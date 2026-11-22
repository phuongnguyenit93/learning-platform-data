# Partition assignment event

## 1. Partition assignment event là gì?

Trong Spring Kafka, **partition assignment event** là thông báo liên quan đến việc một Kafka consumer được gán quyền đọc một hoặc nhiều partition. Một consumer chỉ có thể đọc dữ liệu của những partition hiện được giao cho nó. Việc assignment thay đổi khi consumer group khởi động, rebalance, mở rộng số instance, consumer rời group hoặc subscription thay đổi.

Spring Kafka phát các **application events** để ứng dụng quan sát lifecycle này, đặc biệt:

- **ConsumerPartitionAssignedEvent**: thông báo consumer container được gán các partition.
- **ConsumerPartitionRevokedEvent**: thông báo partition bị thu hồi trong quá trình rebalance.
- **ConsumerPartitionLostEvent**: thông báo consumer đã mất partition theo tình huống tương ứng.

Partition assignment event không phải một bản ghi Kafka được producer gửi vào topic. Đây là sự kiện **trong ứng dụng Spring** do listener container phát khi quản lý KafkaConsumer.

~~~text
Kafka topic orders.created
    P0    P1    P2    P3
     \     |     |    /
      \    |     |   /
       Consumer group rebalance
                  |
                  v
       Kafka partition assignment
                  |
         +--------+--------+
         |                 |
     Consumer A         Consumer B
       P0, P1             P2, P3
         |                 |
         v                 v
    Spring Kafka       Spring Kafka
  listener container listener container
         |                 |
         +---- publish ----+
                  |
                  v
      ConsumerPartitionAssignedEvent
                  |
                  v
       @EventListener / monitoring
~~~

Bài học thuộc nhóm **Rebalance và lifecycle**: cần hiểu event được tạo lúc nào, nên dùng để quan sát hay thực hiện logic nào, khác gì với callback của Kafka ConsumerRebalanceListener và làm sao vận hành an toàn khi partition ownership đổi.

## 2. Vì sao assignment quan trọng?

Kafka chia một topic thành các partition. Trong một consumer group, ở một thời điểm hợp lệ, mỗi partition được giao cho tối đa một consumer trong group. Đây là cơ sở để group phân phối tải và giữ thứ tự đọc theo partition.

Giả sử topic **orders.created** có sáu partition. Ba consumer cùng group **fulfillment-workers** có thể nhận:

~~~text
Consumer A -> P0, P1
Consumer B -> P2, P3
Consumer C -> P4, P5
~~~

Nếu Consumer B bị dừng, Kafka cần gán P2 và P3 cho thành viên còn lại. Khi đó partition assignment thay đổi. Ứng dụng phải sẵn sàng:

- Bắt đầu xử lý partition vừa được giao.
- Ngừng coi partition đã bị thu hồi là thuộc sở hữu của consumer cũ.
- Phục hồi những trạng thái cục bộ chỉ hợp lệ khi sở hữu partition.
- Xử lý record được giao lại vì offset trước đó chưa commit.
- Quan sát consumer lag, throughput và thời gian rebalance.

**Assignment event** giúp ứng dụng nhận biết quá trình thay đổi ownership. Nó không tự sửa offset, không đảm bảo local state đúng và không thay thế error handler hoặc cơ chế Kafka commit.

## 3. Kafka assignment khác Spring application event

Cần phân biệt hai lớp:

| Lớp | Thành phần | Nhiệm vụ |
|---|---|---|
| Kafka client | Consumer group coordinator và assignor | Quyết định partition thuộc consumer nào |
| Kafka client callback | ConsumerRebalanceListener | Thông báo assignment, revoke và loss trong poll/rebalance |
| Spring Kafka | KafkaMessageListenerContainer | Quản lý consumer, poll loop, listener, offset và lifecycle |
| Spring Kafka | ConcurrentMessageListenerContainer | Quản lý nhiều child container, mỗi child có consumer riêng |
| Spring application event | ConsumerPartitionAssignedEvent | Cho các Spring beans quan sát thông tin partition được gán |

**Spring application event không quyết định partition assignment**. Quyết định thuộc về Kafka group protocol, coordinator và partition assignor. Event của Spring Kafka phản ánh sự kiện trong lifecycle của container.

### 3.1. Hai kiểu hook dễ bị nhầm

Một ứng dụng có thể nhận thông tin assignment qua:

1. **@EventListener** xử lý ConsumerPartitionAssignedEvent.
2. **ConsumerAwareRebalanceListener** gắn trực tiếp vào container.

Cả hai đều liên quan đến rebalance, nhưng không có cùng hợp đồng về thời điểm, thread và quyền thao tác với KafkaConsumer. Khi cần thao tác seek hoặc bảo đảm logic xảy ra đồng bộ với rebalance, callback rebalance thường phù hợp hơn.

## 4. ConsumerPartitionAssignedEvent

Tên lớp được Spring Kafka cung cấp là **org.springframework.kafka.event.ConsumerPartitionAssignedEvent**.

Event này mô tả partition được giao cho container. Ứng dụng có thể dùng nó để cập nhật dashboard, ghi log hoặc thông báo một hệ thống quan sát về ownership.

Một handler đơn giản:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionAssignedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPartitionLifecycleObserver {

    @EventListener
    public void onAssigned(ConsumerPartitionAssignedEvent event) {
        log.info(
            "Kafka partitions assigned: {}",
            event.getPartitions()
        );
    }
}
~~~

**getPartitions()** trả về thông tin các TopicPartition liên quan đến assignment event. Mỗi TopicPartition là cặp topic và partition ID.

