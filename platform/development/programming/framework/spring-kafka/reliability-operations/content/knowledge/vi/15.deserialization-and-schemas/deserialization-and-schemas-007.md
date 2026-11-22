# Serializer và deserializer không tương thích

Trong Spring Kafka, producer dùng **serializer** để chuyển key/value từ Java object thành bytes, còn consumer dùng **deserializer** để khôi phục dữ liệu từ các bytes Kafka lưu. Khi hai phía không thống nhất về wire format, encoding, kiểu dữ liệu, JSON type headers hoặc schema, record có thể được broker lưu thành công nhưng consumer không đọc được. Đôi khi deserializer vẫn trả về một object mà dữ liệu đã sai ý nghĩa — lỗi này còn nguy hiểm hơn exception rõ ràng.

Đây là một bài toán reliability: một record lỗi có thể khiến consumer lặp tại cùng offset, tăng lag, chặn các record tiếp theo của partition hoặc thất bại ngay cả khi chuyển DLT. Việc khắc phục phải bắt đầu từ **hợp đồng dữ liệu producer–consumer**, không phải tăng số lần retry một cách máy móc.

## 1. Serializer và deserializer nằm ở đâu?

~~~mermaid
flowchart LR
    A["Producer Java object"] --> B["Serializer"]
    B --> C["Kafka: key/value bytes"]
    C --> D["Deserializer"]
    D --> E["Spring listener Java object"]
    B -. "Serialization error" .-> F["Producer send failure"]
    D -. "Deserialization error" .-> G["Consumer error/recovery"]
~~~

Kafka broker không tự hiểu Java DTO, JSON hay Avro. Broker giữ byte array, headers, topic, partition, offset và timestamp. Format là thỏa thuận giữa các ứng dụng.

Một cặp tương thích:

~~~text
Producer: JsonSerializer<OrderCreatedEvent>
  -> {"eventId":"evt-1","orderId":"ord-9","amount":150000}
  -> Kafka topic "orders"
  -> JsonDeserializer<OrderCreatedEvent>
  -> Listener nhận OrderCreatedEvent
~~~

Một cặp không tương thích:

~~~text
Producer: StringSerializer với value "ord-9|CREATED|150000"
  -> Kafka lưu bytes UTF-8
  -> Consumer: JsonDeserializer<OrderCreatedEvent>
  -> Lỗi parse JSON khi poll()
~~~

Cần phân biệt ba tầng:

| Tầng | Chức năng | Lỗi thường gặp |
|---|---|---|
| Producer serializer | Object → bytes trước khi gửi | Không serialize được field, serializer sai kiểu |
| Consumer deserializer | Bytes → object trong Kafka consumer | Format mismatch, unknown schema, type header sai |
| Spring message converter/listener adapter | Object → kiểu tham số `@KafkaListener` | Converter không tương thích, listener signature sai |

Một consumer dùng `StringDeserializer` có thể đọc chuỗi JSON dưới dạng `String` mà không báo lỗi. Nhưng nếu listener đòi `OrderCreatedEvent` và không có converter tương ứng, lỗi có thể chỉ xuất hiện tại bước chuyển tham số.

## 2. Các kiểu không tương thích thường gặp

| Producer gửi | Consumer mong đợi | Hậu quả |
|---|---|---|
| `StringSerializer` với text thuần | `JsonDeserializer` | JSON parse error |
| `JsonSerializer` tạo JSON object | `StringDeserializer` | Có thể nhận chuỗi JSON nhưng sai kiểu listener |
| `ByteArraySerializer` chứa binary | `StringDeserializer` | Dữ liệu giải mã sai hoặc không có nghĩa |
| Avro/Protobuf theo Schema Registry wire format | JSON deserializer | Parse error tại byte đầu |
| JSON kèm Java FQCN type header | Consumer thiếu class đó | Class not found/type resolution failure |
| JSON không kèm type header | `JsonDeserializer` không có default type | Không biết target Java class |
| JSON schema v2 | Consumer chỉ hiểu schema v1 | Missing field, enum/value mismatch |
| Key serializer đổi kiểu hoặc encoding | Key deserializer cũ | Lỗi key hoặc thay đổi partitioning |
| Payload nén/mã hóa riêng | Consumer không có bước giải mã tương ứng | Bytes không parse được |

