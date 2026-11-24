# Cơ chế chọn MessageConverter và đăng ký bộ chuyển đổi riêng

Spring Cloud Stream cần chuyển payload giữa dạng dữ liệu của broker và kiểu Java mà function sử dụng. Cơ chế chuyển đổi này được thực hiện thông qua các `MessageConverter` của Spring Messaging. Converter phù hợp được chọn dựa trên kiểu nội dung (MIME type/content type), kiểu đích hoặc kiểu payload, và khả năng hỗ trợ của converter.

Khi định dạng message chuẩn của ứng dụng không được hỗ trợ đầy đủ bởi converter mặc định, có thể đăng ký converter riêng. Việc này cần được thực hiện có kiểm soát: xác định content type, kiểu Java được hỗ trợ, cách chuyển đổi hai chiều và cách xử lý dữ liệu không hợp lệ. Cũng cần phân biệt message conversion của Spring Cloud Stream với serialization/deserialization gốc do binder và broker thực hiện.

## 1. MessageConverter làm nhiệm vụ gì?

Một message trong Spring Messaging có payload và headers. Payload có thể là object Java, chuỗi hoặc mảng byte; headers mang metadata như content type, ID và correlation ID.

`MessageConverter` chuyển đổi payload giữa biểu diễn message và kiểu Java mà ứng dụng cần. Hai thao tác chính là:

- **Inbound conversion**: chuyển payload nhận từ binding sang kiểu tham số của function, ví dụ byte array JSON thành `OrderCreated`.
- **Outbound conversion**: chuyển object Java do function trả về thành dạng payload có thể truyền qua broker, ví dụ `OrderAccepted` thành JSON bytes.

Luồng tổng quát:

```mermaid
flowchart LR
    A[Broker record / message] --> B[Binder nhận dữ liệu]
    B --> C[Content type + target Java type]
    C --> D[MessageConverter phù hợp]
    D --> E[Function với payload Java]
    E --> F[Function trả payload]
    F --> G[MessageConverter đầu ra]
    G --> H[Binder gửi dữ liệu]
    H --> I[Broker]
```

Đây là mô hình logic của đường xử lý message. Tùy binder và cấu hình native encoding/decoding, một số bước chuyển đổi có thể do serializer/deserializer của broker đảm nhiệm thay cho converter của Spring Cloud Stream.

## 2. Content type tham gia chọn converter như thế nào?

Content type mô tả định dạng của payload. Một số giá trị thường gặp:

| Content type | Dạng payload thường dùng | Ví dụ |
|---|---|---|
| `application/json` | JSON | `{"orderId":"o-1"}` |
| `text/plain` | Văn bản | `order-created` |
| `text/csv` | Dữ liệu CSV | `o-1,c-1,125000` |
| `application/octet-stream` | Dữ liệu nhị phân | byte array |
| `application/avro` | Dữ liệu Avro | Avro binary hoặc định dạng theo cấu hình |
| `application/x-protobuf` | Dữ liệu Protocol Buffers | Protobuf binary |

Trong Spring Cloud Stream, content type có thể được xác định từ header `contentType` của message, thuộc tính `content-type` của binding hoặc giá trị mặc định của framework. Header message có thể ghi đè cấu hình binding. Nếu không chỉ định, Spring Cloud Stream thường dùng `application/json` làm mặc định cho message conversion. Hãy kiểm tra phiên bản framework và binder đang dùng khi cần dựa vào thứ tự ưu tiên này.

Ví dụ cấu hình content type cho binding:

```yaml
spring:
  cloud:
    function:
      definition: receiveOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: orders.created
          group: order-service
          content-type: application/json
```

Binding khai báo rằng payload được xử lý như JSON. Khi function nhận một kiểu Java cụ thể, converter JSON có thể giải mã payload thành kiểu đó:

```java
@Bean
Consumer<OrderCreated> receiveOrder(OrderService service) {
    return service::handle;
}
```

Trong ví dụ, Spring Cloud Stream dùng kiểu tham số `OrderCreated` làm kiểu đích cho quá trình chuyển đổi đầu vào. Nếu function nhận `Message<OrderCreated>`, converter vẫn có thể chuyển payload trong khi giữ các header message phù hợp.

Không nên nhầm content type với schema version. `application/json` chỉ cho biết định dạng JSON; nó không nói JSON đang tuân theo phiên bản hợp đồng nào. Phiên bản schema cần được quản lý trong envelope, metadata đã thống nhất hoặc schema registry.

## 3. Cách framework lựa chọn MessageConverter

