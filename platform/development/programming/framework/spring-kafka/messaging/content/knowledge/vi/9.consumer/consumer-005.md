# Assign partition thủ công

Kafka consumer có thể nhận partition theo hai cách: tham gia consumer group để coordinator tự phân phối partition, hoặc tự chỉ định các partition mà consumer sẽ đọc. Cách thứ hai được gọi là **manual partition assignment**. Nó hữu ích khi ứng dụng hoặc một hệ thống điều phối bên ngoài đã biết consumer nào chịu trách nhiệm với partition nào.

Trong Spring Kafka, có thể chỉ định partition ngay trên @KafkaListener bằng topicPartitions, hoặc tạo container với các TopicPartitionOffset cụ thể. Ở mức Kafka Consumer API, phương thức assign() thực hiện việc gán trực tiếp. Khi dùng cách này, ứng dụng phải tự quản lý quyền sở hữu partition và thay đổi assignment theo vòng đời hệ thống.

Một điểm cần tách biệt ngay từ đầu: **manual assignment không đồng nghĩa manual offset commit**. Assignment quyết định consumer đọc partition nào; acknowledgement và commit offset quyết định vị trí đọc đã được xác nhận đến đâu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt subscribe() và assign() trong Kafka Consumer API.
- Giải thích vì sao manual assignment không tham gia cơ chế tự động phân phối và rebalance của consumer group.
- Gán partition bằng KafkaConsumer.assign() và bằng @KafkaListener topicPartitions.
- Cấu hình initial offset cho partition được chỉ định.
- Phân biệt manual partition assignment với manual acknowledgement/offset commit.
- Thiết kế cách phân chia partition giữa nhiều instance mà không xử lý trùng ngoài ý muốn.
- Hiểu ảnh hưởng của concurrency, tăng partition, restart và failover.
- Chọn giữa assignment thủ công và consumer group subscription theo yêu cầu vận hành.

## 1. Hai cách nhận partition của Kafka consumer

Kafka Consumer API có hai cơ chế chính:

- subscribe(): consumer đăng ký topic hoặc topic pattern và tham gia consumer group. Group coordinator cùng partition assignor quyết định partition nào được giao cho từng member.
- assign(): ứng dụng chỉ định trực tiếp danh sách TopicPartition mà consumer sẽ đọc.

Sơ đồ khái quát:

~~~text
SUBSCRIBE - group-managed assignment

Consumer A ----\
Consumer B -----+----> Group Coordinator / Partition Assignor
Consumer C ----/                    |
                                    v
                         Phân phối partition tự động


ASSIGN - manual assignment

Ứng dụng / bộ điều phối
        |
        +---- Consumer A: topic orders, partition 0
        |
        +---- Consumer B: topic orders, partition 1
        |
        +---- Consumer C: topic orders, partition 2
~~~

Với subscribe(), Kafka có thể tự phân phối lại partition khi member tham gia, rời group hoặc topology thay đổi. Với assign(), ứng dụng đã chỉ định partition; Kafka không tự chia lại assignment giữa các consumer theo group protocol.

Hai cách này loại trừ nhau trên cùng một KafkaConsumer tại một thời điểm. Gọi subscribe() sau assign() hoặc assign() sau subscribe() sẽ thay thế cơ chế assignment hiện tại; không nên trộn hai cách như thể chúng bổ sung cho nhau.

## 2. Khi nào nên assign partition thủ công?

Manual assignment phù hợp khi việc phân chia partition đã được một thành phần khác quyết định hoặc khi ứng dụng cần kiểm soát chính xác phạm vi đọc.

Một số trường hợp sử dụng:

- **Phân vùng theo shard do hệ thống điều phối:** một shard manager hoặc deployment controller đã gán partition cho từng worker.
- **Ứng dụng đọc một tập partition cố định:** ví dụ một job chuyên xử lý partition 0 và 1 trong một giai đoạn migration.
- **Replay hoặc backfill có phạm vi rõ:** một tiến trình đọc một số partition cụ thể để dựng lại dữ liệu.
- **Tách luồng đọc theo trách nhiệm vận hành:** mỗi worker được cấu hình chỉ đọc partition đã được giao.
- **Kiểm soát assignment trong một công cụ chuyên dụng:** ứng dụng quản trị cần đọc partition cụ thể để kiểm tra hoặc di chuyển dữ liệu.

