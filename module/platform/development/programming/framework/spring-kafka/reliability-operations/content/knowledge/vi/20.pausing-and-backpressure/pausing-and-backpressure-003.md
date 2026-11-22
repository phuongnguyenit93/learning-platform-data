# Pause từng partition

Trong Spring Kafka, một consumer có thể được gán nhiều partition của một hoặc nhiều topic. Không phải lúc nào tất cả partition cũng cần được đọc với tốc độ như nhau: một partition có thể đang bị nghẽn do dependency, quá tải hoặc cần tạm dừng để xử lý dữ liệu bất thường, trong khi các partition còn lại vẫn hoạt động bình thường. **Pause từng partition** cho phép tạm ngừng lấy thêm record từ một `TopicPartition` cụ thể mà không phải dừng toàn bộ listener container.

Spring Kafka cung cấp các API như `pausePartition(TopicPartition)`, `resumePartition(TopicPartition)`, `isPartitionPauseRequested(TopicPartition)` và `isPartitionPaused(TopicPartition)` trên `MessageListenerContainer` ở các phiên bản hỗ trợ (cơ chế pause/resume theo partition được giới thiệu từ Spring Kafka 2.7). Đây là một công cụ **backpressure mang tính vận hành**; nó không phải cơ chế retry, không tự commit offset, không chuyển record sang DLT và không đảm bảo record đã được lấy ra trước khi pause sẽ ngừng xử lý ngay lập tức.

## 1. Partition pause giải quyết tình huống nào?

Giả sử topic `orders` có bốn partition. Một consumer group gồm hai instance, mỗi instance có một consumer:

```text
Topic orders
  partition 0 ---> Consumer A
  partition 1 ---> Consumer A
  partition 2 ---> Consumer B
  partition 3 ---> Consumer B
```

Nếu các record ở `orders-2` đang cần gọi một hệ thống thanh toán không ổn định, đội vận hành có thể muốn giảm áp lực lên hệ thống đó mà vẫn xử lý `orders-3`. Khi pause partition 2:

```text
Consumer B
   |
   +--> orders-2: PAUSED (không fetch thêm record mới)
   |
   +--> orders-3: ACTIVE (tiếp tục poll và giao record)

Consumer A
   |
   +--> orders-0: ACTIVE
   +--> orders-1: ACTIVE
```

Điểm quan trọng: **orders-2 vẫn được gán cho Consumer B**. Pause không yêu cầu Kafka coordinator gán partition đó sang Consumer A. Nếu mục tiêu là chuyển tải sang member khác, phải xem xét scaling, group membership và rebalance thay vì chỉ gọi pause.

### Khi nào hữu ích?

- Một partition chứa các record liên quan đến cùng tenant hoặc key nghiệp vụ cần tạm ngừng vì dependency riêng.
- Một luồng xử lý yêu cầu kiểm tra thủ công trước khi tiếp nhận thêm record ở partition nghi ngờ.
- Ứng dụng có cơ chế giới hạn số request đến dịch vụ ngoài, và muốn giảm consumption ở một số partition trong lúc quá tải.
- Hệ thống cần duy trì tiến độ của các partition lành mạnh thay vì pause toàn bộ listener.
- Một workflow có thể dừng theo partition để bảo toàn thứ tự cục bộ trong lúc chờ điều kiện nghiệp vụ.

Không nên mặc định pause theo partition là giải pháp cho mọi loại quá tải. Nếu toàn bộ database bị nghẽn, pause chọn một partition có thể chỉ chuyển áp lực sang các partition khác; khi đó backpressure ở mức toàn container, giới hạn concurrency, rate limiter hoặc cải thiện dependency có thể phù hợp hơn.

## 2. Partition assignment, pause và Kafka poll là ba khái niệm khác nhau

Kafka consumer group quyết định **member nào sở hữu partition**. Kafka consumer `pause(Collection<TopicPartition>)` quyết định **partition nào tạm thời không được trả record mới qua `poll()`**. Spring Kafka listener container cung cấp API để yêu cầu pause một cách phù hợp với lifecycle của consumer thread.

| Trạng thái | Ý nghĩa | Partition có còn thuộc consumer group member? |
|---|---|---|
| Assigned + active | Consumer sở hữu partition và tiếp tục lấy record. | Có. |
| Assigned + paused | Consumer sở hữu partition nhưng tạm ngừng lấy thêm record từ partition đó. | Có. |
| Revoked | Coordinator đã thu hồi partition khỏi member trong rebalance. | Không. |
| Container stopped | Listener container không còn hoạt động như một consumer bình thường. | Sau khi rời group, partition được phân phối lại. |

