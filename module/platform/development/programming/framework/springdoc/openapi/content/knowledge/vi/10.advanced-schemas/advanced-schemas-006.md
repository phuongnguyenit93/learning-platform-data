# oneOf, anyOf, allOf và not theo điều kiện xác thực

Schema OpenAPI có thể mô tả dữ liệu đơn giản bằng type và properties, nhưng nhiều hợp đồng cần diễn đạt quan hệ logic giữa các cấu trúc. Một request có thể thuộc đúng một trong nhiều biến thể, thỏa ít nhất một nhóm điều kiện, đồng thời phải đáp ứng tất cả quy tắc chung, hoặc bị từ chối nếu khớp một cấu trúc bị cấm.

OpenAPI cung cấp các keyword oneOf, anyOf, allOf và not để biểu diễn những điều kiện này. Springdoc-openapi có thể công bố chúng từ annotation @Schema hoặc từ mô hình OpenAPI được tùy biến. Các keyword này mô tả quy tắc hợp lệ của dữ liệu; chúng không tự cấu hình Jackson, không tự viết logic nghiệp vụ và không thay thế validation ở runtime.

## 1. Ý nghĩa logic của bốn keyword

| Keyword | Điều kiện hợp lệ | Cách hiểu |
| --- | --- | --- |
| oneOf | Khớp chính xác một schema con | Chỉ một biến thể được chấp nhận |
| anyOf | Khớp ít nhất một schema con | Một hoặc nhiều biến thể có thể cùng đúng |
| allOf | Khớp tất cả schema con | Dữ liệu phải thỏa mọi nhóm ràng buộc |
| not | Không khớp schema được chỉ định | Loại trừ một cấu trúc hoặc tập giá trị |

Có thể hình dung:

- oneOf là phép XOR: đúng một nhánh.
- anyOf là phép OR: có ít nhất một nhánh đúng.
- allOf là phép AND: tất cả nhánh đều đúng.
- not là phép phủ định: nhánh được chỉ định phải sai.

Các keyword này kết hợp schema, không phải các toán tử để Spring tự thực thi trong controller. Validator tương thích OpenAPI/JSON Schema có thể dùng chúng để kiểm tra payload; ứng dụng vẫn cần đảm bảo xử lý request và validation thực tế khớp với hợp đồng đã công bố.

## 2. oneOf: đúng một trong nhiều schema

oneOf phù hợp khi request có nhiều biến thể loại trừ lẫn nhau. Ví dụ, phương thức thanh toán có thể là thẻ hoặc chuyển khoản. Một payload phải khớp đúng một biến thể.

~~~yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransferPayment'
  discriminator:
    propertyName: kind
    mapping:
      CARD: '#/components/schemas/CardPayment'
      BANK_TRANSFER: '#/components/schemas/BankTransferPayment'

CardPayment:
  type: object
  required: [kind, cardToken]
  properties:
    kind:
      type: string
      enum: [CARD]
    cardToken:
      type: string

BankTransferPayment:
  type: object
  required: [kind, bankAccount]
  properties:
    kind:
      type: string
      enum: [BANK_TRANSFER]
    bankAccount:
      type: string
~~~

Request hợp lệ theo biến thể thẻ:

~~~json
{
  "kind": "CARD",
  "cardToken": "tok_123"
}
~~~

Request hợp lệ theo biến thể chuyển khoản:

~~~json
{
  "kind": "BANK_TRANSFER",
  "bankAccount": "VN0012345678"
}
~~~

Nếu một object đồng thời thỏa cả CardPayment và BankTransferPayment, oneOf sẽ không hợp lệ vì có hai schema con cùng khớp. Nếu object không khớp schema nào, nó cũng không hợp lệ. Vì vậy, các nhánh nên được thiết kế loại trừ nhau bằng discriminator hoặc các ràng buộc cấu trúc rõ ràng.

### Dùng discriminator để nhận diện biến thể

