# Liên kết phụ thuộc trạng thái hoặc quyền người sử dụng

## 1. Hypermedia trả lời câu hỏi: tiếp theo có thể làm gì?

Trong REST API, tài nguyên có URI, representation mô tả trạng thái và HTTP method biểu diễn thao tác. Nhưng không phải lúc nào người gọi cũng được thực hiện mọi thao tác trên cùng resource. Một đơn hàng **DRAFT** có thể gửi duyệt; khi đơn đã **APPROVED**, gửi duyệt lần nữa không còn phù hợp. Cùng ở trạng thái **SUBMITTED**, người quản lý được duyệt còn người tạo chỉ có thể xem hoặc hủy theo chính sách.

**Hypermedia** bổ sung vào dữ liệu các **liên kết điều hướng và khả năng thao tác** có ý nghĩa với ngữ cảnh hiện tại. Ý tưởng này thường được gọi là **HATEOAS — Hypermedia as the Engine of Application State**: client đọc representation, nhận những quan hệ liên kết/hành động do server cung cấp và chọn bước tương tác kế tiếp.

Bài thuộc chương **Hypermedia** của module **INTEGRATION_API_REST**. Nội dung kết nối thiết kế REST dựa trên resource, URI, phương thức, mã trạng thái và hợp đồng dữ liệu với các chủ đề xác thực, phân quyền, cache, idempotency, OpenAPI, xử lý lỗi và kiểm thử bằng Java/Spring hoặc công nghệ tương đương.

Mục tiêu học tập:

1. Phân biệt **link**, **action/affordance** và **quyền thực thi thực sự**.
2. Tạo liên kết phụ thuộc **trạng thái, vai trò, owner, tenant** và điều kiện nghiệp vụ.
3. Biểu diễn hypermedia bằng **HAL** và **Siren** mà không nhầm link GET với thao tác ghi.
4. Giải quyết khoảng thời gian từ lúc hiện action đến khi server nhận lệnh: kiểm tra lại quyền, ETag, trạng thái và xử lý xung đột.
5. Thiết kế cache, API contract, test và giao diện client thích hợp với hypermedia.

**Nguyên tắc quan trọng:** action xuất hiện chỉ là **khả năng được server giới thiệu ở thời điểm đọc**. Việc **ẩn link không phải cơ chế bảo mật**. Endpoint thực hiện hành động vẫn phải xác thực, phân quyền và kiểm tra trạng thái tại lúc xử lý.

## 2. Ba khái niệm cần tách bạch

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Link** | Có thể điều hướng đến resource nào, có quan hệ gì với resource hiện tại? | `self`, `collection`, `items`, `history` |
| **Action / affordance** | Có thao tác nào, dùng method, URI, kiểu body và trường đầu vào gì? | `POST /v1/orders/{id}/approvals` |
| **Authorization** | Principal hiện tại có **thực sự** được làm việc đó không? | Manager đúng tenant, không phải người tạo đơn, được duyệt |

Một link `self` chỉ định URI của resource. Action `approve` có thể mô tả một POST và form đầu vào. Giao diện nhìn action đó để bật nút **Duyệt**. Server nhận POST vẫn phải kiểm tra lại từ đầu vì client có thể lưu URL, tự dựng URL hoặc dùng representation cũ.

### 2.1. Relation type không phải URL pattern

Liên kết gồm **target URI** và **relation type** (`rel`) nêu ngữ nghĩa. Các quan hệ phổ biến như `self`, `next`, `prev`, `collection` nên được sử dụng đúng mục đích. Với thao tác nghiệp vụ riêng, cần công bố quan hệ mở rộng có ý nghĩa ổn định, chẳng hạn:

~~~text
https://api.example.com/rels/submit-order
https://api.example.com/rels/approve-order
https://api.example.com/rels/cancel-order
~~~

Client có thể tìm theo **relation/action đã biết** thay vì tự nối chuỗi `/orders/{id}/approvals` ở nhiều vị trí. Relation không nên được đặt tên tùy tiện gây nhầm nghĩa; ví dụ `next` không đồng nghĩa “duyệt đơn” chỉ vì đó là màn hình tiếp theo.

### 2.2. Hypermedia khác danh mục endpoint cố định

Một representation luôn phát đủ `submit`, `approve`, `cancel`, `delete` cho mọi trạng thái và người dùng chỉ là tập đường dẫn cố định, rất ít giúp client hiểu workflow. Giá trị của hypermedia nằm ở việc **link/action phản ánh khả năng hiện tại**; điều hướng công khai như tài liệu trợ giúp vẫn có thể luôn được cung cấp.

## 3. Tình huống xuyên suốt: đơn hàng cần phê duyệt

Giả sử một hệ thống nội bộ có nhiều tenant, mỗi đơn hàng tại `/v1/orders/{orderId}` chứa:

~~~json
{
  "id": "o-17",
  "tenantId": "tenant-a",
  "createdBy": "user-7",
  "status": "DRAFT",
  "totalAmount": "2400000",
  "currency": "VND",
  "version": 4
}
~~~

Bài tập dùng bốn trạng thái **DRAFT**, **SUBMITTED**, **APPROVED**, **CANCELLED** với các điều kiện minh họa. Không mặc định mọi ứng dụng đều có workflow như vậy.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: Tạo đơn
    DRAFT --> SUBMITTED: Owner gửi duyệt
    DRAFT --> CANCELLED: Owner hủy
    SUBMITTED --> APPROVED: Manager duyệt
    SUBMITTED --> CANCELLED: Owner hủy trước khi duyệt
    APPROVED --> [*]
    CANCELLED --> [*]
~~~

### 3.1. Những vai trò tham gia

- **Owner:** người tạo đơn, chỉ xem đơn được phép trong tenant; được gửi duyệt hoặc hủy tùy trạng thái.
- **Manager:** người quản lý được cấp quyền trong tenant; duyệt đơn **SUBMITTED** và **không do chính mình tạo** theo quy tắc tách nhiệm vụ.
- **Auditor:** được xem resource và lịch sử trong phạm vi kiểm toán, không thay đổi trạng thái.
- **Người ngoài phạm vi:** không được xem đơn; dùng 404 trung tính để không tiết lộ sự tồn tại nếu chính sách yêu cầu.

### 3.2. Ma trận action do server phát

| Trạng thái | Principal đã có quyền xem | `submit` | `cancel` | `approve` |
|---|---|---|---|---|
| **DRAFT** | Owner | Có | Có | Không |
| **DRAFT** | Manager/Auditor | Không | Không | Không |
| **SUBMITTED** | Owner | Không | Có | Không |
| **SUBMITTED** | Manager không phải người tạo | Không | Không | Có |
| **SUBMITTED** | Auditor hoặc manager tự tạo đơn | Không | Không | Không |
| **APPROVED** | Bất kỳ người có quyền xem | Không | Không | Không |
| **CANCELLED** | Bất kỳ người có quyền xem | Không | Không | Không |
| Bất kỳ | Không có quyền xem/khác tenant | Không trả representation | Không | Không |

Các người gọi được quyền xem có thể nhận `self`, `items` và `history` theo quyền riêng đối với từng resource con. Việc action không xuất hiện **không làm endpoint biến mất**, cũng không có nghĩa không thể thử gọi URI trực tiếp; server phải chặn yêu cầu không hợp lệ.

### 3.3. Luồng quyết định ở server

~~~mermaid
flowchart TD
    A["GET /v1/orders/{id}"] --> B{"Đã xác thực?"}
    B -->|Không| C["401 + WWW-Authenticate"]
    B -->|Có| D{"Được xem resource?"}
    D -->|Không| E["404 trung tính"]
    D -->|Có| F["Representation và link đọc hợp lệ"]
    F --> G{"Owner + DRAFT?"}
    G -->|Có| H["Thêm submit"]
    G -->|Không| I{"Owner + DRAFT/SUBMITTED?"}
    H --> I
    I -->|Có| J["Thêm cancel"]
    I -->|Không| K{"Manager khác người tạo + SUBMITTED?"}
    J --> K
    K -->|Có| L["Thêm approve"]
    K -->|Không| M["Trả representation"]
    L --> M
~~~

Sơ đồ rút gọn điều kiện để dễ học. Chính sách thực tế có thể kiểm tra thêm quyền hành động, hạn mức, trạng thái thanh toán, thời gian đóng sổ hoặc khóa nghiệp vụ. **Phạm vi nhìn thấy** phải được xác định trước khi tạo link nhạy cảm.

## 4. Dùng chung chính sách, kiểm tra ở hai thời điểm

Một policy service tập trung có thể cung cấp:

~~~text
OrderPolicy.canView(actor, order)
OrderPolicy.canReadItems(actor, order)
OrderPolicy.canSubmit(actor, order)
OrderPolicy.canCancel(actor, order)
OrderPolicy.canApprove(actor, order)
~~~

