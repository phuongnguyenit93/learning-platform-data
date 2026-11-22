# Xử lý kết quả không xác định và đối soát trước khi thực hiện lại

> **Bối cảnh:** Microservices · Đồng thời và lặp an toàn  
> **Trọng tâm:** Khi một lời gọi bị timeout, mất kết nối, hoặc tiến trình chết giữa chừng, hệ thống phải xác minh tác động nghiệp vụ thực tế trước khi cho phép thử lại thao tác có tác dụng phụ.

## 1. Vì sao “không nhận được kết quả” khác với “thực hiện thất bại”?

Trong hệ phân tán, **kết quả nghiệp vụ** và **khả năng quan sát kết quả** là hai điều khác nhau. Client có thể gửi yêu cầu thành công, server đã ghi cơ sở dữ liệu hoặc gọi dịch vụ thanh toán thành công, nhưng phản hồi không quay về client. Một lỗi timeout chỉ chứng minh rằng bên chờ **không nhận được phản hồi trong thời hạn**, không chứng minh rằng thao tác chưa xảy ra.

Ví dụ với dịch vụ thanh toán:

1. Order Service nhận yêu cầu thanh toán đơn **ORD-1001** và gọi Payment Provider với khóa lặp an toàn **pay:ORD-1001:v1**.
2. Provider tạo giao dịch và trừ tiền thành công.
3. Kết nối đứt trước khi Order Service nhận mã giao dịch.
4. Order Service chỉ thấy timeout. Nếu lập tức tạo một yêu cầu mới với khóa khác, khách hàng có thể bị trừ tiền hai lần.

Điều này cũng xảy ra với tạo đơn, đặt chỗ, gửi email, xuất kho, hoàn tiền, gọi REST API, xử lý message hoặc commit transaction. Lỗi 502/503/504, mất acknowledgment từ message broker và tiến trình crash đều có thể làm **kết quả thực tế chưa xác định**.

**Nguyên tắc cốt lõi:** Không đồng nhất **UNKNOWN** với **FAILED**. Một thao tác chưa biết kết quả phải được **đối soát (reconciliation)** theo nguồn có thẩm quyền trước khi có retry tạo thêm tác dụng phụ.

## 2. Phân loại kết quả và quyền được thử lại

| Loại kết quả | Bằng chứng quan sát | Hành động |
|---|---|---|
| **SUCCEEDED** | Nguồn có thẩm quyền xác nhận hiệu lực nghiệp vụ đã phát sinh | Lưu kết quả cuối, trả lại cùng kết quả cho các yêu cầu lặp, phát hành sự kiện sau khi lưu trạng thái |
| **FAILED_FINAL** | Nguồn có thẩm quyền xác nhận thất bại cuối cùng hoặc yêu cầu bị từ chối trước mọi tác dụng phụ | Kết thúc thao tác; muốn làm nghiệp vụ mới phải có quyết định và định danh mới |
| **RETRYABLE_NO_EFFECT** | Có bảo đảm rõ ràng yêu cầu chưa thực thi, chưa tạo tác dụng phụ | Có thể thử lại theo chính sách, dùng nguyên định danh nghiệp vụ và khóa idempotency |
| **PENDING** | Provider đã tiếp nhận và đang xử lý | Đợi callback hoặc kiểm tra trạng thái; không gửi một thao tác mới |
| **UNKNOWN** | Timeout, mất ACK, crash, trạng thái local và remote chưa khớp, hoặc kết quả truy vấn chưa đủ tin cậy | Ghi nhận sự không chắc chắn, khóa hành động gây trùng, lên lịch đối soát |
| **NEEDS_REVIEW** | Nhiều lần đối soát vẫn không đủ bằng chứng, hoặc phát hiện giao dịch mâu thuẫn | Chuyển xử lý vận hành có kiểm soát, không tự động làm lại |

Một HTTP 200 chưa đủ để tuyên bố nghiệp vụ hoàn tất nếu body chỉ trả **accepted**. HTTP 202 thường chỉ xác nhận đã nhận việc. Ngược lại, timeout/5xx **không mặc nhiên** là thất bại. Mã 4xx chỉ được coi là **FAILED_FINAL** nếu hợp đồng API khẳng định yêu cầu bị từ chối trước side effect; một số hệ thống vẫn có thể trả lỗi khi hiệu lực đã xảy ra.

