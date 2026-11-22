# Concurrency của listener container

Trong Spring Kafka, `concurrency` xác định số consumer mà một listener container tạo ra để đọc dữ liệu song song trong cùng consumer group. Tăng concurrency có thể giúp xử lý nhiều partition đồng thời, giảm consumer lag và tận dụng CPU tốt hơn. Tuy nhiên, số consumer hoạt động hữu ích bị giới hạn bởi số partition được gán; tăng concurrency quá cao có thể tạo thêm thread và kết nối mà không tăng throughput.

Để chọn concurrency đúng, cần hiểu cách Spring Kafka tạo các consumer con, cách Kafka phân phối partition trong group, quan hệ giữa concurrency và partition count, cùng giới hạn của listener, database và các dịch vụ downstream.

## 1. Listener container quản lý consumer như thế nào?

Khi dùng `@KafkaListener`, ứng dụng không tự tạo `KafkaConsumer` và gọi `poll()`. Spring Kafka tạo listener container để quản lý consumer, poll loop, gọi listener method và commit offset.

Với cấu hình concurrency lớn hơn một, Spring Kafka dùng `ConcurrentMessageListenerContainer`. Container này quản lý nhiều `KafkaMessageListenerContainer` con. Mỗi container con sở hữu một Kafka consumer và chạy poll loop trên thread riêng.

```text
@KafkaListener
      |
      v
ConcurrentMessageListenerContainer
      |
      +--------------------+--------------------+
      |                    |                    |
      v                    v                    v
Child container 0   Child container 1   Child container 2
      |                    |                    |
      v                    v                    v
KafkaConsumer 0      KafkaConsumer 1      KafkaConsumer 2
      |                    |                    |
      v                    v                    v
Consumer thread 0    Consumer thread 1    Consumer thread 2
      |                    |                    |
      +--------------------+--------------------+
                           |
                           v
                    Kafka consumer group
```

Do đó, `concurrency=3` có nghĩa listener endpoint có ba consumer con, mỗi consumer có thread và poll loop riêng. Nó không có nghĩa một `KafkaConsumer` được gọi đồng thời từ ba thread. `KafkaConsumer` không thread-safe; Spring Kafka quản lý việc sở hữu consumer theo từng container con.

## 2. Khai báo concurrency bằng @KafkaListener

Có thể chỉ định concurrency trực tiếp trên annotation:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
            id = "order-created-listener",
            topics = "orders.created",
            groupId = "order-projection",
            concurrency = "3")
    public void onMessage(String payload) {
        // Xử lý một record.
    }
}
```

`concurrency` trong annotation nhận giá trị dạng chuỗi để hỗ trợ placeholder hoặc SpEL. Ví dụ có thể đưa giá trị ra cấu hình:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        concurrency = "${app.kafka.order-listener-concurrency:3}")
public void onMessage(String payload) {
    // Xử lý record.
}
```

```yaml
app:
  kafka:
    order-listener-concurrency: 3
```

Cách này cho phép thay đổi concurrency theo môi trường mà không sửa mã nguồn. Cần bảo đảm giá trị cấu hình là số nguyên dương và không lớn hơn mức tài nguyên mà ứng dụng có thể phục vụ.

## 3. Cấu hình concurrency ở listener container factory

Nếu nhiều listener dùng chung một factory, có thể đặt concurrency mặc định trên `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Listener dùng factory này:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "kafkaListenerContainerFactory")
public void onMessage(String payload) {
    // Xử lý record.
}
```

Với Spring Boot, có thể cấu hình concurrency mặc định cho listener container qua `spring.kafka.listener.concurrency`:

```yaml
spring:
  kafka:
    listener:
      concurrency: 3
```

Giá trị này áp dụng cho factory/container được Boot auto-configure. Nếu ứng dụng tự khai báo factory, hãy đặt concurrency trực tiếp trên factory đó. Giá trị `concurrency` trên `@KafkaListener` có thể ghi đè mức mặc định của factory cho endpoint tương ứng.

