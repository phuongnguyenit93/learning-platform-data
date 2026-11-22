# Concurrency và số partition

Trong Spring Kafka, concurrency quyết định một listener container tạo bao nhiêu consumer để đọc song song. Số partition của topic quyết định có bao nhiêu đơn vị dữ liệu mà các consumer trong cùng một consumer group có thể xử lý độc lập. Hai cấu hình này phải được thiết kế cùng nhau: tăng concurrency chỉ tăng khả năng xử lý song song khi group còn partition chưa được consumer khác nhận.

Ví dụ, topic `orders.in` có 6 partition. Một ứng dụng chạy một listener với concurrency bằng 3 sẽ tạo 3 consumer trong cùng group. Mỗi consumer có thể nhận 2 partition. Nếu tăng concurrency lên 6, mỗi consumer có thể nhận một partition. Nếu tăng lên 10, tối đa 6 consumer có partition để xử lý; 4 consumer còn lại không nhận partition nào.

```text
Topic orders.in: 6 partitions

Concurrency = 3                  Concurrency = 6
Consumer 0 <- P0, P1             Consumer 0 <- P0
Consumer 1 <- P2, P3             Consumer 1 <- P1
Consumer 2 <- P4, P5             Consumer 2 <- P2
                                 Consumer 3 <- P3
                                 Consumer 4 <- P4
                                 Consumer 5 <- P5
```

Mỗi partition chỉ được gán cho tối đa một consumer trong cùng group tại một thời điểm. Vì vậy partition là giới hạn song song cơ bản của một consumer group, còn concurrency là số consumer mà ứng dụng yêu cầu chạy.

## 1. Consumer group và giới hạn song song

Kafka chia topic thành các partition độc lập. Consumer group phối hợp để phân chia các partition đó giữa các consumer có cùng `group.id`. Với một topic có `P` partition và một group có `C` consumer đang đăng ký topic đó:

- Nếu `C` nhỏ hơn `P`, một số consumer sẽ nhận nhiều partition.
- Nếu `C` bằng `P`, mỗi consumer có thể nhận một partition.
- Nếu `C` lớn hơn `P`, ít nhất `C - P` consumer không có partition để đọc.

Trong trường hợp một listener đăng ký nhiều topic, cần xét tổng số partition mà listener subscription có thể nhận. Ví dụ listener đọc `orders.in` có 6 partition và `payments.in` có 4 partition thì group có 10 partition trong phạm vi subscription đó. Tuy nhiên cách chúng được chia cho consumer còn phụ thuộc partition assignor và subscription của các consumer trong group.

Một consumer có thể xử lý nhiều partition, nhưng một partition không được chia đồng thời cho hai consumer trong cùng group. Đây là cơ chế giúp Kafka giữ thứ tự record trong partition và tránh hai consumer cùng tiến offset cho một partition.

### 1.1 Nhiều consumer group không làm tăng song song cho cùng một luồng xử lý

Hai consumer group khác nhau có thể cùng đọc toàn bộ một topic độc lập. Ví dụ `order-enricher` và `order-audit` đều nhận các record từ `orders.in`; mỗi group có offset riêng và mỗi group có thể được gán tất cả partition. Việc thêm group mới tạo thêm một luồng tiêu thụ độc lập, không chia tải cho group cũ.

Muốn tăng số consumer cùng chia tải cho một công việc, các consumer phải tham gia cùng group ID và đăng ký subscription phù hợp. Nếu vô tình cấu hình mỗi replica với `group.id` khác nhau, tất cả replica có thể đọc lại toàn bộ topic thay vì chia partition.

## 2. Cấu hình concurrency trong Spring Kafka

Spring Kafka triển khai concurrency bằng một `ConcurrentMessageListenerContainer` quản lý nhiều child `KafkaMessageListenerContainer`. Mỗi child container sở hữu một Kafka consumer riêng và tham gia consumer group bằng cùng group ID của listener.

Với Spring Boot, có thể cấu hình concurrency mặc định cho listener container:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-enricher
    listener:
      concurrency: 3
```

Giá trị này được dùng khi Boot tạo listener container factory tự động. Nếu ứng dụng tự khai báo factory, có thể đặt concurrency trực tiếp:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, Order>
orderListenerContainerFactory(
        ConsumerFactory<String, Order> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, Order>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
```

Listener có thể chọn factory đó:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        groupId = "${spring.kafka.consumer.group-id}",
        containerFactory = "orderListenerContainerFactory")
