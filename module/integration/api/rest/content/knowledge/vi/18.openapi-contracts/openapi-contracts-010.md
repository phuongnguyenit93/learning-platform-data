# Ví dụ thành công, lỗi, phân trang và yêu cầu có điều kiện

## 1. Ví dụ OpenAPI là một phần của hợp đồng, không phải dữ liệu trang trí

Một nhóm phát triển công bố **GET /orders**, **POST /orders** và **PATCH /orders/{id}**. OpenAPI chỉ ghi rằng endpoint có thể trả JSON và status **200/201/400/412**. Backend hiểu các status, nhưng frontend vẫn phải đoán: danh sách rỗng có trả **[]** hay **items: []**? Lỗi có mã nghiệp vụ không? PATCH cần **If-Match** nào? Response tạo đơn chứa **Location** hay chỉ ID?

**Ví dụ trong OpenAPI** thu hẹp khoảng trống đó bằng các cặp request/response cụ thể, đúng schema, có mã HTTP, header và nội dung phù hợp. Một bộ ví dụ tốt phải mô tả cả **đường thành công, danh sách không có kết quả, lỗi client và điều kiện cập nhật/tái xác nhận**. Tuy nhiên, một ví dụ **không tự động trở thành quy tắc validation**: ràng buộc thực vẫn nằm trong schema, parameter, response và logic của API.

Trong module **INTEGRATION_API_REST**, bài học tập trung cách tác giả hợp đồng REST API dùng OpenAPI để thống nhất **resource/URI, phương thức, status, phân trang, cache, idempotency, xác thực, lỗi và kiểm thử Java/Spring**. Thay vì trình bày mọi cú pháp OpenAPI, chúng ta sẽ dựng một hợp đồng mẫu cho Orders API và kiểm tra nó ở nhiều góc.

### Mục tiêu

Sau bài này bạn có thể:

1. Phân biệt vị trí của **schema.example**, **Media Type Object example/examples** và **components.examples**.
2. Viết ví dụ đúng **200, 201, 204**, lỗi **application/problem+json**, danh sách rỗng và danh sách có trang tiếp.
3. Mô tả **ETag, If-None-Match/304, If-Match/412, 428** trong hợp đồng và hiểu giới hạn của các ví dụ.
4. Thiết kế ví dụ không làm lộ dữ liệu thật và không mâu thuẫn giữa response, security, pagination và quyền truy cập.
5. Thực hiện và kiểm thử hợp đồng bằng Spring MVC, MockMvc và kiểm tra OpenAPI.

## 2. Đặt ví dụ đúng vị trí OpenAPI

| Vị trí trong OAS 3.0.3 | Ý nghĩa |
|---|---|
| **Schema Object: example** | Mẫu chung của property hoặc kiểu dữ liệu; không đại diện cho cả response |
| **requestBody/response content: example** | Một mẫu body theo media type cụ thể |
| **content: examples** | Nhiều mẫu có tên **empty, withNext, stale**; mỗi mục có **value** hoặc **$ref** tới Example Object |
| **components.examples** | Tái sử dụng mẫu giữa nhiều operation |
| **parameter/header: example/examples** | Minh họa limit, cursor, ETag hoặc Location, nhất quán với schema tương ứng |

Tại cùng một **Media Type Object**, **example** và **examples** loại trừ nhau. Ví dụ response **404** nên đặt dưới **responses."404".content.application/problem+json.examples**, không đặt trong schema Order của response 200. Một Example Object có thể dùng **summary, description, value**, hoặc **externalValue** để tham chiếu dữ liệu ngoài; không dùng value và externalValue cùng nhau.

Khi dùng **$ref**, phân biệt **#/components/schemas/Order** (quy tắc kiểu dữ liệu) với **#/components/examples/EmptyPage** (một body mẫu). Ví dụ phải thỏa ràng buộc kiểu, required, enum, nullable; một ví dụ hợp lệ không tự đặt ra ràng buộc mới. OpenAPI đầy đủ ở phần 5 minh họa cách dùng cả **example**, **examples** và **components.examples**.

## 3. Bối cảnh Orders API và những giả định hợp đồng

| Endpoint | Chức năng | Ví dụ chính |
|---|---|---|
| **GET /orders?status=...&limit=...&cursor=...** | Liệt kê các đơn thuộc phạm vi caller | **200** với items và page; có thể rỗng |
| **POST /orders** | Tạo đơn | **201**, Location, ETag và body |
| **GET /orders/{id}** | Đọc một đơn | **200** với ETag hoặc **304** với If-None-Match |
| **PATCH /orders/{id}** | Đổi trạng thái | **200** khi If-Match đúng; **412** khi stale; **428** nếu thiếu |

