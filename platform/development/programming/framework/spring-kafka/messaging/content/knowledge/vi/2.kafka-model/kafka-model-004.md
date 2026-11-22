# Record key, value và timestamp

Kafka lưu và truyền dữ liệu dưới dạng **record** (bản ghi). Một record có phần dữ liệu `key`, `value`, `timestamp` cùng metadata như topic, partition, offset và headers. Hiểu đúng ba thành phần key, value, timestamp giúp thiết kế luồng sự kiện ổn định: các sự kiện của cùng một thực thể có thể đi cùng partition, consumer đọc được đúng payload, và ứng dụng phân biệt được thời điểm sự kiện xảy ra với thời điểm Kafka nhận dữ liệu.

Trong module `SPRING_KAFKA_MESSAGING`, ta thường tạo record bằng `KafkaTemplate` hoặc `ProducerRecord`, rồi đọc record bằng `@KafkaListener` và `ConsumerRecord`. Spring Kafka cung cấp kiểu Java thuận tiện, nhưng các nguyên tắc về key, value và timestamp vẫn là nguyên tắc của Kafka.

## 1. Cấu trúc của một Kafka record

Có thể hình dung một record sau khi được ghi vào Kafka như sau:

```text
Topic: orders
  Partition: 3
    Offset: 182
    Timestamp: 1731741000000
    Timestamp type: CreateTime
    Key: order-8421
    Value: {"orderId":"order-8421","status":"PAID"}
    Headers: event-type=OrderPaid
```

Đây là cách biểu diễn để đọc metadata. Kafka không lưu `key` và `value` dưới dạng object Java hay JSON object; producer chuyển chúng thành byte trước khi gửi. Consumer dùng deserializer tương ứng để chuyển byte trở lại kiểu dữ liệu mà ứng dụng sử dụng.

| Thành phần | Ý nghĩa | Ai cung cấp hoặc xác định? |
|---|---|---|
| `topic` | Luồng logic chứa record, ví dụ `orders` | Producer chọn topic khi gửi |
| `partition` | Phân vùng vật lý của topic; thứ tự được bảo đảm trong từng partition | Producer partitioner hoặc partition được chỉ định; broker lưu record vào partition đó |
| `offset` | Vị trí của record trong một partition | Broker gán khi ghi record |
| `key` | Định danh hoặc khóa phân vùng của record | Producer cung cấp; có thể là `null` |
| `value` | Payload chính, thường là event hoặc dữ liệu trạng thái | Producer cung cấp; có thể là `null` |
| `timestamp` | Mốc thời gian gắn với record, tính bằng mili giây từ Unix epoch | Producer hoặc broker, tùy timestamp type |
| `headers` | Metadata dạng cặp tên và byte value | Producer có thể thêm; consumer có thể đọc |

Trong Java Kafka client, hai kiểu quan trọng là:

- `ProducerRecord<K, V>` mô tả record mà producer chuẩn bị gửi. `K` là kiểu Java của key trước khi serialize ở producer và sau khi deserialize ở consumer; `V` là kiểu value tương ứng.
- `ConsumerRecord<K, V>` là record consumer nhận được, có cả dữ liệu lẫn metadata như topic, partition, offset, timestamp và headers.

Offset chỉ có ý nghĩa trong phạm vi một partition. Hai record ở hai partition khác nhau có thể cùng offset, vì vậy không dùng offset như một số thứ tự toàn cục của topic.

## 2. Key: định danh và lựa chọn partition

Key thường đại diện cho thực thể nghiệp vụ mà một chuỗi sự kiện cùng mô tả, chẳng hạn `orderId`, `accountId` hoặc `customerId`. Key có hai vai trò quan trọng:

1. **Định tuyến record:** partitioner sử dụng key để chọn partition khi producer không chỉ định partition cụ thể.
2. **Nhận diện dữ liệu khi compact:** với topic bật log compaction, Kafka dùng key để xác định những record thuộc cùng một khóa logic.

### 2.1. Key ảnh hưởng đến partition như thế nào?

Với partitioner mặc định và key khác `null`, Kafka tính hash trên byte đã serialize của key rồi chọn một partition. Do đó, cùng một key thường được đưa vào cùng partition khi số partition, cách serialize key và cấu hình partitioner không đổi.

