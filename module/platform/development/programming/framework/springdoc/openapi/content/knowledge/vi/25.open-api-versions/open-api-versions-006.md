# `$ref` và các thuộc tính đi kèm theo ngữ cảnh cùng phiên bản

Trong OpenAPI, `$ref` cho phép tái sử dụng schema, parameter, response, request body và nhiều thành phần khác bằng cách tham chiếu đến một định nghĩa đã có. Tuy nhiên, các thuộc tính đặt cạnh `$ref` không phải lúc nào cũng có hiệu lực. Cách xử lý phụ thuộc vào **ngữ cảnh xuất hiện của `$ref`** và **phiên bản OpenAPI** mà document khai báo.

Điểm cần phân biệt trước tiên là:

- **Reference Object**: đối tượng tham chiếu được dùng tại những vị trí như `responses`, `parameters`, `requestBody`, `headers` hoặc `examples`.
- **Schema Object**: đối tượng mô tả dữ liệu, nơi `$ref` là một keyword của JSON Schema trong OpenAPI 3.1.

Trong OpenAPI 3.0, các thuộc tính đặt cạnh `$ref` thường bị bỏ qua. OpenAPI 3.1 thay đổi đáng kể đối với `$ref` nằm bên trong Schema Object: các schema keyword đi kèm được đánh giá cùng schema được tham chiếu. Riêng Reference Object vẫn có quy tắc riêng, chỉ cho phép `summary` và `description` làm thuộc tính ghi đè tài liệu.

## 1. `$ref` dùng để làm gì?

Thay vì lặp lại một schema hoặc response ở nhiều operation, có thể định nghĩa một lần trong `components` rồi tham chiếu bằng `$ref`.

Ví dụ schema dùng lại:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      responses:
        '200':
          description: Đơn hàng được tìm thấy
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
components:
  schemas:
    Order:
      type: object
      required:
        - id
        - status
      properties:
        id:
          type: integer
          format: int64
        status:
          type: string
```

`#/components/schemas/Order` là một JSON Pointer trỏ đến schema `Order` trong cùng OpenAPI document. Khi một operation tham chiếu schema này, các công cụ có thể dùng chung định nghĩa mà không phải sao chép lại toàn bộ cấu trúc.

Những vị trí thường gặp của `$ref` gồm:

| Vị trí | Ví dụ component |
|---|---|
| Schema | `#/components/schemas/Order` |
| Parameter | `#/components/parameters/PageSize` |
| Request body | `#/components/requestBodies/CreateOrder` |
| Response | `#/components/responses/NotFound` |
| Header | `#/components/headers/RateLimit` |
| Example | `#/components/examples/OrderExample` |
| Link | `#/components/links/OrderDetails` |
| Callback | `#/components/callbacks/OrderEvent` |

Component chỉ là định nghĩa được đặt tên. Đưa một object vào `components` chưa tự động làm nó xuất hiện trong API; operation phải tham chiếu đến component đó hoặc dùng nó theo một cơ chế phù hợp.

Security scheme là trường hợp cần phân biệt: operation không dùng `$ref` để tham chiếu security scheme. Nó dùng tên key của scheme trong Security Requirement Object, ví dụ `security: [{ bearerAuth: [] }]`, còn định nghĩa scheme nằm tại `components.securitySchemes.bearerAuth`.

## 2. Trước khi xét sibling, hãy xác định ngữ cảnh `$ref`

Cùng cú pháp `$ref` nhưng quy tắc có thể khác nhau tùy vị trí.

### `$ref` tại vị trí của Reference Object

Ví dụ tham chiếu một response:

```yaml
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
components:
  responses:
    NotFound:
      description: Không tìm thấy đơn hàng
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
```

Object tại `responses['404']` là Reference Object vì vị trí này chấp nhận một Response Object hoặc một Reference Object. `$ref` trỏ đến response tái sử dụng.

Các vị trí tương tự là phần tử trong danh sách `parameters`, `requestBody` ở cấp operation, `headers`, `examples`, `callbacks` và các component tương ứng.

### `$ref` bên trong Schema Object

Ví dụ tham chiếu một schema property:

```yaml
components:
  schemas:
    Customer:
      type: object
      properties:
        address:
          $ref: '#/components/schemas/Address'
    Address:
      type: object
      properties:
        city:
          type: string
        country:
          type: string
```

