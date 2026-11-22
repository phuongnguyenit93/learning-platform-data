# Consumer group không nhận partition

Trong Spring Kafka, một listener container có thể đang chạy nhưng consumer của nó lại **không được assign partition nào**. Khi đó ứng dụng không nhận record, consumer lag của workload có thể tăng và readiness của service có thể bị ảnh hưởng. Tuy nhiên, trạng thái không có partition chưa chắc là lỗi: nếu số consumer lớn hơn số partition, một số consumer sẽ ở trạng thái chờ hợp lệ trong khi các consumer khác xử lý toàn bộ dữ liệu.

Vì vậy, khi chẩn đoán **Consumer group không nhận partition**, cần trả lời ba câu hỏi trước khi restart hay thay đổi cấu hình:

1. Consumer group có thực sự không có partition được assign, hay chỉ riêng một member không có assignment?
2. Việc không có assignment là trạng thái hợp lệ theo topology, hay là dấu hiệu group chưa hoàn tất rebalance/có cấu hình sai?
3. Ứng dụng có nên được coi là ready khi pod không nhận partition, hay workload vẫn được phục vụ bởi các member khác?

Bài học thuộc chương **Health và readiness**. Nội dung tập trung vào cách Kafka phân phối partition, những nguyên nhân thường gặp trong Spring Kafka, cách kiểm tra group và listener container, xây dựng health policy phù hợp và phục hồi an toàn.

## 1. Partition assignment là gì?

Kafka lưu record trong topic. Mỗi topic có một hoặc nhiều partition; mỗi partition là một log có thứ tự riêng.

Consumer group cho phép nhiều consumer cùng chia sẻ workload. Với cơ chế group management thông thường, Kafka group coordinator phối hợp các thành viên và partition assignor để quyết định consumer nào sở hữu partition nào.

Ví dụ topic `orders.created` có sáu partition:

    orders.created
      P0  P1  P2  P3  P4  P5

    Consumer group: order-workers

    Member A: P0, P1
    Member B: P2, P3
    Member C: P4, P5

Mỗi partition trong group được giao cho tối đa một member tại một thời điểm. Các consumer trong cùng group cùng chia workload; những consumer thuộc group khác có thể đọc độc lập cùng topic.

**Assignment** là danh sách partition mà một consumer group member được giao. Consumer chỉ có thể poll dữ liệu từ những partition mà nó đang sở hữu theo cơ chế subscribe/group management, hoặc những partition được ứng dụng gán thủ công trong mô hình manual assignment.

Nếu một member không có partition, nó không nhận record từ group tại thời điểm đó. Điều này không tự động có nghĩa toàn group ngừng xử lý.

## 2. Phân biệt không có partition với không có record

Hai tình huống thường bị nhầm:

**Không có partition được assign:**

    Consumer A
      assigned partitions = []

    Consumer B
      assigned partitions = [P0, P1]

Consumer A không thể đọc record từ topic qua group assignment hiện tại.

**Có partition nhưng topic không có record mới:**

    Consumer A
      assigned partitions = [P0, P1]
      poll() -> empty
      poll() -> empty
      poll() -> empty

Consumer A vẫn sở hữu partition và có thể đang hoạt động khỏe mạnh; đơn giản là chưa có dữ liệu mới.

| Trạng thái | Assignment | Poll | Tín hiệu cần xem |
|---|---|---|---|
| Không có partition | Rỗng | Không có dữ liệu để đọc từ assignment | Group membership, assignor, subscription |
| Có partition, topic rỗng | Có | Poll trả về rỗng | Idle event, producer traffic |
| Có partition, đang pause | Có | Container không giao thêm record theo pause policy | Pause state, backpressure |
| Có partition, consumer bị kẹt | Có thể vẫn được ghi nhận | Poll không tiến triển | Non-responsive, thread dump, poll interval |
| Group đang rebalance | Assignment có thể đang chuyển tiếp | Tạm thời chưa ổn định | Group state, rebalance events |

Không dùng `ListenerContainerIdleEvent` để kết luận consumer không có partition. Idle thường nói về việc không nhận record trong khoảng thời gian cấu hình, trong khi assignment vẫn có thể tồn tại.

## 3. Một member không có partition khác với toàn group không có partition

Giả sử topic có ba partition và group có năm consumer:

    Topic: orders.created
      P0  P1  P2

    Group: order-workers
      Member A -> P0
      Member B -> P1
      Member C -> P2
      Member D -> []
      Member E -> []

Hai member D và E không có partition là kết quả hợp lệ: Kafka không thể chia ba partition cho năm member mà vẫn giữ nguyên tắc một partition thuộc tối đa một member trong group.

Toàn group vẫn có ba partition được xử lý bởi A, B và C.

Ngược lại, nếu tất cả member đều có assignment rỗng trong khi topic có partition và group đã ổn định, cần điều tra subscription, group identity, metadata, assignor và trạng thái group.

Khi đọc dashboard, phải phân biệt:

- **Member assignment:** partition của một consumer cụ thể.
- **Group assignment:** hợp của partition được giao cho các member trong group.
- **Topic partition count:** tổng partition hiện có trong các topic được subscribe.
- **Expected assignment:** partition mà topology và assignor dự kiến giao cho group.

Chỉ nhìn một pod không có partition chưa đủ để kết luận toàn dịch vụ ngừng tiêu thụ.

## 4. Khi nào không có partition là bình thường?

Một số trường hợp không có assignment là trạng thái được dự đoán:

1. **Số consumer lớn hơn số partition.** Một số consumer dư không có partition.
2. **Topic subscription chỉ khớp một phần topic.** Một member có thể không nhận partition tùy subscription/assignment.
3. **Group vừa thay đổi thành viên.** Consumer đang chờ rebalance hoàn tất.
4. **Topic chưa có partition phù hợp.** Metadata hoặc topic creation chưa hoàn tất; tùy cấu hình auto-create và thời điểm.
5. **Một listener container đã được tạo nhưng chưa start.** Nó chưa tham gia group.
6. **Container đã bị pause hoặc dừng.** Pause vẫn giữ assignment trong nhiều tình huống; stop sẽ rời lifecycle/group theo cách tương ứng.
7. **Ứng dụng dùng manual assignment.** Partition được cấu hình qua `topicPartitions` hoặc `assign()`, không theo cùng quy trình group assignor thông thường.

Readiness policy cần hiểu topology dự kiến. Không đánh dấu mọi pod không có partition là unhealthy nếu deployment cố ý chạy nhiều replica hơn số partition để dự phòng hoặc scale nhanh.

## 5. Tính giới hạn song song từ partition count

Số consumer có thể xử lý song song trong một group bị giới hạn bởi số partition được group subscribe và assign.

Ví dụ:

    orders.created: 8 partitions
    replicas: 3
    concurrency per pod: 4

    Tổng consumer threads: 3 x 4 = 12
    Số partition: 8
    Consumer có assignment: tối đa 8
    Consumer dư: ít nhất 4

