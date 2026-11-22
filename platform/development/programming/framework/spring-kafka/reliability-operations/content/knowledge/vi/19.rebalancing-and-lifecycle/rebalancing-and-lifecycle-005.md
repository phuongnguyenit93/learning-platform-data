# Commit trước rebalance trong Spring Kafka

Trong Kafka consumer group, **rebalance** là quá trình phân phối lại các partition cho các consumer khi thành viên tham gia/rời nhóm, topic thay đổi số partition hoặc group cần điều chỉnh assignment. Một consumer có thể đang xử lý các record của partition P0 rồi được yêu cầu trả P0 cho consumer khác. Nếu những record đã xử lý **chưa được commit offset**, consumer mới có thể đọc lại chúng. Nếu commit **quá sớm**, trước khi side effect nghiệp vụ hoàn tất, hệ thống có thể bỏ sót xử lý.

**Commit trước rebalance** nghĩa là tận dụng giai đoạn partition được thu hồi (*revocation*) để hoàn tất công việc an toàn và commit những offset thực sự đủ điều kiện trước khi chuyển quyền sở hữu partition. Trong Spring Kafka, listener container đã có cơ chế quản lý offset và commit khi rebalance; ứng dụng có thể dùng **ConsumerAwareRebalanceListener** để thực hiện công việc cần thiết trước và sau bước commit của container.

Điều cần nhớ: không phải rebalance nào cũng có một giai đoạn revoke an toàn. Khi consumer mất quyền sở hữu partition do hết timeout hoặc bị fenced, callback **onPartitionsLost** có thể xuất hiện thay vì một cơ hội commit thông thường. Vì thế, commit trước rebalance giúp **giảm redelivery trong những trường hợp bình thường**, nhưng không bảo đảm không có duplicate khi crash, mất mạng hoặc mất quyền sở hữu bất ngờ.

## 1. Vì sao offset commit quan trọng khi partition đổi chủ?

Kafka duy trì committed offset theo **consumer group, topic và partition**. Giá trị được commit là vị trí record tiếp theo nên đọc, không phải số record đã xử lý trong một JVM.

Ví dụ:

~~~text
Topic: orders.events, partition 2

offset 100  --> Event A --> xử lý thành công
offset 101  --> Event B --> xử lý thành công
offset 102  --> Event C --> xử lý thành công
offset 103  --> Event D --> chưa xử lý
                       |
                       v
Nếu A, B, C đã hoàn tất:
  next offset an toàn = 103
  commit offset = 103
~~~

Nếu consumer A đang sở hữu partition 2 rồi rebalance giao partition cho consumer B:

- **Commit thành công offset 103:** B bắt đầu từ offset 103 theo vị trí đã commit, không cần đọc lại A/B/C.
- **Chưa commit tiến độ mới:** B bắt đầu từ committed offset cũ, có thể đọc lại A/B/C.
- **Commit offset 104 quá sớm khi D chưa xử lý:** B có thể bỏ qua D, dẫn tới mất tác động nghiệp vụ.

Do đó, mục tiêu không phải "commit offset lớn nhất đã poll" mà là **commit offset kế tiếp sau dãy record đã xử lý an toàn, liên tục, của từng partition**.

## 2. Rebalance xảy ra khi nào?

Những tình huống thường gây rebalance:

1. Một consumer mới tham gia cùng consumer group.
2. Một consumer chủ động stop hoặc đóng ứng dụng.
3. Consumer mất liên lạc với group coordinator.
4. Consumer không poll đúng hạn theo max.poll.interval.ms.
5. Số partition hoặc metadata topic thay đổi.
6. Rolling deployment, autoscaling hoặc Kubernetes pod termination làm group membership thay đổi.
7. Group protocol hoặc partition assignment strategy yêu cầu điều chỉnh assignment.

~~~text
Ban đầu:
  Consumer A: P0, P1
  Consumer B: P2, P3

Scale out:
  Consumer C tham gia
          |
          v
Group rebalance
          |
          +--> Consumer A: P0
          +--> Consumer B: P2
          +--> Consumer C: P1, P3
~~~

Đây là ví dụ phân phối có thể xảy ra, không phải kết quả assignment chắc chắn. Tùy assignor, Kafka có thể thu hồi toàn bộ partitions (*eager rebalance*) hoặc chỉ thu hồi một số partition cần chuyển (*cooperative rebalance*).

Commit trước khi trả partition giúp consumer mới tiếp tục gần nhất với tiến độ thật của consumer cũ, nhưng quyền commit còn phụ thuộc việc consumer cũ có đang là thành viên hợp lệ của group hay không.

## 3. Phân biệt revoke, lost và assigned

Kafka consumer rebalance API có các lifecycle callbacks quan trọng:

| Callback | Khi nào | Có nên commit? |
|---|---|---|
| onPartitionsRevoked | Consumer được thông báo các partition sắp bị thu hồi | Có thể là cơ hội cuối để commit tiến độ hợp lệ khi còn sở hữu partition |
| onPartitionsLost | Partition đã bị mất quyền sở hữu; không phải revoke bình thường | **Không nên dựa vào việc commit**; có thể đã bị consumer khác tiếp quản |
| onPartitionsAssigned | Consumer nhận assignment mới | Khởi tạo state và bắt đầu/tiếp tục xử lý |
| Spring onPartitionsRevokedBeforeCommit | Hook Spring Kafka trước bước commit pending offsets của container | Hoàn tất/flush state cần thiết trước khi container commit, nếu an toàn |
| Spring onPartitionsRevokedAfterCommit | Hook Spring Kafka sau bước container xử lý commit khi revoke | Ghi nhận và giải phóng resource của partition đã được revoke |

