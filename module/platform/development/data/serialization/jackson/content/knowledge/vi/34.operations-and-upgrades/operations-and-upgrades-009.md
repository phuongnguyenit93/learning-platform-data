# Triển khai có kiểm soát khi thay chính sách chuyển kiểu hoặc giới hạn

Thay đổi chính sách chuyển kiểu (coercion) hoặc giới hạn đọc của Jackson có thể làm thay đổi request nào được chấp nhận, request nào bị từ chối và lượng tài nguyên mà một payload có thể tiêu thụ. Một cấu hình tưởng như nhỏ, chẳng hạn từ chối chuỗi số gửi vào field Integer hoặc giảm giới hạn độ dài string, có thể ảnh hưởng nhiều client cùng lúc. Nếu thay đổi trực tiếp trên mapper dùng chung mà không kiểm kê contract và theo dõi traffic, lỗi chỉ xuất hiện sau khi triển khai production.

Triển khai an toàn cần coi cấu hình Jackson là một phần của API contract. Trước khi thay đổi, xác định mapper nào đang được dùng, endpoint nào chịu ảnh hưởng, dữ liệu thực tế có hình dạng ra sao và client nào còn dựa vào coercion cũ. Sau đó chuẩn bị test tương thích, đo tỷ lệ input cũ, triển khai theo từng nhóm traffic và có cách quay lại cấu hình trước nếu error rate hoặc latency vượt ngưỡng.

Với giới hạn parser, cần kiểm soát nhiều tầng: kích thước body ở HTTP/gateway, giới hạn token và nesting trong Jackson, giới hạn số phần tử và invariant ở DTO/domain. Không có một giới hạn đơn lẻ nào bảo vệ toàn bộ pipeline. Cấu hình phải được quản lý tập trung, bất biến sau khi mapper bắt đầu được dùng và có version để có thể so sánh giữa các lần triển khai.

## 1. Vì sao thay đổi coercion hoặc parser limit có rủi ro?

Jackson chuyển token JSON sang kiểu Java theo quy tắc coercion. Một ứng dụng có thể đang chấp nhận input linh hoạt như:

```json
{
  "quantity": "12",
  "enabled": "true",
  "price": 19.0
}
```

Nếu chính sách mới yêu cầu quantity phải là JSON number, enabled phải là JSON boolean và price phải là integer/decimal đúng kiểu, một số request trước đây thành công có thể bắt đầu thất bại. Đó có thể là thay đổi đúng về contract, nhưng cần biết client nào đang gửi dữ liệu cũ.

Tương tự, giảm giới hạn đọc từ một giá trị rất lớn xuống thấp hơn có thể chặn payload bất thường, nhưng cũng có thể từ chối một request hợp lệ chứa mô tả dài, danh sách lớn hoặc JSON lồng sâu. Tăng giới hạn cũng có rủi ro: payload lớn hơn có thể làm tăng allocation, thời gian parse và áp lực GC.

Các tác động thường gặp:

- Request trước đây được coercion thành công nay trả lỗi 400.
- Request có string/number/array vượt giới hạn nay bị từ chối.
- Client cũ và mới gửi cùng một field theo hai kiểu khác nhau.
- Một mapper dùng chung thay đổi hành vi của nhiều endpoint không liên quan.
- Parser từ chối request trước khi Bean Validation có thể kiểm tra DTO.
- Error rate, retry rate hoặc queue backlog tăng sau rollout.
- Giới hạn mới ảnh hưởng log ingestion, event consumer hoặc batch job dù thay đổi ban đầu chỉ nhắm HTTP API.

Vì vậy, không triển khai thay đổi parser policy như một refactor nội bộ không ảnh hưởng tương thích. Đây là một thay đổi hành vi có thể quan sát được từ phía producer/consumer.

## 2. Xác định chính sách hiện tại trước khi sửa

Trước khi chỉnh mapper, cần biết chính xác cấu hình đang chạy. Jackson có nhiều nguồn cấu hình:

- ObjectMapper được tạo trực tiếp trong code.
- Spring Boot auto-configuration và application properties.
- Jackson2ObjectMapperBuilder customizer.
- Module hoặc mix-in được đăng ký.
- ObjectReader/ObjectWriter có feature riêng.
- JsonFactory có StreamReadConstraints và parser feature.
- Annotation trên DTO như JsonFormat, JsonSetter, JsonDeserialize.
- Custom deserializer/coercion config theo logical type hoặc class.

Không chỉ tìm new ObjectMapper. Trong Spring, controller có thể nhận mapper được cấu hình qua message converter; service khác có thể tự tạo mapper riêng; consumer Kafka có thể dùng mapper độc lập.

### 2.1. Lập danh sách mapper và boundary

Tạo inventory cho từng đường đọc dữ liệu:

| Boundary | Mapper/factory | DTO hoặc schema | Consumer | Cấu hình đáng chú ý |
|---|---|---|---|---|
| REST public API | Spring MVC converter | Request DTO | Mobile/web/partner | Coercion, unknown fields, body limit |
| Internal REST | Mapper nội bộ | Command DTO | Service khác | Strict types, version |
| Kafka consumer | JSON/CBOR mapper | Event DTO | Producer service | Schema/version, payload limit |
| Batch import | Mapper riêng | Import record | File producer | Document size, collection count |
| Admin endpoint | Mapper/API converter | Admin DTO | Operator | Strict parsing, audit |

Đừng giả định mọi boundary cần cùng một mức strictness. Public API có thể cần compatibility trong giai đoạn chuyển đổi; file import không tin cậy có thể cần giới hạn nhỏ hơn; event consumer cần hỗ trợ nhiều schema version.

### 2.2. Xác nhận mapper thực sự được Spring sử dụng

Trong Spring MVC, request body được đọc bởi HttpMessageConverter phù hợp với Content-Type. Có thể có nhiều converter và nhiều ObjectMapper. Nếu endpoint nhận JSON, kiểm tra converter JSON được đăng ký và mapper gắn với converter đó.

