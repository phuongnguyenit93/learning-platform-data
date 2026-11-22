# Consumer bị kẹt trong poll

## 1. Bối cảnh và mục tiêu

Trong Spring Kafka, listener container điều khiển một hoặc nhiều KafkaConsumer. Consumer gọi **poll()** để lấy record từ broker, giao chúng tới phương thức **@KafkaListener**, xử lý acknowledgment/offset commit rồi lặp lại. Một vòng poll khỏe mạnh có thể trả dữ liệu hoặc trả danh sách rỗng khi topic không có dữ liệu.

Một trường hợp bất thường xảy ra khi **poll() không quay lại trong thời gian hợp lý**. Khi đó ứng dụng không nhận thêm record, không phát hiện được idle theo cách thông thường và consumer lag có thể tăng. Tình huống này khác với một listener đang xử lý record lâu hoặc một topic thật sự không có message.

Spring Kafka cung cấp **NonResponsiveConsumerEvent** để giám sát consumer có dấu hiệu không phản hồi ở poll. Bài học giải thích cơ chế phát hiện, cấu hình timeout, cách phân biệt với idle/slow processing, và quy trình xử lý production mà không tạo restart loop.

~~~text
KafkaMessageListenerContainer
       |
       v
Consumer thread
       |
       v
KafkaConsumer.poll()
       |
       +-- Trả về records ---> @KafkaListener ---> commit/ack ---> poll tiếp
       |
       +-- Trả về rỗng ------> idle tracking ------> poll tiếp
       |
       +-- Không quay lại đúng kỳ vọng
                  |
                  v
           Monitor scheduler
                  |
                  v
         NonResponsiveConsumerEvent
                  |
                  v
          Log/metric/investigate
                  |
                  v
         Recovery có kiểm soát
~~~

Một NonResponsiveConsumerEvent là **dấu hiệu cần điều tra**, không phải kết luận chắc chắn rằng Kafka broker đã chết, JVM bị deadlock hoặc một lần restart sẽ khắc phục vấn đề.

## 2. Poll loop hoạt động như thế nào?

Một KafkaMessageListenerContainer thông thường làm các việc:

1. Tạo KafkaConsumer từ ConsumerFactory.
2. Subscribe topic hoặc dùng assignment đã cấu hình.
3. Join consumer group và nhận partition assignment.
4. Gọi KafkaConsumer.poll với khoảng chờ phù hợp.
5. Khi poll trả records, gọi record listener hoặc batch listener.
6. Khi xử lý kết thúc, thực hiện commit/ack theo AckMode và error handler.
7. Gọi poll tiếp; đồng thời xử lý pause, rebalance và lifecycle.
8. Khi container stop, đóng consumer và giải phóng tài nguyên.

**pollTimeout** là timeout truyền vào một lời gọi poll, không phải giới hạn cho toàn bộ vòng xử lý. Một poll có thể trả rất nhanh nhưng listener lại xử lý hàng trăm record trong vài phút.

~~~text
poll()
   |
   v
records/empty
   |
   v
listener hoặc idle logic
   |
   v
commit/error handling
   |
   v
poll() lần tiếp theo
~~~

Nếu poll không trả về, những bước sau trong vòng lặp chưa được chạy. Nếu listener xử lý lâu, poll đã trả về nhưng vòng lặp chưa thể quay lại poll. Hai vấn đề cần được phân biệt khi chẩn đoán.

## 3. Phân biệt idle, non-responsive và processing chậm

| Hiện tượng | Mô tả | Tín hiệu chính |
|---|---|---|
| **Idle** | Poll hoạt động, không có record giao tới listener | ListenerContainerIdleEvent |
| **Non-responsive** | Consumer có dấu hiệu không tiến qua lời gọi poll trong thời gian mong đợi | NonResponsiveConsumerEvent |
| **Long processing** | Poll đã trả record nhưng listener/callback giữ thread quá lâu | Processing duration, thread dump, max.poll.interval.ms |
| **Paused** | Container cố tình tạm ngừng delivery theo pause policy | ConsumerPausedEvent, pause state |
| **Stopped** | Consumer lifecycle đã kết thúc | ConsumerStoppedEvent/ContainerStoppedEvent |
| **Unassigned** | Consumer chưa có partition cần đọc | Group/partition assignment |

Không thể kết luận poll bị kẹt chỉ vì không thấy messages. Topic có thể rỗng; có thể không có partition được gán; hoặc toàn bộ records đang chờ một transaction upstream được commit.

### 3.1. Consumer idle là tình huống bình thường

Một topic settlement chỉ có vài record mỗi giờ. Consumer poll liên tục nhưng không thấy record trong 10 phút vẫn có thể healthy.

