# Sinh tài liệu, mock server và SDK từ cùng hợp đồng

## 1. Bài toán: ba nhóm làm việc trên ba cách hiểu khác nhau

Backend trả **201 Created** với trường **orderId**, docs nói **200 OK** với **id**, SDK gửi **totalAmount** nhưng server đòi **totalMinorUnit**: ba nhóm có ba bản hợp đồng khác nhau nên tích hợp thất bại.

Giải pháp: dùng **một hợp đồng OpenAPI có quản lý phiên bản**:

~~~mermaid
flowchart TD
    A["OpenAPI 3.1: hợp đồng gốc"] --> B["Tài liệu tương tác"]
    A --> C["Mock server"]
    A --> D["SDK và kiểu dữ liệu"]
    A --> E["Schema/contract tests"]
    F["Backend Java/Spring"] --> E
    E --> G{"Đúng hợp đồng?"}
    G -->|Không| H["Sửa mã hoặc cập nhật hợp đồng có kiểm soát"]
    G -->|Có| I["Phát hành"]
~~~

**Docs, mock và SDK phải được sinh từ cùng một phiên bản hợp đồng.** Khi API đổi field/status, phải review, kiểm chứng và phát hành đồng bộ.

Bài thuộc chương **Hợp đồng OpenAPI** trong **INTEGRATION_API_REST**, kết nối resource/URI, HTTP methods/status, dữ liệu, phân trang, cache, idempotency, bảo mật, xử lý lỗi và Java/Spring. Trọng tâm là **chuỗi docs–mock–SDK**, không lặp lại toàn bộ cú pháp OpenAPI.

Sau bài này, người học có thể:

- Phân biệt **source of truth**, tài liệu render, mock và SDK được sinh.
- Thiết kế một hợp đồng OpenAPI 3.1 đủ rõ để ba đầu ra có cùng semantics.
- Xây quy trình **lint → validate → generate → test → publish** có thể tái lập.
- Tích hợp với Java/Spring mà không coi annotation hoặc code generator là bằng chứng hợp đồng đúng.
- Xác định giới hạn của mock, bảo vệ dữ liệu mẫu/secrets và kiểm thử breaking changes.

## 2. Hợp đồng gốc phải mô tả những gì?

Một OpenAPI document không chỉ liệt kê path. Để làm nguồn chung cho tài liệu, mock và SDK, nó cần quy định:

| Thành phần | Ví dụ | Tại sao ảnh hưởng cả ba đầu ra? |
| --- | --- | --- |
| **Paths và methods** | GET /orders/{orderId}, POST /orders | Định tuyến trong mock; hàm gọi trong SDK; trang endpoint trong tài liệu. |
| **operationId** | getOrder, createOrder | Tên hàm ổn định hơn so với để generator tự suy đoán. |
| **Parameters** | orderId dạng UUID; limit 1–100 | Mock kiểm tra input; SDK nhận đúng kiểu; người dùng biết giới hạn. |
| **Request body** | CreateOrder, required fields | Sinh model và validation; minh họa payload hợp lệ. |
| **Responses** | 200, 201, 400, 401, 404, 422 | SDK nhận diện kết quả/lỗi; mock phát được phản hồi; docs giải nghĩa. |
| **Media type** | application/json, application/problem+json | Quyết định serialization và parse lỗi. |
| **Security** | BearerAuth | Cho biết cơ chế xác thực; không tự cài phân quyền. |
| **Examples** | Đơn CREATED với ID cụ thể | Dữ liệu dễ xem trong docs và dùng làm mock response. |
| **Schema constraints** | enum, minimum, nullable | Kiểu sinh, validate contract và sinh dữ liệu mock. |

Phải phân biệt **hợp đồng mô tả** với **thực thi runtime**. Ghi **401** trong OpenAPI không làm endpoint tự bắt buộc đăng nhập; thêm **minimum: 1** không bảo đảm database đã chặn giá trị âm; khai báo **application/problem+json** không tự sinh bộ xử lý lỗi đúng.

### 2.1. Nguồn sự thật và sản phẩm phái sinh

