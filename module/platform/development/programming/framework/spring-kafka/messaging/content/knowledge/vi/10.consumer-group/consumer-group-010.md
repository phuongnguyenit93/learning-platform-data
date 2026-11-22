# Cân bằng số consumer với số partition

## 1. Vì sao phải cân bằng consumer và partition?

Trong Kafka, partition là đơn vị song song cơ bản của một consumer group. Tại một thời điểm, một partition chỉ được gán cho tối đa một consumer member trong cùng group. Một consumer có thể nhận nhiều partition, nhưng nhiều consumer trong cùng group không thể cùng đọc song song một partition theo cơ chế assignment thông thường.

Vì vậy, số partition giới hạn mức song song hữu ích của consumer group. Nếu có ít consumer hơn partition, mỗi consumer sẽ phụ trách nhiều partition. Nếu số consumer bằng số partition, group có thể phân phối gần theo tỷ lệ một consumer cho một partition. Nếu số consumer lớn hơn số partition, một số consumer sẽ không được gán partition và ở trạng thái rảnh đối với topic đó.

Việc chọn số consumer phù hợp giúp cân bằng thông lượng, độ trễ, tài nguyên ứng dụng và chi phí rebalance. Chỉ tăng số consumer không đảm bảo xử lý nhanh hơn; cần xem số partition, tải trên từng partition và năng lực xử lý thực tế của mỗi consumer.

## 2. Quy tắc cơ bản giữa số consumer và partition

Giả sử tất cả consumer trong group cùng subscribe một topic và có cùng phạm vi subscription. Gọi:

- `P`: số partition của topic.
- `C`: số consumer member đang hoạt động trong group.

Mức song song tối đa theo partition có thể ước lượng bằng:

\[
\text{Consumer được gán partition tối đa} = \min(P, C)
\]

Nếu `C > P`, số consumer có thể không được gán partition là:

\[
\text{Consumer rảnh} = \max(C - P, 0)
\]

Đây là quy tắc khái quát cho một topic và cùng subscription. Khi group subscribe nhiều topic, cần tính tổng số partition mà group thực sự nhận assignment; assignor, subscription và cấu hình cụ thể quyết định phân phối cuối cùng.

### Trường hợp consumer ít hơn partition

Ví dụ topic `orders` có 12 partition và group `order-service` có 4 consumer:

```text
Topic orders: P = 12
Consumer group: C = 4

Consumer A  ◀── P0, P1, P2
Consumer B  ◀── P3, P4, P5
Consumer C  ◀── P6, P7, P8
Consumer D  ◀── P9, P10, P11
```

Mỗi consumer phụ trách khoảng 3 partition nếu assignment phân bố đều. Các partition vẫn được xử lý song song giữa bốn consumer; bên trong mỗi consumer, listener container poll dữ liệu từ các partition được gán.

### Trường hợp consumer bằng partition

Nếu topic có 12 partition và group có 12 consumer:

```text
P0  ──▶ Consumer A
P1  ──▶ Consumer B
P2  ──▶ Consumer C
P3  ──▶ Consumer D
P4  ──▶ Consumer E
P5  ──▶ Consumer F
P6  ──▶ Consumer G
P7  ──▶ Consumer H
P8  ──▶ Consumer I
P9  ──▶ Consumer J
P10 ──▶ Consumer K
P11 ──▶ Consumer L
```

Với một topic và các consumer có cùng subscription, group có thể gán mỗi partition cho một consumer. Đây là mức song song tối đa theo số partition của topic.

### Trường hợp consumer nhiều hơn partition

Nếu topic có 12 partition nhưng group có 16 consumer:

```text
P0..P11 ──▶ 12 consumer được gán partition

Consumer M ── rảnh
Consumer N ── rảnh
Consumer O ── rảnh
Consumer P ── rảnh
```

Tối đa 12 consumer có partition để xử lý topic này tại một thời điểm. Bốn consumer còn lại không làm tăng khả năng đọc song song. Chúng vẫn có thể tham gia group và tạo thêm chi phí membership, heartbeat hoặc rebalance tùy cấu hình.

## 3. Bảng so sánh nhanh