Nếu cấu hình idleEventInterval, Spring Kafka có thể phát ListenerContainerIdleEvent. Event này cho biết **không có record được nhận trong khoảng idle**, không phải cảnh báo poll bị block.

### 3.2. Vì sao non-responsive không phát giống idle?

ListenerContainerIdleEvent phụ thuộc poll loop có cơ hội cập nhật idle state. Nếu poll không thoát, container không thể tiếp tục vòng lặp để phát idle event như bình thường. Do đó Spring Kafka có cơ chế monitor riêng phát NonResponsiveConsumerEvent khi poll vượt ngưỡng.

~~~text
A. Topic rỗng nhưng poll khỏe:

poll --> empty --> poll --> empty --> poll --> empty
                    |
                    v
            ListenerContainerIdleEvent

B. Poll không quay lại:

poll -----------------------------------> chưa trả về
          |
          v
    Monitor độc lập
          |
          v
    NonResponsiveConsumerEvent
~~~

## 4. NonResponsiveConsumerEvent trong Spring Kafka

Class:

~~~java
org.springframework.kafka.event.NonResponsiveConsumerEvent
~~~

Đây là một **Spring application event** do listener container phát, không phải Kafka record trong topic.

Các thuộc tính hữu ích:

| API | Ý nghĩa |
|---|---|
| **getListenerId()** | ID của listener/container phát event |
| **getTimeSinceLastPoll()** | Thời gian kể từ poll gần nhất, đơn vị milliseconds |
| **getTopicPartitions()** | Tập topic-partition liên quan tới consumer |
| **getSource()** | Container phát event |
| **getContainer()** | Container liên quan, có thể là parent khi source là child |
| **getConsumer()** | Reference tới Kafka Consumer trong những trường hợp được cung cấp |

**getTimeSinceLastPoll()** không phải consumer lag, số record chờ, hay thời gian xử lý của một record. Đây là một thông số về thời gian poll được framework theo dõi.

Ví dụ observer:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPollObserver {

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
            "Kafka consumer non-responsive: listener={}, ms={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions()
        );
    }
}
~~~

Handler này chỉ ghi log. Không thực hiện consumer.poll(), consumer.seek(), consumer.commitSync() hoặc thao tác bất đồng bộ trực tiếp trên KafkaConsumer.

## 5. Ba tham số phát hiện consumer non-responsive

Spring Kafka dùng các property trong **ContainerProperties**:

| Property | Mặc định thường gặp | Đơn vị | Vai trò |
|---|---:|---|---|
| **pollTimeout** | 5000 | milliseconds | Khoảng chờ truyền vào poll() |
| **noPollThreshold** | 3.0 | hệ số | Ngưỡng so với pollTimeout |
| **monitorInterval** | 30 | seconds | Chu kỳ monitor kiểm tra consumer threads |

Ngưỡng phát hiện mang ý nghĩa:

~~~text
pollTimeout × noPollThreshold
~~~

Ví dụ:

~~~text
pollTimeout      = 5000 ms
noPollThreshold  = 3.0

Ngưỡng          = 5000 × 3.0
                 = 15000 ms
                 = 15 giây

monitorInterval  = 30 giây
~~~

Monitor không phải timer độ chính xác tuyệt đối. Nếu thời gian poll vượt ngưỡng giữa hai lần kiểm tra, event được phát khi monitor kiểm tra ở vòng phù hợp tiếp theo.

### 5.1. Vì sao noPollThreshold phải lớn hơn 1?

Tài liệu Spring Kafka khuyến nghị **noPollThreshold > 1.0** để tránh cảnh báo giả do race condition quanh thời điểm poll. Nếu dùng 1.0, một poll bình thường có thể bị xem là vượt ngưỡng bởi sai lệch timing hoặc scheduling.

Chọn threshold theo yêu cầu phát hiện, pollTimeout thực tế và độ nhiễu của runtime, không chỉ giảm ngưỡng xuống mức thấp nhất.

## 6. Cấu hình monitor bằng Java

Ví dụ một listener factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaMonitoringConfig {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            monitoredKafkaListenerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);

        var props = factory.getContainerProperties();
        props.setPollTimeout(5_000L);
        props.setNoPollThreshold(3.0f);
        props.setMonitorInterval(10);

        return factory;
    }
}
~~~

Listener trỏ tới factory:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "monitoredKafkaListenerFactory"
)
public void consume(OrderCreated order) {
    fulfillmentService.processIdempotently(order);
}
~~~

Trong ví dụ, ngưỡng thời gian tương ứng là 15 giây và monitor được yêu cầu kiểm tra mỗi 10 giây. Đây là cấu hình giám sát; **không tự động restart container**.

