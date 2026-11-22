# Khác biệt về kiểu kết hợp, ràng buộc số và từ khóa schema

OpenAPI 3.0 và OpenAPI 3.1 đều hỗ trợ các từ khóa kết hợp schema như allOf, oneOf, anyOf và not, nhưng cách biểu diễn một số kiểu dữ liệu và ràng buộc đã thay đổi đáng kể. OpenAPI 3.0 dùng một tập con Schema Object riêng dựa trên JSON Schema đời cũ; OpenAPI 3.1 đồng bộ Schema Object với JSON Schema Draft 2020-12 và bổ sung nhiều từ khóa chuẩn.

Khác biệt dễ gặp nhất khi nâng cấp là nullable và exclusiveMinimum/exclusiveMaximum. Trong OpenAPI 3.0, nullable là cờ boolean và exclusive bound cũng là boolean đi cùng minimum/maximum. Trong OpenAPI 3.1, null là một kiểu dữ liệu có thể khai báo trong type, còn exclusive bound nhận trực tiếp giá trị số.

Khi dùng springdoc-openapi, cần biết phiên bản OpenAPI mà tài liệu được sinh ra, kiểm tra schema output tại /v3/api-docs và xác nhận các công cụ downstream hiểu đúng từ khóa được dùng. Việc đổi phiên bản đặc tả không tự động bảo đảm API runtime đã thay đổi hoặc mọi client generator đều tương thích.

## 1. Phiên bản OpenAPI và phiên bản API là hai khái niệm riêng

Tài liệu OpenAPI có trường openapi để chỉ phiên bản định dạng đặc tả, ví dụ 3.0.3 hoặc 3.1.0. Trường info.version mô tả phiên bản của API được công bố.

~~~yaml
openapi: 3.1.0
info:
  title: Product API
  version: 2.4.0
~~~

Trong ví dụ:
- openapi: 3.1.0 là phiên bản cú pháp và mô hình dữ liệu của tài liệu OpenAPI.
- info.version: 2.4.0 là phiên bản API theo quy ước phát hành của sản phẩm.

Nâng tài liệu từ OpenAPI 3.0 lên 3.1 không đồng nghĩa phải đổi URL endpoint, version của API hoặc payload đang chạy. Tuy nhiên, schema mới có thể được validator, gateway hoặc code generator diễn giải khác, nên cần kiểm tra hợp đồng và công cụ sử dụng tài liệu.

## 2. allOf, oneOf, anyOf và not

Các từ khóa composition cho phép kết hợp nhiều schema để mô tả một instance. Chúng có ý nghĩa logic khác nhau:

| Từ khóa | Điều kiện hợp lệ | Cách hiểu |
|---|---|---|
| allOf | Instance phải hợp lệ với tất cả schema con | Giao của các schema |
| oneOf | Instance phải hợp lệ với chính xác một schema con | Chỉ một nhánh được khớp |
| anyOf | Instance phải hợp lệ với ít nhất một schema con | Một hoặc nhiều nhánh được khớp |
| not | Instance không được hợp lệ với schema được chỉ định | Phủ định một schema |

Các từ khóa này có mặt trong cả OpenAPI 3.0 và 3.1. Điểm quan trọng là chúng mô tả quy tắc validation. Chúng không tự tạo class hierarchy trong Java, không tự chuyển đổi JSON thành đúng DTO và không thay thế logic deserialize của ứng dụng.

### 2.1. allOf: tất cả schema con đều phải thỏa mãn

Giả sử mọi sản phẩm đều có mã và tên; sản phẩm vật lý bổ sung trọng lượng:

~~~yaml
components:
  schemas:
    Product:
      type: object
      required: [id, name]
      properties:
        id:
          type: string
        name:
          type: string

    PhysicalProduct:
      allOf:
        - $ref: '#/components/schemas/Product'
        - type: object
          required: [weightKg]
          properties:
            weightKg:
              type: number
              minimum: 0
