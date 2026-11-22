# paths, operations, parameters và requestBody

> **Chương:** Hợp đồng OpenAPI  
> **Module:** `INTEGRATION_API_REST` — học thiết kế REST API theo tài nguyên, URI, phương thức và mã trạng thái HTTP, cùng hợp đồng dữ liệu rõ ràng; thực hành xác thực, phân quyền, xử lý lỗi và kiểm thử với Java/Spring hoặc công nghệ tương đương.

OpenAPI giúp mô tả **client được phép gọi API như thế nào** mà không cần đọc mã nguồn server. Nhưng một tài liệu OpenAPI có thể parse hợp lệ vẫn khiến client gửi sai URI, đặt JSON vào query string, hiểu nhầm một header bắt buộc hoặc tưởng `required: true` tự bảo đảm server đã validate dữ liệu.

Bài này tập trung vào bốn khối gắn chặt với một HTTP request: **`paths`** định danh các điểm truy cập; **operation** nói phương thức nào được thực hiện; **`parameters`** mô tả dữ liệu ở path/query/header/cookie; **`requestBody`** mô tả nội dung của thông điệp gửi lên. Ta dùng **OpenAPI 3.1** và ví dụ REST API quản lý đơn hàng, rồi đối chiếu với controller Spring Boot và các kiểm thử contract.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `Paths Object`, `Path Item Object` và `Operation Object`, tránh nhầm URL với HTTP method.
2. Khai báo đúng `in: path`, `query`, `header`, `cookie`, bao gồm `required`, kiểu dữ liệu, định dạng và serialization.
3. Định nghĩa `requestBody` với media type, JSON Schema, ví dụ và các quy tắc `required` khác nhau.
4. Biết chọn nơi đặt input giữa URI parameters và body theo ngữ nghĩa HTTP.
5. Ánh xạ tài liệu sang Spring MVC `@GetMapping`, `@PostMapping`, `@PatchMapping`, `@PathVariable`, `@RequestParam`, `@RequestHeader` và `@RequestBody`.
6. Kiểm thử tính nhất quán giữa OpenAPI, response lỗi, xác thực/phân quyền và hành vi chạy thực tế.
7. Tránh các lỗi phổ biến của client generation, component reuse và thay đổi hợp đồng.

## 1. Bốn tầng trong một lời gọi API

Ví dụ: `POST /api/orders` nhận body JSON và header `Idempotency-Key`. Trong OpenAPI, các trách nhiệm được tách rõ:

| Phần | Định nghĩa |
| --- | --- |
| `servers` | Base URL, ví dụ `https://api.example.test/api`. |
| `paths` / Path Item | `/orders` — URI của resource; chứa các method `get`, `post`. |
| **Operation** | `post` mô tả tạo đơn; `get` mô tả đọc collection. |
| `parameters` | Query, path, header hoặc cookie; ví dụ `Idempotency-Key` ở header. |
| `requestBody` | Body với media type `application/json` và schema. |
| `responses` | Mã/status, headers và body phản hồi, ví dụ `201` và `Location`. |
| `components` | Schemas, parameters, security schemes dùng lại qua `$ref`. |

`servers.url` đã có `/api` thì `paths./orders` tương ứng URI công khai `/api/orders`; đừng lặp `/api` vào path chỉ vì controller Spring có tiền tố ấy.

## 2. Paths Object và Path Item: mô hình hóa resource

Một cấu trúc tối thiểu:

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
servers:
  - url: https://api.example.test/api
paths:
  /orders:
    get:
      summary: List orders
      responses:
        '200':
          description: Matching orders
    post:
      summary: Create an order
      responses:
        '201':
          description: Order created
  /orders/{orderId}:
    get:
      summary: Get an order
      parameters:
        - name: orderId
          in: path
          required: true
          schema: { type: integer, format: int64 }
      responses:
        '200':
          description: Order found
