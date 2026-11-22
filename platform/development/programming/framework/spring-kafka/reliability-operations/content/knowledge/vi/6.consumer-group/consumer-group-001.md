# Partition assignment và ownership

Trong Kafka consumer group, partition assignment xác định consumer member nào chịu trách nhiệm đọc từng partition của topic. Ownership là trạng thái một consumer member đang được giao quyền xử lý một partition trong group tại một thời điểm. Hai khái niệm này quyết định cách Kafka phân phối tải, duy trì thứ tự trong partition, phục hồi khi consumer rời group và xử lý việc scale ứng dụng.

Trong Spring Kafka, mỗi Kafka listener container quản lý một hoặc nhiều KafkaConsumer. Khi listener dùng group management thông thường, các consumer tham gia group bằng cùng group ID và Kafka phân phối partition cho các member. Spring Kafka quản lý vòng đời consumer, listener thread, commit offset và callback rebalance; thuật toán phân phối vẫn thuộc cơ chế consumer group của Kafka.

Điều quan trọng là phân biệt ba khái niệm:

- **Partition leader** là broker giữ vai trò leader của partition trên cluster. Broker leader xử lý các request đọc và ghi của partition.
- **Consumer group coordinator** là broker điều phối membership và rebalance của group.
- **Partition owner** là consumer member được assignment giao xử lý partition trong một consumer group.

Một partition có thể có nhiều consumer group đọc độc lập. Nhưng trong cùng một group, tại một thời điểm ổn định, một partition chỉ được giao cho tối đa một consumer member. Đây là cơ sở để các consumer trong group chia tải mà không chủ ý xử lý đồng thời cùng một partition.

## 1. Consumer group và partition ownership

Consumer group là tập hợp các consumer có cùng group ID. Mỗi member tham gia group bằng cách đăng ký subscription cho một hoặc nhiều topic. Kafka dùng thông tin membership và subscription để tạo assignment.

Ví dụ topic orders có sáu partition và group orders-service có ba consumer member:

~~~text
Topic orders:  P0  P1 | P2  P3 | P4  P5
Owner:          A   A |  B   B |  C   C

Consumer group: orders-service
~~~

Sơ đồ chỉ minh họa một assignment có thể có. Thuật toán assignor và subscription thực tế quyết định partition nào thuộc member nào.

Nếu group có ít consumer hơn partition, một consumer có thể sở hữu nhiều partition. Nếu group có nhiều consumer hơn số partition được subscribe, một số consumer không được giao partition và không nhận record từ các partition đó. Tăng số consumer vượt quá số partition không làm tăng khả năng đọc song song của topic đó.

Ownership được xác định trong phạm vi group:

- Consumer A trong group orders-service có thể sở hữu partition P0.
- Consumer X trong group fraud-service cũng có thể đọc P0.
- Hai consumer thuộc hai group khác nhau có offset và tiến độ độc lập.
- Trong cùng group orders-service, P0 không được giao cho cả Consumer A và Consumer B trong assignment ổn định.

Vì vậy, tạo thêm group ID mới thường có nghĩa là tạo một luồng đọc độc lập, không phải thêm một worker vào cùng nhóm xử lý.

## 2. Ai quyết định partition assignment?

Trong giao thức consumer group truyền thống (classic group protocol), quy trình có các vai trò sau:

1. Consumer kết nối đến Kafka và gửi yêu cầu tham gia group với group ID, member identity và subscription.
2. Group coordinator quản lý membership, generation và trạng thái rebalance.
3. Các member trao đổi metadata về subscription và khả năng assignor.
4. Một member được chọn làm group leader trong giao thức classic; member này chạy partition assignor để tính assignment cho toàn group.
5. Assignment được gửi lại qua coordinator để các member nhận phần partition của mình.
6. Mỗi consumer bắt đầu fetch từ các partition được giao và tiếp tục duy trì membership.

Group leader trong quy trình này là một consumer member có nhiệm vụ tính assignment. Nó không phải broker leader của topic partition. Group coordinator là broker điều phối group; nó cũng không phải consumer xử lý record.

