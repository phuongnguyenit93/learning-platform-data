# JSON không chuyển đổi được, sai kiểu hoặc mất contentType

## 1. Nhận diện đúng lỗi trước khi sửa cấu hình

Trong Spring Cloud Stream, `Supplier`, `Function` và `Consumer` làm việc với message qua input/output binding. Kafka, RabbitMQ hoặc Pulsar binder chịu trách nhiệm giao tiếp với broker; lớp chuyển đổi message chịu trách nhiệm đưa payload nhận được về kiểu Java mà function mong đợi. Vì vậy, lỗi “JSON không chuyển đổi được” có thể xảy ra ở nhiều thời điểm khác nhau.

Ví dụ một consumer khai báo `Consumer<OrderCreated>` nhưng broker gửi chuỗi bytes, JSON không hợp lệ, content type sai, schema khác hoặc deserializer native trả về một kiểu mà consumer không xử lý được.

Những biểu hiện phổ biến:

- `MessageConversionException` hoặc lỗi `Cannot convert` khi framework chuyển payload.
- `JsonProcessingException`, `MismatchedInputException`, `InvalidFormatException` hoặc lỗi binding của Jackson.
- `ClassCastException` khi handler nhận nhầm kiểu sau conversion hoặc ép kiểu thủ công.
- `SerializationException` hoặc lỗi deserializer từ Kafka client, xảy ra trước khi function được gọi.
- Function được gọi nhưng payload là chuỗi JSON chưa parse thay vì POJO.
- Consumer bỏ qua message hoặc retry mãi do lỗi schema không thể khắc phục.

Không sửa bằng cách đổi bừa mọi binding sang `application/json`. Cần biết **lớp nào đã lỗi**, **payload thực tế là gì**, **header gì còn tồn tại** và **kiểu Java đích có khớp không**.

## 2. Đường đi của một message và vị trí conversion

Một luồng xử lý có thể đi qua:

~~~mermaid
flowchart TD
    P[Producer data / Java object] --> E[Encode payload]
    E --> B[(Kafka / RabbitMQ / Pulsar)]
    B --> D[Binder / native deserializer]
    D --> H[Spring Message headers + payload]
    H --> C[Content type / type conversion]
    C --> F[Supplier / Function / Consumer]
    F --> R[Business result or output binding]
    D -. Deserialization failure .-> X[Poll/client error]
    C -. Conversion failure .-> Y[Conversion error]
    F -. Business exception .-> Z[Processing error]
~~~

Ba nhóm lỗi cần phân biệt:

1. **Broker client/deserializer:** không đọc được record thành kiểu được cấu hình, function chưa chạy.
2. **Spring Cloud Stream conversion:** record được nhận nhưng không chuyển được sang kiểu đầu vào của function.
3. **Business handler:** conversion hoàn tất, code xử lý ném lỗi validation hoặc side effect.

Các nhóm có đường retry, error channel và DLQ khác nhau tùy binder/version. Muốn xử lý đúng phải xác định lỗi nằm ở nhóm nào.

## 3. `contentType` không giống Java type

`contentType` mô tả định dạng dữ liệu được trao đổi, ví dụ:

- `application/json`: payload được mã hóa theo JSON.
- `text/plain`: dữ liệu văn bản thông thường.
- `application/octet-stream`: bytes nhị phân chưa có mô tả cấu trúc cao hơn.
- Một MIME type có hậu tố hoặc tham số đặc thù tùy converter, ví dụ `application/json;charset=UTF-8`.

Java type là kiểu mà function sử dụng, chẳng hạn `String`, `byte[]`, `OrderCreated` hoặc `Message<OrderCreated>`.

Với payload bytes chứa `{"orderId":"O-1"}` và target `OrderCreated`, framework cần biết định dạng bytes và có converter hỗ trợ để tạo đối tượng đúng. `application/json` không tự bảo đảm thành công nếu JSON không phù hợp cấu trúc Java.

Ngược lại, payload là String không có nghĩa MIME type luôn phải là `text/plain`: một String có thể là **văn bản JSON** hoặc **giá trị nghiệp vụ bình thường**. Hai trường hợp có cách encode khác nhau và cần test tường minh.

## 4. Mức ưu tiên khi xác định content type

Trong cơ chế message conversion chuẩn của Spring Cloud Stream, thông tin content type thường được xác định theo thứ tự:

1. Header `contentType` trên message nếu được cung cấp hợp lệ.
2. Thuộc tính `content-type` của binding tương ứng.
3. Content type mặc định do framework áp dụng, thường là `application/json` trong mô hình Spring Cloud Stream thông thường.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
~~~

Khi producer gửi một header content type khác, header có thể được ưu tiên hơn cấu hình binding. Vì vậy, đổi YAML thành JSON không chắc giải quyết được message có header `text/plain` sai.

Lưu ý: quy tắc trên áp dụng khi Spring Cloud Stream quản lý conversion. Với native Kafka SerDe, Pulsar Schema hoặc converter riêng, đường chuyển đổi có thể diễn ra trước hoặc bỏ qua phần này; cần quan sát thực tế theo binder và phiên bản đang dùng.