### 6.1. Một ứng dụng có nhiều factory

Nếu @KafkaListener dùng một factory khác, cấu hình monitor ở factory trên không tác động tới listener đó. Luôn xác định container factory thực sự đang được endpoint sử dụng.

Khi concurrency lớn, mỗi child consumer có poll thread riêng và cần được quan sát theo listener/container identity.

## 7. Kết hợp ListenerContainerIdleEvent

Có thể cấu hình idle event song song để phân biệt topic rỗng và poll bất thường:

~~~java
var props = factory.getContainerProperties();

props.setPollTimeout(5_000L);
props.setIdleEventInterval(60_000L);
props.setNoPollThreshold(3.0f);
props.setMonitorInterval(10);
~~~

Một observer cho cả hai:

~~~java
@Component
public class ConsumerHealthEvents {

    @EventListener
    public void idle(ListenerContainerIdleEvent event) {
        log.info(
            "Listener idle: listener={}, idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }

    @EventListener
    public void nonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Suspected blocked Kafka poll: listener={}, sinceLastPollMs={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll()
        );
    }

    @EventListener
    public void noLongerIdle(ListenerContainerNoLongerIdleEvent event) {
        log.info(
            "Listener receiving records after idle: {}",
            event.getListenerId()
        );
    }
}
~~~

**ListenerContainerNoLongerIdleEvent** xuất hiện khi nhận record sau giai đoạn idle trong các phiên bản hỗ trợ. Nó không phải một event đặc biệt đảm bảo rằng tình huống non-responsive đã được chữa.

## 8. Thread safety của event listener

KafkaConsumer **không thread-safe**, ngoại trừ các thao tác được API Kafka cho phép gọi từ thread khác trong điều kiện cụ thể, ví dụ wakeup().

Non-responsive detection chạy qua cơ chế monitor/scheduler; không nên coi observer NonResponsiveConsumerEvent là consumer poll thread. Spring event multicaster cũng có thể được cấu hình bất đồng bộ.

Vì vậy, observer không nên:

- Gọi consumer.poll(), seek(), commitSync() hoặc subscribe().
- Giữ tham chiếu consumer để dùng từ executor khác.
- Thực hiện I/O nặng làm block scheduler.
- Tự ý pause/resume consumer từ thread không phù hợp.
- Tự restart container ngay trong callback khi chưa kiểm tra lifecycle.
- Gửi dữ liệu nhạy cảm trong record vào logging backend.

Nên giới hạn callback ở logging, Micrometer metrics và gửi **yêu cầu điều tra** tới một coordinator chuyên biệt.

## 9. Poll không quay lại có thể do đâu?

Những giả thuyết cần được phân biệt:

| Nhóm nguyên nhân | Ví dụ | Cách xác minh |
|---|---|---|
| Kafka client | Bug của kafka-clients version cụ thể | Stack trace, version, release notes |
| Broker/network | TCP không ổn định, DNS, broker/coordinator sự cố | Client logs, broker metrics |
| Group coordination | Join group/rebalance chậm hoặc callback bất thường | Rebalance events, thread dump |
| User callback | Rebalance listener, deserializer, interceptor bị block | Thread dump, callback duration |
| Listener processing | HTTP/DB call kéo dài sau poll | Thread dump tại listener, processing timer |
| JVM | GC pause, CPU starvation, lock contention | GC logs, CPU/throttling, thread dump |
| Shutdown race | Container đang stop nhưng thread chưa thoát | Lifecycle events, stop logs |

Không phải mọi nguyên nhân trong bảng đều đồng nghĩa KafkaConsumer.poll đang bị chặn bên trong. Một số làm **khoảng cách giữa các lần poll dài ra**. Phải dùng thread dump để phân loại chính xác.

### 9.1. Broker down không luôn gây blocked poll

Kafka client hiện đại có nhiều cơ chế reconnect và timeout. Broker outage có thể làm poll vẫn trả rỗng và consumer vẫn đi qua vòng lặp. Trong những phiên bản kafka-clients cũ, tài liệu Spring Kafka từng mô tả trường hợp poll không quay lại khi broker không truy cập được.

Do đó, không tạo giả định “broker down = poll deadlock” khi chưa kiểm tra client version và behavior thực tế.

## 10. Thread dump: bằng chứng quan trọng

Khi thấy NonResponsiveConsumerEvent lặp lại, thu thập thread dump theo quy trình vận hành. Có thể dùng JVM tooling được phép, chẳng hạn:

~~~text
jcmd <PID> Thread.print -l
~~~

Không chạy tùy tiện trong production nếu thiếu quyền hoặc làm ảnh hưởng workload. Thread dump có thể chứa tên tài nguyên và dữ liệu cần bảo vệ.

Đối chiếu consumer thread:

| Thread đang ở đâu? | Hướng điều tra |
|---|---|
| KafkaConsumer.poll hoặc network client | Client, broker, coordinator, network |
| Deserializer/interceptor | Schema, validation, custom interceptor hoặc bug |
| onPartitionsAssigned/onPartitionsRevoked | Callback rebalance bị chặn |
| @KafkaListener/HTTP client | Processing chậm, downstream timeout |
| WAITING trên application lock | Deadlock/lock contention |
| GC/CPU pressure | JVM pause hoặc pod throttling |

Một vài thread dumps cách nhau khoảng ngắn có thể cho biết stack có tiến hay đứng yên. Không cần chụp liên tục ở tần suất quá cao.

### 10.1. Phân biệt blocked poll với blocked listener

Nếu stack chỉ ra:

~~~text
org.apache.kafka.clients.consumer.KafkaConsumer.poll(...)
~~~

thì giả thuyết poll bị chặn có cơ sở trực tiếp hơn.

Nếu stack chỉ ra:

~~~text
FulfillmentService.callExternalApi(...)
HttpClient.execute(...)
~~~

thì poll có thể đã trả record và listener đang bị block. Lúc này cần timeout ở downstream, batch sizing và max.poll.interval.ms thay vì chỉ đổi pollTimeout.

## 11. pollTimeout không phải max.poll.interval.ms

Hai property có ý nghĩa hoàn toàn khác:

- **pollTimeout**: thời gian chờ trong một lời gọi KafkaConsumer.poll do container sử dụng.
- **max.poll.interval.ms**: giới hạn của Kafka đối với thời gian giữa các lần consumer poll hợp lệ trong consumer group.

Ví dụ:

~~~text
pollTimeout          = 5 giây
max.poll.interval.ms = 300 giây

poll() trả batch trong 1 giây
listener xử lý 400 giây
poll() lần sau
~~~

Trong ví dụ này, poll không bị kẹt bên trong; **listener processing quá lâu** có thể khiến consumer vi phạm max.poll.interval.ms và mất group membership hoặc gây rebalance.

Một lỗi khác:

~~~text
pollTimeout = 5 giây
poll() không quay lại sau 40 giây
monitor phát NonResponsiveConsumerEvent
~~~

Đây mới gần với tình huống poll không trả về.

| Cấu hình | Cấp | Mục đích |
|---|---|---|
| pollTimeout | Spring Kafka container | Timeout truyền tới poll |
| noPollThreshold | Spring Kafka monitor | Ngưỡng cảnh báo |
| monitorInterval | Spring Kafka monitor | Nhịp kiểm tra |
| max.poll.interval.ms | Kafka client/group | Liveness giữa các lần poll |
| session.timeout.ms | Kafka group protocol | Session failure detection |
| request.timeout.ms | Kafka client | Thời gian chờ request |

Không tăng max.poll.interval.ms vô hạn để che deadlock và không giảm pollTimeout quá nhỏ chỉ nhằm tạo poll loop quay nhanh mà không đo chi phí.

## 12. Batch listener kéo dài khoảng giữa các lần poll

Batch listener xử lý nhiều record:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "ordersBatchFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (var record : records) {
        fulfillmentService.process(record.value());
    }
}
~~~

