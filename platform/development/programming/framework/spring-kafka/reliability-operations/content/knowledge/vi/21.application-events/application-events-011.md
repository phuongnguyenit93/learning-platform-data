# ListenerContainerPartitionIdleEvent

Trong Spring Kafka, một listener có thể subscribe topic chứa nhiều partition. Có những thời điểm hầu hết partition đều có record mới, trong khi một partition không có dữ liệu trong thời gian dài. Nếu chỉ theo dõi trạng thái consumer container hoặc tổng số record được xử lý, tình trạng này rất dễ bị bỏ qua.

**`ListenerContainerPartitionIdleEvent`** là Spring Kafka application event dùng để thông báo rằng **một partition do listener container theo dõi đã không nhận được record trong khoảng thời gian idle được cấu hình**. Sự kiện giúp ứng dụng phân biệt một partition không có hoạt động với việc cả container ngừng tiêu thụ, hỗ trợ quan sát phân bố tải, phát hiện nguồn dữ liệu ngừng gửi và hỗ trợ các quy trình vận hành.

Đây là **tín hiệu quan sát lifecycle và dữ liệu đến ở cấp partition**, không phải Kafka record và không phải bằng chứng rằng broker không có record hoặc listener đã xử lý hết backlog. Để chẩn đoán chính xác, cần kết hợp event với consumer group assignment, consumer lag, offset, pause state và tình trạng producer.

## 1. Vì sao cần theo dõi idle ở cấp partition?

Giả sử topic `orders.events` có bốn partition:

~~~text
orders.events
    |
    +---- partition 0: đều đặn có sự kiện
    +---- partition 1: đều đặn có sự kiện
    +---- partition 2: không có record mới 5 phút
    +---- partition 3: đều đặn có sự kiện
                              |
                              v
                    Spring Kafka listener
~~~

Consumer vẫn xử lý nhiều record mỗi giây từ các partition 0, 1 và 3. Vì thế, một metric “container đang xử lý record” có thể vẫn hoàn toàn bình thường. Nhưng nếu partition 2 tương ứng với một shard, khách hàng hoặc nguồn dữ liệu quan trọng, sự im lặng kéo dài có thể cần được điều tra.

`ListenerContainerPartitionIdleEvent` giúp phát hiện tình trạng **idle cục bộ** này mà không cần đợi toàn bộ container không còn record.

Nó hữu ích trong các tình huống:

- Một partition gần như không còn record trong khi các partition khác có traffic.
- Một upstream shard hoặc routing key có nguy cơ ngừng phát dữ liệu.
- Cần theo dõi sự phân bố records và khả năng một số partition trở thành “lạnh”.
- Một quy trình muốn quan sát thời gian không nhận dữ liệu của từng partition.
- Cần phân biệt consumer vẫn running với việc dữ liệu không đến một partition cụ thể.

Tuy vậy, Kafka **không bảo đảm** mọi partition phải luôn có traffic. Có nhiều partition idle là hoàn toàn bình thường với workload thưa, dữ liệu theo giờ hoặc phân bố key không đều. Cảnh báo chỉ nên phát khi phù hợp hợp đồng nghiệp vụ.

## 2. Sự khác biệt giữa idle container và idle partition

Spring Kafka có event cho trạng thái idle của **toàn container** và event cho **từng partition**.

| Tín hiệu | Phạm vi quan sát | Ý nghĩa |
|---|---|---|
| `ListenerContainerIdleEvent` | Toàn listener container/consumer | Không có record được nhận trong khoảng idle của container. |
| **`ListenerContainerPartitionIdleEvent`** | Một topic-partition cụ thể | Partition này không có record được nhận trong khoảng idle được cấu hình. |
| `ListenerContainerNoLongerIdleEvent` | Container | Sau thời gian container idle, có record mới được nhận. |
| `ListenerContainerPartitionNoLongerIdleEvent` | Partition | Partition từng idle nay có record được nhận trở lại. |
| `NonResponsiveConsumerEvent` | Khả năng poll/tiến triển của consumer | Consumer không đáp ứng cơ chế kiểm tra poll theo ngưỡng; không đồng nghĩa thiếu record. |
| `ConsumerStoppedEvent` | Consumer lifecycle | Consumer đã dừng, có thể kèm nguyên nhân tùy phiên bản. |

Ví dụ:

~~~text
Partition 0: 10 records/giây
Partition 1:  8 records/giây
Partition 2:  0 records/giây

Container tổng thể: có record, KHÔNG nhất thiết idle
Partition 2: idle, có thể phát PartitionIdleEvent
~~~

Vì vậy, **không dùng `ListenerContainerIdleEvent` để thay thế hoàn toàn `ListenerContainerPartitionIdleEvent`** nếu bài toán vận hành cần biết partition nào không có dữ liệu.

Ngược lại, không nên coi nhiều partition idle riêng lẻ là tương đương toàn bộ container đã dừng. Một container có thể hoạt động bình thường và giữ group membership dù không có record mới.

## 3. Điều kiện phát sinh partition idle event

