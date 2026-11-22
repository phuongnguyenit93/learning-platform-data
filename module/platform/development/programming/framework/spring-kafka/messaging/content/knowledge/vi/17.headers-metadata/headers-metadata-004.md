# Mapping header kiểu byte[] trong Spring Kafka

Kafka header luôn có cấu trúc đơn giản: một tên header dạng `String` và một giá trị dạng `byte[]`. Kafka không tự hiểu giá trị đó là UTF-8, số nguyên, JSON hay object Java. Producer và consumer phải thống nhất cách mã hóa và giải mã.

Trong Spring Kafka, `KafkaHeaderMapper` ánh xạ giữa Kafka `Headers` và Spring `MessageHeaders`. Nếu cần giữ header ở dạng byte thô, `SimpleKafkaHeaderMapper` là lựa chọn phù hợp. Mapper này gửi các header `byte[]` trực tiếp và đưa header nhận được vào Spring Message dưới dạng byte array; có thể cấu hình thêm những tên header cần chuyển qua lại giữa `String` và `byte[]`.

## 1. Cấu trúc Kafka Header

Kafka định nghĩa header bằng interface có hai phương thức:

```java
public interface Header {
    String key();
    byte[] value();
}
```

`key()` là tên header; `value()` là mảng byte. Ví dụ một record có thể mang:

```text
correlation-id -> [byte values of "corr-81a2"]
schema-version -> [byte values of "2"]
signature      -> [binary bytes]
```

Kafka chỉ lưu các byte. Khi đọc `correlation-id`, consumer phải biết producer dùng UTF-8 để chuyển chuỗi thành byte. Với `signature`, consumer cần biết thuật toán và định dạng binary đã thống nhất.

Kafka header có các đặc điểm quan trọng:

- Tên header là chuỗi; giá trị là `byte[]` hoặc có thể là `null` theo API record.
- Một record có thể chứa nhiều header với cùng tên.
- Thứ tự header được giữ trong collection `Headers`.
- Kafka không tự deserialize header bằng `value-deserializer` của record.
- Header không thay thế key và không quyết định partition routing.

## 2. Vì sao cần mapping byte[]?

Header thường mang metadata nhỏ để trace hoặc điều khiển luồng xử lý, ví dụ:

| Header | Định dạng gợi ý | Mục đích |
|---|---|---|
| `correlation-id` | UTF-8 | Liên kết log và trace giữa các service |
| `event-id` | UTF-8 | Định danh event để deduplicate |
| `schema-version` | UTF-8 hoặc số binary theo contract | Xác định version schema |
| `content-type` | UTF-8 | Mô tả định dạng payload |
| `signature` | Binary | Chữ ký hoặc checksum theo giao thức đã thống nhất |
| `traceparent` | UTF-8 | Truyền trace context theo chuẩn tracing |

Giữ header ở dạng byte giúp các ứng dụng Java, Go, Python hoặc .NET trao đổi metadata mà không phụ thuộc vào kiểu Java cụ thể hay định dạng JSON nội bộ của Spring.

Ví dụ, một consumer Go có thể đọc `correlation-id` dưới dạng byte và giải mã UTF-8. Nó không cần hiểu `spring_json_header_types` hay tên class Java được nhúng trong metadata của Spring.

## 3. Ghi header byte[] trực tiếp bằng Kafka API

Khi tạo `ProducerRecord`, có thể thêm header trực tiếp qua `headers().add(...)`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders.created.v1", "order-42", event);

record.headers().add(
        new RecordHeader(
                "correlation-id",
                "corr-81a2".getBytes(StandardCharsets.UTF_8)));

record.headers().add(
        new RecordHeader(
                "schema-version",
                "2".getBytes(StandardCharsets.UTF_8)));

kafkaTemplate.send(record);
```

Key và value vẫn được serializer của Kafka xử lý. Các header đã là byte array nên không đi qua `value-serializer` hoặc `key-serializer`.

Nếu tạo record bằng `KafkaTemplate<String, byte[]>`, producer factory cần serializer phù hợp, ví dụ `StringSerializer` cho key và `ByteArraySerializer` cho value. Kiểu serializer của payload không thay đổi cách Kafka lưu header.

## 4. Đọc header byte[] trực tiếp từ ConsumerRecord

Consumer có thể lấy header bằng `lastHeader(name)`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

@KafkaListener(topics = "orders.created.v1")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    Header header = record.headers().lastHeader("correlation-id");

    String correlationId = header == null || header.value() == null
            ? null
            : new String(header.value(), StandardCharsets.UTF_8);

    // Xử lý event và correlation ID.
}
```

