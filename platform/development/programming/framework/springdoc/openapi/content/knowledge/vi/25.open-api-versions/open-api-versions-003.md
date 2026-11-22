# Quan hệ của Schema Object với JSON Schema trong từng phiên bản

`Schema Object` là phần mô tả cấu trúc và ràng buộc dữ liệu trong OpenAPI. Nó được dùng cho request body, response, parameter, header và các model tái sử dụng trong `components.schemas`. Cú pháp Schema Object thay đổi đáng kể giữa OpenAPI 3.0 và 3.1 vì hai phiên bản dựa trên các nền tảng JSON Schema khác nhau.

OpenAPI 3.0 chỉ hỗ trợ một tập con dựa trên JSON Schema Wright Draft 00 và bổ sung một số từ khóa riêng của OpenAPI. OpenAPI 3.1 chuyển sang nền tảng JSON Schema Draft 2020-12, đồng thời định nghĩa dialect cơ sở để bổ sung ngữ nghĩa OpenAPI. Vì vậy, một schema hợp lệ ở 3.1 có thể dùng cú pháp mà validator hoặc code generator chỉ hỗ trợ 3.0 sẽ không hiểu.

Khi dùng springdoc-openapi, cần biết document đang được sinh theo phiên bản nào, hiểu những khác biệt quan trọng của Schema Object và kiểm tra JSON/YAML đầu ra trước khi phân phối hợp đồng API.

## 1. Schema Object dùng để mô tả điều gì?

Schema Object mô tả hình dạng dữ liệu và các quy tắc kiểm tra dữ liệu. Ví dụ một model sản phẩm có thể được mô tả như sau:

```yaml
type: object
required:
  - id
  - name
properties:
  id:
    type: string
    format: uuid
  name:
    type: string
    minLength: 1
    maxLength: 120
  price:
    type: number
    minimum: 0
```

Schema trên cho biết dữ liệu là object, phải có `id` và `name`, `name` là chuỗi có độ dài giới hạn, còn `price` là số không âm.

Schema Object có thể xuất hiện ở nhiều vị trí:

- `components.schemas`: định nghĩa model dùng lại.
- `requestBody.content.<media-type>.schema`: cấu trúc request body.
- `responses.<status>.content.<media-type>.schema`: cấu trúc response body.
- `parameters[].schema`: kiểu dữ liệu của query/path/header/cookie parameter.
- `headers.<name>.schema`: kiểu dữ liệu của response header.

Một schema có thể được tham chiếu bằng `$ref` để tránh lặp định nghĩa. OpenAPI cũng dùng các từ khóa composition như `allOf`, `oneOf` và `anyOf` để mô tả kiểu dữ liệu phức tạp.

## 2. Hai nền tảng JSON Schema khác nhau

| Nội dung | OpenAPI 3.0.x | OpenAPI 3.1.x |
|---|---|---|
| Nền tảng Schema Object | Tập con của JSON Schema Wright Draft 00, có mở rộng OpenAPI | Dựa trên JSON Schema Draft 2020-12 và dialect cơ sở của OpenAPI |
| `type` | Một kiểu dạng chuỗi, ví dụ `string`, `object` | Có thể là một kiểu hoặc mảng kiểu |
| Giá trị null | Từ khóa `nullable: true` | Dùng kiểu `null` theo JSON Schema |
| `exclusiveMinimum` | Boolean kết hợp với `minimum` | Giá trị số độc lập |
| Conditional schema | Không có đầy đủ bộ từ khóa JSON Schema hiện đại | Có `if`, `then`, `else` và các từ khóa 2020-12 tương ứng |
| `prefixItems` | Không thuộc tập Schema Object 3.0 | Được hỗ trợ theo JSON Schema 2020-12 |
| `$defs` | Không thuộc tập từ khóa Schema Object 3.0 | Có thể dùng để định nghĩa schema con theo JSON Schema |
| Dialect | Cấu trúc schema do OpenAPI 3.0 quy định | Có `jsonSchemaDialect` và khả năng chỉ định dialect phù hợp |

Không nên chỉ đổi trường `openapi` từ `3.0.3` thành `3.1.0` rồi giữ nguyên schema. Cần chuyển các từ khóa có ngữ nghĩa khác, kiểm tra validator và kiểm tra công cụ tiêu thụ tài liệu.

## 3. Schema Object của OpenAPI 3.0 là một tập con