Kafka có các thế hệ giao thức consumer group khác nhau. Với classic protocol, mô hình group leader chạy assignor phía client là cách giải thích phổ biến. Các phiên bản Kafka mới cũng phát triển consumer group protocol mới, trong đó một số trách nhiệm assignment được chuyển về phía broker. Chi tiết triển khai phụ thuộc phiên bản broker và client, nhưng nguyên tắc ownership trong group vẫn giữ nguyên.

Các thông tin quan trọng khi tham gia group gồm:

- **group.id**: định danh group. Consumer muốn chia tải và dùng chung tiến độ commit phải tham gia cùng group ID.
- **Subscription**: tập topic mà consumer muốn đọc, hoặc subscription theo pattern.
- **Partition assignor**: thuật toán quyết định phân phối partition giữa các member.
- **Member identity**: nhận diện consumer member trong group.
- **Generation**: phiên bản membership/assignment của group. Khi rebalance hoàn tất, generation mới đại diện cho membership mới.

## 3. Vòng đời của assignment

Partition assignment không phải một cấu hình bất biến. Nó có thể thay đổi khi consumer tham gia, rời group, mất heartbeat, subscription thay đổi hoặc metadata topic thay đổi.

Một vòng đời điển hình:

~~~text
Consumer khởi động
       |
       v
Subscribe topic / join group
       |
       v
Coordinator ghi nhận membership
       |
       v
Rebalance và tính assignment
       |
       v
Consumer nhận partition được giao
       |
       v
Poll record và xử lý
       |
       +------ membership thay đổi? ------+
       |                                   |
       | Không                             | Có
       v                                   v
Tiếp tục xử lý                       Revoke / release
                                           |
                                           v
                                  Assignment mới
                                           |
                                           v
                                  Consumer sở hữu
                                  partition mới
~~~

Một rebalance có thể xảy ra trong các tình huống:

- Consumer mới khởi động và tham gia group.
- Consumer shutdown hoặc đóng consumer.
- Consumer bị crash hoặc mất kết nối.
- Consumer không gửi heartbeat trong giới hạn cho phép.
- Consumer không gọi poll đúng hạn và vượt max.poll.interval.ms.
- Subscription topic hoặc pattern thay đổi.
- Topic được tạo thêm partition hoặc metadata làm thay đổi tập partition.
- Group member thay đổi do triển khai, autoscaling hoặc sự cố hạ tầng.

Khi assignment thay đổi, một số partition có thể được thu hồi từ member cũ và giao cho member mới. Consumer cần ngừng nhận công việc mới trên partition bị revoke và hoàn tất hoặc hủy an toàn công việc đang dở trước khi relinquish ownership. Kafka quản lý quyền đọc trong group, nhưng không thể tự fencing một side effect đang chạy ở database hoặc hệ thống ngoài Kafka; ứng dụng phải xử lý trường hợp đó bằng idempotency hoặc cơ chế fencing riêng. Đây cũng là thời điểm cần commit offset theo chính sách nếu consumer vẫn còn quyền hợp lệ để làm vậy.

## 4. Eager rebalance và cooperative rebalance

Rebalance có thể thu hồi partition theo hai cách tổng quát: eager và cooperative.

### Eager rebalance

Với eager assignment protocol, khi group cần rebalance, các member thu hồi toàn bộ partition đang sở hữu. Sau khi group tính assignment mới, mỗi member nhận lại tập partition tương ứng.

~~~text
Trước rebalance:
  Consumer A: P0, P1
  Consumer B: P2, P3

Eager revoke:
  Consumer A: (không giữ partition)
  Consumer B: (không giữ partition)

Sau rebalance:
  Consumer A: P0, P2
  Consumer B: P1, P3
~~~

Trong khoảng thời gian rebalance, các partition bị thu hồi có thể tạm thời không được consumer nào xử lý. Khi group lớn hoặc có nhiều partition, thời gian dừng này có thể làm tăng consumer lag.

### Cooperative rebalance

Cooperative rebalance cho phép chuyển partition theo từng bước. Chỉ các partition cần chuyển owner mới bị thu hồi; partition vẫn thuộc member cũ có thể tiếp tục được giữ. Sau một hoặc nhiều vòng rebalance, group đạt assignment mới.

~~~text
Trước:
  Consumer A: P0, P1
  Consumer B: P2, P3

