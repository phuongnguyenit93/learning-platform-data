# Thiết kế khóa chống trùng cho POST có tác dụng phụ

## 1. Vì sao một POST có thể tạo hai tác dụng phụ?

Một client gửi `POST /v1/payments` để thu tiền. Server ghi nhận thanh toán thành công, nhưng kết nối mạng đứt trước khi client nhận `201 Created`. Client không biết yêu cầu đã hoàn tất hay chưa và gửi lại. Nếu server xử lý lần hai như một yêu cầu mới, khách hàng có thể bị thu tiền hai lần.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Payment API
    participant D as Database/Provider
    C->>A: POST /payments (yêu cầu X)
    A->>D: Tạo payment/thu tiền
    D-->>A: Thành công
    Note over A,C: Response bị mất trên mạng
    C->>A: Retry POST (vẫn yêu cầu X)
    A->>D: Nếu không chống trùng: thực hiện lần hai!
~~~

HTTP có thể được truyền lại bởi client, SDK hoặc một tầng trung gian đã được cấu hình retry. Vì thế, **“server đã làm xong”** và **“client biết server đã làm xong”** là hai trạng thái khác nhau. Không thể giải quyết sự bất định này chỉ bằng việc tăng timeout.

**Idempotency key** là một mã định danh cho **cùng một ý định nghiệp vụ**. Khi client lặp lại POST với **cùng khóa và cùng nội dung yêu cầu**, server nhận diện lần gọi trước, tránh thực hiện lại tác dụng phụ và cung cấp kết quả theo hợp đồng.

Bài thuộc chương **Lũy đẳng và thử lại** của module **INTEGRATION_API_REST**: thiết kế REST API qua resource, URI, HTTP method, status code và hợp đồng dữ liệu; kết hợp xác thực/phân quyền, xử lý lỗi, OpenAPI và kiểm thử với Java/Spring.

Sau bài này, bạn có thể thiết kế hợp đồng `Idempotency-Key`, chọn phạm vi và thời hạn lưu khóa, chống race giữa hai POST đồng thời, xử lý crash/timeout, tích hợp thanh toán hoặc hàng đợi và viết test chứng minh **một ý định không tạo hai tác dụng phụ**.

## 2. POST, retry và lũy đẳng là ba khái niệm khác nhau

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **HTTP idempotent method** | Gửi nhiều yêu cầu giống nhau có cùng hiệu ứng dự kiến lên trạng thái server như gửi một lần | PUT/DELETE có tính idempotent theo HTTP; response mỗi lần không nhất thiết giống nhau |
| **Retry** | Gửi lại sau timeout, mất kết nối hoặc lỗi tạm thời | Client gửi lại POST do không nhận được response |
| **Business idempotency** | Nhiều lần giao nhận cùng một ý định tạo tối đa một hiệu ứng nghiệp vụ tương ứng | Một yêu cầu thanh toán không tạo hai lần thu tiền |

**POST không mặc định idempotent.** Dù vậy, API có thể cung cấp cơ chế lũy đẳng cho một endpoint POST thông qua khóa chống trùng. Đó là **hợp đồng riêng của API**, không phải việc đổi semantics chuẩn của mọi POST trên Internet.

Một lỗi phổ biến là dựa vào payload: “hai POST có cùng số tiền và sản phẩm chắc chắn là một”. Điều này sai: người dùng **có thể chủ động mua cùng sản phẩm hai lần**. Phải phân biệt:

- **Retry cùng ý định:** giữ **cùng** `Idempotency-Key`, cùng payload có ý nghĩa.
- **Ý định mới, dù payload giống hệt:** dùng **khóa mới**.
- **Cùng khóa nhưng đổi payload:** **từ chối**, không đoán đó là retry hợp lệ.

### 2.1. Endpoint nào cần ưu tiên?

Ưu tiên áp dụng cho POST có hậu quả khó đảo ngược hoặc tốn kém: **thanh toán, tạo đơn, gửi yêu cầu hoàn tiền, phát hành phiếu, đặt chỗ, tạo lệnh chuyển tiền, gửi email/SMS nghiệp vụ**. Đối với endpoint chỉ truy vấn, dùng GET đúng semantics; không tạo cơ chế khóa POST để che đậy một API thiết kế sai phương thức.

## 3. Hợp đồng HTTP tối thiểu

Giả sử `POST /v1/orders` tạo một đơn. Client sinh một khóa ngẫu nhiên mới cho **một lần nhấn “Đặt hàng”**:

~~~http
POST /v1/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: "b3d4c0ec-4021-48e1-893f-20bd53acdd52"

{
  "cartId": "cart-51",
  "deliveryOption": "STANDARD"
}
~~~

Ví dụ dùng cú pháp header **`Idempotency-Key` là Structured Field String** (giá trị đặt trong dấu nháy kép); phải chọn một cách parse và công bố thống nhất với SDK/client. Nhiều API ngoài thực tế dùng UUID không có dấu nháy theo quy ước riêng; **không sao chép lẫn hai dạng** khi validator chỉ nhận một dạng. Mã UUID trong ví dụ chỉ là token opaque, **không** xác thực người dùng.

Lần đầu thành công:

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/o-900
Content-Type: application/json
Cache-Control: no-store

{
  "id": "o-900",
  "status": "CREATED",
  "totalAmount": "250000"
}
~~~

Nếu client **không nhận** response đầu tiên, nó retry với **cùng khóa và cùng payload**:

~~~http
POST /v1/orders HTTP/1.1
Idempotency-Key: "b3d4c0ec-4021-48e1-893f-20bd53acdd52"
Authorization: Bearer <access-token>
Content-Type: application/json

{"cartId":"cart-51","deliveryOption":"STANDARD"}

HTTP/1.1 201 Created
Location: /v1/orders/o-900
Content-Type: application/json
Cache-Control: no-store