Discriminator giúp công cụ và client nhận biết schema nào tương ứng với giá trị của một property. Trong ví dụ trên, kind=CARD ánh xạ đến CardPayment và kind=BANK_TRANSFER ánh xạ đến BankTransferPayment.

Discriminator không tự làm cho các schema loại trừ nhau và không thay thế điều kiện oneOf. Để bảo đảm validation:

- Property discriminator nên được yêu cầu trong từng schema con.
- Mỗi biến thể nên ràng buộc property đó vào một giá trị riêng, thường dùng enum trong OpenAPI 3.0 hoặc const trong OpenAPI 3.1.
- Payload phải có cấu trúc tương ứng với schema được chọn.

Nếu dùng Jackson để deserialize polymorphic request, cần cấu hình @JsonTypeInfo và @JsonSubTypes hoặc cơ chế tương đương. Annotation OpenAPI chỉ mô tả hợp đồng; nó không tự dạy Jackson tạo đúng class con.

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import io.swagger.v3.oas.annotations.media.DiscriminatorMapping;
import io.swagger.v3.oas.annotations.media.Schema;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "CARD"),
    @JsonSubTypes.Type(value = BankTransferPayment.class, name = "BANK_TRANSFER")
})
@Schema(
    name = "PaymentMethod",
    oneOf = {CardPayment.class, BankTransferPayment.class},
    discriminatorProperty = "kind",
    discriminatorMapping = {
        @DiscriminatorMapping(value = "CARD", schema = CardPayment.class),
        @DiscriminatorMapping(value = "BANK_TRANSFER", schema = BankTransferPayment.class)
    }
)
public interface PaymentMethod {
}
~~~

Các DTO CardPayment và BankTransferPayment cần được khai báo như những kiểu cụ thể và có field phù hợp với payload. Khi dùng cấu hình Jackson này, hãy kiểm tra cả quá trình serialize lẫn deserialize để chắc rằng property kind được phát ra và nhận đúng.

## 3. anyOf: khớp một hoặc nhiều schema

anyOf phù hợp khi dữ liệu có thể thỏa một điều kiện hoặc nhiều điều kiện cùng lúc. Ví dụ, thông tin liên hệ có thể có email, số điện thoại hoặc cả hai.

~~~yaml
ContactInfo:
  type: object
  properties:
    email:
      type: string
      format: email
    phone:
      type: string
  anyOf:
    - required: [email]
    - required: [phone]
~~~

Các payload sau đều hợp lệ:

~~~json
{"email": "dev@example.com"}
~~~

~~~json
{"phone": "+84901234567"}
~~~

~~~json
{"email": "dev@example.com", "phone": "+84901234567"}
~~~

Payload không có email lẫn phone không khớp nhánh nào nên không hợp lệ. Payload có cả hai vẫn hợp lệ vì anyOf chỉ yêu cầu ít nhất một nhánh đúng.

Nếu thay anyOf bằng oneOf, payload có cả email và phone sẽ khớp hai nhánh và bị từ chối. Đây là khác biệt quan trọng khi thiết kế schema cho các trường hợp có thể xuất hiện đồng thời.

Có thể khai báo bằng annotation:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "ContactInfo",
    anyOf = {EmailContact.class, PhoneContact.class},
    description = "Thông tin liên hệ có thể gồm email, số điện thoại hoặc cả hai."
)
public interface ContactInfo {
}
~~~

Khi cần thể hiện rõ rằng ít nhất một property phải có mặt, hãy xác minh schema sinh ra có các nhánh required như mong đợi. Annotation anyOf trên một class không tự bảo đảm các thuộc tính runtime được kiểm tra đúng.

## 4. allOf: phải thỏa tất cả schema

allOf kết hợp nhiều schema theo phép AND. Payload phải đáp ứng mọi schema con cùng lúc. Đây là cách hữu ích để tái sử dụng các nhóm thuộc tính chung hoặc mô tả một model được mở rộng.

Ví dụ, mọi thực thể đều có id và thời điểm tạo; sản phẩm bổ sung tên và giá:

~~~yaml
EntityBase:
  type: object
  required: [id, createdAt]
  properties:
    id:
      type: string
      format: uuid
    createdAt:
      type: string
      format: date-time

Product:
  allOf:
    - $ref: '#/components/schemas/EntityBase'
    - type: object
      required: [name, price]
      properties:
        name:
          type: string
        price:
          type: number
          minimum: 0
~~~

Product phải có id, createdAt, name và price; các ràng buộc trong EntityBase và object bổ sung đều được áp dụng.

Có thể mô tả composition bằng annotation:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

@Schema(name = "EntityBase", description = "Các thuộc tính chung của thực thể.")
public class EntityBase {
    public UUID id;
    public OffsetDateTime createdAt;
}

@Schema(
    name = "Product",
    description = "Sản phẩm mở rộng các thuộc tính chung của thực thể.",
    allOf = {EntityBase.class, ProductFields.class}
)
public class Product {
}

@Schema(name = "ProductFields")
public class ProductFields {
    public String name;
    public BigDecimal price;
}
~~~

Đây là ví dụ minh họa việc tạo schema kết hợp từ các model. Trong ứng dụng thật, hãy kiểm tra cách springdoc và swagger-core xử lý tên component, required và properties khi kết hợp allOf; có thể cần điều chỉnh DTO hoặc cấu hình OpenAPI để tránh sinh schema trùng hoặc tham chiếu không mong muốn.

### allOf không đơn thuần là kế thừa Java

allOf là phép giao các điều kiện schema. Nó không tự tạo quan hệ kế thừa trong Java, cũng không tự cấu hình Jackson. Ngược lại, Java class kế thừa không phải lúc nào cũng được sinh thành allOf; kết quả phụ thuộc model resolver, annotation và cấu hình.

Một lỗi hay gặp là đặt additionalProperties: false trong schema cơ sở rồi dùng allOf để thêm thuộc tính. Schema cơ sở có thể từ chối các thuộc tính được định nghĩa ở nhánh khác vì chúng không nằm trong properties của chính schema cơ sở. Hãy kiểm tra toàn bộ quy tắc đóng/mở object trước khi kết hợp allOf; với OpenAPI 3.1 có thể xem xét unevaluatedProperties sau khi hiểu rõ phạm vi đánh giá.

## 5. not: loại trừ một schema

not làm cho schema tổng thể không hợp lệ khi instance khớp schema được đặt trong not. Ví dụ, username không được là một trong các tên dành riêng:

~~~yaml
Username:
  type: string
  minLength: 3
  maxLength: 40
  not:
    enum:
      - admin
      - root
      - system
~~~

Các giá trị admin, root và system bị loại trừ. Các tên khác vẫn phải thỏa type, minLength và maxLength.

not cũng có thể loại trừ một cấu trúc object:

~~~yaml
CreateAccountRequest:
  type: object
  required: [username]
  properties:
    username:
      type: string
    legacyPassword:
      type: string
  not:
    required: [legacyPassword]
~~~

Schema này không cho phép object có property legacyPassword. Lưu ý required trong schema con của not có nghĩa là schema con khớp khi property legacyPassword tồn tại; not đảo ngược kết quả đó.

Với swagger-core, annotation @Schema có thuộc tính not trong các phiên bản hỗ trợ. Có thể tham chiếu một model biểu diễn cấu trúc bị loại trừ:

~~~java
@Schema(
    name = "ReservedUsername",
    type = "string",
    allowableValues = {"admin", "root", "system"}
)
public class ReservedUsername {
}

public record CreateAccountRequest(
    @Schema(not = ReservedUsername.class, description = "Tên đăng nhập không được là tên hệ thống.")
    String username
) {}
~~~

Hãy xác minh version swagger-core đi kèm springdoc hỗ trợ thuộc tính not và schema được sinh đúng kiểu string. Nếu annotation không biểu đạt được cấu trúc cần thiết, có thể cấu hình trực tiếp Schema model bằng OpenAPI customizer.

## 6. Kết hợp các keyword để diễn đạt điều kiện

