# onPartitionsRevoked

Khi một Spring Kafka consumer đang xử lý records, Kafka có thể quyết định **thu hồi quyền sở hữu một hoặc nhiều partition** khỏi consumer đó. Sự kiện này thường xảy ra trong quá trình **consumer group rebalance**: một instance mới tham gia group, một instance rời group, consumer không poll đúng hạn hoặc assignment được tính lại. Kafka gọi callback **onPartitionsRevoked** để thông báo các partition sắp không còn thuộc quyền xử lý của consumer.

Trong hệ thống cần độ tin cậy cao, đây không chỉ là một callback về thay đổi topology. **onPartitionsRevoked là thời điểm quan trọng để hoàn tất hoặc dừng công việc đang gắn với partition, phối hợp offset commit và giải phóng partition-scoped state** trước khi partition được giao cho một consumer khác. Nếu xử lý callback sai, ứng dụng có thể commit offset vượt qua dữ liệu chưa xử lý, lặp side effect, mất state trong bộ nhớ, giữ resource quá lâu hoặc gây thêm rebalance.

Bài học giải thích cơ chế revoke trong Kafka và Spring Kafka, API ConsumerRebalanceListener/ConsumerAwareRebalanceListener, thời điểm commit offset, khác biệt giữa eager/cooperative rebalance, quan hệ với onPartitionsLost, cách bảo vệ xử lý bất đồng bộ và quy trình vận hành.

## 1. onPartitionsRevoked là gì?

Một Kafka consumer group phân phối các partition giữa các consumer member. Với một group tại một thời điểm assignment ổn định, mỗi partition chỉ được giao cho một consumer member. Khi membership hoặc subscription thay đổi, group phải tính lại assignment.

Ví dụ ban đầu:

~~~text
Topic orders: P0, P1, P2, P3

Consumer group orders-service
  Consumer A -> P0, P1, P2, P3
~~~

Khi Consumer B tham gia:

~~~text
Trước rebalance:
  A -> P0, P1, P2, P3
  B -> chưa có partition

Rebalance:
  A nhận yêu cầu revoke các partition cần bàn giao
  Group coordinator tính/chốt assignment mới

Sau rebalance:
  A -> P0, P1
  B -> P2, P3
~~~

Trước khi A nhường P2 và P3, Kafka có thể gọi callback onPartitionsRevoked cho những partition bị thu hồi. Ứng dụng có cơ hội đóng resource, ghi nhận tiến độ xử lý hợp lệ và không khởi động thêm tác vụ cho partition sắp rời đi.

Các điểm cần nhớ:

- **Partition bị revoke** là partition đang trong quá trình rời khỏi assignment của consumer hiện tại.
- **Rebalance callback** chạy trong vòng đời consumer poll, không phải sự kiện nghiệp vụ của từng record.
- **Bộ partition được truyền vào callback** là các partition Kafka báo bị thu hồi; không nên tự giả định nó luôn chứa toàn bộ partition của consumer.
- **Kafka consumer group** quản lý ownership; application state nằm trong bộ nhớ phải tự thích ứng với ownership mới.

## 2. Khi nào callback được gọi?

Những tình huống thường dẫn đến rebalance hoặc thay đổi assignment:

1. Một replica/consumer mới tham gia group để scale out.
2. Một consumer được dừng trong quá trình deployment hoặc scale in.
3. Một member không đáp ứng yêu cầu heartbeat hoặc poll interval theo group protocol.
4. Consumer đổi subscription hoặc topic có thay đổi partition count.
5. Coordinator/consumer gặp lỗi kết nối hoặc cần tái lập membership.
6. Thay đổi assignment strategy giữa các lần deploy.

Không nên suy luận rằng **mọi lần mất ownership đều luôn gọi onPartitionsRevoked đầy đủ trước khi partition được giao cho member khác**. Nếu consumer bị mất membership bất ngờ, chẳng hạn vượt max.poll.interval.ms hoặc broker xác định session đã hết hạn, ứng dụng có thể chỉ biết partition đã mất qua callback/lỗi khác, hoặc process có thể chết trước khi bất cứ callback nào chạy.

Vì vậy, onPartitionsRevoked giúp graceful handoff nhưng **không thể là cơ chế duy nhất để bảo đảm không mất dữ liệu**. Offset commit đúng, idempotency và lưu state bền vững vẫn cần thiết.

## 3. ConsumerRebalanceListener trong Kafka client

Kafka client cung cấp interface **org.apache.kafka.clients.consumer.ConsumerRebalanceListener** với các callback thường gặp:

- **onPartitionsRevoked(Collection<TopicPartition>)**: được gọi khi consumer chuẩn bị nhường các partition được thông báo.
- **onPartitionsAssigned(Collection<TopicPartition>)**: được gọi khi consumer nhận assignment mới hoặc hoàn tất giai đoạn assignment.
- **onPartitionsLost(Collection<TopicPartition>)**: dành cho trường hợp partition đã bị mất ownership, thay vì một đợt revoke có cơ hội bàn giao bình thường; sự hỗ trợ và hành vi phụ thuộc client version.

Luồng tổng quát:

~~~text
Consumer.poll()
     |
     +-- phát hiện cần rebalance
     |
     v
onPartitionsRevoked(...)
     |
     +-- hoàn tất/ghi nhận tiến độ đã xử lý
     +-- ngăn công việc mới trên partition bị revoke
     +-- dọn state cần bàn giao
     |
     v
Group assignment thay đổi
     |
     v
onPartitionsAssigned(...)
     |
     +-- khởi tạo state partition mới
     +-- chuẩn bị tiếp tục consume
~~~