```text
order-1001 ──┐
order-1001 ──┼──> partitioner ──> orders-2
order-1001 ──┘

order-1002 ─────> partitioner ──> orders-5
```

Điều này có ý nghĩa trực tiếp với thứ tự xử lý. Kafka bảo đảm thứ tự record trong một partition. Nếu tất cả event của `order-1001` được ghi vào cùng partition, consumer có thể đọc chuỗi event của đơn hàng đó theo thứ tự offset trong partition. Kafka không bảo đảm thứ tự tổng thể giữa các partition.

Ví dụ, nếu một đơn hàng phát sinh `OrderCreated`, `PaymentAuthorized` và `OrderShipped`, dùng `orderId` làm key giúp các event này đi cùng partition trong điều kiện phân vùng ổn định. Nếu dùng một UUID mới cho mỗi event, các event của cùng đơn hàng có thể bị phân tán và ứng dụng không còn dựa vào thứ tự trong một partition để xử lý chúng.

Khi producer chỉ định `partition` tường minh, partition được chỉ định sẽ được sử dụng thay cho việc chọn partition từ key. Custom partitioner cũng có thể thay đổi quy tắc mặc định. Vì vậy, quy tắc hash theo key là hành vi của partitioner mặc định, không phải cam kết bất biến trong mọi cấu hình.

### 2.2. Điều gì xảy ra khi key là `null`?

Record có thể không có key. Với partitioner mặc định ở các phiên bản Kafka hiện đại, producer thường dùng cơ chế sticky partitioning cho record không có key: một partition được giữ trong một khoảng gửi/batch để gom dữ liệu hiệu quả, sau đó có thể chuyển sang partition khác. Hành vi phân phối cụ thể phụ thuộc phiên bản và cấu hình producer.

Khi key là `null`, ứng dụng không có bảo đảm rằng các record của cùng một thực thể sẽ đi vào cùng partition. Chỉ bỏ key khi nghiệp vụ không cần định tuyến theo thực thể hoặc bảo đảm thứ tự theo key.

### 2.3. Chọn key ổn định

Một key tốt thường có các đặc điểm sau:

- Đại diện cho thực thể cần giữ thứ tự, ví dụ `orderId` cho vòng đời đơn hàng.
- Ổn định qua các event của cùng thực thể.
- Có cách serialize nhất quán giữa các producer và các phiên bản ứng dụng.
- Phân bố đủ đều để tránh dồn phần lớn lưu lượng vào một partition.

Nếu dùng key ghép, hãy chuẩn hóa định dạng và thứ tự các thành phần. Ví dụ `tenant-17:order-1001` rõ ràng và ổn định hơn việc nối các giá trị không có dấu phân cách. Serializer của key rất quan trọng: partitioner hash byte của key sau serialize, nên cùng một giá trị nghiệp vụ nhưng hai cách mã hóa byte khác nhau có thể đi vào partition khác nhau.

Không nên mặc định tăng số partition là thao tác không ảnh hưởng đến key. Với cách phân vùng dựa trên hash và số partition, thay đổi số partition có thể khiến một key được ánh xạ sang partition khác. Record cũ vẫn nằm ở partition cũ, còn record mới có thể đi vào partition mới; khi đó không còn một luồng offset duy nhất để thể hiện thứ tự của thực thể qua toàn bộ lịch sử. Nếu cần thứ tự nghiêm ngặt theo thực thể, hãy tính trước chiến lược mở rộng partition và cách consumer xử lý giai đoạn chuyển tiếp.

Key cũng có thể tạo ra partition nóng. Ví dụ, nếu dùng `countryCode` làm key và phần lớn traffic đến từ một quốc gia, một partition có thể nhận quá nhiều record. Chọn key là bài toán cân bằng giữa thứ tự nghiệp vụ và phân bố tải.

## 3. Value: payload của record

Value chứa dữ liệu mà consumer cần xử lý. Với hệ thống event-driven, value thường là một event có tên và cấu trúc rõ ràng, ví dụ `OrderCreated`, `PaymentCaptured` hoặc `InventoryAdjusted`. Với topic lưu trạng thái, value có thể là snapshot mới nhất của một thực thể.

Key và value được serialize độc lập. Một cấu hình thường gặp là dùng `StringSerializer` cho key và JSON serializer cho value. Hệ thống dùng Avro, Protobuf hoặc định dạng khác cũng tuân theo nguyên tắc tương tự: producer và consumer phải thống nhất schema, serializer, deserializer và chính sách tương thích schema.

