# Thực hành tổng hợp: Soạn OpenAPI và rà soát luồng client trước khi triển khai

## 1. Mục tiêu và đầu ra

Một REST API có thể chạy đúng trên server nhưng vẫn khó tích hợp nếu client phải đoán tên trường, mã lỗi, cách phân trang hoặc cách thử lại yêu cầu. Bài thực hành này đặt **hợp đồng API và hành vi client** lên bàn review trước khi đội Java/Spring bắt đầu triển khai. Đây là bài tổng hợp của module **INTEGRATION_API_REST**: thiết kế API theo resource, URI, phương thức và mã trạng thái HTTP; kết hợp hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử.

Sau bài này, người học cần:

1. Chuyển yêu cầu nghiệp vụ thành resource, endpoint và trạng thái HTTP có lý do rõ ràng.
2. Viết được bản OpenAPI 3.1 mô tả request/response, schema, header, xác thực và lỗi.
3. Lần theo đường đi của một client thật, gồm các nhánh timeout, retry, token hết hạn, xung đột phiên bản và phân trang.
4. Đề xuất kiểm thử hợp đồng cùng tiêu chí quyết định API đã sẵn sàng triển khai hay chưa.

**Sản phẩm phải nộp**: tệp `openapi.yaml`, sơ đồ/trình tự `client-flow.md`, ma trận tình huống HTTP và biên bản review ghi rõ điểm đã thống nhất, điểm cần sửa, người chịu trách nhiệm. Phần bên dưới là một lời giải tham khảo có thể dùng làm chuẩn đối chiếu; khi làm bài, hãy thử tự phác thảo hợp đồng trước khi đọc đặc tả mẫu.

## 2. Tình huống nghiệp vụ và phạm vi

Một ứng dụng mua hàng có luồng: người dùng đăng nhập, tạo **đơn hàng nháp** từ danh sách SKU, xem lại đơn, đổi địa chỉ giao hàng, xác nhận đơn và xem lịch sử đơn. Server tính giá và tổng tiền; client chỉ gửi SKU và số lượng. Người dùng chỉ xem/sửa đơn của chính mình.

Các quy tắc được chốt cho bài tập:

| Quy tắc | Hợp đồng cần biểu diễn |
| --- | --- |
| Tạo đơn | `POST /v1/orders` nhận `items` và `shippingAddress`, trả `201 Created`, `Location`, nội dung đơn và `ETag`. Đơn ban đầu có `status=draft`. |
| Chống tạo trùng | Client gửi `Idempotency-Key` khi POST. Cùng người dùng, phương thức, URI, key và cùng payload trong cửa sổ 24 giờ được trả lại kết quả ban đầu; dùng lại key cho payload khác trả `409`. |
| Đọc đơn | `GET /v1/orders/{orderId}` trả `200` kèm `ETag`; hỗ trợ `If-None-Match` để trả `304` khi bản biểu diễn chưa đổi. |
| Sửa đơn | `PATCH /v1/orders/{orderId}` dùng `application/merge-patch+json` và bắt buộc `If-Match` (strong ETag). Sửa địa chỉ khi còn `draft` hoặc chuyển `draft → confirmed`; xử lý nguyên tử. |
| Đồng thời | Thiếu `If-Match`: `428`; phiên bản cũ: `412`; chuyển trạng thái trái quy tắc hoặc đơn không còn cho sửa: `409`. |
| Lịch sử đơn | `GET /v1/orders?limit=20&cursor=...` trả `data` và `nextCursor` (null nếu hết), cursor là chuỗi opaque, không phải số trang. |
| Bảo mật | Bearer token; `401` khi chưa xác thực, `403` khi thiếu quyền chức năng, `404` khi không tìm thấy hoặc không được tiết lộ sự tồn tại của một đơn cụ thể. |
| Lỗi và giới hạn | Trả `application/problem+json`; `400` cho cú pháp/đầu vào sai dạng, `422` cho dữ liệu đúng dạng nhưng không hợp lệ về nghiệp vụ, `429` kèm `Retry-After` khi giới hạn tần suất. |

**Ranh giới bài tập:** không thiết kế thanh toán, đặt giữ tồn kho, email hay vận chuyển thực tế. Các nghiệp vụ đó cần hợp đồng riêng. Ví dụ dùng `VND`, giá theo đơn vị nhỏ nhất của tiền tệ, nhằm tránh lỗi số thực khi cộng tiền.