Đây là sơ đồ cho một lần revoke/assign có kiểm soát. Trong thực tế, thời điểm và tập partition khác nhau giữa eager và cooperative rebalance; một số giai đoạn có thể lặp, rỗng hoặc không xuất hiện như sơ đồ khi consumer mất membership đột ngột.

Một listener thuần Kafka có thể viết:

~~~java
ConsumerRebalanceListener listener =
        new ConsumerRebalanceListener() {

    @Override
    public void onPartitionsRevoked(
            Collection<TopicPartition> partitions) {
        log.info("Partitions revoked: {}", partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Collection<TopicPartition> partitions) {
        log.info("Partitions assigned: {}", partitions);
    }
};
~~~

Trong Spring Kafka, nên ưu tiên cơ chế đăng ký listener thông qua **listener container**, để Spring Kafka phối hợp callback với việc commit offset và lifecycle của container.

## 4. ConsumerAwareRebalanceListener của Spring Kafka

Spring Kafka cung cấp **ConsumerAwareRebalanceListener**, một biến thể thân thiện với listener container. Interface cho phép callback nhận thêm KafkaConsumer và cung cấp các hook quanh thời điểm container commit pending offsets.

Các callback quan trọng:

| Callback | Ý nghĩa thực tế |
|---|---|
| **onPartitionsRevokedBeforeCommit** | Được gọi trước bước container commit pending offsets trong luồng revoke bình thường |
| **onPartitionsRevokedAfterCommit** | Được gọi sau bước commit pending offsets của container |
| **onPartitionsAssigned** | Cho ứng dụng chuẩn bị state khi partition được assignment |
| **onPartitionsLost** | Xử lý trường hợp ownership đã mất, khi phiên bản Kafka/Spring Kafka hỗ trợ |

Với ứng dụng có listener container quản lý offset, tách **before commit** và **after commit** giúp triển khai logic đúng thời điểm hơn là tự commit offset trong một callback chung.

Ví dụ lớp listener:

~~~java
@Component
public class OrderPartitionRebalanceListener
        implements ConsumerAwareRebalanceListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderPartitionRebalanceListener.class);

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info("Preparing revoke for {}", partitions);
    }

    @Override
    public void onPartitionsRevokedAfterCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info("Revoked after pending commits: {}", partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info("New assignment: {}", partitions);
    }
}
~~~

Đoạn mã minh họa các callback phổ biến của Spring Kafka. Tên method/overload và khả năng hỗ trợ onPartitionsLost cần được xác minh với dependency version thực tế. Chỉ đọc thông tin cần thiết từ KafkaConsumer trong callback; không tùy tiện chuyển Consumer object sang một thread khác.

## 5. Đăng ký callback trên Spring Kafka listener container

Với ConcurrentKafkaListenerContainerFactory, có thể cấu hình rebalance listener trên ContainerProperties:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                OrderPartitionRebalanceListener rebalanceListener) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setConsumerRebalanceListener(rebalanceListener);
    return factory;
}
~~~