Tăng concurrency từ 4 lên 8 không làm một topic tám partition có 24 consumer xử lý song song 24 partition. Một số child consumers sẽ không nhận partition.

| Partition count | Consumer threads | Member có thể nhận partition | Member dư tối thiểu |
|---:|---:|---:|---:|
| 3 | 3 | 3 | 0 |
| 3 | 5 | 3 | 2 |
| 8 | 6 | 6 | 0 |
| 8 | 12 | 8 | 4 |
| 24 | 12 | 12 | 0 |

Bảng là giới hạn đơn giản khi các member cùng subscribe tập topic tương thích và không có ràng buộc assignor khác. Nhiều topic, subscription khác nhau và assignor có thể tạo phân phối không đều.

Trước khi tăng concurrency, hãy tính tổng consumer threads của toàn bộ replicas trong group, không chỉ một pod.

## 6. Kiểm tra topic có tồn tại và có partition

Một nguyên nhân cơ bản là consumer subscribe nhầm topic, topic chưa được tạo hoặc topic có tên khác môi trường.

Dùng Kafka CLI để xem topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
~~~

Xem chi tiết topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.created
~~~

Kết quả mô tả topic cho biết partition count và leader/replica của từng partition. Nếu topic không tồn tại, kiểm tra:

- Tên topic trong `@KafkaListener`.
- Profile/environment đang chạy.
- Biến cấu hình topic có được resolve đúng không.
- Topic provisioning/ACL/auto-create policy.
- Broker bootstrap servers có trỏ đúng cluster không.

Không tự bật auto topic creation trong production chỉ để chữa một listener subscribe sai tên. Việc tạo nhầm topic có thể khiến ứng dụng chạy nhưng đọc một log rỗng khác với dữ liệu thực.

## 7. Kiểm tra consumer group đang ở trạng thái nào

Kafka group trải qua các trạng thái lifecycle như:

- **PreparingRebalance:** group chuẩn bị phân phối lại partition.
- **CompletingRebalance:** group đang hoàn tất assignment.
- **Stable:** group đã ổn định với assignment hiện tại.
- **Empty:** không còn member hoạt động trong group.
- **Dead:** group không còn tồn tại theo trạng thái broker quản lý.

Tên enum/trạng thái và cách hiển thị có thể thay đổi theo Kafka version hoặc CLI. Dùng lệnh mô tả group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group order-workers
~~~

Tùy Kafka version, có thể xem members và assignment chi tiết:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group order-workers --members --verbose
~~~

Cần xem:

- Group có tồn tại và có member không?
- Member count có khớp replicas × concurrency dự kiến không?
- Group đang Stable hay liên tục rebalance?
- Partition nào được assign cho từng member?
- Committed offset và lag có tiến triển không?
- Consumer client ID/host nào tương ứng pod đang điều tra?

Nếu group đang Empty, vấn đề có thể là không có consumer nào tham gia đúng group. Nếu group Stable nhưng một member có assignment rỗng, đó có thể chỉ là consumer dư.

## 8. Sai group.id hoặc nhầm listener ID

Trong Spring Kafka, có nhiều loại định danh cần phân biệt:

- `@KafkaListener(id=...)` xác định listener/container endpoint theo Spring.
- `groupId=...` xác định Kafka consumer group cho listener khi được cấu hình tường minh.
- `spring.kafka.consumer.group-id` là group ID mặc định trong cấu hình consumer.
- `client.id` giúp nhận diện Kafka client instance.

Nếu service mong đợi group `order-workers` nhưng listener thực tế tham gia `order-worker`, dashboard kiểm tra group cũ sẽ không thấy member/assignment như mong muốn.

Ví dụ khai báo rõ:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "order-workers",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Đừng dùng listener ID để suy đoán group ID. Khai báo `groupId` rõ ràng giúp cấu hình dễ đọc và giảm nhầm lẫn giữa các môi trường.

Kiểm tra cả YAML, environment variables, profile, annotation và custom container factory. Một giá trị được override ở annotation có thể làm group thực tế khác với group ID bạn đang tìm.

## 9. Kiểm tra subscription: topics, topicPattern và topicPartitions

Spring Kafka hỗ trợ nhiều cách đăng ký listener.

**Subscribe theo danh sách topic:**

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = {"orders.created", "orders.updated"},
    groupId = "order-workers"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

**Subscribe theo regex pattern:**

~~~java
@KafkaListener(
    id = "tenantEventsListener",
    topicPattern = "tenant\\.events\\..*",
    groupId = "tenant-workers"
)
public void consume(TenantEvent event) {
    tenantService.process(event);
}
~~~

Pattern phải khớp tên topic thực tế. Ví dụ `tenant.events.eu` không khớp pattern `tenant\\.event\\..*` vì pattern có từ `event` số ít.

**Manual partition assignment:**