Một consumer thường nhận callback revoke trong lúc poll xử lý rebalance. Tuy nhiên, khi consumer đã mất ownership vì timeout hoặc fencing, không thể giả định nó vẫn có quyền commit những offset của partition đó.

**onPartitionsLost không phải phiên bản khác tên của onPartitionsRevoked.** Trong trường hợp lost, cơ hội commit có thể đã qua. Hệ thống phải chấp nhận redelivery, dùng idempotency và kiểm soát stale writes.

## 4. Spring Kafka listener container quản lý commit như thế nào?

Trong Spring Kafka, listener container gọi KafkaConsumer.poll(), chuyển record tới listener và theo dõi offset theo **AckMode**. Khi container quản lý commit, ứng dụng không nên tự gọi consumer.commitSync() trong từng listener method trừ khi đã xây một chính sách đặc biệt và hiểu hoàn toàn tác động đến state của container.

Các mode thường gặp:

| AckMode | Thời điểm tiến độ được commit thông thường | Ý nghĩa khi rebalance |
|---|---|---|
| RECORD | Sau khi listener xử lý thành công từng record | Cửa sổ record đã xử lý nhưng chưa commit thường nhỏ hơn |
| BATCH | Sau khi các record của poll đã được xử lý | Có thể còn nhiều record đã xử lý nhưng chưa tới mốc commit |
| TIME | Theo ngưỡng thời gian ackTime | Có offset đang chờ khi rebalance xảy ra |
| COUNT | Theo ngưỡng ackCount | Có thể tích lũy nhiều record chưa commit |
| COUNT_TIME | Khi tới ngưỡng số lượng hoặc thời gian | Có thể có pending offsets trước khi tới ngưỡng |
| MANUAL | Listener gọi acknowledge; container thực hiện commit theo semantics manual/batch | Chỉ những tiến độ đã acknowledge phù hợp mới được commit |
| MANUAL_IMMEDIATE | Acknowledge trên consumer thread có thể commit ngay | Cần kiểm soát thread và thứ tự acknowledge |

Trong các đường rebalance bình thường, Spring Kafka listener container có logic commit pending offsets theo chính sách của nó trước khi partition bị thu hồi. Việc thêm custom rebalance listener **không có nghĩa phải tự commit lần thứ hai**. Thay vào đó, hãy dùng hook phù hợp để hoàn tất resource/flush state trước lúc container xử lý commit.

Đặc biệt, nếu listener method trả về trước khi side effect thực sự hoàn tất do đẩy sang executor async, container có thể xem record đã xử lý xong quá sớm. Commit trước rebalance khi đó cũng **không an toàn**, vì vấn đề nằm ở boundary của listener.

## 5. Thứ tự rebalance callbacks trong Spring Kafka

Spring Kafka có interface **ConsumerAwareRebalanceListener**, mở rộng khả năng của ConsumerRebalanceListener bằng cách cung cấp consumer instance và những callback phù hợp với chu kỳ commit của container.

Một chu trình revoke khái quát:

~~~text
KafkaConsumer.poll() phát hiện rebalance
               |
               v
Spring Kafka container
               |
               +--> onPartitionsRevokedBeforeCommit(...)
               |       |
               |       +--> ứng dụng có thể flush state
               |            an toàn cho các partition liên quan
               |
               +--> Container commit pending offsets
               |       theo ack/error-handling policy
               |
               +--> onPartitionsRevokedAfterCommit(...)
               |       |
               |       +--> giải phóng partition-local resources
               |
               v
Kafka group coordinator phân phối lại
               |
               v
onPartitionsAssigned(...) trên consumer được giao partition
~~~

Sơ đồ là luồng thông thường theo callback API Spring Kafka. Các tình huống lỗi commit, partition lost, phiên bản thư viện và cơ chế rebalance có thể khiến luồng thực tế khác với đường happy path. Callback sau commit **không phải một chứng thư rằng mọi side effect bên ngoài Kafka đã thành công**.

Các quy tắc vận hành:

- Callback chạy trong vòng đời consumer/container; không thực hiện I/O dài hoặc block vô hạn.
- Chỉ tác động đến các partition được callback cung cấp khi dùng cooperative rebalancing.
- Nếu cần flush state, phải đảm bảo nó thật sự được lưu bền vững trước khi cho container commit.
- Khi lost partition, không tiếp tục thực hiện side effect hoặc commit như thể còn sở hữu partition.

## 6. Ví dụ cấu hình ConsumerAwareRebalanceListener

Ví dụ dùng Java configuration và AckMode.RECORD:

~~~java
@Configuration
public class OrderKafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            PartitionStateService partitionStateService) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );

        factory.getContainerProperties().setConsumerRebalanceListener(
                new ConsumerAwareRebalanceListener() {

                    @Override
                    public void onPartitionsRevokedBeforeCommit(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        partitionStateService.flushCompleted(partitions);
                    }

                    @Override
                    public void onPartitionsRevokedAfterCommit(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        partitionStateService.release(partitions);
                    }

                    @Override
                    public void onPartitionsAssigned(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        partitionStateService.initialize(partitions);
                    }

                    @Override
                    public void onPartitionsLost(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        partitionStateService.invalidate(partitions);
                    }
                }
        );

        return factory;
    }
}
~~~

