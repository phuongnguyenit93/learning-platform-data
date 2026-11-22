# Consumer group rebalance liên tục

## 1. Hiện tượng và tác động

Consumer group rebalance là quá trình Kafka phân phối lại các partition cho các consumer đang là thành viên của cùng group. Một lần rebalance ngắn khi consumer mới tham gia, consumer rời group hoặc topic thay đổi là hành vi bình thường.

Vấn đề xuất hiện khi group liên tục chuyển giữa các trạng thái chuẩn bị rebalance, đồng bộ assignment và hoạt động ổn định. Trong khoảng thời gian rebalance, một số hoặc toàn bộ consumer có thể tạm ngừng nhận record tùy giao thức assignment. Hệ quả thường gặp:

- Listener xử lý chậm hoặc ngừng nhận record trong từng khoảng ngắn.
- Consumer lag tăng dù số lượng message không thay đổi nhiều.
- Partition liên tục đổi owner, cache cục bộ và trạng thái xử lý bị khởi tạo lại.
- Offset có thể được xử lý lại nếu record đã chạy nhưng offset chưa commit.
- Throughput giảm, latency tăng và retry có thể xuất hiện nhiều hơn.
- Log liên tục có `Revoking previously assigned partitions`, `Adding newly assigned partitions`, `Preparing to rebalance` hoặc `Rebalance in progress`.

Không phải mọi log rebalance đều là lỗi. Cần xác định group có ổn định sau khi deployment hoặc scale hay đang rebalance lặp lại trong trạng thái tải bình thường.

## 2. Rebalance diễn ra như thế nào?

Với consumer group dùng cơ chế group management, Kafka coordinator theo dõi các thành viên và quyết định partition assignment. Khi membership hoặc subscription thay đổi, group cần tính lại assignment.

```text
Consumer A             Group Coordinator             Consumer B
    |                          |                          |
    |--- JoinGroup ----------->|                          |
    |                          |<---------- JoinGroup -----|
    |                          |                          |
    |<------ assignment / SyncGroup ----------------------|
    |                          |                          |
    |==== A xử lý partition 0  |  B xử lý partition 1 ====|
    |                          |                          |
    |--- A rời group --------->|                          |
    |                          |                          |
    |<------ rebalance / assignment mới ------------------|
    |                          |                          |
    |==== B nhận thêm partition 0 =========================|
```

Trong eager rebalance, các member thường phải nhả assignment cũ trước khi nhận assignment mới. Cooperative rebalance chỉ thu hồi các partition thực sự cần chuyển, nhờ đó giảm thời gian gián đoạn. Kafka 4.0 còn có consumer group protocol mới với assignment tăng dần do broker điều phối.

Rebalance không phải thao tác xóa record. Record vẫn ở Kafka log; điều cần chú ý là ownership và offset commit để tránh xử lý lặp hoặc bỏ sót do ứng dụng commit sai.

## 3. Những nguyên nhân thường gặp

| Nhóm nguyên nhân | Dấu hiệu | Hướng điều tra đầu tiên |
|---|---|---|
| Listener xử lý quá lâu | Rebalance xuất hiện sau một poll có nhiều record hoặc xử lý DB/HTTP chậm | Đo thời gian xử lý và `max.poll.interval.ms` |
| Không nhận heartbeat | Consumer bị loại sau GC pause, CPU starvation, network interruption hoặc broker không nhận heartbeat | Kiểm tra session timeout, heartbeat, JVM và network |
| Pod/process restart liên tục | Rebalance trùng thời điểm rollout, liveness probe hoặc autoscaling | Kiểm tra lịch sử restart và deployment events |
| Consumer instance ID trùng | Static member bị fencing hoặc liên tục thay thế nhau | Kiểm tra `group.instance.id` trên từng instance |
| Concurrency/replica thay đổi | Member và assignment thay đổi theo số replica hoặc listener container | So sánh số consumer với số partition và cấu hình deployment |
| Topic subscription thay đổi | Group rebalance sau khi thêm partition hoặc topic khớp pattern | Kiểm tra metadata, topic pattern và partition count |
| Coordinator/broker/network bất ổn | Nhiều consumer hoặc nhiều group cùng gặp lỗi coordinator/disconnect | Kiểm tra broker log, coordinator và mạng |
| Retry/backoff chặn poll | Rebalance xuất hiện khi downstream lỗi hoặc retry delay dài | Kiểm tra error handler và backoff strategy |
| Rebalance protocol/assignor không tương thích | Member không đồng thuận assignor hoặc protocol | Kiểm tra Kafka client version, `group.protocol` và assignor |

