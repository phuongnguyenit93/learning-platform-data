# Khai báo định dạng khi gửi nhận để tránh đọc sai nội dung

Jackson hỗ trợ nhiều định dạng dữ liệu ngoài JSON văn bản, trong đó có các định dạng nhị phân như CBOR, Smile, BSON và Avro. Các định dạng này có thể giúp giảm kích thước payload, tăng tốc độ xử lý hoặc đáp ứng hợp đồng của một hệ thống cụ thể. Tuy nhiên, byte của một định dạng không thể được đọc tùy ý bằng parser của định dạng khác. Nếu bên gửi tạo CBOR nhưng bên nhận lại dùng JSON `ObjectMapper`, kết quả thường là lỗi parse hoặc dữ liệu bị hiểu sai.

Để tránh lỗi đó, hai đầu giao tiếp phải thống nhất định dạng wire format và khai báo nó rõ ràng ở metadata của giao thức. Với HTTP, request `Content-Type` mô tả định dạng body được gửi lên; `Accept` mô tả định dạng response mà client muốn nhận. Với message broker hoặc file, cần metadata tương đương như content type, schema ID, schema version và file format. Ở phía Java, chọn đúng Jackson factory/mapper cho metadata đã xác thực rồi mới deserialize.

Một nguyên tắc quan trọng: **metadata định dạng, parser được chọn và bytes thực tế phải nhất quán**. Không đoán định dạng từ tên file hoặc vài byte đầu trong một API công khai, không chuyển bytes nhị phân thành String theo UTF-8, và không coi `Content-Encoding` là tên định dạng dữ liệu.

Các ví dụ dùng Jackson 2.x. Module cụ thể và tên media type có thể phụ thuộc format/version hoặc quy ước của hệ thống; hãy công bố một hợp đồng rõ ràng cho cả producer và consumer.

## 1. Wire format là gì?

Wire format là cách dữ liệu được biểu diễn thành bytes để truyền hoặc lưu trữ. Cùng một object Java có thể được mã hóa thành nhiều dạng khác nhau:

```text
Java object
    |
    +-- JSON mapper --> UTF-8 JSON bytes
    |
    +-- CBOR mapper --> CBOR binary bytes
    |
    +-- Smile mapper -> Smile binary bytes
    |
    +-- BSON mapper --> BSON document bytes
    |
    +-- Avro mapper --> Avro encoded bytes + schema contract
```

Ví dụ object:

```java
public record DeviceEvent(
        String deviceId,
        long sequence,
        boolean active) {
}
```

JSON có thể biểu diễn thành:

```json
{
  "deviceId": "sensor-17",
  "sequence": 42,
  "active": true
}
```

CBOR hoặc Smile biểu diễn cùng thông tin thành chuỗi bytes nhị phân. Nội dung logic giống nhau, nhưng bytes không giống JSON text và cần parser tương ứng.

### 1.1. Phân biệt định dạng dữ liệu với encoding và compression

Ba khái niệm thường bị nhầm:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Data format / media type | Payload được cấu trúc theo định dạng nào? | `application/json`, `application/cbor`, `application/x-jackson-smile` |
| Character encoding | Byte văn bản được giải mã thành ký tự theo bảng mã nào? | UTF-8 cho JSON/XML/YAML text |
| Content encoding | Payload đã được nén hoặc biến đổi ở tầng truyền tải như thế nào? | `gzip`, `br` |

Ví dụ HTTP body có thể là CBOR được nén gzip:

```http
Content-Type: application/cbor
Content-Encoding: gzip
```

`Content-Type` vẫn nói body sau khi giải mã content coding là CBOR. `Content-Encoding` cho biết cần giải nén trước khi đưa bytes cho CBOR parser. Gzip không biến CBOR thành JSON và không thay đổi loại mapper cần dùng.

Với định dạng nhị phân, không gắn `charset=UTF-8` một cách máy móc như đối với text. CBOR/Smile/BSON/Avro là binary representation; charset không mô tả cách parse cấu trúc của chúng.

## 2. Những định dạng nhị phân thường gặp trong Jackson

Jackson cung cấp các module dataformat riêng. Cần thêm module tương ứng và tạo mapper bằng factory của format đó.

| Định dạng | Jackson module thường dùng | Factory/mapper | Media type hoặc quy ước thường gặp |
|---|---|---|---|
| CBOR | `jackson-dataformat-cbor` | `CBORFactory` / `CBORMapper` | `application/cbor` |
| Smile | `jackson-dataformat-smile` | `SmileFactory` / `ObjectMapper` | `application/x-jackson-smile` trong hệ sinh thái Jackson |
| BSON | `jackson-dataformat-bson` | `BsonFactory` / `ObjectMapper` | Thường dùng `application/bson`; xác nhận với hệ thống đích |
| Avro | `jackson-dataformat-avro` | `AvroFactory` / `AvroMapper` | Media type/schema contract do giao thức hoặc nền tảng quy định |
| Ion | `jackson-dataformat-ion` | `IonFactory` / mapper tương ứng | `application/ion` trong các hệ thống dùng Amazon Ion |

Tên media type phải được hai bên thống nhất. Với format có media type đã đăng ký, ưu tiên dùng đúng tên chuẩn. Với format đặc thù hoặc cách đóng gói riêng, dùng vendor media type hoặc media type nội bộ có tài liệu hóa; không tự đặt nhiều tên alias không cần thiết.

