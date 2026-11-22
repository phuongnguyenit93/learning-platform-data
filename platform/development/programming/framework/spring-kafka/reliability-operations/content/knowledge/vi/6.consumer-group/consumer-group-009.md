# Cooperative và eager rebalancing

## 1. Rebalancing trong consumer group là gì?

Kafka consumer group chia các partition của topic cho những consumer member cùng group ID. Mỗi partition được gán cho tối đa một consumer trong cùng group tại một thời điểm. Việc phân công này được gọi là partition assignment.

Rebalance là quá trình group điều chỉnh assignment khi trạng thái group hoặc topic thay đổi. Một số nguyên nhân thường gặp:

- Consumer mới tham gia group hoặc một consumer rời group.
- Consumer bị crash, mất kết nối hoặc không gửi heartbeat đúng hạn.
- Consumer không gọi `poll()` trong thời gian cho phép và bị xem là không còn hoạt động.
- Subscription của consumer thay đổi.
- Topic được thêm hoặc bớt partition, hoặc metadata liên quan đến subscription thay đổi.
- Group coordinator cần khôi phục trạng thái group sau sự cố.

Rebalance là cơ chế bình thường của Kafka, giúp phân phối partition giữa các member và tiếp tục xử lý khi topology thay đổi. Tuy nhiên, nó có thể tạm dừng việc tiêu thụ, làm tăng consumer lag và khiến record chưa commit được giao lại.

Có hai chiến lược assignment thường được nhắc đến:

- **Eager rebalancing**: thu hồi toàn bộ partition assignment hiện tại trước khi áp dụng assignment mới.
- **Cooperative rebalancing**: chỉ thu hồi những partition thực sự cần chuyển sang consumer khác; partition vẫn thuộc consumer cũ có thể tiếp tục được giữ.

Sự khác biệt nằm ở cách các partition đang được sở hữu được thu hồi và phân phối lại. Cả hai vẫn dùng consumer group coordination và đều có thể gây gián đoạn trong lúc chuyển quyền sở hữu.

## 2. Eager rebalancing hoạt động như thế nào?

### 2.1. Thu hồi toàn bộ assignment

Với eager rebalancing, khi group cần rebalance, các consumer đang tham gia sẽ thu hồi toàn bộ partition được gán. Sau đó coordinator và partition assignor tính assignment mới rồi phân phối lại cho các member.

Giả sử topic `orders` có 6 partition và group có hai consumer:

~~~text
Trước rebalance

Consumer A: P0, P1, P2
Consumer B: P3, P4, P5
~~~

Một consumer C tham gia. Với eager rebalancing, cả A và B đều phải từ bỏ assignment hiện tại trước khi nhận assignment mới, dù một số partition cuối cùng vẫn quay về đúng consumer cũ.

~~~text
Trong eager rebalance

Consumer A: revoke P0, P1, P2
Consumer B: revoke P3, P4, P5
Consumer C: đang tham gia group

Sau khi phân công lại (ví dụ)

Consumer A: P0, P1
Consumer B: P3, P4
Consumer C: P2, P5
~~~

Trong khoảng thời gian giữa lúc thu hồi và lúc assignment mới có hiệu lực, consumer không tiếp tục xử lý các partition vừa bị thu hồi. Đây là lý do eager rebalance thường được mô tả là một lần dừng toàn group (stop-the-world) đối với việc xử lý các partition của group.

### 2.2. Trình tự ở mức khái quát

Trong classic consumer group protocol, trình tự có thể được hiểu như sau:

1. Consumer phát hiện cần rebalance và tham gia quá trình group coordination.
2. Các member đồng bộ trạng thái subscription và tham gia vòng JoinGroup.
3. Group leader/assignor tính assignment mới.
4. Các member thu hồi assignment cũ theo eager protocol.
5. Assignment mới được phân phối qua SyncGroup.
6. Consumer bắt đầu fetch và xử lý từ vị trí offset tiếp theo theo tiến độ đã commit.

Chi tiết giao thức và cách điều phối có thể khác theo phiên bản Kafka và group protocol đang sử dụng. Điểm quan trọng của eager protocol là toàn bộ assignment cũ phải được thu hồi trước khi assignment mới được áp dụng.

