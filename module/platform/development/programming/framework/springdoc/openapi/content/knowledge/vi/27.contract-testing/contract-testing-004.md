# Kiểm tra mọi tham chiếu $ref có thể được phân giải

Trong OpenAPI, $ref cho phép tái sử dụng schema, parameter, response, request body và nhiều thành phần khác mà không phải sao chép định nghĩa ở mọi nơi. Một tài liệu có thể được phân tách thành nhiều file để dễ tổ chức, hoặc giữ trong một file với các tham chiếu nội bộ. Dù dùng cách nào, mỗi tham chiếu phải trỏ tới một tài nguyên có thể đọc được và một vị trí thực sự tồn tại.

Một OpenAPI document có thể được parser đọc thành công nhưng vẫn có tham chiếu hỏng. Ví dụ, schema Order tham chiếu tới #/components/schemas/Customer nhưng component Customer đã bị đổi tên; một file gốc được chuyển sang thư mục khác khiến đường dẫn tương đối không còn đúng; hoặc JSON Pointer chứa dấu gạch chéo chưa được escape. Những lỗi này thường chỉ xuất hiện khi Swagger UI, code generator, validator hoặc API catalog cố tải và sử dụng schema được tham chiếu.

Kiểm tra $ref vì vậy phải là một bước riêng trong contract testing. Bài này hướng dẫn cách nhận diện tham chiếu, giải quyết URI và JSON Pointer, phân biệt quy tắc OpenAPI 3.0/3.1, phát hiện vòng tham chiếu hợp lệ, xác minh target và tích hợp việc kiểm tra vào CI.

## 1. $ref giải quyết vấn đề gì?

Tham chiếu giúp định nghĩa một thành phần một lần rồi dùng lại ở nhiều vị trí. Ví dụ, nhiều operation cùng trả về lỗi chuẩn:

~~~yaml
components:
  schemas:
    ApiError:
      type: object
      properties:
        code:
          type: string
        message:
          type: string
      required:
        - code
        - message
  responses:
    CommonError:
      description: Request không thể được xử lý.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
~~~

Operation có thể tái sử dụng response:

~~~yaml
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/CommonError'
~~~

Nếu nhiều operation cùng dùng ApiError, thay đổi schema tại một nơi sẽ được phản ánh qua tất cả tham chiếu. Điều này giúp tài liệu nhất quán và giảm trùng lặp.

Đổi lại, mỗi $ref tạo ra một quan hệ phụ thuộc. Nếu target bị xóa, đổi tên, di chuyển hoặc không thể tải, toàn bộ document có thể không được công cụ downstream xử lý đúng.

## 2. Những nơi có thể xuất hiện $ref

Không phải mọi $ref đều tham chiếu tới Schema Object. OpenAPI cho phép tái sử dụng nhiều loại thành phần:

| Vị trí | Target mong đợi |
|---|---|
| Schema Object | Một schema |
| Parameter Object | Một parameter |
| Request Body Object | Một request body |
| Response Object | Một response |
| Header Object | Một header |
| Example Object | Một example |
| Link Object | Một link |
| Callback Object | Một callback |
| Path Item Object | Một path item, ở phiên bản OpenAPI hỗ trợ thành phần này |

Ví dụ tham chiếu schema:

~~~yaml
schema:
  $ref: '#/components/schemas/Order'
~~~

Ví dụ tham chiếu parameter:

~~~yaml
parameters:
  - $ref: '#/components/parameters/OrderId'
~~~

Ví dụ tham chiếu request body:

~~~yaml
requestBody:
  $ref: '#/components/requestBodies/CreateOrder'
~~~

Một tham chiếu có thể phân giải được về mặt URI nhưng vẫn sai loại. Chẳng hạn, một trường responses cần Response Object nhưng lại trỏ tới Schema Object. Vì vậy, kiểm tra phải xác minh cả việc tìm thấy target lẫn loại object phù hợp với vị trí sử dụng.

## 3. Tham chiếu nội bộ trong cùng một document

Tham chiếu nội bộ thường bắt đầu bằng ký tự # và dùng JSON Pointer để xác định vị trí trong document hiện tại:

~~~yaml
components:
  schemas:
    Order:
      type: object
      properties:
        id:
          type: string
        customer:
          $ref: '#/components/schemas/Customer'
    Customer:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
~~~

Tham chiếu:

~~~yaml
$ref: '#/components/schemas/Customer'
~~~

được đọc theo các bước:

1. Dấu # chỉ fragment của document hiện tại.
2. Dấu / mở đầu JSON Pointer.
3. components chọn object components ở gốc.
4. schemas chọn map schema.
5. Customer chọn schema có tên Customer.

Nếu một cấp bị thiếu hoặc tên không khớp chính xác, tham chiếu không phân giải được. Tên key trong JSON Pointer phân biệt chữ hoa/chữ thường.

## 4. JSON Pointer và cách escape tên key

Fragment của một tham chiếu nội bộ thường chứa JSON Pointer. Trong mỗi token JSON Pointer, hai ký tự phải được escape:

| Ký tự trong key | Dạng escape |
|---|---|
| ~ | ~0 |
| / | ~1 |

Ví dụ component có tên chứa dấu gạch chéo:

~~~yaml
components:
  schemas:
    Order/Line:
      type: object
      properties:
        sku:
          type: string
~~~

Tham chiếu đúng:

~~~yaml
$ref: '#/components/schemas/Order~1Line'
~~~

Nếu key chứa dấu ngã:

~~~yaml
components:
  schemas:
    Version~Legacy:
      type: string
~~~

tham chiếu cần dùng:

~~~yaml
$ref: '#/components/schemas/Version~0Legacy'
~~~

Khi tạo token, escape dấu ~ trước rồi mới escape dấu /. Không dùng dấu gạch chéo trong tên key như thể nó là một phần tên; JSON Pointer sẽ hiểu đó là ranh giới giữa các cấp.

## 5. Escape URI fragment và JSON Pointer là hai lớp khác nhau

JSON Pointer trong URI fragment còn chịu quy tắc mã hóa URI. Với tên có dấu cách hoặc ký tự Unicode, fragment có thể cần percent-encoding bên cạnh escape của JSON Pointer.

Ví dụ một key có dấu cách:

~~~yaml
components:
  schemas:
    Order Summary:
      type: object
~~~

Tham chiếu có thể dùng fragment đã percent-encode:

~~~yaml
$ref: '#/components/schemas/Order%20Summary'
~~~

Hãy phân biệt:

- JSON Pointer escape xử lý ~ và / bên trong token.
- Percent-encoding xử lý các ký tự cần mã hóa trong URI fragment.

Không tự thay mọi dấu / trong toàn bộ URI bằng ~1. Chỉ ký tự / nằm trong tên token JSON Pointer mới cần escape thành ~1. Dấu / dùng để phân tách các cấp của pointer phải được giữ nguyên.

## 6. Tham chiếu tới một file khác

Một OpenAPI document có thể chia schema hoặc path thành nhiều file. Ví dụ cấu trúc:

~~~text
api/
├── openapi.yaml
├── schemas/
│   ├── order.yaml
│   └── customer.yaml
└── responses/
    └── errors.yaml
~~~

File gốc tham chiếu tới schema trong file khác:

~~~yaml
components:
  schemas:
    Order:
      $ref: './schemas/order.yaml'
    Customer:
      $ref: './schemas/customer.yaml'
  responses:
    CommonError:
      $ref: './responses/errors.yaml#/CommonError'
~~~

Nếu file order.yaml chứa schema ở gốc:

~~~yaml
type: object
properties:
  id:
    type: string
  customer:
    $ref: './customer.yaml'
~~~

thì customer.yaml được phân giải tương đối theo base URI của schema resource/file chứa tham chiếu. Khi tổ chức nhiều file, cần giữ các đường dẫn tương đối nhất quán.

Một file được tải thành công không đồng nghĩa mọi tham chiếu bên trong file đó cũng hợp lệ. Resolver phải tiếp tục duyệt các tham chiếu lồng nhau cho tới khi toàn bộ đồ thị tham chiếu đã được kiểm tra.

## 7. Tham chiếu tuyệt đối và tương đối

URI-reference có thể là:

| Dạng | Ví dụ | Cách phân giải |
|---|---|---|
| Fragment nội bộ | #/components/schemas/Order | Trong document hiện tại |
| File tương đối | ./schemas/order.yaml | Tương đối theo base URI |
| File ở thư mục cha | ../common/error.yaml | Đi lên một cấp từ base URI |
| URL tuyệt đối | https://schemas.example.com/order.yaml | Tải từ URI tuyệt đối |
| File URI | file:///workspace/api/order.yaml | Đọc từ vị trí file được phép |

Với tham chiếu tương đối, resolver cần biết URI cơ sở của document đang chứa tham chiếu. Nếu root document được đọc từ file /workspace/api/openapi.yaml, đường dẫn ./schemas/order.yaml thường được giải quyết từ thư mục /workspace/api.

Không lấy URL server trong trường servers của OpenAPI làm base URI cho $ref. Server URL mô tả nơi gọi API; nó không phải vị trí của tài liệu OpenAPI hay schema resource.

## 8. Base URI và tác động của $id trong OpenAPI 3.1

OpenAPI 3.1 sử dụng ngữ nghĩa JSON Schema cho Schema Object. Một schema resource có thể khai báo $id để định danh resource và thiết lập base URI dùng khi giải quyết các tham chiếu tương đối bên trong resource đó.

Ví dụ:

~~~yaml
components:
  schemas:
    Customer:
      $id: https://schemas.example.com/customer
      type: object
      properties:
        address:
          $ref: ./address.yaml
~~~

Với schema resource có $id như ví dụ, tham chiếu tương đối ./address.yaml được giải quyết dựa trên base URI của schema resource. Không nhất thiết dựa vào vị trí vật lý của file gốc.

Điều này quan trọng khi dùng schema 3.1 được chia sẻ qua nhiều document. Nếu di chuyển file nhưng giữ nguyên $id, cách giải quyết URI có thể vẫn dựa trên định danh đó. Ngược lại, đổi $id có thể làm thay đổi đích của mọi tham chiếu tương đối trong schema.

OpenAPI 3.0 không có đầy đủ mô hình JSON Schema resource và $id như OAS 3.1. Khi kiểm tra tài liệu 3.0, hãy dùng quy tắc tham chiếu của phiên bản đó và không giả định $id có ngữ nghĩa như trong Draft 2020-12.

## 9. Tham chiếu tới JSON Pointer ở cấp sâu

Không nhất thiết phải tham chiếu toàn bộ component. Có thể trỏ tới một subschema cụ thể:

~~~yaml
$ref: '#/components/schemas/Order/properties/customer'
~~~

Pointer đi qua:

1. components
2. schemas
3. Order
4. properties
5. customer

Kiểu target phải phù hợp với vị trí sử dụng. Nếu requestBody.content.application/json.schema tham chiếu tới subschema customer, target đó phải là Schema Object hợp lệ.

Tham chiếu sâu làm tăng độ nhạy với thay đổi cấu trúc. Nếu đổi tên property customer thành buyer, pointer sâu sẽ hỏng dù component Order vẫn tồn tại. Với các thành phần được tái sử dụng rộng rãi, thường nên tạo component schema riêng thay vì tham chiếu sâu vào property nội bộ.

## 10. Tham chiếu tới path có dấu gạch chéo

Khi tham chiếu tới Path Item trong cấu trúc paths, dấu / của URL là một phần tên key và phải được escape thành ~1 trong JSON Pointer.

Ví dụ path:

~~~yaml
paths:
  /orders/{id}:
    get:
      responses:
        '200':
          description: Order found.
~~~

Nếu cần tham chiếu tới Path Item này trong một vị trí hỗ trợ Path Item reference, pointer phải dùng:

~~~yaml
$ref: '#/paths/~1orders~1{id}'
~~~

Dấu / phân cấp trong JSON Pointer được giữ làm dấu phân cách. Dấu / thuộc tên path được chuyển thành ~1. Nếu quên escape, resolver sẽ tìm các cấp con orders và {id} thay vì key nguyên vẹn /orders/{id}.

## 11. Phân biệt Reference Object và Schema Object có $ref

Trong OpenAPI, $ref xuất hiện ở ít nhất hai ngữ cảnh quan trọng:

- Reference Object dùng để thay thế một object OpenAPI có thể được tham chiếu, chẳng hạn parameter hoặc response.
- Schema Object dùng $ref theo ngữ nghĩa JSON Schema trong OpenAPI 3.1.

Khác biệt này ảnh hưởng tới các trường sibling nằm cạnh $ref.

Với OpenAPI 3.0, Reference Object chỉ định nghĩa $ref; các thuộc tính bổ sung không thuộc mô hình được hỗ trợ và thường bị bỏ qua. Với OpenAPI 3.1, Reference Object hỗ trợ summary và description; các sibling khác không được tự động hợp nhất thành object target.

Trong Schema Object của OpenAPI 3.1, $ref tuân theo JSON Schema 2020-12, vì vậy các keyword sibling có thể tiếp tục áp dụng:

~~~yaml
schema:
  $ref: '#/components/schemas/Order'
  description: Đơn hàng trong kết quả tìm kiếm.
~~~

Đừng áp dụng quy tắc của Reference Object cho mọi Schema Object hoặc ngược lại. Khi kiểm tra sibling, phải biết phiên bản OpenAPI và vị trí chính xác của $ref.

## 12. Kiểm tra target có tồn tại

Mỗi tham chiếu cần được kiểm tra theo một chuỗi bước:

1. Đọc giá trị $ref như một URI-reference.
2. Xác định document/resource hiện tại và base URI.
3. Phân giải phần URI tới tài nguyên đích.
4. Tải tài nguyên nếu đó là một document bên ngoài.
5. Phân giải fragment, JSON Pointer hoặc anchor.
6. Xác nhận target tồn tại.
7. Xác nhận target có đúng loại object theo vị trí dùng.
8. Tiếp tục kiểm tra các $ref nằm trong target.

Ví dụ:

~~~yaml
requestBody:
  $ref: '#/components/requestBodies/CreateOrder'
~~~

Nếu pointer tìm thấy components.requestBodies.CreateOrder nhưng giá trị thực tế là một chuỗi thay vì Request Body Object, tham chiếu đã tìm thấy vị trí nhưng document vẫn không hợp lệ.

Kiểm tra tồn tại và kiểm tra cấu trúc là hai bước riêng. Công cụ validator OpenAPI nên thực hiện cả hai ở mức mà phiên bản công cụ hỗ trợ.

## 13. Anchor và tham chiếu không dùng JSON Pointer

Trong JSON Schema 2020-12, schema resource có thể khai báo anchor:

~~~yaml
$id: https://schemas.example.com/order
$anchor: orderIdentity
type: object
properties:
  id:
    type: string
~~~

Một tham chiếu có thể dùng fragment anchor:

~~~yaml
$ref: 'https://schemas.example.com/order#orderIdentity'
~~~

Khi dùng anchor, resolver phải tìm anchor trong schema resource theo đúng dialect và quy tắc JSON Schema. Không diễn giải mọi fragment đều là JSON Pointer bắt đầu bằng dấu /.

Các tính năng nâng cao như $dynamicAnchor và $dynamicRef còn có ngữ nghĩa động cho schema đệ quy hoặc mở rộng. Công cụ chỉ hỗ trợ JSON Pointer đơn giản có thể không đủ để xác minh đầy đủ các tham chiếu đó.

## 14. Vòng tham chiếu: không phải lúc nào cũng là lỗi

Một đồ thị tham chiếu có thể chứa chu trình hợp lệ. Ví dụ schema Node có thể chứa các Node con:

~~~yaml
components:
  schemas:
    Node:
      type: object
      properties:
        value:
          type: string
        children:
          type: array
          items:
            $ref: '#/components/schemas/Node'
~~~

Đây là schema đệ quy hợp lệ trong nhiều trường hợp. Nếu validator đánh dấu mọi chu trình là lỗi, nó có thể từ chối những mô hình cây hoặc đồ thị vốn hợp lệ.

Cần phân biệt:

- **Unresolved reference:** không tìm thấy tài nguyên hoặc vị trí được tham chiếu. Đây là lỗi.
- **Circular reference:** một tham chiếu dẫn trở lại schema đã gặp. Có thể hợp lệ, nhất là schema đệ quy.
- **Unsupported cycle:** công cụ downstream không xử lý được chu trình trong một thao tác cụ thể, ví dụ tạo mã hoặc dereference. Đây là giới hạn công cụ, không tự động chứng minh OpenAPI document sai.

Resolver nên dùng tập URI/resource đã thăm để tránh duyệt vô hạn. Khi gặp một node đang được xử lý, công cụ ghi nhận chu trình rồi tiếp tục theo chính sách phù hợp, thay vì coi nó là unresolved.

## 15. Phân biệt resolve, validate và dereference

Ba thao tác này không giống nhau:

| Thao tác | Mục đích |
|---|---|
| Resolve | Tìm tài nguyên và target mà $ref chỉ tới |
| Validate | Kiểm tra document và schema có tuân theo quy tắc đặc tả hay không |
| Dereference | Thay tham chiếu bằng nội dung target trong cấu trúc đã mở rộng |
| Bundle | Gom các tài liệu liên quan thành một đầu ra phân phối, thường vẫn giữ một số $ref nội bộ |

Một tham chiếu có thể resolve thành công nhưng target sai loại hoặc vi phạm schema. Khi đó resolve thành công nhưng validation thất bại.

Dereference toàn bộ có thể tạo object graph có chu trình hoặc lặp lại cùng schema nhiều lần. Một số công cụ không thể biểu diễn kết quả dereference hoàn toàn dưới dạng JSON/YAML hữu hạn khi có tham chiếu đệ quy. Bundle thường phù hợp hơn khi muốn tạo một file phân phối nhưng vẫn giữ tham chiếu nội bộ.

Không coi việc bundle thành công là bằng chứng duy nhất rằng mọi hợp đồng đều đúng. Vẫn cần validate document sau khi bundle.

## 16. Tổ chức nhiều file để dễ bảo trì

Một cách tổ chức tài liệu:

~~~text
openapi/
├── openapi.yaml
├── paths/
│   ├── orders.yaml
│   └── customers.yaml
├── schemas/
│   ├── order.yaml
│   ├── order-line.yaml
│   └── customer.yaml
└── responses/
    └── api-error.yaml
~~~

Root document có thể tham chiếu Path Item hoặc thành phần theo cách phù hợp với cấu trúc OpenAPI version đang dùng. Mỗi file nên có một trách nhiệm rõ ràng và đường dẫn tương đối dễ hiểu.

Nguyên tắc tổ chức:

- Giữ tên file ổn định, tránh đổi tên tùy tiện.
- Dùng một quy ước nhất quán cho thư mục paths, schemas và responses.
- Tránh tạo nhiều bản sao cùng một schema với tên khác nhau.
- Hạn chế tham chiếu ngược vòng giữa nhiều file nếu không cần.
- Ghi rõ root document dùng để lint, bundle và phát hành.
- Giữ tất cả file được tham chiếu trong source control hoặc artifact tương ứng.

Nếu chỉ phát hành root openapi.yaml mà không phát hành các file phụ thuộc, client sẽ không thể resolve các relative $ref sau khi tải artifact.

## 17. Kiểm tra bằng công cụ lint và bundle

Nên dùng công cụ hiểu OpenAPI thay vì chỉ tìm chuỗi $ref bằng grep. Một parser có thể phân biệt tham chiếu thật với một ví dụ payload hoặc mô tả văn bản tình cờ chứa key $ref.

Ví dụ dùng Redocly CLI:

~~~bash
npx @redocly/cli lint openapi/openapi.yaml
~~~

Lệnh lint phân tích document và báo các vấn đề theo parser, ruleset và khả năng hỗ trợ của phiên bản CLI.

Có thể bundle thành một file để kiểm tra khả năng phân giải các tham chiếu:

~~~bash
npx @redocly/cli bundle openapi/openapi.yaml -o target/openapi-bundled.yaml
~~~

Sau khi bundle, chạy lint lại trên artifact:

~~~bash
npx @redocly/cli lint target/openapi-bundled.yaml
~~~

Hãy khóa version CLI trong CI, chẳng hạn thông qua package lock hoặc công cụ quản lý version của dự án. Không để mỗi build tự tải một version khác nhau vì kết quả resolver và ruleset có thể thay đổi.

