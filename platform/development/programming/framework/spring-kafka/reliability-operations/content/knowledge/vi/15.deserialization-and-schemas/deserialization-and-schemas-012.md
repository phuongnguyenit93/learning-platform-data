# Kiểm tra dữ liệu trước khi deserialize

Trong hệ thống Kafka, một consumer có thể nhận record chứa bytes không hợp lệ: payload bị cắt cụt, định dạng không khớp với serializer của producer, schema ID sai, dữ liệu lớn bất thường, hoặc header mô tả format không tương ứng với payload. Nếu đưa trực tiếp những bytes này vào JSON/Avro/Protobuf deserializer rồi chỉ xử lý lỗi ở listener, ứng dụng có thể gặp exception trước khi phương thức `@KafkaListener` được gọi. Vòng retry lặp lại cùng payload lỗi sẽ không sửa được dữ liệu và có thể giữ consumer ở một offset, làm consumer lag tăng.

**Kiểm tra dữ liệu trước khi deserialize** (pre-deserialization validation, hay wire-level preflight) là kiểm tra những thuộc tính có thể xác định từ **bytes và Kafka headers**, trước khi chuyển bytes thành domain object. Mục tiêu không phải xác thực toàn bộ nghiệp vụ; mục tiêu là phát hiện sớm record không phù hợp hợp đồng định dạng, giới hạn tài nguyên và tạo đường xử lý lỗi rõ ràng.

Bài học này trình bày vị trí đặt kiểm tra, sự khác nhau giữa validation trước/sau deserialize, cách sử dụng `ByteArrayDeserializer` và custom `Deserializer`, tích hợp `ErrorHandlingDeserializer`, routing sang dead-letter topic (DLT), lưu raw payload an toàn và các runbook vận hành.

## 1. Deserialize diễn ra ở đâu trong pipeline?

Kafka lưu key và value dưới dạng byte array. Khi consumer gọi `poll()`, Kafka client dùng `key.deserializer` và `value.deserializer` để chuyển bytes thành kiểu Java. Spring Kafka listener container sau đó nhận `ConsumerRecord<K,V>`, áp dụng các thành phần container, chuyển đổi message nếu cần rồi mới gọi listener.

~~~text
Kafka broker
    |
    | bytes của key, value + headers
    v
KafkaConsumer.poll()
    |
    +--> key deserializer
    |
    +--> value deserializer
              |
              v
       ConsumerRecord<K,V>
              |
              v
       Spring Kafka container
              |
       message conversion / adapter
              |
              v
          @KafkaListener
              |
              v
       Validation nghiệp vụ
              |
              v
       Side effects + ack/commit
~~~

Nếu `JsonDeserializer` hoặc Avro deserializer ném exception trong `poll()`, listener thường chưa được gọi. Một `try/catch` đặt trong thân `@KafkaListener` sẽ không bắt được lỗi đó.

Điểm này quyết định nên đặt kiểm tra ở tầng nào:

| Vị trí | Có bytes gốc? | Có domain object? | Ví dụ kiểm tra |
|---|---|---|---|
| Producer trước publish | Có thể có | Có | Chặn event không đúng contract trước khi gửi |
| Trong custom Kafka `Deserializer` | Có | Chưa | Kiểm tra kích thước, framing, header, magic byte, schema ID |
| Listener nhận `byte[]` nhờ `ByteArrayDeserializer` | Có | Chưa, nếu ứng dụng tự decode | Kiểm tra bytes rồi gọi parser ở listener/service |
| Sau Kafka deserializer nhưng trước business handler | Tùy pipeline | Có | Bean Validation, enum, required field, object schema |
| Trong service nghiệp vụ | Không nhất thiết | Có | Trạng thái đơn hàng, chính sách, idempotency |

**Record interceptor, record filter và `@KafkaListener` thông thường không phải điểm “trước Kafka deserialize”** nếu value deserializer đã chuyển bytes thành object. Muốn xem raw bytes trước bước đó, cần chọn deserializer phù hợp hoặc tự thiết kế lớp decode.

## 2. Vì sao kiểm tra trước khi deserialize?

### 2.1. Phát hiện format sai trước parser

Một topic dự kiến nhận JSON object nhưng lại có Avro binary, plain text hoặc JSON array. Có thể phát hiện sự khác biệt ở wire framing hoặc một số dấu hiệu rất cơ bản trước khi Jackson cố gắng tạo object.

Tuy nhiên, kiểm tra “byte đầu tiên là ký tự `{`” không phải là JSON validator đầy đủ. Payload hợp lệ có thể có khoảng trắng đầu, BOM theo một số giao thức, hoặc format khác. Preflight phải dựa trên hợp đồng thật của topic, không dựa vào heuristic tùy tiện.

### 2.2. Giới hạn tài nguyên

Một record kích thước lớn bất thường có thể gây:

- Áp lực heap do tạo chuỗi hoặc object graph lớn.
- CPU tăng vì parse JSON sâu hoặc nhiều phần tử.
- Latency cao, ảnh hưởng `max.poll.interval.ms`.
- Áp lực lên database và downstream nếu object được dùng để tạo nhiều thao tác.

Kiểm tra `data.length` trước khi tạo object là biện pháp đơn giản để hạn chế payload vượt ngân sách của ứng dụng. Nhưng nó không thay thế giới hạn message ở broker/producer, fetch configuration hoặc giới hạn độ sâu của JSON parser.

### 2.3. Phân loại lỗi để tránh retry vô nghĩa

Payload sai schema, magic byte hoặc checksum thường không thể tự sửa bằng cách retry cùng bytes. Lỗi network khi gọi Schema Registry lại có thể chỉ là tạm thời. Cần tách **lỗi dữ liệu vĩnh viễn** khỏi **lỗi hạ tầng tạm thời** để tránh retry storm và không bỏ qua record đáng lẽ có thể xử lý sau khi dependency phục hồi.

