# Hoàn thiện tài liệu, dashboard, runbook và kế hoạch tiến hóa

Một REST API **chạy được** chưa chắc đã **sẵn sàng bàn giao và vận hành**. Khi đội frontend muốn tích hợp, họ cần biết hợp đồng request/response, phân trang, cách retry và ý nghĩa lỗi. Khi p95 tăng mạnh, trực vận hành cần dashboard và alert để khoanh vùng. Khi database không đáp ứng hoặc khóa JWT vừa luân chuyển, đội on-call cần runbook có thể hành động, chứ không phải hỏi tác giả code. Khi chuẩn bị đổi schema hoặc loại bỏ endpoint cũ, đội phát triển cần kế hoạch tiến hóa để không làm hỏng client đang sử dụng.

Đây là **bài thực hành tổng hợp** của module `INTEGRATION_API_REST`: thiết kế REST API dựa trên resource, URI, HTTP method/status, phân trang, cache, idempotency, OpenAPI, xác thực/phân quyền, xử lý lỗi và kiểm thử trong Java/Spring hoặc công nghệ tương đương. Bạn sẽ lấy một API đã phát triển và hoàn thiện **bốn sản phẩm vận hành gắn kết**: tài liệu cho người tích hợp, dashboard quan sát, runbook ứng cứu và kế hoạch thay đổi API an toàn.

> **Tiêu chí thành công:** Một người không viết API vẫn có thể đọc tài liệu để gọi đúng; một người trực vận hành không biết code chi tiết vẫn có thể phân loại sự cố; và một client cũ không bị ngắt đột ngột khi API được nâng cấp.

Các tên service, URL, dữ liệu và mục tiêu SLO trong bài là **giả định để thực hành**, không phải mô tả một hệ thống thực tế hay chỉ tiêu áp dụng cho mọi sản phẩm. Bạn có thể thay Java/Spring bằng công nghệ tương đương nếu vẫn chứng minh được cùng hợp đồng và bằng chứng kiểm thử.

## 1. Đề bài và bối cảnh hệ thống

### 1.1. Hệ thống giả định: Commerce Orders API

Bạn tham gia nhóm phụ trách `orders-api`. Service chạy nhiều instance sau API Gateway, sử dụng PostgreSQL lưu dữ liệu giao dịch, Redis tùy chọn cho caching/rate limit và message broker xử lý bước fulfillment bất đồng bộ. Service gọi `inventory-api` và `payment-api` qua HTTP.

~~~mermaid
flowchart LR
    Client[Web / Mobile / Partner] --> GW[API Gateway]
    GW --> ORD[orders-api / Spring Boot]
    ORD --> DB[(PostgreSQL)]
    ORD --> CACHE[(Redis optional)]
    ORD --> INV[inventory-api]
    ORD --> PAY[payment-api]
    ORD --> OUT[(Outbox table)]
    OUT --> PUB[Outbox publisher]
    PUB --> MQ[(Message broker)]
    MQ --> W[Fulfillment worker]
    GW -. request metrics .-> OBS[Metrics / logs / traces]
    ORD -. telemetry .-> OBS
    W -. telemetry .-> OBS
~~~

Hệ thống giả định có các endpoint:

| Resource/action | Phương thức và URI | Ý nghĩa |
| --- | --- | --- |
| Danh sách đơn | `GET /v1/orders?limit=20&after=...` | Danh sách có cursor, chỉ trả dữ liệu thuộc quyền |
| Chi tiết đơn | `GET /v1/orders/{id}` | Trả order và trạng thái đã lưu |
| Tạo đơn bất đồng bộ | `POST /v1/orders` | Nhận lệnh, trả `202 Accepted` và operation monitor |
| Theo dõi lệnh | `GET /v1/operations/{operationId}` | `PENDING`/`RUNNING`/`SUCCEEDED`/`FAILED` |
| Yêu cầu hủy đơn | `POST /v1/orders/{id}/cancellation-requests` | Tạo yêu cầu hủy theo policy nghiệp vụ |
| Readiness/liveness | `GET /readyz`, `GET /livez` | Phục vụ orchestrator, không thay API nghiệp vụ |

**Bất biến nghiệp vụ:** mỗi đơn thuộc một tenant; user chỉ đọc/sửa object có quyền; một `Idempotency-Key` không được làm tạo hai đơn; nếu worker đã thu tiền thành công rồi timeout, retry không được tự động thu lần nữa. Resource operation phải tồn tại đủ lâu để client tra cứu kết quả sau mất kết nối. `202` chỉ chứng minh việc đã **được chấp nhận bền vững**, không chứng minh việc đã hoàn tất.

### 1.2. Những vấn đề cần giải quyết

Trong phiên bản giả định hiện tại:

1. OpenAPI thiếu ví dụ lỗi, chưa thống nhất kiểu `date-time` và kiểu ID, không nói cursor có thời hạn bao lâu.
2. Frontend không rõ khi nào được retry POST: có nguy cơ tạo hai đơn hoặc thu tiền hai lần.
3. Dashboard chỉ có CPU, memory, số request; không hiển thị **tỷ lệ request thành công theo SLO**, p95/p99, lỗi của dependency, queue lag và số operation bị kẹt.
4. Khi `GET /v1/orders` trả 503, người trực không biết lỗi do gateway, connection pool, DB hay timeout downstream.
5. Một thay đổi dự kiến chuyển response list từ `page/size` sang cursor và bổ sung enum status mới; chưa có chính sách cho client cũ.

Bài tập không yêu cầu xây dựng lại toàn hệ thống. Bạn cần **bàn giao được artifact và bằng chứng** để người khác kiểm tra, triển khai và duy trì API an toàn.

## 2. Bốn đầu ra bắt buộc và Definition of Done

| Đầu ra | Tài liệu/sản phẩm cần có | Bằng chứng nghiệm thu |
| --- | --- | --- |
| **A. API documentation** | OpenAPI 3.1, Getting Started, authentication, pagination, errors, async/idempotency, cookbook, changelog | Lint/validate spec, contract tests, ví dụ `curl` chạy được |
| **B. Dashboard + alerts** | Dashboard theo RED/SLI, dependency/queue, panel theo version, alert theo error budget và triệu chứng | Ảnh/snapshot số liệu, đường truy vấn metrics, test alert và link tới traces |
| **C. Runbook** | Ít nhất 3 tình huống: 5xx/DB, 401/JWKS, backlog/202; phân loại, giảm thiểu, rollback, liên lạc | Một buổi tabletop/fault injection, log các quyết định và thời gian phục hồi |
| **D. Evolution plan** | Bảng tương thích, phương án version/deprecation, rollout/canary, migration/rollback và thông báo client | OpenAPI diff, thử client cũ, phương án phục hồi và checklist release |

**Definition of Done tối thiểu:** Người khác tái hiện được ít nhất một happy path và ba error paths từ tài liệu; dashboard phát hiện một lỗi được tiêm vào; runbook có bước thực thi và bước xác minh phục hồi; kế hoạch tiến hóa nêu được rủi ro breaking change và chứng minh client cũ còn hoạt động trong thời gian chuyển đổi.

Để tổ chức bài nộp, có thể dùng cấu trúc **gợi ý**, không bắt buộc phải tạo các file này trong bài học:

~~~text
submission/
  api/
    openapi.yaml
    getting-started.md
    conventions.md
    error-catalog.md
    changelog.md
  observability/
    dashboard.json
    alerts.yaml
    evidence.md
  operations/
    runbook-orders.md
    incident-exercise.md
  evolution/
    compatibility-matrix.md
    rollout-plan.md
    client-notice.md
  tests/
    contract-results.md
    resilience-results.md
~~~

Không tạo một bộ tài liệu chỉ chứa từ ngữ chung chung như “kiểm tra logs”, “theo dõi CPU” hay “đảm bảo backward-compatible”. Mỗi phần phải có **định nghĩa, người chịu trách nhiệm (theo vai trò), hành động cụ thể và điều kiện thành công/rollback**.

## 3. Đầu ra A — Hoàn thiện tài liệu để client tích hợp được

### 3.1. Trang Getting Started

Một người tích hợp mới cần đọc theo thứ tự:

1. **Base URL và environment:** ví dụ `https://api.example.com/v1`, staging và production dùng issuer/audience nào; không đưa token hoặc credentials thật vào tài liệu.
2. **Authentication:** OAuth 2.0 access token qua `Authorization: Bearer`, scope `orders.read`/`orders.write`; 401 khác 403; tránh dùng ID token thay access token.
3. **Request/response:** JSON, `Content-Type`/`Accept`, mã HTTP, cách lấy request ID/trace ID, UTC timestamp RFC 3339, identifier dạng string, số tiền theo minor units.
4. **Danh sách:** cursor opaque, `limit` mặc định 20 tối đa 100, thứ tự cố định `createdAt DESC, id DESC`, `nextCursor: null` khi hết.
5. **Mutation:** `Idempotency-Key` bắt buộc với POST tạo đơn; phạm vi tenant+operation, retry cùng payload; `202` trả monitor URI, cần polling có backoff.
6. **Errors:** Problem Details `application/problem+json` với `type`/`title`/`status`/`code`; `Retry-After` cho 429/503 khi server có hướng dẫn.
7. **Permissions & limits:** chỉ truy cập resource thuộc quyền, giới hạn trang, quota, có thể có CORS/CSRF theo cơ chế auth.

Ví dụ request tạo đơn:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 898cde2e-2f16-43ac-92c4-98d6634e7e00

{
  "items": [
    {"sku": "BOOK-42", "quantity": 2}
  ],
  "deliveryAddressId": "addr-12"
}
~~~