## 3. Những định danh phải giữ ổn định

Để biết hai request có cùng ý nghĩa hay không, hệ thống nên tách các loại ID:

- **businessOperationId:** định danh một ý định nghiệp vụ, ví dụ **payment:ORD-1001**. Đây là cơ sở chống thực thi trùng xuyên các lần retry.
- **idempotencyKey:** khóa bên nhận dùng để trả lại cùng kết quả hoặc ngăn lặp cùng một tác dụng phụ. Chỉ tạo mới khi thật sự là nghiệp vụ mới; không tạo khóa mới chỉ vì timeout.
- **requestFingerprint:** hash của các tham số có ảnh hưởng đến nghiệp vụ (tenant, order, amount, currency, target...). Nếu cùng key nhưng payload khác thì từ chối rõ ràng, chẳng hạn 409.
- **providerRequestId/providerTransactionId:** khóa truy vấn hoặc mã giao dịch của hệ thống bên ngoài, lưu ngay khi có và dùng cho đối soát.
- **attemptId/traceId:** định danh mỗi lần truyền hoặc lần xử lý, phục vụ điều tra. Chúng **có thể thay đổi** qua retry nhưng không thay thế operationId/idempotencyKey.

Phạm vi uniqueness phải rõ, ví dụ **tenant_id + operation_type + idempotency_key**. Giao dịch mới cố ý (hoàn tiền một phần lần hai, thanh toán đợt mới) cần operationId mới theo quy tắc nghiệp vụ. Giao dịch lặp kỹ thuật phải dùng lại ID cũ.

> **Giới hạn quan trọng:** Idempotency của provider có thể chỉ được bảo lưu trong một khoảng thời gian. Sau khi khóa hết hạn, gửi lại cùng key không bảo đảm chống lặp. Khi đã quá cửa sổ bảo đảm, ưu tiên lookup/đối soát và can thiệp thủ công thay vì tự động phát lại.

## 4. Mô hình trạng thái phục hồi

Một cách mô hình hóa cho từng business operation:

~~~text
NEW
  └─ ghi nhận ý định hợp lệ ─▶ PROCESSING
                                 ├─ có bằng chứng thành công ─▶ SUCCEEDED
                                 ├─ có bằng chứng thất bại cuối ─▶ FAILED_FINAL
                                 ├─ provider tiếp nhận, chưa xong ─▶ PENDING
                                 └─ mất kết quả / crash / timeout ─▶ UNKNOWN
PENDING ── callback hoặc truy vấn ─▶ SUCCEEDED | FAILED_FINAL | UNKNOWN
UNKNOWN ── đối soát ─▶ SUCCEEDED | FAILED_FINAL | PENDING
UNKNOWN ── xác nhận chắc chắn chưa có side effect ─▶ PROCESSING (retry cùng key)
UNKNOWN ── hết hạn đối soát / mâu thuẫn ─▶ NEEDS_REVIEW
~~~

**Trạng thái UNKNOWN phải được lưu bền vững** chứ không chỉ nằm trong bộ nhớ thread. Nếu không lưu được trạng thái sau lời gọi, một job phục hồi cần phát hiện các bản ghi **PROCESSING quá hạn lease** và coi chúng là **nghi vấn**, không tự coi đã thất bại. **PROCESSING** mô tả tiến trình đang chạy; **SUCCEEDED** mới mô tả kết quả đã được chứng minh.

Những trạng thái cuối không nên tự chuyển lùi chỉ vì một thông báo cũ đến muộn. Nếu callback báo mâu thuẫn với kết quả đã xác nhận, lưu bằng chứng và đưa vào luồng xử lý sai lệch.

## 5. Quy trình an toàn khi nhận kết quả không xác định