{"id":"o-900","status":"CREATED","totalAmount":"250000"}
~~~

API minh họa chọn **replay status, Location và body của kết quả đã lưu**. Một sản phẩm khác có thể trả `200 OK` cho replay nếu tài liệu hóa rõ; điều bất biến là **không tạo đơn thứ hai** và client truy được resource đã tạo. Nếu response có header động như `Date`, `Request-Id`, không cần sao chép nguyên byte; nhưng những thành phần hợp đồng liên quan kết quả nghiệp vụ phải nhất quán.

### 3.1. Bốn tình huống quan trọng

| Trạng thái khóa trong phạm vi hợp lệ | Điều kiện | Hành vi gợi ý |
|---|---|---|
| **Chưa thấy** | Khóa mới, request hợp lệ | Đăng ký khóa nguyên tử, thực hiện một lần, lưu kết quả rồi phản hồi |
| **Đang xử lý** | Cùng khóa, cùng fingerprint, request trước chưa ngã ngũ | Trả `409 Conflict` với mã `REQUEST_IN_PROGRESS` và `Retry-After`, hoặc chờ có giới hạn theo hợp đồng |
| **Đã hoàn tất** | Cùng khóa, cùng fingerprint | Trả lại kết quả đã lưu, **không chạy lại** side effect |
| **Khác nội dung** | Cùng khóa nhưng fingerprint khác | Từ chối, ví dụ `422 Unprocessable Content` với mã `IDEMPOTENCY_KEY_REUSED` |

Ví dụ lỗi khi cùng khóa nhưng đổi giỏ hàng:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/idempotency-key-reused",
  "title": "Unprocessable Content",
  "status": 422,
  "code": "IDEMPOTENCY_KEY_REUSED",
  "detail": "Khóa đã được dùng cho một yêu cầu khác."
}
~~~

**Không có một bảng mã lỗi bắt buộc cho mọi triển khai idempotency.** Ví dụ dùng 422 cho key/payload không tương thích, 409 cho in-progress; một API khác có thể dùng 409 cho cả hai nếu hợp đồng mô tả rõ. Nếu endpoint **bắt buộc** header mà client không gửi, trả 400 với Problem Details và hướng dẫn sửa request.

### 3.2. Chọn thời gian lưu khóa

Server cần công bố **retention window**, ví dụ **24 giờ từ lần tiếp nhận đầu tiên** (chỉ là con số minh họa). Client chỉ có thể trông chờ replay trong thời hạn đó. **Hết TTL không đồng nghĩa tác dụng phụ trước đây đã biến mất**: nếu cho tái dùng khóa sau khi xóa record mà không có ràng buộc nghiệp vụ khác, một retry muộn có thể tạo đơn mới.

Với thanh toán, hoàn tiền hoặc giao dịch tài chính, cân nhắc **tombstone/dedup theo business ID lâu hơn**, hạn chế tái sử dụng key hoặc cơ chế tra cứu giao dịch độc lập. Không quảng bá “exactly once mãi mãi” khi ledger chỉ lưu 24 giờ.

## 4. Thiết kế khóa: ai tạo, thuộc phạm vi nào và gắn với dữ liệu gì?

### 4.1. Sinh khóa tại client

Một lựa chọn là UUID ngẫu nhiên (ví dụ UUIDv4), hoặc token có entropy tương đương. Client nên:

1. Sinh khóa **một lần** khi bắt đầu ý định tạo đơn/thanh toán.
2. Giữ khóa qua timeout, retry, reload hoặc chuyển mạng nếu vẫn là **cùng ý định**.
3. Không tái sử dụng khóa cho thao tác mới dù payload vô tình giống nhau.
4. Không đặt access token, email, thông tin thẻ hay dữ liệu cá nhân vào key.

**Không dùng timestamp một mình** làm khóa: hai tab hoặc nhiều thiết bị có thể sinh cùng giá trị. Một khóa dễ đoán cũng có thể trở thành cách gây nhiễu nếu hệ thống không scope và rate-limit đúng.

### 4.2. Phạm vi (scope) của key

Lưu chỉ theo `key` toàn cục có thể khiến hai tenant gửi trùng khóa và ảnh hưởng nhau. Một phạm vi thường dùng:

~~~text
(tenantId, authenticatedPrincipalId, operationId, idempotencyKey)
~~~

Ở đây `operationId` có thể là định danh cố định cho `POST /v1/orders`, **không phải chuỗi path thô**. Nếu sản phẩm cần nhiều principal của cùng tenant có thể retry cùng một tác vụ ủy quyền, phạm vi có thể là `(tenantId, operationId, key)`, nhưng phải có chính sách xác thực/quyền khi đọc lại kết quả. Chọn phạm vi theo **mô hình sở hữu ý định**, không áp một tổ hợp cho mọi dịch vụ.

**Không lấy tenantId hoặc principalId từ body do client tự khai.** Phải lấy từ thông tin đã xác thực; mọi lần replay vẫn đi qua xác thực và kiểm tra quyền được phép biết kết quả.

### 4.3. Fingerprint của request

Để ngăn “cùng khóa, khác payload”, lưu thêm **request fingerprint**:

~~~text
fingerprint = SHA-256(
    operationId
    + canonicalMethodAndPath
    + canonicalSemanticallyRelevantHeaders
    + canonicalValidatedRequestBody
)
~~~

Đây là **công thức khái niệm**. Trong triển khai cần định nghĩa serialization không nhập nhằng, giới hạn kích thước, encoding và version của fingerprint. Tránh nối chuỗi không có độ dài/ranh giới vì có thể khiến hai bộ dữ liệu khác nhau tạo cùng chuỗi đầu vào.

Một số quyết định cần ghi rõ:

- JSON key order/whitespace có được coi là tương đương không? Nếu có, dùng **canonical JSON/DTO đã validate**, không hash raw bytes.
- Nếu API có trường tùy chọn có default, cần quyết định `{"deliveryOption":"STANDARD"}` và `{}` có cùng ý nghĩa không.
- Các header ảnh hưởng kết quả như currency, locale, API version hoặc target resource có được đưa vào fingerprint không?
- Dữ liệu nhạy cảm có cần đưa vào fingerprint dưới dạng **hash/HMAC có khóa** để tránh lưu plain text không?
- Đổi thuật toán hoặc schema validation sau deploy có làm các key trong cửa sổ retention trở thành “khác payload” không? Lưu `fingerprintVersion` khi cần.

**Không dùng fingerprint làm idempotency key thay client**: hai yêu cầu mua hàng hợp lệ giống hệt nhau có thể là hai ý định khác nhau.

## 5. Trạng thái ledger và hai kiểu xử lý

**Idempotency ledger** là bản ghi bền vững cho biết một ý định đã được tiếp nhận và có kết quả gì. Cần quyết định cơ chế dựa trên loại side effect.

~~~mermaid
stateDiagram-v2
    [*] --> PROCESSING: Claim key thành công
    PROCESSING --> SUCCEEDED: Business effect commit
    PROCESSING --> FAILED_FINAL: Lỗi nghiệp vụ cuối cùng
    PROCESSING --> NEEDS_RECONCILIATION: Outcome bên ngoài chưa rõ
    NEEDS_RECONCILIATION --> SUCCEEDED: Xác nhận đã hoàn tất
    NEEDS_RECONCILIATION --> FAILED_FINAL: Xác nhận chưa thực hiện
    PROCESSING --> PROCESSING: Retry/lease takeover có kiểm soát
~~~

**Trạng thái trên là mô hình logic**, không bắt buộc persist đủ bốn trạng thái cho mọi endpoint. Hai kiến trúc thường gặp:

**A. Side effect trong cùng database transaction.** Có thể giữ việc **claim key + tạo Order + lưu response** trong **một transaction**. Nếu process crash trước commit, cả ba rollback. Bản ghi `PROCESSING` có thể chỉ tồn tại bên trong transaction chưa commit; request đồng thời đợi khóa/unique constraint. Mô hình này đơn giản và mạnh nếu mọi side effect đều ở cùng database.

**B. Side effect qua hệ thống bên ngoài.** Thanh toán qua payment provider, gửi email hoặc publish tới broker **không nằm trong transaction database** của API. Cần lưu trạng thái xử lý bền vững, claim theo lease/fencing, dùng idempotency của provider hoặc outbox, và có **reconciliation** khi kết quả chưa rõ. Đừng đánh dấu `FAILED_FINAL` chỉ vì mạng timeout sau khi provider có thể đã thu tiền.

### 5.1. Những bất biến của ledger

| Bất biến | Lý do |
|---|---|
| Một scope/key có **tối đa một record** | Chống hai handler độc lập cùng sở hữu một ý định |
| Fingerprint không đổi trong cửa sổ hiệu lực | Chặn cùng khóa cho payload khác |
| Kết quả cuối được lưu bền vững | Retry sau crash trả được kết quả cũ |
| Claim quyền xử lý phải **nguyên tử** | Chống race cùng lúc |
| Không replay kết quả cho principal không được phép | Idempotency không phải cơ chế vượt quyền |
| Khi chưa biết kết quả side effect, không thực hiện lại bằng key mới | Tránh nhân đôi trong khoảng bất định |
| Retention và cleanup không xóa mất bảo đảm nghiệp vụ đã hứa | Retry muộn không tạo duplicate ngoài ý muốn |

Một record `SUCCEEDED` thường lưu status, Location/resource ID và body (hoặc tham chiếu bền vững tới kết quả). Nếu response chứa thông tin nhạy cảm, cần mã hóa, hạn chế quyền đọc và thời hạn lưu phù hợp; **không** lưu Authorization header hoặc thông tin thẻ đầy đủ vào ledger.

## 6. Mẫu A: POST tạo đơn trong một database transaction

Nếu tạo đơn và idempotency ledger nằm trong cùng PostgreSQL database, có thể dùng **unique constraint + transaction** thay vì Redis lock hay `synchronized` trong một instance. Khóa in-memory **không bảo vệ được** nhiều pod/instance và biến mất khi process restart.

### 6.1. Lược đồ lưu dấu request

~~~sql
CREATE TABLE idempotency_requests (
    tenant_id       UUID        NOT NULL,
    principal_id    UUID        NOT NULL,
    operation_id    TEXT        NOT NULL,
    idem_key        TEXT        NOT NULL,
    request_hash    BYTEA       NOT NULL,
    state           TEXT        NOT NULL
                    CHECK (state IN ('PROCESSING', 'SUCCEEDED', 'FAILED_FINAL')),
    http_status     INTEGER,
    resource_uri    TEXT,
    response_json   JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, principal_id, operation_id, idem_key)
);
~~~

Đây là **schema minh họa**. Với ứng dụng thật, chọn kiểu khóa phù hợp, index phục vụ cleanup, hạn dung lượng response, mã hóa và chính sách xóa dữ liệu. `request_hash` được tính từ payload đã canonicalize, **không lưu nội dung nhạy cảm nguyên văn chỉ để đối chiếu**.

### 6.2. Claim key và tạo resource nguyên tử

Phác thảo transaction:

~~~sql
BEGIN;

-- Chỉ một transaction có thể tạo record cho scope/key này.
INSERT INTO idempotency_requests (
    tenant_id, principal_id, operation_id, idem_key,
    request_hash, state, expires_at
)
VALUES (
    :tenantId, :principalId, 'CREATE_ORDER', :key,
    :fingerprint, 'PROCESSING', :expiresAt
)
ON CONFLICT DO NOTHING;