Ví dụ: **contracts/orders/openapi.yaml** là nguồn review; **dist/openapi.yaml**, **dist/docs/** và **generated/clients/** là đầu ra sinh theo cùng commit/toolchain. Không sửa SDK sinh thủ công rồi quên cập nhật contract gốc.

### 2.2. Design-first, code-first và kết hợp

- **Design-first:** viết OpenAPI, review hợp đồng trước, sau đó sinh docs/mock/SDK và triển khai backend. Phù hợp khi nhiều nhóm tiêu thụ API song song.
- **Code-first:** dùng annotation/introspection của Java/Spring để sinh OpenAPI từ controller/DTO rồi tạo các sản phẩm khác. Nhanh cho backend đã chạy, nhưng tài liệu có thể vô tình phản ánh chi tiết framework hoặc thiếu lỗi/quyền không được khai báo.
- **Hybrid:** duy trì contract gốc được review, đồng thời sinh bản quan sát được từ ứng dụng và **diff/kiểm thử** để phát hiện sai lệch. Không trộn hai nguồn mà không có bước hòa giải.

Chọn hướng nào cũng cần **chỉ rõ artifact nào là bản hợp đồng được phát hành**, ai có quyền thay, và CI phát hiện khác biệt như thế nào.

## 3. Một ví dụ OpenAPI 3.1 dùng chung

Ví dụ Orders API gồm **POST tạo đơn** và **GET đọc đơn**, đủ minh họa mô hình, status, header và lỗi; UUID và dữ liệu đều giả định.

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
  description: Quản lý đơn hàng của người dùng đã xác thực.
servers:
  - url: https://api.example.com
tags:
  - name: Orders
security:
  - BearerAuth: []
paths:
  /orders:
    post:
      tags: [Orders]
      operationId: createOrder
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
            example:
              customerId: 22222222-2222-4222-8222-222222222222
              totalMinorUnit: 125000
              note: null
      responses:
        '201':
          description: Đã tạo đơn
          headers:
            Location:
              required: true
              description: URI của đơn mới.
              schema: {type: string, format: uri-reference}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
              example:
                id: 11111111-1111-4111-8111-111111111111
                status: CREATED
                totalMinorUnit: 125000
                note: null
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không được phép tạo đơn
        '422':
          description: Dữ liệu hợp lệ về cú pháp nhưng sai quy tắc nhập
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
  /orders/{orderId}:
    get:
      tags: [Orders]
      operationId: getOrder
      summary: Đọc một đơn hàng
      parameters:
        - in: path
          name: orderId
          required: true
          schema: {type: string, format: uuid}
      responses:
        '200':
          description: Đơn hàng có quyền truy cập
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không có quyền đọc đơn
        '404':
          description: Không tìm thấy hoặc được che theo chính sách
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateOrder:
      type: object
      required: [customerId, totalMinorUnit]
      additionalProperties: false
      properties:
        customerId: {type: string, format: uuid}
        totalMinorUnit: {type: integer, format: int64, minimum: 0}
        note: {type: [string, 'null'], maxLength: 500}
    Order:
      type: object
      required: [id, status, totalMinorUnit, note]
      properties:
        id: {type: string, format: uuid}
        status: {type: string, enum: [CREATED, PAID, CANCELLED]}
        totalMinorUnit: {type: integer, format: int64, minimum: 0}
        note: {type: [string, 'null']}
    Problem:
      type: object
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
          example:
            type: https://api.example.com/problems/invalid-request
            title: Invalid request
            status: 400
            code: INVALID_REQUEST
~~~

Ví dụ chỉ có một số endpoint; production cần thêm phân trang, lọc/sort, idempotency khi cần, rate limit, cache/ETag và lỗi 5xx. **BearerAuth** khai báo cơ chế xác thực, không tự thực thi quyền hay kiểm tra token.

### 3.1. Những chi tiết ảnh hưởng code generation

- **operationId** phải nhất quán và duy nhất: **getOrder** sinh thành method dễ đoán hơn tên tự suy diễn từ đường dẫn.
- **required** là về việc field **phải xuất hiện**, còn **type: [string, 'null']** cho phép giá trị null. Với Order, **note** bắt buộc xuất hiện nhưng có thể null; với CreateOrder, **note** tùy chọn và cũng có thể null.
- OpenAPI **3.1** dùng cách khai báo schema tương thích JSON Schema, nên không cần trường **nullable: true** kiểu 3.0 cho ví dụ này. Không phải generator nào cũng có cùng mức hỗ trợ 3.1; kiểm chứng với phiên bản toolchain đã pin.
- **format: uuid, int64** giúp tooling diễn giải nhưng mức độ kiểm tra format có thể khác nhau. Không xem chúng là thay thế kiểm tra và giới hạn dữ liệu ở runtime.
- **additionalProperties: false** trong CreateOrder là quyết định hợp đồng: client gửi field lạ không hợp lệ theo schema; backend phải thực thi nếu muốn giữ cam kết đó.
- **201 + Location** là semantics tạo resource. SDK cần cho phép đọc cả body lẫn header quan trọng, không chỉ trả một model bỏ mất Location.
- Dùng **application/problem+json** giúp client phân biệt lỗi có cấu trúc với body Order; client phải dựa vào status/media type, không giả định mọi response là Order.

### 3.2. Bản ghi HTTP phải khớp với schema

~~~http
POST /orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{"customerId":"22222222-2222-4222-8222-222222222222","totalMinorUnit":125000}

HTTP/1.1 201 Created
Location: /orders/11111111-1111-4111-8111-111111111111
Content-Type: application/json

{
  "id":"11111111-1111-4111-8111-111111111111",
  "status":"CREATED",
  "totalMinorUnit":125000,
  "note":null
}
~~~

Đây là hai thông điệp HTTP liên tiếp đặt chung để dễ đọc. **Contract test** phải xác minh server trả **201**, có **Location** và body tương thích với Order. Chỉ nhìn JSON không đủ; HTTP status và header cũng là hợp đồng.

## 4. Sinh tài liệu từ cùng contract

Swagger UI, Redoc và các trình xem OpenAPI có thể sinh trang tham chiếu gồm:

- Danh sách endpoint và method theo **tags**; mô tả từ **summary/description**.
- Parameters, bắt buộc hay tùy chọn, kiểu dữ liệu và ví dụ.
- Request/response schema, status và headers.
- Cơ chế security được khai báo và giao diện thử request trong môi trường thích hợp.

Quy trình: **review → lint/validate → bundle $ref → render docs → publish theo version** gắn với bản SDK/backend tương ứng.

Một bộ lệnh **minh họa** (cần cài đặt toolchain phù hợp, pin phiên bản và xem tài liệu CLI của công cụ đang dùng):

~~~bash
# Kiểm tra quy tắc mô tả và cấu trúc.
npx @redocly/cli lint openapi.yaml

# Tạo bản bundle khi spec tách thành nhiều file $ref.
npx @redocly/cli bundle openapi.yaml --output dist/openapi.yaml

# Ví dụ sinh HTML tài liệu tĩnh từ chính bản bundle.
npx @redocly/cli build-docs dist/openapi.yaml --output dist/docs.html
~~~

**Docs đúng cú pháp không chứng minh runtime đúng**: mô tả 201/401 nhưng server có thể trả 200 hoặc bỏ xác thực. Cần contract tests.

### 4.1. Tài liệu cho con người cần thêm quyết định nghiệp vụ

Các quy tắc như TTL cursor, chuyển trạng thái, quyền xem đơn và nâng cấp SDK cần mô tả ở description/policy. **Examples phải dùng dữ liệu giả**, không chứa JWT, API key hay PII.

## 5. Sinh mock server: tích hợp trước khi backend sẵn sàng

Mock trả response theo OpenAPI để frontend/mobile tích hợp sớm và thử trạng thái lỗi hiếm.

Ví dụ công cụ có thể dùng **Prism** hoặc một mock engine khác hiểu OpenAPI:

~~~bash
# Minh họa; cài đặt/pin phiên bản công cụ trong dự án.
npx @stoplight/prism-cli mock openapi.yaml
~~~

Client gọi **GET /orders/{orderId}** hoặc **POST /orders** tới mock; hành vi tùy engine và cách chọn response.

### 5.1. Hai kiểu mock thường gặp

| Kiểu | Kết quả | Khi dùng |
| --- | --- | --- |
| **Static/example-based** | Trả example đã khai báo cho status/schema được chọn. | Demo, UI snapshot, hợp đồng với đối tác, test phản hồi dễ lặp lại. |
| **Dynamic/schema-based** | Sinh dữ liệu hợp schema, có thể thay đổi mỗi lần. | Thử bộ hiển thị với nhiều giá trị, phát hiện null/enum/độ dài. |

Mock có thể dùng example **201 Order** từ POST, nhưng một mock stateless thường **không lưu đơn đã tạo để GET ở request sau**. Tương tự, nếu thêm API phân trang vào hợp đồng, example cursor không tự tạo cơ chế phân trang thật.

### 5.2. Mock được gì và không được gì?

**Mock có thể** kiểm tra route/schema và trả status, example, headers. **Mock thuần không chứng minh** phân quyền tenant, transaction, idempotency, cache, workflow, hiệu năng hay dữ liệu được lưu thật.

Chẳng hạn, contract cho phép **201** khi POST, mock phát 201 dù không hề ghi đơn hàng. Nếu sau đó GET cùng ID, mock có thể trả dữ liệu ví dụ không liên quan. Khi cần kiểm tra workflow:

1. Dùng **stateful mock** với kịch bản xác định trạng thái nếu engine hỗ trợ.
2. Hoặc bổ sung **integration test** trên backend/DB thật để chứng minh hành vi sau POST.

Mock phải dùng fixture giả và không được thay backend production.

### 5.3. Client phải thử response lỗi

Với Orders API, UI cần xử lý cả **400 Problem Details**, **401** khi thiếu token, **403** không có quyền, **404** khi đơn không tồn tại và **422** khi dữ liệu nhập không hợp lệ. Có thể cấu hình scenario hoặc response-selection của mock engine; **đừng mặc định gửi request lỗi sẽ khiến mọi mock tự sinh đúng mã lỗi**.

Một phép thử nhanh với mock:

~~~text
Kịch bản A: GET order -> 200 Order
Kịch bản B: POST order -> 201 + Location
Kịch bản C: POST thiếu totalMinorUnit -> lỗi theo chính sách contract
Kịch bản D: GET order chưa có quyền -> 403 hoặc 404 theo chính sách
~~~

**C/D cần cấu hình mock riêng** nếu engine chỉ phát example thành công; mock chạy được không chứng minh validation/security backend.

## 6. Sinh SDK từ contract

SDK generator đọc OpenAPI để tạo **request builder, client method, models, serializer/deserializer và cơ chế xử lý HTTP** tùy ngôn ngữ/kiểu thư viện. Công cụ phổ biến là OpenAPI Generator; một hướng khác là generator chuyên biệt cho hệ sinh thái TypeScript/Java/Kotlin.

Ví dụ:

~~~bash
# Cần pin phiên bản generator trong package lock/container CI.
npx @openapitools/openapi-generator-cli generate \
  -i dist/openapi.yaml \
  -g typescript-fetch \
  -o generated/typescript-client

npx @openapitools/openapi-generator-cli generate \
  -i dist/openapi.yaml \
  -g java \
  -o generated/java-client
~~~

Tên package và option cụ thể còn tùy phiên bản generator. **Không chạy sinh SDK vào thư mục mã viết tay** nếu chưa có chiến lược overwrite; output sinh lại nên cách ly và có tài liệu về việc người dùng được sửa phần nào.

### 6.1. Các đầu ra dự kiến

Từ **operationId: getOrder**, một SDK TypeScript có thể cung cấp method tương đương **getOrder(orderId)**; từ **CreateOrder**, nó sinh kiểu dữ liệu cho customerId, totalMinorUnit và note. SDK Java có thể sinh model, API class và lời gọi HTTP tương ứng.

Đây là **mô tả ý tưởng**, không cam kết chữ ký method giống hệt giữa các generator/template. Có generator đặt API method trong lớp **OrdersApi**, có generator dùng optional object arguments; trường **nullable/optional** và enum cũng được ánh xạ khác nhau.

**Bốn điểm phải kiểm tra SDK:**

1. **Kiểu:** UUID, số nguyên 64-bit, enum, null, optional được xử lý đúng. Ở JavaScript, số nguyên vượt **Number.MAX_SAFE_INTEGER** có thể mất độ chính xác; cần chính sách kiểu/serializer phù hợp.
2. **HTTP:** response 201, Location, header Authorization, 400/422 Problem Details không bị mất hoặc bị parse như Order.
3. **Runtime:** cấu hình base URL, timeout, retry, cancellation, TLS, proxy và phiên bản runtime được hỗ trợ.
4. **Tương thích:** public SDK API có thể thay đổi giữa các bản generator **ngay cả khi OpenAPI không đổi**; cần test và version riêng cho SDK.

### 6.2. SDK không thay thế business logic

Generator không thể tự quyết định:

- Token có còn hiệu lực hay phải refresh theo luồng OIDC/OAuth2 của ứng dụng.
- Retry **POST /orders** có an toàn không nếu mạng đứt sau khi server đã commit.
- Có được hiển thị đơn thuộc tenant khác không.
- Client nên merge dữ liệu khi GET danh sách thay đổi giữa hai trang ra sao.

Đó là **quy tắc ứng dụng**, không được sinh tự động chỉ từ schema.

## 7. Ghép contract với backend Java/Spring

Với Spring Boot, một controller có thể hiện thực POST và GET theo hợp đồng mẫu:

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record CreateOrderRequest(UUID customerId, long totalMinorUnit, String note) {}
record OrderDto(UUID id, String status, long totalMinorUnit, String note) {}

interface OrderService {
    OrderDto createForCurrentUser(CreateOrderRequest request);
    OrderDto getAuthorized(UUID id);
}

@RestController
@RequestMapping("/orders")
class OrdersController {
    private final OrderService service;

    OrdersController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<OrderDto> create(@RequestBody CreateOrderRequest request) {
        OrderDto result = service.createForCurrentUser(request);
        URI location = URI.create("/orders/" + result.id());
        return ResponseEntity.created(location).body(result);
    }

    @GetMapping("/{orderId}")
    ResponseEntity<OrderDto> get(@PathVariable UUID orderId) {
        return ResponseEntity.ok(service.getAuthorized(orderId));
    }
}
~~~

**Mẫu minh họa** chưa có validation, Problem Details, transaction hay security. Service phải kiểm tra tenant/quyền, dữ liệu và trạng thái. JSON response phải có **note: null** khi schema yêu cầu field này, không cấu hình serializer loại bỏ.

### 7.1. Đối chiếu Spring runtime với contract

| Contract nói | Backend phải thực hiện |
| --- | --- |
| POST /orders trả **201** | Không trả 200 theo mặc định; phát **Location** đúng. |
| **totalMinorUnit >= 0**, customerId UUID | Kiểm tra input và quyết định lỗi **400/422** theo policy. |
| POST có **BearerAuth** | Security filter xác thực; service phân quyền. |
| GET ID không tồn tại trả **404** | Không để NullPointerException thành 500. |
| Lỗi 400 là **Problem Details** | Exception handler dùng media type/schema đã công bố. |
| **note** nullable trong Order | Serialization khớp schema kể cả khi null. |

Có thể sinh bản OpenAPI từ **springdoc/@Operation** rồi diff với contract gốc, nhưng annotation có thể thiếu lỗi nghiệp vụ, quyền và hành vi proxy. **/v3/api-docs** không phải runtime contract test.