`lastHeader(name)` trả về header cuối cùng có tên tương ứng hoặc `null` nếu không có. Khi contract cho phép nhiều header cùng tên, dùng `headers(name)` để đọc tất cả thay vì chỉ lấy giá trị cuối.

Không dùng `new String(bytes)` mà bỏ qua charset. Kết quả khi đó phụ thuộc charset mặc định của máy chạy ứng dụng. Với metadata văn bản, hãy thống nhất UTF-8 và chỉ rõ `StandardCharsets.UTF_8` ở cả hai phía.

## 5. Chuyển đổi số và dữ liệu binary

Không phải header nào cũng là chuỗi. Nếu cần truyền một số `long`, có thể dùng định dạng binary cố định:

```java
import java.nio.ByteBuffer;

long createdAtEpochMillis = 1_790_000_000_000L;
byte[] timestampBytes = ByteBuffer.allocate(Long.BYTES)
        .putLong(createdAtEpochMillis)
        .array();

record.headers().add(new RecordHeader("created-at", timestampBytes));
```

Consumer đọc theo đúng định dạng đã thống nhất:

```java
Header header = record.headers().lastHeader("created-at");
if (header != null && header.value() != null
        && header.value().length == Long.BYTES) {
    long createdAt = ByteBuffer.wrap(header.value()).getLong();
}
```

`ByteBuffer` mặc định dùng big-endian. Nếu giao thức yêu cầu byte order khác, producer và consumer phải đặt cùng byte order. Luôn kiểm tra độ dài trước khi đọc để tránh `BufferUnderflowException` hoặc diễn giải dữ liệu sai.

Với UUID, có thể thống nhất biểu diễn UTF-8 dạng chuỗi hoặc 16 byte binary. Với chữ ký/checksum, giữ nguyên byte từ thư viện mật mã và không chuyển thành chuỗi nếu không có quy định encoding rõ ràng.

## 6. SimpleKafkaHeaderMapper

`SimpleKafkaHeaderMapper` là mapper dành cho trường hợp muốn ánh xạ header đơn giản, không cần JSON encode kiểu Java. Hành vi cơ bản:

- Outbound: chỉ các header có giá trị `byte[]` được map trực tiếp sang Kafka header.
- Inbound: Kafka header được map nguyên dạng thành `byte[]` trong Spring Message.
- Có thể cấu hình một số header để chuyển `String` sang byte khi gửi và byte sang `String` khi nhận.
- Các header Spring đặc biệt biểu diễn thuộc tính của `ProducerRecord`/`ConsumerRecord` thường không được gửi như custom Kafka header.

Ví dụ cấu hình converter dùng mapper byte thô:

```java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;

SimpleKafkaHeaderMapper headerMapper = new SimpleKafkaHeaderMapper();
MessagingMessageConverter converter = new MessagingMessageConverter();
converter.setHeaderMapper(headerMapper);
```

Có thể gắn converter này vào listener container factory:

```java
factory.setRecordMessageConverter(converter);
```

Hoặc vào `KafkaTemplate`:

```java
kafkaTemplate.setMessageConverter(converter);
```

Nhờ đó, listener có thể nhận `Message<?>` và truy cập custom header dưới dạng byte array. Khi cần dùng trực tiếp `ConsumerRecord.headers()`, có thể nhận `ConsumerRecord` mà không cần message mapper.

## 7. Đọc byte[] header qua Spring Message

Khi listener nhận `Message<OrderCreated>` và dùng `SimpleKafkaHeaderMapper`, custom header thường có kiểu `byte[]`:

```java
@KafkaListener(
        topics = "orders.created.v1",
        groupId = "order-projection",
        containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(Message<OrderCreated> message) {
    byte[] rawCorrelationId = message.getHeaders()
            .get("correlation-id", byte[].class);

    String correlationId = rawCorrelationId == null
            ? null
            : new String(rawCorrelationId, StandardCharsets.UTF_8);

    OrderCreated event = message.getPayload();
    // Xử lý event.
}
```

