# jsonSchemaDialect và từ khóa JSON Schema cần đối chiếu khi dùng 3.1

OpenAPI 3.1 thay đổi đáng kể cách mô tả dữ liệu so với OpenAPI 3.0: Schema Object được xây dựng trên JSON Schema Draft 2020-12 và có thể sử dụng các từ khóa JSON Schema tương ứng. Vì vậy, khi đọc hoặc sinh tài liệu OpenAPI 3.1, cần phân biệt phiên bản OpenAPI với dialect dùng để diễn giải từng Schema Object.

Trường cấp cao nhất **jsonSchemaDialect** khai báo dialect mặc định cho các Schema Object trong tài liệu. Nếu một schema resource có từ khóa **$schema** ở gốc, dialect tại đó có thể ghi đè giá trị mặc định. Bên cạnh đó, các từ khóa như **type**, **const**, **prefixItems**, **unevaluatedProperties**, **dependentRequired** và **if/then/else** có ngữ nghĩa theo JSON Schema 2020-12. Dùng sai dialect hoặc mang nguyên cú pháp 3.0 sang 3.1 có thể khiến validator, code generator và công cụ tài liệu hiểu schema khác với ý định.

## 1. Phân biệt phiên bản OpenAPI và JSON Schema dialect

OpenAPI và JSON Schema giải quyết hai lớp vấn đề khác nhau:

| Thành phần | Câu hỏi được trả lời |
|---|---|
| Trường openapi | Tài liệu tuân theo phiên bản đặc tả OpenAPI nào? |
| Trường jsonSchemaDialect | Schema Object mặc định được diễn giải theo dialect JSON Schema nào? |
| Từ khóa $schema trong schema resource | Schema resource cụ thể sử dụng dialect nào? |

Ví dụ, tài liệu có thể khai báo:

~~~yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
~~~

Giá trị openapi là phiên bản OpenAPI. Giá trị jsonSchemaDialect là URI xác định dialect cho Schema Object. Hai giá trị không thay thế nhau: chỉ đổi openapi từ 3.0.3 sang 3.1.0 không tự động giải thích chính xác các schema được viết bằng từ khóa mới.

OpenAPI 3.1 Schema Object là một superset của JSON Schema Draft 2020-12, có thêm các từ khóa và quy tắc riêng của OpenAPI. Vì thế, không nên mặc định mọi Schema Object trong tài liệu OpenAPI đều tương đương một schema JSON Schema thuần mà không có vocabulary bổ sung.

## 2. Khác biệt quan trọng giữa OpenAPI 3.0 và 3.1

OpenAPI 3.0 sử dụng một tập con schema riêng, gần với các bản JSON Schema cũ. OpenAPI 3.1 chuyển sang mô hình dựa trên JSON Schema Draft 2020-12.

| Nội dung | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Cơ sở schema | Tập con Schema Object của OAS 3.0 | JSON Schema Draft 2020-12 và OAS vocabulary |
| jsonSchemaDialect | Không có | Có ở OpenAPI Object |
| Null type | Thường dùng nullable: true cùng type | Dùng type có giá trị null hoặc composition |
| exclusiveMinimum | Boolean kết hợp minimum | Giá trị số làm ngưỡng loại trừ |
| exclusiveMaximum | Boolean kết hợp maximum | Giá trị số làm ngưỡng loại trừ |
| Tuple array | Không có prefixItems theo 2020-12 | Dùng prefixItems và items |
| Conditional schema | Hạn chế theo tập con | Có if, then, else |
| Unevaluated properties/items | Không hỗ trợ theo ngữ nghĩa 2020-12 | Có unevaluatedProperties và unevaluatedItems |
| Reusable subschema | components/schemas và $ref | Có thêm $defs, $anchor và các cơ chế JSON Schema |

Không trộn cú pháp của hai thế hệ. Ví dụ, trong OAS 3.0, exclusiveMinimum thường được viết như một cờ Boolean cùng minimum. Trong JSON Schema 2020-12, exclusiveMinimum là một số. Một schema hợp lệ ở thế hệ này có thể bị từ chối hoặc diễn giải sai ở thế hệ khác.

## 3. jsonSchemaDialect là gì?

jsonSchemaDialect là thuộc tính cấp cao nhất của OpenAPI Object. Nó cung cấp dialect mặc định cho các Schema Object trong tài liệu, nếu schema resource không khai báo dialect riêng bằng $schema.

