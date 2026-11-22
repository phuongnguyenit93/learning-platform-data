# Phân biệt phép hợp thành schema với kế thừa lớp Java

Trong một API có nhiều DTO liên quan nhau, mô hình Java và schema OpenAPI có thể cùng mô tả những cấu trúc tương tự nhưng hoạt động theo quy tắc khác nhau. Java dùng kế thừa lớp, interface và quan hệ chứa đối tượng để tổ chức mã nguồn. OpenAPI dùng các phép hợp thành schema như <code>allOf</code>, <code>oneOf</code> và <code>anyOf</code> để mô tả điều kiện mà một dữ liệu JSON phải thỏa mãn.

Khi springdoc-openapi sinh tài liệu từ controller và DTO, không nên mặc định rằng <code>extends</code> trong Java tương đương với <code>allOf</code> trong OpenAPI. Cần hiểu ngữ nghĩa của từng phép hợp thành, cách Jackson chọn kiểu khi đọc JSON đa hình và cách khai báo <code>@Schema</code> để tài liệu phản ánh đúng hợp đồng HTTP.

## 1. Hai lớp khái niệm khác nhau

Kế thừa Java là quan hệ giữa các kiểu trong chương trình. Một lớp con nhận các thành viên có thể truy cập từ lớp cha, có thể ghi đè phương thức và được dùng ở nơi cần kiểu cha.

Phép hợp thành OpenAPI là quan hệ giữa các schema. Nó quy định một instance JSON cần thỏa mãn một hay nhiều schema thành phần. Bản thân phép hợp thành không tạo lớp Java, không kế thừa method và không quyết định cách Jackson khởi tạo object.

| Khái niệm | Java | OpenAPI |
|---|---|---|
| Kế thừa | <code>class Child extends Parent</code> | Không có toán tử <code>extends</code> |
| Kết hợp nhiều cấu trúc | Một lớp có field tham chiếu đến object khác | Object property chứa <code>$ref</code> |
| Phải thỏa nhiều cấu trúc | Một đối tượng phải tuân theo các kiểu/contract trong chương trình | <code>allOf</code> |
| Chọn đúng một biến thể | Interface hoặc lớp cha đa hình cùng cơ chế runtime | <code>oneOf</code> |
| Chấp nhận một hay nhiều biến thể | Kiểu Java và logic xử lý tự quyết định | <code>anyOf</code> |
| Chọn lớp con khi đọc JSON | Jackson hoặc cơ chế deserialize khác | <code>discriminator</code> hỗ trợ mô tả và nhận diện biến thể |

Ba phép hợp thành schema có ngữ nghĩa riêng:

- <code>allOf</code>: instance phải hợp lệ với **tất cả** schema được liệt kê.
- <code>oneOf</code>: instance phải hợp lệ với **chính xác một** schema được liệt kê.
- <code>anyOf</code>: instance phải hợp lệ với **ít nhất một** schema được liệt kê; có thể đồng thời hợp lệ với nhiều schema.

Đây là các điều kiện kiểm tra dữ liệu, không phải cú pháp mô tả quan hệ lớp Java.

## 2. allOf: dữ liệu phải thỏa tất cả schema

<code>allOf</code> kết hợp các schema theo phép giao. Một object được chấp nhận khi nó thỏa từng schema thành phần.

Ví dụ, nhiều loại sự kiện có chung mã và thời điểm phát sinh:

~~~yaml
components:
  schemas:
    BaseEvent:
      type: object
      required:
        - eventId
      properties:
        eventId:
          type: string
          format: uuid
        occurredAt:
          type: string
          format: date-time

    OrderCreatedEvent:
      allOf:
        - $ref: "#/components/schemas/BaseEvent"
        - type: object
          required:
            - orderId
          properties:
            orderId:
              type: string
            total:
              type: number
              minimum: 0
~~~

Một payload hợp lệ cho <code>OrderCreatedEvent</code>:

~~~json
{
  "eventId": "550e8400-e29b-41d4-a716-446655440000",
  "occurredAt": "2026-11-20T10:30:00Z",
  "orderId": "ORD-100",
  "total": 1250.50
}
~~~