Các keyword có thể lồng nhau để mô tả hợp đồng phức tạp. Ví dụ, một request có thể chứa contact và payment; contact phải có email hoặc phone, còn payment phải thuộc đúng một loại.

~~~yaml
CheckoutRequest:
  type: object
  required: [contact, payment]
  properties:
    contact:
      $ref: '#/components/schemas/ContactInfo'
    payment:
      $ref: '#/components/schemas/PaymentMethod'
~~~

Trong cấu trúc này:

- ContactInfo dùng anyOf để yêu cầu ít nhất một phương thức liên hệ.
- PaymentMethod dùng oneOf để chọn đúng một phương thức thanh toán.
- Các schema cơ sở có thể dùng allOf để chia sẻ thuộc tính chung.
- not có thể loại trừ các giá trị hoặc cấu trúc không được phép.

Không nên lồng nhiều lớp composition nếu có thể diễn đạt rõ bằng một schema đơn giản. Cấu trúc càng sâu thì người đọc, validator và client generator càng khó hỗ trợ nhất quán.

## 7. Điều kiện if/then/else trong OpenAPI 3.1

Một số quy tắc phụ thuộc giá trị của property khác, ví dụ nếu paymentType là CARD thì phải có cardToken; nếu là BANK_TRANSFER thì phải có bankAccount. JSON Schema 2020-12 có if, then và else để diễn đạt điều kiện này.

~~~yaml
PaymentRequest:
  type: object
  properties:
    paymentType:
      type: string
      enum: [CARD, BANK_TRANSFER]
    cardToken:
      type: string
    bankAccount:
      type: string
  required: [paymentType]
  allOf:
    - if:
        properties:
          paymentType:
            const: CARD
        required: [paymentType]
      then:
        required: [cardToken]
        not:
          required: [bankAccount]
    - if:
        properties:
          paymentType:
            const: BANK_TRANSFER
        required: [paymentType]
      then:
        required: [bankAccount]
        not:
          required: [cardToken]
~~~

Trong ví dụ:

- paymentType=CARD yêu cầu cardToken và cấm bankAccount.
- paymentType=BANK_TRANSFER yêu cầu bankAccount và cấm cardToken.
- Nếu không có paymentType, schema bị từ chối vì property này nằm trong required.

if/then/else và const thuộc khả năng Schema Object của OpenAPI 3.1. Không đưa các keyword này vào tài liệu OpenAPI 3.0 và mong mọi validator hiểu chúng như JSON Schema 2020-12. Với OpenAPI 3.0, có thể biểu diễn nhiều trường hợp bằng oneOf với các schema con có enum/required riêng.

## 8. Khai báo composition bằng @Schema trong springdoc

Annotation @Schema của swagger-core cung cấp các thuộc tính composition phổ biến:

~~~java
@Schema(oneOf = {CardPayment.class, BankTransferPayment.class})
PaymentMethod payment;

@Schema(anyOf = {EmailContact.class, PhoneContact.class})
ContactInfo contact;

@Schema(allOf = {EntityBase.class, ProductFields.class})
Product product;

@Schema(not = ReservedUsername.class)
String username;
~~~

Các ví dụ trên minh họa cách gắn schema con vào property hoặc model. Cấu trúc class thực tế cần được thiết kế để schema của từng kiểu con phản ánh đúng payload. Đối với các ràng buộc phức tạp như if/then/else, nhiều nhánh not lồng nhau hoặc schema phụ thuộc điều kiện, dùng OpenAPI bean/customizer có thể dễ kiểm soát hơn annotation.

Ví dụ tùy biến OpenAPI model:

~~~java
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class OpenApiSchemaConfig {

    @Bean
    OpenApiCustomizer reservedUsernameCustomizer() {
        return openApi -> {
            if (openApi.getComponents() == null
                    || openApi.getComponents().getSchemas() == null) {
                return;
            }

            Schema<?> request = openApi.getComponents()
                .getSchemas()
                .get("CreateAccountRequest");
            if (request == null || request.getProperties() == null) {
                return;
            }

            Schema<?> username = (Schema<?>) request.getProperties().get("username");
            if (username != null) {
                Schema<?> reservedNames = new StringSchema();
                reservedNames.setEnum(List.of("admin", "root", "system"));
                username.setNot(reservedNames);
            }
        };
    }
}
~~~

