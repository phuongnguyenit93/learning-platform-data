# ListenerContainerIdleEvent

## 1. ListenerContainerIdleEvent là gì?

Trong Spring Kafka, `ListenerContainerIdleEvent` là **application event** được listener container phát ra khi container không nhận record để giao cho listener trong một khoảng thời gian được cấu hình bởi `idleEventInterval`. Event này giúp ứng dụng nhận biết trạng thái **idle** của luồng tiêu thụ Kafka mà không cần tự xây một vòng kiểm tra thời gian nhận record cuối cùng.

Một ví dụ dễ hình dung:

~~~text
Kafka topic orders              Spring Kafka listener container
      |                                      |
      | --- record A ---------------------> @KafkaListener(A)
      | --- record B ---------------------> @KafkaListener(B)
      |                                      |
      |        Không có record mới          |
      |        trong 30 giây                |
      |                                      v
      |                        ListenerContainerIdleEvent
      |                                      |
      |                               @EventListener
      |                                      |
      |                        Log / metric / trạng thái
~~~

Event được publish **trong JVM của ứng dụng Spring** thông qua cơ chế Spring application events. Nó không phải record được producer publish vào Kafka, cũng không phải message chuyển qua một topic riêng.

Những điều quan trọng:

- **Idle** mô tả việc container không nhận record theo ngưỡng đã cấu hình, **không tự chứng minh** Kafka broker hoặc producer gặp lỗi.
- Event phản ánh hoạt động của **listener container**, không phải kết quả kiểm tra trực tiếp tiến trình nghiệp vụ ở database.
- Container vẫn có thể tiếp tục `poll()` và duy trì consumer group membership trong lúc idle.
- Khi record xuất hiện trở lại sau giai đoạn idle, Spring Kafka có thể phát `ListenerContainerNoLongerIdleEvent` để báo rằng container không còn idle.
- Mặc định ứng dụng cần **bật khoảng thời gian idle** thì mới có các thông báo này; không nên giả định mọi container tự phát idle event nếu không cấu hình.

Trong vận hành Spring Kafka Reliability Operations, `ListenerContainerIdleEvent` là một **tín hiệu quan sát**, cần kết hợp consumer lag, assignment, producer throughput và trạng thái ứng dụng trước khi diễn giải nó thành cảnh báo.

## 2. Mục tiêu dùng idle event trong production

Idle event hữu ích khi cần trả lời các câu hỏi:

1. Consumer có đang không nhận dữ liệu trong thời gian dài hơn mức dự kiến không?
2. Topic được kỳ vọng có event liên tục nhưng listener im lặng do upstream không publish hay vì vấn đề khác?
3. Consumer đã resume nhận record sau một khoảng tạm ngừng chưa?
4. Có cần cập nhật trạng thái UI/dashboard, phát metrics hoặc đánh dấu một giai đoạn nghiệp vụ tạm vắng dữ liệu không?
5. Một partition có im lặng trong khi các partition khác vẫn có traffic không?

Ví dụ dịch vụ `fraud-detection` kỳ vọng nhận payment events ít nhất mỗi vài phút. Khi listener container idle vượt ngưỡng, ứng dụng có thể ghi một metric để hệ thống cảnh báo phân tích thêm.

Ngược lại, một consumer đọc topic chỉ có event khi người dùng đổi mật khẩu có thể idle nhiều giờ mà vẫn hoàn toàn bình thường. Idle event ở trường hợp này là tín hiệu trạng thái, không phải sự cố.

Cần đặt kỳ vọng từ **đặc tính workload**. Ngưỡng 30 giây phù hợp cho luồng event liên tục nhưng có thể gây nhiễu cho luồng chỉ phát vài event mỗi ngày.

## 3. Các sự kiện liên quan trong Spring Kafka

| Event | Ý nghĩa khái quát | Khi nào dùng |
|---|---|---|
| `ListenerContainerIdleEvent` | Container đã ở trạng thái không nhận record đủ ngưỡng idle | Ghi nhận thời gian im lặng và quan sát liveness của luồng dữ liệu |
| `ListenerContainerNoLongerIdleEvent` | Container nhận record trở lại sau trạng thái idle | Kết thúc trạng thái idle, cập nhật metrics/trạng thái |
| `ListenerContainerPartitionIdleEvent` | Một partition không có record đủ ngưỡng theo dõi riêng | Tìm partition ít/không có traffic dù những partition khác hoạt động |
| `ListenerContainerPartitionNoLongerIdleEvent` | Partition có record trở lại sau khi từng idle | Ghi nhận partition khôi phục hoạt động |
| `ConsumerPausedEvent` | Container đã áp dụng pause trên các partition | Phân biệt tạm dừng có chủ đích với luồng không có dữ liệu |
| `ConsumerResumedEvent` | Container thực sự resume partition | Biết thao tác điều khiển resume đã áp dụng |
| `NonResponsiveConsumerEvent` | Poll không phản hồi trong điều kiện giám sát tương ứng | Điều tra consumer poll bị block, khác với idle do không có record |
| `ConsumerStoppedEvent` / `ContainerStoppedEvent` | Consumer/container đã dừng lifecycle | Không diễn giải stopped như một trạng thái idle bình thường |

Không được coi `ListenerContainerIdleEvent`, `ConsumerPausedEvent` và `NonResponsiveConsumerEvent` là ba tên của cùng một sự cố:

- **Idle:** consumer/container vẫn hoạt động nhưng không nhận record theo ngưỡng idle.
- **Paused:** có yêu cầu hoặc trạng thái pause nhằm tạm ngừng fetch/delivery.
- **Non-responsive:** consumer không đáp ứng kỳ vọng của vòng poll/monitoring; cần điều tra riêng.

