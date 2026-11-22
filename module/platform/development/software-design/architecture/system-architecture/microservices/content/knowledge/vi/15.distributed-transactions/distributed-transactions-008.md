# Phục hồi saga sau lỗi và quản lý tiến trình kéo dài

## 1. Bài toán: một nghiệp vụ trải qua nhiều giao dịch cục bộ

Trong kiến trúc microservices, một nghiệp vụ có thể liên quan nhiều dịch vụ, mỗi dịch vụ sở hữu database và transaction riêng. Ví dụ người dùng đặt hàng trên hệ thống thương mại điện tử:

1. Order Service ghi nhận đơn hàng.
2. Inventory Service giữ hàng.
3. Payment Service thực hiện hoặc xác minh thanh toán.
4. Shipping Service chuẩn bị vận chuyển.
5. Notification Service gửi thông báo.

Không thể mặc định cả chuỗi được bảo vệ bởi một transaction ACID duy nhất. Order đã commit nhưng Payment có thể timeout; Inventory đã giữ hàng nhưng service điều phối bị restart; sự kiện PaymentSucceeded có thể đến muộn sau khi hệ thống đã bắt đầu hủy đơn.

**Saga** là mẫu thiết kế điều phối chuỗi **giao dịch cục bộ** và các **hành động bù trừ (compensating actions)** khi cần phục hồi hoặc đi theo nhánh không thành công. Saga không làm các database độc lập trở thành một transaction nguyên tử toàn cục. Thay vào đó, hệ thống lưu trạng thái và quản lý tiến độ sao cho các bước có thể tiếp tục, thử lại an toàn, hủy theo nghiệp vụ hoặc đưa vào đối soát khi chưa biết kết quả.

Bài học này tập trung vào vấn đề thường khó hơn việc vẽ sơ đồ Saga: **khi một bước lỗi, timeout, nhận trùng event hoặc process bị chết, làm cách nào hệ thống biết phải làm tiếp điều gì và không đánh mất nghĩa vụ nghiệp vụ?**

Các nội dung chính:

- Phân biệt lỗi kỹ thuật, thất bại nghiệp vụ và trạng thái chưa xác định.
- Xác định ai sở hữu tiến trình Saga, deadline và kết quả cuối.
- Lưu bền vững state machine, step execution, timer và operation ID.
- Phục hồi sau crash ở ranh giới giữa commit, publish, ACK và side effect bên ngoài.
- Thiết kế retry, idempotency, compensation, reconciliation và manual intervention.
- Quản lý Saga kéo dài qua nhiều phút, giờ hoặc ngày.
- Kiểm thử lỗi bằng failure matrix, fault injection và quan sát production.

## 2. Saga khác transaction cục bộ và distributed transaction thế nào?

### 2.1. Transaction cục bộ

Một transaction SQL trong Order Service có thể đảm bảo tạo order header và order lines atomically:

~~~sql
BEGIN;

INSERT INTO orders(order_id, status)
VALUES ('O-8421', 'PENDING');

INSERT INTO order_items(order_id, sku, quantity)
VALUES ('O-8421', 'SKU-1', 2);

COMMIT;
~~~

Nếu một câu lệnh lỗi trước COMMIT, database có thể rollback cả transaction theo cơ chế của engine. Nhưng transaction này **không tự bao gồm** việc Inventory Service giữ hàng hoặc Payment Provider thu tiền.

### 2.2. Distributed transaction / two-phase commit

Một số kiến trúc sử dụng giao thức transaction phân tán như two-phase commit (2PC) để phối hợp nhiều resource tham gia một commit chung. Giải pháp này có yêu cầu cụ thể về tài nguyên, coordinator, availability và failure handling; không phải mọi broker, REST API hoặc payment provider đều có thể tham gia.

Trong microservices có nhiều hệ thống và external API, việc cố dùng một transaction khóa tài nguyên xuyên nhiều service có thể gây coupling, latency và rủi ro vận hành lớn.

### 2.3. Saga

Saga chia nghiệp vụ thành các giao dịch cục bộ:

~~~text
T1: Tạo đơn ở trạng thái PENDING
T2: Giữ hàng
T3: Khởi tạo / xác nhận thanh toán
T4: Chốt đơn CONFIRMED

Nếu T3 thất bại rõ ràng:
C2: Giải phóng giữ hàng
C1: Hủy đơn hoặc chuyển trạng thái phù hợp
~~~

T và C là **tác vụ nghiệp vụ**, không phải các câu lệnh rollback tự động. Việc “giải phóng hàng” có thể tự là một request bất đồng bộ, bị timeout hoặc cần retry. “Hoàn tiền” là một giao dịch riêng, không xóa sự thật rằng tiền từng được thu.

**Điểm quan trọng:** Saga không bắt buộc mọi bước đều có hành động bù trừ hoàn hảo. Có những bước không thể đảo ngược (gửi email, giao hàng đã giao, thanh toán đã settle), khi đó cần chính sách xử lý khác, như refund, return, manual review hoặc chấp nhận một trạng thái ngoại lệ đã được kiểm soát.

## 3. Hai kiểu phối hợp Saga: orchestration và choreography

### 3.1. Orchestration

Một **Saga orchestrator / process manager** giữ trạng thái toàn quy trình và gửi command tới các dịch vụ:

~~~mermaid
flowchart LR
    U["Client"] --> O["Order Saga Orchestrator"]
    O --> I["Inventory Service"]
    O --> P["Payment Service"]
    O --> S["Shipping Service"]
    O --> D[("Saga State Store")]
~~~

Orchestrator biết bước hiện tại, kết quả đã ghi nhận, lần thử lại và bước tiếp theo. Nó có thể được triển khai bằng code, workflow engine hoặc một service chuyên điều phối.

**Ưu điểm:** trạng thái và đường xử lý dễ nhìn; dễ đặt timer, điều phối bù trừ, phát cảnh báo và thực thi chính sách business deadline.

**Trade-off:** orchestrator có thể trở thành điểm coupling hoặc điểm nghẽn nếu thiết kế không tốt; bản thân nó phải có storage bền vững, khả năng failover và bảo vệ concurrency. Không được chỉ giữ trạng thái Saga trong bộ nhớ của một instance.

### 3.2. Choreography

Các dịch vụ phát/nhận event; bước sau phản ứng theo trạng thái đã xảy ra:

~~~mermaid
flowchart LR
    O["OrderCreated"] --> I["Inventory Service"]
    I --> IR["InventoryReserved"]
    IR --> P["Payment Service"]
    P --> PR["PaymentSucceeded"]
    PR --> OC["OrderConfirmed"]
~~~

**Ưu điểm:** các service có thể ít phụ thuộc trực tiếp vào một coordinator; luồng event tận dụng hệ thống messaging.

**Trade-off:** nếu sự kiện bị trễ, mất do cấu hình hoặc xử lý lỗi, rất khó biết ai đang chịu trách nhiệm đưa đơn tới kết cục cuối. Quy trình càng dài, nhiều nhánh bù trừ và timer thì logic phân tán càng khó hiểu.

Choreography **không có nghĩa không cần owner**. Cần xác định service sở hữu trạng thái order, service nào tìm các operation pending quá hạn, và ai có quyền yêu cầu compensation.

### 3.3. Chọn thế nào?

| Tiêu chí | Orchestration | Choreography |
| --- | --- | --- |
| Quy trình nhiều bước và nhiều nhánh | Dễ hình dung tại một nơi | Dễ phân tán logic |
| Timer, timeout, escalation | Thường tập trung | Cần quy ước owner rõ |
| Quan sát end-to-end | Có một saga state làm mốc | Cần correlation và projection tổng hợp |
| Coupling | Coordinator biết contract các bước | Consumer biết event contract |
| Thêm consumer độc lập | Có thể qua event bên ngoài | Tự nhiên với event |
| Bù trừ phức tạp | Thường dễ quản lý hơn | Dễ thành vòng event khó theo dõi |
| Rủi ro | Coordinator phải bền vững, scale tốt | Workflow owner mơ hồ, event chain khó debug |

Không có lựa chọn tuyệt đối. Một hệ thống có thể dùng **orchestrator cho core transaction** và phát domain events cho notification/analytics.

## 4. Phân loại thất bại trước khi quyết định retry hay bù trừ

Không thể dùng một nhánh catch(Exception) để quyết định mọi Saga đều phải rollback.

| Loại tình huống | Ví dụ | Điều biết chắc | Cách xử lý ưu tiên |
| --- | --- | --- | --- |
| Business failure rõ | Inventory báo OUT_OF_STOCK | Không thể giữ hàng theo yêu cầu | Chạy nhánh từ chối/bù trừ |
| Validation failure | Payment amount sai định dạng | Command không hợp lệ | Sửa logic/dữ liệu, không retry mù |
| Transient technical failure | Service tạm 503 | Có thể phục hồi | Retry có giới hạn nếu an toàn |
| Timeout sau gửi command | Payment chưa phản hồi | **Chưa biết** đã xử lý hay chưa | Query status/idempotency/reconciliation |
| Process crash | Orchestrator chết khi chờ event | State phải còn trong store | Restart và resume từ state bền vững |
| Duplicate delivery | Broker giao lại PaymentSucceeded | Event lặp | Idempotent transition |
| Out-of-order event | Failed đến sau Success | Trật thứ tự | Version/state guard và policy |
| Permanent infrastructure issue | Sai credentials/cấu hình | Retry nhanh không sửa được | Alert, pause, sửa rồi resume |
| Business deadline expired | Hết hạn giữ hàng | Quy tắc nghiệp vụ kết thúc thời gian | Expiration/compensation theo state |
| Compensation failure | Release inventory timeout | Bù trừ chưa chắc thành công | Retry/query/escalation, không báo đã hủy xong |

**Timeout không phải bằng chứng một bước đã thất bại về mặt nghiệp vụ.** Một Saga có thể phải đi qua trạng thái UNKNOWN hoặc WAITING_CONFIRMATION thay vì chuyển ngay sang COMPENSATING.

## 5. Quyền sở hữu tiến trình và kết quả cuối

Mỗi bước có owner cục bộ, nhưng toàn bộ Saga phải có **workflow owner**.

Ví dụ:

| Thành phần | Dữ liệu/kết quả sở hữu |
| --- | --- |
| Order Service | Order aggregate, trạng thái đơn và các bất biến của đơn |
| Inventory Service | Reservation, stock movement, expiration |
| Payment Service | Payment intent, charge/refund trạng thái |
| Shipping Service | Shipment order, carrier response, trạng thái vận chuyển |
| Saga Orchestrator | Tiến độ, step outcomes, timers, retry/compensation state, kết quả workflow |
| Reconciliation Worker | Thực hiện kiểm tra các operation chưa rõ, theo quyền đã giao |
| Ops/Support | Xử lý trường hợp không thể tự động xác minh |