API dùng **Bearer authentication**; dữ liệu đơn, metadata phân trang và validator chỉ hiển thị theo **quyền đã xác thực**. Order có **id, status, totalAmount, version**; số tiền dùng số nguyên VND trong ví dụ. Filter status nhận **DRAFT/CONFIRMED/CANCELLED**, limit trong **1–100**, cursor là token opaque; kết quả lọc rỗng vẫn có **items: []**. PATCH chỉ chấp nhận thay trường **status** của một hợp đồng Merge Patch giới hạn. Mọi ID, giá trị, host và token dưới đây đều là **dữ liệu giả**.

**201 Created** phù hợp khi tạo resource thành công; **204 No Content** dành cho thao tác thành công không gửi body; **202 Accepted** dành cho yêu cầu được nhận nhưng xử lý chưa hoàn tất. Không chọn status chỉ vì body dài hay ngắn.

## 4. Viết ví dụ danh sách có dữ liệu, rỗng và trang kế tiếp

### 4.1. Cùng một schema cho cả hai trạng thái

Response danh sách có trang tiếp:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-cache

{
  "items": [
    {"id":"ord-101","status":"DRAFT","totalAmount":250000,"version":1},
    {"id":"ord-102","status":"DRAFT","totalAmount":175000,"version":2}
  ],
  "page": {
    "limit": 2,
    "nextCursor": "cursor-next-opaque",
    "hasNext": true
  }
}
~~~

Khi filter hợp lệ nhưng không có kết quả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-cache

{
  "items": [],
  "page": {
    "limit": 20,
    "nextCursor": null,
    "hasNext": false
  }
}
~~~

**Không đổi kiểu dữ liệu thành null**, không trả **404** chỉ vì số phần tử bằng 0, và không tự trả **204** nếu client cần schema và metadata thống nhất. **nextCursor** là token opaque; client không tự suy nội dung/ID và không ghép bằng cách đoán.

### 4.2. Phân biệt kết quả rỗng và tham số sai

| Request | Hành vi ví dụ |
|---|---|
| status=CONFIRMED, không có đơn | **200** với items: [] |
| status=UNRECOGNIZED | **400**, mã **INVALID_STATUS_FILTER** |
| limit=0 hoặc limit=1000 | **400**, mã **INVALID_LIMIT** |
| cursor bị sửa sai hoặc không hợp lệ | **400**, mã **INVALID_CURSOR** |
| Không được xác thực | **401**; không trả một danh sách trống giả |
| Không có quyền trên một resource cụ thể | **403** hoặc **404** che giấu theo chính sách |

Cursor phải được xác thực và gắn với những yếu tố có ý nghĩa như **filter, sort, snapshot/expiry, phạm vi tenant**, nếu không có thể trả kết quả sai hoặc rò dữ liệu. Sắp xếp ổn định, chẳng hạn **createdAt DESC, id DESC**, giúp hạn chế duplicate/missing items khi phân trang. Nếu contract có eventual consistency, cần mô tả giới hạn của một chuỗi trang qua dữ liệu thay đổi.

## 5. Hợp đồng OpenAPI 3.0.3 mẫu

Tài liệu rút gọn sau giữ **đủ bốn luồng**: danh sách 200 có/rỗng, tạo 201, GET có điều kiện 304 và PATCH có điều kiện 412/428. Các ví dụ xuất hiện đúng status/media type; phần còn lại có thể mở rộng bằng response 401/403/409/429 theo chính sách API.

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
security:
  - bearerAuth: []