~~~

Một instance PhysicalProduct phải thỏa mãn cả Product lẫn schema object bổ sung. Nó cần id, name và weightKg; các thuộc tính phải thỏa mãn kiểu và constraint tương ứng.

allOf thường được dùng để tái sử dụng schema hoặc mô tả các thành phần cùng áp dụng. Có thể dùng nó cho mô hình gần với kế thừa, nhưng cần nhớ đây là phép kết hợp validation, không phải lệnh bảo Java tạo một lớp con.

### 2.2. oneOf: chính xác một nhánh hợp lệ

Một khoản thanh toán có thể dùng thẻ hoặc chuyển khoản:

~~~yaml
components:
  schemas:
    Payment:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransferPayment'

    CardPayment:
      type: object
      required: [method, cardToken]
      properties:
        method:
          type: string
          enum: [card]
        cardToken:
          type: string

    BankTransferPayment:
      type: object
      required: [method, bankAccount]
      properties:
        method:
          type: string
          enum: [bank_transfer]
        bankAccount:
          type: string
~~~

Instance hợp lệ phải khớp đúng một trong hai schema. Nếu một payload đồng thời thỏa mãn cả hai nhánh, oneOf vẫn không hợp lệ. Vì vậy, các nhánh nên được thiết kế sao cho có thể phân biệt, thường bằng một thuộc tính discriminator có giá trị khác nhau.

### 2.3. anyOf: một hoặc nhiều nhánh hợp lệ

Nếu một đối tượng tìm kiếm có thể chứa một hoặc nhiều tiêu chí, anyOf có thể diễn tả yêu cầu ít nhất một schema con hợp lệ:

~~~yaml
SearchFilter:
  anyOf:
    - $ref: '#/components/schemas/NameFilter'
    - $ref: '#/components/schemas/CategoryFilter'
~~~

Một payload có thể thỏa mãn cả NameFilter và CategoryFilter mà vẫn hợp lệ. Nếu nghiệp vụ yêu cầu đúng một loại filter, dùng oneOf và bảo đảm các nhánh không chồng lấn.

### 2.4. not: loại trừ một dạng dữ liệu

not có thể diễn tả một giá trị không được khớp với schema chỉ định. Ví dụ, một trường không được là chuỗi rỗng:

~~~yaml
NonEmptyValue:
  type: string
  not:
    const: ""
~~~

Từ khóa const thuộc JSON Schema được hỗ trợ trong OpenAPI 3.1. Nếu cần tương thích OpenAPI 3.0, có thể dùng cách biểu diễn phù hợp với tập từ khóa 3.0, chẳng hạn minLength: 1 cho chuỗi không rỗng.

## 3. Discriminator giúp chọn nhánh nhưng không thay đổi logic validation

Với schema đa hình, discriminator cho biết thuộc tính nào giúp client hoặc công cụ nhận diện schema cụ thể. Ví dụ:

~~~yaml
Payment:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransferPayment'
  discriminator:
    propertyName: method
    mapping:
      card: '#/components/schemas/CardPayment'
      bank_transfer: '#/components/schemas/BankTransferPayment'
~~~

propertyName chỉ ra trường phân biệt; mapping ánh xạ giá trị trường sang schema. Giá trị method trong payload phải nhất quán với schema tương ứng.

Discriminator hỗ trợ công cụ hiểu lựa chọn đa hình, nhưng không làm một payload sai trở nên hợp lệ. oneOf vẫn yêu cầu chính xác một schema con thỏa mãn. Backend cũng cần cấu hình Jackson hoặc cơ chế deserialize phù hợp nếu nhận các kiểu payload đa hình.

Nếu discriminator được dùng, hãy bảo đảm:
- Trường phân biệt có trong schema của từng nhánh.
- Giá trị của trường đủ khác nhau để nhận diện nhánh.
- Mapping trỏ đến đúng component schema.
- Ví dụ request thể hiện đúng giá trị discriminator.
- Code generator và serializer của dự án hỗ trợ cách đa hình đã chọn.

