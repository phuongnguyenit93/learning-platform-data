# Phát hiện container không có message

Trong Spring Kafka, một listener container có thể đang **RUNNING** nhưng không có record mới được giao tới **@KafkaListener** trong nhiều giây hoặc nhiều phút. Trạng thái này không nhất thiết là lỗi: topic có thể không có producer, partition đang trống, consumer đã xử lý hết backlog hoặc hệ thống cố ý pause để giảm tải. Tuy nhiên, tình trạng **không có message** cũng có thể che giấu một sự cố: consumer không được assign partition, nhầm topic hoặc consumer group, listener bị pause mà không resume, poll thread không còn tiến triển, hoặc ứng dụng không thể tiếp tục xử lý sau rebalance.

Spring Kafka cung cấp các **application events** để quan sát container idle, đặc biệt **ListenerContainerIdleEvent** khi không có record được giao trong khoảng thời gian cấu hình và **ListenerContainerNoLongerIdleEvent** khi có dữ liệu trở lại sau giai đoạn idle. Đối với trường hợp poll thread có vẻ không còn tiến triển, Spring Kafka có cơ chế giám sát riêng phát **NonResponsiveConsumerEvent**. Ba tín hiệu này giải quyết các câu hỏi khác nhau và không được đánh đồng.

Bài học thuộc chương **Idle và non-responsive** của module **Spring Kafka Reliability Operations**. Mục tiêu là phân biệt *topic không có dữ liệu*, *consumer idle bình thường*, *container chạy nhưng không thực sự xử lý được* và *consumer poll bị chặn*, sau đó thiết kế metrics, alert, runbook và cách phục hồi phù hợp mà không tạo restart loop hoặc duplicate side effect.

## 1. “Không có message” thực chất có nghĩa gì?

Một consumer có thể thiếu message ở nhiều tầng:

1. **Broker không có record mới:** topic không nhận dữ liệu; consumer poll bình thường nhưng liên tục trả kết quả rỗng.
2. **Partition của group đã bắt kịp:** Kafka vẫn có record trong topic nhưng group đã commit đến cuối log.
3. **Consumer không được assign partition:** ứng dụng có listener nhưng không có partition nào để đọc.
4. **Container được pause có chủ đích:** consumer có thể vẫn poll giữ membership nhưng không giao dữ liệu cho listener.
5. **Có dữ liệu nhưng không tới listener:** xảy ra vì lỗi deserialize, rebalance, xử lý/backoff, transaction isolation hoặc sai routing/configuration.
6. **Poll không tiến triển:** consumer thread kẹt trong poll hoặc một công việc khác làm nó không quay lại poll đúng hạn.
7. **Listener có nhận record nhưng xử lý không hoàn tất:** đối với ứng dụng, không có nghiệp vụ thành công dù Kafka consumer vẫn đang đọc message.

Vì vậy, **độ im lặng của listener** không phải một phép đo sức khỏe toàn diện.

| Câu hỏi | Tín hiệu phù hợp |
|---|---|
| Listener có nhận record gần đây không? | ListenerContainerIdleEvent, thời gian từ lần giao record cuối |
| Consumer có tiếp tục poll đúng hạn không? | NonResponsiveConsumerEvent, poll telemetry, consumer thread state |
| Topic/partition có dữ liệu chưa xử lý không? | Committed offset, log end offset, consumer lag |
| Container có đang chạy hay đã dừng không? | Listener container running state, lifecycle events |
| Consumer có được assign partition không? | Assignment/rebalance events, consumer group describe |
| Container/partition có paused không? | Pause requested/effective state, pause/resume events |
| Record được xử lý nghiệp vụ thành công không? | Listener success/failure metrics, processing latency, side-effect confirmation |

## 2. Kafka poll rỗng có thể là hành vi hoàn toàn bình thường

Kafka consumer không nhất thiết nhận dữ liệu ở mỗi lần poll(). Khi partition chưa có record mới, consumer vẫn có thể gọi poll để giữ tiến độ group protocol, xử lý rebalance, và tiếp tục chờ dữ liệu.

~~~text
Kafka topic không có record mới
            |
            v
KafkaConsumer.poll()
            |
            +-- trả về 0 records
            |
            v
Container tiếp tục poll theo lifecycle
            |
            v
Listener chưa được gọi
            |
            v
Container vẫn RUNNING và healthy
~~~

Điều này thường xảy ra với topic chỉ có event theo yêu cầu, chẳng hạn OrderCancelled, AdminCommand hoặc một luồng reconciliation theo ngày. Nếu hệ thống dự kiến không có dữ liệu trong nhiều giờ, một idle event là thông tin vận hành, không phải cảnh báo nghiêm trọng.

Ngược lại, nếu một topic nhận hàng nghìn record mỗi phút và listener đột ngột không nhận message, cần kiểm tra assignment, paused state, lag và consumer thread.

## 3. Phân biệt idle, paused, stopped và non-responsive

| Trạng thái | Container đang chạy? | Poll có thể tiếp tục? | Listener nhận message? | Có nghĩa lỗi? |
|---|---|---|---|---|
| Idle, topic không có record | Có | Có | Chưa có record mới | Không nhất thiết |
| Idle, group đã bắt kịp | Có | Có | Chưa có record để giao | Không nhất thiết |
| Paused | Thường có | Có thể tiếp tục để giữ membership | Không giao record của partition paused | Có thể là backpressure có chủ đích |
| Stopped | Không | Không | Không | Tùy lý do dừng |
| Non-responsive poll | Có thể vẫn báo running | Có dấu hiệu không poll được như dự kiến | Có thể không nhận record | Cần điều tra |
| Listener đang xử lý record lâu | Có | Có thể chưa quay lại poll | Method hiện tại chưa xong | Phụ thuộc latency/SLO |
| Không được assign partition | Container có thể running | Có | Không có partition để giao | Tùy cấu hình/group |

**Running=true chỉ nói container đang ở một trạng thái lifecycle.** Nó không chứng minh có records được giao, không chứng minh thread không bị block và không chứng minh business side effect đã hoàn tất.

## 4. ListenerContainerIdleEvent

Spring Kafka có thể phát **ListenerContainerIdleEvent** khi listener container không được giao record trong thời gian được cấu hình qua **idleEventInterval**.

Các thuộc tính khái quát:

- Idle được đo trên cơ sở thời gian kể từ lần nhận/giao dữ liệu gần nhất theo implementation container, không phải khoảng thời gian kể từ lần commit offset thành công.
- Event có thể được phát lặp lại khi container tiếp tục idle; một event không đồng nghĩa một “phiên idle” vừa bắt đầu.
- Nếu không cấu hình idleEventInterval, đừng giả định ứng dụng tự có các event idle ở ngưỡng mong muốn.
- Khi dữ liệu quay lại sau trạng thái idle, framework có thể phát **ListenerContainerNoLongerIdleEvent**.
- Các event cấp container và cấp partition không hoàn toàn tương đương.

Sơ đồ:

~~~text
Ứng dụng khởi động
        |
        v
Container poll
        |
        +-- Có records --> giao listener --> reset chu kỳ idle theo container
        |
        +-- Không có records
                 |
                 v
          Thời gian không có dữ liệu
                 |
          >= idleEventInterval
                 |
                 v
          ListenerContainerIdleEvent
                 |
                 +-- Vẫn không có dữ liệu
                 |       |
                 |       v
                 |   Có thể phát thêm idle event
                 |
                 +-- Có dữ liệu trở lại
                         |
                         v
                 ListenerContainerNoLongerIdleEvent
~~~

Tần suất event thực tế phụ thuộc poll cycle, cấu hình và phiên bản Spring Kafka. Không nên xây logic đòi hỏi một event phải xuất hiện đúng tại một mili giây cụ thể.

## 5. Cấu hình idleEventInterval

Với @KafkaListener và listener container factory, có thể cấu hình thời gian nhận diện idle ở **ContainerProperties**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    // 30.000 ms không có message theo semantics của container.
    factory.getContainerProperties().setIdleEventInterval(30_000L);

    return factory;
}
~~~

Listener sử dụng factory:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    groupId = "orders-worker",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Với ví dụ này, nếu container liên tục không được giao record đủ lâu, Spring Kafka có thể phát idle event để ứng dụng quan sát. Giá trị **30 giây** chỉ là ví dụ, không phải khuyến nghị chung.

Chọn interval dựa trên đặc tính topic:

- Topic liên tục có dữ liệu: vài chục giây có thể giúp phát hiện bất thường sớm.
- Topic lưu lượng thấp: một interval quá ngắn sẽ tạo nhiều idle events bình thường.
- Topic theo lịch: tính theo khoảng giữa hai batch dự kiến.
- Topic command hiếm: nên kết hợp SLA của producer hoặc synthetic heartbeat thay vì coi mọi khoảng trống là sự cố.

Đừng cấu hình interval vài mili giây để “càng nhạy càng tốt”; listener container có thể tạo nhiều event và log ồn mà không làm phát hiện lỗi đáng tin cậy hơn.

### 5.1. Idle trước khi từng nhận dữ liệu

Một số phiên bản Spring Kafka hỗ trợ các thuộc tính ảnh hưởng thời điểm báo idle lần đầu, ví dụ cơ chế multiplier cho khoảng chờ trước khi từng nhận dữ liệu. Hành vi sau startup có thể khác hành vi idle sau khi đã nhận record.

Khi thiết kế alert, hãy phân biệt:

- **Startup idle:** listener vừa khởi động, chưa từng thấy record.
- **Operational idle:** listener đã xử lý dữ liệu rồi mới im lặng.
- **Expected quiet period:** topic chỉ nhận event ở khung giờ hoặc theo yêu cầu.

Không kết luận producer hỏng chỉ vì listener mới khởi động và chưa có record đầu tiên. Cần kiểm tra assignment, producer lịch phát dữ liệu và cấu hình initial idle của phiên bản thư viện.

## 6. Lắng nghe idle event trong Spring

Có thể dùng Spring **@EventListener** để nhận application events.

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaIdleEventLogger {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
            "Kafka listener idle: listener={}, idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }
}
~~~

**getIdleTime()** biểu thị thời gian idle theo event của framework, thường tính bằng mili giây. Nó không nên được diễn giải thành “thời gian từ lần nghiệp vụ commit thành công gần nhất”.

Một ứng dụng có thể có nhiều Kafka listeners. Event listener cần lọc theo listener ID, consumer group, source container hoặc metadata phù hợp trước khi áp dụng policy cho một topic cụ thể.

Ví dụ:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    if (!event.getListenerId().startsWith("orders-listener")) {
        return;
    }

    idleMetrics.recordIdleObservation(
        "orders-listener",
        event.getIdleTime()
    );
}
~~~

Với concurrent containers, listener ID trong event có thể thể hiện child container identity theo cách Spring Kafka tổ chức; do đó ví dụ lọc bằng prefix chỉ là một policy ứng dụng. Trong production, xác định rõ naming/identity theo phiên bản và cách tạo container.

## 7. ListenerContainerNoLongerIdleEvent

Khi một listener đã idle rồi bắt đầu nhận dữ liệu trở lại, **ListenerContainerNoLongerIdleEvent** giúp nhận diện điểm phục hồi:

~~~java
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;

@EventListener
public void onActiveAgain(ListenerContainerNoLongerIdleEvent event) {
    log.info(
        "Kafka listener received data after idle: listener={}",
        event.getListenerId()
    );
}
~~~

Event này có thể dùng để:

- Kết thúc một incident “không có message” nếu các điều kiện khác cũng đã phục hồi.
- Đo thời gian giữa lần phát hiện idle và lúc nhận message trở lại.
- Quan sát sự thay đổi nhịp dữ liệu sau rollout hoặc producer outage.
- Xác nhận một listener đã nhận dữ liệu sau thời gian startup.

Tuy nhiên, **NoLongerIdleEvent không chứng minh listener đã hoàn tất xử lý nghiệp vụ**. Record có thể vừa được giao và service gọi từ listener vẫn thất bại. Nên kết hợp listener success counter hoặc processed-event metric nếu yêu cầu đo business progress.

### 7.1. Idle events có thể lặp lại

Giả sử listener không nhận record trong 5 phút và idleEventInterval là 30 giây. Framework có thể phát nhiều ListenerContainerIdleEvent trong cùng khoảng im lặng.

Không nên tạo một ticket mới cho mỗi idle event. Hãy dùng một state machine:

~~~text
ACTIVE
   |
   | idle event đầu tiên của phiên idle
   v
IDLE_OPEN
   |
   +-- idle event tiếp theo -> cập nhật idle age/metric
   |
   +-- no-longer-idle -> đóng phiên idle
   |
   +-- container stop/rebalance -> đóng/đổi trạng thái theo lifecycle
~~~

Một incident cần được nhận diện theo listener/consumer/assignment và trạng thái, thay vì theo mỗi event callback.

## 8. Theo dõi idle ở từng partition

Một consumer có thể sở hữu nhiều partitions, nhưng chỉ một partition có dữ liệu mới. Container có thể nhận record liên tục nên **container-level idle không phát hiện được một partition im lặng bất thường**.

Ví dụ:

~~~text
orders.events:

partition 0 -> 100 records/s  -> ACTIVE
partition 1 ->   0 records/s  -> IDLE
partition 2 ->  30 records/s  -> ACTIVE

Container tổng thể nhận record liên tục
        |
        v
ListenerContainerIdleEvent có thể không phản ánh riêng P1
~~~

Spring Kafka có hỗ trợ event idle theo partition ở các phiên bản phù hợp, gồm **ListenerContainerPartitionIdleEvent** và **ListenerContainerPartitionNoLongerIdleEvent**. Có thể cấu hình khoảng kiểm tra tương ứng qua **idlePartitionEventInterval** ở container properties khi API hiện diện.