Nếu batch có 400 record, mỗi record mất 50 ms:

~~~text
400 × 50 ms = 20.000 ms = 20 giây
~~~

Thêm HTTP timeouts hoặc DB lock có thể khiến listener kéo dài nhiều phút.

Biện pháp:

- Điều chỉnh **max.poll.records**.
- Áp dụng timeout cho DB/HTTP.
- Theo dõi batch processing duration p95/p99.
- Giới hạn retry/backoff.
- Chọn concurrency theo số partition và downstream capacity.
- Không tự giao record sang thread pool rồi commit trước khi side effect hoàn tất.

Nếu thread dump cho thấy listener chậm, tăng noPollThreshold chỉ làm cảnh báo ít đi, không sửa bottleneck.

## 13. Rebalance callback gây block

Consumer có thể chạy các callback khi partition được assign hoặc revoked. Nếu callback thực hiện database scan lâu:

~~~text
KafkaConsumer.poll
       |
       v
Rebalance
       |
       v
onPartitionsAssigned(...)
       |
       +-- DB query
       +-- Cache restore
       +-- HTTP dependency
       |
       v
poll loop bị kéo dài
~~~

Không nên thực hiện I/O có thời gian không giới hạn trong ConsumerAwareRebalanceListener.

Nếu local state cần phục hồi, hãy xây cơ chế có timeout, bảo vệ ownership và ngăn tác vụ cũ ghi vào state sau khi partition đã bị chuyển.