| Số partition (`P`) | Số consumer (`C`) | Consumer có assignment tối đa | Nhận xét |
|---:|---:|---:|---|
| 12 | 3 | 3 | Mỗi consumer nhận khoảng 4 partition |
| 12 | 6 | 6 | Mỗi consumer nhận khoảng 2 partition |
| 12 | 12 | 12 | Có thể đạt tỷ lệ 1 consumer/partition |
| 12 | 16 | 12 | Có thể có 4 consumer rảnh |
| 4 | 2 | 2 | Mỗi consumer nhận khoảng 2 partition |
| 4 | 4 | 4 | Có thể phân phối mỗi consumer 1 partition |
| 4 | 8 | 4 | Có thể có 4 consumer rảnh |

Các con số “khoảng” giả định assignment tương đối đều. Không nên xem bảng này là cam kết rằng mọi consumer luôn nhận đúng cùng số partition; kết quả còn phụ thuộc partition assignor, số topic và subscription của từng member.

## 4. Một consumer có thể xử lý nhiều partition như thế nào?

Kafka consumer gọi `poll()` để lấy record từ tất cả partition đang được gán. Một consumer có thể nhận record từ nhiều partition trong cùng một lần poll. Listener container của Spring Kafka quản lý vòng lặp poll và chuyển record đến listener.

Ví dụ consumer B được gán partition 3, 4 và 5:

```text
Consumer B
   |
   +── poll()
        |
        +── orders-3: offset 20, 21
        +── orders-4: offset 80, 81
        +── orders-5: offset 12, 13
```

Các partition có offset độc lập. Offset `21` của `orders-3` không liên quan đến offset `81` của `orders-4`. Consumer group lưu committed offset theo từng cặp topic-partition.

Trong xử lý listener thông thường, container gọi listener cho các record được poll theo quy tắc của container. Thứ tự được Kafka bảo đảm trong phạm vi từng partition, không có thứ tự tổng thể giữa các partition. Nếu ứng dụng tự chuyển record sang executor để xử lý song song, phải tự quản lý thứ tự hoàn tất và ranh giới commit cho từng partition.

## 5. Nhiều topic: phải tính tổng partition được subscribe

Một consumer group có thể subscribe nhiều topic. Khi đó, mức song song được quyết định bởi số partition trong toàn bộ subscription mà group nhận assignment, không chỉ bởi số partition của một topic riêng lẻ.

Ví dụ group `notification-service` subscribe:

| Topic | Số partition |
|---|---:|
| `orders` | 6 |
| `payments` | 4 |
| `shipments` | 2 |
| **Tổng** | **12** |

Nếu tất cả 8 consumer cùng subscribe cả ba topic, tổng cộng có 12 partition để phân phối. Group có thể gán partition cho tối đa 8 consumer; trung bình mỗi consumer nhận khoảng 1 đến 2 partition. Nếu tăng lên 14 consumer, tối đa 12 consumer có assignment và ít nhất 2 consumer có thể rảnh.

Nếu các consumer có subscription khác nhau, không thể chỉ lấy tổng partition rồi chia đều. Ví dụ một số member chỉ subscribe `orders`, member khác subscribe cả ba topic; assignor phải tuân theo tập partition mà từng member có thể nhận. Cần kiểm tra assignment thực tế.

## 6. Partition assignor quyết định cách phân phối

Kafka dùng partition assignor để phân phối partition cho các consumer member trong group. Assignor ảnh hưởng đến việc partition được chia đều thế nào và bao nhiêu partition phải chuyển owner khi group membership thay đổi.

Một số assignor thường gặp trong Kafka client:

| Assignor | Đặc điểm khái quát |
|---|---|
| `RangeAssignor` | Chia các partition theo từng topic thành các dải cho consumer; với nhiều topic có thể tạo phân phối không đồng đều giữa member |
| `RoundRobinAssignor` | Phân phối luân phiên partition qua các consumer đủ điều kiện; thường cân bằng tốt khi các member có cùng subscription |
| `StickyAssignor` | Cố gắng phân phối cân bằng và giữ assignment cũ nhiều nhất có thể để giảm số partition phải di chuyển |
| `CooperativeStickyAssignor` | Kết hợp tính sticky với cooperative/incremental rebalance để giảm việc thu hồi toàn bộ assignment cùng lúc |

Tên assignor có thể cấu hình qua `partition.assignment.strategy`; lựa chọn khả dụng và giao thức rebalance phụ thuộc phiên bản Kafka client và broker. Không nên đổi assignor trong production mà chưa kiểm tra tương thích và hành vi rollout của toàn bộ consumer group.

### Ví dụ phân phối nhiều topic

Giả sử group có ba consumer cùng subscribe hai topic: `orders` có 3 partition và `payments` có 2 partition. Với `RangeAssignor`, assignment được tính theo từng topic. Một kết quả có thể là:

```text
Consumer A: orders-0, payments-0
Consumer B: orders-1, payments-1
Consumer C: orders-2
```

Consumer A và B nhận hai partition, Consumer C nhận một partition. Đây là ví dụ về phân phối có thể lệch khi số partition mỗi topic không chia đều cho số member. Assignor khác có thể rải partition khác đi. Hãy kiểm tra kết quả thực tế thay vì mặc định mọi assignor đều chia đều tổng partition.

## 7. Số consumer trong Spring Kafka

Với Spring Kafka, mỗi listener container quản lý một hoặc nhiều Kafka consumer. Có hai cách phổ biến để tăng số consumer member:

- Tăng số instance ứng dụng (ví dụ số pod hoặc process).
- Tăng `concurrency` của listener container.

Ví dụ cấu hình concurrency bằng `ConcurrentKafkaListenerContainerFactory`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Listener sử dụng factory:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Hoặc đặt concurrency trực tiếp trên annotation:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        concurrency = "3")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Với một endpoint, một application instance và `concurrency=3`, listener container tạo ba consumer. Nếu chạy ba application instance với cùng endpoint và mỗi instance có concurrency 3, group có thể có tổng cộng 9 consumer member. Cần tính số consumer thực tế trên toàn bộ deployment, không chỉ nhìn cấu hình của một instance.

`concurrency` là số consumer mà container tạo cho endpoint. Nó không tạo partition mới. Nếu topic có 4 partition mà toàn deployment có 8 consumer trong cùng group, tối đa 4 consumer được gán partition của topic tại một thời điểm.

## 8. Cách tính số consumer thực tế trong deployment

Với một listener endpoint được triển khai đồng nhất trên nhiều instance, có thể ước lượng:

\[
C_{total} = N_{instances} \times concurrency
\]

Ví dụ:

| Application instance | Concurrency mỗi instance | Tổng consumer member |
|---:|---:|---:|
| 1 | 2 | 2 |
| 2 | 2 | 4 |
| 3 | 2 | 6 |
| 4 | 3 | 12 |

Giả sử topic `orders` có 6 partition:

- 2 instance × concurrency 2 = 4 consumer: mỗi consumer có thể nhận khoảng 1 đến 2 partition.
- 3 instance × concurrency 2 = 6 consumer: có thể đạt tỷ lệ 1 consumer/partition.
- 4 instance × concurrency 3 = 12 consumer: tối đa 6 consumer được gán partition, 6 consumer còn lại có thể rảnh.

Đây là phép tính cho một endpoint và một group. Nếu ứng dụng có nhiều listener endpoint, nhiều topic hoặc nhiều group ID, cần tính riêng membership và subscription của từng group. Không cộng concurrency của các group khác nhau để so với partition của một group.

## 9. Chọn số consumer theo thông lượng, không chỉ theo tỷ lệ 1:1

Tỷ lệ một consumer trên một partition không phải lúc nào cũng là tối ưu. Một consumer có thể xử lý nhiều partition nếu tổng lưu lượng và thời gian xử lý vẫn đáp ứng SLA. Ngược lại, một consumer trên một partition vẫn có thể không đủ năng lực nếu record nặng hoặc consumer phải gọi nhiều hệ thống bên ngoài.

Nên đo các yếu tố sau:

- **Producer throughput**: số record/giây và byte/giây được ghi vào topic.
- **Consumer processing rate**: số record/giây mà mỗi consumer xử lý ổn định với payload và nghiệp vụ thực tế.
- **Processing latency**: thời gian xử lý trung bình, p95/p99 và thời gian gọi dịch vụ phụ thuộc.
- **Partition skew**: tải có phân bố đều giữa partition không; một key nóng có thể khiến một partition quá tải.
- **Consumer lag**: lag tăng liên tục hay chỉ tăng ngắn hạn trong giờ cao điểm.
- **Resource utilization**: CPU, heap, garbage collection, network, connection pool và tải database.
- **Poll/rebalance health**: thời gian giữa các lần poll, số lần rebalance và lỗi xử lý.

Ước lượng ban đầu có thể dùng:

\[
\text{Consumer cần thiết} \approx
\frac{\text{Thông lượng mục tiêu}}{\text{Thông lượng an toàn mỗi consumer}}
\]

Sau đó giới hạn theo số partition được gán cho group. Đây chỉ là bước ước lượng; cần load test để đo thông lượng an toàn và bổ sung headroom cho tải tăng, broker bảo trì hoặc consumer tạm thời lỗi.

