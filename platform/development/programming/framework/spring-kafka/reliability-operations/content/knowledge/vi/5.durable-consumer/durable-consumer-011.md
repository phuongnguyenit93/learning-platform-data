# ConsumerRebalanceListener

Trong một consumer group của Kafka, quyền đọc partition được phân phối giữa các consumer đang hoạt động. Khi thành viên group hoặc tập partition thay đổi, Kafka thực hiện **rebalance** để xác định consumer nào sở hữu partition nào. Trong thời gian này, một consumer có thể mất một số partition, nhận partition mới hoặc mất quyền sở hữu partition đột ngột.

**ConsumerRebalanceListener** là callback cho phép ứng dụng phản ứng với các thay đổi quyền sở hữu đó. Trong Spring Kafka, listener này hữu ích khi consumer cần giải phóng trạng thái theo partition, lưu checkpoint, khởi tạo tài nguyên cho partition mới hoặc ghi nhận tình huống partition đã bị mất. Nếu triển khai không đúng, ứng dụng có thể commit sai offset, giữ tài nguyên quá lâu, xử lý trùng hoặc làm rebalance kéo dài.

## 1. Rebalance là gì và vì sao ứng dụng cần biết?

Kafka consumer group cho phép nhiều consumer cùng chia sẻ việc đọc các partition của một topic. Group coordinator theo dõi thành viên và phối hợp quá trình phân công partition. Khi group cần thay đổi assignment, các consumer tham gia một chu kỳ rebalance.

Một số nguyên nhân thường gặp:

- Một consumer mới tham gia group hoặc một consumer rời group.
- Consumer bị dừng, crash, mất kết nối hoặc không gửi heartbeat đúng hạn.
- Consumer vượt quá thời gian cho phép giữa các lần poll.
- Số partition của topic thay đổi.
- Subscription của consumer thay đổi.
- Một consumer được khởi động lại sau khi triển khai phiên bản mới.
- Assignment strategy hoặc cấu hình group thay đổi.

Ví dụ group có topic gồm sáu partition và ba consumer. Mỗi consumer có thể được giao hai partition. Khi một consumer dừng, Kafka phải phân phối lại partition của nó cho các consumer còn lại. Khi consumer quay lại, group có thể thực hiện một lần rebalance khác để cân bằng assignment.

~~~mermaid
flowchart TD
    A["Consumer group ổn định"] --> B["Membership hoặc partition thay đổi"]
    B --> C["Kafka bắt đầu rebalance"]
    C --> D["Consumer cũ nhận callback revoke/lost"]
    D --> E["Group hoàn tất assignment mới"]
    E --> F["Consumer nhận callback assigned"]
    F --> G["Tiếp tục poll và xử lý record"]
~~~

Ứng dụng cần biết thời điểm này vì trạng thái xử lý thường gắn với partition. Ví dụ, consumer có thể giữ bộ đếm, cache, state store hoặc khóa tài nguyên theo partition. Khi partition được chuyển sang consumer khác, consumer cũ phải xử lý trạng thái của nó và consumer mới phải khởi tạo trạng thái tương ứng.

## 2. ConsumerRebalanceListener cung cấp những callback nào?

Kafka cung cấp interface **org.apache.kafka.clients.consumer.ConsumerRebalanceListener** với ba callback chính:

| Callback | Thời điểm | Việc ứng dụng thường làm |
|---|---|---|
| **onPartitionsRevoked(partitions)** | Trước khi các partition trong danh sách bị thu hồi trong một lần rebalance bình thường | Hoàn tất công việc có thể hoàn tất an toàn, lưu trạng thái và giải phóng tài nguyên |
| **onPartitionsAssigned(partitions)** | Sau khi consumer được giao các partition mới | Khởi tạo state theo partition, nạp checkpoint hoặc seek nếu có chính sách offset riêng |
| **onPartitionsLost(partitions)** | Khi consumer đã mất quyền sở hữu các partition được liệt kê | Đánh dấu ownership đã mất và dọn trạng thái cục bộ; không giả định còn có thể commit |