## 8. CI/CD: một đầu vào, nhiều đầu ra, không được drift

Quy trình triển khai nên coi OpenAPI là một **artifact có phiên bản và kiểm soát thay đổi**:

~~~mermaid
flowchart TD
    A["Pull request sửa openapi.yaml"] --> B["Parse + lint + validate + bundle"]
    B --> C["Breaking-change check"]
    C --> D["Sinh docs và SDK trong môi trường pin toolchain"]
    D --> E["Build/typecheck SDK"]
    E --> F["Contract + integration tests với backend"]
    F --> G["Publish spec, docs và SDK có version"]
~~~

### 8.1. Các cổng kiểm tra nên có

1. **Syntax/structure:** YAML hợp lệ, version OpenAPI đúng, các **$ref** resolve được, không trùng **operationId**, path parameters phù hợp với URI.
2. **Lint style:** đường dẫn, tên, tag, status, header, lỗi, security và description theo convention của tổ chức.
3. **Compatibility:** so bản mới với bản đang phát hành, xác định thay đổi phá vỡ consumer; review ngoại lệ có căn cứ.
4. **Generation:** sinh docs và SDK từ **cùng bản bundle**; toolchain/version/config được pin và truy vết theo commit.
5. **Build/typecheck:** SDK sinh được phải biên dịch, import được và chạy smoke test với runtime mục tiêu.
6. **Runtime contract tests:** API đang chạy phải trả status, body, Content-Type, headers đúng hợp đồng, cả happy path và lỗi.
7. **Publish:** gắn tag/version/commit cho OpenAPI, docs, mock fixture và SDK; không phát hành chéo phiên bản không tương thích.