Khi server đã commit operation/outbox nhưng xử lý còn tiếp:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /v1/operations/op-603
Retry-After: 2
Cache-Control: no-store

{
  "id": "op-603",
  "state": "PENDING",
  "pollAfterSeconds": 2,
  "links": {"self": "/v1/operations/op-603"}
}
~~~

Khi worker hoàn tất:

~~~http
GET /v1/operations/op-603 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "op-603",
  "state": "SUCCEEDED",
  "result": {
    "resourceType": "order",
    "id": "ord-603",
    "url": "/v1/orders/ord-603"
  }
}
~~~

**Lưu ý quan trọng trong tài liệu:** GET operation trả `200` cả khi `state=FAILED`, vì `200` chỉ nói việc *đọc trạng thái* thành công; client **phải đọc `state`** để xác định kết quả nghiệp vụ. Trường hợp trả 202 bị mất trên mạng nhưng server đã commit, client có thể retry **cùng idempotency key và cùng nội dung** để tìm lại operation, không phát lệnh mới tùy tiện.

### 3.2. Bảng status/error code dành cho client

| HTTP | Tình huống | `code` ví dụ | Client nên làm |
| --- | --- | --- | --- |
| `400` | JSON hỏng hoặc tham số sai kiểu | `INVALID_JSON` | Sửa dữ liệu request |
| `401` | Access token thiếu/hết hạn/sai | `INVALID_ACCESS_TOKEN` | Lấy token đúng; retry có giới hạn |
| `403` | Thiếu scope hoặc quyền object | `INSUFFICIENT_SCOPE` | Không tự retry vô hạn; xin quyền phù hợp |
| `404` | Order không tồn tại hoặc bị giấu vì quyền | `RESOURCE_NOT_FOUND` | Không suy diễn tồn tại của object khác |
| `409` | Idempotency key cũ với payload khác; xung đột trạng thái | `IDEMPOTENCY_CONFLICT` | Không dùng lại key cho lệnh khác |
| `422` | Schema đọc được nhưng giá trị sai | `VALIDATION_FAILED` | Sửa field theo `violations` |
| `429` | Vượt quota/throttle | `RATE_LIMITED` | Chờ `Retry-After` và jitter, không retry storm |
| `503` | Service/dependency tạm không khả dụng | `DEPENDENCY_UNAVAILABLE` | Retry có hạn, tuân thủ idempotency |

Ví dụ lỗi dạng RFC 9457:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 422,
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "items[0].quantity",
      "code": "OUT_OF_RANGE",
      "message": "Số lượng phải lớn hơn 0."
    }
  ]
}
~~~

Thống nhất `status` của body với **HTTP response**, nhưng nhớ `code` và `violations` là extension của API. Thông điệp không được chứa bearer token, raw SQL/stack trace, thông tin tenant hay dữ liệu khác người gọi không được xem. Với 401 Bearer cần `WWW-Authenticate` challenge, dù đã trả Problem Details JSON.

### 3.3. OpenAPI 3.1: đoạn hợp đồng có thể kiểm tra

Đây là **một đoạn OpenAPI self-contained thu gọn**, đủ để minh họa `POST`, operation monitor, security, schemas và lỗi chính. Bài nộp đầy đủ phải khai báo thêm `GET /v1/orders`, `GET /v1/orders/{id}`, các response và test đối chiếu với implementation.

~~~yaml
openapi: 3.1.0
info:
  title: Commerce Orders API
  version: 1.0.0
servers:
  - url: https://api.example.com
security:
  - bearerAuth: []
paths:
  /v1/orders:
    post:
      operationId: createOrder
      summary: Tiếp nhận lệnh tạo đơn bất đồng bộ
      description: |
        Yêu cầu Idempotency-Key cho mỗi logical command.
        Trả 202 sau khi đã lưu operation và outbox bền vững.
        Không cam kết đơn hàng đã được xác nhận.
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema:
            type: string
            minLength: 8
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '202':
          description: Đã nhận tác vụ, chưa hoàn tất
          headers:
            Location:
              description: URI tới operation monitor
              schema: {type: string}
            Retry-After:
              description: Gợi ý số giây trước lần polling tiếp
              schema: {type: string}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
        '409':
          description: Idempotency conflict hoặc conflict nghiệp vụ
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '422':
          description: Dữ liệu không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
  /v1/operations/{operationId}:
    get:
      operationId: getOperation
      summary: Đọc tiến độ lệnh
      parameters:
        - name: operationId
          in: path
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Resource operation tồn tại và thuộc quyền xem
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
        '404':
          description: Không tồn tại hoặc không thuộc phạm vi được xem
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
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
      required: [items, deliveryAddressId]
      properties:
        items:
          type: array
          minItems: 1
          maxItems: 100
          items:
            type: object
            additionalProperties: false
            required: [sku, quantity]
            properties:
              sku: {type: string, minLength: 1, maxLength: 64}
              quantity: {type: integer, minimum: 1, maximum: 1000}
        deliveryAddressId: {type: string, minLength: 1}
    Operation:
      type: object
      required: [id, state]
      properties:
        id: {type: string}
        state:
          type: string
          enum: [PENDING, RUNNING, RETRYING, SUCCEEDED, FAILED]
        pollAfterSeconds: {type: integer, minimum: 1}
        result:
          type: object
          properties:
            resourceType: {type: string}
            id: {type: string}
            url: {type: string}
        links:
          type: object
          properties:
            self: {type: string}
    ApiProblem:
      type: object
      required: [type, title, status]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
~~~

Trong OpenAPI ở trên, `type: http` / `scheme: bearer` mô tả cơ chế Bearer ở tầng HTTP; **không tự kiểm JWT issuer, audience hoặc scope**. Resource server phải kiểm chữ ký/claims và policy; bài nộp hoàn chỉnh cần mô tả scope qua tài liệu và/hoặc một security scheme OAuth2 phù hợp với flow thực tế. Với `Operation.result` chỉ xuất hiện khi thành công, tài liệu cần nói rõ quan hệ `state`–`result`–`error`. Đoạn self-contained cố tình chưa mô tả toàn bộ error cases nên **không được xem là OpenAPI production hoàn chỉnh**.

### 3.4. Quy ước kỹ thuật phải ghi ngoài schema

Đối với danh sách, chọn một contract rõ:

~~~http
GET /v1/orders?limit=20&status=CONFIRMED HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~json
{
  "data": [
    {
      "id": "ord-603",
      "createdAt": "2026-11-18T09:15:30.123Z",
      "status": "CONFIRMED",
      "totalMinorUnits": 350000,
      "currency": "VND"
    }
  ],
  "hasNext": false,
  "nextCursor": null
}
~~~

- **Pagination:** `limit` mặc định 20, tối đa 100; `after` là token opaque có kiểm tra toàn vẹn, ràng buộc tenant/filter/sort, không được client tự chỉnh. Trang cuối trả `data: []` nếu không có item và `nextCursor: null`, không dùng HTTP 404 cho trang rỗng.
- **Sort:** `createdAt DESC, id DESC` với tie-breaker ổn định. Cursor không tự đảm bảo snapshot khi dữ liệu đổi; mô tả rõ eventual consistency/điều kiện lọc.
- **Thời gian:** `createdAt` là chuỗi RFC 3339 UTC với `Z` và precision millisecond; `deliveryDate` là ngày lịch `YYYY-MM-DD`, không tự diễn giải thành 00:00 UTC.
- **Số:** identifier là string kể cả DB dùng BIGINT; tiền dùng `totalMinorUnits` theo mã `currency`, quy định range và giới hạn an toàn cho JavaScript; không dùng `double` cho arithmetic tiền.
- **Null/missing:** field `note: null` nghĩa không có ghi chú nếu schema yêu cầu field nullable. Với `PATCH application/merge-patch+json`, *không có key* nghĩa giữ nguyên; key `null` nghĩa xóa member theo RFC 7396. Phân biệt với JSON Patch và PUT.
- **Concurrency:** `ETag`/`If-Match` và `412 Precondition Failed` ở những update cần tránh lost update; API đọc cache cần cam kết phù hợp về dữ liệu cũ.
- **Retry:** 429/503 có `Retry-After` khi hữu ích, client có backoff+jitter, retry budget và idempotency; 202 không có nghĩa tự retry POST ngay.

### 3.5. Hướng dẫn CLI cho người tích hợp

Mẫu `curl` dùng **token thử nghiệm** qua biến môi trường, không đặt token thật vào tài liệu:

~~~bash
# ACCESS_TOKEN là token test hợp lệ được cấp qua secret manager.
curl --fail-with-body -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "https://api.example.com/v1/orders?limit=20"

curl -i -X POST "https://api.example.com/v1/orders" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-order-603-v1" \
  -d '{"items":[{"sku":"BOOK-42","quantity":2}],"deliveryAddressId":"addr-12"}'
~~~

Đoạn mẫu chỉ hoạt động khi API test, quyền và dữ liệu giả định đã được chuẩn bị; **không thực thi POST trên production nếu không được phép tạo đơn thật**. Đừng bảo người tích hợp dùng `curl -v` rồi dán toàn bộ output chứa Authorization header vào issue công khai. Ví dụ nên có request/response kỳ vọng, lỗi thường gặp và cách xác nhận trạng thái operation.

### 3.6. Kiểm thử tài liệu, không chỉ “đọc thấy đúng”

Bài nộp phải có các loại kiểm tra:

1. **Syntax/lint:** OpenAPI hợp lệ, `$ref` resolve được, không trùng `operationId`, schema/response status nhất quán.
2. **Contract:** lấy ví dụ request/response từ docs để validate schema; 202 thực có `Location` và body operation; `application/problem+json` có status trùng HTTP.
3. **Security:** 401 thiếu token, 403 thiếu scope, truy cập chéo tenant bị 403/404, không rò owner/token.
4. **Async:** POST trùng key cùng payload không tạo hai đơn, cùng key khác payload trả 409, worker lỗi làm operation chuyển state rõ.
5. **Usability:** một người khác dùng Getting Started gọi được API test mà không hỏi tác giả; ghi chỗ nào khiến họ phải suy đoán.

Không được xem một file OpenAPI hợp cú pháp là đủ. **Implementation và gateway** phải trả đúng HTTP, content type, CORS, auth và schema đã công bố. Mọi khác biệt phát hiện được phải sửa code hoặc sửa tài liệu theo hành vi **được chủ đích phê duyệt**, không “chỉnh docs cho khớp bug” một cách mù quáng.

## 4. Đầu ra B — Dashboard chứng minh được chất lượng phục vụ

Một dashboard chỉ hiện CPU, memory và tổng số `200` không đủ để điều tra API. Trước hết chọn câu hỏi sản phẩm cần trả lời, rồi tìm **SLI (Service Level Indicator)** và chỉ số hỗ trợ tương ứng. Dashboard nên đi từ ảnh hưởng tới client xuống dependency, không bắt người trực mở 12 trang để xác định có đang xảy ra sự cố hay không.

### 4.1. Định nghĩa SLI/SLO trước khi tạo biểu đồ

Ví dụ **SLO minh họa** cho `GET /v1/orders`:

| SLI/SLO | Mô tả | Mục tiêu minh họa |
| --- | --- | --- |
| **Availability SLI** | Tỷ lệ request **đủ điều kiện** được phục vụ thành công theo chính sách | 99,9% trên cửa sổ 30 ngày |
| **Latency SLI** | Tỷ lệ GET đủ điều kiện hoàn tất trong 500 ms, đo ở ingress/gateway hoặc server theo quy tắc cố định | 99% trên 30 ngày |
| **Correctness** | Response đúng tenant/schema và không tạo hai order cho cùng logical command | Không chấp nhận sự cố vi phạm bất biến |
| **Async completion** | Tỷ lệ operation đã accepted và đạt terminal state trong 60 giây | 99% trên 30 ngày |
| **Read projection** | Độ trễ từ event commit tới projection sẵn sàng | p99 dưới ngưỡng đã chọn và theo dõi riêng |

**Không gộp tùy tiện các SLI vào một tỷ lệ duy nhất.** Availability của HTTP GET khác tỷ lệ operation hoàn tất: một API có thể liên tục trả 202 hợp lệ nhưng worker không xử lý. Một số sai phạm như truy cập trái phép hoặc thu tiền hai lần có **mức độ nghiêm trọng cao** dù xảy ra rất ít; chỉ nhìn SLO trung bình sẽ che khuất chúng.

Định nghĩa **request đủ điều kiện** phải ghi trong tài liệu dashboard và test của metric:

- Response 2xx/3xx hợp lệ được tính là `good` nếu đáp ứng điều kiện đã công bố.
- 5xx do hệ thống và 503/504 ở gateway phải được tính là `bad`; không chỉ đo trong application vì có thể request chưa tới pod.
- 4xx do client sai input/quyền (ví dụ 400/401/403/404) thường **không đưa vào mẫu availability** hoặc được phân loại riêng. Tuy nhiên 429 vì hệ thống không đủ capacity/quota có thể cần tính là bad hoặc có SLI riêng tùy cam kết sản phẩm. **Đừng loại 429 một cách tự động để làm đẹp SLO.**
- Request bị client hủy, readiness probe và traffic nội bộ cũng phải có quy tắc rõ; không trộn probe vào user SLI.
- Nếu route không có traffic trong một cửa sổ, kết quả là **không đủ dữ liệu**, không phải tự động 100% hoặc 0% khả dụng.

Với SLO availability 99,9% trong 30 ngày, error budget tương đương **0,1% của tổng request đủ điều kiện**. Nếu request đến với nhịp ổn định, phần tương đương theo thời gian là khoảng **43 phút 12 giây** trong 30 ngày; phép đổi thời gian chỉ để trực giác, vì error budget thực tế của SLI dựa trên **số request** khi định nghĩa theo request. Lúc traffic tăng mạnh, tiêu hao budget theo request có thể nhanh hơn cách hình dung bằng phút.

### 4.2. Bố cục dashboard cần có

<table>
<tr><th>Hàng/panel</th><th>Câu hỏi</th><th>Dữ liệu cần có</th></tr>
<tr><td>**Tình trạng khách hàng**</td><td>API đang khỏe hay vi phạm SLO?</td><td>Traffic, availability, 5xx/429, latency p50/p95/p99, error budget remaining</td></tr>
<tr><td>**Theo route và release**</td><td>Chỉ một endpoint hoặc version mới bị lỗi?</td><td>Route template, method, status class, deployment version/zone</td></tr>
<tr><td>**Dependencies**</td><td>Chậm ở app, DB hay downstream?</td><td>HTTP client duration/error, DB pool active/pending/timeouts, query latency, retry/circuit breaker</td></tr>
<tr><td>**Async workflow**</td><td>202 accepted có thực sự tiến tới kết quả cuối?</td><td>Operations pending/running/stuck, completion latency, outbox age, queue lag, DLQ, retry attempts</td></tr>
<tr><td>**Hạ tầng/triển khai**</td><td>Có mất capacity hoặc rollout lỗi không?</td><td>Ready pods, restarts, CPU/heap/GC, thread pool, version, canary vs baseline</td></tr>
<tr><td>**Điều tra sâu**</td><td>Trace/log nào giải thích p99?</td><td>Trace exemplars, request/trace ID, sampled error/slow traces, liên kết runbook</td></tr>
</table>

**Chú ý cardinality:** label nên là `http.route=/v1/orders/{id}`, không phải đường dẫn chứa order ID. Không dùng email, access token, idempotency key, customer ID hoặc trace ID làm metric label. Trace ID có thể dùng trong log/tracing với quyền truy cập phù hợp.

### 4.3. Cách đo với Spring Boot và Micrometer

Với Spring Boot Actuator, HTTP server metrics thường xuất phát từ meter `http.server.requests`; khi xuất tới Prometheus, tên series/phân loại tag và histogram phụ thuộc phiên bản Spring/Micrometer/registry. Cần **kiểm tra metrics thực tế đã scrape**, không copy PromQL rồi giả định luôn có series đúng tên.

Ví dụ bật histogram cho HTTP server request khi phiên bản và exporter hỗ trợ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
    tags:
      application: orders-api
~~~

`/actuator/prometheus` chỉ nên để Prometheus nội bộ scrape, **không công khai Internet**. Spring/Micrometer có thể dùng label `uri` cho route template hoặc tên metric khác tùy registry. Nếu chọn OpenTelemetry semantic conventions, metric `http.server.request.duration` có tên/đơn vị khác khi export; cần mapping dashboard rõ ràng và test dashboard sau upgrade instrumentation.

**PromQL minh họa** cho Micrometer Prometheus với histogram `http_server_requests_seconds_bucket` và label `uri`:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      application="orders-api",
      uri="/v1/orders"
    }[5m])
  )
)
~~~

Nếu series có unit giây, ngưỡng 500 ms là `0.5`, không phải `500`. `histogram_quantile` trên histogram tổng hợp cần bucket boundaries giống nhau; kết quả là ước lượng tùy bucket. **Không tính p95 bằng cách trung bình cộng p95 của từng pod**, vì trung bình percentile không tương đương percentile toàn bộ request.

Ví dụ error rate 5xx theo route:

~~~promql
sum(rate(http_server_requests_seconds_count{
  application="orders-api", uri="/v1/orders", status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    application="orders-api", uri="/v1/orders"
  }[5m])),
  0.000001
)
~~~

Đây là **tỷ lệ 5xx trong toàn bộ traffic của route**, **không tự động là availability SLI đã định nghĩa**, vì mẫu số còn bao gồm các 4xx cần phân loại. Có thể dùng panel này để chẩn đoán nhưng không được đổi tên thành “SLO availability” nếu chưa triển khai cùng eligibility policy.

### 4.4. Metric SLI tường minh thay cho suy đoán từ status

Một cách dễ audit là phát custom counter từ gateway/ứng dụng với hai nhãn boolean cardinality thấp:

~~~text
api_sli_requests_total{
  service="orders-api",
  route="/v1/orders",
  eligible="true",
  good="true"
}

api_sli_requests_total{
  service="orders-api",
  route="/v1/orders",
  eligible="true",
  good="false"
}
~~~

**Đây là metric ứng dụng cần tự triển khai**, không phải metric có sẵn của Spring. Việc phân loại nên diễn ra trên một nguồn quan sát có thể thấy lỗi ingress/gateway, không chỉ request đi vào controller; nếu cần tổng hợp nhiều nguồn, phải chống **đếm trùng** một request ở gateway và app. Quy tắc `eligible/good` nên được kiểm thử như một phần contract vận hành.

Tỷ lệ phục vụ tốt theo năm phút:

~~~promql
sum(rate(api_sli_requests_total{
  service="orders-api", route="/v1/orders",
  eligible="true", good="true"
}[5m]))
/
clamp_min(
  sum(rate(api_sli_requests_total{
    service="orders-api", route="/v1/orders",
    eligible="true"
  }[5m])),
  0.000001
)
~~~

