# Theo dõi consumer group

Consumer group là đơn vị Kafka dùng để phân phối việc đọc partition cho nhiều consumer cùng xử lý một luồng dữ liệu. Theo dõi consumer group giúp đội vận hành biết group có đang hoạt động hay không, có bao nhiêu member, member nào sở hữu partition nào, rebalance có diễn ra liên tục không và offset có được commit đúng tiến độ không.

Trong Spring Kafka, consumer group được cấu hình qua `group.id` hoặc thuộc tính `groupId` của `@KafkaListener`. Khi chạy nhiều instance ứng dụng với cùng group ID, Kafka phân phối partition giữa các instance để mở rộng khả năng xử lý. Vì vậy, vận hành group cần quan sát đồng thời trạng thái broker, consumer member, listener container và offset.

## 1. Consumer group giải quyết vấn đề gì?

Một topic có thể có nhiều partition. Consumer group cho phép nhiều consumer phối hợp đọc topic đó:

```text
Topic: orders
  partition 0
  partition 1
  partition 2
  partition 3

Consumer group: orders-service
  consumer A -> partition 0, 1
  consumer B -> partition 2
  consumer C -> partition 3
```

Trong cùng một group, mỗi partition được gán cho tối đa một consumer member tại một thời điểm. Điều này giúp các member chia sẻ công việc mà không chủ động đọc trùng cùng partition.

Một topic có thể được nhiều group đọc độc lập:

- `orders-service` đọc để cập nhật trạng thái đơn hàng.
- `orders-analytics` đọc để tổng hợp dữ liệu phân tích.
- `orders-audit` đọc để lưu dấu vết kiểm toán.

Mỗi group có committed offset riêng. Nếu các ứng dụng cần nhận độc lập toàn bộ sự kiện, hãy dùng group ID khác nhau. Nếu nhiều instance cần chia sẻ tải, chúng dùng cùng group ID.

Không dùng chung group ID cho hai workload có mục đích xử lý khác nhau chỉ vì chúng cùng đọc một topic; khi đó Kafka sẽ phân phối partition giữa hai workload và mỗi workload có thể không nhận được toàn bộ record.

## 2. Group ID, client ID và member ID

Ba định danh này có vai trò khác nhau:

| Định danh | Vai trò |
|---|---|
| `group.id` | Xác định nhóm consumer và namespace lưu committed offsets |
| `client.id` | Nhận diện Kafka client trong log, metric và quota |
| `member.id` | Nhận diện một consumer member trong group; thường do Kafka cấp trong quá trình join |

Một group có thể có nhiều member. Mỗi member có client ID riêng để dễ quan sát log và metrics. Đặt client ID có ý nghĩa như service, instance và listener để tìm ra consumer gây ra lỗi.

Ví dụ:

```properties
group.id=orders-service
client.id=orders-service-instance-2
```

Spring Kafka có thể cấu hình group ID ở cấp consumer factory:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      client-id: orders-service
```

Hoặc khai báo riêng cho listener:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

Nếu nhiều listener cùng dùng một consumer factory, cần xác định rõ listener nào dùng group ID nào. Không suy ra group ID chỉ từ tên bean hoặc tên container.

## 3. Vòng đời và trạng thái consumer group

Kafka coordinator quản lý membership và partition assignment của group. Khi consumer khởi động, nó tham gia group, nhận assignment, gửi heartbeat và tiếp tục poll dữ liệu. Khi membership hoặc metadata thay đổi, group có thể rebalance.

Các trạng thái group thường gặp:

| Trạng thái | Ý nghĩa vận hành |
|---|---|
| `Empty` | Group không có member đang hoạt động; committed offsets có thể vẫn được giữ |
| `PreparingRebalance` | Coordinator đang chuẩn bị phân phối lại partition |
| `CompletingRebalance` | Đang hoàn tất assignment và chờ member tham gia đầy đủ |
| `Stable` | Group đã có assignment ổn định |
| `Dead` | Group đã bị loại bỏ khỏi coordinator |
| `Unknown` | Công cụ không xác định được trạng thái |

Tên trạng thái hoặc tập trạng thái có thể khác theo Kafka version và group protocol. Một số giao thức consumer mới có thể hiển thị trạng thái bổ sung. Khi vận hành, hãy đối chiếu output của đúng Kafka version đang dùng.

Một group ở trạng thái `Empty` không nhất thiết là lỗi: có thể service đang dừng có chủ đích. Nhưng nếu group cần chạy liên tục mà ở `Empty` lâu, cần kiểm tra ứng dụng có khởi động listener hay không, kết nối broker, cấu hình group ID và lỗi khởi tạo consumer.

## 4. Quan sát group bằng kafka-consumer-groups.sh

Liệt kê group hiện có:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --list
```

