# Header mapper và tương tác với ứng dụng Kafka ngoài Spring

Kafka record có payload, key và tập header riêng. Khi ứng dụng Spring Cloud Stream gửi một `Message<T>`, binder phải ánh xạ `MessageHeaders` của Spring sang header dạng byte của Kafka. Khi nhận record, binder thực hiện chiều ngược lại để tạo message cho function hoặc consumer.

Ứng dụng Kafka viết bằng Java thuần, Python, Go hoặc một framework khác không tự hiểu các quy ước kiểu dữ liệu nội bộ của Spring. Vì vậy, khi nhiều nền tảng cùng trao đổi trên một topic, header cần có tên ổn định, kiểu byte rõ ràng và quy tắc mã hóa được công bố. Header mapper là lớp chuyển đổi giữa hai mô hình; nó không phải schema registry và cũng không thay thế việc thiết kế contract payload.

Bài học này xây dựng một contract header có thể đọc được bởi Spring Cloud Stream và Kafka client thông thường, cấu hình bộ lọc header, xử lý kiểu dữ liệu và kiểm tra tương tác hai chiều.

## 1. Phân biệt Kafka record, Spring Message và header

Kafka record chứa key, value và các header. Mỗi Kafka header có tên dạng chuỗi và giá trị dạng `byte[]`. Một record có thể chứa nhiều header cùng tên.

Spring Messaging biểu diễn message bằng payload và `MessageHeaders`, trong đó giá trị header có thể là String, số, object hoặc kiểu dữ liệu của Spring. Do đó, binder cần chuyển đổi giá trị header về byte khi publish và khôi phục kiểu phù hợp khi consume.

~~~text
Spring Cloud Stream                         Apache Kafka
+---------------------------+                +---------------------------+
| Message<T>                |                | ProducerRecord<K, V>      |
|                           |                |                           |
| payload: T  --------------+--------------> | value: byte[]             |
|                           |  serializer    |                           |
| headers: MessageHeaders --+--------------> | headers: key + byte[]     |
|                           | header mapper  |                           |
| KafkaHeaders.KEY ---------+--------------> | record key                |
+---------------------------+                +---------------------------+
                                                           |
                                                           v
                                                Kafka app không dùng Spring
                                                đọc value và header bytes
~~~

Các khái niệm không nên nhầm lẫn:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Payload/value | Nội dung chính của event | JSON OrderCreated |
| Record key | Định danh dùng cho partitioning/compaction | `order-1001` |
| Kafka header | Metadata dạng byte đi kèm record | `event-type=OrderCreated` |
| Spring MessageHeaders | Metadata trong abstraction của Spring | `correlation-id`, `contentType` |
| Header mapper | Chuyển đổi Spring headers và Kafka headers | `KafkaHeaderMapper` |
| Payload serializer/converter | Chuyển payload thành byte và ngược lại | JSON serializer/converter |

Kafka record key không phải là một header tùy chỉnh. Trong Spring, key thường được đặt qua `KafkaHeaders.KEY` khi gửi và đọc qua header key nhận vào. Không tự tạo `record-key` trong metadata rồi cho rằng Kafka sẽ dùng nó để partition.

## 2. Kafka headers là byte, không phải object Java

API Kafka biểu diễn header bằng hai thuộc tính:

~~~java
public interface Header {
    String key();
    byte[] value();
}
~~~

Một ứng dụng Java thuần có thể đọc header và tự giải mã:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.common.header.Header;

Header header = record.headers().lastHeader("correlation-id");

if (header != null && header.value() != null) {
    String correlationId =
        new String(header.value(), StandardCharsets.UTF_8);
}
~~~

Kafka không lưu kiểu Java của header. Nếu producer gửi một chuỗi, nó phải mã hóa chuỗi thành byte; consumer phải biết dùng UTF-8 hoặc một encoding đã thống nhất để giải mã. Nếu producer gửi JSON, Avro hoặc bytes nhị phân trong header, consumer cũng phải biết contract tương ứng.