Với không có traffic, `clamp_min` giúp tránh chia 0 trong biểu thức nhưng **không được xem kết quả bằng 0 là outage**; dashboard/alert phải thêm logic kiểm tra số lượng request hoặc đánh dấu no data. Để tính SLO rolling 30 ngày, cần data retention và recording rules phù hợp; không dùng vài điểm trong đồ thị 5 phút làm giá trị 30 ngày.

### 4.5. Alert trên triệu chứng và error budget, không chỉ CPU

Một số alert ví dụ cần có runbook:

| Alert | Điều kiện gợi ý | Hành động |
| --- | --- | --- |
| **High error budget burn** | Tốc độ tiêu hao budget cao ở cả cửa sổ ngắn và dài, có đủ traffic | Page on-call, mở dashboard/trace |
| **Latency SLO breach** | Tỷ lệ GET trên 500 ms vượt budget latency | Kiểm DB/pool/downstream và release |
| **No healthy endpoints** | Ready pods giảm về 0 | Kiểm readiness/rollout/DB dependency |
| **Queue age high** | Tuổi event cũ nhất vượt ngưỡng dù API còn nhận 202 | Kiểm consumer/DLQ/outbox publisher |
| **Operations stuck** | Nhiều operation PENDING/RUNNING vượt deadline | Reconcile, retry budget và workflow state |
| **JWT validation errors spike** | 401 invalid_token tăng theo vùng hoặc key rotation | Kiểm issuer/JWKS/audience/clock |
| **Rate-limit spike** | 429 tăng cùng traffic/retry | Kiểm quota, retry storm, client rollout |

Với SLO availability 99,9%, **burn rate** bằng tỷ lệ bad/eligible chia cho `0.001`. Một cảnh báo kiểu multi-window có thể yêu cầu burn rate lớn hơn **14,4 lần** ở cả cửa sổ 1 giờ và 5 phút, kết hợp điều kiện số request tối thiểu. Đây là **ví dụ chính sách SRE**, phải điều chỉnh theo sản phẩm, traffic, routing và mức báo động chấp nhận được.

Ví dụ recording rule giả định phát sẵn tỷ lệ `api_sli_error_ratio_1h` và `api_sli_error_ratio_5m` theo đúng eligibility policy:

~~~yaml
groups:
  - name: orders-api-slo
    rules:
      - alert: OrdersAvailabilityFastBurn
        expr: |
          (api_sli_error_ratio_1h{service="orders-api"} / 0.001 > 14.4)
          and
          (api_sli_error_ratio_5m{service="orders-api"} / 0.001 > 14.4)
          and
          (api_sli_eligible_requests_5m{service="orders-api"} >= 100)
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "Orders API đang tiêu hao error budget nhanh"
          runbook: "https://docs.example.com/runbooks/orders-api"
~~~

**Cảnh báo trên chỉ là cấu hình mô hình**: ba recording series `api_sli_error_ratio_1h`, `api_sli_error_ratio_5m`, `api_sli_eligible_requests_5m` **phải được định nghĩa và phát/ghi rule trước**. Nếu không, alert không hoạt động. Tất cả phép tính và label phải khớp SLI thực của hệ thống. Đừng dựng alert chỉ dựa vào container CPU vượt 80% trong 2 phút rồi gọi đó là “API outage”.

### 4.6. Bài nộp dashboard phải trả lời được một tình huống

Đặt giả thuyết: một release mới làm p95 `POST /v1/orders` tăng từ 250 ms lên 1,2 giây. Người trực phải trả lời được bằng dashboard:

1. Traffic có tăng không, hay chỉ p95 tăng sau thời điểm deploy?
2. 5xx/429 tăng hay không? Error budget còn bao nhiêu?
3. Chỉ canary version mới bị ảnh hưởng, hay cả phiên bản cũ?
4. HTTP server span chậm, HTTP client tới Inventory chậm, DB query chậm hay **chờ connection pool**?
5. Operation accepted có đi đến terminal state đúng hạn không, hay queue age tăng?
6. Có thể dẫn từ một điểm latency bất thường tới trace/log tương ứng không?

**Bằng chứng bắt buộc:** lưu ảnh hoặc export dashboard, URL/truy vấn panels, định nghĩa meter và labels, một trace được chọn, dữ liệu trước/sau sự cố và giải thích kết luận. Nếu không có hạ tầng monitoring, có thể dùng dữ liệu giả lập **được ghi rõ là mô phỏng**, cùng truy vấn và phép tính; không công bố số giả là kết quả benchmark thật.

## 5. Đầu ra C — Runbook: từ cảnh báo đến phục hồi

**Runbook** là một thủ tục vận hành có điều kiện, không phải danh sách lệnh vô ngữ cảnh. Người trực cần biết **triệu chứng nào kích hoạt**, **điều gì không được làm**, **bằng chứng nào xác minh nguyên nhân**, **biện pháp giảm tác động nào được phép** và **khi nào cần rollback/escalate**. Các câu trả lời phải liên kết trực tiếp tới dashboard và tài liệu API.

### 5.1. Khuôn mẫu runbook tối thiểu

~~~text
Runbook ID: ORD-API-001
Service: orders-api
Owner: <tên đội/vai trò>
On-call: <nguồn trực/rotation; không hardcode số cá nhân>
Severity criteria: <định nghĩa SEV1/SEV2/SEV3>
Last verified: <ngày chạy thử gần nhất>
Links: <dashboard> / <trace search> / <deploy> / <API docs>

Trigger:
  - Alert / điều kiện / cửa sổ thời gian
  - SLI hoặc hành vi khách hàng bị ảnh hưởng

First 5 minutes:
  - Xác minh alert có đủ traffic, không phải telemetry mất
  - Xác định region, version, route và status
  - Phân biệt ingress/gateway với application/downstream
  - Quyết định mức độ khẩn cấp và người phối hợp

Diagnosis:
  - Giả thuyết A → lệnh/truy vấn kiểm chứng → cách đọc kết quả
  - Giả thuyết B → lệnh/truy vấn kiểm chứng → cách đọc kết quả

Mitigation:
  - Biện pháp ít rủi ro nhất được phép
  - Điều kiện tiên quyết, ảnh hưởng, người phê duyệt nếu cần
  - Lựa chọn rollback / failover / degrade

Verification:
  - Request/SLI/queue/trace phục hồi như thế nào?
  - Đã dừng được tác dụng phụ hay chỉ che lỗi HTTP?

Communication and follow-up:
  - Cập nhật nội bộ/khách hàng theo phạm vi
  - Timeline, nguyên nhân có bằng chứng, action items, test chống tái diễn
~~~

Không đặt password, khóa JWT, nội dung personal data hoặc câu lệnh thay đổi database không được rà soát vào runbook công khai. Link tới secret manager, dashboard và công cụ sự cố phải có **phân quyền** riêng.

### 5.2. Runbook A: 503/504 hoặc p95 cao khi PostgreSQL/pool gặp vấn đề

**Trigger minh họa:** trong 5 phút, tỷ lệ 5xx của `GET /v1/orders` tăng mạnh; đồng thời `db.connection.pending`/pool timeout tăng hoặc p95 vượt SLO. Gateway có thể trả 503 khi không có pod ready; app cũng có thể trả 503 khi DB connection không lấy được. Đừng giả định tất cả 503 là DB.

**Bước 1 — Xác nhận phạm vi và nguồn lỗi.**

~~~bash
# Lệnh chỉ đọc, dùng namespace và tên service minh họa.
kubectl -n commerce get deploy orders-api
kubectl -n commerce get pods -l app=orders-api -o wide
kubectl -n commerce get endpointslices -l kubernetes.io/service-name=orders-api
kubectl -n commerce rollout status deploy/orders-api

# Chỉ lấy log theo thời gian, che secrets theo quyền vận hành.
kubectl -n commerce logs deploy/orders-api --since=10m --tail=200
~~~

Các lệnh này **phải chạy trên cluster được cấp quyền**; tên namespace, label, deployment là ví dụ. Không dùng `kubectl logs` để xuất dữ liệu khách hàng/token vào kênh chia sẻ không an toàn. Nếu Service không có endpoint, ưu tiên kiểm readiness, rollout và selector trước khi đổ lỗi DB.

**Bước 2 — Đối chiếu metrics và trace.**

| Bằng chứng | Cách đọc | Giả thuyết |
| --- | --- | --- |
| Ready pods từ 3 xuống 0 | Gateway thiếu upstream, `/readyz` trả 503 | Readiness policy hoặc rollout lỗi |
| Pool pending-acquire và timeout tăng | App chờ connection trước khi query | Pool exhaustion/leak/slow query |
| SQL execution time/lock wait tăng | DB bận hoặc transaction giữ khóa | Query plan, contention, migration |
| HTTP client Inventory chậm | DB Orders có thể không phải nguồn | Dependency/HTTP pool/retry |
| Chỉ version mới có 5xx | Cấu hình/query mới làm hỏng | Canary rollback candidate |

**Bước 3 — Biện pháp giảm tác động có điều kiện:**

- Nếu chỉ **release mới** gặp lỗi và bản cũ còn ổn, có thể **dừng canary hoặc rollback** theo quy trình phê duyệt; phải kiểm khả năng tương thích migration/schema và cách app cũ đọc dữ liệu do bản mới ghi.
- Nếu DB quá tải do query N+1 mới, hạn chế traffic đắt hoặc vô hiệu feature gây tải bằng feature flag đã được thử; rollback code nếu dữ liệu cho phép.
- Nếu có dấu hiệu retry storm, giảm retry đồng loạt, dùng timeout/deadline, circuit breaker và admission control, thay vì tăng `maxPoolSize` trên mọi pod làm DB càng cạn connection.
- Nếu cần chuyển sang read-only/fallback, phải xác định **route nào còn nhất quán và đúng quyền**. Không trả dữ liệu stale cho thao tác chuyển tiền/hủy đơn rồi coi là đã phục hồi.

