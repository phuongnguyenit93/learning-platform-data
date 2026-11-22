# Xử lý kết quả chưa xác định sau lỗi mạng

## Mục tiêu bài học

Trong hệ thống Microservices, một lời gọi đồng bộ HTTP hoặc gRPC có thể kết thúc bằng timeout hoặc connection reset ngay cả khi phía nhận đã hoàn thành nghiệp vụ. Ví dụ Ordering gọi Inventory để giữ tồn kho, Inventory ghi reservation vào database và chuẩn bị trả response, nhưng kết nối bị ngắt. Ordering chỉ thấy timeout; nó **không biết hàng đã được giữ hay chưa**.

Đây là bài toán **unknown outcome / ambiguous result**. Nếu client retry như một yêu cầu mới, hệ thống có thể tạo trùng đơn hàng, giữ tồn hai lần, gửi hai email hoặc thu tiền hai lần. Nếu client coi timeout là thất bại và hủy các bước sau, trạng thái có thể mâu thuẫn với side effect đã xảy ra. Nếu chờ vô hạn, tài nguyên kết nối và thread có thể bị giữ quá lâu.

Sau bài học, bạn có thể:

- Phân biệt lỗi transport, từ chối nghiệp vụ đã xác nhận và kết quả chưa xác định.
- Giải thích vì sao timeout, connection reset, 500/502/503/504 không tự chứng minh rollback.
- Thiết kế stable operation identity, idempotency key, endpoint tra cứu và state machine.
- Lựa chọn retry an toàn, reconciliation, compensation và manual review.
- Bảo vệ concurrent retries, xử lý crash và tích hợp PSP.
- Áp dụng nguyên tắc trên trong Java/Spring Boot và kiểm thử fault scenarios.

## 1. Một timeout có thể che giấu thành công

~~~text
Ordering client                        Inventory service
       |                                        |
       | -- POST /reservations --------------> |
       |                                        | Validate request
       |                                        | Reserve stock
       |                                        | COMMIT
       | <--------- response lost ---- X       |
       |                                        |
       | ... Request timeout ...                |
       |                                        |
       ? Reservation đã tồn tại hay chưa?        |
~~~

Client chỉ quan sát được **không nhận response đáng tin trong deadline**. Có nhiều khả năng:

1. Request chưa rời client.
2. Request đã rời client nhưng chưa đến server.
3. Server nhận request nhưng chưa bắt đầu nghiệp vụ.
4. Server đang xử lý khi connection bị ngắt.
5. Server đã commit dữ liệu nhưng lỗi trước khi tạo response.
6. Server đã gửi response, nhưng proxy hoặc mạng làm mất.
7. Server gọi tiếp downstream, downstream có thể đã xử lý nhưng response bị mất.

Cùng một SocketTimeoutException có thể xuất hiện trong nhiều trường hợp. Client không thể suy ra trạng thái commit từ việc gửi xong bytes hay từ thời gian chờ.

~~~text
t0: Client gửi request
t1: Gateway nhận và chuyển
t2: Server nhận request
t3: Server validate và xử lý
t4: Side effect COMMIT
t5: Server gửi response
t6: Client nhận response

Mất mạng ở t3, t4, t5 hay t6 cho kết quả nghiệp vụ khác nhau.
~~~

**Nguyên tắc:** Không nhận được xác nhận thành công khác với nhận được xác nhận thất bại. Cancellation của HTTP request không tự rollback transaction đã commit, email đã gửi hoặc giao dịch PSP đang thực hiện.

## 2. Phân biệt transport failure với business failure

| Điều caller nhìn thấy | Có thể kết luận | Hành động |
| --- | --- | --- |
| Thành công 200/201 theo API contract | Nghiệp vụ đạt mức cam kết đã công bố | Lưu resource/operation ID |
| Từ chối có thẩm quyền, ví dụ OUT_OF_STOCK | Business rejection xác định | Xử lý lý do nghiệp vụ |
| HTTP 202/PENDING | Server đã nhận, chưa chắc hoàn tất | Tra cứu tiến độ |
| Timeout/connection reset | Kết quả UNKNOWN | Tra cứu hoặc retry idempotent |
| Gateway 502/503/504 | Downstream có thể đã commit | Không tự coi FAILED |
| HTTP 500 | Phụ thuộc điểm lỗi thực tế | Đối chiếu hợp đồng và source of truth |
| GET status 404 trên replica chậm | Không đủ chứng cứ operation không tồn tại | Tra cứu nguồn có thẩm quyền |