### Quyết định resource trước khi viết YAML

| Nhu cầu | Resource và phương thức | Vì sao |
| --- | --- | --- |
| Tạo đơn mới | `POST /v1/orders` | Server cấp ID và tạo resource. |
| Liệt kê đơn | `GET /v1/orders` | Truy vấn collection có phân trang. |
| Xem đơn | `GET /v1/orders/{orderId}` | Định danh một resource cụ thể. |
| Đổi địa chỉ/xác nhận | `PATCH /v1/orders/{orderId}` | Cập nhật một phần trạng thái resource, có bảo vệ phiên bản. |

URI diễn đạt **danh từ số nhiều**. Không cần tạo các đường dẫn kiểu `/createOrder`, `/updateAddress`, `/confirmOrder` cho các thao tác này. Trạng thái nghiệp vụ nằm trong biểu diễn đơn và quy tắc chuyển trạng thái.

## 3. Bản OpenAPI 3.1 tham khảo

Lưu đoạn dưới thành `openapi.yaml`. Đây là hợp đồng thiết kế, chưa phải bằng chứng server đã triển khai đúng. Trong dự án thật, hãy bổ sung tên miền, chính sách lưu trữ và ví dụ theo thỏa thuận của hai đội.

~~~yaml
openapi: 3.1.0
info:
  title: Order Draft API
  version: 1.0.0
  description: API tạo, đọc, sửa và xác nhận đơn hàng của người dùng.
servers:
  - url: https://api.example.test
security:
  - bearerAuth: []
tags:
  - name: Orders
    description: Đơn hàng của người dùng đang xác thực