~~~mermaid
flowchart TD
    A["Gửi thao tác với operationId và idempotencyKey ổn định"] --> B{"Có phản hồi cuối cùng đáng tin cậy?"}
    B -->|Có| C["Ghi trạng thái cuối cùng và kết quả"]
    B -->|Không| D["Ghi UNKNOWN hoặc đánh dấu attempt quá hạn"]
    D --> E["Tra cứu bản ghi local, provider, ledger, callback"]
    E --> F{"Nguồn có thẩm quyền kết luận gì?"}
    F -->|Đã thành công| G["Ghi SUCCEEDED, tái sử dụng kết quả"]
    F -->|Đã thất bại cuối| H["Ghi FAILED_FINAL"]
    F -->|Đang xử lý| I["Chờ và hẹn đối soát lại"]
    F -->|Chưa có tác dụng phụ và được phép retry| J["Retry cùng operationId/key"]
    F -->|Chưa đủ bằng chứng hoặc mâu thuẫn| K["Giữ UNKNOWN hoặc chuyển NEEDS_REVIEW"]
    I --> E
    J --> B
~~~

**Bước 1 — Bảo toàn ý định trước side effect.** Ghi một operation record với payload fingerprint, key, loại thao tác, tenant và thời điểm bắt đầu. Dùng ràng buộc unique ở DB để hai request đồng thời không thể tạo hai thao tác logic.

**Bước 2 — Gọi hệ thống ngoài bằng một key ổn định.** Tránh giữ một transaction DB mở trong suốt lời gọi mạng. Các worker cạnh tranh phải có cơ chế claim/lease hoặc compare-and-set (CAS) trên bản ghi; khi lease hết hạn, worker mới cần đối soát trạng thái cũ trước khi gọi lại.

**Bước 3 — Gặp timeout/mất kết quả thì ghi nhận nghi vấn.** Lưu lỗi kỹ thuật, attemptId, thời gian, correlation ID và thời điểm đối soát tiếp. Không tạo một operation mới để “chạy lại cho chắc”.

**Bước 4 — Thu thập bằng chứng từ đúng nguồn.** Kiểm tra operation record và transaction/ledger; gọi API tra cứu theo idempotency key, merchant reference hoặc provider transaction ID; xử lý webhook có xác thực; kiểm tra outbox/inbox, audit log và trạng thái tài nguyên liên quan. Ưu tiên nguồn có thẩm quyền đối với side effect đang xét.

**Bước 5 — Quyết định theo bằng chứng.** Nếu đã hoàn tất, đồng bộ local state và trả lại kết quả; nếu đang pending, chờ; nếu chắc chắn chưa phát sinh side effect và hợp đồng cho phép, thử lại cùng key. Nếu truy vấn trả **not found** nhưng dữ liệu remote đồng bộ trễ, **chưa đủ** để kết luận chưa thực hiện.

**Bước 6 — Kết thúc hoặc nâng cấp xử lý.** Giới hạn số lần và thời gian đối soát; ghi lý do vì sao chưa kết luận được, phát cảnh báo và chuyển xử lý có kiểm soát. Không có quy tắc “timeout N lần là failed” nếu không có bằng chứng nghiệp vụ.

## 6. Thiết kế dữ liệu lưu dấu ý định và bằng chứng

Ví dụ một bảng PostgreSQL tối giản, chỉ minh họa khái niệm:

~~~sql
CREATE TABLE business_operations (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(80) NOT NULL,
    operation_type      VARCHAR(40) NOT NULL,
    idempotency_key     VARCHAR(180) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    status              VARCHAR(32) NOT NULL,
    provider_request_id VARCHAR(180),
    provider_txn_id     VARCHAR(180),
    result_payload      JSONB,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    version             BIGINT NOT NULL DEFAULT 0,
    next_reconcile_at   TIMESTAMPTZ,
    last_error_code     VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, operation_type, idempotency_key)
);
CREATE INDEX idx_operation_reconcile
    ON business_operations (status, next_reconcile_at);
~~~

Gợi ý ý nghĩa dữ liệu:

- **result_payload** chứa kết quả đủ để trả lại cho duplicate request khi đã kết thúc; tránh tái tạo tác dụng phụ chỉ để lấy response.
- **version** hỗ trợ cập nhật có điều kiện và chống worker cũ ghi đè kết quả mới.
- **next_reconcile_at**, **attempt_count**, **last_error_code** hỗ trợ scheduling và giám sát.
- **provider_txn_id** phục vụ điều tra và dedup; cân nhắc ràng buộc unique theo tenant/provider nếu business contract cho phép.
- **status** phản ánh kết luận nghiệp vụ, không chỉ trạng thái HTTP gần nhất.