Không phải mismatch nào cũng phát sinh exception. Ví dụ đổi đơn vị số tiền từ đồng sang xu vẫn có thể parse thành số nguyên, nhưng tác động nghiệp vụ sẽ sai. Reliability cần **wire compatibility** và **semantic compatibility**.

## 3. Cấu hình JSON nhất quán trong Spring Boot

Giả sử topic `orders` chỉ chứa một kiểu `OrderCreatedEvent`. Producer gửi JSON, không phụ thuộc vào tên class Java của producer; consumer khai báo target type rõ ràng.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderCreatedEvent
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.orders
    listener:
      ack-mode: record
~~~

Lý do đặt các cấu hình:

- `StringSerializer` và `StringDeserializer` cùng hiểu key dạng chuỗi.
- `JsonSerializer` ghi JSON vào value.
- `spring.json.add.type.headers: false` làm producer không nhúng Java class name vào type header.
- `spring.json.value.default.type` và `spring.json.use.type.headers: false` bảo consumer biết kiểu đích mà không cần type headers.
- `ErrorHandlingDeserializer` bọc delegate để lỗi parse có thể đi qua cơ chế recovery của Spring Kafka.
- `trusted.packages` giới hạn package hợp lệ; không mở rộng thành `*` chỉ để dập lỗi.

Ví dụ DTO và listener:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long amount) {
}