OpenAPI 3.0 không triển khai toàn bộ JSON Schema. Nó chọn một tập từ khóa phù hợp cho mô tả API và thêm các từ khóa như `nullable`, `discriminator`, `readOnly`, `writeOnly`, `xml` và `externalDocs`.

Ví dụ schema object 3.0:

```yaml
openapi: 3.0.3
info:
  title: Customer API
  version: 1.0.0
paths: {}
components:
  schemas:
    Customer:
      type: object
      required:
        - id
      properties:
        id:
          type: string
          format: uuid
        displayName:
          type: string
          nullable: true
```

Trong 3.0, `nullable` là phần mở rộng của Schema Object OpenAPI. Một số từ khóa JSON Schema mới hơn không được hỗ trợ theo mô hình này. Nếu đưa `const`, `$defs`, `prefixItems`, `if/then/else` hoặc `unevaluatedProperties` vào schema 3.0, validator có thể báo lỗi hoặc công cụ có thể bỏ qua chúng.

Vì vậy, khi hợp đồng cần được tiêu thụ bởi nhiều code generator cũ, OpenAPI 3.0 có thể là lựa chọn tương thích hơn, miễn là schema có thể diễn đạt chính xác bằng tập từ khóa của phiên bản đó.

## 4. OpenAPI 3.1 sử dụng JSON Schema Draft 2020-12

OpenAPI 3.1 đưa Schema Object gần với JSON Schema hơn. Một Schema Object là một JSON Schema, được diễn giải theo dialect cơ sở của OpenAPI 3.1. Dialect này dựa trên JSON Schema Draft 2020-12 và bổ sung các quy tắc riêng của OpenAPI.

Ví dụ document 3.1:

```yaml
openapi: 3.1.0
info:
  title: Customer API
  version: 1.0.0
components:
  schemas:
    Customer:
      type: object
      required:
        - id
      properties:
        id:
          type: string
          format: uuid
        displayName:
          type:
            - string
            - 'null'
paths: {}
```

Ở ví dụ này, `displayName` có thể là chuỗi hoặc JSON null. Không cần dùng `nullable: true` như OpenAPI 3.0.

OpenAPI 3.1 cũng cho phép sử dụng nhiều từ khóa JSON Schema 2020-12 như `$defs`, `$id`, `$anchor`, `prefixItems`, `if`, `then`, `else`, `dependentRequired` và `unevaluatedProperties`, miễn là chúng được dùng đúng ngữ nghĩa dialect đã chọn.

## 5. Khác biệt quan trọng: `nullable` và kiểu `null`

Đây là một trong những khác biệt dễ gây lỗi nhất khi chuyển từ OpenAPI 3.0 sang 3.1.

### OpenAPI 3.0

```yaml
type: object
properties:
  middleName:
    type: string
    nullable: true
```

`nullable: true` cho phép giá trị null bên cạnh kiểu được khai báo. Theo quy tắc 3.0, `nullable` chỉ có hiệu lực khi `type` được khai báo rõ trong cùng Schema Object.

### OpenAPI 3.1

```yaml
type: object
properties:
  middleName:
    type:
      - string
      - 'null'
```

Hoặc dùng composition:

```yaml
middleName:
  anyOf:
    - type: string
    - type: 'null'
```

Trong JSON Schema 2020-12, `null` là một kiểu dữ liệu. `nullable` không còn là từ khóa chuẩn để diễn đạt union với null trong Schema Object 3.1. Nếu giữ `nullable: true` trong document 3.1, JSON Schema validator có thể xem nó như annotation không được định nghĩa hoặc bỏ qua, dẫn đến schema không còn cho phép null như dự định.

### Null khác với field không xuất hiện

`required` và nullability giải quyết hai câu hỏi khác nhau:

| Schema | Ý nghĩa |
|---|---|
| Field không nằm trong `required`, type là `string` | Có thể bỏ field; nếu gửi thì phải là string |
| Field nằm trong `required`, type là `string` | Phải có field và giá trị phải là string |
| Field không nằm trong `required`, type là `string` hoặc `null` | Có thể bỏ field hoặc gửi null/string |
| Field nằm trong `required`, type là `string` hoặc `null` | Phải có field, nhưng giá trị có thể là null hoặc string |

Không dùng `nullable` hoặc union với `null` để biểu diễn field optional. Muốn field được phép vắng mặt, điều chỉnh danh sách `required`.

