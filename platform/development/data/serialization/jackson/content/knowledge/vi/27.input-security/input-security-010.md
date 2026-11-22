# Không dùng bỏ qua lỗi ánh xạ như một biện pháp kiểm tra dữ liệu

Khi nhận JSON từ client hoặc một hệ thống khác, Jackson có thể gặp nhiều loại dữ liệu không phù hợp: property không được biết, sai kiểu, giá trị ngoài phạm vi, enum mới, subtype chưa đăng ký hoặc cấu trúc object không đúng hợp đồng. Ứng dụng cần quyết định trường hợp nào được chấp nhận, trường hợp nào phải từ chối và trường hợp nào có thể bỏ qua theo một quy tắc tương thích đã công bố.

Một lỗi thiết kế thường gặp là bật chế độ đọc quá dễ dãi, bỏ qua lỗi ánh xạ hoặc bắt exception rồi tạo object với giá trị mặc định. Cách làm này có thể khiến request sai được xem như hợp lệ. Dữ liệu bị bỏ mất, trạng thái bị thay đổi ngoài ý muốn và lỗi chỉ xuất hiện ở một bước nghiệp vụ xa hơn.

Trong chương **Bảo mật đầu vào**, nguyên tắc quan trọng là: **khả năng bỏ qua một trường không thay thế cho việc xác thực dữ liệu**. Jackson chịu trách nhiệm phân tích và ánh xạ JSON; validation chịu trách nhiệm kiểm tra các điều kiện của dữ liệu; service/domain layer chịu trách nhiệm kiểm tra quyền và quy tắc nghiệp vụ. Mỗi lớp cần giữ đúng trách nhiệm của mình.

## 1. Bỏ qua lỗi ánh xạ có thể che giấu điều gì?

Giả sử endpoint cập nhật hồ sơ nhận request:

~~~json
{
  "displayName": "An",
  "age": "unknown",
  "isAdmin": true,
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

DTO chỉ có displayName, age và timeZone. Nếu ứng dụng bật bỏ qua property không biết, trường isAdmin có thể bị loại bỏ mà không có cảnh báo. Tuy nhiên, age vẫn sai kiểu và cần được xử lý theo hợp đồng.

Một kiểu xử lý nguy hiểm hơn là custom deserializer bắt mọi exception rồi trả về object mặc định:

~~~java
try {
    return readProfile(parser);
} catch (Exception ignored) {
    return new Profile();
}
~~~

Kết quả có thể là request bị sai nhưng API vẫn trả thành công. Người gọi không biết field nào bị loại bỏ hoặc không được đọc. Hệ thống cũng có thể ghi đè dữ liệu hợp lệ bằng giá trị mặc định.

Những hậu quả thường gặp:

- **Mất dữ liệu âm thầm**: property mới hoặc sai tên bị bỏ qua.
- **Sai trạng thái**: giá trị lỗi bị thay bằng null, 0, false hoặc enum mặc định.
- **Lỗi bị trì hoãn**: vấn đề chỉ xuất hiện khi tính toán, lưu database hoặc chạy nghiệp vụ.
- **Khó phát hiện tấn công**: payload có field bất thường không tạo ra dấu hiệu cảnh báo.
- **Hợp đồng không rõ ràng**: client không biết field nào được hỗ trợ và field nào đã bị bỏ qua.
- **Khó tương thích phiên bản**: producer và consumer lệch schema nhưng hệ thống vẫn xử lý như thể dữ liệu đã đầy đủ.

Bỏ qua một trường chỉ hợp lý khi hợp đồng xác định rõ trường đó không ảnh hưởng đến kết quả xử lý và việc bỏ qua là một phần của chính sách tương thích.

## 2. Phân biệt unknown property với lỗi ánh xạ của property đã biết

Hai trường hợp này không giống nhau.

### 2.1. Property không được biết

~~~json
{
  "name": "An",
  "legacyLabel": "old-client"
}
~~~

Nếu class Java chỉ có name, legacyLabel là property không được ánh xạ. Ứng dụng có thể:
- Từ chối vì request chứa field ngoài hợp đồng.
- Bỏ qua vì API cho phép consumer cũ nhận field bổ sung.
- Thu thập field vào một extension map được định nghĩa rõ.
- Ghi nhận metric về field lạ mà không lưu giá trị.

### 2.2. Property đã biết nhưng sai kiểu

~~~json
{
  "name": "An",
  "age": "thirty"
}
~~~

Nếu age là Integer, đây là lỗi ánh xạ của một property đã biết. Bỏ qua unknown property không giải quyết trường hợp này. Nếu Jackson được cấu hình cho phép coercion hoặc custom deserializer nuốt lỗi, giá trị có thể bị chuyển đổi hoặc thay thế ngoài ý muốn.

### 2.3. Property đã biết nhưng giá trị không hợp lệ

~~~json
{
  "name": "An",
  "age": -10
}
~~~

JSON hợp lệ về cú pháp và age có kiểu số nguyên, nhưng giá trị âm có thể vi phạm hợp đồng. Đây là vấn đề validation, không phải unknown property.

| Trường hợp | Ví dụ | Trách nhiệm chính |
|---|---|---|
| JSON sai cú pháp | Thiếu dấu phẩy, string chưa đóng | JSON parser |
| Unknown property | agee thay vì age | Chính sách schema/unknown field |
| Sai kiểu | age là chuỗi không chuyển được | Jackson data binding |
| Coercion không mong muốn | "30" tự chuyển thành số 30 | Cấu hình coercion |
| Giá trị ngoài miền hợp lệ | age = -10 | Bean Validation/domain validation |
| Thiếu property bắt buộc | Không có name | Kiểm tra presence/creator/validation |
| Field có thể ánh xạ nhưng không được phép sửa | isAdmin | DTO allowlist và authorization |

Không nên gộp tất cả thành một khái niệm "lỗi JSON". Mỗi loại cần chính sách riêng.

## 3. FAIL_ON_UNKNOWN_PROPERTIES và chế độ strict

Jackson Databind có DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES. Khi feature được bật, Jackson báo lỗi nếu gặp property không thể ánh xạ và không được xử lý bởi any-setter, ignore rule hoặc problem handler.

Có thể cấu hình tường minh:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
~~~

Đây thường là lựa chọn phù hợp cho request API cần hợp đồng chặt chẽ. Nếu client gửi agee thay vì age, request thất bại ngay tại ranh giới JSON.

### 3.1. @JsonIgnoreProperties(ignoreUnknown = true)

Annotation sau cho phép bỏ qua property không biết trên class được đánh dấu:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class ProfileRequest {
    private String displayName;
    private Integer age;

    // Getter và setter.
}
~~~

Nó hữu ích khi consumer cần tương thích với producer có thể bổ sung field. Tuy nhiên, annotation này cũng có thể che lỗi đánh máy hoặc việc client gửi sai tên property.

Không nên gắn ignoreUnknown = true lên mọi request DTO chỉ để tránh exception. Với endpoint nhạy cảm, từ chối field ngoài hợp đồng thường giúp phát hiện lỗi tích hợp và payload bất thường sớm hơn.

### 3.2. Bỏ qua unknown property không có nghĩa là bỏ qua mọi lỗi

ignoreUnknown = true chỉ áp dụng cho property không được nhận diện. Nó không tự biến mọi sai kiểu của property đã biết thành dữ liệu hợp lệ.

Ví dụ:

~~~json
{
  "displayName": "An",
  "age": "not-a-number",
  "futureField": "ignored"
}
~~~

futureField có thể bị bỏ qua, nhưng age vẫn cần được ánh xạ theo cấu hình coercion và kiểu Java. Nếu age không thể chuyển đổi, Jackson vẫn có thể ném lỗi mapping.

## 4. FAIL_ON_IGNORED_PROPERTIES và field bị đánh dấu bỏ qua

Unknown property khác với property đã biết nhưng được đánh dấu ignore.

Ví dụ:

~~~java
public class AccountRequest {
    private String username;

    @JsonIgnore
    private boolean internalFlag;
}
~~~

Property internalFlag là một property mà model biết, nhưng ứng dụng chủ động không cho data binding vào đó.

DeserializationFeature.FAIL_ON_IGNORED_PROPERTIES có thể yêu cầu Jackson báo lỗi nếu input vẫn gửi property đã bị đánh dấu ignore:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_IGNORED_PROPERTIES)
        .build();
~~~

Điều này hữu ích khi ứng dụng muốn phát hiện client cố gửi một field không được phép hoặc đã bị loại khỏi contract.

Tuy nhiên, annotation và visibility của property có thể ảnh hưởng cách Jackson nhận diện field. Hãy viết test cho chính DTO và cấu hình đang dùng. Đừng coi FAIL_ON_IGNORED_PROPERTIES là cơ chế authorization; nó chỉ giúp phát hiện một dạng input mapping không mong muốn.

