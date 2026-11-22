# Lấy current position khi idle

## 1. Bài toán: consumer đang idle thì đang đứng ở offset nào?

Trong Spring Kafka, listener container có thể chạy bình thường nhưng không nhận thêm bản ghi từ Kafka trong một khoảng thời gian. Khi khoảng im lặng vượt ngưỡng cấu hình, Spring Kafka có thể phát `ListenerContainerIdleEvent`. Tại thời điểm đó, người vận hành thường muốn biết:

- Consumer hiện đang ở **offset nào của từng partition**?
- Consumer đã đọc hết dữ liệu hiện có hay vẫn còn backlog?
- Offset hiện tại có giống offset đã commit của consumer group không?
- Listener không được gọi vì topic không có dữ liệu, vì container bị pause, hay vì có sự cố?
- Có thể lấy vị trí trực tiếp từ `KafkaConsumer` của container hay cần một consumer mới?

Câu trả lời quan trọng là: **có thể dùng Kafka `Consumer.position(TopicPartition)` để lấy current position của consumer tại thời điểm nhận idle event**, miễn là lời gọi được thực hiện theo đúng quy tắc thread-safety của Kafka consumer.

Ví dụ:

~~~text
Topic orders, partition 2

offset:     100  101  102  103  104  105 ...
             |    |    |    |
consumer đã poll đến offset 104
current position = 104   (offset tiếp theo sẽ đọc/cấp ra)

committed offset = 101   (tiến độ đã được group lưu)

end offset = 110         (biên cuối tại thời điểm quan sát)
~~~

Ba giá trị **current position**, **committed offset** và **end offset** có ý nghĩa khác nhau. Bài học này giải thích cách đọc đúng từng giá trị, cách lấy chúng an toàn từ `ListenerContainerIdleEvent`, và cách dùng kết quả trong vận hành Spring Kafka Reliability Operations.

## 2. Hiểu chính xác current position

### 2.1. Kafka consumer position là offset tiếp theo

Kafka `Consumer.position(tp)` trả về vị trí hiện tại của consumer ở một `TopicPartition` được gán. Theo semantics của Kafka client, đó là **offset của record tiếp theo sẽ được trả ra** từ partition đó.

Khi `poll()` trả một số record, position có thể tăng đến sau các record đã được fetch, ngay cả khi ứng dụng chưa xử lý/commit xong toàn bộ những record đó.

Ví dụ:

~~~text
poll() trả về records ở offsets 30, 31, 32

Trước poll:
  position(orders-0) = 30

Sau poll:
  position(orders-0) = 33

Listener đã xử lý:
  Có thể chỉ xử lý xong offset 30

Committed offset:
  Có thể vẫn là 30 hoặc một giá trị khác
~~~

Vì vậy không được gọi current position là "record nghiệp vụ đã xử lý thành công cuối cùng" nếu không có cơ chế kiểm chứng riêng.

### 2.2. Position tính theo từng partition

Không có một current position duy nhất cho cả consumer group. Kafka offset thuộc về **topic-partition**, nên phải lấy riêng:

~~~text
orders-0: position 120
orders-1: position 85
orders-2: position 406
~~~

Nếu một listener container có concurrency lớn hơn 1, mỗi child consumer có thể sở hữu tập partition khác nhau. Position của child A không đại diện cho toàn bộ các child hoặc toàn group.

### 2.3. Position khác offset của record cuối

Giả sử record cuối consumer thấy có offset 49. Position thường là offset tiếp theo, ví dụ 50. Không nên trừ 1 một cách máy móc rồi kết luận offset 49 luôn tồn tại: compacted topic, aborted transactional records, control batches hoặc các khoảng offset bị bỏ có thể làm log không có record user-visible ở từng offset liên tiếp.

Position là một **mốc di chuyển trong Kafka log**, không phải số lượng record đã xử lý.

## 3. Phân biệt position, committed và end offset

| Khái niệm | Lấy từ đâu | Ý nghĩa | Có đồng nghĩa xử lý nghiệp vụ thành công? |
|---|---|---|---|
| Current position | `consumer.position(tp)` | Offset kế tiếp Kafka consumer có thể fetch/cấp ra | Không |
| Committed offset | `consumer.committed(...)` hoặc group offset | Vị trí group đã ghi nhận để resume khi cần | Chỉ nếu ack/commit gắn đúng với kết quả xử lý |
| End offset | `consumer.endOffsets(...)` | Biên cuối của dữ liệu có thể đọc theo isolation semantics | Không |
| Beginning offset | `consumer.beginningOffsets(...)` | Biên đầu còn đọc được của partition | Không |
| Last record processed | Business tracking/application state | Record cuối listener đã xử lý thành công theo hợp đồng nghiệp vụ | Có thể, nếu được lưu đáng tin cậy |
| Last stable offset (LSO) | Kafka transactional visibility | Biên đọc ổn định cho `read_committed` khi có transaction đang mở | Không |

### 3.1. Ví dụ cùng lúc ba offset

~~~text
orders-0
  beginning offset = 50
  committed offset = 80
  current position = 88
  end offset       = 100
~~~

Cách hiểu:

- Nếu một member khác tiếp quản partition và group tiếp tục từ committed offset 80, record bắt đầu từ vùng offset 80 có thể được giao lại theo log còn lưu.
- Consumer đang sống có position 88, nghĩa là vòng poll đã tiến đến biên đó; không có bảo đảm tất cả record đến offset 87 đã hoàn thành side effect.
- End offset 100 cho thấy log còn dữ liệu phía sau position, nếu các offset và isolation cho phép consumer đọc.
- Khoảng cách `end - position = 12` không phải một thước đo chính xác "12 record chưa xử lý". Đó là khoảng cách **theo đơn vị offset**, không nhất thiết bằng số record, và giá trị end là một snapshot có thể đổi.

### 3.2. Tại sao committed offset có thể nhỏ hơn position?

Trường hợp phổ biến là consumer đã nhận một batch qua `poll()` nhưng listener chưa hoàn tất hoặc container chưa commit offset. Với `AckMode.BATCH` hoặc manual acknowledgment, commit có thể diễn ra sau khi nhiều records được xử lý.

Ngay cả khi container đã chuyển record đến listener, database transaction và Kafka offset commit vẫn là hai thao tác riêng. Position không thay thế committed offset khi cần điều tra redelivery sau crash.

