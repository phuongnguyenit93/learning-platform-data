# Vai trò OpenAPI và khác biệt với bản thân phong cách REST

## 1. Hai câu hỏi khác nhau: API hoạt động theo nguyên tắc nào và được mô tả ra sao?

Khi xây dựng REST API bằng Java/Spring, chúng ta thường cần một tài liệu để frontend, mobile, đối tác và đội kiểm thử biết endpoint nào tồn tại, gửi dữ liệu gì, xác thực ra sao và nhận mã HTTP nào. **OpenAPI Specification (OAS)** đáp ứng nhu cầu mô tả hợp đồng HTTP API ở dạng máy có thể đọc, phổ biến là YAML hoặc JSON.

Nhưng **OpenAPI không phải bản thân REST**:

- **REST (Representational State Transfer)** là *phong cách kiến trúc* với các ràng buộc về cách thành phần tương tác và biểu diễn tài nguyên.
- **OpenAPI** là *đặc tả mô tả giao diện HTTP API*: path, method, parameter, request body, response, schema, security scheme, ví dụ và metadata.
- **Implementation/runtime** là hành vi thực của server, gateway, database, cache và client; nó có thể đúng hoặc lệch so với cả thiết kế REST lẫn tài liệu OpenAPI.

Ba lớp này bổ sung cho nhau, không thay thế cho nhau. **Một API dùng OpenAPI đầy đủ vẫn có thể vi phạm ngữ nghĩa HTTP và các ràng buộc REST. Một REST API có thể tồn tại mà không xuất bản tài liệu OpenAPI.**

> **Mục tiêu bài học:** phân biệt rạch ròi REST và OpenAPI, đọc/viết một hợp đồng OpenAPI cho resource, liên kết đặc tả với HTTP và Java/Spring, nhận ra những điều OAS không bảo đảm, rồi tổ chức kiểm thử và tiến hóa hợp đồng an toàn.

## 2. REST là phong cách kiến trúc, không phải tên một định dạng tài liệu

REST được mô tả qua các ràng buộc kiến trúc. Với HTTP API, những ràng buộc cần nắm:

| Ràng buộc REST | Nội dung | Điều cần kiểm chứng trên hệ thống thật |
|---|---|---|
| **Client–server** | Tách giao diện/nhu cầu client khỏi quản lý dữ liệu và nghiệp vụ phía server | Client không phụ thuộc DB hoặc entity nội bộ |
| **Stateless** | Mỗi request chứa ngữ cảnh cần thiết để server hiểu và xử lý; server không dựa vào conversation state lưu theo phiên trên một node | Retry/chuyển node không phải dựa vào session tiến trình cục bộ |
| **Cacheable** | Response thể hiện rõ khả năng cache hoặc không cache | Cache-Control, validator và invalidation đúng với loại dữ liệu |
| **Uniform interface** | Giao diện thống nhất dựa trên tài nguyên, representation, thông điệp tự mô tả và hypermedia | URI, method/status, media type và liên kết/hành động được dùng đúng |
| **Layered system** | Client có thể đi qua gateway, proxy, CDN mà không cần biết tất cả tầng phía sau | Authentication/cache/routing vẫn giữ đúng ngữ nghĩa |
| **Code-on-demand (tùy chọn)** | Server có thể gửi mã để mở rộng hành vi client trong một số hệ thống | Không phải yêu cầu bắt buộc của REST API |

Uniform interface gồm các ý quan trọng:

1. **Identification of resources:** URI định danh resource, ví dụ /api/orders/ord-42.
2. **Manipulation through representations:** client trao đổi representation (JSON, XML, bytes...) thay vì truy cập trực tiếp cấu trúc lưu trữ.
3. **Self-descriptive messages:** HTTP method, status, header, media type và representation giúp diễn giải thông điệp.
4. **Hypermedia as the engine of application state (HATEOAS):** response có thể cung cấp link/hành động để client khám phá bước tiếp theo theo trạng thái hiện tại.