## 5. Bảng chẩn đoán nhanh theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| JSON hợp lệ nhưng nhận `ClassCastException` | Function type không khớp đối tượng được tạo | Xem generic type và converter thực tế |
| `MismatchedInputException` | JSON array trong khi Java target là object hoặc ngược lại | So payload shape với record/class |
| `InvalidFormatException` | Trường JSON sai kiểu, enum/timestamp không parse được | Xem JSON path và giá trị gây lỗi |
| Header `contentType` bị thiếu | Producer không đặt, binder header mapping không giữ, hoặc native mode | Inspect header trước conversion, cấu hình binding |
| Header `text/plain` nhưng payload là JSON object | Producer khai báo sai MIME type | So bytes với header thực tế |
| Message thành `String` chứa JSON | Chữ ký function nhận String hoặc converter không tạo POJO | Kiểm tra target type và serialization |
| Kafka `SerializationException` lúc poll | Native deserializer không đọc được bytes | Kiểm tra key/value deserializer, SerDe, wire format |
| Một vài event lỗi sau deploy | Schema drift/compatibility không được xử lý | So event version, field và consumer build |
| Chỉ lỗi khi qua broker khác | Header propagation/codec khác nhau | So raw bytes và MIME header hai đầu |
| JSON lỗi bị retry mãi | Lỗi dữ liệu không thể retry được cấu hình như lỗi transient | Phân loại lỗi, DLT/DLQ và backoff |

Không kết luận dựa trên tên exception đơn lẻ: nhiều exception được wrap bởi Spring Integration, binder error handler hoặc framework retry.

## 6. Ví dụ xuyên suốt: Function nhận OrderCreated

Định nghĩa dữ liệu mẫu:

~~~java
record OrderCreated(
    String eventId,
    String orderId,
    long totalCents
) {}

record OrderAccepted(String eventId, String status) {}
~~~

Function biến đổi:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event ->
            new OrderAccepted(event.eventId(), "ACCEPTED");
    }
}
~~~

Message JSON hợp lệ:

~~~json
{
  "eventId": "evt-101",
  "orderId": "ord-101",
  "totalCents": 250000
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

Đây là baseline để so sánh. Khi handler không nhận được record, hãy kiểm tra bytes thật, headers và target type trước khi thay đổi code nghiệp vụ.

## 7. Producer gửi JSON đúng cách

Có nhiều cách producer phát event:

- Gửi POJO để converter/binder mã hóa dựa trên content type.
- Gửi bytes JSON đã mã hóa và khai báo rõ content type nếu truyền qua Spring Message.
- Dùng native serializer của broker; lúc đó wire format phải được chọn đồng nhất.

Ví dụ tạo message JSON bytes rõ ràng bằng Jackson:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

ObjectMapper objectMapper = new ObjectMapper();
OrderCreated event = new OrderCreated("evt-101", "ord-101", 250_000);

byte[] bytes = objectMapper.writeValueAsBytes(event);
Message<byte[]> message = MessageBuilder.withPayload(bytes)
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .setHeader("eventId", event.eventId())
    .build();
~~~

Trong đoạn code, `ObjectMapper` tạo JSON bytes và header khai báo `application/json`. Khi message đi qua Kafka/Rabbit/Pulsar, binder và producer configuration quyết định header được mang sang broker như thế nào.

Không encode một đối tượng hai lần: nếu producer đã biến POJO thành JSON String rồi converter tiếp tục serialize String thành JSON, wire format có thể thành một **chuỗi JSON được đặt trong dấu ngoặc kép** thay vì JSON object.

## 8. JSON object và JSON string là hai wire format khác nhau

Hai payload trông gần giống nhưng khác semantics:

~~~json
{"eventId":"evt-101","orderId":"ord-101","totalCents":250000}
~~~

~~~json
"{\"eventId\":\"evt-101\",\"orderId\":\"ord-101\",\"totalCents\":250000}"
~~~

Payload đầu là một JSON object. Payload thứ hai là một JSON string có nội dung giống JSON object. Khi Java target là `OrderCreated`, Jackson không nhất thiết chuyển được chuỗi JSON thứ hai thành object nếu không có cơ chế chuyển đổi riêng.

Trong log, hai chuỗi có thể bị escape khác nhau nên rất dễ đọc nhầm. Hãy kiểm tra:

1. Byte đầu thực tế là dấu `{` hay dấu nháy kép `"`.
2. Producer đang gửi POJO, String, byte[] hay `Message<?>`.
3. Có bước `writeValueAsString` rồi lại qua JSON converter hay không.
4. Consumer target là POJO hay String.

Sửa **điểm encode** thay vì thêm xử lý “parse hai lần” trong mọi consumer, trừ khi phải tương thích tạm thời với dữ liệu legacy đã tồn tại.

## 9. JSON array không thể chuyển thành một POJO đơn

Nếu producer gửi:

~~~json
[
  {"eventId":"evt-1","orderId":"ord-1","totalCents":10000},
  {"eventId":"evt-2","orderId":"ord-2","totalCents":20000}
]
~~~

nhưng bean khai báo `Consumer<OrderCreated>`, JSON root là array trong khi target là object. Đây là mismatch về cấu trúc; thay `contentType` không giải quyết được.

Nếu hợp đồng thực sự là một record chứa danh sách, khai báo wrapper:

~~~java
record OrderBatch(java.util.List<OrderCreated> orders) {}

@Bean
Consumer<OrderBatch> processBatch(OrderService service) {
    return batch -> batch.orders().forEach(service::handle);
}
~~~

Payload tương ứng phải là:

~~~json
{
  "orders": [
    {"eventId":"evt-1","orderId":"ord-1","totalCents":10000},
    {"eventId":"evt-2","orderId":"ord-2","totalCents":20000}
  ]
}
~~~

Không nhầm batch JSON nghiệp vụ với Kafka/Rabbit binder batch-mode: binder batch có thể phát một tập message theo API khác, bao gồm header/ack semantics riêng. Chọn một hợp đồng rõ ràng và kiểm thử nó.

## 10. Sai kiểu field và schema drift

Một số ví dụ gây mismatch:

~~~json
{"eventId":"evt-1","orderId":"ord-1","totalCents":"not-a-number"}
~~~

~~~json
{"eventId":"evt-2","orderId":"ord-2","totalCents":null}
~~~

~~~json
{"eventId":"evt-3","orderId":"ord-3","totalCents":999999999999999999999999}
~~~

`totalCents` là `long`, vì vậy giá trị chữ, null hoặc vượt range có thể lỗi hoặc có hành vi coercion theo Jackson configuration. Không dựa vào coercion mặc định để bảo vệ nghiệp vụ.

Những nguyên nhân cần rà soát:

- Trường được đổi tên nhưng consumer vẫn dùng tên cũ.
- Type từ String sang số, từ object sang array, hoặc enum thêm giá trị mới.
- Producer phát schema version mới trước khi consumer hỗ trợ.
- Field bắt buộc bị thiếu, giá trị null hoặc mất precision.
- Timestamp dùng định dạng không được ObjectMapper cấu hình hỗ trợ.

Schema compatibility phải là một quyết định phát hành: backward, forward hay full compatibility tùy tiến trình nâng cấp. Test với nhiều fixture version cũ/mới trước khi triển khai.

## 11. Java record, constructor và Jackson

Spring Cloud Stream dựa trên conversion và thư viện JSON tương ứng để tạo target POJO. Đối tượng Java phải có cấu trúc có thể bind:

~~~java
public record CustomerEvent(
    String customerId,
    String eventType,
    java.time.Instant occurredAt
) {}
~~~

Với record, dùng phiên bản Jackson hỗ trợ Java record phù hợp. Với class immutable, cần constructor/property names hoặc annotation phù hợp; với Java time type, cần module và cấu hình tương ứng nếu dự án tự cung cấp ObjectMapper.

Ví dụ POJO thiếu constructor thích hợp:

~~~java
class LegacyOrder {
    private final String orderId;

    LegacyOrder(String orderId) {
        this.orderId = orderId;
    }
}
~~~

Class này có thể cần `@JsonCreator` và `@JsonProperty`, hoặc thay bằng record trong phiên bản Java/Jackson hỗ trợ. Không đổi thành field public chỉ để converter hoạt động nếu nó phá tính bất biến của model.

Khi lỗi cho biết “no Creators, like default constructor, exist”, kiểm tra target class và ObjectMapper thay vì cho rằng broker đã gửi payload hỏng.

## 12. Lỗi thiếu `contentType`: tìm nguồn mất header

Giả sử producer gửi JSON bytes đúng nhưng consumer không thấy `contentType`. Những khả năng:

1. Producer chỉ gửi bytes, không gắn header.
2. Producer gắn header nhưng code bridge tái tạo message và làm mất header.
3. Header được lưu dưới tên/kiểu khác do mapping của broker binder.
4. Một non-Spring producer dùng native protocol nhưng không khai báo content type tương đương.
5. Một layer converter trước đó đã biến message thành kiểu khác.

Hãy kiểm tra header ở các ranh giới:

~~~text
producer Spring Message
  -> broker record headers / AMQP properties / Pulsar metadata
  -> Spring Cloud Stream Message
  -> function parameter
~~~

Không phải broker nào cũng có cùng cơ chế truyền header. Một số metadata được map, một số không tồn tại hoặc không phù hợp khi đi qua binder khác.

Nếu hợp đồng topic luôn là JSON, cấu hình `content-type: application/json` trên input binding là giải pháp thường gặp khi không có header; nhưng vẫn cần xác nhận không có header mâu thuẫn và target type đúng.

## 13. Gắn `contentType` trong Message<T> đúng cách

Khi dùng Spring Message API:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<String> jsonMessage = MessageBuilder
    .withPayload("{\"eventId\":\"evt-101\",\"orderId\":\"ord-101\",\"totalCents\":250000}")
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .build();
~~~

Ở đây header là Spring `MessageHeaders.CONTENT_TYPE` và giá trị MIME type được tạo bằng `MimeTypeUtils.APPLICATION_JSON`. Đó là cách tránh typo khi tạo message thủ công.

Nếu đã có producer đang phát String JSON, cần xác minh pipeline có serialize String thêm một lần hay không. Nếu cần kiểm soát wire bytes chặt chẽ, dùng `byte[]` được tạo bởi ObjectMapper và một integration test đọc raw record trên broker.

Không nên set header `contentType` thành Java class name. `com.example.OrderCreated` không phải MIME type.

## 14. Binding `content-type` là fallback, không phải công cụ sửa schema

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

giúp định nghĩa định dạng mong đợi khi binder áp dụng message conversion. Tính năng relaxed binding có thể nhận các biến thể `contentType`/`content-type` trong Spring configuration, nhưng nên dùng một cách nhất quán.

Nó **không** sửa:

- JSON bị cắt cụt hoặc bytes không phải UTF-8.
- JSON array cần POJO đơn.
- Enum mới không được consumer hỗ trợ.
- Class không deserialize được vì thiếu creator.
- Native Kafka deserializer cấu hình nhầm.
- Avro/Protobuf bytes bị coi là JSON.

Nếu header của từng message đã ghi sai `text/plain`, cần sửa nguồn gửi hoặc chuyển header an toàn tại ranh giới được kiểm soát; không tin rằng binding property sẽ luôn ghi đè.

## 15. Đọc kiểu payload thực thay vì đoán bằng toString()

Trong lúc chẩn đoán, dùng một function tạm thời nhận `Message<byte[]>` hoặc một consumer raw ở môi trường test để quan sát những gì thực sự được đưa vào. Ví dụ:

~~~java
import java.util.HexFormat;
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<byte[]>> inspectRawPayload() {
    return message -> {
        byte[] bytes = message.getPayload();
        int count = Math.min(bytes.length, 16);
        String firstBytes = HexFormat.of()
            .formatHex(java.util.Arrays.copyOf(bytes, count));

        System.out.printf("payloadLength=%d firstBytes=%s contentType=%s%n",
            bytes.length, firstBytes,
            message.getHeaders().get("contentType"));
    };
}
~~~

Đây là diagnostic bean minh họa cho môi trường thử nghiệm; đổi function definition có thể khiến consumer nhóm mới hoặc thay đổi cách đọc message. Không thêm diagnostic consumer vào production group đang chạy mà không có quy trình.

**Bảo mật:** chỉ in length, MIME type, eventId an toàn và một lượng nhỏ bytes nếu chính sách cho phép. Raw payload có thể chứa dữ liệu cá nhân, token hoặc thông tin thanh toán. Trong production, ưu tiên hash/checksum, kích thước và metadata thay cho dump message toàn phần.

Trong native mode, `Message<byte[]>` không nhất thiết có thể nhận mọi wire format nếu deserializer đã thất bại trước khi tạo message; khi đó phải đọc raw record bằng client phù hợp ở môi trường cô lập.

## 16. Kiểm tra byte order mark, charset và encoding

Phần lớn JSON event dùng UTF-8. Các sai lệch có thể gặp:

- Producer encode UTF-16 nhưng khai báo UTF-8.
- Payload có byte order mark (BOM) ngoài kỳ vọng của converter.
- Chuỗi được encode bằng một charset và decode bằng charset khác.
- Content type bị gắn `text/plain` không kèm charset nhưng consumer giả định một encoding khác.
- Payload bị nén hoặc mã hóa nhị phân, sau đó được đọc như JSON text.

Ví dụ chẩn đoán bytes hợp lệ trước khi parse:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

String decodeUtf8(byte[] bytes) throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
}
~~~

