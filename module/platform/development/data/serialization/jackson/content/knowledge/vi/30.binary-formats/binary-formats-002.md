# Phân biệt cấu trúc dữ liệu và cách mã hóa trên đường truyền

Khi một ứng dụng serialize object Java, có hai quyết định khác nhau thường bị gộp làm một: **dữ liệu có cấu trúc và ý nghĩa gì**, và **cấu trúc đó được mã hóa thành những byte nào để truyền đi**. Phân biệt hai lớp này giúp thay JSON bằng định dạng nhị phân, tối ưu message hoặc nâng cấp Jackson mà không vô tình thay đổi hợp đồng dữ liệu.

Ví dụ, một sự kiện nghiệp vụ có thể gồm mã sự kiện, thời điểm xảy ra, số tiền và danh sách nhãn. Cấu trúc logic đó có thể được biểu diễn bằng JSON văn bản, Jackson Smile hoặc CBOR. Ba định dạng có cách mã hóa byte khác nhau, nhưng ứng dụng có thể giữ cùng ý nghĩa nghiệp vụ nếu mapping được thiết kế và kiểm thử đúng.

Jackson hỗ trợ cách tiếp cận này thông qua Databind và các format module. Databind ánh xạ object Java thành dữ liệu có cấu trúc; factory/parser/generator của từng định dạng chịu trách nhiệm đọc hoặc ghi cách biểu diễn trên đường truyền.

## 1. Hai khái niệm cần tách biệt

**Cấu trúc dữ liệu** mô tả những thành phần có ý nghĩa trong thông điệp:

- Object có những field nào?
- Field có kiểu string, number, boolean, array, object hay binary data?
- Danh sách có thứ tự không?
- Giá trị nào bắt buộc, nullable hoặc có mặc định?
- Map key được hiểu là mã gì?
- Ngày giờ, tiền tệ và enum có ý nghĩa nghiệp vụ nào?

**Cách mã hóa trên đường truyền** mô tả cách biểu diễn cấu trúc đó thành bytes:

- Dùng ký tự văn bản hay token nhị phân?
- Tên field được ghi trực tiếp hay dùng bảng chia sẻ?
- Số, string và binary value được mã hóa ra sao?
- Độ dài dữ liệu được biểu diễn thế nào?
- Message được đóng khung và nhận diện định dạng ra sao?

Ví dụ cùng một cấu trúc logic:

```text
Event
 ├── eventId: string
 ├── occurredAt: timestamp
 ├── amount: decimal
 └── labels: array<string>
```

có thể được ghi thành JSON:

```json
{
  "eventId": "evt-1001",
  "occurredAt": "2026-11-12T10:30:00Z",
  "amount": 19.95,
  "labels": ["payment", "mobile"]
}
```

hoặc thành bytes theo Smile/CBOR. Byte sequence không giống nhau, nhưng ý nghĩa của eventId, occurredAt, amount và labels có thể được giữ nguyên.

Không nên dùng kích thước file hoặc việc deserialize thành công làm bằng chứng duy nhất rằng hai payload có cùng cấu trúc và ngữ nghĩa.

## 2. Vị trí của từng lớp trong Jackson

Luồng serialization thường có thể nhìn theo các lớp:

```text
Domain object / DTO
        │
        ▼
Jackson Databind
  - chọn serializer theo kiểu Java
  - đọc property và giá trị
  - áp dụng annotation/module
        │
        ▼
Jackson streaming API
  - object / array / field name
  - string / number / boolean / null / binary
        │
        ▼
Format factory + generator
  - JSON, Smile hoặc CBOR
  - chuyển token thành bytes hoặc text
        │
        ▼
Transport / file / message broker
```

Chiều đọc đi ngược lại:

```text
Transport bytes
        │
        ▼
Format factory + parser
        │
        ▼
Jackson token stream
        │
        ▼
Databind deserializer
        │
        ▼
DTO / domain object
```

ObjectMapper là lớp điều phối Databind cùng một JsonFactory. Khi dùng JSON, factory mặc định xử lý JSON. Khi dùng Smile hoặc CBOR, ta truyền factory tương ứng vào ObjectMapper.

Điểm quan trọng là format factory thay đổi cách đọc/ghi trên đường truyền. Nó không tự quyết định toàn bộ ý nghĩa nghiệp vụ. Ý nghĩa vẫn đến từ DTO, serializer/deserializer, module, annotation và hợp đồng dữ liệu của ứng dụng.

## 3. JSON, Smile và CBOR khác nhau ở đâu?

Jackson có các module định dạng nhị phân phổ biến:

| Định dạng | Thư viện/factory | Đặc điểm |
| --- | --- | --- |
| JSON | jackson-core | Văn bản dễ đọc, dễ debug, phổ biến trong HTTP API |
| Smile | jackson-dataformat-smile, SmileFactory | Định dạng nhị phân trong hệ sinh thái Jackson, biểu diễn dữ liệu kiểu JSON bằng token compact |
| CBOR | jackson-dataformat-cbor, CBORFactory | Định dạng nhị phân có tiêu chuẩn riêng, hỗ trợ nhiều kiểu dữ liệu cơ bản và được dùng ngoài Jackson |

Smile được thiết kế để mã hóa dữ liệu theo phong cách JSON bằng dạng nhị phân compact. Nó có thể tận dụng việc chia sẻ tên field hoặc string lặp lại để giảm chi phí biểu diễn trong một số payload.

CBOR là định dạng nhị phân được chuẩn hóa độc lập với Jackson. Nó có các major type cho integer, byte string, text string, array, map, tag và một số dạng scalar khác.

Hai định dạng đều không phải “JSON được nén”. Chúng có quy tắc mã hóa riêng. Compression là một bước khác, ví dụ gzip hoặc zstd, có thể được áp dụng thêm ở tầng transport nếu phù hợp.

Việc chuyển sang Smile/CBOR không tự động bảo đảm payload nhỏ hơn hoặc xử lý nhanh hơn. Hiệu quả phụ thuộc dữ liệu, tên field lặp lại, string, số, byte array, cách triển khai và chi phí của consumer. Cần benchmark trên payload đại diện.

## 4. Cùng một DTO có thể dùng nhiều format factory

Giả sử model:

```java
public record Event(
    String eventId,
    Instant occurredAt,
    BigDecimal amount,
    List<String> labels,
    byte[] payload
) {}
```

Tạo mapper cho từng định dạng:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.dataformat.smile.SmileFactory;
import com.fasterxml.jackson.dataformat.cbor.CBORFactory;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper jsonMapper = new ObjectMapper()
    .registerModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

ObjectMapper smileMapper = new ObjectMapper(new SmileFactory())
    .registerModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

ObjectMapper cborMapper = new ObjectMapper(new CBORFactory())
    .registerModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Ba mapper dùng cùng DTO và module Java Time, nhưng mỗi mapper có factory khác nhau. Cấu hình WRITE_DATES_AS_TIMESTAMPS trong ví dụ giúp thời điểm được biểu diễn theo dạng text ISO-8601 trong mapping này; nếu hợp đồng muốn dạng khác, phải quy định và test riêng.

Serialize:

```java
Event event = new Event(
    "evt-1001",
    Instant.parse("2026-11-12T10:30:00Z"),
    new BigDecimal("19.95"),
    List.of("payment", "mobile"),
    new byte[] { 10, 20, 30, 40 }
);

String json = jsonMapper.writeValueAsString(event);

byte[] smileBytes = smileMapper.writeValueAsBytes(event);
byte[] cborBytes = cborMapper.writeValueAsBytes(event);
```

Đầu ra JSON là văn bản có thể đọc trực tiếp. Smile và CBOR là bytes nhị phân; không nên xem chúng như chuỗi UTF-8.

Deserialize:

```java
Event fromJson = jsonMapper.readValue(json, Event.class);
Event fromSmile = smileMapper.readValue(smileBytes, Event.class);
Event fromCbor = cborMapper.readValue(cborBytes, Event.class);
```

Mỗi mapper cần dùng đúng factory tương ứng với bytes đầu vào. Không đưa Smile bytes vào JSON mapper hoặc CBOR bytes vào Smile mapper rồi kỳ vọng Jackson tự đoán định dạng.

## 5. Cấu trúc logic có thể giống nhau dù bytes khác nhau

Giả sử cùng Event được serialize qua ba mapper:

| Thành phần | JSON | Smile | CBOR |
| --- | --- | --- | --- |
| eventId | JSON string | Binary string/token | Text string |
| occurredAt | Theo serializer Java Time | Theo serializer Java Time và Smile generator | Theo serializer Java Time và CBOR generator |
| amount | JSON number | Token/number theo Smile | Number theo CBOR encoding |
| labels | JSON array | Binary array/token | CBOR array |
| payload (byte[]) | Thường là Base64 string | Có thể dùng binary token | Có thể dùng CBOR byte string |

Bảng này mô tả cách ánh xạ phổ biến của Jackson Databind. Cách biểu diễn cụ thể vẫn phụ thuộc serializer, phiên bản module và cấu hình. Đặc biệt với số thập phân, ngày giờ và byte array, hãy kiểm tra giá trị thực tế sau khi đọc lại.

