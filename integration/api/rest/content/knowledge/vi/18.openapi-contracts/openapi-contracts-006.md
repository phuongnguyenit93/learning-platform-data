# Schema cho object, array, enum, null và trường bắt buộc

## 1. Mục tiêu và tình huống

Trong module **INTEGRATION_API_REST**, thiết kế REST API không dừng ở resource, URI, phương thức HTTP và status. Client còn phải biết **body có cấu trúc thế nào, trường nào bắt buộc, kiểu giá trị được phép, lúc nào được gửi null và khi schema thay đổi thì phiên bản cũ có còn hoạt động hay không**. Chương **Hợp đồng OpenAPI** diễn đạt những điều này thành contract có thể đọc, sinh SDK và kiểm thử.

Bài này dùng **OpenAPI 3.1** (Schema Object dựa trên JSON Schema 2020-12) để thiết kế:

- **object:** thuộc tính, object lồng nhau và chính sách field ngoài dự kiến;
- **array:** kiểu item, số lượng và tính duy nhất;
- **enum:** tập giá trị chấp nhận, rủi ro mở rộng enum;
- **null:** một giá trị JSON riêng, khác với vắng mặt;
- **required:** yêu cầu tên field hiện diện, **không đồng nghĩa** giá trị không null.

Tình huống xuyên suốt: endpoint **POST /api/v1/orders** nhận mã khách hàng, các dòng sản phẩm, độ ưu tiên và ghi chú giao hàng. Server sinh ID, trạng thái và thời điểm tạo; client không được tự đặt các trường do server sở hữu.

**Sau bài học**, bạn có thể viết schema OpenAPI 3.1 đầy đủ, ánh xạ sang DTO Java/Spring/Bean Validation, phân biệt nullable/optional/missing, tránh mass assignment và kiểm thử contract cả ở request lẫn response.

## 2. OpenAPI 3.1 không dùng nullable như OpenAPI 3.0

OpenAPI mô tả **paths, operations, security, requestBody, responses** và các schema dữ liệu. Trong **3.1**, Schema Object có nền tảng **JSON Schema Draft 2020-12**.

| Chủ đề | OpenAPI 3.0 | OpenAPI 3.1 |
| --- | --- | --- |
| String chấp nhận null | **type: string** cùng **nullable: true** | **type: [string, 'null']** |
| JSON Schema | Biến thể/tập con riêng | Tương thích JSON Schema 2020-12 với phần mở rộng OAS |
| Union kiểu | Thường dùng oneOf/anyOf | Có thể dùng **type** là mảng |
| Tham chiếu schema | **$ref** | **$ref**, cần hiểu quy tắc sibling của 3.1 |
| Tooling | Nhiều công cụ cũ hỗ trợ | Phải kiểm chứng phiên bản generator và validator |

Cú pháp 3.1:

~~~yaml
type: [string, 'null']
maxLength: 500
~~~

Cú pháp 3.0:

~~~yaml
type: string
nullable: true
maxLength: 500
~~~

**Không copy nullable: true vào tài liệu 3.1 và cho rằng validator phải chấp nhận null.** Cần kiểm tra phiên bản OpenAPI trước khi diễn giải từ khóa.

Một điểm nữa: **format: uuid**, **format: email**, **format: date-time** giúp mô tả định dạng, nhưng việc validator có thực thi kiểm tra format hay không phụ thuộc thư viện/cấu hình. Schema trong OpenAPI **không thay thế kiểm tra dữ liệu trên server**.

## 3. Object: properties, required và additionalProperties

JSON object:

~~~json
{
  "customerId": "11111111-1111-4111-8111-111111111111",
  "priority": "NORMAL",
  "deliveryNote": "Giao buổi tối"
}
~~~

Schema:

~~~yaml
type: object
required: [customerId]
additionalProperties: false
properties:
  customerId:
    type: string
    format: uuid
  priority:
    type: string
    enum: [NORMAL, EXPRESS]
  deliveryNote:
    type: string
    maxLength: 500
