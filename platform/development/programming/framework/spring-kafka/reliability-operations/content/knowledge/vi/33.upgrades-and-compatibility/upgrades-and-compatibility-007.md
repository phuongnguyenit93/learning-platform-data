# Thay đổi header và record metadata khi nâng cấp Spring Kafka

## 1. Bối cảnh: một thay đổi nhỏ ở header có thể làm mất khả năng tương thích

Khi nâng cấp Spring Kafka, ứng dụng có thể vẫn kết nối broker và đọc được payload, nhưng logic xử lý lại thất bại vì **tên header đổi**, **kiểu dữ liệu sau conversion khác trước**, **metadata không còn ở vị trí code mong đợi**, hoặc **một header bị mapper/serializer loại bỏ**.

Ví dụ, một consumer nhận sự kiện đơn hàng:

```text
Kafka topic: orders.created
  key: ORD-1001
  value: {"orderId":"ORD-1001","amount":120.50}

  headers:
    x-correlation-id: "req-123"
    x-schema-version: "v2"
```

Ứng dụng cần biết:

- `x-correlation-id` để nối log giữa dịch vụ phát và xử lý.
- `x-schema-version` để chọn logic tương thích dữ liệu.
- `topic`, `partition`, `offset` để điều tra và replay message.
- `timestamp` để phân biệt thời điểm Kafka ghi nhận record với thời điểm xử lý.
- Thông tin lỗi và nguồn gốc record nếu message đi vào retry topic hoặc dead-letter topic (DLT).

Trong một lần nâng cấp, developer thay `@KafkaListener` hoặc `MessageConverter` nhưng không cập nhật contract header. Kết quả có thể là:

```text
09:00 payload parse OK
09:00 x-correlation-id = null
09:00 group processing throws validation error
09:00 record được retry nhiều lần
09:01 record chuyển vào DLT nhưng thiếu origin metadata
```

Lỗi nằm ở **lớp chuyển đổi và metadata**, không nhất thiết do Kafka broker mất message.

Trong chương **Spring Kafka Reliability Operations → Nâng cấp và tương thích**, bài này hướng dẫn phân biệt các lớp header, nhận diện thay đổi API theo phiên bản, triển khai đọc/ghi header ổn định và xây kiểm thử contract trước khi rolling upgrade producer, consumer, converter hay retry infrastructure.

## 2. Phân biệt ba nguồn thông tin: native header, message header và record metadata

Đây là nền tảng quan trọng nhất của bài học.

### 2.1. Kafka native headers — dữ liệu nằm trên record

Kafka client cung cấp `org.apache.kafka.common.header.Headers` và `Header`:

```java
public interface Header {
    String key();
    byte[] value();
}
```

Về bản chất, một native Kafka header có **tên là String** và **giá trị là `byte[]`** (hoặc null theo contract native). Kafka cho phép **nhiều header cùng tên** trên một record.

Ví dụ:

```text
ProducerRecord
  topic     = orders.created
  partition = (broker/partitioner quyết định nếu không chỉ định)
  key       = ORD-1001
  value     = {...}
  headers   =
    x-correlation-id -> [114, 101, 113, 45, 49, 50, 51]
    x-schema-version -> [118, 50]
```

Những byte đó có thể được giải mã là UTF-8, JSON, Avro schema identifier hoặc binary tùy **giao ước giữa producer và consumer**. Kafka broker không tự biết header là String, UUID, Map hay object Java.

### 2.2. Spring MessageHeaders — dữ liệu sau khi message được chuyển đổi

Nếu dùng Spring Messaging `Message<?>`, `@Header` hoặc `@Headers`, Spring Kafka có thể ánh xạ native Kafka headers thành `org.springframework.messaging.MessageHeaders` bằng một `KafkaHeaderMapper`.

```text
Kafka native Header("x-correlation-id", byte[])
                    |
                    v
             KafkaHeaderMapper
                    |
                    v
Spring MessageHeaders["x-correlation-id"] = String hoặc byte[]
```

**Kiểu trả về tùy mapper và cấu hình**. Nếu producer gửi raw UTF-8 bytes nhưng consumer mong một `String` được JSON mapper phục hồi theo type metadata, kết quả có thể khác mong đợi khi thay converter.

Ngoài business headers, Spring Kafka dùng những header nội bộ hoặc synthetic headers để làm việc với `Message<?>`, như `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.OFFSET` và `KafkaHeaders.RECEIVED_PARTITION`. Chúng không phải lúc nào cũng là native Kafka headers đã được producer đưa lên wire.

### 2.3. Record metadata — thuộc tính của bản ghi trong Kafka log

Mỗi `ConsumerRecord<K,V>` có các thuộc tính:

```text
topic
partition
offset
timestamp
timestampType
serializedKeySize
serializedValueSize
key
value
headers
leaderEpoch (nếu có)
```

Các thuộc tính như topic/partition/offset nằm ở **record metadata**, không cần producer tự thêm header `x-offset`. Offset do broker gán khi append; producer không thể biết **offset kết quả** trước khi broker xác nhận việc ghi.

Spring Kafka có thể **chiếu metadata** vào `MessageHeaders` của listener, nhưng một consumer nhận raw `ConsumerRecord` sẽ đọc trực tiếp từ record. Nếu code nhầm những metadata này là native header, sẽ phát sinh lỗi hoặc thiếu thông tin khi đổi đường xử lý.

### Bảng quyết định

| Cần thông tin nào? | Nên lấy từ đâu? | Không nên làm gì? |
| --- | --- | --- |
| Correlation ID do ứng dụng gán | Native header đã quy ước, map sang String nếu cần | Giả định mọi producer đều dùng Spring JSON mapper |
| Schema version nghiệp vụ | Header contract hoặc envelope payload | Đồng nhất với `__TypeId__` của Spring serializer |
| Topic, partition, offset khi consume | `ConsumerRecord` hoặc metadata được Spring cung cấp | Yêu cầu producer tự gửi offset |
| Offset của lần publish vừa thành công | `SendResult.recordMetadata()` | Sử dụng offset của record input |
| Delivery attempt | Header/metadata do error handler cấu hình | Giả định header luôn tồn tại |
| Lịch sử lỗi khi qua DLT | Headers của DLT record do recoverer tạo | Giả định chúng là metadata gốc của Kafka record |

## 3. Dòng dữ liệu từ producer đến listener

```text
Producer application
  |
  +-- ProducerRecord(key, value, Headers)
  |        |
  |        +-- header x-correlation-id (byte[])
  |        +-- header x-schema-version (byte[])
  |
  v
Kafka broker
  |
  +-- gán topic partition + offset
  +-- lưu timestamp theo cấu hình topic
  |
  v
KafkaConsumer.poll()
  |
  +-- ConsumerRecord<K,V>
  |       topic, partition, offset, timestamp
  |       headers (native Headers)
  |
  +-- record listener nhận ConsumerRecord trực tiếp
  |
  +-- hoặc MessagingMessageConverter
           |
           v
        Message<?> / @KafkaListener arguments
           payload, @Header, ConsumerRecordMetadata
```

Một upgrade có thể thay **converter**, **serializer/deserializer**, **listener signature**, **error handler** hoặc **batch listener mode**. Để xác định nguyên nhân mất metadata, cần xem nó biến mất ở **lớp nào** chứ không chỉ xem payload cuối cùng.

## 4. Thay đổi KafkaHeaders khi chuyển từ Spring Kafka 2.x lên 3.x

Spring Kafka 3.0 đã **loại bỏ** một số constant từng bị deprecated ở nhánh 2.9. Đây là thay đổi dễ gây lỗi compile khi nâng dependency:

| Constant cũ (2.x) | Constant dùng trong 3.x trở lên | Bối cảnh |
| --- | --- | --- |
| `KafkaHeaders.MESSAGE_KEY` | `KafkaHeaders.KEY` | Record key ở phía gửi |
| `KafkaHeaders.PARTITION_ID` | `KafkaHeaders.PARTITION` | Partition đích phía gửi |
| `KafkaHeaders.RECEIVED_MESSAGE_KEY` | `KafkaHeaders.RECEIVED_KEY` | Key của record nhận |
| `KafkaHeaders.RECEIVED_PARTITION_ID` | `KafkaHeaders.RECEIVED_PARTITION` | Partition của record nhận |

Những tên mới là những constant được công bố trong Spring Kafka 3.x và 4.x. Nếu một project vẫn dùng `MESSAGE_KEY`/`PARTITION_ID` và nâng trực tiếp lên 3.x, code có thể không biên dịch.

Ví dụ **trước upgrade**:

```java
@KafkaListener(topics = "orders.created")
public void listen(
        String payload,
        @Header(KafkaHeaders.RECEIVED_MESSAGE_KEY) String key,
        @Header(KafkaHeaders.RECEIVED_PARTITION_ID) int partition) {
    // Spring Kafka 2.x style.
}
```

Ví dụ **sau upgrade**:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "orders.created")
public void listen(
        @Payload String payload,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String key,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition) {
    // Spring Kafka 3.x+ style.
}
```

**Phân biệt ngữ cảnh:** `KEY`/`PARTITION` mô tả phía **send** theo Spring Messaging; `RECEIVED_KEY`/`RECEIVED_PARTITION` là thông tin của record **đã receive**. Không đổi toàn bộ các chỗ `RECEIVED_*` thành `KEY` chỉ vì thấy tên constant ngắn hơn.

### Vì sao phải kiểm tra cả mã nguồn và cấu hình?

Một dự án có thể dùng constant trong:

- `@Header` trên `@KafkaListener`.
- `MessageBuilder.setHeader(...)` khi publish.
- `KafkaTemplate.send(Message<?>)`.
- `KafkaListenerErrorHandler`.
- Filter, interceptor, converter hoặc adapter.
- Test assertions đọc `MessageHeaders`.

Ngoài lỗi compile, code dùng **literal string** kiểu `"kafka_receivedMessageKey"` có thể tiếp tục biên dịch nhưng đọc sai key của synthetic headers mới. Vì vậy khi migration, ưu tiên constant của đúng framework version thay vì hardcode tên nội bộ.

## 5. Null key: header có thể không xuất hiện

Từ Spring Kafka 2.5, nếu một incoming record có `null` key, header nhận key được **bỏ hẳn** thay vì được populate với giá trị null. Điều này phù hợp với quy ước `spring-messaging`: các header có giá trị null không xuất hiện.

Ví dụ listener dễ gặp lỗi:

```java
@KafkaListener(topics = "orders.events")
void onEvent(
        String payload,
        @Header(KafkaHeaders.RECEIVED_KEY) String key) {
    // required=true mặc định: có thể lỗi với null-key record.
}
```

Giải pháp nếu nghiệp vụ cho phép null key:

```java
@KafkaListener(topics = "orders.events")
void onEvent(
        String payload,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String key) {

    if (key == null) {
        // Quy tắc dành cho record không có key.
    }
}
```

**Khi nâng version, test null-key là bắt buộc** nếu topic có tombstone, record không khóa hoặc nguồn dữ liệu không luôn cung cấp key. Không thiết kế business logic giả định header luôn có mặt.

Null payload và null key là hai tình huống khác nhau. Một Kafka tombstone dùng **null value** cho log compaction, nhưng key của tombstone thường có ý nghĩa xác định bản ghi cần xóa. Hãy xử lý chúng theo contract topic, đừng gộp toàn bộ vào điều kiện “key hoặc value null thì bỏ qua”.

## 6. Đọc record metadata qua ConsumerRecord trực tiếp

Khi logic vận hành cần topic, partition, offset và native headers chính xác, `ConsumerRecord` là phương thức rõ ràng và ít phụ thuộc mapping:

```java
package com.example.kafka.consumer;

import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderRecordListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-processors")
    public void onOrder(ConsumerRecord<String, String> record) {

        String topic = record.topic();
        int partition = record.partition();
        long offset = record.offset();
        long timestamp = record.timestamp();

        Header correlationHeader =
                record.headers().lastHeader("x-correlation-id");

        String correlationId = correlationHeader == null
                || correlationHeader.value() == null
                ? null
                : new String(
                        correlationHeader.value(),
                        StandardCharsets.UTF_8);

        // Dùng dữ liệu an toàn để log/audit/processing.
        processOrder(
                record.value(), record.key(),
                topic, partition, offset, timestamp, correlationId);
    }

    private void processOrder(
            String payload, String key, String topic,
            int partition, long offset, long timestamp,
            String correlationId) {
        // Logic nghiệp vụ riêng của ứng dụng.
    }
}
```

Ưu điểm:

- Đọc native `Headers` đúng giá trị bytes từ Kafka client sau deserialization stage.
- Không phụ thuộc vào quy ước của `KafkaHeaderMapper` để chuyển custom headers thành String/UUID.
- Metadata record được lấy trực tiếp, không cần synthetic header của converter.
- Có thể xử lý nhiều header trùng tên bằng `record.headers().headers(name)`.

Giới hạn:

- `record.value()` đã qua value deserializer. Nếu deserialization fail **trước khi listener được gọi**, method này không tự nhận raw record; cần `ErrorHandlingDeserializer` hoặc cơ chế error handler phù hợp.
- Record metadata **không chứng minh transaction đã commit ở downstream**, cũng không cho biết số lần listener đã retry trừ khi bạn instrument thêm.
- Đừng tự commit offset bằng cách sửa header; offset acknowledgement nằm ở consumer/container.

### Tránh parse header binary sai encoding

`new String(header.value(), UTF_8)` chỉ hợp lệ khi producer cam kết **UTF-8 text**. Nếu producer lưu UUID 16 bytes, integer theo binary codec hay JSON object, decode theo codec được quy định. Không đoán kiểu từ tên header.

## 7. Đọc metadata bằng @Header trong @KafkaListener

Khi dùng `@KafkaListener` với payload mapping, Spring Kafka có thể cung cấp metadata qua synthetic message headers:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(
        topics = "orders.created",
        groupId = "order-processors")
public void listen(
        @Payload String payload,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String receivedKey,
        @Header(KafkaHeaders.RECEIVED_TOPIC)
        String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION)
        int partition,
        @Header(KafkaHeaders.OFFSET)
        long offset,
        @Header(KafkaHeaders.RECEIVED_TIMESTAMP)
        long timestamp) {

    // Log hoặc xử lý cùng metadata đã được Spring cung cấp.
}
```

Đây là kiểu signature thông dụng trên Spring Kafka 3.x. `KafkaHeaders.OFFSET` là **offset của record được consume**; nó không phải offset của message mới khi một listener gửi sang topic khác.

### Metadata không phải header do producer tự viết

Nếu consumer gửi record qua một topic khác bằng cách copy mọi `MessageHeaders`, nó **không nên vô tình chuyển synthetic header** `RECEIVED_TOPIC`/`OFFSET` thành business metadata của record mới. Một converter thường loại trừ một số header gắn với `ConsumerRecord` khi mapping outbound, nhưng với custom code copy headers thủ công, bạn phải kiểm soát.

Một record ở topic `orders.created` offset 25, sau khi republish sang `orders.validated` có thể được broker ghi ở offset 900. Gắn một header tên `kafka_offset=25` vào record mới không thay đổi offset thật của record đó; ngược lại có thể khiến log/consumer hiểu sai nguồn gốc.

Muốn giữ provenance, dùng một **header nghiệp vụ riêng** như `x-origin-topic`, `x-origin-partition` và `x-origin-offset`, có định dạng/codec rõ ràng, hoặc dùng các header chuẩn do `DeadLetterPublishingRecoverer` cung cấp khi gửi DLT.

## 8. ConsumerRecordMetadata: lấy metadata mà không lặp nhiều @Header

Từ Spring Kafka 2.5, listener có thể nhận `ConsumerRecordMetadata`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.adapter.ConsumerRecordMetadata;
import org.springframework.stereotype.Component;

@Component
public class OrderMetadataListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-processors")
    public void listen(
            String payload,
            ConsumerRecordMetadata metadata) {

        String topic = metadata.topic();
        int partition = metadata.partition();
        long offset = metadata.offset();
        long timestamp = metadata.timestamp();

        // ConsumerRecordMetadata không mang key/value.
        audit(topic, partition, offset, timestamp);
    }

    private void audit(
            String topic, int partition, long offset, long timestamp) {
        // Ứng dụng tự định nghĩa.
    }
}
```

`ConsumerRecordMetadata` nằm trong package `org.springframework.kafka.listener.adapter`, cung cấp các thông tin của record (ngoại trừ key/value), bao gồm timestamp type. Nó là **method argument hỗ trợ bởi listener adapter**, không phải một header do producer gửi.

Khi cần key, value và toàn bộ native headers, dùng `ConsumerRecord`. Khi method chủ yếu xử lý payload nhưng cần biết topic/partition/offset để audit, `ConsumerRecordMetadata` hoặc `@Header` có thể gọn hơn.

### Không nhầm với producer RecordMetadata

Kafka clients cũng có `org.apache.kafka.clients.producer.RecordMetadata`, thường nhận được khi **producer send thành công**. Dù tên tương tự, metadata bên producer và consumer gắn với hai thời điểm khác nhau:

```text
Producer: ProducerRecord -> broker append -> RecordMetadata result
Consumer: poll -> ConsumerRecord -> ConsumerRecordMetadata adapter
```

Nếu một processor đọc từ topic input rồi gửi sang topic output, **offset input** và **offset output** phải được ghi nhận thành hai trường riêng.

## 9. RecordMetadata khi gửi Kafka: CompletableFuture và callback

Spring Kafka 3.x đổi `KafkaTemplate` từ trả `ListenableFuture` sang `CompletableFuture`. Đây là breaking change hay gặp trong mã theo dõi send result.

### Trước Spring Kafka 3.x

Một số ứng dụng Spring Kafka 2.x dùng:

```java
ListenableFuture<SendResult<String, String>> future =
        kafkaTemplate.send("orders.out", "ORD-1001", payload);