Khi thấy NonResponsiveConsumerEvent gần thời điểm rebalance, kiểm tra stack trace thay vì suy luận ngay Kafka broker lỗi.

## 14. Pause khác non-responsive

Spring Kafka có thể tạm pause consumer/container để giảm tải hoặc đợi downstream hồi phục. Khi pause, container vẫn cần duy trì poll/liveness theo cơ chế tương ứng để giữ group membership.

| Trạng thái | Ý nghĩa |
|---|---|
| RUNNING | Container còn chạy |
| PAUSED | Container tạm ngừng delivery theo pause policy |
| NON-RESPONSIVE | Monitor thấy tiến độ poll bất thường |
| STOPPED | Consumer/container đã kết thúc lifecycle |

Ở các phiên bản hỗ trợ, container có **pollTimeoutWhilePaused** dành cho poll khi đang pause.

Một container pause có chủ đích có thể tăng lag mà không bị “kẹt”. Không restart chỉ vì throughput giảm nếu pause là trạng thái mong muốn.

## 15. monitorInterval và false positives

Giả sử:

~~~text
pollTimeout      = 5000 ms
noPollThreshold  = 3.0
monitorInterval  = 10000 ms

Ngưỡng       ~ 15 giây
Monitor kiểm tra mỗi 10 giây
~~~

Nếu một lần poll bị trễ ngay sau lần kiểm tra, event có thể chỉ đến ở vòng sau. Nếu JVM GC pause 20 giây, monitor có thể thấy thời gian trôi qua lớn hơn mong muốn dù không hề có deadlock trong Kafka client.

Do đó, tránh quyết định stop/restart dựa vào **một event duy nhất**. Cần quan sát persistence, thread dump, broker health và resource pressure.

Có thể kết hợp:

- GC pause / safepoint durations.
- CPU usage và CPU throttling.
- Thread contention.
- Network disconnect/reconnect.
- Kafka client request latency.
- Consumer lag.
- Rebalance và assignment changes.

## 16. Concurrency và child containers

Với concurrency=3:

~~~text
ConcurrentMessageListenerContainer
       |
       +-- child #0 --> KafkaConsumer #0
       +-- child #1 --> KafkaConsumer #1
       +-- child #2 --> KafkaConsumer #2
~~~

Mỗi child có poll thread riêng. Một child phát NonResponsiveConsumerEvent không có nghĩa tất cả consumers cùng group đều hỏng.

Khi điều tra, gắn event với:

- Listener/child ID.
- Parent container.
- Topic partitions.
- Client ID và group ID.
- Pod/instance.
- Consumer lag theo partition.
- Trạng thái các child khác.

Dừng parent chỉ vì một event đơn lẻ có thể làm cả các child khỏe mạnh phải rời group và tạo rebalance không cần thiết.

## 17. Recovery: dừng container có kiểm soát

KafkaConsumer có **wakeup()** để đánh thức một số blocking operations từ thread khác theo Kafka API. Tuy nhiên, khi dùng Spring Kafka, container đã quản lý KafkaConsumer và lifecycle của nó.

Nếu cần dừng consumer đang có dấu hiệu bị kẹt, ưu tiên thao tác với **managed listener container**. Đừng tự gọi poll, commit hay thay consumer instance từ event callback.

Một kiến trúc hợp lý:

~~~text
NonResponsiveConsumerEvent
          |
          v
Observer log/metric ngắn
          |
          v
Recovery coordinator
          |
          +-- Deduplicate theo listener ID
          +-- Kiểm tra còn non-responsive?
          +-- Kiểm tra context có shutdown?
          +-- Thu thập diagnostics
          +-- Kiểm tra root cause
          |
          v
Stop container ở management thread nếu cần
          |
          v
Chờ stop-complete
          |
          v
Start lại có backoff theo policy
          |
          v
Xác nhận poll/assignment/offset tiến
~~~

Không gọi stop trên thread không phù hợp hoặc gọi start ngay khi stop chưa hoàn tất. Với parent concurrent container, cần tránh thao tác nhầm một child instance.

### 17.1. Ví dụ observer chỉ gửi tín hiệu điều tra

~~~java
@Component
public class NonResponsiveAlertObserver {

    private final KafkaRecoveryCoordinator coordinator;

    public NonResponsiveAlertObserver(
            KafkaRecoveryCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @EventListener
    public void nonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Kafka poll may be blocked: id={}, millis={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll()
        );

        coordinator.requestInvestigation(event.getListenerId());
    }
}
~~~