**Representation assembler** dùng chúng để chọn action; **command handler** cũng dùng cùng quy tắc để quyết định thao tác thực sự. Tránh một bộ `if` của GET trả action khác với logic POST xử lý lệnh.

Tuy dùng chung quy tắc, vẫn có hai thời điểm độc lập:

1. **GET:** server tính action từ trạng thái đã đọc, cho client biết có thể làm gì **vào lúc ấy**.
2. **POST/PATCH/DELETE:** server kiểm tra **lại** principal, owner/tenant, version, policy và trạng thái trong transaction phù hợp.

Một policy không tự động bảo đảm đồng bộ giữa hai HTTP request. Trong lúc client đang đọc màn hình, người khác có thể duyệt/hủy đơn hoặc quản trị viên có thể thu hồi vai trò. Đây là tình huống cần ETag và xử lý lỗi có điều kiện, không phải lý do để cố gắng khóa đơn trong suốt thời gian người dùng mở trang.

## 5. HAL links và Siren actions

Không phải mọi media type đều mô tả được method và payload. Chọn định dạng đúng nhu cầu:

| Biểu diễn | Điểm mạnh | Giới hạn |
|---|---|---|
| **HAL** (`application/hal+json`) | Quan hệ `_links` và tài nguyên nhúng `_embedded` | Link thông thường chỉ diễn tả quan hệ và `href`; không mặc định nêu method, body, precondition |
| **Siren** (`application/vnd.siren+json`) | Entity, link và `actions` có `name`, `method`, `href`, `type`, `fields` | Client phải hiểu Siren; action không thay thế authorization |
| **HAL-FORMS** | HAL kết hợp biểu mẫu/template để mô tả hành động | Cần thỏa thuận phần mở rộng và client hỗ trợ |
| **JSON:API links** | Tài nguyên và relationship links theo quy ước JSON:API | Link không tự mô tả mọi workflow command |
| **JSON tùy biến có availableActions** | Gọn trong một hệ sinh thái riêng | Phải tự định nghĩa method, relation, body, status, version, error và quy tắc tương thích |

### 5.1. HAL dành cho owner xem DRAFT

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: no-store
ETag: "order-o-17-v4"

{
  "id": "o-17",
  "status": "DRAFT",
  "_links": {
    "self": {"href": "/v1/orders/o-17"},
    "items": {"href": "/v1/orders/o-17/items"},
    "curies": [{
      "name": "ops",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    }],
    "ops:submit-order": {"href": "/v1/orders/o-17/submissions"},
    "ops:cancel-order": {"href": "/v1/orders/o-17/cancellations"}
  }
}
~~~

Ở đây `ops:submit-order` và `ops:cancel-order` là các extension relation được giải thích qua CURIE/URI. **HAL tự nó không tuyên bố POST phải được dùng.** Client phải dựa vào hợp đồng của relation/profile, OpenAPI hoặc một media type có mô tả affordance. Đừng gửi GET đến đường tạo approval chỉ vì nhìn thấy `href`.

### 5.2. Siren mô tả được thao tác

Response cho owner khi đơn DRAFT:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.siren+json
Cache-Control: no-store
ETag: "order-o-17-v4"

{
  "class": ["order"],
  "properties": {
    "id": "o-17", "status": "DRAFT", "version": 4
  },
  "links": [
    {"rel": ["self"], "href": "/v1/orders/o-17"},
    {"rel": ["items"], "href": "/v1/orders/o-17/items"}
  ],
  "actions": [
    {
      "name": "submit",
      "title": "Gửi duyệt",
      "method": "POST",
      "href": "/v1/orders/o-17/submissions",
      "type": "application/json",
      "fields": []
    },
    {
      "name": "cancel",
      "title": "Hủy đơn",
      "method": "POST",
      "href": "/v1/orders/o-17/cancellations",
      "type": "application/json",
      "fields": [{"name": "reason", "type": "text"}]
    }
  ]
}
~~~

Một response khi manager đủ quyền xem **SUBMITTED**:

~~~json
{
  "class": ["order"],
  "properties": {"id": "o-17", "status": "SUBMITTED", "version": 5},
  "links": [{"rel": ["self"], "href": "/v1/orders/o-17"}],
  "actions": [{
    "name": "approve",
    "title": "Duyệt đơn",
    "method": "POST",
    "href": "/v1/orders/o-17/approvals",
    "type": "application/json",
      "fields": [{
        "name": "expectedOrderVersion",
        "type": "number",
        "value": 5
      }]
  }]
}
~~~

Auditor có quyền đọc cùng resource có thể nhận `actions: []`. Người ngoài tenant nhận 404 thay vì một representation xác nhận đơn hiện hữu.

Ví dụ dùng POST tạo resource nghiệp vụ **submission/cancellation/approval**. Nếu action không cần body, hợp đồng có thể cho phép body rỗng; nếu biểu diễn `type=application/json` và có field, server phải định nghĩa chính xác JSON cần gửi. Không mặc định mọi lệnh workflow đều phải dùng các URI con này.

### 5.3. Lựa chọn media type

Nếu client chỉ cần **điều hướng** và biết trước cách gọi endpoint, HAL có thể đủ. Nếu client cần khám phá **method, trường nhập và hành động** ở runtime, Siren/HAL-FORMS phù hợp hơn. Có thể tự dùng trường JSON `availableActions` cho một ứng dụng riêng, miễn quy ước nhất quán và được tài liệu hóa.

Việc chọn hypermedia không loại bỏ OpenAPI hay tài liệu nghiệp vụ. Client vẫn cần hiểu ý nghĩa của các relation/action, xác thực, dữ liệu cần nhập, những kết quả và lỗi có thể xảy ra.

## 6. Trạng thái có thể đổi giữa khi đọc và khi bấm action

Hypermedia phản ánh **ảnh chụp trạng thái tại thời điểm GET**. Ví dụ:

~~~mermaid
sequenceDiagram
    participant O as Owner
    participant A as Order API
    participant M as Manager
    O->>A: GET /orders/o-17
    A-->>O: SUBMITTED, action cancel
    M->>A: POST /orders/o-17/approvals
    A-->>M: APPROVED
    Note over O: Màn hình vẫn còn nút Hủy
    O->>A: POST /orders/o-17/cancellations
    A-->>O: 409 Conflict, order đã APPROVED
    O->>A: GET /orders/o-17
    A-->>O: APPROVED, không còn cancel
~~~

Đây là dạng **time-of-check to time-of-use (TOCTOU)**: tại lúc xem đơn thì `cancel` được phép, nhưng trước lúc thực hiện thì điều kiện đã thay đổi. Không thể giải quyết triệt để bằng cách “ẩn nút thật nhanh”, bởi request mạng, quyền người dùng và database vẫn có thể thay đổi độc lập.

### 6.1. Xử lý đúng tại endpoint đích

Command handler nên:

1. Xác thực người gọi và lấy tenant/role/scope từ nguồn đáng tin.
2. Tìm đơn trong **phạm vi được phép nhìn thấy**; áp dụng 404 khi cần ẩn sự tồn tại.
3. Kiểm tra **quyền thực hiện thao tác**, bao gồm tách nhiệm vụ và quyền theo tổ chức.
4. Kiểm tra **trạng thái nghiệp vụ** của đơn ở thời điểm thực thi.
5. Kiểm soát cạnh tranh bằng transaction, khóa hoặc compare-and-set trên version.
6. Commit trạng thái mới và event/audit thích hợp, rồi trả HTTP status tương ứng.

Nếu điều kiện không còn thỏa, trả lỗi theo hợp đồng và để client **GET lại representation**. Không thực hiện lệnh chỉ vì “link được phát ở GET trước đó”.

### 6.2. Ranh giới transaction và thay đổi đồng thời

Ví dụ hai manager cùng thấy `approve` ở đơn SUBMITTED. Cả hai POST gần đồng thời. Nếu không kiểm soát, ứng dụng có thể tạo **hai approval record**, gửi thông báo hai lần hoặc chạy side effect tính tiền hai lần.

Một cách bảo vệ:

~~~text
POST approve(orderId, actor, expectedOrderVersion)
  -> xác thực và xác định tenant
  -> kiểm tra quyền duyệt, owner khác manager
  -> transaction:
       đọc/khóa đơn trong tenant
       xác minh status = SUBMITTED và version khớp
       chuyển trạng thái sang APPROVED, tăng version
       ghi approval record với unique constraint phù hợp
       ghi audit + outbox event
     commit
  -> 201 Created với Location của approval
~~~

