# Đối soát chất lượng dữ liệu và trách nhiệm sửa sai

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm:** Quản trị dữ liệu  
> **Trọng tâm:** Thiết kế quy tắc đo chất lượng dữ liệu, phát hiện và đối soát sai lệch giữa các nguồn, phân công trách nhiệm sửa sai rõ ràng và kiểm chứng kết quả mà không phá tính toàn vẹn nghiệp vụ.  
> **Phạm vi:** Cơ sở dữ liệu giao dịch, event-driven microservices, data pipeline, kho dữ liệu, báo cáo và các hệ thống bên ngoài.

## 1. Vì sao chất lượng dữ liệu là một vấn đề kiến trúc?

Trong hệ thống microservices, cùng một thực thể nghiệp vụ có thể xuất hiện ở nhiều dạng khác nhau:

- **Order Service** lưu đơn hàng, trạng thái thanh toán, tổng giá trị và outbox events.
- **Payment Service** lưu trạng thái giao dịch, idempotency key và mã tham chiếu từ nhà cung cấp thanh toán.
- **Inventory Service** lưu số lượng tồn, lượng đã giữ chỗ và lịch sử chuyển trạng thái reservation.
- **Fulfillment Service** lưu vận đơn, kết quả bàn giao và hoàn hàng.
- **Search/Reporting** tạo materialized views, indexes, bảng tổng hợp hoặc dữ liệu phân tích.
- **Data warehouse** nhận dữ liệu qua CDC, Kafka, batch ETL và nhiều hệ thống nguồn khác.

Những bản sao hoặc phép chiếu này **không phải lúc nào cũng đồng bộ tức thì**. Một sự kiện có thể đến muộn, đến lặp, thất lạc tạm thời, bị xử lý sai version, hoặc dữ liệu bị sửa thủ công mà không phát event tương ứng.

Ví dụ:

~~~text
Order DB:    ORDER-1001, status=PAID, amount=590000 VND
Payment DB:  ORDER-1001, payment=SUCCEEDED, amount=590000 VND
Warehouse:   ORDER-1001, payment_status=PENDING
Dashboard:   Doanh thu chưa tính đơn ORDER-1001
~~~

Có ít nhất ba khả năng:

1. Event chưa tới warehouse, hệ thống vẫn ở trong **độ trễ đồng bộ hợp lệ**.
2. Event đã tới nhưng bị lỗi xử lý, warehouse thực sự thiếu dữ liệu.
3. Hai service diễn giải trạng thái **PAID** và **SUCCEEDED** khác nhau nên phép ánh xạ trong reporting sai.

Không thể sửa bằng cách chọn đại một bảng rồi copy giá trị sang bảng khác. Phải biết **nguồn nào có thẩm quyền**, **độ trễ nào được chấp nhận**, **điều kiện nào chứng minh sai lệch**, và **ai có quyền quyết định phương án khắc phục**.

> **Nguyên tắc:** Đối soát là quá trình tạo bằng chứng về sự phù hợp hoặc chênh lệch giữa các biểu diễn dữ liệu; sửa sai là một quyết định có ràng buộc về ownership, tính nhất quán, bảo mật và hậu quả nghiệp vụ.

## 2. Các thuật ngữ nền tảng

| Thuật ngữ | Định nghĩa thực dụng |
|---|---|
| **Data quality (DQ)** | Mức dữ liệu đáp ứng nhu cầu sử dụng đã xác định, thông qua các dimension và quy tắc đo được |
| **Data contract** | Thỏa thuận về schema, semantics, chất lượng, thời gian cung cấp, ownership và thay đổi dữ liệu giữa producer/consumer |
| **Reconciliation (đối soát)** | So sánh hai hoặc nhiều tập dữ liệu theo khóa, thời điểm và quy tắc nghiệp vụ để phát hiện sự khác biệt |
| **Source of truth / System of record** | Nguồn có thẩm quyền cho một sự thật nghiệp vụ trong phạm vi cụ thể |
| **Data lineage** | Quan hệ xuất xứ và biến đổi: dữ liệu đến từ đâu, đi qua bước nào và được tiêu thụ ở đâu |
| **Data owner** | Người/nhóm chịu trách nhiệm về ý nghĩa, quy tắc và quyết định nghiệp vụ của tập dữ liệu |
| **Data steward** | Vai trò vận hành/quản trị định nghĩa quy tắc, theo dõi chất lượng và phối hợp khắc phục |
| **Technical owner** | Nhóm chịu trách nhiệm triển khai, vận hành pipeline, schema, API, database hoặc công cụ liên quan |
| **Data incident** | Tình huống dữ liệu sai/thiếu/trễ/không tin cậy gây rủi ro hoặc vi phạm ngưỡng đã xác định |
| **Remediation** | Hành động khôi phục chất lượng: sửa nguồn, phát lại event, backfill, tái tính toán, đối soát bù hoặc hủy sai lệch |
| **Exception / discrepancy** | Bản ghi sai lệch có định danh, bằng chứng, phạm vi ảnh hưởng và trạng thái xử lý |

**Data quality không đồng nghĩa chỉ kiểm tra schema hợp lệ.** Một field amount có kiểu integer và không null vẫn có thể sai đơn vị, bị tính trùng hoặc gắn sai currency.

## 3. Sáu nhóm chất lượng dữ liệu thường gặp

### 3.1. Completeness — Đầy đủ

Dữ liệu cần thiết có tồn tại không? Ví dụ đơn hàng đã thanh toán phải có payment reference hoặc một trạng thái giải thích vì sao chưa có.

~~~text
Completeness ratio
  = số bản ghi đạt quy tắc đầy đủ / số bản ghi thuộc phạm vi kiểm tra
~~~

Phải định nghĩa **mẫu số** rõ: chỉ các đơn đã hoàn thành, không bao gồm draft hoặc pending chưa cần reference.

### 3.2. Accuracy — Đúng so với nguồn/căn cứ

Giá trị có phản ánh sự thật đúng không? Amount 590.000 VND trong Order có khớp Payment provider sau phí và hoàn tiền theo quy tắc không?

Accuracy thường cần **nguồn kiểm chứng ngoài bản ghi được xem xét**. Hai bảng cùng sao chép từ một nguồn lỗi sẽ khớp nhau nhưng chưa chắc đúng.

### 3.3. Consistency — Nhất quán

Những hệ thống hoặc những field liên quan có tuân thủ cùng invariant không? Ví dụ:

~~~text
Order.status=PAID
  ⇒ tồn tại Payment với final outcome=SUCCEEDED
     hoặc có trạng thái đối soát/ngoại lệ được công nhận
~~~

Invariant cần nêu rõ trạng thái trung gian, refunds, chargebacks và time window; không dùng một rule cứng mù quáng cho tất cả trường hợp.

### 3.4. Timeliness / Freshness — Kịp thời

Dữ liệu đến nơi tiêu thụ có đủ nhanh không? Ví dụ báo cáo tác nghiệp cần cập nhật trong 5 phút, báo cáo tài chính khóa sổ có thể dùng chu kỳ khác.

Một bản ghi trễ 3 phút có thể chấp nhận nếu SLO lag là 5 phút; không nên tạo incident “mismatch” ngay tại giây đầu tiên.

### 3.5. Validity — Hợp lệ theo contract

Giá trị có đúng kiểu, domain, định dạng, range và rule không? Ví dụ currency thuộc danh sách ISO currency được hỗ trợ, amount ở minor unit theo contract, timestamp là UTC có timezone.

### 3.6. Uniqueness — Không trùng lặp ngoài ý định

Một payment attempt có **provider_transaction_id** duy nhất theo provider và merchant account phù hợp; eventId dùng để deduplicate delivery. Nhưng một order có nhiều payment attempts hợp lệ thì không được yêu cầu order_id duy nhất trong bảng attempts.

**Các dimension phải gắn với mục đích sử dụng**: không tạo dashboard “DQ=98%” chung chung khi người đọc không biết phần còn lại bị lỗi gì và ảnh hưởng người nào.

## 4. Ba lớp kiểm tra: Trước ghi, trên đường truyền và sau đồng bộ

Một kiến trúc bảo vệ dữ liệu cần nhiều lớp:

~~~text
Client / upstream
        |
        v
[Validation at write boundary]
  Schema, business rules, auth, uniqueness
        |
        v
Source of record (database)
        |
        v
[Outbox / CDC / event contract]
  Completeness, schema, delivery, idempotency
        |
        v
Consumer / projection / warehouse
        |
        v
[Reconciliation + quality monitoring]
  Freshness, counts, keyed comparisons, invariants
        |
        v
Incident / repair / verification
~~~

- **Prevention:** từ chối dữ liệu không hợp lệ ngay khi ghi và dùng database constraints.
- **Detection:** giám sát delivery, lag, schema drift, row count và business invariants.
- **Correction:** xử lý chênh lệch bằng workflow có kiểm soát và lưu bằng chứng.

Đối soát sau cùng **không thay thế validation khi ghi**. Nếu API cho phép lưu amount âm không hợp lệ, rồi mỗi ngày dùng SQL sửa, hệ thống vừa tăng chi phí vừa tạo hậu quả nghiệp vụ không cần thiết.

## 5. Xác định nguồn có thẩm quyền theo từng sự thật

Một anti-pattern là tuyên bố “database Order là source of truth cho mọi field trong order”. Thực tế:

| Dữ kiện | Nguồn có thẩm quyền có thể là | Bản sao/phép chiếu |
|---|---|---|
| Order items, price tại thời điểm mua | Order domain | Reporting, search |
| Kết quả authorization/capture | Payment ledger + external provider theo hợp đồng | Order payment status, reporting |
| Tồn kho khả dụng hiện tại | Inventory domain | Product listing cache |
| Trạng thái giao vận | Fulfillment/carrier integration | Order tracking UI |
| Email khách hàng | Customer identity/profile domain | Order contact snapshot |
| Số doanh thu đã được chốt | Ledger/accounting theo policy | BI dashboard |
| Feature configuration | Configuration management | Local config cache |