## 5. Cấu hình strict cho request JSON

Một cấu hình có thể dùng làm điểm khởi đầu cho API cần kiểm soát input:

~~~java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

ObjectMapper mapper = JsonMapper.builder(factory)
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_IGNORED_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
        .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
        .enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE)
        .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
        .build();
~~~

Các feature có ý nghĩa:

| Feature | Mục đích |
|---|---|
| STRICT_DUPLICATE_DETECTION | Từ chối key trùng trong cùng object |
| FAIL_ON_UNKNOWN_PROPERTIES | Từ chối property không được ánh xạ |
| FAIL_ON_IGNORED_PROPERTIES | Từ chối property được đánh dấu ignore nhưng vẫn xuất hiện trong input |
| FAIL_ON_NULL_FOR_PRIMITIVES | Không tự biến JSON null thành giá trị mặc định của primitive |
| FAIL_ON_MISSING_CREATOR_PROPERTIES | Từ chối creator property bắt buộc bị thiếu theo cấu hình creator |
| FAIL_ON_NULL_CREATOR_PROPERTIES | Từ chối null cho creator property theo cấu hình |
| FAIL_ON_TRAILING_TOKENS | Từ chối token dư sau root value |
| FAIL_ON_NUMBERS_FOR_ENUMS | Không dùng số làm enum ordinal |
| FAIL_ON_INVALID_SUBTYPE | Từ chối polymorphic type id không hợp lệ |
| ACCEPT_FLOAT_AS_INT bị tắt | Không âm thầm chuyển số thập phân thành số nguyên |

Đây là điểm khởi đầu, không phải một cấu hình phù hợp tuyệt đối cho mọi hệ thống. Một số feature chỉ áp dụng cho creator properties; ví dụ FAIL_ON_MISSING_CREATOR_PROPERTIES không tự kiểm tra mọi field mutable có setter. Với property bắt buộc trên bean thông thường, cần presence check hoặc validation riêng.

Hãy kiểm tra phiên bản Jackson đang dùng và test từng feature trên DTO thật. Các module jackson-core và jackson-databind nên được quản lý cùng một dòng phiên bản tương thích.

## 6. Kiểm soát coercion thay vì chấp nhận mọi kiểu gần đúng

Một số cấu hình Jackson cho phép chuyển đổi linh hoạt giữa scalar types. Ví dụ, chuỗi "42" có thể được chuyển thành số nguyên trong một số ngữ cảnh. Điều này có thể tiện cho dữ liệu cũ, nhưng cũng làm contract khó đoán.

Nếu API yêu cầu age phải là JSON number nguyên, hãy từ chối string và float thay vì dựa vào coercion.

Với Jackson có hỗ trợ CoercionConfig, có thể cấu hình:

~~~java
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.type.LogicalType;

mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
        )
        .setCoercion(
                CoercionInputShape.Float,
                CoercionAction.Fail
        )
        .setCoercion(
                CoercionInputShape.EmptyString,
                CoercionAction.Fail
        );
~~~

Cấu hình này thể hiện chính sách cho kiểu integer. Có thể cần cấu hình riêng cho Boolean, Enum, Textual hoặc các logical type khác theo contract.

Không nên tắt coercion một cách máy móc nếu API cần chấp nhận định dạng legacy đã công bố. Thay vào đó, định nghĩa rõ kiểu JSON được phép cho từng field và viết test cho các input như:

~~~json
{"age": 42}
~~~

~~~json
{"age": "42"}
~~~

~~~json
{"age": 42.5}
~~~

~~~json
{"age": null}
~~~

Nếu contract chỉ chấp nhận số nguyên, chỉ ví dụ đầu tiên được phép qua bước mapping.

## 7. Không dùng giá trị mặc định để che lỗi

Các primitive Java có giá trị mặc định:
- int: 0
- long: 0
- boolean: false
- double: 0.0

Nếu JSON thiếu property hoặc gửi null, một số đường ánh xạ có thể để lại giá trị mặc định tùy kiểu, creator và cấu hình. Khi 0 hoặc false cũng là giá trị hợp lệ, ứng dụng khó biết client có gửi field hay không.

Ví dụ DTO mutable:

~~~java
public class TransferRequest {
    private long amount;
    private boolean approved;

    // Getter và setter.
}
~~~