Callback **onPartitionsLost** có trên các phiên bản Kafka client hỗ trợ callback này. Khi biên dịch với Kafka client cũ, interface có thể chưa cung cấp method đó. Hãy kiểm tra phiên bản **kafka-clients** mà ứng dụng Spring Kafka thực sự sử dụng.

### 2.1 onPartitionsRevoked

Callback này báo rằng các partition được liệt kê sắp rời khỏi assignment hiện tại của consumer. Với rebalance bình thường, đây là cơ hội cuối cùng để consumer xử lý các công việc liên quan đến những partition đó trước khi quyền sở hữu được chuyển giao.

Các thao tác thường phù hợp:

- Flush state hoặc dữ liệu đệm gắn với các partition sắp bị thu hồi.
- Lưu checkpoint đã được xử lý hoàn tất.
- Đóng tài nguyên cục bộ hoặc giải phóng khóa mà ứng dụng quản lý.
- Ghi metric và log về assignment cũ.
- Hoàn tất commit offset theo chính sách của ứng dụng nếu ứng dụng tự quản lý commit.

Không nên giả định mọi partition đang được consumer sở hữu đều có trong danh sách callback. Với cooperative rebalancing, callback có thể chỉ chứa tập partition thực sự bị thu hồi; consumer có thể tiếp tục sở hữu các partition còn lại.

### 2.2 onPartitionsAssigned

Callback này được gọi sau khi consumer nhận assignment mới. Danh sách truyền vào chứa các partition vừa được giao cho consumer trong chu kỳ đó.

Ứng dụng có thể:

- Tạo state hoặc tài nguyên riêng cho partition.
- Khôi phục cache hoặc state store theo partition.
- Nạp checkpoint do ứng dụng quản lý.
- Dùng **consumer.seek(partition, offset)** nếu có chính sách đọc từ vị trí riêng.
- Ghi nhận assignment mới để quan sát phân bố tải.

Đối với offset, hãy phân biệt committed offset do Kafka quản lý với checkpoint riêng trong database hoặc hệ thống state store. Nếu ứng dụng chủ động seek từ checkpoint riêng, cần xác định rõ checkpoint nào là nguồn sự thật và bảo đảm checkpoint chỉ phản ánh record đã xử lý an toàn.

### 2.3 onPartitionsLost

Callback này thể hiện tình huống consumer đã mất quyền sở hữu partition. Ví dụ, consumer có thể bị mất kết nối đủ lâu hoặc group đã chuyển assignment sang thành viên khác trước khi consumer cũ kịp hoàn tất quy trình revoke bình thường.

Khi partition đã lost, consumer không nên giả định mình vẫn có quyền commit offset. Consumer khác có thể đã tiếp quản partition. Hãy dùng callback này để:

- Đánh dấu ownership của partition đã mất.
- Dừng hoặc vô hiệu hóa các thao tác ghi state gắn với ownership cũ.
- Đóng tài nguyên cục bộ có thể đóng an toàn.
- Ghi log/metric để phân biệt partition lost với revoke bình thường.
- Dựa vào idempotency và fencing để ngăn tác động trùng từ consumer cũ.

Nếu hệ thống ghi state vào kho dùng chung, chỉ dọn tài nguyên cục bộ là chưa đủ. Cần cơ chế fencing, lease hoặc token ownership để consumer cũ không tiếp tục ghi sau khi partition đã được giao cho consumer mới.

## 3. Phân biệt revoke, assigned và lost

Ba callback có ý nghĩa khác nhau về quyền sở hữu và thời điểm xử lý.

| Tình huống | Quyền sở hữu của consumer | Cách phản ứng |
|---|---|---|
| Partition sắp bị revoke trong rebalance bình thường | Consumer vẫn đang ở giai đoạn bàn giao và có cơ hội cleanup | Flush trạng thái cần thiết, hoàn tất công việc an toàn và giải phóng tài nguyên |
| Partition vừa được assign | Consumer đã nhận assignment mới | Khởi tạo state, khôi phục checkpoint và bắt đầu xử lý |
| Partition đã lost | Consumer không còn có thể dựa vào quyền sở hữu cũ | Không commit dựa trên ownership cũ; fence thao tác và dọn trạng thái cục bộ |