### 2.4. Giữ bằng chứng cho recovery

Khi deserializer không thể tạo domain object, recovery cần một cách lưu **raw bytes, key, headers và source topic/partition/offset**. Nếu ứng dụng chỉ log chuỗi exception rồi commit qua record, payload lỗi có thể không còn một đường điều tra thực tế.

## 3. Kiểm tra được gì từ raw bytes?

Các bước preflight thường rẻ, có giới hạn thời gian và không cần parse toàn bộ object:

| Nhóm | Ví dụ | Lưu ý |
|---|---|---|
| Null/tombstone | Value bằng `null` | Có thể hợp lệ với compacted topic; không tự coi là lỗi |
| Kích thước | Rỗng, vượt giới hạn ứng dụng | Kiểm tra trước khi cấp phát object |
| Framing | Magic byte, version byte, length prefix | Phải đúng giao thức thực tế |
| Header contract | Content type, event type, encoding, schema version | Header có thể thiếu hoặc sai; không được tin mù quáng |
| Encoding | UTF-8 hợp lệ, byte order, compression | Chỉ kiểm tra theo content type đã thỏa thuận |
| Integrity | CRC/checksum/signature ở payload envelope nếu có | Kafka CRC không thay thế checksum cấp ứng dụng |
| Schema metadata | Schema ID, subject/version của format có registry | Kiểm tra ID hợp lệ về cấu trúc trước khi lookup |
| Resource budget | Số byte tối đa, giới hạn depth của parser | Một số giới hạn chỉ áp dụng được trong khi parse |

### 3.1. Những điều chưa thể biết trước khi deserialize

Không thể khẳng định các trường nghiệp vụ như `orderId` tồn tại, số tiền dương hoặc enum hợp lệ chỉ bằng cách nhìn vài bytes đầu. Để kiểm tra đầy đủ cần parse/schema validation hoặc ít nhất giải mã cấu trúc. Validation trước deserialize là **lớp phòng vệ đầu tiên**, không phải thay thế validation sau decode.

Một hệ thống đáng tin cậy thường có nhiều tầng:

~~~text
Raw bytes
  |
  +-- Preflight: size, framing, metadata, integrity
  |
  +-- Deserialize: tạo object hoặc parse tree
  |
  +-- Schema validation: type, required fields, compatibility
  |
  +-- Business validation: trạng thái, quota, luật nghiệp vụ
  |
  +-- Persistence/idempotency
~~~

## 4. Hai chiến lược triển khai thường dùng

### Chiến lược A: Đọc byte[] rồi chủ động deserialize

Cấu hình Kafka consumer dùng `ByteArrayDeserializer` cho value; listener nhận `byte[]` và kiểm tra trước khi gọi JSON/Avro parser. Đây là cách dễ hiểu, dễ đo metrics và thấy rõ ranh giới preflight.

Ưu điểm:

- Listener chắc chắn thấy raw bytes trước khi application parser chạy.
- Có thể kiểm tra cả record headers cùng payload.
- Exception từ parser xuất hiện trong đường listener, nên cơ chế listener error handling có thể phân loại.
- Dễ ghi metadata nguồn, DLT và lưu bằng chứng.

Đánh đổi:

- Listener/service phải chịu trách nhiệm decode và validate đúng cách.
- Không được parse cùng payload lặp lại nhiều lần không cần thiết.
- Không thể dựa vào việc container tự tạo domain object ở thời điểm Kafka deserializer chạy.

### Chiến lược B: Custom Kafka Deserializer bọc bước preflight

Viết một `Deserializer<T>` tự kiểm tra raw bytes rồi gọi decoder/delegate. Cách này giữ API của listener nhận domain object, nhưng exception có thể phát sinh **bên trong KafkaConsumer.poll()**. Khi đó, nên tích hợp `ErrorHandlingDeserializer` và recovery thích hợp để tránh lỗi deserialize chặn consumer mà không có khả năng đưa record sang DLT.

Ưu điểm:

- Tập trung quy tắc wire-level ở một chỗ.
- Consumer có thể tiếp tục nhận typed object.
- Phù hợp để kiểm tra magic byte, framing và metadata của một định dạng chuẩn.

Đánh đổi:

- Cần quản lý vòng đời deserializer, thread-safety và cấu hình delegate.
- Error handling ở tầng deserialize phức tạp hơn.
- Payload không decode được phải được giữ cho recovery.

**Chọn một chiến lược chính cho từng consumer path** để tránh duplicate decode và tránh mỗi lớp áp dụng một chính sách lỗi khác nhau.

## 5. Ví dụ: ByteArrayDeserializer và kiểm tra trước JSON parser

Giả sử topic `orders.events` có hợp đồng: value là JSON object UTF-8, tối đa 256 KiB; record rỗng không hợp lệ, nhưng tombstone phải được xét theo chính sách topic.

### 5.1. Cấu hình Spring Boot

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-consumer
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.ByteArrayDeserializer
    listener:
      ack-mode: record
~~~

Với cấu hình này, consumer không dùng `JsonDeserializer` ở tầng Kafka client cho value. Listener sẽ nhận bytes thô.

### 5.2. Một preflight validator nhỏ

~~~java
public final class OrderWirePreflight {
    private static final int MAX_BYTES = 256 * 1024;

    private OrderWirePreflight() {}

    public static void check(byte[] bytes) {
        if (bytes == null) {
            throw new InvalidWireRecordException(
                    "Tombstone is not allowed on orders.events");
        }
        if (bytes.length == 0) {
            throw new InvalidWireRecordException("Empty payload");
        }
        if (bytes.length > MAX_BYTES) {
            throw new InvalidWireRecordException(
                    "Payload exceeds configured size limit");
        }

        int pos = 0;
        while (pos < bytes.length && isJsonWhitespace(bytes[pos])) {
            pos++;
        }
        if (pos == bytes.length || bytes[pos] != (byte) '{') {
            throw new InvalidWireRecordException(
                    "Expected a JSON object envelope");
        }
    }

