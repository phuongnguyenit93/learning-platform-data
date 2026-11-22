# Không nâng trường openapi đơn thuần khi nội dung chưa được chuyển đổi đúng

Trường `openapi` ở đầu tài liệu cho biết tài liệu tuân theo phiên bản nào của **OpenAPI Specification (OAS)**. Nó không tự chuyển đổi cấu trúc bên dưới, không thay đổi hợp đồng API đang chạy và cũng không phải số phiên bản phát hành của API. Vì vậy, khi nâng một tài liệu từ OpenAPI 3.0 lên 3.1, chỉ sửa `openapi: 3.0.3` thành `openapi: 3.1.2` có thể khiến tài liệu mang nhãn phiên bản mới nhưng vẫn chứa Schema Object theo quy tắc cũ.

Điểm khác biệt quan trọng nằm ở Schema Object: OpenAPI 3.1 đồng bộ với JSON Schema Draft 2020-12, trong khi OpenAPI 3.0 dùng một tập con JSON Schema đã được điều chỉnh riêng. Một số từ khóa đổi cách biểu diễn và một số cách mô tả dữ liệu không còn đúng theo 3.1. Cần chuyển đổi nội dung, xác thực lại tài liệu và kiểm tra các công cụ tiêu thụ trước khi phát hành.

## 1. Hiểu đúng các trường phiên bản

Một OpenAPI document có nhiều thông tin phiên bản với ý nghĩa khác nhau:

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| `openapi` | `3.1.2` | Phiên bản OpenAPI Specification mà tài liệu tuân theo |
| `info.version` | `2026.4` hoặc `2.7.0` | Phiên bản của chính OpenAPI document |
| Phiên bản API triển khai | `v1`, `v2` trong path hoặc chính sách phát hành | Phiên bản hợp đồng/API mà hệ thống cung cấp; được tổ chức quản lý theo quy ước riêng |
| Phiên bản springdoc | `2.x`, `3.x` | Phiên bản thư viện tạo tài liệu, phụ thuộc dòng Spring Boot |

Theo đặc tả, `openapi` và `info.version` không thay thế cho nhau. `openapi` giúp công cụ chọn đúng quy tắc phân tích tài liệu; `info.version` nhận diện phiên bản của document. `info.version` cũng không tự quyết định URL `/v1` hay `/v2`, không nâng version của server và không tự báo hiệu một thay đổi tương thích của API.

Ví dụ:

~~~yaml
openapi: 3.1.2
info:
  title: Customer API
  version: 2.4.0
servers:
  - url: https://api.example.com/v2
paths:
  /customers:
    get:
      responses:
        '200':
          description: Danh sách khách hàng
~~~

Trong ví dụ, `3.1.2` là phiên bản đặc tả; `2.4.0` là phiên bản document do nhóm phát hành; `/v2` là version trong base path của API. Ba giá trị có thể thay đổi độc lập theo chính sách quản lý sản phẩm.

## 2. Phiên bản OpenAPI dùng major, minor và patch

OpenAPI dùng cách đánh số `major.minor.patch`. Phần major/minor xác định tập tính năng của đặc tả; phần patch chủ yếu sửa lỗi hoặc làm rõ nội dung, không bổ sung tập tính năng mới. Vì vậy, các bản vá trong cùng dòng như 3.1.0, 3.1.1 và 3.1.2 vẫn thuộc feature set 3.1.

Tại thời điểm biên soạn, các dòng đặc tả liên quan gồm:

| Dòng | Ý nghĩa chuyển đổi |
|---|---|
| OpenAPI 2.0 | Định dạng cũ dùng trường gốc `swagger: '2.0'` |
| OpenAPI 3.0.x | Schema Object dựa trên tập từ khóa JSON Schema được điều chỉnh cho OAS 3.0 |
| OpenAPI 3.1.x | Đồng bộ Schema Object với JSON Schema Draft 2020-12; có thay đổi cần chuyển đổi khi đi từ 3.0 |
| OpenAPI 3.2.x | Bổ sung tính năng mới trên nền 3.1; hướng dẫn chính thức mô tả 3.1→3.2 là tương thích ngược |

