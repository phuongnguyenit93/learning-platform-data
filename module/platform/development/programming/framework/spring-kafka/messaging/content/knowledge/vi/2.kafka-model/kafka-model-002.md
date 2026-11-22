# Topic và log bất biến

Trong Kafka, **topic** là tên logic của một luồng sự kiện. Dữ liệu của topic được chia thành các **partition**; mỗi partition là một log có thứ tự, trong đó Kafka ghi thêm record ở cuối log và gán cho record một **offset**. Cách tổ chức này cho phép nhiều producer ghi dữ liệu, nhiều consumer đọc độc lập, đồng thời mở rộng khả năng lưu trữ và xử lý bằng cách phân phối partition trên các broker.

Khi làm việc với Spring Kafka, `KafkaTemplate` gửi record vào topic, còn `@KafkaListener` nhận record từ topic. Muốn thiết kế luồng messaging đáng tin cậy, cần hiểu dữ liệu được phân vùng ra sao, thứ tự được bảo đảm ở phạm vi nào và Kafka giữ log trong bao lâu.

## 1. Topic là luồng sự kiện logic

Topic đặt tên cho một loại dữ liệu hoặc một luồng sự kiện mà các hệ thống trao đổi với nhau. Ví dụ, ứng dụng bán hàng có thể dùng:

| Topic | Nội dung |
|---|---|
| `orders.events` | Các sự kiện phát sinh trong vòng đời đơn hàng |
| `payments.events` | Các sự kiện liên quan đến thanh toán |
| `inventory.events` | Các thay đổi về tồn kho |

Producer gửi record vào topic. Kafka lưu record trong các partition của topic. Consumer đọc record từ những partition đó theo vị trí đọc riêng của consumer group.

Topic không hoạt động giống một hàng đợi mà mỗi lần một consumer lấy record thì record lập tức biến mất. Kafka giữ dữ liệu theo chính sách lưu trữ của topic. Vì vậy, nhiều consumer group có thể đọc cùng một luồng sự kiện ở những thời điểm khác nhau và duy trì tiến độ riêng. Ví dụ, `order-projection` có thể dựng dữ liệu phục vụ truy vấn, trong khi `order-analytics` đọc cùng sự kiện để tổng hợp báo cáo.

## 2. Partition là một log có thứ tự

Một topic gồm một hoặc nhiều partition. Mỗi partition là một chuỗi record được ghi nối tiếp. Có thể hình dung cấu trúc như sau:

```text
Topic: orders.events

Partition 0:  [offset 0] -> [offset 1] -> [offset 2] -> [offset 3] -> ...
Partition 1:  [offset 0] -> [offset 1] -> [offset 2] -> ...
Partition 2:  [offset 0] -> [offset 1] -> [offset 2] -> ...
```

Các mũi tên biểu diễn thứ tự record trong cùng một partition. Mỗi partition có log và dãy offset riêng. Offset `5` ở partition 0 không có quan hệ thứ tự trước hoặc sau offset `5` ở partition 1.

### Log bất biến có nghĩa là gì?

Kafka tổ chức partition theo mô hình **append-only log**:

- Producer ghi record mới vào cuối log của partition.
- Record đã ghi không được cập nhật tại chỗ như một hàng trong cơ sở dữ liệu quan hệ.
- Consumer đọc log bằng cách tiến dần qua các offset; nhiều consumer có thể đọc cùng record độc lập.
- Kafka có thể xóa dữ liệu cũ theo retention hoặc loại bỏ phiên bản cũ theo compaction. Vì vậy, “bất biến” mô tả cách ghi nối tiếp và không sửa record tại chỗ, không có nghĩa dữ liệu được giữ vĩnh viễn.

Ví dụ, khi trạng thái đơn hàng thay đổi từ `CREATED` sang `PAID`, producer thường ghi thêm sự kiện `OrderPaid`. Sự kiện `OrderCreated` vẫn là sự kiện đã xảy ra; ứng dụng không gửi lệnh sửa record cũ thành `OrderPaid`. Consumer có thể đọc cả hai sự kiện để dựng lại lịch sử hoặc trạng thái hiện tại.

### Offset xác định vị trí đọc

Offset là số thứ tự do Kafka quản lý trong phạm vi một partition. Khi consumer nhận một `ConsumerRecord`, `record.offset()` cho biết offset của record đó trong partition tương ứng.

Offset có một số đặc điểm cần nhớ:

- Offset chỉ có ý nghĩa khi đi cùng topic và partition. Khi định danh một record, hãy xem bộ ba `(topic, partition, offset)`.
- Offset không phải số thứ tự toàn cục của topic và không thể dùng để sắp xếp record thuộc các partition khác nhau.
- Offset không phải timestamp. Hai record có offset tăng dần không nhất thiết cách nhau một khoảng thời gian cố định.
- Offset không nhất thiết bắt đầu từ `0` đối với dữ liệu mà consumer đang nhìn thấy. Retention, compaction và các control record/transaction marker có thể khiến consumer quan sát thấy khoảng trống giữa các offset.