### 3.3. Tại sao position có thể đúng bằng end offset?

Khi consumer đã bắt kịp dữ liệu có thể đọc của partition, hai giá trị có thể bằng nhau:

~~~text
position = 180
end      = 180
~~~

Nếu không có producer ghi mới, consumer có thể tiếp tục poll trả về không có record và listener container phát idle event sau một thời gian.

Tuy vậy, không suy ra "hệ thống khỏe" chỉ từ hai giá trị bằng nhau. Cần xác nhận consumer còn được assign partition đúng, không bị pause, topic đúng và dữ liệu upstream đang được kỳ vọng hay không.

## 4. ListenerContainerIdleEvent giúp lấy position thế nào?

Spring Kafka có `ListenerContainerIdleEvent` để báo listener container đã không nhận record trong khoảng thời gian cấu hình. Event cung cấp metadata về listener và các partition liên quan; với những phiên bản có API tương ứng, event còn cung cấp tham chiếu `Consumer` qua `getConsumer()`.

Luồng mong muốn:

~~~mermaid
sequenceDiagram
    participant K as Kafka broker
    participant C as Listener container
    participant E as Idle event listener
    participant P as Kafka Consumer

    C->>K: poll()
    K-->>C: Không có record mới
    C->>K: poll() tiếp
    K-->>C: Không có record mới
    Note over C: Thời gian idle vượt ngưỡng
    C->>E: Publish ListenerContainerIdleEvent
    E->>P: position(topic-partition)
    P-->>E: Current position
    E->>E: Ghi log/metric ngắn
    Note over C: Container tiếp tục poll bình thường
~~~

Điểm quyết định là **thread thực thi callback**. Kafka `Consumer` không thread-safe; chỉ gọi `position()` trên consumer của container khi callback chạy **đồng bộ trên consumer thread phù hợp**. Không chuyển object `Consumer` lấy từ idle event sang một executor, REST thread hay scheduler rồi gọi sau.

Các event khác như `ListenerContainerNoLongerIdleEvent` phản ánh container có record trở lại. Chúng hữu ích để kết thúc trạng thái idle trên dashboard nhưng không thay thế việc lấy position thực tế.

## 5. Bật idle event trong Spring Boot

Có thể cấu hình Spring Boot listener interval:

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

Ở các Spring Boot versions hỗ trợ property trên, `idle-event-interval: 30s` cấu hình ngưỡng im lặng của listener container.

Cần phân biệt:

- `idle-event-interval`: ngưỡng Spring Kafka dùng để phát idle application event.
- `session.timeout.ms`: ngưỡng coordinator dùng để xác định consumer mất heartbeat trong classic group protocol.
- `max.poll.interval.ms`: giới hạn thời gian giữa các lần poll hợp lệ.
- `auto.offset.reset`: chính sách chọn offset khởi đầu khi không có committed offset hợp lệ.

Chúng là các cơ chế riêng. Không tăng session timeout chỉ vì muốn nhận `ListenerContainerIdleEvent` sau 60 giây.

Nếu ứng dụng tự cấu hình container factory, cần bảo đảm factory được listener dùng thực sự có idle event interval. Property trong YAML không chắc đã được áp dụng khi custom factory bỏ qua cấu hình Boot.

## 6. Bật idle event trên container factory

Cấu hình trực tiếp qua `ContainerProperties`:

~~~java
@Configuration
public class InventoryKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, InventoryChanged>
            inventoryListenerFactory(
                ConsumerFactory<String, InventoryChanged> consumerFactory
            ) {
        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, InventoryChanged>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setIdleEventInterval(30_000L);

        return factory;
    }
}
~~~

Listener được gắn với factory này:

~~~java
@Component
public class InventoryListener {

    @KafkaListener(
        id = "inventory-listener",
        topics = "inventory.changed",
        groupId = "inventory-projection",
        containerFactory = "inventoryListenerFactory"
    )
    public void onInventoryChanged(InventoryChanged event) {
        inventoryService.applyIdempotently(event);
    }
}
~~~

`InventoryChanged` và `inventoryService` là kiểu và bean minh họa của ứng dụng. Dự án cần serializer/deserializer hoặc message converter phù hợp.

Từ góc độ vận hành, muốn quan sát current position tại idle event thì trước hết phải biết container nào đang phát event và partition nào đã được gán cho consumer của container đó.

## 7. Mẫu Java: đọc current position ngay trong idle callback

Đây là ví dụ trọng tâm:

~~~java
import java.util.Collection;
import java.util.Set;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaIdlePositionLogger {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaIdlePositionLogger.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        Consumer<?, ?> consumer = event.getConsumer();

        if (consumer == null) {
            log.debug("Idle event has no consumer reference: {}",
                event.getListenerId());
            return;
        }

        Set<TopicPartition> assigned = consumer.assignment();
        Collection<TopicPartition> partitions = event.getTopicPartitions();

        if (partitions == null || partitions.isEmpty()) {
            log.debug(
                "Idle with no partitions: listener={}",
                event.getListenerId()
            );
            return;
        }

        for (TopicPartition partition : partitions) {
            if (!assigned.contains(partition)) {
                continue;
            }

            long position = consumer.position(partition);

            log.info(
                "Listener idle: listener={}, topic={}, partition={}, " +
                "currentPosition={}, idleMs={}",
                event.getListenerId(),
                partition.topic(),
                partition.partition(),
                position,
                event.getIdleTime()
            );
        }
    }
}
~~~

Ví dụ dùng `ListenerContainerIdleEvent.getConsumer()`, `getTopicPartitions()`, `getListenerId()` và `getIdleTime()` theo Spring Kafka API tương ứng. Nếu ứng dụng dùng phiên bản khác, cần đối chiếu accessors cụ thể trong dependency hiện hành.

Đây là **mẫu đọc ngay trong event callback đồng bộ**. Đừng sửa thành:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    executor.submit(() -> {
        // KHÔNG AN TOÀN: gọi Kafka Consumer từ thread khác!
        event.getConsumer().position(someTopicPartition);
    });
}
~~~

Kafka consumer client không cho phép ứng dụng truy cập các API thông thường của cùng consumer một cách tùy ý từ nhiều thread.

