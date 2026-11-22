# Kiểm thử dữ liệu lỗi, giới hạn tài nguyên và tương thích phiên bản

## 1. Mục tiêu của chiến lược kiểm thử

Một bài kiểm thử Jackson cơ bản thường tạo POJO, serialize thành JSON rồi deserialize lại. Round-trip đó hữu ích nhưng chưa đủ để chứng minh hệ thống an toàn trong production. Dữ liệu thực tế có thể đến từ client cũ, message broker, file import, đối tác tích hợp hoặc nguồn không đáng tin cậy. Những nguồn này có thể gửi JSON sai cú pháp, đúng cú pháp nhưng sai kiểu, payload quá lớn hoặc dữ liệu được tạo bởi phiên bản schema/Jackson khác.

Chiến lược kiểm thử cần trả lời ba câu hỏi:

1. **Tính đúng đắn:** dữ liệu hợp lệ có được đọc và ghi đúng theo hợp đồng không?
2. **Khả năng chống chịu:** dữ liệu lỗi hoặc vượt giới hạn có bị từ chối có kiểm soát không?
3. **Tương thích:** producer, consumer và các phiên bản thư viện có giao tiếp được trong phạm vi hỗ trợ không?

Các nhóm rủi ro chính gồm:

- JSON sai cú pháp, bị cắt giữa chừng hoặc có token ngoài dự kiến.
- JSON hợp lệ nhưng không ánh xạ được vào kiểu Java.
- Giá trị ánh xạ được nhưng vi phạm quy tắc nghiệp vụ.
- Property bị thiếu, explicit null, chuỗi rỗng hoặc giá trị mặc định.
- Số vượt miền kiểu, mất precision hoặc có scale ngoài hợp đồng.
- Property trùng tên, enum hoặc subtype không được biết.
- Nesting, string, number, array, file hoặc request quá lớn.
- Payload cũ cần được đọc sau khi DTO hoặc Jackson được nâng cấp.
- Lỗi parse làm phát sinh side effect một phần hoặc để lại output dở dang.

Không nên chỉ xác nhận rằng exception được ném. Cần kiểm tra loại lỗi, trạng thái hệ thống sau lỗi, khả năng phục hồi và việc không có side effect ngoài ý muốn.

## 2. Phân biệt syntax, mapping và domain validation

Một input có thể thất bại ở ba tầng khác nhau:

| Tầng | Ví dụ | Thành phần chịu trách nhiệm |
|---|---|---|
| Syntax | Thiếu dấu ngoặc, escape sai, token không hợp lệ | Jackson Core parser |
| Mapping | Object gửi vào field integer, enum lạ, creator property không hợp lệ | Jackson Databind |
| Domain | Số lượng âm, ngày kết thúc trước ngày bắt đầu | Validator/nghiệp vụ |

Giữ riêng ba nhóm này giúp API trả lỗi phù hợp và giúp vận hành xác định nguyên nhân. Không nên gom mọi lỗi thành một RuntimeException chung.

Ví dụ, JSON sau đúng cú pháp nhưng không đúng shape DTO:

~~~json
{
  "id": {"value": 10},
  "quantity": "many",
  "active": ["yes"]
}
~~~

Nếu DTO yêu cầu String, int và boolean, Databind sẽ từ chối một hoặc nhiều field tùy cấu hình coercion. Một payload khác có thể deserialize thành công nhưng quantity = -5; đó là lỗi domain, không phải lỗi parser.

## 3. Kiểm thử JSON sai cú pháp

Parser cần từ chối những input không tuân thủ JSON grammar:

~~~text
{"id": 1
{"id": 1,}
{'id': 1}
{"id": "unterminated}
{"id": NaN}
{"id": 01}
~~~

Các trường hợp lần lượt minh họa object chưa đóng, dấu phẩy cuối, dấu nháy đơn, string chưa đóng, token NaN không thuộc JSON chuẩn và số có leading zero không hợp lệ.

Ví dụ JUnit:

~~~java
class JsonSyntaxTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @ParameterizedTest
    @ValueSource(strings = {
        "{\"id\": 1",
        "{\"id\": 1,}",
        "{'id': 1}",
        "{\"id\": \"unterminated}",
        "{\"id\": NaN}",
        "{\"id\": 01}"
    })
    void rejectsMalformedJson(String input) {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readTree(input)
        );
    }
}
~~~

Nếu production bật extension như comments, single quotes, trailing commas hoặc non-numeric numbers, test phải dùng đúng cấu hình production. Một input được chấp nhận trong permissive mode không có nghĩa nó là JSON chuẩn.

Với API công khai, chỉ bật extension khi hợp đồng yêu cầu. Tránh nới lỏng parser chỉ để chấp nhận payload lỗi từ một producer mà không có kế hoạch chuyển đổi.

## 4. Kiểm thử lỗi mapping và coercion