-- Khóa hàng ledger thuộc scope để phân nhánh dựa vào kết quả thật.
SELECT request_hash, state, http_status, resource_uri, response_json
FROM idempotency_requests
WHERE tenant_id = :tenantId
  AND principal_id = :principalId
  AND operation_id = 'CREATE_ORDER'
  AND idem_key = :key
FOR UPDATE;

-- Nếu đã tồn tại:
--   hash khác -> từ chối, KHÔNG tạo đơn
--   SUCCEEDED / FAILED_FINAL -> dùng kết quả theo policy
-- Nếu do transaction này vừa tạo:
--   kiểm tra ràng buộc nghiệp vụ, INSERT orders ...
--   UPDATE idempotency_requests SET state='SUCCEEDED',
--       http_status=201, resource_uri=:location,
--       response_json=:response WHERE ...;
COMMIT;
~~~

Trong PostgreSQL, hai transaction cùng `INSERT ... ON CONFLICT` cho cùng primary key sẽ được **phối hợp qua unique index**; transaction đến sau có thể **đợi** transaction đầu hoàn tất. Sau đó nó đọc ledger đã commit và replay thay vì tạo lại đơn. Cần đặt timeout lock/query hợp lý và trả lỗi **đang xử lý** theo hợp đồng nếu không thể đợi. Không giữ transaction mở trong lúc gọi payment provider hoặc HTTP bên ngoài.

**Điểm cần phân biệt:** trong mẫu A, trạng thái `PROCESSING` ban đầu được ghi **cùng transaction** tạo Order và kết quả; nếu process chết trước `COMMIT`, cả bản ghi ledger lẫn Order rollback. Không có một record `PROCESSING` đã commit bị “kẹt” để tự takeover. Nếu service cố ý commit `PROCESSING` trước và thực hiện side effect ở transaction khác, đó là **mẫu B**, cần lease/reconciliation.

### 6.3. Unique constraint nghiệp vụ vẫn cần thiết

Ledger phân biệt một ý định thông qua key, nhưng **không** tự chứng minh client không tạo hai đơn cùng giỏ bằng **hai khóa khác nhau**. Nếu nghiệp vụ yêu cầu “mỗi checkout session chỉ tạo một đơn”, đặt thêm một **business uniqueness constraint** như `(tenant_id, checkout_session_id)`.

Đừng dùng `UNIQUE(tenant_id, cart_id)` theo phản xạ nếu một giỏ có thể được checkout nhiều lần một cách hợp lệ. Thiết kế invariant từ **định nghĩa nghiệp vụ**, không suy ra từ tên cột.

### 6.4. Kết quả lỗi nào được lưu?

Một chính sách rõ ràng có thể là:

- **Request sai cú pháp/chưa được xác thực:** trả 400/401 trước khi claim key, không lưu outcome.
- **Đã claim, nhưng nghiệp vụ từ chối dứt điểm** (ví dụ sản phẩm bị cấm tại thời điểm xử lý): có thể lưu `FAILED_FINAL` với status/body để retry cùng key không đổi kết quả; công bố rõ nếu làm vậy.
- **Deadlock, DB outage hoặc lỗi mạng tạm thời trước commit:** rollback transaction; cho phép retry cùng key.
- **Đã commit side effect nhưng HTTP response bị mất:** ledger đã có kết quả; retry replay.
- **Outcome bên ngoài không rõ:** tuyệt đối không tự biến thành `FAILED_FINAL` rồi thực hiện lại bằng key mới; chuyển sang quy trình đối soát.

Lưu hay không lưu **mọi** lỗi 4xx/5xx không có câu trả lời chung. Mỗi endpoint phải quy định **điểm bắt đầu thực thi**, loại kết quả được nhớ và khi nào client được retry.

## 7. Mẫu B: thanh toán hoặc side effect ở hệ thống bên ngoài

Không thể đặt database của ứng dụng và hệ thống thanh toán của bên thứ ba trong cùng một local transaction. Một phương án thường dùng là **operation resource + transactional outbox + idempotency của provider + reconciliation**:

~~~mermaid
flowchart LR
    C["Client POST /payments + key K"] --> API["Payment API"]
    API --> DB[("DB: idempotency + payment intent + outbox")]
    DB --> W["Outbox worker"]
    W --> P["Payment provider với key ổn định"]
    P --> W
    W --> DB
    API --> C
    C --> STATUS["GET /payment-operations/{id}"]
    STATUS --> DB
~~~

### 7.1. Các bước quan trọng

1. **POST đầu:** xác thực/quyền, kiểm fingerprint; transaction ghi ledger `PROCESSING`, payment intent và outbox event, sau đó commit. Trả **202 Accepted** kèm `Location` của operation nếu chưa biết kết quả thu tiền.
2. **Worker:** nhận outbox (có thể nhiều lần), gọi provider bằng **cùng một provider idempotency key** suy ra từ operation ID đã lưu.
3. **Provider thành công:** lưu provider transaction ID, trạng thái thanh toán và kết quả operation; chỉ khi đó mới đánh dấu `SUCCEEDED`.
4. **Provider timeout hoặc response mơ hồ:** giữ trạng thái chưa xác định, **tra cứu qua provider transaction/reference** hoặc webhook đã xác minh. Không gọi thu tiền lần nữa bằng một key mới.
5. **Retry từ client:** cùng key và fingerprint trả về **cùng operation ID/trạng thái hiện hành**, không tạo payment intent/charge thứ hai.

Ví dụ response ban đầu:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/payment-operations/op-784
Content-Type: application/json
Cache-Control: no-store

{"id":"op-784","status":"PROCESSING","paymentId":null}
~~~