## 6. Khác biệt về `exclusiveMinimum` và `exclusiveMaximum`

OpenAPI 3.0 dùng Boolean để bật giới hạn loại trừ, còn OpenAPI 3.1 theo JSON Schema 2020-12 dùng giá trị số trực tiếp.

### OpenAPI 3.0

```yaml
type: number
minimum: 0
exclusiveMinimum: true
maximum: 100
exclusiveMaximum: true
```

Schema này yêu cầu số lớn hơn 0 và nhỏ hơn 100.

### OpenAPI 3.1

```yaml
type: number
exclusiveMinimum: 0
exclusiveMaximum: 100
```

Trong JSON Schema 2020-12, `exclusiveMinimum` và `exclusiveMaximum` nhận giá trị số làm ngưỡng loại trừ. Không chuyển nguyên `exclusiveMinimum: true` từ schema 3.0 sang 3.1.

Ví dụ khi giới hạn giá phải lớn hơn 0:

```yaml
# OpenAPI 3.0
type: number
minimum: 0
exclusiveMinimum: true
```

```yaml
# OpenAPI 3.1
type: number
exclusiveMinimum: 0
```

Hãy kiểm tra cả trường hợp bằng ngưỡng, nhỏ hơn ngưỡng và lớn hơn ngưỡng khi chuyển schema. Validator không tương thích có thể hiểu sai kiểu của từ khóa này.

## 7. Kiểu dữ liệu và union type

Trong OpenAPI 3.0, `type` là một giá trị chuỗi:

```yaml
type: string
```

Nếu cần biểu diễn một giá trị thuộc nhiều kiểu, thường dùng `oneOf` hoặc `anyOf`:

```yaml
oneOf:
  - type: string
  - type: integer
```

OpenAPI 3.1 theo JSON Schema 2020-12 cho phép `type` là mảng:

```yaml
type:
  - string
  - integer
```

Đối với nullability, có thể viết:

```yaml
type:
  - string
  - 'null'
```

Mặc dù cú pháp 3.1 ngắn hơn, `oneOf` và `anyOf` vẫn hữu ích khi mỗi nhánh cần schema riêng, mô tả hoặc discriminator. Không thay thế composition bằng union type chỉ để rút ngắn YAML nếu làm mất ý nghĩa của hợp đồng.

## 8. Mảng đồng nhất và tuple với `items`/`prefixItems`

Schema mảng thông thường dùng `items` để mô tả từng phần tử.

OpenAPI 3.0:

```yaml
type: array
items:
  type: string
```

OpenAPI 3.1 vẫn hỗ trợ cách này cho mảng đồng nhất. JSON Schema 2020-12 bổ sung `prefixItems` để mô tả tuple có kiểu phần tử theo vị trí:

```yaml
type: array
prefixItems:
  - type: string
  - type: integer
items: false
minItems: 2
maxItems: 2
```

Schema 3.1 trên mô tả mảng có đúng hai phần tử: phần tử đầu là string, phần tử thứ hai là integer và không cho phép phần tử tiếp theo. `prefixItems` không thuộc tập Schema Object OpenAPI 3.0.

Nếu API chỉ trả danh sách các object cùng kiểu, `items` là đủ. Chỉ dùng tuple khi thứ tự và kiểu từng vị trí là một phần thực sự của hợp đồng.

## 9. Định nghĩa schema con bằng `$defs`

OpenAPI 3.0 thường tái sử dụng schema qua `components.schemas`:

```yaml
components:
  schemas:
    Address:
      type: object
      properties:
        city:
          type: string
        postalCode:
          type: string
    Customer:
      type: object
      properties:
        address:
          $ref: '#/components/schemas/Address'
```

OpenAPI 3.1 tiếp tục hỗ trợ `components.schemas`, đồng thời cho phép JSON Schema `$defs` bên trong schema:

```yaml
components:
  schemas:
    Customer:
      type: object
      properties:
        address:
          $ref: '#/components/schemas/Customer/$defs/Address'
      $defs:
        Address:
          type: object
          properties:
            city:
              type: string
            postalCode:
              type: string
```

`$defs` hữu ích khi một schema lớn cần định nghĩa các schema con chỉ phục vụ nội bộ cho chính schema đó. Với model được dùng chung giữa nhiều operation, `components.schemas` thường dễ tìm và dễ tái sử dụng hơn.