Một HTTP 500 có thể xuất hiện sau khi transaction đã commit nhưng trước lúc response được serialize. Một timeout từ PSP có thể đến sau khi PSP authorize tiền. Vì vậy exception kỹ thuật không phải business result.

Trong code cần phân biệt ít nhất ba nhóm:
- **SUCCEEDED/REJECTED:** kết luận nghiệp vụ có thẩm quyền.
- **PENDING:** có xác nhận đang xử lý.
- **UNKNOWN:** không biết side effect đã xảy ra hay chưa.

## 3. Vì sao Microservices làm kết quả mơ hồ khó xử lý?

~~~text
Mobile app → API Gateway → Ordering → Payments → External PSP
                                  |
                                  +----> Inventory
~~~

Ordering có timeout 2 giây khi gọi Payments; Payments chờ PSP tối đa 5 giây. Ordering hết deadline rồi đánh dấu đơn thất bại, trong khi PSP có thể tiếp tục authorize thành công. Local transaction của Ordering không thể rollback transaction của Payments hoặc PSP.

Rủi ro chính:
- Duplicate create: hai Order cho một checkout.
- Double reservation: trừ tồn hai lần.
- Double charge: cùng một khoản tiền được xử lý dưới hai reference.
- Lost confirmation: UI báo thất bại dù đã tạo tài nguyên.
- Inconsistent workflow: các dịch vụ lưu trạng thái không tương thích.
- Retry storm: nhiều tầng cùng retry, tải khuếch đại.
- Stuck operation: trạng thái PENDING/UNKNOWN không có chủ thể xử lý.

Giải pháp phải nêu rõ **ai là nguồn sự thật**, identity của cùng một ý định và cơ chế phục hồi khi không còn request đồng bộ nào đang chờ.

## 4. UNKNOWN là trạng thái nghiệp vụ hợp lệ

Một state machine tham khảo:

~~~text
NEW -> SUBMITTED -----> SUCCEEDED
            |--------> REJECTED
            |--------> PENDING
            |--------> UNKNOWN
                          |
                          v
                     RECONCILING
                       /   |   \
                      v    v    v
                 SUCCEEDED REJECTED NEEDS_MANUAL_REVIEW
~~~

Ý nghĩa:
- NEW: ý định nghiệp vụ đã có định danh, chưa gửi.
- SUBMITTED: đã thử gửi, chưa có kết quả cuối.
- PENDING: nguồn có thẩm quyền cho biết đang xử lý.
- SUCCEEDED: có bằng chứng nghiệp vụ thành công.
- REJECTED: có kết luận từ chối.
- UNKNOWN: mất thông tin về kết quả.
- RECONCILING: đang kiểm tra lại nguồn sự thật.
- NEEDS_MANUAL_REVIEW: vượt khả năng xác định tự động.

Hết deadline không đồng nghĩa thất bại. Khi vẫn UNKNOWN, có thể hiển thị “đang xác minh” cho người dùng và có background worker xử lý tiếp. Transition phải có kiểm soát phiên bản để một callback PENDING đến muộn không ghi đè SUCCEEDED.

## 5. Stable identity: một ý định, nhiều lần gửi

Các ID có vai trò khác nhau:

| ID | Vai trò |
| --- | --- |
| traceId/requestId | Theo dõi mỗi lần truyền request |
| idempotencyKey | Nhận diện một ý định nghiệp vụ qua mọi retry |
| operationId | Truy vấn trạng thái và khôi phục một tiến trình |
| resourceId | Định danh Order/Payment/Reservation được tạo |

Ví dụ:

~~~http
POST /payments/authorizations
Idempotency-Key: checkout-471-authorize-v1
Content-Type: application/json

{"orderId":"order-471","amountMinor":159900,"currency":"VND"}
~~~

Nếu timeout, client dùng **cùng key và cùng ý nghĩa** ở lần retry. Không tạo key mới chỉ vì requestId của lần gửi mới khác lần trước.