Mô hình khái niệm:

1. Consumer container đang chạy và theo dõi các partition được giao.
2. Với mỗi partition, framework duy trì thông tin lần cuối có record được nhận hoặc mốc theo dõi idle tương ứng.
3. Khi thời gian không nhận record của partition đạt ngưỡng cấu hình, container có thể publish `ListenerContainerPartitionIdleEvent`.
4. Nếu partition tiếp tục không có record, sự kiện idle có thể được phát thêm theo khoảng thời gian cấu hình.
5. Khi partition trước đó idle nhận được record, framework có thể phát `ListenerContainerPartitionNoLongerIdleEvent` để báo trạng thái thay đổi.

~~~text
Partition P1
  |
  +---- record ở T0
  |
  +---- không có record
  |
  +---- đạt ngưỡng idle -> PartitionIdleEvent
  |
  +---- tiếp tục không có record -> có thể phát idle event tiếp
  |
  +---- record mới -> PartitionNoLongerIdleEvent
~~~

Đây là **sơ đồ khái niệm**. Thời điểm phát chính xác phụ thuộc vào vòng `poll()`, container implementation, cấu hình, phiên bản Spring Kafka, thread scheduling và cách consumer được pause/resume.

Sự kiện không phải một timer real-time có độ chính xác tuyệt đối tới millisecond. Nếu listener bị chặn trong xử lý record lâu hoặc container chưa trở lại vòng kiểm tra idle, event có thể đến trễ hơn ngưỡng đã đặt.

## 4. Cấu hình idlePartitionEventInterval

Trong Spring Kafka, thuộc tính trọng tâm là **`ContainerProperties.idlePartitionEventInterval`**, thường được cấu hình qua method:

~~~java
factory.getContainerProperties()
        .setIdlePartitionEventInterval(30_000L);
~~~

Giá trị trong ví dụ là **30.000 millisecond = 30 giây**. Khi ứng dụng không cấu hình ngưỡng này, đừng mặc định rằng framework sẽ tự phát partition idle events ở một khoảng chờ hữu ích; cần chủ động bật tính năng.

Một listener container factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        // Sau 30 giây không nhận record ở một partition,
        // container có thể phát partition-idle event.
        factory.getContainerProperties()
                .setIdlePartitionEventInterval(30_000L);

        return factory;
    }
}
~~~

Listener dùng factory:

~~~java
@KafkaListener(
        id = "orders-listener",
        groupId = "orders-service",
        topics = "orders.events",
        containerFactory = "orderListenerFactory")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Trong ví dụ này, `OrderEvent` và `OrderService` là các kiểu nghiệp vụ do ứng dụng định nghĩa; bean consumer factory, serializer/deserializer và Kafka bootstrap servers phải được cấu hình riêng.

### 4.1. Đừng nhầm với idleEventInterval

Hai thuộc tính thường bị nhầm:

- **`idleEventInterval`:** theo dõi idle ở phạm vi container.
- **`idlePartitionEventInterval`:** theo dõi idle ở phạm vi từng topic-partition.

Ví dụ:

~~~java
factory.getContainerProperties().setIdleEventInterval(60_000L);
factory.getContainerProperties().setIdlePartitionEventInterval(15_000L);
~~~

Một container có thể phát partition-idle event cho một partition sau 15 giây, dù các partition khác vẫn có dữ liệu. Chỉ khi container không nhận record trong 60 giây thì sự kiện idle cấp container mới phù hợp với ngưỡng trong ví dụ.

Một số phiên bản Spring Kafka có hỗ trợ cấu hình idle cấp container qua thuộc tính annotation `@KafkaListener`, nhưng **không nên giả định partition idle có cùng thuộc tính annotation**. Cách rõ ràng là đặt `idlePartitionEventInterval` trên `ContainerProperties` của container factory hoặc container cụ thể theo API đang dùng.

### 4.2. Chọn ngưỡng theo tần suất dữ liệu

Không có một ngưỡng phù hợp cho mọi workload:

| Workload | Nhịp dữ liệu mong đợi | Hướng chọn ngưỡng |
|---|---|---|
| Sự kiện thanh toán liên tục trên nhiều partition | Hàng giây hoặc liên tục | Ngưỡng tương đối ngắn, có cơ chế khử nhiễu. |
| Đồng bộ dữ liệu theo batch | Vài phút hoặc theo lịch | Ngưỡng dài hơn chu kỳ batch và thời gian trễ bình thường. |
| Sự kiện rất hiếm | Có thể hàng giờ không có record | Không cảnh báo chỉ vì partition idle. |
| Nhiều shard không đồng đều | Tùy từng shard | Dùng ngưỡng/ngữ cảnh riêng hoặc so sánh traffic thực tế. |
| Hệ thống gần real-time có SLA phát dữ liệu | Có kỳ vọng rõ về tối đa thời gian im lặng | Ngưỡng dựa trên SLA và thời gian truyền/scheduling. |

