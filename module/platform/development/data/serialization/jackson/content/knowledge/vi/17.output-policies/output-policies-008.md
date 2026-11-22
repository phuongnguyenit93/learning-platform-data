# Biểu diễn một đối tượng bằng JsonValue

Thông thường, Jackson serialize một object Java thành JSON object với nhiều property. Nhưng có những kiểu trong domain chỉ đại diện cho một giá trị duy nhất: mã tiền tệ, địa chỉ email, mã sản phẩm, số điện thoại, đơn vị đo hoặc một trạng thái có mã giao tiếp riêng.

Trong các trường hợp đó, JSON object có thể tạo ra cấu trúc dư thừa. Ví dụ, một EmailAddress chỉ chứa một chuỗi nhưng nếu serialize theo bean convention, kết quả có thể là:

~~~json
{
  "value": "minh@example.com"
}
~~~

Nếu hợp đồng API muốn biểu diễn trực tiếp bằng JSON string:

~~~json
"minh@example.com"
~~~

Jackson cung cấp annotation **@JsonValue** để chọn một accessor làm biểu diễn JSON duy nhất của instance. Accessor đó có thể là method hoặc field; giá trị nó trả về sẽ được serialize như một JSON value.

@JsonValue đặc biệt hữu ích với value object và enum có mã giao tiếp riêng. Tuy nhiên, cần thiết kế cả chiều đọc và chiều ghi: với class thông thường, @JsonValue chủ yếu xác định cách serialize; muốn deserialize ngược từ scalar JSON, thường cần thêm @JsonCreator ở chế độ DELEGATING.

## 1. @JsonValue thay đổi hình dạng JSON như thế nào?

Không có @JsonValue, Jackson thường xem object là tập hợp các property có thể serialize:

~~~java
public final class ProductCode {

    private final String value;

    public ProductCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Kết quả thông thường:

~~~json
{
  "value": "SKU-100"
}
~~~

Khi đánh dấu accessor bằng @JsonValue:

~~~java
import com.fasterxml.jackson.annotation.JsonValue;

public final class ProductCode {

    private final String value;

