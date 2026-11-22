# Gửi với timestamp tùy chỉnh

Mỗi Kafka record có thể mang một timestamp bên cạnh key, value và headers. Timestamp giúp mô tả thời điểm gắn với sự kiện, hỗ trợ quan sát độ trễ và xử lý dữ liệu theo thời gian. Với Spring Kafka, producer có thể chỉ định timestamp khi tạo `ProducerRecord` hoặc gọi overload tương ứng của `KafkaTemplate.send()`.

Khi xây dựng luồng messaging bằng `KafkaTemplate` và `@KafkaListener`, cần xác định rõ timestamp biểu diễn thời điểm nào. Một sự kiện có thể xảy ra ở hệ thống nguồn từ vài phút trước khi được gửi vào Kafka; broker cũng có thể gán thời điểm record được append vào log. Kafka hỗ trợ hai kiểu timestamp là `CreateTime` và `LogAppendTime`, và lựa chọn ở topic quyết định timestamp nào consumer quan sát được.

## 1. Timestamp của Kafka record

Timestamp của record Kafka là một giá trị thời gian tính bằng **mili giây kể từ Unix epoch** (1970-01-01T00:00:00Z). Trong Java, kiểu `Instant` là lựa chọn phù hợp để biểu diễn một thời điểm tuyệt đối và chuyển sang giá trị Kafka bằng `toEpochMilli()`.

Ví dụ, một dịch vụ nhận được sự kiện đơn hàng có thông tin:

```text
orderId: order-1001
event: OrderPaid
occurredAt: 2026-11-17T02:15:30Z
```

Producer có thể dùng `occurredAt` làm timestamp của record. Consumer sau đó đọc timestamp này để xác định thời điểm sự kiện được ghi nhận theo đồng hồ của hệ thống nguồn.

Timestamp là metadata của record, không phải key và cũng không phải offset:

- **Key** thường dùng để định tuyến record đến partition, ví dụ `orderId`.
- **Offset** là vị trí của record trong một partition và quyết định thứ tự log tại partition đó.
- **Timestamp** biểu diễn thời điểm được gắn với record theo kiểu timestamp của topic.

Thay đổi timestamp không làm thay đổi partition do key lựa chọn, không đổi offset và không sắp xếp lại các record đã ghi. Kafka vẫn lưu record theo thứ tự append trong partition. Timestamp có thể tăng hoặc giảm giữa hai record liên tiếp nếu producer gửi sự kiện trễ hoặc dữ liệu đến không theo thứ tự thời gian.

## 2. Phân biệt CreateTime và LogAppendTime

Kafka hỗ trợ hai kiểu timestamp chính, được cấu hình bằng thuộc tính topic `message.timestamp.type`.

| Kiểu timestamp | Giá trị được lưu trên record | Ý nghĩa |
|---|---|---|
| `CreateTime` | Timestamp do producer cung cấp; nếu producer không cung cấp thì Kafka producer thường gán thời điểm hiện tại | Phù hợp khi cần giữ thời điểm sự kiện xảy ra hoặc được tạo ở nguồn |
| `LogAppendTime` | Timestamp do broker gán khi append record vào log | Phù hợp khi cần thời điểm Kafka tiếp nhận record tại broker |

### CreateTime

Với `CreateTime`, broker giữ timestamp do producer gửi. Producer có thể gửi timestamp hiện tại hoặc một thời điểm cũ hơn lấy từ dữ liệu nghiệp vụ. Đây thường là lựa chọn phù hợp cho event time, chẳng hạn thời điểm đơn hàng được thanh toán tại hệ thống thanh toán.

Ví dụ, dịch vụ thanh toán có thể bị mất kết nối Kafka trong hai phút. Khi kết nối trở lại, nó gửi sự kiện `PaymentReceived` với timestamp là thời điểm thanh toán thực tế. Timestamp vẫn phản ánh lúc thanh toán xảy ra, dù record chỉ được Kafka nhận sau đó.

Vì producer quyết định giá trị, hệ thống cần kiểm soát đồng hồ và dữ liệu thời gian đầu vào. Timestamp sai, quá xa hiện tại hoặc không thống nhất múi giờ có thể làm sai kết quả đo độ trễ và xử lý theo event time. Tùy phiên bản và cấu hình broker, Kafka có thể áp dụng giới hạn chênh lệch timestamp để từ chối giá trị không hợp lệ.

### LogAppendTime