Ví dụ log:

~~~text
Kafka partitions assigned:
[orders.created-0, orders.created-1]
~~~

Số partition có thể bằng 0 hoặc thay đổi giữa các lần assignment tùy group protocol, partition assignor và giai đoạn rebalance. Không hardcode giả định rằng mỗi event luôn mang toàn bộ partition của topic hoặc có đúng một event mỗi lần deployment.

### 4.1. Event không chứa record nghiệp vụ

Assigned event không phải ConsumerRecord và không chứa order payload, eventId hay business key. Nó mô tả consumer ownership.

Không dùng handler assignment để xử lý nội dung record thay cho @KafkaListener. Dữ liệu nghiệp vụ vẫn đi qua Kafka consumer poll và listener method tương ứng.

### 4.2. Không dựa vào event làm cơ chế lock phân tán

Kafka group assignment đảm bảo ownership theo semantics của consumer group, nhưng một local application event không phải lock hay lease cho tài nguyên bên ngoài Kafka.

Nếu ứng dụng muốn cho phép đúng một instance ghi một bảng/partition ngoài Kafka, cần xem thêm fencing, ownership epoch, idempotency hoặc distributed coordination. Không chỉ dựa vào việc đã nhận ConsumerPartitionAssignedEvent rồi giữ một boolean local mãi mãi.

## 5. Event thu hồi partition và mất partition

Để hiểu assigned event, cần biết những event đối xứng:

| Event | Ý nghĩa vận hành | Hành động thường gặp |
|---|---|---|
| ConsumerPartitionAssignedEvent | Consumer được giao partition | Ghi log, cập nhật mapping ownership, chuẩn bị local state |
| ConsumerPartitionRevokedEvent | Partition bị thu hồi trong rebalance | Ngừng xử lý theo ownership cũ, cleanup trạng thái cục bộ |
| ConsumerPartitionLostEvent | Consumer không còn sở hữu partition do tình huống loss | Dừng sử dụng ownership cũ, không tự commit như vẫn sở hữu |

**Revoked** và **lost** không đồng nghĩa. Với revoke bình thường, consumer có thể còn cơ hội hoàn tất bước cleanup/commit trong pha rebalance theo callback phù hợp. Với lost, ownership có thể đã chuyển đi; không an toàn khi coi consumer cũ vẫn có quyền thao tác offset.

Ví dụ observer:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionAssignedEvent;
import org.springframework.kafka.event.ConsumerPartitionLostEvent;
import org.springframework.kafka.event.ConsumerPartitionRevokedEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionEvents {

    @EventListener
    public void assigned(ConsumerPartitionAssignedEvent event) {
        log.info("ASSIGNED {}", event.getPartitions());
    }

    @EventListener
    public void revoked(ConsumerPartitionRevokedEvent event) {
        log.info("REVOKED {}", event.getPartitions());
    }

    @EventListener
    public void lost(ConsumerPartitionLostEvent event) {
        log.warn("LOST {}", event.getPartitions());
    }
}
~~~

Những event này phục vụ observability. Với ứng dụng cần commit, seek hoặc thao tác trực tiếp trên KafkaConsumer tại thời điểm rebalance, sử dụng **ConsumerAwareRebalanceListener** đúng lifecycle thay vì làm những tác vụ này một cách gián tiếp từ observer.

## 6. Timeline khi consumer group khởi động

Một quá trình khởi động cơ bản:

~~~text
Spring Boot startup
         |
         v
@KafkaListener container starts
         |
         v
KafkaConsumer subscribes to topic
         |
         v
KafkaConsumer.poll()
         |
         v
Join group / assignment protocol
         |
         v
Kafka assigns partitions
         |
         v
Rebalance callback
         |
         v
Spring Kafka publishes assignment event
         |
         v
Consumer begins polling assigned partitions
         |
         v
Listener processes records
~~~

Thứ tự chi tiết giữa các thao tác nội bộ phụ thuộc phiên bản Kafka client, group protocol, Spring Kafka container và callback. Tuy nhiên, về mặt thiết kế, assigned event cho biết consumer/container đã đi tới giai đoạn nhận partition trong vòng đời của nó.

### 6.1. Event có thể lặp lại

Sau startup, cùng consumer có thể nhận assignment event mới khi:

- Thêm hoặc loại bớt một replica.
- Container dừng rồi chạy lại.
- Consumer bị timeout, crash hoặc mất group membership.
- Topic được thêm partition.
- Subscription hoặc assignment strategy thay đổi.
- Một rebalance được kích hoạt bởi thay đổi thành viên.

Vì vậy, xử lý assignment event cần **idempotent**. Không coi đó là callback chỉ chạy một lần trong cả vòng đời ứng dụng.

## 7. Eager rebalance và cooperative rebalance

Kafka có các chiến lược gán partition khác nhau. Sự khác biệt này ảnh hưởng event mà ứng dụng thấy.

### 7.1. Eager rebalance

Trong phương pháp eager, các consumer trong group có thể thu hồi phần lớn hoặc toàn bộ assignment hiện tại rồi nhận assignment mới.

~~~text
Trước rebalance:
  A -> P0, P1
  B -> P2, P3

Rebalance:
  revoke assignment cũ
  compute assignment mới

Sau rebalance:
  A -> P0, P2
  B -> P1, P3
~~~

Ứng dụng có thể thấy revoke và assign nhiều partition trong một chu kỳ. Đây là lý do một rebalance rộng có thể tạo pause xử lý tạm thời.

### 7.2. Cooperative/incremental rebalance