Đối với byte[], JSON không có kiểu byte string riêng nên Jackson thường ghi nội dung thành Base64 string. Smile/CBOR có khả năng biểu diễn binary value ở dạng nhị phân. Điều đó có nghĩa cùng một property Java có thể có kiểu wire khác nhau giữa JSON và định dạng nhị phân mà vẫn được ánh xạ về cùng byte[].

Không nên so sánh byte sequence của ba format để đánh giá dữ liệu có giống nhau hay không. Hãy so sánh các giá trị nghiệp vụ sau khi deserialize bằng mapper tương ứng.

## 6. Dùng đúng API cho output nhị phân

Với JSON, các API dạng String rất tiện:

```java
String json = jsonMapper.writeValueAsString(event);
Event restored = jsonMapper.readValue(json, Event.class);
```

Với Smile/CBOR, ưu tiên API byte hoặc stream:

```java
byte[] bytes = smileMapper.writeValueAsBytes(event);

Event restored = smileMapper.readValue(bytes, Event.class);
```

Khi làm việc với file hoặc network stream:

```java
try (OutputStream output = Files.newOutputStream(path)) {
    cborMapper.writeValue(output, event);
}

try (InputStream input = Files.newInputStream(path)) {
    Event restored = cborMapper.readValue(input, Event.class);
}
```

Không dùng writeValueAsString() để lấy output của binary mapper. Cũng không làm:

```java
String text = new String(smileBytes, StandardCharsets.UTF_8);
```

rồi kỳ vọng nhận được nội dung đọc được. Bytes có thể chứa byte không hợp lệ trong UTF-8, byte điều khiển hoặc token nhị phân. Nếu cần hiển thị bytes trong log hoặc JSON wrapper, dùng Base64 có chủ đích; việc đó tạo thêm một lớp mã hóa text và không còn là payload Smile/CBOR nguyên bản.

## 7. Binary format không đồng nghĩa với nén, mã hóa bảo mật hoặc schema

Ba khái niệm cần phân biệt:

- **Binary serialization**: chuyển cấu trúc dữ liệu thành byte sequence theo định dạng như Smile/CBOR.
- **Compression**: giảm kích thước byte bằng thuật toán như gzip/zstd.
- **Encryption**: mã hóa để bảo mật nội dung, cần quản lý key và xác thực theo thiết kế.
- **Schema**: mô tả field, kiểu, required, version và ý nghĩa dữ liệu.

Smile/CBOR không tự động mã hóa bí mật dữ liệu và không thay thế TLS hoặc encryption ở tầng lưu trữ. Chúng cũng không tự động nén toàn bộ payload như gzip.

Một payload CBOR có thể có cấu trúc tự mô tả ở mức kiểu dữ liệu, nhưng điều đó không có nghĩa nó chứa schema nghiệp vụ đầy đủ như “field amount là tiền VND, scale 2, bắt buộc trong event version 3”. Ứng dụng vẫn cần hợp đồng hoặc schema riêng.

Tương tự, serialize một Java class sang Smile/CBOR không có nghĩa tên class, package hoặc schema Java được nhúng vào bytes để consumer tự tái tạo object. Consumer vẫn cần biết target type và quy tắc mapping. Type metadata chỉ được ghi khi ứng dụng cấu hình rõ cơ chế polymorphic typing hoặc serializer tương ứng.

## 8. Chọn định dạng theo consumer và hợp đồng

Chọn format dựa trên toàn bộ đường đi của dữ liệu:

| Tiêu chí | JSON | Smile | CBOR |
| --- | --- | --- | --- |
| Khả năng đọc bằng mắt | Rất tốt | Thấp | Thấp |
| Hỗ trợ rộng ngoài Java | Rất rộng | Phụ thuộc ecosystem hỗ trợ Smile | Rộng nhờ tiêu chuẩn CBOR |
| Payload binary | Thường biểu diễn qua Base64 | Có binary token | Có byte string |
| Interoperability | Phổ biến | Cần consumer hỗ trợ Smile | Consumer cần hỗ trợ CBOR |
| Debug thủ công | Dễ | Cần decoder/tool | Cần decoder/tool |
| Schema nghiệp vụ | Cần hợp đồng riêng | Cần hợp đồng riêng | Cần hợp đồng riêng |

JSON thường phù hợp với public HTTP API, cấu hình và tích hợp cần khả năng đọc thủ công. Smile có thể phù hợp khi cả producer và consumer dùng hệ sinh thái Jackson và cần định dạng nhị phân compact. CBOR phù hợp khi cần định dạng nhị phân có chuẩn độc lập và nhiều nền tảng có thể triển khai.

