# Lưu kết quả và xử lý nhiều yêu cầu trùng đến đồng thời trong Microservices

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Đồng thời và lặp an toàn.
>
> **Mục tiêu:** thiết kế idempotency khi hai hay nhiều request có cùng ý định đến **đồng thời**, trên các pods khác nhau hoặc sau retry; claim quyền xử lý nguyên tử, lưu trạng thái/kết quả, trả kết quả đã ghi nhận, bảo vệ các tác động nghiệp vụ, xử lý timeout, crash, lease hết hạn, message redelivery và side effect ở dịch vụ bên ngoài.

## 1. Tình huống cần giải quyết

Khách hàng nhấn thanh toán và request đến Payment Service. Thiết bị hoặc gateway không nhận phản hồi nên gửi lại trước khi lần đầu kết thúc:

```text
Mobile / Gateway
       |
       +---- POST payment(K) ----> Payment Pod A
       |                           | charge đang chạy
       |
       +---- POST payment(K) ----> Payment Pod B
                                   | charge cũng chạy?
                                   v
                             External Gateway

Nếu A và B cùng đọc "chưa có kết quả", hai payments có thể được tạo.
```

Một cache lưu kết quả **sau** khi giao dịch hoàn tất không giải quyết được cuộc đua trước lúc kết quả xuất hiện. Một mutex trong Pod A không bảo vệ Pod B. Một khóa Redis có TTL hết sớm cũng không đảm bảo worker trước đã dừng.

Cần hai lớp bảo đảm bổ sung nhau:

1. **Atomic claim:** chỉ một request/worker giành được quyền bắt đầu cùng một ý định nghiệp vụ, dùng unique constraint, conditional insert hoặc compare-and-set đáng tin cậy.
2. **Durable outcome:** lưu kết quả hoặc operation ID và trạng thái để các lần gọi trùng biết request đang xử lý, đã hoàn tất hay chưa chắc chắn, thay vì khởi tạo side effect mới.

**Điểm cốt lõi:** chống lặp đồng thời phải được bảo vệ **trước side effect**; lưu kết quả để replay phải được gắn với việc commit business state.

## 2. Định nghĩa idempotency có phạm vi

Một operation idempotent nếu lặp lại **cùng business intent** không làm phát sinh thêm tác động nghiệp vụ. Về trực giác:

\[
f(f(s)) = f(s)
\]

Trong API, cần định nghĩa rõ: cùng key, cùng authenticated scope, cùng operation type, cùng payload có nghĩa, trong cửa sổ hỗ trợ.

Ví dụ:

- CreateOrder cùng key tạo một Order.
- CapturePayment cùng key chỉ thu tiền một lần.
- ReleaseReservation cùng reservationId không tăng tồn hai lần.
- RefundCapture cùng refundId không hoàn tiền hai lần.
- PaymentCaptured event giao trùng không cộng doanh thu lần hai cho cùng một consumer.

Không nhất thiết mọi response HTTP phải trùng byte, vì timestamps hoặc request tracing khác nhau. Nhưng **business effect** phải nằm trong phạm vi cam kết.

### 2.1. Request ID không phải idempotency key

Request ID nhận diện một lần HTTP attempt; retry thường có request ID mới. Idempotency key phải giữ nguyên trong mọi attempt của cùng ý định:

```text
Attempt 1:
    X-Request-ID: req-1001
    Idempotency-Key: charge-order-729-v1

Attempt 2:
    X-Request-ID: req-1002
    Idempotency-Key: charge-order-729-v1
```

Tạo key mới cho mỗi retry sẽ biến một ý định thành nhiều ý định độc lập.

### 2.2. Key phải có phạm vi rõ

Một unique business key nên xét những thành phần:

```text
(tenantId, authenticatedScope, operationType, idempotencyKey)
```

Cùng key K ở hai tenants khác nhau không được phép làm lộ kết quả. Cùng K ở CreateOrder và RefundOrder không nên vô tình xung đột nếu chúng là các operation khác loại.

Luôn xác thực/ủy quyền trước khi đọc hoặc replay outcome; không lấy tenantId tùy ý từ body làm nguồn tin duy nhất.

## 3. Phân biệt trùng theo HTTP với trùng theo nghiệp vụ

Hai requests có thể có idempotency keys khác nhau nhưng vẫn cùng **business intent** do client bị lỗi. Ngược lại, hai intents thanh toán hợp lệ có thể cùng amount và currency nhưng không phải trùng.

Cần lựa chọn key phù hợp, ví dụ:

- Client-generated stable UUID cho một lần checkout cụ thể.
- Merchant order ID hoặc payment intent ID do server cấp.
- Refund intent ID gắn với capture và một yêu cầu hoàn cụ thể.
- Reservation ID gắn với order/line và phiên giữ hàng cụ thể.

Idempotency key **không thay thế business uniqueness**. Nếu hai refund intents K1 và K2 cùng refund một capture, Payment còn phải kiểm soát tổng refundable amount và quyền thực hiện. Nếu client tạo hai keys cho một order submission, ràng buộc unique externalOrderId có thể là lớp bảo vệ bổ sung.

## 4. Bốn tình huống cơ bản của duplicate requests

