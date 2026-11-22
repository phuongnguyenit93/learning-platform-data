# @JsonValue, @JsonFormat và biểu diễn enum hoặc ngày giờ

Jackson chuyển đổi dữ liệu Java thành JSON khi Spring Boot trả response và chuyển JSON thành Java object khi nhận request. Với enum và ngày giờ, cách biểu diễn trên wire có thể khác cách Java lưu trữ bên trong. Một enum có thể được gửi bằng tên hằng số hoặc bằng mã nghiệp vụ; một ngày có thể là chuỗi ISO-8601, chuỗi theo mẫu riêng hoặc timestamp. Nếu không kiểm soát rõ, client có thể gửi đúng kiểu JSON nhưng sai giá trị mà server mong đợi.

Với springdoc-openapi, schema được tạo từ kiểu Java, metadata Jackson và annotation OpenAPI mà phiên bản thư viện hỗ trợ. Vì vậy, cần hiểu đồng thời ba lớp: giá trị Java, JSON thực tế và schema OpenAPI được công bố. Jackson quyết định dữ liệu JSON; Springdoc mô tả hợp đồng để client biết dữ liệu đó có ý nghĩa gì.

## 1. Jackson quyết định hình dạng JSON như thế nào?

Khi controller trả về một object, Spring MVC sử dụng HttpMessageConverter để ghi response. Với JSON, converter thường dùng Jackson ObjectMapper. Khi nhận request có @RequestBody, converter đọc JSON rồi ánh xạ vào kiểu Java.

Ví dụ:

```java
public record ProductResponse(
    Long id,
    String name,
    ProductStatus status
) {
}
```

Nếu ProductStatus không có cấu hình đặc biệt, Jackson thường biểu diễn enum bằng tên hằng số:

```json
{
  "id": 42,
  "name": "Bàn phím cơ",
  "status": "AVAILABLE"
}
```

Tên enum trong Java có thể là chi tiết triển khai. Nếu đổi AVAILABLE thành IN_STOCK, client đang dùng giá trị cũ có thể bị ảnh hưởng. API công khai thường cần một giá trị wire ổn định, được thiết kế độc lập với tên hằng số trong mã nguồn.

Tương tự, một thuộc tính Java kiểu LocalDate hoặc OffsetDateTime thường được biểu diễn thành chuỗi ngày giờ. Định dạng cụ thể phụ thuộc Java Time module, cấu hình ObjectMapper và annotation trên thuộc tính.

## 2. Dùng @JsonValue để chọn giá trị JSON đại diện

@JsonValue đánh dấu một phương thức hoặc field mà kết quả của nó được dùng làm giá trị JSON đại diện cho object. Với enum, cách này hữu ích khi API cần gửi mã nghiệp vụ thay vì tên hằng số Java.

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonValue;

public enum ProductStatus {
    AVAILABLE("available"),
    OUT_OF_STOCK("out-of-stock"),
    DISCONTINUED("discontinued");

    private final String value;

    ProductStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }
}
```

Khi serialize, giá trị enum được gửi thành chuỗi:

```json
"out-of-stock"
```

Thay vì:

```json
"OUT_OF_STOCK"
```

Lợi ích chính là tách tên hằng số Java khỏi giá trị hợp đồng API. Có thể đổi tên hằng số hoặc tái cấu trúc package mà không nhất thiết phải thay đổi giá trị JSON đang được client sử dụng.

### 2.1. @JsonValue trên enum và quá trình deserialize

Với enum, Jackson có thể dùng giá trị @JsonValue để tìm ngược hằng số khi đọc JSON nếu các giá trị đại diện là duy nhất. Ví dụ chuỗi "out-of-stock" có thể được ánh xạ về ProductStatus.OUT_OF_STOCK.

Hãy bảo đảm mỗi giá trị @JsonValue là duy nhất. Nếu hai hằng số cùng trả về "active", Jackson không có một ánh xạ ngược rõ ràng và kết quả có thể không như mong đợi.

Khi cần kiểm soát rõ alias, xử lý lỗi hoặc quy tắc đọc dữ liệu, có thể khai báo @JsonCreator:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING_PAYMENT("pending-payment"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String value;

    OrderStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    @JsonCreator
    public static OrderStatus fromValue(String value) {
        for (OrderStatus status : values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Unsupported order status: " + value
        );
    }
}
```