### 2.3. Tác động vận hành

Eager rebalance có một số hệ quả:

- **Tạm dừng xử lý rộng**: ngay cả consumer không mất partition nào trong assignment cuối cùng cũng phải tham gia quá trình thu hồi và nhận lại.
- **Tăng độ trễ phục hồi**: thời gian xử lý có thể dừng trong khi member tham gia group coordination và nhận assignment.
- **Tăng khả năng redelivery**: record đã xử lý nhưng offset chưa commit có thể được giao lại sau rebalance.
- **Có thể gây lag tăng đột ngột**: khi group có nhiều partition hoặc callback xử lý revoke chậm, thời gian dừng càng dài.
- **Đơn giản về trạng thái assignment**: tất cả assignment cũ được thu hồi, nên logic chuyển giao partition có thể dễ hình dung hơn.

Eager rebalancing không có nghĩa mọi record đều bị xử lý trùng. Duplicate chỉ có thể xuất hiện khi tiến độ xử lý chưa được commit hoặc nghiệp vụ có side effect nhưng offset chưa được lưu. Consumer vẫn cần thiết kế idempotent.

## 3. Cooperative rebalancing hoạt động như thế nào?

### 3.1. Thu hồi từng phần

Cooperative rebalancing dùng mô hình incremental: consumer chỉ thu hồi những partition cần chuyển sang member khác. Những partition vẫn được giữ bởi cùng consumer có thể tiếp tục được xử lý trong khi group hoàn tất việc phân phối lại các partition còn lại.

Ví dụ ban đầu vẫn có hai consumer:

~~~text
Trước rebalance

Consumer A: P0, P1, P2
Consumer B: P3, P4, P5
~~~

Consumer C tham gia group. Một assignment cân bằng mới có thể cần chuyển P2 từ A và P5 từ B sang C. Với cooperative rebalancing:

~~~text
Vòng rebalance đầu

Consumer A: giữ P0, P1; revoke P2
Consumer B: giữ P3, P4; revoke P5
Consumer C: chưa nhận P2, P5 trong khi owner cũ chưa nhả

Vòng tiếp theo

Consumer A: P0, P1
Consumer B: P3, P4
Consumer C: P2, P5
~~~

Các partition P0, P1, P3 và P4 không cần bị thu hồi chỉ để phân công lại. Chúng có thể tiếp tục được consumer hiện tại xử lý. P2 và P5 chỉ được chuyển cho C sau khi owner cũ đã nhả chúng.

### 3.2. Vì sao có thể cần nhiều vòng?

Cooperative assignor không thể giao một partition cho consumer mới khi consumer cũ vẫn đang giữ partition đó. Vì vậy, quá trình chuyển giao có thể cần hơn một vòng rebalance:

1. Assignor xác định partition cần di chuyển.
2. Owner hiện tại nhận assignment không còn chứa các partition cần nhả và revoke phần tương ứng.
3. Sau khi quyền sở hữu cũ được thu hồi, group thực hiện vòng phân phối tiếp theo.
4. Consumer mới nhận những partition đã được nhả.

Trong trường hợp thông thường, chuyển giao có thể hoàn tất sau một vòng revoke và một vòng assignment tiếp theo. Với nhiều thay đổi đồng thời hoặc assignment phức tạp, số vòng thực tế phụ thuộc topology và assignor.

Cooperative rebalancing ưu tiên an toàn quyền sở hữu: một partition không được consumer mới bắt đầu xử lý khi consumer cũ chưa nhả partition đó.

### 3.3. CooperativeStickyAssignor

`CooperativeStickyAssignor` là partition assignor của Kafka hỗ trợ cooperative protocol và cố gắng giữ assignment ổn định giữa các lần rebalance.

Assignor này kết hợp hai mục tiêu:

- **Balance**: phân phối partition tương đối cân bằng giữa các consumer.
- **Stickiness**: giữ partition ở consumer hiện tại nếu không cần di chuyển, giảm số partition phải chuyển giao.

Stickiness có ích khi consumer thường xuyên tham gia/rời group hoặc khi group có nhiều partition. Nếu một consumer mới tham gia, assignor có thể chỉ chuyển một số partition cần thiết thay vì phân phối lại toàn bộ assignment.