    private static boolean isJsonWhitespace(byte b) {
        return b == ' ' || b == '\t'
                || b == '\r' || b == '\n';
    }
}
~~~

Exception dành riêng cho wire validation:

~~~java
public class InvalidWireRecordException extends RuntimeException {
    public InvalidWireRecordException(String message) {
        super(message);
    }
}
~~~

Kiểm tra trên **không xác nhận JSON có cấu trúc đúng**. Nó chỉ loại record rỗng/quá lớn và record không có tiền tố JSON object theo hợp đồng của ví dụ. Nếu hệ thống chấp nhận UTF-8 BOM hoặc các envelope hợp lệ khác, cần định nghĩa và xử lý trước khi áp dụng quy tắc ký tự đầu.

### 5.3. Listener kiểm tra rồi mới deserialize

~~~java
@Component
public class OrderRawListener {
    private final ObjectMapper objectMapper;
    private final OrderService orderService;

    public OrderRawListener(
            ObjectMapper objectMapper, OrderService orderService) {
        this.objectMapper = objectMapper;
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.events",
            groupId = "orders-consumer")
    public void listen(ConsumerRecord<String, byte[]> record)
            throws JsonProcessingException {

        byte[] raw = record.value();
        OrderWirePreflight.check(raw);

        // Business object chỉ được tạo sau wire-level preflight.
        OrderEvent event =
                objectMapper.readValue(raw, OrderEvent.class);

        // Schema/bean/business validation tiếp tục ở đây.
        orderService.processIdempotently(event);
    }
}
~~~

Nếu `OrderWirePreflight.check` hoặc `objectMapper.readValue` ném exception, listener sẽ không hoàn tất bình thường. Container error handler có thể phân loại lỗi, retry hoặc publish DLT theo policy. Không `catch` exception rồi chỉ `log.warn` và trả về thành công: như vậy offset có thể tiến qua record chưa được phục hồi.

### 5.4. Phân loại lỗi dữ liệu là không retry

Ví dụ `DefaultErrorHandler` với recoverer:

~~~java
@Bean
DefaultErrorHandler errorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);
    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L));

    handler.addNotRetryableExceptions(
            InvalidWireRecordException.class,
            JsonProcessingException.class);
    return handler;
}
~~~

Điều quan trọng là serializer của DLT producer phải hỗ trợ **byte[]** nếu listener đang nhận value dạng bytes. Ví dụ ở đây giả định `KafkaTemplate<Object,Object>` và serialization/recoverer đã được cấu hình phù hợp; nếu không, lỗi publish DLT có thể khiến recovery thất bại. Cấu hình thực tế cần chọn `ByteArraySerializer` hoặc cơ chế serializer theo kiểu dữ liệu phù hợp.

`JsonProcessingException` là lớp checked exception do Jackson dùng; error handler nhận exception được wrap từ listener và classification cần được kiểm tra với cause chain của phiên bản triển khai. Nếu policy riêng yêu cầu phân biệt malformed JSON với lỗi hạ tầng, hãy bắt `JsonProcessingException` tại tầng decode và bọc trong một custom exception không retry, giữ nguyên cause.

## 6. Kiểm tra Kafka headers trước parser

Header có thể mô tả định dạng dữ liệu mà producer cam kết:

- `content-type`: ví dụ `application/json`.
- `event-type`: ví dụ `OrderCreated`.
- `schema-version`: phiên bản schema hoặc hợp đồng payload.
- `encoding`: ví dụ `utf-8`.
- `trace-id` hoặc `correlation-id`: phục vụ truy vết, không quyết định payload hợp lệ.

Ví dụ kiểm tra một header bắt buộc:

~~~java
private static void requireJsonContentType(Headers headers) {
    Header header = headers.lastHeader("content-type");
    if (header == null || header.value() == null) {
        throw new InvalidWireRecordException(
                "Missing content-type header");
    }

    String contentType = new String(
            header.value(), StandardCharsets.US_ASCII);

    if (!"application/json".equalsIgnoreCase(contentType)) {
        throw new InvalidWireRecordException(
                "Unsupported content type");
    }
}
~~~

Gọi `requireJsonContentType(record.headers())` trước `readValue` nếu hợp đồng **bắt buộc** header này. Nếu hệ thống hiện có producer legacy không gửi header, cần kế hoạch chuyển đổi; áp một quy tắc mới đột ngột có thể làm tất cả record cũ đi DLT.

### 6.1. Không tin header mù quáng

Headers do producer gửi và có thể bị sửa bởi middleware. `content-type: application/json` không chứng minh payload là JSON đúng chuẩn. Tương tự, `schema-version: 3` không đảm bảo nội dung thực sự tuân thủ version 3.

Hãy dùng header để chọn đúng codec và chính sách; parser/schema validator vẫn phải kiểm tra dữ liệu thật. Trong hệ thống có trust boundary, xem header là dữ liệu đầu vào không đáng tin cho đến khi được xác thực theo giao thức.

### 6.2. Kiểm tra số lượng và kích thước header

Một record có thể có nhiều header trùng tên hoặc header chứa bytes lớn. Nếu ứng dụng cho phép tùy ý truyền header vào log, map hoặc downstream, cần giới hạn và chỉ giữ những trường hợp lệ. Không sử dụng `toString()` trên toàn bộ headers để log ở mức INFO vì có thể lộ token, PII hoặc tạo log rất lớn.

## 7. Định dạng nhị phân và magic byte

Với Avro/Protobuf hoặc codec riêng, preflight thường kiểm tra cấu trúc envelope thay vì ký tự JSON. Ví dụ, **Confluent Schema Registry wire format** truyền thống thường đặt một magic byte tại vị trí đầu và schema ID ở bốn byte kế tiếp, rồi mới tới payload.

~~~text
Byte index:   0      1  2  3  4       5...
             +------+-----------+---------------+
             |magic | schema ID | binary payload|
             +------+-----------+---------------+
               1 B       4 B       variable
