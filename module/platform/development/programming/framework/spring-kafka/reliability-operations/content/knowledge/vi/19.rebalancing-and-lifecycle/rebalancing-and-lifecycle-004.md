# onPartitionsLost

Trong Spring Kafka, một consumer thuộc consumer group chỉ được xử lý những partition đang được assign cho nó. Assignment không cố định: Kafka có thể phân phối lại partition khi consumer tham gia hoặc rời group, khi số partition thay đổi hoặc khi một consumer không còn đáp ứng các điều kiện duy trì thành viên.

**onPartitionsLost** là callback báo rằng consumer **đã mất quyền sở hữu** một tập partition, thường trong tình huống không còn cơ hội thực hiện quy trình thu hồi (revoke) bình thường trước khi assignment được chuyển sang consumer khác. Đây là tín hiệu quan trọng trong cơ chế **rebalance và lifecycle**, bởi sau thời điểm này ứng dụng không được tiếp tục hành xử như thể mình còn là chủ sở hữu hợp lệ của những partition đó.

Bài học phân tích sự khác biệt giữa onPartitionsLost và onPartitionsRevoked, cách đăng ký callback trong Spring Kafka, cách dừng hoặc vô hiệu hóa công việc bất đồng bộ, ảnh hưởng tới offset và transaction, và những trường hợp cần kiểm thử khi vận hành consumer group.

## 1. Bối cảnh: partition ownership trong consumer group

Giả sử topic orders.events có sáu partition và consumer group order-processors có ba consumer:

    orders.events:
       P0  P1  P2  P3  P4  P5

    Consumer A: P0, P1
    Consumer B: P2, P3
    Consumer C: P4, P5

Trong cùng một consumer group, một partition được assign cho tối đa một consumer tại một thời điểm theo quyết định của group coordinator. Assignment quyết định consumer nào có trách nhiệm poll và xử lý record từ partition đó.

Khi consumer B bị mất kết nối quá lâu, group coordinator có thể loại nó khỏi group. Các partition P2 và P3 được giao cho thành viên còn hoạt động. Nếu B khôi phục kết nối sau đó và tham gia lại group, nó có thể biết rằng mình đã mất quyền sở hữu P2/P3.

    Trước sự cố: Consumer B sở hữu P2, P3
                    |
                    v
          B không còn tham gia group hợp lệ
                    |
                    v
        Coordinator phân công P2, P3 cho consumer khác
                    |
                    v
       B tiếp tục hoạt động / poll / tham gia lại
                    |
                    v
              onPartitionsLost(P2, P3)

Điều ứng dụng cần phản ứng không phải “cố commit cho xong”, mà là **ngừng mọi hoạt động yêu cầu quyền sở hữu P2/P3**, làm sạch trạng thái cục bộ và để consumer mới tiếp quản.

## 2. Tại sao có callback riêng cho lost?

Kafka có ba mốc thường được trình bày qua ConsumerRebalanceListener:

- **onPartitionsAssigned:** consumer được assign các partition mới; chuẩn bị state và bắt đầu xử lý.
- **onPartitionsRevoked:** consumer được thông báo thu hồi partition trong một rebalance có kiểm soát; nó có thể còn cơ hội hoàn tất những thao tác hợp lệ theo contract.
- **onPartitionsLost:** partition đã bị mất mà consumer không còn quyền ownership; không được giả định vẫn có thể commit offset hay sửa trạng thái với tư cách chủ sở hữu.

So sánh:

| Callback | Ý nghĩa | Commit offset trong callback? | Hành động ưu tiên |
|---|---|---|---|
| onPartitionsAssigned | Nhận quyền sở hữu partition | Không phải thời điểm commit chính | Khởi tạo state, lease, cache |
| onPartitionsRevoked | Sắp nhường ownership trong rebalance có kiểm soát | Có thể cân nhắc theo contract và mode commit | Hoàn tất/flush công việc an toàn, dừng xử lý |
| onPartitionsLost | Quyền sở hữu đã mất | **Không nên cố commit với tư cách owner cũ** | Invalidate công việc cũ, giải phóng state |
 
Trong cooperative rebalance, revoke thường chỉ xảy ra với các partition thực sự cần chuyển đi thay vì toàn bộ assignment. Trong các tình huống mất thành viên hoặc xử lý không kịp, callback lost vẫn quan trọng vì quá trình bàn giao bình thường có thể không diễn ra.

Không phải mọi lần rebalance đều gọi onPartitionsLost. Đây không phải callback “sau mỗi lần onPartitionsRevoked”.

## 3. Ngữ nghĩa quan trọng nhất: không còn ownership

Sau onPartitionsLost, partition có thể đã được assign cho một consumer khác. Nếu consumer cũ tiếp tục commit offset, cập nhật checkpoint hoặc ghi dữ liệu như mình vẫn là owner, có thể xảy ra:

1. Consumer mới bắt đầu xử lý lại record từ committed offset.
2. Consumer cũ vẫn còn task chạy nền chưa hoàn tất.
3. Cả hai cùng thực hiện side effect cho cùng event.
4. Checkpoint hoặc state từ consumer cũ đè lên tiến độ mới.

