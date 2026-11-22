# $ref, components và tổ chức tài liệu có thể tái sử dụng

## 1. Vì sao hợp đồng OpenAPI cần tái sử dụng?

Một REST API quản lý đơn hàng có hàng chục endpoint dùng chung `Order`, `Problem`, `orderId`, header xác thực và phân trang. Nếu copy-paste từng schema, khi đổi kiểu `amountMinor` một nơi dễ bị bỏ sót; SDK sinh từ OpenAPI bắt đầu lệch response thực tế.

Trong chương **Hợp đồng OpenAPI** của module **INTEGRATION_API_REST**, mục tiêu là định nghĩa **một lần những thành phần cùng ngữ nghĩa**, rồi tham chiếu qua `$ref`. Bài liên hệ trực tiếp resource/URI, HTTP methods/status, cache, idempotency, OpenAPI, xác thực/phân quyền, lỗi và kiểm thử Java/Spring.

Sau bài này, bạn sẽ:
1. Dùng `components` để chia sẻ schema, parameter, response, request body và security scheme.
2. Giải thích **JSON Pointer, external refs, Reference Object và Schema Object** theo OpenAPI 3.1.
3. Tổ chức tài liệu multi-file, kiểm soát compatibility, bảo mật, lint/bundle và đối chiếu runtime.

**Tư tưởng chính:** `$ref` **không phải copy-paste hay thừa kế có override tùy ý**. Chỉ chia sẻ khi **ngữ nghĩa giống nhau**; tạo hợp đồng riêng khi request/response hoặc quy tắc nghiệp vụ khác.

## 2. `components`: các định nghĩa có tên, không tự sinh endpoint

~~~yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
paths:
  /api/orders/{orderId}:
    get:
      responses:
        '200':
          description: Đơn hàng
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
components:
  schemas:
    Order:
      type: object
      required: [id, status]
      properties:
        id: {type: string, format: uuid}
        status: {type: string}
~~~

`paths` mô tả HTTP operations; `components` là **thư viện có tên**. Một schema trong components **không tự tạo route/controller, validation hay authorization**.

| Component | Nội dung tái sử dụng |
|---|---|
| `schemas` | Resource/DTO, Problem Details, pagination |
| `parameters` | Path/query/header/cookie parameters |
| `requestBodies` | Body/media type của request |
| `responses` | Response description, headers, content |
| `headers`, `examples` | Header Object, Example Object |
| `securitySchemes` | Bearer/OAuth2/API key |
| `links`, `callbacks` | Link/Callback Objects |
| `pathItems` (OAS 3.1) | Path Item Object |

Nếu một request body chỉ dùng ở một operation và không có ngữ nghĩa chia sẻ, để inline có thể dễ đọc hơn. **Ít dòng YAML không phải mục tiêu quan trọng hơn độ đúng.**

## 3. `$ref`: JSON Pointer, escaping và file bên ngoài

`$ref` chứa **URI reference**; fragment bắt đầu bằng `#/` thường là JSON Pointer tới đối tượng trong tài liệu:

~~~yaml
schema:
  $ref: '#/components/schemas/Order'
~~~

Đọc từ gốc tài liệu: `components` → `schemas` → `Order`. Tên **phân biệt chữ hoa/thường** và target phải là **đúng loại object**. Với key có ký tự đặc biệt, JSON Pointer escape **`~` thành `~0`** và **`/` thành `~1`**:

~~~yaml
components:
  schemas:
    'money/amount': {type: integer, minimum: 0}
    'Text~Code': {type: string}
# Được dùng trong ngữ cảnh có schema:
# $ref: '#/components/schemas/money~1amount'
# $ref: '#/components/schemas/Text~0Code'
~~~

Không dùng `#/components/schemas/money/amount`: nó chỉ vào hai segment, không phải một key. URI fragment còn cần percent-encoding khi có ký tự cần escape ở mức URI.

Với multi-file, đường dẫn được giải quyết **tương đối với file chứa `$ref`**:

~~~yaml
# Trong paths/order-by-id.yaml
schema:
  $ref: '../components/schemas/Order.yaml'
~~~