Không chọn Smile chỉ vì ứng dụng đang dùng Jackson; cũng không chọn CBOR chỉ vì nó là chuẩn. Consumer, công cụ quan sát, versioning, media type, throughput và yêu cầu vận hành mới quyết định lựa chọn.

## 9. Media type và format negotiation

Khi truyền qua HTTP, producer và consumer cần thống nhất định dạng bằng header hoặc giao thức đã định nghĩa.

Ví dụ:

- JSON thường dùng application/json.
- CBOR thường dùng application/cbor.
- Smile thường dùng media type mà hệ thống và consumer đã thống nhất; một giá trị thường gặp là application/x-jackson-smile.

Request có thể dùng Content-Type để chỉ format của body; Accept có thể thể hiện format response client chấp nhận.

Không nên đoán format chỉ bằng cách thử lần lượt nhiều mapper trên cùng bytes. Cách đó gây mơ hồ, tốn tài nguyên và có thể làm parser nhận nhầm dữ liệu. Hãy xác định format qua media type, message header, protocol envelope hoặc cấu hình channel.

Nếu broker có topic riêng cho từng format, ghi rõ trong schema registry/tài liệu topic. Nếu cùng topic chứa nhiều format, cần header định dạng rõ ràng và chính sách xử lý khi header không khớp bytes.

## 10. Framing và ranh giới message là trách nhiệm của transport

Một byte stream không tự động nói cho consumer biết một message kết thúc ở đâu. Khi truyền binary data qua TCP, socket hoặc stream liên tục, hệ thống cần quy tắc framing:

- Length prefix.
- Message delimiter an toàn cho format.
- Frame protocol của broker.
- HTTP body boundary.
- Container/envelope có độ dài đã xác định.

Không giả định một lần gọi parser sẽ luôn tương ứng với một message ở mọi transport. Cần biết transport đưa một message hoàn chỉnh, một frame hay một stream chứa nhiều giá trị.

Ví dụ một envelope nghiệp vụ có thể chứa version và payload:

```json
{
  "schemaVersion": 2,
  "eventType": "customer.updated",
  "payload": {
    "customerId": "cus-1042",
    "displayName": "Nguyen An"
  }
}
```

Envelope logic này có thể được encode bằng JSON, Smile hoặc CBOR. Transport vẫn phải xác định ranh giới message và format của từng frame.

Nếu cần đọc nhiều message liên tiếp từ một stream, hãy dùng protocol framing đã định nghĩa và test trường hợp nhiều message nối nhau, message bị cắt giữa chừng và dữ liệu thừa sau frame.

## 11. Field name và Map key không tự nhiên giữ cùng wire representation

JSON object yêu cầu tên property là string. Jackson Databind thường xử lý property name và key của Map thông qua cơ chế field name/key serializer.

CBOR ở cấp định dạng cho phép map key thuộc nhiều kiểu dữ liệu hơn text string. Tuy nhiên, không nên suy ra rằng Map<K, V> dùng với Jackson Databind sẽ tự động ghi mọi Java key thành CBOR-native key có kiểu tương ứng. Mapping thông thường vẫn dựa vào field-name API và key serializer.

Ví dụ:

```java
Map<CurrencyCode, BigDecimal> rates = ...;
```

Nếu key là kiểu domain riêng, hãy định nghĩa serializer/deserializer cho key theo hợp đồng và kiểm thử riêng với từng format factory. Không giả định custom key serializer hoạt động giống nhau nếu một format không hỗ trợ cùng loại field name.

Khi cần map có key không phải string theo đúng CBOR data model, kiểm tra API của jackson-dataformat-cbor đang dùng và cân nhắc dùng CBOR tree/token API hoặc mô hình dữ liệu chuyên biệt. Đừng dựa vào khả năng của tiêu chuẩn CBOR để kết luận mọi đường mapping của Databind đều hỗ trợ cùng kiểu.

## 12. Kiểu số và độ chính xác

JSON biểu diễn số bằng văn bản. CBOR có các kiểu integer và floating-point nhị phân; Smile cũng có các token số riêng. Jackson Databind quyết định serializer được dùng cho Java type, còn format generator quyết định cách ghi token đó.

Với dữ liệu nghiệp vụ, hãy đặc biệt chú ý:

- int/long có thể bị giới hạn bởi phạm vi của consumer.
- BigInteger cần giữ nguyên độ lớn.
- BigDecimal cần quy định độ chính xác và scale.
- double/float có sai số biểu diễn nhị phân.
- Consumer không phải Java có thể dùng kiểu số khác hoặc mất precision.

