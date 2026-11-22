# onPartitionsAssigned

Trong Kafka consumer group, mỗi partition chỉ được giao cho tối đa một consumer member tại một thời điểm. Khi nhóm consumer khởi động, thay đổi số member hoặc rebalance, consumer cần biết **những partition nào vừa được giao cho mình** để bắt đầu xử lý đúng dữ liệu. Callback `onPartitionsAssigned` là điểm móc (*lifecycle hook*) dành cho công việc đó.

Trong ứng dụng Spring Kafka, `onPartitionsAssigned` thường được dùng để ghi log assignment, khởi tạo trạng thái xử lý theo partition, gắn tài nguyên cục bộ, khôi phục checkpoint do ứng dụng quản lý hoặc quyết định seek đến một offset xác định theo chính sách. Callback này nằm trên ranh giới giữa **quyết định phân công của Kafka** và **vòng đời xử lý của listener container**.

Điểm quan trọng là **được assigned không có nghĩa đã xử lý xong hoặc đã commit offset**. Callback chỉ thông báo consumer hiện có quyền nhận các partition được giao. Việc đọc record, retry, acknowledgement và commit diễn ra theo cơ chế của consumer và Spring Kafka listener container. Nếu thay đổi offset trong callback mà không hiểu điều này, ứng dụng có thể đọc lại hàng loạt hoặc bỏ qua message chưa được xử lý.

## 1. Vị trí của onPartitionsAssigned trong lifecycle consumer

Kafka consumer tham gia consumer group bằng `subscribe(...)`. Group coordinator và partition assignor xác định member nào nhận partition. Sau khi assignment được hoàn tất, Kafka gọi `ConsumerRebalanceListener.onPartitionsAssigned(Collection<TopicPartition>)` trong quá trình `poll()`. Spring Kafka listener container điều phối vòng poll và có thể chuyển sự kiện cho listener rebalance đã đăng ký.

Một chu kỳ minh họa:

~~~mermaid
sequenceDiagram
    participant C as Spring Kafka container
    participant K as Kafka group coordinator
    participant R as Rebalance listener
    participant L as KafkaListener
    C->>K: Subscribe / poll / join group
    K-->>C: Partition assignment mới
    C->>R: onPartitionsAssigned(partitions)
    R-->>C: Khởi tạo tài nguyên / seek theo policy
    C->>K: poll theo assignment hiện tại
    K-->>C: ConsumerRecords
    C->>L: Giao record cho listener
    L-->>C: Xử lý hoàn tất hoặc ném exception
    C->>K: Commit offset theo AckMode / transaction
~~~

Sơ đồ mô tả trình tự logic, không phải một lời hứa rằng Kafka chỉ gọi callback một lần. Một consumer có thể nhận callback nhiều lần trong vòng đời do rebalance, thay đổi subscription hoặc được giao lại partition sau sự cố. Callback cũng có thể được gọi với danh sách rỗng trong một số tình huống; ứng dụng không nên giả định luôn có partition.

### Những điểm gọi phổ biến

- **Khởi động consumer:** group assignment ban đầu được hình thành, callback cho biết các partition đã được giao.
- **Scale out:** một consumer mới tham gia, partition có thể chuyển sang member mới.
- **Scale in hoặc restart:** member khác nhận partition mà member cũ để lại.
- **Consumer bị timeout:** partition của member mất quyền có thể được giao lại sau rebalance.
- **Tăng số partition hoặc đổi subscription:** assignor có thể phân phối lại assignment.
- **Cooperative rebalance:** một số partition được giữ nguyên; một số partition thay đổi chủ sở hữu.

Không dùng callback này để suy ra producer đã ngừng publish, topic đã hết record, hoặc mọi partition trong topic đều thuộc consumer hiện tại.

## 2. TopicPartition và phạm vi callback

Đối số của callback là một collection các `TopicPartition`. Mỗi phần tử chứa tên topic và số partition; nó **không chứa message**, **không chứa offset đã commit** và **không phải khóa phân biệt consumer group**.

~~~text
group.id = orders-service
topic    = orders.events (4 partitions)

Consumer A được assigned:
  TopicPartition(orders.events, 0)
  TopicPartition(orders.events, 2)

Consumer B được assigned:
  TopicPartition(orders.events, 1)
  TopicPartition(orders.events, 3)
~~~