```

Những quy tắc quan trọng:

- Khóa `paths` là **đường dẫn bắt đầu bằng `/`**; các phần `{orderId}` là **template expression**.
- `/orders` là resource tập hợp; `/orders/{orderId}` mô tả một resource cụ thể. Chúng không tự quy định method; `get` và `post` mới là operation.
- Mọi biến template dùng trong đường dẫn phải có **path parameter tương ứng**, ở Path Item hoặc Operation; path parameter **luôn** `required: true`.
- Không tạo hai path template có hình dạng tương đương chỉ khác tên biến, ví dụ `/orders/{id}` và `/orders/{orderId}`, rồi mong router phân biệt được chúng như hai đường dẫn khác nhau.
- Tránh những URI gây nhập nhằng với route cụ thể như `/orders/search` và `/orders/{orderId}` nếu routing, type và độ ưu tiên không được kiểm soát; phải thử trên framework thực tế.
- Query string **không thuộc khóa path**. Viết `/orders` cùng `parameters: in: query`, không tạo path `/orders?page=1`.

### Parameter chung ở Path Item

Nếu cả GET và PATCH cùng dùng `orderId`, ta có thể đặt parameter ở Path Item:

```yaml
paths:
  /orders/{orderId}:
    parameters:
      - name: orderId
        in: path
        required: true
        description: Stable numeric order identifier
        schema: { type: integer, format: int64, minimum: 1 }
    get:
      operationId: getOrder
      responses:
        '200': { description: Current order }
    patch:
      operationId: patchOrder
      responses:
        '204': { description: Updated }
```

Operation có thể **ghi đè** một parameter chung theo cùng cặp (`name`, `in`), nhưng không thể dùng override để xóa parameter đã khai báo ở cấp Path Item. Một danh sách parameters không được chứa hai phần tử trùng (`name`, `in`).

**Đặt cùng một parameter ở đâu?** Đặt ở Path Item khi các operation thực sự cùng dùng một định nghĩa; đặt tại operation nếu parameter chỉ phục vụ method đó (ví dụ `Idempotency-Key` cho POST hay `If-Match` cho PATCH).

## 3. Operation Object: hành vi của một phương thức

Một Operation Object nằm dưới `get`, `post`, `put`, `patch`, `delete`… của một Path Item. Nó có `operationId` **duy nhất trong toàn spec** (quan trọng với SDK), `summary`/`description`, `tags`, `parameters`, `requestBody`, `responses`, `security` và có thể `deprecated`. **`responses` là trường bắt buộc**; `requestBody` chỉ nên dùng khi HTTP method có ngữ nghĩa body đã được xác định.

```yaml
post:
  operationId: createOrder
  summary: Create an order
  tags: [Orders]
  responses:
    '201': { description: Created }
    '409': { description: Business conflict }
```

Method quyết định HTTP semantics; `operationId` chỉ là định danh tài liệu, **không phải** idempotency key. Thay `operationId` hoặc thay media type/required parameters có thể phá client đã được sinh mã.

## 4. Parameters: bốn vị trí, bốn kiểu ràng buộc

OpenAPI 3.x khai báo một Parameter Object với `name`, `in`, `required`, và thường có `schema`. Bốn giá trị `in` là:

| `in` | Vị trí thực | Ví dụ | Trường hợp điển hình |
| --- | --- | --- | --- |
| `path` | Một thành phần của URI path. | `/orders/{orderId}` | Định danh tài nguyên; **bắt buộc** `required: true`. |
| `query` | Query string phía sau `?`. | `?page=2&size=20` | Filter, sort, pagination, search. |
| `header` | HTTP request header. | `If-Match: "v3"` | Conditional request, idempotency/correlation theo hợp đồng. |
| `cookie` | Cookie được gửi cùng request. | `Cookie: preference=compact` | Trường hợp cần state cookie; cân nhắc CSRF và bảo mật. |

Ví dụ đầy đủ cho query:

```yaml
parameters:
  - name: page
    in: query
    description: 1-based page number
    required: false
    schema:
      type: integer
      minimum: 1
      default: 1
  - name: size
    in: query
    required: false
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
  - name: status
    in: query
    required: false
    schema:
      type: string
      enum: [NEW, PAID, CANCELLED]
