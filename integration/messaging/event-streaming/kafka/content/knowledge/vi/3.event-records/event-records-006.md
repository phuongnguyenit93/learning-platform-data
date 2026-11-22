# CreateTime, LogAppendTime và thời gian phát sinh nghiệp vụ

## Mục tiêu

Một record Kafka có timestamp, nhưng timestamp đó không mặc nhiên là thời điểm nghiệp vụ thực sự xảy ra. Bài học này phân biệt timestamp do producer tạo, timestamp do broker ghi nhận và thời gian nằm trong dữ liệu nghiệp vụ. Bạn sẽ cấu hình `CreateTime`/`LogAppendTime`, quan sát timestamp ở consumer Java và chọn đúng loại thời gian khi xây dựng xử lý event-time.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa và nguồn tạo của `CreateTime`, `LogAppendTime`, event time và processing time.
- Cấu hình timestamp type ở broker hoặc topic và kiểm tra cấu hình đang có hiệu lực.
- Chủ động gán timestamp cho `ProducerRecord`, đọc timestamp/type từ `ConsumerRecord`.
- Phân tích clock skew, sự kiện đến trễ, replay và thứ tự record khi xử lý theo thời gian.
- Thiết kế event schema giữ được thời gian nghiệp vụ ngay cả khi Kafka timestamp mang ý nghĩa khác.

## 1. Vì sao cần phân biệt nhiều loại thời gian?

Xét một đơn hàng được tạo lúc 09:00:00 tại hệ thống bán hàng, được producer gửi lúc 09:00:02, broker ghi vào log lúc 09:00:03 và consumer xử lý lúc 09:00:05. Cùng một record có thể liên quan đến bốn thời điểm khác nhau:

| Loại thời gian | Ví dụ | Câu hỏi được trả lời |
|---|---|---|
| Business event time | 09:00:00 | Nghiệp vụ thực sự xảy ra khi nào? |
| Producer/create time | 09:00:02 | Producer tạo/gửi record khi nào? |
| Log append time | 09:00:03 | Broker ghi record vào log khi nào? |
| Processing time | 09:00:05 | Ứng dụng xử lý record khi nào? |

Các thời điểm này có thể trùng nhau, nhưng không nên coi chúng là một. Producer có thể bị nghẽn trước khi gửi; mạng có thể chậm; broker có thể nhận record muộn; consumer có thể xử lý sau một khoảng thời gian dài hoặc đọc lại dữ liệu cũ.

Kafka lưu timestamp trong metadata của record dưới dạng epoch milliseconds. Timestamp này hữu ích cho quan sát và xử lý stream, nhưng không thay thế cho trường thời gian nghiệp vụ trong payload. Việc chọn loại timestamp quyết định ý nghĩa của metadata đó.

## 2. CreateTime

`CreateTime` là chế độ timestamp mặc định của Kafka. Broker giữ timestamp do producer gửi trong record. Nếu ứng dụng không chỉ định timestamp, Kafka producer client thường gán thời gian hiện tại khi gửi record.

Vì producer kiểm soát giá trị này, ứng dụng có thể chủ động dùng thời điểm nghiệp vụ làm Kafka record timestamp. Ví dụ, một sự kiện được phát lại sau vài giờ vẫn có thể mang timestamp lúc nghiệp vụ xảy ra, nếu producer đọc timestamp gốc từ nguồn dữ liệu và gán lại cho record.

Tuy nhiên, Kafka không tự biết timestamp do producer gửi có phải thời gian nghiệp vụ hay không. Nếu producer chỉ dùng thời gian máy của nó, `CreateTime` phản ánh thời điểm tạo record ở producer. Muốn nó mang nghĩa event time, ứng dụng phải chủ động đặt đúng giá trị.

**Ưu điểm**

- Phù hợp với xử lý theo thời điểm sự kiện xảy ra, đặc biệt khi producer có event time đáng tin cậy.
- Giữ được timestamp gốc khi record được chuyển tiếp hoặc replay, nếu pipeline bảo toàn giá trị đó.
- Có thể biểu diễn sự kiện đến trễ mà không biến thời điểm đến broker thành thời điểm xảy ra sự kiện.

**Điểm cần kiểm soát**

