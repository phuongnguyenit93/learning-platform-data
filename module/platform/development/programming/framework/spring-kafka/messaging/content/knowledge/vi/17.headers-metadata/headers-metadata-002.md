# Đọc header trong listener

Kafka record không chỉ có key và value. Mỗi record còn có thể mang các header để truyền thông tin phụ trợ như trace ID, correlation ID, tenant ID, schema version hoặc nguồn phát sinh. Spring Kafka cung cấp nhiều cách đọc các giá trị này trong `@KafkaListener`: dùng `@Header`, `@Headers`, `Message<?>` hoặc truy cập trực tiếp `ConsumerRecord.headers()`.

Chọn cách đọc phù hợp giúp listener nhận đúng kiểu dữ liệu, tránh lỗi khi header không tồn tại và giữ được metadata cần thiết để truy vết. Cần phân biệt **Kafka record header do producer gửi** với **header metadata mà Spring Kafka tạo khi nhận record**.

## 1. Header nằm ở đâu trong Kafka record?

Một Kafka record có các thành phần chính:

- **Key**: dùng để định tuyến record tới partition và hỗ trợ xử lý theo thực thể.
- **Value**: payload chứa dữ liệu nghiệp vụ.
- **Headers**: tập hợp cặp tên và byte array để mang metadata bổ sung.
- **Metadata của record**: topic, partition, offset, timestamp do Kafka quản lý.

Kafka header có API đơn giản:

```java
public interface Header {
    String key();
    byte[] value();
}
```

Tên header là String, còn giá trị trên wire luôn là `byte[]`. Kafka không tự hiểu một header là String, Integer, UUID hay JSON. Producer và consumer phải thống nhất cách mã hóa và giải mã.

Ví dụ record có thể mang:

| Thành phần | Giá trị ví dụ |
|---|---|
| Key | `order-42` |
| Value | JSON của `OrderCreated` |
| `trace-id` | `trace-9f31` được mã hóa UTF-8 |
| `tenant-id` | `tenant-7` được mã hóa UTF-8 |
| `schema-version` | `2` được mã hóa thành byte |

Header không thay thế payload. Không nên đưa toàn bộ dữ liệu nghiệp vụ vào header; hãy giữ header nhỏ, ổn định và dành cho metadata cần thiết.

## 2. Phân biệt custom header và KafkaHeaders

Có hai nhóm header thường gặp trong listener:

1. **Custom header** là header do ứng dụng hoặc producer gửi, ví dụ `trace-id`, `tenant-id`, `event-version`.
2. **KafkaHeaders** là các header Spring Kafka tạo để biểu diễn thông tin của record nhận được, ví dụ topic, key, partition, offset và timestamp.

Các hằng số thường dùng trong Spring Kafka 3.x:

| Hằng số | Ý nghĩa |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Topic nhận record |
| `KafkaHeaders.RECEIVED_KEY` | Key của record nhận được |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition chứa record |
| `KafkaHeaders.OFFSET` | Offset của record |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp của record |
| `KafkaHeaders.TIMESTAMP_TYPE` | Loại timestamp do Kafka cung cấp |
| `KafkaHeaders.NATIVE_HEADERS` | Kafka `Headers` gốc khi không có header mapper |
| `KafkaHeaders.BATCH_CONVERTED_HEADERS` | Danh sách header đã chuyển đổi trong batch listener |

Dùng hằng số `KafkaHeaders` thay vì tự viết chuỗi nội bộ như `kafka_receivedTopic`. Hằng số giúp code rõ ý định và giảm lỗi đánh máy.

`RECEIVED_KEY` có thể không tồn tại khi record có key null. Từ Spring Kafka 2.5, framework không đưa header này vào `MessageHeaders` nếu key của record là null. Vì vậy, tham số nhận key nên được khai báo là tùy chọn.

## 3. Đọc metadata bằng @Header

