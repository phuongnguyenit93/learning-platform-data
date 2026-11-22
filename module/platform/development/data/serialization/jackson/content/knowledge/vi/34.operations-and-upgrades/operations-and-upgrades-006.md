# Đối chiếu thay đổi mặc định trước khi nâng phiên bản

Nâng Jackson lên phiên bản mới thường được xem là một thay đổi dependency. Nhưng Jackson không chỉ là một thư viện parse JSON: nó quyết định cách Java object được biểu diễn thành JSON, cách JSON được chuyển thành object, cách xử lý dữ liệu sai hoặc thiếu, và cách parser phản ứng trước payload lớn hay bất thường. Một thay đổi mặc định có thể làm API trả JSON khác, khiến một request trước đây được chấp nhận nay bị từ chối, hoặc làm dữ liệu được chuyển đổi theo cách khác dù code ứng dụng không thay đổi.

Vì vậy, trước khi nâng phiên bản, cần đối chiếu **hành vi thực tế của cấu hình đang chạy** với hành vi của phiên bản đích. Không nên chỉ so sánh số version hoặc đọc một danh sách thay đổi rồi kết luận rằng ứng dụng không bị ảnh hưởng. Cùng một Jackson version có thể cho kết quả khác nhau khi được khởi tạo bằng `new ObjectMapper()`, qua Spring Boot auto-configuration, qua một customizer, hoặc qua một `ObjectReader` có feature override riêng.

Bài học này trình bày cách lập baseline, tìm đúng các lớp cấu hình, so sánh thay đổi mặc định qua từng version, xây dựng test tương thích, nâng cấp dependency có kiểm soát và phát hiện regression trước khi đưa phiên bản mới vào production.

## 1. Vì sao default behavior có thể làm hỏng tương thích?

Một default là hành vi được dùng khi ứng dụng không cấu hình rõ một tùy chọn. Khi default thay đổi, code không đổi nhưng kết quả có thể thay đổi.

Ví dụ, ứng dụng có DTO:

~~~java
public class CustomerRequest {
    private String customerId;
    private Integer age;

    // Getter và setter.
}
~~~

Client gửi:

~~~json
{
  "customerId": "CUS-100",
  "age": "25",
  "legacyFlag": true
}
~~~

Ứng dụng có thể chịu ảnh hưởng từ nhiều chính sách:

- `"25"` có được coercion thành số nguyên hay không?
- `legacyFlag` không có trong DTO có bị từ chối hay bỏ qua?
- Nếu `age` bị thiếu thì object nhận `null`, zero hay lỗi?
- Nếu `age` là `null` thì kết quả có khác trường hợp thiếu field không?
- Nếu response có property null thì property đó có được ghi ra JSON?
- Nếu enum nhận một giá trị chưa biết thì parser báo lỗi hay dùng giá trị fallback?
- Nếu object có cấu trúc lồng quá sâu thì parser xử lý đến đâu?

Một số hành vi được quyết định bởi feature của Jackson; một số khác đến từ annotation, module, framework hoặc code ứng dụng. Khi nâng cấp, cần tìm đúng nguồn tạo ra hành vi.

## 2. Phân biệt library default với effective configuration

Không có một khái niệm “default Jackson” duy nhất cho toàn bộ ứng dụng. Cần phân biệt ít nhất bốn lớp:

1. **Default của thư viện:** hành vi của `jackson-core`, `jackson-databind` và module khi không có cấu hình bổ sung.
2. **Default của framework:** Spring Boot hoặc framework khác có thể tạo `ObjectMapper` với feature đã bật/tắt.
3. **Cấu hình ứng dụng:** bean `ObjectMapper`, builder customizer, module, serializer, deserializer và cấu hình converter.
4. **Override theo lần sử dụng:** annotation trên class/property, `ObjectReader`, `ObjectWriter` hoặc code gọi mapper có thể thay đổi hành vi tại một boundary cụ thể.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();
~~~

không nhất thiết có cùng cấu hình với:

~~~java
@Autowired
ObjectMapper objectMapper;
~~~

Mapper do Spring Boot cung cấp có thể đã nhận module, customizer và property cấu hình từ application. Một mapper được tạo thủ công trong test có thể không có các thiết lập đó.

Sơ đồ các lớp cấu hình:

~~~text
Jackson library defaults
          |
          v
Framework / Spring Boot defaults
          |
          v
Application ObjectMapper configuration
          |
          v
Annotations, mix-ins, modules
          |
          v
ObjectReader / ObjectWriter overrides
          |
          v
Actual JSON behavior
~~~

Khi so sánh trước và sau nâng cấp, hãy đo lớp cuối cùng: hành vi của mapper/converter thực sự được ứng dụng sử dụng.

## 3. Xác định chính xác dependency đang chạy

Trước khi đọc release notes, cần biết ứng dụng đang chạy phiên bản nào của từng artifact. Jackson là một nhóm module, không phải một JAR duy nhất.

Các artifact thường gặp:

| Artifact | Vai trò |
|---|---|
| `jackson-core` | Streaming API, parser và generator |
| `jackson-annotations` | Annotation metadata |
| `jackson-databind` | Object mapping, ObjectMapper, ObjectReader, ObjectWriter |
| `jackson-datatype-jsr310` | Java Time types |
| `jackson-datatype-jdk8` | Optional và một số kiểu JDK 8 |
| `jackson-module-parameter-names` | Constructor parameter names |
| `jackson-module-kotlin` | Kotlin data classes và constructor |
| `jackson-dataformat-xml` | XML data binding |
| `jackson-dataformat-csv` | CSV data binding |
| `jackson-dataformat-yaml` | YAML data binding |

