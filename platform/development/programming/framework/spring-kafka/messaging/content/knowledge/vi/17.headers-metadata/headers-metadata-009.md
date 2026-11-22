# Giới hạn kích thước và chi phí header

## 1. Kafka header dùng để làm gì?

Kafka record có key, value, timestamp và headers. Key/value thường mang dữ liệu chính của sự kiện; headers mang metadata nhỏ đi kèm record, chẳng hạn correlation ID, event type, schema version, tenant ID hoặc trace context.

Trong Spring Kafka, ứng dụng có thể thêm header khi gửi bằng `ProducerRecord` hoặc `Message<?>`, rồi đọc header ở consumer thông qua `ConsumerRecord.headers()` hoặc `@Header`. Header hữu ích để truyền thông tin phục vụ định tuyến, quan sát và xử lý message mà không phải nhúng tất cả metadata vào payload nghiệp vụ.

Tuy nhiên, header không miễn phí. Mỗi header làm tăng kích thước record, chi phí serialize/deserialize, lưu trữ, replication và truyền qua mạng. Kafka không có một giới hạn riêng phổ quát như `max.header.bytes` hoặc `max.header.count`; header chịu giới hạn kích thước của record batch/request và các giới hạn ứng dụng tự đặt.

Vì vậy, nên xem header là nơi chứa metadata nhỏ, ổn định và có ích cho nhiều consumer. Dữ liệu lớn hoặc dữ liệu nghiệp vụ chính nên nằm trong value hoặc hệ thống lưu trữ phù hợp.

## 2. Cấu trúc header và cách tính kích thước

Một Kafka header gồm:

- **Key**: tên header dạng chuỗi.
- **Value**: mảng byte (`byte[]`); có thể mã hóa chuỗi UTF-8, JSON nhỏ hoặc định dạng nhị phân đã thống nhất.

Kafka cho phép nhiều header có cùng key. Thứ tự header được giữ trong record; khi đọc bằng `lastHeader(name)`, ứng dụng nhận header cuối cùng có tên đó. Vì vậy, thêm header trùng tên có thể làm tăng kích thước và tạo sự mơ hồ nếu producer/consumer không thống nhất cách xử lý.

Trên wire format của Kafka, record lưu số lượng header và từng cặp key/value cùng các trường độ dài. Kích thước header vì vậy không chỉ là tổng số byte của value. Có thêm byte cho tên key, số lượng header và các trường mã hóa độ dài.

Có thể ước lượng phần dữ liệu header như sau:

\[
H \approx V(n) + \sum_{i=1}^{n}\bigl(V(|k_i|)+|k_i|+V(|v_i|)+|v_i|\bigr)
\]

Trong đó:

- `n` là số header.
- `k_i` là tên header sau khi mã hóa UTF-8.
- `v_i` là value dưới dạng byte.
- `V(x)` biểu diễn số byte cần để mã hóa độ dài `x` theo định dạng Kafka.

Đây là cách hình dung chi phí header; kích thước record thực tế còn có timestamp/offset delta, attributes, key, value, record framing và batch overhead. Nếu record được nén, kích thước lưu/truyền có thể khác kích thước trước nén.

### Độ dài chuỗi không đồng nghĩa với số byte

Khi đo header dạng chuỗi, không dùng `String.length()` làm kích thước byte. `String.length()` đếm UTF-16 code unit trong Java, trong khi header key được mã hóa thành byte và value do ứng dụng chuyển thành byte. Với tiếng Việt hoặc ký tự ngoài ASCII, số byte UTF-8 có thể lớn hơn số ký tự.

```java
String correlationId = "don-hang-1001";
byte[] value = correlationId.getBytes(StandardCharsets.UTF_8);

int byteLength = value.length;
```

Nên thống nhất encoding cho mọi producer/consumer, thông thường là UTF-8 cho header dạng chuỗi.

## 3. Header chịu giới hạn nào của Kafka?

