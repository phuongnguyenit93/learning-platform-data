# Cảnh báo consumer không tiến triển

Một Kafka consumer có thể vẫn chạy nhưng không còn xử lý được record. Ví dụ, listener bị kẹt khi gọi database, consumer không poll được broker, một record liên tục thất bại và retry, hoặc consumer group mất partition assignment. Nếu chỉ kiểm tra process còn sống hay container đang `RUNNING`, hệ thống có thể báo khỏe trong khi backlog tăng và event không được xử lý.

Muốn phát hiện đúng tình trạng này, cần theo dõi đồng thời **nguồn có dữ liệu mới hay không**, **committed offset có tiến lên hay không**, **consumer lag và tuổi record tồn đọng**, **listener có xử lý thành công hay không**, và **consumer thread có tiếp tục poll hay không**. Một consumer không nhận record chưa chắc bị lỗi; topic có thể đang không có traffic. Cảnh báo phải dựa trên điều kiện vận hành mong đợi của từng luồng.

## 1. Phân biệt idle, non-responsive và stalled

Ba trạng thái này thường bị nhầm lẫn:

| Trạng thái | Dấu hiệu | Ý nghĩa |
|---|---|---|
| Idle hợp lệ | Không có record mới; lag bằng 0; listener không nhận dữ liệu. | Topic đang yên lặng. Đây thường là trạng thái bình thường. |
| Non-responsive consumer | `poll()` không trả về trong thời gian vượt ngưỡng giám sát; Spring Kafka phát `NonResponsiveConsumerEvent`. | Consumer có thể bị chặn khi poll, ví dụ vấn đề network/broker/client. |
| Consumer stalled | Topic vẫn có record mới hoặc lag còn tồn tại, nhưng committed offset/throughput không tiến triển trong một khoảng thời gian. | Consumer hoặc pipeline xử lý không theo kịp hoặc đã dừng tiến triển. |

`ListenerContainerIdleEvent` chỉ cho biết container không nhận được record trong `idleEventInterval`. Nó không tự chứng minh consumer bị treo. Ngược lại, nếu `poll()` không thoát, Spring Kafka không thể phát idle event vì không nhận được kết quả poll; lúc này `NonResponsiveConsumerEvent` mới là tín hiệu phù hợp.

Một listener xử lý quá lâu cũng có thể khiến poll tiếp theo bị trì hoãn, nhưng đó là vấn đề thời gian xử lý giữa các lần poll. Hãy đo listener duration, committed offset và `max.poll.interval.ms` để phát hiện. Không coi `NonResponsiveConsumerEvent` là watchdog bao quát mọi loại listener bị chậm; event này được thiết kế để phát hiện consumer có vẻ bị chặn trong `poll()`.

## 2. Những tín hiệu cần theo dõi

Không nên chỉ dựa vào một metric như `records-consumed-rate`. Hãy kết hợp các tín hiệu sau:

| Tín hiệu | Câu hỏi cần trả lời | Khi nào đáng cảnh báo? |
|---|---|---|
| Log end offset | Topic/partition có tiếp tục nhận record không? | End offset tăng trong khi consumer không tiến offset. |
| Committed offset | Group đã xác nhận xử lý đến offset nào? | Offset đứng yên trong khi nguồn vẫn có dữ liệu mới. |
| Consumer lag | Còn bao nhiêu record chưa được group xử lý? | Lag tăng liên tục hoặc vượt ngưỡng vận hành. |
| Oldest record age | Record chưa xử lý lâu nhất đã chờ bao lâu? | Tuổi record vượt SLA xử lý. |
| Records consumed rate | Consumer đang nhận record với tốc độ nào? | Tốc độ về 0 trong khi nguồn vẫn phát sinh dữ liệu. |
| Listener success/failure và duration | Listener có hoàn thành thành công hay liên tục lỗi/chậm? | Failure tăng, duration cao hoặc không còn lần xử lý thành công. |
| Assigned partitions | Consumer group có được giao partition cần xử lý không? | Group không có assignment trong khi topic có partition và consumer phải hoạt động. |
| Poll/heartbeat/rebalance | Consumer có tiếp tục poll và giữ membership không? | Poll bị chặn, heartbeat mất hoặc rebalance lặp lại. |
| DLT/retry rate | Record có bị retry hoặc chuyển DLT liên tục không? | Một lỗi làm offset không tiến hoặc DLT tăng bất thường. |