Client có thể theo dõi `GET /v1/payment-operations/op-784` sau khi xác thực. `202` chỉ nói server **đã tiếp nhận để xử lý**, không phải **đã thu tiền thành công**.

### 7.2. Lease, fencing và worker trùng

Nếu ledger `PROCESSING` đã commit, một worker có thể chết. Một worker khác cần quyền tiếp quản thông qua **lease có thời hạn**, owner ID và **fencing token tăng đơn điệu** hoặc kiểm tra version có điều kiện. Tăng token khi takeover; mọi worker ghi kết quả phải chứng minh token của mình còn hợp lệ.

Tuy nhiên, **fencing chỉ bảo vệ những hệ thống thực sự kiểm tra token**. Nó không thể thu hồi một lệnh thu tiền đã đi tới provider. Vì vậy provider idempotency, tra cứu outcome và unique business reference vẫn quan trọng.

### 7.3. Giới hạn của “exactly once”

Trong hệ phân tán, request, event và callback có thể được giao **at least once**. Không thể bảo đảm tuyệt đối rằng một side effect ở mọi hệ thống ngoài sẽ thực hiện đúng một lần chỉ vì API giữ một bảng key. Mục tiêu thực tế là **một hiệu ứng nghiệp vụ duy nhất có thể kiểm chứng**, nhờ tổ hợp ledger, transaction, khóa duy nhất, provider idempotency, outbox và reconciliation.

Đặc biệt, nếu provider **không hỗ trợ idempotency hoặc truy vấn bằng business reference**, cần chính sách dừng retry mù, đối soát/hỗ trợ thủ công và ghi rõ giới hạn bảo đảm. Thời hạn key ở provider có thể **ngắn hơn** thời hạn ledger nội bộ; phải thiết kế theo cửa sổ bảo đảm yếu hơn.

## 8. Client retry đúng cách

Một client tốt **giữ nguyên key** khi retry, không retry vô hạn và biết phân biệt lỗi tạm thời với lỗi nghiệp vụ.

| Tín hiệu | Phản ứng client gợi ý |
|---|---|
| Timeout/mất kết nối, không rõ server đã commit | Retry **cùng key và cùng payload**, hoặc tra cứu operation |
| `409 REQUEST_IN_PROGRESS` | Chờ `Retry-After` nếu có, dùng backoff + jitter, giữ key |
| `202 Accepted` + operation URI | Theo dõi operation bằng GET, không tạo request mới |
| `201` replay thành công | Dùng lại resource đã tạo, kết thúc retry |
| `422 IDEMPOTENCY_KEY_REUSED` | Không retry mù; kiểm tra vì sao payload khác |
| `400` thiếu/sai key | Sửa request; không lặp y hệt vô hạn |
| `401/403` | Xử lý xác thực/phân quyền; key không cấp quyền |
| `429/503` | Retry có giới hạn theo `Retry-After` và chính sách, cùng key |
| `500` sau side effect có thể đã xảy ra | Coi outcome là **không chắc chắn**; retry an toàn cùng key hoặc tra cứu trạng thái |

**Ví dụ backoff:** 0,5 s → 1 s → 2 s → 4 s, thêm jitter và giới hạn tổng thời gian; các con số chỉ mang tính minh họa. Không retry mọi 4xx. Nếu request đã `202`, tốt nhất theo dõi operation resource thay vì liên tục POST.

Khi người dùng bấm lại sau khi màn hình reload, cần phân biệt **retry ý định cũ** với **lệnh mới thật sự**. Cách thiết kế state frontend/SDK và thời hạn key phải ăn khớp; nếu mỗi lần nhấn lại sinh key mới, cơ chế phía server không giúp chống trùng giữa hai key.

## 9. Java/Spring Boot: service tạo đơn có ledger

Ví dụ dùng **Java 17+, Spring Boot 3, Spring MVC và PostgreSQL**. Các class dưới đây là **mã thiết kế có chủ đích**, không phải ứng dụng chạy độc lập: cần bổ sung repository JDBC, mapper, security config, exception, entity và migration DB. Logic quan trọng là **transaction + unique constraint + outcome được lưu trước commit**.

### 9.1. DTO và controller

~~~java
record CreateOrderRequest(
    @NotBlank String cartId,
    @NotBlank String deliveryOption
) {}

record SavedOutcome(
    int status,
    String location,
    String jsonBody
) {}

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderCreationService service;
    private final ActorFactory actors;

    OrderController(OrderCreationService service, ActorFactory actors) {
        this.service = service;
        this.actors = actors;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<String> create(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal Jwt jwt) {

        AuthenticatedActor actor = actors.fromVerifiedJwt(jwt);
        SavedOutcome result = service.create(actor, key, request);

        return ResponseEntity.status(result.status())
            .location(URI.create(result.location()))
            .contentType(MediaType.APPLICATION_JSON)
            .cacheControl(CacheControl.noStore())
            .body(result.jsonBody());
    }
}
~~~

Spring có thể tự trả `400` khi thiếu header bắt buộc hoặc body sai validation sau khi cấu hình phù hợp; nên chuẩn hóa bằng `ProblemDetail`. `ActorFactory` chỉ nhận `Jwt` đã được Spring Security xác thực; phải kiểm tra issuer/audience/tenant claim và quyền theo thiết kế ứng dụng. Mọi replay vẫn phải qua bộ lọc bảo mật.

### 9.2. Service dùng cùng transaction

~~~java
@Service
class OrderCreationService {
    private final IdempotencyRepository ledger;
    private final OrderRepository orders;
    private final OrderSecurity policy;
    private final FingerprintService fingerprints;
    private final OrderResponseSerializer serializer;

    // Constructor injection được lược bớt.