Vì vậy, header liên hệ nhiều nền tảng nên ưu tiên các giá trị scalar đơn giản:

- Chuỗi UTF-8 cho event type, correlation ID, tenant ID hoặc trace context.
- Số nguyên dạng chuỗi hoặc một biểu diễn byte đã được quy định.
- Timestamp dạng ISO-8601 UTC hoặc epoch millis, thống nhất một định dạng.
- Boolean theo `true`/`false` chữ thường.
- Không dùng Java native serialization hoặc tên class Java làm contract liên nền tảng.

Đặt tên header ổn định, ví dụ `event-type`, `event-version`, `correlation-id`, `causation-id`, `traceparent`. Tránh tên dễ xung đột với header nội bộ như `id`, `timestamp`, hoặc các biến thể chữ hoa/thường như `ID`, `Id`.

## 3. Header mapper làm gì?

Spring Kafka cung cấp abstraction `KafkaHeaderMapper` với hai chiều:

~~~java
public interface KafkaHeaderMapper {
    void fromHeaders(MessageHeaders headers, Headers target);
    void toHeaders(Headers source, Map<String, Object> target);
}
~~~

- `fromHeaders`: chuyển `MessageHeaders` thành Kafka `Headers` khi publish.
- `toHeaders`: chuyển Kafka `Headers` thành map để tạo Spring `MessageHeaders` khi consume.

Spring Cloud Stream Kafka binder sử dụng header mapper để thực hiện ánh xạ này. Trong trường hợp thông thường, binder cung cấp mapper mặc định. Chỉ cần custom mapper khi có yêu cầu rõ ràng như raw UTF-8 headers, allowlist, trusted packages hoặc contract đặc biệt với ứng dụng ngoài Spring.

Một mapper có thể quyết định:

1. Header nào được phép gửi ra Kafka.
2. Header nào được đọc vào ứng dụng.
3. Giá trị được mã hóa thành bytes như thế nào.
4. Bytes được giải mã về String hoặc kiểu khác ra sao.
5. Có hỗ trợ header lặp cùng tên hay không.
6. Có chuyển đổi metadata kiểu JSON của Spring hay không.

Nếu tự viết mapper, phải triển khai cả chiều gửi và nhận. Mapper chỉ làm một chiều có thể khiến header xuất hiện ở producer nhưng biến mất khi consumer đọc, hoặc ngược lại.

## 4. Contract header dùng chung cho Spring và Kafka client

Giả sử service đơn hàng gửi event `OrderCreated`. Payload JSON chứa dữ liệu nghiệp vụ, còn header mang metadata để routing, tracing và quan sát.

~~~text
Topic: orders.created
Key: order-1001
Value:
{
  "orderId": "order-1001",
  "customerId": "customer-42",
  "total": 125000,
  "currency": "VND"
}

Headers:
  event-type      = OrderCreated
  event-version   = 1
  correlation-id  = corr-checkout-9001
  causation-id    = cmd-place-order-9001
  traceparent     = 00-<trace-id>-<parent-id>-01
~~~

Bảng contract nên ghi rõ tên, encoding và tính bắt buộc:

| Header | Kiểu byte/encoding | Bắt buộc | Mục đích |
|---|---|---|---|
| `event-type` | UTF-8 string | Có | Tên event ổn định |
| `event-version` | UTF-8 decimal integer | Có | Phiên bản contract |
| `correlation-id` | UTF-8 string | Theo luồng nghiệp vụ | Liên kết các event trong một hành trình |
| `causation-id` | UTF-8 string | Tùy event | Tham chiếu nguyên nhân trực tiếp |
| `traceparent` | W3C Trace Context ASCII | Khi bật tracing | Liên kết distributed trace |
| `tenant-id` | UTF-8 string | Theo mô hình tenant | Định tuyến hoặc phân vùng theo tenant |

Các header này không nên chứa toàn bộ payload hoặc dữ liệu nhạy cảm. Kafka header được ghi cùng record và có thể được nhiều ứng dụng đọc; không đưa access token, mật khẩu, session cookie hoặc thông tin bí mật vào đó.