**Thẩm quyền có thể phụ thuộc thời điểm và loại thông tin.** Order có thể lưu giá sản phẩm tại thời điểm mua làm bằng chứng giao dịch, dù Product Catalog hiện tại đã đổi giá. Không đồng bộ “giá mới nhất” vào order lịch sử nếu business invariant yêu cầu giữ giá đã chốt.

Với payment, một provider trả **AUTHORIZED** chưa đồng nghĩa **CAPTURED**, và hoàn tiền làm thay đổi số tiền ròng. Quy tắc đối soát phải dùng các khái niệm trạng thái đúng hợp đồng.

### 5.1. Bảng ownership tối thiểu

Mỗi critical dataset nên có:

~~~text
Dataset ID: order.transactions
Business owner: Order Domain Owner
Technical owner: Order Platform Team
Producer endpoint/event: Order API / OrderConfirmed v2
Consumers: Payment reconciliation, BI, customer portal
Source of truth: Order PostgreSQL + payment references
Critical fields: order_id, amount_minor, currency, status, updated_at
Freshness objective: <= 5 minutes for operational projection
Quality rules: uniqueness, valid status transition, referential integrity
Discrepancy owner: Order Data Steward / incident commander
Approved repair path: domain command or controlled backfill
Evidence retention: per approved policy
~~~

Các giá trị trên là **mẫu minh họa**; owner và SLO phải được xác nhận bởi tổ chức thực tế.

## 6. Data contracts: Chặn lệch nghĩa trước khi nó trở thành lỗi dữ liệu

Một contract không chỉ nêu các field và kiểu:

~~~yaml
dataset: payment-outcomes
version: 2
owner: payment-domain
primaryKey: [provider, provider_transaction_id]
fields:
  order_id:
    type: string
    required: true
  amount_minor:
    type: integer
    required: true
    semantic: integer amount in minor currency units
  currency:
    type: string
    required: true
  outcome:
    type: string
    enum: [AUTHORIZED, CAPTURED, FAILED, REFUNDED]
  occurred_at:
    type: string
    format: date-time
quality:
  uniqueKey: [provider, provider_transaction_id, outcome]
  freshnessSloMinutes: 5
  reconciliationOwner: payment-domain
~~~

Đây là **tài liệu contract minh họa**, không phải cú pháp bắt buộc của công cụ registry cụ thể. Trong thực tế cần phân biệt payment transaction và lịch sử event transitions; key duy nhất của event có thể là **event_id**, còn một provider transaction có thể có nhiều biến động trạng thái hợp lệ.

Contract phải chỉ rõ:

- **Meaning:** amount_minor là đơn vị nhỏ nhất, không phải số tiền đã định dạng.
- **Timezone:** occurred_at theo UTC hay hệ khác; xử lý clock skew thế nào.
- **Null semantics:** null là “không có”, “chưa biết” hay “không áp dụng”.
- **Allowed state transitions:** CAPTURED có thể sang REFUNDED nhưng không tùy ý quay về CREATED.
- **Delivery semantics:** at-least-once, duplicate handling, ordering expectations.
- **Change policy:** schema và semantic breaking changes được thông báo, version và migrate ra sao.
- **Owner:** ai phê duyệt thay đổi nghĩa và giải quyết các ngoại lệ.

Đổi field **amount_minor** thành **amount** vẫn là một rủi ro nếu cách diễn giải đơn vị thay đổi; schema parser pass không chứng minh contract ngữ nghĩa còn đúng.

## 7. Reconciliation cần so đúng phạm vi và đúng mốc thời gian

Đối soát thiếu temporal context dễ tạo false positives.

Ví dụ:

~~~text
10:00:00  Payment accepted
10:00:02  Payment committed
10:00:04  Payment event published
10:00:20  Order projection updated
10:01:00  BI dashboard refreshed
~~~

Tại 10:00:03, Order chưa hiển thị Payment success **có thể là bình thường** vì event chưa tới, không nhất thiết là dữ liệu sai.

Thiết kế cần có:

- **Allowed propagation lag** cho từng projection.
- **Watermark:** mốc sự kiện mà pipeline đã xử lý đầy đủ theo semantics rõ.
- **Processing time vs event time:** thời điểm xảy ra nghiệp vụ khác thời điểm message được xử lý.
- **Late-arrival window:** khoảng thời gian chấp nhận event đến muộn.
- **Clock skew:** đồng hồ ở nhiều hệ thống không tuyệt đối giống nhau.
- **Business cut-off:** mốc đóng sổ/đối soát theo múi giờ và phiên bản quy tắc.
- **Correction window:** khi nào sai lệch đã đủ già để mở ticket/sửa.

Không đối chiếu các bảng theo **NOW()** ở các replica khác nhau và kỳ vọng chúng có trạng thái tức thì giống nhau. Cần chọn **as-of point** hoặc **eligible closed time window** phù hợp từng pipeline.

## 8. Hai kiểu đối soát: Tổng hợp và theo từng giao dịch

### 8.1. Control totals / aggregate reconciliation

So sánh count, sum amount, số giao dịch thành công, số bản ghi theo currency/date/provider:

~~~text
Payment provider settlement batch:
  count=10.000
  sum=5.400.000.000 VND

Internal ledger expected settlement:
  count=9.998
  sum=5.399.400.000 VND

Difference:
  count=2
  amount=600.000 VND
~~~

Control totals rẻ và giúp nhận diện **phạm vi**. Nhưng tổng tiền bằng nhau không chứng minh từng giao dịch khớp: một giao dịch thừa +100.000 và một giao dịch thiếu -100.000 có thể bù nhau.

### 8.2. Record-level/keyed reconciliation

Dùng stable business key như **provider_transaction_id + merchant_account + currency + event type** theo thiết kế để tìm:

- Missing in source A.
- Missing in source B.
- Present both but amount/status differs.
- Duplicate unique key ngoài ý định.
- Same ID but khác tenant/provider.
- Records trong cửa sổ chưa đủ chín để kết luận.

**Kết hợp cả hai:** aggregate nhanh để phát hiện bất thường, keyed compare giúp xác định bản ghi bị ảnh hưởng và hướng sửa.

### 8.3. Sampling không thay thế exact reconciliation

Sampling có thể dùng để tìm vấn đề sớm trên dữ liệu lớn hoặc kiểm thử bảo mật/latency, nhưng một lỗi hiếm trên payment ledger vẫn có thể gây tổn thất. Với luồng tài chính/high-integrity, cần chọn **full compare** hoặc proof dựa trên partition/hash/control totals theo nghĩa vụ và khả năng đo. Đừng tuyên bố “không có sai lệch” chỉ từ một mẫu ngẫu nhiên nhỏ.

## 9. Khóa đối soát phải ổn định và có ý nghĩa nghiệp vụ

Các khóa phổ biến:

- Order: **order_id** trong namespace/tenant phù hợp.
- Payment: **provider, merchant_account, provider_transaction_id**.
- Payment attempt: **payment_attempt_id** hoặc idempotency key có scope.
- Outbox event: **event_id**.
- Inventory reservation: **reservation_id + product/warehouse** nếu domain yêu cầu.
- Invoice: **invoice_number + legal_entity + tax jurisdiction** theo nghiệp vụ.
- Warehouse event: **source_system + source_id + version**.

Không ghép bằng customer name hoặc timestamp gần nhau trừ khi đó chỉ là bước **candidate matching** có confidence score và review, không phải xác nhận chắc chắn.

Một khóa **order_id** có thể trùng giữa tenants nếu không được đảm bảo global uniqueness; vì vậy join cần scope đúng, ví dụ **tenant_id, order_id**.

**Dữ liệu thiếu khóa ổn định là vấn đề kiến trúc nguồn**, không nên chỉ “sửa” bằng fuzzy matching trong data warehouse mà không ghi nhận rủi ro.

## 10. Kiểu sai lệch và cách phân loại

| Mã minh họa | Ý nghĩa | Hướng xử lý ban đầu |
|---|---|---|
| **MISSING_IN_TARGET** | Nguồn có record, projection/consumer chưa có | Kiểm tra lag, CDC, DLQ và backfill |
| **ORPHAN_IN_TARGET** | Target có record không có nguồn phù hợp | Kiểm tra tombstone, restore, import sai |
| **VALUE_MISMATCH** | Khác amount/currency/field nghiệp vụ | Xác định source of truth và transformation |
| **STATUS_MISMATCH** | Trạng thái business không khớp | Kiểm tra workflow, in-flight windows, state machine |
| **DUPLICATE_KEY** | Một định danh đáng lẽ unique bị lặp | Kiểm tra retry/idempotency/constraints |
| **LATE_DATA** | Dữ liệu đến sau SLO | Kiểm tra queue, batch, watermark |
| **INVALID_REFERENCE** | Quan hệ tham chiếu không tồn tại | Kiểm tra join, xóa, transaction/outbox |
| **SCHEMA_DRIFT** | Producer đổi schema/type/semantic | Đối chiếu contract/version và deployment |
| **RECONCILIATION_GAP** | Không thể so vì thiếu dữ liệu/credential | Đánh dấu UNKNOWN, không báo PASS |
| **AUTHORIZATION_ERROR** | Dữ liệu bị lộ hoặc ghi bởi sai quyền | Phối hợp Security/Privacy và incident response |

Trạng thái **UNMATCHED** chưa chắc là **ERROR**. Cần tách **pending due to expected lag** khỏi **confirmed discrepancy**. Một giao dịch đang processing có thể chỉ cần được đối chiếu lại sau 2 phút.