Nếu amount là bắt buộc, chỉ nhìn giá trị 0 sau deserialize không đủ để biết:
- Client gửi amount = 0.
- Client không gửi amount.
- Client gửi null và cấu hình cho phép primitive default.
- Một logic khác đã gán default.

Dùng wrapper và validation/presence rõ ràng:

~~~java
public class TransferRequest {

    @NotNull
    @Positive
    private Long amount;

    @NotNull
    private Boolean approved;

    // Getter và setter.
}
~~~

Với wrapper, null có thể biểu diễn việc thiếu hoặc null input. Nếu cần phân biệt hai trường hợp, hãy giữ presence flag trong custom deserializer hoặc dùng constructor/creator có kiểm soát.

Không nên viết:

~~~java
try {
    request.setAmount(parser.getLongValue());
} catch (Exception ignored) {
    request.setAmount(0L);
}
~~~

Cách đúng là để mapping error được truyền ra ngoài hoặc tạo exception có ngữ cảnh:

~~~java
if (parser.currentToken() != JsonToken.VALUE_NUMBER_INT) {
    throw JsonMappingException.from(
            parser,
            "Property 'amount' must be an integer"
    );
}
~~~

## 8. Bỏ qua unknown property không phải validation

Một request có thể không chứa property lạ nhưng vẫn hoàn toàn không hợp lệ:

~~~json
{
  "displayName": "",
  "age": -20
}
~~~

Tất cả field đều được biết và có kiểu đúng. FAIL_ON_UNKNOWN_PROPERTIES không phát hiện displayName rỗng hay age âm.

Dùng Bean Validation để kiểm tra constraint:

~~~java
public class ProfileRequest {

    @NotBlank
    private String displayName;

    @NotNull
    @Min(0)
    @Max(130)
    private Integer age;

    // Getter và setter.
}
~~~

Trong Spring MVC:

~~~java
@PostMapping("/profiles")
public ResponseEntity<Void> createProfile(
        @Valid @RequestBody ProfileRequest request
) {
    profileService.create(request);
    return ResponseEntity.noContent().build();
}
~~~

Jackson đọc JSON thành DTO. Sau đó Bean Validation kiểm tra constraint trước khi method xử lý tiếp tục theo cơ chế framework.

Phân chia trách nhiệm:

- Jackson kiểm tra cú pháp, token, kiểu đích và khả năng ánh xạ.
- Bean Validation kiểm tra constraint trên dữ liệu đã ánh xạ.
- Service/domain kiểm tra điều kiện nghiệp vụ và trạng thái hệ thống.
- Authorization kiểm tra người gọi có quyền thực hiện hành động hay không.

Không dùng việc Jackson bỏ qua field như một cách thay thế bất kỳ lớp nào trong số này.

## 9. Unknown enum value cũng là một chính sách tương thích

Enum có thể nhận giá trị mới khi producer được nâng cấp:

~~~json
{
  "status": "ON_HOLD"
}
~~~

Consumer cũ không có constant ON_HOLD. Mặc định strict thường giúp phát hiện sự không tương thích.

Jackson có các lựa chọn:
- Từ chối unknown enum value.
- Bật READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE và đánh dấu một constant bằng @JsonEnumDefaultValue.
- Bật READ_UNKNOWN_ENUM_VALUES_AS_NULL.

Không nên bật fallback global rồi coi đó là validation. Nếu unknown status trở thành UNKNOWN hoặc null, tầng nghiệp vụ phải biết rõ cách xử lý. Không được coi UNKNOWN như PAID, ACTIVE hoặc một trạng thái có quyền thực hiện hành động quan trọng.

Ví dụ enum có fallback tường minh:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(
                DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
        )
        .build();
~~~

Đây là lựa chọn tương thích có chủ đích. Nếu giá trị mới phải bị từ chối vì ảnh hưởng an toàn hoặc tài chính, giữ strict mode.

## 10. Unknown polymorphic subtype không nên bị biến thành null âm thầm

Với hierarchy đa hình, type id chọn class concrete:

~~~json
{
  "type": "payment-card",
  "reference": "PAY-001"
}
~~~

Nếu consumer chưa biết type id mới, Jackson có thể báo InvalidTypeIdException. FAIL_ON_INVALID_SUBTYPE giúp giữ hành vi strict.

Nếu tắt feature này, unresolved subtype có thể dẫn đến null trong một số trường hợp. Điều đó có thể làm lỗi xuất hiện muộn khi code gọi method trên object null.