## 4. allOf và additionalProperties khi kết hợp schema

Một lỗi tinh vi xảy ra khi đặt additionalProperties: false trong schema cơ sở rồi mở rộng bằng allOf:

~~~yaml
BaseProduct:
  type: object
  properties:
    id:
      type: string
  additionalProperties: false

PhysicalProduct:
  allOf:
    - $ref: '#/components/schemas/BaseProduct'
    - type: object
      properties:
        weightKg:
          type: number
~~~

Theo cách đánh giá schema, BaseProduct chỉ biết thuộc tính id. Khi schema cơ sở đóng additionalProperties, nó có thể xem weightKg là thuộc tính không được khai báo và từ chối payload, dù schema thứ hai định nghĩa thuộc tính này.

Với OpenAPI 3.1, JSON Schema có unevaluatedProperties, cho phép xử lý các thuộc tính sau khi các schema được kết hợp:

~~~yaml
BaseProduct:
  type: object
  properties:
    id:
      type: string

PhysicalProduct:
  allOf:
    - $ref: '#/components/schemas/BaseProduct'
    - type: object
      properties:
        weightKg:
          type: number
  unevaluatedProperties: false
~~~

Cách này có thể đóng schema sau khi các nhánh composition đã đánh giá thuộc tính. Schema cơ sở không được tự đặt additionalProperties: false, vì keyword đó sẽ từ chối weightKg ngay trong nhánh cơ sở trước khi schema ngoài áp dụng unevaluatedProperties. Cần kiểm tra validator và code generator đang dùng có hỗ trợ unevaluatedProperties hay không.

Nếu phải hỗ trợ OpenAPI 3.0, hãy thiết kế schema composition để không đóng additionalProperties quá sớm. Có thể đặt ràng buộc đóng thuộc tính ở schema hoàn chỉnh hoặc lặp lại cấu trúc cần thiết tùy hợp đồng, rồi kiểm tra bằng validator tương thích 3.0.

## 5. nullable trong OpenAPI 3.0 và kiểu null trong OpenAPI 3.1

Đây là khác biệt cú pháp quan trọng khi chuyển từ 3.0 lên 3.1.

### OpenAPI 3.0

OpenAPI 3.0 dùng nullable: true cùng một type:

~~~yaml
Product:
  type: object
  properties:
    description:
      type: string
      nullable: true
~~~

Property description có thể chứa chuỗi hoặc giá trị null. Nếu bỏ nullable: true, property kiểu string không nhận null theo mô tả schema.

### OpenAPI 3.1

OpenAPI 3.1 biểu diễn null như một kiểu JSON Schema:

~~~yaml
Product:
  type: object
  properties:
    description:
      type: [string, 'null']
~~~

Có thể dùng anyOf nếu cần diễn tả kiểu phức tạp hơn:

~~~yaml
description:
  anyOf:
    - type: string
    - type: 'null'
~~~

Trong OpenAPI 3.1, không nên tiếp tục dựa vào nullable: true như cách chuẩn của 3.0. Hãy dùng type union có null hoặc composition tương ứng.

Cũng cần phân biệt không có property với property có giá trị null:
- Nếu property không nằm trong required, client có thể bỏ hẳn property.
- Nếu property nằm trong required và schema cho phép null, client phải gửi property nhưng giá trị có thể là null.
- Nếu property nằm trong required và schema không cho null, client phải gửi giá trị hợp lệ khác null.

required điều khiển sự hiện diện của property; nullable ở 3.0 hoặc kiểu null ở 3.1 điều khiển giá trị được chấp nhận.

## 6. exclusiveMinimum và exclusiveMaximum thay đổi kiểu dữ liệu

