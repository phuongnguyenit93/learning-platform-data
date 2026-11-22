# Thiết kế đối soát và sửa sai sau tác dụng phụ từng phần

## 1. Bài toán: một request REST có thể để lại nhiều tác dụng phụ

Một API thương mại điện tử nhận `POST /orders`. Để hoàn tất một đơn, hệ thống có thể phải:

1. Ghi đơn hàng vào cơ sở dữ liệu cục bộ.
2. Giữ tồn kho qua Inventory Service.
3. Ủy quyền hoặc thu tiền qua Payment Provider.
4. Đặt vận chuyển và phát thông báo cho người mua.

Các bước này thường đi qua **nhiều cơ sở dữ liệu hoặc hệ thống bên ngoài**. Không có một transaction ACID chung bảo đảm tất cả cùng commit hoặc cùng rollback. Nếu Inventory giữ hàng thành công, Payment thu tiền thành công nhưng Orders API mất kết nối trước khi ghi kết quả, ta có thể gặp trạng thái:

~~~text
Orders DB:       PENDING_PAYMENT
Inventory API:   RESERVATION_CONFIRMED
Payment API:     CAPTURED
REST client:     timeout / không rõ kết quả
~~~

Client không biết đơn đã thành công hay chưa; server cục bộ cũng chưa chắc biết kết quả thanh toán. Retry mù có thể **thu tiền lần hai**. Đánh dấu order `FAILED` có thể làm khách nghĩ không bị thu tiền. Hoàn tiền ngay khi chưa đối chiếu cũng có thể tạo hoàn tiền sai.

Chủ đề của bài này là **đối soát (reconciliation)** và **sửa sai (remediation)** sau những tác dụng phụ xảy ra từng phần. Đây là lớp thiết kế tiếp nối các khái niệm REST resource, HTTP status, idempotency, transaction, event và Saga. Mục đích không phải mô phỏng một distributed transaction lý tưởng; mục đích là bảo đảm hệ thống **phát hiện sai lệch, giữ bằng chứng, hội tụ về trạng thái hợp lệ và có đường xử lý khi tự động không an toàn**.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt lỗi rõ kết quả với **kết quả chưa biết** sau timeout hoặc crash.
- Thiết kế trạng thái nghiệp vụ, effect intent, bằng chứng và bất biến để nhận biết “một phần đã thành công”.
- Tổ chức outbox, inbox, idempotency và reconciliation worker không tạo trùng tác dụng phụ.
- Chọn giữa hoàn tất phần còn thiếu, bù trừ (compensation) và xử lý thủ công dựa trên bằng chứng.
- Thiết kế REST API có trạng thái xử lý dài, HTTP/Java/Spring/SQL và ma trận kiểm thử tình huống lỗi.
- Theo dõi các đơn cần đối soát bằng chỉ số vận hành, audit và cảnh báo.

## 2. Phân biệt transaction, Saga, đối soát và bù trừ

| Cơ chế | Giải quyết việc gì? | Giới hạn |
|---|---|---|
| Transaction cơ sở dữ liệu cục bộ | Commit/rollback nguyên tử những thay đổi trong **cùng** DB | Không rollback được chuyển khoản hoặc API khác đã thực hiện |
| Transactional outbox | Ghi thay đổi nội bộ và **ý định phát thông điệp** trong cùng DB transaction | Publisher vẫn có thể gửi trùng; consumer cần idempotency |
| Saga | Điều phối nhiều bước với trạng thái và hành động bù trừ | Compensation không phải rollback tức thời hoặc đảm bảo khôi phục mọi thứ |
| Idempotency | Một thao tác logic lặp lại bằng cùng khóa không tạo tác dụng phụ trùng, theo hợp đồng provider | Khóa có phạm vi/thời gian sống; không ngăn trùng khi thay khóa |
| Inbox/deduplication | Consumer xử lý message/event lặp với hiệu ứng logic một lần | Không chứng minh provider bên ngoài đã thực hiện thành công |
| Reconciliation | So sánh **trạng thái mong muốn** với **sự thật đã quan sát có bằng chứng** ở các hệ thống | Có độ trễ, API lookup không đáng tin/không đủ lịch sử |
| Compensation | Tạo tác dụng phụ mới để khắc phục bước trước (release, void, refund) | Có thể mất phí, bị từ chối, không thể đảo ngược hoặc lại rơi vào UNKNOWN |

Ví dụ: payment đã **captured** không thể “rollback” bằng `ROLLBACK` SQL. Refund là một **nghiệp vụ mới** có mã giao dịch, số tiền, trạng thái, thời gian và khả năng thất bại riêng. Nếu hàng đã được giao, gửi email xin lỗi cũng không thể hoàn nguyên hoàn toàn tác động của việc giao.

**Đối soát là cơ chế tìm và sửa bất đồng giữa các hệ thống**; Saga mô tả dòng công việc và quy tắc tiến/lùi. Hai cơ chế bổ sung nhau: Saga kiểm soát con đường thông thường; đối soát tìm trường hợp thông điệp mất, xử lý dở, timeout không rõ kết quả, event đến trễ hoặc thao tác sửa thủ công làm lệch trạng thái.

## 3. Ba dạng kết quả của một tác dụng phụ

Một cuộc gọi từ Orders tới Payment có thể kết thúc bằng:

| Quan sát | Điều có thể kết luận | Điều **không** thể kết luận |
|---|---|---|
| Phản hồi xác nhận thành công, có provider transaction ID | Provider đã ghi nhận một hành động theo hợp đồng | Mọi bước khác của đơn đã thành công |
| Phản hồi lỗi **tường minh, kết thúc cuối cùng** theo hợp đồng | Hành động đó bị từ chối, không có hiệu ứng được cam kết | Các hành động trước hoặc callback khác đều thất bại |
| Timeout, connection reset, process crash, response 5xx không có cam kết kết quả | **UNKNOWN**: chưa biết đã thực hiện hay chưa | “Chưa thu tiền”, “được phép gửi lại bằng khóa khác” hoặc “chắc chắn thất bại” |

Một HTTP `500`, `502`, `503` hay `504` **không tự chứng minh** provider chưa ghi giao dịch: request có thể đã tới provider rồi response bị mất. Ngay cả `200 OK` ở gateway cũng cần đọc **trạng thái nghiệp vụ** của provider; có API trả HTTP 200 kèm `state=PENDING`.

### 3.1. Quy tắc an toàn khi gặp UNKNOWN

1. Giữ nguyên **idempotency key/correlation ID** đã dùng cho thao tác ban đầu.
2. Ghi lại `UNKNOWN`, thời điểm, attempt, provider và thông tin phi nhạy cảm phục vụ tra cứu.
3. Hỏi provider bằng **provider reference** hoặc **idempotency key** đã gắn từ lần đầu, nếu API cho phép.
4. Phân biệt `CONFIRMED`, `FAILED_FINAL`, `NOT_FOUND` và `UNKNOWN`; `NOT_FOUND` có thể chỉ là chưa được index hoặc dữ liệu còn trễ.
5. Chỉ retry thao tác khi provider **cam kết idempotency với cùng key** trong khoảng hiệu lực, hoặc có bằng chứng chắc chắn thao tác chưa xảy ra và được phép thực hiện.
6. Nếu không đủ bằng chứng, giữ `NEEDS_REVIEW`/chặn bước gây tác dụng phụ mới, đồng thời cảnh báo người vận hành.

**Không tạo idempotency key mới chỉ vì lần trước timeout.** Key mới thường mô tả một thao tác mới và có thể khiến provider thu tiền lần nữa.

### 3.2. Ví dụ hai trục trạng thái

Tách **trạng thái công việc** của đơn khỏi **trạng thái quan sát** từng effect:

~~~text
Order workflow:
  ACCEPTED -> RESERVING -> AUTHORIZING -> CAPTURING
           -> SUCCEEDED
           -> COMPENSATING -> COMPENSATED
           -> NEEDS_REVIEW

Inventory effect:
  PLANNED -> SENT -> UNKNOWN -> CONFIRMED | FAILED_FINAL
                                  |
                             release planned

Payment capture effect:
  PLANNED -> SENT -> UNKNOWN -> CONFIRMED | FAILED_FINAL

Refund/void effect (một effect mới):
  PLANNED -> SENT -> UNKNOWN -> CONFIRMED | FAILED_FINAL
~~~

Đây là **một mô hình minh họa**, không bắt buộc phải có tất cả trạng thái. Đừng gộp `UNKNOWN` với `FAILED`, hoặc gộp `COMPENSATED` với `SUCCEEDED`. `COMPENSATED` nói rằng hệ thống đã có các hành động sửa sai được **xác nhận**; nếu refund chưa chắc thành công thì workflow chưa được kết thúc.