Hãy chọn nguyên nhân dựa trên timestamp, member ID, client ID và log cùng thời điểm. Không tăng timeout ngay khi thấy rebalance; điều đó có thể che khuất nguyên nhân gốc và kéo dài thời gian phát hiện consumer chết.

## 4. Phân biệt `max.poll.interval.ms`, `session.timeout.ms` và heartbeat

Đây là ba cấu hình thường bị nhầm lẫn trong consumer group dùng classic protocol.

| Cấu hình | Kiểm soát điều gì? | Rebalance xảy ra khi nào? |
|---|---|---|
| `max.poll.interval.ms` | Khoảng thời gian tối đa giữa hai lần gọi `poll()` | Consumer không gọi `poll()` kịp thời, thường do xử lý record/batch quá lâu |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trước khi coi member đã mất | Broker không nhận heartbeat trong thời gian session timeout |
| `heartbeat.interval.ms` | Chu kỳ consumer gửi heartbeat trong classic protocol | Không phải thời gian xử lý record; giá trị phải thấp hơn session timeout |

Trong classic protocol, heartbeat được duy trì độc lập với phần xử lý listener. Vì vậy consumer có thể vẫn gửi heartbeat trong lúc listener đang chạy, nhưng nếu không gọi `poll()` trước `max.poll.interval.ms`, Kafka vẫn xem consumer không còn tiến triển và bắt đầu rebalance.

Ví dụ: `max.poll.interval.ms = 300000` tương ứng 5 phút. Nếu một poll trả về 100 record và listener mất trung bình 4 giây mỗi record, tổng thời gian xử lý có thể vượt 5 phút dù từng record riêng lẻ đều nhanh.

Với Kafka consumer protocol mới (`group.protocol=consumer`), heartbeat interval và session timeout được điều khiển phía broker. Các thuộc tính client `heartbeat.interval.ms` và `session.timeout.ms` không còn được dùng theo cách classic; hãy xem cấu hình `group.consumer.heartbeat.interval.ms` và `group.consumer.session.timeout.ms` ở broker.

## 5. Chẩn đoán listener xử lý quá lâu

Với record listener, Spring Kafka gọi listener trên consumer thread. Các record được trả về từ một lần `poll()` được chuyển đến listener; consumer tiếp tục poll sau khi container hoàn thành phần xử lý cần thiết của poll đó. Với batch listener, listener xử lý cả batch trước khi quay lại poll.

Ước lượng thời gian xử lý một poll:

\[
T_{poll} \approx N \times T_{record} + T_{overhead}
\]

Trong đó:

- `N` là số record tối đa được trả về trong một poll, bị giới hạn bởi `max.poll.records`.
- `T_record` là thời gian xử lý một record; nên dùng p95/p99 thay vì chỉ dùng trung bình.
- `T_overhead` gồm commit, retry, serialization phụ, logging và thời gian scheduling.

Giữ `T_poll` thấp hơn `max.poll.interval.ms` với biên an toàn đủ lớn. Nếu p99 gần sát timeout, một lần gọi database chậm hoặc JVM pause có thể khiến consumer bị loại khỏi group.

### Ví dụ cấu hình giảm lượng record mỗi poll

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      properties:
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 50
```

`max.poll.records` mặc định của Kafka client hiện hành là 500. Hạ xuống 50 có thể giảm thời gian xử lý một poll, nhưng cũng làm giảm lượng record lấy ra mỗi lần và có thể giảm throughput nếu xử lý từng record rất nhanh. Hãy đo trước và sau khi thay đổi.

`max.poll.records` giới hạn số record được trả về trong một lần `poll()`; nó không giới hạn trực tiếp dữ liệu broker fetch vào consumer. Consumer có thể cache dữ liệu đã fetch và trả dần qua các lần poll tiếp theo.

### Tối ưu phần xử lý listener

- Đo thời gian xử lý theo listener và theo loại nghiệp vụ.
- Đặt timeout cho HTTP/database call để một record không chặn consumer vô hạn.
- Tránh `Thread.sleep()` hoặc chờ Future không giới hạn trong listener.
- Dùng batch database operation khi phù hợp để giảm round-trip.
- Giảm log payload lớn hoặc serialization không cần thiết.
- Tách tác vụ chậm thành workflow riêng nếu thiết kế nghiệp vụ cho phép.
- Nếu xử lý bất đồng bộ, phải thiết kế acknowledgment, retry và backpressure rõ ràng; không trả khỏi listener trước khi công việc được bảo đảm an toàn rồi mặc định offset đã phản ánh kết quả.

## 6. Cấu hình timeout theo classic protocol

Ví dụ cấu hình cho Spring Boot khi dùng Kafka classic group protocol:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      properties:
        "[group.protocol]": classic
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 50
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 3000
```

