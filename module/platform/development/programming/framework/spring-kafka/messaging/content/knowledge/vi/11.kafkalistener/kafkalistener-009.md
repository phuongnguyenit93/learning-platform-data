# Khai báo topicPartitions

`@KafkaListener` có thể nhận record bằng cách subscribe vào một hoặc nhiều topic, hoặc được gán trực tiếp một tập partition cụ thể. Khi cần chỉ định chính xác topic và partition mà listener đọc, Spring Kafka cung cấp thuộc tính `topicPartitions` cùng annotation lồng `@TopicPartition` và `@PartitionOffset`.

Trong module `SPRING_KAFKA_MESSAGING`, consumer thường dùng `@KafkaListener` để nhận event từ Kafka. Khai báo `topicPartitions` hữu ích khi ứng dụng cần kiểm soát phạm vi partition được đọc, xử lý một luồng dữ liệu đã phân chia trước hoặc thực hiện tác vụ replay có phạm vi rõ ràng. Đây là cơ chế phân công thủ công, vì vậy cần hiểu tác động của nó đến consumer group, rebalance, offset và khả năng mở rộng.

## 1. `topicPartitions` dùng để làm gì?

Một topic có thể gồm nhiều partition. Khi listener subscribe vào topic, Kafka group coordinator phân phối partition cho các consumer member trong cùng group. Khi listener khai báo `topicPartitions`, ứng dụng chỉ định trực tiếp partition nào được consumer đọc.

Ví dụ topic `orders` có bốn partition:

```text
orders
├── partition 0
├── partition 1
├── partition 2
└── partition 3
```

Nếu listener được khai báo chỉ đọc partition `0` và `2`, nó sẽ nhận record từ hai partition đó. Record ở partition `1` và `3` không thuộc phạm vi listener này.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.TopicPartition;
import org.springframework.stereotype.Component;

@Component
public class OrderPartitionListener {

    @KafkaListener(
            id = "ordersPartitionListener",
            groupId = "orders-partition-reader",
            topicPartitions = @TopicPartition(
                    topic = "orders",
                    partitions = { "0", "2" }
            )
    )
    public void listen(String payload) {
        System.out.println("Received order event: " + payload);
    }
}
```

Trong ví dụ, `partitions` là danh sách chỉ số partition dưới dạng chuỗi. Kafka đánh số partition từ `0`; topic phải tồn tại và có các partition được khai báo. `topicPartitions` không tạo topic hoặc partition mới.

## 2. Khai báo nhiều topic và partition

`topicPartitions` nhận một mảng `@TopicPartition`, vì vậy một listener có thể đọc các partition thuộc nhiều topic khác nhau:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.TopicPartition;
import org.springframework.stereotype.Component;

@Component
public class IntegrationPartitionListener {

    @KafkaListener(
            id = "integrationPartitionListener",
            groupId = "integration-reader",
            topicPartitions = {
                    @TopicPartition(
                            topic = "orders",
                            partitions = { "0", "1" }
                    ),
                    @TopicPartition(
                            topic = "payments",
                            partitions = { "2" }
                    )
            }
    )
    public void listen(ConsumerRecord<String, String> record) {
        System.out.printf(
                "topic=%s partition=%d offset=%d key=%s value=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value()
        );
    }
}
```

Listener trên nhận record từ `orders-0`, `orders-1` và `payments-2`. Vì nhiều topic có thể cùng gọi một phương thức listener, hãy kiểm tra `record.topic()` trước khi áp dụng quy tắc nghiệp vụ riêng cho từng loại dữ liệu.

Khi dùng `topicPartitions`, không khai báo đồng thời `topics` hoặc `topicPattern` với ý định hợp nhất hai cơ chế. `topicPartitions` là lựa chọn phân công partition tường minh và có ưu tiên riêng trong endpoint; hãy chọn một cách khai báo rõ ràng cho từng listener.

## 3. Khác biệt giữa subscribe topic và assign partition

Đây là điểm quan trọng nhất khi sử dụng `topicPartitions`.