## 4. Điều kiện phát ListenerContainerIdleEvent

### 4.1. idleEventInterval

Thuộc tính `idleEventInterval` quy định khoảng thời gian tính bằng mili-giây để container xét là idle.

Ví dụ:

~~~java
factory.getContainerProperties()
    .setIdleEventInterval(30_000L);
~~~

Khi container không nhận record trong khoảng được cấu hình, Spring Kafka có thể publish `ListenerContainerIdleEvent`. Nếu trạng thái tiếp tục idle, event có thể tiếp tục được phát ở những khoảng thời gian theo cấu hình, chứ không nhất thiết chỉ một lần duy nhất trong cả giai đoạn idle.

Do đó, một lần thiếu record kéo dài có thể tạo **nhiều idle events**. Event consumer không nên cứ mỗi lần nhận event lại phát một email/cảnh báo mới cho cùng một incident mà không có cơ chế deduplication hoặc rate limit.

### 4.2. Ngưỡng không phải đồng hồ chính xác tuyệt đối

Idle detection được kiểm tra thông qua hoạt động của listener container và vòng poll. Không nên giả định event sẽ xuất hiện chính xác đến từng mili-giây so với `idleEventInterval`, bởi thực tế phụ thuộc thời điểm poll, scheduling, listener processing, tải JVM và phiên bản Spring Kafka.

Ví dụ đặt interval 30 giây không có nghĩa event bắt buộc xuất hiện đúng sau 30.000 ms tính từ record cuối cùng theo đồng hồ của business application.

### 4.3. Trước khi có record đầu tiên

Một container vừa khởi động nhưng topic chưa có dữ liệu cũng có thể trở nên idle. Trạng thái này khác với container đã xử lý nhiều record rồi tạm im lặng. Khi phân tích incident, cần biết thời điểm startup và assignment, bởi một listener mới khởi động có thể còn chờ dữ liệu đầu tiên hoặc chờ được gán partition.

Nếu một phiên bản Spring Kafka có thuộc tính điều chỉnh cách đo idle trước record đầu tiên, hãy dùng API của đúng phiên bản; không tự suy ra thời gian idle đầu tiên luôn bắt đầu tại cùng một mốc trong mọi release.

### 4.4. Consumer không có assignment

Một container chưa được gán partition hoặc đang chờ rebalance có thể không nhận record. Khi thấy idle, cần kiểm tra assignment trước khi kết luận topic không có dữ liệu.

Cùng một triệu chứng “listener không gọi” có thể đến từ:

- Topic không có record mới.
- Consumer chưa có partition assignment.
- Có nhiều consumer hơn partition, nên một số consumer đứng rỗi.
- Container đang paused.
- Consumer/group đang rebalance.
- Consumer đã bị stop hoặc cấu hình lỗi.
- Record bị chặn bởi isolation hoặc offset/retention semantics.

Idle event là một điểm bắt đầu điều tra, không phải chẩn đoán hoàn chỉnh.

## 5. Cấu hình bằng Spring Boot application.yml

Một ứng dụng Spring Boot có thể khai báo idle event interval ở các listener properties khi version tương ứng hỗ trợ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: inventory-projection
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      type: single
      ack-mode: record
      idle-event-interval: 30s
~~~

Ý nghĩa của các cấu hình chính:

- `idle-event-interval: 30s`: yêu cầu container phát idle event khi không nhận record theo khoảng 30 giây.
- `type: single`: ví dụ dùng record listener, không phải batch listener.
- `ack-mode: record`: commit offset theo xử lý thành công từng record trong mode phù hợp.
- `enable-auto-commit: false`: giao việc commit cho Spring Kafka container thay vì consumer auto-commit theo timer.

Tên và cách bind property cần đối chiếu Spring Boot release đang dùng. Nếu ứng dụng tự tạo một `ConcurrentKafkaListenerContainerFactory` rồi bỏ qua cấu hình Boot, listener factory đó có thể không kế thừa idle event interval từ `application.yml`.

**Lưu ý:** Idle event không phụ thuộc vào việc consumer đã commit offset hay chưa. Một listener nhận được record và ghi database thành công có thể khiến container không còn idle ngay cả khi commit offset sau đó thất bại; lỗi commit phải theo dõi bằng tín hiệu khác.

## 6. Cấu hình tường minh trên container factory

Nếu cần bảo đảm một listener factory cụ thể phát idle event, cấu hình `ContainerProperties` bằng Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, InventoryChanged>
            inventoryKafkaListenerContainerFactory(
                ConsumerFactory<String, InventoryChanged> consumerFactory
            ) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, InventoryChanged>();

        factory.setConsumerFactory(consumerFactory);

        // Phát container idle event theo ngưỡng 30 giây.
        factory.getContainerProperties()
            .setIdleEventInterval(30_000L);

        return factory;
    }
}
~~~

Listener phải sử dụng factory vừa tạo:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryConsumer {

    @KafkaListener(
        id = "inventory-listener",
        topics = "inventory.changed",
        groupId = "inventory-projection",
        containerFactory = "inventoryKafkaListenerContainerFactory"
    )
    public void onInventoryChanged(InventoryChanged event) {
        inventoryService.applyIdempotently(event);
    }
}
~~~

Các kiểu `InventoryChanged` và `inventoryService` là domain code minh họa do dự án cung cấp. Cần khai báo deserializer/converter phù hợp để consumer thực sự tạo được payload object.