Một partition được pause không nhất thiết làm group chuyển sang trạng thái rebalance. Consumer vẫn phải `poll()` đều đặn để duy trì thành viên và heartbeat phù hợp, nhất là khi tất cả partition đều đang pause.

**Không gọi trực tiếp `KafkaConsumer.pause(...)` từ một HTTP request thread hoặc thread giám sát bên ngoài.** KafkaConsumer không phải object thread-safe dùng tùy ý giữa nhiều thread. Hãy gọi API pause của Spring Kafka container; container điều phối thao tác với consumer trong ngữ cảnh phù hợp.

## 3. API pausePartition và resumePartition

Ở Spring Kafka hỗ trợ per-partition pause, `MessageListenerContainer` cung cấp các thao tác chính:

```java
container.pausePartition(new TopicPartition("orders", 2));
container.resumePartition(new TopicPartition("orders", 2));
```

`TopicPartition` là cặp **tên topic + chỉ số partition**. Ví dụ `TopicPartition("orders", 2)` hoàn toàn khác `TopicPartition("payments", 2)`.

Các API quan sát thường dùng:

```java
TopicPartition tp = new TopicPartition("orders", 2);

boolean requested = container.isPartitionPauseRequested(tp);
boolean applied   = container.isPartitionPaused(tp);
```

Phân biệt rõ:

- `pausePartition(tp)`: **gửi yêu cầu** tạm dừng partition.
- `isPartitionPauseRequested(tp)`: kiểm tra container đã nhận yêu cầu pause hay chưa.
- `isPartitionPaused(tp)`: kiểm tra trạng thái pause đã được container áp dụng theo trạng thái nó quan sát.
- `resumePartition(tp)`: gửi yêu cầu bỏ pause, cho phép partition tiếp tục được poll khi có assignment hợp lệ.

Yêu cầu pause và trạng thái pause thực tế **không nhất thiết thay đổi ngay trong cùng một dòng lệnh gọi**. Spring Kafka có thể thực hiện pause ở một ranh giới vòng poll an toàn. Nếu đang xử lý batch/record đã lấy từ lần poll trước, có thể còn record được giao cho listener trước khi pause có hiệu lực.

Do đó, đừng viết:

```java
container.pausePartition(tp);
// KHÔNG NÊN giả định tại đây mọi xử lý ở tp đã dừng tuyệt đối.
performDangerousMaintenanceOnPartitionData();
```

Nếu cần bảo đảm tuyệt đối không có handler đang chạy trước khi bảo trì, cần thêm giao thức quiescence: quan sát trạng thái pause đã áp dụng, kiểm đếm công việc in-flight, chờ transaction đang chạy hoàn tất và dùng một khóa/lease nghiệp vụ nếu phù hợp.

## 4. Ví dụ với @KafkaListener và KafkaListenerEndpointRegistry

Để điều khiển listener từ một service khác, đặt `id` cố định cho listener:

```java
@Component
public class OrderKafkaListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        concurrency = "3"
    )
    public void onMessage(ConsumerRecord<String, String> record) {
        orderProcessor.process(record.key(), record.value());
    }
}
```

`KafkaListenerEndpointRegistry` cho phép tìm container theo listener ID rồi yêu cầu pause/resume partition:

```java
@Service
public class OrderPartitionControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderPartitionControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause(int partition) {
        TopicPartition tp = new TopicPartition("orders", partition);
        container().pausePartition(tp);
    }

    public void resume(int partition) {
        TopicPartition tp = new TopicPartition("orders", partition);
        container().resumePartition(tp);
    }

    public PartitionPauseState state(int partition) {
        TopicPartition tp = new TopicPartition("orders", partition);
        MessageListenerContainer c = container();

        return new PartitionPauseState(
                c.isPartitionPauseRequested(tp),
                c.isPartitionPaused(tp));
    }

    private MessageListenerContainer container() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-listener");
        if (c == null) {
            throw new IllegalStateException(
                    "orders-listener is not registered");
        }
        return c;
    }

    public record PartitionPauseState(
            boolean pauseRequested,
            boolean paused) {
    }
}
```

Các import chính:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
```

Ví dụ trên giả định Spring Kafka phiên bản hỗ trợ các method theo partition trên container và ứng dụng dùng Java đủ mới cho `record`. Có thể thay `record` bằng DTO/class thông thường nếu dùng Java cũ.

Không công khai phương thức `pause`/`resume` qua một HTTP endpoint không có xác thực. Nếu tạo endpoint vận hành, phải giới hạn quyền, kiểm tra topic/partition hợp lệ, log người thao tác, thời gian và lý do pause, đồng thời có cơ chế tự phục hồi nếu người vận hành quên resume.

## 5. Khi listener concurrency lớn hơn một

`concurrency = "3"` có thể tạo ba child consumer container cho một listener. Mỗi child consumer được Kafka gán một tập partition riêng trong group:

```text
ConcurrentMessageListenerContainer: orders-listener
    |
    +--> child container 0 -> orders-0, orders-3
    +--> child container 1 -> orders-1, orders-4
    +--> child container 2 -> orders-2, orders-5
