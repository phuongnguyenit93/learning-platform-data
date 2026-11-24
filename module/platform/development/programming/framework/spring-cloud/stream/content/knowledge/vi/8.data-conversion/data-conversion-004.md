# Xử lý String, byte[] và dữ liệu nhị phân

Thông điệp trong Spring Cloud Stream có thể mang nội dung văn bản, dữ liệu nhị phân hoặc một đối tượng Java đã được chuyển đổi từ payload. Việc chọn đúng kiểu dữ liệu ở ranh giới messaging giúp ứng dụng tránh lỗi mã hóa ký tự, hỏng dữ liệu, chuyển đổi không cần thiết và khác biệt giữa các binder Kafka, RabbitMQ hoặc Pulsar.

Ba dạng thường gặp là **String**, **byte[]** và đối tượng nhị phân theo định dạng riêng. String phù hợp với nội dung văn bản có charset xác định. byte[] phù hợp khi cần giữ nguyên các octet nhận từ broker hoặc gửi dữ liệu nhị phân. Các định dạng như ảnh, PDF, tệp nén, Protobuf hay Avro cần thêm quy ước về media type, schema hoặc metadata để bên nhận giải mã đúng.

## 1. Payload, Message và kiểu dữ liệu

Spring Messaging biểu diễn một thông điệp bằng payload và headers. Payload chứa nội dung chính; headers mang metadata như content type, thời điểm, mã tương quan hoặc thông tin định tuyến.

~~~java
Message<String> message = MessageBuilder
        .withPayload("Đơn hàng đã được xác nhận")
        .setHeader(MessageHeaders.CONTENT_TYPE, "text/plain;charset=UTF-8")
        .build();
~~~

Với Spring Cloud Stream, một function có thể nhận trực tiếp payload:

~~~java
@Bean
public Consumer<String> textConsumer() {
    return text -> processText(text);
}
~~~

Hoặc nhận toàn bộ Message để đọc headers:

~~~java
@Bean
public Consumer<Message<byte[]>> binaryConsumer() {
    return message -> {
        byte[] payload = message.getPayload();
        Object contentType = message.getHeaders().get(MessageHeaders.CONTENT_TYPE);
        processBinary(payload, contentType);
    };
}
~~~

Chọn kiểu tham số theo trách nhiệm của hàm:

- Dùng **String** khi hàm cần nội dung văn bản đã được giải mã.
- Dùng **byte[]** khi hàm cần các byte gốc và không muốn chuyển đổi sang chuỗi.
- Dùng **Message<T>** khi cần cả payload lẫn metadata trong headers.

Không nên chuyển mọi payload thành String chỉ để log hoặc truyền qua các hàm. Việc giải mã byte nhị phân như thể đó là văn bản có thể làm mất dữ liệu hoặc tạo ký tự thay thế.

## 2. Xử lý String và charset

String trong Java là chuỗi ký tự Unicode. Khi truyền qua broker, nội dung phải được biểu diễn thành byte theo một bộ mã ký tự. UTF-8 là lựa chọn phổ biến cho hệ thống phân tán vì được hỗ trợ rộng rãi và có thể biểu diễn đầy đủ Unicode.

Khi tự chuyển đổi giữa String và byte[], luôn chỉ định charset:

~~~java
String text = "Xin chào Spring Cloud Stream";

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
~~~

Tránh dùng các overload không truyền charset như **getBytes()** hoặc **new String(bytes)** ở ranh giới messaging. Chúng sử dụng charset mặc định của môi trường chạy. Hai instance chạy trên hệ điều hành hoặc cấu hình JVM khác nhau có thể tạo ra kết quả không giống nhau.

### Cấu hình binding cho văn bản

Đặt content type là text/plain và khai báo charset nếu cần:

~~~yaml
spring:
  cloud:
    function:
      definition: textConsumer
      stream:
        bindings:
          textConsumer-in-0:
            destination: text-events
            group: text-reader
            content-type: text/plain;charset=UTF-8