Ví dụ topic cần xử lý 24.000 record/giây, mỗi consumer đã đo được 4.000 record/giây trong điều kiện SLA, thì ước lượng cần 6 consumer hoạt động. Topic cần ít nhất 6 partition có tải phân bố đủ đều để group có thể dùng hết 6 consumer. Nếu topic chỉ có 3 partition, tăng concurrency lên 6 không tạo ra 6 luồng đọc song song hữu ích; cần đánh giá tăng partition hoặc thay đổi kiến trúc xử lý.

## 10. Partition skew và hot key

Số partition và số consumer chỉ tạo ra tiềm năng song song. Nếu một partition nhận phần lớn lưu lượng, consumer sở hữu partition đó có thể bị quá tải trong khi các consumer khác còn rảnh.

Ví dụ topic có 8 partition nhưng 60% record dùng cùng key `customerId=VIP-001`. Nếu partitioner đưa key này vào partition 3, phần lớn tải có thể dồn vào một consumer đang sở hữu partition 3. Tăng consumer từ 8 lên 16 không chia nhỏ một partition cho nhiều consumer trong cùng group.

Các hướng xử lý cần cân nhắc:

- Đo phân bố key và throughput theo partition để xác định hot key.
- Xem lại key theo yêu cầu ordering nghiệp vụ; không đổi key chỉ để cân bằng tải nếu điều đó phá vỡ thứ tự cần giữ.
- Nếu nghiệp vụ cho phép, phân nhỏ workload theo shard key có kiểm soát.
- Tách luồng hoặc topic cho nhóm tải đặc biệt khi có ranh giới nghiệp vụ rõ ràng.
- Điều chỉnh logic xử lý nặng, cache hoặc batch để tăng throughput của consumer sở hữu partition nóng.

Tăng partition có thể làm thay đổi ánh xạ key và thứ tự của các sự kiện cùng key qua thời điểm mở rộng. Nếu cần thứ tự nghiêm ngặt theo entity, phải có kế hoạch thay đổi partition và key mapping riêng.

## 11. Rebalance khi tăng hoặc giảm consumer

Khi consumer tham gia hoặc rời group, Kafka có thể rebalance để phân phối lại partition. Các tình huống thường gây rebalance:

- Scale deployment lên hoặc xuống.
- Một consumer process dừng, crash hoặc mất kết nối.
- Consumer không poll kịp trong giới hạn `max.poll.interval.ms`.
- Subscription hoặc partition count thay đổi.
- Consumer group thay đổi assignment strategy hoặc giao thức group.

Trong rebalance, partition có thể được thu hồi và gán lại. Tùy assignor và cooperative protocol, việc tạm dừng xử lý và số partition phải di chuyển sẽ khác nhau. Rebalance thường xuyên có thể làm giảm throughput và tăng lag.

Một số thuộc tính liên quan:

| Thuộc tính | Vai trò |
|---|---|
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần `poll()` trước khi consumer bị xem là không còn tiến triển và có thể rời group |
| `session.timeout.ms` | Thời gian broker chờ heartbeat trước khi xem consumer mất kết nối (tùy giao thức group và cấu hình) |
| `heartbeat.interval.ms` | Chu kỳ heartbeat trong các cấu hình giao thức consumer áp dụng thuộc tính này |
| `max.poll.records` | Giới hạn số record tối đa trả về trong một lần poll; ảnh hưởng khối lượng xử lý trước poll tiếp theo |

Không nên tăng `max.poll.interval.ms` để che giấu việc xử lý quá chậm mà không đo nguyên nhân. Nếu listener xử lý lâu, hãy xem xét batch phù hợp, tối ưu nghiệp vụ, tách tác vụ nặng, hoặc quản lý xử lý bất đồng bộ nhưng phải giữ commit offset đúng thứ tự.

## 12. Bảo đảm thứ tự khi một consumer nhận nhiều partition

Kafka bảo đảm thứ tự trong từng partition. Nếu một consumer nhận nhiều partition, record trong mỗi partition vẫn có thứ tự riêng, nhưng không có thứ tự toàn cục giữa chúng.

Ví dụ consumer A nhận `orders-0` và `orders-1`:

```text
orders-0:  A1 ── A2 ── A3
orders-1:  B1 ── B2 ── B3

Không có cam kết thứ tự giữa A1 và B1,
hoặc giữa A2 và B2.
```