Không phải mọi binary format đều có cùng đặc tính. CBOR và Smile có thể mang dữ liệu có cấu trúc kiểu JSON; BSON có mô hình document và kiểu dữ liệu riêng; Avro thường cần schema tương ứng để đọc binary payload. Việc khai báo `Content-Type` không tự cung cấp schema còn thiếu.

## 3. Chọn đúng Jackson factory cho bytes

Với JSON:

```java
ObjectMapper jsonMapper = new ObjectMapper();
```

Với CBOR:

```java
import com.fasterxml.jackson.dataformat.cbor.CBORFactory;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());
```

Với Smile:

```java
import com.fasterxml.jackson.dataformat.smile.SmileFactory;

ObjectMapper smileMapper = new ObjectMapper(new SmileFactory());
```

Tạo bytes:

```java
DeviceEvent event = new DeviceEvent("sensor-17", 42L, true);

byte[] cborBytes = cborMapper.writeValueAsBytes(event);
byte[] smileBytes = smileMapper.writeValueAsBytes(event);
byte[] jsonBytes = jsonMapper.writeValueAsBytes(event);
```

Đọc bytes bằng mapper tương ứng:

```java
DeviceEvent fromCbor = cborMapper.readValue(cborBytes, DeviceEvent.class);
DeviceEvent fromSmile = smileMapper.readValue(smileBytes, DeviceEvent.class);
DeviceEvent fromJson = jsonMapper.readValue(jsonBytes, DeviceEvent.class);
```

Không làm như sau:

```java
// Sai: bytes CBOR không phải JSON text.
String text = new String(cborBytes, StandardCharsets.UTF_8);
DeviceEvent event = jsonMapper.readValue(text, DeviceEvent.class);
```

Chuyển bytes nhị phân sang String bằng UTF-8 có thể tạo ký tự rác, làm mất byte hoặc vô tình tạo chuỗi có vẻ hợp lệ nhưng không còn giữ nguyên payload. Dùng `byte[]`, `InputStream` hoặc `ByteBuffer` theo API transport; chỉ giải mã thành String khi payload thực sự là text với charset đã biết.

## 4. Cấu hình mapper theo media type đã khai báo

Phía nhận cần ánh xạ media type sang parser phù hợp. Có thể tạo registry cố định:

```java
public final class WireMappers {
    public static final String JSON = "application/json";
    public static final String CBOR = "application/cbor";
    public static final String SMILE = "application/x-jackson-smile";

    private final Map<String, ObjectMapper> readers;

    public WireMappers() {
        Map<String, ObjectMapper> configured = new HashMap<>();
        configured.put(JSON, new ObjectMapper());
        configured.put(CBOR, new ObjectMapper(new CBORFactory()));
        configured.put(SMILE, new ObjectMapper(new SmileFactory()));
        this.readers = Map.copyOf(configured);
    }

    public ObjectMapper readerFor(String normalizedMediaType) {
        ObjectMapper mapper = readers.get(normalizedMediaType);
        if (mapper == null) {
            throw new UnsupportedPayloadFormatException(normalizedMediaType);
        }
        return mapper;
    }
}
```

Trong code production, parse media type bằng thư viện/framework HTTP thay vì tự cắt chuỗi header. Header có thể có parameters như `charset` hoặc `version`; so sánh type/subtype sau khi chuẩn hóa và áp dụng policy rõ ràng cho parameters.

Ví dụ xử lý request:

```java
MediaType mediaType = MediaType.parseMediaType(contentTypeHeader);
String key = mediaType.getType() + "/" + mediaType.getSubtype();

ObjectMapper mapper = wireMappers.readerFor(key);
DeviceEvent event = mapper.readValue(requestBodyBytes, DeviceEvent.class);
```

Đoạn ví dụ dùng `org.springframework.http.MediaType`; nếu không dùng Spring, hãy dùng parser media type của framework HTTP đang dùng. Không lấy nguyên header chưa chuẩn hóa làm key nếu có parameters hoặc khác biệt chữ hoa/thường.

### 4.1. Registry phải là allowlist

Không nhận tên class/factory từ header rồi khởi tạo bằng reflection. Ví dụ không an toàn:

```java
String className = request.getHeader("X-Mapper-Class");
Class<?> factoryClass = Class.forName(className);
```

Thay vào đó, chỉ cho phép một tập media type cố định được server cấu hình. Header chỉ chọn một entry trong registry; nó không được phép cài plugin, nạp class hoặc thay đổi mapper options.

### 4.2. Không đổi cấu hình mapper theo từng request

`ObjectMapper` nên được cấu hình hoàn tất trước khi dùng đồng thời. Tạo một mapper cho JSON, một mapper cho CBOR và một mapper cho Smile rồi tái sử dụng. Không bật/tắt default typing, thay module hoặc sửa subtype registry theo media type do client gửi.

Nếu hai endpoint có policy khác nhau, tạo mapper/reader được cấu hình riêng cho từng use case. Không dùng một mapper đang phục vụ request rồi thay factory giữa các lần gọi.

## 5. HTTP `Content-Type` mô tả định dạng body gửi lên

Khi client gửi request có body, `Content-Type` mô tả media type của body đó:

```http
POST /events HTTP/1.1
Host: api.example.test
Content-Type: application/cbor
Content-Length: 84

<binary CBOR bytes>
```

Server đọc header, xác định media type được hỗ trợ, chọn mapper tương ứng rồi deserialize bytes. Nếu body là Smile mà header khai báo CBOR, server sẽ chọn sai parser và thường báo lỗi mapping/parse.

`Content-Type` không phải lời khẳng định đáng tin rằng bytes thực sự đúng format. Nó là metadata do bên gửi khai báo. Server vẫn cần parse và từ chối bytes không hợp lệ theo parser được chọn.

### 5.1. Thiếu hoặc không hỗ trợ `Content-Type`

Với endpoint có nhiều format, nên yêu cầu `Content-Type` rõ ràng. Nếu header thiếu hoặc không được hỗ trợ, trả lỗi theo HTTP contract thay vì đoán từ body.

HTTP status thường dùng:

- `415 Unsupported Media Type`: server không hỗ trợ media type của request body.
- `400 Bad Request`: media type được hỗ trợ nhưng body malformed hoặc không ánh xạ được.

Nếu API có quy ước mặc định khi thiếu header, tài liệu phải nói rõ, ví dụ “thiếu Content-Type được xem là JSON”. Không tự suy đoán khác nhau giữa endpoint.

### 5.2. Không dùng file extension làm nguồn chân lý

Tên file `event.cbor` là gợi ý cho người dùng, không phải bằng chứng bytes thực sự là CBOR. File có thể bị đổi tên, tải sai hoặc được tạo bởi một phiên bản khác. Hãy dùng metadata upload (media type đã được chấp nhận), parser đúng và schema/version phù hợp; file extension chỉ hỗ trợ trải nghiệm người dùng.

## 6. HTTP `Accept` mô tả định dạng response client muốn nhận

`Accept` là header thương lượng response. Nó không mô tả định dạng request body.

Ví dụ client gửi JSON nhưng muốn nhận CBOR:

```http
POST /events HTTP/1.1
Content-Type: application/json
Accept: application/cbor

{"deviceId":"sensor-17","sequence":42,"active":true}
```

Server đọc request bằng JSON mapper, xử lý event, sau đó serialize response bằng CBOR mapper và trả:

```http
HTTP/1.1 200 OK
Content-Type: application/cbor

<binary CBOR bytes>
```

Hai header có nhiệm vụ khác nhau:

| Header | Câu hỏi |
|---|---|
| `Content-Type` | Body tôi vừa gửi lên được mã hóa theo format nào? |
| `Accept` | Response tôi muốn nhận có thể dùng format nào? |
| Response `Content-Type` | Server thực tế đã trả body theo format nào? |

Nếu server không thể tạo bất kỳ representation nào trong `Accept`, HTTP thường dùng `406 Not Acceptable`. Nếu có nhiều representation, server chọn theo q-value, thứ tự ưu tiên và policy của API.

### 6.1. Client chấp nhận nhiều format

Ví dụ:

```http
Accept: application/cbor, application/json;q=0.8
```

Client ưu tiên CBOR, nhưng vẫn chấp nhận JSON với mức ưu tiên thấp hơn. Server có thể chọn JSON nếu CBOR không được hỗ trợ hoặc policy không cho phép.

Khi response thay đổi theo `Accept`, cache trung gian cần biết representation phụ thuộc header này. Với HTTP cache, server thường cần gửi `Vary: Accept` khi thích hợp để tránh dùng response JSON cho request đã thương lượng CBOR.

### 6.2. Không trả sai `Content-Type`

Nếu server serialize bằng `CBORFactory`, response phải khai báo media type CBOR đã thỏa thuận. Không trả `Content-Type: application/json` chỉ vì DTO là object Java hoặc vì endpoint trước đó dùng JSON.

Client thường chọn parser dựa trên response header. Header sai có thể làm client cố parse binary bytes như text JSON và báo lỗi ở nơi khó chẩn đoán.

## 7. Ví dụ Spring MVC với `consumes` và `produces`

Trong Spring MVC, mapping có thể khai báo media type được nhận và media type được trả:

```java
@PostMapping(
        path = "/events",
        consumes = "application/cbor",
        produces = "application/cbor"
)
public EventResponse receive(@RequestBody DeviceEvent event) {
    return eventService.handle(event);
}
```

`consumes` ràng buộc media type của request; `produces` mô tả representation response endpoint có thể cung cấp. Tuy nhiên, annotation không tự cài đặt CBOR converter. Ứng dụng phải đăng ký HTTP message converter dùng `CBORFactory`/CBOR mapper tương ứng và converter phải hỗ trợ media type đã khai báo.

Nếu cần cùng endpoint hỗ trợ JSON và CBOR, đăng ký converter cho cả hai và kiểm tra content negotiation:

```java
@PostMapping(
        path = "/events",
        consumes = {"application/json", "application/cbor"},
        produces = {"application/json", "application/cbor"}
)
public EventResponse receive(@RequestBody DeviceEvent event) {
    return eventService.handle(event);
}
```

Framework chọn converter dựa trên request `Content-Type` và response `Accept`. Hãy xác nhận converter order và supported media types; không giả định converter JSON mặc định sẽ tự nhận CBOR.

Với ứng dụng không dùng Spring, nguyên tắc tương tự áp dụng ở JAX-RS, servlet filter hoặc HTTP handler: kiểm tra media type, chọn reader/writer đã cấu hình và trả đúng response header.

