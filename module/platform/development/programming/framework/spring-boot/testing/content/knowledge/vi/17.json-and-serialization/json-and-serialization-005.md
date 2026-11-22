# JSON và serialization trong Spring Boot: naming strategy, null, enum và định dạng ngày giờ

## 1. Vì sao bốn vấn đề này là một hợp đồng API?

Trong nhiều hệ thống Java, object nội bộ sử dụng camelCase, enum theo tên hằng và thời gian theo `java.time`. Nhưng JSON trả cho frontend/đối tác có thể dùng tên trường snake_case, bỏ trường null, công bố enum code dạng chữ thường và yêu cầu timestamp kèm offset. Ví dụ một Java record:

```java
record BookingEvent(
        String bookingId,
        String customerName,
        DeliveryState state,
        LocalDate travelDate,
        OffsetDateTime createdAt,
        String optionalNote) {}
```

Có thể cần tạo JSON theo **wire contract**:

```json
{
  "booking_id": "B-42",
  "customer_name": "Mai",
  "state": "queued",
  "travel_date": "08/11/2026",
  "created_at": "2026-11-08T09:30:00+07:00"
}
```

Trường `optional_note` bị bỏ vì giá trị Java bằng `null`. Enum `DeliveryState.QUEUED` xuất thành `"queued"` thay vì tên hằng `"QUEUED"`. `LocalDate` dùng định dạng ngày theo hợp đồng; `OffsetDateTime` giữ offset `+07:00` để người nhận không đoán múi giờ.

Nếu chỉ test service bằng `assertEquals` trên Java object, **bạn chưa kiểm tra JSON mà client thật nhận**. Bài học này xác định các lựa chọn Jackson và cách viết test để phát hiện những thay đổi phá vỡ hợp đồng JSON ngay cả khi service Java vẫn chạy đúng.

Bài dùng **Java 17, Spring Boot 3.3.x và Jackson 2.x** cho toàn bộ mã runnable. Spring Boot 4.x mặc định sử dụng Jackson 3, với các package/cấu hình có thay đổi; phần cuối ghi rõ cách đối chiếu khi nâng version thay vì trộn imports của hai dòng.

## 2. Mục tiêu học tập

Sau bài này bạn có thể:

1. Hiểu JSON serialization và deserialization, đặc biệt sự khác nhau giữa Java field name và external property name.
2. Cấu hình naming strategy ở cấp ứng dụng hoặc riêng DTO, biết khi nào `@JsonProperty`/`@JsonAlias` được dùng.
3. Phân biệt trường **bị thiếu**, trường có JSON `null`, chuỗi rỗng, collection rỗng và primitive default.
4. Dùng `@JsonInclude` để quyết định output null mà không nhầm với validation của input.
5. Thiết kế enum wire code ổn định với `@JsonValue`/`@JsonCreator`, tránh ordinal và tên hằng bị đổi ngầm.
6. Chọn đúng `LocalDate`, `Instant`, `OffsetDateTime`, `LocalDateTime`, format string và timezone/offset.
7. Biết ý nghĩa `JavaTimeModule` và tại sao `new ObjectMapper()` có thể khác mapper do Spring Boot cung cấp.
8. Viết `@JsonTest` + `JacksonTester` để kiểm tra JSON contract trực tiếp.
9. Viết `@WebMvcTest` + `MockMvc` để xác nhận HTTP request/response dùng đúng cấu hình Jackson.
10. Có một bộ regression tests cho round-trip, input sai, field thiếu/null và chính sách date-time khi nâng framework.

## 3. Hai chiều chuyển đổi phải được test riêng

**Serialization** chuyển object Java sang JSON:

```text
Java BookingEvent
    |
    +-- Property naming: bookingId -> booking_id
    +-- Inclusion rule: optionalNote=null -> bỏ trường
    +-- Enum encoder: QUEUED -> "queued"
    +-- Date/time formatter: LocalDate -> "08/11/2026"
    +-- Offset datetime -> "2026-11-08T09:30:00+07:00"
    v
JSON response
```

**Deserialization** chuyển JSON về object Java:

```text
JSON request
    |
    +-- Tìm đúng tên trường booking_id
    +-- Phân biệt absent và explicit null
    +-- Enum decoder: "queued" -> QUEUED
    +-- Parse ngày theo "dd/MM/yyyy"
    +-- Parse datetime kèm offset
    v
Java BookingEvent
```

Bản chất bất đối xứng:

- `@JsonInclude(NON_NULL)` quyết định **trường nào được ghi ra**. Nó **không** tự cấm client gửi JSON null, cũng không bắt field phải có ở đầu vào.
- `@JsonAlias` hỗ trợ **đọc** thêm tên cũ nhưng serialization vẫn dùng tên chính.
- `@JsonValue` quyết định wire value của enum; để kiểm soát chiều đọc và thông báo lỗi, thường bổ sung `@JsonCreator`.
- `@JsonFormat` có thể tác động cả đọc và ghi, nhưng cần hiểu kiểu thời gian cụ thể.
- Round-trip xanh là hữu ích, song **không đủ** nếu cả serializer và deserializer cùng thay đổi sai theo một hướng. Hãy có **expected JSON độc lập với production code**.

## 4. Cơ chế Jackson trong Spring Boot 3.3

Spring Boot 3.3 thường cung cấp một bean `com.fasterxml.jackson.databind.ObjectMapper` được cấu hình qua:

- Jackson 2 modules được phát hiện/đăng ký, bao gồm hỗ trợ `java.time` khi dependency phù hợp;
- các thuộc tính `spring.jackson.*`;
- `Jackson2ObjectMapperBuilderCustomizer` và các Jackson customization khác;
- annotations Jackson trên model/DTO như `@JsonNaming`, `@JsonInclude`, `@JsonValue`, `@JsonFormat`;
- custom `@JsonComponent`, `JsonSerializer`, `JsonDeserializer` hoặc Jackson `Module` nếu có.

Khi dùng `spring-boot-starter-web`, Jackson thường nằm trên classpath thông qua starter JSON. Spring MVC dùng HTTP message converters (ví dụ Jackson converter) để encode/decode `@RequestBody` và response body.

**Hai điểm cần nhớ:**

1. `ObjectMapper` được Spring Boot autoconfigure **có thể khác** một `new ObjectMapper()` thuần về module, naming, null inclusion và date/time features.
2. `@JsonTest` dùng **JSON test slice** với Jackson được autoconfigure theo scope đó; `@WebMvcTest` đưa thêm MVC converter/request handling. Không coi `@JsonTest` là full HTTP test.

### 4.1. Những thuộc tính Boot 3.3 liên quan

```properties
# Ví dụ cấu hình ứng dụng - không phải tất cả đều cần bật:
spring.jackson.property-naming-strategy=SNAKE_CASE
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.write-dates-as-timestamps=false
spring.jackson.deserialization.adjust-dates-to-context-time-zone=false
spring.jackson.time-zone=UTC
```

Các dòng ở đây là **những lựa chọn độc lập**; không cần copy tất cả vào mọi ứng dụng. Trong dự án mẫu bên dưới, naming và null được đặt trên DTO nhằm thể hiện tính cục bộ; chỉ hai feature date-time được đặt trong `application.properties` để hành vi nhất quán.

| Cấu hình | Mục đích trong Boot 3.3 |
| --- | --- |
| `spring.jackson.property-naming-strategy` | Chọn naming strategy cho Jackson properties, ví dụ `SNAKE_CASE` |
| `spring.jackson.default-property-inclusion` | Quy tắc inclusion mặc định như `non_null` |
| `spring.jackson.serialization.write-dates-as-timestamps` | Bật/tắt cách serialize ngày giờ thành timestamp/array theo loại |
| `spring.jackson.deserialization.adjust-dates-to-context-time-zone` | Cho phép/không cho phép điều chỉnh một số date-time có timezone về mapper context timezone |
| `spring.jackson.time-zone` | Timezone mặc định của mapper, ảnh hưởng những serializer/deserializer liên quan |
| `spring.jackson.date-format` | Date format mặc định chủ yếu cho `java.util.Date`/`Calendar`; **không coi là format phổ quát cho mọi `java.time`** |

**Phân biệt với `spring.mvc.format.*`:** nhóm `spring.mvc.format.date/time/date-time` chủ yếu cấu hình Spring MVC formatting/conversion cho dữ liệu như query/path/form. Nó không đồng nghĩa Jackson JSON serialization của `@RequestBody` hay response DTO.

## 5. Naming strategy: camelCase, snake_case, kebab-case

### 5.1. Một object, nhiều cách đặt tên

Java code:

```java
record CustomerInfo(
        String customerId,
        String firstName,
        String billingAddress) {}
```

Một số lựa chọn phổ biến của Jackson 2:

| Strategy | Tên Java | JSON property ví dụ |
| --- | --- | --- |
| Mặc định lower camel | `customerId` | `customerId` |
| `SNAKE_CASE` | `customerId` | `customer_id` |
| `KEBAB_CASE` | `customerId` | `customer-id` |
| `UPPER_CAMEL_CASE` | `customerId` | `CustomerId` |
| `LOWER_CASE` | `customerId` | `customerid` |

Đây là minh họa những chuyển đổi thông dụng. Với acronym, ký tự đặc biệt, Unicode, dấu gạch dưới sẵn có hoặc property getter không chuẩn, naming strategy có những quy tắc cụ thể; **test actual JSON** thay vì suy luận hoàn toàn bằng mắt.