Đặt **unique constraint** hoặc cơ chế idempotency ở mức business key để bảo vệ khỏi retry. Nếu request thứ hai đến sau khi đơn APPROVED, server không tự chạy workflow thêm lần nữa; có thể trả kết quả đã lưu nếu đúng một idempotency key, hoặc báo conflict nếu đó là ý định khác.

## 7. Preconditions: dùng ETag đúng resource

**ETag** là HTTP validator cho một representation. Trong GET đơn hàng, server có thể trả:

~~~http
GET /v1/orders/o-17 HTTP/1.1

HTTP/1.1 200 OK
ETag: "order-o-17-v5"
Content-Type: application/vnd.siren+json
~~~

Với thao tác cập nhật **chính URI của đơn**, `If-Match` là lựa chọn chuẩn để tránh ghi đè dữ liệu đã đổi:

~~~http
PATCH /v1/orders/o-17 HTTP/1.1
Authorization: Bearer <access-token>
If-Match: "order-o-17-v5"
Content-Type: application/merge-patch+json

{"description": "Mua thiết bị cho phòng lab"}
~~~

Nếu validator không khớp representation hiện tại, server trả **412 Precondition Failed**. Nếu API yêu cầu gửi `If-Match` nhưng client không gửi, có thể trả **428 Precondition Required**. `If-Match` dùng so sánh **strong validator**; không dùng weak ETag để kỳ vọng so khớp theo điều kiện này.

### 7.1. Đừng dùng ETag của resource cha như điều kiện tự động cho URI khác

Với **POST /v1/orders/o-17/approvals**, target URI là **collection approvals**, không phải `/v1/orders/o-17`. Theo semantics HTTP, `If-Match` là tiền điều kiện trên **target resource của request**. Vì vậy **không mặc định** gửi ETag lấy từ GET order làm `If-Match` của POST approvals rồi suy ra được bảo vệ version của order.

Có hai thiết kế hợp lệ tùy hợp đồng:

| Thiết kế | Cơ chế chống stale state | Mã lỗi điển hình |
|---|---|---|
| **PATCH vào chính /orders/{id}** với thay đổi được phép | `If-Match` so với ETag của Order, xử lý trạng thái và quyền trong transaction | **412** khi validator không khớp |
| **POST /orders/{id}/approvals** để tạo action resource | Request chứa `expectedOrderVersion` hoặc điều kiện nghiệp vụ được định nghĩa riêng; server CAS version của Order | **409** nếu version/trạng thái đã đổi theo hợp đồng |

Ví dụ POST có version trong body:

~~~http
POST /v1/orders/o-17/approvals HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: approve-o17-req82

{"expectedOrderVersion": 5}

HTTP/1.1 201 Created
Location: /v1/orders/o-17/approvals/ap-82
Content-Type: application/json

{"id":"ap-82","orderId":"o-17","status":"APPROVED"}
~~~

**expectedOrderVersion** và **Idempotency-Key** ở đây là quy ước riêng của API. Cả hai phải được kiểm tra và lưu/so sánh trong transaction phù hợp. Với Siren action, có thể mô tả `expectedOrderVersion` như một field số hoặc cung cấp tài liệu relation/action hướng dẫn client gửi giá trị.

### 7.2. Một representation có link phụ thuộc quyền cũng cần validator phù hợp

Giả sử hai người thấy cùng Order status=SUBMITTED nhưng chỉ manager có `approve`. Nếu ETag chỉ được tạo từ version của Order, nó có thể **giống nhau** cho hai representation khác nội dung action. Khi dùng conditional GET hoặc cache, điều này dễ dẫn tới kết quả lỗi.

ETag của **representation phụ thuộc quyền** cần phản ánh **representation thực tế** và ngữ cảnh mà validator có hiệu lực. Có thể tính validator từ version order cùng version/quy tắc quyền, hoặc từ các byte representation được chuẩn hóa khi thiết kế cho phép. Không dùng cùng một validator mạnh cho hai representation khác nội dung theo cách khiến cache hoặc `304 Not Modified` tái dùng nhầm các action.

## 8. Cấu trúc API thao tác theo workflow

Các action ví dụ được mô hình hóa như resource kết quả:

~~~text
GET  /v1/orders/{orderId}                       # đọc Order
GET  /v1/orders/{orderId}/items                 # đọc mặt hàng
POST /v1/orders/{orderId}/submissions           # gửi duyệt
POST /v1/orders/{orderId}/approvals             # duyệt
POST /v1/orders/{orderId}/cancellations         # hủy
GET  /v1/orders/{orderId}/approvals/{approvalId} # xem biên bản duyệt
~~~

POST có thể tạo record nghiệp vụ và cập nhật trạng thái Order. Nhưng **không phải mọi chuyển trạng thái đều cần tạo một endpoint động từ riêng**. Nếu nghiệp vụ chỉ cần sửa một thuộc tính với quyền rõ ràng, PATCH trên Order có thể thích hợp. Chọn mô hình theo **danh tính resource, tính nhất quán, audit và vòng đời** thay vì cố ép một quy ước vào mọi hệ thống.

### 8.1. Hợp đồng HTTP

| Tình huống | Mã phù hợp | Điều client cần hiểu |
|---|---|---|
| GET resource đang hiển thị | **200 OK** | Body chứa trạng thái và action hiện có |
| Thiếu credential hợp lệ khi endpoint bắt buộc xác thực | **401 Unauthorized** | Có challenge `WWW-Authenticate` thích hợp |
| Không được xem resource hoặc muốn che giấu sự tồn tại | **404 Not Found** | Không suy đoán ID có tồn tại hay không |
| Được xem nhưng không có quyền duyệt | **403 Forbidden** | Không được thực hiện hành động dù biết URI |
| Có quyền nhưng đơn không còn ở SUBMITTED | **409 Conflict** | Xung đột trạng thái nghiệp vụ; GET lại để cập nhật |
| `If-Match` trên target resource không đạt | **412 Precondition Failed** | Representation đã đổi so với validator |
| Thiếu precondition bắt buộc | **428 Precondition Required** | Gửi điều kiện theo hợp đồng |
| Tạo approval record thành công | **201 Created** | Có `Location` của resource mới |
| Command thành công và không có representation cần trả | **204 No Content** | Không có response body |
| Tác vụ được nhận để xử lý bất đồng bộ | **202 Accepted** | Có operation/status resource để theo dõi, không tuyên bố đã duyệt xong |

Đối với yêu cầu hợp lệ nhưng bị từ chối vì **điều kiện đầu vào nghiệp vụ** (ví dụ lý do hủy sai quy tắc), có thể dùng 400 hoặc 422 theo hợp đồng. Không trả 200 với body `{"success":false}` để che giấu HTTP failure, và không mặc định dùng 404 chỉ vì action không xuất hiện trong response GET.

### 8.2. Idempotency cho action có side effect

Người dùng có thể gửi duyệt, nhận timeout rồi bấm lại. Đối với POST tạo approval, giữ **Idempotency-Key** ổn định cho cùng ý định, lưu fingerprint của request, principal/scope, trạng thái thực thi và kết quả. Retry cùng key/payload trong thời hạn lưu nên trả kết quả tương ứng **mà không tạo approval thứ hai**. Cùng key nhưng payload khác phải bị từ chối theo hợp đồng.

Nếu action gửi email, ghi audit hoặc thông báo downstream, cần bảo vệ **side effect** bằng transaction/outbox và consumer idempotent. Việc Order đổi sang APPROVED chỉ một lần không tự bảo đảm email chỉ được gửi một lần.

Không nên gửi POST tự động chỉ vì client phát hiện link mới. Action duyệt, thanh toán, xóa phải xuất phát từ **ý định người dùng hoặc quy trình được ủy quyền**, có xử lý retry giới hạn và xác nhận phù hợp.

## 9. Bảo mật: link có điều kiện không thay thế phân quyền

### 9.1. Không tiết lộ tài nguyên của tenant khác

Không được lấy Order bằng ID trên toàn database rồi phát link trước khi kiểm tra principal. Một truy vấn đọc có thể giới hạn:

~~~sql
SELECT o.*
FROM orders o
WHERE o.id = :orderId
  AND o.tenant_id = :authenticatedTenantId
  AND (
      o.created_by = :principalId
      OR :hasTenantManagerReadPermission = TRUE
      OR :hasTenantAuditReadPermission = TRUE
  );
~~~

Các biến permission ở ví dụ phải đến từ **policy đáng tin cậy**, không lấy Boolean tự do do client gửi. Với hệ thống lớn, điều kiện quyền có thể nằm ở access-control service hoặc row-level security, nhưng hiệu ứng cuối cùng phải giống nhau: **chỉ tạo representation và link từ những resource người gọi được quyền thấy**.

### 9.2. Kiểm tra quyền thao tác chi tiết