CooperativeStickyAssignor không loại bỏ rebalance. Nó thay đổi phạm vi partition phải thu hồi và có thể giảm thời gian gián đoạn. Nếu toàn bộ member cùng group vẫn thay đổi liên tục hoặc consumer xử lý chậm, group vẫn có thể trải qua nhiều lần rebalance và lag vẫn tăng.

## 4. So sánh eager và cooperative

| Tiêu chí | Eager rebalancing | Cooperative rebalancing |
|---|---|---|
| Phạm vi revoke | Toàn bộ partition assignment hiện tại | Chỉ partition cần chuyển |
| Partition không đổi owner | Vẫn bị thu hồi rồi gán lại | Có thể tiếp tục ở owner hiện tại |
| Mức gián đoạn | Thường rộng hơn | Thường hẹp hơn |
| Số vòng chuyển giao | Thường một chu kỳ thu hồi và gán lại | Có thể cần nhiều vòng incremental |
| Độ phức tạp vận hành | Mô hình đơn giản hơn | Cần assignor và member tương thích |
| Khả năng giảm lag do rebalance | Hạn chế khi group lớn | Có thể giảm thời gian dừng xử lý |
| Tính liên tục | Group thường dừng rộng trong lúc rebalance | Partition không di chuyển có thể tiếp tục xử lý |
| Tính an toàn | Chờ thu hồi assignment cũ trước khi gán mới | Chỉ giao partition sau khi owner cũ nhả |

Không nên hiểu cooperative là không có downtime hoặc không có duplicate. Nó giảm phạm vi thu hồi partition, nhưng vẫn có thể tạm dừng xử lý partition đang được chuyển. Nếu listener đang thực hiện side effect nhưng chưa commit offset, redelivery vẫn có thể xảy ra.

## 5. Partition assignor quyết định cách phân phối

Kafka consumer dùng partition assignor để tính consumer nào nhận partition nào. Rebalance protocol và assignment strategy liên quan nhưng không phải cùng một khái niệm:

- **Rebalance protocol** quyết định cách group thu hồi và áp dụng assignment.
- **Partition assignor** quyết định partition được phân phối cho member ra sao.

Một số assignor thường gặp:

| Assignor | Cách phân phối | Rebalance protocol |
|---|---|---|
| `RangeAssignor` | Chia partition theo phạm vi trong từng topic | Eager |
| `RoundRobinAssignor` | Phân phối luân phiên partition giữa các consumer | Eager |
| `StickyAssignor` | Cố gắng giữ assignment ổn định khi phân phối lại | Eager |
| `CooperativeStickyAssignor` | Phân phối cân bằng và giữ assignment ổn định theo incremental revoke | Cooperative |

`StickyAssignor` và `CooperativeStickyAssignor` có mục tiêu giữ assignment ổn định nhưng khác protocol. Không thể chỉ đổi tên assignor trong một member rồi giả định toàn group đã chuyển sang cooperative.

Trong một group, các member cần thống nhất được assignor/protocol tương thích. Nếu các member đang chạy cấu hình khác nhau trong quá trình rollout, Kafka phải chọn một chiến lược chung mà các member hỗ trợ; cấu hình không tương thích có thể khiến rebalance thất bại hoặc tạo hành vi không như mong muốn.

## 6. Cấu hình cooperative rebalancing trong Spring Kafka

### 6.1. Cấu hình Spring Boot

Với Kafka client hỗ trợ `CooperativeStickyAssignor`, có thể khai báo:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-service
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Thuộc tính Spring Boot `spring.kafka.consumer.properties` chuyển các Kafka client properties tùy chỉnh đến consumer. Tên property ở phía Kafka client là `partition.assignment.strategy`.

Nếu dùng `application.properties`:

~~~properties
spring.kafka.consumer.group-id=orders-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.properties.partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
spring.kafka.listener.ack-mode=record
~~~

Cần kiểm tra phiên bản Kafka client được Spring Boot quản lý. `CooperativeStickyAssignor` có từ Kafka 2.4; các ứng dụng cũ hơn có thể không có class này hoặc không hỗ trợ cooperative protocol. Không chỉ kiểm tra version Spring Kafka; hãy kiểm tra version `kafka-clients` thực tế trong dependency tree.