Nếu `Order.yaml` là **Schema Object**, dùng trực tiếp như trên. Nếu tham chiếu vào một OpenAPI document hoàn chỉnh, cần fragment: `../openapi.yaml#/components/schemas/Order`. Không mặc định `#/components/...` trong file path tự tìm root `openapi.yaml`.

Các file ref phục vụ **toolchain tài liệu**, không tự biến thành URL REST endpoint. Khi publish cần bundle hoặc bảo đảm docs/SDK có thể resolve tất cả dependency.

## 4. Reference Object khác với Schema Object `$ref` trong OAS 3.1

Trong OAS 3.1 có **hai ngữ cảnh**, với quy tắc siblings khác nhau:

**Reference Object** (ví dụ parameter/response):

~~~yaml
parameters:
  - $ref: '#/components/parameters/PageSize'
    required: true  # KHÔNG override định nghĩa PageSize!
~~~

Reference Object có thể có `summary` và `description` theo OAS 3.1, nhưng `required` cạnh `$ref` **không phải cách hợp lệ để chỉnh parameter**. Muốn parameter required ở operation khác, định nghĩa component mới hoặc khai báo inline.

**Schema Object** dùng **JSON Schema Draft 2020-12**; `$ref` là schema keyword và **được đi cùng keyword khác**:

~~~yaml
components:
  schemas:
    MoneyAmount:
      type: integer
      minimum: 0
    PositivePrice:
      $ref: '#/components/schemas/MoneyAmount'
      description: Giá dương
      exclusiveMinimum: 0
~~~

Ràng buộc từ `MoneyAmount` và `exclusiveMinimum` **đều có hiệu lực**; không có cơ chế “cái khai báo sau ghi đè cái trước”. Đừng áp máy móc hướng dẫn OpenAPI 3.0 cho 3.1.

**`allOf` là giao của các schema**, không phải inheritance:

~~~yaml
OrderSummary:
  allOf:
    - $ref: '#/components/schemas/ResourceIdentity'
    - type: object
      required: [status]
      properties:
        status: {type: string}
~~~

Cả identity và status đều phải hợp lệ. Cẩn thận **`additionalProperties: false`** trong schema con khi ghép `allOf`; với JSON Schema 2020-12 cần hiểu `unevaluatedProperties` nếu muốn giới hạn thuộc tính sau composition. `oneOf` yêu cầu đúng một nhánh, `anyOf` ít nhất một; `discriminator` không tự thay validator.

## 5. Ví dụ hợp đồng: dùng chung schema, parameter, response và security

Ví dụ OpenAPI 3.1 dưới đây cho **GET đơn hàng** và **POST tạo đơn**. API chọn bearer authentication, kiểm tra quyền theo tenant ở runtime; POST yêu cầu `Idempotency-Key` để nhận diện cùng intent khi retry.

~~~yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
security:
  - BearerAuth: []
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      parameters:
        - $ref: '#/components/parameters/OrderId'
      responses:
        '200':
          description: Đơn hàng được phép xem
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/Forbidden'
        '404':
          $ref: '#/components/responses/NotFound'
  /api/orders:
    post:
      operationId: createOrder
      parameters:
        - $ref: '#/components/parameters/IdempotencyKey'
      requestBody:
        $ref: '#/components/requestBodies/CreateOrderBody'
      responses:
        '201':
          description: Đã tạo đơn hàng
          headers:
            Location:
              description: URI resource mới
              schema: {type: string, format: uri-reference}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '409':
          $ref: '#/components/responses/Conflict'