```

Assignment trên chỉ là ví dụ; Kafka assignor và số member thực tế quyết định phân phối.

Khi gọi API per-partition trên concurrent container, Spring Kafka cần áp dụng yêu cầu tới child container có partition được gán. Người viết code không nên dựa vào suy luận rằng “partition 2 luôn thuộc child container số 2”, vì rebalance hoặc scale replica có thể thay đổi assignment.

Hãy kiểm tra trạng thái assignment thực tế và chọn đúng **listener container**. Nếu ứng dụng có nhiều `@KafkaListener` cùng subscribe một topic hoặc nhiều group, pause ở container của listener A không đồng nghĩa group B cũng ngừng xử lý partition đó.

Đặc biệt trong nhiều replica:

- Mỗi pod có `KafkaListenerEndpointRegistry` của JVM đó.
- Lệnh gọi registry trong pod A **không tự phát tán** yêu cầu pause đến pod B.
- Nếu partition đang được gán cho pod B, yêu cầu pause thực tế phải được điều phối tới owner phù hợp, hoặc mỗi pod phải nhận cùng desired-state và áp dụng khi nó sở hữu partition.

Với nhu cầu pause tập trung toàn deployment, hãy xây dựng một control plane có desired state và cơ chế reconcile giữa các instance, không mặc định một lệnh trên một pod là đủ.

## 6. Pause không giải phóng partition và không gây rebalance theo chủ ý

Trong Kafka, một partition được pause vẫn thuộc assignment của consumer. Các hệ quả:

1. Consumer khác trong cùng group **không tự nhận partition vừa pause**.
2. Không có cơ chế auto-scaling nào tự chuyển partition đó sang member rảnh chỉ vì lag tăng.
3. Consumer có thể tiếp tục heartbeat và poll để duy trì membership.
4. Partition giữ thứ tự record theo offset khi được resume, nhưng không cam kết giữ thứ tự **giữa các partition**.
5. Committed offset không tự thay đổi chỉ vì pause.

Nếu mục tiêu là tạm dừng `orders-2` vì hệ thống đích chậm, pause là hợp lý. Nếu mục tiêu là phân phối lại tải nóng từ Consumer B sang Consumer A, pause là sai công cụ: cần đánh giá chiến lược partitioning, số consumer, số partition và khả năng cân bằng tải.

### Nếu tất cả partition đều paused?

Container vẫn có thể tiếp tục poll để duy trì trạng thái group, nhưng sẽ không nhận thêm record từ các partition đang pause. Việc dùng container API thay vì chặn thread bằng `Thread.sleep(...)` là rất quan trọng để không gây `max.poll.interval.ms` timeout.

Đừng hiểu “vẫn poll” là ứng dụng hoàn toàn miễn nhiễm với rebalance. Nếu listener đang xử lý record rất lâu, process treo, network mất hoặc có thay đổi membership, group vẫn có thể rebalance theo quy tắc Kafka.

## 7. Pause bắt đầu có hiệu lực ở thời điểm nào?

Yêu cầu pause không tự động xóa các record mà consumer đã fetch trước đó. Có thể có một vòng poll trả về nhiều record:

```text
T0: poll() lấy 5 record từ orders-2
T1: listener bắt đầu xử lý record 1
T2: thread vận hành gọi pausePartition(orders-2)
T3: listener còn xử lý các record đã poll trước đó
T4: container áp dụng pause theo vòng poll
T5: poll tiếp theo không fetch thêm record mới ở orders-2
```

Đây là sơ đồ logic, không phải cam kết chính xác thứ tự T3/T4 cho mọi phiên bản hoặc listener mode. Điều cần nhớ là **pause không phải lệnh hủy tức thì mọi processing đang chạy**.

Nếu ứng dụng dùng batch listener, một batch chứa record ở partition định pause có thể đã được chuyển vào listener trước khi yêu cầu được nhận. Nếu record listener còn nhiều record đang chờ giao từ một poll, việc pause ngay lúc listener đang chạy không nhất thiết ngăn tất cả record đã lấy được xử lý.

Vì vậy:

- Dùng `isPartitionPauseRequested` để biết **ý định** đã được lưu ở container.
- Dùng `isPartitionPaused` hoặc sự kiện pause để biết trạng thái container **đã áp dụng**.
- Theo dõi in-flight task/transaction riêng nếu cần chờ xử lý hiện tại kết thúc.
- Không dùng pause thay cho cơ chế khóa nghiệp vụ hoặc distributed lease cần độ chính xác cao.

## 8. Pause và offset/acknowledgment

Pause không commit offset, không seek và không thay đổi ack mode. Ví dụ:

```text
orders-2:
  committed offset = 100
  log end offset   = 140