Xem thông tin partition và committed offset của một group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service
```

Nếu cluster bật SASL/TLS, truyền client config có quyền đọc group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9093 \
  --command-config admin-client.properties \
  --describe \
  --group orders-service
```

Xem member và partition assignment:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
```

Xem trạng thái group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service \
  --state
```

Khi đọc output, tập trung vào:

- Group có đúng tên và đúng topic subscription hay không.
- Số member hiện tại có phù hợp với số instance dự kiến không.
- Mỗi partition đã được assign cho member nào.
- Có partition không được assign hoặc member có assignment bất thường không.
- Group có ở trạng thái `Stable` hay liên tục chuyển qua rebalance.
- Committed offset có được cập nhật hay bị đứng lâu.

Consumer lag là một góc nhìn khác của group và được trình bày riêng trong bài đo consumer lag. Khi kiểm tra group, hãy dùng lag như tín hiệu bổ sung thay vì coi nó là toàn bộ trạng thái group.

## 5. Xem group bằng Kafka AdminClient

Có thể dùng `AdminClient` để xây dựng trang quản trị hoặc job giám sát nội bộ. AdminClient cho phép liệt kê group, mô tả group, đọc member và xem committed offsets.

Ví dụ đọc trạng thái và assignment:

```java
import java.util.Set;
import java.util.Properties;
import java.util.Map;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;
import org.apache.kafka.clients.admin.MemberDescription;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

class ConsumerGroupInspector {

    void inspect(String bootstrapServers, String groupId)
            throws Exception {

        Properties properties = new Properties();
        properties.put("bootstrap.servers", bootstrapServers);

        try (AdminClient admin = AdminClient.create(properties)) {
            ConsumerGroupDescription description =
                    admin.describeConsumerGroups(Set.of(groupId))
                            .describedGroups()
                            .get(groupId)
                            .get();

            System.out.println("groupId = " + description.groupId());
            System.out.println("state = " + description.state());
            System.out.println("coordinator = " + description.coordinator());

            for (MemberDescription member : description.members()) {
                System.out.println("memberId = " + member.consumerId());
                System.out.println("clientId = " + member.clientId());
                System.out.println("host = " + member.host());
                System.out.println(
                        "partitions = "
                                + member.assignment().topicPartitions()
                );
            }
        }
    }
}
```

Đoạn code là ví dụ đồng bộ tối giản. Trong production, cần đặt timeout cho các KafkaFuture, xử lý group không tồn tại, broker unavailable và lỗi authorization. Tránh gọi AdminClient trên mỗi request UI; nên dùng một service có lifecycle rõ ràng và cache kết quả trong khoảng thời gian ngắn nếu phù hợp.

Đọc committed offsets của group:

```java
// Đặt trong block try (AdminClient admin = ...) của ví dụ trên.
Map<TopicPartition, OffsetAndMetadata> offsets =
        admin.listConsumerGroupOffsets(groupId)
                .partitionsToOffsetAndMetadata()
                .get();
```

Thông tin assignment trả lời câu hỏi member nào đang sở hữu partition. Committed offsets trả lời câu hỏi group đã lưu tiến độ đọc đến đâu. Hai thông tin bổ sung nhau, không thay thế nhau.