| Trạng thái key | Hành vi của server |
| --- | --- |
| Chưa có | Atomic claim và bắt đầu một operation |
| IN_PROGRESS | Không chạy lại; bounded wait, 202 hoặc lỗi in-progress theo contract |
| COMPLETED | Replay saved outcome/cùng resource ID mà không tạo effect mới |
| UNKNOWN/NEEDS_RECONCILIATION | Tra cứu owner/provider theo original operation reference |

Ngoài ra có thể có FAILED_TERMINAL khi một business rejection đã chắc chắn và đúng policy không nên được thực thi lại theo key đó.

### 4.1. Concurrent duplicate

Hai requests đến trong cùng mili giây, cùng thấy dữ liệu chưa tồn tại nếu chỉ dùng SELECT. **Chính unique index/atomic insert** quyết định request được claim, không phải điều kiện IF ở application.

### 4.2. Duplicate trong khi xử lý

Có thể chọn:

- Chờ ngắn một khoảng bounded, rồi replay nếu lần đầu hoàn tất.
- Trả HTTP 202 kèm operationId và status URL.
- Trả HTTP 409 với error code OPERATION_IN_PROGRESS và Retry-After nếu contract phù hợp.

Không giữ hàng nghìn threads chờ vô hạn; không trả trạng thái FAILED chỉ vì một operation đang chạy.

### 4.3. Duplicate sau khi hoàn tất

Kết quả replay có thể là HTTP status/body của lần đầu, hoặc một logical outcome, hoặc trạng thái resource hiện tại. Cần nêu rõ trong API contract. Nếu Payment ban đầu AUTHORIZED nhưng giờ CAPTURED, một API trả current status khác một API replay kết quả ban đầu.

## 5. Same key nhưng khác payload phải bị phát hiện

Ví dụ key K dùng charge 100.000 VND lần đầu; lần hai lại dùng K để charge 500.000 VND. Trả response lần đầu cho request thứ hai là sai semantics.

Server nên lưu **request fingerprint**:

```text
Key K + CreatePayment(order=O1, amount=100000, currency=VND)
  fingerprint = H1

Key K + CreatePayment(order=O1, amount=500000, currency=VND)
  fingerprint = H2

H1 != H2 => KEY_REUSED_WITH_DIFFERENT_PAYLOAD
Không thực hiện payment mới.
```

Fingerprint phải dựa trên những trường quan trọng: authenticated merchant, operation type, order ID, amount, currency, recipient và business terms. Loại bỏ metadata biến động như tracing ID nhưng **không bỏ trường ảnh hưởng tác động nghiệp vụ**.

### 5.1. Canonicalization

Hai JSON bodies có thể chỉ khác thứ tự keys. Có thể tạo canonical encoding rồi dùng SHA-256 hoặc HMAC thích hợp; có version nếu thuật toán thay đổi. Tiền nên có representation chính xác (minor units/decimal contract) thay vì floating-point mơ hồ. Đồng nhất cách hiểu null, absent, Unicode normalization và timezone.

Không để hai phiên bản server trong rolling deployment tính hash khác nhau cho cùng ý định rồi trả conflict giả hoặc xử lý trùng.

## 6. Lược đồ lưu trạng thái và kết quả

Ví dụ PostgreSQL:

```sql
CREATE TABLE idempotency_operations (
    tenant_id        VARCHAR(100) NOT NULL,
    operation_type   VARCHAR(100) NOT NULL,
    idempotency_key  VARCHAR(200) NOT NULL,
    request_hash     CHAR(64) NOT NULL,
    state            VARCHAR(40) NOT NULL,
    business_id      VARCHAR(160),
    response_status  INTEGER,
    response_body    JSONB,
    lease_token      BIGINT NOT NULL DEFAULT 0,
    lease_until      TIMESTAMPTZ,
    last_error_code  VARCHAR(120),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ,
    PRIMARY KEY(tenant_id, operation_type, idempotency_key),
    CONSTRAINT valid_idem_state CHECK (state IN (
        'IN_PROGRESS',
        'COMPLETED',
        'FAILED_TERMINAL',
        'UNKNOWN',
        'NEEDS_RECONCILIATION'
    ))
);

CREATE INDEX idx_idem_recovery
ON idempotency_operations(state, lease_until);
```

Schema này mang tính minh họa. Production phải xem indexing, encryption, table partitioning, response size limit, retention, quyền truy cập và migration. Có thể lưu resource ID/logical outcome thay vì raw response body, đặc biệt khi có PII.

### 6.1. Các trường có ý nghĩa gì?

- tenant + operation + key: định danh intent trong phạm vi có thẩm quyền.
- request_hash: bảo đảm key không bị dùng cho payload khác.
- state: chỉ ra operation đang chạy, terminal hay chưa rõ.
- business_id: trỏ đến resource/operation đã tạo.
- response_status/body: cho phép replay nếu contract cần.
- lease_token/until: phục hồi và chống worker stale.
- timestamps/expiry: vận hành, monitoring và retention.
- last_error_code: phân biệt business rejection với lỗi kỹ thuật.

Không coi response cache là nơi lưu password, bearer token, PAN hoặc nội dung nhạy cảm không cần thiết.

## 7. Atomic claim bằng unique constraint

Không dùng logic sau:

```text
SELECT key K -> not found
CREATE payment
INSERT key K
```

Khi request A và B cùng SELECT trước khi một request INSERT, cả hai có thể thực hiện payment. Unique constraint ở cuối chỉ chặn hai rows kết quả; **không đảo ngược hai external payments đã xảy ra**.

