# Đo consumer lag

Consumer lag cho biết consumer group đang đọc chậm bao xa so với dữ liệu hiện có trong Kafka. Đây là tín hiệu quan trọng để phát hiện backlog, xử lý chậm, consumer bị dừng, partition mất assignment hoặc downstream đang quá tải.

Khi vận hành Spring Kafka, cần theo dõi lag theo từng topic-partition và theo consumer group, sau đó đối chiếu với tốc độ consume, thời gian xử lý listener, commit, rebalance và năng lực downstream. Một con số lag đơn lẻ không đủ để kết luận hệ thống đang khỏe hay gặp sự cố.

## 1. Consumer lag là gì?

Kafka lưu record trong từng partition và gán offset tăng dần cho vị trí record. Consumer group commit offset để ghi nhận vị trí tiếp theo mà group cần đọc. Consumer lag thường được tính bằng hiệu giữa log end offset và committed offset:

```text
consumer lag = log end offset - committed offset
```

Ví dụ:

```text
Topic: orders
Partition: 0

Committed offset = 1240
Log end offset  = 1300

Lag = 1300 - 1240 = 60
```

Committed offset là vị trí tiếp theo cần đọc, không phải offset của record cuối cùng đã xử lý. Vì vậy phép trừ trên không cộng thêm hoặc trừ đi một đơn vị.

Lag thường được hiển thị theo từng partition. Lag của cả group có thể là tổng lag của các partition, còn dashboard cũng nên hiển thị partition lag lớn nhất để phát hiện một partition bị nóng hoặc một consumer member xử lý chậm.

## 2. Phân biệt các loại offset

Muốn đọc lag chính xác, cần phân biệt những offset thường xuất hiện trong Kafka:

| Khái niệm | Ý nghĩa |
|---|---|
| Current position | Vị trí tiếp theo consumer sẽ fetch trong partition |
| Committed offset | Vị trí đã được consumer group lưu bền vững |
| Log end offset (LEO) | Vị trí cuối log theo trạng thái log của leader; là offset tiếp theo sau record cuối được append |
| High watermark (HW) | Ranh giới record đã được replicate đủ theo quy tắc Kafka và có thể được consumer đọc trong chế độ phù hợp |
| Last stable offset (LSO) | Ranh giới ổn định đối với consumer dùng `read_committed`, không vượt qua transaction chưa hoàn tất |

Có hai cách nhìn lag phổ biến:

- **Group committed lag:** log end/visible end offset trừ committed offset. Đây là góc nhìn của công cụ quản trị consumer group.
- **Consumer fetch lag:** end offset trừ current position của consumer. Đây là góc nhìn gần với tiến độ fetch hiện tại và thường xuất hiện trong metric `records-lag`.

Hai giá trị có thể khác nhau. Consumer có thể đã fetch record và tăng current position nhưng chưa commit offset; khi đó fetch lag giảm trong khi committed lag vẫn còn cao. Nếu consumer chết trước khi commit, record có thể được đọc lại.

Với consumer dùng `isolation.level=read_committed`, record thuộc transaction chưa commit chưa được trả về cho ứng dụng. Khi phân tích lag cho transactional topic, cần hiểu end offset đang được công cụ sử dụng và ranh giới LSO mà consumer nhìn thấy.

## 3. Lag theo offset không phải số record chính xác

Hiệu offset là thước đo khoảng cách vị trí trong log, không phải lúc nào cũng là số record nghiệp vụ đang chờ xử lý.

Offset có thể có khoảng trống vì:

- Record đã bị xóa theo retention.
- Topic dùng log compaction và các record cũ cùng key đã bị loại bỏ.
- Transaction control records chiếm vị trí trong log.
- Một số offset không còn được nhìn thấy bởi consumer theo isolation level.

Do đó lag bằng 100 không nhất thiết có nghĩa là còn đúng 100 message nghiệp vụ chưa xử lý. Đây là chỉ số backlog theo offset. Hãy kết hợp với records-consumed-rate, records-produced-rate và thời gian xử lý để đánh giá tác động.

Lag cũng không trực tiếp biểu thị số giây chậm. Muốn đo độ trễ theo thời gian, cần metric time lag dựa trên timestamp của record hoặc thời điểm xử lý, có quy tắc rõ về event time, clock skew và late events.

## 4. Consumer group và partition quyết định cách đọc lag

Mỗi consumer group có committed offset riêng cho từng topic-partition. Hai group đọc cùng một topic có thể có lag rất khác nhau.

