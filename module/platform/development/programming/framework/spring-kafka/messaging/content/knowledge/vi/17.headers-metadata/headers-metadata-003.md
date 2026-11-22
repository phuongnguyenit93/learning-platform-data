# Gửi header bằng KafkaTemplate

Kafka record không chỉ có key và value. Record còn có thể mang **headers** để truyền metadata đi cùng payload, chẳng hạn `trace-id`, `correlation-id`, loại sự kiện, phiên bản hợp đồng hoặc nguồn phát sinh. Với Spring Kafka, có thể gửi header bằng cách tạo `ProducerRecord` rồi gọi `KafkaTemplate.send()`, hoặc tạo Spring `Message<?>` và gửi trực tiếp qua `KafkaTemplate`.

Headers hữu ích khi consumer cần thông tin phục vụ định tuyến, quan sát, tương quan request hoặc xử lý phiên bản mà không phải nhúng tất cả metadata vào JSON payload. Cần phân biệt Kafka headers với Spring Message headers: Kafka lưu header dưới dạng tên và mảng byte, còn Spring Message có thể chứa nhiều kiểu Java và cần converter/header mapper để chuyển đổi.

## 1. Kafka record gồm những thành phần nào?

Một Kafka record có các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| Topic | Nơi record được ghi |
| Partition | Phân vùng chứa record |
| Key | Dữ liệu thường dùng để chọn partition và nhận diện thực thể |
| Value | Payload nghiệp vụ, thường là JSON hoặc byte |
| Timestamp | Thời điểm gắn với record theo cấu hình topic |
| Headers | Metadata bổ sung dưới dạng các cặp tên và byte value |

Ví dụ record sự kiện thanh toán:

```text
topic: payments.events
key: payment-9001
value: {"paymentId":"payment-9001","amount":250000}
headers:
  trace-id: 8d7a...
  correlation-id: checkout-123
  event-type: PaymentCompleted
  schema-version: 2
```

Headers là metadata của record, nằm ngoài value. Thêm `trace-id` không làm thay đổi JSON payload, key hoặc offset. Việc chọn partition thông thường vẫn dựa trên key và partitioner; header chỉ ảnh hưởng đến partition nếu ứng dụng tự viết partitioner để đọc header.

## 2. Kafka headers là byte array

Ở Kafka client, một header được biểu diễn bằng `org.apache.kafka.common.header.Header`, gồm:

- `key()`: tên header dạng chuỗi.
- `value()`: giá trị dạng `byte[]`, có thể là `null`.

Một record có thể chứa nhiều header trùng tên. `Headers` giữ các header theo thứ tự thêm vào; consumer có thể lấy header cuối cùng bằng `lastHeader(name)` hoặc duyệt tất cả bằng `headers(name)`.

Do giá trị là byte, producer và consumer cần thống nhất cách mã hóa. Với metadata văn bản, UTF-8 là lựa chọn phổ biến. Với dữ liệu nhị phân, giữ nguyên byte và dùng định dạng đã thỏa thuận.

```java
byte[] traceBytes = traceId.getBytes(StandardCharsets.UTF_8);
```

Không nên truyền trực tiếp một object Java tùy ý vào Kafka header. Hãy serialize giá trị đó thành byte theo một định dạng rõ ràng, hoặc dùng Spring Kafka header mapper khi gửi Spring `Message<?>`.

## 3. Gửi header bằng ProducerRecord và KafkaTemplate