paths:
  /v1/orders:
    post:
      tags: [Orders]
      operationId: createOrder
      summary: Tạo đơn hàng nháp
      description: >
        Idempotency-Key được lưu trong 24 giờ theo principal, method và URI.
        Cùng key và payload trả lại cùng status, body và các header kết quả;
        cùng key với payload khác trả 409.
      parameters:
        - $ref: '#/components/parameters/IdempotencyKey'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
            example:
              items:
                - sku: BOOK-JAVA
                  quantity: 2
              shippingAddress:
                recipientName: Nguyen An
                street: 12 Nguyen Hue
                city: Ho Chi Minh City
      responses:
        '201':
          description: Đã tạo đơn; replay hợp lệ trả lại kết quả tạo ban đầu
          headers:
            Location:
              description: URI của đơn vừa tạo
              schema:
                type: string
                format: uri-reference
            ETag:
              $ref: '#/components/headers/ETag'
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
              example:
                id: 9e2c9e3e-73b4-45bb-b5c4-9f8d4c2f1438
                status: draft
                currency: VND
                items:
                  - sku: BOOK-JAVA
                    quantity: 2
                    unitPriceMinor: 150000
                    lineTotalMinor: 300000
                totalAmountMinor: 300000
                shippingAddress:
                  recipientName: Nguyen An
                  street: 12 Nguyen Hue
                  city: Ho Chi Minh City
                createdAt: '2026-11-18T08:00:00Z'
                updatedAt: '2026-11-18T08:00:00Z'
        '400':
          $ref: '#/components/responses/Problem'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/Problem'
        '409':
          $ref: '#/components/responses/Problem'
        '422':
          $ref: '#/components/responses/Problem'
        '429':
          $ref: '#/components/responses/RateLimited'
    get:
      tags: [Orders]
      operationId: listOrders
      summary: Liệt kê đơn hàng thuộc người dùng
      description: >
        Sắp xếp theo updatedAt giảm dần, rồi id giảm dần để phân định
        thứ tự khi trùng thời điểm. Cursor là opaque; client không phân tích.
      parameters:
        - name: limit
          in: query
          description: Kích thước trang
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: cursor
          in: query
          description: Cursor do trang trước trả về
          schema:
            type: string
            minLength: 1
      responses:
        '200':
          description: Một trang đơn hàng; mảng data có thể rỗng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderPage'
        '400':
          $ref: '#/components/responses/Problem'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/Problem'
        '429':
          $ref: '#/components/responses/RateLimited'

  /v1/orders/{orderId}:
    parameters:
      - $ref: '#/components/parameters/OrderId'
    get:
      tags: [Orders]
      operationId: getOrder
      summary: Lấy đơn hàng và phiên bản hiện tại
      parameters:
        - name: If-None-Match
          in: header
          description: ETag client đang có để tái xác thực bản biểu diễn
          schema:
            type: string
      responses:
        '200':
          description: Chi tiết đơn
          headers:
            ETag:
              $ref: '#/components/headers/ETag'
            Cache-Control:
              description: Chỉ cache riêng tư và phải tái xác thực trước khi dùng
              schema:
                type: string
              example: private, no-cache
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '304':
          description: Không đổi so với If-None-Match; không có body
          headers:
            ETag:
              $ref: '#/components/headers/ETag'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/Problem'
        '404':
          $ref: '#/components/responses/Problem'
        '429':
          $ref: '#/components/responses/RateLimited'
    patch:
      tags: [Orders]
      operationId: patchOrder
      summary: Đổi địa chỉ hoặc xác nhận đơn nháp
      description: >
        Chỉ đơn draft được sửa. Có thể đổi shippingAddress hoặc đặt
        status=confirmed. Server áp dụng toàn bộ patch nguyên tử.
      parameters:
        - $ref: '#/components/parameters/IfMatch'
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              $ref: '#/components/schemas/PatchOrder'
            example:
              shippingAddress:
                recipientName: Nguyen An
                street: 21 Le Loi
                city: Ho Chi Minh City
      responses:
        '200':
          description: Đơn sau cập nhật
          headers:
            ETag:
              $ref: '#/components/headers/ETag'
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400':
          $ref: '#/components/responses/Problem'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/Problem'
        '404':
          $ref: '#/components/responses/Problem'
        '409':
          $ref: '#/components/responses/Problem'
        '412':
          $ref: '#/components/responses/Problem'
        '422':
          $ref: '#/components/responses/Problem'
        '428':
          $ref: '#/components/responses/Problem'
        '429':
          $ref: '#/components/responses/RateLimited'

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  parameters:
    OrderId:
      name: orderId
      in: path
      required: true
      schema:
        type: string
        format: uuid
    IdempotencyKey:
      name: Idempotency-Key
      in: header
      required: true
      description: Khóa duy nhất cho một ý định tạo đơn, có thể là UUID
      schema:
        type: string
        minLength: 8
        maxLength: 128
    IfMatch:
      name: If-Match
      in: header
      required: true
      description: Strong ETag lấy từ GET/POST/PATCH gần nhất
      schema:
        type: string
  headers:
    ETag:
      description: Strong entity tag của biểu diễn đơn hiện tại
      schema:
        type: string
  responses:
    Problem:
      description: Lỗi API, xem mã HTTP và trường code
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    Unauthorized:
      description: Thiếu hoặc không chấp nhận được thông tin xác thực
      headers:
        WWW-Authenticate:
          schema:
            type: string
          example: Bearer
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    RateLimited:
      description: Quá giới hạn tần suất
      headers:
        Retry-After:
          description: Số giây hoặc ngày HTTP trước khi thử lại
          schema:
            type: string
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
  schemas:
    Address:
      type: object
      additionalProperties: false
      required: [recipientName, street, city]
      properties:
        recipientName:
          type: string
          minLength: 1
          maxLength: 120
        street:
          type: string
          minLength: 1
          maxLength: 240
        city:
          type: string
          minLength: 1
          maxLength: 120
    CreateOrderItem:
      type: object
      additionalProperties: false
      required: [sku, quantity]
      properties:
        sku:
          type: string
          minLength: 1
          maxLength: 64
        quantity:
          type: integer
          minimum: 1
          maximum: 99
    CreateOrder:
      type: object
      additionalProperties: false
      required: [items, shippingAddress]
      properties:
        items:
          type: array
          minItems: 1
          maxItems: 50
          items:
            $ref: '#/components/schemas/CreateOrderItem'
        shippingAddress:
          $ref: '#/components/schemas/Address'
    PatchOrder:
      type: object
      additionalProperties: false
      minProperties: 1
      properties:
        shippingAddress:
          $ref: '#/components/schemas/Address'
        status:
          type: string
          enum: [confirmed]
    OrderItem:
      type: object
      additionalProperties: false
      required: [sku, quantity, unitPriceMinor, lineTotalMinor]
      properties:
        sku:
          type: string
        quantity:
          type: integer
          minimum: 1
        unitPriceMinor:
          type: integer
          minimum: 0
        lineTotalMinor:
          type: integer
          minimum: 0
    Order:
      type: object
      additionalProperties: false
      required: [id, status, currency, items, totalAmountMinor,
                 shippingAddress, createdAt, updatedAt]
      properties:
        id:
          type: string
          format: uuid
          readOnly: true
        status:
          type: string
          enum: [draft, confirmed]
        currency:
          type: string
          const: VND
        items:
          type: array
          items:
            $ref: '#/components/schemas/OrderItem'
        totalAmountMinor:
          type: integer
          minimum: 0
          readOnly: true
        shippingAddress:
          $ref: '#/components/schemas/Address'
        createdAt:
          type: string
          format: date-time
        updatedAt:
          type: string
          format: date-time
    OrderSummary:
      type: object
      additionalProperties: false
      required: [id, status, totalAmountMinor, updatedAt]
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [draft, confirmed]
        totalAmountMinor:
          type: integer
          minimum: 0
        updatedAt:
          type: string
          format: date-time
    OrderPage:
      type: object
      additionalProperties: false
      required: [data, nextCursor]
      properties:
        data:
          type: array
          items:
            $ref: '#/components/schemas/OrderSummary'
        nextCursor:
          type: [string, 'null']
          description: null nếu không còn trang tiếp theo
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
          minimum: 400
          maximum: 599
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
          description: Mã lỗi nghiệp vụ ổn định cho client
        traceId:
          type: string
          description: Định danh truy vết; không chứa dữ liệu nhạy cảm