**KafkaRecoveryCoordinator** là class tùy biến của ứng dụng trong ví dụ; Spring Kafka không cung cấp sẵn class tên này.

Coordinator nên kiểm tra lifecycle, có debounce/backoff, giới hạn restart attempts, và không restart khi Spring context đang closing.

## 18. Restart loop là một lỗi vận hành khác

Một implementation nguy hiểm:

~~~java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    var container = registry.getListenerContainer("orders-listener");
    container.stop();
    container.start();
}
~~~

Không dùng mẫu này trong production vì:

- Stop có thể chưa hoàn tất khi start được gọi.
- Event phát từ child nhưng parent có thể vẫn running.
- Root cause chưa được sửa.
- Monitor có thể phát nhiều events cho một incident.
- Trong shutdown, observer có thể khởi động lại container đã được stop có chủ đích.
- Restart hàng loạt tạo rebalance và connection storm.

Nếu automation thật sự cần thiết, phải có **single-flight guard**, **restart budget**, **backoff/jitter**, **stop-complete callback** và **evidence-based recovery**.

## 19. Offset và duplicate sau restart

Nếu consumer đã tạo side effect nhưng offset Kafka chưa commit khi container dừng, record có thể được giao lại.

~~~text
Committed offset = 100

Consumer cũ:
    offset 100 -> DB update OK
    offset 101 -> DB update OK
    offset 102 -> đang xử lý
    consumer restart trước Kafka commit

Consumer mới:
    có thể đọc lại từ offset 100
~~~

Đây là at-least-once delivery. Non-responsive recovery không tự mang exactly-once tới database hoặc HTTP API.

Biện pháp:

1. Producer tạo event ID ổn định.
2. Consumer lưu event ID cùng business side effect trong một DB transaction.
3. DB có unique constraint chống duplicate.
4. API bên ngoài dùng idempotency key khi có.
5. Offset commit chỉ xảy ra khi processing/recovery phù hợp.
6. DLT/poison record có quy trình xử lý riêng.

Ví dụ:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Không chỉ kiểm tra tồn tại trước khi insert vì có thể xảy ra race condition; unique constraint mới là lớp bảo vệ chính.

## 20. Kafka transaction và non-responsive consumer

Trong consume-transform-produce thuần Kafka, transactional container có thể phối hợp output Kafka và input offsets trong cùng transaction.

Khi transaction abort do lỗi hoặc lifecycle dừng trước commit:

- Output Kafka chưa commit không được read_committed consumers giao.
- Input offsets không commit trong transaction abort.
- Input records có thể được giao lại.
- Side effects ngoài Kafka không tự rollback.

Nếu recovery restart transactional producer, cần kiểm tra transactional ID uniqueness giữa các pod để tránh ProducerFencedException.

NonResponsiveConsumerEvent không báo transaction đã commit hay abort. Muốn biết tình trạng Kafka transaction, cần quan sát transaction manager, broker logs và outcome metrics riêng.

## 21. Monitoring và metrics

| Tín hiệu | Điều cần biết |
|---|---|
| NonResponsiveConsumerEvent count | Tần suất cảnh báo theo listener/consumer |
| timeSinceLastPoll | Khoảng thời gian poll không tiến |
| ListenerContainerIdleEvent count | Poll vẫn hoạt động dù không có record? |
| Listener processing duration | Business code có đang block? |
| Poll latency và request latency | Kafka client/broker có chậm? |
| Consumer lag per partition | Backlog tăng ở partition nào? |
| Records consumed rate | Throughput có ngừng? |
| Rebalance count/duration | Group có mất ổn định? |
| Assigned partitions | Consumer có đang sở hữu partition? |
| GC pause/CPU throttling | JVM/node có trì hoãn consumer thread? |
| Commit errors | Offset có tiến đúng policy? |
| Restart attempts | Có restart loop? |
| DLT/recovery failures | Poison record có làm chậm pipeline? |

Tên metrics thực tế phụ thuộc kafka-clients, Spring Kafka, Micrometer, JMX exporter và dashboard. Đừng giả định mọi metric đều được tạo sẵn.

### 21.1. Structured log

~~~text
event=non_responsive_consumer
listenerId=orders-listener-1
groupId=order-fulfillment
topicPartitions=orders.created-2,orders.created-3
timeSinceLastPollMs=37000
pollTimeoutMs=5000
noPollThreshold=3.0
monitorIntervalSeconds=10
action=investigate
~~~

Không log key/value payload hoặc secrets chỉ để chẩn đoán non-responsive. Thông tin cần thiết là thời gian, consumer identity và trạng thái.

## 22. Runbook production