Dialect mặc định của OpenAPI 3.1 là:

~~~yaml
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
~~~

URI này xác định OAS base dialect. Dialect đó kết hợp các vocabulary JSON Schema cần thiết với các quy tắc bổ sung của OpenAPI Schema Object.

Nếu bỏ jsonSchemaDialect, OpenAPI 3.1 dùng OAS base dialect mặc định. Việc khai báo tường minh có thể giúp người đọc và một số công cụ nhận diện rõ ý định của tài liệu, nhưng không bắt buộc nếu dùng mặc định.

jsonSchemaDialect không phải URL để Swagger UI tải tài liệu và cũng không phải URL của API server. Đây là định danh dialect, không phải endpoint chạy request.

## 4. Khai báo dialect ở cấp tài liệu

Ví dụ tài liệu OpenAPI 3.1:

~~~yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
info:
  title: Store API
  version: 1.0.0
paths: {}
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
      required:
        - id
        - name
~~~

Trong ví dụ, mọi Schema Object không tự khai báo $schema sẽ dùng dialect mặc định được chỉ định ở jsonSchemaDialect. Tài liệu vẫn là một OpenAPI document; dialect chỉ ảnh hưởng cách diễn giải schema, không thay đổi path, operation hay HTTP method.

Nếu dùng công cụ sinh OpenAPI, hãy kiểm tra document đầu ra thay vì chỉ nhìn file cấu hình. Cần xác nhận trường openapi thực sự là 3.1.x và jsonSchemaDialect có giá trị mong đợi hoặc được áp dụng theo mặc định.

## 5. Ghi đè dialect bằng $schema

Một schema resource có thể khai báo $schema ở gốc để chọn dialect riêng:

~~~yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
components:
  schemas:
    ExternalContract:
      $schema: https://json-schema.org/draft/2020-12/schema
      type: object
      properties:
        contractId:
          type: string
      required:
        - contractId
~~~

Ở ví dụ này, $schema tại gốc của ExternalContract ghi đè dialect mặc định của tài liệu cho schema resource đó. Khi chọn dialect JSON Schema thuần, cần cân nhắc các từ khóa bổ sung riêng của OpenAPI như discriminator, xml hoặc externalDocs: validator JSON Schema thuần có thể không hiểu ngữ nghĩa OpenAPI của chúng.

Không đặt $schema tùy tiện ở mọi property con. $schema được dùng để xác định dialect tại gốc của schema resource; một subschema được tham chiếu độc lập bằng URI có thể là một schema resource riêng và có quy tắc base URI riêng.

## 6. Các nhóm từ khóa JSON Schema 2020-12

Có thể chia các từ khóa thường gặp thành các nhóm:

| Nhóm | Từ khóa tiêu biểu | Mục đích |
|---|---|---|
| Core và định danh | $schema, $id, $ref, $anchor, $dynamicRef, $dynamicAnchor, $defs | Chọn dialect, định danh và tái sử dụng schema |
| Kiểu và giá trị | type, enum, const | Giới hạn kiểu hoặc tập giá trị |
| Chuỗi | minLength, maxLength, pattern, format | Ràng buộc chuỗi và gợi ý định dạng |
| Số | minimum, maximum, exclusiveMinimum, exclusiveMaximum, multipleOf | Giới hạn giá trị số |
| Mảng | items, prefixItems, contains, minItems, maxItems, uniqueItems | Mô tả phần tử và cấu trúc mảng |
| Đối tượng | properties, patternProperties, required, additionalProperties | Mô tả thuộc tính object |
| Phụ thuộc và đánh giá | dependentRequired, dependentSchemas, unevaluatedProperties, unevaluatedItems | Ràng buộc phụ thuộc và kiểm soát phần chưa được đánh giá |
| Kết hợp | allOf, anyOf, oneOf, not | Kết hợp nhiều schema |
| Điều kiện | if, then, else | Chọn schema theo điều kiện |
| Nội dung | contentEncoding, contentMediaType, contentSchema | Mô tả dữ liệu có nội dung mã hóa hoặc media type cụ thể |

Danh sách trên là nhóm từ khóa thường dùng, không phải toàn bộ JSON Schema 2020-12. Khi cần dùng vocabulary nâng cao, hãy kiểm tra dialect và mức hỗ trợ của validator, code generator và công cụ downstream.

## 7. type, enum và const

type giới hạn kiểu dữ liệu. JSON Schema 2020-12 có các kiểu cơ bản: object, array, string, number, integer, boolean và null.