## 4. Xác định bất biến nghiệp vụ trước khi viết worker

Một hệ thống “hội tụ” chỉ có ý nghĩa khi biết **thế nào là trạng thái đúng**. Đối với bài toán đặt hàng:

- **Một thao tác tạo đơn logic** (`tenantId + caller + Idempotency-Key` và fingerprint request) không được tạo hai đơn.
- **Một lần capture logic** cho một đơn, một khoản tiền và một mục đích phải có một danh tính giao dịch ổn định. Không capture thêm nếu lần trước chưa biết kết quả.
- `order.status=PAID` chỉ khi có **bằng chứng thanh toán hợp lệ** khớp đơn, tiền tệ, số tiền, bên nhận và provider.
- `order.status=READY_TO_SHIP` chỉ khi các điều kiện stock và payment cần thiết đã được xác nhận.
- Refund hoặc inventory release chỉ được phát cho **tác dụng phụ thực sự tồn tại**, theo policy và lịch sử.
- Một provider transaction chỉ được gắn với đúng một thao tác nghiệp vụ theo ràng buộc độc nhất, tránh ghi cùng giao dịch cho nhiều order.
- Mọi quan sát/callback phải thuộc **đúng tenant, provider, operation và phiên bản chính sách**; event của đơn khác không được làm thay đổi trạng thái.
- Mỗi trạng thái không thể tự động giải quyết phải có owner vận hành, thời điểm kiểm tra tiếp và lịch sử lý do.

Các bất biến phải sống ở **business service và database constraints**. Chỉ chặn ở UI không đủ; scheduled job, webhook và replay event đều có thể đi đường khác.

### 4.1. Chọn thứ tự giảm tác dụng phụ không thể đảo ngược

Ưu tiên **giữ tồn kho trước, authorize trước và capture khi sẵn sàng** nếu hợp đồng thanh toán/kinh doanh cho phép. Authorization có thể được void hoặc tự hết hạn, thường dễ quản lý hơn captured payment cần refund. Tuy nhiên, thời hạn hold, phí, yêu cầu pháp lý và chính sách provider có khác biệt; không suy đoán “void luôn miễn phí” hay “refund luôn thành công”. Với hàng vật lý đã giao, không thể sửa sai chỉ bằng việc đổi cột `status`.

## 5. Dữ liệu phải lưu: ý định, lần thử, bằng chứng và hành động sửa

Nếu chỉ lưu `orders.status` thì khi sự cố không thể biết bước nào đã phát lệnh và provider có khả năng đã xử lý hay chưa. Tối thiểu nên tách:

1. **Operation**: request logic, tenant, caller, fingerprint, idempotency key, trạng thái workflow.
2. **Effect intent**: muốn tạo tác dụng phụ gì (reserve stock, capture payment), số tiền/đơn hàng đích, **key ổn định** và trạng thái dự kiến.
3. **Attempt**: lần gửi lệnh, thời điểm, endpoint/transport, timeout hay response, correlation/request ID.
4. **Evidence/observation**: kết quả lookup, webhook đã xác minh, provider transaction ID, phiên bản/số thứ tự nếu có, nguồn và thời điểm.
5. **Remediation action**: quyết định hoàn tất lại bước còn thiếu, void/refund/release hay chuyển thủ công; actor và kết quả riêng.
6. **Outbox/inbox**: lệnh/event cần chuyển và khóa deduplication.

Một phác thảo bảng PostgreSQL:

~~~sql
CREATE TABLE operations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, actor_id, kind, idempotency_key)
);

CREATE TABLE effect_intents (
    id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES operations(id),
    tenant_id UUID NOT NULL,
    kind TEXT NOT NULL,                 -- STOCK_RESERVE / PAYMENT_CAPTURE / REFUND ...
    logical_step TEXT NOT NULL,         -- ví dụ capture:order-123:v1
    provider TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    desired_state TEXT NOT NULL,
    observed_state TEXT NOT NULL DEFAULT 'PLANNED',
    provider_ref TEXT,
    attempt_count INT NOT NULL DEFAULT 0,
    next_check_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0,
    UNIQUE (operation_id, logical_step),
    UNIQUE (provider, idempotency_key)
);

CREATE TABLE effect_attempts (
    id UUID PRIMARY KEY,
    effect_id UUID NOT NULL REFERENCES effect_intents(id),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    transport_outcome TEXT NOT NULL,    -- SENT / TIMEOUT / RESPONSE / CRASH_RECOVERED
    http_status INT,
    trace_id TEXT
);