Key thường được scope theo tenantId + operationType + idempotencyKey. Cùng key ở hai tenant có thể là hai ý định khác nhau. Key không thay thế authentication/authorization.

### 5.1. Không dùng cùng key cho payload khác

Nếu key K được gửi lần đầu cho amount=100, lần sau lại amount=200, server phải từ chối conflict thay vì trả kết quả của amount=100 như thể thao tác amount=200 thành công.

Có thể lưu fingerprint dựa trên các tham số nghiệp vụ đã chuẩn hóa: tenant, operation type, orderId, amount, currency, recipient. Không chỉ hash raw JSON nếu thứ tự field hoặc cách biểu diễn không ảnh hưởng ngữ nghĩa.

### 5.2. Thời gian giữ key

Nếu server xóa idempotency record sau 24 giờ nhưng client có thể retry lại sau ba ngày, side effect cũ có nguy cơ bị tạo thêm. Retention phải theo vòng đời nghiệp vụ và chính sách provider. Với thao tác tài chính, cần unique business constraint bền vững ngoài response cache TTL.

## 6. Idempotency: retry không được nhân đôi side effect

Với cùng key và cùng payload, server cần:
1. Claim key bằng cơ chế nguyên tử.
2. Cho một executor chịu trách nhiệm side effect.
3. Lưu trạng thái và kết quả.
4. Trả kết quả đã lưu hoặc PENDING cho request trùng.
5. Từ chối key trùng với payload khác.
6. Chịu được concurrent retries và restart.
7. Nếu downstream có side effect, tiếp tục giữ identity qua downstream hoặc reconcile.

**Sai:**

~~~java
for (int attempt = 0; attempt < 3; attempt++) {
    String key = UUID.randomUUID().toString();
    paymentClient.authorize(key, request);
}
~~~

Ba attempt với ba key có thể thành ba payment intent. **Đúng về identity** là tạo một key trước lần gửi đầu rồi giữ nó qua mọi attempt:

~~~java
String stableKey = command.operationId();
// Retry và status inquiry sử dụng stableKey.
~~~

Tuy vậy stable key chỉ là điều kiện cần; còn phải có timeout budget, backoff, xử lý conflict, và contract phía server.

### 6.1. Database giúp chặn race

~~~sql
CREATE TABLE api_operations (
    tenant_id VARCHAR(80) NOT NULL,
    operation_type VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    resource_id VARCHAR(160),
    result_json TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_type, idempotency_key)
);
~~~

Trong cùng database, có thể claim key, tạo resource và cập nhật operation result trong local transaction. Nếu claim đã tồn tại, kiểm tra fingerprint và trả lại trạng thái đã ghi. Unique constraint hoặc atomic insert là cần thiết khi hai request đến đồng thời trên hai pod.

Không nên chỉ check existence rồi mới insert mà không có cơ chế cạnh tranh, vì hai request có thể cùng thấy key chưa tồn tại. Cache riêng từng JVM cũng không đủ cho nhiều instance.

### 6.2. Crash giữa các bước

Nếu server đã lưu CLAIMED rồi crash trước side effect, recovery worker có thể xử lý tiếp. Nếu crash sau khi gửi PSP nhưng trước lúc ghi result nội bộ, worker **không được mặc định chưa gửi**. Nó phải tra cứu provider bằng stable reference để xác minh trước khi thử lại.

Một cơ chế lease/owner token có thể giảm số worker cùng claim; vẫn phải xử lý trường hợp worker cũ còn chạy khi lease hết hạn.

## 7. Endpoint tra cứu trạng thái

Một API có thể trả operation resource:

~~~http
POST /orders
Idempotency-Key: order-create-471

{"cartId":"cart-471"}
~~~

Phản hồi:

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op-471
Retry-After: 2

{"operationId":"op-471","status":"PENDING"}
~~~

Client truy vấn:

~~~http
GET /operations/op-471
~~~

Kết quả:

~~~json
{"operationId":"op-471","status":"SUCCEEDED","resourceId":"order-471"}
~~~

Nhưng nếu response 202 cũng bị mất, client có thể không biết op-471. Vì vậy cần một trong ba phương án:
- Client tự cấp operationId/business resource ID ổn định.
- Server cho phép query theo idempotency key.
- Retry cùng idempotency key để nhận lại operationId và trạng thái.