### Lag không phải tuổi của message

Consumer group lag trong các exporter thường biểu diễn khoảng cách offset giữa vị trí cuối của partition và committed offset của group. Lag bằng 5.000 record có thể tương ứng vài giây ở topic lưu lượng cao hoặc nhiều giờ ở topic lưu lượng thấp. Vì vậy, hãy theo dõi thêm tuổi record lâu nhất hoặc độ trễ event time so với thời điểm hiện tại.

Phân biệt lag do exporter tính từ committed offset với `records-lag-max` của Kafka consumer client: metric client này dựa trên consumer position hiện tại, vì vậy record đã poll nhưng chưa commit có thể không còn được tính là lag ở metric đó. Khi alert cần xác định dữ liệu đã commit, hãy lấy committed offset riêng từ consumer group/admin exporter hoặc công cụ quản trị.

Với topic transactional và consumer `isolation.level=read_committed`, consumer chỉ đọc đến Last Stable Offset (LSO), không nhất thiết đến high watermark khi còn transaction mở. Một số công cụ exporter có thể tính lag khác nhau; khi kiểm tra số liệu, phải biết exporter dùng log end offset, high watermark hay LSO.

## 3. Bật idle event và non-responsive monitor trong Spring Kafka

Spring Kafka cung cấp hai cơ chế application event:

- `ListenerContainerIdleEvent`: phát khi container không nhận record trong khoảng `idleEventInterval`; khi tiếp tục nhận record, từ Spring Kafka 2.6.2 có thêm `ListenerContainerNoLongerIdleEvent`.
- `NonResponsiveConsumerEvent`: phát khi consumer có vẻ bị chặn trong `poll()` quá ngưỡng `noPollThreshold × pollTimeout`. Monitor kiểm tra định kỳ theo `monitorInterval`.

Ví dụ cấu hình một listener container factory riêng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerMonitoringConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);

        var properties = factory.getContainerProperties();
        properties.setPollTimeout(5_000L);
        properties.setIdleEventInterval(60_000L);
        properties.setMonitorInterval(10);
        properties.setNoPollThreshold(3.0f);

        return factory;
    }
}
```

Với ví dụ này:

- `pollTimeout=5.000 ms` là thời gian truyền vào `Consumer.poll()`.
- `noPollThreshold=3.0` đặt ngưỡng non-responsive theo ba lần poll timeout, tương đương khoảng 15 giây.
- `monitorInterval=10` kiểm tra trạng thái consumer mỗi 10 giây.
- `idleEventInterval=60.000 ms` phát idle event mỗi phút khi container không nhận record.

`monitorInterval` tính bằng giây; `pollTimeout` và `idleEventInterval` tính bằng milliseconds. `noPollThreshold` nên lớn hơn `1.0` để tránh event giả do race condition. Các giá trị trên chỉ là ví dụ; cần chọn theo latency poll, traffic và yêu cầu phát hiện sự cố của service.

Từ Spring Kafka 2.8, `idleBeforeDataMultiplier` mặc định là `5.0`: trước khi container nhận record đầu tiên, thời gian chờ idle event có thể được nhân với giá trị này. Sau khi đã nhận record, multiplier không còn được áp dụng. Nếu cần alert startup idle theo mốc riêng, hãy tính đến hành vi này khi chọn `idleEventInterval`.

Gắn factory vào listener:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(OrderEvent event) {
    orderService.handle(event);
}
```

Nếu đang dùng Spring Boot auto-configured factory, có thể cấu hình các thuộc tính `ContainerProperties` trên factory hiện có hoặc tạo custom factory và chỉ định qua `containerFactory`. Khi tạo factory mới, phải giữ lại các thiết lập serializer, converter, error handler, transaction manager và concurrency mà ứng dụng cần.

## 4. Bắt application event để log và phát metric

