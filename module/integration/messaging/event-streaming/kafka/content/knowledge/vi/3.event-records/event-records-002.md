# Phân biệt dữ liệu nghiệp vụ với metadata do Kafka quản lý

## Mục tiêu bài học

Một record Kafka mang theo dữ liệu do ứng dụng tạo ra và thông tin kỹ thuật cần thiết để Kafka lưu trữ, phân phối, định vị và chuyển record đến consumer. Nếu trộn hai nhóm này với nhau, ứng dụng dễ phụ thuộc vào offset hoặc partition như thể đó là định danh nghiệp vụ; ngược lại, nếu đưa mọi thông tin vận hành vào payload, hợp đồng sự kiện trở nên khó hiểu và khó tái sử dụng.

Sau bài học, bạn có thể:

- Phân biệt payload nghiệp vụ, metadata của hợp đồng sự kiện và metadata của Kafka.
- Nhận diện vai trò của topic, partition, offset, timestamp, key, value và headers trong một Kafka record.
- Giải thích trường nào do ứng dụng cung cấp, trường nào do Kafka gán hoặc quản lý, và trường nào có thể phụ thuộc cấu hình.
- Thiết kế event envelope có định danh và thời điểm nghiệp vụ rõ ràng.
- Dùng Java Kafka client để tạo record, đọc record và tránh dùng metadata vận chuyển làm định danh nghiệp vụ.

## 1. Hai nhóm thông tin trong một luồng sự kiện

### 1.1. Dữ liệu nghiệp vụ là gì?

Dữ liệu nghiệp vụ mô tả điều đã xảy ra trong miền ứng dụng hoặc thông tin cần thiết để một dịch vụ khác hiểu và xử lý sự kiện. Ví dụ với hệ thống bán hàng, một sự kiện `OrderCreated` có thể chứa mã đơn hàng, khách hàng, các dòng hàng, tổng tiền và thời điểm đơn hàng được tạo.

Các trường này có ý nghĩa ngay cả khi sự kiện được gửi qua Kafka, ghi vào file, chuyển qua một message broker khác hoặc phát lại trong một môi trường kiểm thử. Chúng thuộc về hợp đồng giữa producer và consumer.

Một payload ví dụ:

```json
{
  "orderId": "ORD-2026-00421",
  "customerId": "CUS-018",
  "currency": "VND",
  "totalAmount": 1250000,
  "items": [
    { "sku": "KB-01", "quantity": 1, "unitPrice": 850000 },
    { "sku": "MS-02", "quantity": 1, "unitPrice": 400000 }
  ]
}
```

Consumer có thể dùng payload này để cập nhật đơn hàng, gửi email xác nhận hoặc tạo dữ liệu phân tích. Các consumer đó không cần biết record đang nằm ở partition nào mới hiểu `orderId` là gì.

### 1.2. Metadata do Kafka quản lý là gì?

Kafka cần thông tin kỹ thuật để xác định record thuộc luồng nào, được lưu ở đâu và consumer cần đọc từ vị trí nào. Ví dụ:

- **Topic** xác định luồng logic mà record được ghi vào.
- **Partition** xác định phân vùng log chứa record trong topic.
- **Offset** xác định vị trí của record trong log của partition đó.
- **Leader epoch** (khi client/API cung cấp) giúp nhận diện thế hệ leader của partition trong một số thao tác và tình huống phục hồi.

Các trường này có ý nghĩa trong Kafka và công cụ vận hành Kafka. Chúng không thay thế mã đơn hàng, mã khách hàng hay mã sự kiện của miền nghiệp vụ.

### 1.3. Metadata của hợp đồng sự kiện và metadata vận chuyển

Không phải mọi thông tin được gọi là metadata đều do Kafka tạo ra. Ứng dụng thường cần thêm các trường mô tả sự kiện, chẳng hạn:

- `eventId`: định danh ổn định của một sự kiện nghiệp vụ.
- `eventType`: loại sự kiện, ví dụ `OrderCreated`.
- `schemaVersion`: phiên bản cấu trúc payload.
- `occurredAt`: thời điểm sự kiện thực sự xảy ra trong nghiệp vụ.
- `aggregateId` hoặc `orderId`: định danh thực thể mà sự kiện mô tả.

Đây là metadata của hợp đồng sự kiện do ứng dụng định nghĩa. Nó vẫn là dữ liệu ứng dụng, dù không phải tất cả trường đều là thuộc tính nghiệp vụ cốt lõi.

Một cách phân loại hữu ích:

| Nhóm | Ví dụ | Ai định nghĩa hoặc gán? | Mục đích |
|---|---|---|---|
| Dữ liệu nghiệp vụ | `orderId`, `totalAmount`, `items` | Ứng dụng nghiệp vụ | Diễn tả sự kiện và trạng thái liên quan |
| Metadata hợp đồng sự kiện | `eventId`, `eventType`, `schemaVersion`, `occurredAt` | Producer và nhóm sở hữu event contract | Nhận diện, diễn giải, kiểm tra và xử lý sự kiện |
| Metadata record do ứng dụng cung cấp | key, headers; đôi khi timestamp | Producer/client, theo quy ước ứng dụng | Định tuyến, truyền ngữ cảnh hoặc gắn thời điểm record |
| Metadata lưu trữ Kafka | topic, partition, offset | Topic được chọn bởi producer; partition/offset được Kafka quản lý và gán theo quá trình ghi | Lưu trữ, định vị và đọc record |

Ranh giới quan trọng là **ý nghĩa và quyền sở hữu**. Một trường thuộc hợp đồng nghiệp vụ nếu ứng dụng và consumer cần hiểu nó độc lập với Kafka. Một trường thuộc metadata Kafka nếu ý nghĩa của nó gắn với vị trí hoặc trạng thái lưu trữ trong cluster.

## 2. Cấu trúc một Kafka record

Ở mức khái niệm, record mà Kafka client gửi/nhận có các thành phần như sau:

```text
Kafka record
  +-- topic       : luồng đích
  +-- partition   : phân vùng log
  +-- offset      : vị trí trong partition (được gán khi ghi)
  +-- timestamp   : thời điểm record theo chính sách timestamp
  +-- key         : bytes do producer cung cấp, có thể null
  +-- value       : bytes payload, có thể null
  +-- headers     : các cặp key/bytes do ứng dụng cung cấp
```

Các trường trên không cùng một nguồn gốc. Producer thường chọn topic và cung cấp key, value, headers; partition có thể được chỉ định tường minh hoặc được partitioner lựa chọn; Kafka gán offset khi append record. Timestamp có thể do producer cung cấp hoặc do broker gán tùy loại timestamp được cấu hình.

### 2.1. Topic: tên luồng dữ liệu

Topic là tên logic của một luồng record, ví dụ `orders`, `payments` hoặc `inventory-events`. Producer chỉ định topic đích trong `ProducerRecord`. Topic được quản lý trong cluster với cấu hình như số partition, replication factor và chính sách retention.

Tên topic thường phản ánh loại luồng hoặc mục đích sử dụng. Nó không phải một trường payload và cũng không phải một định danh duy nhất của từng sự kiện. Một topic chứa rất nhiều record, có thể đến từ nhiều producer.

Ví dụ:

```java
ProducerRecord<String, String> record =
    new ProducerRecord<>("orders", "ORD-2026-00421", "{\"status\":\"CREATED\"}");
```

Trong ví dụ, `orders` là topic do ứng dụng chọn. Mã đơn hàng được đặt làm key; chuỗi JSON là value. Kafka quản lý nơi lưu record trong topic sau khi nhận request.

### 2.2. Partition: phân vùng log