Customizer trên tìm property username trong schema CreateAccountRequest rồi gắn một schema string có enum bị cấm vào not. Tên component và property phải khớp với tài liệu do springdoc sinh. Nếu schema chưa tồn tại hoặc tên đã thay đổi, cần điều chỉnh điểm truy cập. Khi tùy biến model, tránh ghi đè composition hoặc properties hiện có ngoài ý muốn và luôn kiểm tra output JSON sau thay đổi.

## 9. Chọn keyword nào cho tình huống nào?

| Tình huống | Keyword phù hợp | Lý do |
| --- | --- | --- |
| Thanh toán bằng thẻ hoặc chuyển khoản, chỉ một loại được dùng | oneOf | Chính xác một schema con phải khớp |
| Người dùng cung cấp email, phone hoặc cả hai | anyOf | Chấp nhận một hoặc nhiều điều kiện |
| DTO có các thuộc tính chung và thuộc tính chuyên biệt | allOf | Tất cả nhóm thuộc tính/ràng buộc cùng áp dụng |
| Cấm tên đăng nhập admin hoặc root | not | Loại trừ các giá trị bị cấm |
| Trường bắt buộc phụ thuộc một property khác | if/then/else trong OAS 3.1 | Diễn đạt quy tắc có điều kiện |

Không chọn oneOf chỉ vì có nhiều schema con. Nếu dữ liệu có thể thỏa nhiều nhánh cùng lúc, anyOf mới phản ánh đúng hợp đồng. Nếu tất cả ràng buộc đều phải đúng, dùng allOf. Nếu muốn cấm một trường hợp, dùng not hoặc biểu diễn nhánh hợp lệ theo cách rõ ràng.

## 10. Khác biệt giữa OpenAPI 3.0 và 3.1

OpenAPI 3.0 sử dụng một tập con Schema Object dựa trên JSON Schema và hỗ trợ các keyword composition như oneOf, anyOf, allOf và not. OpenAPI 3.1 đồng bộ Schema Object gần hơn với JSON Schema 2020-12.

| Khả năng | OpenAPI 3.0 | OpenAPI 3.1 |
| --- | --- | --- |
| oneOf, anyOf, allOf, not | Có | Có |
| discriminator | Có | Có |
| if/then/else | Không thuộc tập Schema Object chuẩn 3.0 | Có theo JSON Schema 2020-12 |
| const | Không có như keyword Schema Object chuẩn 3.0 | Có |
| JSON Schema vocabulary mở rộng | Hạn chế theo subset OAS 3.0 | Hỗ trợ gần đầy đủ hơn theo dialect được khai báo |

Trước khi dùng keyword nâng cao, hãy xem trường openapi trong JSON/YAML được springdoc sinh ra và xác nhận công cụ client, validator, gateway của tổ chức hỗ trợ phiên bản đó. Không phải mọi công cụ hiểu composition hoặc JSON Schema 3.1 giống nhau.

## 11. Kiểm thử schema composition

Một schema composition cần được kiểm tra bằng các payload đại diện cho từng nhánh và các trường hợp biên. Với oneOf, kiểm tra payload khớp đúng một nhánh, không khớp nhánh nào và vô tình khớp nhiều nhánh. Với anyOf, kiểm tra từng nhánh riêng và trường hợp nhiều nhánh cùng đúng. Với allOf, bỏ lần lượt từng điều kiện để chắc rằng mỗi điều kiện thực sự có tác dụng. Với not, thử cả giá trị bị cấm và giá trị được phép.

Ví dụ kiểm tra tài liệu được sinh:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs.yaml
~~~

Checklist:

1. oneOf, anyOf, allOf hoặc not có nằm đúng schema/property không?
2. Mỗi $ref có trỏ tới component tồn tại không?
3. oneOf có các nhánh loại trừ nhau không?
4. Discriminator property có đúng tên và mapping không?
5. Các property bắt buộc và enum có phản ánh từng biến thể không?
6. allOf có bị xung đột additionalProperties hoặc required không?
7. not có phủ định đúng schema dự kiến không?
8. Nếu dùng if/then/else hoặc const, tài liệu có phải OpenAPI 3.1 không?
9. Jackson và Bean Validation runtime có xử lý payload cùng quy tắc với tài liệu không?

Swagger UI có thể hiển thị danh sách biến thể, nhưng giao diện hiển thị không chứng minh payload được validator hoặc server chấp nhận đúng. Hãy kiểm thử bằng validator OpenAPI/JSON Schema tương thích phiên bản và integration test của controller.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| oneOf từ chối payload có vẻ hợp lệ | Payload khớp nhiều schema con hoặc không khớp schema nào | Làm các nhánh loại trừ nhau và kiểm tra required/enum |
| anyOf chấp nhận dữ liệu thiếu thông tin | Schema con không có required hoặc ràng buộc đủ mạnh | Thêm required và các constraint cần thiết vào từng nhánh |
| allOf không cho phép property mở rộng | additionalProperties: false ở schema con gây xung đột | Xem lại cách đóng object; cân nhắc mô hình composition phù hợp |
| Discriminator hiển thị nhưng Jackson không parse được | Chỉ khai báo OpenAPI discriminator mà chưa cấu hình polymorphic deserialization | Đồng bộ @JsonTypeInfo, @JsonSubTypes và schema |
| not không có tác dụng như mong muốn | Schema bị phủ định không diễn tả đúng giá trị cần cấm | Kiểm tra schema con độc lập và test giá trị bị cấm |
| if/then/else không được công cụ nhận diện | Tài liệu xuất theo OpenAPI 3.0 hoặc validator không hỗ trợ OAS 3.1 | Xác nhận phiên bản và chọn cách biểu diễn tương thích |
| Client generator sinh model khó dùng | Composition quá sâu hoặc công cụ hỗ trợ hạn chế | Đơn giản hóa schema, thử generator mục tiêu và cân nhắc endpoint/DTO riêng |

## 13. Quy trình thiết kế schema có điều kiện

Khi mô hình hóa một request có nhiều dạng hoặc nhiều ràng buộc:

1. Liệt kê các biến thể và xác định một payload có thể thuộc một hay nhiều biến thể.
2. Dùng oneOf nếu phải khớp chính xác một nhánh; dùng anyOf nếu một hoặc nhiều nhánh có thể cùng đúng.
3. Dùng allOf cho các ràng buộc đồng thời hoặc các nhóm thuộc tính được tái sử dụng.
4. Dùng not để loại trừ giá trị hoặc cấu trúc; dùng if/then/else nếu cần điều kiện theo property và tài liệu là OpenAPI 3.1.
5. Bổ sung discriminator khi cần nhận diện biến thể, đồng thời cấu hình Jackson để deserialize đúng subtype.
6. Kiểm tra schema do springdoc sinh ra và thử các payload hợp lệ/không hợp lệ bằng validator tương thích.
7. Đồng bộ Bean Validation, service/domain và xử lý lỗi runtime với quy tắc đã công bố.

Các keyword composition giúp hợp đồng API mô tả được nhiều dạng dữ liệu và điều kiện xác thực phức tạp. Khi chọn đúng phép logic và kiểm tra cả đặc tả lẫn hành vi runtime, client có thể hiểu chính xác payload nào được chấp nhận.

## Tài liệu tham khảo

- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Discriminator Object](https://spec.openapis.org/oas/latest.html#discriminator-object)
- [JSON Schema – Combining Schemas](https://json-schema.org/understanding-json-schema/reference/combining)
- [JSON Schema – Conditional Schema Validation](https://json-schema.org/understanding-json-schema/reference/conditionals)
- [Swagger Core – @Schema Annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