Giá trị trên chỉ là điểm bắt đầu minh họa, không phải cấu hình chung cho mọi hệ thống. `heartbeat.interval.ms` thường không cao hơn một phần ba `session.timeout.ms`. Broker cũng giới hạn giá trị session timeout bằng `group.min.session.timeout.ms` và `group.max.session.timeout.ms`.

Không tăng `session.timeout.ms` để xử lý listener chậm do `max.poll.interval.ms`. Hai timeout bảo vệ hai điều kiện khác nhau. Nếu listener mất 8 phút để xử lý một poll, tăng session timeout lên 2 phút vẫn không giải quyết việc poll interval 5 phút bị vượt.

## 7. Kafka consumer protocol mới và KIP-848

Spring for Apache Kafka 4.0 hỗ trợ consumer group protocol mới của Apache Kafka 4.0. Có thể bật bằng:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.protocol]": consumer
```

Protocol mới sử dụng server-side incremental assignment, giúp giảm thời gian gián đoạn khi group thay đổi. Tuy nhiên, cần bảo đảm broker, Kafka client và Spring Kafka tương thích trước khi bật.

Khi dùng protocol mới:

- Broker điều khiển heartbeat interval và session timeout bằng `group.consumer.heartbeat.interval.ms` và `group.consumer.session.timeout.ms`.
- `heartbeat.interval.ms` và `session.timeout.ms` ở client không được hỗ trợ theo cách classic.
- Partition assignment được thực hiện phía server; custom client assignor trong `partition.assignment.strategy` bị bỏ qua.
- `onPartitionsAssigned()` có thể được gọi nhiều lần với các tập partition nhỏ hơn vì assignment tăng dần.
- `ConsumerAwareRebalanceListener` vẫn hoạt động với protocol mới.

Không chuyển một consumer group đang chạy sang protocol mới bằng một thay đổi cấu hình đơn lẻ nếu chưa kiểm tra compatibility và quy trình rollout. Trước hết xác nhận phiên bản broker/client, server assignor và khả năng tương thích của toàn bộ member trong group.

## 8. Cooperative rebalance với classic protocol

Nếu vẫn dùng classic protocol, có thể cân nhắc `CooperativeStickyAssignor` để giảm số partition phải thu hồi khi group thay đổi:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.protocol]": classic
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Cooperative assignment giữ lại các partition không cần di chuyển và chỉ thu hồi partition cần chuyển. Nó giảm tác động của một lần rebalance nhưng không ngăn rebalance do consumer liên tục rời group, poll quá hạn hoặc mất heartbeat.

Tất cả member trong group phải hỗ trợ và đồng thuận cooperative protocol. Không triển khai assignor không tương thích giữa các phiên bản instance đang chạy. Với Kafka client hiện hành, default strategy có thể chứa cả `RangeAssignor` và `CooperativeStickyAssignor` để hỗ trợ quá trình chuyển đổi từng bước; nếu cấu hình tường minh một assignor, cần lập kế hoạch rollout đồng bộ.

## 9. Static membership và `group.instance.id`

Mặc định consumer tham gia group như dynamic member. Khi một process khởi động lại, group có thể rebalance để phân phối lại partition.

Static membership dùng `group.instance.id` duy nhất cho từng consumer instance. Nếu process tạm thời dừng rồi khởi động lại trong session timeout, Kafka có thể giữ membership để giảm rebalance do restart ngắn.

Ví dụ cấu hình:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": ${KAFKA_INSTANCE_ID}
        "[session.timeout.ms]": 60000
```

Ví dụ này giả định classic group protocol. Nếu dùng `group.protocol=consumer`, session timeout được cấu hình ở broker bằng `group.consumer.session.timeout.ms`, không đặt bằng consumer client property `session.timeout.ms`.

Giá trị `KAFKA_INSTANCE_ID` phải khác nhau giữa các process thuộc cùng group. Với Kubernetes StatefulSet, có thể dùng ordinal/pod identity ổn định. Với Deployment autoscaling, cần tạo ID ổn định và duy nhất theo từng pod; không dùng cùng một chuỗi cố định cho tất cả replica.