~~~yaml
type: object
properties:
  quantity:
    type: integer
  unitPrice:
    type: number
  active:
    type: boolean
  note:
    type: [string, "null"]
~~~

type có thể là một chuỗi hoặc một mảng các kiểu được chấp nhận. Điều này hữu ích khi một trường có thể chứa nhiều kiểu, đặc biệt là null.

enum giới hạn giá trị vào một danh sách:

~~~yaml
status:
  type: string
  enum:
    - pending
    - paid
    - cancelled
~~~

const giới hạn một giá trị duy nhất:

~~~yaml
kind:
  const: physical
~~~

Không cần dùng enum chỉ có một phần tử nếu const thể hiện ý định rõ hơn. Cũng không nhầm const với default: const là ràng buộc giá trị; default chỉ là annotation mô tả giá trị mặc định dự kiến và không tự điền dữ liệu vào request.

## 8. Ràng buộc chuỗi và từ khóa format

Các từ khóa chuỗi thường dùng:

- minLength và maxLength giới hạn độ dài.
- pattern kiểm tra chuỗi theo biểu thức chính quy.
- format mô tả định dạng có ý nghĩa như date, date-time, email, uri hoặc uuid.
- contentEncoding và contentMediaType mô tả cách mã hóa và loại nội dung của chuỗi.

Ví dụ:

~~~yaml
email:
  type: string
  format: email
  maxLength: 254
code:
  type: string
  minLength: 3
  maxLength: 12
  pattern: "^[A-Z0-9]+$"
createdAt:
  type: string
  format: date-time
~~~

format cần được hiểu cẩn thận. Trong JSON Schema 2020-12, format mặc định thuộc vocabulary annotation; việc thực thi format như một assertion phụ thuộc vocabulary và cấu hình validator. Do đó, chỉ khai báo format: email không bảo đảm mọi runtime validator đều từ chối chuỗi email sai.

Nếu quy tắc định dạng là yêu cầu nghiệp vụ, hãy kiểm tra validator có bật format assertion hay bổ sung validation ở tầng ứng dụng. Không dùng format như một cơ chế xác thực duy nhất.

## 9. Ràng buộc số và exclusive bounds

Các từ khóa số phổ biến:

- minimum và maximum đặt ngưỡng bao gồm giá trị biên.
- exclusiveMinimum và exclusiveMaximum đặt ngưỡng loại trừ giá trị biên.
- multipleOf yêu cầu giá trị là bội số của một số cho trước.

Ví dụ theo JSON Schema 2020-12:

~~~yaml
price:
  type: number
  exclusiveMinimum: 0
  multipleOf: 0.01
quantity:
  type: integer
  minimum: 1
  maximum: 1000
discountRate:
  type: number
  minimum: 0
  maximum: 1
~~~

Trong ví dụ, price phải lớn hơn 0 và là bội số của 0.01. quantity nằm trong đoạn từ 1 đến 1000. discountRate chấp nhận cả 0 và 1.

So với OpenAPI 3.0, exclusiveMinimum và exclusiveMaximum đổi từ Boolean sang giá trị số. Không viết cú pháp cũ như:

~~~yaml
minimum: 0
exclusiveMinimum: true
~~~

trong schema 3.1. Cú pháp tương ứng là exclusiveMinimum: 0.

## 10. Mảng trong Draft 2020-12: items và prefixItems

Trong JSON Schema 2020-12, items mô tả schema áp dụng cho các phần tử còn lại của mảng. prefixItems mô tả schema theo vị trí cho một tuple.

Mảng đồng nhất:

~~~yaml
tags:
  type: array
  items:
    type: string
  minItems: 1
  uniqueItems: true
~~~

Tuple có phần tử theo vị trí:

~~~yaml
coordinates:
  type: array
  prefixItems:
    - type: number
    - type: number
  items: false
  minItems: 2
  maxItems: 2
~~~

Ở ví dụ thứ hai, phần tử đầu và thứ hai là số; items: false không cho phép phần tử bổ sung. minItems và maxItems buộc mảng có đúng hai phần tử.

Các từ khóa khác:

- contains yêu cầu có ít nhất một phần tử khớp schema con.
- minContains và maxContains giới hạn số phần tử khớp contains.
- unevaluatedItems kiểm soát các phần tử chưa được đánh giá sau khi áp dụng các schema liên quan.
- uniqueItems yêu cầu không có phần tử trùng nhau theo phép so sánh JSON Schema.