components:
  parameters:
    OrderId:
      name: orderId
      in: path
      required: true
      schema: {type: string, format: uuid}
    IdempotencyKey:
      name: Idempotency-Key
      in: header
      required: true
      schema: {type: string, minLength: 1, maxLength: 200}
  requestBodies:
    CreateOrderBody:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateOrder'
  schemas:
    CreateOrder:
      type: object
      required: [cartId, shippingAddressId]
      properties:
        cartId: {type: string}
        shippingAddressId: {type: string}
      additionalProperties: false
    Order:
      type: object
      required: [id, status, amountMinor, currency]
      properties:
        id: {type: string, format: uuid}
        status:
          type: string
          enum: [PENDING_PAYMENT, PAID, CANCELLED]
        amountMinor: {type: integer, minimum: 0}
        currency: {type: string}
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
  responses:
    BadRequest:
      description: Request không hợp lệ
      content:
        application/problem+json:
          schema: {$ref: '#/components/schemas/Problem'}
    Unauthorized:
      description: Thiếu credential hợp lệ
      headers:
        WWW-Authenticate:
          schema: {type: string}
          example: Bearer
      content:
        application/problem+json:
          schema: {$ref: '#/components/schemas/Problem'}
    Forbidden:
      description: Không có quyền
      content:
        application/problem+json:
          schema: {$ref: '#/components/schemas/Problem'}
    NotFound:
      description: Không có hoặc không được tiết lộ
      content:
        application/problem+json:
          schema: {$ref: '#/components/schemas/Problem'}
    Conflict:
      description: Trạng thái/khóa idempotency xung đột
      content:
        application/problem+json:
          schema: {$ref: '#/components/schemas/Problem'}
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

**Quan sát cách tái sử dụng:** `Order` chỉ mô tả **response**, `CreateOrder` chỉ mô tả **request**; `CreateOrderBody` bổ sung metadata cho body. `OrderId` giữ `name` khớp biến URI và `required=true`. Mỗi response lỗi có **status/description riêng** dù cùng dùng `Problem` với media type `application/problem+json`.

**Ranh giới hợp đồng:** Schema `Problem` này yêu cầu `type/title/status` như **quy tắc riêng của API**; RFC 9457 không bắt tất cả các trường đó luôn hiện diện. `BearerAuth` không thay kiểm tra quyền trên một đơn cụ thể. POST retry có thể trả **201 được replay/200 hiện trạng/202 in-flight**, nhưng ví dụ chỉ mô tả nhánh tạo mới; phải bổ sung các response khác theo implementation thật. Header `Idempotency-Key` không tự thực thi chống trùng.

## 6. Vì sao không dùng một schema cho mọi ngữ cảnh?

Một lỗi phổ biến là dùng `Order` cho cả **POST request**, **GET response**, **PATCH request**, **list item** và **event payload** chỉ để đạt mục tiêu “không trùng code”. Cách này thường khiến client được quyền gửi các trường server quản lý hoặc schema thêm ràng buộc sai.

| Ngữ cảnh | Schema nên cân nhắc | Vì sao |
|---|---|---|
| POST tạo mới | `CreateOrder` | Không cho client tự đặt `id`, `createdAt`, tổng tiền |
| GET chi tiết | `Order` | Có thông tin đầy đủ và server-generated fields |
| GET collection | `OrderSummary`, `OrderPage` | Item rút gọn, pagination metadata và next link |
| PATCH cập nhật | `UpdateOrderAddress` | Chỉ các trường có quyền thay đổi và semantics riêng |
| Event gửi ra broker | `OrderChangedEvent` | Version/event ID, không nhất thiết là HTTP response |
| Lỗi validation | `ValidationProblem` nếu khác lỗi chung | Có extension về trường và quy tắc |

Nếu hai cấu trúc thật sự dùng chung `Money`, `Address` hoặc `PageInfo`, hãy trích những **value objects** ấy thành schema tái sử dụng. Nhưng **đừng áp một “God schema”** cho mọi operation.

### `readOnly` và `writeOnly` không giải quyết tất cả

OpenAPI có `readOnly`/`writeOnly` để đánh dấu vai trò của trường trong request/response. Điều này hữu ích, nhưng với input nghiệp vụ khác biệt lớn, tách `CreateOrder` khỏi `Order` vẫn dễ hiểu hơn và tránh code generator/validator diễn giải quá lỏng.

Với OpenAPI 3.1, các trường optional/nullable nên theo JSON Schema, ví dụ:

~~~yaml
nextCursor:
  type: [string, 'null']
~~~

Đừng áp `nullable: true` từ các ví dụ OAS 3.0 rồi kỳ vọng nó là JSON Schema validation tương đương trong OAS 3.1.

## 7. Tái sử dụng parameter, header và lỗi mà không làm sai HTTP