```

`default: 20` mô tả giá trị mặc định **theo contract**, chứ không làm framework Spring tự dùng 20 khi client bỏ tham số. Controller phải thực thi mặc định đó. Ngược lại, `required: false` không có nghĩa chuỗi rỗng hay giá trị ngoài miền sẽ được tự động chấp nhận.

### Path: phải khớp tên và kiểu

```yaml
- name: orderId
  in: path
  required: true
  schema: { type: integer, format: int64, minimum: 1 }
```

Path expression `{orderId}` phải khớp với `name: orderId`; không đặt `in: query` rồi kỳ vọng route `/orders/{orderId}` được mô tả chính xác. Nếu path thực nhận UUID, schema phải phản ánh kiểu ấy; OpenAPI không tự chuyển ID của database sang schema mong muốn.

### Header: giá trị không đồng nghĩa với quyền

```yaml
- name: If-Match
  in: header
  required: true
  description: Strong ETag of the current order representation
  schema: { type: string }
  example: '"order-42-v3"'
```

Dù OpenAPI đánh dấu bắt buộc, Spring/API gateway vẫn phải kiểm tra việc có header và **đánh giá HTTP precondition**. Đối với endpoint yêu cầu strong ETag cụ thể, thiếu header có thể trả `428 Precondition Required` theo contract; validator đã gửi nhưng không còn khớp có thể trả `412 Precondition Failed`.

Các header HTTP chuẩn như **`Authorization`, `Content-Type` và `Accept` không nên được mô tả bằng Parameter Object có `in: header`**; theo OpenAPI, định nghĩa header parameter mang các tên này bị bỏ qua. Thay vào đó:

- `Authorization`: khai báo `components.securitySchemes` và `security`.
- `Content-Type`: suy từ key trong `requestBody.content`.
- `Accept`: các media type mà `responses[*].content` hỗ trợ.

Header nghiệp vụ như `Idempotency-Key` hoặc `If-Match` có thể là parameter đúng nghĩa.

## 5. Serialization: cùng một mảng có thể có nhiều hình thức URL

Schema định nghĩa **giá trị logic**, nhưng client còn cần biết serialize thành query string như thế nào. Hai thuộc tính quan trọng là `style` và `explode`.

Ví dụ filter nhiều trạng thái:

```yaml
- name: status
  in: query
  required: false
  style: form
  explode: true
  schema:
    type: array
    items:
      type: string
      enum: [NEW, PAID, CANCELLED]