Ví dụ value của event `OrderCreated`:

```json
{
  "orderId": "order-1001",
  "customerId": "customer-42",
  "total": 1250000,
  "currency": "VND",
  "occurredAt": "2026-11-17T02:15:30Z"
}
```

Trong ví dụ này, `orderId` có thể đồng thời là key để định tuyến các event của đơn hàng; toàn bộ object là value để consumer thực hiện nghiệp vụ. Không cần lặp lại mọi trường trong key: key nên nhỏ, ổn định và phục vụ định tuyến hoặc nhận diện; value phục vụ nội dung xử lý.

### 3.1. Phân biệt value rỗng và value `null`

Ba trường hợp sau không giống nhau:

| Trường hợp | Ý nghĩa ở tầng record |
|---|---|
| Value là JSON object rỗng `{}` | Payload vẫn là dữ liệu JSON có nội dung biểu diễn |
| Value là byte array rỗng | Payload tồn tại nhưng có độ dài bằng 0 |
| Value là `null` | Record không có payload value |

Với topic bật **log compaction**, record có key khác `null` và value `null` được gọi là *tombstone*. Tombstone biểu thị việc xóa giá trị hiện tại của key đó. Khi compact log, Kafka giữ lại trạng thái mới nhất theo key và dùng tombstone để truyền thông tin xóa; tombstone chỉ bị loại bỏ sau khoảng lưu giữ tombstone được cấu hình, không biến mất ngay khi producer gửi.

Ví dụ, topic `customer-state` đang có record `customer-42 -> {"name":"An"}`. Khi ứng dụng gửi `customer-42 -> null`, consumer xây dựng lại trạng thái có thể hiểu rằng dữ liệu của khách hàng này đã bị xóa. Record có key `null` không thể đóng vai trò tombstone cho một thực thể cụ thể vì không có key để nhận diện thực thể đó.

Trong topic không bật compaction, value `null` chỉ là một record không có payload; ý nghĩa nghiệp vụ do ứng dụng quy định. Vì thế, không nên dùng `null` tùy tiện nếu consumer chưa có quy ước xử lý rõ ràng.

## 4. Timestamp: thời điểm của record

Timestamp của Kafka record là số mili giây tính từ Unix epoch (`1970-01-01T00:00:00Z`). Timestamp giúp ứng dụng gắn mốc thời gian với dữ liệu, nhưng cần biết mốc đó được tạo ở đâu và đại diện cho thời điểm nào.

Kafka hỗ trợ hai timestamp type phổ biến:

| Timestamp type | Ai đặt timestamp? | Ý nghĩa |
|---|---|---|
| `CreateTime` | Producer | Thời điểm producer gắn vào record. Nếu producer không truyền timestamp, producer thường dùng thời gian hiện tại của máy gửi. |
| `LogAppendTime` | Broker | Thời điểm broker ghi record vào log; broker thay timestamp do producer gửi bằng thời gian broker nhận record. |

Loại timestamp được điều khiển bởi cấu hình `message.timestamp.type` ở broker hoặc cấu hình tương ứng ở cấp topic. `CreateTime` là chế độ thường gặp. Consumer có thể đọc cả giá trị timestamp và loại timestamp để diễn giải chính xác.

### 4.1. Event time và ingestion time

Hai mốc thời gian thường cần phân biệt:

- **Event time:** thời điểm sự kiện thực sự xảy ra trong nghiệp vụ, ví dụ thời điểm khách hàng thanh toán.
- **Ingestion time:** thời điểm Kafka broker nhận và ghi record.

Nếu producer gửi event sau một khoảng trễ và dùng `CreateTime`, timestamp có thể phản ánh event time nếu ứng dụng chủ động truyền thời điểm sự kiện xảy ra. Nếu dùng `LogAppendTime`, timestamp phản ánh thời điểm broker tiếp nhận record. Với bài toán xử lý theo cửa sổ thời gian, chọn sai mốc có thể làm kết quả thống kê lệch so với nghiệp vụ.

Nếu cần cả hai mốc, có thể giữ `occurredAt` trong payload hoặc header và dùng Kafka timestamp cho ingestion time (hoặc ngược lại theo quy ước của hệ thống). Hãy ghi rõ quy ước này trong hợp đồng event để các consumer hiểu giống nhau.