Object tại `properties.address` là Schema Object. Trong OpenAPI 3.1, `$ref` ở đây tuân theo quy tắc keyword của JSON Schema và có thể đi cùng các schema keyword khác. Trong OpenAPI 3.0, các thuộc tính sibling của `$ref` không có hiệu lực theo quy tắc Reference Object.

Đừng áp dụng quy tắc của Schema Object cho response hoặc parameter Reference Object. Ngược lại, đừng mặc định rằng mọi `$ref` trong schema 3.1 đều chỉ được có `summary` và `description` như Reference Object.

## 3. Quy tắc trong OpenAPI 3.0

OpenAPI 3.0 định nghĩa Reference Object riêng. Trong ngữ cảnh Reference Object, `$ref` là thuộc tính bắt buộc; các thuộc tính khác được thêm vào sẽ bị bỏ qua.

Ví dụ:

```yaml
openapi: 3.0.3
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
          description: Đơn hàng không tồn tại
components:
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
```

Trong OpenAPI 3.0, `description` đặt cạnh `$ref` ở vị trí response reference không ghi đè description của component. Reference Object chỉ được dùng để tham chiếu; sibling như `description`, `summary`, `content`, `headers` hoặc `required` không được dùng để tùy biến đối tượng tham chiếu.

Quy tắc tương tự áp dụng khi `$ref` xuất hiện ở vị trí Schema Object trong OpenAPI 3.0: không dựa vào sibling để thêm constraint hoặc metadata. Ví dụ dưới đây không có nghĩa là schema vừa tham chiếu `Address` vừa có `description` mới:

```yaml
properties:
  shippingAddress:
    $ref: '#/components/schemas/Address'
    description: Địa chỉ giao hàng
```

Với OpenAPI 3.0, sibling `description` bị bỏ qua. Nếu cần thêm mô tả hoặc constraint, dùng cách composition tương thích như `allOf` hoặc định nghĩa component riêng phù hợp.

## 4. Quy tắc trong OpenAPI 3.1: Reference Object

OpenAPI 3.1 bổ sung hai thuộc tính đặc biệt cho Reference Object:

- `summary`: phần tóm tắt thay thế summary của đối tượng được tham chiếu khi hiển thị tài liệu.
- `description`: phần mô tả thay thế description của đối tượng được tham chiếu khi hiển thị tài liệu.

Ví dụ response reference:

```yaml
openapi: 3.1.0
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
          description: Không tìm thấy đơn hàng được yêu cầu.
components:
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên.
```

Trong OpenAPI 3.1, description tại Reference Object có thể thay thế description của response được tham chiếu trong ngữ cảnh sử dụng đó. Định nghĩa component gốc vẫn giữ nguyên để các vị trí khác có thể dùng description ban đầu.

Không suy rộng quy tắc này thành “mọi sibling đều hoạt động”. Với Reference Object, `summary` và `description` là hai thuộc tính được quy định; các thuộc tính bổ sung khác vẫn bị bỏ qua.

Ví dụ sau không phải cách hợp lệ để tùy biến response bằng sibling:

```yaml
responses:
  '404':
    $ref: '#/components/responses/NotFound'
    content:
      application/json:
        schema:
          type: object
```

`content` không phải thuộc tính ghi đè được cho phép của Reference Object. Nếu cần một response khác, hãy tạo component response riêng hoặc định nghĩa response trực tiếp.

## 5. Quy tắc trong OpenAPI 3.1: `$ref` bên trong Schema Object

OpenAPI 3.1 đưa Schema Object gần với JSON Schema Draft 2020-12. Vì vậy, khi `$ref` được dùng như keyword trong Schema Object, các keyword sibling được áp dụng cùng schema được tham chiếu thay vì bị bỏ qua.

Ví dụ thêm `description` và giới hạn độ dài cho schema được tham chiếu:

```yaml
openapi: 3.1.0
components:
  schemas:
    ShortCode:
      type: string
      minLength: 1
    CreateOrderRequest:
      type: object
      properties:
        code:
          $ref: '#/components/schemas/ShortCode'
          description: Mã đơn hàng do hệ thống đối tác cấp.
          maxLength: 20
```

Schema tại `code` được đánh giá theo cả schema `ShortCode` và keyword sibling `maxLength: 20`. Vì vậy, giá trị phải đáp ứng `type: string`, `minLength: 1` từ schema được tham chiếu và `maxLength: 20` từ schema tại chỗ.