Spring Kafka hỗ trợ static membership khi concurrency lớn hơn 1; container tự thêm hậu tố cho từng child consumer. Tuy vậy, ID gốc của mỗi application instance vẫn phải duy nhất giữa các pod.

Lưu ý:

- Hai consumer dùng cùng `group.instance.id` sẽ xung đột; member cũ có thể bị fencing.
- Session timeout dài làm Kafka mất nhiều thời gian hơn để phát hiện một static member thực sự đã chết.
- Nếu static member vượt `max.poll.interval.ms`, consumer ngừng gửi heartbeat và partition chỉ được giao lại sau khi session timeout hết hạn; việc này làm chậm quá trình phục hồi.
- Static membership giảm rebalance do restart ngắn; không chữa được listener vượt `max.poll.interval.ms`.
- Không bật static membership nếu không quản lý được identity duy nhất và vòng đời instance.

## 10. Kiểm tra concurrency và số partition

Trong Spring Kafka, `ConcurrentMessageListenerContainer` tạo nhiều child `KafkaMessageListenerContainer`, mỗi child có consumer riêng. Thuộc tính `concurrency` điều khiển số consumer được tạo bởi một listener container.

Ví dụ:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
```

Nếu topic có 3 partition, concurrency 3 có thể sử dụng cả ba consumer. Nếu concurrency 6 nhưng topic chỉ có 3 partition, tối đa 3 consumer nhận partition; các consumer còn lại không có partition để xử lý.

Tăng concurrency hoặc số pod trong cùng group sẽ thay đổi membership và thường tạo một lần rebalance. Đây là hành vi dự kiến khi scale. Nếu số pod dao động liên tục do autoscaler hoặc liveness probe, group có thể không có đủ thời gian ổn định.

Kiểm tra:

- Số partition của topic.
- Số child consumer từ `concurrency` của listener container.
- Số replica của service.
- Số member thực tế trong group.
- Số partition được giao cho từng member.

Không tăng concurrency vượt số partition với kỳ vọng throughput sẽ tăng. Nhiều consumer idle không tự gây rebalance liên tục, nhưng chúng làm tăng số member và độ phức tạp vận hành khi deployment hoặc scale.

## 11. Kiểm tra restart, deployment và health probe

Rebalance thường tăng trong các thời điểm:

- Rolling deployment thay thế nhiều pod.
- Liveness probe restart ứng dụng do endpoint health không phản ánh đúng tình trạng consumer.
- Readiness/lifecycle hook làm listener container stop/start liên tục.
- Autoscaler scale lên/xuống liên tục theo tải ngắn hạn.
- JVM bị OOM, CPU throttling hoặc GC pause kéo dài.
- Container bị kill trước khi listener container dừng graceful.

Đối chiếu timestamp của `ConsumerStartedEvent`, `ConsumerStoppedEvent`, pod restart count, deployment rollout và log rebalance. Nếu rebalance chỉ xuất hiện một lần trong mỗi đợt rollout, đây có thể là hành vi bình thường.

Với Kubernetes:

- Đặt termination grace period đủ để ứng dụng dừng listener container và đóng consumer.
- Dùng preStop/lifecycle hook phù hợp với quy trình shutdown của ứng dụng.
- Tránh liveness probe restart service chỉ vì Kafka tạm thời mất kết nối hoặc downstream chậm.
- Tách readiness (khả năng nhận traffic mới) khỏi liveness (process còn sống).
- Điều chỉnh rollout `maxUnavailable`/`maxSurge` để tránh thay thế quá nhiều consumer cùng lúc.
- Theo dõi CPU throttling, memory pressure, OOMKilled và GC pause.

Không cố giữ pod unhealthy chỉ để tránh rebalance. Cần sửa nguyên nhân health probe và bảo đảm shutdown có kiểm soát.

## 12. Kiểm tra network và group coordinator

Nếu consumer mất kết nối broker hoặc coordinator, heartbeat/join request có thể thất bại và group thay đổi membership.

Kiểm tra:

- DNS resolution và advertised listener của broker.
- Packet loss, network latency, connection reset và firewall idle timeout.
- Broker coordinator có restart hoặc chuyển leader liên tục không.
- CPU, heap, request queue và network của broker.
- Log `NotCoordinator`, `CoordinatorNotAvailable`, `DisconnectException`, `TimeoutException` hoặc lỗi authentication/authorization.
- Nhiều group cùng bị ảnh hưởng hay chỉ một group.

Nếu nhiều group trên cùng cluster cùng mất ổn định tại một thời điểm, điều tra broker/coordinator/network trước khi thay cấu hình riêng của từng consumer. Nếu chỉ một group gặp lỗi, tập trung vào membership, listener và cấu hình của group đó.

Không tăng reconnect timeout hoặc retry vô hạn để che lỗi coordinator. Phải xác định broker nào là coordinator, client đang kết nối broker nào và request nào bị timeout.

## 13. Rebalance do retry và backoff chặn consumer thread

Khi listener ném exception, Spring Kafka error handler có thể retry record theo `BackOff`. `DefaultErrorHandler` mặc định dùng backoff handler chờ trên thread xử lý. Nếu khoảng chờ cộng với thời gian xử lý vượt `max.poll.interval.ms`, consumer có thể bị rebalance.

Với Spring Kafka 2.9 trở lên, `ContainerPausingBackOffHandler` có thể pause listener container trong thời gian backoff rồi resume. Container vẫn poll theo cơ chế pause để duy trì membership. Độ chính xác thời gian chờ phụ thuộc `pollTimeout`.

Ví dụ cấu hình ý tưởng:

```java
@Bean
ListenerContainerPauseService listenerContainerPauseService(
        ListenerContainerRegistry registry,
        TaskScheduler taskScheduler) {

    return new ListenerContainerPauseService(registry, taskScheduler);
}

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> template,
        ListenerContainerPauseService pauseService) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(30_000L, 2L),
            new ContainerPausingBackOffHandler(pauseService));
}
```

Ví dụ trên tạo `ListenerContainerPauseService` từ `ListenerContainerRegistry` và `TaskScheduler`, sau đó truyền service này vào `ContainerPausingBackOffHandler`. Bảo đảm ứng dụng có một `TaskScheduler` bean. Kiểm tra constructor và API theo phiên bản Spring Kafka của dự án.

Với retry delay dài hoặc cần tách retry khỏi luồng chính, có thể cân nhắc non-blocking retry topics (`@RetryableTopic`). Cách này có trade-off về ordering, topic vận hành và semantics xử lý; cần thiết kế theo yêu cầu nghiệp vụ.

Không dùng `Thread.sleep()` trực tiếp trong listener để retry. Cách đó chặn poll loop, khó quản lý offset và dễ làm tăng rebalance.

## 14. Ghi nhận rebalance bằng ConsumerAwareRebalanceListener

Spring Kafka cho phép cài đặt `ConsumerRebalanceListener` thông qua `ContainerProperties`. `ConsumerAwareRebalanceListener` cung cấp callback trước/sau commit khi partition bị revoke, callback khi partition được assign và callback khi partition bị lost.

```java
@Bean
ConsumerAwareRebalanceListener orderRebalanceListener() {
    return new ConsumerAwareRebalanceListener() {

        @Override
        public void onPartitionsRevokedBeforeCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            log.info("Partitions revoked before commit: {}", partitions);
        }

        @Override
        public void onPartitionsRevokedAfterCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            log.info("Partitions revoked after commit: {}", partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            log.info("Partitions assigned: {}", partitions);
        }

        @Override
        public void onPartitionsLost(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            log.warn("Partitions lost: {}", partitions);
        }
    };
}
```

Gắn listener vào factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        ConsumerAwareRebalanceListener orderRebalanceListener) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setConsumerRebalanceListener(orderRebalanceListener);
    return factory;
}
```