paths:
  /orders:
    get:
      summary: Liệt kê đơn trong phạm vi quyền
      parameters:
        - in: query
          name: status
          schema:
            type: string
            enum: [DRAFT, CONFIRMED, CANCELLED]
        - in: query
          name: limit
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - in: query
          name: cursor
          description: Opaque pagination token
          schema: {type: string}
      responses:
        "200":
          description: Trang dữ liệu, có thể rỗng
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderPage"
              examples:
                withNext:
                  value:
                    items:
                      - {id: ord-101, status: DRAFT, totalAmount: 250000, version: 1}
                    page: {limit: 1, nextCursor: cursor-next-opaque, hasNext: true}
                empty:
                  $ref: "#/components/examples/EmptyPage"
        "400":
          description: Query parameter không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
              examples:
                invalidLimit:
                  value:
                    type: https://api.example.test/problems/invalid-query
                    title: Invalid query
                    status: 400
                    code: INVALID_LIMIT

    post:
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [totalAmount]
              properties:
                totalAmount: {type: integer, minimum: 1}
            example: {totalAmount: 250000}
      responses:
        "201":
          description: Đã tạo đơn hàng
          headers:
            Location:
              schema: {type: string, format: uri-reference}
              example: /orders/ord-101
            ETag:
              schema: {type: string}
              example: '"ord-101-v1"'
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
              example:
                id: ord-101
                status: DRAFT
                totalAmount: 250000
                version: 1
        "409":
          description: Xung đột nghiệp vụ

  /orders/{id}:
    parameters:
      - in: path
        name: id
        required: true
        schema: {type: string}
        example: ord-101
    get:
      summary: Đọc đơn và hỗ trợ tái xác nhận
      parameters:
        - in: header
          name: If-None-Match
          schema: {type: string}
          example: '"ord-101-v1"'
      responses:
        "200":
          description: Representation hiện tại
          headers:
            ETag:
              schema: {type: string}
              example: '"ord-101-v1"'
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
              example:
                id: ord-101
                status: DRAFT
                totalAmount: 250000
                version: 1
        "304":
          description: Validator khớp; không có response body
          headers:
            ETag:
              schema: {type: string}
              example: '"ord-101-v1"'
        "404":
          description: Đơn không tồn tại/không được công bố
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
    patch:
      summary: Đổi trạng thái có điều kiện
      parameters:
        - in: header
          name: If-Match
          required: true
          schema: {type: string}
          example: '"ord-101-v1"'
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
              required: [status]
              additionalProperties: false
              properties:
                status:
                  type: string
                  enum: [CONFIRMED, CANCELLED]
            example: {status: CONFIRMED}
      responses:
        "200":
          description: Đã cập nhật
          headers:
            ETag:
              schema: {type: string}
              example: '"ord-101-v2"'
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
              example:
                id: ord-101
                status: CONFIRMED
                totalAmount: 250000
                version: 2
        "409":
          description: Trạng thái nghiệp vụ xung đột
        "412":
          description: If-Match sai phiên bản
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
              examples:
                stale:
                  $ref: "#/components/examples/StaleOrder"
        "428":
          description: Thiếu If-Match bắt buộc
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"

components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    Order:
      type: object
      required: [id, status, totalAmount, version]
      properties:
        id: {type: string}
        status: {type: string, enum: [DRAFT, CONFIRMED, CANCELLED]}
        totalAmount: {type: integer, format: int64, minimum: 0}
        version: {type: integer, minimum: 1}
    OrderPage:
      type: object
      required: [items, page]
      properties:
        items:
          type: array
          items: {$ref: "#/components/schemas/Order"}
        page:
          type: object
          required: [limit, nextCursor, hasNext]
          properties:
            limit: {type: integer, minimum: 1, maximum: 100}
            nextCursor: {type: string, nullable: true}
            hasNext: {type: boolean}
    ApiProblem:
      type: object
      required: [type, title, status, code]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
        correlationId: {type: string}
  examples:
    EmptyPage:
      summary: Filter hợp lệ trả 0 đơn hàng
      value:
        items: []
        page: {limit: 20, nextCursor: null, hasNext: false}
    StaleOrder:
      summary: Cập nhật dựa trên ETag cũ
      value:
        type: https://api.example.test/problems/stale-order
        title: Precondition Failed
        status: 412
        code: STALE_ORDER
        detail: Đơn đã thay đổi, hãy GET lại trước khi sửa.
~~~

**Đọc ví dụ theo 4 trục:** **schema** giới hạn giá trị, **parameters** mô tả query và conditional headers, **responses** ràng buộc status/header/body, còn **security** công bố yêu cầu xác thực. Trong production cần mô tả đầy đủ 401/403/404/422/429, chính sách cache, Idempotency-Key và cách ánh xạ lỗi theo sản phẩm. Tài liệu hợp lệ về cú pháp chưa chứng minh runtime tuân thủ contract.

## 6. Đặt ví dụ lỗi đúng mã và đúng media type