future.addCallback(success -> {
    // success.getRecordMetadata()
}, error -> {
    // xử lý lỗi
});
```

### Với Spring Kafka 3.x trở lên

```java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String key, String payload) {
        kafkaTemplate.send("orders.out", key, payload)
                .whenComplete((SendResult<String, String> result, Throwable ex) -> {
                    if (ex != null) {
                        recordPublishFailure(key, ex);
                        return;
                    }

                    RecordMetadata metadata = result.getRecordMetadata();
                    recordPublishSuccess(
                            key,
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset(),
                            metadata.timestamp());
                });
    }

    private void recordPublishFailure(String key, Throwable ex) {
        // Log/audit có kiểm soát.
    }

    private void recordPublishSuccess(
            String key, String topic, int partition,
            long offset, long timestamp) {
        // Ghi nhận metadata của OUTPUT record.
    }
}
```

Lưu ý:

- `result.getRecordMetadata()` là metadata của **record vừa publish** và được broker xác nhận theo cấu hình producer; không phải metadata của record listener đã consume.
- Callback chạy theo lifecycle của future; đừng giả định nó luôn ở consumer listener thread hoặc có MDC của thread gọi.
- Nếu code có Kafka transaction, send future thành công **không tự chứng minh transaction cuối cùng đã commit**. Transaction có thể bị abort ở một bước sau.
- Không lấy một offset đã gửi thành công làm business idempotency key; khi retry produce, offset có thể khác.
- Trong migration 2.x → 3.x, tìm mọi `ListenableFuture`/`addCallback` liên quan KafkaTemplate và cập nhật cách theo dõi outcome.

## 10. Native Kafka headers có thể trùng tên

Kafka hỗ trợ nhiều giá trị cùng tên:

```text
Headers:
  x-route: primary
  x-route: backup
  x-route: audit
```

Với native API:

```java
Headers headers = record.headers();

Header latest = headers.lastHeader("x-route");
Iterable<Header> all = headers.headers("x-route");
```

`lastHeader` lấy phần tử cuối theo tên, còn `headers(name)` cho phép duyệt các giá trị. Nếu ứng dụng có contract chỉ cho một giá trị, việc thấy nhiều giá trị có thể là **lỗi dữ liệu** và nên được phát hiện thay vì âm thầm nhận cuối cùng.

### Sự khác nhau khi map vào Spring MessageHeaders

`MessageHeaders` về cơ bản là bản đồ từ tên sang một object. Trước khi hỗ trợ multi-value mapping tường minh, các header trùng tên có thể bị rút lại thành một giá trị. Native `Headers` vẫn chứa nhiều entry, nhưng kết quả qua converter có thể **chỉ còn giá trị cuối**.

Từ **Spring Kafka 4.0**, `JsonKafkaHeaderMapper` và `SimpleKafkaHeaderMapper` có hỗ trợ cấu hình ánh xạ multi-value. Để giữ tất cả giá trị khi dùng Spring Messaging, cần khai báo tên hoặc pattern được xem là multi-value:

```java
import org.springframework.kafka.support.mapping.JsonKafkaHeaderMapper;

JsonKafkaHeaderMapper mapper = new JsonKafkaHeaderMapper();
mapper.setMultiValueHeaderPatterns(
        "x-route",
        "x-audit-*");
```

Đây là API **Spring Kafka 4.x**; không sao chép vào code 3.x rồi mong compile. Với header được cấu hình multi-value, mapper có thể gửi các phần tử thành những native headers riêng và nhận về `List<?>` qua các bước conversion.

**Quan trọng khi upgrade:**

1. Tập hợp các topic đang dùng header trùng tên, ví dụ route list hoặc event baggage.
2. Kiểm tra consumer hiện mong `String`/`byte[]` hay `List<?>`.
3. Chỉ bật multi-value cho header có contract xác định; không bật pattern quá rộng nếu downstream không hỗ trợ.
4. Test record có một, nhiều và không có header; bao gồm cả thứ tự và byte contents.
5. Nếu đang dùng `SimpleKafkaHeaderMapper`, xác minh cách nó xử lý collection khác `JsonKafkaHeaderMapper`.

Mặc định của mapper 4.x **không đồng nghĩa mọi header lặp được giữ tự động**. Theo tài liệu, không cấu hình multi-value có thể dẫn đến một header có giá trị collection được JSON serialize như một khối hoặc khi receive chỉ giữ giá trị cuối. Đây là thay đổi quan trọng với những hệ thống rely on multiple same-name headers.

## 11. HeaderMapper: thay đổi kiểu dữ liệu sau conversion

Spring Kafka hỗ trợ các mapper thường gặp:

| Mapper | Đặc điểm | Rủi ro khi upgrade |
| --- | --- | --- |
| `SimpleKafkaHeaderMapper` | Làm việc chủ yếu với raw bytes và một số rule String | Consumer không nên giả định mọi header thành object Java |
| `DefaultKafkaHeaderMapper` (Jackson 2) | JSON encode/decode nhiều kiểu header, dùng type metadata | Kiểu String/Map/UUID có thể khác khi đổi mapper |
| `JsonKafkaHeaderMapper` (Jackson 3, 4.x) | Hướng triển khai mới cho Jackson 3, hỗ trợ multi-value theo cấu hình | Đổi class/config và cần test wire compatibility |
| Native `ConsumerRecord.headers()` | Truy cập đúng bytes sau deserialization | Caller phải tự decode theo contract |

### 11.1. Header type metadata spring_json_header_types

Khi dùng mapper JSON của Spring Kafka, một header đặc biệt `spring_json_header_types` chứa thông tin kiểu để map inbound headers trở lại các kiểu Java tương ứng.

Ví dụ minh họa:

```text
Kafka Headers:
  x-attempts            -> JSON/binary bytes
  x-correlation-id      -> UTF-8 bytes
  spring_json_header_types -> {"x-attempts":"java.lang.Integer", ...}
```

Khi một producer bên ngoài không dùng Spring Kafka gửi cùng những header mà **không có `spring_json_header_types`**, consumer không thể mặc nhiên biết `x-attempts` là Integer. Một mapper có thể đưa nó về `byte[]`. Nên tránh xây cross-language contract phụ thuộc vào Java class name của mapper nếu các producer/consumer do nhiều công nghệ triển khai.

### 11.2. String encoding đã từng thay đổi

Trong lịch sử Spring Kafka, mapper JSON đổi cách xử lý header `String` ở phiên bản 2.3: string header không còn mặc định JSON-encode thành chuỗi có dấu ngoặc kép, nhưng vẫn có type metadata để consumer Spring phù hợp hiểu lại.

Khi có producer/consumer **nhiều phiên bản đồng thời**, producer mới và consumer cũ có thể bất đồng về bytes:

```text
Old producer serialization (minh họa):
  x-correlation-id = bytes of "req-123" (JSON string có dấu ngoặc)

Newer producer serialization (minh họa):
  x-correlation-id = bytes of req-123  (raw UTF-8)
```

Để tương thích với consumer cũ ở những migration liên quan, mapper hỗ trợ `setEncodeStrings(true)` trên các version tương ứng. Nhưng không bật tùy tiện khi đã dùng raw interoperability contract; hãy kiểm tra **wire bytes thực tế**.

### 11.3. Truyền raw UTF-8 String giữa nhiều ngôn ngữ

Nếu producer Java và consumer Node/Python/Go cùng dùng header `x-correlation-id`, contract ổn định có thể là:

```text
Name: x-correlation-id
Wire type: UTF-8 bytes
Value format: opaque printable identifier
Presence: optional
Maximum length: 128 bytes
Duplicates: forbidden
```

Khi dùng Spring Kafka JSON header mapper ở phía Java, có thể cấu hình raw mapping cho header này:

```java
import java.util.Map;
import org.springframework.kafka.support.DefaultKafkaHeaderMapper;