Nếu dùng công cụ khác, kiểm tra rõ công cụ có hỗ trợ OpenAPI 3.0 hay 3.1, JSON Schema dialect nào, external file refs, URI anchors và recursive refs.

## 18. Kiểm tra file OpenAPI được sinh bởi Springdoc

Với springdoc-openapi, tài liệu runtime thường được lấy từ endpoint như /v3/api-docs hoặc được xuất bằng Maven plugin trong bước build. Hãy kiểm tra đúng artifact cuối cùng mà CI sẽ sử dụng.

Quy trình gợi ý:

1. Khởi động ứng dụng bằng profile dành cho contract.
2. Lấy OpenAPI JSON từ endpoint hoặc artifact export.
3. Lưu vào thư mục build.
4. Chạy parser/linter có hỗ trợ phiên bản OpenAPI của document.
5. Kiểm tra toàn bộ $ref nội bộ.
6. Nếu có external refs, chạy resolver từ đúng thư mục và URI gốc.
7. Bundle thành artifact phân phối nếu cần.
8. Validate lại file bundle.

Ví dụ nếu Maven plugin xuất file:

~~~text
target/openapi/openapi.json
~~~

thì lệnh kiểm tra phải dùng đúng file này. Không chỉ lint một file nguồn cũ trong src nếu hợp đồng được công bố là output runtime từ Springdoc.

Nếu Springdoc sinh các schema nội bộ trong components.schemas, kiểm tra các tham chiếu dạng #/components/schemas/... đều tìm thấy target. Nếu OpenApiCustomizer thêm $ref tới file ngoài, bảo đảm các file đó cũng có trong artifact và resolver dùng đúng base URI.

## 19. Kiểm tra tự động trong CI

Có thể đưa việc kiểm tra tham chiếu vào pipeline sau bước export:

~~~text
Start Spring Boot
      |
      v
Fetch /v3/api-docs
      |
      v
Save OpenAPI artifact
      |
      v
Parse and lint document
      |
      v
Resolve all local and external $ref
      |
      v
Bundle if distribution requires it
      |
      v
Validate bundled document
      |
      v
Publish artifact
~~~

Ví dụ script:

~~~bash
mvn clean verify
npx @redocly/cli lint target/openapi/openapi.json
npx @redocly/cli bundle target/openapi/openapi.json -o target/openapi/bundled.yaml
npx @redocly/cli lint target/openapi/bundled.yaml
~~~

Các lệnh giả định Maven đã tạo file tại target/openapi/openapi.json và Redocly CLI được cài trong môi trường build. Điều chỉnh đường dẫn theo cấu hình thật của plugin.

Nếu tài liệu có relative external refs, bảo đảm các file được tham chiếu nằm đúng vị trí tương đối với root document. Không copy riêng root file sang thư mục tạm rồi chạy lint nếu các file phụ thuộc không được copy theo.

## 20. Kiểm tra target type và vị trí sử dụng

Khi kiểm tra $ref, ngoài việc target tồn tại, hãy xác minh nó được dùng đúng vị trí:

~~~yaml
paths:
  /orders:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateOrder'
      responses:
        '201':
          $ref: '#/components/responses/OrderCreated'
components:
  requestBodies:
    CreateOrder:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateOrder'
  responses:
    OrderCreated:
      description: Order created.
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Order'
  schemas:
    CreateOrder:
      type: object
    Order:
      type: object
~~~

Ở ví dụ này:

- requestBody trỏ tới Request Body Object.
- response 201 trỏ tới Response Object.
- schema trong content trỏ tới Schema Object.

Nếu đổi nhầm CreateOrder thành schema ref trực tiếp tại requestBody, vị trí đó sẽ không còn đúng cấu trúc. Một resolver chỉ kiểm tra URI tồn tại có thể không phát hiện lỗi kiểu này; cần OpenAPI validator.

## 21. Phát hiện tham chiếu hỏng do đổi tên hoặc di chuyển

Các thay đổi sau thường làm hỏng $ref:

- Đổi tên component trong components.schemas nhưng quên sửa tham chiếu.
- Chuyển file schema sang thư mục khác nhưng giữ relative URI cũ.
- Đổi tên property đang được tham chiếu bằng JSON Pointer sâu.
- Đổi tên file hoặc case của đường dẫn trong môi trường Linux.
- Thay đổi $id khiến base URI của schema resource đổi.
- Bundle tài liệu nhưng không cập nhật các đường dẫn phụ thuộc.
- Xóa một component đã được operation hoặc component khác sử dụng.

Một số lỗi có thể không xuất hiện trên máy Windows do hệ thống file thường không phân biệt hoa/thường như Linux. CI chạy trên Linux có thể phát hiện đường dẫn sai case. Vì vậy, kiểm tra refs trên cùng loại hệ điều hành hoặc container với môi trường phát hành.

Khi refactor tên schema, dùng tìm kiếm tham chiếu trong IDE hoặc công cụ OpenAPI-aware và chạy linter ngay sau thay đổi. Không chỉ sửa một chuỗi trong file root vì tham chiếu có thể nằm sâu trong các file được include.

## 22. Bảo vệ resolver khi xử lý external refs

External $ref có thể trỏ tới URL hoặc file trên hệ thống. Việc tự động tải mọi URI từ tài liệu không đáng tin cậy có thể tạo rủi ro:

- SSRF: CI bị yêu cầu truy cập dịch vụ nội bộ qua URL do tài liệu cung cấp.
- Path traversal: tham chiếu file cố truy cập ra ngoài thư mục tài liệu được phép.
- Data disclosure: resolver đọc file cấu hình hoặc secret không liên quan.
- Supply-chain risk: schema ngoài thay đổi mà không được kiểm soát.
- Build instability: server schema ngoài tạm thời không truy cập được.

Đối với tài liệu từ pull request hoặc nguồn không tin cậy:

1. Giới hạn resolver vào thư mục tài liệu đã cho phép.
2. Allowlist host/domain được phép tải.
3. Chặn truy cập metadata service và các mạng nội bộ nhạy cảm.
4. Giới hạn kích thước file, thời gian tải và số lượng URI.
5. Không cho URI chứa credential hoặc token.
6. Pin hoặc vendor schema ngoài vào repository khi cần độ tái lập.
7. Ghi lại nguồn và checksum của schema được tải.

Không tắt bảo vệ mạng chỉ để external ref resolve thành công. Nếu schema là dependency chính thức, nên quản lý nó như một dependency có version và nguồn rõ ràng.

## 23. External refs và tính tái lập của build

Nếu mỗi lần build đều tải schema từ một URL có nội dung thay đổi, cùng một commit có thể sinh ra hợp đồng khác nhau ở các ngày khác nhau.

Để build có thể tái lập:

- Dùng version hoặc release cụ thể của schema ngoài.
- Ưu tiên URL bất biến hoặc lưu bản sao đã review trong repository.
- Có thể ghi checksum để phát hiện nội dung thay đổi.
- Cache dependency ngoài theo chính sách có thời hạn.
- Ghi nhận resolver version và nguồn tài liệu.
- Thất bại rõ ràng khi nguồn không truy cập được thay vì âm thầm dùng bản cũ không rõ nguồn.

Nếu dùng URL dạng latest hoặc nhánh main, hãy xem đó là dependency thay đổi theo thời gian. Điều này có thể phù hợp cho tài liệu cập nhật liên tục, nhưng không phù hợp nếu cần phát hành artifact có thể tái tạo chính xác.