Nếu giá trị cần có schema phức tạp hoặc nhiều trường, hãy đưa vào payload/envelope. Header nên ngắn, ổn định và có ý nghĩa xuyên nền tảng.

## 5. Gửi header từ Spring Cloud Stream

Function có thể trả về `Message<T>` để đặt metadata cùng payload:

~~~java
import java.math.BigDecimal;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class OrderProducer {

    @Bean
    Supplier<Message<OrderCreated>> orderCreated() {
        return () -> MessageBuilder
            .withPayload(new OrderCreated(
                "order-1001",
                "customer-42",
                new BigDecimal("125000"),
                "VND"
            ))
            .setHeader("event-type", "OrderCreated")
            .setHeader("event-version", "1")
            .setHeader("correlation-id", "corr-checkout-9001")
            .setHeader("causation-id", "cmd-place-order-9001")
            .build();
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total,
        String currency
    ) {}
}
~~~

Cấu hình output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderCreated

    stream:
      bindings:
        orderCreated-out-0:
          destination: orders.created
          content-type: application/json

      kafka:
        bindings:
          orderCreated-out-0:
            producer:
              header-patterns: "event-type,event-version,correlation-id,causation-id"
~~~

`header-patterns` là danh sách pattern cho header Spring được ánh xạ ra Kafka. Pattern có thể có wildcard ở đầu hoặc cuối và có thể phủ định bằng `!`; quy tắc khớp đầu tiên được áp dụng. Mặc định Kafka binder ánh xạ hầu hết header ngoại trừ `id` và `timestamp`. Khi giao tiếp liên nền tảng, allowlist cụ thể giúp contract dễ kiểm soát hơn.

Header mapper chỉ xử lý metadata. `content-type: application/json` cùng message converter xử lý payload. Không cho rằng khai báo content type sẽ tự định nghĩa cách mã hóa mọi header.

## 6. Đọc header trong Spring Cloud Stream consumer

Consumer nhận `Message<T>` khi cần truy cập metadata:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class OrderConsumer {

    @Bean
    Consumer<Message<OrderCreated>> processOrder() {
        return message -> {
            OrderCreated event = message.getPayload();

            String eventType = message.getHeaders()
                .get("event-type", String.class);
            String correlationId = message.getHeaders()
                .get("correlation-id", String.class);

            // Xử lý event và ghi log theo metadata.
        };
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        java.math.BigDecimal total,
        String currency
    ) {}
}
~~~

Cấu hình input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-projection
          content-type: application/json
~~~

Kiểu thực tế của header sau khi mapper xử lý phụ thuộc mapper và cấu hình. Với raw mapper, header có thể là `byte[]`; với mapper chuyển đổi chuỗi, giá trị có thể là `String`; với JSON type mapping, giá trị có thể được phục hồi thành một kiểu Java đã tin cậy. Khi tích hợp ứng dụng ngoài Spring, nên chọn raw byte/string contract để tránh phụ thuộc vào kiểu Java.

Không ép kiểu trực tiếp sang String nếu chưa xác nhận mapper trả String. Có thể kiểm tra giá trị:

~~~java
import java.nio.charset.StandardCharsets;

Object raw = message.getHeaders().get("correlation-id");

String correlationId;
if (raw instanceof String value) {
    correlationId = value;
} else if (raw instanceof byte[] bytes) {
    correlationId = new String(bytes, StandardCharsets.UTF_8);
} else {
    throw new IllegalArgumentException(
        "Unsupported correlation-id header type"
    );
}
~~~

## 7. Ứng dụng Kafka Java thuần gửi record cho Spring

Một producer không dùng Spring chỉ cần Kafka client. Nó tạo payload theo contract JSON và thêm các header dạng bytes:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("key.serializer",
    "org.apache.kafka.common.serialization.StringSerializer");
properties.put("value.serializer",
    "org.apache.kafka.common.serialization.StringSerializer");