Ví dụ bổ sung một ràng buộc enum:

```yaml
properties:
  status:
    $ref: '#/components/schemas/OrderStatus'
    enum:
      - NEW
      - PAID
```

Trong OpenAPI 3.1, `enum` sibling là một schema constraint bổ sung. Giá trị hợp lệ phải đồng thời đáp ứng schema được tham chiếu và enum tại chỗ. Nó không thay thế `enum` trong component; hai tập ràng buộc được kết hợp theo logic AND của JSON Schema.

Các sibling có thể là validation keyword (`maxLength`, `minimum`, `pattern`, `enum`, `required`, `properties`, `items`, `additionalProperties`...) hoặc annotation keyword (`title`, `description`, `default`, `examples`, `deprecated`, `readOnly`, `writeOnly`...) nếu keyword đó hợp lệ trong Schema Object và dialect đang dùng.

Không đưa `summary` vào Schema Object chỉ vì Reference Object 3.1 hỗ trợ `summary`; `summary` không phải JSON Schema keyword chuẩn của Schema Object.

## 6. Bảng so sánh sibling theo ngữ cảnh và phiên bản

| Ngữ cảnh | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Reference Object tại `responses`, `parameters`, `requestBody`... | Chỉ dựa vào `$ref`; sibling khác bị bỏ qua | `summary` và `description` có thể ghi đè nội dung tài liệu; sibling khác bị bỏ qua |
| `$ref` bên trong Schema Object | Không dựa vào sibling; thuộc tính đi kèm không được áp dụng như schema constraint | Các schema keyword sibling được đánh giá cùng schema được tham chiếu |
| `description` cạnh `$ref` trong response reference | Bị bỏ qua | Ghi đè description để hiển thị tại vị trí dùng reference |
| `description` cạnh `$ref` trong property schema | Bị bỏ qua | Được áp dụng như annotation của Schema Object |
| `maxLength` cạnh `$ref` trong property schema | Bị bỏ qua | Được áp dụng như validation keyword bổ sung |
| `content` cạnh `$ref` trong response reference | Bị bỏ qua | Vẫn bị bỏ qua; không phải thuộc tính override của Reference Object |

Khi đọc một OpenAPI document, hãy trả lời theo thứ tự: document khai báo phiên bản nào, `$ref` đang ở vị trí Reference Object hay Schema Object, và sibling đó có phải thuộc tính được phép trong ngữ cảnh ấy không.

## 7. Cách viết tương thích OpenAPI 3.0 và 3.1

Nếu một document phải được tiêu thụ bởi cả công cụ OpenAPI 3.0 và 3.1, cách an toàn là không phụ thuộc vào sibling của `$ref` để thêm metadata hoặc constraint. Hãy đặt metadata trong component dùng chung hoặc tạo schema/component riêng.

Ví dụ thay vì:

```yaml
properties:
  externalCode:
    $ref: '#/components/schemas/Code'
    description: Mã do đối tác cung cấp
    maxLength: 30
```

hãy tạo một schema riêng bằng `allOf`:

```yaml
components:
  schemas:
    Code:
      type: string
      minLength: 1
    ExternalCode:
      allOf:
        - $ref: '#/components/schemas/Code'
        - type: string
          maxLength: 30
      description: Mã do đối tác cung cấp
```

Sau đó property tham chiếu schema mới:

```yaml
properties:
  externalCode:
    $ref: '#/components/schemas/ExternalCode'
```

`allOf` là composition keyword của Schema Object, không phải sibling tùy tiện trên Reference Object. Tất cả schema trong `allOf` phải được đáp ứng đồng thời. `ExternalCode` vì vậy vừa thỏa `Code`, vừa có giới hạn độ dài bổ sung.

Nếu chỉ cần thay mô tả cho một response trong OpenAPI 3.0, có thể tạo response component khác với description riêng hoặc định nghĩa response inline thay vì cố ghi đè sibling.

## 8. `allOf`, `oneOf`, `anyOf` và `$ref`

Các composition keyword giúp kết hợp nhiều schema. Chúng thường xuất hiện cùng `$ref`, nhưng mỗi keyword có ý nghĩa khác nhau:

| Keyword | Ý nghĩa |
|---|---|
| `allOf` | Instance phải hợp lệ với tất cả schema con |
| `oneOf` | Instance phải hợp lệ với đúng một schema con |
| `anyOf` | Instance phải hợp lệ với ít nhất một schema con |
| `not` | Instance không được hợp lệ với schema được chỉ định |