Đây là ví dụ về cấu trúc Spring listener container factory; PartitionStateService là một service của ứng dụng. Các phương thức flushCompleted, release, initialize, invalidate cần được cài đặt theo business state và thread-safety contract thực tế. API callback cụ thể phụ thuộc phiên bản Spring Kafka, đặc biệt đối với callback partitions lost.

Ý nghĩa:

- **BeforeCommit:** chỉ flush những kết quả đã hoàn tất và đủ điều kiện commit; không đánh dấu công việc async chưa xong là thành công.
- **AfterCommit:** cleanup state gắn với partition được revoke.
- **Assigned:** tạo lại caches hoặc partition-local state cần thiết.
- **Lost:** bỏ quyền thao tác vào partition đã mất; không dùng callback này để ép một commit mới.

Nếu service không có buffered state cần flush, callback trước commit có thể chỉ ghi metrics/log. Không cần thiết thêm một custom listener chỉ để gọi commitSync khi container đã làm việc đó.

## 7. Cần phân biệt flush business state và commit Kafka offset

"Flush trước rebalance" có thể mang nhiều nghĩa:

- Flush bộ đệm ghi database, đảm bảo transaction DB đã commit.
- Chờ những record đang thực thi được xác nhận hoàn tất.
- Flush producer gửi output Kafka.
- Commit offset consumer group vào Kafka.

Những việc này **không tự động tương đương**.

Ví dụ Kafka listener dùng một buffer để gom nhiều record trước khi ghi vào database. Nếu listener trả về success khi record mới chỉ nằm trong RAM, container có thể commit offset dù database chưa lưu dữ liệu. Khi rebalance hoặc crash, dữ liệu trong RAM biến mất.

~~~text
Listener nhận record
       |
       v
Ghi vào buffer trong RAM
       |
       v
Listener trả về bình thường
       |
       v
Spring Kafka có thể đánh dấu record đã xử lý
       |
       v
Commit offset trong rebalance
       |
       v
Process crash, buffer mất
       |
       v
Không còn record để đọc lại
~~~

Nếu cần buffer, phải xây cơ chế ghi nhận hoàn tất phù hợp: chỉ acknowledge/return success sau khi side effect bền vững, hoặc quản lý acknowledgement thủ công theo tiến độ xử lý thật. Không chỉ trông chờ onPartitionsRevokedBeforeCommit để cứu một listener đã báo thành công quá sớm.

Commit đúng offset cần dựa trên **tiến độ hoàn tất liên tục** theo từng partition, không phải record có offset lớn nhất đã bắt đầu xử lý.

## 8. Manual acknowledgment và rebalance

Ví dụ một record listener dùng AckMode.MANUAL_IMMEDIATE:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "manualAckFactory"
)
public void onOrder(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.applyIdempotently(record.value());

    // Chỉ acknowledge sau khi side effect đã được commit an toàn.
    acknowledgment.acknowledge();
}
~~~

Factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
manualAckFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL_IMMEDIATE
    );

    return factory;
}
~~~

Với MANUAL_IMMEDIATE, acknowledgement trên consumer thread có thể commit ngay; khi gọi từ thread khác, hành vi commit có thể được container trì hoãn theo implementation. Vì vậy, **không giả định một callback bất đồng bộ đã gọi acknowledge là offset đã commit tức thì**.

Nếu dùng AckMode.MANUAL, listener gọi acknowledge nhưng container thực hiện commit theo semantics manual/batch. Khi rebalance, pending acknowledgments và consumer position cần được container xử lý theo policy của phiên bản.

Trong cả hai trường hợp:

1. Chỉ acknowledge sau khi hoàn thành side effect nghiệp vụ.
2. Không acknowledge record lỗi chỉ để giảm consumer lag.
3. Không tự tăng offset đã commit vượt record còn chưa hoàn tất.
4. Không dùng consumer object từ worker thread ngoài contract thread-safety.
5. Khi shutdown/revoke, tránh để công việc async tiếp tục ghi stale state sau khi partition đã chuyển chủ.

Nếu nghiệp vụ yêu cầu xử lý bất đồng bộ thực sự, cần một mô hình quản lý completion và ack theo thứ tự, với cơ chế partition ownership khi rebalance. Không nên giải quyết bằng cách trực tiếp commit offset của "task hoàn tất nhanh nhất".

## 9. Ví dụ chọn offset an toàn theo từng partition

Giả sử listener dispatch record của partition 0 tới executor:

~~~text
offset 10 --> xử lý hoàn tất
offset 11 --> xử lý chưa hoàn tất
offset 12 --> xử lý hoàn tất

Offset đã nhận:       10, 11, 12
Offset hoàn tất:      10,     12
Offset được commit an toàn: 11
~~~

Nếu commit 13 vì record 12 đã xong, record 11 sẽ bị bỏ qua khi consumer khác tiếp quản. Ngưỡng an toàn là **offset sau dãy hoàn tất liên tục** bắt đầu từ committed position cũ, trong ví dụ là 11.

Nếu record 11 sau đó thành công, có thể ghi nhận tiến độ tới 13.

~~~text
Before:
  committed = 10
  complete  = {10, 12}
  pending   = {11}
  safe next = 11

After 11 completes:
  complete  = {10, 11, 12}
  safe next = 13
~~~

Spring Kafka có các cơ chế acknowledgement và xử lý out-of-order acknowledgments trong một số phiên bản, nhưng mỗi cơ chế có yêu cầu riêng và có thể pause consumer khi còn gaps. Nếu tự xây executor, người phát triển chịu trách nhiệm đảm bảo ordering, completion state và quyền sở hữu partition.