Nếu header không tồn tại, `get(...)` trả về `null`. Nếu header có thể được gửi bởi producer không tuân thủ contract, cần kiểm tra kiểu và độ dài trước khi decode.

Một cách khác là nhận header trực tiếp bằng `@Header`:

```java
@KafkaListener(topics = "orders.created.v1")
public void onOrder(
        @Payload OrderCreated event,
        @Header(name = "correlation-id", required = false) byte[] correlationBytes) {

    String correlationId = correlationBytes == null
            ? null
            : new String(correlationBytes, StandardCharsets.UTF_8);
}
```

Đặt `required = false` nếu header là tùy chọn. Nếu header bắt buộc theo contract, có thể để bắt buộc và xử lý lỗi thiếu header bằng validation/error handling thích hợp.

## 8. Chuyển một số header byte[] thành String có chọn lọc

Nếu muốn hầu hết header vẫn là `byte[]` nhưng một số header văn bản được chuyển thành `String`, cấu hình `rawMappedHeaders` trên `AbstractKafkaHeaderMapper`:

```java
SimpleKafkaHeaderMapper mapper = new SimpleKafkaHeaderMapper();
mapper.setRawMappedHeaders(Map.of(
        "correlation-id", true,
        "event-id", true,
        "signature", false
));
```

Ý nghĩa:

| Header | Boolean | Outbound từ Spring Message | Inbound vào Spring Message |
|---|---:|---|---|
| `correlation-id` | `true` | String được mã hóa thành byte theo charset mapper | byte được giải mã thành String |
| `event-id` | `true` | String được mã hóa thành byte theo charset mapper | byte được giải mã thành String |
| `signature` | `false` | String nếu có vẫn được ghi thành byte thô; byte[] được giữ nguyên | Giá trị được giữ dưới dạng byte[] |
| Header không nằm trong map | Không cấu hình | byte[] được map trực tiếp; String không tự động thành raw header | Giá trị được map nguyên dạng byte[] |

`true` không có nghĩa Kafka lưu String. Kafka vẫn lưu byte array; boolean chỉ hướng dẫn mapper chuyển byte thành String khi nhận. `false` giữ giá trị nhận ở dạng byte thô.

Charset mặc định của mapper là UTF-8. Nếu contract dùng charset khác, có thể cấu hình charset trên mapper, nhưng producer và consumer phải dùng cùng charset.

## 9. Dùng mapAllStringsOut khi cần gửi mọi String header dạng raw bytes

`setMapAllStringsOut(true)` yêu cầu mapper chuyển tất cả String header outbound thành byte array theo charset cấu hình. Cách này có thể phù hợp khi toàn bộ header văn bản cần trao đổi với hệ thống ngoài Spring.

```java
SimpleKafkaHeaderMapper mapper = new SimpleKafkaHeaderMapper();
mapper.setMapAllStringsOut(true);
```

Tuy nhiên, cấu hình này có phạm vi rộng hơn `rawMappedHeaders`. Nếu một số header cần được giữ ở kiểu khác hoặc không nên xuất hiện trên wire, hãy dùng mapping theo tên và pattern cụ thể. Không map tùy tiện các header nội bộ của Spring như `id` và `timestamp` thành custom Kafka headers.

Với giao thức liên dịch vụ, allowlist theo tên header thường dễ review và ổn định hơn việc gửi mọi String header của Spring Message.

## 10. So sánh SimpleKafkaHeaderMapper và JSON header mapper

Spring Kafka có hai hướng mapping chính:

| Tiêu chí | `SimpleKafkaHeaderMapper` | JSON header mapper |
|---|---|---|
| Giá trị outbound | Chủ yếu map byte[] trực tiếp; có tùy chọn String-to-byte | JSON encode các kiểu header phong phú |
| Giá trị inbound | Mặc định giữ byte[]; có thể decode một số header thành String | Dùng metadata type để chuyển header về kiểu tương ứng |
| Phụ thuộc Jackson | Không cần cho raw mapping | Cần Jackson cho JSON mapping |
| Tương thích hệ thống đa ngôn ngữ | Tốt khi contract byte/encoding rõ ràng | Consumer ngoài Spring phải hiểu định dạng JSON header nếu muốn phục hồi kiểu |
| Trường hợp phù hợp | Trace ID, correlation ID, signature, mã version dạng byte | Header object có kiểu phong phú giữa các ứng dụng Spring |