Server phải đánh giá đồng thời:

- **Identity:** token/phiên hợp lệ, principal và tenant được xác minh.
- **Resource scope:** Order đúng tenant, đúng parent; không dùng ID biết được làm quyền.
- **Action permission:** manager có quyền approve hay chỉ được xem; owner có thể cancel trong điều kiện nào.
- **Separation of duties:** người tạo không được tự duyệt nếu chính sách yêu cầu.
- **Business invariant:** trạng thái cho phép chuyển tiếp, hạn mức/đóng sổ, dữ liệu đầy đủ.
- **Concurrency:** thao tác không dùng phiên bản cũ hoặc phá vỡ trạng thái do race.

**Link bị ẩn** không chặn người khác gọi thẳng endpoint. Ngược lại, **link xuất hiện** không chứng minh người gọi còn quyền khi request tới server. Do đó, authorization bắt buộc ở route/service; kiểm tra một lần lúc sinh hypermedia chỉ nhằm hướng dẫn UX.

### 9.3. Bản thân sự xuất hiện của link có thể là dữ liệu nhạy cảm

Một action `refund` có thể làm lộ đơn đã thanh toán; link `review-fraud` có thể lộ trạng thái kiểm tra gian lận; `users/{id}/suspend` có thể tiết lộ role quản trị. Vì vậy, **không chỉ ẩn data field**, mà cả link, action title, relation, form value và URI đích phải tuân thủ chính sách tiết lộ.

Khi người gọi không có quyền biết một order tồn tại, response 404 cần trung tính; không trả `actions: []` kèm `id` thật, không sinh `Location`, ETag hoặc link dẫn tới tài nguyên bị che giấu.

### 9.4. Link không phải credential

Một URI thông thường không tự cấp quyền. Client phải gửi credential qua cách thức thích hợp; kiểm tra CSRF với phiên dựa trên cookie, kiểm soát CORS đúng nguồn và áp rate limit cho command nguy hiểm. Nếu dùng **signed action URL** có token trong đường dẫn, đó là cơ chế cấp khả năng truy cập đặc biệt với rủi ro rò qua log/referrer/history; phải thiết kế hạn dùng, phạm vi, thu hồi, bảo vệ bí mật và replay rõ ràng. Không đưa access token hoặc dữ liệu nhạy cảm vào `href` chỉ để tiện cho frontend.

### 9.5. URI và reverse proxy

Không tạo link tuyệt đối một cách mù quáng từ header `Host` hoặc `X-Forwarded-Host` chưa được kiểm soát: kẻ tấn công có thể thao túng host để sinh link độc hại. Dùng base URL được cấu hình, trusted proxy headers và HTTPS; hoặc dùng relative links khi hợp đồng và client cho phép. Client theo link ngoài domain cần chính sách tin cậy phù hợp, nhất là với client backend để tránh SSRF.

## 10. Cache và thay đổi quyền

Hypermedia phụ thuộc trạng thái **và principal** nên rất dễ gặp lỗi cache: hai người gọi cùng một URI có thể nhận các action khác nhau; cùng một người có thể bị thu hồi role ngay sau khi GET.

| Dạng response | Hướng xử lý cache | Rủi ro nếu cấu hình sai |
|---|---|---|
| Order có action theo owner/role | `Cache-Control: no-store` là lựa chọn thận trọng | Shared cache có thể phát `approve` của manager cho owner |
| Tài nguyên công khai chỉ chứa link điều hướng chung | Có thể dùng `public` cùng TTL phù hợp | Client tiếp tục dùng link cũ nếu resource chuyển trạng thái |
| Representation theo người dùng, không nhạy cảm và chấp nhận cache cá nhân | `private` + max-age ngắn, cơ chế invalidation | Quyền đã thu hồi nhưng client hiển thị action cũ |
| Response có conditional GET | ETag/Last-Modified phải đúng phiên bản representation | `304` khiến client tái dùng action theo quyền cũ |
| Resource thay đổi bởi command | Trả representation hoặc link để GET lại | UI không đồng bộ trạng thái vừa commit |

**Vary: Authorization** không tự bảo đảm mọi CDN phân tách đúng quyền. Với dữ liệu riêng tư, nên tránh shared caching trừ khi có thiết kế cache key, invalidation và kiểm thử rõ ràng. `Cache-Control: no-store` giúp ngăn lưu response theo chỉ thị cache, nhưng **không thay thế kiểm tra quyền**: client có thể giữ UI đã render hoặc dùng response trước đó.

### 10.1. Có cần push action mới ngay lập tức?

Không nhất thiết. Với UI đơn giản, client GET lại sau command thành công; với hệ thống realtime, có thể nhận sự kiện hoặc notification rồi GET lại representation. **Push event chỉ báo cần đồng bộ**, không tự làm authorization của client có hiệu lực vĩnh viễn.

Nếu quyền hoặc trạng thái thay đổi ngay khi người dùng đang ở màn hình, action có thể vẫn hiển thị cho đến lần GET sau. Đó là trường hợp bình thường; client phải xử lý **403/409/412** và cập nhật UX khi server từ chối.

## 11. Java/Spring: tách policy, assembler và command handler

Ví dụ triển khai dùng **Java 17+, Spring Boot 3, Spring Security và Spring HATEOAS**. Những đoạn mã sau minh họa ranh giới trách nhiệm; để chạy thành một ứng dụng hoàn chỉnh cần bổ sung import, entity, repository, DTO, mapper, cấu hình JWT, security filter, transaction và test fixture. Không nên copy một đoạn lẻ rồi cho rằng ứng dụng đã an toàn.

### 11.1. Mô hình dữ liệu và diễn giải người gọi

~~~java
enum OrderStatus {
    DRAFT, SUBMITTED, APPROVED, CANCELLED
}

record Actor(
    String userId,
    String tenantId,
    Set<String> permissions
) {
    boolean can(String permission) {
        return permissions.contains(permission);
    }
}

record OrderView(
    String id,
    OrderStatus status,
    String totalAmount,
    long version
) {}
~~~

`Actor` phải được dựng từ **identity đã xác thực** và các permission **được chứng thực hoặc tra cứu từ nguồn có thẩm quyền**. Không lấy `tenantId` hoặc danh sách quyền từ query parameter/body để tự cấp quyền cho người gọi. Nếu quyền có thể thu hồi tức thì, không nên tin mãi permission trong token cũ; cần chiến lược xác minh, TTL hoặc invalidation thích hợp.

### 11.2. Policy rõ điều kiện trạng thái và vai trò

~~~java
@Component
class OrderPolicy {
    boolean canView(Actor actor, OrderEntity order) {
        if (!actor.tenantId().equals(order.getTenantId())) {
            return false;
        }
        return actor.userId().equals(order.getCreatedBy())
            || actor.can("orders.read.all")
            || actor.can("orders.audit");
    }

    boolean canReadItems(Actor actor, OrderEntity order) {
        return canView(actor, order)
            && actor.can("orders.items.read");
    }

    boolean canSubmit(Actor actor, OrderEntity order) {
        return canView(actor, order)
            && actor.userId().equals(order.getCreatedBy())
            && actor.can("orders.submit")
            && order.getStatus() == OrderStatus.DRAFT;
    }

    boolean canCancel(Actor actor, OrderEntity order) {
        return canView(actor, order)
            && actor.userId().equals(order.getCreatedBy())
            && actor.can("orders.cancel")
            && (
                order.getStatus() == OrderStatus.DRAFT
                || order.getStatus() == OrderStatus.SUBMITTED
            );
    }

    boolean canApprove(Actor actor, OrderEntity order) {
        return canView(actor, order)
            && actor.can("orders.approve")
            && !actor.userId().equals(order.getCreatedBy())
            && order.getStatus() == OrderStatus.SUBMITTED;
    }
}
~~~

Ví dụ buộc `canView` trước khi thêm action để không làm lộ resource ngoài tenant. Trong thực tế, role/permission có thể khác; manager chỉ được duyệt đơn ở phòng ban hoặc hạn mức nhất định. Những điều kiện ấy nên nằm trong policy và được kiểm tra lại trong transaction thực thi.

### 11.3. Assembler tạo HAL link có điều kiện

~~~java
@Component
class OrderRepresentationAssembler {
    private final OrderPolicy policy;

    OrderRepresentationAssembler(OrderPolicy policy) {
        this.policy = policy;
    }