## 8. Ví dụ client gửi CBOR và đọc response CBOR

Phía Java client:

```java
ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());

byte[] body = cborMapper.writeValueAsBytes(
        new DeviceEvent("sensor-17", 42L, true));

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.test/events"))
        .header("Content-Type", "application/cbor")
        .header("Accept", "application/cbor")
        .POST(HttpRequest.BodyPublishers.ofByteArray(body))
        .build();
```

Khi nhận response:

```java
HttpResponse<byte[]> response = httpClient.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

if (response.statusCode() / 100 != 2) {
    throw new RemoteApiException(response.statusCode());
}

String responseContentType = response.headers()
        .firstValue("Content-Type")
        .orElseThrow(() -> new IllegalStateException("Missing Content-Type"));

MediaType responseType = MediaType.parseMediaType(responseContentType);
if (!responseType.isCompatibleWith(MediaType.parseMediaType("application/cbor"))) {
    throw new IllegalStateException("Unexpected response media type: " + responseType);
}

EventResponse result = cborMapper.readValue(
        response.body(), EventResponse.class);
```

Ví dụ này giả định client chỉ chấp nhận CBOR response. Nếu client gửi nhiều lựa chọn trong `Accept`, cần chọn mapper dựa trên response `Content-Type` thực tế, không chỉ dựa vào format đã ưu tiên trong request.

Trong code production, kiểm tra status code, content type, content encoding, body size và timeout trước khi deserialize. Không đọc một response body không giới hạn vào `byte[]` nếu server từ xa có thể trả payload rất lớn.

## 9. Content-Encoding và nén binary payload

Một binary format có thể được nén trước khi truyền:

```http
Content-Type: application/cbor
Content-Encoding: gzip
```

Thứ tự xử lý logic:

```text
HTTP body bytes
      |
      v
Giải mã Content-Encoding (gzip)
      |
      v
CBOR bytes
      |
      v
CBORFactory / CBOR mapper
      |
      v
Java object
```

Không đưa trực tiếp gzip bytes vào `CBORFactory`; trước hết phải giải nén theo content encoding. Ngược lại, không khai báo `Content-Encoding: gzip` nếu bytes không được nén.

Khi hỗ trợ compression, cần giới hạn cả:

- Kích thước compressed bytes nhận từ mạng.
- Kích thước decompressed bytes sau giải nén.
- Tỷ lệ nén và thời gian giải nén.
- Số request được giải nén đồng thời.

Nếu chỉ giới hạn compressed size, một payload có tỷ lệ nén rất cao vẫn có thể bung ra lượng dữ liệu lớn. Đây là lý do cần giới hạn sau giải nén trước khi parse.

## 10. Binary payload không có charset

Với JSON text, UTF-8 là encoding phổ biến và được quy định trong JSON interchange hiện đại. Với CBOR/Smile/BSON/Avro, bytes không phải văn bản UTF-8 thuần.

Không làm:

```java
String payload = new String(bytes, StandardCharsets.UTF_8);
```

để “đọc thử” một CBOR document. Việc chuyển đổi có thể làm hỏng byte sequence và tạo ký tự thay thế.

Hãy truyền bytes trực tiếp:

```java
DeviceEvent event = cborMapper.readValue(bytes, DeviceEvent.class);
```

Nếu một hệ thống chỉ cho phép vận chuyển text, có thể đóng gói binary bytes dưới dạng Base64 trong JSON:

```json
{
  "format": "cbor",
  "payloadBase64": "..."
}
```

Khi đó outer message là JSON (`Content-Type: application/json`); field `payloadBase64` là chuỗi Base64 chứa binary payload. Receiver phải decode Base64, kiểm tra size và chọn parser theo một format ID allowlist. Không khai báo outer body là `application/cbor` khi nó thực tế là JSON chứa Base64.

## 11. BSON và các định dạng document binary

BSON là binary representation cho document có cấu trúc tương tự JSON nhưng có kiểu dữ liệu và encoding riêng. Jackson có `jackson-dataformat-bson` với `BsonFactory`.

Ví dụ khởi tạo mapper:

```java
import com.fasterxml.jackson.dataformat.bson.BsonFactory;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper bsonMapper = new ObjectMapper(new BsonFactory());
byte[] bson = bsonMapper.writeValueAsBytes(event);
DeviceEvent restored = bsonMapper.readValue(bson, DeviceEvent.class);
```

Khi truyền BSON, hai bên cần thống nhất media type, framing và schema/model. BSON có thể chứa kiểu dữ liệu không tương đương một-một với JSON scalar thông thường. Không giả định mọi BSON document có thể được thay thế bằng JSON mà không mất semantics.

Tên media type `application/bson` được dùng trong một số hệ thống; hãy kiểm tra giao thức/SDK của hệ thống đích thay vì áp dụng tùy tiện. Nếu media type không được chuẩn hóa trong hợp đồng nội bộ, công bố vendor media type và version rõ ràng.

## 12. Avro cần schema tương ứng

Avro là binary serialization format thường được dùng trong data pipeline và event streaming. Khác với một số format có cấu trúc tự mô tả hơn, Avro binary data thường cần writer schema để giải mã đúng.

Với Jackson Avro module, ứng dụng có thể dùng `AvroMapper`/schema API tương ứng. Ví dụ khái quát:

```java
AvroMapper avroMapper = new AvroMapper();
AvroSchema schema = avroMapper.schemaFor(DeviceEvent.class);

byte[] bytes = avroMapper.writer(schema).writeValueAsBytes(event);
DeviceEvent restored = avroMapper.readerFor(DeviceEvent.class)
        .with(schema)
        .readValue(bytes);
```

API cụ thể có thể khác theo version Jackson Avro; hãy kiểm tra Javadoc của module đang dùng. Điểm quan trọng là schema dùng để ghi phải có thể được tìm thấy khi đọc. Chỉ khai báo `Content-Type` là `application/avro` không đủ nếu consumer không biết writer schema.

Trong message broker, Avro thường đi kèm schema registry hoặc schema ID/version trong header/envelope. Consumer dùng schema ID để lấy writer schema, sau đó deserialize và có thể áp dụng reader schema để resolve evolution.

Không gán schema ID do payload không tin cậy cung cấp vào class/schema loader tùy ý. Schema registry access phải được kiểm soát và chỉ cho phép subject/version hợp lệ.

## 13. Định dạng nhị phân có thể cần schema version hoặc framing

Media type trả lời câu hỏi “format là gì?”, nhưng chưa chắc trả lời đủ:

- Schema nào được dùng?
- Version payload nào được ghi?
- Một body chứa một record hay nhiều record?
- Có length prefix, checksum hoặc message envelope không?
- Có compression không?
- Có encryption/signature ở tầng application không?

Ví dụ message envelope:

```text
Transport headers:
  content-type: application/avro
  content-encoding: gzip
  schema-id: 1042
  schema-version: 3

Body:
  gzip(Avro binary bytes encoded with writer schema 1042)
```

Với CBOR/Smile cũng có thể cần `schemaVersion` nếu hai bên thay đổi field semantics theo thời gian. Đừng dựa vào tên class Java hoặc thứ tự field để suy ra schema version.

## 14. Message broker: truyền format cùng message

Trong message broker, body thường chỉ là bytes. Consumer cần metadata để chọn parser. Tùy broker, metadata có thể nằm ở property hoặc header:

```text
Message:
  contentType = application/cbor
  schemaVersion = 2
  correlationId = ...
  body = <CBOR bytes>
```

Với Kafka, có thể dùng record headers để mang content type/schema metadata; với AMQP, message properties có trường content type; các nền tảng khác có envelope riêng. Tên header cụ thể cần được thống nhất trong hệ thống.

Producer phải đặt metadata khớp với serializer đã tạo body. Consumer phải kiểm tra metadata trước khi deserialize. Nếu thiếu content type, hãy áp dụng policy rõ ràng: từ chối, route sang legacy handler đã biết hoặc dùng version mặc định được tài liệu hóa. Không đoán bằng cách thử tất cả parser trên mọi message.

### 14.1. Đừng chỉ dựa vào topic name

Topic `events-cbor` có thể là convention hữu ích, nhưng consumer vẫn nên xác nhận message metadata hoặc contract của topic. Một producer cấu hình sai có thể gửi JSON vào topic CBOR.

Topic name, schema registry subject và content type nên nhất quán. Nếu topic chỉ nhận một format, ghi rõ điều đó trong schema/contract và giám sát message sai format.

### 14.2. Dead-letter và lỗi format

Nếu consumer không parse được bytes:

- Không retry vô hạn một payload malformed không thể sửa.
- Ghi nhận content type, schema ID/version và correlation ID.
- Đưa message vào dead-letter/quarantine theo policy.
- Không log raw binary bytes hoặc secret.
- Phân biệt lỗi format, lỗi schema và lỗi business processing.

Retry phù hợp với lỗi tạm thời như schema registry unavailable; payload sai format thường cần quarantine hoặc sửa producer.

## 15. File và object storage: lưu metadata cùng bytes

Khi lưu binary payload thành file hoặc object storage, giữ media type và schema metadata cùng object:

```text
Object key: events/2026/11/12/evt-100.cbor
Content-Type: application/cbor
Content-Encoding: (none)
Metadata:
  schema-version: 2
  producer: telemetry-service
Body: <CBOR bytes>
```

Nếu chỉ lưu bytes mà không lưu format/version, consumer sau này có thể không biết parser hoặc schema cần dùng. File extension có thể hỗ trợ con người, nhưng metadata object hoặc manifest mới là nguồn định dạng chính.

Với file import từ người dùng, không tin hoàn toàn `Content-Type` do browser gửi. Xác minh bằng parser tương ứng, giới hạn bytes và từ chối mismatch. Nếu ứng dụng chấp nhận nhiều format, người dùng phải chọn format rõ ràng hoặc hệ thống cần một manifest đã xác thực.

## 16. Có nên tự động phát hiện format từ bytes?

Jackson có các cơ chế format detection như `DataFormatDetector` cho một số factory có khả năng nhận diện. Chúng có thể hữu ích khi xử lý kho file legacy đã biết tập format ứng viên.

Tuy nhiên, auto-detection không nên là chính sách mặc định cho API công khai:

- Không phải mọi format đều có magic header duy nhất hoặc đủ để phân biệt trong mọi trường hợp.
- Prefix bytes có thể bị cắt hoặc payload bị hỏng.
- Một số format có thể có bytes đầu trùng nhau hoặc parser detector chỉ nhận diện theo heuristic.
- Thử nhiều parser làm tăng CPU và tạo hành vi mơ hồ.
- Detection không thay thế authentication, schema validation hoặc resource limits.

Nếu buộc phải hỗ trợ legacy auto-detection, chỉ thử một danh sách factory cố định, giới hạn số bytes được xem xét, giới hạn tài nguyên parser và từ chối khi kết quả không rõ ràng. Sau khi phát hiện, vẫn kiểm tra schema/contract và không dùng bytes để quyết định class tùy ý.

Với giao thức mới, hãy gửi media type hoặc format ID tường minh.

## 17. Trường hợp media type và bytes không khớp

Ví dụ server nhận:

```http
Content-Type: application/json
```

nhưng body lại là CBOR bytes. Server chọn JSON mapper theo header và parse thất bại. Không nên tự động fallback sang CBOR sau khi JSON parser lỗi, vì điều đó tạo ambiguity và có thể che giấu lỗi producer.

Một số tình huống và phản ứng:

| Metadata | Bytes thực tế | Phản ứng |
|---|---|---|
| JSON | JSON hợp lệ | Đọc bằng JSON mapper |
| CBOR | CBOR hợp lệ | Đọc bằng CBOR mapper |
| Smile | CBOR | Từ chối mismatch |
| JSON | CBOR | Từ chối mismatch; yêu cầu producer sửa header |
| Không có type | Bất kỳ binary | Từ chối hoặc route theo contract legacy đã biết |
| Avro + schema ID hợp lệ | Avro bytes đúng schema | Lấy writer schema rồi deserialize |
| Avro + schema ID không tồn tại | Avro bytes | Báo schema metadata error; không đoán schema |

Không nên “thử JSON, nếu lỗi thử CBOR, nếu lỗi thử Smile” trên mọi request. Một payload không rõ format cần được coi là không hợp lệ theo hợp đồng.

## 18. Versioning và tương thích giữa producer/consumer

Định dạng binary không tự bảo đảm tương thích schema. Ví dụ producer thêm field bắt buộc, đổi kiểu `sequence` từ integer sang string hoặc thay semantics của `active`; consumer cũ có thể không đọc hoặc đọc sai.

Hãy quản lý:

- Format/media type.
- Schema version hoặc schema ID.
- Quy tắc thêm/bỏ/đổi field.
- Default value và nullable semantics.
- Enum evolution.
- Compatibility policy giữa writer và reader schema.
- Thời gian hỗ trợ payload version cũ.

Với Avro, dùng writer schema và reader schema để thực hiện schema resolution theo quy tắc Avro. Với CBOR/Smile, có thể dùng envelope hoặc header chứa schema version và DTO versioned. Với BSON, thống nhất kiểu dữ liệu và semantics với consumer.

Không dùng Java class name làm version. Refactor package không nên làm thay đổi wire contract.

## 19. Không dùng một mapper cho mọi format

Một mapper được xây dựng từ JSON factory sẽ tạo JSON parser/generator. Đổi tên biến thành `cborMapper` không làm nó đọc được CBOR:

```java
ObjectMapper mapper = new ObjectMapper();
// mapper này vẫn dùng JSON factory.
```

Mapper cần được tạo bằng factory đúng:

```java
ObjectMapper jsonMapper = new ObjectMapper();
ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());
ObjectMapper smileMapper = new ObjectMapper(new SmileFactory());
```

Có thể chia sẻ cấu hình chung bằng helper hoặc module, nhưng mỗi format cần factory tương ứng. Kiểm tra custom serializer/deserializer, naming, subtype và feature có hoạt động đúng trên từng mapper.

Đừng giả định mọi annotation hoặc module hoạt động hoàn toàn giống nhau trên mọi dataformat. Binary format có thể có hạn chế về type, root value, object ID hoặc native type support tùy module/version.

## 20. Dùng `ObjectReader` và `ObjectWriter` theo format/type

Sau khi tạo mapper đúng format, có thể tạo reader/writer bất biến cho target type:

```java
ObjectReader cborEventReader = cborMapper.readerFor(DeviceEvent.class);
ObjectWriter cborEventWriter = cborMapper.writerFor(DeviceEvent.class);

byte[] bytes = cborEventWriter.writeValueAsBytes(event);
DeviceEvent restored = cborEventReader.readValue(bytes);
```

Điều này giúp đóng gói target type và một số feature theo use case. `ObjectReader`/`ObjectWriter` không đổi dataformat factory của mapper; reader được tạo từ JSON mapper vẫn là JSON reader.

Nếu một endpoint cần strict trailing data hoặc view riêng, cấu hình trên reader/writer tương ứng thay vì sửa global mapper sau khi đã dùng.

## 21. Kiểm tra framing và trailing bytes

Một HTTP body thông thường thường đại diện cho một document hoặc một message theo contract. Một số binary format/transport có thể hỗ trợ sequence hoặc framing nhiều record.

Hãy xác định:

- Một body chứa đúng một object hay một sequence?
- Có length prefix hoặc message boundary không?
- Có schema ID/header prefix không?
- Có checksum hoặc signature không?
- Bytes thừa sau object đầu tiên có bị từ chối không?