```

Theo kiểu `form` và `explode: true`, client gửi:

```http
GET /api/orders?status=NEW&status=PAID HTTP/1.1
```

Nếu dùng `explode: false` với `style: form`, biểu diễn điển hình là:

```http
GET /api/orders?status=NEW,PAID HTTP/1.1
```

Hai dạng này **không thể coi như tương đương** nếu server chỉ hỗ trợ một dạng. Spring binding/query parser, gateway và client SDK phải được kiểm thử với cấu hình serialization đã công bố.

Một vài quy tắc hữu ích:

- Query parameter mặc định thường dùng `style: form`; default `explode` phụ thuộc style, với `form` thường là `true`.
- Path/header có kiểu serialization khác, chẳng hạn `simple`; không mặc định áp quy tắc của query cho mọi vị trí.
- `deepObject` có thể mô tả một **query object phẳng**, ví dụ `filter[status]=PAID`; hành vi cho object lồng nhiều cấp không được chuẩn hóa đủ để tự suy ra từ mọi SDK.
- Percent-encoding và ký tự dành riêng trong URI phải được xử lý đúng. `allowReserved` không có nghĩa có thể bỏ toàn bộ encoding hay cho phép injection.
- Parameter identity là (`name`, `in`). Tên của header không phân biệt hoa/thường theo HTTP; API không nên tạo những header parameter chỉ khác chữ hoa.

**Không nối chuỗi SQL từ `sort` hay filter** chỉ vì đầu vào đã được khai báo trong OpenAPI. `schema` giúp tài liệu hóa và tạo client, còn runtime vẫn cần validation/allowlist và parameterized query.

## 6. requestBody: nội dung HTTP khác parameters

Một `requestBody` có dạng:

```yaml
requestBody:
  description: Order data to create
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
```

Ba cấp `required` cần phân biệt:

1. **`requestBody.required: true`**: theo contract, operation yêu cầu **có request body**; mặc định của thuộc tính này là `false`.
2. **`schema.required: [productId, quantity]`**: trong JSON object, các **property này phải xuất hiện**. Nó không quy định HTTP body tự có.
3. **`nullable`/kiểu chấp nhận `null`**: giá trị property có được phép là `null` không. Trong **OpenAPI 3.1**, dựa trên JSON Schema, có thể viết `type: ["string", "null"]`; `required` chỉ liên quan đến hiện diện property, không tự cấm null.

Ví dụ schema:

```yaml
components:
  schemas:
    CreateOrderRequest:
      type: object
      additionalProperties: false
      required: [productId, quantity]
      properties:
        productId:
          type: integer
          format: int64
          minimum: 1
        quantity:
          type: integer
          minimum: 1
          maximum: 100
        note:
          type: ["string", "null"]
          maxLength: 500
```

Giả sử body hợp lệ:

```json
{"productId":15,"quantity":2,"note":null}
```

Body không hợp lệ:

```json
{"productId":15,"quantity":0}
```

Ở ví dụ thứ hai, JSON **đúng cú pháp** nhưng vi phạm ràng buộc `minimum: 1`. API có thể trả `400` hoặc `422 Unprocessable Content` theo chính sách validation đã công bố; việc file OpenAPI có ràng buộc không tự chọn status thay server.

### Media type thuộc requestBody.content

Một operation có thể chấp nhận một hoặc nhiều media type:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
      examples:
        basic:
          summary: Two items
          value: { productId: 15, quantity: 2 }
```

`application/json` là nội dung `Content-Type` mà client phải gửi; `Accept` dùng để thương lượng media type **response**. Nếu endpoint chỉ nhận JSON và client gửi `text/plain`, HTTP status phù hợp thường là **`415 Unsupported Media Type`**, không phải lỗi “thiếu query parameter”.

Các nội dung khác cần mô tả bằng media type chính xác:

| Media type | Dùng khi | Lưu ý |
| --- | --- | --- |
| `application/json` | Tạo/cập nhật resource bằng JSON. | Kiểm tra required fields, enums và schema. |
| `application/merge-patch+json` | PATCH theo JSON Merge Patch. | `null` có ngữ nghĩa xóa member trong patch; không coi như JSON bất kỳ. |
| `application/json-patch+json` | PATCH theo danh sách JSON Patch operations. | Schema là danh sách lệnh `op/path/value` phù hợp. |
| `multipart/form-data` | Nhiều part, có thể chứa file cùng metadata. | Schema object mô tả các part; `encoding` có thể bổ sung media type từng property. |
| `application/x-www-form-urlencoded` | Dữ liệu form encoded trong body. | Vẫn nằm trong `requestBody`, không chuyển thành `parameters: query`. |

**Không lạm dụng body của GET.** HTTP không định nghĩa ngữ nghĩa chung cho nội dung của GET, và nhiều client/proxy/toolchain không hỗ trợ đáng tin cậy. Để truy vấn collection, ưu tiên query parameters đã khai báo; nếu query phức tạp cần body, thiết kế một operation phù hợp (ví dụ POST search) với semantics và cache policy được giải thích rõ.