`@EventListener` có thể nhận event từ mọi listener container trong application context. Với `@KafkaListener` có concurrency, ID của child container thường có hậu tố như `orders-listener-0`, `orders-listener-1`; do đó hãy lọc theo prefix hoặc listener ID phù hợp.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;

@Component
public class KafkaConsumerEventMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerEventMonitor.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (!event.getListenerId().startsWith("orders-listener")) {
            return;
        }

        log.info("Kafka listener idle: id={}, idleMs={}, partitions={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions());
    }

    @EventListener
    public void onActiveAgain(ListenerContainerNoLongerIdleEvent event) {
        if (!event.getListenerId().startsWith("orders-listener")) {
            return;
        }

        log.info("Kafka listener received records again: id={}, partitions={}",
                event.getListenerId(), event.getTopicPartitions());
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        if (!event.getListenerId().startsWith("orders-listener")) {
            return;
        }

        log.error("Kafka consumer is not responding: id={}, timeSinceLastPollMs={}, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions());
    }
}
```

Event handler trên chỉ ghi nhận trạng thái. Trong production, có thể tăng counter `kafka.consumer.nonresponsive` và `kafka.consumer.idle`, đồng thời gửi log có cấu trúc đến hệ thống tập trung. Dùng listener ID hoặc service name làm tag có cardinality thấp; không dùng event ID, message key hoặc danh sách partition thay đổi liên tục làm metric tag.

Thông thường event được publish trên consumer thread. Nếu thay application event multicaster bằng executor bất đồng bộ, không gọi method trên `event.getConsumer()` từ thread khác vì Kafka `Consumer` không thread-safe. Chỉ dùng consumer reference khi hiểu rõ thread và lifecycle của container.

## 5. Phát hiện idle theo từng partition

Một topic có thể nhận traffic không đồng đều: partition 0 liên tục có record trong khi partition 3 không có record trong nhiều giờ. `ListenerContainerIdleEvent` chỉ mô tả trạng thái container; để theo dõi riêng từng partition, cấu hình `idlePartitionEventInterval`.

```java
var properties = factory.getContainerProperties();
properties.setIdleEventInterval(60_000L);
properties.setIdlePartitionEventInterval(120_000L);
```

Spring Kafka phát `ListenerContainerPartitionIdleEvent` khi một partition không nhận record trong khoảng đã cấu hình và `ListenerContainerPartitionNoLongerIdleEvent` khi partition đó nhận record trở lại. Đây là tín hiệu hữu ích khi cần phát hiện partition không có traffic như kỳ vọng hoặc phân bố tải bất thường.

Không alert chỉ vì một partition idle. Partition có thể không được producer chọn do key distribution, hoặc domain không phát sinh event cho key tương ứng. Chỉ cảnh báo khi partition đó có traffic kỳ vọng, backlog tồn tại hoặc yêu cầu SLA theo partition.

## 6. Theo dõi listener duration và kết quả xử lý bằng Micrometer

Spring Kafka tự tạo Micrometer timer cho listener từ phiên bản 2.3 nếu Micrometer có trên classpath và application context có một `MeterRegistry`. Timer có tên `spring.kafka.listener` với các tag chính:

| Tag | Giá trị |
|---|---|
| `name` | Tên container bean; với concurrent container có suffix theo child container. |
| `result` | `success` hoặc `failure`. |
| `exception` | `none` hoặc `ListenerExecutionFailedException`. |

Timer này giúp theo dõi số lần xử lý, thời gian xử lý và tỷ lệ lỗi. Có thể thêm tag tĩnh qua `ContainerProperties.micrometerTags` hoặc tag động qua `micrometerTagsProvider` (từ Spring Kafka 2.9.8/3.0.6). Không đưa business key hoặc event ID vào tag vì cardinality sẽ tăng không giới hạn.

Ví dụ thêm tag service:

```java
import java.util.Map;

