# Kết hợp annotation với cấu hình Jackson cho các kiểu con

Một request có thể chứa một thuộc tính nhận nhiều kiểu dữ liệu khác nhau. Ví dụ, một đơn hàng có thể thanh toán bằng thẻ hoặc chuyển khoản; mỗi phương thức có các trường riêng nhưng cùng thuộc kiểu khái niệm `PaymentMethod`. Đây là mô hình đa hình (polymorphism). Jackson cần biết cách đọc JSON thành đúng lớp con, còn OpenAPI cần mô tả đầy đủ các kiểu có thể xuất hiện để client gửi đúng payload.

Trong Spring Boot, có thể kết hợp annotation Jackson như `@JsonTypeInfo`, `@JsonSubTypes`, `@JsonTypeName` với annotation OpenAPI `@Schema(oneOf = ..., discriminatorProperty = ...)`. Nếu không thể sửa lớp Java, cấu hình Jackson mixin hoặc đăng ký subtype qua `ObjectMapper` có thể đảm nhiệm phần xử lý JSON; schema OpenAPI vẫn cần được công bố rõ ràng và kiểm tra độc lập.

## 1. Bài toán kiểu con trong JSON

Giả sử API tạo giao dịch nhận một `paymentMethod`. Có hai kiểu thanh toán:

- `CardPayment`: chứa token thanh toán và bốn chữ số cuối của thẻ.
- `BankTransferPayment`: chứa mã ngân hàng và số tài khoản nhận.

Một request JSON có thể là:

```json
{
  "paymentMethod": {
    "kind": "card",
    "token": "tok_demo_123",
    "last4": "4242"
  }
}
```

Hoặc:

```json
{
  "paymentMethod": {
    "kind": "bank_transfer",
    "bankCode": "VCB",
    "accountNumber": "0123456789"
  }
}
```

Thuộc tính `kind` là discriminator (trường phân biệt kiểu). Jackson đọc giá trị này để chọn lớp con tương ứng. Trong OpenAPI, `oneOf` mô tả rằng dữ liệu phải khớp một trong các schema con; `discriminator` cho biết trường nào giúp xác định schema cụ thể.

Nếu chỉ khai báo thuộc tính là một interface hoặc abstract class mà không cấu hình đa hình, Jackson không tự biết nên khởi tạo lớp con nào khi nhận JSON. Nếu chỉ cấu hình Jackson mà không mô tả `oneOf` trong OpenAPI, tài liệu cũng có thể không thể hiện rõ các biến thể mà client được phép gửi.

## 2. Khai báo subtype bằng annotation Jackson

Jackson cung cấp một nhóm annotation để mô tả quan hệ giữa kiểu cha và các kiểu con:

| Annotation | Vai trò |
| --- | --- |
| `@JsonTypeInfo` | Bật xử lý type information và chọn cách đưa discriminator vào JSON |
| `@JsonSubTypes` | Liệt kê các lớp con được phép và tên định danh của chúng |
| `@JsonTypeName` | Đặt tên định danh cho một lớp con |
| `@JsonTypeInfo.Id.NAME` | Dùng tên logic như `card`, `bank_transfer` thay vì tên lớp Java |
| `@JsonTypeInfo.As.PROPERTY` | Đưa discriminator vào JSON dưới dạng một property |