Một `Parameter Object` có tên, vị trí và schema xác định; với **path parameter**, `required` phải là `true`. Với query `limit`/`after`:
 
~~~yaml
components:
  parameters:
    PageSize:
      name: limit
      in: query
      schema: {type: integer, minimum: 1, maximum: 100, default: 20}
    Cursor:
      name: after
      in: query
      description: Opaque cursor
      schema: {type: string}
~~~

Một operation tham chiếu bằng hai `$ref` trong `parameters`. Tránh hai parameter cùng bộ **`(name, in)`** trong cùng operation. Parameter cùng `name/in` ở operation có thể override một parameter ở path level theo OAS, nhưng `required` cạnh **Reference Object** không phải override.

`components.headers` chứa **response Header Object**, không phải request parameter. Ví dụ:

~~~yaml
components:
  headers:
    RetryAfter:
      description: Số giây trước khi thử lại
      schema: {type: integer, minimum: 0}
  responses:
    RateLimited:
      description: Vượt hạn mức
      headers:
        Retry-After:
          $ref: '#/components/headers/RetryAfter'
~~~

HTTP `Retry-After` có thể là **delay-seconds hoặc HTTP-date**; schema integer trên chỉ đúng nếu API cam kết phát seconds. Đừng tạo một `GenericError` cho mọi status khiến client không phân biệt được **401 (authentication challenge), 403 (authorization), 404 (not found), 409 (conflict), 429 (rate limit), 503 (unavailable)**. Có thể chia sẻ schema `Problem` nhưng giữ status, description, headers và client behavior đúng từng lỗi.

## 8. Tách tài liệu lớn thành nhiều file nhưng giữ rõ nguồn tham chiếu

Với một API có hàng trăm operation, một `openapi.yaml` khổng lồ có thể khó review. Có thể tổ chức theo **resource/bounded context**:

~~~text
api-contract/
  openapi.yaml
  paths/
    orders.yaml
    order-by-id.yaml
  components/
    schemas/
      Order.yaml
      CreateOrder.yaml
      Problem.yaml
    parameters/
      OrderId.yaml
      IdempotencyKey.yaml
    responses/
      Unauthorized.yaml
      NotFound.yaml
~~~

Ví dụ root chỉ trỏ tới các **Path Item Objects**:

~~~yaml
# openapi.yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
paths:
  /api/orders:
    $ref: './paths/orders.yaml'
  /api/orders/{orderId}:
    $ref: './paths/order-by-id.yaml'
~~~

Một path file:

~~~yaml
# paths/order-by-id.yaml
get:
  operationId: getOrder
  parameters:
    - $ref: '../components/parameters/OrderId.yaml'
  responses:
    '200':
      description: Đơn hàng
      content:
        application/json:
          schema:
            $ref: '../components/schemas/Order.yaml'
    '404':
      $ref: '../components/responses/NotFound.yaml'
~~~

**Cực kỳ quan trọng:** `#/components/schemas/Order` nếu viết **bên trong `paths/order-by-id.yaml`** sẽ tìm `components` của **chính file path đó** theo cơ chế tham chiếu, không tự nhảy về `openapi.yaml`. Cần dùng **relative file path chính xác**, hoặc một URI/fragment được định nghĩa nhất quán và được bundler hỗ trợ.

### Bundling khác với dereferencing

- **Bundle:** đóng gói các tài liệu rời thành artifact giao cho SDK, docs portal, gateway; thường giữ các `$ref` nội bộ để tránh nhân bản.
- **Dereference:** thay các `$ref` bằng nội dung được tham chiếu khi tool hỗ trợ; dễ tạo bản rất lớn hoặc gặp **vòng tham chiếu**.
- **Validate/lint:** phân tích tính hợp lệ OAS, unresolved refs, schema/security conventions, naming và style.

Một quy trình có thể là **source multi-file → validate/lint → bundle → publish artifact đã kiểm tra**. Có công cụ hỗ trợ reference ngoài và có công cụ chỉ nhận single-file; hãy kiểm tra khả năng của **đúng version công cụ** đang dùng, không giả định mọi importer đều xử lý `paths.$ref` giống nhau.

### Ranh giới sở hữu tài liệu

