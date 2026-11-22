# Eventual consistency và biểu diễn trạng thái đang xử lý

Trong REST API, việc máy chủ trả lời thành công một HTTP request **không luôn có nghĩa mọi hệ thống và mọi bản đọc đã cập nhật xong**. Một lệnh tạo đơn hàng có thể được nhận, lưu vào hàng đợi và tiếp tục xử lý tồn kho, thanh toán hoặc tìm kiếm bất đồng bộ. Nếu API chỉ trả `200 OK` với chuỗi `"success"`, client không biết thành công ở bước nào, có nên gửi lại lệnh hay khi nào được đọc kết quả.

**Eventual consistency (nhất quán cuối cùng)** là mô hình trong đó các bản sao hoặc thành phần liên quan có thể tạm thời nhìn thấy các trạng thái khác nhau, nhưng sẽ hội tụ về cùng trạng thái **khi các cập nhật ngừng và việc truyền/áp dụng cập nhật thành công**. Với REST API, cần biểu diễn rõ tiến độ nghiệp vụ, thời điểm kết quả có thể đọc, trạng thái lỗi và cách client kiểm tra. Đây là phần của **Nhất quán nghiệp vụ** trong module thiết kế REST API bằng HTTP và Java/Spring.

Sau bài học, người học có thể thiết kế resource theo dõi tác vụ, trả `202 Accepted` đúng ngữ nghĩa, phối hợp idempotency với transactional outbox, xử lý độ trễ của read model, xây dựng luồng polling và kiểm thử các trạng thái trung gian.

## 1. Hai vấn đề thường đi cùng nhau nhưng không đồng nghĩa

Xét một hệ thống đặt hàng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Orders API
    participant DB as Orders DB
    participant P as Outbox publisher
    participant Q as Queue
    participant W as Worker
    participant R as Read model
    C->>A: POST /v1/orders
    A->>DB: Transaction: operation + outbox
    DB-->>A: Commit
    A-->>C: 202 Accepted + Location monitor
    P->>DB: Đọc outbox sau commit
    DB-->>P: Event đang chờ
    P->>Q: Gửi event
    Q-->>W: Process order (có thể giao lặp)
    W->>DB: Ghi trạng thái nghiệp vụ
    W->>R: Cập nhật projection bất đồng bộ
    C->>A: GET /v1/operations/op-42
    A-->>C: 200, state=SUCCEEDED
    C->>A: GET /v1/orders/ord-42
    A->>R: Đọc đơn hàng
    R-->>A: Dữ liệu đã được cập nhật
    A-->>C: 200 Order
~~~

Trong sơ đồ có **hai dạng không đồng bộ**:

1. **Xử lý tác vụ bất đồng bộ:** request tạo đơn được hệ thống nhận vào quy trình nhưng kết quả nghiệp vụ chưa hoàn tất khi trả HTTP. Đây là lý do thường dùng `202 Accepted` và **operation/status resource**.
2. **Bản đọc nhất quán cuối cùng:** giao dịch đã ghi thành công vào nguồn dữ liệu chính, nhưng cache, replica, search index hoặc read projection chưa kịp nhận thay đổi. Một lệnh có thể đã **hoàn tất** trong hệ thống ghi mà `GET` trên read model vẫn thấy dữ liệu cũ.

Eventual consistency **không bắt buộc** phải dùng HTTP 202. Một `POST` có thể tạo resource ngay trong transaction và trả `201 Created`, trong khi search index vẫn cập nhật chậm. Ngược lại, hệ thống có thể dùng `202` để xếp hàng một tác vụ lâu nhưng đọc/ghi trên một cơ sở dữ liệu nhất quán mạnh. Chọn phản hồi dựa vào **cam kết thực tế ở thời điểm phản hồi**.

### Ví dụ trạng thái trong thực tế

| Thời điểm | Nguồn ghi | Read projection | Trạng thái API nên công bố |
| --- | --- | --- | --- |
| Ngay sau nhận lệnh | Có bản ghi operation + outbox | Chưa có đơn | `PENDING`: đã nhận, chưa hoàn tất |
| Worker bắt đầu | Tác vụ đang chạy | Có thể chưa có đơn | `RUNNING` hoặc `PROCESSING` |
| Ghi đơn thành công | Đơn có trạng thái nghiệp vụ mới | Chưa theo kịp | Tác vụ có thể `SUCCEEDED`; cần nói rõ read model còn trễ |
| Projection bắt kịp | Đơn đã ghi | Bản đọc phản ánh đơn | `GET` đơn trả dữ liệu mới nhất theo version đã xác minh |
| Worker thất bại | Có lỗi hoặc đang chờ retry | Có thể giữ dữ liệu cũ | `RETRYING` hoặc `FAILED` tùy kết quả đã xác định |

**Không đánh đồng** “đã nhận lệnh”, “đã bắt đầu”, “đã ghi dữ liệu nguồn”, “đã cập nhật mọi bản sao” và “đã hoàn tất nghiệp vụ”. Mỗi mốc cần được định nghĩa trong hợp đồng API.

## 2. Thiết kế hai resource: tác vụ và kết quả nghiệp vụ

Ví dụ API nhận yêu cầu tạo đơn `POST /v1/orders` và trả một resource theo dõi tại `/v1/operations/{operationId}`.

**Request (có idempotency key để retry an toàn):**

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Idempotency-Key: 4b5239b7-8284-4e52-8d47-6d249f8c019b
Prefer: respond-async

{
  "items": [
    {"sku": "BOOK-42", "quantity": 2}
  ],
  "shippingAddressId": "addr-09"
}
~~~