OpenAPI 3.2.1 là bản đặc tả mới nhất tại thời điểm biên soạn. Đây là bản patch của dòng 3.2. Khi chọn target version, cần phân biệt việc nâng patch trong cùng feature set với việc chuyển sang một minor release có thêm quy tắc và khả năng mới.

## 3. Vì sao chuyển từ 3.0 lên 3.1 cần sửa Schema Object?

OpenAPI 3.0 không sử dụng toàn bộ ngữ nghĩa JSON Schema hiện đại. Nó định nghĩa một Schema Object riêng với một số từ khóa và quy tắc khác JSON Schema. OpenAPI 3.1 đưa Schema Object về gần JSON Schema Draft 2020-12, đồng thời bổ sung vocabulary riêng của OpenAPI.

Điều này có lợi vì schema có thể diễn tả nhiều trường hợp dữ liệu hơn và tương thích tốt hơn với hệ sinh thái JSON Schema. Tuy nhiên, công cụ đọc tài liệu 3.0 có thể không hiểu các từ khóa mới, còn tài liệu 3.1 vẫn chứa từ khóa cũ có thể không còn đúng nghĩa.

Một phép thay thế chuỗi ở trường đầu tài liệu không thực hiện các việc sau:

- Chuyển `nullable` thành kiểu dữ liệu chứa `null`.
- Chuyển cách biểu diễn `exclusiveMinimum` và `exclusiveMaximum`.
- Phân biệt `example` trong Schema Object với `example` của Media Type Object.
- Chuyển mô tả file/binary sang cách biểu diễn phù hợp với JSON Schema.
- Khai báo hoặc kiểm tra JSON Schema dialect khi tài liệu dùng schema bên ngoài.
- Xác nhận validator, Swagger UI, code generator và API gateway hiểu feature set mới.

## 4. Chuyển nullable sang kiểu dữ liệu có null

Trong OpenAPI 3.0, thuộc tính `nullable: true` được dùng để cho phép giá trị `null`:

~~~yaml
CustomerName:
  type: string
  nullable: true
~~~

Trong OpenAPI 3.1, dùng từ khóa `type` với danh sách kiểu dữ liệu, trong đó có `null`:

~~~yaml
CustomerName:
  type:
    - string
    - 'null'
~~~

Với property trong object:

~~~yaml
Customer:
  type: object
  properties:
    displayName:
      type:
        - string
        - 'null'
    email:
      type: string
~~~

`displayName` có thể nhận chuỗi hoặc `null`; `email` vẫn chỉ nhận chuỗi. Nếu property không nằm trong danh sách `required`, property còn có thể vắng mặt. Cần phân biệt hai trạng thái:

- **Optional:** client có thể không gửi property.
- **Nullable:** property có thể xuất hiện với giá trị `null`.

Hai khái niệm này không giống nhau. Chỉ thêm `null` vào type khi hợp đồng runtime thực sự chấp nhận giá trị null.

### Trường hợp schema tham chiếu bằng $ref

Với một schema được tái sử dụng, cách biểu diễn nullable trong 3.1 có thể dùng `anyOf` để kết hợp component với nhánh `null`:

~~~yaml
properties:
  billingAddress:
    anyOf:
      - $ref: '#/components/schemas/Address'
      - type: 'null'
~~~

Trong OpenAPI 3.0, `nullable` chỉ có tác dụng khi `type` được khai báo tường minh trong cùng Schema Object. Vì vậy, không thể giả định rằng chỉ cần đặt `nullable: true` bên cạnh một `$ref` là reference trở thành nullable. Khi migration schema có composition hoặc reference, hãy đọc lại cấu trúc 3.0 thực tế rồi biểu diễn union phù hợp trong 3.1.

Không sửa component `Address` thành nullable nếu chỉ riêng property `billingAddress` cho phép null; việc đó có thể làm thay đổi ngữ nghĩa ở mọi nơi tham chiếu `Address`.

## 5. Chuyển exclusiveMinimum và exclusiveMaximum