Mục tiêu mới:
  Consumer A: P0, P2
  Consumer B: P1, P3

Vòng cooperative:
  A thu hồi P1
  B thu hồi P2
  P0 và P3 tiếp tục thuộc owner cũ

Assignment hoàn tất:
  Consumer A: P0, P2
  Consumer B: P1, P3
~~~

Cooperative protocol giảm lượng partition phải dừng và chuyển trong một lần rebalance. Nó thường giúp giảm gián đoạn khi group có nhiều member hoặc nhiều partition. Tuy nhiên, ứng dụng vẫn cần xử lý revoke callback và việc partition chuyển owner; cooperative không có nghĩa là không còn rebalance.

Kafka có assignor hỗ trợ cooperative protocol, chẳng hạn CooperativeStickyAssignor. Khi cấu hình nhiều assignor để rolling upgrade, cần tuân theo hướng dẫn tương thích của phiên bản Kafka client; không tùy tiện trộn assignor eager và cooperative trong một cấu hình không hợp lệ.

## 5. Các partition assignor phổ biến

Assignor nhận tập partition cần phân phối và tập consumer member đủ điều kiện, sau đó tạo ánh xạ member-to-partitions. Mỗi chiến lược tối ưu một mục tiêu khác nhau.

### RangeAssignor

RangeAssignor phân phối các partition theo từng topic. Với mỗi topic, partition được sắp theo thứ tự và chia thành các dải liên tiếp cho các consumer member đã subscribe topic đó.

Ví dụ topic orders có năm partition và hai consumer:

~~~text
orders: P0 P1 P2 P3 P4

Consumer A: P0 P1 P2
Consumer B: P3 P4
~~~

Khi số partition không chia hết cho số consumer, một số consumer nhận thêm một partition. Với nhiều topic, phép chia được thực hiện riêng cho từng topic nên tổng số partition giữa các consumer có thể lệch đáng kể nếu subscription khác nhau hoặc số partition mỗi topic khác nhau.

Range có thể phù hợp khi muốn các partition liên tiếp thuộc cùng một consumer, nhưng không phải lúc nào cũng tạo phân phối tổng thể cân bằng nhất.

### RoundRobinAssignor

RoundRobinAssignor sắp xếp các partition và phân phối lần lượt cho các consumer đủ điều kiện theo vòng tròn.

Ví dụ:

~~~text
Partition: P0 P1 P2 P3 P4 P5
Consumer:   A  B  C  A  B  C

Consumer A: P0, P3
Consumer B: P1, P4
Consumer C: P2, P5
~~~

Round robin thường tạo phân phối đều hơn trên tổng tập partition khi các consumer có subscription tương tự. Nếu consumer subscribe các tập topic khác nhau, chỉ các member đủ điều kiện mới nhận partition tương ứng và kết quả có thể không chia đều hoàn hảo.

### StickyAssignor

StickyAssignor hướng đến hai mục tiêu: cân bằng số partition và giữ assignment cũ nhiều nhất có thể. Khi membership thay đổi, nó cố gắng chỉ di chuyển lượng partition cần thiết để đạt assignment mới cân bằng.

Giữ assignment ổn định giúp giảm chi phí khởi tạo lại xử lý, cache cục bộ, state và kết nối tài nguyên gắn với partition. StickyAssignor dùng eager rebalance protocol.

### CooperativeStickyAssignor

CooperativeStickyAssignor kết hợp mục tiêu cân bằng và hạn chế di chuyển của sticky assignment với cooperative rebalance protocol. Các partition không cần chuyển owner có thể tiếp tục được xử lý trong khi những partition cần chuyển được revoke theo từng bước.

Đây là lựa chọn thường được cân nhắc cho group có nhiều partition hoặc cần giảm gián đoạn khi scale. Khả năng sử dụng và mặc định phụ thuộc phiên bản Kafka client, broker và giao thức group đang dùng.

### So sánh nhanh