Trong thực hành, nhiều API được gọi là “REST API” dù chủ yếu là *resource-oriented HTTP+JSON* và không triển khai hypermedia đầy đủ. Cần mô tả chính xác mức độ tuân thủ, thay vì cho rằng chỉ cần GET/POST và URL đẹp là đương nhiên đạt toàn bộ phong cách REST.

### 2.1. Resource không đồng nghĩa một row trong database

Đơn hàng có thể là resource /api/orders/ord-42. Representation của nó có thể tổng hợp nhiều bảng, quyền, dữ liệu snapshot và trạng thái nghiệp vụ:

~~~json
{"id":"ord-42","status":"CONFIRMED",
 "links":{"self":"/api/orders/ord-42",
          "items":"/api/orders/ord-42/items"}}
~~~

Link trong ví dụ giúp điều hướng; nó **không tự cấp quyền** truy cập /items. Một API chỉ chứa links tự thiết kế cũng chưa tự động đáp ứng đầy đủ HATEOAS nếu client vẫn phải hard-code mọi workflow. Tính hypermedia phụ thuộc media type và ngữ nghĩa liên kết/hành động mà client có thể hiểu.

### 2.2. REST không bắt buộc dùng JSON hoặc OpenAPI

Representation có thể là JSON, ảnh, PDF hay media type khác. HTTP đã định nghĩa ngữ nghĩa method/status; REST không bắt buộc có file OpenAPI. OAS giúp mô tả và kiểm thử hợp đồng.

## 3. OpenAPI mô tả được gì?

OpenAPI là đặc tả có cấu trúc cho HTTP API. Một tài liệu OpenAPI thường gồm:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **openapi, info** | Dùng phiên bản OAS nào và mô tả API gì? | openapi: 3.1.0; title; version |
| **servers** | Server URL mặc định là gì? | https://api.example.test |
| **paths + operations** | URI template và method nào được hỗ trợ? | GET /orders/{orderId}, POST /orders |
| **parameters** | Path/query/header/cookie cần gì? | orderId, cursor, If-None-Match |
| **requestBody/content** | Input body dùng media type và schema nào? | application/json + CreateOrderRequest |
| **responses/content/headers** | Status nào, body/header có hình dạng gì? | 201 + Location, 400 Problem Details |
| **components/schemas** | Kiểu dữ liệu và constraint có thể tái sử dụng? | Order, OrderItem, ApiProblem |
| **securitySchemes + security** | API khai báo cơ chế xác thực nào? | HTTP bearer, OAuth2 scopes |
| **tags, description, examples** | Giải thích cách dùng cho con người/SDK? | tags: Orders, sample requests |
| **links/callbacks/webhooks** | Một số quan hệ thao tác hoặc tương tác bổ sung? | Liên kết response với operation khác |

Đặc tả này hỗ trợ **tạo tài liệu tương tác, code/SDK generation, kiểm tra schema, mock server, kiểm thử hợp đồng và review thay đổi API**. Tuy nhiên, OAS không tự chạy endpoint, phân quyền tenant, bảo đảm transaction, tạo pagination đúng hoặc chống lỗi N+1.

### 3.1. Phạm vi của một schema

Một schema có thể quy định:

~~~yaml
type: object
required: [sku, quantity]
properties:
  sku:
    type: string
    minLength: 1
  quantity:
    type: integer
    minimum: 1
additionalProperties: false
~~~

Nó mô tả cấu trúc dữ liệu và một số ràng buộc cục bộ. Nó **không thể tự chứng minh** SKU thuộc đúng tenant, mặt hàng còn tồn kho, người gọi có quyền đặt hàng hoặc yêu cầu đã được xử lý lũy đẳng. Các invariant đó cần logic nghiệp vụ và kiểm thử runtime.

Đối với OAS 3.1, Schema Object dựa trên JSON Schema với sự tương thích cao hơn OAS 3.0; một số cách viết khác nhau tùy phiên bản (ví dụ biểu diễn null). Khi chọn 3.0 hay 3.1, hãy xác định **hệ sinh thái tooling** hỗ trợ thực tế rồi dùng một phiên bản nhất quán trong dự án.