Payload phải có <code>eventId</code> theo schema <code>BaseEvent</code>, đồng thời phải có <code>orderId</code> theo schema thứ hai. <code>allOf</code> không tự gộp các thuộc tính thành một lớp mới; validator kiểm tra cùng một payload với từng schema được tham chiếu.

### 2.1. allOf không phải cơ chế ghi đè thuộc tính

Không nên hiểu <code>allOf</code> như kế thừa Java rồi ghi đè field ở lớp con. Nếu hai schema cùng khai báo một thuộc tính nhưng đặt kiểu hoặc ràng buộc mâu thuẫn, instance có thể không thỏa cả hai.

Ví dụ sau tạo điều kiện không thể đáp ứng cho <code>code</code>:

~~~yaml
allOf:
  - type: object
    properties:
      code:
        type: string
  - type: object
    properties:
      code:
        type: integer
~~~

Một giá trị JSON không thể vừa là string vừa là integer. Schema này không mô tả hành vi ghi đè kiểu từ string thành integer; nó mô tả điều kiện giao của hai kiểu.

Nếu hai phần cùng mô tả một field, hãy thống nhất kiểu và ràng buộc. Nếu mục tiêu là hai biến thể dữ liệu khác nhau, dùng <code>oneOf</code> hoặc <code>anyOf</code> tùy quy tắc chấp nhận.

### 2.2. allOf và kế thừa Java

Java có thể dùng lớp cha để chia sẻ field:

~~~java
import java.time.Instant;
import java.util.UUID;

abstract class BaseEvent {
    private UUID eventId;
    private Instant occurredAt;
}

class OrderCreatedEvent extends BaseEvent {
    private String orderId;
    private java.math.BigDecimal total;
}
~~~

springdoc-openapi và swagger-core có thể biểu diễn mô hình kế thừa Java bằng <code>allOf</code>, tùy kiểu DTO, annotation và phiên bản model converter. Tuy nhiên, kết quả sinh ra không phải cam kết rằng mọi quan hệ <code>extends</code> đều sẽ có cấu trúc <code>allOf</code> giống nhau. Hãy kiểm tra tài liệu JSON thực tế.

Khi cần chủ động công bố phép hợp thành, có thể khai báo <code>allOf</code> trong schema OpenAPI hoặc dùng thuộc tính <code>allOf</code> của annotation <code>@Schema</code>:

~~~java
import java.time.Instant;
import java.util.UUID;

import io.swagger.v3.oas.annotations.media.Schema;

class BaseEventSchema {
    UUID eventId;
    Instant occurredAt;
}

class OrderCreatedFields {
    String orderId;
    java.math.BigDecimal total;
}

@Schema(allOf = {BaseEventSchema.class, OrderCreatedFields.class})
class OrderCreatedEventSchema {
}
~~~

Đây là metadata để mô tả schema. Nó không làm <code>OrderCreatedEventSchema</code> kế thừa các field hoặc method của hai lớp được liệt kê. Nếu muốn Java có quan hệ kế thừa, phải khai báo <code>extends</code> riêng trong mã Java.

## 3. oneOf: dữ liệu phải khớp chính xác một schema

Dùng <code>oneOf</code> khi request hoặc response có nhiều biến thể, nhưng mỗi payload chỉ được thuộc đúng một biến thể.

Ví dụ hệ thống thanh toán chấp nhận thẻ hoặc chuyển khoản:

~~~yaml
components:
  schemas:
    PaymentRequest:
      oneOf:
        - $ref: "#/components/schemas/CardPaymentRequest"
        - $ref: "#/components/schemas/BankTransferRequest"
      discriminator:
        propertyName: paymentType
        mapping:
          card: "#/components/schemas/CardPaymentRequest"
          bank-transfer: "#/components/schemas/BankTransferRequest"

    CardPaymentRequest:
      type: object
      required:
        - paymentType
        - token
      properties:
        paymentType:
          type: string
          enum: [card]
        token:
          type: string

    BankTransferRequest:
      type: object
      required:
        - paymentType
        - bankAccount
      properties:
        paymentType:
          type: string
          enum: [bank-transfer]
        bankAccount:
          type: string