~~~

**Những điểm OpenAPI chưa thể tự bảo đảm:** công cụ kiểm tra schema không chứng minh được “cùng key không tạo hai đơn”, kiểm soát quyền sở hữu, tính nguyên tử của PATCH, điều kiện chuyển trạng thái hay tính đúng đắn của ETag. Các quy tắc này phải được thể hiện trong mô tả, kiểm thử tích hợp và code server. Ngoài ra, `format: uuid` và `format: date-time` có thể được các validator xử lý khác nhau; cần chọn công cụ và cấu hình xác thực thống nhất.

## 4. Rà soát luồng client từ đầu đến cuối

Trước khi viết controller, hai đội cùng duyệt sơ đồ sau; mọi mũi tên cần khớp với ít nhất một operation trong OpenAPI:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client
    participant A as Order API
    U->>C: Chọn SKU và nhập địa chỉ
    C->>C: Sinh và lưu key cho ý định tạo đơn
    C->>A: POST /v1/orders + Bearer + Idempotency-Key
    A-->>C: 201 + Location + ETag "ord-1" + Order(draft)
    C->>A: GET /v1/orders/{id}
    A-->>C: 200 + ETag "ord-1" + Order(draft)
    U->>C: Đổi địa chỉ
    C->>A: PATCH /v1/orders/{id} + If-Match "ord-1"
    A-->>C: 200 + ETag "ord-2" + Order(draft)
    U->>C: Xác nhận
    C->>A: PATCH /v1/orders/{id} + If-Match "ord-2"
    A-->>C: 200 + ETag "ord-3" + Order(confirmed)
    C->>A: GET /v1/orders?limit=20
    A-->>C: 200 + data + nextCursor
~~~

### Đọc một trao đổi HTTP thật

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 8eaa68e1-39fb-451b-9317-9908d9c40fd4

{"items":[{"sku":"BOOK-JAVA","quantity":2}],"shippingAddress":{"recipientName":"Nguyen An","street":"12 Nguyen Hue","city":"Ho Chi Minh City"}}

HTTP/1.1 201 Created
Location: /v1/orders/9e2c9e3e-73b4-45bb-b5c4-9f8d4c2f1438
ETag: "ord-1"
Content-Type: application/json

{"id":"9e2c9e3e-73b4-45bb-b5c4-9f8d4c2f1438","status":"draft","currency":"VND","items":[{"sku":"BOOK-JAVA","quantity":2,"unitPriceMinor":150000,"lineTotalMinor":300000}],"totalAmountMinor":300000,"shippingAddress":{"recipientName":"Nguyen An","street":"12 Nguyen Hue","city":"Ho Chi Minh City"},"createdAt":"2026-11-18T08:00:00Z","updatedAt":"2026-11-18T08:00:00Z"}
~~~