| Assignor | Mục tiêu chính | Hành vi khi membership thay đổi |
|---|---|---|
| RangeAssignor | Chia các dải partition theo từng topic | Có thể tạo nhiều partition movement và eager rebalance |
| RoundRobinAssignor | Phân phối lần lượt trên tập partition | Có thể cân bằng tổng thể, nhưng assignment có thể thay đổi khi member thay đổi |
| StickyAssignor | Cân bằng và giữ assignment cũ | Hạn chế partition movement, dùng eager protocol |
| CooperativeStickyAssignor | Cân bằng, giữ assignment cũ và chuyển dần | Chỉ revoke partition cần chuyển qua cooperative protocol |

Không có assignor tốt nhất cho mọi hệ thống. Lựa chọn phụ thuộc số topic, số partition, subscription của từng member, chi phí chuyển state, yêu cầu cân bằng và mức gián đoạn chấp nhận được.

## 6. Cấu hình partition assignment trong Spring Kafka

Spring Boot chuyển các thuộc tính producer và consumer đến Kafka client. Assignor là consumer property, vì vậy có thể khai báo trong cấu hình consumer:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Tên class cần tồn tại trong phiên bản Kafka client đang sử dụng. Nếu dùng nhiều assignor cho quá trình chuyển đổi rolling, hãy cấu hình danh sách theo định dạng mà Kafka client yêu cầu và kiểm tra khả năng tương thích giữa các member.

Có thể cấu hình bằng Java:

~~~java
Map<String, Object> consumerProps = new HashMap<>();
consumerProps.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092");
consumerProps.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "orders-service");
consumerProps.put(
        ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
        CooperativeStickyAssignor.class.getName());
~~~

Đây là cấu hình cho Kafka consumer factory. Trong ứng dụng Spring Boot thực tế, cần cấu hình deserializer, security, offset reset và các thuộc tính liên quan khác.

Không nên chỉ thay assignor rồi kỳ vọng toàn bộ group tự chuyển sang cooperative trong mọi trường hợp. Tất cả member tham gia group cần có cấu hình và phiên bản tương thích. Khi triển khai rolling upgrade, hãy làm theo quy trình chuyển đổi của Kafka cho assignor và protocol đang dùng.

## 7. Ownership trong Spring Kafka listener container

Spring Kafka tạo consumer và điều phối chúng thông qua listener container. Với ConcurrentMessageListenerContainer, thuộc tính concurrency tạo nhiều child KafkaMessageListenerContainer; mỗi child quản lý một KafkaConsumer riêng.

Ví dụ:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
~~~

Listener dùng factory trên:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "kafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    process(event);
}
~~~

Với cấu hình trên, container tạo ba consumer member trong group orders-service. Nếu topic có ít nhất ba partition và tất cả member subscribe cùng topic, mỗi member có thể nhận một hoặc nhiều partition tùy assignment. Nếu topic chỉ có hai partition, một trong ba consumer có thể không được giao partition.

Concurrency là số consumer thread do container quản lý, không phải số partition và cũng không đảm bảo mỗi thread luôn nhận đúng một partition. Assignment thực tế còn phụ thuộc:

- Số partition của topic.
- Số child consumer trong container.
- Số instance ứng dụng đang chạy cùng group ID.
- Subscription của từng listener/member.
- Partition assignor.

Nếu ứng dụng chạy ba replica và mỗi replica có concurrency bằng 3, group có thể có tổng cộng chín consumer member cho listener đó. Với topic chỉ có sáu partition, ít nhất ba member sẽ không được giao partition trong assignment ổn định. Tăng concurrency vượt số partition có thể tăng số thread và tài nguyên mà không tăng khả năng đọc song song.

### Nhiều topic và nhiều listener

Khi một consumer subscribe nhiều topic, assignor xét subscription của từng member. Nếu listener khác nhau subscribe các tập topic khác nhau nhưng dùng chung group ID, cần hiểu rằng Kafka phân phối partition dựa trên subscription hợp lệ của từng member. Không nên dùng chung group ID một cách tùy tiện cho các listener có mục đích nghiệp vụ độc lập, vì chúng có thể cạnh tranh assignment hoặc tạo ra phân phối ngoài dự kiến.

Thông thường, các consumer xử lý cùng một luồng nghiệp vụ và cùng schema/logic nên dùng chung group ID để chia tải. Các ứng dụng cần nhận toàn bộ sự kiện độc lập nên dùng group ID riêng.