## 10. Tại sao không commitSync bừa trong callback?

Kafka Consumer API cho phép:

~~~java
consumer.commitSync(
        Map.of(
                new TopicPartition("orders.events", 0),
                new OffsetAndMetadata(103L)
        )
);
~~~

Đây chỉ là ví dụ Kafka client về **commit offset 103 cho partition 0**. Để lệnh đúng, 103 phải thực sự là next offset sau các record đã hoàn tất liên tục, và consumer phải còn quyền sở hữu partition trong group hợp lệ.

Không nên copy đoạn này vào onPartitionsRevokedBeforeCommit của Spring Kafka mà không có một custom offset-management design. Nếu container đã theo dõi pending offsets, một commitSync bên ngoài có thể:

- Commit offset cao hơn các record thực tế đã hoàn tất.
- Commit trùng hoặc chồng lên state mà container sẽ commit ngay sau callback.
- Gây khó khăn phân tích offset nếu acknowledgement state của container khác với state tự quản lý.
- Thất bại do rebalance/generation mismatch.
- Tăng thời gian callback và ảnh hưởng ổn định consumer group.

**Ưu tiên để Spring Kafka container commit những offset mà nó theo dõi**. Custom ConsumerRebalanceListener nên tập trung vào lifecycle và state application trừ khi chủ động quản lý toàn bộ offset logic.

## 11. CommitSync so với commitAsync khi gần rebalance

Kafka consumer hỗ trợ cả synchronous và asynchronous offset commit.

| Thuộc tính | commitSync | commitAsync |
|---|---|---|
| Phản hồi cho caller | Chờ broker trả kết quả hoặc lỗi | Trả về trước, callback nhận kết quả |
| Đảm bảo biết kết quả tại thời điểm tiếp tục | Có khi lời gọi kết thúc thành công | Không, phải theo dõi callback |
| Chi phí latency | Có thể cao hơn | Thường ít chặn luồng hơn |
| Lỗi commit | Ném exception cho caller | Báo trong callback |
| Dùng lúc revoke | Dễ xác nhận offset đã commit trước khi trả partition | Có nguy cơ callback chưa về khi ownership thay đổi |

Trong một consumer tự quản lý offsets bằng Kafka client, chiến lược thường là commitAsync định kỳ và commitSync trong revoke/shutdown khi còn quyền sở hữu hợp lệ, theo dõi lỗi của cả hai. Tuy nhiên, với Spring Kafka listener container, **chính container** đã có config syncCommits, commit timeout, AckMode và logic rebalance commit; không tự áp dụng thêm lệnh commitSync vào callback như một quy tắc chung.

Spring Kafka có thể được cấu hình sync commits hoặc async commits theo API ContainerProperties, ví dụ:

~~~java
factory.getContainerProperties().setSyncCommits(true);
~~~

Hãy xác nhận cách cấu hình và timeout phù hợp với Spring Kafka version đang dùng. Khi dùng async commit, cần theo dõi callback/commit errors; một lời gọi commit được gửi đi không phải bằng chứng offset đã được ghi thành công.

## 12. Đối phó CommitFailedException

CommitFailedException có thể xuất hiện khi offset commit không thể được hoàn tất theo consumer group protocol, ví dụ consumer đã không còn là thành viên hợp lệ do rebalance hoặc generation thay đổi.

Một chuỗi sự kiện:

~~~text
Consumer A xử lý lâu
        |
        v
Vượt max.poll.interval.ms
        |
        v
Group rebalance
        |
        v
Partition chuyển sang Consumer B
        |
        v
Consumer A cố commit offset
        |
        v
CommitFailedException / không có quyền commit hợp lệ
~~~

Khi gặp lỗi này:

- Đừng coi offset đã commit.
- Đừng ép ghi offset cao hơn nếu không chắc tất cả side effect đã hoàn tất.
- Không cố "chiếm lại" partition bằng cách tiếp tục dùng consumer cũ ngoài group membership.
- Cho container xử lý lifecycle/rebalance theo contract.
- Dùng idempotency vì consumer B có thể đọc lại record.
- Xác định nguyên nhân: listener quá lâu, max.poll.interval, blocking retry, lỗi broker/network, rebalance quá thường xuyên.

CommitFailedException không phải loại lỗi mà retry vô hạn với cùng consumer state luôn có thể giải quyết. Nó có thể cho biết consumer đã mất quyền sở hữu/generation cần thiết. Phục hồi thường là chấp nhận assignment mới và để record được giao lại theo committed position.

## 13. onPartitionsLost: khi không còn cơ hội commit

Một consumer có thể mất partition do timeout hoặc giao thức group trước khi callback revoke thông thường được thực hiện đúng lúc.

~~~text
Consumer A sở hữu P1
       |
       +--> Mạng mất hoặc xử lý quá lâu
       |
       +--> Coordinator coi A không còn hợp lệ
       |
       v
P1 chuyển sang Consumer B
       |
       v
A nhận biết partition lost
       |
       v
A không còn là owner hợp lệ của P1
~~~

Trong onPartitionsLost:

1. Đánh dấu partition-local ownership không còn hợp lệ.
2. Dừng hoặc hủy các tác vụ async còn dùng dữ liệu của partition đó khi có thể.
3. Không tiếp tục emit side effect dựa trên assumption mình vẫn sở hữu partition.
4. Không cố commit offset như trong onPartitionsRevoked.
5. Để consumer mới xử lý lại từ committed offset.
6. Dựa vào idempotency và version checks để bảo vệ external systems.