~~~

Payload thanh toán bằng thẻ:

~~~json
{
  "paymentType": "card",
  "token": "tok_123"
}
~~~

Payload chuyển khoản:

~~~json
{
  "paymentType": "bank-transfer",
  "bankAccount": "00123456789"
}
~~~

<code>oneOf</code> yêu cầu payload khớp đúng một schema con. Nếu hai schema con quá rộng và cùng chấp nhận một payload, payload đó có thể không hợp lệ vì khớp nhiều hơn một nhánh.

<code>discriminator</code> cho biết thuộc tính nào giúp nhận diện biến thể và ánh xạ giá trị đến schema tương ứng. Nó hỗ trợ tài liệu và công cụ deserialize, nhưng không thay thế việc định nghĩa schema con hoặc điều kiện <code>oneOf</code>.

## 4. anyOf: dữ liệu phải khớp ít nhất một schema

<code>anyOf</code> phù hợp khi dữ liệu được phép thỏa một hoặc nhiều schema trong danh sách.

Ví dụ một trường thông tin liên hệ có thể là email hoặc số điện thoại:

~~~yaml
components:
  schemas:
    ContactValue:
      anyOf:
        - type: string
          format: email
        - type: string
          pattern: "^\\+?[0-9]{8,15}$"
~~~

Payload như <code>dev@example.com</code> có thể thỏa nhánh email. Chuỗi số điện thoại có thể thỏa nhánh pattern. Nếu một chuỗi thỏa cả hai schema, <code>anyOf</code> vẫn chấp nhận vì chỉ cần ít nhất một nhánh hợp lệ.

So sánh nhanh:

| Phép hợp thành | Điều kiện | Ví dụ cách dùng |
|---|---|---|
| <code>allOf</code> | Tất cả schema đều hợp lệ | Thành phần chung kết hợp với các ràng buộc bổ sung |
| <code>oneOf</code> | Chính xác một schema hợp lệ | Một trong các kiểu thanh toán hoặc sự kiện |
| <code>anyOf</code> | Ít nhất một schema hợp lệ | Dữ liệu có thể thỏa nhiều quy tắc chấp nhận |

Không thay <code>oneOf</code> bằng <code>anyOf</code> chỉ để làm schema dễ qua validation. Điều đó có thể làm thay đổi hợp đồng: một payload đồng thời khớp hai nhánh <code>oneOf</code> vốn bị từ chối sẽ được <code>anyOf</code> chấp nhận.

## 5. Kế thừa Java, composition và đa hình JSON

Trong Java, có ba cách tổ chức model thường gặp:

**Kế thừa:** một lớp con dùng <code>extends</code> để nhận các thành viên của lớp cha.

~~~java
class Person {
    String name;
}

class Employee extends Person {
    String employeeCode;
}
~~~

**Composition trong Java:** một lớp chứa đối tượng khác làm field. Đây là quan hệ has-a:

~~~java
class Address {
    String city;
    String postalCode;
}

class Customer {
    String customerId;
    Address address;
}
~~~

Trong OpenAPI, composition kiểu has-a được mô tả bằng một property có schema tham chiếu:

~~~yaml
Customer:
  type: object
  properties:
    customerId:
      type: string
    address:
      $ref: "#/components/schemas/Address"
~~~

Không cần dùng <code>allOf</code> chỉ vì một DTO chứa DTO khác.

**Đa hình:** một biến tham chiếu kiểu cha hoặc interface có thể trỏ đến nhiều kiểu con. Khi nhận JSON, ứng dụng cần quy tắc xác định kiểu cụ thể để deserialize. Đây là nơi Jackson polymorphism và OpenAPI <code>oneOf</code>/<code>discriminator</code> cần thống nhất.

## 6. Đồng bộ Jackson polymorphism với OpenAPI

Jackson có thể dùng <code>@JsonTypeInfo</code> và <code>@JsonSubTypes</code> để chọn lớp con dựa trên một thuộc tính trong JSON. OpenAPI có thể dùng <code>oneOf</code> và <code>discriminator</code> để công bố cùng quy tắc cho client.