    @Transactional
    public SavedOutcome create(
            AuthenticatedActor actor,
            String rawKey,
            CreateOrderRequest request) {

        policy.requireCanCreate(actor);
        String key = parseAndValidateStructuredKey(rawKey);
        Scope scope = new Scope(
            actor.tenantId(), actor.userId(), "CREATE_ORDER", key
        );
        byte[] hash = fingerprints.forCreateOrder(request);

        // INSERT ... ON CONFLICT DO NOTHING, cùng transaction hiện tại.
        boolean newlyClaimed = ledger.tryClaim(scope, hash);

        // SELECT ... FOR UPDATE; ở PostgreSQL, claim trùng đồng thời
        // được phối hợp bởi unique index/transaction.
        LedgerRecord record = ledger.lock(scope);

        if (!newlyClaimed) {
            if (!MessageDigest.isEqual(hash, record.requestHash())) {
                throw new IdempotencyKeyReusedException(); // 422
            }
            if (record.state() != State.SUCCEEDED) {
                throw new RequestInProgressException(); // 409
            }
            policy.requireCanReadOutcome(actor, record.resourceId());
            return record.savedOutcome(); // Không tạo Order lần nữa.
        }

        // Chỉ request sở hữu claim mới được thực hiện nghiệp vụ.
        Order order = orders.createFromCart(actor, request);
        SavedOutcome outcome = new SavedOutcome(
            201,
            "/v1/orders/" + order.id(),
            serializer.toStoredJson(order)
        );

        // Ghi kết quả và Order trong CÙNG transaction.
        ledger.markSucceeded(scope, order.id(), outcome);
        return outcome; // Transaction interceptor commit trước khi trả controller.
    }
}
~~~

**Các method `parseAndValidateStructuredKey`, `FingerprintService`, `IdempotencyRepository` và các class nghiệp vụ là phần cần hiện thực.** Parser của header đã chọn phải kiểm tra Structured Field String/độ dài/entropy phù hợp; repository phải dùng đúng SQL/unique constraint ở Mục 6. Nếu một duplicate bị chặn bởi lock timeout trước khi đọc được record, map thành `REQUEST_IN_PROGRESS` để client retry, không biến thành một đơn mới.

Với **request đầu tiên**, hàm `orders.createFromCart` có thể kiểm tra tồn kho, tổng tiền, cart ownership và tạo Order. Với **replay**, không kiểm tra lại cart state như một lệnh tạo mới vì giỏ có thể đã được checkout sau lần đầu; chỉ kiểm tra **quyền được biết kết quả**. Phần fingerprint của request ban đầu phải được chuẩn hóa giống nhau trong cả hai lần gọi.

**Giới hạn quan trọng:** `markSucceeded` phải lưu đủ outcome trước commit. Nếu controller tạo JSON response sau khi transaction đã commit nhưng ledger chỉ lưu resource ID, client replay có thể thấy representation **đã thay đổi**, không nhất thiết giống response đầu tiên. Điều đó có thể là một hợp đồng khác hợp lệ, nhưng phải công bố rõ; ví dụ này chọn lưu body kết quả ban đầu.

### 9.3. Ánh xạ lỗi theo Problem Details

~~~java
@RestControllerAdvice
class IdempotencyProblemHandler {

    @ExceptionHandler(IdempotencyKeyReusedException.class)
    ResponseEntity<ProblemDetail> reused() {
        return problem(
            HttpStatus.UNPROCESSABLE_ENTITY,
            "IDEMPOTENCY_KEY_REUSED",
            "Khóa đã được dùng cho request khác."
        );
    }