~~~

Đây là ví dụ **giao thức cụ thể**, không phải tiêu chuẩn cho mọi Avro/Protobuf/Kafka serializer. Một số serializer dùng format khác, có thêm message indexes hoặc prefix riêng. Chỉ áp dụng preflight tương ứng với serializer thực tế của producer.

### 7.1. Kiểm tra framing

~~~java
public static int readSchemaId(byte[] bytes) {
    if (bytes == null || bytes.length < 5) {
        throw new InvalidWireRecordException(
                "Not enough bytes for registry framing");
    }
    if (bytes[0] != 0) {
        throw new InvalidWireRecordException(
                "Unexpected magic byte");
    }
    int schemaId = ByteBuffer.wrap(bytes, 1, 4).getInt();
    if (schemaId <= 0) {
        throw new InvalidWireRecordException(
                "Invalid schema id");
    }
    return schemaId;
}
~~~

Đoạn ví dụ giả định magic byte = 0 và schema ID dương theo hợp đồng được triển khai. Phần kiểm tra chỉ đọc framing; nó **không chứng minh schema ID tồn tại trong registry hoặc binary payload tuân thủ schema đó**. Với các format có payload hợp lệ rỗng, không được áp đặt `length > 5` một cách tùy tiện.

### 7.2. Kiểm tra Schema Registry đúng cách

Sau preflight framing, codec có thể gọi Schema Registry để lấy schema theo ID. Cần tách các tình huống:

| Tình huống | Bản chất | Chính sách gợi ý |
|---|---|---|
| Magic byte sai | Payload sai format hoặc producer sai codec | Non-retryable, lưu raw bytes vào recovery |
| Envelope bị cắt cụt | Dữ liệu không đúng hợp đồng | Non-retryable, điều tra producer |
| Schema ID không tồn tại | Có thể là metadata/schema deployment lỗi | Cảnh báo và điều tra; retry có điều kiện nếu registry vừa thay đổi |
| Registry timeout/503 | Hạ tầng tạm thời không khả dụng | Retry hữu hạn với backoff |
| Binary không khớp schema | Dữ liệu/serializer sai | Non-retryable nếu retry cùng bytes không thể sửa |

Không gộp mọi exception có chữ “schema” thành non-retryable: một request lookup schema timeout khác hoàn toàn payload có schema ID sai. Nếu registry client có cache và retry riêng, phải tính tổng số lần gọi để tránh retry storm.

## 8. Custom Deserializer kiểm tra dữ liệu từ tầng Kafka

Khi muốn listener nhận `OrderEvent` nhưng vẫn kiểm tra raw bytes trước lúc Jackson deserialize, có thể dùng custom `Deserializer<OrderEvent>`.

Ví dụ dưới đây bao gồm cả overload không có headers:

~~~java
public class ValidatingOrderDeserializer
        implements Deserializer<OrderEvent> {

    private final ObjectMapper mapper = new ObjectMapper();

    @Override
    public OrderEvent deserialize(String topic, byte[] data) {
        return deserialize(topic, new RecordHeaders(), data);
    }

    @Override
    public OrderEvent deserialize(
            String topic, Headers headers, byte[] data) {
        if (data == null) {
            // Tombstone policy: minh họa cho phép null.
            return null;
        }

        try {
            OrderWirePreflight.check(data);
            return mapper.readValue(data, OrderEvent.class);
        }
        catch (Exception ex) {
            throw new SerializationException(
                    "Cannot deserialize order event from " + topic,
                    ex);
        }
    }
}
~~~

Ví dụ minh họa kỹ thuật. Trong production, deserializer cần quản lý cấu hình, giải phóng resource ở `close()` nếu có, và tuyệt đối không ghi raw payload hoặc thông tin nhạy cảm vào exception message. Nếu có codec được chia sẻ giữa nhiều thread, cần bảo đảm thread-safety của đối tượng dùng chung.

Ở ví dụ này, exception ném từ deserializer xuất hiện tại Kafka client polling layer. Nếu dùng deserializer trực tiếp mà không có error handling thích hợp, container có thể không nhận được record đã deserialize và không thể đưa raw bytes vào DLT một cách thuận tiện. Đó là lý do cần xem `ErrorHandlingDeserializer`.

## 9. ErrorHandlingDeserializer và đường recovery an toàn

`ErrorHandlingDeserializer` của Spring Kafka bọc một delegate deserializer. Khi delegate không deserialize được key/value, wrapper có thể đưa thông tin lỗi vào header tương ứng, cho phép Spring Kafka container/error handler xử lý thay vì chỉ để Kafka `poll()` liên tục thất bại ở cùng offset.

~~~text
Broker raw bytes
      |
      v
ErrorHandlingDeserializer
      |
      v
ValidatingOrderDeserializer (delegate)
      |
      +--> Preflight thành công --> parse --> OrderEvent
      |
      +--> Preflight/parse thất bại
                      |
                      v
             Deserialization error metadata
                      |
                      v
              Spring Kafka error handler
                      |
                      v
                Recovery / DLT
~~~

### 9.1. Cấu hình consumer

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-consumer
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": com.example.kafka.ValidatingOrderDeserializer
    listener:
      ack-mode: record
~~~

Đường dẫn `com.example.kafka.ValidatingOrderDeserializer` là ví dụ; thay bằng class thật. Cấu hình `ErrorHandlingDeserializer` có thêm cách khai báo cho key, delegate và tùy chọn fallback theo phiên bản Spring Kafka.

**Lưu ý:** nếu key cũng có khả năng sai định dạng, phải thiết kế error handling cho key. Một key deserializer ném exception trực tiếp cũng có thể làm consumer không thể tiến đến listener.

### 9.2. Không tự ack record deserialize lỗi

Record không decode được không nên được “xử lý thành công” chỉ vì wrapper đã bắt được exception. Container/error handler cần quyết định đưa nó sang DLT, retry có điều kiện hoặc dừng để điều tra.