Nên dùng cấu hình factory khi nhiều listener có cùng mức concurrency. Nếu từng listener có tải và yêu cầu khác nhau, cấu hình riêng theo annotation hoặc factory riêng sẽ dễ kiểm soát hơn.

## 4. Quan hệ giữa concurrency và số partition

Kafka phân phối partition cho các consumer trong cùng group. Tại một thời điểm, một partition chỉ được gán cho tối đa một consumer trong group. Vì vậy, số consumer có thể xử lý dữ liệu song song bị giới hạn bởi số partition mà group đăng ký.

Ví dụ topic `orders.created` có sáu partition:

```text
Topic orders.created: P0  P1  P2  P3  P4  P5

concurrency = 1
  Consumer 0: P0 P1 P2 P3 P4 P5

concurrency = 3
  Consumer 0: P0 P1
  Consumer 1: P2 P3
  Consumer 2: P4 P5

concurrency = 6
  Consumer 0: P0
  Consumer 1: P1
  Consumer 2: P2
  Consumer 3: P3
  Consumer 4: P4
  Consumer 5: P5

concurrency = 8
  Sáu consumer có partition được gán;
  hai consumer còn lại không có partition để đọc.
```

Sơ đồ là ví dụ phân phối cân bằng để minh họa, không phải cam kết partition assignment luôn theo đúng cặp như trên. Kết quả thực tế phụ thuộc partition assignor, số consumer khác trong group, subscription và trạng thái rebalance.

Khi concurrency nhỏ hơn partition count, một consumer có thể nhận nhiều partition. Khi concurrency bằng partition count, có thể đạt một consumer trên mỗi partition nếu không có consumer khác trong group. Khi concurrency lớn hơn partition count, một số consumer không được gán partition và không làm tăng mức song song đọc của topic đó.

## 5. Tính tổng số consumer trong nhiều instance

Concurrency của một listener endpoint áp dụng trên mỗi instance ứng dụng. Khi scale ứng dụng theo chiều ngang, tổng số consumer trong cùng group tăng theo số replica.

Ví dụ có ba pod, mỗi pod chạy listener với concurrency bằng hai:

```text
Pod A: 2 consumer threads
Pod B: 2 consumer threads
Pod C: 2 consumer threads
-------------------------
Tổng:  6 group members
```

Nếu topic có sáu partition, group có thể phân phối sáu partition cho sáu consumer. Nếu topic chỉ có bốn partition, tối đa bốn consumer có partition được gán; hai consumer còn lại idle.

Với một endpoint đăng ký nhiều topic, giới hạn song song liên quan đến tổng số partition được group đăng ký. Tuy nhiên, subscription pattern, topic có số partition không đồng đều hoặc các listener endpoint khác cùng group có thể làm phân phối phức tạp hơn.

Không cộng concurrency của mọi ứng dụng một cách máy móc nếu chúng dùng group ID khác nhau. Hai group ID khác nhau là hai nhóm tiêu thụ độc lập; mỗi group có thể đọc toàn bộ partition của topic.

## 6. Concurrency và thứ tự record

Kafka chỉ bảo đảm thứ tự trong một partition. Khi Spring Kafka tăng concurrency, các partition khác nhau có thể được xử lý song song trên các consumer thread khác nhau.

Ví dụ:

```text
Partition 0: A1 -> A2 -> A3  -- Consumer 0
Partition 1: B1 -> B2 -> B3  -- Consumer 1
Partition 2: C1 -> C2 -> C3  -- Consumer 2
```

Consumer 0 giữ thứ tự của các record trong Partition 0; Consumer 1 giữ thứ tự trong Partition 1. Không có thứ tự tổng thể giữa A1, B1 và C1.

Nếu các event của cùng một đơn hàng cần được xử lý theo thứ tự, producer nên dùng `orderId` làm key để chúng được định tuyến vào cùng partition. Tăng concurrency không phá vỡ thứ tự trong một partition khi listener xử lý tuần tự trên consumer thread. Tuy nhiên, nếu listener tự gửi công việc sang executor hoặc xử lý bất đồng bộ rồi trả về sớm, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự offset. Khi cần ordering, phải kiểm soát cả luồng xử lý bất đồng bộ và acknowledgement/commit.

