# Cài đặt tác vụ bù khi thanh toán hoặc giao hàng thất bại

Trong chương **Dự án workflow nghiệp vụ**, một đơn hàng thường đi qua nhiều dịch vụ độc lập: giữ hàng trong kho, xác thực hoặc thu tiền, tạo vận đơn và cập nhật trạng thái giao hàng. Mỗi dịch vụ có database và ranh giới lỗi riêng. Nếu một bước thất bại sau khi các bước trước đã commit, không thể dùng một database rollback để đưa toàn bộ hệ thống trở lại trạng thái ban đầu. Workflow cần các tác vụ bù (compensating actions) để xử lý những thay đổi đã xảy ra.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Bài này áp dụng các nguyên tắc đó vào workflow nghiệp vụ: lưu trạng thái bền vững, điều phối các bước, retry có kiểm soát và bù những side effect đã hoàn tất khi thanh toán hoặc giao hàng không thể tiếp tục.

## 1. Bài toán workflow đặt hàng

Giả sử khách hàng đặt một đơn hàng có ba sản phẩm. Hệ thống cần thực hiện:

1. Tạo order ở trạng thái PENDING.
2. Giữ hàng trong inventory.
3. Authorize khoản thanh toán.
4. Tạo shipment và bàn giao thông tin cho đơn vị vận chuyển.
5. Capture khoản thanh toán theo chính sách nghiệp vụ.
6. Chuyển order sang trạng thái CONFIRMED hoặc FULFILLING.

Mỗi bước có thể chạy trong một service hoặc Lambda riêng. Một bước có thể commit thành công trong khi bước tiếp theo thất bại.

Ví dụ: inventory đã giữ hàng và payment đã authorize, nhưng shipping provider từ chối địa chỉ giao hàng. Nếu chỉ đánh dấu order FAILED, hàng vẫn bị giữ và hạn mức thẻ vẫn bị authorize. Workflow phải chạy các hành động bù tương ứng: void payment authorization và release inventory reservation.

~~~mermaid
flowchart TD
    A["Create order"] --> B["Reserve inventory"]
    B --> C["Authorize payment"]
    C --> D["Create shipment"]
    D --> E["Capture payment"]
    E --> F["Confirm order"]
    D -->|"Permanent failure"| X["Compensation workflow"]
    E -->|"Permanent failure"| X
    X --> V["Void shipment / cancel label"]
    V --> P["Void authorization or refund"]
    P --> I["Release inventory when safe"]
    I --> R["Mark order cancelled / needs review"]
~~~

Thứ tự bù phụ thuộc vào các bước đã thành công và trạng thái thực tế của từng hệ thống. Không chạy một danh sách compensation cố định mà không kiểm tra kết quả forward action.

## 2. Compensation là gì?

Compensation là một thao tác nghiệp vụ mới nhằm giảm hoặc đảo ngược tác động của một bước đã commit. Nó không phải rollback vật lý transaction trước đó.

Ví dụ:

- Reserve inventory → Release reservation.
- Authorize payment → Void authorization.
- Capture payment → Refund payment.
- Create shipping label → Void label nếu carrier chưa nhận kiện hàng.
- Carrier đã nhận hàng → Yêu cầu intercept/return; không thể giả định label cancellation sẽ thu hồi được kiện.
- Gửi email xác nhận → Có thể gửi email đính chính; không thể thu hồi email đã gửi.

Compensation có thể thất bại, mất thời gian hoặc chỉ khôi phục một phần. Refund có thể cần vài ngày mới xuất hiện trên sao kê. Hàng đã rời kho có thể phải chờ carrier trả lại trước khi được nhập kho.

Vì vậy, trạng thái cuối không nhất thiết là bản sao chính xác của trạng thái trước workflow. Có thể cần trạng thái REFUND_PENDING, RETURN_IN_PROGRESS hoặc MANUAL_REVIEW.

## 3. Phân biệt retry, forward recovery và compensation

Ba cách phản ứng này không thể thay thế nhau:

| Cách xử lý | Dùng khi | Ví dụ |
|---|---|---|
| Retry step | Lỗi có khả năng tạm thời, chưa cần thay đổi hướng nghiệp vụ | Payment API trả 503 |
| Forward recovery | Workflow vẫn có thể hoàn tất bằng một đường xử lý thay thế | Carrier chính lỗi, chuyển sang carrier dự phòng |
| Compensation | Không thể hoặc không nên tiếp tục; cần xử lý side effect đã commit | Địa chỉ không hợp lệ, hủy authorization và release reservation |

Không chạy compensation ngay khi gặp timeout. Timeout chỉ cho biết caller không nhận được response đúng hạn; downstream có thể đã thực hiện thao tác. Trước khi quyết định bù, cần truy vấn trạng thái bằng operation ID hoặc idempotency key nếu kết quả chưa rõ.