Nếu một async task không thể bị hủy và vẫn ghi vào database sau khi partition lost, có thể có **hai consumer cùng tạo side effect** trong một khoảng ngắn: consumer B mới và stale task từ A. Trường hợp này cần phân quyền theo version/fencing token, unique event ID hoặc lock bền vững tại external resource, không chỉ Kafka offset commit.

## 14. Fencing stale worker khi partition chuyển chủ

Ví dụ một listener dispatch việc ghi database vào executor, rồi partition chuyển từ consumer A sang B. A có thể tiếp tục hoàn tất task cũ trong khi B đã xử lý lại cùng event.

Để tránh stale worker ghi đè trạng thái mới, có thể dùng:

- Unique constraint trên eventId để chặn cùng event thực thi side effect hai lần.
- Optimistic locking với aggregate version.
- Lease hoặc fencing token được lưu tại hệ thống đích.
- State machine yêu cầu chuyển trạng thái đúng phiên bản.
- Phân vùng công việc chỉ theo consumer thread và chờ hoàn tất trong thời gian hợp lý.
- Dừng executor/tasks theo các partition revoked/lost.

Ví dụ optimistic update:

~~~sql
UPDATE orders
SET status = :new_status,
    version = :next_version
WHERE order_id = :order_id
  AND version = :expected_version;
~~~

Nếu record cũ tới muộn, câu UPDATE không được áp dụng khi current version khác expected version. Cần phân loại zero updated rows: event đã áp dụng, event đến sai thứ tự hay dữ liệu thiếu; không retry vô hạn một state conflict cố định.

Điều này bảo vệ trạng thái database **ngoài Kafka**, nơi transaction offset không bao trùm.

## 15. Cooperative và eager rebalance

Kafka có các assignment strategies khác nhau. Hai mô hình thường cần phân biệt:

**Eager rebalance**

- Các consumers có thể phải thu hồi nhiều hoặc toàn bộ partitions trước khi nhận assignment mới.
- Window ngừng xử lý có thể lớn hơn.
- Giai đoạn revoke thường liên quan tới nhiều partition.

**Cooperative rebalance**

- Các consumer có thể chỉ thu hồi những partition cần chuyển chủ.
- Những partition vẫn được giữ có thể tiếp tục thuộc consumer hiện tại.
- Callback revoke có thể chỉ cung cấp **subset** partitions.

Ví dụ:

~~~text
Consumer A trước rebalance:
  P0, P1, P2

Cooperative rebalance cần chuyển P2 sang B:
  revoked from A: {P2}
  retained by A:  {P0, P1}
~~~

Vì vậy, callback nên xử lý chính xác Collection<TopicPartition> được truyền vào, không cleanup/flush toàn bộ global state nếu chỉ một partition bị revoke. Một ứng dụng có partition-local buffers hoặc caches cần có key theo TopicPartition và lifecycle riêng.

Đừng giả định một callback sẽ được gọi đúng một lần cho toàn bộ group rebalance. Theo Kafka protocol, group membership và implementation, callbacks có thể lặp hoặc có collection rỗng; code nên idempotent.

## 16. Spring Kafka concurrency và partition ownership

ConcurrentMessageListenerContainer tạo nhiều child containers, mỗi child có KafkaConsumer riêng. Concurrency làm tăng mức song song theo partition nhưng không biến cùng partition thành nhiều owners cùng lúc trong một consumer group.

~~~text
Topic orders.events: P0 P1 P2 P3 P4 P5
Concurrency: 3

Child Consumer 1: P0, P1
Child Consumer 2: P2, P3
Child Consumer 3: P4, P5
~~~

Đây là một partition assignment minh họa. Khi một child consumer rebalance, lifecycle callback của nó liên quan đến partition mà child đó đang xử lý. Đừng dùng một biến global như currentOffset để quản lý tiến độ của tất cả partitions.

Một PartitionStateService nên lưu theo TopicPartition:

~~~text
TopicPartition("orders.events", 0) -> safe next offset 101
TopicPartition("orders.events", 1) -> safe next offset 205
TopicPartition("orders.events", 2) -> safe next offset  77
~~~

Nếu state dùng chung giữa nhiều child consumers, cần thread-safety và fencing ownership. Khi partition chuyển child, state cũ không được tiếp tục thay đổi offset hoặc side effect như thể còn assignment.

Tăng concurrency quá số partition không mang lại thêm parallelism hữu ích cho topic đó, đồng thời vẫn phải xử lý rebalance lifecycle.

## 17. Shutdown có kiểm soát trước rolling deployment

Một rolling deployment Kubernetes có thể gửi SIGTERM cho pod đang chạy Kafka listener. Đường shutdown bình thường là cơ hội để listener container dừng nhận dữ liệu, hoàn tất công việc đang xử lý và commit offset hợp lệ trước khi đóng consumer.

~~~text
Deployment bắt đầu thay pod
         |
         v
SIGTERM tới pod cũ
         |
         v
Spring application context đóng
         |
         v
Listener container stop
         |
         +--> ngừng lấy công việc mới
         +--> hoàn tất/chờ công việc theo lifecycle
         +--> commit offsets an toàn theo policy
         |
         v
Consumer đóng / rời group
         |
         v
Partition được assign lại
~~~

Đây là đường **graceful shutdown**, không phải điều chắc chắn trong mọi tình huống. OOM kill, node mất điện, kill -9 hoặc grace period hết hạn có thể chặn các bước cleanup/commit cuối.