## 10. `$ref` và các từ khóa nằm cạnh nó

OpenAPI 3.0 có quy tắc Reference Object riêng: object tham chiếu chủ yếu chứa `$ref`; các thuộc tính sibling khác không được xử lý như một phần schema mở rộng. Vì vậy, không nên viết các ràng buộc cạnh `$ref` rồi kỳ vọng mọi công cụ 3.0 áp dụng.

Ví dụ composition an toàn cho 3.0:

```yaml
allOf:
  - $ref: '#/components/schemas/BaseName'
  - type: object
    properties:
      name:
        minLength: 3
```

Trong Schema Object 3.1, `$ref` theo ngữ nghĩa JSON Schema và các từ khóa sibling có thể cùng tham gia đánh giá schema:

```yaml
properties:
  name:
    $ref: '#/components/schemas/Name'
    minLength: 3
```

Điểm này áp dụng cho `$ref` nằm trong Schema Object theo JSON Schema. Đừng nhầm nó với mọi Reference Object trong OpenAPI, chẳng hạn tham chiếu parameter hoặc response; các object đó tuân theo quy tắc Reference Object của OpenAPI.

Khi di chuyển từ 3.0 sang 3.1, kiểm tra các schema đang đặt `description`, `summary` hoặc constraint bên cạnh `$ref`. Kết quả có thể thay đổi vì 3.1 cho phép semantics khác so với cách xử lý Reference Object của 3.0.

## 11. Composition với `allOf`, `oneOf`, `anyOf` và `not`

Các từ khóa composition được hỗ trợ ở cả hai phiên bản, nhưng OpenAPI 3.1 còn cho phép kết hợp rộng hơn với các từ khóa JSON Schema.

| Từ khóa | Ý nghĩa |
|---|---|
| `allOf` | Dữ liệu phải hợp lệ với tất cả schema con |
| `oneOf` | Dữ liệu phải hợp lệ với đúng một schema con |
| `anyOf` | Dữ liệu phải hợp lệ với ít nhất một schema con |
| `not` | Dữ liệu không được hợp lệ với schema con |

Ví dụ dùng `oneOf` để mô tả hai dạng thông tin thanh toán:

```yaml
oneOf:
  - $ref: '#/components/schemas/CardPayment'
  - $ref: '#/components/schemas/BankTransfer'
discriminator:
  propertyName: method
  mapping:
    card: '#/components/schemas/CardPayment'
    bank: '#/components/schemas/BankTransfer'
```

`discriminator` là từ khóa OpenAPI giúp công cụ nhận diện nhánh polymorphic. Nó không phải từ khóa JSON Schema thuần. JSON Schema validator xác định tính hợp lệ bằng `oneOf`/`anyOf` và các ràng buộc schema; không nên giả định validator sẽ dùng `discriminator` để thay thế việc kiểm tra schema con.

## 12. Conditional schema trong OpenAPI 3.1

JSON Schema 2020-12 cung cấp `if`, `then` và `else` để biểu diễn ràng buộc phụ thuộc vào giá trị dữ liệu.

Ví dụ nếu phương thức giao hàng là `pickup`, object phải có `storeId`; nếu là `delivery`, object phải có `address`:

```yaml
type: object
properties:
  fulfillment:
    type: string
    enum: [pickup, delivery]
  storeId:
    type: string
  address:
    type: string
required:
  - fulfillment
if:
  properties:
    fulfillment:
      const: pickup
then:
  required:
    - storeId
else:
  required:
    - address
```

Các từ khóa này không thuộc tập Schema Object OpenAPI 3.0. Khi dùng 3.1, cần bảo đảm validator, code generator và công cụ tài liệu hiểu JSON Schema 2020-12. Swagger UI có thể hiển thị schema nhưng không nhất thiết cung cấp form tương tác đầy đủ cho mọi conditional constraint.

## 13. `additionalProperties`, `patternProperties` và `unevaluatedProperties`

`additionalProperties` điều khiển các thuộc tính không được khai báo trong `properties` hoặc `patternProperties` tương ứng. Trong JSON Schema, nếu không đặt `additionalProperties`, mặc định các thuộc tính bổ sung được chấp nhận.

Ví dụ object chỉ cho phép thuộc tính đã khai báo:

```yaml
type: object
properties:
  id:
    type: string
  name:
    type: string
additionalProperties: false
```

