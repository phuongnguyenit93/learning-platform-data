# Ordering khi tăng concurrency

## 1. Kafka bảo đảm thứ tự ở đâu?

Kafka bảo đảm thứ tự record trong phạm vi một partition. Record được ghi vào partition theo một thứ tự xác định và consumer đọc chúng theo thứ tự offset trong partition đó. Kafka không bảo đảm thứ tự tổng thể giữa nhiều partition.

Khi tăng concurrency của consumer group, cần phân biệt ba loại thứ tự:

- **Thứ tự trong log:** thứ tự record được append vào một partition. Đây là bảo đảm cốt lõi của Kafka.
- **Thứ tự listener nhận record:** thứ tự container chuyển record đến phương thức xử lý. Với record listener đồng bộ, các record của cùng partition được gọi theo thứ tự đọc.
- **Thứ tự hoàn tất nghiệp vụ:** thứ tự các thao tác database/API thực sự kết thúc. Ứng dụng có thể làm thay đổi thứ tự này nếu xử lý song song hoặc bất đồng bộ.

Tăng concurrency không tự thay đổi thứ tự record đã lưu trong partition. Nó thay đổi số consumer member và cách partition được phân công trong group. Thứ tự nghiệp vụ có thể bị ảnh hưởng nếu ứng dụng cho nhiều thao tác cùng partition chạy đồng thời, hoặc dùng retry không chặn.

## 2. Concurrency trong Spring Kafka có nghĩa gì?

Trong Spring Kafka, `concurrency` là số consumer được listener container tạo cho một endpoint trên một application instance. Với `ConcurrentMessageListenerContainer`, Spring quản lý các container con; mỗi container con sử dụng một Kafka consumer riêng.

Các consumer này thường tham gia cùng `group.id` và chia nhau partition. Trong một consumer group, một partition tại một thời điểm chỉ được gán cho tối đa một member. Vì vậy, tăng concurrency có thể tăng số partition được xử lý song song, nhưng không chia một partition thành nhiều luồng consumer.

Ví dụ topic `orders` có 6 partition:

```text
concurrency = 1
  Consumer A: P0, P1, P2, P3, P4, P5

concurrency = 3
  Consumer A: P0, P1
  Consumer B: P2, P3
  Consumer C: P4, P5

concurrency = 6
  Consumer A: P0
  Consumer B: P1
  Consumer C: P2
  Consumer D: P3
  Consumer E: P4
  Consumer F: P5
```

Assignment thực tế phụ thuộc partition assignor và membership; sơ đồ chỉ minh họa số lượng. Với 6 partition, concurrency lớn hơn 6 không tạo thêm khả năng đọc song song cho topic này trong group. Các consumer vượt quá số partition có thể không được gán partition.

## 3. Tăng concurrency có làm đảo thứ tự trong một partition không?

Nếu listener xử lý đồng bộ theo cách thông thường, tăng concurrency **không làm đảo thứ tự đọc trong cùng partition**. Kafka vẫn gán partition đó cho một consumer member tại một thời điểm và consumer đọc các record theo offset.

Ví dụ partition `orders-2` chứa:

```text
offset 100: OrderCreated
offset 101: OrderPaid
offset 102: OrderShipped
```

Khi partition này được gán cho Consumer A, listener nhận các record theo thứ tự `100 → 101 → 102`. Sau khi tăng concurrency và rebalance chuyển partition sang Consumer C, Consumer C tiếp tục từ committed offset của group. Partition không bị chia giữa A và C để hai consumer xử lý các offset khác nhau đồng thời.

Điểm cần lưu ý là **consumer owner có thể thay đổi**, còn thứ tự trong partition không đổi. Nếu xử lý trước đó chưa commit, record có thể được giao lại cho owner mới. Đây là nguy cơ xử lý lặp, không phải Kafka tự đảo thứ tự record trong log.

## 4. Ví dụ tăng concurrency bằng Spring Kafka

Có thể đặt concurrency trong listener container factory:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);
        return factory;
    }
}
```

Listener sử dụng factory:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "ordersListenerFactory")
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
```

Hoặc đặt trực tiếp trên endpoint:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        concurrency = "3")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

Chọn một nơi cấu hình rõ ràng để tránh khó hiểu khi concurrency được đặt ở cả factory và annotation. Giá trị concurrency có thể bị giới hạn theo số partition được gán cho endpoint.

## 5. Scale nhiều application instance

Trong môi trường triển khai nhiều process hoặc pod, số consumer member thực tế của một endpoint thường được ước lượng như sau:

\[
C_{total} = N_{instances} \times concurrency
\]