Ví dụ `allOf` để bổ sung thuộc tính:

```yaml
components:
  schemas:
    Person:
      type: object
      required: [name]
      properties:
        name:
          type: string
    Employee:
      allOf:
        - $ref: '#/components/schemas/Person'
        - type: object
          required: [employeeId]
          properties:
            employeeId:
              type: string
```

`Employee` phải đáp ứng cả `Person` lẫn schema bổ sung. `allOf` không phải cơ chế kế thừa class theo nghĩa hướng đối tượng; nó là phép kết hợp validation.

Một lưu ý quan trọng: nếu schema thành phần đặt `additionalProperties: false`, việc thêm property ở schema khác trong `allOf` có thể bị schema thành phần từ chối vì property đó không được khai báo trong chính object schema của nó. Với mô hình mở rộng phức tạp, hãy thiết kế `additionalProperties` và composition có chủ đích; trong OpenAPI 3.1, `unevaluatedProperties` có thể phù hợp hơn trong một số trường hợp, nhưng phải kiểm tra hỗ trợ của validator và client generator.

## 9. `$ref` trong Parameter, Response và Request Body

Reference Object giúp tái sử dụng cả cấu trúc HTTP, không chỉ schema.

Ví dụ parameter dùng chung:

```yaml
components:
  parameters:
    PageSize:
      name: pageSize
      in: query
      description: Số phần tử tối đa trong một trang.
      required: false
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
paths:
  /orders:
    get:
      parameters:
        - $ref: '#/components/parameters/PageSize'
      responses:
        '200':
          description: Danh sách đơn hàng
```

Ví dụ request body dùng chung:

```yaml
components:
  requestBodies:
    CreateOrder:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateOrderRequest'
paths:
  /orders:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateOrder'
      responses:
        '201':
          description: Đã tạo đơn hàng
```

Ví dụ response dùng chung:

```yaml
components:
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
paths:
  /orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
```

Trong các ví dụ trên, `$ref` ở `parameters`, `requestBody` và `responses` là Reference Object. Nếu cần thay `required`, `schema`, `content` hoặc `headers` tại một nơi sử dụng, hãy tạo component khác hoặc khai báo object trực tiếp. Không thêm những thuộc tính đó cạnh `$ref` với kỳ vọng chúng ghi đè component.

## 10. Đường dẫn tham chiếu: JSON Pointer và URI

Giá trị `$ref` là một URI-reference. Nó có thể trỏ đến:

- Một vị trí trong cùng document bằng fragment, ví dụ `#/components/schemas/Order`.
- Một file khác tương đối với document hiện tại, ví dụ `./common-schemas.yaml#/components/schemas/Address`.
- Một tài nguyên ở URL tuyệt đối, ví dụ `https://schemas.example.com/common.yaml#/components/schemas/Address`.

Ví dụ external reference:

```yaml
components:
  schemas:
    Address:
      $ref: './schemas/address.yaml#/Address'
```

Đường dẫn tương đối được phân giải theo base URI của document chứa reference, không nhất thiết theo working directory của ứng dụng hoặc thư mục source code. Khi di chuyển file OpenAPI, cần kiểm tra lại các relative reference.

Fragment bắt đầu bằng `#` thường dùng JSON Pointer. Trong JSON Pointer:

- `~` được escape thành `~0`.
- `/` được escape thành `~1`.

Ví dụ component có key `Order/Item` phải được tham chiếu như:

```yaml
$ref: '#/components/schemas/Order~1Item'
```

Nếu key có dấu `~`, phải escape trước theo quy tắc JSON Pointer, ví dụ `A~B` thành `A~0B`. Vì `$ref` là URI-reference, các ký tự cần URI encoding cũng phải được xử lý phù hợp. Không tự nối chuỗi path mà bỏ qua JSON Pointer escaping.

## 11. External reference và đóng gói tài liệu

External reference giúp chia schema lớn thành nhiều file, nhưng nó tạo thêm yêu cầu phân phối:

- Tài nguyên được tham chiếu phải tồn tại ở vị trí mà consumer có thể truy cập.
- Relative URL phải còn đúng sau khi publish hoặc di chuyển document.
- Nếu browser tải file ngoài origin, CORS có thể ảnh hưởng.
- Công cụ bundle/validator cần được cấu hình để đọc file local hoặc URL từ xa theo policy.
- Pipeline build cần đóng gói đầy đủ file tham chiếu hoặc bundle chúng nếu consumer chỉ nhận một file.