Ví dụ tiền:

```java
BigDecimal amount = new BigDecimal("19.9500");
```

Nếu scale là một phần ý nghĩa nghiệp vụ, test cả scale. Nếu chỉ quan tâm giá trị số, so sánh bằng compareTo thay vì equals:

```java
assertEquals(0, expectedAmount.compareTo(actualAmount));
```

Không ép BigDecimal thành double chỉ để dùng một serializer chung. Chọn biểu diễn phù hợp và kiểm thử qua đúng mapper/consumer.

## 13. Ngày giờ và enum vẫn cần quy tắc công khai

Binary encoding không tự giải quyết timezone hoặc enum versioning. Nếu Instant được ghi thành chuỗi ISO, Smile/CBOR vẫn encode giá trị string theo cơ chế riêng của format. Nếu serializer ghi timestamp dạng số, consumer cần biết đơn vị và epoch.

Tương tự, enum có thể được ghi theo tên constant hoặc external code tùy cấu hình. Đổi tên enum trong Java không nên làm thay đổi code công khai nếu hợp đồng yêu cầu ổn định.

Nên quy định rõ:

- Timestamp là epoch seconds, milliseconds hay ISO-8601.
- Có timezone/offset hay không.
- Decimal dùng scale nào.
- Enum code có thể mở rộng ra sao.
- Giá trị không nhận diện được sẽ bị từ chối, giữ raw code hay ánh xạ sang UNKNOWN.

Các quy tắc này thuộc schema/contract layer, không phải thuộc tính tự động có được khi dùng binary format.

## 14. Schema evolution: binary không làm hợp đồng tự ổn định

Một message có thể được serialize thành Smile hoặc CBOR nhưng vẫn thay đổi breaking khi:

- Đổi tên field.
- Đổi kiểu field.
- Xóa field mà consumer cũ còn cần.
- Thay null thành omitted.
- Đổi đơn vị của số.
- Đổi enum code.
- Thay cấu trúc object thành array.
- Thay ý nghĩa nghiệp vụ mà giữ nguyên tên field.

Hãy dùng envelope hoặc metadata để xác định schema version:

```java
public record EventEnvelope<T>(
    int schemaVersion,
    String eventType,
    T payload
) {}
```

Khi deserialize generic envelope, giữ đầy đủ generic type bằng TypeReference hoặc JavaType:

```java
JavaType type = mapper.getTypeFactory()
    .constructParametricType(EventEnvelope.class, CustomerUpdated.class);

EventEnvelope<CustomerUpdated> envelope =
    mapper.readValue(bytes, type);
```

Việc có schemaVersion không tự thực hiện migration. Ứng dụng cần chọn reader/DTO theo version, hỗ trợ payload cũ trong giai đoạn chuyển tiếp và kiểm thử consumer tương ứng.

Không nhầm version của Smile/CBOR format với version schema nghiệp vụ. Format version nói về cách giải mã bytes; schema version nói về cấu trúc và ý nghĩa message.

## 15. Dependency cần đồng bộ

Các format module là dependency riêng. Ví dụ Maven khi đã dùng Jackson BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-smile</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-cbor</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>
</dependencies>
```

Thay 2.x.y bằng release Jackson 2.x đã được dự án lựa chọn. BOM giúp các artifact Jackson dùng cùng release train. Nếu framework quản lý Jackson version, tuân theo bộ version được framework hỗ trợ.

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.x.y"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-smile")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-cbor")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

Kiểm tra dependency resolution để tránh Core, Databind và format module lệch phiên bản. Không chỉ kiểm tra compile classpath; runtime classpath mới là thứ chạy parser/generator thực tế.

## 16. Kiểm thử ngữ nghĩa thay vì so sánh byte giữa các format

Một test tương thích tốt tạo object expectation độc lập, serialize qua từng format rồi deserialize bằng mapper tương ứng.

Ví dụ:

```java
Event expected = new Event(
    "evt-1001",
    Instant.parse("2026-11-12T10:30:00Z"),
    new BigDecimal("19.9500"),
    List.of("payment", "mobile"),
    new byte[] { 10, 20, 30, 40 }
);

byte[] smile = smileMapper.writeValueAsBytes(expected);
byte[] cbor = cborMapper.writeValueAsBytes(expected);

Event fromSmile = smileMapper.readValue(smile, Event.class);
Event fromCbor = cborMapper.readValue(cbor, Event.class);

assertEquals(expected.eventId(), fromSmile.eventId());
assertEquals(expected.eventId(), fromCbor.eventId());