public void onOrder(ConsumerRecord<String, Order> record) {
    orderService.process(record.value());
}
```

Nếu chỉ muốn thay đổi concurrency cho một listener, có thể khai báo ngay trên annotation:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        groupId = "order-enricher",
        concurrency = "${app.kafka.orders.concurrency:3}")
public void onOrder(ConsumerRecord<String, Order> record) {
    orderService.process(record.value());
}
```

Concurrency trên `@KafkaListener` áp dụng cho container của listener đó. Nó giúp các listener có tải và yêu cầu song song khác nhau dùng cấu hình riêng. Khi chọn cách cấu hình, cần kiểm tra factory mà listener thực sự sử dụng; giá trị concurrency ở một factory khác không ảnh hưởng đến listener này.

## 3. Tính tổng số consumer khi chạy nhiều replica

Concurrency thường được cấu hình trên mỗi instance ứng dụng. Nếu chạy `R` replica và mỗi replica tạo `C` consumer cho cùng một listener/group, tổng số consumer tham gia group xấp xỉ:

\[
N = R \times C
\]

Với một topic có `P` partition, số consumer có thể được gán ít nhất một partition không vượt quá:

\[
N_{active} \leq \min(P, R \times C)
\]

Ví dụ topic có 12 partition, ứng dụng chạy 3 replica và mỗi replica có concurrency 2:

| Đại lượng | Giá trị |
|---|---:|
| Số partition | 12 |
| Số replica | 3 |
| Concurrency mỗi replica | 2 |
| Tổng consumer trong group | 6 |
| Partition trung bình mỗi consumer | 2 |

Nếu scale lên 6 replica với concurrency 2, group có 12 consumer và có thể dùng hết 12 partition. Nếu scale lên 8 replica, group có 16 consumer nhưng tối đa 12 consumer được gán partition. Bốn consumer còn lại vẫn tham gia group nhưng không đọc record.

Công thức này mô tả giới hạn số consumer có việc trong trường hợp subscription cùng một tập partition. Khi nhiều listener trong cùng group có subscription khác nhau, phải xét assignment thực tế của từng subscription thay vì chỉ cộng partition của mọi topic trong cluster.

## 4. Partition assignor quyết định cách chia partition

Kafka dùng partition assignor để quyết định consumer nào nhận partition nào. Số consumer đang hoạt động cho biết giới hạn song song, nhưng không đảm bảo mỗi consumer nhận đúng cùng một số partition. Kết quả còn phụ thuộc assignor, số topic, subscription và thành viên hiện có trong group.

Một số assignor thường gặp:

| Assignor | Cách phân chia khái quát | Điểm cần lưu ý |
|---|---|---|
| `RangeAssignor` | Chia các partition của từng topic thành các dải liên tiếp cho consumer | Khi subscription có nhiều topic, một consumer có thể nhận các partition cùng vị trí từ nhiều topic, khiến tải không đều giữa consumer. |
| `RoundRobinAssignor` | Phân phối lần lượt partition trên các consumer đủ điều kiện | Có thể phân tán partition của nhiều topic đều hơn khi subscription tương thích. |
| `StickyAssignor` | Cố giữ assignment cũ nhiều nhất có thể trong khi cân bằng lại | Giảm số partition phải chuyển khi group thay đổi thành viên. |
| `CooperativeStickyAssignor` | Cân bằng có tính sticky theo cơ chế cooperative/incremental | Có thể giảm thời gian dừng toàn bộ assignment khi rebalance; cần cấu hình tương thích giữa các consumer và phiên bản client. |

Ví dụ có 3 consumer `C0`, `C1`, `C2`, cùng đăng ký hai topic `orders.in` và `payments.in`, mỗi topic có 3 partition. Với RangeAssignor, mỗi topic có thể được chia theo dải tương ứng: `C0` nhận partition 0 của cả hai topic, `C1` nhận partition 1 của cả hai topic, và `C2` nhận partition 2 của cả hai topic. Mỗi consumer nhận hai partition, nhưng nếu một topic có tải cao hơn hẳn topic kia thì tải giữa consumer có thể không cân bằng.

Không nên chọn assignor chỉ dựa vào tên. Hãy kiểm tra cấu hình `partition.assignment.strategy` của Kafka consumer, phiên bản client và khả năng phối hợp của tất cả thành viên trong group. Việc thay đổi assignor có thể gây rebalance trong lúc rollout.