Ví dụ kiểu cha `PaymentMethod`:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.media.DiscriminatorMapping;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
@Schema(
    name = "PaymentMethod",
    description = "Một trong các phương thức thanh toán được hỗ trợ",
    oneOf = {CardPayment.class, BankTransferPayment.class},
    discriminatorProperty = "kind",
    discriminatorMapping = {
        @DiscriminatorMapping(value = "card", schema = CardPayment.class),
        @DiscriminatorMapping(value = "bank_transfer", schema = BankTransferPayment.class)
    }
)
public interface PaymentMethod {}
```

Ở đây có hai nhóm annotation với hai nhiệm vụ khác nhau:

- `@JsonTypeInfo` và `@JsonSubTypes` điều khiển cách Jackson đọc/ghi JSON.
- `@Schema` với `oneOf`, `discriminatorProperty` và `discriminatorMapping` mô tả hợp đồng OpenAPI.

Tên `card` và `bank_transfer` phải thống nhất giữa cấu hình Jackson và mapping OpenAPI. Việc Springdoc có thể suy ra một phần cấu trúc từ Jackson không loại bỏ nhu cầu kiểm tra discriminator và mapping trong tài liệu được sinh ra.

## 3. Định nghĩa các lớp con

Mỗi lớp con khai báo các thuộc tính riêng. Có thể dùng record với Java 17:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "CardPayment",
    description = "Thanh toán bằng thẻ đã được token hóa"
)
public record CardPayment(
    @Schema(description = "Token do cổng thanh toán cấp", example = "tok_demo_123")
    String token,

    @Schema(description = "Bốn chữ số cuối của thẻ", example = "4242")
    String last4
) implements PaymentMethod {}
```

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "BankTransferPayment",
    description = "Thanh toán bằng chuyển khoản ngân hàng"
)
public record BankTransferPayment(
    @Schema(description = "Mã ngân hàng", example = "VCB")
    String bankCode,

    @Schema(description = "Số tài khoản nhận", example = "0123456789")
    String accountNumber
) implements PaymentMethod {}
```

Trong cấu hình trên, discriminator `kind` do Jackson thêm vào JSON dựa trên tên subtype. Không cần khai báo `kind` thành một record component nếu ứng dụng chỉ cần Jackson dùng nó để chọn kiểu. Nếu muốn giá trị discriminator cũng được đưa vào một thuộc tính Java thông thường, có thể cân nhắc `visible = true` trong `@JsonTypeInfo`; khi đó phải thiết kế field/constructor và kiểm tra cách deserialize để tránh dữ liệu bị gán hai lần hoặc sai kiểu.

`@JsonSubTypes.Type(name = ...)` đã cung cấp tên logic cho mỗi lớp con. Có thể dùng `@JsonTypeName("card")` trên lớp con như một cách khai báo tên tại chính lớp đó, nhưng nên chọn một quy ước rõ ràng và tránh để tên ở hai nơi mâu thuẫn.

## 4. Đưa kiểu đa hình vào request DTO

DTO chứa kiểu cha có thể dùng `PaymentMethod` như một thuộc tính thông thường:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Yêu cầu tạo giao dịch thanh toán")
public record CreatePaymentRequest(
    @Schema(description = "Phương thức thanh toán được chọn")
    PaymentMethod paymentMethod
) {}
```

Controller nhận request bằng Spring `@RequestBody`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentController {

    @PostMapping(
        path = "/api/payments",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    @Operation(
        summary = "Tạo thanh toán",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = CreatePaymentRequest.class),
                examples = {
                    @ExampleObject(
                        name = "CardPaymentExample",
                        summary = "Thanh toán bằng thẻ",
                        value = "{\"paymentMethod\":{\"kind\":\"card\",\"token\":\"tok_demo_123\",\"last4\":\"4242\"}}"
                    ),
                    @ExampleObject(
                        name = "BankTransferExample",
                        summary = "Thanh toán bằng chuyển khoản",
                        value = "{\"paymentMethod\":{\"kind\":\"bank_transfer\",\"bankCode\":\"VCB\",\"accountNumber\":\"0123456789\"}}"
                    )
                }
            )
        )
    )
    public ResponseEntity<Void> create(@RequestBody CreatePaymentRequest request) {
        // Xử lý theo kiểu thực tế của request.paymentMethod().
        return ResponseEntity.accepted().build();
    }
}
```

Ví dụ dùng `@ExampleObject` để trình bày hai payload hợp lệ. Các giá trị token và tài khoản chỉ là dữ liệu giả lập. Không đưa token thanh toán thật, số tài khoản thật hoặc dữ liệu nhạy cảm vào tài liệu công khai.

## 5. Mô tả `oneOf` và discriminator trong OpenAPI

`oneOf` biểu diễn rằng một giá trị phải phù hợp với đúng một trong các schema được liệt kê. `discriminator` cung cấp quy tắc ánh xạ giá trị của một property sang schema tương ứng.

Kết quả OpenAPI rút gọn có thể giống:

```yaml
components:
  schemas:
    PaymentMethod:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransferPayment'
      discriminator:
        propertyName: kind
        mapping:
          card: '#/components/schemas/CardPayment'
          bank_transfer: '#/components/schemas/BankTransferPayment'
    CardPayment:
      type: object
      properties:
        token:
          type: string
        last4:
          type: string
    BankTransferPayment:
      type: object
      properties:
        bankCode:
          type: string
        accountNumber:
          type: string
