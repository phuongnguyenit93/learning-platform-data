# Vai trò của các module CBOR và Smile

Jackson thường được dùng để serialize Java object thành JSON text, nhưng trong một số hệ thống, dữ liệu cần được truyền hoặc lưu dưới dạng nhị phân. Binary format có thể giảm kích thước payload, tránh chi phí biểu diễn văn bản và hỗ trợ một số kiểu dữ liệu như byte string trực tiếp. Trong hệ sinh thái Jackson, hai module thường được nhắc đến cho mục tiêu này là CBOR và Smile.

CBOR là một định dạng nhị phân được chuẩn hóa trong RFC 8949. Nó mô tả các giá trị như integer, byte string, text string, array, map, tag, boolean, null và floating-point. Vì có đặc tả độc lập, CBOR phù hợp khi cần trao đổi với hệ thống không viết bằng Java hoặc không dùng Jackson.

Smile là định dạng nhị phân kiểu JSON được thiết kế cho hệ sinh thái Jackson. Nó biểu diễn các cấu trúc object, array và scalar theo dạng token nhị phân gọn hơn JSON text; có cơ chế chia sẻ tên field và một số string lặp lại trong tài liệu để giảm dữ liệu trùng. Smile hữu ích khi cả hai phía đều có thể dùng thư viện hỗ trợ Smile, đặc biệt trong giao tiếp nội bộ hoặc lưu trữ payload Jackson.

Cả hai module đều kết nối với Jackson databind. Ứng dụng có thể tiếp tục dùng DTO, record, Map, collection, annotation, serializer/deserializer và Tree Model quen thuộc. Điểm thay đổi chủ yếu nằm ở factory/parser/generator và bytes được truyền trên wire.

## 1. Định dạng nhị phân nằm ở đâu trong kiến trúc Jackson?

Jackson được chia thành nhiều lớp:

| Thành phần | Vai trò |
|---|---|
| jackson-core | Streaming API, parser, generator và token |
| jackson-annotations | Annotation mô tả mapping của property và type |
| jackson-databind | ObjectMapper, serializer, deserializer, Tree Model và data binding |
| jackson-dataformat-cbor | CBORFactory, parser và generator cho CBOR |
| jackson-dataformat-smile | SmileFactory, parser và generator cho Smile |

Các module dataformat cung cấp cách chuyển cú pháp nhị phân thành token mà Jackson hiểu. Databind tiếp tục chuyển token thành Java object hoặc chuyển Java object thành token.

~~~text
Java object / DTO / JsonNode
             |
             v
       Jackson Databind
             |
             v
       JsonGenerator API
             |
       +-----+------+
       |            |
       v            v
   CBORFactory   SmileFactory
       |            |
       v            v
   CBOR bytes    Smile bytes
       |            |
       +-----+------+
             |
       Network / File
             |
       +-----+------+
       |            |
       v            v
   CBORParser    SmileParser
       |            |
       +-----+------+
             |
             v
       Jackson Databind
             |
             v
       Java object / JsonNode
~~~

Vì cùng dùng Jackson databind, phần lớn code nghiệp vụ không cần biết payload được mã hóa bằng CBOR hay Smile. Lớp vận chuyển và cấu hình mapper quyết định định dạng thực tế.

## 2. Vai trò của CBOR

CBOR là viết tắt của Concise Binary Object Representation. Định dạng này được chuẩn hóa trong RFC 8949 và được thiết kế để biểu diễn cấu trúc dữ liệu tương tự JSON bằng các mã nhị phân gọn.

CBOR có các nhóm dữ liệu chính:

| Nhóm CBOR | Ý nghĩa |
|---|---|
| Unsigned integer | Số nguyên không âm |
| Negative integer | Số nguyên âm |
| Byte string | Dãy byte nhị phân |
| Text string | Chuỗi Unicode |
| Array | Dãy phần tử có thứ tự |
| Map | Tập cặp key/value |
| Tag | Gắn semantics bổ sung cho một giá trị |
| Simple value | Boolean, null và các giá trị đơn giản |
| Floating-point | Số dấu phẩy động |

Ví dụ dữ liệu JSON:

~~~json
{
  "device": "sensor-17",
  "temperature": 24.75,
  "active": true
}
~~~

Một biểu diễn CBOR tương ứng chứa cùng các giá trị nhưng được mã hóa thành byte theo quy tắc CBOR. Không thể đọc payload đó như văn bản UTF-8 thông thường và mong thấy các tên field hoặc dấu ngoặc JSON.

### 2.1. CBOR phù hợp với trao đổi liên hệ thống

CBOR có lợi thế khi:

- Hai phía dùng ngôn ngữ hoặc runtime khác nhau.
- Một phía không dùng Jackson.
- Giao thức cần định dạng nhị phân có đặc tả công khai.
- Dữ liệu có byte string hoặc tag semantics.
- Hệ thống IoT, thiết bị giới hạn tài nguyên hoặc giao thức nhị phân cần payload gọn.
- Cần một định dạng có thể được kiểm tra bằng nhiều implementation độc lập.