Ví dụ:

```text
Topic orders: 3 partitions

Group orders-projection:
  orders-0 lag = 10
  orders-1 lag = 20
  orders-2 lag = 15
  total lag   = 45

Group orders-analytics:
  orders-0 lag = 300
  orders-1 lag = 450
  orders-2 lag = 280
  total lag   = 1030
```

Group projection có thể đang theo kịp trong khi group analytics bị tụt lại. Vì vậy không nên chỉ đo lag ở cấp topic hoặc chỉ theo một consumer group.

Khi consumer group đang rebalance, assignment có thể thay đổi. Một partition tạm thời chưa được gán hoặc committed offset chưa tồn tại có thể làm báo cáo lag không đầy đủ. Dashboard nên thể hiện trạng thái group, số member, số partition được gán và thời điểm metric được cập nhật.

## 5. Xem lag bằng kafka-consumer-groups.sh

Kafka CLI là cách nhanh để kiểm tra committed lag theo group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service
```

Nếu cluster yêu cầu SASL/TLS, truyền file cấu hình client:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9093 \
  --command-config admin-client.properties \
  --describe \
  --group orders-service
```

Output thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| `TOPIC` | Topic được group consume |
| `PARTITION` | Partition |
| `CURRENT-OFFSET` | Committed offset |
| `LOG-END-OFFSET` | End offset được công cụ quan sát |
| `LAG` | Chênh lệch offset |
| `CONSUMER-ID` | Consumer member đang sở hữu partition |
| `HOST` | Host của consumer |
| `CLIENT-ID` | Client ID |

Ví dụ output:

```text
TOPIC  PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders 0          1240            1300            60
orders 1          900             950             50
orders 2          700             710             10
```

Tổng lag trong ví dụ là 120. Partition 0 có lag cao nhất, nên cần kiểm tra consumer đang sở hữu partition đó, tốc độ xử lý và phân bố key.

Một số lệnh hữu ích khác:

```bash
# Xem các consumer member và partition assignment
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose

# Xem trạng thái consumer group
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service \
  --state
```

Các option cụ thể có thể khác theo Kafka version. Hãy dùng `--help` của đúng bản CLI đang triển khai.

## 6. Đo committed lag bằng AdminClient

Có thể dùng Kafka `AdminClient` để lấy committed offset của consumer group và end offset của các partition tương ứng. Cách này phù hợp khi muốn tạo một job quan sát hoặc API nội bộ.

Ví dụ:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.ListOffsetsResult;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

class ConsumerLagInspector {