**Response khi lệnh đã được chấp nhận và lưu bền vững để xử lý tiếp:**

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /v1/operations/37d56011-27b9-4b02-a343-f9e050df4358
Retry-After: 2
Cache-Control: no-store
Preference-Applied: respond-async

{
  "id": "37d56011-27b9-4b02-a343-f9e050df4358",
  "kind": "CREATE_ORDER",
  "state": "PENDING",
  "createdAt": "2026-11-18T09:00:00Z",
  "updatedAt": "2026-11-18T09:00:00Z",
  "version": 1,
  "pollAfterSeconds": 2,
  "_links": {
    "self": "/v1/operations/37d56011-27b9-4b02-a343-f9e050df4358"
  }
}
~~~

`202 Accepted` nghĩa là **yêu cầu đã được chấp nhận để xử lý, nhưng xử lý chưa hoàn tất và vẫn có thể không thành công về sau**. Đây là phản hồi **không cam kết** kết quả cuối. Nó không buộc server phải trả thêm một HTTP response trên kết nối ban đầu khi worker xong; client cần một kênh quan sát khác. `Location` trỏ tới resource theo dõi; `Retry-After` là gợi ý thời điểm polling, không phải thời hạn hoàn thành được bảo đảm. Nếu client gửi `Prefer: respond-async` và server thực hiện đúng preference đó, có thể trả `Preference-Applied: respond-async`; khi không sử dụng preference thì không cần header này.

**Một số hợp đồng khác cũng hợp lệ:** Nếu resource đã được tạo ngay và có địa chỉ ổn định, `POST` có thể trả `201 Created` và `Location: /v1/orders/ord-42`, trong body ghi `fulfillmentStatus: PENDING`. Nếu client thực hiện cập nhật đồng bộ và kết quả sẵn sàng, trả `200 OK` hoặc `204 No Content` tùy hợp đồng. Không ép tất cả thao tác chậm vào `202` nếu không có trạng thái nào để theo dõi.

### Tại sao cần operation riêng?

- **Resource nghiệp vụ** (`/v1/orders/ord-42`) biểu diễn đơn hàng và trạng thái nghiệp vụ như `CONFIRMED`, `CANCELLED`, `SHIPPED`.
- **Operation resource** (`/v1/operations/op-42`) biểu diễn **tiến độ thực thi một lệnh** như `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`; nó có thể tồn tại trước khi order ID được cấp.
- Một đơn hàng có thể trải qua nhiều operation: tạo đơn, đổi địa chỉ, yêu cầu hủy. Mỗi lệnh có idempotency key, lỗi và thời điểm riêng.
- Việc trả một monitor URI cho phép frontend/mobile/đối tác polling có kiểm soát, khôi phục sau khi mất kết nối và tách timeout HTTP khỏi thời gian xử lý dài.

Không dùng URL operation làm chỗ chứa thông tin nhạy cảm; mỗi lần `GET` operation vẫn phải kiểm tra tenant, principal và quyền xem tiến độ.

## 3. Máy trạng thái công khai: chuyển trạng thái có kiểm soát

Một mô hình tối thiểu:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Commit operation
    PENDING --> RUNNING: Worker nhận việc
    RUNNING --> SUCCEEDED: Kết quả được xác nhận
    RUNNING --> RETRYING: Lỗi tạm thời
    RETRYING --> RUNNING: Retry có kiểm soát
    PENDING --> CANCELLED: Hủy trước khi chạy
    RUNNING --> FAILED: Lỗi vĩnh viễn
    RETRYING --> FAILED: Hết retry budget
    SUCCEEDED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
~~~

Các trạng thái trên là **hợp đồng ví dụ**, không phải enum được HTTP quy định. Với hệ thống có bước bù trừ, có thể bổ sung `COMPENSATING`, `COMPENSATED` hoặc `NEEDS_REVIEW`. Không công bố `CANCELLED` nếu tác vụ đã gây tác động bên ngoài nhưng không thể đảo ngược; “đã yêu cầu hủy” khác “đã hủy thành công”.

| State | Điều server có thể khẳng định | Client nên làm gì? |
| --- | --- | --- |
| `PENDING` | Lệnh được lưu và đang chờ xử lý | Tiếp tục polling, không POST lại tùy tiện |
| `RUNNING` | Đã bắt đầu xử lý; có thể nhiều bước | Poll chậm, hiển thị “Đang xử lý” |
| `RETRYING` | Một bước lỗi tạm, server dự kiến retry | Chờ; không tạo lệnh nghiệp vụ mới |
| `SUCCEEDED` | Điều kiện thành công đã định nghĩa trong hợp đồng được xác nhận | Dùng `resultUrl`/link kết quả; kiểm tra read readiness nếu cần |
| `FAILED` | Tác vụ đã kết thúc mà không đạt điều kiện thành công | Hiển thị lỗi an toàn, theo hướng dẫn phục hồi |
| `CANCELLED` | Việc hủy được xác nhận theo semantics cụ thể | Không xem đây là lỗi mạng có thể retry vô hạn |

Đặt quy tắc **transition hợp lệ**, version tăng đơn điệu và cập nhật có điều kiện (compare-and-set hoặc optimistic locking) để worker trùng không đảo ngược trạng thái terminal. Ví dụ:

~~~sql
UPDATE api_operation
   SET state = 'RUNNING',
       version = version + 1,
       updated_at = CURRENT_TIMESTAMP
 WHERE id = :operation_id
   AND state IN ('PENDING', 'RETRYING')
   AND version = :expected_version;
~~~

Nếu trả về 0 row, worker phải đọc lại state để quyết định bỏ qua hoặc tiếp tục đúng cách. **Không** cho sự kiện đến trễ đặt `SUCCEEDED` trở lại `RUNNING`. Có thể cần claim/lease token và kiểm tra ở worker để tránh hai consumer cùng thực thi side effect không idempotent.