## 7. Record listener và batch listener dưới concurrency

Với record listener, container gọi phương thức listener cho từng record. Một consumer thread có thể nhận một batch từ poll rồi gọi listener tuần tự cho các record đó. Các consumer con khác xử lý partition được gán cho chúng song song.

Với batch listener, container gọi listener một lần với danh sách record từ một poll. Một batch được xử lý trên consumer thread của container con đó; concurrency tạo thêm các consumer con để xử lý các partition khác song song.

Ví dụ batch listener:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-projection",
        concurrency = "3",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onMessages(List<ConsumerRecord<String, String>> records) {
    // Xử lý batch trên consumer thread của container con.
}
```

Factory phải được cấu hình batch mode bằng `setBatchListener(true)`. Concurrency không tự biến record listener thành batch listener; đây là hai thiết lập độc lập.

## 8. Thread safety của listener và các dependency

Khi concurrency lớn hơn một, cùng một listener bean trong Spring context có thể được gọi đồng thời từ nhiều consumer thread. Vì bean thường là singleton, mọi trạng thái mutable trong field của listener có thể bị truy cập đồng thời.

Ví dụ không an toàn:

```java
@Component
public class UnsafeOrderListener {

    private int processedCount;

    @KafkaListener(topics = "orders.created", concurrency = "3")
    public void onMessage(String payload) {
        processedCount++; // Không an toàn khi nhiều thread cùng cập nhật.
    }
}
```

`processedCount++` không phải thao tác nguyên tử. Các thread có thể ghi đè kết quả của nhau. Nếu cần thống kê, dùng Micrometer counter, `LongAdder` hoặc một cơ chế đồng bộ phù hợp thay vì field mutable không bảo vệ.

Ví dụ listener stateless:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders.created", concurrency = "3")
    public void onMessage(OrderCreatedEvent event) {
        orderService.process(event);
    }
}
```

`OrderService` và các dependency mà nó dùng cũng cần an toàn khi được gọi đồng thời. Các repository Spring thường được thiết kế để dùng đồng thời, nhưng trạng thái mutable tự quản lý, cache không thread-safe, formatter dùng chung hoặc client tùy chỉnh có thể cần xử lý riêng.

Ưu tiên listener stateless, biến cục bộ và dependency thread-safe. Không lưu payload hoặc dữ liệu request-specific vào field của singleton listener.

## 9. Concurrency và năng lực của downstream

Tăng số consumer thread không chỉ tăng tải lên Kafka broker. Mỗi thread có thể đồng thời gọi database, REST API, cache hoặc hệ thống khác. Nếu downstream không đủ năng lực, concurrency cao làm tăng contention, timeout và retry thay vì tăng throughput.

Ví dụ listener ghi database:

```text
6 consumer threads
       |
       v
6 xử lý record đồng thời
       |
       v
Database connection pool (size = 4)
       |
       +--> 4 thread có connection
       +--> 2 thread chờ connection
```

Nếu connection pool nhỏ hơn số thread xử lý đồng thời, một số consumer thread sẽ chờ lấy connection. Thời gian chờ làm kéo dài xử lý poll và có thể dẫn đến vượt `max.poll.interval.ms`.

Khi tăng concurrency, cần xem xét đồng bộ:

- Kích thước database connection pool và giới hạn kết nối của database.
- HTTP client connection pool, timeout và rate limit của dịch vụ downstream.
- CPU, heap, garbage collection và số thread của JVM.
- Số partition và thông lượng của broker.
- Thời gian xử lý record/batch và `max.poll.interval.ms`.
- Retry/backoff và khả năng tạo tải lặp khi downstream đang lỗi.

Không nên tăng concurrency chỉ vì consumer lag tăng. Trước hết xác định consumer thiếu năng lực xử lý hay đang bị downstream block.