Một endpoint tra cứu chỉ bằng ID do server sinh trong response dễ bị mất vẫn chưa giải quyết toàn bộ bài toán.

### 7.1. Ý nghĩa của 404

GET status trả 404 có thể do read replica đang lag, TTL đã dọn record hoặc provider chưa index xong. Không được suy diễn “side effect chưa từng xảy ra” nếu contract không bảo đảm. Status query cần nguồn có thẩm quyền, authorization và retention đã xác định.

### 7.2. HTTP status không thay cho business status

- 200/201: thành công theo contract.
- 202: đã nhận việc, có thể chưa hoàn tất.
- 409: conflict key hoặc resource state, nên có error code rõ.
- 422: có thể diễn đạt lỗi ngữ nghĩa theo API.
- 429: throttling; không tự chứng minh thao tác trước chưa xử lý.
- 500/502/503/504: lỗi kỹ thuật, có thể tạo UNKNOWN.
- 404: chỉ có nghĩa theo contract của endpoint và nguồn dữ liệu đọc.

## 8. Thuật toán client khi mất response

~~~text
Create durable business intent + stable key
                       |
                       v
                 Send request
                 /    |    \
                v     v     v
           Success  Rejected  Timeout / Unknown
                |     |       |
                v     v       v
               Done  Done  Mark UNKNOWN
                               |
                               v
                        Query status
                        /    |     \
                       v     v      v
                    Final Pending  Unavailable
                       |     |         |
                       v     v         v
                      Done Backoff  Reconcile /
                                   same-key retry
~~~

Quy tắc:
- Lưu identity và tham số cần phục hồi trước lần gửi đầu nếu workflow quan trọng.
- Không đổi key khi retry cùng ý định.
- Ưu tiên query trạng thái trước khi retry side effect, trừ khi API cam kết retry idempotent rõ.
- Phân biệt business rejection với technical timeout.
- Có retry budget, tổng deadline, backoff và jitter.
- Không chuyển UNKNOWN thành FAILED chỉ vì hết thời gian đợi.
- Khi không thể tự xác minh, tạo tác vụ reconcile và manual review.

Một chính sách tham khảo có thể là connect timeout 500 ms, request timeout 2 giây, hai retry với backoff, tổng budget 8 giây. Các số này chỉ minh họa; phải điều chỉnh theo SLO, workload và provider contract.

### 8.1. Retry storm

Gateway retry 3 lần, Ordering retry 3 lần và Payments retry 3 lần có thể khuếch đại tải tới PSP. Nên định nghĩa tầng nào chịu trách nhiệm retry, truyền deadline, giới hạn attempts và đo retry rate. Circuit breaker có thể giảm tải nhưng không giải đáp được outcome của request cũ.

### 8.2. HTTP method không đủ để kết luận

GET thường phù hợp retry nếu thật sự chỉ đọc. PUT/DELETE có semantics idempotent về trạng thái resource khi implement đúng; POST thường cần idempotency key; PATCH tùy phép toán. Một PUT có thể vẫn gửi email trùng nếu side effect phụ không được bảo vệ. Cần xét toàn bộ hiệu ứng nghiệp vụ, không chỉ tên HTTP method.

## 9. Ví dụ Java/Spring Boot: phân loại UNKNOWN

Application contract:

~~~java
public record AuthorizePaymentCommand(
    String orderId,
    long amountMinor,
    String currency,
    String operationId
) {}

public enum PaymentOutcome {
    AUTHORIZED, REJECTED, PENDING, UNKNOWN
}

public record PaymentResult(
    PaymentOutcome outcome,
    String paymentId,
    String reasonCode
) {}

public interface PaymentPort {
    PaymentResult authorize(AuthorizePaymentCommand cmd);
    PaymentResult findByOperationId(String operationId);
}
~~~

Use case điều phối:

~~~java
public final class StartPaymentUseCase {
    private final PaymentPort payments;
    private final PaymentOperationStore operations;

    public StartPaymentUseCase(
        PaymentPort payments,
        PaymentOperationStore operations) {
        this.payments = payments;
        this.operations = operations;
    }

