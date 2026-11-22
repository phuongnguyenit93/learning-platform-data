# Cách các consumer chia sẻ partition

Kafka dùng **consumer group** để chia việc đọc một topic giữa nhiều consumer. Mỗi group có một định danh riêng là group.id; các consumer cùng group phối hợp nhận partition để xử lý dữ liệu song song. Trong một group, tại một thời điểm, mỗi partition được gán cho tối đa một consumer member. Một consumer có thể nhận nhiều partition, còn consumer không được gán partition nào sẽ ở trạng thái rảnh.

Cơ chế này giúp tăng khả năng xử lý bằng cách chia partition cho nhiều consumer. Giới hạn song song đến từ số partition: thêm consumer không tạo thêm partition và cũng không làm một partition được xử lý đồng thời bởi nhiều member trong cùng group.

Trong Spring Kafka, @KafkaListener tham gia cơ chế này thông qua groupId và cấu hình consumer. Thuộc tính concurrency tạo nhiều consumer con cho một listener endpoint, để Kafka phân phối partition giữa các consumer đó.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách group.id xác định một nhóm consumer cùng chia sẻ partition.
- Mô tả quan hệ giữa số partition, số consumer và mức song song thực tế.
- Phân biệt consumer cùng group với consumer thuộc các group khác nhau.
- Giải thích vai trò của group coordinator và partition assignor.
- Nhận biết các nguyên nhân kích hoạt rebalance và ảnh hưởng đến việc đọc record.
- Cấu hình groupId, concurrency và partition assignment strategy trong Spring Kafka.
- Ước lượng giới hạn throughput từ số partition và năng lực xử lý mỗi consumer.
- Kiểm tra partition assignment, consumer lag và trạng thái group khi vận hành.

## 1. Consumer group chia sẻ công việc như thế nào?

Topic được chia thành các partition. Mỗi partition là một log có thứ tự riêng và có thể được đọc độc lập với partition khác. Consumer group cho phép nhiều consumer cùng đọc một topic nhưng mỗi partition chỉ được giao cho tối đa một member trong group tại cùng thời điểm.

Ví dụ topic orders có bốn partition và group order-service có hai consumer:

~~~text
Topic orders
+---------+---------+---------+---------+
|    P0   |    P1   |    P2   |    P3   |
+---------+---------+---------+---------+
     |         |         |         |
     +----+----+         +----+----+
          |                   |
          v                   v
     Consumer A          Consumer B
     P0, P1               P2, P3

Consumer group: order-service
~~~

Consumer A đọc partition 0 và 1; Consumer B đọc partition 2 và 3. Cả hai cùng thuộc một group nên phối hợp chia công việc. Nếu Consumer A dừng, Kafka có thể kích hoạt rebalance để partition của A được giao cho member còn lại.

Các nguyên tắc cốt lõi:

- Một partition không được gán đồng thời cho hai member trong cùng consumer group.
- Một consumer có thể được gán nhiều partition.
- Các consumer cùng group cùng chia một luồng dữ liệu; trong assignment ổn định, một member đọc partition đó. Record vẫn có thể được giao lại nếu xử lý chưa hoàn tất hoặc offset chưa được commit.
- Mỗi consumer group có offset riêng cho từng partition.
- Partition khác nhau không có thứ tự toàn cục với nhau.

Câu “một partition chỉ có một consumer” cần hiểu đúng phạm vi: đó là một consumer member trong một group tại một thời điểm. Một topic vẫn có thể được nhiều group khác nhau đọc độc lập.

## 2. Số partition giới hạn số consumer hoạt động

Với một topic có P partition và một consumer group có C consumer member, số consumer có thể nhận ít nhất một partition tối đa là min(P, C).

Ví dụ topic có sáu partition:

| Số partition | Consumer trong group | Kết quả có thể có |
|---:|---:|---|
| 6 | 1 | Một consumer đọc cả sáu partition |
| 6 | 2 | Hai consumer, mỗi consumer khoảng ba partition |
| 6 | 3 | Ba consumer, mỗi consumer khoảng hai partition |
| 6 | 6 | Sáu consumer, mỗi consumer một partition |
| 6 | 8 | Tối đa sáu consumer có partition; hai consumer còn lại rảnh |

Sơ đồ khi có nhiều consumer hơn partition:

~~~text
Topic orders: P0  P1  P2  P3