## 8. Callback khi partition được revoke hoặc assign

Khi rebalance xảy ra, ứng dụng có thể cần hoàn tất công việc đang dở, lưu state cục bộ hoặc ghi nhận thay đổi ownership. Kafka Consumer API cung cấp ConsumerRebalanceListener với các callback:

- onPartitionsRevoked: partition sắp bị thu hồi trong eager rebalance hoặc bị chuyển đi trong cooperative rebalance.
- onPartitionsAssigned: partition mới được giao cho consumer.
- onPartitionsLost: partition đã mất ownership, thường do consumer không còn là member hợp lệ hoặc group đã chuyển tiếp; không nên giả định còn đủ thời gian để commit.

Ví dụ với Kafka Consumer API:

~~~java
consumer.subscribe(
        List.of("orders"),
        new ConsumerRebalanceListener() {
            @Override
            public void onPartitionsRevoked(
                    Collection<TopicPartition> partitions) {
                flushPartitionState(partitions);
                commitOffsetsFor(partitions);
            }

            @Override
            public void onPartitionsAssigned(
                    Collection<TopicPartition> partitions) {
                initializePartitionState(partitions);
            }

            @Override
            public void onPartitionsLost(
                    Collection<TopicPartition> partitions) {
                discardOwnershipState(partitions);
            }
        });
~~~

Đoạn mã minh họa API Kafka consumer. Trong Spring Kafka, có thể đăng ký ConsumerRebalanceListener thông qua container properties hoặc cấu hình container phù hợp với phiên bản Spring Kafka. Cần kiểm tra chữ ký API cụ thể của phiên bản dự án.

Callback revoke nên hoàn thành nhanh. Nếu callback thực hiện database call hoặc flush state quá lâu, rebalance có thể kéo dài và làm consumer lag tăng. Không nên gọi commit đồng bộ một cách tùy tiện trong callback; hãy hiểu rõ ack mode, commit strategy và giới hạn thời gian của group.

Với cooperative rebalance, callback revoke chỉ nhận các partition thực sự bị thu hồi ở vòng hiện tại. Không được giả định tất cả partition sẽ luôn bị revoke. Callback assign cũng có thể được gọi qua nhiều vòng để group hoàn tất assignment.

## 9. Partition ownership và offset là hai trạng thái khác nhau

Ownership xác định consumer nào được phép đọc và xử lý partition trong group. Offset thể hiện vị trí tiến độ đọc và vị trí đã commit để group phục hồi sau restart hoặc rebalance. Hai khái niệm liên quan nhưng không đồng nhất.

Ví dụ:

- Consumer A sở hữu partition P0.
- Consumer A đã đọc đến offset 120.
- Offset commit gần nhất là 115.
- Consumer A mất membership và P0 được giao cho Consumer B.
- Consumer B tiếp tục từ offset đã commit theo isolation và reset policy liên quan, có thể đọc lại các record từ offset 116.

Việc B đọc lại một số record là hành vi bình thường của at-least-once khi offset chưa được commit sau xử lý. Ownership mới không tự động chứng minh các record trước đó đã được xử lý thành công.

Trong Spring Kafka, ack mode quyết định thời điểm container commit offset:

| Ack mode | Ý nghĩa khái quát |
|---|---|
| RECORD | Commit offset sau khi listener xử lý xong từng record, theo cơ chế container |
| BATCH | Commit sau khi xử lý xong batch record từ lần poll |
| TIME | Commit theo khoảng thời gian khi có record đã xử lý |
| COUNT | Commit khi đạt số lượng record được cấu hình |
| COUNT_TIME | Kết hợp ngưỡng số lượng và thời gian |
| MANUAL | Listener xác nhận qua Acknowledgment; container commit theo quy tắc manual |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge theo điều kiện luồng gọi và cấu hình container |

Tên và chi tiết hành vi cần đối chiếu phiên bản Spring Kafka. Dù chọn ack mode nào, ứng dụng cần hiểu khoảng cách giữa record đã xử lý và offset đã commit. Nếu consumer mất ownership trước khi commit, record có thể được giao lại cho member mới.