**Không thực hiện** restart toàn bộ pod hay xóa bảng outbox để “giảm backlog” mà không có phân tích và quyền thay đổi. Không tăng timeout vô hạn để giữ request ở server lâu hơn; nó có thể làm pool nghẽn nặng hơn.

**Bước 4 — Xác minh hồi phục:** p95/p99, 5xx và pool pending giảm; `GET` đúng dữ liệu tenant; readiness ổn; operation accepted sau thời điểm sửa vẫn hoàn tất; không còn DLQ tăng bất thường. Theo dõi qua một cửa sổ đủ dài để tránh kết luận từ 30 giây đầu sau restart.

### 5.3. Runbook B: 401 tăng sau JWT key rotation

**Trigger:** sau khi IdP công bố khóa ký mới, nhiều request tới `GET /v1/orders` nhận 401; lỗi tập trung ở một region/version hoặc token có `kid` mới.

**Khoanh vùng:**

1. So sánh `WWW-Authenticate` và mã lỗi an toàn từ resource server, tách `invalid_token` khỏi `insufficient_scope`.
2. Kiểm issuer và audience trusted theo cấu hình ứng dụng. **Không dùng ID token** thay access token để test.
3. Kiểm egress/DNS/TLS tới JWKS/IdP, cache refresh, sự tồn tại của key có `kid` tương ứng, clock skew và thuật toán cho phép.
4. So sánh giữa pod/region, rollout version và thời điểm cập nhật key.
5. Chỉ dùng test token được phép; không decode token khách hàng trên trang web công khai.

**Giảm tác động:** khắc phục kết nối tới JWKS, refresh cache/decoder theo cơ chế hỗ trợ, sửa cấu hình issuer/audience sai hoặc rollback một thay đổi config không tương thích. **Tuyệt đối không** tắt signature verification, bỏ kiểm `exp` hoặc chấp nhận issuer bất kỳ để đưa 401 về 0.

**Xác minh:** token hợp lệ với cả khóa cũ còn hiệu lực và khóa mới được chấp nhận trong thời gian luân chuyển theo policy; token giả chữ ký/sai issuer/sai audience vẫn **401**; token hợp lệ thiếu `orders.read` vẫn **403**. Theo dõi tỷ lệ 401 và log JWKS refresh, không chỉ thử một token có quyền cao.

### 5.4. Runbook C: HTTP 202 đều “thành công” nhưng đơn không hoàn tất

**Trigger:** `POST /v1/orders` trả 202 bình thường, nhưng số operation `PENDING/RUNNING` quá hạn, `outbox oldest age` hoặc queue lag tăng; khách hàng thấy “Đang xử lý” lâu.

~~~mermaid
flowchart LR
    POST[202 Accepted] --> OUT[Operation + Outbox]
    OUT --> PUB[Publisher]
    PUB --> Q[Broker queue]
    Q --> W[Worker]
    W --> PAY[Payment / Inventory]
    PAY --> TERM[SUCCEEDED/FAILED]
    OUT -. backlog .-> DIAG[Dashboard / runbook]
    Q -. queue age .-> DIAG
    W -. retry / DLQ .-> DIAG
~~~

**Các câu hỏi cần trả lời theo thứ tự:**

1. `Operation` và `outbox` có được commit cùng transaction trước khi trả 202 không? Nếu không, đây là lỗi mất việc, không chỉ queue chậm.
2. Outbox publisher đang chạy, có lỗi gửi message hoặc retry vô hạn không?
3. Broker còn partition/consumer group hoạt động? Queue age, in-flight, DLQ và delivery rate thế nào?
4. Worker có bị chặn vì Payment timeout, DB lock hoặc retry/backoff quá dài không?
5. Operation state machine có bị kẹt vì lease hết hạn, event trùng hoặc state update bị từ chối không?

**Giảm tác động an toàn:** có thể tạm giảm tốc độ nhận lệnh mới bằng admission control/429/503 có `Retry-After`, scale consumer nếu dependency chịu được, khôi phục publisher, hoặc replay **idempotent** event theo quy trình đối soát. Không chạy lại payment side effect nếu chưa xác minh có thể thu tiền lặp. Không chuyển bừa mọi `PENDING` thành `FAILED` nếu đã có giao dịch downstream chưa rõ kết quả.

**Xác minh:** backlog cũ giảm bền vững, tuổi event giảm, operation đi đến terminal state, không xuất hiện duplicate order/charge, tỷ lệ completion trong SLO phục hồi. Thông báo trạng thái cho client dựa trên operation resource; **client polling timeout không có nghĩa job đã thất bại**.

### 5.5. Runbook D (mở rộng): 429 tăng, client retry storm

Nếu dashboard cho thấy 429 tăng mạnh, tách **quota theo tenant** khỏi **global capacity protection**. Xem request rate, số key/tenant bị ảnh hưởng (qua logs có quyền, không làm metric label động), `Retry-After`, số lần retry, circuit breaker và release của client. Một client retry POST ngay lập tức với key mới có thể tạo thêm tác vụ thay vì phục hồi.

Chỉ điều chỉnh quota khi có bằng chứng và có quyền thay đổi. Cách phục hồi thường là **backoff + jitter, giới hạn retry budget, idempotency key cố định theo logical command**, và giảm overload. Sau sửa phải kiểm 429 giảm **mà không làm 5xx tăng**; nếu chỉ nới quota khiến DB quá tải, đó không phải thành công.

### 5.6. Kịch bản tabletop/fault injection bắt buộc

Chọn **ít nhất hai** tình huống trong A/B/C/D và chạy theo giả lập có kiểm soát:

| Thời điểm mô phỏng | Người điều phối cung cấp | Đội thực hành phải làm |
| --- | --- | --- |
| T+0 | Alert p95/5xx hoặc queue age | Nhận diện severity, SLI và phạm vi |
| T+5 phút | Dashboard cho thấy version mới lỗi, DB pool pending tăng | Đưa ra hai giả thuyết, dữ liệu kiểm chứng |
| T+10 phút | Traces chứng minh pool wait 600 ms, SQL chỉ 30 ms | Chọn mitigation đúng, tránh “thêm index” vô ích |
| T+15 phút | Tắt feature hoặc rollback canary cải thiện latency | Xác minh response hợp đồng và error budget |
| T+30 phút | Bài học về retry budget và canary guardrail | Viết timeline, nguyên nhân, action items có owner |

Các mốc là **kịch bản diễn tập**, không phải lời hứa mọi sự cố phải giải quyết trong 30 phút. Không gây lỗi trên production để “lấy bằng chứng”; dùng staging, mô phỏng metrics hoặc fault injection có giới hạn, được phép và có cách rollback.

**Mẫu báo cáo sau diễn tập:**

~~~text
Scenario ID: OPS-EX-02
Impact: GET /v1/orders p95 > SLO, 5xx tăng ở release canary
Evidence: request rate, version panel, pool pending, trace sample
Root cause (proven): HTTP client pool bị cạn connection
Contributing factors: retry không có budget, timeout quá dài
Mitigation: dừng canary / giảm retry theo chính sách
Verified by: p95, 5xx, pool pending, canary vs baseline
Customer data impact: <có/không/chưa xác định>
Action items: <việc, owner, deadline, evidence>
~~~

**Sự thật và giả thuyết phải được phân biệt.** Nếu chỉ thấy client span 800 ms, chưa thể nói Inventory server xử lý 800 ms; cần so sánh server span, pool wait và network. Nếu không có trace do sampling, kết luận phải ghi giới hạn quan sát thay vì bịa nguyên nhân.

## 6. Đầu ra D — Kế hoạch tiến hóa API không phá client

API không đứng yên: cần thêm filter, thay cách phân trang, sửa lỗi schema và nâng cấp auth. Một thay đổi **đúng về kỹ thuật ở server** vẫn có thể làm client cũ lỗi khi họ deserialize JSON, lưu cursor, retry mutation hoặc hiểu status code khác trước. Kế hoạch tiến hóa phải trả lời: **thay đổi gì, ai bị ảnh hưởng, phát hiện thế nào, triển khai theo thứ tự nào và quay lại ra sao?**

### 6.1. Bảng phân loại thay đổi tương thích

| Thay đổi dự kiến | Mức rủi ro | Hành động yêu cầu |
| --- | --- | --- |
| Thêm **optional field** vào response | Thường tương thích nếu client bỏ qua field lạ | Kiểm strict decoders và contract cũ |
| Thêm field **required** vào request | **Breaking** cho client cũ | Giữ optional/default hoặc tạo hợp đồng mới |
| Đổi ID JSON number → string | **Breaking** kiểu dữ liệu | Version/migration/SDK update |
| Đổi `page/size` → `after/limit` trên cùng URI mà bỏ cách cũ | **Breaking** semantics | Song song endpoint hoặc API version rõ |
| Đổi sort mặc định của list | Có thể **breaking** thứ tự/bookmark | Giữ behavior cũ hoặc version mới |
| Thêm enum order status `AWAITING_REVIEW` | Có thể breaking cho client dùng exhaustive enum | Kiểm SDK, định nghĩa unknown/fallback, thông báo |
| Đổi status 400 → 422 | Có thể breaking xử lý lỗi client | Contract diff, hướng dẫn migration |
| Biến field required nullable thành field bị omit | **Breaking** shape/null semantics | Mô tả version và test JSON serialization |
| Thêm scope bắt buộc `orders.write` cho endpoint trước đây không cần | **Breaking** quyền sử dụng | Kế hoạch auth/consent và thông báo đối tác |
| Thêm cache với stale reads | Có thể breaking ngữ nghĩa consistency | Công bố cache/freshness và test read-your-writes |
| Bỏ endpoint `/v1/orders/export` | **Breaking** | Deprecation policy, thay thế, telemetry usage |
| Thêm cơ chế giới hạn size 100 trước đây không có | Có thể breaking request lớn | Thông báo, migration client, theo dõi 422/429 |