Với cooperative assignment, Kafka có thể di chuyển partition theo từng bước thay vì buộc mọi consumer trả lại toàn bộ partition ngay lập tức.

~~~text
Trước:
  A -> P0, P1
  B -> P2, P3

Giai đoạn chuyển:
  A giữ P0, nhả P1
  B giữ P2, P3

Giai đoạn tiếp:
  A -> P0
  B -> P1, P2, P3
~~~

Trong các phiên bản và protocol tương ứng, event có thể chỉ mang những partition được thu hồi hoặc mới được giao ở một bước nhất định, thay vì danh sách toàn bộ assignment.

**Không suy ra tổng partition consumer sở hữu chỉ bằng một event đơn lẻ.** Nếu cần hình ảnh ownership đầy đủ, tổng hợp trạng thái theo consumer hoặc dùng công cụ Kafka admin/metrics phù hợp.

### 7.3. Cần chú ý khi chuyển assignor

Chuyển eager sang cooperative không phải chỉ đổi một config trên một pod trong mọi trường hợp. Cần tuân theo quy trình tương thích assignment strategy và group protocol của phiên bản Kafka hiện tại. Một rollout không tương thích có thể làm group rebalance kéo dài hoặc không ổn định.

## 8. Concurrency và per-consumer assignment

Khi @KafkaListener dùng concurrency > 1, Spring Kafka tạo một **ConcurrentMessageListenerContainer** quản lý nhiều **KafkaMessageListenerContainer** con.

Ví dụ:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Giả sử topic có sáu partition và concurrency=3:

~~~text
Parent concurrent listener container
       |
       +-- child #0 -> consumer #0 -> P0, P1
       +-- child #1 -> consumer #1 -> P2, P3
       +-- child #2 -> consumer #2 -> P4, P5
~~~

Mỗi consumer con có assignment và poll loop riêng. Event được phát từ lifecycle của các child containers, vì vậy ứng dụng có thể nhận nhiều assigned events gần nhau thay vì một event duy nhất cho parent.

**Concurrency không làm một partition được nhiều consumer cùng group xử lý đồng thời.** Nó cho phép partition khác nhau được xử lý trên nhiều consumer.

### 8.1. Tổng số consumer trong deployment

Nếu chạy bốn pod, mỗi pod concurrency=3:

~~~text
4 pods x 3 consumers per pod = 12 consumers
~~~

Nếu topic chỉ có 8 partition và group chỉ subscribe topic đó, một số consumer có thể không nhận partition. Đừng xem sự hiện diện của một child consumer mà chưa thấy assignment là bằng chứng consumer gặp lỗi.

### 8.2. Client ID dùng để đối chiếu

Đặt clientIdPrefix giúp nhận diện các consumer con:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3",
    clientIdPrefix = "orders-pod-a"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Spring Kafka có thể thêm suffix cho client IDs của các consumer con, ví dụ orders-pod-a-0, orders-pod-a-1 và orders-pod-a-2.

Khi điều tra assignment event, đối chiếu client ID, group ID, listener/container ID và partition assignment. Chỉ nhìn topic/partition mà không xác định consumer liên quan sẽ khó phân tích một group có nhiều replica.

## 9. Event listener và ConsumerAwareRebalanceListener khác nhau thế nào?

Hai cách đều hữu ích nhưng có mục đích khác.

| Tiêu chí | Spring @EventListener | ConsumerAwareRebalanceListener |
|---|---|---|
| Nhận thông báo assignment | Có | Có |
| Điểm tích hợp | Spring application event system | Kafka consumer rebalance callback trong container |
| Hợp với logging/metrics | Rất phù hợp | Phù hợp |
| Hợp với consumer.seek | Không ưu tiên | Phù hợp khi gọi đúng thread |
| Hợp với logic commit tại revoke | Không ưu tiên | Có callback trước/sau commit |
| Kiểm soát timing đối với rebalance | Phụ thuộc event multicaster | Tương tác trực tiếp ở rebalance lifecycle |
| Nên chạy I/O nặng | Không | Không |
| Tính đồng bộ | Mặc định thường đồng bộ; có thể bị đổi | Chạy theo lifecycle consumer callback |

**@EventListener** phù hợp khi cần quan sát và cập nhật telemetry. **ConsumerAwareRebalanceListener** phù hợp khi cần thao tác KafkaConsumer trong giai đoạn assignment hoặc revoke.

### 9.1. Vì sao không dùng event listener để tự commit?

ApplicationEvent có thể được phát đồng bộ mặc định, nhưng Spring cho phép cấu hình ApplicationEventMulticaster chạy bất đồng bộ. Khi chạy trên thread khác, KafkaConsumer không thread-safe và thao tác commit/seek từ event listener sẽ không an toàn.

Ngay cả khi event listener đang đồng bộ, container đã có cơ chế quản lý commit/offset. Một lệnh commit tự ý có thể xung đột với AckMode, transaction hoặc error handler.

Vì vậy, hãy để container quản lý offset. Nếu cần hành vi đặc biệt trong rebalance, dùng callback đúng lifecycle và hiểu rõ tác động commit.

## 10. ConsumerAwareRebalanceListener

Spring Kafka cung cấp interface **org.springframework.kafka.listener.ConsumerAwareRebalanceListener** để làm việc với assignment/revoke cùng KafkaConsumer đang sở hữu partition.

Một số hook thường dùng:

- **onPartitionsAssigned(Consumer, Collection<TopicPartition>)**
- **onPartitionsRevokedBeforeCommit(Consumer, Collection<TopicPartition>)**
- **onPartitionsRevokedAfterCommit(Consumer, Collection<TopicPartition>)**
- **onPartitionsLost(Consumer, Collection<TopicPartition>)**