Trong cùng một consumer group, partition 0 không được đồng thời giao cho cả A và B khi group đã ổn định. Nếu ứng dụng có nhiều `@KafkaListener`, nhiều group hoặc nhiều container, mỗi container sẽ có callback và assignment riêng. Khi log cần thêm `group.id`, listener ID và application instance ID để xác định callback thuộc consumer nào.

### Assignment không phải ownership vĩnh viễn

Kafka có thể thu hồi assignment trong rebalance tiếp theo. Một job bất đồng bộ được khởi tạo khi `onPartitionsAssigned` chạy có thể tiếp tục tồn tại sau khi partition bị revoke. Vì vậy tài nguyên và công việc theo partition cần gắn với vòng đời *assigned → processing → revoked/lost*, không chỉ thực hiện thao tác khởi tạo một lần tại startup.

## 3. Kafka ConsumerRebalanceListener API

API nền tảng của Kafka client là `ConsumerRebalanceListener` với các callback liên quan:

| Callback | Khi nào dùng | Lưu ý |
|---|---|---|
| `onPartitionsAssigned(partitions)` | Sau khi có assignment | Khởi tạo state, log owner, có thể seek theo policy. |
| `onPartitionsRevoked(partitions)` | Khi partition đang sở hữu chuẩn bị bị thu hồi trong rebalance thông thường | Dọn state, chốt tiến độ hoặc lưu checkpoint nếu phù hợp. |
| `onPartitionsLost(partitions)` | Khi consumer đã mất ownership mà không có cơ hội revoke bình thường | Không giả định có thể commit như owner hiện tại; tập trung giải phóng tài nguyên an toàn. |

`onPartitionsLost` có hành vi mặc định/phương thức hỗ trợ phụ thuộc phiên bản Kafka client; cần kiểm tra API thực tế khi tự cài đặt. Spring Kafka cung cấp các biến thể callback và cách kết nối với container để phối hợp commit và lifecycle.

Không nhầm `onPartitionsAssigned` với `onPartitionsRevoked`:

- Assigned: consumer **bắt đầu có quyền** xử lý các partition được giao.
- Revoked: consumer **chuẩn bị mất quyền** hoặc kết thúc sở hữu một tập partition.
- Lost: consumer **đã mất quyền**; cơ hội commit đồng bộ trước revoke có thể đã qua.

Nếu logic khởi tạo state đặt ở assigned, cần có logic thu hồi hoặc vô hiệu hóa state tương ứng khi revoked/lost.

## 4. Dùng ConsumerAwareRebalanceListener trong Spring Kafka

Spring Kafka hỗ trợ `ConsumerAwareRebalanceListener`, cho phép callback nhận thêm đối tượng `Consumer<?, ?>` đang được container quản lý. Đây là cách tiện lợi để quan sát assignment hoặc thực hiện các thao tác consumer thread-safe đúng ngữ cảnh, chẳng hạn `seek(...)`.

Ví dụ cấu hình một listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties().setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {
                @Override
                public void onPartitionsAssigned(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {

                    for (TopicPartition partition : partitions) {
                        log.info("Assigned topic={} partition={}",
                                partition.topic(),
                                partition.partition());
                    }
                }
            });

    return factory;
}
~~~

Các import liên quan gồm `ConcurrentKafkaListenerContainerFactory`, `ConsumerFactory`, `ConsumerAwareRebalanceListener`, `Consumer`, `TopicPartition` và `Collection`. Ví dụ giả định có logger `log` của ứng dụng.