Đoạn code là công cụ test/diagnostic, không thay thế Jackson JSON parsing. Nếu `decodeUtf8` thành công nhưng POJO conversion lỗi, điều tra cấu trúc JSON/type/schema thay vì network encoding.

Không tự ý thay charset toàn topic nếu producer cũ vẫn đang phát theo hợp đồng trước đó; xử lý chuyển tiếp version có kiểm soát.

## 17. `String`, `byte[]`, `Object` và `Message<T>` có tác động khác nhau

Chữ ký functional bean ảnh hưởng việc framework quyết định có cần chuyển đổi không:

| Chữ ký | Ý định | Điều cần chú ý |
|---|---|---|
| `Consumer<OrderCreated>` | Nhận POJO đã convert | JSON shape và target class phải tương thích |
| `Consumer<String>` | Nhận văn bản | Có thể nhận JSON text nhưng không tự tạo OrderCreated |
| `Consumer<byte[]>` | Nhận bytes | Handler tự chịu trách nhiệm diễn giải bytes khi phù hợp |
| `Consumer<Message<OrderCreated>>` | POJO kèm header | Cần giữ đúng header mapping, payload type |
| `Consumer<Message<byte[]>>` | Bytes kèm header | Hữu ích để chẩn đoán trong mode tương thích |
| `Function<OrderCreated, OrderAccepted>` | Convert input và output | Cần kiểm tra cả serialization phía output |

Đổi target từ `OrderCreated` sang `String` có thể tạm làm exception biến mất nhưng đồng thời khiến handler nhận JSON thô, không còn validation/typing như mong muốn. Đây không phải fix đầy đủ.

Nếu dùng `Object` hoặc raw `Message<?>`, framework có thể không đủ target type để deserialize chính xác; logic phải kiểm tra kiểu và xử lý an toàn, tránh ép kiểu bằng dự đoán.

## 18. Lỗi `ClassCastException` sau khi conversion

Ví dụ code xấu:

~~~java
@Bean
Consumer<Object> processOrder() {
    return payload -> {
        OrderCreated order = (OrderCreated) payload; // may throw
        System.out.println(order.orderId());
    };
}
~~~

Một payload dạng `Map`, `String` hoặc `byte[]` không thể được cast thẳng sang `OrderCreated`. Nếu `ClassCastException` chỉ xuất hiện trong handler, kiểm tra:

1. Functional bean generic type có đầy đủ không?
2. Đã dùng raw `Function`/`Consumer` làm mất type information chưa?
3. Có custom MessageConverter trả về Map không?
4. Có bridge hoặc router thay đổi payload type không?
5. Native serializer có đưa ra object khác target không?

Giải pháp ưu tiên là khai báo generic type đúng và cấu hình converter/Serde tương ứng, không dùng phép cast thiếu kiểm tra. Nếu phải chấp nhận nhiều schema, tạo envelope/versioned DTO và ánh xạ sang domain model rõ ràng.

## 19. Kafka binder: native decoding thay đổi nơi phát sinh lỗi

Trong luồng Kafka chuẩn, Spring Cloud Stream Kafka binder có thể làm việc với bytes và dùng message conversion ở tầng Spring. Khi bật **native decoding**, Kafka client `Deserializer`/SerDe chịu trách nhiệm tạo object trước khi function được gọi.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            useNativeDecoding: true
~~~