var properties = factory.getContainerProperties();
properties.setMicrometerTags(Map.of("service", "orders"));
```

Nếu bật Micrometer Observation bằng `observationEnabled=true`, cơ chế observation quản lý timer và timer listener thông thường bị vô hiệu hóa để tránh ghi nhận trùng. Chọn một cách instrument phù hợp và kiểm tra metric thực tế trong registry/exporter.

## 7. Thu thập Kafka consumer client metrics

Listener timer cho biết thời gian xử lý ở Spring; Kafka client metrics cho biết tình trạng fetch, poll, commit và lag. Spring Kafka cung cấp `MicrometerConsumerListener` để tự bind/unbind metric khi `ConsumerFactory` tạo hoặc đóng consumer.

Ví dụ với factory được tạo thủ công:

```java
import java.util.List;
import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.ImmutableTag;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.MicrometerConsumerListener;

@Bean
ConsumerFactory<String, OrderEvent> consumerFactory(
        Map<String, Object> consumerProperties,
        MeterRegistry meterRegistry) {

    var factory =
            new DefaultKafkaConsumerFactory<String, OrderEvent>(consumerProperties);
    factory.addListener(new MicrometerConsumerListener<>(
            meterRegistry,
            List.of(new ImmutableTag("service", "orders"))));
    return factory;
}
```

Nếu Spring Boot đã tạo `ConsumerFactory`, cần bổ sung listener vào factory hiện có bằng custom bean/configuration phù hợp; không tạo thêm factory thứ hai chỉ để bật metric vì listener container có thể đang dùng factory khác.

Các Kafka consumer metric đáng theo dõi gồm:

| Kafka metric | Ý nghĩa |
|---|---|
| `records-consumed-rate` | Tốc độ consumer nhận record. |
| `records-lag-max` | Lag lớn nhất trong các partition được theo dõi; metric client này dựa trên consumer position hiện tại, không phải committed offset. |
| `fetch-rate` | Tần suất gửi fetch request. |
| `commit-rate` | Tần suất commit offset. |
| `assigned-partitions` | Số partition đang được consumer giữ assignment. |
| `last-poll-seconds-ago` | Số giây kể từ lần gọi `poll()` gần nhất. |
| `time-between-poll-max` | Khoảng thời gian lớn nhất giữa hai lần gọi `poll()`. |
| `poll-idle-ratio-avg` | Tỷ lệ thời gian consumer ở trong `poll()` chờ dữ liệu thay vì xử lý record; giá trị thấp có thể cho thấy code xử lý đang chiếm nhiều thời gian. |

Tên metric khi xuất qua Micrometer/Prometheus có thể được chuẩn hóa khác tên JMX Kafka gốc. Hãy kiểm tra metric thật trong `/actuator/prometheus` hoặc registry của ứng dụng trước khi viết alert rule.

## 8. Đo lag và offset tiến triển

Với mỗi cặp `consumer group + topic + partition`, nên quan sát tối thiểu:

- `logEndOffset`: vị trí cuối hiện tại của partition theo công cụ đo.
- `committedOffset`: offset group đã commit.
- `lag`: khoảng cách giữa log end và committed offset theo cách exporter định nghĩa.
- `lastCommitTime`: thời điểm offset gần nhất tiến lên.
- `oldestUnprocessedAge`: tuổi của record chưa được xử lý lâu nhất, nếu có thể suy ra từ event timestamp.

Không so sánh offset của hai partition khác nhau để tạo một thứ tự toàn cục. Hãy tính lag và tiến triển theo từng partition, sau đó tổng hợp theo group/topic để tạo dashboard.

Ví dụ bảng quan sát trong 5 phút:

| Partition | Log end offset đầu/cuối | Committed offset đầu/cuối | Nhận định |
|---|---:|---:|---|
| 0 | 10.000 → 10.800 | 9.900 → 10.700 | Consumer tiến đều, lag gần như ổn định. |
| 1 | 8.000 → 8.500 | 7.900 → 7.900 | Producer tiếp tục ghi nhưng consumer không tiến. |
| 2 | 4.000 → 4.000 | 4.000 → 4.000 | Không có traffic và không có backlog; idle hợp lệ. |

Partition 1 là dấu hiệu cần điều tra. Partition 2 không nên phát cảnh báo nếu không có yêu cầu traffic hoặc heartbeat nghiệp vụ.

Với `read_committed`, committed offset vẫn là vị trí group đã commit, nhưng log end/LSO khác nhau khi có transaction mở. Dùng cùng một định nghĩa lag xuyên suốt dashboard và alert; tránh so sánh hai exporter dùng hai mốc offset khác nhau.

## 9. Thiết kế cảnh báo theo nhiều tín hiệu

Một alert consumer không tiến triển đáng tin cậy thường kết hợp ba điều kiện:

1. Có backlog hoặc nguồn vẫn tiếp tục ghi record.
2. Committed offset không tăng trong cửa sổ thời gian đủ dài.
3. Điều kiện này kéo dài hơn SLA hoặc ngưỡng bình thường của luồng.

Ví dụ điều kiện logic:

```text
consumer_lag > 0
AND committed_offset không đổi trong 5 phút
AND log_end_offset tăng trong cùng khoảng thời gian
```

Đây là biểu thức logic, không phải tên metric chuẩn. Tên metric và label phụ thuộc Kafka exporter, JMX exporter hoặc cách instrument của tổ chức. Nếu dùng PromQL, hãy map các gauge tương ứng và so sánh từng chuỗi theo `group`, `topic`, `partition`.

Ví dụ biểu thức PromQL minh họa khi exporter cung cấp các gauge tương ứng:

```promql
kafka_group_lag > 0
and on (group, topic, partition)
  (kafka_committed_offset == kafka_committed_offset offset 5m)