Hãy claim trước:

```sql
INSERT INTO idempotency_operations (
    tenant_id, operation_type, idempotency_key,
    request_hash, state
)
VALUES (
    :tenant, :operation, :key,
    :hash, 'IN_PROGRESS'
)
ON CONFLICT DO NOTHING
RETURNING idempotency_key;
```

Nếu INSERT trả một row, request này giành claim. Nếu không, đọc record đã tồn tại và không thực hiện business effect mới. Khi có hai transactions cạnh tranh cùng unique key, database có thể buộc một transaction đợi kết quả commit/rollback của transaction kia.

### 7.1. Các bước của nhánh conflict

1. Đọc row theo đúng tenant/operation/key.
2. Xác minh auth scope.
3. So sánh hash.
4. Nếu khác, trả KEY_CONFLICT.
5. Nếu COMPLETED, replay saved outcome.
6. Nếu IN_PROGRESS, chờ có giới hạn hoặc trả PENDING.
7. Nếu UNKNOWN, trả operation ID để query/reconcile.

Không dùng SELECT riêng lẻ thay cho atomic claim, và không giữ lock database lâu chỉ để request B chờ gateway.

## 8. Local transaction: cùng commit business effect và outcome

Với một operation ngắn chỉ sửa **một local database**, có thể dùng chung transaction:

```text
BEGIN

1. Claim idempotency key K (unique).
2. Chỉ khi claim thành công: INSERT Order O-729.
3. UPDATE idempotency K:
      state = COMPLETED
      business_id = O-729
      response_status = 201
      response_body = outcome
4. COMMIT

HTTP response gửi sau COMMIT.
```

Nếu transaction rollback trước commit, Order và result đều rollback; request khác có thể claim. Nếu commit thành công nhưng response HTTP mất, retry cùng K đọc lại outcome đã lưu, không tạo Order mới.

Một đoạn SQL minh họa:

```sql
BEGIN;

INSERT INTO idempotency_operations (
    tenant_id, operation_type, idempotency_key,
    request_hash, state
)
VALUES (
    :tenant, 'CREATE_ORDER', :key,
    :hash, 'IN_PROGRESS'
)
ON CONFLICT DO NOTHING
RETURNING idempotency_key;

-- Chỉ chạy nhánh tiếp theo khi đã claim được.
INSERT INTO orders(order_id, customer_id, status)
VALUES (:order_id, :customer_id, 'PENDING');

UPDATE idempotency_operations
SET state = 'COMPLETED',
    business_id = :order_id,
    response_status = 201,
    response_body = :response_json,
    updated_at = NOW()
WHERE tenant_id = :tenant
  AND operation_type = 'CREATE_ORDER'
  AND idempotency_key = :key
  AND state = 'IN_PROGRESS';

COMMIT;
```

Đây là mô tả logic, chưa phải stored procedure xử lý mọi nhánh. Code phải kiểm tra INSERT RETURNING, rollback/cancel nhánh conflict, số rows cập nhật và ngoại lệ. Có thể thêm outbox event trong cùng transaction để OrderCreated được publish tin cậy.

**Không gửi HTTP request đến Payment Gateway trong transaction trên chỉ để giữ row lock.** Một external call có thể treo nhiều giây và làm cạn DB connections.

## 9. Long-running operation: durable claim + outbox

Khi business side effect ở hệ bên ngoài, cần một mô hình khác:

```text
Payment API local transaction:
  INSERT idempotency K = IN_PROGRESS
  INSERT PaymentOperation(op-729, PENDING)
  INSERT outbox command ProcessPayment(op-729)
COMMIT

Worker:
  receive ProcessPayment (có thể trùng)
  kiểm tra state và quyền thực thi
  gọi Payment Gateway bằng downstream key ổn định
  ghi outcome hoặc UNKNOWN vào local DB

Retry API cùng K:
  không tạo payment thứ hai
  trả cùng operation ID hoặc saved outcome
```

Claim và outbox phải nằm trong cùng local transaction hoặc có recovery scanner xử lý cửa sổ sau claim trước enqueue. Nếu chỉ tạo row IN_PROGRESS rồi crash trước khi gửi work, operation có thể bị kẹt mãi.

Outbox giúp không làm mất intent, nhưng dispatcher có thể publish trùng. Worker phải idempotent. External gateway cũng cần idempotency key/status query phù hợp. Không được mặc định một message broker khiến toàn bộ side effects thành exactly-once.

## 10. State machine của operation

```text
        Claim K
          |
          v
     IN_PROGRESS
       |    |    \
       |    |     +-- remote outcome uncertain --> UNKNOWN
       |    |                                       |
       |    v                                       v
       |  FAILED_TERMINAL                      RECONCILIATION
       |                                            |
       v                                  +---------+---------+
    COMPLETED                             |                   |
                                       COMPLETED        MANUAL_REVIEW
```

FAILED_TERMINAL là một business outcome có bằng chứng, không phải bất kỳ HTTP 500 nào. UNKNOWN nghĩa là request có thể đã tới external provider và commit, nhưng local service thiếu kết quả.

### 10.1. Không lưu mọi lỗi 500 thành terminal result

Có thể phân loại:

| Tình huống | Hướng xử lý |
| --- | --- |
| Validation từ chối trước side effect | Không claim hoặc lưu terminal theo contract |
| Business rule xác nhận từ chối | Có thể lưu FAILED_TERMINAL |
| Local DB commit thành công, response serialization lỗi | Vẫn có COMPLETED và outcome bền vững |
| Lỗi network trước khi gọi provider | Có thể retry cùng intent theo policy |
| Timeout sau khi đã gửi provider | UNKNOWN, query/reconcile |
| Provider trả ACCEPTED/PENDING | Lưu operation ID và tiếp tục theo dõi |
| Provider confirm success | Lưu COMPLETED và business reference |

Một transient 500 không phải lúc nào cũng là outcome cuối. Ngược lại, bỏ qua mọi 500 rồi chạy lại payment với key mới rất nguy hiểm.

## 11. Lưu kết quả để replay: ba lựa chọn

### 11.1. HTTP status và response body

Ví dụ lưu:

```json
{
  "state": "COMPLETED",
  "responseStatus": 201,
  "responseBody": {
    "paymentId": "pay-729",
    "status": "AUTHORIZED",
    "amount": "150000",
    "currency": "VND"
  }
}
```

Request trùng nhận cùng status/body theo contract. Nhưng phải xem loại headers nào được replay; không lưu Set-Cookie, token, trace metadata hay các trường có tính thời điểm một cách mù quáng.

### 11.2. Business resource ID

Lưu paymentId và lấy current payment state khi replay. Ít dữ liệu lưu hơn, nhưng response lần hai có thể là CAPTURED thay vì AUTHORIZED ban đầu. Contract phải nêu rõ đây là **trạng thái hiện tại**, không phải replay snapshot lần đầu.

### 11.3. Logical outcome

Lưu paymentId, initialDecision, amount, currency, schemaVersion và lý do. Từ đó dựng lại response logic ổn định. Phù hợp khi muốn tránh raw HTTP body nhưng vẫn cần cam kết về kết quả ban đầu.

Không có lựa chọn đúng cho mọi use case. Quyết định dựa trên API semantics, dữ liệu nhạy cảm, response size và retention.

## 12. HTTP status khi requests trùng

Một contract tham khảo:

| Trường hợp | HTTP status có thể chọn |
| --- | --- |
| Lần đầu tạo resource | 201 Created |
| Retry cùng key, đã hoàn tất | 201/200 cùng outcome theo contract |
| Đang xử lý bất đồng bộ | 202 Accepted và operation status URL |
| Duplicate in-progress không chờ | 409 Conflict với mã IN_PROGRESS |
| Cùng key, payload khác | 409 hoặc 422 với mã KEY_REUSED |
| Rate limit trước khi nhận intent | 429 Too Many Requests |
| Remote outcome chưa rõ | 202/response có trạng thái UNKNOWN và hướng đối soát |
| Terminal business reject | 4xx có mã nghiệp vụ phù hợp |

Không phải mọi API đều phải dùng đúng bảng mã này; điều quan trọng là client phân biệt **chưa hoàn tất**, **đã thất bại thật** và **same key different payload**.

Ví dụ operation đang chạy:

```http
HTTP/1.1 202 Accepted
Location: /v1/operations/op-729
Retry-After: 2
Content-Type: application/json

{
  "operationId": "op-729",
  "state": "IN_PROGRESS"
}
```

Status endpoint phải có auth và authorization, không để ai biết operation ID cũng đọc được kết quả người khác. Retry-After là hướng dẫn thử lại, không phải cam kết sẽ xong sau hai giây.

## 13. Lựa chọn chờ hoặc trả kết quả ngay

Nếu request thường hoàn tất trong 30 ms, request trùng có thể chờ tối đa 100 ms để lấy kết quả thay vì trả 202. Nhưng phải hạn chế số waiters.

Nếu payment gateway mất 30 giây hoặc refund có thể xử lý hàng giờ, không nên để nhiều HTTP connections/threads chờ cùng một key. Trả operation ID và cung cấp cơ chế poll/notification có rate limit.

Một số ứng dụng dùng local single-flight: nhiều request trong cùng process dùng chung Future để chờ một computation. Đây là tối ưu latency/resource, **không thay thế durable claim** xuyên pods và restart.

## 14. Lease, worker crash và recovery

Worker có thể crash sau khi claim K. Nếu state IN_PROGRESS tồn tại mãi, mọi retries đều bị kẹt. Cần lease hoặc recovery theo operation state, nhưng không được hiểu lease hết là business chưa xảy ra.

Một phương án lấy lease nguyên tử:

```sql
UPDATE idempotency_operations
SET lease_token = lease_token + 1,
    lease_until = NOW() + INTERVAL '30 seconds',
    updated_at = NOW()
WHERE tenant_id = :tenant
  AND operation_type = :type
  AND idempotency_key = :key
  AND state = 'IN_PROGRESS'
  AND (lease_until IS NULL OR lease_until < NOW())
RETURNING lease_token;
```

Token giúp worker A cũ không ghi đè local outcome sau khi worker B đã takeover. Tuy vậy A có thể đã gửi charge đến gateway; fencing trong local DB không ngăn external provider nhận lệnh trễ. Cần idempotency tại provider và query operation state.

### 14.1. Recovery scanner