| Cách khai báo | Cơ chế consumer | Ai phân phối partition? | Tự động rebalance theo group? |
|---|---|---|---|
| `topics = "orders"` | `subscribe()` | Kafka group coordinator | Có |
| `topicPattern = "orders\\..*"` | `subscribe()` theo pattern | Kafka group coordinator | Có |
| `topicPartitions = @TopicPartition(...)` | `assign()` | Ứng dụng khai báo partition | Không |

Khi subscribe, consumer đăng ký quan tâm đến topic và tham gia cơ chế group management. Kafka phân phối partition giữa các member, đồng thời rebalance khi member tham gia, rời group hoặc metadata thay đổi.

Khi assign thủ công, ứng dụng đưa trực tiếp danh sách `TopicPartition` cho consumer. Consumer không dùng group coordinator để phân phối partition và không tự động rebalance khi instance khác tham gia hoặc rời đi. Nếu triển khai nhiều instance, hệ thống phải tự bảo đảm mỗi partition được giao cho đúng instance theo kế hoạch.

`groupId` vẫn có thể được dùng để lưu committed offset, nhưng không biến manual assignment thành subscribe. Nếu hai instance cùng khai báo và đọc cùng một partition, cả hai có thể xử lý cùng record; nếu cùng dùng group ID để commit offset, chúng còn có thể ghi đè tiến độ của nhau. Không dùng `topicPartitions` như một cách thay thế consumer group load balancing.

## 4. Dùng `@PartitionOffset` để đặt vị trí bắt đầu

Ngoài chỉ định partition, Spring Kafka cho phép khai báo offset ban đầu bằng `partitionOffsets` và `@PartitionOffset`:

Annotation `@PartitionOffset` nằm trong package `org.springframework.kafka.annotation` cùng với `@KafkaListener` và `@TopicPartition`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.PartitionOffset;
import org.springframework.kafka.annotation.TopicPartition;
import org.springframework.stereotype.Component;

@Component
public class OrderReplayListener {

