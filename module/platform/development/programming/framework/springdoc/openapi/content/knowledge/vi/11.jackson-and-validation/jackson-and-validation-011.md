# Giữ nhất quán giữa cấu hình ObjectMapper với dữ liệu được mô tả

Springdoc-openapi tạo schema từ kiểu dữ liệu và metadata mà ứng dụng công bố, trong khi Spring MVC dùng Jackson thông qua `HttpMessageConverter` để đọc request và ghi response JSON. Nếu cấu hình Jackson làm thay đổi tên property, cách biểu diễn ngày giờ, enum, giá trị null hoặc cấu trúc đa hình, payload HTTP có thể khác với schema OpenAPI mà client nhìn thấy. Vì vậy, cần xem cấu hình `ObjectMapper`, annotation Jackson và tài liệu được sinh ra như các phần của cùng một hợp đồng API; thay đổi một phần thì phải kiểm tra lại các phần còn lại.

## 1. Ba lớp cần giữ nhất quán

Một DTO có thể được diễn giải theo ba cách:

1. **Mô hình Java:** tên field, getter/setter, kiểu dữ liệu và annotation trên class.
2. **JSON runtime:** tên key, kiểu JSON, giá trị bị bỏ qua, định dạng chuỗi và quy tắc deserialize do Jackson quyết định.
3. **OpenAPI schema:** tên property, type, format, enum, required và mô tả mà springdoc công bố.

Ví dụ, DTO Java có field `createdAt` kiểu `OffsetDateTime`. Jackson có thể serialize thành key `created_at` và chuỗi thời gian có offset; OpenAPI cần mô tả property `created_at` với kiểu string và format ngày giờ tương ứng. Nếu tài liệu vẫn ghi `createdAt`, client generator sẽ tạo model không khớp payload.

| Cấu hình | Tác động lên JSON | Điều cần kiểm tra trong OpenAPI |
|---|---|---|
| Property naming strategy | Đổi tên key, ví dụ camelCase thành snake_case | Tên trong `properties`, `$ref` và ví dụ |
| `@JsonProperty` / `@JsonAlias` | Đặt tên output hoặc tên input thay thế | Tên property công bố và tên client phải gửi |
| `@JsonInclude` | Bỏ qua null, empty hoặc giá trị mặc định khi serialize | Tính optional, nullable và ví dụ response |
| `@JsonFormat` / Java Time module | Đổi định dạng ngày giờ hoặc kiểu enum | `type`, `format`, `pattern` và ví dụ |
| `@JsonSerialize` / `@JsonDeserialize` | Thay đổi biểu diễn hoặc cách đọc một kiểu | Schema phải phản ánh representation thật |
| `@JsonTypeInfo` / `@JsonSubTypes` | Thêm discriminator và chọn subtype khi đọc/ghi | `oneOf`, `discriminator` và schema subtype |
| Visibility, mix-in, JsonView | Thay đổi property được đọc hoặc ghi | Property có xuất hiện đúng trong từng operation không |

Springdoc có thể nhận diện nhiều annotation Jackson và sử dụng metadata Jackson khi tạo schema. Tuy nhiên, mức độ phản ánh các customizer, module, mix-in và converter phụ thuộc phiên bản cùng cấu hình ứng dụng. Không nên giả định mọi tùy chỉnh runtime đều tự động được chuyển thành schema chính xác; hãy xác minh JSON thực tế và `/v3/api-docs`.

## 2. Cấu hình ObjectMapper trong Spring Boot

Spring Boot thường tự cấu hình `ObjectMapper` và các `HttpMessageConverter` dựa trên dependency cùng application properties. Khi cần tùy chỉnh, nên mở rộng cấu hình do Boot quản lý thay vì tạo một `ObjectMapper` độc lập rồi vô tình khiến controller dùng mapper khác.

Ví dụ đổi tên property sang snake_case và bỏ property null khi serialize:

```java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer apiJsonCustomizer() {
        return builder -> {
            builder.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
            builder.serializationInclusion(JsonInclude.Include.NON_NULL);
        };
    }
}
```

Với cấu hình trên, field Java `productCode` thường được serialize thành `product_code`; property có giá trị `null` bị bỏ qua trong JSON output. Tùy chỉnh được áp dụng vào builder mà Spring Boot sử dụng để tạo mapper cho các converter được auto-configure.