Cách trực tiếp nhất là tạo `ProducerRecord`, thêm `RecordHeader` rồi gửi bằng `KafkaTemplate`. Cách này cho phép kiểm soát chính xác tên header, byte value và các header trùng tên.

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class PaymentEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    PaymentEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String paymentId, String json, String traceId) {
        var record = new ProducerRecord<>(
                "payments.events",
                paymentId,
                json
        );

        record.headers().add(new RecordHeader(
                "trace-id",
                traceId.getBytes(StandardCharsets.UTF_8)
        ));
        record.headers().add(new RecordHeader(
                "event-type",
                "PaymentCompleted".getBytes(StandardCharsets.UTF_8)
        ));

        kafkaTemplate.send(record);
    }
}
```

`ProducerRecord` chứa topic, key, value và headers. Constructor ba tham số trong ví dụ để Kafka partitioner chọn partition dựa trên key. Nếu cần chỉ định partition hoặc timestamp, có thể dùng constructor tương ứng của `ProducerRecord`.

Với Spring Kafka 3.x, `KafkaTemplate.send()` trả về `CompletableFuture<SendResult<K, V>>`; các phiên bản cũ có thể dùng `ListenableFuture`. Trong ứng dụng thực tế, hãy quan sát kết quả bất đồng bộ để phát hiện lỗi serialize, lỗi broker hoặc lỗi gửi. Không xem việc gọi `send()` là bằng chứng record đã được broker ghi thành công.

### Thêm nhiều header cùng tên

Kafka cho phép nhiều header trùng tên. Ví dụ, nếu một record có nhiều tag:

```java
record.headers().add(new RecordHeader(
        "tag", "priority".getBytes(StandardCharsets.UTF_8)));
record.headers().add(new RecordHeader(
        "tag", "customer-facing".getBytes(StandardCharsets.UTF_8)));
```

Consumer có thể đọc tất cả giá trị `tag`. Không nên giả định tên header luôn duy nhất trong một record; hãy quy định rõ ứng dụng muốn lấy giá trị đầu tiên, cuối cùng hay toàn bộ danh sách.

## 4. Gửi header bằng Spring Message và KafkaHeaders

Spring Kafka hỗ trợ gửi một Spring `Message<?>` qua `KafkaTemplate.send(message)`. Cách này phù hợp khi ứng dụng đang sử dụng Spring Messaging và muốn biểu diễn topic, key, partition cùng metadata dưới dạng message headers.

Các hằng số thường dùng trong `KafkaHeaders`:

| Hằng số | Mục đích |
|---|---|
| `KafkaHeaders.TOPIC` | Topic đích |
| `KafkaHeaders.MESSAGE_KEY` | Key của Kafka record |
| `KafkaHeaders.PARTITION` | Partition đích nếu muốn chỉ định rõ |
| `KafkaHeaders.TIMESTAMP` | Timestamp của record nếu cần chỉ định |
| `KafkaHeaders.CORRELATION_ID` | Correlation ID dùng trong request/reply hoặc tương quan thông điệp |

Ví dụ gửi message với custom headers:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class SpringMessagePaymentPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    SpringMessagePaymentPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String paymentId, String json, String traceId) {
        Message<String> message = MessageBuilder
                .withPayload(json)
                .setHeader(KafkaHeaders.TOPIC, "payments.events")
                .setHeader(KafkaHeaders.MESSAGE_KEY, paymentId)
                .setHeader(KafkaHeaders.CORRELATION_ID, "checkout-123")
                .setHeader("trace-id", traceId)
                .setHeader("event-type", "PaymentCompleted")
                .build();

        kafkaTemplate.send(message);
    }
}
```

`KafkaHeaders.TOPIC` và `KafkaHeaders.MESSAGE_KEY` là metadata điều khiển việc tạo `ProducerRecord`. Các header tùy chỉnh như `trace-id` và `event-type` được chuyển thành Kafka record headers thông qua `RecordMessageConverter` và header mapper được cấu hình cho template.

Không nhầm `KafkaHeaders.MESSAGE_KEY` với custom header tên `message-key`. Dùng các hằng số `KafkaHeaders` giúp Spring Kafka hiểu trường nào điều khiển topic, key, partition hoặc timestamp; các tên tự đặt còn lại là metadata ứng dụng.

## 5. Spring Message headers và Kafka record headers khác nhau