Trong OpenAPI 3.0, exclusiveMinimum và exclusiveMaximum là boolean. Chúng làm cho minimum hoặc maximum trở thành giới hạn loại trừ.

Ví dụ số lượng phải lớn hơn 0 và nhỏ hơn 100:

~~~yaml
quantity:
  type: integer
  minimum: 0
  exclusiveMinimum: true
  maximum: 100
  exclusiveMaximum: true
~~~

Điều kiện tương đương là 0 < quantity < 100.

Trong OpenAPI 3.1, exclusive bound nhận trực tiếp ngưỡng số:

~~~yaml
quantity:
  type: integer
  exclusiveMinimum: 0
  exclusiveMaximum: 100
~~~

Không chuyển nguyên cấu trúc 3.0 sang 3.1. Trong 3.1, giá trị boolean cho exclusiveMinimum hoặc exclusiveMaximum không còn đúng kiểu của JSON Schema. Ngược lại, đưa giá trị số trực tiếp vào tài liệu 3.0 sẽ không phù hợp với Schema Object của 3.0.

Bảng so sánh:

| Ý nghĩa | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Lớn hơn 0 | minimum: 0 + exclusiveMinimum: true | exclusiveMinimum: 0 |
| Lớn hơn hoặc bằng 0 | minimum: 0 | minimum: 0 |
| Nhỏ hơn 100 | maximum: 100 + exclusiveMaximum: true | exclusiveMaximum: 100 |
| Nhỏ hơn hoặc bằng 100 | maximum: 100 | maximum: 100 |

## 7. Các ràng buộc số thường dùng

OpenAPI hỗ trợ nhiều keyword để giới hạn giá trị số. Hầu hết có cùng ý nghĩa ở 3.0 và 3.1, trừ cách biểu diễn exclusive bound.

| Keyword | Ý nghĩa | Ví dụ |
|---|---|---|
| minimum | Giá trị nhỏ nhất, bao gồm biên | minimum: 0 |
| maximum | Giá trị lớn nhất, bao gồm biên | maximum: 100 |
| exclusiveMinimum | Giới hạn dưới loại trừ | exclusiveMinimum: 0 trong 3.1 |
| exclusiveMaximum | Giới hạn trên loại trừ | exclusiveMaximum: 100 trong 3.1 |
| multipleOf | Giá trị phải là bội số của số đã cho | multipleOf: 0.01 |

Ví dụ giá tiền lớn hơn 0 và có bước 0,01:

~~~yaml
price:
  type: number
  exclusiveMinimum: 0
  multipleOf: 0.01
~~~

Đây là cú pháp OpenAPI 3.1. Với OpenAPI 3.0, biểu diễn giới hạn dưới bằng minimum: 0 và exclusiveMinimum: true.

multipleOf: 0.01 mô tả điều kiện toán học của schema; không thay thế kiểu tiền tệ chính xác trong ứng dụng. Với tiền, nên cân nhắc BigDecimal và quy tắc scale/rounding rõ ràng thay vì dùng double hoặc float làm kiểu tính toán chính.

### 7.1. Integer và number

- integer mô tả số nguyên.
- number mô tả số có thể có phần thập phân.
- format như int32, int64, float, double bổ sung gợi ý biểu diễn cho công cụ.

Ví dụ:

~~~yaml
quantity:
  type: integer
  format: int32
  minimum: 1

unitPrice:
  type: number
  format: double
  minimum: 0
~~~

Không nhầm format với constraint. minimum và maximum đặt giới hạn giá trị; format là metadata về dạng biểu diễn. Mức độ kiểm tra format có thể khác nhau giữa validator và code generator.

## 8. Các nhóm constraint khác và khả năng tương thích

Ngoài ràng buộc số, Schema Object có các keyword cho chuỗi, mảng và object:

| Nhóm | Keyword | Tác dụng |
|---|---|---|
| Chuỗi | minLength, maxLength | Giới hạn độ dài |
| Chuỗi | pattern | Yêu cầu khớp biểu thức chính quy |
| Mảng | minItems, maxItems | Giới hạn số phần tử |
| Mảng | uniqueItems | Yêu cầu phần tử không trùng nhau |
| Object | required | Yêu cầu property phải hiện diện |
| Object | minProperties, maxProperties | Giới hạn số property |
| Object | additionalProperties | Kiểm soát property không được liệt kê |
| Schema | enum | Giới hạn tập giá trị |
| Schema | const | Chỉ chấp nhận một giá trị cố định trong JSON Schema, dùng với OpenAPI 3.1 |

Ví dụ:

~~~yaml
ProductInput:
  type: object
  required: [name, tags]
  properties:
    name:
      type: string
      minLength: 2
      maxLength: 80
      pattern: '^[A-Za-z0-9 -]+$'
    tags:
      type: array
      minItems: 1
      maxItems: 10
      uniqueItems: true
      items:
        type: string
  additionalProperties: false
~~~

pattern sử dụng cú pháp biểu thức chính quy theo quy tắc JSON Schema; không mặc định mọi engine regex của Java, JavaScript và validator đều có hành vi giống nhau ở các tính năng mở rộng.

Trong OpenAPI 3.1, nhiều keyword từ JSON Schema 2020-12 có thể được dùng, chẳng hạn const, if/then/else, dependentRequired, prefixItems và unevaluatedProperties. Trước khi dùng các keyword này, kiểm tra toolchain của dự án. Một validator hỗ trợ OpenAPI 3.1 có thể hiểu chúng trong khi code generator hoặc API gateway cũ bỏ qua hoặc xử lý không đầy đủ.

## 9. readOnly, writeOnly và validation của request/response

readOnly và writeOnly là các annotation hữu ích khi một model được dùng ở cả request và response:

~~~yaml
User:
  type: object
  properties:
    id:
      type: string
      readOnly: true
    password:
      type: string
      writeOnly: true
    displayName:
      type: string
~~~

- readOnly: true cho biết property được trả về nhưng không nên được gửi trong request.
- writeOnly: true cho biết property được gửi trong request nhưng không nên được trả về.

Các annotation này giúp mô tả hợp đồng nhưng không tự bảo đảm Jackson loại bỏ property hoặc backend từ chối dữ liệu sai. Nếu request và response có quy tắc khác nhau rõ rệt, cân nhắc dùng DTO riêng để tránh một schema chung gây hiểu nhầm.

## 10. Khai báo composition bằng Springdoc và Swagger annotations

Có thể mô tả composition bằng annotation trên DTO hoặc property. Ví dụ dùng @Schema(oneOf = ...) cho một payload đa hình:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    oneOf = {
        CardPaymentRequest.class,
        BankTransferRequest.class
    },
    discriminatorProperty = "method"
)
interface PaymentRequest {
}

@Schema(name = "CardPayment")
record CardPaymentRequest(
    String method,
    String cardToken
) {
}

@Schema(name = "BankTransferPayment")
record BankTransferRequest(
    String method,
    String bankAccount
) {
}
~~~

Các thuộc tính annotation và khả năng sinh discriminator có thể phụ thuộc phiên bản swagger-core đi cùng springdoc. Sau khi build, kiểm tra OpenAPI document thực tế để xác nhận oneOf, component $ref, tên schema và discriminator mapping đúng như mong muốn.

Với schema phức tạp hoặc keyword JSON Schema 3.1 chưa được annotation biểu diễn đầy đủ, có thể tùy biến model OpenAPI bằng OpenApiCustomizer hoặc khai báo schema tĩnh phù hợp. Cần bảo đảm customizer chạy trên đúng document/group và không ghi đè schema khác ngoài dự kiến.