## 4. API có OpenAPI tốt vẫn có thể không đúng REST

Giả sử file OpenAPI mô tả endpoint:

~~~http
GET /api/orders/ord-42/cancel HTTP/1.1
~~~

Nếu GET này **thực hiện hủy đơn**, nó vi phạm tính **safe** của GET theo ngữ nghĩa HTTP: crawler, trình duyệt, cache hoặc cơ chế prefetch có thể vô tình kích hoạt lệnh ghi. Schema OpenAPI dù hợp lệ cũng không biến hành vi đó thành đúng.

Một trường hợp khác:

~~~http
POST /api/orders/ord-42/action HTTP/1.1
Content-Type: application/json

{"action":"getOrder"}
~~~

Không thể kết luận mọi endpoint hành động đều “sai REST” chỉ từ tên path, nhưng một giao diện buộc client gửi tên hàm CRUD trong body, dùng POST cho mọi việc và trả 200 cho cả lỗi dễ làm mất ngữ nghĩa HTTP và tính đồng nhất của giao diện. Hợp đồng có thể ghi chính xác cái đang xảy ra, song **mô tả chính xác không đồng nghĩa thiết kế kiến trúc phù hợp**.

Các vấn đề tương tự còn có **stateful session** gắn vào RAM của một node, **public cache** cho dữ liệu riêng tư, thiếu liên kết hypermedia và kiểm tra quyền tenant sai. OpenAPI có thể ghi lại giao diện hoặc một số header/status liên quan nhưng không chứng minh các ràng buộc REST và chính sách dữ liệu được tuân thủ trong runtime.

Ngược lại, một server có thể vận hành theo các ràng buộc REST nhưng chưa xuất bản OpenAPI. Khi đó điểm yếu chính nằm ở **hợp đồng cho con người và máy công cụ**, không phải mặc nhiên là thiếu REST.

## 5. Từ REST resource đến hợp đồng HTTP cụ thể

Để viết OpenAPI có ích, hãy thiết kế HTTP trước. Ví dụ với resource đơn hàng:

| Mục đích | Request | Kết quả dự kiến |
|---|---|---|
| Tạo đơn | POST /api/orders | 201 Created, Location, body Order |
| Xem một đơn | GET /api/orders/{orderId} | 200 JSON; 404 nếu không có/không được thấy theo policy |
| Xem tập hợp | GET /api/orders?limit=20&cursor=... | 200, phân trang và filter rõ |
| Thay toàn bộ representation nếu hỗ trợ | PUT /api/orders/{orderId} | 200/204; không bỏ qua điều kiện cập nhật |
| Cập nhật từng phần nếu hỗ trợ | PATCH /api/orders/{orderId} | 200/204; semantics phụ thuộc patch media type |
| Hủy đơn theo nghiệp vụ | Thao tác nghiệp vụ được mô hình hóa rõ | Chọn POST tới transition/operation resource khi phù hợp, không dùng GET để gây hủy |

Trạng thái như **409 Conflict**, **412 Precondition Failed**, **422 Unprocessable Content** cần được dùng đúng ngữ nghĩa đã thống nhất. Không buộc mọi API phải có đầy đủ PUT/PATCH/DELETE: chỉ công bố operation thực sự được hỗ trợ và có nghiệp vụ rõ.

### 5.1. Ví dụ phản hồi tạo resource

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
Authorization: Bearer <test-token>
Idempotency-Key: order-intent-a72

{"customerId":"cus-17","items":[{"sku":"BOOK-01","quantity":2}]}

HTTP/1.1 201 Created
Location: /api/orders/ord-42
Content-Type: application/json
Cache-Control: no-store

{"id":"ord-42","status":"PENDING_PAYMENT","totalAmount":350000}
~~~

Đây là **một hợp đồng minh họa**: Idempotency-Key phải được ứng dụng thực thi bằng deduplication bền vững và phạm vi key rõ ràng. Việc chỉ khai báo header trong OpenAPI **không ngăn** hai đơn bị tạo khi client retry sau timeout.