- Đồng hồ các producer có thể lệch nhau hoặc lệch với thời gian thực.
- Producer có thể gửi timestamp sai, ở tương lai hoặc quá xa quá khứ.
- Khi replay dữ liệu, timestamp gốc có thể cũ hơn nhiều so với thời gian ghi vào Kafka hiện tại.

Kafka có cấu hình `message.timestamp.difference.max.ms` để giới hạn độ lệch timestamp của message so với thời gian broker khi dùng `CreateTime`. Hãy đặt giới hạn theo đặc điểm dữ liệu và chính sách replay của hệ thống; giá trị quá chặt có thể từ chối record hợp lệ đến trễ, còn giá trị quá rộng làm giảm khả năng phát hiện timestamp bất thường.

## 3. LogAppendTime

`LogAppendTime` yêu cầu broker ghi đè timestamp do producer cung cấp bằng thời điểm broker append record vào log. Khi consumer đọc record, timestamp phản ánh thời gian broker tiếp nhận và ghi nhận record, thay vì thời điểm producer tạo ra nó.

Chế độ này hữu ích khi cần một mốc thời gian tập trung ở phía Kafka để đo độ trễ từ producer đến broker hoặc quan sát tốc độ ingest. Nếu một producer gửi record có timestamp nghiệp vụ từ nhiều giờ trước, broker vẫn đóng dấu thời điểm append hiện tại.

**Ưu điểm**

- Timestamp được lấy từ đồng hồ broker, giúp giảm khác biệt giữa các producer trong cùng cụm khi so sánh thời gian tiếp nhận.
- Hữu ích cho phân tích ingest, vận hành pipeline và xác định thời điểm record đi vào log.
- Producer không thể tự đặt một timestamp tùy ý làm timestamp Kafka cuối cùng.

**Điểm cần kiểm soát**

- Timestamp không còn biểu diễn thời điểm nghiệp vụ hoặc thời điểm producer tạo record.
- Broker có nhiều node; đồng hồ các broker vẫn cần được đồng bộ để việc phân tích thời gian nhất quán.
- Khi replay, timestamp mới phản ánh lần append hiện tại, vì vậy không thể dùng riêng nó để khôi phục event time ban đầu.

`LogAppendTime` không thêm một trường business timestamp vào payload. Nếu ứng dụng cần biết sự kiện đã xảy ra lúc nào, payload vẫn phải lưu thời điểm đó.

## 4. So sánh CreateTime và LogAppendTime

| Tiêu chí | `CreateTime` | `LogAppendTime` |
|---|---|---|
| Ai quyết định timestamp Kafka? | Producer; client có thể tự gán thời gian hiện tại nếu ứng dụng không cung cấp | Broker tại thời điểm append |
| Ý nghĩa thông thường | Thời điểm producer tạo record; có thể được ứng dụng gán bằng event time | Thời điểm record được broker ghi vào log |
| Ảnh hưởng của clock producer | Có | Không trực tiếp quyết định timestamp cuối cùng |
| Phù hợp với | Event-time khi producer cung cấp timestamp đáng tin cậy | Ingest-time và đo thời điểm tiếp nhận tại broker |
| Khi replay | Có thể giữ timestamp cũ nếu producer bảo toàn nó | Nhận timestamp append mới |
| Rủi ro chính | Clock skew hoặc timestamp do producer cung cấp sai | Mất ý nghĩa event time nếu chỉ dựa vào Kafka timestamp |

Không có lựa chọn đúng cho mọi hệ thống. Hãy xác định câu hỏi nghiệp vụ trước: cần biết sự kiện xảy ra lúc nào, hay cần biết Kafka tiếp nhận record lúc nào? Nếu cần cả hai, lưu business event time trong payload và chọn Kafka timestamp theo mục đích vận hành hoặc xử lý stream.

## 5. Business event time và processing time

Business event time là thời điểm sự kiện xảy ra trong miền nghiệp vụ. Ví dụ:

- `OrderCreated`: thời điểm đơn hàng được tạo.
- `PaymentCaptured`: thời điểm cổng thanh toán xác nhận thu tiền.
- `SensorMeasured`: thời điểm cảm biến thực hiện phép đo.
- `ShipmentDelivered`: thời điểm hàng được xác nhận giao.

