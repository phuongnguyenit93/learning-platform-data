# Khóa lặp an toàn cho thao tác có tác dụng phụ

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Đồng thời và lặp an toàn

## 1. Bài toán: gửi yêu cầu một lần nhưng tác dụng phụ xảy ra hai lần

Trong kiến trúc microservices, người gọi và người nhận trao đổi qua mạng. Một request có thể đã được server xử lý và commit thành công, nhưng phản hồi bị mất vì kết nối đứt, client timeout, gateway đổi tuyến hoặc tiến trình bị khởi động lại. Người gọi chỉ thấy **không nhận được câu trả lời**; họ không thể suy ra chắc chắn yêu cầu chưa được thực hiện.

Ví dụ một người dùng nhấn **Thanh toán**:

```text
Client            API Gateway              PaymentService
  | POST /pay          |                         |
  |------------------->|------------------------>|
  |                    |                         | Tạo giao dịch
  |                    |                         | COMMIT thành công
  |                    |<--------- response -----X  Mất phản hồi
  |<---- timeout ------|
  |
  | Người dùng bấm thử lại
  v
POST /pay một lần nữa
```

Nếu PaymentService coi mỗi request là một ý định thanh toán mới, người dùng có thể bị thu tiền hai lần. Rủi ro tương tự xuất hiện khi:

- Người dùng nhấn **Đặt hàng** hai lần do giao diện chậm.
- Mobile app tự retry khi chuyển giữa Wi-Fi và mạng di động.
- API Gateway/HTTP client retry một POST sau lỗi 502, 503 hoặc timeout.
- Consumer nhận lại cùng message từ broker do at-least-once delivery.
- Worker restart sau khi đã thực hiện tác dụng phụ nhưng chưa ACK message.
- Saga gửi lại command vì không nhận được kết quả bước trước.
- Webhook provider phát lại cùng một sự kiện do chưa nhận được ACK.
- Batch job được khởi chạy lại sau khi đã tạo một phần dữ liệu.

**Khóa lặp an toàn (idempotency key)** là một cơ chế giúp các lần gọi lặp **cùng một ý định nghiệp vụ** nhận kết quả nhất quán mà không thực thi tác dụng phụ ngoài ý muốn nhiều lần.

Điểm then chốt:

> Khi người gọi retry vì chưa biết kết quả, cùng một business intent phải được nhận diện bằng cùng một khóa; phía service sở hữu tác dụng phụ phải dùng khóa đó để quyết định nên xử lý, chờ, trả kết quả cũ hay báo xung đột.

Idempotency key không thể thay thế bảo vệ transaction, ràng buộc duy nhất hoặc thiết kế nghiệp vụ. Đây là một phần của **hợp đồng xử lý request và chống lặp**, không đơn thuần là một header cho đẹp.

## 2. Định nghĩa idempotency: lặp lại không tạo thêm tác dụng phụ

Trong toán học, một hàm `f` idempotent khi áp dụng lại không làm thay đổi kết quả sau lần đầu: `f(f(x)) = f(x)`. Trong API và hệ phân tán, ý tưởng tương ứng là **thực hiện lại cùng một yêu cầu có định danh ổn định không làm lặp tác dụng phụ nghiệp vụ**, trong phạm vi hợp đồng đã được công bố.

Ví dụ một intent “tạo đơn cho giỏ hàng tại thời điểm xác nhận”:

```text
request key = order-intent-8ab2

Lần 1: tạo Order ORD-91
Lần 2: cùng key -> trả ORD-91
Lần 3: cùng key -> trả ORD-91
```

Điều này không có nghĩa không có thêm log, tracing hoặc số lần network call. Idempotency tập trung vào **kết quả và side effect nghiệp vụ** được định nghĩa, chẳng hạn số đơn mới được tạo, số tiền bị thu hoặc số lần reservation tăng.

### 2.1. Phân biệt ba khái niệm thường bị lẫn

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Idempotency | Lặp một **ý định** có làm tác dụng phụ phát sinh thêm không? | Cùng key không tạo thanh toán thứ hai |
| Deduplication | Có nhận ra một message/request đã thấy trước đó không? | `eventId` đã có trong inbox |
| Exactly-once effect | Tác dụng phụ nghiệp vụ được áp dụng đúng một lần trong phạm vi đã định nghĩa không? | Stock chỉ trừ một lần dù command đến lặp |

Một broker có thể có cơ chế giao nhận hoặc xử lý exactly-once trong phạm vi sản phẩm, topic hoặc transaction nhất định. Điều đó **không tự bảo đảm** một email được gửi đúng một lần hoặc bên thứ ba chỉ thu tiền một lần. Side effect nằm ngoài transaction của broker vẫn cần cơ chế riêng.

### 2.2. Idempotent operation khác idempotent delivery

HTTP `GET` được thiết kế là phương thức an toàn; `PUT` và `DELETE` được định nghĩa là idempotent về hiệu quả dự kiến theo semantics HTTP, còn `POST` không mặc định idempotent. Nhưng implementation có thể vẫn sai: GET kích hoạt giao dịch ngoài mong muốn, PUT làm tăng counter mỗi lần, DELETE gửi email hủy không giới hạn. Cần xem **behavior thật**, không chỉ động từ HTTP.

Một `POST /payments` có thể được làm idempotent bằng khóa. Một `PUT` vốn có semantics idempotent vẫn cần concurrency control và có thể cần business key nếu nó gọi hệ thống ngoài.

## 3. Khóa lặp an toàn định danh một ý định, không định danh một lần thử

Các trường cần phân biệt:

- **Business intent ID:** định danh việc người dùng hoặc workflow thực sự muốn làm, ví dụ một ý định thanh toán.
- **Idempotency key:** khóa mà các lần thử thực hiện cùng intent dùng chung để chống lặp side effect.
- **Request/attempt ID:** định danh một HTTP request hoặc một lần thử qua mạng; thường mới mỗi lần.
- **Message ID:** định danh một message phát trên broker; không nhất thiết giống business intent khi message được phát lại theo cách khác.
- **Correlation ID / trace ID:** giúp liên kết log và tracing; không mặc định bảo đảm uniqueness hay idempotency.
- **Resource ID:** ID của kết quả như order hoặc payment; có thể được tạo sau khi nhận intent.

Ví dụ:

```text
Business intent    = mua 2 sản phẩm trong giỏ X
Idempotency key    = 01JCK2A9EXAMPLE
HTTP attempt #1    = req-001
HTTP attempt #2    = req-002
Resulting order ID = ord-8042
```

**Cùng một ý định → cùng key**, dù `requestId` thay đổi qua các lần thử.

**Ý định mới → key mới**, ngay cả khi payload giống hệt. Người dùng có thể cố tình mua hai đơn có cùng sản phẩm và số tiền. Nếu dùng hash của toàn bộ payload làm khóa duy nhất mà không có danh tính intent, hai giao dịch hợp lệ có thể bị gộp sai.

### 3.1. Ai tạo khóa?

Có thể do client, BFF hoặc service điều phối sinh, tùy workflow:

- Client tạo UUID/ngẫu nhiên đủ khó đoán **trước lần gửi đầu**, giữ nguyên khi retry cùng intent.
- Với một workflow server-side, service điều phối tạo key ổn định theo `orderId + operationType + operationVersion` nếu mỗi order chỉ có một intent tương ứng.
- Với broker message, consumer có thể dùng business key của command hoặc event ID theo semantics phù hợp.
- Với bên thứ ba, hệ thống gửi **cùng provider idempotency key** khi thử lại cùng intent theo contract provider.

Key không phải thông tin xác thực. Không dùng key thay token, quyền truy cập hoặc xác minh sở hữu resource.

### 3.2. Không tạo khóa mới trong mỗi lần retry

Ví dụ sai:

```java
for (int attempt = 0; attempt < 3; attempt++) {
    String key = UUID.randomUUID().toString(); // SAI nếu cùng intent
    paymentClient.charge(request, key);
}
```

Ví dụ hợp lý hơn:

```java
String key = intent.idempotencyKey(); // Ổn định qua các attempts

for (int attempt = 0; attempt < maxAttempts; attempt++) {
    paymentClient.charge(request, key);
}
```