Do đó, consumer nên dùng offset để theo dõi vị trí trong partition, không tự suy diễn rằng mọi offset liên tiếp đều tương ứng với một record ứng dụng mà nó chắc chắn sẽ nhận được.

## 3. Key quyết định cách phân phối record

Mỗi record Kafka có thể có key, value, timestamp và các header. Trong nhiều luồng nghiệp vụ, key giúp các record liên quan được đưa về cùng partition.

Với partitioner mặc định, producer dùng key để xác định partition. Các record có cùng key thường được gửi về cùng một partition khi số partition và cấu hình phân vùng không thay đổi. Ví dụ, dùng `orderId` làm key giúp các sự kiện của cùng một đơn hàng đi qua cùng partition:

```text
key = order-1001  -> Partition 1
key = order-1001  -> Partition 1
key = order-1002  -> Partition 0
key = order-1003  -> Partition 2
```

Đây là cơ sở để consumer xử lý các thay đổi của cùng một thực thể theo thứ tự. Nếu record không có key, partitioner của producer sẽ chọn partition theo chiến lược của nó; không nên dựa vào giả định rằng các record không key luôn được phân phối luân phiên từng record.

### Phạm vi bảo đảm thứ tự

Kafka bảo đảm thứ tự đọc trong một partition. Nếu các sự kiện của cùng một đơn hàng được ghi vào cùng partition, consumer có thể đọc chúng theo thứ tự log của partition đó. Kafka không tạo ra một thứ tự tổng thể giữa các partition của cùng topic.

Ví dụ, partition 0 có thể chứa `OrderCreated` ở offset 10, trong khi partition 2 chứa `PaymentReceived` ở offset 4. Không thể kết luận sự kiện nào xảy ra trước chỉ bằng cách so sánh hai offset này.

Việc tăng số partition cần được cân nhắc với luồng phụ thuộc thứ tự. Khi số partition thay đổi, phép ánh xạ key sang partition có thể thay đổi; các record cũ và mới của cùng key có thể nằm ở hai partition khác nhau. Nếu nghiệp vụ yêu cầu thứ tự theo thực thể, hãy xác định chiến lược mở rộng partition và cách chuyển đổi dữ liệu trước khi thay đổi cấu hình topic.

## 4. Partition và replication

Partition giúp phân chia dữ liệu và tải xử lý. Kafka còn có thể tạo nhiều replica cho mỗi partition để tăng khả năng chịu lỗi. Đây là hai khái niệm khác nhau:

- **Số partition** quyết định topic được chia thành bao nhiêu log độc lập, từ đó ảnh hưởng đến khả năng phân phối và xử lý song song.
- **Replication factor** quyết định mỗi partition có bao nhiêu bản sao được lưu trên các broker.

Trong một nhóm replica, một replica giữ vai trò leader và các replica còn lại theo dõi, sao chép dữ liệu từ leader. Các thao tác ghi thông thường đi qua leader. Những replica đang theo kịp leader được gọi là in-sync replicas (ISR). Khi broker gặp sự cố, Kafka có thể chọn một replica phù hợp trong ISR làm leader mới, tùy trạng thái replica và cấu hình cluster.

Replication factor bằng `1` không có bản sao dự phòng trên broker khác. Với cluster có ít nhất ba broker, replication factor bằng `3` thường tạo khả năng chịu lỗi tốt hơn. Để ràng buộc mức xác nhận ghi trong môi trường production, cần thiết kế đồng thời `acks` của producer và `min.insync.replicas` của topic/broker. Chỉ tăng replication factor mà không xem xét các cấu hình xác nhận ghi chưa đủ để xác định mức độ an toàn của dữ liệu.

## 5. Kafka giữ log bằng retention và compaction

Log có thể tăng liên tục, vì vậy topic cần chính sách dọn dữ liệu. Kafka hỗ trợ hai cơ chế chính: xóa theo retention và compact theo key.

### Retention: giữ dữ liệu trong một khoảng thời gian hoặc dung lượng

Với `cleanup.policy=delete`, Kafka đánh dấu các segment log đủ điều kiện để xóa theo giới hạn thời gian (`retention.ms`) hoặc dung lượng (`retention.bytes`). Việc xóa diễn ra theo segment, nên không nên xem `retention.ms` như một bộ hẹn giờ xóa chính xác cho từng record.

Ví dụ, nếu topic đặt `retention.ms=604800000`, dữ liệu được giữ theo chính sách thời gian khoảng bảy ngày. Sau khi segment đủ điều kiện bị xóa, consumer không thể quay lại đọc những record đã bị loại bỏ khỏi log.