## 11. Ví dụ SQL: Đối chiếu bảng nguồn và projection

Giả sử có hai bảng **source_orders** và **reporting_orders** trong một môi trường kiểm thử hoặc đối soát được cấp quyền. Dữ liệu có khóa **tenant_id, order_id**, và hai bên đều ở mốc đã đóng.

~~~sql
SELECT
    COALESCE(s.tenant_id, r.tenant_id) AS tenant_id,
    COALESCE(s.order_id, r.order_id) AS order_id,
    s.status AS source_status,
    r.status AS reporting_status,
    s.amount_minor AS source_amount,
    r.amount_minor AS reporting_amount,
    CASE
        WHEN s.order_id IS NULL THEN 'MISSING_IN_SOURCE'
        WHEN r.order_id IS NULL THEN 'MISSING_IN_TARGET'
        WHEN s.status IS DISTINCT FROM r.status
             OR s.amount_minor IS DISTINCT FROM r.amount_minor
          THEN 'VALUE_MISMATCH'
        ELSE 'MATCH'
    END AS reconciliation_result
FROM source_orders s
FULL OUTER JOIN reporting_orders r
  ON s.tenant_id = r.tenant_id
 AND s.order_id = r.order_id
WHERE s.order_id IS NULL
   OR r.order_id IS NULL
   OR s.status IS DISTINCT FROM r.status
   OR s.amount_minor IS DISTINCT FROM r.amount_minor;
~~~

**Giả định quan trọng:** Cả hai bảng có unique key theo tenant/order và cùng semantic amount. Nếu một bên có duplicates, FULL OUTER JOIN có thể nhân số dòng và làm sai kết quả. Kiểm tra uniqueness trước. Query dùng cú pháp **IS DISTINCT FROM** được PostgreSQL hỗ trợ; với DBMS khác cần cú pháp tương đương.

**Không chạy kiểu compare này trực tiếp trên hai database production lớn** bằng cách copy toàn bộ dữ liệu không giới hạn. Cần partition theo thời gian, streaming/CDC snapshot, read replicas hoặc kho đối soát chuyên biệt có kiểm soát tài nguyên và quyền.

### 11.1. Kiểm tra duplicates trước khi join

~~~sql
SELECT tenant_id, order_id, COUNT(*) AS cnt
FROM reporting_orders
GROUP BY tenant_id, order_id
HAVING COUNT(*) > 1;
~~~

Số dòng duplicate giúp kiểm tra một giả định của mô hình, nhưng nguyên nhân có thể là bảng reporting là **event history** thay vì current-state projection. Không tự xóa “bản ghi trùng” nếu domain cho phép nhiều versions.

### 11.2. Kiểm tra sai lệch theo thời gian

~~~sql
SELECT DATE(event_time) AS event_day,
       COUNT(*) AS records,
       SUM(amount_minor) AS sum_amount_minor
FROM payment_settlements
WHERE event_time >= TIMESTAMP '2026-11-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-02 00:00:00'
GROUP BY DATE(event_time);
~~~

Thời gian ở ví dụ phải được diễn giải trong timezone quy định và đồng nhất giữa nguồn; với PostgreSQL timestamptz cần cẩn thận session timezone. So **sum minor units** trong từng currency, không cộng VND và USD như một số tiền cùng đơn vị.

## 12. Phân biệt trạng thái hiện tại với event history

Một bảng trạng thái hiện tại có thể chỉ giữ một dòng mỗi order:

~~~text
orders:
ORDER-1001 | PAID | updated_at=10:05
~~~

Trong khi event history có:

~~~text
ORDER-1001 | OrderCreated     | 10:00
ORDER-1001 | PaymentRequested | 10:01
ORDER-1001 | PaymentSucceeded | 10:04
ORDER-1001 | OrderPaid        | 10:05
~~~

So row count giữa hai bảng này là **sai mô hình**. Reconciliation phải biết **tập dữ liệu đại diện cho một state snapshot hay một log of transitions**.

Đối với current-state projection, có thể rebuild bằng fold events theo version/order. Đối với audit/ledger, các entries lịch sử thường phải append-only, **không overwrite** để “trông giống” trạng thái hiện tại.

**Source of truth** cũng có thể là state machine và ledger events, không nhất thiết là một cột latest_status đơn giản.

## 13. Event-driven consistency: CDC, outbox, inbox và dedup

Một luồng phổ biến:

~~~text
Order transaction
    |
    +--> update orders
    +--> insert outbox_event (cùng transaction)
    |
    v
Outbox relay / CDC
    |
    v
Kafka topic
    |
    v
Consumer (idempotent)
    |
    +--> inbox/dedup record
    +--> update materialized view
    |
    v
Reporting projection
~~~

Rủi ro và bằng chứng cần đo:

- Outbox record đã commit nhưng chưa publish.
- Relay publish thành công nhưng chưa mark, nên publish lặp.
- Consumer nhận hai lần, nhưng dedup logic thiếu.
- Event schema version mới không được parse.
- Consumer commit offset trước khi update projection bền vững.
- DLQ chứa sự kiện sai khiến reporting trễ.
- Event đến không đúng thứ tự hoặc aggregate version bị nhảy.

**At-least-once delivery thường có thể tạo duplicate.** Không suy ra hai event deliveries nghĩa là hai giao dịch nghiệp vụ thật. Đối soát dựa trên **event ID và processing outcome**, kết hợp state/ledger.

### 13.1. Idempotent consumer

Một handler phù hợp có thể:

1. Bắt đầu transaction dữ liệu ở consumer.
2. Thử ghi **processed_event_id** với unique constraint.
3. Nếu đã xử lý, kết thúc an toàn.
4. Nếu mới, cập nhật projection và commit cùng transaction.
5. Chỉ ack broker sau khi commit phù hợp contract.

Nếu projection database và dedup store không cùng transaction, cần cơ chế chống partial failure tương ứng. **Không chỉ ghi một biến in-memory “seen IDs”** rồi hy vọng restart/scale không tạo duplicate.

## 14. Watermark và cửa sổ đối soát trong hệ thống eventual consistency

Để giảm báo động giả, có thể xây quy tắc:

~~~text
Source event happened at T0
Allowed propagation lag: 5 minutes
Reconciliation eligibility: T0 + 5 minutes + safety margin
After eligibility:
  - if target still absent → open discrepancy
  - if target present but changed value → compare semantics/version
~~~

Nhưng T0 có thể là clock của producer không đáng tin; nên kết hợp **event time, committed position/LSN, broker timestamp và processing watermark**. Với stream processing, **watermark** là ước lượng tiến độ event-time theo semantics của engine, không phải lời bảo đảm đã nhìn thấy mọi event trễ.

Nếu đối soát hai pipelines khác nhau, chỉ so dữ liệu nằm trong khoảng **cả hai đã xử lý đến một mốc đủ tin cậy**. Nếu một pipeline mới tới 10:00 còn pipeline kia tới 10:15, so đến 10:15 sẽ tạo sai lệch giả.

Cần có trường **data_as_of**, **processing_watermark** và **last_successful_sync** trong reports để người sử dụng hiểu dữ liệu mới đến đâu.

## 15. Đối soát payment: Không xử lý tiền bằng phép copy trạng thái

Luồng đơn giản:

~~~text
Order O1001 created, amount=590000 VND
        |
        v
Payment attempt P901 initiated (idempotency key K)
        |
        v
Payment provider authorized/captured
        |
        v
Payment ledger records final outcome
        |
        v
Order projection becomes PAID
        |
        v
BI revenue recognition per accounting policy
~~~

Một sai lệch:

~~~text
Order:    status=PAYMENT_PENDING
Payment:  status=CAPTURED, amount=590000
Provider: transaction=CAPTURED
~~~

Hướng xử lý:

1. Xác định Payment transaction/reference và idempotency key.
2. Kiểm tra provider bằng API đối soát theo quyền và rate limit cho phép.
3. Kiểm tra Payment ledger, webhook delivery, inbox/outbox và consumer offset.
4. Xác nhận Order có thể transition **PENDING → PAID** theo state machine, không có refund/chargeback/duplicate bất thường.
5. Thực thi **domain reconciliation command** hoặc phát lại event an toàn với dedup, không cập nhật một cột reporting để che lỗi.
6. Kiểm tra Order view, ledger, outbox, reporting và audit sau thao tác.
7. Nếu giao dịch đã hoàn tiền, quy tắc “CAPTURED ⇒ PAID” có thể không còn đúng; cần xem timeline và terminal state.

**Không bao giờ tạo thêm payment charge chỉ để hai bảng cùng có số giao dịch.** Với outcome không xác định, phải **lookup/reconcile trước retry**. Sai lệch ở payment có thể ảnh hưởng tiền thật và nghĩa vụ kế toán; cần phê duyệt nghiệp vụ đúng vai trò.

## 16. Đối soát inventory và reservation

Các đại lượng thường gặp:

~~~text
on_hand         = số lượng tồn vật lý/đã ghi nhận
reserved        = số lượng đã giữ chỗ hợp lệ
available       = on_hand - reserved - các khoản điều chỉnh theo policy
~~~

Ví dụ:

~~~text
Inventory DB:
  on_hand=100, reserved=30, available=70

Order projection:
  35 units marked RESERVED

Discrepancy candidate: 5 units
~~~

Không vội tăng **reserved** lên 35 vì:

- Có thể năm đơn đã bị hủy và Order chưa nhận event release.
- Có thể một warehouse khác ghi nhận stock riêng.
- Có thể sự kiện reservation đến trễ.
- Có thể customer cart reservation hết TTL nhưng Order projection chưa cập nhật.
- Có thể hai nguồn dùng **different time cutoffs**.

