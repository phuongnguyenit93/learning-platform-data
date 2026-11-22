# Dynamic tags từ ConsumerRecord

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring Kafka có thể xử lý hàng triệu record thuộc nhiều nhóm sự kiện khác nhau. Nếu chỉ có metric tổng số message, lỗi và độ trễ của một listener, đội vận hành khó biết vì sao một nhóm event bị chậm hơn các nhóm còn lại.

Ví dụ topic **orders.events** chứa OrderCreated, OrderConfirmed, OrderCancelled và OrderRefundRequested. Producer gửi thêm header **event-family** và **event-version** để consumer phân loại event. Những thông tin này có thể được đưa vào metrics hoặc traces dưới dạng **dynamic tags từ ConsumerRecord**.

~~~text
Kafka topic: orders.events
          |
          v
ConsumerRecord
  topic=orders.events
  partition=3
  offset=4021
  headers:
    event-family=order
    event-version=v2
          |
          v
Spring Kafka listener container
          |
     +----+-------------------------+
     |                              |
Legacy Micrometer Timers      Micrometer Observation
     |                              |
micrometerTagsProvider        KafkaListenerObservationConvention
     |                              |
     v                              v
Dynamic metric labels         Low/high-cardinality key values
                                    |
                                    v
                             Metrics + tracing spans
~~~

Một dynamic tag phải giải quyết vấn đề quan sát thực tế. **Không phải bất cứ trường nào của ConsumerRecord cũng thích hợp làm metric label**. Key, offset, user ID hoặc payload có thể tạo số lượng time series cực lớn hoặc tiết lộ dữ liệu nhạy cảm.

Bài học giải thích cách chọn API đúng theo Spring Kafka version, truy cập metadata và headers an toàn, phân biệt low/high cardinality, gắn custom observation convention, xử lý batch listener và kiểm thử khả năng quan sát.

## 2. ConsumerRecord chứa những gì?

KafkaConsumer.poll nhận các message dưới dạng ConsumerRecord. Khi listener nhận record trực tiếp:

~~~java
@KafkaListener(
    id = "orders-observer",
    topics = "orders.events",
    groupId = "orders-reader"
)
public void consume(ConsumerRecord<String, OrderEvent> record) {
    log.debug(
        "topic={} partition={} offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );

    orderService.process(record.value());
}
~~~

Những trường quan trọng:

| Thuộc tính | API | Đánh giá khi tạo tag |
|---|---|---|
| Topic | record.topic() | Thường hữu ích nếu số topic được giới hạn |
| Partition | record.partition() | Hữu ích với trace; cân nhắc metric cardinality |
| Offset | record.offset() | Giá trị thay đổi liên tục; không dùng làm metric label |
| Key | record.key() | Có thể là entity ID/PII; không dùng nguyên bản làm label |
| Value | record.value() | Payload nghiệp vụ; không gắn trực tiếp vào telemetry |
| Headers | record.headers() | Có thể chứa family/version hoặc secret, cần allowlist |
| Timestamp | record.timestamp() | Dùng tính độ trễ, không gắn từng timestamp làm tag |
| Serialized sizes | serializedKeySize(), serializedValueSize() | Phù hợp histogram, không phải giá trị label |

Một record cụ thể có thể như sau:

~~~text
topic=orders.events
partition=3
offset=4021
key=order-913828
headers:
  event-family: order
  event-version: v2
  producer-service: checkout
  traceparent: 00-...-...-01
value=OrderConfirmed(...)
~~~

**event-family=order** có thể là tag ít giá trị nếu hợp đồng producer chỉ cho phép một tập cố định. **order-913828** hoặc trace ID thay đổi theo event nên không phù hợp làm metric label.

## 3. Static tags khác dynamic tags

**Static tags** được khai báo theo cấu hình listener hoặc service, có cùng giá trị cho mọi record:

~~~text
application=fulfillment-service
environment=prod
team=orders
~~~

**Dynamic tags** được tính từ từng ConsumerRecord:

~~~text
app.event.family=order
app.event.version=v2
~~~

Nếu record tiếp theo có event-family=payment thì dynamic tag có thể đổi sang payment trong khi environment vẫn là prod.

| Loại tag | Ví dụ | Nguồn dữ liệu |
|---|---|---|
| Static | application=fulfillment | Deployment/configuration |
| Dynamic low-cardinality | event.family=order | Header đã chuẩn hóa |
| Dynamic low-cardinality | event.version=v2 | Header thuộc whitelist |
| High-cardinality trace attribute | Opaque correlation ID đã được phê duyệt | Message context |
| Không nên tạo tag | Raw payload, password, JWT, offset, customer ID | Dữ liệu nhạy cảm hoặc vô hạn |

Cần thống nhất semantics: một tag nên có tên key và tập giá trị ổn định giữa các lần deploy, tránh lúc dùng v2, lúc dùng version-2 cho cùng một khái niệm.

## 4. Hai cơ chế monitoring của Spring Kafka

Spring Kafka có hai đường instrumentation khác nhau.

### 4.1. Micrometer Timers truyền thống

Listener container có thể tạo Micrometer timers khi Micrometer và MeterRegistry được cấu hình. Có thể thêm:

- **micrometerTags**: tags cố định.
- **micrometerTagsProvider**: function đọc ConsumerRecord để trả về tags động.

Spring Kafka bổ sung **micrometerTagsProvider** từ các phiên bản **2.9.8 / 3.0.6**.

Tài liệu API nêu rõ provider chỉ áp dụng cho **record listeners**, bị bỏ qua cho **batch listeners**, và **không áp dụng khi bật Observation**.

### 4.2. Micrometer Observation

Từ Spring Kafka **3.0**, framework hỗ trợ Micrometer Observation cho KafkaTemplate và listener containers. Với record listener, Observation có thể tạo timer và tracing span tùy các handlers trong ObservationRegistry.

Các thành phần chính:

~~~text
KafkaListenerObservationConvention
KafkaRecordReceiverContext
KafkaListenerObservation.DefaultKafkaListenerObservationConvention
~~~

Từ Spring Kafka **3.0.6**, receiver context có **getRecord()** để lấy ConsumerRecord, giúp custom convention đọc headers và metadata theo từng message.

### 4.3. Chọn cơ chế phù hợp

| Trường hợp | API nên dùng |
|---|---|
| Legacy Micrometer Timer, Observation tắt | setMicrometerTagsProvider |
| Listener bật observationEnabled=true | KafkaListenerObservationConvention |
| Kafka producer được quan sát | KafkaTemplateObservationConvention |
| Chỉ cần static tags trên legacy Timer | setMicrometerTags |
| Muốn thêm thuộc tính vào span đang chạy | Observation API trong scope hợp lệ |
| Batch listener cần per-record tags | Xem version và batch observation mode |

**Không cấu hình micrometerTagsProvider rồi mong nó tự tạo tags cho tracing spans** nếu application đã chuyển sang Observation.

## 5. Cách A: micrometerTagsProvider

Ví dụ cho record listener dùng timers truyền thống:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        legacyOrdersFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    var properties = factory.getContainerProperties();

    properties.setMicrometerEnabled(true);

    properties.setMicrometerTags(Map.of(
        "application", "fulfillment-service"
    ));

    properties.setMicrometerTagsProvider(record -> Map.of(
        "app.event.family", RecordTags.family(record),
        "app.event.version", RecordTags.version(record)
    ));

    return factory;
}
~~~