~~~java
@KafkaListener(
    id = "ordersPartitionListener",
    groupId = "orders-manual",
    topicPartitions = {
        @TopicPartition(
            topic = "orders.created",
            partitions = {"0", "1"}
        )
    }
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Khi dùng `topicPartitions`, ứng dụng chỉ định partition trực tiếp. Mô hình này khác subscription qua group assignor; không chẩn đoán bằng cách kỳ vọng các callback/assignment giống hoàn toàn một consumer subscribe thông thường.

Không khai báo đồng thời nhiều cách subscription trái ngược rồi giả định chúng được kết hợp. Kiểm tra annotation và factory thực tế được listener sử dụng.

## 10. Regex subscription không khớp topic

Với `topicPattern`, Kafka client nhận một pattern và định kỳ có thể cập nhật metadata để phát hiện topic khớp. Một lỗi escape hoặc khác biệt naming convention có thể khiến subscription không khớp topic nào.

Ví dụ:

~~~java
@KafkaListener(
    id = "auditListener",
    topicPattern = "audit\\.events\\..*",
    groupId = "audit-workers"
)
public void consume(AuditEvent event) {
    auditService.process(event);
}
~~~

Các topic khớp:

- `audit.events.eu`
- `audit.events.us`
- `audit.events.internal`

Các topic không khớp:

- `audit.event.eu`
- `orders.audit.events`
- `audit-events-eu`

Nếu group Stable nhưng không có partition, xác nhận pattern bằng tên topic thật và kiểm tra subscription metadata. Một regex quá rộng cũng có thể khiến listener subscribe ngoài ý muốn tới topic khác.

Không sửa regex production bằng cách mở rộng tùy tiện thành `.*`; listener có thể nhận dữ liệu không thuộc service hoặc vi phạm ranh giới quyền truy cập.

## 11. Consumer group chưa hoàn tất rebalance

Khi member mới tham gia, member rời group, topic partition thay đổi hoặc subscription đổi, Kafka có thể bắt đầu rebalance.

Trong thời gian rebalance, assignment cũ có thể bị thu hồi và assignment mới chưa được áp dụng đầy đủ. Quan sát trong một khoảng ngắn có thể thấy không có partition hoặc assignment đang thay đổi.

Sơ đồ:

    Member A, B đang Stable
           |
           v
    Member C tham gia group
           |
           v
    PreparingRebalance
           |
           v
    Revocation / assignment calculation
           |
           v
    CompletingRebalance
           |
           v
    Stable với assignment mới

Nếu group liên tục không đạt Stable, cần điều tra nguyên nhân làm rebalance lặp:

- Consumer xử lý quá lâu, vượt `max.poll.interval.ms`.
- Network/broker connectivity không ổn định.
- Pod restart liên tục.
- Static member bị fencing do trùng `group.instance.id`.
- Subscription/metadata thay đổi thường xuyên.
- Cooperative/eager assignor không tương thích giữa các member.
- Consumer bị crash hoặc không hoàn tất poll lifecycle.

Một lần rebalance ngắn là bình thường; rebalance storm mới là vấn đề vận hành.

## 12. Cooperative và eager assignment

Kafka có nhiều partition assignment strategies. Các strategy eager thường revoke assignment rộng hơn trước khi tạo assignment mới; cooperative strategy cố gắng chỉ chuyển những partition cần thiết để giảm gián đoạn.

Ví dụ cấu hình assignor có thể nằm trong consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Tên class và tính tương thích phụ thuộc Kafka client version. Trong một đợt rolling upgrade, cần chú ý compatibility giữa các member đang chạy strategy khác nhau.

Cooperative rebalance không loại bỏ tình huống một member không có partition. Nếu consumer threads nhiều hơn partition, một số vẫn dư. Nó cũng không bảo đảm group sẽ không rebalance khi consumer mất membership.

Không đổi assignor chỉ vì một pod không có assignment. Trước hết kiểm tra partition count, member count và subscription; thay assignor có thể tạo thêm rebalance và ảnh hưởng toàn group.

## 13. RangeAssignor có thể tạo phân phối không đều

Với nhiều topic và nhiều partition, assignor có thể phân phối không đều tùy strategy và subscription.

Ví dụ group có hai topic, mỗi topic có ba partition, và ba consumers đều subscribe cả hai topic. Range assignment có thể chia partition theo từng topic, dẫn đến consumer đầu nhận một số partition của cả hai topic, trong khi member khác có thể nhận ít hơn tùy số lượng và cấu trúc.

Khi một consumer không nhận partition, hãy kiểm tra:

- Nó subscribe cùng tập topic với các member khác không?
- Có topic nào chỉ một subset member subscribe không?
- Partition count từng topic có chênh lệch không?
- Assignment strategy hiện tại là gì?
- Các member có cùng version/compatible configuration không?

Không chỉ so sánh tổng partition của cluster với tổng consumer threads. Cần so sánh **partition có thể được assign cho từng member dựa trên subscription thực tế**.

## 14. Consumer threads nhiều hơn partition count

Spring Kafka `concurrency` tạo nhiều child consumers cho một listener container. Concurrency không tạo thêm partition.

Ví dụ:

~~~java
factory.setConcurrency(6);
~~~

Nếu topic có ba partition và listener chỉ subscribe topic đó, tối đa ba child consumers có thể nhận partition trong một group. Ba child còn lại có thể không có assignment.

Với bốn replicas, mỗi replica concurrency=6:

    Tổng child consumers = 4 x 6 = 24
    Topic partitions = 3
    Member có assignment tối đa = 3
    Member không có assignment ít nhất = 21

Cấu hình này thường lãng phí tài nguyên và có thể làm tăng overhead group membership. Nó không tăng throughput của một topic ba partition.

Chọn concurrency dựa trên partition topology và workload. Nếu cần song song hơn, có thể cần tăng partition count sau khi đánh giá key distribution, ordering và giới hạn broker.

## 15. Topic chưa được tạo hoặc metadata chưa cập nhật

Khi listener khởi động trước khi topic được tạo, consumer có thể chưa có partition metadata phù hợp. Tùy cấu hình broker/client, auto topic creation và subscription, quá trình discovery có thể khác nhau.

Các việc cần kiểm tra:

1. Topic có tồn tại trong đúng cluster không?
2. Topic có partition count lớn hơn 0 không?
3. Broker có cho phép auto topic creation không?
4. ACL của principal có cho phép describe/subscribe/read không?
5. Metadata có được client refresh không?
6. Topic vừa được tạo hoặc partition vừa tăng có đang trong quá trình propagation không?

Một topic name sai có thể khiến listener vẫn chạy nhưng không nhận được dữ liệu từ topic dự định. Nếu auto-create bật, Kafka có thể tạo topic rỗng khi consumer subscribe; điều này làm lỗi cấu hình khó phát hiện hơn.

Production nên quản lý topic qua provisioning/IaC và xác nhận partition count trước khi triển khai consumer phụ thuộc vào topic.

## 16. ACL và xác thực: phân biệt assignment với fetch permission

Một consumer có thể gặp lỗi bảo mật khi subscribe hoặc fetch:

- Không có quyền `READ` trên topic.
- Không có quyền phù hợp trên consumer group.
- SASL/TLS credential sai hoặc hết hạn.
- Broker authorization policy khác giữa môi trường.

Cần phân biệt hai hiện tượng:

- **Không được assign partition:** group assignment/subscription không giao partition cho member.
- **Đã có assignment nhưng không đọc được:** fetch/offset commit có thể lỗi do authorization hoặc authentication.

Thiếu quyền không phải lúc nào cũng được biểu diễn thành một assignment rỗng. Consumer có thể nhận exception trong poll hoặc log lỗi authorization dù metadata assignment có tồn tại.

Kiểm tra broker/client logs và ACL với principal thực tế. Không log password, token hoặc private key trong lúc điều tra.

## 17. auto.offset.reset không tạo partition assignment

Một hiểu nhầm phổ biến là group không có offset nên Kafka không assign partition.

Thực tế, partition assignment và offset initialization là hai bước khác nhau:

    Subscribe topic
        |
        v
    Group coordinator/assignor giao partition
        |
        v
    Consumer xác định vị trí đọc
        |
        +--> committed offset còn hợp lệ
        |
        +--> nếu không có/hết hạn: auto.offset.reset policy
        |
        v
    Poll records

`auto.offset.reset=earliest/latest/none` quyết định cách xử lý khi không có offset hợp lệ. Nó không phải cơ chế tạo assignment.

Nếu cấu hình `none`, consumer có thể có partition nhưng ném lỗi vì không tìm thấy offset. Đừng thay đổi reset policy để chữa một lỗi assignment khi chưa xác định đúng nguyên nhân; `latest` có thể bỏ qua dữ liệu cũ cần xử lý.

## 18. group.id khác nhau khiến dữ liệu được chia khác nhau

Nếu mỗi pod vô tình tham gia một group ID riêng, Kafka không chia partition giữa các pod theo cách bạn mong muốn.

Ví dụ:

    Pod A -> group order-worker-A
    Pod B -> group order-worker-B
    Pod C -> group order-worker-C

Mỗi group độc lập có thể nhận toàn bộ partition của topic. Điều này tạo fan-out, không phải load balancing giữa ba pod.

Nếu mong muốn chia workload, các consumer phải dùng cùng group ID:

    Pod A --+
    Pod B --+--> group order-workers --> partitions chia giữa members
    Pod C --+

Nếu dashboard đang xem group `order-workers` mà ứng dụng thực tế dùng `order-worker-A`, bạn có thể kết luận nhầm rằng group không nhận partition.

Đối chiếu group ID runtime từ cấu hình listener và group description trên broker, không chỉ đọc YAML mặc định.

## 19. Static membership và group.instance.id

Static membership dùng `group.instance.id` để nhận diện một member ổn định qua những lần restart phù hợp, có thể giảm rebalance không cần thiết.

Nhưng `group.instance.id` phải duy nhất trong group. Nếu hai instance cùng sử dụng một ID, Kafka có thể fencing một member hoặc gây lỗi membership.

Ví dụ:

    Pod A: group.instance.id=orders-0
    Pod B: group.instance.id=orders-1
    Pod C: group.instance.id=orders-2

Không cấu hình cùng `orders-worker` cho tất cả pod.

Static membership không làm consumer được ưu tiên nhận partition và không giải quyết việc số consumer lớn hơn số partition. Nó cũng không thay thế graceful shutdown, heartbeat hoặc xử lý rebalance đúng cách.

Nếu dùng Kubernetes StatefulSet, ordinal có thể giúp tạo identity ổn định; với Deployment replica thay đổi, cần chiến lược ID khác và tránh tái sử dụng một ID khi instance cũ vẫn còn hoạt động.

## 20. Spring Kafka listener container có đang chạy không?

Trước khi kiểm tra group assignment, xác nhận listener container đã được start.

Có thể truy cập container qua `KafkaListenerEndpointRegistry`:

~~~java
@Service
public class ListenerStatusService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerStatusService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isOrdersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        return container != null && container.isRunning();
    }
}
~~~