**RFC 9457 Problem Details** chuẩn hóa các trường **type, title, status, detail, instance**. API có thể bổ sung **code, correlationId, violations** như extension members. Mẫu lỗi cần nhất quán với status thực tế, không đưa exception message hoặc stack trace vào response công khai.

Ví dụ client gửi **PATCH** dựa trên ETag cũ:

~~~http
PATCH /orders/ord-101 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "ord-101-v1"

{"status":"CONFIRMED"}
~~~

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store
X-Correlation-ID: 89035e18-e704-4e1c-8d84-4c3b8d409065

{
  "type":"https://api.example.test/problems/stale-order",
  "title":"Precondition Failed",
  "status":412,
  "detail":"Đơn đã thay đổi. Hãy GET lại trước khi sửa.",
  "code":"STALE_ORDER",
  "correlationId":"89035e18-e704-4e1c-8d84-4c3b8d409065"
}
~~~

| Mã | Khi nào dùng trong ví dụ | Ví dụ code ứng dụng |
|---|---|---|
| **400 Bad Request** | status filter không đúng enum, limit sai, cursor hỏng | INVALID_FILTER, INVALID_LIMIT |
| **401 Unauthorized** | Không có xác thực hợp lệ; phản hồi Bearer có WWW-Authenticate khi phù hợp | UNAUTHENTICATED |
| **403 Forbidden** | Caller đã xác thực nhưng không có quyền; có thể dùng 404 để che giấu sự tồn tại | FORBIDDEN |
| **404 Not Found** | Order resource không có/không được công bố; **không dùng cho collection rỗng** | ORDER_NOT_FOUND |
| **409 Conflict** | Không thể chuyển trạng thái theo quy tắc nghiệp vụ | INVALID_STATE_TRANSITION |
| **412 Precondition Failed** | If-Match có mặt nhưng không thỏa | STALE_ORDER |
| **422 Unprocessable Content** | Content có cú pháp hợp lệ nhưng giá trị vi phạm quy tắc đã công bố | INVALID_ORDER_AMOUNT |
| **428 Precondition Required** | Client bỏ qua If-Match bắt buộc của PATCH | IF_MATCH_REQUIRED |
| **429 Too Many Requests** | Rate limit; có thể có Retry-After | RATE_LIMITED |

**400, 409, 412, 422 không đồng nghĩa.** Ví dụ mang field **status: 412** trong body nhưng HTTP thực tế là 409 là mâu thuẫn. Tương tự, **type URI** phải ổn định theo loại vấn đề, không lạm dụng một type cho mọi lỗi chỉ để có một mẫu JSON duy nhất.

Đừng chỉ công bố **default: 500** và bỏ qua lỗi có thể dự báo. Khai báo các response 4xx quan trọng giúp SDK, client và contract test phân biệt xử lý đầu vào, phân quyền, xung đột và retry.

## 7. Yêu cầu có điều kiện: ví dụ status/header quan trọng hơn body

### 7.1. GET, If-None-Match và 304

Một GET bình thường trả representation và validator:

~~~http
GET /orders/ord-101 HTTP/1.1

HTTP/1.1 200 OK
ETag: "ord-101-v1"
Cache-Control: private, no-cache
Content-Type: application/json

{"id":"ord-101","status":"DRAFT","totalAmount":250000,"version":1}
~~~

Client có bản sao gửi **If-None-Match**. Nếu selected representation không thay đổi và điều kiện HTTP được đáp ứng, server trả:

~~~http
GET /orders/ord-101 HTTP/1.1
If-None-Match: "ord-101-v1"

HTTP/1.1 304 Not Modified
ETag: "ord-101-v1"
Cache-Control: private, no-cache
~~~

**304 không mang representation body**. Trong OpenAPI, hãy khai báo nó ở **responses."304"** với các header cần thiết, **không có content.application/json** hoặc ví dụ body **{}**. Client phải có bản sao phù hợp mới tái sử dụng được dữ liệu. Nếu representation đổi, server cần trả **200 với body mới và validator mới**.

### 7.2. PATCH, If-Match và 412

**If-Match** dùng **strong comparison**. Khi hai client cùng đọc ETag v1 rồi cùng PATCH trạng thái khác nhau, server phải bảo vệ việc so điều kiện và ghi tài nguyên **một cách nguyên tử** nếu hợp đồng nhằm chống lost update. Một request có thể thành công với ETag v2, request còn lại nhận **412**.