Các biện pháp:

- Đặt terminationGracePeriodSeconds đủ phù hợp với thời gian xử lý record và thời gian đóng container.
- Không giữ listener chạy các thao tác blocking không giới hạn.
- Tạo cơ chế drain công việc async trước khi container dừng, nếu cần.
- Theo dõi shutdown timeout, commit errors và rebalance lag.
- Sử dụng idempotency để chịu crash không graceful.
- Không cố commit offset sau khi consumer đã đóng hoặc mất assignment.

Đừng chỉ tăng grace period rồi bỏ qua giới hạn xử lý/commit thực tế. Hệ thống vẫn phải an toàn khi shutdown bị cắt ngang.

## 18. Static membership giúp gì?

Kafka hỗ trợ static membership qua group.instance.id nhằm giảm churn của group membership trong một số chu kỳ restart ngắn khi cấu hình và protocol phù hợp.

Ý nghĩa:

- Có thể giảm số lần group phải phân phối lại partition trong một số trường hợp.
- Có thể hữu ích khi rolling deployment có các consumer identities ổn định.
- Không loại bỏ hoàn toàn rebalance.
- Không thay thế commit offset hoặc idempotency.
- Nếu consumer mất membership hay partition bị thu hồi thật sự, vẫn phải xử lý revoke/lost chính xác.

Khi dùng concurrency, mỗi child consumer phải có danh tính group.instance.id hợp lệ/duy nhất theo cơ chế Spring Kafka và Kafka client tương ứng. Không copy cùng một ID tĩnh cho nhiều consumer đồng thời.

Static membership là công cụ giảm rebalance không cần thiết, **không phải cơ chế đảm bảo exactly-once side effect**.

## 19. Rebalance và Kafka transactions

Với transactional listener container, input offsets và Kafka output records có thể được commit cùng một Kafka transaction. Nếu listener thất bại hoặc transaction bị abort, output chưa commit không hiện với read_committed consumers và offsets không commit trong transaction đó.

~~~text
Consumer xử lý event E trong Kafka transaction
        |
        +--> KafkaTemplate.send(output)
        |
        +--> Listener thành công
        |       |
        |       v
        |    Input offset vào transaction
        |       |
        |       v
        |    Commit transaction
        |
        +--> Exception / abort
                |
                +--> Output không commit
                +--> Input offset không commit
                |
                v
         AfterRollbackProcessor
                |
                v
           Seek / redelivery
~~~

Khi rebalance, transaction có thể thất bại hoặc producer bị fenced nếu group ownership/generation không còn phù hợp. Không nên cố commit offsets thủ công bên ngoài Kafka transaction để “cứu” một lần xử lý mà transaction đã abort.

Điều cần bảo vệ là **đúng transaction boundary**: listener hoàn tất, output Kafka, input offsets và exception propagation theo Spring Kafka container.

Nếu listener còn update database hoặc gọi HTTP, Kafka rollback không tự undo side effect đó. Vẫn cần transactional inbox/outbox hoặc idempotency.

## 20. Commit trước rebalance không tạo exactly-once cho database

Giả sử một record được dùng để cập nhật database:

~~~text
Consumer A xử lý event E
        |
        v
Database COMMIT thành công
        |
        v
Consumer A bị crash trước Kafka offset commit
        |
        v
Consumer B nhận partition
        |
        v
Consumer B đọc lại event E
        |
        v
Database có thể bị update lần nữa
~~~

Rebalance callback không có cơ hội chạy khi A bị crash đột ngột. Vì thế, nếu mục tiêu là effect chỉ áp dụng một lần, cần idempotent consumer:

~~~java
@Transactional
public void process(OrderCreated event) {

    boolean firstTime = processedEvents.insertIfAbsent(
            "order-projector",
            event.eventId()
    );

    if (!firstTime) {
        return;
    }

    orderRepository.applyCreated(event);
}
~~~

insertIfAbsent phải dùng atomic insert/unique constraint và cùng database transaction với orderRepository.applyCreated. Nếu event đã xử lý, method có thể trả về bình thường để Spring Kafka container commit offset mà không tạo side effect thứ hai.

Như vậy, **commit trước rebalance giảm xác suất đọc lại**, còn **idempotency bảo đảm việc đọc lại không làm sai kết quả nghiệp vụ**.

## 21. Tình huống commit quá sớm gây mất dữ liệu

Một listener có thể đẩy công việc vào executor rồi trả về:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {

    executor.execute(() -> orderService.apply(event));

    // Listener trả về trước khi executor hoàn thành.
}
~~~

Với container dùng AckMode.RECORD, listener trả về bình thường có thể được coi là xử lý xong record. Offset có thể commit trong lúc task thực sự chưa hoàn tất. Sau đó rebalance hoặc crash làm task mất, consumer mới không còn đọc lại record vì offset đã tiến.

Giải pháp không phải thêm commitSync vào revoke callback. Cần thay đổi completion contract:

- Xử lý đồng bộ tới khi side effect bền vững rồi mới return.
- Hoặc dùng một cơ chế async acknowledgement được Spring Kafka hỗ trợ và quản lý đủ trạng thái completion/revocation.
- Hoặc lưu công việc vào durable queue/database trước khi coi record Kafka đã hoàn tất.
- Không trả về success chỉ vì đã submit một Runnable vào RAM.

Đây là vấn đề reliability lớn hơn lựa chọn sync hay async offset commit.

## 22. Tình huống commit thất bại sau side effect thành công