Ví dụ CAS để chỉ một worker được chuyển từ UNKNOWN sang PROCESSING sau khi **đã có bằng chứng cho phép retry**:

~~~sql
UPDATE business_operations
   SET status = 'PROCESSING',
       version = version + 1,
       attempt_count = attempt_count + 1,
       updated_at = now()
 WHERE id = :operation_id
   AND status = 'UNKNOWN'
   AND version = :expected_version
 RETURNING id, version, idempotency_key;
~~~

Nếu trả về 0 hàng, một worker khác đã thay đổi trạng thái; đọc lại kết quả hiện hành. CAS **không tự chứng minh** có thể retry: điều kiện “không có side effect hoặc provider bảo đảm cùng key an toàn” phải được kiểm tra trước. Trong sản phẩm thực tế còn cần lưu lease owner, lease expiry hoặc fencing token để xử lý worker chết và tránh hai tiến trình cùng thao tác.

## 7. Cách triển khai trong một luồng Java/Spring

Mã giả dưới đây diễn tả thứ tự xử lý, không phụ thuộc SDK provider cụ thể:

~~~java
PaymentResult pay(PaymentCommand command) {
    Operation op = operationStore.findOrCreate(
        command.tenantId(),
        "PAYMENT",
        command.idempotencyKey(),
        fingerprint(command)
    ); // Unique constraint và kiểm tra fingerprint phải là atomic.

    if (op.isFinal()) {
        return op.savedResult(); // Phản hồi ổn định cho duplicate.
    }
    if (op.isPendingOrUnknown()) {
        return PaymentResult.accepted(op.id()); // Client theo dõi operation.
    }

    // Claim operation bằng CAS/lease; chỉ một executor thực thi.
    if (!operationStore.tryClaim(op.id(), op.version())) {
        return PaymentResult.accepted(op.id());
    }

    try {
        ProviderResult response = paymentProvider.charge(
            command.amount(), command.currency(), op.idempotencyKey()
        );

        if (response.isTerminalSuccess()) {
            operationStore.completeSuccess(op.id(), response);
            return PaymentResult.success(response.transactionId());
        }
        if (response.isTerminalFailureWithEvidence()) {
            operationStore.completeFailure(op.id(), response);
            return PaymentResult.failed(response.reason());
        }

        operationStore.markUnknown(op.id(), "REMOTE_NOT_TERMINAL");
        return PaymentResult.accepted(op.id());
    } catch (TimeoutException | ConnectionException ex) {
        operationStore.markUnknown(op.id(), "RESPONSE_NOT_OBSERVED");
        return PaymentResult.accepted(op.id());
    }
}
~~~

Đây là **pseudocode**, không phải đoạn Java copy là chạy: tên exception, repo, mapper, transaction và response phải khớp hệ thống thật. Điểm quyết định là **exception về mạng dẫn đến UNKNOWN**, còn việc gọi lại phải đi qua worker đối soát. Nếu tiến trình chết trước khi gọi **markUnknown**, watchdog phát hiện operation PROCESSING/lease đã quá hạn và đưa vào đối soát.

Một **reconciliation worker** có thể hoạt động như sau:

~~~text
reconcile(operation):
  claim bằng lease/CAS
  lấy provider reference và idempotency key đã lưu
  query nguồn giao dịch có thẩm quyền
  nếu SUCCEEDED với bằng chứng khớp amount/currency/order:
      hoàn tất local state theo CAS
      ghi outbox event một lần trong cùng transaction
  nếu FAILED_FINAL:
      lưu thất bại cuối theo CAS
  nếu PENDING hoặc kết quả chưa có tính kết luận:
      hẹn đối soát tiếp với backoff + jitter
  nếu xác nhận no-effect theo hợp đồng provider:
      cho phép retry đúng cùng key, trong cửa sổ idempotency
  nếu dữ liệu mâu thuẫn hoặc quá ngưỡng phục hồi:
      chuyển NEEDS_REVIEW, tạo cảnh báo, giữ đầy đủ bằng chứng
~~~

**Ranh giới transaction:** Chỉ commit dữ liệu local và outbox trong cùng transaction DB của service. Một lời gọi ra provider nằm ngoài transaction đó, nên có khoảng trống có thể crash. Chính vì vậy cần record ý định, khóa ổn định và đối soát; không thể lấy một **@Transactional** bọc HTTP call rồi coi toàn bộ hai hệ thống là atomic.