try (KafkaProducer<String, String> producer =
        new KafkaProducer<>(properties)) {

    String json = """
        {
          "orderId": "order-1002",
          "customerId": "customer-77",
          "total": 85000,
          "currency": "VND"
        }
        """;

    ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.created", "order-1002", json);

    record.headers().add(new RecordHeader(
        "event-type",
        "OrderCreated".getBytes(StandardCharsets.UTF_8)
    ));
    record.headers().add(new RecordHeader(
        "event-version",
        "1".getBytes(StandardCharsets.UTF_8)
    ));
    record.headers().add(new RecordHeader(
        "correlation-id",
        "corr-checkout-9002".getBytes(StandardCharsets.UTF_8)
    ));

    producer.send(record).get();
}
~~~

Ứng dụng ngoài Spring không cần tạo `spring_json_header_types` nếu chỉ gửi các header raw string đã thống nhất. Spring consumer dùng mapper phù hợp để đọc bytes về String.

Payload được serialize bằng `StringSerializer` vì ví dụ tạo JSON String. Nếu payload là object Java, cần serializer JSON/Avro/Protobuf tương ứng; không truyền object vào StringSerializer.

## 8. Ứng dụng Kafka Java thuần đọc record từ Spring

Consumer Kafka client nhận `ConsumerRecord`, đọc payload và header độc lập:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

private void handle(ConsumerRecord<String, String> record) {
    Header eventTypeHeader =
        record.headers().lastHeader("event-type");

    Header correlationHeader =
        record.headers().lastHeader("correlation-id");

    String eventType = eventTypeHeader == null
        ? null
        : new String(
            eventTypeHeader.value(),
            StandardCharsets.UTF_8
        );

    String correlationId = correlationHeader == null
        ? null
        : new String(
            correlationHeader.value(),
            StandardCharsets.UTF_8
        );

    String orderId = record.key();
    String jsonPayload = record.value();

    // Deserialize JSON theo schema đã công bố rồi xử lý.
}
~~~

Kafka client đọc các header mà Spring mapper đã ghi nếu giá trị được mã hóa theo contract tương thích. Nó không cần Spring, Jackson hoặc package của ứng dụng producer để đọc raw UTF-8 bytes.

Khi nhận nhiều header cùng tên, `lastHeader(name)` trả về lần xuất hiện cuối. Nếu contract cho phép header lặp, consumer phải duyệt toàn bộ `record.headers().headers(name)` và xác định thứ tự/ý nghĩa. Không giả định mọi mapper Spring giữ nguyên nhiều giá trị cùng tên; hành vi này phụ thuộc mapper và phiên bản.

## 9. Header JSON và metadata kiểu của Spring

`JsonKafkaHeaderMapper` có thể chuyển các giá trị header phức tạp qua JSON. Để khôi phục kiểu ban đầu, mapper có thể thêm một header đặc biệt tên `spring_json_header_types`, chứa ánh xạ từ tên header sang kiểu Java.

Ví dụ khái niệm:

~~~text
Kafka record headers:
  correlation-id            -> UTF-8 bytes
  retry-count               -> JSON bytes
  spring_json_header_types  -> {"retry-count":"java.lang.Integer"}
~~~

Ứng dụng Spring tương thích có thể dùng metadata này để phục hồi kiểu. Kafka client thuần vẫn đọc được bytes, nhưng không biết `spring_json_header_types` có ý nghĩa gì nếu không tự triển khai quy ước đó. Client có thể bỏ qua header metadata này và đọc các header contract đã công bố.

Đối với tích hợp nhiều ngôn ngữ, tránh yêu cầu consumer hiểu tên class Java như `com.example.OrderMetadata`. Thay vào đó:

- Dùng raw UTF-8 cho metadata đơn giản.
- Định nghĩa schema độc lập ngôn ngữ nếu header cần cấu trúc.
- Để dữ liệu phức tạp trong payload có schema rõ ràng.
- Không dùng Java native serialization.
- Không phụ thuộc vào `spring_json_header_types` như một phần bắt buộc của contract công khai.