Một cấu hình mapper riêng được tạo trong service không nhất thiết ảnh hưởng @RequestBody. Ngược lại, thay mapper toàn cục có thể ảnh hưởng cả endpoint không nằm trong phạm vi dự định.

Trong integration test, kiểm tra qua MockMvc hoặc WebTestClient phù hợp với stack. Unit test tạo mapper mới chỉ chứng minh mapper đó, không chứng minh mapper production.

## 3. Coercion trong Jackson

Coercion là việc chuyển một JSON token sang kiểu Java khác với token type tự nhiên. Ví dụ, token string "42" được chuyển thành Integer 42, hoặc token number 1 được chuyển thành Boolean theo một số cấu hình.

Coercion có thể hữu ích với dữ liệu legacy, nhưng nó làm contract kém rõ ràng nếu producer gửi kiểu không nhất quán. Khi hệ thống có nhiều client, cần quyết định coercion nào được chấp nhận và coercion nào phải bị từ chối.

### 3.1. Các token shape cần quan tâm

| JSON token | Ví dụ | Kiểu đích có thể bị ảnh hưởng |
|---|---|---|
| String | "12" | Integer, decimal, boolean, enum, date |
| Integer | 12 | String, enum ordinal, boolean theo cấu hình |
| Float | 12.5 | Integer nếu float-to-int được cho phép |
| Boolean | true | Một số scalar type nếu coercion được cho phép |
| Null | null | Reference, primitive hoặc policy setter |
| Array | [12] | Single value as array / unwrap single value |
| Object | {} | POJO, map hoặc empty-object coercion |
| Empty string | "" | Null/empty/default tùy target và config |

Không nên bật hoặc tắt coercion chung chỉ vì một ví dụ. Xác định logical type và input shape cụ thể cần kiểm soát.

### 3.2. Tắt một số coercion phổ biến

Jackson cung cấp các feature có phạm vi cụ thể. Ví dụ, nếu integer field không được nhận floating-point token:

```java
ObjectMapper mapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();
```

Nếu enum không được nhận numeric ordinal:

```java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
    .build();
```

Nếu API không muốn một scalar tự động được bọc thành array, giữ ACCEPT_SINGLE_VALUE_AS_ARRAY ở trạng thái tắt. Nếu không muốn array một phần tử được unwrap thành scalar, giữ UNWRAP_SINGLE_VALUE_ARRAYS ở trạng thái tắt.

Các feature này có default và tương tác phụ thuộc version/cấu hình. Hãy kiểm tra version Jackson đang chạy và test behavior bằng input thật. Không dựa vào trí nhớ về default của một version khác.

### 3.3. CoercionConfig theo logical type

Jackson 2.x có API CoercionConfig để định nghĩa hành vi theo logical type và input shape. Ví dụ minh họa từ chối string cho integer:

```java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Có thể đặt policy khác cho empty string:

```java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
```

Các action phổ biến gồm:

| CoercionAction | Ý nghĩa |
|---|---|
| Fail | Từ chối input shape đó |
| TryConvert | Thử chuyển đổi theo deserializer |
| AsNull | Diễn giải thành null |
| AsEmpty | Dùng empty value của kiểu đích |

CoercionInputShape có các dạng như String, Integer, Float, Boolean, Array, Object, Binary, EmptyString, EmptyArray và EmptyObject. Danh sách cụ thể phụ thuộc Jackson version.

CoercionConfig giúp kiểm soát policy chi tiết hơn một feature toàn cục. Tuy nhiên, cấu hình theo logical type có thể ảnh hưởng nhiều class. Nếu chỉ một property cần rule riêng, cân nhắc custom deserializer hoặc DTO type riêng để tránh thay đổi các boundary không liên quan.

### 3.4. CoercionConfig theo class

Có thể cấu hình theo kiểu Java cụ thể:

```java
mapper.coercionConfigFor(Quantity.class)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Đây là hướng phù hợp khi một value object có contract chặt hơn các scalar khác. API cụ thể cần đối chiếu Jackson version và kiểu deserializer đang sử dụng.

Không dùng class-level coercion để thay thế validation domain. Coercion quyết định input representation nào có thể chuyển thành object; constructor/factory vẫn cần kiểm tra invariant của giá trị sau khi parse.

### 3.5. Empty string và null cần policy riêng

Chuỗi rỗng, whitespace-only và null là ba input khác nhau. Nếu API coi empty string là invalid nhưng cho phép null ở một số field, không nên dùng một cấu hình global làm chúng tương đương.

Ví dụ:

```java
public record UpdateProfileRequest(
    @NotBlank String displayName,
    String optionalNote
) {}
```

displayName có thể bị từ chối bởi @NotBlank sau khi binding; optionalNote có thể cho phép null hoặc chuỗi rỗng theo contract. Nếu bật coercion toàn cục biến empty string thành null, hai field có thể có behavior khác dự kiến.

Tách parsing policy và validation policy:

- Parsing: token nào chuyển được sang kiểu Java?
- Validation: giá trị Java sau binding có hợp lệ không?
- Domain: giá trị đó có hợp lệ trong trạng thái nghiệp vụ hiện tại không?

## 4. Kiểm soát coercion theo từng kiểu dữ liệu

### 4.1. Integer và decimal

Kiểm tra:

- "12" có được nhận thành 12 không?
- 12.0 có được nhận vào Integer không?
- 12.7 có bị từ chối hay bị cắt phần thập phân?
- Giá trị vượt range có gây lỗi rõ ràng không?
- Empty string và null có khác nhau không?

Với tiền, dùng BigDecimal và quy định scale/precision. Tránh nhận float rồi chuyển sang integer hoặc decimal theo coercion ngầm. Một thay đổi parser policy không thay thế @Digits, @DecimalMin, @DecimalMax hoặc domain validation.

### 4.2. Boolean

Một số hệ thống legacy gửi "true", "false", "1" hoặc "0" dưới dạng string. Nếu contract mới yêu cầu JSON boolean token, cần xác định rõ những dạng cũ còn được hỗ trợ trong giai đoạn chuyển đổi.