Hook chính xác và default behavior có thể khác theo phiên bản Spring Kafka; kiểm tra JavaDoc khi dùng trực tiếp.

Ví dụ cấu hình trong factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {

            @Override
            public void onPartitionsAssigned(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {

                log.info("Assigned {}", partitions);
            }

            @Override
            public void onPartitionsRevokedBeforeCommit(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {

                log.info("Revoking before commit {}", partitions);
            }

            @Override
            public void onPartitionsRevokedAfterCommit(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {

                log.info("Revoked after commit {}", partitions);
            }

            @Override
            public void onPartitionsLost(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {

                log.warn("Partitions lost {}", partitions);
            }
        }
    );

    return factory;
}
~~~

Đoạn code tập trung vào các callback. Ứng dụng cần bổ sung imports, deserializer, error handler và cấu hình khác tùy use case.

### 10.1. Vì sao có before commit và after commit?

Spring Kafka tách hook revoke để hỗ trợ một số công việc trước/sau khi container xử lý các commit đang chờ theo quy tắc của nó. Điều này không có nghĩa mọi revoke đều chắc chắn commit được; trạng thái group, transaction và lỗi broker vẫn cần được xử lý đúng.

Không nên gọi **consumer.commitSync()** trong mọi callback nếu container đã quản lý AckMode và transaction. Việc commit tự ý có thể làm offset vượt qua record chưa xử lý hoặc xung đột với ranh giới transaction.

### 10.2. onPartitionsLost khác onPartitionsRevoked

Khi partition đã bị mất, consumer có thể không còn quyền sở hữu hợp lệ để commit offset cho partition đó. Nên dùng callback lost để dọn state cục bộ, ngừng quyền xử lý và ghi nhận mất ownership.

Không xử lý lost bằng cách cố commit “lần cuối” như trong revoke bình thường. Offset commit cần được quản lý theo container semantics và tính hợp lệ của consumer group membership.

## 11. Seek khi nhận partition mới

Một use case có thể cần đặt lại vị trí đọc khi partition được giao. Ví dụ một ứng dụng đặc biệt muốn bắt đầu từ offset đã lưu ngoài Kafka hoặc replay từ một điểm được phê duyệt.

Với ConsumerAwareRebalanceListener, có thể thao tác seek trên consumer thread trong callback assignment:

~~~java
@Override
public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    for (TopicPartition partition : partitions) {
        Long requiredOffset = recoveryStore.findOffset(partition);

        if (requiredOffset != null) {
            consumer.seek(partition, requiredOffset);
        }
    }
}
~~~

**Chỉ dùng kiểu thiết kế này nếu có lý do rõ ràng**. Trong consumer group thông thường, Kafka đã lưu committed offset và auto.offset.reset quyết định nơi bắt đầu nếu chưa có offset. Tự seek ở mỗi assignment có thể:

- Đọc lại record cũ ngoài dự kiến.
- Bỏ qua record chưa xử lý nếu external offset quá cao.
- Phá vỡ chính sách retry/recovery.
- Làm trạng thái Kafka group offset và external checkpoint lệch nhau.
- Tạo duplicate side effect sau rebalance.

Nếu cần seek để bootstrap một luồng replay, hãy định nghĩa policy, test multi-partition và ghi rõ khi nào external offset có thể được tin cậy.

### 11.1. ConsumerSeekAware là lựa chọn khác

Spring Kafka cũng cung cấp **ConsumerSeekAware** cho các trường hợp listener cần điều chỉnh vị trí đọc theo assignment/idle event. Đây có thể là lựa chọn có cấu trúc hơn để tương tác với seek callbacks, tùy kiểu listener và phiên bản.

Đừng dùng cả ConsumerSeekAware và ConsumerAwareRebalanceListener để seek cùng partition mà không có quy tắc ưu tiên; thứ tự callback và trạng thái offset có thể khó dự đoán.

## 12. Sử dụng event để làm mới local state

Một số ứng dụng duy trì cache hoặc state theo partition:

~~~text
Partition P0:
  local cache for customer range A
  buffered aggregation state
  in-memory sequence tracker

Partition P1:
  local cache for customer range B
  buffered aggregation state
  in-memory sequence tracker
~~~

Khi được gán partition mới, consumer có thể cần tải lại state thích hợp. Khi partition bị thu hồi hoặc mất, cần giải phóng ownership và dọn state cục bộ.

Tuy nhiên, state reconstruction có thể mất nhiều thời gian. Không thực hiện một DB scan kéo dài phút ngay trong consumer rebalance callback; điều này có thể trì hoãn poll, heartbeat và assignment.

Một cách thiết kế:

1. Ghi nhận partition được assign.
2. Tạo trạng thái **initializing** cho partition.
3. Khởi động logic chuẩn bị state có kiểm soát.
4. Không xử lý record nghiệp vụ với state chưa sẵn sàng.
5. Chỉ chuyển **ready** khi state đã được phục hồi và ownership vẫn hợp lệ.
6. Khi revoke/lost, hủy công việc khởi tạo cũ và dọn state theo generation.

Nếu dùng asynchronous initialization, phải xử lý race: partition có thể bị revoke trước khi tác vụ restore hoàn tất. Không để tác vụ cũ ghi vào state của một consumer mới đã nhận partition.

### 12.1. Lưu state ở đâu?

Nếu state quan trọng cho reliability, đừng chỉ giữ trong heap. Có thể cân nhắc:

- External database với version/ownership metadata.
- Compact Kafka topic cho changelog phù hợp với thiết kế riêng.
- Local persistent store với recovery/rebuild strategy.
- Cache có TTL và idempotent rebuild.
- Framework stream processing chuyên biệt nếu bài toán thực sự yêu cầu stateful stream semantics.

Partition assignment event chỉ báo thời điểm ownership thay đổi; nó không cung cấp sẵn state store hay checkpoint transaction.

## 13. Thread safety và event multicaster

Theo cấu hình phổ biến, Spring application events được phát đồng bộ qua ApplicationEventMulticaster mặc định. Vì Kafka container phát event trong lifecycle consumer, một handler nặng có thể kéo dài đường thực thi liên quan consumer.

Nhưng ứng dụng có thể tùy biến multicaster để chạy async. Khi đó handler event không còn chắc chắn chạy trên consumer thread.

**Nguyên tắc an toàn:**

- Không gọi KafkaConsumer từ thread tùy ý.
- Không gọi commitSync/seek/pause trực tiếp từ async event handler.
- Không chạy HTTP/DB blocking lâu trong @EventListener.
- Không giữ reference KafkaConsumer để sử dụng sau này.
- Ghi nhận metrics/log ngắn gọn, không tạo công việc nặng.
- Nếu cần thay đổi ownership state, dùng data structure thread-safe.
- Nếu cần thao tác consumer, dùng hook/cơ chế container đảm bảo chạy đúng thread.

### 13.1. Event listener exception

Nếu @EventListener ném exception khi event được publish đồng bộ, exception có thể ảnh hưởng đường lifecycle của container theo cách khó mong muốn. Vì thế observer nên tránh để lỗi telemetry/notification lan ra như lỗi nghiệp vụ.

Ví dụ:

~~~java
@EventListener
public void onAssigned(ConsumerPartitionAssignedEvent event) {
    try {
        partitionMetrics.recordAssignment(event.getPartitions());
    }
    catch (RuntimeException ex) {
        log.warn(
            "Cannot publish assignment telemetry, partitions={}",
            event.getPartitions(),
            ex
        );
    }
}
~~~

Không bắt mọi exception để che một lỗi assignment/seek có tính nghiệp vụ nếu hook được dùng làm phần bắt buộc của correctness. Phần critical nên có retry/fail-fast policy và được triển khai ở lifecycle callback thích hợp.

## 14. Phân biệt assignment event và pause/resume event

Spring Kafka cũng có events cho pause/resume consumer hoặc partition. Những sự kiện này khác assignment.

| Sự kiện | Ý nghĩa |
|---|---|
| Partition assigned | Consumer được gán quyền đọc partition |
| Partition revoked | Partition bị thu hồi từ consumer |
| Partition lost | Consumer mất ownership partition |
| Consumer paused | Consumer/container đang pause fetch/delivery theo container API |
| Consumer resumed | Consumer/container tiếp tục |
| Partition paused | Một partition được pause |
| Partition resumed | Một partition được resume |

**Pause không đồng nghĩa revoke.** Khi pause, consumer thường vẫn sở hữu partition và duy trì group membership. Khi revoke, partition có thể được gán sang consumer khác.

Không xóa state theo partition chỉ vì pause event nếu state cần được giữ để resume. Tương tự, một assignment event không có nghĩa consumer đang xử lý record ngay lập tức, vì listener có thể đang pause hoặc chờ state restoration.

## 15. Group rebalance triggers

Các thay đổi thường làm assignment thay đổi:

1. Một consumer mới tham gia group.
2. Một consumer rời group hoặc process crash.
3. Consumer bị coi là không còn hoạt động vì heartbeat/session timeout.
4. Consumer poll quá chậm và vi phạm max.poll.interval.ms.
5. Số partition của topic tăng.
6. Consumer subscription thay đổi.
7. Assignment strategy hoặc group protocol thay đổi.
8. Pod rolling restart, autoscale hoặc deployment bị kill.
9. Một consumer gặp lỗi khiến container restart hoặc membership thay đổi.

Không phải mọi thay đổi trong các trường hợp trên đều bắt buộc tạo một bản phân phối mới khác hoàn toàn. Rebalance có thể giữ một số partition ở consumer cũ tùy assignor.

### 15.1. Event có thể đến thường xuyên hơn kỳ vọng

Khi một ứng dụng restart liên tục hoặc được scale quá thường xuyên, số assignment events có thể tăng mạnh. Đây có thể là triệu chứng hệ thống mất ổn định, không phải nguyên nhân gốc.

Cần so sánh event timestamps với:

- Pod restart/rollout.
- Health check failures.
- Consumer poll latency.
- JVM GC pauses.
- Broker coordinator logs.
- Group rebalance rate.
- Network partition và session timeout.
- Downstream DB/HTTP latency.

## 16. Ảnh hưởng tới offset commit và at-least-once

Khi consumer mất partition, record đã xử lý nhưng chưa commit có thể được giao lại cho consumer tiếp theo. Ví dụ:

~~~text
Consumer A nhận P0, offset 100..104
      |
      +-- xử lý 100..102 thành công
      |
      +-- chưa commit offset 103
      |
      v
Rebalance -> P0 chuyển sang Consumer B
      |
      v
Consumer B đọc từ committed offset cũ
      |
      v
100..102 có thể bị giao lại
~~~

Đây là hành vi phù hợp với at-least-once. Assignment event không tạo exactly-once cho business side effects.

Vì vậy:

- Business side effect cần idempotency.
- AckMode phải phù hợp với ranh giới xử lý.
- Error handler cần định nghĩa retry/recovery.
- Khi revoke bình thường, container có thể xử lý pending offset theo policy.
- Khi partition lost, không giả định consumer cũ còn quyền commit.
- Nếu dùng Kafka transaction, input offset và output Kafka phải được phối hợp trong transaction tương ứng.

### 16.1. Ví dụ idempotency

Một consumer ghi trạng thái thanh toán/fulfillment vào database. Nếu cùng event được giao lại sau rebalance, unique event ID có thể giúp tránh duplicate.

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Nên ghi processed_event và side effect trong cùng DB transaction. Không chỉ dùng check-before-insert vì race condition; unique constraint cần được thực thi.

## 17. EOS và assignment event

Trong consume-transform-produce thuần Kafka, transactional listener container có thể commit output Kafka và input offsets trong cùng transaction. Khi rebalance hoặc exception làm transaction abort, output transactional chưa commit không xuất hiện với consumer read_committed và offset input không được commit trong transaction đó.

Tuy nhiên, assignment event không phải một transaction event:

~~~text
Assignment event:
   "Consumer vừa nhận partition"

Kafka transaction:
   "Những output và offset trong transaction được commit/abort"
~~~

Không suy ra transaction đã commit từ assignment event, và cũng không dùng assignment event để khởi tạo một Kafka transaction tùy ý thay container.

Nếu transactional listener cần xử lý lỗi, phải xem AfterRollbackProcessor và chính sách rollback của version Spring Kafka. Khi assignment đổi do rebalance, có thể xuất hiện replay ở listener method dù output Kafka committed vẫn tuân theo EOS trong scope Kafka.

## 18. Subscribe theo group và manual partition assignment

Kafka consumer có hai hướng quản lý partition:

**Group subscription:** dùng subscribe tới topic hoặc pattern, coordinator/assignor tự phân phối partition giữa consumer trong group.

**Explicit assignment:** gán TopicPartition cụ thể theo cấu hình, ví dụ @KafkaListener(topicPartitions=...), không dựa vào cùng quá trình group rebalance để phân phối partition tự động.

Ví dụ subscribe:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "fulfillment-workers"
)
public void consume(OrderCreated event) {
    process(event);
}
~~~