### Progress và status có nghĩa cụ thể

Đừng tạo “99%” nếu hệ thống không đo được tiến độ. Với workflow xác định được số bước, có thể trả:

~~~json
{
  "id": "37d56011-27b9-4b02-a343-f9e050df4358",
  "state": "RUNNING",
  "phase": "RESERVING_INVENTORY",
  "completedSteps": 1,
  "totalSteps": 3,
  "version": 3,
  "updatedAt": "2026-11-18T09:00:03Z",
  "pollAfterSeconds": 2
}
~~~

Nếu số bước có thể thay đổi, hãy trả `phase` hoặc thông báo “Đang xác nhận tồn kho” và bỏ `percentage`. Chọn các nhãn ổn định để UI/SDK xử lý; không phơi bày queue topology, database internals, stack trace hay thông tin tenant khác. Với retry, số bước đã hoàn tất có thể cần chạy lại; công bố rõ liệu progress là ước lượng hay milestone đã xác nhận.

## 4. HTTP status của request khác trạng thái nghiệp vụ trong body

Điểm dễ nhầm là `GET /v1/operations/op-42` trả `200 OK` dù operation đang `FAILED`. Điều đó hợp lý: **HTTP 200 chỉ nói việc truy xuất resource trạng thái thành công**; việc lệnh nghiệp vụ thất bại là **dữ liệu bên trong resource**.

**Đang chạy:**

~~~http
GET /v1/operations/37d56011-27b9-4b02-a343-f9e050df4358 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "op-3"
Cache-Control: no-store

{
  "id": "37d56011-27b9-4b02-a343-f9e050df4358",
  "state": "RUNNING",
  "phase": "RESERVING_INVENTORY",
  "version": 3,
  "pollAfterSeconds": 2
}
~~~

**Hoàn tất thành công:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "op-6"
Cache-Control: no-store

{
  "id": "37d56011-27b9-4b02-a343-f9e050df4358",
  "state": "SUCCEEDED",
  "version": 6,
  "result": {
    "resourceType": "order",
    "id": "ord-42",
    "url": "/v1/orders/ord-42"
  },
  "completedAt": "2026-11-18T09:00:08Z"
}
~~~

**Hoàn tất thất bại:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "37d56011-27b9-4b02-a343-f9e050df4358",
  "state": "FAILED",
  "error": {
    "type": "https://api.example.com/problems/stock-unavailable",
    "title": "Không đủ hàng",
    "status": 409,
    "code": "OUT_OF_STOCK",
    "detail": "Một mặt hàng không còn đủ số lượng."
  },
  "version": 7,
  "completedAt": "2026-11-18T09:00:09Z"
}
~~~

Ở ví dụ cuối, object `error` dùng những trường quen thuộc của **Problem Details (RFC 9457)** để mô tả *lỗi nghiệp vụ đã xảy ra trong tác vụ*. Trường `status: 409` mô tả loại lỗi tương ứng nếu được xử lý đồng bộ; **mã HTTP thực tế của lần GET operation vẫn là 200**. Hợp đồng nên ghi rõ điều này để client không hiểu nhầm 200 là đặt hàng thành công. Có thể dùng mã lỗi nghiệp vụ riêng thay cho nội dung Problem Details nếu định nghĩa rõ.

### Bảng lựa chọn HTTP status

| Tình huống | HTTP | Ý nghĩa |
| --- | --- | --- |
| POST hợp lệ, đã được chấp nhận để xử lý sau | **202 Accepted** | Cần monitor, chưa cam kết kết quả cuối |
| POST tạo resource và đã commit xong | **201 Created** | `Location` tới resource đã tạo |
| GET operation tồn tại và thuộc quyền xem | **200 OK** | Body nói đang chạy, thành công hay lỗi |
| GET operation chưa đổi version và có conditional request phù hợp | **304 Not Modified** | Client có thể giữ representation đã lưu |
| GET operation không tồn tại hoặc bị che khỏi tenant khác | **404 Not Found** | Không xác nhận sự tồn tại của resource không được phép |
| Operation hết thời gian lưu và server còn biết đã từng tồn tại | **410 Gone** (*tùy hợp đồng*) | Monitor đã bị xóa; client cần đường tra cứu khác |
| POST trùng idempotency key với nội dung **khác** | **409 Conflict** | Không thể tái sử dụng key cho lệnh khác |
| POST sai schema, người gọi không có quyền | **400/422**, **401/403** | Từ chối ngay, không tạo việc |
| Service chưa thể nhận thêm việc | **429** hoặc **503** tùy nguyên nhân | Không hứa đã xếp việc nếu chưa ghi bền |

Có thể trả `303 See Other` từ monitor đã hoàn tất để hướng client sang resource kết quả, nhưng nhiều client tự động follow redirect và mất trạng thái cuối của operation. **GET trả 200 chứa `result.url` thường dễ dùng hơn**; chọn một cách và ghi rõ trong OpenAPI.

## 5. Độ trễ bản đọc: xử lý read-your-writes và phiên bản dữ liệu

Giả sử transaction xác nhận tạo đơn lúc 09:00:08 và operation được đánh dấu `SUCCEEDED`, nhưng Elasticsearch/read replica chỉ bắt kịp lúc 09:00:10. Nếu client lập tức gọi `GET /v1/orders/ord-42` qua read model, có thể thấy `404` hoặc bản cũ.

Điều cần thiết là **định nghĩa mốc thành công** và **cam kết đọc**:

- **Giải pháp A — Kết quả đọc được ngay:** trả `SUCCEEDED` chỉ khi dữ liệu mà `result.url` trỏ tới đã có thể đọc theo đúng tiêu chí nhất quán API công bố. Có thể đọc nguồn ghi để đáp ứng luồng read-after-write.
- **Giải pháp B — Phân biệt hoàn tất lệnh và projection:** trả `SUCCEEDED` khi nguồn ghi đã commit và kèm `projectionStatus: PENDING`; chuyển thành `READY` khi bản đọc đạt version yêu cầu. Client chờ `READY` nếu phải xem kết quả ngay trên projection.
- **Giải pháp C — Đọc theo mốc phiên bản:** response của lệnh trả một `writeVersion` hoặc `consistencyToken`; GET sau đó yêu cầu dữ liệu **tối thiểu** phiên bản ấy, server có thể đợi có giới hạn hoặc đọc nguồn chính. Nếu hết timeout, trả lỗi/tiến độ có cấu trúc, không tự trả dữ liệu cũ rồi tuyên bố mới nhất.

Ví dụ contract mở rộng khi projection còn trễ:

~~~json
{
  "state": "SUCCEEDED",
  "result": {
    "id": "ord-42",
    "url": "/v1/orders/ord-42",
    "writeVersion": 12
  },
  "projection": {
    "state": "PENDING",
    "observedVersion": 10,
    "requiredVersion": 12
  }
}
~~~

Sau khi projection hội tụ:

~~~json
{
  "state": "SUCCEEDED",
  "result": {
    "id": "ord-42",
    "url": "/v1/orders/ord-42",
    "writeVersion": 12
  },
  "projection": {
    "state": "READY",
    "observedVersion": 12,
    "requiredVersion": 12
  }
}
~~~

Phiên bản trong ví dụ chỉ có ý nghĩa nếu thuộc **cùng một luồng/version domain**; không so sánh hai con số không cùng hệ quy chiếu. Trong event pipeline có nhiều partition, cần offset theo partition hoặc một cơ chế consistency token phù hợp, thay vì giả định có một global sequence rẻ và luôn sẵn. Đồng thời, replica có thể thiếu cập nhật vì lỗi, nên eventual consistency **không bảo đảm thời hạn hội tụ cố định** nếu không có SLO, retry, phát hiện drift và quy trình khôi phục.

Một số thao tác đọc không nên dựa trên bản sao trễ: quyết định chuyển tiền, kiểm tra giới hạn tín dụng hoặc bảo đảm không bán quá tồn kho phải dùng transaction, khóa/điều kiện cập nhật, unique constraint hoặc cơ chế điều phối tương ứng trong **nguồn dữ liệu quyết định**.

### Cache và ETag

Khi trạng thái operation thay đổi, có thể phát `ETag: "op-6"` tương ứng với version của representation. Client gửi `If-None-Match: "op-6"`; nếu chưa đổi, server trả `304 Not Modified`. Điều này giảm băng thông phản hồi, **không giảm số request polling**, nên vẫn cần rate limit và backoff. `Cache-Control: no-store` phù hợp với trạng thái đơn hàng nhạy cảm; server vẫn có thể thực thi conditional GET theo các điều kiện HTTP. Nếu chọn caching cho monitor công khai, phải xác định rõ `Cache-Control`, `Vary` và tránh cache giữa người dùng/tenant.

Tránh cấp `ETag` hoặc version chỉ dựa trên thay đổi `state`: `progress`, `projectionStatus`, `result` hay `error` đổi thì representation cũng phải đổi version/validator. Client cần biết khi nào trạng thái thực sự khác để không bỏ lỡ cập nhật.

## 6. Bảo đảm nhận lệnh bền vững: idempotency và transactional outbox

**Tình huống nguy hiểm:** API ghi “đã nhận” trong DB rồi crash trước khi publish message. Client đã nhận `202` nhưng worker không bao giờ biết việc cần làm. Hướng giải quyết là **ghi operation và outbox trong cùng một DB transaction**, sau đó publisher đọc outbox để gửi event. Nếu không commit được, **không trả `202`**.

~~~mermaid
flowchart LR
    C[Client POST] --> A[API: validate, auth, idempotency]
    A --> T[DB transaction]
    T --> O[(Operation + idempotency row)]
    T --> X[(Outbox event)]
    X --> P[Publisher có retry]
    P --> B[(Broker)]
    B --> W[Worker idempotent]
    W --> S[(Business state)]
    S --> R[Read projection]
~~~

**Lược đồ SQL minh họa** (dành cho PostgreSQL; rút gọn các index/constraint vận hành):

~~~sql
CREATE TABLE api_operation (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    action VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(120) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    state VARCHAR(24) NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    result_uri TEXT,
    error_code VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, action, idempotency_key)
);

CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES api_operation(id),
    event_type VARCHAR(80) NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE consumed_event (
    consumer_name VARCHAR(80) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Lưu ý các quy tắc:

1. Phạm vi idempotency key phải được định danh, ví dụ **tenant + action + key**; so sánh **hash của yêu cầu chuẩn hóa**. Cùng key/cùng nội dung phải trả về **cùng operation**, không tạo đơn thứ hai; cùng key/khác nội dung trả `409`. Việc tính hash cần xác định rõ các trường có ý nghĩa, không phụ thuộc thứ tự property JSON không liên quan.
2. `UNIQUE` bảo vệ race giữa hai instance cùng nhận key. Không chỉ làm `SELECT` rồi `INSERT` mà bỏ qua tranh chấp; dùng insert có kiểm soát va chạm và đọc bản ghi thắng cuộc trong transaction thích hợp.
3. Ghi operation và outbox **atomically trong cùng DB transaction**. Redis cache hoặc publish Kafka không thể tự ghép vào transaction SQL thường bằng một lệnh đơn giản; outbox giúp loại bỏ khoảng trống “commit DB rồi mất message”.
4. Publisher có thể gửi message **ít nhất một lần**: ví dụ gửi thành công rồi crash trước khi cập nhật `published_at`. Consumer phải **idempotent**: ghi dấu `consumed_event` cùng transaction với thay đổi nghiệp vụ nội bộ, hoặc sử dụng unique business key/conditional update phù hợp.
5. “Exactly once” ở broker không tự bảo đảm một lời gọi sang payment provider/warehouse chỉ chạy đúng một lần. Khi side effect vượt biên transaction, truyền idempotency key cho provider nếu họ hỗ trợ, dùng reconciliation và quy trình bù trừ.
6. Bản ghi operation có vòng đời và thời gian lưu rõ ràng; đừng xóa key idempotency quá sớm khi vẫn có client retry request cũ. Chính sách retention phải được ghi trong tài liệu API.

Khi client gửi lại **cùng key** sau lúc operation đã hoàn tất, server vẫn trả về **cùng operation**; HTTP có thể trả `200 OK` cùng representation terminal, hoặc phát lại phản hồi đã lưu theo hợp đồng idempotency. Không nên tiếp tục tuyên bố `202 Accepted` như thể tác vụ vẫn chưa hoàn tất khi response hiện tại đang mô tả kết quả terminal. Client cần căn cứ vào `state`, `result` và `error`.

Nếu không dùng message broker, DB worker có thể quét bảng job/outbox với cơ chế claim an toàn như `FOR UPDATE SKIP LOCKED` hoặc lease. Dù chọn cách nào, cần tránh hai worker cùng thực thi một side effect không idempotent.

## 7. Java/Spring: REST controller cho operation status

Đoạn code dùng Spring Boot 3.x, Java 17+, Spring MVC và một service ứng dụng quản lý transaction. Ví dụ tách interface domain để tập trung vào **hợp đồng REST**; repository, outbox publisher và xử lý nghiệp vụ phải được triển khai theo nguyên tắc ở mục trước.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1")
public class OrderCommandController {
    private final OperationService operations;

    public OrderCommandController(OperationService operations) {
        this.operations = operations;
    }

    @PostMapping(value = "/orders",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OperationView> submit(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @Valid @RequestBody PlaceOrderRequest request,
            Authentication authentication) {

        // Resolve tenant từ principal đã xác thực, không từ JSON/header tùy ý.
        String tenantId = TenantIdentity.from(authentication);
        OperationView operation =
            operations.acceptOrder(tenantId, idempotencyKey, request);

        URI monitor = URI.create("/v1/operations/" + operation.id());
        // Nếu cùng Idempotency-Key được retry sau khi tác vụ đã hoàn tất,
        // trả representation terminal với 200 và cùng monitor URI.
        boolean terminal = switch (operation.state()) {
            case "SUCCEEDED", "FAILED", "CANCELLED" -> true;
            default -> false;
        };
        if (terminal) {
            return ResponseEntity.ok()
                .location(monitor)
                .cacheControl(CacheControl.noStore())
                .body(operation);
        }
        return ResponseEntity.accepted()
            .location(monitor)
            .header("Retry-After", "2")
            .cacheControl(CacheControl.noStore())
            .body(operation);
    }

    @GetMapping("/operations/{id}")
    public ResponseEntity<OperationView> getOperation(
            @PathVariable UUID id,
            Authentication authentication) {

        String tenantId = TenantIdentity.from(authentication);
        OperationView operation = operations.getVisible(tenantId, id);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(operation);
    }

    public record PlaceOrderRequest(
        @NotEmpty @Size(max = 100) List<@Valid Line> items,
        @NotBlank String shippingAddressId
    ) {}

    public record Line(
        @NotBlank String sku,
        @Min(1) int quantity
    ) {}

    public record OperationView(
        UUID id,
        String kind,
        String state,
        long version,
        Instant createdAt,
        Instant updatedAt,
        Integer pollAfterSeconds,
        ResultLink result,
        OperationError error
    ) {}

    public record ResultLink(String resourceType, String id, URI url) {}
    public record OperationError(String code, String message) {}
}

// Giao diện minh họa. Cần implementation theo DB transaction + outbox.
interface OperationService {
    OrderCommandController.OperationView acceptOrder(
        String tenantId,
        String idempotencyKey,
        OrderCommandController.PlaceOrderRequest request
    );

    OrderCommandController.OperationView getVisible(String tenantId, UUID id);
}

// Adapter ví dụ cho OAuth2 Resource Server đã verify JWT.
final class TenantIdentity {
    private TenantIdentity() {}
    static String from(Authentication authentication) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            throw new AccessDeniedException("JWT authentication required");
        }
        String tenant = jwtAuth.getToken().getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            throw new AccessDeniedException("Tenant claim missing");
        }
        return tenant;
    }
}
~~~

**Điểm phải hoàn thiện khi dùng thật:** ví dụ `TenantIdentity.from()` giả định Spring Security đã xác thực **JWT hợp lệ** và hệ thống quản lý claim `tenant_id`. Khi triển khai phải cấu hình xác minh chữ ký, issuer/audience và bảo đảm user có quyền với tenant đó; nếu dùng session hoặc định dạng principal khác, thay adapter tương ứng. Không chấp nhận tenant do client tự truyền. `OperationService` phải validate idempotency key (độ dài/định dạng), kiểm tra quyền địa chỉ giao hàng, hash request, đặt unique constraint, commit operation + outbox và ném exception HTTP phù hợp nếu không thể nhận việc. Khi gặp cùng idempotency key, service phải trả lại đúng operation cũ, kể cả khi POST đầu tiên trả 202 nhưng client bị đứt mạng.