Không được tiếp tục xử lý hoặc commit offset của partition sau khi consumer đã mất ownership. Nếu một tác vụ bất đồng bộ tiếp tục chạy sau khi listener trả về, cần thiết kế để tác vụ không gây side effect trùng khi partition được giao cho consumer khác.

## 10. Manual assignment và group-managed assignment

Kafka hỗ trợ hai cách nhận partition:

### Subscribe và group management

Với subscribe(), consumer tham gia group và Kafka quản lý membership, rebalance và assignment.

~~~java
consumer.subscribe(List.of("orders"));
~~~

Đây là cách dùng thông thường khi nhiều instance Spring Kafka cần chia tải và tự phục hồi khi member thay đổi.

### Assign partition thủ công

Với assign(), ứng dụng chỉ định trực tiếp các TopicPartition mà consumer sẽ đọc:

~~~java
consumer.assign(List.of(
        new TopicPartition("orders", 0),
        new TopicPartition("orders", 1)));
~~~

Manual assignment không tham gia cơ chế group-managed assignment và rebalance tự động như subscribe(). Ứng dụng chịu trách nhiệm quyết định member nào đọc partition nào và xử lý việc chuyển owner khi instance thay đổi. Không thể gọi subscribe() và assign() đồng thời trên cùng consumer.

Trong Spring Kafka, listener có thể dùng thuộc tính topicPartitions để chỉ định partition cụ thể. Đây là cách phù hợp cho một số workload cố định hoặc khi ứng dụng cần kiểm soát assignment rõ ràng. Tuy nhiên, cần tự thiết kế việc phân phối partition giữa các instance và tránh hai instance cùng được cấu hình đọc một partition nếu không muốn xử lý trùng.

Manual assignment không phải giải pháp mặc định để tăng hiệu năng. Nó loại bỏ cơ chế điều phối tự động của group, nên đổi lại ứng dụng phải chịu trách nhiệm vận hành và phục hồi.

## 11. Static membership và giảm rebalance không cần thiết

Mỗi lần một consumer member rời group và tham gia lại, group có thể cần rebalance. Với ứng dụng thường restart do rolling deployment hoặc bảo trì, những thay đổi membership liên tục có thể tạo ra nhiều lần rebalance.

Static membership cho phép consumer khai báo group.instance.id ổn định. Khi consumer tạm thời mất kết nối trong giới hạn session timeout, coordinator có thể giữ chỗ member thay vì ngay lập tức coi đó là một member mới. Điều này giúp giảm rebalance không cần thiết trong một số kịch bản restart ngắn.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      properties:
        "[group.instance.id]": orders-service-pod-0
~~~

Giá trị group.instance.id phải duy nhất trong group. Nếu hai instance cùng dùng một ID, Kafka có thể loại một member vì trùng static identity. Khi chạy nhiều replica, hãy tạo ID dựa trên ordinal hoặc định danh instance ổn định, không dùng một giá trị chung cho tất cả pod.

Static membership không loại bỏ rebalance khi partition topology hoặc subscription thay đổi. Nó cũng không thay thế heartbeat, session timeout và max.poll.interval.ms. Cần cân nhắc thời gian shutdown, thời gian restart và khả năng instance thực sự quay lại.

## 12. Những cấu hình ảnh hưởng đến membership và rebalance

| Thuộc tính | Vai trò | Điều cần lưu ý |
|---|---|---|
| group.id | Xác định consumer group | Các member muốn chia tải phải dùng cùng group ID. |
| partition.assignment.strategy | Chọn assignor | Các member cần có cấu hình tương thích. |
| heartbeat.interval.ms | Chu kỳ heartbeat với classic protocol | Thường cần nhỏ hơn session.timeout.ms; giá trị quá nhỏ làm tăng traffic. |
| session.timeout.ms | Thời gian coordinator chờ heartbeat trước khi loại member theo classic protocol | Quá thấp có thể gây rebalance do lỗi mạng ngắn; quá cao làm phục hồi chậm. |
| max.poll.interval.ms | Khoảng tối đa giữa các lần poll | Xử lý một batch quá lâu có thể khiến consumer bị xem là không tiến triển và rời group. |
| max.poll.records | Số record tối đa trả về trong một lần poll | Batch quá lớn có thể kéo dài thời gian xử lý và ảnh hưởng max.poll.interval.ms. |
| group.instance.id | Định danh static member | Phải duy nhất trong group. |
| partition.assignment.strategy | Danh sách assignor được hỗ trợ | Cần đồng bộ tương thích trong quá trình rolling upgrade. |