Function **setMicrometerTagsProvider** nhận ConsumerRecord và trả **Map<String,String>**. Khi metrics được tạo, dynamic tags được kết hợp với static tags theo behavior của framework.

Cần định nghĩa **RecordTags** sao cho giá trị được chuẩn hóa, hữu hạn, không ném exception vì header lỗi và không tiết lộ payload.

### 5.1. Những giới hạn phải nhớ

- Provider hoạt động cho **record listener**, không phải batch listener.
- Khi **observationEnabled=true**, provider không phải cơ chế dùng để gắn tags.
- Function có thể được gọi thường xuyên ở hot path, nên không gọi HTTP/DB bên trong.
- Chỉ trả low-cardinality values để tránh metric series explosion.
- Nếu có nhiều factories, chỉ listener dùng factory được cấu hình mới nhận tags đó.

## 6. Đọc Kafka headers an toàn

Kafka header có value dạng **byte[]**, không phải lúc nào cũng là một String. Header có thể thiếu, dài bất thường hoặc chứa giá trị không thuộc contract.

Ví dụ helper:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public final class RecordTags {

    private RecordTags() {
    }

    private static String headerValue(
            ConsumerRecord<?, ?> record,
            String name) {

        Header header = record.headers().lastHeader(name);

        if (header == null || header.value() == null) {
            return "missing";
        }

        byte[] bytes = header.value();

        if (bytes.length == 0 || bytes.length > 64) {
            return "invalid";
        }

        return new String(bytes, StandardCharsets.UTF_8);
    }

    public static String family(ConsumerRecord<?, ?> record) {
        return switch (headerValue(record, "event-family")) {
            case "order" -> "order";
            case "payment" -> "payment";
            case "inventory" -> "inventory";
            default -> "other";
        };
    }

    public static String version(ConsumerRecord<?, ?> record) {
        return switch (headerValue(record, "event-version")) {
            case "v1" -> "v1";
            case "v2" -> "v2";
            case "v3" -> "v3";
            default -> "other";
        };
    }
}
~~~

Với thiết kế này, producer gửi event-family=order-913828 cũng chỉ tạo tag **other**, không tạo một metric label mới theo mỗi event.

Nếu format headers yêu cầu normalization khác, hãy điều chỉnh helper theo một **schema contract rõ ràng**. Không tự suy luận từ dữ liệu không đáng tin cậy.

### 6.1. Multiple headers cùng tên