Nếu cần `ETag` cho monitor, thêm validation version của **representation đầy đủ** và xử lý `If-None-Match` theo HTTP (có thể dùng `WebRequest.checkNotModified` trong Spring MVC) để trả 304. Không tự so sánh một chuỗi raw đơn giản nếu muốn hỗ trợ đúng nhiều ETag, wildcard và weak validator.

### Transaction pseudocode của service

~~~text
acceptOrder(tenant, idempotencyKey, request):
  validate key, request, authentication & resource authorization
  fingerprint = SHA-256(canonicalBusinessPayload(request))
  BEGIN TRANSACTION
    try INSERT operation(
        tenant, action="CREATE_ORDER",
        idempotencyKey, fingerprint, state="PENDING")
    if UNIQUE(tenant, action, key) conflicts:
        load existing operation
        if fingerprint differs: reject with 409
        return existing operation (không tạo outbox thứ hai)
    INSERT outbox_event(
        id=new-event-id,
        operationId=operation.id,
        type="CREATE_ORDER_REQUESTED",
        payload=validated command)
  COMMIT
  return operation PENDING as HTTP 202

worker(event):
  if already applied event or operation terminal: acknowledge safely
  claim operation with lease/version check
  apply business transition idempotently
  write business state + operation state in appropriate transactions
  on transient failure: schedule bounded retry with backoff
  on permanent failure: mark FAILED with safe error code
  publish state/projection events reliably
~~~

Trong code thực tế, xử lý va chạm unique constraint tùy cách giao dịch của DB và framework: sau một lỗi insert, transaction có thể bị đánh dấu rollback-only; hãy dùng thao tác insert-on-conflict phù hợp hoặc ranh giới transaction để đọc bản ghi đã tồn tại một cách an toàn. Pseudocode mô tả bất biến, không giả định catch exception rồi cứ tiếp tục trong cùng transaction đã hỏng.

## 8. Polling, Retry-After và các kênh cập nhật khác

Client không nên polling mỗi vài mili-giây. Hãy cung cấp `pollAfterSeconds` hoặc `Retry-After`, kết hợp **backoff + jitter + deadline**, và xử lý chính xác mọi trạng thái terminal. Ví dụ JavaScript rút gọn:

~~~javascript
const terminal = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);

async function pollOperation(monitorUrl, signal) {
  const startedAt = Date.now();
  const maxWaitMs = 60_000;
  let delayMs = 2_000;

  while (Date.now() - startedAt < maxWaitMs) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");

    const response = await fetch(monitorUrl, {
      credentials: "include",
      cache: "no-store",
      signal
    });

    if (response.status === 401 || response.status === 403) {
      throw new Error("Không có quyền xem trạng thái tác vụ");
    }
    if (response.status === 404 || response.status === 410) {
      throw new Error("Không còn truy cập được resource theo dõi");
    }
    if (!response.ok) {
      throw new Error("Không thể đọc trạng thái: HTTP " + response.status);
    }

    const op = await response.json();
    if (terminal.has(op.state)) return op;

    // Server cung cấp gợi ý, client áp trần để bảo vệ UX.
    const seconds = Math.max(1, Math.min(15, op.pollAfterSeconds ?? 2));
    delayMs = Math.max(delayMs, seconds * 1000);
    const jitterMs = Math.floor(Math.random() * 300);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        signal?.removeEventListener("abort", onAbort);
        resolve();
      }, delayMs + jitterMs);
      function onAbort() {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      }
      signal?.addEventListener("abort", onAbort, { once: true });
    });
    delayMs = Math.min(delayMs * 1.5, 15_000);
  }
  throw new Error("Hết thời gian chờ; tác vụ có thể vẫn đang xử lý");
}
~~~

Đoạn trên để minh họa vòng polling, chưa thay thế một HTTP client production: cần xử lý `429`/`503` với `Retry-After`, network retries theo ngân sách, quy tắc origin/CORS, timeout từng request và giới hạn thời gian chờ chính xác (kể cả một request/giấc ngủ vượt deadline). **Hết thời gian polling ở client không đồng nghĩa operation thất bại ở server**. Client phải có cách tra cứu lại monitor URI sau khi tải lại trang, đồng thời tránh lưu thông tin nhạy cảm công khai.

Ngoài polling:

| Cách báo tiến độ | Phù hợp | Điều kiện |
| --- | --- | --- |
| **Polling GET operation** | Tương thích gần như mọi client | Có backoff, deadline, ETag, rate limit |
| **Server-Sent Events (SSE)** | Giao diện cần cập nhật một chiều | Kết nối có thể đứt; cần reconnect và chống mất event |
| **WebSocket** | Giao tiếp hai chiều/real-time nhiều sự kiện | Cần auth, reconnect, heartbeat, backpressure |
| **Webhook callback** | Tích hợp server-to-server | Ký payload, chống replay, retry, deduplicate, endpoint nhận độc lập |

Đừng chỉ gửi một notification rồi xóa operation: client offline sẽ không biết kết quả. Duy trì resource tra cứu cuối cùng trong thời gian retention đã công bố; SSE/webhook chỉ là **kênh thông báo bổ sung**, không phải nguồn sự thật duy nhất.

## 9. Lỗi, retry, timeout và bù trừ nghiệp vụ

Xử lý bất đồng bộ trải qua nhiều hệ thống nên sẽ gặp các tình huống khác nhau:

| Tình huống | Phản ứng có kiểm soát |
| --- | --- |
| API lỗi trước khi commit operation/outbox | Trả 4xx/5xx phù hợp; **không khẳng định đã nhận việc** |
| Commit thành công nhưng phản hồi 202 bị mất | Client retry **cùng idempotency key**; API trả lại operation cũ |
| Publisher gửi event rồi crash trước khi đánh dấu outbox | Có thể phát lại; consumer phải idempotent |
| Worker xử lý một phần rồi bị kill | Resume/retry có checkpoint và idempotent side effect |
| Payment provider timeout, không biết đã thu tiền chưa | Đánh dấu tình trạng **chưa xác định** và reconcile bằng provider idempotency/reference; không thu tiền lại mù quáng |
| Hết retry budget do lỗi cố định | `FAILED`/`NEEDS_REVIEW` cùng mã lỗi và thông tin khôi phục an toàn |
| Một bước đã thành công nhưng bước sau thất bại | Chạy bước **compensation** nếu nghiệp vụ cho phép; chưa nên công bố kết quả cuối quá sớm |
| Read projection chậm hoặc ngừng cập nhật | Theo dõi lag/offset, repair/replay; phân biệt nguồn ghi và bản đọc |
| User yêu cầu hủy khi worker đang thực thi | Xác minh có thể hủy hay không, kiểm soát race; `CANCEL_REQUESTED` khác `CANCELLED` |

**Saga/compensation** giúp quản lý chuỗi tác vụ nhiều hệ thống khi không có một ACID transaction bao trùm tất cả. Ví dụ giữ tồn kho → thu tiền → tạo vận đơn: khi tạo vận đơn thất bại, hệ thống có thể hoàn tiền và trả tồn kho theo nghiệp vụ. Nhưng compensation **không phải rollback ACID tức thì** và bản thân bước bù trừ cũng có thể lỗi; lúc đó trạng thái đúng có thể là `COMPENSATING` hoặc `NEEDS_REVIEW`. Không gắn `FAILED` với lời hứa “không hề có side effect” nếu chưa xác minh.

Phân biệt timeout:

- **HTTP timeout:** Client đã ngừng chờ nhưng server có thể vẫn chạy.
- **Job deadline:** Hạn xử lý nghiệp vụ do server quyết định; có thể hủy, bù trừ hoặc chuyển review.
- **Downstream timeout:** Không chứng minh downstream không thực thi; cần idempotency/reconciliation.
- **SLO hội tụ:** Mục tiêu về độ trễ cập nhật projection (ví dụ p99 trong vài giây), không phải bảo đảm toán học của eventual consistency.

Một tác vụ chưa rõ kết quả **không nên tự động** chuyển thành `FAILED` chỉ vì lần polling cuối timeout. Hãy biểu diễn `RETRYING`, `AWAITING_CONFIRMATION` hoặc `NEEDS_REVIEW` tùy trạng thái mà hệ thống thật sự biết.

## 10. Bảo mật và khả năng quan sát

Operation monitor có thể lộ SKU, tình trạng thanh toán, địa chỉ giao hàng hoặc trạng thái xác minh danh tính. Bảo vệ nó như resource nghiệp vụ:

- Dùng authentication và kiểm tra **quyền theo tenant/chủ sở hữu** ở mỗi lần POST/GET. ID dạng UUID khó đoán không thay thế authorization; khi cần che sự tồn tại của operation người khác, trả 404 có chủ đích.
- Không đặt access token, khóa bí mật hay dữ liệu cá nhân vào URL theo dõi; không đưa stack trace, message queue payload, SQL hoặc nội dung đầy đủ của payment provider vào `error`.
- Rate limit cả endpoint nhận lệnh và GET polling. Một màn hình mở hàng nghìn tab cùng polling 100 ms cũng có thể gây sự cố dù job rất ít.
- Giới hạn kích thước command, số phần tử, concurrency theo tenant, và thời gian lưu operation/outbox/DLQ. Không giữ payload nhạy cảm lâu hơn cần thiết.
- Đặt `correlationId`/`traceId` đủ để liên kết POST → operation → outbox → consumer → projection. Khi đưa trace ID ra client, bảo đảm không lộ thông tin hạ tầng hoặc định danh người khác.

**Các số liệu nên đo:** latency từ nhận lệnh đến `SUCCEEDED`/`FAILED`; tỷ lệ pending lâu; queue age và depth; retry count; DLQ count; thời gian projection lag; số operation stuck; idempotency conflicts; POST được chấp nhận, GET polling, HTTP 429 và lỗi downstream. Cảnh báo theo SLO thay vì chỉ nhìn HTTP 2xx: hệ thống có thể liên tục trả `202` nhưng không có job nào hoàn thành.

## 11. Kiểm thử hợp đồng và sự cố phân tán

Để tránh “test xanh nhưng hệ thống mất đơn”, cần kiểm thử **invariant** cùng điều kiện race, không chỉ một happy path.