Listener sử dụng factory:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void onOrderEvent(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

Factory tạo ba consumer con khi `concurrency=3`. Mỗi consumer có assignment và callback của riêng nó. Nếu topic có hai partition, không phải cả ba consumer đều nhận partition; một consumer có thể không có assignment.

### Vì sao Spring có ConsumerAware?

Kafka consumer không thread-safe. Spring Kafka container sở hữu vòng poll trên consumer thread. Khi callback được thực thi trong vòng rebalance của container, việc gọi các thao tác consumer được phép trong callback có thể an toàn hơn việc đưa reference consumer ra một worker thread bất kỳ.

Tuy nhiên, **có quyền truy cập `Consumer` không có nghĩa nên gọi mọi phương thức trong callback**. Tránh thao tác blocking dài, thao tác trái lifecycle container hoặc tự commit offsets không phù hợp với transaction/AckMode.

## 5. onPartitionsAssigned không phải onPartitionsRevoked

Spring Kafka có các callback cho phép xử lý revoke ở những thời điểm khác nhau của quy trình container commit. `ConsumerAwareRebalanceListener` cung cấp các hook như `onPartitionsRevokedBeforeCommit` và `onPartitionsRevokedAfterCommit` ở các phiên bản hỗ trợ.

Phân công trách nhiệm điển hình:

| Thời điểm | Công việc phù hợp | Không nên làm |
|---|---|---|
| Assigned | Log assignment, đăng ký state, chuẩn bị consumer position | Commit offset của record chưa xử lý. |
| Revoked trước commit | Ghi checkpoint/capture trạng thái ứng dụng phù hợp | Chặn consumer thread quá lâu hoặc hứa rollback external side effect. |
| Revoked sau commit | Giải phóng tài nguyên, đánh dấu partition không còn thuộc owner | Tiếp tục xử lý công việc cũ như owner. |
| Lost | Vô hiệu hóa owner và hủy/đánh dấu job pending | Cố commit offset như thể vẫn còn quyền sở hữu. |

Với eager rebalance, nhiều partition có thể bị thu hồi rồi được gán lại. Với cooperative rebalance, chỉ một phần assignment cần thay đổi. Do đó logic lifecycle nên **xử lý theo tập partition được callback thông báo**, không tự xóa toàn bộ state của container ở mọi lần assignment.

## 6. Eager và cooperative rebalance: ý nghĩa của danh sách assigned

Partition assignor và rebalance protocol ảnh hưởng tập partition được trả trong callback.

### Eager rebalance

Trong mô hình eager, các member thường thu hồi toàn bộ partition trong quá trình rebalance rồi được cấp assignment mới. Vì vậy, callback assigned có thể nhận lại cả những partition mà consumer vừa sở hữu trước đó.

Nếu code mỗi lần assigned đều xóa state hoặc seek về đầu topic, ứng dụng có thể đọc lại quá nhiều record sau mỗi đợt scale hoặc rolling restart.

### Cooperative rebalance

Với cooperative assignor như `CooperativeStickyAssignor`, consumer có thể giữ lại các partition không cần chuyển giao; chỉ các partition phải chuyển ownership mới bị revoke/assigned theo từng bước. Danh sách trong callback assigned **không nhất thiết là toàn bộ các partition đang thuộc consumer**; một số partition có thể đã được giữ nguyên qua rebalance.

Ví dụ:

~~~text
Trước rebalance:
  Consumer A: P0, P1, P2
  Consumer B: P3

Sau thay đổi group:
  Consumer A: P0, P1
  Consumer B: P2, P3

P0, P1 vẫn ở A; P2 chuyển sang B.
Callback của từng member phụ thuộc protocol và assignment.
~~~

Không triển khai logic kiểu "mỗi lần onPartitionsAssigned xuất hiện, xóa toàn bộ map state rồi tạo lại chỉ từ danh sách callback". Trong cooperative rebalance, cách đó có thể làm mất state của partition vẫn thuộc owner.

Nếu cần biết assignment đầy đủ, dùng API container/consumer phù hợp tại thời điểm hợp lệ để đối chiếu; đừng coi danh sách callback luôn là snapshot đầy đủ của mọi partition trong mọi giao thức.

## 7. Khởi tạo trạng thái theo partition

Một số consumer duy trì cache, bộ đếm, dữ liệu tham chiếu hoặc trạng thái xử lý theo partition. Khi được assigned, ứng dụng có thể khởi tạo bản ghi owner hoặc tạo state container tương ứng.

Ví dụ ý tưởng quản lý state:

~~~java
public final class PartitionStateRegistry {
    private final ConcurrentMap<TopicPartition, PartitionState> states =
            new ConcurrentHashMap<>();

    public void assigned(Collection<TopicPartition> partitions) {
        partitions.forEach(topicPartition ->
                states.computeIfAbsent(
                        topicPartition,
                        ignored -> new PartitionState()));
    }

    public void revoked(Collection<TopicPartition> partitions) {
        partitions.forEach(states::remove);
    }
}
~~~

Ví dụ minh họa registry; `PartitionState` là kiểu do ứng dụng định nghĩa. Nếu nhiều container con trong cùng ứng dụng cùng thao tác registry, cần quản lý owner chính xác và tránh state rò rỉ sau rebalance. `computeIfAbsent` chỉ tránh tạo lại khi đã có state; nó không thay thế kiểm soát version, checkpoint hoặc validity khi partition đổi owner.

### Restore state từ hệ thống ngoài

Nếu cần load state từ database hoặc object storage, nên:

1. Xác định chính xác topic/partition vừa nhận.
2. Đọc metadata phiên bản/checkpoint ứng với partition và vị trí offset.
3. Kiểm tra checkpoint tương thích với committed offset dự kiến.
4. Chỉ cho listener xử lý khi state cần thiết đã sẵn sàng.
5. Khi partition bị revoked/lost, dừng dùng state cũ và hủy công việc pending phù hợp.

Không chạy truy vấn dài nhiều phút trực tiếp trong callback nếu sẽ giữ consumer thread không poll. Nếu state lớn, cân nhắc chiến lược chuẩn bị bất đồng bộ kết hợp container pause/resume đúng cách; chỉ resume sau khi restore thành công và phải kiểm soát trạng thái assignment còn hiệu lực.

## 8. Seek trong onPartitionsAssigned

Kafka consumer thường bắt đầu đọc từ **committed offset** của consumer group cho partition. Nếu chưa có committed offset hợp lệ, chính sách `auto.offset.reset` được dùng để chọn điểm bắt đầu theo cấu hình.

Trong `onPartitionsAssigned`, có thể chủ động `seek` đến offset khác. Nhưng seek là quyết định thay đổi vị trí đọc của consumer:

- `seek(topicPartition, offset)` thay đổi **position**, không tự commit offset.
- `seekToBeginning(...)` yêu cầu đọc từ đầu phần log còn được giữ.
- `seekToEnd(...)` yêu cầu đi tới cuối log hiện tại, có thể bỏ qua backlog chưa xử lý nếu dùng sai.
- `commitSync(...)` ghi tiến độ group; không tương đương seek.

Ví dụ có chủ đích đọc lại từ đầu các partition mới được assigned:

~~~java
@Override
public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    if (!partitions.isEmpty() && replayModeEnabled) {
        consumer.seekToBeginning(partitions);
    }
}
~~~

