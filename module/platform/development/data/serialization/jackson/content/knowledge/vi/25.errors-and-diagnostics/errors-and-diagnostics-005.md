# Xử lý trường không nhận diện và giá trị enum không hợp lệ

Khi deserialize JSON, Jackson có thể gặp hai loại dữ liệu không khớp với model Java: một field không tồn tại trong DTO, hoặc một field có tên hợp lệ nhưng giá trị không thuộc tập enum được khai báo. Hai tình huống này trông giống nhau ở mức “JSON không khớp model”, nhưng chúng là hai vấn đề khác nhau và cần chính sách xử lý riêng.

Ví dụ DTO:

```java
public class OrderRequest {
    private String orderId;
    private OrderStatus status;
}

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

JSON sau có một trường không nhận diện:

```json
{
  "orderId": "ORD-100",
  "status": "PAID",
  "campaignCode": "SUMMER"
}
```

`campaignCode` không phải property của `OrderRequest`. Đây là **unknown property**.

JSON sau có tên field hợp lệ nhưng enum value không hợp lệ:

```json
{
  "orderId": "ORD-100",
  "status": "REFUNDED"
}
```

`status` là property đã biết, nhưng `REFUNDED` không phải hằng enum trong `OrderStatus`. Đây là **unknown enum value**.

Jackson có các cơ chế riêng để từ chối, bỏ qua, thu thập hoặc thay thế những dữ liệu này. Chọn chính sách phù hợp giúp API tương thích khi schema mở rộng mà vẫn phát hiện được dữ liệu sai.

## 1. Phân biệt unknown property và unknown enum value

| Tình huống | Ví dụ | Cơ chế Jackson liên quan |
|---|---|---|
| Tên field không có trong DTO | `"campaignCode": "SUMMER"` | `FAIL_ON_UNKNOWN_PROPERTIES`, `@JsonIgnoreProperties`, `@JsonAnySetter`, `DeserializationProblemHandler` |
| Field có tên hợp lệ, enum literal không tồn tại | `"status": "REFUNDED"` | `READ_UNKNOWN_ENUM_VALUES_AS_NULL`, `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE`, `@JsonEnumDefaultValue`, custom enum mapping |
| Field có tên hợp lệ nhưng sai kiểu JSON | `"status": {}` | Coercion/deserializer và xử lý token không mong đợi |
| Field bị thiếu | Không có key `status` | Giá trị khởi tạo, creator/default và null/missing handling |
| Field có giá trị JSON null | `"status": null` | Null handling, `@JsonSetter`, `Nulls` |

Không nên dùng một cấu hình để giải quyết tất cả các trường hợp. Ví dụ, bỏ qua unknown property không làm cho enum value không hợp lệ trở nên hợp lệ. Tương tự, cho phép enum fallback không ảnh hưởng đến một key hoàn toàn không được DTO nhận diện.

## 2. Vì sao JSON có thể chứa trường không nhận diện?

Unknown property thường xuất hiện khi hai phía của API triển khai ở các thời điểm khác nhau:

- Producer đã thêm field mới nhưng consumer chưa nâng cấp.
- Một hệ thống gửi thêm metadata mà DTO hiện tại không cần.
- Tên field bị sai chính tả hoặc khác naming convention.
- Client gửi nhầm payload của endpoint khác.
- JSON có dữ liệu mở rộng do plugin hoặc phiên bản schema mới cung cấp.

Ví dụ consumer chỉ biết:

```java
public class CustomerRequest {
    private String name;
    private String email;
}
```

Producer gửi:

```json
{
  "name": "An",
  "email": "an@example.com",
  "preferredLanguage": "vi"
}
```

Nếu consumer chưa cần `preferredLanguage`, có thể bỏ qua hoặc lưu lại field đó tùy yêu cầu. Nhưng nếu field lạ thực ra là `emali` thay vì `email`, bỏ qua âm thầm có thể khiến dữ liệu bắt buộc bị mất. Chính sách phải phản ánh mức độ nghiêm ngặt của hợp đồng.

## 3. Hành vi mặc định: FAIL_ON_UNKNOWN_PROPERTIES

Trong Jackson Databind, `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` được bật mặc định trong cấu hình thông thường. Khi Jackson gặp property không thể ánh xạ vào DTO và không có cơ chế xử lý khác, nó ném lỗi thay vì âm thầm bỏ qua.

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "name": "An",
      "preferredLanguage": "vi"
    }
    """;

CustomerRequest request = mapper.readValue(json, CustomerRequest.class);
```