Lúc đó, client deserializer cho value phải khớp wire format thực tế. Nếu producer dùng StringSerializer, consumer dùng JSON deserializer hoặc ngược lại, lỗi có thể xuất hiện ngay trong poll trước Spring conversion.

Tên và cách đặt key/value deserializer phụ thuộc Spring Cloud Stream Kafka binder, Spring Kafka và Spring Boot version. Kiểm tra cấu hình consumer properties đang có thay vì chỉ thêm `content-type: application/json` và hy vọng sửa được native error.

Một số error handling của Kafka dành cho lỗi deserialize ở poll yêu cầu cơ chế đặc biệt như `ErrorHandlingDeserializer` và điều chỉnh DLQ/error handler theo version. Lỗi xảy ra trước khi message được tạo có thể không đi qua Function/DLQ như lỗi xử lý bình thường.

## 20. Kafka key và value có thể dùng SerDe khác nhau

Kafka record có **key** và **value** độc lập. Lỗi đôi khi ở key nhưng log bị hiểu thành lỗi JSON payload:

~~~text
key bytes:   "customer-42"  -> StringDeserializer
value bytes: {"eventId":"evt-42", ...} -> JSON converter/Deserializer
~~~

Nếu producer gửi key là UUID bytes nhưng consumer config dùng StringDeserializer, routing và key metadata có thể hỏng hoặc decode sai mà value JSON vẫn hợp lệ.

Khi điều tra, ghi rõ:

- Exception xảy ra ở key hay value deserializer?
- `key.serializer`/`key.deserializer` và tương ứng cho value là gì?
- Có schema registry, custom serializer hoặc wire prefix đặc biệt không?
- Consumer dùng native hay Spring conversion?
- Payload có phải record được ghi trước khi đổi serializer không?

Không thay consumer key deserializer chỉ để làm payload JSON thành công nếu key vẫn cần được dùng cho partition hoặc business ordering.

## 21. Spring Kafka type headers và rủi ro type mismatch

Trong một số mô hình dùng Spring Kafka JSON serializer/deserializer, Kafka record có thể chứa type headers mô tả Java class. Nếu producer và consumer không cùng package/class, hoặc bị giới hạn trusted packages, deserialize có thể thất bại.

Ví dụ producer có type header trỏ tới `com.producer.OrderCreated` trong khi consumer chỉ có `com.consumer.OrderCreated`. Dù JSON fields tương thích, consumer có thể không load được class được ghi trong header.

Giải pháp thiết kế:

- Dùng contract type/envelope độc lập với tên Java package.
- Cấu hình JSON deserializer dùng target class rõ ràng hoặc type mapping được kiểm soát.
- Kiểm soát việc đọc/bỏ qua type headers theo framework version.
- Hạn chế trusted packages đúng phạm vi; không mở `*` một cách bừa bãi trong production.
- Test producer/consumer của hai release khác nhau với topic thực tế.

`contentType` và Spring Kafka type headers là **hai cơ chế khác nhau**. Đặt `contentType=application/json` không sửa được type header trỏ đến class không tồn tại.

## 22. RabbitMQ binder: AMQP properties và Spring headers

RabbitMQ sử dụng AMQP message properties, trong đó có `content_type`, và có headers riêng. Spring Cloud Stream Rabbit binder có thể chuyển metadata này thành Spring Message headers khi nhận dữ liệu.

Các trường hợp cần xác minh:

- Producer ngoài Spring không khai báo `content_type` hoặc khai báo `text/plain` khi bytes thực tế là JSON.
- Producer gửi một đối tượng nhị phân Java serialization thay vì JSON.
- Producer cấu hình serializer khác consumer.
- Message qua exchange/queue đúng nhưng binding `content-type` chưa đặt.
- Tên queue/group thay đổi khiến consumer mới nhận một tập message cũ có wire format khác.

Ví dụ binding consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          content-type: application/json
~~~

Trong hệ thống có non-Spring publisher, kiểm tra raw AMQP body và properties bằng công cụ quản trị/test client phù hợp. Không dựa hoàn toàn vào màn hình queue UI, vì UI có thể hiển thị body theo text dù bytes không được khai báo MIME type chính xác.

## 23. Pulsar binder: Schema và content type không phải một thứ

Pulsar client có cơ chế `Schema` như `Schema.JSON`, `Schema.STRING`, `Schema.BYTES` hoặc schema được quản lý ở broker. Cấu hình schema native ảnh hưởng cách producer mã hóa và consumer giải mã message.

Ví dụ một client Pulsar native:

~~~java
import org.apache.pulsar.client.api.PulsarClient;
import org.apache.pulsar.client.api.Producer;
import org.apache.pulsar.client.api.Schema;

Producer<OrderCreated> producer = pulsarClient
    .newProducer(Schema.JSON(OrderCreated.class))
    .topic("persistent://commerce/orders/events")
    .create();
~~~

Nếu consumer kỳ vọng `Schema.STRING` nhưng producer sử dụng JSON schema, kết quả không tương đương việc Spring Cloud Stream tự convert JSON bytes theo header. Phải xác định nơi schema được áp dụng (native Pulsar client, binder hoặc Spring message converter) và target type.

Message properties của Pulsar không tự tương đương tuyệt đối với Spring `contentType` ở mọi version/binder. Không giả định header Kafka/Rabbit sẽ tự giữ nguyên khi bridge sang Pulsar. Kiểm tra schema và message headers sau một vòng publish/consume thực sự.

## 24. JSON khác Avro, Protobuf và schema registry

