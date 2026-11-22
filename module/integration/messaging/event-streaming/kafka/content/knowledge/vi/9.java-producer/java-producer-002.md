# Serializer cho key, value và xử lý lỗi tuần tự hóa

Kafka lưu record dưới dạng byte. Trong ứng dụng Java, producer thường làm việc với kiểu dữ liệu có ý nghĩa nghiệp vụ như String, UUID hoặc một object Java; **serializer** chuyển key và value thành byte array trước khi Kafka client gửi record đến broker.

Key và value có serializer riêng. Cấu hình sai serializer, dữ liệu không hợp lệ hoặc hai phía không thống nhất định dạng có thể làm producer gửi thất bại hoặc consumer không giải mã được record. Vì vậy, thiết kế serializer cần đi cùng hợp đồng dữ liệu, xử lý lỗi và kế hoạch thay đổi schema.

Bài học này giải thích cách cấu hình serializer cho key/value bằng Kafka Java client và Spring Kafka, cách viết custom serializer, phân biệt lỗi tuần tự hóa với lỗi gửi đến broker, đồng thời kiểm thử và vận hành luồng sự kiện an toàn.

## 1. Serializer nằm ở đâu trong luồng gửi?

Một ProducerRecord trong Java có các thành phần chính:

- Topic: tên luồng sự kiện đích.
- Key: dữ liệu dùng để định tuyến record đến partition hoặc xác định thực thể nghiệp vụ.
- Value: payload của sự kiện.
- Headers: metadata bổ sung như trace ID, correlation ID hoặc event type.
- Partition và timestamp: thông tin định tuyến/thời gian tùy cách ứng dụng khai báo.

Producer client serialize key và value thành byte trước khi tạo record batch gửi đến broker. Broker lưu byte record; broker không cần biết object Java ban đầu có kiểu gì.

~~~mermaid
flowchart LR
    A["Ứng dụng Java<br/>Key + Value"] --> B["Key Serializer"]
    A --> C["Value Serializer"]
    B --> D["Kafka record<br/>byte[] key"]
    C --> D
    D --> E["Partitioner<br/>chọn partition"]
    E --> F["Producer client<br/>batch + gửi"]
    F --> G["Broker leader"]
~~~

Key serializer và value serializer hoạt động độc lập. Một cấu hình phổ biến là dùng StringSerializer cho key và JSON serializer cho value. Cấu hình consumer phải có deserializer tương ứng với định dạng byte đã ghi.

## 2. Serializer của Kafka Java client

Kafka client định nghĩa interface Serializer<T>. Serializer nhận một object kiểu T và trả về byte array. Các serializer thường được cấu hình qua hai thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| key.serializer | Class chuyển key thành byte |
| value.serializer | Class chuyển value thành byte |

Một số serializer có sẵn thường dùng:

| Serializer | Dữ liệu phù hợp |
|---|---|
| StringSerializer | Chuỗi UTF-8 như orderId, customerId hoặc event type |
| ByteArraySerializer | Dữ liệu đã được ứng dụng mã hóa thành byte[] |
| ByteBufferSerializer | Dữ liệu dạng ByteBuffer |
| IntegerSerializer | Giá trị Integer |
| LongSerializer | Giá trị Long |
| UUIDSerializer | UUID trên các phiên bản client có hỗ trợ serializer này |

Chọn serializer theo hợp đồng dữ liệu. Ví dụ, nếu key là orderId dạng chuỗi, dùng StringSerializer; nếu value là một object OrderCreated, cần JSON, Avro, Protobuf hoặc serializer tùy chỉnh tương ứng.

### Cấu hình producer thuần Java

Ví dụ producer gửi String key và String value:

~~~java
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("key.serializer",
    "org.apache.kafka.common.serialization.StringSerializer");
properties.put("value.serializer",
    "org.apache.kafka.common.serialization.StringSerializer");

try (KafkaProducer<String, String> producer =
         new KafkaProducer<>(properties)) {
    ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.events", "order-42", "OrderCreated");
    producer.send(record);
}
~~~

Hai generic type của KafkaProducer phải khớp với kiểu key/value mà serializer xử lý. Nếu khai báo KafkaProducer<String, OrderCreated>, value.serializer phải là serializer có thể nhận OrderCreated.

Không nên dùng serializer kiểu String cho một object Java rồi kỳ vọng Kafka tự chuyển object thành JSON. Kafka client không tự suy luận cấu trúc object nghiệp vụ.