DefaultKafkaHeaderMapper mapper =
        new DefaultKafkaHeaderMapper();
mapper.setRawMappedHeaders(
        Map.of("x-correlation-id", true));
```

Ví dụ trên phù hợp cho **Spring Kafka 3.x dùng Jackson 2**. Giá trị `true` cho biết header String outbound được map thành raw bytes và inbound raw bytes được map ngược thành String theo charset cấu hình (mặc định UTF-8). Khi chuyển sang 4.x/Jackson 3, dùng mapper class tương ứng và xác minh lại method/config của phiên bản được dùng.

Nếu tất cả ứng dụng đều cam kết raw bytes, một phương án tránh phụ thuộc hoàn toàn vào mapper là tạo `ProducerRecord` với `RecordHeader` và đọc trực tiếp `ConsumerRecord.headers()` ở nơi cần chính xác tuyệt đối.

## 12. Serialization type headers không phải schema version nghiệp vụ

Spring Kafka JSON serializer có thể thêm header type metadata như:

```text
__TypeId__
__KeyTypeId__
__ContentTypeId__
```

Các header này giúp Jackson-based serializer/deserializer nhận biết Java type khi payload có nhiều kiểu. Chúng **không có nghĩa** schema của hệ thống là phiên bản `v1`, `v2` hay `v3`.

Không nên viết:

```java
// Không nên diễn giải __TypeId__ như business schema version.
String schemaVersion = readHeader("__TypeId__");
```

Ví dụ business contract rõ ràng hơn:

```text
x-event-type: order.created
x-schema-version: 2
content-type: application/json
```

Từ schema version, consumer chọn parser hoặc migration logic phù hợp. Khi dùng Avro/Protobuf/JSON Schema Registry, schema identity có thể nằm trong payload wire format hoặc metadata do serializer cung cấp; đừng giả định mọi framework dùng cùng một header.

### 12.1. Vì sao mất __TypeId__ sau khi deserialize?

Theo hành vi của Spring Kafka JSON deserializer, type info headers có thể bị **remove mặc định sau khi deserialization** (hành vi này xuất hiện từ nhánh 2.2). Vì thế listener không thấy `__TypeId__` không nhất thiết do producer không gửi.

Với Spring Kafka 3.x dùng `JsonDeserializer`, các thuộc tính liên quan bao gồm:

```properties
spring.json.use.type.headers=true
spring.json.remove.type.headers=true
spring.json.trusted.packages=com.example.orders.events
```

Đây là các **Kafka deserializer config keys**, không phải toàn bộ file `application.properties` cho Spring Boot. Trong Spring Boot, khi truyền vào consumer properties thường đặt dưới `spring.kafka.consumer.properties.*` hoặc cấu hình trực tiếp deserializer:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.use.type.headers: true
        spring.json.remove.type.headers: true
        spring.json.trusted.packages: "com.example.orders.events"
```

Lưu ý trong Spring Kafka 4.x có các class Jackson 3 mới với tên hằng/property tương ứng. Khi migration, cần chọn đúng serializer/deserializer pair; không trộn package Jackson 2/3 một cách ngẫu nhiên rồi giả định behavior cũ.

Nếu application cần lưu type info phục vụ audit, có thể cấu hình giữ lại khi phù hợp, nhưng **đừng phụ thuộc type header kỹ thuật cho khả năng hiểu schema lâu dài**. Schema version nên là contract nghiệp vụ độc lập.

### 12.2. Trusted packages là ranh giới bảo mật

Không cấu hình `trusted.packages=*` chỉ để “hết lỗi” khi upgrade. Type metadata có thể ảnh hưởng cách deserializer tạo object Java. Chỉ cho phép các package/schema type cần thiết, hoặc dùng target type cố định khi contract topic cho phép.

Với header mapper JSON, cấu hình package tin cậy cũng quyết định kiểu Java nào được phép tái tạo từ `spring_json_header_types`. Nếu một package không được trust, mapper có thể trả một representation như `NonTrustedHeaderType` thay vì deserialize thành object ban đầu.

Khi nâng từ Jackson 2 sang Jackson 3, phải kiểm tra cả **class name/import** và **policies trusted type**; không dùng wildcard rộng như cách sửa nhanh.

## 13. Spring Kafka 4.x: Jackson 3 và tên lớp mới

Spring Kafka 4.x bổ sung hỗ trợ Jackson 3 bên cạnh các class Jackson 2. Những cặp tên thường gặp:

| Jackson 2 / code cũ | Jackson 3 / code mới | Vai trò |
| --- | --- | --- |
| `DefaultKafkaHeaderMapper` | `JsonKafkaHeaderMapper` | JSON header mapping |
| `JsonSerializer` | `JacksonJsonSerializer` | Serialize payload JSON |
| `JsonDeserializer` | `JacksonJsonDeserializer` | Deserialize payload JSON |
| `JsonSerde` | `JacksonJsonSerde` | Serde cho Kafka Streams |
| `JsonMessageConverter` và các biến thể | `JacksonJsonMessageConverter` và các biến thể | Chuyển đổi Message payload |
| `DefaultJackson2JavaTypeMapper` | `DefaultJacksonJavaTypeMapper` | Ánh xạ type identifiers |

Tài liệu Spring Kafka 4.x nêu rằng các class Jackson 2 cũ vẫn được cung cấp nhưng đã deprecated trong hướng nâng cấp. Framework có thể ưu tiên Jackson 3 khi cả hai cùng có trên classpath.

**Hệ quả vận hành:** thêm dependency Jackson 3 hoặc nâng parent BOM có thể khiến conversion path khác trước mặc dù business code ít thay đổi. Migration nên kiểm tra **effective dependency tree**, các bean converter/mapper thực sự được tạo và bytes gửi/nhận.

### Một chiến lược nâng cấp thận trọng

1. Khóa version Spring Boot/Spring Kafka/Jackson được hỗ trợ cùng nhau; không chỉ update một jar lẻ.
2. Ghi lại mapper/serializer/deserializer đang hoạt động ở phiên bản cũ.
3. Tạo contract tests so sánh raw header bytes và converted types.
4. Chuyển class/import sang API mới ở code branch riêng nếu muốn dùng Jackson 3.
5. Chạy mixed-version tests: producer cũ → consumer mới, producer mới → consumer cũ.
6. Nâng consumer trước hoặc producer trước tùy hướng forward/backward compatibility đã được chứng minh bằng test.
7. Bật giám sát lỗi deserialization/conversion/retry và triển khai canary.
8. Chỉ gỡ compatibility flags sau khi không còn phiên bản cũ cần hỗ trợ.

Đừng giả định Jackson 3 là một thay đổi chỉ ở import. Với hệ thống có producer/consumer viết bằng nhiều ngôn ngữ, **wire contract** mới là điều quan trọng.

## 14. Producer gửi header: dùng ProducerRecord khi cần wire contract rõ ràng

Để gửi chính xác một header UTF-8 theo giao ước giữa nhiều hệ thống:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.springframework.kafka.core.KafkaTemplate;

public class OrderWirePublisher {

    private final KafkaTemplate<String, String> template;

    public OrderWirePublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public void publish(
            String orderId, String payload, String correlationId) {

        RecordHeaders headers = new RecordHeaders();
        headers.add(
                "x-correlation-id",
                correlationId.getBytes(StandardCharsets.UTF_8));
        headers.add(
                "x-schema-version",
                "2".getBytes(StandardCharsets.UTF_8));

        ProducerRecord<String, String> record =
                new ProducerRecord<>(
                        "orders.created",
                        null, // partition: để Kafka chọn
                        orderId,
                        payload,
                        headers);

        template.send(record);
    }
}
```

Ở ví dụ này, ta dùng constructor `ProducerRecord(topic, partition, key, value, headers)` phù hợp với các Kafka client version phổ biến của Spring Kafka 3.x. `KafkaTemplate.send(record)` gửi raw Kafka producer record, không cần thông qua `MessageBuilder` và Spring Messaging header mapper để biểu diễn custom header.

Tuy nhiên, **`template.send(record)` bất đồng bộ**. Nếu cần biết broker đã nhận record, xử lý future `whenComplete(...)` hoặc chờ kết quả có timeout. Không log “đã publish thành công” chỉ vì method `send` trả future.

### Đưa trace/correlation qua header

Nếu ứng dụng dùng Micrometer Tracing/OpenTelemetry, instrumentation có thể inject trace context vào headers theo propagation format riêng. Không tự đặt key `traceparent` hoặc copy trace ID nếu không hiểu context propagation; tốt hơn để tracing instrumentation xử lý. Business correlation ID là contract độc lập và vẫn có thể cần cho audit khi trace đã hết retention.

## 15. Dùng MessageBuilder: phân biệt header để route với header đưa lên wire

Với `KafkaTemplate.send(Message<?>)`, Spring Messaging header có thể điều khiển topic/key/partition/timestamp của record outgoing:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-1001\"}")
        .setHeader(KafkaHeaders.TOPIC, "orders.created")
        .setHeader(KafkaHeaders.KEY, "ORD-1001")
        .setHeader("x-correlation-id", "req-123")
        .build();

kafkaTemplate.send(message);
```