Không dùng cú pháp items dạng mảng của các draft JSON Schema cũ để mô tả tuple trong 2020-12. Hãy dùng prefixItems.

## 11. Đối tượng: properties và additionalProperties

Các từ khóa object thường gặp:

- properties định nghĩa schema cho thuộc tính có tên cụ thể.
- patternProperties áp dụng schema theo biểu thức chính quy của tên thuộc tính.
- required liệt kê tên thuộc tính bắt buộc.
- additionalProperties kiểm soát thuộc tính không được properties hoặc patternProperties mô tả.
- propertyNames kiểm tra tên của từng thuộc tính.
- minProperties và maxProperties giới hạn số lượng thuộc tính.

Ví dụ:

~~~yaml
type: object
properties:
  id:
    type: string
  name:
    type: string
    minLength: 1
required:
  - id
  - name
additionalProperties: false
~~~

Trong ví dụ, id và name là bắt buộc, và object không được chứa thuộc tính ngoài hai tên đã khai báo. Nếu không khai báo additionalProperties, JSON Schema mặc định cho phép thuộc tính bổ sung.

required là một danh sách tên thuộc tính ở cấp object, không phải cờ đặt riêng trên từng property. Đặt required bên trong schema con không làm thuộc tính của object cha trở thành bắt buộc.

## 12. dependentRequired và dependentSchemas

JSON Schema 2020-12 có thể mô tả sự phụ thuộc giữa các thuộc tính:

- dependentRequired yêu cầu một số thuộc tính khác phải có khi một thuộc tính được xuất hiện.
- dependentSchemas áp dụng một schema bổ sung khi thuộc tính kích hoạt có mặt.

Ví dụ dependentRequired:

~~~yaml
type: object
properties:
  paymentMethod:
    type: string
  cardToken:
    type: string
dependentRequired:
  paymentMethod:
    - cardToken
~~~

Nếu object có paymentMethod thì cardToken cũng phải có. Đây là quan hệ phụ thuộc một chiều theo khai báo; nếu cần chiều ngược lại, phải mô tả riêng.

Ví dụ dependentSchemas:

~~~yaml
type: object
properties:
  businessAccount:
    type: boolean
dependentSchemas:
  businessAccount:
    properties:
      taxCode:
        type: string
    required:
      - taxCode
~~~

Khi businessAccount xuất hiện, schema phụ được áp dụng và yêu cầu taxCode. Cần nhớ điều kiện của dependentSchemas dựa trên sự hiện diện của property, không dựa trên giá trị true/false của property đó.

## 13. unevaluatedProperties và unevaluatedItems

additionalProperties chỉ xét các property được đánh giá trong schema object hiện tại. Khi dùng composition như allOf hoặc $ref, có thể cần kiểm soát các thuộc tính chưa được đánh giá trên toàn bộ kết quả kết hợp. JSON Schema 2020-12 cung cấp unevaluatedProperties và unevaluatedItems cho trường hợp này.

Ví dụ:

~~~yaml
type: object
allOf:
  - properties:
      id:
        type: string
    required:
      - id
  - properties:
      name:
        type: string
    required:
      - name
unevaluatedProperties: false
~~~

Schema yêu cầu id và name qua hai nhánh allOf, đồng thời từ chối thuộc tính còn lại chưa được đánh giá. Điều này thường phù hợp hơn việc đặt additionalProperties: false trong một nhánh con khi các property hợp lệ được khai báo ở nhánh khác.

unevaluatedProperties và unevaluatedItems phụ thuộc cơ chế theo dõi kết quả đánh giá của JSON Schema. Một số công cụ tạo mã hoặc validator cũ có thể chưa hỗ trợ đầy đủ; cần thử bằng đúng công cụ dự kiến sử dụng.

## 14. Kết hợp schema bằng allOf, anyOf, oneOf và not

Các từ khóa composition cho phép xây dựng schema từ nhiều schema nhỏ:

| Từ khóa | Ý nghĩa |
|---|---|
| allOf | Dữ liệu phải hợp lệ với tất cả schema con |
| anyOf | Dữ liệu phải hợp lệ với ít nhất một schema con |
| oneOf | Dữ liệu phải hợp lệ với đúng một schema con |
| not | Dữ liệu không được hợp lệ với schema con |

Ví dụ:

~~~yaml
Payment:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransfer'
~~~