Và chọn factory khi khai báo listener:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "orderKafkaListenerContainerFactory")
public void handle(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

Nếu factory có concurrency lớn hơn 1, Spring Kafka tạo các child containers/consumers tương ứng; mỗi consumer có thể nhận những tập partition khác nhau. Một rebalance listener bean có thể được nhiều child containers sử dụng. Vì vậy:

- Không lưu một biến toàn cục kiểu currentPartition rồi giả định chỉ có một consumer.
- Không xóa toàn bộ partition state của tất cả consumers khi callback chỉ revoke một số partition.
- Nếu dùng shared state, bảo đảm thread safety và có key nhận diện consumer/container phù hợp.
- Mọi thao tác liên quan đến Consumer object phải tuân thủ thread-confinement của KafkaConsumer.

Không nên gắn một rebalance listener mới cho mỗi @KafkaListener bằng cách sửa consumer subscription thủ công sau khi container đã chạy; dùng container factory hoặc cấu hình container được Spring Kafka hỗ trợ.

## 6. Thứ tự before commit và after commit

Spring Kafka container có thể đang giữ các offsets đủ điều kiện commit theo AckMode khi một rebalance xuất hiện. Vì vậy, các hook quanh commit có ý nghĩa vận hành:

~~~text
Kafka gọi quá trình revoke
       |
       v
onPartitionsRevokedBeforeCommit(...)
       |
       v
Spring Kafka container commit pending offsets
       |
       v
onPartitionsRevokedAfterCommit(...)
       |
       v
Consumer bàn giao partition
~~~

**onPartitionsRevokedBeforeCommit** phù hợp để chốt state nội bộ liên quan đến những records đã hoàn thành, đảm bảo không tiếp tục nhận thêm công việc trên các partition bị revoke, hoặc ghi log số lượng in-flight tasks.

**onPartitionsRevokedAfterCommit** phù hợp để đóng resource gắn với partition, cập nhật ownership state trong ứng dụng hoặc ghi nhận checkpoint đã được container thử commit.

Tuy nhiên, tên after commit **không phải lời hứa rằng mọi offset của mọi record đã xử lý bất đồng bộ đều được commit thành công**. Pending offsets phụ thuộc AckMode và trạng thái acknowledgment. Nếu commit thất bại, callback/lifecycle có thể khác; cần quan sát lỗi commit riêng. Với processing bất đồng bộ, ứng dụng phải biết offset nào thực sự hoàn thành trước khi acknowledgment.

Không tự đặt consumer.commitSync() trong before-commit callback chỉ để "chắc chắn", nếu container vốn đã quản lý commits. Việc commit thêm có thể xung đột với pending ack hoặc đưa group offset vượt qua records chưa hoàn thành.

## 7. Vì sao offset commit là rủi ro lớn nhất?

Kafka consumer commits offset để consumer group biết vị trí cần đọc tiếp. Nếu record ở partition P1, offset 40 xử lý thành công, group thường commit **41**, tức vị trí tiếp theo.

~~~text
orders/P1

offset 38 -> hoàn tất
offset 39 -> hoàn tất
offset 40 -> hoàn tất
offset 41 -> chưa hoàn tất

Offset an toàn để commit: 41
~~~

Nếu đang có tác vụ bất đồng bộ ở offset 41 và offset 42, việc commit 43 trước khi offset 41 hoàn tất có thể khiến record 41 bị bỏ qua sau rebalance.

~~~text
Tác vụ:
  offset 41 -> đang gọi REST API
  offset 42 -> hoàn tất

Rebalance đến

Commit offset 43 -> không an toàn
Vì offset 41 chưa hoàn thành
~~~

Điều này thường gặp khi listener nhận record rồi gửi công việc sang ExecutorService và **trả về ngay**, trong khi container dùng ack mode cho phép commit khi method hoàn tất.

Nguyên tắc:

1. Chỉ acknowledge những records đã xử lý thành công theo semantics nghiệp vụ.
2. Không commit offset vượt qua khoảng trống của các records chưa hoàn tất trong cùng partition.
3. Khi revoke, ngăn công việc mới và xử lý các in-flight tasks theo deadline.
4. Nếu không thể hoàn tất an toàn, để records chưa commit được giao lại và dựa vào idempotency để chống lặp side effect.

Commit đúng là điều kiện cần để không mất record; idempotency là điều kiện cần để giảm tác hại khi record bị xử lý lại.

## 8. AckMode và revoke

Spring Kafka có nhiều AckMode, mỗi mode ảnh hưởng thời điểm container commit offsets:

| AckMode | Ý nghĩa khái quát | Điểm cần lưu ý khi revoke |
|---|---|---|
| **RECORD** | Commit theo records được listener xử lý thành công | Thường rõ ràng với listener đồng bộ |
| **BATCH** | Commit sau khi xử lý records của một poll batch | Revoke có thể xuất hiện khi có pending offsets |
| **TIME / COUNT / COUNT_TIME** | Commit dựa trên điều kiện thời gian/số records | Pending offsets có thể chưa commit trước rebalance |
| **MANUAL** | Listener acknowledge, container thực hiện commit theo semantics của mode | Phải kiểm soát ack khi xử lý bất đồng bộ |
| **MANUAL_IMMEDIATE** | Có thể commit khi acknowledge trên consumer thread theo semantics mode | Không tùy ý acknowledge từ thread khác |

Với transactional listener, consumed offsets có thể được đưa vào Kafka transaction do container quản lý; không nên thêm commitSync thủ công trong rebalance callback rồi nghĩ rằng nó sẽ tham gia transaction này.

Chọn AckMode dựa trên processing model thay vì chỉ dựa vào ý muốn "commit nhanh". Với async processing, cần nắm rõ hỗ trợ async acks, thứ tự acknowledgment và cách container pause/seek khi có gaps.

Revoke callback không thể sửa một thiết kế acknowledgment sai từ trước. Nó chỉ là một phần của lifecycle.

## 9. onPartitionsRevoked và onPartitionsLost khác nhau thế nào?

Hai callback biểu thị tình huống sở hữu partition khác nhau:

| Callback | Thời điểm | Việc có thể làm |
|---|---|---|
| **onPartitionsRevoked** | Consumer đang tham gia bàn giao partition theo rebalance bình thường | Chốt tiến độ hoàn thành, bàn giao state, dừng việc mới; commit qua container khi phù hợp |
| **onPartitionsLost** | Partition đã mất ownership trước khi consumer có cơ hội bàn giao thông thường | Ngừng xử lý, giải phóng resources, **không cố commit offset trên partition đã mất** |

Khi partition đã lost, một consumer khác có thể là owner hợp lệ. Cố commit offsets hoặc ghi state như thể mình vẫn sở hữu partition có thể gây commit failure, dữ liệu chồng chéo hoặc race condition.

Ví dụ:

~~~text
Consumer A sở hữu P2
    |
    +-- A bị tạm dừng quá max.poll.interval.ms
    |
Group chuyển P2 sang Consumer B
    |
Consumer A hoạt động lại
    |
    +-- phát hiện mất ownership
    +-- onPartitionsLost(P2) nếu client/container hỗ trợ
    |
    +-- KHÔNG commit offset P2 như owner cũ
    +-- dừng task liên quan và xóa state cục bộ
~~~

Một số phiên bản Kafka/Spring Kafka có method onPartitionsLost mặc định hoặc callback với chữ ký khác; cần xác minh API đang dùng. Quan trọng hơn chữ ký chính là nguyên tắc **không hứa chắc có graceful revoke trước mọi ownership loss**.

## 10. Eager rebalance và cooperative rebalance

Partition assignment strategy ảnh hưởng trực tiếp đến tập partitions trong revoke callback.

### Eager rebalance

Với cơ chế eager truyền thống, members thường nhường toàn bộ assignment hiện tại trước khi group chốt assignment mới.

~~~text
Trước:
  A -> P0, P1
  B -> P2, P3

Eager rebalance:
  A revoke P0, P1
  B revoke P2, P3

Sau:
  A -> P0
  B -> P1, P2, P3
~~~

Ứng dụng có thể quan sát nhiều partition bị revoke ngay cả khi một số partition sau đó được assign lại cho cùng consumer.

### Cooperative rebalance

Với cooperative strategy, group cố giảm lượng partition cần nhường, có thể giữ lại những partitions không cần chuyển owner.

~~~text
Trước:
  A -> P0, P1
  B -> P2, P3

Cooperative rebalance:
  A revoke P1
  B giữ P2, P3

Sau:
  A -> P0
  B -> P1, P2, P3
~~~

Sơ đồ là minh họa đơn giản; cooperative assignment thực tế có thể gồm nhiều vòng rebalance để chuyển ownership an toàn.

**Hệ quả:** callback không được xóa global cache hay đóng tài nguyên của P0 chỉ vì P1 bị revoked. Hãy xử lý đúng **Collection<TopicPartition> partitions** được truyền vào callback.

Chiến lược eager hay cooperative được quyết định bởi partition assignment protocol/assignor và tương thích của members trong group; không nên đoán chỉ từ số consumers.

## 11. Partition-scoped state nên được quản lý thế nào?

Một listener có thể có state gắn với từng partition:

- Bộ đệm records chưa flush.
- Checkpoint hoặc watermark đã hoàn tất.
- In-memory aggregation.
- Connection hoặc cache chuyên biệt theo partition.
- File handle, local temporary state, scheduler, executor queue.
- Metadata về consumer ownership.

Khi revoke, chỉ nên dọn những state của partition trong tập bị thu hồi:

~~~text
Partition state map

P0 -> state A
P1 -> state B
P2 -> state C
P3 -> state D

onPartitionsRevoked(P1, P3):
  close state B
  close state D

Giữ state A, C nếu P0/P2 vẫn được sở hữu.
~~~

Với cache dữ liệu có thể tái dựng, xóa khi revoke thường không gây mất dữ liệu; với dữ liệu chỉ nằm trong bộ nhớ và chưa có checkpoint bền vững, xóa ngay có thể làm mất kết quả chưa commit.

Do đó, thiết kế state nên có quy trình **persist/flush an toàn rồi mới release** khi có thời gian; nếu không có thời gian hoặc ownership đã mất, để record được replay từ committed offset và tái dựng state bằng dữ liệu Kafka.

## 12. Ví dụ: quản lý partition state trong callback

Giả sử ứng dụng quản lý một đối tượng PartitionState riêng cho mỗi TopicPartition. Có thể tách logic cleanup vào service chuyên biệt:

~~~java
public interface PartitionStateRegistry {
    void prepareForRevoke(Collection<TopicPartition> partitions);
    void closeRevoked(Collection<TopicPartition> partitions);
    void initializeAssigned(Collection<TopicPartition> partitions);
}
~~~

Và đăng ký rebalance listener:

~~~java
@Component
public class StateAwareRebalanceListener
        implements ConsumerAwareRebalanceListener {

    private final PartitionStateRegistry stateRegistry;

    public StateAwareRebalanceListener(
            PartitionStateRegistry stateRegistry) {
        this.stateRegistry = stateRegistry;
    }

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        stateRegistry.prepareForRevoke(partitions);
    }

    @Override
    public void onPartitionsRevokedAfterCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        stateRegistry.closeRevoked(partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        stateRegistry.initializeAssigned(partitions);
    }
}
~~~