Ví dụ interface thanh toán:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import io.swagger.v3.oas.annotations.media.DiscriminatorMapping;
import io.swagger.v3.oas.annotations.media.Schema;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "paymentType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPaymentRequest.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferRequest.class, name = "bank-transfer")
})
@Schema(
    name = "PaymentRequest",
    oneOf = {CardPaymentRequest.class, BankTransferRequest.class},
    discriminatorProperty = "paymentType",
    discriminatorMapping = {
        @DiscriminatorMapping(value = "card", schema = CardPaymentRequest.class),
        @DiscriminatorMapping(value = "bank-transfer", schema = BankTransferRequest.class)
    }
)
public interface PaymentRequest {
}
~~~

Hai kiểu triển khai:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record CardPaymentRequest(
    @Schema(allowableValues = {"card"})
    String paymentType,
    String token
) implements PaymentRequest {
}

public record BankTransferRequest(
    @Schema(allowableValues = {"bank-transfer"})
    String paymentType,
    String bankAccount
) implements PaymentRequest {
}
~~~

Controller nhận interface:

~~~java
@PostMapping("/payments")
ResponseEntity<Void> createPayment(
        @RequestBody PaymentRequest request) {
    // Xử lý theo biến thể đã được Jackson deserialize
    return ResponseEntity.accepted().build();
}
~~~

Trong ví dụ:

- <code>@JsonTypeInfo</code> chỉ định thuộc tính <code>paymentType</code> được dùng để chọn kiểu khi Jackson đọc JSON.
- <code>@JsonSubTypes</code> ánh xạ giá trị <code>card</code> và <code>bank-transfer</code> đến lớp Java tương ứng.
- <code>@Schema(oneOf = ...)</code> mô tả hai schema có thể có trong OpenAPI.
- <code>discriminatorProperty</code> và <code>discriminatorMapping</code> mô tả cùng quy tắc chọn biến thể cho công cụ đọc tài liệu.

Giá trị trong Jackson và OpenAPI phải khớp nhau. Nếu Jackson dùng <code>bank-transfer</code> nhưng discriminator mapping lại dùng <code>transfer</code>, tài liệu và runtime sẽ hiểu hai hợp đồng khác nhau. Hãy kiểm tra JSON mẫu với cả Swagger UI và endpoint thực tế.

## 7. Biểu diễn phép hợp thành bằng annotation @Schema

Annotation <code>@Schema</code> có các thuộc tính phục vụ composition:

| Thuộc tính | Mục đích |
|---|---|
| <code>allOf</code> | Liệt kê các schema mà dữ liệu phải đồng thời thỏa mãn |
| <code>oneOf</code> | Liệt kê các schema, trong đó dữ liệu phải khớp chính xác một |
| <code>anyOf</code> | Liệt kê các schema, trong đó dữ liệu phải khớp ít nhất một |
| <code>discriminatorProperty</code> | Tên thuộc tính phân biệt biến thể |
| <code>discriminatorMapping</code> | Ánh xạ giá trị discriminator đến schema |

Ví dụ một interface có hai biến thể:

~~~java
@Schema(
    oneOf = {CardPaymentRequest.class, BankTransferRequest.class},
    discriminatorProperty = "paymentType"
)
public interface PaymentRequest {
}
~~~

Với mô hình phức tạp, có thể dùng OpenAPI bean hoặc <code>OpenApiCustomizer</code> để chỉnh sửa schema được sinh ra. Cách này hữu ích khi model converter tự động tạo cấu trúc chưa đúng hợp đồng hoặc khi cần bổ sung <code>allOf</code>, <code>oneOf</code>, <code>anyOf</code> và discriminator mapping tường minh.

Không đặt <code>@Schema(oneOf = ...)</code> vào một kiểu rồi giả định Jackson tự biết cách deserialize. Annotation Swagger mô tả tài liệu; Jackson cần cấu hình polymorphic riêng hoặc custom deserializer.

## 8. Lưu ý quan trọng về additionalProperties khi dùng allOf