Listener phải có ID tương ứng:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "order-workers"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

`isRunning()` chỉ phản ánh lifecycle container. Nó không chứng minh container có partition, đã poll thành công hay đang xử lý record.

Một container có thể running nhưng subscription chưa khớp topic, group đang rebalance hoặc member không có partition vì consumer dư.

## 21. Quan sát assignment bằng rebalance listener

Spring Kafka hỗ trợ `ConsumerAwareRebalanceListener` để nhận callback assignment/revocation/lost cùng consumer context.

Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        PartitionAssignmentTracker tracker) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties()
            .setConsumerRebalanceListener(
                new ConsumerAwareRebalanceListener() {

                    @Override
                    public void onPartitionsAssigned(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        tracker.assigned(
                            consumer,
                            partitions
                        );
                    }

                    @Override
                    public void onPartitionsRevoked(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        tracker.revoked(
                            consumer,
                            partitions
                        );
                    }

                    @Override
                    public void onPartitionsLost(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        tracker.lost(
                            consumer,
                            partitions
                        );
                    }
                }
            );

    return factory;
}
~~~

Các import chính:

~~~java
import java.util.Collection;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
~~~

`PartitionAssignmentTracker` là service ứng dụng cần tự định nghĩa. Callback giúp ghi nhận assignment thực tế và cập nhật snapshot cho health monitoring.

Lưu ý:

- Callback có thể được gọi trên consumer thread.
- Giữ callback ngắn, không gọi HTTP/database blocking.
- Không dùng Consumer từ thread khác.
- Xử lý nhiều child consumers/concurrency an toàn.
- Không xem một callback assigned rỗng trong giai đoạn chuyển tiếp là kết luận group đã mất partition vĩnh viễn.
- Dùng onPartitionsLost riêng cho tình huống đã mất ownership; không commit offset từ callback lost.

## 22. Lưu snapshot assignment cho health check

Health endpoint thường chạy trên HTTP request thread, không phải consumer thread. Không nên gọi raw `KafkaConsumer.assignment()` từ health check vì KafkaConsumer không thread-safe.

Một cách an toàn hơn là cập nhật snapshot bất biến từ rebalance callback:

~~~java
@Component
public class PartitionAssignmentTracker {

    private final AtomicReference<Set<TopicPartition>> assigned =
            new AtomicReference<>(Set.of());

    public void assigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        Set<TopicPartition> next =
                new HashSet<>(consumer.assignment());

        assigned.set(Set.copyOf(next));
    }

    public void revoked(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        updateRemoving(partitions);
    }

    public void lost(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        updateRemoving(partitions);
    }

    public Set<TopicPartition> snapshot() {
        return assigned.get();
    }

    private void updateRemoving(
            Collection<TopicPartition> partitions) {

        assigned.updateAndGet(current -> {
            Set<TopicPartition> next = new HashSet<>(current);
            next.removeAll(partitions);
            return Set.copyOf(next);
        });
    }
}
~~~

Ví dụ trên minh họa snapshot đơn giản cho một consumer. Với concurrent container, cần lưu assignment theo **consumer/child identity** rồi tính hợp hoặc tổng theo listener. Một biến AtomicReference dùng chung như trên nếu nhiều child callback cùng ghi có thể ghi đè snapshot của child khác.

Thiết kế production nên quản lý map từ child consumer identity tới set partition, rồi cập nhật nguyên tử. Khi child stop, xóa entry tương ứng; khi rebalance, thay assignment của đúng child.

Không dùng `consumer.assignment()` trong health endpoint để truy vấn live consumer từ thread HTTP. Snapshot được cập nhật trên callback giúp tách quyền sở hữu thread.

## 23. HealthIndicator: đánh giá assignment theo kỳ vọng

Một health check hữu ích cần biết listener nào **bắt buộc** phải có partition và thời gian chờ assignment hợp lệ là bao lâu.

Ví dụ đơn giản cho một listener chuyên xử lý một topic:

~~~java
@Component
public class OrdersAssignmentHealthIndicator implements HealthIndicator {

    private final ListenerStatusService listenerStatus;
    private final PartitionAssignmentTracker tracker;

    public OrdersAssignmentHealthIndicator(
            ListenerStatusService listenerStatus,
            PartitionAssignmentTracker tracker) {
        this.listenerStatus = listenerStatus;
        this.tracker = tracker;
    }

    @Override
    public Health health() {

        boolean running = listenerStatus.isOrdersListenerRunning();
        int assignedCount = tracker.snapshot().size();

        if (!running) {
            return Health.down()
                    .withDetail("listenerRunning", false)
                    .build();
        }

        if (assignedCount == 0) {
            return Health.unknown()
                    .withDetail("listenerRunning", true)
                    .withDetail("assignedPartitions", 0)
                    .withDetail("reason", "No assignment observed")
                    .build();
        }

        return Health.up()
                .withDetail("listenerRunning", true)
                .withDetail("assignedPartitions", assignedCount)
                .build();
    }
}
~~~

Đây là ví dụ minh họa cho listener có một consumer snapshot. Trong production cần imports Spring Boot Actuator và kiểu health tương ứng.