### 4.2. Timestamp không phải thứ tự toàn cục

Timestamp không phải số thứ tự duy nhất. Nhiều record có thể có cùng timestamp; đồng hồ máy producer có thể lệch nhau; record gửi muộn có thể mang event time cũ hơn record đã được ghi trước đó. Ngay cả khi timestamp tăng dần trong một luồng thử nghiệm, ứng dụng cũng không nên dựa vào điều đó như một bảo đảm của Kafka.

Nếu cần thứ tự trong partition, dùng thứ tự offset của partition đó. Nếu cần thứ tự nghiệp vụ theo một thực thể, thiết kế key để các event của thực thể đi cùng partition và bảo đảm producer gửi theo thứ tự mong muốn. Timestamp hữu ích cho phân tích thời gian và event-time processing, nhưng không thay thế offset hoặc cơ chế versioning của nghiệp vụ.

## 5. Gửi và nhận record bằng Spring Kafka

### 5.1. Gửi record với key, value và timestamp tường minh

Ví dụ sau dùng `orderId` làm key, object `OrderCreated` làm value và `occurredAt` làm timestamp. Header `event-type` bổ sung loại event để consumer hoặc công cụ quan sát có thể đọc mà không cần suy luận từ tên class.

```java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

public record OrderCreated(
        String orderId,
        BigDecimal total,
        Instant occurredAt
) {}

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        List<Header> headers = List.of(
                new RecordHeader(
                        "event-type",
                        "OrderCreated".getBytes(StandardCharsets.UTF_8)
                )
        );

        ProducerRecord<String, OrderCreated> record = new ProducerRecord<>(
                "orders",
                null, // Để partitioner chọn partition từ key
                event.occurredAt().toEpochMilli(),
                event.orderId(),
                event,
                headers
        );

        kafkaTemplate.send(record);
    }
}
```

Tham số thứ hai là `partition`; để `null` nghĩa là producer tự chọn partition. Tham số thứ ba là timestamp tính bằng mili giây. Tham số thứ tư và thứ năm lần lượt là key và value. Nếu không cần tự đặt timestamp hoặc headers, có thể dùng dạng ngắn `kafkaTemplate.send("orders", event.orderId(), event)`.

Ví dụ giả định `occurredAt` luôn có giá trị. Trong ứng dụng thực tế, cần kiểm tra dữ liệu đầu vào và thống nhất timezone/định dạng thời gian ở tầng domain. Kiểu trả về của `KafkaTemplate.send` thay đổi theo phiên bản Spring Kafka; với các phiên bản hiện đại, phương thức trả về `CompletableFuture<SendResult<K, V>>`, cho phép xử lý kết quả gửi bất đồng bộ.

Key và value serializer phải khớp với generic type của `KafkaTemplate`. Ví dụ, key kiểu `String` cần serializer/deserializer chuỗi; value kiểu `OrderCreated` cần serializer JSON phù hợp và consumer cần deserializer có thể chuyển payload về đúng kiểu. Cấu hình serializer không khớp thường dẫn đến lỗi gửi, lỗi deserialize hoặc dữ liệu không đọc được ở consumer.

### 5.2. Đọc metadata bằng `ConsumerRecord`

Nếu listener chỉ nhận tham số kiểu `OrderCreated`, Spring Kafka chuyển payload cho phương thức listener một cách thuận tiện. Khi cần kiểm tra key, timestamp, partition hoặc offset, hãy nhận `ConsumerRecord`:

```java
import java.time.Instant;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onMessage(ConsumerRecord<String, OrderCreated> record) {
        long timestamp = record.timestamp();
        String recordTime = timestamp >= 0
                ? Instant.ofEpochMilli(timestamp).toString()
                : "unknown";

        System.out.printf(
                "topic=%s partition=%d offset=%d key=%s timestamp=%s type=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                recordTime,
                record.timestampType()
        );

        OrderCreated event = record.value();
        // Xử lý event theo quy tắc nghiệp vụ.
    }
}
```

`record.key()` trả về key sau deserialize; `record.value()` trả về payload sau deserialize. `record.timestamp()` trả về timestamp dạng mili giây và `record.timestampType()` cho biết đó là `CreateTime` hay `LogAppendTime`. Các thông tin `topic`, `partition`, `offset` hữu ích khi ghi log, truy vết lỗi và đối chiếu tiến độ consumer.