oneOf yêu cầu dữ liệu khớp đúng một trong hai schema. Nếu một payload đồng thời khớp cả CardPayment và BankTransfer, payload đó không hợp lệ với oneOf. Nếu ý định chỉ là khớp ít nhất một loại, hãy cân nhắc anyOf.

allOf thường được dùng để ghép các ràng buộc hoặc mô hình nền. Tuy nhiên, allOf không phải lúc nào cũng tương đương kế thừa class trong Java. Nó là phép giao của các schema: dữ liệu phải đáp ứng mọi nhánh.

## 15. if, then và else

JSON Schema 2020-12 hỗ trợ schema có điều kiện:

~~~yaml
type: object
properties:
  accountType:
    type: string
    enum:
      - personal
      - business
  taxCode:
    type: string
if:
  properties:
    accountType:
      const: business
  required:
    - accountType
then:
  required:
    - taxCode
else:
  properties:
    taxCode:
      not: {}
~~~

Nếu accountType là business thì taxCode là bắt buộc. Nhánh else ở đây cấm taxCode với mọi giá trị. Nếu nghiệp vụ chỉ muốn bỏ qua taxCode thay vì cấm, không cần thêm ràng buộc ở else.

Khi dùng if, nên đặt required cho property điều kiện trong schema if nếu muốn phân biệt trường hợp property bị thiếu. Nếu chỉ dùng properties với const mà không yêu cầu property có mặt, schema if có thể vẫn hợp lệ khi object không chứa property đó.

## 16. Các từ khóa annotation và từ khóa riêng của OpenAPI

Không phải từ khóa nào trong Schema Object cũng dùng để từ chối payload. Nhiều từ khóa chỉ cung cấp thông tin cho tài liệu hoặc công cụ.

| Từ khóa | Vai trò thường gặp |
|---|---|
| title, description | Mô tả schema |
| default | Giá trị mặc định được mô tả |
| examples | Các ví dụ dữ liệu theo JSON Schema |
| deprecated | Đánh dấu schema hoặc property đã lỗi thời |
| readOnly | Property chủ yếu được trả về trong response |
| writeOnly | Property chủ yếu được gửi trong request |
| xml | Metadata cho biểu diễn XML trong OpenAPI |
| externalDocs | Liên kết tài liệu bên ngoài |
| discriminator | Hỗ trợ chọn subtype trong mô hình đa hình OpenAPI |
| example | Từ khóa OAS cũ trong Schema Object; đã deprecated trong OAS 3.1 để ưu tiên examples |

default không tự điền giá trị vào request hoặc sửa dữ liệu. readOnly và writeOnly giúp mô tả hướng dữ liệu, nhưng không tự thay thế logic bảo vệ dữ liệu nhạy cảm ở server. Ví dụ, đánh dấu password là writeOnly không bảo đảm server sẽ không trả password nếu DTO hoặc serializer vẫn xuất trường đó.

Trong JSON Schema, examples là annotation chứa một mảng ví dụ. Ở Media Type Object của OpenAPI, thuộc tính examples lại là map các ví dụ có tên và có cấu trúc riêng. Không nhầm hai vị trí này.

## 17. format là annotation hay assertion?

format thường biểu diễn định dạng có ý nghĩa của dữ liệu, ví dụ:

~~~yaml
birthDate:
  type: string
  format: date
website:
  type: string
  format: uri
traceId:
  type: string
  format: uuid
~~~

Theo JSON Schema 2020-12, vocabulary format-annotation là phần mặc định; format-assertion là vocabulary riêng và có thể được triển khai tùy chọn. Vì vậy, một validator có thể chấp nhận chuỗi không đúng định dạng dù schema có format: date-time.

Khi cần kiểm tra chặt:

1. Xác định validator dùng để kiểm tra payload.
2. Xác minh validator hỗ trợ format assertion hoặc bật chế độ tương ứng.
3. Kiểm tra các format cần thiết có được triển khai.
4. Bổ sung kiểm thử với giá trị đúng và sai.
5. Giữ validation runtime của ứng dụng nhất quán với hợp đồng OpenAPI.

Đừng giả định Swagger UI hoặc mọi code generator sẽ thực thi format như một bộ kiểm tra dữ liệu.

## 18. Null trong OpenAPI 3.1

OpenAPI 3.1 dùng mô hình JSON Schema cho null. Thay vì dùng nullable: true như trong OAS 3.0, có thể khai báo:

~~~yaml
middleName:
  type:
    - string
    - "null"