Nếu `CustomerRequest` không có property `preferredLanguage`, thao tác deserialize có thể ném `UnrecognizedPropertyException` (một dạng `JsonMappingException`).

### 3.1. Vì sao mặc định fail hữu ích?

Fail sớm giúp phát hiện:

- Field bị gõ sai.
- Producer gửi nhầm schema.
- Consumer chưa được nâng cấp theo hợp đồng mới.
- Payload có dữ liệu ngoài dự kiến.

Với request quan trọng như thanh toán, quyền truy cập hoặc thay đổi trạng thái, từ chối field lạ có thể giúp tránh việc client nghĩ rằng server đã xử lý một giá trị mà server thực tế bỏ qua.

### 3.2. Tắt fail ở cấp ObjectMapper

Nếu ứng dụng chủ động muốn bỏ qua unknown property trên mọi DTO, có thể tắt feature:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Khi đó, các property không được nhận diện thường bị bỏ qua trong quá trình deserialize.

Đây là cấu hình rộng: nó ảnh hưởng mọi kiểu được mapper xử lý, trừ nơi có cơ chế riêng. Chỉ dùng khi chính sách tương thích này thực sự phù hợp với toàn bộ mapper. Nếu một số request cần nghiêm ngặt và một số request cần linh hoạt, hãy dùng DTO/reader/mapper riêng hoặc cấu hình ở cấp lớp/property.

## 4. Bỏ qua unknown property bằng @JsonIgnoreProperties

Nếu chỉ một DTO cần chấp nhận field lạ, đặt annotation trên class:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class ExternalCustomerPayload {
    private String name;
    private String email;

    // Getter và setter
}
```

Với annotation này, Jackson bỏ qua các property không được nhận diện khi deserialize `ExternalCustomerPayload`.

Ví dụ JSON:

```json
{
  "name": "An",
  "email": "an@example.com",
  "newFieldFromPartner": "value"
}
```

`name` và `email` được ánh xạ; `newFieldFromPartner` bị bỏ qua.

### 4.1. Phạm vi của annotation

`@JsonIgnoreProperties(ignoreUnknown = true)` trên một class áp dụng cho các property của kiểu đó. Nó không tự động làm mọi class lồng bên trong đều bỏ qua field lạ.

Ví dụ:

```java
public class PartnerResponse {
    private String id;
    private PartnerProfile profile;
}