Ví dụ 3 application instance, mỗi instance có concurrency 2, tạo tối đa 6 consumer member cho endpoint và group tương ứng. Nếu topic có 6 partition, group có thể sử dụng cả 6 consumer. Nếu scale lên 5 instance với concurrency 2, tổng số member là 10 nhưng vẫn chỉ có tối đa 6 member nhận partition của topic.

Điều quan trọng là các instance cùng dịch vụ phải dùng group ID ổn định và giống nhau nếu mục tiêu là chia tải. Nếu mỗi instance dùng group ID khác nhau, mỗi instance trở thành subscriber độc lập và có thể đọc toàn bộ topic, làm thay đổi hoàn toàn hành vi xử lý.

## 6. Rebalance khi tăng concurrency

Khi thêm consumer member, Kafka group coordinator thực hiện rebalance để phân phối lại partition. Một số partition có thể chuyển từ consumer cũ sang consumer mới. Tùy assignor và giao thức rebalance, group có thể tạm dừng xử lý toàn bộ hoặc chỉ thu hồi một phần assignment.

Trong lúc scale up:

1. Các consumer mới khởi động và tham gia group.
2. Group nhận biết membership thay đổi.
3. Partition assignment được tính lại.
4. Consumer cũ thu hồi partition được chuyển đi; consumer mới nhận assignment.
5. Consumer mới khôi phục vị trí từ committed offset và tiếp tục poll.

Nếu consumer cũ đã xử lý record nhưng chưa commit trước khi partition bị thu hồi, consumer mới có thể đọc lại record đó. Vì vậy, scale up có thể tạo redelivery quanh thời điểm rebalance. Handler cần idempotent để tránh cập nhật database, gửi email hoặc tạo tác dụng phụ hai lần.

Cooperative assignor có thể giảm số partition bị thu hồi trong mỗi vòng rebalance, nhưng không loại bỏ mọi gián đoạn hoặc mọi khả năng redelivery. Hãy quan sát rebalance duration, consumer lag và log khi thay đổi concurrency ở production.

## 7. Concurrency không chia nhỏ một partition

Giả sử topic chỉ có một partition và consumer group có concurrency 8:

```text
Topic orders: P0

Consumer group order-service:
  Consumer A: P0
  Consumer B: không có partition
  Consumer C: không có partition
  Consumer D: không có partition
  Consumer E: không có partition
  Consumer F: không có partition
  Consumer G: không có partition
  Consumer H: không có partition
```

Chỉ một consumer có thể sở hữu P0 tại một thời điểm. Bảy consumer còn lại không thể cùng đọc các offset khác nhau của P0 trong cùng group theo cơ chế consumer group thông thường.

Nếu throughput bị giới hạn bởi một partition, tăng concurrency không giải quyết được nút thắt đó. Có thể cần tăng số partition, nhưng thay đổi partition count có thể làm thay đổi ánh xạ key và ảnh hưởng ordering qua thời điểm mở rộng. Cần đánh giá yêu cầu thứ tự trước khi thay đổi.

## 8. Giữ thứ tự theo key

Nếu producer gửi key ổn định như `orderId`, partitioner thường đưa các record cùng key vào cùng partition. Điều này cho phép Kafka duy trì thứ tự append của các sự kiện liên quan đến cùng đơn hàng.

Ví dụ:

```java
kafkaTemplate.send("orders", event.orderId(), event);
```

Giả sử các sự kiện của `ORD-100` đều vào `orders-2`:

```text
orders-2:
  offset 100: ORD-100 / OrderCreated
  offset 101: ORD-100 / OrderPaid
  offset 102: ORD-100 / OrderShipped
```

Tăng concurrency từ 1 lên 3 hoặc 6 chỉ có thể chuyển `orders-2` sang consumer member khác. Nó không tự thay đổi partition được chọn cho key `ORD-100`, miễn là partition count và partitioner không thay đổi. Do đó, thứ tự đọc trong partition vẫn được giữ.

Nếu tăng số partition, phép ánh xạ key có thể thay đổi. Đây là thay đổi khác với tăng concurrency và cần kế hoạch riêng. Không nên nhầm hai thao tác này khi điều tra lỗi ordering.

## 9. Khi nào ứng dụng tự làm mất thứ tự?

Ngay cả khi Kafka và listener container giao record đúng thứ tự, ứng dụng vẫn có thể hoàn tất xử lý sai thứ tự nếu tự tạo concurrency bên trong listener.

### Gửi tác vụ sang executor rồi trả về ngay

Ví dụ nguy hiểm:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
    // Listener kết thúc trước khi tác vụ nghiệp vụ hoàn tất.
}
```

Container có thể xem listener đã hoàn tất và tiếp tục tiến độ/commit theo AckMode, trong khi tác vụ nền vẫn đang chạy. Record sau có thể bắt đầu xử lý trước record trước; nếu process dừng, offset đã commit có thể khiến tác vụ chưa hoàn tất không được giao lại.

### Dùng CompletableFuture không kiểm soát

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public CompletableFuture<Void> onOrder(OrderEvent event) {
    return CompletableFuture.runAsync(
            () -> orderService.process(event), executor);
}
```