Không giả định mọi dạng string/number boolean đều được Jackson chấp nhận giống nhau. Viết test với từng token shape trên đúng mapper.

### 4.3. Enum

Nếu enum được đọc từ string, quyết định cách xử lý:

- Tên enum đúng.
- Tên không biết.
- Chuỗi rỗng.
- Null.
- Numeric ordinal.
- Case khác nhau.

Không dùng ordinal làm contract lâu dài vì thứ tự constant có thể thay đổi. Nếu cần tolerant handling cho enum mới, cân nhắc unknown sentinel hoặc custom deserializer có quy tắc rõ ràng. Test unknown value để không vô tình biến lỗi thành một trạng thái mặc định nguy hiểm.

### 4.4. Date/time

Thay đổi date coercion hoặc format có thể làm client cũ gửi timestamp number trong khi client mới gửi ISO-8601 string. Dùng Java Time module và JsonFormat/formatter rõ ràng. Xác định timezone, offset, precision và đơn vị epoch nếu nhận number.

Không triển khai thay đổi format ngày giờ cùng lúc với thay đổi coercion scalar nếu chưa có test riêng; nếu request fail, sẽ khó xác định nguyên nhân.

### 4.5. Array và collection

Các policy như ACCEPT_SINGLE_VALUE_AS_ARRAY có thể khiến:

```json
{"tags": "java"}
```

được chuyển thành list một phần tử, trong khi contract mong muốn:

```json
{"tags": ["java"]}
```

Nếu tắt coercion này, client gửi scalar sẽ bị từ chối. Kiểm tra cả array rỗng, array có null element, array quá nhiều phần tử và nested arrays.

### 4.6. Object và map

Empty object {} có thể tạo POJO với default values hoặc map rỗng. Một object token gửi vào scalar field thường là lỗi binding, nhưng custom deserializer có thể thay đổi hành vi. Test object rỗng, object lồng sâu, map có nhiều entry và key quá dài.

## 5. Giới hạn đọc của Jackson

Jackson Core cung cấp StreamReadConstraints để giới hạn một số đặc tính của input trước khi databinding tạo object. API này được giới thiệu trong Jackson Core 2.15; kiểm tra module version nếu ứng dụng dùng API cũ.

Các giới hạn thường cần xem xét:

- Maximum nesting depth.
- Maximum string length.
- Maximum number token length.

Một số version mới có thể bổ sung thêm loại constraint. Chỉ cấu hình các API có trong version dependency của ứng dụng.

### 5.1. Cấu hình StreamReadConstraints

Ví dụ:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(100)
    .maxStringLength(1_000_000)
    .maxNumberLength(100)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Các con số trên chỉ minh họa cách cấu hình, không phải giá trị khuyến nghị cho mọi ứng dụng. Chọn limit từ payload hợp lệ lớn nhất đã đo, cộng biên an toàn hợp lý, và đặt ngưỡng theo từng boundary nếu nhu cầu khác nhau.

Giới hạn string length tính theo cách Jackson Core định nghĩa cho token, không phải luôn đồng nhất với số byte HTTP hoặc số ký tự người dùng nhìn thấy. Unicode, encoding và compression khiến các con số này khác nhau.

### 5.2. Giới hạn document size ở transport

StreamReadConstraints không thay thế giới hạn kích thước HTTP request body. Cần đặt giới hạn ở:

- API gateway hoặc reverse proxy.
- Servlet container/server.
- Multipart/upload handler nếu có.
- Message broker hoặc consumer client.
- Application layer trước khi buffer toàn bộ body nếu tự đọc stream.

Giới hạn ở gateway giúp chặn sớm payload quá lớn trước khi nó tiêu thụ tài nguyên trong JVM. Nhưng vẫn cần limit trong application vì không phải mọi đường vào đều đi qua cùng gateway.

### 5.3. Giới hạn số phần tử collection

Một JSON array có thể chứa rất nhiều phần tử nhỏ mà từng string/number đều nằm trong limit:

```json
{"ids": [1, 2, 3, 4, 5]}
```

StreamReadConstraints không thay thế một giới hạn domain cụ thể về số phần tử. Dùng:

- Bean Validation như @Size(max = ...).
- Constructor/factory kiểm tra kích thước nếu invariant thuộc domain.
- Custom deserializer khi cần dừng đọc sớm trước khi tạo collection quá lớn.
- Giới hạn request body để đặt trần tổng thể.

Ví dụ:

```java
public record BulkLookupRequest(
    @NotEmpty
    @Size(max = 500)
    List<@NotNull Long> ids
) {}
```

Bean Validation chạy sau binding, nên nó không ngăn Jackson tạo một list rất lớn trước khi validator từ chối. Với payload có nguy cơ lớn, kết hợp body limit và custom streaming/count limit để giới hạn allocation trong lúc parse.

### 5.4. Giới hạn nesting và cấu trúc đệ quy

Nested object sâu có thể gây áp lực stack, CPU và memory:

```json
{"node":{"child":{"child":{"child":{}}}}}
```

Giới hạn maxNestingDepth ở parser giúp chặn độ sâu trước khi binding toàn bộ object graph. Ngoài ra, domain model có thể cần giới hạn depth riêng nếu một field cho phép tree structure.

Không đặt depth quá thấp nếu format hợp lệ có nested data thực tế; đo payload production và test boundary ở mức ngay dưới, bằng và vượt limit.

### 5.5. Number length và numeric range là hai kiểm tra khác nhau

maxNumberLength giới hạn độ dài token số trong JSON. Nó không thay thế kiểm tra range của kiểu đích hoặc nghiệp vụ:

- Một số token ngắn vẫn có thể vượt Integer range.
- Một decimal token dài có thể nằm trong giới hạn parser nhưng vượt precision cho phép.
- Một số rất lớn có thể được đọc vào BigInteger nhưng không hợp lệ với domain.