## 5. Concurrency không tạo thêm partition

Concurrency chỉ tạo thêm consumer; nó không chia một partition thành nhiều phần. Nếu topic có 3 partition, một group không thể có 8 consumer cùng đọc độc lập 8 phần của topic đó. Tăng concurrency từ 3 lên 8 chỉ làm 5 consumer không có partition.

Nếu throughput cần nhiều hơn mức một partition có thể cung cấp, có thể cần tăng partition count. Tuy nhiên đây là thay đổi topology của topic, không phải một nút tăng tốc không có chi phí. Cần cân nhắc:

- Khả năng chia dữ liệu theo key để có đủ partition mà vẫn giữ thứ tự theo thực thể nghiệp vụ.
- Tốc độ ghi và đọc, kích thước record, replication factor và năng lực broker.
- Số file log, metadata, replica và chi phí phục hồi khi broker khởi động.
- Số consumer, số kết nối và thời gian rebalance khi group thay đổi.
- Ảnh hưởng của việc tăng partition đến cách key được ánh xạ vào partition.

Với partitioner mặc định dựa trên hash key, tăng số partition có thể khiến record mới của cùng key được gửi sang partition khác so với record cũ. Khi đó, record cũ vẫn nằm ở partition trước trong khi record mới nằm ở partition mới; Kafka không bảo đảm thứ tự tổng thể giữa hai partition. Nếu thứ tự theo `orderId` là yêu cầu bắt buộc, hãy đánh giá tác động của việc tăng partition trước khi thay đổi topic đang có dữ liệu.

## 6. Partition là đơn vị bảo đảm thứ tự

Kafka bảo đảm thứ tự trong một partition. Một consumer được gán partition đó sẽ đọc record theo thứ tự offset. Nếu hai record cùng `orderId` cần được xử lý tuần tự, producer thường dùng `orderId` làm key để các record đó được định tuyến về cùng partition.

```text
orders.in

P0: order-100 created -> order-100 paid -> order-100 shipped
P1: order-200 created -> order-200 paid
P2: order-300 created -> order-300 cancelled

Consumer C0 xử lý P0
Consumer C1 xử lý P1
Consumer C2 xử lý P2
```

Các partition có thể được xử lý song song, trong khi thứ tự của từng đơn hàng được giữ trong partition tương ứng. Nếu ứng dụng tự đưa record sang executor hoặc xử lý bất đồng bộ nhiều record của cùng partition, nó có thể làm mất thứ tự hoàn tất nghiệp vụ dù Kafka vẫn trả record theo đúng thứ tự. Khi thứ tự quan trọng, không nên tạo song song không kiểm soát bên trong cùng partition.

Tăng số consumer không làm tăng số thứ tự độc lập trong một partition. Để mở rộng xử lý, cần có đủ partition và key phân bố đủ đều. Nếu mọi record đều dùng cùng một key, chúng tập trung vào một partition và một consumer; phần consumer còn lại có thể nhàn rỗi dù topic có nhiều partition.

## 7. Tải không đều và hot partition

Số partition không nói lên rằng tải được chia đều. Một topic có 12 partition vẫn có thể bị giới hạn bởi một partition nếu phần lớn record có cùng key hoặc một số key quá nóng. Đây là hiện tượng hot partition.

Ví dụ, nếu producer dùng `countryCode` làm key nhưng phần lớn đơn hàng đến từ một quốc gia, partition chứa key đó có thể nhận phần lớn lưu lượng. Các consumer khác xử lý partition còn lại nhanh hơn và chờ, trong khi một consumer liên tục bị quá tải.

Theo dõi lag theo partition thay vì chỉ nhìn tổng lag của group. Một partition có lag tăng liên tục trong khi các partition khác gần bằng 0 thường chỉ ra phân phối key hoặc thời gian xử lý không đồng đều. Cách xử lý có thể gồm:

- Chọn key có cardinality và phân phối phù hợp hơn với yêu cầu thứ tự nghiệp vụ.
- Tối ưu xử lý cho loại record tạo hot partition.
- Tách luồng có tải khác biệt sang topic riêng.
- Dùng chiến lược sharding key có chủ đích nếu nghiệp vụ cho phép thay đổi ranh giới thứ tự.

Không thêm random suffix vào key một cách tùy tiện. Cách đó có thể phân tán tải nhưng phá vỡ thứ tự theo thực thể và làm các sự kiện cùng một đơn hàng đi đến nhiều partition.