Khi ghi log trong môi trường thật, tránh in toàn bộ value nếu payload có dữ liệu cá nhân hoặc thông tin nhạy cảm. Thường chỉ cần log key, topic, partition, offset, event type và correlation id đã được cho phép.

## 6. Chọn key, value và timestamp theo tình huống

| Tình huống | Key nên dùng | Value nên chứa | Timestamp nên đại diện |
|---|---|---|---|
| Event vòng đời đơn hàng | `orderId` | Event như `OrderCreated`, `OrderPaid` | Thời điểm event xảy ra nếu xử lý theo event time |
| Event của tài khoản | `accountId` | Giao dịch hoặc thay đổi số dư | Thời điểm nghiệp vụ phát sinh |
| Topic lưu trạng thái mới nhất có compaction | ID ổn định của thực thể | Snapshot hiện tại; `null` để phát tombstone khi xóa | Thời điểm cập nhật hoặc thời điểm broker nhận, theo quy ước |
| Log sự kiện độc lập, không cần affinity theo thực thể | Có thể để `null` | Payload của sự kiện | Thời điểm nghiệp vụ hoặc thời điểm tiếp nhận |

Trước khi chốt thiết kế, hãy trả lời ba câu hỏi:

1. Consumer cần giữ thứ tự theo thực thể nào? Dùng định danh của thực thể đó làm key.
2. Consumer cần dữ liệu gì để xử lý? Đặt nội dung đó trong value và quản lý schema tương thích.
3. Hệ thống cần phân tích theo thời điểm sự kiện hay thời điểm tiếp nhận? Chọn timestamp type và trường thời gian tương ứng.

## 7. Những lỗi thiết kế thường gặp

- **Dùng ID riêng cho từng event làm key trong khi cần thứ tự theo aggregate:** các event của cùng một thực thể có thể đi vào nhiều partition. Hãy cân nhắc dùng `orderId`, `accountId` hoặc aggregate ID.
- **Cho rằng cùng key luôn nằm ở cùng partition mãi mãi:** tăng số partition, đổi partitioner hoặc đổi cách serialize key có thể thay đổi kết quả định tuyến.
- **Dùng key có phân bố lệch:** một partition nóng làm giảm khả năng xử lý song song của topic. Hãy đo phân bố key bằng dữ liệu thực tế.
- **Coi timestamp là thứ tự toàn cục:** timestamp có thể trùng, lệch đồng hồ hoặc đến muộn. Dùng offset trong partition khi cần thứ tự log.
- **Nhầm `value = null` với object rỗng:** trong topic compacted, key khác `null` và value `null` có ý nghĩa tombstone.
- **Không thống nhất serializer/deserializer:** producer có thể gửi được nhưng consumer không giải mã được key hoặc value. Cần quản lý cấu hình và schema như một phần của hợp đồng event.
- **Không phân biệt event time với ingestion time:** báo cáo theo thời điểm broker nhận có thể khác với báo cáo theo thời điểm nghiệp vụ xảy ra.

## 8. Checklist trước khi đưa topic vào sử dụng

- [ ] Key đại diện cho đúng thực thể cần định tuyến hoặc compact.
- [ ] Các producer dùng cách serialize key nhất quán.
- [ ] Phân bố key không tạo partition nóng ngoài dự kiến.
- [ ] Value có schema rõ ràng và consumer có deserializer tương thích.
- [ ] Quy ước xử lý `null` value và tombstone được xác định nếu topic bật compaction.
- [ ] Timestamp được định nghĩa rõ là event time hay ingestion time.
- [ ] Consumer cần metadata sử dụng `ConsumerRecord` hoặc cơ chế lấy header phù hợp.
- [ ] Kế hoạch tăng số partition đã tính đến ảnh hưởng tới định tuyến và thứ tự theo key.

Khi key, value và timestamp được thiết kế như một hợp đồng dữ liệu, producer có thể gửi event bằng `KafkaTemplate`, còn consumer dùng `@KafkaListener` để xử lý với ngữ nghĩa nhất quán. Đây là nền tảng để triển khai các phần tiếp theo như serialization, consumer group, retry, dead-letter và kiểm thử luồng messaging.