Nếu ngưỡng quá ngắn, ứng dụng có thể phát nhiều event và alert không có giá trị. Nếu quá dài, phát hiện nguồn phát dữ liệu ngừng hoạt động sẽ chậm.

## 5. Nhận event bằng @EventListener

Package sự kiện:

~~~java
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
~~~

Một Spring bean nhận event:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionIdleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionIdleObserver.class);

    @EventListener
    public void onPartitionIdle(
            ListenerContainerPartitionIdleEvent event) {

        log.info("Kafka partition idle: source={}, container={}",
                event.getSource(),
                event.getContainer());
    }
}
~~~

`@EventListener` được Spring gọi khi application context nhận event tương ứng. Đây là cơ chế event **in-process**; nó không tự tạo Kafka record, không có consumer group riêng và không lưu sự kiện vào broker.

Tùy phiên bản Spring Kafka, event còn cung cấp các thông tin như topic-partition đang idle, listener ID, idle duration, consumer hoặc trạng thái pause. Khi viết code production, nên sử dụng API được công bố ở đúng phiên bản thay vì trích metadata bằng cách parse `toString()` của source.

### 5.1. Lấy topic-partition và idle time

Với phiên bản cung cấp các accessor tương ứng, có thể dùng các thông tin của event để ghi metric theo partition:

~~~java
@EventListener
public void onPartitionIdle(
        ListenerContainerPartitionIdleEvent event) {

    TopicPartition partition = event.getTopicPartition();
    long idleMillis = event.getIdleTime();

    log.info(
            "Partition idle topic={} partition={} idleMillis={}",
            partition.topic(),
            partition.partition(),
            idleMillis);
}
~~~

Import `TopicPartition` từ `org.apache.kafka.common.TopicPartition`. Giá trị `idleMillis` biểu diễn khoảng thời gian idle mà framework báo tại thời điểm phát event; nó không nhất thiết bằng chính xác giá trị ngưỡng và có thể lớn hơn do poll/scheduling.

Trong ứng dụng có nhiều listener dùng chung một topic, thêm listener/container identity vào log để không nhầm sự im lặng của một consumer group với sự im lặng toàn topic.

### 5.2. Nhận event bằng ApplicationListener

Nếu muốn khai báo kiểu listener rõ ràng:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionIdleListener
        implements ApplicationListener<ListenerContainerPartitionIdleEvent> {

    @Override
    public void onApplicationEvent(
            ListenerContainerPartitionIdleEvent event) {
        // Cập nhật số liệu theo topic-partition.
        metrics.recordPartitionIdle(event);
    }
}
~~~

Hai cách `@EventListener` và `ApplicationListener` đều nhận application event; dùng một cách thống nhất để tránh ghi lặp số liệu khi không cần thiết.

## 6. Khi partition nhận record trở lại

Một partition trước đó idle không nhất thiết tiếp tục idle mãi. Khi có record trở lại, Spring Kafka có event tương ứng là **`ListenerContainerPartitionNoLongerIdleEvent`** trong các phiên bản hỗ trợ.

~~~text
P2: có record
     |
     v
30 giây không có record
     |
     +---- ListenerContainerPartitionIdleEvent
     |
     v
P2 nhận record mới
     |
     +---- ListenerContainerPartitionNoLongerIdleEvent
     |
     v
Trạng thái P2 không còn idle
~~~

Ví dụ listener quan sát cả hai chuyển đổi:

~~~java
@Component
public class PartitionActivityLogger {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionActivityLogger.class);

    @EventListener
    public void onIdle(ListenerContainerPartitionIdleEvent event) {
        log.info("Partition entered idle state: {}",
                event.getSource());
    }

    @EventListener
    public void onActive(
            ListenerContainerPartitionNoLongerIdleEvent event) {
        log.info("Partition no longer idle: {}",
                event.getSource());
    }
}
~~~

Nếu ứng dụng duy trì gauge trạng thái idle, nó cần xử lý **cả sự kiện idle và no-longer-idle** và đối soát khi consumer bị stop/rebalance. Không chỉ nhận sự kiện idle rồi tăng một biến trạng thái vĩnh viễn, vì partition sau đó có thể có dữ liệu hoặc được chuyển sang consumer member khác.

## 7. Idleness và consumer lag là hai khái niệm khác nhau

Một partition không được listener nhận record trong một khoảng thời gian chưa đủ để kết luận broker không có dữ liệu.

**Consumer lag** thường được tính từ log end offset và committed consumer group offset:

```text
lag = log end offset - committed offset
```

Diễn giải cần cẩn thận vì committed offset có thể trễ so với consumer position, đặc biệt khi xử lý batch hoặc manual ack.

| Partition idle? | Lag | Diễn giải có thể có |
|---|---:|---|
| Có | 0 | Không có dữ liệu mới; bình thường nếu nguồn không phát sự kiện. |
| Có | Cao | Consumer có thể bị pause, kẹt, không theo kịp hoặc lag do offset chưa commit. |
| Không | Cao | Consumer đang xử lý nhưng tốc độ chưa theo kịp producer. |
| Không | 0 hoặc thấp | Có record và consumer có thể theo kịp nguồn. |