### 6.2. Cấu hình Java ConsumerFactory

Nếu tự tạo consumer factory:

~~~java
Map<String, Object> properties = new HashMap<>();

properties.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
properties.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "orders-service"
);
properties.put(
    ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
    false
);
properties.put(
    ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
    CooperativeStickyAssignor.class.getName()
);

ConsumerFactory<String, OrderCreated> consumerFactory =
    new DefaultKafkaConsumerFactory<>(properties);
~~~

Sau đó bảo đảm listener container dùng đúng factory này. Với ứng dụng có nhiều consumer factory hoặc nhiều `@KafkaListener`, không giả định một cấu hình áp dụng cho tất cả container.

### 6.3. Đừng nhầm concurrency với rebalance strategy

Spring Kafka có thể tạo nhiều consumer trong một listener container bằng thuộc tính `concurrency`. Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "3"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

`concurrency` xác định số consumer thread do container tạo. Nó không chọn eager hay cooperative protocol. Rebalance strategy được điều khiển bởi Kafka consumer property `partition.assignment.strategy`.

Số consumer có thể xử lý song song vẫn bị giới hạn bởi số partition được gán. Nếu topic có 3 partition, tăng concurrency lên 8 không tạo ra 8 consumer cùng xử lý một partition trong cùng group.

## 7. Chuyển từ eager sang cooperative

Chuyển đổi cần được thực hiện đồng bộ cho các member trong cùng consumer group. Một member dùng eager assignor trong khi member khác dùng cooperative assignor có thể làm group không thống nhất protocol.

Một cách rollout thường dùng là chuyển theo hai giai đoạn, giữ assignor eager hiện tại cùng cooperative assignor trong danh sách hỗ trợ:

**Giai đoạn 1: triển khai client hỗ trợ cả hai assignor**

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.RangeAssignor,org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Roll từng instance theo cách triển khai an toàn. Trong giai đoạn này, `RangeAssignor` đứng trước nên group vẫn có thể chọn eager assignment khi tất cả member cùng hỗ trợ danh sách đó.

**Giai đoạn 2: chuyển sang cooperative**

Sau khi tất cả member đã chạy cấu hình giai đoạn 1 và group ổn định, cập nhật cấu hình để chỉ dùng:

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Tiếp tục rollout các instance. Khi toàn bộ member đã hỗ trợ cooperative assignor và group thương lượng được chiến lược này, group có thể chuyển sang cooperative rebalancing.

Đây là mẫu migration phổ biến cho classic consumer group protocol. Cần kiểm tra hướng dẫn nâng cấp của Kafka client và framework đang dùng, đặc biệt khi có nhiều ứng dụng cùng chia sẻ group ID hoặc các member không được triển khai đồng thời.

Trước rollout cần:

1. Liệt kê tất cả ứng dụng và instance đang dùng group ID.
2. Xác nhận Kafka client version hỗ trợ cooperative assignor.
3. Kiểm tra danh sách assignor hiện tại và cách framework tạo consumer properties.
4. Triển khai giai đoạn hỗ trợ cả hai assignor cho toàn bộ member.
5. Xác nhận group ổn định và không còn member cũ.
6. Chuyển sang cooperative assignor duy nhất theo rollout có kiểm soát.
7. Theo dõi rebalance count, thời gian rebalance, consumer lag và lỗi callback.

Không nên thay đổi assignor đồng thời với việc đổi group ID, tăng partition count và thay đổi commit policy nếu không cần thiết. Nhiều thay đổi cùng lúc làm khó xác định nguyên nhân khi group không ổn định.

## 8. ConsumerRebalanceListener và vòng đời partition

Kafka cung cấp `ConsumerRebalanceListener` để ứng dụng nhận biết partition được thu hồi và được gán. Hai callback cơ bản là:

- `onPartitionsRevoked(...)`: consumer sắp mất một số hoặc toàn bộ partition.
- `onPartitionsAssigned(...)`: consumer vừa nhận assignment.

Một số phiên bản Kafka còn có callback `onPartitionsLost(...)` để báo partition đã bị mất quyền sở hữu mà không có quá trình revoke bình thường. Cần kiểm tra API theo Kafka client version.