### 5.2. Ví dụ đọc có điều kiện

Khi GET /api/orders/ord-42 gửi **If-None-Match: "ord-42-view-v3"** và representation hiện tại có validator khớp, server có thể trả **304 Not Modified**, không có response body. Điều này chỉ đúng khi caller vẫn được quyền đọc; OAS không tự thực thi kiểm tra đó. Với dữ liệu nhạy cảm, chính sách no-store có thể thích hợp hơn việc lưu để revalidate.

## 6. Ví dụ OpenAPI 3.1 tự chứa

Dưới đây là một tài liệu OAS minh họa cho **hai operation**: tạo đơn và đọc đơn. Nó không phải toàn bộ hệ thống, nhưng thể hiện các phần quan trọng của hợp đồng HTTP:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
  description: Contract for creating and reading an order
servers:
  - url: https://api.example.test
security:
  - bearerAuth: []
paths:
  /api/orders:
    post:
      operationId: createOrder
      summary: Create one order
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          description: Stable per logical creation intent
          schema:
            type: string
            minLength: 1
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Created or saved result of the same intent
          headers:
            Location:
              required: true
              schema:
                type: string
                format: uri-reference
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          description: Missing or invalid authentication
        '403':
          description: Not permitted to create an order
        '409':
          description: Conflicting resource state or key/payload reuse
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Read an order visible to the caller
      parameters:
        - in: path
          name: orderId
          required: true
          schema:
            type: string
        - in: header
          name: If-None-Match
          required: false
          schema:
            type: string
      responses:
        '200':
          description: Current representation of the order
          headers:
            ETag:
              schema:
                type: string
            Cache-Control:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '304':
          description: Matching validator, no response body
          headers:
            ETag:
              schema:
                type: string
        '401':
          description: Missing or invalid authentication
        '403':
          description: Insufficient permission
        '404':
          description: Order absent or deliberately hidden
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  responses:
    BadRequest:
      description: Malformed or invalid request
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, items]
      properties:
        customerId:
          type: string
        items:
          type: array
          minItems: 1
          items:
            type: object
            required: [sku, quantity]
            properties:
              sku:
                type: string
                minLength: 1
              quantity:
                type: integer
                minimum: 1
    Order:
      type: object
      required: [id, status, totalAmount]
      properties:
        id:
          type: string
        status:
          type: string
          enum: [PENDING_PAYMENT, CONFIRMED, CANCELLED]
        totalAmount:
          type: integer
          minimum: 0
    ApiProblem:
      type: object
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
~~~

**Giới hạn có chủ đích:** ví dụ chưa mô tả đủ pagination, tất cả mã lỗi, rate limit, độ phức tạp nghiệp vụ và chính sách retention của Idempotency-Key. Với OpenAPI 3.1, một số quy tắc JSON Schema có khác biệt so với 3.0; hãy tránh copy schema từ hai phiên bản rồi coi chúng hoàn toàn tương đương.

### 6.1. Đọc đúng ý nghĩa của các khai báo

- **openapi: 3.1.0** là phiên bản *định dạng tài liệu*, còn info.version: 1.0.0 là phiên bản do API công bố; hai giá trị không cùng ý nghĩa.
- **paths** chứa URI *template*; orderId được khai báo ở in: path với required: true.
- **requestBody** mô tả JSON và schema được gửi; **responses** mô tả các status/media type/header mà server hứa hỗ trợ.
- **$ref** giúp tái sử dụng cấu phần, không phải lời gọi mạng hay tự động truy vấn tài nguyên.
- **securitySchemes** mô tả bearer token; **bearerFormat: JWT** là gợi ý mô tả định dạng, không kiểm tra chữ ký, issuer, audience hoặc scopes.
- **304** cố ý không có content/body. Thêm application/json vào 304 chỉ để sinh SDK sẽ tạo hợp đồng sai.

**Lưu ý:** RFC 9457 định nghĩa Problem Details với media type application/problem+json. Trường type/title/status/detail/instance có ý nghĩa chuẩn; các extension như code hoặc invalid-params phải được **API tự định nghĩa schema**, không coi chúng là trường chuẩn có sẵn.