Để cập nhật địa chỉ, client gửi `PATCH` với `Content-Type: application/merge-patch+json`, `If-Match: "ord-1"` và body chỉ chứa `shippingAddress` đầy đủ. Server trả biểu diễn mới cùng ETag mới. Client dùng ETag mới khi xác nhận bằng body `{"status":"confirmed"}`. Với JSON Merge Patch, `null` có nghĩa loại bỏ trường; hợp đồng này không cho xóa các trường bắt buộc, nên client không gửi `null` để “xóa địa chỉ”.

**Phân biệt hai header điều kiện:** `If-None-Match` dùng khi GET nhằm tránh tải lại biểu diễn chưa đổi (`304` không có body); `If-Match` dùng khi PATCH để tránh ghi đè bản mới hơn (`412` nếu ETag không khớp). Client không tự ghép hay đoán ETag.

### Phân nhánh khi xảy ra lỗi

| Tình huống client thấy | Hành động đúng của client | Kỳ vọng phía server |
| --- | --- | --- |
| POST đã gửi nhưng mất kết nối, không biết đã tạo đơn chưa | Giữ **cùng** `Idempotency-Key` và payload để thử lại trong thời hạn hợp đồng; không sinh key mới | Trả lại kết quả POST đầu tiên, không tạo đơn thứ hai |
| POST cùng key nhưng body khác | Sinh key mới chỉ khi người dùng thật sự tạo một ý định đơn mới; báo lỗi logic nếu tái dùng nhầm | `409` với mã lỗi phân biệt key trùng payload khác |
| Access token hết hạn | Thử lấy token hợp lệ qua cơ chế đăng nhập/refresh đã thỏa thuận rồi gửi lại tối đa theo chính sách client | `401` và `WWW-Authenticate`; không biến thành `403` |
| Người dùng không có quyền chức năng | Hiển thị không được phép; không retry bằng cùng quyền | `403` |
| Đọc ID không tồn tại hoặc ID của người khác | Hiển thị “không tìm thấy”; không hé lộ chủ đơn | `404` theo chính sách bảo mật đã chốt |
| PATCH thiếu `If-Match` | Lấy lại chi tiết và ETag rồi xin người dùng xác nhận thay đổi | `428 Precondition Required` |
| PATCH bằng ETag cũ | GET lại đơn, đối chiếu dữ liệu mới, cho người dùng quyết định gửi thay đổi mới | `412 Precondition Failed`, không ghi đè dữ liệu |
| Đơn đã confirmed mà tiếp tục sửa địa chỉ | Khóa thao tác sửa và hiển thị trạng thái hiện tại | `409 Conflict` với mã lỗi nghiệp vụ |
| SKU hết khả dụng, số lượng không đáp ứng quy tắc | Hiển thị vấn đề tại mục tương ứng | `422 Unprocessable Content` với thông tin lỗi an toàn |
| Client gửi JSON hỏng, query limit không hợp lệ | Sửa request, không retry y nguyên | `400 Bad Request` |
| GET có `If-None-Match` phù hợp | Dùng bản biểu diễn đã lưu, chỉ khi bản đó thực sự còn sẵn | `304 Not Modified`, không có body |
| `429` hoặc lỗi server thoáng qua | Với `429`, tôn trọng `Retry-After`; dùng backoff có jitter, giới hạn lượt thử; với PATCH không rõ kết quả thì GET đối soát trước khi gửi tiếp | Server không yêu cầu client retry vô hạn, trả lỗi có thể truy vết |

Lưu ý: giữ lại `Idempotency-Key` giữa các lần retry cùng một ý định tạo đơn. Sau khi nhận xác nhận hoặc hết thời hạn 24 giờ, client phải có chiến lược đối soát bằng resource/đơn đã biết trước khi tạo ý định mới. Không mặc định bất kỳ POST nào cũng idempotent nếu thiếu hợp đồng như ở đây.

## 5. Review hợp đồng và sự tương thích trước khi viết Java/Spring

Tổ chức một buổi review có ít nhất đại diện client, backend và QA. Lần lượt mở tài liệu OpenAPI, sơ đồ và các ví dụ HTTP; đối với mỗi ô dưới đây, ghi **PASS**, **NEEDS CHANGE** hoặc **OPEN QUESTION**, kèm quyết định.