JSON có thể hợp lệ nhưng không phù hợp kiểu Java. Cần kiểm thử những token shape khác nhau cho từng field:

- String thay cho number.
- Object thay cho scalar.
- Array thay cho object.
- Boolean thay cho string.
- Decimal gửi vào integer.
- String rỗng hoặc whitespace gửi vào number.
- Giá trị null gửi vào primitive.

Ví dụ:

~~~java
class ProductRequest {
    public String id;
    public int quantity;
    public boolean active;
}

@Test
void rejectsWrongJsonShape() {
    String json = """
        {
          "id": {"value": 10},
          "quantity": "many",
          "active": ["yes"]
        }
        """;

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue(json, ProductRequest.class)
    );
}
~~~

Đoạn text block yêu cầu Java 15 trở lên. Với JDK cũ hơn, dùng chuỗi Java thông thường.

Không phải mọi khác biệt JSON/Java đều mặc định bị từ chối. Jackson có coercion rules cho một số trường hợp. Ví dụ, floating-point có thể được ép thành integer nếu ACCEPT_FLOAT_AS_INT đang bật.

Nếu hợp đồng yêu cầu integer token, hãy tắt feature này và kiểm thử:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();

assertThrows(
    JsonProcessingException.class,
    () -> strictMapper.readValue("12.5", Integer.class)
);
~~~

Từ Jackson Databind 2.12, coercion có thể được cấu hình theo logical type và input shape:

~~~java
strictMapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Kiểm thử cả default behavior và override theo property nếu ứng dụng dùng @JsonFormat, custom deserializer hoặc coercion configuration riêng.

## 5. Kiểm thử missing, null, empty và default

Các trạng thái dưới đây không nhất thiết tương đương:

~~~json
{}
~~~

~~~json
{"name": null}
~~~

~~~json
{"name": ""}
~~~

~~~json
{"name": " "}
~~~

~~~json
{"name": "Lan"}
~~~

Với bean mutable, property bị thiếu thường giữ initializer hoặc giá trị mặc định của Java nếu không được gán. Explicit null thường được áp dụng theo null policy. Với constructor hoặc record, missing creator parameter có thể có hành vi khác và có thể bị từ chối khi bật feature tương ứng.

Test nên xác nhận:

- Field thiếu có được phép không?
- Null có được phép không?
- Empty string có phải giá trị hợp lệ không?
- Whitespace-only có được trim hoặc từ chối không?
- Default được áp dụng ở Jackson hay domain layer?
- Primitive có vô tình biến missing/null thành 0 hoặc false không?

Không dựa vào primitive default để phân biệt “client không gửi” với “client gửi 0/false”. Dùng wrapper, presence flag hoặc DTO patch riêng nếu hai trạng thái có ý nghĩa khác nhau.

Ví dụ bật kiểm tra null cho primitive:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();

assertThrows(
    JsonProcessingException.class,
    () -> mapper.readValue("{\"quantity\":null}", ProductRequest.class)
);
~~~

Với creator properties, có thể kiểm thử FAIL_ON_MISSING_CREATOR_PROPERTIES và FAIL_ON_NULL_CREATOR_PROPERTIES theo đúng schema. Không bật feature một cách máy móc nếu API có chủ đích dùng default cho field bị thiếu.

## 6. Kiểm thử số lớn, miền giá trị và precision

Test số phải chạm cả hai biên và giá trị ngay ngoài biên:

~~~java
@Test
void checksIntegerBoundaries() throws Exception {
    assertEquals(
        Integer.MIN_VALUE,
        mapper.readValue("-2147483648", Integer.class)
    );
    assertEquals(
        Integer.MAX_VALUE,
        mapper.readValue("2147483647", Integer.class)
    );

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue("-2147483649", Integer.class)
    );
    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue("2147483648", Integer.class)
    );
}
~~~

Với số nguyên lớn, đọc vào BigInteger thay vì ép về long:

~~~java
BigInteger original =
    new BigInteger("123456789012345678901234567890");

String json = mapper.writeValueAsString(original);
BigInteger restored = mapper.readValue(json, BigInteger.class);

assertEquals(original, restored);
~~~

Với decimal cần chính xác, dùng BigDecimal:

~~~java
BigDecimal original = new BigDecimal("1234567890.12000");
String json = mapper.writeValueAsString(original);
BigDecimal restored = mapper.readValue(json, BigDecimal.class);

assertEquals(original, restored);
~~~

BigDecimal.equals() so sánh cả scale; compareTo() so sánh giá trị số học. Chọn phép so sánh theo hợp đồng. Đừng chuyển qua double nếu cần giữ chính xác decimal.

Ngoài miền kiểu Java, kiểm tra giới hạn nghiệp vụ: số âm, precision tối đa, scale, rounding mode và giá trị lớn nhất được phép.