Nếu một project có nhiều factories, chỉ factory nào được cấu hình idle interval và được endpoint sử dụng mới có expected behavior tương ứng. Khai báo idle interval ở một factory không tự áp dụng cho mọi listener khác.

### 6.1. Cấu hình interval tùy workload

Có thể chọn ngưỡng khác nhau:

~~~text
inventory-listener:  30 giây
payments-listener:   60 giây
audit-listener:      10 phút
user-login-listener: có thể không cần idle event
~~~

Không nên đặt một ngưỡng chung quá thấp cho tất cả topics. Các topic có traffic tự nhiên thấp có thể tạo rất nhiều event không hữu ích.

## 7. Nhận ListenerContainerIdleEvent bằng @EventListener

Spring ApplicationContext có thể nhận event bằng annotation `@EventListener`.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class InventoryIdleEventLogger {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryIdleEventLogger.class);

    @EventListener
    public void onContainerIdle(ListenerContainerIdleEvent event) {
        log.warn(
            "Kafka listener idle: listenerId={}, idleMs={}, partitions={}",
            event.getListenerId(),
            event.getIdleTime(),
            event.getTopicPartitions()
        );
    }
}
~~~

Đoạn code dùng các accessors phổ biến của `ListenerContainerIdleEvent`. Nếu đang sử dụng phiên bản Spring Kafka khác, đối chiếu class API tương ứng trước khi thêm logic phụ thuộc vào metadata mới.

Event này cho phép ghi:

- Listener/container ID để truy vết endpoint.
- `idleTime` để biết thời lượng idle được báo.
- Assigned partitions liên quan đến container phát event.
- Thời điểm, application instance và correlation information nếu hệ thống logging có hỗ trợ.

Nên log theo structured fields thay vì ghi toàn bộ record payload; khi idle vốn thường không có record hiện tại để log.

### 7.1. @EventListener không tạo thêm Kafka consumer

Một bean nhận `ListenerContainerIdleEvent` không tham gia consumer group mới và không làm tăng partition consumption. Nó chỉ nhận Spring application event từ các listener containers trong cùng ApplicationContext.

Nhờ vậy, event listener có thể phục vụ metrics/diagnostics mà không ảnh hưởng đến Kafka offset của nhóm đang xử lý.

### 7.2. Phạm vi theo JVM

Nếu ứng dụng chạy ba pod, mỗi pod có Spring ApplicationContext riêng. Bean `@EventListener` của Pod A chỉ nhận các Spring application events được publish trong Pod A, không nhận event của Pod B hoặc Pod C.

Để có trạng thái toàn consumer group, cần tập hợp logs/metrics/traces từ mọi instance. Kafka không tự lan truyền `ListenerContainerIdleEvent` sang các member khác trong group.

## 8. Phân biệt ListenerContainerNoLongerIdleEvent

Sau khi container từng idle và sau đó nhận record trở lại, Spring Kafka có thể publish `ListenerContainerNoLongerIdleEvent`. Đây là tín hiệu hữu ích để kết thúc một giai đoạn idle.

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class InventoryActivityEvents {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
            "Listener became/stays idle: listenerId={}, idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        log.info(
            "Listener received records after idle: listenerId={}",
            event.getListenerId()
        );
    }
}
~~~

Vì idle event có thể lặp trong cùng giai đoạn, nên xử lý event theo state:

~~~text
RUNNING / RECEIVING
      |
      | Không có record đủ ngưỡng
      v
IDLE  -- idle event có thể phát thêm -->
      |
      | Record xuất hiện trở lại
      v
ACTIVE / NO_LONGER_IDLE
~~~

Không suy ra mỗi lần `ListenerContainerIdleEvent` đều sẽ có đúng một event `NoLongerIdle` tương ứng. Container có thể bị stop, mất assignment, restart hoặc Spring context shutdown trong lúc đang idle. Dashboard cần xét cả container lifecycle và startup events.

## 9. Idle theo container khác idle theo partition

Một listener container có thể xử lý nhiều partition, đặc biệt khi một consumer được gán nhiều partition.

~~~text
inventory.changed
  P0 -> 100 records/phút
  P1 ->   0 records/phút
  P2 ->  20 records/phút

Consumer C sở hữu P0, P1, P2
~~~

Consumer C vẫn nhận records từ P0/P2 nên có thể **không** xuất hiện container idle event, mặc dù P1 đã im lặng rất lâu.

Nếu muốn biết từng partition có data hay không, có thể dùng cơ chế **partition idle events** trong phiên bản Spring Kafka hỗ trợ.

~~~java
factory.getContainerProperties()
    .setIdleEventInterval(30_000L);

factory.getContainerProperties()
    .setIdlePartitionEventInterval(60_000L);
~~~

Ý nghĩa:

- `idleEventInterval` xét việc container không nhận records.
- `idlePartitionEventInterval` xét thời gian không nhận records từ **mỗi assigned partition** theo cơ chế container.

Hai ngưỡng có thể khác nhau vì mục tiêu khác nhau.

### 9.1. Khi nào nên quan sát partition idle?

- Topic được phân phối traffic theo tenant/key và một partition có thể thiếu event bất thường.
- Hệ thống cần kiểm tra partition-local SLA.
- Một producer chỉ ghi vào một tập partition vì bug partitioner.
- Muốn phát hiện một partition có log end offset tăng nhưng consumer không tiến.
- Cần phân biệt “cả consumer rỗi” với “chỉ một partition không được nhận record”.