~~~

- **type: object** yêu cầu giá trị ở cấp này là một object.
- **properties** mô tả các field được nhận diện, nhưng **không tự làm chúng bắt buộc**.
- **required** nằm ở **schema object cha**, liệt kê tên field phải xuất hiện trong object.
- **additionalProperties: false** từ chối field ngoài danh sách đã công bố (trong ngữ cảnh schema đơn giản trên); JSON Schema mặc định không cấm field khác nếu không đặt hạn chế.
- **deliveryNote** vắng mặt thì hợp lệ. Nhưng **deliveryNote: null** không hợp lệ với **type: string**.

### 3.1. Object lồng nhau

~~~yaml
type: object
required: [recipient]
properties:
  recipient:
    type: object
    required: [name, countryCode]
    properties:
      name:
        type: string
        minLength: 1
      countryCode:
        type: string
        pattern: '^[A-Z]{2}$'
      addressLine2:
        type: string
    additionalProperties: false
~~~

Schema ngoài yêu cầu có **recipient**; schema **bên trong** yêu cầu **name, countryCode**. Không đặt name vào required của object ngoài vì required chỉ tác động tới các property trực tiếp ở cấp đó.

### 3.2. Object dạng map

Khi client được phép đặt key tùy ý, dùng schema cho **additionalProperties**:

~~~yaml
type: object
maxProperties: 10
additionalProperties:
  type: string
  maxLength: 80
~~~

Ví dụ **{"channel":"web","campaign":"spring"}** hợp lệ. Tuy nhiên, key tùy ý có thể bị lợi dụng để lưu dữ liệu nhạy cảm hoặc tạo payload quá lớn; giới hạn key/value, quota và chính sách dữ liệu.

Nếu ứng dụng cần **closed request model**, additionalProperties: false giúp phát hiện lỗi gõ sai field. Nhưng biến một API từng cho phép extension fields thành closed schema có thể gây breaking change.

## 4. Required không đồng nghĩa non-null; optional không đồng nghĩa nullable

Hãy phân biệt ba body:

~~~json
{}
~~~

~~~json
{"deliveryNote":null}
~~~

~~~json
{"deliveryNote":""}
~~~

Tương ứng: **field không có mặt**, field có mặt với **giá trị null**, field có mặt với **string rỗng**. Đây là ba trạng thái có thể được nghiệp vụ hiểu khác nhau.

| Schema của field | Không có key | null | String rỗng | String hợp lệ |
| --- | --- | --- | --- | --- |
| optional, **type: string** | Có | Không | Có nếu không có minLength | Có |
| required, **type: string** | Không | Không | Có nếu không có minLength | Có |
| optional, **type: [string, 'null']** | Có | Có | Có nếu không có minLength | Có |
| required, **type: [string, 'null']** | Không | Có | Có nếu không có minLength | Có |

Ví dụ field **bắt buộc hiện diện nhưng được null**:

~~~yaml
type: object
required: [approvedAt]
properties:
  approvedAt:
    type: [string, 'null']
    format: date-time
~~~

Nếu approvedAt chưa có, client **vẫn phải gửi** **approvedAt: null**. Nếu bỏ key hoàn toàn, schema không hợp lệ.

Ngược lại, field **có thể bỏ nhưng khi gửi không được null**:

~~~yaml
type: object
properties:
  nickname:
    type: string
    minLength: 1
~~~

### 4.1. Default không tự sửa JSON request

~~~yaml
priority:
  type: string
  enum: [NORMAL, EXPRESS]
  default: NORMAL
~~~

**default** trong JSON Schema là thông tin cho công cụ/người đọc, **không tự buộc một validator bổ sung field** vào JSON. Nếu server thực tế áp NORMAL khi priority vắng mặt, phải cài đặt hành vi đó và kiểm thử. Không để YAML công bố default mà backend lại xử lý null/thiếu field khác nhau ngoài dự kiến.