    EntityModel<OrderView> toModel(
            OrderEntity order, Actor actor, OrderView view) {
        String base = "/v1/orders/" + order.getId();

        EntityModel<OrderView> model = EntityModel.of(view);
        model.add(Link.of(base).withSelfRel());

        if (policy.canReadItems(actor, order)) {
            model.add(Link.of(base + "/items").withRel("items"));
        }
        if (policy.canSubmit(actor, order)) {
            model.add(Link.of(base + "/submissions")
                .withRel("https://api.example.com/rels/submit-order"));
        }
        if (policy.canCancel(actor, order)) {
            model.add(Link.of(base + "/cancellations")
                .withRel("https://api.example.com/rels/cancel-order"));
        }
        if (policy.canApprove(actor, order)) {
            model.add(Link.of(base + "/approvals")
                .withRel("https://api.example.com/rels/approve-order"));
        }
        return model;
    }
}
~~~

Spring HATEOAS cung cấp `EntityModel` và `Link` để biểu diễn resource và link relation. Ví dụ dùng link tương đối nhằm tránh phụ thuộc host; **relation URI mở rộng phải có tài liệu ngữ nghĩa**. Đoạn này tạo **HAL links**, chưa mô tả method/fields như Siren actions. Nếu dùng Siren thực sự, hãy xây assembler/serializer Siren hoặc affordance tương ứng theo thư viện đã chọn, kiểm tra media type đầu ra.

### 11.4. Controller chỉ phục vụ resource được quyền xem

~~~java
@RestController
@RequestMapping("/v1/orders")
class OrderQueryController {
    private final OrderReadService orders;
    private final OrderRepresentationAssembler assembler;
    private final ActorFactory actors;

    OrderQueryController(
            OrderReadService orders,
            OrderRepresentationAssembler assembler,
            ActorFactory actors) {
        this.orders = orders;
        this.assembler = assembler;
        this.actors = actors;
    }

    @GetMapping(
        path = "/{id}",
        produces = "application/hal+json"
    )
    ResponseEntity<EntityModel<OrderView>> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        Actor actor = actors.fromVerifiedJwt(jwt);
        OrderEntity order = orders.findVisibleOrder(actor, id);
        OrderView view = orders.toView(order);

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(assembler.toModel(order, actor, view));
    }
}
~~~

`findVisibleOrder` phải đối chiếu tenant/owner và chính sách đọc, trả 404 trung tính khi ID không tồn tại hoặc bị ẩn theo hợp đồng. Ở ví dụ này **không tạo ETag chỉ từ version của Order**, bởi action phụ thuộc principal và permission. Khi hỗ trợ conditional GET cần một validator biểu diễn đúng biến thể theo quyền như đã nêu ở Mục 7.

### 11.5. Command handler không tin action đã hiển thị

~~~java
record ApproveOrderRequest(long expectedOrderVersion) {}

@RestController
@RequestMapping("/v1/orders/{orderId}/approvals")
class OrderApprovalController {
    private final OrderCommandService commands;
    private final ActorFactory actors;

    OrderApprovalController(
            OrderCommandService commands,
            ActorFactory actors) {
        this.commands = commands;
        this.actors = actors;
    }

    @PostMapping
    ResponseEntity<ApprovalView> approve(
            @PathVariable String orderId,
            @Valid @RequestBody ApproveOrderRequest request,
            @RequestHeader("Idempotency-Key") String key,
            @AuthenticationPrincipal Jwt jwt) {

        Actor actor = actors.fromVerifiedJwt(jwt);
        ApprovalView result = commands.approve(
            actor, orderId, request.expectedOrderVersion(), key
        );
        URI location = URI.create(
            "/v1/orders/" + orderId + "/approvals/" + result.id()
        );
        return ResponseEntity.created(location)
            .cacheControl(CacheControl.noStore())
            .body(result);
    }
}
~~~

Controller **không được** chấp nhận một flag `canApprove=true` do client gửi để bỏ qua policy. Service cần chống replay và race:

~~~text
approve(actor, orderId, expectedVersion, idempotencyKey):
    validateAuthenticatedPrincipal(actor)
    validateIdempotencyKeyScopeAndPayload(...)
    transaction:
        order = readOrderWithinTenantForUpdate(orderId, actor.tenantId)
        if order absent or not visible: 404
        if not policy.canApprove(actor, order): 403 hoặc 409
            # 403 nếu thiếu quyền; 409 nếu có quyền nhưng sai trạng thái
        if order.version != expectedVersion: 409 STALE_ORDER
        createApprovalRecordOnce(...)
        updateOrderStatus(APPROVED) and incrementVersion(...)
        insertAuditAndOutboxRecords(...)
        storeIdempotentOutcome(...)
    return persistedApproval
~~~

Trình tự thực tế cần phân biệt **lỗi quyền** với **lỗi trạng thái** trước khi chọn 403/409; pseudocode cho thấy chỗ đặt kiểm tra chứ không gộp hai lỗi thành một. **Idempotency record** cần được điều phối nhất quán với transaction để cùng key không tạo hai approval; không chỉ lưu kết quả trong cache memory. Một command xử lý lâu hoặc gọi hệ thống bên ngoài có thể cần operation resource và trạng thái `202 Accepted` thay vì giữ kết nối HTTP.

### 11.6. Map exception theo Problem Details