Một pipeline giả mã:

~~~yaml
steps:
  - name: Validate contract
    run: |
      npx @redocly/cli lint openapi.yaml
      npx @redocly/cli bundle openapi.yaml --output dist/openapi.yaml
  - name: Check changes
    run: contract-diff --base released --head dist/openapi.yaml
  - name: Generate clients and docs
    run: generate-from-contract dist/openapi.yaml
  - name: Verify generated code
    run: typecheck-and-smoke-test-generated-clients
  - name: Verify Spring behavior
    run: run-authenticated-contract-and-integration-tests
~~~

**contract-diff**, **generate-from-contract** và hai lệnh test là **giả mã**, cần thay bằng tool thật. Nếu commit SDK sinh, CI nên sinh lại rồi fail nếu có diff chưa review.

### 8.2. Tính tái lập quan trọng hơn “máy tôi chạy được”

Pin generator/template, Java/Node, lint rules và lockfile/container. Lưu **contract version, generator version, config**. Nâng generator có thể làm **SDK breaking** dù HTTP contract không đổi.

## 9. Bảo mật khi docs, mock và SDK dùng chung hợp đồng

**OpenAPI mô tả security; không tự thực thi quyền.** Ba rủi ro:

| Lớp | Rủi ro | Biện pháp |
| --- | --- | --- |
| **Docs** | Công khai nội bộ endpoint, ví dụ chứa PII/JWT, nút “Try it out” gọi nhầm production. | Tách public/internal docs; dùng dữ liệu giả; cấu hình origin và auth theo môi trường; không nhúng secret. |
| **Mock** | Mock trả dữ liệu từ production hoặc bị người ngoài dùng để giả mạo backend; auth mô phỏng bị hiểu là auth thật. | Fixture tổng hợp, môi trường cô lập, giới hạn truy cập, mock URL/hostname khác production. |
| **SDK** | Ghi log token, chuyển Authorization sang host lạ, retry POST không an toàn, bỏ qua TLS. | Credential provider an toàn, allowlist base URL, TLS validation, log redaction và retry policy rõ ràng. |