Nếu hệ thống cần tương thích với subtype mới, hãy dùng UnknownEvent/UnknownPayment chuyên dụng hoặc defaultImpl có semantics rõ ràng. Giữ lại type id và payload cần thiết để xử lý sau. Không ánh xạ subtype mới về một subtype cũ chỉ để tránh exception.

## 11. Duplicate key có thể làm dữ liệu bị diễn giải khác nhau

JSON sau có cùng property xuất hiện hai lần:

~~~json
{
  "role": "user",
  "role": "admin"
}
~~~

Nếu parser không bật strict duplicate detection, hành vi xử lý key trùng có thể phụ thuộc parser hoặc thành phần downstream. Một tầng có thể lấy giá trị đầu, tầng khác lấy giá trị cuối. Sự khác biệt này có thể tạo ra lỗ hổng khi gateway, validator và service không diễn giải cùng một payload.

Bật:

~~~java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();
~~~

Khi key trùng trong cùng object, parser báo lỗi thay vì để nhiều tầng tự chọn cách diễn giải.

Duplicate detection là kiểm tra cấu trúc ở parser. Nó không thay thế validation hoặc authorization.

## 12. Từ chối dữ liệu dư sau root value

Một request được định nghĩa là một JSON document duy nhất nhưng lại chứa hai root value:

~~~text
{"role":"user"} {"role":"admin"}
~~~

Nếu chỉ đọc root value đầu tiên mà không kiểm tra phần còn lại, dữ liệu dư có thể bị bỏ qua ở một tầng và được xử lý ở tầng khác.

Bật:

~~~java
mapper.enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
~~~

Feature này yêu cầu không còn token ngoài root value đã đọc. Nó hữu ích khi API contract yêu cầu chính xác một document.

Nếu giao thức thật sự là JSON sequence hoặc NDJSON, hãy dùng parser/framing phù hợp với giao thức đó thay vì áp dụng quy tắc một root document.

## 13. Unknown property và @JsonAnySetter

Một số API có vùng extension được công bố rõ để producer bổ sung metadata. Trong trường hợp này, có thể thu thập field mở rộng thay vì bỏ qua tất cả:

~~~java
public class EventEnvelope {

    private String eventId;
    private Map<String, JsonNode> extensions = new LinkedHashMap<>();

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        if (!name.startsWith("x-")) {
            throw new IllegalArgumentException(
                    "Unsupported extension property"
            );
        }

        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> getExtensions() {
        return extensions;
    }
}
~~~

Ví dụ JSON:

~~~json
{
  "eventId": "EVT-100",
  "x-source-region": "ap-southeast-1",
  "x-schema-revision": 3
}
~~~

@JsonAnySetter nhận property chưa được khai báo và cho ứng dụng kiểm tra namespace/allowlist. @JsonAnyGetter cho phép serialize lại map extension nếu contract yêu cầu.

Cần giới hạn:
- Những prefix/key được phép.
- Số lượng extension.
- Kích thước mỗi value.
- Độ sâu object/array.
- Những loại dữ liệu có thể được lưu hoặc chuyển tiếp.

Không nên dùng @JsonAnySetter để thu thập mọi field tùy ý rồi tự động đưa vào entity hoặc câu lệnh database. Extension map là một phần của contract có kiểm soát, không phải cơ chế mass assignment.

## 14. DeserializationProblemHandler không phải bộ validation tổng quát

Jackson có DeserializationProblemHandler để ứng dụng can thiệp vào một số tình huống bất thường, ví dụ unknown property hoặc unknown type id.

Với unknown property, handler có thể trả về true để cho biết tình huống đã được xử lý. Khi đó Jackson không tiếp tục báo lỗi mặc định cho property đó.

Đây là một điểm dễ bị lạm dụng: nếu handler trả true cho mọi property lạ mà không kiểm tra, ứng dụng đã vô hiệu hóa một tín hiệu quan trọng của contract.

Nếu dùng handler:
- Chỉ chấp nhận những field đã được quy định là extension.
- Kiểm tra tên field bằng allowlist/prefix rõ ràng.
- Tiêu thụ value đúng cách nếu handler quyết định bỏ qua nó.
- Ghi metric an toàn về loại field bất thường.
- Với field không được phép, để handler từ chối hoặc ném mapping exception.
- Không ghi raw value vào log.

Handler giải quyết một điểm mở rộng trong quy trình deserialize. Nó không thay thế Bean Validation, authorization hoặc quy tắc domain.