@JsonCreator ở đây định nghĩa cách chuyển chuỗi đầu vào thành enum. Với API thực tế, nên chuyển lỗi giá trị không hợp lệ thành response validation nhất quán, chẳng hạn 400 Bad Request, thông qua cơ chế xử lý exception của ứng dụng.

### 2.2. @JsonValue không chỉ dành cho enum

Annotation này cũng có thể dùng cho value object khi JSON cần là một giá trị đơn giản:

```java
public record CurrencyCode(String value) {
    @JsonValue
    public String asJson() {
        return value;
    }
}
```

Khi đó, CurrencyCode("VND") có thể được serialize thành chuỗi "VND" thay vì object {"value":"VND"}. Nếu cần đọc chuỗi JSON thành value object, có thể dùng constructor hoặc factory method được đánh dấu @JsonCreator.

Chỉ nên dùng biểu diễn scalar khi nó phù hợp với ý nghĩa dữ liệu. Nếu object có nhiều thuộc tính cần công bố độc lập, giữ cấu trúc object thường rõ ràng hơn.

## 3. @JsonFormat với enum

@JsonFormat có thể thay đổi cách Jackson biểu diễn enum. Với dạng chuỗi thông thường, có thể khai báo:

```java
@JsonFormat(shape = JsonFormat.Shape.STRING)
public enum PaymentMethod {
    CARD,
    BANK_TRANSFER,
    CASH
}
```

Shape.STRING thể hiện enum dưới dạng chuỗi. Đây cũng là dạng mặc định phổ biến của Jackson cho enum. Annotation này không tự đổi CARD thành "card" hoặc "bank-transfer"; muốn dùng giá trị tùy chỉnh, hãy cân nhắc @JsonValue hoặc @JsonProperty trên từng hằng số theo nhu cầu.

Một số cấu hình Jackson toàn cục cũng ảnh hưởng đến enum, chẳng hạn:

- WRITE_ENUMS_USING_TO_STRING: dùng kết quả toString() khi serialize enum.
- READ_ENUMS_USING_TO_STRING: dùng toString() khi deserialize enum.
- READ_UNKNOWN_ENUM_VALUES_AS_NULL: xử lý enum không nhận diện được thành null.
- READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE: dùng hằng số có @JsonEnumDefaultValue nếu được cấu hình hỗ trợ.

Đây là cấu hình của ObjectMapper, có thể tác động tới nhiều DTO cùng lúc. Chỉ bật khi quy ước đó phù hợp toàn bộ API; nếu mỗi enum có hợp đồng khác nhau, cấu hình tại enum hoặc thuộc tính thường dễ kiểm soát hơn.

### 3.1. Biểu diễn enum dưới dạng object

Jackson có hỗ trợ @JsonFormat(shape = JsonFormat.Shape.OBJECT) cho enum trong một số cách dùng, để serialize các thuộc tính bean của enum thành JSON object. Ví dụ enum có mã và nhãn hiển thị có thể được trả về như một object thay vì một chuỗi.

Tuy nhiên, biểu diễn enum thành object làm thay đổi hình dạng hợp đồng:

```json
{
  "code": "pending-payment",
  "label": "Chờ thanh toán"
}
```

Hãy kiểm tra riêng cả serialization lẫn deserialization với phiên bản Jackson đang dùng. Việc đọc JSON object trở lại enum không phải lúc nào cũng tự suy ra được khóa định danh; có thể cần @JsonCreator hoặc deserializer riêng. Với request/response công khai, nếu client chỉ cần mã trạng thái thì chuỗi scalar thường đơn giản và ổn định hơn.

## 4. Mô tả enum trong OpenAPI và Springdoc

Trong OpenAPI, enum dạng chuỗi thường được mô tả bằng schema type string cùng danh sách enum. Ví dụ:

```yaml
ProductStatus:
  type: string
  enum:
    - available
    - out-of-stock
    - discontinued
  description: Trạng thái kinh doanh của sản phẩm.
```

Springdoc có thể suy ra schema enum từ kiểu Java và metadata mà swagger-core nhận diện. Tuy nhiên, cách thư viện suy luận giá trị enum có @JsonValue, @JsonProperty, toString() hoặc custom serializer có thể phụ thuộc phiên bản và cấu hình. Đừng giả định schema chắc chắn luôn khớp với JSON thực tế.

Khi cần công bố rõ các giá trị wire, có thể bổ sung @Schema ở thuộc tính DTO:

```java
public record ProductResponse(
    Long id,

    @Schema(
        type = "string",
        allowableValues = {
            "available",
            "out-of-stock",
            "discontinued"
        },
        example = "available",
        description = "Mã trạng thái sản phẩm trong API."
    )
    ProductStatus status
) {
}
```

Sau khi cấu hình, kiểm tra cả hai đầu:

1. Gọi endpoint thật để xem Jackson trả giá trị JSON nào.
2. Mở /v3/api-docs để xem components.schemas và enum mà Springdoc công bố.

Nếu schema vẫn liệt kê AVAILABLE, OUT_OF_STOCK trong khi JSON trả available, out-of-stock, tài liệu đang không khớp hợp đồng. Hãy điều chỉnh metadata hoặc customizer phù hợp với phiên bản thư viện và kiểm thử output sau khi thay đổi.

## 5. Ngày giờ trong Java: chọn kiểu theo ý nghĩa thời gian

Trước khi định dạng ngày giờ, cần chọn kiểu Java đúng với ý nghĩa dữ liệu:

| Java type | Ý nghĩa | Có múi giờ/offset? | Ví dụ |
|---|---|---:|---|
| LocalDate | Một ngày trên lịch | Không | Ngày sinh, ngày giao hàng dự kiến |
| LocalTime | Giờ trong ngày | Không | Giờ mở cửa |
| LocalDateTime | Ngày và giờ địa phương | Không | Giờ hẹn chưa gắn múi giờ |
| OffsetDateTime | Ngày giờ kèm độ lệch UTC | Có offset | Thời điểm do client gửi kèm +07:00 |
| ZonedDateTime | Ngày giờ gắn vùng thời gian | Có vùng | Lịch tại Asia/Ho_Chi_Minh |
| Instant | Một thời điểm trên dòng thời gian UTC | UTC | Thời điểm tạo bản ghi |

Không dùng LocalDateTime để biểu diễn một thời điểm toàn cầu nếu hệ thống cần biết chính xác thời điểm đó ở đâu trên UTC timeline. LocalDateTime không chứa offset hoặc timezone; cùng một giá trị có thể tương ứng với những thời điểm khác nhau ở các vùng khác nhau.

Với timestamp nghiệp vụ như createdAt, paidAt, expiresAt, thường nên cân nhắc Instant hoặc OffsetDateTime. Với ngày lịch như birthDate, deliveryDate, LocalDate thường phù hợp hơn.

## 6. Java Time module và định dạng mặc định

Để Jackson đọc và ghi các kiểu trong java.time, ứng dụng cần Java Time module (jackson-datatype-jsr310) được đăng ký với ObjectMapper. Spring Boot thường tự cấu hình module có trên classpath thông qua Jackson auto-configuration. Nếu dùng ObjectMapper tự tạo, cần xác nhận module đã được đăng ký.

Ví dụ tạo mapper độc lập:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();
```

Trong ứng dụng Spring Boot, không nên tạo một ObjectMapper riêng cho controller chỉ để định dạng một field vì điều đó có thể bỏ qua các module và cấu hình toàn cục. Ưu tiên cấu hình mapper do Spring quản lý hoặc dùng annotation tại thuộc tính nếu chỉ cần thay đổi cục bộ.

Các kiểu Java Time thường được biểu diễn bằng chuỗi ISO-8601 khi ứng dụng cấu hình Jackson để ghi ngày giờ dưới dạng văn bản. Spring Boot thường tắt chế độ ghi timestamp cho JSON trong cấu hình web mặc định. Có thể đặt rõ:

```yaml
spring:
  jackson:
    serialization:
      write-dates-as-timestamps: false