Một số failure thuộc nhóm **không retry** theo mặc định của `DefaultErrorHandler`, trong đó có deserialization/conversion failure. Danh sách và cách xét cause thay đổi theo phiên bản; với custom `SerializationException` hoặc wrapper riêng, nên khai báo classification rõ ràng và kiểm thử.

### 9.3. Giữ raw payload cho DLT

Khi sử dụng ErrorHandlingDeserializer, Spring Kafka có hỗ trợ recovery cho record có lỗi deserialize và có thể chuyển bytes gốc vào DLT. Tuy nhiên, producer DLT phải có serializer hỗ trợ kiểu dữ liệu mà recoverer gửi:

- Record decode được có thể mang domain object.
- Record decode lỗi có thể cần lưu raw `byte[]`.
- Key cũng có thể là raw bytes nếu lỗi nằm ở key.

Không ép mọi DLT value qua `JsonSerializer<OrderEvent>` nếu record đã thất bại ở bước deserialize. Cần dùng serializer tương thích theo kiểu dữ liệu, ví dụ `DelegatingByTypeSerializer` hoặc một KafkaTemplate dành riêng cho raw bytes, tùy phiên bản và thiết kế.

Kiểm thử thực tế phải xác nhận record lỗi có thể được publish vào DLT và đọc lại dưới dạng bytes, không chỉ xác nhận error handler được gọi.

## 10. Kafka max message size không thay thế preflight

Kafka có các giới hạn liên quan kích thước message/record batch như `message.max.bytes` hoặc `max.message.bytes` theo cấp broker/topic, và những thuộc tính liên quan producer request, consumer fetch. Các giá trị đó bảo vệ luồng truyền và broker ở một mức nhất định.

Preflight ở ứng dụng có mục tiêu khác: giới hạn **payload và cấu trúc mà business consumer chấp nhận**. Ví dụ cluster cho phép record khá lớn vì có nhiều topic dùng chung, nhưng consumer xử lý đơn hàng chỉ cho phép 256 KiB.

Không cố giải quyết record quá lớn bằng cách giảm `max.poll.records`. Thuộc tính đó giới hạn số record một lần poll trả về, không phải kích thước của một record riêng lẻ.

Không dựa vào `fetch.max.bytes` như giới hạn tuyệt đối cho mỗi record: Kafka client có các bảo đảm fetch batch để consumer có thể tiến triển trong một số trường hợp record batch lớn hơn giới hạn cấu hình. Hãy đặt giới hạn ứng dụng một cách rõ ràng.

## 11. Kiểm tra UTF-8, JSON depth và payload độc hại

Kiểm tra byte đầu chỉ là bước rất nhẹ. Một payload JSON có thể bắt đầu đúng bằng `{` nhưng chứa:

- UTF-8 không hợp lệ.
- Cấu trúc nested rất sâu.
- Chuỗi hoặc mảng cực lớn.
- Object có số trường vượt dự kiến.
- Trường lặp hoặc kiểu không khớp schema.
- Dữ liệu nguy hiểm nếu ứng dụng tiếp tục dùng trong SQL, URL hoặc file path mà không kiểm soát.

### 11.1. UTF-8 phải được kiểm tra khi hợp đồng yêu cầu

Nếu producer cam kết JSON UTF-8, Java có thể dùng decoder cấu hình `CodingErrorAction.REPORT` để từ chối chuỗi byte sai encoding. Một số API chuyển `new String(bytes, UTF_8)` có thể thay byte sai bằng ký tự replacement; không nên xem việc tạo được `String` là bằng chứng payload hợp lệ.

Ví dụ:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String json = decoder.decode(
        ByteBuffer.wrap(raw)).toString();
~~~

Ví dụ yêu cầu xử lý `CharacterCodingException` và ngân sách bộ nhớ phù hợp khi tạo `String`. Với payload lớn, decode cả chuỗi chỉ để xác nhận encoding có thể tốn tài nguyên; nhiều JSON parser đã kiểm tra encoding khi đọc bytes.

### 11.2. Giới hạn độ sâu parser

Độ dài bytes không thể ngăn payload nested rất sâu. Khi dùng Jackson hoặc thư viện khác, hãy cấu hình các giới hạn parser như maximum nesting depth, string length, number length hoặc token count theo API phiên bản đang sử dụng.

Không đặt mọi giới hạn thật cao để “không bị lỗi”. Hãy chọn dựa trên hợp đồng nghiệp vụ, dữ liệu hiện có và mức độ tin cậy của producer.

### 11.3. Không sử dụng deserialization đa hình thiếu kiểm soát

Nếu dùng JSON có thông tin class type trong header hoặc payload, không bật cơ chế cho phép instantiate class tùy ý từ dữ liệu không đáng tin. Dùng danh sách trusted types/packages, mapping rõ ràng và giới hạn loại event được chấp nhận. Không coi type header là bằng chứng đáng tin về class an toàn.

## 12. Tombstone, empty payload và null semantics

Trong compacted topic, tombstone là record có key và value bằng `null`. Nó có thể mang ý nghĩa xóa state tương ứng key. Nếu preflight luôn báo lỗi khi `data == null`, consumer có thể phá vỡ đúng hợp đồng của topic compacted.

Hãy phân biệt:

| Trường hợp | Ý nghĩa có thể có | Quyết định cần dựa trên |
|---|---|---|
| `data == null` | Tombstone hoặc value null theo protocol | Hợp đồng topic, retention/compaction, state store |
| `data.length == 0` | Empty byte array | Hợp đồng payload, không đồng nhất với null |
| Bytes chứa `null` của JSON | JSON literal null | JSON contract và domain semantics |
| `{}` | JSON object rỗng | Schema required fields |
| Bytes bất kỳ không parse được | Malformed payload | Parser/schema validator |