Nếu topic có partition tự nhiên ít hoặc không có traffic, partition idle event có thể xảy ra bình thường. Đừng tạo cảnh báo mức nghiêm trọng cao cho tất cả partition idle mà không đối chiếu expected traffic.

## 10. Nhận partition idle events

Spring Kafka cung cấp những event chuyên biệt như `ListenerContainerPartitionIdleEvent` và `ListenerContainerPartitionNoLongerIdleEvent` trong các phiên bản hỗ trợ.

Ví dụ chỉ log event object và container context:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
import org.springframework.kafka.event.ListenerContainerPartitionNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionIdleEventLogger {

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        log.warn("Kafka partition idle: {}", event);
    }

    @EventListener
    public void onPartitionActive(
        ListenerContainerPartitionNoLongerIdleEvent event
    ) {
        log.info("Kafka partition active after idle: {}", event);
    }
}
~~~

Đây là ví dụ độc lập, logger `log` cần được khai báo bằng SLF4J tương tự các ví dụ trước. Khi cần xuất đúng topic-partition ra metrics, dùng accessor mà phiên bản Spring Kafka đang chạy cung cấp.

Một số phiên bản hoặc cấu hình có thể chỉ theo dõi container-level events; vì vậy cần kiểm tra dependency trước khi dựa vào partition events. Không tự thay sự kiện partition bằng một `ListenerContainerIdleEvent` rồi suy ra partition nào thiếu data.

## 11. Idle không đồng nghĩa consumer bị pause

Khi ứng dụng chủ động backpressure bằng `container.pause()`, các partition bị pause không trả thêm record cho listener. Tùy vòng poll và version, trạng thái không nhận record có thể cùng xuất hiện với idle-detection.

Vì vậy khi thấy idle event, cần hỏi container có đang pause hay không.

~~~text
Không có record delivered
       |
       +-- Topic thật sự chưa có data?
       |
       +-- Container đang paused?
       |
       +-- Chưa có assignment?
       |
       +-- Consumer đang rebalance?
       |
       +-- Producer/upstream đang ngừng?
       |
       +-- Consumer lỗi hoặc không poll?
~~~

Spring Kafka cung cấp các API như:

- `isPauseRequested()`: đã có yêu cầu pause.
- `isConsumerPaused()`: pause thực sự đã được áp dụng theo trạng thái container.
- `ConsumerPausedEvent` và `ConsumerResumedEvent`: theo dõi thời điểm pause/resume hiệu lực.

Dùng các tín hiệu đó để phân biệt intentional pause với thiếu dữ liệu. Không tự động restart consumer chỉ vì nhận idle event trong lúc backpressure controller đang chủ động pause.

## 12. Idle không đồng nghĩa consumer đã chết

Một consumer không có dữ liệu mới vẫn có thể gọi `poll()` bình thường và duy trì heartbeat với group coordinator.

~~~text
KafkaConsumer.poll()
      |
      +-- Không có records
      |
      +-- Container vẫn tiếp tục hoạt động
      |
      +-- Heartbeat / group membership có thể vẫn khỏe
      |
      v
Sau idle interval: ListenerContainerIdleEvent
~~~

Trường hợp này khác với:

- `session.timeout.ms`: broker không nhận đủ heartbeat và có thể loại member khỏi group.
- `max.poll.interval.ms`: consumer không gọi poll đúng hạn vì xử lý quá lâu.
- `NonResponsiveConsumerEvent`: Spring Kafka phát hiện poll có vẻ không phản hồi theo cơ chế monitor riêng.

Một listener xử lý business logic lâu khiến consumer không kịp poll có thể **không tạo idle event đúng kỳ**, vì container chưa quay lại điểm kiểm tra idle. Không dùng absence of idle event như bằng chứng consumer vẫn khỏe.

### 12.1. Idle và lag không tương đương

Nếu topic không có record mới và consumer đã bắt kịp log end, lag có thể bằng 0 và idle là bình thường.

Nếu consumer không được assign partition hoặc đang paused còn producer tiếp tục ghi, lag có thể tăng. Một idle event ở trường hợp này cần được phân tích cùng lag và assignment để xác định có vấn đề hay không.

| Idle event | Consumer lag | Một số cách hiểu |
|---|---|---|
| Có | 0 | Luồng có thể đang bình thường nhưng không có data mới |
| Có | Tăng | Có thể paused, chưa được xử lý, mất assignment hoặc có vấn đề đọc |
| Không | 0 | Consumer có thể đang xử lý hoặc chưa đạt ngưỡng idle |
| Không | Tăng | Consumer có thể đang xử lý chậm, kẹt poll hoặc ngưỡng idle chưa đạt |

Bảng này chỉ giúp định hướng điều tra. Không một cặp tín hiệu nào tự xác định root cause.

## 13. IdleEvent với concurrency lớn hơn một

Khi cấu hình `ConcurrentMessageListenerContainer` với `concurrency > 1`, Spring Kafka tạo nhiều child consumers. Mỗi child có thể sở hữu partition khác nhau và có trạng thái idle riêng.

Ví dụ:

~~~text
Topic orders: P0, P1, P2, P3

Concurrency = 2

Child consumer 0 -> P0, P1  (đang nhận record)
Child consumer 1 -> P2, P3  (không có record)
~~~

Child 1 có thể phát idle event dù child 0 vẫn xử lý bình thường. Vì vậy:

- Không coi idle event của **một child consumer** là toàn bộ service không nhận data.
- Khi ghi log, cần giữ listener/container ID và các partition assigned.
- Khi tạo dashboard toàn service, xác định rõ đang tính “một child idle”, “tất cả child idle” hay “topic không có data”.
- Nếu tăng concurrency vượt số partition, một số consumer không có assignment nên sự im lặng có thể là hệ quả cấu hình chứ không phải incident.