    public ProductCode(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

Kết quả:

~~~json
"SKU-100"
~~~

Jackson lấy kết quả của method value() và serialize nó như giá trị đại diện cho ProductCode. Hợp đồng JSON lúc này là một string scalar, không phải object có field value.

Có thể hình dung:

~~~text
ProductCode instance
       |
       v
@JsonValue accessor
       |
       v
     String
       |
       v
JSON string: "SKU-100"
~~~

Đây không phải cách đổi tên property. @JsonProperty("value") vẫn tạo một property trong JSON object; @JsonValue thay biểu diễn của toàn bộ instance bằng giá trị accessor trả về.

## 2. Khi nào nên dùng @JsonValue?

@JsonValue phù hợp khi kiểu Java là một value object có đúng một biểu diễn bên ngoài ổn định.

Các ví dụ:

| Kiểu Java | Giá trị @JsonValue | JSON có thể dùng |
|---|---|---|
| EmailAddress | String email | "minh@example.com" |
| ProductCode | String code | "SKU-100" |
| CurrencyCode | String ISO code | "VND" |
| Percentage | BigDecimal value | 12.5 |
| FeatureEnabled | boolean | true |
| OrderStatus | String code | "IN_PROGRESS" |
| Coordinates | List/array hoặc object biểu diễn tọa độ | [10.7, 106.6] hoặc object theo hợp đồng |

Dùng @JsonValue khi:

- Instance đại diện cho một giá trị duy nhất.
- JSON scalar là hợp đồng rõ ràng và tự nhiên hơn object có một field.
- Cần che giấu cấu trúc triển khai nội bộ của value object.
- Tên thuộc tính Java không nên xuất hiện trong API.
- Enum cần serialize bằng mã ổn định thay vì tên constant Java.

Không nên dùng chỉ để làm JSON ngắn hơn. Nếu object có nhiều thuộc tính độc lập, các field đó thường cần được biểu diễn tường minh để consumer hiểu và cập nhật từng phần.

## 3. Chọn accessor cho @JsonValue

@JsonValue có thể được đặt trên method hoặc field.

### 3.1. Đánh dấu method

Đây là cách thường dễ đọc nhất:

~~~java
public final class CurrencyCode {

    private final String code;

    public CurrencyCode(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }
}
~~~

Method có thể trả về giá trị đã chuẩn hóa hoặc một biểu diễn ổn định. Ví dụ, class lưu mã tiền tệ theo dạng chuẩn uppercase và accessor trả mã đó.

Nên để accessor không có side effect. Serialization có thể diễn ra nhiều lần, trong nhiều request và ở nhiều context; method không nên gọi database, thay đổi trạng thái hoặc phụ thuộc vào thời điểm hiện tại.

### 3.2. Đánh dấu field

Jackson cũng hỗ trợ đặt annotation trên field:

~~~java
public final class ProductCode {

    @JsonValue
    private final String value;

    public ProductCode(String value) {
        this.value = value;
    }
}
~~~

Cách này phù hợp khi field chính là biểu diễn bên ngoài và không cần logic tính toán.

Dù dùng field hay method, hãy chọn một điểm biểu diễn duy nhất cho class. Không đánh dấu nhiều accessor @JsonValue với ý định xuất nhiều property; annotation này xác định một giá trị đại diện, không phải danh sách property.

### 3.3. Giá trị trả về phải serialize được

Accessor có thể trả về kiểu scalar như String, boolean hoặc number; cũng có thể trả về một cấu trúc mà Jackson biết cách serialize như List, Map, array, JsonNode hoặc một DTO khác.

Ví dụ trả về hai tọa độ dưới dạng array:

~~~java
public record GeoPoint(double latitude, double longitude) {

    @JsonValue
    public List<Double> coordinates() {
        return List.of(latitude, longitude);
    }
}
~~~

Kết quả:

~~~json
[10.7, 106.6]
~~~

Hợp đồng lúc này quy định phần tử thứ nhất là latitude và phần tử thứ hai là longitude. Consumer phải biết thứ tự này; nếu thứ tự có thể gây nhầm, một JSON object với tên field có thể rõ ràng hơn.

Nếu accessor trả về một object khác, Jackson sẽ serialize giá trị trả về theo quy tắc của kiểu đó. Hãy tránh trả về chính instance hiện tại vì có thể tạo vòng lặp hoặc đệ quy không kết thúc.

## 4. Ví dụ value object biểu diễn bằng JSON string

EmailAddress là ví dụ điển hình:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public final class EmailAddress {

    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public EmailAddress(String value) {
        if (value == null || value.isBlank() || !value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }

        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

Serialize:

~~~java
ObjectMapper mapper = new ObjectMapper();

EmailAddress email = new EmailAddress("minh@example.com");

String json = mapper.writeValueAsString(email);
~~~

Kết quả:

~~~json
"minh@example.com"
~~~

Deserialize:

~~~java
EmailAddress restored =
    mapper.readValue(json, EmailAddress.class);
~~~

Kết quả là một EmailAddress được tạo từ JSON string.

Hai annotation có trách nhiệm khác nhau:

- @JsonValue quyết định instance được ghi thành JSON value nào.
- @JsonCreator(mode = DELEGATING) quyết định JSON value được chuyển vào constructor/factory như thế nào khi đọc.

Kết hợp chúng tạo một hợp đồng hai chiều rõ ràng.

## 5. Vì sao class thông thường cần @JsonCreator?

@JsonValue được thiết kế chủ yếu cho serialization. Với enum, Jackson có hỗ trợ đặc biệt để dùng giá trị @JsonValue khi tìm constant tương ứng trong quá trình deserialize.

Với class thông thường, không nên giả định rằng Jackson tự suy ra constructor ngược từ method @JsonValue. Hãy khai báo creator tường minh.

Ví dụ chỉ có @JsonValue:

~~~java
public final class ProductCode {

    private final String value;

    public ProductCode(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

Class này đã xác định cách ghi ra JSON string. Nhưng nếu cần đọc JSON string trở lại ProductCode, hãy cung cấp constructor hoặc factory được đánh dấu @JsonCreator:

~~~java
@JsonCreator(mode = JsonCreator.Mode.DELEGATING)
public ProductCode(String value) {
    this.value = value;
}
~~~

DELEGATING có nghĩa toàn bộ JSON value được truyền cho một tham số creator. Nó phù hợp với JSON scalar như string, number hoặc boolean, cũng như một cấu trúc được nhận qua JsonNode.

Nếu dùng PROPERTIES cho creator một tham số, Jackson sẽ hiểu tham số như một property của JSON object theo cấu hình tương ứng. Điều đó không khớp với hợp đồng JSON string đơn.

## 6. Dùng static factory làm chiều deserialize

Không bắt buộc creator phải là constructor. Có thể dùng static factory method để chuẩn hóa hoặc kiểm tra dữ liệu:

~~~java
public final class ProductCode {

    private final String value;

    private ProductCode(String value) {
        this.value = value;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static ProductCode fromJson(String rawValue) {
        if (rawValue == null || rawValue.isBlank()) {
            throw new IllegalArgumentException("Product code is required");
        }

        String normalized = rawValue.trim().toUpperCase(Locale.ROOT);
        return new ProductCode(normalized);
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

Khi đọc JSON:

~~~json
" sku-100 "
~~~

factory nhận chuỗi, chuẩn hóa rồi tạo ProductCode. Khi ghi, @JsonValue xuất mã đã chuẩn hóa:

~~~json
"SKU-100"
~~~

Lưu ý rằng việc chuẩn hóa làm thay đổi biểu diễn đầu vào. Đây là quyết định hợp đồng: nếu cần round-trip giữ nguyên chính xác chuỗi gốc, không trim hoặc đổi casing. Nếu hợp đồng quy định mã canonical, hãy test rằng mọi input hợp lệ đều serialize về đúng canonical form.

## 7. @JsonValue với enum và mã giao tiếp ổn định

Enum Java thường serialize bằng tên constant:

~~~java
public enum PaymentStatus {
    PENDING,
    PAID,
    FAILED
}
~~~

JSON mặc định thường là:

~~~json
"PAID"
~~~

Nếu tên constant Java không nên trở thành hợp đồng bên ngoài, hãy định nghĩa mã riêng:

~~~java
public enum PaymentStatus {
    PENDING("P"),
    PAID("S"),
    FAILED("F");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }
}
~~~

Kết quả serialize:

~~~java
mapper.writeValueAsString(PaymentStatus.PAID);
~~~

~~~json
"S"
~~~

Tên constant có thể được đổi trong code mà không nhất thiết thay đổi mã JSON, miễn là code giao tiếp vẫn ổn định.

### 7.1. Deserialize enum từ giá trị @JsonValue

Jackson hỗ trợ đặc biệt enum: giá trị do @JsonValue trả về có thể được dùng để tìm enum constant khi deserialize.

Ví dụ:

~~~java
PaymentStatus status =
    mapper.readValue("\"S\"", PaymentStatus.class);
~~~

Kết quả là PaymentStatus.PAID.

Mỗi constant nên có mã duy nhất. Nếu hai constant trả cùng một giá trị @JsonValue, việc tra cứu ngược sẽ không còn xác định và có thể dẫn đến kết quả không mong muốn.

### 7.2. Khi cần chính sách enum tường minh

Nếu cần alias, chuẩn hóa hoặc cách xử lý mã không biết riêng, có thể khai báo @JsonCreator:

~~~java
public enum PaymentStatus {
    PENDING("P"),
    PAID("S"),
    FAILED("F");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static PaymentStatus fromCode(String code) {
        for (PaymentStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }

        throw new IllegalArgumentException("Unknown payment status");
    }
}
~~~

Factory này áp dụng chính sách strict: mã không biết bị từ chối. Nếu muốn fallback, hãy định nghĩa rõ constant và hành vi nghiệp vụ. Đừng biến mọi mã lạ thành một trạng thái có thể thực hiện thanh toán hoặc chuyển trạng thái một cách âm thầm.

## 8. @JsonValue không phải @JsonProperty

Hai annotation có mục đích khác nhau:

| Annotation | Tác dụng | Hình dạng JSON thường gặp |
|---|---|---|
| @JsonProperty("code") | Đặt tên cho một property | {"code":"SKU-100"} |
| @JsonValue | Dùng giá trị accessor làm biểu diễn của toàn instance | "SKU-100" |

Ví dụ @JsonProperty:

~~~java
public class ProductCode {

    private final String value;

    @JsonProperty("code")
    public String getValue() {
        return value;
    }
}
~~~

JSON:

~~~json
{
  "code": "SKU-100"
}
~~~

Ví dụ @JsonValue:

~~~java
public class ProductCode {

    private final String value;

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

JSON:

~~~json
"SKU-100"
~~~

Nếu API cần tên field để người đọc hiểu cấu trúc, @JsonProperty thường phù hợp. Nếu kiểu Java thực sự là một giá trị đơn, @JsonValue thể hiện bản chất value object tốt hơn.

## 9. @JsonValue không giống @JsonUnwrapped

@JsonUnwrapped làm phẳng property của object lồng vào object cha. Nó vẫn hoạt động trong ngữ cảnh JSON object.

Ví dụ:

~~~java
public class CustomerResponse {

    private String id;

    @JsonUnwrapped
    private Address address;
}
~~~

Kết quả có thể là:

~~~json
{
  "id": "C-10",
  "city": "Hanoi",
  "district": "Ba Dinh"
}
~~~

@JsonValue lại thay biểu diễn của instance được đánh dấu bằng giá trị accessor trả về. Nó không phải công cụ để đưa các property của object con lên object cha.

Chọn annotation theo hình dạng hợp đồng mong muốn:

- Muốn một scalar đại diện cho value object: @JsonValue.
- Muốn property có tên riêng: @JsonProperty.
- Muốn flatten một object lồng trong object cha: @JsonUnwrapped.
- Muốn logic ghi phức tạp hoặc phụ thuộc context: custom JsonSerializer.

## 10. @JsonValue trong object lồng nhau và collection

@JsonValue có hiệu lực mỗi khi Jackson serialize instance của kiểu đó, không chỉ khi instance là root object.

Ví dụ:

~~~java
public record OrderResponse(
    String id,
    ProductCode productCode,
    List<EmailAddress> recipients
) {}
~~~

Nếu ProductCode và EmailAddress đều dùng @JsonValue, JSON có thể là:

~~~json
{
  "id": "ORD-100",
  "productCode": "SKU-100",
  "recipients": [
    "minh@example.com",
    "an@example.com"
  ]
}
~~~

Không cần viết custom serializer riêng cho OrderResponse chỉ để các value object xuất thành scalar. Jackson áp dụng annotation trên từng kiểu khi serialize thuộc tính hoặc phần tử collection.

Điều này giúp domain model giữ được kiểu mạnh trong Java mà hợp đồng JSON vẫn gọn.

## 11. @JsonValue với số và kiểu số chính xác

Accessor có thể trả về number thay vì String:

~~~java
public final class Percentage {

    private final BigDecimal value;

    public Percentage(BigDecimal value) {
        this.value = Objects.requireNonNull(value);
    }

    @JsonValue
    public BigDecimal value() {
        return value;
    }
}
~~~

Ví dụ serialize:

~~~java
Percentage discount = new Percentage(new BigDecimal("12.50"));
String json = mapper.writeValueAsString(discount);
~~~

JSON:

~~~json
12.50
~~~

BigDecimal phù hợp khi cần biểu diễn số thập phân chính xác, chẳng hạn tiền hoặc tỷ lệ có quy tắc scale. Không chuyển sang double chỉ để tiện serialize vì có thể xuất hiện sai số nhị phân.

Nếu hợp đồng muốn số phần trăm dưới dạng string như "12.50%", accessor có thể trả String. Nhưng khi đó consumer không còn nhận JSON number và phải tự parse. Hãy chọn một dạng có ý nghĩa rõ ràng.

## 12. @JsonValue với boolean hoặc cấu trúc khác

Một kiểu đơn giản có thể biểu diễn bằng boolean:

~~~java
public final class FeatureFlag {

    private final boolean enabled;

    public FeatureFlag(boolean enabled) {
        this.enabled = enabled;
    }

    @JsonValue
    public boolean enabled() {
        return enabled;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static FeatureFlag fromJson(boolean enabled) {
        return new FeatureFlag(enabled);
    }
}
~~~

JSON:

~~~json
true
~~~

Nếu accessor trả List hoặc Map, toàn bộ object được biểu diễn theo cấu trúc đó:

~~~java
public final class CoordinatePair {

    private final double latitude;
    private final double longitude;

    public CoordinatePair(double latitude, double longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }

    @JsonValue
    public Map<String, Double> asJson() {
        return Map.of(
            "latitude", latitude,
            "longitude", longitude
        );
    }
}
~~~

JSON:

~~~json
{
  "latitude": 10.7,
  "longitude": 106.6
}
~~~

Ví dụ này tạo object JSON thông qua Map. Tuy nhiên, nếu cấu trúc object chính là hợp đồng mong muốn, một DTO thông thường với hai property có thể rõ ràng và dễ deserialize hơn. @JsonValue có ích khi muốn kiểm soát biểu diễn tập trung hoặc trả về một cấu trúc dẫn xuất; không nên dùng nó chỉ để tránh khai báo getter.

## 13. Các giới hạn và điều cần tránh

### 13.1. Không đánh dấu nhiều accessor làm giá trị đại diện

Một kiểu chỉ nên có một accessor @JsonValue có ý nghĩa. Nếu đánh dấu nhiều method/field, Jackson có thể báo lỗi cấu hình hoặc không thể xác định biểu diễn duy nhất.

Hãy gom logic về một method:

~~~java
@JsonValue
public String toJsonValue() {
    return code;
}
~~~

### 13.2. Không trả về chính instance

Tránh:

~~~java
@JsonValue
public ProductCode value() {
    return this;
}
~~~

Jackson lại serialize ProductCode, gọi @JsonValue lần nữa và có thể tạo đệ quy. Accessor phải trả về một giá trị biểu diễn khác, chẳng hạn String hoặc number.

### 13.3. Không để accessor có side effect

Accessor không nên:

- Thay đổi field của object.
- Gọi database hoặc network.
- Đọc trạng thái request hiện tại.
- Sinh giá trị ngẫu nhiên hoặc phụ thuộc thời gian.
- Trả dữ liệu khác nhau giữa các lần serialize nếu hợp đồng yêu cầu ổn định.

Serialization nên là thao tác biểu diễn dữ liệu đã có. Nếu biểu diễn phụ thuộc context, custom serializer với provider/context có thể phù hợp hơn.

### 13.4. Không làm mất thông tin cần thiết

Nếu một object có nhiều field nhưng @JsonValue chỉ trả một field, các thông tin còn lại không xuất hiện trong JSON theo biểu diễn đó.

Ví dụ một Money object có amount, currency và scale. Nếu @JsonValue chỉ trả amount, consumer không biết currency. Chỉ làm vậy khi currency đã được quy định bên ngoài hoặc không thuộc hợp đồng. Nếu không, hãy trả cấu trúc có đủ thông tin hoặc dùng DTO.

### 13.5. Cẩn thận với null

Nếu accessor trả null, giá trị đại diện được serialize thành JSON null theo hành vi serializer tương ứng. Điều đó không giống việc instance Java ban đầu là null: instance có thể tồn tại nhưng accessor trả null.

Với value object, thường nên bảo đảm giá trị nội bộ không null ngay trong constructor/factory. Nếu null là trạng thái hợp lệ, hãy quy định rõ output và test riêng.

### 13.6. Cẩn thận với đổi hình dạng hợp đồng

Chuyển từ:

~~~json
{
  "value": "SKU-100"
}
~~~

sang:

~~~json
"SKU-100"
~~~

là thay đổi schema JSON. Client đang truy cập property value sẽ không còn hoạt động. Đây là thay đổi có thể phá vỡ tương thích dù code Java chỉ thêm một annotation.

Hãy xem @JsonValue như một thay đổi hợp đồng API và áp dụng quy trình versioning/migration phù hợp.

## 14. Khi nào custom serializer phù hợp hơn?

@JsonValue phù hợp khi biểu diễn chỉ phụ thuộc một accessor. Nếu cần nhiều quy tắc, custom serializer có thể rõ ràng hơn.

Ví dụ serializer có thể:

- Ghi object theo cấu trúc khác nhau tùy context.
- Ghi thêm metadata hoặc discriminator.
- Chuẩn hóa giá trị theo cấu hình.
- Kiểm soát thứ tự token.
- Tương tác với SerializerProvider.
- Xử lý kiểu có nhiều biến thể biểu diễn.

@JsonValue phù hợp với trường hợp đơn giản:

~~~java
@JsonValue
public String code() {
    return code;
}
~~~

Custom serializer phù hợp khi logic ghi trở thành một quy trình riêng. Đừng viết custom serializer chỉ để trả về một field string nếu @JsonValue đã thể hiện đúng hợp đồng.

## 15. Kiểm thử hợp đồng serialize và deserialize

Một test tốt cần kiểm tra JSON chính xác, không chỉ kiểm tra rằng mapper không ném lỗi.

Ví dụ value object:

~~~java
public final class ProductCode {

    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public ProductCode(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Code is required");
        }
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

Test serialization:

~~~java
@Test
void serializesProductCodeAsJsonString() throws Exception {
    ProductCode code = new ProductCode("SKU-100");

    String json = mapper.writeValueAsString(code);

    assertEquals("\"SKU-100\"", json);
}
~~~

Test deserialization:

~~~java
@Test
void deserializesJsonStringIntoProductCode() throws Exception {
    ProductCode code = mapper.readValue(
        "\"SKU-100\"",
        ProductCode.class
    );

    assertEquals("SKU-100", code.value());
}
~~~

Test round-trip:

~~~java
@Test
void roundTripsProductCode() throws Exception {
    ProductCode original = new ProductCode("SKU-100");

    String json = mapper.writeValueAsString(original);
    ProductCode restored = mapper.readValue(json, ProductCode.class);

    assertEquals(original.value(), restored.value());
}
~~~

Với enum có mã riêng, test cả hai chiều:

~~~java
@Test
void serializesAndDeserializesPaymentStatusByCode() throws Exception {
    String json = mapper.writeValueAsString(PaymentStatus.PAID);

    assertEquals("\"S\"", json);
    assertEquals(
        PaymentStatus.PAID,
        mapper.readValue(json, PaymentStatus.class)
    );
}
~~~

### 15.1. Những trường hợp nên kiểm thử thêm

- Giá trị rỗng hoặc null bị từ chối theo invariant.
- Giá trị có whitespace hoặc casing khác.
- Mã enum không biết.
- Hai enum constant có mã trùng.
- Accessor trả BigDecimal hoặc boolean.
- Value object nằm trong DTO và List.
- JSON object được gửi vào creator DELEGATING vốn mong đợi string.
- JSON string được gửi vào creator PROPERTIES vốn mong đợi object.
- Hợp đồng cũ và mới nếu thay đổi từ object sang scalar.

Không chỉ test round-trip. Nếu cả serializer và deserializer cùng thay đổi theo một cách không mong muốn, round-trip vẫn có thể qua. Hãy assert JSON literal mà API thực sự phát hành.

## 16. Tổ chức value object trong domain model

Một value object có thể dùng kiểu Java mạnh để ngăn truyền nhầm dữ liệu:

~~~java
public record OrderResponse(
    String orderId,
    ProductCode productCode,
    CurrencyCode currency,
    EmailAddress contactEmail
) {}
~~~

Trong Java, các field có kiểu riêng và có thể kiểm tra invariant tại constructor. Trong JSON, chúng có thể được biểu diễn bằng scalar:

~~~json
{
  "orderId": "ORD-100",
  "productCode": "SKU-100",
  "currency": "VND",
  "contactEmail": "minh@example.com"
}
~~~

Điều này giữ được lợi ích type safety trong domain mà không bắt consumer phải hiểu cấu trúc wrapper nội bộ.

Tuy nhiên, nếu API cần mô tả thêm metadata của value object, ví dụ currency code và display name, hãy cân nhắc trả object:

~~~json
{
  "currency": {
    "code": "VND",
    "displayName": "Vietnamese dong"
  }
}
~~~

Một kiểu Java có thể có nhiều representation ở các API khác nhau, nhưng cần cấu hình serializer/DTO rõ ràng cho từng hợp đồng. Không nên để một @JsonValue toàn cục vô tình thay đổi mọi API đang dùng kiểu đó.

## 17. Quy trình quyết định dùng @JsonValue

1. Xác định kiểu Java có thực sự đại diện cho một giá trị duy nhất không.
2. Xác định JSON contract mong muốn là string, number, boolean, array hay object.
3. Chọn một method/field duy nhất làm accessor.
4. Bảo đảm accessor không có side effect và trả kiểu Jackson serialize được.
5. Nếu class thông thường cần deserialize ngược, thêm constructor/factory @JsonCreator(mode = DELEGATING).
6. Nếu là enum, kiểm tra mã @JsonValue có duy nhất và ổn định.
7. Kiểm tra null, empty, invalid value và coercion.
8. Test JSON literal cho cả root object lẫn object lồng nhau.
9. Đánh giá ảnh hưởng đến client trước khi đổi từ JSON object sang scalar.
10. Dùng custom serializer hoặc DTO riêng nếu biểu diễn phụ thuộc context hoặc cần nhiều field.

## 18. Nguyên tắc nên giữ

- Dùng @JsonValue khi một instance có một biểu diễn JSON duy nhất, tự nhiên.
- Phân biệt @JsonValue với @JsonProperty: một annotation thay representation, annotation kia đặt tên property.
- Dùng @JsonCreator DELEGATING cho class thông thường nếu cần đọc lại JSON scalar.
- Với enum, mã @JsonValue cần duy nhất và ổn định.
- Accessor nên thuần, không thay đổi trạng thái và không gọi dịch vụ ngoài.
- Không trả về chính instance từ accessor.
- Không làm mất field cần thiết của hợp đồng chỉ để JSON ngắn hơn.
- Kiểm tra hành vi khi accessor trả null.
- Xem việc đổi object thành scalar là thay đổi schema có thể ảnh hưởng client.
- Dùng custom serializer khi cần logic ghi phức tạp hơn một accessor.
- Test JSON literal, deserialize, round-trip và trường hợp lỗi.

@JsonValue là cách gọn để biến value object Java thành một JSON value trực tiếp. Nó giúp domain model giữ kiểu mạnh như EmailAddress, ProductCode hay CurrencyCode trong khi API chỉ trao đổi chuỗi hoặc số tương ứng. Khi cần đọc ngược, hãy thiết kế creator phù hợp; khi dùng enum, giữ mã ổn định; và luôn xem hình dạng JSON được tạo ra là một phần hợp đồng mà client phụ thuộc.