Nên có owner cho từng bounded context. Nhóm Checkout có thể sở hữu `CreateOrder`, nhóm Catalog sở hữu `Product`, trong khi `Problem`, authentication scheme hoặc pagination conventions do nhóm API platform quản lý. Một shared schema thay đổi nên được review bởi **mọi consumer bị ảnh hưởng**, bởi một sửa nhỏ có thể lan tới hàng chục endpoint.

## 9. Vòng tham chiếu và thay đổi shared schema

Một schema có thể đệ quy:
 
~~~yaml
components:
  schemas:
    CategoryNode:
      type: object
      required: [id]
      properties:
        id: {type: string}
        children:
          type: array
          items:
            $ref: '#/components/schemas/CategoryNode'
~~~

Đây là mô hình hợp lệ cho cây, nhưng **dereference toàn bộ hoặc code generator** có thể gặp recursion; cần kiểm tra với toolchain. Vòng `A → B → A` không chứa cấu trúc có ý nghĩa thường là lỗi thiết kế.

Với shared `Order` được 12 operation sử dụng, một thay đổi có thể lan sang cả 12:

- Thêm **required field**, đổi kiểu, bỏ trường hay đổi relation/status semantics thường **breaking**.
- Thêm trường optional ít rủi ro hơn nhưng client quá nghiêm ngặt vẫn có thể lỗi.
- Mở rộng enum cần kiểm tra client xử lý trạng thái lạ; đổi security requirement/status cũng là thay đổi hợp đồng.
- Đổi tên component/đường dẫn file có thể phá toolchain dù REST runtime không đổi.

Hãy có **owner và compatibility diff** cho shared components; kiểm thử cả operation sử dụng chúng. `info.version` chỉ gắn nhãn tài liệu, không tự thực hiện migration.

## 10. Security: chia sẻ cơ chế, không chia sẻ quyền truy cập

~~~yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - BearerAuth: []
~~~

Với HTTP bearer scheme, mảng `[]` **không phải roles**. Server vẫn phải kiểm tra **BOLA/object-level authorization** theo principal, tenant, `orderId`; OAS không thay runtime check. Root `security` mặc định áp dụng cho operations, nhưng **`security: []` tại operation làm endpoint public trong tài liệu**; cần review tránh mở nhầm.

Các entry khác nhau trong mảng `security` biểu thị **OR**; nhiều schemes trong cùng Security Requirement Object biểu thị **AND**. Chỉ mô tả lựa chọn mà server thật hỗ trợ, không thêm API key chỉ để “đầy đủ”.

**Remote `$ref` là dependency cần tin cậy.** Pin version, cho phép đúng origin/repository, hạn chế quyền truy cập filesystem/network của resolver, tránh đưa secret hoặc đường dẫn nội bộ vào artifact công khai. Với response, không đưa trường nội bộ nhạy cảm vào schema shared rồi vô ý dùng nó cho endpoint public. Kiểm thử **401, 403, cross-tenant và tải artifact có quyền**.

## 11. Java/Spring: từ controller đến `components.schemas`

Hai chiến lược:

- **Design-first:** Hợp đồng OpenAPI được review/lint trước, sinh interface/DTO hoặc test và đối chiếu runtime.
- **Code-first:** Spring controller/DTO là nguồn; dùng generator OpenAPI (ví dụ springdoc-openapi phù hợp Spring Boot version), rồi review artifact đã sinh để chống drift.

Ví dụ **Spring Boot 3 + Swagger annotations**:

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

record OrderResponse(
    UUID id, String status, long amountMinor, String currency) {}
record CreateOrderRequest(String cartId, String shippingAddressId) {}

interface OrderService {
    OrderResponse getVisible(Authentication principal, UUID id);
    OrderResponse create(
        Authentication principal, String key, CreateOrderRequest request);
}

@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "BearerAuth")
class OrdersController {
    private final OrderService service;
    OrdersController(OrderService service) { this.service = service; }