Code chỉ minh họa nguyên tắc. Retry thật cần deadline, phân loại lỗi, backoff, rate limit và tra cứu kết quả khi outcome chưa rõ.

## 4. Hợp đồng API của idempotency key

Ví dụ endpoint:

```http
POST /payments/authorizations
Authorization: Bearer <access-token>
Idempotency-Key: 01JCK2A9EXAMPLE
Content-Type: application/json
```

```json
{
  "orderId": "ord-8042",
  "amountMinor": 250000,
  "currency": "VND"
}
```

Response lần đầu khi đã hoàn tất:

```http
HTTP/1.1 201 Created
Location: /payments/pay-1042
Content-Type: application/json
```

```json
{
  "paymentId": "pay-1042",
  "orderId": "ord-8042",
  "status": "AUTHORIZED",
  "amountMinor": 250000,
  "currency": "VND"
}
```

Nếu caller gửi lại **cùng key và cùng intent**, server có thể trả lại kết quả đã lưu, ví dụ cùng `paymentId=pay-1042`, thay vì tạo thêm authorization.

Không có một quy tắc toàn cầu bắt mọi API phải trả cùng byte của HTTP response hoặc cùng status code trong mọi trường hợp. Contract phải định nghĩa:

1. Khi key chưa tồn tại, server xử lý gì?
2. Khi key đang được xử lý, server trả trạng thái nào?
3. Khi key đã hoàn tất, server trả lại response trước hay một đại diện trạng thái hiện tại?
4. Khi cùng key được gửi với payload khác, trả lỗi nào?
5. Key có phạm vi theo tenant, account, operation hay resource nào?
6. Key tồn tại bao lâu? Sau khi hết hạn, retry cũ có còn được chống lặp?
7. Khi server không thể xác định kết quả của provider ngoài, client truy vấn trạng thái thế nào?
8. Key có được phép sử dụng lại cho một intent mới không? Thường không trong thời hạn bảo vệ.

Có thể công bố một HTTP header như `Idempotency-Key` và error schema rõ ràng. Cơ chế lưu trạng thái phía server mới quyết định việc chống lặp, không phải sự hiện diện của header.

## 5. Ba tình huống cần xử lý cùng một khóa

### 5.1. Lần đầu nhận khóa

```text
Key K chưa tồn tại
    |
    v
Kiểm tra auth, scope, validation
    |
    v
Ghi nhận intent K bền vững
    |
    v
Thực thi tác dụng phụ theo policy
    |
    v
Lưu kết quả và trả response
```

Với business operation hoàn toàn nằm trong một database, có thể xử lý idempotency record và domain write trong cùng transaction. Với side effect ở provider ngoài, cần state machine, provider key và reconciliation; không thể chỉ dùng một DB transaction local để bảo đảm thao tác từ xa đã xảy ra đúng một lần.

### 5.2. Khóa lặp khi yêu cầu đang IN_PROGRESS

Hai request cùng key có thể đến **đồng thời** trước khi lần đầu hoàn tất:

```text
Request A (K) ----- xử lý lâu ------>
Request B (K) ----------- đến khi A đang chạy
```

Request B không được bắt đầu một side effect thứ hai. Có thể:

- Trả `202 Accepted` hoặc một trạng thái `IN_PROGRESS` kèm operation ID.
- Trả `409 Conflict` hoặc lỗi “same-key request already processing” theo contract của API.
- Chờ kết quả của A **trong một deadline hữu hạn** rồi trả kết quả tương đương.
- Trả URI để query trạng thái thay vì giữ kết nối.

Chọn cách nào phụ thuộc API. Không nên chặn thread vô hạn hoặc tự tạo charge thứ hai để “chạy song song cho nhanh”.

### 5.3. Khóa lặp sau khi đã COMPLETED

Khi result đã được lưu:

```text
Request K lần 1 -> tạo pay-1042
Request K lần 2 -> trả kết quả gắn với pay-1042
Request K lần 3 -> trả kết quả gắn với pay-1042
```

Nếu response mới trả trạng thái hiện tại thay vì response gốc, cần công bố rõ. Ví dụ lần đầu payment là PENDING, sau đó AUTHORIZED; một lần gọi sau cùng key có thể trả PENDING đã cache hoặc AUTHORISED hiện tại tùy contract. **Quan trọng nhất là không thực hiện charge mới.**

## 6. Khóa giống nhau nhưng payload khác nhau: phải ngăn lẫn intent

Một lỗi thường gặp:

```text
POST /payments
key=K, amountMinor=250000

POST /payments
key=K, amountMinor=900000
```

Nếu service chỉ tìm K rồi trả thành công của request đầu tiên, caller của request thứ hai có thể nhầm rằng khoản 900.000 đã được xử lý. Nếu service lại thực hiện request thứ hai, nó phá idempotency.

Cần lưu **request fingerprint** hoặc các thuộc tính xác định intent để phát hiện reuse sai.

Ví dụ record:

```json
{
  "scope": "tenant-42:payment-authorization",
  "idempotencyKey": "K",
  "requestFingerprint": "sha256:example-digest",
  "state": "COMPLETED",
  "resourceId": "pay-1042"
}
```

Khi nhận lại:

- Cùng scope + key + fingerprint → xử lý như retry.
- Cùng scope + key nhưng fingerprint khác → báo conflict/validation error theo contract.
- Key khác → có thể là intent mới, nhưng business rules vẫn có thể từ chối nếu trùng order/payment.
- Khác tenant hoặc khác resource scope → không tự coi là cùng intent.

### 6.1. Fingerprint nên dựa trên dữ liệu chuẩn hóa

Hash toàn bộ raw JSON byte có thể coi hai request tương đương là khác nhau do thứ tự property, whitespace hoặc cách viết số. Nếu dùng fingerprint, cần định nghĩa canonicalization rõ:

- Các trường nào là phần **ngữ nghĩa** của intent?
- Có dùng `tenantId`, `accountId`, `orderId`, amount, currency, operation type không?
- Có loại trừ tracing headers, timestamp của attempt, retry counters không?
- Với decimal, đơn vị tiền và cách chuẩn hóa được xác định ra sao?
- Với các collection, thứ tự có ý nghĩa không?
- Với schema evolution, field optional mới có khiến fingerprint cũ bị thay đổi không?

Có thể lưu các trường business đã chuẩn hóa thay vì chỉ hash. Không nên dùng hash làm bằng chứng ủy quyền; nó chỉ hỗ trợ so sánh intent trong scope được bảo vệ.

### 6.2. Cùng payload không nhất thiết cùng intent

Hai đơn hàng khác nhau có thể có cùng danh sách SKU, quantity, amount và địa chỉ giao hàng. Vì vậy **fingerprint không thay thế idempotency key**. Nó chỉ giúp phát hiện sai lệch khi cùng key bị tái sử dụng.

## 7. Phạm vi khóa (scope) là một phần của contract

Không phải mọi idempotency key phải duy nhất trên toàn hệ thống. Một thiết kế thường cần composite identity:

```text
(tenant_id, operation_type, idempotency_key)
```

Hoặc:

```text
(account_id, resource_id, operation_name, idempotency_key)
```

Ví dụ key `K` ở tenant A không nên trả kết quả thanh toán của tenant B. Cũng không nên cho một key dùng ở `CreateOrder` vô tình khóa thao tác `RefundPayment` chỉ vì cùng chuỗi.

Các quyết định cần định nghĩa:

- Key có uniqueness trên tenant, merchant, user, account hay toàn hệ thống?
- Mọi operation hay mỗi operation có namespace riêng?
- Cùng một key có thể dùng cho nhiều bản ghi con hợp lệ không?
- Key dài tối đa bao nhiêu, được phép dùng ký tự gì?
- Có chống key cố ý rất lớn để gây tốn memory/storage không?
- Client không có quyền trên resource thì kiểm tra gì trước khi đọc/trả kết quả cũ?

Phạm vi không rõ có thể tạo lỗi nghiêm trọng: trả response của người khác, khóa nhầm giao dịch hoặc cho phép dùng lại key vượt tenant. **Authorization phải được kiểm tra ngay cả khi trả kết quả đã cache theo key.**

## 8. Mô hình trạng thái của một idempotency record