Đừng mô tả 412 như một **409 bất kỳ**. **409** dành cho xung đột nghiệp vụ, chẳng hạn muốn chuyển **CANCELLED → CONFIRMED** khi điều đó không được phép, ngay cả khi ETag hiện tại đúng. **428** diễn đạt việc endpoint đòi precondition nhưng client không gửi.

**Weak ETag** không thỏa If-Match theo strong comparison; **If-Match: \*** có ngữ nghĩa riêng (representation hiện tại tồn tại), không tự bỏ qua authorization. Một parser chỉ so chuỗi thô với một ETag không hỗ trợ đúng toàn bộ cú pháp header; dùng cơ chế HTTP có kiểm chứng, không tự đơn giản hóa logic production.

### 7.3. Ví dụ có điều kiện không thay thế quy tắc cập nhật tại DB

Nếu service chỉ:

~~~text
READ current version
if client ETag == current ETag:
    UPDATE row without version condition
~~~

thì hai transaction có thể cùng vượt kiểm tra và ghi đè nhau. Ở persistence cần **@Version, conditional UPDATE (compare-and-swap), locking hoặc cơ chế nguyên tử tương đương**. Contract test cần kiểm tra trạng thái cuối, không chỉ một response ví dụ trong OpenAPI.

### 7.4. 204 và 304 không phải “JSON rỗng”

Một endpoint **DELETE /orders/{id}** nếu hoàn thành và không trả body có thể quy định **204 No Content**. Khi đó response trong OpenAPI:

~~~yaml
responses:
  "204":
    description: Đã xóa thành công, không có response body
~~~

**Không thêm content.application/json.example: {}** cho response 204. Với **304**, cũng không được có response content; khác biệt là 304 phục vụ điều kiện tái xác nhận của request. **200 với items: []** mới là cách trả biểu diễn một collection hợp lệ nhưng không có phần tử.

## 8. Bảo mật, cache và dữ liệu mẫu trong tài liệu

OpenAPI cho biết API sử dụng **HTTP Bearer** nhưng khai báo security scheme **không tự bảo vệ server**; middleware/service vẫn phải xác thực token và kiểm tra quyền trên **mỗi resource/tenant**.

| Rủi ro hợp đồng | Cách xử lý |
|---|---|
| Copy token thật vào request example | Dùng placeholder, không nhúng Authorization secret vào specs |
| Mẫu response chứa email, đơn hàng hoặc ID thực | Dùng dữ liệu giả, tối thiểu; không xuất PII production |
| Trả 404 khác biệt làm lộ tài nguyên tenant khác | Định nghĩa chính sách 403/404 che giấu nhất quán |
| Cursor lộ tenant/ID hoặc cho chỉnh sửa | Token opaque, xác thực/kiểm scope, có expiry khi cần |
| Cached response cá nhân được shared giữa user | **private** hoặc **no-store** theo độ nhạy cảm; không chỉ dựa vào bearer token |
| 304 được trả trước authorization | Xác minh quyền trước khi cho reuse representation riêng tư |
| Problem Details phản chiếu input, SQL hoặc exception | Redact, code ổn định, detail an toàn |
| Ví dụ ETag chỉ dựa vào một trường nhưng body đổi theo quyền | Validator phải phản ánh selected representation và biến thể có liên quan |

Khi response thay đổi theo ngôn ngữ, biểu diễn hoặc encoding, cần xét **Vary** phù hợp; khi data phụ thuộc user/tenant, không thể chỉ đặt **Vary: Authorization** rồi coi như đã có phân quyền. Những ví dụ có **Cache-Control** phải tương thích với tính cá nhân hóa thực tế.

**Một ví dụ tốt cũng phải an toàn để sao chép:** API clients và tài liệu tương tác có thể tự động gửi payload mẫu; không chứa tài khoản production, đường dẫn nội bộ nhạy cảm, private key hay hành động gây side effect nguy hiểm nếu người học thử trên môi trường thật.

## 9. Java/Spring: status, validator và transaction phải khớp hợp đồng