## 3. Cấu hình serializer trong Spring Boot và Spring Kafka

Spring Boot cho phép cấu hình serializer qua application.yml. Ví dụ dùng String key và JSON value:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
~~~

Khai báo event:

~~~java
import java.math.BigDecimal;

public record OrderCreated(
    String orderId,
    BigDecimal total,
    String currency
) {
}
~~~

Producer dùng KafkaTemplate với generic type tương ứng:

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class OrderEventProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders.events", event.orderId(), event);
    }
}
~~~

Trong ví dụ này:

- Key được serialize bằng StringSerializer.
- Value được serialize thành JSON bằng Spring Kafka JsonSerializer.
- orderId được dùng làm key để các sự kiện cùng đơn hàng có thể được định tuyến nhất quán.
- Consumer cần JsonDeserializer hoặc deserializer tương thích với JSON format đã phát.

Spring Kafka JsonSerializer thường thêm type headers để consumer nhận diện kiểu Java. Có thể cấu hình type mapping hoặc tắt type headers nếu hợp đồng dữ liệu đã quy định rõ kiểu đích. Cấu hình phải thống nhất giữa producer và consumer; không nên phụ thuộc vào tên class Java nội bộ nếu nhiều ứng dụng/ngôn ngữ cùng đọc topic.

Ví dụ cấu hình consumer theo kiểu đích mặc định:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
~~~

Tên package và class cần thay theo ứng dụng. Chỉ thêm package đáng tin cậy cần thiết; không mở rộng trusted packages quá mức khi đọc dữ liệu từ topic mà nhiều producer có thể ghi.

## 4. Tự viết custom serializer

Khi định dạng dữ liệu không được serializer có sẵn hỗ trợ hoặc cần kiểm soát wire format, có thể triển khai org.apache.kafka.common.serialization.Serializer<T>.

Ví dụ serializer JSON đơn giản cho OrderCreated:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.common.errors.SerializationException;
import org.apache.kafka.common.serialization.Serializer;

public class OrderCreatedSerializer implements Serializer<OrderCreated> {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public byte[] serialize(String topic, OrderCreated data) {
        if (data == null) {
            return null;
        }

        try {
            return objectMapper.writeValueAsBytes(data);
        } catch (JsonProcessingException exception) {
            throw new SerializationException(
                "Cannot serialize OrderCreated for topic " + topic,
                exception
            );
        }
    }
}
~~~

Serializer trả về null khi dữ liệu đầu vào null. Với record có key khác null và value null, Kafka có thể dùng record đó làm tombstone nếu topic được cấu hình compaction. Đây là một ý nghĩa nghiệp vụ có chủ đích, không phải lỗi serialize.

Khai báo trong producer:

~~~properties
key.serializer=org.apache.kafka.common.serialization.StringSerializer
value.serializer=com.example.kafka.OrderCreatedSerializer
~~~

Serializer có thể triển khai thêm configure/close nếu cần đọc cấu hình hoặc giải phóng tài nguyên. Không nên tạo kết nối mạng, gọi database hoặc thực hiện nghiệp vụ bên trong serialize; hàm này nên tập trung vào chuyển đổi dữ liệu để tránh làm chậm luồng gửi và gây lỗi khó dự đoán.

### Khi nào nên dùng custom serializer?

- Có định dạng nhị phân riêng hoặc giao thức nội bộ đã được chuẩn hóa.
- Cần kiểm soát chính xác byte representation.
- Cần tích hợp schema encoding theo một hợp đồng cụ thể.
- Cần tối ưu kích thước hoặc chi phí serialize sau khi đã đo được nút thắt.

Nếu chỉ cần JSON thông thường trong Spring Kafka, JsonSerializer thường dễ bảo trì hơn việc tự xây serializer. Nếu nhiều service hoặc nhiều ngôn ngữ cùng chia sẻ event schema, cân nhắc Avro/Protobuf/JSON Schema cùng Schema Registry thay vì tự tạo format riêng.

## 5. Key serializer và value serializer phải tương thích với consumer

Producer lưu byte; consumer phải biết cách chuyển byte trở lại kiểu dữ liệu. Serializer/deserializer không tương thích có thể tạo ra lỗi giải mã hoặc dữ liệu sai nghĩa dù producer gửi thành công.