    Map<TopicPartition, Long> calculateLag(
            String bootstrapServers,
            String groupId) throws Exception {

        Properties properties = new Properties();
        properties.put(
                "bootstrap.servers",
                bootstrapServers
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            Map<TopicPartition, OffsetAndMetadata> committed =
                    admin.listConsumerGroupOffsets(groupId)
                            .partitionsToOffsetAndMetadata()
                            .get();

            Map<TopicPartition, OffsetSpec> requests =
                    new HashMap<>();

            committed.keySet().forEach(topicPartition ->
                    requests.put(topicPartition, OffsetSpec.latest())
            );

            Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo>
                    endOffsets = admin.listOffsets(requests).all().get();

            Map<TopicPartition, Long> lagByPartition =
                    new HashMap<>();

            committed.forEach((topicPartition, offsetMetadata) -> {
                long committedOffset = offsetMetadata.offset();
                long endOffset = endOffsets.get(topicPartition).offset();

                lagByPartition.put(
                        topicPartition,
                        endOffset - committedOffset
                );
            });

            return lagByPartition;
        }
    }
}
```

Đây là ví dụ tối giản cho các partition đã có committed offset. Trong production cần bổ sung:

- Cấu hình SASL/TLS của AdminClient giống chính sách bảo mật cluster.
- Timeout cho các KafkaFuture và xử lý lỗi broker/partition không sẵn sàng.
- Phát hiện lag âm hoặc committed offset nằm ngoài end offset sau truncation/retention; không âm thầm ép về 0.
- Phát hiện partition đang được assign nhưng chưa có committed offset.
- Gắn group ID, topic, partition và thời điểm đo vào metric.
- Đóng AdminClient đúng lifecycle; không tạo client mới liên tục theo mỗi request HTTP.

Principal của AdminClient cần quyền đọc committed offsets của group và truy vấn metadata/offset của topic theo ACL cluster.

## 7. Partition chưa có committed offset

Nếu consumer group chưa từng commit offset cho một partition, partition đó có thể không xuất hiện trong kết quả `listConsumerGroupOffsets`. Không được hiểu partition vắng mặt là lag bằng 0.

Cần xác định tập partition mà group thực sự subscribe/assign, sau đó đối chiếu với committed offsets:

- Có assignment nhưng chưa có committed offset: trạng thái khởi tạo hoặc offset chưa được commit.
- Không có assignment: có thể group đang rỗng, rebalance hoặc subscription không bao gồm topic đó.
- Có committed offset nhưng không còn end offset hợp lệ: kiểm tra topic/partition đã bị xóa hoặc metadata không đồng bộ.

Offset khởi tạo còn phụ thuộc `auto.offset.reset` khi group chưa có offset hợp lệ. `earliest` bắt đầu từ offset sớm nhất còn lưu; `latest` bắt đầu từ end offset tại thời điểm reset. Lựa chọn này ảnh hưởng trực tiếp tới lượng backlog ban đầu.

## 8. Theo dõi Kafka consumer metrics

Kafka consumer cung cấp metrics qua `KafkaConsumer.metrics()` và JMX. Một số metric hữu ích:

| Metric | Ý nghĩa vận hành |
|---|---|
| `records-lag` | Lag theo partition tại vị trí consumer hiện tại |
| `records-lag-max` | Lag lớn nhất trong các partition consumer đang theo dõi |
| `records-consumed-rate` | Tốc độ record được consume |
| `records-consumed-total` | Tổng số record đã consume |
| `fetch-rate` | Tần suất fetch |
| `fetch-latency-avg` | Độ trễ fetch trung bình |
| `commit-rate` | Tần suất commit offset |
| `commit-latency-avg` | Độ trễ commit trung bình |
| `poll-idle-ratio-avg` | Tỷ lệ thời gian consumer idle giữa các lần poll |
| `assigned-partitions` | Số partition đang được assign, nếu client/version cung cấp |

Metric name và tag có thể khác theo Kafka client version và cách exporter ánh xạ JMX. Đừng giả định mọi metric đều có group ID; hãy kiểm tra `client.id`, topic, partition và tag thực tế trong hệ thống quan sát.

`records-lag-max` rất hữu ích để phát hiện partition bị nóng. Tuy nhiên nó không thay thế committed group lag vì nó thường phản ánh tiến độ consumer hiện tại, không nhất thiết là offset đã commit.

## 9. Đưa metrics vào Spring Boot bằng Micrometer

Spring Kafka và Kafka client có thể tích hợp với Micrometer để xuất metric cho Prometheus hoặc hệ thống quan sát khác. Cách cấu hình cụ thể phụ thuộc phiên bản Spring Boot và Spring Kafka.

Với Spring Kafka có hỗ trợ `MicrometerConsumerListener`, có thể đăng ký listener với `ConsumerFactory` để gắn metrics cho consumer được tạo:

```java
import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.MicrometerConsumerListener;