Ví dụ mô tả **các lifecycle hooks**, không mặc định stateRegistry tự giải quyết concurrency hay durability. Đối với trạng thái được chia sẻ giữa nhiều container threads, registry cần có khóa/key ownership đủ phân biệt instance hoặc child container.

Không lưu Consumer object trong registry để dùng sau ở background thread. KafkaConsumer không được truy cập đồng thời tùy ý từ nhiều threads.

## 13. In-flight asynchronous processing là tình huống nguy hiểm

Giả sử listener gửi một record sang worker pool:

~~~java
@KafkaListener(topics = "orders")
public void handle(ConsumerRecord<String, OrderEvent> record) {
    executor.submit(() -> orderService.process(record.value()));
}
~~~

Đây là một anti-pattern nếu container hiểu rằng method kết thúc có nghĩa record đã được xử lý xong. Callback trả về trước khi business work hoàn tất; một rebalance có thể xảy ra trong lúc task vẫn chạy.

~~~text
Consumer A:
  poll P1@100
  enqueue async task
  listener return

Rebalance:
  A revoke P1
  Consumer B được assign P1

Async task cũ trên A:
  vẫn có thể update database sau revoke
~~~

Nguy cơ gồm:

- Offset đã commit trong khi async task chưa hoàn thành: có thể mất xử lý.
- Offset chưa commit: B xử lý lại record, đồng thời A vẫn chạy task cũ, gây duplicate side effects.
- State gắn partition bị đóng trong khi task còn sử dụng.
- Callback chờ vô hạn để drain worker pool, khiến poll loop không tiến.

Nếu bắt buộc async, cần một mô hình được Spring Kafka hỗ trợ cho acknowledgment bất đồng bộ hoặc một cơ chế phối hợp riêng, có **partition ownership, in-flight tracking, bounded drain, cancellation và idempotency**.

## 14. Chiến lược drain in-flight tasks khi revoke

Một chiến lược thường dùng:

1. Đánh dấu các partition bị revoke thành **closing** trong state registry.
2. Không enqueue công việc mới cho các partition đó.
3. Đợi trong một khoảng thời gian ngắn có giới hạn để các task đã nhận hoàn tất.
4. Ghi nhận checkpoint/ack chỉ cho các offsets liên tục đã thực sự hoàn thành.
5. Hủy hoặc cho phép retry các task còn dang dở theo semantics ứng dụng.
6. Giải phóng state và ownership.

Ví dụ:

~~~text
P1 processing:
  offset 100 -> DONE
  offset 101 -> DONE
  offset 102 -> IN_FLIGHT
  offset 103 -> DONE

onPartitionsRevoked(P1):
  mark closing
  drain <= configured deadline
  last contiguous completed = 101
  commit offset 102 (nếu policy/ownership cho phép)
  không commit 104 vì offset 102 chưa hoàn tất
~~~

Nguyên tắc **contiguous completion** đặc biệt quan trọng khi nhiều tasks cho cùng partition có thể hoàn thành lệch thứ tự. Record 103 DONE không cho phép commit vượt qua record 102 đang IN_FLIGHT.

Nếu callback không thể drain trong deadline, hệ thống phải chấp nhận record chưa hoàn thành được giao lại. Idempotency và retry logic giải quyết rủi ro side effect đã thực hiện một phần.

Không biến revoke callback thành nơi chờ hết toàn bộ batch không giới hạn; callback bị block quá lâu có thể làm rebalance chậm, tăng rủi ro consumer bị mất membership.

## 15. Nên commit offset trong callback không?

Kafka client cho phép một số ứng dụng quản lý offsets thủ công commit trong onPartitionsRevoked nếu vẫn còn ownership và đã hoàn tất công việc. Nhưng trong **Spring Kafka listener container**, container thường quản lý commit theo AckMode và rebalance lifecycle.

Vì vậy, quy tắc ưu tiên:

- Để container commit pending offsets theo chính sách đã cấu hình.
- Chỉ acknowledge records đã hoàn tất.
- Dùng before/after commit callbacks của ConsumerAwareRebalanceListener để phối hợp state.
- Tránh tự gọi commitSync/commitAsync ngay trong callback nếu không có lý do và thiết kế ownership rõ.
- Không cố commit partitions đã lost.

Nếu ứng dụng sử dụng raw KafkaConsumer, tự quản lý poll và manual commits, việc commit trong revoke callback có thể là một phần hợp lệ của giao thức at-least-once. Nhưng thiết kế đó khác với container-managed Spring Kafka; không sao chép nguyên mã raw consumer vào một @KafkaListener container đang có commit logic.

Một lỗi nguy hiểm là commit offset dựa trên **last delivered** thay vì **last completed**. Record đã được listener nhận nhưng nghiệp vụ chưa hoàn thành không nên được xem là processed.

## 16. Manual acknowledgment và callback revoke

Với listener có Acknowledgment:

~~~java
@KafkaListener(
        topics = "orders",
        containerFactory = "manualAckListenerFactory")
public void handle(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment ack) {

    orderService.process(record.value());
    ack.acknowledge();
}
~~~

Đây là ví dụ đồng bộ: ack sau khi process thành công. Factory cần được cấu hình AckMode.MANUAL hoặc MANUAL_IMMEDIATE tùy semantics mong muốn.

Nếu chuyển sang async:

~~~text
Listener nhận record
  |
  +-- gửi task sang executor
  +-- trả về trước khi xử lý hoàn tất
  |
  +-- task hoàn tất ở thread khác
          |
          +-- cần phối hợp acknowledgment đúng API/config
~~~

Spring Kafka có các tùy chọn dành cho out-of-order async acknowledgments trong một số phiên bản, nhưng chúng có điều kiện và hệ quả về pause/commit. Không mặc định có thể gọi Acknowledgment từ bất kỳ thread nào và không kiểm soát thứ tự mà vẫn bảo đảm xử lý đúng.

Rebalance làm tình huống phức tạp hơn: task có thể hoàn tất **sau khi partition đã chuyển owner**. Hãy kiểm tra ownership/generation trước khi ghi nhận tiến độ, và thiết kế side effects idempotent để task cũ không gây sai trạng thái.

## 17. Transactional listener và revoke

Với Kafka container transaction, source offsets được đưa vào cùng Kafka transaction với output Kafka khi listener thành công. Khi transaction thất bại, container có thể abort và sử dụng AfterRollbackProcessor để xử lý lại.

~~~text
Listener transaction đang xử lý P1@100
    |
    +-- produce output trong Kafka transaction
    +-- send source offset vào transaction khi thành công
    |
    +-- rebalance hoặc commit failure
    |
    v
Transaction có thể abort
    |
    +-- output abort không hiển thị với read_committed
    +-- source offset không commit trong transaction lỗi
~~~

**Không gọi consumer.commitSync() trong onPartitionsRevoked để bổ sung offset cho transactional listener**. Commit thủ công nằm ngoài transaction có thể phá vỡ mục tiêu atomically commit output và consumed offsets.

Ngoài ra, Kafka transaction không bảo vệ database/API side effects. Nếu consumer cũ đã ghi database trước khi transaction abort do revoke/rebalance, consumer mới xử lý lại cùng event có thể ghi trùng. Cần idempotency/outbox hoặc version check.

Với giao dịch Kafka, callback nên tập trung vào state và resource lifecycle; offset/transaction completion thuộc container transaction manager.

## 18. Tương tác với max.poll.interval.ms

**max.poll.interval.ms** giới hạn khoảng thời gian giữa các lần poll theo semantics consumer group protocol. Khi business listener xử lý quá lâu hoặc callback revoke chờ quá lâu, consumer có thể không poll đúng hạn.

Ví dụ:

~~~text
max.poll.interval.ms = 120 giây

Business listener xử lý:   95 giây
Revoke callback drain:     40 giây
---------------------------------
Tổng:                     135 giây
~~~

Trong ví dụ, nếu khoảng thời gian giữa các poll thực tế vượt 120 giây, consumer có nguy cơ mất membership. Callback có thể không hoàn tất graceful handoff như kỳ vọng.