`replayModeEnabled` là một policy flag do ứng dụng quản lý; đây chỉ là code minh họa. **Không dùng ví dụ này mặc định trong production.** Với group đã có committed offsets, `seekToBeginning` có thể khiến mọi lần rebalance lặp lại dữ liệu cũ. Nếu listener có tác động nghiệp vụ, việc đọc lại phải có idempotency và phê duyệt replay.

### Seek đến checkpoint ngoài Kafka

Một kiến trúc đặc biệt có thể lưu checkpoint ở database:

~~~text
Topic orders.events, partition 2
Kafka committed offset: 510
External state checkpoint: 505

Nếu seek về 505:
  Có thể xử lý lại 505..509
  Cần đảm bảo state restore và idempotency tương ứng

Nếu seek đến 520:
  Có thể bỏ qua 510..519
  Chỉ hợp lệ khi có quyết định nghiệp vụ rõ ràng
~~~

Không trộn hai nguồn checkpoint mà không có quy tắc nhất quán. Kafka committed offsets và external snapshot phải được liên kết với một ranh giới trạng thái có thể kiểm chứng. Khi không cần custom checkpoint, nên để container bắt đầu theo committed offset bình thường.

## 9. ConsumerSeekAware.onPartitionsAssigned

Spring Kafka cung cấp một hướng khác dành cho thao tác seek tại listener: interface `ConsumerSeekAware`. Interface này có callback với dạng:

~~~java
void onPartitionsAssigned(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback);
~~~

Đây là **Spring Kafka `ConsumerSeekAware` callback**, không phải cùng chữ ký với Kafka `ConsumerRebalanceListener`. Map chứa partition và vị trí/offset mà framework cung cấp tại thời điểm callback; `ConsumerSeekCallback` cung cấp các phương thức để yêu cầu seek theo cách Spring Kafka điều phối.

Ví dụ listener chỉ ghi nhận các partition và offset khởi đầu:

~~~java
public class OrdersListener implements ConsumerSeekAware {