### 4.2. Giá trị null phải có ý nghĩa trong domain

Null có thể mang nghĩa **chưa được phê duyệt**, **không áp dụng**, hoặc **chủ động xóa giá trị**. Khi null và missing không cần phân biệt trong response, chọn một quy tắc serializer nhất quán. Khi PATCH, phải phân biệt theo **media type** vì null có thể là một chỉ thị thay đổi dữ liệu.

## 5. Array: items, minItems/maxItems và ràng buộc phần tử

Một đơn hàng có nhiều dòng:

~~~json
{"items":[{"sku":"SKU-001","quantity":2},{"sku":"SKU-002","quantity":1}]}
~~~

Schema:

~~~yaml
type: object
required: [items]
properties:
  items:
    type: array
    minItems: 1
    maxItems: 100
    items:
      type: object
      required: [sku, quantity]
      additionalProperties: false
      properties:
        sku:
          type: string
          minLength: 1
          maxLength: 64
        quantity:
          type: integer
          minimum: 1
          maximum: 999
~~~

- **required: [items]** bắt buộc có key items.
- **type: array** bắt buộc giá trị là mảng, không phải object hoặc null.
- **minItems: 1** cấm mảng rỗng; chỉ required thì vẫn cho **[]**.
- **items** là schema áp cho **từng phần tử**.
- **required: [sku, quantity]** là điều kiện cho **mỗi object dòng hàng**.
- **maxItems: 100** giới hạn chi phí xử lý; request body size và quota vẫn cần kiểm soát riêng.

| Giá trị items | Kết quả |
| --- | --- |
| Vắng mặt | Sai vì required |
| null | Sai vì không phải array |
| [] | Sai vì minItems |
| [null] | Sai vì item phải là object |
| [{}] | Sai vì thiếu sku và quantity |
| [{"sku":"A","quantity":1}] | Hợp lệ |
| 101 phần tử | Sai vì maxItems |

### 5.1. uniqueItems và giới hạn của nó

~~~yaml
type: array
uniqueItems: true
items:
  type: string
~~~

**uniqueItems: true** loại phần tử JSON trùng theo quan hệ equality của JSON Schema. Với array object, hai dòng cùng SKU nhưng khác quantity là **hai object khác nhau**; uniqueItems không thực thi quy tắc “SKU không được lặp”. Hãy kiểm tra quy tắc này tại service hoặc chọn mô hình data phù hợp.

Trong JSON Schema 2020-12 còn có **prefixItems** cho tuple, nhưng danh sách line item đồng nhất nên dùng **items**. Với array lớn, unique check có chi phí; luôn chọn maxItems hợp lý.

## 6. Enum: kiểu, null và tiến hóa

~~~yaml
priority:
  type: string
  enum: [NORMAL, EXPRESS]

status:
  type: string
  enum: [DRAFT, CONFIRMED, CANCELLED]
~~~

**Enum phân biệt chữ hoa/chữ thường và kiểu dữ liệu.** NORMAL không bằng normal, số 1 không bằng string "1".

Nếu muốn cho enum **nhận null**:

~~~yaml
type: [string, 'null']
enum: [NORMAL, EXPRESS, null]
~~~

Chỉ ghi **type: [string, 'null']** nhưng giữ **enum: [NORMAL, EXPRESS]** thì **null vẫn sai**, vì giá trị phải thỏa **cả type và enum**.

Java:

~~~java
public enum Priority {
    NORMAL, EXPRESS
}
~~~

Nếu server thêm giá trị **OVERNIGHT** vào response, client Java đã codegen thành enum đóng có thể **deserialize thất bại**. Vì vậy “thêm giá trị enum” không đương nhiên tương thích với mọi SDK. Cần công bố tính mở rộng, thiết kế UNKNOWN fallback khi công cụ hỗ trợ, hoặc quản lý qua version/migration.