Ví dụ Spring Kafka 3.x trở lên; `kafkaTemplate` được giả định là một `KafkaTemplate` thích hợp trong class service. `KafkaHeaders.TOPIC` xác định topic đích và `KafkaHeaders.KEY` xác định key khi converter tạo Kafka record. Các header còn lại được chuyển đổi theo `KafkaHeaderMapper` của `MessagingMessageConverter`.

Nếu consumer ngoài Java đọc `x-correlation-id`, phải đảm bảo mapper encode header thành **bytes đúng contract**. Đừng suy từ kiểu `String` của `MessageBuilder` rằng Kafka broker lưu String; Kafka wire header vẫn là `byte[]`.

### Khi nào dùng cách nào?

| Nhu cầu | Cách thuận tiện |
| --- | --- |
| Muốn nhận Spring Messaging payload và routing headers | `MessageBuilder` + `KafkaTemplate.send(Message<?>)` |
| Muốn kiểm soát chính xác byte của native header | `ProducerRecord` + `RecordHeaders` |
| Muốn dùng JSON object headers giữa ứng dụng Spring | Header mapper JSON có contract type rõ |
| Muốn giao tiếp đa ngôn ngữ ổn định | Native bytes theo UTF-8/binary/JSON contract đã công bố |

## 16. Batch listener: metadata được ánh xạ theo vị trí

Với batch mode, listener nhận **nhiều records**, vì vậy topic/partition/offset có thể là **danh sách** thay vì giá trị đơn.

Ví dụ một listener cấu hình batch qua container factory:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-consumers",
        containerFactory = "batchKafkaListenerContainerFactory")
public void listenBatch(
        java.util.List<String> payloads,
        @Header(KafkaHeaders.RECEIVED_TOPIC)
        java.util.List<String> topics,
        @Header(KafkaHeaders.RECEIVED_PARTITION)
        java.util.List<Integer> partitions,
        @Header(KafkaHeaders.OFFSET)
        java.util.List<Long> offsets) {

    for (int i = 0; i < payloads.size(); i++) {
        audit(payloads.get(i),
                topics.get(i),
                partitions.get(i),
                offsets.get(i));
    }
}
```

Đây là đoạn method minh họa, `audit(...)` cần được ứng dụng định nghĩa. Container factory phải thật sự có `batchListener=true`. Không dùng signature của record listener rồi giả định metadata dạng một scalar trong batch.

### Batch converted headers và native headers

Khi dùng `BatchMessagingMessageConverter`:

- `KafkaHeaders.BATCH_CONVERTED_HEADERS` có thể chứa `List<Map<String,Object>>`, mỗi map tương ứng một item trong batch.
- Khi không dùng header mapper, `KafkaHeaders.NATIVE_HEADERS` có thể cung cấp native `Headers`; với batch là một danh sách tương ứng các records.
- Vị trí trong danh sách header metadata phải gắn với đúng vị trí trong danh sách payload.

Đối với các record có **null key**, danh sách header/metadata có thể có quy tắc hiện diện khác với một list các giá trị đơn giản. Tránh zip nhiều danh sách mà không kiểm tra cấu hình converter và test trường hợp null/missing headers. Nếu cần chắc chắn metadata từng record, nhận `List<ConsumerRecord<K,V>>` trong batch listener để đọc topic/partition/offset/native headers từ đúng record.

## 17. Header trong retry và dead-letter topic

Các hệ thống reliability thường dùng `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` hoặc retry topics. Khi record bị chuyển sang DLT, framework có thể giữ custom headers và bổ sung **thông tin nguồn gốc, exception**.

Ví dụ:

```text
Original:
  topic=orders.created, partition=2, offset=125
  headers:
    x-correlation-id=req-123

After DeadLetterPublishingRecoverer:
  topic=orders.created-dlt, partition=2, offset=10  (DLT broker gán)
  headers:
    x-correlation-id=req-123
    kafka_dlt-original-topic = orders.created
    kafka_dlt-original-partition = 2
    kafka_dlt-original-offset = 125
    kafka_dlt-exception-fqcn = ...
```

Tên native key ở đoạn mô tả là **minh họa về ý nghĩa**; trong code dùng các hằng `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, `KafkaHeaders.DLT_EXCEPTION_FQCN` của đúng phiên bản thay vì hardcode literal tên wire không kiểm chứng.

### DLT metadata khác metadata của DLT record

Một consumer đọc DLT có:

- `record.topic()/partition()/offset()`: vị trí **hiện tại trong DLT**.
- `KafkaHeaders.DLT_ORIGINAL_*`: thông tin về **record nguồn** mà recoverer đã gắn.

Nếu điều tra message ban đầu ở `orders.created`, cần dùng origin metadata, không lấy offset `10` của DLT để đi tìm trên topic input.

### Header tích lũy khi retry nhiều lần

Kafka cho phép trùng tên header. Nếu record bị republish qua nhiều retry topics, DLT exception/origin headers có thể **tích lũy**, đặc biệt là stack trace. Điều này có thể dẫn đến:

- Header list ngày càng lớn.
- Record vượt giới hạn kích thước.
- Consumer đọc `lastHeader` nhưng business muốn origin đầu tiên.
- Tính toán retry depth sai vì đếm header không có contract.

`DeadLetterPublishingRecoverer` có các cơ chế quản lý, ví dụ `appendOriginalHeaders` và `stripPreviousExceptionHeaders`; các mức mặc định/phạm vi có thể khác giữa basic DLT và non-blocking retries. Hãy đối chiếu cấu hình thực tế thay vì chỉ dựa vào một giả định chung.

Nếu cần một origin header bất biến trong nhiều hop, định nghĩa rõ **first origin** và **last failure**. Không tùy tiện overwrite source metadata khi re-drive DLT.

### Byte encoding của DLT headers

Thông tin `DLT_ORIGINAL_PARTITION`/`DLT_ORIGINAL_OFFSET` được Spring Kafka mã hóa theo convention riêng. Không tự giả định đó là UTF-8 text số `"125"`; khi đọc native headers cần decode đúng binary representation của framework version, hoặc dùng converter/utility phù hợp. Với DLT consumers viết bằng ngôn ngữ khác, contract codec càng quan trọng.

## 18. Delivery attempt header: vắng mặt không phải lần thử đầu tiên

Spring Kafka cung cấp `KafkaHeaders.DELIVERY_ATTEMPT` để hỗ trợ quan sát retry với những error handler/after rollback processors có hỗ trợ và khi container được cấu hình bật:

```java
@KafkaListener(topics = "orders.created")
public void listen(
        String payload,
        @Header(name = KafkaHeaders.DELIVERY_ATTEMPT, required = false)
        Integer attempt) {

    int observedAttempt = attempt == null ? -1 : attempt;
    // -1: header không khả dụng/không được bật;
    // không khẳng định đây là attempt=1.
}
```

Ở raw `ConsumerRecord`, giá trị của delivery attempt header có thể là một số nguyên mã hóa **4 bytes**, cần decode theo convention framework:

```java
Header header =
        record.headers().lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);

if (header != null && header.value() != null
        && header.value().length == Integer.BYTES) {
    int attempt = java.nio.ByteBuffer
            .wrap(header.value())
            .getInt();
}
```

Một listener dùng converted header mapper có thể nhận `int` trực tiếp, trong khi listener raw nhận `byte[]`. Nếu sau upgrade đổi listener signature từ `ConsumerRecord` sang `@Header`, test cả **kiểu và giá trị** của delivery attempt.

Không mặc định header luôn được bật, hoặc luôn có ở batch listeners. Cấu hình `deliveryAttemptHeader` và khả năng cung cấp của error handler quyết định sự hiện diện.

## 19. Mô hình contract header ổn định cho producer và consumer

Một contract nên mô tả hơn tên header. Ví dụ:

| Header | Wire format | Bắt buộc? | Duplicate? | Quy tắc |
| --- | --- | --- | --- | --- |
| `x-event-type` | UTF-8 string | Có | Không | `order.created`, `order.updated`, ... |
| `x-schema-version` | UTF-8 ASCII digits | Có | Không | `1`, `2`, ... |
| `x-correlation-id` | UTF-8 string | Có (trừ migration window) | Không | Không chứa PII |
| `x-source-service` | UTF-8 string | Tùy nhu cầu | Không | Nằm trong danh mục service đã biết |
| `traceparent` | W3C trace context theo instrumentation | Tùy có tracing | Theo propagator | Không tự sửa bằng business code |
| `x-replay-reason` | UTF-8 enum | Chỉ có trong replay | Không | `manual`, `scheduled`, `repair` |
| Spring `__TypeId__` | Framework-specific | Không thuộc business contract | Theo serializer | Không dùng làm business schema version |

### Nguyên tắc thiết kế

1. Dùng **tên riêng có namespace** như `x-schema-version` cho business semantics, tránh tên giống internal Kafka/Spring metadata.
2. Quy định rõ header là optional hay required.
3. Định nghĩa raw bytes/charset/endianness, không chỉ kiểu Java.
4. Xác định có cho duplicate cùng tên hay không.
5. Giới hạn kích thước và ký tự để tránh khai thác log/serialization.
6. Phân biệt **semantic field** với transport metadata.
7. Có test producer ↔ consumer trên byte-level và converted-value level.
8. Có compatibility window khi thay tên hoặc kiểu; tránh đổi producer và consumer cùng lúc rồi mất khả năng rollback.

### Chuẩn hóa tên header

Kafka native header names là `String` và phân biệt hoa thường. `X-Correlation-Id` và `x-correlation-id` có thể bị coi là hai key khác nhau trong consumer code. Hãy chọn convention, ví dụ tất cả business header tên chữ thường với dấu gạch ngang, và test sự nhất quán này.

## 20. Migration contract: thêm header mới rồi mới bỏ header cũ

Giả sử hệ thống cũ dùng `correlationId` (camelCase) còn hệ thống mới muốn `x-correlation-id`. Thay producer và consumer cùng lúc sẽ tạo rủi ro ở rolling deployment.

Một kế hoạch an toàn:

```text
Phase A:
  Old producer writes correlationId
  Old consumer reads correlationId

Phase B:
  Updated consumer reads x-correlation-id, fallback correlationId
  Producer vẫn viết correlationId

Phase C:
  New producer writes BOTH headers
  Consumer mới/old vẫn đọc được

Phase D:
  Xác nhận không còn consumer cũ / không còn backlog cần key cũ
  New producer writes only x-correlation-id

Phase E:
  Xóa fallback của consumer khi retention/backlog phù hợp
```

Đoạn mã tương thích cho native `ConsumerRecord`:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;

static String getCorrelationId(Headers headers) {
    Header newHeader = headers.lastHeader("x-correlation-id");
    Header oldHeader = headers.lastHeader("correlationId");

    if (newHeader != null && newHeader.value() != null) {
        return new String(newHeader.value(), StandardCharsets.UTF_8);
    }
    if (oldHeader != null && oldHeader.value() != null) {
        return new String(oldHeader.value(), StandardCharsets.UTF_8);
    }
    return null;
}
```

**Quan trọng:** nếu cả hai headers tồn tại nhưng khác giá trị, đừng âm thầm chọn một khi contract yêu cầu duy nhất. Có thể phát sinh do producer lỗi, do proxy/bridge thay đổi metadata hoặc do replay. Với thông tin audit quan trọng, nên **fail/quarantine** theo chính sách, ghi error category và điều tra.

### Retention/backlog khi đổi header

Ngay cả khi tất cả producer mới đã viết header mới, consumer vẫn có thể đọc records cũ trong topic hoặc replay từ DLT. Vì vậy thời điểm xóa fallback phải tính tới **topic retention, compaction, replay process, DLT retention và audit storage**, không chỉ ngày deploy.

## 21. Kiểm thử native headers bằng Kafka client API

Đoạn test sau không cần Kafka broker; nó xác minh bytes và duplicate semantics của `RecordHeaders`:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;

class NativeHeaderContractTest {

    @Test
    void utf8HeaderRetainsExactBytes() {
        RecordHeaders headers = new RecordHeaders();
        headers.add(
                "x-correlation-id",
                "req-123".getBytes(StandardCharsets.UTF_8));

        Header header = headers.lastHeader("x-correlation-id");

        assertNotNull(header);
        assertArrayEquals(
                "req-123".getBytes(StandardCharsets.UTF_8),
                header.value());
    }

    @Test
    void duplicateHeadersAreNotAutomaticallyCollapsed() {
        RecordHeaders headers = new RecordHeaders();
        headers.add("x-route", new byte[]{1});
        headers.add("x-route", new byte[]{2});

        List<Header> all = new ArrayList<>();
        headers.headers("x-route").forEach(all::add);

        assertEquals(2, all.size());
        assertArrayEquals(new byte[]{2},
                headers.lastHeader("x-route").value());
    }

    @Test
    void oldAndNewCorrelationKeysCanCoexist() {
        RecordHeaders headers = new RecordHeaders();
        headers.add(
                "correlationId",
                "req-123".getBytes(StandardCharsets.UTF_8));
        headers.add(
                "x-correlation-id",
                "req-123".getBytes(StandardCharsets.UTF_8));

        assertEquals("req-123", getCorrelationId(headers));
    }
}
```

Method `getCorrelationId(...)` là helper ở mục trước; đưa nó vào test class hoặc import static từ tiện ích ứng dụng. Unit test này chứng minh **Kafka header bytes**, chưa kiểm tra mapper hay wire exchange thật với broker.

## 22. Kiểm thử header mapper giữa hai phiên bản

Nên có một bộ **contract fixture** giữ nguyên:

```text
fixtures/
  native-headers-v1.json
  native-headers-v2.json
  payload-order-created-v1.json
  payload-order-created-v2.json
```

File fixture chỉ là gợi ý cấu trúc của dự án test, không phải file được tạo trong bài này. Với mapper của Spring Kafka 3.x, ví dụ round-trip:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.DefaultKafkaHeaderMapper;
import org.springframework.messaging.MessageHeaders;

class HeaderMapperContractTest {

