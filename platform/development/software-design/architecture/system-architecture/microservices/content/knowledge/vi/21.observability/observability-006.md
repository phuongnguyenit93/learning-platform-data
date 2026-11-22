# Chỉ số nghiệp vụ và đo kết quả của quy trình liên dịch vụ

## 1. Vì sao phải đo theo quy trình nghiệp vụ?

Trong hệ thống microservices, mỗi dịch vụ có thể báo `HTTP 200`, CPU bình thường và độ trễ thấp nhưng **khách hàng vẫn không đạt kết quả mong muốn**. Order Service tạo đơn thành công, Payment Service đã thu tiền, Inventory Service không giữ được hàng, Shipping Service chưa nhận yêu cầu: nếu chỉ nhìn dashboard riêng từng service, ta có thể bỏ sót một quy trình bị kẹt.

**Chỉ số nghiệp vụ (business metrics)** cho biết người dùng và tổ chức có đạt kết quả cần thiết hay không: đặt hàng được không, thanh toán thành công không, xử lý đúng hạn không, giao dịch có phải hoàn tiền không, có bao nhiêu đơn bị thất lạc giữa các service. **Chỉ số quy trình liên dịch vụ (end-to-end workflow metrics)** theo dõi hành trình từ điểm bắt đầu đến kết quả cuối, kể cả API đồng bộ, sự kiện bất đồng bộ, retry, bù trừ và bước do con người xử lý.

Mục tiêu của quan sát hệ thống không chỉ là xác định service nào bị lỗi, mà còn trả lời:

1. Bao nhiêu người hoặc yêu cầu đã **bắt đầu** một hành trình?
2. Bao nhiêu hành trình **hoàn thành đúng nghĩa nghiệp vụ**?
3. Bao nhiêu hành trình thất bại, hủy, vẫn xử lý, bị kẹt hoặc phải bù trừ?
4. Mất bao lâu từ lúc bắt đầu đến khi đạt kết quả, ở bước nào chờ lâu nhất?
5. Độ tin cậy, chi phí và trải nghiệm thay đổi thế nào theo phiên bản, khu vực, kênh bán hàng và loại thanh toán?
6. Khi số liệu xấu đi, có thể truy về workflow instance và dịch vụ gây ảnh hưởng để hành động được không?

Tài liệu dùng ví dụ nền tảng thương mại điện tử gồm Checkout/Order, Payment, Inventory, Fulfillment, Shipping và Notification. Phương pháp cũng áp dụng cho mở tài khoản ngân hàng, đăng ký dịch vụ, duyệt vay, xử lý bảo hiểm, đặt chỗ hoặc bất kỳ workflow phân tán nào.

## 2. Phân biệt ba lớp đo lường

| Lớp | Câu hỏi chính | Ví dụ | Vai trò |
|---|---|---|---|
| **Business outcomes** | Kết quả có tạo giá trị không? | Tỷ lệ đặt hàng hoàn tất, số đơn giao đúng hẹn, doanh thu được ghi nhận | Đo trải nghiệm và mục tiêu tổ chức |
| **Workflow/process health** | Quy trình đi tới trạng thái nào, mắc ở đâu? | Tỷ lệ kẹt sau thanh toán, thời gian OrderPlaced → Delivered, tỷ lệ bù trừ | Tìm khoảng trống giữa các service |
| **Technical health** | Thành phần có hoạt động đúng không? | Error rate, P95 latency, queue lag, DB saturation, trace lỗi | Chẩn đoán nguyên nhân và năng lực hạ tầng |

Một tỷ lệ `payment_authorization_success=99%` không đồng nghĩa `order_delivered_success=99%`. Một yêu cầu HTTP 200 từ Order API có thể chỉ nói “đã nhận lệnh” chứ chưa bảo đảm xuất kho hay giao hàng.

Cần phân biệt thêm:

- **Leading indicators:** dấu hiệu sớm như queue lag tăng, Payment retry tăng, số workflow chờ quá ngưỡng.
- **Lagging indicators:** kết quả xuất hiện muộn như đơn giao hoàn tất, tỷ lệ hoàn tiền, khách hàng quay lại.
- **Guardrail metrics:** điều kiện không được đánh đổi khi tối ưu một chỉ số khác, chẳng hạn conversion tăng nhưng fraud loss, chargeback hoặc giao trễ cũng tăng.
- **Operational metrics:** đủ nhanh để kích hoạt xử lý sự cố; có thể khác với báo cáo tài chính đã đối soát cuối ngày.

Cả ba lớp nên được liên kết qua một danh mục metric chính thức, tránh mỗi nhóm tự định nghĩa “successful order” theo cách riêng.

## 3. Ví dụ một quy trình nhiều dịch vụ

Một khách hàng bấm “Đặt hàng”. API Gateway chuyển lệnh tới Order Service. Order tạo đơn và yêu cầu Payment thu tiền hoặc authorize. Inventory giữ hàng, Fulfillment chuẩn bị, Shipping giao; Notification thông báo thay đổi. Một số bước đồng bộ, một số bước dựa trên broker.

~~~mermaid
flowchart LR
    U[Customer] --> G[API Gateway]
    G --> O[Order Service]
    O --> P[Payment Service]
    O --> B[(Event Broker)]
    B --> I[Inventory Service]
    B --> F[Fulfillment Service]
    F --> S[Shipping Service]
    B --> N[Notification Service]
    P --> PSP[Payment Provider]
    PSP --> P
    I --> B
    P --> B
    S --> B
~~~

Các mốc nghiệp vụ có thể là:

~~~text
CheckoutStarted
    ↓
OrderPlaced
    ↓
PaymentAuthorized
    ↓
InventoryReserved
    ↓
FulfillmentAccepted
    ↓
ShipmentCreated
    ↓
Delivered
    ↓
OrderCompleted
~~~

Nhánh lỗi cần xuất hiện rõ trong mô hình:

~~~text
OrderPlaced ── PaymentDeclined ──> OrderCancelled
PaymentAuthorized ── InventoryRejected ──> RefundRequested
RefundRequested ── RefundSucceeded ──> OrderCompensated
ShipmentCreated ── DeliveryFailed ──> ManualIntervention
Any pending state ── TimeoutExceeded ──> RecoveryOrEscalation
~~~

Tên sự kiện là ví dụ; hệ thống thực tế cần định nghĩa chính xác **state machine và quy tắc kết thúc**. “PaymentAuthorized” có thể chưa phải tiền đã capture; “Delivered” có thể do đối tác xác nhận nhưng chưa được hệ thống đối soát; “OrderCompleted” phải do domain owner phát sau khi tất cả điều kiện đạt.

### 3.1. Trả lời “quy trình nào đã hoàn tất?”

Mỗi workflow instance nên có:

- `workflow_id` hoặc `order_id` bền vững qua các service và retry.
- `workflow_type` và `workflow_version` để hiểu các biến thể luồng.
- `started_at`, `terminal_at` và `terminal_status`.
- Trạng thái terminal được định nghĩa rõ: `COMPLETED`, `FAILED`, `CANCELLED`, `COMPENSATED`; trạng thái chưa kết thúc là `IN_PROGRESS` hoặc `NEEDS_ATTENTION`.
- Quy tắc cho các trạng thái đặc biệt: hoàn tiền sau giao hàng, khách trả hàng, order split, partial shipment, partial capture.
- Owner của state machine: service orchestration hoặc process projection; tránh mỗi consumer tự “đoán” trạng thái cuối.

**Không lấy số response 2xx của một endpoint làm số đơn hoàn thành**. Nếu người dùng retry request hoặc gateway trả 202 Accepted, một lệnh có thể tạo nhiều request nhưng vẫn chỉ có một workflow hợp lệ.

## 4. Bắt đầu từ bất biến và mục tiêu nghiệp vụ

Trước khi instrument, hãy viết **điều gì đúng thì xem như thành công**:

| Bất biến / mục tiêu | Cách biến thành phép đo |
|---|---|
| Mỗi đơn đã xác nhận chỉ có một chuỗi thanh toán hợp lệ | Số đơn có charge trùng hoặc payment attempt không đối soát |
| Đơn đã thu tiền phải có kết cục rõ ràng | Tỷ lệ paid orders không có terminal outcome sau ngưỡng |
| Một đơn không trừ kho hai lần vì event redelivery | Số inventory reservation trùng trên một order/line |
| Đơn đủ điều kiện được giao trong thời hạn cam kết | Tỷ lệ giao đúng hạn trên tập đơn đủ điều kiện |
| Thất bại phải được bù trừ hoặc chuyển hỗ trợ | Tỷ lệ compensation hoàn tất, số case tồn quá SLA |
| Khách hàng nhận được kết quả có thể hiểu | Tỷ lệ checkout có trạng thái cuối hiển thị cho khách |