## 24. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Unresolved reference | Target không tồn tại | Kiểm tra tên component, file và fragment |
| 404 khi tải external ref | URL sai hoặc server không có file | Kiểm tra URI và quyền truy cập |
| Relative ref hoạt động local nhưng lỗi CI | Base URI hoặc cấu trúc thư mục khác | Giữ nguyên cấu trúc file và chạy resolver từ root document |
| JSON Pointer không tìm thấy key có dấu / | Chưa escape dấu / thành ~1 | Escape token đúng quy tắc JSON Pointer |
| Key chứa dấu ~ không được tìm thấy | Chưa đổi ~ thành ~0 | Escape dấu ~ trước dấu / |
| Ref sai chữ hoa/thường | Key hoặc tên file không khớp | Đồng bộ case, kiểm tra trên Linux |
| Ref tìm thấy nhưng validator vẫn báo lỗi | Target sai loại hoặc cấu trúc không hợp lệ | Kiểm tra object type theo vị trí |
| Ref sibling bị bỏ qua | Nhầm Reference Object với Schema Object | Đối chiếu OAS 3.0/3.1 và vị trí $ref |
| Validator báo circular reference | Công cụ không hỗ trợ hoặc policy chặn chu trình | Phân biệt recursive schema hợp lệ với lỗi resolve |
| Bundle thành công nhưng document sai | Chưa chạy validation sau bundle | Lint/validate artifact cuối cùng |
| File root được phát hành nhưng thiếu file con | External relative refs không được đóng gói | Bundle hoặc phát hành cả cây file phụ thuộc |
| Resolver truy cập host ngoài dự kiến | External URI không được giới hạn | Allowlist domain và sandbox network |
| Build lúc được lúc lỗi | Schema URL ngoài thay đổi hoặc không ổn định | Pin version, vendor hoặc checksum |
| Dùng grep để kiểm tra mọi $ref | Chuỗi trong example/description bị nhận nhầm | Dùng parser OpenAPI để duyệt cấu trúc |

## 25. Checklist trước khi chấp nhận OpenAPI contract

Trước khi đưa tài liệu vào release:

1. Xác định root OpenAPI document và phiên bản OAS.
2. Parse YAML/JSON bằng parser hỗ trợ phiên bản đó.
3. Duyệt mọi vị trí có thể chứa Reference Object hoặc Schema Object với $ref.
4. Phân giải URI tương đối theo đúng base URI.
5. Áp dụng $id và dialect khi xử lý schema resource của OAS 3.1.
6. Giải mã fragment, JSON Pointer và anchor đúng quy tắc.
7. Xác minh target tồn tại.
8. Xác minh target có đúng loại object.
9. Duyệt tiếp các tham chiếu lồng nhau.
10. Chấp nhận chu trình hợp lệ và phát hiện unresolved reference.
11. Kiểm tra external URI trong phạm vi network/file được phép.
12. Bundle nếu cần phân phối một file độc lập.
13. Validate lại artifact sau bundle.
14. Kiểm tra Swagger UI, code generator hoặc consumer thực tế nếu đó là công cụ downstream.
15. Lưu kết quả và version resolver trong CI log/artifact.

## 26. Ghi nhớ

- $ref giúp tái sử dụng schema và các thành phần OpenAPI.
- Tham chiếu nội bộ thường dùng JSON Pointer bắt đầu bằng #/.
- Dấu ~ trong token được escape thành ~0; dấu / trong tên token thành ~1.
- URI fragment còn có thể cần percent-encoding.
- Relative refs được giải quyết theo base URI của tài liệu/resource; OAS 3.1 còn xét $id của schema resource.
- Không dùng servers URL làm base URI cho $ref.
- Kiểm tra cả target tồn tại lẫn đúng loại object.
- Phân biệt Reference Object với Schema Object có $ref, đặc biệt khi xử lý sibling trong OAS 3.0 và 3.1.
- Anchor và các keyword động cần resolver hiểu JSON Schema dialect tương ứng.
- Circular schema có thể hợp lệ; unresolved reference luôn cần xử lý.
- Resolve, validate, bundle và dereference là các thao tác khác nhau.
- Dùng parser/linter OpenAPI thay vì grep chuỗi để kiểm tra refs.
- Giới hạn external resolver để tránh SSRF, path traversal và dependency không ổn định.
- Kiểm tra artifact cuối cùng được sinh từ Springdoc, không chỉ file nguồn.

Để xác nhận mọi tham chiếu $ref có thể được phân giải, hãy kiểm tra document được sinh ra bằng một resolver hiểu đúng phiên bản OpenAPI và JSON Schema dialect. Xác minh URI, fragment, JSON Pointer, target type và các tham chiếu lồng nhau; phân biệt chu trình schema hợp lệ với target bị thiếu. Sau đó lint và validate artifact cuối cùng trong CI, đồng thời giới hạn truy cập file và network khi xử lý external refs.