`onPartitionsRevokedBeforeCommit()` được gọi ngay trước khi container commit các offset đang chờ. `onPartitionsRevokedAfterCommit()` chạy sau commit. `onPartitionsLost()` có từ Spring Kafka 2.4 và biểu thị partition đã mất quyền sở hữu; không gọi `onPartitionsRevoked()` từ callback này vì container có thể tự xử lý revoke sau đó.

Giữ callback ngắn và không gọi HTTP/database chậm. Callback chạy trên consumer thread; xử lý lâu ở đây cũng có thể làm group mất ổn định. Không tự commit offset hoặc thay đổi consumer position trong callback nếu container đang quản lý offset, trừ khi ứng dụng có thiết kế thủ công và hiểu rõ semantics.

Với consumer protocol mới, `onPartitionsAssigned()` có thể được gọi nhiều lần với tập partition nhỏ hơn do assignment tăng dần. Không giả định callback chỉ được gọi đúng một lần cho toàn bộ assignment.

## 15. Theo dõi poll bị treo bằng Spring Application Events

Spring Kafka có `NonResponsiveConsumerEvent` khi consumer có vẻ bị kẹt trong `poll()`. Event này khác `ListenerContainerIdleEvent`: idle event chỉ nói rằng không có message được giao trong khoảng thời gian cấu hình; nó không có nghĩa consumer bị treo.

