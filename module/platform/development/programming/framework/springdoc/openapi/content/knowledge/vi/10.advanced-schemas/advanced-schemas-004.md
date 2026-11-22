# Record, lớp bất biến và dữ liệu được suy ra từ accessor

Trong Java hiện đại, DTO dùng cho API có thể được biểu diễn bằng record hoặc lớp bất biến với các trường `final`. Những kiểu dữ liệu này giúp giới hạn việc thay đổi trạng thái sau khi khởi tạo, làm rõ dữ liệu đầu vào và đầu ra, đồng thời giảm mã getter/setter. Tuy nhiên, khi springdoc-openapi tạo schema, kết quả còn phụ thuộc cách Jackson nhận diện property từ record component, constructor, getter và accessor được định nghĩa thêm.

Một lớp có thể chứa dữ liệu lưu trữ cùng các giá trị được tính toán từ dữ liệu đó. Ví dụ, `ProductView` có `name` và `price`, đồng thời cung cấp `displayName` hoặc `formattedPrice` qua getter. Nếu Jackson xem getter đó là một property được serialize, springdoc có thể đưa property tương ứng vào schema OpenAPI. Khi tài liệu và JSON thực tế không thống nhất, client có thể hiểu sai response hoặc gửi nhầm trường chỉ dành cho máy chủ.

Bài học này giải thích cách record và lớp bất biến được nhận diện, cách đặt tên và kiểm soát property bằng Jackson, cách mô tả trường dẫn xuất bằng OpenAPI, và cách kiểm chứng schema sinh ra cùng JSON runtime.

## Mục tiêu

Sau bài học, bạn có thể:

- Hiểu cách Jackson và springdoc-openapi nhận diện property từ record component, field, constructor và accessor.
- Dùng record cho request/response DTO và lớp bất biến cho các trường hợp cần constructor tường minh.
- Phân biệt accessor của record, JavaBean getter và phương thức tiện ích thông thường.
- Kiểm soát tên, chiều đọc/ghi và việc loại bỏ property bằng annotation Jackson.
- Mô tả trường do máy chủ tính toán bằng `@Schema`, `readOnly` hoặc `writeOnly`.
- Tránh để accessor ngoài ý muốn làm lộ dữ liệu hoặc làm schema sai lệch.
- Kiểm tra schema OpenAPI và payload JSON được serialize/deserialized trong Spring Boot.

## 1. Từ kiểu Java đến schema OpenAPI

springdoc-openapi phân tích controller, kiểu tham số, kiểu trả về và metadata của các thư viện liên quan để tạo đặc tả OpenAPI. Với DTO, kết quả thường chịu ảnh hưởng của hai lớp:

1. **Jackson** quyết định thuộc tính nào được xem là property khi đọc hoặc ghi JSON, tên JSON là gì và property có thể đọc/ghi theo chiều nào.
2. **Swagger Core và springdoc-openapi** xây dựng schema OpenAPI từ kiểu Java cùng metadata annotation, trong đó có annotation Swagger/OpenAPI và các thông tin Jackson mà bộ phân tích hỗ trợ.

Do đó, schema không đơn giản là danh sách field khai báo trong lớp. Một getter công khai có thể trở thành property JSON dù lớp không có field tương ứng. Ngược lại, một field nội bộ có thể không xuất hiện nếu Jackson bỏ qua nó. Annotation có thể đổi tên, ẩn hoặc đánh dấu property chỉ đọc/ghi.

Ví dụ response có thể có các property:

| Nguồn trong Java | Tên JSON có thể xuất hiện | Ý nghĩa |
|---|---|---|
| Record component `name` | `name` | Dữ liệu thành phần của record |
| Getter `getDisplayName()` | `displayName` | Property theo quy ước JavaBean |
| Getter boolean `isAvailable()` | `available` | Property boolean theo JavaBean |
| Method `normalizedName()` | Thường không tự xuất hiện | Phương thức tiện ích, không phải getter JavaBean |
| Method có `@JsonProperty("label")` | `label` | Property được Jackson công bố tường minh |

Đây là quy tắc nhận diện phổ biến; cấu hình ObjectMapper, visibility, mix-in và annotation tùy chỉnh có thể làm thay đổi kết quả. Hãy coi JSON được serialize và OpenAPI JSON thực tế là bằng chứng cuối cùng của dự án.

## 2. Record và record component

Record là kiểu dữ liệu được thiết kế để giữ một tập giá trị cố định. Các thành phần khai báo trong header record tạo ra:

- Thành phần dữ liệu có tên và kiểu rõ ràng.
- Trường lưu trữ tương ứng, thường là `private final`.
- Accessor cùng tên component, ví dụ `name()` thay vì `getName()`.
- Constructor canonical nhận các component theo thứ tự khai báo.
- Các phương thức `equals`, `hashCode` và `toString` được sinh tự động.

Ví dụ:

~~~java
public record ProductResponse(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Một instance được tạo một lần với các giá trị đã cho:

~~~java
ProductResponse product =
    new ProductResponse(42L, "Bàn phím cơ", new BigDecimal("1250000"));

Long id = product.id();
String name = product.name();
~~~

Record không tạo setter cho component. Điều này phù hợp với response DTO vì dữ liệu thường được tạo ở service rồi serialize để trả về client. Record cũng có thể dùng làm request DTO khi framework và phiên bản Jackson hỗ trợ constructor binding cho record.

Record cung cấp tính bất biến nông (shallow immutability). Component không thể được gán lại sau khi khởi tạo, nhưng object mà component tham chiếu vẫn có thể mutable. Ví dụ, một record chứa `List` vẫn có thể bị thay đổi nếu giữ nguyên danh sách mutable bên ngoài. Có thể sao chép phòng vệ trong compact constructor:

~~~java
public record TeamView(List<String> members) {
    public TeamView {
        members = List.copyOf(members);
    }
}
~~~

Schema OpenAPI vẫn mô tả `members` là array; việc sao chép phòng vệ bảo đảm giá trị bên trong record không bị thay đổi thông qua tham chiếu collection bên ngoài.

### Record được Jackson nhận diện như thế nào?

Record là tính năng Java được hoàn thiện từ Java 16. Jackson hỗ trợ record từ dòng 2.12. Với phiên bản phù hợp, record component được nhận diện như property JSON dù accessor có dạng `name()` chứ không phải `getName()`. Khi Spring MVC nhận JSON vào record, Jackson có thể gọi canonical constructor để tạo instance.

Các phiên bản Spring Boot quản lý phiên bản Jackson theo dependency management. Trước khi dùng record trong API, hãy xác nhận phiên bản Java, Spring Boot và Jackson mà dự án thực sự chạy. Không nâng riêng Jackson một cách tùy tiện nếu Spring Boot đã quản lý bộ phiên bản tương thích.

Trong response, springdoc thường sinh schema dựa trên các component:

~~~yaml
ProductResponse:
  type: object
  properties:
    id:
      type: integer
      format: int64
    name:
      type: string
    price:
      type: number
    # Các property khác tùy annotation và cấu hình.
~~~

Schema minh họa được rút gọn. Để biết `required`, format, nullable và ví dụ thực tế, cần xem tài liệu `/v3/api-docs` do ứng dụng tạo.

## 3. Dùng record cho request và response riêng

Tách request DTO và response DTO giúp kiểm soát trường nào client được gửi và trường nào máy chủ tạo:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

@Schema(name = "CreateProductRequest")
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(description = "Tên sản phẩm", example = "Bàn phím cơ")
    String name,

    @Positive
    @Schema(description = "Giá bán", example = "1250000")
    BigDecimal price
) {}