Với listener dạng payload, có thể lấy metadata bằng annotation `@Header`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(
    topics = "order-events",
    groupId = "billing-service"
)
public void handle(
        @Payload OrderCreated event,
        @Header(value = KafkaHeaders.RECEIVED_KEY, required = false) String orderKey,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(KafkaHeaders.RECEIVED_TIMESTAMP) long timestamp) {

    // Xử lý event và sử dụng metadata để truy vết.
}
```

Spring Kafka ánh xạ metadata của `ConsumerRecord` thành message headers để method argument resolver có thể bind vào tham số.

Một số lưu ý:

- `@Payload` đánh dấu tham số chứa value đã deserialize/convert.
- `@Header` lấy một header theo tên.
- Kiểu tham số phải tương thích với giá trị header sau khi mapping.
- `partition` và `offset` là metadata của Kafka, không phải custom header producer tự đặt.
- Nếu không cần timestamp, không phải khai báo tham số này.

Có thể nhận timestamp type nếu cần phân biệt timestamp do producer tạo và timestamp do broker append:

```java
import org.apache.kafka.common.record.TimestampType;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.TIMESTAMP_TYPE) TimestampType timestampType) {

    // CREATE_TIME hoặc LOG_APPEND_TIME tùy cấu hình topic/broker.
}
```

`TimestampType` là enum của Kafka. Hãy kiểm tra kiểu thực tế của tham số thay vì mặc định chuyển mọi header thành String.

## 4. Xử lý header không bắt buộc

Không phải record nào cũng có đầy đủ header. Ví dụ producer có thể không gửi key hoặc hệ thống cũ chưa gửi `trace-id`.

Nếu header có thể vắng mặt, dùng `required = false`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(
            value = KafkaHeaders.RECEIVED_KEY,
            required = false
        ) String orderKey,
        @Header(
            value = "trace-id",
            required = false
        ) byte[] traceIdBytes) {

    if (traceIdBytes == null || traceIdBytes.length == 0) {
        // Tạo correlation context nội bộ nếu chính sách cho phép.
    }

    // Xử lý event.
}
```

Có thể dùng `defaultValue` khi một giá trị mặc định thực sự hợp lệ:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(
            value = "source-system",
            defaultValue = "legacy"
        ) String sourceSystem) {

    // Xử lý theo sourceSystem.
}
```

Khi khai báo `defaultValue`, Spring xem header là không bắt buộc. Chỉ dùng giá trị mặc định nếu nó có ý nghĩa nghiệp vụ. Không dùng chuỗi mặc định giả như `unknown` cho một header bắt buộc về bảo mật hoặc tenant, vì có thể khiến record sai dữ liệu được xử lý như hợp lệ.

Với header quan trọng, hãy validate ngay đầu listener hoặc trong lớp chuyển đổi request.

## 5. Producer gửi custom header như thế nào?

Kafka producer có thể thêm header vào `ProducerRecord` trước khi gửi:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

ProducerRecord<String, String> record =
    new ProducerRecord<>(
        "order-events",
        "order-42",
        "{\"orderId\":\"order-42\"}"
    );

record.headers().add(
    new RecordHeader(
        "trace-id",
        "trace-9f31".getBytes(StandardCharsets.UTF_8)
    )
);

record.headers().add(
    new RecordHeader(
        "tenant-id",
        "tenant-7".getBytes(StandardCharsets.UTF_8)
    )
);

kafkaTemplate.send(record);
```

Producer tạo `RecordHeader` với giá trị byte array. Consumer phải biết header `trace-id` và `tenant-id` dùng UTF-8 để giải mã đúng.

Nếu dùng Spring `Message<?>` để gửi qua `KafkaTemplate`, header Spring Messaging có thể được `KafkaHeaderMapper` chuyển thành Kafka header. Cách mapping phụ thuộc mapper đang được cấu hình; phần 9 giải thích chi tiết.

## 6. Đọc custom header bằng @Header

