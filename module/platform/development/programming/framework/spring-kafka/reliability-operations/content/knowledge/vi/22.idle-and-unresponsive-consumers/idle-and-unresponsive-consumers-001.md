# idleEventInterval

Trong Spring Kafka, một Kafka consumer có thể đang chạy bình thường nhưng **không nhận được record nào** trong một thời gian dài. Điều này có thể hoàn toàn hợp lệ với topic ít traffic, hoặc là dấu hiệu cần kiểm tra khi ứng dụng mong đợi có dữ liệu liên tục. Thuộc tính **`idleEventInterval`** cho phép listener container phát sự kiện **`ListenerContainerIdleEvent`** khi không có message được nhận trong một khoảng thời gian do ứng dụng cấu hình.

Đây là một cơ chế quan sát của chương **Idle và non-responsive**: nó giúp phát hiện và phản ứng với tình trạng không nhận record, nhưng phải phân biệt với trường hợp consumer bị kẹt ở `poll()`, bị pause có chủ đích, chưa được gán partition hoặc topic thực sự không có dữ liệu.

**Điểm cốt lõi:** `idleEventInterval` không tự retry, không điều khiển offset, không tự khởi động lại consumer và không chứng minh Kafka gặp sự cố. Nó chỉ cấu hình **khi nào Spring Kafka publish một application event thông báo listener đang idle**.

## 1. Idle của listener container nghĩa là gì?

Một listener container thường lặp lại:

~~~text
consumer.poll()
      |
      +-- Có records --> dispatch tới @KafkaListener
      |                     |
      |                     +--> xử lý thành công/lỗi theo handler
      |
      +-- Không có records --> tiếp tục polling
                                |
                                +--> idle đủ khoảng cấu hình?
                                          |
                                          +-- Có --> ListenerContainerIdleEvent
~~~

Khi `idleEventInterval` được cấu hình, Spring Kafka theo dõi thời gian từ khi có record gần nhất. Nếu `poll()` trả về không có records và thời gian không nhận dữ liệu đạt ngưỡng, container có thể publish `ListenerContainerIdleEvent`. Khi tình trạng idle tiếp diễn, event được phát **lặp lại theo khoảng idle interval**, không chỉ phát một lần duy nhất.

Ví dụ:

~~~text
idleEventInterval = 60.000 ms

12:00:00   Consumer nhận record cuối
12:01:00   Không có record mới -> phát IdleEvent
12:02:00   Vẫn không có record -> phát IdleEvent
12:03:00   Vẫn không có record -> phát IdleEvent
12:03:20   Nhận record mới -> hết idle
~~~

Mốc trên là **minh họa gần đúng**. Thời gian thực tế phụ thuộc `pollTimeout`, scheduling, thời điểm container kiểm tra và cấu hình liên quan như `idleBeforeDataMultiplier`. `idleEventInterval` không phải đồng hồ real-time chính xác đến từng millisecond.

Idle được hiểu là **không nhận record**, không phải “business listener xử lý xong mọi tác vụ”. Một listener có thể đang thực hiện thao tác bất đồng bộ dài hạn ở thread khác trong khi consumer được xem là idle ở tầng poll.

## 2. Đơn vị, mặc định và thời điểm phát

Thuộc tính được cấu hình bằng **milliseconds**:

~~~java
containerProperties.setIdleEventInterval(60_000L);
~~~

Nghĩa là đặt khoảng quan sát idle cơ bản thành 60 giây. Trong những phiên bản Spring Kafka phổ biến, `idleEventInterval` mặc định là `null`, tức **không bật phát idle events** nếu không cấu hình.

Một vài tham số cần phân biệt:

| Thuộc tính | Ý nghĩa | Ghi chú |
|---|---|---|
| `idleEventInterval` | Khoảng giữa các idle events khi không có message | Milliseconds, mặc định `null` |
| `idleBeforeDataMultiplier` | Hệ số nhân idle interval trước khi container nhận record đầu tiên | Mặc định `5.0` ở các phiên bản hỗ trợ |
| `idlePartitionEventInterval` | Theo dõi idle theo **từng partition** | Tạo loại event khác |
| `pollTimeout` | Khoảng timeout của một lần `poll()` | Có thể ảnh hưởng độ trễ quan sát idle |
| `monitorInterval` | Tần suất monitor kiểm tra consumer không phản hồi | Tính bằng seconds |
| `noPollThreshold` | Ngưỡng xác định consumer poll không phản hồi | Hệ số tương đối với `pollTimeout` |
| `idleBetweenPolls` | Sleep có chủ đích giữa các lần poll để điều tiết | Không phải idle event interval |

**Không nhầm `idleEventInterval` và `idleBetweenPolls`.** Thuộc tính đầu chỉ bật phát notification. Thuộc tính sau chủ động làm chậm vòng poll và cần tính với `max.poll.interval.ms`.

## 3. Cấu hình cho @KafkaListener bằng container factory

Với ứng dụng dùng `@KafkaListener`, có thể cấu hình `idleEventInterval` ở `ConcurrentKafkaListenerContainerFactory`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaIdleMonitoringConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setIdleEventInterval(60_000L);

        return factory;
    }
}
~~~

Listener dùng factory này:

~~~java
@Component
public class OrderConsumer {