Nếu deserialize dữ liệu untyped thành Object hoặc Map, các feature như USE_BIG_INTEGER_FOR_INTS và USE_BIG_DECIMAL_FOR_FLOATS có thể ảnh hưởng kiểu runtime. Test cả typed DTO lẫn untyped data nếu ứng dụng dùng hai cách.

## 7. Kiểm thử enum và subtype không biết

Khi producer thêm enum value mới, consumer cũ có thể ném InvalidFormatException. Có thể chọn strict rejection hoặc fallback có chủ đích:

~~~java
enum Status {
    NEW,
    PAID,
    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

~~~java
ObjectMapper tolerantEnumMapper = JsonMapper.builder()
    .enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
    )
    .build();
~~~

Test phải xác nhận enum lạ được từ chối hoặc chuyển về UNKNOWN đúng chính sách. Không ánh xạ giá trị lạ vào trạng thái có ý nghĩa như PAID nếu không có quy tắc nghiệp vụ rõ.

Nếu DTO dùng polymorphic deserialization, kiểm thử:

- Type ID hợp lệ.
- Type ID không biết.
- Thiếu type ID.
- Type ID có JSON type sai.
- Subtype không nằm trong allowlist.
- Payload có field subtype không hợp lệ.

Không bật default typing không giới hạn cho dữ liệu không đáng tin cậy. Nếu polymorphism là cần thiết, dùng subtype registration tường minh hoặc PolymorphicTypeValidator phù hợp, sau đó kiểm thử cả subtype được phép lẫn bị từ chối.

## 8. Kiểm thử duplicate property

Duplicate member name có thể khiến parser hoặc tầng trung gian diễn giải payload khác nhau. Jackson Core hỗ trợ strict duplicate detection:

~~~java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper strictMapper = new ObjectMapper(factory);
~~~

Test:

~~~java
@Test
void rejectsDuplicateMemberNames() {
    String json = """
        {
          "role": "reader",
          "role": "administrator"
        }
        """;

    assertThrows(
        JsonProcessingException.class,
        () -> strictMapper.readTree(json)
    );
}
~~~

Kiểm tra duplicate ở object lồng nhau và tên sau khi giải mã escape. Strict parser detection xử lý duplicate member name ở tầng JSON. Nó không nhất thiết phát hiện hai tên khác nhau cùng ánh xạ vào một property Java do @JsonAlias, case-insensitive matching hoặc naming strategy. Nếu DTO có alias, thêm test semantic collision ở tầng schema/DTO.

## 9. Giới hạn tài nguyên của parser

Một payload có thể hợp lệ về cú pháp nhưng quá lớn để xử lý an toàn. Các dạng gây áp lực gồm:

- Nesting depth rất sâu.
- String có hàng triệu ký tự.
- Number token có quá nhiều chữ số.
- Object có quá nhiều property.
- Array có số lượng phần tử lớn.
- Nhiều record nhỏ nhưng tổng file quá lớn.
- Một record đơn lẻ chiếm phần lớn heap.

Jackson Core cung cấp StreamReadConstraints trong các phiên bản hỗ trợ. Có thể đặt giới hạn độ sâu, độ dài string và number:

~~~java
JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(
        StreamReadConstraints.builder()
            .maxNestingDepth(100)
            .maxStringLength(1_000_000)
            .maxNumberLength(1_000)
            .build()
    )
    .build();

ObjectMapper constrainedMapper = new ObjectMapper(factory);
~~~

Các con số chỉ là ví dụ. Chọn theo schema và workload thực tế. API và default của StreamReadConstraints phụ thuộc phiên bản Jackson Core; xác nhận với dependency đang sử dụng.

Parser constraints không thay thế giới hạn ở transport hoặc nghiệp vụ. Nên có thêm maximum request/file size, maximum record size, maximum array item count, timeout đọc/xử lý, giới hạn batch/queue và giới hạn tổng record của một lần import.

## 10. Kiểm thử nesting depth, string và number tại biên

Tạo input lồng nhau để xác nhận giới hạn:

~~~java
static String nestedArray(int depth) {
    return "[".repeat(depth) + "0" + "]".repeat(depth);
}

@Test
void rejectsNestingBeyondConfiguredLimit() {
    String input = nestedArray(150);

    assertThrows(
        JsonProcessingException.class,
        () -> constrainedMapper.readTree(input)
    );
}
~~~

Ví dụ dùng String.repeat() của Java 11 trở lên. Test nên có độ sâu ngay dưới, tại và vượt giới hạn. Kiểm tra tại biên giúp phát hiện khác biệt trong cách parser đếm container.

String và number quá dài:

~~~java
String oversizedString =
    "{\"value\":\"" + "x".repeat(1_000_001) + "\"}";

assertThrows(
    JsonProcessingException.class,
    () -> constrainedMapper.readTree(oversizedString)
);

String longNumber = "9".repeat(1_001);

assertThrows(
    JsonProcessingException.class,
    () -> constrainedMapper.readTree(longNumber)
);
~~~