~~~

Hoặc dùng composition:

~~~yaml
middleName:
  anyOf:
    - type: string
    - type: "null"
~~~

Một enum cũng có thể chứa null:

~~~yaml
status:
  type:
    - string
    - "null"
  enum:
    - active
    - inactive
    - null
~~~

nullable không phải từ khóa JSON Schema 2020-12 chuẩn. Khi chuyển schema từ 3.0 sang 3.1, hãy chuyển ý nghĩa nullable sang type union hoặc composition phù hợp. Không để cả nullable: true và type union một cách máy móc rồi cho rằng mọi công cụ sẽ diễn giải giống nhau.

## 19. $id, $ref, $anchor và $defs

Các từ khóa định danh và tham chiếu giúp tái sử dụng schema:

- $id định danh schema resource và ảnh hưởng base URI dùng để giải quyết tham chiếu tương đối.
- $ref tham chiếu đến một schema khác bằng URI.
- $anchor đặt tên điểm neo trong schema resource.
- $defs chứa các subschema có thể được tham chiếu lại.
- $dynamicAnchor và $dynamicRef hỗ trợ tham chiếu động trong một số schema đệ quy hoặc mở rộng.

Ví dụ dùng $defs:

~~~yaml
$defs:
  Identifier:
    type: string
    minLength: 1
type: object
properties:
  id:
    $ref: '#/$defs/Identifier'
  parentId:
    $ref: '#/$defs/Identifier'
~~~

Trong OpenAPI, components.schemas cũng là nơi phổ biến để định nghĩa schema dùng chung:

~~~yaml
components:
  schemas:
    ProductId:
      type: string
      minLength: 1
~~~

Sau đó tham chiếu bằng:

~~~yaml
schema:
  $ref: '#/components/schemas/ProductId'
~~~

$defs thường hữu ích cho cấu trúc nội bộ của một schema resource. components.schemas phù hợp với các mô hình dùng chung ở cấp OpenAPI document, được tham chiếu từ request, response hoặc nhiều operation.

## 20. $ref và các sibling trong OpenAPI 3.1

Trong Schema Object, $ref là từ khóa JSON Schema. Theo ngữ nghĩa JSON Schema 2020-12, các từ khóa sibling bên cạnh $ref vẫn có thể được áp dụng:

~~~yaml
schema:
  $ref: '#/components/schemas/Product'
  description: Sản phẩm được trả về trong danh sách.
~~~

Điều này khác với cách nhiều người quen xử lý Reference Object của OpenAPI 3.0, nơi các thuộc tính sibling của $ref thường bị bỏ qua hoặc không có cùng ngữ nghĩa. Cần phân biệt:

- $ref nằm trong Schema Object: tuân theo ngữ nghĩa JSON Schema của dialect đang dùng.
- Reference Object ở những vị trí OpenAPI khác: tuân theo quy tắc Reference Object của phiên bản OpenAPI.

Không kết luận mọi nơi có $ref đều xử lý sibling giống nhau. Hãy xác định vị trí cấu trúc của $ref trước khi viết description, summary hoặc các trường bổ sung bên cạnh nó.

## 21. Ví dụ hợp đồng OpenAPI 3.1 hoàn chỉnh

Ví dụ sau dùng dialect mặc định của OAS 3.1, schema nullable, ràng buộc số và schema dùng chung:

~~~yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
info:
  title: Store API
  version: 1.0.0
paths:
  /api/orders:
    post:
      operationId: createOrder
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
      responses:
        '201':
          description: Đơn hàng đã được tạo.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
components:
  schemas:
    CreateOrder:
      type: object
      additionalProperties: false
      properties:
        customerId:
          type: string
          minLength: 1
        note:
          type:
            - string
            - "null"
          maxLength: 500
        items:
          type: array
          minItems: 1
          items:
            $ref: '#/components/schemas/OrderLine'
      required:
        - customerId
        - items
    OrderLine:
      type: object
      additionalProperties: false
      properties:
        productId:
          type: string
        quantity:
          type: integer
          minimum: 1
        unitPrice:
          type: number
          exclusiveMinimum: 0
      required:
        - productId
        - quantity
        - unitPrice
    Order:
      allOf:
        - $ref: '#/components/schemas/CreateOrder'
        - type: object
          properties:
            id:
              type: string
            createdAt:
              type: string
              format: date-time
          required:
            - id
            - createdAt
~~~