Không coi việc đặt @Schema(oneOf = ...) là đủ để Jackson tự deserialize đúng subtype. Cấu hình polymorphic type handling của ứng dụng, chẳng hạn @JsonTypeInfo/@JsonSubTypes hoặc custom deserializer, là một mối quan tâm riêng.

## 11. Chọn OpenAPI 3.0 hay 3.1 với springdoc-openapi

Các dòng springdoc hiện đại hỗ trợ tạo tài liệu OpenAPI 3.1 và có thể cấu hình phiên bản tài liệu qua springdoc.api-docs.version nếu phiên bản thư viện đang dùng hỗ trợ thuộc tính đó.

Ví dụ chọn OpenAPI 3.1:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Nếu hệ sinh thái downstream chỉ hỗ trợ OpenAPI 3.0, có thể chọn:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Sau khi đổi cấu hình, truy cập /v3/api-docs và kiểm tra trường đầu tài liệu:
- openapi: 3.1.0 khi chọn 3.1.
- openapi: 3.0.x khi chọn 3.0.

Tên enum/property được hỗ trợ phụ thuộc phiên bản springdoc. Nếu cấu hình không có tác dụng, kiểm tra tài liệu đúng version và dependency thực tế thay vì giả định ứng dụng đã đổi chuẩn.

Khi chuyển từ 3.0 lên 3.1:
1. Kiểm tra các schema có nullable: true và chuyển sang biểu diễn null phù hợp.
2. Chuyển exclusiveMinimum/exclusiveMaximum từ boolean sang ngưỡng số.
3. Kiểm tra các keyword JSON Schema 3.1 được thêm vào.
4. Xác minh composition, discriminator và $ref.
5. Chạy validator và code generator đúng phiên bản.
6. So sánh client SDK hoặc contract test trước và sau khi chuyển.

Nếu chỉ cần giữ tương thích rộng, tiếp tục phát hành 3.0 cho đến khi các công cụ tiêu thụ tài liệu hỗ trợ 3.1. Nếu cần JSON Schema 2020-12, union type có null hoặc keyword mới, hãy chọn 3.1 và kiểm thử toàn bộ pipeline.

## 12. Kiểm tra schema bằng ví dụ thực tế

Giả sử endpoint tạo sản phẩm yêu cầu giá lớn hơn 0, số lượng từ 1 đến 100 và mô tả có thể null. Với OpenAPI 3.1:

~~~yaml
openapi: 3.1.0
info:
  title: Product API
  version: 1.0.0
paths:
  /products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        "201":
          description: Created
components:
  schemas:
    CreateProductRequest:
      type: object
      required: [name, price, quantity]
      properties:
        name:
          type: string
          minLength: 2
          maxLength: 80
        price:
          type: number
          exclusiveMinimum: 0
          multipleOf: 0.01
        quantity:
          type: integer
          minimum: 1
          maximum: 100
        description:
          type: [string, 'null']
~~~

Các trường hợp cần kiểm tra:

| Payload | Kết quả theo schema |
|---|---|
| price: 12.50, quantity: 2, description: null | Hợp lệ nếu name thỏa độ dài |
| price: 0 | Không hợp lệ vì exclusive minimum |
| price: 12.505 | Không hợp lệ vì không phải bội số của 0.01 |
| quantity: 0 | Không hợp lệ vì nhỏ hơn minimum |
| quantity: 101 | Không hợp lệ vì vượt maximum |
| Bỏ quantity | Không hợp lệ vì property nằm trong required |
| description: null | Hợp lệ vì schema chấp nhận kiểu null |

Nếu chuyển schema này sang OpenAPI 3.0, cần sửa hai chỗ: description dùng nullable: true với type: string; price dùng minimum: 0 và exclusiveMinimum: true.

## 13. Lỗi thường gặp

**Dùng nullable: true trong OpenAPI 3.1 như cú pháp chuẩn.** Chuyển sang type: [string, 'null'] hoặc composition có type: 'null'.