@Schema(name = "ProductResponse")
public record ProductResponse(
    @Schema(description = "Mã sản phẩm do máy chủ cấp", example = "42")
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @PostMapping
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {

        ProductResponse created = productService.create(request);
        URI location = URI.create("/api/products/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}
~~~

Trong ví dụ, client chỉ gửi `name` và `price`. Server cấp `id` và trả về `ProductResponse`. Việc dùng hai record riêng làm hợp đồng rõ ràng, không phụ thuộc vào việc ẩn một trường trên cùng DTO để cố dùng chung cho hai chiều.

Bean Validation annotation trên record component được các framework hiện đại hỗ trợ thông qua cơ chế annotation propagation và validation. Để validation chạy trong controller, vẫn cần `@Valid` và dependency Bean Validation tương ứng. springdoc có thể dùng metadata constraint để mô tả `required`, giới hạn hoặc format, nhưng hãy kiểm tra schema được sinh ra thay vì giả định mọi ràng buộc nghiệp vụ đều tự động xuất hiện.

## 4. Accessor của record khác JavaBean getter

Record tạo accessor theo đúng tên component:

~~~java
public record CustomerView(String fullName, boolean active) {
    // Accessor được sinh: fullName() và active()
}
~~~

Đây không phải JavaBean getter `getFullName()` hoặc `isActive()`. Jackson nhận diện record component nhờ hỗ trợ record, vì vậy property `fullName` và `active` vẫn có thể được serialize.

Với lớp Java thông thường, quy ước JavaBean thường dùng:

~~~java
public final class CustomerView {
    private final String fullName;
    private final boolean active;

    public CustomerView(String fullName, boolean active) {
        this.fullName = fullName;
        this.active = active;
    }

    public String getFullName() {
        return fullName;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Jackson thường nhận `getFullName()` thành property `fullName` và `isActive()` thành property `active`, tùy cấu hình visibility và quy tắc đặt tên. Khi chuyển từ lớp getter/setter sang record, tên accessor Java thay đổi nhưng tên property JSON có thể vẫn giữ nguyên.

### Phương thức tiện ích không tự động là property

Trong record:

~~~java
public record CustomerView(String fullName) {

    public String normalizedName() {
        return fullName.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

`normalizedName()` là method tiện ích, không theo quy ước getter JavaBean. Thông thường, Jackson không tự coi nó là property JSON. Nếu muốn công bố giá trị này trong response, hãy đánh dấu tường minh bằng `@JsonProperty` hoặc tạo getter theo quy ước:

~~~java
public record CustomerView(String fullName) {

    @JsonProperty("normalizedName")
    public String normalizedName() {
        return fullName.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Khi dùng `@JsonProperty`, method trở thành property được Jackson xem xét cho JSON. Hãy kiểm tra cả schema OpenAPI và JSON response để xác nhận property có xuất hiện đúng tên.

## 5. Lớp bất biến với constructor tường minh

Không phải DTO nào cũng cần record. Một lớp bất biến phù hợp khi cần tương thích với cấu trúc lớp hiện có, có logic khởi tạo phức tạp hoặc cần kiểm soát constructor:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "Money")
public final class Money {

    private final String currency;
    private final BigDecimal amount;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Money(
            @JsonProperty("currency") String currency,
            @JsonProperty("amount") BigDecimal amount) {
        this.currency = Objects.requireNonNull(currency);
        this.amount = Objects.requireNonNull(amount);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
    }

    @JsonProperty("currency")
    public String getCurrency() {
        return currency;
    }

    @JsonProperty("amount")
    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

`@JsonCreator` chỉ ra constructor Jackson dùng để tạo object khi đọc JSON. `@JsonProperty` trên tham số gắn tên JSON với tham số constructor; trên getter, annotation xác định tên property khi serialize. Các trường `final` không có setter nên không thể thay đổi qua setter sau khi object được tạo.

Với lớp bất biến, cần bảo đảm:

- Jackson biết constructor hoặc factory method nào dùng để deserialize.
- Mỗi tham số constructor được ánh xạ đúng tên property JSON.
- Getter hoặc annotation xác định các property cần serialize.
- Quy tắc kiểm tra trong constructor không tạo ra khác biệt bất ngờ so với validation của request DTO.

Tên tham số constructor có thể được suy luận trong một số cấu hình nếu bytecode có metadata phù hợp, nhưng khai báo `@JsonProperty` tường minh thường giúp hợp đồng ổn định hơn. Với record được Jackson hỗ trợ, canonical constructor thường được nhận diện tự động nên không cần lặp lại mẫu constructor này.

### Khi nào chọn record, khi nào chọn lớp bất biến?

| Tiêu chí | Record | Lớp bất biến |
|---|---|---|
| Mục đích | DTO/value carrier gọn, dữ liệu cố định | Mô hình cần kiểm soát khởi tạo hoặc cấu trúc phức tạp |
| Accessor | Tên component như `amount()` | Thường dùng getter JavaBean như `getAmount()` |
| Constructor | Canonical constructor được sinh | Tự khai báo constructor/factory |
| Jackson | Hỗ trợ record ở phiên bản phù hợp | Thường cần getter và creator/constructor rõ ràng |
| Kế thừa | Record là final, không thể extends lớp khác | Có thể tổ chức kế thừa nếu thiết kế cho phép |
| Logic bổ sung | Có thể thêm method và constructor phụ | Có thể thêm method, factory và nhiều constructor |

Đối với DTO request/response đơn giản, record thường giúp schema và dữ liệu dễ đọc. Với mô hình cần tương thích API cũ hoặc khởi tạo theo quy tắc riêng, lớp bất biến có thể phù hợp hơn.

## 6. Property được tính toán từ accessor

Một response có thể chứa dữ liệu gốc cùng giá trị suy ra. Ví dụ:

~~~java
public final class ProductView {
    private final Long id;
    private final String name;
    private final BigDecimal price;

    public ProductView(Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public String getDisplayName() {
        return name + " (#" + id + ")";
    }

    public boolean isPremium() {
        return price.compareTo(new BigDecimal("1000000")) >= 0;
    }
}
~~~

Với cấu hình Jackson thông thường, các getter JavaBean như `getDisplayName()` và `isPremium()` có thể trở thành property JSON. JSON có thể chứa cả ba trường lưu trữ và hai trường được tính toán:

~~~json
{
  "id": 42,
  "name": "Bàn phím cơ",
  "price": 1250000,
  "displayName": "Bàn phím cơ (#42)",
  "premium": true
}
~~~

Các giá trị dẫn xuất không có field lưu trữ riêng nhưng vẫn là một phần của biểu diễn JSON nếu Jackson serialize getter tương ứng. springdoc có thể đưa chúng vào schema response khi bộ phân tích nhận diện chúng là property.

### Vì sao accessor có thể làm schema thay đổi?

Giả sử trước đây response chỉ có `id`, `name` và `price`. Khi thêm getter công khai `getDisplayName()`, Jackson có thể bổ sung property `displayName` vào JSON. Đặc tả OpenAPI được sinh cũng có thể thay đổi, dù bạn không thêm field mới vào lớp.

Điều này thường hữu ích khi giá trị dẫn xuất là một phần hợp đồng, chẳng hạn:

- `totalAmount` được tính từ đơn giá và số lượng.
- `displayName` ghép tên và mã tài nguyên.
- `available` phản ánh khả năng đặt hàng.
- `canEdit` biểu diễn quyền thao tác của người dùng hiện tại.

Tuy nhiên, một getter tiện ích có thể vô tình trở thành property công khai. Trước khi thêm method bắt đầu bằng `get` hoặc `is` vào DTO, hãy quyết định nó có nên xuất hiện trong JSON và OpenAPI hay không.

### Method không phải getter JavaBean

Method `calculateTotal()` hoặc `normalizedName()` thường không được Jackson tự nhận diện như property chỉ vì nó public. Nếu muốn đưa kết quả vào JSON, có thể đánh dấu `@JsonProperty`:

~~~java
@JsonProperty("normalizedName")
public String normalizedName() {
    return name.trim().toLowerCase(Locale.ROOT);
}
~~~

Nếu không muốn công bố, giữ method ở tên thông thường và không đánh dấu nó thành property. Khi dự án tùy chỉnh visibility hoặc dùng mix-in, quy tắc có thể khác nên cần kiểm tra bằng ObjectMapper đang được Spring Boot cấu hình.

## 7. Đặt tên và kiểm soát property bằng Jackson

Jackson cung cấp annotation để xác định property nào xuất hiện và tên của nó. Các annotation thường gặp:

| Annotation | Tác động |
|---|---|
| `@JsonProperty("publicName")` | Đặt tên property JSON tường minh |
| `@JsonIgnore` | Bỏ qua property khi serialize/deserialze theo cấu hình Jackson |
| `@JsonProperty(access = READ_ONLY)` | Property được xuất ra nhưng không nhận giá trị từ input JSON |
| `@JsonProperty(access = WRITE_ONLY)` | Property nhận từ input JSON nhưng không xuất ra response |
| `@JsonGetter("name")` | Chỉ định method dùng để serialize property với tên cụ thể |
| `@JsonInclude` | Điều khiển khi nào property được đưa vào output, ví dụ bỏ qua null |
| `@JsonAlias` | Cho phép thêm tên thay thế khi deserialize |

Ví dụ đổi tên property:

~~~java
public record AccountView(
    @JsonProperty("account_id")
    Long id,
    @JsonProperty("display_name")
    String displayName
) {}
~~~

JSON sử dụng `account_id` và `display_name`. springdoc thường phản ánh tên property sau khi Jackson xử lý, nhưng hãy xác nhận trong `/v3/api-docs` vì cấu hình naming strategy hoặc phiên bản thư viện có thể ảnh hưởng kết quả.

### Ẩn property nội bộ

~~~java
public final class AccountView {
    private final String username;
    private final String internalRiskScore;

    public AccountView(String username, String internalRiskScore) {
        this.username = username;
        this.internalRiskScore = internalRiskScore;
    }

    public String getUsername() {
        return username;
    }

    @JsonIgnore
    public String getInternalRiskScore() {
        return internalRiskScore;
    }
}
~~~

`@JsonIgnore` yêu cầu Jackson bỏ qua property. springdoc thường tôn trọng metadata Jackson và không đưa property bị bỏ qua vào schema. Dù vậy, nếu có mix-in, custom serializer hoặc cấu hình riêng cho tài liệu, hãy kiểm tra cả hai đầu ra.

Không dùng `@Schema(hidden = true)` như cách duy nhất để che dữ liệu nhạy cảm. Annotation này điều khiển tài liệu OpenAPI; nó không bảo đảm Jackson ngừng serialize property.

## 8. Mô tả chiều đọc và ghi bằng readOnly, writeOnly

Một property có thể chỉ được máy chủ trả về hoặc chỉ được client gửi lên. OpenAPI biểu diễn hai trường hợp này bằng:

- `readOnly: true`: property thuộc response; client không nên gửi nó trong request.
- `writeOnly: true`: property thuộc request; server không trả nó trong response.

Với springdoc, có thể dùng `@Schema(accessMode = Schema.AccessMode.READ_ONLY)` hoặc `WRITE_ONLY`:

~~~java
public record ProductView(
    @Schema(accessMode = Schema.AccessMode.READ_ONLY,
            description = "Mã do máy chủ cấp")
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Đây là metadata tài liệu. Nếu cần Jackson thực thi cùng chiều đọc/ghi trong JSON, dùng thêm `@JsonProperty(access = JsonProperty.Access.READ_ONLY)`:

~~~java
public record ProductView(
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    @Schema(accessMode = Schema.AccessMode.READ_ONLY,
            description = "Mã do máy chủ cấp")
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Đối với trường chỉ gửi lên, ví dụ mật khẩu khi đăng ký:

~~~java
public record RegisterRequest(
    @NotBlank String username,
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY,
            description = "Mật khẩu chỉ dùng khi tạo tài khoản")
    @NotBlank String password
) {}
~~~

`@JsonProperty(access = ...)` điều khiển cách Jackson đọc/ghi property; `@Schema(accessMode = ...)` mô tả chiều sử dụng trong OpenAPI. Dùng cả hai khi muốn runtime JSON và hợp đồng cùng thể hiện một quy tắc. Nếu chỉ thêm `@Schema`, đừng cho rằng Jackson tự ngừng nhận hoặc trả property đó.

### Không thay thế DTO request/response bằng accessMode trong mọi trường hợp

Một schema dùng chung với readOnly/writeOnly có thể phù hợp khi hai chiều dữ liệu gần như giống nhau. Tuy nhiên, nếu request và response khác nhiều trường, khác validation hoặc có vòng đời riêng, hãy tách thành DTO riêng. Điều đó giúp tránh client gửi nhầm trường do server quản lý và tránh vô tình trả dữ liệu nhạy cảm.

## 9. Gắn metadata OpenAPI cho property dẫn xuất

Khi getter dẫn xuất là một phần hợp đồng, mô tả ý nghĩa, ví dụ và chiều dữ liệu ngay trên accessor:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "ProductView", description = "Thông tin sản phẩm hiển thị cho client")
public record ProductView(
    Long id,
    String name,
    BigDecimal price
) {

    @JsonProperty(value = "displayName", access = JsonProperty.Access.READ_ONLY)
    @Schema(
        description = "Tên hiển thị ghép từ tên và mã sản phẩm",
        example = "Bàn phím cơ (#42)",
        accessMode = Schema.AccessMode.READ_ONLY
    )
    public String getDisplayName() {
        return name + " (#" + id + ")";
    }

    @JsonIgnore
    public String getInternalSearchKey() {
        return name.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Trong ví dụ:

- `displayName` được Jackson serialize và được mô tả là property chỉ đọc.
- `internalSearchKey` bị Jackson bỏ qua nên không phải dữ liệu response công khai.
- Các record component vẫn là dữ liệu cơ bản của ProductView.

Getter dẫn xuất nên tính toán từ dữ liệu đã có trong DTO, có kết quả ổn định và chi phí thấp. Tránh gọi cơ sở dữ liệu, dịch vụ mạng hoặc đọc trạng thái thay đổi liên tục từ getter; quá trình serialize có thể gọi getter nhiều lần và làm response chậm hoặc không nhất quán. Nếu giá trị phụ thuộc người dùng hiện tại hoặc quyền truy cập, hãy tính nó ở service rồi đưa vào DTO response với ngữ nghĩa được mô tả rõ.

Schema OpenAPI dự kiến có `displayName` với `readOnly: true` và không có `internalSearchKey`. JSON runtime cũng nên có `displayName` nhưng không có `internalSearchKey`. Cần xác minh cả hai vì một cấu hình Jackson tùy chỉnh có thể làm khác hành vi mặc định.

### Khi nào nên dùng @Schema(hidden = true)?

`@Schema(hidden = true)` hữu ích khi property không nên xuất hiện trong tài liệu vì lý do trình bày hoặc vì schema dùng cho một ngữ cảnh đặc biệt. Nhưng nó không thay thế `@JsonIgnore` nếu property không được phép xuất hiện trong JSON. Trước khi ẩn property khỏi hợp đồng, hãy cân nhắc liệu client có cần biết trường đó tồn tại để parse response hay gửi request hay không.

## 10. Các annotation Jackson có thể ảnh hưởng schema

Một số annotation thay đổi JSON theo cách có thể làm schema OpenAPI thay đổi:

| Annotation | Ảnh hưởng tới JSON | Điều cần kiểm tra trong OpenAPI |
|---|---|---|
| `@JsonProperty` | Đổi tên hoặc công bố property | Tên property trong `properties` |
| `@JsonIgnore` | Bỏ property | Property có bị loại khỏi schema không |
| `@JsonProperty(access = READ_ONLY)` | Chỉ serialize | `readOnly: true` |
| `@JsonProperty(access = WRITE_ONLY)` | Chỉ deserialize | `writeOnly: true` |
| `@JsonInclude(NON_NULL)` | Bỏ property null khỏi JSON | `required`, nullable và ví dụ có còn đúng không |
| `@JsonAlias` | Nhận tên thay thế khi đọc JSON | Schema có mô tả đúng tên canonical mà client nên gửi không |
| `@JsonUnwrapped` | Làm phẳng property object vào object cha | Schema có phản ánh cấu trúc phẳng không |
| `@JsonValue` | Serialize object qua một giá trị đại diện | Schema có phải scalar thay vì object không |

Không phải mọi chi tiết serialization đều được suy ra giống nhau bởi tất cả phiên bản springdoc/swagger-core. Ví dụ, custom serializer có thể biến một lớp thành chuỗi trong JSON nhưng schema vẫn được suy luận từ field. Với trường hợp đó, cần khai báo schema tường minh bằng `@Schema(type = ...)`, `implementation = ...` hoặc customizer phù hợp và kiểm tra output thực tế.

### @JsonInclude không có nghĩa là property không tồn tại

`@JsonInclude(Include.NON_NULL)` thường bỏ property khỏi JSON khi giá trị là null. Điều này không nhất thiết có nghĩa property không thuộc schema hoặc không thể xuất hiện. Schema có thể vẫn khai báo property nhưng không bắt buộc; client cần hiểu rằng giá trị có thể vắng mặt.

### @JsonAlias không đổi tên canonical khi serialize

`@JsonAlias("old_name")` cho phép Jackson nhận thêm tên cũ khi deserialize. Khi serialize, tên canonical vẫn theo property name được cấu hình. Hợp đồng OpenAPI nên hướng client dùng tên chuẩn hiện tại; alias chủ yếu hỗ trợ tương thích ngược ở phía server.

### @JsonUnwrapped và cấu trúc phẳng

Nếu một object lồng nhau được đánh dấu `@JsonUnwrapped`, Jackson có thể đưa các property con lên object cha. Hãy kiểm tra schema do springdoc sinh vì cấu trúc Java lồng nhau và JSON thực tế không còn cùng hình dạng. Nếu công cụ không suy ra đúng, khai báo schema tương ứng hoặc thay DTO để cấu trúc trở nên rõ ràng.

## 11. Kiểm tra JSON runtime bằng ObjectMapper

Đừng chỉ nhìn schema để kết luận property có xuất hiện trong response. Hãy serialize object bằng chính ObjectMapper mà Spring Boot cấu hình:

~~~java
import java.math.BigDecimal;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest
class ProductViewJsonTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void serializesDerivedPropertyButOmitsInternalProperty() throws Exception {
        ProductView view = new ProductView(
            42L,
            "Bàn phím cơ",
            new BigDecimal("1250000")
        );

        JsonNode json = objectMapper.readTree(
            objectMapper.writeValueAsString(view)
        );

        assertEquals("Bàn phím cơ (#42)", json.path("displayName").asText());
        assertFalse(json.has("internalSearchKey"));
    }

    @Test
    void readOnlyDerivedPropertyIsNotAcceptedFromInput() throws Exception {
        String input = """
            {
              "id": 42,
              "name": "Bàn phím cơ",
              "price": 1250000,
              "displayName": "Giá trị giả do client gửi"
            }
            """;

        ProductView view = objectMapper.readValue(input, ProductView.class);

        assertEquals("Bàn phím cơ (#42)", view.getDisplayName());
    }
}
~~~

Ví dụ giả định ProductView được định nghĩa như phần trước và có constructor record mà Jackson hỗ trợ. Kiểm tra đầu tiên xác nhận getter dẫn xuất được serialize và property nội bộ không xuất hiện. Kiểm tra thứ hai xác nhận giá trị displayName do client gửi không ghi đè kết quả tính toán vì property được đánh dấu READ_ONLY.

Nếu dự án có ObjectMapper riêng, custom module, mix-in hoặc custom serializer, test phải inject đúng bean đang được MVC sử dụng. Tạo một ObjectMapper mới bằng constructor mặc định có thể cho kết quả khác cấu hình runtime của ứng dụng.

## 12. Kiểm tra schema do springdoc sinh

Giả sử controller trả về ProductView:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductViewController {

    @GetMapping("/{id}/view")
    public ProductView getView(@PathVariable Long id) {
        return productService.getView(id);
    }
}
~~~

Trong tài liệu OpenAPI, schema ProductView dự kiến có property dẫn xuất chỉ đọc và không có property nội bộ:

~~~yaml
components:
  schemas:
    ProductView:
      type: object
      properties:
        id:
          type: integer
          format: int64
        name:
          type: string
        price:
          type: number
        displayName:
          type: string
          description: Tên hiển thị ghép từ tên và mã sản phẩm
          readOnly: true
~~~

Đây là cấu trúc minh họa, không phải output cố định cho mọi phiên bản. Tên schema, kiểu số, danh sách required và cách xử lý nullable phụ thuộc DTO, Jackson và phiên bản OpenAPI mà ứng dụng sinh ra.

Có thể kiểm tra bằng MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductOpenApiSchemaTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsDerivedPropertyAsReadOnly() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.components.schemas.ProductView.properties.displayName.readOnly"
            ).value(true))
            .andExpect(jsonPath(
                "$.components.schemas.ProductView.properties.internalSearchKey"
            ).doesNotExist());
    }
}
~~~

Nếu ứng dụng chia GroupedOpenApi, gọi endpoint đặc tả của nhóm có ProductView. Nếu tên schema được thay đổi bằng `@Schema(name = ...)`, dùng đúng tên đó trong JSONPath. Test schema không thay thế test response JSON; nên có cả hai để phát hiện trường hợp tài liệu và runtime lệch nhau.

### Ma trận đối chiếu

| Câu hỏi | Kiểm tra ở đâu | Kết quả mong đợi trong ví dụ |
|---|---|---|
| Record component có được serialize? | JSON từ ObjectMapper | `id`, `name`, `price` xuất hiện |
| Getter dẫn xuất có được serialize? | JSON từ ObjectMapper | `displayName` xuất hiện |
| Getter nội bộ có bị loại? | JSON từ ObjectMapper | `internalSearchKey` vắng mặt |
| Property dẫn xuất có được mô tả? | `/v3/api-docs` | `displayName` có trong schema |
| Property có đúng chiều? | `/v3/api-docs` | `displayName.readOnly` là true |
| Tài liệu có lộ property nội bộ? | `/v3/api-docs` | `internalSearchKey` không có |
| Client có thể ghi đè property dẫn xuất? | Deserialize JSON | Giá trị tính toán vẫn do server/DTO quyết định |

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Record không deserialize được | Jackson quá cũ hoặc constructor binding không tương thích | Kiểm tra Jackson được Spring Boot quản lý và phiên bản Java |
| Property record bị thiếu trong JSON | Cấu hình Jackson hoặc annotation thay đổi visibility | Kiểm tra ObjectMapper và annotation trên component |
| Thêm getter làm response có trường mới | Jackson nhận getter JavaBean như property | Dùng `@JsonIgnore` nếu không công bố; nếu có công bố, cập nhật hợp đồng |
| Method tiện ích không xuất hiện | Method không phải getter và không có `@JsonProperty` | Đánh dấu property tường minh nếu đó là dữ liệu công khai |
| Schema có property nhưng JSON không có | `@Schema` chỉ mô tả tài liệu hoặc serializer bỏ property | Kiểm tra Jackson và đồng bộ metadata |
| JSON có property nhưng schema thiếu | springdoc không suy luận custom serializer/accessor | Khai báo `@Schema` hoặc customizer và kiểm tra lại |
| Trường nội bộ vẫn bị trả về | Chỉ dùng `@Schema(hidden = true)` | Kiểm soát bằng DTO, `@JsonIgnore` hoặc serializer |
| Client gửi được giá trị vào trường server quản lý | Chỉ đánh dấu `readOnly` trong tài liệu | Dùng `@JsonProperty(access = READ_ONLY)` hoặc DTO riêng |
| Schema có tên property không mong muốn | Naming strategy hoặc `@JsonProperty` đổi tên | Kiểm tra tên JSON canonical và OpenAPI `properties` |
| Trường null không có trong JSON | `@JsonInclude(NON_NULL)` hoặc cấu hình serialization | Mô tả đúng tính tùy chọn và khả năng vắng mặt |

## 14. Nguyên tắc thiết kế DTO bất biến cho API

Khi thiết kế record hoặc lớp bất biến, hãy áp dụng các nguyên tắc sau:

1. Tách request DTO và response DTO nếu các chiều dữ liệu có ý nghĩa hoặc quyền ghi khác nhau.
2. Giữ record component đúng với dữ liệu công khai mà client cần gửi hoặc nhận.
3. Chỉ thêm JavaBean getter dẫn xuất khi giá trị đó thực sự thuộc hợp đồng API.
4. Đánh dấu rõ chiều dữ liệu của property bằng Jackson và OpenAPI khi cần.
5. Dùng `@JsonIgnore` hoặc DTO riêng để ngăn dữ liệu nội bộ xuất hiện trong JSON.
6. Dùng `@JsonProperty` để ổn định tên JSON khi refactor tên field hoặc accessor.
7. Đừng giả định mọi custom serializer đều được springdoc suy luận chính xác.
8. Kiểm tra cả JSON runtime và OpenAPI JSON sau khi thay đổi DTO hoặc accessor.
9. Đánh giá ảnh hưởng tương thích khi thêm, xóa hoặc đổi tên property response.

Một getter mới có thể là thay đổi hợp đồng dù không thêm field lưu trữ. Nếu client generator tạo model từ OpenAPI, property mới có thể làm thay đổi mã client, snapshot hoặc quy tắc xử lý dữ liệu. Hãy review thay đổi schema cùng với thay đổi Java.

## 15. Bài thực hành tổng hợp

Xây dựng API xem thông tin sản phẩm với DTO bất biến:

1. Tạo `CreateProductRequest` và `ProductView` bằng record.
2. Tạo một lớp bất biến `Money` với constructor `@JsonCreator` và tham số `@JsonProperty`.
3. Thêm getter dẫn xuất `getDisplayName()` vào ProductView.
4. Dùng `@JsonProperty(access = READ_ONLY)` và `@Schema(accessMode = READ_ONLY)` cho displayName.
5. Thêm một accessor nội bộ và loại nó khỏi JSON bằng `@JsonIgnore`.
6. Thêm trường password vào request DTO thử nghiệm và đánh dấu WRITE_ONLY.
7. Khởi động ứng dụng, xem `/v3/api-docs` và kiểm tra schema ProductView.
8. Dùng ObjectMapper test để xác minh property nào được serialize/deserialized.
9. Dùng MockMvc test để đối chiếu JSON response với OpenAPI schema.
10. Thử thêm một getter mới rồi so sánh tài liệu trước/sau để nhận diện thay đổi hợp đồng.

### Tiêu chí hoàn thành

- [ ] Record component được nhận diện đúng trong JSON và OpenAPI.
- [ ] Lớp bất biến có constructor binding rõ ràng và deserialize thành công.
- [ ] Accessor JavaBean dẫn xuất chỉ xuất hiện khi được chủ ý công bố.
- [ ] Method tiện ích không bị hiểu nhầm thành property ngoài ý muốn.
- [ ] Property read-only/write-only có chiều dữ liệu đúng ở cả Jackson và OpenAPI.
- [ ] Dữ liệu nội bộ không xuất hiện trong response JSON.
- [ ] Schema OpenAPI phản ánh đúng tên, kiểu, mô tả và access mode.
- [ ] Test xác minh cả serialization, deserialization và schema được sinh.

## Tiếp tục học

Sau bài này, hãy kết hợp record và lớp bất biến với schema composition, polymorphism, custom serializer và versioning hợp đồng. Khi thay đổi accessor hoặc annotation, hãy xem lại JSON runtime, schema OpenAPI và client được sinh từ đặc tả. Ba kết quả này cần mô tả cùng một mô hình dữ liệu để API ổn định và dễ tích hợp.