OpenAPI 3.0 hỗ trợ `additionalProperties` là Boolean hoặc Schema Object. OpenAPI 3.1 kế thừa cách dùng này và còn có `patternProperties`:

```yaml
type: object
patternProperties:
  '^x-[a-z0-9-]+$':
    type: string
additionalProperties: false
```

Schema 3.1 trên cho phép các thuộc tính có tên bắt đầu bằng `x-` và giá trị string, đồng thời từ chối các thuộc tính khác không được khai báo.

### Lưu ý khi kết hợp `allOf`

Trong schema composition, `additionalProperties: false` có thể gây bất ngờ vì nó đánh giá các thuộc tính chưa được khai báo trong chính schema con chứa từ khóa đó. Một thuộc tính được khai báo ở nhánh `allOf` khác có thể bị xem là additional.

OpenAPI 3.1/JSON Schema 2020-12 có `unevaluatedProperties` để xử lý các thuộc tính chưa được đánh giá sau khi áp dụng các schema composition:

```yaml
allOf:
  - $ref: '#/components/schemas/BaseCustomer'
  - type: object
    properties:
      loyaltyCode:
        type: string
unevaluatedProperties: false
```

Đây là khả năng của JSON Schema hiện đại và không có trong tập Schema Object OpenAPI 3.0. Hãy kiểm tra validator mà hệ thống sử dụng trước khi áp dụng vào hợp đồng production.

## 14. `format` là annotation hay assertion?

`format` thường mô tả định dạng cụ thể của một kiểu dữ liệu:

```yaml
type: string
format: date-time
```

Các format phổ biến gồm `date`, `date-time`, `uuid`, `email`, `uri`, `hostname`, `ipv4`, `ipv6`, `int32` và `int64`. Format giúp người đọc, Swagger UI, validator hoặc code generator hiểu ý nghĩa dữ liệu tốt hơn.

Tuy nhiên, theo mô hình JSON Schema 2020-12, từ khóa `format` mặc định có vai trò annotation; validator có thể hỗ trợ chế độ format assertion tùy cấu hình. Do đó, không nên cho rằng chỉ khai báo `format: email` là server đã kiểm tra địa chỉ email.

Nếu cần xác thực ở runtime, hãy dùng Bean Validation như `@Email`, logic nghiệp vụ hoặc validator phù hợp. Springdoc có thể đưa constraint vào schema, nhưng việc tài liệu hiển thị format không tự kích hoạt kiểm tra dữ liệu trong controller.

## 15. Từ khóa riêng của OpenAPI trong Schema Object

Schema Object 3.1 vừa dùng từ khóa JSON Schema, vừa giữ một số từ khóa bổ sung của OpenAPI để mô tả API.

| Từ khóa | Vai trò |
|---|---|
| `readOnly` | Thuộc tính chỉ đọc, thường có ý nghĩa ở response |
| `writeOnly` | Thuộc tính chỉ ghi, thường có ý nghĩa ở request |
| `deprecated` | Đánh dấu schema/property đã lỗi thời |
| `discriminator` | Hỗ trợ nhận diện kiểu trong mô hình polymorphic |
| `xml` | Hướng dẫn biểu diễn XML |
| `externalDocs` | Liên kết tài liệu bổ sung |
| `example` | Ví dụ đơn lẻ; đã deprecated trong Schema Object 3.1 |

Trong OpenAPI 3.1, JSON Schema `examples` là mảng ví dụ ở cấp schema. Cần phân biệt nó với `examples` ở Media Type Object, vốn là map có tên đến các Example Object.

`readOnly` và `writeOnly` là metadata ngữ nghĩa OpenAPI, không phải cơ chế phân quyền hay tự động xóa dữ liệu trong server. Ví dụ `password` được đánh dấu `writeOnly: true` không có nghĩa Jackson hoặc Spring tự động ngăn server trả password; ứng dụng phải dùng DTO/serialization phù hợp.

## 16. Dialect và `jsonSchemaDialect` trong OpenAPI 3.1

OpenAPI 3.1 cho phép xác định dialect mặc định của các Schema Object bằng trường `jsonSchemaDialect` ở cấp OpenAPI document.

Ví dụ:

```yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
info:
  title: Catalog API
  version: 1.0.0
paths: {}
```