Một lỗi transient nên được retry trong giới hạn. Khi vượt retry budget hoặc gặp lỗi permanent, orchestrator mới quyết định tiếp tục bằng phương án khác hay bắt đầu compensation.

## 4. Lập bản đồ forward action và compensation

Mỗi bước trong saga cần có hành động chính, kết quả bền vững và hành động bù:

| Forward action | Kết quả cần lưu | Compensation | Giới hạn |
|---|---|---|---|
| Create order | orderId, version | Cancel order | Có thể giữ audit record |
| Reserve inventory | reservationId, expiry | Release reservation | Chỉ release reservation còn hiệu lực |
| Authorize payment | authorizationId | Void authorization | Có thể hết hạn hoặc provider không hỗ trợ void |
| Capture payment | captureId | Refund capture | Refund là giao dịch mới, có thể bất đồng bộ |
| Create shipment label | shipmentId, labelId | Void label | Chỉ hiệu quả trước một số mốc bàn giao |
| Carrier accepts parcel | trackingId, acceptedAt | Intercept/return request | Không bảo đảm thu hồi thành công |
| Send notification | message reference | Send correction | Không thể thu hồi notification đã nhận |

Bảng này cần được xác nhận bởi owner của từng domain. Tên action và khả năng bù phụ thuộc API của inventory, payment provider và shipping carrier.

Không dùng chung một hàm compensate() cho mọi loại bước. Mỗi compensation cần biết resource ID, trạng thái hiện tại, giới hạn nghiệp vụ và idempotency key riêng.

## 5. Saga pattern

Saga là một workflow gồm nhiều local transaction. Mỗi local transaction commit trong service của nó; nếu workflow không thể tiếp tục, saga chạy các compensation tương ứng cho những bước đã hoàn tất.

Một saga lưu ít nhất:

- Saga ID và business entity ID.
- Trạng thái workflow hiện tại.
- Kết quả của từng forward step.
- Resource ID do downstream trả về.
- Compensation status và attempt count.
- Correlation ID và idempotency key.
- Deadline, retry policy và thời điểm cập nhật.
- Lỗi cuối và trạng thái cần can thiệp.

Saga không tạo distributed ACID transaction. Nó quản lý tiến trình và trạng thái phục hồi qua nhiều transaction độc lập.

### 5.1. Orchestration và choreography

Có hai cách tổ chức saga:

| Kiểu | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Orchestration | Một orchestrator lưu state và gọi từng participant | Workflow có nhánh, timeout, compensation và audit rõ |
| Choreography | Service phát event, service khác phản ứng và phát event tiếp | Luồng ít bước, coupling thấp và dễ biểu diễn bằng event |

Orchestration giúp xác định chính xác bước nào đã hoàn tất và bước nào cần bù. Choreography giảm sự phụ thuộc vào một coordinator nhưng có thể khó theo dõi khi có nhiều nhánh và compensation.

Với workflow thanh toán và giao hàng có nhiều side effect, một orchestrator thường giúp vận hành và điều tra rõ hơn. Các service participant vẫn giữ quyền sở hữu dữ liệu và transaction của mình.

## 6. Thiết kế state machine cho workflow

Một state machine minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> INVENTORY_RESERVED
    INVENTORY_RESERVED --> PAYMENT_AUTHORIZED
    PAYMENT_AUTHORIZED --> SHIPMENT_CREATED
    SHIPMENT_CREATED --> PAYMENT_CAPTURED
    PAYMENT_CAPTURED --> CONFIRMED
    INVENTORY_RESERVED --> COMPENSATING: Payment failed
    PAYMENT_AUTHORIZED --> COMPENSATING: Shipping failed
    SHIPMENT_CREATED --> COMPENSATING: Capture failed
    COMPENSATING --> CANCELLED: Compensation complete
    COMPENSATING --> MANUAL_REVIEW: Compensation failed
    CONFIRMED --> [*]
    CANCELLED --> [*]
~~~

Các trạng thái chính:

- PENDING: workflow được tạo.
- INVENTORY_RESERVED: reservation đã commit.
- PAYMENT_AUTHORIZED: provider đã xác nhận authorization.
- SHIPMENT_CREATED: shipment hoặc label đã được tạo.
- PAYMENT_CAPTURED: khoản thanh toán đã capture.
- CONFIRMED: forward workflow hoàn tất.
- COMPENSATING: đang chạy một hoặc nhiều hành động bù.
- CANCELLED: các compensation bắt buộc đã hoàn tất.
- MANUAL_REVIEW: không thể tự động phục hồi an toàn.

State machine thật có thể cần thêm trạng thái như PAYMENT_UNKNOWN, SHIPMENT_ACCEPTED, REFUND_PENDING hoặc RETURN_IN_PROGRESS. Không ép mọi kết quả vào SUCCESS/FAILED nếu downstream có trạng thái trung gian.