Manual assignment không phải lựa chọn mặc định cho mọi consumer. Nếu cần tự động scale, phân phối lại khi instance lỗi và cân bằng partition giữa các member, subscribe() với consumer group thường đơn giản và an toàn hơn.

### Những trách nhiệm ứng dụng phải tự đảm nhận

Khi tự gán partition, ứng dụng phải biết:

1. Partition nào thuộc về instance nào.
2. Hai instance có vô tình cùng đọc một partition hay không.
3. Điều gì xảy ra khi instance dừng hoặc khởi động lại.
4. Ai phát hiện instance lỗi và chuyển quyền sở hữu partition.
5. Cách cập nhật assignment khi topic tăng partition.
6. Cách tránh hai worker đồng thời commit offset cho cùng một group/partition.

Kafka không tự giải quyết các câu hỏi trên bằng consumer group rebalance khi ứng dụng dùng assign().

## 3. Gán partition bằng Kafka Consumer API

Ở mức Kafka client thuần, ứng dụng tạo danh sách TopicPartition rồi truyền cho assign().

Ví dụ consumer chỉ đọc partition 0 và 1 của topic orders:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-manual-reader");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        OrderEventDeserializer.class);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

KafkaConsumer<String, OrderEvent> consumer =
        new KafkaConsumer<>(props);

TopicPartition partition0 = new TopicPartition("orders", 0);
TopicPartition partition1 = new TopicPartition("orders", 1);

consumer.assign(List.of(partition0, partition1));

try {
    while (running) {
        ConsumerRecords<String, OrderEvent> records =
                consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, OrderEvent> record : records) {
            processIdempotently(record);

            // commitSync() sau khi xử lý thành công.
            // Có thể commit theo batch để giảm chi phí.
        }

        consumer.commitSync();
    }
} finally {
    consumer.close();
}
~~~

Ví dụ minh họa vòng đời cơ bản. Trong ứng dụng thật, cần xử lý exception, shutdown signal, timeout và commit offset phù hợp. Không để biến running hoặc lifecycle consumer bị điều khiển từ nhiều thread mà không có cơ chế đồng bộ.

Các bước quan trọng:

1. Khởi tạo KafkaConsumer với bootstrap servers, deserializer và group.id nếu cần lưu offset theo consumer group.
2. Tạo TopicPartition cho từng partition cần đọc.
3. Gọi assign() trước vòng poll.
4. Gọi poll() để lấy record.
5. Xử lý record và commit offset theo chính sách của ứng dụng.
6. Gọi close() khi dừng để giải phóng tài nguyên.

### KafkaConsumer không thread-safe

KafkaConsumer không được thiết kế để nhiều thread gọi đồng thời. Các thao tác assign(), poll(), seek(), commitSync() và close() cần được điều phối theo consumer thread hoặc cơ chế thread ownership được Kafka hỗ trợ.

Không inject một KafkaConsumer dùng chung vào nhiều service thread rồi gọi poll/assign từ các thread khác nhau. Nếu cần xử lý song song, hãy tách phần lấy record khỏi phần xử lý nghiệp vụ và thiết kế acknowledgement/commit sao cho không xác nhận offset trước khi công việc tương ứng hoàn tất.

## 4. Assign không tự động rebalance

Khi dùng subscribe(), consumer group coordinator theo dõi membership và có thể phân phối lại partition. Khi dùng assign(), consumer chỉ nhận đúng danh sách partition mà ứng dụng chỉ định.

Ví dụ có ba instance:

~~~text
orders topic: P0  P1  P2  P3  P4  P5

Instance A:   P0  P1
Instance B:   P2  P3
Instance C:   P4  P5
~~~

Nếu Instance B dừng, Kafka không tự động chuyển P2 và P3 sang A hoặc C. Assignment vẫn là quyết định của ứng dụng. Một bộ điều phối bên ngoài cần phát hiện lỗi và gán lại hai partition đó cho worker còn hoạt động.

Nếu cả ba instance khởi động với cùng danh sách partition, mỗi instance có thể cùng đọc toàn bộ các partition được chỉ định. Đây là hành vi có thể xảy ra vì manual assignment không yêu cầu coordinator phân chia partition độc quyền giữa các member.

### Group ID vẫn có thể được dùng để lưu offset