Mỗi topic được chia thành một hoặc nhiều partition. Mỗi partition là một log có thứ tự riêng. Kafka phân phối partition trên các broker để tăng khả năng mở rộng và song song hóa.

Producer có thể chỉ định partition cụ thể. Nếu không chỉ định, producer client dùng partitioner để chọn partition, thường dựa trên key nếu key có giá trị. Vì vậy:

- Topic được producer chọn để xác định luồng logic.
- Partition có thể được producer chỉ định hoặc được partitioner chọn theo cấu hình và phiên bản client.
- Broker lưu record vào partition đích và quản lý replica của partition đó.

Partition là khái niệm hạ tầng. Consumer thường cần nó để xác định thứ tự và vị trí đọc, nhưng logic nghiệp vụ không nên phụ thuộc vào số partition cố định nếu không có yêu cầu rõ ràng.

### 2.3. Offset: vị trí trong một partition

Offset là vị trí record trong log của một partition. Khi broker append record vào partition, Kafka gán offset theo thứ tự log của partition đó.

Ví dụ:

```text
Topic: orders

Partition 0:  offset 0 -> event A
              offset 1 -> event B
              offset 2 -> event C

Partition 1:  offset 0 -> event D
              offset 1 -> event E
```

Offset `1` ở partition 0 và offset `1` ở partition 1 là hai vị trí khác nhau. Offset không phải số thứ tự toàn topic và cũng không phải event ID.

Một vài hệ quả quan trọng:

- Cặp `(topic, partition, offset)` định vị một record trong log Kafka tại thời điểm record còn tồn tại.
- Cùng một sự kiện được publish lại có thể nhận offset mới, kể cả khi payload và `eventId` không đổi.
- Khi dữ liệu được copy sang cluster khác hoặc ghi lại vào topic khác, offset có thể khác.
- Offset có thể có khoảng trống do transaction, control record hoặc cách Kafka quản lý log; không nên giả định mọi số nguyên đều tương ứng với một record ứng dụng mà consumer nhìn thấy.

Offset commit của consumer group cũng cần được phân biệt với offset của record. Khi consumer commit vị trí tiếp theo cần đọc, giá trị commit thường biểu thị **offset kế tiếp**, không phải mã nghiệp vụ của record vừa xử lý. Cách commit và thời điểm commit ảnh hưởng đến khả năng đọc lại sau lỗi.

### 2.4. Key: dữ liệu do producer cung cấp để định tuyến

Key là một phần của record do producer cung cấp. Key có thể chứa mã thực thể như `orderId`, `customerId` hoặc một giá trị khác theo yêu cầu của ứng dụng. Producer có thể dùng key để các sự kiện liên quan được định tuyến về cùng partition, từ đó giữ thứ tự trong phạm vi thực thể đó.

Key không phải metadata do Kafka tự tạo. Kafka nhận key dưới dạng bytes sau khi serializer xử lý. Kafka không tự hiểu rằng `ORD-2026-00421` là mã đơn hàng; ý nghĩa đó đến từ hợp đồng ứng dụng.

Ví dụ:

```java
ProducerRecord<String, String> record = new ProducerRecord<>(
    "orders",
    "ORD-2026-00421", // key: do ứng dụng chọn
    "{\"status\":\"CREATED\"}" // value: payload
);
```

Với partitioner mặc định trong nhiều cấu hình client, các record có cùng key thường được đưa về cùng partition khi số partition và cách phân vùng không đổi. Tuy nhiên, thay đổi số partition hoặc partitioner có thể làm mapping key-partition thay đổi. Nếu ordering là yêu cầu nghiệp vụ, cần quản lý thay đổi topology và kiểm tra partitioner thay vì xem mapping này là bất biến tuyệt đối.

Key cũng có thể là `null`. Khi không có key, partitioner có thể phân phối record theo chiến lược khác; không nên kỳ vọng các record liên quan sẽ luôn nằm cùng partition.

### 2.5. Value: payload của record