Retention áp dụng độc lập với việc consumer đã đọc hay chưa. Một consumer group bị dừng lâu hơn thời gian lưu trữ có thể quay lại và phát hiện offset đã cam kết nằm trước phần dữ liệu còn tồn tại. Ứng dụng cần chọn retention phù hợp với thời gian gián đoạn tối đa dự kiến và nhu cầu replay.

### Compaction: giữ phiên bản mới nhất theo key

Với `cleanup.policy=compact`, Kafka dọn các phiên bản cũ của record có cùng key để log dần giữ lại giá trị mới nhất cho mỗi key. Compaction chạy nền, không nhất thiết diễn ra ngay sau khi producer ghi phiên bản mới.

Ví dụ, một topic lưu trạng thái tài khoản có thể nhận:

| Offset | Key | Value |
|---:|---|---|
| 0 | `account-01` | `ACTIVE` |
| 1 | `account-02` | `ACTIVE` |
| 2 | `account-01` | `SUSPENDED` |
| 3 | `account-01` | `CLOSED` |

Sau khi compaction hoàn tất trên các segment liên quan, Kafka có thể loại bỏ các phiên bản cũ của `account-01` và giữ phiên bản mới nhất `CLOSED`. Record mới vẫn được append; compaction không cập nhật record cũ tại chỗ theo cách của một cơ sở dữ liệu.

Một record có key và value `null` được gọi là **tombstone**. Tombstone biểu thị việc xóa key trong topic compact. Kafka giữ tombstone trong khoảng thời gian cấu hình để consumer có cơ hội quan sát tín hiệu xóa, sau đó tombstone cũng có thể bị dọn.

Topic có thể dùng `cleanup.policy=compact,delete` để kết hợp hai cơ chế. Hãy chọn chính sách dựa trên mục đích dữ liệu: event history thường cần retention đủ dài để replay, còn topic biểu diễn trạng thái mới nhất theo key có thể phù hợp với compaction.

## 6. Consumer group và vị trí đọc

Mỗi consumer group duy trì tiến độ đọc riêng cho từng partition. Kafka lưu offset đã cam kết của group trong topic nội bộ `__consumer_offsets`.

Trong cùng một consumer group, tại một thời điểm một partition được gán cho tối đa một consumer. Một consumer có thể nhận nhiều partition. Nếu topic có ba partition và group có hai consumer, một consumer có thể nhận hai partition, consumer còn lại nhận một partition. Nếu group có nhiều consumer hơn số partition, một số consumer sẽ chưa được gán partition.

Các group khác nhau đọc độc lập. Chẳng hạn, `order-projection` và `order-analytics` đều có thể đọc `orders.events`; việc group thứ nhất đã đọc đến offset 100 không làm group thứ hai bị chuyển vị trí đọc theo.

Phân biệt hai giá trị sau:

- `record.offset()` là offset của record consumer đang xử lý.
- Offset được commit thường là **vị trí tiếp theo cần đọc**. Nếu consumer đã xử lý record offset `12` và commit tiến độ tương ứng, giá trị commit thường là `13`.

Ứng dụng cần phối hợp thời điểm xử lý record với thời điểm commit offset. Nếu commit trước khi xử lý thành công rồi tiến trình dừng, record có thể bị bỏ qua khi đọc tiếp. Nếu xử lý xong nhưng chưa commit rồi tiến trình dừng, record có thể được đọc và xử lý lại. Vì vậy, consumer thường cần xử lý theo hướng chịu được việc nhận lại cùng một sự kiện, đặc biệt khi dùng cơ chế giao nhận at-least-once.

`auto.offset.reset` chỉ được dùng khi group chưa có offset hợp lệ hoặc offset đã lưu không còn nằm trong phạm vi log hiện tại. Giá trị `earliest` yêu cầu bắt đầu từ phần dữ liệu sớm nhất còn tồn tại; `latest` bắt đầu từ dữ liệu mới được ghi tiếp theo. Thuộc tính này không tự động đưa một group đang có offset hợp lệ quay về đầu topic.

## 7. Khai báo topic và quan sát record bằng Spring Kafka

Spring Kafka cung cấp `NewTopic` và `TopicBuilder` để khai báo topic dưới dạng bean. Khi ứng dụng Spring Boot có cấu hình Kafka Admin và kết nối được tới cluster, bean `NewTopic` có thể được dùng để yêu cầu Kafka tạo topic nếu topic đó chưa tồn tại.

Ví dụ dưới đây tạo topic có ba partition, replication factor bằng ba và retention theo thời gian bảy ngày:

```java
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersEventsTopic() {
        return TopicBuilder.name("orders.events")
                .partitions(3)
                .replicas(3)
                .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                .config(TopicConfig.CLEANUP_POLICY_CONFIG,
                        TopicConfig.CLEANUP_POLICY_DELETE)
                .build();
    }
}
```