**Dùng exclusiveMinimum: 0 trong OpenAPI 3.0.** Ở 3.0, exclusiveMinimum là boolean và phải đi cùng minimum.

**Dùng boolean exclusiveMinimum trong OpenAPI 3.1.** Ở 3.1, giá trị là ngưỡng số; boolean không còn đúng schema.

**Nhầm oneOf với anyOf.** oneOf đòi hỏi đúng một nhánh; anyOf chỉ cần ít nhất một nhánh.

**Coi allOf là kế thừa Java.** allOf là phép kết hợp validation; cần cấu hình DTO/deserializer riêng nếu muốn ánh xạ thành class hierarchy.

**Cho rằng discriminator tự chọn subtype và xác thực payload.** Discriminator là metadata hỗ trợ nhận diện schema; validation vẫn theo các schema composition.

**Đóng additionalProperties trong schema cơ sở rồi mở rộng bằng allOf.** Schema cơ sở có thể từ chối thuộc tính được định nghĩa ở nhánh khác. Với 3.1, xem xét unevaluatedProperties; với 3.0, thiết kế lại vị trí đóng schema.

**Dùng keyword 3.1 nhưng phát hành tài liệu 3.0.** Kiểm tra trường openapi và validator để bảo đảm cú pháp phù hợp phiên bản.

**Chỉ kiểm tra tài liệu hiển thị trên Swagger UI.** UI hiển thị được không chứng minh mọi keyword được validator hoặc code generator hiểu. Cần kiểm tra schema output và công cụ downstream.

**Dùng float/double cho tiền chỉ vì schema khai báo number.** Schema mô tả hợp đồng; lựa chọn kiểu Java và quy tắc tính toán chính xác vẫn thuộc thiết kế ứng dụng.

## 14. Checklist trước khi phát hành OpenAPI

- [ ] Phân biệt openapi với info.version.
- [ ] Chọn OpenAPI 3.0 hoặc 3.1 theo khả năng của client, validator và gateway.
- [ ] Dùng allOf, oneOf, anyOf và not đúng ngữ nghĩa.
- [ ] Các nhánh oneOf không chồng lấn ngoài dự kiến.
- [ ] Discriminator property và mapping khớp schema.
- [ ] Không dùng nullable của 3.0 thay cho null type trong 3.1.
- [ ] exclusiveMinimum/exclusiveMaximum đúng kiểu theo phiên bản.
- [ ] Kiểm tra multipleOf, minimum và maximum bằng các giá trị biên.
- [ ] Kiểm tra required độc lập với khả năng nhận null.
- [ ] Xem xét tác động của additionalProperties trong composition.
- [ ] Chỉ dùng keyword JSON Schema 3.1 khi toolchain hỗ trợ.
- [ ] Kiểm tra readOnly/writeOnly và schema request/response.
- [ ] Xem /v3/api-docs để xác nhận phiên bản và schema output.
- [ ] Chạy validator, contract test và code generator phù hợp.
- [ ] So sánh client hoặc contract trước/sau khi đổi phiên bản.

## Tài liệu tham khảo

- [OpenAPI Specification 3.0.3 – Schema Object](https://spec.openapis.org/oas/v3.0.3.html#schema-object): Schema Object và các giới hạn trong OpenAPI 3.0.
- [OpenAPI Specification 3.1.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object): tích hợp JSON Schema Draft 2020-12 trong OpenAPI 3.1.
- [JSON Schema 2020-12 – Validation](https://json-schema.org/draft/2020-12/json-schema-validation): semantics của numeric, string, array và object constraints.
- [JSON Schema – Combining schemas](https://json-schema.org/understanding-json-schema/reference/combining): allOf, anyOf, oneOf và not.
- [springdoc-openapi](https://springdoc.org/): cấu hình phiên bản OpenAPI và sinh tài liệu từ Spring Boot.
- [Swagger Core – Schema annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): các thuộc tính annotation để mô tả schema.