Ví dụ listener cơ bản:

~~~java
public class OrderRebalanceListener implements ConsumerRebalanceListener {

    @Override
    public void onPartitionsRevoked(
        Collection<TopicPartition> partitions
    ) {
        log.info("Partitions revoked: {}", partitions);
        // Hoàn tất công việc có thể hoàn tất và xử lý offset
        // theo chính sách commit của ứng dụng.
    }

    @Override
    public void onPartitionsAssigned(
        Collection<TopicPartition> partitions
    ) {
        log.info("Partitions assigned: {}", partitions);
        // Khởi tạo trạng thái cục bộ cho partition mới nhận.
    }

    @Override
    public void onPartitionsLost(
        Collection<TopicPartition> partitions
    ) {
        log.warn("Partitions lost: {}", partitions);
        // Không giả định consumer vẫn có quyền commit cho các partition này.
    }
}
~~~

Trong cooperative rebalance, danh sách `partitions` trong callback revoke có thể chỉ chứa partition đang được chuyển. Ứng dụng không nên giả định callback luôn nhận toàn bộ assignment.

### 8.1. Công việc cần làm khi revoke

Khi một consumer chuẩn bị nhả partition, ứng dụng có thể cần:

- Dừng nhận thêm công việc mới cho partition sắp bị thu hồi.
- Hoàn tất hoặc hủy công việc đang xử lý theo chính sách.
- Flush trạng thái cục bộ hoặc batch ghi xuống hệ thống ngoài.
- Commit offset cuối cùng nếu ứng dụng tự quản lý commit và vẫn còn quyền sở hữu partition.
- Giải phóng tài nguyên gắn với partition.

Không nên chờ vô hạn trong callback revoke. Callback kéo dài có thể làm group rebalance lâu hơn, khiến consumer khác phải chờ và làm tăng lag.

Với `onPartitionsLost`, partition có thể đã được giao cho member khác. Không giả định có thể commit offset hoặc hoàn tất chuyển giao như callback revoke bình thường.

### 8.2. Công việc khi assigned

Khi nhận partition, consumer có thể cần tạo trạng thái cục bộ, khôi phục cache hoặc bắt đầu theo dõi partition mới. Nếu dùng cooperative protocol, callback assigned có thể được gọi trong các vòng rebalance incremental; ứng dụng phải xử lý assignment theo phần được cung cấp thay vì giả định nhận toàn bộ partition mỗi lần.

Không khởi tạo lại toàn bộ trạng thái consumer nếu chỉ có một partition mới được gán. Dùng map theo `TopicPartition` hoặc cơ chế quản lý trạng thái tương ứng để cập nhật đúng phần assignment.

## 9. ConsumerAwareRebalanceListener trong Spring Kafka

Spring Kafka cung cấp `ConsumerAwareRebalanceListener`, mở rộng callback rebalance của Kafka và cho phép truy cập consumer trong callback. Nó còn cung cấp các hook để kiểm soát thời điểm revoke liên quan đến commit của container.

Các hook thường dùng gồm:

- `onPartitionsRevokedBeforeCommit(...)`: được gọi trước khi container thực hiện commit offset cuối cùng theo chu kỳ revoke.
- `onPartitionsRevokedAfterCommit(...)`: được gọi sau khi container hoàn tất commit tương ứng.
- `onPartitionsAssigned(...)`: được gọi khi partition được gán.
- `onPartitionsLost(...)`: được gọi khi partition bị mất trong các phiên bản hỗ trợ.

Ví dụ khung implementation:

~~~java
public class OrderConsumerRebalanceListener
        implements ConsumerAwareRebalanceListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderConsumerRebalanceListener.class);

    @Override
    public void onPartitionsRevokedBeforeCommit(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions
    ) {
        log.info("Revoking before commit: {}", partitions);
        // Chuẩn bị trạng thái cục bộ trước commit do container quản lý.
    }

    @Override
    public void onPartitionsRevokedAfterCommit(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions
    ) {
        log.info("Revoked after commit: {}", partitions);
        // Giải phóng tài nguyên của các partition đã nhả.
    }

    @Override
    public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions
    ) {
        log.info("Assigned: {}", partitions);
        // Khởi tạo trạng thái cho partition vừa nhận.
    }

    @Override
    public void onPartitionsLost(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions
    ) {
        log.warn("Lost: {}", partitions);
        // Dọn trạng thái cục bộ; không commit như thể vẫn sở hữu partition.
    }
}
~~~