Processing time là thời điểm một thành phần xử lý record. Ở consumer, đó thường là thời gian ứng dụng bắt đầu hoặc hoàn tất xử lý. Một record được replay hôm nay vẫn giữ business event time của ngày phát sinh, nhưng processing time là hôm nay.

Ví dụ payload có thể lưu nhiều mốc thời gian với tên thể hiện rõ ý nghĩa:

```json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "orderId": "O-1001",
  "occurredAt": "2026-11-20T09:00:00.000Z",
  "sourceCreatedAt": "2026-11-20T09:00:01.250Z"
}
```

`occurredAt` là thời điểm nghiệp vụ xảy ra. `sourceCreatedAt` có thể hữu ích nếu cần phân tích thời gian từ lúc nghiệp vụ xảy ra đến lúc service tạo event. Không nên đặt tên chung chung như `time` hoặc `timestamp` nếu không định nghĩa rõ semantics.

Với Java, biểu diễn thời gian tuyệt đối bằng `Instant` và serialize theo ISO-8601 UTC (đuôi `Z`) hoặc epoch milliseconds có quy ước rõ ràng. Tránh gửi local date-time không có offset/time zone, vì cùng một chuỗi có thể được diễn giải thành các thời điểm khác nhau ở môi trường khác nhau.

## 6. Cấu hình timestamp type

### 6.1. Cấu hình broker

Trong `server.properties`, cấu hình:

```properties
# Giữ timestamp do producer cung cấp (chế độ mặc định)
message.timestamp.type=CreateTime

# Chỉ áp dụng khi message.timestamp.type=CreateTime
# Từ chối timestamp lệch khỏi đồng hồ broker quá giới hạn này
message.timestamp.difference.max.ms=86400000
```

Đổi thành `LogAppendTime` nếu muốn broker đóng dấu thời gian append:

```properties
message.timestamp.type=LogAppendTime
```

`message.timestamp.difference.max.ms` chỉ có ý nghĩa với `CreateTime`; nó không biến `CreateTime` thành event time và cũng không xác thực nội dung timestamp trong payload. Hãy kiểm tra tài liệu cấu hình của đúng phiên bản Kafka đang vận hành trước khi thay đổi giá trị ở cụm thật.

### 6.2. Cấu hình riêng cho topic

Kafka hỗ trợ cấu hình `message.timestamp.type` ở cấp topic. Ví dụ, đặt topic `orders-ingest` dùng `LogAppendTime`:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders-ingest \
  --alter --add-config message.timestamp.type=LogAppendTime
```

Đọc lại cấu hình topic:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders-ingest --describe
```

Nếu muốn topic bỏ cấu hình override và quay về giá trị kế thừa từ broker, xóa cấu hình riêng:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders-ingest \
  --alter --delete-config message.timestamp.type
```

Khi tạo topic mới, cũng có thể chỉ định cấu hình ngay lúc tạo:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders-ingest --partitions 3 --replication-factor 1 \
  --config message.timestamp.type=LogAppendTime
```

Hãy kiểm tra cấu hình hiệu lực sau khi thay đổi. Trong môi trường nhiều broker, cần hiểu phạm vi cấu hình và quy trình rollout của phiên bản Kafka đang dùng; không giả định rằng chỉ sửa một file cấu hình cục bộ là toàn cụm đã đồng nhất.

## 7. Gán timestamp từ Java producer

Với Java Kafka Producer API, `ProducerRecord` có constructor nhận timestamp theo epoch milliseconds. Để dùng thời điểm nghiệp vụ làm Kafka timestamp, ứng dụng cần chủ động chuyển `Instant` sang milliseconds:

```java
Instant occurredAt = order.getOccurredAt();
String key = order.getId();
String value = objectMapper.writeValueAsString(orderCreatedEvent);

ProducerRecord<String, String> record = new ProducerRecord<>(
    "orders",
    null,                       // partition: để partitioner lựa chọn
    occurredAt.toEpochMilli(),  // timestamp: business event time
    key,
    value
);

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        // Ghi nhận lỗi gửi và xử lý theo chính sách retry của ứng dụng
        logger.error("Cannot publish order event", exception);
        return;
    }

    logger.info("Published topic={}, partition={}, offset={}, timestamp={}",
        metadata.topic(), metadata.partition(), metadata.offset(),
        metadata.timestamp());
});
```