CREATE TABLE effect_evidence (
    id UUID PRIMARY KEY,
    effect_id UUID NOT NULL REFERENCES effect_intents(id),
    observed_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,               -- LOOKUP / VERIFIED_WEBHOOK / REPORT
    provider_event_id TEXT,
    provider_ref TEXT,
    result TEXT NOT NULL,               -- CONFIRMED / FAILED_FINAL / NOT_FOUND / UNKNOWN
    evidence_digest TEXT,
    UNIQUE (source, provider_event_id)
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
~~~

**Lưu ý kỹ thuật:** `UNIQUE (source, provider_event_id)` trên PostgreSQL cho phép nhiều hàng có `provider_event_id IS NULL`; điều đó có thể phù hợp với kết quả polling không có event ID. Với webhook cần dedupe chắc chắn, dùng khóa `provider + provider_event_id` đã xác minh hoặc unique partial index theo nguồn có event ID. `UNIQUE(provider,idempotency_key)` yêu cầu key thực sự có tính duy nhất theo không gian của provider; nếu provider scope key theo tài khoản merchant, thêm `merchant_account` vào unique key. Bảng ví dụ là khung tối thiểu; cần bổ sung các CHECK/ENUM, FK tenant và phân quyền DB phù hợp trước production.

Không lưu token xác thực hoặc full payment-card data trong audit. Có thể giữ provider reference và hash của bằng chứng được bảo vệ. Thời gian retention phải dài **ít nhất** theo cửa sổ tranh chấp, thời hạn tra cứu/retry của provider và yêu cầu nghiệp vụ/tuân thủ, thay vì xóa record UNKNOWN sau vài giờ.

### 5.1. Outbox và ranh giới transaction

Trong một `@Transactional` cục bộ, tạo `operation`, `effect_intent` ban đầu và **outbox event** cùng commit. Worker phát lệnh ngoài DB transaction, rồi cập nhật attempt/evidence ở transaction khác. Nếu worker crash ngay sau khi provider thực hiện nhưng **trước khi ghi CONFIRMED**, DB còn `SENT/UNKNOWN` và reconciliation sẽ tra cứu bằng key cũ.

~~~mermaid
sequenceDiagram
    actor U as Client
    participant A as Orders API
    participant D as Orders DB + Outbox
    participant W as Worker
    participant P as Payment Provider
    participant R as Reconciler

    U->>A: POST /orders + Idempotency-Key K
    A->>D: TX: operation + effect intent + outbox
    D-->>A: COMMIT
    A-->>U: 202 Accepted + operation URI
    W->>D: Claim intent (lease)
    W->>P: Capture với provider key K-pay
    P-->>W: Thực hiện thành công nhưng response mất
    Note over W: Timeout/crash; local result UNKNOWN
    R->>D: Quét intent UNKNOWN đã đến hạn
    R->>P: Lookup bằng K-pay / provider ref
    P-->>R: CONFIRMED + transaction ref
    R->>D: TX: evidence + update state + outbox
    U->>A: GET /operations/{id}
    A->>D: Đọc trạng thái đã đối soát
    A-->>U: 200 trạng thái SUCCEEDED
~~~

**Outbox cho phép phát lại ít nhất một lần**, không đem lại “exactly once” trên toàn bộ internet. Worker, message consumer và provider API phải có idempotency/deduplication tương ứng. Nếu provider không hỗ trợ idempotency hoặc lookup tin cậy, đặt tác dụng phụ rủi ro vào `NEEDS_REVIEW` thay vì tự động gửi lại.

## 6. Đối soát: so sánh “mong muốn” với “đã xảy ra”

Một reconciliation run phải xác định:

- **Đối tượng**: effect intents nào chưa đạt trạng thái cuối hoặc đang có bằng chứng mâu thuẫn?
- **Nguồn sự thật**: DB nội bộ, Payment Provider, Inventory Provider hay báo cáo settlement?
- **Độ tin cậy**: lookup có bao phủ đúng merchant/tenant, tiền tệ, amount, khoảng thời gian và có độ trễ hiển thị không?
- **Hành động**: ghi nhận success, thử lại bằng **cùng key**, tạo compensation độc lập, đợi thêm hay mở incident?
- **Điều kiện hoàn tất**: bằng chứng nào là đủ để chuyển trạng thái cuối, theo phiên bản business rules nào?

### 6.1. Bốn kết quả quan sát

| Kết quả lookup | Ý nghĩa | Quyết định mặc định |
|---|---|---|
| `CONFIRMED` | Provider xác nhận effect đã được thực hiện, có reference/evidence khớp | Ghi bằng chứng và chuyển tiếp workflow nếu các invariant khác đạt |
| `FAILED_FINAL` | Provider đảm bảo lệnh bị từ chối cuối cùng, không có effect cần xử lý | Ghi thất bại, chọn retry nghiệp vụ khác hoặc compensation bước trước |
| `NOT_FOUND` | Chưa thấy effect khi truy vấn | **Chưa chắc** chưa xảy ra; xét độ trễ index, cửa sổ tra cứu và cam kết provider |
| `UNKNOWN` | Timeout lookup, dữ liệu mâu thuẫn/không đầy đủ | Backoff rồi tra tiếp; quá ngưỡng chuyển manual review |

Một `NOT_FOUND` chỉ trở thành bằng chứng mạnh cho “chưa xảy ra” nếu **provider cam kết lookup đầy đủ** sau khoảng visibility lag, đúng account/scope, đúng idempotency key và trong thời gian retention. Nếu không, phải coi là chưa chắc chắn.

### 6.2. Ma trận quyết định an toàn

| Trạng thái cục bộ | Bằng chứng bên ngoài | Điều kiện phụ | Hành động |
|---|---|---|---|
| `UNKNOWN` | `CONFIRMED` | Reference/amount/currency/tenant khớp | Ghi `CONFIRMED`, tiếp tục workflow |
| `UNKNOWN` | `CONFIRMED` | Amount hoặc merchant khác | **Dừng tự động**, incident/kiểm tra gian lận |
| `UNKNOWN` | `FAILED_FINAL` | Provider đảm bảo không có effect | Ghi failed; xác định bước bù trừ còn lại |
| `UNKNOWN` | `NOT_FOUND` | Chưa qua visibility window | Chờ rồi tra tiếp |
| `UNKNOWN` | `NOT_FOUND` | Lookup đầy đủ, same-key retry được cam kết và chưa hết retention | Có thể **retry cùng key**, theo budget |
| `UNKNOWN` | `NOT_FOUND` | Key hết hạn hoặc provider không có cam kết idempotency | `NEEDS_REVIEW`, không tạo key mới |
| `UNKNOWN` | `UNKNOWN` | Chưa vượt số lần/thời gian tối đa | Backoff+jitter, đặt `next_check_at` |
| `UNKNOWN` | `UNKNOWN` | Vượt ngưỡng vận hành | `NEEDS_REVIEW`, cảnh báo |
| `COMPENSATING` | Refund `UNKNOWN` | Chưa biết đã hoàn tiền | Tra refund theo **key hoàn tiền**, không gửi refund khác |
| `SUCCEEDED` | Webhook cũ báo `PENDING` | Event đến trễ/out-of-order | Giữ trạng thái đã xác minh; lưu event, không lùi trạng thái mù |

**Không quyết định chỉ dựa vào HTTP code của lời gọi tra cứu.** Ví dụ provider trả 200 chứa `status=PENDING` thì effect vẫn chưa được xác nhận. Khi có sự kiện mâu thuẫn nhau (provider lookup CONFIRMED nhưng webhook FAILED), không dùng nguyên tắc “event đến sau thắng”: cần quy tắc tin cậy/sequence của provider, tra cứu lại và có thể chuyển review.

### 6.3. Thuật toán đối soát có kiểm soát

~~~text
reconcile(intent):
    assert intent chưa final hoặc có discrepancy cần làm rõ
    if intent đã có lease đang hiệu lực:
        bỏ qua hoặc sắp lại
    observation = provider.lookup(intent.providerAccount,
                                  intent.idempotencyKey,
                                  intent.providerReference)

    if observation == CONFIRMED và thuộc đúng amount/currency/order:
        transaction: ghi evidence; cập nhật effect; enqueue bước tiếp
    else if observation == FAILED_FINAL có bảo đảm không tạo effect:
        transaction: ghi evidence; lên kế hoạch compensation khi cần
    else if observation == NOT_FOUND:
        if visibilityWindowPassed AND lookupComplete
           AND sameKeyRetryGuaranteed AND keyStillValid:
            enqueue retry với CÙNG idempotency key
        else:
            đặt nextCheckAt hoặc NEEDS_REVIEW
    else:
        backoff+jitter; vượt budget thì NEEDS_REVIEW

    mọi quyết định và bằng chứng được audit
~~~

Bước lookup có thể cần phân trang/tổng hợp report, vì không phải provider nào hỗ trợ truy vấn trực tiếp bằng idempotency key. Nếu provider không có API lookup, có thể đối chiếu qua webhook/báo cáo settlement/batch export, nhưng độ trễ và tính đầy đủ phải được thể hiện trong SLA. Không suy từ “chưa có webhook” sang “chưa thu tiền”.

### 6.4. Quét những effect nào?

Worker nên quét các intent `SENT` quá hạn acknowledgment, `UNKNOWN` đến `next_check_at`, workflow `PENDING` quá SLA, outbox chưa được publish và trạng thái bất biến bị vi phạm. Bổ sung **full reconciliation định kỳ** giữa sổ nội bộ và báo cáo của provider để tìm những giao dịch không hề xuất hiện trong intent cục bộ, ví dụ do bug cũ hoặc thao tác thủ công. Đây là dạng sai lệch khác với retry hàng đợi.

Khi query dữ liệu lớn, dùng cursor theo `(updated_at, id)` hoặc watermark có overlap, phân trang ổn định và **quét lặp những cửa sổ gần đây** để tránh bỏ sự kiện đến trễ. Watermark `processed_until` không nên được đẩy tới khi các trang cần xử lý đã được ghi checkpoint thành công.

## 7. Chọn giữa hoàn tất công việc và compensation

Khi một số tác dụng phụ đã xảy ra, quyết định sửa sai là **quyết định nghiệp vụ**. Ba hướng:

1. **Forward recovery**: giữ các effect đã xảy ra và làm tiếp bước còn thiếu. Ví dụ payment CAPTURED, reservation CONFIRMED, chỉ thiếu ghi đơn vào hệ thống logistics; có thể tái phát lệnh logistics bằng key ổn định.
2. **Compensation**: phát tác dụng phụ ngược có chủ đích. Ví dụ không thể giữ tồn kho nhưng đã thu tiền: tạo `REFUND_REQUESTED` với một refund idempotency key riêng; nếu refund xác nhận thì đánh dấu `REFUNDED`.
3. **Human review**: bằng chứng thiếu/mâu thuẫn, giao dịch đã settlement, giao hàng không thể hủy, provider hết thời hạn lookup/idempotency, hoặc có nguy cơ gây thiệt hại nếu tự động thực hiện.

| Effect đã xảy ra | Bước thất bại sau đó | Sửa sai có thể dùng | Rủi ro cần xét |
|---|---|---|---|
| Giữ tồn kho | Thanh toán bị từ chối cuối cùng | Release reservation theo reservation ID/key | Reservation có thể đã hết hạn/đã release |
| Payment **authorized** | Không thể hoàn tất order | Void/cancel authorization theo provider contract | Hold có thể tự hết hạn, trạng thái settlement thay đổi |
| Payment **captured** | Không thể giữ hàng | Refund theo key riêng | Refund có thể mất thời gian/phí hoặc bị từ chối |
| Shipping label đã tạo | Order bị hủy | Void label nếu hãng hỗ trợ | Không đồng nghĩa kiện hàng đã được thu hồi |
| Hàng đã giao | Payment bị đảo ngược | Quy trình thu hồi công nợ/hỗ trợ khách | Không thể “undo” giao hàng bằng HTTP |
| Email đã gửi | Order bị hủy | Gửi thông báo đính chính | Không thể xóa email đã đọc |

Compensation là **state machine riêng**, không phải lệnh `DELETE` không có audit. Ví dụ refund có các trạng thái `REQUESTED → SENT → UNKNOWN → CONFIRMED` hoặc `FAILED_FINAL`; chỉ khi đủ điều kiện mới kết thúc workflow ở `COMPENSATED`. Một refund gửi đi nhưng chưa biết kết quả vẫn phải đi qua reconciliation giống payment ban đầu.

### 7.1. Tránh bù trừ hai lần

Đặt constraint `UNIQUE (operation_id, logical_step)` cho effect `refund:paymentRef:v1`. Hai worker phát hiện cùng discrepancy chỉ được tạo **một refund intent logic**, và provider nhận cùng idempotency key. Có thể tạo phiên bản `v2` chỉ sau khi policy/nhân viên phê duyệt một thao tác refund thật sự khác (ví dụ refund một phần bổ sung), với amount còn lại và audit riêng. Không thay key chỉ vì worker retry.

## 8. REST API: trả kết quả theo tiến trình dài

Thực hiện nhiều tác dụng phụ ngoài tiến trình HTTP request thường không thể bảo đảm hoàn tất trước timeout. Thiết kế tài nguyên **operation** để client có thể theo dõi và retry yêu cầu ban đầu an toàn.

### 8.1. Tạo đơn với `Idempotency-Key`

~~~http
POST /api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Content-Type: application/json
Idempotency-Key: order-create-7c8e

{
  "cartId": "cart-872",
  "currency": "VND",
  "totalAmount": 320000
}
~~~

Ở server:

- Xác thực token, audience, scope, membership tenant, quyền tạo đơn; kiểm `cartId`, số tiền và logic chống thao túng giá từ client.
- Chuẩn hóa request và tính fingerprint theo những trường nghiệp vụ được công bố; không dùng trực tiếp `totalAmount` client để quyết định tiền phải thu, mà phải tính trên dữ liệu giá server.
- Kiểm unique `(tenant, caller, kind, idempotencyKey)`. Nếu **cùng key, cùng fingerprint**, trả lại operation đã tồn tại. Nếu **cùng key, payload khác**, trả `409 Conflict` (hoặc mã thống nhất trong hợp đồng).
- Trong một transaction tạo operation, order dự thảo, effect intent và outbox; sau khi commit mới trả acknowledgment.
- Chỉ trả thành công hoàn tất khi có bằng chứng nghiệp vụ; đã nhận request vào xử lý thì trả `202 Accepted`.

Ví dụ response sau commit:

~~~http
HTTP/1.1 202 Accepted
Location: /api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/operations/11111111-1111-4111-8111-111111111111
Content-Type: application/json
Cache-Control: no-store

{
  "operationId": "11111111-1111-4111-8111-111111111111",
  "status": "ACCEPTED",
  "links": {
    "self": "/api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/operations/11111111-1111-4111-8111-111111111111"
  }
}
~~~

**202 chỉ xác nhận server đã chấp nhận công việc**, chưa chứng minh các bước bên ngoài thành công. Nếu hệ thống **không lưu bền vững** command/operation trước khi trả, đừng hứa tiếp tục xử lý bằng 202. Nếu nhận request nhưng service không có năng lực ghi nhận công việc, có thể trả `503` theo policy và cho client retry với **cùng key**.

### 8.2. Theo dõi operation

~~~http
GET /api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/operations/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "operationId": "11111111-1111-4111-8111-111111111111",
  "status": "RECONCILING",
  "lastUpdatedAt": "2026-11-18T10:20:00Z",
  "nextCheckAt": "2026-11-18T10:21:00Z",
  "links": {
    "self": "/api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/operations/11111111-1111-4111-8111-111111111111"
  }
}
~~~