### 7.1. Vì sao kiểm tra assignment?

`position(tp)` chỉ có ý nghĩa đối với partition mà consumer hiện được assign. Trong lúc group rebalance hoặc thay đổi assignment, một partition có thể không còn thuộc consumer đó.

`consumer.assignment()` phản ánh assignment local tại thời điểm callback. Kiểm tra assignment giúp tránh gọi position cho partition không thuộc quyền sở hữu của consumer đang quan sát.

### 7.2. Callback cần ngắn

`position(tp)` thường có thể trả về từ trạng thái client, nhưng có những trường hợp consumer cần xác định vị trí bằng metadata/offset lookup, nên API có thể chặn và thất bại. Đọc quá nhiều partition hoặc thực hiện thêm các request Kafka nặng trong event callback có thể làm chậm vòng poll.

Không nên gọi database, HTTP service hoặc tính toán lớn từ callback chỉ để lưu snapshot offset. Hãy ghi log/metric nhẹ rồi để một hệ thống monitoring bất đồng bộ xử lý **giá trị snapshot**, không truyền tham chiếu KafkaConsumer qua thread.

### 7.3. Không lưu Consumer lâu dài

Không đưa `event.getConsumer()` vào singleton field, cache hoặc static holder để REST endpoint có thể gọi `position()` sau đó. Consumer lifecycle/assignment có thể thay đổi và truy cập từ thread khác là không an toàn.

Muốn hiển thị current position từ một API, có thể cập nhật một **snapshot thread-safe** trong idle callback rồi cho API đọc snapshot đó. Snapshot cần có timestamp và listener identity để người xem biết dữ liệu có còn mới hay không.

## 8. Ví dụ lưu snapshot position để hệ thống khác đọc

Một service quan sát có thể lưu dữ liệu đơn giản trong `ConcurrentHashMap`. Việc đọc `consumer.position()` vẫn diễn ra trên thread event đồng bộ; các thread khác chỉ đọc **giá trị đã chụp**, không dùng KafkaConsumer trực tiếp.

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class IdlePositionSnapshotStore {

    public record Snapshot(
        String listenerId,
        TopicPartition partition,
        long nextOffset,
        Instant observedAt
    ) {}

    private final ConcurrentMap<String, Snapshot> snapshots =
        new ConcurrentHashMap<>();

    @EventListener
    public void recordIdlePosition(ListenerContainerIdleEvent event) {
        Consumer<?, ?> consumer = event.getConsumer();

        if (consumer == null || event.getTopicPartitions() == null) {
            return;
        }

        for (TopicPartition partition : event.getTopicPartitions()) {
            if (!consumer.assignment().contains(partition)) {
                continue;
            }

            long position = consumer.position(partition);

            Snapshot snapshot = new Snapshot(
                event.getListenerId(),
                partition,
                position,
                Instant.now()
            );

            String key = event.getListenerId() + "/" +
                partition.topic() + "/" + partition.partition();

            snapshots.put(key, snapshot);
        }
    }

    public Map<String, Snapshot> currentSnapshots() {
        return Map.copyOf(snapshots);
    }
}
~~~

`Snapshot` là immutable record, phù hợp để chia sẻ giữa thread đọc vị trí và thread đọc kết quả. Nhưng nó **không phải trạng thái position real-time**: đây là giá trị ghi lại **tại thời điểm idle event cuối cùng**.

Với production cần bổ sung:

- TTL hoặc cleanup khi listener container stopped.
- Xóa hoặc đánh dấu stale khi partition bị revoke/lost.
- Phân biệt các child consumers và các pod.
- Metadata về assignment, pause và lifecycle.
- Giới hạn số snapshots nếu topic/partition set thay đổi nhiều.
- Rate-limit event logging nếu idle event được phát lặp lại liên tục.

Không gắn KafkaConsumer object vào snapshot; chỉ lưu các số liệu và định danh đã đọc.

## 9. Lấy position và committed offset có gì khác?

Kafka consumer cung cấp API committed offset. Tùy Kafka client version, các overload có thể là:

~~~java
Map<TopicPartition, OffsetAndMetadata> committed =
    consumer.committed(Set.of(partition));

OffsetAndMetadata metadata = committed.get(partition);

Long committedNextOffset =
    metadata == null ? null : metadata.offset();
~~~

Tuy nhiên, `consumer.committed(...)` có thể thực hiện network request. **Không nên gọi API này cho mọi partition ở mọi idle event chỉ để ghi monitoring**, nhất là khi số consumer/partition lớn.

Một thiết kế vận hành tốt hơn:

- Trong idle callback, đọc `position(tp)` nhanh và xuất snapshot.
- Lấy committed offsets định kỳ qua một kênh monitoring độc lập hoặc Kafka group offset metrics/CLI.
- Đối chiếu dữ liệu bằng cùng topic-partition và timestamp gần nhau.
- Nếu thực sự phải đọc committed offset trong callback, giới hạn tần suất, timeout và số partition, và hiểu rằng callback có thể chặn consumer thread.

### 9.1. Lấy position không đồng nghĩa commit offset

Không bao giờ viết:

~~~java
long position = consumer.position(partition);

// Sai về mặt ý nghĩa nghiệp vụ:
// Không commit thẳng position chỉ vì consumer idle.
consumer.commitSync(
    Map.of(partition, new OffsetAndMetadata(position))
);
~~~

Đoạn trên là ví dụ **không nên làm**. Position có thể đi trước record đã hoàn tất xử lý, nên commit nó mà không kiểm chứng có thể khiến consumer group bỏ qua những record chưa được lưu bền vững.

Nếu listener container đang quản lý acknowledgment theo `AckMode.RECORD`, `BATCH` hoặc manual ack, ứng dụng không nên can thiệp commit offset từ idle callback mà không có thiết kế offset ownership rất rõ ràng.

### 9.2. Committed offset có thể null

Nếu group chưa từng commit offset cho partition, `committed(...)` có thể trả về null cho partition đó. Khi consumer khởi động, position có thể được chọn từ `auto.offset.reset` (ví dụ earliest/latest) khi không có committed offset hợp lệ.

Do đó, `position=100` không chứng minh group đã commit 100; nó có thể chỉ là điểm bắt đầu được chọn khi consumer join group.