    public PaymentResult start(AuthorizePaymentCommand command) {
        operations.recordIntentIfAbsent(command);
        try {
            PaymentResult result = payments.authorize(command);
            operations.recordResult(command.operationId(), result);
            return result;
        } catch (PaymentTransportException ex) {
            operations.markUnknown(command.operationId());
            return new PaymentResult(
                PaymentOutcome.UNKNOWN, null, "UNCONFIRMED");
        }
    }
}
~~~

Đây là cấu trúc minh họa. Store phải thực hiện uniqueness, fingerprint, transaction và concurrent state transition; hệ thống cần reconciliation worker, retry budget và cơ chế phục hồi nếu lưu UNKNOWN thất bại. Business exception không được bắt hết rồi chuyển thành UNKNOWN.

Outbound HTTP adapter:

~~~java
public final class PaymentHttpAdapter implements PaymentPort {
    private final RestClient client;

    public PaymentHttpAdapter(RestClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(AuthorizePaymentCommand cmd) {
        return client.post()
            .uri("/authorizations")
            .header("Idempotency-Key", cmd.operationId())
            .body(new PaymentRequest(
                cmd.orderId(), cmd.amountMinor(), cmd.currency()))
            .retrieve()
            .body(PaymentResult.class);
    }

    @Override
    public PaymentResult findByOperationId(String id) {
        return client.get()
            .uri("/authorizations/by-operation/{id}", id)
            .retrieve()
            .body(PaymentResult.class);
    }
}
~~~

Ví dụ giả định API Payments có DTO tương ứng. Code production cần timeout, authentication, mapping HTTP errors, DTO transport và xác định các lỗi chưa rõ kết quả.

## 10. PSP và side effect bên ngoài

~~~text
Payments DB             Payments service              PSP
    |                          |                        |
    | Save PENDING             |                        |
    |                          | -- authorize key=K --> |
    |                          |                        | AUTHORIZED
    |                          | <-- response lost -- X  |
    |                          |                        |
    |                          v                        |
    |                        UNKNOWN                    |
~~~

Không có local DB transaction bao trùm luôn PSP. Payments cần:
1. Lưu durable intent và stable merchant reference.
2. Dùng cùng provider idempotency key nếu PSP hỗ trợ.
3. Tra cứu trạng thái bằng provider API/reference.
4. Nhận webhook có chữ ký và chống replay.
5. Deduplicate webhook và bảo vệ state transition.
6. Nếu vẫn chưa xác định, ghi RECONCILING và đặt lịch tra cứu lại.
7. Có audit/manual review khi quá hạn.

~~~text
UNKNOWN
   |
   v
Query PSP by stable reference
   |
   +-- AUTHORIZED -> Record success
   +-- REJECTED   -> Record business failure
   +-- PENDING    -> Query later
   +-- NOT FOUND / UNAVAILABLE
                       |
                       v
               Check provider semantics
                       |
                       v
               Retry inquiry with backoff
                       |
                       v
               Manual review if unresolved
~~~

NOT FOUND ở provider có thể do index chậm. Provider có thể giới hạn thời gian giữ idempotency key, nên key cache đơn thuần không thay thế unique business identity và đối soát.

## 11. Retry, reconciliation và compensation

**Retry:** gửi lại cùng ý định với stable key. Chỉ an toàn khi có contract idempotent và retry budget.

**Reconciliation:** tra cứu nguồn có thẩm quyền để biết tác dụng thực tế của yêu cầu cũ. Đây thường là bước đầu tiên khi outcome UNKNOWN.

**Compensation:** một nghiệp vụ mới xử lý hậu quả của nghiệp vụ trước: giải phóng reservation, void authorization, refund sau capture. Compensation không phải distributed SQL rollback; nó cũng có thể timeout và cần key/idempotency riêng.

Ví dụ:
- Authorize timeout → tra cứu PSP.
- PSP xác nhận AUTHORIZED nhưng đơn phải hủy → void theo policy.
- PSP đã CAPTURED → refund qua operation có identity riêng.
- Inventory đã reserve nhưng đặt hàng bị REJECTED → release.
- Release timeout → tra cứu reservation trước khi gửi lại.

Không gọi compensation vô điều kiện chỉ vì timeout khi side effect gốc chưa được xác định.

## 12. Saga và outbox có vai trò gì?

Một checkout có nhiều bước: Order(PENDING), ReserveInventory, AuthorizePayment, ConfirmOrder. Nếu ReserveInventory timeout, coordinator giữ trạng thái WAITING_INVENTORY_RECONCILIATION, không ngầm coi Inventory failed. Trong choreography, consumer/domain owner cũng phải xử lý UNKNOWN theo dữ liệu có thẩm quyền.

Transactional outbox giúp tránh local commit xong mà không publish event:

~~~text
BEGIN
  Save Order(PENDING)
  Save OutboxEvent(OrderPlaced, eventId)
COMMIT

Relay -> Broker -> Consumers
~~~

Outbox có thể phát lại event, nên consumers cần idempotency/inbox. Outbox không tự xác minh PSP đã thực hiện hay chưa. Saga phải có owner, state machine, deadline và phương án xử lý workflow treo.

## 13. Ví dụ theo nghiệp vụ

**Tạo đơn:** POST /orders timeout, DB đã có order-471. Retry cùng checkout key trả lại order-471 hoặc status, không tạo order-472.

**Giữ tồn kho:** Inventory đã giảm available cho order-471 nhưng response mất. Dùng reservation identity như orderId + sku + purpose, unique constraint và GET reservation để tra cứu. Retry không giảm tồn hai lần; release không cộng tồn hai lần.

**Thanh toán:** PSP authorize thành công, response mất. Dùng stable merchant reference, trạng thái UNKNOWN/RECONCILING, query PSP và webhook xác thực. Không tạo payment mới.

**Email:** Provider có thể đã gửi nhưng response mất. Nếu provider hỗ trợ messageId/idempotency thì dùng; nếu không, phải chấp nhận và quản lý khả năng duplicate. Không hứa exactly-once khi provider không đảm bảo.

**GET chỉ đọc:** Có thể retry dễ hơn nhưng phải giới hạn attempts và cân nhắc replica lag. GET status từ replica trả 404 không chứng minh không tồn tại.

**Refund:** Request refund timeout, PSP có thể đã hoàn tiền. Retry với reference mới có nguy cơ refund hai lần. Cần giữ refund ID cũ và reconcile.

## 14. Quan sát, bảo mật và vận hành

Dữ liệu nên lưu cho operation:
- operationId, idempotency key, tenant/merchant scope.
- Request fingerprint, resourceId và downstream reference.
- traceId/correlationId cho từng attempt.
- status, attempt count, last error.
- createdAt, deadlineAt, nextReconcileAt.
- version/sequence cho concurrent transitions.

Không log token, thẻ thanh toán hay PII không cần thiết. Status endpoint phải xác thực và kiểm tra quyền theo tenant; biết key không tự cho quyền truy cập.

Các metrics quan trọng:
- Số UNKNOWN và thời gian nằm trong trạng thái đó.
- Tỷ lệ timeout theo endpoint/downstream.
- Số operation cần manual review.
- Reconciliation success/rejection rate.
- Duplicate side effect bị chặn; số vi phạm invariant.
- Retry attempts, p95/p99 latency, queue/connection saturation.

Cần biết ai trực xử lý một operation quá deadline và nơi nào chứa dữ liệu có thẩm quyền cho từng giao dịch.

## 15. Kiểm thử fault scenarios

1. Request không tới server: retry cùng key tạo tối đa một resource.
2. Response mất sau COMMIT: client timeout nhưng retry trả lại resource cũ.
3. Hai request đồng thời cùng key trên hai pod: chỉ một side effect.
4. Cùng key, payload khác: trả conflict.
5. Crash sau CLAIMED trước side effect: worker phục hồi.
6. Crash sau PSP thực hiện nhưng trước local result: query provider, không tạo payment mới.
7. Webhook đến trễ/trùng/đảo thứ tự: state transition idempotent.
8. Status endpoint 503 hoặc replica lag: không kết luận failure.
9. Idempotency cache hết TTL: unique business constraint vẫn chặn duplicate.
10. Compensation timeout: không release/refund hai lần.
11. Retry nhiều tầng: attempts được giới hạn, không gây retry storm.
12. Quá deadline: tạo cảnh báo và manual review.

Đánh giá theo business invariant: một checkout chỉ tạo một đơn; một reservation không trừ tồn hai lần; một payment intent không capture hai lần; các trạng thái cuối không mâu thuẫn.

## 16. Hiểu lầm thường gặp

- “Timeout nghĩa là thất bại”: sai, chỉ là chưa nhận response trước deadline.
- “HTTP 500 chứng minh rollback”: sai, commit có thể đã xảy ra.
- “Retry POST tới khi 200”: nguy hiểm khi không có stable key.
- “Mỗi retry phải tạo idempotency key mới”: sai với cùng ý định.
- “Có cache Redis key là đủ”: chưa chắc do TTL, eviction, failover, race.
- “GET status 404 chứng minh chưa xử lý”: chưa chắc vì replica lag/retention.
- “Timeout thì compensation ngay”: có thể làm sai vì kết quả gốc chưa rõ.
- “Broker exactly-once cũng đảm bảo HTTP PSP exactly-once”: không đúng phạm vi.
- “Client hủy connection thì server rollback”: không chắc.

## 17. Checklist thiết kế API có side effect

- [ ] Đã xác định điểm commit và ngữ nghĩa success?
- [ ] Client giữ stable key qua mọi retry?
- [ ] Có fingerprint và scope key theo tenant/operation?
- [ ] Server dùng atomic claim hoặc unique business constraint?
- [ ] Concurrent retry chỉ tạo một side effect?
- [ ] Có status endpoint/query theo key khi response mất?
- [ ] Status query có nguồn có thẩm quyền và retention rõ?
- [ ] Timeout/5xx không bị coi ngay là business REJECTED?
- [ ] Có total deadline, retry budget, backoff và jitter?
- [ ] Provider bên ngoài hỗ trợ reference và reconciliation?
- [ ] Webhook được xác thực, deduplicate và xử lý muộn?
- [ ] Workflow UNKNOWN có owner, timer và manual review?
- [ ] Compensation có operation ID và idempotency riêng?
- [ ] Có đủ audit/metrics/traces và kiểm thử fault injection?

## 18. Bài tập tình huống

**Bài 1:** POST /orders timeout nhưng đã tạo order-471. Làm sao client retry mà không tạo order-472? Gợi ý: stable checkout key, unique constraint, trả result cũ hoặc query status.

**Bài 2:** Inventory reserve thành công, response mất. Retry làm giảm tồn thêm một lần. Nguyên nhân và cách sửa? Gợi ý: thiếu idempotent reservation business key và atomic state handling.

**Bài 3:** PSP đã AUTHORIZE nhưng response mất; webhook đến sau một phút. Backend/UI cần làm gì? Gợi ý: UNKNOWN/RECONCILING, tra cứu bằng reference cũ, không tạo intent mới.

**Bài 4:** Hai request chung key nhưng amount=100 và amount=200. Hệ thống phải xử lý thế nào? Gợi ý: request fingerprint conflict.

**Bài 5:** GET status ở replica trả 404 nhưng primary có PENDING. Có được kết luận payment chưa xảy ra? Gợi ý: không; tra cứu nguồn có thẩm quyền.

**Bài 6:** Refund timeout và coordinator định tạo refund bằng reference mới. Rủi ro là gì? Gợi ý: hoàn tiền hai lần; cần reconcile refund cũ trước.

## 19. Kết luận

Trong giao tiếp đồng bộ giữa Microservices, **mất response không phải bằng chứng thất bại nghiệp vụ**. Side effect có thể đã commit trong khi phía gọi chỉ thấy timeout, reset hoặc gateway error.

Một hệ thống đáng tin cậy cần **stable operation identity**, **idempotency key và atomic claim**, **durable operation state**, **truy vấn trạng thái có thẩm quyền**, **retry có giới hạn**, **reconciliation** và **compensation được kiểm soát**. UNKNOWN là trạng thái cần được theo dõi cho đến khi có kết luận, không phải lỗi có thể tự đổi thành FAILED.

Khi chưa biết kết quả một thao tác có side effect, hãy giữ identity cũ và xác minh trước khi tạo thao tác mới.