```

Đây là ví dụ minh họa cấu trúc. Schema thực tế có thể chứa thêm `required`, description, example, constraints và tên tham chiếu do Springdoc sinh ra. Kiểm tra `components.schemas.PaymentMethod` để xác nhận `oneOf`, `discriminator.propertyName` và từng mapping đã xuất hiện.

### Phân biệt `oneOf`, `anyOf` và `allOf`

| Từ khóa | Ý nghĩa | Trường hợp thường dùng |
| --- | --- | --- |
| `oneOf` | Dữ liệu khớp đúng một schema trong danh sách | Các biến thể loại trừ nhau như thanh toán thẻ hoặc chuyển khoản |
| `anyOf` | Dữ liệu khớp ít nhất một schema trong danh sách | Các cấu trúc có thể chồng lấp hoặc kết hợp |
| `allOf` | Dữ liệu phải thỏa tất cả schema được kết hợp | Tái sử dụng hoặc mở rộng cấu trúc schema |

Với discriminator chọn một kiểu con cụ thể, `oneOf` thường phù hợp hơn. Chỉ dùng `allOf` khi mô hình schema thực sự cần kết hợp các phần; không dùng nó như cách thay thế tùy tiện cho cấu hình đa hình Jackson.

## 6. Dùng `@JsonTypeName` khi muốn đặt tên tại lớp con

Thay vì ghi tên trong `@JsonSubTypes.Type`, Jackson cho phép gắn tên logic trực tiếp lên lớp con:

```java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("card")
public record CardPayment(String token, String last4) implements PaymentMethod {}
```

Khi dùng cách này, vẫn đăng ký lớp con trong `@JsonSubTypes` nhưng bỏ thuộc tính `name` để Jackson lấy tên từ `@JsonTypeName`:

```java
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class),
    @JsonSubTypes.Type(value = BankTransferPayment.class)
})
```

Tương ứng, gắn `@JsonTypeName("bank_transfer")` lên `BankTransferPayment`. `@JsonTypeName` chỉ đặt tên cho subtype; tự nó không thay thế `@JsonTypeInfo` ở kiểu cha và không tự mô tả `oneOf` trong OpenAPI.

Không dùng tên Java class làm discriminator công khai nếu không cần thiết. Tên logic như `card` ổn định hơn khi đổi package hoặc đổi tên lớp. Nếu tên discriminator đã được client sử dụng, thay đổi nó có thể là thay đổi hợp đồng API.

## 7. Khi không thể sửa kiểu cha: dùng Jackson mixin

Một số kiểu cha đến từ thư viện bên ngoài hoặc module dùng chung mà nhóm không muốn sửa source. Jackson mixin cho phép gắn annotation Jackson từ một lớp khác vào kiểu đích.

Mixin cho `PaymentMethod` đặt annotation ở cấp kiểu:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
abstract class PaymentMethodMixin {}
```

Đăng ký mixin với Jackson builder do Spring Boot quản lý:

```java
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonPolymorphismConfig {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer paymentMethodMixin() {
        return builder -> builder.mixIn(PaymentMethod.class, PaymentMethodMixin.class);
    }
}
```

Spring Boot áp dụng customizer khi tạo `ObjectMapper` được auto-configure. Nếu ứng dụng tự khai báo nhiều `ObjectMapper`, converter riêng hoặc cấu hình Jackson tùy chỉnh, hãy xác minh mapper mà `MappingJackson2HttpMessageConverter` thực sự sử dụng cũng đã nhận mixin.

Mixin giải quyết cách Jackson serialize/deserialize. Để OpenAPI mô tả chính xác các kiểu con, hãy khai báo `@Schema(oneOf = ..., discriminatorProperty = ..., discriminatorMapping = ...)` trên thuộc tính DTO hoặc một lớp tài liệu mà Springdoc đọc được. Khả năng Springdoc phản ánh mọi mixin có thể phụ thuộc cách cấu hình mapper và phiên bản thư viện; không giả định rằng mixin luôn tự tạo đầy đủ `oneOf` và discriminator.

Ví dụ khai báo schema trực tiếp trên thuộc tính khi không thể thêm `@Schema` vào kiểu cha:

```java
public record CreatePaymentRequest(
    @Schema(
        description = "Phương thức thanh toán",
        oneOf = {CardPayment.class, BankTransferPayment.class},
        discriminatorProperty = "kind",
        discriminatorMapping = {
            @DiscriminatorMapping(value = "card", schema = CardPayment.class),
            @DiscriminatorMapping(value = "bank_transfer", schema = BankTransferPayment.class)
        }
    )
    PaymentMethod paymentMethod
) {}
```

## 8. Đăng ký subtype qua cấu hình `ObjectMapper`

Ngoài `@JsonSubTypes`, Jackson cho phép đăng ký các subtype bằng `NamedType`. Cách này hữu ích khi muốn quản lý danh sách subtype tập trung trong cấu hình:

```java
import com.fasterxml.jackson.databind.jsontype.NamedType;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PaymentSubtypeConfig {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer registerPaymentSubtypes() {
        return builder -> builder.postConfigurer(mapper ->
            mapper.registerSubtypes(
                new NamedType(CardPayment.class, "card"),
                new NamedType(BankTransferPayment.class, "bank_transfer")
            )
        );
    }
}
```

Cấu hình đăng ký subtype cần đi cùng `@JsonTypeInfo` trên kiểu cha hoặc mixin để Jackson biết phải đọc discriminator `kind`. Nếu dùng cách đăng ký này, không nhất thiết phải lặp lại `@JsonSubTypes`; hãy chọn một nơi làm nguồn quản lý danh sách subtype để tránh mapping trùng hoặc lệch tên.

Đăng ký subtype trong `ObjectMapper` chỉ cấu hình runtime của Jackson. OpenAPI vẫn cần được mô tả bằng `oneOf` và discriminator. Nếu kiểu cha không thể gắn `@Schema`, hãy đặt metadata trên property DTO như ví dụ ở phần trước.

## 9. Giữ mapping Jackson và OpenAPI nhất quán

Một lỗi phổ biến là Jackson dùng tên `bank_transfer` nhưng OpenAPI mapping lại dùng `bank-transfer` hoặc tên lớp. Khi đó request có thể deserialize đúng trong một số trường hợp nhưng tài liệu hướng dẫn client gửi sai discriminator.

Hãy quản lý một bảng ánh xạ rõ ràng:

| Giá trị `kind` trong JSON | Lớp Java | Schema OpenAPI |
| --- | --- | --- |
| `card` | `CardPayment` | `#/components/schemas/CardPayment` |
| `bank_transfer` | `BankTransferPayment` | `#/components/schemas/BankTransferPayment` |

Kiểm tra các điểm sau:

1. Tên trong `@JsonSubTypes.Type(name = ...)`, `@JsonTypeName` hoặc `NamedType` giống giá trị discriminator mà client gửi.
2. `@JsonTypeInfo(property = "kind")` dùng cùng tên với `@Schema(discriminatorProperty = "kind")`.
3. `@DiscriminatorMapping(value = ...)` trỏ đến đúng schema con.
4. Mỗi schema con mô tả các field mà Jackson thực sự nhận và trả về.
5. Ví dụ JSON sử dụng đúng discriminator và field của subtype.
6. Các subtype được đăng ký đều là loại mà API thực sự cho phép.

Nếu có nhiều endpoint dùng cùng kiểu đa hình, nên đặt metadata schema ở kiểu cha hoặc một cấu hình tài liệu dùng chung để tránh các operation mô tả khác nhau.

## 10. Kiểm tra deserialize, serialize và tài liệu OpenAPI

Không nên chỉ nhìn Swagger UI để kết luận đa hình hoạt động đúng. Cần xác minh cả JSON runtime và đặc tả.

### Kiểm tra JSON đầu vào

Gửi request với discriminator `card`:

```bash
curl -X POST http://localhost:8080/api/payments \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"paymentMethod":{"kind":"card","token":"tok_demo_123","last4":"4242"}}'
```

Sau đó thử `bank_transfer` với các field tương ứng. Nếu controller nhận được đúng lớp con, Jackson đã chọn subtype theo discriminator.

### Kiểm tra OpenAPI

Mở `/v3/api-docs` hoặc `/v3/api-docs.yaml` và xác nhận:

- Schema cha `PaymentMethod` có `oneOf` trỏ đến tất cả kiểu con được hỗ trợ.
- Discriminator có `propertyName: kind`.
- Mapping có các giá trị `card` và `bank_transfer` cùng tham chiếu đúng schema.
- Schema con chứa các field, kiểu dữ liệu, required và example phù hợp.
- Request body của operation tham chiếu đến DTO chứa `PaymentMethod`.

Swagger UI nên hiển thị các biến thể và ví dụ để người tích hợp chọn payload thích hợp. Tùy phiên bản Swagger UI, cách trình bày `oneOf` có thể khác nhau; tài liệu JSON/YAML là căn cứ để xác minh cấu trúc hợp đồng.

## 11. Xử lý discriminator không hợp lệ và subtype chưa biết

Nếu request không có `kind`, hoặc gửi một giá trị không được đăng ký, Jackson có thể ném lỗi như `InvalidTypeIdException`. Spring MVC thường chuyển lỗi chuyển đổi request body thành `400 Bad Request`, tùy exception handler của ứng dụng.

Hãy xác định rõ hành vi API:

- Discriminator có bắt buộc không?
- Client nhận mã lỗi nào nếu thiếu `kind`?
- Client nhận mã lỗi nào nếu `kind` không được hỗ trợ?
- Khi thêm subtype mới, các client cũ có cần xử lý trường hợp chưa biết hay không?

Nếu có exception handler riêng, hãy mô tả response lỗi bằng schema thực tế. Không tự động chọn subtype mặc định cho dữ liệu không rõ nguồn gốc nếu điều đó có thể khiến request bị diễn giải sai nghiệp vụ.

## 12. Lưu ý an toàn khi bật polymorphic deserialization

Request JSON đến từ client là dữ liệu không đáng tin cậy. Cấu hình subtype nên giới hạn rõ các lớp mà API cho phép khởi tạo.

- Ưu tiên `JsonTypeInfo.Id.NAME` với danh sách subtype được allowlist bằng `@JsonSubTypes` hoặc `NamedType`.
- Tránh dùng `JsonTypeInfo.Id.CLASS` cho payload không tin cậy vì client có thể gửi tên lớp Java, làm lộ chi tiết triển khai và mở rộng phạm vi kiểu được Jackson xử lý.
- Không bật global default typing một cách tùy tiện cho `ObjectMapper` nhận dữ liệu bên ngoài. Nếu thực sự cần, phải dùng validator giới hạn subtype và đánh giá kỹ rủi ro.
- Không đăng ký lớp tùy ý chỉ để làm cho một payload deserialize được. Chỉ đăng ký các subtype thuộc hợp đồng API.
- Không đưa thông tin thanh toán, token hoặc dữ liệu cá nhân thật vào example.