## 10. Dùng rawMappedHeaders để truyền chuỗi UTF-8

Spring Kafka hỗ trợ cấu hình các header String được ánh xạ trực tiếp thành bytes thay vì JSON. `rawMappedHeaders` là map từ tên header sang boolean:

- `true`: String outbound được mã hóa thành bytes; bytes inbound được giải mã thành String theo charset.
- `false`: không tự chuyển bytes inbound thành String.
- Header không có trong map sẽ giữ kiểu raw theo mapper.

Ví dụ với Spring Kafka mapper:

~~~java
import java.util.Map;

import org.springframework.kafka.support.DefaultKafkaHeaderMapper;
import org.springframework.kafka.support.KafkaHeaderMapper;
import org.springframework.context.annotation.Bean;

@Bean
KafkaHeaderMapper kafkaHeaderMapper() {
    DefaultKafkaHeaderMapper mapper =
        new DefaultKafkaHeaderMapper(
            "!id",
            "!timestamp",
            "event-*",
            "correlation-id",
            "causation-id",
            "traceparent"
        );

    mapper.setRawMappedHeaders(Map.of(
        "event-type", true,
        "event-version", true,
        "correlation-id", true,
        "causation-id", true,
        "traceparent", true
    ));

    return mapper;
}
~~~

Đây là ví dụ cấu hình mapper của Spring Kafka. Khi dùng với Kafka binder, cần đăng ký mapper đúng bean name và thuộc tính `spring.cloud.stream.kafka.binder.header-mapper-bean-name` theo phiên bản binder. Nếu dùng `BinderHeaderMapper` do binder cung cấp, hãy áp dụng API tương ứng của phiên bản đó. Không thêm bean mapper tùy chỉnh nếu default mapper đã đáp ứng contract.

Đặt method `kafkaHeaderMapper()` trong một lớp `@Configuration` để Spring đăng ký bean. Đoạn này minh họa cách tạo mapper; nếu dùng binder, hãy cấu hình bean name được binder tham chiếu thay vì giả định mọi bean `KafkaHeaderMapper` đều tự động được chọn.

Với dữ liệu từ nguồn không tin cậy, không mở rộng trusted packages bằng wildcard. JSON header mapper có thể phục hồi object theo thông tin kiểu; chỉ tin cậy package cụ thể cần dùng. Cách an toàn và dễ tương tác nhất vẫn là dùng chuỗi/bytes đơn giản, không yêu cầu deserialize object Java từ header.

## 11. Custom KafkaHeaderMapper với allowlist raw bytes

Khi cần contract byte rõ ràng và không muốn phụ thuộc metadata kiểu JSON, có thể tự triển khai mapper chỉ cho phép một số header. Ví dụ sau ánh xạ bốn header String theo UTF-8:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.support.KafkaHeaderMapper;
import org.springframework.messaging.MessageHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InteropHeaderMapperConfiguration {

    @Bean
    KafkaHeaderMapper interopHeaderMapper() {
        return new KafkaHeaderMapper() {
            @Override
            public void fromHeaders(
                    MessageHeaders source,
                    Headers target) {

                addString(source, target, "event-type");
                addString(source, target, "event-version");
                addString(source, target, "correlation-id");
                addString(source, target, "traceparent");
            }

            @Override
            public void toHeaders(
                    Headers source,
                    Map<String, Object> target) {

                copyString(source, target, "event-type");
                copyString(source, target, "event-version");
                copyString(source, target, "correlation-id");
                copyString(source, target, "traceparent");
            }
        };
    }

    private static void addString(
            MessageHeaders source,
            Headers target,
            String name) {

        Object value = source.get(name);
        if (value instanceof String text) {
            target.add(
                name,
                text.getBytes(StandardCharsets.UTF_8)
            );
        }
    }

    private static void copyString(
            Headers source,
            Map<String, Object> target,
            String name) {

        Header header = source.lastHeader(name);
        if (header != null && header.value() != null) {
            target.put(
                name,
                new String(
                    header.value(),
                    StandardCharsets.UTF_8
                )
            );
        }
    }
}
~~~