“Thêm field vào response luôn backward-compatible” là khẳng định quá mức: nhiều client Java dùng deserializer strict hoặc SDK generated có enum không hỗ trợ giá trị mới. Vì thế phải **chạy consumer contracts trên những client thực sự được hỗ trợ**, không chỉ dựa vào nguyên tắc lý thuyết.

### 6.2. Bài toán tiến hóa cụ thể: từ offset sang cursor

Hệ thống đang có:

~~~http
GET /v1/orders?page=0&size=20 HTTP/1.1
~~~

Hệ thống muốn hỗ trợ:

~~~http
GET /v1/orders?limit=20&after=<opaque-cursor> HTTP/1.1
~~~

**Không nên** thay `page=0` thành ý nghĩa “cursor đầu” hoặc tự bỏ `totalCount` mà không thông báo, vì client cũ có thể bị hỏng. Hai phương án:

**Phương án A — Giữ song song trong cùng version với hợp đồng tách biệt:**

- Giữ `page/size` cũ cho client hiện tại, không thay sort/default bất ngờ.
- Tạo `/v1/orders:search` hoặc một **operation/path khác đã định nghĩa rõ** cho cursor; hoặc sử dụng `paginationMode=cursor` với schema riêng khi công cụ/docs/client cho phép.
- Ghi rõ hai chế độ không được trộn: `page` cùng `after` trả 400/422 thay vì đoán ý.
- Gắn telemetry để biết bao nhiêu request đang còn dùng offset, đặc biệt `page` sâu.

**Phương án B — Ra `/v2/orders`:**

- `/v1/orders` tiếp tục contract cũ trong cửa sổ hỗ trợ.
- `/v2/orders` dùng cursor, field representation và SDK mới.
- Có hướng dẫn chuyển đổi, kiểm thử end-to-end của client cũ và client mới, policy deprecation/retirement rõ.

Chọn dựa trên mức thay đổi và thỏa thuận với người tích hợp. Không nhất thiết tăng major version cho mọi field tùy chọn, nhưng đổi pagination model và response shape thường đáng xem là thay đổi lớn.

### 6.3. Contract versioning và migration mà không khóa triển khai

Một quy trình **expand → migrate → contract** phù hợp khi nhiều client và service được triển khai không đồng thời:

~~~mermaid
flowchart LR
    A[Expand: server hỗ trợ v1 và v2] --> B[Publish docs + SDK + contract tests]
    B --> C[Canary clients/v2 route]
    C --> D[Observe usage, SLO, errors]
    D --> E{Đạt guardrails?}
    E -- Không --> R[Rollback canary / feature flag]
    E -- Có --> F[Migrate clients theo cohort]
    F --> G[Confirm v1 usage giảm về ngưỡng]
    G --> H[Contract: sunset v1 theo chính sách]
~~~

**Expand:** triển khai schema/database và server sao cho cả v1/v2 đọc/ghi an toàn. Nếu migration DB, ưu tiên thêm cột/đường đọc trước khi xóa cột cũ, và kiểm tương thích giữa app version cũ/mới trong cùng thời gian rollout. Nếu có dual-write, phải có kế hoạch reconciliation và phát hiện divergence; dual-write không tự bảo đảm atomic cross-system.

**Migrate:** công bố migration guide, SDK samples và changelog, mở canary cho tập client có thể rollback; theo dõi tỷ lệ sử dụng v2, 4xx/5xx/p95, idempotency conflicts, cursor invalid và nhóm client v1 còn đang dùng.

**Contract:** chỉ loại bỏ v1 khi đã đạt tiêu chí đã công bố và có phê duyệt phù hợp, không phải khi “đội mình nghĩ chắc không ai dùng”. Nếu các client cũ ngoài kiểm soát vẫn gửi request, cần quyết định hỗ trợ dài hơn, trả deprecation notice hoặc giải pháp chuyển tiếp an toàn.

### 6.4. Cơ chế thông báo deprecation

Trong tài liệu/changelog, ghi **ngày thông báo, chính sách hỗ trợ, deadline và đường thay thế**. Có thể dùng HTTP `Deprecation` và `Sunset` headers khi áp dụng, kèm tài liệu migration. Ví dụ minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1798761600
Sunset: Tue, 30 Mar 2027 00:00:00 GMT
Link: <https://docs.example.com/api/migrate-v2>; rel="deprecation"
~~~

Đây là **ví dụ định dạng header cần kiểm tra với tiêu chuẩn và tooling của stack đang dùng**, không phải một deadline có thật. `Deprecation` cho biết interface đã hoặc sẽ bị deprecate theo mốc công bố; `Sunset` là thời điểm dự kiến ngừng hoạt động. Hai mốc **khác nhau**; đặt trong docs cùng support policy và phải nhất quán với thông báo đối tác. Header không thay email/changelog/migration guide cho client không đọc các header đó.

Một bản thông báo dành cho tích hợp nên chứa:

~~~text
Subject: Lộ trình chuyển từ Orders API v1 pagination sang v2
Change: v1 dùng page/size; v2 dùng limit/after (opaque cursor).
Why: giảm chi phí trang sâu, ổn định điều hướng theo sort.
Affected: client GET danh sách orders và SDK có response schema cũ.
Action: cập nhật SDK, đọc links/nextCursor, không tự tạo cursor.
Compatibility: v1 tiếp tục hoạt động tới thời điểm công bố.
Testing: staging endpoint và các contract scenarios đính kèm.
Timeline: <ngày bắt đầu>, <ngày canary>, <ngày ngừng hỗ trợ>.
Contact: <đầu mối hỗ trợ tích hợp qua kênh chính thức>.
Rollback: client có thể quay lại v1 trong giai đoạn hỗ trợ.
~~~

**Không tự chọn mốc ngừng v1 ngắn hơn hợp đồng hỗ trợ đối tác.** Timeline T0+30/T0+60 trong bài dưới đây chỉ là mô phỏng học thuật; khi thực tế phải căn cứ usage, SLA, thông báo pháp lý/hợp đồng và năng lực client.

### 6.5. Guardrails của rollout và quy tắc rollback

| Giai đoạn | Tỷ lệ traffic giả định | Kiểm tra bắt buộc | Điều kiện dừng |
| --- | --- | --- | --- |
| **Baseline** | 100% v1 | Ghi request rate, p95/p99, 5xx/429, invalid cursor (nếu có), operation completion | Baseline thiếu telemetry hoặc SLO đang vi phạm |
| **Internal** | Chỉ client test | Contract/schema/security, migration, load test, replay cùng request | Không đúng v2 spec hoặc lộ dữ liệu tenant |
| **Canary 1** | 1–5% nhóm được chọn | So v2 với nhóm kiểm soát, traces, errors, DB load | 5xx/p95 vượt guardrail đã phê duyệt |
| **Canary 2** | 10–25% | Client diversity, cursor expiry, backwards compat v1, async correctness | Tăng 409/422 bất thường hoặc duplicate order |
| **Rollout** | Tăng dần 50% → 100% client có khả năng v2 | SLO, error budget, queue, logs, usage v1/v2 | Bất kỳ vi phạm an toàn dữ liệu/quyền |
| **Retire** | V1 chỉ còn usage dưới ngưỡng đã công bố | Đã thông báo, đủ thời gian hỗ trợ, canary v2 đạt | Còn client bắt buộc phụ thuộc v1 hoặc thiếu approvals |

Những tỷ lệ trên là **ví dụ**, không phải chiến lược áp dụng máy móc. Điều kiện rollback phải được định lượng theo **baseline** và SLO: ví dụ 5xx của canary cao hơn nhóm kiểm soát nhiều lần với đủ traffic; p95 vượt giới hạn trong khoảng liên tiếp; 429 hoặc database load tăng; error budget burn quá nhanh; hoặc phát hiện BOLA/duplicate charge. Với lỗi bảo mật/dữ liệu, **không chờ đủ thời gian thống kê**.

Rollback không phải lúc nào cũng chỉ là `kubectl rollout undo`:

- Bản cũ có đọc được dữ liệu/schema do bản mới ghi không?
- Đã có migration không đảo ngược, event schema mới hoặc external side effect mới chưa?
- Bản cũ có xử lý được queue message mới không?
- Cần tắt feature flag hoặc routing v2 thay vì rollback database ngay không?
- Dữ liệu đã ghi nhầm có cần reconciliation/compensation sau rollback không?

Nếu có migration **không thể đảo ngược**, kế hoạch phải nói rõ fallback khác (forward-fix, restore có kiểm soát, tách traffic) thay vì tuyên bố “undo deployment là đủ”.

### 6.6. Một timeline minh họa có bằng chứng ở mỗi mốc