Ví dụ:

    P2 offset 900: OrderUpdated(evt-900)
                |
                +--> Consumer B đã gọi DB, chưa hoàn tất
                |
          B mất ownership P2
                |
                +--> Consumer D được assign P2
                            |
                            +--> D xử lý evt-900
                |
                +--> Task cũ của B quay lại và cập nhật DB

Callback lost giúp consumer cũ **biết phải dừng hoặc vô hiệu hóa task**, nhưng bản thân callback không thể hoàn tác tác vụ đã gửi ra hệ thống ngoài Kafka. Vì vậy, muốn chống xử lý trùng và ghi đè trạng thái cần thêm **idempotency, fencing hoặc optimistic concurrency** ở nơi lưu dữ liệu.

## 4. API Kafka client: ConsumerRebalanceListener

Kafka Java client cung cấp interface org.apache.kafka.clients.consumer.ConsumerRebalanceListener. Các callback cơ bản dùng Collection<TopicPartition>:

~~~java
public class OrderRebalanceListener implements ConsumerRebalanceListener {

    @Override
    public void onPartitionsAssigned(
            Collection<TopicPartition> partitions) {
        log.info("Assigned partitions: {}", partitions);
    }

    @Override
    public void onPartitionsRevoked(
            Collection<TopicPartition> partitions) {
        log.info("Revoked partitions: {}", partitions);
    }

    @Override
    public void onPartitionsLost(
            Collection<TopicPartition> partitions) {
        log.warn("Lost partitions: {}", partitions);
    }
}
~~~

Các import chính:

~~~java
import java.util.Collection;
import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import org.apache.kafka.common.TopicPartition;
~~~

onPartitionsLost là method được hỗ trợ ở các phiên bản Kafka client có cơ chế callback lost. Với một số phiên bản, default implementation của callback lost có thể chuyển tiếp sang logic revoked nếu ứng dụng không override. **Nếu revoked handler có logic commit offset, hãy override lost rõ ràng để tránh tái sử dụng logic commit ở thời điểm đã mất ownership.**

Kafka consumer callback chạy trong ngữ cảnh hoạt động poll/rebalance của consumer, không phải một worker nền tùy ý do ứng dụng tự tạo. Callback nên ngắn gọn, thread-safe và không làm poll thread bị block kéo dài.

## 5. API Spring Kafka: ConsumerAwareRebalanceListener

Spring Kafka cung cấp ConsumerAwareRebalanceListener để callback có thể nhận thêm đối tượng Kafka Consumer. Trong listener container Spring Kafka, đây là điểm mở rộng thường dùng để theo dõi lifecycle assignment theo từng consumer.

Các method hay gặp:

- onPartitionsAssigned(Consumer<?, ?> consumer, Collection<TopicPartition> partitions)
- onPartitionsRevokedBeforeCommit(Consumer<?, ?> consumer, Collection<TopicPartition> partitions)
- onPartitionsRevokedAfterCommit(Consumer<?, ?> consumer, Collection<TopicPartition> partitions)
- onPartitionsLost(Consumer<?, ?> consumer, Collection<TopicPartition> partitions)

Spring Kafka cung cấp các callback trước/sau logic commit của container nhằm cho phép ứng dụng phối hợp thao tác vào thời điểm phù hợp. Không nên dựa vào thứ tự của những callback này bằng suy đoán khi cấu hình AckMode hoặc transaction khác nhau; hãy đọc contract của phiên bản đang sử dụng.

Một mẫu cấu hình:

~~~java
@Configuration
public class OrderKafkaListenerConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            PartitionLifecycleService lifecycleService) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
                .setConsumerRebalanceListener(
                    new ConsumerAwareRebalanceListener() {

                        @Override
                        public void onPartitionsAssigned(
                                Consumer<?, ?> consumer,
                                Collection<TopicPartition> partitions) {

                            lifecycleService.onAssigned(partitions);
                        }

                        @Override
                        public void onPartitionsRevokedBeforeCommit(
                                Consumer<?, ?> consumer,
                                Collection<TopicPartition> partitions) {

                            lifecycleService.onRevoking(partitions);
                        }

                        @Override
                        public void onPartitionsLost(
                                Consumer<?, ?> consumer,
                                Collection<TopicPartition> partitions) {

                            lifecycleService.onLost(partitions);
                        }
                    }
                );

        return factory;
    }
}
~~~

Listener tham chiếu factory:

~~~java
@KafkaListener(
    id = "orders",
    topics = "orders.events",
    groupId = "order-processors",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

OrderEvent và PartitionLifecycleService là các kiểu/bean của ứng dụng, cần định nghĩa. Ví dụ tập trung vào cách nối callback vào container, không phải một project chạy độc lập.

Vì một factory có thể tạo nhiều child containers khi concurrency lớn hơn 1, callback và lifecycleService phải chịu được việc được gọi từ nhiều consumer thread. Không dùng một biến mutable chung để lưu “partition hiện tại” mà không gắn với owner cụ thể.

## 6. Cấu hình cơ bản bằng Spring Boot

Ví dụ consumer group ba consumer thread mỗi instance:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processors
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
    listener:
      concurrency: 3
      ack-mode: record
~~~

Điều cần hiểu:

- concurrency=3 tạo ba consumer trong một application instance khi factory phù hợp.
- Nếu có hai instance với concurrency=3, group có thể có sáu consumer.
- max.poll.interval.ms liên quan khoảng thời gian giữa các poll; listener quá chậm có thể khiến consumer không duy trì tư cách thành viên hợp lệ.
- enable-auto-commit=false để container quản lý việc commit theo AckMode.
- AckMode.RECORD là một cách commit theo record listener; nó không biến onPartitionsLost thành thời điểm có thể commit tùy ý.

Cấu hình Spring Boot không tự đăng ký callback tùy chỉnh. Muốn dùng ConsumerAwareRebalanceListener cần gắn nó vào ContainerProperties của factory hoặc listener container tương ứng.

## 7. Khi nào onPartitionsLost được gọi?

Một số tình huống có thể dẫn tới lost ownership:

**Consumer không poll kịp:** listener xử lý quá lâu, hoặc bị block ở HTTP/database, dẫn tới vượt max.poll.interval.ms. Group có thể tiến hành phân công lại partition.

**Kết nối và membership bị gián đoạn:** một consumer mất liên lạc đủ lâu để coordinator xem nó không còn là thành viên hợp lệ. Khi nó khôi phục và đi vào luồng poll/rebalance, callback lost có thể được gọi.

**Rebalance không có revocation bàn giao bình thường:** membership hoặc coordinator state thay đổi khiến consumer phát hiện partition đã không còn thuộc về nó.

**Ứng dụng sử dụng worker async sai cách:** listener nhanh chóng gửi việc vào executor rồi poll tiếp. Consumer vẫn poll, nhưng task cũ có thể kéo dài qua rebalance và trở thành công việc của owner cũ.

Cần phân biệt **nguyên nhân làm mất ownership** với **điều kiện callback được thực thi**. Nếu JVM crash hoặc pod bị kill tức thì, không có thread nào còn sống để thực thi onPartitionsLost. Nếu consumer bị treo vĩnh viễn mà không poll lại, callback cũng có thể không chạy đúng lúc. Vì thế không được phụ thuộc duy nhất vào callback để giải phóng distributed lock hoặc lease.

## 8. onPartitionsRevoked và onPartitionsLost không thể dùng thay nhau

Trong revoke thông thường, consumer biết trước mình chuẩn bị nhường partition. Ứng dụng có thể ngừng nhận thêm việc, hoàn tất những task cần thiết và phối hợp commit/checkpoint theo contract.

Trong lost, Kafka đã xem consumer không còn owner. Một task cũ có thể vẫn đang chạy, và consumer mới có thể đã bắt đầu.

    Revoke có kiểm soát:
      Owner A -> Callback revoked -> Dừng/commit an toàn -> Owner B

    Lost:
      Owner A bị loại khỏi group
           -> Owner B có thể đã nhận partition
           -> Owner A về sau mới biết qua callback lost

Vì vậy:

- Trong revoked, có thể thiết kế bước graceful drain ngắn và commit offset nếu còn phù hợp.
- Trong lost, **không commit offset**, không khẳng định task cũ hoàn tất thay mặt group.
- Trong cả hai, cần ngăn task cũ tiếp tục ghi side effect khi không còn hợp lệ.
- Trong lost, giải phóng tài nguyên cục bộ và phát tín hiệu cảnh báo/metric có thể quan trọng hơn việc cố cứu checkpoint.

Nếu lưu một cache chỉ dùng cho partition đang sở hữu, cần đảm bảo cache được xóa khi lost. Nhưng nếu cache được chia sẻ với consumer mới trong cùng JVM, thao tác xóa phải gắn với đúng owner token để không xóa nhầm trạng thái của assignment mới.

## 9. Điều không nên làm trong onPartitionsLost

Những hành động nguy hiểm:

~~~java
@Override
public void onPartitionsLost(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    // KHÔNG LÀM: cố commit offset khi đã mất ownership.
    consumer.commitSync();

    // KHÔNG LÀM: giả định seek làm mình có lại partition.
    for (TopicPartition tp : partitions) {
        consumer.seek(tp, 0L);
    }
}
~~~

Đoạn trên là ví dụ **sai**, không phải cấu hình khuyến nghị. Commit có thể thất bại do group generation/ownership không còn hợp lệ; một lần commit sai thời điểm còn gây rủi ro ghi nhận tiến độ không đúng. Seek không tái cấp quyền sở hữu partition.

Các hành động khác nên tránh:

- Gọi acknowledge() cho record cũ chỉ vì callback đã xảy ra.
- Ghi checkpoint bên ngoài với nhãn “hoàn tất” nếu task chưa hoàn tất.
- Chờ vô hạn để executor drain trong callback.
- Giữ lock lâu, gọi API mạng blocking hoặc thực hiện database transaction lớn trong callback.
- Nuốt exception từ logic dừng task rồi xem việc thu hồi đã thành công.
- Hủy toàn bộ state theo partition name mà không biết state thuộc owner cũ hay assignment mới.

Mục tiêu callback là **invalidate quyền làm việc cũ và làm sạch nhanh**. Recovery cần thực hiện bởi cơ chế phù hợp, không phải “cố commit lần cuối” khi ownership đã mất.

## 10. Ví dụ callback an toàn: ghi metric và báo hiệu lost

Một chiến lược đơn giản là chuyển sự kiện lost tới service quản lý lifecycle:

~~~java
public final class PartitionLifecycleService {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionLifecycleService.class);

    private final LongAdder lostCount = new LongAdder();

    public void onAssigned(Collection<TopicPartition> partitions) {
        log.info("Assigned: {}", partitions);
    }

    public void onRevoking(Collection<TopicPartition> partitions) {
        log.info("Revoking: {}", partitions);
    }

    public void onLost(Collection<TopicPartition> partitions) {
        lostCount.add(partitions.size());

        for (TopicPartition partition : partitions) {
            log.warn(
                "Consumer lost ownership topic={} partition={}",
                partition.topic(),
                partition.partition()
            );
        }

        // Tín hiệu hủy/invalid công việc cũ phải không blocking.
        // Nếu có nhiều child consumers, cần match owner token cụ thể.
    }

    public long lostPartitionsTotal() {
        return lostCount.sum();
    }
}
~~~