Tên và chữ ký callback có thể thay đổi theo Spring Kafka version. Hãy đối chiếu Javadoc của dependency đang sử dụng trước khi triển khai.

Có thể đăng ký listener trên `ContainerProperties`:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties()
        .setConsumerRebalanceListener(
            new OrderConsumerRebalanceListener()
        );

    return factory;
}
~~~

Sau đó gắn factory vào listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Khi Spring listener container đang quản lý commit, tránh tự commit offset trong callback theo một cách xung đột với acknowledgment mode. Các hook BeforeCommit và AfterCommit giúp ứng dụng phối hợp công việc cục bộ với chu kỳ commit của container mà không vô tình tạo hai chủ sở hữu offset.

## 10. Cooperative rebalancing ảnh hưởng đến xử lý song song ra sao?

Cooperative rebalancing cho phép partition không di chuyển tiếp tục được xử lý, nhưng ứng dụng vẫn cần quản lý công việc đang chạy trên partition bị revoke.

Ví dụ listener xử lý một batch từ P2 trong khi P2 sắp được chuyển từ consumer A sang consumer C. Nếu A vẫn có task bất đồng bộ chạy nền sau khi callback revoke hoàn tất, task đó có thể tiếp tục ghi database hoặc phát event dù C đã bắt đầu xử lý P2. Điều này có thể gây xử lý đồng thời cùng một partition và phá vỡ giả định ordering ở tầng nghiệp vụ.

Với xử lý bất đồng bộ:

- Theo dõi task theo `TopicPartition`.
- Khi partition bị revoke, ngừng phát sinh task mới cho partition đó.
- Hoàn tất hoặc hủy task đang chạy theo deadline.
- Chỉ commit offset tương ứng với các record đã hoàn thành liên tục theo thứ tự cần thiết.
- Không cho task cũ tiếp tục side effect sau khi partition đã bị chuyển.
- Dùng event ID và thao tác idempotent để phòng trường hợp task bị giao lại sau sự cố.

Cooperative protocol bảo đảm quy trình chuyển quyền sở hữu partition ở cấp Kafka. Nó không tự quản lý các thread nền, queue hoặc side effect do ứng dụng tạo ra.

## 11. Các cấu hình khác ảnh hưởng đến tần suất rebalance

Cooperative rebalancing giúp giảm phạm vi revoke, nhưng nguyên nhân gây rebalance vẫn cần được xử lý. Một số cấu hình consumer quan trọng:

| Cấu hình | Tác động |
|---|---|
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trước khi xem member mất kết nối |
| `heartbeat.interval.ms` | Tần suất consumer gửi heartbeat trong classic protocol |
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần poll khi xử lý theo cơ chế consumer |
| `max.poll.records` | Số record tối đa trả về trong một lần poll |
| `partition.assignment.strategy` | Chọn assignor và cách phân phối partition |
| `group.instance.id` | Bật static membership cho consumer member có identity ổn định |
| `group.initial.rebalance.delay.ms` | Khoảng chờ ban đầu để gom member mới tham gia group trong classic protocol |

Các giá trị và tác dụng cụ thể phụ thuộc group protocol và Kafka client version. Ví dụ, heartbeat/session behavior có thể khác khi dùng protocol consumer mới so với classic protocol.

Tăng `session.timeout.ms` không giải quyết listener xử lý quá lâu nếu consumer vi phạm `max.poll.interval.ms`. Tăng `max.poll.interval.ms` cũng không giải quyết broker/network bị lỗi heartbeat. Cần xác định loại timeout gây rebalance trước khi điều chỉnh.

`group.instance.id` có thể giảm rebalance không cần thiết khi một instance restart ngắn hạn và quay lại với cùng identity. Nhưng static membership không thay thế cooperative assignor; đây là hai cơ chế giải quyết những vấn đề khác nhau.

## 12. Các tình huống vận hành và cách điều tra