## 10. Lấy beginning và end offsets: khi nào có ích?

Nếu muốn biết consumer đã bắt kịp log hay chưa, có thể lấy các boundaries:

~~~java
Set<TopicPartition> partitions = consumer.assignment();

Map<TopicPartition, Long> beginnings =
    consumer.beginningOffsets(partitions);

Map<TopicPartition, Long> ends =
    consumer.endOffsets(partitions);
~~~

Những lời gọi này có thể liên hệ broker để truy vấn offsets. Không nên đặt chúng trên đường hot path của consumer hoặc gọi lặp với tần suất cao trong callback event.

### 10.1. End offset không phải last processed offset

`endOffsets` trả một biên cuối của dữ liệu Kafka tùy isolation level. Nó không cho biết record cuối cùng của listener đã xử lý thành công hay chưa.

### 10.2. Isolation read_committed

Nếu consumer dùng `isolation.level=read_committed`, end offset có thể bị giới hạn bởi **last stable offset (LSO)** khi có transaction Kafka chưa kết thúc. Một producer transaction đang mở có thể làm consumer không thấy các record nằm phía sau LSO dù Kafka log vật lý đã có dữ liệu.

Vì vậy, khi current position bằng end offset của consumer `read_committed`, cần hiểu đó là biên đọc có thể quan sát dưới isolation đã chọn, không nhất thiết là high watermark/end vật lý tuyệt đối của log.

### 10.3. Offset gap không đồng nghĩa số message

Với compacted topic hoặc giao thức transactions, các offsets có thể có khoảng trống. Phép trừ `end - position` chỉ cho **offset distance**, không bảo đảm đó là số lượng business messages chưa xử lý.

### 10.4. Khi end thay đổi trong lúc đo

Kafka producer có thể tiếp tục gửi event trong lúc hệ thống đọc position và end offset. Hai số đo không phải một snapshot nguyên tử. Do đó, một phép tính lag tại một thời điểm chỉ là quan sát gần đúng, cần timestamp và polling cadence nhất quán.

## 11. Có thể tính lag từ current position không?

Có thể tính một **khoảng cách tạm thời**:

~~~text
fetch distance = end offset - current position
~~~

Ví dụ:

~~~text
position = 1.250
end      = 1.300
distance = 50 offset units
~~~

Nhưng **consumer group lag** thường được tính từ committed offset:

~~~text
group lag = log end offset - committed offset
~~~

Hai phép đo trả lời hai câu hỏi khác nhau.

| Quan sát | Công thức đơn giản | Diễn giải |
|---|---|---|
| Fetch distance | `end - position` | Consumer local còn cách biên có thể đọc bao xa |
| Group offset lag | `end - committed` | Group còn cách biên log bao xa theo committed progress |
| Uncommitted distance | `position - committed` | Consumer đã poll tiến xa hơn mức đã commit bao nhiêu offset |
| Business work backlog | Nguồn dữ liệu nghiệp vụ riêng | Bao nhiêu event thực sự chưa hoàn tất side effect |

**Cảnh báo:** Các công thức chỉ là khoảng cách theo offset, có thể không trùng số records; chúng cũng không tự phản ánh batch in-flight, transactions, compaction, filtering và assignment churn.

Nếu cần cảnh báo production, ưu tiên Kafka consumer group lag/consumer metrics chính thức kết hợp listener processing metrics, thay vì xây một “lag” duy nhất từ position trong idle callback.

## 12. Vì sao idle event xuất hiện khi position chưa bằng end?

Một số khả năng:

1. Consumer bị pause ở container hoặc partition, nên vẫn poll nhưng không trả thêm dữ liệu từ partition paused.
2. Có record bị giữ lại vì retry, backoff, error handling hoặc container đang ở trạng thái chuyển tiếp.
3. Consumer vừa rebalance, assignment hoặc position thay đổi gần thời điểm quan sát.
4. End offset được đo ở thời điểm khác với current position; producer có thể vừa gửi thêm records.
5. Có mismatch giữa topic-partition/consumer instance của dữ liệu đo.
6. Isolation `read_committed` hoặc transaction đang mở làm visibility khác so với dữ liệu log-end từ công cụ khác.
7. Event consumer được xem là idle theo phạm vi container, còn một partition hoặc consumer khác đang có backlog.

Không nên kết luận “Kafka mất record” khi chỉ thấy `position < end`. Cần xem container assignment, poll, pause, retry, committed offsets và thời điểm đo.

### 12.1. Pause có chủ đích

Nếu hệ thống dùng `container.pause()` để backpressure, consumer tiếp tục polling để giữ membership nhưng không nhận thêm records từ các partition paused. Idle event có thể xuất hiện tùy container/version trong lúc đó.

Khi đánh giá current position, kiểm tra `isPauseRequested()`, `isConsumerPaused()` hoặc các `ConsumerPausedEvent`/`ConsumerResumedEvent` tương ứng.

### 12.2. Partition không có assignment

Nếu một child consumer không sở hữu partition, không lấy `position(tp)` từ child đó. Nếu số consumer lớn hơn số partitions, một số child có thể không được assign dữ liệu; việc chúng không nhận record không chứng minh topic thiếu traffic.

### 12.3. Data chưa visible do Kafka transactions

Khi consumer dùng `read_committed`, một transaction chưa hoàn tất có thể khiến record chưa visible. Consumer có thể idle theo chiều nhận record nhưng producer thực sự vẫn ghi. Cần đối chiếu LSO và transaction monitoring, không tự seek hoặc reset offset để “vượt qua” dữ liệu chưa ổn định.

## 13. Tương tác với AckMode trong Spring Kafka

Offset ownership phụ thuộc cách container commit.

| AckMode | Ý nghĩa liên quan position và commit |
|---|---|
| `RECORD` | Container commit sau từng record listener xử lý thành công theo policy |
| `BATCH` | Container commit theo tiến độ records của một poll/batch sau xử lý |
| `TIME` | Tiến độ commit có thể được trì hoãn theo thời gian và điều kiện container |
| `COUNT` | Commit theo số record xử lý và điều kiện cấu hình |
| `COUNT_TIME` | Kết hợp điều kiện count/time |
| `MANUAL` | Listener quyết định acknowledge; commit theo semantics container |
| `MANUAL_IMMEDIATE` | Acknowledge có thể yêu cầu commit ngay theo điều kiện/cách gọi phù hợp |