Spring Messaging cung cấp cơ chế chọn converter dựa trên khả năng hỗ trợ kiểu nội dung và kiểu dữ liệu. Trong Spring Cloud Stream, các converter mặc định và converter tùy chỉnh được đưa vào chuỗi chuyển đổi để framework tìm converter phù hợp.

Có thể hình dung quy trình lựa chọn như sau:

1. Xác định content type từ message header hoặc cấu hình binding.
2. Xác định kiểu Java cần nhận hoặc kiểu payload cần gửi.
3. Tìm converter hỗ trợ content type đó và có thể chuyển đổi kiểu dữ liệu tương ứng.
4. Thực hiện chuyển đổi inbound hoặc outbound.
5. Nếu không có converter phù hợp hoặc dữ liệu không thể chuyển đổi, quá trình xử lý phát sinh lỗi chuyển đổi.

Việc converter có hỗ trợ MIME type chưa đủ để bảo đảm chuyển đổi được mọi kiểu Java. Converter cũng có thể giới hạn các lớp mà nó xử lý. Ví dụ, converter CSV có thể hỗ trợ `text/csv` nhưng chỉ chuyển đổi `OrderCreated`; nó không nên nhận mọi object rồi cố phân tích theo một cấu trúc CSV không xác định.

Các converter mặc định phổ biến thường hỗ trợ JSON, String và byte array. Bộ converter cụ thể phụ thuộc phiên bản Spring Framework/Spring Cloud Stream, classpath và cấu hình ứng dụng. Vì vậy, hãy xác định rõ kiểu payload và content type thay vì dựa vào chuyển đổi ngầm.

### JSON

Với `application/json`, converter JSON thường dùng Jackson để chuyển object Java thành JSON và ngược lại. Ví dụ payload:

```json
{
  "orderId": "order-1007",
  "customerId": "customer-42",
  "total": 125000
}
```

Có thể ánh xạ vào record:

```java
public record OrderCreated(
    String orderId,
    String customerId,
    BigDecimal total
) {}
```

Kiểu dữ liệu, tên field, constructor và cấu hình Jackson phải tương thích với JSON thực tế. Nếu JSON thiếu trường bắt buộc hoặc chứa giá trị không thể parse, conversion có thể thất bại.

### String và byte array

Với `text/plain`, converter String thường xử lý văn bản. Với `application/octet-stream`, payload thường được giữ dưới dạng `byte[]`. Nếu ứng dụng cần tự giải mã dữ liệu nhị phân, có thể khai báo function nhận `byte[]` hoặc `Message<byte[]>` và gọi thư viện chuyên biệt trong adapter.

Ví dụ nhận dữ liệu thô:

```java
@Bean
Consumer<byte[]> receiveRawPayload(RawPayloadService service) {
    return service::process;
}
```

Cách này hữu ích khi ứng dụng cần kiểm soát hoàn toàn định dạng, hoặc khi dùng thư viện giải mã riêng. Tuy nhiên, tự xử lý byte array đồng nghĩa ứng dụng phải quản lý việc kiểm tra định dạng, charset, lỗi parse và giới hạn kích thước payload.

## 4. Chọn kiểu tham số function phù hợp

Kiểu tham số của function ảnh hưởng trực tiếp đến kiểu đích của conversion:

| Kiểu function | Kết quả mong đợi |
|---|---|
| `Consumer<OrderCreated>` | Payload được chuyển thành `OrderCreated` |
| `Function<OrderCreated, OrderAccepted>` | Payload đầu vào thành `OrderCreated`; kết quả đầu ra được chuyển theo content type của binding đầu ra |
| `Consumer<Message<OrderCreated>>` | Nhận message envelope và payload đã chuyển thành `OrderCreated` |
| `Consumer<byte[]>` | Nhận payload nhị phân để ứng dụng tự xử lý |
| `Function<String, String>` | Chuyển payload sang String trước khi gọi function |

Dùng kiểu Java cụ thể khi muốn framework thực hiện conversion. Dùng `Message<T>` khi cần đọc header. Dùng `byte[]` khi muốn xử lý dữ liệu thô hoặc dùng một bộ giải mã riêng.