Trong OpenAPI 3.0, hai từ khóa này là boolean bổ sung ý nghĩa cho `minimum` và `maximum`:

~~~yaml
age:
  type: integer
  minimum: 18
  exclusiveMinimum: true
~~~

Nghĩa là giá trị phải lớn hơn 18, không chấp nhận 18.

Trong OpenAPI 3.1, `exclusiveMinimum` nhận trực tiếp ngưỡng số:

~~~yaml
age:
  type: integer
  exclusiveMinimum: 18
~~~

Tương tự, chuyển:

~~~yaml
price:
  type: number
  maximum: 100
  exclusiveMaximum: true
~~~

thành:

~~~yaml
price:
  type: number
  exclusiveMaximum: 100
~~~

Nếu `exclusiveMinimum` hoặc `exclusiveMaximum` trong tài liệu 3.0 là `false`, giữ lại `minimum` hoặc `maximum` tương ứng và bỏ cờ boolean. Không được thay mọi giá trị boolean thành số một cách máy móc; cần đọc cả cặp từ khóa để giữ đúng ranh giới bao gồm hay loại trừ.

## 6. Chuyển example trong Schema Object sang examples

Trong OpenAPI 3.0, Schema Object có thể dùng `example`:

~~~yaml
CustomerStatus:
  type: string
  enum:
    - ACTIVE
    - SUSPENDED
  example: ACTIVE
~~~

Trong OpenAPI 3.1, dùng từ khóa JSON Schema `examples` với giá trị dạng mảng:

~~~yaml
CustomerStatus:
  type: string
  enum:
    - ACTIVE
    - SUSPENDED
  examples:
    - ACTIVE
    - SUSPENDED
~~~

Trong OAS 3.1, trường `example` cũ trong Schema Object vẫn được giữ để tương thích nhưng đã bị đánh dấu deprecated; `examples` là cách được ưu tiên theo JSON Schema. Vì vậy, chuyển sang `examples` là bước migration nên làm khi chuẩn hóa schema 3.1, nhưng cần hiểu đây là thay đổi được khuyến nghị thay vì cho rằng mọi validator 3.1 đều bắt buộc từ chối `example` cũ.

Có một điểm rất dễ gây lỗi khi chuyển đổi: không phải mọi trường `example` trong OpenAPI 3.0 đều cần đổi thành mảng `examples`.

| Vị trí | Cách xử lý khi chuyển 3.0→3.1 |
|---|---|
| Schema Object | Chuyển `example` sang JSON Schema `examples` dạng mảng |
| Media Type Object trong `requestBody`/`responses` | `example` và `examples` vẫn là các trường của Media Type Object; giữ đúng cấu trúc object tương ứng |
| Example Object được tham chiếu bằng `$ref` | Giữ cấu trúc Example Object; không biến nó thành mảng JSON Schema |

Ví dụ `examples` ở Media Type Object là một map có tên:

~~~yaml
content:
  application/json:
    examples:
      standard:
        summary: Khách hàng thông thường
        value:
          name: An
      corporate:
        summary: Khách hàng doanh nghiệp
        value:
          name: Công ty Minh Phát
~~~

Đây không phải cấu trúc mảng `examples` trong Schema Object. Hãy xác định vị trí của từ khóa trước khi chuyển đổi.

## 7. Cập nhật mô tả file và dữ liệu binary

OpenAPI 3.0 thường mô tả file upload bằng `type: string` và `format: binary`:

~~~yaml
requestBody:
  required: true
  content:
    application/octet-stream:
      schema:
        type: string
        format: binary
~~~

OpenAPI 3.1 dùng các khái niệm JSON Schema như `contentEncoding` và `contentMediaType` để mô tả nội dung được mã hóa và media type. Với body truyền trực tiếp bằng `application/octet-stream`, tài liệu migration minh họa:

~~~yaml
requestBody:
  required: true
  content:
    application/octet-stream: {}
~~~

Với chuỗi Base64:

~~~yaml
schema:
  type: string
  contentEncoding: base64
  contentMediaType: image/png
~~~

Với một phần file trong multipart:

~~~yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        properties:
          file:
            type: string
            contentMediaType: application/octet-stream
~~~

Không chuyển tất cả `format: binary` thành cùng một schema rỗng hoặc cùng `contentEncoding`. Cần xác định dữ liệu thực tế là luồng byte thô, chuỗi Base64 hay một phần multipart có media type riêng. Kiểm tra cách client serializer gửi payload và cách server nhận file để bảo đảm tài liệu phản ánh đúng wire format.

## 8. JSON Schema dialect và từ khóa mới

OpenAPI 3.1 hỗ trợ khai báo dialect mặc định cho Schema Object bằng `jsonSchemaDialect`. Nếu không chỉ định, OAS 3.1 dùng dialect nền tảng của chính OpenAPI 3.1, dựa trên JSON Schema Draft 2020-12 và vocabulary của OpenAPI.

Ví dụ khai báo tường minh:

~~~yaml
openapi: 3.1.2
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
info:
  title: Customer API
  version: 2.4.0
paths: {}
components:
  schemas:
    CustomerFilter:
      type: object
      properties:
        age:
          type: integer
          minimum: 0
~~~

Không cần thêm `jsonSchemaDialect` nếu chỉ dùng dialect mặc định. Trường này hữu ích khi nhóm muốn công bố rõ dialect hoặc có quy tắc schema đặc biệt. Nếu dùng schema bên ngoài, có thể khai báo `$schema` ở schema document đó để xác định dialect của nó.

Khi đã dùng 3.1, schema có thể sử dụng các từ khóa JSON Schema 2020-12 như `if`, `then`, `else`, `prefixItems`, `contains` và các từ khóa khác phù hợp với mô hình dữ liệu. Tuy nhiên, chỉ nên dùng khi validator, renderer và code generator trong pipeline hiểu chúng. Một tài liệu hợp lệ theo đặc tả nhưng bị toolchain cũ bỏ qua từ khóa vẫn có thể tạo ra SDK hoặc tài liệu sai.

## 9. Ví dụ chuyển đổi Schema Object hoàn chỉnh

Giả sử tài liệu 3.0 đang mô tả khách hàng:

~~~yaml
openapi: 3.0.3
info:
  title: Customer API
  version: 2.4.0
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
          example: Nguyen An
        age:
          type: integer
          minimum: 18
          exclusiveMinimum: true
~~~

Sau khi chuyển sang 3.1.2:

~~~yaml
openapi: 3.1.2
info:
  title: Customer API
  version: 2.4.0
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
          type:
            - string
            - 'null'
          examples:
            - Nguyen An
        age:
          type: integer
          exclusiveMinimum: 18
~~~

Ví dụ này minh họa các thay đổi schema chính. Cách mô tả file cần được xử lý riêng theo đúng media type và cách truyền dữ liệu thực tế như đã trình bày ở phần trước.

## 10. Chuyển từ OpenAPI 2.0 cần một bước khác

Tài liệu OpenAPI 2.0 dùng trường gốc:

~~~yaml
swagger: '2.0'
~~~

Không đổi trường này thành:

~~~yaml
openapi: 3.1.2
~~~

OpenAPI 2.0 và OpenAPI 3.x khác nhau ở cấu trúc request body, response content, server, security và nhiều thành phần khác. Cần chuyển tài liệu Swagger 2.0 sang OpenAPI 3.0 trước, sau đó thực hiện migration 3.0→3.1.

Có thể dùng công cụ chuyển đổi như `swagger2openapi` để tạo bản nháp OpenAPI 3.0. Sau chuyển đổi, vẫn cần kiểm tra các nội dung không thể suy ra hoàn toàn từ tài liệu cũ, chẳng hạn server URL, media type, schema, security và các extension riêng.

## 11. Chuyển từ OpenAPI 3.1 lên 3.2 có gì khác?

Không phải mọi lần nâng phiên bản đều cần một đợt sửa Schema Object như 3.0→3.1. Hướng dẫn migration của OpenAPI Initiative mô tả chuyển từ 3.1 lên 3.2 là tương thích ngược: tài liệu 3.1 hiện có có thể tiếp tục hoạt động khi cập nhật trường phiên bản lên 3.2, với điều kiện tài liệu thực sự hợp lệ và toolchain hỗ trợ 3.2.