assertEquals(expected.occurredAt(), fromSmile.occurredAt());
assertEquals(expected.occurredAt(), fromCbor.occurredAt());

assertEquals(0, expected.amount().compareTo(fromSmile.amount()));
assertEquals(0, expected.amount().compareTo(fromCbor.amount()));

assertEquals(expected.labels(), fromSmile.labels());
assertEquals(expected.labels(), fromCbor.labels());

assertArrayEquals(expected.payload(), fromSmile.payload());
assertArrayEquals(expected.payload(), fromCbor.payload());
```

Dùng assertArrayEquals cho byte[]. Nếu Event là record, equals mặc định của record so sánh array field theo identity; do đó không nên chỉ dùng assertEquals(expected, restored) để kiểm tra nội dung byte array.

Nếu scale của BigDecimal là một phần contract, bổ sung assertion về scale thay vì chỉ so sánh giá trị bằng compareTo.

### 16.1. Vì sao không so sánh bytes?

Các format dùng encoding khác nhau nên bytes khác nhau là điều bình thường. Ngay cả cùng một format, thay đổi thứ tự property, feature hoặc phiên bản serializer có thể làm bytes thay đổi trong khi dữ liệu logic vẫn tương đương.

Chỉ so sánh byte-for-byte khi hợp đồng thực sự yêu cầu canonical byte representation, ví dụ chữ ký số hoặc hash được tính trên chính bytes. Trong trường hợp đó, cần quy định canonicalization rõ ràng; không giả định mapper mặc định luôn tạo byte sequence ổn định giữa mọi phiên bản.

### 16.2. Tree comparison có giới hạn

Với phần dữ liệu chỉ gồm object, array, string, number, boolean và null, có thể đọc thành JsonNode để so sánh cấu trúc logic.

Nhưng byte[] là ví dụ cho khác biệt: JSON thường biểu diễn nó thành Base64 text, còn CBOR/Smile có thể trả về binary token. Tree node của hai mapper có thể khác loại dù khi bind vào byte[] thì kết quả giống nhau.

Vì vậy, chọn cách so sánh theo contract:

- So sánh tree cho phần dữ liệu có cùng kiểu wire logic.
- So sánh domain object cho ý nghĩa nghiệp vụ.
- So sánh raw bytes khi byte-level encoding là một phần hợp đồng.
- So sánh schema khi cần kiểm tra cấu trúc và kiểu được công bố.

## 17. Lưu fixture nhị phân và kiểm thử interoperability

Có thể lưu payload Smile/CBOR mẫu trong src/test/resources:

```text
src/test/resources/contracts/
  event-v1.json
  event-v1.smile
  event-v1.cbor
  event-v1-invalid.cbor
```

Fixture nhị phân không đọc được bằng mắt thường, nên lưu thêm tài liệu mô tả:

- Format và version thư viện đã tạo fixture.
- Schema version và event type.
- Ý nghĩa payload mẫu.
- Trường hợp biên được kiểm thử.
- Cách tái tạo fixture nếu cần.

Test đọc fixture bằng mapper tương ứng:

```java
Event event = smileMapper.readValue(
    resourceBytes("contracts/event-v1.smile"),
    Event.class
);
```

Hoặc CBOR:

```java
Event event = cborMapper.readValue(
    resourceBytes("contracts/event-v1.cbor"),
    Event.class
);
```

Để kiểm tra interoperability thực sự, nên có payload do consumer/producer độc lập tạo ra hoặc fixture theo chuẩn, không chỉ payload do chính mapper đang kiểm thử tự tạo. Nếu cả hai phía cùng dùng một lỗi encoding/assumption, round-trip nội bộ có thể che giấu vấn đề.

## 18. Kiểm thử dữ liệu thiếu, null, unknown field và sai kiểu

Định dạng nhị phân không làm mất nhu cầu kiểm thử các trường hợp biên của schema.

Với từng format, kiểm tra:

- Field bắt buộc bị thiếu.
- Field nullable có giá trị null.
- Field có giá trị mặc định.
- Field không biết.
- Field sai kiểu.
- Number vượt range hoặc precision.
- String quá dài.
- Collection rỗng, null và nhiều phần tử.
- Binary payload rỗng và payload lớn.
- Version cũ của message.

Cùng một DeserializationFeature có thể được dùng trên mapper khác format, nhưng parser và module vẫn có hành vi riêng. Hãy cấu hình và test từng mapper thay vì cho rằng test JSON tự động bao phủ Smile/CBOR.

Ví dụ bật strict unknown-property handling:

```java
ObjectMapper cborMapper = new ObjectMapper(new CBORFactory())
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Nếu consumer cần forward compatibility và bỏ qua field mới, chọn chính sách lenient có chủ đích. Nếu cần bảo toàn extension field, dùng Map/JsonNode hoặc mô hình extension riêng thay vì bỏ qua dữ liệu không biết.