## 15. Đặc biệt chú ý mass assignment

Bỏ qua unknown property không bảo vệ ứng dụng khỏi mass assignment.

Mass assignment xảy ra khi request được ánh xạ trực tiếp vào object có nhiều field nội bộ, và người gọi có thể gửi những field mà họ không được phép thay đổi.

Ví dụ entity:

~~~java
public class UserAccount {
    private Long id;
    private String displayName;
    private String email;
    private boolean admin;
    private boolean locked;
    private BigDecimal creditLimit;

    // Getter và setter.
}
~~~

Nếu API deserialize request trực tiếp vào UserAccount, các field admin, locked hoặc creditLimit vẫn là property đã biết. FAIL_ON_UNKNOWN_PROPERTIES không từ chối chúng.

Giải pháp là dùng DTO chỉ chứa field được phép cập nhật:

~~~java
public record UpdateProfileRequest(
        @NotBlank String displayName,
        @Email String email
) {
}
~~~

Sau đó service cập nhật có chủ đích:

~~~java
public void updateProfile(
        UserAccount account,
        UpdateProfileRequest request
) {
    account.setDisplayName(request.displayName());
    account.setEmail(request.email());
}
~~~

Các field quyền hạn, trạng thái khóa và giới hạn tín dụng được thay đổi qua use case riêng có authorization phù hợp.

Đây là nguyên tắc allowlist: chỉ dữ liệu được công bố trong request DTO mới có thể đi vào thao tác cập nhật. Từ chối unknown property vẫn hữu ích, nhưng không thay thế DTO và authorization.

## 16. Chọn chính sách theo loại endpoint

Không phải mọi JSON consumer đều cần strictness giống nhau.

| Loại đầu vào | Chính sách thường phù hợp | Lý do |
|---|---|---|
| API cập nhật tài khoản/thanh toán | Strict unknown field, type và validation | Sai field có thể ảnh hưởng quyền hoặc dữ liệu quan trọng |
| Internal command có schema cố định | Strict mapping | Phát hiện producer/consumer lệch phiên bản |
| Event consumer cần forward compatibility | Cho phép extension có kiểm soát hoặc UnknownEvent | Có thể nhận và chuyển tiếp event chưa hiểu |
| Analytics ingest với schema mở | Thu thập extension hoặc lưu raw payload trong vùng kiểm soát | Schema có thể tiến hóa thường xuyên |
| Public webhook | Xác thực signature, giới hạn payload và validate schema | Nguồn bên ngoài không đáng tin cậy |
| Configuration file nội bộ | Strict unknown property thường hữu ích | Bắt lỗi đánh máy trong cấu hình |

Nếu chọn bỏ qua field, hãy trả lời:
- Field nào được phép bỏ qua?
- Vì sao bỏ qua không làm sai kết quả?
- Có cần lưu hoặc chuyển tiếp field đó không?
- Có metric để biết producer đã bắt đầu gửi field mới không?
- Khi nào chính sách bỏ qua sẽ được gỡ bỏ?

Một cờ ignoreUnknown toàn cục thường quá rộng cho nhiều loại contract khác nhau.

## 17. Xử lý lỗi mà không biến chúng thành thành công giả

Không nên viết:

~~~java
public Profile readProfile(String json) {
    try {
        return mapper.readValue(json, Profile.class);
    } catch (JsonProcessingException e) {
        logger.warn("Could not read profile");
        return new Profile();
    }
}
~~~

Caller không thể phân biệt profile rỗng thật với request không hợp lệ.

Hãy để lỗi được truyền đến exception handler hoặc trả về một kết quả lỗi tường minh:

~~~java
public Profile readProfile(String json)
        throws JsonProcessingException {

    return mapper.readValue(json, Profile.class);
}
~~~

Tầng API có thể ánh xạ exception thành response 400 với error code và field path an toàn:

~~~json
{
  "code": "INVALID_REQUEST",
  "field": "$.age",
  "message": "Field must be a non-negative integer"
}
~~~

Không đưa toàn bộ payload, raw value hoặc stack trace vào response. Log nội bộ có thể ghi request ID, loại lỗi, path đã lọc và location số.

Nếu ứng dụng thực sự có một trường hợp fallback, hãy biểu diễn nó rõ trong kiểu kết quả, chẳng hạn Success/Rejected hoặc một kiểu UnknownEvent chuyên dụng. Đừng dùng object rỗng làm dấu hiệu cho lỗi.