Đoạn ví dụ tương ứng giới hạn 1.000 ký tự. Hãy giữ test setup và input thống nhất. Ngoài exception, đo thời gian và memory với payload gần giới hạn. Một parser có thể từ chối đúng nhưng vẫn phải đọc đáng kể dữ liệu trước khi phát hiện token vượt ngưỡng.

## 11. Giới hạn request, file và record ở các tầng khác nhau

Một giới hạn parser chỉ bảo vệ token đang được parse. Nó không tự giới hạn tổng kích thước file hoặc số record. Cần phân tầng:

| Tầng | Giới hạn ví dụ | Mục đích |
|---|---|---|
| HTTP/server | Request body bytes | Không nhận body quá lớn |
| File ingestion | File bytes, decompressed bytes | Chặn file quá lớn hoặc gzip bomb |
| Framing | NDJSON line bytes / record bytes | Giới hạn một record |
| Jackson Core | Nesting, string, number | Giới hạn độ phức tạp token |
| Databind/domain | Array count, field count, range | Giới hạn cấu trúc và nghiệp vụ |
| Pipeline | Batch, queue, concurrency | Giới hạn dữ liệu đang in-flight |

Với dữ liệu nén, giới hạn kích thước sau giải nén cũng quan trọng. Một file gzip nhỏ có thể nở thành lượng dữ liệu rất lớn. Đặt cả compressed-size limit và decompressed-byte limit.

## 12. Kiểm thử lỗi không tạo side effect

Một payload không hợp lệ không được làm thay đổi hệ thống một phần ngoài ý muốn.

Ví dụ request có nhiều command:

~~~json
{
  "commands": [
    {"accountId": "A-1", "amount": 10},
    {"accountId": "A-2", "amount": "invalid"}
  ]
}
~~~

Nếu ứng dụng xử lý phần tử đầu trước khi biết phần tử sau không hợp lệ, tài khoản A-1 có thể đã được cập nhật trong khi request tổng thể thất bại.

Tùy nghiệp vụ, chọn một trong các cách:

- Parse và validate toàn bộ request trước khi thực hiện side effect.
- Dùng transaction để commit hoặc rollback toàn bộ.
- Xử lý từng record độc lập và công bố partial success rõ ràng.
- Cách ly record lỗi và tiếp tục nếu hợp đồng cho phép.

Test phải xác nhận trạng thái database, file output hoặc message downstream sau lỗi. Chỉ assert exception được ném là chưa đủ.

## 13. Kiểm thử duplicate, coercion và parser extension cùng nhau

Mapper production có thể bật nhiều feature. Test từng feature riêng là cần thiết, nhưng cũng nên có test tích hợp cho cấu hình hoàn chỉnh:

- Duplicate key bị từ chối khi đọc POJO, Map và JsonNode.
- String số bị từ chối nếu numeric policy yêu cầu.
- Floating-point token không bị ép vào integer ngoài ý muốn.
- Comment hoặc trailing comma chỉ được chấp nhận nếu hợp đồng cho phép.
- Unknown property theo đúng strict/tolerant policy.
- Nesting, string và number limit vẫn áp dụng khi dùng custom deserializer.

Không parse bằng mapper permissive rồi chuyển sang mapper strict sau đó. Dữ liệu có thể đã bị chuẩn hóa hoặc mất thông tin ở bước đầu.

## 14. Property-based testing

Boundary tests cố định rất quan trọng nhưng không bao phủ mọi tổ hợp. Property-based testing tạo nhiều giá trị theo generator và kiểm tra một thuộc tính tổng quát.

Các property hữu ích:

- Serialize rồi deserialize POJO hợp lệ phải giữ các giá trị theo contract.
- BigInteger round-trip không mất chữ số.
- BigDecimal round-trip giữ giá trị và scale nếu scale thuộc hợp đồng.
- Chuỗi Unicode hợp lệ không bị thay đổi ngoài quy tắc normalization đã công bố.
- Payload vượt parser constraint bị từ chối.
- Unknown enum/subtype theo đúng policy.
- Các collection giữ thứ tự nếu thứ tự là một phần của contract.

Có thể dùng jqwik hoặc QuickTheories nếu dự án đã có. Không cần thêm framework chỉ để kiểm tra một vài giá trị cố định; JUnit parameterized test thường đủ cho boundary đơn giản.

Thuộc tính round-trip thường được diễn đạt:

~~~text
deserialize(serialize(value)) = value
~~~

Với object có thời gian, decimal hoặc collection không thứ tự, định nghĩa equality theo semantics domain thay vì so sánh chuỗi JSON. Ví dụ timezone có thể được chuẩn hóa sang UTC; decimal có thể giữ numeric value nhưng không giữ scale nếu contract cho phép.

## 15. Fuzz testing parser và deserializer

Fuzz testing đưa vào parser nhiều chuỗi/byte bất thường để tìm lỗi xử lý, crash hoặc tiêu thụ tài nguyên không hợp lý.