Dùng parser limit để giới hạn chi phí đọc; dùng type binding và validation/domain để kiểm tra giá trị.

## 6. Giới hạn ở nhiều tầng

Một chính sách an toàn thường có nhiều lớp:

| Tầng | Giới hạn ví dụ | Mục tiêu |
|---|---|---|
| Gateway/proxy | Body bytes, timeout, rate limit | Chặn request quá lớn trước JVM |
| HTTP server | Request size, connection/read timeout | Bảo vệ server resources |
| Jackson Core | Nesting, string length, number length | Chặn token/pathological structure |
| Databinding | Coercion, unknown property, duplicate detection | Bảo vệ contract type |
| DTO validation | List size, text length, range | Kiểm tra request sau binding |
| Domain/service | Quota, batch count, business bounds | Bảo vệ nghiệp vụ và trạng thái |
| Storage/queue | Record size, retention, batch limit | Tránh đẩy dữ liệu quá lớn xuống hạ tầng |

Các lớp không thay thế nhau. Ví dụ @Size(max=500) không ngăn parser cấp phát list một triệu phần tử trước khi validator chạy. Ngược lại, body limit không đảm bảo email hợp lệ hoặc amount nằm trong business range.

### 6.1. Chú ý decompression

Nếu gateway hoặc ứng dụng nhận compressed request, giới hạn compressed bytes có thể nhỏ trong khi decompressed bytes rất lớn. Cần kiểm soát kích thước sau giải nén và tỷ lệ nén ở tầng hỗ trợ decompression. Không để client gửi payload nhỏ nhưng mở rộng thành dữ liệu khổng lồ trước khi Jackson đọc.

### 6.2. Chú ý streaming và buffering

Nếu controller nhận @RequestBody SomeDto, converter sẽ đọc body và tạo object. Nếu ứng dụng buffer toàn bộ body để log rồi lại parse, memory cost có thể tăng gấp đôi hoặc hơn. Tránh đọc body nhiều lần không cần thiết.

Với file import lớn, cân nhắc streaming parser và xử lý từng record thay vì deserialize toàn bộ file thành một collection. Streaming cũng cần giới hạn số record, tổng byte, thời gian và kích thước từng record.

## 7. Quản lý cấu hình mapper tập trung

Mapper cần được cấu hình hoàn chỉnh trước khi chia sẻ cho nhiều thread. ObjectMapper được thiết kế để tái sử dụng sau khi cấu hình; không thay đổi coercion/feature động trên instance đang xử lý request.

Tạo factory/configuration class:

```java
public final class JsonMapperFactory {
    private JsonMapperFactory() {}

    public static ObjectMapper createPublicApiMapper() {
        StreamReadConstraints constraints =
            StreamReadConstraints.builder()
                .maxNestingDepth(80)
                .maxStringLength(500_000)
                .maxNumberLength(80)
                .build();

        JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(constraints)
            .build();

        return JsonMapper.builder(factory)
            .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
            .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
            .build();
    }
}
```

Đây là profile minh họa. Giá trị phải được điều chỉnh theo contract và version. Nếu cần một mapper cho partner legacy có coercion khác, tạo profile riêng và gắn nó với converter/boundary tương ứng.

### 7.1. Dùng ObjectReader cho policy đọc cụ thể

ObjectReader là immutable configuration view phù hợp cho một lần đọc hoặc một nhóm use case:

```java
ObjectReader strictReader = mapper.readerFor(CreateOrderRequest.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .without(DeserializationFeature.ACCEPT_FLOAT_AS_INT);
```

ObjectReader có thể hữu ích khi cần cấu hình read behavior theo target type mà không mutate mapper gốc. Tuy nhiên, không phải mọi coercion/constraint đều có thể được thay đổi qua reader nếu chúng thuộc JsonFactory/mapper configuration. Với parser constraints, tạo factory/mapper riêng cho profile cần thiết.

### 7.2. Không mutate mapper sau khi ứng dụng đã bắt đầu

Tránh thay đổi feature trên mapper dùng chung trong request handler hoặc khi mapper đang được chia sẻ. Thay đổi cấu hình lúc runtime có thể tạo behavior khó dự đoán giữa các request đồng thời. Tạo mapper/reader profile trước khi phục vụ traffic; khi cần đổi policy, triển khai cấu hình mới theo version/canary.

### 7.3. Đặt tên profile theo contract

Tên như strictMapper hoặc looseMapper quá chung. Tên gắn với boundary dễ hiểu hơn:

- publicApiV1Reader
- partnerLegacyReader
- internalEventV2Reader
- bulkImportReader

Profile nên được mô tả bằng contract, không chỉ là danh sách feature. Ví dụ partnerLegacyReader có thể tạm nhận numeric string đến khi partner chuyển đổi; publicApiV2Reader yêu cầu JSON number.

## 8. Thiết kế thay đổi tương thích

Trước khi thay policy, phân loại thay đổi:

| Thay đổi | Tác động tương thích |
|---|---|
| Từ chối string-to-integer coercion | Có thể breaking với client gửi số dạng string |
| Từ chối float-to-integer | Có thể breaking với client gửi 1.0 cho field integer |
| Từ chối unknown properties | Có thể breaking khi client thêm field mới |
| Giảm max string length | Có thể breaking với payload dài hợp lệ |
| Giảm max nesting depth | Có thể breaking với document tree sâu |
| Giảm body size | Có thể breaking với batch request lớn |
| Từ chối null cho primitive/creator | Có thể breaking với client gửi explicit null |
| Giảm max collection size | Có thể breaking với batch client |

Thay đổi strict hơn thường là breaking đối với input trước đây được chấp nhận. Thay đổi nới rộng limit thường ít gây lỗi client hơn nhưng có thể tăng rủi ro resource consumption.

### 8.1. Expand-and-contract

Một quy trình phù hợp:

1. Công bố contract mới và ngưỡng sẽ áp dụng.
2. Thêm telemetry để đo bao nhiêu request sẽ bị policy mới từ chối.
3. Cập nhật client/producer gửi đúng kiểu và kích thước.
4. Giữ khả năng đọc cũ trong giai đoạn chuyển tiếp nếu cần.
5. Triển khai strict reader cho một nhóm traffic nhỏ.
6. Theo dõi lỗi và resource metrics.
7. Mở rộng dần sang toàn bộ traffic.
8. Loại bỏ compatibility path sau thời gian đã thông báo.

Không phải thay đổi nào cũng cần giữ hai reader lâu dài. Mục tiêu là tạo thời gian quan sát và cập nhật producer trước khi từ chối input cũ.

### 8.2. Version endpoint hoặc media contract khi semantics đổi lớn

Nếu coercion cũ là một phần contract đã được client sử dụng rộng, cân nhắc version endpoint, media type/profile hoặc event schema thay vì âm thầm đổi behavior trên cùng version.

Ví dụ:

- /api/v1/orders tiếp tục nhận legacy numeric string trong thời gian hỗ trợ.
- /api/v2/orders yêu cầu numeric token.
- Hoặc dùng request schema/event version riêng nếu hệ thống đã có cơ chế versioning.

Không tạo version mới chỉ cho một thay đổi nội bộ không quan sát được. Versioning nên phản ánh thay đổi contract mà consumer cần xử lý.

## 9. Quan sát trước khi bật strict policy

Muốn biết coercion nào đang được dùng, cần telemetry có chủ đích. Jackson không mặc định cung cấp một dashboard đầy đủ về mọi coercion đã xảy ra. Có thể dùng:

- Gateway/request logs đã chuẩn hóa.
- Custom deserializer hoặc parser instrumentation cho field trọng yếu.
- Metric từ lỗi mapping sau khi strict mode chạy ở canary.
- Sampling có giới hạn cho request đã được loại bỏ dữ liệu nhạy cảm.
- Client version/header để nhóm traffic theo producer.

Không log raw value hoặc body chỉ để đo coercion. Có thể ghi token shape, field path đã allowlist, endpoint và client version mà không ghi giá trị.

### 9.1. Metric nên có

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| request_body_unreadable_total | Đếm lỗi parse/binding |
| coercion_rejection_total | Đếm input bị policy mới từ chối |
| parser_constraint_violation_total | Đếm payload vượt parser limit |
| request_body_bytes | Theo dõi phân phối kích thước request |
| json_nesting_depth | Theo dõi độ sâu quan sát được nếu instrument được |
| collection_size | Theo dõi batch/list sizes theo endpoint |
| validation_failure_total | Đếm Bean Validation failures |
| request_latency | Phát hiện parse/validation chậm |
| allocation/GC metrics | Theo dõi memory pressure |

Metric label cần cardinality thấp. Dùng endpoint template, policy profile, client category hoặc failure category. Không dùng raw URL chứa ID, field value, user ID hoặc exception message làm label.

### 9.2. Phân biệt parser failure và validation failure

Nếu chỉ theo dõi tổng HTTP 400, sẽ không biết thay đổi coercion hay giới hạn parser gây lỗi. Tách:

- Jackson parse/binding errors.
- Parser constraint violations.
- Bean Validation violations.
- Spring parameter conversion errors.
- Domain/business rule failures.

Điều này giúp rollback đúng thay đổi và tránh nhầm một đợt client gửi dữ liệu nghiệp vụ sai với regression do parser config.

### 9.3. Sampling và privacy

Nếu cần xem ví dụ payload:

- Chỉ sample một tỷ lệ nhỏ.
- Redact field nhạy cảm trước khi lưu.
- Đặt retention ngắn.
- Kiểm soát quyền truy cập log.
- Không ghi token/password/secret.
- Không giữ body quá lớn trong log pipeline.

Trong nhiều trường hợp, token shape và field path đủ để biết client đang gửi sai kiểu; không cần lưu giá trị thật.

## 10. Test trước khi rollout

Một thay đổi policy nên có nhiều lớp test.

### 10.1. Unit test cho coercion

Với từng kiểu trọng yếu, kiểm tra input:

```json
{"quantity": 12}
{"quantity": "12"}
{"quantity": 12.0}
{"quantity": 12.7}
{"quantity": null}
{"quantity": ""}
```

Xác nhận input nào được nhận, input nào bị từ chối và exception category mong đợi. Test cả boundary numeric range.

### 10.2. Test parser constraints ở ranh giới

Với maxNestingDepth = N, kiểm tra:

- Payload sâu N-1.
- Payload sâu N.
- Payload sâu N+1.

Tương tự với maxStringLength và maxNumberLength: kiểm tra ngay dưới, tại và vượt limit. Cần tính đúng cách Jackson định nghĩa length và encoding; không chỉ dùng một string ASCII ngắn rồi suy ra behavior cho Unicode.

Ví dụ tạo nested JSON trong test:

```java
String nestedJson(int depth) {
    return "[".repeat(depth) + "0" + "]".repeat(depth);
}
```

Dùng helper này với mapper có limit cụ thể để xác nhận parser dừng ở ngưỡng mong đợi. Giữ depth vừa đủ để test nhanh, không tạo payload khổng lồ trong unit test.

### 10.3. Test HTTP integration

Dùng MockMvc để xác nhận:

- Content-Type đúng.
- Body được converter/mapper production đọc.
- Lỗi parser trả response contract đúng.
- Lỗi Bean Validation vẫn được phân biệt.
- Service không được gọi khi body bị từ chối.
- Request hợp lệ lớn nhất vẫn thành công.

Test trực tiếp ObjectMapper không chứng minh gateway/server body limit hoặc Spring converter đang dùng mapper đó.

### 10.4. Test compatibility fixtures

Lưu fixture JSON đại diện cho các client/version đang hoạt động:

- Payload từ client cũ.
- Payload từ client mới.
- Field optional bị thiếu.
- Explicit null.
- Numeric string/float/enum legacy.
- Payload lớn nhất hợp lệ.
- Nested structure hợp lệ sâu nhất.
- Unknown field nếu contract cho phép.