Một tình huống khác:

~~~text
Listener xử lý DB thành công
         |
         v
DB commit thành công
         |
         v
Rebalance callback / container commit Kafka offset
         |
         v
CommitFailedException
         |
         v
Partition được giao cho Consumer B
         |
         v
Record có thể đọc lại
~~~

Không nên cố ép Kafka offset tiến bằng mọi giá. Nếu consumer A không còn quyền commit hợp lệ, nó phải dừng thao tác theo assignment cũ. Consumer B đọc lại và dùng eventId để xác định DB effect đã được thực hiện.

Hướng vận hành:

1. Ghi log commit error với group/topic/partition/offset nhưng không lộ payload nhạy cảm.
2. Theo dõi consumer group membership và rebalance count.
3. Kiểm tra listener processing time và max.poll.interval.ms.
4. Kiểm tra network/coordinator lỗi nếu có.
5. Đảm bảo idempotent xử lý redelivery.
6. Tránh retry commit vô hạn bằng consumer đã mất quyền sở hữu.

## 23. So sánh các thời điểm commit

| Thời điểm | Ưu điểm | Rủi ro |
|---|---|---|
| Sau từng record xử lý thành công (RECORD) | Cửa sổ duplicate nhỏ hơn | Commit thường xuyên |
| Sau mỗi poll batch hoàn tất (BATCH) | Giảm commit overhead | Nhiều record đã xử lý có thể chưa commit |
| Theo COUNT/TIME | Tối ưu tần suất commit | Pending offsets lớn hoặc thời gian chờ dài |
| Sau MANUAL ack | Ứng dụng kiểm soát completion | Ack sớm/sai thứ tự có thể làm mất dữ liệu |
| Trong revoke bình thường | Giảm replay khi partition chuyển chủ | Không có cơ hội này khi lost/crash |
| Commit trước side effect | Giảm duplicate | **Nguy cơ mất nghiệp vụ** |
| Commit sau side effect | Có thể redelivery khi crash | Cần idempotency, thường là thiết kế an toàn hơn |

Commit trước rebalance **bổ sung** cho acknowledgment policy hằng ngày, chứ không thay thế nó. Nếu hệ thống chỉ commit khi rebalance, có thể giữ số lượng lớn record đã xử lý nhưng chưa commit trong thời gian group ổn định và gặp replay rộng khi crash.

## 24. Các sự cố thường gặp và cách chẩn đoán

### Rebalance xong, nhiều record cũ được đọc lại

Kiểm tra committed offset trước và sau revoke, AckMode, số pending acknowledgments và commit errors. Nếu một consumer mất partition mà không có cơ hội commit, redelivery là hành vi bình thường. Không nên kết luận đây là lỗi Kafka broker.

### onPartitionsRevokedBeforeCommit không được gọi

Có thể consumer mất ownership qua đường onPartitionsLost, container bị kill đột ngột, hoặc rebalance protocol không thu hồi partition theo đường bạn đang mong đợi. Kiểm tra container lifecycle events và group logs. Không đặt logic bảo đảm duy nhất của nghiệp vụ trong callback mà có thể không chạy.

### Đã tự gọi commitSync nhưng vẫn có duplicate

Commit chỉ có tác dụng nếu thành công, offset đúng và consumer vẫn có quyền commit. Crash có thể xảy ra sau side effect trước commit. Duplicate vẫn có thể xuất hiện; cần idempotency tại database hoặc external system.

### CommitFailedException tăng đột ngột

Kiểm tra max.poll.interval.ms, listener bị block lâu, retry backoff, broker/network và rebalance frequency. Không tự tăng timeout vô hạn để che giấu listener bị treo.

### Consumer mới xử lý cùng event trong khi consumer cũ chưa dừng

Kiểm tra async tasks còn chạy sau onPartitionsLost và thiếu fencing. Dùng idempotent side effects, event version hoặc lease token tại resource đích.

### Rebalance cooperative chỉ revoke một partition nhưng toàn bộ cache bị xóa

Callback chỉ nên cleanup state thuộc partition được cung cấp. Không xóa global state khi những partition khác vẫn còn assigned.

### Offset tăng nhưng database thiếu record

Kiểm tra listener có trả về trước khi DB commit không, có bắt rồi nuốt exception không, hoặc có commit/ack quá sớm không. Đây là dấu hiệu của mất dữ liệu nghiệp vụ do tiến độ Kafka vượt tiến độ thật.

## 25. Monitoring cho rebalance và offset commit

Một số tín hiệu cần quan sát:

| Tín hiệu | Ý nghĩa |
|---|---|
| Rebalance count/rate | Group có chuyển assignment quá thường xuyên không |
| Rebalance duration | Thời gian dừng/gián đoạn xử lý |
| Partitions revoked/assigned/lost | Hiểu đường lifecycle thực tế |
| Commit rate | Tần suất container commit offsets |
| Commit latency | Thời gian broker xác nhận commit |
| Commit failure count | Lỗi commit do generation/network/coordinator |
| Consumer lag theo partition | Partition không theo kịp dữ liệu mới |
| Pending acknowledgments | Số record đã hoàn tất nhưng chưa được commit |
| Listener processing p95/p99 | Nguy cơ vượt max.poll.interval.ms |
| Async task backlog | Công việc chưa hoàn tất khi revoke/lost |
| Duplicate event detection count | Idempotency đang ngăn replay bao nhiêu |
| Shutdown timeout | Có đủ thời gian drain/commit không |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter; một số metric về pending acknowledgments hoặc partition-local state cần ứng dụng tự xuất.