Những vùng đầu vào đáng fuzz:

- Dấu ngoặc, dấu phẩy, quote và escape sequence.
- Unicode surrogate pair và ký tự điều khiển.
- Number token, exponent và dấu âm.
- Object/array lồng nhau.
- Property trùng tên.
- String dài và payload bị cắt ở nhiều vị trí.
- Polymorphic type ID.
- Payload sát parser constraints.

Kết quả mong đợi:

- Parse thành công với dữ liệu hợp lệ.
- Từ chối bằng exception có kiểm soát với dữ liệu không hợp lệ.
- Không treo vô hạn.
- Không làm process cạn heap hoặc CPU trong giới hạn test.
- Không tạo side effect trước khi validation hoàn tất.

Fuzz test nên chạy trong process/container có giới hạn CPU và memory. Không chạy payload cực đoan không giới hạn trong môi trường developer hoặc production. Khi tìm được input gây lỗi, lưu nó thành regression fixture để lỗi không tái xuất hiện.

## 16. Kiểm thử tương thích producer và consumer

Tương thích có hai chiều:

- **Backward compatibility:** reader mới đọc được payload do writer cũ tạo.
- **Forward compatibility:** reader cũ đọc được payload do writer mới tạo trong phạm vi contract đã định nghĩa.

Với hai schema version, kiểm tra cả bốn đường:

~~~text
Writer V1 ---> Reader V1
Writer V1 ---> Reader V2
Writer V2 ---> Reader V1
Writer V2 ---> Reader V2
~~~

Ma trận:

| Writer | Reader | Cần xác nhận |
|---|---|---|
| V1 | V1 | Hành vi nền |
| V1 | V2 | Default cho field mới, alias cho tên cũ, chuyển đổi kiểu |
| V2 | V1 | Unknown field, enum mới, kiểu JSON thay đổi |
| V2 | V2 | Hợp đồng hiện tại |

Không giả định thêm field luôn tương thích. Nếu reader cũ bật FAIL_ON_UNKNOWN_PROPERTIES, field mới có thể làm nó thất bại. Nếu reader mới thêm field bắt buộc, payload cũ có thể không còn đọc được. Tương thích phụ thuộc cả cấu hình mapper và cách consumer dùng dữ liệu.

## 17. Golden fixtures cho các phiên bản cũ

Lưu payload đại diện do release trước tạo ra trong test resources:

~~~text
src/test/resources/contracts/
    event-v1.json
    event-v2.json
    order-v1.json
    order-v2.json
    legacy-null-values.json
    legacy-enum-values.json
~~~

Mỗi fixture nên có metadata thể hiện producer/schema version, message type, cấu hình liên quan nếu cần và kết quả domain mong đợi.

Test reader hiện tại với mọi fixture còn được hỗ trợ. Khi thay DTO hoặc mapper configuration, fixture giúp phát hiện regression với dữ liệu lịch sử, message còn nằm trong broker hoặc dữ liệu restore từ backup.

Không cập nhật fixture cũ chỉ để test mới chạy qua nếu chưa xác định đó là thay đổi contract có chủ đích. Nếu hành vi phải thay đổi, tạo fixture version mới và ghi rõ migration.

## 18. Schema evolution và dual-read, single-write

Những thay đổi cần có test tương thích:

- Thêm field optional và default.
- Đổi tên field nhưng vẫn đọc tên cũ.
- Ngừng ghi field cũ nhưng tiếp tục đọc trong giai đoạn chuyển tiếp.
- Đổi int sang long hoặc number sang string.
- Thêm enum constant.
- Đổi cấu trúc object lồng nhau.
- Thay array bằng object hoặc ngược lại.
- Thay đổi null/missing semantics.

Ví dụ dùng @JsonAlias để đọc cả tên cũ và tên mới, nhưng chỉ ghi tên chuẩn:

~~~java
class Customer {
    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }
}
~~~

~~~java
@Test
void readsLegacyNameAndWritesCanonicalName() throws Exception {
    Customer customer = mapper.readValue(
        "{\"name\":\"Lan\"}",
        Customer.class
    );

    assertEquals("Lan", customer.getDisplayName());

    JsonNode output = mapper.readTree(
        mapper.writeValueAsString(customer)
    );

    assertEquals("Lan", output.path("displayName").asText());
    assertFalse(output.has("name"));
}
~~~

Giữ fixture legacy trong thời gian dữ liệu cũ còn có thể được replay hoặc restore. Chỉ bỏ alias/adapter khi đã xác nhận không còn producer hoặc dữ liệu nào cần nó.

## 19. Tương thích các Jackson artifact

Jackson gồm nhiều artifact: jackson-core, jackson-annotations, jackson-databind, các jackson-dataformat module và các datatype module như jsr310/jdk8.

Các artifact cần được căn chỉnh theo ma trận tương thích của Jackson. Không trộn tùy tiện Core 2.x, Databind 2.y và dataformat module 2.z chỉ vì project compile thành công.