Consumer A:   P0
Consumer B:   P1
Consumer C:   P2
Consumer D:   P3
Consumer E:   (không có partition)
Consumer F:   (không có partition)
~~~

Consumer E và F vẫn có thể là member của group, nhưng không có dữ liệu từ topic này để đọc. Tăng số consumer từ bốn lên sáu không làm tăng mức song song của topic bốn partition.

Ngược lại, nếu có ít consumer hơn partition, mỗi consumer nhận nhiều partition. Điều này vẫn cho phép đọc song song giữa các partition, nhưng các partition được giao cho cùng consumer sẽ dùng chung consumer thread khi listener xử lý đồng bộ.

**Giới hạn quan trọng:** một topic chỉ có một partition thì trong một group chỉ có một consumer member nhận partition đó. Nếu cần tăng khả năng xử lý song song cho topic, cần thiết kế số partition ngay từ đầu theo tải và yêu cầu thứ tự nghiệp vụ.

## 3. Consumer group khác nhau nhận dữ liệu độc lập

Hai consumer thuộc cùng group chia nhau partition. Hai consumer thuộc hai group khác nhau có thể đọc toàn bộ topic độc lập với nhau.

Ví dụ topic orders có ba partition và hai group:

~~~text
                         Topic orders
                    +------+------+------+
                    |  P0  |  P1  |  P2  |
                    +------+------+------+
                       |      |      |
             +---------+------+------+
             |                        |
             v                        v
      Group: billing             Group: analytics
      Consumer B1                Consumer A1
      Consumer B2                Consumer A2
      Consumer B3                Consumer A3

      Mỗi group có assignment riêng cho cả P0, P1, P2.
~~~

Group billing có thể xử lý sự kiện để cập nhật thanh toán; group analytics có thể đọc cùng sự kiện để tổng hợp báo cáo. Việc group này commit offset không làm thay đổi offset của group kia.

Offset được lưu theo group và partition. Vì vậy, cùng một record có thể được mỗi group đọc ở thời điểm khác nhau, hoặc được một group replay mà không làm thay đổi tiến độ của group còn lại.

Đây là nền tảng của mô hình publish-subscribe:

- Producer gửi một record vào topic.
- Mỗi consumer group là một luồng tiêu thụ độc lập.
- Các member bên trong một group chia nhau partition.
- Các group khác nhau nhận dữ liệu độc lập theo offset riêng.

Không tạo một consumer group mới cho từng consumer nếu mục tiêu là chia tải giữa chúng. Nếu mỗi consumer có group.id khác nhau, mỗi consumer sẽ đọc toàn bộ dữ liệu theo tiến độ riêng, làm tăng số lần xử lý và tải broker.

## 4. Group coordinator và partition assignor

Khi consumer dùng subscribe(), nó tham gia consumer group. Một broker được chọn làm **group coordinator** quản lý membership, heartbeat, generation và quá trình đồng bộ assignment.

Partition assignor quyết định cách phân phối các partition của topic cho member trong group. Coordinator phối hợp với các member để hoàn tất assignment theo group protocol.

Luồng tham gia group ở mức khái quát:

~~~mermaid
sequenceDiagram
    participant A as Consumer A / Group Leader
    participant B as Consumer B
    participant G as Group Coordinator
    A->>G: JoinGroup
    B->>G: JoinGroup
    G-->>A: Chọn A làm group leader (classic protocol)
    A->>A: Assignor tính partition assignment
    A->>G: Gửi assignment của các member
    G-->>A: Assignment cho A
    G-->>B: Assignment cho B
    A->>G: Heartbeat
    B->>G: Heartbeat
~~~

Trong classic consumer group protocol, group coordinator quản lý membership và chọn group leader; assignor chạy ở group leader để tính assignment rồi gửi kết quả về coordinator. Coordinator phân phối assignment cho các member. Với consumer group protocol mới, broker có thể đảm nhiệm việc tính assignment thông qua server-side assignor. Coordinator theo dõi member thông qua heartbeat và các mốc tiến triển của consumer. Khi membership hoặc subscription thay đổi, group có thể cần tính lại assignment.

Partition assignor có thể sử dụng các chiến lược khác nhau:

| Strategy | Cách phân phối khái quát | Đặc điểm |
|---|---|---|
| RangeAssignor | Chia các dải partition liên tiếp cho consumer theo từng topic | Dễ hiểu; có thể tạo phân phối lệch giữa các consumer khi nhiều topic |
| RoundRobinAssignor | Luân phiên phân phối partition cho các consumer đủ điều kiện | Có thể phân phối đều hơn giữa nhiều topic nếu subscription tương thích |
| StickyAssignor | Cố gắng cân bằng và giữ lại assignment cũ nhiều nhất có thể | Giảm số partition phải chuyển khi group thay đổi |
| CooperativeStickyAssignor | Sticky assignment với cơ chế cooperative/incremental rebalance | Có thể thu hồi và gán lại partition theo từng bước, giảm việc dừng toàn bộ group |

Chiến lược có sẵn và hành vi mặc định phụ thuộc phiên bản Kafka client, broker và group protocol. Hãy kiểm tra cấu hình thực tế thay vì mặc định rằng mọi cluster đều dùng cùng một assignor.

### Cấu hình partition assignment strategy

Trong classic consumer group protocol, client có thể cấu hình partition.assignment.strategy. Ví dụ chọn cooperative sticky assignor:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Tất cả consumer member trong cùng group cần có cấu hình tương thích. Khi thay đổi assignor trong môi trường đang chạy, hãy triển khai theo hướng dẫn tương thích của Kafka client và phiên bản broker; thay đổi không đồng bộ có thể làm group không thống nhất chiến lược assignment.

Các phiên bản Kafka hỗ trợ consumer group protocol mới có thể chuyển một phần việc chọn assignor sang broker. Khi dùng protocol đó, cách cấu hình và các property liên quan có thể khác classic protocol. Hãy kiểm tra tài liệu theo đúng phiên bản Kafka đang sử dụng.

## 5. Rebalance: chia lại partition khi group thay đổi

**Rebalance** là quá trình consumer group tính toán và phân phối lại partition cho các member. Rebalance cần thiết để group tiếp tục hoạt động khi số consumer hoặc tập partition thay đổi.

Các nguyên nhân thường gặp:

- Consumer mới tham gia group.
- Consumer dừng bình thường hoặc bị crash.
- Consumer không gửi heartbeat trong thời gian session cho phép.
- Consumer không tiếp tục gọi poll() trong giới hạn max.poll.interval.ms.
- Subscription của member thay đổi.
- Topic được thêm partition hoặc topic pattern phát hiện topic mới.
- Một số thay đổi cấu hình hoặc trạng thái group yêu cầu assignment mới.

Ví dụ ban đầu có hai consumer:

~~~text
Trước rebalance:
P0  P1  P2  P3  P4  P5
|   |   |   |   |   |
+---+---+---+   +---+---+
        |           |
    Consumer A  Consumer B
      P0-P3       P4-P5
~~~

Khi Consumer C tham gia, group có thể phân phối lại:

~~~text
Sau rebalance:
P0  P1  P2  P3  P4  P5
|   |   |   |   |   |
+---+   +---+   +---+
  |       |       |
Consumer A Consumer B Consumer C
  P0-P1     P2-P3     P4-P5
~~~

Sơ đồ chỉ minh họa một kết quả cân bằng; assignment thật phụ thuộc assignor và membership.

Trong quá trình rebalance, partition có thể bị thu hồi khỏi consumer cũ rồi giao cho consumer mới. Listener có thể tạm dừng nhận thêm record. Nếu record đã xử lý nhưng offset chưa commit, record có thể được giao lại sau rebalance. Vì vậy, consumer nên xử lý idempotent.

### Eager và cooperative rebalance

Với eager rebalance, group có thể thu hồi toàn bộ partition đang được giao trước khi phân phối lại. Điều này làm gián đoạn xử lý rộng hơn trong thời gian rebalance.

Cooperative rebalance cho phép thu hồi và chuyển giao partition theo từng bước. Nó có thể giảm phạm vi gián đoạn vì partition không cần thay đổi owner có thể tiếp tục được xử lý. Tuy nhiên, nó không loại bỏ mọi rebalance hoặc mọi khả năng xử lý lặp.

Chọn assignor phù hợp và giữ thời gian xử lý listener trong giới hạn là hai yếu tố quan trọng để giảm rebalance không cần thiết.

## 6. Cấu hình consumer group trong Spring Boot