~~~java
@RestControllerAdvice
class OrderProblemHandler {
    @ExceptionHandler(OrderStateConflictException.class)
    ResponseEntity<ProblemDetail> stateConflict() {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Trạng thái đơn đã thay đổi; hãy tải lại đơn."
        );
        p.setType(URI.create(
            "https://api.example.com/problems/order-state-conflict"
        ));
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

Trong ứng dụng thật, bổ sung handler cho missing precondition, validation, lỗi idempotency và resource bị ẩn. Lớp bảo mật xử lý 401/403 phù hợp; không tiết lộ owner, tenant hoặc role nội bộ trong body lỗi công khai. Hợp đồng `application/problem+json` theo **RFC 9457** giúp client xử lý bằng `type`/`status` thay vì parse thông điệp tiếng Việt.

## 12. Client hypermedia: tìm action thay vì tự đoán đường đi

Một client có thể có trình tự:

~~~mermaid
flowchart LR
    A["GET Order"] --> B["Đọc status và actions"]
    B --> C{"Có action approve?"}
    C -->|Có| D["Hiện nút Duyệt"]
    C -->|Không| E["Ẩn/khóa chức năng duyệt"]
    D --> F["Người dùng xác nhận"]
    F --> G["POST đúng href, body, auth"]
    G --> H{"Thành công?"}
    H -->|Có| I["GET lại Order"]
    H -->|403/409/412| J["Hiển thị thay đổi và GET lại"]
~~~

Client **không nên** tự suy ra “manager luôn có nút approve” hoặc tự tạo `/orders/{id}/approvals` từ ID khi representation không còn action. Đồng thời client phải biết ý nghĩa action để hiển thị hợp lý: relation giúp giảm coupling với URL, nhưng **không tự thay thế kiến thức về nghiệp vụ**.

### 12.1. Pseudocode theo Siren

~~~javascript
async function renderOrder(orderUrl) {
  const response = await apiGet(orderUrl);
  const entity = await response.json();

  const approve = (entity.actions ?? [])
    .find(action => action.name === "approve");

  approveButton.hidden = !approve;
  if (approve) {
    approveButton.onclick = async () => {
      const expectedOrderVersion = entity.properties.version;
      const result = await apiPost(approve.href, {
        expectedOrderVersion
      }, { idempotencyKey: getOrCreateKeyForThisIntent() });

      if (result.status === 409 || result.status === 403) {
        showMessage("Đơn hoặc quyền đã thay đổi.");
      } else if (!result.ok) {
        showMessage("Không thể hoàn tất yêu cầu.");
      }
      await renderOrder(orderUrl);
    };
  }
}
~~~

Đây là **pseudocode frontend**, cần bổ sung xác thực, chống CSRF khi dùng cookie, timeout, xử lý mạng và quản lý state thực tế. `getOrCreateKeyForThisIntent()` phải trả **cùng key khi retry cùng một ý định**, nhưng tạo key khác cho ý định mới; tránh mỗi lần click do timeout lại tạo một key khác vô tình nhân side effect.

### 12.2. Nếu client chưa hiểu action mới?

Client nên bỏ qua **relation/action chưa biết** một cách an toàn, thay vì cố đoán method hoặc thực thi tự động. Với action đã hiểu nhưng không xuất hiện, UI có thể ẩn nút hoặc hiển thị lý do chung; lý do thiếu action **không được suy ra là chắc chắn thiếu role**, vì cũng có thể do trạng thái nghiệp vụ, tenant, giới hạn hoặc chính sách khác.

Nếu sản phẩm cần giải thích **vì sao không được làm**, có thể cung cấp một capability/eligibility endpoint được **phân quyền rõ** hoặc một danh sách lý do an toàn. Đừng đưa thông báo chi tiết chứa thông tin nhạy cảm vào tất cả response chỉ để làm nút disabled trông rõ hơn.

### 12.3. Thiết kế client cho nhiều thiết bị và phiên bản

Hypermedia giúp server thay đổi URL đích hoặc giới thiệu thao tác mới mà không bắt client dựng path cứng. Nhưng khả năng tương thích còn phụ thuộc:

- Relation/action name có giữ cùng ngữ nghĩa khi đổi URL không?
- Client có hỗ trợ media type và schema của form mới?
- Khi action bị rút, client có xử lý thiếu action mà không crash không?
- Có xác định được trạng thái cuối và đường đọc lại sau command không?
- Client cũ gặp action không hỗ trợ có bỏ qua an toàn không?

**Không thay đổi ý nghĩa của một relation đã công bố**. Nếu command thay đổi semantics lớn hoặc payload không còn tương thích, dùng version/profile/rel mới hoặc chiến lược migration rõ ràng.

## 13. Hợp đồng OpenAPI và tài liệu relation

Hypermedia trả về **ở runtime**, còn OpenAPI mô tả trước **URI, method, schema, response và lỗi**. Client đọc Siren để biết action nào đang có; khi hiểu action `approve`, client vẫn cần hợp đồng về payload và kết quả. Hai hình thức tài liệu hỗ trợ nhau.

| Nội dung | Phần phải mô tả |
|---|---|
| Media type | `application/vnd.siren+json` hay `application/hal+json`; content negotiation |
| Relation/action | Ý nghĩa của `self`, `items`, `submit`, `cancel`, `approve` |
| Điều kiện hiện diện | Trạng thái, role, owner, tenant, yêu cầu nghiệp vụ |
| Thao tác | HTTP method, target URI, content type, field và precondition |
| Idempotency | `Idempotency-Key`, phạm vi và thời hạn, xử lý retry trùng |
| Kết quả/lỗi | 200/201/202/204, 401/403/404/409/412/428, `Location` |
| Cache | `Cache-Control`, scope, ETag của representation theo quyền |
| Tương thích | Relation/profile version, khả năng action mới bị client cũ bỏ qua |

Các `links` của OpenAPI có thể mô tả quan hệ **giữa các operations tại thời điểm thiết kế**; chúng không thay thế những action đã được tính theo trạng thái và principal trong response thực tế.

### 13.1. Ví dụ OpenAPI 3.1 rút gọn

~~~yaml
openapi: 3.1.0
info:
  title: Orders Hypermedia API
  version: 1.0.0
paths:
  /v1/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Đọc đơn và action phù hợp người gọi
      description: >
        Response Siren chỉ giới thiệu action hợp lệ tại thời điểm GET.
        Mọi command đều kiểm tra lại quyền và trạng thái.
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/orderId"
      responses:
        "200":
          description: Đơn hàng được phép xem
          content:
            application/vnd.siren+json:
              schema:
                $ref: "#/components/schemas/OrderSiren"
        "401":
          description: Xác thực thiếu hoặc không hợp lệ
          headers:
            WWW-Authenticate:
              schema:
                type: string
        "404":
          description: Đơn không có hoặc không được phép tiết lộ
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
  /v1/orders/{orderId}/approvals:
    post:
      operationId: approveOrder
      summary: Tạo quyết định duyệt đơn
      description: >
        Manager đủ quyền, không phải người tạo, có thể duyệt
        đơn SUBMITTED; yêu cầu version và idempotency key.
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/orderId"
        - name: Idempotency-Key
          in: header
          required: true
          schema:
            type: string
            minLength: 1
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [expectedOrderVersion]
              properties:
                expectedOrderVersion:
                  type: integer
                  format: int64
                  minimum: 0
      responses:
        "201":
          description: Đã tạo approval và cập nhật đơn
          headers:
            Location:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Approval"
        "401":
          description: Credential không hợp lệ
        "403":
          description: Không có quyền duyệt
        "404":
          description: Order không có hoặc không được tiết lộ
        "409":
          description: Sai trạng thái, version hoặc xung đột idempotency
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
components:
  parameters:
    orderId:
      name: orderId
      in: path
      required: true
      schema:
        type: string
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    OrderSiren:
      type: object
      required: [class, properties, links]
      properties:
        class:
          type: array
          items:
            type: string
        properties:
          type: object
          properties:
            id:
              type: string
            status:
              type: string
              enum: [DRAFT, SUBMITTED, APPROVED, CANCELLED]
            version:
              type: integer
        links:
          type: array
          items:
            type: object
            required: [rel, href]
            properties:
              rel:
                type: array
                items:
                  type: string
              href:
                type: string
                format: uri-reference
        actions:
          type: array
          items:
            type: object
            required: [name, method, href]
            properties:
              name:
                type: string
                enum: [submit, cancel, approve]
              method:
                type: string
                enum: [POST]
              href:
                type: string
                format: uri-reference
              fields:
                type: array
                items:
                  type: object
    Approval:
      type: object
      required: [id, orderId, status]
      properties:
        id:
          type: string
        orderId:
          type: string
        status:
          type: string
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
        detail:
          type: string
~~~

Ví dụ mô tả **biến thể Siren**. Nếu ứng dụng dùng HAL, phải đổi media type/schema. Khi triển khai thật cần bổ sung chi tiết `submit`/`cancel`, schema field Siren theo profile áp dụng, giới hạn body, mã lỗi, bảo mật và kiểm thử contract. OpenAPI không thể tự suy ra role của principal đang gọi và loại bỏ action ở runtime.

### 13.2. Tài liệu relation/action để client hiểu method

~~~text
Relation: https://api.example.com/rels/approve-order
Ý nghĩa: Duyệt một Order ở trạng thái SUBMITTED.
Method: POST
Target: URI do response cung cấp.
Content-Type: application/json
Payload: expectedOrderVersion từ Order được xem.
Header: Idempotency-Key
Kết quả: 201, 401, 403, 404, 409
Sau thành công: GET Order mới để đọc action hiện tại.
~~~

Tài liệu này đặc biệt hữu ích với HAL vì HAL link không tự mang method/fields. Với Siren, nó bổ sung ý nghĩa nghiệp vụ, validation và lỗi. **Giữ nguyên ngữ nghĩa của relation** khi đổi URL; nếu semantics thay đổi lớn, cần relation/profile mới hoặc migration client được hoạch định.

## 14. Hypermedia cho collection và phân trang

Collection có thể trả `self`, `next`, `prev` và link tới từng resource:

~~~json
{
  "class": ["orders", "collection"],
  "entities": [
    {"rel": ["item"], "href": "/v1/orders/o-17"},
    {"rel": ["item"], "href": "/v1/orders/o-18"}
  ],
  "links": [
    {
      "rel": ["self"],
      "href": "/v1/orders?status=SUBMITTED&limit=2"
    },
    {
      "rel": ["next"],
      "href": "/v1/orders?status=SUBMITTED&limit=2&cursor=opaque"
    }
  ]
}
~~~

Client nên theo `next` do server phát thay vì tự ghép offset hoặc cursor. Server vẫn kiểm tra cursor **đúng filter, sort, tenant, principal/scope và thời hạn**. Một cursor đã xuất hiện trong response trước không bảo đảm người dùng còn quyền ở lần gọi tiếp theo.

Không nên phát `approve` cho mọi order trong collection chỉ vì người gọi có role MANAGER. Mỗi order có **owner và state khác nhau**; có thể tính policy cho từng entity rồi nhúng action hợp lệ. Với collection lớn, kiểm tra permission từng item có thể tạo **N+1 queries**; cân nhắc batch policy evaluation, projection theo database và limit hợp lý.

Nếu collection nhúng Order hay thuộc tính con (`entities` hoặc `_embedded`), những field/action đó cũng phải tuân theo quyền. Có quyền liệt kê đơn **không đồng nghĩa** được xem giá nhạy cảm, lịch sử duyệt hoặc được duyệt tất cả đơn.

### 14.1. Thay đổi giữa các trang

Cursor ổn định giúp tiếp tục theo khóa sắp xếp, **không đóng băng quyền hoặc trạng thái**. Người dùng có thể thấy link `approve` ở trang trước, nhưng đơn đã APPROVED ở trang sau. Không lưu một danh sách action rồi tái dùng vô hạn cho toàn workflow.

## 15. Kiểm thử link phụ thuộc quyền và trạng thái

Một API có thể trả đúng **200** và đúng JSON nhưng vẫn sai nếu action `approve` xuất hiện với owner hoặc biến mất với manager đủ quyền. Cần kiểm tra cả **representation** lẫn **việc endpoint chặn gọi trực tiếp**. Test chỉ xác minh “nút Duyệt bị ẩn” không đủ bảo mật.

### 15.1. Ma trận test theo principal và trạng thái

| Ca | Ngữ cảnh | Kỳ vọng GET | Kỳ vọng gọi command |
|---|---|---|---|
| H01 | Owner, đơn DRAFT | Có `submit` và `cancel`, không có `approve` | Submit hợp lệ, approve bị từ chối |
| H02 | Manager, đơn DRAFT | Không có `approve` | POST approve bị từ chối vì sai trạng thái |
| H03 | Owner, đơn SUBMITTED | Có `cancel`, không có `approve` | POST approve bị chặn |
| H04 | Manager khác người tạo, SUBMITTED | Có `approve` | POST approve đúng version tạo kết quả theo hợp đồng |
| H05 | Manager đồng thời là người tạo, SUBMITTED | Không có `approve` | POST approve bị chặn theo separation of duties |
| H06 | Auditor, SUBMITTED | Chỉ các link đọc được phép | POST approve bị 403/404 theo visibility policy |
| H07 | Manager, APPROVED | Không còn `approve` | POST approve khác key không tạo duyệt thứ hai |
| H08 | Owner, CANCELLED | Không có action chuyển trạng thái | POST submit/cancel bị từ chối |
| H09 | Người của tenant khác biết orderId | 404 trung tính, không có representation | Command không làm lộ order |
| H10 | Người chưa xác thực | 401 và `WWW-Authenticate` | Command yêu cầu auth |
| H11 | User có quyền đọc nhưng thiếu quyền đọc items | Không có link `items` | GET items vẫn phải kiểm tra quyền |
| H12 | Role bị thu hồi sau GET | GET mới bỏ action | POST bằng href cũ bị từ chối |
| H13 | Order chuyển trạng thái sau GET | Link màn hình có thể cũ | POST trả 409 hoặc lỗi precondition thích hợp |
| H14 | Gửi lại cùng Idempotency-Key sau timeout | Response theo hợp đồng replay | Chỉ một approval và side effect nghiệp vụ |
| H15 | Cùng key nhưng request body khác | Không xử lý thêm | Lỗi idempotency được tài liệu hóa |
| H16 | Conditional GET trong ngữ cảnh quyền khác | Không tái dùng nhầm action của principal khác | Validator/cache isolation đúng |
| H17 | Response dùng Siren | `method`, `href`, `fields` đúng action được phát | Client gửi đúng payload và content type |
| H18 | Response dùng HAL | Các rel/href hợp lệ theo HAL | Client tra relation docs để biết POST |

**H04 và H05 quan trọng:** cùng role “manager” không đủ để quyết định action; cần xét **người tạo đơn**. **H12 và H13** kiểm chứng khoảng cách giữa đọc và ghi, vốn là rủi ro chính của hypermedia động.

### 15.2. Ví dụ MockMvc cho Siren action

Giả sử hệ thống đã triển khai Siren response và fixture có hai tài khoản trong tenant-a, order SUBMITTED thuộc user-7. Các import và helper seed được lược bớt:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderHypermediaContractTest {
    @Autowired MockMvc mvc;

    String submittedOrderId; // fixture thuộc user-7

    @Test
    void managerGetsApproveAction() throws Exception {
        mvc.perform(
                get("/v1/orders/{id}", submittedOrderId)
                    .accept("application/vnd.siren+json")
                    .with(jwt().jwt(j -> j
                        .subject("manager-2")
                        .claim("tenant_id", "tenant-a")
                    ))
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.actions[*].name",
                hasItem("approve")));
    }