Không nên khai báo một bean `new ObjectMapper()` riêng mà không hiểu cách nó tương tác với mapper do Boot quản lý. Nếu ứng dụng có nhiều converter hoặc nhiều mapper cho các media type khác nhau, hãy xác định rõ endpoint nào dùng mapper nào và tài liệu cần phản ánh representation nào.

### Khi nào dùng application properties?

Một số tùy chọn Jackson có thể cấu hình qua `application.yml` hoặc `application.properties`, ví dụ property naming strategy và serialization inclusion. Dù dùng properties hay `Jackson2ObjectMapperBuilderCustomizer`, mục tiêu vẫn là cấu hình mapper thực sự được HTTP converter sử dụng. Tránh cấu hình cùng một tùy chọn ở nhiều nơi với giá trị mâu thuẫn.

## 3. Property naming strategy và tên field trong schema

Jackson hỗ trợ các chiến lược đặt tên như `LOWER_CAMEL_CASE`, `SNAKE_CASE`, `KEBAB_CASE` và `UPPER_CAMEL_CASE`. Với `SNAKE_CASE`, field `productCode` thường trở thành `product_code` trong JSON.

DTO minh họa:

```java
public record ProductResponse(
    Long id,
    String productCode,
    String displayName,
    BigDecimal sellingPrice
) {}
```

Payload thực tế với naming strategy snake_case:

```json
{
  "id": 101,
  "product_code": "P-001",
  "display_name": "Bút bi",
  "selling_price": 12000
}
```

Schema OpenAPI tương ứng cần dùng đúng tên JSON:

```yaml
ProductResponse:
  type: object
  properties:
    id:
      type: integer
      format: int64
    product_code:
      type: string
    display_name:
      type: string
    selling_price:
      type: number
```

Springdoc có thể lấy naming strategy từ Jackson introspection trong cấu hình tương ứng. Hãy kiểm tra schema đầu ra sau khi thay đổi global naming strategy, đặc biệt nếu ứng dụng đã có các DTO dùng `@JsonProperty` hoặc mix-in.

### Dùng @JsonProperty để đặt tên tường minh

`@JsonProperty` chỉ định tên property trong JSON. Tên tường minh thường được ưu tiên hơn naming strategy chung:

```java
public record ProductResponse(
    @JsonProperty("product_code") String productCode,
    @JsonProperty("displayName") String displayName
) {}
```

Trong ví dụ, `productCode` được công bố dưới tên `product_code`, còn `displayName` được giữ camelCase dù mapper dùng snake_case. Tài liệu OpenAPI phải theo tên JSON bên ngoài mà client thực sự gửi hoặc nhận, không theo tên component Java.

### Dùng @JsonAlias cho tên đầu vào cũ

`@JsonAlias` khai báo một hoặc nhiều tên thay thế được chấp nhận khi deserialize. Nó không đổi tên property khi serialize:

```java
public record ProductUpdateRequest(
    @JsonProperty("product_code")
    @JsonAlias({"productCode", "code"})
    String productCode
) {}
```

Trong trường hợp này, server có thể nhận `product_code`, `productCode` hoặc `code`, nhưng output theo tên chính `product_code`. OpenAPI thông thường mô tả tên chuẩn mà API công bố; các alias đầu vào là khả năng tương thích bổ sung và cần được giải thích trong description nếu client cần biết.

Không đưa tất cả alias thành nhiều property độc lập trong schema, vì chúng cùng ánh xạ vào một giá trị Java. Nếu muốn loại bỏ alias cũ, cần đánh giá client đang dùng chúng trước khi thay đổi hành vi deserialize.

## 4. @JsonInclude và khác biệt giữa optional, null và required

`@JsonInclude` điều khiển khi nào Jackson ghi property vào JSON output. Một số chế độ phổ biến:

| Giá trị | Hành vi serialize |
|---|---|
| `ALWAYS` | Luôn ghi property theo cấu hình serializer |
| `NON_NULL` | Bỏ property nếu giá trị là `null` |
| `NON_EMPTY` | Bỏ giá trị rỗng như chuỗi rỗng, collection rỗng hoặc null theo định nghĩa serializer |
| `NON_DEFAULT` | Bỏ giá trị được xem là mặc định theo quy tắc Jackson |

