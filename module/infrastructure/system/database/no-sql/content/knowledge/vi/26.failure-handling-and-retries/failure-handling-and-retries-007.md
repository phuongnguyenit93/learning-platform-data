# Idempotency key, lưu kết quả xử lý và chống tạo bản ghi trùng

Một người dùng bấm **Đặt hàng** trên ứng dụng. Server tạo order thành công trong NoSQL, nhưng đúng lúc trả phản hồi, kết nối mạng bị ngắt. Ứng dụng không nhận được HTTP **201 Created**, nên sau vài giây gửi lại yêu cầu. Nếu mỗi lần nhận **POST /orders** đều tạo một bản ghi với ID mới, hệ thống có thể xuất hiện **hai đơn hàng cho cùng một lần bấm**. Trường hợp tương tự xảy ra khi giữ ghế, ghi điểm thưởng, tiếp nhận webhook, xử lý message hoặc yêu cầu thanh toán.

Vấn đề này không nhất thiết là lỗi mạng hiếm gặp. Trong hệ phân tán, một thao tác có thể **đã được áp dụng ở server nhưng kết quả không đến được client**. Client chỉ biết “không nhận được kết quả”, không thể tự kết luận “server chưa làm”. Khi request được gửi lại, ứng dụng cần phân biệt **một ý định được gửi nhiều lần** với **hai ý định độc lập**.

**Idempotency key** là định danh ổn định cho một **ý định nghiệp vụ**. Server dùng key để phát hiện request đã xử lý, từ chối sử dụng lại key với payload khác, và **trả lại kết quả đã lưu** khi client retry. Để chống tạo bản ghi trùng thật sự, key còn phải được gắn với **quy tắc uniqueness, giao dịch/conditional write, trạng thái xử lý và chính sách phục hồi** phù hợp với NoSQL đang dùng.

Bài học nằm trong chương **Lỗi phân tán và retry**, module **Database No SQL**. Ta sẽ xây một giao thức idempotent từ đầu đến cuối, giải thích các trạng thái **NEW / PROCESSING / COMPLETED / FAILED**, phân tích race khi nhiều client gửi cùng key, lưu kết quả để phát lại, xử lý timeout có kết quả không rõ, so sánh MongoDB, DynamoDB, Cassandra, Redis, message broker, outbox/inbox và các giới hạn khi gọi hệ thống bên ngoài. Trọng tâm là **không tạo hai hiệu ứng nghiệp vụ từ cùng một ý định**, chứ không chỉ “thêm một header vào HTTP”.

## 1. Hiểu đúng tình huống kết quả không rõ

Xét lịch sử sau:

~~~text
t1  Mobile App gửi CreateOrder(requestId=checkout-9001)
t2  API nhận request và ghi order-101 thành công
t3  Database xác nhận commit
t4  API gửi HTTP 201, nhưng kết nối bị đứt
t5  Mobile App timeout
t6  Mobile App gửi lại CreateOrder
~~~

Ở t5, có ít nhất ba khả năng:

1. Server chưa nhận request lần đầu.
2. Server nhận request nhưng chưa commit hoặc đã rollback.
3. Server đã commit thành công nhưng response bị mất.

Client **không có đủ bằng chứng** để chọn một khả năng chỉ từ lỗi timeout.

Nếu retry tạo ID mới:

~~~text
Lần 1 -> order-101
Lần 2 -> order-102
~~~

thì một lần checkout trở thành hai order. Nếu retry bằng cùng **idempotency key**, server có thể trả:

~~~text
Lần 1 -> order-101, response bị mất
Lần 2 -> phát lại response của order-101
~~~

Khi đó client nhận được kết quả ổn định dù request có thể đã chạy qua nhiều lần truyền mạng.

## 2. Định nghĩa idempotency ở mức thao tác

Trong toán học, một phép biến đổi **f** là idempotent nếu:

\[
f(f(x)) = f(x)
\]

Trong API, ngữ nghĩa tương tự nhưng phải xác định **đơn vị ý định**:

~~~text
Process(operationId=K, payload=P) nhiều lần
  -> chỉ một hiệu ứng nghiệp vụ của K
  -> những lần lặp hợp lệ nhận lại outcome của K
~~~

Đừng nhầm với:

~~~text
POST hai lần nhưng có hai Idempotency-Key khác nhau
  -> đây có thể là hai ý định hợp lệ, tùy contract
~~~

Ví dụ:

| Operation | Lặp không điều kiện | Điều cần bảo vệ |
|---|---|---|
| SET status=READY | Có thể cho cùng trạng thái cuối | Tránh side effects khác hoặc ghi lùi |
| INCREMENT views +1 | Tăng hai lần | Mỗi view event chỉ tăng một lần nếu cần exact count |
| CREATE order với ID mới | Tạo hai bản ghi | Cùng checkout intent chỉ có một order |
| RESERVE seat | Có thể giữ cùng ghế hai lần hoặc phát hai xác nhận | Unique reservation/state transition |
| CAPTURE payment | Có thể thu tiền hai lần | Provider idempotency và ledger |
| SEND email | Có thể gửi hai email | Dedup intent hoặc chấp nhận at-least-once rõ ràng |

**Idempotent về trạng thái cuối** không đồng nghĩa **mọi side effect chỉ xảy ra một lần**. Chẳng hạn hai lần SET cùng giá trị có thể vẫn kích hoạt hai notification nếu hệ thống tự phát event sau mỗi request.

## 3. Idempotency khác retry, dedup, uniqueness và transaction

| Khái niệm | Trả lời câu hỏi | Không tự giải quyết |
|---|---|---|
| **Retry** | Có gửi lại request thất bại/timeout không? | Tạo trùng nếu effect không idempotent |
| **Idempotency key** | Những request nào thuộc cùng một ý định? | Atomicity/uniqueness nếu không được thực thi |
| **Deduplication** | Đã thấy operation ID này chưa? | Race giữa kiểm tra và ghi |
| **Unique constraint** | Có thể tồn tại hai records cùng khóa logic không? | Trả lại outcome/response từ request cũ |
| **Conditional write/CAS** | Một chuyển trạng thái có còn hợp lệ không? | Ghi nhận kết quả của intent cho retry |
| **Transaction** | Các thay đổi có commit cùng nhau không? | External effect ngoài phạm vi transaction |
| **Outbox/inbox** | Event có thể gửi/nhận lại an toàn không? | Mặc nhiên đảm bảo provider ngoài chỉ tác động một lần |
| **Fencing token** | Owner cũ có bị chặn sau thế hệ mới không? | Retry cùng owner với cùng effect |

Một hệ thống đúng thường **kết hợp nhiều lớp**: idempotency key xác định ý định, unique index/conditional mutation xử lý cạnh tranh, transaction gắn marker với effect, saved response giải quyết retry và outbox/inbox xử lý phần bất đồng bộ.

## 4. At-most-once, at-least-once và “exactly-once effect”

Ba cách nhìn thường gặp:

- **At-most-once attempt:** không chủ động gửi lại nếu mất response; có thể bỏ lỡ effect.
- **At-least-once delivery:** retry/redelivery cho đến khi có xác nhận phù hợp; có thể nhận cùng event nhiều lần.
- **Effect một lần theo logical ID:** cho phép giao lại nhiều lần nhưng chỉ áp dụng một hiệu ứng cho một ID trong phạm vi đã định nghĩa.

~~~text
Network delivery: E1, E1, E1
Business effect:  +1
~~~

Để đạt kết quả này thường cần:

\[
\text{stable identity}
+\text{atomic dedup/effect}
+\text{recovery}
\]

Không nên tuyên bố “exactly once toàn hệ” nếu còn payment provider, email, object storage hoặc hệ độc lập không tham gia cùng một giao thức. Một bảo đảm thực tế nên ghi:

> “Trong phạm vi tenant, operation type, idempotency key và thời hạn lưu bản ghi đã công bố, hệ không tạo nhiều hơn một order được commit cho cùng request hợp lệ.”

Đây là lời hứa có thể thiết kế, kiểm thử và giám sát.

## 5. Chọn đúng đối tượng cho idempotency key

Ví dụ client gửi:

~~~http
POST /v1/orders HTTP/1.1
Authorization: Bearer <token>
Idempotency-Key: checkout-9001
Content-Type: application/json

{
  "cartId": "cart-77",
  "shippingAddressId": "addr-12",
  "currency": "VND"
}
~~~

**checkout-9001** đại diện cho một **lần xác nhận mua hàng**, không phải mọi thao tác của tài khoản trong một ngày.

Các nguyên tắc:

1. **Một ý định → một key ổn định** qua timeout, retry, reconnect và đổi node.
2. **Ý định khác → key khác**, kể cả payload tình cờ giống nhau nếu người dùng thực sự muốn mua lần nữa.
3. Key có **phạm vi uniqueness** rõ: tenant, principal/account, operation type và namespace/phiên bản API nếu cần.
4. Server vẫn xác thực danh tính và quyền; key không phải mật khẩu.
5. Một key đã dùng với payload P không được âm thầm đại diện cho payload Q.
6. Key phải tồn tại đủ lâu cho mọi retry hợp lệ và cơ chế replay.

Một key có thể là UUID ngẫu nhiên do client tạo, hoặc một định danh nghiệp vụ ổn định. Chọn kiểu nào tùy hệ thống, nhưng phải đảm bảo không vô tình **sinh UUID mới trong mỗi attempt**.

## 6. Phân biệt request ID, trace ID và idempotency key

~~~text
User checkout intent:
  Idempotency-Key = checkout-9001

HTTP attempt 1:
  X-Request-Id = req-a
  traceId = trace-01

HTTP attempt 2:
  X-Request-Id = req-b
  traceId = trace-02
~~~

Hai lần gửi có thể có **request ID và trace ID khác nhau**, nhưng phải giữ **idempotency key giống nhau**.

| ID | Mục tiêu | Cần ổn định qua retry? |
|---|---|---|
| **Idempotency key** | Gắn các attempts với một logical operation | **Có** |
| **Request ID** | Nhận diện một HTTP attempt | Không nhất thiết |
| **Trace ID** | Truy vết một chuỗi xử lý | Có thể khác theo policy tracing |
| **Order ID** | Nhận diện order đã tạo | Ổn định sau khi được quyết định |
| **Payment intent ID** | Nhận diện ý định thanh toán | Ổn định cho cùng intent |
| **Message ID** | Nhận diện message/event trong queue | Phụ thuộc broker, không luôn là logical intent |
| **Fencing token** | Thế hệ quyền của worker | Thay khi owner/lease generation đổi |

**Dùng request ID sinh ở API Gateway làm idempotency key** thường sai: mỗi attempt được gateway tạo ID mới, nên server không nhận ra retry.

## 7. Một key cần gắn với nội dung request

Nếu client gửi:

~~~text
Idempotency-Key: checkout-9001
Payload A: cartId=cart-77, currency=VND
~~~

và sau đó:

~~~text
Idempotency-Key: checkout-9001
Payload B: cartId=cart-88, currency=VND
~~~