## 8. Ví dụ đối soát thanh toán từ đầu đến cuối

Giả sử đơn **ORD-1001** có tổng tiền **590.000 VND** và duy nhất một ý định thanh toán. Operation được tạo với:

~~~json
{
  "operationId": "payment:ORD-1001",
  "idempotencyKey": "pay:ORD-1001:v1",
  "amount": 590000,
  "currency": "VND",
  "status": "PROCESSING"
}
~~~

| Mốc | Thực tế ở provider | Điều Order Service nhìn thấy | Hành động an toàn |
|---|---|---|---|
| T0 | Chưa có giao dịch | Đã lưu operation PROCESSING | Gọi charge với key cố định |
| T1 | Charge thành công, mã P-7788 | Kết nối bị timeout | Ghi UNKNOWN, trả operationId |
| T2 | Giao dịch P-7788 tồn tại | Reconciler lookup theo key/merchant reference | Xác nhận amount/currency/order khớp |
| T3 | Không cần charge thêm | Cập nhật SUCCEEDED và ghi PaymentSucceeded vào outbox | Consumer khác xử lý sự kiện theo eventId |
| T4 | Không có giao dịch mới | Client gửi lại cùng key hoặc GET trạng thái | Trả lại kết quả lưu sẵn P-7788 |

Nếu provider trả **PENDING**, không phát **PaymentSucceeded**. Nếu API lookup trả **NOT_FOUND** ngay tại T2, phải hiểu rõ tính nhất quán và độ trễ của provider; một phản hồi tra cứu âm tính tức thời có thể chưa chứng minh không có charge. Khi không có khả năng tra cứu đáng tin cậy và không có bảo đảm idempotency, chuyển xử lý thủ công thường an toàn hơn tự động phát lại charge.

### Trường hợp hai request đồng thời

Client A và B cùng gửi **pay:ORD-1001:v1**. Ràng buộc unique chỉ cho phép một operation; request còn lại đọc trạng thái đã tồn tại. CAS/lease chỉ cho một worker thực thi; những request khác nhận cùng operationId và trạng thái pending/success. Nếu key giống nhưng amount khác, từ chối vì fingerprint mismatch, không tái sử dụng kết quả của amount cũ.

## 9. HTTP API và trải nghiệm client

Một API bất đồng bộ có thể công khai:

~~~http
POST /payments
Idempotency-Key: pay:ORD-1001:v1

HTTP/1.1 202 Accepted
Location: /operations/payment:ORD-1001
Retry-After: 3
~~~

~~~http
GET /operations/payment:ORD-1001

HTTP/1.1 200 OK
Content-Type: application/json

{
  "operationId": "payment:ORD-1001",
  "status": "UNKNOWN",
  "message": "Đang xác minh kết quả giao dịch"
}
~~~

Client nên lưu **operationId và idempotencyKey** qua refresh/restart, dùng GET status hoặc nhận thông báo bất đồng bộ để theo dõi. Nếu POST timeout, trước hết tra cứu operation; nếu phải gửi lại POST thì phải **giữ nguyên key và payload**. UI không hiển thị “thanh toán thất bại” khi service mới chỉ biết UNKNOWN; cũng không hiển thị “đã thanh toán” khi mới accepted. Retry-After giúp tránh client polling liên tục.

Hệ thống cần quy định retention của operation/result đủ lâu so với cửa sổ retry của client, thời gian giải quyết giao dịch và thời hạn idempotency của provider.

## 10. Đối soát khi thao tác gồm nhiều side effect

Một nghiệp vụ đặt hàng có thể gồm **giữ hàng → thanh toán → phát hành sự kiện**. Không nên trả một trạng thái tổng quát “thất bại” rồi làm lại cả chuỗi nếu chỉ mất ACK ở bước cuối.