Trong các phiên bản Spring Kafka cũ, JSON header mapper thường có tên `DefaultKafkaHeaderMapper`. Tài liệu/API phiên bản mới có thể dùng tên `JsonKafkaHeaderMapper`. Hãy kiểm tra class có trong dependency của dự án trước khi sao chép code.

JSON header mapper có thể thêm header metadata như `spring_json_header_types` để mô tả kiểu Java. Nếu mục tiêu là wire contract chỉ gồm tên header và byte[] độc lập ngôn ngữ, `SimpleKafkaHeaderMapper` thường phù hợp hơn.

## 11. Header nào được map và header nào là metadata record?

Không phải mọi Spring Message header đều được ghi thành Kafka header. Một số `KafkaHeaders` biểu diễn thuộc tính của record, ví dụ:

| Spring header | Ý nghĩa khi gửi |
|---|---|
| `KafkaHeaders.TOPIC` | Topic đích của record |
| `KafkaHeaders.MESSAGE_KEY` | Key của record |
| `KafkaHeaders.PARTITION` | Partition được chỉ định |
| `KafkaHeaders.TIMESTAMP` | Timestamp được chỉ định |
| `KafkaHeaders.RECEIVED_TOPIC` | Metadata topic của record đã nhận |
| `KafkaHeaders.OFFSET` | Offset của record đã nhận |

Các header như topic, key, partition và timestamp được converter dùng để tạo `ProducerRecord`; chúng không nhất thiết trở thành custom Kafka headers. Các header ứng dụng như `correlation-id`, `event-id` và `schema-version` mới là metadata thường được map qua `KafkaHeaderMapper`.

Đừng dùng tên custom header trùng với tên header dành riêng của Spring Kafka. Hãy chọn namespace rõ ràng cho metadata ứng dụng, ví dụ `x-correlation-id` hoặc `event-source`.

## 12. Header trùng tên và thứ tự header

Kafka `Headers` cho phép nhiều header có cùng tên. Ví dụ:

```java
record.headers().add("tag", "priority".getBytes(StandardCharsets.UTF_8));
record.headers().add("tag", "retryable".getBytes(StandardCharsets.UTF_8));
```

Đọc tất cả giá trị:

```java
for (Header header : record.headers().headers("tag")) {
    byte[] value = header.value();
    // Xử lý từng giá trị theo thứ tự.
}
```

`lastHeader("tag")` chỉ trả về lần xuất hiện cuối cùng. Nếu contract cần giữ mọi giá trị, phải dùng API lấy tất cả header và không được chuyển chúng vào một map đơn giá trị mà không có quy tắc.

Với Spring Message mapping, hành vi multi-value phụ thuộc phiên bản và mapper. Tài liệu Spring Kafka 4.x hỗ trợ khai báo pattern cho header nhiều giá trị trên JSON mapper; nếu cần bảo toàn duplicate headers, kiểm tra khả năng của phiên bản đang dùng hoặc nhận `ConsumerRecord` để đọc `Headers` gốc. `SimpleKafkaHeaderMapper` không phải lựa chọn để tự động chuyển một collection byte[] thành nhiều Kafka headers.

## 13. Thiết kế contract header giữa các service

Header là một phần của giao thức trao đổi event. Nên lập bảng contract rõ ràng:

| Tên header | Bắt buộc | Encoding | Ví dụ |
|---|---|---|---|
| `correlation-id` | Có | UTF-8 | `corr-81a2` |
| `event-id` | Có | UTF-8 | `evt-1001` |
| `schema-version` | Có | UTF-8 decimal | `2` |
| `traceparent` | Theo tracing policy | UTF-8 | W3C Trace Context |
| `signature` | Theo security policy | Binary | Bytes theo thuật toán đã chọn |

Với mỗi header, thống nhất:

- Tên chính xác, gồm quy ước chữ thường/gạch nối.
- Encoding và byte order.
- Có bắt buộc hay không.
- Độ dài tối đa và cách xử lý giá trị rỗng.
- Có cho phép lặp nhiều header cùng tên không.
- Quy tắc versioning khi thay đổi định dạng.
- Quy tắc tương thích khi producer và consumer được triển khai lệch thời điểm.

Không truyền một object Java tùy ý bằng cách serialize `toString()` rồi mong service khác hiểu được. Nếu header cần cấu trúc phức tạp, hãy định nghĩa một binary/JSON schema nhỏ có version, hoặc chuyển dữ liệu đó vào payload event.

## 14. Kiểm tra và validate header đầu vào

Consumer không nên tin rằng mọi header đều tồn tại hoặc đúng encoding. Ví dụ:

```java
private String requiredUtf8Header(Headers headers, String name) {
    Header header = headers.lastHeader(name);
    if (header == null || header.value() == null || header.value().length == 0) {
        throw new IllegalArgumentException("Missing required header: " + name);
    }

    return StandardCharsets.UTF_8.decode(
            ByteBuffer.wrap(header.value())).toString();
}
```

Đoạn code minh họa kiểm tra header bắt buộc và giải mã UTF-8. Với dữ liệu cần xác thực nghiêm ngặt, dùng `CharsetDecoder` được cấu hình `CodingErrorAction.REPORT` để từ chối chuỗi byte không hợp lệ, thay vì chấp nhận ký tự thay thế.

Các kiểm tra nên có:

- Header bắt buộc có tồn tại không.
- Giá trị có null hoặc rỗng không.
- Byte length có vượt giới hạn contract không.
- Encoding có hợp lệ không.
- UUID, số, timestamp hoặc signature có đúng định dạng không.
- Header trùng tên có được phép không.
- Header có nằm trong allowlist mà ứng dụng sử dụng không.

Header thiếu hoặc sai định dạng nên được xử lý như lỗi dữ liệu đầu vào theo chính sách retry/DLT của consumer; không tự tạo giá trị mặc định có thể làm sai correlation hoặc security context.

## 15. Giới hạn kích thước và bảo mật

Kafka headers được truyền cùng record và làm tăng kích thước dữ liệu trên wire. Không dùng header để mang payload lớn, stack trace dài, object JSON lớn hoặc dữ liệu nhị phân không có giới hạn.

Các nguyên tắc vận hành:

- Giữ header nhỏ và chỉ chứa metadata cần thiết.
- Không đưa password, bearer token, private key hoặc dữ liệu nhạy cảm vào header.
- Không ghi toàn bộ byte array vào log; chỉ ghi tên header, độ dài hoặc giá trị đã mask khi cần.
- Kiểm tra byte length trước khi decode hoặc parse.
- Dùng TLS/SASL và ACL Kafka để bảo vệ đường truyền và quyền truy cập topic.
- Nếu header là chữ ký, xác minh chữ ký trên đúng byte sequence theo contract; không decode rồi encode lại trước khi verify.

Kafka header không phải ranh giới bảo mật độc lập. Bất kỳ producer nào có quyền ghi topic đều có thể tạo header theo ý mình; consumer phải validate và xác thực nội dung quan trọng.

## 16. Kiểm thử mapping byte[] hai chiều

Nên kiểm thử mapper trực tiếp và kiểm thử tích hợp qua broker.