Không nên dùng **onPartitionsRevoked** như một callback chung cho mọi tình huống mất partition. Khi Kafka thông báo partition lost, quy trình revoke bình thường có thể đã không diễn ra như mong đợi. Việc phân biệt hai trường hợp giúp tránh commit hoặc ghi state bằng một consumer đã mất quyền sở hữu.

## 4. Eager và cooperative rebalancing ảnh hưởng callback ra sao?

### Eager rebalancing

Với eager assignment strategy, group thường thu hồi toàn bộ assignment hiện tại trước khi phân phối assignment mới. Trong giai đoạn này, consumer có thể phải tạm dừng xử lý tất cả partition, kể cả partition cuối cùng vẫn được giao cho chính consumer đó sau rebalance.

Hệ quả là một thay đổi membership nhỏ có thể làm nhiều partition bị thu hồi và giao lại. Callback revoke cần xử lý tập partition được truyền vào, không nên giả định chỉ một partition thay đổi.

### Cooperative rebalancing

Cooperative rebalancing cho phép chuyển partition theo từng phần. Consumer chỉ thu hồi những partition cần chuyển; các partition còn lại có thể tiếp tục được giữ. Assignment strategy phổ biến cho cách tiếp cận này là **CooperativeStickyAssignor**.

Với cooperative rebalancing:

- **onPartitionsRevoked** có thể chỉ nhận một phần assignment hiện tại.
- Consumer có thể tiếp tục xử lý các partition không bị thu hồi.
- **onPartitionsAssigned** báo các partition mới được giao trong chu kỳ.
- Cleanup phải giới hạn đúng tập partition trong callback.

Không được xóa toàn bộ state của consumer khi chỉ một phần partition bị revoke. Hãy quản lý state theo **TopicPartition** và chỉ thay đổi các mục có trong danh sách callback.

## 5. Callback chạy trên luồng nào?

Các callback rebalance được gọi trong quá trình consumer xử lý poll và điều phối group, thường trên chính luồng thực hiện các thao tác consumer. Điều này có một số hệ quả vận hành:

- Callback nên chạy nhanh để không kéo dài rebalance.
- Không thực hiện truy vấn database chậm, gọi HTTP hoặc chờ dịch vụ bên ngoài trong callback nếu có thể tránh.
- Không gọi **poll()** lồng bên trong callback.
- Kafka consumer không thread-safe; không chia sẻ consumer object cho thread khác để gọi API tùy ý.
- Không thực hiện xử lý nghiệp vụ dài trong callback.
- Nếu phải flush dữ liệu, đặt timeout rõ ràng và giới hạn lượng dữ liệu cần flush.

Callback kéo dài có thể làm consumer không poll kịp, khiến group tiếp tục rebalance hoặc vượt **max.poll.interval.ms**. Nếu cleanup cần công việc nặng, hãy thiết kế state để có thể checkpoint theo chu kỳ trong lúc xử lý record, nhờ đó callback chỉ cần hoàn tất phần nhỏ còn lại.

Với Spring Kafka concurrency lớn hơn một, container có nhiều consumer con. Callback được thực hiện theo từng consumer và assignment riêng. Trạng thái dùng chung giữa các callback cần có cơ chế đồng bộ phù hợp; không giả định callback của mọi consumer sẽ chạy tuần tự trên cùng một luồng.

## 6. Đăng ký listener trực tiếp với Kafka Consumer

Ở Kafka client thuần, ứng dụng đăng ký **ConsumerRebalanceListener** khi subscribe topic:

~~~java
import java.util.Collection;
import java.util.List;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import org.apache.kafka.common.TopicPartition;