@Component
class OrderListener {

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onMessage(OrderCreatedEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

Config trên chỉ phù hợp khi tất cả value của topic đều tuân theo contract tương ứng. Nếu cùng topic chứa nhiều event type, một default type chung có thể không đủ; nên dùng type mapping, envelope hoặc schema-aware format.

## 4. Java type headers gây coupling giữa services

Spring Kafka `JsonSerializer` có thể gắn thông tin Java type vào Kafka headers; `JsonDeserializer` có thể dùng header để xác định class cần tạo.

~~~text
Service producer:
  com.producer.events.OrderCreated

Type header:
  com.producer.events.OrderCreated

Service consumer:
  com.consumer.api.OrderCreatedEvent

Consumer không có class của producer hoặc không trust package.
~~~

JSON value của hai ứng dụng có thể hoàn toàn tương thích, nhưng consumer vẫn lỗi vì class name trong header. Khi các service có codebase riêng, tránh biến Java FQCN thành giao thức public.

Các hướng xử lý:

1. Với topic chỉ chứa một event type: tắt type headers và khai báo default target type.
2. Với nhiều event type: dùng logical type mapping chung token, nhưng mỗi bên mapping tới class riêng.
3. Dùng envelope với `eventType`, `schemaVersion` rồi dispatch theo contract nghiệp vụ.
4. Dùng Avro, Protobuf hoặc JSON Schema với registry/contract rõ ràng.

Ví dụ logical token:

~~~yaml
# Producer
spring:
  kafka:
    producer:
      properties:
        spring.json.type.mapping: orderCreated:com.producer.events.OrderCreated
~~~

~~~yaml
# Consumer
spring:
  kafka:
    consumer:
      properties:
        spring.json.type.mapping: orderCreated:com.consumer.events.OrderCreatedEvent
        spring.json.trusted.packages: com.consumer.events
~~~

Producer phải bật việc gửi type headers và consumer phải thực sự dùng type headers nếu muốn mapping này có hiệu lực. Không cấu hình mapping rồi đồng thời tắt cả hai phía type headers và kỳ vọng framework tự tìm class theo token.

Không nên chữa lỗi `not in trusted packages` bằng `spring.json.trusted.packages: "*"` trong production. Chỉ trust package cụ thể và xác nhận nguồn dữ liệu được phép gửi type mapping đó.

## 5. Key serializer cũng là một phần của hợp đồng

Key không chỉ là metadata cho listener. Kafka dùng **bytes của key** để chọn partition theo partitioner. Nếu producer đổi key từ String sang custom binary serialization, cùng một business ID có thể hash tới partition khác.

~~~text
Producer v1: key = StringSerializer("order-42")
Producer v2: key = custom binary serializer(orderId=42)

=> Key bytes khác nhau.
=> Partition assignment theo key có thể khác.
=> Thứ tự sự kiện của cùng order không còn như kỳ vọng.
~~~

Nếu consumer vẫn dùng `StringDeserializer` cho key binary, record có thể lỗi trước khi listener nhận value, hoặc tạo chuỗi vô nghĩa. Vì vậy:

- Ghi rõ key schema riêng với value schema.
- Kiểm tra partitioning/order khi thay key serializer.
- Nếu cần recover cả key lỗi, bọc key deserializer bằng `ErrorHandlingDeserializer`.
- DLT publisher cần serialize được raw key bytes khi key deserialization thất bại.
- Thay key contract lớn có thể cần topic mới và migration theo từng giai đoạn.

Không sửa được vấn đề key bằng cách chỉ thay JSON value deserializer.

## 6. Schema evolution: cùng JSON vẫn có thể không tương thích

Producer v1 ghi:

~~~json
{
  "eventId": "evt-88",
  "orderId": "ord-120",
  "amount": 120000
}
~~~

Producer v2 đổi tên field và thêm thông tin tiền tệ:

~~~json
{
  "eventId": "evt-88",
  "orderId": "ord-120",
  "totalAmount": 120000,
  "currency": "VND"
}
~~~

Một consumer cũ có thể chờ `amount`. Tùy mapper/constructor/validation, nó có thể báo lỗi thiếu property hoặc âm thầm tạo giá trị mặc định. Cả hai đều phải được xử lý.

Những thay đổi cần cân nhắc:

| Thay đổi schema | Rủi ro |
|---|---|
| Thêm field tùy chọn có default | Thường dễ tương thích hơn nếu consumer bỏ qua field lạ |
| Thêm field bắt buộc | Consumer cũ có thể không hiểu hoặc dữ liệu cũ không đủ field |
| Đổi tên/xóa field | Consumer có thể nhận null/default hoặc lỗi |
| Đổi kiểu String ↔ Number | Conversion error hoặc sai semantics |
| Thêm enum value | Consumer cũ có thể không có case tương ứng |
| Đổi đơn vị tiền/timestamp | Có thể parse thành công nhưng tính toán sai |
| Đổi nesting hoặc structure | Mapping DTO lỗi |
| Đổi wire-format framing | Deserializer hoàn toàn không đọc được |

Schema compatibility nên được kiểm tra ở cả tầng parse và tầng nghiệp vụ. Validation sau deserialization giúp ngăn object “hợp lệ về cú pháp” nhưng sai invariant được commit.

## 7. Avro, Protobuf và Schema Registry

Một số serializer Avro/Protobuf kèm Schema Registry ghi record theo wire format có schema ID. Bytes không nhất thiết là UTF-8 JSON.

~~~text
Producer: Schema Registry-aware Avro serializer
  -> [magic byte][schema ID][binary payload]
  -> Kafka
Consumer: JsonDeserializer
  -> lỗi parse vì payload không phải JSON text
~~~

Ngược lại, consumer dùng Schema Registry deserializer để đọc JSON thuần có thể báo `Unknown magic byte` hoặc lỗi framing. Với Kafka thuần, không có cơ chế tự động nhận diện Avro, Protobuf và JSON cho mọi payload.

Hệ thống cần thống nhất:

- Serializer/deserializer **cùng wire protocol** và registry vendor.
- Registry URL, credential, subject-naming strategy, schema ID format.
- Chính sách compatibility như BACKWARD/FORWARD/FULL theo registry đang dùng.
- Reader schema, writer schema và cách xử lý version cũ.
- Serializer tương thích cho retry/DLT khi payload có thể là raw bytes.

Lỗi `schema ID not found` có thể do sai registry, sai subject/ID hoặc schema đã bị xóa. Lỗi timeout tới registry là vấn đề hạ tầng và có thể phù hợp với retry, khác với lỗi payload cố định không thể parse.

## 8. Nhận diện lỗi theo exception và vị trí phát sinh

Ví dụ các dấu hiệu:

~~~text
RecordDeserializationException:
  Error deserializing key/value for partition orders-2 at offset 418

DeserializationException: failed to deserialize

JsonParseException: Unexpected character ...

IllegalArgumentException:
  The class '...' is not in the trusted packages

IllegalStateException:
  No type information in headers and no default type provided
~~~

Câu chữ chính xác tùy thư viện và phiên bản. Khi điều tra, giữ exception class/cause chain, topic, partition, offset và producer/consumer release version.

| Triệu chứng | Giả thuyết cần kiểm tra |
|---|---|
| JSON parse error ngay byte đầu | Consumer đang đọc String/binary không phải JSON |
| Unknown magic byte | Schema Registry deserializer đọc sai wire format |
| ClassNotFound/type mapping error | Type header tham chiếu class không tồn tại ở consumer |
| Trusted packages error | Package/type ID không được phép |
| No type information | Thiếu type header và default type |
| Consumer lỗi lặp đúng offset | Poison record chưa có recovery phù hợp |
| Producer `SerializationException` | Record có thể chưa gửi lên broker |
| Listener `ClassCastException` | Deserialize hoặc message conversion trả sai kiểu |
| Không lỗi nhưng field sai | Schema/encoding/semantic mismatch |
| Toàn bộ record lỗi sau deploy | Thay đổi cấu hình SerDe hoặc schema breaking |

Nếu một record lỗi, ưu tiên truy vết producer của record đó. Nếu toàn bộ partition/topic lỗi sau một thời điểm, kiểm tra thay đổi rollout, schema và config consumer factory.

## 9. Tại sao DefaultErrorHandler không tự giải được lỗi trong poll?

Nếu deserializer của Kafka client ném exception trong `poll()`, container chưa có một `ConsumerRecord` hợp lệ để chuyển tới listener. Chỉ thêm `DefaultErrorHandler` có thể chưa đủ; consumer có thể lặp lại lỗi tại cùng offset.

`ErrorHandlingDeserializer` của Spring Kafka bọc delegate deserializer, bắt lỗi parse và cung cấp thông tin lỗi trong record headers để container/error handler có thể đưa record sang recovery.

~~~mermaid
flowchart TD
    A["Kafka record bytes"] --> B["ErrorHandlingDeserializer"]
    B -->|Delegate OK| C["Java object -> @KafkaListener"]
    B -->|Delegate fail| D["Deserialization exception metadata"]
    D --> E["Container error handler"]
    E --> F["DLT / quarantine"]
~~~

`ErrorHandlingDeserializer` không sửa dữ liệu và không tự nâng cấp schema. Nó cho phép **không mất khả năng tiến offset** khi gặp poison record, với điều kiện recovery được thiết kế đúng.

## 10. Bọc cả key và value khi cần

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderCreatedEvent
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.orders
~~~

Dùng đúng delegate theo producer thực tế. Nếu topic chứa key Long binary nhưng config dùng `StringDeserializer`, việc chỉ thêm wrapper giúp recover lỗi phát sinh, **không** biến String deserializer thành Long deserializer tương thích.

Spring Kafka có thể giữ lại raw bytes và metadata exception để publish DLT cho record không thể deserialize. Producer DLT phải có serializer phù hợp cho dữ liệu đó. Tránh dùng chung một consumer factory cho nhiều topic có định dạng wire khác nhau trừ khi đã thiết kế dispatch rõ ràng.

## 11. DefaultErrorHandler và DLT cho record không parse được

Ví dụ error handler cho non-transactional listener:

~~~java
@Bean
DefaultErrorHandler errorHandler(
        KafkaTemplate<Object, Object> deadLetterTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
        deadLetterTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
        org.springframework.kafka.support.serializer.DeserializationException.class,
        UnsupportedEventVersionException.class
    );

    return handler;
}
~~~

Khi payload không thể parse theo contract, chờ thêm 1 giây thường không giúp ích. Non-retryable classification cho phép chuyển record đến DLT/quarantine nhanh hơn. DLT cần đủ partition nếu destination resolver giữ partition nguồn.

Nếu publish DLT thất bại, không được coi recovery đã hoàn tất và tự commit vượt qua record nguồn. Lưu record không đọc được là bước bảo vệ dữ liệu, không phải xác nhận nghiệp vụ thành công.

Với Kafka transactional listener, luồng rollback/recovery có thể dùng `DefaultAfterRollbackProcessor` thay vì cấu hình non-transactional `DefaultErrorHandler` tương tự; cần xác định transaction boundary trước khi áp dụng.

## 12. DLT serializer phải xử lý được raw bytes

Lỗi thứ cấp phổ biến: `ErrorHandlingDeserializer` đã bắt lỗi JSON nhưng `DeadLetterPublishingRecoverer` lại không publish được vì producer DLT chỉ được cấu hình cho Java DTO. Khi lỗi deserialization, key/value ở DLT có thể là raw `byte[]`.

Một ví dụ serializer chọn delegate theo kiểu dữ liệu (với phiên bản Spring Kafka hỗ trợ `DelegatingByTypeSerializer`):

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(Object.class, new JsonSerializer<>());

Serializer<Object> dltValueSerializer =
        new DelegatingByTypeSerializer(delegates, true);
~~~

Đây là phác thảo cấu hình value serializer: bytes dùng `ByteArraySerializer`, object còn lại dùng JSON. Cần gắn serializer này vào producer factory tương ứng. Nếu key cũng có thể deserialize lỗi, cần kiểm tra cả key serializer. API constructor và dispatch logic có thể khác theo phiên bản Spring Kafka.

Một chiến lược khác là thiết kế DLT lưu toàn bộ raw key/value bytes và một envelope metadata nhất quán, nhưng cần chuyển đổi chủ động và giữ đủ provenance. Không chỉ đổi producer sang `ByteArraySerializer` trong khi recoverer vẫn có thể gửi Java object.

## 13. Producer serialization error: không có record cho consumer retry

Lỗi serialize ở producer thường xảy ra trước khi record được ghi thành công. Một consumer DLT không thể cứu một event mà producer chưa hề gửi.

Ví dụ với Spring Kafka 3.x:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        try {
            kafkaTemplate.send("orders", event.orderId(), event)
                .whenComplete((result, error) -> {
                    if (error != null) {
                        log.error("Publish failed: {}", event.eventId(), error);
                    }
                });
        }
        catch (RuntimeException error) {
            log.error("Publish failed before completion", error);
            throw error;
        }
    }
}
~~~