Không nên mặc định trả DOWN ngay khi assignment count bằng 0. Có thể pod này là consumer dư hợp lệ, đang chờ rebalance hoặc vừa start. Một health policy đúng cần thêm:

- Thời gian kể từ lúc container start.
- Expected partition count.
- Tổng member/partition của group.
- Assignment của các member khác.
- Listener có phải workload bắt buộc trên mọi pod không?
- Group có đang Stable không?
- Có lag tăng và không member nào xử lý không?

Có thể dùng trạng thái UNKNOWN/OUT_OF_SERVICE hoặc custom status tùy mục tiêu readiness, nhưng phải phân biệt health của **pod** và health của **toàn consumer group**.

## 24. Pod readiness không giống consumer assignment

Kubernetes readiness probe quyết định pod có được đưa vào các service endpoints để nhận traffic mạng hay không. Kafka consumer group không dựa vào readiness HTTP để assign partition.

Nếu pod không có partition:

- Mark pod NotReady không tự động làm Kafka group rời member.
- Consumer có thể tiếp tục tham gia group và chờ partition.
- Nếu deployment controller thay pod vì readiness/liveness policy khác, có thể tạo thêm restart/rebalance.
- Nếu mọi pod đều bị đánh NotReady vì assignment rỗng trong giai đoạn rebalance, hệ thống có thể tự tạo outage.

Nên phân biệt:

| Health dimension | Câu hỏi | Nguồn |
|---|---|---|
| Process liveness | JVM còn sống và tiến triển không? | Liveness, process/JVM |
| Application readiness | API có thể nhận traffic HTTP không? | Readiness |
| Listener lifecycle | Container đã start và chưa stop? | Registry/container |
| Consumer assignment | Member có partition nào? | Rebalance callback/group description |
| Group health | Toàn group có member xử lý đủ partition không? | Kafka Admin/metrics |
| Data freshness | Record được xử lý trong SLA? | Lag/oldest age/business metrics |

Một service có thể HTTP-ready nhưng consumer group không hoạt động. Ngược lại, một pod không có partition có thể vẫn là thành viên dự phòng hợp lệ.

## 25. Chọn readiness policy theo topology

Có ba mô hình thường gặp.

**Mô hình A: mỗi pod phải có partition.** Ví dụ replicas không vượt số partition và mỗi instance là một phần bắt buộc của capacity. Khi group Stable mà một pod không có assignment, đó có thể là dấu hiệu cấu hình sai.

**Mô hình B: số pod lớn hơn số partition.** Một số pod không có assignment là bình thường. Không dùng assignment count của từng pod làm readiness gate.

**Mô hình C: group có thể scale động.** Trong quá trình scale hoặc rebalance, assignment có thể tạm thời rỗng. Readiness cần có grace period và xác nhận group đã ổn định trước khi đánh giá.

Đối với health của cả workload, câu hỏi hữu ích hơn là:

> Có đủ member khỏe mạnh đang xử lý tất cả partition bắt buộc và tiến độ offset còn đáp ứng freshness SLO không?

Không phải:

> Mọi pod có ít nhất một partition không?

Nếu service có nhiều listener groups, hãy đánh giá từng listener theo vai trò. Một listener phụ hoặc maintenance topic không nhất thiết phải quyết định readiness của toàn bộ API service.

## 26. Kiểm tra group bằng Kafka AdminClient

Có thể dùng Kafka AdminClient để mô tả consumer group từ một service monitoring hoặc diagnostic tool.

Ví dụ định hướng:

~~~java
public Map<String, Object> describeGroup(
        AdminClient adminClient,
        String groupId) throws Exception {

    ConsumerGroupDescription description =
            adminClient.describeConsumerGroups(
                    List.of(groupId))
                .describedGroups()
                .get(groupId)
                .get();

    Map<String, Object> result = new HashMap<>();

    result.put("groupId", description.groupId());
    result.put("state", description.state().toString());
    result.put("memberCount", description.members().size());

    Map<String, List<String>> assignments = new HashMap<>();

    for (MemberDescription member : description.members()) {
        List<String> partitions =
                member.assignment().topicPartitions()
                    .stream()
                    .map(tp -> tp.topic() + "-" + tp.partition())
                    .toList();

        assignments.put(member.consumerId(), partitions);
    }

    result.put("assignments", assignments);
    return result;
}
~~~

Imports chính:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;
import org.apache.kafka.clients.admin.MemberDescription;
~~~

Ví dụ dùng API AdminClient có trong Kafka clients hiện đại; method và kiểu group state có thể khác giữa các phiên bản. Diagnostic call là I/O mạng, nên cần timeout và không nên chạy đồng bộ trong mỗi readiness probe với tần suất rất cao.

AdminClient description cho biết group/member assignment tại thời điểm broker trả kết quả. Nó không chứng minh listener đã xử lý record thành công hay offset đang tiến. Ghép dữ liệu group với consumer metrics và application snapshot.

## 27. Kiểm tra subscription và assignment của từng member

Khi một member không có partition, so sánh nó với các member khác:

| Thông tin | Member A | Member B | Member C |
|---|---|---|---|
| group.id | order-workers | order-workers | order-workers |
| client.id | orders-0 | orders-1 | orders-2 |
| subscribed topics | orders.created | orders.created | orders.updated |
| assignment | P0, P1 | P2, P3 | rỗng |
| state | Stable | Stable | Stable |

Trong ví dụ, Member C subscribe topic khác với topic có partition đang quan tâm. Không nên kỳ vọng nó nhận partition từ `orders.created`.

Nếu một group member có subscription không giống các member khác, assignor chỉ có thể giao những partition phù hợp với subscription. Điều này thường xảy ra khi deployment có cấu hình profile khác nhau hoặc một số listener subscribe pattern khác.

Để điều tra, log/metric nên ghi listener ID, group ID, client ID, subscription topic names (không chứa dữ liệu nhạy cảm) và assignment count.

## 28. Topic partition tăng không tự bảo đảm phân phối tức thì

Khi tăng partition count của topic, consumer group có thể cần metadata refresh và rebalance để assignment mới phản ánh partition mới.

Một số lưu ý:

- Partition count chỉ tăng, không giảm được bằng thao tác thông thường.
- Tăng partition có thể thay đổi key-to-partition mapping cho producer dùng hash partitioning.
- Consumer group cần nhận metadata và hoàn tất rebalance.
- Assignment strategy có thể phân phối partition mới không đều trong giai đoạn chuyển tiếp.
- Tăng partition không tự sửa group ID hoặc topic subscription sai.

Không tăng partition chỉ để làm mọi consumer có assignment nếu nhiều consumer đang dư do thiết kế. Partition count ảnh hưởng ordering theo key, storage, replication, controller load và downstream concurrency.

Trước khi thay đổi, đánh giá yêu cầu ordering, key distribution và capacity của broker.

## 29. Paused partition vẫn là partition được assign