Current position có thể lớn hơn committed offset trong tất cả các mode nếu consumer đã poll record mà chưa đến thời điểm commit. Bởi vậy không thay thế container-managed acknowledgment bằng cách đọc position và commit thủ công trong idle callback.

### 13.1. Manual ack

Ví dụ:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    orderService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
~~~

Chỉ acknowledge sau side effect bền vững. Đọc position trong idle event không chứng minh listener đã gọi `acknowledge()` đúng mọi record.

### 13.2. Giao dịch database

Nếu listener ghi database, một crash có thể xảy ra sau DB commit nhưng trước Kafka offset commit. Khi record được giao lại, position có thể thay đổi nhưng event ID/inbox mới quyết định tránh duplicate side effect.

Do đó, "current position" là **thông tin về Kafka consumer**, không phải transaction log của database.

## 14. Consumer position với batch listener

Batch listener nhận nhiều record trong một lần gọi:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    orderService.processBatch(records);
}
~~~

Một batch có thể gồm record từ nhiều partitions. Khi `poll()` trả batch, consumer position có thể tiến qua nhiều offsets, dù business method chưa xử lý xong batch.

Ví dụ:

~~~text
Một poll trả:
  orders-0: offsets 10, 11, 12
  orders-1: offsets 40, 41

Ngay sau poll:
  position(orders-0) có thể là 13
  position(orders-1) có thể là 42

Listener vẫn đang chạy:
  processBatch chưa commit database
~~~

Nếu batch lỗi và được retry, không được dùng position để suy ra phần nào đã xử lý thành công. Với `BatchListenerFailedException`, error handler có thể xử lý theo index; với lỗi chung, có thể retry toàn batch. Cần theo dõi business state và commit riêng từng partition.

Khi container phát idle event sau nhiều poll không nhận record, position snapshot chỉ mô tả vị trí hiện tại của consumer, không phải bằng chứng tất cả side effect của batch trước đã hoàn tất.

## 15. Read current position khi có retry hoặc seek

Spring Kafka error handler có thể thực hiện seek về offset của record lỗi hoặc giữ record để resubmit mà không seek tùy cấu hình và phiên bản.

### 15.1. Retry bằng seek

Giả sử listener xử lý offset 90 thất bại; error handler seek về 90 để nhận lại record:

~~~text
Trước lỗi:
  position = 94 vì poll đã nhận offsets 90..93

Sau error handler seek về offset 90:
  position có thể trở thành 90

Sau khi retry hoàn tất:
  position lại tiến theo poll
~~~

Position **không bắt buộc tăng đơn điệu** qua toàn bộ vòng đời consumer. Application hoặc framework có thể `seek()` về offset cũ.

### 15.2. Retain và resubmit

Với một số cấu hình error handler như `seekAfterError=false`, container có thể giữ records chưa xử lý và đưa chúng lại cho listener mà không gọi seek thực sự cho từng record. Trong lúc đó, KafkaConsumer position có thể đã tiến sau các records đã poll, còn container vẫn đang giữ workload cần retry.

Do đó, chỉ nhìn `consumer.position(tp)` không phản ánh đầy đủ backlog **đang nằm trong listener container**. Muốn điều tra retry, cần đối chiếu retry attempts, record offsets, error handler state và metrics.

### 15.3. Recovery/DLT

Khi record không xử lý được và được gửi sang DLT thành công, container có thể tiến offset theo recovery/ack policy. Nếu DLT publish thất bại, record có thể cần retry recovery.

Current position tại idle event không chứng minh recoverer đã publish DLT thành công. Cần theo dõi DLT send result và committed offsets riêng.

## 16. Transactional listener và read_committed

Kafka transaction có thể gộp output Kafka records và source consumer offsets trong consume–process–produce.

~~~text
Input Kafka record
      |
      v
Transactional listener container
      |
      +-- KafkaTemplate.send(output)
      +-- Send source offset to transaction
      |
      v
Commit Kafka transaction
~~~

Khi transaction abort, source offset có thể chưa được commit trong transaction đó, và input record có thể được redeliver. Consumer position vẫn có thể đã tiến hoặc bị seek theo rollback processing.

Nếu transaction chưa commit, downstream `read_committed` consumer không thấy output aborted hoặc in-flight. Khi theo dõi vị trí, không nhầm fetch position với **transaction outcome**.

### 16.1. Last stable offset

Trong `read_committed` mode, consumer có thể chỉ đọc đến LSO. Một transaction đang mở có thể trì hoãn visibility của records về sau, khiến current position bằng end offset theo isolation view trong khi log vật lý có dữ liệu phía sau.

Nếu vận hành gặp idle bất thường ở topic transactional, hãy kiểm tra transaction durations, abort rates, producer fencing và LSO-related lag trước khi thay đổi consumer offset.

### 16.2. Kafka exactly-once không có nghĩa listener chỉ chạy một lần

Khi transaction abort/rebalance, listener có thể xử lý lại record. Kafka EOS bảo vệ phạm vi output + source offsets trong transaction được cấu hình đúng, không tự ngăn duplicate side effect database/HTTP.

Đừng dùng current position như một phép chứng minh end-to-end exactly-once.

## 17. Các event khác cần phân biệt

| Event/hiện tượng | Điều nó phản ánh | Quan hệ với current position |
|---|---|---|
| `ListenerContainerIdleEvent` | Không nhận record đủ khoảng idle | Có thể chụp position trong callback đồng bộ |
| `ListenerContainerNoLongerIdleEvent` | Có record trở lại sau idle | Position có thể tiếp tục tăng |
| `ListenerContainerPartitionIdleEvent` | Partition cụ thể im lặng | Có thể cần position của đúng partition đó |
| `ConsumerPausedEvent` | Pause đã thực thi | Position có thể đứng yên dù producer còn ghi |
| `ConsumerResumedEvent` | Resume đã thực thi | Consumer có thể tiếp tục poll/dispatch |
| `NonResponsiveConsumerEvent` | Consumer poll không phản hồi theo giám sát | Không nên suy ra có thể truy vấn consumer như khi idle bình thường |
| Rebalance/partition revoked | Assignment thay đổi | Position cũ có thể không còn thuộc consumer |
| Container stopped | Consumer lifecycle dừng | Snapshot position cũ có thể bị stale |