    @KafkaListener(
            id = "ordersReplayListener",
            groupId = "orders-replay",
            topicPartitions = @TopicPartition(
                    topic = "orders",
                    partitionOffsets = {
                            @PartitionOffset(
                                    partition = "0",
                                    initialOffset = "100"
                            ),
                            @PartitionOffset(
                                    partition = "1",
                                    initialOffset = "250"
                            )
                    }
            )
    )
    public void listen(String payload) {
        // Xử lý dữ liệu replay từ các offset đã chỉ định.
    }
}
```

Trong ví dụ, listener được gán partition `0` và `1` của topic `orders`; Spring Kafka thực hiện seek đến offset được khai báo khi áp dụng cấu hình initial offset cho partition. Offset là vị trí trong từng partition, không phải số thứ tự toàn cục của topic.

`initialOffset` được khai báo dưới dạng chuỗi để annotation có thể dùng giá trị cấu hình hoặc placeholder theo cơ chế hỗ trợ của Spring. Cần kiểm tra semantics seek của phiên bản Spring Kafka đang sử dụng và kiểm thử cả lần khởi động đầu lẫn lần khởi động lại: một explicit seek có thể làm listener đọc lại hoặc bỏ qua một phần dữ liệu so với committed offset đang có.

Nếu không khai báo offset seek tường minh, consumer sử dụng committed offset của group nếu có; khi chưa có committed offset hợp lệ, `auto.offset.reset` quyết định vị trí bắt đầu, chẳng hạn `earliest` hoặc `latest`. Đừng nhầm `initialOffset` với `auto.offset.reset`: một bên là vị trí seek do cấu hình listener chỉ định, bên kia là chính sách fallback của Kafka consumer khi không có offset hợp lệ.

## 5. Phân biệt partition assignment với acknowledgment/commit

`topicPartitions` quyết định **consumer đọc partition nào**. Nó không quyết định **khi nào offset được commit**.

Spring Kafka quản lý commit theo `AckMode` của listener container, ví dụ `RECORD`, `BATCH`, `MANUAL` hoặc `MANUAL_IMMEDIATE`. Cơ chế commit còn phụ thuộc `enable.auto.commit` và cấu hình container. Vì vậy:

- Có thể assign thủ công partition nhưng vẫn dùng chế độ commit offset tự động do container quản lý.
- Có thể dùng manual acknowledgment trên listener subscribe topic bình thường.
- `@PartitionOffset(initialOffset = ...)` là cấu hình seek ban đầu; nó không phải lệnh commit offset.
- Commit offset biểu thị tiến độ đã xử lý của consumer group; nó không thay đổi danh sách partition được assign.

Nếu listener dùng manual acknowledgment, hãy cấu hình `AckMode` tương ứng và chỉ acknowledge sau khi xử lý nghiệp vụ thành công. Không dùng `topicPartitions` để cố giải quyết lỗi duplicate hoặc commit sai thứ tự; cần thiết kế acknowledgment, idempotency và error handling riêng.

## 6. Phối hợp `topicPartitions` với concurrency

`@KafkaListener` có thể cấu hình `concurrency` để Spring Kafka tạo nhiều consumer chạy song song trong listener container. Khi sử dụng explicit partition assignment, Spring Kafka phân phối các partition được khai báo cho các consumer con theo cấu hình container.

```java
@KafkaListener(
        id = "ordersConcurrentListener",
        groupId = "orders-concurrent-reader",
        concurrency = "2",
        topicPartitions = @TopicPartition(
                topic = "orders",
                partitions = { "0", "1", "2", "3" }
        )
)
public void listen(String payload) {
    process(payload);
}
```

Với bốn partition và concurrency bằng hai, container có thể phân chia công việc cho hai consumer con. Nếu concurrency lớn hơn số partition được gán, một số consumer con không có partition để đọc. Tăng concurrency không làm tăng số partition và cũng không tạo thêm khả năng song song vượt quá số partition có dữ liệu.

Nếu mỗi instance ứng dụng lại khởi chạy một listener có cùng explicit assignment, mỗi instance có thể tự đọc cùng tập partition. Concurrency bên trong một instance không tự giải quyết việc phân chia partition giữa nhiều instance độc lập. Cần thiết kế một cơ chế phân bổ partition ở cấp triển khai nếu muốn mỗi partition chỉ có một owner.

## 7. Khi nào nên dùng `topicPartitions`?

| Tình huống | Có nên dùng? | Lý do |
|---|---|---|
| Một tác vụ replay cần đọc một vài partition xác định | Có thể phù hợp | Phạm vi đọc được kiểm soát rõ |
| Ứng dụng có routing/ownership partition do hệ thống ngoài quản lý | Phù hợp | Có thể gắn listener với partition đã được phân bổ |
| Mỗi consumer instance cần đọc một tập partition cố định theo topology | Có thể phù hợp | Cần quy trình quản lý ownership khi scale/restart |
| Service thông thường cần tự động scale consumer trong group | Thường không nên | `topics` và subscribe cho Kafka tự rebalance |
| Nhiều instance cùng chạy và muốn Kafka tự chia partition | Không nên | Manual assignment không tự phối hợp giữa các instance |
| Topic có partition count thường xuyên thay đổi | Cần cân nhắc | Danh sách partition khai báo tường minh có thể phải cập nhật |

Với đa số service xử lý event thông thường, subscribe theo topic thường đơn giản và dễ mở rộng hơn. Chỉ dùng explicit assignment khi có yêu cầu vận hành hoặc định tuyến rõ ràng.

## 8. Cấu hình topic và group ID

Ví dụ cấu hình consumer cơ bản:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-partition-reader
      enable-auto-commit: false
      auto-offset-reset: earliest
```

Nếu `groupId` đã được khai báo trực tiếp trên `@KafkaListener`, nó được dùng cho listener đó; nếu không, listener có thể kế thừa group ID từ cấu hình consumer factory. Cần chọn group ID ổn định nếu muốn committed offset được chia sẻ qua các lần khởi động của cùng logical consumer.

Với manual assignment, group ID chủ yếu gắn với offset commit và danh tính consumer cho các cơ chế liên quan; nó không khiến Kafka phân phối partition. Tránh dùng chung group ID cho các instance đang assign trùng partition nếu không có thiết kế commit/ownership rõ ràng.

Topic và partition phải được provisioning trước. Nếu topic chưa tồn tại hoặc partition index không hợp lệ, listener có thể không khởi động được hoặc gặp lỗi khi tạo consumer assignment. Quản lý topic bằng `KafkaAdmin`/`NewTopic` hoặc pipeline provisioning và xác minh partition count trước khi deploy listener.