Một thiết kế bền vững có thể dùng state machine:

```text
ABSENT
  |
  v
IN_PROGRESS
  |
  +------> COMPLETED
  |
  +------> BUSINESS_REJECTED
  |
  +------> OUTCOME_UNKNOWN
               |
               +----> COMPLETED
               +----> BUSINESS_REJECTED
               '---> NEEDS_RECONCILIATION
```

Các trạng thái phụ thuộc hệ thống, không phải chuẩn bắt buộc.

| State | Ý nghĩa | Retry cùng key nên làm gì? |
| --- | --- | --- |
| ABSENT | Chưa thấy intent | Có thể bắt đầu xử lý sau validation |
| IN_PROGRESS | Có worker đang thực hiện | Không chạy thêm side effect; chờ/trả pending |
| COMPLETED | Đã có kết quả thành công | Trả kết quả đã cam kết |
| BUSINESS_REJECTED | Có từ chối nghiệp vụ xác định | Trả cùng loại kết quả hoặc status theo contract |
| OUTCOME_UNKNOWN | Không biết provider đã xử lý hay chưa | Query/reconcile, không tự tạo intent mới |
| NEEDS_RECONCILIATION | Cần can thiệp/đối soát | Giữ bản ghi, cảnh báo và cung cấp trạng thái |

Không coi `IN_PROGRESS` là trạng thái tồn tại mãi nếu worker crash. Cần lease, heartbeat, timeout, owner/version và một tiến trình phục hồi. Nhưng hết lease **không đồng nghĩa** tác dụng phụ ở provider chưa xảy ra.

### 8.1. Retry business error khác retry infrastructure error

Một payment bị từ chối chắc chắn (card declined) thường là **kết quả nghiệp vụ**, không phải lỗi transient. Cần quy định có lưu/cached kết quả decline theo key không. Nếu khách đổi thẻ hoặc số tiền, đó có thể là ý định mới hoặc một bước mới theo workflow.

Một lỗi 503 trước khi request được ghi nhận khác với timeout sau khi side effect đã commit. Cần phân loại trạng thái theo evidence, không chỉ status code.

## 9. Bảo đảm tính nguyên tử khi nhiều request cùng key

Một kiểm tra kiểu:

```text
if (!exists(K)) {
    doSideEffect();
    save(K);
}
```

**Không an toàn dưới concurrency**. Hai worker có thể cùng thấy K chưa tồn tại rồi cùng thực hiện side effect trước khi một worker save bản ghi.

Timeline:

```text
Worker A: SELECT K -> not found
Worker B: SELECT K -> not found
Worker A: charge()
Worker B: charge()
Worker A: INSERT K
Worker B: INSERT K -> unique conflict
```

Unique constraint ở bước cuối đã quá muộn để ngăn **hai charge**. Idempotency phải bảo vệ quá trình **claim intent trước khi thực hiện side effect** hoặc đưa business change vào cùng transaction an toàn.

### 9.1. Unique constraint và atomic claim

Ví dụ bảng:

```sql
CREATE TABLE idempotency_records (
    tenant_id           VARCHAR(64) NOT NULL,
    operation_type      VARCHAR(64) NOT NULL,
    idempotency_key     VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    state               VARCHAR(32) NOT NULL,
    resource_id         VARCHAR(128),
    response_code       INTEGER,
    response_body       TEXT,
    owner_token         VARCHAR(128),
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL,
    expires_at          TIMESTAMP,
    PRIMARY KEY (
        tenant_id, operation_type, idempotency_key
    )
);
```

Các trường và kiểu là ví dụ, không phải schema bắt buộc. Bảng có thể cần encryption/redaction, retention và dung lượng phù hợp.

Một worker cố tạo bản ghi `IN_PROGRESS` với composite PK. Chỉ một tiến trình claim được K. Những request cùng key khác phải đọc state đã tồn tại, so fingerprint và phản hồi theo contract.

### 9.2. Một transaction cho idempotency record và domain change

Nếu side effect là cập nhật trong **cùng database**, có thể xử lý nguyên tử:

```sql
BEGIN;

-- Claim key K bằng INSERT có unique constraint.
-- Nếu K đã tồn tại, không chạy domain mutation lần nữa.
INSERT INTO idempotency_records (
    tenant_id, operation_type, idempotency_key,
    request_fingerprint, state, created_at, updated_at
) VALUES (
    'tenant-42', 'CREATE_ORDER', 'K',
    'fingerprint-v1', 'IN_PROGRESS',
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
);

INSERT INTO orders (
    order_id, tenant_id, status
) VALUES (
    'ord-8042', 'tenant-42', 'PENDING'
);

UPDATE idempotency_records
SET state = 'COMPLETED',
    resource_id = 'ord-8042',
    response_code = 201,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 'tenant-42'
  AND operation_type = 'CREATE_ORDER'
  AND idempotency_key = 'K';

COMMIT;
```

Đây là mô hình ý tưởng, không phải SQL có xử lý conflict đầy đủ. Nếu insert key va unique, transaction cần đọc bản ghi trước và **không tạo order thứ hai**. Nếu một transaction rollback, cả bản ghi key và order do transaction tạo cũng rollback, theo ràng buộc database.

### 9.3. Locking và optimistic concurrency

Có thể dùng row-level lock, conditional update với version hoặc unique constraints để phối hợp nhiều worker. `SELECT` rồi `INSERT` không đủ nếu không có atomicity/constraint đúng. Distributed lock ngoài database có thể hữu ích trong một số hệ thống nhưng **không thay cho constraint ở nguồn sự thật** khi khóa có thể hết lease, bị mất do network partition hoặc có hai chủ cùng nghĩ mình sở hữu lock.

## 10. Redis/cache và sự nguy hiểm khi chỉ lưu trạng thái tạm

Một số thiết kế dùng Redis `SET NX` để claim key:

```text
SET idempotency:tenant-42:K "IN_PROGRESS" NX EX 600
```

Điều này có thể giúp điều phối nhanh, nhưng **chỉ claim bằng TTL không đủ bảo đảm chống lặp side effect bền vững**:

- Redis có thể mất dữ liệu hoặc failover theo cấu hình.
- Lease hết hạn trong lúc worker cũ vẫn thực hiện tác vụ.
- Worker B claim key sau TTL và gọi provider ngoài lần nữa.
- Cache record bị evict trước khi mọi retry cũ kết thúc.
- Trạng thái Redis và DB business có thể không commit atomically.

Với nghiệp vụ nhạy cảm như thu tiền, tạo đơn hay hoàn tiền, cần cân nhắc **durable idempotency ledger trong database của owner**, business uniqueness và idempotency của provider. Redis có thể là lớp tăng tốc, nhưng không nên là bằng chứng duy nhất rằng một charge đã hoặc chưa xảy ra khi dữ liệu có thể biến mất.

### 10.1. Lease cần fencing hoặc kiểm tra quyền ghi

Nếu worker A giữ lease, rồi bị chậm quá hạn, worker B có thể giành quyền xử lý. A thức dậy và cố ghi kết quả cũ. Có thể dùng version/fencing token để những writer cũ không được cập nhật trạng thái sau khi quyền điều phối thay đổi. Với provider ngoài không hỗ trợ fencing, cần tra cứu trạng thái/idempotency của provider thay vì suy rằng lease mới ngăn được charge trùng.

## 11. Cửa sổ lỗi khi side effect ở một hệ thống ngoài

Đây là trường hợp khó hơn một local DB transaction. Ví dụ PaymentService gọi một cổng thanh toán bên thứ ba:

```text
1. PaymentService ghi K -> IN_PROGRESS vào DB.
2. PaymentService gọi provider. Provider CAPTURE thành công.
3. PaymentService crash trước khi lưu response/result.
4. Caller retry với K.
5. DB vẫn cho thấy IN_PROGRESS hoặc OUTCOME_UNKNOWN.
```

Một DB transaction local **không bao trùm** trạng thái đã commit ở provider. Nếu retry request provider với key mới, có thể thu tiền lần hai.

Cách thiết kế có kiểm soát:

1. Tạo payment intent/resource ID bền vững trước khi gọi provider.
2. Gắn **provider idempotency key** ổn định với chính intent.
3. Lưu mapping nội bộ `businessIntent -> providerKey -> providerReference`.
4. Khi gọi provider lần đầu, truyền đúng provider key theo hợp đồng bên thứ ba.
5. Nếu timeout/crash, khôi phục intent và **query provider** bằng key/reference khi có API.
6. Nếu provider hỗ trợ retry cùng key an toàn, chỉ retry trong điều kiện và thời hạn họ công bố.
7. Nếu không chắc kết quả, giữ `OUTCOME_UNKNOWN` và đối soát; không khẳng định FAILED.
8. Chỉ đánh COMPLETED khi có bằng chứng thỏa business rule.
9. Khi cần rollback nghiệp vụ, dùng void/refund theo trạng thái thật, không coi timeout là rollback.

**Một khóa ở API Gateway không tự kiểm soát side effect tại provider ngoài.** Bảo đảm phải được đặt ở bên sở hữu operation và phối hợp với hợp đồng của provider.

### 11.1. Tại sao không giữ DB transaction mở khi gọi provider?

Giữ transaction database mở qua một lời gọi mạng có thể kéo dài nhiều giây/phút, chiếm connection/lock và gây deadlock hoặc timeout. Hơn nữa, rollback local DB sau khi provider charge thành công không đảo ngược được provider charge. Thường nên dùng intent ledger và state machine có bước xử lý ngoài transaction ngắn.

## 12. Outbox, inbox và idempotency kết hợp như thế nào?

**Transactional outbox** giúp một service ghi domain change và intent publish event/command trong cùng local transaction:

```text
Local DB transaction:
  - update order/payment state
  - insert outbox message
  - commit

Publisher:
  - read outbox
  - publish to broker
  - mark progress
```

Nếu publisher crash sau publish nhưng trước khi đánh dấu, event có thể được phát lại. **Consumer inbox/dedup** có thể dùng `messageId` để không áp dụng cùng một message hai lần. Nhưng business intent có thể được phát dưới **message ID khác** sau một retry/các bước orchestration. Khi đó consumer cần thêm **business idempotency key** hoặc unique constraint theo operation.

### 12.1. Message ID và business key khác nhau

Ví dụ:

```text
Saga sends ReserveInventory(key=ord-8042:reserve)
Message publication #1 -> msg-100
Message publication #2 -> msg-101
```

Nếu Inventory chỉ dedup theo `msg-100` thì `msg-101` có thể trừ stock lần nữa. Cần biết hai message thuộc cùng **business operation**.

Ngược lại, nếu một event định kỳ biểu diễn hai hành động nghiệp vụ khác nhau với payload tương tự, dùng hash payload làm key có thể gộp nhầm. Idempotency luôn phải dựa trên semantics.

### 12.2. Inbox cùng transaction domain

Một consumer có thể:

```text
BEGIN
  INSERT processed_messages(consumer, message_id)
  APPLY domain effect
COMMIT
ACK broker message
```

Khi event đến lại, unique constraint của inbox ngăn lặp effect. Nếu ACK trước commit, crash có thể mất xử lý. Nếu commit rồi crash trước ACK, event được giao lại nhưng inbox chặn duplicate.

Với side effect ngoài database (gửi email, gọi provider), transaction inbox **không tự bảo đảm** side effect được thực hiện đúng một lần. Có thể cần outbox từ consumer, provider key, trạng thái gửi và reconciliation.

## 13. Idempotency trong Saga và các hành động bù trừ

Một Saga đặt hàng có các command:

```text
CreateOrder
ReserveInventory
AuthorizePayment
ConfirmOrder
```

Khi Payment bị từ chối chắc chắn, coordinator có thể phát:

```text
ReleaseInventory
MarkOrderRejected
```

Mỗi command có thể được gửi lặp vì coordinator crash hoặc reply mất. Cần key ổn định cho từng business operation:

| Operation | Khóa gợi ý | Điều phải chống lặp |
| --- | --- | --- |
| CreateOrder | `checkout-intent-id` | Tạo hai orders cho cùng intent |
| ReserveInventory | `orderId:reserve:v1` | Giữ stock hai lần |
| AuthorizePayment | `orderId:authorize:paymentIntentId` | Tạo hai authorizations |
| CapturePayment | `paymentIntentId:capture` | Thu tiền hai lần |
| ReleaseInventory | `reservationId:release` | Hoàn stock hai lần |
| RefundPayment | `paymentId:refundIntentId` | Hoàn tiền hai lần |
| CreateShipment | `orderId:shipmentIntentId` | Tạo hai shipments |

Các chuỗi chỉ là minh họa. Key cần xét nghiệp vụ **có cho phép nhiều lần cùng operation không**. Ví dụ một payment có thể có nhiều partial refunds hợp lệ; dùng một key `paymentId:refund` cho mọi refund sẽ gộp nhầm các ý định khác nhau. Mỗi refund intent phải có định danh riêng và tổng refund vẫn phải được kiểm soát bởi business invariant.

### 13.1. Compensation cũng phải idempotent

Khi `ReleaseReservation` được nhận lần đầu:

```text
Reservation ACTIVE -> RELEASED
Stock available +2
```

Lần thứ hai:

```text
Reservation RELEASED -> RELEASED
Stock available +0
```

Một handler không được cộng stock trên mọi lần gọi. Có thể dùng conditional update/row lock trong một DB transaction để chỉ thực hiện biến đổi stock khi trạng thái reservation chuyển thành công lần đầu.

### 13.2. Idempotency không thay thế business invariant

Ngay cả khi mỗi intent có key riêng, hai người dùng vẫn có thể đồng thời giữ cùng số hàng cuối. Inventory cần transaction/optimistic concurrency bảo vệ số lượng khả dụng. Payment cần quy tắc không capture vượt số được ủy quyền và không refund vượt số đã capture.

**Khóa lặp an toàn chống lặp cùng intent; concurrency control bảo vệ tính đúng đắn giữa các intent khác nhau.**

## 14. Thiết kế idempotency cho webhook

Webhook có đặc tính at-least-once từ nhiều provider: khi không nhận được response thành công, provider có thể phát lại cùng event. Một số hệ thống cũng cho phép operator replay thủ công.

Ví dụ:

```json
{
  "eventId": "evt-1024",
  "type": "payment.captured",
  "paymentId": "pay-8042",
  "capturedAmountMinor": 250000,
  "currency": "VND"
}
```

Consumer nên:

1. **Xác minh chữ ký/authenticity** và kiểm tra quyền nguồn gửi trước.
2. Đọc định danh event/message theo contract của provider.
3. Dùng inbox/unique constraint để ghi nhận event đã xử lý.
4. Liên hệ event với payment intent authoritative.
5. Chuyển state có điều kiện; không capture hoặc cộng tổng tiền trùng.
6. ACK sau khi xử lý bền vững theo policy.
7. Hỗ trợ replay, event trễ và đối soát khi provider gửi không theo thứ tự.

Nếu cùng một business transition được báo bằng hai event ID khác nhau, chỉ dedup event ID có thể chưa đủ. Business state machine phải ngăn chuyển `CAPTURED -> CAPTURED` tạo side effect lần hai.

### 14.1. Event lặp không đồng nghĩa event mới

Ví dụ PaymentCaptured và PaymentRefunded đều liên quan cùng `paymentId`, nhưng là **hai sự thật nghiệp vụ khác nhau**, không được dùng một idempotency key duy nhất để bỏ qua event refund chỉ vì payment từng được xử lý.

Chọn key theo event/operation semantics, kết hợp owner state và business invariant.

## 15. Response caching: lưu cái gì để trả lại khi retry?

Một idempotency store có thể lưu:

- HTTP status code và các header an toàn cần tái tạo.
- Body đã được phép lưu theo retention/security policy.
- Resource ID và trạng thái cuối.
- Business result code và timestamp.
- Request fingerprint, scope và version.
- Trạng thái đang chạy hoặc kết quả chưa rõ.
- Error classification (business decline vs transient infrastructure).

Có hai chiến lược:

**Cache response gốc:** retry trả cùng status/body như lần đầu. Đơn giản cho contract nhưng cần kiểm soát dữ liệu nhạy cảm và khả năng response cũ không còn phản ánh trạng thái hiện tại.