Một consumer có thể có assignment nhưng các partition đang bị pause bởi Spring Kafka container hoặc ứng dụng. Khi đó nó không giao thêm record cho listener theo pause policy, nhưng không đồng nghĩa group đã mất partition.

Ví dụ:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null) {
    container.pause();
}
~~~

Container pause thường được thiết kế để duy trì consumer lifecycle/poll cần thiết trong khi tạm dừng fetch/delivery. Vì vậy dashboard cần phân biệt:

- assigned partition count.
- paused partition count.
- records consumed rate.
- listener processing rate.

Nếu assigned count > 0 nhưng consumed rate = 0, kiểm tra pause, poll, backlog và lỗi fetch. Đừng chẩn đoán “không có partition” khi thực tế các partition đang bị pause.

## 30. Manual assignment khác group subscription

Spring Kafka có thể cấu hình listener theo partition cụ thể bằng `@TopicPartition` hoặc dùng KafkaConsumer.assign() trong ứng dụng tự quản lý.

Trong manual assignment, ứng dụng chỉ định partition trực tiếp và không sử dụng group assignor để phân phối subscription theo cùng cách `subscribe()` thông thường.

Điều này có các hệ quả:

- Nhiều consumer có thể vô tình được cấu hình cùng một partition.
- Ứng dụng phải quản lý ownership và phân chia partition.
- Rebalance callbacks/group assignment có semantics khác.
- Group ID vẫn có thể liên quan đến offset commits, nhưng không có nghĩa group coordinator tự chia partition như subscription.
- Scale replica không tự phân phối lại các manual assignments.

Nếu dùng `topicPartitions`, hãy xác nhận annotation được gắn vào listener đúng và partition numbers tồn tại. Đừng tìm lỗi group assignor khi listener đang dùng manual assignment.

## 31. NonResponsiveConsumerEvent không đồng nghĩa không có partition

Spring Kafka có thể phát `NonResponsiveConsumerEvent` khi monitor phát hiện consumer không đáp ứng nhịp poll theo cấu hình. Đây là vấn đề tiến triển poll, khác với một member có assignment rỗng hợp lệ.

Tương tự:

- `ConsumerPausedEvent`: consumer đã pause.
- `ConsumerStoppedEvent`: consumer kết thúc lifecycle.
- `ConsumerPartitionPausedEvent`: partition được pause.
- `ListenerContainerIdleEvent`: container không nhận record trong khoảng thời gian cấu hình.
- Rebalance callbacks: assignment thay đổi.

Không gộp tất cả thành một health state “consumer dead”. Một member không có partition có thể poll khỏe mạnh; một member có partition có thể bị non-responsive.

Monitoring nên có metric riêng cho assignment, pause, poll responsiveness, stopped state và lag.

## 32. Consumer group không nhận partition do max.poll.interval.ms?

`max.poll.interval.ms` quy định giới hạn thời gian giữa các lần poll để consumer duy trì membership theo cơ chế Kafka. Nếu listener xử lý quá lâu, consumer có thể mất membership và group rebalance.

Chuỗi sự kiện:

    Consumer A được assign P0
          |
          v
    Listener xử lý quá lâu
          |
          v
    Không poll lại trong giới hạn
          |
          v
    Group thay đổi membership / rebalance
          |
          v
    P0 có thể được assign cho Consumer B

Sau rebalance, A có thể không còn partition. Nhưng nguyên nhân gốc là xử lý/poll chậm, không phải assignor tự ý bỏ partition.

Kiểm tra:

- max.poll.interval.ms.
- max.poll.records.
- listener processing duration p95/p99.
- synchronous commit latency.
- dependency timeouts/retry.
- GC pause và CPU throttling.
- rebalance count/duration.
- onPartitionsLost/revoked callbacks.

Đừng chỉ tăng max.poll.interval.ms để che một listener bị block vô hạn. Cần giới hạn thời gian dependency, giảm batch size hoặc thay đổi xử lý.

## 33. Kiểm tra Spring Kafka logs

Khi assignment không xuất hiện, log của Spring Kafka và Kafka client có thể giúp xác định group lifecycle.

Có thể tăng log level tạm thời:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: DEBUG
    org.springframework.kafka.config: INFO
    org.apache.kafka.clients.consumer.internals.ConsumerCoordinator: DEBUG
    org.apache.kafka.clients.consumer.internals.AbstractCoordinator: INFO
~~~

Tên package nội bộ và chi tiết log phụ thuộc Kafka client version. Chỉ bật DEBUG trong phạm vi cần thiết và có thời hạn vì log group/rebalance có thể nhiều.

Tìm các thông tin:

- Subscribed topics/pattern.
- Group join và generation.
- Rebalance started/completed.
- Assignment received.
- Commit/heartbeat failures.
- Authentication/authorization errors.
- Consumer shutdown/restart.
- Client ID và member identity.

Không log SASL password, bearer token hoặc private key khi bật debug.

## 34. Metric cần theo dõi

Một dashboard assignment/health nên kết hợp:

| Metric | Ý nghĩa |
|---|---|
| assigned-partitions | Số partition được assign cho consumer |
| group-member-count | Số member trong group |
| topic-partition-count | Tổng partition của workload |
| records-consumed-rate | Tốc độ consumer nhận record |
| records-lag-max | Lag lớn nhất theo client/partition nếu client xuất metric |
| rebalance-total | Số lần rebalance |
| last-rebalance-seconds-ago | Thời gian từ rebalance gần nhất nếu hỗ trợ |
| commit-rate / commit-latency | Tiến độ offset commit |
| listener-container-running | Lifecycle container |
| consumer-paused | Trạng thái pause |
| nonresponsive-events | Số cảnh báo poll không phản hồi |
| oldest-record-age | Tuổi record chưa xử lý |
| processing-duration | Thời gian listener xử lý |

Tên và nhóm metric chính xác phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter. Xác nhận metric thực tế trước khi tạo alert.

Không gắn eventId, offset hoặc UUID làm metric label vì high cardinality. Có thể dùng application, group, listener và topic nếu số lượng được kiểm soát.

## 35. Readiness policy: không đánh DOWN chỉ vì assigned count bằng 0

Một readiness check đơn giản như:

~~~java
if (assignedPartitions.isEmpty()) {
    return Health.down().build();
}
~~~

có thể tạo false negative khi pod là consumer dư hợp lệ hoặc group đang rebalance.

Một policy thực tế hơn cần ít nhất:

1. Listener container đã start chưa?
2. Pod có nằm trong nhóm instance bắt buộc phải nhận partition không?
3. Tổng partition và consumer count hiện tại ra sao?
4. Group đã Stable đủ lâu chưa?
5. Các partition bắt buộc có member nào đang xử lý không?
6. Lag/oldest record age có vượt SLO không?
7. Assignment rỗng kéo dài bao lâu?
8. Đây là trạng thái dự kiến trong scale/deployment hay sự cố?

Có thể chia health status thành:

- **UP:** container running và assignment/processing phù hợp với topology.
- **UNKNOWN/STARTING:** chưa đủ thời gian để assignment hoàn tất.
- **DEGRADED:** một member không có assignment nhưng group vẫn xử lý workload.
- **DOWN/OUT_OF_SERVICE:** toàn group không có consumer xử lý partition bắt buộc hoặc freshness SLO bị vi phạm.

Đây là ví dụ phân loại ứng dụng, không phải enum bắt buộc của Spring Kafka. Chọn mapping sang Kubernetes readiness theo mục tiêu triển khai.

## 36. Không dùng liveness để chữa assignment rỗng

Liveness probe thất bại thường dẫn tới restart container/pod. Nếu consumer không có partition vì concurrency lớn hơn partition count, restart không làm xuất hiện partition mới.

Một vòng lặp nguy hiểm:

    Pod không có partition
          |
          v
    Liveness đánh fail
          |
          v
    Kubernetes restart pod
          |
          v
    Consumer group rebalance
          |
          v
    Pod mới lại không có partition
          |
          v
    Liveness fail lần nữa

Kết quả là rebalance storm và workload có thể kém ổn định hơn.

Dùng liveness để phát hiện process không còn tiến triển ở mức JVM/application. Dùng readiness và group-level monitoring để thể hiện khả năng xử lý workload. Không dùng restart như cách ép assignor giao partition cho một member cụ thể.

## 37. Quy trình chẩn đoán theo thứ tự

Khi một listener báo không nhận partition:

1. **Xác nhận đúng group ID.** Đọc runtime config/annotation và so với group đang xem.
2. **Xác nhận đúng topic.** Kiểm tra tên topic, regex pattern và cluster.
3. **Kiểm tra partition count.** Topic có partition phù hợp không?
4. **Kiểm tra listener lifecycle.** Container đã start chưa?
5. **Kiểm tra member count.** Tổng consumer threads có vượt partition count không?
6. **Xem group state.** Stable, PreparingRebalance, CompletingRebalance hay Empty?
7. **Xem member assignment.** Một member rỗng hay toàn group rỗng?
8. **Kiểm tra assignor và subscription.** Các member có cùng strategy/tập topic phù hợp không?
9. **Kiểm tra rebalance churn.** Poll quá chậm, restart, network hoặc static membership conflict?
10. **Kiểm tra ACL/metadata.** Consumer có đọc/describe/join group được không?
11. **Phân biệt pause và idle.** Partition có được assign nhưng đang pause hoặc topic không có record?
12. **Kiểm tra offset riêng.** auto.offset.reset và retention chỉ sau khi xác nhận assignment.
13. **Đối chiếu lag và committed offsets.** Có member khác đang xử lý không?
14. **Chọn recovery đúng nguyên nhân.** Sửa group/topic/config/partition/capacity; tránh restart mù.

Quy trình này giúp không nhầm lỗi cấu hình với trạng thái dư consumer được dự kiến.

## 38. Các tình huống thực tế

### 38.1. Một pod trong ba pod không có partition

Topic có sáu partition, group có ba pod, concurrency=2. Tổng sáu consumers; mỗi consumer có thể nhận một partition. Nếu một pod không có assignment, kiểm tra member count và assignment của hai pod còn lại. Có thể là group chưa ổn định hoặc listener của pod đó subscribe khác.

### 38.2. Sáu pod nhưng chỉ hai partition

Mỗi pod concurrency=1, group có sáu members nhưng chỉ hai partition. Bốn pod không có assignment là bình thường. Không cần restart hoặc tăng partition nếu throughput hiện tại đáp ứng SLA.

### 38.3. Group Stable nhưng tất cả assignment rỗng

Kiểm tra subscription có khớp topic không, group ID có đúng không, topic có partition không và member có subscribe topic phù hợp không. Nếu group description cho thấy tất cả member rỗng trong khi topic có partition, kiểm tra assignor/subscription và metadata.

### 38.4. Group liên tục PreparingRebalance

Kiểm tra consumer processing time, max.poll.interval.ms, network, pod restart và group.instance.id trùng. Một group không ổn định có thể không giữ assignment lâu đủ để xử lý.

### 38.5. Có assignment nhưng không có record

Kiểm tra producer traffic, committed offsets, pause state và topic partition. Đây có thể là idle bình thường, không phải assignment failure.

### 38.6. Có assignment nhưng poll lỗi authorization

Kiểm tra ACL và credentials. Assignment và fetch permission là hai vấn đề khác nhau; sửa quyền thay vì tăng partition count.

## 39. Recovery: khi nào tăng partition, khi nào giảm consumer?

Chỉ tăng partition khi throughput/parallelism thực sự cần và các hệ quả nghiệp vụ đã được đánh giá.

**Tăng partition có thể phù hợp khi:**

- Consumer capacity bị giới hạn bởi số partition.
- Có đủ key distribution và broker capacity.
- Có thể chấp nhận thay đổi key-to-partition mapping với producer partitioner.
- Ordering chỉ cần trong partition và được thiết kế phù hợp.

**Giảm concurrency/replicas có thể phù hợp khi:**

- Nhiều consumer không có assignment kéo dài.
- Mỗi pod/consumer dư gây overhead không cần thiết.
- Autoscaler đang scale theo metric không phù hợp và tạo dư thừa.
- Dependency không chịu được số consumer hiện tại.

**Không thay đổi topology khi:**

- Group đang rebalance ngắn hạn.
- Topic/subscription/group ID đang sai.
- ACL hoặc metadata lỗi.
- Consumer bị pause hoặc xử lý chậm.
- Lỗi thực tế là offset invalid chứ không phải assignment.

Không có thao tác tăng partition nào sửa được group ID sai hoặc topic pattern không khớp.

## 40. Kiểm thử assignment trong Spring Kafka

Dùng Embedded Kafka hoặc Testcontainers với broker tương thích để kiểm tra assignment thật.

Một kịch bản:

1. Tạo topic `orders.created` có ba partition.
2. Tạo listener group `order-workers` với concurrency=3.
3. Chờ assignment ổn định qua callback hoặc container metadata.
4. Xác nhận tổng assignment của group bằng ba.
5. Tạo thêm hai consumer member trong cùng group.
6. Xác nhận có member không nhận partition nhưng group vẫn xử lý đủ ba partition.
7. Gửi record vào từng partition.
8. Xác nhận record được xử lý bởi một member hợp lệ.
9. Kiểm tra committed offsets và lag sau khi xử lý.
10. Dừng một member, chờ rebalance và xác nhận partition được phân phối lại.

Không assert một partition cụ thể luôn thuộc consumer có client ID cố định nếu assignor có thể thay đổi assignment. Nên assert invariant: mỗi partition được giao tối đa một member trong group và tổng assignment bao phủ tập partition subscribed phù hợp.

## 41. Kiểm thử trường hợp group không nhận partition

Một test cần bao phủ các lỗi cấu hình:

**Topic pattern không khớp:** listener subscribe pattern không match topic; xác nhận không có assignment và log cho thấy subscription thực tế.