CBOR không phụ thuộc vào Java class name, package hoặc Jackson-specific metadata. Tuy nhiên, hai phía vẫn cần thống nhất schema: tên key, kiểu dữ liệu, tag được dùng, miền giá trị và semantics của field.

### 2.2. CBOR không đồng nghĩa với schema

CBOR định nghĩa cách mã hóa data item. Nó không tự định nghĩa rằng key temperature phải là decimal Celsius hay key device phải là identifier nào.

Hợp đồng ứng dụng vẫn cần mô tả:

- Các key bắt buộc.
- Kiểu dữ liệu và miền giá trị.
- Đơn vị đo.
- Tag semantics nếu có.
- Version của payload.
- Chính sách unknown field.
- Quy tắc tương thích giữa producer và consumer.

CBOR giải quyết encoding. Schema và validation giải quyết ý nghĩa của dữ liệu.

### 2.3. CBOR map key linh hoạt hơn JSON object key

Trong CBOR, map key có thể là nhiều loại data item, không chỉ text string. JSON object truyền thống dùng tên property dạng string.

Jackson databind khi bind POJO thường làm việc với tên property và các key serializer/deserializer theo mô hình của Jackson. Vì vậy, khả năng biểu diễn map key tổng quát của CBOR không có nghĩa mọi CBOR map với key phức tạp đều có thể bind trực tiếp vào Java bean.

Nếu giao thức dùng key không phải string, hãy kiểm tra API và serializer của module CBOR, rồi viết fixture độc lập cho đúng dạng map đó.

## 3. Vai trò của Smile

Smile là định dạng nhị phân được thiết kế cho Jackson để biểu diễn dữ liệu kiểu JSON một cách gọn và hiệu quả. Nó có parser/generator riêng và được tích hợp với databind thông qua SmileFactory.

Smile tập trung vào các cấu trúc quen thuộc:

- Object và field name.
- Array.
- String.
- Integer và floating-point.
- Boolean và null.
- Binary payload.
- Type/metadata theo các khả năng của format và Jackson.

Một ưu điểm của Smile là có thể chia sẻ field name và một số string value lặp lại trong cùng tài liệu. Khi object có nhiều record cùng key như id, type, timestamp, repeated names có thể được mã hóa ngắn hơn sau lần xuất hiện đầu.

Ví dụ JSON có nhiều object:

~~~json
[
  {"type": "reading", "device": "sensor-1", "value": 21.5},
  {"type": "reading", "device": "sensor-2", "value": 22.1},
  {"type": "reading", "device": "sensor-3", "value": 20.9}
]
~~~

Smile có thể tận dụng tên field và string lặp lại để giảm phần dữ liệu lặp trong encoding. Hiệu quả thực tế phụ thuộc cấu trúc và nội dung payload.

### 3.1. Smile thường phù hợp với hệ sinh thái Jackson

Smile hữu ích khi:

- Cả producer và consumer đều dùng Jackson hoặc implementation tương thích Smile.
- Payload có nhiều field name/string lặp lại.
- Hệ thống muốn giảm chi phí truyền JSON text.
- Dữ liệu được lưu trong cache hoặc message nội bộ.
- Cần dùng lại DTO và databind configuration hiện có.

Smile không phải định dạng JSON text có thể đọc trực tiếp bằng trình soạn thảo. Nó cũng không phải một chuẩn nhị phân phổ quát tương đương CBOR. Khi giao tiếp với hệ thống bên ngoài, phải xác nhận consumer có parser Smile tương thích.

### 3.2. Smile không phải thuật toán nén tổng quát

Smile có encoding gọn và chia sẻ string/name trong tài liệu, nhưng không nên coi nó như gzip, zstd hoặc một thuật toán nén tùy ý.

Nếu payload chứa các blob lớn, ảnh hoặc dữ liệu vốn đã nén, Smile có thể không giảm kích thước đáng kể. Nếu cần nén transport, hãy cân nhắc compression ở tầng giao thức và đo tổng chi phí CPU, latency, memory cùng kích thước bytes.

## 4. So sánh CBOR và Smile

| Tiêu chí | CBOR | Smile |
|---|---|---|
| Đặc tả | Chuẩn hóa trong RFC 8949 | Định dạng nhị phân của hệ sinh thái Jackson |
| Mục tiêu | Trao đổi data model nhị phân liên hệ thống | Biểu diễn JSON-like compact cho Jackson |
| Interoperability | Có nhiều implementation ngoài Java | Phụ thuộc consumer hỗ trợ Smile |
| Cấu trúc | Integer, byte/text string, array, map, tag, simple value | Object, array, scalar và binary token theo Smile |
| Map key | Có thể là data item nhiều kiểu | Theo mô hình object/field của Smile |
| Lặp field/string | Encoding theo CBOR rules | Có cơ chế chia sẻ field name/string trong document |
| Jackson integration | CBORFactory và databind | SmileFactory và databind |
| Dễ debug bằng mắt | Thấp, cần decoder/tool | Thấp, cần decoder/tool |
| Dùng với hệ thống khác ngôn ngữ | Phù hợp nếu hai bên thống nhất schema | Cần thư viện hỗ trợ Smile |
| Khi chọn | Giao thức nhị phân công khai, liên hệ thống | Giao tiếp nội bộ dùng Jackson |