### 5.2. Cấu hình cấp ứng dụng

Trong Spring Boot 3.3:

```properties
spring.jackson.property-naming-strategy=SNAKE_CASE
```

Khi Jackson mapper do Boot cung cấp nhận cấu hình này, các properties không có override cụ thể sẽ chuyển sang snake_case. Ưu điểm: nhất quán nếu toàn bộ API thống nhất quy ước. Rủi ro: thay một property global có thể đổi JSON của **mọi DTO** do mapper đó xử lý và phá backward compatibility.

**Không nên** sửa global naming chỉ để một endpoint mới trả snake_case, nếu các API cũ vẫn dùng camelCase. Với hợp đồng từng endpoint không đồng nhất, đặt annotation riêng trên DTO thích hợp an toàn hơn.

### 5.3. Cấu hình theo từng DTO

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record CustomerInfo(
        String customerId,
        String firstName,
        String billingAddress) {}
```

Mã minh họa này là một record cần đặt trong file `CustomerInfo.java`/package phù hợp; kết quả JSON sẽ dùng `customer_id`, `first_name` và `billing_address` nếu không có annotation override khác.

**Ưu điểm của `@JsonNaming`:** mô tả ngay external contract tại model, dễ review và không thay đổi DTO khác.

### 5.4. `@JsonProperty` và `@JsonAlias`

Khi một trường có tên được hợp đồng quy định cố định, dùng `@JsonProperty`:

```java
public record ClientInfo(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("displayName") String displayName) {}
```

Đây là snippet cần import `com.fasterxml.jackson.annotation.JsonProperty`. Tên chỉ định tường minh thường được ưu tiên hơn quy tắc naming chung.

Nếu muốn **đọc tên cũ** nhưng **ghi tên mới**:

```java
public record ClientInfo(
        @JsonProperty("customer_id")
        @JsonAlias({"customerId", "legacy_customer_code"})
        String customerId) {}
```

`@JsonAlias` là **deserialization-only**: nó không khiến JSON response xuất đồng thời cả ba key. Phương án này hữu ích trong quá trình chuyển API client sang `customer_id`; cần có test cho cả tên mới và tên alias.

**Lưu ý:** nếu client gửi đồng thời `customer_id` và `customerId` với giá trị mâu thuẫn, không nên lấy một thứ tự xử lý ngẫu nhiên làm business rule. Hãy định nghĩa chính sách yêu cầu một tên chuẩn và từ chối ambiguous input khi cần.

### 5.5. Map keys không phải POJO property names

`SNAKE_CASE` áp dụng naming cho **bean/record property names**. Nó **không bảo đảm tự chuyển mọi key động** trong `Map<String,Object>`. Ví dụ một Map chứa key `"customerId"` có thể vẫn serialize thành key đó. Muốn normalize Map keys, cần chiến lược riêng (chuyển key trước, custom key serializer hoặc explicit DTO).

Vì vậy, đừng test naming strategy bằng duy nhất một object Map nếu điều bạn muốn bảo vệ là DTO property naming.

## 6. Null: absent, explicit null, empty và default

JSON có nhiều trạng thái khác nhau:

```json
{"optional_note": null}
```

```json
{}
```

```json
{"optional_note": ""}
```

```json
{"optional_note": []}
```

Chúng **không** có cùng ý nghĩa hợp đồng:

| JSON | Ý nghĩa có thể dùng trong API |
| --- | --- |
| Field **không xuất hiện** | Client không cung cấp/không muốn thay đổi giá trị |
| `"field": null` | Client cung cấp một giá trị null tường minh, có thể yêu cầu xóa |
| `"field": ""` | Chuỗi rỗng, có thể hợp lệ hoặc invalid tùy validation |
| `"field": []` | Danh sách rỗng, khác null |
| `"field": 0` | Số không, khác null khi dùng wrapper type |

**Trong Java record chỉ dùng field nullable thông thường**, Jackson có thể gán cả field thiếu lẫn explicit null thành cùng giá trị `null`. Điều này **làm mất thông tin presence** nếu API PATCH cần phân biệt “không sửa” với “xóa”. Đừng dựa vào Java record `String` để suy ra một trong hai ý nghĩa đó mà không có cơ chế bổ sung.

### 6.1. `@JsonInclude` kiểm soát output

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiResult(
        String code,
        String optionalNote) {}
```

Snippet cần import `com.fasterxml.jackson.annotation.JsonInclude`. Với `new ApiResult("OK", null)`, serializer có thể tạo `{"code":"OK"}`; quy tắc chỉ kiểm soát **ghi JSON**, không cấm deserialization của null.

Một số lựa chọn:

| Include | Hành vi chính | Lưu ý |
| --- | --- | --- |
| `ALWAYS` | Ghi các properties theo mặc định, kể cả null | Trường null thường xuất hiện |
| `NON_NULL` | Không ghi property có giá trị Java null | Không tự loại empty string/list |
| `NON_EMPTY` | Không ghi null và các giá trị được Jackson coi là empty như `""`, empty collection/map | Tùy serializer/type; không coi mọi số 0 là empty |
| `NON_ABSENT` | Không ghi null/giá trị absent của reference types như `Optional.empty()` khi được hỗ trợ | Cần module kiểu JDK8 nếu dùng Optional |
| `NON_DEFAULT` | Không ghi giá trị được xác định là default theo ngữ cảnh | Semantics phụ thuộc class-level/global/value defaults; test riêng |

**Ngộ nhận phổ biến:** `NON_NULL` **không** đồng nghĩa “field optional” theo hợp đồng request. Một field bắt buộc của input vẫn cần validation riêng dù response serializer bỏ null.

### 6.2. Không nhầm `null` với field thiếu khi deserialization

Giả sử:

```java
public record PatchRequest(String displayName) {}
```

Khi deserialize `{}` hoặc `{"displayName":null}`, cả hai có thể thành `new PatchRequest(null)` với cấu hình Jackson thông thường. Nhưng với HTTP PATCH, thường cần:

- Field **không có**: không cập nhật.
- Field **có null**: xóa dữ liệu.
- Field **có giá trị**: cập nhật.

Có thể dùng `JsonNode.has(...)` và `JsonNode.isNull()` để quan sát presence, hoặc một kiểu wrapper thể hiện undefined/null/value (ví dụ thư viện JsonNullable phù hợp API) thay vì record thuần.

```java
JsonNode root = mapper.readTree(jsonText);
boolean provided = root.has("display_name");
boolean explicitlyNull =
        provided && root.get("display_name").isNull();
```

Đây là snippet cần `JsonNode`, `ObjectMapper` và biến `jsonText`. `root.has("display_name")` là true kể cả value là JSON null; `root.hasNonNull("display_name")` chỉ true nếu value không null. Kiểm tra key thiếu chính xác thay vì dùng `root.path(...).asText()` để suy luận.

### 6.3. Validation không phải JSON inclusion

`@NotNull`, `@NotBlank` và `@Valid` của Jakarta Bean Validation xử lý tính hợp lệ của request khi validator được kích hoạt. `@JsonInclude(NON_NULL)` không thay thế chúng.

- `@NotNull`: không chấp nhận Java null theo nhóm validation.
- `@NotBlank`: yêu cầu chuỗi khác null, có ký tự không phải whitespace.
- `@Valid`: kích hoạt validation nested/`@RequestBody` khi setup MVC và starter validation phù hợp.
- `@JsonSetter(nulls = Nulls.FAIL)`: có thể yêu cầu lỗi khi JSON đưa null vào property cụ thể, là một cơ chế deserialization khác validation.

**Đừng tự mặc định** tên field bắt buộc sẽ trả HTTP 400 chỉ vì bạn thêm `@JsonInclude`. Cần thiết lập validation/deserialization contract rồi viết negative test.

### 6.4. Primitive field có thể che input thiếu

`int quantity` và `boolean active` là primitives nên có default `0`/`false`. Nếu client bỏ trường, một số cách deserialize có thể gán default; sau đó rất khó biết đó là input thật hay missing. Với dữ liệu mà missing cần bị từ chối, cân nhắc wrapper `Integer`/`Boolean` và validation, hoặc property creator stricter rules.

## 7. Enum: tên Java không nên mặc nhiên là wire contract

Mặc định Jackson thường serialize enum bằng tên hằng:

```java
enum DeliveryState {
    QUEUED, SENT
}
```

Giá trị `DeliveryState.QUEUED` thường xuất thành `"QUEUED"`. Nếu API công bố code `"queued"`, việc đổi tên hằng, chữ hoa/thường hoặc bật `toString()` có thể phá client.

### 7.1. Vì sao không dùng ordinal?

`ordinal()` là vị trí enum trong khai báo, ví dụ QUEUED=0, SENT=1. Thêm một hằng ở đầu sẽ làm vị trí các hằng còn lại thay đổi. JSON number như `0` cũng khó hiểu và dễ biến thành coupling với thứ tự code.

**Khuyến nghị:** dùng **wire codes ổn định**, độc lập với enum constant name và ordinal.