**Group ID sai:** listener dùng group khác với group mà test đang mô tả; xác nhận member xuất hiện trong group runtime.

**Topic chưa có partition:** kiểm tra listener không thể nhận dữ liệu từ topic chưa được provision; test phải quản lý auto-create để kết quả xác định.

**Consumer dư:** tạo nhiều consumer hơn partition; xác nhận member dư có assignment rỗng nhưng không bị coi là lỗi toàn group.

**Rebalance:** thêm/bớt member và xác nhận assignment có thể tạm thời thay đổi trước khi Stable.

**Manual assignment:** kiểm tra listener dùng `topicPartitions` có đúng partition được cấu hình và không phụ thuộc kỳ vọng group assignor.

## 42. Kiểm thử readiness policy

Health test nên xác nhận readiness theo topology, không chỉ theo một snapshot rỗng.

Các trường hợp:

| Container | Group state | Group assignment | Kết quả mong đợi |
|---|---|---|---|
| Chưa start | Empty | Không có | Not ready |
| Running mới start | PreparingRebalance | Chưa ổn định | Starting/unknown trong grace period |
| Running | Stable | Đủ partition, member này rỗng do dư consumer | Pod vẫn có thể ready |
| Running | Stable | Toàn group rỗng dù partition bắt buộc tồn tại | Degraded/Not ready |
| Running | Stable | Có assignment, topic chưa có record | Ready nếu các điều kiện khác đạt |
| Running, paused | Stable | Có assignment | Ready hay degraded theo pause/SLO policy |
| Stopped | Empty | Không có | Not ready nếu listener là bắt buộc |

Readiness check không nên gọi AdminClient với timeout dài ở mỗi probe. Có thể cập nhật group snapshot định kỳ bằng một monitor có giới hạn, cache kết quả trong thời gian ngắn và xử lý lỗi telemetry rõ ràng.

## 43. Runbook khi group không nhận partition

Khi sự cố xảy ra ở production:

1. Ghi lại application instance, listener ID, group ID và topic.
2. Xác nhận listener container có running.
3. Kiểm tra topic tồn tại và partition count.
4. Mô tả consumer group, member count, state và assignments.
5. Xác định chỉ một member hay toàn group không có partition.
6. So sánh số consumer threads toàn group với partition count.
7. Xác nhận tất cả members có subscription/assignor tương thích.
8. Kiểm tra log rebalance, heartbeat, poll và authentication.
9. Kiểm tra group.instance.id có trùng không.
10. Kiểm tra pause state và NonResponsiveConsumerEvent.
11. Đối chiếu committed offset, lag và oldest record age.
12. Sửa đúng nguyên nhân: topic, group ID, regex, ACL, concurrency, partition count hoặc timeout.
13. Chờ group Stable và xác nhận assignment mới.
14. Gửi test record an toàn và xác nhận listener xử lý.
15. Theo dõi lag/commit progress sau phục hồi.
16. Ghi lại thay đổi topology/config và cập nhật readiness expectation.

Không reset offset hoặc xóa consumer group để chữa assignment rỗng khi chưa xác định nguyên nhân. Các thao tác đó có thể làm mất tiến độ hoặc tạo thêm rebalance mà không sửa cấu hình sai.

## 44. Những lỗi thiết kế thường gặp

| Sai sót | Hậu quả | Cách xử lý |
|---|---|---|
| Coi mọi pod phải có partition | False unhealthy khi consumer dư | Readiness theo topology/group |
| Chỉ nhìn một member | Bỏ sót member khác đang xử lý | Kiểm tra toàn group assignment |
| Nhầm listener ID với group ID | Điều tra nhầm group | Cấu hình groupId rõ ràng |
| Tăng concurrency khi partition ít | Tạo thêm consumer dư | Tính replicas × concurrency |
| Tăng partition để sửa topic pattern | Không sửa subscription sai | Kiểm tra regex/topic trước |
| Dùng liveness restart khi assignment rỗng | Rebalance storm | Phân biệt liveness và readiness |
| Nhầm idle với no assignment | Alert sai | Đo assigned partitions riêng |
| Nhầm pause với lost assignment | Recovery sai | Theo dõi pause và assignment riêng |
| Coi auto.offset.reset là assignment policy | Thay offset không cần thiết | Chẩn đoán assignment trước |
| Bỏ qua group state | Restart khi rebalance bình thường | Chờ Stable có timeout |
| Dùng manual assignment nhưng kỳ vọng assignor | Partition bị giao sai/không giao | Xác minh mode subscription |
| Dùng group.instance.id trùng | Member fencing/membership conflict | Identity duy nhất |
| Gọi KafkaConsumer từ health thread | Vi phạm thread safety | Dùng snapshot/callback/AdminClient |
| Dựa vào isRunning() để kết luận khỏe | Container chạy nhưng không có assignment | Kết hợp group/lag/freshness |
| Alert chỉ theo assigned count | Không phản ánh workload còn được xử lý | Ghép assignment và SLO |

## 45. Checklist triển khai production

- Đã xác định topic và partition count thực tế?
- Listener đang dùng đúng cluster và group ID?
- `@KafkaListener` khai báo topics, topicPattern hay topicPartitions?
- Pattern có match topic thật không?
- Tổng replicas × concurrency có vượt partition count không?
- Các member trong group có subscription tương thích?
- Group state có ổn định hay đang rebalance liên tục?
- Assignment được kiểm tra ở cấp member và toàn group?
- Consumer assignor có tương thích giữa các member?
- group.instance.id có duy nhất?
- Container đã running và không bị stop/pause ngoài ý muốn?
- ACL/credentials có cho phép subscribe/fetch/commit?
- max.poll.interval.ms và processing duration có phù hợp?
- Health check phân biệt pod readiness với group health?
- Consumer dư có được coi là trạng thái hợp lệ?
- Có metric assigned partitions, member count, lag và rebalance?
- Có integration tests cho group Stable, consumer dư, pattern sai và rebalance?
- Có runbook xác minh offset trước khi reset/recover?

## 46. Kết luận

**Consumer group không nhận partition** có thể là một lỗi cấu hình hoặc một trạng thái hợp lệ do topology. Trước khi can thiệp, cần phân biệt một member không có assignment với toàn group không có assignment, rồi xác nhận topic, partition count, group ID, subscription, concurrency và group state.

Trong Spring Kafka, listener container running không chứng minh consumer đã nhận partition. Ngược lại, một member có assignment rỗng cũng không nhất thiết làm service mất khả năng xử lý nếu các member khác vẫn sở hữu toàn bộ partition bắt buộc. Readiness cần đánh giá theo **khả năng của cả workload và freshness SLO**, có grace period cho startup/rebalance và không dùng liveness restart để ép Kafka assign partition.

Khi chẩn đoán có hệ thống từ topic metadata, group description, rebalance callbacks, container lifecycle và consumer metrics, đội vận hành có thể sửa đúng nguyên nhân mà không tạo rebalance storm, reset offset sai hoặc đánh dấu unhealthy những pod đang ở trạng thái chờ hợp lệ.