public class OrderRebalanceListener
        implements ConsumerRebalanceListener {

    @Override
    public void onPartitionsRevoked(
            Collection<TopicPartition> partitions) {

        // Lưu trạng thái đã hoàn tất và giải phóng tài nguyên
        // thuộc các partition sắp bị thu hồi.
        stateStore.flush(partitions);
        stateStore.release(partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Collection<TopicPartition> partitions) {

        // Khởi tạo state cho các partition mới được giao.
        stateStore.initialize(partitions);
    }

    @Override
    public void onPartitionsLost(
            Collection<TopicPartition> partitions) {

        // Ownership đã mất: không commit dựa trên assignment cũ.
        stateStore.markOwnershipLost(partitions);
    }
}
~~~

Đăng ký listener:

~~~java
consumer.subscribe(
        List.of("orders.created"),
        new OrderRebalanceListener()
);
~~~

Ví dụ tập trung vào lifecycle của state. **stateStore** là thành phần do ứng dụng xây dựng; Kafka không tự cung cấp các phương thức flush, release hoặc initialize này.

Trong callback của interface Kafka thuần, listener chỉ nhận danh sách partition. Nếu cần thao tác consumer như seek, ứng dụng có thể dùng callback mở rộng của Spring Kafka hoặc một thiết kế phù hợp với API consumer đang chạy. Không giữ consumer ở một field để gọi từ thread khác.

## 7. Tích hợp ConsumerRebalanceListener trong Spring Kafka

Spring Kafka cho phép gắn listener vào **ContainerProperties** của listener container. Vì container quản lý consumer, cách này giúp đăng ký callback tập trung cùng cấu hình listener factory.

Có hai lựa chọn:

- Dùng **ConsumerRebalanceListener** của Kafka khi chỉ cần danh sách partition.
- Dùng **ConsumerAwareRebalanceListener** của Spring Kafka khi cần nhận thêm **Consumer** trong callback, ví dụ để gọi **seek()** hoặc truy vấn vị trí consumer theo partition.

**ConsumerAwareRebalanceListener** mở rộng listener của Kafka và cung cấp các callback bổ sung để phối hợp với thứ tự commit offset do container quản lý.

### 7.1 Cấu hình listener factory

Ví dụ dưới đây dùng Spring Kafka 3.x và **ConsumerAwareRebalanceListener**:

~~~java
import java.util.Collection;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        PartitionStateStore partitionStateStore) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties()
            .setConsumerRebalanceListener(
                    new ConsumerAwareRebalanceListener() {

        @Override
        public void onPartitionsRevokedBeforeCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            // Flush state trước bước container commit offset đang chờ.
            partitionStateStore.flush(partitions);
        }

        @Override
        public void onPartitionsRevokedAfterCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            // Hoàn tất cleanup sau bước commit của container.
            partitionStateStore.release(partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            partitionStateStore.initialize(partitions);
        }

        @Override
        public void onPartitionsLost(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            // Không giả định còn quyền commit các partition này.
            partitionStateStore.markOwnershipLost(partitions);
        }
    });

    return factory;
}
~~~

Tên và chữ ký callback cần khớp với phiên bản Spring Kafka và Kafka client đang dùng. Nếu client cũ chưa có **onPartitionsLost**, bỏ override đó hoặc nâng phiên bản dependency theo kế hoạch tương thích của ứng dụng.

**onPartitionsRevokedBeforeCommit** và **onPartitionsRevokedAfterCommit** là phần mở rộng của Spring Kafka. Chúng giúp đặt thao tác cleanup trước và sau bước container xử lý các offset đang chờ commit. Điều này đặc biệt hữu ích khi ứng dụng cần flush state trước commit và giải phóng tài nguyên sau giai đoạn commit.

Không nên tự gọi commit thêm trong callback chỉ vì có quyền truy cập **Consumer**. Listener container đã quản lý offset theo acknowledgement mode và cấu hình commit. Nếu ứng dụng tự quản lý commit, phải xác định rõ một nơi duy nhất chịu trách nhiệm và hiểu hệ quả của việc commit đồng bộ trong callback.