**Listener idle** và **consumer non-responsive** là hai vấn đề khác nhau. Idle có thể rất lành mạnh: consumer liên tục poll nhưng topic không có record. Non-responsive có thể là poll bị block hoặc consumer không đáp ứng đúng kỳ.

Không coi event nhận được là lý do tự động restart container hoặc reset offset. Điều tra nguồn dữ liệu, assignment và health trước.

## 18. Lấy position khi một partition idle nhưng container không idle

Một consumer có thể sở hữu nhiều partitions:

~~~text
inventory-0: có 100 records/phút
inventory-1: có 0 records/phút
inventory-2: có 30 records/phút
~~~

Vì container vẫn nhận record từ P0/P2, nó có thể **không phát container-level idle event**, dù P1 không có record. Trong các Spring Kafka versions hỗ trợ, có thể cấu hình `idlePartitionEventInterval` để quan sát partition-level idle riêng.

~~~java
factory.getContainerProperties()
    .setIdleEventInterval(30_000L);

factory.getContainerProperties()
    .setIdlePartitionEventInterval(60_000L);
~~~

`ListenerContainerPartitionIdleEvent` phản ánh partition-level idleness. Khi muốn lấy current position cho partition cụ thể, cần lấy đúng Kafka consumer của container/child đang sở hữu partition ấy theo API/version được hỗ trợ và thực hiện truy cập theo đúng consumer thread.

Không giả định một event cho partition P1 đồng nghĩa current position của P0/P2 cũng đứng yên.

### 18.1. Dùng offset cho partition-level SLA

Nếu một partition theo thiết kế phải nhận event mỗi phút, partition idle event cùng position/end offset có thể giúp phát hiện producer không phân phối đều hoặc partitioner bị lệch.

Nhưng topic có key-based partitioning thường không có traffic đều tuyệt đối giữa các partitions. Một partition không có dữ liệu trong một khoảng thời gian có thể hoàn toàn hợp lệ; cần baseline riêng.

## 19. Theo dõi nhiều instance và concurrent containers

Giả sử ứng dụng chạy ba pod, mỗi pod `concurrency=2`; tổng cộng có thể có sáu consumer members:

~~~text
Group orders-service

Pod A:
  child A-0 -> orders-0
  child A-1 -> orders-1

Pod B:
  child B-0 -> orders-2
  child B-1 -> orders-3

Pod C:
  child C-0 -> orders-4
  child C-1 -> orders-5
~~~

Khi child A-0 phát idle event, chỉ có thể đọc position của các partitions **đang được gán cho A-0**. Không có một KafkaConsumer duy nhất để đọc current position của toàn group.

Nếu cần dashboard tập trung, mỗi JVM publish **snapshot data** sang monitoring, không publish tham chiếu KafkaConsumer:

~~~text
pod_id, listener_id, topic, partition, position, observed_at

pod-a, orders-0, orders, 0, 120, 2026-...
pod-a, orders-1, orders, 1,  87, 2026-...
pod-b, orders-0, orders, 2, 302, 2026-...
~~~

Khi rebalance xảy ra, partition có thể chuyển owner; snapshot của owner cũ phải được đánh dấu stale. Có thể lưu thêm group generation/assignment epoch nếu hạ tầng quan sát hỗ trợ, nhưng không xây logic offset trên một snapshot cũ.

### 19.1. Listener ID

Event có listener/container ID; với concurrent child containers, ID có thể có suffix riêng. Đừng hard-code giả định mọi child dùng cùng ID hay mọi version sinh suffix theo cùng format.

### 19.2. Không trộn nhiều consumer groups

Hai group khác nhau có thể ở hai positions khác nhau cho cùng một topic-partition. Mọi snapshot cần có `group.id` hoặc consumer group identity rõ ràng; nếu không, dashboard có thể hiểu sai position của group khác thành của group đang cần điều tra.

## 20. Monitoring: snapshot nhẹ, metric an toàn

Những dữ liệu có ích khi nhận idle event:

| Trường | Lý do |
|---|---|
| Listener/container ID | Biết event thuộc listener nào |
| Pod/instance ID | Khoanh vùng JVM phát event |
| Group ID | Phân biệt các tiến độ tiêu thụ độc lập |
| Topic và partition | Offset luôn thuộc từng partition |
| Current position | Offset kế tiếp của consumer tại thời điểm quan sát |
| Idle duration | Khoảng im lặng đã ghi nhận |
| Observed timestamp | Phân biệt snapshot mới và stale |
| Paused state | Biết ngừng fetch có chủ đích hay không |
| Assignment | Xác nhận partition thuộc consumer nào |
| Committed offset | Tiến độ được group lưu; thu thập riêng khi phù hợp |
| End offset/LSO | Biên dữ liệu có thể đọc |
| Consumer group lag | Backlog từ committed offsets |
| Listener processing latency | Phát hiện xử lý quá chậm |
| Retry/recovery count | Hiểu record có đang bị retry/retained |
| Rebalance events | Phát hiện ownership thay đổi |

### 20.1. Không tạo alert cho mọi idle event

Nếu `idleEventInterval=10s` và topic không có dữ liệu trong 30 phút, container có thể phát nhiều events. Gửi cảnh báo cho từng event tạo alert storm.

Nên dùng state machine ACTIVE → IDLE → ACTIVE; chỉ alert khi idle duration vượt ngưỡng nghiệp vụ **và** hệ thống thực sự kỳ vọng có record.

### 20.2. Không dùng offset làm label có cardinality cao

Metric labels nên gồm service, listener, topic và outcome có tập giá trị hữu hạn. Position thay đổi liên tục; không dùng offset hoặc event ID làm label.

Có thể dùng gauge cho position với label topic/partition nếu số partition có thể kiểm soát, hoặc dùng structured logs để tránh cardinality quá lớn ở cluster có hàng chục nghìn partitions.

### 20.3. Snapshot không phải phép đo đồng thời

Nếu lấy position tại T1 và committed offset từ CLI tại T2, một producer hoặc container có thể tiến offsets giữa hai mốc. Dùng timestamp, nguồn dữ liệu và interpretation rõ ràng; đừng yêu cầu các số phải khớp tuyệt đối khi không có atomic snapshot.