Có thể cấu hình ở cấp class:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ProductResponse(
    Long id,
    String name,
    String description,
    List<String> labels
) {}
```

Nếu `description` là `null`, Jackson có thể không ghi key `description` vào response. Nếu `labels` là danh sách rỗng và dùng `NON_EMPTY`, key `labels` cũng có thể bị bỏ qua.

Điều này cần được phân biệt với các khái niệm OpenAPI:

- **Required:** property phải hiện diện trong object. Nó được biểu diễn trong danh sách `required` của schema.
- **Optional:** property có thể không xuất hiện trong object.
- **Nullable:** property có thể hiện diện với giá trị JSON `null`. Cách biểu diễn cụ thể phụ thuộc phiên bản OpenAPI.
- **Omitted:** Jackson không ghi property vào JSON output trong trường hợp giá trị thỏa điều kiện `JsonInclude`.

Một property không có trong danh sách `required` không tự động có nghĩa nó nhận `null`; nó chỉ không bắt buộc phải xuất hiện. Ngược lại, property có thể được đánh dấu nullable nhưng vẫn bắt buộc phải có key. Trong OpenAPI 3.0, `nullable: true` thường dùng để diễn tả giá trị null; trong OpenAPI 3.1, có thể biểu diễn null trong type theo mô hình JSON Schema.

Vì `NON_NULL` ảnh hưởng response serialization, schema nên mô tả property là không bắt buộc nếu server có thể bỏ nó khỏi payload. Đừng tự suy ra mọi thuộc tính nullable chỉ từ `@JsonInclude`; hãy xem cả kiểu Java, validation, schema sinh ra và ví dụ response.

## 5. Định dạng ngày giờ và Java Time module

Jackson cần module hỗ trợ các kiểu ngày giờ Java như `LocalDate`, `LocalDateTime`, `OffsetDateTime` và `Instant`. Spring Boot thường tự đăng ký module Java Time khi dependency tương ứng có mặt. Với hợp đồng API, nên chọn representation rõ ràng và dùng định dạng ISO 8601 khi phù hợp.

Ví dụ:

```java
public record OrderResponse(
    LocalDate orderDate,
    @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
    OffsetDateTime createdAt,
    Instant processedAt
) {}
```

Payload có thể có dạng:

```json
{
  "orderDate": "2026-11-20",
  "createdAt": "2026-11-20T14:30:00+07:00",
  "processedAt": "2026-11-20T07:30:00Z"
}
```

Schema OpenAPI thường mô tả `orderDate` là `string` với `format: date`, còn các timestamp là `string` với `format: date-time`. Nếu dùng pattern tùy chỉnh, có thể bổ sung `description` hoặc `example` để client hiểu chính xác múi giờ và độ chính xác được sử dụng.

`LocalDateTime` không mang thông tin múi giờ. Nếu nghiệp vụ cần một thời điểm toàn cầu, cân nhắc `Instant` hoặc `OffsetDateTime`; việc dùng `LocalDateTime` rồi ngầm giả định múi giờ có thể làm client diễn giải sai dữ liệu.

## 6. Enum và cách Jackson biểu diễn giá trị

Enum Java có thể được serialize thành tên hằng số, ordinal hoặc một giá trị tùy chỉnh. Cấu hình Jackson và annotation có thể làm representation khác với tên enum trong mã nguồn.

Ví dụ enum dùng code công khai:

```java
public enum OrderStatus {
    NEW("new"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String getCode() {
        return code;
    }

    @JsonCreator
    public static OrderStatus fromCode(String value) {
        return Arrays.stream(values())
            .filter(status -> status.code.equalsIgnoreCase(value))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException("Unknown status: " + value));
    }
}
```

JSON dùng `"paid"`, không dùng tên hằng số `"PAID"`. Nếu schema OpenAPI lại công bố enum là `NEW`, `PAID`, `CANCELLED`, client có thể gửi giá trị không đúng với deserializer.

Với enum có `@JsonValue`, `@JsonCreator` hoặc custom serializer, hãy kiểm tra schema `enum` và ví dụ được sinh ra. Nếu springdoc không suy luận đúng representation tùy chỉnh, có thể mô tả property bằng `@Schema` hoặc dùng DTO/API enum riêng có representation đơn giản và ổn định.

Không nên bật chế độ serialize enum thành ordinal số nguyên cho API công khai nếu không có lý do tương thích rõ ràng. Thứ tự enum có thể thay đổi khi thêm phần tử, làm giá trị số cũ bị diễn giải sai.

## 7. Custom serializer và deserializer

Jackson cho phép thay đổi cách một kiểu Java được đọc hoặc ghi bằng `@JsonSerialize` và `@JsonDeserialize`, hoặc đăng ký module tùy chỉnh. Đây là nguồn sai lệch quan trọng vì schema suy luận từ kiểu Java có thể không phản ánh representation do serializer tạo ra.

Ví dụ một kiểu tiền tệ được ghi thành chuỗi:

```java
public record Money(BigDecimal amount, String currency) {}