Client chỉ thấy trạng thái nghiệp vụ công khai (`ACCEPTED`, `PROCESSING`, `RECONCILING`, `SUCCEEDED`, `COMPENSATED`, `NEEDS_REVIEW`), không xem token provider hoặc chi tiết giao dịch người khác. Nếu operation đã thành công, `GET` có thể trả `200` với trạng thái và liên kết tới order; khi chưa xong vẫn có thể trả `200` cho tài nguyên operation tồn tại. HTTP `200` của lần polling **không** có nghĩa nghiệp vụ đã `SUCCEEDED`.

### 8.3. Mã lỗi của API và khi nào dùng

| HTTP | Tình huống | Lưu ý |
|---|---|---|
| `202 Accepted` | Command đã ghi bền vững, xử lý bất đồng bộ | `Location` trỏ operation |
| `200 OK` | GET operation hoặc replay cùng key đã có kết quả theo contract | Status nghiệp vụ nằm trong JSON |
| `201 Created` | Đơn đã được tạo và API cam kết resource theo contract | Không diễn giải là đã thanh toán nếu chưa có bằng chứng |
| `400/422` | Payload không hợp lệ/quy tắc nghiệp vụ không thỏa | Không tự động retry nguyên request |
| `409 Conflict` | Cùng idempotency key nhưng fingerprint khác; action xung đột trạng thái | Trả Problem Details ổn định |
| `401/403` | Chưa xác thực/không được phép | Không tiết lộ operation tenant khác |
| `404` | Operation không tồn tại hoặc bị che giấu theo policy | Chống BOLA với tenant/owner |
| `429` | Client vượt quota khi poll/retry | Dùng backoff/`Retry-After` nếu có |
| `503` | API tạm không nhận hoặc phục vụ được | Retry có giới hạn và **cùng Idempotency-Key** |

Không biến timeout của provider thành `201 PAID`; cũng không mặc định trả `500` và khuyên client tạo đơn mới. Một request idempotent có cùng key cần cho client cách truy hồi kết quả kể cả khi response ban đầu bị mất.

**Hủy operation:** `DELETE /operations/{id}` không có nghĩa rollback tất cả tác dụng phụ. Nếu hỗ trợ hủy, định nghĩa một command `POST /operations/{id}/cancellations` hoặc resource/action có contract rõ, kiểm trạng thái hiện tại và cho biết hủy có thể chuyển thành compensation. Trạng thái `CANCEL_REQUESTED` chưa phải `CANCELLED`.

## 9. Java/Spring Boot: nhận command an toàn

Ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x và Spring Data JPA. Những đoạn code sau minh họa **ranh giới transaction, idempotency và quyết định đối soát**; entity/repository/provider adapter được định nghĩa theo dự án. Mã không tự thay thế xác thực access token, tenant isolation hoặc hợp đồng provider thực tế.

### 9.1. Lưu operation + outbox cùng transaction

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record CreateOrderRequest(String cartId, String currency) {}
record AcceptedOperation(UUID id, String status) {}

@Service
class OrderCommandService {
    private final IdentityPolicy identities;
    private final OperationRepository operations;
    private final OrderRepository orders;
    private final EffectRepository effects;
    private final OutboxRepository outbox;
    private final FingerprintService fingerprints;

    OrderCommandService(
        IdentityPolicy identities,
        OperationRepository operations,
        OrderRepository orders,
        EffectRepository effects,
        OutboxRepository outbox,
        FingerprintService fingerprints
    ) {
        this.identities = identities;
        this.operations = operations;
        this.orders = orders;
        this.effects = effects;
        this.outbox = outbox;
        this.fingerprints = fingerprints;
    }

    @Transactional
    AcceptedOperation accept(
        UUID tenantId, String verifiedIssuer, String verifiedSubject,
        String idemKey, CreateOrderRequest request
    ) {
        // Kiểm quyền tạo đơn và membership tenant từ principal đã xác minh.
        UUID actor = identities.requireActiveMemberWithCreatePermission(
            tenantId, verifiedIssuer, verifiedSubject);

        // Fingerprint canonical và tính tiền trên dữ liệu server.
        String requestHash = fingerprints.of(request, tenantId, actor);

        var existing = operations.findByTenantIdAndActorIdAndKindAndIdempotencyKey(
            tenantId, actor, "CREATE_ORDER", idemKey);
        if (existing.isPresent()) {
            Operation op = existing.get();
            if (!op.getRequestHash().equals(requestHash)) {
                throw new IdempotencyConflictException();
            }
            return new AcceptedOperation(op.getId(), op.getStatus());
        }

        Operation op = operations.save(Operation.accepted(
            tenantId, actor, idemKey, requestHash));

        Order order = orders.save(Order.draftFromServerPricing(
            tenantId, actor, request));

        EffectIntent reserve = effects.save(
            EffectIntent.stockReserve(op.getId(), tenantId, order.getId()));

        outbox.save(OutboxEvent.forEffect(reserve));
        return new AcceptedOperation(op.getId(), op.getStatus());
    }
}
~~~

Ví dụ dùng các factory `Operation.accepted`, `Order.draftFromServerPricing`, `EffectIntent.stockReserve` và các repository **tượng trưng cho domain model**. Trong ứng dụng thật phải định nghĩa chúng, kiểm validation, request hash, khóa unique và lỗi constraint.