Kafka kiểm soát kích thước dữ liệu ở cấp record batch và request. Header nằm bên trong record nên được tính vào kích thước dữ liệu này. Một header quá lớn có thể làm record/batch vượt giới hạn ngay cả khi value nghiệp vụ nhỏ.

Các cấu hình quan trọng gồm:

| Cấu hình | Phạm vi | Vai trò |
|---|---|---|
| `max.request.size` | Producer | Giới hạn kích thước request mà producer gửi; đồng thời là giới hạn thực tế đối với record batch chưa nén mà producer có thể tạo |
| `message.max.bytes` | Broker | Giới hạn kích thước record batch broker chấp nhận; cần xem cùng cấu hình topic và phiên bản Kafka |
| `max.message.bytes` | Topic | Có thể ghi đè giới hạn batch ở cấp broker cho topic cụ thể |
| `fetch.max.bytes` | Consumer | Giới hạn lượng dữ liệu tối đa broker trả về trong một fetch response |
| `max.partition.fetch.bytes` | Consumer | Giới hạn lượng dữ liệu fetch cho một partition trong một request |
| `replica.fetch.max.bytes` | Broker follower | Giới hạn lượng dữ liệu follower fetch từ leader trong một request |

Tên property và mặc định có thể thay đổi theo phiên bản Kafka hoặc cách đóng gói. Hãy kiểm tra cấu hình thực tế của broker, topic, producer và consumer thay vì dựa vào một con số mặc định chung.

Một số điểm cần nhớ:

- `max.request.size` không phải giới hạn riêng cho header; nó áp dụng ở cấp request/record batch producer.
- `message.max.bytes` và `max.message.bytes` giới hạn record batch, trong đó có key, value và headers.
- Consumer fetch limit ảnh hưởng cách dữ liệu được trả về; Kafka có ngoại lệ cho batch đầu tiên để consumer vẫn có thể tiến triển khi batch lớn hơn giới hạn fetch đã đặt.
- Replication cũng phải có khả năng vận chuyển batch. Cấu hình fetch của follower cần được xem xét khi cho phép record lớn.

Không nên tăng mọi giới hạn chỉ để một header lớn có thể đi qua. Tăng giới hạn record ảnh hưởng bộ nhớ, mạng, broker và consumer; cần xác định rõ nhu cầu trước khi thay đổi.

## 4. Không có giới hạn header riêng không có nghĩa là không giới hạn

Kafka core không cung cấp một cấu hình chuẩn độc lập để giới hạn số lượng header hoặc tổng số byte header của từng record. Tuy nhiên, mỗi header vẫn tiêu thụ kích thước record batch và chịu các giới hạn tổng thể của producer/broker.

Ứng dụng nên tự đặt chính sách, ví dụ:

- Tối đa 16 header tùy chỉnh cho một record.
- Tổng byte của tên và value header không vượt 8 KiB.
- Một value header đơn lẻ không vượt 2 KiB.
- Chỉ cho phép tên header nằm trong danh sách đã thống nhất.
- Không cho phép nhiều header trùng tên đối với các trường chỉ được có một giá trị.

Các con số trên chỉ là ví dụ về **ngân sách do ứng dụng tự chọn**, không phải giới hạn mặc định của Kafka. Mức phù hợp phải dựa trên workload, giao thức nội bộ và giới hạn record của hệ thống.

Đặt giới hạn ở producer boundary giúp từ chối dữ liệu bất thường trước khi gửi, thay vì đợi broker trả lỗi `RecordTooLargeException` hoặc để consumer gặp record khó xử lý.

## 5. Đo số lượng và kích thước header trong Java

Có thể đo gần đúng header bytes trước khi gửi. Đoạn mã sau tính số header và tổng byte của key/value, chưa cộng các trường độ dài và overhead record của Kafka:

```java
public record HeaderSize(int count, long payloadBytes) {}

public final class HeaderSizer {

    private HeaderSizer() {}

    public static HeaderSize measure(Headers headers) {
        int count = 0;
        long bytes = 0;

        for (Header header : headers) {
            count++;
            bytes += header.key().getBytes(StandardCharsets.UTF_8).length;

            byte[] value = header.value();
            if (value != null) {
                bytes += value.length;
            }
        }

        return new HeaderSize(count, bytes);
    }
}
```