`ListenerContainerPartitionIdleEvent` đo **khoảng thời gian không thấy record được nhận ở partition trong ngữ cảnh container**. Nó không thay thế các API đọc log end offset, committed offset hoặc consumer position.

Ví dụ một listener giữ partition 4 nhưng `pause()` partition này: container có thể không nhận record mới từ partition 4, trong khi producer vẫn liên tục ghi vào đó. Khi ấy “idle” không đồng nghĩa upstream ngừng phát record. Phải kiểm tra pause state và lag trước khi cảnh báo.

## 8. Partition assignment và rebalance

Kafka consumer group chỉ gán một partition cho tối đa một consumer member trong cùng group tại một thời điểm. Khi group rebalance, partition có thể bị thu hồi khỏi consumer hiện tại rồi giao cho member khác.

~~~text
Trước rebalance:
  consumer A -> partition 0, partition 1
  consumer B -> partition 2

Sau rebalance:
  consumer A -> partition 0
  consumer B -> partition 1, partition 2
~~~

Nếu một partition trước đó idle trên consumer A, sau rebalance nó có thể được quản lý bởi consumer B. **Event lịch sử của A không còn chứng minh trạng thái hiện tại của partition trên B.**

Trong ứng dụng duy trì bảng trạng thái idle theo partition:

1. Lắng nghe các events idle/no-longer-idle để ghi nhận chuyển đổi.
2. Theo dõi `onPartitionsAssigned` và `onPartitionsRevoked` qua rebalance listener hoặc API tương ứng.
3. Xóa/cập nhật trạng thái khi container mất quyền sở hữu partition.
4. Không coi idle state cũ là dữ liệu chính xác vĩnh viễn sau rebalance.
5. Dùng metrics của consumer group để xác minh owner mới đang hoạt động.

Không dùng partition idle event để thay thế `ConsumerRebalanceListener` hoặc `ConsumerAwareRebalanceListener`. Đây là hai cơ chế có mục đích khác nhau.

### 8.1. Một partition không được assign không nhất thiết idle

Nếu số consumer lớn hơn số partition, một số consumer không nhận partition. Không thể mong chờ partition idle event từ consumer **không sở hữu partition đó**.

Vì vậy, khi quan sát không có event cho một partition, hãy kiểm tra:

- Partition có tồn tại và thuộc topic đã subscribe không?
- Consumer group có đang có member sở hữu nó không?
- Listener container có running và polling không?
- Ngưỡng idle đã được cấu hình chưa?
- Partition vừa được assign lại hay đã bị revoked?
- Event observer có đang nhận event từ đúng application context không?

Không có event không phải bằng chứng Kafka đang healthy.

## 9. ConcurrentMessageListenerContainer và phạm vi event

Một listener với `concurrency = 3` có thể có ba child consumers:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> ordersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
            .setIdlePartitionEventInterval(20_000L);

    return factory;
}
~~~

~~~text
Concurrent listener container
      |
      +---- consumer A -> p0, p1
      +---- consumer B -> p2
      +---- consumer C -> p3, p4
~~~

Nếu p1 idle, event sẽ liên quan tới partition p1 trong bối cảnh consumer/container đang sở hữu nó. Event không nói rằng cả child consumer A hoặc toàn parent container không có record, vì consumer A vẫn có thể xử lý p0.

Trong monitoring, nên gắn các trường:

- Topic và partition.
- Listener ID/container identity.
- Consumer group.
- Instance/pod ID nếu cần đối chiếu với deployment.
- Thời gian idle tính bằng millisecond.
- Trạng thái pause và số partition được assign.

Khi metric dùng topic/partition làm labels, cần kiểm soát cardinality nếu cluster có số partition rất lớn. Không đưa event ID, record key hoặc offset vào mọi metric label.

## 10. Ảnh hưởng của pause/resume

Spring Kafka cho phép pause listener container hoặc partition trong các tình huống backpressure, bảo trì hay điều tiết throughput. Khi pause, consumer vẫn có thể polling để duy trì group membership mà không giao record mới cho listener.

Ví dụ một partition đang pause:

~~~text
Producer tiếp tục ghi vào partition 3
            |
            v
Broker log end offset tăng
            |
            v
Consumer đã pause partition 3
            |
            v
Listener không nhận record mới từ partition 3
            |
            +---- Partition idle event có thể xuất hiện
            |
            +---- Consumer lag có thể tăng
~~~

Do vậy, **trước khi gọi một partition idle là upstream outage, kiểm tra liệu container hoặc partition có đang bị pause**. Một pause có chủ đích thường không cần cảnh báo “nguồn phát đã ngừng”.

Có thể đọc trạng thái pause qua API container thích hợp và thông tin event nếu phiên bản cung cấp. Không nên gọi trực tiếp các thao tác KafkaConsumer như `pause()`, `resume()`, `seek()` từ event listener bất đồng bộ mà không bảo đảm đúng consumer thread.