**Race condition:** Hai request cùng key có thể cùng thấy “chưa tồn tại”. Unique constraint DB là điểm chặn cuối cùng. Nếu `save/flush` ném unique violation trong transaction, **đừng tiếp tục truy vấn trong transaction đã bị rollback-only**. Xử lý ngoại lệ ở ngoài transaction đó, đọc lại operation đã commit trong transaction mới, so fingerprint và trả cùng operation. Có thể dùng câu `INSERT ... ON CONFLICT` theo PostgreSQL với logic đối chiếu fingerprint được kiểm thử. Chỉ `synchronized` trong một JVM không đủ khi chạy nhiều pod.

### 9.2. Controller HTTP với operation URI

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/tenants/{tenantId}")
class OrderCommandController {
    private final OrderCommandService commands;

    OrderCommandController(OrderCommandService commands) {
        this.commands = commands;
    }

    @PostMapping("/orders")
    ResponseEntity<AcceptedOperation> create(
        @PathVariable UUID tenantId,
        @RequestHeader("Idempotency-Key") String idemKey,
        @AuthenticationPrincipal Jwt jwt,
        @RequestBody CreateOrderRequest request
    ) {
        AcceptedOperation op = commands.accept(
            tenantId, jwt.getIssuer().toString(), jwt.getSubject(),
            idemKey, request);

        URI uri = URI.create("/api/tenants/" + tenantId
            + "/operations/" + op.id());
        return ResponseEntity.accepted()
            .location(uri)
            .cacheControl(CacheControl.noStore())
            .body(op);
    }
}
~~~

Ở đây controller luôn trả `202` cho operation đã được ghi nhận, kể cả replay đang chạy; nếu contract muốn trả 200 khi đã kết thúc, service/controller cần phân biệt trạng thái rõ. Header `Idempotency-Key` phải được kiểm độ dài, ký tự và giới hạn kích thước; mã này trình bày luồng cơ bản. Với Spring Security Resource Server, cần xác minh chữ ký JWT, issuer, expiry, audience API và `orders.write`; service vẫn kiểm membership/role của tenant theo request, ownership theo resource. Không lấy actor từ `actorId` trong body.

### 9.3. Worker chọn effect không giữ DB transaction khi gọi mạng

Worker có thể dùng SQL claim batch:

~~~sql
SELECT id
FROM effect_intents
WHERE observed_state IN ('SENT', 'UNKNOWN')
  AND next_check_at IS NOT NULL
  AND next_check_at <= now()
ORDER BY next_check_at, id
FOR UPDATE SKIP LOCKED
LIMIT 50;
~~~

Truy vấn này dành cho **reconciler**: `SENT` là lệnh đã được dispatch nhưng chưa có xác nhận cuối, còn `UNKNOWN` là kết quả mơ hồ; cả hai chỉ được tra lại khi đến `next_check_at`. Intent `PLANNED` được **outbox dispatcher** xử lý ở luồng phát lệnh lần đầu, với same-key idempotency và ghi lại attempt/trạng thái; không gọi `lookup` cho `PLANNED` rồi suy ra lệnh đã được gửi. Với `SENT`, đặt `next_check_at` khi dispatch để phát hiện trường hợp không có acknowledgment.

**Phải thực hiện câu SELECT cùng thao tác claim lease trong một transaction ngắn.** `SKIP LOCKED` tránh hai worker cùng lấy một hàng đang khóa, nhưng chỉ giữ lock đến lúc commit. Nếu commit rồi gọi provider mà không lưu trạng thái claim/lease, worker khác vẫn có thể xử lý cùng intent. Mẫu production cần `lease_owner`, `lease_until`, `attempt_count` và fencing/version, cùng cơ chế thu hồi lease quá hạn.

~~~text
Transaction 1 (ngắn):
  lock/claim những intent đến hạn
  ghi leaseOwner, leaseUntil, version
  commit

Ngoài transaction:
  lookup provider / gửi lệnh với same idempotency key

Transaction 2 (ngắn):
  kiểm lease/version vẫn hợp lệ
  ghi attempt + evidence
  chuyển state hoặc đặt nextCheckAt
  phát outbox khi có bước kế tiếp
  commit
~~~

Không giữ lock DB xuyên suốt API call vài giây hoặc hàng phút. **Lease không bảo đảm đúng một lần gọi** khi worker crash, timeout hoặc lease hết hạn trong lúc provider xử lý. Đúng đắn phải đến từ identity của logical effect, cùng idempotency key, constraint và phép ghi trạng thái có điều kiện.

Một scheduler minh họa (các thành phần cần triển khai theo DB/provider thật):

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class ReconciliationScheduler {
    private final ReconciliationQueue queue;
    private final ProviderObservationClient provider;
    private final EvidenceRecorder recorder;

    ReconciliationScheduler(
        ReconciliationQueue queue,
        ProviderObservationClient provider,
        EvidenceRecorder recorder
    ) {
        this.queue = queue;
        this.provider = provider;
        this.recorder = recorder;
    }

    @Scheduled(fixedDelay = 10_000)
    void reconcileDueIntents() {
        // claimBatch phải commit lease trước khi trả về.
        for (LeasedEffect effect : queue.claimBatch(50)) {
            try {
                ProviderObservation observation =
                    provider.lookup(effect.provider(),
                                    effect.idempotencyKey(),
                                    effect.providerReference());

                // recorder thực hiện transaction với optimistic
                // version/lease check, lưu evidence và next action.
                recorder.record(effect, observation);
            } catch (Exception transientError) {
                // Ghi lỗi quan sát và lịch retry, không đánh dấu FAILED_FINAL.
                recorder.deferWithBackoff(effect, transientError);
            }
        }
    }
}
~~~

Bật scheduling bằng `@EnableScheduling` trong cấu hình ứng dụng. `catch (Exception)` ở đây chỉ nhằm **không làm mất batch đang xử lý**; code thực tế cần phân loại lỗi tạm thời, lỗi cấu hình, security/credential và lỗi không thể retry. Không nuốt hoặc đánh dấu success khi recorder lỗi. Khi lưu evidence thất bại, lease phải hết hạn và reconciler sẽ tra lại, không gửi một effect mới thiếu kiểm soát.

### 9.4. Hàm quyết định thuần để dễ kiểm thử

~~~java
enum ObservationStatus {
    CONFIRMED, FAILED_FINAL, NOT_FOUND, UNKNOWN
}

enum NextAction {
    ACCEPT_CONFIRMATION,
    RECORD_FINAL_FAILURE,
    RETRY_SAME_KEY,
    WAIT_AND_RECHECK,
    MANUAL_REVIEW
}

record Evidence(
    ObservationStatus status,
    boolean businessFieldsMatch,
    boolean lookupCompleteAfterVisibilityWindow
) {}

final class ReconciliationPolicy {
    static NextAction decide(
        Evidence evidence,
        boolean sameKeyRetryGuaranteed,
        boolean idempotencyKeyStillValid,
        boolean retryBudgetAvailable
    ) {
        return switch (evidence.status()) {
            case CONFIRMED -> evidence.businessFieldsMatch()
                ? NextAction.ACCEPT_CONFIRMATION
                : NextAction.MANUAL_REVIEW;
            case FAILED_FINAL -> NextAction.RECORD_FINAL_FAILURE;
            case NOT_FOUND -> {
                if (!idempotencyKeyStillValid) {
                    yield NextAction.MANUAL_REVIEW;
                }
                if (!evidence.lookupCompleteAfterVisibilityWindow()) {
                    yield NextAction.WAIT_AND_RECHECK;
                }
                boolean safeRetry =
                    sameKeyRetryGuaranteed
                    && retryBudgetAvailable;
                yield safeRetry
                    ? NextAction.RETRY_SAME_KEY
                    : NextAction.MANUAL_REVIEW;
            }
            case UNKNOWN -> retryBudgetAvailable
                ? NextAction.WAIT_AND_RECHECK
                : NextAction.MANUAL_REVIEW;
        };
    }
}
~~~

Đây là **policy thuần minh họa**: `WAIT_AND_RECHECK` chỉ được dùng khi chưa vượt SLA; tầng orchestrator phải đổi thành `MANUAL_REVIEW` nếu không thể có bằng chứng đủ tin cậy, hoặc quá thời hạn xử lý. Khi key đã hết hạn mà lookup trả NOT_FOUND, policy minh họa chuyển thẳng `MANUAL_REVIEW`; nó không thử lại bằng khóa mới. `FAILED_FINAL` cần bằng chứng thật từ provider, không được suy từ timeout. Việc state chuyển sang `SUCCEEDED` hoặc `COMPENSATED` là quyết định của workflow dựa trên **tất cả effect**, không phải chỉ một `Evidence`.