Không có định dạng luôn nhanh hơn hoặc nhỏ hơn trong mọi trường hợp. Payload nhỏ, cấu trúc lặp nhiều, binary field lớn hoặc dữ liệu số có thể cho kết quả khác nhau. Hãy benchmark bằng dữ liệu đại diện cho ứng dụng.

## 5. Thêm dependency cho CBOR và Smile

CBOR module:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-cbor</artifactId>
</dependency>
~~~

Smile module:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-smile</artifactId>
</dependency>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-cbor")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-smile")
}
~~~

Nếu dùng Jackson BOM, không cần khai báo version riêng cho từng module thuộc BOM. Ví dụ Maven dependency management:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>...</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Coordinates của BOM và module cần được xác nhận theo major line mà dự án chọn. Không trộn module Jackson từ các major line khác nhau chỉ vì artifact name giống nhau.

### 5.1. Đồng bộ version

CBOR/Smile module phụ thuộc vào Jackson core và tích hợp với databind. Nếu module, core và databind không tương thích, có thể gặp lỗi linkage như NoSuchMethodError, NoClassDefFoundError hoặc lỗi parser/generator.

Sau khi thêm dependency, kiểm tra resolved graph:

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra cả runtime classpath và artifact cuối. Đừng chỉ xác nhận dependency xuất hiện trong file build.

## 6. Tạo CBOR mapper

Jackson CBOR module cung cấp CBORFactory. Có thể tạo ObjectMapper dùng factory này:

~~~java
import com.fasterxml.jackson.dataformat.cbor.CBORFactory;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper cborMapper =
    new ObjectMapper(new CBORFactory());
~~~

Từ đây có thể dùng databind API:

~~~java
byte[] payload = cborMapper.writeValueAsBytes(event);

OrderEvent restored =
    cborMapper.readValue(payload, OrderEvent.class);
~~~

writeValueAsBytes() trả về byte array chứa CBOR encoding. readValue(byte[], Class) đọc bytes đó thành Java object.

Không dùng writeValueAsString() để vận chuyển CBOR. Dữ liệu CBOR là nhị phân; chuyển nó thành String theo charset thông thường có thể làm hỏng byte sequence.

### 6.1. Dùng ObjectReader/ObjectWriter

~~~java
ObjectWriter writer = cborMapper.writerFor(OrderEvent.class);
ObjectReader reader = cborMapper.readerFor(OrderEvent.class);

byte[] payload = writer.writeValueAsBytes(event);
OrderEvent restored = reader.readValue(payload);
~~~

ObjectWriter và ObjectReader cho phép cố định target/source type và cấu hình theo operation. Chúng hữu ích khi mapper phục vụ nhiều loại message.

## 7. Tạo Smile mapper

Smile module cung cấp SmileFactory:

~~~java
import com.fasterxml.jackson.dataformat.smile.SmileFactory;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper smileMapper =
    new ObjectMapper(new SmileFactory());
~~~

Sử dụng tương tự:

~~~java
byte[] payload = smileMapper.writeValueAsBytes(event);

OrderEvent restored =
    smileMapper.readValue(payload, OrderEvent.class);
~~~

Jackson databind vẫn xử lý POJO và annotation. SmileFactory đảm nhiệm binary encoding/decoding.

Không đọc bytes Smile bằng new String(payload, UTF_8). Nếu cần log để debug, hãy deserialize về object hoặc JsonNode rồi ghi một representation text an toàn, có kiểm soát.

### 7.1. Header và document boundary

Smile có quy tắc framing/header riêng của format. Parser và generator của Jackson xử lý chúng theo cấu hình và phiên bản module. Nếu một hệ thống khác đọc Smile, hai bên phải thống nhất format options và cách nhận diện document.

Không tự thêm hoặc loại bỏ byte header bằng thao tác chuỗi. Hãy cấu hình SmileFactory hoặc API module tương ứng và test bằng payload thực tế.

## 8. Dùng cùng DTO cho JSON, CBOR và Smile

Ví dụ DTO:

~~~java
public record TelemetryEvent(
    String eventId,
    String deviceId,
    Instant occurredAt,
    BigDecimal value,
    boolean active
) {}
~~~

Một mapper JSON, CBOR và Smile có thể dùng cùng model:

~~~java
ObjectMapper jsonMapper = new ObjectMapper();

ObjectMapper cborMapper =
    new ObjectMapper(new CBORFactory());

ObjectMapper smileMapper =
    new ObjectMapper(new SmileFactory());
~~~

Tạo payload:

~~~java
TelemetryEvent event = new TelemetryEvent(
    "evt-100",
    "sensor-17",
    Instant.parse("2026-11-12T08:30:00Z"),
    new BigDecimal("24.75"),
    true
);

byte[] cborBytes = cborMapper.writeValueAsBytes(event);
byte[] smileBytes = smileMapper.writeValueAsBytes(event);
String jsonText = jsonMapper.writeValueAsString(event);
~~~