Tùy version, listener/container ID được trình bày kèm hậu tố chỉ child instance. Không hard-code cách nối suffix mà chưa kiểm tra giá trị `getListenerId()` thực tế trong môi trường chạy.

## 14. Event callback chạy trên thread nào?

Theo cấu hình Spring application event multicaster thông thường, Spring Kafka publish event trên đường của container/consumer thread, và một `@EventListener` đồng bộ có thể chạy ngay trong thread đó.

Đây là một chi tiết vận hành quan trọng: **event handler chậm có thể làm consumer bị chậm**, dù event chỉ được dùng để monitoring.

### 14.1. Nên làm

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    log.info(
        "Idle event: listenerId={}, idleMs={}",
        event.getListenerId(),
        event.getIdleTime()
    );

    idleEventCounter.increment();
}
~~~

Ví dụ `idleEventCounter` là counter do ứng dụng tạo. Callback chỉ ghi log và cập nhật metric nhẹ.

### 14.2. Không nên làm

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    externalHttpClient.waitForReport(120_000L);
    database.rebuildLargeProjection();
}
~~~

Nếu handler chạy đồng bộ trên consumer thread, hai thao tác này có thể khiến vòng poll bị block, tăng nguy cơ `max.poll.interval.ms` violation, rebalance và lag.

### 14.3. Cẩn thận với Async multicaster

Nếu ứng dụng cấu hình asynchronous `ApplicationEventMulticaster` hoặc `@Async` cho event listener, callback có thể chạy trên thread khác. Lúc đó không được tùy ý gọi phương thức `KafkaConsumer` từ event data hoặc thread riêng, vì KafkaConsumer không thread-safe.

Nếu muốn thao tác pause/resume, dùng container-level API. Nếu cần seek một partition, cần tuân thủ contract của consumer thread và cơ chế Spring Kafka hỗ trợ. Không biến event callback bất đồng bộ thành nơi gọi trực tiếp `consumer.seek()`.

### 14.4. Stop container từ idle event

Một số ứng dụng muốn dừng listener khi idle quá lâu. Không nên gọi một `stop()` đồng bộ có thể chờ consumer thread hoàn tất ngay từ callback chạy trên chính consumer thread: nó có thể gây deadlock hoặc kẹt lifecycle.

Nên gửi yêu cầu quản lý lifecycle sang một scheduler/control thread có deadline, hoặc dùng API lifecycle không chặn phù hợp với version. Nếu chỉ muốn giảm workload, cân nhắc pause thay vì stop, nhưng pause sẽ thay đổi hành vi nhận record và cần một điều kiện resume rõ ràng.

## 15. Xây dựng một bộ theo dõi trạng thái idle

Một cách sử dụng thực tế là lưu trạng thái **observed idle** cho từng listener để dashboard hiển thị.

~~~text
Listener inventory-listener

ACTIVE
  |
  | Nhận ListenerContainerIdleEvent
  v
IDLE
  |
  | Vẫn nhận các idle events tiếp theo
  | Chỉ cập nhật thời gian, không mở incident mới
  |
  | Nhận ListenerContainerNoLongerIdleEvent
  v
ACTIVE
~~~

### 15.1. Idempotent event handling

Do idle event có thể phát lặp, code nên xử lý state transition idempotent:

- Lần đầu ACTIVE → IDLE: ghi thời điểm bắt đầu một giai đoạn idle.
- Các lần IDLE → IDLE: cập nhật last seen hoặc metric, không tạo nhiều alert giống nhau.
- Lần IDLE → ACTIVE: ghi nhận kết thúc và thời lượng idle.
- Nếu container stop/restart: kết thúc hoặc chuyển trạng thái sang STOPPED, không giữ dashboard ở IDLE mãi.

### 15.2. Ví dụ state tracker đơn giản

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class ListenerIdleTracker {

    private final ConcurrentMap<String, AtomicBoolean> idleByListener =
        new ConcurrentHashMap<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        AtomicBoolean state = idleByListener.computeIfAbsent(
            event.getListenerId(),
            ignored -> new AtomicBoolean(false)
        );

        if (state.compareAndSet(false, true)) {
            log.warn(
                "Listener entered idle state: {}",
                event.getListenerId()
            );
        }
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        AtomicBoolean state = idleByListener.computeIfAbsent(
            event.getListenerId(),
            ignored -> new AtomicBoolean(false)
        );

        if (state.compareAndSet(true, false)) {
            log.info(
                "Listener left idle state: {}",
                event.getListenerId()
            );
        }
    }
}
~~~

Đây là ví dụ chỉ trình bày state transition; biến `log` cần được khai báo với SLF4J như các ví dụ trước. Nó chưa xử lý đầy đủ container stopping, startup, rebalance, child listener identity, ApplicationContext shutdown hoặc multi-instance aggregation.

Một tracker production nên có timestamp, lifecycle state, pod identity và expiry/cleanup cho keys cũ. Nếu chuyển event delivery sang asynchronous, cần kiểm soát khả năng events đến không đúng thứ tự.

## 16. Dùng idle event để cảnh báo khi upstream ngừng phát

Một use case điển hình:

~~~text
Upstream order-service
      |
      v
Kafka topic orders.created
      |
      v
Spring Kafka orders-projection
      |
      v
ListenerContainerIdleEvent
      |
      v
Metric/alert: "Không có order events đủ lâu"
~~~