Dùng Jackson BOM trong Maven:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson</groupId>
      <artifactId>jackson-bom</artifactId>
      <version>YOUR_JACKSON_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo các Jackson dependency mà không lặp version ở từng artifact. Với Gradle, dùng platform/BOM tương ứng.

Tên version trong ví dụ là placeholder. Chọn phiên bản đã được dự án phê duyệt và kiểm tra dependency tree thực tế sau khi build. Framework hoặc dependency bắc cầu có thể kéo thêm version khác nếu không được quản lý tập trung.

## 20. Kiểm thử nâng cấp Jackson

Một lần nâng cấp có thể thay đổi API, default feature, coercion/null behavior, serializer/deserializer, parser constraints, thông báo lỗi, module registration hoặc format-specific behavior.

Quy trình kiểm thử nâng cấp:

1. Ghi lại Core, Annotations, Databind và dataformat module versions trước khi nâng cấp.
2. Xác định DTO, mapper, producer và consumer chịu ảnh hưởng.
3. Giữ golden fixtures của các phiên bản còn được hỗ trợ.
4. Nâng dependency bằng BOM để căn chỉnh artifact.
5. Chạy syntax, mapping, null, numeric và resource-limit tests.
6. Chạy cross-version contract tests.
7. Chạy round-trip cho các kiểu quan trọng.
8. Chạy malformed/adversarial payload tests.
9. Chạy integration tests với producer/consumer hoặc fixture đã lưu.
10. Chạy load test cho payload lớn và parser constraints.
11. So sánh output, error category, latency, allocation và memory.
12. Canary hoặc rollout theo nhóm consumer nếu thay đổi ảnh hưởng message production.

Không chỉ dựa vào compile hoặc unit test đơn giản. Thay đổi default có thể khiến ứng dụng vẫn compile nhưng đọc dữ liệu cũ khác đi.

## 21. Kiểm thử module và format compatibility

Nếu hệ thống dùng nhiều định dạng, test riêng từng factory:

| Định dạng | Factory/Mapper | Điều cần kiểm tra |
|---|---|---|
| JSON | JsonFactory/ObjectMapper | Syntax, coercion, duplicate, constraints |
| XML | XmlFactory/XmlMapper | Root, namespace, DTD/entity policy, attributes, collections |
| YAML | YAMLFactory/YAMLMapper | Scalar typing, aliases/anchors, nesting, duplicate |
| Smile | SmileFactory | Header, format detection, round-trip, fixtures |
| CBOR | CBORFactory | Numeric types, byte strings, tags, cross-implementation |
| CSV | CsvFactory/CsvMapper | Header, column order, quoting, null, schema |

Một DTO round-trip đúng trong JSON không chứng minh nó round-trip đúng trong XML hoặc CBOR. Annotation, type representation và format-specific feature có thể khác nhau.

Nếu lưu binary payload lâu dài, giữ format identifier, schema version và producer version cùng metadata message. Không dựa vào byte đầu tiên để đoán format nếu protocol không định nghĩa điều đó.

## 22. Kiểm thử XML và YAML an toàn

Khi hệ thống hỗ trợ format không phải JSON, input không đáng tin cậy cần test đặc thù:

- XML: DTD và external entity policy, entity expansion, document size và nesting.
- YAML: alias/anchor expansion, nesting, duplicate keys và scalar coercion.
- CSV: số cột, độ dài cell, quoting, delimiter và row count.

Không giả định parser constraint của JSON tự động áp dụng giống hệt cho XML/YAML/CSV. Mỗi factory/module có cấu hình và rủi ro riêng. Kiểm tra tài liệu đúng phiên bản và viết test trên mapper production.

Đặc biệt, XML external entity và YAML alias expansion có thể gây rủi ro ngoài phạm vi JSON. Nếu ứng dụng không cần tính năng đó, tắt hoặc giới hạn theo khả năng của module.

## 23. Kiểm thử boundary API và thông báo lỗi

Lỗi parser/mapping từ request thường được ánh xạ thành HTTP 400. Validation nghiệp vụ có thể là 400 hoặc 422 tùy contract. Lỗi I/O hoặc lỗi nội bộ không nên bị chuyển nhầm thành lỗi dữ liệu client.

Test controller/service cần xác nhận:

- Status code phù hợp.
- Error code ổn định.
- Không trả stack trace hoặc raw payload.
- Không có side effect khi parse/validation thất bại.
- Correlation ID có mặt để tra log.
- Metrics đếm lỗi theo category.

Ví dụ response:

~~~json
{
  "errorCode": "INVALID_JSON",
  "message": "Request body is not valid JSON",
  "correlationId": "C-123"
}
~~~

Thông báo cho client nên hữu ích nhưng không tiết lộ classpath, file path, SQL, secret hoặc nội dung nhạy cảm. Log nội bộ có thể giữ vị trí lỗi đã được lọc và correlation ID; không ghi toàn bộ payload theo mặc định.