    @KafkaListener(topics = "orders.events", groupId = "orders-service")
    public void onMessage(OrderEvent event) {
        orderService.processIdempotently(event);
    }

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.forEach((tp, offset) ->
                log.info("Spring seek-aware assignment: {}-{} at {}",
                        tp.topic(), tp.partition(), offset));
    }
}
~~~

Class ở ví dụ cần được đăng ký làm Spring bean/listener phù hợp để container phát hiện `ConsumerSeekAware`. Nếu cần seek chủ động, dùng các phương thức của `ConsumerSeekCallback`, ví dụ `seek(topic, partition, offset)`, trong ngữ cảnh hỗ trợ.

### Chọn ConsumerAwareRebalanceListener hay ConsumerSeekAware?

| Nhu cầu | API thường phù hợp |
|---|---|
| Log assignment và tương tác với `KafkaConsumer` ngay trong rebalance | `ConsumerAwareRebalanceListener` |
| Gắn hook ở mức listener bean và thực hiện seek theo API Spring Kafka | `ConsumerSeekAware` |
| Quản lý revoke/lost và tài nguyên state theo partition ở container | Rebalance listener phù hợp |
| Seek theo timestamp/offset cho use case replay | `ConsumerSeekAware` hoặc consumer-aware callback, với policy rõ ràng |

Không đăng ký đồng thời hai cơ chế để cùng seek tới hai vị trí khác nhau. Nếu nhiều callback can thiệp consumer position trong cùng lifecycle, thứ tự thực hiện và offset cuối cùng có thể không đúng kỳ vọng. Chọn một thành phần chịu trách nhiệm chính cho offset policy.

## 10. Callback chạy trên consumer thread

Kafka client gọi rebalance callbacks như một phần của `poll()`. Trong Spring Kafka, callback của rebalance listener được gọi trong ngữ cảnh container consumer thread. Đây là lý do có thể thao tác consumer trực tiếp **trong callback**, nhưng cũng là nguồn rủi ro hiệu năng.

### Không chặn thread quá lâu

Nếu `onPartitionsAssigned` gọi service ngoài mất 90 giây, consumer thread chưa tiếp tục poll. Với nhiều partition hoặc rebalance liên tiếp, group có thể chịu latency lớn, nguy cơ chạm `max.poll.interval.ms` hoặc các giới hạn timeout.

Không làm những công việc sau một cách không giới hạn trong callback:

- Gọi REST API không timeout.
- Chạy database migration hoặc truy vấn nặng.
- Load toàn bộ cache nhiều GB từ object storage.
- `Thread.sleep` chờ điều kiện nghiệp vụ.
- Khởi tạo thread pool vô hạn hoặc spawn job mà không gắn vòng đời partition.
- Tự gọi `poll()` lồng nhau hay commit offsets tùy tiện trong listener callback.

Nên giữ callback nhỏ, quyết định assignment và khởi tạo metadata nhanh. Nếu workload yêu cầu restore state nặng, thiết kế cơ chế pause/resume/ready riêng, bảo đảm consumer vẫn poll khi cần và không xử lý record trước khi state sẵn sàng.

### KafkaConsumer không thread-safe

Không lưu `Consumer<?, ?>` từ callback rồi truyền cho executor để gọi `seek` hay `commitSync`. KafkaConsumer nói chung không thread-safe; các thao tác consumer cần được điều phối trên thread phù hợp. Spring Kafka có API container và `ConsumerSeekCallback` cho những thao tác nhất định; sử dụng chúng đúng lifecycle thay vì truy cập consumer trực tiếp từ background thread.

## 11. Offset commit và acknowledgement sau assignment

`onPartitionsAssigned` không có nghĩa record nào đã được xử lý. Khi một partition vừa được giao, consumer thường đọc từ committed offset hợp lệ và Spring Kafka listener bắt đầu xử lý.

Với `enable.auto.commit=false`, container quản lý commit theo `AckMode`:

| Chế độ | Quan hệ với callback |
|---|---|
| `RECORD` | Offset commit sau từng record listener xử lý thành công; assignment chỉ xác định nơi đọc. |
| `BATCH` | Offset commit sau batch theo policy; callback không phải ranh giới commit batch. |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()` sau nghiệp vụ; assignment không tự acknowledge. |
| `MANUAL_IMMEDIATE` | Acknowledge trên consumer thread có thể commit ngay theo policy; không gọi sớm trong assignment. |
| Transactional container | Container đưa input offsets cùng Kafka output vào transaction khi xử lý thành công. |

Ví dụ nguy hiểm:

~~~java
@Override
public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    // Không commit "cuối topic" chỉ vì vừa được assigned.
    consumer.seekToEnd(partitions);
    // Nếu tiếp tục commit các position này sai policy,
    // backlog chưa xử lý có thể bị bỏ qua sau restart.
}
~~~

Seek không tự commit, nhưng thay đổi position rồi xử lý/commit tiếp có thể khiến record cũ không được giao lại theo cách thông thường. Nếu muốn reset offset, cần quy trình có kiểm soát và đảm bảo consumer group không đang xử lý song song ngoài dự kiến.

### Retry và idempotency

Khi partition chuyển ownership, record đã xử lý nghiệp vụ nhưng chưa commit offset có thể được giao lại cho owner mới. `onPartitionsAssigned` không loại bỏ duplicate này. Dùng event ID ổn định và cơ chế idempotency (ví dụ inbox table với unique constraint trong cùng DB transaction) cho tác động ngoài Kafka.

## 12. Rebalance, revoked/lost và tác vụ bất đồng bộ

Một rủi ro phổ biến là listener nhận partition rồi đẩy record sang executor. Khi rebalance xảy ra, worker cũ vẫn có thể xử lý record sau khi partition đã được giao cho consumer khác.

Ví dụ:

~~~text
T1: Consumer A nhận P2 (onPartitionsAssigned)
T2: A gửi record offset 80 sang worker nền
T3: Group rebalance, P2 chuyển từ A sang B
T4: B bắt đầu xử lý offset 80 từ committed offset
T5: Worker nền của A hoàn tất, định commit offset 81
~~~

Nếu A commit offset tùy tiện ở T5, hệ thống có thể bị sai ownership hoặc gặp commit failure. Nếu A ghi database trước khi commit, B có thể tạo duplicate nghiệp vụ.

Để tránh:

1. Gắn owner/assignment generation hoặc token riêng với mỗi partition state.
2. Khi revoked/lost, đánh dấu token cũ không còn hợp lệ.
3. Hủy, đợi hoàn tất hoặc chuyển công việc pending sang cơ chế recovery an toàn.
4. Không commit offset cho những record chưa hoàn tất theo đúng thứ tự partition.
5. Không gọi consumer từ background worker không được container quản lý.
6. Dùng idempotency ở database/API, vì cancel worker không bảo đảm rollback side effect đã xảy ra.

Nếu chọn xử lý bất đồng bộ, cần hiểu cách Spring Kafka quản lý acknowledgements, pause/resume và out-of-order ack trong phiên bản đang chạy. Không chỉ dựa vào `onPartitionsAssigned` làm nguồn sự thật duy nhất về quyền xử lý.

## 13. Kết hợp với static membership

`group.instance.id` cho phép Kafka nhận diện consumer instance ổn định qua restart. Static membership có thể giúp giảm rebalance trong những lần restart ngắn, nhưng **không ngăn mọi callback assignment**, cũng không làm partition ownership cố định vĩnh viễn.

Nếu static member không quay lại trước session timeout hoặc group thay đổi vì lý do khác, partition vẫn có thể được giao cho member khác. Khi đó `onPartitionsAssigned` của owner mới phải được xử lý bình thường.

Không dùng việc callback ít xuất hiện hơn làm chỉ số duy nhất đánh giá static membership thành công. Cần quan sát cả group member count, rebalance duration, partition assignment và consumer lag.

## 14. Cấu hình Spring Boot minh họa

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      concurrency: 3
      ack-mode: record
~~~

Trong cấu hình này, có thể tạo ba consumer thread trong cùng listener container. `onPartitionsAssigned` của từng consumer phản ánh những partition được giao riêng cho nó.

Nếu topic có sáu partition và không có member khác trong group, mỗi consumer có thể nhận khoảng hai partition tùy partition assignor. Nếu topic có hai partition, một consumer có thể nhàn rỗi. Không tăng `concurrency` rồi giả định nhiều consumer thread sẽ cùng xử lý **một partition**.

Các giá trị thời gian và batch là ví dụ, cần đo độ trễ listener, retry, database và thời gian callback restore state trước khi đưa vào production.

## 15. Quan sát onPartitionsAssigned trong production

Log assignment là bằng chứng trực tiếp cho việc partition chuyển chủ. Tuy nhiên, chỉ log tên partition mà không có instance/consumer ID thì khó dựng lại timeline khi xảy ra rebalance.

| Tín hiệu | Mục đích | Chú ý |
|---|---|---|
| Group ID, member/client ID, listener ID | Xác định callback thuộc consumer nào | Không dùng ID biến thiên theo record làm metric label. |
| Assigned topic/partition set | Theo dõi partition owner hiện tại | Phân biệt callback delta với assignment toàn phần ở cooperative rebalance. |
| Revoked/lost partition set | Xác định khi owner cũ mất quyền | Liên kết với worker pending và offset commit. |
| Timestamp và callback duration | Phát hiện callback khởi tạo state quá chậm | Cảnh báo khi restore tăng p95/p99. |
| Consumer lag và committed offset | Kiểm tra tiến độ sau rebalance | Lag phải xem theo partition. |
| Seek count và seek target | Phát hiện seek ngoài dự kiến | Không log payload hoặc dữ liệu nhạy cảm. |
| Rebalance count/duration | Đánh giá độ ổn định của group | So sánh với deployment và timeout. |
| Listener errors/retries | Biết record mới assigned có tiếp tục thất bại không | Phân biệt lỗi dữ liệu và lỗi hạ tầng. |

Log gợi ý:

~~~text
INFO rebalance_assigned
  groupId=orders-service
  listenerId=ordersListener-1
  instanceId=orders-pod-2
  assigned=[orders.events-0,orders.events-3]
  callbackDurationMs=8
  seekPolicy=committed-offset
~~~

Đây là cấu trúc minh họa; nên phát log có cấu trúc thay vì chuỗi tự do nếu hệ thống có tập trung log/trace.

### Không coi mọi assigned callback là lỗi

Callback xuất hiện khi startup hoặc scale có thể là hoàn toàn bình thường. Cảnh báo nên dựa vào rebalance liên tục, callback kéo dài, lag tăng, mất assignment lặp hoặc seek ngoài ý muốn; không cảnh báo chỉ vì có một lần `onPartitionsAssigned`.

## 16. Runbook: onPartitionsAssigned xuất hiện liên tục

1. Xác định group ID, listener ID, instance và thời điểm mỗi callback.
2. Kiểm tra lịch deploy/scale và số member trong group.
3. Đọc log rebalance, session timeout, heartbeat và `max.poll.interval.ms`.
4. Kiểm tra listener xử lý chậm, retry blocking hoặc callback restore state mất nhiều thời gian.
5. Xem partition assignor, eager/cooperative strategy và thay đổi subscription.
6. Kiểm tra có consumer nhiều hơn số partition hay không, hoặc các instance liên tục join/leave.
7. Khắc phục nguyên nhân membership không ổn định và đo lại rebalance rate/lag.

Không tăng mọi timeout theo cảm tính. Nếu thread bị chặn vì truy vấn dài trong callback, tăng session timeout có thể chỉ làm chậm failover.

## 17. Runbook: Consumer đọc lại từ đầu sau rebalance

1. Kiểm tra callback có gọi `seekToBeginning`, `seek` hoặc callback `ConsumerSeekAware` khác không.
2. Đọc committed offset thực tế của group cho topic/partition bị ảnh hưởng.
3. Kiểm tra group ID có thay đổi giữa các lần deploy không.
4. Kiểm tra `auto.offset.reset` chỉ có hiệu lực khi không có committed offset hợp lệ.
5. Đối chiếu checkpoint bên ngoài với offset Kafka và policy restore state.
6. Nếu có seek thủ công, xác định lý do và owner chấp thuận replay.
7. Dùng idempotency để kiểm soát duplicate; không reset tiếp khi chưa hiểu nguyên nhân.

Nếu offset đã commit bị mất do retention hoặc group ID mới, chính sách reset có thể ảnh hưởng điểm bắt đầu; cần xác minh trước khi kết luận callback là nguyên nhân.

## 18. Runbook: Partition đã assigned nhưng không xử lý record

1. Xác nhận partition được gán cho consumer có listener đang chạy, không chỉ log từ một lần callback cũ.
2. Kiểm tra container có paused, stopped hoặc waiting for state restore không.
3. Kiểm tra listener đã subscribe đúng topic/partition và Kafka ACL cho phép fetch không.
4. Đối chiếu current position, committed offset và end offset.
5. Xem callback có seek tới cuối log hoặc offset ngoài khoảng hợp lệ không.
6. Kiểm tra exception trong `onPartitionsAssigned` hoặc logic khởi tạo state có làm container ngừng hoạt động không.
7. Kiểm tra downstream blocking, poll interval và lag sau khi khôi phục.

Không chạy `seekToBeginning` như thao tác chữa cháy mặc định; điều đó có thể tạo replay lớn và duplicate.

## 19. Runbook: State bị mất hoặc trùng sau cooperative rebalance

1. Xác định partition nào thực sự bị revoke, lost hoặc assigned.
2. Kiểm tra code có xóa toàn bộ map state ở mỗi callback hay không.
3. Đối chiếu event timeline với mode rebalance và partition assignment đã giữ nguyên.
4. Đảm bảo cleanup chỉ áp dụng cho partition đã bị thu hồi/lost.
5. Với partition mới, restore state kèm checkpoint version/offset phù hợp.
6. Kiểm tra worker bất đồng bộ cũ có tiếp tục dùng state sau khi partition mất ownership không.
7. Thử rebalance từng phần ở staging trước khi triển khai sửa đổi.

## 20. Runbook: onPartitionsAssigned quá chậm

1. Đo duration của callback theo từng member và số partition.
2. Xác định truy vấn DB, remote API, tải snapshot hoặc lock đang chặn callback.
3. Đặt timeout hữu hạn cho mọi I/O và giảm công việc đồng bộ trong consumer thread.
4. Tách restore state nặng thành cơ chế bất đồng bộ có trạng thái ready và pause/resume đúng cách nếu ứng dụng yêu cầu.
5. Khi thực hiện async restore, đánh dấu assignment epoch/owner để hủy kết quả cũ nếu partition bị revoke.
6. Theo dõi `max.poll.interval.ms`, rebalance duration và listener lag sau khi thay đổi.

Tránh chuyển việc nặng sang executor rồi ngay lập tức cho listener đọc record khi state chưa sẵn sàng. Điều đó chỉ đổi một lỗi timeout thành lỗi nhất quán nghiệp vụ.

## 21. Bảng kiểm soát onPartitionsAssigned

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Callback wiring | Rebalance listener đã gắn vào đúng container factory chưa? | Bean configuration và log assigned. |
| Assignment semantics | Danh sách callback là tập newly assigned hay toàn assignment ở rebalance hiện tại? | Assignor/protocol, trước-sau rebalance timeline. |
| Thread ownership | Có gọi consumer API từ consumer thread đúng cách không? | Callback location và thread name. |
| State restore | State/checkpoint có tương thích với partition và committed offset không? | Snapshot version, offset, restore result. |
| Seek policy | Có seek thủ công không, có nguy cơ đọc lại/bỏ qua dữ liệu? | Seek target, committed offset và replay approval. |
| Lifecycle | Revoked/lost có cleanup state và hủy worker cũ không? | Assignment token, cleanup logs. |
| Backpressure | Callback có giữ poll quá lâu không? | Callback duration, poll interval và timeout metrics. |
| Ordering/offset | Listener có ack/commit sau khi nghiệp vụ hoàn tất không? | AckMode, committed offsets, event ID. |
| Rebalance | Có rebalance storm, static ID collision hoặc consumer quá tải không? | Member count, rebalance logs và lag. |
| Recovery | Restart, retry, reassignment có tạo duplicate không? | Inbox/unique event ID và fault-injection tests. |

**Kết luận:** `onPartitionsAssigned` là điểm bắt đầu vòng đời xử lý của những Kafka partition được giao cho một consumer. Trong Spring Kafka, callback giúp quan sát assignment, khởi tạo state và thực hiện seek có kiểm soát, nhưng không phải tín hiệu xử lý thành công hay nơi commit offset tùy tiện. Thiết kế vững chắc cần xử lý riêng các trường hợp assigned, revoked và lost; phân biệt eager/cooperative rebalance; không chặn consumer thread quá lâu; và bảo vệ offset, state cùng external side effects trước restart/rebalance. Khi dùng đúng, `onPartitionsAssigned` giúp consumer tiếp tục từ vị trí hợp lệ và phục hồi an toàn mỗi lần partition đổi chủ.