Có thể dùng kết quả để kiểm tra chính sách:

```java
private static final int MAX_CUSTOM_HEADERS = 16;
private static final long MAX_HEADER_PAYLOAD_BYTES = 8 * 1024;

void validateHeaders(Headers headers) {
    HeaderSize size = HeaderSizer.measure(headers);

    if (size.count() > MAX_CUSTOM_HEADERS) {
        throw new IllegalArgumentException("Too many Kafka headers");
    }

    if (size.payloadBytes() > MAX_HEADER_PAYLOAD_BYTES) {
        throw new IllegalArgumentException("Kafka headers exceed application budget");
    }
}
```

Đây là phép đo payload header gần đúng. Nó không thay thế việc kiểm tra kích thước record/batch cuối cùng vì còn framing, key/value, record metadata và compression. Nếu cần ngân sách chính xác, hãy đo record ở dạng serialize thực tế trong integration test hoặc instrumentation phù hợp với producer.

## 6. Thêm header bằng ProducerRecord

`ProducerRecord` cho phép thêm header trước khi gửi:

```java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event,
        String correlationId,
        String traceParent) {

    ProducerRecord<String, OrderCreated> record =
            new ProducerRecord<>("orders", event.orderId(), event);

    record.headers()
            .add("event-type", "OrderCreated".getBytes(StandardCharsets.UTF_8))
            .add("schema-version", "1".getBytes(StandardCharsets.UTF_8))
            .add("correlation-id", correlationId.getBytes(StandardCharsets.UTF_8));

    if (traceParent != null) {
        record.headers().add(
                "traceparent", traceParent.getBytes(StandardCharsets.UTF_8));
    }

    validateHeaders(record.headers());
    return kafkaTemplate.send(record);
}
```

Các header trong ví dụ đều là metadata nhỏ. `event-type` và `schema-version` giúp consumer hiểu hợp đồng payload; `correlation-id` liên kết các bước xử lý; `traceparent` mang thông tin trace theo chuẩn tracing nếu hệ thống đã tích hợp.

Không đưa toàn bộ object `OrderCreated` vào header. Payload chính vẫn nằm trong value; header chỉ bổ sung thông tin cần thiết để xử lý hoặc quan sát.

## 7. Dùng Spring Message và KafkaHeaderMapper

Spring Kafka hỗ trợ gửi `Message<?>` để kết hợp payload với headers của Spring Messaging:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("correlation-id", correlationId)
        .setHeader("schema-version", "1")
        .build();

kafkaTemplate.send(message);
```

`KafkaTemplate` chuyển Spring message thành Kafka record. `KafkaHeaderMapper` ánh xạ header giữa Spring Messaging và Kafka. Cấu hình mapper có thể ảnh hưởng cách header được serialize, đặc biệt với kiểu dữ liệu không phải chuỗi hoặc byte array.

Để giảm overhead và tránh khác biệt giữa các ngôn ngữ, nên ưu tiên header dạng `String` hoặc `byte[]` với encoding/quy ước rõ ràng. Tránh truyền object Java tùy ý trong header nếu consumer có thể viết bằng Python, Go hoặc một nền tảng khác.

Spring Kafka có thể thêm metadata type cho một số header khi mapper chuyển đổi giá trị phức tạp. Điều này giúp khôi phục kiểu ở phía Spring consumer nhưng cũng tạo thêm header/byte và phụ thuộc vào cấu hình mapper. Hãy kiểm tra record thực tế khi dùng custom header mapper hoặc header không phải kiểu đơn giản.

## 8. Đọc header ở consumer

Consumer có thể đọc trực tiếp từ `ConsumerRecord`:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    Header correlationHeader =
            record.headers().lastHeader("correlation-id");

    String correlationId = correlationHeader == null
            ? null
            : new String(correlationHeader.value(), StandardCharsets.UTF_8);

    orderService.process(record.value(), correlationId);
}
```