Đối soát đúng phải lọc theo **reservation_id, SKU, warehouse, status, TTL, quantity unit, event version** và trạng thái cuối sau allowed lag. Với inventory adjustment có thể ảnh hưởng khả năng bán, nên theo business policy và có audit, không chạy một SQL UPDATE âm thầm.

## 17. Data warehouse và reporting: Rebuild thay vì vá thủ công

Data warehouse có thể là **derived data** từ transaction DB/events. Khi một partition ETL lỗi, phương án tốt thường là **replay/backfill deterministically** hơn là sửa trực tiếp 500 dòng theo tay.

Ví dụ:

~~~text
Payment DB (source of truth)
       |
       v
CDC / export with stable checkpoint
       |
       v
Staging raw events
       |
       v
Transform + deduplicate + business mapping
       |
       v
Fact table daily_payment
       |
       v
Dashboard
~~~

Khi phát hiện dashboard thiếu giao dịch:

1. Chọn **partition/window** có sai lệch bằng control totals.
2. Kiểm tra CDC checkpoints, raw ingest và transform errors.
3. Xác định nguyên nhân gốc: missing events, mapping, timezone hay schema drift.
4. Chuẩn bị job backfill chỉ cho phạm vi đã được xác nhận, **idempotent**.
5. Dùng staging/shadow table hoặc atomic partition swap nếu kỹ thuật hỗ trợ.
6. So lại counts, sums, unique keys, business invariants trước/sau.
7. Ghi **data-as-of**, job ID và lineage để dashboard consumers biết bản nào đã được sửa.

**Không sửa dữ liệu dẫn xuất bằng update thủ công mà không sửa pipeline**: lần chạy lại kế tiếp có thể tái tạo lỗi, hoặc báo cáo trở nên không thể truy vết.

## 18. Đối soát master/reference data

Một khách hàng có thể có hồ sơ tại CRM, Auth Service và Billing. Các trường **email, legal_name, billing_address, tax_id** có ownership và thời điểm hiệu lực khác nhau.

Các tình huống:

- Cùng một khách hàng có hai customer IDs vì onboarding duplicate.
- Địa chỉ thanh toán hiện tại không giống snapshot trên hóa đơn đã phát hành.
- Một thay đổi tên hợp pháp chỉ có hiệu lực từ ngày cụ thể.
- CRM đổi email nhưng Auth chưa đồng bộ vì yêu cầu xác minh email.

Cần **entity resolution** có confidence levels và human review đối với merge có rủi ro, không tự suy luận hai khách hàng giống nhau chỉ dựa vào email/tên. Khi hợp nhất IDs, cần mapping, event history, quyền truy cập và khả năng undo theo chính sách.

**Không update lại chứng từ lịch sử** nếu phải giữ giá trị tại thời điểm phát hành; mỗi field có **temporal semantics** khác nhau.

## 19. Thiết kế quy tắc DQ bằng hợp đồng kiểm chứng được

Một rule nên có những thuộc tính:

~~~yaml
ruleId: PAYMENT_CAPTURED_HAS_PROVIDER_REF
dataset: payment.transactions
owner: payment-domain
dimension: completeness
description: Captured payment must have provider reference
scope:
  statuses: [CAPTURED]
  environments: [production]
  exclude:
    - legitimate-migration-window
severity: critical
evaluation:
  cadence: every_5_minutes
  consistencyWindowMinutes: 10
  expectedViolations: 0
actions:
  onFailure: open_reconciliation_case
  automaticMutation: false
~~~

Ví dụ cấu hình mang tính khái niệm, **không phải schema chuẩn của một công cụ cụ thể**. Cần có:

- **Rule version** và effective date.
- **Dataset owner** và người bảo trì technical rule.
- **Query/check implementation** có test.
- **Population và denominator** đúng.
- **Lag tolerance** trước khi kết luận.
- **Threshold** và business impact mapping.
- **Severity** cùng action khi lỗi.
- **Evidence** và retention an toàn.
- **Exception process** có owner/expiry.
- **Rollback/remediation policy**.

Một rule vô chủ tạo cảnh báo mà không ai xử lý. Một rule định nghĩa sai biến các trường hợp hợp lệ thành incident, khiến team tắt alert.

## 20. Đo DQ: Tỷ lệ lỗi, độ trễ, độ phủ và tác động

Một dashboard có thể trình bày:

| Chỉ số | Ý nghĩa |
|---|---|
| **DQ pass rate per rule** | Tỷ lệ dòng/phân vùng đạt một kiểm tra cụ thể |
| **Open discrepancy count** | Số sai lệch chưa xử lý, theo severity và owner |
| **Age of oldest discrepancy** | Thời gian sai lệch tồn tại lâu nhất |
| **Freshness lag** | Thời gian từ nguồn tới nơi tiêu thụ |
| **Missing event/record count** | Số sự kiện/bản ghi thiếu ngoài allowed window |
| **Duplicate rate** | Tỷ lệ records vi phạm unique key theo contract |
| **Reconciliation coverage** | Tỷ lệ datasets/partitions đã được kiểm tra |
| **MTTD** | Mean time to detect data incidents |
| **MTTR** | Mean time to recover/resolve, với định nghĩa rõ |
| **Repair recurrence** | Số sai lệch xuất hiện lại sau khắc phục |
| **Business impact** | Số khách hàng/đơn/tổng tiền bị ảnh hưởng theo policy |

Không gộp mọi rule thành một **điểm chất lượng duy nhất** mà che khuất một lỗi payment nghiêm trọng sau hàng nghìn records catalog đúng. Cần phân nhóm theo **criticality**, dataset, contract và mục đích tiêu thụ.

### 20.1. Ví dụ SLO dữ liệu

~~~text
Operational Order Projection:
  99.9% eligible orders reflected within 5 minutes
  100% confirmed paid orders have traceable payment reference
  No duplicate settlement key in financial ledger

Daily Finance Report:
  publish by 08:00 local time after cut-off and reconciliation
  all report partitions have reconciliation evidence
  any unresolved material discrepancy requires approved exception
~~~

Các mục tiêu ở trên chỉ là ví dụ; định nghĩa **eligible**, **confirmed**, **material discrepancy** và cut-off bắt buộc phải ghi rõ trong contract. Nếu không, con số 99,9% dễ bị báo cáo theo nhiều cách khác nhau.

## 21. RACI: Ai chịu trách nhiệm khi phát hiện dữ liệu sai?

Trong nhiều sự cố, hệ thống phát hiện được sai lệch nhưng các team tranh luận “data team sửa hay service team sửa?”. Cần quy định vai trò trước.

Một cách phân công minh họa:

| Hoạt động | Data Owner | Technical Owner | Data Steward | SRE/Platform | Security/Compliance |
|---|---|---|---|---|---|
| Định nghĩa business invariant | A | C | R | I | C khi nhạy cảm |
| Viết/duy trì DQ check | C | R | A/C | C | I |
| Vận hành pipeline/alert | I | R | A/C | R/C | I |
| Xác định source of truth | A | C | R | I | C khi cần |
| Phê duyệt sửa dữ liệu nghiệp vụ trọng yếu | A | R/C | C | I | C theo policy |
| Thực hiện backfill kỹ thuật | I | R | A/C | C | I |
| Khôi phục hạ tầng/storage | I | C | I | A/R | C |
| Phê duyệt exception về dữ liệu nhạy cảm | C | C | R | I | A theo policy |

**R = Responsible (thực hiện), A = Accountable (chịu trách nhiệm quyết định), C = Consulted, I = Informed**. Bảng chỉ mô tả một mô hình và có thể có hơn một vai trò cùng chịu trách nhiệm ở cấp tổ chức; với một quyết định cụ thể nên chỉ định **một đầu mối accountable rõ ràng**.

Phân biệt:

- **Business/Data Owner:** quyết định ý nghĩa đúng, chấp nhận data loss hoặc cần bút toán điều chỉnh nào.
- **Technical Owner:** sửa code, pipeline, schema/connector và triển khai remediation an toàn.
- **Data Steward:** điều phối trường hợp, quản lý rule/evidence và kiểm tra closure.
- **SRE/Platform:** xử lý năng lực, hạ tầng, broker, storage, khả năng quan sát.
- **Security/Privacy/Compliance:** quyết định khi sai lệch liên quan lộ dữ liệu, quyền truy cập, nghĩa vụ lưu trữ hoặc kiểm toán.

**Không để developer hoặc data engineer tự ý chỉnh ledger/nguồn thẩm quyền chỉ vì có quyền database.** Quyền thực thi và quyền phê duyệt nghiệp vụ là hai thứ khác nhau.

## 22. Phân định trách nhiệm: Producer, transport và consumer

Một record thiếu ở data warehouse có thể do bất cứ mắt xích nào:

~~~text
Producer → Outbox → CDC/Relay → Broker → Consumer → Warehouse
     A          B         C          D        E         F
~~~

Cách điều tra theo chứng cứ:

1. **Producer:** nguồn có ghi giao dịch đúng theo domain invariant không?
2. **Outbox:** event record được commit cùng giao dịch chưa?
3. **Relay:** event có được xuất và có offset/metadata tương ứng không?
4. **Broker:** partition/topic có lưu event và consumer được phép đọc không?
5. **Consumer:** đã nhận, parse, dedup và commit transaction target chưa?
6. **Warehouse:** mapping, partitioning, merge và materialized view có đúng không?

Trách nhiệm sửa thường dựa vào **nơi phát sinh lỗi nguyên nhân gốc**:

- Producer ghi sai business value → producer/domain owner xử lý.
- Relay mất publish → integration/platform owner khôi phục delivery.
- Consumer bỏ field sai version → consumer owner sửa mapping/backfill.
- Warehouse transformation sai timezone → analytics/transform owner sửa và tính lại.
- Contract mơ hồ → data owner + producer/consumer đồng quyết định và cập nhật contract.