Spring Kafka 3.x dùng `CompletableFuture` cho `send`; phiên bản cũ có API future khác. Exception có thể phát sinh khi gọi hoặc được báo trong future/callback. Đối với business event quan trọng, cần ghi nhận publish failure bền vững, ví dụ transactional outbox, rồi sửa nguyên nhân trước khi gửi lại.

Không retry vô hạn một lỗi serializer không hiểu class/format; cần sửa serialization contract, model hoặc cấu hình producer.

## 14. Lỗi trước listener khác lỗi sau listener

Một ví dụ dễ nhầm: producer ghi JSON object, consumer cấu hình `StringDeserializer`, listener khai báo `OrderCreatedEvent`.

~~~text
Kafka bytes: {"eventId":"evt-1"}
     |
StringDeserializer
     v
Java String: "{\"eventId\":\"evt-1\"}"
     |
Spring listener adapter
     v
Không có converter phù hợp để chuyển String -> OrderCreatedEvent
~~~

Đây có thể là lỗi conversion/invocation thay vì lỗi Kafka deserializer. Nếu chỉ phân loại `DeserializationException` và quên `MessageConversionException`, chính sách retry/recovery sẽ không nhất quán.

Một cách chẩn đoán là tạm kiểm tra kiểu dữ liệu **được trả về bởi configured deserializer** và kiểu listener cần, thay vì chỉ nhìn raw payload. Tránh thay đổi code production thành listener String vĩnh viễn chỉ để che lỗi conversion; hãy sửa contract ở đúng tầng.