Value chứa nội dung chính mà producer muốn chuyển đến consumer. Value thường là JSON, Avro, Protobuf, String hoặc dữ liệu nhị phân tùy serializer. Kafka lưu và chuyển bytes; Kafka broker không tự hiểu cấu trúc nghiệp vụ bên trong value.

Value có thể là `null`. Trong topic bật log compaction, record có key và value `null` thường được dùng như tombstone để biểu thị việc xóa key khi compaction diễn ra. Vì vậy, consumer cần hiểu hợp đồng của topic trước khi diễn giải `null` là dữ liệu thiếu hay sự kiện xóa.

### 2.6. Headers: ngữ cảnh do ứng dụng gắn vào record

Headers là danh sách cặp key/value dạng bytes đi kèm record. Ứng dụng có thể dùng headers cho correlation ID, trace context, tên luồng nguồn hoặc thông tin định tuyến phụ trợ.

Ví dụ một số header thường gặp:

| Header | Mục đích có thể có | Lưu ý |
|---|---|---|
| `traceparent` | Truyền trace context theo W3C Trace Context | Cần tuân thủ định dạng và chính sách tracing |
| `correlation-id` | Liên kết các thao tác thuộc cùng một request/workflow | Không tự động là event ID duy nhất |
| `source-service` | Ghi nhận service phát sự kiện | Giá trị do ứng dụng cung cấp, cần xác thực nếu dùng cho quyết định bảo mật |
| `content-type` | Gợi ý định dạng nội dung | Cần thống nhất với serializer và contract |

Headers không phải nơi thay thế payload. Consumer có thể cần các trường nghiệp vụ để xử lý kể cả khi headers bị bỏ qua bởi một công cụ trung gian. Không đặt bí mật hoặc dữ liệu nhạy cảm vào headers với giả định rằng headers được bảo vệ riêng biệt so với value.

## 3. Timestamp: thời điểm record và thời điểm nghiệp vụ

Timestamp là trường dễ bị hiểu nhầm vì nó xuất hiện trong Kafka record nhưng có thể phản ánh thời điểm khác nhau.

Kafka hỗ trợ hai kiểu timestamp phổ biến:

- **CreateTime:** timestamp được producer cung cấp khi tạo record. Đây thường là mặc định trong nhiều cấu hình. Nếu producer không truyền timestamp, client thường dùng thời gian hiện tại khi tạo record.
- **LogAppendTime:** broker gán timestamp khi record được append vào log, theo cấu hình topic/broker.

Do đó, timestamp của Kafka record không nhất thiết là thời điểm sự kiện nghiệp vụ thực sự xảy ra. Ví dụ một đơn hàng được tạo lúc 09:00 nhưng ứng dụng mất mạng và gửi lại lúc 09:07; timestamp do producer gán khi tạo lại record có thể phản ánh 09:07. Nếu broker dùng `LogAppendTime`, timestamp phản ánh thời điểm broker append record, cũng không phải thời điểm khách hàng nhấn nút đặt hàng.

Nếu cần phân tích thời gian nghiệp vụ, hãy lưu trường riêng trong event contract, chẳng hạn:

```json
{
  "eventId": "evt-7f8a1d",
  "eventType": "OrderCreated",
  "occurredAt": "2026-11-20T09:00:00+07:00",
  "orderId": "ORD-2026-00421",
  "totalAmount": 1250000
}
```

Trong ví dụ này:

- `occurredAt` là thời điểm nghiệp vụ do ứng dụng định nghĩa.
- Kafka record timestamp là timestamp của record theo `CreateTime` hoặc `LogAppendTime`.
- `offset` là vị trí record trong partition.

Ba giá trị trả lời ba câu hỏi khác nhau: sự kiện xảy ra lúc nào, record được tạo/append lúc nào, và record nằm ở vị trí nào trong log. Khi phân tích độ trễ, có thể so sánh `occurredAt` với record timestamp, nhưng phải tính đến clock skew giữa các máy và quy ước múi giờ.