```

Hành vi thực tế còn phụ thuộc phiên bản Spring Boot/Jackson và cấu hình ứng dụng. Kiểm tra JSON trả về thay vì dựa hoàn toàn vào giá trị mặc định.

## 7. Dùng @JsonFormat để định dạng ngày giờ

@JsonFormat cho phép đặt shape, pattern, locale và timezone tùy kiểu dữ liệu. Với Java Time, pattern được diễn giải bởi bộ định dạng thời gian của module Java Time.

### 7.1. LocalDate

LocalDate biểu diễn ngày lịch, không chứa thời gian hoặc múi giờ:

```java
public record CustomerResponse(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd"
    )
    LocalDate birthDate
) {
}
```

JSON:

```json
{
  "birthDate": "1995-08-21"
}
```

Với LocalDate, không cần gắn timezone vì bản thân kiểu dữ liệu không biểu diễn một thời điểm cần chuyển đổi múi giờ.

### 7.2. LocalDateTime

LocalDateTime biểu diễn ngày giờ địa phương, không có offset:

```java
public record AppointmentRequest(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ss"
    )
    LocalDateTime appointmentAt
) {
}
```

JSON:

```json
{
  "appointmentAt": "2026-11-20T14:30:00"
}
```

Giá trị trên không cho biết 14:30 thuộc múi giờ nào. Nếu hệ thống cần lịch hẹn gắn với địa điểm, hãy lưu hoặc truyền thêm timezone/offset theo một hợp đồng rõ ràng, hoặc dùng ZonedDateTime/OffsetDateTime tùy nhu cầu.

### 7.3. OffsetDateTime

OffsetDateTime chứa độ lệch UTC:

```java
public record PaymentResponse(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX"
    )
    OffsetDateTime paidAt
) {
}
```

JSON:

```json
{
  "paidAt": "2026-11-20T14:30:00+07:00"
}
```

Ký hiệu XXX biểu diễn offset theo dạng như +07:00. Nếu client cần giữ offset mà nó gửi, dùng kiểu có offset thay vì LocalDateTime.

### 7.4. Instant

Instant biểu diễn một thời điểm trên UTC timeline. Dạng ISO-8601 thường có hậu tố Z:

```java
public record AuditResponse(
    Instant createdAt
) {
}
```

JSON ví dụ:

```json
{
  "createdAt": "2026-11-20T07:30:00Z"
}
```

Nếu cần định dạng khác, có thể áp dụng @JsonFormat sau khi kiểm tra cách Jackson xử lý timezone và kiểu Java Time trong phiên bản dự án. Với timestamp dùng trong tích hợp hệ thống, ISO-8601 UTC thường dễ trao đổi và ít gây hiểu nhầm.

## 8. Pattern, locale và timezone cần được dùng đúng

Các thành phần của @JsonFormat có ý nghĩa khác nhau:

| Thuộc tính | Công dụng | Lưu ý |
|---|---|---|
| shape | Chọn hình dạng JSON như STRING hoặc NUMBER | Không phải mọi kiểu Java đều hỗ trợ mọi shape |
| pattern | Mẫu chuỗi ngày giờ | Phải khớp với kiểu Java và dữ liệu đầu vào |
| locale | Quy tắc ngôn ngữ/vùng cho định dạng | Hữu ích với tên tháng hoặc ngày theo locale |
| timezone | Múi giờ dùng khi chuyển đổi các kiểu biểu diễn thời điểm | Không thêm timezone vào LocalDate hoặc LocalDateTime |
| lenient | Điều chỉnh mức độ chấp nhận dữ liệu không nghiêm ngặt trong một số bộ chuyển đổi | Hành vi phụ thuộc kiểu và phiên bản |

Ví dụ dùng pattern:

```java
@JsonFormat(
    shape = JsonFormat.Shape.STRING,
    pattern = "dd/MM/uuuu",
    locale = "vi_VN"
)
LocalDate invoiceDate;
```

JSON có dạng "20/11/2026". Đây là định dạng dễ đọc cho một nhóm người dùng, nhưng các client quốc tế có thể quen với ISO-8601 hơn. Nếu dùng pattern riêng, cần mô tả rõ trong OpenAPI và ví dụ request/response.

Lưu ý về ký hiệu pattern:

- uuuu thường phù hợp khi định dạng năm theo Java Time.
- MM là tháng; mm là phút.
- HH là giờ theo hệ 24 giờ; hh là giờ theo hệ 12 giờ.
- XXX biểu diễn offset như +07:00.
- Dấu nháy đơn dùng để bao quanh ký tự literal, ví dụ chữ T trong ISO-8601.

Không nhầm pattern của Java Time với mọi quy ước của SimpleDateFormat. Dù nhiều ký hiệu giống nhau, một số chi tiết có ý nghĩa khác nhau.

## 9. @JsonFormat không giống @DateTimeFormat

Spring có hai annotation thường được dùng ở các vị trí khác nhau:

| Annotation | Phạm vi chính | Ví dụ |
|---|---|---|
| @JsonFormat | Jackson serialize/deserialize JSON body hoặc JSON response | Field LocalDate trong DTO |
| @DateTimeFormat | Spring conversion cho query parameter, path variable, form field | ?from=2026-11-01 |

Ví dụ tham số query:

```java
@GetMapping("/reports")
public ReportResponse report(
    @RequestParam
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate from
) {
    return reportService.create(from);
}
```

Ví dụ DTO JSON:

```java
public record ReportRequest(
    @JsonFormat(pattern = "uuuu-MM-dd")
    LocalDate from
) {
}
```

Hai annotation không thay thế nhau. Đặt @JsonFormat trên tham số query không phải cách chuẩn để điều khiển Spring MVC chuyển đổi query parameter.

## 10. Springdoc mô tả enum và ngày giờ như thế nào?

Springdoc dùng metadata của kiểu Java, Jackson và annotation OpenAPI để tạo schema. Với kiểu ngày giờ chuẩn, schema thường có dạng:

```yaml
birthDate:
  type: string
  format: date