Ví dụ:

~~~java
factory.getContainerProperties()
       .setIdlePartitionEventInterval(60_000L);
~~~

Điểm cần chú ý:

- Partition không có dữ liệu có thể hoàn toàn bình thường với key ít hoạt động.
- Partition mới được assign có thể chưa từng nhận record.
- Khi rebalance, định danh owner và thời gian bắt đầu theo dõi thay đổi.
- Listener-level idle age không đồng nghĩa với maximum partition idle age.
- Nếu có hàng nghìn partitions, per-partition metrics cần được quản lý cardinality và vòng đời.

Với topic lưu lượng cao, partition-level idle có thể hữu ích để phát hiện producer partitioner sai, một shard business không gửi event, hoặc mất cân bằng traffic.

## 9. Idle không đồng nghĩa consumer non-responsive

Một nguồn nhầm lẫn phổ biến là xem container idle event và non-responsive consumer event như cùng một cảnh báo.

**ListenerContainerIdleEvent** có nghĩa không có record giao tới listener trong thời gian quan sát. Poll có thể vẫn chạy bình thường.

**NonResponsiveConsumerEvent** được dùng khi bộ giám sát của Spring Kafka phát hiện consumer không hoàn thành poll/không tiến triển qua poll theo ngưỡng được cấu hình. Đây là chỉ báo đáng điều tra về thread hoặc network, không phải bằng chứng tự động rằng broker hỏng.

~~~text
Trường hợp A: topic rỗng
  poll() -> 0 records
  poll() -> 0 records
  poll() -> 0 records
  => idle, nhưng poll vẫn responsive

Trường hợp B: consumer poll thread bị chặn
  poll() bắt đầu
       |
       +-- Không trở lại trong thời gian dự kiến
       |
       v
  Monitor phát hiện non-responsive
~~~

Vì thế:

- Idle event thường có severity **INFO/WARNING theo nghiệp vụ**.
- Non-responsive event có thể có severity **WARNING/CRITICAL theo thời gian không poll**.
- Cả hai cần được đối chiếu với state, lag, assignment, pause và broker health.

## 10. Cấu hình NonResponsiveConsumerEvent

Spring Kafka có cơ chế monitor định kỳ kiểm tra poll. Các thuộc tính liên quan thường gồm:

- **pollTimeout:** thời gian chờ tối đa của một poll call do container thiết lập.
- **noPollThreshold:** hệ số ngưỡng so với pollTimeout để xác định thời gian không có poll progress đáng nghi.
- **monitorInterval:** chu kỳ tác vụ monitor kiểm tra điều kiện.

Ví dụ:

~~~java
var props = factory.getContainerProperties();

// Poll timeout: 3 giây.
props.setPollTimeout(3_000L);

// Ngưỡng khái niệm: thời gian từ last poll
// vượt 3 lần poll timeout có thể bị cảnh báo.
props.setNoPollThreshold(3.0f);

// Monitor kiểm tra mỗi 10 giây.
props.setMonitorInterval(10);
~~~

Ví dụ trên minh họa các API thuộc những phiên bản Spring Kafka hỗ trợ. Giá trị 3.0, 10 giây không phải mặc định hoặc công thức SLA bắt buộc; kiểm tra chính xác các kiểu tham số và điều kiện từ Javadoc của phiên bản đang triển khai.

Thời gian phát event thực tế phụ thuộc **chu kỳ monitor** và trạng thái thread. Nếu threshold tương đương 9 giây nhưng monitor chạy 10 giây/lần, event có thể xuất hiện trễ hơn mốc 9 giây; đừng lấy timer monitor làm đồng hồ thời gian thực.

### 10.1. Lắng nghe NonResponsiveConsumerEvent

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;

@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    log.warn(
        "Kafka consumer may be non-responsive: listener={}, msSincePoll={}",
        event.getListenerId(),
        event.getTimeSinceLastPoll()
    );

    // Chỉ ghi nhận metric / yêu cầu điều tra.
    // Không restart listener vô điều kiện tại đây.
}
~~~

Không nên tự động stop rồi start container ngay mỗi khi nhận event. Nếu nguyên nhân là network outage, broker failover hoặc một thread đang mắc deadlock, restart lặp có thể gây rebalance storm, duplicate và khiến nguyên nhân khó điều tra hơn.

## 11. Tại sao một consumer có thể non-responsive?

Những nhóm nguyên nhân thường gặp:

| Nguyên nhân | Dấu hiệu | Hành động điều tra |
|---|---|---|
| Consumer poll block/network chậm | Non-responsive event, network timeout, broker errors | Kiểm tra broker/connection/client logs |
| Listener xử lý quá lâu | Processing latency tăng, poll không quay lại | Đo listener, HTTP/DB timeout, batch size |
| GC stop-the-world | JVM pause lớn, timer monitor cũng có thể trễ | Xem GC logs, heap, CPU |
| Thread starvation | Consumer thread không được scheduling phù hợp | Thread dump, CPU throttling, executor contention |
| Synchronized lock/deadlock | Thread bị BLOCKED/WAITING lâu | Thread dump, lock graph |
| Retry blocking kéo dài | Error handler backoff và retry attempts tăng | Kiểm tra BackOff, listener exceptions |
| Lifecycle shutdown/rebalance | Container đang stopping, assignments thay đổi | Kiểm tra lifecycle/rebalance events |
| Consumer API bị gọi sai thread | IllegalStateException/concurrent access | Dùng container APIs thay vì KafkaConsumer trực tiếp |

Một event non-responsive là **triệu chứng**. Nó không cho biết root cause và không có nghĩa mọi partition trong group đều mất dữ liệu.

## 12. Cấu hình idle và non-responsive trong cùng factory

Một factory minh họa:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    var props = factory.getContainerProperties();

    // Nhận diện container không có message.
    props.setIdleEventInterval(30_000L);

    // Nhận diện từng partition không có message.
    props.setIdlePartitionEventInterval(60_000L);

    // Quan sát khả năng tiếp tục poll.
    props.setPollTimeout(3_000L);
    props.setNoPollThreshold(3.0f);
    props.setMonitorInterval(10);

    return factory;
}
~~~

Chính sách cảnh báo tách biệt:

- Idle container 30 giây: ghi metric và đánh giá expected traffic.
- Partition idle 60 giây: kiểm tra producer traffic tại partition đó.
- Non-responsive vượt monitor threshold: điều tra poll/consumer thread và connectivity.

Đừng đặt cả ba cùng một severity hoặc cho cùng một automation tự restart container. Chúng có bản chất khác nhau.

## 13. Event listeners nên làm công việc nhẹ

Spring application events trong Kafka listener container có thể được phát từ thread liên quan consumer/container theo cơ chế mặc định. Nếu @EventListener thực hiện thao tác blocking dài, chính logic quan sát có thể làm chậm consumer.

Tránh:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    // Không nên gọi HTTP monitoring endpoint đồng bộ
    // rồi chờ nhiều giây ngay trong event callback.
    incidentApi.createTicketSynchronously(event);
}
~~~