@JsonIgnoreProperties(ignoreUnknown = true)
public class PartnerProfile {
    private String displayName;
}
```

Trong ví dụ, `PartnerProfile` bỏ qua field lạ của chính nó. Nếu JSON có field lạ ở cấp `PartnerResponse`, cần chính sách tương ứng ở class cha hoặc mapper.

### 4.2. Phân biệt ignoreUnknown với danh sách property bị ignore

`@JsonIgnoreProperties` còn có thể chỉ định các tên property cần bỏ qua:

```java
@JsonIgnoreProperties({"legacyToken", "internalNote"})
public class PartnerResponse {
    private String id;
}
```

Đây là danh sách tên đã biết nhưng ứng dụng chủ động không ánh xạ. Nó khác với `ignoreUnknown = true`, vốn cho phép bỏ qua mọi tên không nhận diện.

Nếu bật `DeserializationFeature.FAIL_ON_IGNORED_PROPERTIES`, việc JSON chứa một property đã bị đánh dấu ignore có thể gây lỗi. Feature này khác `FAIL_ON_UNKNOWN_PROPERTIES`: một property bị ignore là tên mà cấu hình đã biết nhưng chủ động loại bỏ.

## 5. Thu thập field động bằng @JsonAnySetter

Đôi khi ứng dụng không muốn bỏ qua field lạ mà muốn giữ lại chúng. `@JsonAnySetter` cho phép một method hoặc field nhận các property còn lại sau khi Jackson xử lý các property đã khai báo.

Ví dụ lưu dữ liệu mở dưới dạng `Map<String, JsonNode>`:

```java
public class PartnerResponse {
    private String id;
    private String name;
    private final Map<String, JsonNode> extra = new LinkedHashMap<>();

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    @JsonAnySetter
    public void addExtra(String propertyName, JsonNode value) {
        extra.put(propertyName, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> getExtra() {
        return extra;
    }
}
```

Với JSON:

```json
{
  "id": "C-25",
  "name": "An",
  "preferredLanguage": "vi",
  "partnerFlags": {
    "priority": true
  }
}
```

Jackson gán `id` và `name` vào property đã khai báo. Các field còn lại được chuyển đến `addExtra()`:

- `preferredLanguage` trở thành `TextNode`.
- `partnerFlags` trở thành `ObjectNode`.

Dùng `JsonNode` giúp giữ nguyên kiểu và cấu trúc JSON của dữ liệu mở. Nếu dùng `Object`, các object lồng nhau thường được biểu diễn bằng Map/List và scalar Java; điều đó cũng hợp lệ nhưng tree model cung cấp API rõ ràng hơn để thao tác JSON.

### 5.1. Khi nào dùng JsonAnySetter thay vì ignoreUnknown?

| Nhu cầu | Cơ chế |
|---|---|
| Field lạ không có ý nghĩa với consumer | `@JsonIgnoreProperties(ignoreUnknown = true)` |
| Cần giữ lại metadata do đối tác gửi | `@JsonAnySetter` và Map/JsonNode |
| Cần log hoặc xử lý tập trung field lạ | `DeserializationProblemHandler` |
| Cần từ chối field lạ để bảo vệ schema | Giữ `FAIL_ON_UNKNOWN_PROPERTIES` bật |

Nếu dùng `@JsonAnySetter`, property lạ đã được xử lý nên không còn đi đến bước fail unknown property thông thường. Hãy xác định rõ field động nào được phép và giới hạn kích thước/kiểu dữ liệu nếu nguồn không đáng tin cậy.

### 5.2. Ghi lại dữ liệu mở khi serialize

Kết hợp `@JsonAnyGetter` cho phép xuất các entry trong Map như property cùng cấp với field cố định. Ví dụ trên sẽ có thể serialize thành:

```json
{
  "id": "C-25",
  "name": "An",
  "preferredLanguage": "vi",
  "partnerFlags": {
    "priority": true
  }
}
```

`@JsonAnyGetter` có thể tạo xung đột nếu Map chứa key trùng với property cố định như `id` hoặc `name`. Nên kiểm tra key trước khi lưu và xác định quy tắc ưu tiên rõ ràng.

## 6. Xử lý unknown property tập trung bằng DeserializationProblemHandler

Nếu muốn ghi log, đếm hoặc áp dụng một chính sách chung cho nhiều DTO mà không sửa từng class, có thể đăng ký `DeserializationProblemHandler` trên mapper.

```java
ObjectMapper mapper = new ObjectMapper();

mapper.addHandler(new DeserializationProblemHandler() {
    @Override
    public boolean handleUnknownProperty(
            DeserializationContext context,
            JsonParser parser,
            JsonDeserializer<?> deserializer,
            Object beanOrClass,
            String propertyName) throws IOException {

        // Ghi nhận tên property và kiểu bean nếu cần.
        parser.skipChildren();
        return true;
    }
});
```

Handler được gọi khi Jackson gặp property chưa xử lý. Trả về `true` có nghĩa handler đã xử lý property đó; trả về `false` để Jackson tiếp tục cơ chế xử lý mặc định, thường là báo lỗi nếu `FAIL_ON_UNKNOWN_PROPERTIES` vẫn bật.

`parser.skipChildren()` quan trọng khi giá trị field lạ là object hoặc array. Nó đưa parser qua toàn bộ cấu trúc con để Jackson có thể tiếp tục đọc field tiếp theo. Với scalar, lệnh này không cần bỏ qua node lồng nhau.

### 6.1. Handler không nên âm thầm che mọi lỗi

Một handler có thể log field lạ rồi bỏ qua, nhưng nên ghi nhận đủ ngữ cảnh để điều tra schema drift. Tránh log toàn bộ giá trị nhạy cảm từ JSON; tên field, kiểu DTO và nguồn request thường đã đủ cho telemetry.

Nếu chỉ một DTO cho phép field lạ, annotation cấp class dễ đọc và ít ảnh hưởng hơn handler toàn mapper. Dùng handler khi cần chính sách tập trung hoặc instrumentation.

### 6.2. Thứ tự xử lý

Jackson chỉ xem property là unknown sau khi các cơ chế property đã khai báo, alias, ignore và any-setter được xem xét. `DeserializationProblemHandler` là điểm mở rộng cho trường hợp còn lại. Vì vậy, nó không thay thế `@JsonAnySetter` khi ứng dụng cần lưu field động vào object.

## 7. Giá trị enum không hợp lệ: hành vi mặc định

Giả sử enum:

```java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

JSON:

```json
{
  "status": "REFUNDED"
}
```

Nếu dùng cấu hình mặc định và không có custom creator/deserializer, Jackson không tìm thấy hằng enum tương ứng và thường ném `InvalidFormatException` (một dạng `JsonMappingException`).

Đây là hành vi nghiêm ngặt hữu ích khi enum biểu diễn trạng thái nghiệp vụ mà consumer phải hiểu chính xác. Ví dụ, nếu một phiên bản producer gửi `REFUNDED` nhưng consumer chưa biết trạng thái này, tiếp tục xử lý như `PAID` hoặc `CANCELLED` có thể gây sai logic.

## 8. Chuyển enum không nhận diện thành null

Nếu hệ thống chấp nhận rằng giá trị enum mới có thể xuất hiện và muốn biểu diễn nó thành null, bật:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL);
```

Khi gặp:

```json
{
  "status": "REFUNDED"
}
```

Jackson gán `null` cho property enum trong trường hợp phù hợp.

### 8.1. Khi nào AS_NULL phù hợp?

Chính sách này có thể phù hợp khi:

- Enum chỉ mang tính mô tả phụ, không điều khiển nghiệp vụ quan trọng.
- Consumer có thể tiếp tục mà không cần phân biệt giá trị mới.
- Null đã có ý nghĩa rõ ràng trong model.

Không nên dùng nếu null có nghĩa là “chưa được cung cấp” trong khi giá trị lạ thực ra là một trạng thái có thật. Việc chuyển cả hai trường hợp thành null sẽ làm mất thông tin về schema mới.

### 8.2. Hành vi với EnumSet và EnumMap

`EnumSet` và key của `EnumMap` không thể chứa null. Khi unknown enum value được chuyển thành null, phần tử/key tương ứng có thể bị bỏ qua thay vì lưu null. Nếu dữ liệu có thể đi vào collection enum, hãy test hành vi cụ thể thay vì giả định một null entry sẽ được giữ.

### 8.3. Null, thiếu field và enum lạ là ba trạng thái khác nhau

| JSON | Kết quả/ý nghĩa |
|---|---|
| Không có `status` | Field bị thiếu; giá trị khởi tạo hoặc creator quyết định |
| `"status": null` | Giá trị null tường minh; null handling quyết định |
| `"status": "REFUNDED"` với AS_NULL | Enum literal lạ được chuyển thành null |
| `"status": "PAID"` | Enum hợp lệ `OrderStatus.PAID` |

Nếu ứng dụng cần phân biệt giá trị lạ với null thực sự, hãy dùng default enum hoặc giữ raw value trong DTO trung gian thay vì AS_NULL.

## 9. Dùng hằng mặc định với @JsonEnumDefaultValue

Một lựa chọn thường rõ nghĩa hơn null là khai báo hằng enum đại diện cho giá trị chưa biết:

```java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
```

Bật feature:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
```

Khi JSON có:

```json
{
  "status": "REFUNDED"
}
```

Jackson ánh xạ `REFUNDED` thành `OrderStatus.UNKNOWN`.

### 9.1. Chọn đúng một default enum

Đánh dấu một hằng enum duy nhất bằng `@JsonEnumDefaultValue`. Nếu không có hằng được đánh dấu mà feature được bật, Jackson không có giá trị mặc định để dùng và unknown value vẫn có thể gây lỗi. Nếu có nhiều hằng được đánh dấu, lựa chọn không nên được dựa vào; hãy chỉ định một hằng rõ ràng.

### 9.2. Ưu tiên default enum so với AS_NULL

Nếu đồng thời bật `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` và `READ_UNKNOWN_ENUM_VALUES_AS_NULL`, chính sách dùng default enum có ưu tiên cao hơn. Hãy tránh bật cả hai nếu không cần thiết để cấu hình dễ hiểu; chọn một semantics phù hợp với domain.

### 9.3. Default enum không xử lý field bị thiếu

`@JsonEnumDefaultValue` áp dụng khi JSON có một enum value không nhận diện. Nó không tự gán `UNKNOWN` khi key `status` hoàn toàn bị thiếu. Nếu muốn field thiếu cũng nhận `UNKNOWN`, cần đặt giá trị khởi tạo trong DTO hoặc xử lý bằng creator/default logic.

## 10. Chấp nhận enum không phân biệt chữ hoa/thường

Producer đôi khi gửi `paid`, `Paid` hoặc `PAID`. Nếu hợp đồng cho phép khác biệt chữ hoa/thường, có thể bật:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS);
```

Khi đó, enum value có thể được nhận diện mà không phân biệt case theo cơ chế enum deserializer của Jackson.

Điều này không có nghĩa mọi chuỗi gần giống nhau đều hợp lệ. Ví dụ `"pa id"`, `"payd"` hoặc `"REFUNDED"` vẫn là các giá trị khác và cần chính sách riêng.

### 10.1. Chỉ bật khi hợp đồng cho phép

Nếu enum dùng mã wire phân biệt chữ hoa/thường hoặc các mã legacy có ý nghĩa khác nhau, bật case-insensitive có thể làm mất sự phân biệt. Hãy xem đây là chính sách của mapper, không phải bước normalize vô hại.

Nếu chỉ một enum hoặc một property cần chấp nhận nhiều cách viết, custom creator/deserializer hoặc DTO đầu vào riêng có thể giới hạn ảnh hưởng tốt hơn.

## 11. Ngăn số JSON được hiểu là ordinal enum

Theo mặc định, Jackson có thể đọc một JSON number thành ordinal của enum trong một số cấu hình, ví dụ `0` tương ứng hằng đầu tiên, `1` tương ứng hằng thứ hai. Điều này rất dễ gây lỗi khi thứ tự khai báo enum thay đổi.

Có thể từ chối số cho enum bằng:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS);
```