### 7.2 Gắn factory vào @KafkaListener

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void onOrderCreated(OrderCreated event) {
        orderProjection.apply(event);
    }
}
~~~

Container sử dụng factory đã cấu hình, vì vậy consumer của listener sẽ đăng ký rebalance listener tương ứng. Nếu một ứng dụng có nhiều listener factory, hãy cấu hình callback cho đúng factory; không giả định mọi **@KafkaListener** đều dùng cùng một rebalance listener.

### 7.3 ConsumerAwareRebalanceListener cung cấp Consumer để làm gì?

Trong callback **onPartitionsAssigned**, tham số **Consumer** có thể dùng để thao tác trên consumer đang xử lý callback. Một tình huống là seek từ checkpoint riêng:

~~~java
@Override
public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    for (TopicPartition partition : partitions) {
        Long nextOffset = checkpointStore.loadNextOffset(partition);

        if (nextOffset != null && nextOffset >= 0) {
            consumer.seek(partition, nextOffset);
        }
    }
}
~~~

Đây chỉ là ví dụ cho hệ thống có checkpoint store do ứng dụng quản lý. Trước khi sử dụng, cần xác định:

- Checkpoint lưu offset tiếp theo cần đọc hay offset của record cuối cùng đã xử lý.
- Checkpoint được cập nhật sau khi side effect nghiệp vụ đã commit hay chưa.
- Hành vi khi không có checkpoint.
- Quan hệ giữa checkpoint riêng và committed offset trong Kafka.
- Cách xử lý khi seek tới offset đã hết hạn do retention hoặc không còn tồn tại.

Nếu checkpoint riêng và committed offset không nhất quán, ứng dụng có thể bỏ qua record chưa xử lý hoặc đọc lại nhiều record. Với nhiều trường hợp, để Kafka quản lý committed offset theo container là đủ; chỉ dùng seek khi có yêu cầu nghiệp vụ rõ ràng.

## 8. Phối hợp rebalance callback với offset commit trong Spring Kafka

Spring Kafka có các acknowledgement mode điều khiển cách container ghi nhận tiến độ xử lý. Những mode phổ biến gồm:

| Ack mode | Cách hoạt động khái quát |
|---|---|
| **RECORD** | Commit offset sau khi từng record được listener xử lý thành công |
| **BATCH** | Commit offset sau khi các record trong lần poll được xử lý thành công |
| **MANUAL** | Listener chủ động acknowledge; container quản lý commit theo semantics của mode |
| **MANUAL_IMMEDIATE** | Commit ngay khi acknowledge trên consumer thread; hành vi còn phụ thuộc thread gọi acknowledge |

Tên và hành vi chi tiết cần đối chiếu với phiên bản Spring Kafka. Dù dùng mode nào, cần xác định mốc nào thể hiện record đã được xử lý an toàn.

Một luồng điển hình khi partition bị revoke bình thường:

1. Container nhận biết rebalance và chuẩn bị xử lý assignment cũ.
2. Callback trước commit của Spring Kafka được gọi nếu dùng **ConsumerAwareRebalanceListener**.
3. Container xử lý các offset đang chờ commit theo cấu hình.
4. Callback sau commit được gọi.
5. Consumer hoàn tất việc bàn giao partition theo giao thức rebalance.

Thứ tự chi tiết giữa các callback và commit phụ thuộc API, phiên bản và loại listener. Hãy dựa vào callback Spring cung cấp cho mục đích trước/sau commit thay vì tự suy đoán thứ tự bằng cách đặt logic vào một callback chung.

### Offset commit không thay thế checkpoint nghiệp vụ

Offset Kafka biểu diễn vị trí consumer group đã xác nhận trong partition. Nó không tự chứng minh database transaction, HTTP request hoặc side effect ngoài Kafka đã hoàn tất.

Ví dụ consumer cập nhật database rồi process dừng trước khi commit offset. Record có thể được giao lại sau rebalance. Đây là hành vi at-least-once thường gặp. Consumer cần idempotency hoặc một cơ chế inbox để lần giao lại không nhân đôi side effect.