Ba output khác nhau về encoding nhưng có thể biểu diễn cùng dữ liệu logic. Consumer dùng mapper tương ứng để đọc:

~~~java
TelemetryEvent fromCbor =
    cborMapper.readValue(cborBytes, TelemetryEvent.class);

TelemetryEvent fromSmile =
    smileMapper.readValue(smileBytes, TelemetryEvent.class);

TelemetryEvent fromJson =
    jsonMapper.readValue(jsonText, TelemetryEvent.class);
~~~

Dùng cùng DTO không có nghĩa ba định dạng tạo bytes giống nhau. Cũng không bảo đảm mọi tính năng JSON đều có semantics giống nhau trong binary format. Hãy kiểm tra các kiểu đặc biệt, custom serializer, type metadata, binary value và map key.

## 9. Cấu hình Java Time và module bổ sung

Nếu DTO chứa Instant, LocalDate, Optional hoặc kiểu Java cần module bổ sung, đăng ký module tương ứng cho mapper binary giống như mapper JSON.

Ví dụ:

~~~java
ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());
cborMapper.registerModule(new JavaTimeModule());
cborMapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

ObjectMapper smileMapper = new ObjectMapper(new SmileFactory());
smileMapper.registerModule(new JavaTimeModule());
smileMapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

Cấu hình date/time cụ thể phụ thuộc hợp đồng. Nếu một hệ thống mong timestamp epoch còn hệ thống kia mong ISO-8601 string, không nên giả định cùng DTO sẽ tự tạo semantics giống nhau nếu mapper configuration khác nhau.

Có thể tạo factory cấu hình dùng chung cho các module cần thiết, nhưng không dùng chung JsonFactory giữa các format. Mỗi mapper cần factory đúng định dạng.

## 10. CBOR và kiểu dữ liệu nhị phân

Một khác biệt đáng chú ý giữa JSON text và CBOR là CBOR có byte string như một loại dữ liệu gốc. JSON không có byte string primitive; ứng dụng thường biểu diễn byte[] dưới dạng Base64 string hoặc một cấu trúc số.

Ví dụ DTO:

~~~java
public record Attachment(
    String fileName,
    byte[] content
) {}
~~~

Khi dùng JSON mapper, byte[] thường được biểu diễn dưới dạng Base64 string theo Jackson serializer mặc định. Với CBOR, module có thể ghi byte[] dưới dạng CBOR byte string, phù hợp hơn với dữ liệu nhị phân.

~~~java
Attachment attachment = new Attachment(
    "sample.bin",
    new byte[] { 1, 2, 3, 4, 5 }
);

byte[] cbor = cborMapper.writeValueAsBytes(attachment);
Attachment restored =
    cborMapper.readValue(cbor, Attachment.class);
~~~

Hãy xác nhận representation thực tế bằng test và kiểm tra với consumer ngoài Jackson. Nếu contract yêu cầu Base64 text ngay cả trong CBOR, cần cấu hình/serializer phù hợp thay vì dựa vào default.

Không nên dùng CBOR chỉ để tránh Base64 nếu payload vẫn phải chuyển qua một hệ thống chỉ nhận JSON. Lợi ích binary chỉ có khi toàn bộ đường truyền hỗ trợ đúng media type và byte payload.

## 11. CBOR tags và semantics ngoài JSON

CBOR hỗ trợ tag để gắn thêm ý nghĩa cho data item. Ví dụ, RFC 8949 định nghĩa các tag cho bignum, decimal fraction, bigfloat, date/time và các loại dữ liệu khác.

Tag không tự động biến thành một Java type có semantics chính xác trong mọi Jackson module. Khả năng parse, ghi và ánh xạ tag phụ thuộc phiên bản CBOR module và cách ứng dụng dùng Streaming API hoặc databind.

Nếu giao thức dựa vào tag:

- Ghi rõ tag number và semantics trong schema.
- Xác định implementation của producer/consumer có hỗ trợ tag đó không.
- Kiểm tra tag có được giữ, diễn giải hay bỏ qua khi đi qua JsonNode/POJO.
- Tạo fixture CBOR bytes độc lập.
- Kiểm tra round-trip giữa các implementation khác nhau.
- Không giả định tag được bảo toàn khi chuyển CBOR sang JSON hoặc Smile.

Đặc biệt, khi chuyển một CBOR document có tag sang JsonNode, một số semantics có thể không còn biểu diễn được trong JSON tree tổng quát. Nếu tag mang ý nghĩa nghiệp vụ, cần một mapping tường minh.

## 12. Smile và việc chia sẻ field name/string

Smile tối ưu payload JSON-like bằng cách mã hóa tên field và string value theo quy tắc riêng. Các tên field lặp lại có thể được tham chiếu qua bảng chia sẻ thay vì ghi toàn bộ nhiều lần.

Điều này có lợi với payload dạng record:

~~~json
[
  {"eventType": "reading", "deviceId": "sensor-1", "status": "ok"},
  {"eventType": "reading", "deviceId": "sensor-2", "status": "ok"},
  {"eventType": "reading", "deviceId": "sensor-3", "status": "ok"}
]
~~~