## 7. Xác định compensation theo điểm thất bại

Một workflow chỉ bù những forward action đã thành công hoặc có khả năng đã thành công. Ví dụ:

| Điểm lỗi | Các bước đã hoàn tất | Hành động tiếp theo |
|---|---|---|
| Reserve inventory thất bại | Create order | Hủy order hoặc đánh dấu không thể xử lý |
| Authorize payment thất bại | Create order, reserve inventory | Release reservation, hủy order |
| Create shipment thất bại | Reserve inventory, authorize payment | Void authorization, release reservation |
| Capture payment thất bại chắc chắn | Reserve, authorize, shipment label | Void label nếu còn được phép, void authorization, release inventory khi an toàn |
| Capture timeout, kết quả chưa rõ | Các bước trước và capture request | Query provider bằng idempotency key trước khi retry hoặc bù |
| Carrier từ chối sau khi nhận kiện | Inventory, payment, shipment handoff | Intercept/return, refund theo policy, chỉ restock khi hàng được xác nhận trả về |

Nếu một bước chưa từng thành công, không cần compensation cho bước đó. Nếu kết quả không rõ, trước hết phải reconcile trạng thái thực tế.

## 8. Bù theo thứ tự ngược

Trong một saga tuần tự, compensation thường chạy theo thứ tự ngược của các forward action đã commit. Nếu đã reserve inventory, authorize payment và tạo shipment label, thì khi capture thất bại, workflow có thể:

1. Void shipment label nếu carrier chưa nhận kiện.
2. Void payment authorization nếu chưa capture.
3. Release inventory reservation.
4. Cập nhật order thành CANCELLED hoặc NEEDS_REVIEW.

Thứ tự ngược giúp giảm phụ thuộc vào resource đã tạo. Tuy nhiên, thứ tự bù thực tế phải theo domain. Ví dụ, không release inventory nếu carrier đã nhận hàng và sản phẩm chưa quay lại kho.

Với các bước song song, không có một thứ tự ngược tuyến tính duy nhất. Orchestrator cần chờ các nhánh đã hoàn tất, sau đó chạy compensation cho từng nhánh theo dependency graph.

## 9. Phân biệt authorization, capture và refund

Thanh toán thường có nhiều trạng thái:

- **Authorize:** provider kiểm tra và giữ hạn mức; chưa nhất thiết chuyển tiền.
- **Capture:** yêu cầu thu tiền dựa trên authorization.
- **Void:** hủy authorization chưa capture hoặc hủy giao dịch theo khả năng provider.
- **Refund:** hoàn lại khoản đã capture; đây là một giao dịch mới.

Nếu shipping thất bại trước capture, void authorization có thể phù hợp. Nếu capture đã thành công, cần refund. Không gọi void cho một khoản đã capture nếu provider không hỗ trợ semantics đó.

Refund có thể ở trạng thái PENDING, SUCCEEDED hoặc FAILED. Order chỉ nên chuyển sang trạng thái phù hợp với kết quả refund; không đánh dấu REFUNDED ngay khi gửi request.

Mọi payment request cần operation ID và idempotency key ổn định. Khi timeout, query provider trước khi gửi một thao tác mới có thể tạo charge hoặc refund trùng.

## 10. Phân biệt tạo label và bàn giao cho carrier

Shipping cũng có nhiều mốc:

1. Tạo shipment record.
2. Mua hoặc tạo shipping label.
3. Đặt lịch pickup.
4. Carrier scan và nhận kiện.
5. Kiện đang vận chuyển.
6. Giao thành công hoặc thất bại.

Void label trước khi carrier nhận kiện có thể là compensation đơn giản. Sau khi carrier đã nhận, hành động bù có thể là intercept, return-to-sender hoặc tạo yêu cầu trả hàng. Không thể giả định một API cancel sẽ dừng kiện hàng đang vận chuyển.

Inventory cũng phải được bù theo trạng thái vật lý. Nếu hàng đã rời kho, chỉ release reservation không đủ; cần quy trình return và kiểm tra hàng trước khi cộng lại available stock.

## 11. Durable saga state

Không giữ saga state trong biến static hoặc memory của Lambda. Execution environment có thể bị thay thế, nhiều invocation có thể chạy đồng thời và retry có thể tới một instance khác.

Một bảng saga có thể chứa:

~~~sql
CREATE TABLE business_saga (
    saga_id          VARCHAR(120) PRIMARY KEY,
    order_id         VARCHAR(120) NOT NULL,
    state            VARCHAR(40) NOT NULL,
    current_step     VARCHAR(80),
    version          BIGINT NOT NULL,
    context_json     JSONB NOT NULL,
    last_error_code  VARCHAR(120),
    created_at       TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL
);
~~~

Bảng step riêng:

~~~sql
CREATE TABLE saga_step (
    saga_id          VARCHAR(120) NOT NULL,
    step_name        VARCHAR(80) NOT NULL,
    status           VARCHAR(40) NOT NULL,
    operation_id     VARCHAR(160),
    resource_id      VARCHAR(160),
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    last_error_code  VARCHAR(120),
    updated_at       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (saga_id, step_name)
);
~~~

Có thể dùng một bảng cho cả forward step và compensation, nhưng cần phân biệt action type và trạng thái. Không ghi toàn bộ dữ liệu thanh toán nhạy cảm vào context_json; chỉ lưu token/reference cần thiết và có quyền truy cập phù hợp.

Mỗi state transition cần optimistic locking hoặc conditional update để hai invocation không cùng điều phối saga từ một version cũ.

## 12. Idempotency cho forward action và compensation

Một compensation có thể được retry nếu response bị mất hoặc worker crash. Vì vậy compensation cũng phải idempotent.

Ví dụ key:

- Forward reserve: sagaId + reserve-inventory.
- Compensation release: sagaId + release-inventory.
- Forward authorize: sagaId + authorize-payment.
- Compensation void: sagaId + void-authorization.
- Compensation refund: sagaId + refund-capture.

Không dùng cùng key cho forward action và compensation vì chúng là hai operation khác nhau.

Nếu inventory release được gọi hai lần, lần thứ hai phải trả về kết quả đã xử lý hoặc xác nhận reservation đã được giải phóng. Nếu refund request bị retry, provider phải nhận cùng idempotency key để không tạo hai refund.

Ở database nội bộ, dùng unique constraint/conditional write. Với external provider, dùng idempotency feature của API nếu có và lưu provider operation reference.

## 13. Transactional outbox và inbox trong saga

Một participant thường phải vừa cập nhật local state vừa phát event tiếp theo. Nếu commit database xong nhưng publish thất bại, saga có thể bị treo.

Transactional outbox giải quyết dual-write:

1. Trong một transaction, cập nhật local business state và insert outbox event.
2. Commit.
3. Publisher gửi event.
4. Consumer nhận event và dùng inbox/idempotency để chống duplicate.
5. Orchestrator cập nhật saga state dựa trên kết quả đã commit.

Outbox publisher có thể gửi lặp sau crash. Consumer vẫn cần idempotency. Không đánh dấu step thành SUCCEEDED chỉ vì message được publish; phải dựa trên kết quả của participant hoặc event xác nhận.

## 14. Compensation failure và trạng thái cần can thiệp

Compensation cũng có thể thất bại:

- Payment provider tạm thời unavailable.
- Void authorization bị từ chối vì đã capture.
- Refund bị pending hoặc provider trả lỗi.
- Shipping carrier không thể intercept.
- Inventory service không tìm thấy reservation.
- Reservation đã hết hạn trước khi release.

Không được chuyển saga thành CANCELLED nếu các compensation bắt buộc chưa hoàn tất hoặc chưa được xử lý theo policy. Dùng trạng thái COMPENSATION_PENDING, COMPENSATION_FAILED hoặc MANUAL_REVIEW.

Một recovery worker có thể quét saga bị kẹt, kiểm tra lease/deadline và tiếp tục compensation. Cần giới hạn retry, backoff, alert và runbook cho nhóm vận hành.

Nếu compensation không thể tự động hoàn tất, giữ trạng thái có thể truy vết và tạo task cho nhân viên. Không xóa saga record sau khi lỗi.

## 15. Timeout và kết quả không rõ

Timeout là tình huống khó vì caller không biết downstream đã commit hay chưa.

Ví dụ payment capture:

1. Lambda gửi capture request với key K.
2. Payment provider capture thành công.
3. Response bị mất.
4. Lambda timeout.
5. Saga không biết capture thành công hay thất bại.

Hành động an toàn:

- Không lập tức gửi capture mới với key khác.
- Query provider theo authorization/capture reference hoặc idempotency key.
- Nếu capture thành công, ghi nhận PAYMENT_CAPTURED và tiếp tục.
- Nếu provider xác nhận chưa capture, retry cùng operation/key theo policy.
- Nếu trạng thái vẫn không rõ, giữ PAYMENT_UNKNOWN và đưa vào reconciliation.

Không chạy refund chỉ vì capture timeout. Nếu capture thực tế chưa xảy ra, refund không có giao dịch nguồn; nếu capture đã xảy ra, cần xác minh số tiền và reference trước khi refund.

## 16. Orchestrator bằng AWS Step Functions

AWS Step Functions có thể điều phối các bước Lambda/service, lưu execution state, áp dụng Retry/Catch và gọi nhánh compensation.

Một workflow khái niệm:

~~~mermaid
flowchart TD
    START["Start order saga"] --> INV["Reserve inventory"]
    INV --> PAY["Authorize payment"]
    PAY --> SHIP["Create shipment"]
    SHIP --> CAP["Capture payment"]
    CAP --> DONE["Confirm order"]
    INV -->|"Failure"| FAIL["Handle failure"]
    PAY -->|"Failure"| REL["Release inventory"]
    SHIP -->|"Failure"| VOID["Void authorization"]
    VOID --> REL
    CAP -->|"Failure"| CANCELSHIP["Cancel label or request intercept"]
    CANCELSHIP --> VOID2["Void authorization"]
    VOID2 --> REL
    REL --> CANCEL["Mark cancelled / review"]
    FAIL --> CANCEL
~~~

Trong Step Functions, có thể dùng:

- Task state cho Lambda hoặc service integration.
- Retry cho lỗi transient có giới hạn.
- Catch để chuyển sang nhánh compensation.
- Choice để rẽ nhánh theo business result.
- Wait cho backoff hoặc chờ callback.
- Map/Parallel khi có các bước độc lập.
- Execution history để điều tra tiến trình.

Step Functions lưu trạng thái orchestration nhưng không tự làm cho side effect bên ngoài idempotent. Mỗi Task cần operation key ổn định và phải xử lý trường hợp Task thành công nhưng state transition chưa được ghi nhận do timeout hoặc retry.

### 16.1. Retry và Catch phải phân biệt lỗi

Không dùng Retry cho mọi exception. Ví dụ:

- ThrottlingException, service unavailable hoặc lỗi mạng: retry có backoff.
- InvalidAddress hoặc PaymentDeclined: thường là business failure, chuyển sang compensation.
- AccessDenied: sửa quyền, cảnh báo; không retry liên tục.
- Timeout với kết quả chưa rõ: query trạng thái operation trước khi quyết định.

Catch có thể chuyển sang compensation state, nhưng nhánh đó cần biết những bước nào thực sự đã commit. Execution input/output nên chứa resource references và step status bền vững.

## 17. Orchestration bằng Java

Nếu dùng Java orchestrator riêng, nên mô hình hóa từng step và compensation rõ ràng thay vì viết một chuỗi try/catch dài.

~~~java
public interface SagaStep<C> {
    String name();

    StepResult execute(C context);

    CompensationResult compensate(C context);
}
~~~

Một orchestrator có thể:

1. Đọc saga state và version.
2. Claim quyền điều phối bằng lease/conditional update.
3. Chọn step tiếp theo.
4. Ghi trạng thái RUNNING và operation ID.
5. Gọi participant với idempotency key.
6. Ghi kết quả thành công hoặc failure.
7. Nếu terminal failure, chuyển state sang COMPENSATING.
8. Chạy compensation cho các step đã thành công theo thứ tự dependency.
9. Ghi trạng thái hoàn tất hoặc MANUAL_REVIEW.

Không giữ database transaction mở trong khi gọi HTTP tới participant. Ghi intent/operation trước, gọi bên ngoài, rồi ghi kết quả bằng transaction riêng; participant phải idempotent để xử lý crash giữa các bước.

## 18. Java model cho step và compensation

Một model đơn giản:

~~~java
public enum StepStatus {
    PENDING,
    RUNNING,
    SUCCEEDED,
    RETRY_WAIT,
    FAILED,
    COMPENSATING,
    COMPENSATED,
    MANUAL_REVIEW
}

public record StepExecution(
        String sagaId,
        String stepName,
        String operationId,
        String resourceId,
        StepStatus status,
        int attempts) {
}
~~~

Compensation cần nhận resource ID được tạo bởi forward action. Ví dụ releaseInventory cần reservationId; voidAuthorization cần authorizationId; refund cần captureId và amount.

Không dựng resource ID bằng cách đoán từ orderId nếu provider trả reference riêng. Lưu response/reference ngay sau khi xác nhận operation thành công.

## 19. Ví dụ Java compensation cho payment

~~~java
public interface PaymentGateway {
    AuthorizationResult authorize(
            String orderId,
            long amountMinor,
            String idempotencyKey);

    VoidResult voidAuthorization(
            String authorizationId,
            String idempotencyKey);

    RefundResult refund(
            String captureId,
            long amountMinor,
            String idempotencyKey);

    PaymentStatus findAuthorization(String authorizationId);
}
~~~

Ví dụ service bù authorization:

~~~java
public CompensationResult voidPaymentAuthorization(
        SagaContext context,
        String authorizationId) {

    String key = context.sagaId() + ":void-authorization";

    PaymentStatus current =
            paymentGateway.findAuthorization(authorizationId);

    if (current.isVoided()) {
        return CompensationResult.ALREADY_COMPLETED;
    }

    if (current.isCaptured()) {
        return CompensationResult.REFUND_REQUIRED;
    }

    if (current.isVoidPending()) {
        return CompensationResult.PENDING_CONFIRMATION;
    }

    VoidResult result =
            paymentGateway.voidAuthorization(authorizationId, key);

    if (result.isCompleted()) {
        return CompensationResult.COMPLETED;
    }

    if (result.isAccepted()) {
        return CompensationResult.PENDING_CONFIRMATION;
    }

    return CompensationResult.RETRY_REQUIRED;
}
~~~