    @Test
    void ownerDoesNotGetApproveAction() throws Exception {
        mvc.perform(
                get("/v1/orders/{id}", submittedOrderId)
                    .accept("application/vnd.siren+json")
                    .with(jwt().jwt(j -> j
                        .subject("user-7")
                        .claim("tenant_id", "tenant-a")
                    ))
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.actions[*].name",
                not(hasItem("approve"))));
    }

    @Test
    void foreignTenantCannotDiscoverOrder() throws Exception {
        mvc.perform(
                get("/v1/orders/{id}", submittedOrderId)
                    .with(jwt().jwt(j -> j
                        .subject("outsider")
                        .claim("tenant_id", "tenant-b")
                    ))
            )
            .andExpect(status().isNotFound());
    }
}
~~~

**Mã trên chỉ minh họa test**, cần cấu hình principal có quyền manager/owner/auditor đúng theo policy trong fixture hoặc authorities. `jwt()` của Spring Security Test có thể dựng principal thử mà **không xác minh chữ ký token thật**. Do đó phải có test bảo mật tích hợp với token thiếu, sai issuer/audience, hết hạn, bị thu hồi hoặc claim thiếu nếu hệ thống có những ràng buộc ấy.

Nếu endpoint hiện triển khai HAL như ví dụ Spring HATEOAS ở Mục 11, **không được chạy test Siren rồi kết luận sai thư viện**. Đó là hai định dạng khác nhau; hãy dùng contract test theo media type thực sự được công bố. Test HAL nên kiểm tra `_links` với relation URI tương ứng.

### 15.3. Kiểm thử gọi thẳng endpoint và tranh chấp

1. GET khi manager được duyệt, ghi lại version 5 và action `approve`.
2. Đổi đơn sang APPROVED bằng một command khác hoặc thu hồi role manager.
3. Gửi POST tới **href đã lưu** với `expectedOrderVersion=5` và idempotency key mới.
4. Xác nhận server trả **409** cho conflict trạng thái/version, hoặc **403** khi quyền đã bị thu hồi, và **không có side effect** mới.
5. GET lại Order; xác nhận action thay đổi đúng, response theo scope mới.

Sau đó kiểm thử hai request approve đồng thời với hai idempotency key khác nhau trên database phù hợp, dùng barrier/concurrency harness để tạo race. Kết quả cuối phải có **một** chuyển trạng thái hợp lệ, số approval record đúng quy tắc, outbox/audit nhất quán. Test tuần tự đơn giản khó bắt lỗi race.

### 15.4. Kiểm thử caching và link độc hại

- Cho manager và owner GET **cùng URI**, xác minh cache không dùng nhầm representation chứa action.
- Thu hồi quyền trong lúc client có ETag/cache cũ; kiểm tra validator, `304` và invalidation phù hợp.
- Kiểm tra link `href` không lấy host từ header chưa được tin cậy, không chứa access token hoặc dữ liệu nhạy cảm.
- Kiểm tra người gọi không thể lợi dụng query param, JWT claim tự dựng hay link từ response người khác để vượt tenant.
- Với client backend theo link, kiểm tra allowlist/domain/HTTPS và chính sách tránh truy cập địa chỉ nội bộ không được phép.

## 16. Bài tập thực hành và phương án tham khảo

### Bài tập A — Thiết kế nút thao tác cho đơn hàng

**Đề bài:** API GET /v1/orders/{id} có trạng thái DRAFT, SUBMITTED, APPROVED, CANCELLED và ba actor Owner, Manager, Auditor cùng tenant. Owner được submit DRAFT và cancel DRAFT/SUBMITTED. Manager được approve SUBMITTED nhưng không duyệt đơn do chính mình tạo. Auditor chỉ được đọc.

**Yêu cầu:** vẽ state diagram, lập ma trận action, chọn media type, mô tả POST approval và lỗi nếu hai manager cùng duyệt.

**Phương án tham khảo:** sử dụng state diagram ở Mục 3 và ma trận action ở Mục 3.2. Với client cần khám phá method và form, chọn Siren; response owner DRAFT có `submit`, `cancel`; response manager SUBMITTED có `approve` nếu không phải người tạo. POST approval cần idempotency key và `expectedOrderVersion`, server kiểm tra lại quyền/trạng thái trong transaction. Người thắng race tạo approval và chuyển Order sang APPROVED; người thua nhận kết quả replay nếu cùng intent/key hoặc conflict nếu intent khác.

### Bài tập B — Nhận diện rò rỉ quyền qua link

**Đề bài:** một client không thuộc tenant-a GET resource ngoài phạm vi và nhận:

~~~json
{
  "id": "o-17",
  "status": "SUBMITTED",
  "actions": [],
  "links": [
    {"rel": ["self"], "href": "/v1/orders/o-17"}
  ]
}
~~~

**Câu hỏi:** đã an toàn vì không có action thay đổi trạng thái chưa?

**Lời giải:** chưa. Response vẫn xác nhận ID và trạng thái của đơn. Nếu chính sách ẩn sự tồn tại, phải trả **404 trung tính**, không phát `self`, ETag, link hay metadata tiết lộ đơn. Việc không cho phép POST là một điều kiện bảo mật **riêng**, vẫn cần xử lý tại endpoint.

### Bài tập C — Action cũ sau khi quyền thay đổi

**Đề bài:** manager GET order SUBMITTED và thấy `approve`. Quản trị viên thu hồi role. Ba mươi giây sau manager bấm duyệt bằng href cũ.