Ngược lại, nếu ứng dụng commit offset trước khi side effect bền vững, record có thể bị bỏ qua sau khi process dừng. Vì vậy callback revoke không thể sửa một thứ tự xử lý sai trong listener; nó chỉ giúp hoàn tất phần bàn giao partition.

## 9. Quản lý state theo partition

Một ứng dụng có state theo partition nên lưu trạng thái dưới dạng map hoặc registry với key là **TopicPartition**, thay vì một biến state chung cho toàn bộ consumer.

Ví dụ mô hình:

~~~java
Map<TopicPartition, PartitionState> states;
~~~

Khi partition được assign, ứng dụng tạo hoặc khôi phục **PartitionState**. Khi revoke, ứng dụng flush và release đúng các partition trong callback. Khi lost, ứng dụng đánh dấu ownership đã mất và vô hiệu hóa các thao tác ghi từ owner cũ.

Các quy tắc nên áp dụng:

- Mọi thao tác flush, release và initialize phải có thể nhận một tập partition cụ thể.
- Cleanup phải idempotent vì callback hoặc quá trình shutdown có thể khiến ứng dụng phải dọn state ở nhiều đường lifecycle.
- Không xóa state của partition vẫn còn được giao trong cooperative rebalance.
- Nếu state được chia sẻ giữa nhiều instance, dùng fencing token, lease hoặc cơ chế ownership để tránh consumer cũ ghi đè dữ liệu của consumer mới.
- Nếu state có thể khôi phục từ Kafka hoặc database, lưu đủ metadata để phát hiện checkpoint cũ hoặc không còn hợp lệ.

Đối với state store lớn, hãy cập nhật state theo chu kỳ trong lúc xử lý record. Callback revoke chỉ nên flush phần thay đổi cuối cùng còn lại thay vì phải ghi toàn bộ state lớn trong một lần.

## 10. Những lỗi thường gặp khi triển khai callback

### Thực hiện công việc chậm trong callback

Gọi API bên ngoài hoặc chờ database trong callback có thể kéo dài rebalance. Giải pháp là checkpoint định kỳ, giới hạn công việc còn lại trong callback và đặt timeout cho cleanup.

### Xóa toàn bộ state khi một partition bị revoke

Với cooperative rebalancing, consumer có thể chỉ mất một phần assignment. Chỉ cleanup các partition được truyền vào callback.

### Commit offset sau khi partition đã lost

Khi callback lost được gọi, consumer không còn quyền sở hữu an toàn. Không cố commit dựa trên assignment cũ. Dựa vào consumer mới và idempotency để xử lý lại phần chưa được xác nhận.

### Gọi commit thủ công trùng với container

Spring Kafka container có thể đã quản lý commit theo ack mode. Thêm **commitSync()** trong callback mà không xác định ranh giới quản lý offset có thể gây commit sớm hoặc hành vi khó dự đoán.

### Giữ Consumer để gọi từ thread khác

Kafka consumer không thread-safe. Không đưa object Consumer vào executor rồi gọi **seek**, **commitSync** hoặc **pause** tùy ý. Thao tác consumer nên diễn ra trên thread sở hữu consumer hoặc thông qua API điều phối của Spring Kafka.

### Giả định assigned luôn chứa toàn bộ partition

Với cooperative rebalancing, callback có thể chỉ chứa partition mới được giao. Khởi tạo hoặc khôi phục theo đúng tập partition được truyền vào.

### Không xử lý lỗi cleanup

Nếu flush state thất bại, log và metric cần chỉ rõ partition bị ảnh hưởng. Không đánh dấu checkpoint thành công khi dữ liệu chưa được lưu. Hãy thiết kế cleanup có thể thử lại an toàn và không làm callback chờ vô hạn.

### Dùng callback thay cho quản lý consumer lag