## 15. Xem raw bytes và Kafka headers

Khi không rõ format, cần xác định broker thực sự đã lưu những gì. Không chỉ suy đoán từ DTO Java, tên topic hoặc một log “send success”.

Quy trình:

1. Xác định topic, partition, offset và key của record lỗi.
2. Xác định producer instance và phiên bản gửi record đó.
3. Đối chiếu key/value serializer của producer với deserializer của consumer.
4. Kiểm tra type headers, schema ID, encoding và custom framing.
5. Lấy raw bytes có kiểm soát (hash/hex preview, không log dữ liệu nhạy cảm).
6. Đối chiếu với record được xử lý thành công gần đó.
7. Kiểm tra mốc triển khai producer/consumer/schema registry.
8. Kiểm tra raw bytes có thể được giải mã bằng đúng format trước khi replay.

Ví dụ nhận diện sơ bộ:

~~~text
7B 22 65 76 65 6E 74 49 64 ...
^  ^
{  "
Có thể là đầu JSON object UTF-8

00 00 00 01 A7 ...
^
Có thể là framing kiểu Schema Registry, nhưng cần kiểm tra
wire protocol, schema ID và toàn bộ bytes, không suy từ 1 byte.
~~~

Nếu cần tool debug đọc raw value, có thể dùng `ByteArrayDeserializer` và group ID **khác** consumer production, hoặc đọc tại offset xác định bằng công cụ có quyền truy cập phù hợp. Không thao tác reset offset của group production chỉ để kiểm tra một record.

## 16. Poison record, offset và lag

Một record hỏng tại offset 418 có thể chặn các record sau trong cùng partition:

~~~text
orders-2:
  417: đọc OK
  418: JSON sai -> poll fail
  419: record hợp lệ
  420: record hợp lệ
~~~

Nếu thiếu cơ chế recovery, consumer có thể fail liên tục tại 418 và group lag tăng. Sau khi cấu hình `ErrorHandlingDeserializer`, handler có thể chuyển record 418 sang DLT để group tiến tiếp theo chính sách.

Không “chữa cháy” bằng reset offset hoặc skip offset tùy tiện: thao tác đó có thể làm mất cơ hội xử lý event nghiệp vụ. Nếu một emergency skip thực sự cần, phải có phê duyệt, bảo toàn raw record và kế hoạch replay cụ thể.

Khi record 418 được cách ly, cũng cần cân nhắc invariant về ordering. Nếu 419 là event phụ thuộc vào 418, cho 419 xử lý ngay có thể sai logic dù Kafka consumer hoạt động trở lại.

## 17. Rollout schema tương thích

Đổi wire contract khi producer và consumer triển khai độc lập cần thứ tự nâng cấp hợp lý. Một chiến lược là **expand then contract**:

~~~text
A. Consumer v1 đang đọc schema v1.
B. Triển khai consumer v2 đọc được cả v1 và v2.
C. Producer bắt đầu phát schema v2.
D. Theo dõi consumer cũ, retry topic và DLT chứa v1.
E. Sau khi hết cửa sổ retention/replay, mới gỡ hỗ trợ v1.
~~~

Các công cụ kỹ thuật:

- Envelope `eventType` + `schemaVersion` và upcaster cho event cũ.
- Schema Registry compatibility checks ở CI/CD.
- Contract tests trên **bytes serialize thật**, không chỉ mock DTO.
- Validation sau deserialize cho required fields, currency, timezone, enum.
- Consumer tolerant reader với default/alias có chủ đích, không nuốt lỗi làm sai dữ liệu.
- Dual-read hoặc topic mới khi thay wire format lớn.
- Event ID/idempotency giữ nguyên trong retry và replay.

Lưu ý DLT hoặc retry topics có thể giữ record phiên bản cũ lâu hơn topic gốc. Khi gỡ hỗ trợ schema v1, cần tính cả kế hoạch replay DLT cũ, không chỉ kiểm tra consumer đang chạy hôm nay.

## 18. Retry topic và transaction cũng cần SerDe tương thích

Nếu ứng dụng dùng non-blocking retry, record được forward qua nhiều topic. Producer chuyển record sang retry topic và consumer retry đều cần serializer/deserializer tương thích với dữ liệu được gửi. Có trường hợp topic gốc hoạt động nhưng topic retry lỗi vì factory khác hoặc raw bytes không được cấu hình đúng.

Kafka transaction có thể phối hợp một số thao tác publish Kafka và commit offset trong cùng transaction được cấu hình, nhưng không thể làm một deserializer sai format đọc được bytes. Nếu listener có side effect database/HTTP, vẫn cần idempotency hoặc inbox/outbox để chống tác động trùng khi replay.

Không trộn cấu hình `DefaultErrorHandler` của non-transactional listener với transactional rollback flow mà không phân tích semantics. Sửa SerDe và xác định đúng đường recovery phải đi trước điều chỉnh transaction/retry.

## 19. Observability và cảnh báo

| Chỉ số | Mục đích |
|---|---|
| Producer serialization/send failures | Phát hiện event chưa được gửi |
| Consumer deserialization errors theo topic | Nhận diện sai format và poison record |
| Exception type/cause, app version | Ghép sự cố với bản deploy |
| Lag cố định tại một offset | Phát hiện consumer mắc kẹt |
| JSON type ID / schema ID errors | Phát hiện coupling hoặc schema mismatch |
| Schema Registry latency/error rate | Phân biệt outage registry với payload hỏng |
| DLT count theo nguồn và exception | Kiểm soát số event cách ly |
| DLT publish failures | Phát hiện lỗi serializer thứ cấp |
| Replay success/failure và duplicate rate | Đánh giá phục hồi an toàn |

Metric tag nên có cardinality thấp như topic, event type, exception class. Event ID và offset phù hợp trong log/trace, không nên trở thành metric label với hàng triệu giá trị.

Cảnh báo cần phân biệt **một poison record** với **lỗi hàng loạt sau deploy**. Nếu toàn bộ record mới thất bại, có thể cần rollback hoặc dừng nguồn phát thay vì đẩy hết backlog sang DLT.

## 20. Runbook khi gặp lỗi serializer/deserializer

1. **Khoanh vùng:** topic, partition, offset, producer version và consumer group nào bị ảnh hưởng?
2. **Xác định tầng:** producer serializer, Kafka deserializer, Spring message converter hay logic listener?
3. **So sánh cấu hình:** key/value SerDe, target type, trusted packages, type headers và registry.
4. **Đọc chứng cứ:** exception class/cause, raw bytes preview, headers, schema ID/version.
5. **Xác định phạm vi:** một record, một producer instance, hay tất cả record sau rollout?
6. **Phân loại:** format sai vĩnh viễn, schema breaking, cấu hình class/type sai, hay outage registry tạm thời?
7. **Bảo toàn record:** dùng `ErrorHandlingDeserializer` và DLT/quarantine phù hợp cho record không đọc được; xác nhận DLT publisher hỗ trợ bytes.
8. **Sửa nguồn lỗi:** cập nhật producer/consumer/schema contract, không chỉ tăng retry attempts.
9. **Đánh giá side effect:** idempotency, key ordering và trạng thái nghiệp vụ trước khi replay.
10. **Rollout tương thích:** consumer đọc được dữ liệu cũ và mới trước khi producer thay đổi.
11. **Replay có kiểm soát:** giữ event ID và provenance, theo dõi lại exception/lag/DLT.
12. **Theo dõi sau sửa:** mọi consumer cần thiết tiến offset, không còn serialization errors mới và không nhân đôi nghiệp vụ.

## 21. Những nguyên tắc cần nhớ

- Kafka lưu **bytes**, không lưu type safety của Java producer.
- Xem key và value như hai hợp đồng serialization độc lập.
- Phân biệt lỗi producer send với lỗi consumer poll và lỗi Spring listener conversion.
- Tránh phụ thuộc Java FQCN qua service boundary nếu không thật sự cần.
- Dùng default target type, logical type mapping hoặc envelope phù hợp.
- Kiểm tra schema evolution cả ở wire level và semantic level.
- Với Avro/Protobuf, producer và consumer phải dùng đúng wire protocol và registry.
- `ErrorHandlingDeserializer` giúp đưa lỗi deserialize vào recovery, không tự sửa payload.
- DLT producer cần hỗ trợ raw bytes trong trường hợp deserialization failure.
- Không retry vô hạn payload cố định sai format; hãy xử lý DLT và sửa contract.
- Không reset/skip offset thiếu kiểm soát để “khỏi kẹt”.
- Thử tương thích bằng bytes thật và triển khai consumer trước producer khi có thể.
- Giữ idempotency và event ID khi record có thể được xử lý lại.

**Serializer và deserializer không tương thích là sự cố hợp đồng dữ liệu giữa các ứng dụng Kafka.** Xác định chính xác bytes đã ghi, lớp SerDe thực tế, type/schema metadata và tầng phát sinh exception sẽ chỉ ra cách sửa. Với dữ liệu lỗi, `ErrorHandlingDeserializer` và DLT hỗ trợ cách ly an toàn; với thay đổi schema, cần versioning và rollout tương thích. Kết hợp các biện pháp đó với validation, observability và idempotency giúp Spring Kafka consumer phục hồi mà không âm thầm bỏ qua dữ liệu nghiệp vụ.