Các import liên quan:

~~~java
import java.util.Collection;
import java.util.concurrent.atomic.LongAdder;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

Ví dụ này chỉ log và đếm sự kiện, chưa hoàn thành cơ chế fencing. Trong hệ thống chỉ xử lý listener đồng bộ và không sở hữu state bên ngoài, đây có thể là bước quan sát đủ dùng. Với xử lý bất đồng bộ hoặc partition-local state quan trọng, cần bổ sung ownership tracking và hủy công việc có kiểm soát.

Metrics nên phân biệt lost và revoked. Một đợt scale bình thường có thể tạo revoked nhiều lần; lost tăng đột biến có thể cho thấy consumer đang bị treo, poll quá chậm hoặc membership không ổn định.

## 11. Bảo vệ công việc async bằng ownership token

Một listener có thể giao record cho ExecutorService để xử lý bất đồng bộ:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    executor.submit(() -> process(record));
}
~~~

Mẫu này **không an toàn nếu container coi record đã xử lý ngay khi listener trả về**. Ngoài vấn đề mất ownership, offset có thể commit trước khi process() hoàn tất.

Nếu thật sự cần async, kiến trúc phải quản lý:

1. Assignment token cho mỗi lần nhận partition.
2. Tình trạng token còn hợp lệ hay đã lost/revoked.
3. Thời điểm task hoàn tất và side effect được commit.
4. Acknowledgment gắn với hoàn tất thực tế, không gắn với submit().
5. Cơ chế fencing ở database hoặc dependency để task cũ không ghi đè task mới.

Ví dụ kiểm tra token về mặt ý tưởng:

~~~java
public record PartitionClaim(
        TopicPartition partition,
        long epoch,
        AtomicBoolean valid) {

    public void invalidate() {
        valid.set(false);
    }

    public void assertValid() {
        if (!valid.get()) {
            throw new CancellationException(
                "Partition ownership has been lost"
            );
        }
    }
}
~~~

Khi onPartitionsAssigned, hệ thống tạo claim mới; khi onPartitionsLost, invalidate claim **thuộc chính consumer cũ**; khi task chuẩn bị ghi dữ liệu, nó kiểm tra claim.

Nhưng chỉ kiểm tra AtomicBoolean trước khi ghi DB **chưa đủ để fencing nguyên tử**: trạng thái có thể bị đổi sau kiểm tra nhưng trước khi commit DB. Nếu cần chống owner cũ tuyệt đối, database phải thực thi fencing token/epoch theo một câu lệnh có điều kiện hoặc unique constraint.

Ví dụ kiểm tra và ghi trạng thái có fence:

~~~sql
UPDATE partition_projection
SET processed_offset = :new_offset,
    state_json = :new_state
WHERE topic = :topic
  AND partition_id = :partition
  AND owner_epoch = :current_epoch
  AND processed_offset < :new_offset;
~~~

Ở đây owner_epoch phải do một coordinator/lease store bảo đảm tăng hoặc thay đổi có tính đồng bộ. Một biến đếm trong RAM của pod không tự là fencing token toàn cục giữa các instance. Ngoài ra, processed_offset chỉ phù hợp khi state được thiết kế đơn điệu theo offset và transaction DB kiểm soát điều kiện ghi.

## 12. Không xóa nhầm state của assignment mới

Khi concurrency lớn hơn 1, các callback có thể chạy trên nhiều child consumer. Cũng có thể một partition được thu hồi khỏi consumer A rồi assign cho consumer B trong cùng application instance.

Mẫu sai:

~~~java
// Map chia sẻ mọi child consumer.
Map<TopicPartition, PartitionState> states = new ConcurrentHashMap<>();

void onLost(Collection<TopicPartition> lost) {
    // Có thể xóa state mới nếu B đã gắn state cho cùng partition.
    lost.forEach(states::remove);
}
~~~

Nếu callback của owner cũ chạy sau khi owner mới đã thêm state cùng key, việc remove theo partition đơn thuần có thể xóa state hợp lệ của B.

Một thiết kế có owner identity:

~~~java
record PartitionState(String ownerId, long epoch) {}

void removeOldOwner(
        TopicPartition partition,
        String oldOwnerId,
        ConcurrentMap<TopicPartition, PartitionState> states) {

    states.computeIfPresent(partition, (tp, current) ->
        current.ownerId().equals(oldOwnerId) ? null : current
    );
}
~~~

Đoạn trên giả định ownerId là ID duy nhất cho **một assignment/consumer owner**, được quản lý bởi ứng dụng. Khi dùng trong production, phải cung cấp ownerId đúng vào callback và dùng cùng ID trong state tạo lúc assign.