Các tham số heartbeat và session timeout có hành vi phụ thuộc group protocol. Với classic protocol, heartbeat.interval.ms và session.timeout.ms là những tham số quan trọng để điều phối membership. Với consumer group protocol mới, một số tham số và trách nhiệm được quản lý khác đi. Hãy kiểm tra tài liệu Kafka client đúng phiên bản thay vì sao chép cấu hình giữa các phiên bản.

max.poll.interval.ms đặc biệt quan trọng khi listener xử lý lâu. Nếu một consumer gọi poll quá thưa, group có thể loại member và giao partition cho consumer khác. Khi consumer cũ tiếp tục hoàn tất tác vụ chậm, nó có thể tạo side effect trùng nếu ứng dụng không kiểm soát ownership và idempotency.

## 13. Theo dõi ownership và rebalance trong production

Để hiểu một partition đang thuộc member nào, cần quan sát trạng thái group, member và lag. Một số lệnh Kafka CLI hữu ích:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service
~~~

Lệnh describe hiển thị topic, partition, offset đã commit, log end offset và lag theo định dạng hỗ trợ của phiên bản Kafka.

Để xem member và assignment chi tiết hơn, nhiều phiên bản Kafka hỗ trợ:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
~~~

Tùy phiên bản, có thể dùng thêm lệnh xem trạng thái group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service \
  --state
~~~

Các tùy chọn CLI có thể khác theo bản phân phối và phiên bản Kafka. Hãy kiểm tra kafka-consumer-groups.sh --help của môi trường đang vận hành.

Nên theo dõi:

- Số member hiện tại và trạng thái group.
- Partition assignment theo từng member.
- Số lần rebalance và thời gian hoàn tất rebalance.
- Consumer lag theo partition, không chỉ tổng lag.
- Số partition không có consumer owner khi group ổn định.
- Thời gian xử lý listener và thời gian giữa các lần poll.
- Log về partition revoked, assigned và lost.
- Tỷ lệ commit lỗi và số record được xử lý lại sau rebalance.

Spring Kafka cho phép cấu hình log và listener để ghi nhận assignment. Khi cần điều tra, hãy ghi group ID, client ID, member ID, partition và generation nếu có thể lấy từ consumer metadata. Không log payload nhạy cảm chỉ để theo dõi rebalance.

## 14. Các tình huống vận hành thường gặp

### Consumer mới tham gia và group rebalance liên tục

Nếu autoscaler tạo và xóa pod thường xuyên, group membership thay đổi liên tục. Eager rebalance có thể làm nhiều partition tạm dừng xử lý mỗi lần thay đổi. Hãy xem lại chính sách scale, readiness, graceful shutdown, cooperative assignor và static membership nếu phù hợp.

### Một consumer nhận nhiều partition hơn các consumer khác

Kiểm tra assignor, subscription của member và số partition mỗi topic. RangeAssignor có thể tạo lệch tổng thể khi nhiều topic được chia độc lập. RoundRobin hoặc Sticky có thể phù hợp hơn, nhưng cần thử nghiệm với subscription thực tế.

### Một số consumer không có partition

Nếu số consumer lớn hơn số partition đủ điều kiện, đây là kết quả bình thường. Kiểm tra concurrency và số replica để tránh tạo quá nhiều consumer không có việc. Nếu topic có nhiều partition nhưng một consumer vẫn không nhận partition, hãy kiểm tra subscription, group ID và trạng thái member.

### Consumer bị loại khỏi group khi xử lý record lâu

Đo thời gian xử lý từng poll batch. Giảm max.poll.records, tối ưu listener, tăng max.poll.interval.ms nếu phù hợp và tránh blocking lâu trong luồng consumer. Nếu chuyển xử lý sang executor bất đồng bộ, phải quản lý offset và ownership cẩn thận vì listener có thể hoàn tất trước khi nghiệp vụ thực sự xong.