## 6. Theo dõi consumer group trong Spring Kafka

Spring Kafka quản lý listener container thông qua `KafkaListenerEndpointRegistry`. Gán ID ổn định cho listener để có thể quan sát và điều khiển container theo ID.

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

Có thể lấy container từ registry:

```java
import java.util.Collection;

import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
class ListenerContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    ListenerContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    void inspectOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null) {
            return;
        }

        boolean running = container.isRunning();
        Collection<TopicPartition> assigned =
                container.getAssignedPartitions();

        System.out.println("running = " + running);
        System.out.println("assigned = " + assigned);
    }
}
```

`isRunning()` cho biết container lifecycle đang chạy hay dừng. `getAssignedPartitions()` giúp quan sát partition assignment mà container báo cáo; giá trị có thể null khi container chưa nhận assignment. Với `ConcurrentMessageListenerContainer`, container cha có thể quản lý nhiều child container, vì vậy cần kiểm tra API/version để lấy thông tin chi tiết theo child khi cần.

Trạng thái container đang chạy không chứng minh broker đã assign partition hoặc listener đang xử lý thành công. Hãy đối chiếu registry, AdminClient, metrics và log của consumer.

## 7. Một listener container và nhiều consumer member

Trong Spring Kafka, thuộc tính `concurrency` của listener container có thể tạo nhiều consumer thread cho cùng listener. Mỗi child container sử dụng một Kafka consumer và tham gia group theo group ID đã cấu hình.

Ví dụ:

```yaml
spring:
  kafka:
    listener:
      concurrency: 3
```

Hoặc cấu hình tại listener:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service",
        concurrency = "3"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

Nếu triển khai 2 instance ứng dụng, mỗi instance có concurrency 3, group có thể có tối đa 6 consumer member từ listener đó. Số member thực tế còn phụ thuộc cấu hình, container lifecycle, subscription và partition count.

Nếu topic có 4 partition nhưng group có 6 member, tối đa 4 member có thể sở hữu partition; các member còn lại sẽ idle. Tăng concurrency không tự tạo thêm partition hoặc tăng khả năng song song vượt giới hạn partition.

## 8. Partition assignment và assignor

Kafka dùng partition assignor để quyết định partition nào được giao cho member nào. Các chiến lược phổ biến:

| Assignor | Đặc điểm khái quát |
|---|---|
| `RangeAssignor` | Chia partition theo range trong từng topic; có thể tạo phân bố không đều giữa nhiều topic |
| `RoundRobinAssignor` | Phân phối lần lượt partition cho member; thường cân bằng tổng số partition tốt hơn |
| `StickyAssignor` | Cố giữ assignment cũ khi có thể, giảm số partition phải di chuyển |
| `CooperativeStickyAssignor` | Kết hợp tính sticky với incremental cooperative rebalance để hạn chế việc thu hồi toàn bộ assignment cùng lúc |

Chiến lược phù hợp phụ thuộc số topic, partition, member và khả năng tương thích của client. Không đổi assignor tùy tiện giữa các instance của cùng group. Trong rolling upgrade, phải theo quy trình tương thích của Kafka version và assignor đang dùng.

Có thể cấu hình assignor trong consumer properties:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Chỉ dùng assignor này khi tất cả member trong group và phiên bản Kafka client hỗ trợ cooperative protocol. Khi chuyển đổi từ eager assignor, hãy làm theo trình tự migration của phiên bản Kafka để tránh member không tương thích.

## 9. Những sự kiện làm group rebalance

Rebalance là cơ chế bình thường để group phân phối lại partition khi membership hoặc subscription thay đổi. Tuy nhiên, rebalance quá thường xuyên làm giảm thời gian xử lý hữu ích.

Các nguyên nhân thường gặp:

- Một instance mới tham gia group hoặc một instance dừng.
- Consumer bị crash hoặc mất kết nối.
- Listener xử lý quá lâu và consumer không gọi `poll()` trong giới hạn.
- Heartbeat không đến broker đúng hạn.
- Topic được thêm partition hoặc subscription thay đổi.
- Consumer group thay đổi assignor hoặc cấu hình membership.
- Deployment rolling restart nhiều instance gần như đồng thời.

Khi rebalance xảy ra, consumer có thể tạm dừng xử lý trong lúc assignment thay đổi. Cần theo dõi tần suất rebalance, thời gian group ở trạng thái không ổn định, số member và số partition được assign.

Không phải mọi lần rebalance đều là sự cố. Hãy đánh giá tần suất, thời gian và tác động đến SLA trước khi thay đổi cấu hình.

## 10. Heartbeat, session timeout và poll interval

Ba cấu hình ảnh hưởng lớn đến membership:

| Property | Vai trò |
|---|---|
| `heartbeat.interval.ms` | Khoảng thời gian consumer gửi heartbeat khi thuộc group |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trước khi xem member mất kết nối |
| `max.poll.interval.ms` | Thời gian tối đa giữa hai lần gọi `poll()` trước khi consumer bị xem là không còn tiến triển |

`heartbeat.interval.ms` thường được đặt nhỏ hơn đáng kể so với `session.timeout.ms`. `max.poll.interval.ms` cần đủ lớn cho thời gian xử lý batch trong trường hợp bình thường, nhưng tăng quá cao có thể làm phát hiện consumer bị treo chậm hơn.

Ví dụ cấu hình client:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[heartbeat.interval.ms]": 3000
        "[session.timeout.ms]": 10000
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 100
```

Đây chỉ là giá trị minh họa. Hãy đo thời gian xử lý record/batch và độ trễ downstream trước khi chọn ngưỡng. Nếu listener có tác vụ chậm không giới hạn, tăng `max.poll.interval.ms` không giải quyết được nguyên nhân gốc; cần thiết kế lại cách xử lý hoặc quản lý pause/resume và commit phù hợp.

## 11. Static membership với group.instance.id

Static membership dùng `group.instance.id` để định danh ổn định một consumer instance. Khi member tạm thời mất kết nối nhưng quay lại trong khoảng thời gian phù hợp, Kafka có thể giữ assignment cho member đó và giảm rebalance không cần thiết.

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": orders-service-pod-0
```

Mỗi consumer member đồng thời trong cùng group phải có `group.instance.id` duy nhất. Nếu hai member cùng dùng một ID, broker có thể fencing một member bằng lỗi instance ID trùng. Với listener có concurrency lớn hơn 1, cần xác minh phiên bản Spring Kafka đang dùng có tự thêm suffix cho từng child consumer hay không; nếu không, phải cấp ID khác nhau cho từng child. Không giả định một giá trị cấu hình ở cấp pod luôn đủ duy nhất.

Trong môi trường Kubernetes, có thể dùng StatefulSet ordinal kết hợp child index hoặc identity ổn định khác để tạo ID. Không dùng một giá trị cố định giống nhau cho mọi replica. Static membership cũng không loại bỏ rebalance trong mọi trường hợp; nó thay đổi cách broker xử lý việc member rời/vào group.

## 12. Scaling consumer group

Khả năng song song của consumer group bị giới hạn bởi số partition có thể assign cho group. Nếu cần tăng throughput, hãy đánh giá đồng thời:

- Số partition của topic.
- Số consumer member đang hoạt động.
- Concurrency của listener container trên mỗi instance.
- Throughput và latency của từng record.
- Khả năng chịu tải của database hoặc downstream service.
- Key distribution và partition skew.
- Tần suất rebalance và thời gian xử lý batch.

Ví dụ topic có 8 partition, group có 4 member thì mỗi member có thể nhận khoảng 2 partition nếu assignor phân phối cân bằng. Tăng lên 10 member không tạo thêm khả năng đọc song song; 2 member sẽ không có partition.