## 7. Ví dụ OpenAPI 3.1 hoàn chỉnh ở mức bài học

Đoạn sau là một hợp đồng tối thiểu có thể dùng để thực hành `paths`, operations, parameters, requestBody và security. `servers.url` đã có hậu tố `/api` nên keys chỉ dùng `/orders`. Đây là bản minh họa cho một sản phẩm giả định; production cần bổ sung policy idempotency/authorization chi tiết và các response khác nếu có.

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
servers:
  - url: https://api.example.test/api
security:
  - bearerAuth: []

paths:
  /orders:
    get:
      operationId: listOrders
      tags: [Orders]
      summary: List orders visible to caller
      parameters:
        - name: page
          in: query
          schema: { type: integer, minimum: 1, default: 1 }
        - name: size
          in: query
          schema: { type: integer, minimum: 1, maximum: 100, default: 20 }
        - name: status
          in: query
          style: form
          explode: true
          schema:
            type: array
            items:
              type: string
              enum: [NEW, PAID, CANCELLED]
      responses:
        '200':
          description: Matching orders
          content:
            application/json:
              schema: { $ref: '#/components/schemas/OrderPage' }
        '401': { description: Authentication required }
        '403': { description: Forbidden }

    post:
      operationId: createOrder
      tags: [Orders]
      summary: Create an order
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: { type: string, minLength: 1, maxLength: 128 }
          description: Key for deduplicating retries within published window
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/CreateOrderRequest' }
            examples:
              basic:
                value: { productId: 15, quantity: 2 }
      responses:
        '201':
          description: Created
          headers:
            Location:
              description: URI of the created order
              schema: { type: string }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Order' }
        '400': { description: Malformed request }
        '401': { description: Authentication required }
        '403': { description: Forbidden }
        '409': { description: Stock or idempotency conflict }
        '415': { description: Unsupported media type }
        '422': { description: Valid JSON with invalid field values }

  /orders/{orderId}:
    parameters:
      - name: orderId
        in: path
        required: true
        schema: { type: integer, format: int64, minimum: 1 }
    get:
      operationId: getOrder
      tags: [Orders]
      responses:
        '200':
          description: Current order
          headers:
            ETag:
              description: Strong validator used by conditional PATCH
              schema: { type: string }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Order' }
        '401': { description: Authentication required }
        '403': { description: Forbidden }
        '404': { description: Order not found or not disclosed }

    patch:
      operationId: patchOrder
      tags: [Orders]
      summary: Update note if representation has not changed
      parameters:
        - name: If-Match
          in: header
          required: true
          description: Current strong entity tag from GET
          schema: { type: string }
          example: '"order-42-v3"'
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema: { $ref: '#/components/schemas/OrderNotePatch' }
      responses:
        '204': { description: Updated; GET to obtain new ETag }
        '400': { description: Invalid request }
        '401': { description: Authentication required }
        '403': { description: Forbidden }
        '404': { description: Order not found or not disclosed }
        '409': { description: Business state conflict }
        '412': { description: If-Match condition failed }
        '415': { description: Unsupported patch media type }
        '428': { description: If-Match required }

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateOrderRequest:
      type: object
      additionalProperties: false
      required: [productId, quantity]
      properties:
        productId: { type: integer, format: int64, minimum: 1 }
        quantity: { type: integer, minimum: 1, maximum: 100 }
        note: { type: ["string", "null"], maxLength: 500 }
    OrderNotePatch:
      type: object
      additionalProperties: false
      properties:
        note: { type: ["string", "null"], maxLength: 500 }
    Order:
      type: object
      required: [id, status]
      properties:
        id: { type: integer, format: int64 }
        status: { type: string, enum: [NEW, PAID, CANCELLED] }
        note: { type: ["string", "null"] }
    OrderPage:
      type: object
      required: [items, page, size, hasNext]
      properties:
        items:
          type: array
          items: { $ref: '#/components/schemas/Order' }
        page: { type: integer, minimum: 1 }
        size: { type: integer, minimum: 1 }
        hasNext: { type: boolean }