    @GetMapping("/{orderId}")
    @Operation(operationId = "getOrder", summary = "Xem đơn hàng")
    @ApiResponse(responseCode = "200", description = "Đơn hàng",
        content = @Content(
            schema = @Schema(implementation = OrderResponse.class)))
    ResponseEntity<OrderResponse> get(
        Authentication principal, @PathVariable UUID orderId) {
        return ResponseEntity.ok(
            service.getVisible(principal, orderId));
    }

    @PostMapping
    @Operation(operationId = "createOrder", summary = "Tạo đơn hàng")
    ResponseEntity<OrderResponse> create(
        Authentication principal,
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody CreateOrderRequest request) {
        OrderResponse order = service.create(principal, key, request);
        return ResponseEntity.created(
            URI.create("/api/orders/" + order.id())).body(order);
    }
}
~~~

Đây là **mã minh họa**, chưa có security config, validation/exception handler, database và idempotency storage; không khẳng định đã chạy. `OrderService` phải kiểm tra tenant/role, triển khai transaction và chống trùng. OpenAPI được sinh từ annotation **có thể** tạo schema có tên trong `components` và `$ref`, nhưng tên component, required/nullability, security và Problem Details phụ thuộc công cụ/version.

Đối chiếu runtime GET với contract: **200**, `Content-Type: application/json`, các trường `id/status/amountMinor/currency` đúng kiểu. Nếu code đổi thành `amount` nhưng OpenAPI vẫn ghi `amountMinor`, đó là **contract drift** dù mọi `$ref` resolve thành công.

## 12. CI: parse, resolve, bundle, compatibility và runtime tests

~~~mermaid
flowchart LR
    A["OpenAPI source"] --> B["Resolve $ref + lint"]
    B --> C["Bundle artifact"]
    C --> D["Compatibility diff"]
    D --> E["HTTP contract tests"]
    E --> F["Publish spec/SDK"]
~~~

| Kiểm tra | Điều kiện đạt |
|---|---|
| **Resolve** | Không thiếu file, sai case, fragment hoặc dùng Response thay Schema |
| **OAS/schema** | Đúng version 3.1, JSON Schema và required/nullability/composition hợp lệ |
| **HTTP** | Method/status/media type/headers như Location, WWW-Authenticate đúng |
| **Security** | Không vô ý `security: []`; quyền theo tenant được test |
| **Change impact** | Shared schema đổi có compatibility check với consumer |
| **Publish** | Artifact bundled không chứa ref bị vỡ ở docs portal/SDK |

Tooling có thể `lint`, `bundle` hoặc dereference; **cú pháp CLI và hỗ trợ external refs tùy công cụ/version**. Bundle thành công **không chứng minh server trả đúng response**.

Kiểm thử HTTP với **MockMvc**:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersContractTest {
    @Autowired MockMvc mvc;
    @Test
    void getOrderMatchesContract() throws Exception {
        String id = "5f2a8d0c-1b44-46bd-9f88-6697cf5e4424";
        // Seed fixture và mock principal có quyền xem order.
        mvc.perform(get("/api/orders/{orderId}", id)
                    .accept("application/json"))
           .andExpect(status().isOk())
           .andExpect(content().contentTypeCompatibleWith(
               "application/json"))
           .andExpect(jsonPath("$.id").value(id))
           .andExpect(jsonPath("$.amountMinor").isNumber());
    }
}
~~~

**Test là khung minh họa**, không phải test đã chạy; cần fixture, auth và controller. MockMvc kiểm thử một route, **không tự validate toàn bộ `$ref`**; hãy kết hợp OpenAPI schema validator và contract test response thực.

Test lỗi có chủ đích: đổi pointer `Order` thành `Orders` (resolve fail), trả string thay integer (schema fail), thiếu `WWW-Authenticate` khi 401 (HTTP fail), dùng token tenant B đọc đơn tenant A (BOLA fail), và sửa shared `Order` thành required field mới (compatibility gate fail).

## 13. Bài tập: tìm và sửa tham chiếu sai

Cho OpenAPI 3.1:

~~~yaml
openapi: 3.1.0
info: {title: Catalog API, version: 1.0.0}
paths:
  /api/products/{productId}:
    get:
      parameters:
        - $ref: '#/components/parameters/ItemId'
          required: false
      responses:
        '200':
          description: Sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/responses/Product'
        '401':
          $ref: '#/components/responses/Error'