## 10. Liên hệ với max.poll.records và max.poll.interval.ms

Concurrency quyết định số consumer, còn `max.poll.records` giới hạn số record trả về cho một lần poll. `max.poll.interval.ms` giới hạn khoảng thời gian tối đa giữa hai lần poll.

Giả sử mỗi consumer nhận 100 record và xử lý tuần tự, trung bình 80 ms mỗi record:

```text
100 record x 80 ms = 8.000 ms = 8 giây
```

Thời gian thực tế còn có thời gian database, network, GC và logic phụ. Nếu một batch mất quá lâu trước lần poll tiếp theo, consumer có thể rời group và gây rebalance. Tăng concurrency không sửa được một listener thread bị treo hoặc batch quá lớn.

Các hướng điều chỉnh:

1. Đo processing time ở percentile cao thay vì chỉ nhìn trung bình.
2. Giảm `max.poll.records` nếu mỗi batch mất quá lâu.
3. Tăng `max.poll.interval.ms` khi nghiệp vụ thật sự cần thời gian dài, đồng thời đặt timeout cho I/O.
4. Tối ưu batch database hoặc giảm công việc đồng bộ trong listener.
5. Chỉ tăng concurrency nếu có đủ partition và tài nguyên downstream.

## 11. Rebalance khi thay đổi concurrency hoặc replica

Khi số consumer trong group thay đổi, Kafka cần phân phối lại partition. Rebalance xảy ra trong các tình huống như:

- Ứng dụng khởi động thêm replica.
- Một replica bị dừng hoặc mất kết nối.
- Thay đổi concurrency khiến số consumer con tăng hoặc giảm.
- Topic được thêm partition hoặc pattern subscription phát hiện topic mới.
- Consumer không poll đúng thời hạn hoặc bị xem là không hoạt động.

Trong thời gian rebalance, partition có thể tạm ngừng được xử lý khi group thực hiện thu hồi và gán lại assignment. Rebalance thường xuyên làm tăng latency và consumer lag.

Hãy theo dõi log rebalance, thời gian assignment và consumer lag. Chọn concurrency ổn định theo tải thay vì liên tục thay đổi theo từng biến động ngắn. Với hệ thống cần giảm thời gian gián đoạn, có thể xem xét cooperative assignment strategy và static membership khi phù hợp với phiên bản Kafka, Spring Kafka và mô hình triển khai. Các cơ chế này cần cấu hình đồng bộ cho toàn group; chúng không loại bỏ hoàn toàn rebalance.

## 12. Theo dõi consumer concurrency

Để đánh giá concurrency có tạo thêm throughput hay chỉ tạo thêm thread, cần quan sát nhiều chỉ số cùng lúc:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Consumer count trong group | Có bao nhiêu member đang tham gia group? |
| Partition assignment | Mỗi consumer được gán bao nhiêu partition? Có consumer idle không? |
| Records consumed rate | Tổng số record xử lý mỗi giây có tăng không? |
| Consumer lag theo partition | Partition nào đang tụt lại? |
| Listener processing time | Mỗi record/batch mất bao lâu? |
| Poll interval | Consumer có gọi poll đều và trong giới hạn không? |
| Rebalance count/duration | Group có thường xuyên tái phân bổ không? |
| Downstream pool usage | Database/HTTP pool có bị cạn không? |
| CPU và heap | JVM còn dư tài nguyên không? |

Khi tăng concurrency từ 2 lên 4, nếu throughput không tăng nhưng database wait time và rebalance tăng, hệ thống có thể đã chạm giới hạn downstream. Nếu một vài partition có lag cao trong khi partition khác gần như rỗng, có thể key distribution bị lệch hoặc hot partition.

## 13. Quy trình chọn concurrency thực tế

Có thể bắt đầu theo các bước sau:

1. Xác định số partition của topic hoặc tổng partition mà listener đăng ký.
2. Đo throughput cần đạt và thời gian xử lý trung bình/percentile cao của mỗi record.
3. Chọn concurrency ban đầu không vượt quá số partition có thể được gán.
4. Chạy thử với tải đại diện, quan sát consumer lag, throughput, poll interval và downstream saturation.
5. Tăng từng bước concurrency hoặc số replica, rồi so sánh kết quả.
6. Dừng tăng khi throughput không cải thiện hoặc latency/tài nguyên downstream xấu đi.
7. Nếu cần song song hơn mức partition hiện tại, đánh giá tăng partition count và tác động tới key ordering trước khi thay đổi topic.

Không có một con số concurrency tối ưu cho mọi listener. Một listener chỉ parse payload nhẹ có thể dùng nhiều consumer thread hơn listener thực hiện nhiều truy vấn database hoặc gọi dịch vụ bên ngoài.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tăng concurrency nhưng throughput không tăng | Consumer count đã vượt partition count hoặc downstream là bottleneck | Kiểm tra assignment, partition count và thời gian downstream |
| Một số consumer không nhận record | Không có partition được gán cho các consumer dư | Giảm concurrency hoặc tăng partition nếu phù hợp |
| Listener gặp race condition | Singleton listener có field mutable được nhiều thread dùng chung | Stateless listener, dùng cấu trúc thread-safe hoặc đồng bộ |
| Consumer thường xuyên rebalance | Xử lý lâu, poll interval vượt giới hạn hoặc instance chập chờn | Đo thời gian xử lý, kiểm tra poll/heartbeat và hạ tải |
| Database connection pool cạn | Concurrency lớn hơn năng lực kết nối hoặc query chậm | Điều chỉnh pool có kiểm soát, tối ưu query và giới hạn concurrency |
| Thứ tự nghiệp vụ bị đảo | Listener offload xử lý bất đồng bộ hoặc key không cùng partition | Kiểm soát async completion và chọn key theo aggregate |
| Lag tập trung ở một partition | Hot key hoặc dữ liệu phân bố không đều | Phân tích key distribution và thiết kế lại partitioning khi cần |
| Tăng replica gây latency đột biến | Rebalance và warm-up consumer | Theo dõi assignment, triển khai scale theo bước và dùng strategy phù hợp |

## 15. Checklist trước khi tăng concurrency

- [ ] Đã biết tổng số partition listener có thể đọc.
- [ ] Đã kiểm tra số consumer hiện tại trong toàn group, bao gồm mọi replica.
- [ ] Concurrency không vượt quá mức song song hữu ích của partition.
- [ ] Listener bean và dependency an toàn khi được gọi đồng thời.
- [ ] Database/HTTP connection pool đủ năng lực cho tải đồng thời.
- [ ] Thời gian xử lý batch nằm trong `max.poll.interval.ms`.
- [ ] Đã kiểm tra ordering theo key và partition.
- [ ] Có metric consumer lag, processing time và rebalance.
- [ ] Đã thử tải đại diện và đo throughput trước/sau khi tăng.
- [ ] Có kế hoạch rollback concurrency nếu downstream bị quá tải.

## 16. Kết luận

`concurrency` của Spring Kafka listener container quyết định số consumer con và thread poll loop được tạo cho một listener endpoint. Tăng concurrency giúp xử lý nhiều partition song song, nhưng một partition trong cùng consumer group chỉ được gán cho một consumer tại một thời điểm. Vì vậy, partition count, tổng số replica và concurrency cùng xác định mức song song thực tế.

Khi scale, hãy bảo đảm listener và dependency thread-safe, downstream đủ năng lực, thời gian xử lý không vượt poll interval và thứ tự theo partition vẫn phù hợp với nghiệp vụ. Đo consumer lag, processing time, assignment và rebalance trước khi tăng thêm consumer. Concurrency hiệu quả là mức giúp throughput tăng mà không làm hệ thống downstream hoặc consumer group mất ổn định.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-driven.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka — Consumer Groups](https://kafka.apache.org/documentation/#intro_consumers)