thì đây không còn là một retry tương đương. Server phải **phát hiện reuse key với nội dung khác**:

~~~text
Existing key K with fingerprint(P)
Incoming K with fingerprint(Q)

If fingerprint(P) != fingerprint(Q):
  return IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST
~~~

Không được âm thầm trả order của cart-77 cho yêu cầu cart-88; cũng không được tự tạo order mới cho cùng key.

### Fingerprint nên tính trên những trường nào?

Thường gồm:

- HTTP method và operation type.
- API/schema version nếu ảnh hưởng semantics.
- Tenant/account đã xác thực.
- Những trường payload **ảnh hưởng hiệu ứng nghiệp vụ**.
- Đơn vị tiền/currency, resource IDs, số lượng, options.

Không nên đưa những trường không liên quan như **traceId hoặc timestamp attempt** vào fingerprint, nếu không retry hợp lệ lại bị xem là request khác.

## 8. Canonicalization trước khi hash payload

Hai JSON sau có thể có cùng ý nghĩa:

~~~json
{"cartId":"cart-77","currency":"VND"}
~~~

~~~json
{"currency":"VND","cartId":"cart-77"}
~~~

Nếu hash raw bytes, chúng có thể có fingerprint khác chỉ vì **thứ tự field**.

Quy trình khái niệm:

~~~text
1. Validate request theo schema.
2. Chuẩn hóa các field có semantics tương đương.
3. Bỏ trường transport-only như traceId.
4. Serialize canonical form ổn định.
5. Tính fingerprint bằng hash thích hợp.
6. Lưu fingerprint cùng idempotency key.
~~~

Ví dụ:

~~~json
{
  "operation": "CreateOrder:v1",
  "tenantId": "shop-a",
  "cartId": "cart-77",
  "currency": "VND",
  "shippingAddressId": "addr-12"
}
~~~

**Không chuẩn hóa bừa những trường có nghĩa khác nhau.** Ví dụ 10.0 và 10.00 có thể tương đương cho một số amount nhưng khác về cách định dạng ở một số workflow; thứ tự danh sách sản phẩm có thể có hoặc không có ý nghĩa tùy API. Canonicalization phải tuân theo **business contract**, không chỉ sắp xếp JSON cho đẹp.

Không lưu raw card numbers, secrets hoặc payload nhạy cảm không cần thiết trong bản ghi dedup; có thể lưu fingerprint và bản response đã lọc.

## 9. Phạm vi key: tenant, tài khoản và loại thao tác

Một bảng idempotency nên có logical key:

~~~text
(tenantId, operationType, idempotencyKey)
~~~

Ví dụ:

~~~text
("shop-a", "CreateOrder", "checkout-9001")
("shop-b", "CreateOrder", "checkout-9001")
("shop-a", "CapturePayment", "checkout-9001")
~~~

Ba bản ghi này **không được vô tình coi là cùng một operation**, vì thuộc tenant hoặc loại thao tác khác nhau.

Mặt khác, API cần tránh để người dùng đoán key của người khác rồi lấy **saved response chứa thông tin order**. Phải xác thực tenant/account trước khi lookup và replay response. Một idempotency key không thay thế authorization.

### Cẩn thận với key do client tự chọn

Nếu client gửi **key="1"** cho mọi checkout, server sẽ coi mọi checkout dùng lại cùng một ID trong scope đã định. Nên:

- Yêu cầu độ dài/format và entropy phù hợp.
- Rate limit và giới hạn số key mới được tạo.
- Đối chiếu payload fingerprint.
- Tài liệu hóa việc tạo key ở SDK/mobile.
- Không chấp nhận key rỗng khi endpoint yêu cầu idempotency.

## 10. Lưu kết quả xử lý, không chỉ lưu dấu “đã thấy”

Một bản ghi tối thiểu có thể là:

~~~json
{
  "tenantId": "shop-a",
  "operationType": "CreateOrder",
  "idempotencyKey": "checkout-9001",
  "requestFingerprint": "sha256:...",
  "status": "COMPLETED",
  "businessResourceId": "order-101",
  "responseHttpStatus": 201,
  "responseBody": {
    "orderId": "order-101",
    "status": "PENDING_PAYMENT"
  },
  "createdAt": "2026-11-14T09:00:00Z",
  "completedAt": "2026-11-14T09:00:01Z",
  "expiresAt": "2026-11-21T09:00:00Z"
}
~~~

**Saved response** giúp client retry sau timeout nhận lại cùng outcome mà không phải:

- Tạo order mới.
- Tính lại giá/khuyến mãi trong một thời điểm khác.
- Phát thêm event hoặc gửi email một lần nữa.
- Suy đoán từ GET nếu API đã có outcome ổn định.

Tùy nhu cầu, có thể lưu **response đầy đủ đã được lọc**, hoặc chỉ lưu **resourceId + outcome metadata** rồi dựng response từ dữ liệu bất biến. Nếu dựng lại từ trạng thái hiện hành, response có thể khác **kết quả tại thời điểm thao tác ban đầu**; phải viết rõ hợp đồng.

## 11. Mô hình trạng thái xử lý

Một state machine thường gặp:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PROCESSING: claim key
    PROCESSING --> COMPLETED: effect + result committed
    PROCESSING --> RETRYABLE: no-effect failure / safe recovery
    PROCESSING --> FAILED_FINAL: final business rejection
    RETRYABLE --> PROCESSING: safe takeover
    COMPLETED --> [*]: retain for replay
    FAILED_FINAL --> [*]: retain outcome by policy
~~~

Ý nghĩa:

| Trạng thái | Đặc điểm | Retry cùng key |
|---|---|---|
| **NEW** | Chưa có bản ghi xử lý | Có thể claim |
| **PROCESSING** | Một attempt/worker đang xử lý | Không chạy song song effect lần hai |
| **COMPLETED** | Effect và outcome đã được công nhận | Phát lại response |
| **RETRYABLE** | Biết chắc chưa có effect hoặc có protocol phục hồi | Có thể xử lý lại có kiểm soát |
| **FAILED_FINAL** | Rejection nghiệp vụ xác định theo policy | Phát lại failure hoặc contract rõ ràng |
| **UNKNOWN** | Client/worker không biết effect đã commit chưa | Reconcile/verify, không tạo operation mới |

**UNKNOWN** có thể là **outcome của attempt** thay vì một trạng thái persisted, và không phải mọi hệ nên tự tạo một row UNKNOWN mỗi khi timeout. Điều quan trọng là **không biến “không nhận response” thành “chắc chắn thất bại”**.

## 12. Timeline: hai requests cùng key đến đồng thời

Client gửi cùng key hai lần vì retry nhanh hoặc network:

~~~text
Request A: K=checkout-9001
Request B: K=checkout-9001

               +--------------------+
A -----------> | Idempotency store  |
B -----------> | unique key K       |
               +--------------------+
                     |
       Chỉ một request giành quyền NEW -> PROCESSING
                     |
            Business operation
                     |
           Persist outcome
                     |
       Request còn lại replay/wait/poll
~~~

**Check-then-insert không nguyên tử**:

~~~text
A: GET K -> NOT_FOUND
B: GET K -> NOT_FOUND
A: CREATE order-101
B: CREATE order-102
A: INSERT marker K
B: INSERT marker K -> duplicate
~~~

Unique marker ở cuối đã quá muộn: **cả hai orders đã được tạo**.

Cần đặt **điểm giành quyền hoặc transaction** trước side effect, và bảo đảm marker/effect nhất quán khi có crash.

## 13. Ranh giới atomicity là vấn đề quyết định

Một giải pháp tưởng đúng:

~~~text
1. INSERT idempotency marker K.
2. CREATE order.
3. UPDATE marker -> COMPLETED.
~~~

Nếu ba bước tách rời, có các cửa sổ lỗi:

| Crash ở đâu? | Điều còn lại | Nguy cơ |
|---|---|---|
| Trước bước 1 | Không có marker/effect | Có thể retry an toàn |
| Sau bước 1, trước bước 2 | Marker PROCESSING, chưa có order | Key bị kẹt hoặc takeover sai |
| Sau bước 2, trước bước 3 | Order đã có, marker chưa COMPLETED | Retry tạo order thứ hai |
| Sau bước 3, trước HTTP response | Order và response đã lưu | Retry nên phát lại, không tạo mới |

Thiết kế mạnh nhất khi cùng phạm vi dữ liệu hỗ trợ:

~~~text
Atomic transaction:
  enforce uniqueness of idempotency key
  apply business effect
  save final result
COMMIT
~~~

Nếu **định danh business resource** được quyết định trước commit, cả resource và response có thể được ghi cùng transaction.

Nhưng một số NoSQL không hỗ trợ transaction tùy ý trên nhiều partitions. Khi đó phải thiết kế **same-partition conditional mutation, deterministic business key, job state machine, ledger/outbox hoặc reconciliation**, chứ không giả vờ ba writes tách rời là nguyên tử.

## 14. Mẫu A: transaction gộp key, effect và response

Mô hình:

~~~text
BEGIN ATOMIC UNIT

  Assert no existing key (tenant,operation,K)
  Create order with stable ID O
  Save idempotency(K, fingerprint, COMPLETED, O, response)

COMMIT
~~~

Sau khi commit:

~~~text
Retry K:
  Read idempotency record
  Verify fingerprint
  Return saved HTTP status/body
~~~

**Ưu điểm:** không có trạng thái “order đã commit nhưng marker chưa có” nếu tất cả thay đổi nằm trong transaction thực sự.

**Giới hạn:** không thể đặt HTTP response vào cùng transaction với việc **client nhận được response**. Nhưng không cần làm vậy: server có thể commit **saved outcome**, còn việc gửi response là thao tác có thể lặp lại.

Một transaction DB cũng không tự bao gồm email, message broker hoặc external payment provider. Những hiệu ứng đó cần lớp riêng.

## 15. Mẫu B: một record vừa là business resource vừa là dedup record

Nếu API tạo một tài nguyên với **khóa tự nhiên đủ ổn định**, có thể đơn giản hơn:

~~~text
order identity = (tenantId, clientCheckoutId)

CreateOnly:
  INSERT order IF ABSENT
  with original request fingerprint and orderId
~~~

Retry cùng key:

~~~text
INSERT IF ABSENT -> ALREADY_EXISTS
GET original record
Compare fingerprint
Return original outcome
~~~

Mô hình này giúp **không cần transaction hai records** nếu một record đã chứa đầy đủ identity, trạng thái và outcome.

Tuy nhiên:

- Nếu còn side effect ở payment/inventory/email, vẫn cần workflow idempotent riêng.
- Nếu order có trạng thái biến động, response cũ và current state cần được phân biệt.
- Nếu key được phép tái sử dụng sau TTL/xóa, contract phải xác định khi nào một checkout mới được phép dùng lại.
- Nếu client không được phép chọn order ID, server có thể ánh xạ **clientCheckoutId → orderId** trong một record có uniqueness.

**Đặt logical intent identity vào mô hình dữ liệu** đôi khi vững và rẻ hơn duy trì bảng dedup tách biệt.