Tại thời điểm biên soạn, bản mới nhất là 3.2.1. Một quy trình nâng từ 3.1 lên 3.2 có thể bắt đầu bằng:

~~~yaml
openapi: 3.2.1
~~~

Nhưng chỉ thực hiện khi validator, Swagger UI/renderer, code generator, API gateway và các hệ thống tiêu thụ đã hỗ trợ 3.2. Nếu muốn dùng tính năng mới của 3.2, cần bổ sung cấu trúc tương ứng và kiểm tra từng consumer.

Một số khả năng mới trong 3.2 gồm:

- Tag phân cấp với `parent`, phân loại `kind` và nhãn `summary`.
- HTTP method `QUERY` và các operation bổ sung.
- Vị trí parameter `querystring`.
- Mô tả dữ liệu tuần tự/streaming với `itemSchema` và các media type như `application/jsonl`, `application/json-seq`.
- OAuth 2.0 Device Authorization flow và metadata liên quan.
- Cải tiến discriminator và ví dụ dữ liệu.

Nếu tài liệu chỉ dùng tính năng 3.1 và toàn bộ toolchain đã hỗ trợ 3.2, cập nhật phiên bản có thể là bước hợp lý. Nếu tài liệu đang chuyển từ 3.0, không được áp dụng lập luận này để bỏ qua các thay đổi bắt buộc của Schema Object 3.1.

## 12. Cấu hình phiên bản OpenAPI được springdoc sinh ra

Khi springdoc tạo OpenAPI document từ controller Spring Boot, có thể chọn phiên bản đặc tả bằng thuộc tính:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Hoặc chọn OpenAPI 3.0:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Theo tài liệu cấu hình springdoc hiện hành, `springdoc.api-docs.version` chọn OpenAPI 3.0 hoặc 3.1; mặc định được công bố là `openapi_3_1`. Cấu hình này điều khiển phiên bản đặc tả mà springdoc sinh ra từ ứng dụng.

Điểm cần nhớ:

- Đây là cấu hình cho document được springdoc sinh, không phải một bộ chuyển đổi bất kỳ file OpenAPI tĩnh.
- Đổi giá trị sang 3.1 không tự đảm bảo annotation, customizer hoặc schema tùy chỉnh của ứng dụng đã đúng theo JSON Schema 2020-12.
- Tài liệu thuộc tính springdoc hiện công bố lựa chọn 3.0 và 3.1; không tự đặt `OPENAPI_3_2` hoặc sửa output thành `openapi: 3.2.1` khi thư viện chưa công bố hỗ trợ.
- Nếu hệ thống cần OpenAPI 3.2, cần xác minh phiên bản springdoc và thư viện swagger-core đi kèm có hỗ trợ chính thức trước khi thiết kế pipeline phát hành 3.2.

Sau khi đổi cấu hình, lấy lại `/v3/api-docs` và kiểm tra trường `openapi`, Schema Object, request body, response, security và các component. Không chỉ xác nhận rằng dòng đầu tài liệu đã đổi.

## 13. Quy trình migration an toàn

Một quy trình chuyển đổi có thể lặp lại nên có các bước sau:

1. **Lưu baseline:** lưu bản OpenAPI hiện tại và ghi nhận phiên bản `openapi`, `info.version`, nguồn sinh tài liệu và các consumer.
2. **Chọn target:** xác định cần lên 3.1 hay 3.2; kiểm tra validator, Swagger UI, code generator, gateway và portal có hỗ trợ target không.
3. **Phân loại nguồn:** xác định tài liệu là do springdoc sinh, được viết thủ công hay ghép từ nhiều file `$ref`.
4. **Chuyển đổi có kiểm soát:** dùng công cụ phù hợp để tạo bản nháp, sau đó rà soát `nullable`, exclusive bounds, schema examples, binary payload và dialect.
5. **Cập nhật version:** chỉ đổi trường `openapi` sau khi nội dung đã được chuyển đổi theo target. Giữ `info.version` theo quy tắc phát hành document của nhóm.
6. **Validate:** chạy parser, validator tương thích với target và lint rules của tổ chức; kiểm tra cả reference bên ngoài và schema được tái sử dụng.
7. **So sánh contract:** diff các path, HTTP method, parameter, required flag, request body, response, media type, security và schema trước/sau.
8. **Kiểm thử consumer:** render bằng Swagger UI, sinh SDK thử, chạy contract test và kiểm tra gateway/API portal.
9. **Phát hành:** lưu artifact OpenAPI đã xác thực, gắn version và ghi rõ thay đổi; không ghi đè baseline nếu chưa có kế hoạch rollback.