Đây là ví dụ minh họa cấu trúc hợp đồng. Trong ứng dụng thực tế, kiểm tra schema sau khi springdoc sinh ra, đặc biệt nếu schema đến từ DTO, Jackson annotation hoặc Bean Validation. Không giả định annotation Java tự sinh chính xác mọi từ khóa JSON Schema nâng cao.

## 22. Ảnh hưởng tới Springdoc và validation runtime

springdoc tạo tài liệu OpenAPI từ controller, DTO, annotation Swagger và một phần metadata framework như Jackson hoặc Bean Validation. Khả năng biểu diễn từ khóa JSON Schema phụ thuộc phiên bản springdoc, swagger-core và cách mô hình dữ liệu được khai báo.

Điểm cần phân biệt:

- OpenAPI Schema mô tả hợp đồng mà client nên tuân theo.
- Spring Bean Validation kiểm tra các constraint được khai báo và được kích hoạt trong luồng xử lý.
- Jackson kiểm soát quá trình serialize/deserialize JSON.
- JSON Schema validator kiểm tra instance theo dialect và vocabulary được hỗ trợ.

Khai báo một từ khóa trong OpenAPI không tự khiến Spring MVC hoặc WebFlux thực thi quy tắc đó. Ví dụ, unevaluatedProperties: false trong tài liệu không tự chặn property lạ nếu runtime không có validator thực thi schema đó.

Nếu cần ràng buộc dữ liệu tại server, dùng validation phù hợp như jakarta.validation với @Valid, constraint tùy chỉnh hoặc JSON Schema validator được tích hợp rõ ràng. Sau đó kiểm tra rằng hợp đồng OpenAPI mô tả cùng quy tắc với runtime.

## 23. Kiểm tra công cụ downstream và dialect

Một tài liệu có thể hợp lệ theo OAS 3.1 nhưng công cụ downstream vẫn chỉ hỗ trợ một phần JSON Schema 2020-12. Những khu vực cần kiểm tra kỹ gồm:

- prefixItems và tuple array.
- unevaluatedProperties và unevaluatedItems.
- dependentSchemas và dependentRequired.
- $dynamicRef và $dynamicAnchor.
- if/then/else.
- format assertion.
- $ref sibling và URI resolution.
- OAS vocabulary như discriminator, xml và readOnly/writeOnly.

Trước khi dùng từ khóa nâng cao trong API công khai, hãy kiểm tra:

1. Phiên bản OpenAPI và jsonSchemaDialect của document.
2. Validator có hỗ trợ dialect và vocabulary tương ứng không.
3. Swagger UI có render schema đúng không.
4. Code generator có tạo kiểu dữ liệu và validation mong đợi không.
5. Gateway, contract testing tool hoặc API catalog có giữ nguyên từ khóa không.
6. Pipeline có kiểm tra payload hợp lệ và không hợp lệ theo đúng dialect không.

Không dùng một validator JSON Schema cũ để kết luận schema 2020-12 sai. Ngược lại, cũng không kết luận schema đúng chỉ vì parser OpenAPI chấp nhận document: parser có thể chỉ kiểm tra cấu trúc OpenAPI mà không thực thi toàn bộ ràng buộc JSON Schema trên payload.

## 24. Quy trình xác minh schema 3.1

Một quy trình kiểm tra thực tế:

1. Xác nhận document có trường openapi thuộc dòng 3.1.x.
2. Kiểm tra jsonSchemaDialect; nếu bỏ trống, ghi nhận OAS base dialect mặc định.
3. Tìm các schema resource có $schema để xác định override.
4. Đối chiếu các từ khóa được dùng với JSON Schema Draft 2020-12.
5. Kiểm tra nullable đã được chuyển thành type null hoặc composition.
6. Kiểm tra exclusiveMinimum/exclusiveMaximum dùng giá trị số.
7. Kiểm tra tuple array dùng prefixItems thay vì items dạng mảng cũ.
8. Kiểm tra $ref, $id, $anchor, $defs và URI base resolution.
9. Chạy OpenAPI validator để xác minh cấu trúc document.
10. Chạy JSON Schema validator tương thích dialect để kiểm tra payload.
11. Kiểm tra format assertion nếu nghiệp vụ phụ thuộc định dạng.
12. Thử Swagger UI và code generator được dùng trong dự án.
13. So sánh OpenAPI document trước và sau khi thay đổi DTO hoặc dependency.