    @KafkaListener(
        id = "orders-consumer",
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "ordersKafkaListenerFactory")
    public void onOrder(OrderEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

Ở ví dụ này, nếu consumer không nhận record mới trong khoảng idle áp dụng, Spring Kafka phát `ListenerContainerIdleEvent`. Listener không cần tự cài đặt timer, không cần tự gọi Kafka `poll()` và không cần thêm sleep trong method `onOrder`.

Nếu factory được tái sử dụng bởi nhiều `@KafkaListener`, mọi listener tạo từ factory đó có thể cùng nhận cấu hình idle. Điều này quan trọng khi chỉ muốn quan sát một số topics: nên tạo factory riêng hoặc xác định chính sách logging/alert phù hợp từng listener.

## 4. Cấu hình cho KafkaMessageListenerContainer tạo thủ công

Trong ứng dụng không dùng `@KafkaListener`, có thể cấu hình trực tiếp `ContainerProperties`:

~~~java
@Bean
KafkaMessageListenerContainer<String, String> manualListenerContainer(
        ConsumerFactory<String, String> consumerFactory,
        MessageListener<String, String> messageListener) {

    ContainerProperties properties = new ContainerProperties("audit-events");
    properties.setGroupId("audit-processor");
    properties.setMessageListener(messageListener);
    properties.setIdleEventInterval(30_000L);

    return new KafkaMessageListenerContainer<>(
        consumerFactory,
        properties
    );
}
~~~

Ở đây:

- Topic là `audit-events`.
- Consumer group là `audit-processor`.
- Idle interval được đặt 30 giây.
- Event được phát từ container này, không phải từ một Kafka topic riêng.

`ListenerContainerIdleEvent` là **Spring application event trong process**, không phải một Kafka record tự động được gửi sang Kafka broker.

## 5. Trường hợp trước khi nhận record đầu tiên

Một chi tiết dễ gây hiểu nhầm là `idleBeforeDataMultiplier`. Từ Spring Kafka 2.8, các phiên bản hỗ trợ có hệ số nhân này; mặc định được tài liệu mô tả là **5.0**. Hệ số được dùng **trước khi consumer nhận record đầu tiên**.

Giả sử:

~~~java
factory.getContainerProperties().setIdleEventInterval(60_000L);
factory.getContainerProperties().setIdleBeforeDataMultiplier(5.0);
~~~

Các mốc mong đợi:

~~~text
Container start, chưa nhận record nào
    |
    | Initial idle threshold xấp xỉ:
    | 60 giây * 5 = 300 giây
    v
Idle event đầu tiên có thể xuất hiện sau khoảng 5 phút
    |
    v
Container nhận record đầu tiên
    |
    | Sau đó dùng interval cơ bản 60 giây
    v
Nếu không có record mới, idle events theo interval khoảng 60 giây
~~~

Bảng minh họa:

| Trạng thái | Công thức | Khoảng |
|---|---|---|
| Chưa từng nhận data | `idleEventInterval × idleBeforeDataMultiplier` | 60s × 5 = 300s |
| Đã nhận ít nhất một record | `idleEventInterval` | 60s |
| Không bật `idleEventInterval` | Không phát event chỉ do idle | — |

Mốc thực tế còn phụ thuộc lịch poll và phiên bản. Nếu consumer mới khởi động nhưng không thấy idle event sau đúng 60 giây, cần kiểm tra **`idleBeforeDataMultiplier` trước tiên**, không vội kết luận application event listener bị lỗi.

Có thể điều chỉnh multiplier khi nghiệp vụ cần cảnh báo nhanh hơn lúc startup. Tuy nhiên, việc đặt quá nhỏ trên topic rất ít dữ liệu có thể tạo cảnh báo không có ý nghĩa.

## 6. Lắng nghe ListenerContainerIdleEvent bằng @EventListener

Một cách thường dùng là đăng ký Spring event listener:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaIdleEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleEventObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.warn(
            "Kafka consumer idle: listenerId={} idleMs={} partitions={} paused={}",
            event.getListenerId(),
            event.getIdleTime(),
            event.getTopicPartitions(),
            event.isPaused()
        );
    }
}
~~~

Những method quan trọng:

| Method | Thông tin |
|---|---|
| `getListenerId()` | Listener ID hoặc container bean name |
| `getIdleTime()` | Thời gian container không nhận record, tính bằng milliseconds |
| `getTopicPartitions()` | Tập partitions được assign khi event được tạo |
| `getConsumer()` | Kafka consumer reference khi khả dụng |
| `isPaused()` | Cho biết consumer đang paused tại thời điểm event được publish |
| `getSource(Class)` | Container trực tiếp phát event |
| `getContainer(Class)` | Container tương ứng, có thể là parent khi source là child |

Ứng dụng nhận event của **mọi containers trong application context** nếu không lọc. Vì vậy, trên hệ thống có nhiều topics và listener factories, không nên coi mọi idle event là lỗi của một listener duy nhất.

## 7. Lọc event theo listener ID

Ví dụ chỉ theo dõi `orders-consumer`:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {

    MessageListenerContainer parent =
            event.getContainer(MessageListenerContainer.class);

    if (!"orders-consumer".equals(parent.getListenerId())) {
        return;
    }

    log.info(
        "orders-consumer idle for {} milliseconds; assigned={}",
        event.getIdleTime(),
        event.getTopicPartitions()
    );
}
~~~

Cần chú ý `source` có thể là một child container khi concurrency lớn hơn 1, còn `container` là parent. Khi lọc theo ID, việc so sánh listener ID của parent thường dễ hiểu hơn nếu mục tiêu là toàn bộ logical `@KafkaListener`.

Spring Kafka cũng hỗ trợ `@EventListener(condition = "...")` bằng SpEL. Với concurrent containers, child IDs thường có hậu tố theo quy tắc container. Không nên hardcode một child suffix như thể đó là identity ổn định xuyên restart/rebalance.

Nếu dùng điều kiện SpEL, chỉ viết expression đơn giản và xác định đúng property exposed. Tránh giả định mọi event type đều có `listenerId` cùng ý nghĩa mà không kiểm tra API.

## 8. Khi record xuất hiện lại: ListenerContainerNoLongerIdleEvent