Đặt tên bean trong cấu hình binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          header-mapper-bean-name: interopHeaderMapper
~~~

Mapper này là allowlist: chỉ bốn header được ánh xạ. Những header khác không tự động truyền qua. Nếu ứng dụng cần `contentType`, trace baggage hoặc metadata khác, hãy thêm vào contract và mapper một cách có chủ đích.

Ví dụ dùng `lastHeader` để chọn giá trị cuối cùng nếu Kafka record có nhiều header cùng tên. Nếu contract cần giữ nhiều giá trị, hãy duyệt toàn bộ các header tương ứng và định nghĩa cách đưa danh sách vào Spring MessageHeaders. Kiểm tra API multi-value của mapper và phiên bản Spring Kafka trước khi triển khai.

Không đồng thời cấu hình nhiều mapper khác nhau mà không xác định rõ mapper nào đang được binder sử dụng. `headerMapperBeanName` trỏ tới bean được binder chọn; kiểm tra tên bean và log khởi động nếu header không được chuyển như mong đợi.

## 12. headerPatterns, headerMode và native encoding khác nhau thế nào?

Ba cấu hình thường bị nhầm:

| Cấu hình | Điều khiển | Không điều khiển |
|---|---|---|
| `headerPatterns` | Header Spring nào được mapper gửi sang Kafka | Serializer của payload |
| `headerMode` | Header dùng cơ chế native của middleware hay được nhúng trong payload | Kiểu Java của payload |
| `useNativeEncoding` / `useNativeDecoding` | Kafka client serializer/deserializer có xử lý payload hay không | Allowlist và kiểu mã hóa header |

Kafka hỗ trợ native record headers. Khi trao đổi với Kafka client ngoài Spring, dùng native Kafka headers là lựa chọn tự nhiên. `embeddedHeaders` là cơ chế nhúng metadata vào payload cho middleware không có header native; client Kafka thông thường sẽ không tự giải mã định dạng nhúng này.

Native headers được Kafka client hỗ trợ từ phiên bản 0.11.0.0. Nếu phải tích hợp client/binder rất cũ, hãy kiểm tra giới hạn phiên bản và cơ chế legacy header của binder; không áp dụng cấu hình legacy cho hệ thống Kafka hiện đại nếu không có yêu cầu tương thích cụ thể.

`useNativeEncoding=true` chuyển trách nhiệm serialize payload sang Kafka client serializer. Khi đó việc marshal payload không dựa trên `content-type` của binding; consumer cần cấu hình deserializer tương ứng. Điều này không có nghĩa Kafka headers tự động được chuyển đổi theo cùng serializer. Payload và headers là hai đường chuyển đổi độc lập.

Nếu dùng native encoding, ví dụ payload JSON String có thể dùng `StringSerializer`; nếu dùng object, chọn serializer có contract chung như Avro, JSON hoặc Protobuf. Không đặt `useNativeEncoding` chỉ để giải quyết vấn đề header.

## 13. Header key, topic, partition và metadata của Kafka

Một số header Spring thực chất đại diện cho thuộc tính của Kafka record:

| Spring header | Ý nghĩa Kafka |
|---|---|
| `KafkaHeaders.KEY` | Record key khi gửi |
| `KafkaHeaders.RECEIVED_KEY` | Record key khi nhận |
| `KafkaHeaders.TOPIC` | Topic khi gửi/định tuyến nếu cấu hình hỗ trợ |
| `KafkaHeaders.PARTITION` | Partition được chỉ định khi gửi trong trường hợp phù hợp |
| `KafkaHeaders.RECORD_METADATA` | Metadata kết quả gửi, gồm topic/partition/offset |

Các thuộc tính này không nên bị nhầm với custom header như `event-type`. Kafka binder xử lý key, topic và partition theo semantics riêng. Một Kafka app ngoài Spring đọc chúng qua `ConsumerRecord.key()`, `topic()`, `partition()` và `offset()`, không cần tìm trong `record.headers()`.