pausePartition(orders-2)

orders-2:
  committed offset vẫn = 100 (nếu không có commit khác)
  producer tiếp tục ghi: log end có thể tăng lên 150
```

Nếu có record đã xử lý xong trước pause và container commit offset của chúng sau đó, committed offset vẫn có thể tăng. Sự thay đổi này đến từ xử lý/ack trước đó, **không phải bản thân lệnh pause**.

Các nguyên tắc:

| Thao tác | Có tự commit offset? | Có ảnh hưởng fetching? |
|---|---|---|
| `pausePartition(tp)` | Không. | Có, tạm ngừng lấy record mới của partition khi pause đã áp dụng. |
| `resumePartition(tp)` | Không. | Có, cho phép lấy record trở lại. |
| `Acknowledgment.acknowledge()` | Theo ack mode/cấu hình. | Không phải lệnh pause. |
| `consumer.seek(tp, offset)` | Không tự commit. | Thay đổi vị trí đọc; khác pause. |
| `container.stop()` | Có lifecycle và xử lý pending riêng theo cấu hình. | Dừng container, không tương đương pause một partition. |

Với transactional listener, một transaction đã bắt đầu trước khi pause cần commit/abort theo chính sách transaction. Pause không biến các transaction đang mở thành đã hoàn tất.

## 9. Backpressure theo partition: thiết kế điều khiển

Backpressure là cách ngăn tốc độ nhận thêm công việc vượt quá năng lực xử lý. Với pause từng partition, luồng điều khiển có thể dựa vào độ trễ dependency, số request in-flight, tỷ lệ timeout hoặc queue depth, không nên chỉ dựa vào lag Kafka.

Ví dụ chính sách cho các partition ánh xạ tương đối ổn định đến một tài nguyên downstream:

```text
Dependency latency / error rate tăng
            |
            v
  Vi phạm ngưỡng bảo vệ?
       /           \
     Không          Có
      |              |
      v              v
  Tiếp tục      pausePartition(tp)
    poll              |
                      v
             Theo dõi dependency recovery
                      |
                      v
             Đạt điều kiện ổn định?
                 /          \
               Không         Có
                 |            |
                 v            v
               Giữ       resumePartition(tp)
               pause
```

### Ngưỡng cao/thấp và hysteresis

Nếu ứng dụng pause ngay khi dependency latency vượt 500 ms và resume ngay khi latency xuống dưới 500 ms, trạng thái có thể đổi liên tục. Nên dùng **hysteresis**:

- Pause nếu latency trung bình vượt 800 ms liên tục một khoảng quan sát, hoặc error rate vượt giới hạn đã chọn.
- Chỉ resume khi latency xuống dưới 300 ms và error rate ổn định trong vài chu kỳ.
- Có thời gian pause tối thiểu và cooldown sau khi resume.
- Có giới hạn pause tối đa hoặc cảnh báo để tránh quên một partition quá lâu.

Các ngưỡng chỉ là ví dụ; cần đo từ SLA, throughput và đặc điểm dependency. Backpressure không làm biến mất công việc: record vẫn ở Kafka trong thời gian retention cho phép, và **lag thường tăng trong thời gian partition bị pause**.

### Vì sao không dùng lag cao làm điều kiện pause duy nhất?

Lag cao thường chỉ ra consumer đang theo không kịp producer. Nếu chỉ vì lag cao mà lại pause consumer, backlog có thể tăng nhanh hơn. Lag nên được dùng **để đánh giá hậu quả và quyết định ưu tiên phục hồi**, còn quyết định pause nên gắn với lý do bảo vệ cụ thể như dependency không đủ năng lực hoặc trạng thái nghiệp vụ chưa an toàn.

## 10. Quản lý desired state khi có nhiều pod

Trong môi trường Kubernetes, một quyết định pause có thể cần tiếp tục có hiệu lực sau rolling update, restart hoặc rebalance. State pause cục bộ trong một container Java **không phải cấu hình bền vững toàn cụm**.

Một thiết kế vận hành:

```text
Control plane / database
  desiredPausedPartitions = {orders-2, orders-5}
                 |
                 v
        Control reconciler
                 |
         +-------+-------+
         |               |
         v               v
       Pod A           Pod B
   local registry   local registry
         |               |
         v               v
   Owns orders-2?   Owns orders-5?
         |               |
         v               v
   Apply pause      Apply pause