## 8. Concurrency và thời gian xử lý record

Mỗi consumer phải tiếp tục poll Kafka để duy trì membership trong group. Nếu listener xử lý quá lâu, consumer có thể vượt `max.poll.interval.ms`; broker và group coordinator có thể xem consumer không còn hoạt động và kích hoạt rebalance. Consumer khác có thể nhận partition, trong khi lần xử lý cũ vẫn đang chạy ở phía ứng dụng.

Một số cấu hình cần xem xét cùng nhau:

| Thuộc tính | Ý nghĩa | Cách suy nghĩ khi vận hành |
|---|---|---|
| `max.poll.records` | Giới hạn số record tối đa trả về trong một lần poll | Giảm giá trị có thể giảm lượng công việc mỗi poll, nhưng tăng số lần poll và overhead. |
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần poll trước khi consumer bị xem là không còn tiến triển | Phải đủ lớn cho thời gian xử lý batch/poll ở trường hợp tải cao, có biên an toàn. |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trước khi xem consumer mất session | Liên quan phát hiện consumer mất kết nối; không thay thế giới hạn xử lý của poll. |
| `heartbeat.interval.ms` | Chu kỳ heartbeat trong các chế độ consumer tương ứng | Cần tương thích với session timeout và cấu hình group protocol/client đang dùng. |

Trong các phiên bản Kafka client hiện đại, heartbeat có thể được gửi bởi luồng nền trong khi application thread xử lý record, nhưng `max.poll.interval.ms` vẫn giới hạn khoảng thời gian giữa các lần poll. Đừng chỉ tăng session timeout để chữa listener xử lý lâu.

Với record listener, container gọi listener cho từng record theo luồng xử lý của consumer. Với batch listener, listener nhận một batch từ poll; tổng thời gian xử lý batch phải nằm trong ngân sách poll. Nếu xử lý bất đồng bộ, cần thiết kế rõ lúc nào record được xác nhận và bảo đảm không commit offset vượt qua record chưa hoàn tất.

## 9. Chọn concurrency theo năng lực thực tế

Mục tiêu không phải là đặt concurrency cao nhất có thể. Mỗi consumer tạo thêm công việc nền như poll, heartbeat, network I/O, deserialization và quản lý partition. Listener cũng tiêu thụ CPU, bộ nhớ, connection pool và tài nguyên của dependency.

Một cách chọn ban đầu:

1. Xác định số partition và lưu lượng dự kiến của topic.
2. Đo thời gian xử lý trung bình và phân vị cao của một record.
3. Xác định năng lực xử lý của một consumer trên tài nguyên được cấp.
4. Đặt concurrency sao cho số consumer không vượt quá mức song song có ích của partition subscription.
5. Tăng dần replica hoặc concurrency trong môi trường kiểm thử tải, theo dõi throughput, lag, CPU, heap, connection pool và thời gian xử lý.
6. Giữ khoảng dự phòng cho rebalance, tăng tải và dependency chậm.

Nếu listener chủ yếu chờ I/O, có thể tận dụng nhiều consumer hơn so với workload CPU-bound, nhưng số consumer vẫn bị giới hạn bởi partition và năng lực downstream. Nếu listener dùng database connection pool tối đa 10 connection mà concurrency là 40, nhiều consumer có thể cùng chờ connection và làm tăng độ trễ thay vì tăng throughput.

Hãy xem cả số thread của ứng dụng và số partition được gán. Tăng concurrency không giúp khi bottleneck nằm ở database, HTTP service, broker disk hoặc một hot partition.

## 10. Rebalance khi thay đổi concurrency hoặc replica

Khi consumer tham gia hoặc rời group, group coordinator cần phân phối lại partition. Điều này gọi là rebalance. Rebalance có thể xảy ra khi:

- Ứng dụng scale up hoặc scale down replica.
- Listener container tăng hoặc giảm concurrency.
- Consumer bị dừng, crash hoặc mất kết nối.
- Subscription thay đổi hoặc topic được thêm vào pattern subscription.
- Partition của topic thay đổi.
- Consumer không poll trong thời gian cho phép hoặc bị loại khỏi group.

Trong rebalance, partition có thể được thu hồi khỏi consumer cũ và gán cho consumer mới. Container sẽ phối hợp với Kafka client để dừng nhận công việc mới, hoàn tất hoặc xử lý các record đang chạy theo semantics của cấu hình, rồi tiếp tục với assignment mới. Thời gian rebalance làm tăng độ trễ và có thể làm lag tăng tạm thời.