| Producer | Consumer tương ứng | Lưu ý |
|---|---|---|
| StringSerializer | StringDeserializer | Hai phía thống nhất encoding, thường là UTF-8 |
| ByteArraySerializer | ByteArrayDeserializer | Ứng dụng tự quản lý format của byte |
| IntegerSerializer | IntegerDeserializer | Phải thống nhất kiểu và biểu diễn |
| LongSerializer | LongDeserializer | Phải thống nhất kiểu và biểu diễn |
| Spring JsonSerializer | Spring JsonDeserializer hoặc JSON deserializer tương thích | Cần thống nhất type mapping, headers và schema |
| Avro/Protobuf serializer có Schema Registry | Deserializer tương ứng cùng registry/subject | Không thể đọc như JSON thuần |

Một lỗi phổ biến là producer phát JSON nhưng consumer lại dùng StringDeserializer hoặc JsonDeserializer với cấu hình type không phù hợp. StringDeserializer chỉ trả về chuỗi; nó không tự chuyển chuỗi JSON thành object Java. Tương tự, JsonDeserializer cần biết kiểu đích và cách xử lý type metadata.

### Schema evolution

Event schema thay đổi theo thời gian. Ví dụ OrderCreated ban đầu có orderId và total; phiên bản sau bổ sung currency. Hãy thiết kế thay đổi tương thích:

- Ưu tiên thêm field tùy chọn hoặc có default phù hợp.
- Không đổi ý nghĩa hoặc kiểu dữ liệu của field đang được consumer sử dụng.
- Không xóa/đổi tên field bắt buộc mà không có kế hoạch chuyển đổi.
- Kiểm thử consumer cũ với event mới và consumer mới với event cũ theo compatibility policy đã chọn.
- Quản lý version của schema và quy trình rollout producer/consumer.

Với Schema Registry, serializer thường ghi schema ID cùng payload theo wire format của registry. Consumer phải dùng deserializer tương ứng để lấy schema và giải mã. Không gửi payload Avro/Protobuf qua JsonDeserializer và không giả định mọi byte payload đều là JSON.

## 6. Lỗi tuần tự hóa xảy ra ở đâu?

Lỗi serializer khác với lỗi broker. Kafka producer thường gọi serializer ở phía client trước khi record được đưa vào batch gửi mạng.

Các lỗi thường gặp:

| Lỗi | Nguyên nhân |
|---|---|
| SerializationException | Serializer không thể chuyển object thành byte |
| ClassCastException | Generic type hoặc object thực tế không khớp serializer |
| JsonProcessingException | Object có cấu trúc không thể serialize, custom serializer hoặc Jackson module cấu hình sai |
| Missing/invalid schema | Schema không tồn tại, sai subject hoặc registry không truy cập được |
| DeserializationException ở consumer | Consumer dùng deserializer hoặc schema không tương thích với byte đã ghi |
| Null key/invalid key | Ứng dụng thiếu key trong khi partitioning hoặc nghiệp vụ yêu cầu key |

Một lỗi serialize phía producer thường xảy ra trước khi gửi request đến broker. Vì vậy, không nên chờ callback gửi thành công xử lý mọi lỗi serializer. Với KafkaProducer thuần Java, lời gọi send có thể ném SerializationException đồng bộ; cần đặt try/catch quanh chính lời gọi send.

Các lỗi phát sinh sau khi request đã được gửi, chẳng hạn broker timeout, authorization hoặc lỗi replica, được báo qua callback/future tùy API và phiên bản client. Phải tách hai nhóm lỗi để chọn cách xử lý phù hợp.

## 7. Xử lý lỗi đồng bộ và bất đồng bộ trong Java

Ví dụ với KafkaProducer:

~~~java
import org.apache.kafka.common.errors.SerializationException;
import org.apache.kafka.clients.producer.Callback;
import org.apache.kafka.clients.producer.ProducerRecord;