| Mốc | Việc cần hoàn tất | Bằng chứng |
| --- | --- | --- |
| **T0** | Đánh dấu RFC/ADR, duyệt contract diff và phân loại breaking changes | Quyết định thiết kế, OpenAPI v1/v2 |
| **T0 + 1 tuần** | Server hỗ trợ cả v1/v2, metrics và tracing phân biệt version | Contract + security + performance tests |
| **T0 + 2 tuần** | Docs/SDK/staging, thử nhóm client nội bộ | Getting Started, SDK test report |
| **T0 + 30 ngày** | Canary đối tác đã đăng ký, thu phản hồi | Dashboard so cohort, lỗi tích hợp |
| **T0 + 60 ngày** | Mở rộng rollout, ghi usage v1/v2, nhắc deprecation | Usage report, release/incident review |
| **T0 + 90 ngày hoặc muộn hơn theo hợp đồng** | Chỉ đề xuất sunset v1 nếu đủ điều kiện | Phê duyệt, tỷ lệ client đã migrate, support record |

Timeline này là **bài tập lập kế hoạch** và không thay chính sách release thực tế. Tất cả mốc phải có owner, dependencies, cách rollback và tiêu chí **không được tiến lên**.

## 7. Gắn bốn đầu ra vào pipeline kiểm thử và release

Một bộ tài liệu chỉ có giá trị khi được giữ đúng sau mỗi lần thay đổi. Mục tiêu bài tập là đề xuất pipeline đủ phát hiện **contract drift**, sự cố phân quyền, N+1/performance regression, telemetry bị mất và breaking changes — mà không buộc mỗi pull request chạy lại toàn bộ kiểm thử tải nhiều giờ.

### 7.1. Chia tầng kiểm thử theo chi phí và mục đích

| Giai đoạn CI/CD | Kiểm tra | Khi nào chạy |
| --- | --- | --- |
| **Static nhanh** | OpenAPI lint, `$ref`, schema compile, docs links/examples, secret scan | Mọi pull request |
| **Unit/MockMvc** | JSON validation, HTTP status/Problem Details, idempotency adapter, authorization matcher, ETag/If-Match | Mọi pull request |
| **Integration** | PostgreSQL unique constraint, transaction+outbox, tenant filtering, worker retry, schema migrations | Pull request/merge; dữ liệu cô lập |
| **Contract** | Provider/consumer OpenAPI, SDK version cũ, async monitor semantics, backward compatibility diff | Pull request/merge và trước release |
| **Perf/resilience** | N+1 query count, latency dưới tải đại diện, timeouts/429/503, fault injection | Theo release hoặc khi thay đổi hot path |
| **Deploy canary** | Live SLO metrics, trace continuity, readiness/drain, operation completion, 401/403 policy | Khi rollout môi trường staging/production |
| **Post-release** | Error budget, canary vs baseline, client usage, rollback guardrails | Trong cửa sổ quan sát được phê duyệt |

Không coi test chạy bằng `MockMvc.with(jwt())` là chứng cứ xác minh chữ ký JWT: nó thường **bỏ qua JWT decoder thực**, chỉ phù hợp kiểm downstream authorization. Không coi mock database như bằng chứng transaction + outbox có tính bền vững khi crash. Không lấy một trace đơn lẻ làm chứng cứ latency p95. **Mỗi bằng chứng phải đúng tầng**.

### 7.2. Ma trận test bắt buộc xuyên bốn đầu ra

| Scenario | Contract/API docs | Dashboard | Runbook | Evolution |
| --- | --- | --- | --- | --- |
| POST hợp lệ trả 202 | `Location` và schema operation | Accepted rate + completion latency | Theo dõi job chưa xong | v1/v2 giữ idempotency semantics |
| POST trùng key cùng body | Cùng operation, không tạo đơn thứ hai | Duplicate/replayed command metric | Không replay payment mù quáng | Client cũ retry an toàn |
| POST trùng key khác body | 409 + Problem Details | Error code count an toàn | Kiểm client SDK bug | Code/error không đổi bất ngờ |
| GET chéo tenant | 404/403 theo policy | Denied count không lộ ID | Điều tra BOLA | Không nới quyền khi đổi query |
| JWT sai audience | 401 + Bearer challenge | JWT invalid reason theo region | JWKS/issuer/audience runbook | Auth rollout không bỏ validator |
| DB pool exhaustion | 503/504 hoặc timeout theo contract | p95, pool pending, 5xx | Chẩn đoán pool vs SQL | Canary gate/rollback |
| Worker bị kill sau external call | Operation state rõ, không double charge | Queue age/retry/terminal | Reconcile idempotent | Message schema compatible |
| V1 pagination gặp client cũ | Response v1 giữ shape/sort | Usage v1 và error rate | Hỗ trợ đối tác | Chỉ sunset sau bằng chứng |
| V2 cursor bị giả mạo | 400 + error code, không rò dữ liệu | Invalid cursor rate | Xác định abuse/config | Cursor không phụ thuộc nội dung client tự sửa |

### 7.3. Một ví dụ test cho HTTP contract