Runtime vẫn phải kiểm tra token, scope và **object-level authorization**; mock cho GET không token không chứng minh endpoint thật cho phép.

Tách **mock/staging/production base URL**, không gửi production token tới mock; test bằng dữ liệu giả.

## 10. Kiểm thử hợp đồng trên ba lớp

### 10.1. Ma trận kiểm thử

| ID | Kiểm chứng | Kỳ vọng |
| --- | --- | --- |
| K01 | OpenAPI lint/resolve | Không lỗi cấu trúc, **$ref** hỏng hay operationId trùng. |
| K02 | Sinh docs/mock/SDK từ cùng revision | Artifact ghi nhận cùng version/commit. |
| K03 | SDK getOrder với UUID hợp lệ | Request tới đúng path và method GET. |
| K04 | POST createOrder thành công | **201**, **Location**, JSON đúng Order. |
| K05 | POST thiếu totalMinorUnit | Bị từ chối theo 400/422 đã công bố; không tạo đơn. |
| K06 | GET order không tồn tại | **404** theo chính sách; không parse response như Order. |
| K07 | Thiếu bearer token | **401** và không có dữ liệu; mock không thay thế test thật. |
| K08 | Đọc order thuộc tenant khác | 403/404 theo policy, không lộ dữ liệu. |
| K09 | Request chứa field lạ bị cấm theo CreateOrder | Bị từ chối theo chính sách thêm thuộc tính. |
| K10 | Field note null và vắng mặt | SDK/parser phân biệt đúng quy tắc **required/nullable**. |
| K11 | Số nguyên gần giới hạn an toàn của JavaScript | SDK không âm thầm làm tròn nếu nghiệp vụ hỗ trợ miền đó. |
| K12 | Thay đổi spec như xóa field/đổi operationId | CI phát hiện breaking change ở wire hoặc SDK. |