Sau khi container đã phát `ListenerContainerIdleEvent`, nếu nó nhận record mới, Spring Kafka có thể phát `ListenerContainerNoLongerIdleEvent` (được hỗ trợ từ Spring Kafka 2.6.2).

Một chuỗi:

~~~text
12:00:00  Xử lý record cuối
12:01:00  ListenerContainerIdleEvent
12:02:00  ListenerContainerIdleEvent
12:02:15  Nhận record mới
12:02:15  ListenerContainerNoLongerIdleEvent
12:02:15  Listener xử lý record
~~~

Observer:

~~~java
@Component
public class KafkaIdleTransitionObserver {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.warn(
            "CONSUMER_IDLE listener={} idleMs={} paused={}",
            event.getListenerId(),
            event.getIdleTime(),
            event.isPaused()
        );
    }

    @EventListener
    public void onNoLongerIdle(ListenerContainerNoLongerIdleEvent event) {
        log.info(
            "CONSUMER_ACTIVE_AGAIN listener={} previousIdleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }
}
~~~

Khi thiết kế alert, nên xem `ListenerContainerIdleEvent` và `ListenerContainerNoLongerIdleEvent` là **một cặp transition**. Nếu mỗi idle event đều mở một incident mới, một consumer idle 30 phút có thể tạo hàng chục tickets.

Event no-longer-idle chứng minh consumer nhận lại record, nhưng không đảm bảo record đó đã được business listener xử lý và commit thành công. Cần metrics xử lý record và offset để đánh giá data path.

## 9. Idle của cả container khác idle theo từng partition

Một concurrent consumer có thể đang nhận rất nhiều records từ partition 0 nhưng **không nhận record nào từ partition 1**.

~~~text
orders partition 0: 100 records/s
orders partition 1:   0 records/s
orders partition 2:  80 records/s
~~~

Nếu container vẫn nhận records từ các partitions khác, nó có thể **không phát global `ListenerContainerIdleEvent`** mặc dù một partition riêng đã im lặng.

Spring Kafka có cấu hình:

~~~java
factory.getContainerProperties()
       .setIdlePartitionEventInterval(120_000L);
~~~

Thuộc tính này bật phát **`ListenerContainerPartitionIdleEvent`** cho partition không nhận record trong khoảng quy định. Đây là một loại event khác với `ListenerContainerIdleEvent`.

Ví dụ observer:

~~~java
@Component
public class PartitionIdleObserver {

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        log.info(
            "Partition idle: listener={} partition={} idleMs={}",
            event.getListenerId(),
            event.getTopicPartition(),
            event.getIdleTime()
        );
    }
}
~~~

Dùng global idle để biết **consumer không nhận bất kỳ record nào**; dùng partition idle để biết **một partition riêng không có dữ liệu**. Trong hệ thống sharding theo tenant hoặc key, việc theo dõi partition idle có thể hữu ích, nhưng cần hiểu rằng một partition ít traffic hoàn toàn bình thường không nhất thiết là lỗi.

## 10. Idle event khác NonResponsiveConsumerEvent

Đây là phân biệt quan trọng nhất của chương.

**Idle:** `poll()` vẫn quay về bình thường nhưng không có records để giao. Container đủ khả năng tiến đến bước kiểm tra elapsed idle time và phát event.

**Non-responsive:** `poll()` bị giữ quá lâu hoặc không trả quyền điều khiển về container trong thời gian dự kiến. Khi đó container **không thể phát idle event theo cơ chế thông thường** vì consumer thread chưa thoát khỏi lần `poll()`.

| Đặc điểm | `ListenerContainerIdleEvent` | `NonResponsiveConsumerEvent` |
|---|---|---|
| Điều kiện chính | Không nhận messages trong khoảng configured interval | Consumer `poll()` bị giữ lâu vượt ngưỡng monitor |
| Vòng poll | Vẫn tiến triển để có thể kiểm tra idle | Có thể không trả về đúng hạn |
| Cấu hình | `idleEventInterval` | `pollTimeout`, `monitorInterval`, `noPollThreshold` |
| Diễn giải | “Không có dữ liệu mới” | “Consumer có vẻ không phản hồi” |
| Hướng xử lý | Kiểm tra traffic, assignment, pause, lag/SLO | Điều tra poll block, broker/client/network, thread state |
| Có nghĩa broker down? | Không | Cũng không tự chứng minh broker down |

Spring Kafka có monitor phát `NonResponsiveConsumerEvent` khi `poll()` không trả về trong khoảng ngưỡng. Theo tài liệu, `noPollThreshold` mặc định khoảng `3.0` lần `pollTimeout`, monitor kiểm tra mỗi `monitorInterval` (mặc định 30 giây). `noPollThreshold` nên lớn hơn 1.0 để giảm cảnh báo giả vì race.

Ví dụ cấu hình minh họa:

~~~java
var props = factory.getContainerProperties();

props.setIdleEventInterval(60_000L);
props.setMonitorInterval(30);
props.setNoPollThreshold(3.0f);
~~~

Thay đổi monitor threshold phải dựa trên poll timeout và môi trường triển khai; không chọn số này chỉ vì muốn giảm số cảnh báo. Khi `poll()` kẹt thật, tăng ngưỡng sẽ làm phát hiện chậm hơn.

## 11. Consumer đang pause có thể trông giống idle

Khi người vận hành dùng:

~~~java
container.pause();
~~~

Spring Kafka container thường vẫn tiếp tục `poll()` để duy trì consumer group nhưng không giao records từ các partitions paused. Do đó, container có thể đạt điều kiện **không nhận dữ liệu** và phát idle event.

`ListenerContainerIdleEvent.isPaused()` giúp biết trạng thái pause tại thời điểm event.

Ví dụ:

~~~java
@EventListener
public void handleIdle(ListenerContainerIdleEvent event) {
    if (event.isPaused()) {
        log.debug(
            "Idle expected while paused: listener={} idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
        return;
    }

    log.warn(
        "Unpaused consumer has no incoming records: listener={} idleMs={}",
        event.getListenerId(),
        event.getIdleTime()
    );
}
~~~

Ngay cả khi consumer không paused, idle vẫn có thể là bình thường nếu topic ít traffic hoặc backlog đã bằng 0. `isPaused()` chỉ giúp tránh nhầm một nguyên nhân, không tự phân loại event là lỗi.

Đừng dùng idle event làm lý do tự gọi `resume()` mọi container đang paused; pause có thể do maintenance, circuit breaker hoặc backpressure chủ động.

## 12. Idle không phải là consumer lag

Một consumer idle có thể ở nhiều trạng thái:

| Tình huống | Có thể thấy idle? | Consumer lag |
|---|---|---|
| Topic không có records mới, consumer đã bắt kịp | Có | Thấp hoặc 0 |
| Consumer bị pause có chủ đích | Có thể | Tăng nếu producer tiếp tục gửi |
| Consumer không có partition assignment | Có thể thiếu data | Tùy phân vùng/group |
| Chỉ một partition không có traffic | Global idle có thể không phát | Partition khác vẫn tiến |
| Consumer đang stuck trong poll | Idle event có thể không phát | Có thể tăng |
| Record lỗi bị retry blocking | Phụ thuộc error handler/poll flow | Có thể tăng |
| Producer upstream mất khả năng gửi | Có thể | Thấp dù business flow bị gián đoạn |

**Idle event không phải phép đo backlog.** Để biết consumer có chậm không, phải xem committed offsets và log-end offsets theo partition hoặc các metrics tương đương.

Ví dụ topic xử lý xong toàn bộ 100.000 records rồi ngừng phát: consumer sẽ idle, nhưng đó là trạng thái hoàn toàn khỏe. Ngược lại, topic có record liên tục nhưng consumer đang stuck tại một poison record, có thể có lag cao và không phát idle event như kỳ vọng.

## 13. Điều kiện không có dữ liệu và bài toán business heartbeat

Một dịch vụ nhận event đơn hàng có thể mong đợi ít nhất một event mỗi phút trong giờ cao điểm. Tuy nhiên, traffic tự nhiên có thể biến động theo ngày/giờ. Dựa vào `idleEventInterval = 60s` để page operator mọi khi không có order là không hợp lý.

Nếu nghiệp vụ thật sự yêu cầu một tín hiệu liên tục, có thể thiết kế một **heartbeat event** riêng hoặc giám sát upstream producer throughput. Khi đó:

- Heartbeat nên có contract và topic phù hợp.
- Không nhầm heartbeat với business transaction.
- Consumer có thể xác nhận đã nhận heartbeat nhưng không chứng minh database write cho order đã thành công.
- Consumer group chỉ đọc committed records theo cấu hình transaction/isolation.
- DLT và retry không nên tự tạo heartbeat giả để che outage.

`idleEventInterval` phục vụ quan sát **không nhận message**, còn business SLO cần nhiều tín hiệu hơn: producer liveness, pipeline backlog, success rate và end-to-end latency.

## 14. Ảnh hưởng của pollTimeout tới thời điểm phát

`idleEventInterval` không được thực thi bằng một scheduled timer độc lập chính xác theo millisecond. Logic kiểm tra idle diễn ra khi consumer/container có cơ hội tiến qua vòng poll và xác định không có records.

Nếu `pollTimeout` lớn hoặc poll chậm, event có thể được phát **muộn hơn ngưỡng cấu hình**. Ví dụ:

~~~text
idleEventInterval = 10 giây
pollTimeout = 5 giây

Có thể quan sát event sau khoảng 10-15 giây
tùy thời điểm poll trả về và thời gian xử lý nội bộ.
~~~

Đây chỉ là minh họa về độ chính xác, không phải công thức luôn đúng. `poll()` có thể trả sớm khi nhận dữ liệu, bị ảnh hưởng bởi assignment/rebalance và các hoạt động khác.

Không dùng idle event như một scheduler bảo đảm “chạy tác vụ đúng 12:00:10”. Nếu cần trigger chính xác hoặc xử lý timeout nghiệp vụ riêng, nên dùng scheduler/workflow chuyên trách.

## 15. Ảnh hưởng của concurrency

Một `ConcurrentMessageListenerContainer` tạo nhiều child consumers. Ví dụ `concurrency = 3`:

~~~text
orders-consumer
   |
   +-- child consumer 0 -> partitions 0,3
   +-- child consumer 1 -> partitions 1,4
   +-- child consumer 2 -> partitions 2,5
~~~

Mỗi child consumer có vòng poll và lịch nhận records riêng. Do đó, một child có thể idle trong khi child khác liên tục nhận records. Khi cấu hình `idleEventInterval` trên factory, events có thể được phát từ từng child container.

Các hệ quả vận hành:

- Một logical `@KafkaListener` có thể phát **nhiều idle events** từ nhiều child consumers.
- Không đếm số events toàn cluster như số lần topic ngừng hoạt động.
- `event.getSource(...)` thường là child container phát sự kiện.
- `event.getContainer(...)` có thể là parent `ConcurrentMessageListenerContainer`.
- Listener IDs của child có thể mang hậu tố; cần chuẩn hóa trước khi gắn metrics.
- Nếu concurrency lớn hơn số partitions, một số consumer có thể không được assign partition; việc không có records không nhất thiết là sự cố.

Nếu mục tiêu là đánh giá **cả application service không nhận dữ liệu**, cần tổng hợp theo tất cả consumers/instances có liên quan, không chỉ dựa vào một idle event của một child.

## 16. Event source, parent container và group visibility

`ListenerContainerIdleEvent` mang references:

~~~java
MessageListenerContainer source =
        event.getSource(MessageListenerContainer.class);

MessageListenerContainer parent =
        event.getContainer(MessageListenerContainer.class);
~~~

`source` giúp truy vết consumer cụ thể; `parent` giúp quy về listener container logic. Với consumer tạo từ `@KafkaListener`, `event.getListenerId()` trả về container ID tại thời điểm event.

Một ứng dụng triển khai 5 pods sẽ có 5 Spring application contexts khác nhau. Event được publish **trong JVM của pod đó**; nó không tự phát qua Kafka tới các pods khác.

Muốn có dashboard toàn consumer group:

1. Mỗi pod xuất metrics/logging của events cục bộ.
2. Hệ thống giám sát tổng hợp theo application, listener ID, group ID và instance.
3. Khi cần phân tích chính xác, truy vết source child container và partitions.
4. Không giả định nhận event trên pod A đồng nghĩa pod B hoặc cả group idle.

## 17. Xử lý event trên consumer thread

Theo mặc định, Spring application event multicaster thường gọi listeners **đồng bộ trên thread phát event**. Với `ListenerContainerIdleEvent`, đây thường là consumer thread.

Vì thế, event handler nên **nhanh và không blocking**.

Không nên:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    Thread.sleep(120_000L);
    externalApi.rebuildAllCaches();
}
~~~