@Configuration
class KafkaConsumerMetricsConfiguration {

@Bean
DefaultKafkaConsumerFactory<String, OrderEvent> ordersConsumerFactory(
        MeterRegistry meterRegistry) {

    DefaultKafkaConsumerFactory<String, OrderEvent> factory =
            new DefaultKafkaConsumerFactory<>(consumerProperties());

    factory.addListener(
            new MicrometerConsumerListener<>(
                    meterRegistry,
                    Map.of("service", "orders-service")
            )
    );

    return factory;
}
}
```

`consumerProperties()` là phương thức ứng dụng trả về map cấu hình consumer gồm bootstrap servers, deserializer, group ID và các thuộc tính cần thiết. Ví dụ cho thấy đăng ký listener trực tiếp lên factory hiện có; không tạo factory mới hoặc bean tự tham chiếu chính nó chỉ để thêm metrics.

Một lựa chọn khác là dùng Micrometer `KafkaClientMetrics` để bind trực tiếp metrics của Kafka client. Cần quản lý vòng đời binder tương ứng với producer/consumer được tạo và đóng; tránh bind lặp lại mỗi lần consumer được tạo mà không deregister.

Spring Kafka listener container cũng có thể xuất timer cho thời gian listener xử lý record/batch. Timer này bổ sung cho Kafka client metrics: client metrics cho biết fetch/lag/commit, còn listener timer cho biết thời gian xử lý nghiệp vụ. Không nhầm timer xử lý listener với committed lag của group.

## 10. Expose metrics qua Spring Boot Actuator

Thêm registry Prometheus phù hợp với phiên bản Spring Boot đang dùng, sau đó expose endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

Các endpoint thường dùng:

- `/actuator/health`: tình trạng ứng dụng và health indicator đã cấu hình.
- `/actuator/metrics`: tra cứu metric đã được Micrometer đăng ký.
- `/actuator/prometheus`: scrape metrics dạng Prometheus nếu registry đã được thêm.

Không expose Actuator endpoint nhạy cảm ra Internet công khai. Bảo vệ endpoint bằng network policy, authentication và authorization; chỉ mở endpoint cần thiết cho hệ thống giám sát.

Metrics từ Kafka client thường có tên theo binder và phiên bản, có thể dùng dấu gạch dưới khi xuất Prometheus. Hãy truy vấn `/actuator/metrics` hoặc `/actuator/prometheus` để xác nhận metric thực tế trước khi viết dashboard và alert rule.

## 11. Theo dõi lag bằng Prometheus và dashboard

Dashboard nên thể hiện ít nhất bốn góc nhìn:

1. Tổng lag theo consumer group.
2. Lag lớn nhất theo topic-partition.
3. Lag thay đổi theo thời gian.
4. Tốc độ produce/consume và listener processing latency.

Ví dụ metric tùy biến sau khi job tính committed lag:

```text
kafka_consumer_group_lag{
  group="orders-service",
  topic="orders",
  partition="0"
} 60
```

Đây là metric do ứng dụng/exporter tự định nghĩa, không phải tên metric chuẩn của Kafka. Nếu dùng exporter có schema khác, hãy chuẩn hóa label trước khi tạo dashboard.

Có thể tính tổng lag:

```promql
sum by (group, topic) (kafka_consumer_group_lag)
```

Tìm partition lag lớn nhất:

```promql
max by (group, topic) (kafka_consumer_group_lag)
```

Theo dõi tốc độ tăng lag:

```promql
deriv(kafka_consumer_group_lag[5m])
```

`deriv` cho biết xu hướng tăng/giảm gần đúng trong cửa sổ thời gian. Không dùng nó một mình làm điều kiện paging; kết hợp với tổng lag, tốc độ consume và thời gian duy trì tình trạng.

## 12. Thiết kế alert theo backlog và thời gian

Không có một ngưỡng lag phù hợp cho mọi topic. Ngưỡng phụ thuộc throughput, SLA, kích thước message, thời gian xử lý và khả năng mở rộng consumer.

Một chính sách alert có thể gồm:

| Điều kiện | Ý nghĩa | Phản ứng |
|---|---|---|
| Lag tăng liên tục trong vài phút | Consumer không theo kịp producer | Kiểm tra consume rate, processing latency và downstream |
| Lag vượt ngưỡng cao trong thời gian đủ dài | Backlog có thể ảnh hưởng SLA | Cảnh báo vận hành hoặc paging theo mức độ |
| Một partition lag cao bất thường | Hot key, skew hoặc một consumer chậm | Kiểm tra key distribution và partition assignment |
| Lag cao và consume rate bằng 0 | Consumer dừng, mất assignment hoặc bị kẹt | Kiểm tra container state, exception và broker connectivity |
| Lag giảm nhưng commit rate bằng 0 | Consumer fetch/ xử lý nhưng chưa commit hoặc metric không đồng bộ | Kiểm tra AckMode, transaction và commit |
| Group không có committed offset | Group mới hoặc offset chưa được tạo | Kiểm tra trạng thái triển khai và `auto.offset.reset` |

Có thể ước lượng thời gian drain backlog:

```text
estimated drain time
  = current lag / (consume rate - produce rate)