Spring `Message<?>` có payload và một map headers của Spring Messaging. Các giá trị trong map có thể là `String`, `UUID`, `Long`, object hoặc kiểu khác. Kafka record headers chỉ lưu byte array. Converter/header mapper chịu trách nhiệm chuyển đổi giữa hai mô hình.

| Đặc điểm | Spring Message header | Kafka record header |
|---|---|---|
| Kiểu giá trị | Object Java | `byte[]` hoặc `null` |
| Phạm vi | Trong ứng dụng Spring Messaging | Được lưu cùng record trong Kafka |
| Chuyển đổi | Có thể giữ kiểu Java trong runtime | Phải encode/serialize thành byte |
| Nhiều giá trị cùng tên | Map header thông thường có một giá trị cho mỗi key | Có thể có nhiều header cùng tên |

Khi dùng `KafkaTemplate.send(Message<?>)`, template sử dụng `RecordMessageConverter` để chuyển Spring Message thành Kafka `ProducerRecord`. Header mapper được converter sử dụng quyết định cách ánh xạ custom headers.

Với metadata văn bản, nên dùng giá trị `String` và kiểm tra mapper đang dùng có ánh xạ các header đó hay không. Với header object phức tạp, `DefaultKafkaHeaderMapper` có thể serialize giá trị và mang thêm metadata kiểu để khôi phục object khi đi qua Spring Kafka. Khi giao tiếp với ứng dụng không dùng Spring, ưu tiên header dạng chuỗi/byte với encoding và schema rõ ràng.

Nếu cần kiểm soát mapping, có thể cấu hình `MessagingMessageConverter` riêng và gắn `KafkaHeaderMapper` phù hợp. API và mapper mặc định có thể khác theo phiên bản Spring Kafka; hãy kiểm tra converter thực tế của `KafkaTemplate` trong ứng dụng trước khi dựa vào hành vi ánh xạ tự động.

Ví dụ dưới đây dùng `SimpleKafkaHeaderMapper` cho custom headers dạng `String` và `byte[]`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Configuration
class KafkaMessageConverterConfiguration {

    @Bean
    RecordMessageConverter kafkaRecordMessageConverter() {
        var converter = new MessagingMessageConverter();
        converter.setHeaderMapper(new SimpleKafkaHeaderMapper());
        return converter;
    }
}
```

Gắn converter này vào `KafkaTemplate` mà ứng dụng sử dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;

@Bean
KafkaTemplate<String, String> kafkaTemplate(
        ProducerFactory<String, String> producerFactory,
        RecordMessageConverter kafkaRecordMessageConverter
) {
    var template = new KafkaTemplate<>(producerFactory);
    template.setMessageConverter(kafkaRecordMessageConverter);
    return template;
}
```

Nếu custom header chứa `UUID`, số hoặc object phức tạp, hãy chọn mapper có khả năng chuyển đổi kiểu đó, ví dụ `DefaultKafkaHeaderMapper`, và thống nhất cách giải mã ở consumer. Với ứng dụng ngoài Spring, ưu tiên chuỗi UTF-8 hoặc byte theo hợp đồng chung để không phụ thuộc metadata kiểu riêng của Spring.

## 6. Đọc custom headers ở consumer