Kafka cho phép nhiều header có cùng tên. **lastHeader(name)** trả header cuối cùng khớp tên. Ứng dụng cần xác định rõ quy tắc producer/gateway: có được gửi lặp hay không, có tin header cuối không, khi nào xem metadata là invalid.

Nếu hợp đồng chỉ cho phép một giá trị, có thể kiểm tra duplicate và trả **other** khi nhận nhiều header cùng tên, thay vì lấy giá trị bất kỳ.

### 6.2. Không dùng exception header làm tag

Spring Kafka ErrorHandlingDeserializer có thể thêm serialized exception header. Đó không phải thông điệp UTF-8 bình thường và có thể chứa raw bytes nhạy cảm. Không lấy nội dung lỗi hoặc serialized exception trực tiếp làm metric label.

## 7. Low cardinality và high cardinality

**Low cardinality** nghĩa là tập giá trị nhỏ, ổn định và có thể dự đoán:

~~~text
app.event.family:
  order
  payment
  inventory
  other

app.event.version:
  v1
  v2
  v3
  other
~~~

**High cardinality** nghĩa là tập giá trị rất lớn hoặc thay đổi theo record:

~~~text
orderId=order-913828
correlationId=5d91...
offset=4021
customerId=928172
~~~

Trong metrics backend dạng time series, mỗi tập label mới có thể tạo một series mới. Tracing backend thường có khả năng lưu span attributes nhiều giá trị hơn, nhưng vẫn phải tuân thủ sampling, retention, privacy và quota.

| Trường dữ liệu | Metric label | Trace attribute |
|---|---|---|
| Event family trong allowlist | Có | Có |
| Schema version hữu hạn | Có | Có |
| Topic có tập giá trị giới hạn | Có thể | Có |
| Partition | Cân nhắc budget | Thường hữu ích |
| Offset | Không | Có thể, khi cần debug |
| Opaque correlation ID được phê duyệt | Không | Có thể |
| Order ID, customer ID | Không | Cần privacy approval |
| Email, phone, JWT, password | Không | Không |
| Raw JSON payload | Không | Không |

**High-cardinality không đồng nghĩa luôn được phép đưa dữ liệu vào trace.** Traces có thể lưu lâu, được truy cập bởi nhiều nhóm và được export sang nền tảng ngoài.

## 8. Cardinality là phép nhân, không phải phép cộng

Giả sử metric có:

~~~text
service:       5 giá trị
topic:         8 giá trị
event.family:  4 giá trị
event.version: 4 giá trị
result:        2 giá trị
~~~

Tổng số tổ hợp lý thuyết:

~~~text
5 x 8 x 4 x 4 x 2 = 1280 time series
~~~

Nếu thêm **customer.id** với 100.000 giá trị, số tổ hợp có thể tăng nhiều bậc độ lớn. Đây là lý do gắn record.key() vào metrics rất nguy hiểm.

Ví dụ không nên triển khai:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
    "order.id", String.valueOf(record.key())
));
~~~

Dù nhìn có vẻ tiện lọc theo một order, nó làm số series tăng gần theo số đơn hàng.

**Hướng thay thế:** dùng event.family hoặc một business class đã chuẩn hóa như priority=standard|express|other.

## 9. Cách B: KafkaListenerObservationConvention

Khi bật **Micrometer Observation**, dynamic tags được tạo qua một custom **KafkaListenerObservationConvention**.

Class receiver context:

~~~java
org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext
~~~

Context này cung cấp **getRecord()**, trả ConsumerRecord tương ứng trong những phiên bản hỗ trợ.

Nên mở rộng default convention thay vì thay thế toàn bộ default tags. Những tags mặc định mô tả messaging system, topic, listener và consumer group rất quan trọng cho dashboards và tracing semantic conventions.

### 9.1. Ví dụ custom convention

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.support.micrometer.KafkaListenerObservation;
import org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext;

public final class OrderListenerObservationConvention
        extends KafkaListenerObservation
            .DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        ConsumerRecord<?, ?> record = context.getRecord();

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of(
                "app.event.family",
                RecordTags.family(record)
            ))
            .and(KeyValue.of(
                "app.event.version",
                RecordTags.version(record)
            ));
    }
}
~~~

Đây là code Java hướng tới Spring Kafka hỗ trợ getRecord() trong KafkaRecordReceiverContext, tức Spring Kafka 3.0.6 trở lên trong những version tương ứng.

**Gọi super** giúp giữ low-cardinality tags mà framework định nghĩa. Nếu chỉ trả KeyValues của ứng dụng, bạn có thể vô tình làm mất messaging.* và spring.kafka.listener.id.

### 9.2. Gắn convention vào container

~~~java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        observedOrdersFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                ObservationRegistry observationRegistry) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    var properties = factory.getContainerProperties();

    properties.setObservationEnabled(true);
    properties.setObservationRegistry(observationRegistry);
    properties.setObservationConvention(
        new OrderListenerObservationConvention()
    );

    return factory;
}
~~~