**Nhóm phát hiện không mặc nhiên là nhóm phải sửa**. Một data platform team có thể cung cấp alert nhưng không có thẩm quyền biến đổi payment ledger.

## 23. Workflow xử lý một discrepancy từ phát hiện đến đóng

~~~text
Detection
   |
   v
Classify (rule, dataset, severity, scope, age)
   |
   v
Check freshness/lag window
   |           |
   | pending   | confirmed
   v           v
Recheck later  Open case with evidence
                   |
                   v
             Identify owners
                   |
                   v
             Investigate lineage
                   |
                   v
             Propose remediation
                   |
                   v
             Approval / risk review
                   |
                   v
             Execute safe repair
                   |
                   v
             Independent verification
                   |
                   v
             Close + root cause action
~~~

Mỗi case nên có:

- **Case ID** và detection rule/version.
- Dataset, tenant/currency scope, affected time window, record keys.
- First seen time, last checked time, watermark/as-of time.
- Expected value, observed value, **nguồn chứng minh**, không chỉ dự đoán.
- Severity, business impact, số records/amount tại rủi ro.
- Owner tiếp nhận, technical owner, approver.
- Root cause hypothesis và bằng chứng từng tầng.
- Remediation plan, blast radius, rollback/compensation.
- Execution ID, kết quả kiểm tra và thời điểm đóng.

Đây là **workflow xử lý dữ liệu**, không phải các trường QA của công việc tạo README.

## 24. Trạng thái discrepancy nên minh bạch

Một lifecycle thực dụng:

~~~text
DETECTED
   |
   +--> PENDING_PROPAGATION
   |       |
   |       +--> RESOLVED_BY_NORMAL_SYNC
   |       +--> CONFIRMED
   |
   +--> CONFIRMED
           |
           +--> INVESTIGATING
           |
           +--> AWAITING_APPROVAL
           |
           +--> REPAIR_IN_PROGRESS
           |
           +--> VERIFYING
           |
           +--> RESOLVED
           |
           +--> ACCEPTED_RISK / DEFERRED (có owner, expiry, lý do)
~~~

Nếu kiểm tra không thể chạy do mất credential, không được chuyển case thành **RESOLVED**. Nên dùng trạng thái **UNKNOWN/BLOCKED_VERIFICATION** và phát cảnh báo về việc mất khả năng quan sát.

Không cho một record cùng lúc có hai case sửa xung đột nếu cần serialization, lock hoặc workflow coordination.

## 25. Chọn cách sửa sai theo nguồn và mức độ rủi ro

| Loại sai lệch | Cách khắc phục phù hợp | Tránh |
|---|---|---|
| Consumer miss event | Replay từ checkpoint/offset, idempotent handler | Sửa projection không lưu nguyên nhân |
| Materialized view stale | Recompute/backfill partition | Update từng dòng không lặp lại được |
| Producer validation bug | Sửa validation + migrate/correct data có phê duyệt | Chỉ thêm rule ở warehouse |
| Duplicate event delivery | Dedup/inbox + kiểm tra side effect | Xóa ngẫu nhiên record hợp lệ |
| Ledger entry sai | Reversal/adjustment theo policy kế toán | Overwrite lịch sử không audit |
| Khác currency/amount unit | Sửa contract/mapping và chạy lại transform | Nhân 100 trên production không scope |
| Missing object attachments | Khôi phục object từ nguồn/backup, check checksum | Đánh dấu tồn tại dù file chưa phục hồi |
| Wrong customer merge | Domain-reviewed split/undo mapping | Gộp thêm bằng fuzzy match tự động |
| Sai lệch do backup/restore | Reconciliation theo recovery point | Replay vô hạn mọi event |

Ưu tiên sửa **nguyên nhân gốc**, sau đó sửa những dữ liệu đã bị ảnh hưởng và xác minh. Nếu chỉ sửa dữ liệu mà code vẫn tiếp tục tạo lỗi, discrepancy sẽ tái diễn.

## 26. Khi nào được tự động sửa dữ liệu?

**Auto-remediation** có thể phù hợp khi tính đúng đắn chứng minh được, side effect an toàn và thao tác idempotent.

Ví dụ có thể tự động:

- Rebuild search index từ source of truth đã xác nhận.
- Replay một event bị miss với eventId dedup và bounded retries.
- Refresh derived cache hoặc materialized view theo một snapshot hợp lệ.
- Retry ingest một partition ETL không có side effects ngoài dữ liệu dẫn xuất.
- Quarantine dữ liệu không hợp lệ trước khi vào bảng serving.

Ví dụ cần phê duyệt hoặc xử lý chuyên biệt:

- Chỉnh Payment ledger hoặc đánh dấu một khoản tiền đã/ chưa thanh toán.
- Gộp hoặc tách hồ sơ khách hàng.
- Xóa/audit redaction dữ liệu chứa thông tin cá nhân.
- Thay đổi chứng từ kế toán, thuế hoặc hạn mức.
- Viết lại sự kiện lịch sử ảnh hưởng nhiều consumers.
- Sửa một biến động tồn kho đã tác động đến vận đơn thực.

Một hệ thống không nên tự động chọn “giá trị mới nhất thắng” nếu dữ liệu ở nhiều nguồn có **semantics khác nhau**.

### 26.1. Điều kiện tối thiểu của auto-repair

~~~text
Known source of truth?
Deterministic transformation?
Clear target scope?
No unreviewed external side effect?
Idempotent and retry-safe?
Can record before/after evidence?
Can verify independently?
Has rate limit, dry run, rollback/compensation?
If any critical answer is NO → manual approval / escalation
~~~

Quyền service account để chạy job không tự biến job thành người có thẩm quyền phê duyệt thay đổi nghiệp vụ.

## 27. Remediation cần idempotency, checkpoint và tính lặp lại

Một job backfill có thể bị restart, chạy lại sau timeout hoặc chịu retry từ orchestrator. Vì vậy cần:

- **Idempotency key:** ví dụ **repair_case_id + target_record_id + rule_version** theo thiết kế.
- **Scoped checkpoint:** ghi tiến độ theo partition/offset/batch.
- **Expected version:** optimistic concurrency để không ghi đè một record đã có cập nhật mới.
- **Before image / change log:** ghi điều chỉnh đã thực hiện khi chính sách cho phép.
- **Dry run:** đếm và xuất danh sách/tổng dự kiến trước khi mutate.
- **Rate limiting:** tránh backfill làm sập DB/producer.
- **Atomicity:** commit transaction theo nhóm hợp lý; không dùng một transaction khổng lồ.
- **Partial failure handling:** dừng, resume hoặc rollback/compensate theo policy.
- **Audit:** lưu actor, lý do, payload hash, thời gian và result.

**Retry-safe không đồng nghĩa side-effect-free.** Một email có thể đã gửi thành công nhưng caller timeout; chạy lại mà không dedup sẽ gửi trùng.

## 28. Ví dụ PostgreSQL: Sửa projection theo nguồn có thẩm quyền

Giả sử bảng **orders_projection** là dữ liệu dẫn xuất có thể tái dựng, còn **orders_source** là source of truth, cả hai đã được chuẩn hóa cùng version và có khóa duy nhất. Một cách cập nhật kỹ thuật có kiểm soát:

~~~sql
-- Chỉ là mẫu minh họa trong môi trường kiểm thử.
-- Production cần dry run, backup/snapshot phù hợp và approval.
BEGIN;

UPDATE orders_projection p
SET status = s.status,
    amount_minor = s.amount_minor,
    source_version = s.version,
    refreshed_at = CURRENT_TIMESTAMP
FROM orders_source s
WHERE p.tenant_id = s.tenant_id
  AND p.order_id = s.order_id
  AND p.source_version < s.version
  AND p.order_id IN ('ORDER-1001', 'ORDER-1002');

-- Kiểm tra số dòng, constraints, ảnh hưởng mong đợi.
-- Chỉ COMMIT sau khi đã kiểm tra theo quy trình đã duyệt.
ROLLBACK;
~~~

Ở đây kết thúc bằng **ROLLBACK** để tránh tạo ví dụ copy-paste có thể sửa dữ liệu thật. Dùng **source_version** để tránh ghi đè projection mới hơn bằng snapshot cũ, nhưng vẫn phải xử lý delete/tombstone, không chỉ update các hàng đã có.

Trong production, nên ưu tiên chạy **pipeline rebuild/backfill chuẩn** để lưu lineage/transform version, thay vì SQL thủ công nếu có thể. Với ledger hoặc source of truth, việc UPDATE trực tiếp thường không phù hợp; dùng **domain command, reversal hoặc correction event** được kiểm soát.

### 28.1. Vì sao không dùng MERGE/UPSERT vô điều kiện?

Nếu bản sao nguồn chứa bản ghi đã bị xóa, có thể cần tombstone. Nếu **source_version** không tăng đơn điệu, một latest-timestamp-wins update có thể chọn sai. Nếu consumer thực thi nghiệp vụ phụ khi insert, UPSERT vào database bypass business side effects. Cần hiểu model trước khi chọn cơ chế.

## 29. Sửa qua domain API/command thay vì chạm DB trực tiếp

Đối với một nguồn nghiệp vụ quan trọng, một **reconciliation command** có thể là phương án đúng:

~~~text
Reconciliation Operator
        |
        | approved correction case
        v
Payment Domain API
        |
        +--> validate state transition
        +--> check provider transaction status
        +--> enforce idempotency
        +--> write audit + ledger adjustment
        +--> append outbox event
        |
        v
Consumers update projections
~~~

Lợi ích:

- Giữ invariants và authorization.
- Cho phép phát events để các projections đồng bộ.
- Có audit và reversible business operations.
- Không bỏ qua integration hooks đã thiết kế.