- Mỗi bước có định danh và trạng thái riêng, ví dụ **reservation:ORD-1001** và **payment:ORD-1001**.
- Sử dụng **Saga** để điều phối các bước với hành động bù (release reservation/refund) khi có bằng chứng về trạng thái từng bước; bù không thay thế đối soát và bản thân hành động bù cũng phải idempotent.
- **Transactional Outbox:** Khi commit **SUCCEEDED** cùng lúc ghi một outbox event trong cùng local transaction. Publisher có thể gửi trùng do mất ACK, nên consumer cần chống lặp.
- **Inbox/Dedup:** Consumer lưu **eventId** đã xử lý với unique constraint trong cùng transaction với side effect local; chỉ ACK message sau commit. Mất ACK có thể làm broker phát lại, nhưng không được xử lý nghiệp vụ lần hai.
- **Compensation:** Chỉ hoàn tiền khi có bằng chứng charge thực sự xảy ra và quyết định nghiệp vụ yêu cầu hoàn; không hoàn tiền “phòng hờ” chỉ vì lookup chưa thấy kết quả.

Khái niệm **exactly once** của một broker hoặc database không bảo đảm hiệu ứng **exactly once xuyên HTTP provider, broker và DB độc lập**. Mục tiêu thực tế là **at-least-once delivery + idempotent processing + reconciliation + durable evidence**.

## 11. Cạm bẫy với “NOT_FOUND”, retry và tính đồng thời

### 11.1. Phản hồi tra cứu âm tính không luôn là bằng chứng no-effect

Lệnh charge có thể đang trong hàng đợi, giao dịch vừa commit nhưng chỉ mục tra cứu đồng bộ trễ, hoặc callback đến sau. Nếu **query → NOT_FOUND → charge lần hai** chạy trước khi thao tác cũ hiển thị, vẫn có double charge.

Chỉ retry tự động khi một trong các điều kiện được bảo đảm: (a) provider có cơ chế idempotency còn hiệu lực đối với cùng key, hoặc (b) provider có câu trả lời cuối cùng có thẩm quyền rằng thao tác cũ không phát sinh side effect. “Không nhìn thấy” hoặc “đã chờ 10 giây” không đủ.

### 11.2. TTL và cửa sổ lặp an toàn

Nếu provider quên key sau 24 giờ còn job phục hồi chạy sau 36 giờ, gửi lại cùng key có thể tạo giao dịch mới. Theo dõi **idempotency_expires_at** hoặc deadline nghiệp vụ. Hết bảo đảm thì đưa vào tra cứu/điều tra, không cố retry mù.

### 11.3. Lease hết hạn trong khi worker cũ vẫn chạy

Worker A gọi provider chậm; lease hết hạn; worker B nhận job. CAS ở DB chặn ghi đè trạng thái local, nhưng **không chặn được hai HTTP call bên ngoài** nếu hai worker cùng gửi với key khác. Cả hai phải dùng chung key bền vững; nơi hỗ trợ nên dùng fencing token hoặc claim phiên bản rõ ràng. Một timeout của worker A không chứng minh tác động của nó chưa xảy ra.

### 11.4. Webhook trùng, đến muộn hoặc đảo thứ tự

Webhook phải được xác thực, dedup theo eventId và khớp transaction/order/amount. Event **PENDING** đến sau **SUCCEEDED** không được ghi đè trạng thái cuối. Trạng thái mâu thuẫn cần lưu lịch sử và điều tra.

## 12. Retry policy và vận hành đối soát

**Retry cho lỗi kỹ thuật** vẫn hữu ích nhưng cần phân loại: GET/status lookup thường có thể retry an toàn với giới hạn; POST tạo side effect chỉ retry sau khi thỏa hợp đồng idempotency và bằng chứng phù hợp.

Một lịch tham khảo cho reconciler: chạy sau **5 giây → 15 giây → 45 giây → 2 phút → 5 phút**, có jitter, tối đa số attempt và deadline theo SLA nghiệp vụ. Đây là ví dụ, phải chỉnh theo latency, rate limit, consistency window và quota của provider. Gặp 429 cần tuân thủ Retry-After nếu có; 5xx từ lookup chỉ làm tăng thời gian chờ, không kết luận FAILED.

Các chỉ số nên theo dõi gồm số operation UNKNOWN/PENDING, **tuổi UNKNOWN lớn nhất**, thời gian đến kết luận cuối, tỷ lệ đối soát thành công, tỷ lệ phải can thiệp, duplicate bị ngăn, fingerprint conflict, provider lookup error và số operation mắc kẹt sau restart. Log/trace phải liên kết operationId, attemptId, providerRequestId, providerTxnId; tránh log dữ liệu thẻ hoặc thông tin nhạy cảm.