Ví dụ Spring Framework 6+ minh họa hai nhánh **GET có điều kiện** và **PATCH bắt buộc If-Match**. Các kiểu **OrderService, OrderView, VersionedOrder** là abstraction của ứng dụng.

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable String id,
            Principal caller,
            WebRequest webRequest) {

        VersionedOrder order = service.findVisible(id, caller);
        String etag = order.strongEtag(); // Bao gồm dấu ngoặc kép.
        CacheControl cache = CacheControl.noCache().cachePrivate();

        if (webRequest.checkNotModified(etag)) {
            return ResponseEntity.status(304)
                .eTag(etag).cacheControl(cache).build();
        }
        return ResponseEntity.ok()
            .eTag(etag).cacheControl(cache).body(order.view());
    }

    @PatchMapping(
        path = "/{id}",
        consumes = "application/merge-patch+json"
    )
    ResponseEntity<OrderView> changeStatus(
            @PathVariable String id,
            @RequestHeader(name = "If-Match", required = false)
                String ifMatch,
            @RequestBody StatusPatch patch,
            Principal caller) {

        if (ifMatch == null || ifMatch.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.PRECONDITION_REQUIRED);
        }
        VersionedOrder updated =
            service.updateIfMatch(id, patch.status(), ifMatch, caller);
        return ResponseEntity.ok()
            .eTag(updated.strongEtag()).body(updated.view());
    }
}
~~~

Ví dụ cần imports Spring MVC/HTTP, Principal và các DTO/domain classes theo dự án. **Service phải xác minh quyền trước khi trả ETag**, kiểm tra If-Match bằng phép so khớp strong validator đúng cú pháp, và cập nhật nguyên tử bằng **@Version/conditional UPDATE**. Không đủ nếu chỉ so ETag trong controller rồi ghi không điều kiện. Với tạo đơn, endpoint POST nên dùng **ResponseEntity.created(location).eTag(etag).body(order)** để thực thi mẫu 201.

Khi version thay đổi, ánh xạ **StaleOrderException** sang **412** bằng **@RestControllerAdvice + ProblemDetail.forStatus(HttpStatus.PRECONDITION_FAILED)**, thêm **type/title/code** an toàn. Thiếu If-Match trả **428**; chuyển trạng thái không hợp lệ trả **409** theo contract. Không để handler tổng quát nuốt lỗi validation, auth hoặc framework thành một status tùy tiện. Triển khai Merge Patch phải xử lý rõ **field vắng mặt/null** và từ chối những field ngoài schema khi contract cấm.

## 10. Kiểm thử đối chiếu OpenAPI và phản hồi thực

Một tài liệu YAML parse được vẫn có thể chứa **example sai schema, $ref hỏng hoặc status/header không đúng runtime**. Kiểm tra theo ba lớp: **lint/validate OpenAPI**, **HTTP integration/MockMvc** và **contract tests** đối chiếu status, media type, header, schema với tài liệu.

Ví dụ các assertion MockMvc (giả định có **MockMvc mockMvc**, fixture và principal có quyền, đã cấu hình security/CSRF):
 