Hạn chế: một API command có thể quá chậm cho hàng triệu records. Khi cần bulk correction, thiết kế **batch domain processing** vẫn tôn trọng các invariant và checkpoint, thay vì mở quyền SQL UPDATE không kiểm soát.

## 30. Root cause analysis: Sửa dữ liệu và sửa hệ thống là hai việc

Một discrepancy được đóng không có nghĩa lỗi nguồn đã hết. Cần phân biệt:

- **Data correction:** đưa dataset bị ảnh hưởng về trạng thái đúng.
- **System correction:** sửa code, contract, pipeline, permission hoặc quy trình làm phát sinh lỗi.
- **Detection improvement:** thêm rule/alert để phát hiện sớm hơn lần sau.
- **Prevention:** database constraint, transactional outbox, schema evolution plan, idempotency.
- **Operational improvement:** runbook, ownership, observability, replay capacity.

Ví dụ một consumer thiếu trường **currency** khi event schema đổi. Nếu chỉ backfill, lần deploy sau lỗi tương tự có thể xảy ra. Action dài hạn cần gồm **contract test** cho event version, migration policy và alert theo số event bị quarantine.

Một postmortem nên mô tả **điều kiện hệ thống cho phép lỗi**, không chỉ quy trách nhiệm cá nhân. Song song, việc **phân công owner/approver** vẫn cần rõ để thực thi và kiểm toán.

## 31. Kiến trúc một dịch vụ đối soát

Một mô hình tham khảo:

~~~text
Sources: DB snapshots / CDC / API / object manifests
                         |
                         v
              Extract with watermarks
                         |
                         v
               Normalization layer
          - units, timezone, keys
          - contract/schema version
                         |
                         v
               Reconciliation engine
          - aggregate control totals
          - keyed compare/invariants
          - late-arrival allowance
                         |
             +-----------+-----------+
             |                       |
           MATCH                 DISCREPANCY
             |                       |
             v                       v
       Evidence store        Discrepancy registry
                                     |
                                     v
                              Owner / triage
                                     |
                                     v
                         Approved repair workflows
                                     |
                                     v
                           Independent verification
                                     |
                                     v
                           Audit + scorecards
~~~

### 31.1. Phân tách control plane và data plane

**Control plane:** rule registry, ownership, schedule, thresholds, policy, approval, exception lifecycle.

**Data plane:** extract jobs, watermark tracking, keyed compare, data sampling/exact scans, backfill/replay, verification.

Phân tách này tránh việc một người tùy ý sửa rule production đồng thời kích hoạt batch mutate dữ liệu có quyền cao. Dùng versioned configuration và approvals.

### 31.2. Data reconciliation store không nên trở thành nguồn sự thật mới

Registry cần lưu **khóa, bằng chứng đủ dùng, result và trạng thái xử lý**. Không copy toàn bộ PII hoặc payment details vào hệ thống quality nếu không thực sự cần. Có thể lưu hashes/references và truy lại nguồn qua quyền được cấp.

## 32. Tối ưu đối soát trên dữ liệu lớn

Không thể mỗi phút full-scan hàng tỷ giao dịch trên production primary. Các chiến lược:

1. **Partition theo event/business date**, tenant/tier hoặc domain boundary.
2. **Incremental reconciliation** theo checkpoint/CDC position.
3. **Control totals** để phát hiện partition nghi vấn rồi drill down.
4. **Chunked keyed comparisons** có bounded memory.
5. **Hashes/Merkle-style digests** để rút phạm vi, nhưng vẫn cần canonicalization và tránh collision assumptions.
6. **Read replicas/snapshots** hoặc compute tách biệt để giảm tải OLTP.
7. **Rate limit** query, giới hạn concurrency/timeout và không khóa bảng quá lâu.
8. **Persist reconciliation runs** với input snapshot IDs, rule versions và kết quả.
9. **Rerun deterministically** khi phát hiện rule bug hoặc delayed data.
10. **Backfill theo cửa sổ**, ghi progress để resume an toàn.

**Hash equality** của dữ liệu đã canonicalized có thể là tín hiệu mạnh rằng các tập giống nhau trong phạm vi; nhưng nếu phép canonicalization bỏ một field quan trọng, hai nguồn vẫn “khớp” theo hash và sai nghiệp vụ. Phải xác định cẩn thận field set, sorting, null semantics và encoding.

## 33. SQL và truy vấn không được là điểm gây quá tải

Một quality job có thể làm chậm chính database nguồn nếu chạy FULL OUTER JOIN trên bảng hàng trăm triệu dòng vào giờ cao điểm.

Cần:

- Sử dụng index theo join keys và time partition.
- Tránh giữ transaction snapshot quá lâu khi ảnh hưởng vacuum/retention.
- Chọn scan windows với as-of boundary rõ.
- Đặt query timeout và giới hạn parallelism.
- Theo dõi CPU, IO, locks, replication lag và connection pool.
- Không dùng CDC high-cardinality joins không giới hạn memory.
- Đưa large-scale compare sang analytical compute khi phù hợp.
- Tự dừng hoặc giảm tốc khi production saturation tăng.

**Quality control phải có resource budget** giống mọi workload khác. Một job đối soát gây outage production không đạt mục tiêu quản trị dữ liệu.

## 34. Data observability: Phát hiện sai lệch trước khi có ticket khách hàng

Quan sát pipeline nên theo dõi:

~~~text
source_committed_records_total
outbox_pending_events
cdc_source_lag_seconds
broker_consumer_lag
dead_letter_messages_total
transform_rejected_records_total
projection_freshness_seconds
reconciliation_eligible_records
reconciliation_mismatch_records_total
reconciliation_last_success_timestamp
remediation_cases_open
remediation_case_age_seconds
repair_verification_failures_total
~~~

Đây là **tên metric minh họa**, cần gắn đúng khả năng instrumentation của hệ dùng. Label nên giới hạn theo **service, dataset, rule, severity, environment**, tránh đưa order_id/trace_id vào metric label vì cardinality quá lớn.

Một alert phải phân biệt:

- **Mismatch thật:** đã qua propagation window và rule xác nhận.
- **Lag/backlog:** dữ liệu đến muộn nhưng chưa vượt tolerance.
- **Unknown quality:** job không chạy, không có quyền hoặc thiếu một nguồn.
- **Rule regression:** check vừa đổi version và phát hiện quá nhiều lỗi bất thường.
- **Repair failure:** job sửa sai hoặc verification thất bại.

**Không có cảnh báo không có nghĩa dữ liệu đúng** nếu pipeline đo đang down. Dashboard nên chỉ rõ **last checked / coverage / evidence freshness**.

## 35. SLO và error budget cho chất lượng dữ liệu

Một SLO nên đo điều người dùng thực sự cần.

Ví dụ operational projection:

~~~text
SLI = % eligible Order events xuất hiện trong reporting
      trong vòng 5 phút sau khi commit source

SLO = >= 99.9% trong rolling 30 ngày

Error budget = phần chênh được cho phép trước khi phải
               giảm triển khai rủi ro, xử lý backlog hoặc
               nâng độ tin cậy pipeline
~~~

Cần định nghĩa kỹ:

- Eligible events gồm loại nào?
- Event time lấy từ source commit timestamp hay broker receive?
- Khi source bị down, denominator xử lý thế nào?
- Duplicate delivery có đếm thêm không?
- Khi correction event xuất hiện, trạng thái trước đó có được xem là sai không?
- Phần dữ liệu pháp lý/financial critical có **zero tolerance** hoặc quy trình riêng không?

SLO freshness 99,9% **không biện minh bỏ qua một giao dịch thanh toán có số tiền lớn**. Chất lượng cần kết hợp **đếm phần trăm, business impact threshold và các invariant nghiêm ngặt**.

## 36. Data quality scorecard cần dễ hành động

Một scorecard cho mỗi dataset có thể gồm:

| Dataset | Freshness | Completeness | Keyed match | Open critical | Owner |
|---|---|---|---|---|---|
| Order projection | Theo SLO | Theo rule | Theo cửa sổ đã đóng | Số case | Order team |
| Payment ledger reporting | Theo settlement cycle | Theo provider refs | Theo batch IDs | Số case/amount | Payment/Finance |
| Inventory reservation view | Theo reservation TTL | Theo SKU/warehouse | Theo reservation IDs | Số case | Inventory team |
| Customer identity mapping | Theo quy tắc xác minh | Theo field semantics | Theo canonical ID | Số case | Identity team |

**Đừng báo GREEN nếu chưa đối soát được.** Với missing source hoặc job failure, trạng thái nên là **NO DATA/UNKNOWN** cùng thời điểm lần đo cuối, khác với “0 discrepancy”.

Scorecard còn nên cho phép drill down vào exception IDs/lineage theo quyền, chứ không đưa PII/raw payment data vào bảng công khai.

## 37. Incident severity theo mức ảnh hưởng nghiệp vụ

Có thể phân loại theo:

- **P0/P1:** dữ liệu tài chính sai gây thu/chi nhầm, leak giữa tenants, mất nguồn sự thật, phá compliance hoặc chặn hoạt động nghiệp vụ sống còn.
- **P2:** thiếu/late dữ liệu gây sai dashboard tác nghiệp hoặc ảnh hưởng nhóm khách hàng, có workaround trong giới hạn.
- **P3:** vấn đề chất lượng không ảnh hưởng trực tiếp khách hàng, có thời hạn sửa trong backlog.

Đây là **minh họa về phân lớp**, không thay severity policy tổ chức. Cần đánh giá:

~~~text
severity = f(
  domain criticality,
  affected users/transactions,
  monetary exposure,
  data loss/privacy risk,
  age and propagation,
  ability to recover,
  regulatory obligations
)
~~~