Fixture phải không chứa secret hoặc dữ liệu cá nhân thật. Có thể dùng dữ liệu tổng hợp có cùng hình dạng và kích thước.

### 10.5. Consumer-driven contract tests

Nếu có nhiều producer/consumer, kiểm tra hợp đồng ở cả hai phía:

- Producer test payload mà nó phát ra.
- Consumer test payload từ producer version cũ.
- Compatibility test xác nhận consumer mới đọc dữ liệu cũ.
- Nếu strict policy mới từ chối một input, test thông báo lỗi và version contract.

Một test chỉ dùng producer mới và consumer mới không phát hiện được vấn đề với client cũ đang chạy ngoài production.

## 11. Triển khai canary và mở rộng dần

Sau khi test pass, triển khai thay đổi qua các giai đoạn:

1. **Stage 0 — Baseline.** Ghi nhận request volume, parse/binding errors, p95/p99, body size, memory và GC trước khi đổi.
2. **Stage 1 — Observe.** Bật metric hoặc shadow analysis để biết bao nhiêu request sẽ bị policy mới từ chối. Không ghi raw payload nhạy cảm.
3. **Stage 2 — Canary.** Bật strict policy cho một nhóm instance, tenant hoặc client đã chọn.
4. **Stage 3 — Expand.** Mở rộng traffic theo từng bước khi error rate và resource metrics ổn định.
5. **Stage 4 — Enforce.** Áp dụng policy mới cho toàn bộ boundary và loại bỏ compatibility path theo kế hoạch.
6. **Stage 5 — Verify.** Xác nhận không còn producer phụ thuộc coercion cũ; cập nhật tài liệu và config version.

Canary cần được phân nhóm đúng. Nếu client cũ chỉ gửi traffic vào một cụm hoặc một tenant, chia ngẫu nhiên theo instance có thể không đại diện. Dùng client ID/version hoặc tenant cohort khi có thể.

### 11.1. Shadow parsing

Trong một số trường hợp, có thể đọc cùng payload bằng policy cũ và policy mới để đo khác biệt trước khi enforcement. Đây là kỹ thuật shadow parsing:

1. Đọc body một lần hoặc lưu một bản bounded byte buffer an toàn.
2. Parse bằng mapper hiện tại để giữ behavior production.
3. Parse bản sao bằng mapper candidate.
4. Ghi metric về kết quả khác nhau, không gọi business logic hai lần.

Không parse body hai lần bằng cách đọc InputStream đã tiêu thụ. Nếu shadow parse cần buffer body, phải giới hạn kích thước và đánh giá memory cost. Không chạy custom deserializer có side effect hai lần; chỉ dùng mapper thuần cho shadow path.

Shadow parse cũng không thay thế canary enforcement. Nó đo sự khác biệt trên traffic quan sát được, nhưng không bảo đảm mọi edge case đã xuất hiện.

### 11.2. Không bật strictness theo một flag mutable trong mapper

Feature toggle có thể chọn giữa hai reader/mapper đã cấu hình trước:

```java
ObjectReader legacyReader = legacyMapper.readerFor(CreateOrderRequest.class);
ObjectReader strictReader = strictMapper.readerFor(CreateOrderRequest.class);

ObjectReader selected = rolloutPolicy.useStrictReader(clientId)
    ? strictReader
    : legacyReader;

CreateOrderRequest request = selected.readValue(bodyBytes);
```

Đây là ví dụ kiến trúc. rolloutPolicy cần quyết định ổn định theo cohort và được quan sát; không mutate mapper trong request. Với Spring MVC, lựa chọn reader theo request có thể cần converter riêng hoặc một abstraction đọc body có kiểm soát. Không tự thay converter toàn cục theo request nếu không hiểu lifecycle của Spring.

## 12. Theo dõi sau triển khai

Sau mỗi giai đoạn rollout, so sánh với baseline:

- Tỷ lệ HttpMessageNotReadableException theo endpoint/client cohort.
- Tỷ lệ parser constraint violation.
- Tỷ lệ Bean Validation error để xem có thay đổi mix input.
- p50/p95/p99 latency.
- Request body size distribution.
- CPU, allocation, heap, GC pause.
- Retry rate và backlog ở broker/queue.
- Tỷ lệ request hợp lệ từ client cũ.

Không chỉ nhìn số lỗi tuyệt đối. Nếu traffic tăng hoặc giảm, dùng rate trên tổng request theo cohort. So sánh cùng khung giờ và loại endpoint khi có seasonality.

### 12.1. Ngưỡng dừng rollout

Đặt ngưỡng trước khi canary:

- Error rate tăng vượt baseline một mức đã thống nhất.
- Một client/tenant quan trọng có tỷ lệ reject tăng mạnh.
- Request hợp lệ lớn nhất bắt đầu thất bại.
- p95/p99 hoặc CPU/GC vượt SLO.
- Consumer backlog hoặc retry tăng kéo dài.

Ngưỡng cụ thể tùy service. Không đợi toàn bộ hệ thống outage mới rollback; một cohort quan trọng bị ảnh hưởng có thể đủ để dừng mở rộng.

## 13. Rollback và forward fix

Trước rollout, chuẩn bị đường quay lại:

- Giữ config version trước đó.
- Có thể chọn lại legacy reader/mapper đã được test.
- Biết cần restart instance hay chỉ đổi deployment configuration.
- Có metric xác nhận traffic đã trở lại behavior cũ.
- Ghi rõ rollback có làm mất các giới hạn bảo mật quan trọng hay không.

Nếu thay đổi nhằm chặn một input nguy hiểm, rollback về policy quá permissive có thể tái mở rủi ro. Trong trường hợp đó, có thể rollback phần coercion nhưng giữ body/parser limit, hoặc áp dụng allowlist tạm thời cho client bị ảnh hưởng.

### 13.1. Phân biệt rollback code và rollback data