## 7. Design-first và code-first: hai cách giữ hợp đồng

### 7.1. Design-first (contract-first)

Nhóm thống nhất OpenAPI trước khi triển khai:

~~~text
Nhu cầu nghiệp vụ
     -> Resource/URI/HTTP semantics
     -> OpenAPI review với consumer
     -> Mock / SDK / test cases
     -> Java/Spring implementation
     -> Contract test / deployment
~~~

**Lợi ích:** frontend/backend làm song song, thảo luận sớm trạng thái lỗi, tham số phân trang, authorization và các thay đổi phá vỡ client. **Rủi ro:** spec có thể trở thành tài liệu lý tưởng nhưng runtime không đáp ứng nếu thiếu kiểm thử và trách nhiệm duy trì.

### 7.2. Code-first

Nhóm viết controller/DTO/annotation trước, sau đó sinh mô tả OpenAPI bằng công cụ phù hợp với Spring:

~~~text
Resource design -> Spring controller/DTO
               -> OpenAPI generation
               -> Review generated contract
               -> Tests + publish
~~~

**Lợi ích:** giảm công việc lặp lại ở các endpoint đơn giản, tài liệu gần với type/annotation. **Rủi ro:** đặc tả sinh tự động có thể bỏ sót 401/403, điều kiện ETag, quy tắc idempotency, response 304/202, quyền tenant hoặc semantics không biểu đạt được bằng DTO.

Trong cả hai mô hình, **OpenAPI phải có chủ sở hữu, quy trình review, kiểm tra CI và versioning**. Không nên xem “đã generate swagger” là hoàn thành thiết kế REST.

### 7.3. Generator hỗ trợ đến đâu?

Generator có thể sinh path, DTO, SDK, tài liệu, mock hoặc schema validator khi được cấu hình. Nó **không tự xác định resource đúng, kiểm tra phân quyền, bảo đảm retry/idempotency, xử lý 304 hay thực thi invariant nghiệp vụ**. Những trách nhiệm đó thuộc thiết kế, server và kiểm thử.

## 8. Java/Spring: map endpoint thành hợp đồng và giữ semantics

Một controller minh họa:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.net.URI;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record ItemInput(@NotBlank String sku, @Min(1) int quantity) {}
record CreateOrderInput(
        @NotBlank String customerId,
        @NotEmpty List<@Valid ItemInput> items) {}
record OrderView(String id, String status, long totalAmount) {}

interface OrdersUseCase {
    // Kiểm tra scope, owner/tenant, invariant và idempotency.
    OrderView create(
            Authentication caller, String key, CreateOrderInput input);
    OrderView readVisible(Authentication caller, String id);
}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrdersUseCase orders;

    OrdersController(OrdersUseCase orders) {
        this.orders = orders;
    }

    @PostMapping(consumes = "application/json",
                 produces = "application/json")
    ResponseEntity<OrderView> create(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateOrderInput input,
            Authentication caller) {

        OrderView result = orders.create(caller, key, input);
        return ResponseEntity
                .created(URI.create("/api/orders/" + result.id()))
                .cacheControl(CacheControl.noStore())
                .body(result);
    }

    @GetMapping(path = "/{orderId}", produces = "application/json")
    ResponseEntity<OrderView> get(
            @PathVariable String orderId, Authentication caller) {

        OrderView view = orders.readVisible(caller, orderId);
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(view);
    }
}
~~~

**Đây là ví dụ tối thiểu**, chưa có implementation OrdersUseCase, security configuration, exception handler, lưu kết quả idempotency hoặc ETag. Controller trên **không triển khai 304**, vì vậy nếu dùng nguyên mã, OpenAPI ở mục 6 sẽ **lệch runtime** tại response 304. Cần hoặc triển khai conditional GET đúng quy tắc, hoặc bỏ 304 khỏi hợp đồng được xuất bản. Đây chính là bài học về khác biệt giữa **spec** và **hành vi thật**.

Các chi tiết nên kiểm tra khi triển khai:

- **POST trả 201 + Location** sau khi tạo đơn thành công; lệnh tạo trùng cần record bền vững nếu client retry cùng Idempotency-Key.
- **@Valid** xử lý một phần ràng buộc DTO, không thay thế kiểm tra tenant, tồn kho, trạng thái đặt hàng hoặc uniqueness.
- **GET phải safe**, không thay đổi trạng thái đơn chỉ vì client đọc hoặc crawler truy cập.
- **404 và 403** phải theo chính sách che giấu/authorization; không tiết lộ dữ liệu khác tenant qua đường tìm ID.
- **Cache-Control** cho đơn hàng nhạy cảm cần chính sách cụ thể. Ví dụ chọn no-store; nếu muốn 304 hữu ích cho private cache, phải cân nhắc một chính sách lưu/revalidate được cho phép.
- **ResponseEntity** chỉ giúp tạo status/header/body đúng nếu business code trả đúng kết quả; nó không tự chứng minh REST constraints.

### 8.1. Mô tả thêm bằng annotation có làm API đúng hơn?

Các annotation mô tả như Operation, ApiResponse, Parameter hoặc Schema **chỉ hỗ trợ tạo tài liệu**, không thực thi business rule hay security. Nếu tài liệu hứa 409 nhưng runtime trả 500, API vẫn lệch hợp đồng.

Tương tự, exception handler dùng ProblemDetail có thể chuẩn hóa lỗi:

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class OrderErrorAdvice {
    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail notFound() {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setType(URI.create(
                "https://api.example.test/problems/order-not-found"));
        problem.setTitle("Order not found");
        return problem;
    }
}
~~~

OrderNotFoundException là exception ứng dụng cần định nghĩa; Spring có thể serialize ProblemDetail thành application/problem+json theo cấu hình thích hợp. **Không copy stack trace hoặc rejectedValue nhạy cảm** vào detail. Nếu cần phân biệt 400/409/422, hãy định nghĩa và kiểm thử từng trường hợp thay vì bắt mọi exception thành một lỗi chung.

## 9. Bảo mật nằm trong runtime, không nằm “bên trong file YAML”

Trong mục 6 có:

~~~yaml
security:
  - bearerAuth: []
~~~

Khai báo này nói rằng các operation sử dụng scheme bearerAuth theo mô tả; nó **không tạo một Spring Security filter**, không xác minh chữ ký JWT, issuer/audience, token expiry, scope hay quyền sở hữu đơn. Để đạt bảo mật cần triển khai và kiểm thử độc lập:

1. **Authentication:** xác thực token/credential và từ chối request không hợp lệ (thường 401, với challenge phù hợp).
2. **Authorization:** kiểm tra role/scope và **ownership/tenant trên từng resource**; thiếu quyền có thể là 403 hoặc 404 che giấu theo chính sách.
3. **Validation:** chặn payload sai kiểu, số lượng âm, body quá lớn, header không đúng; không tin schema OpenAPI sẽ chạy tự động trên mọi request.
4. **Data minimization:** chỉ serialize những trường caller được phép xem; không trả nội bộ hoặc thông tin cá nhân vì DTO có thuộc tính ấy.
5. **Operational protection:** rate limit/quota, logging có masking, cache policy, timeout và kiểm tra dependency.

Đặc biệt với API nhiều tenant, không nên chỉ đọc tenantId từ query string hoặc body rồi xem đó là sự thật. Dùng tenant context từ danh tính đã xác minh và áp dụng giới hạn tại truy vấn hoặc domain. **Mã ID khó đoán không thay được authorization**.

Một OpenAPI file có thể mô tả 401/403 và OAuth2 scopes, nhưng cũng không bảo đảm rằng **từng nhánh logic runtime** áp dụng đúng chính sách. Cần kiểm thử truy cập trái phép cho cả GET, POST, response lỗi, link download và các thao tác theo ID.

## 10. Kiểm thử hợp đồng: từ YAML đến hành vi thực