**Câu hỏi:** status nên là gì và client xử lý thế nào?

**Lời giải:** endpoint kiểm tra lại quyền, từ chối với **403** nếu người gọi vẫn có quyền biết Order; hoặc **404** nếu chính sách cần ẩn cả Order. Client hiện thông báo phù hợp và GET lại representation trong phạm vi mới, thay vì tiếp tục thử lại POST. Cần kiểm tra caching/token TTL vì quyền đã thu hồi có thể còn nằm trong phiên hoặc token cũ nếu hệ thống không có cơ chế cập nhật phù hợp.

### Bài tập D — Chọn ETag cho hai URI khác nhau

**Đề bài:** client GET /v1/orders/o-17 nhận `ETag: "v8"`, rồi POST /v1/orders/o-17/approvals kèm `If-Match: "v8"`.

**Câu hỏi:** có chắc đó là kiểm tra version đơn đúng chuẩn HTTP không?

**Lời giải:** không. `If-Match` áp dụng cho **target resource của request POST**, trong khi ETag được lấy từ GET **Order URI**. Có thể dùng PATCH lên chính Order URI với `If-Match`; hoặc giữ POST approvals và gửi `expectedOrderVersion` trong body/custom condition được tài liệu hóa, server thực hiện CAS trong transaction. Khi version body đã cũ, API ví dụ trả **409 Conflict**.

### Bài tập E — Thêm action mới không phá client cũ

**Đề bài:** sản phẩm muốn thêm thao tác `request-changes` khi Order SUBMITTED, chỉ manager có quyền. Client mobile cũ không biết action này.

**Phương án tham khảo:** tạo relation/action có ngữ nghĩa riêng, mô tả method, input, trạng thái chuyển tiếp và errors; phát action theo policy. Client cũ nên bỏ qua action không biết, client mới hiển thị nút khi action xuất hiện. Không đổi nghĩa action `approve` để lén biểu diễn “yêu cầu sửa”; nếu hợp đồng hiện hành chưa có quy tắc tương thích cho action mới, cần version/profile và kế hoạch triển khai rõ ràng.

## 17. Các phản mẫu dễ gặp

| Phản mẫu | Rủi ro | Cách khắc phục |
|---|---|---|
| Trả mọi action cho mọi role và status | Client không biết thao tác nào thực sự hợp lệ | Sinh action từ policy theo trạng thái và principal |
| Ẩn nút trên frontend rồi bỏ kiểm tra backend | Gọi API trực tiếp có thể vượt quyền | Kiểm tra authentication, authorization và business state ở command handler |
| Coi link đã phát là quyền vĩnh viễn | Quyền hoặc đơn thay đổi sau GET | Reauthorize, kiểm tra version/trạng thái khi thực thi |
| Chỉ dựa vào role mà không kiểm tra owner/tenant | Manager tự duyệt hoặc truy cập chéo tenant | Kiểm tra đầy đủ role, owner, tenant, scope và tách nhiệm vụ |
| Trả `actions: []` kèm dữ liệu ngoài tenant | Lộ ID và trạng thái resource | 404 trung tính khi không được xem |
| Dùng HAL `href` như thể tự chứa method POST | Client có thể gửi GET sai hoặc đoán payload | Relation docs/profile hoặc Siren/HAL-FORMS |
| Dùng ETag của Order làm `If-Match` cho URI approvals mà không có hợp đồng | Hiểu sai precondition trên target resource | PATCH cùng Order URI hoặc expectedOrderVersion/CAS trên command |
| Cache Siren/HAL riêng tư như dữ liệu public | Action của manager có thể bị phục vụ cho người khác | no-store, phân tách cache và validator theo representation |
| Tạo action có URI phụ thuộc header Host không tin cậy | Sinh link trỏ miền bị thao túng | Trusted proxy, cấu hình base URL hoặc relative link |
| Client tự dựng URL thay vì đọc rel/action | Client dễ hỏng khi đổi URI | Dùng relation/action hợp đồng và bỏ qua action lạ an toàn |
| Tự POST mọi action mới xuất hiện | Side effect trái ý định người dùng | Chỉ thực thi khi được ủy quyền hoặc user xác nhận |
| Retry POST không có idempotency | Trùng approval/email/event | Idempotency key, DB constraint, outbox và kiểm tra side effect |
| Chỉ test GET có/không action | Bỏ lọt lỗi phân quyền ở endpoint đích | Test POST trực tiếp, quyền bị thu hồi, stale state và race |
| Trộn media type HAL và Siren cùng payload mà không thống nhất | Client parse sai representation | Hợp đồng Content-Type/Accept và serializer/test phù hợp |
| Không document rel riêng và version | Client không hiểu ý nghĩa action hoặc upgrade khó | Relation URI/profile, OpenAPI và chiến lược tương thích |
| Tính permission từng item bằng truy vấn lặp | N+1 queries, collection tải chậm | Batch policy evaluation, projection và pagination |

## 18. Checklist thiết kế và tài liệu tham khảo

### Checklist trước khi phát hành

- [ ] Resource có URI, biểu diễn trạng thái và action/rel được định nghĩa rõ.
- [ ] Có ma trận **trạng thái × role × owner × tenant** cho từng thao tác.
- [ ] Phân biệt link điều hướng, action/affordance và **authorization thực thi**.
- [ ] Server chỉ sinh action sau khi xác minh người gọi **được xem resource**.
- [ ] GET và command handler dùng chung các quy tắc policy, với **kiểm tra lại khi ghi**.
- [ ] Endpoint chống TOCTOU bằng transaction, state validation và concurrency control.
- [ ] ETag/If-Match được áp dụng **đúng target URI**; command subresource có cơ chế version của parent riêng nếu cần.
- [ ] POST có side effect có idempotency key, bảo vệ replay và xử lý kết quả không rõ.
- [ ] HAL link không bị nhầm với action có method/fields; media type được công bố chính xác.
- [ ] Mọi relation/action tùy biến có tên/ngữ nghĩa ổn định, tài liệu và kế hoạch tương thích.
- [ ] Không tiết lộ ID, trạng thái, link, relation, ETag hoặc metadata từ resource ngoài tenant/ACL.
- [ ] 401/403/404/409/412/428/201/202/204 được dùng theo ngữ nghĩa HTTP và hợp đồng nghiệp vụ.
- [ ] Representation phụ thuộc quyền được xử lý cache/ETag đúng; không dùng shared cache lẫn người gọi.
- [ ] URI, Host, forwarded headers, credential và signed URL có mô hình tin cậy rõ ràng.
- [ ] Client có thể bỏ qua action chưa biết, xử lý action biến mất và GET lại sau command.
- [ ] Nếu collection nhúng action theo item, policy và hiệu năng N+1 đã được kiểm tra.
- [ ] OpenAPI mô tả method/payload/error; hypermedia response thể hiện affordance tại runtime.
- [ ] Test matrix bao gồm đủ state/role, direct POST, cross-tenant, stale link, idempotency, concurrency, cache và content type.
- [ ] Observability có requestId, action type, state transition, authorization-denied rate và conflict rate, nhưng không log token/PII.
- [ ] Có runbook khi action hiển thị lệch quyền, phiên bản cache sai hoặc hàng loạt POST bị conflict.

### Tài liệu để tìm hiểu sâu

- **RFC 8288 — Web Linking:** relation type và ngữ nghĩa của liên kết. [RFC 8288](https://www.rfc-editor.org/rfc/rfc8288)
- **RFC 9110 — HTTP Semantics:** GET/POST/PATCH-related HTTP preconditions, ETag, status code và cache liên quan. [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110)
- **RFC 9457 — Problem Details for HTTP APIs:** phản hồi lỗi máy đọc được. [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
- **RFC 6906 — The 'profile' Link Relation Type:** bổ sung thông tin ngữ nghĩa của representation. [RFC 6906](https://www.rfc-editor.org/rfc/rfc6906)
- **OpenAPI 3.1:** mô tả endpoint, schema, security và response. [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0)
- **Spring HATEOAS:** `EntityModel`, `Link` và hỗ trợ hypermedia; đối chiếu API với phiên bản thư viện đang triển khai.
- **HAL, Siren và HAL-FORMS:** chọn và kiểm tra media type, relation, action/template đúng theo format thực tế của client/server.

**Điểm cần nhớ:** hypermedia hữu ích khi server phát ra **những bước tiếp theo phù hợp với resource và người gọi**, nhưng quyền thực thi luôn được xác định lại tại endpoint. Thiết kế đúng cần kết hợp relation/action có ngữ nghĩa, state machine, kiểm tra quyền theo tenant/owner, concurrency, idempotency, cache và các bài kiểm thử đổi quyền hoặc đổi trạng thái giữa hai HTTP request.