Khi listener nhận `ConsumerRecord`, có thể đọc trực tiếp Kafka headers. Ví dụ:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class PaymentEventListener {

    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void consume(ConsumerRecord<String, String> record) {
        String traceId = readUtf8Header(record, "trace-id");
        String eventType = readUtf8Header(record, "event-type");

        process(record.key(), record.value(), traceId, eventType);
    }

    private String readUtf8Header(
            ConsumerRecord<String, String> record,
            String name
    ) {
        Header header = record.headers().lastHeader(name);
        if (header == null || header.value() == null) {
            return null;
        }
        return new String(header.value(), StandardCharsets.UTF_8);
    }

    private void process(
            String paymentId,
            String payload,
            String traceId,
            String eventType
    ) {
        // Xử lý sự kiện và gắn traceId vào log/tracing context.
    }
}
```

Nếu một header có thể lặp tên, dùng `headers(name)` để duyệt tất cả thay vì `lastHeader(name)`:

```java
for (Header header : record.headers().headers("tag")) {
    String tag = header.value() == null
            ? null
            : new String(header.value(), StandardCharsets.UTF_8);
    log.debug("tag={}", tag);
}
```

Với listener nhận trực tiếp payload thay vì `ConsumerRecord`, custom headers có thể được ánh xạ thành Spring Message headers nếu converter/header mapper được cấu hình tương ứng. Nếu cần metadata Kafka cụ thể hoặc xử lý nhiều header cùng tên, nhận `ConsumerRecord` sẽ rõ ràng hơn.

## 7. Dùng headers cho correlation ID và trace ID

Trong kiến trúc nhiều dịch vụ, một request có thể tạo ra nhiều event và đi qua nhiều consumer. `correlation-id` giúp liên kết các message thuộc cùng một luồng nghiệp vụ; `trace-id` giúp hệ thống tracing liên kết span qua các dịch vụ.

Ví dụ luồng xử lý:

```text
HTTP request
    |
    | trace-id = T1, correlation-id = C1
    v
Order service
    |
    | Kafka record + trace-id T1 + correlation-id C1
    v
orders.events
    |
    v
Billing consumer
    |
    | record mới tiếp tục mang correlation-id C1
    v
payments.events
    |
    v
Notification consumer
```

Khi tạo event tiếp theo, ứng dụng nên tiếp tục truyền correlation ID theo quy ước nghiệp vụ. Với trace ID, nên dùng thư viện tracing/instrumentation tương thích để inject và extract context theo chuẩn như W3C Trace Context; tự sao chép một chuỗi `trace-id` không tự động tạo span hoặc propagation đầy đủ.

Nếu consumer forward một record sang topic khác, cần quyết định header nào được giữ, thay đổi hoặc loại bỏ. Tránh sao chép mù quáng mọi header nội bộ vì chúng có thể chứa thông tin chỉ có ý nghĩa ở dịch vụ nguồn.

## 8. Quy ước tên, encoding và kích thước header

Đặt tên header nhất quán, dễ hiểu và tránh xung đột với header do framework quản lý. Ví dụ:

| Header | Encoding/giá trị gợi ý | Mục đích |
|---|---|---|
| `trace-id` | UTF-8 string | Liên kết distributed trace |
| `correlation-id` | UTF-8 string | Tương quan luồng nghiệp vụ |
| `event-type` | UTF-8 string | Tên loại sự kiện |
| `schema-version` | UTF-8 string hoặc số được encode rõ ràng | Phiên bản hợp đồng payload |
| `source-service` | UTF-8 string | Dịch vụ phát sinh record |

Các nguyên tắc nên áp dụng:

- Thống nhất chữ thường và dấu gạch nối trong tên custom header.
- Dùng UTF-8 cho metadata dạng văn bản và thống nhất cách decode.
- Quy định rõ đơn vị nếu header mang số, ví dụ milliseconds hay seconds.
- Không dùng header để truyền payload lớn; dữ liệu nghiệp vụ nên nằm trong value.
- Tránh lưu mật khẩu, access token, session cookie hoặc dữ liệu cá nhân nhạy cảm trong header.
- Giữ số lượng và tổng kích thước header ở mức nhỏ vì chúng góp phần làm tăng kích thước record/batch và chi phí truyền, lưu trữ.

Headers không phải vùng lưu trữ miễn phí. Record lớn có thể chạm giới hạn kích thước message/batch hoặc làm tăng network và memory pressure. Hãy đo kích thước thực tế và đặt giới hạn ở tầng producer, broker và consumer phù hợp với hệ thống.

## 9. Khi nào chọn ProducerRecord, khi nào chọn Spring Message?

| Nhu cầu | Cách phù hợp |
|---|---|
| Muốn kiểm soát chính xác raw bytes của header | `ProducerRecord` và `RecordHeader` |
| Cần nhiều header trùng tên | `ProducerRecord` |
| Cần chỉ định topic/key/partition/timestamp cùng headers | `ProducerRecord` hoặc Spring Message với `KafkaHeaders` tương ứng |
| Ứng dụng đã dùng Spring Messaging | `Message<?>` và `KafkaHeaders` |
| Muốn chuyển metadata object Java qua mapper | `Message<?>` với converter/header mapper được cấu hình rõ |
| Cần giao tiếp đơn giản với consumer ngoài Spring | Kafka headers dạng UTF-8 hoặc byte theo hợp đồng chung |

Hai cách đều kết thúc bằng một Kafka `ProducerRecord`. Chọn cách nào phụ thuộc vào việc ứng dụng muốn làm việc trực tiếp với Kafka client API hay tận dụng mô hình Spring Messaging.

## 10. Kiểm tra việc gửi header

Khi kiểm thử producer, nên xác minh cả payload và headers của record. Với test tích hợp dùng Kafka thật hoặc broker nhúng, consumer có thể nhận `ConsumerRecord` rồi kiểm tra:

```java
assertThat(record.key()).isEqualTo("payment-9001");
assertThat(record.value()).contains("paymentId");