Đây là pseudocode; API provider thực tế có thể không hỗ trợ query theo authorization ID hoặc trả trạng thái khác. Khi đó cần dùng reference và reconciliation endpoint được provider cung cấp. Chỉ đánh dấu COMPLETED khi provider xác nhận void đã hoàn tất. HTTP 202 thường chỉ cho biết yêu cầu đã được tiếp nhận, vì vậy phải giữ PENDING_CONFIRMATION và kiểm tra trạng thái sau đó. Nếu authorization đã capture, chuyển sang quy trình refund thay vì cố void.

## 20. Ví dụ compensation cho inventory và shipping

Inventory release:

~~~java
public CompensationResult releaseReservation(
        SagaContext context,
        String reservationId) {

    String key = context.sagaId() + ":release-inventory";

    InventoryResult result =
            inventory.release(reservationId, key);

    return switch (result.status()) {
        case RELEASED, ALREADY_RELEASED ->
                CompensationResult.COMPLETED;
        case TEMPORARY_FAILURE ->
                CompensationResult.RETRY_REQUIRED;
        case NOT_FOUND ->
                CompensationResult.NEEDS_REVIEW;
    };
}
~~~

Shipping cancellation cần kiểm tra trạng thái carrier:

~~~java
public CompensationResult cancelShipment(
        SagaContext context,
        String shipmentId) {

    ShipmentStatus status = shipping.find(shipmentId);

    if (status.isLabelCreated() && !status.isCarrierAccepted()) {
        return shipping.voidLabel(
                shipmentId,
                context.sagaId() + ":void-label");
    }

    if (status.isCarrierAccepted()) {
        return shipping.requestInterceptOrReturn(
                shipmentId,
                context.sagaId() + ":intercept-shipment");
    }

    return CompensationResult.NEEDS_REVIEW;
}
~~~

Các method và enum chỉ là abstraction. Thực tế carrier có thể không hỗ trợ intercept, hoặc yêu cầu phí và approval. Không release stock ngay khi gửi return request; chờ hàng được xác nhận quay về và kiểm tra tình trạng.

## 21. Compensation cho workflow có bước song song

Một đơn hàng có thể giữ hàng từ nhiều kho hoặc tạo shipment cho nhiều package. Nếu các nhánh chạy song song, một số nhánh thành công và nhánh khác thất bại.

Orchestrator cần:

- Lưu kết quả riêng cho từng branch/package.
- Chỉ bù resource đã được tạo thành công.
- Không bù nhánh đang có kết quả chưa rõ trước khi query trạng thái.
- Giới hạn concurrency của compensation để không quá tải downstream.
- Chờ compensation bắt buộc hoàn tất hoặc đưa nhánh lỗi vào MANUAL_REVIEW.
- Tổng hợp trạng thái order theo kết quả của tất cả nhánh.

Nếu một package đã giao thành công và package khác thất bại, không thể tự động refund toàn bộ và release toàn bộ inventory. Cần partial fulfillment/partial refund policy.

## 22. Race giữa cancellation, timeout và callback

Một khách hàng có thể hủy order đúng lúc payment callback hoặc shipping event đến. Các workflow cạnh tranh có thể cùng cố cập nhật trạng thái.

Dùng:

- Saga version và optimistic locking.
- Conditional state transition.
- Idempotency key theo action.
- Unique constraint cho external event ID.
- Explicit terminal state policy.
- Reconciliation khi kết quả bên ngoài không rõ.

Ví dụ, nếu order đã chuyển sang CANCELLING, callback PaymentCaptured không nên tự chuyển order thành CONFIRMED. Callback cần được ghi nhận và chuyển sang nhánh refund/compensation phù hợp.

Không để một event callback đến muộn ghi đè state machine hiện tại chỉ vì nó được xử lý sau cùng.

## 23. Observability cho saga và compensation

Mỗi log/trace cần liên kết:

- sagaId.
- orderId hoặc business key.
- stepName và actionType.
- operationId/idempotencyKey reference.
- resourceId như reservationId, authorizationId, shipmentId.
- attempt và retry delay.
- compensation status.
- correlationId/causationId.
- failure category và downstream response class.

Metric nên theo dõi:

- Saga đang chạy theo state.
- Saga quá deadline.
- Compensation pending/failed.
- Retry count theo step.
- Payment UNKNOWN và REFUND_PENDING.
- Shipment intercept/return pending.
- Inventory reservation sắp hết hạn.
- Manual review backlog.
- Thời gian từ failure đến compensation complete.