Không chỉ xếp hạng theo số bản ghi: **một** payment ledger entry sai có thể nghiêm trọng hơn hàng triệu analytics rows trễ vài phút.

Incident commander điều phối khôi phục, còn data owner phê duyệt semantics/adjustments theo chính sách. Các quyết định “chấp nhận sai lệch tạm thời” phải được ghi rõ.

## 38. Approval, audit trail và segregation of duties

Với correction có tác động lớn:

1. Người đề xuất nêu mismatch, nguồn và cách xác định đúng.
2. Người có thẩm quyền nghiệp vụ phê duyệt **expected state/correction intent**.
3. Technical owner chuẩn bị migration/backfill command, dry run và impact estimate.
4. Một người/nhóm độc lập review khi policy yêu cầu.
5. Execution được thực hiện bởi identity tối thiểu quyền, trong change window phù hợp.
6. Kết quả được **re-validate** bằng rule độc lập.
7. Case lưu actor, approver, timestamp, before/after hashes, số records, job ID và rollback plan.
8. Những thay đổi hệ thống phát sinh RCA ticket đến khi đóng.

**Audit log nên append-only/tamper-evident theo thiết kế**, phân quyền đọc và retention phù hợp. Không để actor sửa record tự xóa cả dấu vết điều chỉnh.

Với ledger, thường sử dụng **reversal/adjustment entry** thay vì ghi đè bút toán gốc, nhưng cách thức cụ thể phụ thuộc domain và quy định áp dụng.

## 39. Security và privacy trong đối soát

Dữ liệu đối soát có thể chứa **tên, email, thông tin giao dịch, mã định danh khách hàng**. Các nguyên tắc:

- **Least privilege:** job chỉ đọc những dataset/fields cần cho rule; account sửa sai tách khỏi account đối soát read-only.
- **Data minimization:** case registry lưu key/tokenized reference và evidence cần thiết, không copy mọi payload.
- **Encryption:** truyền và lưu dữ liệu qua cơ chế bảo mật phù hợp.
- **Row-level/tenant isolation:** không lấy dữ liệu tenant A để sửa tenant B vì join thiếu tenant key.
- **PII redaction:** logs/tickets/alerts không xuất toàn bộ thông tin nhạy cảm.
- **Retention:** exception evidence và snapshots có vòng đời được duyệt.
- **Access review:** quyền đặc biệt dùng trong repair có expiry và được audit.
- **Consent/deletion:** restore/backfill từ dữ liệu cũ có thể tái sinh record đã phải xóa; phải áp dụng deletion/tombstone policy.
- **Incident handling:** nếu sai lệch liên quan lộ dữ liệu hoặc truy cập trái phép, cần kích hoạt Security/Privacy workflow riêng.

Không dùng một tài khoản admin DB chung để mọi data engineer chạy script correction. Khả năng “sửa được” không đồng nghĩa được phép sửa.

## 40. Dữ liệu trễ, event duplicate và dữ liệu không xác định

Ba trạng thái dễ bị đánh đồng:

**Late but valid:** event đến trong allowed lag, dữ liệu chưa sai.

**Duplicate delivery:** broker chuyển event hai lần, projection có thể vẫn đúng nếu idempotent; không đồng nhất delivery count với business operations.

**Unknown outcome:** request đến provider, caller timeout và không biết transaction đã commit; không suy luận thất bại chỉ dựa vào timeout.

Đặc biệt với payment:

~~~text
Order → Payment provider: authorize 590000
Network timeout while waiting response
          |
          v
Outcome UNKNOWN, not definitely FAILED
          |
          v
Lookup by idempotency/reference
          |
     +----+-----------+
     |                |
  SUCCEEDED       NOT FOUND/FAILED
     |                |
     v                v
 Reconcile state   Apply retry policy
                   only when safe
~~~

Phải phân biệt **không có bằng chứng** và **bằng chứng không tồn tại**. Một reconciliation tool query thất bại vì thiếu quyền không được ghi “Payment missing”.

## 41. Data quality trong CI/CD và thay đổi schema

Phòng tránh regression bằng các quality gates:

1. **Schema validation:** các field required/type/enum tuân contract.
2. **Compatibility checks:** provider/consumer thay đổi không phá phiên bản đang chạy.
3. **Database constraints:** PK/FK/unique/check và migration rehearsal.
4. **Transformation tests:** cùng input snapshot tạo output kỳ vọng.
5. **Business invariants:** paid orders có payment reference, inventory không bị bán vượt điều kiện policy.
6. **Replay/idempotency tests:** event lặp không nhân side effect.
7. **Late/out-of-order tests:** order version cũ không ghi đè state mới.
8. **Cross-tenant security tests:** mapping không trộn dữ liệu khác tenant.
9. **Backfill dry-run tests:** job chạy lại nhiều lần vẫn tạo kết quả ổn định.
10. **Observability checks:** DQ job missing/lag không bị coi là PASS.

Một migration thêm field mới có thể triển khai theo **expand–migrate–contract**: cho consumers đọc được cả schema cũ và mới, backfill, xác nhận không còn usage cũ rồi mới remove.

**Schema-compatible không tự động semantic-compatible**. Ví dụ đổi amount từ VND sang minor currency units nhưng vẫn giữ integer là lỗi có thể rất nghiêm trọng mà type checker không thấy.

## 42. Disaster recovery và đối soát sau restore

Một restore thành công về DB engine không chứng minh các service cùng ở một trạng thái nghiệp vụ:

~~~text
Order DB restored through 10:00
Payment DB restored through 10:05
Kafka contains events through 10:10
External payment provider reflects actual state through 10:15
~~~

Sau phục hồi:

1. Ghi lại recovery point và backup IDs từng dataset.
2. Chặn/giới hạn consumer có side effect cho tới khi quyết định resume/replay.
3. Xác định **discrepancy window** giữa các recovery points.
4. Đối soát theo stable transaction IDs và provider references.
5. Ghi nhận các trạng thái **unknown**, không tự quyết định FAILED.
6. Thực hiện domain-approved correction/compensation an toàn.
7. Rebuild projections và kiểm tra business invariants.
8. Xác minh audit, counts, sums, event offsets, customer-facing flows.
9. Mở traffic có kiểm soát và theo dõi recurrence.

**PITR của từng database riêng lẻ không tạo distributed transaction across microservices.** Reconciliation và idempotency là thành phần quan trọng của DR readiness.

## 43. Ví dụ thiết kế một rule đối soát Order–Payment end-to-end

Giả sử yêu cầu:

> Mọi đơn ở trạng thái PAID quá 10 phút phải có một payment captured tương ứng và số tiền captured hợp lệ, ngoại trừ quy tắc partial captures/refunds đã được định nghĩa.

### 43.1. Inputs

~~~text
Order source:
  tenant_id, order_id, amount_minor, currency, status, paid_at

Payment ledger:
  tenant_id, order_id, provider_txn_id, amount_minor,
  currency, status, event_version, updated_at

Provider statement:
  merchant_account, provider_txn_id, settled_amount,
  currency, settlement_status
~~~

### 43.2. Eligibility

Chỉ đối soát các đơn **PAID** có **paid_at** trước watermark đã đóng và trừ allowed lag, trong phạm vi merchant/currency/tenant đúng hợp đồng.

### 43.3. Matching

- Dùng **tenant_id, order_id** để liên hệ các payment attempts.
- Dùng **provider_txn_id + merchant account** để đối chiếu provider.
- Nếu có nhiều captures/partial refunds, tổng hợp theo đúng lifecycle, không yêu cầu một dòng duy nhất.
- Tách **authorized, captured, settled, refunded** theo business semantics.
- Không so amount khác currency nếu chưa có FX policy và timestamp tương ứng.

### 43.4. Output

~~~json
{
  "caseId": "DQ-EXAMPLE-1001",
  "ruleId": "PAID_ORDER_CAPTURE_RECON_V3",
  "tenantScope": "example-tenant",
  "orderId": "ORDER-1001",
  "asOf": "2026-11-12T10:00:00Z",
  "classification": "VALUE_MISMATCH",
  "expectedMinor": 590000,
  "observedMinor": 580000,
  "currency": "VND",
  "severity": "HIGH",
  "status": "INVESTIGATING",
  "recommendedOwner": "payment-domain"
}
~~~

Đây là **bản ghi minh họa**, không phải dữ liệu production. Giá trị expected cần có **nguồn chứng minh** theo policy; không thể chỉ lấy expected bằng cách tự tin chọn bảng Order nếu ledger/provider mới có thẩm quyền đối với actual captured amount.

### 43.5. Remediation

1. Kiểm tra provider và ledger, xác định giao dịch thật, fees/refunds và mốc.
2. Data owner quyết định điều chỉnh Order state hay ledger entry, hoặc ghi nhận chargeback/partial capture.
3. Technical owner thực hiện domain command/bút toán điều chỉnh, có idempotency và audit.
4. Chạy lại rule trên case và aggregate settlement batch.
5. Xác minh không có sai lệch mới sau repair và thông báo consumers cần thiết.

## 44. Kiểm thử hệ thống đối soát