Log có cấu trúc nên có:

~~~text
event=kafka_partition_revoked
group=orders-service
topic=orders.events
partition=2
consumer=orders-0
committed_offset=103
pending_ack_count=0
reason=rebalance
~~~

Ví dụ chỉ minh họa format; không nên ghi nhận committed_offset=103 là thành công trước khi callback/commit thực tế xác nhận. Nên dùng trạng thái như commit_requested, commit_succeeded hoặc commit_failed nếu dữ liệu đang ở các giai đoạn khác nhau.

Tránh dùng eventId/record key tùy ý làm metric labels có cardinality vô hạn.

## 26. Test tích hợp các cửa sổ rebalance

Unit test gọi trực tiếp listener method không kiểm tra được Kafka group rebalance và commit semantics. Có thể dùng Testcontainers Kafka hoặc môi trường Kafka tích hợp để thử:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Consumer thứ hai tham gia group | Revoke/assign callbacks và commit tiến độ hợp lệ |
| Graceful stop một consumer | Pending offsets đã hoàn tất được commit theo policy |
| Kill -9 consumer đang xử lý | Consumer mới redeliver record chưa commit |
| Consumer vượt max.poll.interval.ms | Partition lost/rebalance, commit cũ có thể thất bại |
| Listener update DB xong, chưa commit offset | Replay không làm DB side effect trùng |
| Listener submit async rồi return | Phát hiện nguy cơ commit trước completion |
| Cooperative rebalance chỉ thu hồi subset | Không cleanup partitions vẫn assigned |
| Commit broker lỗi trong revoke | Không ghi nhận thành công giả |
| Batch chỉ xử lý một phần | Không commit vượt record chưa hoàn tất |
| Record lỗi chuyển DLT | Recovery và offset commit nhất quán theo policy |
| Transactional listener abort khi rebalance | Output chưa commit không hiện với read_committed |
| Rolling deployment nhiều replicas | Graceful shutdown và group stability đạt yêu cầu |

Trong test nên xác nhận **committed group offsets**, output Kafka, database state và side effects; không chỉ kiểm tra số lần callback được gọi.

## 27. Quy trình thiết kế commit trước rebalance

1. Xác định từng topic/partition có những side effect nào trước khi record được coi là hoàn tất.
2. Chọn AckMode theo nhu cầu latency, throughput và recovery.
3. Không báo listener success/ack khi side effect mới chỉ được gửi vào hàng đợi RAM.
4. Nếu cần partition-local buffers, thiết kế flush bền vững và callback trước commit phù hợp.
5. Dùng ConsumerAwareRebalanceListener cho lifecycle, không tự commit bừa ngoài container.
6. Xử lý revoke theo **partition subset** để tương thích cooperative rebalance.
7. Xử lý partitions lost như trường hợp đã mất ownership; không cố commit muộn.
8. Thiết kế shutdown graceful nhưng vẫn chấp nhận crash không graceful.
9. Đảm bảo eventId/idempotency và fencing cho external side effects.
10. Với transactional container, giữ output Kafka và offsets trong đúng transaction.
11. Theo dõi commit failures, rebalance, processing latency và consumer lag.
12. Thử fault injection ở thời điểm sau side effect nhưng trước commit và khi partition vừa đổi chủ.

## 28. Checklist trước production

- Consumer group, topic và partition assignment được quan sát rõ ràng.
- AckMode đúng với thời điểm side effect thực sự hoàn tất.
- Container quản lý offset commit; không có custom commitSync chồng chéo không cần thiết.
- Callback onPartitionsRevokedBeforeCommit xử lý được partition-local state nếu có.
- Callback onPartitionsRevokedAfterCommit không dựa vào giả định mọi external side effect thành công.
- onPartitionsLost không cố commit sau khi đã mất ownership.
- onPartitionsAssigned khởi tạo state đúng cho partition mới.
- Logic xử lý callback idempotent và không block vô hạn.
- Cooperative rebalance chỉ cleanup những partition thực sự được revoke.
- Concurrency không dùng chung một biến offset cho nhiều partitions.
- Pending async tasks có lifecycle drain/cancel/fencing khi revoke/lost.
- Không commit offset vượt dãy record hoàn tất liên tục.
- Commit failures được theo dõi và redelivery được chấp nhận.
- Database/API side effects có idempotency hoặc unique constraints.
- Transactional listener không commit offsets bên ngoài Kafka transaction.
- Shutdown grace period phù hợp nhưng hệ thống vẫn an toàn khi kill đột ngột.
- max.poll.interval.ms phù hợp với thời gian xử lý listener.
- Có monitoring rebalance, commit latency/errors, lag và duplicate.
- Đã thử join/leave group, rolling deploy, crash và lost partitions.

**Kết luận:** Commit trước rebalance là việc đưa những offset đã xử lý **thực sự an toàn** vào trạng thái committed khi partition được thu hồi bình thường. Spring Kafka listener container quản lý phần lớn offset commit theo AckMode và cung cấp ConsumerAwareRebalanceListener để ứng dụng flush/cleanup state đúng thời điểm. Tuy nhiên, partition có thể bị lost mà không còn cơ hội commit, và crash có thể xảy ra sau side effect trước commit. Vì vậy, thiết kế đúng phải kết hợp **offset discipline, idempotency, partition ownership/fencing và graceful lifecycle**, chứ không chỉ thêm một lệnh commitSync vào rebalance callback.