Không ghi payment token, card data hoặc secret vào log. Không dùng sagaId/orderId làm metric dimension có cardinality cao; giữ chúng trong log và trace.

## 24. Kiểm thử compensation

Bộ test phải bao phủ forward success, failure và compensation failure.

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| SAGA-01 | Reserve inventory thất bại | Không gọi payment; order bị từ chối theo policy |
| SAGA-02 | Payment authorization bị decline | Release reservation |
| SAGA-03 | Shipping provider từ chối trước khi tạo label | Void authorization, release reservation |
| SAGA-04 | Capture thất bại chắc chắn | Void/cancel shipment nếu còn khả thi, void authorization, release stock theo policy |
| SAGA-05 | Capture timeout nhưng thực tế thành công | Query provider, ghi nhận capture, không capture lần hai |
| SAGA-06 | Refund tạm thời thất bại | Giữ REFUND_PENDING, retry có giới hạn |
| SAGA-07 | Compensation được giao lặp | Một compensation effect logic |
| SAGA-08 | Worker crash sau compensation success trước khi ghi state | Retry không lặp side effect |
| SAGA-09 | Carrier đã nhận kiện | Dùng intercept/return flow, không chỉ void label |
| SAGA-10 | Compensation không thể hoàn tất | MANUAL_REVIEW và alert |
| SAGA-11 | Customer cancel cạnh tranh payment callback | Conditional transition giữ state nhất quán |
| SAGA-12 | Hai branch shipment, một thành công một thất bại | Chỉ bù branch phù hợp theo partial fulfillment policy |

Test cần kiểm tra state database và trạng thái provider stub. Chỉ xác minh orchestrator đi tới nhánh Catch không chứng minh payment đã void hoặc inventory đã release.

## 25. Failure injection và test doubles

Dùng WireMock hoặc stub server để mô phỏng payment/shipping:

- 503 trong hai lần đầu, sau đó 200.
- 429 kèm Retry-After.
- Timeout sau khi ghi nhận operation.
- Response 202 rồi trạng thái chuyển thành SUCCEEDED sau đó.
- 400/403 permanent failure.
- Connection reset sau khi server nhận request.

Dùng Testcontainers cho database để kiểm tra transaction, unique constraint và optimistic locking. Có thể dùng LocalStack để thử một số integration AWS, nhưng cần test cloud riêng cho Step Functions, IAM, callback và semantics dịch vụ mà local emulator không mô phỏng đầy đủ.

Tạo fault hook ở các điểm:

1. Sau khi ghi saga state.
2. Sau khi participant commit nhưng trước khi response tới orchestrator.
3. Sau khi ghi compensation result ở provider nhưng trước khi saga state cập nhật.
4. Trong lúc retry.
5. Khi lease của orchestrator hết hạn.
6. Khi callback đến trễ hoặc lặp.

## 26. Runbook khi compensation thất bại

Một runbook cần xác định:

1. Tìm saga theo sagaId/orderId.
2. Xem forward steps đã commit và resource references.
3. Xác định compensation nào đang pending/failed.
4. Query trạng thái thực tế ở payment, inventory và shipping provider.
5. Phân loại transient, permanent hay ambiguous outcome.
6. Kiểm tra idempotency key trước khi gửi lại action.
7. Retry compensation an toàn hoặc tạo manual task.
8. Cập nhật saga state bằng conditional transition.
9. Đối soát order, payment, inventory và shipment.
10. Lưu audit và đóng incident khi business state đã được xác minh.

Không chạy script bù hàng loạt mà không kiểm tra resource status. Một lệnh refund lặp có thể gây hoàn tiền hai lần; release reservation có thể ảnh hưởng đơn hàng đã được tái phân bổ.

## 27. Bảo mật và quyền truy cập

Mỗi participant chỉ nên có quyền cần thiết:

- Inventory Lambda chỉ reserve/release đúng inventory scope.
- Payment Lambda chỉ authorize/void/refund qua credential được quản lý.
- Shipping Lambda chỉ tạo/cancel/intercept shipment theo quyền.
- Orchestrator chỉ gọi task và đọc/ghi saga state cần thiết.
- Operator có quyền manual compensation phải được audit.

Không đưa card data hoặc credential vào Step Functions input/output hay saga context. Dùng token/reference từ payment provider và secret manager. Bảo vệ execution history vì nó có thể chứa business identifiers và lỗi downstream.

Tách quyền khởi chạy compensation thủ công khỏi quyền xem dữ liệu nhạy cảm khi phù hợp. Một người có thể cần điều phối recovery nhưng không cần đọc toàn bộ payment details.

## 28. Chi phí và giới hạn vận hành

Chi phí của workflow gồm:

- Step Functions state transitions/executions.
- Lambda invocation và duration.
- Queue/event bus requests.
- Database read/write và saga state storage.
- Payment/shipping API calls.
- Retry và compensation attempts.
- Logs, traces và audit storage.