Các khuyến nghị:

- Giữ callback ngắn và có deadline cụ thể.
- Không gọi API ngoài với retry vô hạn trong revoke.
- Tách work dài khỏi poll thread theo mô hình có ownership và ack an toàn.
- Giảm max.poll.records nếu một poll batch quá lớn.
- Đo listener processing latency và callback duration.
- Dùng max.poll.interval.ms theo SLO thực tế, không chỉ tăng vô hạn.

Nếu consumer bị mất membership, **onPartitionsLost** và lỗi commit cần được xử lý hợp lý. Không dựa vào việc onPartitionsRevoked luôn có đủ thời gian để flush mọi công việc.

## 19. Graceful shutdown có giống rebalance revoke không?

Khi ứng dụng shutdown hoặc listener container stop, consumer rời group và partition ownership được nhường cho members khác. Trong lifecycle này, callback liên quan đến revoke/cleanup có thể được gọi tùy thời điểm và phiên bản.

Tuy nhiên, **shutdown không hoàn toàn tương đương một rebalance thông thường**:

- Process có thể bị kill trước khi callback chạy.
- Container có shutdown timeout riêng.
- KafkaConsumer có thể không còn kết nối để commit.
- Kubernetes termination grace period có thể hết trước khi các tasks hoàn tất.

Do đó, không nên để toàn bộ cơ chế flush dữ liệu dựa vào onPartitionsRevoked. Dữ liệu có giá trị phải được ghi nhận thường xuyên hoặc nằm trong một hệ thống bền vững.

Ví dụ khi deploy rolling update:

~~~text
Pod A nhận SIGTERM
      |
      v
Spring listener container stop
      |
      v
Consumer rời group
      |
      v
Partition chuyển sang Pod B

Nếu A bị SIGKILL trước cleanup:
  B vẫn phải xử lý lại từ committed offsets an toàn
~~~

Thiết kế đúng cần chịu được cả graceful shutdown và abrupt termination.

## 20. onPartitionsAssigned và khôi phục state

onPartitionsRevoked chỉ là nửa đầu của lifecycle. Khi partition được assign cho consumer mới, ứng dụng có thể phải tải lại state:

~~~text
Consumer A:
  onPartitionsRevoked(P2)
  save checkpoint hợp lệ
  close partition state

Consumer B:
  onPartitionsAssigned(P2)
  load state từ storage
  tiếp tục consume theo committed offset
~~~

Nếu sử dụng Kafka offset làm checkpoint chính, B đọc từ committed offset theo consumer group. Nếu có local state hoặc aggregate snapshot, cần đảm bảo snapshot đồng bộ với offset đã xử lý.

Ví dụ snapshot ghi nhận đã xử lý tới offset 99, trong khi group committed offset là 90: khi B đọc từ 90, phải biết có thể có records được replay và state snapshot có thể đã bao gồm chúng. Một cách an toàn là thiết kế snapshot cùng offset checkpoint theo transaction của store tương ứng hoặc làm replay idempotent.

Không tự seek đến offset lớn hơn group committed offset chỉ vì state cache báo đã xử lý xa hơn, nếu không có cơ chế durability và consistency đủ tin cậy; điều đó có thể bỏ mất records.

## 21. Phân biệt rebalance với partition pause/resume

Spring Kafka có thể pause/resume container hoặc partitions để backoff, throttling hoặc xử lý bất đồng bộ. **Pause không phải revoke**.

| Trạng thái | Ownership | Consumer có thể poll? | Callback revoke? |
|---|---|---|---|
| Partition assigned và active | Vẫn sở hữu | Có | Không vì chỉ đang active |
| Partition paused | Vẫn sở hữu | Có thể poll để duy trì membership | Không chỉ vì pause |
| Partition revoked | Đang bàn giao ownership | Không nên xử lý tiếp partition đó | Có thể gọi revoke callback |
| Partition lost | Đã mất ownership | Không còn là owner hợp lệ | Lost callback khi hỗ trợ |

Không dọn partition state chỉ vì Spring Kafka pause partition. Nếu pause chỉ nhằm chờ retry, state sẽ còn được dùng khi resume.

Ngược lại, khi onPartitionsRevoked được gọi, không giả định có thể resume partition đó sau callback. Consumer khác có thể trở thành owner.

## 22. Cooperative rebalance: xử lý chính xác tập partition

Một lỗi phổ biến khi chuyển từ eager sang cooperative:

~~~java
@Override
public void onPartitionsRevokedBeforeCommit(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> revoked) {

    stateRegistry.clearAll(); // Không nên: có thể xóa state của partition vẫn owned.
}
~~~

Thiết kế phù hợp hơn:

~~~java
@Override
public void onPartitionsRevokedBeforeCommit(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> revoked) {

    stateRegistry.prepareForRevoke(revoked);
}
~~~

Registry dùng từng TopicPartition trong **revoked** để đánh dấu closing, không suy luận mọi partition trong group đều phải dừng.

Với eager rebalance, tập bị revoke có thể rộng hơn; xử lý theo tập tham số vẫn đúng. Với cooperative, cách làm này đặc biệt quan trọng để không gây gián đoạn cho partitions vẫn được giữ.

Khi thay đổi assignor/protocol trong rolling deploy, phải kiểm tra tính tương thích giữa các consumers của cùng group, không tự chuyển một consumer riêng lẻ sang mode khác mà bỏ qua quy tắc phối hợp group.

## 23. Tránh thao tác nguy hiểm trong callback

Các việc nên tránh trong onPartitionsRevoked:

- **Chờ vô hạn** cho async tasks hoặc external API.
- **Ghi offset bằng last fetched offset** thay vì last completed offset.
- **Gọi consumer.commitSync** bên ngoài chính sách commit của container mà không kiểm soát.
- **Gửi Consumer object sang background thread**, vì KafkaConsumer không thread-safe.
- **Xóa state toàn bộ group** khi chỉ một subset partition bị revoked.
- **Seek/pause/resume tùy tiện** trong callback mà không theo container lifecycle.
- **Khởi tạo Kafka listener container mới** bên trong callback.
- **Nuốt mọi lỗi flush** rồi coi checkpoint đã thành công.
- **Giữ lock toàn cục** trên cache/registry quá lâu và chặn các consumer threads khác.

Một callback an toàn thường chỉ đánh dấu partition closing, flush những dữ liệu đã hoàn tất theo cơ chế có giới hạn, log trạng thái và release resources. Các thao tác cần lâu nên được thiết kế từ trước bằng checkpoint định kỳ hoặc durable queues, không chờ đến lúc rebalance mới thực hiện.

## 24. Lỗi flush/checkpoint trong revoke phải xử lý ra sao?

Giả sử ứng dụng có stateful aggregation và cần flush một snapshot khi partition bị revoke. Nếu flush thất bại, không nên ghi log thành công hoặc commit offset vượt qua state chưa bền vững.

~~~text
Partition P2:
  Kafka consumed offsets 0..100
  In-memory state đã áp dụng tới 100
  Last durable checkpoint tới 95

Revoke đến:
  flush state tới 100 -> FAILURE

Không được tự khẳng định checkpoint tới 100.
~~~

Hướng xử lý phụ thuộc kiến trúc:

- Nếu có thể tái dựng state từ Kafka, cho phép replay từ checkpoint/offset an toàn.
- Nếu mất state dẫn đến mất dữ liệu không thể tái dựng, cần đưa trạng thái sang durable store trong lúc processing thay vì chỉ khi revoke.
- Nếu commit offset và state checkpoint cần nhất quán, dùng một protocol/transaction của state store hoặc idempotent replay strategy.
- Ghi rõ failure metric và alert; tránh retry vô hạn ngay trong callback.

Với Spring Kafka container-managed commits, callback trước commit không có nghĩa có thể chặn mọi commit tương lai chỉ bằng cách trả về false. Cần thiết kế exception propagation/ack logic theo API cụ thể; không dựa vào callback như một distributed transaction hook.

## 25. Logging và metrics cho rebalance lifecycle

Để phân tích rebalance, log phải cho biết **consumer nào, partition nào, lúc nào và đã làm gì**.

Ví dụ structured log do ứng dụng tạo:

~~~text
event=partitions_revoked
listenerId=orders-listener-2
groupId=orders-service
partitions=[orders-1,orders-3]
inFlight=4
lastContiguousCompleted={orders-1:104,orders-3:88}
drainTimedOut=true
durationMs=750
~~~

Các metric hữu ích:

- Số lần rebalance và số partition bị revoke/assigned/lost.
- Thời gian thực thi callback revoke, p95/p99.
- Số in-flight tasks khi bắt đầu revoke.
- Số in-flight tasks còn lại khi callback kết thúc.
- Số lần flush/checkpoint thất bại.
- Consumer lag và commit failure rate.
- Rebalance duration và member churn.
- Khoảng thời gian giữa các lần poll.
- Tỷ lệ duplicate processing sau rebalance.
- Thời gian load state khi partitions assigned.

Không dùng offset hoặc event ID làm metric labels có cardinality cao. Offset phù hợp với log/trace; metrics nên gắn nhãn tập giá trị kiểm soát như listener, group, topic và outcome.

Nếu mọi consumer liên tục revoke/assign và lag tăng, hãy điều tra thời gian xử lý, group churn, deployment rollout, poll interval, network và coordinator, thay vì chỉ tăng số replicas.

## 26. Điều tra khi consumer bị revoke liên tục

Một quy trình chẩn đoán:

1. Xác định group và consumer instance nào đang rebalance.
2. Kiểm tra có pod scale up/down, crash/restart hoặc rolling deployment không.
3. Đọc consumer group state và partition assignment.
4. So sánh listener processing time với max.poll.interval.ms.
5. Kiểm tra logs heartbeat, commit errors và coordinator disconnects.
6. Đo onPartitionsRevoked callback duration.
7. Kiểm tra async tasks hoặc khóa toàn cục có giữ thread lâu không.
8. Xem assignor eager/cooperative và tính tương thích group members.
9. Kiểm tra producer fencing/transaction abort nếu listener transactional.
10. Xác nhận offsets không bị commit vượt các in-flight records.

Không xem mọi callback revoke là lỗi. Rebalance khi scale hoặc deploy là hoạt động bình thường. Nó trở thành vấn đề reliability khi quá thường xuyên, kéo dài, làm lag tăng hoặc dẫn đến mất/nhân đôi side effect không kiểm soát.

## 27. Kiểm thử onPartitionsRevoked bằng integration test

Nên kiểm thử với Kafka broker thực hoặc Testcontainers Kafka, vì mock listener callback đơn lẻ không tái hiện được consumer group protocol, assignment và commit behavior.

### Test 1: consumer mới tham gia

1. Tạo topic có nhiều partitions.
2. Khởi chạy Consumer A trong group.
3. Chờ A được assign partitions.
4. Khởi chạy Consumer B cùng group.
5. Quan sát callback revoked/assigned theo assignor đang dùng.
6. Xác nhận không có record bị bỏ qua hoặc xử lý sai sau handoff.

### Test 2: cooperative partial revoke