and on (topic, partition)
  (kafka_log_end_offset > kafka_log_end_offset offset 5m)
```

Các metric `kafka_group_lag`, `kafka_committed_offset`, `kafka_log_end_offset` trong ví dụ là tên quy ước minh họa; thay bằng tên metric và label thực tế của exporter. Với luồng lưu lượng thấp, hãy điều chỉnh `5m` theo SLA và lịch phát event.

### Ma trận cảnh báo đề xuất

| Điều kiện | Mức cảnh báo gợi ý | Lý do |
|---|---|---|
| Lag tăng và committed offset không tiến trong vài phút, nguồn vẫn có record mới. | Warning | Consumer bắt đầu không theo kịp. |
| Oldest record age vượt SLA nghiệp vụ. | Critical/Page | Event đang chờ lâu hơn thời hạn xử lý. |
| `NonResponsiveConsumerEvent` xuất hiện lặp lại hoặc kéo dài. | Critical/Page | Consumer poll có dấu hiệu bị chặn. |
| Listener failure tăng và offset không tiến. | Warning/Critical | Lỗi xử lý hoặc retry đang giữ backlog. |
| Assigned partitions bằng 0 trong khi group phải hoạt động và topic có partition. | Warning | Consumer không nhận partition cần xử lý. |
| Không có record mới và lag bằng 0. | Không cảnh báo | Có thể chỉ là topic idle bình thường. |
| Một partition idle nhưng không có backlog và không có traffic kỳ vọng. | Không cảnh báo | Partition có thể không được chọn trong khoảng thời gian đó. |

Nên dùng `for` để loại bỏ dao động ngắn và tách warning khỏi page. Đừng page chỉ vì lag dương trong một lần scrape; lag có thể xuất hiện bình thường khi producer ghi nhanh hơn consumer trong thời gian ngắn.

## 10. Cấu hình Kafka consumer ảnh hưởng đến tiến triển

Hai cấu hình quan trọng khi listener xử lý lâu là `max.poll.interval.ms` và `session.timeout.ms`.

| Cấu hình | Vai trò | Khi quá hạn |
|---|---|---|
| `max.poll.interval.ms` | Giới hạn thời gian tối đa giữa hai lần gọi `poll()` khi dùng group management. | Consumer bị coi là không tiếp tục poll; group có thể rebalance và partition được giao cho member khác. |
| `session.timeout.ms` | Giới hạn thời gian broker chờ heartbeat để xác định consumer còn sống trong group protocol classic. | Broker loại consumer khỏi group nếu không nhận heartbeat trong thời gian cho phép. |
| `max.poll.records` | Số record tối đa trả về trong một lần poll. | Giá trị lớn có thể làm một lượt xử lý kéo dài nếu mỗi record tốn nhiều thời gian. |
| `pollTimeout` | Thời gian container truyền vào `Consumer.poll()`. | Ảnh hưởng thời điểm poll trả về và ngưỡng phát `NonResponsiveConsumerEvent`. |

`max.poll.interval.ms` không giống `session.timeout.ms`. Kafka client có thể duy trì heartbeat trong khi xử lý record, nhưng nếu không gọi `poll()` trong giới hạn `max.poll.interval.ms`, consumer vẫn có thể bị loại khỏi group. Với group protocol `consumer` mới, một số thiết lập heartbeat/session được điều khiển ở broker; hãy kiểm tra protocol đang dùng trước khi chỉnh client property.

Ví dụ cấu hình consumer trong Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
```