Header traceHeader = record.headers().lastHeader("trace-id");
assertThat(traceHeader).isNotNull();
assertThat(new String(traceHeader.value(), StandardCharsets.UTF_8))
        .isEqualTo("trace-abc");
```

Ngoài việc kiểm tra giá trị, cần xác minh:

1. Tên header đúng chính tả và đúng quy ước.
2. Byte value có encoding đúng.
3. Header có được giữ khi đi qua converter/serializer hay không.
4. Consumer có xử lý được header thiếu, null hoặc lặp tên không.
5. Header framework như type metadata không bị custom mapper ghi đè ngoài ý muốn.

Nếu gửi bằng `Message<?>`, hãy kiểm thử converter/header mapper đang dùng vì việc ánh xạ custom header phụ thuộc cấu hình đó. Nếu gửi bằng `ProducerRecord`, có thể kiểm tra trực tiếp byte header trước khi gửi và khi consumer nhận record.

## 11. Những nhầm lẫn thường gặp

1. **Cho rằng header là một phần của JSON value.** Kafka lưu headers riêng bên cạnh key/value.
2. **Đưa object Java trực tiếp vào Kafka header.** Kafka header chỉ lưu byte; cần encode hoặc dùng mapper.
3. **Cho rằng custom header tự quyết định partition.** Partitioner mặc định chủ yếu dựa trên key; header chỉ tham gia nếu partitioner tùy chỉnh đọc nó.
4. **Nhầm Spring Message header với Kafka record header.** Converter và header mapper phải chuyển đổi giữa hai mô hình.
5. **Cho rằng tên header luôn duy nhất.** Kafka cho phép nhiều header cùng tên; consumer cần chọn cách đọc phù hợp.
6. **Dùng header để chứa payload lớn hoặc bí mật.** Header làm tăng kích thước record và có thể xuất hiện trong log/tool quản trị.
7. **Cho rằng trace ID tự động tạo distributed tracing.** Cần instrumentation và propagation context đúng chuẩn.
8. **Cho rằng `KafkaTemplate.send()` trả về là record đã được ghi.** Cần quan sát future/result và xử lý lỗi bất đồng bộ.

Gửi header bằng `KafkaTemplate` giúp metadata đi cùng record từ producer đến consumer. Dùng `ProducerRecord` khi cần kiểm soát byte và header lặp; dùng Spring `Message<?>` khi muốn tích hợp với Spring Messaging và `KafkaHeaders`. Dù chọn cách nào, hãy thống nhất tên, encoding và ý nghĩa của header, đồng thời kiểm tra converter/header mapper để consumer nhận được đúng metadata mong muốn.