public void publish(OrderCreated event) {
    ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>("orders.events", event.orderId(), event);

    try {
        producer.send(record, (metadata, exception) -> {
            if (exception != null) {
                // Lỗi sau khi client bắt đầu gửi hoặc nhận phản hồi từ broker.
                log.error("Kafka send failed", exception);
                return;
            }

            log.info(
                "Sent topic={}, partition={}, offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
    } catch (SerializationException exception) {
        // Serializer thất bại trước khi record được gửi.
        log.error("Cannot serialize event for Kafka", exception);
        throw exception;
    }
}
~~~

Callback xử lý kết quả gửi bất đồng bộ. Nếu serializer ném exception trước khi producer xếp record vào luồng gửi, callback không phải nơi tin cậy để nhận lỗi đó. Đặt try/catch quanh send để bắt lỗi đồng bộ.

Không nên log toàn bộ event khi serialize thất bại nếu payload chứa thông tin cá nhân hoặc dữ liệu nhạy cảm. Ghi event ID, topic, loại event và nguyên nhân kỹ thuật đã được làm sạch thường đủ để chẩn đoán.

## 8. Xử lý lỗi với Spring Kafka KafkaTemplate

KafkaTemplate.send thường trả về CompletableFuture<SendResult<K,V>> ở các phiên bản Spring Kafka hiện đại. Có thể theo dõi kết quả gửi bất đồng bộ:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
        KafkaTemplate<String, OrderCreated> kafkaTemplate
    ) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        try {
            CompletableFuture<SendResult<String, OrderCreated>> future =
                kafkaTemplate.send(
                    "orders.events",
                    event.orderId(),
                    event
                );

            future.whenComplete((result, exception) -> {
                if (exception != null) {
                    // Xử lý lỗi gửi bất đồng bộ.
                    return;
                }

                var metadata = result.getRecordMetadata();
                // Ghi nhận topic, partition, offset.
            });
        } catch (RuntimeException exception) {
            // Bắt lỗi đồng bộ khi tạo/gửi record, bao gồm lỗi serializer
            // được KafkaTemplate chuyển tiếp hoặc bọc lại.
            throw exception;
        }
    }
}
~~~

Đặt cả lời gọi KafkaTemplate.send và việc đăng ký callback trong try/catch để bắt lỗi phát sinh ngay tại thời điểm gọi API. Cách bọc exception cụ thể có thể khác theo phiên bản Spring Kafka; khi cần phân loại, hãy kiểm tra cause chain để tìm SerializationException hoặc lỗi gốc.

Ở Spring Kafka cũ hơn, kiểu trả về của send có thể là ListenableFuture thay vì CompletableFuture. Hãy dùng API tương ứng với phiên bản dependency của dự án.

## 9. Xác thực dữ liệu trước khi serialize

Serializer chịu trách nhiệm chuyển đổi định dạng, không nên là nơi duy nhất kiểm tra quy tắc nghiệp vụ. Hãy xác thực dữ liệu trước khi gửi:

- orderId không rỗng và có định dạng hợp lệ.
- total không âm và có độ chính xác phù hợp.
- currency thuộc tập giá trị được hỗ trợ.
- Các field bắt buộc có mặt.
- Event version hoặc event ID được tạo nhất quán.

Ví dụ dùng Jakarta Bean Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.math.BigDecimal;

public record OrderCreated(
    @NotBlank String orderId,
    @NotNull @PositiveOrZero BigDecimal total,
    @NotBlank String currency
) {
}
~~~

Việc khai báo annotation không tự động kích hoạt validation khi gọi KafkaTemplate.send. Ứng dụng cần gọi Validator hoặc dùng cơ chế validation ở service boundary trước khi publish.

Nếu dữ liệu không hợp lệ, nên từ chối event và ghi nhận lỗi tại nguồn. Không nên gửi một payload lỗi sang Kafka rồi kỳ vọng broker sửa dữ liệu.

## 10. Có nên gửi lỗi serialize vào dead-letter topic?

Dead-letter topic thường được dùng để cách ly record consumer không xử lý được sau khi record đã tồn tại trong Kafka. Lỗi serialize ở producer xảy ra trước khi có record hợp lệ để gửi, nên không thể mặc định dùng consumer dead-letter mechanism cho trường hợp này.

Các lựa chọn phù hợp hơn:

1. Từ chối event, ghi log có correlation ID và trả lỗi cho luồng nghiệp vụ gọi publish.
2. Lưu event vào transactional outbox/database nếu cần giữ lại để xử lý sau khi sửa serializer hoặc schema.
3. Dùng một error envelope có schema ổn định nếu cần phát thông tin lỗi vào Kafka; envelope này phải được serialize bằng một format đáng tin cậy độc lập với payload lỗi.
4. Đưa sự kiện vào hàng chờ sửa chữa ở ứng dụng nếu có quy trình vận hành và replay được kiểm soát.

Không đưa trực tiếp object không serialize được vào một topic lỗi bằng cùng serializer đang hỏng. Cách đó chỉ lặp lại lỗi ban đầu.

## 11. Kiểm thử serializer

Serializer nên có unit test độc lập, không cần khởi chạy Kafka broker cho các trường hợp chuyển đổi thuần túy.