Ví dụ, JSON:

```json
{
  "status": 1
}
```

sẽ bị từ chối thay vì được diễn giải thành enum theo vị trí.

Đối với API và dữ liệu lưu lâu dài, nên dùng string token ổn định như `"PAID"` hoặc `"paid"`. Ordinal phụ thuộc thứ tự hằng enum và có thể làm dữ liệu cũ đổi ý nghĩa khi source code được sắp xếp lại.

## 12. Kiểm soát tên enum trong JSON

Tên hằng Java không nhất thiết phải là tên wire format. Có thể dùng `@JsonProperty` trên enum constant để đặt giá trị JSON ổn định:

```java
public enum OrderStatus {
    @JsonProperty("new")
    NEW,

    @JsonProperty("paid")
    PAID,

    @JsonProperty("cancelled")
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
```

Nhờ vậy, JSON dùng token chữ thường trong khi code Java vẫn dùng tên constant theo convention. `@JsonProperty` giúp định nghĩa tên external; hãy giữ các tên này ổn định nếu JSON được lưu lâu dài hoặc trao đổi giữa nhiều phiên bản service.

Nếu bật `READ_ENUMS_USING_TO_STRING`, Jackson dùng `toString()` để đọc enum thay vì tên enum thông thường. Chỉ bật khi ứng dụng chủ động định nghĩa `toString()` như một phần của wire contract. `toString()` thường được dùng cho debug/log; thay đổi nó có thể vô tình làm thay đổi cách đọc JSON.