Một background job có thể tìm những IN_PROGRESS hoặc UNKNOWN quá tuổi, phân bổ worker mới, kiểm tra trạng thái downstream, tiếp tục với **cùng original operation ID/key** và cập nhật kết quả có version guard.

Không xóa record rồi tạo intent mới; không retry với provider key mới. Recovery nên có rate limit, backoff và manual escalation nếu không đối soát được.

## 15. Payment: response mất sau commit

Timeline:

```text
T1: Payment Pod A nhận charge K, lưu IN_PROGRESS.
T2: A gọi Gateway với providerKey=P-729.
T3: Gateway charge thành công và commit.
T4: Response của Gateway mất.
T5: A ghi UNKNOWN hoặc crash.
T6: Pod B nhận retry của client với K.
T7: B thấy cùng operation, KHÔNG tạo charge mới.
T8: Recovery query Gateway bằng P-729/merchant reference.
T9: Gateway xác nhận charge.
T10: Payment lưu COMPLETED + gateway transaction ID.
T11: Retry tiếp theo trả cùng payment result.
```

**Timeout là tín hiệu truyền thông, không chứng minh business transaction thất bại.**

Downstream idempotency key phải được giữ nguyên qua retry và được lưu bền vững. Nếu provider chỉ hỗ trợ idempotency trong một cửa sổ hữu hạn, service cần status API, merchant reference hoặc reconciliation khi quá cửa sổ ấy.

### 15.1. Hai lớp bảo vệ

- Local idempotency record chặn việc tạo nhiều Payment intents cùng key.
- Gateway idempotency/reference chặn nhiều attempts tới gateway thuộc cùng intent.

Cả hai không tự thay thế invariant trên Order/Payment như “một order chỉ có một active capture theo policy” hoặc “không refund vượt tiền đã thu”.

## 16. Redis SET NX có đủ không?

Một giải pháp dễ thấy:

```text
SET idem:K processing NX PX 30000
```

Lệnh này có thể giảm concurrency tạm thời, nhưng **không tự bảo đảm exactly-once**:

- TTL có thể hết trong khi worker vẫn gọi gateway.
- Worker A còn chạy, worker B đã claim lại.
- Redis failover/restart có thể làm mất state theo persistence policy.
- Redis key không transaction chung với business DB.
- Chỉ lưu processing flag thì không replay được outcome.
- Xóa lock không kiểm tra owner token có thể xóa lock của worker khác.

Redis có thể làm cache terminal outcome hoặc rate limiter bổ sung, nhưng một payment system vẫn cần authoritative business state, unique constraints, provider operation reference và reconciliation.

### 16.1. Distributed lock và fencing

Nếu dùng lock có lease, cần ownership token và fencing khi resource hỗ trợ. Khi lease cũ đã hết, resource nên từ chối token cũ. Nếu external provider không hỗ trợ fencing, dùng downstream idempotency/status query; không đặt toàn bộ kỳ vọng an toàn vào lock.

## 17. Kafka/message consumer: duplicate delivery

Broker có thể giao cùng event lại nếu consumer commit business state nhưng crash trước khi ACK offset:

```text
Broker -> RevenueConsumer:
  PaymentCaptured(eventId=E1, amount=150000)

Consumer:
  tăng revenue 150000
  commit DB
  crash trước ACK

Broker phát lại E1.
Nếu xử lý lại như sự kiện mới => doanh thu bị cộng đôi.
```

Một inbox/processed-event table:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Consumer xử lý trong cùng local transaction nếu có thể:

```text
BEGIN
  INSERT processed_events(consumerName, eventId)
      ON CONFLICT DO NOTHING

  Chỉ nếu insert thành công:
      UPDATE revenue_projection
  Nếu conflict:
      bỏ qua business effect
COMMIT

ACK message sau DB commit
```

Ứng dụng phải kiểm tra RETURNING/affected rows; nếu luôn UPDATE projection dù INSERT conflict, unique constraint không bảo vệ business effect.

### 17.1. Dedupe theo consumer

Cùng một event PaymentCaptured có thể cần Reporting và Notification cùng xử lý. Không dùng một global processed flag để Reporting xử lý trước khiến Notification bỏ qua. Key nên gồm consumerName/effectType và eventId.

### 17.2. Duplicate khác out-of-order

Hai eventIds khác nhau thuộc cùng aggregate có thể đến sai thứ tự. Dedupe event ID không ngăn một state version cũ ghi đè bản mới. Cần aggregate version/sequence và expected-state guard; với delta events thiếu version, phải replay hoặc lấy snapshot.

## 18. TTL, retention và xóa result

Lưu mọi raw response vô thời hạn làm tăng dung lượng và rủi ro dữ liệu nhạy cảm. Nhưng xóa key quá sớm có thể khiến retry cũ tạo side effect mới.

Cần xét:

- Thời gian client có thể retry hoặc offline.
- Retention idempotency của gateway.
- Saga/refund có thể PENDING bao lâu.
- Broker message retention và khả năng replay.
- Thời gian reconciliation/chargeback/dispute.
- Business operation uniqueness có lưu lâu hơn result cache không.
- Chính sách dữ liệu nhạy cảm và compliance.

### 18.1. TTL hết không đồng nghĩa chưa từng có operation