Thay parser policy thường không thay đổi database schema, nhưng có thể làm queue chứa message bị reject hoặc dead-letter. Khi rollback:

- Xác định message đã bị từ chối có được retry không.
- Giữ payload gốc trong DLQ theo retention/security policy.
- Không replay vô hạn một message luôn lỗi.
- Nếu client đã thay đổi payload theo contract mới, legacy reader có thể vẫn đọc được nhưng phải xác nhận.

### 13.2. Khi nào nên forward fix?

Nếu policy mới đúng nhưng limit chọn quá thấp, tăng limit có kiểm soát có thể tốt hơn rollback toàn bộ. Nếu coercion mới phát hiện client vi phạm contract, cập nhật client có thể đúng hơn nới policy cho mọi người. Quyết định dựa trên dữ liệu, mức độ an toàn và contract đã công bố.

## 14. Thay đổi giới hạn: tăng và giảm đều cần kế hoạch

### 14.1. Giảm giới hạn

Giảm limit thường là thay đổi breaking với payload hợp lệ lớn hơn ngưỡng mới. Quy trình:

1. Đo phân phối thực tế và tìm p99/max hợp lệ.
2. Xác định payload nào vượt ngưỡng mới và client nào tạo ra.
3. Thông báo hoặc giới hạn batch ở producer.
4. Bật metric cảnh báo trước enforcement.
5. Giảm theo từng bước nếu có thể.
6. Canary và theo dõi reject rate.

### 14.2. Tăng giới hạn

Tăng limit có thể làm hệ thống chấp nhận payload tốn nhiều tài nguyên hơn. Trước khi tăng:

- Load test với payload lớn nhất mới.
- Ước tính memory per concurrent request.
- Kiểm tra timeout và backpressure.
- Kiểm tra giới hạn proxy/server có đồng bộ không.
- Kiểm tra số phần tử có thể tạo ra từ một body.
- Cân nhắc streaming thay vì tăng buffer/limit.

Không tăng mọi limit cùng lúc. Thay đổi một chiều mỗi lần giúp xác định nguyên nhân khi latency hoặc memory thay đổi.

### 14.3. Đặt giới hạn theo endpoint/use case

Một endpoint upload metadata có thể cần string dài; endpoint tạo user không cần. Một bulk API có thể cần list tối đa 500 phần tử; API đơn lẻ chỉ cần một object.

Nếu tất cả endpoint dùng một mapper toàn cục, limit chung có thể quá rộng hoặc quá chặt. Có thể dùng converter/mapper riêng cho nhóm endpoint, DTO-specific validation và transport-level route limits. Đảm bảo các mapper riêng vẫn chia sẻ security baseline và không tạo lỗ hổng do cấu hình thiếu.

## 15. Quản lý cấu hình theo môi trường

Không để dev, staging và production vô tình chạy các coercion/limits khác nhau mà không biết:

- Lưu config trong code hoặc configuration source có version.
- Ghi log startup summary về policy profile và limit, không log secret.
- Expose config version qua build metadata/diagnostic endpoint có kiểm soát.
- Test profile production-like trong CI/staging.
- Không cho operator sửa mapper runtime tùy ý qua endpoint quản trị.

Nếu giá trị limit có thể cấu hình qua environment variables, validate range lúc startup. Giá trị âm, null hoặc quá lớn phải làm startup fail rõ ràng thay vì âm thầm dùng default.

Ví dụ properties:

```yaml
app:
  json:
    policy-version: strict-v2
    max-nesting-depth: 80
    max-string-length: 500000
    max-number-length: 80
    max-request-bytes: 2000000
    max-bulk-items: 500
```

Đây là ví dụ cấu trúc config. Mỗi giá trị cần được bind vào configuration properties có validation và dùng để tạo factory/mapper lúc startup. max-request-bytes cần được thực thi ở server/gateway hoặc body reader; không tự động được StreamReadConstraints áp dụng.

## 16. Cấu hình Spring Boot và message converter

Trong Spring Boot, có thể cấu hình mapper qua Jackson2ObjectMapperBuilderCustomizer hoặc bean ObjectMapper tùy ứng dụng. Tránh tạo nhiều bean cùng type không có qualifier rồi để injection chọn không rõ ràng.

Ví dụ customizer:

```java
@Configuration
public class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer strictJsonPolicy() {
        return builder -> builder.featuresToDisable(
            DeserializationFeature.ACCEPT_FLOAT_AS_INT
        );
    }
}
```

Customizer này áp dụng cho mapper do builder tạo; nó không nhất thiết cấu hình mọi ObjectMapper được tạo trực tiếp bằng constructor. Với StreamReadConstraints, cần kiểm soát JsonFactory được dùng bởi mapper. Tùy Spring Boot/Jackson version, có thể cần factory custom hoặc bean mapper cụ thể.

Nếu ứng dụng đăng ký MappingJackson2HttpMessageConverter riêng, kiểm tra converter đó có dùng mapper mong muốn và thứ tự converter có phù hợp không. Integration test nên gửi HTTP request thực tế qua MVC để xác nhận.

## 17. Test rollout profile

Tạo test cho từng policy profile:

```java
class JsonPolicyTest {
    private final ObjectMapper legacyMapper = createLegacyMapper();
    private final ObjectMapper strictMapper = createStrictMapper();

    @Test
    void legacyProfileAcceptsSupportedLegacyNumericString() throws Exception {
        LegacyRequest request = legacyMapper.readValue(
            "{\"quantity\":\"12\"}",
            LegacyRequest.class
        );

        assertEquals(12, request.quantity());
    }

    @Test
    void strictProfileRejectsNumericString() {
        assertThrows(JsonMappingException.class, () ->
            strictMapper.readValue(
                "{\"quantity\":\"12\"}",
                StrictRequest.class
            )
        );
    }
}
```

Hai profile không nhất thiết dùng hai DTO khác nhau; ví dụ chỉ minh họa cách tách contract. Nếu cùng DTO được dùng, test đúng class và mapper đang gắn với từng endpoint.