Ví dụ này có ý nghĩa event-time khi topic/broker dùng `CreateTime`. Nếu topic dùng `LogAppendTime`, broker sẽ thay timestamp bằng thời điểm append; `occurredAt` trong payload vẫn được giữ nguyên.

Nếu constructor nhận timestamp không được dùng và ứng dụng gửi record với timestamp `null`, producer client sẽ gán thời gian tạo record. Điều đó không tự động biến timestamp thành business event time. Hãy kiểm tra cách producer tạo `ProducerRecord` và cấu hình timestamp type của topic khi điều tra dữ liệu.

## 8. Đọc timestamp ở Java consumer

`ConsumerRecord` cung cấp cả giá trị timestamp và loại timestamp:

```java
ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, String> record : records) {
    long kafkaTimestampMillis = record.timestamp();
    TimestampType timestampType = record.timestampType();

    Instant kafkaTimestamp = Instant.ofEpochMilli(kafkaTimestampMillis);
    Instant processingStartedAt = Instant.now();

    OrderCreatedEvent event = objectMapper.readValue(
        record.value(), OrderCreatedEvent.class);
    Instant businessEventTime = event.occurredAt();

    Duration eventToProcessing = Duration.between(
        businessEventTime, processingStartedAt);

    logger.info(
        "topic={}, partition={}, offset={}, timestampType={}, kafkaTimestamp={}, eventTime={}, processingStartedAt={}, eventToProcessingMs={}",
        record.topic(), record.partition(), record.offset(), timestampType,
        kafkaTimestamp, businessEventTime, processingStartedAt,
        eventToProcessing.toMillis());
}
```

Diễn giải:

- `record.timestamp()` là timestamp metadata mà Kafka trả về cho record.
- `record.timestampType()` cho biết timestamp có kiểu `CREATE_TIME` hay `LOG_APPEND_TIME` (ngoài ra API còn có trạng thái không có timestamp cho các trường hợp tương ứng).
- `event.occurredAt()` là thời gian nghiệp vụ do schema và producer định nghĩa.
- `processingStartedAt` được consumer lấy từ đồng hồ ứng dụng tại thời điểm xử lý.

Nếu `timestampType` là `LOG_APPEND_TIME`, hiệu giữa `record.timestamp()` và thời gian producer tạo/gửi record có thể dùng để ước lượng thời gian trước khi broker append, với điều kiện đồng hồ được đồng bộ và mốc so sánh có cùng semantics. Nếu là `CREATE_TIME`, hiệu đó chỉ có ý nghĩa theo giá trị producer đã gán; không mặc định là ingest latency.

## 9. Event time trong Kafka Streams

Kafka Streams dùng timestamp của record để xác định thời gian cho các phép toán windowed như tumbling, hopping hoặc session window. Timestamp extractor quyết định thời gian được gắn cho record trong xử lý stream.

Mặc định, Kafka Streams lấy timestamp từ Kafka record. Nếu producer đặt Kafka timestamp bằng business event time và topic dùng `CreateTime`, mặc định này có thể phù hợp. Nếu topic dùng `LogAppendTime` nhưng phép tính cần thời điểm nghiệp vụ, hãy trích `occurredAt` từ payload bằng một `TimestampExtractor` tùy chỉnh.

Ví dụ extractor minh họa:

```java
public final class OrderEventTimestampExtractor
        implements TimestampExtractor {

    private final ObjectMapper objectMapper;

    public OrderEventTimestampExtractor(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public long extract(ConsumerRecord<Object, Object> record,
                        long partitionTime) {
        try {
            // Ví dụ này giả định value đã được giải mã thành String.
            String json = (String) record.value();
            OrderCreatedEvent event = objectMapper.readValue(
                json, OrderCreatedEvent.class);
            return event.occurredAt().toEpochMilli();
        } catch (Exception exception) {
            throw new IllegalArgumentException(
                "Invalid event-time in record at offset " + record.offset(),
                exception);
        }
    }
}
```