Nếu không khai báo `jsonSchemaDialect`, OpenAPI 3.1 sử dụng dialect cơ sở được quy định bởi đặc tả. Một Schema Object riêng có thể khai báo `$schema` để chỉ định dialect khác khi phù hợp với quy tắc của OpenAPI 3.1.

Dialect xác định cách diễn giải từ khóa schema. Khi dùng một dialect JSON Schema tùy chỉnh, phải bảo đảm validator và công cụ tiêu thụ tài liệu hiểu dialect đó. Không phải mọi OpenAPI tool đều hỗ trợ mọi vocabulary mở rộng.

## 17. Tái sử dụng schema trong `components.schemas`

Với API có nhiều operation dùng chung model, đặt schema trong `components.schemas` và tham chiếu bằng `$ref` giúp hợp đồng nhất quán.

```yaml
components:
  schemas:
    Money:
      type: object
      required:
        - amount
        - currency
      properties:
        amount:
          type: number
          minimum: 0
        currency:
          type: string
          minLength: 3
          maxLength: 3
    ProductResponse:
      type: object
      required:
        - id
        - price
      properties:
        id:
          type: string
          format: uuid
        price:
          $ref: '#/components/schemas/Money'
```

Request và response có thể dùng chung schema nếu cấu trúc và ngữ nghĩa thực sự giống nhau. Nếu request có field ghi được nhưng response không nên tiết lộ, hãy cân nhắc tách `CreateProductRequest` và `ProductResponse` thay vì dựa vào `readOnly`/`writeOnly` mà không kiểm tra serialization.

## 18. Ánh xạ Schema Object từ Java bằng springdoc

Springdoc đọc Java type, Jackson metadata, Bean Validation và Swagger annotations để sinh Schema Object. Ví dụ DTO:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.UUID;

@Schema(name = "CreateProductRequest", description = "Dữ liệu tạo sản phẩm")
record CreateProductRequest(
        @Schema(description = "Tên sản phẩm", example = "Bàn phím cơ")
        @NotBlank
        @Size(max = 120)
        String name,

        @Schema(description = "Giá bán", example = "129.90", minimum = "0.01")
        @DecimalMin("0.01")
        BigDecimal price
) {}