Spring Kafka có hỗ trợ một số kiểu trả về bất đồng bộ ở các phiên bản hiện đại, nhưng hành vi acknowledgement và lỗi phụ thuộc phiên bản, loại listener và cấu hình. Không nên mặc định rằng mọi `CompletableFuture` đều tự giữ partition cho đến khi hoàn tất. Hãy kiểm tra tài liệu phiên bản đang dùng và cấu hình async listener/acknowledgment tương ứng. Nếu không cần xử lý bất đồng bộ, listener đồng bộ thường dễ bảo đảm ordering và commit hơn.

### Dùng parallel stream trong batch listener

```java
events.parallelStream().forEach(orderService::process);
```

Đoạn này có thể làm các record trong batch hoàn tất không theo thứ tự đầu vào. Nếu các record cùng partition biểu diễn các trạng thái cần áp dụng tuần tự, kết quả nghiệp vụ có thể sai dù Kafka đã trả record đúng thứ tự.

## 10. Cách xử lý song song mà vẫn giữ thứ tự cần thiết

Nếu cần tăng throughput mà vẫn giữ thứ tự theo entity, hãy xác định rõ phạm vi cần tuần tự:

- **Theo partition:** xử lý tuần tự record trong partition; cho phép các partition khác nhau chạy song song. Đây là cách phù hợp tự nhiên với Kafka.
- **Theo key/entity:** giữ key ổn định để các record của entity vào cùng partition và xử lý tuần tự trong partition đó.
- **Theo toàn topic:** nếu mọi record phải theo một thứ tự toàn cục, cần một partition và một luồng xử lý; điều này giới hạn khả năng song song.
- **Theo tác vụ downstream:** nếu phải gửi tác vụ nền, dùng cơ chế tuần tự hóa theo partition/key và chỉ acknowledge khi các offset trước đó đã hoàn tất liên tục.

Với xử lý bất đồng bộ, cần quản lý trạng thái hoàn tất theo từng partition. Chỉ commit offset kế tiếp sau dãy record liên tục đã hoàn tất; không commit vượt qua một record còn đang chạy. Đồng thời phải xử lý shutdown/rebalance để chờ hoặc hủy tác vụ đúng cách mà không làm mất tiến độ.

## 11. Retry có thể ảnh hưởng ordering như thế nào?

Cần phân biệt retry chặn (blocking retry) và retry không chặn qua topic khác.

### Blocking retry

Với `DefaultErrorHandler` và backoff thông thường, consumer xử lý lại record lỗi theo luồng của partition. Trong thời gian retry, việc xử lý record tiếp theo của partition đó thường bị chặn, giúp giữ thứ tự xử lý nhưng làm partition bị tạm dừng và có thể tăng lag.

### Non-blocking retry topic

Với retry topic (ví dụ `@RetryableTopic`), record lỗi được chuyển sang topic retry để xử lý sau. Consumer của topic chính có thể tiếp tục record tiếp theo. Khi đó, record offset sau có thể được xử lý trước record lỗi đang chờ ở retry topic.

Ví dụ:

```text
Topic orders:
  offset 10: OrderCreated ── lỗi, chuyển sang orders-retry
  offset 11: OrderPaid    ── xử lý ngay thành công

Topic orders-retry:
  OrderCreated được thử lại sau
```

Kết quả là thứ tự nghiệp vụ của cùng entity có thể bị đảo. Nếu ordering là yêu cầu bắt buộc, cần cân nhắc blocking retry, tạm dừng partition, thiết kế retry theo key hoặc cơ chế kiểm tra version/state trước khi áp dụng sự kiện. Non-blocking retry là lựa chọn đánh đổi giữa khả năng tiếp tục xử lý và thứ tự.

## 12. Tác động của AckMode và xử lý lỗi

Concurrency không thay đổi ý nghĩa của AckMode, nhưng nhiều consumer member sẽ commit offset độc lập theo partition mà mỗi consumer sở hữu.

| AckMode | Ảnh hưởng khi tăng concurrency |
|---|---|
| `RECORD` | Mỗi consumer commit sau khi listener xử lý thành công từng record trên partition được gán |
| `BATCH` | Mỗi consumer commit các offset của batch poll sau khi batch xử lý thành công |
| `MANUAL` | Listener xác nhận theo quy tắc manual; cần bảo đảm chỉ xác nhận phần đã xử lý xong |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge trên consumer thread; không dùng để commit vượt qua record trước chưa hoàn tất |