Tương tự, `WRITE_ENUMS_USING_TO_STRING` ảnh hưởng cách serialize enum. Nếu cần wire name ổn định, ưu tiên annotation hoặc một cơ chế mapping tường minh thay vì phụ thuộc chuỗi debug.

## 13. Dùng @JsonCreator để hỗ trợ alias và chuẩn hóa enum

Khi enum cần nhận nhiều tên cũ, trim khoảng trắng hoặc áp dụng mapping nghiệp vụ riêng, có thể dùng static factory với `@JsonCreator`:

```java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED,
    UNKNOWN;

    @JsonCreator
    public static OrderStatus fromJson(String raw) {
        if (raw == null) {
            return null;
        }

        return switch (raw.trim().toLowerCase(Locale.ROOT)) {
            case "new", "created" -> NEW;
            case "paid", "settled" -> PAID;
            case "cancelled", "canceled" -> CANCELLED;
            default -> UNKNOWN;
        };
    }
}
```

Với JSON `"settled"`, kết quả là `PAID`; `"canceled"` được chuẩn hóa thành `CANCELLED`; mọi giá trị còn lại thành `UNKNOWN`.

### 13.1. Creator có thể chủ động fail

Nếu muốn chỉ chấp nhận alias đã biết và từ chối giá trị còn lại:

```java
@JsonCreator
public static OrderStatus fromJson(String raw) {
    if (raw == null) {
        return null;
    }

    return switch (raw.trim().toLowerCase(Locale.ROOT)) {
        case "new", "created" -> NEW;
        case "paid", "settled" -> PAID;
        case "cancelled", "canceled" -> CANCELLED;
        default -> throw new IllegalArgumentException("Unknown order status: " + raw);
    };
}
```

Jackson sẽ bọc lỗi từ creator trong lỗi mapping phù hợp. Thông điệp nên cung cấp ngữ cảnh nhưng tránh đưa dữ liệu nhạy cảm vào log.

### 13.2. Creator là chính sách riêng