Rebalance listener không phải cơ chế xử lý lag. Lag tăng cần được điều tra ở tốc độ xử lý, concurrency, số partition, downstream dependency và cấu hình poll.

## 11. Những cấu hình consumer có liên quan đến rebalance

Một số thuộc tính ảnh hưởng tần suất và hành vi rebalance:

| Thuộc tính | Vai trò | Lưu ý vận hành |
|---|---|---|
| **group.id** | Định danh consumer group | Consumer có group ID khác thuộc group khác |
| **partition.assignment.strategy** | Chọn assignor phân phối partition | Cooperative assignor có thể giảm lượng partition phải thu hồi |
| **session.timeout.ms** | Thời gian coordinator chờ heartbeat trước khi xem consumer không còn hoạt động | Giá trị quá thấp dễ làm consumer bị loại khi có gián đoạn ngắn |
| **heartbeat.interval.ms** | Chu kỳ gửi heartbeat trong các giao thức dùng heartbeat riêng | Thường phải nhỏ hơn session timeout theo giới hạn Kafka |
| **max.poll.interval.ms** | Thời gian tối đa giữa các lần poll khi consumer đang xử lý | Xử lý quá lâu có thể khiến consumer rời group |
| **max.poll.records** | Giới hạn số record trả về trong một lần poll | Điều chỉnh cùng thời gian xử lý mỗi record |
| **group.instance.id** | Định danh thành viên tĩnh nếu sử dụng static membership | Có thể giảm rebalance khi restart có kiểm soát; cần ID duy nhất theo instance |

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      properties:
        max.poll.interval.ms: 300000
        session.timeout.ms: 45000
        heartbeat.interval.ms: 15000
        max.poll.records: 200
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Đây là giá trị minh họa, không phải cấu hình mặc định phù hợp cho mọi hệ thống. Thời gian xử lý thực tế, số partition, tải và phiên bản Kafka cần được đo trước khi điều chỉnh.

Giảm **max.poll.records** có thể giảm thời gian xử lý mỗi batch, nhưng cũng có thể giảm throughput. Tăng **max.poll.interval.ms** có thể cho phép xử lý batch lâu hơn, nhưng không giải quyết nguyên nhân downstream chậm. Cooperative assignor giúp giảm phạm vi partition bị chuyển trong nhiều trường hợp, nhưng không loại bỏ mọi rebalance.

## 12. Quan sát rebalance trong production

Nên theo dõi cả metric của consumer và thông tin callback. Một số chỉ số hữu ích:

- Số lần rebalance theo consumer group và instance.
- Thời gian từ lúc bắt đầu rebalance tới khi consumer tiếp tục xử lý ổn định.
- Số partition được revoke, assigned và lost.
- Thời gian thực thi từng callback.
- Số lỗi khi flush checkpoint hoặc cleanup state.
- Số lỗi commit offset.
- Consumer lag và tốc độ xử lý trước/sau rebalance.
- Số lần consumer bị loại do vượt **max.poll.interval.ms** hoặc không duy trì heartbeat.

Log callback nên có group ID, client ID, consumer instance, topic, partition, callback type và timestamp. Không chỉ ghi “rebalance happened”; thông tin partition giúp xác định assignment có thay đổi như dự kiến hay không.

Ví dụ log có cấu trúc:

~~~text
event=consumer_rebalance
group_id=order-projection
client_id=consumer-2
callback=onPartitionsRevoked
partitions=orders.created-2,orders.created-3
duration_ms=18
~~~

Các giá trị trên chỉ minh họa. Hãy tránh ghi payload hoặc thông tin bí mật vào log rebalance.

Nếu callback kéo dài, điều tra database flush, lock contention, state store hoặc thao tác mạng được gọi bên trong callback. Nếu rebalance xảy ra liên tục, kiểm tra log coordinator, poll interval, heartbeat, consumer restart, subscription và network.

## 13. Kiểm thử ConsumerRebalanceListener

Unit test có thể kiểm tra logic cleanup và state transition bằng cách gọi callback với các tập **TopicPartition** giả lập. Tuy nhiên, unit test không chứng minh group coordinator và assignor thực sự phát callback theo đúng tình huống.