Saga owner không được tự tuyên bố payment thành công chỉ vì đã gửi command. Nó nhận kết quả **từ nguồn có thẩm quyền** và quyết định transition của workflow theo invariant.

Cần phân biệt:

- **Technical response deadline:** client chờ lời gọi trong bao lâu.
- **Step timeout:** một command được chờ/phải có phản hồi trong bao lâu.
- **Business expiration:** reservation/giá/offer có hiệu lực tới khi nào.
- **Workflow completion deadline:** một Saga được phép pending bao lâu trước khi phải retry/escalate.
- **Operational escalation deadline:** khi nào phải báo người trực và manual review.

Những thời hạn này không nhất thiết giống nhau. HTTP request timeout sau 3 giây không tự làm Saga 10 phút ngừng tồn tại.

## 6. Mô hình Saga state machine bền vững

Một Saga không nên chỉ có một biến boolean success. Với các bước phân tán, nên định nghĩa trạng thái rõ:

- NEW: chưa bắt đầu.
- RUNNING: đang có công việc cần tiến hành.
- WAITING: chờ sự kiện/kết quả theo một operation ID.
- RETRY_SCHEDULED: đã quyết định thử lại khi đến hạn.
- CONFIRMATION_REQUIRED: kết quả side effect chưa chắc chắn.
- COMPENSATING: đang thực hiện các hành động bù trừ.
- COMPLETED: nghiệp vụ đạt kết quả cuối thành công.
- COMPENSATED: những bù trừ cần thiết đã được xác nhận theo policy.
- FAILED_TERMINAL: kết thúc với thất bại nghiệp vụ đã xử lý và không còn nghĩa vụ xử lý theo workflow hiện tại.
- NEEDS_MANUAL_REVIEW: chưa thể tự động chốt, cần owner và quy trình hỗ trợ.

Tên gọi chỉ là ví dụ. Cần định nghĩa chính xác thế nào là terminal state. Một Saga bị “không thể hoàn tất” nhưng vẫn còn khoản tiền chưa xác minh **không nên** được đánh dấu là đã bù trừ hoàn toàn.

### 6.1. Sơ đồ trạng thái minh họa

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> RUNNING: Persist saga & start
    RUNNING --> WAITING: Send command / await outcome
    WAITING --> RUNNING: Step succeeded
    WAITING --> RETRY_SCHEDULED: Transient error
    RETRY_SCHEDULED --> WAITING: Retry same operation
    WAITING --> CONFIRMATION_REQUIRED: Ambiguous timeout
    CONFIRMATION_REQUIRED --> RUNNING: Outcome verified success
    CONFIRMATION_REQUIRED --> COMPENSATING: Outcome verified failure
    RUNNING --> COMPENSATING: Business rejection
    COMPENSATING --> COMPENSATED: Compensations verified
    COMPENSATING --> NEEDS_MANUAL_REVIEW: Cannot reconcile
    CONFIRMATION_REQUIRED --> NEEDS_MANUAL_REVIEW: Exceeds reconciliation policy
    RUNNING --> COMPLETED: All required steps confirmed
    COMPLETED --> [*]
    COMPENSATED --> [*]
~~~

Một state machine production có thể có nhiều sub-states theo mỗi bước, cancel requested, expiry và late event handling. Sơ đồ phải gắn với business invariants thay vì dựa vào việc “đã nhận event X”.

### 6.2. Mỗi transition phải có guard

Một event PaymentSucceeded đến hai lần không được làm đơn CONFIRMED hai lần với hai side effects. Một timer hết hạn đến sau khi đơn hoàn thành không được ghi đè COMPLETED thành FAILED.

Với database quan hệ, có thể bảo vệ bằng optimistic locking:

~~~sql
UPDATE sagas
SET state = 'WAITING_PAYMENT',
    version = version + 1,
    updated_at = now()
WHERE saga_id = 'S-8421'
  AND version = 7
  AND state = 'WAITING_INVENTORY';
~~~

Nếu affected rows = 0, handler phải đọc state mới và xem transition còn hợp lệ không. Không được bỏ version check rồi overwrite theo thứ tự event đến.

## 7. Saga cần lưu những dữ liệu gì?

Một mô hình bền vững tối thiểu có thể gồm ba nhóm: Saga instance, step execution và event/timer metadata.

~~~sql
CREATE TABLE saga_instances (
    saga_id TEXT PRIMARY KEY,
    business_key TEXT NOT NULL UNIQUE,
    saga_type TEXT NOT NULL,
    state TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    current_step TEXT,
    business_deadline_at TIMESTAMPTZ,
    next_action_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    last_error_code TEXT
);

CREATE TABLE saga_steps (
    saga_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    confirmed_at TIMESTAMPTZ,
    result_reference TEXT,
    PRIMARY KEY (saga_id, step_name),
    UNIQUE(operation_id)
);