## 18. Kiểm thử chính sách mapping và validation

Kiểm thử nên chứng minh rằng dữ liệu sai bị từ chối và dữ liệu mở rộng chỉ được chấp nhận trong trường hợp đã công bố.

### 18.1. Unknown property bị từ chối

~~~java
@Test
void rejectsUnknownProperty() {
    String json = """
            {
              "displayName": "An",
              "age": 30,
              "admin": true
            }
            """;

    assertThrows(
            UnrecognizedPropertyException.class,
            () -> strictMapper.readValue(json, ProfileRequest.class)
    );
}
~~~

### 18.2. Sai kiểu của property đã biết vẫn bị từ chối

~~~java
@Test
void rejectsStringForIntegerAge() {
    String json = """
            {
              "displayName": "An",
              "age": "thirty"
            }
            """;

    assertThrows(
            JsonMappingException.class,
            () -> strictMapper.readValue(json, ProfileRequest.class)
    );
}
~~~

### 18.3. Giá trị đúng kiểu nhưng ngoài miền hợp lệ bị validation từ chối

~~~java
@Test
void rejectsNegativeAgeAfterBinding() throws Exception {
    String json = """
            {
              "displayName": "An",
              "age": -10
            }
            """;

    ProfileRequest request =
            strictMapper.readValue(json, ProfileRequest.class);

    Set<ConstraintViolation<ProfileRequest>> violations =
            validator.validate(request);

    assertFalse(violations.isEmpty());
}
~~~

Test này cho thấy mapping thành công không có nghĩa dữ liệu đã hợp lệ.

### 18.4. Duplicate property bị từ chối

~~~java
@Test
void rejectsDuplicateJsonKeys() {
    String json = """
            {
              "role": "user",
              "role": "admin"
            }
            """;

    assertThrows(
            JsonProcessingException.class,
            () -> strictMapper.readValue(json, JsonNode.class)
    );
}
~~~

### 18.5. Root trailing token bị từ chối

~~~java
@Test
void rejectsTrailingRootValue() {
    String json = "{\"name\":\"An\"} {\"name\":\"Binh\"}";

    assertThrows(
            JsonProcessingException.class,
            () -> strictMapper.readValue(json, ProfileRequest.class)
    );
}
~~~

### 18.6. Unknown extension được giữ theo allowlist

~~~java
@Test
void acceptsOnlyDeclaredExtensionNamespace() throws Exception {
    String accepted = """
            {
              "eventId": "EVT-100",
              "x-source-region": "ap-southeast-1"
            }
            """;

    EventEnvelope envelope =
            extensionMapper.readValue(accepted, EventEnvelope.class);

    assertTrue(envelope.getExtensions().containsKey("x-source-region"));
}
~~~

Ngoài các test trên, nên có test cho:
- Null vào primitive và creator property.
- Missing required creator property.
- Float gửi vào integer.
- String gửi vào number.
- Enum value mới.
- Polymorphic subtype chưa biết.
- Unknown property có nested object/array.
- Field nhạy cảm hoặc field quyền hạn gửi vào request DTO.
- Handler/annotation có vô tình bỏ qua field ngoài allowlist hay không.

## 19. Các lỗi cấu hình thường gặp

| Cách làm | Rủi ro | Cách xử lý |
|---|---|---|
| Bật ignoreUnknown trên mọi DTO | Che lỗi đánh máy và schema drift | Chỉ bật ở contract cho phép extension |
| Tắt FAIL_ON_UNKNOWN_PROPERTIES global | Tất cả endpoint mất tín hiệu field lạ | Cấu hình theo boundary/mapper phù hợp |
| Bắt JsonMappingException rồi trả object mặc định | Request sai được xem là thành công | Truyền lỗi hoặc trả lỗi tường minh |
| Dùng primitive cho field bắt buộc | Missing/null có thể nhập với default | Dùng wrapper, creator hoặc presence check |
| Chấp nhận string-to-number không kiểm soát | Input ngoài contract vẫn qua mapping | Cấu hình coercion và test |
| Ánh xạ unknown enum thành null | Downstream có thể gặp null không mong muốn | Dùng strict hoặc UNKNOWN có semantics |
| Tắt FAIL_ON_INVALID_SUBTYPE | Unknown subtype có thể thành null | Dùng strict hoặc Unknown subtype chuyên dụng |
| Bỏ qua duplicate key | Các tầng có thể hiểu payload khác nhau | STRICT_DUPLICATE_DETECTION |
| Chỉ đọc root value đầu | Dữ liệu dư không được kiểm tra | FAIL_ON_TRAILING_TOKENS |
| Deserialize thẳng vào entity | Mass assignment field đã biết | Request DTO allowlist và mapping rõ |
| Coi mapping thành công là validation thành công | Giá trị như số âm vẫn qua mapping | Bean Validation/domain validation |
| Dùng handler trả true cho mọi unknown field | Vô hiệu hóa strict unknown policy | Chỉ chấp nhận extension được phép |