## 7. $ref, allOf, oneOf và anyOf khi tái sử dụng

Để dùng lại schema:

~~~yaml
items:
  type: array
  items:
    $ref: '#/components/schemas/OrderLine'
~~~

| Từ khóa | Điều kiện |
| --- | --- |
| **$ref** | Tham chiếu định nghĩa schema khác |
| **allOf** | Dữ liệu thỏa **mọi** schema con |
| **anyOf** | Dữ liệu thỏa **ít nhất một** schema con |
| **oneOf** | Dữ liệu thỏa **chính xác một** schema con |

Ví dụ hai hình thức giao hàng:

~~~yaml
oneOf:
  - type: object
    required: [method, address]
    properties:
      method:
        const: DELIVERY
      address:
        type: string
        minLength: 1
    additionalProperties: false
  - type: object
    required: [method, storeId]
    properties:
      method:
        const: PICKUP
      storeId:
        type: string
        minLength: 1
    additionalProperties: false
~~~

Ở đây const giúp hai nhánh khác nhau. Nếu một giá trị cùng thỏa hai nhánh thì **oneOf thất bại**, trong khi **anyOf** chỉ yêu cầu ít nhất một nhánh. Đừng dùng oneOf như cú pháp đẹp hơn của anyOf.

Với allOf và additionalProperties: false, việc “đóng” object ở từng nhánh có thể vô tình cấm field của nhánh khác. JSON Schema 2020-12 có **unevaluatedProperties** nhưng cần công cụ hỗ trợ đúng; với DTO đơn giản nên ưu tiên schema rõ, ít tổ hợp.

## 8. Request và response cần quyền sở hữu field khác nhau

Một **create request** không nên cho client tự đặt id, status, totalPrice hoặc createdAt nếu server quản lý các giá trị đó.

| Trường | CreateOrderRequest | OrderResponse |
| --- | --- | --- |
| customerId | Required | Có thể có, tùy contract |
| items | Required, không rỗng | Required |
| priority | Optional, server default | Required |
| deliveryNote | Optional + nullable | Nullable |
| id | Không cho gửi | Required |
| status | Không cho gửi | Required |
| createdAt | Không cho gửi | Required |

Dùng **CreateOrderRequest** và **OrderResponse** riêng thường dễ hiểu và an toàn. OpenAPI còn có **readOnly** và **writeOnly** để mô tả ngữ nghĩa theo hướng request/response:

~~~yaml
id:
  type: string
  format: uuid
  readOnly: true
secret:
  type: string
  writeOnly: true
~~~

Các cờ này **không tự chặn mass assignment** trong controller, không tự ngăn serializer ghi secret vào log. Kiểm soát bằng DTO, service authorization và response mapping.

## 9. Một OpenAPI 3.1 hoàn chỉnh cho API tạo đơn

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      operationId: createOrder
      summary: Tạo đơn hàng
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
            example:
              customerId: "11111111-1111-4111-8111-111111111111"
              items:
                - sku: SKU-001
                  quantity: 2
              priority: NORMAL
              deliveryNote: null
      responses:
        '201':
          description: Đã tạo đơn
          headers:
            Location:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400':
          description: Request không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không có quyền
        '409':
          description: Xung đột nghiệp vụ
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, items]
      additionalProperties: false
      properties:
        customerId:
          type: string
          format: uuid
        items:
          type: array
          minItems: 1
          maxItems: 100
          items:
            $ref: '#/components/schemas/OrderLine'
        priority:
          $ref: '#/components/schemas/Priority'
        deliveryNote:
          type: [string, 'null']
          maxLength: 500
    OrderLine:
      type: object
      required: [sku, quantity]
      additionalProperties: false
      properties:
        sku:
          type: string
          minLength: 1
          maxLength: 64
        quantity:
          type: integer
          minimum: 1
          maximum: 999
    Priority:
      type: string
      enum: [NORMAL, EXPRESS]
      default: NORMAL
    OrderResponse:
      type: object
      required: [id, status, items, priority, createdAt]
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [DRAFT, CONFIRMED, CANCELLED]
        items:
          type: array
          items:
            $ref: '#/components/schemas/OrderLine'
        priority:
          $ref: '#/components/schemas/Priority'
        deliveryNote:
          type: [string, 'null']
        createdAt:
          type: string
          format: date-time
    ApiProblem:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        code:
          type: string
        violations:
          type: array
          items:
            type: object
            required: [field, message]
            properties:
              field:
                type: string
              message:
                type: string