CREATE TABLE saga_inbox (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Đây là schema minh họa. Một Saga có thể thực hiện cùng tên bước nhiều lần trong một workflow (ví dụ shipment retry khác operation); khi đó primary key cần có **step instance ID** hoặc attempt/sequence đúng domain, không dùng duy nhất (saga_id, step_name).

Các trường cần lưu:

- sagaId và businessKey ổn định để chống tạo Saga trùng.
- Saga type và **definition version** khi workflow có thể thay đổi trong quá trình chạy.
- State hiện tại và version để kiểm soát concurrency.
- Step name/instance ID/operationId, kết quả đã xác minh và timestamp.
- Retry count, nextActionAt, deadline và thông tin lỗi đủ để phục hồi.
- Reference tới paymentId, reservationId, shipmentId, không nhất thiết sao chép toàn bộ dữ liệu nhạy cảm.
- Thông tin bù trừ đã chạy/đang chờ và business outcome.
- Audit trail hoặc event history theo nhu cầu giải thích và compliance.

**Không nên lưu mật khẩu, token, dữ liệu thẻ hoặc toàn bộ payload nhạy cảm vào Saga state** chỉ vì muốn dễ debug. Lưu reference và metadata cần thiết, mã hóa và phân quyền các trường nhạy cảm nếu bắt buộc.

### 7.1. Vì sao cần definition version?

Một Saga có thể bắt đầu hôm nay nhưng kết thúc ngày mai, trong khi ứng dụng được deploy một phiên bản code mới. Nếu quy trình đã đổi thứ tự hoặc nghĩa của bước, resume bằng code mới có thể đi nhầm nhánh.

Có thể lưu sagaDefinitionVersion và xây chính sách migration/completion cho instance cũ. Không bắt buộc giữ mọi version vĩnh viễn, nhưng phải có **chiến lược tương thích cho Saga đang chạy**.

## 8. Đừng giữ tiến độ chỉ trong bộ nhớ hoặc call stack

Anti-pattern:

~~~text
POST /checkout
  reserveInventory()
  chargePayment()
  scheduleShipment()
  return success
~~~

Nếu process chết sau reserveInventory() nhưng trước chargePayment(), hệ thống không có bản ghi biết đơn đã giữ hàng mà còn cần tiếp tục. Một retry từ client có thể bắt đầu một quy trình mới và giữ thêm hàng.

Tốt hơn:

1. Ghi Saga instance và operation ID bền vững.
2. Ghi ý định gửi command vào outbox khi cần.
3. Worker xử lý step theo state đã commit.
4. Khi nhận kết quả, ghi state transition và outbox event trong transaction.
5. Sau restart, worker quét những Saga RUNNING/WAITING/RETRY_SCHEDULED đến hạn và tiếp tục.

**Một request HTTP không phải nơi sở hữu tuổi thọ của một workflow kéo dài.** Client đóng tab, Gateway timeout hoặc một instance restart không làm mất nghĩa vụ hoàn tất hoặc đối soát.

## 9. Khởi tạo Saga an toàn với idempotency

Nếu client gửi POST /orders rồi mất kết nối trước khi nhận operationId, client có thể retry. Hệ thống cần tránh tạo hai đơn và hai Saga.

Ví dụ:

~~~http
POST /v1/orders
Idempotency-Key: checkout-session-8421
Content-Type: application/json

{
  "cartId": "CART-17",
  "paymentMethodId": "PM-Token"
}
~~~

Order Service cần lưu khóa idempotency trong phạm vi tài khoản/tenant cùng kết quả tiếp nhận. Trong một transaction cục bộ, có thể tạo Order PENDING, Saga instance và outbox record. Cùng key và payload được gửi lại phải trả lại operationId/đơn đã tồn tại hoặc trạng thái hiện tại theo contract.

Nếu dùng cùng key nhưng payload khác (ví dụ amount hoặc cart khác), phải trả conflict theo chính sách, không âm thầm coi là cùng một yêu cầu.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Order API
    participant D as Database
    C->>O: POST order, idempotency key K
    O->>D: Transaction: check K, persist order+saga+outbox
    D-->>O: Commit, operationId=S-8421
    O--xC: Response lost
    C->>O: Retry same key K
    O->>D: Lookup K
    D-->>O: Existing operationId=S-8421
    O-->>C: Return existing operation/status
~~~

Khóa idempotency phải gắn với **ý định nghiệp vụ**, không phải UUID ngẫu nhiên được tạo mới cho mỗi network attempt.

## 10. Transactional Outbox: không đánh mất command sau commit

Một lỗi rất thường gặp:

~~~text
1. COMMIT Saga state = WAITING_INVENTORY
2. Publish ReserveInventory command
3. Process crash giữa 1 và 2
~~~

Saga đang chờ Inventory nhưng command chưa được gửi. Nếu không có cơ chế phục hồi, workflow mắc kẹt vô thời hạn.

**Transactional Outbox** lưu state transition và một record chứa ý định phát command/event trong cùng transaction với Saga state:

~~~sql
BEGIN;

UPDATE saga_instances
SET state = 'WAITING',
    current_step = 'RESERVE_INVENTORY',
    version = version + 1
WHERE saga_id = 'S-8421'
  AND version = 0;

INSERT INTO outbox (
    event_id, event_type, aggregate_id, payload, created_at
)
VALUES (
    'cmd-reserve-8421',
    'ReserveInventory',
    'S-8421',
    '{"sagaId":"S-8421","operationId":"reserve-8421"}',
    now()
);

COMMIT;
~~~

Publisher đọc outbox và chuyển đến broker hoặc API theo cơ chế đã thiết kế. Sau publish thành công nhưng trước khi đánh dấu sent, publisher có thể crash và **gửi lại**. Vì vậy service nhận phải xử lý command idempotent.

### 10.1. Inbox ở bên nhận

Inventory Service có thể lưu commandId/operationId trong database của nó, cùng transaction với việc tạo reservation:

~~~text
Receive ReserveInventory(operationId)
BEGIN Inventory DB
  Check / insert unique operationId
  If already processed: return stored outcome
  Else validate available quantity
       create reservation atomically
       persist outcome
COMMIT
Emit InventoryReserved or InventoryRejected
~~~

Nếu ACK của message bị mất, replay cùng operationId không tạo reservation thứ hai. Chỉ một header chứa idempotency key **không** tự làm logic trở nên idempotent; storage phía nhận phải bảo vệ concurrency.

### 10.2. Outbox không bảo đảm publish đúng một lần

Một outbox publisher thường có at-least-once publication. Kết quả chính xác về mặt nghiệp vụ đến từ **identity ổn định, local transactions, business constraints và idempotent consumers**. Không nên tuyên bố Outbox biến cả Saga thành một transaction duy nhất.

## 11. Phục hồi Saga sau process crash

Khi orchestrator restart, nó không được đơn giản chạy lại toàn bộ steps từ đầu.

### 11.1. Quy trình resume

1. Load Saga state và version từ storage bền vững.
2. Xác định current step, last confirmed outcome và những command đã ghi outbox.
3. Kiểm tra timer/nextActionAt và business deadline.
4. Nếu step chưa gửi nhưng outbox còn pending, tiếp tục publish.
5. Nếu step đã gửi nhưng kết quả chưa rõ, **query state bên owner** hoặc retry cùng operationId khi contract cho phép.
6. Nếu step thành công đã xác minh, tiến sang step kế tiếp với guarded transition.
7. Nếu business failure rõ, lập kế hoạch compensation phù hợp.
8. Nếu không thể xác minh, chuyển vào trạng thái reconciliation/manual review và cảnh báo.
9. Ghi audit/tracing/metrics cho hoạt động phục hồi.

### 11.2. Các điểm chết có khả năng xảy ra

| Điểm crash | Dữ liệu đã có | Recovery hợp lý |
| --- | --- | --- |
| Trước khi Saga được lưu | Chưa tạo Saga | Client retry bằng cùng idempotency key |
| Sau khi lưu Saga trước publish | Saga/outbox đã commit | Outbox publisher phát sau restart |
| Sau publish trước mark-sent | Broker có thể đã nhận | Publish lại cùng commandId; recipient dedup |
| Sau Inventory commit trước response | Reservation có thể đã tạo | Query theo reservationId/operationId |
| Sau Saga nhận event trước state commit | Event có thể được giao lại | Inbox/state transaction xử lý lại an toàn |
| Sau state commit trước broker ACK | State mới đã lưu | Redelivery thấy inbox marker và no-op |
| Sau compensation thành công trước xác nhận | Bù trừ có thể đã diễn ra | Query hoặc retry cùng compensation ID |
| Trong manual review | Chưa đạt kết quả tự động | Người có quyền xử lý theo audit/runbook |

**Tái khởi động chỉ nên tiếp tục từ state đã lưu**, kết hợp xác minh các side effects chưa rõ. Không dùng trạng thái trên memory trước crash làm bằng chứng đã commit.

## 12. Nhận event trùng, muộn hoặc sai thứ tự

Một Saga có thể nhận:

~~~text
InventoryReserved(saga=S-8421,eventId=E10)
InventoryReserved(saga=S-8421,eventId=E10)   // redelivery
PaymentFailed(saga=S-8421,eventId=E12)
PaymentSucceeded(saga=S-8421,eventId=E11)    // late
~~~

Nếu cứ xử lý theo thứ tự nhận, hệ thống có thể vừa chuyển COMPENSATING vừa chuyển COMPLETED, hoặc bù trừ sai.

### 12.1. Dedup theo eventId

Một inbox marker giúp chặn cùng eventId bị áp dụng lại:

~~~sql
BEGIN;

INSERT INTO saga_inbox(consumer_name,event_id)
VALUES ('order-saga', 'E10')
ON CONFLICT DO NOTHING;

-- Nếu đã tồn tại, no-op. Nếu mới, kiểm tra state/version và update.

COMMIT;
~~~

Marker và state update cần **cùng transaction**. Nếu ghi marker trước rồi crash trước business state update, lần redelivery có thể bị bỏ qua và workflow mắc kẹt.

### 12.2. Idempotency theo business operation

Hai eventId khác nhau vẫn có thể mô tả cùng operation. Vì vậy Saga còn cần paymentId, reservationId hoặc step instance ID ổn định để tránh chấp nhận hai kết quả mâu thuẫn cho cùng command.

### 12.3. Guard theo state/version

Saga chỉ nên chấp nhận PaymentSucceeded nếu trạng thái hiện tại và các điều kiện nghiệp vụ cho phép. Khi event tới sau timeout/expiry, cần **late-result policy**, không mặc định bỏ qua hoặc chốt thành công.

Ví dụ:

- Saga đang WAITING_PAYMENT: lưu success và kiểm tra Inventory còn hợp lệ.
- Saga đang COMPENSATING: ghi nhận late success và quyết định hoàn tiền/điều tra.
- Saga đã COMPENSATED: tạo quy trình refund hoặc xử lý ngoại lệ mới khi cần, không âm thầm đảo lịch sử.
- Saga COMPLETED: event duplicate là no-op; event mâu thuẫn cần audit/escalation.

**“At-least-once delivery” là điều kiện vận hành bình thường**, vì vậy duplicate, retry và reordering phải nằm trong thiết kế từ đầu.

## 13. Timeout: chờ kết quả không phải kết luận kết quả

Ví dụ Payment Service nhận ChargePayment, gửi lệnh tới provider và đã thu tiền. Response bị mất, Saga chờ hết hạn 2 giây.

Saga biết:

- Chưa nhận confirmation đúng hạn.
- Không biết provider đã xử lý hay chưa.
- Không được tạo paymentId mới để thử lại cùng ý định.
- Không được lập tức chạy refund nếu chưa có bằng chứng tồn tại charge, trừ khi policy và provider API cho phép thao tác bù trừ idempotent trên một operation đã biết.

Một luồng phù hợp:

~~~mermaid
flowchart TD
    A["Payment command sent"] --> B{"Response received?"}
    B -- "Success confirmed" --> C["Record success and continue"]
    B -- "Definitive business failure" --> D["Plan compensation"]
    B -- "Timeout / connection lost" --> E["PAYMENT_OUTCOME_UNKNOWN"]
    E --> F["Query provider / payment service using same operationId"]
    F --> G{"Authoritative outcome?"}
    G -- "Succeeded" --> C
    G -- "Failed" --> D
    G -- "Still unknown" --> H["Schedule bounded reconciliation"]
    H --> F
    H --> I["Escalate when policy exceeded"]
~~~

Trạng thái UNKNOWN/PENDING_CONFIRMATION có thể kéo dài hơn deadline HTTP nhưng phải có **thời hạn kiểm tra tiếp, owner và escalation**. Không để Saga ở WAITING vô hạn chỉ vì một callback không đến.

## 14. Retry phải có giới hạn và dùng lại cùng operation

Một lỗi 503 ngắn có thể phục hồi sau retry, nhưng retry không được làm hệ thống quá tải thêm.

Chính sách retry cần:

- Xác định lỗi có khả năng tạm thời.
- Số attempt tối đa hoặc retry budget.
- Exponential backoff và jitter.
- Overall workflow/step deadline.
- Cùng idempotency key cho cùng business operation.
- Giới hạn concurrency và queue.
- Không để gateway, SDK và Saga worker cùng retry độc lập quá nhiều lần.
- Chuyển sang reconciliation/manual review khi retry không còn hợp lý.

Công thức minh họa:

~~~text
rawDelay = min(maxDelay, baseDelay × 2^(attempt - 1))
wait = random(0, rawDelay)    // full jitter example
~~~

Không có một cấu hình chung phù hợp mọi hệ thống. Một API kiểm tra trạng thái có thể retry khác với lệnh charge tiền hoặc release inventory.

### 14.1. Retry amplification

Nếu orchestrator retry 3 lần, SDK downstream retry 3 lần và proxy cũng retry 3 lần, một business operation có thể bị gọi tới 27 lần trong tình huống xấu. Hãy xác định tầng sở hữu retry và giới hạn tổng.

### 14.2. Retry không an toàn thì phải hỏi trạng thái

Nếu thao tác có side effect nhưng không có idempotency contract, retry mù có nguy cơ làm lặp tác dụng. Trong những tình huống này, Saga nên query authoritative status, giữ pending và escalate thay vì tự động tạo thao tác mới.

### 14.3. Retry exhaustion không phải terminal failure mặc định

Một bước retry hết 5 lần không đồng nghĩa nghiệp vụ chắc chắn FAILED. Nếu kết quả chưa rõ, trạng thái đúng có thể là NEEDS_RECONCILIATION; nếu thất bại đã được xác minh thì chuyển sang COMPENSATING.

## 15. Compensation: bù trừ là một nghiệp vụ mới

Saga thường được mô tả:

~~~text
T1 -> T2 -> T3
Nếu T3 lỗi:
C2 -> C1
~~~

Trong thực tế, C2 và C1 không phải rollback của transaction T2/T1. Chúng là **các giao dịch cục bộ mới**, phải có ID, state, retry, deadline và cách phục hồi riêng.

Ví dụ:

- T2: giữ 2 sản phẩm (InventoryReserved).
- C2: giải phóng reservation (InventoryReleased).
- T3: charge 250.000 VND (PaymentSucceeded).
- C3: refund 250.000 VND (RefundSucceeded).

Một refund có thể mất vài ngày hoặc có trạng thái processing theo provider. Không được xóa PaymentSucceeded khỏi lịch sử như thể tiền chưa từng được thu.

### 15.1. Bù trừ thường theo thứ tự ngược nhưng không tuyệt đối

Nếu các bước T1, T2, T3 có phụ thuộc và side effects, compensation thường được thực hiện theo thứ tự ngược để giảm xung đột. Nhưng tùy nghiệp vụ, một số compensation có thể song song hoặc có điều kiện.

Ví dụ nếu email đã gửi, không có lệnh “thu hồi email” đáng tin. Có thể gửi email sửa thông tin nhưng đó là side effect khác. Nếu hàng đã bàn giao đơn vị vận chuyển, việc hủy có thể trở thành return process.

### 15.2. Compensation cần idempotency

Một ReleaseReservation có thể bị gửi hai lần do response mất. Inventory phải hiểu cùng compensation operation và không cộng stock lại hai lần.

~~~json
{
  "sagaId": "S-8421",
  "operationId": "release-reservation-8421",
  "reservationId": "R-8421",
  "reason": "PAYMENT_DECLINED"
}
~~~

Một commandId ổn định qua retry và một constraint theo reservation state giúp tránh giải phóng trùng.

### 15.3. Bù trừ có thể thất bại

Nếu release inventory gặp lỗi database, Saga không thể ghi COMPENSATED một cách lạc quan. Nó phải giữ COMPENSATING, có lịch retry/query và điều kiện escalation. Một Saga “đã hủy” trong UI có thể vẫn cần hiển thị “đang hoàn tiền” nếu refund là workflow khác chưa xong.

## 16. Phân loại thao tác dễ/khó bù trừ

| Thao tác | Bù trừ khả dĩ | Giới hạn |
| --- | --- | --- |
| Giữ tồn kho | Release reservation | Phải tránh release trùng hoặc sau khi đã giao |
| Đặt chỗ tạm | Cancel reservation | Có thể bị phí/hết hạn theo provider |
| Tạo đơn PENDING | Mark CANCELLED | Không xóa audit hoặc các side effects khác |
| Charge tiền | Refund | Refund không đồng nghĩa charge chưa từng xảy ra |
| Gửi email | Gửi email sửa/đính chính | Không thể xóa email đã đến hộp thư |
| Tạo shipment label | Cancel label | Có thể không hủy được sau handover |
| Cấp quyền truy cập | Revoke permission | Có thể đã có sử dụng trước revoke |
| Chuyển dữ liệu sang hệ ngoài | Gửi yêu cầu xóa/điều chỉnh | Có thể bị retention/compliance hạn chế |

Thiết kế workflow cần phân loại các bước:

1. **Compensatable:** có một hành động bù trừ tương ứng.
2. **Retryable:** có thể thử lại an toàn với idempotency.
3. **Pivot / irreversible:** sau một thời điểm, workflow phải tiến tiếp hoặc xử lý ngoại lệ, không thể quay về trạng thái ban đầu đơn giản.

Các thuật ngữ này mô tả tư duy thiết kế, không phải mọi use case đều phải hiện thực theo một công thức duy nhất.

## 17. Tiến trình kéo dài: phút, giờ và ngày

Một số nghiệp vụ không thể hoàn tất trong request-response:

- Thanh toán chờ đối soát hoặc xác nhận thủ công.
- Duyệt khoản vay qua nhiều bộ phận.
- Đặt chuyến đi với nhiều bên cung cấp.
- Yêu cầu hoàn tiền, đổi trả hàng.
- Quy trình onboarding khách hàng doanh nghiệp.
- Tạo báo cáo lớn, import dữ liệu hoặc xử lý video.
- Xử lý giao hàng và chứng từ theo từng mốc thời gian.

Với các Saga này, phải tách:

- **HTTP response deadline**: client chờ bao lâu.
- **Business deadline**: tác vụ còn có nghĩa tới khi nào.
- **Step SLA/timeout**: chờ một bên bao lâu trước khi điều tra.
- **Escalation SLA**: khi nào cần con người can thiệp.
- **Retention**: giữ workflow state và audit bao lâu.

Không nên giữ một HTTP connection mở hàng giờ. Có thể trả **202 Accepted + operationId + status URL**, sau đó cập nhật bằng polling, webhook, SSE/WebSocket hoặc event, tùy sản phẩm. Kênh thông báo không thay thế persistent state.

### 17.1. Ví dụ API cho long-running Saga

~~~http
POST /v1/checkouts
Idempotency-Key: checkout-8421
Content-Type: application/json

{"cartId":"C-8421","paymentMethodId":"PM-17"}
~~~

Phản hồi khi đã lưu bền vững operation:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/S-8421
Retry-After: 3
Content-Type: application/json

{
  "operationId": "S-8421",
  "status": "WAITING_PAYMENT",
  "terminal": false,
  "statusUrl": "/v1/operations/S-8421"
}
~~~

Sau đó client gọi GET /v1/operations/S-8421 để biết tiến độ và kết quả cuối.

**Không trả 202 nếu Gateway không có bằng chứng operation đã được nhận/lưu**. Một timeout không rõ request đã tới server hay chưa cần được xử lý theo idempotency/status lookup contract, không tự tuyên bố đã tiếp nhận.

### 17.2. Mẫu status response

~~~json
{
  "operationId": "S-8421",
  "orderId": "O-8421",
  "status": "NEEDS_RECONCILIATION",
  "terminal": false,
  "currentStep": "VERIFY_PAYMENT",
  "lastUpdatedAt": "2026-11-11T10:46:00Z",
  "nextSuggestedPollSeconds": 10
}
~~~

Không gửi stack trace, token, thông tin thẻ hoặc internal host trong public status. OperationId không thay thế authentication/authorization. Một user không được truy vấn trạng thái đơn của user khác chỉ nhờ đoán ID.

## 18. Durable timers và scheduler

Saga kéo dài thường cần các timer:

- Kiểm tra payment status sau 30 giây.
- Hết hạn reservation sau một khoảng thời gian nghiệp vụ.
- Nhắc người duyệt sau một ngày.
- Đẩy sang manual review nếu chưa xác minh trong thời hạn.
- Chạy lại compensation sau lỗi tạm thời.

**Một timer trong RAM của một instance không phải durable timer**. Instance restart có thể làm mất callback. Có thể lưu nextActionAt trong database hoặc dùng workflow/timer service hỗ trợ persistence.

### 18.1. Scheduler quét trạng thái đến hạn

~~~text
Every polling interval:
  find sagas where next_action_at <= now()
    and state in (WAITING, RETRY_SCHEDULED,
                  CONFIRMATION_REQUIRED, COMPENSATING)
  claim a bounded batch
  process each claimed saga idempotently
  update state and next_action_at in transaction
~~~

Worker có thể dùng lease/claim row/lock thích hợp và đặt giới hạn số job đang xử lý. Thời gian hệ thống giữa các node cần được đồng bộ và thao tác duration nên dùng đồng hồ phù hợp. Không hứa timer sẽ fire đúng tuyệt đối tại một thời điểm nếu scheduler có lag.

### 18.2. Timer có thể chạy lại hoặc chạy muộn

Một scheduler có thể dispatch cùng job hai lần khi mất acknowledgment hoặc failover. Worker phải đọc state mới và kiểm tra guard. Nếu Saga đã COMPLETED trước lúc timer hết hạn chạy, timer xử lý no-op. Nếu payment vừa thành công, timer không tự ghi FAILED dựa trên snapshot cũ.

### 18.3. Business expiry khác retry delay

Reservation hết hạn lúc 10:15 là quy tắc domain. Retry delay 10 giây chỉ là lịch kỹ thuật. Không kéo dài reservation đơn thuần vì retry được thực hiện muộn; muốn gia hạn cần một thao tác nghiệp vụ có thẩm quyền và kiểm tra availability.

## 19. Multiple workers, lease và fencing

Nếu hai instance cùng khôi phục Saga S-8421, chúng có thể gửi hai command hoặc ghi state đè nhau. Cần giới hạn ownership tại thời điểm xử lý.

Các cơ chế có thể kết hợp:

- **Optimistic locking** trên saga.version.
- **Database row lock** trong transaction ngắn khi cập nhật state.
- **Lease** với thời hạn, owner ID, khả năng claim lại sau crash.
- **Fencing token / generation** để một worker cũ không ghi sau khi lease đã thuộc worker mới.
- **Idempotency ở step recipient** làm hàng phòng thủ cuối.

### 19.1. Vì sao lease một mình chưa đủ?

Worker A giữ lease, bị pause lâu. Lease hết hạn, Worker B nhận quyền xử lý. Sau đó A thức dậy và vẫn cố gửi một command hoặc ghi state.

Nếu chỉ nhìn biến local, cả A và B có thể hành động. Version/fencing giúp phát hiện A đã lỗi thời. Tuy nhiên với external side effect, chỉ có DB fencing ở orchestrator **không bảo đảm** bên ngoài không nhận hai request; vẫn cần cùng operationId/idempotency key phía nhận.

### 19.2. Claim batch an toàn

Trong PostgreSQL, có thể dùng cơ chế khóa dòng và SKIP LOCKED cho một hàng công việc phù hợp:

~~~sql
BEGIN;

SELECT saga_id
FROM saga_instances
WHERE next_action_at <= now()
  AND state IN ('RETRY_SCHEDULED', 'COMPENSATING')
ORDER BY next_action_at
FOR UPDATE SKIP LOCKED
LIMIT 50;

-- Claim/assign lease hoặc update các rows đã chọn.
COMMIT;
~~~

Đây là phác thảo, không phải SQL hoàn chỉnh cho toàn bộ claiming. Trong production, cần lưu owner/lease expiry/fencing generation, giới hạn transaction duration và xử lý retry khi database unavailable.

## 20. Orchestrator restart không nên làm lặp side effect

Một ví dụ failure matrix cụ thể:

~~~text
Saga S-8421:
  currentStep = CHARGE_PAYMENT
  operationId = pay-8421-1
  state = WAITING_PAYMENT
~~~

Process A gửi ChargePayment. Payment Service commit thành công rồi response mất. A crash. Process B nhận Saga và muốn tiếp tục.

**Hành vi không an toàn:** B tạo paymentId mới pay-8421-2, gửi charge lần nữa.

**Hành vi an toàn hơn:** B dùng paymentId cũ pay-8421-1 để:

1. Query Payment Service theo operationId.
2. Nếu Payment đã SUCCEEDED, ghi nhận state và tiếp tục.
3. Nếu Payment FAILED rõ, chuyển sang compensation.
4. Nếu Payment PENDING, đặt timer kiểm tra lại.
5. Nếu không biết và provider hỗ trợ idempotency, retry cùng key theo policy.
6. Nếu không thể xác minh, escalate; không tuyên bố giao dịch thất bại để tạo charge mới.

Từ đây thấy Saga recovery cần **persistent business identity**, không chỉ một biến currentStep.

## 21. Reconciliation: đóng khoảng trống sau timeout

**Reconciliation** là quy trình đối chiếu trạng thái nội bộ với nguồn có thẩm quyền khác để xử lý trường hợp chưa rõ.

Ví dụ Payment Service có payment P-8421 ở trạng thái UNKNOWN. Provider có thể có API tra cứu transaction hoặc batch settlement report. Reconciliation worker có thể:

1. Lấy danh sách payment chưa xác minh quá một ngưỡng.
2. Query provider bằng stable operation/provider reference.
3. Xác minh dữ liệu: amount, currency, merchant, status, reference.
4. So sánh với state đã lưu.
5. Áp dụng transition hợp lệ, idempotent.
6. Phát event PaymentSucceeded/Failed nếu có thay đổi đã commit.
7. Ghi audit, owner và thời điểm đối soát.
8. Nếu không có kết quả chắc chắn, giữ pending hoặc chuyển manual review.

Không nên tự suy ra payment FAILED chỉ vì provider tạm không trả kết quả. Trường hợp xung đột giữa callback và query response phải được xử lý theo **contract, version và mức độ tin cậy của nguồn**.

### 21.1. Đối soát nhiều lớp

Có thể cần:

- Reconciliation Saga ↔ từng step owner.
- Payment Service ↔ payment provider.
- Inventory Service ↔ reservation state.
- Order Service ↔ các kết quả đã xác minh.
- Ledger ↔ giao dịch thực tế/kế toán khi nghiệp vụ yêu cầu.

Mỗi lớp có dữ liệu authoritative khác nhau. Không để orchestrator tự sửa record của Payment Service khi chưa có quyền và bằng chứng.

### 21.2. Manual review là trạng thái có ownership

Một record NEEDS_MANUAL_REVIEW nên có:

- Business ID, sagaId, step/operationId.
- Lý do không thể tự động xác minh.
- Các trạng thái đã được xác minh, thời điểm và nguồn.
- Người/nhóm được giao và mức ưu tiên.
- Ngày đến hạn xử lý/escalation.
- Những hành động cho phép và yêu cầu audit/approval.
- Cách quay lại workflow khi điều kiện giải quyết được đáp ứng.

Manual review không nên là nơi bỏ quên các Saga chưa kết thúc.

## 22. Mẫu Saga thực tế: Order, Inventory và Payment

**Giả định nghiệp vụ:**

- Order bắt đầu PENDING.
- Inventory giữ hàng trong 15 phút.
- Payment có thể phản hồi tức thì hoặc chậm.
- Order chỉ CONFIRMED khi reservation hợp lệ và payment đã xác minh thành công.
- Khi Payment bị từ chối, phải release reservation.
- Khi có payment thành công nhưng đơn không thể hoàn tất, cần refund theo chính sách.

### 22.1. Happy path

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Order Saga
    participant I as Inventory
    participant P as Payment
    C->>O: Checkout(idempotencyKey)
    O->>O: Persist order PENDING and saga
    O->>I: Reserve(orderId, operationId)
    I-->>O: InventoryReserved(reservationId)
    O->>P: Charge(paymentId, same stable key)
    P-->>O: PaymentSucceeded(paymentId)
    O->>O: Verify reservation validity
    O->>O: Commit order CONFIRMED + outbox
    O-->>C: Final status or status URL
~~~

Kết quả: Order CONFIRMED, Inventory có reservation phù hợp, Payment có kết quả đã xác minh. Mọi step được ghi state bền vững và có IDs để replay/recover.

### 22.2. Inventory hết hàng

~~~text
T1 Order PENDING -> committed
T2 Inventory rejects OUT_OF_STOCK (definitive)
Order records rejection
Order transitions REJECTED or CANCELLED according to domain
No charge command is sent
Saga closes with a terminal business rejection
~~~

Không cần “refund” nếu chưa hề charge. Không nên lập kế hoạch compensation cho một bước chưa có side effect.

### 22.3. Payment bị từ chối rõ ràng

~~~text
InventoryReserved confirmed
PaymentDeclined confirmed
Saga enters COMPENSATING
ReleaseReservation command (stable compensation ID)
InventoryReleased confirmed
Order CANCELLED/REJECTED according to policy
Saga COMPENSATED
~~~

Nếu ReleaseReservation timeout, Saga phải giữ COMPENSATING hoặc CONFIRMATION_REQUIRED, không chuyển COMPENSATED trước khi biết release đã thực hiện.

### 22.4. Payment timeout sau khi provider charge

~~~text
InventoryReserved confirmed
ChargePayment sent
Provider charge succeeded
Response lost
Saga times out waiting
Saga marks PAYMENT_OUTCOME_UNKNOWN
Reconciliation queries Payment using paymentId
PaymentSucceeded verified
If reservation remains valid -> continue confirmation
Else -> compensation/refund policy
~~~

Nếu reservation đã hết hạn trước khi xác minh Payment, không thể tự giả định còn stock. Phải dựa trên dữ liệu của Inventory owner và chính sách xử lý late success.

### 22.5. Saga restart giữa các bước

~~~text
Order persisted Saga + outbox
Outbox publisher sent ReserveInventory
Inventory persisted reservation
Orchestrator crashed before consuming InventoryReserved
Event may be redelivered; or worker queries reservation by operationId
Saga resumes from WAITING_INVENTORY
Receives authoritative outcome, then proceeds to Payment
~~~

Không bắt đầu lại từ CreateOrder khi đã có sagaId/businessKey cũ.

## 23. Quy tắc xử lý kết quả đến muộn

Một Saga cần chính sách rõ cho **late outcomes**:

| Saga hiện tại | Event đến muộn | Cách xử lý |
| --- | --- | --- |
| WAITING_PAYMENT | PaymentSucceeded | Tiếp tục nếu điều kiện nghiệp vụ hợp lệ |
| COMPENSATING | PaymentSucceeded | Ghi nhận thực tế, xác định refund/cancel path |
| COMPENSATING | InventoryReleased | Hoàn tất step bù trừ nếu đúng operationId |
| COMPENSATED | PaymentSucceeded | Mở compensation/refund follow-up hoặc escalation |
| COMPLETED | Duplicate PaymentSucceeded | No-op idempotent và audit nếu cần |
| COMPLETED | PaymentFailed mâu thuẫn | Điều tra nguồn và state, không overwrite tự động |
| NEEDS_MANUAL_REVIEW | PaymentSucceeded đã xác minh | Có thể resume qua transition được kiểm soát |
| CANCEL_REQUESTED | ShipmentCreated | Áp dụng chính sách hủy/vận chuyển/return |

Không có một quy tắc chung “bỏ qua mọi event khi Saga terminal”. Với side effect tài chính phát hiện muộn, hệ thống vẫn cần lưu bằng chứng và có workflow xử lý hậu quả.

## 24. Java/Spring Boot: phác thảo lưu bền vững Saga

Một triển khai đơn giản có thể dùng Spring Boot, Spring Data JPA/JDBC và message broker. Mục tiêu đoạn mã dưới đây là minh họa **ranh giới transaction**, không phải sản phẩm chạy sẵn.

### 24.1. Service bắt đầu Saga

~~~java
@Service
public class CheckoutSagaService {

    private final SagaRepository sagas;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public CheckoutSagaService(
            SagaRepository sagas,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.sagas = sagas;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public String start(CheckoutCommand command, String idempotencyKey) {
        String businessKey = command.tenantId() + ":" + idempotencyKey;
        var existing = sagas.findByBusinessKey(businessKey);

        if (existing.isPresent()) {
            // Production: also check payload compatibility and authorization.
            return existing.get().getSagaId();
        }

        String sagaId = UUID.randomUUID().toString();
        String orderId = UUID.randomUUID().toString();

        orders.save(Order.pending(orderId, command));
        sagas.save(SagaInstance.waitingInventory(
            sagaId, businessKey, orderId
        ));

        outbox.save(OutboxMessage.reserveInventory(
            "reserve-" + sagaId, sagaId, orderId,
            command.items()
        ));

        return sagaId;
    }
}
~~~

**Điểm cần triển khai thêm:**

- findByBusinessKey rồi save **chưa đủ chống race** giữa hai request đồng thời; cần UNIQUE database, atomic insert và xử lý conflict đúng transaction.
- Lưu payload fingerprint để ngăn cùng idempotency key nhưng dữ liệu khác nhau.
- Order, Saga và Outbox phải dùng cùng local transaction thực sự.
- Validate quyền, dữ liệu và business invariants.
- Không chứa credit card data nhạy cảm trong Saga/outbox.
- Không gọi HTTP Inventory giữa transaction này rồi coi transaction local có thể rollback Inventory.

### 24.2. Event handler có inbox

~~~java
@Service
public class InventoryEventHandler {

    private final SagaRepository sagas;
    private final InboxRepository inbox;
    private final OutboxRepository outbox;

    public InventoryEventHandler(
            SagaRepository sagas,
            InboxRepository inbox,
            OutboxRepository outbox) {
        this.sagas = sagas;
        this.inbox = inbox;
        this.outbox = outbox;
    }

    @Transactional
    public void onInventoryReserved(InventoryReserved event) {
        boolean newEvent = inbox.tryInsert(
            "checkout-saga", event.eventId()
        );
        if (!newEvent) {
            return;
        }

        SagaInstance saga = sagas.lockById(event.sagaId());

        if (!saga.canAcceptInventoryReserved(event.operationId())) {
            saga.recordIgnoredOrLateEvent(event.eventId());
            return;
        }

        saga.confirmInventoryReservation(event.reservationId());

        String paymentOperationId = "payment-" + saga.getSagaId();
        outbox.save(OutboxMessage.chargePayment(
            paymentOperationId,
            saga.getSagaId(),
            saga.getOrderId()
        ));
    }
}
~~~

Điểm trọng yếu: inbox marker, guarded Saga state update và outbox record nằm trong cùng database transaction. Listener chỉ commit broker offset/ACK sau khi local commit thành công theo cách framework tích hợp.

Production cần thêm:
- Transaction isolation/locking phù hợp và UNIQUE constraints.
- Duplicate event handling qua operationId và business key.
- Error classification thay vì nuốt mọi exception.
- Bảo vệ event schema, version và caller permissions.
- Logging/tracing không lộ secret.
- Trạng thái khi event đến sau compensation hoặc terminal completion.

### 24.3. Không dựa vào @Transactional cho external API

Nếu một method có @Transactional rồi gọi Payment Provider, transaction SQL **không thể tự rollback charge bên provider** khi Java throw exception. Nên tách operation state và external call thành workflow step, dùng idempotency provider và reconciliation.

## 25. Recovery worker bằng pseudocode

~~~text
function recoverSaga(sagaId):
    claimLeaseOrLock(sagaId)
    saga = loadDurableState(sagaId)

    if saga is terminal:
        return

    if saga has unresolved external side effect:
        outcome = queryAuthoritativeOwner(
            saga.currentOperationId
        )

        if outcome == CONFIRMED_SUCCESS:
            applyGuardedSuccessTransition(saga, outcome)
            return

        if outcome == CONFIRMED_FAILURE:
            planRequiredCompensations(saga)
            return

        scheduleNextReconciliation(saga, backoffWithJitter())
        return

    if saga.state == RETRY_SCHEDULED:
        if businessDeadlineAllowsRetry(saga):
            publishSameOperationIdViaOutbox(saga)
        else:
            applyExpirationPolicy(saga)
        return

    if saga.state == COMPENSATING:
        findNextUnconfirmedCompensation(saga)
        dispatchOrQueryWithSameCompensationId()
        return

    if saga.state == WAITING:
        if stepDeadlineExceeded(saga):
            markForOutcomeVerification(saga)
        else:
            maintainDurableTimer(saga)
        return

    alertOwnerIfNoSafeAutomaticAction(saga)
~~~

**Pseudocode là khung quyết định**, không phải code có thể chạy nguyên xi. Worker phải bảo đảm state transition và outbox write trong transaction, kết thúc lease đúng, xử lý worker cũ sau lease expiry và không gọi side effect theo operation ID mới.

### 25.1. Scheduler không nên quét toàn bộ bảng liên tục

Với hàng triệu Saga, cần index theo state/nextActionAt và batch bounded. Có thể partition historical instances, archive terminal records và thiết kế job queue phù hợp. Tránh N+1 queries, full table scan và một lock khổng lồ khi chạy recovery.

### 25.2. Backpressure và giới hạn concurrency

Nếu sau sự cố broker có 100.000 Saga cần resume, worker không nên gửi đồng thời 100.000 payment requests. Cần rate limits, per-tenant fairness, max concurrent operations, retry budget và ưu tiên theo business deadline.

## 26. Tính đúng đắn dưới concurrency và failover

Có ba lớp bảo vệ thường cần:

1. **Workflow level:** chỉ một state transition hợp lệ được commit theo version/currentState.
2. **Message level:** inbox/eventId ngăn cùng event áp dụng lại.
3. **Business side effect level:** operationId/business unique key hoặc provider idempotency ngăn tác dụng lặp.

Một lớp không thay thế tất cả lớp khác.

Ví dụ hai event khác eventId có thể cùng báo PaymentSucceeded cho cùng paymentId. Inbox không nhận ra chúng là duplicate, nhưng step identity/paymentId và state guard giúp tránh chốt hai lần.

### 26.1. Source of truth khi xảy ra mâu thuẫn

Nếu Saga state ghi PaymentPending nhưng Payment Service trả Succeeded, Payment Service là owner của payment outcome; Saga nên ghi nhận kết quả đã xác minh và áp dụng điều kiện của Order. Không sửa dữ liệu Payment trực tiếp từ Saga.

Nếu một callback PaymentFailed đến muộn sau PaymentSucceeded, phải dựa vào payment state machine và provider contract, không chọn “event tới sau thắng”. Một nguồn dữ liệu có thẩm quyền và version/sequence giúp quyết định.

### 26.2. Split-brain và fencing

Khi hai orchestrator nghĩ mình cùng sở hữu một Saga do phân vùng mạng, cần các ràng buộc ở storage để chỉ một transition thắng. Leases giảm tranh chấp nhưng không tự bảo đảm external effect duy nhất; idempotency phía Payment/Inventory là lớp cuối quan trọng.

## 27. Quản lý cancellation trong Saga kéo dài

Người dùng nhấn “Hủy đơn” không có nghĩa mọi side effect đã biến mất ngay.

Có thể thiết kế các state:

- CANCEL_REQUESTED: ghi nhận ý định hủy.
- CANCELLING: dừng bước chưa chạy, phát compensation cho bước đã thực hiện.
- WAITING_REFUND: charge có thực nên phải chờ refund.
- CANCELLED: các điều kiện hủy được đáp ứng theo contract.
- NEEDS_REVIEW: không thể xác minh hay bù trừ tự động.

### 27.1. Cancellation race

Giả sử PaymentSucceeded tới cùng lúc với CANCEL_REQUESTED. Hai handler phải đọc state/version và áp dụng một chính sách xác định:

- Nếu chưa charge, có thể dừng bước.
- Nếu đã charge, refund hoặc xử lý exception.
- Nếu fulfillment đã bàn giao, có thể cần quy trình return.
- Nếu không rõ provider đã xử lý, phải tra cứu trước khi kết luận.

Không được xử lý bằng cách đặt order CANCELLED trước rồi bỏ qua mọi event tài chính về sau.

### 27.2. Đơn hủy và refund là hai workflow

Một Order có thể CANCELLED nhưng refund còn PENDING. API/UI cần nói rõ trạng thái hoàn tiền, tránh tuyên bố người dùng đã nhận lại tiền. Refund itself cần operationId, idempotency, retry và reconciliation.

## 28. API và trải nghiệm người dùng cho tiến trình dài

Một workflow kéo dài cần hợp đồng giao tiếp rõ để người dùng không gửi lại thao tác vì tưởng hệ thống treo.

Một API có thể hỗ trợ:

| Endpoint | Ý nghĩa |
| --- | --- |
| POST /orders | Tiếp nhận idempotent, trả orderId/operationId |
| GET /operations/{id} | Truy vấn trạng thái Saga theo quyền |
| POST /operations/{id}/cancel | Ghi nhận yêu cầu hủy, không mặc định hủy tức thì |
| GET /orders/{id} | Trả trạng thái business của đơn |
| Webhook / SSE / WebSocket | Thông báo thay đổi, có phương án fallback polling |

Response nên phân biệt:
- Accepted / In progress.
- Waiting for provider.
- Needs user action.
- Cancellation pending.
- Completed / rejected.
- Manual review / reconciliation pending.

Không đưa internal exception, stack trace, tên queue hoặc số lần retry vào public response nếu không cần thiết. Thông tin vận hành phải ở logs/metrics an toàn.

### 28.1. Polling cần backoff

Client có thể dùng Retry-After hoặc gợi ý interval, giới hạn polling và dừng khi terminal. Nếu kết nối realtime ngắt, query status là nguồn đáng tin để đồng bộ lại, không dựa hoàn toàn vào việc một event push từng được gửi.

### 28.2. Không tạo status URL không kiểm soát quyền

OperationId không phải authentication token. Mọi GET status/cancel phải xác thực và phân quyền theo tenant/customer, kiểm soát resource enumeration và dữ liệu nhạy cảm.

## 29. Observability: đo cả sự sống của workflow

Ngoài CPU, HTTP latency hoặc broker lag, cần đo trạng thái kinh doanh của Saga.

| SLI/metric | Ý nghĩa |
| --- | --- |
| Saga started/completed/compensated | Tỷ lệ kết thúc và loại kết quả |
| Saga time-to-terminal p50/p95/p99 | Thời gian đi đến kết quả cuối |
| Saga pending by state and age | Công việc đang kẹt ở bước nào |
| Step success/failure/timeout rate | Dependency nào có vấn đề |
| Step retry count / retry budget | Có retry storm không |
| Compensation success/lag | Các nghĩa vụ hoàn tác đã hoàn thành chưa |
| Unknown external operations | Payment/shipping chưa xác minh |
| Reconciliation success/age | Đối soát có đóng được trạng thái không |
| Durable timer lag | Scheduler có xử lý đúng hạn không |
| Outbox backlog oldest age | Command/event chưa publish |
| Inbox duplicate count | Redelivery được chặn |
| Lease contention/fencing conflicts | Nhiều worker cùng tranh ownership |
| Manual review queue age | Trường hợp ngoại lệ có bị quên không |
| Late event count | Hệ thống nhận kết quả sau deadline |
| Business anomalies | Charge trùng, reservation kẹt, refund quá hạn |

Một số Saga có thể tồn tại nhiều ngày do nghiệp vụ bình thường; không alert chỉ vì “chưa terminal sau 1 phút”. Cần ngưỡng theo **saga type và bước đang chờ**, có tính lịch làm việc, SLA đối tác và business expiry.

### 29.1. Correlation ID và tracing

Nên có:

- sagaId xuyên toàn bộ workflow.
- orderId/paymentId/reservationId và operationId cho từng bước.
- eventId/commandId cho message.
- traceId cho từng technical execution.
- structured logs theo transition, attempt, status và source.

Một Saga dài có thể gồm nhiều traces; **traceId không thay sagaId**. Traces/logs không cần chứa secret và dữ liệu cá nhân không cần thiết. Có thể cho support tra cứu bằng public operationId đã phân quyền.

### 29.2. Audit trail

Với transaction quan trọng, audit nên ghi:

- Transition từ state nào sang state nào.
- Ai hoặc sự kiện nào kích hoạt.
- Thời điểm và bản version.
- OperationId của side effect.
- Bằng chứng/kết quả đã xác minh.
- Lý do bù trừ/manual override.
- Liên kết tới workflow bù trừ/refund riêng.

Nhờ đó có thể giải thích vì sao một đơn bị hủy dù PaymentSucceeded đến muộn, hoặc vì sao refund được khởi tạo.

## 30. SLO cho Saga kéo dài

Ví dụ minh họa, không phải SLO chuẩn:

~~~text
Trong một cửa sổ 30 ngày:
- 99,5% checkout saga đã tiếp nhận đạt trạng thái terminal
  hoặc trạng thái exception có owner trong 15 phút.
- 99% compensation tự động được xác minh trong 10 phút
  khi dependency sẵn sàng theo giả định.
- Không có operation thanh toán UNKNOWN nào quá ngưỡng
  mà không được gắn owner/escalation.
~~~

Cần định nghĩa rõ:
- Workflow nào được tính.
- Khung thời gian và excluded conditions.
- Loại state nào thực sự terminal.
- Nghĩa của compensated khi refund còn pending.
- Business calendars và downtime của external provider.
- Điểm bắt đầu đo từ ACCEPTED hay từ lúc nhận event đầu tiên.

Một SLO đo “có HTTP 200” không đủ bảo đảm Saga đã hoàn tất nghiệp vụ. Phải đo **time-to-terminal**, pending age và kết quả thực tế.

## 31. Độ tin cậy và hạ tầng

### 31.1. Backup, restore, RPO và RTO

Saga state là dữ liệu quan trọng. Nếu database chứa Saga bị mất 30 phút dữ liệu, có thể mất dấu các command đã gửi đến Payment. Cần chính sách RPO/RTO gắn với rủi ro nghiệp vụ, backup/PITR và restore drills.

Replication không thay backup: xóa nhầm hoặc dữ liệu sai có thể được replicate sang các bản sao. Sau restore, phải **đối soát trạng thái external systems** thay vì giả định database là tất cả sự thật.

### 31.2. Broker retention và event replay

Nếu broker chỉ giữ event ba ngày nhưng Saga có thể chờ 30 ngày, đừng thiết kế recovery phụ thuộc vào khả năng đọc lại event duy nhất từ ngày đầu. Cần lưu state bền vững hoặc archive/replay policy.

Event replay phải tránh kích hoạt lại external effects ngoài ý muốn. Phân biệt rebuild projection, retry cùng operation và command mới.

### 31.3. Nâng cấp workflow version

Một Saga đang chạy có thể thuộc phiên bản định nghĩa cũ. Khi deploy:
- Giữ khả năng hiểu state/event schema cũ trong giai đoạn chuyển tiếp.
- Ghi version của Saga definition.
- Có migration plan hoặc cho Saga cũ hoàn thành theo logic tương ứng.
- Test restart, rollback và rolling deploy.
- Tránh đổi tên state/step thiếu compatibility mà không xử lý dữ liệu đã lưu.

## 32. Các anti-pattern thường gặp

**1. Saga chỉ tồn tại trong HTTP request.**  
Một process chết giữa bước làm mất tiến độ. Dùng durable workflow state.

**2. Timeout đồng nghĩa rollback mọi thứ.**  
Timeout chỉ cho biết caller chưa nhận kết quả; side effect có thể đã commit.

**3. Retry bằng operationId mới.**  
Cùng ý định nghiệp vụ có thể bị thực hiện hai lần.

**4. Compensation được coi là SQL rollback.**  
Hoàn tiền, giải phóng hàng và hủy shipment là các nghiệp vụ riêng, có thể thất bại.

**5. Mọi lỗi đều chuyển COMPENSATING.**  
Lỗi transient có thể retry; lỗi UNKNOWN phải xác minh trước khi quyết định.

**6. ACK event trước khi commit Saga state.**  
Crash sau ACK trước commit có thể làm mất bước workflow.

**7. Chỉ lưu lastStep và boolean success.**  
Không đủ biết command đã gửi, side effect đã thực hiện hay bù trừ nào còn pending.

**8. Không dùng outbox cho state + publish.**  
Có thể commit state nhưng đánh mất command/event cần phát.

**9. Có inbox nhưng không có business idempotency.**  
Hai eventId khác nhau vẫn có thể cùng biểu diễn một operation.

**10. Choreography không có workflow owner.**  
Khi event bị trễ hoặc mất, không ai xử lý pending quá hạn.

**11. Timer chạy thì ghi FAILED ngay.**  
Timer cần đọc state hiện tại và kiểm tra authoritative outcome.

**12. Worker lease hết hạn nhưng vẫn gửi lệnh.**  
Phải có version/fencing và idempotent recipient.

**13. Bỏ qua late PaymentSucceeded vì Saga đã CANCELLED.**  
Có thể bỏ quên tiền đã thu và nghĩa vụ refund.

**14. Không có retry budget.**  
Hệ thống có thể tạo retry storm khi dependency outage.

**15. Không có manual escalation.**  
Một số kết quả từ provider không thể tự động xác minh; phải có owner.

**16. Dùng traceId thay business operationId.**  
Một Saga gồm nhiều requests/traces, trace không bảo vệ side effect.

**17. Dựa vào callback duy nhất.**  
Callback có thể trễ, lặp hoặc không đến; cần query/reconciliation khi quan trọng.

**18. Đánh dấu COMPENSATED khi mới phát command release.**  
Phải xác minh kết quả bù trừ theo policy.

**19. Không thử replay sau restart.**  
Happy path không chứng minh khả năng phục hồi.

**20. Không lưu workflow definition version.**  
Rolling deploy có thể thay logic một Saga đang chạy.

## 33. Failure-injection và integration test

Một hệ Saga cần kiểm thử tại các ranh giới transaction, message và side effect.

| Tình huống thử nghiệm | Điều cần xác minh |
| --- | --- |
| Crash trước khi Saga được commit | Client retry cùng idempotency key không tạo hai đơn |
| Crash sau Saga/outbox commit trước publish | Publisher tiếp tục phát command |
| Crash sau publish trước mark-sent | Recipient dedup cùng operationId |
| Inventory commit reservation nhưng response mất | Query/retry không giữ hàng hai lần |
| Payment charge thành công nhưng response mất | Saga giữ UNKNOWN và đối soát, không charge trùng |
| Consumer crash sau Saga state commit trước ACK | Redelivery no-op với inbox/version |
| Hai orchestrator cùng claim Saga | Một transition commit; worker cũ không ghi đè |
| Scheduler timer chạy sau khi Saga COMPLETED | Timer no-op |
| PaymentSucceeded đến sau bắt đầu compensation | Áp dụng late outcome policy/refund |
| ReleaseReservation đã thành công nhưng response mất | Bù trừ retry/query không cộng hàng hai lần |
| Broker outage kéo dài | Outbox pending không mất; có alert/backpressure |
| Database restart | Durable Saga resume đúng |
| DLQ poison message | Có owner và đường xử lý ngoại lệ |
| Deploy workflow version mới | Saga cũ resume theo contract |
| Client đóng tab | Workflow vẫn chạy hoặc kết thúc theo business policy |
| Manual override và event trễ | State guard và audit giữ đúng invariant |

### 33.1. Test crash giữa commit và ACK

~~~text
Given:
  Saga S-8421 ở WAITING_INVENTORY
  Command reserve-8421 đã được xử lý ở Inventory

When:
  InventoryReserved E10 được consumer xử lý,
  Saga DB COMMIT sang WAITING_PAYMENT và ghi outbox
  Consumer crash trước broker ACK
  Broker phát lại E10

Then:
  Inbox ngăn áp dụng E10 lần thứ hai
  Saga giữ một current payment operation
  Không tạo thêm payment command với ID mới
  Outbox có thể phát lại cùng stable command ID an toàn
~~~

### 33.2. Test timeout sau side effect

~~~text
Given:
  Payment provider đã ghi nhận charge P-8421

When:
  Response bị mất
  Saga vượt step timeout
  Orchestrator restart

Then:
  Saga không ghi PaymentFailed chỉ từ timeout
  Recovery query P-8421 và xác minh kết quả
  Không tạo charge P-8422 để thử lại
  State đi tiếp hoặc bù trừ theo reservation/business policy
~~~

### 33.3. Test concurrency

Chạy hai worker cùng lúc với event/timer khác nhau. Xác minh optimistic locking/row lock bảo vệ transition và mọi side effect có cùng operation IDs. Unit mock thường không mô phỏng đúng khóa, transaction isolation và broker ACK; các bước quan trọng nên được thử bằng database/broker gần thật.

### 33.4. Test recovery time

Không chỉ test đúng dữ liệu. Đo thời gian phát hiện Saga kẹt, thời gian scheduler tiếp tục, backlog được drain và p95/p99 time-to-terminal sau outage. Nếu recovery gây tải gấp 10 lần, cần điều chỉnh rate limiting và retry budget.

## 34. Quy trình xử lý incident Saga kẹt

Giả sử có hàng nghìn checkout Saga ở WAITING_PAYMENT quá hạn.

**Bước 1 — Xác định phạm vi.** Từ khi nào pending tăng? Có liên quan region, release, provider hay broker không?

**Bước 2 — Phân loại state và operation.** Bao nhiêu payment thực sự UNKNOWN, bao nhiêu đã thành công nhưng event trễ, bao nhiêu rejected rõ?

**Bước 3 — Bảo vệ hệ thống.** Giảm retry storm, giới hạn recovery concurrency, tránh gửi duplicate charge.

**Bước 4 — Đối chiếu nguồn sự thật.** Payment Service/provider trạng thái từng operationId thế nào?

**Bước 5 — Khôi phục theo batch có kiểm soát.** Resume Saga dựa trên state bền vững, dùng idempotency và fencing.

**Bước 6 — Xử lý compensation.** Với đơn không thể hoàn tất nhưng đã charge, thực hiện refund workflow theo policy; với reservation kẹt, release an toàn.

**Bước 7 — Escalate ngoại lệ.** Những operation chưa thể xác minh phải có owner, không được xóa hoặc đánh dấu FAILED tùy tiện.

**Bước 8 — Kiểm tra invariants.** Không trừ tiền trùng, không giữ tồn kho trùng, không phát sinh order status mâu thuẫn.

**Bước 9 — Quan sát recovery.** Theo dõi backlog, time-to-terminal, compensation lag, pending age và errors.

**Bước 10 — Postmortem.** Ghi nguyên nhân, failure window, dữ liệu bị ảnh hưởng, hành động khắc phục, test và runbook mới.

Tránh “sửa nhanh” bằng cách reset tất cả Saga về NEW hoặc chạy lại toàn bộ steps mà không đối soát side effects đã diễn ra.

## 35. Thiết kế các ranh giới giao dịch trong Saga

Một sơ đồ hợp lý:

~~~mermaid
flowchart TD
    A["API accepts checkout"] --> B[("Order DB: order+saga+outbox transaction")]
    B --> C["Outbox Publisher"]
    C --> D[("Broker")]
    D --> E["Inventory Consumer"]
    E --> F[("Inventory DB: reservation+inbox transaction")]
    F --> G["Inventory outcome event"]
    G --> H["Saga event handler"]
    H --> I[("Saga DB: state+inbox+outbox transaction")]
    I --> J["Next command / timer"]
~~~

Các ranh giới:

- **Order DB transaction**: tạo order, Saga, outbox.
- **Inventory DB transaction**: lưu reservation và marker chống trùng.
- **Saga DB transaction**: update guarded state, inbox, next outbox command.
- **Provider API**: external side effect có hợp đồng riêng và cần idempotency/lookup.
- **Broker delivery**: có thể redeliver, không thay thế business transaction.

Không có đường kết nối ma thuật giúp tất cả thành một commit. Recovery dựa trên **durable intent + replay-safe operations + authoritative status verification**.

## 36. Chi phí và trade-offs của Saga kéo dài

Saga tăng khả năng xử lý một workflow xuyên service, nhưng cũng có chi phí:

- Bảng Saga state, outbox/inbox, scheduler, retention.
- Số lượng events/commands và retries.
- Quản lý step versions, migrations và long-running instances.
- Tracing nhiều request/traces.
- Compensation/reconciliation và manual operations.
- Transaction guards, locks, duplicate handling.
- Kết nối provider và các quy tắc business deadline.
- On-call, runbooks, test failure injection.

### 36.1. Đừng dùng Saga khi chỉ cần một local transaction

Nếu một business invariant yêu cầu cập nhật hai bảng trong cùng service/database, dùng transaction cục bộ sẽ đơn giản và mạnh hơn một Saga không cần thiết.

Nếu hai service phải liên tục gọi nhau để bảo vệ một invariant không thể tách, cần xem lại **bounded context và service boundaries**, không nhất thiết thêm coordinator mới để chữa một ranh giới domain sai.

### 36.2. Khi nào workflow engine hữu ích?

Một engine có durable execution/timers/state history có thể giảm lượng code tự viết cho scheduler, retry, versioning hoặc observability, nhưng cần kiểm tra chính xác contract, operational model và giới hạn của engine.

Engine **không tự làm external payment idempotent**, không thay business compensation design và không quyết định giúp sản phẩm xem refund đã hoàn tất chưa.

Đội nên so sánh:
- Tự triển khai Saga state machine bằng database + outbox + scheduler.
- Sử dụng workflow orchestration platform.
- Choreography dựa trên events và process manager nhẹ cho các luồng cần theo dõi.

Chọn theo complexity workflow, số lượng workflows, SLA, chi phí vận hành và kỹ năng team; không theo số lượng công nghệ mới.

## 37. Mẫu ADR về khả năng phục hồi Saga

~~~markdown
# ADR: Durable checkout Saga và phục hồi sau timeout

Trạng thái: Accepted (ví dụ)
Owner: Order Team

## Bối cảnh
- Checkout gồm Order, Inventory, Payment.
- Mỗi service có local transaction riêng.
- Payment provider có thể trả kết quả muộn.
- Không chấp nhận duplicate charge hoặc orphan reservation.
- Saga có thể kéo dài vượt HTTP deadline.

## Quyết định
- Order Service sở hữu checkout workflow state.
- Lưu sagaId, businessKey, step operation IDs, state,
  version, nextActionAt, deadline và compensation outcomes.
- Ghi Saga transition và outbox command cùng local transaction.
- Các service nhận xử lý idempotent theo stable operationId.
- Retry có backoff/jitter/budget; timeout sau side effect là UNKNOWN.
- Reconciliation worker query authoritative owners.
- Dùng optimistic locking, lease/fencing cho concurrent workers.
- Không chuyển Saga terminal khi compensation bắt buộc chưa xác minh.

## Không bảo đảm
- Không có ACID transaction xuyên mọi service.
- Provider API ngoài không bị rollback bằng SQL transaction.
- Event có thể giao trùng/muộn/sai thứ tự.
- Compensation không nhất thiết khôi phục thế giới như chưa từng có thao tác.

## Kiểm chứng
- Crash sau commit trước ACK/publish.
- Payment success response lost.
- Duplicate/late events.
- Compensation timeout.
- Concurrent timer vs callback.
- Restart, recovery lag, DLQ và manual escalation.

## Triggers xem lại
- Time-to-terminal vượt SLO.
- Compensation backlog tăng.
- Chi phí recovery/on-call quá cao.
- Workflow complexity vượt khả năng maintain.
~~~

ADR giúp nhóm hiểu **bảo đảm và giới hạn thực tế**, không chỉ tên pattern.

## 38. Checklist triển khai Saga phục hồi được

- [ ] Saga có owner và business outcome rõ.
- [ ] Mỗi bước có operationId ổn định và side-effect contract.
- [ ] State machine có transition guards và terminal semantics.
- [ ] Saga state được lưu bền vững trước khi dispatch command.
- [ ] Có outbox hoặc cơ chế tương đương tránh mất ý định phát message.
- [ ] Consumer có inbox/dedup và business uniqueness constraints.
- [ ] Broker ACK/offset diễn ra sau durable transaction phù hợp.
- [ ] Không retry side effect với operationId mới.
- [ ] Timeout sau gửi request được coi là UNKNOWN khi có thể đã xử lý.
- [ ] Có query status/reconciliation cho kết quả chưa xác định.
- [ ] Compensation có operationId, trạng thái, retry và audit riêng.
- [ ] Saga không báo compensated khi compensation chưa xác minh.
- [ ] Có durable timers, business expiry và escalation deadlines.
- [ ] Multiple workers được kiểm soát bằng lock/version/lease/fencing.
- [ ] Có xử lý event đến trễ, trùng và sai thứ tự.
- [ ] Có workflow definition version và migration policy.
- [ ] Có retention, backup, restore drill và RPO/RTO phù hợp.
- [ ] Có GET status/notification và authorization cho client.
- [ ] Có dashboard pending age, time-to-terminal, retry/compensation lag.
- [ ] Có manual review owner và runbook.
- [ ] Đã fault-test crash/timeout/restart/duplicate/late events.
- [ ] Không dùng Saga khi một local transaction đơn giản đã đủ.

## 39. Bài tập tình huống

### Bài tập A — Payment đã thành công nhưng Saga mất phản hồi

Order Saga phát ChargePayment(P-8421). Provider ghi nhận charge, Payment Service trả event nhưng broker lỗi, Saga không nhận. Sau 20 giây timer kích hoạt.

Hãy thiết kế:
1. State mà Saga nên ghi.
2. OperationId nào phải giữ nguyên.
3. Nguồn nào có thẩm quyền xác minh.
4. Cách quyết định retry/query và khi nào escalate.
5. Nếu giữ hàng hết hạn, cách xử lý refund/compensation.
6. Test nào chứng minh không có duplicate charge.

### Bài tập B — Orchestrator crash sau publish

Saga ghi WAITING_INVENTORY, publish ReserveInventory thành công nhưng crash trước khi đánh dấu outbox sent. Sau restart, publisher phát cùng command lần nữa.

Hãy giải thích cách Inventory deduplicate, Saga xử lý duplicate InventoryReserved, và vì sao không cần giả định broker chỉ giao message một lần.

### Bài tập C — Cancellation race

User yêu cầu hủy, trong khi PaymentSucceeded và timer hết hạn đồng thời đến. Hãy định nghĩa state machine, transition guards, compensation và cách không ghi đè một kết quả đã commit hợp lệ.

### Bài tập D — Workflow kéo dài 3 ngày

Một B2B onboarding Saga gồm xác minh hồ sơ, duyệt thủ công, cấp quyền và gửi email. Hãy xác định business deadlines, durable timers, trạng thái chờ, manual approval, cancellation và cách resume sau rolling deployment.

### Bài tập E — 100.000 Saga kẹt sau outage

Broker ngừng 30 phút, sau hồi phục có 100.000 Saga tới hạn retry. Thiết kế batch claiming, priority, rate limits, backpressure, retry jitter, SLO recovery và monitoring không làm downstream quá tải.

### Bài tập F — Compensation thất bại

Inventory release đã thực hiện nhưng response mất; cùng lúc Payment refund đang pending. Hãy chỉ ra tại sao Saga chưa thể báo “mọi bù trừ hoàn tất”, cách query từng owner và thiết kế status API minh bạch.

## 40. Câu hỏi tự kiểm tra

1. Vì sao Saga không giống một ACID transaction toàn cục?
2. Khi nào nên chọn orchestration thay vì choreography?
3. Vì sao choreography vẫn cần workflow owner?
4. Một Saga nên lưu những dữ liệu bền vững nào để resume?
5. Step timeout khác business expiry ở điểm nào?
6. Vì sao timeout sau ChargePayment không chứng minh payment failed?
7. Transactional Outbox xử lý lỗi ở ranh giới nào?
8. Vì sao outbox publisher có thể phát command trùng?
9. Inbox marker và business state nên được commit thế nào?
10. EventId và operationId có mục đích chống trùng khác nhau ra sao?
11. Nếu một Saga process chết sau Inventory commit, recovery nên làm gì?
12. Vì sao compensation không đồng nghĩa SQL rollback?
13. ReleaseReservation và Refund có cần idempotency không?
14. Saga COMPENSATING có thể kéo dài vì lý do nào?
15. Khi PaymentSucceeded đến sau Saga CANCELLED, phải làm gì?
16. Durable timer khác một setTimeout trong memory ở điểm nào?
17. Vì sao timer phải đọc state hiện tại trước khi chuyển trạng thái?
18. Lease expiry có thể khiến hai worker cùng hành động ra sao?
19. Optimistic locking bảo vệ khía cạnh nào và không bảo vệ điều gì?
20. Reconciliation cần hỏi nguồn dữ liệu có thẩm quyền nào?
21. Retry exhaustion có phải terminal business failure không?
22. Khi nào cần manual review và dữ liệu audit nào phải đi cùng?
23. Workflow definition version cần làm gì khi rolling deploy?
24. Những SLI nào đo Saga khỏe ngoài HTTP 200?
25. Có thể thử nghiệm chính xác tình huống crash sau COMMIT trước ACK như thế nào?
26. Tại sao không nên replay toàn bộ Saga từ bước đầu sau restart?
27. Saga cancellation khác dừng HTTP request như thế nào?
28. Khi nào nên dùng local transaction thay vì Saga?
29. Workflow engine giải quyết được phần nào và phần nào vẫn là trách nhiệm nghiệp vụ?
30. Làm thế nào chứng minh một Saga kéo dài không bị bỏ quên sau outage?

## 41. Kết luận

**Một Saga đáng tin cậy không chỉ biết đường đi khi mọi bước thành công; nó phải biết tiếp tục ở đâu sau crash, chờ gì khi kết quả chưa xác định và bù trừ thế nào mà không tạo side effect trùng.**

Trong giao dịch phân tán, timeout, event đến muộn, message redelivery, timer chạy trùng và instance restart là những điều kiện bình thường cần được đưa vào mô hình. Saga state phải được lưu bền vững, mỗi step có operation ID ổn định, state transition có guard, command/event có cơ chế publish an toàn và các hệ nhận phải xử lý idempotent.

Khi một side effect bên ngoài đã có thể xảy ra, **đừng đoán kết quả từ lỗi mạng**: hãy truy vấn nguồn có thẩm quyền, đối soát và giữ trạng thái trung gian với owner rõ. Compensation phải được xác minh như một nghiệp vụ mới, không phải một rollback kỳ diệu. Với tiến trình kéo dài, durable timers, scheduler, retry budget, manual escalation, audit, metrics và SLO time-to-terminal giúp bảo đảm công việc không bị quên.

Mục tiêu cuối cùng không phải “Saga luôn hoàn tất ngay”, mà là **mọi Saga được tiếp nhận đều có đường đi tới kết quả hợp lệ hoặc trạng thái ngoại lệ được quản lý, kể cả sau sự cố và nhiều lần phục hồi**.