Đây là ví dụ khái niệm: trong ứng dụng thực tế, nên dùng deserializer phù hợp với kiểu value, kiểm tra null/range/time zone, định nghĩa chính sách cho timestamp thiếu hoặc sai và tránh parse JSON lại nếu serializer/deserializer đã tạo object có kiểu. Không nên âm thầm thay event time lỗi bằng `Instant.now()`, vì thao tác đó biến dữ liệu không hợp lệ thành một mốc processing time và làm sai kết quả window.

Nếu mục tiêu là xử lý theo processing time, có thể dùng timestamp extractor dựa trên đồng hồ ứng dụng, chẳng hạn `WallclockTimestampExtractor`. Khi chọn extractor, hãy ghi rõ semantics trong tài liệu topology để người vận hành hiểu cửa sổ thời gian đang dựa trên event time hay processing time.

## 10. Sự kiện đến trễ, replay và thứ tự

### Sự kiện đến trễ

Một sự kiện có `occurredAt=09:00` nhưng đến Kafka lúc 09:10 có thể là dữ liệu hợp lệ: mạng gián đoạn, thiết bị offline, batch upload hoặc retry kéo dài. Với `CreateTime` được gán bằng event time, record vẫn mang timestamp 09:00. Với `LogAppendTime`, Kafka timestamp sẽ là khoảng 09:10; payload vẫn cần giữ `occurredAt=09:00`.

Trong xử lý window theo event time, sự kiện đến sau khi window đã gần hoặc đã đóng được gọi là late event. Kafka Streams có cấu hình grace period cho window để cho phép một khoảng thời gian nhận thêm sự kiện đến trễ. Chọn grace period dựa trên độ trễ thực tế, yêu cầu nghiệp vụ và chi phí giữ state; không có một giá trị đúng cho mọi topology.

### Replay và backfill

Replay có thể xảy ra khi consumer reset offset, khôi phục hệ thống hoặc nạp dữ liệu lịch sử. Trong lúc replay:

- `CreateTime` có thể giữ nguyên timestamp cũ nếu producer tái phát lại giá trị gốc.
- `LogAppendTime` phản ánh lần append mới vào log.
- Processing time phản ánh lần consumer xử lý lại.
- Business event time phải được giữ trong payload hoặc nguồn dữ liệu chuẩn.

Do đó, dashboard đo ingest hiện tại và báo cáo doanh thu theo ngày phát sinh nghiệp vụ có thể cần hai trường thời gian khác nhau. Nếu chỉ dùng một timestamp, replay có thể làm số liệu vận hành hoặc số liệu nghiệp vụ bị diễn giải sai.

### Timestamp không quyết định thứ tự log

Kafka bảo đảm thứ tự record theo offset trong từng partition. Timestamp không sắp xếp lại log và không tạo ra thứ tự tổng thể giữa các partition. Hai record có timestamp gần nhau hoặc ngược nhau vẫn được đọc theo offset trong partition của chúng.

Nếu nghiệp vụ cần thứ tự theo một thực thể, hãy chọn key ổn định (ví dụ `orderId`) để các sự kiện của thực thể đi vào cùng partition, rồi dùng offset để xác định thứ tự đã được ghi. Timestamp vẫn có thể giúp phân tích thời gian, nhưng không thay thế partition ordering.

## 11. Đồng bộ đồng hồ và chất lượng dữ liệu thời gian

Khi so sánh timestamp giữa nhiều máy, cần đồng bộ đồng hồ bằng NTP hoặc dịch vụ time synchronization tương đương. Đồng hồ lệch có thể tạo ra:

- Record `CreateTime` nằm trong tương lai so với broker.
- Độ trễ âm khi lấy thời gian broker trừ thời gian producer.
- Event hiển thị sai ngày/giờ khi serialize local time không kèm múi giờ.
- Thứ tự timestamp khác với thứ tự phát sinh hoặc thứ tự append thực tế.

Các nguyên tắc nên áp dụng:

1. Dùng UTC cho thời điểm tuyệt đối; serialize ISO-8601 có `Z` hoặc offset rõ ràng.
2. Đặt tên trường theo nghĩa, ví dụ `occurredAt`, `sourceCreatedAt`, `receivedAt` và `processedAt`.
3. Xác định rõ hệ thống nào là nguồn chuẩn của business event time.
4. Kiểm tra timestamp thiếu, sai định dạng, ngoài miền hợp lệ hoặc ở tương lai quá xa.
5. Đồng bộ đồng hồ producer, broker và consumer; theo dõi clock skew như một tín hiệu vận hành.
6. Không suy ra thứ tự nghiệp vụ toàn cục chỉ từ timestamp hoặc offset của các partition khác nhau.