Việc này có thể chặn consumer thread, gây poll delay và ảnh hưởng group lifecycle. Nó cũng làm `idleEventInterval` bị hiểu sai: khi handler đang blocking, consumer không có cơ hội tiếp tục poll để publish các idle events khác.

Nên làm:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    log.info(
        "Listener idle: id={} idleMs={} partitions={}",
        event.getListenerId(),
        event.getIdleTime(),
        event.getTopicPartitions()
    );

    metricsRecorder.recordIdle(event.getListenerId());
}
~~~

Nếu cần gửi alert tới dịch vụ bên ngoài, hãy dùng cơ chế bất đồng bộ, queue có giới hạn hoặc alerting pipeline. Không để lỗi gửi alert làm hỏng vòng poll consumer.

## 18. Thread safety khi đổi event multicaster sang async

`ListenerContainerIdleEvent` có thể chứa reference tới Kafka `Consumer` qua `getConsumer()`. Java KafkaConsumer **không thread-safe**.

Nếu event listener chạy đồng bộ trên consumer thread, một số thao tác với consumer reference có thể an toàn theo quy định framework. Nhưng nếu ứng dụng cấu hình Spring application event multicaster chạy bằng executor bất đồng bộ, listener có thể thực thi trên thread khác.

Khi đó:

- **Không** gọi `event.getConsumer().seek(...)`, `pause(...)` hoặc `resume(...)` từ async handler.
- Nếu cần thao tác lifecycle, dùng API của `MessageListenerContainer` hoặc registry ở thread phù hợp.
- Nếu cần seek theo thời điểm idle, xem `ConsumerSeekAware.onIdleContainer(...)` trong listener, được Spring Kafka thiết kế cho use case đó.
- Không giữ lâu KafkaConsumer reference trong cache hoặc gửi sang thread quản trị.
- Không tự gọi `consumer.poll()` từ event listener.

Đây là vấn đề thread ownership, không phải vấn đề event type có chứa reference hay không.

## 19. Không gọi container.stop() trực tiếp trên thread phát idle event

Một use case là “nếu consumer idle 10 phút, dừng listener”. Nhưng gọi `container.stop()` ngay trên consumer thread đang phát event có thể tạo chậm trễ hoặc log không cần thiết.

Hướng an toàn: **handoff yêu cầu stop sang thread điều khiển riêng**, và nếu event đến từ child container của một concurrent container, dừng **parent container** thay vì chỉ child.

Ví dụ phác thảo control service:

~~~java
@Component
public class IdleStopPolicy {

    private final KafkaListenerEndpointRegistry registry;
    private final Executor controlExecutor;

    public IdleStopPolicy(
            KafkaListenerEndpointRegistry registry,
            @Qualifier("kafkaControlExecutor") Executor controlExecutor) {
        this.registry = registry;
        this.controlExecutor = controlExecutor;
    }

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (event.getIdleTime() < 600_000L) {
            return;
        }

        MessageListenerContainer parent =
                event.getContainer(MessageListenerContainer.class);

        if (!"nightly-import-consumer".equals(parent.getListenerId())) {
            return;
        }

        controlExecutor.execute(() -> {
            MessageListenerContainer container =
                    registry.getListenerContainer("nightly-import-consumer");

            if (container != null && container.isRunning()) {
                container.stop();
            }
        });
    }
}
~~~

`kafkaControlExecutor` là bean executor do ứng dụng cấu hình với số thread/queue phù hợp; đoạn code chỉ minh họa cơ chế chuyển control action khỏi consumer thread. Trước khi dùng trong production cần cân nhắc policy, quyền vận hành, thread pool saturation và nhu cầu tự start trở lại.

**Không nên tự dừng một consumer production liên tục nhận event theo SLO chỉ vì nó idle ngắn hạn.** Dừng container có thể khiến partition được rebalance; pause có semantics khác với stop.

## 20. Khi nào dùng ConsumerSeekAware.onIdleContainer?

Đôi khi ứng dụng muốn quan sát các vị trí đã được consumer assign hoặc thực hiện seek có chủ đích khi container idle. Spring Kafka có `ConsumerSeekAware` hỗ trợ callback `onIdleContainer(...)` phục vụ use case này.

Ví dụ ý tưởng:

~~~java
@Component
public class IdleAwareListener implements ConsumerSeekAware {