Nếu listener xử lý đồng bộ, container có thể quản lý commit theo tiến độ xử lý. Nếu listener tạo tác vụ nền rồi trả về, commit có thể đi trước side effect. Hãy giữ công việc cần thiết trong thời gian listener invocation hoặc dùng cơ chế async listener/acknowledgment được Spring Kafka hỗ trợ đúng phiên bản.

Khi rebalance, partition có thể được giao cho consumer khác. Record chưa commit có thể được đọc lại. Không dùng concurrency như một cách bảo đảm exactly-once; cần idempotency hoặc transaction phù hợp với ranh giới dữ liệu.

## 13. Cấu hình và vận hành để tránh rebalance không cần thiết

Một số cấu hình consumer ảnh hưởng việc group giữ member và thời gian xử lý:

| Thuộc tính | Vai trò |
|---|---|
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần poll; xử lý quá lâu có thể khiến member rời group |
| `max.poll.records` | Giới hạn số record một lần poll; batch lớn làm tăng thời gian xử lý trước poll tiếp theo |
| `session.timeout.ms` | Thời gian phát hiện member mất heartbeat trong giao thức áp dụng cấu hình này |
| `heartbeat.interval.ms` | Chu kỳ heartbeat trong cấu hình giao thức consumer sử dụng thuộc tính này |
| `partition.assignment.strategy` | Chọn chiến lược phân phối partition khi membership thay đổi |

Không tăng concurrency liên tục khi lag tăng mà chưa tìm nguyên nhân. Nếu bottleneck là database, hot key, downstream API hoặc một partition duy nhất, thêm consumer có thể chỉ tăng cạnh tranh tài nguyên và rebalance.

Khi scale deployment, nên tăng theo từng bước và quan sát:

- Số consumer member thực tế trong group.
- Partition assignment trước và sau scale.
- Rebalance count và thời gian rebalance.
- Consumer lag theo từng partition.
- Throughput và processing latency của listener.
- CPU, heap, connection pool và tải database.

## 14. Kiểm thử ordering khi tăng concurrency

Kiểm thử cần xác minh cả thứ tự record trong partition và thứ tự hoàn tất nghiệp vụ. Có thể xây dựng các kịch bản:

1. Tạo topic `orders` với nhiều partition và gửi các sự kiện có cùng `orderId` làm key.
2. Chạy listener đồng bộ với concurrency 1, ghi nhận thứ tự offset và kết quả nghiệp vụ.
3. Tăng concurrency lên 3, gửi chuỗi sự kiện cùng key và xác nhận chúng vẫn nằm cùng partition, được xử lý theo thứ tự.
4. Gửi các key khác nhau để xác nhận nhiều partition có thể được xử lý song song.
5. Scale thêm application instance để tạo rebalance; xác nhận partition owner thay đổi nhưng record chưa commit có thể được giao lại.
6. Làm một listener xử lý lỗi và so sánh blocking retry với retry topic để quan sát khác biệt ordering.
7. Thử dispatch tác vụ sang executor hoặc `parallelStream()` và đo thứ tự hoàn tất để phát hiện việc ứng dụng tự tạo concurrency.
8. Dừng process trong lúc có tác vụ đang chạy, sau đó khởi động lại và xác minh offset, redelivery và idempotency.

Mỗi record test nên có `eventId`, `aggregateId`/`orderId` và sequence/version nghiệp vụ. Log topic, partition, offset, consumer ID và thời điểm bắt đầu/kết thúc xử lý để phân biệt thứ tự đọc với thứ tự hoàn tất.

## 15. Tổng kết

- Kafka giữ thứ tự trong từng partition; không có thứ tự tổng thể giữa các partition.
- Tăng concurrency tạo thêm consumer member và có thể tăng xử lý song song giữa partition.
- Một partition tại một thời điểm chỉ được gán cho tối đa một consumer trong group; tăng concurrency không chia một partition cho nhiều consumer.
- Scale up gây rebalance và có thể redeliver record chưa commit; consumer cần idempotent.
- Cùng key thường được định tuyến vào cùng partition; tăng concurrency không tự thay đổi key mapping, còn tăng partition có thể thay đổi.
- Ứng dụng có thể phá thứ tự hoàn tất bằng executor, future hoặc parallel processing nếu không quản lý tuần tự theo partition/key.
- Blocking retry thường giữ partition chờ record lỗi; retry topic có thể cho record sau vượt lên trước.
- Chọn concurrency theo partition count, throughput, lag, tài nguyên và yêu cầu ordering; kiểm thử trước khi rollout production.

Khi tăng concurrency đúng cách, Spring Kafka có thể xử lý nhiều partition song song mà vẫn giữ thứ tự trong từng partition. Muốn bảo toàn thứ tự nghiệp vụ, cần đồng thời kiểm soát key, cách listener xử lý, retry, commit offset và hành vi khi rebalance.