public class MoneySerializer extends JsonSerializer<Money> {
    @Override
    public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider
    ) throws IOException {
        generator.writeString(value.amount().toPlainString() + " " + value.currency());
    }
}
```

Gắn serializer:

```java
public record InvoiceResponse(
    Long id,
    @JsonSerialize(using = MoneySerializer.class)
    Money total
) {}
```

Runtime JSON có thể là:

```json
{
  "id": 501,
  "total": "125000.00 VND"
}
```

Nếu schema được suy luận như object có `amount` và `currency`, tài liệu sẽ không khớp payload. Trong trường hợp này, mô tả `total` là string, kèm format/description/example phù hợp bằng annotation hoặc customizer OpenAPI. Với API cần tính toán tiền tệ, representation số cùng currency field riêng thường dễ sinh client và xử lý hơn chuỗi định dạng hiển thị.

Deserializer tùy chỉnh cũng cần được kiểm tra ở chiều request. Nếu server nhận một chuỗi định dạng riêng rồi chuyển thành object, schema phải mô tả đúng kiểu client gửi. Không nên dùng một kiểu Java phức tạp nếu wire format thực tế là một primitive mà không bổ sung metadata tương ứng.

## 8. Polymorphism và discriminator

Một property có thể chứa nhiều subtype khác nhau. Jackson dùng `@JsonTypeInfo` và `@JsonSubTypes` để chọn subtype dựa trên discriminator hoặc metadata khác.

Ví dụ:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank_transfer")
})
public sealed interface PaymentMethod
    permits CardPayment, BankTransfer {}

public record CardPayment(String lastFourDigits) implements PaymentMethod {}
public record BankTransfer(String bankCode, String accountNumber) implements PaymentMethod {}
```

JSON có thể có một trong hai dạng:

```json
{
  "kind": "card",
  "lastFourDigits": "4242"
}
```

```json
{
  "kind": "bank_transfer",
  "bankCode": "ABC",
  "accountNumber": "001234"
}
```

OpenAPI nên mô tả schema cơ sở bằng `oneOf` và discriminator `kind`, cùng các schema subtype. Ví dụ:

```yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransfer'
  discriminator:
    propertyName: kind
    mapping:
      card: '#/components/schemas/CardPayment'
      bank_transfer: '#/components/schemas/BankTransfer'
```

Không phải mọi cấu hình Jackson polymorphic đều tự tạo ra schema `oneOf`/`discriminator` đúng như mong đợi. Hãy kiểm tra `/v3/api-docs`; khi cần, dùng `@Schema(oneOf = {...}, discriminatorProperty = "kind")` hoặc customizer để mô tả hợp đồng. Các subtype phải thực sự được serializer/deserializer hỗ trợ.

## 9. Property visibility, mix-in và JsonView

Jackson có thể thay đổi tập property được serialize hoặc deserialize bằng `@JsonAutoDetect`, `@JsonIgnoreProperties`, mix-in và `@JsonView`. Những cơ chế này cần được cân nhắc khi schema được tạo tự động.

### Property visibility

`@JsonAutoDetect` điều khiển Jackson có nhìn thấy field, getter, setter hoặc creator hay không. Ví dụ, cấu hình field visibility rộng có thể khiến các field private được serialize dù trước đó chỉ getter công khai được dùng. Nếu schema vẫn dựa trên một tập property khác, tài liệu có thể thiếu field hoặc xuất hiện field không mong muốn.

### Mix-in

Jackson mix-in cho phép gắn annotation vào một class mà không sửa class gốc. Đây là cách hữu ích với kiểu từ thư viện ngoài hoặc entity không thể chỉnh sửa. Tuy nhiên, khả năng springdoc nhìn thấy mix-in phụ thuộc ObjectMapper/model converter mà phiên bản đang dùng sử dụng. Sau khi đăng ký mix-in, hãy kiểm tra cả JSON output và schema OpenAPI.