## 19. Streaming và kích thước payload

Binary serialization vẫn có thể tạo payload rất lớn. Định dạng compact không thay thế giới hạn tài nguyên.

Với object lớn, có thể ghi trực tiếp ra OutputStream:

```java
try (OutputStream output = Files.newOutputStream(path)) {
    cborMapper.writeValue(output, largeEvent);
}
```

Khi đọc:

```java
try (InputStream input = Files.newInputStream(path)) {
    Event event = cborMapper.readValue(input, Event.class);
}
```

Cần phân biệt:

- Tổng kích thước message.
- Độ sâu lồng nhau.
- Số phần tử trong array.
- Độ dài từng string/byte string.
- Thời gian parse.
- Số message đồng thời.
- Bộ nhớ cần để materialize object.

Nếu cần xử lý hàng triệu record, cân nhắc streaming từng item thay vì deserialize toàn bộ thành List<Event>. Nếu transport có giới hạn frame, phải kiểm tra frame size trước khi tạo object graph.

## 20. Logging và quan sát binary payload

Không log bytes bằng cách chuyển trực tiếp sang UTF-8. Log kiểu đó có thể chứa ký tự rác, cắt mất dữ liệu hoặc làm hệ thống log xử lý sai encoding.

Một số cách quan sát an toàn hơn:

- Log metadata như format, event type, schema version, byte length và correlation id.
- Deserialize bằng mapper đúng format rồi log một số field đã được redaction.
- Dùng decoder/tool hỗ trợ Smile hoặc CBOR khi cần điều tra payload.
- Chỉ Base64 encode bytes khi cần đính kèm một mẫu nhỏ vào nơi chỉ hỗ trợ text; bảo vệ dữ liệu nhạy cảm và giới hạn kích thước log.

Binary format không làm payload tự an toàn. Dữ liệu vẫn có thể chứa token, thông tin cá nhân hoặc bí mật. Áp dụng chính sách redaction và access control như với JSON.

## 21. Lỗi thường gặp khi chuyển từ JSON sang binary format

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đọc bytes bằng JSON mapper thất bại | Bytes được mã hóa bằng Smile/CBOR | Dùng mapper có factory đúng format |
| Output binary thành chuỗi khó đọc | Dùng API String hoặc giải mã UTF-8 tùy tiện | Dùng writeValueAsBytes/OutputStream |
| Consumer không nhận được payload | Consumer chưa hỗ trợ format hoặc media type không khớp | Thống nhất format, header và decoder |
| Payload không nhỏ hơn dự kiến | Dữ liệu không phù hợp hoặc overhead format lớn | Benchmark payload đại diện; đo cả compression nếu có |
| Byte array khác khi so sánh tree | JSON Base64 string khác binary node | Bind thành byte[] và so sánh nội dung |
| Map key không được giữ kiểu | Databind dùng field-name/key serializer | Định nghĩa key mapping và test theo format |
| Number mất precision | Consumer hoặc serializer dùng kiểu số không phù hợp | Quy định decimal/integer và test range/scale |
| Consumer cũ không đọc được message | Schema thay đổi dù format vẫn hợp lệ | Version hóa schema và giữ compatibility fixture |
| Mapper không tìm thấy factory/module | Thiếu format dependency | Thêm module tương ứng và đồng bộ Jackson BOM |
| Runtime lỗi method/class | Core, Databind và format module lệch phiên bản | Kiểm tra runtime dependency tree |
| Log chứa ký tự rác | Bytes nhị phân bị xem như UTF-8 | Log metadata hoặc decode bằng mapper đúng format |
| Parser đọc nhầm frame | Transport boundary không được định nghĩa | Dùng framing/message boundary rõ ràng |

## 22. Quy trình thiết kế và chuyển đổi format

Khi cân nhắc chuyển JSON sang Smile hoặc CBOR:

1. Xác định cấu trúc nghiệp vụ độc lập với format.
2. Viết DTO/schema và payload mẫu đại diện.
3. Xác định consumer có hỗ trợ Smile/CBOR hay không.
4. Chọn format theo interoperability, tooling, hiệu năng và yêu cầu vận hành.
5. Thêm format module tương ứng và đồng bộ phiên bản Jackson.
6. Tạo mapper riêng với factory đúng định dạng.
7. Quy định media type, message header và framing.
8. Kiểm tra binary value, số thập phân, ngày giờ, enum và Map key.
9. Định nghĩa schema version riêng với format version.
10. Viết fixture và test semantic compatibility.
11. Benchmark kích thước, throughput, latency và bộ nhớ trên payload thực tế.
12. Chỉ chuyển consumer khi cả hai phía đã hỗ trợ format và có kế hoạch chuyển đổi.
13. Giữ JSON path trong giai đoạn migration nếu client chưa thể chuyển đồng thời.
14. Theo dõi lỗi decode, payload size và version mismatch sau khi triển khai.

Không nên đổi định dạng chỉ vì một microbenchmark nhỏ. Hãy đo toàn bộ đường đi, bao gồm encode, truyền, decode, mapping, logging và vận hành consumer.

## 23. Bài thực hành tổng hợp

Tạo một event:

```java
public record PaymentEvent(
    String eventId,
    Instant occurredAt,
    BigDecimal amount,
    List<String> labels,
    byte[] rawPayload
) {}
```

Thực hiện:

1. Tạo ObjectMapper cho JSON.
2. Tạo mapper dùng SmileFactory.
3. Tạo mapper dùng CBORFactory.
4. Đăng ký JavaTimeModule trên cả ba mapper.
5. Cấu hình cách ghi timestamp thống nhất.
6. Serialize cùng một event thành JSON string, Smile bytes và CBOR bytes.
7. Đọc từng output bằng mapper tương ứng.
8. So sánh eventId, occurredAt, amount, labels và nội dung rawPayload.
9. Dùng assertArrayEquals cho byte array.
10. Kiểm tra BigDecimal theo value và scale tùy hợp đồng.
11. Đọc fixture nhị phân do một producer khác tạo ra nếu có.
12. Thử dùng sai mapper để quan sát lỗi format mismatch.
13. Gửi payload qua transport với media type/header rõ ràng.
14. Kiểm thử message framing và payload bị cắt.
15. Benchmark JSON, Smile và CBOR trên tập payload thực tế.
16. Ghi lại kích thước, thời gian serialize/deserialize và bộ nhớ.
17. Thay đổi schema version và kiểm tra consumer cũ/mới.
18. Xác nhận log không chuyển bytes nhị phân thành UTF-8 tùy tiện.

Bài thực hành hoàn thành khi có thể chứng minh ba mapper tạo bytes khác nhau nhưng giữ cùng các giá trị nghiệp vụ được quy định, đồng thời consumer biết chính xác cách nhận diện và giải mã từng payload.

## 24. Nguyên tắc ghi nhớ

- Cấu trúc dữ liệu mô tả field, kiểu và ý nghĩa; encoding mô tả cách biến cấu trúc đó thành bytes.
- Databind ánh xạ Java object; format factory/parser/generator quyết định cách đọc/ghi JSON, Smile hoặc CBOR.
- Cùng DTO không có nghĩa bytes hoặc wire shape giống nhau.
- Smile là binary format trong hệ sinh thái Jackson; CBOR là binary format có chuẩn độc lập.
- Binary serialization không tự động là compression, encryption hoặc schema registry.
- Dùng writeValueAsBytes/OutputStream cho binary output và đúng mapper khi đọc.
- Không chuyển Smile/CBOR bytes thành UTF-8 để xem nội dung.
- byte[] có thể là Base64 string trong JSON và binary value trong format nhị phân.
- CBOR hỗ trợ map key rộng hơn ở cấp chuẩn, nhưng không suy ra Databind Map<K,V> tự động dùng mọi kiểu key native.
- Quy định precision của số, timezone của timestamp, enum code và semantics của null.
- Format version khác schema version; consumer vẫn cần biết target type và hợp đồng.
- Dùng media type/header và framing để xác định format và ranh giới message.
- So sánh ngữ nghĩa sau deserialize, không so sánh bytes giữa các format trừ khi canonical bytes là hợp đồng.
- Dùng fixture độc lập để kiểm tra interoperability, không chỉ round-trip trong cùng mapper.
- Đồng bộ Jackson Core, Databind và format module bằng BOM.
- Benchmark trên payload thực tế và kiểm soát kích thước, số phần tử, độ sâu, memory và concurrency.

Hãy xác định cấu trúc và ý nghĩa dữ liệu trước, rồi chọn cách mã hóa phù hợp với consumer. Khi hai lớp được tách biệt và có fixture/contract test riêng, ứng dụng có thể chuyển giữa JSON, Smile và CBOR mà không nhầm việc thay đổi bytes với việc thay đổi dữ liệu nghiệp vụ.