Compensation kéo dài có thể tốn nhiều hơn forward path vì cần retry và reconciliation. Đặt deadline, retry budget và alert cho saga bị kẹt. Không giữ một Lambda invocation mở trong nhiều phút chỉ để chờ carrier hoặc refund; lưu trạng thái và tiếp tục bằng event/callback hoặc scheduled worker.

Cần giới hạn concurrency của compensation. Khi một downstream phục hồi, hàng nghìn saga có thể cùng retry; gradual ramp-up và rate limiter bảo vệ quota của provider.

## 29. Những lỗi thường gặp

**Coi compensation là database rollback:** Side effect ở service khác không thể rollback bằng transaction local. Thiết kế action nghiệp vụ riêng.

**Compensate ngay khi timeout:** Downstream có thể đã commit. Query trạng thái bằng operation reference trước.

**Bù mọi bước theo danh sách cố định:** Một số bước chưa thành công hoặc đã qua mốc không thể đảo ngược. Dựa trên step status và resource state.

**Release inventory sau khi carrier đã nhận hàng:** Có thể bán lại hàng vẫn đang vận chuyển. Chỉ restock khi hàng được trả và kiểm tra.

**Refund ngay sau khi capture timeout:** Capture có thể chưa xảy ra hoặc đã thành công. Reconcile trước khi quyết định.

**Retry compensation không idempotent:** Có thể tạo refund hoặc release lặp. Dùng key riêng cho từng compensation.

**Đánh dấu CANCELLED khi compensation còn pending:** Trạng thái nghiệp vụ gây hiểu nhầm. Dùng REFUND_PENDING, RETURN_IN_PROGRESS hoặc MANUAL_REVIEW.

**Giữ saga state trong Lambda memory:** State mất khi environment bị thay thế. Lưu bền vững và dùng optimistic locking.

**Không có outbox/inbox:** Event có thể mất hoặc được xử lý lặp. Dùng transactional outbox và consumer idempotency.

**Không xử lý callback đến muộn:** Callback có thể ghi đè trạng thái cancellation. Dùng conditional state transition.

**Không có manual recovery:** Compensation có thể thất bại vĩnh viễn. Cần runbook, audit và owner.

## 30. Checklist production

- [ ] Mỗi forward step có trạng thái và resource reference bền vững.
- [ ] Mỗi side effect có idempotency key ổn định.
- [ ] Mỗi forward step có compensation hoặc lý do rõ ràng không thể bù tự động.
- [ ] Compensation chỉ chạy cho action đã thành công hoặc đã xác minh.
- [ ] Compensation chạy theo dependency/reverse order phù hợp.
- [ ] Timeout/ambiguous outcome được query trước khi retry hoặc bù.
- [ ] Payment authorization, capture, void và refund được phân biệt.
- [ ] Shipment label, carrier acceptance, intercept và return được phân biệt.
- [ ] Inventory chỉ được restock khi trạng thái vật lý cho phép.
- [ ] Saga state được lưu bền vững và cập nhật bằng version/conditional write.
- [ ] Outbox/inbox bảo vệ event delivery và duplicate.
- [ ] Retry có backoff, jitter, max attempts và deadline.
- [ ] Compensation failure có trạng thái pending/failed/manual review.
- [ ] Parallel branch có policy partial success và compensation riêng.
- [ ] Cancellation và callback cạnh tranh được kiểm soát.
- [ ] Metrics theo dõi saga age, compensation backlog và manual review.
- [ ] Log không chứa card data, secret hoặc token.
- [ ] Có integration test và fault injection cho crash windows.
- [ ] Có runbook và quyền manual compensation được audit.
- [ ] Có giới hạn concurrency/rate để không gây bão retry khi provider phục hồi.

## Kết luận

Tác vụ bù giúp workflow nghiệp vụ phục hồi khi một bước sau thất bại sau khi các bước trước đã commit. Với thanh toán và giao hàng, cần phân biệt authorize, capture, void, refund, tạo label, carrier acceptance và return; mỗi hành động có giới hạn và trạng thái riêng. Compensation là một thao tác nghiệp vụ mới, có thể bất đồng bộ hoặc cần can thiệp thủ công.

Một saga đáng tin cậy lưu state bền vững, biết chính xác forward step nào đã thành công, dùng idempotency cho cả forward action lẫn compensation và kiểm tra kết quả không rõ trước khi retry. Orchestrator có thể dùng Java hoặc Step Functions, nhưng không thay thế transaction local, outbox/inbox và conditional state transition của từng participant. Khi test bao phủ crash window, duplicate, timeout, compensation failure và recovery, hệ thống có thể xử lý lỗi thanh toán/giao hàng mà vẫn giữ trạng thái order, payment và inventory nhất quán.