| Nhóm kiểm tra | Câu hỏi buộc phải trả lời được |
| --- | --- |
| Resource và HTTP | Các URI có nhất quán không? `POST` trả `201`/`Location`? `GET` không tạo tác dụng phụ? `PATCH` được xử lý nguyên tử? |
| Schema và dữ liệu | Field nào bắt buộc, tối đa bao nhiêu phần tử, kiểu `null` có hợp lệ không? Client có gửi giá tiền hay server tự tính? |
| Chính sách trạng thái | Những chuyển đổi nào hợp lệ? Xác nhận hai lần có hiệu ứng gì? `409` khác `412` ra sao? |
| Retry và đồng thời | Key được sinh/lưu ở đâu, phạm vi và TTL là gì? ETag có đổi sau mọi cập nhật không? Khi timeout ở PATCH, client đối soát thế nào? |
| Phân trang | Limit mặc định/tối đa? Cursor được ràng buộc với người dùng và bộ lọc ra sao? Khi có đơn mới/cập nhật giữa các trang thì chấp nhận lặp hoặc bỏ sót như thế nào? |
| Bảo mật | Kiểm tra quyền sở hữu tại backend thế nào? Token có bị đưa vào query/log không? Có tránh trả thông tin đơn của tài khoản khác không? |
| Cache và lỗi | `304` có body không? Header cache có phù hợp dữ liệu cá nhân? Lỗi có `application/problem+json`, `code`, `traceId` mà không lộ thông tin nhạy cảm không? |
| Vận hành client | Timeout, retry budget, xử lý `Retry-After`, UX khi offline và chuyển trạng thái màn hình đã được chốt chưa? |
| Tương thích | Thay đổi schema có phá client cũ không? Có cơ chế thông báo deprecation/version và thay đổi ví dụ SDK/mock không? |

Riêng cursor pagination, đặc tả mẫu chỉ chốt thứ tự và ý nghĩa `nextCursor`; **tính ổn định khi dữ liệu thay đổi giữa các lần lấy trang là một quyết định còn mở**. Phải chọn một trong các mô hình (ảnh chụp nhất quán theo snapshot, hoặc danh sách cập nhật gần thời gian thực có thể lặp/bỏ sót), ghi vào contract và viết kiểm thử tương ứng. Client tối thiểu nên loại trùng theo `id`; việc này không tự giải quyết được bản ghi bị bỏ sót.

### Phản biện mẫu: phát hiện 5 lỗi trước khi triển khai

Cho nhóm nhận một bản đề xuất sai: `POST /createOrder` không nhận idempotency key; `PATCH` không nhận `If-Match`; server trả mọi lỗi dưới dạng `200 {"success":false}`; danh sách đơn chỉ có `page=1` và không quy định sort; một người dùng có thể đọc đơn của người khác qua ID. Hãy sửa hợp đồng và giải thích rủi ro:

1. POST thiếu idempotency key có thể tạo đơn trùng sau timeout.
2. PATCH không kiểm soát phiên bản có thể ghi đè thay đổi của thiết bị khác.
3. HTTP `200` cho lỗi phá semantic của HTTP, retry logic, alerting và client generator.
4. Phân trang không có sắp xếp xác định dẫn đến kết quả khó tái lập khi dữ liệu thay đổi.
5. Thiếu kiểm tra quyền theo từng resource là lỗi phân quyền đối tượng; token hợp lệ không có nghĩa được đọc mọi đơn.

## 6. Kế hoạch kiểm thử trước và sau triển khai

**Trước khi có server:** dùng công cụ lint/validate OpenAPI để bắt lỗi cú pháp và reference, dựng mock server từ spec, sinh request mẫu hoặc SDK thử nghiệm. Chẳng hạn, nếu dự án sử dụng Redocly CLI:

~~~bash
npx @redocly/cli lint openapi.yaml
~~~

Sau khi có server Java/Spring, biến từng hành vi thành contract/integration test với cơ sở dữ liệu độc lập và token cho ít nhất hai tài khoản. Một bộ kiểm thử tối thiểu có thể mô tả như sau:

| Test ID | Thiết lập và hành động | Điều kiện đạt |
| --- | --- | --- |
| CT-01 | POST body hợp lệ và key mới | `201`, `Location` trỏ được đến GET `200`, body khớp schema, có strong ETag |
| CT-02 | Lặp POST cùng key và payload (kể cả giả lập mất response) | Cùng kết quả và chỉ một đơn trong DB |
| CT-03 | Lặp key nhưng đổi số lượng | `409`, vẫn chỉ một đơn |
| CT-04 | Hai client GET cùng ETag; A PATCH thành công, B PATCH bằng ETag cũ | A nhận ETag mới, B nhận `412`, dữ liệu A không bị ghi đè |
| CT-05 | PATCH không kèm `If-Match` | `428`, dữ liệu không thay đổi |
| CT-06 | Xác nhận đơn, sau đó sửa địa chỉ | Lần xác nhận hợp lệ; sửa sau xác nhận trả `409` |
| CT-07 | GET với `If-None-Match` bằng ETag hiện tại | `304`, không có body |
| CT-08 | Token thiếu/hết hạn; token không có quyền; user B đọc order của A | Lần lượt xử lý `401`, `403` khi phù hợp, `404` cho ID bị che giấu; không rò rỉ dữ liệu |
| CT-09 | List với `limit=2`, duyệt đến `nextCursor=null` | Đúng giới hạn/trật tự đã chốt, cursor hoạt động, không lộ đơn của tài khoản khác |
| CT-10 | JSON lỗi, dữ liệu nghiệp vụ không hợp lệ, giới hạn tần suất | Trả `400`, `422`, `429` và media type/header được mô tả |
| CT-11 | So response thực tế với OpenAPI bằng contract testing | Không có response field ngoài dự kiến, sai kiểu, sai mã trạng thái hoặc thiếu header bắt buộc |

Một test idempotency phải kiểm tra **tác dụng trong database**, không chỉ nhìn hai response đều trả `201`. Một test phân quyền phải dùng **hai principal thật sự khác nhau** để phát hiện lỗ hổng truy cập theo ID. Kiểm thử retry cần giả lập mất phản hồi **sau khi server đã commit**, vì đó là ca dễ sinh đơn trùng nhất.

### Bài nộp và thang tự đánh giá

| Hạng mục | Điểm tối đa | Bằng chứng cần có |
| --- | ---: | --- |
| Resource, HTTP method, status, lifecycle | 20 | Bảng quyết định và API paths có giải thích |
| OpenAPI hợp lệ, schema và ví dụ | 25 | Tệp lint được, schema/header/security/response nhất quán |
| Luồng client thành công và thất bại | 25 | Sơ đồ, xử lý retry/token/ETag/cursor có thể thực hiện |
| Bảo mật và tính nhất quán | 15 | Quy tắc ownership, idempotency, concurrency, không tiết lộ dữ liệu |
| Kiểm thử và review trước triển khai | 15 | Test cases, mock/contract check, danh sách open questions |
| **Tổng** | **100** | |

Chỉ chấp nhận chuyển sang triển khai khi không còn câu hỏi mở ảnh hưởng đến việc client gọi API: ít nhất phải chốt ý nghĩa từng status, thời hạn idempotency key, hành vi PATCH khi timeout, bảo mật theo đơn và tính ổn định của phân trang. Những thay đổi sau buổi review cần được cập nhật vào OpenAPI, tài liệu client và test cases trong cùng một thay đổi có thể review.

## 7. Câu hỏi tự kiểm tra

1. Vì sao sau khi POST timeout, gửi lại cùng payload với **key mới** có thể gây ra lỗi nghiêm trọng?
2. Khi GET trả `304`, client cần có điều kiện gì mới được dùng dữ liệu đã lưu?
3. Sự khác nhau về ý nghĩa và cách xử lý client giữa `409`, `412`, `428` là gì?
4. Vì sao mô tả `bearerAuth` trong OpenAPI vẫn chưa chứng minh có phân quyền theo chủ sở hữu đơn?
5. Nếu `nextCursor` không null nhưng có đơn mới chen vào đầu danh sách, contract cần quy định điều gì để client không suy luận sai?
6. Test nào phân biệt được một server trả response đúng định dạng với một server thật sự không tạo trùng đơn?

**Hướng đối chiếu:** (1) key mới có thể được hiểu là ý định mới; (2) client phải có bản biểu diễn tương ứng còn khả dụng và đúng scope; (3) `409` là xung đột quy tắc nghiệp vụ/key, `412` là điều kiện ETag thất bại, `428` là thiếu điều kiện bắt buộc; (4) xác thực khác phân quyền ở cấp resource; (5) phải chốt ngữ nghĩa nhất quán của cursor khi dữ liệu biến động; (6) kiểm thử số bản ghi/side effect trong DB dưới retry sau commit.