Nếu tài liệu được sinh tự động bởi springdoc, sửa annotation/model/customizer ở mã nguồn để output đúng. Không duy trì một bản OpenAPI đã chỉnh tay trong thư mục build nếu lần build kế tiếp sẽ ghi đè nó.

## 14. Kiểm tra những gì sau khi migration?

Kiểm tra theo từng lớp để phát hiện lỗi ở đúng nơi:

| Lớp kiểm tra | Câu hỏi |
|---|---|
| Cú pháp | JSON/YAML có parse được không? |
| OpenAPI structure | Các field bắt buộc và object có đúng cấu trúc của target version không? |
| Schema semantics | Nullability, bounds, examples, binary và composition có giữ đúng ý nghĩa không? |
| References | `$ref`, `$id`, `$schema` và external schema có resolve đúng không? |
| Contract | Operation, parameter, response, security và media type có thay đổi ngoài ý muốn không? |
| Toolchain | Swagger UI, validator, code generator và API gateway có hiểu target version không? |
| Runtime | Request/response thực tế có khớp schema đã công bố không? |

Một validator báo hợp lệ mới xác nhận được một phần. Nó không chứng minh rằng code generator tạo ra SDK tương thích hoặc rằng server runtime thực hiện đúng hợp đồng. Cần kiểm tra cả tài liệu, công cụ tiêu thụ và hành vi API.

### Kiểm tra thay đổi hợp đồng bằng diff

Sau khi sinh tài liệu mới, so sánh hai bản đã chuẩn hóa thứ tự key:

~~~text
openapi-before.yaml
openapi-after.yaml
~~~

Rà soát các thay đổi có thể ảnh hưởng consumer:

- Property trước đây bắt buộc nay thành optional hoặc ngược lại.
- Schema trước đây không nhận `null` nay nhận `null`.
- Giới hạn số thay đổi từ inclusive sang exclusive hoặc ngược lại.
- Media type của request/response bị thay đổi.
- Security requirement hoặc OAuth scope thay đổi.
- Path, method hoặc response status biến mất.
- Reference không resolve hoặc component bị loại khỏi document.

Nếu có thay đổi hợp đồng, hãy quyết định đó là thay đổi dự kiến hay lỗi migration trước khi phát hành.

## 15. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Validator báo `nullable` không được hỗ trợ | Schema 3.0 chưa chuyển sang type có `null` | Chuyển `nullable: true` sang `type` array hoặc union schema phù hợp |
| Schema integer chấp nhận sai giá trị biên | Chuyển `exclusiveMinimum`/`exclusiveMaximum` sai | Đối chiếu `minimum`/`maximum` với cờ boolean cũ và chuyển sang giá trị số |
| Swagger UI không hiển thị ví dụ | Đổi nhầm `example` của Media Type Object thành mảng Schema Object hoặc ngược lại | Kiểm tra vị trí của example trước khi chuyển |
| File upload hiển thị sai | Chuyển `format: binary` mà không xác định raw bytes, Base64 hay multipart | Mô tả đúng media type và cách mã hóa thực tế |
| Một validator chấp nhận nhưng code generator lỗi | Generator chưa hỗ trợ OpenAPI/JSON Schema target | Nâng phiên bản tool hoặc giới hạn feature set cho đến khi hỗ trợ |
| `$ref` không resolve sau khi tách file | Base URI, `$id` hoặc đường dẫn tương đối thay đổi | Kiểm tra resolution từ entry document và từng schema document |
| Springdoc vẫn sinh OpenAPI 3.1 dù muốn 3.2 | Thuộc tính hiện hành chỉ công bố lựa chọn 3.0/3.1 | Không sửa header thủ công; xác minh phiên bản springdoc và swagger-core hỗ trợ 3.2 |
| `info.version` thay đổi nhưng `openapi` không đổi | Nhầm version của document với version của đặc tả | Quản lý hai trường độc lập |
| Tài liệu 3.1 bị gắn nhãn 3.2 nhưng tool cũ từ chối | Consumer chưa hỗ trợ OAS 3.2 | Chỉ phát hành target khi toàn bộ toolchain hỗ trợ hoặc cung cấp artifact tương thích riêng |
| Tài liệu 3.0 bị gắn nhãn 3.1 nhưng schema vẫn dùng từ khóa cũ | Chỉ sửa trường `openapi` | Thực hiện migration Schema Object rồi validate lại |