Trong JSON text, các chuỗi eventType, deviceId, status và reading, ok xuất hiện lặp. Smile có thể mã hóa một số chuỗi lặp gọn hơn trong phạm vi document.

Lợi ích phụ thuộc dữ liệu:

- Object có nhiều field name lặp thường có cơ hội giảm bytes.
- Payload chủ yếu là blob nhị phân có thể không hưởng lợi nhiều.
- Một object nhỏ có thể không tiết kiệm đáng kể.
- String ngẫu nhiên, không lặp có thể không tận dụng được sharing.

Không nên kết luận Smile luôn nhỏ hơn CBOR hoặc JSON. Benchmark bằng bộ payload thực tế.

## 13. Tree Model với CBOR và Smile

Cả hai mapper có thể đọc dữ liệu thành JsonNode:

~~~java
JsonNode cborTree = cborMapper.readTree(cborBytes);
JsonNode smileTree = smileMapper.readTree(smileBytes);
~~~

Có thể kiểm tra:

~~~java
String deviceId = cborTree.path("deviceId").asText();
BigDecimal value = cborTree.path("value").decimalValue();
~~~

Sau khi tạo tree, có thể ghi sang định dạng khác:

~~~java
String json = jsonMapper
    .writerWithDefaultPrettyPrinter()
    .writeValueAsString(cborTree);
~~~

Hoặc chuyển JSON tree thành CBOR:

~~~java
JsonNode jsonTree = jsonMapper.readTree(jsonText);
byte[] cborPayload = cborMapper.writeValueAsBytes(jsonTree);
~~~

Đây là chuyển đổi qua data model. Các semantics không có trong JsonNode tổng quát, chẳng hạn một số CBOR tags hoặc metadata format-specific, có thể bị mất. Không dùng tree conversion nếu cần bảo toàn mọi chi tiết nhị phân hoặc tag.

## 14. Streaming API cho CBOR và Smile

Khi payload lớn hoặc ứng dụng cần kiểm soát token, có thể dùng factory để tạo JsonParser/JsonGenerator.

CBOR:

~~~java
CBORFactory factory = new CBORFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        // Xử lý từng token.
    }
}
~~~

Smile:

~~~java
SmileFactory factory = new SmileFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        // Xử lý từng token.
    }
}
~~~

Cả hai parser phát ra Jackson JsonToken để code streaming có thể dùng cùng một mô hình xử lý. Nếu cần tạo generator:

~~~java
try (JsonGenerator generator = factory.createGenerator(outputStream)) {
    generator.writeStartObject();
    generator.writeStringField("deviceId", "sensor-17");
    generator.writeNumberField("value", 24.75);
    generator.writeEndObject();
}
~~~

Generator được tạo từ CBORFactory sẽ ghi CBOR; generator từ SmileFactory sẽ ghi Smile. Không cần tự mã hóa header hoặc token.

Streaming hữu ích khi:

- Dữ liệu lớn và không muốn giữ toàn bộ object graph.
- Muốn xử lý từng record.
- Cần giới hạn bộ nhớ.
- Chỉ cần một số field trong payload.
- Muốn kiểm soát thứ tự ghi token hoặc xử lý lỗi sớm.

## 15. Truyền binary payload qua HTTP

Khi dùng CBOR hoặc Smile qua HTTP, Content-Type phải thể hiện định dạng. Một số media type thường gặp:

| Format | Media type thường dùng |
|---|---|
| JSON | application/json |
| CBOR | application/cbor |
| Smile | application/x-jackson-smile |

Media type phải được hai phía thống nhất và framework phải có converter/codec tương ứng. Với API công khai, hãy kiểm tra quy ước media type mà hệ thống đối tác hỗ trợ.

Ví dụ gửi CBOR bytes qua một HTTP client:

~~~java
byte[] body = cborMapper.writeValueAsBytes(event);

HttpRequest request = HttpRequest.newBuilder(uri)
    .header("Content-Type", "application/cbor")
    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
    .build();
~~~

Phía nhận đọc bytes:

~~~java
OrderEvent event =
    cborMapper.readValue(requestBodyBytes, OrderEvent.class);
~~~

Ví dụ trên minh họa payload bytes. Trong ứng dụng thực tế, HTTP framework có thể tự chọn converter theo Content-Type và Accept. Hãy xác nhận converter được đăng ký và không vô tình gửi byte payload dưới Content-Type JSON.

### 15.1. Content negotiation

Một endpoint có thể hỗ trợ nhiều representation:

- application/json
- application/cbor
- application/x-jackson-smile

Client gửi Accept để yêu cầu format mong muốn; server trả Content-Type tương ứng. Nếu server không hỗ trợ format, cần trả lỗi phù hợp thay vì gửi binary bytes dưới nhãn JSON.

Không tự fallback sang một định dạng khác mà không thông báo. Client có thể cố parse bytes theo media type đã nhận.

## 16. Truyền qua message broker và lưu trữ

Binary payload có thể được gửi qua Kafka, RabbitMQ hoặc message broker khác dưới dạng byte array. Producer và consumer cần thống nhất:

- Format identifier hoặc Content-Type.
- Schema/version.
- Encoding và framing.
- Message key và partitioning nếu có.
- Compression ở broker/transport.
- Retention và replay compatibility.
- Cách xử lý payload từ producer cũ.

Ví dụ envelope metadata:

~~~text
content-type: application/cbor
schema-version: 2
payload: <binary bytes>
~~~

Không dựa vào phần mở rộng file hoặc đoán định dạng từ bytes nếu có thể truyền metadata rõ ràng.

Khi lưu file, dùng extension và metadata phù hợp, ví dụ .cbor hoặc .smile. Không mở file binary bằng editor text rồi sửa trực tiếp.

Nếu cần lưu payload lâu dài, hãy quản lý schema version và giữ reader tương thích với các phiên bản còn được replay. Thay đổi DTO hoặc serializer có thể khiến payload cũ không còn bind được.

## 17. Compatibility và versioning

CBOR và Smile là encoding format, không thay thế schema versioning. Một payload vẫn có thể thay đổi semantics khi field được đổi tên, đổi kiểu hoặc đổi ý nghĩa.

Nên có một cách xác định version:

~~~json
{
  "schemaVersion": 2,
  "eventType": "telemetry"
}
~~~

Với binary format, version có thể nằm trong message envelope hoặc trong chính data model. Đừng nhầm format version của Smile/CBOR với schema version của ứng dụng.

Các thay đổi cần đánh giá:

| Thay đổi | Rủi ro |
|---|---|
| Thêm optional field | Thường dễ tương thích nếu consumer bỏ qua unknown field |
| Thêm required field | Có thể làm consumer cũ không bind được |
| Đổi tên field | Breaking change nếu không hỗ trợ alias |
| Đổi integer sang string | Thay đổi data type |
| Đổi decimal precision/scale | Có thể thay đổi semantics |
| Đổi enum code | Consumer cũ có thể từ chối |
| Đổi discriminator | Có thể không resolve được subtype |
| Thay đổi CBOR tag | Có thể thay đổi semantics ngoài JsonNode |
| Đổi format JSON sang Smile | Consumer cần parser Smile và media type mới |

Giữ fixture bytes của version cũ và kiểm tra consumer mới đọc được nếu chính sách yêu cầu backward compatibility.

## 18. CBOR và Smile không tự cung cấp bảo mật

Binary format không tự động mã hóa, xác thực hoặc bảo vệ payload khỏi giả mạo. Bytes CBOR/Smile vẫn có thể chứa dữ liệu không tin cậy.

Cần tiếp tục áp dụng:

- TLS khi truyền qua network.
- Authentication và authorization ở transport/application layer.
- Giới hạn request/message size.
- Parser constraints và nesting limits nếu được hỗ trợ.
- Kiểm tra range, precision và schema.
- Không bật polymorphic typing rộng cho input bên ngoài.
- Dùng logical subtype ID và allowlist nếu cần polymorphism.
- Cập nhật Jackson và dependency parser theo advisory.
- Không deserialize vào kiểu tùy ý do payload điều khiển.
- Giới hạn thời gian xử lý và số record.

CBOR tags hoặc Smile metadata không phải cơ chế authorization. Định dạng nhị phân cũng không làm dữ liệu an toàn chỉ vì người đọc không thể mở nó bằng text editor.

### 18.1. Kiểm soát polymorphic deserialization

Nếu dùng @JsonTypeInfo, ưu tiên logical type id và subtype được khai báo rõ. Không cho payload tự chọn tên class Java tùy ý.

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = SensorReading.class, name = "reading"),
    @JsonSubTypes.Type(value = SensorAlert.class, name = "alert")
})
public interface SensorEvent {}
~~~

Test unknown type id và missing discriminator. Nếu input đến từ thiết bị hoặc đối tác bên ngoài, chỉ chấp nhận các subtype được phép.

### 18.2. Giới hạn parser và payload

Nếu phiên bản Jackson hỗ trợ StreamReadConstraints, cấu hình giới hạn nesting, string và number phù hợp. Đồng thời giới hạn body size ở HTTP gateway hoặc broker consumer.

CBOR và Smile có thể chứa payload binary hoặc cấu trúc lồng nhau. Đừng giả định binary format đồng nghĩa payload nhỏ hoặc parser không thể bị tiêu tốn tài nguyên.

## 19. Hiệu năng và lựa chọn format bằng benchmark

Khi so sánh JSON, CBOR và Smile, đo cả:

- Kích thước payload bytes.
- Thời gian serialize.
- Thời gian deserialize.
- CPU và allocation.
- Peak memory.
- Throughput khi concurrency cao.
- Chi phí compression nếu có.
- Tỷ lệ payload lỗi hoặc không tương thích.
- Khả năng debug và vận hành.

Ví dụ một benchmark đơn giản cần chạy trên dữ liệu đại diện:

~~~java
byte[] json = jsonMapper.writeValueAsBytes(event);
byte[] cbor = cborMapper.writeValueAsBytes(event);
byte[] smile = smileMapper.writeValueAsBytes(event);