**Lưu result reference:** retry lấy `resourceId` đã tạo và trả một đại diện kết quả theo contract. Linh hoạt hơn nhưng có thể thay đổi status/body; phải định nghĩa rõ.

Không trả dữ liệu nhạy cảm từ result cache cho request chỉ có key mà không được authorization. Nếu dữ liệu chứa PII/token, nên cân nhắc lưu tối thiểu và có cơ chế masking/encryption.

### 15.1. HTTP status cho concurrent/same-key requests

Không có một quy tắc duy nhất bắt buộc mọi API:

| Trường hợp | Một thiết kế có thể chọn | Điều phải công bố |
| --- | --- | --- |
| Key mới | `201 Created`, `200 OK` hoặc `202 Accepted` | Resource đã tạo, đã hoàn tất hay chỉ tiếp nhận |
| Cùng key đã COMPLETED | Trả lại kết quả đã lưu hoặc 200 với resource cũ | Không tạo side effect mới |
| Cùng key đang IN_PROGRESS | `202`, `409` hoặc chờ có giới hạn | Có operation ID, retry/query policy |
| Cùng key, payload khác | `409` hoặc `422` theo contract | Không xử lý request khác dưới key cũ |
| Business rejection đã biết | Cùng business result hoặc lỗi đã công bố | Không tự retry tạo intent mới |
| Result UNKNOWN | `202`/trạng thái chờ hoặc lỗi có hướng dẫn tra cứu | Không khẳng định thất bại/chưa thực hiện |

Nên xem `Retry-After` khi có trạng thái tạm thời và sử dụng Problem Details/error code ổn định khi phù hợp. Điều kiện quan trọng hơn mã cụ thể là **consumer có thể quyết định hành động tiếp theo một cách an toàn**.

## 16. Thời hạn lưu key và vấn đề retry rất muộn

Một idempotency record không thể luôn được lưu vô hạn nếu lưu lượng rất lớn; nhưng xóa quá sớm khiến một retry trễ được coi là intent mới.

Ví dụ:

```text
T0: Client gửi charge key K.
T1: Provider charge thành công.
T2: Server lưu COMPLETED(K).
T3: Sau 24 giờ, record K bị xóa.
T4: Một job cũ retry K.
```

Nếu T4 được xử lý như request mới, có thể charge lần hai. Chính sách retention cần xét:

- Thời gian retry tối đa của client, gateway, broker và worker.
- Thời gian provider còn lưu idempotency key.
- Thời hạn mà người dùng có thể gửi lại cùng intent.
- Thời gian webhook/replay và các job chậm.
- Ràng buộc nghiệp vụ/accounting cần giữ để đối soát.
- Nhu cầu GDPR/privacy, lưu trữ, xóa dữ liệu và chi phí storage.

Không có một TTL chuẩn chung áp dụng cho thanh toán, đơn hàng, xuất email và update profile.

### 16.1. Business uniqueness là lớp bảo vệ sau khi key hết hạn

Với nghiệp vụ nhạy cảm, có thể giữ một **business identity** ổn định lâu hơn idempotency cache:

```text
orders.checkout_intent_id UNIQUE
payments.provider_intent_id UNIQUE
refunds.refund_intent_id UNIQUE
```

Khi key HTTP hết hạn, hệ thống vẫn có thể nhận ra một intent đã tồn tại theo định danh nghiệp vụ được phép giữ. Nhưng uniqueness phải phản ánh đúng domain: không được cấm một khách mua hai đơn giống nhau chỉ vì cùng giỏ hàng hoặc cùng số tiền.

### 16.2. TTL không được làm mất trạng thái IN_PROGRESS mơ hồ

Một worker bị treo có thể khiến key IN_PROGRESS lâu hơn dự kiến. Không xóa record rồi tự tạo side effect mới ngay sau TTL. Cần xác định trạng thái thực theo owner/provider và cơ chế claim lại có fencing hoặc reconciliation.

## 17. Khi nào không nên lưu kết quả mãi?

Một operation có thể thất bại do validation sai và không tạo side effect; có thể không cần giữ idempotency record hoặc chỉ giữ một thời gian ngắn. Nhưng nếu một business decline đã được provider xử lý và có reference, lưu outcome có thể cần để tránh nhận lại cùng command với một kết quả khác.

Hãy phân biệt:

1. **Reject trước khi claim key và trước side effect**: có thể không cần lưu nếu contract cho phép sửa request với cùng key; phải công bố rõ.
2. **Reject nghiệp vụ sau khi đã ghi nhận intent**: có thể cần lưu business result để các lần retry nhất quán.
3. **Transient infrastructure failure**: có thể retry sau, nhưng cần biết đã có side effect chưa.
4. **Unknown outcome**: giữ pending/reconciliation, không phát lại với key khác.

Chỉ cache HTTP 500 vô điều kiện mãi mãi có thể khiến client không thể phục hồi; nhưng không cache bất kỳ lỗi nào cũng nguy hiểm nếu lỗi đó xảy ra **sau khi** side effect đã thành công. Phải xây chính sách trên **vị trí lỗi trong lifecycle**, không chỉ mã HTTP.

## 18. Một implementation Java/Spring Boot minh họa

Một service tạo order nội bộ có thể dùng idempotency table và unique constraint. Mô hình khái niệm:

```java
public record CreateOrderCommand(
    String tenantId,
    String checkoutIntentId,
    List<OrderLine> items
) {}

public record OrderResult(
    String orderId,
    String status
) {}
```

Service logic giả định:

```java
@Service
public class OrderApplicationService {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;

    @Transactional
    public OrderResult createOrder(
            CreateOrderCommand command,
            String key) {

        String fingerprint = fingerprint(command);

        // Claim phải dựa vào UNIQUE constraint trong DB.
        // Nếu trùng key, transaction hiện tại không được tạo order mới.
        ClaimResult claim = idempotency.tryInsert(
            command.tenantId(),
            "CREATE_ORDER",
            key,
            fingerprint
        );

        if (claim == ClaimResult.DUPLICATE) {
            var previous = idempotency.find(
                command.tenantId(), "CREATE_ORDER", key);

            if (!previous.fingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException();
            }

            return previous.savedOrderResultOrPending();
        }

        Order order = Order.pending(
            command.tenantId(), command.items());

        orders.save(order);
        idempotency.complete(
            command.tenantId(),
            "CREATE_ORDER",
            key,
            order.id(),
            "PENDING"
        );

        return new OrderResult(order.id(), "PENDING");
    }
}
```

Đoạn code **không nhằm chạy nguyên văn**; interface `tryInsert`, `savedOrderResultOrPending`, `fingerprint` và xử lý unique conflict chỉ là abstraction. Một implementation thực phải lưu đầy đủ trạng thái, kiểm tra transaction isolation, giải quyết simultaneous requests, lỗi DB và business validation.

**Với domain write hoàn toàn trong một DB**, việc tạo order và ghi result idempotency trong **cùng transaction** giúp giảm cửa sổ mất liên hệ giữa key và resource. Nhưng nếu `orders.save()` gọi thêm một provider ngoài, local transaction không thể tự bảo đảm provider side effect.

### 18.1. Race condition tại lúc claim

Hai HTTP handlers cố insert cùng key. Unique constraint bảo đảm tối đa một row theo scope. Request thua phải xử lý duplicate sau khi transaction thắng commit/rollback. Không làm:

```java
if (idempotency.find(key).isEmpty()) {
    chargeProvider();   // race: hai request cùng đi tới đây
    idempotency.save(key);
}
```

Nếu dùng SQL `INSERT ... ON CONFLICT DO NOTHING` hoặc tương đương, cần kiểm tra row count và đọc lại state; DB dialect và isolation khác nhau có thể có semantics khác. Không đưa một mẫu SQL chung vào production mà chưa kiểm chứng.

## 19. Tách external side effect ra khỏi transaction ngắn

Đối với việc gọi provider ngoài, một flow an toàn hơn có thể là:

```text
POST /charges (K)
      |
      v
Claim K + create PaymentIntent trong DB
      |
      v
COMMIT local transaction
      |
      v
Worker gọi provider với providerKey ổn định
      |
      +--> accepted/confirmed: lưu result
      |
      +--> rejected definitive: lưu decline
      |
      '--> timeout/unknown: lưu UNKNOWN, reconcile
```