### 10.1. Không tự động seek/replay chỉ vì partition idle

Một lỗi thiết kế là thấy partition idle rồi tự gọi `seekToBeginning` hoặc reset offsets để “kích hoạt” dữ liệu. Nếu partition không có record mới, reset offset sẽ làm đọc lại record cũ, có thể tạo side effect trùng hoặc sai thứ tự.

Phản ứng phù hợp hơn thường là:

1. Quan sát lag và nguồn phát.
2. Kiểm tra consumer assignment/pause.
3. Đối chiếu lịch sản sinh sự kiện theo nghiệp vụ.
4. Nếu cần, phát alert hoặc đánh dấu shard im lặng trong monitoring.
5. Chỉ replay sau khi có quyết định rõ ràng và idempotency phù hợp.

## 11. Event listener được thực thi trên thread nào?

Application events đi qua Spring `ApplicationEventMulticaster`. Với multicaster đồng bộ mặc định, `@EventListener` có thể được gọi ngay trên **consumer thread** đang phát event. Nếu cấu hình multicaster có executor bất đồng bộ, event listener có thể chạy ở thread khác.

Điều này ảnh hưởng trực tiếp đến an toàn của thao tác:

- Kafka `Consumer` không thread-safe cho các thao tác thông thường.
- Một event có thể cung cấp tham chiếu consumer, nhưng không nên dùng tham chiếu đó từ thread bất kỳ.
- Block lâu trong event handler đồng bộ có thể làm chậm vòng `poll()` và ảnh hưởng consumer group.
- Gọi lại container lifecycle methods từ callback không phù hợp có thể gây deadlock hoặc race.
- Với multicaster async, event order và thời gian thực thi không nhất thiết trùng thời điểm phát event.

Vì vậy, `@EventListener` cho partition idle nên làm việc **nhẹ và bounded**:

~~~java
@EventListener
public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
    TopicPartition tp = event.getTopicPartition();

    log.info("Partition idle: {}-{}, idleMs={}",
            tp.topic(),
            tp.partition(),
            event.getIdleTime());

    metrics.recordIdleObservation(tp.topic(), tp.partition());
}
~~~

Đừng gọi HTTP chậm, database migration hoặc truy vấn nặng ở đây. Nếu cần enrichment dữ liệu, có thể đẩy một **thông báo nhỏ không chứa Consumer object** sang một executor riêng để xử lý, kèm giới hạn queue và cơ chế tránh trùng.

Nếu event được dùng để yêu cầu pause/resume container, dùng API container hỗ trợ thread-safe request tương ứng và xác minh behavior của phiên bản đang chạy; đừng sử dụng consumer reference bừa bãi.

## 12. Khử nhiễu và tránh alert storm

Một partition có thể tiếp tục idle qua nhiều khoảng thời gian, nên ứng dụng có thể nhận nhiều idle events mà không có thay đổi trạng thái thực sự.

Ví dụ với ngưỡng 30 giây:

~~~text
T+30s  -> PartitionIdleEvent
T+60s  -> PartitionIdleEvent
T+90s  -> PartitionIdleEvent
T+120s -> PartitionIdleEvent
~~~

Đừng tự động gửi một incident mới ở mỗi event. Thay vào đó, duy trì state machine theo partition:

~~~text
ACTIVE
   |
   | lần đầu idle
   v
IDLE (mở một alert nếu phù hợp)
   |
   | idle tiếp tục
   v
IDLE (cập nhật duration/metric, không tạo alert trùng)
   |
   | record mới
   v
ACTIVE (đóng alert hoặc ghi recovered)
~~~

Ứng dụng cần cập nhật state khi rebalance/restart/stop để không giữ “idle” cũ cho partition không còn thuộc consumer hiện tại.

Trong nhiều hệ thống, alert dựa trên **lag + throughput + SLO của producer** có giá trị hơn alert chỉ dựa trên idle. Ví dụ topic sự kiện xử lý đơn hàng ít traffic ban đêm có thể có nhiều partition idle bình thường; nhưng topic heartbeat của các shard bắt buộc gửi một lần mỗi phút thì idle kéo dài là bất thường.

## 13. Phân biệt sự cố upstream và sự cố consumer

Khi nhận `ListenerContainerPartitionIdleEvent`, có thể điều tra theo nhánh:

~~~text
Partition idle event
       |
       +---- Consumer còn sở hữu partition?
       |          |
       |          +---- Không -> kiểm tra rebalance/assignment
       |
       +---- Partition có bị pause?
       |          |
       |          +---- Có -> backpressure/maintenance
       |
       +---- Lag có tăng?
       |          |
       |          +---- Có -> consumer đang chậm/kẹt/offset chưa commit
       |          |
       |          +---- Không -> có thể không có dữ liệu mới
       |
       +---- Producer có ghi vào partition?
                  |
                  +---- Không -> kiểm tra upstream routing, source, schedule
                  +---- Có -> kiểm tra fetch, permission, offset, consumer state
~~~

Các nguyên nhân thường gặp:

| Hiện tượng | Nguyên nhân có thể | Bằng chứng cần thu thập |
|---|---|---|
| Một partition không có record, lag gần 0 | Workload thưa, producer key skew, upstream shard dừng | Records-in per partition, producer logs, business schedule. |
| Partition idle nhưng lag cao | Pause, consumer bị chặn, offset chưa commit, fetch vấn đề | Pause state, consumer metrics, thread dump, committed offset. |
| Nhiều partition đồng thời idle | Upstream ngừng phát, hệ thống đang ít tải | Producer throughput, broker records-in, lịch dữ liệu. |
| Idle sau rebalance | Assignment thay đổi, trạng thái theo dõi vừa được khởi tạo lại | Group assignment, revoke/assign callbacks, instance logs. |
| Idle event không xuất hiện dù không có record | Ngưỡng chưa bật, container dừng, observer thiếu, poll bị kẹt | ContainerProperties, lifecycle logs, application event wiring. |
| Idle rất nhiều lần trong một khoảng ngắn | Threshold quá thấp, event lặp hoặc nhiều container | Metric event frequency, concurrency, assigned partitions. |

Không dùng một event để khẳng định nguyên nhân root cause. Nó là **triệu chứng quan sát**, cần đặt trong ngữ cảnh hệ thống.

## 14. Phân biệt partition idle với listener xử lý chậm

Giả sử một consumer nhận batch gồm record ở các partition 0 và 1; listener xử lý một record rất chậm. Dù broker đang có dữ liệu, consumer thread có thể chưa quay lại `poll()` để nhận thêm.

Trong tình huống này:

- Thời gian giữa hai lần giao record cho listener có thể dài.
- Consumer lag có thể tăng.
- `NonResponsiveConsumerEvent` hoặc các metric poll/processing có thể báo dấu hiệu khác.
- Partition idle event có thể đến trễ vì container không có cơ hội kiểm tra điều kiện idle đúng lịch.

Do đó, không xem partition idle event là **bộ phát hiện consumer bị treo**. Với consumer không poll hoặc bị block, cần theo dõi poll interval, thread dumps, consumer group rebalances và processing latency.

Nếu listener xử lý lâu, còn phải xem `max.poll.interval.ms` và các timeouts của dependency. Một consumer bị loại khỏi group do quá lâu không poll là vấn đề lifecycle khác với việc partition đơn giản không có record mới.

## 15. Ảnh hưởng của record filter, retry và transaction

### 15.1. Record filtering

Một record có thể được consumer fetch nhưng bị filter trước khi vào business listener (ví dụ `RecordFilterStrategy`). Việc có phát idle/no-longer-idle event hay không có thể liên quan điểm Spring Kafka cập nhật trạng thái nhận record trong implementation.

Không suy luận “không có business handler invocation” luôn tương đương “partition idle” nếu pipeline có filter, interceptor hoặc batch listener. Khi cần hiểu business activity, đo metric **record được nghiệp vụ chấp nhận và xử lý thành công** riêng với metric container nhận record.

### 15.2. Retry và DLT

Khi một record lỗi và được retry, partition có thể không tiến theo nhịp bình thường; với blocking retry, partition còn có thể bị chặn bởi poison record. `ListenerContainerPartitionIdleEvent` không thay thế metric retry, error handler, DLT và committed offsets.

Non-blocking retry chuyển record qua retry topics; idle ở main topic không có nghĩa record đã xử lý thành công ở retry topic. Cần theo dõi main, retry và DLT theo từng group/topic thích hợp.

### 15.3. Kafka transaction

Với Kafka transactional listener, một record có thể được nhận và listener đã chạy nhưng Kafka transaction cuối cùng rollback. Idle event chỉ thể hiện **hoạt động nhận record**, không xác nhận offset hoặc output transaction đã commit.

Nếu cần bảo đảm end-to-end, kiểm tra:

- Output topic bằng consumer `read_committed`.
- Committed offset của group.
- Kết quả recovery/AfterRollbackProcessor.
- DLT record khi hết retry.
- Business database state và idempotency nếu có side effects ngoài Kafka.

## 16. Logging và metric cho partition idle

Một structured log minh họa:

~~~text
event_type=ListenerContainerPartitionIdleEvent
service=orders-worker
listener_id=orders-listener
group_id=orders-service
topic=orders.events
partition=2
idle_ms=60000
instance_id=orders-worker-3
observed_at=2026-11-15T16:00:00Z
~~~

Các trường `service`, `group_id`, `instance_id`, `observed_at` là metadata do ứng dụng cung cấp hoặc enrichment từ runtime, không nhất thiết là properties trực tiếp của event.

Nên có các metric:

| Metric | Mục đích |
|---|---|
| Partition idle event count | Phát hiện số lần container ghi nhận idle. |
| Partition idle duration | Đo khoảng thời gian không nhận record ở từng partition. |
| Partition currently idle gauge | Phản ánh trạng thái gần nhất, cần đối soát khi rebalance. |
| Records consumed per partition | Phân biệt không có dữ liệu với ít dữ liệu. |
| Consumer lag per partition | Kiểm tra partition không tiến vì backlog hay nguồn không phát. |
| Records produced per partition | Kiểm tra upstream routing/key skew. |
| Partition pause state | Phân biệt idle chủ đích với lỗi. |
| Consumer group assignment | Biết member đang sở hữu partition. |
| Listener processing latency | Loại trừ tình huống consumer xử lý quá lâu. |

Không dùng topic-partition làm metric có cardinality không giới hạn nếu cluster có hàng trăm nghìn partition. Cân nhắc tổng hợp theo service, topic và nhóm partition với dashboards có khả năng drill-down.

Một hệ thống alert nên biểu diễn **“partition được kỳ vọng có dữ liệu, nhưng không có trong X phút”**, không phải “mọi partition idle đều lỗi”.

## 17. Integration test với Embedded Kafka hoặc Testcontainers

Một integration test cần xác nhận Spring Kafka **thực sự phát event** khi partition không nhận record trong ngưỡng. Test chỉ gọi trực tiếp method `onPartitionIdle` không chứng minh event được tạo bởi listener container.

Cách xây dựng test:

1. Tạo topic có ít nhất hai partition, ví dụ `idle.test` gồm partition 0 và 1.
2. Tạo listener container với `idlePartitionEventInterval` ngắn, chẳng hạn 1.000–2.000 ms.
3. Bảo đảm listener có assignment cho các partition cần kiểm tra.
4. Gửi record đều đặn vào partition 0, không gửi vào partition 1.
5. Chờ `ListenerContainerPartitionIdleEvent` của partition 1 bằng queue/latch.
6. Xác nhận partition 0 vẫn nhận record trong thời gian partition 1 idle.
7. Gửi record vào partition 1, chờ event no-longer-idle nếu phiên bản hỗ trợ.
8. Stop container và cleanup consumer group, topic/test resources.

### 17.1. Probe nhận event

~~~java
@Component
public class PartitionIdleProbe {

    private final BlockingQueue<ListenerContainerPartitionIdleEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onIdle(ListenerContainerPartitionIdleEvent event) {
        events.offer(event);
    }