Thay vào đó:

1. Cập nhật gauge/counter in-memory nhanh.
2. Ghi log có rate limit.
3. Nếu cần tạo ticket, gửi sự kiện đã làm sạch vào queue có bounded capacity.
4. Một worker riêng gọi hệ thống alerting với timeout/retry.
5. Nếu queue đầy, tăng metric dropped notifications; không giữ poll thread vô hạn.

Nếu ứng dụng cấu hình **asynchronous ApplicationEventMulticaster**, event callbacks có thể chạy trên thread khác. Khi đó **không sử dụng Consumer object từ event để gọi KafkaConsumer APIs từ thread lạ**; KafkaConsumer không hỗ trợ concurrent access chung. Container operations phải đi qua API quản lý lifecycle an toàn.

## 14. Xây tracker cho thời điểm nhận message cuối

Idle event hữu ích để phát hiện ngưỡng, nhưng nhiều hệ thống còn muốn dashboard có **seconds since last message**. Có thể instrument listener để ghi thời điểm nhận record và thời điểm xử lý thành công riêng.

Ví dụ:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class MessageProgressTracker {

    private final AtomicLong lastDeliveredNanos =
        new AtomicLong(0L);

    private final AtomicLong lastSucceededNanos =
        new AtomicLong(0L);

    public void onDelivered() {
        lastDeliveredNanos.set(System.nanoTime());
    }

    public void onSucceeded() {
        lastSucceededNanos.set(System.nanoTime());
    }

    public double secondsSinceLastDelivered() {
        return elapsedSeconds(lastDeliveredNanos.get());
    }

    public double secondsSinceLastSucceeded() {
        return elapsedSeconds(lastSucceededNanos.get());
    }

    private double elapsedSeconds(long mark) {
        if (mark == 0L) {
            return -1.0; // Chưa từng quan sát event.
        }
        long elapsed = System.nanoTime() - mark;
        return Math.max(0L, elapsed) / 1_000_000_000.0;
    }
}
~~~

**System.nanoTime()** thích hợp để đo elapsed duration trong cùng JVM. Không lưu nanoTime qua restart; nếu cần audit timestamp xuyên các instances, lưu thêm Instant.now() hoặc Clock ở UTC.

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderEvent event) {
    progressTracker.onDelivered();

    orderService.process(event);

    progressTracker.onSucceeded();
}
~~~

Hai metric phải tách riêng:

- **lastDelivered:** lần gần nhất listener bắt đầu nhận record.
- **lastSucceeded:** lần gần nhất business logic hoàn thành không ném exception.

Nếu listener nhận 100 record/s nhưng tất cả đều fail, lastDelivered age nhỏ trong khi lastSucceeded age tăng. Chỉ nhìn idle event sẽ không phát hiện đầy đủ sự cố nghiệp vụ này.

### 14.1. Tracker in-memory có giới hạn

Một tracker ở cấp bean thường tổng hợp tất cả partitions mà listener instance xử lý. Khi rebalance, nó không tự biết instance đã mất partition nào; sau restart nó chưa có dữ liệu.

Nếu cần phát hiện một shard im lặng:

- Duy trì state theo TopicPartition với assignment epoch.
- Xóa/đóng state khi revoke/lost.
- Có clock/timestamp riêng cho từng partition.
- Không coi partition chưa từng có message là bằng chứng producer thất bại nếu traffic theo key rất thưa.

## 15. Micrometer gauge cho khoảng im lặng

Với Spring Boot tích hợp Micrometer, có thể xuất custom metrics:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public void registerProgressMetrics(
        MeterRegistry registry,
        MessageProgressTracker tracker) {

    Gauge.builder(
        "app.kafka.listener.since.last.delivered.seconds",
        tracker,
        MessageProgressTracker::secondsSinceLastDelivered
    )
    .tag("listener_id", "orders-listener")
    .register(registry);

    Gauge.builder(
        "app.kafka.listener.since.last.success.seconds",
        tracker,
        MessageProgressTracker::secondsSinceLastSucceeded
    )
    .tag("listener_id", "orders-listener")
    .register(registry);
}
~~~

Các metric names là **custom conventions**; không phải built-in metrics có sẵn ở mọi Spring Kafka version. Nếu tracker chưa từng thấy record, ví dụ dùng -1 thay vì báo một duration giả rất lớn; dashboard nên hiển thị **NEVER_SEEN** riêng.

Một gauge không phải công cụ xác minh message đã được commit offset. Cần bổ sung error handler, offset commit và end-to-end processing metrics.

## 16. Đo thời gian idle liên tục bằng state machine

Do idle event có thể lặp trong cùng một giai đoạn im lặng, muốn đo **độ dài một phiên idle** cần theo dõi transition thay vì đếm event callback.

~~~text
UNKNOWN / STARTUP
       |
       | nhận message
       v
ACTIVE
       |
       | vượt ngưỡng idle
       v
IDLE(startAt, reason=NO_MESSAGES)
       |
       +-- idle event tiếp theo:
       |      cập nhật currentIdleSeconds
       |
       +-- no-longer-idle event:
       |      completedIdleDuration
       |      trở về ACTIVE
       |
       +-- stop/revoke:
              đóng state với endReason riêng
~~~

Chú ý: nếu chỉ bắt đầu timer khi nhận **idle event đầu tiên**, bạn đang đo “thời gian kể từ lúc framework phát hiện idle”, **không phải** toàn bộ thời gian từ record cuối. Để báo cáo true silence age, cần dùng thời điểm last record/last delivery hoặc idleTime do event cung cấp để suy ra đúng ý nghĩa.

Ví dụ:

~~~text
Last record received: t=00
idleEventInterval: 30s
First idle event: t≈30
Second idle event: t≈60
Record resumed: t=90

Silence duration ≈ 90s
Time since first idle alert ≈ 60s
~~~

Hai đại lượng đều hữu ích nhưng phục vụ mục tiêu khác nhau. Khi thiết kế SLO hoặc cảnh báo, ghi rõ định nghĩa.

## 17. Container idle so với partition idle

Nếu container concurrency=3, có thể có ba consumer threads:

~~~text
orders-listener
    |
    +-- child-0 -> P0, P3 -> P0 nhận record
    |
    +-- child-1 -> P1, P4 -> không nhận record
    |
    +-- child-2 -> P2, P5 -> P5 nhận record
~~~

Một event idle từ child-1 không có nghĩa tất cả listener instances của consumer group đều idle. Ngược lại, tổng throughput toàn group cao vẫn có thể che một partition không có message quá lâu.

Các lớp metrics có thể cần:

- **Container-level:** child consumer nào idle bao lâu.
- **Listener-level:** có ít nhất một consumer đang nhận record hay không.
- **Partition-level:** mỗi partition đã không có record bao lâu.
- **Group-level:** tổng tiến độ và lag trên tất cả partitions.
- **Business-level:** time since last successful event cho một flow hoặc event type.