Khi cần giữ key đầu vào qua một function và phát record mới, hãy truyền key bằng header key phù hợp. Với reactive function, ứng dụng cần tự sao chép metadata/key cần thiết sang message đầu ra; không giả định tất cả header được giữ tự động.

## 14. Tương thích với ứng dụng Python, Go và framework khác

Ngôn ngữ khác nhau vẫn có thể đọc Kafka headers nếu cùng thống nhất tên và byte encoding. Ví dụ một consumer Python dùng Kafka client có thể đọc danh sách cặp `(name, bytes)`, sau đó giải mã:

~~~python
headers = dict(record.headers() or [])

event_type = headers.get("event-type")
if event_type is not None:
    event_type = event_type.decode("utf-8")

correlation_id = headers.get("correlation-id")
if correlation_id is not None:
    correlation_id = correlation_id.decode("utf-8")
~~~

Đoạn code minh họa cách giải mã header dạng raw bytes. Nếu record có nhiều header cùng tên, chuyển thành dict có thể làm mất giá trị trùng; hãy duyệt danh sách header thay vì dict khi contract hỗ trợ header lặp.

Với Go hoặc framework khác, nguyên tắc tương tự: đọc byte value của header, giải mã UTF-8 theo contract và xử lý payload bằng schema riêng. Không yêu cầu ứng dụng ngoài Spring phải hiểu package Java hoặc Spring Messaging.

## 15. Bảo mật và độ tin cậy của header

Header đến từ Kafka là dữ liệu bên ngoài. Không tin tưởng kiểu hoặc giá trị chỉ vì producer là một service nội bộ.

- Chỉ ánh xạ các header cần thiết; dùng allowlist thay vì truyền mọi metadata không kiểm soát.
- Không trust tất cả package khi JSON mapper phục hồi object từ type metadata.
- Kiểm tra độ dài header và giới hạn tổng metadata để tránh record quá lớn.
- Xác thực enum, version, tenant ID và trace context trước khi dùng.
- Không dùng header để truyền secret hoặc token.
- Không dùng header làm nguồn duy nhất cho quy tắc nghiệp vụ quan trọng nếu payload contract phải chứa thông tin đó.
- Ghi log header có chọn lọc; tránh ghi dữ liệu nhạy cảm.
- Không coi correlation ID hoặc tenant ID là bằng chứng xác thực danh tính.

Nếu header bắt buộc bị thiếu hoặc sai định dạng, consumer nên trả lỗi contract có thể quan sát được. Nếu header tùy chọn bị thiếu, xác định fallback rõ ràng. Không tự tạo correlation ID mới ở mỗi service nếu mục tiêu là theo dõi cùng một hành trình.

## 16. Kiểm thử tương tác hai chiều

Một integration test đầy đủ cần có ít nhất ba trường hợp:

1. Spring producer gửi payload và header; Kafka client thuần đọc đúng bytes.
2. Kafka client thuần gửi record có header raw UTF-8; Spring Cloud Stream consumer đọc đúng String.
3. Header không nằm trong allowlist bị loại bỏ theo chính sách; payload vẫn đọc bình thường.

Ma trận kiểm thử:

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Spring gửi `event-type=OrderCreated` | Kafka record có header bytes UTF-8 đúng |
| Java client gửi `correlation-id` | Spring consumer nhận String theo mapper |
| Header không tồn tại | Consumer xử lý theo chính sách optional/required |
| Header bytes không phải UTF-8 hợp lệ | Validation báo lỗi hoặc giữ raw bytes, không giải mã tùy tiện |
| Header có kiểu object Java | Consumer ngoài Spring không phụ thuộc vào class name |
| Header trùng tên | Cả hai phía áp dụng cùng quy tắc last/first/all |
| Header không trong allowlist | Không được chuyển tiếp ngoài ý muốn |
| Payload dùng native encoding | Serializer/deserializer khớp; header vẫn đọc độc lập |
| Message đi qua function | Các header cần thiết được copy tường minh |
| Kafka client cũ | Kiểm tra hỗ trợ native headers theo phiên bản |