Để hạn chế ảnh hưởng:

- Dùng graceful shutdown để container dừng có kiểm soát và commit/ack theo cấu hình.
- Tránh scale replica liên tục theo dao động nhỏ của lag.
- Chọn assignor phù hợp, cân nhắc cooperative rebalance nếu client và group hỗ trợ.
- Giữ thời gian xử lý listener trong giới hạn poll và timeout.
- Theo dõi số lần rebalance, thời gian rebalance và thời điểm xảy ra cùng với deployment.

Nếu dùng static membership với `group.instance.id`, mỗi consumer member cần identity phù hợp và không bị trùng giữa các member đang hoạt động. Với concurrent container, cần kiểm tra cách phiên bản Spring Kafka đang dùng tạo hoặc bổ sung identity cho child consumer; không tự gán cùng một `group.instance.id` cho nhiều consumer.

## 11. Khi nào nên tăng partition, concurrency hay replica?

Ba thay đổi này giải quyết các giới hạn khác nhau:

| Thay đổi | Tác động | Khi phù hợp |
|---|---|---|
| Tăng concurrency trong một instance | Tạo thêm consumer thread/container con trong cùng process | Process còn CPU/memory và topic còn partition chưa được khai thác. |
| Tăng số replica | Thêm process và consumer vào group | Một instance không đủ tài nguyên hoặc cần phân tán tải và tăng khả năng chịu lỗi. |
| Tăng partition count | Tạo thêm đơn vị song song trong topic | Group đã dùng hết partition nhưng cần thêm mức song song và key distribution cho phép. |

Ví dụ, topic có 4 partition, một replica concurrency 4 và lag tăng. Tăng lên 8 replica với concurrency 4 không tạo thêm partition; phần lớn consumer không có việc. Nếu broker và mô hình key cho phép, tăng topic lên 8 partition rồi scale consumer có thể tăng mức song song. Nhưng nếu lag tập trung ở một hot partition, tăng partition đơn thuần có thể không giải quyết vì key nóng vẫn ánh xạ vào một partition.

Trước khi tăng partition, hãy kiểm tra khả năng broker chịu thêm replica, dung lượng lưu trữ, số partition toàn cluster, consumer assignor, key distribution và yêu cầu thứ tự. Partition count nên được xem là quyết định thiết kế dài hạn vì việc giảm partition sau này thường không đơn giản như tăng.

## 12. Quan sát và chẩn đoán concurrency

Các chỉ số nên được theo dõi cùng nhau:

- **Consumer lag theo partition:** phát hiện partition có backlog hoặc hot key.
- **Số consumer đang hoạt động và số partition được gán:** phát hiện consumer dư hoặc partition chưa có consumer.
- **Throughput theo consumer và partition:** xem tải có phân phối đều không.
- **Listener duration:** phát hiện xử lý chậm và các outlier kéo dài.
- **Poll interval và rebalance count:** phát hiện consumer bị xem là không tiến triển hoặc group churn.
- **CPU, heap, GC và connection pool:** xác định giới hạn trong process hoặc dependency.
- **Số lần retry, lỗi và DLT:** phân biệt lag do tải cao với lag do record lỗi lặp lại.

Ví dụ cách diễn giải:

| Quan sát | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Lag cao trên mọi partition, CPU cao | Năng lực xử lý của ứng dụng chưa đủ | Đo listener duration, tăng tài nguyên hoặc song song nếu còn partition. |
| Lag cao trên một partition, các partition khác thấp | Hot partition hoặc một record xử lý rất lâu | Kiểm tra key, kích thước record và log theo partition/offset. |
| Nhiều consumer không có assignment | Consumer nhiều hơn partition hoặc subscription không khớp | Kiểm tra tổng concurrency, replica, group ID và topic subscription. |
| Lag tăng theo các lần rollout | Rebalance thường xuyên hoặc shutdown kéo dài | Kiểm tra deployment, graceful shutdown, assignor và thời gian rebalance. |
| Lag tăng dù CPU thấp | Consumer chờ dependency hoặc bị giới hạn bởi I/O | Kiểm tra DB pool, HTTP latency, retry và connection. |