Một lỗi thường gặp là đặt <code>additionalProperties: false</code> trong schema cơ sở rồi mở rộng bằng <code>allOf</code>. Trong JSON Schema, <code>additionalProperties</code> chỉ xét các thuộc tính được khai báo trong chính schema đó. Vì vậy, schema cơ sở có thể xem thuộc tính mới được khai báo ở nhánh khác là thuộc tính không được phép.

Ví dụ dễ gây lỗi:

~~~yaml
Base:
  type: object
  properties:
    id:
      type: string
  additionalProperties: false

Child:
  allOf:
    - $ref: "#/components/schemas/Base"
    - type: object
      properties:
        detail:
          type: string
~~~

Payload có cả <code>id</code> và <code>detail</code> có thể bị schema <code>Base</code> từ chối vì <code>detail</code> không được khai báo trong chính nhánh <code>Base</code>.

Với OpenAPI 3.0, cách đơn giản là không đóng object ở schema cơ sở khi còn cần mở rộng bằng <code>allOf</code>, hoặc định nghĩa schema cuối cùng theo một object đã làm phẳng. Nếu bắt buộc phải cấm thuộc tính không biết, cần thiết kế lại schema và kiểm tra bằng validator tương thích OAS 3.0.

OpenAPI 3.1 dựa trên JSON Schema 2020-12 và có <code>unevaluatedProperties</code>, có thể dùng ở schema ngoài cùng để kiểm soát các thuộc tính sau khi các nhánh <code>allOf</code> đã được đánh giá:

~~~yaml
Child:
  allOf:
    - $ref: "#/components/schemas/Base"
    - type: object
      properties:
        detail:
          type: string
  unevaluatedProperties: false
~~~

Chỉ dùng <code>unevaluatedProperties</code> khi tài liệu thực sự là OpenAPI 3.1 và validator trong hệ thống hỗ trợ từ khóa này. Không đưa từ khóa JSON Schema 2020-12 vào tài liệu OAS 3.0 rồi kỳ vọng mọi công cụ hiểu giống nhau.

## 9. Chọn phép hợp thành phù hợp

Hãy bắt đầu từ quy tắc dữ liệu mà API chấp nhận:

| Yêu cầu hợp đồng | Cách mô hình hóa |
|---|---|
| Một object phải có các trường chung và các ràng buộc bổ sung | <code>allOf</code> |
| Một payload là đúng một trong các kiểu đã biết | <code>oneOf</code> |
| Một payload được chấp nhận nếu thỏa ít nhất một nhóm quy tắc | <code>anyOf</code> |
| Một object có field chứa object khác | Property với <code>$ref</code> |
| Một interface Java có nhiều lớp triển khai | Thường mô tả bằng <code>oneOf</code> và discriminator nếu JSON có kiểu phân biệt |
| Một lớp con Java kế thừa lớp cha | Có thể được biểu diễn bằng <code>allOf</code>, nhưng cần kiểm tra schema sinh ra |

Không dùng <code>allOf</code> chỉ để tạo cảm giác có kế thừa. Không dùng <code>oneOf</code> nếu các biến thể có thể cùng hợp lệ. Không dùng <code>anyOf</code> khi hợp đồng yêu cầu duy nhất một biến thể.

## 10. Kiểm tra schema springdoc sinh ra

Sau khi khởi động ứng dụng, lấy đặc tả JSON:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Kiểm tra các phần sau:

1. <code>allOf</code>, <code>oneOf</code> hoặc <code>anyOf</code> xuất hiện đúng vị trí trong schema.
2. Các <code>$ref</code> trỏ tới component tồn tại và không tạo vòng tham chiếu ngoài ý muốn.
3. <code>oneOf</code> có các nhánh thực sự loại trừ nhau cho payload hợp lệ.
4. Discriminator property và mapping khớp với giá trị Jackson sử dụng.
5. Thuộc tính kế thừa từ Java có xuất hiện trong schema cuối cùng không.
6. <code>additionalProperties</code> không vô tình loại bỏ thuộc tính của nhánh khác.
7. Các công cụ downstream như Swagger UI, validator và code generator đọc được cấu trúc đã công bố.

Nên kiểm tra cả tài liệu và hành vi runtime:

- Gửi một payload hợp lệ cho từng biến thể.
- Gửi payload thiếu thuộc tính bắt buộc.
- Gửi payload có discriminator không được hỗ trợ.
- Gửi payload khớp đồng thời nhiều nhánh <code>oneOf</code> để xác nhận bị từ chối.
- Gửi payload chỉ khớp một nhánh <code>anyOf</code> để xác nhận được chấp nhận.
- Kiểm tra deserialize thực tế của Jackson, không chỉ xem schema.

## 11. Lỗi thường gặp

**Xem allOf như extends.** <code>allOf</code> là phép giao schema. Nó không tạo quan hệ kế thừa trong Java và không tự ghi đè field.

**Dùng allOf cho quan hệ has-a.** Nếu <code>Order</code> chứa <code>Address</code>, hãy khai báo property <code>address</code> tham chiếu schema <code>Address</code>; không dùng <code>allOf</code>.

**Dùng oneOf cho các schema chồng lấn.** Một payload khớp hai nhánh sẽ không hợp lệ với <code>oneOf</code>. Hãy điều chỉnh schema hoặc chọn <code>anyOf</code> nếu hợp đồng cho phép nhiều nhánh cùng khớp.

**Nghĩ discriminator tự kiểm tra payload.** Discriminator hỗ trợ xác định biến thể nhưng schema con vẫn cần mô tả thuộc tính và ràng buộc hợp lệ.

**Jackson và OpenAPI dùng tên biến thể khác nhau.** Đồng bộ <code>@JsonSubTypes</code>, <code>discriminatorMapping</code> và enum/constant của thuộc tính phân biệt.

**Đặt additionalProperties false trong schema cơ sở.** Với <code>allOf</code>, nhánh cơ sở có thể từ chối field do nhánh con khai báo. Thiết kế lại schema theo phiên bản OAS đang dùng.

**Giả định springdoc luôn sinh allOf cho mọi extends.** Đầu ra phụ thuộc model converter, annotation và phiên bản thư viện. Kiểm tra <code>/v3/api-docs</code> thay vì dựa vào cấu trúc Java.

## 12. Danh sách rà soát trước khi công bố

- [ ] Đã xác định quan hệ là kế thừa, composition has-a hay đa hình.
- [ ] <code>allOf</code> chỉ được dùng khi instance phải thỏa tất cả schema.
- [ ] <code>oneOf</code> chỉ được dùng khi instance phải khớp chính xác một nhánh.
- [ ] <code>anyOf</code> được dùng khi chỉ cần khớp ít nhất một nhánh.
- [ ] Discriminator mapping khớp với giá trị subtype mà Jackson sử dụng.
- [ ] Annotation <code>@Schema</code> mô tả đúng hợp đồng và không bị nhầm với cấu hình runtime.
- [ ] Không để <code>additionalProperties: false</code> ở nhánh cơ sở vô tình chặn field mở rộng.
- [ ] Đã kiểm tra các <code>$ref</code> và schema được springdoc sinh ra.
- [ ] Đã thử deserialize và validate payload thực tế cho từng biến thể.

## Tài liệu tham khảo

- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): <code>allOf</code>, <code>oneOf</code>, <code>anyOf</code> và discriminator.
- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html): tích hợp JSON Schema 2020-12 và các từ khóa schema.
- [JSON Schema – Combining Schemas](https://json-schema.org/understanding-json-schema/reference/combining): ngữ nghĩa của <code>allOf</code>, <code>anyOf</code> và <code>oneOf</code>.
- [JSON Schema – Object](https://json-schema.org/understanding-json-schema/reference/object): <code>properties</code>, <code>additionalProperties</code> và <code>unevaluatedProperties</code>.
- [Jackson Annotations – JsonTypeInfo](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonTypeInfo.html): cấu hình nhận diện kiểu con khi đọc/ghi JSON.
- [Swagger Core – Schema annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): khai báo composition và discriminator qua <code>@Schema</code>.
- [springdoc-openapi](https://springdoc.org/): sinh và tùy chỉnh đặc tả OpenAPI từ Spring Boot.