## 10. Webhook, outbox và sự kiện đến trễ

Payment Provider có thể gửi webhook `payment.succeeded` ngay khi worker vẫn nghĩ HTTP call timeout. Reconciler và webhook consumer sẽ cùng cập nhật một effect.

Quy tắc thiết kế:

- **Xác minh webhook**: chữ ký, secret/key rotation, timestamp/replay window và mapping đúng merchant/tenant; không tin callback không có xác thực.
- **Dedupe**: ghi provider event ID vào inbox với unique constraint trong DB transaction; event trùng được ACK an toàn, không chạy lại nghiệp vụ.
- **Không suy thứ tự từ thời gian nhận**: event `PENDING` đến sau `CAPTURED` không được hạ trạng thái chỉ vì nhận muộn. Dựa theo sequence/version từ provider nếu có, hoặc query trạng thái authoritative.
- **Ghi evidence trước quyết định**: lưu loại event, transaction ref, amount/currency, thời điểm và hash/bằng chứng; không lưu thông tin thanh toán nhạy cảm.
- **Idempotent transition**: cập nhật DB với `WHERE version=?` hoặc khóa ngắn, chỉ chuyển từ state hợp lệ; chỉ phát outbox cho effect tiếp theo một lần.
- **Conflict handling**: nếu webhook nói `FAILED` nhưng lookup sau đó xác nhận `CAPTURED`, giữ evidence hai bên và mở review theo độ tin cậy/semantics của provider.

Outbox publisher có thể phát hai bản `PaymentCaptured`; consumer kho vận phải có inbox/dedupe hoặc khóa business operation để không giao hàng hai lần. Cũng không được tuyên bố “kafka exactly-once” là đủ để ngăn hai lần gọi REST sang Payment Provider: chính các external calls vẫn cần stable idempotency key và reconciliation.

## 11. Backoff, ngân sách retry và tránh retry storm

Việc quét trạng thái UNKNOWN quá thường xuyên dễ làm provider bị rate limit và khiến recovery chậm hơn. Dùng `next_check_at`, exponential backoff có jitter, giới hạn số lần và tổng thời gian:

~~~text
base = 5 giây
cap = 15 phút
upper = min(cap, base * 2^attempt)
delay = random(0, upper)
nextCheckAt = now + max(providerRetryAfter, delay)
~~~

- Nếu provider trả `429` hoặc `503` kèm `Retry-After` hợp lệ, **không gửi lại sớm hơn** thời điểm được khuyến nghị; có thể thêm jitter sau mốc đó.
- Nếu provider lookup chậm hoặc hết hạn, dùng timeout/deadline của từng attempt và tổng SLA. Không giữ hàng chờ vô hạn.
- Khi hết budget, đưa vào `NEEDS_REVIEW`/dead-letter queue có owner xử lý; **không bỏ mất effect intent**.
- Nếu provider không hỗ trợ same-key retry trong cửa sổ đủ dài, sau expiry của key cần dừng automation; dùng báo cáo/tra cứu hỗ trợ hoặc manual reconciliation.
- Giới hạn concurrency theo provider, merchant và tenant; ngăn một batch nhiều nghìn effect UNKNOWN làm gián đoạn đường tạo đơn mới.
- Dùng circuit breaker cho lookup provider đang hỏng; nhưng breaker mở không chứng minh effect thất bại.

Với dòng tiền, “retry cho tới khi hết lỗi” không phải chính sách đủ an toàn. Cần biết **lệnh retry có idempotent không**, liệu key được lưu qua restart, và kết quả từ lần gọi trước còn đang có thể xuất hiện hay không.

## 12. Đối soát định kỳ với báo cáo bên ngoài

Không phải bất đồng nào cũng có một intent `UNKNOWN` rõ ràng. Có thể có một khoản thanh toán thành công **mà Orders DB không có dòng liên quan** do bug, thao tác thủ công hoặc migration. Do đó cần **đối soát hai chiều**:

- **Từ nội bộ ra ngoài:** mọi effect intent `CONFIRMED` phải có provider transaction hợp lệ; mọi `UNKNOWN` phải có chính sách xử lý; không có order SUCCEEDED thiếu bằng chứng.
- **Từ ngoài vào trong:** mọi giao dịch provider thuộc merchant/tenant/phạm vi ngày cần được gắn với đúng operation/order hoặc đưa vào danh sách **unmatched external transactions** để điều tra.

Ví dụ đối soát settlement cuối ngày:

| Provider transaction | Orders DB | Phát hiện | Hành động |
|---|---|---|---|
| PAY-101 captured 320.000 VND | Order 101 paid, amount khớp | Đồng nhất | Lưu checkpoint đối soát |
| PAY-102 captured 450.000 VND | Order 102 đang UNKNOWN | Chưa cập nhật bằng chứng | Gắn evidence, cập nhật workflow nếu đủ điều kiện |
| PAY-103 captured 500.000 VND | Không tìm thấy order | Giao dịch mồ côi | Quarantine/manual review, không refund tự động |
| PAY-104 absent | Order 104 ghi PAID | DB tuyên bố success thiếu bằng chứng | Dừng fulfillment, điều tra provider/lookup lag |
| PAY-105 refunded | Order 105 ghi REFUND_UNKNOWN | Sửa sai đã xảy ra | Ghi refund CONFIRMED và xét workflow compensated |

Đối soát phải kiểm **amount, currency, merchant account, payment method/provider reference, trạng thái settlement, tenant và order**. Chỉ match theo `orderId` trong metadata có thể bị trùng/giả; nếu transaction ID có uniqueness, dùng nó làm căn cứ mạnh hơn. Việc đối chiếu với báo cáo tài chính còn có timezone, ngày settlement, phí, partial capture, partial refund, chargeback và rounding; không được so sánh tổng tiền tùy tiện rồi kết luận hết lệch.

Với dữ liệu lớn: phân vùng ngày/merchant, lưu watermark/checkpoint an toàn, chạy overlap cho giao dịch đến trễ, ghi tổng số record đọc/xử lý, đánh dấu batch `COMPLETED` chỉ sau khi checkpoint được lưu. Mọi bản ghi unmatched cần có tuổi, mức độ rủi ro, người phụ trách và kế hoạch xử lý.

## 13. Bảo mật, phân quyền và khả năng truy vết

Đối soát có quyền truy cập nhiều hệ thống và đôi khi phát lệnh **refund/release**; đây là đường API/job cần kiểm soát chặt.

- **Tenant isolation:** operation, effect, evidence, report và log tra cứu phải liên kết cùng tenant. Khi worker chạy không có HTTP principal, nó cần service identity, tenant context đã xác minh và quyền trên provider account tương ứng.
- **Least privilege:** tài khoản đọc trạng thái provider khác tài khoản có quyền refund/capture nếu hạ tầng cho phép; manual override cần quyền theo vai trò và có thể yêu cầu hai người phê duyệt.
- **Bằng chứng có xác thực:** xác minh chữ ký webhook; chỉ nhận provider reference từ adapter đã tin cậy; không cho caller sửa trạng thái `PAID` qua `PATCH /orders`.
- **Audit append-only:** ghi actor/service, lý do, operation ID, effect ID, quyết định, evidence source, thời gian và result; các thay đổi thủ công phải lưu trước/sau, người phê duyệt.
- **Ẩn thông tin nhạy cảm:** không lưu nguyên access token, API key, số thẻ, CVV hoặc payload provider chứa PII trong trace/log; dùng masked reference và quyền truy cập log.
- **Ngăn chạy song song:** unique key, lease, optimistic locking và idempotency khiến hai worker không tạo refund/capture logic trùng.
- **Khả năng hủy/đổi policy:** quyết định manual override cần kiểm tra state mới nhất và version để không thực hiện thao tác trên bản ghi vừa được reconciler cập nhật.

### 13.1. HTTP status và bảo mật endpoint theo dõi

`GET /operations/{id}` phải kiểm caller thuộc đúng tenant và có quyền xem operation. Không dùng UUID khó đoán làm bằng chứng quyền. Có thể trả 404 che giấu operation tenant khác. Request đọc trạng thái không nên trả toàn bộ payment-provider reference hoặc chi tiết tranh chấp nếu caller chỉ có quyền xem đơn cơ bản.

Đối với API quản trị `POST /operations/{id}/reconcile` hoặc `POST /remediations`, cần quyền tách biệt, idempotency key và policy chặn thao tác lặp; không để user thường buộc server gửi lại charge/refund liên tục. Có thể cho phép người dùng gửi “yêu cầu kiểm tra” nhưng worker vẫn quyết định theo policy và ngân sách, không biến endpoint đó thành cổng gọi provider không giới hạn.