Thay vì giữ DB transaction mở qua HTTP call lâu, service lưu durable intent rồi xử lý async hoặc một bước đồng bộ ngắn có reconciliation.

Một số hệ thống có thể xử lý đồng bộ và trả response trực tiếp nếu provider nhanh; nhưng vẫn phải bảo đảm **sau crash có thể tìm lại intent và kết quả**, không chỉ dựa vào stack frame của request ban đầu.

### 19.1. Payment intent có ID ổn định

Ví dụ:

```json
{
  "paymentIntentId": "pi-8042",
  "idempotencyKey": "K",
  "orderId": "ord-8042",
  "amountMinor": 250000,
  "currency": "VND",
  "state": "PROCESSING",
  "providerKey": "merchant42:pi-8042"
}
```

Khi worker retry, nó dùng lại `providerKey`. Khi provider báo thành công nhưng response mất, hệ thống tra cứu theo provider reference để hoàn thành state. Không coi timeout là thất bại chắc chắn hoặc tạo intent thứ hai mù quáng.

## 20. Gateway không nên là lớp duy nhất giữ idempotency

Một Gateway/BFF có thể chuyển tiếp hoặc kiểm tra header key, giới hạn độ dài, gắn correlation và bảo vệ rate limit. Nhưng side effect thực sự nằm ở owner như Ordering, Payment hoặc Inventory. Nếu gateway restart, cache mất hoặc request đi qua gateway replica khác, service vẫn phải tránh trùng.

Một kiến trúc phân lớp:

```text
Client:
  giữ key ổn định theo intent
      |
Gateway:
  validate header, auth, rate limit, propagate
      |
Owner service:
  durable idempotency + business invariant
      |
Provider/external service:
  own idempotency key / reference / reconciliation
```

Không mặc định gateway có thể ngăn trùng chỉ bằng request cache. Và không cho client tự chọn tenant scope mà không kiểm tra: scope phải dựa trên danh tính đã xác thực hoặc quan hệ resource được owner xác nhận.

## 21. Retry, backoff, deadline và idempotency

**Idempotent** không có nghĩa nên retry vô hạn. Mỗi lần retry vẫn tốn tài nguyên, có thể làm gia tăng load, dẫn tới rate limiting hoặc chặn cả hệ thống.

Quy tắc thực tế:

1. Chỉ retry những lỗi được policy phân loại là transient.
2. Dùng deadline tổng; nếu không còn thời gian hữu ích thì ngừng.
3. Exponential backoff với jitter và retry budget.
4. Không cho nhiều tầng gateway/client/worker cùng retry không phối hợp.
5. Với operation đang xử lý, ưu tiên query status thay vì liên tục POST.
6. Giữ cùng idempotency key khi retry cùng intent.
7. Với unknown outcome ở provider, query/reconcile trước khi quyết định side effect mới.
8. Kiểm soát concurrency: cùng key đang IN_PROGRESS không được chạy nhiều attempts song song.
9. Khi business rejection đã được xác định, không retry mù nếu không có thay đổi intent.
10. Quan sát total attempts per intent và số duplicate suppressed.

Ví dụ: nếu ba tầng cùng thực hiện tối đa ba attempts, số lời gọi xuống đáy có thể tới `3 × 3 × 3 = 27` trong tình huống retries lồng nhau. Idempotency có thể giảm duplicate effect nhưng **không xóa lưu lượng khuếch đại**.

## 22. Khóa lặp an toàn khác optimistic locking

**Idempotency key** ngăn lặp lại **cùng một business intent**. **Optimistic concurrency/versioning** ngăn nhiều **intent khác nhau** ghi đè hoặc vi phạm invariant trên cùng resource.

Ví dụ hai user cùng cập nhật Order version 7:

```text
Intent A: đổi địa chỉ giao hàng
Intent B: hủy đơn
```

Nếu A và B dùng hai key khác nhau, cả hai không phải duplicate. Service vẫn phải bảo vệ state transition và version:

```sql
UPDATE orders
SET status = 'CANCELLED',
    version = version + 1
WHERE order_id = 'ord-8042'
  AND version = 7
  AND status IN ('PENDING', 'CONFIRMED');
```

Nếu số rows cập nhật bằng 0, không được âm thầm coi là thành công. Cần tải state và trả conflict/business result theo contract.

Một payment intent có key đúng vẫn có thể bị capture vượt hạn nếu các worker thực hiện **những intent khác nhau** đồng thời mà domain không bảo vệ tổng amount. Idempotency và concurrency control bổ sung nhau.

## 23. Khóa lặp an toàn không được làm mất khả năng tạo hành động mới hợp lệ

Những lỗi có thể xảy ra nếu scope quá rộng:

- Người dùng cố ý đặt **hai đơn giống nhau** nhưng key được tạo từ hash giỏ hàng → đơn thứ hai bị chặn.
- Một payment cho phép **nhiều partial refunds**, nhưng mọi refund dùng `paymentId:refund` → refund thứ hai hợp lệ bị bỏ.
- Một shipment cần nhiều kiện, nhưng key chỉ có `orderId:ship` → chỉ tạo một kiện.
- Notification gửi nhiều thông báo theo những thời điểm khác nhau, nhưng key chỉ có `customerId` → những thông báo sau bị mất.

Giải pháp là **định nghĩa chính xác business intent**. Ví dụ partial refund có `refundIntentId` riêng cho mỗi ý định hoàn, kết hợp business rule rằng tổng số tiền hoàn không vượt tiền đã thu.

Một intent mới phải có một key mới ngay cả khi nội dung payload gần giống. Key lặp không phải công cụ chống mọi hành vi được coi là “trùng” về mặt UX.

## 24. Khóa và dữ liệu nhạy cảm

Idempotency key nên là chuỗi định danh không chứa token, số thẻ, email hoặc dữ liệu nhạy cảm. Không xây khóa bằng:

```text
"customer-email:card-number:amount"
```

Vì key có thể xuất hiện trong HTTP headers, logs, tracing, Redis keyspace, metrics hoặc support tooling.

Các nguyên tắc:

- Key đủ khó đoán nếu client sinh ngẫu nhiên và không mang bí mật.
- Scope theo danh tính đã xác thực; không trả kết quả của tenant/user khác.
- Giới hạn độ dài/định dạng và số key hoạt động.
- Tránh đặt key raw vào metrics labels gây cardinality cao.
- Bảo vệ dữ liệu kết quả trong ledger, mã hóa khi cần, đặt retention thích hợp.
- Với một key đã được dùng, không cho phép thay payload mà lặng lẽ tạo side effect mới.
- Logs có thể ghi hash/truncated correlation được phê duyệt, không lưu dữ liệu thanh toán thô.

Key không phải authorization token. Người biết key của người khác không được nhận response tương ứng nếu không có quyền trên resource.

## 25. Migration và thay đổi phiên bản API

Khi API v1 và v2 cùng tồn tại, cần quyết định key có namespace theo API version hay theo **business operation**.

Ví dụ hai endpoint:

```text
POST /v1/payments
POST /v2/payments/authorizations
```

Nếu cả hai thực chất cùng tạo **một authorization intent**, chỉ tách scope theo URL version có thể tạo hai giao dịch nếu client retry sang endpoint mới với cùng key. Ngược lại, nếu v2 có semantic khác (ví dụ authorization vs capture), không nên gộp chúng vào một key namespace.

Cần quản lý:

- Phiên bản contract/operation type trong scope.
- Cách fingerprint được chuẩn hóa qua schema versions.
- Định danh intent ổn định khi client nâng API version.
- Legacy clients và batch retries.
- Tuổi của idempotency record so với cửa sổ migration.
- Chính sách khi một key đã xử lý với schema cũ được gọi bằng schema mới.

Nên có contract tests cho cùng key qua phiên bản được hỗ trợ. Không đặt việc chống lặp phụ thuộc vào class/field nội bộ có thể đổi tên mỗi release.

## 26. Quan sát: metrics nào chứng minh hệ thống đang chống lặp?