### 10.2. Test HTTP trên Spring bằng MockMvc

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(post("/orders")
        .contentType("application/json")
        .content("""
            {
              "customerId":"22222222-2222-4222-8222-222222222222",
              "totalMinorUnit":125000
            }
            """))
    .andExpect(status().isCreated())
    .andExpect(header().exists("Location"))
    .andExpect(content().contentTypeCompatibleWith("application/json"))
    .andExpect(jsonPath("$.status").value("CREATED"))
    .andExpect(jsonPath("$.totalMinorUnit").value(125000));
~~~

Test này giả định service trả đơn mới; bổ sung Spring Security context, kiểm tra Location URI, schema, lỗi và DB. **Principal giả không chứng minh phân quyền**.

### 10.3. Schema-conformance chưa đủ

Một response **201** hợp JSON Schema vẫn có thể sai nghiệp vụ: tạo đơn trùng, tổng tiền bị tính sai, dữ liệu tenant khác bị lộ, hoặc Location trỏ resource không tồn tại. Vì vậy:

- **Contract test** xác minh request/response phù hợp OpenAPI.
- **Integration test** chạy service và DB để xác minh ghi/đọc, quyền, transaction, cache/idempotency thực tế.
- **Consumer test** dùng SDK sinh để gọi backend thử nghiệm, không chỉ gọi mock.
- **Negative/security test** gửi thiếu token, token hết hạn, sai scope/tenant, giá trị vượt giới hạn.