Không giả định endpoint `/v3/api-docs` tự động nhúng toàn bộ nội dung của mọi external `$ref`. Springdoc có thể sinh document có reference; việc resolve hoặc bundle external resource còn tùy cấu hình và công cụ downstream. Hãy kiểm tra OpenAPI JSON/YAML cuối cùng và thử tải từ môi trường triển khai thực tế.

Đối với reference đến URL bên ngoài, cân nhắc tính ổn định, quyền truy cập, cache và supply-chain risk. Một schema URL thay đổi nội dung có thể làm hợp đồng của ứng dụng thay đổi mà không có commit trong repository. Nếu cần tính tái lập, pin tài nguyên theo version hoặc lưu bản sao đã kiểm soát trong source/artifact.

## 12. Reference đệ quy và schema lồng nhau

`$ref` có thể tham chiếu một schema đang tham chiếu ngược lại chính nó. Đây là cách mô tả cấu trúc cây hoặc quan hệ đệ quy.

```yaml
components:
  schemas:
    Category:
      type: object
      required: [id, name]
      properties:
        id:
          type: integer
        name:
          type: string
        children:
          type: array
          items:
            $ref: '#/components/schemas/Category'
```

Schema `Category` có thể chứa danh sách `children`, mỗi phần tử cũng là `Category`. Đây là reference đệ quy hợp lệ. Client generator hoặc schema renderer cần hỗ trợ recursive model; một số công cụ có thể hiển thị hoặc sinh code khác nhau.

Phân biệt recursion có chủ đích với vòng tham chiếu lỗi. Ví dụ `$ref` trỏ đến key không tồn tại, file ngoài không truy cập được hoặc fragment sai là reference không thể resolve. Với recursion, đường dẫn reference vẫn resolve đến schema hợp lệ, chỉ là schema tiếp tục chứa một reference đến chính nó.

## 13. `$ref` và discriminator trong polymorphism

Khi một field có thể chứa nhiều loại object, thường kết hợp `$ref` với `oneOf` hoặc `anyOf`, và có thể dùng `discriminator` để giúp công cụ xác định subtype.

```yaml
components:
  schemas:
    PaymentMethod:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransfer'
      discriminator:
        propertyName: type
        mapping:
          card: '#/components/schemas/CardPayment'
          bank-transfer: '#/components/schemas/BankTransfer'
    CardPayment:
      type: object
      required: [type, last4]
      properties:
        type:
          type: string
          const: card
        last4:
          type: string
    BankTransfer:
      type: object
      required: [type, accountNumber]
      properties:
        type:
          type: string
          const: bank-transfer
        accountNumber:
          type: string
```

Trong ví dụ này, `oneOf` yêu cầu payload hợp lệ với đúng một schema con. `discriminator` cung cấp gợi ý mapping subtype theo property `type`; nó không thay thế validation của `oneOf`. Hãy bảo đảm các schema con phân biệt được và mapping trỏ đến reference hợp lệ.

Các keyword JSON Schema như `const` có trong OpenAPI 3.1 nhưng không thuộc subset Schema Object của OpenAPI 3.0. Nếu cần tương thích 3.0, có thể dùng `enum` một phần tử để biểu diễn giá trị cố định và kiểm tra lại output theo phiên bản mục tiêu.

## 14. Ảnh hưởng của JSON Schema dialect trong OpenAPI 3.1

OpenAPI 3.1 căn chỉnh Schema Object với JSON Schema Draft 2020-12 và hỗ trợ khai báo dialect qua `jsonSchemaDialect` ở cấp document. Nếu không khai báo, OpenAPI sử dụng dialect nền tảng được quy định cho OAS 3.1.

Điều này quan trọng vì các keyword như `$ref`, `$id`, `$anchor`, `$dynamicRef`, `unevaluatedProperties`, `prefixItems` hoặc vocabulary tùy chỉnh có thể ảnh hưởng đến cách schema được phân giải và đánh giá. Không phải công cụ OpenAPI nào cũng hỗ trợ toàn bộ JSON Schema 2020-12 hoặc custom dialect như nhau.