Một service có idempotency tốt không chỉ “chưa thấy double charge”. Nó cần quan sát tình trạng xử lý và các cửa sổ không chắc chắn.

| Nhóm metrics | Gợi ý theo dõi |
| --- | --- |
| Requests | Tỷ lệ yêu cầu có key, requests missing key, invalid key |
| Duplicate | Duplicate requests per intent, duplicate suppressed |
| Conflict | Same-key different-fingerprint counts |
| State | IN_PROGRESS age, COMPLETED, OUTCOME_UNKNOWN, RECONCILIATION |
| Latency | Thời gian claim key, xử lý intent, trả stored result |
| Storage | Ledger growth, TTL expiry, cleanup backlog |
| External provider | Timeout, query/reconcile attempts, duplicate provider response |
| Broker | Redeliveries, inbox dedup, outbox publish lag |
| Business effect | Số charge/order/refund/reservation tạo theo intent |
| Safety | Cross-tenant access denied, anomalous replays |
| Reliability | Crash recovery outcomes, stuck intents, reconciliation success |

Đừng gắn `idempotencyKey` trực tiếp làm metric label: cardinality bùng nổ. Có thể dùng request ID và business reference trong trace/log theo chính sách bảo mật.

### 26.1. Cảnh báo đáng quan tâm

- Một payment intent gắn với nhiều provider charges ngoài policy.
- Record IN_PROGRESS quá thời hạn xử lý tối đa.
- OUTCOME_UNKNOWN tăng liên tục.
- Cùng key xuất hiện với nhiều fingerprints.
- Compensation/refund được thực hiện nhiều lần cho cùng refund intent.
- Idempotency ledger cleanup sớm hơn retry window.
- Một service có key hợp lệ nhưng side effect vẫn bị lặp.

Các chỉ số phải gắn với **business outcome**, không chỉ HTTP 200/409.

## 27. Kiểm thử concurrency, crash và retry

Một happy-path test không chứng minh idempotency. Cần kiểm tra từng cửa sổ lỗi:

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Hai request cùng key tới đồng thời | Chỉ một business effect; request còn lại nhận pending/result |
| Ba request cùng key khác payload | Không thực hiện payload thứ hai; có conflict theo contract |
| Retry sau timeout nhưng DB commit xong | Trả cùng resource/result, không tạo thêm |
| Crash sau claim, trước domain write | Có recovery/expiry an toàn, không kẹt vô hạn |
| Crash sau domain commit, trước HTTP response | Key/result bền vững và retry trả đúng |
| Crash sau provider charge, trước lưu local result | Query/reconcile bằng provider key, không charge trùng |
| Redis lease hết hạn khi worker cũ còn chạy | Không có hai worker cùng tạo side effect |
| Event nhận hai lần với cùng message ID | Inbox chống duplicate |
| Cùng business intent qua hai message IDs | Business key chống effect lặp |
| Compensation nhận hai lần | Stock/refund không tăng hai lần |
| Event cũ đến sau event mới | State machine/versions chặn transition sai |
| Retry sau key TTL | Có policy business uniqueness hoặc kết quả rõ |
| Hai tenants dùng cùng chuỗi key | Không chia sẻ result hoặc khóa lẫn nhau |
| Client đổi API version giữa retries | Không tạo hai effects nếu cùng intent |
| Client gửi key giống nhau cho hai intent hợp lệ | Báo conflict thay vì lặng lẽ gộp |

### 27.1. Gherkin ví dụ

```gherkin
Given payment intent pi-8042 chưa có authorization
When hai request đồng thời cùng Idempotency-Key K được gửi
Then tối đa một authorization được tạo tại provider
  And cả hai request liên hệ cùng payment intent
  And hệ thống không trả kết quả của một tenant khác
```

```gherkin
Given payment intent pi-8042 đã được provider capture
  And server mất kết nối trước khi lưu kết quả
When client retry với cùng key K
Then service đối soát theo provider reference hoặc provider key
  And không capture lần thứ hai
  And trả hoặc công bố trạng thái phù hợp với kết quả đã xác minh
```

```gherkin
Given inventory reservation res-8042 đang ACTIVE
When hai message ReleaseReservation cùng business key đến
Then reservation chuyển ACTIVE -> RELEASED một lần
  And số lượng stock chỉ được hoàn lại một lần
```

Kiểm thử cần quan sát database state, provider sandbox/record và số side effects, không chỉ số lần mock method được gọi. Với concurrency, chạy nhiều threads/processes và thật sự tạo race thay vì tuần tự hóa request trong unit test.

## 28. Phân tích một lỗi thực tế giả định

Hệ thống Payment có flow:

```text
POST /charges:
  if redis.has(K): return cached
  provider.charge(card, amount)
  redis.put(K, result, ttl=5min)
  return result
```

Một đợt retry mạng xảy ra khi:

1. Worker A thấy K chưa có.
2. Worker B cũng thấy K chưa có.
3. Cả hai gọi provider trước khi có result cache.
4. Provider tạo hai charges.
5. Hai kết quả được ghi đè vào cùng cache key.

Vấn đề:

- `has` rồi `put` không atomic claim.
- Cache được ghi **sau** side effect.
- Không có provider idempotency key.
- Không có transaction/idempotency ledger bền vững.
- Không có unique business intent và reconciliation.
- TTL 5 phút có thể ngắn hơn retry window.

Một phương án thiết kế lại:

```text
Client -> PaymentService
            |
            +--> Validate auth, scope, intent
            +--> Atomic durable claim K with fingerprint
            +--> Return prior result/pending if duplicate
            +--> Persist payment intent & provider key
            +--> Call provider with same stable provider key
            +--> Persist authoritative result or UNKNOWN
            +--> Retry/reconcile when outcome uncertain
            '--> Return result/status + operation reference
```

Ngay cả thiết kế mới vẫn cần bảo đảm provider có khả năng dedup/lookup hoặc đường khắc phục khi provider không cung cấp. Không có một câu lệnh `SET NX` nào có thể tự biến hai hệ thống độc lập thành transaction atomic toàn cục.

## 29. Những ngộ nhận dễ gây tác dụng phụ trùng

1. **“POST luôn tạo resource mới.”** Có thể thiết kế POST idempotent theo business key.
2. **“Có Idempotency-Key header là đã an toàn.”** Không đủ nếu server không lưu và kiểm tra một cách atomic.
3. **“Timeout nghĩa là request chưa được thực hiện.”** Sai; server hoặc provider có thể đã commit.
4. **“Mỗi retry nên có request ID mới nên key cũng phải mới.”** Request ID và idempotency key khác nhau.
5. **“Hash payload là khóa đủ tốt.”** Hai intent hợp lệ có thể có payload giống nhau.
6. **“Cùng key khác payload cứ thực hiện tiếp.”** Phải chặn conflict hoặc có contract rõ.
7. **“Dedup theo messageId là đủ.”** Một intent có thể đến qua hai message IDs.
8. **“Unique constraint đặt sau charge sẽ ngăn double charge.”** Quá muộn nếu side effect ngoài đã xảy ra.
9. **“Redis TTL 5 phút đảm bảo không bao giờ lặp.”** Lease hết hạn/cache mất có thể làm request chạy lại.
10. **“Broker exactly-once là payment exactly-once.”** Broker không điều khiển mọi side effects bên ngoài.
11. **“Cùng key có thể được dùng cho mọi refund của một payment.”** Có thể gộp nhầm partial refunds hợp lệ.
12. **“Thành công rồi thì có thể xóa idempotency record ngay.”** Retry muộn có thể tạo tác dụng phụ thứ hai.
13. **“Lỗi 500 lúc nào cũng nên cache hoặc lúc nào cũng phải retry.”** Phải dựa vào vị trí lỗi và trạng thái side effect.
14. **“Gateway dedup là đủ, downstream không cần kiểm tra.”** Side effect owner phải bảo vệ dữ liệu của mình.
15. **“Mọi duplicate đều là hành vi xấu.”** Retry cùng intent là hợp lệ; cần phản hồi nhất quán.
16. **“Key có thể thay authorization.”** Không; scope và quyền phải được kiểm tra riêng.
17. **“Một key hợp lệ thay thế optimistic locking.”** Không; nhiều intent khác nhau vẫn có thể gây race.
18. **“Idempotency cho phép retry vô hạn.”** Retry vẫn tiêu tốn tài nguyên và gây quá tải.
19. **“Compensation không cần idempotency.”** Refund/release lặp là lỗi nghiệp vụ nghiêm trọng.
20. **“Chỉ cần so HTTP response, không cần kiểm tra DB/provider.”** Sự cố thường nằm ở side effect âm thầm.