Nếu key K bị dọn sau một ngày nhưng payment đã charge, retry K ngày thứ ba không được âm thầm tạo charge mới trái contract. Có thể giữ business reference/unique constraint dài hơn cache, lưu tombstone nhỏ, hoặc trả EXPIRED_KEY kèm hướng tra cứu/khởi tạo intent mới có chủ đích.

### 18.2. Không dọn UNKNOWN theo thời gian đơn thuần

UNKNOWN có thể chứa một payment đã thực thi nhưng chưa có evidence. Hãy reconcile và chuyển terminal hoặc giữ case có owner, không xóa mất dấu rồi cho retry cũ chạy lại.

## 19. Response replay và an toàn bảo mật

Idempotency store là nơi có thể chứa lịch sử nghiệp vụ và thông tin người dùng. Các nguyên tắc:

- Xác thực và ủy quyền trước khi replay outcome.
- Scope theo tenant/principal/operation type.
- Không cho user B dùng key user A để đọc payment result.
- Không lưu bearer token, password, PAN hay thông tin nhạy cảm không cần thiết.
- Lưu logical outcome hoặc business ID thay cho body lớn nếu hợp lý.
- Mã hóa dữ liệu và kiểm soát backup/logs/retention.
- Giới hạn độ dài key, kích thước payload và request rate để tránh lạm dụng.
- Không dùng raw keys/customer IDs làm metric labels cardinality cao.
- Giữ fingerprint algorithm tương thích khi rolling deployment.
- Xác định quyền truy cập outcome khi quyền của người dùng bị thu hồi.

**Idempotency key không phải một access token**. Biết được key không đồng nghĩa được quyền đọc resource.

## 20. Java/Spring: cách phân chia trách nhiệm

Các lớp minh họa:

```java
public record CreatePaymentRequest(
    String orderId,
    String amount,
    String currency
) {}

public enum ClaimDecision {
    CLAIMED, IN_PROGRESS, COMPLETED, KEY_CONFLICT, UNKNOWN
}

public record ClaimResult(
    ClaimDecision decision,
    String operationId,
    SavedOutcome outcome
) {}
```

Controller nhận request, kiểm auth và input. Application layer tạo canonical fingerprint, gọi repository atomic claim, rồi quyết định response.

```java
public ApiResult submitPayment(
    AuthenticatedScope scope,
    String key,
    CreatePaymentRequest body
) {
    String fingerprint = fingerprintService.hash(
        "CREATE_PAYMENT", scope, body
    );

    ClaimResult claim = store.claimOrGet(
        scope.tenantId(),
        "CREATE_PAYMENT",
        key,
        fingerprint
    );

    return switch (claim.decision()) {
        case CLAIMED ->
            operationService.acceptAndSchedule(claim.operationId(), body);

        case IN_PROGRESS ->
            ApiResult.pending(claim.operationId());

        case COMPLETED ->
            ApiResult.replayed(claim.outcome());

        case KEY_CONFLICT ->
            ApiResult.conflict("Idempotency key reused with different payload");

        case UNKNOWN ->
            ApiResult.pendingReconciliation(claim.operationId());
    };
}
```

Đây là pseudocode về điều phối, không phải code hoàn chỉnh chạy production. Cần bảo đảm acceptAndSchedule được lưu cùng atomic claim/outbox hoặc có recovery; có exception mapping, version/fencing, validation và tests. Đừng gọi external gateway ngay trong transaction giữ row lock.

## 21. Các failure windows cần xử lý

| Thời điểm crash/failure | Rủi ro | Cơ chế phục hồi |
| --- | --- | --- |
| Trước claim | Chưa có operation | Request khác claim bình thường |
| Sau claim, trước enqueue | Operation IN_PROGRESS bị kẹt | Claim+outbox cùng transaction hoặc recovery scanner |
| Sau outbox commit, trước publish | Command chưa gửi | Dispatcher retry |
| Sau publish, trước ACK | Command giao lại | Worker idempotent |
| Trong local DB transaction | Rollback/commit tùy DB | Business write + result atomic |
| Sau local commit, trước HTTP response | Client không biết success | Replay durable outcome |
| Sau gửi external call, trước provider response | UNKNOWN outcome | Same provider key + status query |
| Sau provider commit, trước local result | Local record stale | Reconciliation |
| Sau result commit, trước broker ACK | Message lặp | Inbox/dedupe |
| Lease hết nhưng worker cũ vẫn hoạt động | Split execution | Fencing local + downstream idempotency |
| TTL hết rồi retry cũ đến | Có thể tạo effect lần hai | Business unique key/tombstone/expired policy |

Điểm mấu chốt: unique index trong DB A không tự ngăn hai side effects ở provider B nếu mỗi attempt dùng một provider key khác nhau.

## 22. Quan sát và vận hành

Metrics hữu ích:

| Nhóm | Tín hiệu |
| --- | --- |
| Claim | first claims, conflicts, lock contention |
| Replay | saved-result hits, lookup latency |
| Payload | same key different fingerprint count |
| State | tuổi và số lượng IN_PROGRESS |
| Recovery | lease takeovers, stale worker rejects |
| Unknown | NEEDS_RECONCILIATION count và tuổi |
| Provider | status queries, idempotency conflicts |
| Messaging | processed-event duplicates, outbox backlog, DLQ age |
| Business | duplicate charge/refund incidents, unique orders |
| Storage | row count, body size, expired rows, cleanup lag |
| Security | cross-tenant replay denied, auth failures |