## 16. Mẫu C: claim PROCESSING rồi thực hiện workflow

Khi effect kéo dài hoặc gọi hệ ngoài:

~~~text
NEW
  |
  | atomic claim K
  v
PROCESSING(owner, lease, generation)
  |
  +-- bước 1: reserve inventory
  +-- bước 2: authorize payment
  +-- bước 3: write order final state
  |
  v
COMPLETED(saved result)
~~~

Điều kiện bắt buộc:

- **Claim** phải atomic/unique.
- Mỗi bước có **operation ID hoặc natural idempotency** riêng.
- Marker PROCESSING có policy cho **worker crash và timeout**.
- Takeover phải có **owner generation/fencing/CAS** để worker cũ không hoàn tất sai.
- Resume phải dựa vào **đã ghi nhận bước nào**, không chạy lại mù tất cả.
- Các bước có side effect ngoài DB cần kiểm tra outcome qua provider hoặc sổ ledger.

**Trạng thái PROCESSING không tự làm effect idempotent**. Nếu worker chết sau khi gọi provider thành công nhưng trước khi đánh dấu bước done, worker mới phải biết cách **verify/retry bằng cùng provider idempotency ID**.

## 17. Thiết kế result record: những trường cần lưu

Ví dụ:

~~~yaml
# Dữ liệu mô hình hóa, không phải cấu hình trực tiếp của engine
identity:
  tenantId: shop-a
  operationType: CreateOrder:v1
  idempotencyKey: checkout-9001
requestFingerprint: "sha256:..."
status: COMPLETED
businessResult:
  resourceType: order
  resourceId: order-101
response:
  httpStatus: 201
  body:
    orderId: order-101
    status: PENDING_PAYMENT
owner:
  leaseId: null
  generation: 7
timing:
  createdAt: "2026-11-14T09:00:00Z"
  completedAt: "2026-11-14T09:00:01Z"
  expiresAt: "2026-11-21T09:00:00Z"
schemaVersion: 1
~~~

Không phải endpoint nào cũng cần **owner/generation** nếu toàn bộ effect commit trong một transaction tức thời. Đừng thêm state machine phức tạp cho một operation mà **conditional single-item Put** đã giải quyết trọn vẹn.

### Response có những dữ liệu gì?

Nên giữ:

- HTTP status hoặc trạng thái API tương đương.
- Resource ID đã tạo.
- Kết quả nghiệp vụ bất biến tại thời điểm commit.
- Field cần thiết để replay response theo hợp đồng.
- Error code xác định nếu policy lưu failure.

Không nên lưu:

- Bearer token, password, secret, thông tin thẻ thanh toán nguyên bản.
- Bản sao vô hạn của payload lớn không cần thiết.
- Response chứa dữ liệu nhạy cảm mà caller mới không còn quyền truy cập.
- Header transport như Date/trace ID rồi giả định chúng phải giống mãi.

Server có thể dựng **body response ổn định** và thêm **headers hiện thời** như trace ID mới.

## 18. Replay phải trả gì?

Một contract HTTP minh họa:

| Request tới | Server state | Hành vi |
|---|---|---|
| Key mới, payload P | NEW | Thực hiện, lưu result, trả 201 |
| Cùng key, cùng P | COMPLETED | Trả lại 201 + cùng orderId/result |
| Cùng key, payload Q khác | Bất kỳ đã claim | 409 hoặc 422 theo contract |
| Cùng key, cùng P | PROCESSING | 202 + status URL, hoặc 409/425 với Retry-After tùy API |
| Cùng key, cùng P | FAILED_FINAL | Replay rejection theo policy |
| Cùng key | Outcome chưa rõ nội bộ | 202/503 hoặc endpoint tra trạng thái; không tạo effect mới |
| Key hết retention | Không còn marker | Hành vi phụ thuộc retention/unique business key |

Không tồn tại **một HTTP status duy nhất bắt buộc cho mọi idempotency API**. Điều quan trọng là tính nhất quán của contract, tài liệu và client SDK. Ví dụ **409 Conflict** cho key dùng lại khác payload là hợp lý; một API khác có thể chọn **422 Unprocessable Content** cho tình huống đó.

**202 Accepted** phải đi kèm cách biết kết quả về sau: operation resource/status URL, polling hoặc notification; nếu không, client dễ retry vô hạn.

## 19. Có cần replay cả lỗi không?

Một số lỗi nên được xem là **outcome xác định của ý định**:

~~~text
CreateOrder(K, cart-77)
  -> REJECTED: cart already checked out
~~~

Nếu policy công nhận và lưu rejection đó, retry cùng K có thể nhận cùng kết quả.

Nhưng không nên cache vô điều kiện:

~~~text
500 DB_CONNECTION_LOST
~~~

và biến nó thành “kết quả nghiệp vụ vĩnh viễn” nếu server chưa biết effect đã xảy ra hay chưa. Cần phân biệt:

- **Validation failure trước khi claim/ghi:** có thể cho client sửa payload và gửi key mới.
- **Business failure xác định sau điều kiện nguyên tử:** có thể lưu như final outcome.
- **Transient error chắc chắn không effect:** cho retry an toàn theo chính sách.
- **Timeout/unknown commit:** phải xác minh chứ không tự ghi FAILED_FINAL.
- **Error sau effect đã commit:** có thể lưu/đọc lại original committed result.

Một API có thể chọn replay cả một số lỗi server theo thiết kế, nhưng phải công bố chính sách; không biến **một lỗi bất định** thành bản ghi “đã xử lý” làm chôn mất effect.

## 20. Có cần trả cùng response body mãi mãi?

Giả sử checkout ban đầu tạo order trạng thái **PENDING_PAYMENT**. Sau một giờ, order thành **PAID**. Retry cùng key:

~~~text
Option A: replay response gốc
  {"orderId":"order-101","status":"PENDING_PAYMENT"}

Option B: trả current state
  {"orderId":"order-101","status":"PAID"}
~~~

Cả hai có thể là contract hợp lệ, nhưng ý nghĩa khác nhau:

- **Replay nguyên kết quả gốc** cho phép client nhận cùng response của operation CreateOrder.
- **Return current state** biểu diễn resource hiện tại, có thể thay đổi sau operation.

Nên ưu tiên tách:

~~~text
POST /orders (idempotent CreateOrder) -> original create outcome
GET /orders/order-101 -> current order state
~~~

Nếu replay được dựng lại từ record hiện hành, phải bảo đảm **orderId/identity không đổi** và không tái chạy business effect.

## 21. Retention và TTL: key được nhớ trong bao lâu?

Một idempotency record không nhất thiết lưu vĩnh viễn, nhưng xóa sớm có thể gây trùng.

Giả sử:

~~~text
t0: K tạo order-101
t1: record K có TTL 1 giờ
t2: mobile offline 2 ngày
t3: mobile reconnect và retry K
~~~

Nếu marker đã hết hạn, server có thể coi K là mới và tạo **order-102**.

Phải thiết kế retention theo:

\[
T_{\mathrm{retain}}
\geq
\max(T_{\mathrm{clientRetry}}, T_{\mathrm{queueReplay}},
T_{\mathrm{recoveryReplay}})
\]

và cộng thêm margin theo yêu cầu vận hành. Đây là **quan hệ hoạch định**, không phải công thức bảo đảm tự động: cần xét timeout thực, network outage, backup replay, worker backlog, offline clients và retention của nguồn event.

Nếu order phải **không bao giờ trùng theo checkoutId**, một unique business key có thể cần tồn tại lâu hơn idempotency cache. **TTL chỉ định cửa sổ replay**, còn **business uniqueness** có thể là bất biến dài hạn.

## 22. Không tái sử dụng key sau TTL một cách mơ hồ

Sau khi marker hết hạn, API phải có policy:

- **Policy A:** cùng key có thể được xem là ý định mới sau thời gian công bố; client phải hiểu rủi ro.
- **Policy B:** key không bao giờ được tái sử dụng trong một business scope, nhờ unique natural key vẫn còn.
- **Policy C:** marker được archive/tombstone để từ chối replay cũ, còn response lớn được dọn.
- **Policy D:** dùng một operationId được ghi trong chính business record, có thể tra lại mà không phụ thuộc cache.

Nếu replay sau hai tuần vẫn có thể xảy ra nhưng chỉ lưu marker bảy ngày, **exactly-once effect trong hai tuần** chưa được bảo vệ bởi cache đó.

TTL ở các NoSQL cũng có thể là **xóa bất đồng bộ**, không phải câu lệnh đếm ngược bảo đảm record biến mất chính xác tại expiresAt. Đừng dùng thời điểm xóa vật lý làm nguồn duy nhất xác định chính sách hết hạn.

## 23. Idempotency key không thay thế business uniqueness

Một khách có thể bấm nút hai lần và **app tạo hai keys khác nhau**:

~~~text
Checkout intent thực tế: cart-77

Request 1: key=uuid-A -> order-101
Request 2: key=uuid-B -> order-102
~~~

Idempotency theo key không coi chúng là trùng. Nếu business rule là **một cart chỉ checkout thành công một lần**, cần thêm unique constraint:

~~~text
Unique(tenantId, cartCheckoutId)
~~~

Hai lớp:

1. **Idempotency key**: chống lặp khi truyền lại một ý định đã đặt ID.
2. **Business unique key/constraint**: chặn hai ý định được đánh ID khác nhau nhưng tranh cùng một tài nguyên chỉ được tạo một lần.

Ví dụ đặt ghế:

~~~text
Unique active claim per (showId, seatId)
~~~

Điều kiện này phải được thực thi bằng cơ chế dữ liệu/state machine thích hợp, không chỉ nằm trong kiểm tra phía UI.

## 24. Deterministic ID có thể giúp chống tạo trùng

Thay vì mỗi attempt tự sinh order ID:

~~~text
orderId = randomUUID() per attempt
~~~

có thể dùng logical request ID:

~~~text
orderId = deriveStableId(tenantId, checkoutId)
~~~

hoặc gán một orderId duy nhất tại lần claim đầu tiên và lưu:

~~~text
checkoutId -> orderId
~~~

Nếu database có **create-only/conditional Put** theo orderId, retry sẽ không tạo thêm record.

Nhưng:

- Stable ID không tự ngăn hai checkoutIds khác nhau cho cùng cart nếu business yêu cầu uniqueness theo cart.
- Không đưa dữ liệu nhạy cảm vào ID dễ đoán.
- Hash có collision policy và scope.
- Tài nguyên bị xóa/recreate vẫn có thể tạo lại effect nếu không giữ tombstone/unique constraint.
- Multi-region conditional uniqueness có giới hạn khác nhau theo topology.

**ID ổn định + create-only + fingerprint** thường là một nền tảng tốt cho API tạo resource.

## 25. MongoDB: unique index cho idempotency records

Một collection:

~~~javascript
db.idempotencyRecords.createIndex(
  {
    tenantId: 1,
    operationType: 1,
    idempotencyKey: 1
  },
  { unique: true }
);
~~~

Một unique index khác bảo vệ ý định checkout:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, checkoutId: 1 },
  { unique: true }
);
~~~