Integration test với Kafka broker phù hợp nên bao phủ:

1. Một consumer nhận assignment ban đầu và khởi tạo state cho các partition được giao.
2. Một consumer thứ hai tham gia group và tạo rebalance.
3. Consumer cũ chỉ cleanup các partition thực sự bị revoke.
4. Consumer mới khởi tạo state cho partition được giao.
5. Consumer bị mất kết nối hoặc mất ownership và đường lost được xử lý nếu phiên bản client hỗ trợ.
6. Callback không làm mất offset đã xử lý hoặc bỏ qua record chưa xử lý.
7. Cooperative rebalancing giữ lại state của partition không bị revoke.
8. Listener cleanup không vượt thời gian poll và không làm group rebalance lặp lại.

Khi kiểm thử callback, nên xác minh trạng thái partition trước và sau rebalance, không chỉ xác minh callback được gọi. Một test có thể thấy **onPartitionsRevoked** chạy nhưng vẫn bỏ sót lỗi xóa state của partition không bị revoke.

## 14. Checklist triển khai

**Thiết kế callback**

- [ ] Đã xác định state hoặc tài nguyên nào gắn với partition.
- [ ] Đã phân biệt revoke bình thường, assignment mới và partition lost.
- [ ] Callback chỉ thao tác trên partition được truyền vào.
- [ ] Cleanup có thể chạy lặp an toàn và không xóa state của partition vẫn được giữ.
- [ ] Có fencing hoặc ownership check nếu state được chia sẻ giữa nhiều consumer.

**Tích hợp Spring Kafka**

- [ ] Listener được gắn vào đúng container factory.
- [ ] Đã chọn **ConsumerRebalanceListener** hay **ConsumerAwareRebalanceListener** theo nhu cầu.
- [ ] Đã hiểu callback trước/sau commit của Spring Kafka.
- [ ] Ack mode và offset commit strategy đã được xác định.
- [ ] Không commit thủ công trùng với container.
- [ ] Không gọi API Consumer từ thread khác.

**Hiệu năng và độ tin cậy**

- [ ] Callback ngắn, không chờ dịch vụ bên ngoài không giới hạn.
- [ ] Flush/checkpoint được thực hiện định kỳ trong quá trình xử lý.
- [ ] **max.poll.interval.ms**, heartbeat và session timeout phù hợp với tải.
- [ ] Hành vi cooperative/eager assignor đã được tính đến.
- [ ] Consumer có idempotency để chịu được record được giao lại sau rebalance.

**Quan sát và kiểm thử**

- [ ] Có log/metric cho revoke, assigned, lost, callback duration và commit failure.
- [ ] Có kiểm thử khi consumer gia nhập, rời group, restart và mất kết nối.
- [ ] Đã kiểm tra tình huống callback chỉ nhận một phần partition.
- [ ] Đã xác minh state và offset không bị mất hoặc ghi sai sau rebalance.

## 15. Nguyên tắc vận hành

ConsumerRebalanceListener là điểm tích hợp cho vòng đời assignment của partition. **onPartitionsRevoked** cho ứng dụng cơ hội hoàn tất cleanup trước khi bàn giao bình thường; **onPartitionsAssigned** cho phép khởi tạo trạng thái khi nhận partition; **onPartitionsLost** xử lý tình huống quyền sở hữu đã mất.

Trong Spring Kafka, hãy gắn listener vào đúng container factory và sử dụng **ConsumerAwareRebalanceListener** khi cần truy cập consumer hoặc phối hợp thao tác trước/sau commit. Giữ callback ngắn, quản lý state theo từng **TopicPartition**, tôn trọng cơ chế commit của container và bảo vệ state dùng chung bằng idempotency hoặc fencing. Khi các quy tắc này rõ ràng, consumer có thể thay đổi assignment mà vẫn giữ được tiến độ xử lý và khả năng phục hồi khi thành viên group gặp sự cố.