Quy trình hỗ trợ vận hành nên cho phép xem **timeline và bằng chứng**, truy vấn lại provider, đánh dấu đã giải quyết bằng kết quả có chứng từ và phát cảnh báo. Một nút **“Retry” thủ công** cũng phải đi qua guard idempotency/đối soát, không gọi side effect trực tiếp.

## 13. Kịch bản kiểm thử lỗi phân tán

| Tình huống cố ý tạo lỗi | Kỳ vọng |
|---|---|
| Provider charge thành công nhưng response bị cắt | UNKNOWN → lookup xác nhận SUCCEEDED; chỉ một charge |
| Timeout trước khi provider nhận request | Chờ bằng chứng no-effect hoặc retry cùng key theo bảo đảm của provider |
| Process chết sau provider success nhưng trước local commit | Watchdog tìm PROCESSING quá hạn; đối soát và hoàn tất |
| Hai request cùng key đến đồng thời | Một operation, một tác dụng phụ; request thứ hai nhận cùng kết quả/trạng thái |
| Một key nhưng amount khác | Từ chối conflict; không dùng lại kết quả sai |
| Provider lookup trả NOT_FOUND tạm thời rồi xuất hiện giao dịch | Không charge trùng trong cửa sổ đồng bộ trễ |
| Broker phát lại event do mất ACK | Consumer xử lý side effect đúng một lần nhờ inbox/unique |
| Webhook SUCCEEDED đến trước webhook PENDING | Không hạ trạng thái từ SUCCEEDED về PENDING |
| Lease worker hết hạn và worker khác nhận job | CAS/lease bảo vệ local state; cùng idempotency key bảo vệ provider |
| Provider hết hạn lưu idempotency key | Không tự động phát lại giao dịch khi chưa có bằng chứng no-effect |
| Provider trả hai giao dịch khác nhau cho cùng logical operation | Cảnh báo mâu thuẫn, NEEDS_REVIEW, lưu đủ chứng cứ |

Có thể dùng fault injection để ngắt kết nối đúng sau khi provider xử lý, kill process giữa hai commit, delay callback và chạy nhiều worker song song. Điều cần quan sát là **số tác dụng phụ thực tế**, **trạng thái cuối đúng**, **khả năng phục hồi sau restart** và **việc không mất dấu UNKNOWN**; chỉ kiểm tra HTTP response là chưa đủ.

## 14. Quy tắc ra quyết định khi triển khai

1. **Định nghĩa rõ “đã thực hiện”** cho từng nghiệp vụ và chọn nguồn có thẩm quyền (payment ledger/provider, inventory owner, shipping provider...).
2. **Ghi ý định bền vững trước external side effect**; dùng unique operationId/idempotencyKey và kiểm tra fingerprint.
3. **Tách attempt kỹ thuật khỏi operation nghiệp vụ.** Timeout chỉ đổi trạng thái quan sát, không tạo nghiệp vụ mới.
4. **Bảo vệ đồng thời** bằng DB unique + CAS/lease; dùng lại khóa idempotency tại nơi thực thi side effect.
5. **Đối soát trước retry.** Chỉ retry khi có bảo đảm idempotency còn hiệu lực hoặc kết luận đáng tin cậy rằng chưa có side effect.
6. **Duy trì trạng thái UNKNOWN/PENDING bền vững**, job phục hồi, log bằng chứng, deadline và lối xử lý thủ công.
7. **Chống trùng toàn chuỗi** bằng outbox/inbox, xử lý callback idempotent và state transition đơn điệu.
8. **Trả thông tin trung thực cho client:** chưa xác định thì công bố đang xác minh, cung cấp operationId để tra cứu.

### Tự kiểm tra bằng một câu hỏi

**“Nếu thao tác thực sự đã thành công nhưng mọi phản hồi đều bị mất, lần chạy tiếp theo của hệ thống có tạo thêm một side effect không?”**

Một thiết kế an toàn phải chứng minh được bằng định danh ổn định, bản ghi bền vững, ràng buộc đồng thời và quy trình đối soát rằng câu trả lời là **không**, kể cả khi tiến trình crash, message bị phát lại hoặc hai worker cùng hoạt động.