Mock giúp phát triển song song; **backend thật mới quyết định** hệ thống có thỏa hợp đồng và nghiệp vụ không.

## 11. Quản lý thay đổi và tương thích

Phải đánh giá breaking changes ở HTTP, mock/docs và **public SDK API**:

| Thay đổi | Rủi ro |
| --- | --- |
| Xóa/đổi tên endpoint hoặc field đang dùng | Thường phá client cũ. |
| Đổi required field tùy chọn thành bắt buộc | Client cũ có thể không gửi, request bị từ chối. |
| Đổi **201** thành **200** hoặc bỏ **Location** | Client dựa vào status/header có thể hỏng. |
| Đổi kiểu integer sang string | Parse/schema và model SDK thay đổi. |
| Thu hẹp enum hoặc tăng yêu cầu quyền/scope | Client cũ và workflows có thể thất bại. |
| Thêm giá trị enum ở response | Client có switch kiểm hết các giá trị cũ có thể chưa xử lý. |
| Đổi **operationId** nhưng giữ HTTP route | Wire API có thể không đổi, nhưng **method SDK sinh** bị đổi. |
| Thêm field tùy chọn vào response | Thường dễ tương thích hơn, nhưng strict clients có thể từ chối field lạ. |

Quy trình an toàn: **diff bản phát hành**, phân loại breaking/non-breaking, thông báo deprecation/migration khi cần, thử client sinh từ bản cũ trên backend mới, phát hành version SDK thích hợp. Không chỉ tăng **info.version** rồi coi mọi consumer đã nâng cấp.