## 14. Quan sát và SLO của reconciliation

Một workflow có thể vẫn trả 202 và không có lỗi HTTP nhưng **không bao giờ hoàn tất**. Chỉ số phải phản ánh chất lượng hội tụ, không chỉ tỷ lệ 2xx.

| Metric/telemetry | Ý nghĩa |
|---|---|
| `operations_inflight` theo workflow/status | Số đơn đang chờ hoặc đối soát |
| `effect_unknown_total` và tuổi effect UNKNOWN | Mức độ mơ hồ chưa được giải quyết |
| `reconciliation_backlog`, `oldest_due_age` | Worker có đang tụt hậu không |
| `reconciliation_attempts_total` theo result/source | Lookup thành công/thất bại, vòng retry |
| `reconciliation_resolution_latency` p50/p95/p99 | Thời gian từ UNKNOWN đến trạng thái đã xác minh |
| `unmatched_provider_transactions` | Giao dịch bên ngoài chưa liên kết nội bộ |
| `compensation_requested/confirmed/failed` | Độ tin cậy của luồng sửa sai |
| `idempotency_conflict_total` | Client dùng lại key với payload khác hoặc thiết kế key sai |
| `inbox_duplicate_total` / `outbox_lag` | Sự kiện trùng/lưu thông điệp chậm |
| `manual_review_age` | Vụ việc còn mở vượt SLA |
| `provider_429/503/timeout` | Dấu hiệu provider bận, cần điều chỉnh backoff |

Tránh dùng `orderId`/`userId` làm label Prometheus có cardinality cao; dùng route template, provider, status, tenant tier và error class. Trace/log có phân quyền mới chứa ID liên kết cần điều tra. SLO có thể là “99,9% operation không rủi ro đạt trạng thái terminal trong 10 phút” cùng SLO riêng cho UNKNOWN/NEEDS_REVIEW; xác định riêng khoảng cách settlement dài hơn vì nghiệp vụ tiền không nhất thiết hoàn tất tức thời.

**Cảnh báo quan trọng:** UNKNOWN quá lâu với captured payment; refund UNKNOWN quá SLA; unmatched external payment; double capture/refund attempts; stale outbox; lease tồn đọng; chênh tiền không khớp và số operations chuyển manual review tăng đột biến. Không đánh giá worker “thành công” chỉ vì job scheduler chạy xong không ném exception.

## 15. Kiểm thử: chèn lỗi vào từng ranh giới

Không thể chứng minh khả năng phục hồi chỉ bằng unit test happy path. Tạo **fake provider có thể ghi hiệu ứng nhưng cố tình làm mất response**, hoặc dùng sandbox provider cùng contract idempotency. Với PostgreSQL dùng Testcontainers khi muốn kiểm unique constraint, transaction, outbox và lease/lock đúng semantics; mock không tái hiện đủ race.

### 15.1. Ma trận lỗi và bất biến

| Kịch bản | Quan sát đầu tiên | Kỳ vọng sau reconciliation |
|---|---|---|
| Orders DB rollback **trước** khi ghi outbox | Không có operation bền vững | Không gọi provider; client retry cùng key có thể tạo operation hợp lệ |
| Outbox commit, publisher crash trước khi gửi | Operation + outbox chờ | Publisher lần sau tiếp tục, không mất lệnh |
| Provider xử lý thành công, response bị mất | Effect UNKNOWN | Lookup CONFIRMED; không tạo capture thứ hai |
| Provider từ chối cuối cùng, stock đã giữ | Failed final + reservation confirmed | Release reservation có key riêng và được xác minh |
| Payment capture thành công, stock giữ thất bại | Captured + stock failed | Theo policy refund hoặc forward recovery, có audit |
| Refund thành công, response mất | Refund UNKNOWN | Lookup refund CONFIRMED; không refund lần hai |
| Cùng webhook gửi 3 lần | Trùng event ID | Inbox dedupe, chuyển trạng thái một lần |
| Webhook PENDING đến sau CAPTURED | Event đến lệch thứ tự | Không lùi trạng thái confirmed nếu không có bằng chứng hợp lệ |
| Provider lookup trả NOT_FOUND trong cửa sổ indexing | Chưa thấy giao dịch | Đợi, không retry bằng key mới |
| Provider key hết hiệu lực và kết quả không chắc | UNKNOWN sau retention | NEEDS_REVIEW, chặn tự động tạo effect trùng |
| Hai worker cùng claim khi lease hết hạn | Nguy cơ gọi trùng | Same-key provider idempotency, lease/fencing, một logical effect |
| Client retry POST cùng key và cùng body | Replay | Cùng operation ID, không tạo thêm order |
| Client retry cùng key nhưng khác body | Conflict | 409, không thay operation đầu |
| Tenant B đoán operation của Tenant A | Cross-tenant request | 403/404 theo policy, không lộ evidence |
| Provider timeout/429/503 nhiều lần | Lookup UNKNOWN | Backoff/jitter; không gây retry storm |
| Worker phát lệnh xong nhưng DB lưu evidence lỗi | State vẫn UNKNOWN | Lần sau lookup lại và hội tụ, không tự tạo key mới |

**Điều kiện kiểm thử mạnh:** đếm **tác dụng phụ thực ở provider fake**, không chỉ số lần HTTP call. Hai request HTTP giống nhau có thể được provider idempotently dedupe; điều cần bảo đảm là **một capture logic** và state cuối đúng.

### 15.2. Unit test cho quyết định đối soát

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ReconciliationPolicyTest {
    @Test
    void confirmedEvidenceCompletesEffect() {
        Evidence ev = new Evidence(
            ObservationStatus.CONFIRMED, true, false);
        assertEquals(
            NextAction.ACCEPT_CONFIRMATION,
            ReconciliationPolicy.decide(ev, false, false, false));
    }

    @Test
    void mismatchRequiresReview() {
        Evidence ev = new Evidence(
            ObservationStatus.CONFIRMED, false, true);
        assertEquals(
            NextAction.MANUAL_REVIEW,
            ReconciliationPolicy.decide(ev, true, true, true));
    }

    @Test
    void notFoundBeforeVisibilityWindowMustNotRetry() {
        Evidence ev = new Evidence(
            ObservationStatus.NOT_FOUND, false, false);
        assertEquals(
            NextAction.WAIT_AND_RECHECK,
            ReconciliationPolicy.decide(ev, true, true, true));
    }

    @Test
    void notFoundWithCompleteLookupAndValidSameKeyCanRetry() {
        Evidence ev = new Evidence(
            ObservationStatus.NOT_FOUND, false, true);
        assertEquals(
            NextAction.RETRY_SAME_KEY,
            ReconciliationPolicy.decide(ev, true, true, true));
    }

    @Test
    void expiredKeyMustNotTriggerAutomaticRetry() {
        Evidence ev = new Evidence(
            ObservationStatus.NOT_FOUND, false, true);
        assertEquals(
            NextAction.MANUAL_REVIEW,
            ReconciliationPolicy.decide(ev, true, false, true));
    }
}
~~~

Bộ test kiểm **policy thuần**; cần test orchestration nâng `WAIT_AND_RECHECK` thành `MANUAL_REVIEW` khi vượt SLA, kiểm transition được ghi trong DB và không tạo duplicate refund.

### 15.3. MockMvc và HTTP contract