Manual assignment không dùng group coordinator để phân phối partition, nhưng consumer vẫn có thể dùng group.id để lưu và đọc committed offset của partition. Coordinator vẫn tham gia các yêu cầu commit offset; điều đó không biến manual assignment thành subscription có rebalance tự động.

Vì vậy, cần phân biệt:

- **Partition ownership:** do ứng dụng chỉ định.
- **Offset storage:** có thể dùng group.id để lưu vị trí đọc đã commit.
- **Group-managed assignment:** không diễn ra khi consumer dùng assign().

Nếu nhiều consumer manual assign cùng một partition và dùng cùng group.id, chúng có thể cùng xử lý dữ liệu và cùng ghi offset cho partition đó. Các commit có thể cạnh tranh hoặc ghi đè vị trí của nhau. Chỉ cho phép một worker có quyền sở hữu partition trong cùng một group nếu muốn tránh xử lý trùng và offset race.

Nếu mỗi tiến trình cần đọc độc lập toàn bộ dữ liệu, hãy dùng group.id riêng cho từng reader. Nếu cần chia partition giữa các instance và failover tự động, hãy cân nhắc subscribe().

## 5. Manual assignment trong Spring Kafka với @KafkaListener

Spring Kafka hỗ trợ gán partition trực tiếp trong annotation bằng thuộc tính topicPartitions. Khi sử dụng topicPartitions, listener container tạo consumer với assignment đã chỉ định thay vì đăng ký topic bằng group subscription.

Ví dụ listener chỉ nhận partition 0 và 1:

~~~java
@Component
public class OrdersPartitionListener {

    @KafkaListener(
        id = "orders-partition-listener",
        groupId = "orders-manual-reader",
        topicPartitions = @TopicPartition(
            topic = "orders",
            partitions = {"0", "1"}
        )
    )
    public void onOrder(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

Trong ví dụ:

- id xác định listener container để quản lý lifecycle.
- groupId xác định nhóm offset được sử dụng cho consumer.
- topicPartitions chỉ định topic và partition cụ thể.
- Listener chỉ nhận record từ partition đã gán.

Khi cần nhiều topic hoặc partition, có thể khai báo nhiều @TopicPartition:

~~~java
@KafkaListener(
    id = "billing-manual-listener",
    groupId = "billing-manual-reader",
    topicPartitions = {
        @TopicPartition(topic = "orders", partitions = {"0", "2"}),
        @TopicPartition(topic = "refunds", partitions = {"1"})
    }
)
public void onBillingEvent(Object event) {
    billingService.handle(event);
}
~~~

Một endpoint có thể được gán partition từ nhiều topic. Hãy bảo đảm kiểu payload hoặc cách nhận record phù hợp với các topic đó; nếu schema khác nhau, có thể dùng ConsumerRecord hoặc cấu hình listener riêng cho từng loại message.

Trong annotation, topics, topicPattern và topicPartitions là các cách khai báo subscription/assignment khác nhau. Dùng topicPartitions khi cần assignment tĩnh; không khai báo đồng thời như thể chúng là các nguồn partition bổ sung.

## 6. Chỉ định initial offset cho partition

Ngoài danh sách partition, Spring Kafka cho phép khai báo initial offset bằng @PartitionOffset trong @TopicPartition.

Ví dụ:

~~~java
@KafkaListener(
    id = "orders-replay-listener",
    groupId = "orders-replay-reader",
    topicPartitions = @TopicPartition(
        topic = "orders",
        partitionOffsets = {
            @PartitionOffset(partition = "0", initialOffset = "0"),
            @PartitionOffset(partition = "1", initialOffset = "100")
        }
    )
)
public void replayOrder(OrderEvent event) {
    replayService.handle(event);
}
~~~

Trong ví dụ, listener được cấu hình để bắt đầu partition 0 từ offset 0 và partition 1 từ offset 100 theo chính sách initial seek của Spring Kafka.

Cần phân biệt initial offset với offset commit đã tồn tại:

- Consumer group có thể đã có committed offset cho partition.
- auto.offset.reset được dùng khi không có committed offset hợp lệ hoặc offset đã nằm ngoài phạm vi log, tùy cấu hình.
- initialOffset trong TopicPartitionOffset/@PartitionOffset là chỉ dẫn seek khởi đầu cho partition. Hãy kiểm tra cách nó tương tác với committed offset theo phiên bản Spring Kafka đang dùng; đừng giả định auto.offset.reset là cơ chế duy nhất quyết định vị trí bắt đầu.
- Nếu mục tiêu là replay từ đầu một cách có chủ đích, hãy dùng group ID riêng cho job replay hoặc thực hiện quy trình seek/reset offset có kiểm soát.

Không dùng chung group ID của consumer production khi chạy một job replay có thể commit offset về vị trí cũ. Job replay có thể làm thay đổi committed offset mà consumer production đang dựa vào.

### Seek sau khi assignment

Ở Kafka Consumer API, seek() cho phép thay đổi vị trí đọc của một partition đã được assign:

~~~java
TopicPartition partition = new TopicPartition("orders", 0);

consumer.assign(List.of(partition));
consumer.seek(partition, 500L);
~~~

Phải assign partition trước khi seek. Offset cần nằm trong phạm vi log còn tồn tại; nếu offset nhỏ hơn log start offset hoặc lớn hơn vị trí hợp lệ, ứng dụng phải xử lý tình huống tương ứng.

Kafka Consumer cũng hỗ trợ seekToBeginning(), seekToEnd() và position() để điều khiển hoặc kiểm tra vị trí đọc. Khi thao tác trên nhiều partition, hãy xử lý từng partition và không giả định offset giữa các partition có quan hệ với nhau.

## 7. Manual assignment không đồng nghĩa manual offset commit

Đây là hai khái niệm thường bị nhầm:

| Khái niệm | Ý nghĩa | Cơ chế |
|---|---|---|
| Manual partition assignment | Chỉ định consumer đọc partition nào | assign(), @KafkaListener topicPartitions |
| Manual acknowledgement | Listener chủ động báo container rằng record đã xử lý xong | Acknowledgment.acknowledge() |
| Manual offset commit | Ứng dụng chủ động ghi committed offset | commitSync(), commitAsync() |

Một listener dùng topicPartitions vẫn có thể dùng AckMode.RECORD hoặc BATCH để container quản lý commit. Ngược lại, consumer dùng subscribe() vẫn có thể tắt auto commit và commit thủ công.

Ví dụ manual acknowledgement trong Spring Kafka:

~~~java
@KafkaListener(
    id = "orders-manual-ack",
    groupId = "orders-manual-reader",
    topicPartitions = @TopicPartition(
        topic = "orders",
        partitions = {"0"}
    ),
    containerFactory = "manualAckListenerContainerFactory"
)
public void onOrder(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);

    // Chỉ acknowledge sau khi side effect cần thiết hoàn tất.
    acknowledgment.acknowledge();
}
~~~

Factory tương ứng cần được cấu hình acknowledgement mode:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        manualAckListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL
    );

    return factory;
}
~~~