@Schema(name = "ProductResponse", description = "Thông tin sản phẩm")
record ProductResponse(
        @Schema(description = "Mã sản phẩm", format = "uuid")
        UUID id,

        @Schema(description = "Tên sản phẩm")
        String name,

        @Schema(description = "Giá bán")
        BigDecimal price
) {}
```

Trong ví dụ, springdoc có thể suy luận UUID, số, required và một số constraint từ Java type/Bean Validation. `@Schema` bổ sung mô tả, example và metadata mà kiểu Java không thể hiện.

Không giả định mọi annotation đều chuyển thành JSON Schema giống nhau ở mọi phiên bản. Cần xem `openapi` version và schema đầu ra để biết springdoc đã chuyển `nullable`, giới hạn số hoặc `required` như thế nào.

## 19. Chọn OpenAPI 3.0 hay 3.1 trong ứng dụng

Lựa chọn phiên bản phụ thuộc khả năng của cả producer và consumer:

| Tiêu chí | Ưu tiên 3.0 | Ưu tiên 3.1 |
|---|---|---|
| Code generator/validator cũ chỉ hỗ trợ 3.0 | Phù hợp | Có thể không tương thích |
| Cần mô hình hóa JSON Schema 2020-12 | Không đủ từ khóa | Phù hợp |
| Cần union type qua `type` array | Dùng composition thay thế | Hỗ trợ trực tiếp |
| Cần `if/then/else`, `$defs`, `prefixItems` | Không thuộc tập 3.0 | Hỗ trợ theo JSON Schema 2020-12 |
| Hệ sinh thái client đã kiểm tra 3.1 | Không bắt buộc | Có thể chuẩn hóa ở 3.1 |

Với springdoc, khả năng chọn OpenAPI 3.0 hoặc 3.1 phụ thuộc phiên bản springdoc đang dùng. Nếu phiên bản hỗ trợ cấu hình `springdoc.api-docs.version`, có thể chọn giá trị tương ứng, ví dụ:

```yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
```

Tên property và giá trị được hỗ trợ cần đối chiếu với tài liệu đúng phiên bản springdoc của dự án. Sau khi thay đổi, kiểm tra trường `openapi` trong `/v3/api-docs`; đừng chỉ dựa vào cấu hình đã khai báo.

## 20. Quy trình chuyển schema từ OpenAPI 3.0 sang 3.1

Khi nâng cấp document, rà soát các điểm sau:

1. Đổi trường `openapi` sang phiên bản 3.1 chỉ sau khi producer và consumer đã hỗ trợ.
2. Chuyển `nullable: true` thành union có kiểu `null` hoặc `anyOf`.
3. Chuyển `exclusiveMinimum: true`/`exclusiveMaximum: true` thành giá trị số tương ứng.
4. Kiểm tra `type` có đang dùng mảng kiểu hợp lệ theo 3.1 hay không.
5. Kiểm tra `$ref` có sibling keyword; semantics có thể khác với Reference Object 3.0.
6. Kiểm tra schema đang dùng từ khóa JSON Schema mới như `$defs`, `prefixItems`, `if/then/else`, `patternProperties` hoặc `unevaluatedProperties`.
7. Rà soát `example` trong Schema Object và cân nhắc chuyển sang `examples` theo JSON Schema.
8. Kiểm tra `format` có đang được validator assertion hay chỉ dùng như annotation.
9. Xác minh `readOnly`, `writeOnly` và `discriminator` không bị hiểu nhầm là validation hoặc authorization.
10. Chạy OpenAPI validator và JSON Schema validator tương thích 3.1.
11. Generate SDK thử nghiệm và chạy contract test với client đại diện.
12. So sánh request/response thực tế trước và sau nâng cấp.

## 21. Kiểm tra OpenAPI document do springdoc sinh ra

Lấy document JSON:

```bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
```

Kiểm tra phiên bản OpenAPI:

```bash
jq -r '.openapi' openapi.json
```

Kiểm tra schema được sinh:

```bash
jq '.components.schemas.CreateProductRequest' openapi.json
jq '.components.schemas.ProductResponse' openapi.json
```

Tìm các schema có nullable hoặc exclusive boundary:

```bash
jq '.. | objects | select(has("nullable") or has("exclusiveMinimum") or has("exclusiveMaximum"))' openapi.json
```

Đối với OpenAPI 3.1, xác minh:

- `openapi` bắt đầu bằng `3.1`.
- Nullability được biểu diễn bằng kiểu `null` hoặc composition phù hợp.
- `exclusiveMinimum`/`exclusiveMaximum` có giá trị số.
- Các từ khóa 2020-12 được giữ lại trong output.
- `$ref` được phân giải đúng.
- `components.schemas` không có định nghĩa trùng hoặc mất liên kết.

Đối với OpenAPI 3.0, xác minh:

- `openapi` bắt đầu bằng `3.0`.
- Nullability dùng `nullable` theo quy tắc 3.0.
- Exclusive boundary dùng cú pháp Boolean cùng `minimum`/`maximum`.
- Không có từ khóa JSON Schema mới mà công cụ tiêu thụ 3.0 không hiểu.

## 22. Kiểm tra bằng validator và consumer thực tế

Một tài liệu parse được chưa chắc schema đã có ngữ nghĩa như mong đợi. Nên kiểm tra ở nhiều lớp:

| Lớp kiểm tra | Mục đích |
|---|---|
| YAML/JSON parser | Xác nhận cú pháp document hợp lệ |
| OpenAPI validator | Kiểm tra cấu trúc và quy tắc của OpenAPI version |
| JSON Schema validator | Kiểm tra Schema Object theo dialect tương ứng |
| Swagger UI | Kiểm tra tài liệu có hiển thị được và form có dùng schema hợp lý |
| Code generator | Kiểm tra SDK được sinh đúng kiểu dữ liệu |
| Contract/integration test | Kiểm tra server thực thi cùng ngữ nghĩa với hợp đồng |

Với OpenAPI 3.1, cần dùng validator có hỗ trợ JSON Schema Draft 2020-12. Validator chỉ hỗ trợ OpenAPI 3.0 có thể báo lỗi với từ khóa 3.1 hoặc bỏ qua một số ràng buộc.

Code generator cũng có mức hỗ trợ khác nhau. Ví dụ, một generator có thể parse `type: [string, 'null']` nhưng sinh kiểu Java khác với kỳ vọng, hoặc không hỗ trợ `unevaluatedProperties`. Hãy kiểm tra SDK sinh ra và test payload null/optional thực tế.

## 23. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Schema 3.1 vẫn dùng `nullable: true` | Mang cú pháp 3.0 sang 3.1 | Dùng type union có `null` hoặc composition |
| `exclusiveMinimum` bị báo sai kiểu | Dùng Boolean của 3.0 trong schema 3.1 | Dùng giá trị số trong 3.1 |
| Validator 3.0 từ chối `$defs` hoặc `prefixItems` | Dùng từ khóa JSON Schema 2020-12 trong document 3.0 | Chuyển validator/document sang 3.1 hoặc diễn đạt lại schema |
| Field null bị coi là optional | Nhầm nullability với `required` | Kiểm tra riêng type và danh sách required |
| `$ref` sibling constraint bị bỏ qua | Công cụ áp dụng quy tắc Reference Object 3.0 | Dùng schema composition tương thích hoặc nâng consumer lên 3.1 |
| `format: email` không từ chối dữ liệu sai | Validator không bật format assertion hoặc format chỉ là annotation | Dùng validation runtime và cấu hình validator phù hợp |
| `additionalProperties: false` làm schema `allOf` không hợp lệ | Từ khóa đánh giá property trong từng schema con | Xem xét `unevaluatedProperties` ở 3.1 hoặc thiết kế lại composition |
| Swagger UI hiển thị schema nhưng form không biểu diễn đủ conditional | UI không hỗ trợ tương tác với mọi JSON Schema keyword | Kiểm tra JSON Schema/contract riêng, không suy ra từ form UI |
| Code generator sinh kiểu nullable không mong muốn | Generator chưa hỗ trợ đầy đủ OpenAPI 3.1 | Nâng phiên bản generator hoặc điều chỉnh schema có chủ đích |
| `readOnly` bị xem là bảo vệ dữ liệu | Nhầm metadata OpenAPI với runtime serialization/security | Dùng DTO, Jackson và authorization phù hợp |
| Document khai báo 3.1 nhưng tool parse như 3.0 | Consumer chưa hỗ trợ 3.1 | Nâng consumer hoặc giữ document 3.0 |

## 24. Nguyên tắc thiết kế

- Luôn kiểm tra trường `openapi` để biết Schema Object đang theo phiên bản nào.
- Xem Schema Object 3.0 là tập con JSON Schema theo quy tắc OpenAPI 3.0, không phải toàn bộ JSON Schema hiện đại.
- Với 3.1, dùng cú pháp JSON Schema 2020-12 và hiểu dialect cơ sở của OpenAPI.
- Chuyển `nullable` sang union có kiểu `null` khi nâng cấp 3.0 lên 3.1.
- Chuyển exclusive boundary từ Boolean sang giá trị số.
- Phân biệt field optional với field cho phép null.
- Dùng `$ref` và `components.schemas` để tái sử dụng model; dùng `$defs` khi cần schema con nội bộ ở 3.1.
- Hiểu khác biệt của `$ref` sibling giữa Schema Object 3.1 và Reference Object của OpenAPI.
- Chỉ dùng từ khóa 2020-12 khi validator, Swagger UI và code generator có khả năng hỗ trợ.
- Xem `format` là metadata cho tới khi validator/runtime được cấu hình kiểm tra.
- Không coi `readOnly`, `writeOnly` hoặc `discriminator` là cơ chế authorization.
- Kiểm tra OpenAPI document, JSON Schema, SDK và request/response thực tế sau mỗi lần đổi phiên bản.

## Kết luận

Schema Object của OpenAPI 3.0 dựa trên một tập con JSON Schema cũ cùng các phần mở rộng OpenAPI; OpenAPI 3.1 chuyển sang JSON Schema Draft 2020-12 với dialect cơ sở riêng. Khác biệt dễ ảnh hưởng nhất khi nâng cấp là `nullable` so với kiểu `null`, kiểu của `exclusiveMinimum`/`exclusiveMaximum`, semantics của `$ref` và các từ khóa mới như `$defs`, `prefixItems`, `if/then/else` hay `unevaluatedProperties`. Springdoc có thể sinh Schema Object từ Java type, Jackson, Bean Validation và Swagger annotations, nhưng document đầu ra vẫn cần được kiểm tra bằng validator và consumer tương thích. Hãy chọn OpenAPI version theo khả năng của toàn bộ hệ sinh thái, chuyển schema có kiểm soát và xác minh hợp đồng với request/response runtime.