Một topic có thể cho phép tombstone nhưng cấm empty payload. Cách xử lý phải được viết trong contract và test, không áp dụng một rule chung cho toàn bộ consumer.

## 13. Schema evolution và kiểm tra version

Consumer thường chạy song song với nhiều phiên bản producer trong rolling deployment. Preflight cần tương thích với chiến lược schema evolution.

Ví dụ:

- Producer v1 gửi JSON với `schema-version: 1`.
- Producer v2 thêm trường tùy chọn và gửi `schema-version: 2`.
- Consumer mới hỗ trợ cả v1 và v2.

Nếu preflight chỉ chấp nhận v2 trong khi topic còn record v1, ứng dụng sẽ đưa nhiều dữ liệu hợp lệ trước đó sang DLT. Điều này không phải cách triển khai schema evolution an toàn.

Một hợp đồng version rõ ràng có thể gồm:

1. Các version mà consumer chấp nhận.
2. Quy tắc chuyển version cũ thành model hiện tại.
3. Cách xử lý trường mới/không biết.
4. Giới hạn kích thước và loại dữ liệu theo version.
5. Kế hoạch nâng cấp producer/consumer và replay record cũ.

### 13.1. Schema ID không đồng nghĩa schema hợp lệ

Magic byte và schema ID có thể đúng cấu trúc nhưng registry đã xóa schema hoặc payload không khớp schema. Sau preflight, codec/schema validator vẫn phải xác minh dữ liệu thực tế. Đừng cho record qua business logic chỉ vì header chứa schema ID dương.

### 13.2. Xử lý registry outage

Nếu lỗi là registry timeout, retry hợp lý hơn DLT ngay trong một số hệ thống. Tuy nhiên cần backoff, deadline và circuit breaker để tránh hàng trăm consumer cùng dồn request vào registry đang không khỏe. Cached schema có thể giúp hệ thống tiếp tục hoạt động; việc cache/TTL cần theo yêu cầu tương thích và bảo mật.

## 14. Xử lý lỗi theo từng nhóm

Một bảng chính sách tham khảo:

| Lỗi | Retry? | Recovery đề xuất |
|---|---|---|
| Payload vượt size limit ứng dụng | Không, nếu hợp đồng không đổi | DLT raw bytes hoặc quarantine, alert producer |
| Magic byte sai | Thường không | DLT; kiểm tra serializer producer |
| JSON malformed | Thường không | DLT; ghi metadata parse error |
| Schema ID không tồn tại | Phụ thuộc nguyên nhân | Điều tra registry/deployment; retry hữu hạn nếu có tính tạm thời |
| Schema Registry timeout | Có giới hạn | Backoff/circuit breaker; alert nếu kéo dài |
| Thất bại xác thực chữ ký | Thường không | Quarantine, security alert theo mức độ |
| Null tombstone không được hỗ trợ | Không | DLT/quarantine hoặc thay đổi contract |
| Field nghiệp vụ thiếu | Thường không | Schema/business validation error, DLT |
| Database timeout sau deserialize | Có, nếu idempotent | Listener retry, không quy lỗi cho wire format |

Không nên retry mọi `SerializationException` cùng một chính sách nếu bên trong nó có cả lỗi dữ liệu và lỗi network. Nếu dùng custom deserializer, exception type/cause nên giữ nguyên nguồn gốc để error handler phân loại được.

### 14.1. Quarantine khác DLT như thế nào?

**DLT** là topic lưu record lỗi để điều tra/replay. **Quarantine** thường mô tả một luồng/kho dữ liệu tách biệt dành cho payload không đáng tin hoặc không phù hợp contract, có quyền truy cập và quy trình bảo mật riêng.

Không có một Kafka API bắt buộc tên `quarantine`. Hệ thống có thể dùng DLT làm quarantine nếu bảo đảm ACL, encryption, retention và không tự replay payload nguy hiểm. Đặt tên và ranh giới theo chính sách thực tế.

## 15. Bảo toàn key, headers và source location khi lỗi

Một record không deserialize được vẫn có thể có metadata rất hữu ích:

- Topic nguồn, partition, offset.
- Timestamp Kafka.
- Key hoặc key bytes.
- Producer/event id nếu có.
- Headers định dạng, schema, correlation id.
- Class exception, message và nguyên nhân gốc.

DLT recoverer có thể đưa metadata này vào DLT headers. Nhưng cần phân biệt offset nguồn và offset của DLT: chúng thuộc những log khác nhau.

Nếu lưu raw bytes vào database/object storage, nên ghi một tham chiếu ổn định cùng metadata nguồn thay vì log toàn bộ payload lên console.

### 15.1. Một record lỗi có thể được publish lại nhiều lần

Nếu DLT producer đã ghi record thành công nhưng consumer crash trước khi nguồn commit, record có thể được giao lại và xuất hiện thêm bản trong DLT. Vì vậy, audit/recovery cần idempotency key, chẳng hạn event id hoặc tổ hợp topic+partition+offset gốc cộng consumer group theo phạm vi bài toán.

Không dùng offset trên DLT làm khóa duy nhất để suy ra đây là cùng một event: các bản publish lại có thể có offset DLT khác nhau.

## 16. Không commit offset khi recovery chưa an toàn

Một quy tắc quan trọng: **Không xác nhận một record không xử lý được cho tới khi nó đã được xử lý hoặc lưu vào đường recovery bền vững theo thiết kế.**

Ví dụ rủi ro:

~~~text
Record ở offset 90
     |
     v
Preflight phát hiện malformed bytes
     |
     v
Ứng dụng chỉ ghi log WARN
     |
     v
Listener trả về bình thường
     |
     v
Container commit offset 91
     |
     v
Record lỗi không còn đường retry
~~~

Đường đúng cần:

~~~text
Record không hợp lệ
     |
     v
Exception được phân loại
     |
     v