Có thể cấu hình monitor trên listener container:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMonitorInterval(30);
    factory.getContainerProperties().setNoPollThreshold(3.0);
    factory.getContainerProperties().setPollTimeout(5_000L);
    return factory;
}
```

`monitorInterval` tính bằng giây và mặc định là 30; `noPollThreshold` mặc định là 3.0; `pollTimeout` tính bằng milliseconds. Event được phát khi consumer có vẻ không trở lại từ `poll()` trong ngưỡng tương ứng. Nên để `noPollThreshold` lớn hơn 1.0 để tránh cảnh báo giả do race condition.

Có thể lắng nghe event:

```java
@Component
public class KafkaConsumerDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerDiagnostics.class);

    @EventListener
    public void onNonResponsiveConsumer(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer not responsive: listenerId={}, timeSinceLastPoll={} ms, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions());
    }
}
```

Event cho biết container/listener ID, thời gian từ lần poll cuối và partition liên quan. Hãy dùng nó để kích hoạt điều tra. Không tự động restart container chỉ vì nhận một event đơn lẻ; xác minh poll thread, broker connectivity và tình trạng ứng dụng trước.

## 16. Đọc trạng thái consumer group bằng CLI

Dùng `kafka-consumer-groups.sh` để kiểm tra trạng thái group, member và partition assignment. Ví dụ trên Linux/macOS:

```bash
# Xem trạng thái group và số member
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-service --state

# Xem danh sách consumer member
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-service --members

# Xem partition được giao cho từng member
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-service --members --verbose

# Xem offset và lag theo topic-partition
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-service
```

Với Windows, dùng script `bin\windows\kafka-consumer-groups.bat` và cùng các tham số tương ứng.

Diễn giải kết quả:

- `STATE=Stable` và member/assignment không đổi qua nhiều lần kiểm tra: group đang ổn định.
- Member count tăng/giảm liên tục: process/pod join hoặc leave liên tục.
- Assignment thay đổi liên tục: partition ownership đang bị phân phối lại.
- Có member nhưng `#PARTITIONS=0`: consumer hiện không được giao partition, có thể do số member lớn hơn partition hoặc đang trong quá trình assignment.
- Lag tăng đồng thời rebalance rate tăng: consumer có thể đang mất thời gian phục hồi assignment thay vì xử lý record.

Lấy kết quả nhiều lần cách nhau vài giây để nhận biết trạng thái thay đổi. Một lần chụp trạng thái không đủ kết luận group đang rebalance liên tục.

## 17. Theo dõi metrics của consumer

Kafka Java client cung cấp consumer metrics qua JMX hoặc `KafkaConsumer.metrics()`. Những metric quan trọng:

| Metric | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| `time-between-poll-avg` | Thời gian trung bình giữa các lần poll | Tăng cao khi listener xử lý lâu |
| `time-between-poll-max` | Khoảng cách poll lớn nhất | Tiến gần `max.poll.interval.ms` |
| `last-poll-seconds-ago` | Số giây từ lần poll gần nhất | Tăng bất thường khi consumer bị block |
| `poll-idle-ratio-avg` | Tỷ lệ thời gian poll thread idle | Giảm mạnh có thể cho thấy xử lý chiếm nhiều thời gian |
| `rebalance-total` | Tổng số rebalance consumer tham gia | Tăng liên tục trong steady state |
| `rebalance-rate-per-hour` | Tốc độ rebalance theo giờ | Dùng để phát hiện churn |
| `rebalance-latency-avg/max` | Thời gian rebalance | Tăng khi coordinator hoặc assignment chậm |
| `failed-rebalance-total` | Số lần rebalance thất bại | Tăng cho thấy group join/sync không ổn định |
| `last-rebalance-seconds-ago` | Thời gian từ rebalance gần nhất | Liên tục trở về thấp khi group churn |
| `assigned-partitions` | Số partition consumer đang sở hữu | Tụt về 0 hoặc thay đổi liên tục |