Với contract một value, bật `FAIL_ON_TRAILING_TOKENS` nếu parser/format hỗ trợ và test bytes thừa. Với sequence, dùng streaming reader/parser và giới hạn record count. Không tự cắt payload theo một offset giả định nếu framing không được quy định.

## 22. Charset, BOM và định dạng văn bản

Một số định dạng Jackson là văn bản (JSON, XML, YAML); một số là nhị phân. Với text format, thống nhất encoding, thường là UTF-8 cho HTTP JSON. Với binary format, không áp dụng charset như cách giải mã text.

Nếu payload là JSON UTF-8, dùng `application/json` và bytes UTF-8. Nếu payload là CBOR, dùng media type CBOR và bytes CBOR. Không dùng `application/octet-stream` cho mọi loại nếu server cần biết parser nào để chọn; chỉ dùng generic binary khi giao thức có một envelope hoặc metadata khác xác định format.

Nếu nhận `application/octet-stream`, cần một contract riêng như header `X-Payload-Format` đã allowlist, manifest đã xác thực hoặc container format tự mô tả. Không lấy tên class/factory từ metadata tùy ý.

## 23. Xử lý media type parameters

Media type có thể có parameters:

```http
Content-Type: application/json; charset=utf-8
```

Hoặc một giao thức nội bộ có thể quy định:

```http
Content-Type: application/vnd.example.event+cbor; version=2
```

Khi chọn parser:

1. Parse header thành media type bằng thư viện chuẩn.
2. Chuẩn hóa type/subtype theo quy tắc media type.
3. Kiểm tra parameters được hỗ trợ.
4. Chọn mapper từ allowlist cố định.
5. Kiểm tra schema/version metadata riêng nếu cần.

Không loại bỏ mọi parameters một cách mù quáng. `charset` có thể không liên quan với binary format, nhưng `version` hoặc `profile` có thể là một phần của hợp đồng. Tài liệu API cần nói rõ parameters nào được phép và ý nghĩa của chúng.

## 24. Đặt media type riêng cho contract nội bộ

Nếu dùng Smile hoặc một binary profile riêng, có thể công bố vendor media type:

```http
Content-Type: application/vnd.example.device-event+smile; version=1
Accept: application/vnd.example.device-event+smile; version=1
```

Đây là ví dụ media type do tổ chức định nghĩa, không phải tên mặc định bắt buộc của Jackson. Cần đăng ký/ghi tài liệu nội bộ, nêu rõ:

- Bytes dùng Smile/CBOR/BSON hay một profile cụ thể.
- Jackson module/version tương thích.
- Schema version.
- Compression/framing.
- Quy tắc tương thích và lỗi.

Vendor media type hữu ích khi body là một hợp đồng domain cụ thể, không chỉ là binary representation tổng quát. Không tạo media type mới cho mọi class Java nếu không có nhu cầu versioning thực sự.

## 25. Test hai đầu giao tiếp với bytes thật

Test tốt nhất là serialize bằng mapper producer, giữ nguyên bytes, rồi deserialize bằng mapper consumer độc lập. Không chỉ test cùng một mapper ở cả hai chiều nếu production có hai service/version khác nhau.

```java
@Test
void producerAndConsumerAgreeOnCborWireFormat() throws Exception {
    ObjectMapper producer = new ObjectMapper(new CBORFactory());
    ObjectMapper consumer = new ObjectMapper(new CBORFactory());

    DeviceEvent original = new DeviceEvent("sensor-17", 42L, true);
    byte[] wireBytes = producer.writeValueAsBytes(original);

    DeviceEvent restored = consumer.readValue(wireBytes, DeviceEvent.class);

    assertEquals(original, restored);
}
```

Test mismatch:

```java
@Test
void doesNotTreatCborBytesAsJson() throws Exception {
    ObjectMapper cbor = new ObjectMapper(new CBORFactory());
    ObjectMapper json = new ObjectMapper();

    byte[] bytes = cbor.writeValueAsBytes(
            new DeviceEvent("sensor-17", 42L, true));

    assertThrows(JsonProcessingException.class,
            () -> json.readValue(bytes, DeviceEvent.class));
}
```

Test này minh họa rằng mapper sai format không được dùng thay thế. Với một số byte sequence, parser sai có thể báo lỗi khác nhau; điều quan trọng là application chọn parser từ metadata và không fallback tùy tiện.

## 26. Test HTTP content negotiation

Integration test cần kiểm tra:

- Request `Content-Type` JSON được JSON converter đọc.
- Request `Content-Type` CBOR được CBOR converter đọc.
- Header media type không hỗ trợ trả 415.
- Body malformed theo format đã khai báo trả 400.
- `Accept` CBOR nhận response CBOR và header response đúng.
- `Accept` chỉ chứa format không hỗ trợ trả 406.
- Client gửi JSON body nhưng `Accept` CBOR vẫn được đọc request bằng JSON và trả response CBOR.
- Content-Encoding gzip được giải nén đúng trước khi parse, nếu endpoint hỗ trợ.

Không chỉ assert status code; hãy kiểm tra response `Content-Type` và parse response bytes bằng đúng mapper để xác nhận representation thực tế.

## 27. Test schema/version và metadata message broker

Với Avro hoặc message có schema ID, test cần kiểm tra:

- Producer ghi đúng content type.
- Schema ID/version được gắn cùng message.
- Consumer lấy đúng writer schema.
- Payload sai schema bị từ chối.
- Schema version không hỗ trợ được xử lý rõ ràng.
- Schema registry timeout được phân biệt với payload malformed.
- Message có metadata thiếu hoặc mâu thuẫn đi vào lỗi/quarantine đúng policy.

Với CBOR/Smile không dùng schema registry, vẫn nên test version envelope hoặc schema version header nếu model có evolution.

## 28. Quan sát và chẩn đoán lỗi format

Khi consumer không đọc được payload, log metadata hữu ích:

- Producer/service và topic/endpoint.
- Media type đã nhận.
- Content encoding.
- Schema ID/version nếu có.
- Payload byte length.
- Correlation/message ID.
- Loại parser/mapping exception và vị trí nếu có.

Tránh log toàn bộ binary bytes hoặc chuyển chúng thành chuỗi để debug. Nếu cần giữ payload để điều tra, lưu vào vùng quarantine có quyền truy cập, retention và mã hóa phù hợp.

Các metric có thể theo dõi:

- Số message theo media type.
- Tỷ lệ parse error theo producer/format/version.
- Số request bị từ chối do media type không hỗ trợ.
- Kích thước payload trung bình/p95/p99.
- Tỷ lệ compression và decompressed size.
- Schema lookup error và version không hỗ trợ.

Metric giúp phát hiện producer gửi nhầm format hoặc một client vẫn dùng schema cũ.

## 29. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| CBOR bytes không đọc được bằng JSON mapper | Parser/factory sai định dạng | Chọn mapper theo media type đã khai báo |
| Client báo lỗi ký tự UTF-8 khi đọc binary | Binary bytes bị chuyển thành String | Truyền `byte[]`/stream trực tiếp |
| Server parse sai request dù client serialize đúng | `Content-Type` không khớp body | Sửa header hoặc serializer producer |
| Response body là CBOR nhưng client cố parse JSON | Response `Content-Type` sai hoặc client bỏ qua header | Trả/đọc đúng response media type |
| Endpoint khai báo `consumes` CBOR nhưng vẫn lỗi converter | Chưa đăng ký CBOR HTTP message converter | Cấu hình converter với CBOR mapper |
| Gửi `Accept: application/cbor` nhưng response JSON | Server không thương lượng hoặc không hỗ trợ CBOR writer | Đăng ký converter và kiểm tra `produces`/Accept |
| Avro bytes không giải mã được | Thiếu hoặc sai writer schema/schema ID | Gắn schema metadata và resolve đúng schema |
| Payload gzip không đọc được | Đưa compressed bytes thẳng vào mapper | Giải nén theo `Content-Encoding` trước khi parse |
| Dùng file extension để chọn parser nhưng đọc sai | Tên file không phản ánh bytes | Dùng media type/manifest và validate parser |
| Auto-detection chọn nhầm format | Detection mơ hồ hoặc dữ liệu bị cắt | Ưu tiên metadata tường minh, giới hạn detector |
| Producer và consumer dùng format version khác | Không quản lý schema/version | Định nghĩa version và compatibility policy |
| Consumer thử nhiều parser đến khi có một parser thành công | Fallback che giấu mismatch | Allowlist theo media type và từ chối mismatch |

## 30. Quy trình thiết kế gửi/nhận binary payload

Khi xây dựng một API hoặc message contract có binary format, hãy thực hiện theo trình tự:

1. Chọn format dựa trên yêu cầu tương thích, schema, kích thước và hệ sinh thái consumer.
2. Chọn media type chuẩn hoặc vendor media type đã được tài liệu hóa.
3. Quy định schema ID/version, framing và compression nếu có.
4. Producer serialize bằng đúng Jackson factory/mapper.
5. Producer gắn `Content-Type` hoặc message metadata khớp với bytes.
6. Consumer kiểm tra metadata và chọn mapper từ allowlist cố định.
7. Consumer giải mã `Content-Encoding` trước khi parse nếu có.
8. Consumer đọc bytes bằng `byte[]`/stream, không chuyển binary sang String.
9. Consumer validate schema, type, resource limits và business rules.
10. Consumer từ chối media type không hỗ trợ, bytes malformed hoặc metadata mâu thuẫn.
11. Test cả chiều producer/consumer, mismatch, negotiation và schema evolution.
12. Theo dõi metric lỗi theo format/version và không log raw payload nhạy cảm.

## 31. Ghi nhớ

Định dạng nhị phân chỉ hoạt động đúng khi producer, transport metadata và consumer thống nhất. Jackson cần factory/mapper đúng format: JSON, CBOR, Smile, BSON hoặc Avro không thể được thay thế cho nhau chỉ bằng cách đổi tên biến mapper. Với HTTP, `Content-Type` mô tả request body, `Accept` mô tả response client muốn nhận và response `Content-Type` phải khớp bytes thực tế. Với broker/file, lưu content type cùng schema ID/version và framing cần thiết.

Hãy tách data format khỏi charset và compression; giữ binary payload ở dạng bytes/stream; chọn mapper từ registry allowlist; không để header hoặc payload khởi tạo class tùy ý; và từ chối mismatch thay vì thử parser ngẫu nhiên. Khi media type, schema/version và bytes được khai báo nhất quán, hai đầu có thể deserialize đúng nội dung và lỗi format sẽ dễ phát hiện, chẩn đoán hơn.