OpenAPI **info.version** là phiên bản tài liệu/hợp đồng do đội API quản lý; nó không nhất thiết bằng URL **/v2** hay version package SDK. Hãy công bố mối quan hệ giữa ba loại phiên bản thay vì mặc định chúng luôn đồng nhất.

## 12. Bài tập: một nguồn cho ba nhóm

**Tình huống:** đội backend đổi **POST /orders** từ **totalAmount** (đơn vị tiền chính) sang **totalMinorUnit** (đơn vị tiền nhỏ nhất), thêm response **422** và yêu cầu bearer authentication. Web frontend, mobile SDK Java/Kotlin và đối tác cần tích hợp khi backend chưa hoàn tất.

**Yêu cầu:**

1. Những phần nào của OpenAPI phải sửa để docs, mock, SDK cùng phản ánh thay đổi?
2. Nên phát hành mock thế nào để frontend thử được **201** và **422**?
3. Phải kiểm tra gì khi sinh SDK mới, nhất là kiểu số và lỗi HTTP?
4. Làm sao phát hiện server vẫn đang trả field cũ hoặc thiếu header Location?
5. Nếu người dùng SDK cũ vẫn gửi **totalAmount**, thay đổi có breaking không và xử lý ra sao?
6. Làm thế nào bảo đảm mock không phát dữ liệu production và SDK không chuyển bearer token sai host?

**Hướng giải:** sửa **CreateOrder/Order**, description/units, example, response 201/422, Problem schema và security scheme trong **một pull request hợp đồng**. Lint, review compatibility, sinh lại docs/mock/SDK theo cùng version. Cấu hình mock trả example 201 và scenario 422; không coi response mock là kiểm chứng backend. Build/typecheck SDK, test parse số và Problem Details, gọi staging với SDK sinh. Contract/integration tests kiểm tra **201 + Location + JSON field đúng**, validate input và quyền. Đổi một field request đang được dùng là **breaking change**: cần lộ trình tương thích hoặc version mới, không âm thầm xóa field cũ. Dùng synthetic fixtures, môi trường mock tách biệt và credential provider an toàn.

## 13. Checklist trước khi phát hành

- [ ] Có **một contract được review** và version hóa; chỉ rõ design-first/code-first/hybrid.
- [ ] OpenAPI khai báo method/path, operationId, parameter, schema, status, headers, media types và security đúng.
- [ ] **$ref**, required/nullable, enum, int64, examples được validate với toolchain đã pin.
- [ ] Docs/mock/SDK được sinh từ **cùng revision hoặc cùng bundle**.
- [ ] Mock có kịch bản thành công và lỗi; không được xem là chứng minh business logic/auth.
- [ ] SDK được build, typecheck và thử gọi backend thật; null, int64, error handling, header Location được kiểm tra.
- [ ] Spring backend có kiểm thử status, response headers, schema, authorization và persistence.
- [ ] CI có lint, compatibility diff, generation reproducibility và contract/integration tests.
- [ ] API/SDK versions, deprecation và migration được công bố khi có breaking change.
- [ ] Không đưa JWT/secrets/PII vào spec/examples/mock; tách base URL và kiểm soát token ở runtime.

**Kết luận:** dùng **một hợp đồng OpenAPI có kiểm soát phiên bản** để sinh tài liệu, mock và SDK giúp giảm lệch cấu trúc giữa các nhóm, tạo điều kiện phát triển song song và kiểm soát phát hành. Giá trị thực sự đến từ **hợp đồng được review, đầu ra có thể tái lập và kiểm thử đối chiếu backend thật**. Generator không thay thế việc bảo vệ quyền, thực thi nghiệp vụ hay đánh giá tương thích; nó chỉ giúp tất cả các bên bắt đầu từ cùng một cam kết rõ ràng.