Khi kiểm tra payload, chuẩn bị cả trường hợp hợp lệ và không hợp lệ. Ví dụ với quantity có minimum 1, cần xác minh 1 được chấp nhận và 0 bị từ chối. Với additionalProperties: false, cần thử object có thuộc tính không khai báo. Với oneOf, thử cả payload khớp đúng một nhánh và payload khớp nhiều nhánh.

## 25. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Nhầm openapi với jsonSchemaDialect | Chọn sai cách diễn giải Schema Object | Kiểm tra riêng version OpenAPI và dialect |
| Mang nullable: true từ OAS 3.0 sang 3.1 | Validator JSON Schema có thể bỏ qua hoặc xử lý khác | Dùng type union có null hoặc composition |
| Dùng exclusiveMinimum dạng Boolean | Không đúng kiểu dữ liệu của Draft 2020-12 | Đặt exclusiveMinimum bằng ngưỡng số |
| Dùng items dạng mảng để mô tả tuple | Dùng cú pháp của draft cũ | Chuyển các schema theo vị trí sang prefixItems |
| Dùng additionalItems trong schema 2020-12 | Công cụ có thể không hiểu ý định tuple | Dùng prefixItems, items và unevaluatedItems phù hợp |
| Nghĩ format luôn được kiểm tra | Payload sai định dạng vẫn có thể được chấp nhận | Kiểm tra format-assertion và runtime validation |
| Dùng default như giá trị tự điền | Client hoặc server không tự động nhận giá trị đó | Xử lý default ở ứng dụng nếu cần |
| Đặt required bên trong property | Object cha không được ràng buộc như dự kiến | Đặt required ở schema object chứa property |
| Dùng additionalProperties: false trong từng nhánh allOf | Property được khai báo ở nhánh khác có thể bị từ chối | Xem xét unevaluatedProperties ở schema kết hợp |
| Nhầm $defs với components.schemas | Tham chiếu không đúng vị trí | Dùng đúng JSON Pointer cho từng vùng |
| Cho rằng mọi $ref sibling đều có cùng quy tắc | Mô tả hoặc metadata bị bỏ qua | Phân biệt Schema Object với Reference Object |
| Tài liệu hợp lệ nhưng runtime không từ chối payload sai | Schema chỉ là hợp đồng, chưa có validator runtime | Tích hợp Bean Validation hoặc JSON Schema validator |
| Code generator bỏ qua từ khóa mới | Client model không phản ánh ràng buộc | Kiểm tra hỗ trợ 2020-12 hoặc chọn chiến lược tương thích |

## 26. Ghi nhớ

- openapi xác định phiên bản OpenAPI; jsonSchemaDialect xác định dialect mặc định của Schema Object.
- OAS 3.1 mặc định dùng https://spec.openapis.org/oas/3.1/dialect/base.
- $schema tại gốc của schema resource có thể ghi đè dialect mặc định.
- Schema Object OAS 3.1 dựa trên JSON Schema Draft 2020-12 và có vocabulary riêng của OpenAPI.
- Dùng type, enum và const để giới hạn kiểu và giá trị.
- format mặc định chủ yếu là annotation; cần xác minh format assertion nếu muốn validator từ chối dữ liệu sai.
- Dùng type có null thay cho nullable: true khi viết schema 3.1.
- Dùng prefixItems cho tuple array; items mô tả các phần tử còn lại.
- exclusiveMinimum và exclusiveMaximum nhận giá trị số trong Draft 2020-12.
- dependentRequired, dependentSchemas, unevaluatedProperties, if/then/else và composition giúp mô tả quy tắc phức tạp.
- Phân biệt $defs nội bộ với components.schemas ở cấp OpenAPI.
- $ref trong Schema Object có ngữ nghĩa JSON Schema; Reference Object ở vị trí OpenAPI khác có quy tắc riêng.
- OpenAPI document hợp lệ không chứng minh runtime tự thực thi mọi keyword JSON Schema.
- Kiểm tra dialect, validator, Swagger UI, code generator và payload mẫu trước khi công bố hợp đồng.

Khi dùng OpenAPI 3.1, hãy xác định dialect trước rồi mới đánh giá các từ khóa trong Schema Object. Đối chiếu cú pháp với JSON Schema 2020-12, chuyển đúng những khác biệt từ OpenAPI 3.0 và kiểm tra công cụ downstream có hỗ trợ vocabulary được dùng hay không. Cuối cùng, xác minh hợp đồng được sinh ra và validation runtime bằng các payload thực tế.