~~~

Trong cấu hình trên, ứng dụng nhận payload văn bản qua binding đầu vào. Khi producer cũng là ứng dụng Spring Cloud Stream, nên đặt content type tương ứng ở output binding hoặc trên Message được gửi để bên nhận có đủ thông tin chuyển đổi.

Ví dụ output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        textPublisher-out-0:
          destination: text-events
          content-type: text/plain;charset=UTF-8
~~~

Với văn bản đến từ hệ thống ngoài, không phải lúc nào producer cũng gửi metadata content type. Khi thiếu thông tin, hai bên cần thống nhất charset và định dạng bằng hợp đồng tích hợp. Đừng dựa vào charset mặc định của máy chủ.

### Xử lý văn bản lỗi mã hóa

Nếu byte nhận được không hợp lệ với charset đã khai báo, việc tạo String có thể thay thế chuỗi byte lỗi bằng ký tự thay thế. Khi dữ liệu cần được kiểm tra nghiêm ngặt, dùng CharsetDecoder và đặt hành vi báo lỗi:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String text = decoder.decode(ByteBuffer.wrap(payload)).toString();
~~~

Lỗi giải mã nên được ghi nhận như lỗi dữ liệu đầu vào. Không tự ý bỏ byte hoặc đổi charset để cố tiếp tục nếu điều đó làm thay đổi ý nghĩa nghiệp vụ.

## 3. Xử lý byte[] như dữ liệu nguyên bản

byte[] là mảng các byte trong Java, phù hợp với payload không phải văn bản. Một consumer nhận byte[] có thể lưu tệp, tính checksum, giải mã định dạng riêng hoặc chuyển tiếp nguyên nội dung sang dịch vụ khác.

~~~java
@Bean
public Consumer<byte[]> imageConsumer() {
    return bytes -> {
        validateImage(bytes);
        imageStorage.store(bytes);
    };
}
~~~

Khai báo content type phù hợp, chẳng hạn application/octet-stream cho dữ liệu nhị phân tổng quát:

~~~yaml
spring:
  cloud:
    function:
      definition: imageConsumer
    stream:
      bindings:
        imageConsumer-in-0:
          destination: image-events
          group: image-storage
          content-type: application/octet-stream
~~~

Nếu định dạng đã biết, nên dùng media type cụ thể hơn, ví dụ **image/png**, **application/pdf** hoặc media type do tổ chức định nghĩa cho payload riêng. Media type mô tả cách diễn giải dữ liệu; nó không tự kiểm tra rằng byte thực sự đúng định dạng đó.

### Gửi byte[] qua output binding

Một hàm có thể tạo hoặc chuyển tiếp byte[]:

~~~java
@Bean
public Function<byte[], byte[]> binaryTransform() {
    return input -> transformBinary(input);
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: binaryTransform
    stream:
      bindings:
        binaryTransform-in-0:
          destination: raw-input
          content-type: application/octet-stream
        binaryTransform-out-0:
          destination: raw-output
          content-type: application/octet-stream
~~~

Nếu cần giữ headers, dùng Function nhận và trả Message:

~~~java
@Bean
public Function<Message<byte[]>, Message<byte[]>> forwardBinary() {
    return message -> MessageBuilder.withPayload(message.getPayload())
            .copyHeaders(message.getHeaders())
            .build();
}
~~~

Khi sao chép headers, hãy xem xét header nào thực sự có ý nghĩa ở đích. Không chuyển tiếp một cách mù quáng header nội bộ của binder, thông tin định tuyến hoặc metadata không còn đúng sau khi thông điệp đi qua một ranh giới hệ thống khác.

## 4. Content type và cơ chế chuyển đổi của Spring Cloud Stream

Spring Cloud Stream dùng content type để lựa chọn cách chuyển đổi payload giữa biểu diễn trên wire và kiểu Java mà function mong đợi. Content type có thể được đặt ở binding hoặc đi cùng Message dưới dạng header. Khi có metadata ở nhiều nguồn, cần hiểu thứ tự ưu tiên và hành vi của phiên bản Spring Cloud Stream đang dùng; không nên giả định một giá trị ở binding luôn thắng header của thông điệp.

Một số media type phổ biến:

| Content type | Ý nghĩa | Kiểu Java thường dùng |
|---|---|---|
| **text/plain;charset=UTF-8** | Văn bản UTF-8. | String |
| **application/json** | Dữ liệu JSON. | DTO, Map hoặc JsonNode tùy converter |
| **application/octet-stream** | Dữ liệu nhị phân không chỉ rõ định dạng. | byte[] |
| **image/png** | Ảnh PNG. | byte[] hoặc kiểu ảnh do ứng dụng xử lý |
| **application/pdf** | Tài liệu PDF. | byte[] |
| **application/x-protobuf** | Payload Protocol Buffers theo hợp đồng đã thống nhất. | Message class được sinh từ schema hoặc byte[] |

Content type là metadata, không phải phép biến đổi dữ liệu. Đặt **application/pdf** không làm một mảng byte bất kỳ trở thành PDF. Ứng dụng vẫn cần kiểm tra chữ ký định dạng, kích thước, schema hoặc checksum khi dữ liệu có yêu cầu an toàn và toàn vẹn.

### Ví dụ chuyển đổi JSON và byte[]

Giả sử một producer gửi JSON dưới dạng byte[]:

~~~java
byte[] json = """
        {"orderId":"ORD-1001","status":"CREATED"}
        """.getBytes(StandardCharsets.UTF_8);
~~~

Nếu consumer mong đợi DTO, content type phải chỉ ra JSON và converter phải hỗ trợ chuyển đổi sang kiểu đó. Nếu consumer nhận byte[], ứng dụng có thể tự kiểm soát việc parse:

~~~java
ObjectMapper mapper = new ObjectMapper();
OrderCreated event = mapper.readValue(json, OrderCreated.class);
~~~

Hai cách có trade-off khác nhau. Để Spring Cloud Stream chuyển đổi giúp function làm việc trực tiếp với DTO, giảm mã parse trong business logic. Nhận byte[] phù hợp khi cần xác thực chữ ký trên dữ liệu gốc, lưu trữ nguyên bản hoặc dùng parser riêng. Tránh parse cùng một payload nhiều lần ở các tầng khác nhau.

## 5. Native encoding và native decoding

Spring Cloud Stream có thể chuyển đổi payload bằng message converter trước khi binder gửi hoặc sau khi binder nhận. Một số binder cũng hỗ trợ cơ chế native encoding/decoding, trong đó serializer và deserializer của broker chịu trách nhiệm chuyển đổi dữ liệu.

Với Kafka binder, hai tùy chọn thường dùng ở cấp binding là:

- **producer.useNativeEncoding:** giao việc serialize cho Kafka producer serializer.
- **consumer.useNativeDecoding:** giao việc deserialize cho Kafka consumer deserializer.

Ví dụ minh họa cấu hình trên một output và input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        binaryPublisher-out-0:
          destination: binary-events
          producer:
            use-native-encoding: true
        binaryReader-in-0:
          destination: binary-events
          group: binary-reader
          consumer:
            use-native-decoding: true
~~~

Khi dùng native encoding/decoding, serializer/deserializer của binder phải được cấu hình tương ứng với kiểu dữ liệu. Nếu consumer mong đợi byte[] nhưng deserializer trả về một đối tượng khác, function sẽ không nhận được kiểu payload dự kiến. Ngược lại, nếu producer serializer nhận DTO nhưng ứng dụng đưa byte[] vào, cần bảo đảm serializer có thể xử lý đúng kiểu đó.

Không bật native encoding hoặc decoding chỉ để tăng tốc mà chưa xác định hợp đồng wire format. Khi native conversion được dùng, các converter thông thường của Spring Cloud Stream có thể không tham gia vào đường dữ liệu tương ứng. Cấu hình chi tiết serializer/deserializer phụ thuộc binder và phiên bản; hãy tham chiếu đúng tài liệu Kafka, RabbitMQ hoặc Pulsar binder.

## 6. Định dạng nhị phân có cấu trúc

Một payload nhị phân thường cần nhiều thông tin hơn một mảng byte. Các hệ thống cần thống nhất:

1. **Định dạng:** Protobuf, Avro, PDF, PNG, ZIP hoặc định dạng riêng.
2. **Schema hoặc phiên bản:** cách diễn giải các trường và khả năng tương thích.
3. **Encoding:** byte order, charset nếu có phần văn bản, quy tắc framing và độ dài.
4. **Metadata:** mã schema, phiên bản, content type, correlation ID hoặc checksum.
5. **Giới hạn:** kích thước tối đa, thời gian xử lý và chính sách lưu trữ.

Ví dụ, với một payload Protobuf, producer và consumer cần cùng hiểu schema hoặc schema ID. Consumer không thể suy ra đầy đủ cấu trúc chỉ từ byte[] nếu thiếu thông tin định dạng. Với Avro, cần thống nhất schema và cách lấy schema, chẳng hạn thông qua schema registry nếu kiến trúc sử dụng registry.

Một envelope nhị phân có thể được thiết kế để chứa version và payload:

~~~java
public record BinaryEnvelope(
        String eventType,
        int schemaVersion,
        byte[] data,
        String checksum) {
}
~~~

Đây chỉ là mô hình trong bộ nhớ. Khi serialize envelope, cần định nghĩa định dạng wire rõ ràng, không gửi biểu diễn Java mặc định rồi giả định ứng dụng khác có thể đọc. Nếu schema được thay đổi, cần quy định trường bắt buộc, trường tùy chọn, giá trị mặc định và cách xử lý phiên bản không được hỗ trợ.

### Không nhầm nén với mã hóa bảo mật

Nén dữ liệu làm giảm dung lượng truyền hoặc lưu trữ; mã hóa bảo mật bảo vệ tính bí mật. Hai mục đích này khác nhau. Một file ZIP hoặc payload nén vẫn có thể đọc được nếu không có lớp mã hóa riêng.

Nếu dùng nén ở cấp ứng dụng, hai bên cần thống nhất thuật toán và cách nhận biết payload đã nén. Metadata như content-encoding có thể biểu diễn quy ước đó nếu hệ thống và binder bảo toàn header tương ứng. Không giải nén payload không đáng tin cậy mà không giới hạn kích thước đầu ra, vì dữ liệu nén có thể mở rộng rất lớn.

## 7. Bảo toàn dữ liệu và kiểm tra payload

Với byte[], cần coi dữ liệu là chuỗi octet có thể chứa mọi giá trị từ 0 đến 255. Không dùng thao tác cắt khoảng trắng, đổi chữ hoa/thường hoặc chuẩn hóa Unicode lên byte nhị phân. Những thao tác đó chỉ có ý nghĩa với văn bản đã giải mã đúng charset.

Các bước kiểm tra hữu ích:

- Kiểm tra payload không null và có độ dài trong giới hạn.
- Xác minh content type hoặc định dạng theo hợp đồng.
- Kiểm tra magic bytes hoặc chữ ký file khi phù hợp.
- Kiểm tra checksum hoặc chữ ký số nếu cần xác thực tính toàn vẹn.
- Giới hạn thời gian parse, giải nén và xử lý.
- Không tin tên file hoặc content type do client gửi nếu chưa kiểm chứng.
- Không ghi toàn bộ payload nhị phân vào log; dùng kích thước, checksum hoặc mã định danh để chẩn đoán.

Ví dụ kiểm tra kích thước:

~~~java
private static final int MAX_PAYLOAD_BYTES = 5 * 1024 * 1024;

static void validateBinary(byte[] payload) {
    if (payload == null || payload.length == 0) {
        throw new IllegalArgumentException("Payload rỗng");
    }
    if (payload.length > MAX_PAYLOAD_BYTES) {
        throw new IllegalArgumentException("Payload vượt giới hạn");
    }
}
~~~

Giới hạn cần được chọn theo năng lực broker, cấu hình producer/consumer, bộ nhớ JVM và thời gian xử lý. Một payload nhỏ hơn giới hạn broker vẫn có thể gây áp lực bộ nhớ nếu nhiều consumer xử lý đồng thời hoặc ứng dụng giữ nhiều bản sao trong heap.

## 8. Gửi và nhận dữ liệu nhị phân qua StreamBridge

StreamBridge cho phép thành phần nghiệp vụ gửi payload qua output binding. Với dữ liệu nhị phân, có thể gửi byte[] và đặt content type rõ ràng:

~~~java
public boolean publishDocument(StreamBridge bridge, byte[] document) {
    Message<byte[]> message = MessageBuilder
            .withPayload(document)
            .setHeader(MessageHeaders.CONTENT_TYPE, "application/pdf")
            .build();
    return bridge.send("documentsOut", message);
}
~~~

Output binding:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: documentsOut
      bindings:
        documentsOut:
          destination: documents
          content-type: application/pdf
~~~

Ở phía nhận, consumer có thể làm việc trực tiếp với byte[]:

~~~java
@Bean
public Consumer<byte[]> documentConsumer(DocumentStore store) {
    return bytes -> {
        validatePdf(bytes);
        store.save(bytes);
    };
}
~~~

Nếu consumer cần content type để chọn parser, nhận **Message<byte[]>** thay vì chỉ byte[] để đọc metadata. Dù vậy, headers có thể bị thay đổi hoặc không được truyền qua mọi broker theo cùng cách. Với metadata quan trọng cho hợp đồng dữ liệu, hãy cân nhắc đặt nó trong envelope hoặc một trường định dạng có thể kiểm soát thay vì chỉ dựa vào header tùy chọn.

## 9. Kiểm thử String, byte[] và dữ liệu nhị phân

Kiểm thử chuyển đổi nên xác minh cả nội dung lẫn metadata. Chỉ kiểm tra rằng consumer được gọi là chưa đủ; cần chứng minh payload sau khi đi qua converter vẫn giữ đúng giá trị.

| Trường hợp | Dữ liệu thử | Điều cần xác nhận |
|---|---|---|
| String UTF-8 | Tiếng Việt có dấu, ký tự ngoài ASCII và emoji. | Chuỗi nhận được giống chuỗi gửi, không lỗi charset. |
| byte[] tùy ý | Mảng có byte 0, byte âm theo cách Java biểu diễn và các giá trị ở cuối dải. | Các byte được bảo toàn từng vị trí. |
| application/octet-stream | Payload nhị phân không phải văn bản. | Consumer nhận byte[] nguyên bản. |
| JSON sang DTO | JSON đúng schema và JSON thiếu trường tùy chọn. | Converter hoặc parser tạo đối tượng theo hợp đồng. |
| JSON sai định dạng | Payload bị cắt hoặc sai cú pháp. | Lỗi chuyển đổi được xử lý theo chính sách retry/DLQ. |
| Content type không khớp | Byte PDF nhưng khai báo text/plain. | Kiểm thử phát hiện hợp đồng sai và không âm thầm xử lý như văn bản. |
| Native decoding | Serializer/deserializer thử nghiệm của binder. | Kiểu Java và định dạng wire tương thích ở hai đầu. |
| Payload quá lớn | Dữ liệu vượt giới hạn ứng dụng. | Bị từ chối trước khi gây áp lực bộ nhớ hoặc làm gián đoạn consumer. |

Ví dụ kiểm tra bảo toàn byte:

~~~java
byte[] original = new byte[] {0, 1, 10, 13, 127, (byte) 0x80, (byte) 0xFF};
byte[] restored = Arrays.copyOf(original, original.length);

assertArrayEquals(original, restored);
~~~

Trong integration test, gửi dữ liệu qua test binder hoặc broker thử nghiệm và so sánh byte[] nhận được với dữ liệu gốc. Nếu dùng Kafka, RabbitMQ hoặc Pulsar với native serialization, cần kiểm thử riêng serializer/deserializer thực tế và cấu hình broker tương ứng.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tiếng Việt bị lỗi ký tự | Producer và consumer dùng charset khác nhau hoặc dựa vào charset mặc định. | Chuẩn hóa UTF-8 và khai báo charset rõ ràng. |
| PDF hoặc ảnh bị hỏng | Payload nhị phân bị chuyển thành String hoặc bị biến đổi như văn bản. | Dùng byte[] và media type phù hợp. |
| Consumer báo sai kiểu payload | Content type, function signature hoặc native deserializer không khớp. | Kiểm tra kiểu Java, converter và serializer/deserializer ở hai phía. |
| DTO không được chuyển đổi | Content type không phải JSON, thiếu converter hoặc schema không tương thích. | Xác nhận content type và cấu hình chuyển đổi. |
| Header content type không đúng | Producer không gửi metadata hoặc binder không bảo toàn header như mong đợi. | Đặt content type tại binding và xác minh metadata thực tế; đưa metadata quan trọng vào envelope nếu cần. |
| Payload lớn làm tăng bộ nhớ | Nhiều bản sao byte[] hoặc xử lý đồng thời vượt năng lực heap. | Đặt giới hạn kích thước, điều chỉnh concurrency và cân nhắc lưu file ngoài broker. |
| Native decoding trả về kiểu không mong muốn | Deserializer không khớp kiểu function hoặc wire format. | Cấu hình serializer/deserializer tương ứng và kiểm thử hợp đồng. |
| Log khó chẩn đoán dữ liệu nhị phân | Ghi payload trực tiếp hoặc chỉ log một chuỗi đã decode sai. | Log event ID, content type, kích thước và checksum. |

Khi điều tra, xác định trước dữ liệu trên wire là văn bản hay nhị phân. Sau đó kiểm tra charset hoặc media type, kiểu tham số của function, converter đang hoạt động và chế độ native encoding/decoding. Cuối cùng xác nhận serializer/deserializer của binder và payload thực tế trên broker.

## 11. Checklist trước khi triển khai

- [ ] Mỗi binding có content type phù hợp với payload.
- [ ] Văn bản sử dụng charset được thống nhất, ưu tiên UTF-8.
- [ ] Chuyển đổi String và byte[] luôn chỉ định charset rõ ràng.
- [ ] Payload nhị phân được giữ dưới dạng byte[] hoặc kiểu nhị phân phù hợp.
- [ ] Không decode dữ liệu nhị phân như văn bản.
- [ ] Schema, phiên bản và media type được thống nhất giữa producer và consumer.
- [ ] Native encoding/decoding chỉ bật khi serializer và deserializer đã được cấu hình tương thích.
- [ ] Kích thước, checksum, định dạng và thời gian xử lý được kiểm tra theo yêu cầu.
- [ ] Log không ghi nội dung nhạy cảm hoặc toàn bộ payload.
- [ ] Integration test xác nhận payload và metadata được bảo toàn qua binder thật.

Trong Spring Cloud Stream, String, byte[] và dữ liệu nhị phân là những lựa chọn biểu diễn payload có mục đích khác nhau. String cần charset thống nhất; byte[] giữ nguyên octet; định dạng nhị phân có cấu trúc cần schema và metadata để giải mã. Khi content type, converter và serializer/deserializer được cấu hình nhất quán, ứng dụng có thể trao đổi văn bản, tệp và dữ liệu nhị phân đáng tin cậy qua Kafka, RabbitMQ hoặc Pulsar.