```

**Hai điểm cần chủ ý hoàn thiện khi triển khai:**

- `GET /orders/{orderId}` phải **thực sự phát** `ETag` mạnh đúng với representation như `responses.'200'.headers.ETag` mô tả. Test phải kiểm tra header này; đừng để PATCH đòi validator mà API không có đường lấy.
- `OrderNotePatch` dùng JSON Merge Patch, trong đó `note: null` mang nghĩa **xóa member** theo RFC 7396; server phải định nghĩa rõ liệu xóa ghi chú là hợp lệ. Việc khai báo nullable một cách máy móc không thay thế ngữ nghĩa patch.

## 8. Ánh xạ sang Java/Spring MVC

| OpenAPI | Spring MVC | Điều phải thực thi |
| --- | --- | --- |
| `paths./orders.get` | `@GetMapping` | Query filters, giới hạn pagination, quyền xem. |
| `in: path` | `@PathVariable` | Đúng tên và kiểu `orderId`. |
| `in: query` | `@RequestParam` | Default, min/max, giá trị enum và serialization. |
| `in: header` | `@RequestHeader` | Có mặt **và** hợp lệ, ví dụ idempotency key. |
| `requestBody.content` | `@RequestBody`, `consumes` | Media type, parse JSON, Bean Validation. |
| `responses.'201'` | `ResponseEntity.created(...)` | Tạo resource và `Location` chính xác. |

Ví dụ skeleton Spring Boot 3 (đã rút gọn phần persistence/security):

```java
record CreateOrderRequest(
    @jakarta.validation.constraints.NotNull
    @jakarta.validation.constraints.Positive Long productId,
    @jakarta.validation.constraints.NotNull
    @jakarta.validation.constraints.Min(1)
    @jakarta.validation.constraints.Max(100) Integer quantity
) {}

record OrderView(long id, String status) {}

@RestController
@RequestMapping("/api/orders")
@Validated
class OrderController {
    private final OrderService service;
    OrderController(OrderService service) { this.service = service; }

    @GetMapping
    ResponseEntity<?> list(
        java.security.Principal user,
        @RequestParam(defaultValue = "1") @Min(1) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
        @RequestParam(required = false) java.util.List<String> status) {
        return ResponseEntity.ok(
            service.listVisible(user.getName(), page, size, status));
    }

    @PostMapping(consumes = "application/json")
    ResponseEntity<OrderView> create(
        java.security.Principal user,
        @RequestHeader("Idempotency-Key") String key,
        @Valid @RequestBody CreateOrderRequest body) {
        OrderView order = service.create(user.getName(), key, body);
        return ResponseEntity
            .created(java.net.URI.create("/api/orders/" + order.id()))
            .body(order);
    }
}
```

Các import cho MVC/Bean Validation và `OrderService` cần được bổ sung trong dự án. `@Validated` và `@Valid` chưa tự đảm bảo mọi quy tắc: kiểm tra `status` theo enum, giới hạn `Idempotency-Key`, khóa chống tạo trùng, authz theo tenant và validation DTO/JSON tùy cấu hình. `additionalProperties: false` trong schema cũng cần cấu hình Jackson hoặc runtime validator tương ứng để từ chối field lạ.

Đối với `GET /orders/{orderId}`, hãy phát strong `ETag` nếu `PATCH` yêu cầu `If-Match`; service phải kiểm tra version bằng cập nhật nguyên tử, không chỉ kiểm tra chuỗi ở controller. Mô tả OpenAPI và code phải nhất quán về `415` khi sai `Content-Type` và `400/422` khi input sai.

## 9. Dùng lại parameter/schema bằng components

```yaml
components:
  parameters:
    Page:
      name: page
      in: query
      schema: { type: integer, minimum: 1, default: 1 }