1. Xác định service/pod, listener ID, group ID và partitions.
2. Ghi nhận NonResponsiveConsumerEvent và timeSinceLastPoll.
3. Xác định pollTimeout, noPollThreshold và monitorInterval thực tế.
4. Kiểm tra container RUNNING, PAUSED, STOPPING hay STOPPED.
5. Đối chiếu idle events và tốc độ record được producer gửi.
6. Xem lag từng partition và last committed offset.
7. Thu thập thread dump hợp lệ để xác định thread đang ở poll hay listener.
8. Xem Kafka client logs: disconnect, timeout, coordinator và rebalance.
9. Kiểm tra broker health, DNS, network, TLS và ACL.
10. Xem GC pauses, CPU throttling, thread contention và task executor.
11. Nếu listener block, kiểm tra timeout DB/HTTP, batch size và retry/backoff.
12. Nếu rebalance callback block, kiểm tra state restoration và external calls.
13. Đánh giá event có kéo dài nhiều monitor cycles hay chỉ xảy ra một lần.
14. Không reset offsets hay restart hàng loạt khi chưa biết root cause.
15. Nếu cần, stop/restart managed container từ thread điều phối riêng.
16. Đợi partition assignment và poll/processing tiếp tục.
17. Kiểm tra commit offset và consumer lag giảm.
18. Xác nhận idempotency cho những record được giao lại.
19. Ghi root cause, remediation và bằng chứng phục hồi.

**Không chỉ dùng container.isRunning() làm tiêu chí kết thúc incident.** Một container running vẫn có thể không nhận partition, bị pause hoặc không xử lý record.

## 23. Integration test: idle, blocked poll và slow listener

Nên tách ba tình huống test độc lập với Kafka broker thực hoặc Embedded Kafka/Testcontainers phù hợp.

### 23.1. Consumer idle

- Tạo topic không có record.
- Đặt idleEventInterval nhỏ trong môi trường test.
- Khởi động listener, đợi assignment.
- Xác nhận ListenerContainerIdleEvent xuất hiện.
- Gửi record và xác nhận listener nhận.
- Khi version hỗ trợ, kiểm tra ListenerContainerNoLongerIdleEvent.

Test chứng minh topic rỗng không đồng nghĩa poll bị kẹt.

### 23.2. Non-responsive

- Cấu hình pollTimeout, noPollThreshold và monitorInterval nhỏ, có giới hạn.
- Dùng test-specific consumer wrapper hoặc fault injection để tạo độ trễ poll được kiểm soát.
- Thu thập NonResponsiveConsumerEvent.
- Kiểm tra listener ID và timeSinceLastPoll.
- Gỡ fault injection, stop container nếu cần.
- Xác nhận cleanup không để thread bị block sau khi test kết thúc.

Không tạo test bằng cách chặn consumer thread vô hạn hoặc chỉ tắt broker rồi mặc định mọi kafka-clients version đều kẹt.

### 23.3. Listener xử lý lâu

- Gửi batch đủ lớn hoặc mô phỏng downstream latency có timeout.
- Đo listener processing duration.
- Xem max.poll.interval.ms và rebalance.
- Thu thập thread dump trong phạm vi test.
- Xác nhận stack nằm trong business code khi listener bị block.
- Thử giảm batch size hoặc thêm timeout và đo lại.

Test giúp đội vận hành không nhầm nguyên nhân rồi thay sai cấu hình poll.

## 24. Ví dụ thực tế: Order Fulfillment

Order Fulfillment có topic orders.created với tám partition. Hai pod, mỗi pod concurrency=2. Factory:

~~~java
var props = factory.getContainerProperties();

props.setPollTimeout(5_000L);
props.setNoPollThreshold(3.0f);
props.setMonitorInterval(10);
props.setIdleEventInterval(60_000L);
~~~

Một child phát:

~~~text
listenerId=orders-listener-1
timeSinceLastPollMs=42000
partitions=[orders.created-4, orders.created-5]
~~~

Đội vận hành:

1. Xem lag của P4/P5; các partition khác vẫn tiến.
2. Đọc Kafka client logs và broker connection metrics.
3. Lấy thread dump của pod liên quan.
4. Nếu thread nằm trong network-client poll code, xem kafka-clients version, broker/coordinator và network.
5. Nếu thread nằm trong FulfillmentService gọi API không có timeout, sửa timeout và retry policy.
6. Đối chiếu GC pause, CPU throttling và monitor interval.
7. Khi container không thể phục hồi, stop/restart có backoff và stop-complete, không chạy trực tiếp trong event callback.
8. Sau restart, xác nhận group assignment, commits và lag bắt đầu giảm.
9. Kiểm tra event ID deduplication cho records có thể được nhận lại.