Các trường hợp cần kiểm tra:

- Object hợp lệ tạo ra byte array không rỗng.
- Deserialize byte vừa serialize tạo lại dữ liệu tương đương.
- Field null hoặc optional được xử lý đúng theo schema.
- Giá trị biên và ký tự Unicode không bị biến đổi.
- Dữ liệu không hợp lệ tạo exception rõ ràng.
- Input null có hành vi đúng với hợp đồng; đặc biệt không nhầm null value với empty payload.
- Producer và consumer dùng schema/version tương thích.

Ví dụ kiểm thử round-trip:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import com.fasterxml.jackson.databind.ObjectMapper;

class OrderCreatedSerializerTest {

    @Test
    void shouldSerializeAndDeserializeEvent() throws Exception {
        var serializer = new OrderCreatedSerializer();
        var mapper = new ObjectMapper();
        var original = new OrderCreated(
            "order-42",
            new java.math.BigDecimal("125.50"),
            "VND"
        );

        byte[] bytes = serializer.serialize("orders.events", original);
        OrderCreated restored =
            mapper.readValue(bytes, OrderCreated.class);

        assertEquals(original, restored);
    }
}
~~~

Trong dự án thực tế, dùng cùng cấu hình ObjectMapper/module với ứng dụng production. Nếu serializer/deserializer dùng type header hoặc Schema Registry, test cần kiểm tra cả metadata/wire format đó chứ không chỉ JSON payload.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| ClassCastException trong serializer | KafkaTemplate/KafkaProducer generic type không khớp object thực tế | Kiểm tra kiểu key/value và nơi tạo ProducerRecord |
| SerializationException trước khi gửi | Serializer không hỗ trợ object hoặc dữ liệu lỗi | Kiểm tra serializer class, object và cause gốc |
| Consumer không đọc được JSON | Deserializer/type mapping không đúng | Kiểm tra JSON format, type headers, default type và trusted packages |
| Consumer nhận chuỗi JSON thay vì object | Đang dùng StringDeserializer | Dùng JsonDeserializer hoặc parse chuỗi bằng Jackson ở tầng ứng dụng |
| Payload Avro/Protobuf không giải mã được | Dùng deserializer không đúng wire format hoặc thiếu Schema Registry | Cấu hình serializer/deserializer và registry cùng hợp đồng schema |
| Event mới làm consumer cũ lỗi | Schema thay đổi không tương thích | Áp dụng compatibility policy và kiểm thử rollout |
| Callback không nhận lỗi serializer | Serialize thất bại trước khi record được xếp vào luồng gửi | Bắt exception quanh lời gọi send |
| Record gửi được nhưng key phân bố sai | Key serializer khác nhau giữa producer hoặc key không ổn định | Chuẩn hóa key format và serializer trên mọi producer |

## 13. Checklist trước khi đưa producer vào vận hành

- Key serializer và value serializer được khai báo tường minh.
- Generic type của KafkaProducer/KafkaTemplate khớp với kiểu dữ liệu thực tế.
- Consumer có deserializer tương thích với wire format.
- Schema có quy tắc version và compatibility rõ ràng.
- Null value được phân biệt với empty payload và được dùng có chủ đích.
- Lỗi serializer được bắt ở phía gọi send; lỗi broker được xử lý qua callback/future.
- Payload nhạy cảm không bị ghi vào log lỗi.
- Unit test có round-trip, null, Unicode, field optional và dữ liệu lỗi.
- Retry, idempotence và outbox được thiết kế theo yêu cầu giao nhận của nghiệp vụ.
- Có metric cho send success/failure, serialization failure và latency.

## Kết luận

Serializer chuyển key và value của record Java thành byte để Kafka lưu trữ và truyền tải. Key serializer và value serializer độc lập, phải được cấu hình đúng kiểu dữ liệu và tương thích với deserializer phía consumer. JSON phù hợp với nhiều ứng dụng Spring Kafka; custom serializer hoặc Avro/Protobuf phù hợp khi cần wire format và schema contract rõ ràng.

Lỗi serialize thường xảy ra ở producer trước khi gửi request đến broker, vì vậy cần bắt lỗi đồng bộ quanh lời gọi send. Lỗi phát sinh sau khi gửi được xử lý qua callback hoặc future. Kết hợp validation nghiệp vụ, schema compatibility, kiểm thử round-trip và logging có kiểm soát sẽ giúp producer phát sự kiện ổn định và dễ vận hành.