```

Mỗi instance cần biết partition nào nó đang sở hữu và reconcile desired state theo assignment thực tế. Khi partition chuyển owner do rebalance, instance mới phải áp dụng chính sách trước khi coi partition đó là an toàn để xử lý, nếu nghiệp vụ yêu cầu pause liên tục.

Trong các phiên bản/cách cấu hình cụ thể, yêu cầu pause cục bộ có thể được container quản lý qua những lần assignment thay đổi; tuy nhiên **không dựa vào trạng thái cục bộ như nguồn sự thật bền vững sau restart**. Hãy có cơ chế reconcile và xác nhận thực tế.

Tùy yêu cầu bảo mật, desired-state API nên:

1. Xác thực và phân quyền người hoặc service yêu cầu pause.
2. Kiểm tra topic/partition thuộc allowlist.
3. Ghi lý do, incident ID, người thao tác và thời gian hết hạn lệnh pause.
4. Đồng bộ trạng thái yêu cầu tới các instance liên quan.
5. Quan sát yêu cầu đã được áp dụng, không chỉ trả HTTP 200 ngay khi đặt flag.

## 11. Rebalance, revoke và resume

Consumer group có thể rebalance khi scale pod, có lỗi `max.poll.interval.ms`, một member rời group hoặc topic tăng số partition. Trong rebalance, partition có thể bị revoke rồi assigned cho consumer khác.

```text
Trước rebalance:
  Pod A owns orders-2 (paused)

Sau rebalance:
  Pod A: orders-2 revoked
  Pod B: orders-2 assigned
```

Đừng kỳ vọng trạng thái pause của Pod A tự chuyển qua Pod B. Nếu quy tắc nghiệp vụ “orders-2 phải pause đến khi một operator resume”, cần lưu ý định đó ngoài từng JVM và áp dụng lại khi assignment mới xuất hiện.

Nếu dùng `ConsumerAwareRebalanceListener` hoặc application event cho assignment/revoke, code phải tránh block consumer thread. Reconciler có thể cập nhật state hoặc lập lịch áp dụng chính sách; đừng gọi database/HTTP dài ngay trong callback rebalance.

Trước khi resume, xác nhận:

- Partition đang thuộc listener container cần thao tác.
- Nguyên nhân pause đã được xử lý, không chỉ alert đã tắt.
- Không có thao tác bảo trì hoặc xử lý record in-flight xung đột.
- Desired state toàn cụm đã được thay đổi thành “resume”.
- Có theo dõi throughput, error rate, lag khi record bắt đầu được đọc lại.

## 12. Sự kiện quan sát pause/resume

Spring Kafka phát các application event liên quan đến pause/resume. Theo phiên bản hỗ trợ, các event theo partition có thể gồm `ConsumerPartitionPausedEvent` và `ConsumerPartitionResumedEvent`.

Ví dụ listener ghi log metadata của event:

```java
@Component
public class KafkaPartitionPauseEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPartitionPauseEvents.class);

    @EventListener
    public void onPaused(ConsumerPartitionPausedEvent event) {
        log.info("Kafka partition pause applied: {}", event);
    }

    @EventListener
    public void onResumed(ConsumerPartitionResumedEvent event) {
        log.info("Kafka partition resume applied: {}", event);
    }
}
```

Import minh họa:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionPausedEvent;
import org.springframework.kafka.event.ConsumerPartitionResumedEvent;
import org.springframework.stereotype.Component;
```

Trong dự án thực tế, hãy chọn field chính xác từ event theo API của phiên bản và bổ sung `pod`, `listenerId`, `groupId`, `topicPartition`, `reason` vào structured log. Event được phát trong luồng xử lý container; handler nên nhanh, không chờ một network call dài.

**Sự kiện “pause applied” khác với log “pause requested”.** Nếu có dashboard, nên tách hai trạng thái để không báo partition đã dừng khi container còn đang hoàn tất record từ poll trước.

## 13. Quan sát lag và retained backlog

Trong thời gian pause, producer có thể tiếp tục ghi record. Nếu không có commit mới, lag của partition tăng:

```text
orders-2 committed offset  = 100
orders-2 log end offset    = 110
lag                        = 10

pause orders-2
producer ghi thêm 40 record

orders-2 committed offset  = 100
orders-2 log end offset    = 150
lag                        = 50
```