Một topic có thể chứa bytes của Avro/Protobuf hoặc wire format có prefix/magic bytes/schema ID. Bytes đó không thể biến thành JSON chỉ bằng cách đặt header `contentType=application/json`.

Ví dụ:

~~~text
Actual bytes:
  [wire prefix / schema id][binary Avro payload]

Incorrect assumption:
  contentType = application/json
  targetType  = OrderCreated
~~~

Lỗi parse JSON ở byte đầu không có nghĩa broker làm hỏng record. Có thể producer đang dùng serializer khác với consumer.

Giải pháp:

1. Xác định format thực từ producer và schema registry.
2. Kiểm tra schema ID/version, compatibility và serializer config.
3. Chọn decoder/Serde phù hợp.
4. Chỉ dùng message conversion JSON sau khi dữ liệu đã ở định dạng JSON hoặc POJO đúng.
5. Tách migration sang format mới bằng topic/version hoặc quy trình dual-read được kiểm thử.

Không dùng `new String(bytes, UTF_8)` rồi parse JSON đối với dữ liệu binary format.

## 25. Header bị mất khi chuyển từ Function sang StreamBridge

Một pipeline nhận `Message<OrderCreated>` rồi publish sang output có thể vô tình làm mất content type và correlation headers:

~~~java
@Bean
Consumer<Message<OrderCreated>> forward(StreamBridge bridge) {
    return incoming -> {
        bridge.send("outboundOrders", incoming.getPayload());
    };
}
~~~

Khi gửi chỉ payload, code trên không giữ các header nghiệp vụ của incoming message. Nếu output dựa vào header MIME hoặc event version, kết quả có thể khác dự kiến.

Ví dụ chuyển những header **được lựa chọn**:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;
import org.springframework.cloud.stream.function.StreamBridge;
import java.util.function.Consumer;

@Bean
Consumer<Message<OrderCreated>> forward(StreamBridge bridge) {
    return incoming -> {
        Object correlationId = incoming.getHeaders().get("correlationId");
        MessageBuilder<OrderCreated> builder = MessageBuilder
            .withPayload(incoming.getPayload())
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON);
        if (correlationId != null) {
            builder.setHeader("correlationId", correlationId);
        }
        Message<OrderCreated> outbound = builder.build();
        if (!bridge.send("outboundOrders", outbound)) {
            throw new IllegalStateException("Bridge did not accept the message");
        }
    };
}
~~~

Không copy bừa mọi consumer/broker header như ack handle, offset hay native partition metadata. Chọn và kiểm thử các business headers, trace headers cần có. Nếu correlationId null, bỏ qua header hoặc có quy tắc tạo mới rõ ràng.

## 26. Kiểm tra tên binding và destination thực tế

Một lỗi được mô tả là “consumer không parse JSON” có thể thực chất do consumer nhận dữ liệu từ **topic khác** sau khi rename bean/function.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
~~~

Tên binding là `processOrder-in-0`, không phải `input` nếu chưa khai báo alias. Khi YAML vẫn đặt conversion properties dưới `spring.cloud.stream.bindings.input`, nó có thể không ảnh hưởng binding thực sự đang chạy.

Rà lại:

- `spring.cloud.function.definition` có chọn đúng function bean không?
- `destination` đang trỏ topic/queue nào?
- `group` và tên subscription có đổi không?
- `binder` nào đang được chọn trong ứng dụng nhiều binder?
- Có bản cũ của topic chứa payload khác format không?
- Có điều kiện routing khiến function khác nhận nhầm message không?

Khi debug, không xóa group/offset hoặc queue chỉ để “cho mất lỗi”. Điều đó có thể gây mất hoặc đọc lại dữ liệu ngoài kế hoạch.

## 27. Retry không sửa được JSON sai định dạng

Một payload JSON không hợp lệ thường là lỗi **không thể retry**: đọc lại cùng bytes nhiều lần vẫn lỗi. Khác với lỗi HTTP 503 hoặc database timeout có thể phục hồi sau một khoảng thời gian.

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Syntax JSON sai | Dấu ngoặc thiếu, JSON bị cắt | Non-retryable → DLQ/quarantine |
| Field sai schema | Enum mới, kiểu dữ liệu không tương thích | Kiểm tra compatibility, DLQ nếu không tự sửa |
| Type header sai | Class không tồn tại/trusted packages | Sửa serializer/type mapping, kiểm tra dữ liệu tồn |
| Service phụ thuộc tạm lỗi | HTTP 503, timeout, connection reset | Retry giới hạn, backoff |
| DB conflict có idempotency | Cùng eventId được gửi lại | Deduplicate/ghi nhận thành công theo nghiệp vụ |
| Broker outage | Kết nối bị ngắt, leader change | Client reconnect/retry theo binder |

Nếu chuyển tất cả exception conversion vào retry với `maxAttempts` lớn, một poison message có thể làm tăng CPU, lag và khiến partition xử lý chậm. DLQ phải lưu đủ context như eventId, topic, lỗi, schema version và thời điểm, nhưng tránh đẩy dữ liệu nhạy cảm vào logs không kiểm soát.

## 28. Lỗi xảy ra trước khi handler được gọi: xử lý khác gì?

Một exception ở native Kafka deserializer có thể phát sinh ngay lúc poll, trước khi Spring tạo `Message<OrderCreated>` và trước khi handler của ứng dụng được gọi. Khi đó:

- `try/catch` đặt trong `Consumer<OrderCreated>` không thể bắt lỗi.
- Retry logic ở service method có thể không được kích hoạt.
- DLT/DLQ của binder có thể cần cấu hình hỗ trợ lỗi deserialize riêng.
- Một record hỏng có thể cản trở tiến độ consumer nếu deserializer/error handler không xử lý đúng.