Chỉ dùng idle event để mở cảnh báo khi có **hợp đồng traffic rõ ràng**. Ví dụ:

- Ban ngày phải có ít nhất một order trong 5 phút.
- Cuối tuần có thể không có order trong 30 phút.
- Luồng heartbeat event phải có một event mỗi phút.
- Một số topic chỉ được publish trong batch job hàng đêm.

Một alert có thể cần thêm điều kiện:

1. Container đang running và đã được assign partition.
2. Không bị pause theo backpressure policy.
3. Topic thực sự được kỳ vọng có data trong khung giờ hiện tại.
4. Producer rate hoặc source queue depth cho thấy dữ liệu nên xuất hiện.
5. Consumer lag và broker health không chỉ ra lỗi khác.
6. Idle duration đã vượt SLO và có khoảng xác nhận để tránh alert nhiễu.

Nếu source topic có traffic tự nhiên không đều, thay vì gọi incident ngay, có thể coi idle là một diagnostic event hoặc một trạng thái dashboard.

## 17. Khi idle nhưng consumer lag đang tăng

Đây là tình huống cần điều tra kỹ vì topic có dữ liệu chưa đọc mà listener không nhận được record.

Các khả năng:

- Container đang paused vì backpressure.
- Consumer không có assignment trên partition đang có lag.
- Group vừa rebalance và chưa ổn định.
- Consumer đang bị lỗi deserialize trước khi message được dispatch theo đường thông thường.
- Consumer đang block, không poll đúng nhịp.
- Record chưa visible theo `read_committed` do transaction đang mở.
- Topic/partition hoặc group ID đang được quan sát sai.
- Hệ thống theo dõi lag có delay hoặc số liệu không cùng thời điểm.

Quy trình chẩn đoán:

1. Xác nhận listener container running.
2. Kiểm tra group ID, topic subscription và assignment.
3. Kiểm tra paused state và các `ConsumerPausedEvent`.
4. Đọc Kafka consumer client logs và các exception.
5. Kiểm tra poll latency, `max.poll.interval.ms` và heartbeat.
6. Đối chiếu log end offset, committed offset và last stable offset khi dùng transactions.
7. Kiểm tra deserialization errors và error handler.
8. Đối chiếu producer throughput và topic retention.

Không dùng idle event để tự động reset consumer offset, vì thao tác đó có thể bỏ qua hoặc replay dữ liệu nghiệp vụ ngoài ý muốn.

## 18. Khi không có idle event dù topic không có dữ liệu

Một số nguyên nhân:

- `idleEventInterval` chưa được cấu hình hoặc cấu hình nằm trên factory khác.
- Listener container chưa running hoặc chưa join group.
- Listener đang thực thi một operation lâu và chưa quay lại vòng poll để idle được đánh giá.
- Event listener được đăng ký sai ApplicationContext hoặc không phải Spring bean.
- Event filter đang bỏ qua listener/container ID tương ứng.
- Có một số record được nhận định kỳ đủ để reset idle clock.
- Phiên bản Spring Kafka có semantics khác về idle detection ban đầu hoặc per-partition tracking.
- Concurrent child khác đang nhận record, nên container tổng thể không idle như đã giả định.

Một cách điều tra:

~~~text
Kiểm tra config idle-event-interval
       |
       v
Xác nhận đúng listener container factory
       |
       v
Xác nhận container RUNNING, có assignment
       |
       v
Xác nhận @EventListener là Spring bean
       |
       v
Quan sát poll/record traffic và event logs
       |
       v
Đối chiếu idle interval thực tế và version
~~~

Không kết luận sự kiện bị mất chỉ vì một lời gọi callback chưa xuất hiện đúng thời điểm ngưỡng trên đồng hồ của test.

## 19. Event và consumer group rebalance

Khi consumer group rebalance, partition assignment có thể thay đổi. Từ đó:

- Một child consumer từng nhận nhiều record có thể nhận ít hoặc không có partition.
- Một child khác có thể nhận các partition vừa chuyển quyền và bắt đầu có data.
- Trạng thái idle trước rebalance có thể không còn mô tả đúng trạng thái traffic sau reassignment.
- Metadata partitions trong một event phản ánh assignment ở thời điểm publish event.

Nếu ứng dụng dùng idle event để đo sức khỏe một topic, cần **cập nhật cách tính sau assignment change**. Không lưu vĩnh viễn tập partition từ lần idle đầu tiên và coi nó là assignment hiện tại.

### 19.1. Idle khác rebalance

Rebalance có thể làm listener tạm không có record nhưng không phải một idle problem độc lập. Khi có idle event gần thời điểm deploy/scale, hãy đối chiếu:

- Member join/leave events.
- Partition revoked/assigned/lost callbacks.
- Consumer group coordinator errors.
- Pod restart và concurrency.
- Consumer lag theo partition.

### 19.2. Stop/restart trong lúc idle

Một container stop khi đang idle có thể không có sự kiện `ListenerContainerNoLongerIdleEvent`. Monitoring state nên dùng lifecycle events hoặc kiểm tra container running state để chuyển từ IDLE sang STOPPED/UNKNOWN.

Nếu ứng dụng restart, in-memory tracker cũ mất. Monitoring tập trung nên xem mỗi pod/process là một phiên khác, tránh so sánh state của instance cũ với instance mới như thể cùng một vòng đời liên tục.

## 20. Monitoring và metrics cho idle events

Những metrics hữu ích:

| Tín hiệu | Ý nghĩa |
|---|---|
| Idle event count | Số lần container báo idle |
| Idle state gauge | Listener/child hiện đang idle hay active |
| Idle duration | Thời gian một giai đoạn idle liên tục |
| Time since last received record | Khoảng vắng data theo listener/partition |
| No-longer-idle event count | Số lần container nhận record trở lại |
| Consumer lag | Backlog chưa tiêu thụ |
| Partition assignment count | Biết consumer có được giao partition không |
| Consumer poll rate/latency | Kiểm tra consumer vẫn poll |
| Heartbeat/rebalance events | Nhận biết membership bất ổn |
| Pause requested / observed | Phân biệt backpressure có chủ đích |
| Producer rate | Đánh giá upstream có tạo event không |
| Listener processing duration | Phân biệt idle với handler chạy quá lâu |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và instrumentation ứng dụng. Không mặc định Spring Kafka xuất sẵn một metric `idle_state` theo tên này; có thể tự xây một tracker và cung cấp gauge.

Nên dùng metric labels có cardinality hữu hạn như service, listener ID, topic, state và environment. Không dùng event ID, record key hoặc customer ID làm metric labels.

Nếu dashboard hiển thị pause duration/idle duration, cần nêu rõ:

- Idle tính từ **container-level hay partition-level**?
- Là thời gian kể từ event đầu tiên hay từ record cuối?
- Có tính các khoảng container stopped/rebalancing không?
- Đã aggregate trên tất cả pod hay chỉ một pod?

Nếu không có định nghĩa, biểu đồ “consumer idle” rất dễ gây hiểu nhầm.

## 21. Kiểm thử ListenerContainerIdleEvent

Nên kiểm thử trên Kafka test broker/cluster hoặc môi trường tích hợp có topic, consumer group riêng.

### 21.1. Kiểm thử không có dữ liệu

1. Tạo topic test và một listener container có `idleEventInterval` ngắn, ví dụ 1–2 giây.
2. Khởi động listener và đợi container thực sự có assignment.
3. Không gửi record mới.
4. Dùng `CountDownLatch`, Awaitility hoặc cơ chế chờ event có timeout.
5. Xác nhận nhận được `ListenerContainerIdleEvent` cho đúng listener ID.
6. Kiểm tra metadata assigned partitions và idle time.
7. Không viết test dựa vào một lần `Thread.sleep()` cố định rồi giả định event phải xuất hiện đúng miligiây.

### 21.2. Kiểm thử nhận record trở lại

1. Đợi container chuyển sang trạng thái idle.
2. Producer gửi một record hợp lệ.
3. Xác nhận `@KafkaListener` được gọi và xử lý thành công.
4. Quan sát `ListenerContainerNoLongerIdleEvent` ở version hỗ trợ.
5. Xác nhận state tracker chuyển từ IDLE sang ACTIVE.
6. Chờ đủ lâu không gửi thêm record và quan sát container idle trở lại.

### 21.3. Kiểm thử nhiều partition

1. Tạo topic có ít nhất hai partition.
2. Gửi record liên tục vào P0.
3. Không gửi record vào P1.
4. Bật `idlePartitionEventInterval`.
5. Xác nhận partition P1 có thể báo idle trong khi container vẫn nhận record từ P0.
6. Gửi record vào P1, quan sát partition no-longer-idle event.
7. Xác nhận dashboard không coi toàn container idle chỉ vì P1 idle.

### 21.4. Kiểm thử pause

1. Cho listener có assignment và đang nhận record.
2. Gọi `container.pause()`.
3. Quan sát `ConsumerPausedEvent` hoặc `isConsumerPaused()`.
4. Chờ một khoảng đủ để idle detection được xét.
5. Nếu xuất hiện idle event, xác nhận hệ thống không mở cảnh báo thiếu producer data khi pause là có chủ đích.
6. Resume và xác nhận record tiếp tục được xử lý.

### 21.5. Kiểm thử lifecycle/rebalance

1. Chạy hai consumer members trong cùng group.
2. Ghi nhận listener/container IDs và assignments.
3. Làm một member rời group theo cách kiểm soát trong test.
4. Xác nhận state tracker cập nhật khi assignment thay đổi.
5. Stop một container đang idle; đảm bảo dashboard không để state IDLE cũ mãi.
6. Khởi động lại và kiểm tra event/state thuộc đúng process lifecycle mới.

## 22. Đoạn mã kiểm thử bằng CountDownLatch

Một cách đơn giản để tránh test flaky là dùng listener nhận idle event rồi giảm latch:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class TestIdleEventProbe {

    private final CountDownLatch firstIdle =
        new CountDownLatch(1);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (event.getListenerId().startsWith("inventory-listener")) {
            firstIdle.countDown();
        }
    }

    public boolean awaitIdle() throws InterruptedException {
        return firstIdle.await(10, TimeUnit.SECONDS);
    }
}
~~~

Trong môi trường test, có thể đưa probe vào ApplicationContext và assertion rằng `awaitIdle()` trả về true sau khi listener được assign. Với concurrency, ID của child consumer có thể mang suffix; filter dùng prefix chỉ là ví dụ, cần xác nhận ID cụ thể.

Probe trên chỉ phục vụ một lượt test đơn giản. Nếu nhiều test chạy trong cùng context, cần reset/recreate latch theo vòng test, tránh việc một idle event từ test trước khiến test sau pass sai.

Không gọi `awaitIdle()` trên consumer thread; callback event chỉ nên gọi `countDown()` nhanh.

## 23. Những lỗi vận hành thường gặp

**Không cấu hình idleEventInterval nhưng chờ event:** container có thể không phát idle event vì ngưỡng chưa được bật.