Spring Kafka listener container mặc định quản lý commit offset và tắt Kafka auto-commit nếu ứng dụng không chủ động cấu hình khác. Hãy chọn acknowledgement mode theo cách xử lý record, không chỉ dựa vào việc partition được gán thủ công hay tự động.

Với KafkaConsumer API thuần, có thể tắt enable.auto.commit và gọi commitSync() sau khi xử lý thành công. commitSync() lưu vị trí đọc tiếp theo của consumer, không phải offset của record vừa xử lý. Kafka client quản lý việc chuyển vị trí đọc hiện tại thành offset commit phù hợp.

## 8. Concurrency với manual assignment trong Spring Kafka

Spring Kafka có thể dùng ConcurrentMessageListenerContainer để chạy nhiều consumer con cho một listener endpoint. Khi endpoint dùng topicPartitions, Spring phân phối danh sách partition được chỉ định giữa các consumer con của concurrent container.

Ví dụ một endpoint có sáu partition và concurrency bằng ba:

~~~text
ConcurrentMessageListenerContainer
       |
       +-- Consumer 1: P0, P1
       |
       +-- Consumer 2: P2, P3
       |
       +-- Consumer 3: P4, P5
~~~

Đây là ví dụ minh họa; phân chia thực tế phụ thuộc cấu hình container và số partition được khai báo.

Các điểm cần nhớ:

- Concurrency không tạo thêm partition.
- Nếu concurrency lớn hơn số partition được gán, một số consumer con có thể không có partition để đọc.
- Nếu concurrency nhỏ hơn số partition, một consumer có thể đọc nhiều partition.
- Listener bean có thể được nhiều consumer thread gọi đồng thời; bean cần stateless hoặc thread-safe.
- Việc phân chia nội bộ trong một concurrent container không tạo group rebalance giữa các ứng dụng độc lập.