Nếu nhiều callers cùng poll một operation, dùng bounded polling, backoff/jitter, local single-flight hoặc notification để giảm thundering herd. Không giữ row lock trong lúc chờ HTTP gateway.

Alert nên có: IN_PROGRESS kẹt quá thời gian; UNKNOWN payments tăng; key fingerprint mismatch tăng sau client release; recovery scanner không xử lý backlog; business invariant bị vi phạm dù idempotency layer trông bình thường.

Không đưa idempotency key, customerId, paymentId vào metric labels có cardinality không giới hạn. Dùng tracing/log có phân quyền và retention.

## 23. Kiểm thử concurrent duplicates

### 23.1. 100 requests cùng key

Gửi đồng thời 100 requests cùng payload, auth scope và key, phân phối qua nhiều pods.

Kỳ vọng:

1. Chỉ một business operation/resource được tạo.
2. Không có hai payments hay refunds.
3. Các requests còn lại nhận IN_PROGRESS hoặc cùng outcome.
4. Sau hoàn tất, retries có cùng business ID.
5. Không có response sai tenant/payload.

### 23.2. Cùng key, payload khác

Gửi 50 requests amount 100000 và 50 requests amount 200000 dưới cùng key. Chỉ một fingerprint được claim; nhóm còn lại nhận KEY_CONFLICT. Không tạo hai charges, không trả response của amount này như kết quả amount kia.

### 23.3. 100 keys khác nhau

Nếu chúng đại diện 100 ý định hợp lệ, hệ không nên dùng một global mutex khiến tất cả requests bị tuần tự hóa không cần thiết, trừ concurrency/rate limit có chủ đích.

### 23.4. Hai pods cùng claim

Force requests tới Pod A và Pod B cùng lúc. Một map local không đủ; unique constraint/durable store phải quyết định một claim.

### 23.5. Local DB crash

Kill trước commit => order/outcome cùng rollback. Kill sau commit trước HTTP response => retry trả outcome đã lưu.

### 23.6. Gateway commit, response lost

Simulate charge thành công nhưng cắt response; client retry không tạo charge mới, local UNKNOWN được reconcile.

### 23.7. Lease takeover

Worker A treo; worker B takeover; A tiếp tục. A không ghi đè local state; external provider nhận các attempts thuộc cùng key.

### 23.8. Kafka redelivery

Consumer commit projection trước ACK rồi crash. Message lặp không làm cộng doanh thu hai lần.

### 23.9. TTL và rolling deployment

Retry sau expiration theo đúng contract; chạy v1 và v2 servers cùng key để kiểm fingerprint/canonicalization tương thích.

### 23.10. Unauthorized replay

User B biết key của user A nhưng không được đọc outcome. Kiểm cả tenant isolation, key enumeration và response privacy.

## 24. Các anti-pattern cần tránh

1. **SELECT-then-INSERT không có uniqueness:** hai requests đều bắt đầu side effect.
2. **Chỉ dùng ConcurrentHashMap:** không bảo vệ nhiều pods hoặc restart.
3. **Chỉ dùng Redis lock TTL:** worker cũ vẫn có thể chạy sau expiry, outcome không được lưu bền vững.
4. **Chỉ lưu boolean processed:** không replay được resource/result sau response lost.
5. **Tạo key mới khi retry:** một intent thành nhiều transactions.
6. **Không fingerprint payload:** cùng key amount khác lại được hiểu là thành công.
7. **Ghi COMPLETED trước business commit:** có thể nói success khi dữ liệu rollback.
8. **Giữ DB transaction qua network:** lock wait và cạn connection pool.
9. **Coi timeout là FAILED:** có thể provider đã commit.
10. **Retry external operation với provider key mới:** nguy cơ charge/refund trùng.
11. **Coi lease expired là chưa thực thi:** worker cũ hoặc provider còn chạy.
12. **Lưu mọi HTTP 500 thành terminal:** che lỗi transient và làm operation không thể hồi phục.
13. **Dedupe inbox nhưng vẫn update projection mọi lần:** effect vẫn trùng.
14. **ACK message trước DB commit:** có thể mất event.
15. **TTL dọn UNKNOWN:** mất evidence và mở đường double effect.
16. **Bỏ qua authorization khi replay:** lộ kết quả giữa users/tenants.
17. **Idempotency theo key thay business uniqueness:** hai keys khác nhau vẫn có thể phá invariant.
18. **Không test concurrency thật:** retry tuần tự không phát hiện race ở bước claim.

## 25. Checklist trước production

1. Idempotency-Key xác định business intent nào?
2. Scope có tenant, principal, operation type và resource phù hợp không?
3. Same key different payload được phát hiện bằng fingerprint nào?
4. Claim dùng unique constraint hoặc atomic CAS đáng tin không?
5. IN_PROGRESS có cách chờ/202/conflict rõ không?
6. Stored result là HTTP response, logical outcome hay resource ID?
7. Local business write và outcome có commit cùng transaction không?
8. Long-running operation có durable claim + outbox/recovery không?
9. Downstream có idempotency key và operation status API không?
10. Timeout sau remote call được đánh dấu UNKNOWN thay vì FAILED không?
11. Lease takeover có fencing và stale-worker protection không?
12. Retry/backoff có giới hạn và không tạo key mới không?
13. TTL có phù hợp provider window, offline retries và reconciliation không?
14. Security/authorization được áp dụng trước result replay không?
15. Response storage có PII minimization và retention không?
16. Kafka consumer có inbox + atomic projection update không?
17. Có test multiple pods, request burst, crash và response loss không?
18. Có dashboards cho IN_PROGRESS, UNKNOWN, replay và key conflict không?
19. Business uniqueness/invariants vẫn bảo vệ khi hai keys khác nhau không?
20. Client hiểu status PENDING, COMPLETED, KEY_CONFLICT và EXPIRED không?