Dùng Gradle để xem dependency đã resolve:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Có thể lọc các dependency Jackson:

~~~bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Lặp lại với `jackson-core`, `jackson-annotations` và các module mà ứng dụng dùng. Với Maven:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson
~~~

Không chỉ nhìn version trong `build.gradle` hoặc `pom.xml`. BOM, dependency constraints, Spring Boot dependency management và dependency bắc cầu có thể quyết định version cuối cùng.

## 4. Giữ các module Jackson đồng bộ

Các artifact Jackson có quan hệ tương thích phiên bản. Khi nâng cấp, tránh tình trạng `jackson-databind` ở version mới nhưng `jackson-core` hoặc `jackson-annotations` ở version cũ ngoài dự kiến.

Với Gradle, có thể dùng Jackson BOM:

~~~gradle
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:<version>"))

    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
~~~

Placeholder `<version>` phải được thay bằng version đã chọn và đã xác minh. Nếu Spring Boot quản lý Jackson qua dependency management, hãy cân nhắc nâng Spring Boot/BOM theo ma trận tương thích thay vì override tùy tiện từng artifact.

Không ép tất cả module lên cùng version chỉ bằng cách sửa một dòng mà bỏ qua Spring Boot. Hãy kiểm tra:

- Version do BOM quản lý.
- Version bị pin bởi dependency constraint.
- Module nào không còn được dùng.
- Module nào có version lệch.
- Dependency bắc cầu có kéo một version khác vào không.
- Runtime classpath có trùng artifact hoặc xung đột không.

## 5. Đọc release notes theo từng bước nâng cấp

Nếu ứng dụng đang ở một version cũ và muốn nhảy qua nhiều minor/patch release, hãy xem thay đổi của tất cả các version nằm giữa. Một thay đổi được giới thiệu ở minor version trung gian vẫn có thể ảnh hưởng dù ứng dụng không dừng lại ở version đó.

Quy trình đọc:

1. Xác định version hiện tại đã resolve.
2. Xác định version đích và các version trung gian.
3. Đọc release notes của `jackson-core`, `jackson-databind` và module đang dùng.
4. Tìm các mục liên quan đến default, coercion, parser, serializer, annotation, security và deprecation.
5. Ghi lại thay đổi có khả năng ảnh hưởng tới input/output thực tế.
6. Kiểm tra migration note và issue liên quan nếu release note nêu một thay đổi có điều kiện.
7. Chuyển từng thay đổi thành một test hoặc một quyết định cấu hình.

Không nên chỉ đọc changelog của `jackson-databind`. Thay đổi trong Core có thể ảnh hưởng parser/generator; thay đổi trong module Java Time hoặc Kotlin có thể ảnh hưởng riêng một nhóm DTO.

## 6. Lập bảng đối chiếu trước và sau

Tạo một bảng migration có các cột rõ ràng:

| Hạng mục | Version hiện tại | Version đích | Nguồn cấu hình | Rủi ro | Test |
|---|---|---|---|---|---|
| Unknown properties | Giá trị thực tế | Giá trị thực tế | Boot / mapper | Request cũ bị từ chối | Unknown field |
| Scalar coercion | Giá trị thực tế | Giá trị thực tế | Databind / coercion config | Thay đổi kiểu dữ liệu | String-to-number |
| Null/missing | Giá trị thực tế | Giá trị thực tế | Feature / annotation | Sai semantics | Missing vs null |
| Date/time | Output hiện tại | Output đích | JavaTimeModule / format | JSON contract đổi | Date golden |
| Enum | Cách đọc/ghi hiện tại | Cách đọc/ghi đích | Feature / annotation | Client không tương thích | Unknown enum |
| Parser limits | Ngưỡng hiện tại | Ngưỡng đích | JsonFactory | Payload bị từ chối | Boundary |

Không điền “giống nhau” chỉ vì chưa thấy lỗi. Mỗi hàng nên có bằng chứng từ cấu hình hoặc test. Nếu không thể đọc trực tiếp một giá trị cấu hình, ghi rõ rằng hành vi đã được xác minh bằng test.

## 7. Những default thường cần đối chiếu

Các feature dưới đây thường đáng đưa vào migration matrix. Bảng mô tả nhóm hành vi và giá trị thường gặp của vanilla Jackson; **không dùng bảng này thay cho việc đo cấu hình thực tế của ứng dụng**. Spring Boot, customizer, module, annotation hoặc reader/writer override có thể làm kết quả khác đi.

| Nhóm | Feature / hành vi | Điều cần xác nhận |
|---|---|---|
| Unknown fields | `FAIL_ON_UNKNOWN_PROPERTIES` | Field lạ bị từ chối hay bỏ qua? |
| Null primitive | `FAIL_ON_NULL_FOR_PRIMITIVES` | `null` vào int/boolean có bị từ chối? |
| Number coercion | `ACCEPT_FLOAT_AS_INT` | `2.7` vào integer bị từ chối hay bị chuyển đổi? |
| Enum numeric | `FAIL_ON_NUMBERS_FOR_ENUMS` | Số có thể được dùng làm ordinal enum không? |
| Single value array | `ACCEPT_SINGLE_VALUE_AS_ARRAY` | Một object đơn có được chấp nhận thay array một phần tử? |
| Array unwrapping | `UNWRAP_SINGLE_VALUE_ARRAYS` | Array một phần tử có được chuyển thành scalar? |
| Trailing tokens | `FAIL_ON_TRAILING_TOKENS` | Có từ chối nội dung sau root value không? |
| Empty bean | `FAIL_ON_EMPTY_BEANS` | Object không có property có làm serialize lỗi? |
| Date/time | `WRITE_DATES_AS_TIMESTAMPS` | Date được ghi thành timestamp hay text? |
| Property inclusion | `JsonInclude` | Null/empty/default có được ghi ra không? |
| Case-insensitive | `ACCEPT_CASE_INSENSITIVE_PROPERTIES` | Tên field có phân biệt hoa/thường không? |
| Parser constraints | `StreamReadConstraints` | Depth/string/number có ngưỡng nào? |
| Duplicate keys | Strict duplicate detection | Key trùng trong object được xử lý ra sao? |