Với Spring Boot 3.x, JUnit 5 và MockMvc, đoạn sau minh họa assertion **202 phải có monitor URI và body đúng trạng thái**; giả định application test đã cung cấp mock service và principal có quyền:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void acceptedCommandExposesDurableMonitorContract() throws Exception {
    // Mock OrderCommandService trả Operation("op-603", "PENDING", ...).
    // Test ở đây xác minh HTTP shape; durability được test với DB riêng.
    mockMvc.perform(post("/v1/orders")
            .with(jwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.write"))
                .jwt(token -> token.claim("tenant_id", "tenant-a")))
            .header("Idempotency-Key", "test-order-603-v1")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "items": [{"sku":"BOOK-42","quantity":2}],
                  "deliveryAddressId":"addr-12"
                }
                """))
        .andExpect(status().isAccepted())
        .andExpect(header().string(
            "Location", "/v1/operations/op-603"))
        .andExpect(jsonPath("$.state").value("PENDING"))
        .andExpect(jsonPath("$.links.self")
            .value("/v1/operations/op-603"));
}
~~~

Nếu hợp đồng trả operation ID dạng UUID, thay dữ liệu ví dụ bằng ID phù hợp; đừng hardcode `op-603` trong production. Với bài tập, cần **thực thi test** với fixture/mocks/mapper đúng, và thêm integration test về **transaction và outbox**. Lưu bằng chứng PASS/FAIL thực tế, không viết “test pass” khi chưa chạy.

### 7.4. Công cụ kiểm thử tài liệu và thông tin phiên bản

Bạn có thể chọn một công cụ OpenAPI linter và một validator request/response tương thích OpenAPI 3.1; quan trọng là mô tả được **phiên bản công cụ, cấu hình, câu lệnh và exit code**. Ghi version Java/Spring Boot, cơ sở dữ liệu, SDK/client test, OpenAPI và dashboard exporter trong hồ sơ bàn giao để người sau tái hiện được.

Không viết câu “đã tự động kiểm schema” khi pipeline thực tế chỉ kiểm YAML syntax. Một contract test có ý nghĩa phải kiểm **schema của request/response, HTTP status, content type và behavior** tương ứng. Tương tự, dashboard test cần xác minh metric tồn tại và alert thực sự kích hoạt trong kịch bản mô phỏng hoặc dữ liệu test.

## 8. Kịch bản triển khai bài thực hành theo thứ tự phụ thuộc

Đây là **trình tự làm bài**, không phải ước lượng thời gian hay lời hứa thực hiện tự động:

~~~mermaid
flowchart TD
    START[Chốt baseline API + quyền] --> DOC[Viết tài liệu + OpenAPI]
    DOC --> CONTRACT[Contract tests và ví dụ chạy được]
    START --> METRICS[Chọn SLI / SLO và cài instrumentation]
    METRICS --> DASH[Dashboard + alerts]
    CONTRACT --> RUN[Runbook theo failure modes]
    DASH --> RUN
    RUN --> DRILL[Diễn tập sự cố + cập nhật runbook]
    CONTRACT --> EVOL[Contract diff + migration plan]
    DASH --> EVOL
    DRILL --> EVIDENCE[Evidence + nghiệm thu]
    EVOL --> EVIDENCE
~~~

**Vòng 1 — Baseline:** xác định tập endpoint, principal/tenant policy, schema đang phục vụ, request/response mẫu, phiên bản client hiện hành, HTTP metrics và trạng thái deployment. Nếu không có baseline, sẽ không biết migration tạo regression hay không.

**Vòng 2 — Documentation:** viết hướng dẫn tích hợp và OpenAPI, yêu cầu một người khác gọi API test; ghi lại điểm thiếu, sửa dựa trên phản hồi và test tự động. Chỉ dùng dữ liệu giả, không sao chép token/customer data thật.

**Vòng 3 — Observability:** định nghĩa SLI/eligibility trước, xây dashboard và alert từ metrics có thể chứng minh là thật; chạy một failure simulation để thấy graph thay đổi. Kiểm tra route labels/cardinality và bảo mật telemetry.

**Vòng 4 — Operations:** thực hiện tabletop/fault injection trong môi trường kiểm soát. Viết rõ mỗi bước chẩn đoán và điều kiện “nếu A thì B”, thêm rollback/escalation/verification, rồi để người khác dùng runbook đó không cần lời nhắc riêng.

**Vòng 5 — Evolution:** chọn ít nhất một breaking change, lập ma trận ảnh hưởng và roadmap version/deprecation, thực hiện contract diff và chạy client cũ + client mới trên staging. Ghi canary guardrail và fallback khi migration không thể đảo ngược.

**Vòng 6 — Evidence:** gom báo cáo tự kiểm, link artifact, các test có kết quả thật, lỗi còn mở với mức độ ảnh hưởng, người chịu trách nhiệm và quyết định release/no-release.

## 9. Mẫu báo cáo nghiệm thu và rubric

### 9.1. Bảng kiểm có thể dùng khi review chéo

| Hạng mục | Pass khi |
| --- | --- |
| API Reference | Mọi endpoint có method/URI/security/request/response/status và ví dụ lỗi |
| Contract consistency | OpenAPI khớp response thực và không mâu thuẫn về null/time/money/id |
| Pagination | Client biết default/max/sort, cursor expiry và trang cuối |
| Auth and BOLA | 401/403/404 đúng policy; không xem resource khác tenant |
| Async semantics | 202, monitor, retry/idempotency, failure state không mơ hồ |
| Dashboard | Có SLI/SLO, traffic, 5xx/429, p95/p99, dependency và queue |
| Observability quality | Metric labels cardinality thấp, trace/log không có PII/tokens |
| Alerts | Alert có trigger, ngưỡng, no-data policy, link tới runbook và test |
| Runbook | Có trigger, chẩn đoán, mitigation, escalation, rollback, xác minh |
| Drill | Có bằng chứng thao tác, timeline, phát hiện/khắc phục, cải tiến |
| Evolution | Có compatibility matrix, migration/deprecation, canary/rollback |
| Client safety | Client v1/v2 đã được kiểm theo chính sách hỗ trợ |
| Evidence | Kết quả test/ảnh dashboard/runbook drill là thực, ghi rõ mô phỏng |

### 9.2. Thang điểm gợi ý (100 điểm)

| Nhóm | Điểm tối đa | Cách đánh giá |
| --- | ---: | --- |
| **A. Tài liệu và OpenAPI** | 25 | Đầy đủ hợp đồng, ví dụ đúng, lỗi/auth/pagination/async được kiểm bằng test |
| **B. Dashboard, SLI/SLO và alerts** | 25 | SLI rõ, panel có ích, metric thực và alert thử được |
| **C. Runbook và diễn tập** | 25 | Chẩn đoán có chứng cứ, mitigation/rollback an toàn, review sau diễn tập |
| **D. Kế hoạch tiến hóa** | 20 | Phân loại breaking changes, rollout theo cohort, client compatibility, fallback |
| **E. Evidence/handoff** | 5 | Link artifact, phiên bản, kết quả chạy thử, owner và open risks |
| **Tổng** | **100** | Không chỉ chấm văn bản; phải có tính tái hiện và độ tin cậy |

**Điều kiện không đạt dù điểm cao:** phát hiện dữ liệu chéo tenant, lưu token/PII trong tài liệu/dashboard/log, gỡ authentication/CSRF sai kiến trúc để test pass, retry gây double charge, tuyên bố test đã chạy khi chưa có bằng chứng, hoặc kế hoạch migration không có đường xử lý dữ liệu không tương thích.

### 9.3. Mẫu báo cáo cuối cùng

~~~text
Project: Commerce Orders API
Revision / commit: <hash hoặc release tag>
Environment: <local/staging>

Artifacts:
  OpenAPI + Getting Started: <link>
  Error/Conventions docs: <link>
  Dashboard + alert definition: <link>
  Runbook + drill evidence: <link>
  Evolution plan + client notice: <link>

Tests and evidence:
  OpenAPI lint: PASS/FAIL/NOT_RUN + output
  Contract tests: PASS/FAIL/NOT_RUN + output
  Security/BOLA tests: PASS/FAIL/NOT_RUN + output
  Idempotency/outbox tests: PASS/FAIL/NOT_RUN + output
  Dashboard alert simulation: PASS/FAIL/NOT_RUN + evidence
  Tabletop/fault injection: PASS/FAIL/NOT_RUN + timeline
  Client v1 compatibility: PASS/FAIL/NOT_RUN + version

SLO baseline:
  Time window: <UTC interval>
  Eligible request count: <measured>
  Availability, latency, async completion: <measured>
  Trace coverage / telemetry gaps: <measured or unknown>

Open issues:
  <risk, severity, owner, decision deadline>

Decision:
  READY / NOT_READY / READY_WITH_APPROVED_RISK
  Reviewer: <role>
  Approval/rollback link: <link>
~~~

`NOT_RUN` là kết quả hợp lệ khi môi trường chưa hỗ trợ, nhưng phải ghi rõ giới hạn và tác động tới quyết định release; **không được đổi NOT_RUN thành PASS**. Mục tiêu của bài không phải làm mọi panel xanh bằng số giả mà là tạo bằng chứng đáng tin để người khác ra quyết định.

## 10. Câu hỏi tự kiểm tra và bài tập nâng cao

**Bài 1 — Hoàn thiện tài liệu.** Từ ví dụ Orders API, bổ sung `GET /v1/orders` với cursor và `GET /v1/orders/{id}` vào OpenAPI 3.1. Viết bảng 401/403/404/429/503, ý nghĩa ETag/If-Match, thời gian UTC, amount/currency, nullable field, cursor expiry, và ví dụ curl kiểm tra 202 rồi GET operation.

**Bài 2 — Xây dashboard SLO.** Tạo một dashboard có request rate, tỷ lệ 5xx/429, availability SLI 99,9%, latency p95/p99, queue age, operation completion và DB pool. Cho một tập metric giả định **được gắn nhãn mô phỏng**, định nghĩa error budget burn và điều kiện cảnh báo khi traffic thấp/no data.

**Bài 3 — Diễn tập sự cố.** API trả 202 bình thường, nhưng operation không bao giờ tới `SUCCEEDED`. Hãy dùng runbook đi từ outbox → publisher → broker → worker → payment, chỉ ra số liệu cần nhìn ở mỗi bước và cách phục hồi **không làm thu tiền hai lần**.

**Bài 4 — Đọc trace đúng nguyên nhân.** HTTP client span Inventory mất 850 ms, nhưng Inventory server span chỉ 60 ms; DB Orders query 25 ms. Dashboard cho thấy pending-acquire của HTTP client pool tăng. Hãy đề xuất chẩn đoán, mitigation, KPI kiểm hồi phục và cập nhật runbook để tránh lỗi “thêm index DB vô ích”.

**Bài 5 — Tiến hóa v1 → v2.** Một đối tác phụ thuộc `page/size`, response `totalCount` và enum chỉ có `PENDING`/`CONFIRMED`. Thiết kế v2 cursor, xử lý enum mở rộng và thông báo deprecation. Liệt kê những hành vi v1 phải giữ trong cửa sổ hỗ trợ, contract tests của SDK cũ, canary guardrails và rollback khi một số client không nâng cấp.

**Bài 6 — Kiểm thử bảo mật trong release.** Đợt đổi JWT issuer/audience làm 401 tăng sau canary; một developer đề xuất bỏ audience validation cho nhanh. Hãy viết lập luận từ chối, đưa ra runbook kiểm khóa/issuer/audience/clock và định nghĩa tiêu chí “được tiếp tục rollout” phải bao gồm token giả/sai audience vẫn bị từ chối.

**Bài 7 — Handoff cho người không viết hệ thống.** Đưa bốn artifact cho một người khác, yêu cầu họ tìm câu trả lời trong 15 phút diễn tập: “Client retry POST thế nào?”, “Tại sao 202 chưa có order?”, “Dashboard nào cho thấy worker kẹt?”, “Ai phê duyệt rollback?”, “Đến khi nào client v1 còn được hỗ trợ?”. Ghi lại câu hỏi chưa được tài liệu trả lời và cập nhật bản nộp.

### Hướng dẫn đáp án và điểm cần đạt

- **Bài 1:** API reference phải tự chứa và ví dụ có thể chạy ở staging; 202 có monitor, operation terminal phân biệt business success/failure, 401 có Bearer challenge.
- **Bài 2:** Availability SLI có tập eligible/good rõ ràng, không lấy tỷ lệ 5xx toàn traffic thay SLI một cách âm thầm; histogram hợp lệ, no-data được xử lý, alert có runbook.
- **Bài 3:** Kiểm operation/outbox commit, tuổi event, publisher, broker, consumer, retry/DLQ và reconciliation; không replay payment nếu kết quả chưa xác minh.
- **Bài 4:** 850 ms client span không đồng nghĩa server xử lý 850 ms; HTTP pool wait/connection/TLS/retry là nghi vấn, cần metrics và trace xác nhận.
- **Bài 5:** Không xóa `page/size` ngay; enum thêm giá trị có thể phá SDK strict, nên dùng client compatibility tests, canary theo cohort và lịch deprecation có phê duyệt.
- **Bài 6:** Bỏ audience validation là mở khả năng dùng token dành cho resource khác; chỉ sửa trust/JWKS/config đúng nguồn và xác minh negative tests sau sửa.
- **Bài 7:** Bàn giao thành công khi người khác xác định được câu trả lời **từ artifact và bằng chứng**, không phụ thuộc vào trí nhớ của tác giả.

## Kết luận

Một REST API trưởng thành không chỉ đúng resource, URI và status code; nó còn có **hợp đồng để người khác tích hợp**, **tín hiệu đo được để xác định sự cố**, **quy trình phục hồi an toàn** và **lộ trình tiến hóa tôn trọng client cũ**. Bốn đầu ra của bài thực hành phải tham chiếu qua lại: error code trong docs xuất hiện trong dashboard; alert mở đúng runbook; runbook dựa vào traces/metrics có thật; kế hoạch canary/rollback dựa vào SLO và contract tests.

Nếu có một nguyên tắc cần giữ khi bàn giao, đó là: **mỗi lời hứa trong tài liệu phải có hành vi API tương ứng, mỗi cảnh báo phải có bước xử lý, và mỗi thay đổi có rủi ro phải có cách kiểm chứng lẫn phương án phục hồi**.