Ví dụ function đọc message và trả về message mới:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder(
        OrderService service) {

    return input -> {
        OrderAccepted result = service.accept(input.getPayload());

        return MessageBuilder
            .withPayload(result)
            .setHeader("correlationId",
                input.getHeaders().get("correlationId"))
            .build();
    };
}
```

Content type của binding đầu ra cần phù hợp với converter có thể chuyển `OrderAccepted` thành định dạng đích. Header được giữ hoặc chuyển tiếp cần tuân theo quy tắc của binder; không giả định mọi header nội bộ đều được truyền nguyên vẹn qua broker.

## 5. Khi nào cần converter tùy chỉnh?

Converter mặc định thường đủ cho JSON, String và byte array. Converter riêng phù hợp khi ứng dụng dùng định dạng hoặc quy tắc ánh xạ đặc thù, ví dụ:

- Payload là CSV theo một hợp đồng cố định.
- Hệ thống cũ dùng định dạng văn bản riêng.
- Một kiểu nhị phân cần được giải mã bằng thư viện chuyên biệt.
- Quy tắc ánh xạ giữa payload và object Java khác với quy tắc JSON mặc định.
- Ứng dụng cần hỗ trợ một MIME type riêng đã được thống nhất với producer/consumer.

Trước khi viết converter, cần xem xét liệu serializer/deserializer của binder, thư viện định dạng hoặc schema registry có phù hợp hơn không. Nếu định dạng là Avro hoặc Protobuf và binder đã có tích hợp native serializer/deserializer, sử dụng cơ chế đó có thể rõ ràng hơn việc tự viết một MessageConverter tổng quát.

Converter tùy chỉnh nên có phạm vi hẹp: hỗ trợ MIME type cụ thể, các kiểu Java cụ thể và định nghĩa rõ hành vi ở cả chiều vào lẫn chiều ra. Không nên đăng ký một converter quá rộng có thể cạnh tranh với converter JSON mặc định.

## 6. Triển khai converter riêng cho định dạng CSV

Giả sử hệ thống cũ phát sự kiện đơn hàng dưới dạng CSV với ba trường:

```text
order-1007,customer-42,125000
```

Ứng dụng muốn chuyển dữ liệu thành record:

```java
public record OrderCreated(
    String orderId,
    String customerId,
    BigDecimal total
) {}
```

Có thể tạo converter bằng cách kế thừa `AbstractMessageConverter`. Lớp này hỗ trợ khai báo MIME type và các hook chuyển đổi vào/ra:

```java
public class OrderCsvMessageConverter extends AbstractMessageConverter {

    public OrderCsvMessageConverter() {
        super(MimeTypeUtils.parseMimeType("text/csv"));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return OrderCreated.class.isAssignableFrom(clazz);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message,
            Class<?> targetClass,
            Object conversionHint) {

        String csv = payloadAsString(message.getPayload());
        String[] fields = csv.split(",", -1);

        if (fields.length != 3) {
            throw new MessageConversionException(
                message, "Expected 3 CSV fields"
            );
        }

        try {
            return new OrderCreated(
                fields[0].trim(),
                fields[1].trim(),
                new BigDecimal(fields[2].trim())
            );
        } catch (RuntimeException ex) {
            throw new MessageConversionException(
                message, "Invalid OrderCreated CSV payload", ex
            );
        }
    }

    @Override
    protected Object convertToInternal(
            Object payload,
            MessageHeaders headers,
            Object conversionHint) {

        if (!(payload instanceof OrderCreated event)) {
            return null;
        }

        return String.join(
            ",",
            event.orderId(),
            event.customerId(),
            event.total().toPlainString()
        );
    }

    private String payloadAsString(Object payload) {
        if (payload instanceof byte[] bytes) {
            return new String(bytes, StandardCharsets.UTF_8);
        }
        if (payload instanceof String text) {
            return text;
        }
        throw new IllegalArgumentException(
            "CSV payload must be String or byte[]"
        );
    }
}
```

Converter trên hỗ trợ MIME type `text/csv` và kiểu Java `OrderCreated`. Khi nhận dữ liệu, nó chấp nhận payload String hoặc byte array UTF-8, kiểm tra số trường và parse tổng tiền. Khi gửi, nó chuyển `OrderCreated` thành chuỗi CSV.

Đây là ví dụ CSV đơn giản, giả định giá trị không chứa dấu phẩy, dấu xuống dòng hoặc dấu ngoặc kép cần escape. Với CSV production có các quy tắc quoting/escaping, nên dùng thư viện CSV chuyên dụng thay vì `String.split()`. Cũng cần giới hạn kích thước payload và kiểm tra giá trị từng trường trước khi xử lý nghiệp vụ.

Một converter thực tế nên phát sinh `MessageConversionException` khi payload có định dạng đúng MIME type nhưng dữ liệu sai cấu trúc. Khi converter không hỗ trợ kiểu payload hoặc MIME type, nó nên để converter khác xử lý bằng cách không nhận chuyển đổi đó.

## 7. Đăng ký converter với Spring Cloud Stream

Spring Cloud Stream cho phép đăng ký converter riêng bằng bean có annotation `@StreamMessageConverter`. Annotation này giúp framework nhận diện bean như một converter dành cho message conversion của Spring Cloud Stream.

```java
@Configuration
public class MessageConversionConfiguration {