## 16. Checklist trước khi nâng phiên bản

- [ ] Đã xác định đúng nguồn tài liệu: springdoc, file viết tay hay tài liệu nhiều phần.
- [ ] Đã phân biệt `openapi`, `info.version` và version API triển khai.
- [ ] Đã xác định chuyển đổi 2.0→3.0, 3.0→3.1 hay 3.1→3.2.
- [ ] Nếu từ 3.0 lên 3.1, đã xử lý `nullable`, exclusive bounds, Schema Object examples và binary content.
- [ ] Đã rà soát JSON Schema dialect và external references.
- [ ] Đã xác nhận toolchain hỗ trợ target version.
- [ ] Nếu dùng springdoc, đã chọn `OPENAPI_3_0` hoặc `OPENAPI_3_1` theo khả năng được tài liệu công bố.
- [ ] Không tự gắn nhãn 3.2 cho output nếu springdoc chưa hỗ trợ.
- [ ] Đã chạy parser, validator và lint trên artifact cuối.
- [ ] Đã diff path, operation, parameter, schema, media type và security.
- [ ] Đã thử render, sinh SDK và chạy contract test.
- [ ] Đã lưu baseline và có kế hoạch rollback.

## 17. Tài liệu tham khảo chính thức

- [OpenAPI Specification 3.2.1](https://spec.openapis.org/oas/latest.html) — ý nghĩa trường `openapi`, `info.version`, versioning major/minor/patch và Schema Object hiện hành.
- [Upgrading from OpenAPI 3.0 to 3.1](https://learn.openapis.org/upgrading/v3.0-to-v3.1.html) — các bước chuyển `nullable`, exclusive bounds, schema examples, binary content và JSON Schema dialect.
- [Upgrading from OpenAPI 3.1 to 3.2](https://learn.openapis.org/upgrading/v3.1-to-v3.2.html) — khả năng tương thích ngược và cách áp dụng dần tính năng mới của 3.2.
- [OpenAPI Specification v3.1.2](https://spec.openapis.org/oas/v3.1.2.html) — đặc tả chính thức của dòng 3.1.
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — thuộc tính `springdoc.api-docs.version`, giá trị hỗ trợ 3.0/3.1 và cấu hình tài liệu.
- [swagger2openapi](https://github.com/Mermade/swagger2openapi) — công cụ chuyển Swagger 2.0 sang OpenAPI 3.x; cần validate và rà soát kết quả sau chuyển đổi.

Nâng phiên bản OpenAPI là thay đổi về hợp đồng mô tả mà validator, Swagger UI, code generator và các hệ thống tích hợp cùng đọc. Hãy chuyển đổi ngữ nghĩa schema trước khi đổi nhãn phiên bản; sau đó xác thực tài liệu và kiểm tra toàn bộ toolchain. Với 3.1→3.2, có thể bắt đầu bằng thay đổi trường phiên bản khi tài liệu 3.1 đã hợp lệ và công cụ hỗ trợ 3.2; với 3.0→3.1, cần xử lý các khác biệt JSON Schema trước khi phát hành.