**Phiên bản:** setter **setObservationRegistry** xuất hiện trong các dòng Spring Kafka mới như 3.3.1+. Với các version 3.0.x, API kết nối registry có thể khác. Hãy đối chiếu JavaDoc version đang dùng.

Listener:

~~~java
@KafkaListener(
    id = "orders-observer",
    topics = "orders.events",
    groupId = "orders-reader",
    containerFactory = "observedOrdersFactory"
)
public void consume(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

Không cần gọi custom convention bằng tay trong listener. Container tạo observation context và gọi convention trong pipeline instrumentation.

## 10. ObservationRegistry và tracing handlers

**ObservationRegistry** điều phối các ObservationHandler của Micrometer. Tùy configuration, observation có thể:

- Sinh timer để đo thời lượng listener.
- Ghi outcome/error metadata.
- Tạo tracing span.
- Gắn low/high-cardinality KeyValues.
- Phục hồi trace context được propagate từ producer.

~~~text
ConsumerRecord
      |
      v
KafkaRecordReceiverContext
      |
      v
KafkaListenerObservationConvention
      |
      +-- low-cardinality keys
      +-- high-cardinality keys
      |
      v
Observation
      |
      +-- Metrics handler --> Prometheus/Grafana
      |
      +-- Tracing handler --> Tempo/Jaeger/Zipkin
~~~

Bật **observationEnabled=true** không tự bảo đảm span đã được export. Ứng dụng còn cần Micrometer Tracing bridge, propagation configuration, exporter và backend phù hợp.

Nếu thiếu ObservationHandler cho một backend, convention vẫn có thể tạo KeyValues đúng nhưng bạn không thấy kết quả mong đợi trên hệ thống quan sát.

## 11. High-cardinality tracing tag: ví dụ có kiểm soát

Nếu cần liên kết một message với workflow và policy cho phép, có thể đọc **opaque correlation ID** rồi thêm vào high-cardinality attributes.

~~~java
@Override
public KeyValues getHighCardinalityKeyValues(
        KafkaRecordReceiverContext context) {

    String correlationId =
        TraceTags.approvedCorrelationId(context.getRecord());

    return super.getHighCardinalityKeyValues(context)
        .and(KeyValue.of(
            "app.correlation.id",
            correlationId
        ));
}
~~~

**TraceTags.approvedCorrelationId** là helper ứng dụng tự viết, không phải class Spring Kafka. Nó phải giới hạn độ dài, định dạng, chỉ chấp nhận ID opaque đã được phê duyệt và trả fallback **none** cho giá trị khác.

Một chính sách khả thi:

~~~text
Accepted:
  32 hexadecimal characters, opaque random ID

Rejected:
  email
  phone number
  JWT
  URL chứa query secret
  arbitrary user input
  raw JSON
~~~

Trong nhiều hệ thống, tracing đã có **trace ID** được truyền qua trace context, nên không cần thêm correlation ID nếu không có use case vận hành.

Đừng đưa cùng high-cardinality ID vào **getLowCardinalityKeyValues**, vì nó có thể thành metric label.

## 12. Trace context propagation khác dynamic tags

Kafka headers có thể mang **traceparent**, **tracestate** hoặc baggage.

~~~text
HTTP request
      |
      v
Order API span
      |
      v
KafkaTemplate producer
      |
      +-- inject trace context into headers
      |
      v
Kafka topic
      |
      v
Spring Kafka consumer
      |
      +-- extract trace context
      |
      v
Listener processing span
~~~

**Context propagation** liên kết spans thuộc cùng transaction phân tán. **Dynamic tags** mô tả message hoặc operation để filter, aggregate hay điều tra.

Không đưa nguyên traceparent header vào metric label; nó mang trace ID thay đổi theo request và tạo cardinality cực cao.

Baggage cũng không phải danh sách tag được phép tự động copy. Nếu baggage chứa userId hoặc sessionId, việc đưa nó vào metrics/traces cần xét cardinality và chính sách dữ liệu.

## 13. Tên tags và default conventions

Theo phiên bản Spring Kafka, listener observation có các tags mặc định như:

- **messaging.system**
- **messaging.operation**
- **messaging.source.name**
- **messaging.source.kind**
- **messaging.kafka.consumer.group**
- **spring.kafka.listener.id**

Một số span attributes cũng có partition, offset, client ID hoặc consumer ID.

Custom tags nên có namespace riêng:

~~~text
app.event.family
app.event.version
app.producer.role
app.processing.tier
~~~

Không ghi đè tùy tiện các framework tags như messaging.system hoặc spring.kafka.listener.id. Việc thay đổi chúng có thể phá dashboards, tracing conventions hoặc làm backend query không còn match.

### 13.1. Tag key cũng không nên động

Không nên tạo:

~~~text
app.event.order-913828=true
app.event.order-913829=true
~~~

Tag keys phải cố định, ví dụ:

~~~text
Key:   app.event.family
Value: order | payment | inventory | other
~~~

Không chỉ tag values mới gây cardinality: số lượng tag keys tạo tùy ý cũng ảnh hưởng chi phí và schema telemetry.

## 14. Dynamic tag từ topic hoặc partition

Topic thường là một tag hữu ích, nhưng không phải lúc nào cũng low cardinality.

~~~text
orders.events
payments.events
inventory.events
~~~

Ba topic ổn định có thể phù hợp với metrics.

Ngược lại:

~~~text
orders.tenant-000001
orders.tenant-000002
...
orders.tenant-500000
~~~

Nếu hệ thống tạo topic theo tenant, lấy nguyên record.topic() làm custom label có thể gây cardinality rất lớn. Có thể dùng một **topic.family** hữu hạn thay thế.

Partition có số giá trị giới hạn trong mỗi topic, thường phù hợp hơn với trace hoặc dashboard per-partition được thiết kế riêng. Kafka offset tăng theo record, nên không dùng offset làm label cho metric thông thường.

Nếu default observation đã cung cấp partition/offset span attributes, không cần thêm bản sao.

## 15. Dynamic tag từ record key

Record key thường là order ID, payment ID, user ID hoặc routing key. Dùng nguyên key làm metric label vừa tăng cardinality vừa có nguy cơ rò rỉ dữ liệu.

Nếu hợp đồng key có những prefix cố định thể hiện routing class, có thể phân loại mà không giữ ID:

~~~java
public static String routingClass(ConsumerRecord<?, ?> record) {
    Object key = record.key();

    if (!(key instanceof String text)) {
        return "unknown";
    }

    if (text.startsWith("priority-")) {
        return "priority";
    }

    if (text.startsWith("standard-")) {
        return "standard";
    }

    return "other";
}
~~~

Đoạn code chỉ phù hợp khi prefix là contract ổn định của hệ thống. **Hash ID rồi dùng hash làm tag không giải quyết cardinality**, vì một hash unique vẫn tạo rất nhiều giá trị.

## 16. Lỗi header thiếu, sai hoặc dài

Producer cũ có thể chưa gửi event-family. Middleware có thể thêm header trùng tên. Record tombstone có value=null hợp lệ. Delegate deserializer có thể thất bại.

Tag extraction nên có các fallback:

| Tình huống | Xử lý |
|---|---|
| Header không tồn tại | Trả other |
| Header value=null | Trả other |
| Header vượt giới hạn bytes | Trả other |
| Header không thuộc allowlist | Trả other |
| Header thuộc tập giá trị chuẩn | Trả giá trị chuẩn hóa |
| Value tombstone=null | Không truy cập value.getClass() |
| Deserialization failure | Không cố parse raw payload trong convention |
| Header chứa token/PII | Không log, không xuất thành tag |

**Telemetry không được làm listener lỗi vì một header không hợp lệ.** Helper nên thuần dữ liệu, không blocking, không gọi network, không deserialize Java object tùy ý và có fallback an toàn.

### 16.1. Tại sao không parse payload để lấy tags?

Một convention có thể chạy trên hot path mỗi record. Nếu nó parse lại JSON payload, gọi schema registry hoặc truy vấn DB để lấy customer tier, độ trễ xử lý tăng lên và một lỗi monitoring có thể ảnh hưởng nghiệp vụ.

Nên ưu tiên Kafka metadata hoặc header đã có contract rõ ràng. Nếu cần một phân loại phụ thuộc nghiệp vụ, cân nhắc tính tại producer và gửi header chuẩn hóa.

## 17. Producer-side dynamic tags

Ở phía KafkaTemplate, dữ liệu nguồn là **ProducerRecord**, không phải ConsumerRecord.

Spring Kafka cung cấp:

~~~text
KafkaTemplateObservationConvention
KafkaRecordSenderContext
~~~

Khi custom convention phía producer đọc record, nó có thể sử dụng topic và headers để bổ sung metadata cho producer observations.

Ở đường legacy timer, KafkaTemplate có **setMicrometerTagsProvider(Function<ProducerRecord<?, ?>, Map<String,String>>)** trong các phiên bản hỗ trợ. Provider này cũng không áp dụng khi Observation bật.

Không cấu hình KafkaTemplateObservationConvention rồi mong nó sửa tags của consumer listener. Phải gắn convention ở đúng phía của luồng.

## 18. Batch listener: khác biệt theo Spring Kafka version

Đây là ngoại lệ quan trọng.

Với **Spring Kafka 3.x**, tài liệu Micrometer Observation truyền thống cho biết batch listener không được hỗ trợ cùng cách record listener và thường dùng Micrometer Timers. Đồng thời **micrometerTagsProvider** chỉ áp dụng cho record listeners, không phải batch listeners.

Các dòng **Spring Kafka 4.x** mở rộng khả năng quan sát batch. Tài liệu **4.2** mô tả:

- Khi **observationEnabled=true** và **recordObservationsInBatch=false** (mặc định), một **batch-level observation** được tạo cho cả batch, sử dụng metadata nguồn phù hợp với record đầu tiên.
- Khi **recordObservationsInBatch=true**, có thể tạo per-record observations cho những record trong batch.
- Per-record observations trong batch không nhất thiết được propagate thành current observation bên trong batch listener method.

Ví dụ cho phiên bản có API này:

~~~java
factory.setBatchListener(true);

var properties = factory.getContainerProperties();

properties.setObservationEnabled(true);
properties.setRecordObservationsInBatch(true);
properties.setObservationConvention(
    new OrderListenerObservationConvention()
);
~~~

**Không sao chép API batch này vào Spring Kafka 3.x mà chưa đối chiếu version.** Một số behavior, tên meter và tags thay đổi giữa các dòng 4.x.

### 18.1. Tag đại diện batch không đại diện mọi record

Ví dụ batch:

~~~text
record[0] event-family=order
record[1] event-family=payment
record[2] event-family=inventory
~~~

Nếu batch-level observation lấy metadata record đầu tiên, tag event-family=order **không có nghĩa toàn batch chỉ có order events**.

Khi cần thống kê chính xác từng family trong mixed batch, dùng per-record observation ở version hỗ trợ hoặc thiết kế metric aggregation riêng, có cardinality budget.

## 19. Observability khi consumer retry hoặc replay

Một record có thể được giao lại do retry, rebalance hoặc restart:

~~~text
P0 offset 900
  attempt 1 -> failure
  attempt 2 -> failure
  attempt 3 -> success
~~~

Tùy chỗ đặt instrumentation:

- **listener.invocations** có thể tăng ba.
- **processing.attempts** có thể tăng ba.
- **processing.successes** chỉ tăng một cho attempt thành công.
- **unique business events** cần idempotency/deduplication riêng.

Dynamic tags chỉ phân loại dữ liệu; chúng không tự quyết định semantic của metric hay cung cấp exactly-once processing.

Một timer listener đo các lần gọi listener không nhất thiết bằng latency end-to-end tính từ producer event timestamp tới business completion.

## 20. Hiệu năng khi có nhiều records

Một topic tiêu thụ 20.000 record/giây có thể phát sinh lượng lớn observations, allocations và tracing spans nếu đo đầy đủ từng record.

Những biện pháp cần thiết:

- Dùng low-cardinality metrics để tổng hợp toàn bộ traffic.
- Áp dụng **trace sampling** phù hợp throughput.
- Đặt **cardinality budget** trước khi thêm tags mới.
- Đọc headers không I/O, không parse payload lại.
- Giới hạn kích thước và số lượng trace attributes.
- Không log từng event ở mức INFO mặc định khi volume cao.
- Đo CPU/GC/latency trước và sau bật Observation.
- Kiểm soát metrics series count và tracing ingestion quota.

Việc giảm số tags nhưng vẫn export span cho mọi record có thể chưa đủ để kiểm soát chi phí. Cần thiết kế sampling cùng các metric cần luôn chính xác.

## 21. Test helper với ConsumerRecord

Một unit test không cần Kafka broker có thể tạo ConsumerRecord trực tiếp.

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RecordTagsTest {

    @Test
    void extractsAllowedFamily() {
        var record = new ConsumerRecord<String, String>(
            "orders.events", 2, 42L, "order-42", "payload"
        );

        record.headers().add(
            "event-family",
            "order".getBytes(StandardCharsets.UTF_8)
        );

        assertThat(RecordTags.family(record))
            .isEqualTo("order");
    }

    @Test
    void missingFamilyReturnsOther() {
        var record = new ConsumerRecord<String, String>(
            "orders.events", 0, 10L, "key", "payload"
        );

        assertThat(RecordTags.family(record))
            .isEqualTo("other");
    }

    @Test
    void unboundedValueDoesNotBecomeTag() {
        var record = new ConsumerRecord<String, String>(
            "orders.events", 0, 11L, "key", "payload"
        );

        record.headers().add(
            "event-family",
            "order-913828".getBytes(StandardCharsets.UTF_8)
        );

        assertThat(RecordTags.family(record))
            .isEqualTo("other");
    }
}
~~~

Bổ sung test header null, byte array dài, nhiều headers cùng tên, version lạ và tombstone. Mục tiêu là đảm bảo helper trả về **tập giá trị hữu hạn** chứ không chỉ hoạt động ở happy path.

## 22. Integration test Observation thực tế

Sau khi unit test helper, cần integration test để chứng minh Spring Kafka thật sự sử dụng convention.

1. Tạo Spring context có ObservationRegistry và handlers/test registry phù hợp.
2. Tạo listener container với **observationEnabled=true**.
3. Gắn OrderListenerObservationConvention vào đúng factory.
4. Gửi một record có event-family=order và event-version=v2.
5. Đợi @KafkaListener xử lý.
6. Kiểm tra observation low-cardinality tags chứa app.event.family=order và app.event.version=v2.
7. Xác nhận default messaging.* tags vẫn tồn tại.
8. Gửi header lạ và kiểm tra fallback other.
9. Kiểm tra metrics registry không tạo label từ record.key/offset.
10. Nếu tracing bật, kiểm tra span export và trace context propagation theo sampler.
11. Nếu dùng batch, kiểm tra version và behavior recordObservationsInBatch.
12. Đo series count khi nhiều event IDs khác nhau được gửi.

Chỉ gọi custom convention trực tiếp trong unit test chưa chứng minh nó đã được gắn vào listener factory đang chạy.

### 22.1. Vì sao cần test registry?

ObservationRegistry có thể tồn tại nhưng không có handler export mong muốn. Cần phân biệt:

- Convention tạo KeyValues đúng.
- Container thật sự bật Observation.
- ObservationRegistry được truyền đúng.
- Metrics handler tạo meter.
- Tracing handler tạo span.
- Exporter gửi dữ liệu.
- Sampling policy có giữ span cho tình huống test không.

Một vấn đề ở tracing exporter không có nghĩa logic dynamic tag bị sai.

## 23. Dashboard và truy vấn có ý nghĩa

Ví dụ một dashboard theo dõi Order Fulfillment:

| Panel | Dimensions | Giá trị vận hành |
|---|---|---|
| Listener processing latency | topic, event.family | Nhóm event nào chậm |
| Error rate | listener, event.family, result | Nhóm event nào lỗi nhiều |
| Event version distribution | event.version | Producer có đang rollout schema mới |
| Listener throughput | topic, listener | Listener nào tăng tải |
| Consumer lag | group, topic, partition | Partition nào backlog |
| Span detail | trace ID, source topic, partition | Điều tra một lần xử lý cụ thể |

Không thêm event ID vào metric labels chỉ để click từ dashboard tới một đơn hàng. Nếu cần drill-down, dùng trace/log correlation theo ID được phép, kết hợp query có giới hạn quyền.

### 23.1. Tag unknown/other là tín hiệu hữu ích

Nếu app.event.version=other tăng mạnh sau deploy producer, có thể một producer mới gửi version chưa được consumer monitoring allowlist.

Có thể alert theo tỷ lệ **other** và xem schema contract; không nên đổi code để chấp nhận mọi chuỗi lạ thành tag.

## 24. Bảo mật của dynamic tags

Một Kafka header có thể chứa:

- Authorization token.
- Tenant ID hoặc user ID.
- Trace baggage.
- Request URL chứa query parameters.
- Debug payload.
- Thông tin khách hàng.
- Dữ liệu do producer bên ngoài kiểm soát.

Ngay cả khi một tag chỉ được gắn vào trace, dữ liệu vẫn có thể được export sang backend và tồn tại ngoài application database.

Nguyên tắc:

1. Chỉ dùng fields đã được phê duyệt.
2. Không đưa secret, JWT, email, phone hay payload vào tags.
3. Áp dụng whitelist values và limit độ dài.
4. Không log full headers khi extraction thất bại.
5. Có retention/access control cho tracing backend.
6. Không lấy dữ liệu nhạy cảm từ headers chỉ để debug metric.
7. Kiểm tra compliance trước khi rollout các high-cardinality attributes.

Không dựa vào việc hash email hoặc customer ID để tự động coi dữ liệu đã vô danh: hash vẫn có thể mang thông tin liên kết và gây cardinality cao.

## 25. Những sai lầm thường gặp

**Dùng micrometerTagsProvider khi observationEnabled=true.** Provider legacy không áp dụng, nên dynamic tags không xuất hiện như kỳ vọng.

**Gắn KafkaTemplateObservationConvention để đo consumer.** Producer và consumer dùng observation contexts khác nhau.

**Override getLowCardinalityKeyValues không gọi super.** Có thể mất tags mặc định quan trọng.

**Dùng record.key() làm metric label.** Dễ tạo time series explosion.

**Lấy raw traceparent làm metric tag.** Nó chứa trace ID thay đổi từng request.

**Lấy nguyên header không có allowlist.** Producer có thể gửi vô hạn giá trị hoặc dữ liệu nhạy cảm.

**Dùng offset làm metric label.** Giá trị tăng liên tục theo record.

**Parse payload trong convention.** Tăng độ trễ và tạo điểm lỗi phụ trong hot path.

**Cho rằng Observation luôn tạo spans.** Cần tracing handlers/exporter/sampler.

**Cho rằng batch listener luôn có per-record Observation.** Phụ thuộc phiên bản và mode.

**Cho rằng batch-level event-family đại diện toàn bộ batch.** Batch có thể chứa nhiều nhóm event.

**Cho rằng một listener invocation là một unique business event.** Retry/replay có thể gây nhiều invocation.

**Không kiểm tra series count sau deploy.** Một tag có nhiều giá trị có thể làm backend observability bị quá tải.

## 26. Runbook khi dynamic tags không xuất hiện

1. Xác định Spring Kafka version và Micrometer version.
2. Xác định listener là record hay batch.
3. Kiểm tra **observationEnabled** của container.
4. Nếu Observation bật, kiểm tra KafkaListenerObservationConvention.
5. Nếu Observation tắt, kiểm tra micrometerEnabled và micrometerTagsProvider.
6. Xác nhận @KafkaListener dùng đúng containerFactory.
7. Kiểm tra context.getRecord() có headers phù hợp không.
8. Kiểm tra helper đang trả default other vì header sai hay thiếu.
9. Xác nhận ObservationRegistry và handlers đã đăng ký.
10. Kiểm tra tracing sampling và exporter.
11. Với batch, kiểm tra mode và behavior đúng version.
12. Xác nhận default metrics tags còn nguyên sau custom convention.
13. Kiểm tra backend label filtering hoặc schema change.
14. Đo cardinality và ingestion cost.
15. Kiểm tra privacy/security policy của các tags.
16. Thử gửi một record mẫu có header rõ ràng rồi đối chiếu metric/span.
17. Lưu cấu hình thực tế và quy trình kiểm thử vào runbook upgrade.

## 27. Ví dụ tổng hợp: Order Fulfillment

Order Fulfillment đọc topic **orders.events**. Producer ghi headers:

~~~text
event-family: order
event-version: v2
producer-service: checkout
~~~

Consumer bật Observation với custom convention. Khi nhận:

~~~text
Topic: orders.events
Partition: 3
Offset: 7821
Key: order-913828
Headers:
  event-family: order
  event-version: v2
~~~

Telemetry mong đợi có low-cardinality tags:

~~~text
messaging.system=kafka
messaging.source.name=orders.events
spring.kafka.listener.id=orders-observer
app.event.family=order
app.event.version=v2
~~~

Các framework tags thực tế phụ thuộc version. Metric tags **không chứa** order-913828 hoặc offset 7821.

Nếu producer gửi:

~~~text
event-family: order-913828
event-version: v999999
~~~

Helper trả:

~~~text
app.event.family=other
app.event.version=other
~~~

Series count không tăng theo từng event ID lạ. Đội vận hành vẫn có thể quan sát tỷ lệ other tăng để điều tra producer metadata contract.

## 28. Checklist triển khai

- [ ] Xác định Observation mode và Spring Kafka version.
- [ ] Chỉ dùng micrometerTagsProvider cho legacy record listener timers.
- [ ] Dùng KafkaListenerObservationConvention khi bật Observation.
- [ ] Gắn convention vào đúng container factory.
- [ ] Cấu hình ObservationRegistry và handlers theo stack thực tế.
- [ ] Đọc ConsumerRecord từ KafkaRecordReceiverContext.getRecord().
- [ ] Giữ default tags bằng cách kế thừa default convention và gọi super.
- [ ] Chỉ dùng low-cardinality values được allowlist.
- [ ] Không đưa key, offset, event ID, payload hoặc secrets vào metric tags.
- [ ] Xử lý header thiếu, sai, lặp, null, dài và tombstone.
- [ ] Phân biệt trace context propagation với dynamic tags.
- [ ] Kiểm soát high-cardinality trace attributes theo privacy policy.
- [ ] Không gọi I/O trong observation convention.
- [ ] Hiểu batch observation behavior theo version.
- [ ] Test helper, convention và integration pipeline.
- [ ] Theo dõi time series count, span rate và CPU overhead.
- [ ] Có runbook khi tags biến mất sau upgrade.

## 29. Tài liệu tham khảo

- Spring Kafka Reference — Monitoring: https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html
- Spring Kafka Reference — Micrometer Observation conventions: https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html
- Spring Kafka JavaDoc — KafkaListenerObservationConvention: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaListenerObservationConvention.html
- Spring Kafka JavaDoc — KafkaRecordReceiverContext: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaRecordReceiverContext.html
- Spring Kafka 4.2 Reference — Batch Listener Observations: https://docs.spring.io/spring-kafka/reference/4.2/kafka/micrometer.html

Khi nâng cấp Spring Kafka 3.x lên 4.x, đối chiếu API và behavior của đúng version, nhất là về batch observation, default tags và khả năng tạo per-record observations.

## 30. Ghi nhớ

**Dynamic tags từ ConsumerRecord** cho phép Spring Kafka phân loại listener metrics/traces theo metadata từng message, chẳng hạn event family hoặc schema version. Với **legacy Micrometer Timers**, dùng **micrometerTagsProvider** ở record listener. Với **Micrometer Observation**, dùng **KafkaListenerObservationConvention** và đọc record qua **KafkaRecordReceiverContext.getRecord()**.

Nguyên tắc cốt lõi là **cardinality và bảo mật**: low-cardinality metric tags chỉ nhận tập giá trị hữu hạn, đã chuẩn hóa; không dùng order ID, Kafka offset, raw payload hoặc tokens làm labels. High-cardinality trace attributes cũng phải tuân thủ policy và quota.

Triển khai bền vững cần giữ default convention tags, bật đúng ObservationRegistry/handlers, kiểm tra mode batch theo version và test từ helper đến instrumentation pipeline. Dynamic tags tốt giúp chẩn đoán nhanh hơn mà không khiến hệ thống observability trở thành nguồn sự cố mới.