Các feature có thể thay đổi theo version và cách khởi tạo. Đặc biệt, không suy luận rằng giá trị vanilla mapper chính là giá trị mapper trong Spring Boot.

## 8. Unknown properties: strict hay tolerant?

`DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` quyết định cách xử lý property JSON không có trong target type và không được xử lý bởi any-setter hoặc cơ chế khác.

Input:

~~~json
{
  "id": "ORD-1001",
  "newPartnerFlag": true
}
~~~

Nếu mapper strict, field không nhận diện có thể làm deserialize thất bại. Nếu mapper tolerant hoặc DTO có `@JsonIgnoreProperties(ignoreUnknown = true)`, field có thể được bỏ qua.

Test hai policy:

~~~java
@Test
void unknownPropertyPolicyIsExplicit() {
    ObjectMapper strict = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    ObjectMapper tolerant = new ObjectMapper()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    String json = """
        {"id":"ORD-1","newPartnerFlag":true}
        """;

    assertThrows(
        UnrecognizedPropertyException.class,
        () -> strict.readValue(json, OrderRequest.class)
    );

    assertEquals(
        "ORD-1",
        tolerant.readValue(json, OrderRequest.class).getId()
    );
}
~~~

Khi nâng version, kiểm tra cả cấu hình mapper và annotation trên DTO. Một DTO có `ignoreUnknown = true` vẫn có thể tolerant dù mapper strict. Ngược lại, một reader có override riêng có thể thay đổi policy của mapper.

Chọn policy theo hợp đồng: API nội bộ cần phát hiện typo có thể ưu tiên strict; API cần forward compatibility với producer mở rộng field có thể chọn tolerant hoặc capture extension field. Đừng để policy thay đổi ngoài ý muốn theo version.

## 9. Scalar coercion và dữ liệu sai kiểu

Jackson có thể chuyển một số scalar từ kiểu JSON này sang kiểu Java khác theo coercion policy. Ví dụ chuỗi `"25"` có thể được chuyển thành integer trong một số cấu hình; số thập phân có thể được chuyển vào integer tùy feature và coercion rules.

Các input nên được kiểm tra riêng:

~~~json
{"quantity": 25}
~~~

~~~json
{"quantity": "25"}
~~~

~~~json
{"quantity": 25.8}
~~~

~~~json
{"quantity": ""}
~~~

~~~json
{"quantity": null}
~~~

Đừng chỉ test một payload hợp lệ. Một thay đổi coercion có thể làm dữ liệu vốn được chấp nhận chuyển thành lỗi, hoặc ngược lại làm dữ liệu không đúng contract vẫn lọt qua.

Có thể đặt coercion policy rõ ràng bằng `CoercionConfig` trên `ObjectMapper`/`MutableCoercionConfig` ở các version hỗ trợ. API chi tiết phụ thuộc version; hãy kiểm tra Javadoc trước khi dùng. Với field quan trọng, DTO type rõ ràng cùng validation vẫn cần thiết.

## 10. Missing field, null và primitive

Ba trường hợp sau không giống nhau:

~~~json
{}
~~~

~~~json
{"quantity": null}
~~~

~~~json
{"quantity": 0}
~~~

Với Java primitive `int`, object không thể giữ trạng thái null. Nếu field bị thiếu hoặc null, kết quả phụ thuộc feature và coercion policy; có thể nhận giá trị mặc định hoặc lỗi. Với `Integer`, ứng dụng có thể phân biệt null với số 0, nhưng vẫn cần xác định semantics của field bị thiếu.

Khi nâng cấp, test các field:

- Bắt buộc và không được null.
- Có thể bỏ qua khi thiếu.
- Có giá trị mặc định.
- Dùng primitive.
- Dùng wrapper type.
- Có `@JsonSetter(nulls = ...)` hoặc `@JsonProperty(required = ...)`.

Đừng dùng giá trị Java mặc định để thay thế validation nghiệp vụ. Nếu quantity phải lớn hơn zero, hãy kiểm tra rõ sau deserialize.

## 11. Date và time: thay đổi dễ làm hỏng API contract

Date/time là một trong các vùng có khả năng tạo regression cao vì kết quả phụ thuộc module, feature và annotation.

Ví dụ `Instant` hoặc `LocalDateTime` có thể được ghi dưới dạng timestamp hoặc chuỗi ISO tùy cấu hình và loại Java Time. Với `JavaTimeModule`, hành vi còn liên quan tới `WRITE_DATES_AS_TIMESTAMPS`.

Một cấu hình thường gặp:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Test output thực tế:

~~~java
@Test
void instantUsesExpectedWireFormat() throws Exception {
    Instant instant = Instant.parse("2026-11-12T08:30:00Z");

    String json = mapper.writeValueAsString(instant);

    assertEquals("\"2026-11-12T08:30:00Z\"", json);
}
~~~

Test thêm:

- `Instant`, `OffsetDateTime`, `ZonedDateTime`, `LocalDate` và `LocalDateTime`.
- Múi giờ và offset.
- Millisecond/nanosecond precision.
- Date trước/sau epoch nếu dùng timestamp.
- Format tùy chỉnh bằng `@JsonFormat`.
- Giá trị null và field bị thiếu.
- Parse chuỗi không có timezone vào kiểu cần timezone.

Không chỉ kiểm tra object round-trip với cùng mapper. Nếu cả writer và reader cùng thay đổi theo một hướng, round-trip vẫn có thể pass dù JSON contract đã đổi. Hãy so sánh wire format với fixture độc lập.

## 12. Enum và giá trị chưa biết

Enum có thể được ghi theo tên, ordinal hoặc một representation tùy chỉnh. Khi deserialize, một giá trị chưa biết có thể làm lỗi hoặc dùng fallback nếu được cấu hình bằng annotation/feature phù hợp.

Ví dụ:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED
}
~~~

Test contract:

~~~java
@Test
void enumIsWrittenByName() throws Exception {
    assertEquals(
        "\"PAID\"",
        mapper.writeValueAsString(OrderStatus.PAID)
    );
}
~~~

~~~java
@Test
void unknownEnumValueFollowsDeclaredPolicy() throws Exception {
    assertThrows(
        InvalidFormatException.class,
        () -> mapper.readValue("\"REFUNDED\"", OrderStatus.class)
    );
}
~~~

Nếu ứng dụng cần forward compatibility, có thể cân nhắc `@JsonEnumDefaultValue` cùng feature chấp nhận unknown enum default, tùy version. Hãy kiểm tra rõ cách feature được bật và enum có đánh dấu fallback hay không.

Không dùng ordinal làm wire contract nếu enum có thể được sắp xếp lại. Thêm một enum constant ở đầu danh sách có thể làm thay đổi ordinal của các giá trị cũ.

## 13. Null và property inclusion khi serialize

`JsonInclude` quyết định property nào được ghi ra JSON. Các policy thường gặp:

- `ALWAYS`: ghi property kể cả null.
- `NON_NULL`: bỏ property null.
- `NON_EMPTY`: bỏ giá trị rỗng theo semantics của kiểu.
- `NON_DEFAULT`: bỏ giá trị được xem là default.

Ví dụ:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class CustomerResponse {
    private String id;
    private String nickname;

    // Getter và setter.
}
~~~

Hoặc cấu hình mapper:

~~~java
mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
~~~

Khi nâng cấp, test riêng:

- Property null.
- Chuỗi rỗng.
- Collection rỗng.
- Map rỗng.
- Primitive zero/false.
- Wrapper null.
- Property có annotation riêng ghi đè global policy.

Không coi `NON_EMPTY` và `NON_NULL` là tương đương. Thay đổi inclusion có thể ảnh hưởng client phân biệt “không gửi field” với “gửi field có null”.

## 14. Property naming, annotation và visibility

Một DTO có thể dùng tên Java camelCase nhưng wire contract là snake_case:

~~~java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class CustomerRequest {
    private String customerId;
}
~~~

Hoặc mapper có global naming strategy. Khi nâng cấp, kiểm tra:

- `@JsonProperty` có ghi đè naming strategy không.
- `@JsonAlias` có tiếp tục nhận tên cũ không.
- Field/getter/setter visibility.
- Field private có được phát hiện không.
- Getter boolean dạng `isActive()` có tên property mong đợi không.
- `@JsonIgnore`, `@JsonIgnoreProperties` và mix-in.
- Constructor/creator parameter names.
- Java record và Kotlin constructor metadata nếu dự án dùng.

Test cả tên output và tên input. Một serializer có thể ghi `customer_id` nhưng deserializer không nhận tên đó nếu mix-in hoặc visibility config khác nhau.

## 15. Constructor, record và creator discovery

Jackson có thể tạo object qua constructor mặc định/setter, `@JsonCreator`, constructor parameter names, Java record canonical constructor hoặc cơ chế module tương ứng.

Khi nâng cấp, kiểm tra DTO:

- Immutable class.
- Java record.
- Lombok-generated constructor.
- `@JsonCreator` với `@JsonProperty`.
- Constructor có nhiều overload.
- Parameter names phụ thuộc compiler flag.
- Kotlin data class và Kotlin module.

Ví dụ creator rõ ràng:

~~~java
public class Money {
    private final BigDecimal amount;
    private final String currency;