Ví dụ `$id` có thể xác định base URI của một schema resource trong JSON Schema. Khi dùng nested `$id` hoặc external schema resource, quy tắc phân giải reference có thể khác với việc chỉ nối fragment vào URL OpenAPI ban đầu. Hãy dùng validator hiểu đúng dialect và kiểm tra URL base khi schema có `$id`.

`$dynamicRef` và `$dynamicAnchor` là cơ chế nâng cao của JSON Schema 2020-12, hữu ích trong một số schema đệ quy có thể mở rộng. Chúng không phải cú pháp thay thế tổng quát cho `$ref`; chỉ dùng khi hiểu dynamic scope và xác nhận validator/client generator hỗ trợ.

## 15. Springdoc tạo và sử dụng `$ref` như thế nào?

Springdoc phân tích controller, kiểu DTO, Swagger annotations và model converter để tạo OpenAPI document. Khi một DTO được dùng làm request hoặc response schema, Springdoc thường đặt định nghĩa tái sử dụng trong `components.schemas` và tham chiếu bằng `$ref`.

Ví dụ DTO Java:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "OrderSummary", description = "Thông tin tóm tắt đơn hàng")
public record OrderSummary(
    Long id,
    String status,
    String customerName
) {
}
```

Controller có thể dùng cùng DTO ở nhiều operation:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{id}")
    OrderSummary getOrder(@PathVariable Long id) {
        return orderService.getSummary(id);
    }

    @GetMapping("/api/orders/recent")
    List<OrderSummary> recentOrders() {
        return orderService.findRecentSummaries();
    }
}
```

Document sinh ra thường có một schema component `OrderSummary`; response của hai operation tham chiếu đến component đó, trong đó operation danh sách dùng schema array có `items.$ref`.

Tên component có thể chịu ảnh hưởng của model converter, generic type, package và cấu hình Springdoc. Dùng `@Schema(name = "...")` khi cần tên schema ổn định và có ý nghĩa. Không chỉnh sửa trực tiếp JSON output như nguồn dữ liệu chính; hãy sửa DTO, annotation hoặc customizer để thay đổi được tái tạo mỗi lần ứng dụng khởi động.

Nếu dùng `@Schema` với `implementation`, `ref` hoặc `allOf`, kiểm tra phiên bản Swagger Annotations và Springdoc đang dùng. Các annotation có thể tạo Schema Object khác nhau tùy context; điều quan trọng là kiểm tra OpenAPI document thực tế, đặc biệt sibling của `$ref` và phiên bản `openapi` ở root.

## 16. Kiểm tra `$ref` trong document Springdoc

Sau khi ứng dụng khởi động, lấy OpenAPI JSON:

```bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
```

Kiểm tra phiên bản document:

```bash
jq -r '.openapi' openapi.json
```

Kiểm tra component schema:

```bash
jq '.components.schemas.OrderSummary' openapi.json
```

Kiểm tra response schema của một operation:

```bash
jq '.paths["/api/orders/{id}"].get.responses["200"].content["application/json"].schema' openapi.json
```

Kiểm tra `$ref` có được sinh ra:

```bash
jq '.. | objects | select(has("$ref")) | ."$ref"' openapi.json
```

Khi thấy `$ref` có sibling, hãy kiểm tra đúng ngữ cảnh:

1. Đọc giá trị `.openapi` để biết document là 3.0 hay 3.1.
2. Xác định object chứa `$ref` là Reference Object hay Schema Object.
3. Xác định sibling có phải thuộc tính được phép trong ngữ cảnh đó không.
4. Kiểm tra công cụ downstream có hỗ trợ semantics tương ứng không.
5. Chạy validator hoặc contract test trên document cuối cùng.