Nếu chạy nhiều instance ứng dụng, mỗi instance có thể tạo concurrent container riêng. Nếu các instance khai báo cùng tập partition, chúng có thể cùng đọc những partition đó. Cần thiết kế assignment khác nhau theo instance hoặc có bộ điều phối bên ngoài để phân chia quyền sở hữu.

## 9. Quản lý assignment khi ứng dụng scale hoặc restart

Manual assignment thường đi cùng một cấu hình phân vùng tĩnh hoặc một cơ chế điều phối riêng.

Ví dụ ba instance được gán partition theo cấu hình:

| Instance | Partition được giao |
|---|---|
| worker-a | orders-0, orders-1 |
| worker-b | orders-2, orders-3 |
| worker-c | orders-4, orders-5 |

Nếu worker-b dừng, cần có quy trình:

1. Phát hiện worker-b không còn hoạt động.
2. Đảm bảo worker-b không tiếp tục xử lý hoặc commit offset.
3. Chọn worker thay thế.
4. Cập nhật assignment để worker thay thế nhận orders-2 và orders-3.
5. Khởi động hoặc cập nhật container.
6. Theo dõi offset, duplicate và thứ tự xử lý trong thời gian chuyển giao.

Nếu không có fencing hoặc cơ chế xác nhận quyền sở hữu, worker cũ có thể vẫn chạy sau một network partition và cùng xử lý partition với worker mới. Đây là tình huống split-brain ở tầng ứng dụng. Có thể dùng lease, distributed lock có fencing token, orchestration hoặc cơ chế ownership phù hợp để ngăn hai worker cùng có quyền ghi side effect.

### Khi topic tăng partition

Consumer dùng manual assignment không tự nhận partition mới nếu danh sách assignment được khai báo tĩnh. Khi topic tăng partition, cần cập nhật cấu hình và phân phối partition mới cho worker.

Không nên thay đổi partition count mà không đánh giá lại mapping key và assignment. Nếu key có thể được ánh xạ sang partition mới, các record cũ và mới của cùng thực thể có thể nằm ở các partition khác nhau. Điều này ảnh hưởng thứ tự và xử lý state.

### Dừng container trước khi đổi assignment

Với Spring Kafka, assignment được thiết lập khi container khởi tạo. Để thay đổi danh sách partition an toàn, hãy quản lý lifecycle: dừng container, tạo/cập nhật container với assignment mới và khởi động lại theo quy trình. Không gọi KafkaConsumer.assign() trực tiếp từ một thread khác trong khi listener container đang sở hữu consumer.

## 10. Xử lý lỗi và duplicate khi dùng manual assignment

Manual assignment không tự ngăn record được xử lý nhiều lần. Nếu listener đã ghi database nhưng offset chưa commit, record có thể được đọc lại sau restart. Nếu hai worker cùng assign một partition, cả hai có thể xử lý cùng record.

Các biện pháp quan trọng:

- Dùng eventId ổn định và unique constraint/inbox table để deduplicate.
- Chỉ commit offset sau khi side effect cần thiết hoàn tất.
- Xác định một chủ sở hữu partition tại một thời điểm cho mỗi luồng xử lý.
- Có fencing khi chuyển ownership để worker cũ không tiếp tục ghi dữ liệu.
- Theo dõi committed offset và log start offset.
- Kiểm thử restart giữa thời điểm xử lý và commit.
- Xác định cách xử lý record lỗi, retry và dead-letter theo từng partition.

Nếu cần thứ tự, hãy xử lý record trong mỗi partition tuần tự hoặc quản lý rõ các tác vụ bất đồng bộ để offset không vượt qua công việc chưa hoàn tất.

## 11. Kiểm thử manual assignment

Kiểm thử nên xác nhận cả assignment thực tế và hành vi offset.

Các kịch bản tích hợp:

- Tạo topic có nhiều partition, assign consumer vào một partition và xác nhận chỉ nhận record từ partition đó.
- Gán hai partition cho một consumer và xác nhận consumer đọc cả hai.
- Gán cùng partition cho hai consumer độc lập để quan sát hành vi đọc trùng và chứng minh ứng dụng phải quản lý ownership.
- Dùng group ID riêng cho job replay để xác nhận job không thay đổi offset production.
- Dùng @KafkaListener topicPartitions và kiểm tra container nhận đúng partition.
- Kiểm tra initialOffset khi group chưa có committed offset.
- Xử lý record thành công nhưng dừng tiến trình trước commit, sau đó khởi động lại để xác nhận handler idempotent.
- Tăng partition count và xác nhận consumer manual assignment không tự nhận partition mới nếu chưa cập nhật cấu hình.
- Dừng một worker và thực hiện chuyển assignment bằng cơ chế điều phối của ứng dụng.

Trong test, không chỉ kiểm tra listener có được gọi. Hãy kiểm tra topic, partition, offset, group ID và assignment thực tế để tránh nhầm consumer đang đọc partition khác.

## 12. Quan sát và vận hành

Các tín hiệu nên theo dõi:

- Partition được gán cho từng instance/container.
- Consumer lag theo group và partition.
- Committed offset và log start/end offset.
- Số record xử lý, lỗi, retry và duplicate.
- Thời gian xử lý từng partition.
- Trạng thái ownership/lease của worker nếu có bộ điều phối ngoài.
- Sự kiện restart, chuyển assignment và khoảng thời gian partition không có consumer xử lý.

Manual assignment không tự tạo rebalance event như group-managed subscription. Vì vậy, cần có metric hoặc log riêng để biết assignment hiện tại và thời điểm chuyển quyền sở hữu.

## 13. So sánh manual assignment và subscribe

| Tiêu chí | subscribe() | assign() |
|---|---|---|
| Ai quyết định partition? | Group coordinator/assignor | Ứng dụng |
| Tự động rebalance | Có | Không |
| Tự phân phối khi member join/leave | Có | Không |
| Tự nhận partition mới theo topic subscription | Có, sau metadata/group rebalance | Không nếu assignment tĩnh chưa cập nhật |
| Kiểm soát partition cụ thể | Thông qua assignor hoặc subscription pattern | Trực tiếp |
| Phải quản lý ownership giữa các instance | Chủ yếu do consumer group | Ứng dụng/bộ điều phối |
| Phù hợp | Consumer group cần scale và failover tự động | Worker/job có assignment được kiểm soát bên ngoài |

Chọn subscribe() khi cần Kafka quản lý việc chia partition và rebalance. Chọn assign() khi ứng dụng có lý do rõ ràng để sở hữu assignment và có cơ chế quản lý vòng đời, failover, ownership.

## 14. Checklist trước khi triển khai

- [ ] Đã xác định vì sao cần manual assignment thay vì subscribe().
- [ ] Danh sách topic/partition của từng instance được quản lý rõ ràng.
- [ ] Không có hai worker cùng sở hữu partition ngoài chủ đích.
- [ ] group.id được chọn đúng mục đích lưu offset.
- [ ] Job replay dùng group ID riêng nếu không muốn tác động offset production.
- [ ] Initial offset và auto.offset.reset được hiểu đúng.
- [ ] Manual assignment được phân biệt với manual acknowledgement/commit.
- [ ] Listener/container có acknowledgement mode phù hợp.
- [ ] Listener bean an toàn khi concurrency lớn hơn một.
- [ ] Có quy trình chuyển ownership khi worker lỗi hoặc restart.
- [ ] Có cơ chế fencing hoặc lease khi cần ngăn worker cũ tiếp tục xử lý.
- [ ] Đã kiểm thử duplicate, offset commit, partition tăng và chuyển assignment.
- [ ] Có log/metric về assignment, lag và ownership.

## Kết luận

Manual partition assignment cho phép ứng dụng chỉ định chính xác consumer sẽ đọc partition nào thông qua KafkaConsumer.assign() hoặc Spring Kafka @KafkaListener topicPartitions. Cách này không tham gia cơ chế tự động phân phối và rebalance của consumer group; ứng dụng phải tự quản lý ownership, scale, failover và thay đổi partition. group.id vẫn có thể dùng để lưu committed offset, nhưng không đảm bảo các consumer manual assign sẽ chia partition độc quyền cho nhau. Hãy phân biệt assignment với acknowledgement/commit, dùng idempotent handler và chỉ chọn manual assignment khi hệ thống có cơ chế điều phối partition rõ ràng.