Trong MongoDB sharded cluster, **unique-index rules có điều kiện liên quan shard key**. Không tự kết luận index trên là một unique constraint toàn cụm trong mọi cấu hình; phải thiết kế shard key/index theo phạm vi database hỗ trợ và kiểm tra trước khi vận hành.

### Tại sao check-then-insert vẫn sai?

~~~javascript
// Ví dụ sai nếu không có cơ chế atomic/unique phù hợp.
const old = db.idempotencyRecords.findOne({
  tenantId: "shop-a",
  idempotencyKey: "checkout-9001"
});

if (!old) {
  db.orders.insertOne({ _id: newOrderId() });
}
~~~

Hai threads có thể cùng findOne trả null trước khi một thread insert. Cần để **unique index/transaction/conditional mutation** quyết định, không dựa vào kiểm tra ứng dụng đơn thuần.

## 26. MongoDB: transaction gắn result với order

Ví dụ khái niệm với MongoDB Node.js driver:

~~~javascript
// Minh họa transaction core; chưa có controller, validation,
// error mapping, retry policy hay authentication đầy đủ.
const session = client.startSession();
const tenantId = "shop-a";
const key = "checkout-9001";
const fingerprint = "sha256:canonical-request";
const orderId = "order-101";

try {
  await session.withTransaction(async () => {
    const order = {
      _id: orderId,
      tenantId,
      checkoutId: key,
      status: "PENDING_PAYMENT"
    };

    await db.collection("orders").insertOne(order, { session });

    await db.collection("idempotencyRecords").insertOne(
      {
        tenantId,
        operationType: "CreateOrder:v1",
        idempotencyKey: key,
        requestFingerprint: fingerprint,
        status: "COMPLETED",
        businessResourceId: orderId,
        responseHttpStatus: 201,
        responseBody: {
          orderId,
          status: "PENDING_PAYMENT"
        }
      },
      { session }
    );
  });
} finally {
  await session.endSession();
}
~~~

**Điều kiện của ví dụ:**

- Database deployment/driver phải hỗ trợ transactions đúng phạm vi và cấu hình.
- Cần unique indexes tương ứng; hai transactions tranh cùng key không được đều commit hai orders.
- Nếu insert marker bị duplicate, transaction phải rollback cả order, không được swallow lỗi rồi commit order.
- Lần gọi sau phải tìm existing idempotency record, kiểm fingerprint và replay response.
- Ghi nhận hiệu ứng ngoài DB như email/payment **không nên gọi trực tiếp bên trong transaction callback** vì callback có thể được retry bởi driver; dùng outbox sau commit.
- Driver có thể retry transaction/commit theo policy. Khi commit outcome UNKNOWN, cần tra record theo key ở nguồn thích hợp trước khi kết luận.
- Đây là ví dụ cốt lõi, không phải toàn bộ handler production.

**Điểm quyết định:** order và idempotency record phải có **cùng số phận commit**, không thể có order được commit nhưng marker chưa commit trong phạm vi transaction trên.

## 27. MongoDB: xử lý race duplicate-key và replay

Hai client đến cùng lúc:

~~~text
A transaction:
  insert order-101
  insert idempotency K
  commit -> SUCCESS

B transaction:
  insert order-102
  insert idempotency K
  commit -> DUPLICATE / CONFLICT
  rollback
~~~

B phải:

1. Xác nhận transaction của B không còn side effect.
2. Đọc record K đã commit bằng đường đọc phù hợp.
3. So fingerprint với payload B.
4. Nếu giống và status=COMPLETED, replay original result.
5. Nếu khác, báo conflict.
6. Nếu chưa nhìn thấy record do giao dịch A chưa hoàn tất/visibility mode, chờ/backoff có giới hạn hoặc tra status theo contract.

**Đừng bắt lỗi duplicate rồi tự trả “success” mà không xác minh record nào đang có**. Một duplicate business key có thể do một checkout khác, còn fingerprint mismatch có ý nghĩa khác retry hợp lệ.

## 28. DynamoDB: PutItem có điều kiện cho identity ổn định

Với DynamoDB, một **PutItem** có **ConditionExpression**:

~~~text
PK = ORDER#shop-a#checkout-9001

ConditionExpression:
  attribute_not_exists(PK)
~~~

có thể giúp **chỉ một request tạo item cho logical key đó** trong phạm vi bảo đảm của item/API.

Item ví dụ:

~~~json
{
  "PK": "ORDER#shop-a#checkout-9001",
  "orderId": "order-101",
  "requestFingerprint": "sha256:...",
  "status": "PENDING_PAYMENT",
  "createOutcome": {
    "httpStatus": 201,
    "orderId": "order-101"
  }
}
~~~

Retry:

~~~text
PutItem same PK -> ConditionalCheckFailed
GetItem existing item with appropriate read mode
Compare requestFingerprint
Return original createOutcome
~~~

Khi business resource chính là item này, **không cần hai writes riêng** để tạo order và marker.

Read mode có ý nghĩa: strongly consistent read được hỗ trợ trên base table trong phạm vi dịch vụ; **GSI eventual** không nên là nơi duy nhất quyết định đã có key hay chưa.

## 29. DynamoDB: marker và order ở hai items

Giả sử:

~~~text
IDEMP#shop-a#CreateOrder#checkout-9001
ORDER#shop-a#order-101
~~~

Nếu cần commit cả hai:

~~~text
TransactWriteItems:
  Put idempotency item (status=COMPLETED, saved response)
    ConditionExpression: attribute_not_exists(PK)

  Put order item (orderId=order-101)
    ConditionExpression: attribute_not_exists(PK)
~~~

**Hai actions ở hai items** nằm trong cùng transaction theo phạm vi dịch vụ hỗ trợ. Không thiết kế một transaction chứa **Put và Update vào cùng một item** nếu API TransactWriteItems không cho nhiều actions trên cùng một item.

Những lưu ý:

- Tài khoản, vùng, số items, kích thước và loại actions bị ràng buộc theo giới hạn dịch vụ.
- **ClientRequestToken** của transactional API hỗ trợ idempotency ở một phạm vi/cửa sổ được tài liệu định nghĩa, không thay logical idempotency record lưu dài hạn.
- Client timeout sau transaction có thể có outcome UNKNOWN; đọc lại marker theo policy trước khi lặp với ID mới.
- Nếu một conditional Put thất bại, transaction phải không tạo một order mới.
- Nếu response có chứa những field sẽ thay đổi, lưu original response hoặc resource ID để giữ contract.
- Trong global multi-region replication, không được suy một conditional write tại một region cung cấp uniqueness tuyến tính toàn cầu trong mọi chế độ; phải xem đúng consistency contract/region ownership.

## 30. Cassandra: LWT IF NOT EXISTS

Trong Cassandra, các ordinary writes có thể hành xử theo upsert; **INSERT cùng primary key không mặc nhiên là create-only**.

Một bảng đồng thời lưu intent và order result:

~~~sql
CREATE TABLE orders_by_checkout (
    tenant_id text,
    checkout_id text,
    order_id text,
    request_fingerprint text,
    status text,
    create_response text,
    PRIMARY KEY ((tenant_id, checkout_id))
);
~~~

Một lệnh conditional create:

~~~sql
INSERT INTO orders_by_checkout (
    tenant_id,
    checkout_id,
    order_id,
    request_fingerprint,
    status,
    create_response
) VALUES (
    'shop-a',
    'checkout-9001',
    'order-101',
    'sha256:...',
    'PENDING_PAYMENT',
    '{"orderId":"order-101"}'
)
IF NOT EXISTS;
~~~

Cần kiểm tra kết quả **[applied]**:

- **true:** row được tạo bởi intent này.
- **false:** đã có row ở cùng key; đọc bản hiện có, so fingerprint và trả original result/đúng contract.

### Giới hạn

- **LWT** có chi phí điều phối và phạm vi partition/operation theo engine; throughput và p99 cần đo.
- Nếu idempotency record nằm ở partition khác order record, hai ordinary CQL writes không tự là một transaction atomic.
- Cassandra **logged batch không tương đương SQL transaction serializable** cho mọi row/partition.
- Dùng một row làm **authoritative operation record** rồi xây read models từ log/outbox/processing có thể phù hợp hơn khi tránh cross-partition atomicity.
- Counter updates trong Cassandra không idempotent chỉ vì đã dùng QUORUM; phải dedup đúng intent.

## 31. Cassandra: đừng dùng QUORUM thay cho uniqueness

Timeline:

~~~text
A SELECT key K at QUORUM -> not found
B SELECT key K at QUORUM -> not found
A INSERT K ordinary -> ACK
B INSERT K ordinary -> ACK
~~~

Quorum read/write không biến chuỗi **SELECT rồi INSERT** thành một create-if-absent operation. Với Cassandra, ordinary INSERT còn có thể cập nhật/ghi đè fields theo conflict/timestamp semantics.

Nếu contract là **chỉ một người có quyền claim key**, phải dùng LWT/conditional operation trong phạm vi hỗ trợ hoặc một nguồn authority khác. Nếu một side effect nằm ngoài row conditional, tiếp tục cần outbox/reconciliation.

## 32. Redis: SET NX cho marker và những giới hạn

Redis cho phép tạo marker nếu chưa tồn tại:

~~~redis
SET idem:shop-a:CreateOrder:checkout-9001 PROCESSING NX EX 86400
~~~

Đây có thể là bước **claim key** trong một thiết kế chấp nhận các đặc điểm Redis.

Nhưng:

- **SET NX không tự commit cùng việc tạo order trong MongoDB/DynamoDB**.
- Nếu marker được tạo rồi worker crash trước khi tạo order, retry có thể mắc kẹt.
- Nếu order được tạo rồi worker crash trước khi marker COMPLETED, một worker khác có thể tạo trùng.
- TTL hết hạn trong khi processing kéo dài có thể cho worker khác claim.
- Replication/failover/persistence của Redis có bảo đảm riêng; marker có thể không bền như business record.
- Marker không lưu saved result thì retry chưa biết phải trả outcome gì.

Redis có thể thích hợp cho **cache replay, rate limiting hoặc optimization**; với nghiệp vụ không chấp nhận trùng, nên có **uniqueness/authoritative state** tại nơi effect được commit.

## 33. Redis Lua và atomicity không đồng nghĩa cross-system transaction

Nếu **marker và effect đều nằm trong cùng phạm vi Redis** (và cùng slot khi Redis Cluster yêu cầu), có thể dùng Lua/script để kiểm marker và cập nhật trong một execution không bị lệnh khác chen vào.

Mã minh họa cho counter:

~~~lua
-- KEYS[1]: marker cho eventId
-- KEYS[2]: counter của cùng slot/instance
-- ARGV[1]: giá trị response cần lưu

local existing = redis.call("GET", KEYS[1])
if existing then
  return existing
end

local value = redis.call("INCRBY", KEYS[2], 1)
redis.call("SET", KEYS[1], ARGV[1])
return ARGV[1]
~~~

**Đây là ví dụ giới hạn, không phải recipe exactly-once production**:

- Script chạy nối tiếp với những commands khác trên instance phù hợp, nhưng **lỗi runtime sau khi một lệnh đã thành công không có rollback kiểu SQL**; ví dụ INCRBY thành công rồi SET lỗi có thể tạo effect thiếu marker.
- Nếu marker/counter có TTL/durability không phù hợp, replay vẫn có thể tăng lần nữa.
- Replication/failover có thể ảnh hưởng cả marker và counter.
- Trong Redis Cluster, các keys mà script truy cập phải tuân thủ quy tắc slots.
- Một script Redis không thể bảo đảm effect trong payment API hoặc MongoDB cùng commit.

Khi cần guarantee cứng, cần thiết kế dữ liệu, atomicity và recovery rộng hơn một script.

## 34. Idempotency key và business unique index nên đi cùng nhau

Ví dụ API tạo reservation:

~~~text
Idempotency scope:
  (tenantId, "ReserveSeat", requestKey)

Business uniqueness:
  (showId, seatId, activeClaim)
~~~

Hai khách khác nhau:

~~~text
Alice key=A1 -> claim seat A12
Bob   key=B1 -> claim seat A12
~~~

Hai keys khác nhau, nhưng business invariant **chỉ một active claim**. Idempotency không ngăn Bob nếu hệ không có conditional claim hoặc unique rule phù hợp.

Ngược lại, Alice retry A1 sau timeout, unique claim có thể chặn tạo trùng nhưng cần **idempotency result record** để trả:

~~~text
SUCCESS: reservationId=res-101
~~~

thay vì báo Alice rằng ghế đã có người giữ như thể một request khác.

**Idempotency bảo vệ cùng ý định; business uniqueness bảo vệ cùng tài nguyên.**

## 35. Một workflow giữ ghế hoàn chỉnh

State:

~~~text
Seat:
  AVAILABLE -> HELD -> SOLD
               |
               -> AVAILABLE (release/expiry có điều kiện)
~~~

Yêu cầu:

~~~json
{
  "showId": "show-07",
  "seatId": "A12",
  "reservationRequestId": "reserve-9001"
}
~~~

Luồng:

1. Xác thực user/tenant và so fingerprint.
2. Kiểm idempotency record cho **reserve-9001**.
3. Chạy **conditional claim**: seat còn AVAILABLE, chưa có chủ.
4. Gán reservationId ổn định, ghi owner/expiry/version.
5. Lưu outcome của reserve-9001 **nguyên tử với claim hoặc qua protocol recoverable**.
6. Nếu retry, phát lại chính reservationId.
7. Nếu một request khác giành ghế trước, trả **CONFLICT** xác định.
8. Khi hold hết hạn, chỉ release nếu **reservationId/version vẫn khớp**; không dùng job cũ release ghế của chủ mới.

Idempotency ở bước tạo hold và **fencing/version** ở bước release/renew giải quyết các loại race khác nhau.

## 36. Thao tác tăng/giảm không tự idempotent

~~~text
loyaltyPoints = 100

Apply +10 for event E1.
Network timeout.
Retry +10 for E1.

Result sai nếu không dedup:
  120 thay vì 110.
~~~

Không đủ nếu chỉ dùng **atomic increment**:

~~~text
INCRBY points 10
~~~

Atomic increment chống lost update giữa hai writers, nhưng **không chặn cùng một event chạy hai lần**.

Một mô hình phù hợp:

~~~text
Atomic unit:
  Put ledgerEvent E1 IF ABSENT
  Apply +10 to points
  Save outcome for E1
~~~

Nếu source ledger là authority, có thể materialize points vào read model bằng worker idempotent và reconcile; không cần mỗi event luôn sửa counter authoritative đồng thời nếu contract chấp nhận eventual aggregate.

## 37. Outbox: khi DB commit nhưng publish event có thể thất bại

Một lỗi kinh điển:

~~~text
1. CreateOrder commit trong DB.
2. Publish OrderCreated tới broker.
~~~

Nếu process crash sau 1 trước 2, order tồn tại nhưng event bị mất. Nếu cố publish trước DB commit, event có thể được phát cho order chưa thực sự tồn tại.

**Transactional outbox** lưu event cần phát trong cùng transaction với order:

~~~text
DB transaction:
  Create order
  Save idempotency outcome
  Insert outbox event OrderCreated(eventId=E1)
COMMIT

Outbox relay:
  Read unsent outbox rows
  Publish E1 to broker
  Mark E1 delivered / checkpoint
~~~

Relay có thể publish E1 nhiều lần nếu response/ack mất. Vì vậy consumer cần **inbox/dedup**.

**Outbox không bảo đảm broker nhận đúng một message vật lý**. Nó giúp **không mất ý định phát event sau commit**, còn downstream phải chịu được duplicate delivery.

## 38. Inbox: consumer nhận event nhiều lần

Một worker xử lý:

~~~text
OrderCreated(eventId=E1, orderId=order-101)
~~~

Broker giao E1, worker cập nhật projection rồi crash trước khi ACK; broker giao lại E1.

Một **inbox record** lưu:

~~~text
consumerName + eventId -> PROCESSING/COMPLETED
~~~

Luồng trong một atomic unit nếu DB hỗ trợ:

~~~text
if inbox[consumer,E1] absent:
    apply projection/update
    insert inbox[consumer,E1] as COMPLETED
commit
~~~

Retry đọc inbox đã COMPLETED thì bỏ qua effect.

Nếu inbox nằm ở database A nhưng projection nằm ở B, hai writes tách rời có crash window; cần recoverable workflow hoặc đổi data model để commit cùng nơi. **Lưu inbox ở Redis chỉ để cache mà effect ở NoSQL khác không tự cung cấp exactly-once effect**.

## 39. Consumer progress và message offset không thay event identity

Trong hệ dùng Kafka hoặc queue:

~~~text
partition p3, offset 120: event E1
~~~

**Offset** đánh dấu vị trí message trong một log, nhưng:

- Cùng logical event có thể được publish lại với **offset mới**.
- Một event đi qua nhiều topics hoặc consumer groups.
- Event có thể được replay từ nguồn và đổi vị trí.
- Consumer commit offset và database write có thể không cùng transaction.

Do đó dedup theo **logical eventId và consumer scope** thường rõ hơn khi bảo vệ nghiệp vụ; offset có thể là **checkpoint xử lý** nếu giao thức đã định nghĩa.

Nếu dùng offset để xác định batch, phải đảm bảo **partition owner, source generation, contiguous ranges và effect/checkpoint** được phối hợp. Một worker bị rebalance có thể xử lý lại cùng range; fencing và idempotency cần bổ trợ.

## 40. Webhook và callbacks từ hệ ngoài

Payment provider có thể gửi:

~~~text
payment.succeeded(eventId=evt-77, paymentIntentId=pi-1001)
~~~

nhiều lần vì webhook response timeout.

Receiver nên:

1. **Xác minh chữ ký/nguồn gửi**, không coi eventId là secret.
2. Kiểm tra eventId chưa xử lý trong scope provider.
3. Đặt một business transition có điều kiện, ví dụ **PAYMENT_PENDING → PAID**.
4. Lưu event marker/outcome cùng transition hoặc qua recoverable workflow.
5. Trả HTTP success cho event đã xử lý hợp lệ để provider dừng retry.
6. Nếu event đến sai thứ tự, dùng version/provider lookup và state machine thay vì luôn overwrite status.

**Webhook event ID và payment intent ID giải quyết hai scope khác nhau.** Một provider có thể phát nhiều event IDs mô tả cùng một payment intent; business state machine vẫn phải chặn effect bị áp dụng hai lần.

## 41. Gọi payment provider: phải dùng cùng provider idempotency ID

Giả sử API trong ứng dụng:

~~~text
POST /checkout
Idempotency-Key: checkout-9001
~~~

và server gọi provider:

~~~text
CapturePayment(
  paymentIntentId=pi-1001,
  idempotencyKey=checkout-9001:capture
)
~~~

Khi server timeout, retry phải dùng **cùng provider-level operation identity**, hoặc tra trạng thái paymentIntent trước khi quyết định gửi lại theo hợp đồng provider.

Không nên:

~~~text
Retry checkout
  -> tạo paymentIntent mới
  -> tạo provider idempotency key mới
  -> capture lần nữa
~~~

**Database transaction của order không bao trùm payment provider**. Do đó cần:

- Bản ghi paymentIntent/command có identity ổn định.
- Outbox/state machine cho việc gửi command.
- Provider idempotency trong phạm vi/thời hạn hỗ trợ.
- Provider query/reconciliation khi timeout UNKNOWN.
- Compensation/refund nếu business workflow có partial success.

Không tuyên bố idempotency 100% vĩnh viễn nếu provider chỉ nhớ key trong một cửa sổ thời gian nhất định.

## 42. Saga: mỗi bước cần idempotency riêng

Một checkout:

~~~text
CreateOrder -> ReserveInventory -> AuthorizePayment -> ConfirmOrder
~~~

Có thể dùng Saga:

~~~text
SagaId = checkout-9001

Step reserve inventory:
  operationId = checkout-9001:reserve

Step authorize payment:
  operationId = checkout-9001:authorize

Step confirm order:
  operationId = checkout-9001:confirm
~~~

Mỗi bước cần:

- Ghi trạng thái step và version.
- Nhận diện retry của cùng step.
- Xác định outcome success/final failure/UNKNOWN.
- Chỉ chạy bước tiếp theo khi predecessor đạt trạng thái phù hợp.
- Compensation có ID riêng nhưng ổn định cho **một ý định bù**, không thực hiện bù hai lần.

**Một idempotency key cho HTTP đầu vào không tự làm mọi step của Saga idempotent** nếu các workers ở dưới tiếp tục gọi service với IDs mới.

## 43. Kết quả PROCESSING bị kẹt khi worker chết

Một record:

~~~json
{
  "idempotencyKey": "checkout-9001",
  "status": "PROCESSING",
  "owner": "worker-A",
  "generation": 7,
  "leaseExpiresAt": "2026-11-14T09:01:00Z"
}
~~~

Worker A crash trước khi hoàn tất. Nếu mọi retry chỉ trả “đang xử lý” mãi, key bị kẹt.

Một cơ chế recovery:

1. Xác định trạng thái worker/lease bằng nguồn có thẩm quyền.
2. Nếu hết quyền, worker B **claim takeover nguyên tử** và tăng generation.
3. B xem những bước đã commit qua markers/resource IDs.
4. B **không tự tin** bước chưa có response chắc chắn chưa xảy ra.
5. B retry những bước có idempotency bảo vệ hoặc verify outcome.
6. B lưu final result/failed outcome theo contract.
7. Mọi write từ worker A thế hệ cũ phải bị chặn bằng **fencing/CAS tại sink** khi cần.

**Hết lease không làm pending operation ở provider ngoài tự bị hủy.** Recovery cần nhìn cả các effect đã có thể rời khỏi process A.

## 44. Lease và fencing khi hai workers cùng cố hoàn tất

Timeline:

~~~text
t1  A claim K, generation=7.
t2  A pause lâu.
t3  Lease A hết hạn.
t4  B takeover K, generation=8.
t5  B ghi final outcome.
t6  A tỉnh và ghi final outcome cũ.
~~~

Nếu update final result chỉ theo idempotencyKey, A có thể ghi đè B.

Guard phù hợp:

~~~text
UPDATE idempotency[K]
IF status == PROCESSING
   AND ownerGeneration == incomingGeneration
THEN set COMPLETED, result
~~~

Sau B takeover, A generation 7 không match. Nếu bước effect nằm ở một resource khác, resource đó cũng cần **fencing/conditional logic** hoặc một protocol có thể chịu được stale worker.

Đừng nhầm **lease dùng để phân công worker** với **unique constraint dùng để chặn tạo order**: nếu business effect đã được bảo vệ ngay tại nguồn, stale worker có thể thất bại khi create-only dù vẫn cố chạy.

## 45. Kết quả timeout ở từng giai đoạn

| Giai đoạn | Timeout có thể có nghĩa gì? | Cách phản ứng |
|---|---|---|
| Trước khi gửi request | Chưa gửi theo bằng chứng local | Có thể retry cùng key |
| Sau khi gửi đến gateway | Không biết gateway đã forward chưa | Retry cùng key, không đổi intent |
| Đợi DB commit | Transaction có thể commit rồi response mất | Read marker/order theo key |
| Đợi provider capture | Tiền có thể đã thu | Query provider bằng intent ID; cùng provider key |
| Đợi broker publish | Event có thể đã gửi | Outbox/inbox dedup |
| Đợi client nhận HTTP result | Business effect có thể hoàn tất | Replay saved response |

Không nên dùng một biến **success=false** trong catch(timeout) để quyết định undo nếu chưa biết effect. Một thao tác bù sai có thể còn nguy hiểm hơn request retry.

## 46. Quy tắc client retry an toàn

Client nên:

1. Tạo idempotency key **một lần cho một ý định**.
2. Persist key nếu ứng dụng có thể bị kill/restart hoặc offline.
3. Giữ **cùng payload semantics** cho các attempts của key đó.
4. Retry lỗi transport/503/429 theo **deadline, Retry-After, exponential backoff và jitter**.
5. Không tự tạo order/payment ID mới khi chỉ chưa nhận response.
6. Nếu server trả PROCESSING, dùng **GET operation status** hoặc cơ chế chờ được công bố.
7. Nếu server trả fingerprint conflict, dừng retry bằng key cũ và điều tra request thay đổi.
8. Khi kết quả COMPLETED, hiển thị resource ID đã lưu, không phát lại ý định.

Pseudocode:

~~~typescript
async function submitCheckout(intent: CheckoutIntent) {
  const key = await getOrCreatePersistedKey(intent.localIntentId);

  return retryWithBackoff(
    async () => {
      const res = await http.post("/v1/orders", intent.payload, {
        headers: { "Idempotency-Key": key }
      });

      if (res.status === 202) {
        return await pollOperationStatus(res.data.operationId);
      }

      return res.data;
    },
    { deadlineMs: 20000, maxAttempts: 5 }
  );
}
~~~

Đây là pseudocode: implementation phải phân loại lỗi retryable/non-retryable, hủy theo deadline, lưu local intent và bảo vệ dữ liệu người dùng.

## 47. Java: một service contract để biểu diễn kết quả

Một thiết kế Java có thể tách:

~~~java
public record IdempotencyIdentity(
    String tenantId,
    String operationType,
    String idempotencyKey
) {}

public record IdempotentOutcome(
    String resourceId,
    int httpStatus,
    String responseBodyJson
) {}

public interface IdempotentOperationStore {
    // Contract: atomic create/claim theo identity.
    ClaimResult claim(IdempotencyIdentity identity, String fingerprint);

    // Chỉ hoàn tất khi điều kiện owner/generation còn hợp lệ.
    void complete(
        IdempotencyIdentity identity,
        long generation,
        IdempotentOutcome outcome
    );

    StoredOperation find(IdempotencyIdentity identity);
}
~~~

Nếu store không thể gắn **effect và completion** trong một atomic unit, interface này chưa đủ guarantee. Cần service sử dụng transaction/same-partition source, deterministic order ID hoặc Saga recovery protocol.

Điểm hay của tách interface là các adapter MongoDB/DynamoDB/Cassandra có thể thực thi atomicity khác nhau, nhưng **nghĩa của claim/complete** phải được ghi thành contract kỹ thuật, không chỉ trùng tên method.

## 48. Java: xử lý fingerprint conflict và replay

Pseudocode orchestration:

~~~java
public CreateOrderResponse createOrder(
        AuthenticatedTenant tenant,
        String idempotencyKey,
        CreateOrderRequest request) {

    String fingerprint = canonicalFingerprint(
        "CreateOrder:v1",
        tenant.id(),
        request
    );

    IdempotencyIdentity id = new IdempotencyIdentity(
        tenant.id(),
        "CreateOrder:v1",
        idempotencyKey
    );

    StoredOperation existing = store.find(id);

    if (existing != null) {
        if (!existing.fingerprint().equals(fingerprint)) {
            throw new IdempotencyConflictException();
        }
        if (existing.status() == Status.COMPLETED) {
            return decodeOriginalResponse(existing);
        }
        throw new OperationStillProcessingException();
    }

    // Đây KHÔNG phải cách thực hiện concurrency an toàn đầy đủ:
    // hai threads vẫn có thể cùng thấy null.
    // Bước thực thi thật phải dùng transaction/unique create/claim.
    return atomicCreateOrderAndSaveOutcome(id, fingerprint, request);
}
~~~

Đoạn trên **cố ý** cho thấy read-before-write chỉ là **fast path**. Điểm quyết định duy nhất phải nằm trong **atomicCreateOrderAndSaveOutcome**, và duplicate-key/condition-failed phải được chuyển sang **read-and-replay**.

Không được lấy một code snippet có find() rồi insert() tách rời để tuyên bố xử lý được concurrent retries.

## 49. Không gửi email hoặc publish event trong retryable transaction callback

Một số database drivers tự retry transaction callback khi gặp transient conflicts.

Ví dụ cách làm sai:

~~~javascript
await session.withTransaction(async () => {
  await orders.insertOne(order, { session });

  // Sai: email nằm ngoài transaction, callback có thể chạy lại.
  await emailService.sendOrderConfirmation(order);
});
~~~

Nếu callback chạy lại hoặc transaction rollback, email có thể:

- Được gửi hai lần.
- Được gửi dù order không commit.

Cách phù hợp hơn:

~~~text
DB transaction:
  insert order
  save idempotency outcome
  insert outbox("OrderConfirmationRequested", eventId)
COMMIT

Relay:
  gửi event/email theo policy, có dedup/idempotency phù hợp
~~~

Vẫn cần chấp nhận giới hạn của external email provider: nếu provider không có dedup API và response mất, có thể không đạt exactly-once delivery tuyệt đối. Có thể chọn duplicate suppression best-effort và xử lý UX rõ.

## 50. Tranh chấp cùng key cần có phương án chờ hữu hạn

Nếu request A đang PROCESSING, request B cùng key đến:

**Lựa chọn 1 — Chờ ngắn có giới hạn**

~~~text
B chờ A đến deadline nhỏ.
Nếu A commit -> replay.
Nếu vẫn PROCESSING -> 202 + status URL.
~~~

**Lựa chọn 2 — Trả ngay**

~~~text
B -> 202 Accepted
operationId = checkout-9001
pollAfterMs = 1000
~~~

**Lựa chọn 3 — Conflict đang xử lý**

~~~text
B -> 409 Conflict
error = OPERATION_IN_PROGRESS
Retry-After = ...
~~~

Không có phương án duy nhất cho mọi API. Quan trọng là **không thực hiện cùng effect lần hai** và không để 1.000 retries cùng key tạo một đám đông workers.

Nếu API chọn chờ, nên có **waiter limit, timeout budget và cancellation**. Client disconnect không có nghĩa transaction A phải rollback sau khi đã commit.

## 51. Cách phân biệt duplicate hợp lệ và key bị lạm dụng

Một hệ có thể ghi audit:

~~~json
{
  "tenantId": "shop-a",
  "operationType": "CreateOrder:v1",
  "idempotencyKeyHash": "hash-of-key",
  "attemptId": "req-b",
  "requestFingerprint": "sha256:...",
  "matchedExisting": true,
  "action": "REPLAY_STORED_RESPONSE"
}
~~~

Các sự kiện cần phân biệt:

- **REPLAY_SAME_REQUEST:** retry hợp lệ.
- **CONFLICT_DIFFERENT_PAYLOAD:** key được dùng lại sai.
- **IN_PROGRESS_DUPLICATE:** client gửi quá nhanh hoặc service chậm.
- **UNKNOWN_RESULT:** server chưa xác định commit.
- **EXPIRED_KEY_REUSE:** replay ngoài retention.
- **CROSS_TENANT_LOOKUP_DENIED:** client cố truy cập scope không có quyền.

Không log raw Authorization header, secret keys hoặc payment data. Chỉ số conflict tăng đột biến có thể chỉ ra bug của client sinh key, không phải ngay lập tức tấn công.

## 52. Chống đếm trùng ở nhiều datacenter

Nếu cùng key K đến Region A và Region B trong lúc WAN bị chia cắt:

~~~text
Region A:
  K chưa tồn tại -> create order-101 -> ACK

Region B:
  K chưa tồn tại -> create order-102 -> ACK
~~~

Nếu idempotency stores chỉ đồng bộ **eventual** giữa regions, cả hai có thể cùng claim K.

Muốn **uniqueness toàn cầu tức thời**, cần thiết kế:

- **Home region/owner** cho logical key.
- Một conditional/transaction service có **consistency guarantee xuyên vùng** phù hợp.
- Phân vùng namespace/identity để những yêu cầu không tranh cùng key.
- Khi WAN mất, có thể từ chối/chờ request không đạt quyền.
- Hoặc công bố kết quả local **provisional**, rồi resolve conflict — không gọi đó là exactly-once global.

Chỉ vì một API là DynamoDB, MongoDB hoặc Cassandra **không đủ** để kết luận idempotency toàn cầu: phải biết replication topology và mode write/read thực tế.

## 53. Sharding và unique scope trong NoSQL

Một idempotency key phải được lưu và kiểm trong **phạm vi nhất quán có thể thực thi uniqueness**.

Ví dụ:

~~~text
Logical key:
  tenantId + operationType + idempotencyKey

Partition key:
  hash(tenantId, operationType, idempotencyKey)
~~~

Nếu duplicate attempts của cùng logical key bị route đến **hai physical shards khác nhau** vì client dùng shard map cũ, hệ phải có **routing/migration protocol** ngăn cả hai tạo record được công nhận.

Đặc biệt:

- Unique index có thể có điều kiện về shard key.
- Same-partition CAS không tự bảo vệ side effects ở partition khác.
- Transaction xuyên shards có thể tốn thêm latency hoặc bị giới hạn.
- Cached routing key được thay đổi trong lúc retry có thể khiến key tìm sang nơi mới.
- Có thể dùng **deterministic resource IDs** để giảm số lookup.

Đừng biến routing/migration thành một lý do để lặng lẽ thay đổi idempotency identity của client.

## 54. TTL và xóa bản ghi trùng trong workflow nhiều bước

Giả sử:

~~~text
Idempotency record TTL = 24 giờ.
Payment provider lưu dedup key = 72 giờ.
Queue có thể replay sau 7 ngày.
~~~

Trong ngày thứ ba, idempotency marker ở ứng dụng đã mất nhưng message cũ vẫn có thể được giao lại. Một workflow không có business identity dài hạn có thể tạo order mới.

Thiết kế retention phải xét **toàn chuỗi**:

~~~text
Client retry horizon
  + queue redelivery/replay horizon
  + provider reconciliation horizon
  + disaster recovery replay horizon
  + source data lifecycle
~~~

Không phải mọi marker đều cần lưu payload lớn; có thể giữ **tombstone/identity nhỏ** lâu hơn saved response. Nếu archived outcome không còn, server có thể trả **operation expired, please query order by stable business ID** thay vì tạo lại effect một cách mù quáng.

## 55. Bản ghi kết quả có thể là read model, nhưng nguồn cần rõ

Một số hệ lưu:

~~~text
IdempotencyKey -> resourceId, status, response
~~~

trong Redis cache để giảm độ trễ. Nhưng nếu Redis bị mất cache trong khi order authoritative ở MongoDB, retry có thể không thấy marker.

Giải pháp:

~~~text
Fast path:
  Redis -> replay cache nếu hit và hợp lệ

Miss path:
  NoSQL authoritative business key/operation record
  -> read original result
  -> refresh Redis cache
~~~

**Cache miss không chứng minh operation chưa từng được thực hiện**. Chỉ nguồn có uniqueness/ledger đáng tin mới được quyết định tạo mới.

Đối với response cache, cần cân nhắc invalidation, encryption, tenant scope và schema version. Khi application deploy phiên bản mới, saved response cũ có thể cần serializer tương thích hoặc migration.

## 56. Kiểm thử bằng lịch sử thao tác

Một bài test tốt ghi:

~~~text
invoke A: CreateOrder K=P
invoke B: CreateOrder K=P
response A: 201 order-101
response B: 201 order-101
database: đúng một authoritative order cho K
~~~

Đây là một lịch sử chấp nhận được theo hợp đồng replay.

Một lịch sử sai:

~~~text
invoke A: CreateOrder K=P
invoke B: CreateOrder K=P
response A: 201 order-101
response B: 201 order-102
database: tồn tại cả order-101 và order-102
~~~

**Chỉ kiểm response chưa đủ**: server có thể trả cùng orderId hai lần nhưng đã gửi hai emails hoặc capture tiền hai lần. Kiểm tra phải bao phủ các **business effects thực sự**.

## 57. Bảng lỗi và khả năng hồi phục

| Lỗi được tiêm | Rủi ro | Kết quả cần đạt |
|---|---|---|
| Response mất sau commit | Client retry tạo record khác | Replay same resource/result |
| Hai requests cùng key đến đồng thời | Race check-then-insert | Chỉ một commit hợp lệ |
| Same key, different payload | Gắn hai intents vào một key | Conflict, không tạo effect thứ hai |
| Crash sau marker, trước effect | PROCESSING kẹt | Recover hoặc rollback xác định |
| Crash sau effect, trước completion | Retry tạo lại effect | Transaction hoặc verify/reconcile |
| Driver retry transaction callback | Gửi side effect ngoài DB hai lần | Không gọi provider trong callback; outbox |
| Worker lease hết, worker cũ tỉnh lại | Ghi đè result mới | CAS/fencing tại sink |
| Provider response timeout | Có thể charge hai lần | Provider key ổn định, status lookup |
| Broker redelivers event | Projection/counter tăng trùng | Inbox/ledger/conditional effect |
| Idempotency cache evicted | Tạo order mới sau cache miss | Authoritative lookup |
| Marker TTL hết trước queue replay | Event cũ tạo mới | Retention/business uniqueness |
| Hai regions partition | Cùng key được tạo tại hai vùng | Global authority hoặc sửa contract |
| Restore DB/counter từ backup cũ | Mất marker thế hệ mới | Reconcile identity và history |
| Event đến sai thứ tự | State regression | Version/state-machine conditions |

Thử nghiệm nên dùng **dữ liệu cô lập và fault injection được phép**, ghi rõ trạng thái đầu, thao tác, thời điểm crash/timeout, kết quả của API và business invariants.

## 58. Metrics và logs cần thiết

| Metric | Ý nghĩa |
|---|---|
| **idempotency_key_new_total** | Số ý định mới được claim |
| **idempotency_replay_total** | Số retries được phát lại kết quả |
| **idempotency_payload_conflict_total** | Key bị tái sử dụng khác payload |
| **idempotency_processing_age** | Operations mắc kẹt PROCESSING |
| **idempotency_takeover_total** | Recovery sau owner hết lease |
| **unknown_outcome_total** | Commit/provider status chưa xác định |
| **unique_constraint_conflict_total** | Tranh chấp create-only/business identity |
| **duplicate_business_effect_detected** | Phát hiện tạo order/payment/counter lặp |
| **outbox_backlog_age** | Events chưa được publish |
| **inbox_dedup_total** | Messages đã xử lý được giao lại |
| **provider_reconciliation_lag** | Thời gian chưa xác minh external result |
| **retry_attempts_per_intent** | Có retry storm hoặc client bug không |
| **retention_expired_replay_total** | Requests retry ngoài thời hạn nhớ |

Tránh dùng toàn bộ idempotencyKey hay orderId làm metric label có cardinality rất lớn. Trong tracing, có thể lưu **key hash/operation ID** với kiểm soát quyền và retention.

## 59. Checklist thiết kế trước khi triển khai

Một API idempotent cần trả lời:

1. **Logical operation là gì?** Một checkout, một payment capture, một event hay một state transition?
2. **Ai tạo key?** Client hay server, và key được persist qua app restart thế nào?
3. **Scope uniqueness** gồm tenant/account, operation type và API version nào?
4. **Payload fingerprint** có canonicalization và conflict policy gì?
5. **Nơi lưu authoritative marker/outcome** là đâu?
6. **Bước nào atomic** với effect và saved response?
7. **Business uniqueness** có cần một key khác idempotency key không?
8. **Concurrent same-key attempts** được wait, 202 hay 409 như thế nào?
9. **PROCESSING stale** được takeover/reconcile ra sao?
10. **Failed final vs retryable vs unknown outcome** được phân biệt thế nào?
11. **Saved response** giữ status/body nào, lưu bao lâu, có PII/secrets không?
12. **Retention** có bao phủ retry/queue replay/DR hay cần tombstone?
13. **Outbox/inbox** bảo vệ event asynchronous chưa?
14. **External provider** có idempotency key và verify API không?
15. **Multi-region/shard consistency** có bảo vệ uniqueness như contract chưa?
16. **Authentication/authorization** được kiểm tra trước replay?
17. **Metrics/fault tests** có xác minh một hiệu ứng và kết quả ổn định?

Không đủ nếu chỉ ghi tài liệu: “API hỗ trợ Idempotency-Key”. Phải nêu **được đảm bảo ở đâu và trong bao lâu**.

## 60. Sơ đồ quyết định áp dụng idempotency

~~~mermaid
flowchart TD
    A["Một logical intent có thể được gửi lại?"] --> B{"Effect có thể lặp an toàn?"}
    B -->|"Không"| C["Chọn stable idempotency identity"]
    B -->|"Có với state cuối"| D["Kiểm external side effects/response"]
    D --> C
    C --> E["Fingerprint + tenant/operation scope"]
    E --> F{"Effect và marker cùng atomic unit?"}
    F -->|"Có"| G["Transaction / conditional create + saved result"]
    F -->|"Không"| H["Saga/ledger/outbox + recoverable state"]
    G --> I["Concurrent requests: replay hoặc in progress"]
    H --> I
    I --> J["TTL/replay horizon + business uniqueness"]
    J --> K["Timeout UNKNOWN + provider verification"]
    K --> L["Fault tests và reconciliation"]
~~~

Đây là quy trình thực hành:

1. Khai báo nghiệp vụ, resource key và kết quả mong muốn.
2. Chọn identity/fingerprint và policy cho key reuse.
3. Chọn model NoSQL và phạm vi uniqueness thực tế.
4. Gom effect, dedup marker và result trong một atomic unit nếu có thể.
5. Nếu không thể, thiết kế workflow recoverable và stable per-step IDs.
6. Định nghĩa behavior cho concurrent calls, stuck processing và UNKNOWN.
7. Tách response gốc khỏi current resource state nếu cần.
8. Dùng outbox/inbox và provider idempotency cho side effects ngoài DB.
9. Đặt retention đủ bao phủ replay, cùng business key chống trùng lâu dài.
10. Chạy test đồng thời, timeout sau commit, failover, replay và multi-region.
11. Giám sát replay, conflicts, stale jobs và invariant violations.
12. Viết runbook đối soát khi metadata xử lý và business resource không khớp.

## 61. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách xử lý đúng |
|---|---|---|
| “Client timeout thì server chưa chạy” | Commit có thể thành công, response mất | UNKNOWN; retry cùng key/verify |
| “POST không idempotent nên không thể retry” | Có thể định nghĩa application-level intent key | Key + atomic outcome |
| “Cùng payload thì luôn là cùng ý định” | Người dùng có thể mua hai lần | Stable intent ID, không dedup chỉ theo payload |
| “Mỗi request ID là idempotency key” | Gateway sinh request ID mới mỗi attempt | Key theo logical intent |
| “Key ngẫu nhiên là đủ” | Thiếu uniqueness/atomic effect | Unique index/conditional operation |
| “Đã thấy key trong cache thì chắc hoàn tất” | Marker có thể PROCESSING/stale | State machine/recovery |
| “FindOne trước InsertOne chống race” | Hai threads cùng thấy absent | Atomic unique/create/transaction |
| “Lưu marker trước effect là luôn an toàn” | Crash có thể làm mất effect | Transaction hoặc recoverable workflow |
| “Lưu marker sau effect là an toàn” | Crash tạo effect thiếu marker | Gắn atomic/reconcile |
| “Chỉ cần key, không cần fingerprint” | Key bị dùng lại với payload khác | Canonical request fingerprint |
| “Unique business key đã đủ API replay” | Có thể không biết original response | Lưu resource/outcome theo intent |
| “Idempotency key chặn hai khách tranh một ghế” | Hai khách dùng hai keys khác nhau | Seat-level conditional claim |
| “INCR nguyên tử là idempotent” | Retry vẫn cộng nhiều lần | Event marker/ledger |
| “QUORUM tự chống duplicate” | Không thay create-only/CAS | LWT/transaction/unique authority |
| “Redis SET NX bảo vệ order ở DB khác” | Không có atomicity xuyên hệ | DB uniqueness/protocol |
| “DynamoDB ClientRequestToken thay marker vĩnh viễn” | Có scope/window giới hạn | Business-level persisted identity |
| “Transaction callback chỉ chạy một lần” | Driver có thể retry callback | Không gửi provider/email trực tiếp |
| “Outbox đảm bảo broker chỉ giao một event” | Relay có thể publish lại | Inbox/consumer dedup |
| “Kafka offset luôn bằng eventId” | Replay/new offset và log khác | Logical event identity |
| “Idempotency key ngăn external payment double charge” | Provider có policy riêng | Provider key + verify/reconcile |
| “Token worker/fencing thay idempotency” | Cùng worker có thể retry effect | Mỗi step có operation ID |
| “Nếu marker TTL hết thì chắc intent đã chết” | Client offline/queue replay dài | Retention/business uniqueness |
| “Cache miss là chưa xử lý” | Cache có thể mất dữ liệu | Authoritative lookup |
| “Hai region eventual đều có unique ngay” | WAN partition cho hai local claims | Home owner/coordination |
| “Replay response gốc luôn phản ánh current state” | Resource đã thay đổi | Tách POST outcome và GET state |
| “Lưu cả 500 error là an toàn” | Có thể che UNKNOWN hoặc transient error | Failure classification |
| “Trả cùng orderId là đủ” | Side effect khác có thể lặp | Kiểm payment/outbox/email |
| “Test một lần pass là bảo đảm không trùng” | Race/failover/restore có thể hiếm | Concurrency và fault histories |