    @ExceptionHandler(RequestInProgressException.class)
    ResponseEntity<ProblemDetail> inProgress() {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Request cùng khóa đang được xử lý."
        );
        body.setProperty("code", "REQUEST_IN_PROGRESS");
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .header(HttpHeaders.RETRY_AFTER, "2")
            .cacheControl(CacheControl.noStore())
            .body(body);
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String code, String detail) {
        ProblemDetail body =
            ProblemDetail.forStatusAndDetail(status, detail);
        body.setProperty("code", code);
        return ResponseEntity.status(status)
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

Các exception tự định nghĩa cần được map phù hợp với transaction rollback. Với mô hình có `FAILED_FINAL`, service có thể replay một lỗi đã lưu theo policy; không áp `SUCCEEDED` như điều kiện duy nhất nếu API chủ động lưu cả kết quả thất bại cuối cùng.

## 10. OpenAPI: công bố key, replay và lỗi

Ví dụ rút gọn cho endpoint tạo đơn:

~~~yaml
openapi: 3.1.0
info:
  title: Order Creation API
  version: 1.0.0
paths:
  /v1/orders:
    post:
      operationId: createOrder
      summary: Tạo đơn hàng với idempotency key
      description: >
        Cùng key, cùng payload, cùng phạm vi trong 24 giờ sẽ không
        tạo đơn thứ hai. Replay kết quả thành công trả lại status,
        Location và body đã lưu. Key khác biểu diễn ý định mới.
      security:
        - bearerAuth: []
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          description: >
            Structured Field String, token ngẫu nhiên cho một ý định.
            Giữ nguyên key khi retry và không dùng lại với payload khác.
          schema:
            type: string
          example: '"b3d4c0ec-4021-48e1-893f-20bd53acdd52"'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [cartId, deliveryOption]
              properties:
                cartId:
                  type: string
                deliveryOption:
                  type: string
                  enum: [STANDARD, EXPRESS]
      responses:
        "201":
          description: >
            Đã tạo đơn hoặc replay đúng kết quả tạo đơn trước đó.
          headers:
            Location:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "400":
          description: Thiếu key hoặc request sai cú pháp
        "401":
          description: Không xác thực hợp lệ
        "403":
          description: Không có quyền tạo hoặc xem kết quả
        "409":
          description: Cùng key đang xử lý; có thể retry sau
          headers:
            Retry-After:
              schema:
                type: string
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
        "422":
          description: Cùng key nhưng request fingerprint khác
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    Order:
      type: object
      required: [id, status, totalAmount]
      properties:
        id:
          type: string
        status:
          type: string
        totalAmount:
          type: string
    Problem:
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
~~~

OpenAPI **không tự thực thi chống trùng**. Mô tả retention, key scope, cách replay, lỗi khi fingerprint khác, xử lý in-progress và hành vi sau khi hết hạn phải được bổ sung vào tài liệu vận hành/SDK và test contract. Nếu endpoint thanh toán bất đồng bộ trả `202`, cần **operation URI, schema trạng thái và các mã lỗi riêng**, không sao chép mô tả `201` của ví dụ tạo đơn đồng bộ.

## 11. Kiểm thử chứng minh không tạo trùng

Một unit test chỉ kiểm tra `Idempotency-Key` có mặt trong header **không chứng minh** hệ thống chống trùng. Cần test cả outcome HTTP **và** trạng thái nghiệp vụ, tốt nhất với PostgreSQL thực hoặc môi trường có hành vi locking tương đương production.

### 11.1. Ma trận test tối thiểu

| Ca | Tình huống | Kỳ vọng |
|---|---|---|
| K01 | Khóa mới, payload hợp lệ | `201`, một Order, ledger `SUCCEEDED` |
| K02 | Gửi lại cùng khóa/payload sau khi K01 commit | Cùng Order/Location/kết quả; số Order vẫn là **1** |
| K03 | Cùng khóa nhưng `cartId` hoặc `deliveryOption` khác | `422`, không tạo thêm Order |
| K04 | Khóa khác, payload giống K01; nghiệp vụ cho phép mua hai lần | Hai ý định độc lập; không bị dedup sai |
| K05 | Hai POST **đồng thời** cùng key/payload | Một business effect; request thứ hai replay hoặc nhận `409` đang xử lý |
| K06 | Hai POST đồng thời cùng key, payload khác | Một intent được claim; intent còn lại bị từ chối, không có hai effects |
| K07 | Crash/rollback trước commit trong mẫu A | Không có Order/ledger final của lần lỗi; retry có thể thực hiện |
| K08 | Commit thành công, mất HTTP response | Retry trả kết quả cũ, không thực hiện lại |
| K09 | Tenant B gửi key của tenant A | Không đọc/replay outcome của A; scope và quyền đúng |
| K10 | Cùng principal nhưng thiếu quyền khi replay | Trả lỗi quyền an toàn, không lộ result |
| K11 | Key hết hạn | Hành vi đúng hợp đồng; không tuyên bố dedup ngoài retention |
| K12 | Worker thanh toán nhận event hai lần | Cùng provider key, không tạo thêm charge |
| K13 | Provider timeout nhưng đã thu tiền | Reconcile rồi hoàn tất operation; không thu lại bằng key mới |
| K14 | Same key, JSON chỉ đổi whitespace/thứ tự field | Match hay mismatch đúng chính sách canonicalization |
| K15 | Same key nhưng đổi currency/API version có ảnh hưởng kết quả | Fingerprint không cho phép thực hiện dưới hợp đồng khác |

### 11.2. MockMvc minh họa: gửi lại sau khi đã commit

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderIdempotencyContractTest {
    @Autowired MockMvc mvc;
    @Autowired OrderRepository orders;

    @Test
    void replayKeepsOneOrderAndSameLocation() throws Exception {
        String key = "\"a4a294a1-197b-49cf-9ba9-5dc8bb05c926\"";
        String body =
            "{\"cartId\":\"cart-test-51\",\"deliveryOption\":\"STANDARD\"}";

        MvcResult first = mvc.perform(
                post("/v1/orders")
                    .with(jwt().jwt(j -> j
                        .subject("actor-1")
                        .claim("tenant_id", "tenant-test")
                    ))
                    .header("Idempotency-Key", key)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body)
            )
            .andExpect(status().isCreated())
            .andReturn();

        MvcResult replay = mvc.perform(
                post("/v1/orders")
                    .with(jwt().jwt(j -> j
                        .subject("actor-1")
                        .claim("tenant_id", "tenant-test")
                    ))
                    .header("Idempotency-Key", key)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body)
            )
            .andExpect(status().isCreated())
            .andReturn();

        assertEquals(
            first.getResponse().getHeader("Location"),
            replay.getResponse().getHeader("Location")
        );
        assertEquals(
            first.getResponse().getContentAsString(),
            replay.getResponse().getContentAsString()
        );
        assertEquals(1, orders.countForCheckout("cart-test-51"));
    }
}
~~~

Test trên là **khung minh họa**: cần import, fixture giỏ hợp lệ, repository query count và authorization đúng. `jwt()` của `spring-security-test` mô phỏng principal, **không xác minh token thật**; cần test tích hợp riêng cho token sai chữ ký/issuer/audience/hết hạn và claim tenant thiếu.

### 11.3. Test đồng thời mới phát hiện race

Chạy hai request song song bằng `ExecutorService` và `CountDownLatch`, cho cả hai cùng bắt đầu với **một key**. Lặp trên DB thực, đo kết quả và assert **chỉ một order/payment record**. Một request có thể nhận `201` replay hoặc `409` do lock timeout tùy implementation; test phải dựa vào **hợp đồng**, không áp đặt cả hai luôn 201.

Kiểm tra thêm tình huống: process chết sau khi đã claim nhưng **trước commit** (mẫu A), worker chết sau khi đã ghi `PROCESSING` (mẫu B), provider callback đến hai lần, và cleanup đúng TTL. Đối với external provider, dùng sandbox/fake có thể điều khiển “đã thu tiền nhưng response timeout” để xác nhận **reconciliation thay vì charge lần hai**.

## 12. Bài tập áp dụng: checkout và thanh toán