**Đặt interval quá thấp:** các topic traffic thấp tạo nhiều event và log nhiễu.

**Coi idle là Kafka broker chết:** consumer có thể khỏe nhưng topic không có dữ liệu mới.

**Coi idle đồng nghĩa consumer paused:** pause là thao tác điều khiển; idle là hiện tượng không nhận record theo ngưỡng.

**Coi idle đồng nghĩa session timeout:** session timeout là group coordinator mất heartbeat, không phải listener không có data.

**Coi idle event đồng nghĩa offset đã commit:** idle không bảo đảm tiến độ commit hoặc xử lý side effect.

**Chỉ nghe một child và kết luận toàn group rỗi:** concurrent containers có thể có child còn hoạt động.

**Chỉ đo container idle khi cần partition idle:** một partition có thể đứng yên dù partition khác có record.

**Gọi KafkaConsumer từ async event handler:** vi phạm quy tắc thread ownership và có thể gây lỗi khó đoán.

**Dùng callback idle để thực thi HTTP/database dài:** có thể chặn consumer thread và tạo vấn đề poll interval.

**Stop container đồng bộ trên chính consumer thread:** có nguy cơ deadlock hoặc kẹt lifecycle.

**Gửi cảnh báo mỗi idle event:** event có thể lặp trong cùng một giai đoạn; cần state transition/deduplication.

**Quên phân biệt pod/instance:** application event chỉ có phạm vi JVM và cần aggregation ở monitoring.

**Không xử lý container stop/rebalance:** trạng thái IDLE cũ có thể tồn tại trên dashboard dù container đã dừng hoặc partition đã chuyển owner.

**Cho rằng một event NoLongerIdle chắc chắn phải xuất hiện:** stop, restart hoặc reassignment có thể làm vòng đời không kết thúc bằng event đó.

**Dùng idle event để tự động reset offsets:** nguy cơ bỏ qua/replay dữ liệu mà không có kiểm soát nghiệp vụ.

## 24. Quy trình điều tra khi listener idle bất thường

Một runbook thực tế:

1. Xác định environment, pod, listener ID, group ID và topic subscription.
2. Kiểm tra thời điểm idle bắt đầu, duration và các events đã nhận.
3. Xác nhận container còn running và có partition assignment.
4. Kiểm tra consumer paused state và các pause/resume events.
5. Đối chiếu committed offset, log end offset và consumer lag theo partition.
6. Kiểm tra producer throughput, upstream health và lịch phát dữ liệu kỳ vọng.
7. Xác định classic hay consumer group protocol và rebalance đang diễn ra không.
8. Kiểm tra poll rate, heartbeat, `max.poll.interval.ms` và lỗi Kafka client.
9. Xem serializer/deserializer và error handler nếu record không được dispatch.
10. Với `read_committed`, xem khả năng transaction đang mở ảnh hưởng visibility.
11. Nếu thiếu dữ liệu do upstream, điều tra producer pipeline; nếu consumer không nhận dù lag tăng, điều tra pause/assignment/poll.
12. Sau khi khắc phục, quan sát `ListenerContainerNoLongerIdleEvent` hoặc record processing thực tế.
13. Ghi nhận root cause, tác động SLA và điều kiện cảnh báo để giảm false positives.

Không tự động restart consumer chỉ vì thấy idle. Nếu topic thực sự không có dữ liệu, restart chỉ tạo group churn. Nếu downstream bị pause có chủ đích, restart có thể phá cơ chế backpressure. Hành động phải dựa vào nhiều tín hiệu được xác minh.

## 25. Nguyên tắc triển khai trong production

- Bật `idleEventInterval` trên đúng listener container factory hoặc property Spring Boot hiệu lực.
- Chọn ngưỡng dựa trên **traffic expectation**, không dùng một ngưỡng cho mọi topic.
- Dùng `@EventListener` để nhận `ListenerContainerIdleEvent` và `ListenerContainerNoLongerIdleEvent`; giữ callback ngắn.
- Phân biệt container-level idle với partition-level idle khi consumer sở hữu nhiều partitions.
- Với concurrency, theo dõi per-child listener ID và assigned partitions.
- Coi event là **quan sát**, không phải bằng chứng chắc chắn Kafka mất dữ liệu.
- Đối chiếu idle với consumer lag, producer rate, assignment, pause, poll/heartbeat và trạng thái broker.
- Không thao tác KafkaConsumer từ một async application event handler.
- Không block consumer thread bằng HTTP/database trong idle callback.
- Không stop đồng bộ container trên chính consumer thread.
- Dùng state transition và rate limit để tránh alert storm khi idle event lặp lại.
- Xử lý lifecycle/rebalance để stale idle state không kéo dài sau khi container dừng.
- Dùng Testcontainers/embedded broker hoặc môi trường Kafka test để xác nhận event timing và behavior.
- Không dùng idle event thay cho error handler, offset correctness, transaction hoặc business idempotency.

**Kết luận:** `ListenerContainerIdleEvent` cho phép ứng dụng Spring Kafka nhận biết listener container đã không nhận records trong khoảng thời gian được cấu hình. Kết hợp `ListenerContainerNoLongerIdleEvent`, ứng dụng có thể theo dõi sự chuyển đổi giữa trạng thái idle và active, đo idle duration và phát hiện các bất thường về luồng dữ liệu. Tuy nhiên, idle không đồng nghĩa paused, stopped, session timeout hoặc producer bị lỗi. Muốn vận hành đáng tin cậy, cần quan sát đúng container/partition, hiểu giới hạn của event và kết hợp metrics của Kafka group, producer, broker cùng downstream.