Với `LogAppendTime`, broker ghi đè timestamp producer gửi bằng thời điểm broker append record vào log. Giá trị này phản ánh thời điểm Kafka tiếp nhận dữ liệu ở broker leader, hữu ích khi đo thời gian ingest hoặc điều tra độ trễ gửi đến Kafka.

Nếu producer gửi một sự kiện có timestamp cũ, giá trị đó không còn là timestamp của record sau khi broker áp dụng `LogAppendTime`. Nếu nghiệp vụ vẫn cần biết thời điểm sự kiện thực sự xảy ra, hãy giữ `occurredAt` trong payload hoặc header của record.

Đồng hồ của các broker cần được đồng bộ khi dùng `LogAppendTime`, đặc biệt khi partition có thể chuyển leader giữa các broker. Sai lệch đồng hồ có thể làm số đo thời gian tiếp nhận thiếu nhất quán.

## 3. Gửi timestamp tùy chỉnh bằng ProducerRecord

`ProducerRecord` có constructor cho phép chỉ định topic, partition, timestamp, key và value. Timestamp truyền vào constructor là `Long` theo đơn vị mili giây. Nếu truyền `null` ở vị trí partition, producer vẫn dùng partitioner để chọn partition dựa trên key.

Ví dụ với Spring Kafka:

```java
import java.time.Instant;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventProducer {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderEventProducer(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(
            String orderId,
            String payload,
            Instant occurredAt
    ) {
        long timestamp = occurredAt.toEpochMilli();

        ProducerRecord<String, String> record = new ProducerRecord<>(
                "orders.events",
                null,           // Để partitioner chọn partition từ key.
                timestamp,      // Mili giây kể từ Unix epoch.
                orderId,
                payload
        );

        kafkaTemplate.send(record);
    }
}
```

Trong ví dụ, `orderId` là key và `occurredAt` là timestamp. Nếu topic dùng `CreateTime`, Kafka giữ timestamp tùy chỉnh. Nếu topic dùng `LogAppendTime`, broker thay timestamp này bằng thời điểm append.

Nên dùng `Instant` thay vì tự tạo số mili giây hoặc dùng `LocalDateTime` không có múi giờ. Nếu thời điểm đến từ chuỗi ISO-8601 có offset hoặc ký hiệu `Z`, có thể parse thành `Instant` trước khi gửi:

```java
Instant occurredAt = Instant.parse("2026-11-17T02:15:30Z");
long timestamp = occurredAt.toEpochMilli();
```

Nếu dữ liệu đầu vào là giờ địa phương, cần chuyển đổi với `ZoneId` đã biết để xác định đúng một thời điểm. Không tự giả định `LocalDateTime` là UTC.

## 4. Gửi timestamp qua overload của KafkaTemplate

Spring Kafka cũng cung cấp overload của `KafkaTemplate.send()` nhận trực tiếp timestamp:

```java
public void publish(
        String orderId,
        String payload,
        Instant occurredAt
) {
    kafkaTemplate.send(
            "orders.events",
            null,                       // Partition: để partitioner lựa chọn.
            occurredAt.toEpochMilli(), // Timestamp theo epoch milliseconds.
            orderId,                    // Key.
            payload                     // Value.
    );
}
```

Overload này tương đương với việc tạo `ProducerRecord` rồi gọi `send(record)`. Dùng `ProducerRecord` hữu ích khi cần thiết lập thêm headers hoặc giữ record như một đối tượng trước khi gửi. Dùng overload trực tiếp gọn hơn khi chỉ cần truyền các trường cơ bản.

`KafkaTemplate.send()` gửi bất đồng bộ và trả về future chứa kết quả gửi. Trong ứng dụng thực tế, hãy quan sát lỗi gửi và metadata trả về thay vì giả định record đã được broker ghi chỉ vì phương thức `send()` đã được gọi. Cách khai báo future cụ thể phụ thuộc phiên bản Spring Kafka; từ Spring Kafka 3.x, các phương thức send trả về `CompletableFuture`.

## 5. Cấu hình timestamp type cho topic

Kiểu timestamp là cấu hình của topic. Có thể khai báo topic bằng `NewTopic` và `TopicBuilder` trong Spring Kafka. Ví dụ sau chọn `CreateTime` cho `orders.events`:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
class OrderTopicConfiguration {