| Hiện tượng | Eager rebalancing | Cooperative rebalancing | Hướng kiểm tra |
|---|---|---|---|
| Thêm một consumer | Toàn bộ assignment có thể bị thu hồi | Chỉ partition cần chuyển bị revoke | Kiểm tra member join và assignment |
| Một consumer rời group | Các member còn lại thu hồi rồi nhận lại toàn bộ assignment | Partition của member rời group được phân phối incremental | Kiểm tra shutdown và session timeout |
| Listener xử lý lâu | Có thể vượt max poll interval và gây rebalance rộng | Vẫn có thể gây rebalance; partition bị revoke theo incremental protocol | Đo processing time và poll interval |
| Topic tăng partition | Group cần phân phối partition mới và có thể gán lại | Có thể chỉ bổ sung partition mới hoặc chuyển phần cần thiết | Kiểm tra metadata và assignment |
| Consumer restart liên tục | Group có thể rebalance liên tục | Cooperative giảm revoke không cần thiết nhưng không ngăn churn | Kiểm tra restart, health check và static membership |
| Callback revoke chậm | Làm chậm toàn bộ quá trình rebalance | Làm chậm việc nhả partition đang di chuyển | Đo callback duration và công việc cleanup |

### 12.1. Rebalance liên tục

Nếu log liên tục ghi nhận rebalance, cần xác định trigger:

- Pod/container restart hoặc liveness probe không phù hợp.
- Network chập chờn khiến heartbeat bị gián đoạn.
- Listener xử lý quá lâu làm vượt `max.poll.interval.ms`.
- Consumer thread bị block bởi database hoặc service ngoài.
- Group ID hoặc subscription thay đổi giữa các lần triển khai.
- Số member thay đổi liên tục do autoscaling.

Cooperative assignor không chữa được một consumer liên tục rời group. Nó chỉ giúp giảm lượng partition phải thu hồi trong mỗi lần assignment thay đổi.

### 12.2. Rebalance kéo dài

Nếu thời gian rebalance cao, xem:

- Thời gian callback `onPartitionsRevoked`.
- Thời gian callback `onPartitionsAssigned`.
- Số partition trong group và số member.
- Thời gian group coordinator xử lý JoinGroup/SyncGroup.
- Các task đang chạy cần flush hoặc dừng.
- Lỗi metadata hoặc coordinator communication.

Trong cooperative mode, có thể xuất hiện nhiều vòng incremental. Cần xem tổng thời gian từ lúc bắt đầu đến khi assignment ổn định, không chỉ thời gian của một callback.

### 12.3. Duplicate sau rebalance

Nếu một record xuất hiện hai lần sau rebalance, kiểm tra:

1. Listener có hoàn tất side effect trước khi commit offset không?
2. Commit offset có thất bại hoặc chưa được thực hiện khi partition bị revoke không?
3. Có task bất đồng bộ tiếp tục xử lý sau khi partition bị chuyển không?
4. Callback revoke có flush hoặc chờ công việc theo deadline không?
5. Consumer có idempotency key hoặc unique constraint không?

Rebalance có thể làm record chưa commit được giao lại. Đây là hành vi phù hợp với at-least-once processing. Consumer cần xử lý duplicate an toàn thay vì giả định mỗi record chỉ được giao một lần.

## 13. Metrics và log cần theo dõi

Để đánh giá lợi ích của cooperative rebalancing, theo dõi trước và sau khi chuyển đổi bằng cùng một tập chỉ số:

| Chỉ số | Điều cần biết |
|---|---|
| Rebalance count | Group xảy ra bao nhiêu lần rebalance |
| Rebalance duration | Mỗi lần rebalance kéo dài bao lâu |
| Time without assigned partitions | Consumer bị thiếu partition trong bao lâu |
| Partitions revoked | Bao nhiêu partition bị thu hồi mỗi vòng |
| Partitions assigned | Bao nhiêu partition được nhận mỗi vòng |
| Consumer lag | Tiến độ đọc có tụt lại trong lúc rebalance không |
| Poll interval / poll latency | Listener có xử lý lâu hoặc poll chậm không |
| Heartbeat failures | Member có mất heartbeat hoặc coordinator connection không |
| Listener processing duration | Công việc nghiệp vụ có giữ partition quá lâu không |