Một consumer cần group-id để tham gia nhóm và lưu offset theo nhóm. Spring Boot có thể cấu hình group ID và các thuộc tính listener:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      concurrency: 3
~~~

Trong ví dụ:

- group-id: order-service đặt tên group cho consumer.
- enable-auto-commit: false để Spring Kafka listener container quản lý commit offset theo acknowledgement mode.
- auto-offset-reset: earliest quy định vị trí bắt đầu khi group chưa có committed offset hợp lệ hoặc offset đã ngoài phạm vi log.
- concurrency: 3 yêu cầu listener container tạo tối đa ba consumer con cho endpoint mặc định.

auto-offset-reset không có nghĩa mỗi lần ứng dụng khởi động consumer đều đọc lại từ đầu. Nếu group đã có committed offset hợp lệ, consumer tiếp tục từ vị trí đã lưu.

Trong ứng dụng có nhiều listener, có thể đặt concurrency riêng cho từng endpoint hoặc tạo container factory riêng. Hãy kiểm tra factory mà listener thực sự sử dụng để tránh cấu hình ở một factory nhưng endpoint lại dùng factory khác.

## 7. Chia partition bằng @KafkaListener concurrency

Ví dụ listener xử lý sự kiện đơn hàng:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "order-listener",
        topics = "orders",
        groupId = "order-service",
        concurrency = "3"
    )
    public void handle(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

Với topic có sáu partition, concurrency bằng ba tạo ba consumer con trong cùng group. Group coordinator và assignor phân phối partition cho ba consumer đó.

Một cách cấu hình tương đương là đặt concurrency trên container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

Listener tham chiếu factory:

~~~java
@KafkaListener(
    id = "order-listener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerContainerFactory"
)
public void handle(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

Không cần đồng thời đặt nhiều giá trị concurrency mâu thuẫn. Hãy chọn nơi cấu hình phù hợp với cách tổ chức listener của ứng dụng.

### Quan hệ giữa concurrency và partition

Với một endpoint xử lý một topic:

- Nếu số partition lớn hơn concurrency, một consumer con có thể nhận nhiều partition.
- Nếu số partition bằng concurrency, mỗi consumer con có thể nhận một partition.
- Nếu số partition nhỏ hơn concurrency, một số consumer con không có partition.
- Khi concurrency thay đổi, group có thể rebalance để phân phối lại assignment.

Concurrency chỉ tạo thêm consumer trong ứng dụng. Nó không tăng số partition và không bảo đảm throughput tăng tuyến tính. Nếu hệ thống đích như database hoặc HTTP service đã bão hòa, thêm consumer có thể chỉ làm tăng số request đồng thời và áp lực lên dependency.

## 8. Consumer group và thứ tự xử lý

Kafka bảo đảm thứ tự record trong từng partition theo offset. Khi một consumer nhận nhiều partition, nó có thể đọc các partition đó trong cùng poll loop, nhưng không có thứ tự toàn cục giữa chúng.

Ví dụ các sự kiện cùng đơn hàng dùng orderId làm key:

~~~java
kafkaTemplate.send("orders", orderId, event);
~~~

Các record cùng key thường được định tuyến vào cùng partition với partitioner mặc định khi số partition và cấu hình routing không thay đổi. Vì thế, consumer xử lý partition đó có thể đọc các sự kiện theo thứ tự offset.

Khi có nhiều consumer trong cùng group:

- Mỗi partition vẫn chỉ được giao cho một consumer member tại một thời điểm.
- Các partition khác nhau có thể được xử lý song song.
- Record của cùng partition được giao theo thứ tự offset.
- Nếu listener tự chuyển công việc sang executor hoặc xử lý bất đồng bộ, thứ tự hoàn tất side effect có thể khác thứ tự record đã nhận.
- Rebalance có thể chuyển partition sang consumer khác; ứng dụng cần chịu được record được giao lại.

Nếu nghiệp vụ cần thứ tự theo thực thể, hãy chọn key phù hợp và tránh xử lý song song các record cùng partition theo cách làm đảo thứ tự cập nhật.

## 9. Static membership và giảm rebalance khi restart

Kafka hỗ trợ static membership thông qua group.instance.id trong classic consumer group protocol. Member có định danh instance ổn định có thể giữ membership qua một số lần restart ngắn thay vì bị xem ngay là member mới.

Ví dụ property:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": order-worker-1
~~~

Giá trị group.instance.id phải duy nhất giữa các instance đang hoạt động trong cùng group. Không dùng cùng một giá trị cho nhiều replica của ứng dụng vì coordinator có thể phát hiện member trùng và fencing một member.

Static membership có thể giảm rebalance khi rolling restart, nhưng có đánh đổi: partition có thể tiếp tục được giữ bởi member tạm thời mất kết nối cho đến khi session hết hạn. Hãy chọn session timeout phù hợp với thời gian restart và mục tiêu failover.

Trong Spring Kafka, nếu nhiều consumer con được tạo từ một concurrent container, cần bảo đảm mỗi consumer có định danh instance phù hợp và duy nhất theo yêu cầu của Kafka client/phiên bản đang dùng. Không sao chép một group.instance.id cố định cho tất cả consumer con.

## 10. Consumer group khi scale ứng dụng

Giả sử ứng dụng order-service có sáu partition và ba replica. Mỗi replica cấu hình concurrency bằng hai, tổng cộng có tối đa sáu consumer member trong group:

~~~text
Kubernetes / Application replicas
  order-service-1: consumer 1, consumer 2
  order-service-2: consumer 3, consumer 4
  order-service-3: consumer 5, consumer 6

Consumer group: order-service
Topic: orders (6 partitions)
~~~

Khi scale từ ba lên bốn replica mà concurrency vẫn bằng hai, group có tám consumer member nhưng topic chỉ có sáu partition. Tối đa sáu consumer nhận partition; hai consumer còn lại rảnh.

Khi scale down, consumer rời group và partition được phân phối lại cho member còn lại. Nếu ứng dụng dừng đột ngột, coordinator cần phát hiện member mất thông qua heartbeat/session hoặc cơ chế poll progress trước khi rebalance hoàn tất.

Một số lưu ý vận hành:

- Tổng consumer member bằng số replica nhân concurrency của mỗi replica nếu mọi replica dùng cùng endpoint.
- Số consumer có ích bị giới hạn bởi tổng số partition mà group subscribe.
- Scale lên quá số partition không làm tăng song song của topic.
- Scale down có thể tăng số partition trên mỗi consumer và tải xử lý trên từng thread.
- Rebalance tạo một khoảng gián đoạn và có thể làm tăng record được giao lại.
- Khi thay đổi partition count, assignor có thể phân phối lại partition và thay đổi consumer sở hữu chúng.

## 11. Theo dõi consumer group bằng Kafka CLI

Có thể dùng Kafka CLI để xem group, member và partition assignment.

Liệt kê group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Xem offset và lag của group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
~~~

Xem member và partition assignment trên các phiên bản CLI hỗ trợ:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service \
  --members \
  --verbose
~~~

Kết quả mô tả thường giúp xác định:

- Consumer group có bao nhiêu member.
- Member nào được gán partition nào.
- Current offset của group.
- Log end offset và consumer lag.
- Partition nào chưa có consumer xử lý.

Cú pháp và trường hiển thị có thể khác giữa phiên bản Kafka. Hãy dùng script đi kèm đúng phiên bản broker/client.

## 12. Quan sát trong Spring Kafka

Trong ứng dụng Spring Kafka, nên theo dõi đồng thời trạng thái listener container và consumer group:

- Consumer lag theo group và partition.
- Số consumer member đang hoạt động.
- Partition assignment của từng listener container.
- Số lần rebalance và thời gian hoàn tất.
- Thời gian xử lý listener và tỷ lệ lỗi.
- Số record retry, dead-letter và duplicate.
- Thời gian từ lúc nhận record đến khi commit offset.

Một group có lag tăng không nhất thiết do thiếu consumer. Nguyên nhân có thể là listener xử lý chậm, database quá tải, partition nóng, rebalance liên tục hoặc record lỗi bị retry nhiều lần.

Hãy đối chiếu lag theo partition. Nếu chỉ một partition tăng lag trong khi các partition khác ổn định, có thể partition đó nhận phần lớn traffic hoặc chứa một key nóng. Tăng concurrency không giúp phân tán một partition nóng sang nhiều consumer trong cùng group.

## 13. Các lỗi thiết kế thường gặp

**Tạo nhiều consumer với cùng group ID nhưng topic chỉ có ít partition.** Consumer dư sẽ không được gán partition. Kiểm tra số partition trước khi tăng replica hoặc concurrency.

**Mỗi consumer đặt một group ID khác nhau trong khi muốn chia tải.** Mỗi group đọc độc lập toàn bộ topic; dữ liệu sẽ bị xử lý lặp giữa các group. Dùng chung group ID cho các member cần chia việc.

**Tưởng consumer group bảo đảm thứ tự toàn topic.** Kafka chỉ bảo đảm thứ tự trong từng partition. Dùng key để đưa các sự kiện cần thứ tự vào cùng partition.

**Tăng concurrency mà không đo năng lực hệ thống đích.** Nhiều consumer có thể làm database hoặc API bị quá tải. Đo thời gian xử lý, lag và throughput trước khi tăng.

**Listener xử lý quá lâu khiến consumer không poll kịp.** Có thể vượt max.poll.interval.ms và gây rebalance. Tối ưu listener, điều chỉnh max.poll.records và timeout theo thời gian xử lý thực tế.

**Không làm handler idempotent.** Rebalance, restart hoặc lỗi trước commit có thể làm record được giao lại. Dùng event ID, unique constraint hoặc inbox pattern để tránh side effect trùng.

**Dùng static member ID giống nhau trên nhiều instance.** Member có thể bị fencing hoặc group liên tục thay đổi trạng thái. Mỗi instance cần định danh duy nhất nếu sử dụng static membership.

## 14. Kiểm thử cách group chia partition

Kiểm thử tích hợp nên chạy Kafka có đủ partition và nhiều consumer member. Các kịch bản hữu ích:

- Tạo topic sáu partition và khởi chạy ba consumer cùng group; xác nhận group assignment bao phủ sáu partition.
- Tăng số consumer lên tám; xác nhận chỉ tối đa sáu consumer có partition từ topic này.
- Khởi chạy hai group khác nhau; xác nhận mỗi group đọc độc lập cùng record.
- Dừng một consumer; xác nhận partition được phân phối lại cho member còn lại.
- Khởi chạy consumer mới; xác nhận rebalance và assignment sau đó.
- Tăng partition count; xác nhận group cập nhật assignment sau rebalance.
- Gửi nhiều record cùng key; xác nhận chúng cùng partition và listener xử lý theo thứ tự offset.
- Làm listener chậm hoặc ném exception; quan sát poll interval, retry và rebalance.
- Scale ứng dụng lên/xuống; đo lag và thời gian phục hồi.

Trong test, hãy đợi assignment hoàn tất trước khi gửi hoặc xác nhận record. Không dùng sleep cố định ngắn rồi giả định group đã ổn định; dùng trạng thái assignment hoặc điều kiện đồng bộ với timeout rõ ràng.

## 15. Checklist thiết kế consumer group

- [ ] Các consumer cần chia tải có cùng group.id.
- [ ] Các ứng dụng cần đọc độc lập dùng group ID riêng.
- [ ] Số partition đủ cho mức song song mong muốn.
- [ ] Tổng consumer member đã tính cả số replica ứng dụng và concurrency.
- [ ] Partition assignor phù hợp với yêu cầu cân bằng và giảm chuyển partition.
- [ ] Rebalance, restart và consumer failure đã được kiểm thử.
- [ ] Listener xử lý idempotent để chịu được record được giao lại.
- [ ] Key bảo đảm các sự kiện cần thứ tự nằm cùng partition.
- [ ] max.poll.interval.ms và max.poll.records phù hợp với thời gian xử lý.
- [ ] Có dashboard/metric cho assignment, lag, rebalance và lỗi.
- [ ] Static membership chỉ được bật khi có định danh duy nhất và kế hoạch failover rõ ràng.

## Kết luận

Consumer group chia partition bằng cách giao mỗi partition cho tối đa một consumer member trong cùng group tại một thời điểm. Một consumer có thể nhận nhiều partition; nếu số consumer vượt số partition, phần consumer dư sẽ rảnh. Các group khác nhau đọc topic độc lập với offset riêng. Trong Spring Kafka, groupId xác định nhóm và concurrency điều khiển số consumer con cho listener. Hãy thiết kế số partition theo mức song song cần thiết, chọn assignor phù hợp, xử lý rebalance và làm listener idempotent để group hoạt động ổn định khi scale hoặc gặp lỗi.