Không chỉ nhìn `rebalance-total` tuyệt đối vì counter tăng theo vòng đời process. Hãy quan sát rate, delta theo thời gian và đối chiếu với số member, poll latency và application restart.

## 18. Metrics phía broker và coordinator

Broker cũng cung cấp metrics về group coordinator. Với classic group protocol, theo dõi số group ở trạng thái `PreparingRebalance`, `CompletingRebalance`, `Stable`, `Empty` và `Dead`.

Với consumer protocol mới, Kafka có các metric group coordinator như:

- `consumer-group-count` theo state `Empty`, `Assigning`, `Reconciling`, `Stable`, `Dead`.
- `consumer-group-rebalance-rate`.
- `consumer-group-rebalance-count`.
- `group-count` theo protocol `classic`, `consumer` hoặc `streams`.

Nếu coordinator metric cho thấy nhiều group đồng thời rebalance, kiểm tra tải broker và group coordinator. Nếu chỉ một group tăng rebalance count, điều tra member của group đó trước.

## 19. Quy trình điều tra từng bước

1. **Xác định group:** ghi lại `group.id`, topic, listener ID, thời gian bắt đầu và tần suất rebalance.
2. **Kiểm tra group state:** chạy CLI `--state`, `--members` và `--members --verbose` nhiều lần.
3. **Đối chiếu member lifecycle:** so sánh client ID, host, pod restart, deployment và consumer start/stop event.
4. **Kiểm tra poll interval:** đọc `time-between-poll-max`, `last-poll-seconds-ago` và p95/p99 listener duration.
5. **Kiểm tra heartbeat/session:** tìm disconnect, heartbeat timeout, network issue và JVM pause.
6. **Kiểm tra tải xử lý:** đo database/HTTP latency, retry delay, batch size và `max.poll.records`.
7. **Kiểm tra topology:** so sánh số partition, consumer concurrency và số replica.
8. **Kiểm tra identity:** xác minh `group.instance.id` không trùng nếu dùng static membership.
9. **Kiểm tra protocol:** xác nhận tất cả member dùng compatible Kafka client, assignor và `group.protocol`.
10. **Kiểm tra coordinator/broker:** nếu nhiều group bị ảnh hưởng, xem broker log, coordinator và network.
11. **Thay đổi một yếu tố:** ví dụ hạ `max.poll.records` hoặc tối ưu listener, sau đó theo dõi lại rebalance rate.
12. **Xác nhận ổn định:** group ở `Stable`, assignment ổn định, poll interval có biên an toàn và lag giảm.

Không reset offset để chữa rebalance. Reset offset thay đổi vị trí đọc và có thể gây mất hoặc xử lý lại dữ liệu; nó không sửa nguyên nhân membership churn.

## 20. Bảng triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
|---|---|---|
| Rebalance sau mỗi batch lớn | Thời gian xử lý batch vượt `max.poll.interval.ms` | Hạ `max.poll.records`, giảm batch work, tăng timeout sau khi đo |
| Rebalance trùng lúc DB chậm | Listener chờ database hoặc HTTP | Đặt dependency timeout, bulkhead, tối ưu query và retry có kiểm soát |
| Rebalance trùng lúc rollout | Dynamic member rời/join group | Rolling deployment có kiểm soát; cân nhắc static membership/cooperative assignor |
| Rebalance sau GC pause | JVM dừng lâu khiến heartbeat hoặc poll không kịp | Phân tích GC log, heap, allocation và pause time |
| `FencedInstanceIdException` | Nhiều consumer dùng cùng `group.instance.id` | Cấp ID duy nhất cho mỗi process/consumer |
| Group liên tục `PreparingRebalance` | Member join/leave hoặc heartbeat/session timeout | Xem log coordinator, member list, session timeout và restart |
| Group `Stable` nhưng consumer lag tăng | Có thể là xử lý chậm, partition nóng hoặc throughput không đủ | Kiểm tra per-partition lag và listener duration |
| Nhiều group cùng rebalance | Broker/coordinator/network không ổn định | Điều tra broker, network và group coordinator |
| Rebalance trong lúc retry dài | Backoff chặn consumer thread | Dùng `ContainerPausingBackOffHandler` hoặc retry topic |
| Consumer được tạo nhưng không nhận partition | Số consumer vượt partition hoặc subscription không khớp | Kiểm tra partition count, group ID và topic subscription |
| Assignment callback chạy nhiều lần | Cooperative/KIP-848 incremental assignment | Viết callback idempotent, không giả định callback một lần |