    public ListenerContainerPartitionIdleEvent await(Duration timeout)
            throws InterruptedException {
        return events.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Imports chính gồm `java.time.Duration`, `java.util.concurrent.BlockingQueue`, `LinkedBlockingQueue`, `TimeUnit` và Spring Kafka event class.

Để tránh false positive khi context có nhiều listeners, test nên lọc theo listener ID và topic-partition. Có thể dùng vòng đợi với deadline hữu hạn:

~~~java
ListenerContainerPartitionIdleEvent matching = null;
long deadline = System.nanoTime() + Duration.ofSeconds(20).toNanos();

while (System.nanoTime() < deadline && matching == null) {
    ListenerContainerPartitionIdleEvent event =
            probe.await(Duration.ofMillis(500));

    if (event != null
            && event.getTopicPartition().topic().equals("idle.test")
            && event.getTopicPartition().partition() == 1) {
        matching = event;
    }
}

assertThat(matching).isNotNull();
~~~

Đây là một fragment kiểm thử dùng probe đã khai báo. Cần tạo topic/factory/consumer group và start listener trong test context trước khi gọi; không dùng fragment độc lập làm một chương trình hoàn chỉnh.

### 17.2. Kiểm tra partition có dữ liệu trở lại

Có thể gửi record chỉ định partition:

~~~java
kafkaTemplate.send("idle.test", 1, "key-1", "wake-up");
~~~

Sau khi partition 1 nhận record, ứng dụng có thể phát `ListenerContainerPartitionNoLongerIdleEvent`. Test nên quan sát loại event đó hoặc ít nhất xác nhận listener đã nhận record từ partition 1.

Để test deterministic:

- Bảo đảm partition 1 đã được **assign** cho listener thử nghiệm.
- Sử dụng consumer group riêng cho test.
- Không cho test khác cùng lúc ghi vào topic `idle.test`.
- Không dùng thời điểm chính xác tuyệt đối của event làm assertion.
- Đặt timeout hữu hạn, chấp nhận scheduling jitter.
- Nếu kiểm tra “partition 0 vẫn hoạt động”, gửi nhiều record vào partition 0 trong suốt cửa sổ quan sát.
- Tránh các sleep dài cố định; dùng queue/latch và condition-based waiting.

### 17.3. Kiểm thử pause và rebalance

Các bài test bổ sung có giá trị:

- **Pause partition 1:** xác nhận trạng thái event, lag và pause không bị diễn giải thành upstream failure.
- **Rebalance:** thêm/bớt consumer; kiểm tra observer không giữ idle state sai cho partition vừa revoke.
- **Concurrency > partition count:** xác nhận không suy ra idle từ consumer không nhận partition.
- **Listener xử lý chậm:** kiểm tra event timing có thể bị trì hoãn; không gán nhầm là broker ngừng gửi.
- **Container stop:** không nhận thêm event từ container đã dừng, state monitoring được cleanup.
- **Retry/DLT:** record lỗi đi qua retry pipeline; partition idle event không được dùng làm tín hiệu success.

Không nên chạy các bài test này bằng cách thay đổi offset hoặc force kill consumer trên một group đang được những test khác sử dụng.

## 18. Những sai lầm thường gặp

- **Nhầm partition idle với container idle:** các partition khác vẫn có thể có traffic.
- **Nhầm idle với lag bằng 0:** partition có thể không nhận record vì pause hoặc xử lý chậm trong khi lag tăng.
- **Nhầm idle với producer đã chết:** topic/partition có thể bình thường không có sự kiện mới.
- **Không cấu hình `idlePartitionEventInterval`:** listener không được kỳ vọng tự phát event như mong muốn.
- **Đặt ngưỡng quá ngắn:** event lặp nhiều lần và tạo alert storm.
- **Chỉ nhận idle event, bỏ qua no-longer-idle:** metric giữ trạng thái idle dù record đã trở lại.
- **Không xử lý rebalance:** giữ thông tin idle cho partition mà consumer đã mất quyền sở hữu.
- **Dùng event để reset offset/replay:** có thể tạo duplicate, sai business state.
- **Thao tác trực tiếp KafkaConsumer từ event listener async:** vi phạm ràng buộc thread ownership.
- **Block consumer thread trong event handler:** gây poll latency, lag hoặc rebalance ngoài ý muốn.
- **Cho rằng event xác nhận business processing đã thành công:** transaction có thể rollback.
- **Xem không có event là bằng chứng partition đang khỏe:** container có thể stop hoặc observer không nhận event.
- **Dùng event in-memory như audit bền vững:** JVM crash có thể làm mất event chưa được ghi ra ngoài.
- **Đếm event bằng số nguồn phát ngừng hoạt động:** nhiều consumer/group có thể cùng nhận các event cho một topic-partition.
- **Không lọc event theo listener và partition trong test:** một event từ listener khác làm assertion pass sai.

## 19. Quy trình chẩn đoán partition idle trong production

Khi quan sát partition idle bất thường, thực hiện lần lượt:

1. **Xác nhận context:** topic, partition, listener ID, consumer group và instance đang sở hữu.
2. **Đọc lag:** phân biệt không có record mới với consumer không theo kịp.
3. **Kiểm tra pause/resume:** container hoặc partition có được pause có chủ đích không?
4. **Kiểm tra producer traffic theo partition:** key skew, partitioner, upstream outage hoặc batch schedule.
5. **Xem consumer state:** container running, poll latency, thread dumps nếu xử lý bị chặn.
6. **Đối chiếu rebalance:** partition vừa chuyển owner hay assignment mới chưa ổn định?
7. **Xem retry và deserialization errors:** có record lỗi liên tục hoặc DLT tăng không?
8. **Đánh giá kỳ vọng nghiệp vụ:** partition này có bắt buộc nhận record trong cửa sổ đang xét không?
9. **Gắn mức độ cảnh báo phù hợp:** nhiều trường hợp chỉ cần dashboard, không cần incident.
10. **Xác nhận phục hồi:** record đến trở lại, lag và processing metrics ổn định, idle state được cập nhật.

Nếu một partition không có record nhưng producer và broker đều xác nhận không có dữ liệu mới, hệ thống có thể hoàn toàn bình thường. Nếu producer xác nhận đã ghi nhiều record trong khi consumer không nhận, hãy điều tra assignment, fetch, pause, committed offset, deserialization và consumer health.

## 20. Thiết kế ứng dụng theo dõi idle một cách an toàn

Một mô hình thực tế:

~~~text
ListenerContainerPartitionIdleEvent
                |
                v
Spring @EventListener (xử lý nhẹ)
                |
                +---- structured log / idle metrics
                +---- cập nhật state theo topic-partition và owner
                |
                +---- kết hợp:
                        PartitionNoLongerIdleEvent
                        rebalance assignment
                        consumer lag
                        producer throughput
                        pause state
                        business SLA
                |
                v
Alert hoặc operational workflow khi đủ bằng chứng
~~~

Event nên là **đầu vào cho observability**, không phải điểm duy nhất quyết định commit offset, replay dữ liệu hoặc đánh dấu giao dịch thành công. Khi consumer group thay đổi, state được cập nhật theo ownership mới; khi record quay lại, idle state phải được kết thúc; khi JVM crash, monitoring bên ngoài vẫn cần dựa vào committed offsets và dữ liệu broker.

**`ListenerContainerPartitionIdleEvent`** giúp Spring Kafka nhìn thấy sự im lặng của *một partition cụ thể* ngay cả khi toàn listener vẫn nhận record từ các partition khác. Giá trị vận hành của nó nằm ở khả năng phát hiện sớm các shard không còn hoạt động theo kỳ vọng, đồng thời tránh kết luận sai bằng cách kiểm chứng lag, assignment, pause và upstream traffic trước khi hành động.