Tăng số partition có thể tăng song song nhưng cũng thay đổi mapping key-to-partition cho record mới. Nếu nghiệp vụ phụ thuộc thứ tự theo key, hãy đánh giá tác động trước khi mở rộng partition count.

## 13. Rolling deploy và graceful shutdown

Khi triển khai phiên bản mới, consumer member cũ rời group và member mới tham gia. Nếu dừng nhiều instance cùng lúc, group có thể rebalance nhiều lần và backlog tăng.

Một quy trình deploy ổn định:

1. Xác nhận group đang hoạt động và số member hiện tại.
2. Triển khai từng instance hoặc theo batch nhỏ.
3. Cho listener container dừng có kiểm soát để consumer rời group đúng lifecycle.
4. Chờ instance mới khởi động, join group và nhận partition.
5. Kiểm tra group state, member count và assignment sau mỗi batch.
6. Theo dõi lỗi listener, commit, rebalance và downstream.
7. Tiếp tục batch tiếp theo khi group ổn định.

Spring Kafka listener container hỗ trợ lifecycle start/stop. Có thể đặt `shutdownTimeout` trong `ContainerProperties` để giới hạn thời gian chờ khi dừng container; giá trị phù hợp phải dựa trên thời gian xử lý và semantics commit.

Không kill -9 hoặc terminate đồng loạt mọi instance trong một group nếu không cần thiết. Nếu xử lý record đang chạy, hãy xác nhận container có thời gian hoàn tất hoặc cơ chế xử lý lại an toàn.

## 14. Reset offset là thao tác vận hành có rủi ro

Reset offset thay đổi vị trí mà group sẽ đọc tiếp. Đây là thao tác có thể làm bỏ qua record hoặc phát lại record đã xử lý; chỉ thực hiện khi đã xác định mục đích, phạm vi topic/partition và có phê duyệt vận hành phù hợp.