### Record bị xử lý lặp sau rebalance

Kiểm tra offset commit gần nhất, ack mode, thời điểm listener hoàn tất và thời điểm partition bị revoke. Thiết kế consumer idempotent theo event ID để xử lý an toàn khi record được giao lại. Rebalance không tự tạo duplicate trong log; duplicate quan sát được thường đến từ việc đọc lại record chưa commit hoặc side effect được thực hiện trước khi offset được commit.

### Rebalance kéo dài

Kiểm tra thời gian callback revoke, thời gian xử lý listener, số partition, assignor, heartbeat, session timeout và các lần GC pause hoặc network interruption. Không đặt timeout lớn tùy tiện để che một listener bị treo; hãy xác định nguyên nhân làm consumer không poll hoặc không heartbeat đúng hạn.

## 15. Những hiểu nhầm thường gặp

**Mỗi consumer luôn nhận đúng một partition.** Không đúng. Một consumer có thể sở hữu nhiều partition; một số consumer có thể không được giao partition nếu member nhiều hơn partition.

**Partition assignment do broker leader của topic quyết định.** Không đúng. Broker leader phục vụ partition; group coordinator điều phối membership. Thuật toán assignment được thực hiện theo group protocol và assignor đang dùng.

**Group leader là partition leader.** Không đúng. Trong classic group protocol, group leader là consumer member tính assignment. Partition leader là broker.

**Mỗi consumer group chỉ có thể có một consumer.** Không đúng. Group có nhiều member để chia partition và xử lý song song.

**Hai group không thể đọc cùng partition.** Không đúng. Mỗi group có offset và assignment riêng; nhiều group có thể đọc cùng topic độc lập.

**Tăng concurrency luôn tăng throughput.** Không đúng. Song song tối đa còn phụ thuộc số partition, broker capacity, xử lý listener và hệ thống downstream. Consumer vượt số partition có thể không được giao partition.

**Cooperative rebalance loại bỏ hoàn toàn gián đoạn.** Không đúng. Nó giảm số partition phải revoke cùng lúc, nhưng partition chuyển owner vẫn cần quy trình revoke và assign.

**Partition được giao cho consumer nghĩa là record đã được xử lý.** Không đúng. Ownership chỉ xác định member có trách nhiệm đọc partition. Offset commit và hoàn tất nghiệp vụ là các trạng thái khác.

**Manual assignment vẫn tự rebalance như subscribe().** Không đúng. Khi dùng assign(), ứng dụng tự chịu trách nhiệm phân phối và chuyển ownership.

## 16. Hướng dẫn thiết kế

Khi thiết kế consumer group cho một workload Spring Kafka, hãy xác định trước số partition, số instance và mức song song cần thiết. Dùng cùng group ID cho các consumer cần chia tải; dùng group ID riêng cho các luồng đọc độc lập.

Một cấu hình triển khai có thể bắt đầu theo trình tự:

1. Chọn số partition theo throughput, thứ tự nghiệp vụ và khả năng mở rộng.
2. Đặt group ID ổn định cho từng luồng xử lý độc lập.
3. Chọn assignor phù hợp với số topic, subscription và mức gián đoạn chấp nhận được.
4. Cấu hình concurrency sao cho phù hợp với số partition và tài nguyên xử lý.
5. Thiết lập heartbeat, session timeout và max.poll.interval.ms theo group protocol và thời gian xử lý thực tế.
6. Dùng graceful shutdown để consumer có cơ hội hoàn tất và revoke partition đúng cách.
7. Cấu hình ack mode và commit strategy phù hợp với nghiệp vụ.
8. Thiết kế consumer idempotent để xử lý record được giao lại sau rebalance.
9. Theo dõi member, assignment, rebalance, lag và lỗi commit.
10. Kiểm thử các tình huống scale up, scale down, restart, mất mạng và xử lý listener chậm.

Partition assignment xác định consumer nào chịu trách nhiệm đọc partition; ownership thay đổi theo membership và rebalance. Hiểu rõ assignor, giao thức rebalance, concurrency và offset giúp hệ thống scale có kiểm soát, giảm thời gian dừng khi chuyển owner và phục hồi an toàn khi consumer gặp sự cố.