## 4. Thiết kế event envelope rõ ràng

Một event contract thường gồm phần mô tả sự kiện và phần dữ liệu nghiệp vụ. Cách tổ chức cụ thể phụ thuộc hệ thống, nhưng cần nhất quán giữa producer và consumer.

Ví dụ envelope:

```json
{
  "eventId": "evt-7f8a1d",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "occurredAt": "2026-11-20T09:00:00+07:00",
  "producer": "order-service",
  "aggregate": {
    "type": "Order",
    "id": "ORD-2026-00421",
    "version": 1
  },
  "data": {
    "customerId": "CUS-018",
    "currency": "VND",
    "totalAmount": 1250000
  }
}
```

Trong envelope:

- `eventId` nhận diện lần phát sinh sự kiện. Nó cần ổn định khi retry hoặc phát lại cùng một event.
- `eventType` giúp consumer chọn logic xử lý.
- `schemaVersion` giúp consumer biết cấu trúc payload thuộc phiên bản nào.
- `occurredAt` biểu thị thời điểm nghiệp vụ.
- `producer` cho biết nguồn theo hợp đồng ứng dụng; đây không phải bằng chứng xác thực danh tính service.
- `aggregate.id` và `aggregate.version` giúp nhận diện thực thể và thứ tự thay đổi của thực thể nếu domain hỗ trợ version.
- `data` chứa thông tin nghiệp vụ cần thiết cho event.

Không phải dự án nào cũng cần đúng các trường trên. Điều quan trọng là định nghĩa ý nghĩa, kiểu dữ liệu, tính bắt buộc, quy tắc tương thích và quyền sở hữu từng trường. Tránh thêm trường chỉ vì Kafka có một thuộc tính cùng tên.

### 4.1. Event ID và offset không thay thế nhau

`eventId` thuộc hợp đồng ứng dụng. Nó có thể được lưu trong database, dùng để deduplicate hoặc nối log qua nhiều hệ thống. Offset thuộc log Kafka và chỉ có ý nghĩa trong partition cụ thể.

Ví dụ một event có `eventId = evt-7f8a1d` có thể được gửi vào `orders` partition 2 offset 41. Nếu replay qua một pipeline khác và ghi vào `orders-replay` partition 0 offset 8, `eventId` vẫn có thể giữ nguyên trong khi vị trí Kafka thay đổi.

Vì vậy:

- Dùng `eventId` để nhận diện sự kiện nghiệp vụ xuyên qua hệ thống.
- Dùng `(topic, partition, offset)` để định vị record trong Kafka.
- Dùng consumer group offset để theo dõi tiến độ đọc của group.

### 4.2. Event time và entity version

Timestamp không phải lúc nào cũng đủ để sắp thứ tự thay đổi của một thực thể. Hai sự kiện có thể có timestamp bằng nhau; đồng hồ giữa các service có thể lệch; sự kiện cũ có thể đến muộn. Nếu miền nghiệp vụ cần thứ tự chính xác theo thực thể, hãy cân nhắc một `aggregate.version` hoặc sequence do domain sở hữu.

Version này cũng là dữ liệu ứng dụng, không phải Kafka offset. Consumer có thể dùng version để phát hiện sự kiện đến sai thứ tự, bỏ qua bản cũ hoặc yêu cầu đồng bộ lại theo quy tắc nghiệp vụ.

## 5. Quan sát record trong Java Kafka client

### 5.1. Tạo record ở producer

Ví dụ dưới đây minh họa key, value, timestamp và headers. Đoạn mã giả định ứng dụng đã cấu hình `KafkaProducer<String, String>` với serializer phù hợp và có một producer đang hoạt động.

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

String key = "ORD-2026-00421";
String value = "{\"eventId\":\"evt-7f8a1d\","
    + "\"eventType\":\"OrderCreated\","
    + "\"occurredAt\":\"2026-11-20T09:00:00+07:00\","
    + "\"orderId\":\"ORD-2026-00421\","
    + "\"totalAmount\":1250000}";