## 26. Bài tập thực hành

**Bài 1 — CreateOrder đồng thời:** thiết kế database table và transaction để 100 POST cùng key chỉ tạo một order. Mô tả nhánh A commit nhưng response mất trước khi tới client.

**Bài 2 — Payment timeout:** Pod A charge K; gateway commit nhưng response mất; Pod B nhận retry. Xác định state machine, provider key và status query cần dùng.

**Bài 3 — Payload conflict:** cùng key nhưng amount khác. Thiết kế fingerprint, error status và logging không lộ dữ liệu nhạy cảm.

**Bài 4 — Redis TTL:** một lock 10 giây nhưng gateway có lúc xử lý 30 giây. Vẽ hai workers chạy đồng thời và đề xuất durable protection.

**Bài 5 — Refund concurrency:** hai refund intents có hai keys khác nhau cùng muốn hoàn tiền một capture. Bảo vệ tổng refundable amount bằng transaction/locking của Payment.

**Bài 6 — Broker redelivery:** Reporting đã cộng doanh thu rồi crash trước ACK. Thiết kế inbox và transaction để không cộng đôi; giải thích vì sao Notification vẫn được phép xử lý cùng event.

**Bài 7 — TTL 24 giờ, client offline 72 giờ:** đề xuất expiration policy, unique business ID, status endpoint và quy tắc retry cũ.

**Bài 8 — Fault injection:** liệt kê từng điểm crash: sau claim, sau outbox, sau provider commit, trước saved result, trước HTTP response; ghi expected outcome và cơ chế recovery.

## 27. Câu hỏi tự kiểm tra

1. Vì sao cache kết quả chưa đủ chống hai requests tới cùng lúc?
2. Idempotency key khác request ID và resource ID ra sao?
3. Unique index giải quyết check-then-insert race thế nào?
4. Same key khác amount phải được xử lý ra sao?
5. Vì sao tenant/owner scope quan trọng khi replay outcome?
6. IN_PROGRESS, COMPLETED và UNKNOWN khác nhau thế nào?
7. Vì sao bounded waiting an toàn hơn chờ vô hạn?
8. Khi nào lưu raw HTTP response, khi nào lưu logical outcome?
9. Tại sao business write và saved result nên chung local transaction?
10. Vì sao không giữ transaction mở suốt khi gọi payment gateway?
11. Lease expiry có chứng minh external effect chưa xảy ra không?
12. Fencing local DB chưa bảo vệ được external provider ra sao?
13. Khi provider commit rồi response mất, cần làm gì?
14. Redis SET NX giúp được gì và thiếu điều gì?
15. Single-flight trong memory khác durable idempotency như thế nào?
16. Vì sao Kafka có thể gửi lại event sau khi consumer đã commit?
17. Inbox dedupe theo consumer giúp gì?
18. TTL quá ngắn có thể gây duplicate thế nào?
19. Vì sao hai keys khác nhau vẫn phải bảo vệ business invariant?
20. Những test nào chứng minh concurrent duplicate handling qua nhiều pods?
21. Có nên lưu mọi HTTP 500 như một terminal outcome không?
22. Tại sao người biết idempotency key không tự có quyền xem result?

## 28. Ghi nhớ

- **Chống duplicate đồng thời bắt đầu từ atomic claim**, không từ một IF kiểm tra cache.
- **Saved outcome là phần bắt buộc của trải nghiệm retry an toàn**: client có thể nhận lại kết quả dù response lần đầu bị mất.
- **Cùng key cần cùng scope và fingerprint**, không cho payload khác dùng lại kết quả cũ.
- **Business state và result nên atomic trong local transaction** khi có thể; side effects bên ngoài cần durable operation reference, downstream idempotency và reconciliation.
- **IN_PROGRESS phải có recovery**; lease hết hạn không tự chứng minh request cũ chưa commit.
- **Timeout khác business failure**: giữ UNKNOWN và tra cứu trước khi quyết định lại.
- **Outbox/inbox giúp chuyển lệnh và dedupe**, không tạo exactly-once toàn hệ.
- **TTL, authorization và data minimization** ảnh hưởng trực tiếp tới tính đúng và bảo mật.
- **Business invariants vẫn phải được bảo vệ** nếu hai keys khác nhau cùng tác động lên một resource.
- **Kiểm thử concurrency trên nhiều pods, response loss và crash**, không chỉ gửi một retry tuần tự.

**Câu hỏi quyết định:** nếu hai POST thanh toán cùng key đến hai pods trong cùng một mili giây, và gateway đã charge nhưng response bị mất, hệ có thể cuối cùng trả đúng một payment result mà không phát sinh khoản thu thứ hai không? Muốn trả lời “có”, cần chỉ rõ atomic claim, transaction boundary, saved outcome, provider idempotency key và recovery test.