1. Dùng assignment strategy phù hợp, được tất cả group members hỗ trợ.
2. Cấu hình state registry theo TopicPartition.
3. Gây rebalance chuyển chỉ một phần partitions.
4. Xác nhận chỉ state của revoked partitions bị đóng.
5. Xác nhận partitions không bị revoke vẫn xử lý được.

### Test 3: in-flight task chưa hoàn thành

1. Đưa record vào worker pool và chặn task bằng cơ chế test.
2. Gây rebalance khi task vẫn in-flight.
3. Xác nhận callback không commit vượt qua record chưa hoàn thành.
4. Cho consumer mới xử lý record chưa committed.
5. Xác nhận side effect idempotent khi task cũ cũng hoàn tất muộn.

### Test 4: shutdown đột ngột

1. Consumer A đang xử lý record.
2. Kill process hoặc container mà không graceful revoke.
3. Khởi chạy Consumer B.
4. Xác nhận B đọc lại từ committed offset hợp lệ.
5. Xác nhận không dựa vào callback revoke để giữ dữ liệu độc nhất.

### Test 5: callback drain timeout

1. Giả lập một external operation không hoàn tất trong deadline.
2. Gây revoke.
3. Đo callback trả về trong thời gian cho phép.
4. Xác nhận outstanding records vẫn có đường retry.
5. Xác nhận metric/alert báo in-flight còn tồn tại.

### Test 6: transactional listener

1. Cấu hình Kafka consume-process-produce có transaction.
2. Gây rebalance hoặc lỗi trong transaction trước commit.
3. Xác nhận aborted Kafka outputs không visible với downstream read_committed.
4. Xác nhận consumed offsets không commit sai.
5. Xác nhận DB/API side effects có idempotency nếu tồn tại.

Test nên dùng event ID cố định, record key có phân phối partition dự đoán được và condition-based waits có timeout. Không dùng sleep dài rồi giả định rebalance chắc chắn đã hoàn tất.

## 28. Những hiểu nhầm thường gặp

**onPartitionsRevoked chỉ là callback để log.** Không đúng. Nó là ranh giới ownership quan trọng cho partition-scoped state, offset và in-flight work.

**onPartitionsRevoked luôn được gọi trước khi consumer mất partition.** Không đúng trong mọi sự cố. Consumer có thể mất membership hoặc chết đột ngột trước graceful revoke.

**Danh sách partition bị revoke luôn là toàn bộ assignment.** Không đúng, đặc biệt với cooperative rebalance.

**AfterCommit có nghĩa mọi async task đã hoàn tất.** Không đúng. Nó chỉ liên quan bước container commit pending offsets theo chính sách; async completion cần quản lý riêng.

**Có thể commit last fetched offset khi revoke.** Không đúng. Chỉ commit tiến độ records đã hoàn thành liên tục; last fetched có thể vượt qua records chưa xử lý.

**KafkaConsumer thread-safe nên callback có thể gửi Consumer sang executor.** Không đúng. KafkaConsumer không được sử dụng đồng thời tùy ý.

**onPartitionsLost cũng là dịp commit offset.** Không đúng. Ownership đã mất, không nên cố commit như owner cũ.

**Partition pause đồng nghĩa partition revoke.** Không đúng. Pause thường vẫn giữ assignment, còn revoke là chuyển ownership.

**Thêm concurrency sẽ luôn giảm rebalance impact.** Không đúng. Concurrency có giới hạn theo partitions và làm tăng member/resource overhead.

**Kafka transaction sẽ rollback DB side effect khi revoke.** Không đúng. Kafka transaction không tự rollback DB/API ngoài transaction đó.

**Commit offset nhanh là luôn tốt.** Không đúng. Commit quá sớm có thể làm mất processing của record chưa hoàn thành; commit quá muộn làm tăng replay. Cần chọn boundary an toàn.

## 29. Nguyên tắc thiết kế production

Khi triển khai onPartitionsRevoked cho Spring Kafka listener:

1. Hiểu assignor/protocol của group: eager hay cooperative.
2. Dùng ConsumerAwareRebalanceListener để phối hợp với lifecycle commit của container.
3. Xử lý đúng tập TopicPartition được truyền vào callback, không xóa toàn bộ state.
4. Chọn AckMode và commit policy dựa trên **processed** chứ không phải **fetched** records.
5. Với async work, có tracking theo partition, contiguous offset completion và bounded drain.
6. Chấp nhận record có thể được replay; bảo vệ side effects bằng idempotency.
7. Không gọi Consumer API từ background thread.
8. Không tự commit offset bên ngoài Kafka transaction trong transactional listener.
9. Khi onPartitionsLost, chỉ cleanup an toàn; không giả định còn quyền commit.
10. Thiết kế partition state có thể khôi phục từ storage hoặc Kafka replay sau crash.
11. Giữ callback ngắn, đo thời gian và không chặn poll loop quá giới hạn.
12. Theo dõi rebalance, revoked partitions, in-flight work, commit errors và consumer lag.
13. Kiểm thử partial revoke, abrupt shutdown, async work và transaction abort.

**onPartitionsRevoked** là điểm chuyển giao quyền sở hữu partition giữa các Kafka consumers. Trong Spring Kafka, callback này phải được hiểu cùng listener container, AckMode, offset commit, AfterRollbackProcessor và cơ chế rebalance của group. Khi thiết kế tốt, callback giúp bàn giao state gọn gàng và hạn chế rủi ro mất hoặc lặp xử lý. Nhưng chính **commit offset đúng, lưu state bền vững và idempotent processing** mới bảo vệ hệ thống trong cả những trường hợp không có cơ hội graceful revoke.