Đây chỉ là ví dụ. Không tăng `max.poll.interval.ms` một cách máy móc để che listener bị treo. Trước tiên hãy đo thời gian xử lý tối đa của cả batch được poll, sau đó điều chỉnh `max.poll.records`, tối ưu dependency hoặc tách công việc dài theo mô hình phù hợp. Nếu tăng interval, thời gian phát hiện consumer thực sự chết và thời gian rebalance cũng có thể kéo dài.

## 11. Các nguyên nhân thường khiến consumer không tiến triển

| Nguyên nhân | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Listener gọi database/API bị treo | Listener duration tăng, poll tiếp theo bị trì hoãn, lag tăng. | Kiểm tra connection pool, query timeout, HTTP timeout và thread dump. |
| Một record gây exception lặp lại | Failure timer tăng, committed offset đứng ở cùng partition. | Kiểm tra error handler, retry/backoff, poison record và DLT. |
| Consumer không poll được broker | `NonResponsiveConsumerEvent`, fetch rate giảm hoặc không đổi. | Kiểm tra broker/network, DNS, TLS, client logs và thread dump. |
| Consumer group rebalance liên tục | Assigned partitions thay đổi, offset/throughput chập chờn. | Kiểm tra member restart, `max.poll.interval.ms`, session/heartbeat và thời gian xử lý. |
| Consumer chưa được assign partition | Assigned partitions bằng 0, listener không nhận record. | Kiểm tra group ID, topic subscription, ACL, số partition và trạng thái group. |
| Consumer bị pause có chủ đích | Event idle hoặc throughput bằng 0 trong khi container paused. | Kiểm tra pause/resume state và nguyên nhân backpressure. |
| Một partition quá nóng | Lag tăng tập trung ở một partition; các partition khác tiến đều. | Kiểm tra key distribution, hot key, partitioning và consumer concurrency. |
| Deserialization hoặc schema lỗi | Failure/DLT tăng ngay khi gặp record có schema không tương thích. | Kiểm tra serializer, deserializer, schema version và error handler. |
| JVM pause/GC hoặc thread starvation | Poll gap lớn, latency tăng đồng thời ở nhiều listener. | Kiểm tra GC pause, CPU throttling, thread pool và memory pressure. |

## 12. Runbook khi alert consumer không tiến triển

Khi nhận cảnh báo, điều tra theo thứ tự để tránh reset offset hoặc restart gây mất thông tin:

1. **Xác nhận có traffic:** kiểm tra log end offset của topic/partition có tăng trong cửa sổ alert không. Nếu không có record mới và lag bằng 0, có thể chỉ là idle.
2. **Xác định phạm vi:** kiểm tra group, topic, partition và listener ID nào bị ảnh hưởng. Nếu chỉ một partition, tập trung vào key distribution hoặc record cụ thể.
3. **Kiểm tra assignment:** xem consumer group có member và partition assignment không; xác nhận consumer không bị pause ngoài ý muốn.
4. **So sánh offset:** xem committed offset có tiến không và lag/oldest record age thay đổi thế nào.
5. **Kiểm tra listener:** xem timer success/failure, exception, retry, DLT và thời gian gọi database/API.
6. **Kiểm tra poll/rebalance:** tìm `NonResponsiveConsumerEvent`, log max poll interval, heartbeat và rebalance.
7. **Kiểm tra tài nguyên:** CPU, memory, GC pause, thread dump, network, broker health và connection pool.
8. **Khắc phục nguyên nhân:** sửa dependency, poison record, cấu hình hoặc capacity trước khi replay/restart.
9. **Xác nhận phục hồi:** committed offset tiếp tục tăng, lag giảm, oldest record age giảm và listener success trở lại.