    @Override
    public void onIdleContainer(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        log.debug("Consumer positions when idle: {}", assignments);
        // Nếu thật sự cần seek, dùng callback theo policy đã kiểm soát.
    }

    @KafkaListener(topics = "snapshot-events", groupId = "snapshot-reader")
    public void listen(String payload) {
        snapshotService.apply(payload);
    }
}
~~~

Chữ ký API có thể thay đổi theo phiên bản và cần imports phù hợp với `ConsumerSeekAware` và nested `ConsumerSeekCallback`. Ví dụ nhằm minh họa **vị trí hiện tại khi idle**, không khuyến nghị tự động seek về đầu topic mỗi khi không nhận record.

Tự seek trong idle callback có thể tạo replay khối lượng lớn, lặp DB side effect hoặc phá tiến độ consumer group. Nếu use case cần replay, hãy định nghĩa rõ điều kiện, idempotency, quyền vận hành và số record cần đọc lại.

## 21. Khi nào idle là bình thường?

Một số bối cảnh có idle event nhưng không có incident:

- Topic `daily-report-trigger` chỉ phát một lần/ngày.
- Topic `fraud-alert` ít dữ liệu khi hệ thống hoạt động tốt.
- Consumer đã bắt kịp và producer đang không có event mới.
- Môi trường staging/test gần như không có traffic.
- Consumer cố tình pause trong bảo trì hoặc backpressure.
- Listener đọc một partition ít traffic trong concurrent group.
- Producer đang shutdown có kế hoạch, không có nhu cầu gửi thêm.

Với các topic dạng này, dùng `idleEventInterval` để logging ở mức INFO/DEBUG hoặc đánh dấu trạng thái quan sát. Không gắn alert SEV1 chỉ vì event được phát.

Nếu topic có SLO “phải có event trong mỗi 5 phút”, cần mô tả rõ SLO, giờ hoạt động và nguồn dữ liệu được kỳ vọng; sau đó kết hợp idle event với producer health và kiểm tra business traffic.

## 22. Khi nào idle có thể là tín hiệu sự cố?

Một số trường hợp cần điều tra:

- Topic có producer đang gửi records nhưng consumer không nhận được dù lag tăng.
- Consumer pause do một control loop và không được resume.
- Consumer vừa rebalance và không còn assignment mong muốn.
- ACL/authorization hoặc metadata issue khiến consumer không đọc đúng topic.
- Listener bị cấu hình sai topic name/group id.
- Upstream producer ngừng phát ngoài kế hoạch.
- Downstream processing lỗi, consumer đang stuck trong retry/backoff; cần xem thêm các signals vì idle event có thể không được phát khi poll không quay về.
- Một partition business-critical ngừng nhận data trong khi những partitions khác vẫn tiếp tục.

Idle là tín hiệu để **khoanh vùng điều tra**, không phải bằng chứng root cause.

## 23. Quan sát idle cùng consumer lag và assignment

Một dashboard đáng tin nên có cả:

| Metric/event | Ý nghĩa |
|---|---|
| `ListenerContainerIdleEvent` count | Số lần container báo không nhận dữ liệu |
| `ListenerContainerNoLongerIdleEvent` count | Số lần consumer nhận dữ liệu trở lại |
| Last record received timestamp | Thời gian từ lần gần nhất nhận record |
| Consumer group lag | Backlog còn chờ |
| Partition assignment | Consumer đang sở hữu những partition nào |
| Pause requested/effective state | Không nhận dữ liệu do pause? |
| `NonResponsiveConsumerEvent` count | Consumer poll có thể đang bị block |
| Producer send success/error | Upstream có đang phát record? |
| Error handler retry/DLT | Có record lỗi/poison record? |
| Record processing success/latency | Business handler có hoạt động không |

Dùng labels có cardinality thấp: application, listener ID, topic, group và event type. Hạn chế dùng một metric series riêng cho event ID, offset, thread ID thay đổi liên tục.

Nếu muốn đo “đã không có record bao lâu”, `event.getIdleTime()` là metadata trực tiếp. Không cần tự tạo timer chính xác tuyệt đối nếu bài toán chỉ là cảnh báo mất traffic.

## 24. Giảm spam event và alert

Vì `ListenerContainerIdleEvent` được phát lặp lại trong lúc container idle, một listener có `idleEventInterval = 5_000L` có thể tạo nhiều logs/events khi topic thực sự trống.

Nếu có 50 child consumers idle trong một phút:

~~~text
interval = 5 giây
~12 idle events/consumer/phút
50 consumers x 12 = ~600 idle events/phút
~~~

Đây là ước lượng khi tất cả đã qua ngưỡng ban đầu, poll và scheduling cho phép kiểm tra đều đặn.

Các chiến lược:

- Chọn interval phù hợp với traffic pattern và SLO.
- Chỉ log transition sang idle ở WARN; các event lặp lại ở DEBUG hoặc aggregate.
- Dùng `ListenerContainerNoLongerIdleEvent` để đóng incident.
- Thêm cooldown/rate limit cho notification.
- Tổng hợp theo parent listener hoặc group nếu business chỉ cần một cảnh báo.
- Không gửi alert đến HTTP API đồng bộ ngay trên consumer thread.
- Bỏ qua hoặc phân loại riêng idle trong khoảng maintenance/pause.
- Dùng metric gauge “idle state” thay vì tạo ticket cho từng event.

Không cố loại bỏ mọi idle event vì chúng có thể giúp điều tra một đợt outage; mục tiêu là phân biệt telemetry và hành động vận hành.

## 25. Kết hợp với backpressure và pause

Một consumer bị pause do downstream quá tải sẽ không nhận record mới từ paused partitions. Nếu `idleEventInterval` được bật, tình trạng này có thể phát idle event.

Tuy nhiên, event không nhất thiết có nghĩa cần resume:

~~~text
Database overloaded
        |
        v