Ví dụ manual assignment:

~~~java
@KafkaListener(
    topicPartitions = @TopicPartition(
        topic = "orders.priority",
        partitions = {"0", "1"}
    )
)
public void consumePriority(OrderCreated event) {
    processPriority(event);
}
~~~

Khi dùng explicit assignment, không nên kỳ vọng mọi callback của **group rebalance** xảy ra giống subscribe-based consumer. Event/lifecycle xử lý assigned partitions có thể có hành vi khác tùy Spring Kafka version và container type.

Nếu ứng dụng phụ thuộc event để rebuild state, phải test cả mode thực sự đang dùng.

## 19. Nhiều listener và lọc theo nguồn event

Một Spring Boot app có thể có nhiều @KafkaListener, chẳng hạn orders, payments và audit. Một @EventListener nhận ConsumerPartitionAssignedEvent có thể quan sát event từ nhiều containers, không chỉ một topic.

Ví dụ:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "fulfillment-workers"
)
public void consumeOrder(OrderCreated event) {
    processOrder(event);
}

@KafkaListener(
    id = "audit-listener",
    topics = "orders.audit",
    groupId = "audit-indexer"
)
public void consumeAudit(OrderAudit event) {
    indexAudit(event);
}
~~~

Nếu chỉ cần log chung, một observer là đủ. Nếu cần xử lý riêng theo listener, phải lọc dựa trên thông tin container/source thích hợp và metadata topic/partition trong event.