Không trộn các lớp rồi đặt một metric tên “Kafka idle duration” mà không chỉ rõ aggregation.

## 18. Khi không được assign partition

Một @KafkaListener có thể được khởi tạo thành công nhưng chưa sở hữu partition:

- Consumer group có nhiều members hơn số partitions.
- Assignor chưa hoàn tất rebalance.
- Pattern subscription không match topic mong muốn.
- Topic chưa được tạo hoặc metadata chưa sẵn sàng.
- Container đã dừng, bị cấu hình autoStartup=false hoặc listener ID khác đang được quan sát.

Ví dụ:

~~~text
Topic có 3 partitions
Consumer group có 5 active consumers

=> Có thể có 2 consumer không được assign partition
=> Các consumers đó không nhận message
=> Không nhất thiết là lỗi
~~~

Một container không có assignment không thể được đánh giá giống một container đang sở hữu 3 partitions có lag lớn. Cần thêm **assigned_partition_count** vào dashboard và điều kiện cảnh báo.

Trong lúc rebalance, tạm thiếu assignment có thể là trạng thái quá độ. Alert nên có grace window phù hợp thay vì tạo incident mỗi khi rollout.

## 19. Kiểm tra consumer lag và tiến độ

Để phân biệt idle bình thường và không có message bất thường, hãy so sánh committed offset với log end offset:

~~~text
Consumer group committed offset: 1200
Partition log end offset:       1200

lag = 0
=> không có backlog chưa commit theo cách đo offset đó
~~~

Trường hợp khác:

~~~text
Consumer group committed offset: 1200
Partition log end offset:       1250

lag = 50
=> còn dữ liệu chưa được group commit
~~~

Nếu listener idle lâu trong khi lag cao, cần điều tra. Tuy nhiên:

- Lag có thể phản ánh record đang xử lý nhưng chưa commit.
- Kafka transactions với read_committed có thể làm LSO giới hạn dữ liệu có thể đọc trước LEO.
- Topic retention và offset reset policy ảnh hưởng khả năng replay.
- Một partition paused có thể giữ lag tăng mặc dù consumer vẫn hoạt động.
- Lag ở group không chứng minh mọi member phải có message.

Do đó, **idle + lag + assignment + paused/running + poll responsiveness** là phép chẩn đoán mạnh hơn chỉ một chỉ số.

## 20. Kafka CLI không cho biết idle event của Spring

Kafka cung cấp công cụ mô tả consumer group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --group orders-worker \
  --describe
~~~

Ví dụ kết quả:

~~~text
TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders.events  0          1200            1200            0
orders.events  1           550             650          100
orders.events  2           920             920            0
~~~

CLI cho thấy trạng thái offset/lag và có thể cung cấp thông tin assignment theo phiên bản/tool output. Nó **không biết** listener Spring đã phát ListenerContainerIdleEvent hay chưa và không biết listener business operation có thành công không.

Để chẩn đoán, kết hợp:

- CLI group membership/offset.
- Spring listener/container events và trạng thái lifecycle.
- Producer publish rates/topic ingress.
- Listener success/failure metrics.
- JVM thread dump và Kafka client logs khi nghi poll non-responsive.

## 21. Paused container có thể trông như idle

Khi container được pause:

~~~text
Downstream quá tải
        |
        v
PauseService gọi container.pause()
        |
        v
Consumer có thể vẫn poll giữ membership
        |
        v
Listener không nhận records mới
        |
        v
Time since last message tiếp tục tăng
~~~

Điều đó không có nghĩa consumer bị lỗi. Nó có thể đúng chính sách backpressure. Nhưng nếu pause bị quên hoặc không resume sau khi downstream khỏe, hệ thống có thể ngừng xử lý lâu ngoài dự kiến.

Vì vậy, khi nhận idle event hãy kiểm tra:

1. **isPauseRequested()**: ứng dụng có yêu cầu pause không?
2. **isConsumerPaused()**: pause đã có hiệu lực chưa?
3. Có partition-specific pause không?
4. Ai yêu cầu pause, vì sao và lúc nào?
5. Điều kiện resume đã đạt chưa?

Không tự gọi resume() chỉ vì listener idle nếu pause là hành vi bảo vệ một dependency đang lỗi. Phải dựa trên trạng thái hệ thống và ownership của pause request.

## 22. Một record poison có thể khiến nghiệp vụ không tiến triển

Một listener có thể nhận record lỗi rồi retry nhiều lần. Trạng thái nhìn từ metrics phụ thuộc:

- Listener method có được gọi lại không?
- Error handler retry blocking hay non-blocking?
- Record bị deserialize lỗi trước khi tới listener không?
- Consumer có tiếp tục poll trong backoff không?
- Record đã được chuyển DLT/retry topic hay chưa?

Ví dụ:

~~~text
Topic P0 offset 150 là poison record
        |
        v
Listener/Deserializer lỗi
        |
        v
ErrorHandler retry liên tục
        |
        v
Không có business success
        |
        v
Offset không tiến / lag tăng
~~~

Một metric “time since last success” sẽ tăng, nhưng “time since last delivery” có thể liên tục reset vì record được giao lại. Không phải mọi trường hợp đều phát idle event.

Nếu một offset xuất hiện trong logs hàng trăm lần, hãy phân loại transient/permanent error, xem error handler/BackOff và kiểm tra DLT recovery thay vì xử lý như vấn đề “topic không có message”.

## 23. Không có message vì deserialization thất bại trước listener

Kafka deserializer được gọi trong Consumer.poll(), trước khi @KafkaListener nhận object. Nếu payload bị lỗi và deserializer ném exception, listener có thể không được gọi.

Trong Spring Kafka, **ErrorHandlingDeserializer** giúp chuyển thông tin lỗi deserialization vào headers để container/error handler có cơ hội xử lý record.

Nếu không cấu hình phù hợp, một poison pill có thể làm cùng offset thất bại lặp lại mà dashboard listener count không tăng. Hãy xem:

- Lỗi từ KafkaConsumer.poll() và deserializer.
- ErrorHandlingDeserializer cho key/value.
- DefaultErrorHandler classification.
- DeadLetterPublishingRecoverer và serializer có hỗ trợ raw bytes không.
- DLT publish failure, offset commit và record replay.

Không suy đoán rằng producer không gửi record chỉ vì @KafkaListener không được gọi. Cần xem log tại poll/deserialization boundary.

## 24. Không có message vì read_committed và open transaction

Kafka consumer có **isolation.level=read_committed** chỉ đọc records transactional đã commit và records không transactional theo protocol. Nếu một transaction đang mở ở partition, **Last Stable Offset (LSO)** có thể nằm phía sau Log End Offset (LEO).

Ví dụ:

~~~text
Topic partition log:
  offset 200: committed
  offset 201: transaction T đang mở
  offset 202: record khác ghi sau T

LEO tăng nhưng LSO vẫn ở ranh giới T chưa ổn định
        |
        v
read_committed consumer chưa thể đọc sau LSO
        |
        v