| Kiểm thử | Cách dựng tình huống | Kỳ vọng |
| --- | --- | --- |
| Nhận lệnh mới | POST hợp lệ với key mới | 202, `Location` tới operation, state `PENDING` |
| Input không hợp lệ | JSON sai schema/quyền không đủ | 400/422 hoặc 401/403; không tạo outbox |
| Lặp cùng key, cùng body | POST 2 lần/đồng thời qua nhiều instance | Một operation và một lệnh nghiệp vụ; trả lại monitor cũ |
| Lặp key, body khác | Thay quantity nhưng giữ key | 409, không tạo operation mới |
| Crash sau DB commit trước publish | Kill publisher | Outbox còn; publisher khác/restart sẽ phát lại |
| Broker giao message trùng | Gửi cùng `eventId` hai lần | Side effect nghiệp vụ áp dụng đúng một lần về mặt kết quả |
| Worker bị kill sau external call | Timeout/kill trước khi ghi kết quả | Retry/reconcile qua idempotency key; không thu tiền hai lần |
| Read model lag | Chặn consumer projection | Operation không hứa read readiness sai; sau replay bắt kịp |
| Trạng thái tới sai thứ tự | Gửi event RUNNING sau SUCCEEDED | Không đảo ngược terminal state/version |
| GET operation bị chặn | Tenant khác truy cập UUID thật | 404/403 theo hợp đồng, không rò dữ liệu |
| Polling quá dày | Nhiều client polling | Có quota, ETag/backoff, không nghẽn service |
| Quá hạn retention | GET operation đã được dọn | 404 hoặc 410 theo hợp đồng và hướng dẫn truy cập kết quả |
| Lỗi vĩnh viễn | Không đủ hàng, hết retry budget | Terminal state/error code rõ; không ẩn sau 202 mãi mãi |

### Ví dụ MockMvc kiểm tra response ban đầu

Giả sử mock service đã trả một operation ở `PENDING` và security test cấp principal hợp lệ:

~~~java
@Test
void postReturnsAcceptedWithOperationLocation() throws Exception {
    mockMvc.perform(post("/v1/orders")
            .with(jwt()) // Spring Security Test; cần claim tenant hợp lệ
            .header("Idempotency-Key", "cmd-2026-001")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "items": [{"sku":"BOOK-42","quantity":2}],
                  "shippingAddressId":"addr-09"
                }
                """))
        .andExpect(status().isAccepted())
        .andExpect(header().string("Location",
                startsWith("/v1/operations/")))
        .andExpect(jsonPath("$.state").value("PENDING"));
}
~~~

Đây là **trích đoạn test**; cần thêm mock `OperationService`, security principal/tenant adapter và import JUnit/MockMvc/Hamcrest trong ứng dụng. Test này chỉ chứng minh HTTP contract; cần integration test thật với PostgreSQL + outbox worker/broker (hoặc mô phỏng crash/restart) để chứng minh nhận lệnh bền vững và không lặp side effect.

### Tiêu chí chấp nhận quan trọng

1. Sau khi API trả `202`, **truy vấn DB tìm thấy operation và outbox đã commit**; worker sẽ có đường phục hồi để xử lý sau restart.
2. Gửi cùng một lệnh hai lần với cùng key ở hai instance không tạo hai operation/order/payment.
3. `GET` monitor không dùng HTTP 200 như chứng cứ thành công nghiệp vụ; client đọc `state` và `result`/`error`.
4. Khi read model trễ, API không hứa `SUCCEEDED` đồng nghĩa “đã hiện trên search” trừ khi có cơ chế kiểm chứng.
5. Khi worker thất bại, job đi đến retry, failure, compensation hoặc review có giám sát; không đứng `RUNNING` vô hạn.

## 12. Bài tập thực hành

**Bài 1 — Thiết kế HTTP.** Một API xuất báo cáo mất 30–90 giây. Hãy thiết kế `POST /v1/reports` với `Idempotency-Key` và `202 Accepted`, `Location` theo dõi, payload status khi `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`. Nêu thời gian lưu operation, cách client tải kết quả và cách thông báo lỗi hết dữ liệu đầu vào.

**Bài 2 — Phân biệt ba mốc.** `POST /v1/orders` trả 202 sau 20 ms; worker ghi order lúc 2 giây; Elasticsearch cập nhật lúc 4 giây. Tại giây thứ 3: (a) operation nên hiển thị trạng thái gì nếu định nghĩa thành công ở nguồn ghi? (b) `GET` qua Elasticsearch có thể thấy gì? (c) dùng `writeVersion`/`projectionStatus` hoặc nguồn ghi để bảo đảm user thấy đơn mới như thế nào?

**Bài 3 — Chống gửi trùng.** Hai request đồng thời cùng tenant, cùng `Idempotency-Key` và cùng body đến hai instance khác nhau. Hãy thiết kế unique constraint, transaction tạo operation/outbox và logic trả monitor cũ. Thử lại với body thay đổi nhưng giữ key; chọn status phù hợp.

**Bài 4 — Mô phỏng sự cố.** Viết integration test dừng worker ngay sau khi payment provider trả thành công nhưng trước khi cập nhật DB. Cho worker chạy lại và chứng minh hệ thống không thu tiền lần hai. Hãy chỉ ra chỗ nào bắt buộc cần idempotency/reconciliation từ payment provider và chỗ nào đủ dùng transaction nội bộ.

**Bài 5 — UI không gây hiểu nhầm.** Một màn hình chỉ hiện `"Đã tạo đơn!"` ngay sau 202. Viết lại luồng trạng thái UI cho người dùng, bao gồm khi mạng ngắt, khi job không đủ hàng, khi projection chưa bắt kịp và khi user mở lại trang sau vài phút.

**Gợi ý tự kiểm tra:** Bài 1 cần monitor URI, trạng thái terminal và retention; 202 không phải báo đã xuất báo cáo xong. Bài 2 ở giây thứ 3 có thể `SUCCEEDED` ở nguồn ghi nhưng projection còn `PENDING`; cần mốc phiên bản hoặc read-after-write. Bài 3 dùng unique theo tenant/action/key, trả lại operation cũ cho cùng fingerprint và `409` khi fingerprint khác. Bài 4 không thể kết luận payment chưa chạy khi timeout; phải đối soát theo idempotency/reference ở provider. Bài 5 cần hiển thị “Đang xử lý”, lưu monitor URI an toàn, polling có backoff, thông báo thành công/lỗi chỉ khi đã xác nhận và giải thích rõ trường hợp bản đọc còn trễ.