Không dựa vào thread name theo một format không được bảo đảm giữa các phiên bản. Nên khai báo listener ID rõ ràng và dùng API source/container metadata được version hỗ trợ để mapping với listener.

### 19.1. Tránh cập nhật một map dùng chung không đồng bộ

Nhiều consumer containers có thể phát events từ những thread khác nhau. Nếu observer cập nhật mapping ownership:

~~~text
consumer-0 -> {orders.created-0, orders.created-1}
consumer-1 -> {orders.created-2, orders.created-3}
~~~

Map cần thread-safe hoặc được bảo vệ bằng cơ chế synchronization. Đồng thời, cần xử lý revoke/lost để không giữ partition ownership cũ.

Một counter “đã nhận assigned event” không thay thế cho state mapping hiện thời nếu event chỉ mang delta assignment.

## 20. Metrics và observability

Partition assignment event là nguồn thông tin hữu ích để theo dõi group lifecycle. Tuy nhiên, event chỉ là một phần observability; cần kết hợp metrics Kafka consumer và broker.

| Chỉ số/tín hiệu | Ý nghĩa |
|---|---|
| Assignment event count | Tần suất consumer nhận partition |
| Revoked event count | Tần suất partition bị thu hồi |
| Lost event count | Các trường hợp mất ownership cần chú ý |
| Assigned partition count | Số partition consumer đang sở hữu |
| Group rebalance rate | Group có ổn định hay không |
| Rebalance duration | Thời gian gián đoạn do rebalance |
| Consumer lag per partition | Partition nào đang chậm |
| Records consumed per client | Consumer có nhận tải cân bằng |
| Listener processing time | Thời gian xử lý record/batch |
| Commit latency/failures | Offset tiến đúng theo policy không |
| Pod restart / OOM / GC | Nguyên nhân có thể làm consumer rời group |
| Downstream latency | DB/API chậm dẫn tới poll interval vượt giới hạn |

Các metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer, exporter và tracing configuration. Không giả định mọi chỉ số đều có sẵn.

### 20.1. Log structured

Một log assignment hữu ích:

~~~text
event=partition_assigned
listenerId=orders-listener
groupId=fulfillment-workers
clientId=orders-pod-a-1
partitions=orders.created-2,orders.created-3
timestamp=...
~~~

Với revoke:

~~~text
event=partition_revoked
listenerId=orders-listener
groupId=fulfillment-workers
clientId=orders-pod-a-1
partitions=orders.created-3
timestamp=...
~~~

Không thêm record key, order ID, event ID hoặc payload vào assignment event log: những dữ liệu đó không thuộc partition ownership và gây cardinality/privacy risk.

### 20.2. Cardinality của metrics

Nếu tạo metric per partition và per consumer instance, số time series có thể tăng đáng kể. Nên chọn label có phạm vi rõ ràng: service, environment, consumer group và topic. Client ID/partition có ích cho chẩn đoán nhưng cần cân nhắc retention/cardinality.

## 21. Rebalance loop và sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Điều tra |
|---|---|---|
| Assigned/revoked event xuất hiện liên tục | Group rebalance lặp lại | Pod restart, heartbeat, max.poll.interval.ms |
| Event assigned có tập partition rỗng | Consumer chưa được gán partition hữu ích hoặc callback theo protocol | So sánh concurrency với partition count |
| Consumer lag tăng ngay sau scale | Rebalance hoặc state restore chậm | Event timestamps, assignment, downstream |
| Một consumer không có assignment | Nhiều consumer hơn partition hoặc distribution | Kiểm tra group members và partition count |
| Partition liên tục đổi owner | Rollout, unstable consumer hoặc assignor | Kiểm tra deployment và broker logs |
| Consumer B xử lý lặp record của A | A đã xử lý nhưng chưa commit trước revoke/crash | Idempotency, AckMode, commit logs |
| Local cache sai sau rebalance | State cũ không bị xóa hoặc restore chưa xong | Revoke/lost cleanup và state generation |
| Event handler làm consumer chậm | I/O/blocking trong @EventListener | Đo handler latency, tách telemetry |
| Lỗi seek khi event được xử lý async | KafkaConsumer được gọi ngoài consumer thread | Dùng rebalance listener/ConsumerSeekAware |
| Lost event và commit failure | Ownership đã mất | Không commit thủ công, điều tra group membership |

Không tăng concurrency hoặc timeout ngay khi thấy lag. Trước tiên xác định liệu lag đến từ rebalance, hot partition, downstream bottleneck, commit failure hay open transaction.

## 22. Testing partition assignment events

Một bài kiểm thử tích hợp có thể dùng Embedded Kafka hoặc Testcontainers để chạy broker với topic có nhiều partition.

### 22.1. Test startup assignment

1. Tạo topic orders.created có bốn partition.
2. Khởi động consumer group với listener concurrency=2.
3. Dùng @EventListener thu thập ConsumerPartitionAssignedEvent.
4. Xác nhận đã xảy ra assignment cho consumer trong group.
5. So sánh tổng partition được sở hữu hiện tại với topic và group membership.
6. Gửi record và xác nhận listener thực sự tiêu thụ.

Không chỉ dựa vào số event được phát để kết luận số partition: có thể có nhiều event hoặc event chỉ chứa subset assignment.

### 22.2. Test rebalance khi thêm consumer

1. Khởi động một instance consumer.
2. Đợi group ổn định và ghi nhận assignment.
3. Khởi động instance thứ hai với cùng group ID.
4. Quan sát revoke/assign events.
5. Xác nhận các partition được phân phối lại theo assignor.
6. Xác nhận không có partition bị hai consumer cùng group xử lý đồng thời như hai owner hợp lệ.
7. Gửi record để kiểm tra group tiếp tục xử lý.

Với cooperative assignor, có thể thấy partition chuyển theo các bước; đừng hardcode eager sequence cho mọi version.

### 22.3. Test consumer crash

1. Consumer A nhận partition và xử lý một số record.
2. Kill process A trước khi commit một offset để mô phỏng lỗi.
3. Consumer B tiếp tục tham gia group.
4. Quan sát assignment/loss tùy tình huống.
5. Xác nhận record chưa commit có thể được redeliver.
6. Kiểm tra idempotency hoặc deduplication ở business layer.

### 22.4. Test async event listener

Nếu ứng dụng cấu hình ApplicationEventMulticaster chạy bất đồng bộ, kiểm tra observer không chạm KafkaConsumer trực tiếp. Mục tiêu test là xác nhận event telemetry hoạt động mà không ảnh hưởng đến consumer poll/lifecycle.

## 23. Ví dụ thực tế: Order Fulfillment scale-out

Giả sử topic orders.created có tám partition. Ban đầu ứng dụng có hai pod, mỗi pod concurrency=2. Tổng cộng bốn consumer cùng group fulfillment-workers.

~~~text
Topic partitions: P0 P1 P2 P3 P4 P5 P6 P7

Pod A:
  Consumer A0 -> P0, P1
  Consumer A1 -> P2, P3

Pod B:
  Consumer B0 -> P4, P5
  Consumer B1 -> P6, P7
~~~

Ứng dụng tăng từ hai lên ba pod khi lượng đơn cao. Hai consumer mới được tạo. Kafka sẽ rebalance group; một số partition chuyển ownership.

Những consumer liên quan có thể phát:

~~~text
ConsumerPartitionRevokedEvent
ConsumerPartitionAssignedEvent
~~~

Nếu một pod gặp sự cố bất thường, có thể có tình huống partition lost theo semantics của client/container.

Tại lớp nghiệp vụ:

- Cache theo partition cũ phải được cleanup.
- Consumer mới nhận partition cần khôi phục local state nếu có.
- Các record đã xử lý nhưng chưa commit có thể được giao lại.
- Side effect tạo fulfillment phải idempotent theo event ID.
- Dashboard cần biểu diễn consumer-to-partition ownership sau rebalance.
- Không xử lý blocking state restore dài ngay trong event handler.

Sau khi group ổn định, đội vận hành nên kiểm tra consumer lag theo partition và throughput. Nếu một partition có hot key, tăng số consumer không giúp partition đó được xử lý bởi nhiều consumer cùng group.

## 24. Checklist khi triển khai

- [ ] Phân biệt Kafka group assignment với Spring application event.
- [ ] Biết các event Assigned, Revoked và Lost.
- [ ] Không giả định event chỉ chạy một lần.
- [ ] @EventListener chỉ làm observability/logic nhẹ khi phù hợp.
- [ ] Nếu cần seek, dùng callback đúng consumer thread.
- [ ] Nếu cần commit logic ở revoke, hiểu AckMode và lifecycle before/after commit.
- [ ] Không cố commit như vẫn sở hữu partition đã lost.
- [ ] Xử lý event state theo consumer, không gom nhầm nhiều child containers.
- [ ] Cân nhắc cooperative rebalance với delta assignments.
- [ ] Dọn local state khi revoke/lost và chống restore stale.
- [ ] Dùng idempotency cho record redelivery sau rebalance.
- [ ] Theo dõi rebalance, lag, commit, restart và poll interval.
- [ ] Kiểm thử startup, scale-out, crash và assignment changes.
- [ ] Có runbook cho rebalance loop và hot partition.
- [ ] Không dùng event assignment thay cho transaction hoặc distributed lock.

## 25. Runbook điều tra production

1. Xác định consumer group, topic và số partition.
2. Xác định listener ID, client ID, pod/instance bị ảnh hưởng.
3. Đọc timestamps của assigned/revoked/lost events.
4. Xem pod rollout, restart, OOM, readiness/liveness failures.
5. Kiểm tra consumer group membership và partition assignment hiện tại.
6. Kiểm tra max.poll.interval.ms, session timeout, heartbeat và poll duration.
7. Xem consumer lag theo partition và processing latency.
8. Kiểm tra downstream DB/API có làm listener block quá lâu không.
9. Đối chiếu assignor/protocol và thay đổi partition count.
10. Nếu có local state, xác minh cleanup/rebuild và generation.
11. Nếu thấy duplicate, xem committed offset, AckMode, replay và idempotency.
12. Nếu Kafka transactional, xem abort/recovery và input offset commit.
13. Kiểm tra observer có chặn consumer hoặc gọi KafkaConsumer sai thread không.
14. Sau khắc phục, xác nhận group ổn định và partition tiếp tục xử lý.
15. Ghi nguyên nhân và thay đổi cấu hình/runbook cho lần sau.

## 26. Những nhầm lẫn thường gặp

**“Partition assignment event là một record trong Kafka topic.”** Sai. Đó là Spring application event do listener container phát.

**“Nhận AssignedEvent nghĩa là partition sẽ thuộc consumer đó mãi mãi.”** Sai. Rebalance có thể thu hồi hoặc chuyển ownership.

**“AssignedEvent luôn chứa mọi partition của cả group.”** Sai. Event phản ánh assignment liên quan container và có thể là subset/incremental theo context.

**“Thấy nhiều assignment events là Kafka xử lý dữ liệu trùng.”** Chưa đủ kết luận. Cần kiểm tra offset, group state và side effect.

**“Có thể seek/commit trực tiếp từ bất kỳ @EventListener nào.”** Sai. KafkaConsumer không thread-safe; nếu event listener chạy async, điều đó rất nguy hiểm.

**“Revoked và Lost giống nhau.”** Sai. Lost có thể nghĩa consumer không còn ownership hợp lệ để commit.

**“Pause là revoke.”** Sai. Pause thường giữ assignment nhưng tạm dừng đọc/delivery.

**“Tăng concurrency luôn làm hết lag.”** Sai. Concurrency hữu ích bị giới hạn bởi partition và downstream capacity.

**“Assignment event tự quản lý local state.”** Sai. Ứng dụng phải thiết kế restore, cleanup và idempotency.

**“Đổi assignment không ảnh hưởng record đã xử lý.”** Sai. Record chưa commit có thể được giao lại.

**“Lọc event bằng thread name là một API ổn định.”** Không nên. Dùng listener/container metadata chính thức.

## 27. Ghi nhớ

**Partition assignment event** trong Spring Kafka là tín hiệu lifecycle cho biết partition được giao cho một consumer container. Sự kiện thường được quan sát qua **ConsumerPartitionAssignedEvent**, cùng với ConsumerPartitionRevokedEvent và ConsumerPartitionLostEvent khi ownership thay đổi.

Với tác vụ logging, monitoring và cập nhật trạng thái nhẹ, **@EventListener** là cách thuận tiện. Với thao tác consumer cần chạy đồng bộ trong rebalance như seek hoặc xử lý revoke có kiểm soát, ưu tiên **ConsumerAwareRebalanceListener** hoặc API lifecycle phù hợp, tránh truy cập KafkaConsumer từ thread khác.

Trong hệ thống bền vững, partition ownership luôn có thể thay đổi do scale, restart hoặc rebalance. Hãy kết hợp assignment event với commit offset đúng policy, local state cleanup, idempotent side effect, monitoring consumer lag và integration tests để consumer group phục hồi an toàn mà không bỏ sót hoặc tạo sai kết quả nghiệp vụ.