~~~

**Đọc hợp đồng:** CreateOrderRequest yêu cầu customerId và items; priority có default ở mức mô tả; deliveryNote có thể bỏ hoặc gửi null; response có id/status/createdAt do server sinh. **additionalProperties: false** chặn một client tự gửi trường server-managed như id trong create request, miễn là runtime cũng thực thi chính sách.

### 9.1. Ví dụ HTTP tương ứng

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "customerId": "11111111-1111-4111-8111-111111111111",
  "items": [{"sku":"SKU-001","quantity":2}],
  "deliveryNote": null
}
~~~

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/22222222-2222-4222-8222-222222222222
Content-Type: application/json

{
  "id": "22222222-2222-4222-8222-222222222222",
  "status": "DRAFT",
  "items": [{"sku":"SKU-001","quantity":2}],
  "priority": "NORMAL",
  "deliveryNote": null,
  "createdAt": "2026-11-18T10:20:00Z"
}
~~~

Server **phải tự áp dụng NORMAL** trong code; JSON Schema không tự bổ sung field này. Response mẫu không có customerId vì OrderResponse ở ví dụ không quy định trường đó.

## 10. Java/Spring: kiểm tra đúng lúc deserialize và validate

Ví dụ Java 17+, Spring Boot 3 / Spring Web và Jakarta Bean Validation:

~~~java
public enum Priority {
    NORMAL, EXPRESS
}

public record OrderLineRequest(
        @NotBlank @Size(max = 64) String sku,
        @NotNull @Min(1) @Max(999) Integer quantity
) {}

public record CreateOrderRequest(
        @NotNull UUID customerId,
        @NotEmpty @Size(max = 100)
        List<@NotNull @Valid OrderLineRequest> items,
        @JsonSetter(nulls = Nulls.FAIL) Priority priority,
        @Size(max = 500) String deliveryNote
) {}
~~~

- **@NotNull** yêu cầu giá trị không null sau Jackson binding.
- **@NotEmpty** cấm mảng null/rỗng; tương ứng required + minItems.
- **@NotNull** trên mỗi phần tử cấm **items: [null]**; **@Valid** kiểm tra thuộc tính của từng dòng con.
- Dùng **Integer** thay cho int để dễ kiểm tra null; @Min cấm 0.
- **@Size** cho phép null, nhưng kiểm tra độ dài khi có string.
- **@JsonSetter(nulls = Nulls.FAIL)** minh họa cách yêu cầu Jackson từ chối **priority: null** dù cho phép bỏ key; phải kiểm thử hành vi này với ObjectMapper/version thực tế.
- **Java String null không phân biệt missing với explicit null** sau binding thông thường. Với **deliveryNote** điều này được phép; nếu nghiệp vụ cần phân biệt, phải dùng representation tri-state.
- Enum sai tên thường gây deserialization error, cần ánh xạ thành phản hồi HTTP 400 phù hợp.

Controller minh họa:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest body,
            Authentication authentication) {

        Priority priority = body.priority() == null
                ? Priority.NORMAL
                : body.priority();

        OrderResponse created = service.createAuthorized(
                authentication, body, priority);

        return ResponseEntity
                .created(URI.create("/api/v1/orders/" + created.id()))
                .body(created);
    }
}
~~~