long recordTimestamp = Instant.now().toEpochMilli();

ProducerRecord<String, String> record = new ProducerRecord<>(
    "orders",                 // topic
    null,                      // partition: để partitioner lựa chọn
    recordTimestamp,           // timestamp do producer cung cấp
    key,                       // key do ứng dụng cung cấp
    value                      // payload do ứng dụng cung cấp
);

record.headers().add(new RecordHeader(
    "correlation-id",
    "req-92ab".getBytes(StandardCharsets.UTF_8)
));

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        // Ghi nhận lỗi gửi và xử lý theo retry/error policy của ứng dụng.
        exception.printStackTrace();
        return;
    }

    // Các giá trị dưới đây do Kafka trả về sau khi ghi thành công.
    System.out.printf(
        "topic=%s partition=%d offset=%d timestamp=%d%n",
        metadata.topic(), metadata.partition(),
        metadata.offset(), metadata.timestamp()
    );
});
```

Trong ví dụ:

- `topic`, `key`, `value`, `timestamp` và header được ứng dụng đưa vào record.
- `partition` để `null`, nghĩa là producer partitioner lựa chọn theo cấu hình.
- `metadata.partition()` và `metadata.offset()` trong callback là kết quả broker trả về sau khi record được ghi.
- Timestamp thực tế lưu trong record phụ thuộc cấu hình timestamp của topic/broker; nếu topic dùng `LogAppendTime`, broker có thể thay timestamp do producer cung cấp.

Ví dụ chỉ tập trung vào cấu trúc record. Trong ứng dụng thực tế, cần quản lý vòng đời producer, callback, lỗi gửi, timeout, đóng producer và chính sách retry phù hợp.

### 5.2. Đọc record ở consumer

Consumer nhận `ConsumerRecord`, trong đó có cả dữ liệu do ứng dụng gửi và metadata Kafka:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;

ConsumerRecord<String, String> record = /* record lấy từ poll() */;

String orderId = record.key();
String payload = record.value();
String correlationId = null;

var header = record.headers().lastHeader("correlation-id");
if (header != null) {
    correlationId = new String(header.value(), StandardCharsets.UTF_8);
}

System.out.printf("event key=%s correlation=%s%n", orderId, correlationId);
System.out.printf(
    "Kafka location: topic=%s partition=%d offset=%d%n",
    record.topic(), record.partition(), record.offset()
);
System.out.printf(
    "record timestamp=%d timestamp type=%s%n",
    record.timestamp(), record.timestampType()
);
```

`record.key()`, `record.value()` và `record.headers()` phản ánh nội dung producer gửi sau khi deserialize/giải mã theo cấu hình client. `record.topic()`, `record.partition()` và `record.offset()` mô tả vị trí record trong Kafka. `record.timestamp()` đi kèm `record.timestampType()` để biết timestamp thuộc kiểu nào.

Consumer nên parse payload theo schema và kiểm tra dữ liệu đầu vào. Không nên giả định key luôn tồn tại, header luôn có đủ hoặc value luôn là JSON hợp lệ.