Nếu xử lý listener tuần tự, container xử lý các record theo thứ tự poll/dispatch phù hợp với từng partition. Nếu ứng dụng chuyển công việc sang nhiều thread, B1 có thể hoàn tất trước A1 dù A1 được poll trước. Khi đó cần thiết kế thứ tự theo partition hoặc key, và chỉ commit đến offset liên tục đã hoàn tất trong partition đó.

Không dùng số consumer như cách tạo thứ tự toàn cục. Nếu nghiệp vụ cần tuần tự tuyệt đối cho toàn topic, phải cân nhắc chỉ một partition và một luồng xử lý, chấp nhận giới hạn throughput tương ứng.

## 13. Kiểm tra assignment và consumer lag

### Kiểm tra số partition của topic

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Lệnh hiển thị partition, leader, replica và ISR. Ghi nhận tổng số partition trước khi quyết định tăng consumer.

### Kiểm tra consumer group

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
```

Kết quả cho biết partition nào được gán cho consumer member nào, host của consumer và lag theo partition. Nếu số consumer lớn hơn partition, có thể thấy một số member không xuất hiện ở các dòng partition vì chúng không sở hữu partition nào; dùng chế độ hiển thị member chi tiết của phiên bản Kafka đang chạy nếu cần xác định đầy đủ member rảnh.

Không chỉ xem tổng lag. Một partition lag cao trong khi các partition khác gần bằng 0 thường gợi ý skew, hot key hoặc một consumer member gặp vấn đề. Nếu tất cả partition cùng tăng lag, có thể tổng năng lực consumer thấp hơn tốc độ producer.

## 14. Quy trình chọn và điều chỉnh số consumer

Một quy trình thực tế có thể thực hiện theo các bước sau:

1. **Đếm partition:** xác định số partition của topic hoặc tổng subscription của group.
2. **Đếm consumer thực tế:** tính số application instance nhân concurrency của endpoint; xác định đúng group ID.
3. **Đo tải:** lấy throughput, processing latency, lag theo partition và tài nguyên CPU/memory/network.
4. **Tìm bottleneck:** xác định thiếu consumer, partition nóng, xử lý nghiệp vụ chậm, rebalance hoặc hệ thống downstream quá tải.
5. **Scale consumer có kiểm soát:** tăng hoặc giảm instance/concurrency theo từng bước và quan sát rebalance.
6. **Đánh giá partition:** nếu số consumer hữu ích đã chạm giới hạn partition, xem xét tăng partition sau khi đánh giá key mapping và ordering.
7. **Kiểm thử lỗi:** dừng một consumer, kiểm tra partition được gán lại, committed offset và khả năng xử lý record giao lại.
8. **Chốt cấu hình:** ghi nhận concurrency, số instance, partition count, assignor và ngưỡng lag/SLA cần theo dõi.

Không cần ép số consumer bằng số partition trong mọi hệ thống. Một consumer xử lý nhiều partition có thể hiệu quả hơn nếu thông lượng đáp ứng yêu cầu và tài nguyên được sử dụng hợp lý. Mục tiêu là đủ năng lực xử lý với độ trễ chấp nhận được và khả năng phục hồi khi một member gặp lỗi.

## 15. Tổng kết

- Trong một consumer group, một partition chỉ được gán cho tối đa một consumer member tại một thời điểm.
- Nếu consumer ít hơn partition, mỗi consumer có thể nhận nhiều partition; nếu consumer nhiều hơn partition, một số consumer sẽ rảnh.
- Với một topic và subscription giống nhau, mức song song tối đa theo partition là `min(partition count, consumer count)`.
- Khi subscribe nhiều topic, cần tính tổng partition đủ điều kiện assignment và xem xét subscription/assignor.
- Spring Kafka tăng số consumer bằng application instance và `concurrency`; concurrency không tạo partition mới.
- Throughput, partition skew, hot key, thời gian xử lý và rebalance quan trọng hơn việc đạt tỷ lệ 1:1 trên giấy.
- Tăng consumer vượt số partition không tăng song song hữu ích; muốn mở rộng hơn phải đánh giá partition count và ordering.
- Luôn kiểm tra assignment, lag và tài nguyên sau khi scale.

Khi cân bằng đúng số consumer với số partition, ứng dụng Spring Kafka có thể tận dụng song song mà topic cung cấp, hạn chế consumer rảnh và giữ được khả năng xử lý ổn định khi tải thay đổi.