System.out.println("JSON bytes: " + json.length);
System.out.println("CBOR bytes: " + cbor.length);
System.out.println("Smile bytes: " + smile.length);
~~~

Đây chỉ là phép đo kích thước một payload, không phải benchmark hiệu năng hoàn chỉnh. Để đo throughput/latency, dùng JMH hoặc harness phù hợp, warm-up JVM, lặp nhiều lần, dùng cùng dữ liệu và cùng cấu hình mapper.

Không kết luận từ một payload duy nhất. Một cấu trúc nhiều field name lặp có thể có kết quả khác với payload chủ yếu là string dài hoặc byte array.

### 19.1. Trade-off vận hành

| Yếu tố | JSON text | CBOR | Smile |
|---|---|---|---|
| Debug bằng mắt | Dễ | Khó | Khó |
| Tooling phổ thông | Rộng | Tùy hệ sinh thái | Hẹp hơn |
| Interoperability | Rất rộng | Rộng theo RFC | Cần Smile support |
| Binary value | Thường Base64/string hoặc cấu trúc khác | Có byte string | Có binary token |
| Payload compact | Có thể lớn hơn | Thường compact | Có thể compact khi string lặp |
| Schema | Cần hợp đồng riêng | Cần hợp đồng riêng | Cần hợp đồng riêng |
| Bảo mật | Cần kiểm soát | Cần kiểm soát | Cần kiểm soát |

Nếu khả năng quan sát và tương thích phổ thông quan trọng hơn vài phần trăm payload, JSON có thể vẫn là lựa chọn tốt. Nếu giao thức liên hệ thống cần binary standard, xem xét CBOR. Nếu cả hai phía kiểm soát Jackson và muốn encoding compact, xem xét Smile.

## 20. Kiểm thử round-trip cho CBOR và Smile

Một test cơ bản:

~~~java
@Test
void cborRoundTripPreservesEvent() throws Exception {
    TelemetryEvent source = sampleEvent();

    byte[] bytes = cborMapper.writeValueAsBytes(source);

    TelemetryEvent restored =
        cborMapper.readValue(bytes, TelemetryEvent.class);

    assertEquals(source, restored);
}
~~~

Smile:

~~~java
@Test
void smileRoundTripPreservesEvent() throws Exception {
    TelemetryEvent source = sampleEvent();

    byte[] bytes = smileMapper.writeValueAsBytes(source);

    TelemetryEvent restored =
        smileMapper.readValue(bytes, TelemetryEvent.class);

    assertEquals(source, restored);
}
~~~

Round-trip xác nhận mapper có thể đọc lại dữ liệu do chính nó ghi. Nhưng nó không chứng minh interoperability với implementation khác hoặc schema đã công bố.

### 20.1. So sánh data model thay vì bytes

Hai lần serialize cùng object có thể tạo bytes khác nhau do thứ tự property, generator options hoặc format-specific encoding. Không assert byte array bằng nhau trừ khi hợp đồng yêu cầu deterministic/canonical encoding và đã cấu hình đúng.

Có thể đọc payload về JsonNode rồi so sánh cấu trúc:

~~~java
JsonNode expected = jsonMapper.valueToTree(source);

JsonNode fromCbor = cborMapper.readTree(cborBytes);
JsonNode fromSmile = smileMapper.readTree(smileBytes);

assertEquals(expected, fromCbor);
assertEquals(expected, fromSmile);
~~~

Cách này kiểm tra data model mà các mapper nhìn thấy. Nó không kiểm tra các tag hoặc metadata format-specific đã bị bỏ qua.

### 20.2. Test interoperability độc lập

Nếu CBOR được trao đổi với một implementation khác ngôn ngữ:

- Lấy fixture CBOR được tạo bởi implementation đó.
- Đọc fixture bằng Jackson.
- Ghi payload bằng Jackson và đọc bằng implementation đối tác.
- Kiểm tra map key, integer range, decimal, byte string, tag và null.
- Giữ fixture theo schema version.

Với Smile, kiểm tra producer/consumer dùng các phiên bản Jackson được hỗ trợ và cấu hình tương thích. Đừng giả định consumer không dùng Jackson có sẵn Smile parser.

## 21. Test binary payload và kiểu đặc biệt

Nên có fixture cho:

- Byte array rỗng và byte array lớn.
- Integer ở boundary.
- BigInteger/BigDecimal nếu contract dùng.
- Timestamp và timezone.
- Enum và unknown enum.
- Polymorphic subtype.
- Null/missing/empty collection.
- Map key.
- Unknown field.
- Payload bị cắt cụt hoặc bytes không hợp lệ.
- Tag CBOR nếu giao thức sử dụng.
- Binary format header/framing nếu có.

Test byte[]:

~~~java
@Test
void preservesBinaryAttachment() throws Exception {
    Attachment source = new Attachment(
        "sample.bin",
        new byte[] { 1, 2, 3, 4, 5 }
    );

    byte[] bytes = cborMapper.writeValueAsBytes(source);
    Attachment restored =
        cborMapper.readValue(bytes, Attachment.class);

    assertArrayEquals(source.content(), restored.content());
}
~~~