Listener có thể idle dù log end offset vẫn tăng
~~~

Khi transaction T commit hoặc abort, LSO có thể tiến lên. Nếu chỉ nhìn LEO - committed offset, bạn có thể báo sai “consumer không chịu poll” trong khi nó đang tuân thủ isolation semantics.

Hãy kiểm tra transaction timeout, producer commit/abort rate, broker coordinator health, isolation level và định nghĩa offset/lag của exporter.

## 25. Khi nào nên alert idle?

Không nên đặt một alert chung “không có message trong 30 giây” cho mọi topic.

Một cảnh báo nên tính tới:

- Topic có lịch phát dữ liệu hay không?
- Có SLA rằng ít nhất một event sẽ đến trong một khoảng?
- Producer ingress có thực sự lớn hơn 0?
- Consumer đang sở hữu partition không?
- Group còn lag không?
- Container có paused hoặc stopped theo yêu cầu không?
- Có deployment/rebalance đang diễn ra không?
- Có lỗi poll/deserialization/recovery không?
- Listener business success gần nhất cách đây bao lâu?

Ví dụ policy:

| Luồng | Kỳ vọng | Alert gợi ý |
|---|---|---|
| Payment events liên tục | Có dữ liệu mọi phút | Idle lâu + producer ingress > 0 + lag > 0 |
| Daily settlement | Một batch mỗi ngày | Không nhận batch sau deadline dự kiến |
| Rare admin command | Có thể im lặng nhiều ngày | Không alert chỉ vì idle; theo dõi container health riêng |
| Retry topic | Record chỉ đến khi có lỗi | Không alert idle; alert retry backlog/oldest age |
| DLT | Chỉ có record khi recovery | Không alert DLT idle; alert DLT publish failure và backlog |

**Idle event là một tín hiệu quan sát, không phải một SLO chung cho mọi consumer.**

## 26. Synthetic heartbeat và kiểm tra end-to-end

Với một pipeline yêu cầu chứng minh khả năng nhận message liên tục, có thể thiết kế một **heartbeat event** hoặc synthetic probe có ID riêng, được producer gửi định kỳ rồi consumer xử lý.

~~~text
Heartbeat producer
       |
       v
Kafka topic / partition
       |
       v
Spring Kafka consumer
       |
       v
Ghi nhận heartbeatId, sentAt, receivedAt, processedAt
       |
       v
Dashboard end-to-end latency và missing-heartbeat alert
~~~

Heartbeat cần được thiết kế cẩn thận:

- Không trộn với command nghiệp vụ nếu schema hoặc ordering không cho phép.
- Xác định heartbeat đi vào partition nào; một heartbeat trên một partition không chứng minh mọi partition đều khỏe.
- Ghi nhận sentAt/receivedAt/processedAt để tách producer delay và consumer delay.
- Không dùng timestamp từ các máy có clock skew lớn để đo elapsed duration chính xác mà không tính sai số.
- Heartbeat không thay thế monitoring Kafka broker, consumer group và business processing.

Một synthetic heartbeat là bổ sung hữu ích khi **sự im lặng bình thường** không phân biệt được với **producer đã chết**.

## 27. Theo dõi các loại thời gian im lặng

Một hệ thống reliability thường cần nhiều timestamp:

| Timestamp/duration | Định nghĩa | Công dụng |
|---|---|---|
| lastProducedAt | Lần gần nhất producer xác nhận event đã publish | Phát hiện producer ngừng ghi |
| lastFetchedAt | Lần gần nhất consumer poll nhận dữ liệu | Phát hiện thiếu input |
| lastDeliveredAt | Lần gần nhất listener được gọi | Phát hiện listener không nhận record |
| lastSucceededAt | Lần gần nhất nghiệp vụ xử lý xong | Phát hiện xử lý lỗi liên tục |
| lastCommittedAt | Lần gần nhất group tiến độ offset được ghi nhận | Phát hiện không commit |
| lastRebalanceAt | Lần gần nhất assignment thay đổi | Phân biệt khoảng lặng do rebalance |
| idleStartedAt | Thời điểm xác định container idle | Đo duration phiên idle |
| nonResponsiveDetectedAt | Thời điểm monitor phát hiện poll không tiến triển | Điều tra thread/poll |

Các timestamps có thể đến từ các nguồn đo khác nhau. Chỉ gắn chung một tên “last message time” sẽ khiến người trực vận hành hiểu sai.

Nếu cần đo **elapsed duration trong cùng JVM**, dùng System.nanoTime(). Nếu cần audit và tương quan qua các instances, lưu timestamps UTC và ghi nhận độ lệch clock có thể xảy ra.

## 28. Metrics và dashboard

Một dashboard cho chương Idle và non-responsive có thể gồm:

**Container state**

- Running/stopping/stopped.
- Assigned partition count.
- Pause requested/effective status.
- Last rebalance age.

**Traffic và processing**

- Records fetched/delivered per second.
- Listener success/failure rate.
- Seconds since last delivered message.
- Seconds since last successful processing.
- Lag và oldest record age theo partition.

**Idle behavior**

- Idle event count.
- Current idle age.
- Completed idle interval duration.
- No-longer-idle event count.
- Partition idle count và max partition idle age.

**Poll responsiveness**

- Non-responsive event count.
- Time since last poll theo metric/client phù hợp.
- Poll latency và request latency.
- max.poll.interval.ms violation, rebalance count.
- Thread/GC health và blocked time.

**Recovery**

- Retry attempts/exhausted.
- Deserialization failure.
- DLT publish success/failure.
- Container restarts và manual intervention.

Không nhất thiết Spring Kafka xuất sẵn toàn bộ các metrics này. Một số đến từ Kafka client metrics, Micrometer observations, broker/consumer group monitoring; các chỉ số như lastSucceededAt hoặc currentIdleAge thường cần application instrumentation.

## 29. Prometheus: ví dụ cảnh báo dựa trên nhiều điều kiện

Giả sử ứng dụng xuất custom metric:

- app_kafka_listener_since_last_delivered_seconds.
- app_kafka_listener_running.
- app_kafka_listener_paused.
- app_kafka_listener_assigned_partitions.
- kafka_consumergroup_lag của exporter phù hợp.

Một alert dạng ý tưởng:

~~~promql
(
  app_kafka_listener_since_last_delivered_seconds > 120
)
and on (listener_id)
(
  app_kafka_listener_running == 1
)
and on (listener_id)
(
  app_kafka_listener_paused == 0
)
~~~

Đây là **PromQL minh họa dựa trên metric custom**. Trong hệ thống thực tế, labels của exporter và semantics của metric phải được thiết kế để phép join hoạt động; có thể cần group labels, group-left hoặc recording rules phù hợp.

Một cảnh báo mạnh hơn nên bổ sung:

- Có producer traffic hoặc backlog lớn.
- Không đang trong startup/rebalance grace window.
- Consumer có assignment.
- Không có maintenance suppression.