## 62. Bài tập thực hành

### Bài tập 1 — Timeout sau commit

Server tạo order-101 và commit, response HTTP 201 bị mất, client retry cùng key K. Vẽ timeline và giải thích vì sao client không thể kết luận request đầu chưa thực hiện.

### Bài tập 2 — Phân biệt ba loại ID

Cho hai HTTP attempts của một lần checkout. Đề xuất request ID, trace ID, idempotency key và order ID; đánh dấu cái nào phải giữ ổn định qua retry.

### Bài tập 3 — Key mới sai

Một mobile SDK sinh UUID mới mỗi lần catch(timeout). Thiết kế cách persist logical intent ID qua app restart và reconnect để cùng một checkout không tạo hai orders.

### Bài tập 4 — Payload conflict

Client gửi key K với cart-77, sau đó gửi cùng K với cart-88. Thiết kế fingerprint, error code và dữ liệu cần log để không trả nhầm saved response.

### Bài tập 5 — Canonical JSON

Hai payload cùng fields nhưng thứ tự JSON khác nhau. Hãy đề xuất canonicalization ổn định, loại bỏ traceId và nêu ví dụ một field không được loại nếu nó ảnh hưởng tiền hoặc số lượng.

### Bài tập 6 — Scope theo tenant

Tenant A và B cùng gửi Idempotency-Key=checkout-9001. Thiết kế unique key và authorization để A không nhận được order của B.

### Bài tập 7 — Check-then-insert race

Hai threads cùng đọc “key K chưa tồn tại”, rồi mỗi thread tạo order khác nhau. Vẽ lịch sử và giải thích tại sao unique marker được ghi **sau** tạo order không đủ.

### Bài tập 8 — Crash matrix

Một workflow tạo PROCESSING marker, tạo order, rồi set COMPLETED. Hãy liệt kê hậu quả nếu crash giữa từng bước và chọn transaction hoặc recovery protocol phù hợp.

### Bài tập 9 — Saved response

Order đã tạo ở trạng thái PENDING_PAYMENT, sau một giờ đã PAID. API replay response gốc hay current order state? Viết contract cho POST /orders và GET /orders/{id}.

### Bài tập 10 — HTTP statuses

Đề xuất hành vi cho NEW, PROCESSING, COMPLETED, fingerprint mismatch và UNKNOWN commit, gồm status, body/operation URL và Retry-After khi thích hợp.

### Bài tập 11 — MongoDB unique indexes

Thiết kế idempotencyRecords với unique(tenantId, operationType, idempotencyKey) và orders với unique(tenantId, checkoutId). Giải thích cần lưu ý gì về shard key nếu collections được sharded.

### Bài tập 12 — MongoDB transaction

Viết pseudocode transaction tạo order, lưu marker COMPLETED và saved 201 response. Khi marker bị duplicate trong transaction thứ hai, làm thế nào để không commit order trùng?

### Bài tập 13 — Retryable transaction callback

Một transaction callback MongoDB gọi emailService.send trước commit. Phân tích trường hợp driver retry callback rồi email gửi hai lần; thiết kế outbox thay thế.

### Bài tập 14 — DynamoDB conditional Put

Thiết kế một order item có PK dựa vào tenantId+checkoutId, dùng attribute_not_exists để create-only và response replay từ cùng item.

### Bài tập 15 — DynamoDB TransactWriteItems

Marker và order nằm ở hai items. Viết hai actions Put có điều kiện trong một transaction. Vì sao không nên thiết kế Put + Update trên **cùng một item** trong cùng TransactWriteItems?

### Bài tập 16 — DynamoDB ClientRequestToken

Giải thích sự khác biệt giữa idempotency được hỗ trợ ở cửa sổ của transactional API và một logical checkout identity phải còn hợp lệ qua mobile offline nhiều ngày.

### Bài tập 17 — Cassandra IF NOT EXISTS

Tạo bảng orders_by_checkout theo (tenantId,checkoutId), viết INSERT ... IF NOT EXISTS và mô tả cách xử lý [applied]=false bằng fingerprint và saved outcome.

### Bài tập 18 — Cassandra QUORUM

Vì sao SELECT QUORUM rồi INSERT thường không bảo đảm chỉ một người tạo resource khi requests concurrent? Nêu khi nào LWT hoặc một authority khác cần thiết.

### Bài tập 19 — Redis marker

Một worker SET idem:K PROCESSING NX EX rồi tạo order ở database khác. Worker crash ở ba thời điểm. Giải thích vì sao SET NX không tự làm hai hệ transaction nguyên tử.

### Bài tập 20 — Counter

Event E1 cộng +10 điểm thưởng, bị broker redeliver hai lần. Thiết kế ledger eventId và atomic effect/marker để points không tăng +20.

### Bài tập 21 — Business uniqueness khác idempotency

Alice và Bob tranh ghế A12 bằng hai idempotency keys khác nhau. Thiết kế điều kiện ngăn double reservation; sau đó giải thích Alice retry key cũ phải nhận kết quả nào.

### Bài tập 22 — PROCESSING stale

A claim key K, bị pause vượt lease, B takeover và ghi result. A tỉnh lại. Đề xuất generation guard/fencing ngăn A ghi đè outcome của B.

### Bài tập 23 — Saga checkout

CreateOrder, ReserveInventory, AuthorizePayment và ConfirmOrder chạy ở các services khác nhau. Đặt stable operationId cho mỗi step và mô tả retry/compensation khi payment outcome UNKNOWN.

### Bài tập 24 — Outbox/inbox

Một relay publish OrderCreated rồi crash trước khi mark delivered. Broker gửi event hai lần. Thiết kế inbox key (consumer,eventId), transaction với projection và chỉ ra vì sao outbox không đủ nếu consumer không dedup.

### Bài tập 25 — Webhook

Payment provider gửi payment.succeeded với cùng eventId ba lần và có thêm một event khác cho cùng paymentIntent. Hãy đề xuất dedup ở cấp event và state machine ở cấp paymentIntent.

### Bài tập 26 — Multi-region

Hai regions mất WAN cùng xử lý key K với local eventual stores. Cả hai tạo order và ACK. Đề xuất home owner/coordination hoặc thay đổi contract, giải thích giới hạn giữa availability và global uniqueness.

### Bài tập 27 — TTL và offline client

Idempotency marker giữ một ngày nhưng mobile có thể retry sau ba ngày. Đề xuất retention/tombstone/business unique key và cách API trả kết quả khi saved response đã hết hạn.

### Bài tập 28 — Response cache vs authority

Redis mất cache idempotency, còn MongoDB có order đã commit. Thiết kế cache miss path để không tạo mới khi marker trong Redis biến mất.

### Bài tập 29 — Tìm hiệu ứng trùng

Một API luôn replay cùng orderId nhưng đôi lúc gửi hai emails và trừ hai lần tồn. Xác định nơi cần thêm outbox, operation ID, conditional inventory update và consumer dedup.

### Bài tập 30 — Fault injection

Viết test plan tiêm: duplicate concurrent requests, timeout sau commit, worker crash sau marker, provider timeout, broker redelivery, TTL expiry, region partition và restore backup. Với mỗi trường hợp, nêu **bất biến, kết quả mong đợi và bằng chứng kiểm chứng**.

### Bài tập 31 — Thiết kế endpoint hoàn chỉnh

Thiết kế:

~~~text
POST /v1/orders
Idempotency-Key: ...
~~~

với các mục:

1. Scope identity theo tenant/user/operation.
2. Canonical payload fingerprint và conflict code.
3. NoSQL data model, indexes/conditional writes.
4. Phạm vi atomicity của order + marker + saved response.
5. Concurrent duplicate attempts và PROCESSING policy.
6. Unknown outcome/retry của mobile.
7. Outbox/inbox, payment provider, idempotent Saga steps.
8. TTL, business uniqueness và data deletion.
9. Multi-region/failover behavior.
10. Metrics, security, fault tests và reconciliation.

**Không được trả lời bằng duy nhất câu “dùng UUID và lưu Redis”**: phải chứng minh những effect ở nguồn được áp dụng đúng số lần trong điều kiện retry và lỗi.

---

**Kết luận:** Trong NoSQL phân tán, một request có thể **đã commit nhưng phản hồi bị mất**. Retry là cần thiết để phục hồi trải nghiệm người dùng, nhưng nếu mỗi attempt được coi là một ý định mới, hệ thống có thể tạo **đơn hàng, reservation, payment hoặc counter effect trùng**. **Idempotency key** phải ổn định theo logical intent, có **tenant/operation scope**, được đối chiếu với **request fingerprint**, và dẫn tới **kết quả đã lưu** để các attempts sau nhận lại cùng outcome. Điểm quan trọng nhất không phải header, mà là **atomicity hoặc recovery protocol** giữa **unique marker, business effect và saved response**. MongoDB transactions/unique indexes, DynamoDB conditional Put/transactions, Cassandra LWT và Redis atomic commands có phạm vi bảo đảm khác nhau; không được lấy một cache hoặc một thao tác check-then-insert thay cho nguồn uniqueness có thẩm quyền. Với workflow bất đồng bộ, phải ghép **outbox/inbox, stable step IDs, provider idempotency, trạng thái UNKNOWN, leases/fencing khi takeover, retention và reconciliation**. Một hệ thống đáng tin không hứa mạng sẽ không giao trùng; nó thiết kế để **cùng một ý định được gửi lại nhiều lần mà không làm sai trạng thái nghiệp vụ và vẫn có thể trả kết quả xác định cho người dùng**.