Nếu header đã được Spring Kafka header mapper chuyển đổi sang kiểu Java phù hợp, có thể nhận trực tiếp bằng `@Header`:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(value = "trace-id", required = false) byte[] traceIdBytes) {

    String traceId = traceIdBytes == null
        ? null
        : new String(traceIdBytes, StandardCharsets.UTF_8);

    // Gắn traceId vào log hoặc tracing context.
}
```

Ví dụ trên nhận byte array để thể hiện rõ trường hợp header đến từ producer Kafka thuần, không có type metadata của Spring. Nếu ứng dụng cấu hình mapper chuyển raw header sang String, tham số có thể khai báo `String`.

Không nên ép kiểu một cách mù quáng:

```java
String traceId = (String) message.getHeaders().get("trace-id");
```

Header có thể đang là `byte[]`, `String`, `Integer` hoặc một kiểu khác tùy mapper và producer. Hãy xác định wire format và cấu hình mapper thống nhất giữa các service.

## 7. Đọc toàn bộ header bằng @Headers

Khi listener cần nhiều custom header hoặc cần xử lý linh hoạt theo metadata, dùng `@Headers` để nhận map:

```java
import java.util.Map;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Headers Map<String, Object> headers) {

    Object traceId = headers.get("trace-id");
    Object tenantId = headers.get("tenant-id");
    Object source = headers.get("source-system");

    // Kiểm tra kiểu và giá trị trước khi sử dụng.
}
```

Map chứa các header đã được Spring header mapper chuyển đổi. Nó hữu ích khi số lượng custom header thay đổi theo loại event hoặc khi cần truyền metadata tới lớp xử lý.

Không nên giả định mọi key trong map đều tồn tại. Dùng `containsKey`, kiểm tra null và kiểm tra kiểu trước khi ép kiểu.

Nếu chỉ cần một hoặc hai header cố định, `@Header` thường dễ đọc hơn. Nếu cần truy cập nhiều header, `@Headers` giúp giảm số tham số của method.

## 8. Đọc header qua Message<?> và MessageHeaders

Listener cũng có thể nhận Spring `Message<T>`. Payload và metadata nằm trong cùng một object:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;

@KafkaListener(topics = "order-events")
public void handle(Message<OrderCreated> message) {
    OrderCreated event = message.getPayload();

    MessageHeaders headers = message.getHeaders();

    String topic = headers.get(
        KafkaHeaders.RECEIVED_TOPIC,
        String.class
    );

    Integer partition = headers.get(
        KafkaHeaders.RECEIVED_PARTITION,
        Integer.class
    );

    Long offset = headers.get(
        KafkaHeaders.OFFSET,
        Long.class
    );

    Object traceId = headers.get("trace-id");

    // Chuyển event và metadata cần thiết cho tầng nghiệp vụ.
}
```

Cách này hữu ích khi cần truyền cả payload và metadata qua một lớp adapter hoặc một pipeline Spring Messaging. `MessageHeaders` là cấu trúc header của Spring, không phải Kafka `Headers` gốc.

`MessageHeaders` được thiết kế bất biến. Không sửa map header trực tiếp; nếu cần tạo message mới với header bổ sung hoặc thay đổi, hãy dùng `MessageBuilder`.

## 9. KafkaHeaderMapper chuyển đổi header như thế nào?

Kafka native header chỉ lưu `byte[]`, còn Spring `MessageHeaders` có thể chứa nhiều kiểu Java. `KafkaHeaderMapper` là cầu nối giữa hai cấu trúc này.

Hai mapper thường gặp trong Spring Kafka 3.x:

| Mapper | Hành vi |
|---|---|
| `DefaultKafkaHeaderMapper` | Chuyển header phong phú bằng JSON và lưu type metadata để khôi phục kiểu Java |
| `SimpleKafkaHeaderMapper` | Ánh xạ header thô dưới dạng `byte[]`, có tùy chọn chuyển một số header thành String |