## 30. Quy trình thiết kế idempotency cho một operation mới

**Bước 1 — Đặt tên business intent.** Ví dụ “ủy quyền thanh toán cho paymentIntent pi-8042”, không phải “HTTP request thứ 17”.

**Bước 2 — Liệt kê side effects.** Database records, stock changes, provider payment, email, shipment, external API.

**Bước 3 — Chọn scope và key.** Tenant/account, operation type, business resource; client tạo key hay server tạo? Key giữ ổn định qua những lần retry nào?

**Bước 4 — Định nghĩa payload equivalence.** Fingerprint dựa trên các thuộc tính nào; same-key different-payload xử lý ra sao?

**Bước 5 — Thiết kế atomic claim.** Unique constraint, transaction và guarded state transition theo database owner.

**Bước 6 — Định nghĩa trạng thái.** IN_PROGRESS, COMPLETED, REJECTED, UNKNOWN, reconciliation; cách duplicate requests nhận phản hồi.

**Bước 7 — Nếu có provider ngoài, dùng stable provider key.** Đọc kỹ chính sách, retention và khả năng truy vấn trạng thái của provider.

**Bước 8 — Thiết kế recovery.** Crash windows, timeout sau commit, stale leases, retry muộn và đồng thời nhiều workers.

**Bước 9 — Định nghĩa retention.** Bao gồm client retries, broker replay, batch delays, accounting và bảo mật dữ liệu.

**Bước 10 — Kiểm soát retry.** Deadline, backoff, jitter, retry budget và tránh retries chồng tầng.

**Bước 11 — Kiểm thử.** Đồng thời hai requests, duplicate messages, crash sau side effect, same-key different-payload, key TTL và cross-tenant safety.

**Bước 12 — Quan sát production.** Duplicate suppressed, pending/unknown age, reconciliation, provider double effects và manual interventions.

### 30.1. Checklist ngắn trước khi phát hành

| Câu hỏi | Tiêu chí hoàn tất |
| --- | --- |
| Key đại diện đúng một business intent? | Có định nghĩa rõ ràng |
| Cùng intent retry có giữ cùng key? | Có |
| Scope khóa ngăn cross-tenant collision/leak? | Có |
| Same-key khác payload có bị chặn? | Có fingerprint/validation |
| Concurrent same-key có thể chạy hai effects? | Không, có atomic claim/constraint |
| Result được lưu cùng domain state khi có thể? | Có transaction phù hợp |
| Provider ngoài có key/lookup/reconciliation? | Có chính sách rõ |
| Timeout có trạng thái UNKNOWN hợp lệ? | Có |
| Compensation có idempotency riêng? | Có |
| Retention dài hơn cửa sổ replay cần bảo vệ? | Có |
| Response khi IN_PROGRESS/COMPLETED có contract? | Có |
| Retry có deadline/backoff/budget? | Có |
| Có metrics và alert cho duplicate effects? | Có |
| Có test crash/concurrency, không chỉ happy path? | Có |

## 31. Bài tập tình huống

### Bài tập A — Tạo đơn khi mobile app mất mạng

Mobile app gửi `POST /orders` với key K. Server tạo Order ORD-91 và commit, nhưng mobile không nhận response. App restart và gửi lại.

1. K nên được lưu ở đâu trong ứng dụng để tồn tại qua app restart?
2. Server dùng bảng nào để liên hệ K với ORD-91?
3. Nếu app gửi lại cùng K nhưng giỏ hàng đã đổi, server phải làm gì?
4. Nếu app cố tình tạo đơn thứ hai giống hệt, cần key mới hay dùng K?
5. Nếu K hết hạn trước khi app retry, còn business key nào có thể chống tạo đơn trùng?

### Bài tập B — Payment provider không hỗ trợ exactly-once end-to-end

PaymentService gửi charge tới provider, provider thành công nhưng response bị mất. Local ledger đang IN_PROGRESS.

1. Vì sao không thể coi transaction local rollback là charge đã được hoàn?
2. Cần payment intent, provider key và provider reference thế nào?
3. Khi provider chỉ cho query bằng reference mà reference chưa nhận được, có thể cần biện pháp đối soát nào?
4. Nếu provider không hỗ trợ idempotency cũng không hỗ trợ lookup, hệ thống có thể cam kết “không bao giờ double charge” hay không?
5. Khi chưa rõ kết quả, client nên thấy trạng thái nào?

### Bài tập C — Refund hai lần

Một khách hàng được phép partial refund hai lần, mỗi lần 100.000 VND cho cùng Payment.

1. Nếu dùng `paymentId:refund` làm key, lỗi gì xảy ra?
2. Nếu dùng key khác cho từng refund intent nhưng gửi cùng intent hai lần, cần chống lặp thế nào?
3. Làm sao bảo vệ tổng tiền refund không vượt số tiền đã thu, kể cả hai refund chạy song song?
4. Compensation refund bị timeout thì Saga cần trạng thái nào?
5. Nếu provider nhận hai API calls với cùng provider key, hợp đồng provider phải bảo đảm điều gì?

### Bài tập D — Event duplicate ở Inventory

Hai message khác `messageId` cùng yêu cầu giữ hàng cho cùng `orderId` và cùng business intent. Handler chỉ dedup theo message ID.

1. Hậu quả nào có thể xuất hiện?
2. Business idempotency key nên được đặt theo reservation intent thế nào?
3. Unique constraint hoặc conditional update nào giúp giữ stock một lần?
4. Nếu key giống nhưng payload quantity khác, nên xử lý ra sao?
5. Khi ReleaseReservation bị giao lại, làm sao đảm bảo không cộng stock lần hai?

**Hướng suy luận:** luôn xuất phát từ ý định nghiệp vụ, phân biệt retries với hành động mới hợp lệ, rồi áp dụng atomic claim tại owner, key ổn định, authoritative state, provider support và reconciliation. Chỉ nhìn vào HTTP header hoặc message ID sẽ không đủ.

## 32. Ghi nhớ

- **Khóa lặp an toàn định danh một ý định nghiệp vụ**, không phải một lần thử request.
- **Cùng intent → cùng key; intent mới → key mới.** Payload giống nhau không chứng minh cùng intent.
- **Scope, fingerprint và business ownership** là một phần của hợp đồng; phải chặn same-key khác nội dung và cross-tenant leakage.
- **Atomic claim/unique constraint** ngăn hai worker đồng thời cùng thực hiện một local side effect.
- **Lưu trạng thái và kết quả bền vững** giúp retry sau timeout/crash nhận đúng resource đã tạo.
- **IN_PROGRESS và OUTCOME_UNKNOWN là trạng thái khác nhau**; timeout không chứng minh bước chưa commit.
- **External provider không nằm trong local transaction**. Cần stable provider key, query/reconciliation và chính sách unknown outcome.
- **Outbox/inbox, message dedup và business idempotency** phối hợp nhau nhưng không thay thế lẫn nhau.
- **Compensation cũng phải idempotent**; release/refund lặp có thể nguy hiểm không kém tạo mới lặp.
- **TTL và lưu trữ phải theo cửa sổ retry/replay**, không chọn một thời hạn tùy tiện.
- **Idempotency khác optimistic concurrency**: một cái chống lặp cùng ý định, cái kia bảo vệ bất biến giữa nhiều ý định.
- **Retries phải có deadline và ngân sách**, không được khuếch đại tải hoặc thực hiện side effect mới khi chưa rõ kết quả.

**Thông điệp cuối:** Trong hệ phân tán, câu “tôi không nhận được phản hồi” khác hoàn toàn với “hệ thống chưa thực hiện yêu cầu”. Một idempotency key được thiết kế đúng biến các lần thử lại thành việc **tra cứu hoặc hoàn tất cùng một business intent**, thay vì tạo ra những tác dụng phụ mới không mong muốn.