```

Công thức chỉ có ý nghĩa khi consume rate lớn hơn produce rate và các tốc độ ổn định trong khoảng đo. Nếu consume rate nhỏ hơn hoặc bằng produce rate, backlog không tự giảm. Ước lượng này không phải SLA chính xác vì record size, xử lý downstream và partition skew có thể thay đổi.

## 13. Đọc pattern lag để tìm nguyên nhân

Một số pattern thường gặp:

| Pattern | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Tất cả partition cùng tăng lag | Consumer capacity thấp hoặc downstream chậm | Tăng năng lực xử lý, tối ưu listener/DB, xem produce rate |
| Chỉ một partition tăng mạnh | Hot key hoặc phân bố key lệch | Kiểm tra key, partitioner và thời gian xử lý theo key |
| Lag tăng theo đợt rồi giảm | Traffic burst hoặc batch processing | So sánh peak throughput và drain time |
| Lag cao, fetch rate thấp | Consumer không fetch được hoặc bị pause | Kiểm tra assignment, poll, broker network và pause state |
| Lag cao, fetch rate cao nhưng consume rate thấp | Fetch được dữ liệu nhưng xử lý chậm | Kiểm tra listener, DB, HTTP call và thread contention |
| Lag thấp nhưng listener latency cao | Traffic ít hoặc lag chưa kịp tích lũy | Theo dõi latency/SLA riêng, không chỉ lag |
| Lag đột ngột thay đổi sau rebalance | Assignment/offset ownership thay đổi | Kiểm tra rebalance events, group member và commit |
| Lag giảm đột ngột sau reset offset | Offset đã bị thay đổi | Kiểm tra audit và lệnh reset; lag thấp không đồng nghĩa event đã xử lý |

Đừng tăng concurrency ngay khi thấy lag. Nếu số partition ít, tăng concurrency có thể không tạo thêm consumer hữu ích. Nếu database đã bão hòa, tăng consumer thread có thể làm hệ thống chậm hơn.

## 14. Rebalance và consumer lag

Khi member tham gia/rời group, consumer group có thể rebalance và phân phối lại partition. Trong thời gian rebalance, một số partition tạm dừng xử lý; lag có thể tăng hoặc metric assignment tạm thời biến mất.

Các nguyên nhân thường gặp:

- Instance restart hoặc crash.
- Deployment rolling làm consumer rời group.
- Consumer không gọi `poll()` kịp thời và vượt `max.poll.interval.ms`.
- Network interruption hoặc broker unavailable.
- Thay đổi subscription hoặc số partition.
- Consumer xử lý một batch quá lâu trước khi poll tiếp.

Theo dõi rebalance rate, assigned partitions, poll interval, heartbeat và commit latency cùng lag. Nếu rebalance xảy ra liên tục, chỉ tăng số consumer có thể làm tình hình tệ hơn.

Với Spring Kafka, kiểm tra listener container state, concurrency, exception handler và thời gian xử lý listener. Cần bảo đảm listener không block quá lâu đến mức consumer vượt giới hạn poll; nếu xử lý lâu, hãy thiết kế batch, pause/resume hoặc worker queue theo đúng semantics offset.

## 15. Liên hệ lag với cấu hình commit trong Spring Kafka

Lag dựa trên committed offset, vì vậy `AckMode` và commit strategy ảnh hưởng trực tiếp đến số liệu.

Một số chế độ acknowledgement:

| AckMode | Hành vi khái quát |
|---|---|
| `RECORD` | Commit sau khi từng record được listener xử lý |
| `BATCH` | Commit sau khi các record trong poll batch được xử lý |
| `MANUAL` | Listener gọi acknowledge; container commit theo semantics của mode |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trong thread consumer theo cấu hình phù hợp |

Nếu ứng dụng xử lý record thành công nhưng chưa commit, committed lag có thể vẫn cao. Đây không nhất thiết là backlog chưa xử lý; có thể chỉ là khoảng cách giữa processing position và committed position.

Ngược lại, commit trước khi side effect nghiệp vụ hoàn tất có thể làm lag giảm dù công việc chưa thành công. Vì vậy commit phải theo đúng semantics xử lý, retry và transaction. Không tối ưu dashboard bằng cách commit sớm để làm đẹp lag.

## 16. Đo time lag và end-to-end latency

Offset lag trả lời câu hỏi “consumer còn cách end offset bao nhiêu vị trí?”. Time lag trả lời “sự kiện mới nhất đã được xử lý chậm bao lâu?”. Hai chỉ số bổ sung cho nhau.

Có thể đo end-to-end latency bằng timestamp event do producer gắn và timestamp khi listener hoàn tất:

```java
import java.util.concurrent.TimeUnit;

long eventTime = event.createdAt().toEpochMilli();
long processedAt = clock.millis();

long processingDelayMs = processedAt - eventTime;