Với `DefaultKafkaHeaderMapper`, Spring dùng header đặc biệt `spring_json_header_types` để lưu thông tin kiểu của các header được serialize. Khi consumer đọc record được gửi bởi một ứng dụng Spring tương thích, mapper có thể khôi phục kiểu Java ban đầu.

Với producer ngoài Spring hoặc producer chỉ thêm `RecordHeader` bằng byte array, header có thể được nhận dưới dạng byte array vì không có type metadata của Spring. Đây là lý do nên thống nhất định dạng header ở cấp giao tiếp giữa các service.

Trong Spring Kafka 3.x, `DefaultKafkaHeaderMapper` thường được dùng mặc định trong `MessagingMessageConverter` và `BatchMessagingMessageConverter` nếu Jackson có trên classpath. Với Spring Kafka 4.x, API mapper JSON được đổi tên thành `JsonKafkaHeaderMapper`; hãy chọn đúng class theo version đang dùng.

### Cấu hình mapper tường minh

Có thể cấu hình mapper để chỉ gửi những header được cho phép:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.DefaultKafkaHeaderMapper;
import org.springframework.kafka.support.KafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
public class KafkaHeaderConfiguration {

    @Bean
    KafkaHeaderMapper kafkaHeaderMapper() {
        return new DefaultKafkaHeaderMapper(
            "!id",
            "!timestamp",
            "trace-*",
            "tenant-id",
            "source-system"
        );
    }

    @Bean
    RecordMessageConverter kafkaRecordMessageConverter(
            KafkaHeaderMapper kafkaHeaderMapper) {
        MessagingMessageConverter converter = new MessagingMessageConverter();
        converter.setHeaderMapper(kafkaHeaderMapper);
        return converter;
    }
}
```

Các pattern được xét theo thứ tự; pattern đầu tiên khớp sẽ quyết định header có được mapping hay không. Khi tự cấu hình pattern, nên loại `id` và `timestamp` của Spring Messaging vì đây là header nội bộ, không phải metadata nghiệp vụ để gửi sang Kafka. Bean mapper phải được gắn vào `MessagingMessageConverter`; sau đó converter này phải được dùng bởi listener container factory. Với record listener, gọi `factory.setRecordMessageConverter(kafkaRecordMessageConverter)`. Với batch listener, bọc nó bằng `new BatchMessagingMessageConverter(kafkaRecordMessageConverter)` rồi truyền vào `factory.setBatchMessageConverter(...)`. Chỉ khai báo mapper bean mà không gắn vào converter thì chưa thay đổi luồng mapping.

`DefaultKafkaHeaderMapper` chỉ deserialize các kiểu thuộc những package được tin cậy. Nếu cần khôi phục kiểu header tùy chỉnh, hãy thêm đúng package bằng `addTrustedPackages(...)`. Tránh tin cậy tất cả package bằng `*` khi nhận record từ nguồn không kiểm soát.

Nếu dùng Spring Kafka 4.x, thay `DefaultKafkaHeaderMapper` bằng `JsonKafkaHeaderMapper` tương ứng.

Không mở mapping tất cả header một cách tùy tiện nếu message có thể chứa token, thông tin cá nhân hoặc metadata nội bộ. Chỉ map những header cần truyền qua Kafka.

## 10. Đọc native Kafka Headers qua ConsumerRecord

Khi cần truy cập chính xác Kafka header gốc, nhận `ConsumerRecord<K,V>` trong listener:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "order-events")
public void handle(ConsumerRecord<String, OrderCreated> record) {
    Header traceHeader = record.headers().lastHeader("trace-id");

    String traceId = traceHeader == null || traceHeader.value() == null
        ? null
        : new String(traceHeader.value(), StandardCharsets.UTF_8);

    String topic = record.topic();
    int partition = record.partition();
    long offset = record.offset();

    OrderCreated event = record.value();

    // Dùng raw header và metadata của record.
}
```

`ConsumerRecord.headers()` trả về Kafka `Headers` gốc. Cách này phù hợp khi:

- Cần đọc byte array chính xác như producer đã gửi.
- Cần xử lý header do hệ thống không dùng Spring tạo ra.
- Cần xử lý nhiều header trùng tên.
- Cần truy cập metadata gốc mà không phụ thuộc `KafkaHeaderMapper`.

Nếu listener chỉ cần payload và một vài metadata, `@Header` thường ngắn gọn hơn. `ConsumerRecord` hữu ích khi cần toàn quyền kiểm soát record.

## 11. Header trùng tên và nhiều giá trị

Kafka cho phép một record có nhiều header cùng tên. Ví dụ producer có thể gửi hai giá trị `route-tag`:

```java
record.headers()
    .add(new RecordHeader("route-tag", "blue".getBytes(StandardCharsets.UTF_8)))
    .add(new RecordHeader("route-tag", "priority".getBytes(StandardCharsets.UTF_8)));
```

Khi đọc native Kafka Headers:

```java
Iterable<Header> routeHeaders =
    record.headers().headers("route-tag");

for (Header header : routeHeaders) {
    String value = new String(
        header.value(),
        StandardCharsets.UTF_8
    );
}
```

`lastHeader("route-tag")` chỉ trả về header cuối cùng có tên đó. Dùng `headers("route-tag")` nếu cần đọc tất cả giá trị.

Việc mapping nhiều header cùng tên sang Spring `MessageHeaders` phụ thuộc version và cấu hình mapper. Hỗ trợ mapping multi-value được bổ sung trong Spring Kafka 4.0 thông qua các pattern multi-value của JSON header mapper. Ở các version trước, không giả định `@Header` hoặc `Map<String,Object>` sẽ giữ nguyên tất cả header trùng tên; dùng `ConsumerRecord.headers()` khi cần bảo toàn từng occurrence.

## 12. Khi không có header mapper: NATIVE_HEADERS

Nếu không có header mapper, Spring Kafka có thể đặt Kafka `Headers` gốc vào `KafkaHeaders.NATIVE_HEADERS` thay vì chuyển đổi từng header thành Spring `MessageHeaders`.

Ví dụ:

```java
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.NATIVE_HEADERS) Headers nativeHeaders) {

    Header traceHeader = nativeHeaders.lastHeader("trace-id");

    // Giải mã byte[] theo wire format của ứng dụng.
}
```

`NATIVE_HEADERS` là lựa chọn khi cần lấy toàn bộ header Kafka chưa được map. Trong batch listener, cấu trúc native headers có thể là danh sách `Headers`, tương ứng với vị trí payload trong batch.

Nếu mapper đã hoạt động, ưu tiên dùng `@Header`, `@Headers` hoặc `MessageHeaders` theo kiểu dữ liệu đã mapping. Đừng giả định `NATIVE_HEADERS` luôn có mặt trong mọi cấu hình.

## 13. ConsumerRecordMetadata khi chỉ cần metadata

Nếu method cần topic, partition, offset và timestamp nhưng không cần key, value hoặc raw headers, Spring Kafka cung cấp `ConsumerRecordMetadata`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.adapter.ConsumerRecordMetadata;