Không gửi critical page chỉ từ một gauge idle age cho một topic có lưu lượng thưa.

## 30. Không đưa event payload hay ID vào metric labels

Với Prometheus/Micrometer, labels có cardinality cao gây tăng số lượng time series, ảnh hưởng hiệu năng và chi phí lưu trữ.

Labels phù hợp:

- service.
- listener_id.
- consumer_group.
- topic.
- exception_category.
- state.

Labels cần cân nhắc:

- partition (có thể nhiều, cần giới hạn).
- client_id/instance_id (phù hợp nếu cardinality được kiểm soát).

Không đưa:

- eventId.
- orderId.
- userId.
- raw exception message.
- toàn bộ Kafka key hoặc payload.

Event ID và offset nên nằm trong log/trace. Khi rebalance thay đổi assignment, cần xóa hoặc đóng metrics per-partition của owner cũ để tránh stale series làm dashboard báo một partition vẫn idle trên instance không còn sở hữu nó.

## 31. Vận hành qua @EventListener: tránh hành động quá mạnh

Một anti-pattern:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    MessageListenerContainer container =
        registry.getListenerContainer(event.getListenerId());

    // Không nên restart ngay vì chỉ có idle event.
    container.stop();
    container.start();
}
~~~

Vấn đề:

- Topic có thể đang rỗng; restart không tạo ra message.
- Stop/start gây thay đổi consumer group assignment.
- Nếu nhiều instances cùng nhận policy, có thể tạo rebalance storm.
- Pending offsets và in-flight work có thể bị ảnh hưởng.
- Lỗi gốc ở producer/Schema Registry/dependency vẫn chưa được xử lý.

Thay vào đó:

1. Ghi lại idle age.
2. Kiểm tra running, paused, assignment và lag.
3. Phân biệt idle bình thường với poll non-responsive.
4. Chỉ kích hoạt recovery tự động khi có bằng chứng cụ thể và giới hạn retry.
5. Cảnh báo người vận hành nếu điều kiện vượt SLO.

Nếu cần restart một container thực sự bị kẹt, nên dùng supervisor với state machine, rate limit, kiểm tra producer/transaction lifecycle và idempotency, không gọi stop/start đồng bộ bên trong listener event callback.

## 32. Runbook: listener không có message nhưng lag bằng 0

### Bước 1: Xác định có phải topic ít dữ liệu không

Xem lịch producer, publish rate, event volume theo giờ/ngày và SLA input. Một topic có thể hoàn toàn im lặng nhưng hệ thống vẫn khỏe.

### Bước 2: Kiểm tra subscription

- Listener có đăng ký đúng topic/topic pattern không?
- Group ID có đúng môi trường không?
- Topic đã tồn tại và có partitions như kỳ vọng không?
- Consumer có được assign partition không?

### Bước 3: Kiểm tra trạng thái

Container running hay stopped? Có paused vì backpressure không? Có assignment/rebalance mới gần đây không?

### Bước 4: Xác nhận producer

Tìm producer send success/error metrics, topic ingress rate và lỗi authorization/serializer. Nếu producer đã dừng, consumer chỉ đang phản ánh upstream silence.

### Bước 5: Đánh giá cảnh báo

Nếu không có SLA data arrival, giữ metric idle ở mức informational. Nếu có expected periodic heartbeat, kiểm tra tín hiệu heartbeat end-to-end và mở incident nếu quá deadline.

## 33. Runbook: listener idle nhưng lag lớn

Đây thường đáng điều tra hơn vì có dữ liệu chưa được group commit.

1. Xem lag theo từng partition; xác định partition nào ảnh hưởng.
2. Kiểm tra consumer assignment và group rebalance.
3. Kiểm tra isPauseRequested()/isConsumerPaused() và partition pause.
4. Xem poll responsiveness, non-responsive events và thread dump.
5. Xem listener processing latency, retry/backoff và errors.
6. Kiểm tra deserialization/poison record trước @KafkaListener.
7. Nếu isolation=read_committed, kiểm tra open transactions và LSO.
8. Kiểm tra Kafka ACL, broker/coordinator health và network errors.
9. Không reset offset hoặc force commit trước khi hiểu dữ liệu chưa xử lý.
10. Sau khắc phục, theo dõi record success, committed offset và lag giảm.

Nếu một partition bị paused có chủ đích, không ép resume khi downstream chưa khỏe chỉ để lag giảm. Cần cân bằng backpressure với retention và backlog budget.

## 34. Runbook: NonResponsiveConsumerEvent tăng

### Bước 1: Kiểm tra thread và JVM

Lấy thread dump trong môi trường cho phép. Tìm Kafka consumer thread đang BLOCKED/WAITING ở lock, HTTP/database call, producer send, poll hoặc retry handler.

### Bước 2: Kiểm tra timeout

- pollTimeout.
- noPollThreshold.
- monitorInterval.
- max.poll.interval.ms.
- HTTP connect/read timeout.
- Database statement/lock timeout.

Nếu monitor threshold nhỏ hơn latency hợp lệ thường gặp của poll hoặc tác vụ xử lý, có thể phát hiện quá nhạy. Không loại bỏ cảnh báo bằng cách tăng timeout vô hạn mà không đo thực tế.

### Bước 3: Kiểm tra Kafka infrastructure

Broker request latency, disconnects, authentication, coordinator changes, leader/ISR và network.

### Bước 4: Xác định có cần can thiệp không

Nếu consumer tự phục hồi và poll trở lại, ghi nhận duration/nguồn lỗi. Nếu thread thực sự kẹt, cân nhắc recovery có rate limit, chặn side effect duplicate bằng idempotency, và tránh restart toàn group cùng lúc.

### Bước 5: Xác minh hậu quả

Kiểm tra offset chưa commit, listener output, DLT/retry backlog và business side effects sau khi container phục hồi.

## 35. Runbook: container bị pause và bị quên

Không có message có thể là hậu quả của một pause từng được yêu cầu hợp lệ nhưng không có resume.

Kiểm tra:

- Pause reason, requester và timestamp.
- Downstream circuit breaker/queue hiện đã khỏe chưa.
- Low-watermark resume condition có đạt không.
- Một manual-maintenance reason còn active không.
- Container vẫn sở hữu partition đó hay rebalance đã xảy ra.
- Requested resume đã được áp dụng chưa.
- Retention và oldest record age đang ở ngưỡng nào.

Resume nên có điều phối và theo dõi throughput sau đó. Nếu backlog đã lớn, có thể cần giới hạn tốc độ hoặc tăng capacity phù hợp để không làm downstream quá tải khi record dồn trở lại.

## 36. Kiểm thử phát hiện container không có message

Một bộ integration tests nên có các tình huống:

### 36.1. Topic rỗng

Khởi động listener với một topic trống, chờ interval. Xác nhận ListenerContainerIdleEvent được phát theo policy, trong khi container vẫn running và không bị restart tự động.

### 36.2. Dữ liệu đến sau idle