## 21. Quy trình điều tra khi idle nhưng không biết vị trí

Một runbook:

1. Xác nhận listener container **running**, Kafka consumer còn assignment.
2. Kiểm tra `idleEventInterval` có được bật trên factory mà listener dùng không.
3. Ghi nhận event listener ID, idle duration, topic-partitions.
4. Đọc `position(tp)` ngay trong callback đồng bộ, nếu event cung cấp consumer và thread-safety được bảo đảm.
5. Đối chiếu Kafka committed offsets theo group ID và từng partition.
6. Đối chiếu end offsets/LSO với consumer isolation mode.
7. Kiểm tra pause requested/actual paused state của container.
8. Kiểm tra records được poll, retry/seek/retained records và listener processing.
9. Đối chiếu producer throughput, broker metadata và các lỗi deserialize.
10. Xem rebalance/partition loss quanh thời điểm event.
11. Nếu position bằng end, xem upstream có phát dữ liệu theo kỳ vọng hay không.
12. Nếu position thấp hơn end, xác định lý do chưa fetch tiếp trước khi seek/reset.
13. Nếu committed thấp hơn position, kiểm tra AckMode, transaction/retry và tiến độ xử lý.
14. Dùng event ID/inbox nếu cần xác nhận external side effect đã hoàn tất, không suy ra từ position.
15. Sau điều chỉnh, theo dõi record delivery, group lag và position snapshots mới.

Không dùng idle event như một trigger mặc định để `seekToEnd()`. Làm vậy có thể bỏ qua backlog chưa xử lý và gây mất dữ liệu nghiệp vụ đối với consumer group.

## 22. Các tình huống vận hành cụ thể

### 22.1. Idle, position bằng end, committed bằng position

~~~text
position  = 500
committed = 500
end       = 500
~~~

Consumer có thể đã bắt kịp topic. Nếu upstream không phát event mới, đây là trạng thái bình thường. Nếu upstream **đáng lẽ** đang phát, cần kiểm tra producer, routing, topic name, partitioner và monitoring ingestion.

Không restart consumer chỉ vì đã idle lâu.

### 22.2. Idle, position bằng end nhưng committed thấp hơn

~~~text
position  = 500
committed = 495
end       = 500
~~~

Consumer đã poll đến biên cuối nhưng group vẫn chỉ ghi nhận offset 495. Có thể còn records chưa ack, một commit bị chậm/lỗi, hoặc container đang xử lý/retry. Không ép commit 500 chỉ để số liệu đẹp.

Khi process restart, group có thể đọc lại từ committed offset nếu những offsets đó còn được lưu. Cần idempotency.

### 22.3. Idle, position thấp hơn end, container paused

~~~text
position  = 500
committed = 500
end       = 620
paused    = true
~~~

Backlog tăng vì consumer tạm không nhận thêm. Đây có thể là backpressure chủ đích. Kiểm tra điều kiện resume, deadline và lag/retention budget.

### 22.4. Idle, position thấp hơn end, không paused

~~~text
position  = 500
end       = 620
paused    = false
~~~

Cần điều tra assignment, consumer health, poll latency, isolation, error handling, timeout và số đo end/position có cùng consumer/partition/timestamp không. Không đủ bằng chứng để kết luận Kafka broker bị lỗi.

### 22.5. Không có current position vì partition chưa được assign

Khi `consumer.assignment()` không chứa partition cần quan sát, `position(tp)` không phải lời gọi hợp lệ cho partition đó. Đừng lấy từ KafkaConsumer local và giả định consumer sở hữu partition.

Nếu cần dữ liệu offset của partition không được assign cho local consumer, có thể dùng công cụ quản trị/group offset API độc lập phù hợp quyền truy cập; đó là phép đo **committed/group/end offsets**, không phải current position của member local.

## 23. Test lấy current position khi idle

### 23.1. Kiểm thử idle khi topic rỗng

1. Tạo topic test có một partition và consumer group mới.
2. Cấu hình `idleEventInterval` ngắn, ví dụ 1–2 giây.
3. Khởi động listener và chờ partition assignment.
4. Không gửi record.
5. Chờ `ListenerContainerIdleEvent` bằng latch/Awaitility có timeout.
6. Trong callback đồng bộ, lấy `consumer.position(tp)` cho assigned partition.
7. Ghi nhận position, committed offset và end offset qua các phép đo riêng.
8. Xác nhận callback không ném exception và container tiếp tục poll.

Không dùng `Thread.sleep(2000)` rồi đoán event chắc chắn đã đến đúng thời điểm. Đồng hồ idle phụ thuộc scheduling và poll cycle.

### 23.2. Kiểm thử sau khi tiêu thụ records

1. Gửi ba records vào topic test.
2. Đợi listener xử lý thành công.
3. Đợi group commit theo AckMode đã chọn.
4. Chờ idle event.
5. Lấy current position và so với biên end gần thời điểm đó.
6. Xác minh position là **next offset**, không phải offset record cuối.
7. Xác nhận database side effect bằng dữ liệu thực, không chỉ offset.

### 23.3. Kiểm thử batch poll nhưng commit chậm

1. Cho poll trả nhiều records và dùng ack mode batch hoặc manual phù hợp.
2. Tạo tình huống commit không ngay sau poll.
3. Chụp position và committed offset.
4. Xác nhận hai giá trị có thể khác nhau.
5. Sau khi xử lý/commit thành công, quan sát committed offset tiến.
6. Kiểm tra redelivery khi restart nếu offset chưa commit.

### 23.4. Kiểm thử pause

1. Tạo producer gửi records liên tục.
2. Yêu cầu `container.pause()`.
3. Chờ `ConsumerPausedEvent` hoặc actual paused state.
4. Quan sát idle events và position snapshots theo phiên bản.
5. Xác nhận position không nhất thiết tiến khi partition paused dù end offset vẫn tăng.
6. Resume và kiểm tra dữ liệu được tiêu thụ theo offset/ack policy.

### 23.5. Kiểm thử rebalance