    @JsonCreator
    public Money(
            @JsonProperty("amount") BigDecimal amount,
            @JsonProperty("currency") String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Explicit creator metadata giúp giảm phụ thuộc vào auto-detection. Tuy vậy, hãy test trên đúng JDK/compiler/module mà production dùng; một unit test chạy trên classpath khác có thể che giấu lỗi parameter metadata.

## 16. Trailing tokens và duplicate object keys

Một JSON text chuẩn có một root value. Nhưng một số parser có thể được cấu hình để đọc một root value rồi bỏ qua nội dung tiếp theo, hoặc phát hiện key trùng trong object theo policy riêng.

Ví dụ trailing content:

~~~text
{"id":"ORD-1"} {"id":"ORD-2"}
~~~

Ví dụ duplicate key:

~~~json
{
  "role": "user",
  "role": "admin"
}
~~~

Khi nâng cấp, xác nhận:

- `FAIL_ON_TRAILING_TOKENS` có được bật không.
- Strict duplicate detection có được bật trên `JsonFactory` không.
- Parser có chấp nhận comments, single quotes, unquoted field names hoặc non-numeric numbers không.
- `readValue()` và sequence-reading API có được dùng đúng với framing của input không.

Duplicate key đặc biệt đáng chú ý vì các hệ thống khác nhau có thể giữ giá trị đầu, giá trị cuối hoặc từ chối. Nếu JSON được dùng cho authorization hoặc cấu hình nhạy cảm, hãy có một policy rõ ràng thay vì dựa vào parser mặc định.

## 17. Parser constraints và giới hạn tài nguyên

Jackson Core có `StreamReadConstraints` trong các phiên bản hỗ trợ. Những giới hạn thường cần đối chiếu gồm:

- Maximum nesting depth.
- Maximum string token length.
- Maximum number token length.

Khi nâng version, không chỉ xem API có thay đổi không; hãy kiểm tra default constraints và giá trị ứng dụng đã cấu hình. Một ứng dụng có thể bắt đầu từ default mới của thư viện nhưng Spring Boot hoặc custom `JsonFactory` lại áp dụng policy riêng.

Ví dụ cấu hình tường minh:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(32)
    .maxStringLength(65_536)
    .maxNumberLength(128)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Các giới hạn token không phải giới hạn tổng byte request hoặc số record. Hãy tiếp tục kiểm soát upload size, decompressed size, record count, batch size và concurrency ở tầng tương ứng.

Nếu ứng dụng dựa vào một default constraints cụ thể, hãy biến nó thành cấu hình tường minh và test boundary để nâng version không âm thầm thay đổi policy.

## 18. Polymorphic deserialization và bảo mật

Polymorphic deserialization cho phép một property hoặc root value được tạo thành một subtype dựa trên type metadata. Đây là vùng cần kiểm tra cẩn thận khi nâng cấp vì nó liên quan tới bảo mật và tương thích dữ liệu.

Tránh bật default typing toàn cục cho JSON không tin cậy nếu không có một policy subtype an toàn. Khi cần polymorphism:

- Ưu tiên discriminator rõ ràng trong hợp đồng.
- Dùng subtype allowlist.
- Dùng `PolymorphicTypeValidator` ở các API hỗ trợ.
- Không cho payload tùy ý chọn class bất kỳ trên classpath.
- Test subtype hợp lệ, subtype không được phép và type id chưa biết.
- Xem lại annotation `@JsonTypeInfo` và `@JsonSubTypes`.
- Kiểm tra dữ liệu cũ có type id đã bị đổi tên hoặc di chuyển package không.

Một nâng cấp có thể làm một số type id cũ không còn được resolve hoặc policy validator không còn cho phép subtype. Đừng giải quyết bằng cách mở rộng allowlist quá rộng; hãy xác định tập subtype hợp lệ theo domain.

## 19. Module và thứ tự đăng ký

Module bổ sung serializer, deserializer, type modifier hoặc hỗ trợ kiểu Java cụ thể. Những module thường gặp gồm Java Time, JDK 8 Optional, Kotlin và parameter names.

Khi nâng version, kiểm tra:

- Module có cùng dòng version với core/databind không.
- Module đã được đăng ký tự động hay thủ công.
- Module có bị đăng ký hai lần không.
- Thứ tự đăng ký module có ảnh hưởng serializer/deserializer không.
- Framework có tự discover module trên classpath không.
- Custom module có phụ thuộc API đã deprecated hoặc đổi signature không.

Ví dụ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .addModule(new Jdk8Module())
    .build();
~~~

Không vừa đăng ký module thủ công vừa dựa vào auto-discovery mà không biết có trùng hay không. Hãy xem danh sách module thực tế và test những kiểu dữ liệu mà module chịu trách nhiệm.

## 20. Deprecated API và cấu hình cũ

Jackson có thể deprecate API trước khi loại bỏ ở major version sau. Khi nâng cấp, compiler warning là tín hiệu cần xử lý, nhưng không phải mọi deprecated API đều cần thay thế ngay trong cùng một patch release.

Phân loại:

- API deprecated nhưng vẫn hoạt động và chưa có migration requirement.
- API có replacement tương đương.
- API thay đổi semantics hoặc không còn được hỗ trợ.
- Feature cũ được chuyển sang một config API mới.
- Extension point nội bộ không có cam kết tương thích.

Ví dụ, nhiều cấu hình trước đây gọi trực tiếp trên mapper có thể có builder hoặc config object tương ứng. Ưu tiên API được tài liệu version đích khuyến nghị, nhưng không thay đổi cấu hình hàng loạt mà không có test xác nhận semantics.

Không bỏ qua warning từ module custom hoặc converter custom. Một method override không còn đúng signature có thể khiến extension point không được gọi như dự kiến.

## 21. Tạo một báo cáo cấu hình mapper thực tế

Có thể ghi lại các feature của mapper đang được Spring inject. Ví dụ một component chẩn đoán chỉ chạy trong profile migration:

~~~java
@Component
@Profile("jackson-migration-report")
public class JacksonConfigurationReporter implements ApplicationRunner {
    private final ObjectMapper mapper;

    public JacksonConfigurationReporter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (SerializationFeature feature : SerializationFeature.values()) {
            log.info("jackson.serialization.{}={}",
                feature, mapper.isEnabled(feature));
        }

        for (DeserializationFeature feature : DeserializationFeature.values()) {
            log.info("jackson.deserialization.{}={}",
                feature, mapper.isEnabled(feature));
        }

        for (MapperFeature feature : MapperFeature.values()) {
            log.info("jackson.mapper.{}={}",
                feature, mapper.isEnabled(feature));
        }

        log.info("jackson.modules={}", mapper.getRegisteredModuleIds());
    }
}
~~~

Đây là báo cáo hữu ích nhưng chưa phải toàn bộ cấu hình. Nó không tự ghi lại mọi per-type override, annotation, mix-in, coercion rule, parser factory option hoặc `ObjectReader`/`ObjectWriter` riêng.

Hãy chạy báo cáo trên mapper thực tế trong Spring context. Nếu ứng dụng có nhiều mapper/converter, ghi rõ bean name và mục đích từng mapper; inject một bean ngẫu nhiên không đủ để chứng minh tất cả endpoint dùng cùng policy.

Không để log cấu hình nhạy cảm hoặc bật reporter vĩnh viễn nếu nó tạo quá nhiều log. Có thể dùng profile migration và lưu output làm artifact của lần nâng cấp.

## 22. Xây dựng bộ fixture JSON làm baseline

Tạo một tập fixture nhỏ nhưng đại diện cho contract thực tế:

~~~text
src/test/resources/jackson-baseline/
  valid-minimal.json
  valid-full.json
  unknown-property.json
  missing-field.json
  explicit-null.json
  scalar-coercion.json
  enum-unknown.json
  date-time.json
  nested-boundary.json
  trailing-content.json
  duplicate-key.json
~~~

Mỗi fixture cần trả lời một câu hỏi cụ thể. Ví dụ:

- Minimal payload: field bắt buộc nào cần có?
- Unknown property: forward compatibility hay strict validation?
- Missing/null: client cũ có bỏ field không?
- Scalar coercion: string number có được chấp nhận?
- Date/time: timezone và precision có ổn định?
- Trailing content: parser có từ chối thêm root value không?
- Duplicate key: ứng dụng có phát hiện dữ liệu nhập nhằng không?

Fixture nên độc lập với code tạo expected value. Nếu expected JSON được tạo bằng chính mapper đang test, test có thể lặp lại cùng một lỗi hoặc cùng một thay đổi default mà không phát hiện.

## 23. So sánh serialize output trước và sau nâng cấp

Có hai cách so sánh JSON output:

1. **So sánh semantic:** parse cả hai thành JSON tree rồi so sánh nội dung.
2. **So sánh byte/text chính xác:** dùng khi whitespace, property order, escaping hoặc lexical form là một phần của contract.

Ví dụ semantic comparison:

~~~java
JsonNode expected = baselineMapper.readTree(expectedJson);
JsonNode actual = upgradedMapper.readTree(actualJson);

assertEquals(expected, actual);
~~~

Cách này không coi thứ tự property object là khác biệt, phù hợp khi consumer chỉ quan tâm cấu trúc JSON. Tuy nhiên, nó vẫn có thể bỏ qua một số khác biệt lexical như cách biểu diễn số hoặc escaping. Nếu consumer phụ thuộc format cụ thể, hãy có test text/byte riêng.

Các trường hợp cần golden output:

- Date/time format.
- Enum representation.
- Null/empty inclusion.
- Decimal scale và numeric formatting.
- Property naming.
- Polymorphic type metadata.
- Escaping ký tự Unicode hoặc HTML-sensitive characters nếu contract yêu cầu.
- Array ordering.
- Root wrapping hoặc unwrapping.

Không tự động cập nhật mọi golden file khi test fail. Trước tiên xác định output mới có phải thay đổi được chấp nhận hay là regression.

## 24. Chạy cùng contract test trên hai version

Một cách hiệu quả là chạy cùng bộ test trên version hiện tại và version đích trong hai build/test job riêng. Không cố nạp hai phiên bản `jackson-databind` có cùng package vào một classloader thông thường; classpath conflict khiến kết quả không đáng tin cậy.

Pipeline có thể có hai job:

~~~text
                Shared contract fixtures
                         |
               +---------+---------+
               |                   |
               v                   v
       Current Jackson       Target Jackson
          test suite            test suite
               |                   |
               v                   v
       Baseline results      Candidate results
               |                   |
               +---------+---------+
                         |
                         v
                 Compare behavior
~~~

Lưu output của từng job:

- Resolved dependency tree.
- Mapper configuration report.
- Test result.
- Golden serialization output.
- Exception type cho fixture không hợp lệ.
- Performance measurement nếu cần.

Nếu version đích nằm trong một branch riêng, hãy giữ fixture và test source dùng chung để hai job không vô tình kiểm tra hai bộ test khác nhau.

## 25. Kiểm tra cấu hình Spring Boot và converter

Trong ứng dụng Spring MVC, `MappingJackson2HttpMessageConverter` thường dùng mapper do Boot hoặc ứng dụng cấu hình. Một mapper được inject trong service có thể không phải mapper của mọi converter nếu ứng dụng đăng ký converter riêng.

Khi nâng Spring Boot cùng lúc với Jackson, hãy đối chiếu:

- Spring Boot version và dependency management.
- Jackson BOM version được Boot quản lý.
- `spring.jackson.*` properties.
- `Jackson2ObjectMapperBuilderCustomizer`.
- Bean `ObjectMapper` do ứng dụng khai báo.
- `WebMvcConfigurer` và converter custom.
- Media type và thứ tự converter.
- Mapper riêng cho vendor media type hoặc partner API.

Test bằng `@WebMvcTest`/MockMvc để xác nhận request thực tế được đọc theo policy dự kiến. Test trực tiếp `ObjectMapper` không chứng minh converter trong Spring context đang dùng đúng bean hoặc đúng cấu hình.

## 26. Không để test baseline phụ thuộc cấu hình ngầm

Một test có thể pass trên máy developer nhưng fail trên CI nếu mapper được tạo từ auto-configuration khác nhau hoặc module classpath khác nhau.

Các nguyên tắc:

- Dùng dependency management nhất quán.
- Không tạo mapper thủ công nếu mục tiêu test mapper của Spring.
- Nếu test policy độc lập, tạo factory/mapper với feature được cấu hình tường minh.
- Ghi nhận module được đăng ký.
- Test date/time với timezone xác định.
- Không phụ thuộc locale hoặc default timezone của máy.
- Dùng fixture UTF-8 rõ ràng.
- Không so sánh property order nếu contract không yêu cầu.
- Không dùng reflection vào field nội bộ của Jackson để đọc config.
- Không dùng global default override làm thay đổi test khác.

Mỗi test nên mô tả hành vi được mong đợi, không chỉ kiểm tra một feature flag. Ví dụ, test `"quantity": "25"` tốt hơn việc chỉ assert `ACCEPT_FLOAT_AS_INT` đang bật.

## 27. Đánh giá thay đổi theo mức độ rủi ro

Không phải mọi default change đều có tác động như nhau. Có thể phân loại:

| Mức độ | Ví dụ | Hướng xử lý |
|---|---|---|
| Cao | Polymorphic subtype policy, parser security limits, unknown property handling của API quan trọng | Phải có test và quyết định rõ trước release |
| Cao | Date/time hoặc enum wire format thay đổi | Golden contract test và kế hoạch tương thích client |
| Trung bình | Scalar coercion, missing/null, empty collection | Boundary tests và kiểm tra dữ liệu production |
| Trung bình | Module discovery, constructor detection, naming | DTO-focused regression tests |
| Thấp hơn | Pretty print, whitespace hoặc property order không thuộc contract | Xác nhận consumer không phụ thuộc lexical output |

Phân loại phải dựa trên dữ liệu và consumer thực tế. Một thay đổi tưởng nhỏ như bỏ null property có thể gây lỗi nếu client phân biệt field không có với field null.

## 28. Quyết định giữ default mới hay khóa hành vi cũ

Sau khi phát hiện một thay đổi, có ba lựa chọn:

1. **Chấp nhận default mới:** nếu phù hợp với contract và không làm hỏng consumer.
2. **Cấu hình tường minh để giữ hành vi cũ:** nếu API cần tương thích trong giai đoạn chuyển tiếp.
3. **Thay đổi contract có chủ đích:** nếu muốn sửa hành vi cũ, cần versioning, tài liệu và thông báo client.

Ví dụ bật strict unknown property rõ ràng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Hoặc cho phép một DTO bỏ qua unknown fields:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class PartnerWebhook {
    private String eventId;
}
~~~

Không nên bật một feature toàn cục chỉ để sửa một endpoint. Nếu hai API có contract khác nhau, cân nhắc mapper/converter hoặc DTO policy riêng thay vì làm thay đổi mọi endpoint.

Cấu hình tường minh giúp hành vi ổn định qua lần nâng cấp tiếp theo, nhưng cũng tạo trách nhiệm bảo trì. Hãy ghi lý do cấu hình và test để sau này biết đó là quyết định có chủ đích.

## 29. Nâng cấp từng bước và rollback

Một quy trình triển khai an toàn:

1. Chọn version đích và kiểm tra tương thích với JDK/Spring Boot.
2. Cập nhật BOM hoặc dependency management.
3. Xem dependency tree để xác nhận toàn bộ module Jackson được resolve đúng.
4. Chạy unit test và contract test trên version mới.
5. Chạy integration test qua Spring MVC converter.
6. Chạy performance/security test phù hợp.
7. So sánh log cấu hình mapper và golden output.
8. Deploy vào môi trường staging với dữ liệu đại diện.
9. Theo dõi lỗi deserialize/serialize, 400/406/415, latency, heap và GC.
10. Triển khai theo canary hoặc từng nhóm instance nếu hệ thống hỗ trợ.
11. Giữ khả năng rollback dependency/application artifact.
12. Sau khi ổn định, cập nhật tài liệu và xóa compatibility override không còn cần thiết.

Rollback cần tính tới dữ liệu đã được ghi bởi phiên bản mới. Nếu phiên bản mới serialize một format mà phiên bản cũ không đọc được, quay lại binary cũ không tự khôi phục tương thích dữ liệu. Hãy duy trì format tương thích trong giai đoạn rollout hoặc có kế hoạch migration dữ liệu riêng.

## 30. Checklist cho một lần nâng Jackson

### Trước khi thay dependency

- [ ] Ghi lại version hiện tại của core, databind, annotations và module.
- [ ] Xác định Jackson được quản lý bởi BOM nào.
- [ ] Xác định mapper thực tế trong Spring context.
- [ ] Liệt kê converter và mapper riêng.
- [ ] Ghi lại mapper feature và module.
- [ ] Thu thập fixture request/response quan trọng.
- [ ] Đọc release notes và security notes của các version trung gian.

### Khi nâng version

- [ ] Giữ các artifact/module tương thích.
- [ ] Chạy cùng contract test trên version đích.
- [ ] Kiểm tra unknown fields, coercion, null/missing và enum.
- [ ] Kiểm tra date/time, naming, constructor và polymorphism.
- [ ] Kiểm tra parser constraints và duplicate/trailing tokens.
- [ ] Kiểm tra custom serializer/deserializer và deprecated API.
- [ ] Kiểm tra Spring Boot properties và converter selection.

### Trước production

- [ ] Chạy integration test và test với payload đại diện.
- [ ] Đo latency, throughput, heap và GC.
- [ ] Kiểm tra lỗi 400/406/415 và error response.
- [ ] Xác nhận log không lộ payload nhạy cảm.
- [ ] Có kế hoạch canary và rollback.
- [ ] Tài liệu hóa mọi override giữ hành vi cũ.
- [ ] Chỉ xóa override sau khi test chứng minh không còn cần.

## 31. Những sai lầm thường gặp

### Chỉ thay version databind

Các module core, annotations và datatype có thể bị lệch. Kiểm tra runtime dependency tree và BOM.

### Chỉ đọc release notes của version đích

Thay đổi ở version trung gian vẫn có thể ảnh hưởng. Đọc toàn bộ khoảng nâng cấp và module liên quan.

### So sánh vanilla ObjectMapper thay vì mapper của ứng dụng

Spring Boot có thể áp dụng customizer và property riêng. Test mapper/converter trong Spring context.

### Cho rằng default mới luôn tốt hơn

Default mới có thể an toàn hơn nhưng không tương thích với contract cũ. Đưa ra quyết định theo consumer và dữ liệu thực tế.

### Chỉ test round-trip

Writer và reader có thể cùng thay đổi theo một hướng, khiến round-trip vẫn pass trong khi wire format đã đổi. So sánh với fixture độc lập.

### Cập nhật golden file để làm test pass

Golden output là contract evidence. Chỉ cập nhật sau khi đã xác định và chấp nhận thay đổi.

### Override global default để sửa một endpoint

Có thể thay đổi hành vi của mọi mapper trong JVM. Ưu tiên policy theo mapper/reader/DTO phù hợp.

### Bỏ qua module và converter custom

Một custom serializer hoặc vendor converter có thể có hành vi khác mapper mặc định. Lập danh sách tất cả boundary JSON/XML/CSV mà ứng dụng sử dụng.

### Nâng Jackson và Spring Boot cùng lúc mà không tách nguyên nhân

Nếu có regression, khó biết nó đến từ Jackson hay framework. Khi có thể, tách thay đổi thành các bước và giữ cùng contract test.

### Không có rollback data format

Rollback code không đủ nếu output mới đã được lưu hoặc gửi cho consumer cũ. Duy trì tương thích dữ liệu trong giai đoạn rollout.

## 32. Quy trình đối chiếu thay đổi mặc định

1. Xác định version hiện tại và version đích của toàn bộ Jackson artifacts.
2. Kiểm tra BOM, dependency constraints và runtime classpath.
3. Đọc release notes của core, databind và các module liên quan qua toàn bộ khoảng nâng cấp.
4. Xác định mapper nào được dùng bởi từng converter và service.
5. Ghi lại feature flags, module, naming, date/time, inclusion và parser constraints.
6. Thu thập fixture JSON đại diện cho request, response và dữ liệu lưu trữ.
7. Chạy cùng contract test trên version hiện tại và version đích.
8. So sánh semantic JSON, wire format, exception và resource behavior.
9. Chuyển mỗi thay đổi quan trọng thành một quyết định: chấp nhận, khóa cấu hình cũ hoặc thay contract.
10. Cập nhật cấu hình tường minh tại đúng phạm vi.
11. Chạy MVC/integration, security và performance tests.
12. Deploy staging/canary, theo dõi metrics và giữ phương án rollback.
13. Ghi tài liệu các override cùng lý do và test bảo vệ chúng.

## 33. Bảng ghi nhớ

| Hạng mục | Cần đối chiếu |
|---|---|
| Dependency versions | jackson-core, jackson-databind, jackson-annotations, module |
| Dependency management | BOM, Spring Boot và version được resolve |
| Mapper thực tế | Bean, customizer, converter và reader/writer override |
| Unknown fields | FAIL_ON_UNKNOWN_PROPERTIES |
| Coercion | String/number, float-to-int, empty string và null |
| Missing fields | Primitive, wrapper, creator và required property |
| Serialization | Null inclusion, date/time, enum, naming và numeric output |
| Deserialization | Enum unknown, case sensitivity, aliases và constructor |
| Parser behavior | Trailing tokens, duplicate keys và non-standard JSON |
| Resource limits | StreamReadConstraints, request bytes, record count |
| Security | Polymorphic typing, subtype allowlist và payload logging |
| Module behavior | Java Time, JDK 8, Kotlin và custom modules |
| Framework integration | Spring Boot auto-configuration và converter order |
| Compatibility evidence | Golden fixtures, contract tests và MVC tests |
| Rollout | Staging, canary, metrics và rollback |

## 34. Kết luận

Đối chiếu thay đổi mặc định trước khi nâng Jackson là việc so sánh hành vi thực tế của ứng dụng, không chỉ so sánh giá trị mặc định của một ObjectMapper mới. Hành vi đó được hình thành từ Jackson core/databind, module, Spring Boot, bean cấu hình, converter, annotation và override theo reader/writer.

Hãy ghi lại dependency tree và mapper configuration, đọc release notes của toàn bộ khoảng nâng cấp, rồi dùng fixture độc lập để so sánh serialize, deserialize, coercion, null/missing, date/time, enum, parser constraints và security policy. Với mỗi thay đổi, quyết định rõ việc chấp nhận default mới, khóa hành vi cũ bằng cấu hình tường minh hay thay đổi contract có version. Chạy cùng contract tests trên version hiện tại và version đích, kiểm tra trong Spring context, triển khai có theo dõi và giữ rollback tương thích với dữ liệu. Cách làm này biến một lần nâng dependency thành một thay đổi có bằng chứng và có thể kiểm soát.