### JsonView

`@JsonView` cho phép chọn nhóm property theo view của từng operation. Ví dụ response chi tiết có thể chứa nhiều trường hơn response danh sách. Nếu controller dùng các view khác nhau, tài liệu cũng cần mô tả đúng schema tương ứng cho từng operation; không nên giả định một schema chung luôn thể hiện được mọi view. Có thể dùng DTO riêng nếu các view khác nhau đáng kể hoặc client generator cần model rõ ràng.

## 10. Cấu hình xử lý field không biết và additionalProperties

Jackson có tùy chọn quyết định việc deserialize có thất bại khi JSON chứa property không được khai báo trong DTO hay không. Một ứng dụng có thể bỏ qua field lạ hoặc từ chối request tùy cấu hình `FAIL_ON_UNKNOWN_PROPERTIES` và annotation trên class.

OpenAPI Schema Object có thể dùng `additionalProperties` để mô tả việc object cho phép các property ngoài danh sách đã khai báo. Nếu runtime từ chối field lạ nhưng schema để mặc định cho phép, client có thể gửi payload mà tài liệu dường như chấp nhận nhưng server lại trả lỗi. Ngược lại, nếu runtime bỏ qua field lạ nhưng schema khai báo `additionalProperties: false`, hợp đồng nghiêm ngặt hơn hành vi thực tế.

Ví dụ schema chỉ cho phép các property được liệt kê:

```yaml
CreateProductRequest:
  type: object
  additionalProperties: false
  required: [name, price]
  properties:
    name:
      type: string
    price:
      type: number
```

Nếu chọn chính sách từ chối field lạ, cần cấu hình Jackson và kiểm thử để hành vi runtime thống nhất với schema. Nếu chọn bỏ qua field lạ để hỗ trợ tương thích, hãy mô tả chính sách đó rõ ràng. Không nên bật/tắt `FAIL_ON_UNKNOWN_PROPERTIES` chỉ vì muốn schema trông nghiêm ngặt hơn mà chưa đánh giá client hiện tại.

## 11. Không dùng một ObjectMapper khác với mapper của HTTP converter

Một lỗi thường gặp là test hoặc code nghiệp vụ tạo `new ObjectMapper()` trong khi Spring MVC dùng mapper do Boot cấu hình. Hai mapper có thể khác naming strategy, module ngày giờ, inclusion, enum hoặc custom serializer.

Trong test Spring, nên inject đúng bean `ObjectMapper` của ứng dụng:

```java
@SpringBootTest
class JacksonContractTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesSnakeCaseAndOmitsNull() throws Exception {
        ProductResponse response = new ProductResponse(
            101L,
            "P-001",
            "Bút bi",
            new BigDecimal("12000")
        );

        JsonNode json = objectMapper.readTree(
            objectMapper.writeValueAsBytes(response)
        );

        assertThat(json.has("product_code")).isTrue();
        assertThat(json.has("productCode")).isFalse();
    }
}
```

Ví dụ kiểm tra trên giả định DTO và cấu hình snake_case đã được khai báo. Nếu cần kiểm tra response HTTP thực tế, dùng MockMvc để đi qua đúng `HttpMessageConverter` thay vì chỉ gọi `ObjectMapper` trực tiếp.

## 12. Kiểm tra OpenAPI và JSON runtime song song

Sau mỗi thay đổi cấu hình Jackson, hãy kiểm tra hai đầu ra.

**JSON runtime:**

- Gửi request mẫu và xác nhận các tên key, kiểu giá trị, định dạng ngày giờ, enum và hành vi null.
- Kiểm tra JSON response từ endpoint, không chỉ object Java trước serialization.
- Xác nhận custom serializer/deserializer hoạt động theo media type thực tế.

**OpenAPI:**

- Tải `/v3/api-docs` hoặc `/v3/api-docs.yaml`.
- Kiểm tra property name và schema type.
- Kiểm tra enum, format, pattern, required, nullable và ví dụ.
- Kiểm tra subtype, discriminator, `oneOf` và `additionalProperties` nếu dùng.
- Kiểm tra các `$ref` trong request body và response.

Ví dụ MockMvc kiểm tra response và tài liệu:

```java
mockMvc.perform(get("/api/products/101"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.product_code").value("P-001"))
    .andExpect(jsonPath("$.productCode").doesNotExist());

mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.ProductResponse.properties.product_code"
    ).exists())
    .andExpect(jsonPath(
        "$.components.schemas.ProductResponse.properties.productCode"
    ).doesNotExist());
```