1. Chạy hai consumer members của cùng group.
2. Ghi nhận partition ownership và position snapshots.
3. Tạo join/leave member có kiểm soát.
4. Xác nhận assignment thay đổi.
5. Kiểm tra callback bỏ qua partition không còn được assign.
6. Đánh dấu snapshot của owner cũ stale, không hiển thị như vị trí hiện tại của partition.
7. Cho member mới xử lý và kiểm tra consumer group lag.

### 23.6. Kiểm thử event handler bất đồng bộ

Không dùng một asynchronous event listener để trực tiếp gọi KafkaConsumer.position. Nếu ứng dụng đã cấu hình async multicaster, hãy chuyển thiết kế sang thu thập snapshot trên consumer thread thông qua extension/listener callback được hỗ trợ, hoặc dùng một nguồn offset monitoring độc lập.

Mục tiêu test là xác nhận **an toàn về thread**, không chỉ việc gọi API trả số đúng trên máy dev một lần.

## 24. Các sai lầm thường gặp

**Cho rằng position là committed offset:** position có thể tiến ngay sau poll; committed offset phụ thuộc acknowledgment và transaction.

**Cho rằng position là record cuối đã xử lý:** position là offset tiếp theo; record có thể còn in-flight.

**Lấy position từ event trên executor thread:** KafkaConsumer không thread-safe, có nguy cơ `ConcurrentModificationException`/`ConcurrentAccessException` hoặc hành vi không được hỗ trợ.

**Lưu Consumer từ idle event vào singleton:** object có lifecycle và ownership; thread khác không được dùng tùy ý.

**Gọi committed/endOffsets ở mọi idle event không giới hạn:** có thể tạo metadata/network overhead và chặn consumer thread.

**Không kiểm tra assignment:** gọi position cho partition không thuộc consumer đang quan sát có thể gây lỗi.

**Nhầm idle với non-responsive:** idle có thể là poll bình thường không có record; non-responsive liên quan consumer không đáp ứng hoạt động poll.

**Nhầm idle với paused:** paused có thể là chủ ý backpressure; idle chỉ mô tả không có record được nhận theo ngưỡng.

**Tính số message còn lại bằng end - position:** khoảng cách offset không phải exact record count.

**Dùng read_uncommitted và read_committed như thể giống nhau:** transactional visibility có thể khiến end offset khác.

**Coi snapshot cũ là position hiện tại:** sau rebalance, owner và position có thể thay đổi.

**Quan sát một child rồi kết luận toàn group:** concurrent container có nhiều KafkaConsumers độc lập.

**Dùng idle callback để commit offset:** có nguy cơ bỏ qua record chưa hoàn tất xử lý.

**Dùng idle callback để seekToEnd không kiểm soát:** trực tiếp làm mất cơ hội xử lý backlog.

**Block consumer thread trong @EventListener:** có thể kéo dài poll interval, gây lag hoặc rebalance.

**Restart consumer khi position bằng end:** nếu producer không gửi thêm, restart không giải quyết điều gì.

**Không ghi group ID và topic-partition:** các offset khác group/partition không thể so sánh trực tiếp.

## 25. Tổng kết quyết định nhanh

| Mục tiêu | Cách làm | Không nên làm |
|---|---|---|
| Biết vị trí local consumer khi idle | `ListenerContainerIdleEvent` + `event.getConsumer().position(tp)` đồng bộ trên consumer thread | Gọi cùng consumer từ REST/executor thread |
| Biết tiến độ đã commit | Group committed offsets | Coi position là committed |
| Biết biên cuối của partition | `endOffsets` hoặc Kafka monitoring | Gọi quá nhiều từ idle callback |
| Biết group còn backlog | Lag theo committed offset/end, kèm timestamp | Chỉ lấy end - position rồi coi là số message |
| Biết một partition cụ thể idle | Partition idle event theo version hỗ trợ | Chỉ xem container-level idle |
| Biết container đang pause | Pause API/events và actual state | Suy ra từ việc không có records |
| Biết listener đang bị kẹt poll | Poll/heartbeat/non-responsive monitoring | Suy ra từ idle event |
| Hiển thị vị trí trong dashboard | Snapshot immutable có timestamp, owner và partition | Đưa KafkaConsumer object vào cache |
| Đảm bảo không lặp DB effect | Event ID/inbox/idempotency | Dựa vào current position |
| Xử lý lỗi commit/rebalance | Theo dõi committed offset, ownership và redelivery | Ép commit position trong idle handler |

## 26. Nguyên tắc production

- Bật `idleEventInterval` ở **đúng listener container factory** để có `ListenerContainerIdleEvent`.
- Dùng `Consumer.position(TopicPartition)` để lấy current position **theo từng assigned partition**.
- Chỉ truy cập `event.getConsumer()` khi callback chạy đồng bộ trên consumer thread phù hợp; tránh async event handler cho thao tác KafkaConsumer.
- Không lưu KafkaConsumer để thread khác dùng; chỉ xuất các snapshot dữ liệu.
- Luôn gắn listener ID, group ID, topic, partition, instance ID và observed timestamp vào kết quả.
- Hiểu position là **next offset**, không phải committed offset và không phải business completed offset.
- Nếu so sánh committed/end offsets, thu thập có kiểm soát, lưu timestamp và xét transaction isolation.
- Phân biệt container-level idle với partition-level idle, đặc biệt khi concurrency cao.
- Đối chiếu idle với pause, assignment, poll health, producer activity và group lag.
- Không tự commit hoặc seek chỉ vì current position đứng yên.
- Giữ event callback ngắn để không làm poll loop mất ổn định.
- Cần snapshot cleanup khi rebalance, stopped container hoặc instance restart.
- Test topic rỗng, record mới, ack chậm, pause và rebalance trước khi dùng để điều khiển tự động.

**Kết luận:** Khi Spring Kafka listener container idle, `ListenerContainerIdleEvent` có thể cung cấp đúng ngữ cảnh để lấy **current position** của Kafka consumer bằng `Consumer.position(tp)`. Để sử dụng an toàn, hãy đọc vị trí trên consumer thread, kiểm tra assignment và coi giá trị trả về là offset tiếp theo của consumer tại thời điểm quan sát. Không đánh đồng nó với committed offset, end offset hoặc trạng thái xử lý nghiệp vụ. Kết hợp current position với consumer lag, pause/rebalance signals và committed offsets mới cho phép giải thích tình huống idle một cách đáng tin cậy.