components:
  parameters:
    ItemId:
      name: itemId
      in: path
      required: true
      schema: {type: string}
  schemas:
    Product:
      type: object
      required: [id, name]
      properties:
        id: {type: string}
        name: {type: string}
  responses:
    Error:
      description: Lỗi
      content:
        application/problem+json:
          schema: {type: object}
~~~

**Yêu cầu:** (1) Nêu bốn lỗi/thiếu sót về `$ref`, parameter, HTTP; (2) sửa `parameters` và schema response 200; (3) nêu relative ref từ `paths/product-by-id.yaml` tới `components/schemas/Product.yaml`; (4) đề xuất test/CI; (5) giải thích khi nào `NotFound` nên chia sẻ hay chuyên biệt.

### Đáp án gợi ý

1. **Path mismatch:** `productId` ở URI nhưng `ItemId.name=itemId`; **reference sibling:** `required: false` không override `Parameter Object`, path parameter phải required; **wrong target type:** `200.schema` trỏ `responses/Product` thay vì `schemas/Product`; **401:** thiếu challenge `WWW-Authenticate` khi dùng HTTP authentication; chưa mô tả security scheme.
2. Định nghĩa `components.parameters.ProductId` với `name: productId, in: path, required: true`; sửa operation:
   
   ~~~yaml
   parameters:
     - $ref: '#/components/parameters/ProductId'
   responses:
     '200':
       description: Sản phẩm
       content:
         application/json:
           schema: {$ref: '#/components/schemas/Product'}
   ~~~

   Thêm `Unauthorized` response có `WWW-Authenticate`, body lỗi và security scheme phù hợp.
3. Trong file path, dùng `$ref: '../components/schemas/Product.yaml'`; không dùng fragment root sai ngữ cảnh.
4. Parse + resolve + bundle; contract test 200/schema, 401/challenge, 403/BOLA và compatibility diff nếu `Product` đổi.
5. Dùng shared `NotFound` nếu HTTP status, mô tả, Problem type và privacy policy giống nhau. Tách response khi error code/khả năng tiết lộ khác; vẫn có thể dùng chung schema `Problem`.

## 14. Checklist xuất bản hợp đồng

- [ ] Từng `$ref` resolve và **đúng loại object** tại vị trí sử dụng; JSON Pointer `~0`/`~1` và file path được kiểm tra.
- [ ] Phân biệt Reference Object và Schema Object trong OAS 3.1; không coi siblings là override tùy ý.
- [ ] Dùng `allOf/oneOf/anyOf` theo validation semantics, không chỉ phục vụ codegen.
- [ ] Request/response schemas tách khi cần; value objects có cùng nghĩa mới được chia sẻ.
- [ ] Path parameter required=true và tên khớp URI; không lặp `(name,in)`.
- [ ] Response reuse không xóa khác biệt **status/Content-Type/Location/WWW-Authenticate/Retry-After**.
- [ ] `securitySchemes` đúng runtime; kiểm tra `security: []`, 401/403, BOLA và quyền từng resource.
- [ ] Shared components có owner, version và compatibility checks.
- [ ] Multi-file source có quy trình **lint → resolve → bundle → publish**; remote refs được pin và tin cậy.
- [ ] Spring runtime, HTTP contract tests, JSON Schema và SDK/docs cùng phản ánh một hợp đồng.

**Kết luận:** `components` là thư viện tái sử dụng, `$ref` nối các mảnh tài liệu; giá trị thực đến từ **tính nhất quán ngữ nghĩa**, khả năng giải tham chiếu, kiểm tra tương thích và xác nhận runtime. Đừng đánh đổi đúng HTTP/bảo mật lấy YAML ngắn.

### Tài liệu nền

- **OpenAPI Specification 3.1:** Components, Reference Object, Path Item, Security và Schema Object.
- **JSON Schema 2020-12:** `$ref`, composition, validation, nullability.
- **RFC 6901:** JSON Pointer và escape.
- **RFC 9110, RFC 9457:** HTTP status/headers và Problem Details.
- **Spring Framework / springdoc-openapi:** annotations, generated OpenAPI và contract tests.