meterRegistry.timer(
        "orders.event.processing.delay",
        "eventType",
        event.eventType()
).record(processingDelayMs, TimeUnit.MILLISECONDS);
```

Cần xác định rõ `createdAt` là event time hay processing time. Clock giữa producer và consumer có thể lệch; nếu cần đo chính xác, dùng clock synchronization và quy ước timestamp thống nhất.

Một metric khác là thời gian từ record mới nhất ở partition đến thời điểm consumer xử lý record đó. Việc này cần đọc timestamp của record và trạng thái xử lý gần nhất theo partition; tránh lấy timestamp từ một partition khác để đại diện toàn topic.

## 17. Kiểm thử việc đo lag

Integration test nên xác minh công thức và các trạng thái biên, không chỉ kiểm tra consumer nhận được message.

Các trường hợp cần có:

1. Gửi 10 record, chưa consume/commit: group lag tăng theo offset.
2. Consume và commit đủ record: committed lag giảm về 0.
3. Consume nhưng chưa commit: fetch lag có thể giảm trong khi committed lag vẫn cao.
4. Tạo hai consumer group: xác minh mỗi group có lag độc lập.
5. Tạo nhiều partition: xác minh lag được tính riêng từng partition.
6. Group chưa có committed offset: metric phải thể hiện trạng thái unknown/uninitialized, không tự báo 0.
7. Rebalance: assignment và lag metric được cập nhật sau khi group ổn định.
8. Reset offset hoặc retention: phát hiện thay đổi bất thường và tránh báo số liệu âm như backlog hợp lệ.
9. Với transactional topic, kiểm tra consumer `read_committed` và ranh giới record có thể đọc.

Khi dùng Testcontainers hoặc Embedded Kafka, tạo topic với số partition cố định, dùng consumer group ID duy nhất cho từng test và chờ commit hoàn tất trước khi assert. Không dùng sleep cố định dài; ưu tiên polling assertion với deadline để test ổn định.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lag luôn bằng 0 dù consumer không chạy | Group chưa có committed offset hoặc dashboard bỏ partition chưa commit | Theo dõi group state và uninitialized offset riêng |
| CLI và `records-lag-max` khác nhau | Một bên dùng committed offset, bên kia dùng consumer position | Ghi rõ định nghĩa metric và không so sánh trực tiếp |
| Lag âm | Offset state thay đổi do truncation, reset hoặc dữ liệu quan sát không đồng bộ | Cảnh báo trạng thái offset bất thường và kiểm tra metadata |
| Lag tăng dù listener xử lý nhanh | Commit batch chậm hoặc commit không diễn ra | Kiểm tra AckMode, commit interval và transaction |
| Tổng lag thấp nhưng SLA vẫn trễ | Record ít nhưng xử lý chậm hoặc timestamp/event time trễ | Theo dõi time lag và listener latency |
| Lag chỉ cao ở một partition | Hot key hoặc skew | Kiểm tra partitioning và phân bố key |
| Metric biến mất khi rebalance | Consumer tạm thời không có assignment | Theo dõi group state và rebalance |
| Dashboard nhân đôi lag | Nhiều exporter cùng publish một group/partition | Chuẩn hóa scrape target và label |
| AdminClient không lấy được committed offsets | ACL thiếu quyền hoặc broker unavailable | Kiểm tra group authorization và connectivity |

## 19. Checklist quan sát consumer lag

1. Xác định consumer group và topic-partition cần giám sát.
2. Đo committed lag theo từng partition và tổng theo group.
3. Phân biệt committed offset với consumer current position.
4. Hiển thị partition lag lớn nhất để phát hiện hot partition.
5. Theo dõi records-consumed-rate, fetch-rate, commit-rate và listener latency.
6. Theo dõi rebalance, assigned partitions và consumer group state.
7. Đặt alert theo mức lag, tốc độ tăng và thời gian duy trì, gắn với SLA.
8. Đo time lag/end-to-end latency riêng nếu nghiệp vụ cần độ trễ theo thời gian.
9. Xử lý riêng group chưa có committed offset, partition bị xóa và offset bất thường.
10. Bảo vệ Actuator, Prometheus và AdminClient bằng ACL/TLS phù hợp.
11. Kiểm thử lag trước/sau consume, commit, rebalance và reset offset.
12. Không reset offset hoặc tăng concurrency chỉ để làm giảm con số lag mà chưa xác định nguyên nhân.

Consumer lag là chỉ số quan trọng để biết consumer group đang theo kịp log Kafka đến đâu. Khi đo đúng theo topic-partition, phân biệt committed offset với fetch position và kết hợp metrics xử lý, commit, rebalance cùng time lag, đội vận hành có thể tìm ra backlog thực sự và chọn cách khắc phục phù hợp.