Bài học từ tình huống: **event chỉ là điểm bắt đầu điều tra; root cause và tiến độ sau recovery mới quyết định thành công**.

## 25. Những sai lầm cần tránh

**“Không thấy record nghĩa là poll bị kẹt.”** Sai. Topic có thể rỗng hoặc consumer đang pause.

**“Idle event và non-responsive event là một.”** Sai. Một cái phản ánh không nhận record, một cái cảnh báo tiến độ poll bất thường.

**“NonResponsiveConsumerEvent chứng minh Kafka broker down.”** Sai. Cần thread dump và broker/network evidence.

**“Không thấy idle event tức là consumer khỏe.”** Sai. Poll không trả về có thể khiến idle event không phát.

**“pollTimeout là max.poll.interval.ms.”** Sai. Hai giới hạn thuộc hai tầng khác nhau.

**“monitorInterval=10 bảo đảm event đến sau đúng 10 giây.”** Sai. Ngưỡng và scheduler đều ảnh hưởng.

**“noPollThreshold=1.0 chính xác hơn.”** Không nên; Spring Kafka khuyến nghị >1.0 để tránh false positives.

**“Có event thì gọi KafkaConsumer.commitSync.”** Không an toàn. KafkaConsumer không thread-safe.

**“Stop rồi start ngay trong event handler.”** Có thể tạo lifecycle race, đặc biệt với child containers.

**“Restart container không tạo duplicate.”** Sai. Record chưa commit có thể được giao lại.

**“Broker outage luôn gây blocked poll.”** Không đúng; nhiều kafka-clients versions có reconnect/timeout phù hợp.

**“Tăng max.poll.interval.ms sẽ sửa deadlock.”** Sai. Đó là cấu hình liveness, không phải sửa code bị block.

## 26. Checklist vận hành

- [ ] Xác nhận listener/container ID và consumer group.
- [ ] Biết pollTimeout, noPollThreshold, monitorInterval hiệu lực.
- [ ] noPollThreshold lớn hơn 1.0.
- [ ] Có observer NonResponsiveConsumerEvent nhẹ và thread-safe.
- [ ] Có idle events nếu cần phân biệt topic rỗng.
- [ ] Không gọi KafkaConsumer methods từ observer thread bất kỳ.
- [ ] Có consumer lag và partition assignment metrics.
- [ ] Có JVM GC, CPU, thread dump diagnostics.
- [ ] Có timeout cho DB/HTTP calls và giới hạn batch processing.
- [ ] Không restart vì một cảnh báo đơn lẻ không có bằng chứng thêm.
- [ ] Recovery coordinator có single-flight guard, stop-complete, backoff và budget.
- [ ] Không restart trong application shutdown.
- [ ] Có idempotency cho record redelivery.
- [ ] Test phân biệt idle, non-responsive và listener processing chậm.
- [ ] Sau recovery xác minh throughput, assignment và offset commit.

## 27. Tài liệu tham khảo

- Spring Kafka Reference — Application Events: https://docs.spring.io/spring-kafka/reference/kafka/events.html
- Spring Kafka Reference — Listener Container Properties: https://docs.spring.io/spring-kafka/reference/kafka/container-props.html
- Spring Kafka JavaDoc — NonResponsiveConsumerEvent: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/event/NonResponsiveConsumerEvent.html

Khi triển khai, đối chiếu phiên bản Spring Kafka và kafka-clients thực tế, đặc biệt nếu ứng dụng có custom ConsumerFactory, asynchronous event multicaster hoặc listener container lifecycle tùy chỉnh.

## 28. Ghi nhớ

**Consumer bị kẹt trong poll** là tình huống Kafka consumer không đạt tiến độ poll theo kỳ vọng. Spring Kafka dùng **NonResponsiveConsumerEvent** để cảnh báo, với ngưỡng dựa trên **pollTimeout × noPollThreshold** và chu kỳ kiểm tra **monitorInterval**. Mặc định thường là pollTimeout 5 giây, noPollThreshold 3.0 và monitorInterval 30 giây.

Cần phân biệt một poll không quay lại với topic idle, listener xử lý chậm, container pause và consumer stop. Event chỉ là tín hiệu; thread dump, client logs, broker metrics, partition assignment và consumer lag mới giúp tìm nguyên nhân.

Khi phục hồi, sửa root cause trước, không thao tác KafkaConsumer từ thread tùy ý, tránh restart loop và đảm bảo offset commit cùng idempotency cho record có thể được giao lại. Hệ thống chỉ được xem là phục hồi khi poll, xử lý và commit có tiến độ thực tế.