Ý tưởng cốt lõi: callback lost được phát ra cho owner cũ, nên chỉ được làm sạch tài nguyên của owner cũ. Với distributed lease, việc release cũng phải có điều kiện theo lease token; không release lock bằng key partition mà không xác minh token.

## 13. Offset commit khi partition đã lost

Commit offset là thao tác nhạy cảm với ownership và group generation. Một consumer không còn assignment hợp lệ không thể tiếp tục coi offset của mình là tiến độ chính thức của group.

Trong onPartitionsRevoked có kiểm soát, ứng dụng có thể hoàn tất/commit những offset đã xử lý tùy chính sách; Spring Kafka container cũng có cơ chế commit pending offsets ở những thời điểm xác định.

Trong onPartitionsLost:

- **Không thực hiện consumer.commitSync()/commitAsync() như một bước cleanup.**
- Không đánh dấu offset chưa được xử lý thành công là đã hoàn tất.
- Không tự seek/assign lại partition để giành lại ownership.
- Không gọi acknowledgment muộn cho record thuộc assignment đã mất như thể nó vẫn hợp lệ.
- Chấp nhận khả năng một số record phải redeliver từ committed offset trước đó.

Ví dụ:

    Committed offset = 400
    A poll offsets 400..409
    A xử lý 400, 401 nhưng chưa commit
    A mất ownership
    B nhận partition từ offset 400

B có thể xử lý lại các record 400, 401. Đây là hành vi phù hợp với at-least-once delivery khi commit của A chưa hoàn tất. Ứng dụng cần idempotency theo eventId để tránh side effect trùng.

Nếu muốn giảm replay, hãy tối ưu thời điểm commit trong chế độ đang dùng và graceful revocation; **đừng dùng onPartitionsLost để commit bù sau khi ownership đã mất**.

## 14. onPartitionsLost với AckMode.MANUAL và MANUAL_IMMEDIATE

Với Spring Kafka manual acknowledgment, ứng dụng nhận Acknowledgment để xác nhận record sau khi hoàn tất side effect:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "order-processors"
)
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment ack) {

    orderService.processIdempotently(record.value());
    ack.acknowledge();
}
~~~

Phương thức trên minh họa xử lý đồng bộ trước acknowledgment. Với listener async, ack có thể xảy ra sau khi assignment thay đổi, tùy container và chính sách async acks; cần kiểm soát riêng.

Một số điểm cần nhớ:

- MANUAL và MANUAL_IMMEDIATE khác nhau về thời điểm container thực hiện commit.
- Một acknowledgment từ task cũ sau lost không được coi là cơ chế hợp lệ để hoàn tất offset của owner cũ.
- onPartitionsLost không phải nơi gọi ack cho các record còn tồn đọng.
- Nếu container dùng Kafka transactions, offset và output giao dịch có semantics riêng; callback lost vẫn không thể cấp lại ownership.
- Manual ack không tự biến business side effect thành exactly-once.

Ví dụ đang dùng phương thức có Acknowledgment phải có container AckMode tương ứng; nếu factory đang dùng RECORD mà listener yêu cầu manual acknowledgment, cần chỉnh cấu hình phù hợp.

## 15. Transaction Kafka, producer fencing và lost partitions

Khi listener container quản lý Kafka transaction cho consume-process-produce, output Kafka và offset nguồn có thể được commit cùng transaction.

Nếu consumer mất assignment trong lúc xử lý, những rủi ro có thể xuất hiện:

- Transaction đang chạy không còn phù hợp với group generation hiện tại.
- Offset gửi vào transaction có thể bị từ chối do metadata/fencing.
- Container cần abort hoặc xử lý transaction failure.
- Record đầu vào có thể được đọc lại bởi owner mới.
- Task side effect ngoài Kafka từ owner cũ vẫn có thể đang chạy.

Kafka transactions và EOS v2 giúp bảo vệ tính nhất quán trong phạm vi Kafka, nhưng không biến lost callback thành nơi có thể tiếp tục publish/commit thay cho owner mới.

Trong onPartitionsLost, tránh tự tạo một “transaction sửa sai” để commit offset của partition đã bị mất. Nếu có DLT/recovery, phải thực hiện theo lifecycle và quyền sở hữu hợp lệ của container/recoverer.

Đối với database hay HTTP call đã chạy trước rollback Kafka, cần tiếp tục dùng idempotency key, inbox hoặc fencing token. Abort Kafka transaction không tự đảo ngược side effect ngoài Kafka.

## 16. Pause, stop và rebalance khác lost thế nào?

Một partition bị pause không có nghĩa consumer mất quyền sở hữu nó. Pausing thường chỉ tạm dừng việc lấy thêm record, trong khi assignment vẫn thuộc consumer.

Một listener container bị stop có thể rời group theo cơ chế graceful shutdown. Trong trường hợp bình thường, callback revoked hoặc bước cleanup tương ứng có thể xảy ra trước khi assignment được giao lại.

So sánh:

| Sự kiện | Partition còn thuộc consumer? | Có nên tiếp tục xử lý? |
|---|---|---|
| pause() | Về logic vẫn thuộc consumer | Phụ thuộc chính sách pause, task hiện tại |
| resume() | Consumer vẫn có assignment hợp lệ | Có thể poll tiếp |
| onPartitionsRevoked | Đang nhường ownership | Kết thúc/flush theo contract |
| onPartitionsLost | **Đã mất ownership** | Dừng/invalid task cũ ngay |
| Container stop | Đang dừng lifecycle consumer | Drain/cleanup theo shutdown policy |
| JVM crash | Không có callback bảo đảm chạy | Hệ thống khác phải phục hồi qua lease/replay |

Không dùng một biến paused để suy ra partition đã lost. Ngược lại, không dùng lost callback để quyết định pause; lost là sự kiện sau khi ownership không còn.

## 17. onPartitionsLost và cooperative rebalance

Kafka có các assignment strategy khác nhau, trong đó cooperative rebalance hướng tới giảm việc thu hồi hàng loạt partition khi group thay đổi.

Trong eager rebalance, consumer thường revoke assignment lớn trước khi phân công lại. Trong cooperative rebalance, consumer có thể giữ những partition không cần chuyển và chỉ revoke phần cần thay đổi.

Điều này làm giảm gián đoạn, nhưng không loại bỏ mọi trường hợp lost:

- Consumer vẫn có thể mất membership vì không poll kịp.
- Network partition vẫn có thể gây timeout.
- Coordinator/member generation vẫn có thể thay đổi ngoài dự kiến.
- Một consumer từng sở hữu partition có thể nhận ra quyền sở hữu đã mất.

Không được xây logic rằng cooperative assignment bảo đảm onPartitionsLost sẽ không bao giờ xảy ra. Tương tự, không suy luận mọi lần rebalance trong cooperative mode đều có onPartitionsRevoked với toàn bộ partition.

Đội vận hành nên kiểm tra assignment strategy thực tế mà Kafka clients đang dùng và các giao diện callback được hỗ trợ trong phiên bản thư viện đang chạy.

## 18. Static membership có loại bỏ lost không?

Kafka hỗ trợ static membership qua group.instance.id nhằm giảm rebalance không cần thiết khi instance restart ngắn hoặc tạm thời mất liên lạc. Tuy nhiên, static membership không biến ownership thành vĩnh viễn.

Nếu một instance ngừng heartbeat đủ lâu, broker vẫn có thể phân phối lại partition. Với một số đường xử lý vượt max.poll.interval.ms, thành viên static có thể ngừng heartbeat rồi bị reassigned khi session timeout; chi tiết phụ thuộc Kafka client/version và cấu hình timeout.

Vì vậy:

- Static membership có thể làm assignment ổn định hơn trong một số tình huống.
- Nó không thay thế graceful shutdown và timeout hợp lý.
- Nó không thay thế cơ chế idempotency/fencing.
- Nó không bảo đảm onPartitionsLost sẽ luôn được gọi trước khi partition chuyển owner.

Không dùng group.instance.id trùng giữa hai instance đang chạy; điều đó gây fencing/membership conflicts.

## 19. Long-running listener và max.poll.interval.ms

Giả sử listener nhận một record rồi gọi một API có timeout 10 phút, trong khi max.poll.interval.ms là 5 phút. Consumer có thể bị xem là không poll đủ thường xuyên, dẫn đến thay đổi group membership.

    poll() nhận record
           |
           v
    listener gọi API 10 phút
           |
           +---- max.poll.interval.ms vượt giới hạn
           |
           +---- coordinator có thể chuyển assignment
           |
           v
    listener trả về và consumer tiếp tục poll
           |
           v
    Kafka client phát hiện ownership đã thay đổi

Dù onPartitionsLost xuất hiện, nó không thể ngăn API đã chạy xong. Nếu API thực hiện side effect trước khi consumer nhận ra mình lost, consumer mới có thể xử lý cùng record.

Giảm rủi ro bằng:

1. Đặt timeout cho dependency.
2. Giảm max.poll.records để giới hạn thời gian xử lý mỗi poll.
3. Đo processing duration p95/p99.
4. Cân nhắc tăng max.poll.interval.ms khi có cơ sở, không chỉ che lỗi.
5. Tránh block vô hạn ở DB/network.
6. Thiết kế idempotent side effect.
7. Nếu offload async, quản lý completion và partition ownership đúng cách.

Tăng max.poll.interval.ms quá cao có thể làm phục hồi chậm khi consumer thật sự bị treo. Cần cân bằng tốc độ phát hiện lỗi và thời gian xử lý thực tế.

## 20. Những lỗi khi cleanup ở callback

### 20.1. Block poll thread quá lâu

~~~java
@Override
public void onPartitionsLost(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    executor.awaitTermination(10, TimeUnit.MINUTES);
}
~~~

Đây là **phản ví dụ**: callback chờ lâu khiến consumer khó hoàn tất rebalance và tham gia group trở lại. Hãy phát tín hiệu cancel/invalid nhanh, sau đó tổ chức cleanup có giới hạn ở nơi khác nếu thật sự cần.

### 20.2. Release distributed lock vô điều kiện

Nếu lock đã hết hạn và consumer mới nhận lock cùng key, owner cũ gọi release(key) có thể vô tình xóa quyền của consumer mới. Giải pháp là release theo token hoặc compare-and-delete.

### 20.3. Dùng ThreadLocal đơn giản cho mọi state