Replication factor bằng ba yêu cầu cluster có đủ broker phù hợp. Khi chạy Kafka cục bộ chỉ có một broker, hãy dùng `.replicas(1)` cho môi trường phát triển. Số partition và replication factor nên được chọn theo tải, mức song song và yêu cầu chịu lỗi của môi trường triển khai.

Với ví dụ dùng key và value kiểu `String`, cấu hình serializer/deserializer có thể viết trong `application.yml` như sau:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

Producer dùng `KafkaTemplate` để gửi `orderId` làm key. Consumer nhận `ConsumerRecord` để quan sát topic, partition và offset mà Kafka gán cho record:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
class OrderEventMessaging {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderEventMessaging(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String eventPayload) {
        // Cùng orderId thường được partitioner mặc định định tuyến về cùng partition.
        kafkaTemplate.send("orders.events", orderId, eventPayload);
    }

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        System.out.printf(
                "topic=%s, partition=%d, offset=%d, key=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key()
        );

        String eventPayload = record.value();
        // Chuyển eventPayload tới bước xử lý nghiệp vụ của ứng dụng.
    }
}
```

Trong ví dụ, `publish` gửi record với key là `orderId`; key hỗ trợ gom các sự kiện cùng đơn hàng vào cùng partition theo partitioner mặc định. Phương thức `consume` cho thấy metadata mà consumer nhận được. Nó hữu ích khi kiểm tra cách record được phân phối và khi đối chiếu tiến độ đọc của consumer group.

`acks=all` yêu cầu broker xác nhận theo các replica đang trong ISR. Trong production, cần cấu hình thêm `min.insync.replicas` phù hợp với replication factor và khả năng chịu lỗi mong muốn. Cấu hình serializer trong ví dụ chỉ phù hợp với payload chuỗi; nếu gửi object, producer và consumer phải thống nhất định dạng serialization, deserialization và cách quản lý schema.

## 8. Cách chọn cấu hình theo yêu cầu nghiệp vụ

| Yêu cầu | Điều cần quyết định |
|---|---|
| Cần giữ thứ tự các sự kiện của cùng đơn hàng | Dùng `orderId` làm key và giữ chiến lược phân vùng ổn định |
| Cần tăng khả năng xử lý song song | Chọn số partition đủ cho mức song song dự kiến và phân bố consumer group hợp lý |
| Cần đọc lại sự kiện sau sự cố | Chọn retention dài hơn thời gian gián đoạn và thời gian replay dự kiến |
| Chỉ cần lưu trạng thái mới nhất theo định danh | Cân nhắc `cleanup.policy=compact` và quy ước key/tombstone rõ ràng |
| Cần chịu lỗi khi broker hỏng | Chọn replication factor, `acks` và `min.insync.replicas` đồng bộ |

Trước khi tạo topic cho một luồng nghiệp vụ, hãy trả lời ba câu hỏi: record cần được sắp thứ tự theo thực thể nào, ứng dụng cần replay dữ liệu trong bao lâu, và mức mất dữ liệu có thể chấp nhận là bao nhiêu. Câu trả lời sẽ định hướng key, số partition, retention/compaction và replication phù hợp.

## 9. Những nhầm lẫn thường gặp

1. **Cho rằng offset là duy nhất trong toàn topic.** Offset chỉ duy nhất trong một partition; hãy dùng bộ ba topic, partition và offset để định vị record.
2. **Cho rằng nhiều partition vẫn có thứ tự chung.** Kafka chỉ bảo đảm thứ tự trong từng partition. Muốn giữ thứ tự theo đơn hàng, hãy dùng key phù hợp và kiểm soát việc thay đổi số partition.
3. **Cho rằng consumer đọc xong thì Kafka xóa record.** Dữ liệu được giữ theo retention hoặc compaction, độc lập với tiến độ của từng consumer group.
4. **Cho rằng log bất biến nghĩa là dữ liệu không bao giờ mất.** Retention và compaction có thể loại bỏ dữ liệu theo cấu hình; cần chọn chính sách phù hợp với nhu cầu replay.
5. **Cho rằng tăng số consumer luôn tăng throughput.** Trong một group, số consumer có thể xử lý song song hữu ích bị giới hạn bởi số partition được gán.
6. **Cho rằng replication factor bằng ba tự động bảo đảm mọi lần ghi đều có ba bản sao xác nhận.** Mức xác nhận còn phụ thuộc ISR, `acks` và `min.insync.replicas`.

Khi nắm được topic, partition, offset và vòng đời log, bạn có thể đọc metadata trong Spring Kafka một cách chính xác, lựa chọn key để giữ thứ tự theo nghiệp vụ và thiết kế chính sách lưu trữ phù hợp với cách các consumer group sử dụng sự kiện.