Sau khi nhận idle event, publish một record hợp lệ. Xác nhận listener nhận dữ liệu và ListenerContainerNoLongerIdleEvent được quan sát nếu version/container hỗ trợ.

### 36.3. Idle event lặp

Để topic trống qua nhiều intervals. Xác nhận tracker không tạo nhiều incident/idle sessions cho cùng một khoảng im lặng.

### 36.4. Partition idle

Tạo topic nhiều partitions, chỉ publish tới một partition. Xác nhận partition-level idle instrumentation không báo sai toàn bộ container khi partition khác có traffic.

### 36.5. Paused container

Gọi pause(), để record mới được publish, kiểm tra pause state và lag. Không kỳ vọng listener nhận record trên paused partitions cho tới khi resume.

### 36.6. Consumer không được assignment

Chạy group có nhiều consumers hơn partitions. Kiểm tra consumer không được assign không bị kết luận faulty chỉ vì không có message.

### 36.7. Poll thread bị chặn

Trong môi trường test có kiểm soát, gây consumer poll không tiến triển hoặc một tác vụ kéo dài vượt threshold. Quan sát NonResponsiveConsumerEvent, đồng thời xác nhận không có restart loop.

### 36.8. Retry và poison record

Gửi record lỗi deserialize hoặc listener exception. Xác nhận metrics phân biệt “không có delivered message” với “delivered nhưng fail”, và error handler/recovery xử lý record theo policy.

### 36.9. Rebalance trong lúc idle

Thêm/bớt consumer member. Xác nhận tracker reset/đóng state theo assignment epoch và không giữ stale partition idle metrics ở owner cũ.

### 36.10. Forced shutdown

Kết thúc JVM đột ngột trong test. Xác nhận monitoring không xem process đã chết là một idle interval đang tăng mãi và alert liveness được tách khỏi alert idle.

Không test bằng cách phá production topic, tắt broker dùng chung hoặc reset offset group đang phục vụ nghiệp vụ. Dùng Kafka test cluster và các container/consumer groups riêng.

## 37. Các sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Coi mọi idle event là lỗi consumer | Alert ồn và restart không cần thiết | Xét traffic expectation, lag, assignment |
| Nhầm idle với non-responsive poll | Chẩn đoán sai root cause | Dùng NonResponsiveConsumerEvent và poll metrics riêng |
| Chỉ nhìn running=true | Bỏ sót paused, no assignment, poll blocked | Ghép lifecycle, pause, assignment, poll |
| Không cấu hình idleEventInterval | Không có event theo ngưỡng mong muốn | Cấu hình và xác nhận ở factory thực tế |
| Đếm từng idle event như incident mới | Tạo nhiều ticket cho một khoảng idle | State machine, dedup, rate limit |
| Gộp idle của child consumer thành toàn group | Báo sai phạm vi | Dùng child/partition/group-level metrics |
| Chỉ nhìn lag bằng 0 | Bỏ sót producer đã dừng | So sánh expected producer rate/heartbeat |
| Chỉ nhìn lag lớn | Không phân biệt paused, poison, LSO | Kiểm tra root cause và commit progress |
| Dùng lastDelivered thay cho lastSucceeded | Không thấy listener đang fail liên tục | Theo dõi hai mốc độc lập |
| Restart trong @EventListener mỗi khi idle | Rebalance storm/duplicate | Chỉ recovery sau chẩn đoán và rate limit |
| Event handler gọi HTTP đồng bộ dài | Chặn consumer/event thread | Metrics update nhanh, async bounded notification |
| Dùng KafkaConsumer từ async event thread | Vi phạm thread safety | Điều khiển qua container APIs |
| Không đóng idle state khi revoke/stop | Gauge stale, false alert | Lifecycle-aware tracking |
| Alert topic rare-events như topic real-time | False positives liên tục | Topic-specific SLA/arrival schedule |
| Không phân biệt startup idle | Cảnh báo ngay khi chưa từng có record | Startup grace và never-seen state |
| Dùng metric labels eventId/customerId | Cardinality tăng mạnh | ID ở logs/traces, labels bounded |
| Không kiểm tra DLT/deserialize errors | Poison pill bị hiểu thành thiếu dữ liệu | ErrorHandlingDeserializer/error handler |
| Cho rằng read_committed có thể đọc tới LEO | Báo lỗi khi LSO bị open transaction giữ | Kiểm tra transaction state và LSO |

## 38. Checklist production

Trước khi triển khai cơ chế phát hiện container không có message:

1. Có xác định rõ “không có message” nghĩa là không fetch, không deliver hay không xử lý thành công không?
2. Topic có expected arrival pattern và SLO dữ liệu không?
3. Container factory thực tế đã cấu hình idleEventInterval theo mục tiêu chưa?
4. Event listeners có nhận đúng ListenerContainerIdleEvent và NoLongerIdleEvent không?
5. Có cần idle event theo partition thay vì chỉ theo container không?
6. Event IDs/listener IDs có được xử lý đúng cho concurrent child containers không?
7. Có dedup idle events thành một khoảng idle duy nhất không?
8. Có đo seconds since last delivered và last successful processing riêng không?
9. Khi container pause, metrics và alert có nhận biết nguyên nhân pause không?
10. Có phân biệt running, paused, stopped, assigned partition count và rebalance không?
11. Có NonResponsiveConsumerEvent monitor với pollTimeout/noPollThreshold/monitorInterval phù hợp không?
12. Event handlers có tránh blocking I/O và truy cập KafkaConsumer sai thread không?
13. Có kết hợp idle với group lag, producer traffic và oldest unprocessed record age không?
14. Consumer isolation=read_committed và khả năng LSO bị giữ có được xem xét không?
15. Có monitor deserialization failure, retry/backoff và DLT publish failure không?
16. Có startup grace và never-seen state cho listener chưa từng nhận dữ liệu không?
17. Có policy alert khác nhau cho continuous, scheduled và rare-event topics không?
18. Có giới hạn metric labels và lifecycle cleanup khi partition revoke/instance stop không?
19. Có runbook cho idle+lag=0, idle+lag>0, paused quá lâu và non-responsive poll không?
20. Có integration tests cho empty topic, resume, pause, rebalance, poison record và forced shutdown không?

**Kết luận:** Phát hiện container không có message trong Spring Kafka không chỉ là chờ một ListenerContainerIdleEvent. Idle là sự thiếu dữ liệu được giao trong một khoảng thời gian; non-responsive là dấu hiệu consumer poll không tiến triển như kỳ vọng; paused/stopped và không được assignment lại có nguyên nhân vận hành riêng. Một hệ thống đáng tin cậy cần kết hợp **idle events, no-longer-idle events, NonResponsiveConsumerEvent, assignment, pause state, lag, producer ingress và listener success metrics** để xác định liệu khoảng im lặng có bình thường hay đang che giấu sự cố. Khi phân loại đúng, cảnh báo sẽ hữu ích hơn, tránh restart loop và bảo vệ khả năng phục hồi record mà không tạo duplicate hoặc commit sai offset.