ThreadLocal gắn với thread, không đủ biểu diễn vòng đời assignment khi consumer callback và task async chạy trên các thread khác nhau. State nên gắn với (consumer owner, topic, partition, assignment token), không chỉ thread ID.

### 20.4. Commit offset trong lost callback

Dù commitSync đôi khi ném exception dễ thấy, cũng không nên dùng try/catch để bỏ qua rồi tiếp tục như đã hoàn tất. Đó là thiết kế sai về ownership và có thể che giấu replay/duplicate.

### 20.5. Chỉ dọn state ở onPartitionsRevoked

Nếu chỉ có logic revoked, tình huống lost ownership không qua revocation bình thường có thể khiến state cũ tồn tại. Override lost tường minh và có đường invalid riêng.

### 20.6. Dùng callback làm nơi xử lý lại record

onPartitionsLost không có hợp đồng để chạy lại record. Đừng tự gọi listener, tạo DLT hoặc seek vào partition ở callback; recovery thuộc về consumer hợp lệ và container error/recovery infrastructure.

## 21. Thiết kế PartitionLifecycleService cho production

Một service theo dõi assignment thường có các thành phần:

    Kafka callback
         |
         v
    PartitionLifecycleService
         |
         +--- map owner token theo topic-partition
         |
         +--- cancel/invalidate local processing
         |
         +--- release owner-scoped resource
         |
         +--- metric: assigned / revoked / lost
         |
         +--- structured log: groupId, clientId, partitions
         |
         v
    Consumer mới xử lý từ committed offset

Các quy tắc:

- Mỗi assignment sinh một token riêng.
- Token được đưa cùng task để kiểm tra ownership.
- Cleanup phải nhận token cũ, không chỉ partition name.
- Nếu task ghi external store, store phải hỗ trợ idempotency hoặc fencing đủ mạnh.
- Không coi callback lost là điều kiện duy nhất để hết hạn token; cần timeout/lease TTL hoặc cơ chế phát hiện owner không còn sống.
- Có giới hạn thời gian và kích thước queue của cleanup.
- Nếu không thể cleanup đồng bộ an toàn, có thể đưa tác vụ cleanup idempotent vào queue nội bộ, nhưng queue không được giữ độc quyền partition vô thời hạn.
- Callback nhận partition collection có thể rỗng trong một số chuỗi rebalance; code cần chịu được tập rỗng.

Sự kiện lost là một **tín hiệu local**, không phải một thông điệp consensus gửi tới mọi consumer khác. Các ràng buộc xuyên instance phải được bảo vệ tại hệ thống điều phối hoặc nơi ghi side effect.

## 22. Quan sát lost partitions bằng metrics

Không chỉ theo dõi tổng số lần rebalance. Một group có thể rebalance vì rollout định kỳ mà không có vấn đề, hoặc có lost ownership thường xuyên do listener bị kẹt.

Các metric gợi ý:

| Metric | Ý nghĩa | Cách diễn giải |
|---|---|---|
| partitions_lost_total | Số partition trong các lần lost callback | Tăng liên tục là tín hiệu cần điều tra |
| partitions_revoked_total | Số partition được revoke bình thường | Có thể tăng khi scale/rollout |
| partitions_assigned_total | Số partition được assign | Giúp quan sát biến động ownership |
| rebalance_duration | Thời gian group đổi assignment | Cao có thể ảnh hưởng throughput |
| records_processed_duplicate_total | Duplicate phát hiện bằng eventId | Đo tác động thực tế của redelivery |
| consumer_lag | Backlog theo group/topic/partition | Có thể tăng khi rebalances dày |
| listener_processing_duration | Thời gian xử lý p95/p99 | So với max.poll.interval.ms |
| commit_failure_total | Lỗi commit offset | Có thể liên quan generation/ownership |
| in_flight_tasks | Task còn chạy khi partition lost | Phát hiện async work không được fence |

Nếu dùng Micrometer, hạn chế gắn eventId, offset hoặc UUID làm label vì gây high cardinality. Có thể gắn consumer group, topic, clientId và reason category đã chuẩn hóa.

Log ví dụ:

    level=WARN
    event=consumer_partition_lost
    group=order-processors
    client=orders-2
    partitions=orders.events-2,orders.events-3
    inflight=4

Thông tin reason thực tế có thể không được callback cung cấp trực tiếp. Không tự gắn nhãn cause=timeout nếu chỉ biết sự kiện lost; cần đối chiếu log Kafka client, network và processing duration.

## 23. Quy trình điều tra khi onPartitionsLost tăng

Khi metric lost tăng đột biến:

1. **Kiểm tra sự kiện trước đó:** rolling deployment, scale, broker outage hay network interruption?
2. **Kiểm tra consumer group:** số member, assignment, rebalance count và duration.
3. **Kiểm tra poll:** listener có xử lý lâu hơn max.poll.interval.ms không?
4. **Kiểm tra dependency:** database/API có tăng latency, lock hoặc timeout không?
5. **Kiểm tra JVM:** GC pause, CPU throttling, thread starvation hoặc out-of-memory.
6. **Kiểm tra network:** kết nối broker/coordinator, DNS và packet loss.
7. **Kiểm tra callback:** cleanup có block poll thread hoặc ném exception không?
8. **Kiểm tra offsets:** commit failure, redelivery và lag sau rebalance.
9. **Kiểm tra side effect:** duplicate, out-of-order update, stale owner write.
10. **Khắc phục có đo lường:** timeout, max.poll.records, concurrency, lease/fencing, graceful shutdown.