createdAt:
  type: string
  format: date-time
```

Với enum, schema thường là chuỗi có danh sách enum:

```yaml
status:
  type: string
  enum:
    - available
    - out-of-stock
    - discontinued
```

Nếu @JsonFormat đặt pattern riêng, schema có thể vẫn chỉ thể hiện type string hoặc format date/date-time; không phải mọi pattern Jackson đều được chuyển thành một ràng buộc OpenAPI có thể kiểm tra máy. Hãy bổ sung @Schema(example = ...) và description để người đọc biết chính xác định dạng.

Ví dụ:

```java
public record AppointmentResponse(
    @Schema(
        type = "string",
        format = "date-time",
        example = "2026-11-20T14:30:00"
    )
    @JsonFormat(pattern = "uuuu-MM-dd'T'HH:mm:ss")
    LocalDateTime appointmentAt
) {
}
```

Nếu pattern có giới hạn cụ thể, có thể dùng @Schema(pattern = "...") khi schema cần công bố regex tương ứng và regex đó thực sự mô tả dữ liệu JSON. Không sao chép pattern Jackson sang OpenAPI một cách máy móc vì hai bộ định dạng có cú pháp và mục tiêu khác nhau.

## 11. Ví dụ hoàn chỉnh: enum mã nghiệp vụ và ngày giờ trong DTO

Ví dụ sau dùng mã trạng thái ổn định và timestamp có offset:

```java
public enum ShipmentStatus {
    CREATED("created"),
    IN_TRANSIT("in-transit"),
    DELIVERED("delivered");

    private final String value;

    ShipmentStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    @JsonCreator
    public static ShipmentStatus fromValue(String value) {
        for (ShipmentStatus status : values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown shipment status");
    }
}

public record ShipmentResponse(
    Long shipmentId,

    @Schema(
        type = "string",
        allowableValues = {"created", "in-transit", "delivered"},
        example = "in-transit"
    )
    ShipmentStatus status,

    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX"
    )
    OffsetDateTime updatedAt
) {
}
```

Response JSON có thể là:

```json
{
  "shipmentId": 701,
  "status": "in-transit",
  "updatedAt": "2026-11-20T14:30:00+07:00"
}
```

Schema OpenAPI tương ứng cần thể hiện status là chuỗi với ba giá trị wire và updatedAt là chuỗi ngày giờ có offset. Ví dụ minh họa:

```yaml
ShipmentResponse:
  type: object
  properties:
    shipmentId:
      type: integer
      format: int64
    status:
      type: string
      enum:
        - created
        - in-transit
        - delivered
    updatedAt:
      type: string
      format: date-time
      example: "2026-11-20T14:30:00+07:00"
```

Hãy so sánh JSON thật với schema được springdoc sinh ra. Nếu Jackson và OpenAPI không đồng ý về giá trị enum hoặc định dạng ngày giờ, client generator có thể tạo kiểu hoặc validation không chính xác.

## 12. Cấu hình Jackson toàn cục và tùy biến cục bộ

Có thể cấu hình Jackson trên toàn ứng dụng hoặc chỉ cho một thuộc tính:

| Cách cấu hình | Phạm vi | Khi nên dùng |
|---|---|---|
| spring.jackson.* | Các tính năng toàn cục được Spring Boot hỗ trợ | Quy ước chung cho toàn ứng dụng |
| Jackson2ObjectMapperBuilderCustomizer | Tùy chỉnh mapper do Spring Boot quản lý | Đăng ký module hoặc thay đổi serializer/deserializer chung |
| @JsonValue, @JsonFormat | Enum, class hoặc thuộc tính cụ thể | Hợp đồng riêng của một kiểu dữ liệu |
| @JsonSerialize, @JsonDeserialize | Serializer/deserializer tùy biến | Quy tắc chuyển đổi phức tạp |

Ví dụ tùy chỉnh mapper do Spring Boot quản lý:

```java
@Configuration
public class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> builder.featuresToDisable(
            SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
        );
    }
}
```

Không nên tạo một bean ObjectMapper mới nếu chỉ muốn đổi một định dạng ngày giờ, vì có thể vô tình bỏ qua module Java Time, module parameter names, cấu hình naming strategy hoặc các customizer khác của ứng dụng. Ưu tiên customizer hoặc annotation tại thuộc tính.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đổi tên enum Java và để tên đó trở thành giá trị JSON | Client bị ảnh hưởng bởi refactor nội bộ | Dùng mã wire ổn định bằng @JsonValue hoặc mapping tường minh |
| Hai enum có cùng giá trị @JsonValue | Deserialize có thể mơ hồ | Bảo đảm giá trị đại diện duy nhất |
| Chỉ dùng @Schema để đổi JSON enum | Tài liệu đổi nhưng Jackson vẫn serialize theo quy tắc cũ | Cấu hình Jackson và OpenAPI đồng bộ |
| Chỉ dùng @JsonValue rồi giả định schema luôn đúng | enum trong OpenAPI có thể khác JSON thực tế | Kiểm tra /v3/api-docs và bổ sung metadata |
| Dùng LocalDateTime cho thời điểm toàn cầu | Không có offset để xác định instant | Dùng Instant hoặc OffsetDateTime |
| Đặt timezone cho LocalDate | Tạo cảm giác ngày lịch có chuyển đổi múi giờ | Dùng LocalDate mà không gắn timezone |
| Dùng @DateTimeFormat cho JSON body | Jackson không nhận được định dạng mong muốn | Dùng @JsonFormat cho JSON |
| Pattern dùng mm thay vì MM | Phút bị dùng thay cho tháng | Kiểm tra ký hiệu pattern |
| Khai báo pattern riêng nhưng không ghi example | Client không biết chuỗi cần gửi | Bổ sung @Schema(example = ...) và description |
| Tạo ObjectMapper riêng không đăng ký JavaTimeModule | Không đọc/ghi được kiểu Java Time hoặc cấu hình khác bị mất | Dùng mapper do Spring quản lý và xác nhận module |

## 14. Quy trình kiểm tra Jackson và OpenAPI

Khi thêm hoặc thay đổi enum/ngày giờ trong DTO:

1. Chọn kiểu Java đúng với ý nghĩa dữ liệu: ngày lịch, giờ địa phương hay thời điểm có offset.
2. Xác định giá trị JSON mà client sẽ gửi và nhận.
3. Dùng @JsonValue, @JsonCreator hoặc @JsonFormat khi cần quy tắc riêng.
4. Bổ sung @Schema để mô tả giá trị enum, format, pattern và example nếu cần.
5. Kiểm tra serialization bằng cách gọi endpoint response hoặc dùng ObjectMapper.
6. Kiểm tra deserialization bằng payload request hợp lệ và không hợp lệ.
7. Mở /v3/api-docs để xác nhận schema khớp JSON thực tế.
8. Dùng Swagger UI thử request và kiểm tra ví dụ hiển thị.

Có thể viết unit test cho enum:

```java
@Test
void shouldSerializeAndDeserializeOrderStatus() throws Exception {
    ObjectMapper mapper = objectMapper;

    String json = mapper.writeValueAsString(OrderStatus.PENDING_PAYMENT);
    assertThat(json).isEqualTo("\"pending-payment\"");

    OrderStatus value = mapper.readValue(
        "\"pending-payment\"",
        OrderStatus.class
    );
    assertThat(value).isEqualTo(OrderStatus.PENDING_PAYMENT);
}
```

Và test ngày giờ:

```java
@Test
void shouldUseExpectedOffsetDateTimePattern() throws Exception {
    var response = new PaymentResponse(
        OffsetDateTime.parse("2026-11-20T14:30:00+07:00")
    );

    String json = objectMapper.writeValueAsString(response);

    assertThat(json)
        .contains("2026-11-20T14:30:00+07:00");
}
```

Các ví dụ test giả định objectMapper được inject từ Spring hoặc đã đăng ký module và cấu hình giống môi trường chạy thật. Nếu test dùng một mapper tự tạo khác mapper trong ứng dụng, kết quả có thể không phản ánh hành vi HTTP thực tế.

## 15. Ghi nhớ

- Jackson quyết định JSON thực tế; Springdoc tạo schema OpenAPI từ kiểu Java và metadata được nhận diện.
- @JsonValue chọn giá trị JSON đại diện, đặc biệt hữu ích để enum dùng mã nghiệp vụ ổn định.
- Với enum, giá trị @JsonValue cần duy nhất; dùng @JsonCreator khi muốn kiểm soát chiều đọc JSON.
- @JsonFormat(shape = STRING) giữ enum ở dạng chuỗi; nó không tự đổi tên hằng số thành mã nghiệp vụ.
- Chọn kiểu Java Time theo ý nghĩa: LocalDate cho ngày lịch, LocalDateTime cho giờ địa phương, Instant hoặc OffsetDateTime cho thời điểm.
- @JsonFormat điều khiển JSON; @DateTimeFormat chủ yếu điều khiển Spring conversion cho query/path/form.
- OpenAPI thường dùng string với format date hoặc date-time; enum dùng type string và enum.
- Schema cần khớp JSON thật, nhất là khi dùng custom enum value hoặc pattern ngày giờ.
- Kiểm tra cả serialization, deserialization và /v3/api-docs sau khi thay đổi.

Khi thiết kế biểu diễn enum và ngày giờ, hãy xem giá trị JSON là một phần của hợp đồng API. Dùng @JsonValue để tách mã công khai khỏi tên enum nội bộ, chọn Java Time type phù hợp với ý nghĩa thời gian và dùng @JsonFormat khi cần định dạng riêng. Cuối cùng, xác minh Jackson và Springdoc công bố cùng một cách biểu diễn để client có thể tích hợp ổn định.