Không chỉ nhìn tổng consumer lag. Tổng lag có thể che khuất một partition đang bị nghẽn; cũng không thể kết luận concurrency thấp chỉ từ lag nếu dependency downstream mới là bottleneck.

## 13. Kiểm thử phân phối partition và concurrency

Kiểm thử tích hợp nên xác nhận assignment thực tế trong group. Với topic có 6 partition và listener concurrency 3, có thể kiểm tra group có 3 consumer và tất cả 6 partition được gán. Sau đó tăng concurrency lên 8 và xác nhận số consumer có assignment không vượt quá 6.

Các kịch bản nên bao gồm:

1. Một instance, concurrency nhỏ hơn partition count: xác nhận consumer nhận nhiều partition.
2. Một instance, concurrency bằng partition count: xác nhận group có thể dùng hết partition.
3. Concurrency lớn hơn partition count: xác nhận consumer dư không nhận partition.
4. Nhiều replica cùng group: xác nhận tổng consumer được tính từ concurrency mỗi replica.
5. Hai group ID khác nhau: xác nhận mỗi group nhận luồng record độc lập.
6. Thêm/bớt replica: quan sát rebalance và xác nhận record không bị mất theo semantics commit đã cấu hình.
7. Phân phối key lệch: xác nhận lag theo partition thể hiện hot partition.
8. Listener xử lý chậm: xác nhận cấu hình poll timeout và retry phù hợp, không phát sinh rebalance ngoài dự kiến.

Khi kiểm thử, dùng AdminClient hoặc công cụ Kafka để xem partition assignment và consumer group state. Chờ trạng thái assignment ổn định theo điều kiện rõ ràng thay vì sleep cố định. Dọn consumer group và topic sau test để kết quả lần chạy sau không bị ảnh hưởng.

## 14. Các lỗi cấu hình thường gặp

- **Tăng concurrency vượt partition count với kỳ vọng throughput tiếp tục tăng:** consumer dư sẽ không nhận partition.
- **Mỗi replica dùng group ID khác nhau:** mọi replica có thể đọc lại toàn bộ topic thay vì chia tải.
- **Dùng concurrency cao hơn năng lực downstream:** nhiều consumer cùng chờ database hoặc HTTP connection, làm tăng độ trễ.
- **Chỉ nhìn tổng lag:** bỏ sót hot partition hoặc một record xử lý rất lâu.
- **Tăng partition mà không xem key distribution:** có thể thay đổi mapping của key và ảnh hưởng thứ tự theo thực thể.
- **Tự xử lý song song record cùng partition:** có thể làm thứ tự hoàn tất nghiệp vụ khác thứ tự Kafka.
- **Bỏ qua rebalance khi scale:** deployment hoặc autoscaling liên tục có thể gây gián đoạn và tăng lag.
- **Cấu hình `group.instance.id` trùng cho nhiều consumer:** gây lỗi static membership fencing và làm group không ổn định.
- **Tăng `session.timeout.ms` để chữa listener xử lý lâu:** bỏ qua giới hạn `max.poll.interval.ms` và nguyên nhân thực sự của việc poll chậm.

## 15. Quy trình chọn cấu hình cho một listener

Khi thiết kế listener cho một topic, hãy bắt đầu từ partition count và tải thực tế. Xác định key nào quyết định thứ tự nghiệp vụ, sau đó kiểm tra key có phân phối đều hay không. Chọn concurrency mỗi instance sao cho tổng consumer của các replica khai thác được số partition có ích. Cuối cùng, đo throughput và lag khi tăng tải để điều chỉnh tài nguyên và cấu hình.

Một cấu hình có thể dùng làm điểm xuất phát:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-enricher
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
    listener:
      concurrency: 3
      ack-mode: record
```

Các giá trị trên chỉ là ví dụ cấu hình ban đầu. `max.poll.records`, `max.poll.interval.ms`, ack mode, concurrency và số replica phải được điều chỉnh theo thời gian xử lý, kích thước batch, retry policy và topology topic. Spring Kafka container thường quản lý offset commit; hãy giữ auto commit tắt để offset tuân theo semantics của container.

Trước khi triển khai, trả lời bốn câu hỏi: topic có bao nhiêu partition, tổng cộng có bao nhiêu consumer trong group, partition/key nào có thể trở thành điểm nóng, và listener có xử lý xong trong ngân sách poll hay không. Những câu trả lời này cho biết concurrency hiện tại có thể khai thác hết partition hay không và liệu tăng consumer có thực sự cải thiện throughput.