paths:
  /products:
    get:
      parameters:
        - $ref: '#/components/parameters/Page'
      responses:
        '200': { description: Product page }
```

`components.schemas` dùng cho JSON schemas, `components.parameters` cho Parameter Objects, `components.requestBodies` cho Request Body Objects; `$ref` phải trỏ đúng loại và giải được. Chỉ reuse khi ý nghĩa contract giống nhau. OpenAPI **3.1** dùng JSON Schema gần chuẩn hơn so với 3.0; lưu ý khác biệt về nullable/union types và khả năng hỗ trợ của linter, SDK generator trước khi chuyển phiên bản.

## 10. Authentication, authorization và lỗi

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
```

Đây là **mô tả cơ chế**, không tự xác minh JWT hoặc chứng minh user có quyền với order. Server cần kiểm tra quyền ở mỗi operation; `401` cho thiếu xác thực hợp lệ, `403` cho hành động bị từ chối, hoặc `404` khi chính sách yêu cầu che giấu tài nguyên. Một operation có `security: []` có thể ghi đè chính sách bảo mật thừa kế: kiểm tra kỹ trước phát hành.

Ghi các mã lỗi có ý nghĩa như `400`, `401/403`, `404`, `409`, `412/428`, `415`, `422` và `429` nếu được API sử dụng. Phản hồi nên định nghĩa `application/problem+json` với `type`, `title`, `status`, `detail` và `code` ổn định; đừng xuất SQL/stack trace/secret ra public response. `bearerFormat: JWT` chỉ là hint định dạng token.

## 11. Kiểm thử contract và drift

Đừng chỉ validate rằng YAML parse được. Cần kiểm tra **cấu trúc**, **HTTP runtime** và **quyền/tính đúng đắn**.

| Test | Yêu cầu | Kỳ vọng |
| --- | --- | --- |
| Path/query | `GET /orders?page=0`, `size=101` | 4xx đúng contract, không truy vấn vô hạn. |
| Query serialization | `?status=NEW&status=PAID` | Server nhận hai giá trị theo `form/explode=true`. |
| Path binding | `GET /orders/abc` khi ID là số | Lỗi kiểu/path rõ; không lấy sai đơn. |
| Media type | POST body `text/plain` | `415` khi chỉ cho phép JSON. |
| Required body/fields | POST không body, thiếu `quantity`, `quantity=0` | Lỗi theo contract; không tạo resource. |
| Header/created | POST thiếu key hoặc POST hợp lệ | Header bị từ chối đúng; thành công `201` + `Location` đúng. |
| Authz | User B đọc order A | `403/404` theo chính sách, không tiết lộ dữ liệu. |
| Conditional patch | Thiếu `If-Match` hoặc tag cũ | `428/412`; không mất cập nhật. |
| Idempotency | Retry POST cùng key/payload | Không tạo hai đơn logic. |
| Evolution | Thay `operationId`, media type, required field | CI phát hiện breaking change ngoài chủ ý. |

MockMvc có thể xác nhận HTTP contract của POST:

```java
@Test
void createdResponseIncludesLocation() throws Exception {
    when(service.create(eq("alice"), eq("once"), any()))
        .thenReturn(new OrderView(42L, "NEW"));
    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .header("Idempotency-Key", "once")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"productId\":15,\"quantity\":2}"))
        .andExpect(status().isCreated())
        .andExpect(header().string("Location", "/api/orders/42"))
        .andExpect(jsonPath("$.id").value(42));
}
```

Đây là **test skeleton** (cần MockMvc, security-test, Mockito và service mock). Nó không chứng minh idempotency hay authorization nếu service được mock; bổ sung integration tests với DB thật, nhiều requests cạnh tranh và principal khác nhau.