Đường dẫn JSONPath cần điều chỉnh theo tên component và cấu hình nhóm tài liệu của ứng dụng. Nếu schema đúng nhưng payload HTTP sai, kiểm tra converter/ObjectMapper runtime. Nếu payload đúng nhưng schema sai, kiểm tra model converter, annotation Swagger và cấu hình springdoc.

## 13. Các dấu hiệu không nhất quán thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| JSON dùng snake_case nhưng schema dùng camelCase | Naming strategy runtime không được phản ánh vào schema | Kiểm tra mapper mà springdoc sử dụng, annotation tên tường minh và schema sinh ra |
| `@JsonAlias` được hiểu thành nhiều property | Nhầm alias deserialize với tên output | Công bố tên chuẩn; mô tả alias trong description nếu cần |
| Field null biến mất nhưng schema đánh dấu required | Inclusion và required chưa thống nhất | Kiểm tra `@JsonInclude`, validation và danh sách `required` |
| Timestamp runtime khác format trong schema | `@JsonFormat` hoặc Java Time module làm đổi representation | Đồng bộ format/example và kiểm tra JSON thật |
| Enum runtime trả code nhưng schema liệt kê tên hằng | `@JsonValue` hoặc custom serializer không được phản ánh | Override schema enum hoặc dùng representation ổn định |
| Custom serializer trả string nhưng schema là object/number | Schema được suy luận từ kiểu Java | Dùng `@Schema` hoặc OpenApiCustomizer để mô tả wire format |
| Polymorphic JSON có discriminator nhưng schema không có oneOf | Model converter không suy luận đầy đủ subtype | Khai báo oneOf/discriminator và kiểm tra từng subtype |
| Runtime từ chối field lạ nhưng schema cho phép | Jackson unknown-property policy khác `additionalProperties` | Đồng bộ cấu hình runtime và schema |
| Unit test serialize khác response HTTP | Test dùng ObjectMapper khác HTTP converter | Inject mapper của Spring hoặc kiểm tra bằng MockMvc |

## 14. Quy trình thay đổi ObjectMapper an toàn

Khi cần thay đổi cấu hình JSON của ứng dụng, thực hiện theo trình tự:

1. Xác định endpoint và DTO bị ảnh hưởng, gồm request lẫn response.
2. Ghi lại payload JSON hiện tại và schema OpenAPI hiện tại để có mốc so sánh.
3. Thay đổi một nhóm cấu hình có liên quan, chẳng hạn naming strategy, inclusion hoặc date/time format.
4. Kiểm tra annotation cục bộ như `@JsonProperty`, `@JsonAlias`, `@JsonFormat`, `@JsonValue` và custom serializer có ghi đè cấu hình chung không.
5. Dùng đúng mapper/converter của Spring để serialize và deserialize payload đại diện.
6. Tải `/v3/api-docs` và so sánh property, type, enum, format, required và examples.
7. Chạy kiểm thử HTTP cho cả request hợp lệ, request sai định dạng và response.
8. Đánh giá tác động tương thích với client generator và các client đang sử dụng API.
9. Ghi nhận thay đổi hợp đồng nếu wire format thực sự thay đổi; không coi đây chỉ là refactor nội bộ.

Nếu nhiều endpoint có yêu cầu JSON khác nhau, cân nhắc dùng DTO riêng hoặc converter riêng với hợp đồng được mô tả rõ. Một global ObjectMapper áp dụng cho toàn ứng dụng có thể làm thay đổi hàng loạt endpoint cùng lúc.

## 15. Tài liệu tham khảo

- [Spring Boot – Jackson](https://docs.spring.io/spring-boot/reference/features/json.html): cấu hình Jackson và các tùy chỉnh JSON trong Spring Boot.
- [Jackson Databind](https://github.com/FasterXML/jackson-databind): ObjectMapper, serialization, deserialization và module.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations): `@JsonProperty`, `@JsonAlias`, `@JsonInclude`, `@JsonFormat`, `@JsonView` và các annotation khác.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): type, format, enum, required, nullable, discriminator và additionalProperties.
- [Springdoc OpenAPI](https://springdoc.org/): tích hợp Jackson metadata và tạo schema OpenAPI từ Spring Boot.