Để kiểm tra:

1. Quan sát stack trace đầu tiên, không chỉ exception wrapper cuối.
2. Xác định lỗi ở `poll()`/deserializer hay ở function invocation.
3. Kiểm tra consumer native decoding và serializer/deserializer value/key.
4. Xem cơ chế `ErrorHandlingDeserializer` hoặc error handler tương ứng của Spring Kafka version.
5. Kiểm thử record hỏng được skip, DLQ hay giữ nguyên offset theo chính sách được phê duyệt.

Không commit/skip offset tùy tiện để làm consumer “chạy lại”. Nếu message hỏng phải được cách ly, cần lưu bằng chứng và có khả năng reprocess có kiểm soát.

## 29. Test Binder: tái hiện thành công và failure một cách ổn định

Với functional bean `acceptOrder`, Spring Cloud Stream Test Binder cho phép gửi bytes JSON tới input destination và kiểm tra output:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(properties = {
    "spring.cloud.function.definition=acceptOrder",
    "spring.cloud.stream.bindings.acceptOrder-in-0.destination=orders.events",
    "spring.cloud.stream.bindings.acceptOrder-in-0.content-type=application/json",
    "spring.cloud.stream.bindings.acceptOrder-out-0.destination=orders.accepted"
})
@Import(TestChannelBinderConfiguration.class)
class JsonConversionTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void convertsJsonBytesIntoOrderCreated() {
        byte[] json = """
            {"eventId":"evt-101","orderId":"ord-101","totalCents":250000}
            """.getBytes(StandardCharsets.UTF_8);

        input.send(
            MessageBuilder.withPayload(json)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build(),
            "orders.events"
        );

        Message<byte[]> result = output.receive(2_000, "orders.accepted");
        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .contains("evt-101", "ACCEPTED");
    }
}
~~~

Ở test này, header `contentType` được đặt chính xác và binding cũng khai báo fallback. Sau khi baseline pass, tạo biến thể test bỏ header, thay header bằng text/plain và gửi JSON sai để quan sát **cơ chế thực** của phiên bản dự án.

Test Binder xác minh conversion trong app context nhưng không mô phỏng đầy đủ wire headers, Kafka native deserializer, Rabbit AMQP properties hoặc Pulsar Schema. Các trường hợp đó cần integration test riêng với broker.

## 30. Test các trường hợp lỗi mà không làm treo suite

Một test matrix thực tế:

| Case | Payload | Header | Target | Kết quả cần xác minh |
|---|---|---|---|---|
| J01 | JSON object đúng schema | application/json | OrderCreated | Convert thành công |
| J02 | JSON object đúng schema | Không có header | OrderCreated | Fallback binding hoặc lỗi được giải thích |
| J03 | JSON object đúng schema | text/plain | OrderCreated | Xác minh ưu tiên header và converter |
| J04 | JSON array | application/json | OrderCreated | Schema/shape mismatch được phân loại |
| J05 | JSON string bọc JSON object | application/json | OrderCreated | Không bị double encode âm thầm |
| J06 | Field sai kiểu | application/json | OrderCreated | Parse/type error rõ ràng |
| J07 | Bytes Avro hoặc nén | application/json | OrderCreated | Không bị nhầm là JSON |
| J08 | POJO hợp lệ | application/json | OrderCreated | Function và output đúng |
| J09 | Event schema cũ | application/json | OrderCreated | Backward compatibility đúng chính sách |
| J10 | Key bytes sai SerDe | Native Kafka mode | Deserializer đích | Lỗi key được phân loại đúng |

Với negative test qua broker, đặt timeout hữu hạn và không để retry vô hạn. Xác minh kết quả là exception, DLQ hoặc thông điệp bị reject theo chính sách đã xác định; không chỉ đợi output rồi kết luận thiếu output là đúng.

Nếu test dùng subscription/group chung từ lần trước, có thể có backlog cũ làm nhiễu. Tạo destination/group riêng theo run hoặc reset theo quy trình an toàn cho môi trường test.

## 31. Log và metric cần thu thập khi troubleshooting

Ghi đủ metadata phục vụ phân tích nhưng không lộ payload:

- `bindingName`, `destination`, `binderName` và consumer group/subscription.
- `eventId` hoặc correlation ID được kiểm soát.
- `contentType` nhận được và binding-level default.
- Payload type trước và sau conversion nếu có thể quan sát.
- Payload length và checksum/hash cho trường hợp đối soát.
- Error stage: poll/deserializer, conversion hoặc handler.
- Exception class, JSON property path và schema version.
- Retry attempt, DLQ destination và outcome cuối cùng.
- Kafka topic/partition/offset; Rabbit queue/redelivered flag; Pulsar message ID/subscription khi phù hợp.

Không gắn eventId làm tag metric có cardinality cao. Dùng metrics với nhãn có số giá trị giới hạn như binding, error category, contentType và outcome. Dữ liệu chi tiết có thể nằm trong structured log/tracing với chính sách sampling và retention.

Một dashboard hữu ích sẽ phân biệt `deserialization_error_count`, `conversion_error_count`, `business_error_count` và `dlq_publish_error_count` theo tên chỉ số do dự án định nghĩa. Đừng giả định đây là metric mặc định của mọi binder.

## 32. Runbook: sửa lỗi JSON trong production

Quy trình khuyến nghị:

1. **Khoanh vùng:** xác định service/version, binding, topic/queue, thời gian bắt đầu lỗi và số message bị ảnh hưởng.
2. **Xác định stage:** lỗi xuất hiện trước function, trong conversion hay trong handler?
3. **Kiểm tra bytes an toàn:** payload length, magic prefix/encoding, JSON object/array/string.
4. **Đối chiếu header:** `contentType` trên message, binding `content-type`, native mode.
5. **Đối chiếu Java type:** function generic signature, record/class, Jackson creator, enum/time fields.
6. **Đối chiếu serializer:** producer bytes, broker wire format, Kafka key/value SerDe hoặc Pulsar Schema.
7. **Kiểm tra thay đổi gần nhất:** schema release, package rename, header mapping, binder upgrade.
8. **Phân loại lỗi:** invalid event hay mismatch do bản phát hành?
9. **Cô lập an toàn:** giới hạn retry cho poison message; bảo quản event có thể reprocess.
10. **Khắc phục ở đúng lớp:** producer encode, binder config, target type, deserializer hoặc schema compatibility.
11. **Kiểm thử:** fixture pass/fail và broker integration test tương ứng.
12. **Xác minh sau rollout:** lag giảm, error rate về ngưỡng, event ID đối soát, DLQ không tăng bất thường.

Không đổi group/offset, xóa queue, skip record hoặc drop payload chỉ để làm lỗi biến mất. Những hành động đó có thể tạo mất dữ liệu âm thầm.

~~~mermaid
flowchart TD
    A[JSON error alert] --> B{Exception occurred where?}
    B -->|Broker poll| C[Inspect SerDe / schema / native mode]
    B -->|Spring conversion| D[Inspect contentType, bytes and target type]
    B -->|Business handler| E[Inspect validation and side effects]
    C --> F{Wire format matches?}
    D --> F
    F -->|No| G[Fix producer / deserializer / mapping]
    F -->|Yes| H[Check DTO/Jackson/schema compatibility]
    E --> I[Classify retryable vs non-retryable]
    G --> J[Test with real broker]
    H --> J
    I --> J
    J --> K[Reconcile ID, DLQ and lag]
~~~

## 33. Những sửa chữa hấp tấp cần tránh

- Không ép `String` thành POJO bằng cast để né converter.
- Không thêm `contentType=application/json` cho bytes binary Avro/Protobuf.
- Không mở toàn bộ trusted packages của JSON deserializer trong production khi chưa đánh giá rủi ro.
- Không thay function input thành `Object` chỉ để exception biến mất mà không xử lý type.
- Không “parse hai lần” ở mọi consumer để che lỗi double encoding nếu có thể sửa producer.
- Không bỏ qua exception Jackson rồi ack/commit như thành công.
- Không bật retry vô hạn cho JSON không hợp lệ.
- Không chuyển mọi message sai vào DLQ mà không có thông tin để điều tra/reprocess.
- Không dump toàn bộ raw payload nhạy cảm vào logs.
- Không thay group, topic hoặc subscription để né backlog có message lỗi.
- Không chỉ kiểm thử với Test Binder nếu lỗi nằm ở Kafka/Rabbit/Pulsar wire layer.

## 34. Checklist chẩn đoán trước khi đóng sự cố

- [ ] Xác định được exception gốc và stage gây lỗi.
- [ ] Có sample wire bytes an toàn, payload size và encoding được xác minh.
- [ ] Phân biệt được JSON object, JSON array, JSON string và non-JSON bytes.
- [ ] Header contentType và binding content-type đã đối chiếu theo đúng precedence.
- [ ] Không nhầm contentType với Java class/type header hoặc broker native Schema.
- [ ] Functional bean có generic type đầy đủ và đúng target.
- [ ] Record/POJO/Jackson hỗ trợ field, constructor và schema version thực tế.
- [ ] Kafka key/value serializer/deserializer hoặc Pulsar Schema tương thích producer.
- [ ] Rabbit AMQP content_type/header mapping được xác minh nếu có Rabbit binder.
- [ ] Bridge/StreamBridge giữ các business headers quan trọng.
- [ ] Có negative test cho malformed JSON và wrong type.
- [ ] Retry/DLQ được cấu hình phù hợp với lỗi transient/non-retryable.
- [ ] Không có event bị mất dấu do skip offset, đổi group hoặc xóa queue.
- [ ] Sau sửa lỗi, lag/backlog, error rate và DLQ đạt tiêu chí vận hành.

## 35. Tổng kết

Lỗi JSON trong Spring Cloud Stream không có một nguyên nhân duy nhất. Một message chỉ được xử lý đúng khi **wire bytes, content type, converter/Serde và Java target type** cùng thống nhất. Thiếu `contentType` có thể được giải quyết ở producer hoặc bằng binding-level fallback nếu topic thực sự là JSON; nhưng JSON sai cấu trúc, schema drift, native deserializer sai hoặc type header không tương thích cần cách khắc phục khác.

Với Kafka, kiểm tra native decoding, key/value SerDe và lỗi xảy ra ở poll; với RabbitMQ, kiểm tra AMQP body, content_type và queue; với Pulsar, kiểm tra schema native, topic metadata và subscription. Giữ nguyên event ID, phân loại lỗi trước khi retry, cô lập poison message an toàn và kiểm thử cả bằng Test Binder lẫn broker thật. Mục tiêu không chỉ là làm exception biến mất mà phải khôi phục đúng hợp đồng message và bảo toàn trạng thái xử lý của hệ thống.

## Tài liệu tham khảo

- [Spring Cloud Stream — Content Type and Message Conversion](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/content-type-management.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar-binder.html)
- [Jackson Databind — Deserialization Features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features)