Test không nên chỉ kiểm tra object equality nếu class dùng array, vì equals() mặc định của array so sánh identity. Dùng assertArrayEquals để so sánh nội dung bytes.

## 22. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đọc CBOR bằng JSON mapper | Sai factory/parser | Dùng CBORFactory |
| Đọc Smile bằng CBOR mapper hoặc ngược lại | Nhầm binary format | Chọn mapper đúng Content-Type/format id |
| Chuyển binary bytes thành UTF-8 String | Binary payload không phải text | Giữ byte[] hoặc InputStream |
| Chỉ nâng dataformat module | Core/databind lệch version | Dùng BOM và kiểm tra dependency tree |
| Nghĩ CBOR/Smile tự có schema | Nhầm encoding với contract | Định nghĩa schema/version riêng |
| Giả định Smile tương thích mọi parser | Smile không phổ quát như CBOR | Xác nhận consumer có Smile implementation |
| Giả định CBOR tag luôn map thành Java type | Tag support phụ thuộc module | Test tag cụ thể và quy định mapping |
| Cho rằng binary luôn nhỏ hơn JSON | Payload phụ thuộc nội dung | Benchmark dữ liệu thực tế |
| Dùng Tree Model để bảo toàn mọi tag | JsonNode không chứa mọi semantics format | Giữ representation format-specific khi cần |
| Không gửi Content-Type đúng | Consumer chọn sai parser | Thống nhất media type và content negotiation |
| Không version hóa payload | Consumer cũ không đọc được message mới | Thêm schema version và fixture cũ |
| Không giới hạn payload | Parser vẫn có thể tiêu tốn tài nguyên | Giới hạn request, token và thời gian |
| So sánh byte output tuyệt đối | Encoding có thể khác dù data model giống | So sánh JsonNode hoặc kiểm canonical encoding |
| Round-trip pass nhưng đối tác không đọc được | Hai chiều dùng cùng implementation | Test fixture/interoperability độc lập |

## 23. Quy trình chọn CBOR hay Smile

1. Xác định producer và consumer, ngôn ngữ/runtime của mỗi phía.
2. Nếu cần chuẩn nhị phân công khai, ưu tiên đánh giá CBOR.
3. Nếu cả hai phía dùng Jackson và cần encoding JSON-like compact, đánh giá Smile.
4. Kiểm tra module và dependency compatibility qua BOM.
5. Xác định schema, media type và version của payload.
6. Kiểm tra các kiểu đặc biệt như byte[], BigInteger, BigDecimal, date/time và polymorphism.
7. Benchmark kích thước, latency, CPU và memory trên payload thực.
8. Cấu hình mapper/factory riêng cho mỗi format.
9. Test round-trip và fixture độc lập từ implementation khác nếu có.
10. Kiểm tra HTTP/broker adapter truyền bytes và Content-Type đúng.
11. Giới hạn input, kiểm soát subtype và cập nhật dependency.
12. Giữ fixture/version cũ để bảo vệ replay và backward compatibility.

## 24. Nguyên tắc nên giữ

- CBOR là định dạng nhị phân được chuẩn hóa trong RFC 8949.
- Smile là định dạng nhị phân JSON-like gắn với hệ sinh thái Jackson.
- Hai module cung cấp factory/parser/generator riêng nhưng có thể dùng lại Jackson databind.
- Dùng CBOR khi cần interoperability với implementation độc lập.
- Dùng Smile khi producer/consumer có hỗ trợ Smile và lợi ích compact được đo thấy.
- CBOR/Smile là encoding, không tự định nghĩa schema nghiệp vụ.
- Dùng byte[] hoặc stream để truyền binary; không chuyển bytes thành String UTF-8 tùy tiện.
- Dùng đúng CBORFactory hoặc SmileFactory cho từng payload.
- Đồng bộ module với Jackson core/databind bằng BOM hoặc constraints.
- Kiểm tra byte string, tag, map key và số lớn theo contract thực tế.
- Không giả định Tree Model giữ mọi semantics đặc thù của CBOR.
- Thống nhất Content-Type, schema version và framing ở tầng transport.
- Binary format không tự mã hóa, xác thực hoặc bảo vệ dữ liệu.
- Benchmark trên payload thực thay vì mặc định format nào luôn nhanh/nhỏ hơn.
- Test round-trip cùng fixture độc lập và interoperability khi có đối tác ngoài Jackson.

CBOR và Smile mở rộng Jackson sang các định dạng nhị phân mà vẫn giữ được phần lớn trải nghiệm databind quen thuộc. CBOR phù hợp khi cần một encoding có đặc tả công khai và khả năng trao đổi giữa nhiều implementation; Smile phù hợp khi các phía cùng hỗ trợ định dạng Jackson và muốn tận dụng encoding compact cho dữ liệu JSON-like. Việc lựa chọn cần dựa trên interoperability, schema, media type, kiểu dữ liệu thực tế, bảo mật và benchmark, sau đó được bảo vệ bằng fixture và contract test.