Không chỉ tăng max.poll.interval.ms mà bỏ qua nguyên nhân. Nếu nguyên nhân là DB đang chậm do overload, tăng timeout có thể làm consumer chậm phục hồi hơn; cần xử lý dependency, giới hạn concurrency hoặc thay đổi mô hình work.

## 24. Kiểm thử onPartitionsLost

Unit test có thể kiểm tra logic callback gọi lifecycleService.onLost(partitions), nhưng không đủ chứng minh consumer thực sự mất ownership. Cần integration test hoặc thử nghiệm nhóm consumer có kiểm soát.

### 24.1. Unit test callback

~~~java
@Test
void lostInvalidatesOwnerScopedWork() {
    TopicPartition partition = new TopicPartition("orders.events", 0);

    lifecycleService.onAssigned(List.of(partition));
    lifecycleService.onLost(List.of(partition));

    assertThat(lifecycleService.lostPartitionsTotal()).isEqualTo(1);
}
~~~

Đây là mẫu test phần service minh họa; khi ứng dụng có owner tokens, test nên kiểm tra token của assignment cũ bị invalid và assignment mới không bị ảnh hưởng.

### 24.2. Mô phỏng rebalance bình thường

1. Khởi tạo topic nhiều partition và hai consumer cùng group.
2. Quan sát onPartitionsAssigned.
3. Thêm consumer thứ ba hoặc scale instance.
4. Ghi nhận onPartitionsRevoked và assignment mới.
5. Xác nhận callback lost **không bị giả định là bắt buộc** cho một lần rebalance có kiểm soát.

### 24.3. Mô phỏng mất ownership

1. Cho consumer xử lý một record chậm hoặc tạo tình huống làm consumer mất membership.
2. Để coordinator phân phối partition cho consumer còn lại.
3. Cho consumer cũ tiếp tục poll/rejoin nếu còn sống.
4. Quan sát onPartitionsLost khi Kafka client phát hiện trạng thái lost theo cơ chế của phiên bản đang dùng.
5. Xác nhận consumer cũ không cố commit offset hoặc xử lý side effect khi ownership đã mất.
6. Xác nhận consumer mới xử lý từ committed offset hợp lệ.

Thực tế, onPartitionsLost không được bảo đảm xuất hiện trong mọi cách gây lỗi. Test nên ghi nhận group assignment và callback theo từng phiên bản Kafka client, tránh viết assertion bắt buộc lost cho mọi lần restart/crash.

### 24.4. Test async task cũ

1. Consumer A nhận partition và tạo một task nền cố ý chờ.
2. Chuyển partition sang consumer B.
3. Invalidate token của A.
4. Để task cũ của A tiếp tục tới bước ghi DB.
5. Xác nhận fencing/idempotency chặn stale write.
6. Xác nhận task mới của B vẫn có thể ghi bình thường.

### 24.5. Test crash không có callback

1. Consumer A nhận partition và tạo một lease bên ngoài.
2. Kill process A trước khi callback cleanup có thể chạy.
3. Xác nhận lease hết hạn hoặc coordinator/owner mới có thể lấy quyền theo chính sách.
4. Xác nhận record chưa commit được redeliver.
5. Xác nhận hệ thống không cần onPartitionsLost của A để phục hồi.

Test crash rất quan trọng: callback không thay thế distributed fault tolerance.

## 25. Checklist trước khi triển khai

- Có phân biệt đúng onPartitionsRevoked và onPartitionsLost hay chưa?
- Có override lost riêng thay vì vô tình dùng logic revoked commit offset?
- Callback có được đăng ký vào đúng ConcurrentKafkaListenerContainerFactory?
- Có nhiều child consumers/concurrency cần đồng bộ state không?
- Cleanup có nhanh, bounded và không block consumer poll thread?
- Có ngừng hoặc invalidate async work thuộc owner cũ?
- Có owner token để không xóa state/lock của assignment mới?
- External DB/API có idempotency, optimistic concurrency hoặc fencing đủ mạnh?
- Có tránh commit offset và late ack sau khi partition đã mất?
- Đã đo max.poll.interval.ms, processing duration và rebalance duration?
- Có metric lost, revoked, assigned, commit failure và duplicate?
- Có test clean rebalance, lost membership, restart/crash và stale worker?
- Có kiểm tra phiên bản Kafka client/Spring Kafka và callback contract cụ thể?

## 26. Kết luận

**onPartitionsLost không phải lời nhắc để commit offset lần cuối.** Nó là tín hiệu rằng consumer cũ đã mất quyền sở hữu partition và phải ngừng hành xử như một owner hợp lệ. Trong Spring Kafka, ConsumerAwareRebalanceListener cho phép ứng dụng tiếp nhận tín hiệu này, dọn trạng thái cục bộ, vô hiệu hóa công việc cũ và quan sát các sự cố membership.

Độ tin cậy không dừng ở callback: để tránh duplicate và stale write khi partition chuyển chủ, ứng dụng cần phối hợp committed offset an toàn, idempotent side effect, owner fencing và cơ chế phục hồi ngay cả khi process chết trước khi bất kỳ callback nào chạy.