Khi dùng `@JsonCreator`, factory method chịu trách nhiệm quyết định alias, case, whitespace và fallback. Không nên giả định mọi feature enum chuẩn như `READ_UNKNOWN_ENUM_VALUES_AS_NULL` hoặc `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` sẽ thay thế logic trong creator theo cùng cách như enum deserializer mặc định.

Hãy viết test cho creator như một API parse độc lập, bao gồm null, alias, khoảng trắng, case và giá trị không biết.

## 14. Dùng custom deserializer khi quy tắc enum phức tạp

Nếu enum cần nhận cả string và object, hoặc mapping phụ thuộc dữ liệu khác, custom deserializer có thể phù hợp hơn:

```java
public class OrderStatusDeserializer extends StdDeserializer<OrderStatus> {
    public OrderStatusDeserializer() {
        super(OrderStatus.class);
    }

    @Override
    public OrderStatus deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            return (OrderStatus) context.handleUnexpectedToken(
                OrderStatus.class,
                parser
            );
        }

        String raw = parser.getText().trim();
        return switch (raw.toLowerCase(Locale.ROOT)) {
            case "new", "created" -> OrderStatus.NEW;
            case "paid", "settled" -> OrderStatus.PAID;
            case "cancelled", "canceled" -> OrderStatus.CANCELLED;
            default -> OrderStatus.UNKNOWN;
        };
    }
}
```

Gắn cho enum hoặc một property:

```java
public class OrderRequest {
    @JsonDeserialize(using = OrderStatusDeserializer.class)
    private OrderStatus status;
}
```

Nếu mọi property của enum cần cùng quy tắc, có thể đặt annotation trên enum. Nếu chỉ một field nhận dữ liệu legacy, đặt annotation ở property để không làm thay đổi các nơi khác.

Custom deserializer phải xử lý null theo cơ chế null handling phù hợp. Với token `VALUE_NULL`, Jackson có thể gọi `getNullValue()` thay vì `deserialize()`; override `getNullValue()` nếu semantics riêng yêu cầu.

## 15. Kết hợp unknown property và enum fallback trong một DTO

Một API đối tác có thể thêm field mới và mở rộng tập enum độc lập. Có thể chọn chính sách cho từng loại:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class PartnerOrder {
    private String orderId;
    private PartnerStatus status;

    // Getter và setter
}

public enum PartnerStatus {
    NEW,
    PAID,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
```

Mapper:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
```

Với JSON:

```json
{
  "orderId": "ORD-100",
  "status": "REFUNDED",
  "newPartnerMetadata": {
    "source": "mobile"
  }
}
```

Kết quả:

- `orderId` được ánh xạ bình thường.
- `status` trở thành `PartnerStatus.UNKNOWN`.
- `newPartnerMetadata` bị bỏ qua bởi `ignoreUnknown = true`.

Nếu ứng dụng cần giữ metadata mới, thay `ignoreUnknown = true` bằng `@JsonAnySetter` để thu thập field động. Hai chính sách có thể phối hợp với enum fallback nhưng phải được thiết kế độc lập.

## 16. Tạo reader riêng cho endpoint có chính sách khác nhau

Không phải mọi endpoint đều nên dùng cùng một mức độ khoan dung. Có thể tạo `ObjectReader` với feature riêng cho một luồng:

```java
ObjectReader partnerReader = mapper.readerFor(PartnerOrder.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .with(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
```

Reader này có cấu hình đọc riêng và có thể tái sử dụng cho dữ liệu đối tác. Mapper gốc vẫn giữ cấu hình nghiêm ngặt cho các request nội bộ.

Với enum fallback, feature `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` cần enum có một hằng `@JsonEnumDefaultValue`. Nếu không có, reader không tự tạo một hằng mới.

Nếu muốn property-level enum policy khác nhau trong cùng một DTO, dùng custom deserializer hoặc tách DTO theo hợp đồng thay vì bật feature toàn mapper.

## 17. Chẩn đoán lỗi và đọc thông tin exception

Khi Jackson từ chối JSON, exception thường chứa loại lỗi, kiểu đích và đường dẫn property.

Ví dụ bắt lỗi:

```java
try {
    OrderRequest request = mapper.readValue(json, OrderRequest.class);
} catch (UnrecognizedPropertyException e) {
    System.err.println("Unknown property: " + e.getPropertyName());
    System.err.println("Target type: " + e.getReferringClass().getName());
} catch (InvalidFormatException e) {
    System.err.println("Invalid value: " + e.getValue());
    System.err.println("Target type: " + e.getTargetType().getName());
} catch (JsonProcessingException e) {
    System.err.println("JSON mapping failed: " + e.getOriginalMessage());
}
```

`UnrecognizedPropertyException` thường biểu thị tên field không được nhận diện. `InvalidFormatException` thường xuất hiện khi giá trị không thể chuyển thành kiểu đích, chẳng hạn enum literal không hợp lệ hoặc chuỗi không parse được thành số.

Không nên chỉ dựa vào message text để phân loại lỗi vì message có thể thay đổi theo phiên bản hoặc locale. Nếu cần phân loại trong ứng dụng, hãy bắt exception subtype phù hợp hoặc kiểm tra cause/path một cách có chủ đích.

### 17.1. Path giúp xác định vị trí lỗi

Một enum không hợp lệ có thể nằm sâu trong object:

```json
{
  "order": {
    "payment": {
      "status": "REFUNDED"
    }
  }
}
```

Thông tin path của `JsonMappingException` giúp xác định chuỗi property dẫn đến lỗi. Khi ghi log, có thể dùng `getPathReference()` hoặc các path segment để bổ sung ngữ cảnh. Tránh log toàn bộ request body nếu có thông tin nhạy cảm.

## 18. Ví dụ JUnit kiểm tra các chính sách

Các test sau minh họa những chính sách độc lập.

### 18.1. Unknown property bị từ chối theo mặc định

```java
@Test
void rejectsUnknownPropertyByDefault() {
    ObjectMapper mapper = new ObjectMapper();
    String json = "{\"name\":\"An\",\"extra\":1}";

    assertThrows(UnrecognizedPropertyException.class,
        () -> mapper.readValue(json, CustomerRequest.class));
}
```

### 18.2. Bỏ qua unknown property ở DTO được đánh dấu

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public static class LenientCustomerRequest {
    public String name;
}

@Test
void ignoresUnknownPropertyOnAnnotatedType() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    LenientCustomerRequest value = mapper.readValue(
        "{\"name\":\"An\",\"extra\":1}",
        LenientCustomerRequest.class
    );