**Đây là mã giảng giải**, cần import, DTO response, service, security và exception handler để chạy thành ứng dụng. Service phải kiểm tra customerId có thuộc phạm vi được phép, SKU tồn tại, giá và tồn kho hợp lệ. Một UUID đúng format **không chứng minh** người gọi có quyền với khách hàng đó.

### 10.1. Hợp đồng và runtime phải được đối chiếu

Jackson có thể bỏ unknown fields tùy cấu hình. Nếu OpenAPI quy định **additionalProperties: false** nhưng ObjectMapper bỏ qua unknown properties, implementation không thực thi strict contract. Chọn cấu hình ObjectMapper/DTO phù hợp, hoặc validation bằng JSON Schema trước binding khi cần.

Công cụ code-first có thể sinh OpenAPI từ DTO, nhưng không phải mọi annotation đều cho kết quả mong muốn: optional/nullable, default, unknown fields và readOnly cần kiểm tra spec xuất ra. **Không coi annotation là bằng chứng runtime và spec đã khớp.**

## 11. Missing vs null khi PUT/PATCH: lỗi có thể phá dữ liệu

**PUT** diễn đạt tạo/thay thế trạng thái tài nguyên theo hợp đồng. Nếu trường bắt buộc bị bỏ, server cần xử lý như lỗi request, không âm thầm coi missing là “giữ nguyên” như PATCH.

**PATCH** phải có media type định nghĩa ngữ nghĩa:

- **application/merge-patch+json (RFC 7396):** field **vắng mặt** là không đụng tới; field **có null** có tác dụng **loại bỏ thành viên** khỏi object đích.
- **application/json-patch+json (RFC 6902):** request là danh sách thao tác add/remove/replace; null có thể là giá trị của replace, còn remove là thao tác xóa rõ ràng.

~~~http
PATCH /api/v1/orders/22222222-2222-4222-8222-222222222222 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "order-v5"

{"deliveryNote": null}
~~~

Với JSON Merge Patch, ví dụ trên có ý nghĩa **xóa thuộc tính deliveryNote**, không đơn giản là gán string null theo logic của một DTO Java.

Nếu server cần phân biệt ba trạng thái **absent / explicit null / non-null**, dùng **JsonNode**, wrapper có dấu hiệu field hiện diện, hoặc giải pháp tri-state (ví dụ JsonNullable khi phù hợp). Không mong một String Java nullable tự giữ thông tin này. PATCH nên có **If-Match** nếu thao tác cần chống lost update.

## 12. Security và API errors: schema không cấp quyền

Một request có thể thỏa toàn bộ JSON Schema mà vẫn bị từ chối bởi security hoặc nghiệp vụ.

| Rủi ro | Biện pháp |
| --- | --- |
| Mass assignment: gửi id/tenantId/role/totalPrice | DTO request chỉ nhận field được phép; server sinh trường do server quản lý |
| IDOR/BOLA: customerId của tenant khác | Kiểm tra quyền và tenant tại service/query |
| Thông tin riêng qua field trả về | Response DTO và field-level authorization |
| Request quá lớn hoặc array rất dài | maxItems/maxLength, max body size, quota, timeout |
| Giá trị không hợp lệ | Validation sau deserialize và domain validation |
| Lộ thông tin qua lỗi | Problem Details an toàn, không trả SQL/stack trace/rejected secret |
| Null/unknown fields xử lý sai | Contract test với ObjectMapper cấu hình thực |

Ví dụ response validation theo **RFC 9457**:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Request validation failed",
  "status": 400,
  "detail": "Một hoặc nhiều trường dữ liệu không hợp lệ.",
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field":"items[0].quantity","message":"Phải từ 1 đến 999"}
  ]
}
~~~