`Id.NAME` cùng danh sách subtype rõ ràng giúp hợp đồng ổn định và giới hạn loại dữ liệu Jackson có thể tạo. Đây là lựa chọn phù hợp hơn cho API công khai so với việc để client chỉ định trực tiếp tên lớp Java.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Jackson báo không tìm thấy subtype | Thiếu `@JsonSubTypes`, `@JsonTypeName` hoặc đăng ký `NamedType` | Kiểm tra danh sách subtype và giá trị `kind` |
| JSON deserialize vào kiểu sai | Tên discriminator trùng hoặc mapping không nhất quán | Dùng tên logic duy nhất cho từng subtype |
| Swagger UI không hiển thị các kiểu con | Chưa khai báo `@Schema(oneOf = ...)` hoặc Springdoc không nhận cấu hình Jackson mong muốn | Khai báo schema tường minh và kiểm tra `components.schemas` |
| Có `oneOf` nhưng thiếu discriminator | Chưa đặt `discriminatorProperty` hoặc mapping | Bổ sung `discriminatorProperty` và `@DiscriminatorMapping` |
| Discriminator trong JSON khác OpenAPI | Jackson và `@Schema` dùng tên property hoặc giá trị mapping khác nhau | Đồng bộ `kind`, subtype name và mapping |
| Mixin hoạt động với controller khác nhưng không hoạt động ở endpoint này | Converter đang dùng `ObjectMapper` khác với mapper đã cấu hình | Kiểm tra `HttpMessageConverter` và các bean mapper |
| Field discriminator bị thiếu trong object Java | Jackson dùng type id để chọn subtype nhưng không chuyển nó thành property thường | Chỉ dùng `visible = true` khi DTO thực sự cần giữ property đó |
| Request có `kind` lạ trả về lỗi | Subtype không nằm trong allowlist | Công bố lỗi phù hợp và chỉ đăng ký loại được hỗ trợ |

## 14. Checklist kết hợp Jackson và OpenAPI

- [ ] Kiểu cha có `@JsonTypeInfo` hoặc mixin cấu hình type information.
- [ ] Subtype được liệt kê rõ bằng `@JsonSubTypes`, `@JsonTypeName` hoặc `NamedType`.
- [ ] Dùng discriminator logic ổn định như `card` hoặc `bank_transfer`.
- [ ] `@Schema(oneOf = ...)` liệt kê đầy đủ các lớp con.
- [ ] `discriminatorProperty` khớp với `property` của `@JsonTypeInfo`.
- [ ] `@DiscriminatorMapping` khớp với tên subtype mà Jackson sử dụng.
- [ ] Schema con có mô tả và example phù hợp với JSON thực tế.
- [ ] Mixin được gắn vào đúng `ObjectMapper` mà Spring MVC sử dụng.
- [ ] Đã kiểm tra JSON deserialize/serialize cho từng subtype.
- [ ] Đã kiểm tra `oneOf`, discriminator và mapping trong `/v3/api-docs`.
- [ ] Đã xác định cách xử lý discriminator thiếu hoặc không hợp lệ.
- [ ] Chỉ cho phép các subtype đã được kiểm soát; không bật default typing rộng cho dữ liệu không tin cậy.

Jackson quyết định cách chuyển JSON thành kiểu con và cách ghi discriminator ra JSON; Springdoc công bố các kiểu con đó thành `oneOf` và discriminator trong OpenAPI. Khi annotation, cấu hình `ObjectMapper` và metadata schema dùng cùng một danh sách subtype cùng tên mapping, API vừa deserialize đúng dữ liệu vừa cung cấp hợp đồng rõ ràng cho client.