### 17.1. Kiểm tra policy version

Nếu config có policy-version, test startup/config binding xác nhận:

- Config thiếu thì default có chủ đích.
- Config sai tên thì startup fail.
- Limit ngoài range thì startup fail.
- Mapper được tạo với constraints tương ứng.
- MVC converter dùng mapper đó.

Không chỉ assert properties object có giá trị; cần integration test để chứng minh giá trị đã đi tới parser.

### 17.2. Regression fixtures

Mỗi lần thay policy, chạy lại fixture corpus. Có thể lưu metadata cho từng fixture:

| Fixture | Producer version | Expected profile | Expected result |
|---|---|---|---|
| order-v1-numeric-string.json | client v1 | legacy | Accept |
| order-v2-number.json | client v2 | strict | Accept |
| order-float-quantity.json | client v2 | strict | Reject |
| order-deep-nesting.json | import v1 | bounded | Reject nếu vượt limit |
| order-large-list.json | bulk v2 | bounded | Accept dưới quota |

Fixture phải có kích thước được kiểm soát và không chứa dữ liệu thật. Khi behavior thay đổi có chủ đích, cập nhật expected result và ghi lại contract/version liên quan.

## 18. Lỗi thường gặp khi rollout

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nhiều client nhận 400 sau deploy | Tắt coercion mà chưa kiểm tra input cũ | Dùng telemetry/cohort, cập nhật producer rồi canary strict policy. |
| Một endpoint không đổi behavior | MVC converter dùng mapper khác | Kiểm tra converter và integration test qua HTTP. |
| Payload hợp lệ bị từ chối | Limit chọn thấp hơn phân phối thực tế | Đo p99/max hợp lệ, nâng limit có kiểm soát hoặc chia endpoint profile. |
| Memory tăng sau khi tăng limit | Chỉ tăng parser limit, bỏ qua concurrency/body size | Load test và kiểm soát body bytes, collection count, concurrency. |
| List khổng lồ vẫn được parse rồi mới fail | Chỉ dùng @Size sau binding | Thêm streaming/count limit và body cap. |
| Mapper behavior thay đổi giữa request | Mutate ObjectMapper dùng chung lúc runtime | Tạo immutable mapper/reader profile trước startup. |
| Shadow parser làm side effect lặp | Custom deserializer không thuần được chạy hai lần | Chỉ shadow parse bằng mapper thuần; không gọi business logic. |
| Error dashboard không chỉ ra nguyên nhân | Chỉ đếm HTTP 400 tổng | Tách parse, bind, limit, Bean Validation và conversion metrics. |
| Rollback mở lại input nguy hiểm | Quay lại toàn bộ cấu hình permissive | Rollback theo profile/feature và giữ các limit an toàn cần thiết. |
| Consumer queue bị kẹt | Message cũ không tương thích policy mới | Dùng DLQ/replay có kiểm soát và giữ schema/format version. |

## 19. Quy trình triển khai thực tế

1. Inventory mọi ObjectMapper, JsonFactory, ObjectReader và Spring message converter.
2. Xác định boundary, producer, consumer và DTO chịu ảnh hưởng.
3. Ghi lại policy hiện tại: coercion, unknown fields, null, parser constraints và body limits.
4. Phân loại thay đổi là breaking hay non-breaking đối với input đã được chấp nhận.
5. Tạo fixture đại diện cho client cũ/mới và payload biên.
6. Viết unit tests cho coercion và parser limits ở dưới/tại/vượt ngưỡng.
7. Viết integration tests qua converter production, kiểm tra cả error response và service interaction.
8. Thêm metric có cardinality thấp để phân biệt parse, bind, limit và validation.
9. Nếu cần, shadow-parse bằng mapper thuần và buffer có giới hạn để đo khác biệt.
10. Cập nhật producer/client trước khi enforcement nếu policy mới từ chối input cũ.
11. Tạo mapper/reader profile mới bất biến; không mutate mapper đang phục vụ traffic.
12. Canary theo client/tenant/instance cohort có ý nghĩa.
13. So sánh error rate, latency, body size, CPU, memory, GC và queue backlog với baseline.
14. Mở rộng theo từng giai đoạn; dừng hoặc rollback khi vượt ngưỡng đã đặt.
15. Giữ DLQ/replay và config rollback cho message/file đã bị từ chối.
16. Khi rollout hoàn tất, loại bỏ compatibility path và cập nhật contract/tài liệu.

## 20. Checklist trước khi bật policy mới

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Mapper nào thực sự đọc request? | Inventory và integration test qua HTTP |
| Client nào dùng coercion cũ? | Metrics/cohort hoặc fixture từ producer |
| Input nào sẽ bị từ chối? | Test cụ thể theo token shape |
| Limit mới có chặn payload hợp lệ không? | Phân phối traffic và boundary tests |
| Có giới hạn body ở transport không? | Gateway/server config |
| Có giới hạn số phần tử không? | DTO/domain/count enforcement |
| Error được phân loại rõ không? | Metric và error code riêng |
| Có thể rollback không? | Config version/legacy profile đã test |
| Shadow path có side effect không? | Mapper thuần và test service không bị gọi |
| Consumer cũ có tương thích không? | Contract fixtures/consumer tests |

Triển khai thay đổi coercion hoặc parser limit an toàn là quá trình quản lý contract, không chỉ là bật một feature trên ObjectMapper. Hãy xác định chính xác mapper và consumer chịu ảnh hưởng, đo input thực tế, chọn giới hạn từ workload hợp lệ, kiểm thử từng token shape và boundary, rồi rollout theo cohort với metric và rollback đã chuẩn bị. Khi mapper được cấu hình bất biến theo profile, giới hạn được áp dụng ở nhiều tầng và producer được cập nhật theo expand-and-contract, ứng dụng có thể tăng tính nghiêm ngặt và khả năng chống payload bất thường mà không tạo ra một đợt lỗi hàng loạt ngoài dự kiến.