## 24. Kiểm thử streaming và memory

Streaming parser giúp không materialize toàn bộ file, nhưng ứng dụng vẫn có thể giữ dữ liệu không giới hạn trong List, cache, queue hoặc future. Load test cần xác nhận:

- Số record tăng nhưng heap không tăng tuyến tính theo tổng record khi pipeline đã ổn định.
- Queue có giới hạn và producer chịu backpressure khi consumer chậm.
- Batch được clear sau khi persist.
- Record lỗi không bị giữ vô hạn trong quarantine buffer.
- Một record quá lớn bị từ chối theo giới hạn.
- Output không được công bố nếu generator thất bại giữa chừng.

Không dùng System.gc() trong test như bằng chứng memory đã được giải phóng. GC là quyết định của JVM. Quan sát heap, allocation và retained references bằng JFR hoặc heap dump.

Với JSON array, lỗi cú pháp giữa document thường khiến parser không thể tiếp tục an toàn. Nếu cần cách ly lỗi cú pháp theo record, NDJSON cung cấp ranh giới dòng độc lập, miễn producer tuân thủ một JSON value trên mỗi dòng.

## 25. Fuzz, timeout và resource exhaustion tests

Một test input lớn nên chạy với timeout và memory budget được kiểm soát. JUnit timeout có thể dùng làm guard cơ bản:

~~~java
@Test
@Timeout(value = 2, unit = TimeUnit.SECONDS)
void rejectsExcessiveNestingPromptly() {
    assertThrows(
        JsonProcessingException.class,
        () -> constrainedMapper.readTree(nestedArray(10_000))
    );
}
~~~

Timeout trong unit test phụ thuộc máy CI; không đặt ngưỡng quá sát khiến test chập chờn. Với memory test, dùng forked process/container có heap limit và giới hạn tài nguyên riêng.

Tách fuzz/load tests khỏi suite chạy nhanh. Lưu mọi input đã phát hiện bug thành regression fixture. Khi nâng cấp Jackson, chạy lại bộ fixture này để phát hiện lỗi hồi quy.

## 26. Metrics theo dõi regression sau deploy

Sau khi nâng cấp hoặc đổi cấu hình, nên theo dõi:

- Tỷ lệ lỗi parse và mapping.
- Tỷ lệ unknown property/enum.
- Tỷ lệ payload vượt constraints.
- Số message theo schema version.
- Số message đi qua alias hoặc legacy adapter.
- Payload size trung bình và p95/p99.
- Parse/deserialization latency p50/p95/p99.
- Allocation rate, heap và GC pause.
- Số lần retry và quarantine.

Metric label nên có cardinality thấp, chẳng hạn format, schema version, producer type và error category. Không dùng message ID hoặc user ID làm metric label; đưa định danh đó vào log/trace có kiểm soát.

Một đợt nâng cấp có thể không làm test thất bại nhưng khiến unknown-field hoặc coercion rate tăng trong production. Metrics giúp phát hiện sớm configuration drift.

## 27. Ma trận kiểm thử tổng hợp

| Nhóm | Test tiêu biểu | Loại kiểm thử |
|---|---|---|
| Syntax | Missing brace, invalid escape, trailing comma | Unit |
| Mapping | Wrong token shape, unknown property | Unit/contract |
| Null/missing | Missing creator field, explicit null, empty string | Unit |
| Numeric | Integer boundary, BigInteger, BigDecimal scale | Unit/property |
| Enum/subtype | Unknown enum, unknown subtype | Unit/security |
| Duplicate | Root, nested và escaped duplicate | Unit |
| Resource | Depth, string, number, request-size limit | Unit/load |
| Large file | Streaming, bounded queue, memory stability | Integration/load |
| Side effect | Invalid record không commit | Integration |
| Version | V1 writer với V2 reader và ngược lại | Contract |
| Jackson upgrade | Fixture cũ qua dependency mới | Compatibility |
| Data format | JSON/XML/YAML/Smile/CBOR/CSV | Integration |
| Fuzz | Unicode, nesting, malformed token | Fuzz |
| Operations | Metrics, error response, quarantine | Integration |

Không phải dự án nào cũng dùng mọi định dạng hoặc cần mọi loại test. Chọn theo mapper và nguồn dữ liệu thực tế, nhưng không bỏ qua kiểm thử dữ liệu lỗi và giới hạn tài nguyên ở boundary không đáng tin cậy.

## 28. Quy trình nâng cấp và phát hành an toàn

Một quy trình thực tế:

1. Ghi lại Jackson Core, Annotations, Databind và dataformat module versions hiện tại.
2. Xác định DTO, mapper, producer và consumer chịu ảnh hưởng.
3. Giữ golden fixtures của các phiên bản còn được hỗ trợ.
4. Nâng dependency bằng BOM.
5. Chạy syntax, mapping, null, numeric và resource-limit tests.
6. Chạy cross-version contract tests.
7. Chạy test cho từng data format đang sử dụng.
8. Chạy fuzz/load tests trong môi trường có giới hạn.
9. So sánh error rate, output, latency, allocation và heap.
10. Canary hoặc rollout theo nhóm consumer.
11. Theo dõi schema version và lỗi legacy sau deploy.
12. Chỉ bỏ adapter/alias cũ khi dữ liệu cũ không còn cần hỗ trợ.

Nếu producer và consumer được deploy độc lập, không đổi format hoặc schema mặc định trước khi các consumer cần thiết đã hiểu hợp đồng mới. Dùng versioned topic/endpoint hoặc content negotiation khi cần giai đoạn chuyển tiếp.

## 29. Những lỗi thường gặp

### Chỉ test payload hợp lệ

Không phát hiện parser lỗi, mapping mismatch, coercion ngoài ý muốn hoặc dữ liệu quá lớn. Bổ sung negative và boundary tests.

### Chỉ assert exception

Không biết hệ thống có thực hiện side effect trước lỗi hay không. Kiểm tra cả trạng thái database, output và queue.

### Dùng parser mặc định trong test nhưng production có custom config

Test không phản ánh behavior thực tế. Inject đúng mapper/factory production.

### Không giới hạn string, number và nesting

Payload có thể gây cạn heap hoặc CPU dù cú pháp hợp lệ. Dùng StreamReadConstraints và giới hạn transport/domain.

### Bật permissive coercion không có hợp đồng

Client gửi string, decimal hoặc token sai shape vẫn có thể được chuyển đổi. Cấu hình strict/tolerant rõ ràng.

### Bật polymorphic default typing rộng

Có thể cho phép tạo subtype ngoài dự kiến từ dữ liệu không tin cậy. Dùng allowlist và test âm.

### Chỉ kiểm thử phiên bản Jackson mới với dữ liệu mới

Không phát hiện dữ liệu lịch sử bị lỗi sau nâng cấp. Dùng golden fixtures từ release cũ.

### Chỉ căn chỉnh Databind mà quên dataformat module

Dependency lệch version có thể gây lỗi runtime hoặc hành vi không tương thích. Dùng BOM và kiểm tra dependency tree.

### Coi JSON, XML và CBOR có cùng behavior

Mỗi module có representation và parser policy riêng. Test từng format đang sử dụng.

### Cập nhật fixture cũ để làm test xanh mà không xem xét contract

Có thể che giấu breaking change. Giữ fixture lịch sử và tạo fixture version mới khi contract thực sự thay đổi.

## 30. Checklist trước khi phát hành

- [ ] Có test JSON syntax hợp lệ và sai cú pháp.
- [ ] Có test mapping sai shape, unknown field và coercion.
- [ ] Có test missing, null, empty và default.
- [ ] Có test Integer/Long boundaries, BigInteger và BigDecimal.
- [ ] Có test enum/subtype lạ và allowlist.
- [ ] Có test duplicate member names và alias collisions.
- [ ] Có parser constraints cho nesting, string và number.
- [ ] Có giới hạn request/file/record size ở boundary.
- [ ] Có test không xảy ra side effect khi parse/validation thất bại.
- [ ] Có test streaming và memory với dữ liệu lớn.
- [ ] Có bounded queue, batch và backpressure nếu xử lý song song.
- [ ] Có golden fixtures cho schema/producer versions cũ.
- [ ] Có ma trận writer-reader hai chiều.
- [ ] Jackson artifacts được căn chỉnh bằng BOM/dependency management.
- [ ] Có test cho từng data format đang sử dụng.
- [ ] Có fuzz/load tests chạy trong môi trường giới hạn.
- [ ] Có metrics cho lỗi, version, latency, size và memory.
- [ ] Error response/log không làm lộ payload hoặc secret.

## 31. Kết luận

Kiểm thử dữ liệu Jackson cần bao phủ dữ liệu sai cú pháp, sai kiểu, null/missing, số ngoài biên, duplicate, enum/subtype không biết và payload có kích thước hoặc độ sâu bất thường. StreamReadConstraints, strict duplicate detection và coercion policy giúp đặt giới hạn ở tầng parser, nhưng vẫn cần giới hạn request/record và validation nghiệp vụ. Với dữ liệu không đáng tin cậy, polymorphic typing phải có allowlist. Tương thích phiên bản cần được kiểm tra bằng golden fixtures và ma trận writer-reader cũ/mới; các Jackson artifact và dataformat module phải được căn chỉnh phiên bản. Sau nâng cấp, chạy contract, security, load và integration tests rồi theo dõi error rate, schema version, latency, allocation và heap. Một mapper đáng tin cậy phải đọc đúng dữ liệu hợp lệ, từ chối dữ liệu lỗi có kiểm soát và tiếp tục hỗ trợ các payload cũ còn nằm trong thời hạn hợp đồng.