| Kịch bản | Kỳ vọng |
|---|---|
| Nguồn/target khớp hoàn toàn | Không có confirmed discrepancy |
| Event đến trễ trong allowed window | Được giữ PENDING, không báo sai ngay |
| Event đến sau allowed window | Được phân loại sai lệch theo rule và watermark |
| Consumer nhận duplicate event | Projection không nhân side effect nhờ dedup |
| Event out of order | Version/checkpoint bảo vệ state mới |
| Một giao dịch thiếu ở target | Keyed reconciliation phát hiện |
| Tổng tiền khớp nhưng hai giao dịch bù nhau | Record-level compare phát hiện |
| Bảng target chứa duplicate key | Uniqueness check phát hiện trước join |
| Cùng order_id ở hai tenants | Join không trộn tenant |
| Amount khác currency | Không cộng/trừ trực tiếp sai đơn vị |
| Provider timeout nhưng charge đã xảy ra | Outcome UNKNOWN, lookup/reconcile trước retry |
| Outbox relay crash sau publish | Replay vẫn idempotent |
| Schema thay đổi semantics | Contract tests hoặc invariant phát hiện |
| Data source unavailable | Run UNKNOWN, không tạo PASS giả |
| Backfill bị restart giữa chừng | Resume idempotent từ checkpoint |
| Một record thay đổi sau dry-run | Expected version ngăn overwrite |
| Repair approved nhưng xác minh fail | Case không được đóng |
| Job đối soát làm tăng DB load | Resource cap/timeout bảo vệ OLTP |
| Event replay sau DR restore | Không tạo duplicate payment/email |
| Dữ liệu đã phải xóa xuất hiện lại | Deletion/tombstone policy xử lý |
| Người chạy repair không được cấp quyền | RBAC/policy từ chối, có audit |
| Một rule bị sửa sai gây false alarms | Versioning/rollout và owner review |
| Dashboard chưa được kiểm tra hôm nay | Hiển thị last checked/UNKNOWN rõ |

**Test cả cơ chế phát hiện và cơ chế khắc phục.** Một detector bắt đúng lỗi nhưng repair script sửa nhầm tenant vẫn có thể gây hậu quả nghiêm trọng hơn lỗi ban đầu.

## 45. Runbook ngắn khi nhận cảnh báo sai lệch dữ liệu

### Bước 1 — Xác nhận tín hiệu

Ghi ruleId, dataset, runId, phạm vi, watermark, firstSeen, lastChecked và số records. Kiểm tra job có đủ quyền, nguồn có reachable và metric có cập nhật không.

### Bước 2 — Phân biệt trễ và sai

Xem pipeline lag, event age, backlog/DLQ và allowed window. Không mở incident data corruption nếu dữ liệu vẫn trong độ trễ hợp lệ, nhưng tiếp tục monitor.

### Bước 3 — Định lượng ảnh hưởng

Tính affected records, time range, tenants, currencies và monetary exposure nếu liên quan. Có cần freeze settlement/reporting/feature không? Quyết định theo severity policy.

### Bước 4 — Truy nguyên lineage

Dùng correlation/event IDs, outbox status, CDC checkpoint, broker offset, consumer logs, transform version, query plan để tìm lớp phát sinh lỗi.

### Bước 5 — Xác định thẩm quyền

Ai là data owner? Giá trị “đúng” được chứng minh bằng nguồn nào? Có trường hợp ngoại lệ hoặc status transition hợp lệ?

### Bước 6 — Chọn biện pháp

Replay, backfill, recompute, domain correction, accounting adjustment, quarantine hoặc accepted-risk exception. Chuẩn bị dry-run, rollback/compensation và phê duyệt tương ứng.

### Bước 7 — Thực thi có kiểm soát

Chỉ chạy đúng scope, giới hạn throughput, theo dõi transaction/offset, ghi execution ID và evidence. Dừng khi phát hiện impact ngoài dự kiến.

### Bước 8 — Xác minh độc lập

Chạy lại rule, kiểm tra control totals, keyed comparisons, downstream consumers và business flows. Không đóng chỉ vì job sửa báo “success”.

### Bước 9 — Đóng và ngăn tái diễn

Ghi RCA, owner, code/contract/pipeline fixes, DQ rule mới, test mới, thời hạn và link evidence theo policy.

## 46. Những anti-pattern cần tránh

**1. Chỉ so số dòng.** Count có thể bằng nhau dù dữ liệu sai hoặc record thiếu được bù bằng duplicate.

**2. So dữ liệu ở hai mốc khác nhau.** Eventual consistency tạo false positives nếu bỏ watermark/allowed lag.

**3. Không xác định source of truth theo field.** Chọn bên có timestamp mới hơn có thể viết đè dữ liệu đúng.

**4. Sửa reporting để dashboard xanh nhưng bỏ nguyên nhân ở producer.** Lỗi tái xuất sau lần chạy ETL kế tiếp.

**5. Cho phép mọi data engineer UPDATE ledger.** Mất audit, business invariants và segregation of duties.

**6. Dùng một quy tắc trạng thái quá đơn giản.** Authorized, captured, settled, refunded là những trạng thái khác nhau.

**7. Replay events mà không có idempotency.** Có thể tạo side effect trùng.

**8. Dùng order_id làm join key nhưng quên tenant scope.** Có thể trộn dữ liệu hai khách hàng.

**9. Tự động merge customer records theo tên/email.** Có thể hợp nhất sai hai cá nhân.

**10. Đánh dấu DQ PASS khi job không chạy.** Thiếu quan sát là UNKNOWN, không phải dữ liệu đúng.

**11. Đặt mỗi mismatch thành severity critical.** Alert fatigue làm team mất niềm tin.

**12. Chạy full scans trên OLTP vào giờ cao điểm.** Job quality trở thành nguồn gây outage.

**13. Không ghi rule version và recovery point.** Kết quả đối soát không tái tạo được.

**14. Không có owner/approval.** Sai lệch bị chuyền qua nhiều nhóm mà không ai quyết định.

**15. Chỉ sửa record sai mà không sửa code/pipeline.** Tỷ lệ tái phát cao.

**16. Tự sửa payment khi outcome không rõ.** Có thể tạo double charge hoặc sai bút toán.

**17. Quên dữ liệu lịch sử và temporal semantics.** Update giá hiện tại vào invoice đã chốt.

**18. Đưa raw PII vào ticket/metrics.** Tạo thêm rủi ro bảo mật từ hệ thống DQ.

**19. Backfill không có checkpoint/idempotency.** Thất bại giữa chừng để lại dữ liệu nửa vời.

**20. Đóng case ngay khi script trả exit code 0.** Chưa có độc lập verification và business signoff.

## 47. Checklist thiết kế một hệ thống DQ và đối soát

1. **Dataset nào quan trọng?** Đã lập inventory và phân nhóm criticality?
2. **Nguồn có thẩm quyền cho từng field là gì?** Có tranh chấp giữa domains?
3. **Các phép chiếu có temporal semantics nào?** State, event history, ledger hay snapshot?
4. **Có business/data owner và technical owner rõ?** Ai được phê duyệt correction?
5. **Data contracts có schema và ngữ nghĩa?** Currency units, timezone, null, states?
6. **Có stable keys và tenant scope đúng không?**
7. **Có validation sớm ở API/DB và contract checks ở pipeline?**
8. **Đối soát có cùng as-of boundary/watermark không?**
9. **Có allowed lag trước khi kết luận mismatch?**
10. **Có cả aggregate controls và keyed comparison khi cần?**
11. **Dữ liệu lớn có partition/incremental strategy không?**
12. **Reconciliation có thể tự làm quá tải nguồn không?** Có rate limit?
13. **Khi source unavailable, kết quả là UNKNOWN chứ không phải PASS?**
14. **Sai lệch có case ID, evidence và severity phù hợp?**
15. **Có workflow owner/approver và quyền thực thi tách biệt?**
16. **Auto-fix chỉ áp dụng thao tác idempotent an toàn?**
17. **Payment/ledger corrections có domain-approved path?**
18. **Backfill/replay có checkpoint, dry-run, rollback/compensation và audit?**
19. **Sau sửa có verify độc lập và kiểm tra downstream consumers?**
20. **Có SLO freshness/completeness/accuracy theo business use case?**
21. **Có scorecard và alert theo owner, không che UNKNOWN?**
22. **Có RCA và prevention changes để lỗi không tái diễn?**
23. **Có kiểm tra DR/replay và dữ liệu xóa theo privacy policy?**
24. **Có CI tests cho schema, semantics, idempotency và migration?**
25. **Người dùng báo cáo có biết data-as-of và exception status không?**

## 48. Kết luận

**Quản trị chất lượng dữ liệu không chỉ là làm một báo cáo đếm records sai.** Đó là một phần của kiến trúc microservices, nơi mỗi dữ liệu có semantics, nguồn thẩm quyền, vòng đời và những consumers khác nhau.

Một chương trình đối soát bền vững cần kết hợp:

- **Định nghĩa đúng:** Data contracts, business invariants, khóa và source of truth.
- **Đo đúng:** Completeness, accuracy, consistency, freshness, validity, uniqueness theo phạm vi/mốc phù hợp.
- **Phát hiện đúng:** Control totals + keyed reconciliation, watermark, allowed lag và lineage.
- **Sửa đúng:** RACI, quyền phê duyệt, idempotency, domain commands, audit và independent verification.
- **Ngăn lặp:** Root cause fixes, CI contract tests, monitoring/SLO và ownership rõ.
- **Bảo vệ dữ liệu:** Quyền tối thiểu, tenant isolation, privacy và xử lý side effects có kiểm soát.

**Câu hỏi tự kiểm tra:** *Nếu Payment Service nói một đơn đã được thanh toán nhưng Order Service và dashboard nói chưa, hệ thống có xác định được đây là dữ liệu đến trễ hay sai lệch thật, nguồn nào có thẩm quyền, ai được quyết định sửa, sửa bằng lệnh nào để không thu tiền lần hai, và bằng chứng nào xác nhận các hệ đã nhất quán trở lại?*

Nếu trả lời được với **hợp đồng, runbook, owners và bằng chứng kỹ thuật thực tế**, tổ chức đã chuyển từ “dữ liệu có vẻ đúng” sang **chất lượng dữ liệu có thể kiểm chứng và có người chịu trách nhiệm đến cùng**.