@KafkaListener(topics = "order-events")
public void handle(
        OrderCreated event,
        ConsumerRecordMetadata metadata) {

    String topic = metadata.topic();
    int partition = metadata.partition();
    long offset = metadata.offset();
    long timestamp = metadata.timestamp();

    // Xử lý event cùng metadata.
}
```

`ConsumerRecordMetadata` có từ Spring Kafka 2.5 và chứa metadata của record, ngoại trừ key và value. Nếu cần đọc custom headers, vẫn phải dùng `@Header`, `@Headers`, `Message<?>` hoặc `ConsumerRecord`.

Cách này giúp chữ ký listener gọn khi chỉ cần metadata kỹ thuật mà không cần khai báo nhiều `@Header`.

## 14. Validation và xử lý header

Header là dữ liệu đầu vào từ producer. Không nên tin cậy chúng chỉ vì tên header có vẻ hợp lệ.

Ví dụ kiểm tra tenant ID và trace ID:

Đoạn code giả định producer gửi hai header dưới dạng byte array UTF-8 thô, như ví dụ ở phần 5.

```java
import java.nio.charset.StandardCharsets;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "order-events")
public void handle(
        @Payload OrderCreated event,
        @Header(value = "tenant-id", required = false) byte[] tenantIdBytes,
        @Header(value = "trace-id", required = false) byte[] traceIdBytes) {

    String tenantId = tenantIdBytes == null
        ? null
        : new String(tenantIdBytes, StandardCharsets.UTF_8);

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Missing tenant-id header");
    }

    if (tenantId.length() > 80) {
        throw new IllegalArgumentException("Invalid tenant-id header");
    }

    String traceId = traceIdBytes == null
        ? null
        : new String(traceIdBytes, StandardCharsets.UTF_8);

    // Tiếp tục xử lý sau khi xác thực metadata.
}
```

Các nguyên tắc nên áp dụng:

- Validate header bắt buộc trước khi dùng nó để định tuyến hoặc phân quyền.
- Giới hạn độ dài và tập ký tự nếu header được dùng trong log, URL hoặc query.
- Không dùng `tenant-id` từ header làm căn cứ cấp quyền nếu chưa đối chiếu với danh tính đã xác thực.
- Không ghi token, mật khẩu hoặc dữ liệu cá nhân nhạy cảm vào log.
- Xử lý trường hợp header null, sai encoding hoặc sai kiểu.
- Giữ tên header và wire format ổn định giữa các phiên bản service.

Nếu header không hợp lệ, hãy ném exception phù hợp để listener error handler áp dụng retry, recoverer hoặc DLT theo chính sách. Lỗi dữ liệu sai vĩnh viễn thường không có ích khi retry vô hạn.

## 15. Kiểm thử đọc custom header

Có thể dùng Embedded Kafka để xác minh producer gửi raw header và listener đọc đúng byte array. Ví dụ listener capture record vào queue:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class HeaderCaptureListener {

    private final BlockingQueue<ConsumerRecord<String, String>> records =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "header-capture",
        topics = "audit-events",
        groupId = "header-capture-test"
    )
    public void capture(ConsumerRecord<String, String> record) {
        records.add(record);
    }

    public ConsumerRecord<String, String> poll(
            long timeout,
            TimeUnit unit) throws InterruptedException {
        return records.poll(timeout, unit);
    }
}
```

Test gửi record có header:

```java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.ContainerTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "audit-events",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaHeaderListenerTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private HeaderCaptureListener capture;

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @BeforeEach
    void waitForAssignment() {
        ContainerTestUtils.waitForAssignment(
            registry.getListenerContainer("header-capture"),
            1
        );
    }

    @Test
    void readsTraceIdFromNativeHeader() throws Exception {
        ProducerRecord<String, String> record =
            new ProducerRecord<>(
                "audit-events",
                "order-42",
                "{\"orderId\":\"order-42\"}"
            );

        record.headers().add(
            new RecordHeader(
                "trace-id",
                "trace-9f31".getBytes(StandardCharsets.UTF_8)
            )
        );

        kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> received =
            capture.poll(10, TimeUnit.SECONDS);

        assertThat(received).isNotNull();

        String traceId = new String(
            received.headers().lastHeader("trace-id").value(),
            StandardCharsets.UTF_8
        );

        assertThat(traceId).isEqualTo("trace-9f31");
    }
}
```

Test cần dùng serializer/deserializer tương thích với `KafkaTemplate<String,String>` và consumer. Nếu dự án dùng cấu hình Spring Boot chung, hãy bảo đảm listener test dùng group ID riêng và topic test riêng. `waitForAssignment` tránh gửi record trước khi consumer đã nhận partition.

Các trường hợp nên kiểm thử thêm:

- Header không tồn tại.
- Header có giá trị byte array rỗng hoặc sai encoding.
- Header trùng tên.
- Header có giá trị không đúng wire format.
- `@Header(required = false)` hoạt động đúng khi thiếu header.
- Mapper khôi phục kiểu Java đúng khi producer và consumer đều dùng Spring mapper.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@Header` báo thiếu header | Producer không gửi hoặc tên header sai | Kiểm tra tên header và dùng `required=false` nếu tùy chọn |
| Nhận `byte[]` thay vì String | Raw Kafka header chưa có type metadata hoặc mapper trả raw bytes | Giải mã UTF-8 hoặc cấu hình mapper |
| `RECEIVED_KEY` không tồn tại | Record được gửi với key null | Đánh dấu tham số là tùy chọn |
| Header custom không xuất hiện trong `MessageHeaders` | Mapper pattern loại header hoặc mapper chưa được gắn vào converter | Kiểm tra `KafkaHeaderMapper` và pattern |
| Ép kiểu header gây `ClassCastException` | Producer và consumer không thống nhất kiểu/wire format | Xác định rõ kiểu byte và quy tắc mapping |
| Chỉ đọc được một header trùng tên | `lastHeader()` chỉ lấy occurrence cuối hoặc mapper gộp giá trị | Dùng `headers(name)` trên `ConsumerRecord` |
| Không có `KafkaHeaders.NATIVE_HEADERS` | Header mapper đang chuyển native headers thành Spring headers | Dùng `@Header`/`@Headers` hoặc cấu hình mapper |
| Type metadata không được khôi phục | Producer không gửi `spring_json_header_types` hoặc package không được tin cậy | Dùng wire format đơn giản hoặc cấu hình trusted packages cụ thể |

## 17. Checklist thiết kế header

- Phân biệt custom header với metadata do Kafka/Spring Kafka tạo.
- Dùng hằng số `KafkaHeaders` cho topic, key, partition, offset và timestamp.
- Thống nhất encoding, thường là UTF-8 cho header dạng text.
- Dùng `required=false` khi header thực sự có thể vắng mặt.
- Chọn `@Header`, `@Headers`, `Message<?>` hay `ConsumerRecord` theo nhu cầu.
- Hiểu rõ mapper đang chuyển header thành String, byte array hay kiểu Java khác.
- Dùng native `Headers` khi cần giữ các header trùng tên.
- Giới hạn pattern mapping và trusted packages.
- Validate header trước khi dùng cho tenant, routing hoặc security.
- Không lưu bí mật hoặc payload lớn trong header.
- Kiểm thử header thiếu, sai kiểu, trùng tên và khác phiên bản.

## 18. Ghi nhớ

- Kafka header lưu tên và giá trị byte array; Kafka không tự quy định kiểu Java cho giá trị.
- `@Header` lấy một header; `@Headers` lấy map header; `Message<?>` giữ payload và metadata.
- `KafkaHeaders.RECEIVED_*` biểu diễn metadata của record nhận được.
- `ConsumerRecord.headers()` cho phép đọc Kafka header gốc và xử lý nhiều occurrence cùng tên.
- `KafkaHeaderMapper` quyết định cách chuyển native Kafka headers thành Spring `MessageHeaders`.
- `DefaultKafkaHeaderMapper` thường dùng trong Spring Kafka 3.x; Spring Kafka 4.x dùng `JsonKafkaHeaderMapper`.
- Header không bắt buộc phải có; cần xử lý null, sai kiểu và encoding không hợp lệ.
- Header là dữ liệu đầu vào, cần validation và chính sách bảo mật như payload.

Khi hiểu rõ wire format, header mapper và các cách bind tham số, listener có thể đọc metadata và custom header một cách an toàn. Điều này giúp truyền trace ID, tenant ID và thông tin định tuyến qua Kafka mà vẫn giữ được ranh giới rõ ràng giữa payload, header ứng dụng và metadata của broker.