Ví dụ kiểm tra `SimpleKafkaHeaderMapper` giữ raw bytes:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.messaging.MessageHeaders;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void shouldMapRawBytesWithoutChangingThem() {
    SimpleKafkaHeaderMapper mapper = new SimpleKafkaHeaderMapper();

    byte[] expected = new byte[] {0x01, 0x02, 0x7F};
    MessageHeaders messageHeaders = new MessageHeaders(
            Map.of("signature", expected));

    Headers kafkaHeaders = new RecordHeaders();
    mapper.fromHeaders(messageHeaders, kafkaHeaders);

    Header mapped = kafkaHeaders.lastHeader("signature");
    assertThat(mapped.value()).containsExactly(0x01, 0x02, 0x7F);

    Map<String, Object> inbound = new HashMap<>();
    mapper.toHeaders(kafkaHeaders, inbound);

    assertThat((byte[]) inbound.get("signature"))
            .containsExactly(0x01, 0x02, 0x7F);
}
```

Khi kiểm tra `byte[]`, nên so sánh nội dung mảng bằng `containsExactly` hoặc `Arrays.equals`; không dùng `==` để so sánh hai object array vì phép đó so sánh tham chiếu.

Nếu có cấu hình `rawMappedHeaders`, bổ sung test xác minh:

- Header có giá trị `true` chuyển String outbound thành byte và byte inbound thành String.
- Header có giá trị `false` giữ byte inbound ở dạng `byte[]`.
- Header không nằm trong map vẫn giữ hành vi raw mặc định.
- Charset được cấu hình giống nhau ở hai phía.
- Header duplicate được giữ hoặc loại theo quy tắc đã thống nhất.

Integration test với `@EmbeddedKafka` hoặc Testcontainers nên gửi record có custom headers, đọc lại record và xác minh byte array, tên header, thứ tự và duplicate semantics. Unit test mapper không chứng minh broker/client đang dùng đúng cấu hình serializer và converter.

## 17. Lỗi thường gặp

**Đọc byte[] như String bằng charset mặc định:** dùng `StandardCharsets.UTF_8` hoặc charset đã thống nhất.

**Producer gửi String nhưng SimpleKafkaHeaderMapper không map:** mapper outbound chỉ map `byte[]` theo mặc định. Gửi byte array hoặc cấu hình `rawMappedHeaders`/`mapAllStringsOut`.

**Consumer mong nhận String nhưng nhận byte[]:** thêm tên header vào `rawMappedHeaders` với giá trị `true`, hoặc tự decode từ byte[] ở listener.

**Dùng Default/JSON mapper nhưng consumer ngoài Spring không hiểu header:** chọn raw byte mapper hoặc cấu hình raw mapping cho header liên dịch vụ.

**Nhầm header với key/value serializer:** header value phải được tạo thành byte[] riêng; Kafka value serializer không tự chuyển đổi custom headers.

**Chỉ đọc lastHeader trong khi producer gửi duplicate:** dùng `headers(name)` và định nghĩa quy tắc nhiều giá trị.

**Header không xuất hiện ở broker:** kiểm tra outbound pattern của mapper, kiểu dữ liệu header và tên header có thuộc metadata dành riêng của Spring không.

**Đưa object lớn hoặc secret vào header:** chuyển dữ liệu lớn vào payload, bỏ secret và giới hạn kích thước metadata.

**Thay đổi encoding mà không version contract:** consumer giải mã sai dữ liệu. Giữ encoding ổn định hoặc phát hành schema/header version mới.

## 18. Checklist production

- Mỗi header có tên, kiểu byte, encoding và ngữ nghĩa được ghi trong contract.
- Header văn bản dùng UTF-8 rõ ràng; dữ liệu binary có định dạng và byte order xác định.
- Producer tạo byte array đúng contract trước khi thêm Kafka header.
- Consumer kiểm tra header tồn tại, độ dài và encoding trước khi sử dụng.
- Chọn `SimpleKafkaHeaderMapper` khi muốn mapping raw byte; chỉ bật String conversion cho header cần thiết.
- Không bật map tất cả String headers nếu chưa đánh giá phạm vi mapping.
- Dùng JSON header mapper khi cần kiểu header phong phú và các bên hiểu format đó.
- Xác định duplicate header có được phép và cách giữ nhiều giá trị.
- Không dùng header cho payload lớn, secret hoặc dữ liệu cá nhân không cần thiết.
- Có unit test mapper và integration test qua Kafka broker.
- Theo dõi lỗi thiếu header/encoding sai mà không log nội dung nhạy cảm.

Mapping header kiểu `byte[]` giúp Kafka metadata giữ một contract đơn giản và độc lập ngôn ngữ. Dùng `SimpleKafkaHeaderMapper` cho raw bytes, cấu hình chuyển String có chọn lọc và thống nhất encoding giữa producer/consumer. Khi contract nêu rõ tên, định dạng, duplicate semantics và giới hạn kích thước, header sẽ hỗ trợ trace và metadata mà không tạo phụ thuộc vào kiểu Java nội bộ.