~~~java
// Filter hợp lệ nhưng không có đơn: vẫn 200 + items array.
mockMvc.perform(get("/orders")
        .with(user("alice"))
        .param("status", "CANCELLED"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.items", hasSize(0)))
    .andExpect(jsonPath("$.page.hasNext").value(false));

// GET cung cấp ETag, request có điều kiện nhận 304 không body.
MvcResult first = mockMvc.perform(
        get("/orders/{id}", id).with(user("alice")))
    .andExpect(status().isOk())
    .andExpect(header().exists("ETag"))
    .andReturn();
String etag = first.getResponse().getHeader("ETag");
mockMvc.perform(get("/orders/{id}", id)
        .with(user("alice"))
        .header("If-None-Match", etag))
    .andExpect(status().isNotModified())
    .andExpect(content().string(""));

// PATCH thiếu điều kiện: 428, dữ liệu không thay đổi.
mockMvc.perform(patch("/orders/{id}", id)
        .with(user("alice")).with(csrf())
        .contentType("application/merge-patch+json")
        .content("{\"status\":\"CONFIRMED\"}"))
    .andExpect(status().is(428));
~~~

Các static imports của MockMvc, Hamcrest, Security Test và kiểu MvcResult cần được thêm trong class test thực; **@WithMockUser/user() không thay thế kiểm thử Bearer token thật qua gateway**. Thêm test POST trả **201 + Location + ETag**, PATCH với ETag hiện tại trả 200, sau đó PATCH lại bằng ETag cũ trả **412** và không thay dữ liệu. Với concurrency thực, gửi hai PATCH cùng ETag trên DB thật và xác nhận tối đa một cập nhật thành công.

| Nhóm test | Bằng chứng cần có |
|---|---|
| **Examples vs schema** | empty.nextCursor là null phải được schema cho phép; enum/required đúng |
| **HTTP status/header** | 201 có Location; 304 không body; 412/428 đúng điều kiện |
| **Pagination** | Trang còn tiếp có nextCursor; trang rỗng items: [] và hasNext=false |
| **Security** | Tenant khác không đọc được body, ETag hoặc response cache riêng |
| **Problem Details** | HTTP status khớp field status; code đúng và detail không lộ secret |
| **Drift** | Đổi field/enum/status trong server khiến contract test fail |

**Đừng chỉ chụp snapshot JSON:** assert mã HTTP, header, Content-Type và trạng thái dữ liệu cuối. Ví dụ giúp người đọc hiểu API; contract test giúp phát hiện ví dụ không còn đúng khi phần mềm thay đổi.

## 11. Bài thực hành: hoàn thiện ví dụ cho API sản phẩm

Một API khác cung cấp:

~~~text
GET   /products?category=stationery&limit=10&cursor=...
GET   /products/{id}
PATCH /products/{id}
~~~

**Hợp đồng:** danh sách chỉ chứa sản phẩm caller được phép xem; trả 200 với **items/page** dù không có dữ liệu; GET một sản phẩm trả strong ETag; PATCH thay giá bắt buộc If-Match. Lỗi dùng **application/problem+json** với code ổn định.

**Nhiệm vụ:**

1. Viết hai **examples** cho response 200 của GET collection: một trang còn tiếp, một trang không có item. Đặt chúng dưới đúng media type.
2. Mô tả query limit (**integer 1–50**), cursor và thông điệp lỗi **400 INVALID_CURSOR**.
3. Viết ví dụ **GET 200 + ETag**, **GET 304 không body**, **PATCH 412 STALE_PRODUCT** và **PATCH 428 IF_MATCH_REQUIRED**.
4. Đề xuất một test xác minh PATCH stale **không ghi đè giá**, một test chống rò sản phẩm giữa tenant và một test chứng minh trang rỗng **không phải 404**.
5. Phát hiện lỗi trong mô tả sau: response **304** có body **{}**; response **412** có body status **409**; collection empty có **items: null** trong khi schema định nghĩa array không nullable.

**Gợi ý đáp án:** Các ví dụ của GET collection đặt ở **responses."200".content.application/json.examples** và dùng chung schema có **items: array**. Với filter hợp lệ, trang rỗng trả 200 và **items: []**. GET có ETag khớp If-None-Match có thể trả 304 **không có content**; PATCH với If-Match cũ phải 412, thiếu điều kiện bắt buộc là 428. Ba lỗi ở câu 5 đều vi phạm ngữ nghĩa HTTP hoặc schema; test phải thất bại để buộc sửa docs hay runtime.

## 12. Checklist và nguồn tham khảo

- [ ] Mỗi example nằm đúng **operation, response status, media type** và khớp schema (type, enum, required, nullable).
- [ ] Phân biệt **example** và **examples**, tái sử dụng bằng **components.examples** khi hữu ích; không nhầm $ref schema với $ref example.
- [ ] 200 có trang rỗng và trang có dữ liệu dùng chung schema; cursor, limit, filter có hợp đồng cụ thể.
- [ ] 201 có Location khi tạo resource; 204/304 không gửi body mẫu; 200/304 có ETag đúng biểu diễn.
- [ ] PATCH có If-Match, 412 và 428 rõ ràng; backend dùng kiểm tra phiên bản nguyên tử.
- [ ] 4xx/5xx có Problem Details an toàn, status trong body phù hợp HTTP status.
- [ ] Security, tenant isolation, Cache-Control, metadata phân trang và ví dụ không dùng dữ liệu thật/secret.
- [ ] OpenAPI được lint/validate; MockMvc/HTTP integration và contract tests kiểm status, header, body và trạng thái cuối.

Nguồn đối chiếu: [OpenAPI Specification 3.0.3](https://spec.openapis.org/oas/v3.0.3.html) — Example, Media Type, Parameter, Header và Response Objects; [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — conditional requests và status; [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457); [Spring MVC — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html).

**Ghi nhớ:** Ví dụ OpenAPI tốt là những **hợp đồng HTTP có thể kiểm chứng**: thành công và rỗng dùng schema nhất quán, lỗi có cấu trúc, pagination có metadata, conditional requests có validator/status đúng; Java/Spring và kiểm thử phải thực thi đúng những gì tài liệu công bố.