**Linter/validator OpenAPI** chỉ cho biết tài liệu có tuân cấu trúc, tham chiếu $ref tồn tại, path parameter khai báo hợp lệ hay không. Nó không chứng minh server thật trả 201 đúng Location, dùng GET an toàn hoặc ngăn đọc dữ liệu khác tenant.

Ma trận cần kiểm chứng:

| Kiểm thử | Điều kiện | Kỳ vọng |
|---|---|---|
| Create | POST JSON hợp lệ, quyền phù hợp | 201, Location, body theo schema |
| Validation | quantity = 0 hoặc thiếu items | 400/422 **đúng như contract đã chọn**, không ghi đơn |
| Không có token | GET/POST protected | 401; không lộ body nhạy cảm |
| Không đủ quyền | GET order của tenant khác | 403/404 đúng policy, không lộ dữ liệu |
| Không tìm thấy | GET ID không có | 404, response lỗi theo contract |
| Idempotency | Gửi lại POST cùng key/payload sau mất phản hồi | Không tạo đơn thứ hai |
| Conditional GET nếu đã công bố | If-None-Match khớp | 304, không có body, quyền vẫn được kiểm tra |
| Malformed JSON | Body sai cú pháp | 400, không xuất stack trace |
| Media type không hỗ trợ | Content-Type sai | 415 nếu API quy định |
| Body quá lớn | Vượt hạn mức | 413, không cạn memory |

Ví dụ kiểm thử controller với MockMvc (fragment cần service test fixture và Spring Security test principal):

~~~java
mockMvc.perform(post("/api/orders")
        .with(jwt())
        .header("Idempotency-Key", "intent-test-1")
        .contentType("application/json")
        .content("""
            {"customerId":"cus-17",
             "items":[{"sku":"BOOK-01","quantity":2}]}
            """))
    .andExpect(status().isCreated())
    .andExpect(header().string(
            "Location", startsWith("/api/orders/")))
    .andExpect(jsonPath("$.id").exists());
~~~

Các hàm post, jwt, status, header, jsonPath, startsWith là static import từ MockMvc/Spring Security Test/Hamcrest; cần khai báo MockMvc và mock use case. Test trên xác minh response 201 **không đủ** để chứng minh lưu đơn chính xác: integration test phải kiểm tra DB, key lũy đẳng, isolation tenant, side effects và đường lỗi.

### 10.1. Quy trình CI tối thiểu

1. **Validate/lint OAS:** cú pháp YAML/JSON, schema, operationId, parameter required, $ref, tiêu chuẩn đặt tên.
2. **Review thay đổi contract:** so sánh phiên bản mới/cũ, nhận diện breaking changes với consumer.
3. **Contract tests:** gọi server hoặc môi trường test, xác minh status, header, media type và JSON body.
4. **Security & negative tests:** token thiếu/hết hạn, quyền tenant, payload lỗi, rate/size limits.
5. **Publish có version:** phát hành bản mô tả gắn với phiên bản API và build có thể truy vết.

Nếu dùng code-first, CI còn nên so **OpenAPI sinh từ build** với hợp đồng đã phê duyệt để phát hiện drift. Nếu design-first, kiểm thử cần chứng minh implementation khớp spec đã thống nhất. **Mock server khớp YAML không đồng nghĩa production server khớp YAML**.

## 11. Tiến hóa OpenAPI và tương thích client

| Thay đổi | Rủi ro đối với client cũ |
|---|---|
| Xóa/đổi tên path hoặc method | Client gọi endpoint cũ thất bại |
| Thêm request field bắt buộc | Request cũ không còn hợp lệ |
| Đổi response field từ string sang integer | Lỗi deserialize hoặc xử lý nghiệp vụ |
| Đổi status 201 thành 200 không báo trước | Client phụ thuộc status/Location bị ảnh hưởng |
| Loại bỏ mã enum đã công bố | Client cũ không hiểu tài nguyên hiện hữu |
| Thêm một giá trị enum response | Có thể gây lỗi cho client dùng exhaustive switch |
| Thêm optional response field | Thường dễ tương thích hơn, nhưng client strict vẫn có thể lỗi |
| Đổi chính sách pagination, idempotency, auth | Có thể phá hành vi dù schema không đổi |