## 12. Chọn timestamp theo yêu cầu

| Nhu cầu | Thiết kế gợi ý |
|---|---|
| Tính doanh thu theo ngày đơn hàng thực sự được tạo | Lưu `occurredAt` trong event; dùng nó làm event-time trong stream/table hoặc analytics |
| Đo thời gian từ lúc Kafka nhận record | Dùng `LogAppendTime` hoặc một mốc ingest riêng được ghi nhận rõ ràng |
| Phát lại dữ liệu lịch sử mà vẫn tính đúng cửa sổ nghiệp vụ | Bảo toàn business event time; cân nhắc `CreateTime` và extractor phù hợp |
| Đo thời gian consumer xử lý | Ghi processing time ở consumer/observability; không dùng business event time thay thế |
| So sánh các event của cùng một đơn hàng | Dùng key ổn định để vào cùng partition và dựa vào offset cho thứ tự log |

Một thiết kế thường dùng là giữ `occurredAt` trong payload như dữ liệu nghiệp vụ chuẩn, để Kafka record timestamp là `CreateTime` nếu cần event-time mặc định, hoặc `LogAppendTime` nếu cần mốc ingest do broker cấp. Consumer và Kafka Streams phải biết rõ đang sử dụng mốc nào.

## 13. Bài thực hành và tự kiểm tra

### Thực hành A — Quan sát hai timestamp type

1. Tạo topic `timestamp-lab` với ba partition và replication factor phù hợp môi trường lab.
2. Đặt topic dùng `CreateTime`, gửi hai record: một record không chỉ định timestamp và một record có timestamp cũ hơn vài phút.
3. Đọc bằng Java consumer, in `record.timestamp()` và `record.timestampType()`.
4. Đổi topic sang `LogAppendTime`, gửi lại record có timestamp cũ.
5. So sánh timestamp consumer đọc được và giải thích vì sao payload vẫn cần `occurredAt`.

### Thực hành B — Đo event-to-ingest và event-to-processing

1. Tạo payload có `occurredAt` theo UTC.
2. Producer đặt Kafka timestamp bằng `occurredAt` và gửi record.
3. Consumer đọc `occurredAt`, Kafka timestamp và ghi `processedAt=Instant.now()`.
4. Tính `eventToProcessing = processedAt - occurredAt`.
5. Lặp lại với topic `LogAppendTime` và so sánh `appendToProcessing` với `eventToProcessing`.
6. Thử gửi event có `occurredAt` cũ hơn hiện tại 10 phút và giải thích ảnh hưởng với event-time window.

### Câu hỏi tự kiểm tra

1. Khi topic dùng `CreateTime`, điều gì quyết định giá trị `ConsumerRecord.timestamp()`?
2. Vì sao `CreateTime` không mặc nhiên là business event time?
3. Khi dùng `LogAppendTime`, Kafka timestamp thay đổi thế nào khi record được replay?
4. Nếu cần tính số đơn hàng theo ngày phát sinh nghiệp vụ, nên dùng trường thời gian nào và vì sao?
5. Kafka bảo đảm thứ tự theo timestamp hay theo offset? Phạm vi bảo đảm thứ tự là gì?
6. Vì sao clock skew có thể tạo ra độ trễ âm?
7. Khi Kafka Streams cần event time trong payload nhưng topic dùng `LogAppendTime`, cần cấu hình thành phần nào?

## Kết luận

`CreateTime` giữ timestamp từ producer, `LogAppendTime` dùng thời điểm broker append, còn business event time và processing time là các khái niệm thuộc dữ liệu và vòng đời xử lý của ứng dụng. Hãy lưu thời điểm nghiệp vụ thành trường có tên rõ nghĩa trong event schema, chọn Kafka timestamp theo mục đích, và dùng offset/partition để hiểu thứ tự log. Thiết kế này giúp hệ thống xử lý được sự kiện đến trễ, replay và phân tích độ trễ mà không đánh đồng các mốc thời gian.