    assertEquals("An", value.name);
}
```

### 18.3. Unknown enum value bị từ chối mặc định

```java
@Test
void rejectsUnknownEnumValueByDefault() {
    ObjectMapper mapper = new ObjectMapper();

    assertThrows(InvalidFormatException.class,
        () -> mapper.readValue("{\"status\":\"REFUNDED\"}", OrderRequest.class));
}
```

### 18.4. Unknown enum value thành default constant

```java
@Test
void mapsUnknownEnumToDefaultConstant() throws Exception {
    ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);

    OrderRequest value = mapper.readValue(
        "{\"status\":\"REFUNDED\"}",
        OrderRequest.class
    );

    assertEquals(OrderStatus.UNKNOWN, value.getStatus());
}
```

### 18.5. Unknown enum value thành null

```java
@Test
void mapsUnknownEnumToNullWhenConfigured() throws Exception {
    ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL);

    OrderRequest value = mapper.readValue(
        "{\"status\":\"REFUNDED\"}",
        OrderRequest.class
    );

    assertNull(value.getStatus());
}
```

### 18.6. Số ordinal bị từ chối

```java
@Test
void rejectsNumericEnumValues() {
    ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS);

    assertThrows(JsonProcessingException.class,
        () -> mapper.readValue("{\"status\":1}", OrderRequest.class));
}
```

Các test cần dùng đúng DTO/enum và getter tương ứng trong project. Mục tiêu là xác nhận từng feature với mapper production, không chỉ kiểm tra một JSON tổng hợp.

## 19. Chọn chính sách theo loại ứng dụng

| Ngữ cảnh | Unknown property | Unknown enum value |
|---|---|---|
| API nội bộ có schema kiểm soát | Thường giữ fail để phát hiện lệch contract | Thường giữ fail nếu enum điều khiển nghiệp vụ |
| Consumer đọc dữ liệu từ đối tác có thể thêm field | Bỏ qua hoặc thu thập field mở theo hợp đồng | Dùng default/unknown sentinel nếu có thể tiếp tục an toàn |
| Lưu trữ event dài hạn | Thường giữ raw extension hoặc version schema rõ ràng | Ưu tiên giữ raw value hoặc default có khả năng quan sát; tránh mất thông tin |
| Log/telemetry | Có thể bỏ field mới nếu không cần | Có thể dùng UNKNOWN để dashboard vẫn đọc được |
| Thanh toán, quyền hạn, workflow | Từ chối field sai để phát hiện payload lỗi | Thường từ chối trạng thái không hiểu để tránh quyết định sai |

Không có một chính sách duy nhất đúng cho mọi hệ thống. Hãy cân nhắc hậu quả của việc bỏ dữ liệu, thay thế dữ liệu hoặc từ chối toàn bộ request.

## 20. Những lỗi thường gặp

**Tắt `FAIL_ON_UNKNOWN_PROPERTIES` để sửa enum không hợp lệ.** Hai lỗi khác nhau. Feature này chỉ xử lý property name không được nhận diện; enum literal sai cần enum-specific policy hoặc custom mapping.

**Dùng `@JsonIgnoreProperties(ignoreUnknown = true)` rồi mong giữ field lạ.** Annotation này bỏ field; dùng `@JsonAnySetter` nếu cần thu thập.

**Đặt `ignoreUnknown` ở class cha và nghĩ nested DTO cũng được bảo vệ.** Annotation chỉ áp dụng cho kiểu được đánh dấu; kiểm tra từng nested type hoặc dùng cấu hình reader/mapper có phạm vi phù hợp.

**Dùng AS_NULL rồi không phân biệt enum lạ với null thật.** Cả hai có thể trở thành null. Nếu cần biết producer gửi giá trị mới, dùng default sentinel hoặc giữ raw value.

**Bật default enum nhưng quên `@JsonEnumDefaultValue`.** Jackson không có constant để chọn. Đánh dấu một hằng duy nhất.

**Cho rằng default enum xử lý field bị thiếu.** Default enum chỉ xử lý literal không nhận diện. Field không có trong JSON cần default/creator logic riêng.

**Dùng ordinal enum trong JSON.** Thứ tự hằng có thể thay đổi. Dùng string wire value và cân nhắc `FAIL_ON_NUMBERS_FOR_ENUMS`.

**Bật case-insensitive mà không xem xét contract.** Việc này thay đổi cách nhận diện enum trên phạm vi mapper và có thể làm mất phân biệt case.

**Dùng `toString()` làm wire value nhưng sau đó thay đổi cách debug.** Chỉ bật `READ_ENUMS_USING_TO_STRING`/`WRITE_ENUMS_USING_TO_STRING` khi `toString()` được coi là contract ổn định.

**Custom creator trả UNKNOWN cho mọi giá trị nhưng không ghi nhận raw input.** Điều này có thể che giấu producer mới hoặc lỗi chính tả. Nếu cần quan sát, lưu raw value ở DTO trung gian hoặc ghi telemetry an toàn.

## 21. Quy trình thiết kế và kiểm thử

1. Phân loại lỗi: tên property lạ, enum literal lạ, sai JSON shape, null hay field thiếu.
2. Với unknown property, quyết định fail, ignore, capture bằng `@JsonAnySetter` hay xử lý qua handler.
3. Chọn phạm vi cấu hình: một DTO, một reader hoặc mapper dùng chung.
4. Với enum, quyết định fail, null, default sentinel, case-insensitive hay custom alias mapping.
5. Nếu dùng default sentinel, đánh dấu một constant bằng `@JsonEnumDefaultValue` và bật feature tương ứng.
6. Nếu dùng string enum, đặt wire name ổn định; cân nhắc từ chối numeric ordinal.
7. Giữ riêng semantics của null và field bị thiếu.
8. Kiểm tra nested DTO và collection enum, bao gồm hành vi EnumSet/EnumMap.
9. Viết test cho field lạ ở cấp cha/con, enum hợp lệ/lạ, null, missing, case, số và token sai loại.
10. Theo dõi lỗi schema drift mà không log dữ liệu nhạy cảm.

## Kết luận

Unknown property và enum value không hợp lệ là hai dạng lệch dữ liệu khác nhau. Với field không nhận diện, Jackson có thể từ chối bằng `FAIL_ON_UNKNOWN_PROPERTIES`, bỏ qua bằng `@JsonIgnoreProperties(ignoreUnknown = true)`, thu thập bằng `@JsonAnySetter` hoặc xử lý tập trung qua `DeserializationProblemHandler`. Với enum literal không biết, có thể giữ hành vi fail mặc định, chuyển thành null, dùng constant `@JsonEnumDefaultValue`, chấp nhận khác biệt chữ hoa/thường hoặc tự định nghĩa alias bằng `@JsonCreator`/custom deserializer. Hãy chọn chính sách theo ý nghĩa nghiệp vụ, phân biệt rõ null với missing và unknown, rồi kiểm tra từng trường hợp bằng mapper thực tế.