    @Bean
    NewTopic ordersEventsTopic() {
        return TopicBuilder.name("orders.events")
                .partitions(3)
                .replicas(1)
                .config("message.timestamp.type", "CreateTime")
                .build();
    }
}
```

Replication factor bằng một phù hợp với cluster phát triển chỉ có một broker. Trong production, chọn replication factor theo số broker và yêu cầu chịu lỗi của hệ thống. Cấu hình `message.timestamp.type` có thể đặt ở cấp broker làm mặc định và được ghi đè ở cấp topic.

Để dùng thời điểm broker append, thay cấu hình bằng:

```java
.config("message.timestamp.type", "LogAppendTime")
```

Hai lựa chọn có mục đích khác nhau. Không nên chọn `LogAppendTime` nếu downstream cần timestamp Kafka phản ánh thời điểm sự kiện xảy ra ở nguồn; trong trường hợp đó, hãy dùng `CreateTime` hoặc lưu riêng event time trong payload khi bắt buộc dùng append time.

Bean `NewTopic` giúp Spring Kafka yêu cầu Kafka Admin tạo topic với cấu hình đã khai báo khi topic chưa tồn tại. Khi topic đã được tạo trước đó, cần kiểm tra cấu hình thực tế trên cluster; không nên cho rằng chỉ sửa bean là chắc chắn thay đổi cấu hình của topic hiện hữu.

## 6. Đọc timestamp ở consumer

Consumer có thể đọc timestamp và kiểu timestamp từ `ConsumerRecord`. Với Spring Kafka, `@KafkaListener` có thể nhận trực tiếp `ConsumerRecord` để lấy cả payload lẫn metadata:

```java
import java.time.Instant;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        long timestampMillis = record.timestamp();

        if (timestampMillis >= 0) {
            Instant recordTime = Instant.ofEpochMilli(timestampMillis);
            System.out.printf(
                    "key=%s, timestamp=%s, timestampType=%s, partition=%d, offset=%d%n",
                    record.key(),
                    recordTime,
                    record.timestampType(),
                    record.partition(),
                    record.offset()
            );
        }

        process(record.value());
    }

    private void process(String payload) {
        // Xử lý sự kiện đơn hàng.
    }
}
```

`record.timestamp()` trả về timestamp theo mili giây; `record.timestampType()` cho biết timestamp thuộc kiểu `CREATE_TIME` hay `LOG_APPEND_TIME`. Kiểm tra cả hai trường giúp consumer hiểu đúng ý nghĩa của thời gian nhận được. Trong một số định dạng hoặc trường hợp record không có timestamp hợp lệ, giá trị có thể là giá trị sentinel âm; vì vậy nên kiểm tra trước khi chuyển thành `Instant`.

Nếu cần đo độ trễ ingest cho topic dùng `CreateTime`, có thể so sánh thời điểm broker/consumer quan sát với timestamp sự kiện. Phép đo này chỉ có ý nghĩa khi đồng hồ producer, broker và consumer được đồng bộ đủ tốt. Với topic dùng `LogAppendTime`, timestamp record phản ánh thời điểm append tại broker; để đo thời gian xử lý ở consumer, cần ghi thêm thời điểm xử lý tại ứng dụng.

## 7. Timestamp ảnh hưởng đến xử lý thời gian như thế nào?

Timestamp có ý nghĩa trong các hệ thống xử lý sự kiện theo thời gian, nhưng không thay thế offset và không đảm bảo thứ tự toàn cục.

### Event time, ingest time và processing time

| Khái niệm | Thời điểm biểu diễn | Nguồn thường gặp |
|---|---|---|
| Event time | Lúc sự kiện nghiệp vụ thực sự xảy ra | Dữ liệu nguồn, ví dụ `occurredAt` |
| Ingest/append time | Lúc Kafka broker ghi record vào log | Timestamp kiểu `LogAppendTime` |
| Processing time | Lúc ứng dụng consumer xử lý record | Đồng hồ của tiến trình consumer |

Ba thời điểm có thể khác nhau đáng kể. Ví dụ, sự kiện thanh toán xảy ra lúc 10:00, producer gửi lại lúc 10:03 sau khi mất kết nối và consumer xử lý lúc 10:03:02. Khi đó event time là 10:00, append time gần 10:03 và processing time gần 10:03:02.

Nếu dùng `CreateTime`, record có thể giữ event time để tổng hợp doanh thu theo giờ giao dịch. Nếu dùng `LogAppendTime`, timestamp record phù hợp hơn để thống kê thời điểm Kafka tiếp nhận dữ liệu. Nếu cần cả hai, hãy giữ event time trong payload và dùng timestamp record cho append time.

### Timestamp không sắp xếp lại log

Giả sử producer gửi ba sự kiện cùng partition theo thứ tự sau:

| Offset | Event | Timestamp |
|---:|---|---|
| 40 | `OrderCreated` | 10:00:00 |
| 41 | `OrderPaid` | 10:02:00 |
| 42 | `OrderItemAdded` (đến trễ) | 09:59:30 |

Consumer vẫn đọc offset 40, 41 rồi 42. Timestamp của record cuối cũ hơn hai record trước, nhưng Kafka không di chuyển nó lên trước trong log. Ứng dụng xử lý event time phải có chính sách cho dữ liệu đến trễ, chẳng hạn watermark, grace period hoặc cập nhật kết quả đã tính.

Kafka Streams sử dụng timestamp của record cho xử lý theo thời gian theo cấu hình timestamp extractor. Vì vậy, chọn `CreateTime` hay `LogAppendTime` có thể thay đổi kết quả cửa sổ thời gian, cách nhận biết sự kiện đến trễ và thời điểm hoàn tất cửa sổ. Hãy thống nhất timestamp semantics giữa producer và các ứng dụng downstream.

### Timestamp và retention

Với retention theo thời gian, timestamp của log segment có thể tham gia xác định khi segment đủ điều kiện xóa. Khi topic dùng `CreateTime`, timestamp do producer cung cấp vì thế cần hợp lý. Timestamp quá xa trong tương lai có thể làm sai lệch thời điểm dọn dữ liệu theo thời gian; timestamp quá cũ có thể khiến dữ liệu đủ điều kiện xóa sớm hơn dự kiến. Với `LogAppendTime`, broker sử dụng thời điểm append nên chính sách lưu trữ phản ánh thời gian dữ liệu vào log.

Không nên dùng timestamp tùy chỉnh như một cách đặt lịch xóa record hoặc thay thế retention policy. Retention được áp dụng theo segment và cấu hình topic/broker, không phải bộ hẹn giờ độc lập cho từng record.

## 8. Kiểm tra và lựa chọn cách dùng

Trước khi đưa timestamp tùy chỉnh vào production, hãy kiểm tra các điểm sau:

1. **Đơn vị:** giá trị gửi vào Kafka là epoch milliseconds. Không truyền trực tiếp epoch seconds hoặc nanoseconds.
2. **Múi giờ:** chuyển thời điểm nguồn thành `Instant`; không diễn giải `LocalDateTime` khi chưa xác định `ZoneId`.
3. **Ý nghĩa:** quyết định timestamp là event time hay broker append time và cấu hình `message.timestamp.type` tương ứng.
4. **Độ lệch đồng hồ:** đồng bộ thời gian giữa producer, broker và consumer; kiểm tra chính sách broker nếu gửi timestamp quá xa hiện tại.
5. **Partition và ordering:** tiếp tục dùng key để định tuyến record. Timestamp không đảm bảo thứ tự sự kiện.
6. **Downstream:** kiểm tra consumer và Kafka Streams có đang sử dụng timestamp record làm event time hay không.
7. **Retention:** kiểm tra tác động của timestamp tùy chỉnh đến chính sách xóa theo thời gian.
8. **Kết quả gửi:** quan sát future và metadata trả về để xác nhận record được gửi thành công và timestamp broker thực tế là giá trị mong đợi.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Tổng hợp theo thời điểm nghiệp vụ xảy ra | `CreateTime` và truyền `occurredAt` |
| Đo thời điểm Kafka tiếp nhận dữ liệu | `LogAppendTime` |
| Cần event time trong khi topic dùng append time | Lưu `occurredAt` trong payload/header và dùng timestamp record cho append time |
| Chỉ cần thời điểm producer gửi hiện tại | Để producer tự gán timestamp mặc định hoặc truyền `Instant.now()` |

Gửi timestamp tùy chỉnh giúp luồng sự kiện giữ được ngữ nghĩa thời gian phù hợp với nghiệp vụ. Khi dùng Spring Kafka, hãy truyền epoch milliseconds qua `ProducerRecord` hoặc `KafkaTemplate.send()`, xác định rõ `CreateTime` hay `LogAppendTime` ở topic và kiểm tra timestamp cùng `timestampType` tại consumer. Offset vẫn là cơ sở xác định thứ tự log; timestamp bổ sung thông tin thời gian để ứng dụng đo lường và xử lý sự kiện đúng ngữ cảnh.