## 21. Các cấu hình không nên thay đổi tùy tiện

- **Không tăng `max.poll.interval.ms` vô hạn:** consumer có thể giữ group lâu hơn dù listener bị treo, làm giảm khả năng phục hồi.
- **Không tăng `session.timeout.ms` nếu chưa đo heartbeat:** thời gian phát hiện member chết sẽ dài hơn.
- **Không giảm `heartbeat.interval.ms` quá thấp:** tăng tải coordinator và không giải quyết listener xử lý chậm.
- **Không bật static membership với ID trùng:** member sẽ fencing lẫn nhau.
- **Không đổi assignor giữa các instance:** có thể gây lỗi protocol khi các member không tương thích.
- **Không tăng concurrency vượt partition để mong tăng throughput:** consumer dư sẽ idle.
- **Không gọi `Consumer` từ thread khác:** Kafka consumer không thread-safe; để listener container quản lý consumer thread.
- **Không chạy tác vụ chặn trong rebalance callback:** callback nằm trên consumer thread và có thể kéo dài rebalance.
- **Không tắt auto/commit hoặc đổi AckMode chỉ để giảm log rebalance:** offset semantics phải theo yêu cầu xử lý và transaction.

## 22. Checklist vận hành

- [ ] Group ổn định sau deployment và scale event.
- [ ] `time-between-poll-max` thấp hơn `max.poll.interval.ms` với biên an toàn.
- [ ] Listener p99 và batch processing duration được đo.
- [ ] `max.poll.records` phù hợp với thời gian xử lý thực tế.
- [ ] `session.timeout.ms` và heartbeat phù hợp với classic protocol, hoặc broker-side timeout phù hợp với consumer protocol.
- [ ] Consumer `group.instance.id` duy nhất nếu dùng static membership.
- [ ] Partition count đủ cho mức concurrency cần thiết.
- [ ] Retry/backoff không chặn consumer thread vượt poll interval.
- [ ] Broker coordinator và network không có disconnect bất thường.
- [ ] Rebalance rate, latency và failed rebalance được dashboard/alert.
- [ ] Consumer group CLI cho thấy member và partition assignment ổn định.
- [ ] Rebalance listener callback không thực hiện công việc chậm hoặc commit thủ công ngoài thiết kế.

## 23. Tổng kết

- Rebalance là cơ chế phân phối lại partition; một lần rebalance khi member hoặc topic thay đổi là bình thường.
- Rebalance liên tục thường xuất phát từ member join/leave, listener xử lý quá lâu, heartbeat timeout, restart, topic change hoặc coordinator/network bất ổn.
- `max.poll.interval.ms` giới hạn khoảng cách giữa hai lần `poll()`; `session.timeout.ms` và `heartbeat.interval.ms` liên quan đến heartbeat trong classic protocol.
- Hạ `max.poll.records`, tối ưu listener và đặt timeout cho dependency để giảm thời gian xử lý mỗi poll.
- Spring Kafka 2.9+ có `ContainerPausingBackOffHandler` để xử lý backoff dài mà vẫn duy trì poll; retry topic là lựa chọn cho delay dài với trade-off ordering.
- CooperativeStickyAssignor giảm partition bị thu hồi; Kafka 4.0 consumer protocol hỗ trợ incremental server-side assignment.
- Static membership có thể giảm rebalance do restart ngắn nhưng cần `group.instance.id` duy nhất.
- `ConsumerAwareRebalanceListener`, `NonResponsiveConsumerEvent`, consumer metrics và `kafka-consumer-groups.sh` giúp quan sát nguyên nhân.
- Không reset offset hoặc tăng timeout mù quáng; cần đối chiếu log, metrics, member lifecycle và thời gian xử lý trước khi sửa.

Khi poll interval, heartbeat, consumer membership và partition assignment được theo dõi riêng, nhóm vận hành có thể xác định chính xác vì sao group liên tục rebalance. Sửa đúng nguyên nhân giúp consumer giữ assignment ổn định, giảm lag và tránh xử lý lại record không cần thiết.

## Tài liệu tham khảo

- [Apache Kafka — Consumer Configs](https://kafka.apache.org/41/configuration/consumer-configs/)
- [Apache Kafka — Monitoring](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka — Basic Kafka Operations](https://kafka.apache.org/43/operations/basic-kafka-operations/)
- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Rebalancing Listeners](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/rebalance-listeners.html)
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring Kafka — Handling Exceptions and Backoff](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