**Không có công cụ diff nào tự hiểu đầy đủ tính tương thích nghiệp vụ.** Ví dụ thêm field tùy chọn có vẻ an toàn về schema nhưng có thể khiến response lớn hơn hoặc chứa dữ liệu nhạy cảm. Review cần kết hợp consumer contract tests, thay đổi hành vi, triển khai song song và thông báo chuyển đổi.

OpenAPI có **Link Object** liên kết response với operation khác, nhưng không tự biến response runtime thành hypermedia. HATEOAS đòi hỏi liên kết/hành động thực tế có ngữ nghĩa theo trạng thái và client hiểu cách dùng.

## 12. Bài tập thực hành có đáp án

**Bài 1 — Phân biệt REST và OAS.** Nhóm có file OpenAPI hợp lệ, nhưng GET /orders/42/cancel làm thay đổi trạng thái đơn. Có thể tuyên bố đạt REST chỉ nhờ OAS không? **Đáp án:** Không; GET phải safe. Cần thiết kế thao tác gây thay đổi bằng method/resource phù hợp và cập nhật đặc tả.

**Bài 2 — Tìm phần thiếu của hợp đồng.** POST /orders tạo đơn và trả Location nhưng file OpenAPI chỉ khai response 200 JSON. **Đáp án:** Phải mô tả đúng 201 Created, header Location, schema body và các phản hồi lỗi thực tế; đồng thời kiểm thử runtime.

**Bài 3 — Bảo mật.** OAS ghi security bearerAuth, GET /orders/{id} vẫn trả đơn của tenant B khi token thuộc A. Lỗi nằm ở đâu? **Đáp án:** Authorization/resource ownership runtime bị thiếu hoặc sai. YAML không tự lọc tenant; cần sửa truy vấn/ACL và thêm negative test.

**Bài 4 — Contract drift.** Spec mô tả 304 cho If-None-Match; controller chỉ trả 200 JSON. Cần làm gì? **Đáp án:** Triển khai conditional GET đúng validator/quyền/cache policy và test 304 không có body, hoặc bỏ cam kết 304 khỏi OAS đến khi hỗ trợ.

**Bài 5 — Breaking changes.** API thêm status PAYMENT_REVIEW vào enum phản hồi Order. Thay đổi này có chắc an toàn? **Đáp án:** Không; client dùng switch exhaustive có thể không xử lý giá trị mới. Cần đánh giá consumer và có fallback/versioning theo chính sách.

## 13. Checklist và kết luận

- [ ] Đã tách rõ **REST architecture**, **OpenAPI contract** và **runtime implementation**?
- [ ] Resource, URI, method, HTTP status và media type được thiết kế trước khi generate tài liệu?
- [ ] OAS dùng phiên bản nhất quán, có servers/paths/parameters/requestBody/responses/schema?
- [ ] Mỗi path parameter có định nghĩa; body, header và lỗi có schema/status đúng?
- [ ] Security scheme trong OAS được thực thi bằng authentication/authorization thật?
- [ ] Không dựa vào schema để thay tenant check, business invariant hoặc idempotency?
- [ ] Spec không hứa 304, 202, ETag hoặc những response mà runtime chưa hỗ trợ?
- [ ] Có lint, API diff, contract test, security test và quy trình review/publish theo version?
- [ ] Đã đánh giá thay đổi phá client và đặc tính REST ngoài khả năng kiểm tra của OAS?

**Kết luận:** REST giúp quyết định **cách tổ chức tương tác tài nguyên và ngữ nghĩa giao thức**; OpenAPI giúp **diễn đạt, chia sẻ, sinh công cụ và kiểm tra hợp đồng HTTP**. Cả hai đều quan trọng nhưng không thay thế nhau. Một API đáng tin cần thiết kế resource/HTTP đúng, mô tả OAS chính xác, triển khai Java/Spring an toàn và liên tục kiểm thử để hợp đồng không lệch khỏi hành vi thực tế.