CI nên đi qua: **parse OAS 3.1 → lint/resolve `$ref` → kiểm tra compatibility → HTTP contract tests → security/concurrency tests**. Dù dùng contract-first hay springdoc/code-first, phải kiểm tra drift giữa spec và runtime.

## 12. Lỗi thiết kế thường gặp

| Sai | Đúng |
| --- | --- |
| `paths: /orders?page=1` | `paths: /orders`, `page` là query parameter. |
| `/orders/{id}` thiếu `in: path, required: true` | Khai báo parameter trùng tên template. |
| JSON body đặt vào `parameters` | Dùng `requestBody.content.application/json`. |
| `Authorization` hoặc `Content-Type` là header parameter | Dùng security scheme và media type ở requestBody. |
| Nhầm `requestBody.required` với `schema.required` | Kiểm tra riêng có body và có property. |
| `operationId` trùng hoặc đổi tùy tiện | ID duy nhất, ổn định cho SDK. |
| Schema đúng nhưng runtime không validate | Dùng Bean Validation, config JSON, integration tests. |
| Chỉ mô tả `200` dù trả `201/204/409` | Mô tả status/headers/errors thực tế. |
| Dùng Swagger UI chạy thử và coi là contract QA | Có lint, CI contract tests và security tests. |

## 13. Bài thực hành: OpenAPI cho phiếu hỗ trợ

Thiết kế `GET /api/tickets` (filter `status` nhiều giá trị, `page` 1-based, `size` tối đa 50), `POST /api/tickets` (JSON `subject`, `description`, bắt buộc `Idempotency-Key`), `GET /api/tickets/{ticketId}` và `PATCH /api/tickets/{ticketId}` (Merge Patch, `If-Match`).

**Yêu cầu:** khai báo hai Path Items và bốn Operations với `operationId` duy nhất; `ticketId` trong path, `page/size/status` trong query, key và ETag trong header; schemas `CreateTicketRequest`, `Ticket`, `TicketPatch`; `201` với `Location`, `204` khi patch thành công, `401/403/404/409/412/415/428` khi phù hợp; Bearer security và Problem Details. Viết thêm controller skeleton và tối thiểu sáu tests gồm serialization, validation, media type, quyền, stale ETag và retry POST.

Ví dụ request cần mô tả đúng:

```http
GET /api/tickets?status=OPEN&status=PENDING&page=2&size=10 HTTP/1.1
Accept: application/json
```

```http
PATCH /api/tickets/101 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "ticket-101-v2"

{"subject":"Cần hỗ trợ đăng nhập"}
```

**Tự kiểm:** GET dùng query parameters; POST/PATCH dùng requestBody, header không nằm trong JSON; path template buộc có path parameter; `If-Match` không khớp trả `412` theo ngữ nghĩa HTTP, thiếu điều kiện bắt buộc có thể `428`. Kiểm tra quyền ngoài schema.

## 14. Checklist xuất bản

- [ ] `paths` và `servers` tạo đúng URI; mọi path template có parameter bắt buộc.
- [ ] Mỗi operation có `operationId` duy nhất, `responses` và HTTP semantics rõ.
- [ ] Query/path/header/cookie parameters có schema và serialization đúng.
- [ ] Body dùng `requestBody.content` đúng media type; phân biệt body-required/property-required.
- [ ] Authentication, authorization, lỗi và response headers được mô tả/kiểm thử.
- [ ] `$ref` giải được, schema và Spring runtime nhất quán, CI kiểm tra compatibility.

**Kết luận:** `paths` định nghĩa **tài nguyên ở đâu**, operation định nghĩa **phương thức và hành vi**, `parameters` định nghĩa **dữ liệu URI/header/cookie**, còn `requestBody` định nghĩa **nội dung HTTP body**. Một hợp đồng OpenAPI chỉ đáng tin khi hành vi runtime, client SDK và kiểm thử đều tuân theo nó.