## 20. Quy trình thiết kế input mapping an toàn

Khi cấu hình Jackson cho một API hoặc message consumer:

1. Xác định contract cho từng endpoint/message type.
2. Chọn DTO đầu vào chỉ chứa field người gửi được phép cung cấp.
3. Quy định unknown property sẽ bị từ chối, bỏ qua hay thu thập thành extension.
4. Không bật ignoreUnknown rộng nếu chưa có yêu cầu tương thích cụ thể.
5. Xác định kiểu JSON chính xác cho từng field và cấu hình coercion tương ứng.
6. Phân biệt missing, null và giá trị mặc định.
7. Bật duplicate detection nếu giao thức yêu cầu key duy nhất.
8. Kiểm tra trailing token khi chỉ chấp nhận một root document.
9. Giữ strict policy cho enum và subtype, hoặc định nghĩa UNKNOWN fallback có semantics rõ.
10. Dùng Bean Validation cho constraint và service/domain cho quy tắc nghiệp vụ.
11. Dùng authorization cho field/action nhạy cảm; không dựa vào mapping configuration.
12. Không nuốt exception rồi tạo object mặc định.
13. Trả lỗi có mã ổn định và path an toàn; không echo raw payload.
14. Viết test cho input hợp lệ, sai kiểu, unknown, duplicate, null, missing và các trường hợp tương thích.

## 21. Những điểm cần nhớ

- Bỏ qua unknown property không phải là validation dữ liệu.
- Unknown property khác với property đã biết nhưng sai kiểu hoặc sai giá trị.
- FAIL_ON_UNKNOWN_PROPERTIES giúp từ chối field không được ánh xạ; @JsonIgnoreProperties(ignoreUnknown = true) có thể bỏ qua field đó.
- FAIL_ON_IGNORED_PROPERTIES giúp phát hiện field đã bị đánh dấu ignore nhưng vẫn xuất hiện trong input.
- FAIL_ON_NULL_FOR_PRIMITIVES và các feature creator hỗ trợ kiểm soát null/missing ở những phạm vi cụ thể.
- Coercion cần được cấu hình theo contract; không chấp nhận string/float thay cho integer một cách vô tình.
- STRICT_DUPLICATE_DETECTION và FAIL_ON_TRAILING_TOKENS giúp kiểm soát cấu trúc document.
- Unknown enum/subtype cần chính sách riêng; không biến chúng thành trạng thái nghiệp vụ đã biết.
- Bean Validation kiểm tra constraint sau khi mapping; service/domain kiểm tra quy tắc nghiệp vụ.
- FAIL_ON_UNKNOWN_PROPERTIES không ngăn mass assignment đối với field đã biết.
- Request DTO allowlist và authorization là biện pháp cần thiết để bảo vệ field nhạy cảm.
- Không bắt lỗi rồi trả object rỗng hoặc giá trị mặc định như thể request hợp lệ.
- Chỉ bỏ qua dữ liệu khi contract cho phép rõ ràng, có giới hạn và có kiểm thử.

Jackson có thể được cấu hình linh hoạt để hỗ trợ nhiều phiên bản producer và consumer, nhưng tính linh hoạt cần được giới hạn bởi hợp đồng dữ liệu. Khi một property được bỏ qua, ứng dụng đã chủ động từ bỏ việc kiểm tra property đó. Vì vậy, hãy chỉ bỏ qua field mở rộng đã được cho phép; với field sai kiểu, thiếu bắt buộc, giá trị không hợp lệ hoặc dữ liệu có thể ảnh hưởng quyền hạn, hãy từ chối và báo lỗi theo ngữ cảnh. Kết hợp mapping strict phù hợp, DTO allowlist, Bean Validation và authorization giúp đầu vào được xử lý đúng nghĩa thay vì chỉ được đọc mà không có kiểm soát.