Một số API chọn **422 Unprocessable Content** cho validation ngữ nghĩa; ví dụ này dùng 400. **Quan trọng là nhất quán** về status, code và cấu trúc lỗi. **401** dùng cho xác thực chưa hợp lệ, **403/404** cho quyền và phạm vi công bố, **409** cho xung đột nghiệp vụ; không ép mọi lỗi thành 400.

## 13. Tiến hóa schema và backward compatibility

| Thay đổi | Rủi ro |
| --- | --- |
| Thêm field required vào request | Breaking: client cũ không gửi |
| Optional → required | Breaking |
| Request từ nullable → non-null | Client cũ gửi null có thể lỗi |
| Response từ non-null → nullable | Client cũ có thể gặp null ngoài dự kiến |
| Thêm enum value ở response | SDK enum đóng có thể không parse được |
| Đổi integer thành string | Breaking cho serializer và validator |
| Thêm optional field vào response | Thường an toàn với client linh hoạt, không chắc với strict parser |
| Bật additionalProperties: false sau khi từng cho extension | Có thể chặn request cũ |
| Giảm maxItems/maxLength | Một số request trước đây hợp lệ thành lỗi |

**Hướng request và response không đối xứng.** Server cho phép thêm một input optional có thể ít rủi ro; server trả thêm giá trị enum có thể làm client đã sinh SDK bị lỗi.

Khi thay đổi, chạy **OpenAPI diff**, thử với SDK thực tế, kiểm tra client cũ, canary và theo dõi 400/422 do schema. Không chỉ nhìn YAML có vẻ tương thích rồi phát hành.

## 14. Kiểm thử: JSON Schema và Java/Spring runtime

| ID | Request hoặc tình huống | Kỳ vọng |
| --- | --- | --- |
| S01 | Body hợp lệ, thiếu priority | 201 và server dùng NORMAL |
| S02 | Thiếu customerId | 400 |
| S03 | customerId=null hoặc sai UUID | 400 |
| S04 | Thiếu items | 400 |
| S05 | items=[] | 400 do minItems |
| S06 | items=[null] | 400 do item type |
| S07 | quantity=0 hoặc 1000 | 400 |
| S08 | sku="" hoặc quá 64 ký tự | 400 |
| S09 | priority=normal hoặc UNKNOWN | 400 |
| S10 | deliveryNote bị bỏ | Hợp lệ |
| S11 | deliveryNote=null | Hợp lệ |
| S12 | deliveryNote=7 | 400 |
| S13 | Unknown top-level property | 400 nếu strict contract |
| S14 | 101 items | 400 và không xử lý quá mức |
| S15 | customerId thuộc tenant khác | 403/404, không tạo đơn |
| S16 | Response 201 | Validate OrderResponse và Location |
| S17 | JSON Merge Patch null vs missing | Không cùng nghĩa |
| S18 | SDK codegen | Enum/null/default tương thích |

Mẫu **MockMvc**:

~~~java
@Test
void rejectEmptyItems() throws Exception {
    mvc.perform(post("/api/v1/orders")
            .header("Authorization", "Bearer " + validTestToken)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": "11111111-1111-4111-8111-111111111111",
                  "items": []
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json")))
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
}
~~~

Đoạn này cần fixture, security, advice và bộ test thực tế. **Mock service trả lỗi theo kịch bản** không đủ chứng minh Bean Validation và Jackson đã thực thi đúng. Kết hợp:

- **Schema validation:** các JSON request/response có đúng cấu trúc không?
- **Integration test:** Jackson binding, Bean Validation, default và unknown field behavior đúng không?
- **Authorization test:** payload hợp schema nhưng không có quyền có bị từ chối không?
- **Contract test:** response thật được SDK cũ parse; nếu code-first, spec xuất ra phải so với baseline.

## 15. Bài thực hành: API đăng ký khóa học

**Bối cảnh:** **POST /api/v1/enrollments** nhận **studentId**, mảng **courses**, enum **plan** (BASIC/PRO) và **referralCode** có thể null. Response thêm **enrollmentId**, **state** (PENDING/ACTIVE/CANCELLED) và **createdAt**. Mỗi lần tối đa tám khóa; một course có code và quantity từ 1 đến 3. Nếu không gửi plan, server dùng BASIC.

**Yêu cầu (100 điểm):**

1. **Schema – 40 điểm:** viết OpenAPI 3.1 object/array/enum/null/required, giới hạn số phần tử; tách request và response; cấm client tự gửi enrollmentId/state.
2. **Java/Spring – 25 điểm:** thiết kế DTO record và Bean Validation, POST trả 201/Location; thực thi default BASIC; giải thích null so với missing.
3. **Bảo mật và tương thích – 15 điểm:** xác minh studentId thuộc quyền caller; phân tích khi thêm plan=ENTERPRISE hoặc biến referralCode thành required.
4. **Kiểm thử – 20 điểm:** ít nhất tám ca gồm thiếu studentId, mảng rỗng, quá tám khóa, quantity=0, plan lạ, null referralCode, field lạ, khác tenant và response 201.

**Hướng giải schema rút gọn:**

~~~yaml
EnrollmentRequest:
  type: object
  required: [studentId, courses]
  additionalProperties: false
  properties:
    studentId:
      type: string
      format: uuid
    courses:
      type: array
      minItems: 1
      maxItems: 8
      items:
        type: object
        required: [code, quantity]
        additionalProperties: false
        properties:
          code:
            type: string
            minLength: 1
          quantity:
            type: integer
            minimum: 1
            maximum: 3
    plan:
      type: string
      enum: [BASIC, PRO]
      default: BASIC
    referralCode:
      type: [string, 'null']
~~~

Server thật phải áp default, kiểm tra quyền và chỉ sinh state/ID. Một bài làm đạt yêu cầu cần giải thích **required khác non-null, optional khác nullable** chứ không chỉ tạo YAML đúng cú pháp.

## 16. Checklist và tài liệu tham khảo

- [ ] Tôi phân biệt cú pháp null ở OAS **3.1** và **3.0**.
- [ ] Tôi đặt **required** tại object cha, không nhầm với **properties**.
- [ ] Tôi phân biệt missing, null, string rỗng và default.
- [ ] Tôi dùng **items**, minItems/maxItems và giới hạn array phù hợp.
- [ ] Tôi biết enum cùng type; null chỉ hợp lệ nếu enum cũng cho phép.
- [ ] Tôi hiểu $ref, allOf, oneOf, anyOf và nguy cơ schema kết hợp.
- [ ] Tôi không cho client tự ghi các trường server-managed.
- [ ] Java/Spring/Bean Validation/Jackson được kiểm thử khớp schema.
- [ ] Tôi biết PATCH Merge Patch null có ý nghĩa xóa member.
- [ ] Tôi kiểm tra tenant/authorization ngoài JSON Schema.
- [ ] Tôi có schema diff, contract test, SDK test và kế hoạch migration.

**Ghi nhớ:** Schema không chỉ nói **“dữ liệu có kiểu gì?”** mà còn định nghĩa **“field có phải xuất hiện không, có thể mang null không, có giới hạn gì và client được phép kiểm soát gì?”**. OpenAPI chỉ đáng tin khi được triển khai và kiểm thử nhất quán qua **HTTP, Java/Spring, hệ thống phân quyền và SDK**.

### Tài liệu chuẩn

- **OpenAPI Specification 3.1:** Schema Object, Request Body, Responses và Security.
- **JSON Schema Draft 2020-12:** object, array, enum, type, required và validation.
- **RFC 7396 – JSON Merge Patch:** vắng mặt/null trong PATCH.
- **RFC 6902 – JSON Patch:** add/remove/replace.
- **RFC 9457 – Problem Details for HTTP APIs:** lỗi API.
- **Spring Web, Jackson, Jakarta Bean Validation:** binding/validation ở runtime.