Các mục tiêu cần được thống nhất bởi product/domain owner, kỹ thuật, vận hành và nhóm dữ liệu. Ví dụ: “thành công” đối với Checkout có thể là “đơn được tạo” trong luồng đặt hàng trước, nhưng là “đã thanh toán và giữ hàng” với luồng thanh toán ngay. Hai định nghĩa tạo ra hai tỷ lệ khác nhau; không thể ghép chung mà không ghi semantics.

## 5. Metric catalog: tên, công thức và mẫu số

Một metric dùng để ra quyết định phải có **định nghĩa**, không chỉ có tên. Mỗi metric cần:

- Tên, mô tả và mục tiêu quyết định.
- Đơn vị: count, %, tiền, giây hoặc số đơn.
- Tử số, mẫu số, tập đủ điều kiện.
- Thời điểm cohort: theo start time, event time hay terminal time.
- Cửa sổ thời gian và thời gian chờ hoàn thành (maturity window).
- Xử lý retry, duplicate, cancel, partial completion, refund, late event.
- Owner và nguồn sự thật (source of truth).
- Chiều phân tích được phép: environment, region, channel, payment method, release.
- Mức độ trễ dữ liệu, lịch đối soát và tiêu chí chất lượng.

Ví dụ catalog:

| Mã | Metric | Định nghĩa đề xuất | Diễn giải |
|---|---|---|---|
| B-01 | Checkout conversion | Số checkout attempts hợp lệ dẫn tới `OrderPlaced` / số checkout attempts hợp lệ | Hiệu quả chuyển đổi |
| B-02 | End-to-end completion rate | Số workflow cohort hoàn thành đúng outcome / tổng workflow đủ thời gian quan sát | Tỷ lệ đạt kết quả |
| B-03 | Payment authorization rate | Số payment intents được authorize / số payment intents đủ điều kiện authorize | Tính hiệu quả thanh toán |
| B-04 | Inventory reservation success | Số order đủ điều kiện giữ hàng được reserve / số order đã yêu cầu reserve | Khả năng đáp ứng hàng |
| B-05 | Workflow completion time | `terminal_at - started_at` trên workflow hoàn tất | Thời gian end-to-end |
| B-06 | On-time fulfillment | Số đơn đủ điều kiện hoàn thành trước promised deadline / tổng đơn đủ điều kiện có kết quả | Đúng hẹn |
| B-07 | Stuck workflow rate | Số workflow chưa terminal quá ngưỡng trạng thái / tổng active workflows | Phát hiện workflow kẹt |
| B-08 | Compensation rate | Số workflow cần bù trừ / số workflow có bước tác động đã commit | Chi phí rủi ro và phục hồi |
| B-09 | Duplicate side-effect rate | Số trường hợp charge/reservation lặp thực tế / số giao dịch đủ điều kiện | An toàn nghiệp vụ |
| B-10 | Reconciliation mismatch | Số payment/fulfillment records lệch nguồn ngoài / tổng records đối soát | Tính đúng đắn dữ liệu |
| B-11 | Net value completed | Giá trị các đơn hoàn tất sau điều chỉnh theo quy tắc tài chính | Giá trị đầu ra đã xác định |
| B-12 | Manual intervention burden | Số workflow cần can thiệp / tổng workflow; thời gian xử lý mỗi case | Chi phí vận hành |

Đừng dùng một tên như `conversion_rate` mà không ghi cohort, thời hạn và kiểu sự kiện. “Tỷ lệ thanh toán thành công” cũng cần phân biệt theo **lượt thử (attempt)**, **payment intent**, **order** hoặc **người dùng**. Một order thử thẻ ba lần chỉ được tính một order, nhưng là ba attempts nếu định nghĩa dùng attempt.

### 5.1. Công thức minh họa

Với tập workflow bắt đầu trong một khoảng T và đã có đủ thời gian quan sát:

\[
\text{CompletionRate}(T) =
\frac{\#\{\text{workflow trong cohort T có kết quả COMPLETED}\}}
{\#\{\text{workflow hợp lệ trong cohort T}\}}
\times 100\%
\]

\[
\text{OnTimeRate}(T) =
\frac{\#\{\text{đơn đủ điều kiện có DeliveredAt} \leq \text{PromisedAt}\}}
{\#\{\text{đơn đủ điều kiện đã có kết cục giao hàng}\}}
\times 100\%
\]

\[
\text{StuckRate}(t) =
\frac{\#\{\text{workflow đang mở vượt state-specific timeout tại }t\}}
{\#\{\text{workflow đang mở tại }t\}}
\times 100\%
\]

Điều kiện “đã đủ thời gian quan sát” phải được công bố. Nếu quy trình giao hàng kéo dài hai ngày, không nên lấy mọi order của 10 phút gần nhất làm mẫu số completion rate rồi kết luận conversion giảm.

## 6. Cohort, time window và các loại đồng hồ

Một trong những sai lầm lớn nhất là lấy numerator và denominator thuộc **hai tập khác nhau**. Ví dụ, đếm số đơn giao hôm nay rồi chia số đơn tạo hôm nay: phần lớn đơn giao hôm nay có thể được tạo hôm trước.

Có ba cách xem thời gian thường gặp:

1. **Start cohort:** gom workflow theo thời điểm bắt đầu, rồi quan sát kết quả của đúng các workflow đó. Phù hợp completion/conversion và phân tích funnel.
2. **Terminal/event window:** gom theo ngày sự kiện cuối xảy ra. Phù hợp thông lượng hoàn tất mỗi ngày, doanh thu phát sinh theo mốc đã xác nhận.
3. **Snapshot at time:** xem tất cả workflow đang mở và tuổi của từng trạng thái tại một thời điểm. Phù hợp queue/backlog, stuck workflow và điều hành.

Cần giữ các khái niệm riêng:

| Trường thời gian | Nghĩa | Lưu ý |
|---|---|---|
| `occurred_at` | Sự kiện phát sinh tại hệ nguồn | Có thể bị lệch đồng hồ |
| `ingested_at` | Pipeline nhận sự kiện | Dùng đo trễ dữ liệu |
| `started_at` | Workflow hợp lệ bắt đầu | Mốc cohort |
| `terminal_at` | Workflow đạt trạng thái cuối | Mốc kết thúc |
| `promised_at` | Deadline đã cam kết với người dùng | Có timezone, quy tắc ngày nghỉ và thay đổi cam kết |
| `processed_at` | Consumer xử lý xong | Không luôn bằng thời điểm nghiệp vụ xảy ra |

Giữ timestamp chuẩn hóa (thường UTC) và timezone chỉ tại lớp hiển thị/báo cáo. Event time và processing time không giống nhau; cần late-arrival policy và watermark hoặc lịch tái tính toán khi có event gửi chậm.

### 6.1. Cohort đã trưởng thành (mature cohort)

Giả sử deadline hoàn tất checkout là 10 phút. Để báo cáo completion rate ở thời điểm 10:30, chỉ tính các workflow bắt đầu trước 10:20 hoặc trước mốc được chọn đã trừ đủ thời gian dữ liệu trễ. Với shipping có thể phải đợi nhiều ngày.

Nếu quy trình có hủy hoặc pending không giới hạn, định nghĩa rõ:

- Có chờ đến khi terminal hay đặt tối đa observation window?
- Workflow hết thời gian có tính là failure hay censored/pending?
- Khi kết quả đến muộn có cập nhật lại báo cáo lịch sử không?
- Nếu người dùng mở checkout rồi bỏ ngang, có xem là một attempt hợp lệ không?
- Khi người dùng refresh/retry, khóa de-dup là checkout_id hay session_id?

Không tự loại trừ trường hợp “khó” khỏi mẫu số để làm tỷ lệ đẹp hơn. Các trường hợp pending/censored phải được trình bày thành một nhóm riêng.

## 7. Event contract để nối hành trình nhiều dịch vụ

Muốn đo workflow, cần một khóa xuyên qua các sự kiện. `trace_id` rất hữu ích để debug request, nhưng có thể đổi khi job async chạy lại hoặc workflow kéo dài nhiều ngày. Do đó cần **business workflow ID bền vững**.

Ví dụ sự kiện nghiệp vụ:

~~~json
{
  "event_id": "evt-5f31",
  "event_type": "PaymentAuthorized",
  "event_version": 2,
  "producer": "payment-service",
  "workflow_type": "checkout",
  "workflow_id": "wf-10492",
  "order_id": "ord-10492",
  "payment_intent_id": "pi-775",
  "attempt_id": "pay-attempt-3",
  "occurred_at": "2026-11-12T02:14:31Z",
  "correlation_id": "wf-10492",
  "causation_id": "evt-5f29",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "attributes": {
    "payment_method_family": "card",
    "region": "apac",
    "currency": "VND"
  }
}
~~~

Các ID là ví dụ; hệ thống thật cần áp quy tắc bảo mật dữ liệu, không đưa token hoặc thông tin thẻ vào event. Tên producer và event version phải được hiểu nhất quán. `causation_id` cho biết sự kiện nào dẫn đến sự kiện này; `correlation_id` gắn một chuỗi liên quan; `workflow_id` định danh tiến trình nghiệp vụ.

### 7.1. Tập trường tối thiểu gợi ý

| Nhóm | Trường | Mục đích |
|---|---|---|
| Identity | `event_id`, `event_type`, `event_version` | De-dup và schema evolution |
| Process | `workflow_id`, `workflow_type`, `workflow_version` | Nối hành trình |
| Domain | `order_id` / `payment_intent_id` | Liên kết object nghiệp vụ |
| Causality | `correlation_id`, `causation_id` | Nối nguyên nhân |
| Time | `occurred_at`, `ingested_at` | Đo thời gian và phát hiện late event |
| Origin | `producer`, `environment`, `region` | Phân tích nơi phát |
| Outcome | `status`, `failure_reason_code` | Phân loại kết quả |
| Trace | `trace_id` / `span_id` nếu có | Drill down kỹ thuật |

Đừng đưa `user_id`, `order_id`, email hoặc `workflow_id` làm **metric label cho mọi time series**: cardinality nổ rất nhanh và có thể gây lộ dữ liệu. Giữ các ID chi tiết trong trace/log/event store đã phân quyền; metrics chỉ có dimension hữu hạn như outcome, service, region, payment method family.

### 7.2. Đặt tên event theo sự thật đã xảy ra

- `PaymentRequested` là lệnh/yêu cầu được phát ra, chưa chắc có kết quả.
- `PaymentAuthorized` là nhà cung cấp đã ủy quyền giao dịch.
- `PaymentCaptured` là mốc khác nếu hệ thống tách authorize/capture.
- `OrderCompleted` phải có điều kiện nghiệp vụ chặt.
- `OrderNotificationSent` chỉ nói hệ thống gửi, không chứng minh khách đã đọc.
- `RefundRequested` khác `RefundSucceeded`.

Chỉ số tính bằng một event mang nghĩa không rõ sẽ gây sai lệch xuyên nhiều dashboard.

## 8. Cách xây dựng trạng thái quy trình có thể đo

Có hai kiến trúc phổ biến:

**Orchestration:** một Workflow/Order orchestrator quản lý state machine, ra lệnh service và nhận kết quả. Dễ có bảng trạng thái tổng, nhưng orchestrator trở thành thành phần quan trọng cần bảo đảm khả dụng và replay.

**Choreography:** mỗi service phát event và phản ứng với event khác. Ít điều phối tập trung, nhưng cần một **workflow projection** đọc stream để suy ra trạng thái tổng; phải xử lý event đến trễ/lặp và khả năng reconcile với nguồn domain.

Dù chọn cách nào, state model cần có trạng thái chuyển hợp lệ, mốc thời gian, điều kiện terminal và bằng chứng bù trừ.

~~~text
CHECKOUT_STARTED
  -> ORDER_PLACED
  -> PAYMENT_AUTHORIZED
  -> INVENTORY_RESERVED
  -> FULFILLMENT_STARTED
  -> DELIVERED
  -> COMPLETED

PAYMENT_DECLINED -> FAILED
INVENTORY_REJECTED -> COMPENSATING -> COMPENSATED
DELIVERY_EXCEPTION -> NEEDS_ATTENTION -> COMPLETED | CANCELLED
~~~

Không đếm `COMPENSATED` như `COMPLETED` nếu mục tiêu là đơn hàng giao thành công. Tuy nhiên, có thể có metric khác “tỷ lệ xử lý thất bại được khôi phục an toàn” tính bù trừ thành công là kết quả vận hành tốt. Mỗi KPI cần một nghĩa duy nhất.

## 9. Nguồn dữ liệu đáng tin và pipeline đo lường

Một kiến trúc mẫu:

~~~mermaid
flowchart LR
    A[Domain services] --> O[Transactional outbox]
    O --> B[(Event broker)]
    B --> C[Idempotent consumer]
    C --> W[(Workflow state projection)]
    W --> M[Operational metrics]
    W --> D[(Warehouse / mart)]
    D --> R[Business dashboards]
    M --> X[Alerts]
    C --> T[Trace and log linkage]
~~~

### 9.1. Tránh mất sự kiện giữa DB và broker

Nếu Order Service ghi đơn vào DB rồi crash trước khi publish `OrderPlaced`, pipeline đo sẽ nghĩ chưa có đơn. **Transactional outbox** ghi thay đổi domain và một bản ghi outbox trong cùng transaction. Publisher sau đó gửi event; consumer phải idempotent vì event có thể được gửi lại.

Không có outbox cũng có thể dùng CDC hoặc hệ thống workflow có durability phù hợp, nhưng phải hiểu bảo đảm delivery và lỗ hổng khi crash. Không nên dùng “gửi metric/log” làm nguồn sự thật duy nhất cho giao dịch tài chính.

### 9.2. De-dup và exactly-once ở cấp nghiệp vụ

- Broker thường có thể redeliver, producer có thể retry; cùng `event_id` được gửi nhiều lần.
- Consumer lưu processed-event ID hoặc unique constraint trong transaction cùng update projection.
- Một workflow có thể có nhiều `PaymentAttempted` hợp lệ: không de-dup chỉ theo `order_id` nếu muốn đếm attempts.
- Completion của một workflow chỉ được đếm một lần theo `workflow_id`, dù event terminal phát lại.
- Khi replay lịch sử để sửa projection, chỉ số không được cộng lặp; nên recompute/idempotent upsert thay vì tăng bộ đếm mù.
- Source of truth cho tiền/giao dịch phải đối soát với hệ thống thanh toán/kế toán khi cần.

**“Exactly once delivery” ở một chặng broker không bảo đảm side effect đúng một lần** khi DB, broker và PSP nằm ở các giao dịch độc lập.

### 9.3. Event đến trễ, thiếu hoặc sai thứ tự

Một sự kiện `ShipmentDelivered` có thể đến trước `ShipmentCreated` do network/consumer delay. Projection không nên mặc định “không có ShipmentCreated thì không thể Delivered”; cần version/sequence, buffer/reconcile hoặc rule kiểm nguồn tùy domain.

Cần lưu:

- `event_time` và `ingestion_time` để đo freshness và watermark.
- Trạng thái “unknown/pending” khi thiếu bước, không tự suy luận thành success.
- Job reconciliation định kỳ với DB domain hoặc nhà cung cấp ngoài.
- DLQ/dead-letter monitoring, event schema validation và cảnh báo parsing failures.
- Chính sách late-arrival: được điều chỉnh báo cáo quá khứ tới thời điểm nào.

## 10. Định nghĩa funnel xuyên nhiều service

Funnel minh họa:

~~~text
CheckoutStarted  ->  OrderPlaced
                        -> PaymentAuthorized
                           -> InventoryReserved
                              -> OrderCompleted
~~~

Để funnel đúng:

1. Mỗi bước đếm **distinct workflow_id** hoặc khóa định nghĩa rõ, không đếm event messages.
2. Các bước phải cùng cohort và đi đúng state machine; không cộng event của order khác.
3. Khi có nhánh thay thế, ví dụ COD không có authorize thẻ, phải có funnel riêng hoặc định nghĩa bước “PaymentRequirementSatisfied”.
4. Đặt observation window đủ dài; báo cáo trạng thái pending riêng.
5. Phân tích drop-off ở bước nào, kết hợp reason code chuẩn hóa, không chỉ thấy tổng giảm.
6. Phân biệt conversion theo người dùng, session, attempt và đơn; các tập này không tương đương.

**Tỷ lệ chuyển bước** và **tỷ lệ toàn hành trình** mang thông tin khác nhau:

\[
\text{PaymentStepRate}
= \frac{\text{distinct workflows đạt PaymentAuthorized}}
{\text{distinct workflows đạt OrderPlaced và đủ điều kiện}}
\]

\[
\text{EndToEndRate}
= \frac{\text{distinct workflows đạt OrderCompleted}}
{\text{distinct CheckoutStarted hợp lệ đã đủ thời gian quan sát}}
\]

Nếu một đơn hỗ trợ trả bằng COD, nó không nên bị coi “lỗi thanh toán thẻ” vì không có `PaymentAuthorized`; định nghĩa phải phản ánh điều kiện nghiệp vụ.

## 11. Thời gian end-to-end và nút thắt

Thời gian hoàn thành là `terminal_at - started_at`, nhưng cần tách:

- **Active processing:** thực thi thực tế bên trong service.
- **Queue waiting:** chờ trong broker/job queue.
- **External dependency:** chờ PSP, đơn vị giao hàng, đối tác.
- **Human waiting:** chờ người duyệt hoặc khách bổ sung thông tin.
- **Retry/backoff:** các khoảng giãn để phục hồi lỗi.
- **Business hold:** chờ theo chính sách, ví dụ giữ hàng chờ khách thanh toán.

Ví dụ workflow:

~~~text
T0  10:00:00  CheckoutStarted
T1  10:00:01  OrderPlaced
T2  10:00:05  PaymentAuthorized
T3  10:00:07  InventoryReserved
T4  10:00:42  FulfillmentAccepted
T5  10:04:00  ShipmentCreated
T6  day+1     Delivered
~~~

Không tính thời gian giao hàng nhiều ngày vào SLO “checkout API hoàn tất dưới 2 giây”. Có thể cần hai SLO: **checkout accepted/confirmed** trong vài giây và **delivery fulfilled** trong số ngày cam kết. Đừng gộp thời gian do con người chờ với độ trễ CPU để chọn sai biện pháp.

### 11.1. P50, P95, P99 và SLA

- **P50** cho thấy trải nghiệm điển hình, không cho thấy đuôi chậm.
- **P95/P99** cho thấy nhóm workflow chậm nhất; cần số mẫu đủ lớn.
- **Mean** nhạy với outliers; phù hợp một số bài toán tổng chi phí nhưng không thay percentile.
- **% within deadline** thường dễ hành động hơn percentile khi có cam kết rõ.
- Báo cáo theo cohort/case mix; so sánh hai tuần có loại đơn khác nhau có thể làm biểu đồ lệch dù hiệu năng không đổi.

Trong luồng phân tán song song, tổng thời gian end-to-end **không bằng tổng latency của mọi span**. Nếu Inventory và Payment thực hiện song song, critical path quyết định thời gian. Span duration chỉ mô tả từng hoạt động; cần trace/correlation và event timestamps để phân biệt chờ queue, đồng bộ và đường song song.

## 12. Đo SLI/SLO nghiệp vụ

**SLI (Service Level Indicator)** là số đo định lượng; **SLO (Service Level Objective)** là mục tiêu theo cửa sổ thời gian; **SLA** là cam kết có hệ quả theo thỏa thuận. Với workflow, SLI nên gần hành trình người dùng.

Ví dụ minh họa:

| SLI | SLO giả định | Cửa sổ | Loại |
|---|---|---|---|
| Tỷ lệ checkout đạt xác nhận hoặc lỗi rõ ràng trong 30 giây | ≥ 99.5% | Rolling 28 ngày | Trải nghiệm checkout |
| Tỷ lệ paid orders không bị kẹt quá 10 phút ở bước giữ hàng | ≥ 99.9% | Rolling 28 ngày | Sức khỏe quy trình |
| Tỷ lệ đơn giao trước deadline đã hứa | ≥ 97% | Theo cohort giao hàng đủ thời gian | Kết quả fulfillment |
| Tỷ lệ refund hoàn tất trong thời gian cam kết | ≥ 99% | Theo cohort refund đủ thời gian | Khả năng phục hồi |

Các con số chỉ là ví dụ học tập; SLO thật cần dựa trên kỳ vọng người dùng, baseline, khối lượng, cost và quy trình hỗ trợ.

### 12.1. Chọn good events / valid events

Ví dụ “checkout xác nhận kịp thời”:

- **Valid events:** checkout attempts hợp lệ, loại bot/test/traffic nội bộ theo chính sách rõ.
- **Good events:** checkout nhận kết quả cuối có thể hiểu trong 30 giây, theo contract nghiệp vụ.
- **Bad events:** không trả kết quả, timeout, trạng thái treo quá 30 giây.
- **Not applicable:** attempt không hợp lệ bị chặn ở bước validation, nếu chính sách quy định không là workflow hợp lệ.

Cần quyết định: user hủy ngay có tính bad không; PSP từ chối hợp lệ có tính service unreliability không. Thông thường cần tách **kết quả nghiệp vụ không thành công nhưng được xử lý đúng** với **hệ thống không đưa ra kết quả đúng hạn**.

### 12.2. Error budget

Với SLO 99.5% trên 100.000 workflow hợp lệ trong một cửa sổ, error budget là 500 bad workflows. Nếu 200 workflow bị treo vì Inventory, đã tiêu thụ 40% ngân sách. Đo theo **số người/đơn bị ảnh hưởng**, không chỉ phần trăm API error của một service, giúp ưu tiên sự cố có tác động thực tế.

Với traffic thấp hoặc workflow kéo dài nhiều ngày, alert theo budget burn có thể nhiễu; kết hợp absolute counts, baseline và tiêu chí kinh doanh thay vì áp một công thức duy nhất cho mọi metric.

## 13. Instrumentation từ ứng dụng đến observability

Có hai đường đo bổ sung nhau:

**Operational instrumentation:** timer/counter/histogram từ service cho latency, error, queue lag và các bước; phục vụ realtime alert.

**Durable business events:** sự kiện trạng thái domain có ID và thời điểm; dùng tái dựng workflow, phân tích cohort, reconciliation và business reporting.

Không dùng một counter in-memory làm bằng chứng duy nhất về doanh thu hoặc số giao dịch đã thu tiền: process restart, scrape failure, replay và tranh chấp state có thể làm sai số.

### 13.1. Naming và labels

Đặt metric theo ý nghĩa ổn định:

~~~text
workflow_attempts_total{workflow="checkout",channel="web",region="apac"}
workflow_terminal_total{workflow="checkout",outcome="completed|failed|cancelled",region="apac"}
workflow_step_transitions_total{workflow="checkout",step="payment",result="success|failure"}
workflow_step_duration_seconds_bucket{workflow="checkout",step="inventory",le="..."}
workflow_stuck_active{workflow="checkout",state="payment_pending",region="apac"}
workflow_compensation_total{workflow="checkout",result="success|failure"}
business_event_ingest_lag_seconds{producer="payment-service"}
~~~

Các tên Prometheus ở đây là minh họa; tên histogram sau khi export phụ thuộc registry và cấu hình. Đặt **unit trong tên**, phân biệt counter với gauge, và chuẩn hóa outcome/reason code. `order_id`, `user_id`, email, raw URL, trace ID, payment intent ID không phù hợp để làm label vì cardinality và nhạy cảm; dùng exemplar hoặc trace/log liên kết thay thế.

### 13.2. Ví dụ Java/Spring Boot với Micrometer

Đo một bước xử lý từ góc nhìn service. Mã minh họa:

~~~java
package example.payment;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

@Component
public class PaymentMetrics {
    private final MeterRegistry registry;

    public PaymentMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAuthorization(
        String methodFamily,
        String result,
        long durationNanos
    ) {
        String safeMethod = switch (methodFamily) {
            case "card", "bank_transfer", "wallet" -> methodFamily;
            default -> "other";
        };
        String safeResult = switch (result) {
            case "success", "declined", "timeout", "error" -> result;
            default -> "unknown";
        };

        Counter.builder("payment.authorization.attempts")
            .tag("method_family", safeMethod)
            .tag("result", safeResult)
            .register(registry)
            .increment();

        Timer.builder("payment.authorization.duration")
            .tag("method_family", safeMethod)
            .tag("result", safeResult)
            .publishPercentileHistogram()
            .register(registry)
            .record(durationNanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Đếm **attempt** ở mã trên, không phải số order đã thanh toán thành công. Nếu service retry, counter có thể tăng nhiều lần trên một order; business completion phải dựa trên trạng thái domain de-duplicated. Chỉ dùng tags từ allowlist giá trị hữu hạn; không dùng exception message hoặc ID động làm tag.

Để đo cùng một workflow qua nhiều service, ghi `workflow_id` vào event/log/trace context; không truyền nó thành label metric. Với async messaging, dùng context propagation/span links phù hợp, và luôn có workflow ID bền vững cho phân tích dài hạn.

## 14. PromQL minh họa cho metric vận hành

### 14.1. Thông lượng workflow hoàn tất

~~~promql
sum(
  rate(workflow_terminal_total{
    workflow="checkout", outcome="completed"
  }[5m])
)
~~~

Đây là thông lượng hoàn tất/giây theo thời gian xảy ra terminal outcome. Nó không trực tiếp là completion rate của cohort bắt đầu trong cùng năm phút.

### 14.2. Tỷ lệ kết quả completed trong số terminal outcomes

~~~promql
sum(rate(workflow_terminal_total{
  workflow="checkout", outcome="completed"
}[15m]))
/
clamp_min(
  sum(rate(workflow_terminal_total{
    workflow="checkout"
  }[15m])),
  0.000001
)
~~~

Đây là tỷ lệ **trong các workflow đã kết thúc** của cửa sổ quan sát, không phải end-to-end completion rate trên toàn bộ attempts đã bắt đầu. Pending workflow không nằm trong mẫu số. Khi không có traffic, dashboard nên hiển thị `no data` hoặc một trạng thái riêng, thay vì diễn giải số 0 hoặc phép chia ép mẫu số thành kết quả có nghĩa.

### 14.3. P95 latency theo histogram bucket

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(workflow_step_duration_seconds_bucket{
      workflow="checkout", step="payment"
    }[10m])
  )
)
~~~

Ví dụ dùng histogram cổ điển với bucket `le`. Nếu dùng native histogram, truy vấn và khả năng export khác. Kết quả phản ánh thời gian bước Payment đã được quan sát, không bao gồm các workflow đang kẹt chưa hoàn tất nếu timer chỉ ghi khi hoàn thành.

### 14.4. Stuck workflow

~~~promql
sum by (state, region) (
  workflow_stuck_active{workflow="checkout"}
)
~~~

Đây là gauge do workflow projection phát ra; muốn đúng phải cập nhật theo trạng thái hiện hành, không chỉ increment khi thấy một sự kiện rồi không decrement. Khi dịch vụ giám sát restart, phải tái dựng từ durable state để tránh mất số workflow đang mắc kẹt.

PromQL phù hợp observability realtime. Các phép tính distinct workflow/cohort phức tạp nên lấy từ state store hoặc warehouse, không ép Prometheus lưu một time series cho mỗi workflow.

## 15. SQL tái dựng metric theo workflow ID

Giả sử warehouse có bảng sự kiện:

~~~sql
CREATE TABLE workflow_events (
  event_id TEXT NOT NULL,
  workflow_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL,
  producer TEXT NOT NULL,
  event_version INTEGER NOT NULL,
  environment TEXT NOT NULL
);
~~~

Đây là cấu trúc minh họa, không phải schema đủ cho production. Cần phân loại dữ liệu, index/partition, quyền truy cập và cơ chế bảo đảm uniqueness ở pipeline thật.

### 15.1. De-dup trước khi tính cohort

Ví dụ PostgreSQL tính cohort bắt đầu từ 2026-11-01 đến trước 2026-11-02, chỉ xét workflow đã có ít nhất 72 giờ để quan sát (cửa sổ ví dụ; production chọn theo SLA):

~~~sql
WITH dedup AS (
  SELECT *
  FROM (
    SELECT
      e.*,
      ROW_NUMBER() OVER (
        PARTITION BY event_id
        ORDER BY ingested_at ASC
      ) AS rn
    FROM workflow_events e
    WHERE environment = 'production'
  ) x
  WHERE rn = 1
),
per_workflow AS (
  SELECT
    workflow_id,
    MIN(occurred_at) FILTER (
      WHERE event_type = 'CheckoutStarted'
    ) AS started_at,
    MIN(occurred_at) FILTER (
      WHERE event_type = 'OrderPlaced'
    ) AS placed_at,
    MIN(occurred_at) FILTER (
      WHERE event_type = 'OrderCompleted'
    ) AS completed_at,
    MIN(occurred_at) FILTER (
      WHERE event_type IN ('OrderFailed','OrderCancelled')
    ) AS failed_or_cancelled_at
  FROM dedup
  GROUP BY workflow_id
),
cohort AS (
  SELECT *
  FROM per_workflow
  WHERE started_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
    AND started_at <  TIMESTAMPTZ '2026-11-02 00:00:00+00'
    AND started_at < CURRENT_TIMESTAMP - INTERVAL '72 hours'
)
SELECT
  COUNT(*) AS checkout_started,
  COUNT(*) FILTER (
    WHERE placed_at IS NOT NULL
  ) AS order_placed,
  COUNT(*) FILTER (
    WHERE completed_at IS NOT NULL
  ) AS order_completed,
  COUNT(*) FILTER (
    WHERE failed_or_cancelled_at IS NOT NULL
  ) AS failed_or_cancelled,
  COUNT(*) FILTER (
    WHERE completed_at IS NULL
      AND failed_or_cancelled_at IS NULL
  ) AS still_pending,
  ROUND(
    COUNT(*) FILTER (WHERE completed_at IS NOT NULL)
    * 100.0 / NULLIF(COUNT(*), 0),
    2
  ) AS completion_rate_pct
FROM cohort;
~~~

Với hệ thống thật, thêm điều kiện state transition và terminal status theo source of truth; ví dụ trên sẽ đếm cả completed và cancelled nếu dữ liệu mâu thuẫn. Dữ liệu mâu thuẫn phải được gắn cờ và sửa projection, không tự xem hai terminal outcomes là bình thường. `MIN` chọn mốc đầu tiên; một số nghiệp vụ có legitimate retry/cycle cần logic khác.

### 15.2. Vì sao JOIN thẳng từng event dễ sai?

Nếu một workflow có 2 `PaymentAttempted`, 3 `InventoryRetried` và 2 `NotificationSent`, JOIN trực tiếp các bảng event theo workflow ID có thể sinh 2 × 3 × 2 = 12 dòng. `COUNT(*)` sẽ phóng đại số đơn và doanh thu. Thay vào đó:

1. De-dup event theo identity.
2. Chuẩn hóa thành một hàng trên workflow hoặc một hàng trên step/attempt đúng granularity.
3. Aggregate từng bảng con trước khi JOIN.
4. Dùng distinct workflow ID khi công thức định nghĩa trên workflow.
5. Kiểm tra tổng tiền và tổng order với domain source of truth.

## 16. Đo hiệu quả bước và phân tích nút thắt

Một funnel cho biết ở đâu kết quả giảm; nhưng không đủ chỉ ra **nguyên nhân**. Cần phân loại step outcome:

| Bước | Success | Failure/decline | Pending | Thời gian cần xem |
|---|---|---|---|---|
| Create order | OrderPlaced | ValidationRejected | — | Request latency |
| Payment | Authorized/Captured | ProviderDeclined, Timeout | AwaitingPSP | PSP latency, retry wait |
| Inventory | Reserved | OutOfStock, Conflict | ReservationPending | Queue wait, DB conflict |
| Fulfillment | Accepted | PickingFailed | Queueing | Dispatch delay |
| Delivery | Delivered | Lost/Returned | InTransit | Lead time, promise adherence |
| Compensation | RefundSucceeded | RefundFailed | RefundPending | Recovery time |

**Nhánh lỗi hợp lệ** (khách không đủ tiền, hàng hết) khác **sự cố nền tảng** (timeout, event thất lạc, duplicate charge). Một dashboard tốt hiển thị cả loại kết quả và reason code để tránh quy lỗi kỹ thuật cho quyết định nghiệp vụ hợp lệ.

### 16.1. Phân rã E2E latency

Đo các mốc thời gian theo trạng thái:

- `time_to_order_placed`: bắt đầu → OrderPlaced.
- `time_to_payment_authorized`: OrderPlaced → PaymentAuthorized.
- `time_to_inventory_reserved`: PaymentAuthorized → InventoryReserved.
- `time_to_fulfillment_started`: InventoryReserved → FulfillmentStarted.
- `time_to_shipment_created`: FulfillmentStarted → ShipmentCreated.
- `time_to_delivered`: ShipmentCreated → Delivered.

Đây là thời gian giữa mốc nghiệp vụ, thường gồm chờ và retry. Nếu muốn đo latency thực thi, dùng traces/timers kỹ thuật riêng. Trong các nhánh song song, không cộng thời gian của hai bước song song để suy ra tổng E2E.

### 16.2. Đo queue, retry và saga compensation

Cần quan sát:

- Queue depth, oldest message age, consumer lag, retry attempts.
- Số workflow chuyển sang `COMPENSATING` và số chờ quá SLA.
- Chi phí bù trừ: refund, hủy giữ hàng, hỗ trợ thủ công.
- Số workflow phải replay hoặc reconcile để khôi phục.
- Số thông điệp bị gửi lặp và số **side effects** thực sự bị lặp; hai con số khác nhau.
- Tỉ lệ manual intervention và thời gian để đóng case.

Một consumer xử lý 10.000 messages/phút không chứng minh có 10.000 đơn hoàn tất/phút: có thể phần lớn là retries hoặc technical events.

## 17. Dashboard theo người sử dụng

Không nên nhồi tất cả metric vào một màn hình. Ba góc nhìn hỗ trợ nhau:

### 17.1. Dashboard sản phẩm và kinh doanh

- Tổng số checkout attempts hợp lệ, completion/conversion theo cohort.
- Giá trị đơn đã hoàn tất theo định nghĩa tài chính.
- Payment success theo payment method/channel.
- On-time delivery và customer-visible errors.
- Trend theo ngày/tuần, release hoặc cohort; chú thích chiến dịch và thay đổi định nghĩa.
- Tách “pending/chưa đủ tuổi” khỏi “failed”.

### 17.2. Dashboard vận hành workflow

- Active workflows theo state/age bucket.
- Stuck workflows và oldest age, phân nhóm theo region/service.
- Compensation pending, refund pending, reconciliation mismatch.
- Throughput bắt đầu/kết thúc, queue lag và event freshness.
- Đơn vị/on-call owner và runbook cho từng loại kẹt.
- Một liên kết drill down có kiểm soát tới workflow instance.

### 17.3. Dashboard kỹ thuật

- Request/error/latency/saturation của từng service.
- Span waterfall và async event lineage.
- Producer/consumer errors, DLQ, retry, backpressure.
- Dependency latency và timeout, circuit breaker status.
- Deployment/config revision đang chạy để nối thời điểm biến động.
- Correlation giữa KPI nghiệp vụ xấu và lỗi kỹ thuật.

Mọi dashboard cần nhãn: khoảng thời gian, timezone, cohort/window, data freshness, sampling, nguồn, owner và version định nghĩa. Nếu một đường biểu diễn chỉ được tính trên 20 đơn, nên hiển thị số mẫu.

## 18. Cảnh báo dựa trên tác động người dùng

Một cảnh báo tốt trả lời “ai bị ảnh hưởng, đến mức nào, ai sẽ xử lý, làm gì trước?”. Không phát alert chỉ vì có một metric bất kỳ vượt giá trị tùy tiện.

Ví dụ rule vận hành minh họa:

| Tín hiệu | Điều kiện ví dụ | Hành động |
|---|---|---|
| Workflow kẹt sau thu tiền | Paid order quá 10 phút không có inventory outcome, ≥ 20 đơn | Page on-call; kiểm event backlog và trạng thái PSP |
| Checkout reliability | Bad outcome tăng, vượt burn-rate budget nhiều cửa sổ | Incident; đánh giá release/region |
| Payment mismatch | Bất kỳ charge trùng xác nhận hoặc mismatch tài chính mức nghiêm trọng | Escalate Payment/Finance theo policy |
| Compensation backlog | RefundPending vượt cam kết | Tạo case và đối soát PSP |
| Event freshness | P95 ingest lag vượt ngưỡng | Điều tra pipeline; đánh dấu dashboard stale |
| Conversion drop | Giảm rõ so với baseline có số mẫu đủ | Điều tra cohort, kênh, release, campaign |

Ngưỡng phải điều chỉnh theo volume và hành vi thực tế. Hệ thống 10 requests/ngày không thể dùng cùng rule phần trăm với hệ thống 100.000 requests/phút. Cần debounce, rolling windows, seasonality, minimum sample và quy tắc mất dữ liệu.

### 18.1. Runbook khi completion rate đột ngột giảm

1. Xác nhận metric có dữ liệu mới, dashboard không stale và denominator đúng cohort.
2. Phân loại ảnh hưởng theo region, channel, phương thức thanh toán, app/config version.
3. Xem workflow states và step failure reason để tìm bước làm rơi đơn.
4. Kiểm độ trễ broker, trace tiêu biểu, lỗi downstream, rollback/canary gần nhất.
5. Nếu có thu tiền, đối soát payment intent trước khi retry để tránh double charge.
6. Chọn hành động: dừng rollout, giảm tải, điều chỉnh retry có giới hạn, sửa consumer, replay an toàn, mở case thủ công.
7. Theo dõi phục hồi bằng business outcome và stuck backlog, không chỉ CPU và HTTP success.
8. Sau sự cố, bổ sung test, detection và định nghĩa nếu metric chưa phản ánh đúng tác động.

Không để workflow mất kết quả chỉ vì một alert đã im lặng sau khi queue hồi phục. Cần kiểm chứng các workflow tồn đọng cũng đã được xử lý.

## 19. Dữ liệu chất lượng thấp có thể tạo quyết định sai

Các tình huống làm metric lệch thường xuất hiện ở ranh giới dịch vụ và pipeline:

| Vấn đề | Hệ quả | Kiểm soát |
|---|---|---|
| Event redelivery | Đếm trùng completed/payment | De-dup bằng event ID và grain đúng |
| Thiếu event do crash | Bỏ sót đơn/step | Transactional outbox, CDC hoặc reconciliation |
| Late event | Báo cáo lịch sử thay đổi | Event time + watermark/recompute |
| Clock skew | Duration âm hoặc sai | Đồng bộ thời gian, kiểm anomaly và sequence |
| Producer đổi ý nghĩa event | Trend gãy sau release | Schema/version và metric-definition governance |
| Join fan-out | Phóng đại số đơn/doanh thu | Aggregate theo workflow trước JOIN |
| Không chuẩn hóa timezone | Sai ranh giới ngày/tuần | UTC nội bộ + timezone báo cáo rõ |
| Missing correlation ID | Không nối được hành trình | Quy ước propagation và completeness check |
| Sampling trace | Mất một số hành trình khi dùng trace để đếm | Dựa vào durable events cho totals |
| Dashboard stale | Cảnh báo giả hoặc bỏ lỡ sự cố | Freshness SLI và trạng thái “dữ liệu trễ” |

### 19.1. Data quality SLI

Cần quan sát pipeline đo lường như một hệ thống:

- **Completeness:** % workflow có event start, terminal hoặc state hợp lệ đúng hạn.
- **Uniqueness:** % event IDs không trùng sau ingestion.
- **Validity:** % event hợp schema, enum, required fields.
- **Freshness:** độ trễ `ingested_at - occurred_at` theo P95/P99.
- **Consistency:** sai lệch giữa workflow projection và Order/Payment source of truth.
- **Timeliness:** % báo cáo cập nhật trước thời điểm cam kết.
- **Lineage:** có biết version/schema/producer tạo số liệu không.

Dữ liệu không đủ tin cậy phải hiển thị tình trạng chất lượng hoặc tạm ngừng dùng cho quyết định rủi ro cao, thay vì âm thầm suy đoán giá trị còn thiếu.

## 20. Quyền truy cập, riêng tư và chi phí observability

Business metrics có thể chứa thông tin khách hàng, thanh toán và tenant. Cần cân bằng khả năng điều tra với quyền riêng tư:

- Không đưa email, số điện thoại, số thẻ, token, địa chỉ cá nhân hoặc ID định danh vào metric labels.
- Workflow ID được đưa vào event/trace/log có phân quyền, retention và audit; không hiển thị đại trà trên dashboard công khai.
- Dùng dimension tổng hợp như channel, region, currency, payment method family; cân nhắc nguy cơ tái nhận diện ở nhóm quá nhỏ.
- Phân quyền truy cập event raw và warehouse theo vai trò; dữ liệu nhạy cảm cần masking/tokenization phù hợp.
- Chỉ giữ dữ liệu đủ lâu theo yêu cầu nghiệp vụ/pháp lý, có chiến lược xóa và lưu trữ.
- Metric cardinality cao làm tăng chi phí time series; log/tracing cũng cần sampling và retention chính sách.
- Với sự kiện tài chính, bảo đảm đối soát và audit trail thay vì dựa trên dashboard sampled.
- Khi phân tích tenant, dùng warehouse truy vấn có kiểm soát hoặc aggregate theo nhóm, tránh mỗi tenant một label metric nếu số lượng rất lớn.

## 21. Ví dụ tính toán end-to-end với dữ liệu nhất quán

Giả sử một cohort **1.000 checkout attempts hợp lệ** đã qua đủ thời gian quan sát và mỗi attempt có một workflow ID riêng. Sau khi loại duplicate event và đối soát state machine:

| Mốc | Số workflow | Ý nghĩa |
|---|---:|---|
| CheckoutStarted | 1.000 | Tập cohort |
| OrderPlaced | 800 | 200 attempt không tạo đơn |
| PaymentAuthorized | 760 | 40 order không được authorize |
| InventoryReserved | 740 | 20 order đã authorize nhưng giữ hàng thất bại |
| OrderCompleted | 710 | 710 order đạt terminal success |
| Post-reservation failed/cancelled | 30 | 30 order đã reserve nhưng không hoàn tất |

Giả sử mọi workflow đều đã đạt terminal state hoặc được phân loại kết cục tương ứng. Các số trên là phép đếm **distinct workflow ID**, không phải số event. Khi đó:

\[
\text{CheckoutConversion}=800/1000=80\%
\]

\[
\text{PaymentAuthorizationRate}\mid_{\text{OrderPlaced}}
=760/800=95\%
\]

\[
\text{InventoryReservationRate}\mid_{\text{PaymentAuthorized}}
=740/760\approx97.37\%
\]

\[
\text{OrderCompletionRate}\mid_{\text{CheckoutStarted}}
=710/1000=71\%
\]

\[
\text{CompletionAfterOrderPlaced}
=710/800=88.75\%
\]

Một người có thể thấy Payment authorize 95% và tưởng hệ thống gần hoàn hảo, nhưng chỉ **71%** checkout attempts dẫn đến đơn hoàn tất. Khoảng cách này buộc nhóm xem cả drop-off phía trước Payment, Inventory, Fulfillment và các tình huống hủy sau giữ hàng.

Nếu 690 trong 710 đơn hoàn tất được giao trước deadline, **on-time among completed** là `690/710 ≈ 97.18%`. Nếu báo cáo trên tất cả đơn đã reserve có kết cục, đó là `690/740 ≈ 93.24%`; hai con số dùng mẫu số khác nhau, không thể chỉ ghi chung “on-time rate”.

### 21.1. Những gì bảng funnel chưa nói

- Có bao nhiêu refund/compensation sau 20 inventory failures?
- 30 đơn sau reserve không hoàn tất là hủy tự nguyện, lỗi giao hàng hay sự cố kỹ thuật?
- Những checkout không tạo đơn là người dùng bỏ dở hay lỗi hệ thống?
- Các nhóm channel/region có tỷ lệ giống nhau không?
- P95 end-to-end duration và thời gian đợi queue ra sao?
- Có bao nhiêu workflow cần manual intervention nhưng cuối cùng vẫn được hoàn tất?

Bổ sung outcome reason, compensation metrics, E2E duration và phân tích cohort để trả lời, tránh kết luận vội từ một tỷ lệ duy nhất.

## 22. Áp dụng vào quy trình Saga

Saga gồm nhiều local transaction và hành động bù trừ khi một bước lỗi. Metric cần theo dõi cả **kết quả mục tiêu** và **khả năng phục hồi**.

Ví dụ luồng:

~~~text
OrderPlaced
 -> PaymentCaptured
 -> InventoryReserveFailed
 -> RefundRequested
 -> RefundSucceeded
 -> OrderCompensated
~~~

Điều cần đo:

1. **Primary success:** đơn có đạt trạng thái hoàn tất đã định nghĩa không?
2. **Recovery success:** khi primary flow thất bại, compensation có hoàn tất đúng hạn không?
3. **Recovery latency:** từ phát hiện lỗi đến hoàn tất bù trừ.
4. **Residual risk:** có workflow nào đã thu tiền nhưng không giao hàng và chưa hoàn tiền không?
5. **Manual intervention:** case nào cần con người và bao lâu để xử lý.
6. **Cost:** số giao dịch bổ sung, phí hoàn tiền, tài nguyên và hỗ trợ.

Một flow được bù trừ thành công là tín hiệu resilience tích cực, **không biến giao dịch ban đầu thành order completed**. Hai metric nên được trình bày song song.

## 23. Làm việc với hệ thống ngoài và bước con người

Không phải mọi kết quả đều diễn ra trong microservices của tổ chức. Payment Provider, đơn vị vận chuyển, người kiểm duyệt hay khách hàng xác nhận có thể chậm hoặc gửi callback sai thời điểm. Cần:

- Lưu external correlation ID và đối chiếu với workflow ID nội bộ.
- Phân biệt thời điểm service gửi lệnh, đối tác nhận và đối tác xác nhận.
- Có retry/callback dedup và cơ chế poll/reconcile độc lập khi callback thất lạc.
- Gắn trạng thái `WAITING_EXTERNAL` hoặc `WAITING_HUMAN` nếu nó có nghĩa nghiệp vụ.
- Dùng SLA riêng cho từng đối tác và cam kết tổng với người dùng.
- Đo external failure riêng, nhưng vẫn giữ trách nhiệm đưa workflow tới kết cục rõ cho khách.

Ví dụ KPI giao hàng không chỉ tính từ lúc Shipping Service phát `ShipmentCreated` nếu trải nghiệm khách bắt đầu ngay khi đặt hàng. Hai thước đo có thể cùng tồn tại: logistics transit time và customer order-to-delivery time.

## 24. So sánh theo phiên bản và tìm nguyên nhân

Gắn app version, config revision hoặc deployment generation vào metadata để đối chiếu khi thay đổi hành vi, nhưng phân tích phải tránh thiên lệch.

Ví dụ sau khi release Order Service v2:

- Completion rate giảm ở region APAC nhưng không giảm EU.
- Payment step rate ổn định, Inventory reservation giảm.
- Queue lag `order.placed` tăng và event schema validation failures tăng.
- Version 2 phát field mới; consumer Inventory version cũ reject event.
- Sửa contract/consumer hoặc rollback release, sau đó đo lại completion của cohort mới.

Đây là chuỗi suy luận dựa trên dữ liệu: **business KPI → step metric → technical symptom → deployment/version context**. Việc tương quan với một release chưa chứng minh quan hệ nhân quả; cần so sánh cohort, case mix, traffic và kiểm chứng can thiệp.

### 24.1. Tránh Simpson’s paradox

Conversion toàn hệ thống có thể giảm vì tỷ trọng traffic từ kênh khó chuyển đổi tăng, dù conversion của từng kênh không đổi. Khi so sánh, phân tích ít nhất:

- Channel: web, mobile, đối tác.
- Region và timezone.
- Payment method family.
- New/returning customer khi có cơ sở pháp lý và nguồn dữ liệu.
- Order value band và loại sản phẩm.
- App/config revision và thời gian rollout.
- Điều kiện đủ để đưa vào mẫu số.

Đừng phân mảnh đến mức mỗi nhóm chỉ có vài event, làm tỷ lệ dao động vô nghĩa hoặc lộ dữ liệu.

## 25. Quy trình triển khai metric catalog trong nhóm

Một trình tự thực hành:

**Bước 1 — Chọn một hành trình.** Ví dụ CheckoutStarted → OrderCompleted. Vẽ service, broker, DB, external callbacks, nhánh lỗi và compensation.

**Bước 2 — Chốt outcome.** Ghi điều kiện chính xác cho success, failure, cancel, pending, compensated, điều kiện loại trừ và mẫu số.

**Bước 3 — Tạo event contract.** Có workflow ID, event ID, version, thời điểm, producer, outcome và causation. Xác định hệ sở hữu từng sự kiện.

**Bước 4 — Xây projection và reconciliation.** Dedup, state transition, terminal semantics, late event handling, đối soát nguồn thật.

**Bước 5 — Định nghĩa metric.** Công thức, cohort, cửa sổ, dimension, đơn vị, owner, SLO, nguồn và data freshness.

**Bước 6 — Instrument và kiểm thử.** Unit/integration test sự kiện, duplicate, replay, out-of-order, timeout, compensation, rolling version và correlation ID.

**Bước 7 — Dashboard và alert.** Có lớp business/workflow/technical, drill down theo workflow, alert action-oriented và runbook.

**Bước 8 — Vận hành.** Theo dõi chất lượng dữ liệu, schema changes, review KPI khi nghiệp vụ thay đổi, đối soát và đào tạo on-call.

Các metric thuộc tổ chức nên có **metric owner**, **technical owner**, **data steward** và người được hỏi khi cần thay đổi định nghĩa. Thay đổi denominator là thay đổi ý nghĩa KPI, cần công bố và versioning tương tự đổi contract.

## 26. Anti-patterns thường gặp

1. **Chỉ đo HTTP 200 ở từng service.** Một request được nhận chưa chắc workflow hoàn tất; đo terminal outcome.
2. **Đếm event messages thay vì business instances.** Retry/redelivery làm phóng đại kết quả; dedup theo event/attempt/workflow đúng grain.
3. **Lấy completed hôm nay chia started hôm nay.** Hai cohort khác nhau; định nghĩa start-cohort hoặc event-window nhất quán.
4. **Không có trạng thái pending.** Workflow đang chờ bị gán sai thành failed hoặc bỏ sót hoàn toàn.
5. **Chỉ instrument happy path.** Thiếu declined, timeout, compensate và manual intervention nên không nhìn thấy thất bại thật.
6. **Đếm doanh thu từ counter trong memory.** Restart và sampling làm sai; đối soát dữ liệu giao dịch từ nguồn tài chính.
7. **Dùng trace ID làm khóa nghiệp vụ duy nhất.** Async và workflow kéo dài tạo nhiều trace; dùng workflow ID bền vững.
8. **Đưa order ID/user ID vào Prometheus labels.** Tạo cardinality cao, rủi ro bảo mật và chi phí.
9. **Không ghi data freshness.** Dashboard chậm bị diễn giải thành business crash.
10. **Gộp decline hợp lệ với lỗi hạ tầng.** Phân biệt kết quả kinh doanh và reliability.
11. **Không theo dõi compensation.** Hệ thống mất đơn nhưng tiền chưa trả vẫn không thấy trên bảng success rate.
12. **Metric đổi nghĩa theo release mà không version.** Trend qua thời gian không thể so sánh; cần contract và annotation.
13. **Alert phần trăm khi ít traffic.** Một lỗi trong hai đơn tạo 50%; dùng số mẫu, minimum count và rolling window.
14. **Chỉ nhìn trung bình latency.** Workflow kẹt lâu bị chìm; đo tail latency, age bucket và stuck count.
15. **Không kiểm tra trạng thái sau rollback.** API có thể hồi phục nhưng backlog còn hàng nghìn workflow; theo dõi đến terminal outcome.
16. **Số liệu đẹp hơn bằng cách loại những case khó.** Mẫu số phải công khai, các ngoại lệ được báo riêng.

## 27. Bài tập thực hành

### Bài A — Thiết kế metric cho Checkout

Một khách vào trang thanh toán, tạo order, authorize tiền, giữ hàng và nhận confirmation. Hãy vẽ state machine gồm success, payment declined, inventory failed, cancelled và pending. Tạo catalog ít nhất sáu metric với công thức, denominator, owner và source of truth.

**Gợi ý:** có cả completion rate trên checkout-start cohort, payment authorization theo eligible intents, stuck paid orders và compensation completion. Giải thích rõ 202 Accepted và 200 OK khác business success thế nào.

### Bài B — Tính funnel từ dữ liệu

Một cohort có 2.000 CheckoutStarted, 1.500 OrderPlaced, 1.425 PaymentAuthorized, 1.360 InventoryReserved, 1.300 OrderCompleted, 60 case sau reserve bị hủy/thất bại. Hãy tính conversion theo từng bước và end-to-end; xác định 75 order đặt mà chưa authorize nên kiểm reason code nào.

**Gợi ý:** dùng distinct workflow ID; các tỷ lệ khác nhau phải ghi rõ mẫu số và cửa sổ.

### Bài C — Xử lý replay

Consumer nhận `OrderCompleted(event_id=E1, workflow_id=W1)` ba lần. Một lần khác nhận `OrderCompleted(event_id=E2, workflow_id=W1)` do producer phát lại bằng ID mới. Nêu quy tắc dedup event ID, cách bảo đảm chỉ có một terminal outcome trên workflow ID và phương án audit dữ liệu bất thường.

### Bài D — Độ trễ và kẹt

Order chờ Payment 200 ms, Inventory 150 ms, Fulfillment queue 20 phút, Shipping tạo mã 2 phút. P95 riêng từng API rất thấp. Hãy xác định vì sao tổng thời gian trải nghiệm vẫn kém, cần metric nào về queue age, step duration, workflow state và deadline.

### Bài E — Sự cố sau release

Sau khi deploy schema event v3, completion rate giảm 8% trong khi Order API 2xx giữ nguyên. Lập quy trình kiểm freshness, cohort, consumer schema errors, DLQ, lag, effective version và replay; nêu điều kiện an toàn để rollback.

## 28. Checklist dùng trong hệ thống thật

- [ ] Có một định nghĩa workflow start, terminal success, failure, cancelled, compensated và pending.
- [ ] Có workflow ID bền vững, event ID, event version, occurred_at và producer trên sự kiện quan trọng.
- [ ] Metric catalog ghi rõ tử số/mẫu số, cohort/window, units, exclusions và owner.
- [ ] Tách business outcome, workflow health và technical health; có drill-down giữa các lớp.
- [ ] Các nhánh retry, duplicate, timeout, external callback, manual step và compensation đều được đo.
- [ ] Event pipeline idempotent, có late-arrival policy, watermark hoặc reconciliation phù hợp.
- [ ] Có nguồn sự thật cho trạng thái cuối và tài chính; không dùng sampled trace/counter để quyết toán.
- [ ] Đo E2E latency, state age, stuck workflow, completion và error reason, không chỉ HTTP latency.
- [ ] SLI/SLO bám tác động người dùng, có observation window và dữ liệu đủ tin cậy.
- [ ] Alerts có ngưỡng, minimum sample, owner, runbook và hành động tiếp theo rõ.
- [ ] Không đưa PII hoặc ID động vào metric label; đã phân quyền event/trace và dashboard.
- [ ] Version event contract/metric definition, ghi release/config revision và data freshness.
- [ ] Có dashboard theo business, vận hành workflow và kỹ thuật; hiển thị pending/censored rõ.
- [ ] Có kiểm thử duplicate/out-of-order/missing event, reconciliation và thay đổi version.
- [ ] Sau incident hoặc rollout, xác nhận backlog được xử lý, không chỉ service trở lại màu xanh.

## 29. Ghi nhớ

Một quy trình liên dịch vụ chỉ thật sự khỏe khi **người dùng nhận đúng kết quả, đúng hạn và hệ thống giải quyết được những trường hợp lỗi hoặc còn dang dở**. Muốn đo điều đó, hãy bắt đầu từ outcome và mẫu số, gắn workflow ID xuyên các bước, phát sự kiện có hợp đồng, tái dựng state bền vững, xử lý retry/late events, rồi liên kết metric nghiệp vụ với trace và chỉ số kỹ thuật.

Khi một KPI đổi hướng, câu hỏi hữu ích không phải chỉ là “service nào đang đỏ?”, mà là: **workflow nào bị ảnh hưởng, ở trạng thái nào, bao nhiêu người/đơn bị tác động, đâu là nguyên nhân, và chúng ta xác minh phục hồi bằng kết quả nghiệp vụ ra sao?**