Ví dụ giả định `@SpringBootTest`, `@AutoConfigureMockMvc`, test DB seed và Spring Security `jwt()`:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderOperationHttpTest {
    @Autowired MockMvc mvc;

    @Test
    void acceptedRequestReturnsOperationUri() throws Exception {
        UUID tenantId = UUID.fromString(
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");

        mvc.perform(post("/api/tenants/{t}/orders", tenantId)
                .header("Idempotency-Key", "test-create-123")
                .contentType("application/json")
                .content("{\"cartId\":\"cart-872\",\"currency\":\"VND\"}")
                .with(jwt()
                    .jwt(j -> j.issuer("https://login.example.test")
                               .subject("test-sub"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders.write"))))
            .andExpect(status().isAccepted())
            .andExpect(header().exists("Location"));
    }
}
~~~

Test thực tế phải có membership/giá server/cart fixture và repository, nên ví dụ trên là **khung test**, không chạy độc lập nếu chưa dựng domain. `jwt()` chỉ tạo principal giả cho security test; cần test tích hợp decoder thật để xác minh chữ ký, issuer, audience và expiry. Bổ sung kiểm thử GET operation của tenant khác trả 403/404; retry cùng idempotency key trả cùng ID; key + payload khác trả 409.

### 15.4. Fault injection có thứ tự

Một chuỗi fault injection hiệu quả là:

1. Crash trước khi commit operation/outbox.
2. Crash sau khi commit outbox nhưng trước khi gửi lệnh.
3. Cho provider **ghi tác dụng phụ**, rồi cắt kết nối trước khi server nhận response.
4. Crash sau khi provider phản hồi thành công nhưng **trước khi local DB cập nhật evidence**.
5. Phát lại webhook và outbox event, đảo thứ tự các event.
6. Mô phỏng `NOT_FOUND` sớm rồi `CONFIRMED` sau visibility window.
7. Hết TTL idempotency key, tạo discrepancy và kiểm manual review.
8. Kích hoạt worker kép, lease hết hạn, membership bị thu hồi và một refund đang UNKNOWN.
9. Chạy full reconciliation với settlement report có giao dịch mồ côi.
10. Xác minh không có capture/refund trùng, mọi operation có trạng thái giải thích được và alert được mở khi cần.

Không cần tạo tải thật vào provider sản xuất. Có thể triển khai fake adapter có `effectCount`, `lookupByKey`, điều khiển độ trễ/cut response và chạy integration test bằng Spring/Testcontainers ở staging.

## 16. Bài tập thực hành

### Bài tập 1 — Dựng state machine cho thanh toán UNKNOWN

Đơn `O-101` đã giữ tồn kho `R-55`. Orders Service gọi capture với key `CAP-O101-1`; provider thu 320.000 VND nhưng response mất. DB còn `PAYMENT_UNKNOWN`.

Hãy đề xuất các trạng thái, bảng evidence tối thiểu, truy vấn lookup và quyết định khi provider lần lượt trả: (a) CONFIRMED khớp số tiền; (b) NOT_FOUND nhưng index có trễ 2 phút; (c) CONFIRMED sai merchant; (d) không có API lookup và key đã hết hạn. Chỉ ra lúc nào được phát lệnh capture mới.

**Gợi ý:** (a) ghi evidence và tiếp tục; (b) chờ; (c) manual review; (d) manual review. Không tự tạo capture mới trong trạng thái UNKNOWN.

### Bài tập 2 — Hoàn thành thiếu hay hoàn tiền?

Đơn `O-102` đã capture thành công nhưng Inventory Service báo `FAILED_FINAL`. Hãy so sánh **forward recovery** (lấy hàng từ kho khác) với **compensation** (refund), đề xuất điều kiện business quyết định, trạng thái refund, cách xác minh và audit. Xem xét trường hợp refund bị timeout sau khi provider đã hoàn tiền.

**Tiêu chí đạt:** Refund là effect riêng có key ổn định; chỉ `COMPENSATED` khi có bằng chứng hoàn tiền; không coi `refund sent` là `refunded`.

### Bài tập 3 — Xử lý hai request cùng Idempotency-Key

Hai pod nhận đồng thời `POST /orders` với tenant/user/key giống nhau. Cả hai đọc DB chưa thấy operation rồi cùng INSERT.

Hãy đề xuất unique constraint, điểm catch exception phù hợp với transaction boundary, cách đọc operation sau race và so request hash. Viết test gửi 20 request đồng thời có cùng key, kiểm chỉ có **một order** và **một effect intent logic**.

**Tiêu chí đạt:** Không dựa vào lock trong một JVM; trả cùng operation ID khi body giống nhau và 409 khi khác.

### Bài tập 4 — Đối soát theo báo cáo cuối ngày

Provider trả danh sách `PAY-201`, `PAY-202`, `PAY-203`; DB có `PAY-201` khớp, `PAY-202` ở UNKNOWN, còn `PAY-203` không có operation. Thiết kế batch reconciliation hai chiều, watermark/checkpoint, cửa sổ overlap, bảng discrepancy và kế hoạch cho unmatched transaction.

**Tiêu chí đạt:** Không chỉ quét intent UNKNOWN; có quy trình phát hiện giao dịch bên ngoài không có record cục bộ và không tự refund một khoản chưa xác định chủ sở hữu.

### Bài tập 5 — Viết fault-injection test

Thiết kế fake Payment Provider hỗ trợ idempotency key và lookup. Cho provider ghi `CAPTURED`, nhưng client adapter ném timeout. Worker retry với same key và reconciliation xác nhận.

**Tiêu chí đạt:** `provider.captureCountForLogicalKey == 1`, order chỉ chuyển `PAID` khi bằng chứng khớp, status endpoint ban đầu không tự báo thành công; kiểm webhook đến hai lần và outbox publish trùng.

### Bài tập 6 — Quy trình manual review an toàn

Một refund ở `UNKNOWN` quá 24 giờ; provider không hỗ trợ lookup và key đã mất hiệu lực. Hãy thiết kế ticket review, thông tin bằng chứng được phép nhìn thấy, quyền phê duyệt, thao tác đặt lại trạng thái và cách tránh worker tự động chạy song song với quyết định của nhân viên.

**Tiêu chí đạt:** Không refund lại mù; ticket có owner/SLA, version check, audit append-only, có khả năng đối chiếu báo cáo settlement và thông báo khách hàng theo chính sách.

## 17. Tự kiểm tra và tài liệu đối chiếu

1. **Timeout từ Payment có nghĩa chưa thu tiền?** Không; trạng thái đúng là UNKNOWN cho tới khi có bằng chứng.
2. **DB rollback có hoàn tác capture ở provider không?** Không; tác dụng phụ bên ngoài nằm ngoài local transaction.
3. **Có outbox là được “exactly once” toàn hệ thống?** Không; publisher có thể phát trùng, consumer/provider cần idempotency và đối soát.
4. **Vì sao NOT_FOUND chưa đủ để retry?** Lookup có thể trễ, sai phạm vi hoặc hết cửa sổ tra cứu.
5. **Một refund có thể coi là rollback không?** Không; đó là effect mới cần state, key và bằng chứng riêng.
6. **Khi nào 202 hợp lý?** Khi command đã được chấp nhận/ghi bền vững để xử lý và chưa cam kết outcome cuối cùng.
7. **Tại sao GET operation phải kiểm tenant/owner?** Operation chứa trạng thái và dấu vết tác dụng phụ liên quan dữ liệu người dùng.
8. **Khi nào chuyển NEEDS_REVIEW?** Khi không còn cách xác minh/retry an toàn, có bằng chứng mâu thuẫn hoặc vượt SLA.
9. **Làm sao tránh double capture sau crash?** Stable logical key, provider idempotency, lookup theo key/reference, unique intent và reconciliation.
10. **Đối soát hàng ngày khác worker UNKNOWN thế nào?** Nó phát hiện cả giao dịch không có bản ghi cục bộ, chênh số tiền và kết quả settlement đến trễ.

Tài liệu nên đối chiếu khi triển khai:

- **RFC 9110 — HTTP Semantics:** response 202, 409, 503 và cách diễn giải trạng thái HTTP — https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9457 — Problem Details for HTTP APIs:** lỗi có cấu trúc — https://www.rfc-editor.org/rfc/rfc9457
- **RFC 9111 — HTTP Caching:** quy tắc cache response operation/dữ liệu cá nhân — https://www.rfc-editor.org/rfc/rfc9111
- **Spring Framework — Transaction Management:** transaction cục bộ, ranh giới commit và exception — https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- **Spring Security — OAuth2 Resource Server:** xác minh access token trước khi truy cập operation — https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **PostgreSQL — Explicit Locking:** `FOR UPDATE SKIP LOCKED`, khóa và cạnh tranh — https://www.postgresql.org/docs/current/explicit-locking.html
- **Microservices.io — Transactional Outbox Pattern:** cách kết hợp thay đổi DB và message intent — https://microservices.io/patterns/data/transactional-outbox
- **Microservices.io — Saga Pattern:** điều phối bước và compensation — https://microservices.io/patterns/data/saga.html
- **Provider-specific idempotency/webhook/lookup documentation:** bắt buộc xác minh phạm vi key, TTL, độ trễ quan sát và semantics của refund/capture theo nhà cung cấp cụ thể.

**Điểm cốt lõi:** Sau tác dụng phụ từng phần, trạng thái **chưa biết** phải được giữ như một trạng thái có ý nghĩa. Hệ thống cần lưu **ý định → lần thử → bằng chứng → quyết định sửa sai**, đối chiếu với nguồn sự thật có độ tin cậy đã xác định, và chỉ tạo tác dụng phụ tiếp theo khi các bất biến nghiệp vụ được chứng minh. Sửa sai an toàn là một quá trình có trạng thái, idempotency, giới hạn retry, kiểm toán và lối thoát cho xử lý thủ công.