Có thể dùng Testcontainers Kafka để chạy broker thật. Gửi record bằng KafkaProducer thuần, đọc bằng Spring consumer, sau đó gửi ngược từ Spring và đọc bằng KafkaConsumer thuần. Unit test mapper chỉ chứng minh chuyển đổi cục bộ; integration test mới chứng minh binder thực sự ghi/đọc native Kafka headers.

## 17. Quy trình chẩn đoán khi header bị mất hoặc sai kiểu

Khi consumer không thấy header, kiểm tra theo thứ tự:

1. Producer có thực sự đặt Spring header trước khi gửi không?
2. Header name có đúng chính tả và chữ hoa/thường không?
3. Producer binding có `headerPatterns` loại header đó không?
4. Có custom mapper nào đang thay mapper mặc định và bỏ qua header không?
5. Mapper có chuyển String thành UTF-8 bytes không?
6. Consumer binding có dùng native Kafka headers hay đang mong embedded headers?
7. Consumer mapper có đọc tên header đúng và giải mã đúng encoding không?
8. Header có bị framework reserved như `id`/`timestamp` hoặc gần giống chúng gây xung đột không?
9. Consumer có đang đọc header lặp bằng `lastHeader` trong khi producer gửi nhiều giá trị không?
10. Có nhầm record key hoặc topic/partition metadata với custom header không?

Khi cần debug, dùng Kafka console consumer hoặc một consumer client nhỏ để in tên header và bytes dạng hex/UTF-8. So sánh record thô với Spring MessageHeaders. Nếu Kafka record đã có header nhưng Spring không thấy, tập trung vào mapper/converter. Nếu record không có header, kiểm tra producer pattern, custom mapper và cách tạo Message.

## 18. Trình tự thực hành và tiêu chí hoàn thành

Thực hiện bài tập với topic `orders.created`:

1. Định nghĩa contract payload JSON và năm header `event-type`, `event-version`, `correlation-id`, `causation-id`, `traceparent`.
2. Viết Spring Supplier trả `Message<OrderCreated>` với các header trên.
3. Cấu hình Kafka producer `header-patterns` theo allowlist.
4. Dùng Kafka console/client thuần đọc record và xác nhận header là UTF-8 bytes.
5. Viết Kafka Java producer gửi JSON String và raw header bytes.
6. Dùng Spring Cloud Stream consumer nhận message và đọc header theo mapper.
7. Thử custom mapper với allowlist và raw UTF-8.
8. Gửi header thiếu, sai encoding và header trùng tên để kiểm tra chính sách.
9. Bật native payload encoding trong một môi trường thử nghiệm riêng; cấu hình serializer/deserializer tương ứng và xác nhận header vẫn độc lập.
10. Chạy integration test hai chiều với broker thật.
11. Ghi lại phiên bản Spring Cloud Stream, Spring Kafka và kafka-clients cùng contract header được chọn.

Hoàn thành bài khi có thể giải thích khác biệt giữa Spring MessageHeaders và Kafka Headers; cấu hình được header mapper; gửi/nhận raw bytes ổn định; giúp Kafka client không dùng Spring đọc được metadata; và chẩn đoán được header bị mất, đổi kiểu hoặc bị lọc.

## 19. Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html) — Kafka binder, header mapper và cấu hình producer/consumer.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — `headerMapperBeanName`, producer properties và binder configuration.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — `headerMode`, `useNativeEncoding` và `useNativeDecoding`.
- [Spring Cloud Stream — Kafka Tips and Tricks](https://docs.spring.io/spring-cloud-stream/reference/4.3/kafka/kafka_tips.html) — ví dụ custom Kafka header mapper và header đặc biệt.
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html) — KafkaHeaderMapper, JSON type metadata, rawMappedHeaders và trusted packages.
- [Apache Kafka — Record Headers API](https://kafka.apache.org/40/javadoc/org/apache/kafka/common/header/Headers.html) — API thêm, đọc và duyệt Kafka headers.