Backpressure monitor yêu cầu pause
        |
        v
Container không nhận record mới
        |
        v
ListenerContainerIdleEvent (paused=true)
        |
        v
Operator phải xem nguyên nhân pause trước khi quyết định resume
~~~

Nếu application có nhiều nguồn yêu cầu pause (manual maintenance, circuit breaker, rate limiter), cần một control plane thống nhất. Không cho idle observer độc lập gọi `resume()` mọi khi nhận idle event, vì có thể phá mục đích backpressure và tạo retry storm.

## 26. Manual ack, transaction và idle

`idleEventInterval` không thay đổi delivery guarantee.

Với `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE`, application vẫn phải ack record sau khi side effect quan trọng hoàn tất. Việc sau đó consumer idle không làm record chưa ack trở thành “đã xử lý”.

Với transactional listener container, output Kafka và input offset có thể được commit trong Kafka transaction. Idle event chỉ phản ánh việc không có record mới; nó không commit/abort transaction đang xử lý và không mở một Kafka transaction mới.

Một dòng thời gian:

~~~text
Record A received
    |
Business listener updates DB
    |
DB transaction commits
    |
Kafka offset commit may succeed/fail
    |
Consumer không nhận record mới
    |
Idle event xuất hiện khi đủ interval
~~~

**Idle không xác nhận DB write của record A an toàn hoặc Kafka offset đã commit**. Nếu record A được giao lại sau crash, consumer vẫn cần idempotency ở database.

## 27. Bài toán một consumer group có nhiều pods

Giả sử consumer group `order-projection` chạy ba pods:

~~~text
pod-A: partitions 0,1  -> có traffic liên tục
pod-B: partitions 2,3  -> idle
pod-C: partitions 4,5  -> có traffic liên tục
~~~

`pod-B` có thể publish idle events trong khi toàn group vẫn đang tiến triển bình thường. Một system-wide alert chỉ dựa vào một idle event sẽ gây hiểu nhầm.

Để đánh giá cả group:

1. Lấy consumer group membership và partition assignment.
2. So sánh ingress/lag theo từng partition.
3. Xác định event của pod nào, child container nào.
4. Tìm hotspot/imbalance do producer partition key.
5. Quan sát việc xử lý thực tế trên các pods còn lại.
6. Chỉ báo động nếu business SLO yêu cầu traffic ở partition đó.

Nếu `concurrency` lớn hơn số partitions, có thể tồn tại child consumer không có assignment. Không kỳ vọng mỗi child bắt buộc nhận record.

## 28. Test tình huống idle và active

Để hiểu hành vi của `idleEventInterval`, có thể thiết kế integration test trên Kafka broker phù hợp:

1. Tạo topic test, consumer group mới và listener factory có `idleEventInterval` nhỏ.
2. Điều chỉnh `idleBeforeDataMultiplier` để có ngưỡng startup phù hợp với thời gian test.
3. Đăng ký `@EventListener` thu `ListenerContainerIdleEvent`.
4. Không gửi record, chờ event xuất hiện sau threshold.
5. Dùng `event.getListenerId()` để xác nhận đúng listener.
6. Gửi một record hợp lệ và xác nhận `ListenerContainerNoLongerIdleEvent`.
7. Xác nhận listener thực tế nhận và xử lý record.
8. Pause container, quan sát `isPaused()` và phân biệt idle do pause.
9. Tạo tình huống một partition idle nhưng partition khác có traffic để kiểm tra `idlePartitionEventInterval`.
10. Dừng listener/container và dọn tài nguyên sau test.

Vì startup threshold có multiplier và event timing phụ thuộc poll, nên test dùng latch/await với khoảng timeout đủ rộng, **không assert chính xác event phải xuất hiện ở millisecond cố định**.

Đó là các tình huống gợi ý cho người học; không có thao tác chạy test application trong bước biên soạn bài này.

## 29. Runbook: không thấy idle event dù topic đã im lặng

Khi consumer dự kiến phát `ListenerContainerIdleEvent` nhưng không thấy:

1. **Kiểm tra cấu hình:** `idleEventInterval` có bị `null` hoặc áp dụng ở factory khác không?
2. **Kiểm tra listener startup:** container có `isRunning()` không?
3. **Kiểm tra event registration:** observer `@EventListener` có được Spring tạo bean không?
4. **Kiểm tra initial multiplier:** `idleBeforeDataMultiplier` có làm ngưỡng trước record đầu tiên dài hơn không?
5. **Kiểm tra consumer activity:** thật sự không có records? Có heartbeat/business record nào được gửi?
6. **Kiểm tra polling:** `poll()` có trả về không, hay xuất hiện `NonResponsiveConsumerEvent`?
7. **Kiểm tra concurrency:** event đến từ child container khác listener ID mà bộ lọc đang chờ?
8. **Kiểm tra application event multicaster:** event handler có lỗi hoặc bị lọc condition không?
9. **Kiểm tra poll timeout:** container có cơ hội kiểm tra idle interval chưa?
10. **Kiểm tra logs/metrics:** logging level, alert suppression hoặc rate limit có che event không?

Nếu `poll()` không thoát, idle event có thể không được tạo. Đây là lúc phải xem non-responsive monitor thay vì chỉ tăng idle interval.

## 30. Runbook: có idle event nhưng producer vẫn gửi liên tục

Đây là tình huống cần điều tra theo chứng cứ:

1. Xác định listener ID, parent/child container, instance và assigned partitions.
2. So sánh topic và group ID của consumer với topic producer thực sự gửi.
3. Kiểm tra Kafka consumer lag theo partitions.
4. Kiểm tra consumer đang paused hay không qua `event.isPaused()` và container state.
5. Xem group membership và rebalance logs.
6. Kiểm tra producer gửi vào đúng cluster/namespace/topic hay không.
7. Kiểm tra ACL/authentication và deserialization exceptions.
8. Nếu một partition hot còn partition khác idle, dùng partition-level metrics/events.
9. Kiểm tra một event handler blocking có làm poll loop chậm không.
10. Nếu muốn can thiệp offset/seek, xây quy trình riêng với audit; không seek tự động từ idle observer.