Ví dụ xem trước việc reset về earliest:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Sau khi xem kết quả dry-run, xác nhận group không có consumer active và hiểu tác động trước khi chạy với `--execute`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
```

Các lựa chọn reset khác có thể gồm `--to-latest`, `--shift-by`, `--to-offset` hoặc `--to-datetime` tùy Kafka version. Đọc `--help` của CLI và luôn dùng `--dry-run` trước. Một số phiên bản yêu cầu group không có member active mới cho phép reset.

Trước khi thực hiện, cần:

- Ghi lại committed offsets hiện tại.
- Xác định rõ topic và partition bị tác động.
- Đánh giá khả năng duplicate side effect khi replay.
- Xác nhận retention còn giữ record cần đọc lại.
- Có kế hoạch rollback hoặc khôi phục offset đã lưu.
- Theo dõi consumer sau khi reset và xác minh dữ liệu nghiệp vụ.

Không reset offset chỉ để làm lag giảm hoặc để xóa một cảnh báo dashboard.

## 15. ACL và quyền quan sát consumer group

Client có thể xác thực thành công nhưng không có quyền mô tả group hoặc đọc committed offsets. Khi dùng SASL/ACL, công cụ quản trị và AdminClient phải có principal được cấp đúng quyền.

Các quyền thường liên quan:

- Quyền `Describe` trên group để xem metadata group.
- Quyền `Read` trên group cho các thao tác liên quan committed offsets/consumer group theo authorization semantics của Kafka version.
- Quyền `Describe` trên topic để đọc metadata.
- Quyền phù hợp trên cluster cho các thao tác quản trị đặc thù.

Không cấp `ClusterAction` hoặc quyền superuser cho dashboard chỉ để xem group. Hãy cấp đúng ACL cần thiết và kiểm tra bằng principal của công cụ quan sát, không dùng tài khoản administrator chung cho ứng dụng nghiệp vụ.

## 16. Chẩn đoán các tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Group ở `Empty` | Không có consumer active, listener chưa start hoặc toàn bộ instance đã dừng | Kiểm tra registry, deployment, broker connectivity và group ID |
| Group ở `PreparingRebalance` lâu | Member không join/sync hoàn tất hoặc rebalance liên tục | Kiểm tra log coordinator, network, heartbeat và member |
| Số member ít hơn số instance | Listener không chạy, group ID khác nhau hoặc startup lỗi | Kiểm tra `@KafkaListener`, factory và application logs |
| Nhiều member idle | Số member lớn hơn số partition hoặc subscription không có dữ liệu | So sánh partition count và assignment |
| Một member sở hữu nhiều partition hơn | Assignor, subscription nhiều topic hoặc partition count không đều | Kiểm tra assignment và assignor |
| Rebalance lặp lại | Poll interval, heartbeat, restart hoặc network không ổn định | Kiểm tra thời gian listener, timeout và deployment |
| Member bị fencing | `group.instance.id` bị trùng hoặc member cũ chưa rời group | Kiểm tra identity của từng replica |
| Group ổn định nhưng dữ liệu không xử lý | Listener bị pause, lỗi bị nuốt hoặc downstream bị block | Kiểm tra container state, listener logs và processing metrics |
| Không xem được group bằng AdminClient | ACL thiếu quyền hoặc broker không sẵn sàng | Kiểm tra security config và authorization |
| Sau reset offset có duplicate | Consumer đọc lại record đã xử lý | Kiểm tra idempotency key và side effect |

## 17. Runbook theo dõi consumer group

Khi có cảnh báo consumer group, có thể thực hiện theo trình tự:

1. Xác định đúng group ID, topic và môi trường.
2. Kiểm tra trạng thái group bằng `kafka-consumer-groups.sh --describe --state`.
3. Kiểm tra số member và partition assignment bằng `--members --verbose`.
4. Đối chiếu số member dự kiến với số instance và concurrency trong Spring Kafka.
5. Kiểm tra log ứng dụng quanh thời điểm member join/leave, rebalance và listener exception.
6. Kiểm tra heartbeat, `max.poll.interval.ms`, thời gian xử lý batch và network.
7. Kiểm tra committed offset và consumer lag để biết tiến độ group.
8. Kiểm tra downstream, database và thread pool nếu consumer đã fetch nhưng xử lý chậm.
9. Nếu cần thay đổi offset, lưu offset hiện tại, chạy dry-run và đánh giá replay trước khi execute.
10. Sau khi khắc phục, xác nhận group về trạng thái ổn định, assignment đầy đủ và commit tiếp tục tiến triển.

Ghi lại thời điểm, group ID, member ID, client ID, topic-partition, trạng thái group và hành động đã thực hiện trong incident record. Tránh ghi credential hoặc payload nhạy cảm vào log vận hành.

## 18. Checklist vận hành consumer group

1. Đặt group ID riêng cho từng workload độc lập; dùng cùng group ID cho các replica chia tải.
2. Đặt client ID có thể nhận diện service và instance.
3. Theo dõi group state, member count và partition assignment.
4. Kiểm tra concurrency so với partition count.
5. Theo dõi rebalance rate và nguyên nhân member rời group.
6. Đặt `heartbeat.interval.ms`, `session.timeout.ms` và `max.poll.interval.ms` dựa trên tải thực tế.
7. Dùng `group.instance.id` duy nhất nếu áp dụng static membership.
8. Triển khai rolling và graceful shutdown để giảm rebalance không cần thiết.
9. Dùng AdminClient/CLI với ACL tối thiểu để quan sát group.
10. Lưu committed offset trước khi thực hiện reset.
11. Chạy `--dry-run` trước mọi thao tác reset và kiểm tra group không active.
12. Theo dõi lag, commit, listener latency và downstream cùng trạng thái group.

Theo dõi consumer group là quan sát membership và cách Kafka phân phối partition cho các consumer, còn consumer lag là quan sát tiến độ đọc so với log. Kết hợp hai góc nhìn với lifecycle của listener container, rebalance, commit và sức khỏe downstream giúp đội vận hành xác định đúng nguyên nhân khi một luồng Spring Kafka không còn xử lý ổn định.