    @Test
    void rawCorrelationStringIsCompatible() {
        DefaultKafkaHeaderMapper mapper =
                new DefaultKafkaHeaderMapper();
        mapper.setRawMappedHeaders(
                Map.of("x-correlation-id", true));

        MessageHeaders source =
                new MessageHeaders(
                        Map.of("x-correlation-id", "req-123"));

        RecordHeaders nativeHeaders = new RecordHeaders();
        mapper.fromHeaders(source, nativeHeaders);

        Map<String, Object> received = new HashMap<>();
        mapper.toHeaders(nativeHeaders, received);

        assertEquals("req-123", received.get("x-correlation-id"));
    }
}
```

Đây là ví dụ **Spring Kafka 3.x/Jackson 2**. Với 4.x/Jackson 3, dùng `JsonKafkaHeaderMapper` tương ứng. Giữ một test fixture của hệ thống cũ để kiểm tra:

- Name/bytes của native headers producer đã tạo.
- Type trong converted `MessageHeaders`.
- Trường hợp header vắng mặt hoặc giá trị null.
- Trường hợp string có Unicode, dấu ngoặc kép hoặc ký tự escaping.
- Duplicate headers và chiều dữ liệu qua mapper.
- Trường hợp package type metadata không được trust.

**Chỉ test round-trip cùng một mapper chưa đủ chứng minh interoperability.** Nếu mapper A encode và decode được dữ liệu của chính nó, mapper B ở phiên bản cũ vẫn có thể không đọc được. Test trực tiếp cặp producer-version A ↔ consumer-version B.

## 23. Integration test với broker: producer cũ và consumer mới

Với dự án Spring Boot 3.x/Spring Kafka 3.x, có thể dùng `spring-kafka-test` và `@EmbeddedKafka` hoặc Testcontainers Kafka. Broker test có ích để xác minh cả producer send, assigned metadata, converter, error handler và actual listener signatures.

### Ma trận kiểm thử

| Producer | Consumer | Điều cần chứng minh |
| --- | --- | --- |
| Version cũ | Version cũ | Baseline contract vẫn đúng |
| Version cũ | Version mới | Backward compatibility |
| Version mới | Version cũ | Forward compatibility trong rolling window |
| Version mới | Version mới | Định dạng mục tiêu |
| External (không Spring) | Spring mới | Raw UTF-8/binary headers không phụ thuộc Java type mapper |
| Spring mới | External | Producer không tạo bytes mà external consumer không hiểu |
| DLT từ version cũ | Consumer re-drive mới | Origin metadata và exception headers còn đọc được |
| Record có null key/value | Consumer mới | Signature/required header phù hợp |
| Record có duplicate header | Mapper mới | Không mất dữ liệu ngoài contract |

### Integration test nên xác minh gì?

1. Gửi record có key, payload và hai custom headers.
2. Chờ producer future hoàn thành; lấy `SendResult.getRecordMetadata()` để biết **output offset**.
3. Consume bằng `read_committed` hoặc `read_uncommitted` theo mục tiêu test (đừng cấu hình sai isolation level).
4. So sánh native header bytes lấy từ `ConsumerRecord.headers()`.
5. Nếu listener dùng conversion, so sánh converted header values và types.
6. Assert `topic`/`partition`/`offset` bên listener bằng metadata từ record nhận, không bằng một literal hardcode.
7. Gây exception có kiểm soát, đưa vào DLT và xác minh origin topic/partition/offset.
8. Thử lại trên đúng producer/consumer versions dự định sử dụng khi deploy.

Lưu ý: producer có thể nhận một offset sau send, nhưng test concurrent có thể làm thứ tự offset khác dự kiến. Nên tương quan bằng key hoặc correlation ID, không khẳng định một message luôn có offset cụ thể trừ khi topic/partition/test setup được cô lập.

## 24. Kiểm thử batch metadata và DLT

Khi ứng dụng chuyển từ record listener sang batch listener, có rủi ro mapping metadata sai vị trí. Một test nên gửi ba records tới cùng topic nhưng có key và header khác nhau:

```text
Record A: key=A, correlation=req-a
Record B: key=B, correlation=req-b
Record C: key=C, correlation=req-c
```

Nếu nhận `List<ConsumerRecord<String,String>>`, test trực tiếp:

```java
for (ConsumerRecord<String, String> record : records) {
    String key = record.key();
    String correlation =
            decodeUtf8(record.headers(), "x-correlation-id");

    assertEquals(expectedCorrelationByKey.get(key), correlation);
}
```

`decodeUtf8(...)` và `expectedCorrelationByKey` là helper/fixture của test. Với list của `Message<?>` hoặc converted-header list, cần bảo đảm index giữa payload và metadata khớp.

Trong DLT test, hãy ghi riêng:

```text
dltRecord.topic / partition / offset
originTopic / originPartition / originOffset
errorCategory
correlationId
```

Không gộp `offset` của DLT vào `originOffset`. Nếu retry/re-drive qua nhiều topics, test rằng origin metadata không bị vô tình thay bằng metadata của hop trung gian.

## 25. Quan sát sự cố header sau upgrade

Một kế hoạch rollout nên có logging hữu ích nhưng không làm lộ dữ liệu:

```json
{
  "event": "kafka_header_contract_violation",
  "service": "orders-consumer",
  "topic": "orders.created",
  "partition": 2,
  "offset": 125,
  "headerName": "x-schema-version",
  "errorCategory": "MISSING_REQUIRED_HEADER",
  "consumerVersion": "vNext",
  "producerContractVersion": "v2"
}
```

Đây là schema log đề xuất, không phải record tự động của Spring Kafka. Thường nên log:

- `topic`, `partition`, `offset` để truy lại record.
- `consumerGroup` và version ứng dụng để biết deployment nào lỗi.
- Header name, error category, expected codec/schema version.
- Correlation ID đã được kiểm soát nếu không nhạy cảm.
- Exception class và nguyên nhân tóm tắt.

Không ghi raw payload chứa PII, Authorization header, token hoặc toàn bộ DLT exception stack trace vào log công khai.

### Metric gợi ý

| Metric | Nhóm tag có cardinality thấp | Mục đích |
| --- | --- | --- |
| `kafka_header_contract_error_total` | service, topic, errorCategory | Phát hiện incompatibility sớm |
| `kafka_deserialization_failure_total` | service, topic, errorCategory | Phân biệt wire payload/type header lỗi |
| `kafka_dlt_publish_total` | service, sourceTopic, reason | Theo dõi lỗi dẫn đến DLT |
| `kafka_record_process_duration` | service, listenerId | Phát hiện converter mới tăng latency |
| `kafka_record_retry_total` | service, listenerId, reason | Thấy lỗi dữ liệu khiến retry tăng |
| `kafka_consumed_lag` | group, topic | Cảnh báo backlog trong rollout |

Đây là **tên metric ví dụ của ứng dụng**, không phải khẳng định Spring Kafka/Micrometer có sẵn nguyên tên như bảng. Tránh dùng `offset`, correlation ID, payload, exception message hoặc header value làm metric label vì cardinality cao.

### Một số tín hiệu phân biệt root cause

| Triệu chứng | Nguyên nhân khả dĩ | Điều nên xem |
| --- | --- | --- |
| Compiler báo `MESSAGE_KEY` không tồn tại | Constant đã bị bỏ ở Spring Kafka 3.x | Đổi sang `KEY` |
| Listener required header exception khi key null | Header `RECEIVED_KEY` không hiện diện | `required=false` và contract null key |
| Consumer thấy `byte[]` thay vì String | Mapper hoặc raw header contract khác | Header mapper, rawMappedHeaders, codec |
| Consumer không thấy `__TypeId__` | Deserializer đã remove type headers | Config removeTypeHeaders và pipeline |
| Json header chuyển thành `NonTrustedHeaderType` | Package không nằm trong trusted list | Whitelist package cần thiết |
| Sau Jackson 3 upgrade, map value type đổi | Mapper/serializer/deserializer mới hoạt động | Bean type, dependency tree, fixtures |
| Duplicate header mất giá trị đầu | Default mapper chỉ expose last value | Native headers hoặc multi-value mapping 4.x |
| @Header metadata scalar fail ở batch listener | Batch trả list | Chuyển signature batch hoặc dùng raw records |
| Callback publish không compile | `ListenableFuture` đã đổi sang `CompletableFuture` | `whenComplete` / `getRecordMetadata` |
| DLT offset không khớp source | Nhầm DLT record offset và original offset | `DLT_ORIGINAL_OFFSET` |
| Retry count luôn bằng 1/không có | Delivery attempt header chưa bật hoặc đọc sai type | Container config và raw/converted view |
| Offset trùng sau republish? | Offset là theo topic-partition, không phải ID sự kiện | Dùng business key/correlation |

## 26. Quy trình nâng cấp header/metadata trong production

Một runbook có thể chia làm các giai đoạn sau.

### Giai đoạn 1 — Inventory

Lập danh sách **tất cả** producer/consumer đang liên quan đến topic:

- Spring Kafka 2.x, 3.x, 4.x, hoặc Kafka clients trực tiếp.
- Ngoại ngữ: Python, Node.js, Go, .NET.
- Header bắt buộc và optional.
- Codec và version payload.
- Deserialization/type mapping policy.
- Retry/DLT/re-drive flows, retention và consumer group.
- Có batch listener hay record listener.

### Giai đoạn 2 — Freeze contract

Ghi lại những mẫu record có:

- Native header bytes.
- Kafka key và payload bytes/format.
- Presence/absence của optional headers.
- Duplicate headers nếu producer có thể phát.
- Type info headers ở Spring JSON.
- DLT original headers và exception headers.
- Topic/partition/offset/timestamp từ metadata của record.

Các fixtures này phải có phiên bản và được lưu ngoài vòng đời ứng dụng để so sánh khi nâng cấp.

### Giai đoạn 3 — Build và compile migration

Thay `MESSAGE_KEY` → `KEY`, `RECEIVED_MESSAGE_KEY` → `RECEIVED_KEY`, `PARTITION_ID` → `PARTITION` và `RECEIVED_PARTITION_ID` → `RECEIVED_PARTITION` nếu nâng 2.x lên 3.x. Điều chỉnh `KafkaTemplate` futures từ `ListenableFuture` sang `CompletableFuture`.

Nếu chuyển 3.x lên 4.x và lựa chọn Jackson 3, xác định các class serializer/header mapper mới. Không kết hợp API của các version vào cùng một ví dụ chạy mà chưa đối chiếu package.

### Giai đoạn 4 — Contract và integration tests

Chạy unit tests native headers, mapper round-trip và mixed-version tests với broker. Thử null key, duplicate header, UTF-8, header type metadata, DLT và delivery attempts. Ghi nhận record output metadata.

### Giai đoạn 5 — Canary và rolling deployment

Đưa consumer tương thích đọc **cả header cũ và header mới** nếu contract thay đổi. Tiếp theo nâng producer với giai đoạn dual-write. Theo dõi conversion failures, DLT rate, lag và logs header contract; có ngưỡng rollback rõ.

### Giai đoạn 6 — Bỏ compatibility shim có điều kiện

Sau khi hệ thống không còn consumer cũ và backlog/retained records không yêu cầu field cũ, mới bỏ dual-write/fallback. Lưu tài liệu contract để các nhóm downstream biết kiểu header trên wire và ý nghĩa metadata.

## 27. Những lỗi thiết kế cần tránh

### 27.1. Coi Kafka header là một String

Kafka header trên wire là bytes. Decode sai charset hoặc nhầm JSON bytes với raw text sẽ tạo lỗi khó nhận biết. Luôn có codec theo contract.

### 27.2. Coi KafkaHeaders.RECEIVED_* là native headers từ producer

Đây là các constant Spring Messaging dùng để đại diện thuộc tính của incoming record. Khi dùng `ConsumerRecord` trực tiếp, hãy đọc metadata từ record. Không hardcode synthetic names vào contract cross-language.

### 27.3. Đổi tên constant mà không kiểm tra chiều send/receive

`KEY` dùng outbound; `RECEIVED_KEY` dùng inbound. Chuyển hai cái cho nhau có thể làm code compile nhưng không đi đúng đường conversion.

### 27.4. Đọc @Header required khi header optional

Incoming key có thể null, retry/delivery attempt headers có thể chưa được bật, và business headers có thể thiếu trong dữ liệu lịch sử. Sử dụng `required=false` hoặc API nullable và có policy rõ khi thiếu.

### 27.5. Dựa vào Java class name như schema contract

`__TypeId__` và `spring_json_header_types` là metadata phục vụ framework, không phải semantic schema version. Type/class refactor hoặc đổi Jackson có thể phá interoperability.

### 27.6. Mở trusted packages bằng wildcard không kiểm soát

Đặt `trusted.packages=*` để bỏ lỗi deserialization làm mở rộng bề mặt tạo object từ dữ liệu ngoài. Nên whitelist package hoặc sử dụng target type/schema cố định.

### 27.7. Mất duplicate headers qua mapper

Native Kafka hỗ trợ nhiều giá trị, còn Spring MessageHeaders không tự biểu diễn đúng mọi duplicate theo mặc định. Với 4.x cần cấu hình multi-value tường minh; với 3.x cần đọc native headers nếu contract yêu cầu.

### 27.8. Nhầm offset của record nguồn và record DLT/output

Offset chỉ có ý nghĩa trong một **topic-partition**. Bản ghi được publish lại có offset mới. Dùng origin headers hoặc business ID để nối sự kiện, không dùng một offset làm ID toàn cục.

### 27.9. Đặt header quá lớn hoặc chứa dữ liệu bí mật

Kafka headers được tính trong kích thước message và có thể bị copy qua retry/DLT. Đừng nhúng stack trace tùy ý, full payload, token hoặc thông tin nhạy cảm vào custom headers. Theo dõi giới hạn message size và retention.

### 27.10. Chỉ test payload

Ứng dụng có thể parse JSON thành công nhưng mất correlation ID hoặc DLT origin. Upgrade test phải assert **headers và metadata**, không chỉ số message và business payload.

## 28. Bài tập thực hành

**Bài 1 — Đọc native headers.** Viết một producer gửi `x-correlation-id` và `x-schema-version` dưới dạng UTF-8 bytes. Consumer nhận `ConsumerRecord`, decode và in topic/partition/offset/timestamp. Test record thiếu một header.

**Bài 2 — Migration KafkaHeaders.** Tìm và chuyển các constant cũ `MESSAGE_KEY`, `PARTITION_ID`, `RECEIVED_MESSAGE_KEY`, `RECEIVED_PARTITION_ID` sang tên mới. Giải thích trường nào dùng cho producer và trường nào dùng cho consumer.

**Bài 3 — Null key.** Publish một record với null key; viết listener có `@Header(RECEIVED_KEY)` required và quan sát lỗi. Chuyển sang `required=false` rồi xác minh xử lý đúng.

**Bài 4 — ConsumerRecordMetadata.** Viết hai listener tương đương: một dùng `@Header` riêng lẻ, một dùng `ConsumerRecordMetadata`. So sánh topic/partition/offset của cùng record.

**Bài 5 — Producer output RecordMetadata.** Publish một message rồi xử lý `CompletableFuture<SendResult>`; log metadata output. Không đánh đồng offset output với offset input khi xây pipeline consume-transform-produce.

**Bài 6 — Raw vs JSON mapper.** Tạo header `x-attempts` dưới dạng String và Integer trong Spring Messaging. Kiểm tra bytes sau outbound conversion và type inbound tương ứng; sau đó gửi record raw không có `spring_json_header_types` để xem consumer nhận kiểu gì.

**Bài 7 — Jackson type headers.** Dùng JSON serializer với type metadata. Bật/tắt `remove.type.headers` ở deserializer phù hợp version, quan sát header hiện diện tại listener và viết contract `x-schema-version` độc lập.

**Bài 8 — Duplicate headers.** Gửi record chứa hai `x-route` headers, đọc bằng `headers(name)` và `lastHeader`. Nếu dùng Spring Kafka 4.x, cấu hình `setMultiValueHeaderPatterns(...)` rồi kiểm tra `List<?>` sau conversion.

**Bài 9 — DLT provenance.** Cố tình cho listener throw exception đến khi record vào DLT. Đối chiếu offset của DLT với `DLT_ORIGINAL_OFFSET`; sau đó re-drive DLT và xác minh vẫn giữ source identity mong đợi.

**Bài 10 — Mixed-version rollout.** Dùng hai phiên bản producer/consumer hoặc hai mapper configurations. Chạy các tổ hợp old→old, old→new, new→old, new→new với fixture có Unicode, null key và headers tùy chọn.

**Bài 11 — Batch listener.** Chuyển record listener thành batch listener, dùng danh sách metadata hoặc `List<ConsumerRecord>`. Xác minh header và offset của từng message không bị lệch khi có null key.

**Bài 12 — Runbook vận hành.** Thiết kế log errorCategory cho `MISSING_HEADER`, `TYPE_CONVERSION_FAILED`, `UNTRUSTED_TYPE`, `DLT_ORIGIN_MISSING`. Viết hướng dẫn rollback canary nếu tỉ lệ lỗi tăng sau upgrade.

## 29. Kết luận

Khi nâng cấp Spring Kafka, **header và record metadata là một phần của compatibility contract**, không phải chi tiết phụ của payload. Một thay đổi ở `KafkaHeaders`, header mapper, Jackson serializer/deserializer, batch listener hoặc DLT recoverer có thể làm ứng dụng đọc sai **key, offset, correlation ID, type metadata hoặc nguồn gốc của record lỗi** mà Kafka broker vẫn hoạt động bình thường.

Các nguyên tắc giúp nâng cấp an toàn:

- Phân biệt **native Kafka headers (`String` → `byte[]`)**, **Spring MessageHeaders** và **ConsumerRecord/RecordMetadata**.
- Dùng đúng tên constant KafkaHeaders theo phiên bản; đặc biệt chú ý các tên bị loại bỏ trong 3.0.
- Quy định header nghiệp vụ bằng **wire contract ổn định**: tên, codec, required/optional, duplicate policy và schema version.
- Hiểu rằng JSON type headers và header type mapping của Spring không tự thay thế business schema contract; chỉ trust package cần thiết.
- Trên Spring Kafka 4.x, kiểm tra Jackson 3 và cách cấu hình **multi-value header mapping** nếu dữ liệu dùng duplicate headers.
- Kiểm tra cả metadata của **record nhận**, **record gửi**, và **origin DLT** trong test và observability.
- Triển khai migration tương thích hai chiều khi rolling upgrade, kiểm tra backlog/retention trước khi xóa fallback.

Một bài test chỉ chứng minh payload JSON không lỗi là chưa đủ. Reliability của Kafka còn phụ thuộc việc producer và consumer hiểu cùng một ý nghĩa về headers, offsets, schema, retry và record provenance qua nhiều phiên bản ứng dụng.

### Tài liệu tham khảo

- [Spring Kafka Reference — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring Kafka Reference — Listener Annotation / Consumer Record Metadata](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Kafka Reference — Sending Messages / SendResult](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka Reference — Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring Kafka Reference — Change History (KafkaHeaders, Jackson 3, multi-value headers)](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Spring Kafka Reference — Handling Exceptions and Dead-letter Headers](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Non-blocking Retry Header Management](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html)
- [Spring Kafka Javadoc — KafkaHeaders](https://docs.spring.io/spring-kafka/docs/4.0.0/api/org/springframework/kafka/support/KafkaHeaders.html)
- [Apache Kafka — Record Headers API](https://kafka.apache.org/40/javadoc/org/apache/kafka/common/header/Headers.html)