Recoverer gửi DLT/quarantine
     |
     +---- Publish thành công ---> Handler hoàn tất
     |                              |
     |                              v
     |                     Commit theo ack policy
     |
     +---- Publish thất bại -----> Không xem là recovery thành công;
                                    ghi alert và retry theo chính sách
~~~

Chi tiết commit phụ thuộc `AckMode`, transaction, error handler và phiên bản Spring Kafka. Không giả định chỉ cần gọi `kafkaTemplate.send()` đã hoàn tất publish: với producer bất đồng bộ, cần quan sát kết quả publish và exception.

## 17. Observability cho pre-deserialization validation

Một hệ thống có thể có ít record lỗi nhưng tác động lớn nếu chúng xuất hiện ở đầu partition và cản trở tiến độ. Hãy giám sát cả **tỷ lệ lỗi dữ liệu** lẫn **tác động lên consumer**.

| Metric | Ý nghĩa |
|---|---|
| Preflight reject count/rate | Số record bị từ chối vì framing/header/size |
| Deserialization failure rate | Số lỗi parser/codec |
| Failure by normalized reason | Phân loại size, magic byte, schema, encoding, null |
| Schema Registry error rate | Lỗi lookup/timeout/5xx |
| DLT publish success/failure | Đường recovery có hoạt động không |
| Consumer lag by partition | Có partition bị chặn bởi record lỗi không |
| Oldest unprocessed record age | Độ trễ thực tế so với SLO |
| Processing duration | Chi phí preflight + deserialize + business |
| Raw payload size histogram | Xu hướng kích thước dữ liệu |

### 17.1. Structured log

Một log nên có:

~~~text
service=orders-consumer
group=orders-consumer
topic=orders.events
partition=2
offset=1708
stage=pre_deserialize
reason=invalid_magic_byte
payloadBytes=412
schemaId=unknown
recovery=dlt_requested
~~~

Đây là dữ liệu minh họa. Log thực tế không nên chứa raw payload, token hoặc thông tin nhạy cảm nếu chưa có chính sách cho phép. Có thể log hash payload nếu phục vụ deduplication, nhưng cần cân nhắc rủi ro rò rỉ và collisions trong cách dùng.

### 17.2. Metric tags

Các tag nên có cardinality thấp như `service`, `topic` (tập hữu hạn), `reason` đã chuẩn hóa và `environment`. Không dùng event id, offset, order id, exception message hoặc raw header values làm tag vì có thể tạo số lượng time series rất lớn.

### 17.3. Alert

Thiết lập cảnh báo khi:

- Deserialization failure tăng bất thường sau deploy producer.
- Một schema version không được consumer nhận.
- DLT publish thất bại.
- Một partition có lag tăng trong khi tốc độ xử lý bằng 0.
- Schema Registry timeout kéo dài.
- Tỷ lệ payload vượt size limit tăng nhanh.
- Quarantine backlog hoặc tuổi record chưa xử lý vượt SLA.

## 18. Runbook: consumer lỗi liên tục ở cùng offset

1. Xác định consumer group, topic, partition và offset từ log.
2. Kiểm tra exception phát sinh ở Kafka deserializer, message converter hay trong listener.
3. Nếu Kafka deserializer trực tiếp ném lỗi, xác định có dùng `ErrorHandlingDeserializer` không.
4. Xác minh payload bytes, framing và header contract bằng công cụ an toàn theo chính sách dữ liệu.
5. Phân loại lỗi tạm thời của registry/network và lỗi dữ liệu vĩnh viễn.
6. Kiểm tra error handler/recoverer có được cấu hình đúng factory không.
7. Xác nhận DLT serializer hỗ trợ raw bytes của record lỗi.
8. Kiểm tra publish DLT và committed offset trước/sau recovery.
9. Sửa producer, serializer hoặc schema, sau đó replay có kiểm soát.

Không tự chạy lệnh thay đổi group offset để bỏ qua record khi chưa có sự chấp thuận theo quy trình dữ liệu. Bỏ qua offset có thể làm mất khả năng xử lý một sự kiện quan trọng.

## 19. Runbook: sau deploy có nhiều record bị từ chối

1. So sánh thời điểm lỗi với phiên bản producer/consumer mới.
2. Nhóm reject theo nguyên nhân: size, framing, schema, encoding, header.
3. Xác định producer nào tạo record lỗi; không chỉ nhìn consumer.
4. Kiểm tra schema compatibility và version trong rollout.
5. Xem preflight có vô tình siết contract với record cũ không.
6. Kiểm tra dữ liệu hợp lệ có bị false positive vì whitespace/BOM/tombstone hay không.
7. Nếu cần rollback, xác định tương thích với record mới đã nằm trong topic.
8. Sau khi sửa, replay DLT/quarantine theo batch nhỏ và đối soát idempotency.

False positive ở preflight có thể nghiêm trọng: một lượng lớn record hợp lệ bị xem là corrupt chỉ vì kiểm tra quá đơn giản. Do đó, quy tắc phải bám sát producer contract và phiên bản schema.

## 20. Runbook: lỗi khi publish raw payload sang DLT

1. Kiểm tra type thực tế của value sau `ErrorHandlingDeserializer`.
2. Kiểm tra producer DLT serializer có hỗ trợ `byte[]` hay không.
3. Kiểm tra producer có dùng serializer kiểu domain object cho mọi record không.
4. Kiểm tra DLT topic tồn tại, ACL, partition routing và kích thước message.
5. Kiểm tra kết quả bất đồng bộ của send, timeout và broker error.
6. Xác nhận error handler không đánh dấu recovery thành công khi DLT publish lỗi.
7. Thử lại bằng một record deserialize hỏng có kiểm soát.

Đừng “chữa” lỗi DLT bằng cách nuốt exception hoặc commit qua record nguồn. Điều đó chuyển từ một lỗi recovery quan sát được sang nguy cơ mất dữ liệu.

## 21. Kiểm thử chiến lược pre-deserialization

### 21.1. Trường hợp hợp lệ