**Đề bài:** hệ thống bán hàng có hai endpoint:

~~~text
POST /v1/orders   -> tạo đơn từ giỏ hàng
POST /v1/payments -> thu tiền qua đối tác bên ngoài
~~~

Client có thể mất kết nối sau khi server commit. Một tenant có nhiều nhân viên, giỏ hàng có thể được checkout nhiều lần nếu người dùng thực sự bắt đầu giao dịch mới. Provider thanh toán hỗ trợ một key có hiệu lực **ngắn hơn** ledger nội bộ.

Hãy trả lời:

1. Tạo key và fingerprint cho hai endpoint thế nào để không dedup nhầm hai lần mua hợp lệ?
2. Nếu hai POST tạo đơn đến đồng thời cùng key, cần cơ chế nào ngoài `synchronized`?
3. Nếu charge timeout nhưng provider có thể đã thu tiền, server có nên tạo key mới và charge lại?
4. Khi replay cùng key nhưng deliveryOption khác, nên làm gì?
5. Khi nhân viên bị thu hồi quyền sau khi tạo đơn, retry key cũ có được xem kết quả không?

**Đáp án gợi ý:** mỗi **ý định** có key riêng; fingerprint gắn operation và request đã chuẩn hóa. Tạo Order dùng transaction cùng ledger và unique constraint; không dựa vào lock JVM. Thanh toán dùng operation ID, provider key ổn định, outbox và reconciliation, **không charge bằng key mới khi outcome chưa rõ**. Cùng key khác payload trả lỗi 422 theo hợp đồng đã chọn. Replay vẫn phải xác thực/phân quyền; nếu nhân viên không còn quyền xem Order thì không trả lại body nhạy cảm chỉ vì key đúng. Khi key provider hết hạn, cần tra cứu theo business reference hoặc có biện pháp dừng xử lý/đối soát, không tin TTL nội bộ là đủ.

## 13. Phản mẫu và checklist rà soát

| Phản mẫu | Hậu quả | Thay bằng |
|---|---|---|
| Server tự hash payload làm key | Hai giao dịch hợp lệ giống nhau bị gộp | Key theo **ý định** do client cấp |
| Sinh key mới cho mỗi lần retry | Retry trở thành giao dịch mới | Giữ key qua mất mạng/timeout |
| Chỉ lưu key trong Redis/in-memory, rồi ghi DB khác không nguyên tử | Crash giữa hai bước gây mismatch | Transaction cùng DB hoặc workflow/outbox phù hợp |
| `SELECT key` rồi `INSERT` không có unique constraint | Hai request cùng thấy “chưa có” | Unique index + claim nguyên tử |
| Lưu `PROCESSING` vĩnh viễn, không có cơ chế phục hồi | Request bị kẹt sau crash | Lease/fencing/reconciliation cho workflow dài |
| Chỉ lưu status, không lưu resource/outcome | Replay không biết giao dịch nào đã tạo | Outcome/operation ID bền vững |
| Retry charge bằng provider key mới sau timeout | Thu tiền lặp | Giữ provider key, tra cứu outcome |
| Cache lỗi 500 tạm thời như thất bại cuối cùng | Không thể phục hồi dù chưa có side effect | Policy lỗi rõ, reconciliation khi bất định |
| Cùng key nhưng payload khác vẫn chạy | Key mất ý nghĩa | Fingerprint và từ chối mismatch |
| Trả outcome cho người biết key mà không auth | Lộ tài nguyên của người khác | Scope theo identity, kiểm tra quyền replay |
| Xóa ledger đúng 24h rồi quảng bá “exactly once” | Retry muộn tạo trùng | Công bố TTL và business uniqueness/đối soát |

**Checklist triển khai:**

- [ ] Endpoint POST nào có side effect cần dedup đã được xác định rõ.
- [ ] Quy ước `Idempotency-Key` (cú pháp, độ dài, entropy, phạm vi, TTL) được công bố và SDK tuân thủ.
- [ ] Client tạo key cho **một ý định** và giữ nguyên khi retry; ý định mới dùng key mới.
- [ ] Fingerprint chuẩn hóa request và bao gồm những trường/phiên bản ảnh hưởng kết quả.
- [ ] Có unique constraint, claim nguyên tử và outcome bền vững; không chỉ dùng lock process.
- [ ] Với cùng DB, claim + business write + final outcome **cùng transaction**.
- [ ] Với hệ thống ngoài, có **provider idempotency, outbox, lease/fencing và reconciliation** khi cần.
- [ ] Đã định nghĩa 201/202 replay, 409 đang chạy, 422 key mismatch, 400 thiếu key và lỗi quyền.
- [ ] Replay vẫn xác thực và phân quyền; ledger không chứa credential/PII không cần thiết.
- [ ] Cleanup/TTL không phá bảo đảm nghiệp vụ; có metrics cho duplicate/replay/in-progress/conflict.
- [ ] Test có retry sau commit, crash, race song song, khác payload, cross-tenant và provider timeout.

### Nguồn tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): POST, PUT, idempotent methods, 201/202/409 và điều kiện HTTP.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): body lỗi có cấu trúc theo `application/problem+json`.
- [RFC 8941 — Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc8941): cú pháp Structured Field String cho hợp đồng header đã chọn.
- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0): mô tả header, request, response và lỗi.

**Điểm cần nhớ:** `Idempotency-Key` không phải phép màu biến POST thành “exactly once”. Nó là **mã của một ý định**, có hiệu lực khi đi kèm fingerprint, scope, unique constraint, transaction và kết quả bền vững. Với side effect bên ngoài, phải thêm provider idempotency và đối soát khi outcome bất định. Thiết kế tốt cho phép retry **cùng ý định** an toàn mà vẫn cho phép **ý định mới** được thực hiện độc lập.