Hoặc ánh xạ một header vào tham số bằng `@Header`:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(
        OrderCreated event,
        @Header(name = "correlation-id", required = false) byte[] correlationBytes) {

    String correlationId = correlationBytes == null
            ? null
            : new String(correlationBytes, StandardCharsets.UTF_8);

    orderService.process(event, correlationId);
}
```

Khi một key header có thể xuất hiện nhiều lần, hãy xác định rõ muốn dùng `lastHeader()` hay lặp qua tất cả header cùng tên. Không giả định header luôn duy nhất nếu producer không có chính sách kiểm soát.

## 9. Header lớn làm tăng chi phí ở đâu?

### Kích thước lưu trữ

Header nằm trong record log. Header lớn làm record batch lớn hơn, do đó tăng dung lượng cần lưu và dữ liệu phải sao chép giữa các replica. Với retention dài hoặc topic có lưu lượng cao, vài KiB thừa trên mỗi record có thể tích lũy thành lượng dữ liệu đáng kể.

### Network và replication

Producer gửi header cùng record đến broker. Broker sao chép record batch theo replication factor. Consumer fetch record cũng nhận header, kể cả khi listener không dùng chúng. Vì vậy, header lớn làm tăng network traffic trên đường producer → broker, broker → follower và broker → consumer.

### CPU, allocation và garbage collection

Header dạng chuỗi hoặc object cần được chuyển đổi thành byte. Consumer có thể tạo thêm object khi map header về Spring Message. Header nhiều hoặc lớn làm tăng allocation, copy byte, parse JSON và áp lực garbage collection.

### Quan sát và log

Header được dùng để tracing hoặc correlation có thể xuất hiện trong log, tracing span hoặc DLT. Header quá lớn làm log nặng, tăng chi phí lưu telemetry và có nguy cơ lộ dữ liệu nếu chứa thông tin nhạy cảm.

### Chi phí khi có nhiều consumer group

Kafka không tạo một bản sao log riêng cho từng consumer group; record được lưu theo replication factor của partition. Tuy nhiên, mỗi group đọc record sẽ nhận phần header đó qua fetch. Nhiều group độc lập vì vậy có thể làm tăng tổng lượng byte truyền và xử lý, dù dung lượng log không nhân theo số group.

## 10. Ước lượng chi phí header ở quy mô lớn

Giả sử:

- Mỗi record có trung bình 1.5 KiB header.
- Topic nhận 20.000 record/giây.
- Replication factor là 3.

Phần header thô được producer gửi vào topic mỗi giây xấp xỉ:

\[
20{,}000 \times 1.5\text{ KiB} \approx 29.3\text{ MiB/s}
\]

Với replication factor 3, lượng header cần được lưu trên các replica của cụm vào khoảng ba lần phần dữ liệu header thô, trước khi xét compression, segment/index và overhead khác. Nếu có nhiều consumer group đọc độc lập, mỗi group còn tạo thêm lưu lượng fetch chứa header.

Đây chỉ là ước lượng để thấy tác động theo quy mô; dung lượng thực tế phụ thuộc compression, batch, retention, replication và tốc độ đọc. Header không nên được đánh giá chỉ bằng kích thước một record đơn lẻ. Hãy nhân với record rate và thời gian lưu giữ.

## 11. Compression có loại bỏ chi phí header không?

Kafka có thể nén record batch bằng các codec như gzip, snappy, lz4 hoặc zstd tùy phiên bản và cấu hình. Header được serialize cùng record nên dữ liệu header cũng có thể được hưởng lợi từ compression nếu giá trị lặp lại hoặc có cấu trúc dễ nén.

Tuy nhiên:

- Compression không làm header biến mất; consumer vẫn phải giải nén và nhận header.
- Header ngẫu nhiên hoặc giá trị duy nhất như UUID có thể nén kém hơn chuỗi lặp.
- Producer vẫn cần serialize và giữ dữ liệu trước nén trong bộ nhớ.
- Giới hạn producer/broker có quy tắc riêng về request và record batch; không dựa vào compression để cho phép header không giới hạn.
- Compression tăng chi phí CPU và có thể đổi latency.

Hãy đo compression ratio và throughput với dữ liệu thật. Nếu header chứa correlation ID duy nhất trên mỗi record, không nên giả định nó sẽ nén đáng kể.

## 12. Nên đưa gì vào header và không nên đưa gì?

| Loại dữ liệu | Nên đặt ở đâu? | Lý do |
|---|---|---|
| Correlation ID / trace context | Header | Metadata nhỏ, dùng để nối các bước xử lý |
| Event type / schema version | Header hoặc schema envelope | Giúp nhận diện hợp đồng payload; cần quy ước thống nhất |
| Tenant ID nhỏ | Header nếu phục vụ routing/observability và không nhạy cảm | Dễ lọc/quan sát, nhưng cần kiểm tra quyền truy cập và độ tin cậy |
| User ID hoặc account ID | Thường trong payload; chỉ đưa vào header khi có yêu cầu rõ | Có thể là dữ liệu nhạy cảm và bị lộ qua log/telemetry |
| JWT, access token, API key | Không nên đặt trong header Kafka | Dễ bị sao chép qua broker, DLT, log và consumer |
| Toàn bộ HTTP request headers | Không nên copy nguyên trạng | Nhiều trường không cần thiết, có thể chứa secret và làm record lớn |
| Stack trace đầy đủ | Log hoặc hệ thống error tracking; DLT chỉ lưu khi có chính sách | Nội dung dài, dễ chứa dữ liệu nội bộ và tăng kích thước record |
| JSON context lớn hoặc binary attachment | Value hoặc object storage; header chỉ giữ reference | Header không phù hợp cho dữ liệu lớn |
| File, ảnh, nội dung tài liệu | Object storage; value chứa ID/URI có kiểm soát | Giảm tải Kafka và dễ quản lý vòng đời dữ liệu |

Một header tốt thường có tên ngắn, ý nghĩa rõ, kiểu dữ liệu đơn giản và hợp đồng ổn định. Không đưa thông tin chỉ phục vụ debug nhất thời vào mọi record nếu không có nhu cầu vận hành cụ thể.

## 13. Header trùng tên, số lượng lớn và quy ước schema

Kafka cho phép header trùng tên, nhưng ứng dụng cần quy định cách sử dụng:

- Header dạng đơn trị như `correlation-id`, `event-type`, `schema-version` nên xuất hiện tối đa một lần.
- Header dạng đa trị chỉ nên dùng khi hợp đồng quy định rõ thứ tự và cách diễn giải.
- Dùng `lastHeader()` khi quy ước yêu cầu lấy giá trị mới nhất; nếu cần tất cả giá trị, lặp qua `headers().headers(name)`.
- Không thêm cùng header ở nhiều tầng mà không xác định ai sở hữu giá trị cuối cùng.
- Chuẩn hóa tên header và encoding để producer Java, Python, Go hoặc .NET có thể trao đổi nhất quán.

Nên quản lý danh sách header được phép theo event contract. Khi đổi tên hoặc đổi kiểu header, cần đánh giá backward compatibility giống như thay đổi schema payload.

## 14. Header và metadata của Kafka không phải một

Trong vận hành, cần phân biệt header do ứng dụng gắn với metadata Kafka do broker/consumer cung cấp:

| Thông tin | Nguồn | Ví dụ |
|---|---|---|
| Custom header | Producer hoặc ứng dụng | `correlation-id`, `event-type`, `tenant-id` |
| Record key/value | Producer | `orderId`, `OrderCreated` |
| Topic/partition/offset | Kafka record metadata | `orders`, partition `2`, offset `120` |
| Timestamp | Producer hoặc broker theo timestamp type | Create time / log append time |
| Consumer group committed offset | Kafka group coordinator | Tiến độ đã commit theo group và partition |

Topic, partition và offset không cần được copy vào custom header để consumer biết record đến từ đâu; `ConsumerRecord` và các `KafkaHeaders` của Spring Kafka đã cung cấp thông tin này. Copy lại metadata có thể tạo dữ liệu trùng lặp hoặc sai lệch khi record được chuyển tiếp sang topic khác.

## 15. Theo dõi và kiểm soát chi phí header

Nên theo dõi header ở cả tầng ứng dụng và Kafka:

- Đo số header và tổng byte header trước khi publish.
- Ghi nhận phân vị kích thước header (p50, p95, p99) theo topic/event type.
- Theo dõi record size, producer send failure và lỗi `RecordTooLargeException`.
- Quan sát broker request size, network throughput, replication traffic và disk growth.
- Theo dõi consumer fetch bytes, processing latency và garbage collection khi thay đổi header schema.
- Kiểm tra DLT và log để bảo đảm exception/header không làm lộ dữ liệu nhạy cảm.

Có thể đặt metric ứng dụng như `kafka.headers.count` và `kafka.headers.bytes` theo topic, nhưng tránh dùng header value hoặc correlation ID làm metric tag vì cardinality sẽ tăng rất nhanh. Dùng topic/event type làm dimension có kiểm soát; correlation ID phù hợp với log/trace hơn là metric label.

Khi phát hiện header tăng bất thường, hãy tìm producer hoặc phiên bản event schema tạo header đó. Giảm header không cần thiết thường hiệu quả hơn tăng giới hạn toàn cụm.

## 16. Quy trình thiết kế ngân sách header

1. Liệt kê metadata thực sự cần truyền giữa producer và consumer.
2. Xác định kiểu dữ liệu, encoding và quy tắc đơn trị/đa trị cho từng header.
3. Đặt giới hạn số header, tổng byte và kích thước từng value ở tầng ứng dụng.
4. Đo header bằng byte UTF-8 hoặc byte array thực tế; không dùng số ký tự Java làm kích thước.
5. Kiểm tra tổng record/batch với `max.request.size`, `message.max.bytes`/`max.message.bytes` và cấu hình fetch liên quan.
6. Kiểm thử record lớn, header trùng, header thiếu và header không hợp lệ.
7. Đo throughput, network, storage, compression và consumer allocation với dữ liệu thật.
8. Theo dõi sau triển khai và giữ quy ước header tương thích giữa các phiên bản producer/consumer.

Nếu payload hoặc metadata vượt ngân sách, chuyển dữ liệu lớn sang value hoặc object storage và chỉ truyền một reference nhỏ trong header hoặc payload. Đảm bảo reference có quyền truy cập, thời hạn và cơ chế bảo vệ phù hợp.

## 17. Tổng kết

- Header là cặp key/string và value/byte[] gắn với từng Kafka record; Kafka cho phép nhiều header trùng tên.
- Header nằm trong record batch nên chịu giới hạn kích thước của producer, broker và topic; Kafka không có một giới hạn header riêng phổ quát.
- Kích thước header gồm tên, value và overhead mã hóa độ dài/số lượng; chuỗi phải được đo theo byte sau encoding.
- Header lớn làm tăng storage, replication traffic, consumer fetch, CPU, allocation và chi phí telemetry.
- Compression có thể giảm byte lưu/truyền nhưng không loại bỏ chi phí serialize, giải nén và xử lý header.
- Dùng header cho correlation ID, trace context, event type và schema version; tránh token, secret, stack trace và payload lớn.
- Đặt ngân sách header ở ứng dụng, đo kích thước thực tế và theo dõi record size thay vì dựa vào một giới hạn header mặc định.
- Phân biệt custom header với metadata Kafka như topic, partition, offset và timestamp.

Thiết kế header nhỏ và có hợp đồng rõ giúp các ứng dụng Spring Kafka truyền metadata cần thiết mà vẫn kiểm soát được kích thước record, chi phí lưu trữ, network và xử lý ở toàn bộ consumer group.