### 7.2. `@JsonValue` và `@JsonCreator`

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum DeliveryState {
    QUEUED("queued"),
    SENT("sent");

    private final String wireCode;

    DeliveryState(String wireCode) {
        this.wireCode = wireCode;
    }

    @JsonValue
    public String wireCode() {
        return wireCode;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static DeliveryState fromWireCode(String code) {
        for (DeliveryState state : values()) {
            if (state.wireCode.equals(code)) {
                return state;
            }
        }
        throw new IllegalArgumentException(
                "Unknown delivery state: " + code);
    }
}
```

Đây là một enum Java 17 hoàn chỉnh khi lưu ở `DeliveryState.java`.

- `@JsonValue`: serialize `QUEUED` → `"queued"`.
- `@JsonCreator`: deserialize `"queued"` → `QUEUED`.
- Không phụ thuộc `name()`, `ordinal()`, `toString()`.
- Giá trị lạ như `"delayed"` ném exception trong creator, được Jackson bọc thành mapping exception khi đọc JSON. Trong HTTP MVC, lỗi decode request thường được chuyển thành 400 nếu không có error handler override.

Nếu muốn thêm state mới, cân nhắc tương thích của các client cũ; ngay cả khi server có thể xuất code mới, client chưa chắc hiểu được.

### 7.3. Có nên cho phép enum không biết?

Có vài chiến lược:

1. **Strict**: enum code lạ gây lỗi — phù hợp khi dữ liệu phải được kiểm soát chặt và client cần phản hồi rõ.
2. **Fallback `UNKNOWN`**: có hằng `@JsonEnumDefaultValue`, bật `DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` trong Jackson 2 nếu phù hợp.
3. **Map thành null**: `READ_UNKNOWN_ENUM_VALUES_AS_NULL` trong những trường hợp có quyết định rõ.

Không bật fallback toàn hệ thống chỉ để test xanh, vì nó có thể **che typo hoặc thay đổi API không tương thích**. `UNKNOWN` cần được xử lý có chủ đích ở nghiệp vụ; không coi nó mặc nhiên là một state hợp lệ.

**Không nhầm:** `@JsonEnumDefaultValue` một mình không có nghĩa feature “using default value” đã được bật trong mọi mapper/version. Test unknown enum input để xác nhận.

### 7.4. `@JsonFormat(shape=OBJECT)` cho enum?

Jackson cũng có thể serialize enum thành object chứa nhiều properties. Nhưng API dùng object `{"code":"queued","label":"Chờ gửi"}` khác schema so với string `"queued"`. Nếu hợp đồng chỉ yêu cầu một code ổn định, `@JsonValue` thường đơn giản hơn. Không tự bật enum object output rồi mong client string vẫn tương thích.

## 8. Date/time: chọn đúng Java type trước khi đặt format

| Kiểu Java | Biểu diễn | Có múi giờ/offset? | Dùng khi |
| --- | --- | --- | --- |
| `LocalDate` | Ngày lịch, ví dụ 2026-11-08 | **Không** | Ngày sinh, ngày đặt chỗ, kỳ hạn |
| `LocalTime` | Giờ trong ngày | Không | Giờ mở cửa theo lịch, cần zone riêng nếu quy đổi instant |
| `LocalDateTime` | Ngày + giờ local | **Không** | Lịch nội bộ khi có zone được quản lý riêng |
| `Instant` | Thời điểm tuyệt đối theo UTC timeline | Không mang zone ID; đại diện một instant | Audit createdAt, event timestamp |
| `OffsetDateTime` | Ngày giờ + offset như `+07:00` | **Có offset**, không nhất thiết có zone ID | API cần thời gian và offset rõ |
| `ZonedDateTime` | Ngày giờ + zone ID như `Asia/Ho_Chi_Minh` | Có zone ID và offset theo quy tắc | Lịch theo múi giờ khu vực/DST |
| `java.util.Date` | Kiểu legacy biểu diễn instant | Định dạng phụ thuộc mapper/timezone | Tương thích hệ thống cũ |

**Nguyên tắc:** chọn type theo ý nghĩa dữ liệu trước, rồi mới format JSON. Không dùng `LocalDateTime` cho “thời điểm tạo giao dịch toàn cầu” nếu client cần xác định instant độc lập múi giờ.

### 8.1. Offset khác zone ID

`+07:00` là **offset cố định** so với UTC. `Asia/Ho_Chi_Minh` là **ZoneId** chứa các quy tắc thời gian lịch sử và có thể khác về ý nghĩa so với một offset cố định ở các khu vực có DST. Với thời gian có daylight-saving, một local wall clock có thể mơ hồ hoặc không tồn tại trong một zone.

Nếu API cần chỉ một instant tuyệt đối, `Instant` chuẩn UTC thường dễ dùng. Nếu cần giữ thông tin người dùng đã khai báo `+07:00`, dùng `OffsetDateTime`. Nếu cần lịch tương lai theo vùng, có thể cần ZoneId song song với ngày/giờ local.

### 8.2. ISO-8601 và mẫu tùy biến

Với JavaTimeModule và Boot setup phù hợp, các `java.time` types thường có thể serialize thành ISO-8601-like strings. Nhưng **đừng dựa vào defaults như một hợp đồng không thay đổi**: cấu hình `WRITE_DATES_AS_TIMESTAMPS`, module, annotation và Jackson major version đều có thể ảnh hưởng.

Để quy định riêng một field:

```java
@JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd/MM/yyyy")
LocalDate travelDate
```

Để quy định offset datetime:

```java
@JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
OffsetDateTime createdAt
```

`@JsonFormat` từ `com.fasterxml.jackson.annotation`. Mẫu `XXX` biểu diễn offset dạng `+07:00` hoặc `Z` cho UTC; dấu `'T'` là ký tự literal. Trong demo dùng thời gian có giây nguyên để không cần quy định fraction precision.

### 8.3. Các token rất dễ dùng sai

| Token | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| `yyyy` | Year-of-era | Nhầm với tuần-năm khi dùng `YYYY` |
| `uuuu` | Proleptic year trong DateTimeFormatter | Cần chú ý nếu parse strict/era |
| `MM` | Tháng | Nhầm `mm` là phút |
| `dd` | Ngày trong tháng | Nhầm `DD` là ngày trong năm |
| `HH` | Giờ 0–23 | Nhầm `hh` là 1–12 không kèm AM/PM |
| `mm` | Phút | Nhầm `MM` là tháng |
| `ss` | Giây | Không biểu diễn millisecond |
| `SSS` | Millisecond/fraction 3 chữ số | Dữ liệu nanosecond dài hơn cần policy riêng |
| `XXX` | Offset dạng `+07:00`/`Z` | Không đồng nghĩa ZoneId |
| `'T'` | Ký tự T literal | Quên quote làm pattern không đúng |

Đặc biệt tránh `YYYY-MM-dd` cho ngày dương lịch: `YYYY` có thể là week-based year khác calendar year ở cuối/đầu năm. Test những ngày gần 31/12 và 01/01 để phát hiện lỗi này.

### 8.4. Timezone normalization khi deserialize

Một input như:

```json
{"created_at":"2026-11-08T09:30:00+07:00"}
```

đại diện cùng instant với `2026-11-08T02:30:00Z`. Trong Jackson 2, feature `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` có thể điều chỉnh một số kiểu date-time có offset/zone về mapper context timezone khi đọc.

Khi hợp đồng yêu cầu **giữ nguyên offset người gửi**, tắt feature đó cho mapper của ứng dụng/test theo phiên bản:

```properties
spring.jackson.deserialization.adjust-dates-to-context-time-zone=false
```

Nếu hợp đồng chỉ quan tâm instant, so sánh `toInstant()` thay vì so sánh string offset. Hai chuỗi với offset khác nhau có thể biểu diễn **cùng thời điểm**; test cần xác định muốn giữ *instant*, *offset* hay *local wall time*.

**Không thay đổi timezone của JVM trong từng test** để ép expected khớp. Điều đó ảnh hưởng global state và dễ gây test bất định khi chạy song song. Dùng dữ liệu có offset/zone tường minh và mapper/test configuration.

### 8.5. `spring.jackson.date-format` không thay hết `java.time`

Trong Boot 3.3:

```properties
spring.jackson.date-format=yyyy-MM-dd HH:mm:ss
```

thuộc tính này chủ yếu liên quan `java.util.Date`/`Calendar` và định dạng do Jackson legacy DateFormat xử lý. Nó **không phải công tắc đồng nhất** cho mọi `LocalDate`, `Instant` hay `OffsetDateTime` đã dùng JavaTimeModule. Muốn field JSON cụ thể theo format khác, dùng `@JsonFormat` hoặc serializer/deserializer `java.time` thích hợp.

Tương tự, `spring.mvc.format.date` liên quan Spring conversion của request params/path/form, không mặc nhiên đổi `@RequestBody` JSON.

## 9. Không tự dựng ObjectMapper rồi nghĩ giống Spring Boot

Một lỗi phổ biến:

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(
        OffsetDateTime.now());
```

Đây là **ví dụ về cách dễ gây lỗi**, không nên dùng làm test hợp đồng. Mapper thuần có thể **không** được đăng ký `JavaTimeModule` cho `OffsetDateTime`, tùy dependency/version, và không có `spring.jackson.*`/customizers của app. Kết quả có thể là exception kiểu “Java 8 date/time type not supported” hoặc JSON khác HTTP response thật.

Trong Spring Boot test, ưu tiên:

```java
@JsonTest
class JsonContractTest {
    @Autowired
    ObjectMapper mapper;
}
```

hoặc dùng `@Autowired JacksonTester<T>`. Chúng sử dụng cấu hình JSON được Boot dựng cho test slice. Nếu phải unit test mapper tự tạo, hãy cấu hình modules/features tường minh; **không** so sánh kết quả mapper thuần với HTTP rồi xem sự khác biệt là bug của controller.

### 9.1. JavaTimeModule là gì?

Với Jackson 2, `jackson-datatype-jsr310` cung cấp `JavaTimeModule` để serialize/deserialize `java.time`. `spring-boot-starter-json` trong Boot 3.3 bao gồm hỗ trợ này khi dependency được quản lý đúng. Nếu tự xây mapper, có thể cần:

```java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(
                DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE);
```

Đoạn này là **mẫu mapper riêng**, cần imports từ `com.fasterxml.jackson.*`; không nên tạo một mapper riêng cho từng controller mà không có lý do, vì có thể bỏ sót cấu hình global của ứng dụng.

### 9.2. Cấu hình singleton ObjectMapper có thể ảnh hưởng toàn app

`ObjectMapper` bean thường được chia sẻ. Đừng gọi `mapper.setPropertyNamingStrategy(...)` tùy tiện trong một test rồi để nó rò sang test khác qua context cache. Nếu muốn thay mapper cho một test riêng, dùng test properties/configuration phân lập hoặc `mapper.copy()` để tạo instance riêng.

Các tùy chỉnh Jackson nên được áp dụng **trước khi mapper được dùng**; cấu hình mutable mapper sau lần đọc/ghi đầu tiên có thể tạo hành vi khó dự đoán hoặc không an toàn khi chạy song song.

## 10. Dự án runnable: Java 17, Spring Boot 3.3.0, Jackson 2

Dự án sau bảo vệ đồng thời **naming, null, enum và ngày giờ** qua:

- Test JSON thuần bằng `@JsonTest`/`JacksonTester`.
- Test naming strategy global bằng `@TestPropertySource` trong JSON slice riêng.
- Test HTTP JSON ở tầng MVC bằng `@WebMvcTest`/`MockMvc`.
- Negative tests với enum code lạ và ngày sai.
- Test phân biệt null/missing ở góc độ `JsonNode`, không giả vờ rằng DTO nullable luôn giữ được thông tin presence.

### 10.1. Cây thư mục

```text
booking-json-contract/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── resources/
    │   │   └── application.properties
    │   └── java/example/json/
    │       ├── JsonDemoApplication.java
    │       ├── DeliveryState.java
    │       ├── BookingEvent.java
    │       ├── BookingQueryService.java
    │       └── BookingController.java
    └── test/java/example/json/
        ├── BookingEventJsonTest.java
        ├── GlobalNamingJsonTest.java
        └── BookingControllerWebTest.java
```

### 10.2. Gradle settings

**`settings.gradle`:**

```groovy
rootProject.name = 'booking-json-contract'
```

### 10.3. Gradle build

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.0 dùng Jackson 2.x được BOM quản lý. `spring-boot-starter-web` kéo theo Jackson/Jackson Java time support phù hợp; `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, JSON test helpers, Mockito, MockMvc và Spring Test. Ví dụ không dùng database, Docker hay dịch vụ ngoài.

Dùng Gradle Wrapper tương thích với JDK17/Boot3.3 (ví dụ Gradle 8.5), không ép một version Jackson khác riêng lẻ rồi kỳ vọng BOM test vẫn đồng bộ.

### 10.4. App-level date-time features

**`src/main/resources/application.properties`:**

```properties
# JSON java.time phải ghi thành string thay vì timestamp/array.
spring.jackson.serialization.write-dates-as-timestamps=false

# Khi đọc OffsetDateTime, giữ offset từ JSON thay vì đổi về mapper context zone.
spring.jackson.deserialization.adjust-dates-to-context-time-zone=false
```

Hai dòng được giữ **cố định** trong demo, dùng cả cho JSON slice và MVC web slice. Naming/null không được đặt global, vì `BookingEvent` sẽ dùng annotations trên DTO. Điều này giúp các test chứng minh lớp nào quyết định behavior.

Nếu API thực tế muốn normalize mọi timestamps sang UTC, có thể chọn contract khác. Khi ấy **không** sao chép việc tắt timezone adjustment một cách máy móc; hãy dùng `Instant`/mapper configuration phù hợp và assert instant đúng.

### 10.5. Spring Boot application

**`src/main/java/example/json/JsonDemoApplication.java`:**

```java
package example.json;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` đặt cùng package gốc giúp Boot scan service/controller. Với `@JsonTest`, test slice chủ yếu nạp JSON infrastructure chứ không khởi chạy web server.

### 10.6. Enum wire contract

**`src/main/java/example/json/DeliveryState.java`:**

```java
package example.json;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum DeliveryState {
    QUEUED("queued"),
    SENT("sent");

    private final String wireCode;

    DeliveryState(String wireCode) {
        this.wireCode = wireCode;
    }

    @JsonValue
    public String wireCode() {
        return wireCode;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static DeliveryState fromWireCode(String code) {
        for (DeliveryState state : values()) {
            if (state.wireCode.equals(code)) {
                return state;
            }
        }
        throw new IllegalArgumentException(
                "Unknown delivery state: " + code);
    }
}
```

Với type này: Java `DeliveryState.QUEUED` → JSON `"queued"`; JSON `"sent"` → Java `DeliveryState.SENT`; JSON `"delayed"` gây lỗi decode. Bởi vì wire code được gán tường minh, đổi Java enum constant name (nếu không đổi wireCode) không nhất thiết đổi external wire contract.

**Không nên** phát enum ordinal như 0/1. Thêm enum values có thể làm dịch chuyển ordinal.

### 10.7. DTO: naming + null + date/time format

**`src/main/java/example/json/BookingEvent.java`:**

```java
package example.json;

import java.time.LocalDate;
import java.time.OffsetDateTime;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@JsonInclude(JsonInclude.Include.NON_NULL)
public record BookingEvent(
        String bookingId,
        String customerName,
        DeliveryState state,
        @JsonFormat(
                shape = JsonFormat.Shape.STRING,
                pattern = "dd/MM/yyyy")
        LocalDate travelDate,
        @JsonFormat(
                shape = JsonFormat.Shape.STRING,
                pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
        OffsetDateTime createdAt,
        String optionalNote) {}
```

Mỗi annotation có nhiệm vụ khác nhau:

- `@JsonNaming(...SnakeCaseStrategy.class)`: Java `bookingId` → JSON `booking_id`.
- `@JsonInclude(NON_NULL)`: `optionalNote = null` → không có property `optional_note` khi **ghi** JSON.
- `DeliveryState` có serializer/deserializer riêng từ `@JsonValue`/`@JsonCreator`.
- `travelDate` theo `dd/MM/yyyy`, ví dụ `08/11/2026`.
- `createdAt` theo pattern có `XXX`, ví dụ `2026-11-08T09:30:00+07:00`.

**Chú ý Java record:** Jackson 2 trong Boot 3.3 hỗ trợ records. Các annotation gắn lên record components được Jackson nhận khi xử lý properties. Với POJO JavaBeans truyền thống, có thể đặt annotations trên field/getter/constructor parameter theo cách mapper introspection thực sự sử dụng; test ngay trên class production thay vì đoán.

### 10.8. Service đơn giản phục vụ MVC test

**`src/main/java/example/json/BookingQueryService.java`:**

```java
package example.json;

import java.time.LocalDate;
import java.time.OffsetDateTime;

import org.springframework.stereotype.Service;

@Service
public class BookingQueryService {
    public BookingEvent find(String bookingId) {
        return new BookingEvent(
                bookingId,
                "Mai",
                DeliveryState.QUEUED,
                LocalDate.of(2026, 11, 8),
                OffsetDateTime.parse(
                        "2026-11-08T09:30:00+07:00"),
                null);
    }
}
```

Đây là service demo không gọi database/HTTP. `@WebMvcTest` sẽ mock service để tập trung vào JSON/MVC boundary; không cần toàn application context.

### 10.9. Controller với GET và POST echo

**`src/main/java/example/json/BookingController.java`:**

```java
package example.json;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {
    private final BookingQueryService service;

    public BookingController(BookingQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public BookingEvent get(@PathVariable String id) {
        return service.find(id);
    }

    @PostMapping("/echo")
    public BookingEvent echo(@RequestBody BookingEvent body) {
        return body;
    }
}
```

Endpoint `echo` chỉ phục vụ minh họa **deserialization + serialization qua Spring MVC**. Đây không phải API production bắt buộc; ứng dụng thật nên có business contract, validation và security thích hợp.

## 11. Test 1 — `@JsonTest` bảo vệ toàn bộ JSON wire contract

**`src/test/java/example/json/BookingEventJsonTest.java`:**

```java
package example.json;

import java.time.LocalDate;
import java.time.OffsetDateTime;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JsonTest
class BookingEventJsonTest {
    @Autowired
    JacksonTester<BookingEvent> json;

    @Autowired
    ObjectMapper mapper;

    private BookingEvent sample() {
        return new BookingEvent(
                "B-42",
                "Mai",
                DeliveryState.QUEUED,
                LocalDate.of(2026, 11, 8),
                OffsetDateTime.parse(
                        "2026-11-08T09:30:00+07:00"),
                null);
    }

    private String validJson() {
        return """
                {
                  "booking_id": "B-42",
                  "customer_name": "Mai",
                  "state": "queued",
                  "travel_date": "08/11/2026",
                  "created_at": "2026-11-08T09:30:00+07:00"
                }
                """;
    }

    @Test
    void serializeUsesSnakeCaseEnumCodeAndDateFormats()
            throws Exception {
        String output = json.write(sample()).getJson();
        JsonNode root = mapper.readTree(output);

        assertEquals("B-42",
                root.path("booking_id").asText());
        assertEquals("Mai",
                root.path("customer_name").asText());
        assertEquals("queued",
                root.path("state").asText());
        assertEquals("08/11/2026",
                root.path("travel_date").asText());
        assertEquals("2026-11-08T09:30:00+07:00",
                root.path("created_at").asText());

        assertFalse(root.has("bookingId"));
        assertFalse(root.has("createdAt"));
        assertFalse(root.has("optional_note"));
    }

    @Test
    void deserializationPreservesValuesAndOffset()
            throws Exception {
        BookingEvent event = json.parseObject(validJson());

        assertEquals(sample(), event);
        assertEquals("+07:00",
                event.createdAt().getOffset().toString());
        assertEquals(
                OffsetDateTime.parse(
                        "2026-11-08T02:30:00Z").toInstant(),
                event.createdAt().toInstant());
    }

    @Test
    void missingAndExplicitNullBothBecomeNullInPlainRecord()
            throws Exception {
        JsonNode root = mapper.readTree(validJson());
        assertFalse(root.has("optional_note"));

        BookingEvent missing =
                mapper.treeToValue(root, BookingEvent.class);
        assertNull(missing.optionalNote());

        ObjectNode withNull = (ObjectNode) root.deepCopy();
        withNull.putNull("optional_note");

        assertTrue(withNull.has("optional_note"));
        assertTrue(withNull.get("optional_note").isNull());

        BookingEvent explicit =
                mapper.treeToValue(withNull, BookingEvent.class);
        assertNull(explicit.optionalNote());
    }

    @Test
    void unknownEnumCodeFailsInsteadOfSilentlyMapping()
            throws Exception {
        String invalid = validJson().replace(
                "\"queued\"", "\"delayed\"");

        assertThrows(JsonProcessingException.class,
                () -> mapper.readValue(
                        invalid, BookingEvent.class));
    }

    @Test
    void invalidCalendarDateFailsOnDecode() {
        String invalid = validJson().replace(
                "08/11/2026", "not-a-date");

        assertThrows(JsonProcessingException.class,
                () -> mapper.readValue(
                        invalid, BookingEvent.class));
    }
}
```

### 11.1. Test này thực sự kiểm tra gì?

- JSON field names `booking_id` và `created_at`, đồng thời loại trừ camelCase trong output.
- `optional_note` không có mặt khi Java value null (không chỉ kiểm tra `path(...).asText()` rỗng).
- Enum `QUEUED` được ghi thành `"queued"`; code lạ bị từ chối.
- `LocalDate` và `OffsetDateTime` tuân thủ patterns tường minh.
- Khi đọc, OffsetDateTime giữ offset `+07:00` nhờ cấu hình Boot test mapper, đồng thời biểu diễn đúng instant UTC `02:30:00Z`.
- Input thiếu `optional_note` và input null tường minh đều thành Java null trong record thuần, minh họa vì sao PATCH có thể cần kiểu biểu diễn presence riêng.
- Date text sai bị báo lỗi decode, không bị tự chuyển thành một ngày giả định.

### 11.2. Vì sao assert JSON bằng JsonNode?

`JsonNode` cho phép kiểm tra field **vắng mặt** bằng `has` thay vì dùng `asText()` — bởi `MissingNode` có thể tạo ra string rỗng khiến test nhầm giữa missing và empty. Đồng thời ta không phụ thuộc thứ tự JSON keys/whitespace.

Ngoài `ObjectMapper.readTree`, Spring Boot `JacksonTester` còn có AssertJ JSON assertions, ví dụ:

```java
assertThat(json.write(sample()))
        .extractingJsonPathStringValue("@.booking_id")
        .isEqualTo("B-42");
```

Đoạn này yêu cầu static import AssertJ `assertThat`; trong bài mẫu chính dùng JsonNode + JUnit để khẳng định mọi trạng thái presence cụ thể.

### 11.3. Bảo vệ fixed expected thay vì chỉ round-trip

Nếu serializer vô tình đổi `booking_id` thành `bookingId` và deserializer cũng đổi tương ứng, một test chỉ serialize rồi deserialize lại có thể **vẫn pass**. Vì vậy test `serializeUses...` assert JSON keys/value cụ thể độc lập, còn `deserializationPreserves...` kiểm tra chiều đọc. Bộ đôi này bắt được nhiều regression hơn.

## 12. Test 2 — Chiến lược naming cấp ứng dụng

Để chứng minh cấu hình `spring.jackson.property-naming-strategy=SNAKE_CASE` tác động lên DTO **không có `@JsonNaming`**, tạo một JSON slice riêng với test property.

**`src/test/java/example/json/GlobalNamingJsonTest.java`:**

```java
package example.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@JsonTest
@TestPropertySource(properties =
        "spring.jackson.property-naming-strategy=SNAKE_CASE")
class GlobalNamingJsonTest {
    @Autowired
    ObjectMapper mapper;

    record PlainEnvelope(
            String trackingId,
            String customerEmail) {}

    @Test
    void globalStrategyAppliesToUnannotatedRecord()
            throws Exception {
        String result = mapper.writeValueAsString(
                new PlainEnvelope(
                        "TRK-7", "mai@example.test"));

        JsonNode root = mapper.readTree(result);

        assertEquals("TRK-7",
                root.path("tracking_id").asText());
        assertEquals("mai@example.test",
                root.path("customer_email").asText());
        assertFalse(root.has("trackingId"));
        assertFalse(root.has("customerEmail"));
    }
}
```

Điểm cần nắm:

- `PlainEnvelope` không có `@JsonNaming`: naming đến từ property của Spring Boot.
- Property chỉ được thiết lập trong **test class context này**, không tự sửa production config.
- Nếu bạn chuyển property global trong một app lớn, các DTO không có override có thể đổi đồng loạt. Cần regression tests cho schema public API.
- Các test contexts có properties khác nhau có thể có **cache keys khác nhau**; đó là hành vi bình thường của Spring TestContext.

## 13. Test 3 — JSON qua Spring MVC HTTP boundary với MockMvc

`@JsonTest` là nơi tốt nhất để test serializer/deserializer tập trung. Nhưng cũng cần biết Spring MVC thật dùng Jackson configuration đó cho `@RequestBody` và response.

**`src/test/java/example/json/BookingControllerWebTest.java`:**

```java
package example.json;

import java.time.LocalDate;
import java.time.OffsetDateTime;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookingController.class)
class BookingControllerWebTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockBean
    BookingQueryService service;

    private BookingEvent sample() {
        return new BookingEvent(
                "B-42",
                "Mai",
                DeliveryState.QUEUED,
                LocalDate.of(2026, 11, 8),
                OffsetDateTime.parse(
                        "2026-11-08T09:30:00+07:00"),
                null);
    }

    @Test
    void getRendersPublicWireContract() throws Exception {
        when(service.find("B-42"))
                .thenReturn(sample());

        mvc.perform(get("/api/bookings/B-42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.booking_id")
                        .value("B-42"))
                .andExpect(jsonPath("$.customer_name")
                        .value("Mai"))
                .andExpect(jsonPath("$.state")
                        .value("queued"))
                .andExpect(jsonPath("$.travel_date")
                        .value("08/11/2026"))
                .andExpect(jsonPath("$.created_at")
                        .value(
                                "2026-11-08T09:30:00+07:00"))
                .andExpect(jsonPath("$.optional_note")
                        .doesNotExist());

        verify(service).find("B-42");
    }

    @Test
    void postEchoDecodesAndReencodesJson()
            throws Exception {
        String payload = mapper.writeValueAsString(
                sample());

        mvc.perform(post("/api/bookings/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.booking_id")
                        .value("B-42"))
                .andExpect(jsonPath("$.state")
                        .value("queued"))
                .andExpect(jsonPath("$.travel_date")
                        .value("08/11/2026"))
                .andExpect(jsonPath("$.created_at")
                        .value(
                                "2026-11-08T09:30:00+07:00"));
    }

    @Test
    void postRejectsUnknownEnumWireCode()
            throws Exception {
        String payload = mapper.writeValueAsString(
                sample()).replace(
                        "\"queued\"", "\"delayed\"");

        mvc.perform(post("/api/bookings/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isBadRequest());
    }
}
```

### 13.1. Điều được chứng minh

- `@WebMvcTest` cấu hình MVC controller và HTTP message converters của slice.
- `@MockBean BookingQueryService` cung cấp dependency ngoài slice, nhưng service thật **không được kiểm tra**.
- GET trả snake_case, null bị bỏ, enum wire code đúng và date/time format đúng ở **response HTTP giả lập**.
- POST decode cùng định dạng thành `BookingEvent` và echo thành JSON theo contract.
- Enum code `delayed` không parse được sẽ làm request body decode fail; với MVC error handling mặc định của ví dụ, status 400.
- Không mở embedded TCP server, không chứng minh database/remote client.

### 13.2. Tại sao vẫn cần test JSON thuần?

HTTP GET có thể pass trong khi một chiều deserialization không được test; POST echo giúp thêm chiều đọc nhưng vẫn không kiểm tra được field presence một cách chi tiết như `JsonNode`. `@JsonTest` chạy nhẹ và gắn trực tiếp với contract DTO; `@WebMvcTest` bảo đảm MVC layer sử dụng cấu hình JSON ấy.

**Lưu ý về response error:** test chỉ assert status 400 cho enum code sai. Spring Boot/Spring MVC có thể thay đổi default error body schema theo version/configuration; không assert raw stack trace hoặc một error JSON code chưa được triển khai qua `@ControllerAdvice`.

## 14. Chạy dự án và kết quả dự kiến

Với JDK 17, Gradle Wrapper tương thích và dependencies đã được tải:

```bash
./gradlew test
./gradlew test --tests example.json.BookingEventJsonTest
./gradlew test --tests example.json.GlobalNamingJsonTest
./gradlew test --tests example.json.BookingControllerWebTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.json.BookingEventJsonTest
```

Dự kiến **9 test methods pass**: `BookingEventJsonTest` có 5, `GlobalNamingJsonTest` có 1, `BookingControllerWebTest` có 3. Khi tất cả Gradle tasks hoàn tất, thường thấy `BUILD SUCCESSFUL`. Không có stdout nghiệp vụ cố định; Boot có thể in startup/test logs, nhưng chúng **không phải** assertions.

**Mục tiêu thực hành:** không cần Docker, database, network hay bên thứ ba. Một lỗi JSON contract sẽ làm ít nhất một assertion cụ thể thất bại; đọc failed test name và actual JSON để biết naming/null/enum/date nào bị thay đổi.

### 14.1. Bảng kết quả cần mong đợi

| Kịch bản | Kết quả |
| --- | --- |
| Serialize `BookingEvent` | `booking_id`/`created_at` snake_case |
| `optionalNote = null` | Không có `optional_note` |
| `DeliveryState.QUEUED` | JSON `"queued"` |
| `travelDate = 2026-11-08` | JSON `"08/11/2026"` |
| `createdAt = ...+07:00` | JSON giữ `+07:00` trong pattern |
| Deserialization JSON hợp lệ | Tạo record giá trị đúng |
| JSON thiếu `optional_note` | Java `optionalNote == null` |
| JSON `optional_note:null` | Java `optionalNote == null` |
| Enum `"delayed"` | Parse lỗi; HTTP POST echo 400 |
| `travel_date:"not-a-date"` | Parse lỗi |
| Global SNAKE_CASE của record không annotation | `tracking_id`, `customer_email` |

### 14.2. Hai loại lỗi thường bị đọc nhầm

- **JSON test fail**: có thể do naming/date/enum format thay đổi, thiếu JavaTimeModule hoặc Jackson customizer được áp dụng sai.
- **MVC test fail nạp context**: có thể do missing `BookingQueryService` mock, package scan hoặc web/security auto-config. Đây là vấn đề test scope/bean graph, không nhất thiết là Jackson.

Đừng sửa lỗi code JSON bằng cách bật `@SpringBootTest` full context ngay lập tức. Xác định rõ context đang thiếu bean hay JSON serializer trả sai output.

## 15. @JsonTest hay @SpringBootTest?

| Mục tiêu | Phương án phù hợp | Điều chưa chứng minh |
| --- | --- | --- |
| DTO serialization/deserialization | `@JsonTest` + `JacksonTester` | HTTP routing, service, DB |
| Global Jackson naming/property override | `@JsonTest` + test properties | Runtime endpoint/network |
| Controller trả JSON/schema đúng | `@WebMvcTest` + `MockMvc` | Service thật, DB, embedded server |
| Controller-service phối hợp với repositories | `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | TCP/embedded server |
| Client gửi HTTP qua server thật | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Ingress/TLS/load balancer bên ngoài |
| Reactive WebFlux contract | `@WebFluxTest` + `WebTestClient` | Full reactive app mặc định |
| JSON của outbound WebClient | Client/mock HTTP server integration | Không tự chứng minh endpoint inbound |

**Quy tắc:** Nếu thay đổi chỉ liên quan DTO naming/null/date, test `@JsonTest` thường là phản hồi nhanh nhất. Nhưng một số ít HTTP tests giúp phát hiện converter hoặc configuration ở web boundary khác mapper được dùng trong test thuần.

## 16. Tại sao output JSON có thể khác khi chạy thật?

Một số nguyên nhân hay gặp:

1. **Mapper không cùng một bean:** test tạo `new ObjectMapper()`, MVC dùng Boot mapper.
2. **Global strategy khác:** `spring.jackson.property-naming-strategy` giữa test/profile và production không giống.
3. **Mix-in hoặc `@JsonView`:** thay đổi property visibility chỉ ở endpoint cụ thể.
4. **Custom Jackson Module/@JsonComponent`:** slice test không tự import hết module cần thiết nếu configuration bị exclude.
5. **Controller dùng `String` response thay vì object:** Spring MVC có thể gửi string nguyên văn, không serialize qua Jackson theo cùng đường.
6. **`ResponseEntity` và content negotiation:** `Accept`/`Content-Type` ảnh hưởng converter được chọn.
7. **Date-time modules và features:** `WRITE_DATES_AS_TIMESTAMPS`, timezone adjustment, custom formatter khác.
8. **Global inclusion vs DTO override:** `@JsonInclude` cụ thể có thể làm field bị bỏ dù application default là ALWAYS.
9. **Version/library khác:** Jackson 2 vs Jackson 3; annotations, serializers hoặc defaults không nhất thiết giống.
10. **Getter/is-getter vs field visibility:** với POJO có getters và annotations đặt không nhất quán, Jackson property introspection có thể tạo tên/property khác mong muốn.

**Tư duy debug:** so sánh **cùng object**, **cùng ObjectMapper configuration**, **cùng JSON serializer path** trước khi kết luận lỗi ở DTO.

## 17. Naming strategy và schema evolution

Đổi từ camelCase sang snake_case trong một public API có thể là **breaking change** dù mã Java không thay đổi. Client đang gọi `response.customerId` có thể nhận undefined khi server bắt đầu gửi `customer_id`.

Chiến lược chuyển tiếp:

- Công bố versioned API hoặc kế hoạch chuyển đổi.
- Dùng `@JsonAlias` trong **deserialization** để đọc tên cũ và mới khi thích hợp.
- Chỉ serialize ra một tên chuẩn theo contract, tránh gửi hai keys không có nghĩa nếu không được thiết kế.
- Test cả client legacy request input và response output mới.
- Nếu nhiều API có conventions khác nhau, dùng DTO per endpoint/version thay vì bật global naming cho toàn bộ ObjectMapper.

Ví dụ cho phép client gửi input cũ:

```java
public record UserRequest(
        @JsonProperty("customer_id")
        @JsonAlias("customerId")
        String customerId) {}
```

Code cần imports Jackson. Serialization của `UserRequest` vẫn xuất `customer_id`, còn `customerId` được chấp nhận ở chiều đọc khi mapper hỗ trợ alias theo annotations.

**Không tự suy luận** bật alias là hoàn tất migration. Nếu hai trường đều được gửi, validation/biz logic cần quy tắc giải quyết ambiguity; schema docs và client tests cũng phải được cập nhật.

## 18. Enum thay đổi là thay đổi protocol

Giả sử hệ thống bổ sung state mới `RETRYING("retrying")`. Server có thể serialize code đó, nhưng client cũ chỉ biết `queued`/`sent`. Những client dùng exhaustive switch có thể fail.

Khi mở rộng enum:

1. Xem client contract có cho phép giá trị lạ không.
2. Nếu không, version API hoặc rollout client trước server.
3. Nếu cho phép, thiết kế client fallback `UNKNOWN` có quan sát/metric.
4. Giữ wire code ổn định, không rename `"queued"` thành `"waiting"` chỉ vì rename Java enum.
5. Test serializer **và** deserializer, cộng negative cases.
6. Không tự ý bật `READ_UNKNOWN_ENUM_VALUES_AS_NULL` toàn cục nếu null có nghĩa khác.

**Thực hành tốt:** enum value là dữ liệu giao thức, không chỉ implementation detail của Java source.

## 19. Null omission và PATCH semantics

Xét API PATCH:

```json
{"display_name":"Mai"}
```

và:

```json
{"display_name":null}
```

Có thể mong muốn:

- PATCH thiếu `display_name`: không động tới tên hiện tại.
- PATCH có `display_name:null`: xóa tên.

Nếu deserialize cả hai vào `record Patch(String displayName)` rồi xử lý `if (displayName == null)`, bạn không phân biệt được yêu cầu xóa với không cập nhật.

Một giải pháp ở mức payload tree:

```java
JsonNode body = mapper.readTree(jsonText);
if (body.has("display_name")) {
    if (body.get("display_name").isNull()) {
        // Có yêu cầu xóa tên (nếu business contract cho phép).
    } else {
        String newName = body.get("display_name").asText();
        // Cập nhật sau khi validation.
    }
}
```

Đây là snippet mô tả ý tưởng, cần xử lý kiểu dữ liệu và validation cẩn thận. Với API quy mô lớn, có thể dùng typed wrapper biểu diễn `UNDEFINED`/`NULL`/`VALUE` để giữ strong typing.

**Đừng dùng `@JsonInclude(NON_NULL)` trên request DTO rồi nghĩ parser sẽ biết ý định PATCH.** Annotation ấy là quy tắc output, không phải cơ chế tracking field presence lúc đọc.

## 20. Định dạng thời gian là business contract

### 20.1. Ngày lịch khác instant

Ngày bay `2026-11-08` không phải instant. Chuyển nó thành UTC timestamp 00:00:00Z có thể khiến người ở timezone âm thấy **ngày trước đó**. Dùng `LocalDate` cho lịch ngày nếu hợp đồng thực sự chỉ nói ngày.

### 20.2. Timestamp có timezone rõ

Với createdAt của một event toàn cầu, có hai hợp đồng phổ biến:

- **Instant canonical UTC:** `2026-11-08T02:30:00Z`.
- **OffsetDateTime giữ offset nhập:** `2026-11-08T09:30:00+07:00`.

Chúng có thể chỉ cùng một instant. Test nên quyết định phải assert **text offset** hay chỉ `toInstant()`. Nếu client cần hiển thị timezone region (DST/luật vùng), chỉ offset có thể chưa đủ.

### 20.3. Thời gian có giây lẻ/nanoseconds

Java `Instant`/`OffsetDateTime` có thể giữ precision đến nanosecond. Một API chỉ muốn milliseconds cần quy tắc làm tròn/cắt rõ ràng. `@JsonFormat(pattern = "...SSSXXX")` biểu diễn 3 chữ số phần giây; nhưng nếu dữ liệu có precision lớn hơn, cần xác định việc truncate/round và assert trên giá trị biên.

Tránh so sánh `OffsetDateTime.now()` trong test: thời điểm hiện tại thay đổi liên tục. Dùng một fixed timestamp từ `parse(...)` hoặc inject `Clock` để kiểm soát dữ liệu.

### 20.4. Locale và chuỗi ngày giờ

Nếu format sử dụng tên tháng/ngày (ví dụ `MMM`), locale có thể ảnh hưởng output. Cấu hình `@JsonFormat(locale=...)` hoặc formatter riêng khi contract quy định. Với pattern chỉ số như `dd/MM/yyyy` trong demo, tránh phụ thuộc locale để bài test ổn định.

### 20.5. Các mốc lịch đặc biệt

Test thêm:

- Ngày 29/02 năm nhuận và ngày không hợp lệ.
- 31/12 và 01/01 để bắt lỗi `YYYY` vs `yyyy`.
- Trước/sau DST transition nếu dùng ZoneId ở vùng có daylight-saving.
- Offset `Z`, `+00:00`, `+07:00`, `-05:00` nếu contract chấp nhận.
- Giây lẻ 0, 3, 6 hoặc 9 chữ số nếu API quyết định precision.
- Timestamp rất cũ (trước 1970) hoặc rất xa nếu nghiệp vụ yêu cầu.

Một “test ngày hôm nay” chạy xanh không chứng minh formatter đúng tại các boundary.

## 21. JsonTesters, golden files và JSONPath

Spring Boot `JacksonTester<T>` có thể so JSON với resource file, dùng AssertJ helpers:

```java
assertThat(json.write(sample()))
        .isEqualToJson("expected-booking.json");
```

Ví dụ này yêu cầu file JSON fixture ở vị trí mà JacksonTester tìm theo class test/resource, không có trong project runnable vì bài đã dùng explicit JsonNode assertions thay thế.

Ưu điểm golden JSON:

- Là **hợp đồng bên ngoài** rõ ràng, dễ review trong pull request.
- Phát hiện property name hoặc enum wire code đổi.
- Thích hợp DTO lớn và nested structures.

Nhược điểm:

- Snapshot quá lớn dễ được cập nhật máy móc mà không review API compatibility.
- UUID, timestamp, generated IDs làm golden JSON không ổn định nếu không kiểm soát.
- Một số JSON comparison options bỏ qua field thừa hoặc thứ tự array; phải chọn strictness theo contract.

**Không tự động “update snapshot” khi test đỏ**. Trước tiên xác định thay đổi là chủ đích hay regression.

## 22. Kiểm tra output đúng mà không phụ thuộc implementation

Trong tests của bài:

- Expected `"queued"` là external enum code, không suy ra từ `DeliveryState.QUEUED.name().toLowerCase()`. Nếu code production đổi sai, expected vẫn bắt được.
- Expected `"08/11/2026"` là string hợp đồng, không format bằng cùng formatter production rồi so sánh.
- Expected property `booking_id` là fixed JSON key, không chạy cùng naming strategy để tự tính expected.
- Tự tạo `new BookingEvent(...)` trong test là okay; dùng service production để tạo cả expected và actual có thể làm test che lỗi.
- Với timezone, xác minh cả wire string cần giữ offset và instant tương đương khi contract yêu cầu cả hai.

Đây là **test oracle độc lập**: expected phải có nguồn từ yêu cầu API, không đơn giản lặp lại cách implement.

## 23. Các lỗi phổ biến và hướng chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| JSON có `bookingId` thay vì `booking_id` | Chưa cấu hình naming hoặc dùng mapper khác | Kiểm tra `@JsonNaming`/global strategy và mapper thực |
| Một DTO đổi tên trường, DTO khác không | Annotation class-level hoặc `@JsonProperty` override | Review phạm vi type vs global |
| `@JsonAlias` “không xuất thêm alias” | Alias chỉ dành cho deserialization | Dùng tên chuẩn khi serialize |
| Map key không thành snake_case | Naming strategy thường áp dụng POJO property | Chuyển Map key có chủ đích/custom serializer |
| Field null vẫn xuất | `ALWAYS` default hoặc inclusion config không áp dụng đúng mapper/type | Assert `has("field")`, kiểm tra `@JsonInclude` |
| Field empty string bị bỏ | `NON_EMPTY` đang áp dụng | Đổi contract/inclusion nếu empty có nghĩa |
| Null và missing đều thành null | DTO thuần không track presence | Dùng JsonNode/typed tri-state wrapper cho PATCH |
| Enum xuất `"QUEUED"` thay `"queued"` | Chưa có `@JsonValue`/enum config | Wire code explicit + test |
| JSON enum là số `0` | Ordinal serialization bị bật/config sai | Không dùng ordinal làm wire contract |
| Enum code lạ âm thầm thành null | Có feature unknown-as-null | Xem mapper features, negative test |
| `LocalDate` ra array `[2026,11,8]` | Timestamp feature/module config | Tắt `WRITE_DATES_AS_TIMESTAMPS` hoặc `@JsonFormat` |
| `OffsetDateTime` đổi `+07:00` thành `Z` | Context timezone adjustment khi deserialize | Xem feature, assert offset/instant đúng |
| JavaTime type không serialize được | Mapper thiếu `JavaTimeModule` | Dùng Boot mapper hoặc register module đúng |
| `spring.jackson.date-format` không đổi LocalDate | Không phải format chung mọi `java.time` | Dùng `@JsonFormat`/JavaTime customizer |
| `spring.mvc.format.date` không đổi JSON | MVC conversion khác Jackson JSON | Cấu hình đúng lớp Jackson |
| API HTTP JSON khác test unit | MVC converter dùng mapper/config khác | Test `@WebMvcTest`, kiểm tra ObjectMapper beans |
| HTTP POST 400 thay vì 200 | JSON parser/enum/date invalid | Xem body và root cause `HttpMessageNotReadableException` |
| HTTP 401/403 trong web test | Security filters/CSRF có mặt | Cấu hình Spring Security Test hoặc test profile đúng |
| Date test fail chỉ trên CI | Dùng default locale/timezone/`now()` | Fixed values, offset tường minh, cấu hình đồng bộ |
| Sau nâng Boot 4 imports Jackson lỗi | Jackson 3 packages và modules khác | Nâng dependencies đồng bộ, migration guide |
| Test xanh nhưng client production fail | Only round-trip, expected tự tính | Fixed wire JSON + HTTP contract tests |

### 23.1. Đọc đúng lỗi Jackson

Nếu gặp `InvalidFormatException`, `MismatchedInputException`, `ValueInstantiationException` hoặc `JsonMappingException`, xem:

1. Path của property gây lỗi (ví dụ `created_at`/`state`).
2. JSON token kiểu gì: string, number, object, array, null.
3. Java target type có đúng không.
4. Date/time pattern và offset có đúng không.
5. Jackson features/defaults của mapper đang chạy.
6. Annotation được đặt đúng property/accessor/record component chưa.
7. Dữ liệu lỗi có được xử lý thành HTTP 400/422 theo contract không.

Đừng chỉ sửa expected trong test để khớp actual JSON rồi bỏ qua backward compatibility.

### 23.2. Lỗi 400 từ MVC thường xảy ra trước controller

Khi JSON `@RequestBody` không parse được (enum code sai hoặc date sai), Spring MVC converter có thể ném `HttpMessageNotReadableException` trước khi method controller chạy. Vì vậy `@MockBean BookingQueryService` không có tác động đến lỗi decode trong `POST /echo`.

Nếu input validation phải chạy **sau** deserialization, cần `@Valid` và validator; không nhầm lỗi parse 400 với Bean Validation 400.

## 24. Versioning: Boot 3.3/Jackson 2 và Boot 4/Jackson 3

Dự án runnable này cố ý dùng:

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
```

Đây là **bộ imports Jackson 2** được Spring Boot 3.3 BOM quản lý.

Từ Spring Boot **4.0** và Spring Framework 7, Jackson 3 trở thành lựa chọn mặc định trong Spring Boot starter/auto-configuration; Jackson 2 còn có con đường tương thích trong giai đoạn chuyển tiếp nhưng không nên ghép tùy tiện Jackson 2 và 3 artifacts. Những packages mới bao gồm `tools.jackson.*` ở mapper/core và nhiều cấu hình test/Jackson có thay đổi, trong khi một số annotations vẫn theo library/version cụ thể.

**Đừng nâng lên Boot 4 rồi chỉ copy nguyên Gradle/Java code mẫu và mặc định API không thay đổi.** Hãy:

1. Dùng Boot BOM và test starter theo major version hỗ trợ.
2. Kiểm tra Jackson 2/3 đang thực sự nằm trên runtime classpath.
3. Sửa imports/mapper builder/customizers theo migration guide chính thức.
4. Xác minh naming, null inclusion, enum code và date/time feature behavior bằng regression tests.
5. Kiểm tra `@JsonTest`/JacksonTester tương ứng với mapper được tự cấu hình trong Boot mới.
6. Kiểm tra HTTP message converters trong MVC/WebFlux, vì JSON mapper test thuần chưa chắc đại diện cho mọi endpoint.
7. Chỉ giữ Jackson 2 compatibility layer như một bước quá độ được kiểm soát, không trộn modules không tương thích.

Với Spring Boot **3.4/3.5**, Jackson 2 vẫn là cấu hình chính của dòng 3.x; nhưng các annotations như `@MockBean` trong MVC slice bắt đầu deprecated để hướng đến `@MockitoBean` của Spring Framework mới. Khi migrate, xử lý cả test doubles và JSON mapper version đúng tổ hợp BOM.

## 25. Checklist khi review DTO JSON contract

- [ ] Có ví dụ JSON đúng contract, độc lập với Java class implementation.
- [ ] Biết naming là global `spring.jackson.*` hay `@JsonNaming` trên DTO.
- [ ] Các field có `@JsonProperty` được xác minh output name.
- [ ] `@JsonAlias` chỉ được dùng với ý đồ backward compatibility đầu vào.
- [ ] Không nhầm DTO POJO property names với dynamic `Map` keys.
- [ ] Quy tắc null được quy định rõ: missing, explicit null, empty string/list.
- [ ] `@JsonInclude` không bị dùng thay validation hoặc PATCH presence tracking.
- [ ] Enum xuất wire code tường minh, không phụ thuộc `name()`/`ordinal()`.
- [ ] Unknown enum input có chính sách fail/fallback rõ ràng.
- [ ] `LocalDate` và instant/offset/timezone types được chọn đúng ý nghĩa.
- [ ] Date/time pattern được test ở các mốc năm mới, leap day, offset/DST nếu liên quan.
- [ ] Không dùng `LocalDateTime.now()` trong expected API snapshot.
- [ ] Mapper trong test là Boot-configured mapper hoặc mapper riêng đã configure đúng modules/features.
- [ ] Có test JSON serialization **và** deserialization; round-trip không là bằng chứng duy nhất.
- [ ] Có negative tests cho enum/date sai và field thiếu/null theo hợp đồng.
- [ ] Có một web-layer test để kiểm tra HTTP converter và JSON output của controller khi quan trọng.
- [ ] Nếu lên Boot 4, đã xem Jackson 3 migration và test modules.
- [ ] Không log raw request/response nhạy cảm chỉ để debug JSON failures.

## 26. Bài tập thực hành

### Bài 1 — Đổi strategy và quan sát test

Trong `BookingEvent`, tạm bỏ `@JsonNaming(SnakeCaseStrategy.class)`. Chạy `BookingEventJsonTest`. Bài test nào đỏ? Vì sao? Khôi phục annotation.

**Gợi ý:** keys `booking_id`/`created_at` sẽ không còn đúng trong JSON output. Đừng đổi expected cho khớp nếu hợp đồng public API chưa đổi.

### Bài 2 — Đổi null policy

Thay `@JsonInclude(NON_NULL)` bằng `ALWAYS` và chạy test serialization. Vì sao `optional_note` xuất hiện dưới dạng JSON null? Sau đó thử `NON_EMPTY` với `optionalNote=""` và phân biệt empty với missing.

**Gợi ý:** policy output khác nhau; không có nghĩa deserializer đã phân biệt PATCH field presence.

### Bài 3 — Thêm enum state

Thêm `RETRYING("retrying")` vào `DeliveryState`. Viết hai tests:

- Serialize Java `RETRYING` thành `"retrying"`.
- Deserialize `"retrying"` thành `RETRYING`.

Sau đó mô tả cách phát hành value mới mà không làm client cũ fail; có thể cần API versioning hoặc client fallback.

### Bài 4 — Phân biệt missing và explicit null

Dùng `ObjectNode` tạo hai JSON nodes, một thiếu `optional_note`, một có field null. Chứng minh `has`/`isNull` phân biệt được chúng nhưng `BookingEvent.optionalNote` sau deserialize đều null. Thiết kế DTO riêng cho PATCH có tri-state.

### Bài 5 — `yyyy` vs `YYYY`

Tạo một formatter/thí nghiệm riêng cho 30/12, 31/12 và 01/01 ở những năm mà week-based year đổi khác calendar year. Viết expected theo ngày dương lịch và tìm trường hợp `YYYY` trả year khác. Không sửa production format chỉ vì test ở giữa năm vẫn pass.

### Bài 6 — Offset vs instant

Lấy `2026-11-08T09:30:00+07:00` và `2026-11-08T02:30:00Z`. So sánh `toInstant()` và `getOffset()`. Khi business contract yêu cầu giữ offset người dùng, cần assert gì? Khi chỉ yêu cầu audit timestamp tuyệt đối, cần assert gì?

### Bài 7 — Tạo mapper sai có chủ đích

Trong một unit test sandbox, tạo `new ObjectMapper()` rồi serialize `OffsetDateTime` mà không đăng ký `JavaTimeModule`. So sánh exception/output với `@JsonTest` mapper của Boot. Giải thích vì sao unit mapper không đại diện cho MVC mapper.

### Bài 8 — Global strategy tác động nhiều DTO

Bật global `spring.jackson.property-naming-strategy=SNAKE_CASE` trong test configuration và serialize hai DTO không gắn `@JsonNaming`. Kết quả thay đổi thế nào? Nếu ứng dụng có một endpoint legacy camelCase, đâu là chiến lược versioning an toàn?

### Bài 9 — Invalid request qua MVC

Dùng `BookingControllerWebTest`, gửi `"state":"delayed"` và `"travel_date":"not-a-date"`. Viết assertion status 400 cho cả hai. Nếu muốn response error JSON code chuẩn hóa, thêm `@RestControllerAdvice` và test JSON code có ý nghĩa thay vì default exception message.

### Bài 10 — Golden JSON contract

Tạo `expected-booking.json` trong test resources với đúng field names/enum/date và không có `optional_note`. So sánh bằng `JacksonTester`/JSONAssert. Phân biệt các thay đổi được chấp nhận (whitespace/key ordering) và breaking changes (rename field, enum code, date pattern).

## 27. Tổng kết: chiến lược test ít mà hiệu quả

`Naming strategy`, `null inclusion`, `enum wire value` và `date/time format` đều là **quyết định giao thức**. Chúng có thể không ảnh hưởng business logic Java nhưng làm client JSON hỏng ngay khi release.

Một chiến lược phù hợp:

1. **`@JsonTest`** làm lớp bảo vệ nhanh cho mỗi public DTO quan trọng: fixed expected JSON + chiều đọc + negative inputs.
2. **`@WebMvcTest`** bảo vệ một số HTTP routes quan trọng để xác minh converter, content type và error mapping dùng cùng schema.
3. **Service/domain tests** kiểm tra nghiệp vụ mà không cần khởi động web context.
4. **Full integration tests** bổ sung khi cần chứng minh DB, cross-bean effects hoặc live HTTP transport.
5. **Schema regression tests trước nâng major** để nhận biết các thay đổi từ Jackson 2 sang Jackson 3 thay vì để client production phát hiện đầu tiên.

Điểm quan trọng nhất: **test JSON như dữ liệu mà hệ thống khác thật sự nhìn thấy**, không chỉ như một object Java chạy trong JVM.

## 28. Tài liệu chính thức

- Spring Boot 3.3 — Testing Spring Boot Applications, JSON tests: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Common Application Properties, `spring.jackson.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — JSON features and Jackson customization: https://docs.spring.io/spring-boot/3.3/reference/features/json.html
- Spring Boot 3.3 — `@JsonTest` API: https://docs.spring.io/spring-boot/3.3.6/api/java/org/springframework/boot/test/autoconfigure/json/JsonTest.html
- Jackson 2 — JsonInclude: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonInclude.html
- Jackson 2 — JsonFormat: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonFormat.html
- Jackson 2 — JsonCreator and JsonValue: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonCreator.html
- Jackson 2 — PropertyNamingStrategies: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/PropertyNamingStrategies.html
- Jackson 2 — JavaTimeModule: https://javadoc.io/doc/com.fasterxml.jackson.datatype/jackson-datatype-jsr310/latest/com/fasterxml/jackson/datatype/jsr310/JavaTimeModule.html
- Java SE 17 — DateTimeFormatter patterns: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Spring Framework — Spring MVC testing MockMvc: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring — Introducing Jackson 3 support, migration context: https://spring.io/blog/2025/10/07/introducing-jackson-3-support-in-spring/
- JUnit User Guide: https://docs.junit.org/current/user-guide/