Có thể xem nhanh offset, lag và member bằng Kafka CLI:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group order-projection
```

Kết quả giúp đối chiếu `CURRENT-OFFSET`, `LOG-END-OFFSET`, `LAG`, `CONSUMER-ID`, `HOST` và `CLIENT-ID` theo topic/partition. Với cluster bảo mật, bổ sung `--command-config client.properties` để CLI dùng đúng security protocol và credential được cấp quyền.

Không reset group offset về `latest` để làm alert biến mất. Hành động đó có thể bỏ qua record chưa xử lý. Không restart liên tục khi chưa xác định nguyên nhân vì có thể tạo rebalance storm và làm backlog tăng thêm.

Nếu poll thread thực sự bị kẹt, Spring Kafka ghi nhận `NonResponsiveConsumerEvent`; tài liệu cho biết có thể dừng container để đánh thức consumer và cho phép nó dừng. Nếu thực hiện recovery tự động, hãy gọi thao tác stop từ thread khác, xác định đúng parent `ConcurrentMessageListenerContainer` và có chính sách restart/backoff rõ ràng. Không dừng child container trực tiếp hoặc gọi stop ngay trên thread đang xử lý event nếu điều đó làm chậm listener.

## 13. Phân biệt consumer health với application health

Health endpoint báo process sống không chứng minh consumer đang tiến triển. Một ứng dụng có thể trả HTTP 200 trong khi listener thread bị kẹt hoặc group không có partition assignment.

Nên tách các khái niệm:

- **Liveness:** JVM/process còn hoạt động và có thể tiếp tục chạy.
- **Readiness:** ứng dụng sẵn sàng nhận traffic theo tiêu chí của service; với một số hệ thống, Kafka dependency phải sẵn sàng mới nhận HTTP request.
- **Consumer progress:** committed offset và listener success tiếp tục tiến theo traffic.
- **Consumer availability:** group có member/assignment phù hợp và consumer có thể poll.

Không nên đưa mọi lần idle vào readiness failure. Với topic event-driven, idle là bình thường; đánh dấu pod NotReady khi topic không có record có thể tạo vòng lặp rollout hoặc scale không cần thiết. Dùng alert riêng cho progress và chỉ gắn readiness với điều kiện thật sự cần thiết của service.

## 14. Kiểm thử cảnh báo và recovery

Một bộ kiểm thử observability nên mô phỏng nhiều trạng thái để xác nhận alert không false-positive:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Topic không có record, lag bằng 0 | Idle event có thể phát; không tạo alert stalled. |
| Producer ghi record liên tục, consumer xử lý bình thường | Offset tiến và lag ổn định/giảm; không alert. |
| Listener xử lý chậm nhưng vẫn hoàn tất trong giới hạn | Duration tăng; warning nếu vượt ngưỡng latency, không kết luận non-responsive poll. |
| Listener bị block lâu | Offset không tiến, lag tăng; kiểm tra max poll interval và listener timer. |
| Consumer poll bị treo/không trả về | `NonResponsiveConsumerEvent` xuất hiện theo monitor threshold. |
| Một record liên tục lỗi | Failure/retry tăng; offset partition bị giữ lại theo error handling policy. |
| Consumer group mất assignment | Assigned partition giảm hoặc bằng 0; alert theo trạng thái group. |
| Consumer được pause có chủ đích | Metric phản ánh paused state; không alert nếu pause nằm trong kế hoạch. |
| Consumer phục hồi và nhận record trở lại | `ListenerContainerNoLongerIdleEvent` có thể phát; offset tiếp tục tăng và alert được clear. |

Integration test có thể dùng Embedded Kafka hoặc Testcontainers để tạo topic/group thật. Đối với kịch bản listener bị block, dùng latch trong test và luôn đặt timeout để test không treo vô hạn. Đối với non-responsive poll, cần mô phỏng điều kiện khiến `poll()` không trả về; không giả định chỉ sleep trong listener sẽ phát event này.

## 15. Lỗi thường gặp khi thiết kế alert

| Lỗi thiết kế | Hệ quả | Cách sửa |
|---|---|---|
| Alert khi `records-consumed-rate = 0` | Topic yên lặng tạo cảnh báo giả. | Kết hợp với source traffic, lag và lịch phát event. |
| Alert khi lag lớn hơn 0 ngay lập tức | Backlog bình thường cũng bị page. | Dùng cửa sổ thời gian, tốc độ tăng lag và oldest record age. |
| Chỉ theo dõi process health | Listener treo nhưng process vẫn sống. | Theo dõi offset, lag, listener timer và poll event. |
| Chỉ theo dõi tổng lag của group | Một partition bị kẹt có thể bị che bởi partition khác tiến tốt. | Theo dõi lag và committed offset theo partition. |
| Dùng `ListenerContainerIdleEvent` làm bằng chứng consumer chết | Idle hợp lệ bị hiểu nhầm thành lỗi. | Phân biệt idle với `NonResponsiveConsumerEvent` và stalled condition. |
| Tăng `max.poll.interval.ms` quá lớn để hết rebalance | Phát hiện consumer hỏng chậm hơn và che listener xử lý quá lâu. | Đo thời gian xử lý, giảm batch, tối ưu dependency rồi chọn timeout phù hợp. |
| Dùng topic/partition/message key làm metric tag không giới hạn | Cardinality cao làm Prometheus/Micrometer tốn tài nguyên. | Dùng service, listener ID, group và topic đã kiểm soát; chi tiết partition để ở log hoặc metric có giới hạn. |
| Tự động reset offset khi alert | Có thể bỏ qua event chưa xử lý. | Điều tra và dùng quy trình replay có kiểm soát. |

## 16. Ghi nhớ

- Idle không đồng nghĩa stalled; topic không có traffic và lag bằng 0 thường là trạng thái bình thường.
- `ListenerContainerIdleEvent` phát khi không nhận record trong `idleEventInterval`.
- `NonResponsiveConsumerEvent` phát khi consumer có vẻ bị chặn trong `poll()` quá `noPollThreshold × pollTimeout`.
- `monitorInterval` xác định tần suất kiểm tra non-responsive; `noPollThreshold` nên lớn hơn `1.0`.
- `ListenerContainerNoLongerIdleEvent` cho biết record đã quay lại sau giai đoạn idle.
- Theo dõi committed offset, log end offset, lag, oldest record age, listener timer, assignment và rebalance.
- `max.poll.interval.ms` giới hạn khoảng cách giữa hai lần poll; `session.timeout.ms` theo dõi heartbeat trong group protocol classic.
- Alert tốt cần xác nhận nguồn còn traffic hoặc backlog thực sự tồn tại trước khi page.
- Không reset offset hoặc restart liên tục để che dấu hiệu consumer không tiến triển.
- Dùng runbook kết hợp log, metric, event, thread dump và tình trạng dependency để tìm nguyên nhân.

Cảnh báo consumer không tiến triển phải phản ánh được việc event đang bị giữ lại, không chỉ việc listener tạm thời không nhận dữ liệu. Kết hợp offset/lag với traffic đầu vào, tuổi record, listener duration và application event của Spring Kafka sẽ giúp phân biệt topic idle, poll bị chặn, listener xử lý quá lâu và consumer group mất assignment. Khi có tín hiệu đủ rõ, đội vận hành có thể xử lý đúng nguyên nhân mà không phải reset offset hoặc restart tùy tiện.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring for Apache Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring for Apache Kafka — Monitoring with Micrometer](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka — NonResponsiveConsumerEvent API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/event/NonResponsiveConsumerEvent.html)
- [Apache Kafka — Consumer Configurations](https://kafka.apache.org/41/generated/consumer_config.html)