## 9. Kiểm thử listener dùng `topicPartitions`

Kiểm thử cần chứng minh listener nhận đúng partition và không nhận record từ partition ngoài phạm vi.

Các kịch bản nên có:

- Tạo topic test có ít nhất ba partition.
- Gửi record vào từng partition bằng producer chỉ định partition.
- Khởi chạy listener assign một tập con, ví dụ partition `0` và `2`.
- Xác minh listener nhận record từ hai partition được gán và không nhận record từ partition `1`.
- Kiểm tra metadata `ConsumerRecord.partition()` hoặc header `KafkaHeaders.RECEIVED_PARTITION`.
- Kiểm tra `@PartitionOffset` ở lần khởi động đầu và khi khởi động lại với committed offset đã tồn tại.
- Nếu concurrency lớn hơn một, xác minh cách Spring Kafka phân chia partition giữa consumer con.
- Nếu triển khai nhiều instance, kiểm thử trường hợp assign trùng partition để thấy rõ nguy cơ duplicate processing và commit race.

Có thể dùng Embedded Kafka hoặc Testcontainers. Nên tạo topic riêng cho từng test, đặt partition count tường minh và dùng group ID riêng để tránh offset từ test trước ảnh hưởng đến kết quả.

## 10. Những lỗi thường gặp

- **Nhầm `topicPartitions` với `topics`:** một bên assign partition thủ công, một bên subscribe để group coordinator phân phối.
- **Cho rằng manual assignment tự rebalance:** khi instance chết hoặc thêm instance mới, ứng dụng phải cập nhật ownership/assignment theo quy trình riêng.
- **Khai báo partition không tồn tại:** listener không thể đọc partition chưa được tạo; kiểm tra topic metadata trước khi triển khai.
- **Nhầm offset ban đầu với committed offset:** explicit seek có thể làm thay đổi vị trí bắt đầu so với tiến độ đã lưu; cần test restart.
- **Coi `auto.offset.reset` luôn ghi đè `initialOffset`:** đây là hai cơ chế khác nhau; `auto.offset.reset` chỉ là fallback khi không có committed offset hợp lệ.
- **Nghĩ rằng assignment quyết định commit:** commit mode là cấu hình độc lập của listener container.
- **Dùng cùng group ID và cùng partition ở nhiều instance:** có thể xử lý trùng và ghi đè committed offset.
- **Tăng concurrency mà không tăng partition:** một số consumer con sẽ không có partition để xử lý.
- **Không cập nhật danh sách partition khi topic thay đổi:** listener explicit assignment có thể bỏ qua partition mới.
- **Dùng manual assignment cho hệ thống cần scale tự động:** vận hành ownership phức tạp hơn subscribe theo topic.

## 11. Checklist trước khi dùng `topicPartitions`

- [ ] Có yêu cầu rõ ràng cần chỉ định partition thay vì subscribe topic.
- [ ] Topic đã tồn tại và tất cả partition index đều hợp lệ.
- [ ] Đã hiểu listener sử dụng manual assignment, không có automatic group rebalance.
- [ ] Có kế hoạch phân bổ partition giữa các instance và xử lý ownership khi scale/restart.
- [ ] Group ID được chọn phù hợp với chiến lược committed offset.
- [ ] `initialOffset` được dùng có chủ đích và đã kiểm thử khi restart.
- [ ] Phân biệt rõ assignment, seek, acknowledgment và commit offset.
- [ ] Concurrency không vượt quá nhu cầu và số partition được gán.
- [ ] Producer/consumer test xác minh đúng partition được đọc.
- [ ] Có giám sát partition assignment, lag, lỗi listener và duplicate processing.

`topicPartitions` giúp Spring Kafka gắn listener với những partition cụ thể và có thể kết hợp `@PartitionOffset` để điều khiển vị trí bắt đầu. Đổi lại, ứng dụng chịu trách nhiệm quản lý phân công partition và vòng đời ownership. Khi cần Kafka tự chia tải và rebalance giữa các instance, subscribe bằng `topics` thường là lựa chọn phù hợp hơn.