## 6. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng | Hệ quả nếu thiết kế sai |
|---|---|---|
| Dùng offset làm event ID | Offset là vị trí trong một partition; event ID thuộc hợp đồng ứng dụng | Không deduplicate được ổn định qua replay/copy cluster |
| Xem partition là thuộc tính nghiệp vụ | Partition là đơn vị lưu trữ và song song hóa | Logic domain bị gắn chặt với topology Kafka |
| Xem timestamp Kafka là `occurredAt` | Record timestamp có thể là CreateTime hoặc LogAppendTime | Phân tích thời gian nghiệp vụ và độ trễ sai lệch |
| Nghĩ key do Kafka tự sinh | Key thường do producer cung cấp và serializer chuyển thành bytes | Mất khả năng định tuyến theo thực thể hoặc hiểu sai key null |
| Đưa correlation ID vào payload nhưng không thống nhất contract | Có thể dùng payload hoặc header theo quy ước xuyên hệ thống | Trace và log khó liên kết hoặc mỗi service dùng một cách |
| Cho rằng headers là dữ liệu bí mật | Headers đi cùng record và không phải vùng bảo mật riêng | Lộ credential hoặc thông tin nhạy cảm |
| Cho rằng Kafka hiểu JSON trong value | Broker chủ yếu lưu/chuyển bytes; ứng dụng chịu trách nhiệm schema | Không kiểm soát được tương thích và lỗi deserialize |
| Dùng topic name làm event type duy nhất | Topic là luồng vận chuyển; event type là khái niệm hợp đồng | Một topic chứa nhiều event type sẽ khó phân biệt |

### 6.1. Có nên lặp lại thông tin ở key, header và payload?

Đôi khi cùng một giá trị xuất hiện ở nhiều nơi, ví dụ `orderId` trong key và payload. Việc lặp lại có thể hợp lý nếu mỗi vị trí phục vụ một mục đích:

- Key hỗ trợ partitioning và compaction.
- Payload mang dữ liệu cần cho consumer nghiệp vụ.
- Header mang ngữ cảnh vận chuyển hoặc quan sát như trace/correlation.

Nếu lặp lại, phải quy định nguồn dữ liệu có thẩm quyền và cách xử lý khi các giá trị không khớp. Ví dụ `orderId` trong key khác với `orderId` trong payload là lỗi dữ liệu cần được phát hiện, không nên âm thầm chọn một giá trị.

Không lặp lại chỉ để tiện truy vấn nếu chưa có nhu cầu rõ ràng; mỗi bản sao làm tăng nguy cơ không nhất quán và chi phí thay đổi contract.

## 7. Replay, retry và xử lý trùng

Kafka cho phép consumer đọc lại record bằng cách điều chỉnh offset hoặc tạo consumer group mới. Khi replay, record có thể vẫn giữ nguyên payload, key, headers và event ID, nhưng vị trí đọc phụ thuộc topic/partition/offset của log đang phát lại.

Một sự kiện có thể xuất hiện nhiều lần vì:

- Producer retry sau timeout trong khi broker có thể đã ghi record nhưng response bị mất.
- Ứng dụng phát lại event từ outbox hoặc nguồn dữ liệu khác.
- Consumer xử lý xong side effect nhưng crash trước khi commit offset.
- Một pipeline sao chép dữ liệu sang topic/cluster khác.

Để xử lý trùng, dùng định danh ổn định như `eventId` và thiết kế consumer idempotent. Ví dụ, consumer có thể lưu `eventId` đã xử lý cùng kết quả nghiệp vụ trong database và đặt unique constraint để một event không áp dụng side effect hai lần. Cơ chế cụ thể phải bảo đảm việc ghi nhận event đã xử lý và cập nhật nghiệp vụ có tính nguyên tử phù hợp.

Không nên dùng `(topic, partition, offset)` làm khóa dedup xuyên nhiều topic hoặc cluster. Bộ ba đó hữu ích để truy vết bản ghi ở Kafka, nhưng cùng một event được copy hoặc publish lại sẽ có vị trí mới.

## 8. Schema và metadata bên ngoài Kafka

Kafka broker lưu bytes của key, value và headers. Nếu ứng dụng dùng Avro, Protobuf hoặc JSON Schema cùng Schema Registry, schema ID hoặc thông tin định dạng có thể được mã hóa trong payload theo quy ước serializer. Schema Registry là dịch vụ riêng; schema ID không phải offset và cũng không phải metadata lưu trữ Kafka.

Phân biệt ba lớp:

1. **Schema của event:** định nghĩa trường, kiểu dữ liệu, ràng buộc và quy tắc tương thích của payload.
2. **Serializer/deserializer:** chuyển object thành bytes và khôi phục bytes thành object; có thể nhúng schema identifier theo định dạng đã chọn.
3. **Kafka record metadata:** topic, partition, offset và các thông tin record do Kafka cung cấp.

Khi schema thay đổi, hãy kiểm tra tương thích ngược/tiến theo cách consumer và producer được triển khai. Việc thay đổi schema payload không đồng nghĩa topic, partition hoặc offset thay đổi; ngược lại, đổi topology Kafka không tự cập nhật schema nghiệp vụ.

## 9. Checklist thiết kế và kiểm tra một event

Trước khi đưa event lên topic, hãy trả lời các câu hỏi sau:

| Câu hỏi | Mục đích |
|---|---|
| Event mô tả sự thật nghiệp vụ nào? | Xác định ý nghĩa và ranh giới domain |
| `eventId` được tạo ở đâu và có ổn định khi retry không? | Hỗ trợ deduplication và truy vết |
| `occurredAt` có ý nghĩa gì, dùng múi giờ nào? | Phân biệt event time với record timestamp |
| Key là gì và tại sao chọn key đó? | Kiểm soát partitioning, ordering và compaction |
| Consumer cần những trường nào trong value? | Giữ payload tự đủ nghĩa cho xử lý nghiệp vụ |
| Header nào được chuẩn hóa giữa các service? | Hỗ trợ trace/correlation và ngữ cảnh vận chuyển |
| Topic và partition được chọn theo tiêu chí nào? | Tách quyết định hạ tầng khỏi hợp đồng domain |
| Consumer xử lý event trùng và event đến muộn ra sao? | Bảo vệ tính đúng đắn khi retry/replay |
| Schema có quy tắc tương thích nào? | Hỗ trợ triển khai producer/consumer lệch phiên bản |

Một record dễ vận hành thường có:

- Payload có cấu trúc và ý nghĩa nghiệp vụ rõ ràng.
- Event ID ổn định và event type dễ nhận diện.
- Event time tách biệt với Kafka record timestamp.
- Key được chọn theo yêu cầu ordering/partitioning.
- Headers có quy ước rõ ràng và không chứa bí mật.
- Topic, partition và offset được dùng để truy vết vị trí Kafka, không dùng làm định danh nghiệp vụ.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `orderId` trong payload có thể vẫn cần xuất hiện ở key của record?
2. Topic do thành phần nào chọn, và Kafka quản lý những gì liên quan đến topic?
3. Offset `15` ở partition 0 có cùng ý nghĩa với offset `15` ở partition 1 không?
4. Vì sao offset không phù hợp làm event ID khi một sự kiện được replay sang topic khác?
5. Sự khác nhau giữa `occurredAt`, `CreateTime` và `LogAppendTime` là gì?
6. Key, value và headers có phải metadata do Kafka tự tạo không? Ai định nghĩa ý nghĩa của chúng?
7. Nếu key là `null`, producer có thể mất bảo đảm ordering theo thực thể như thế nào?
8. Consumer nên dùng event ID hay `(topic, partition, offset)` để chống áp dụng nghiệp vụ trùng? Vì sao?
9. Schema Registry và schema ID khác gì với metadata topic/partition/offset?
10. Nếu `orderId` trong key không khớp với `orderId` trong payload, consumer nên xử lý theo nguyên tắc nào?

## Kết luận

Payload và metadata hợp đồng sự kiện mô tả ý nghĩa mà các ứng dụng cần hiểu. Key, value, headers và timestamp là các thành phần record do producer cung cấp hoặc hình thành theo chính sách timestamp. Topic, partition và offset phục vụ việc lưu trữ, phân phối và định vị record trong Kafka. Giữ rõ ranh giới này giúp event contract bền vững khi replay, retry, thay đổi topology hoặc tích hợp thêm consumer.