Tên metric chính xác phụ thuộc Kafka client, Spring Kafka, Micrometer và hệ thống monitoring. Có thể kết hợp Kafka client metrics, Spring Kafka listener/container observations và log callback rebalance.

Log nên có group ID, member ID, topic-partition và loại callback. Với cooperative mode, ghi danh sách partition revoke/assigned giúp xác định incremental assignment có đúng kỳ vọng hay không. Tránh ghi một dòng quá lớn chứa toàn bộ assignment của group nếu số partition rất nhiều; có thể ghi số lượng và chi tiết ở mức debug.

## 14. Kiểm thử cooperative và eager rebalancing

Nên kiểm thử trên Kafka test broker hoặc môi trường tích hợp riêng, dùng topic và group ID không ảnh hưởng dữ liệu production.

### 14.1. Kịch bản eager

1. Tạo topic có 6 partition.
2. Khởi chạy consumer A và B trong cùng group với eager assignor.
3. Ghi nhận assignment ban đầu.
4. Khởi chạy consumer C.
5. Theo dõi `onPartitionsRevoked` và `onPartitionsAssigned` của A, B, C.
6. Xác nhận assignment cũ bị thu hồi toàn bộ trước khi assignment mới được áp dụng.
7. Ghi nhận khoảng thời gian xử lý bị gián đoạn và consumer lag.

### 14.2. Kịch bản cooperative

1. Dùng cùng topic và số partition, nhưng cấu hình tất cả member với `CooperativeStickyAssignor`.
2. Khởi chạy A và B, ghi nhận assignment ban đầu.
3. Khởi chạy C.
4. Theo dõi danh sách partition trong callback revoke và assigned qua từng vòng.
5. Xác nhận partition không cần di chuyển vẫn thuộc consumer cũ.
6. Xác nhận partition chuyển giao chỉ được consumer mới nhận sau khi owner cũ revoke.
7. So sánh thời gian gián đoạn và lag với eager trong cùng điều kiện tải.

### 14.3. Kiểm thử member rời group và xử lý lỗi

Ngoài việc thêm consumer, cần thử:

- Dừng một consumer theo graceful shutdown.
- Kill consumer đột ngột để kiểm tra session timeout.
- Tạo listener xử lý lâu để quan sát `max.poll.interval.ms`.
- Tăng partition count.
- Tạo task bất đồng bộ đang chạy khi partition bị revoke.
- Kiểm tra duplicate và trạng thái commit offset sau khi rebalance.

Khi so sánh, giữ nguyên số partition, throughput, concurrency và thời gian xử lý. Nếu thay đổi nhiều tham số cùng lúc, không thể kết luận cooperative protocol là nguyên nhân của khác biệt.

## 15. Nguyên tắc chọn và vận hành

- Dùng eager khi cần tương thích với client/assignor hiện có hoặc muốn giữ mô hình revoke toàn bộ đơn giản.
- Cân nhắc `CooperativeStickyAssignor` cho group lớn, có nhiều partition hoặc thường xuyên thay đổi member và cần giảm gián đoạn.
- Bảo đảm mọi member trong cùng group hỗ trợ và thống nhất assignor/protocol trước khi chuyển đổi.
- Rollout theo giai đoạn khi migrate từ eager sang cooperative.
- Không giả định cooperative loại bỏ rebalance, duplicate hoặc consumer lag.
- Giữ callback revoke ngắn và có deadline; dọn đúng trạng thái partition đang chuyển.
- Phân biệt `onPartitionsRevoked` với `onPartitionsLost`; không commit khi partition đã mất quyền sở hữu.
- Theo dõi rebalance duration, số partition revoke, consumer lag và thời gian listener.
- Kiểm soát task bất đồng bộ theo topic-partition để task cũ không tiếp tục side effect sau khi partition được chuyển.
- Dùng idempotency ở consumer để xử lý redelivery khi offset chưa commit.

Eager rebalancing thu hồi toàn bộ assignment trước khi phân phối lại, còn cooperative rebalancing chuyển giao từng phần và giữ nguyên những partition không cần di chuyển. Lựa chọn phù hợp phụ thuộc phiên bản client, assignor, quy mô group và cách ứng dụng quản lý công việc khi partition được revoke.