Với producer đã gửi tới Kafka nhưng consumer chưa poll, lag có thể tăng. Với producer gửi sai cluster, lag ở cluster đang quan sát có thể bằng 0 dù upstream “báo đã gửi”. Vì vậy cần đối chiếu địa chỉ bootstrap, topic và metadata của cả hai phía.

## 31. Runbook: idle event tạo alert quá nhiều

1. Xác định event count theo listener/partition và traffic pattern.
2. Kiểm tra initial startup multiplier, concurrency và số pods.
3. Chuyển từ alert cho từng event sang **stateful alert** theo lần chuyển vào idle.
4. Dùng no-longer-idle event để clear trạng thái.
5. Bỏ qua idle do maintenance pause khi được phép.
6. Tăng interval nếu phù hợp SLO, không tăng chỉ để che outage.
7. Dùng metric aggregation theo listener/group thay vì per-child notifications.
8. Kiểm tra producer health trước khi page operator.
9. Đặt cooldown/notification window.
10. Định nghĩa ownership và action cụ thể cho người nhận alert.

Nếu một topic chỉ phát dữ liệu hàng ngày, không nên dùng ngưỡng idle 10 giây với severity cao. Idle là thuộc tính lưu lượng, không tự động là lỗi.

## 32. Những sai lầm thường gặp

### Nhầm idle với consumer không phản hồi

Idle nghĩa là không nhận records nhưng poll có thể vẫn hoạt động. Non-responsive nghĩa là poll không trả về đúng hạn. Dùng hai loại events khác nhau.

### Coi `idleEventInterval` là retry timeout

Thuộc tính này không retry, seek hay chuyển DLT. Error handler và backoff mới quyết định retry/recovery của record lỗi.

### Không tính `idleBeforeDataMultiplier`

Trước record đầu tiên, ngưỡng event có thể là nhiều lần base interval. Không thấy event sau một base interval chưa hẳn là lỗi.

### Một child idle thì kết luận cả topic idle

Với concurrency, mỗi child có partitions khác nhau. Cần aggregate theo group/partition.

### Tự stop container trong consumer thread

Có thể gây delay và log không cần thiết. Handoff sang thread điều khiển và dừng parent concurrent container đúng cách.

### Sử dụng KafkaConsumer từ event handler async

KafkaConsumer không thread-safe. Nếu multicaster được cấu hình async, không gọi methods của Consumer reference từ thread khác.

### Đưa alert synchronous I/O vào callback

Một HTTP request chậm có thể làm consumer thread trì hoãn vòng poll, tạo thêm sự cố.

### Dùng idle event làm readiness duy nhất

Idle có thể xảy ra khi topic rỗng; không đồng nghĩa consumer bị lỗi hay process không ready.

### Bỏ qua pause state và lag

Idle khi paused có thể là hành vi đúng chủ đích. Kết hợp `isPaused()`, lag và backpressure reason.

## 33. Checklist thiết kế idleEventInterval

- [ ] Chỉ bật `idleEventInterval` khi có use case quan sát rõ ràng.
- [ ] Chọn interval theo traffic pattern và SLO của từng listener/topic.
- [ ] Biết rằng cấu hình tính bằng milliseconds, mặc định `null`.
- [ ] Xem xét `idleBeforeDataMultiplier` trước record đầu tiên.
- [ ] Hiểu event phát khi `poll()` không có record, và có thể lặp lại khi idle tiếp diễn.
- [ ] Lắng nghe `ListenerContainerIdleEvent` qua `@EventListener` hoặc `ApplicationListener`.
- [ ] Lọc parent/child listener ID phù hợp concurrency.
- [ ] Có thể dùng `ListenerContainerNoLongerIdleEvent` để xác nhận có record trở lại.
- [ ] Khi cần theo dõi một partition, dùng `idlePartitionEventInterval` và event tương ứng.
- [ ] Phân biệt idle với `NonResponsiveConsumerEvent`.
- [ ] Không blocking consumer thread trong event handler.
- [ ] Không tự thao tác KafkaConsumer từ async event callback.
- [ ] Không stop child container trong consumer thread; dùng control thread/parent.
- [ ] Không coi idle là commit offset, business success hay readiness.
- [ ] Kết hợp với lag, assignment, paused state, producer throughput và error/DLT metrics.
- [ ] Dùng alert state/cooldown để tránh spam từ events lặp lại.
- [ ] Có runbook khi không phát event, khi có idle bất thường và khi alert quá nhiều.

## 34. Nguồn tham khảo

- [Spring Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka API — ListenerContainerIdleEvent](https://docs.spring.io/spring-kafka/docs/3.3.11/api/org/springframework/kafka/event/ListenerContainerIdleEvent.html)

**Kết luận:** `idleEventInterval` giúp Spring Kafka phát hiện và thông báo **listener container không nhận record mới** trong một khoảng thời gian được cấu hình. Nó rất hữu ích cho quan sát traffic, điều phối maintenance và phát hiện pipeline mất dữ liệu đầu vào, nhưng không phải bằng chứng consumer bị lỗi. Khi thiết kế vận hành, cần xét initial multiplier, concurrency, partition-level idle, pause state và consumer lag; đồng thời tách riêng `NonResponsiveConsumerEvent` cho tình huống `poll()` không quay về. Sử dụng events để bổ sung observability và quyết định có căn cứ, không để event handler tự tạo rủi ro cho consumer thread.