    @Bean
    @StreamMessageConverter
    public MessageConverter orderCsvMessageConverter() {
        return new OrderCsvMessageConverter();
    }
}
```

Converter được thêm vào cơ chế chuyển đổi của Spring Cloud Stream. Không cần tự tạo `MessageChannel` hoặc gọi converter trực tiếp trong từng function nếu framework có thể xác định content type và kiểu đích.

Sau khi đăng ký converter, cấu hình binding dùng đúng MIME type:

```yaml
spring:
  cloud:
    function:
      definition: receiveOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: legacy.orders
          group: order-service
          content-type: text/csv
```

Function có thể nhận payload đã được chuyển đổi:

```java
@Bean
Consumer<OrderCreated> receiveOrder(OrderService service) {
    return service::handle;
}
```

Nếu producer gửi payload CSV, binder nhận message và converter được chọn theo `text/csv` cùng kiểu đích `OrderCreated`. Ở chiều đầu ra, cấu hình binding đầu ra cũng cần content type tương ứng nếu muốn converter CSV chuyển object thành CSV.

Tên annotation, package và cơ chế đăng ký cần được đối chiếu với phiên bản Spring Cloud Stream trong dự án. Khi nâng cấp framework, hãy xác minh converter vẫn được phát hiện và thứ tự lựa chọn không thay đổi ngoài dự kiến.

## 8. Chọn converter và xử lý xung đột

Một ứng dụng có thể có nhiều converter cùng tồn tại: JSON, String, byte array và converter tùy chỉnh. Xung đột có thể xảy ra nếu nhiều converter cùng tuyên bố hỗ trợ một MIME type và một kiểu Java.

Để tránh xung đột:

- Chọn MIME type riêng, rõ ràng cho định dạng tùy chỉnh, ví dụ `text/csv`.
- Giới hạn `supports(Class<?> clazz)` ở các kiểu thực sự được converter xử lý.
- Không khai báo converter tùy chỉnh là hỗ trợ `application/json` nếu chỉ muốn thay đổi cách parse một loại DTO mà chưa xem xét converter JSON mặc định.
- Kiểm tra cả inbound và outbound; converter có thể hỗ trợ một chiều nhưng chưa chắc đã chuyển đổi đúng chiều còn lại.
- Không dựa vào thứ tự bean không được tài liệu bảo đảm để giải quyết xung đột.

Nếu cần thay đổi cách xử lý JSON, trước hết hãy xem xét cấu hình Jackson, module, naming strategy hoặc serializer/deserializer thích hợp. Viết converter JSON riêng chỉ nên thực hiện khi quy tắc chuyển đổi thực sự khác với cơ chế mặc định và có kiểm thử rõ ràng.

## 9. Phân biệt MessageConverter với native encoding/decoding

Spring Cloud Stream message conversion và native serialization của binder là hai đường xử lý khác nhau.

Với cơ chế message conversion của Spring Cloud Stream:

- Function khai báo kiểu Java.
- Framework sử dụng content type và MessageConverter để chuyển payload.
- Binder gửi hoặc nhận biểu diễn message theo giao diện của nó.

Với native encoding/decoding, binder sử dụng serializer/deserializer riêng của broker hoặc client. Các thuộc tính như `useNativeEncoding` và `useNativeDecoding` có thể bật hành vi này ở những binder hỗ trợ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            use-native-encoding: true
        receiveOrder-in-0:
          consumer:
            use-native-decoding: true
```

Khi dùng native encoding/decoding, không nên giả định custom `MessageConverter` sẽ được gọi trên đường dữ liệu tương ứng. Cần cấu hình serializer/deserializer và schema strategy theo binder. Ví dụ với Kafka, có thể cấu hình Kafka serializer/deserializer và tích hợp schema registry theo thư viện đang sử dụng.

Chọn một cơ chế chuyển đổi rõ ràng cho mỗi binding. Nếu vừa cấu hình converter riêng vừa bật native serialization, hãy kiểm tra thứ tự và trách nhiệm thực tế để tránh chuyển đổi hai lần hoặc bỏ qua converter ngoài dự kiến.

## 10. Kiểm thử converter

Converter cần được kiểm thử độc lập trước khi kiểm thử qua binder. Những trường hợp quan trọng gồm:

1. Chuyển đổi CSV hợp lệ thành đúng object Java.
2. Chuyển đổi object Java thành chuỗi CSV có định dạng ổn định.
3. Từ chối payload thiếu trường, thừa trường hoặc sai kiểu dữ liệu.
4. Từ chối kiểu payload không được hỗ trợ.
5. Xử lý charset và content type không đúng.
6. Bảo đảm converter không chiếm xử lý MIME type của converter khác.
7. Xác minh content type và header cần thiết qua binding thực tế.

Ví dụ unit test cho converter:

```java
class OrderCsvMessageConverterTest {

    private final OrderCsvMessageConverter converter =
        new OrderCsvMessageConverter();

    @Test
    void convertsCsvToOrder() {
        Message<byte[]> message = MessageBuilder
            .withPayload(
                "order-1007,customer-42,125000".getBytes(StandardCharsets.UTF_8)
            )
            .setHeader(MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.parseMimeType("text/csv"))
            .build();

        OrderCreated event =
            (OrderCreated) converter.fromMessage(message, OrderCreated.class);

        assertThat(event.orderId()).isEqualTo("order-1007");
        assertThat(event.customerId()).isEqualTo("customer-42");
        assertThat(event.total()).isEqualByComparingTo("125000");
    }
}
```

Ví dụ này kiểm tra trực tiếp chiều inbound. Cần có thêm test cho chiều outbound và trường hợp dữ liệu sai. API của converter và cách khởi tạo `MessageHeaders` có thể khác nhẹ theo phiên bản Spring Framework; hãy đồng bộ import và dependency với phiên bản dự án.

Sau unit test, có thể dùng Spring Cloud Stream Test Binder để xác minh converter được phát hiện và áp dụng trong binding. Test Binder không chứng minh broker thật giữ nguyên header hoặc serialization theo đúng cấu hình native. Nếu ứng dụng phụ thuộc vào serializer, partition key, schema registry hay header mapping của Kafka/RabbitMQ/Pulsar, cần integration test với broker tương ứng.

## 11. Chẩn đoán lỗi chuyển đổi

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy converter phù hợp | Content type hoặc kiểu Java không được converter hỗ trợ | Kiểm tra `content-type`, kiểu function và MIME type của converter |
| JSON không ánh xạ được vào DTO | Tên field, kiểu dữ liệu hoặc constructor không tương thích | Kiểm tra payload, DTO và cấu hình Jackson |
| Converter tùy chỉnh không được gọi | Bean chưa được đăng ký đúng hoặc binding dùng content type khác | Kiểm tra `@StreamMessageConverter`, bean và cấu hình binding |
| Payload nhận được vẫn là byte[] | Function yêu cầu dữ liệu thô hoặc native decoding được bật | Kiểm tra kiểu function và cấu hình binder |
| Chuyển đổi outbound sai định dạng | Binding đầu ra dùng content type không đúng hoặc converter không hỗ trợ payload | Kiểm tra content type đầu ra và `supports()` |
| Chuyển đổi thành công trong Test Binder nhưng sai với broker | Native serialization, header mapping hoặc client serializer khác biệt | Chạy integration test với broker thật |

Khi xử lý lỗi, nên ghi log content type, tên binding, loại payload và loại đích. Tránh ghi toàn bộ payload nếu dữ liệu có thể chứa thông tin nhạy cảm. Log nên giúp xác định converter nào được chọn mà không làm lộ nội dung nghiệp vụ.

## 12. Checklist trước khi đưa converter vào production

- Xác định content type và kiểu Java ở cả chiều inbound/outbound.
- Dùng converter mặc định nếu nó đã đáp ứng yêu cầu.
- Converter tùy chỉnh giới hạn rõ MIME type và kiểu Java được hỗ trợ.
- Đăng ký converter qua bean `@StreamMessageConverter` đúng phiên bản.
- Kiểm tra content type ở binding và header message.
- Xử lý payload sai định dạng bằng exception rõ ràng, không trả object giả.
- Giới hạn kích thước dữ liệu và kiểm tra charset, cấu trúc, giá trị.
- Không nhầm MessageConverter với serializer/deserializer native của binder.
- Kiểm thử unit, Test Binder và broker thật theo các hành vi ứng dụng phụ thuộc.

MessageConverter giúp Spring Cloud Stream chuyển đổi dữ liệu giữa broker và kiểu Java của function. Framework lựa chọn converter theo content type và khả năng hỗ trợ kiểu dữ liệu; ứng dụng chỉ cần đăng ký converter riêng khi có định dạng hoặc quy tắc chuyển đổi đặc thù. Khi content type, kiểu function, converter và cấu hình native serialization được thống nhất, dữ liệu sẽ được chuyển đổi có thể dự đoán và dễ kiểm thử hơn.