1. Payload JSON hợp lệ theo schema hiện hành.
2. Payload hợp lệ theo một phiên bản schema cũ vẫn được hỗ trợ.
3. Header được gửi đầy đủ và đúng encoding.
4. Record ở kích thước gần giới hạn nhưng không vượt.
5. Tombstone hợp lệ nếu topic cho phép.

### 21.2. Trường hợp dữ liệu không hợp lệ

1. Payload rỗng và null ở topic cấm tombstone.
2. Payload vượt giới hạn kích thước.
3. JSON sai cú pháp nhưng có byte đầu là `{`.
4. Header content type nói JSON nhưng payload là binary.
5. UTF-8 malformed.
6. Confluent framing thiếu bytes hoặc magic byte sai.
7. Schema ID không hợp lệ.
8. JSON quá sâu hoặc chuỗi dài vượt parser constraint.
9. Key deserialize lỗi.

### 21.3. Trường hợp hạ tầng

1. Registry timeout tạm thời: retry có giới hạn.
2. Registry trả schema không tồn tại: classification theo hợp đồng.
3. DLT broker hoặc ACL không cho publish: record nguồn không bị xác nhận mất dữ liệu.
4. Consumer restart sau lỗi và record được giao lại.
5. Rebalance giữa retry và recovery.
6. Producer thay đổi serializer khi rolling update.

### 21.4. Điều cần quan sát trong test

- Listener có được gọi hay không (lỗi xảy ra trước hay sau Kafka deserializer).
- Loại exception và cause chain.
- Record có được retry hay chuyển DLT theo policy.
- DLT có giữ key, value/raw bytes và metadata nguồn.
- Group offset commit có đúng sau recovery.
- Idempotency có ngăn side effect trùng khi redelivery.

Test nên kiểm tra kết quả dữ liệu và offset thực tế, không chỉ assert số lần logger được gọi.

## 22. Thiết kế ranh giới trách nhiệm

Để hệ thống dễ vận hành, nên chia trách nhiệm rõ:

| Thành phần | Trách nhiệm |
|---|---|
| Producer contract | Sinh dữ liệu đúng format/schema, giữ event id |
| Wire preflight | Kiểm tra bytes, framing, metadata và resource budget |
| Deserializer/codec | Parse bytes thành object, kiểm tra encoding/format |
| Schema validator | Kiểm tra cấu trúc và tính tương thích |
| Business validator | Kiểm tra quy tắc nghiệp vụ và trạng thái |
| Error handler | Phân loại exception, retry/backoff/recovery |
| DLT/quarantine | Giữ record không xử lý được để điều tra |
| Observability | Metrics/log/trace theo lỗi và hậu quả |
| Replay workflow | Đưa record trở lại xử lý sau khi nguyên nhân đã được sửa |

Không để lớp preflight bắt đầu gọi API nghiệp vụ hoặc cập nhật database khi chưa decode được record. Preflight nên rẻ và ít side effect để hoạt động an toàn ngay cả khi gặp malformed/untrusted bytes.

## 23. Checklist vận hành

### Format và preflight

- [ ] Hợp đồng topic nêu rõ serialization format, size limit, tombstone policy và schema version.
- [ ] Đã chọn điểm preflight đúng: raw `byte[]` listener hoặc custom Kafka deserializer.
- [ ] Preflight không giả định sai rằng mọi JSON bắt đầu ngay bằng `{` hoặc mọi binary có cùng magic byte.
- [ ] Headers được kiểm tra theo contract nhưng không bị xem là nguồn đáng tin tuyệt đối.
- [ ] Có giới hạn kích thước, độ sâu parser và kiểu event hợp lệ.

### Error handling

- [ ] Có `ErrorHandlingDeserializer` nếu custom Kafka deserializer có thể ném lỗi trước listener.
- [ ] Phân loại malformed data và lỗi Registry/network khác nhau.
- [ ] Retry/backoff hữu hạn; không retry storm với payload vĩnh viễn sai.
- [ ] DLT producer hỗ trợ raw bytes và domain object theo recovery path.
- [ ] Publish DLT thất bại không dẫn đến commit offset nguồn sai.

### Độ tin cậy

- [ ] Event id và metadata nguồn được giữ qua DLT/replay.
- [ ] Consumer idempotent khi Kafka giao lại record.
- [ ] Tombstone được xử lý theo chính sách riêng.
- [ ] Schema evolution có kiểm thử tương thích ngược.
- [ ] Replay được giới hạn tốc độ và có đối soát kết quả.

### Observability và bảo mật

- [ ] Metrics cho reject rate, deserialization failure, registry timeout, lag và DLT.
- [ ] Log có stage, reason, topic/partition/offset nhưng không lộ payload nhạy cảm.
- [ ] Không dùng event id/offset làm metric tag.
- [ ] Có runbook xử lý poison pill và lỗi DLT serialization.
- [ ] ACL, encryption, retention và quyền truy cập quarantine/DLT được quản lý.

## Kết luận

Kiểm tra dữ liệu trước khi deserialize là lớp phòng vệ giúp Spring Kafka consumer phát hiện sớm payload không phù hợp hợp đồng wire format và giới hạn tài nguyên trước khi tạo domain object. Có thể triển khai bằng `ByteArrayDeserializer` rồi validate/decode trong listener, hoặc bằng custom Kafka `Deserializer` kết hợp `ErrorHandlingDeserializer` để lỗi trước listener vẫn có đường xử lý an toàn. Các kiểm tra hữu ích gồm kích thước, tombstone, framing, magic byte, schema ID, content type và integrity, nhưng chúng không thay thế parser, schema validation hay quy tắc nghiệp vụ. Hãy phân biệt lỗi dữ liệu vĩnh viễn với lỗi hạ tầng tạm thời, giữ raw payload cho DLT, chỉ commit khi recovery đã an toàn, và đo lag/exception/recovery để một record lỗi không trở thành poison pill kéo dài trên consumer group.