Sau resume, consumer cần đủ throughput để giảm backlog. Nếu producer ghi trung bình 200 record/s mà consumer xử lý 250 record/s, tốc độ giảm lag tối đa theo lý thuyết chỉ khoảng 50 record/s (trước khi tính overhead, batching, retry và partition skew).

Theo dõi tối thiểu:

| Tín hiệu | Mục đích |
|---|---|
| `pause_requested` theo topic-partition | Biết operator/controller đã yêu cầu dừng hay chưa. |
| `pause_applied` theo topic-partition | Biết consumer thực tế đã được pause hay chưa. |
| Pause duration | Tránh để partition ở trạng thái pause vô thời hạn. |
| Consumer lag và log-end offset theo partition | Đo lượng dữ liệu tồn đọng và tốc độ phục hồi. |
| Listener throughput theo partition | Xác nhận các partition active vẫn tiến triển. |
| Dependency latency/error rate | Biết nguyên nhân pause có còn tồn tại không. |
| Rebalance/assignment events | Phát hiện partition chuyển owner khi đang pause. |
| Oldest record age / retention headroom | Tránh pause lâu đến mức dữ liệu cũ bị xóa trước khi xử lý. |

Các tên metric trên là **gợi ý instrumentation**, không mặc định có sẵn trong Kafka client hoặc Spring Kafka. Consumer lag thường có thể xem từ Kafka tooling; riêng pause state của Spring container cần lấy từ API, event hoặc metric do ứng dụng cung cấp.

## 14. Kiểm tra qua Kafka CLI và log ứng dụng

Một bước quan trọng khi vận hành là xác nhận **group vẫn sở hữu partition** và hiểu lag tăng do pause hay do lỗi khác.

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service
```

Lệnh trên thường hiển thị topic, partition, committed offset, log end offset, lag và member/host/client ID. Tuy nhiên, **Kafka CLI không thể kết luận container Spring Kafka đang pause partition** chỉ từ assignment hoặc lag. Consumer group protocol không cung cấp một cờ “paused by Spring container” để suy ra trực tiếp từ output thông thường.

Với Kubernetes, có thể kết hợp:

```bash
kubectl get pods -l app=order-service -o wide
kubectl logs -l app=order-service --since=15m --prefix=true
```

Tìm log `pause requested`, `partition pause applied`, `resume`, assignment/revoke, listener exception, transaction abort và dependency health. Nếu CLI cho thấy partition vẫn assigned nhưng offset đứng yên trong khi các partition khác tiến, đó là dấu hiệu phù hợp với pause; cần **xác nhận bằng state của container**, không suy đoán chỉ từ lag.

## 15. Pause khác gì stop, seek, retry hoặc scale?

| Cơ chế | Tác động chính | Khi nên dùng |
|---|---|---|
| `pausePartition(tp)` | Tạm ngừng fetch record mới từ một partition; vẫn giữ assignment. | Backpressure chọn lọc hoặc tạm dừng có chủ đích một partition. |
| `container.pause()` | Yêu cầu tạm dừng consumption của toàn container. | Cần giảm áp lực từ tất cả partition do container quản lý. |
| `container.stop()` | Dừng lifecycle container; có thể rời group và dẫn tới rebalance. | Bảo trì hoặc ngừng listener thực sự. |
| `consumer.seek(tp, offset)` | Thay đổi vị trí đọc theo offset. | Replay/skip có kiểm soát; không phải pause. |
| `DefaultErrorHandler` + `BackOff` | Retry hoặc phục hồi record lỗi. | Xử lý transient/permanent listener failures. |
| `@RetryableTopic` | Chuyển record lỗi sang retry topic để xử lý lại. | Non-blocking retry khi phù hợp với thứ tự và transaction model. |
| Tăng concurrency/replicas | Tăng số consumer member và phân phối assignment nếu có partition. | Tăng năng lực xử lý song song, không thay thế pause. |

Pause không giải quyết lỗi poison record vĩnh viễn. Nếu một record luôn fail do dữ liệu sai, cần exception classification, retry có giới hạn và DLT/recovery. Pause chỉ trì hoãn việc đọc thêm record; khi resume, lỗi có thể xuất hiện lại nếu nguyên nhân chưa được sửa.

## 16. Pause và ErrorHandler/transactional listener

Error handler có thể đang retry một record với backoff. Nếu cùng lúc operator yêu cầu pause partition, cần hiểu ranh giới:

- Pause không hủy một retry listener đang chạy.
- Record đã fetch trước pause có thể tiếp tục được xử lý hoặc retry theo container/error handler.
- Pause không tự đưa record lỗi sang DLT.
- Pause không thay đổi chính sách `AckMode` hoặc committed offset.
- Với Kafka transaction, transaction đang mở vẫn phải commit/abort; pause không tự làm atomicity thay đổi.

Nếu mục tiêu là chặn gửi request tới dependency đang lỗi, nên có thêm **circuit breaker hoặc rate limiter tại callsite**, không chỉ dựa vào pause vì một số record có thể đã in-flight.

Nếu dùng non-blocking retry topic, một record lỗi có thể đã được chuyển sang topic retry riêng. Pause partition ở **topic chính** không tự pause partition của **retry topic** hoặc DLT consumer. Mỗi listener/container và group phải được quản lý theo phạm vi chính xác của nó.

## 17. Retention, lag và nguy cơ pause quá lâu

Backpressure không miễn phí. Record chờ trong Kafka chịu chính sách retention của topic. Nếu partition bị pause lâu và log retention xóa các offset cũ trước khi chúng được xử lý, consumer có thể gặp tình huống offset không còn hợp lệ hoặc bỏ lỡ dữ liệu tùy cách thiết lập `auto.offset.reset` và recovery.

Ví dụ:

```text
Topic retention: 24 giờ
Partition pause: 20 giờ
Oldest unprocessed record age: 22 giờ