Đừng chỉ nhìn Swagger UI để kết luận `$ref` được xử lý đúng. UI có thể ẩn sibling không hợp lệ hoặc hiển thị description từ component gốc, khiến vấn đề khó nhận ra. Kiểm tra JSON/YAML raw và validation output.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `description` cạnh `$ref` không xuất hiện trong OpenAPI 3.0 | Sibling của Reference Object bị bỏ qua | Đặt description trong component hoặc tạo component riêng |
| `maxLength` cạnh `$ref` không giới hạn schema trong 3.0 | Schema `$ref` sibling không được áp dụng | Dùng `allOf` với schema bổ sung hoặc component riêng |
| `content` cạnh response `$ref` không thay response component | `content` không phải sibling override được phép của Reference Object | Tạo response component khác hoặc khai báo response inline |
| Sibling `description` hoạt động trong 3.1 nhưng không ở 3.0 | Khác biệt quy tắc version | Xác nhận trường `openapi` và điều chỉnh schema theo version |
| Sibling constraint trong Schema Object 3.1 không được validator nhận | Tool dùng parser OAS 3.0 hoặc JSON Schema dialect cũ | Nâng/cấu hình validator hỗ trợ OAS 3.1 |
| `$ref` không resolve | Sai JSON Pointer, file path, URL hoặc quyền truy cập | Kiểm tra URI base, escaping và tài nguyên đích |
| Reference có key chứa `/` không resolve | Chưa escape JSON Pointer token thành `~1` | Escape `/` thành `~1` và `~` thành `~0` |
| External ref chạy local nhưng hỏng khi publish | Relative path thay đổi hoặc file không được đóng gói | Bundle hoặc phân phối đầy đủ external resources |
| Schema `allOf` không nhận property mở rộng | `additionalProperties: false` trong một schema con | Thiết kế lại composition; xem xét `unevaluatedProperties` với OAS 3.1 |
| Recursive schema làm client generator lỗi | Tool downstream không hỗ trợ recursion tốt | Kiểm tra hỗ trợ recursive model hoặc điều chỉnh contract cho client mục tiêu |
| `oneOf` không phân biệt subtype | Schema con chồng lấn hoặc discriminator mapping sai | Thiết kế discriminator/property và xác minh từng nhánh |

## 18. Checklist dùng `$ref` an toàn

- [ ] Đã xác định OpenAPI document là 3.0.x hay 3.1.x.
- [ ] Đã xác định `$ref` nằm trong Reference Object hay Schema Object.
- [ ] Không dùng sibling tùy ý trên Reference Object.
- [ ] Với Reference Object 3.1, chỉ dựa vào `summary`/`description` override được quy định.
- [ ] Với Schema Object 3.1, sibling là keyword hợp lệ trong dialect đang dùng.
- [ ] Với tài liệu 3.0, dùng `allOf` hoặc component riêng để thêm constraint/metadata.
- [ ] Tên component và JSON Pointer fragment khớp chính xác.
- [ ] Đã escape `~` thành `~0` và `/` thành `~1` trong JSON Pointer token.
- [ ] External reference có base URI đúng và tài nguyên được đóng gói/phục vụ.
- [ ] Recursion là có chủ đích và công cụ downstream hỗ trợ.
- [ ] `allOf`, `oneOf`, `anyOf` được dùng theo đúng semantics validation.
- [ ] `discriminator` mapping trỏ đến schema hợp lệ và các nhánh phân biệt được.
- [ ] Springdoc output được kiểm tra sau khi thay đổi DTO, annotation hoặc customizer.
- [ ] Validator và client generator hỗ trợ phiên bản OpenAPI/JSON Schema mà document khai báo.

`$ref` không có một quy tắc sibling duy nhất cho mọi nơi. Trong Reference Object, OpenAPI 3.0 bỏ qua các thuộc tính đi kèm, còn OpenAPI 3.1 cho phép `summary` và `description` ghi đè nội dung tài liệu. Trong Schema Object của OpenAPI 3.1, `$ref` tuân theo JSON Schema và các schema keyword sibling được áp dụng cùng schema được tham chiếu. Khi xác định đúng ngữ cảnh và phiên bản trước khi viết reference, dùng `allOf` khi cần tương thích 3.0, rồi kiểm tra document Springdoc raw cùng validator/client generator, hợp đồng sẽ dễ tái sử dụng và ít lỗi hơn.

## Tài liệu tham khảo

- [OpenAPI Specification 3.0.4 – Reference Object](https://spec.openapis.org/oas/v3.0.4.html#reference-object)
- [OpenAPI Specification 3.1.1 – Reference Object](https://spec.openapis.org/oas/v3.1.1.html#reference-object)
- [OpenAPI Specification 3.1.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object)
- [OpenAPI Specification 3.1.1 – Relative References in URLs](https://spec.openapis.org/oas/v3.1.1.html#relative-references-in-urls)
- [JSON Schema 2020-12 – Core, `$ref` and base URI](https://json-schema.org/draft/2020-12/json-schema-core.html)
- [JSON Schema 2020-12 – Validation](https://json-schema.org/draft/2020-12/json-schema-validation.html)
- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