Nguy cơ: record chưa xử lý có thể bị loại khỏi log sớm
```

Không dùng con số retention đơn giản làm một deadline chắc chắn nếu topic còn chịu log compaction, size-based retention hoặc chính sách broker khác. Hãy theo dõi **tuổi record chưa xử lý lâu nhất**, log start offset và retention headroom, rồi cảnh báo trước khi dữ liệu gặp nguy cơ.

Với hệ thống yêu cầu không mất event, có thể cần pause tối đa ngắn, tăng retention, chuyển tải sang hàng đợi có độ bền phù hợp hoặc thiết kế một workflow xử lý lại chủ động thay vì để partition pause vô hạn.

## 18. Runbook: pause một partition để bảo vệ dependency

Giả sử `orders-2` gây timeout liên tục tới service thanh toán, còn các partition khác vẫn chạy.

**Bước 1 — Xác nhận phạm vi.** Kiểm tra lỗi chỉ liên quan `orders-2` hay là lỗi toàn hệ thống. Đối chiếu key, topic, partition, consumer member, dependency metrics và thời điểm bắt đầu lỗi.

**Bước 2 — Xác định owner.** Xem consumer group assignment hiện tại. Với nhiều pod, tìm instance đang sở hữu partition hoặc bảo đảm control plane phân phối desired-state đến các pod phù hợp.

**Bước 3 — Yêu cầu pause.** Gọi `pausePartition(new TopicPartition("orders", 2))` qua Spring Kafka container API, không gọi `KafkaConsumer.pause` từ thread ngoài.

**Bước 4 — Xác nhận áp dụng.** Kiểm tra `isPartitionPauseRequested`, `isPartitionPaused`, application event và in-flight work. Không tuyên bố đã dừng tuyệt đối ngay sau khi gọi method.

**Bước 5 — Giám sát khi pause.** Kiểm tra lag `orders-2`, tuổi record, retention headroom, dependency health và throughput của các partition còn lại. Đặt cảnh báo nếu pause vượt thời gian mục tiêu.

**Bước 6 — Khôi phục điều kiện xử lý.** Sửa dependency, cập nhật rate limit/circuit breaker hoặc khắc phục dữ liệu lỗi. Nếu có poison record, chọn retry/DLT phù hợp trước khi resume.

**Bước 7 — Resume.** Cập nhật desired state, gọi `resumePartition(tp)`, xác nhận event resume và offset bắt đầu tiến. Theo dõi error rate để tránh một vòng pause/resume liên tục.

**Bước 8 — Kết thúc sự cố.** Ghi lại nguyên nhân pause, thời gian gián đoạn, lượng lag tích lũy, thời gian catch-up, các record thất bại và biện pháp phòng ngừa.

Không reset offset để “cho lag biến mất” nếu chưa có quyết định nghiệp vụ và cơ chế bảo toàn dữ liệu đã được duyệt.

## 19. Runbook: partition đã pause nhưng vẫn thấy record xử lý

Các nguyên nhân thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ngay sau `pausePartition` vẫn có log listener | Record đã được trả về ở poll trước, hoặc pause chưa áp dụng. | Kiểm tra requested/applied state, đợi xử lý in-flight hoàn tất. |
| Partition tiếp tục chạy sau rebalance | Partition chuyển sang pod khác chưa có desired pause state. | Reconcile pause trên owner mới, kiểm tra assignment events. |
| Chỉ một pod dừng, pod khác vẫn xử lý cùng topic | Pause ở container/group/instance khác. | Xác minh listener ID, consumer group và owner partition. |
| Kafka CLI vẫn báo partition assigned | Đây là trạng thái bình thường khi pause. | Không dùng assignment làm bằng chứng resume; kiểm tra container pause state. |
| Một topic retry vẫn xử lý record | Pause chỉ áp dụng cho topic-partition ở container được chỉ định. | Quản lý retry listener/topic riêng nếu cần. |
| Consumer group bị rebalance trong thời gian pause | Pod restart, long-running listener, timeout hoặc membership thay đổi. | Xem `max.poll.interval.ms`, poll, heartbeat và Kubernetes events. |
| Offset vẫn tiến một chút sau pause | Commit/ack của record đã xử lý trước pause. | Đối chiếu thời điểm pause áp dụng và lịch sử commit. |

Nếu pause đã được áp dụng nhưng listener tiếp tục nhận record mới liên tục từ đúng partition, cần kiểm tra API và listener container nào được thao tác, phiên bản Spring Kafka, tình trạng assignment và việc có code khác gọi `resumePartition` hay không.

## 20. Kiểm thử tích hợp cho pause từng partition

Để chứng minh chính sách hoạt động, nên chạy integration test với Kafka thực, ví dụ qua Testcontainers hoặc embedded broker hỗ trợ phiên bản Kafka đang dùng.

Một kịch bản kiểm thử:

1. Tạo topic `orders` có ít nhất hai partition.
2. Khởi động listener container với `id` cố định và group ID riêng của test.
3. Chờ assignment đầy đủ và xác nhận listener đã nhận record baseline của cả hai partition.
4. Gọi `pausePartition(orders-0)`, chờ đến khi trạng thái pause đã áp dụng.
5. Publish thêm record vào `orders-0` và `orders-1`.
6. Xác nhận `orders-1` vẫn được xử lý; `orders-0` không tiếp tục nhận record mới sau khi đã tính đến in-flight records.
7. Gọi `resumePartition(orders-0)`, chờ applied state thay đổi.
8. Xác nhận record tồn đọng ở `orders-0` được xử lý, offset tiến và không mất dữ liệu.
9. Tùy nhu cầu, tạo rebalance/restart để kiểm tra desired-state được khôi phục đúng.

Tránh assert ngay sau lệnh pause mà không chờ điều kiện bất đồng bộ; điều đó tạo flaky test. Cũng tránh dùng một lệnh `Thread.sleep(...)` dài cố định thay cho việc chờ trạng thái pause thực sự khi test có thể sử dụng công cụ await điều kiện.

Nếu cần kiểm tra xử lý đúng một lần theo nghiệp vụ, tích hợp thêm idempotency/assertion riêng. Pause/resume bản thân nó không phải bảo đảm exactly-once.

## 21. Nguyên tắc vận hành

- Dùng `pausePartition(tp)` / `resumePartition(tp)` của Spring Kafka container thay vì gọi `KafkaConsumer.pause` từ thread không thuộc consumer.
- Hiểu pause là **ngừng fetch thêm**, không phải dừng hoặc hủy ngay mọi record đang xử lý.
- Tách `pause requested` và `pause applied` khi hiển thị trạng thái.
- Pause **không thu hồi assignment**, không tự gây rebalance và không chuyển partition sang member khác.
- Pause **không commit offset**, không seek, không thay thế error handler hoặc DLT.
- Với concurrency và nhiều replica, xác nhận đúng owner; giữ desired state bền vững nếu pause cần tồn tại qua restart/rebalance.
- Theo dõi lag, tuổi record, retention headroom, thời gian pause và dependency health; đừng để partition pause vô thời hạn.
- Chọn ngưỡng backpressure có hysteresis và cooldown; tránh liên tục pause/resume theo một ngưỡng duy nhất.
- Khi resume, kiểm tra dependency đã hồi phục và công suất xử lý đủ để bắt kịp backlog.
- Bảo vệ API vận hành bằng authentication, authorization, audit log và kiểm tra topic-partition hợp lệ.
- Kiểm thử pause trong điều kiện có in-flight records, nhiều partition, rebalance và restart.

**Pause từng partition** là công cụ kiểm soát consumption theo phạm vi hẹp trong Spring Kafka. Nó giúp bảo vệ dependency hoặc tạm ngừng một luồng dữ liệu bất thường mà không bắt buộc các partition khác dừng theo. Để vận hành tin cậy, cần phân biệt yêu cầu pause với trạng thái đã áp dụng, bảo toàn offset và thứ tự trong partition, xử lý assignment khi scale/rebalance, và có kế hoạch resume dựa trên lag, retention cùng sức khỏe của hệ thống downstream.
