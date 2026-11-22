# Khôi phục sau sự cố và xác minh hợp đồng, dữ liệu, phụ thuộc

## 1. Khôi phục REST API không chỉ là đưa pod về trạng thái Running

Sau một lần triển khai lỗi, API đơn hàng ngừng phục vụ trong 20 phút. Đội vận hành rollback ứng dụng, Kubernetes báo pod Ready và endpoint **/actuator/health** trả HTTP 200. Nhưng một phần order đã được tạo ở database chưa đi sang payment, Redis vẫn giữ dữ liệu cũ, client thấy 409 khi retry một số request, và JWT mới phát hành không được một instance xác thực. Gọi sự cố là “đã khôi phục” lúc này quá sớm.

Trong module **INTEGRATION_API_REST**, khôi phục thành công phải đồng thời xác minh các ranh giới mà client phụ thuộc:

1. **Hợp đồng HTTP/API:** URI, method, status, headers, content, version và OpenAPI còn hoạt động đúng.
2. **Tính đúng đắn dữ liệu:** bản ghi bền vững, không mất/nhân đôi side effect, quan hệ tenant và trạng thái workflow nhất quán.
3. **Phụ thuộc:** gateway, identity provider, database, cache, message broker, payment/inventory service và DNS/TLS hoạt động theo chế độ phục hồi.
4. **Bảo mật và khả năng quan sát:** xác thực, phân quyền, rate limit, audit, metrics/traces/logs còn hiệu lực; không dùng bypass nguy hiểm để “đưa 200 lên”.
5. **Trải nghiệm người dùng:** thao tác quan trọng thật sự hoàn thành, không chỉ endpoint health còn sống.

**Mục tiêu học tập:** biết phân loại sự cố; phân biệt **RTO/RPO** với SLA/SLO; thiết kế runbook khôi phục theo các cổng kiểm chứng; thực hiện rollback/rollforward an toàn với schema và dữ liệu; xác minh contract HTTP cùng downstream; viết smoke/contract/reconciliation tests bằng Java/Spring; tổ chức quyết định mở traffic bằng bằng chứng.

> **Nguyên tắc:** Chỉ chuyển trạng thái **RECOVERED** khi có bằng chứng hệ thống đạt tiêu chí phục vụ đã công bố. **Liveness, readiness, HTTP 200 và một dashboard xanh không thay thế kiểm tra dữ liệu, quyền và tác động nghiệp vụ.**

### 1.1. Tình huống xuyên suốt: OmniOrder

API có ba thao tác chủ đạo:

~~~http
GET /api/orders/ord-741 HTTP/1.1
Authorization: Bearer <access-token>

POST /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: checkout-741

{"customerId":"cus-17","items":[{"sku":"BOOK-01","quantity":1}]}
~~~

~~~http
GET /api/operations/op-741 HTTP/1.1
Authorization: Bearer <access-token>
~~~

Hợp đồng ví dụ: POST tạo order có thể trả **201 Created** nếu hoàn tất đồng bộ, hoặc **202 Accepted + Location đến operation** nếu bất đồng bộ. GET order cần phân quyền theo tenant/owner. Idempotency-Key được lưu theo **logical intent** để retry sau timeout không tạo order trùng. Khi khôi phục, phải kiểm cả **kết quả nhận HTTP** lẫn **trạng thái sau cùng của operation**.

## 2. RTO, RPO, SLO và blast radius: chọn đích trước khi sửa

| Khái niệm | Câu hỏi | Ví dụ minh họa |
|---|---|---|
| **RTO (Recovery Time Objective)** | Thời gian tối đa mục tiêu để khôi phục khả năng phục vụ | Checkout hoạt động lại trong 30 phút |
| **RPO (Recovery Point Objective)** | Mức mất dữ liệu theo thời gian có thể chấp nhận | RPO 0 cho committed payment ledger; catalog có thể khác |
| **SLO** | Tỷ lệ trải nghiệm đạt mục tiêu trong cửa sổ đo | 99,9% eligible POST được phục vụ đúng |
| **Error budget** | Lượng sự kiện xấu cho phép theo SLO | 0,1% eligible requests trong 28 ngày |
| **Blast radius** | Phạm vi tài nguyên, tenant, vùng, operations bị ảnh hưởng | Chỉ region A hoặc toàn checkout |
| **MTTD / MTTR** | Thời gian phát hiện / khôi phục đo được | Chỉ số vận hành, không phải đích thay RTO |

**RTO/RPO là mục tiêu thiết kế**, không tự chứng minh hệ thống đạt chúng. RPO=0 cho một transaction liên vùng đòi cơ chế bền vững/replication/quorum tương ứng; không thể tuyên bố bằng cách thấy DB replica đã lên. Một RPO có thể khác theo **loại dữ liệu**: product catalog tái tạo được; payment/authorization ledger cần kiểm soát chặt hơn.

Trước khi chọn biện pháp cứu dịch vụ, ghi lại:

- **Impact:** tài nguyên/method nào lỗi, người dùng/tenant/region nào, lỗi 5xx/429/timeout hay sai dữ liệu.
- **Last known good:** deployment artifact/config/schema/policy và thời điểm cuối có chứng cứ tốt.
- **Write safety:** có thể còn write đang xử lý, event đang đi, hoặc payment provider đã commit dù client timeout?
- **Recovery options:** rollback binary, rollback traffic, rollforward patch, restore DB, replay messages, bypass cache có kiểm soát.
- **Owner/decision:** ai được quyền đóng ghi, chuyển traffic, phục hồi dữ liệu và chấp nhận residual risk?

Nếu không biết nguồn dữ liệu nào đã commit, **đừng xóa bảng hay reset queue để làm lỗi biến mất**. Đầu tiên phải bảo tồn chứng cứ cần thiết, giới hạn tác động và xác định khả năng tái xử lý an toàn.

### 2.1. Bốn loại sự cố dễ nhầm

| Loại | Triệu chứng | Cách xác minh đầu tiên |
|---|---|---|
| **Availability** | 502/503/504, timeout, connection refused | Edge và application request metrics, readiness, dependency |
| **Contract regression** | Trả 200 thay 201, thiếu Location, JSON schema đổi | Contract tests tại API boundary, diff OpenAPI |
| **Data correctness** | Order trùng, status kẹt, mất event, đọc dữ liệu cũ | DB reconciliation, ledger, outbox/queue offsets |
| **Security regression** | Token hợp lệ bị 401, tenant khác đọc được order, audit mất | JWT/ACL negative tests, security events/audit |

Một sự cố có thể thuộc nhiều loại. **Sửa phần dễ thấy nhất không tự khôi phục các phần còn lại.**

## 3. Quy trình ứng cứu theo cổng kiểm chứng

~~~mermaid
flowchart TD
    D[Phát hiện & xác minh tác động] --> S[Ổn định, giới hạn blast radius]
    S --> E[Giữ evidence & chụp trạng thái]
    E --> C{Chọn rollback / rollforward / restore}
    C --> R[Thực thi thay đổi có kiểm soát]
    R --> H{HTTP contract đạt?}
    H -->|Không| S
    H -->|Có| B{Dữ liệu & workflow đạt?}
    B -->|Không| Q[Reconcile / replay / sửa dữ liệu an toàn]
    Q --> B
    B -->|Có| P{Phụ thuộc & bảo mật đạt?}
    P -->|Không| S
    P -->|Có| T[Canary và mở traffic từng phần]
    T --> V{SLI, synthetic, outcome ổn định?}
    V -->|Không| S
    V -->|Có| F[Thông báo khôi phục & theo dõi hậu sự cố]
~~~

Các bước có thể chạy song song, nhưng **cổng mở traffic cần đồng thời thỏa các điều kiện bắt buộc**. Bảng sau gợi ý quyết định:

| Giai đoạn | Hành động | Bằng chứng đầu ra |
|---|---|---|
| **Detect** | So sánh edge errors, business outcomes, báo cáo khách | Incident timeline, scope, severity |
| **Contain** | Dừng rollout, giảm traffic đến vùng lỗi, tắt feature gây side effect | Ảnh hưởng không tiếp tục mở rộng |
| **Preserve** | Lưu release/config digest, metrics, audit, DB/queue snapshot/offset | Đủ căn cứ phân tích và đối soát |
| **Recover** | Rollback/rollforward, failover hoặc restore có runbook | Bản triển khai và nguồn dữ liệu xác định |
| **Verify** | HTTP, data, dependencies, security, canary | Báo cáo PASS/FAIL từng tiêu chí |
| **Reopen** | Mở traffic theo giai đoạn với auto-stop guard | SLI và nghiệp vụ ổn định dưới tải thật |
| **Review** | Hậu kiểm và action items | Root-cause hypotheses, thử nghiệm tái diễn |

### 3.1. Phân vai và giao tiếp

Nên có **incident commander** điều phối thời điểm/ưu tiên, **technical leads** phụ trách phục hồi hệ thống, người giữ **data reconciliation**, người kiểm **security/tenant boundaries**, và người cập nhật stakeholder. Không để nhiều người cùng chạy schema rollback/purge/replay khác nhau trong khi không thống nhất nguồn sự thật.

Mỗi quyết định quan trọng ghi **UTC timestamp, ai duyệt, command/change ID, điều kiện dừng, kỳ vọng và kết quả**. Không đưa token, dữ liệu khách hàng hoặc secret vào chat incident công khai. Khi chưa có đủ bằng chứng, thông báo đúng trạng thái **degraded / partial recovery**, không tuyên bố “mọi giao dịch đã thành công”.

## 4. Ổn định và chọn rollback hay rollforward

**Stop the bleeding** thường quan trọng hơn tìm root cause ngay. Tùy sự cố, có thể dừng rollout, giữ phiên bản tốt, giới hạn concurrency, giảm tỷ lệ traffic, tắt tác vụ gửi side effect hoặc đưa endpoint vào chế độ từ chối có kiểm soát.

### 4.1. Chiến lược khôi phục

| Biện pháp | Khi phù hợp | Rủi ro cần chặn |
|---|---|---|
| **Rollback binary** | Regression app mới nhưng schema/data tương thích | Binary cũ không hiểu schema/migration mới |
| **Rollforward hotfix** | Bug nhỏ, có thể kiểm chứng patch nhanh | Thêm thay đổi trong khi system chưa ổn định |
| **Traffic rollback/failover** | Region/instance lỗi, region khác còn tốt | Session/state, replica lag, quota, DNS TTL |
| **Feature flag/kill switch** | Chức năng mới gây lỗi, có đường an toàn | Flag chỉ che UI, background job vẫn chạy |
| **Disable writes có chọn lọc** | Không xác định commit state, nguy cơ double charge | Mất khả dụng tạm; cần thông báo hợp đồng rõ |
| **Restore/point-in-time recovery** | Hư hỏng dữ liệu, có backup đã xác minh | Mất ghi sau restore point, split-brain, replay trùng |
| **Reconcile / replay** | Workflow thiếu message/side effect | At-least-once delivery, order, dedup và external provider |

**Đừng coi rollback code đồng nghĩa rollback schema/data.** Khi migration đã thêm/đổi cột, dữ liệu đã được ghi theo schema mới hoặc event shape đã đổi, binary cũ có thể lỗi hoặc đọc sai. Một chiến lược **expand → migrate → contract** giúp giữ tương thích: thêm cột/field tương thích trước; deploy code đọc/ghi được phiên bản trung gian; backfill; cuối cùng xóa phần cũ sau giai đoạn quan sát.

### 4.2. Ví dụ HTTP của chế độ giảm chức năng

Nếu hệ thống cố ý từ chối ghi checkout tạm thời thay vì nhận rồi mất đơn:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: checkout-741
Content-Type: application/json

{"customerId":"cus-17","items":[{"sku":"BOOK-01","quantity":1}]}

HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 30
Cache-Control: no-store

{"type":"https://api.example.test/problems/checkout-unavailable",
 "title":"Checkout temporarily unavailable","status":503,
 "code":"CHECKOUT_UNAVAILABLE"}
~~~

Đây là **minh họa hai message HTTP liên tiếp**, không phải cú pháp một request gồm luôn response. **Retry-After: 30** là gợi ý bằng giây, không bảo đảm POST an toàn để thử lại. Chỉ khi endpoint hỗ trợ **Idempotency-Key** bền vững hoặc operation inquiry, client mới nên retry cùng ý định/payload theo policy. Nếu gateway từ chối **trước khi chuyển request vào app**, cần có bằng chứng; nếu mất kết nối **sau khi app có thể commit**, outcome là không chắc chắn.

**Không** trả 200 cho lệnh tạo đơn rồi âm thầm bỏ hàng đợi chỉ để dashboard availability xanh. Nếu endpoint chuyển sang 202, phải có **durable operation resource**, cơ chế kiểm status và SLA/SLO hoàn tất riêng.

## 5. Khôi phục dữ liệu: backup, transaction, event và idempotency

Dữ liệu thường quyết định liệu có thể thực sự mở lại API. Một ứng dụng được rollback về phiên bản cũ vẫn có thể đang xử lý order đã commit trước sự cố, payment provider đã thu tiền, hoặc consumer sẽ phát lại message sau khi kết nối trở lại.

### 5.1. Xác định source of truth và RPO thực tế

| Thành phần | Điều phải đối chiếu | Nguy cơ phổ biến |
|---|---|---|
| **Database chính** | Latest committed revision, schema, constraints, transaction log | Restore lệch thời điểm, bỏ sót write |
| **Read replicas** | Replication lag, promotion/fencing, consistency mode | Đọc stale hoặc split-brain |
| **Redis/cache** | TTL, version, key scope, invalidation lag | Trả dữ liệu cũ; cache không phải backup |
| **Outbox/message broker** | Event ID, offset, ack, DLQ, consumer lag | Mất publish, replay trùng, sai thứ tự |
| **Idempotency ledger** | Tenant + operation + key, fingerprint, state, outcome, TTL | Retry tạo thêm side effect |
| **External payment/inventory** | Provider receipt/reference, final status, callback | App ghi FAILED nhưng provider đã xử lý |
| **Object storage** | Object version, checksum, permission, metadata | DB trỏ vào file đã mất/không truy cập được |

**RPO không đo bằng thời gian hoàn tất restore.** Khôi phục snapshot DB lúc 10:00 vào 10:30 có thể đạt RTO 30 phút nhưng đã mất các ghi sau 10:00. Nếu doanh nghiệp yêu cầu RPO=0 với payments, phải có chiến lược transactional durability/replication/reconciliation tương ứng và **không coi snapshot cũ là đủ**.

Các thao tác restore phải chạy trong **môi trường hoặc cửa sổ được phê duyệt**, có inventory của backup, khả năng đọc/giải mã, checksums, recovery timeline, replication topology và phương án rollback của chính lần restore. **Không tự động chạy lệnh destructive restore trong production** chỉ vì phát hiện 5xx.

### 5.2. Point-in-time recovery và dữ liệu vừa bị ghi

Quy trình có kiểm soát:

1. Chặn hoặc điều phối writes mới; biết **fencing point** để tránh hai writers cạnh tranh sau failover.
2. Chọn recovery target timestamp/LSN và xác nhận backup + WAL/binlog có thể replay đến đó.
3. Restore **vào môi trường cách ly** trước, kiểm integrity, schema, count, constraints, mẫu dữ liệu và khả năng chạy ứng dụng.
4. Lập danh sách các transactions trong **khoảng có thể bị mất**; đối chiếu outbox, audit, external receipts và request logs.
5. Chọn cách **replay có idempotency, reconcile hoặc compensating action**; không copy dữ liệu mù từ hệ thống cũ vào DB mới.
6. Kiểm ledger và các side effects trước khi mở lại đường ghi; giữ bằng chứng nguồn/đích cho postmortem.

Nếu đã thay schema theo migration không tương thích, backup DB có thể **không tương thích binary cũ**. Kiểm cả code artifact, configuration, DB schema version và event schema như một bộ phiên bản phục hồi; không nâng/hạ từng thành phần độc lập rồi mong hoạt động.

### 5.3. Đối soát giao dịch thay vì chỉ đếm HTTP 201

Một bảng đối soát cần ít nhất các mối liên hệ:

~~~text
logical_intent_id  -> idempotency key + verified tenant + request fingerprint
order_id           -> DB committed order + current revision/state
outbox_event_id    -> event for order creation + published/acked state
provider_ref       -> payment/inventory external reference + outcome
operation_id       -> 202 workflow public status, terminal result
~~~

Ví dụ một truy vấn PostgreSQL **chỉ-đọc** phát hiện order chưa có outbox event (cần sửa theo schema thật):

~~~sql
SELECT o.id, o.tenant_id, o.created_at
FROM orders AS o
WHERE o.created_at >= :incident_start
  AND o.created_at < :incident_end
  AND NOT EXISTS (
    SELECT 1
    FROM order_outbox AS e
    WHERE e.aggregate_id = o.id
      AND e.event_type = 'OrderCreated'
  );
~~~

**Không kết luận mọi row kết quả đều mất event:** có thể outbox đã được archive, operation thuộc luồng khác, transaction rollback, hoặc schema đã đổi. Đọc thêm audit/CDC và kiểm theo business rule. Truy vấn phải chạy bằng tài khoản có quyền giới hạn và tránh dump dữ liệu nhạy cảm ra log/chat.

Đặc biệt quan trọng: nếu payment provider đã charge, **gửi lại POST với idempotency key mới** có thể thu tiền hai lần. Tìm provider receipt theo merchant reference và key của provider trước khi xử lý compensation/retry. **Exactly-once delivery** không mặc nhiên có chỉ vì broker có transaction; phải thiết kế **idempotent consumer** và ràng buộc duy nhất theo intent/business key.

### 5.4. Outbox, retry và message redrive

Quy tắc an toàn khi consumer khởi động lại:

- **At-least-once**: một event có thể được nhận hai lần. Consumer phải kiểm **event ID hoặc business intent key** trong transaction đủ chặt.
- **Ordering**: event v19 đến trước v18 không được lùi trạng thái, quyền hoặc cache pointer về v18.
- **DLQ/redrive**: chỉ replay sau khi kiểm nguyên nhân độc, phiên bản schema và phạm vi event; đặt giới hạn attempt/backoff.
- **Transactional outbox**: event gắn với DB transaction nguồn; sau crash relay có thể phát lại. Không coi ack broker là DB side effect đã commit.
- **External actions**: phải có provider idempotency/inquiry và reconciliation, vì local DB transaction không bao trùm payment provider.

Đối với cache sau restore, **invalidate/namespace-version** theo data generation để tránh một bản Redis/CDN từ “tương lai” hoặc schema khác phục vụ body không tương thích. Việc **xóa hết cache** cũng có thể gây stampede DB lúc mở traffic; nên có warm-up, rate limit và limiter tại tầng nguồn.

## 6. Xác minh hợp đồng REST sau khôi phục

Hợp đồng không chỉ là HTTP status thành công. Phải kiểm **method/URI, media type, schema, response headers, security, idempotency và mã lỗi** tại cùng ranh giới mà client thực sự sử dụng (ưu tiên qua gateway/edge).

### 6.1. Ma trận smoke/contract test

| Hành động | Kết quả mong đợi | Lý do sau sự cố |
|---|---|---|
| GET /api/orders/{id} của chủ sở hữu | 200 JSON đúng schema, tenant, ETag/cache theo contract | Kiểm định tuyến, auth và DB |
| GET order không tồn tại | 404 Problem Details | Kiểm mapping và không lộ stack |
| GET order thuộc tenant khác | 403/404 theo policy, **không 200/304** | Chặn BOLA sau rollback |
| POST tạo order hợp lệ | 201 + Location hoặc 202 + operation URI | Khôi phục contract create |
| POST cùng key + payload | Outcome được replay theo contract, **1 side effect** | Chống double order |
| POST key cũ + payload khác | 409 với mã lỗi ổn định | Ledger/fingerprint còn hiệu lực |
| POST body invalid | 400/422 theo contract, field errors | Validation không bị bỏ qua |
| GET với If-None-Match mới nhất | 304 không body khi còn quyền | Validator và cache đúng |
| PATCH với If-Match lỗi thời | 412, DB không bị ghi | Concurrency sau schema changes |
| GET collection với cursor | Items, next link/cursor, sort đúng | Không nhân bản/bỏ sót dữ liệu |
| Hết quota/overload | 429/503 + Retry-After khi áp dụng | Không retry storm |
| Token thiếu/sai/hết hạn | 401 + WWW-Authenticate phù hợp | Identity integration |
| Scope đúng nhưng resource sai quyền | 403/404; không lộ dữ liệu | ACL/tenant |
| CORS preflight từ origin duyệt | OPTIONS đúng headers, không bắt JWT actual POST | Browser API trở lại hoạt động |

Không nhất thiết smoke test chạy **tất cả các luồng có side effect bằng tiền thật**. Dùng tenant/test account chuyên dụng, sandbox provider, idempotency key riêng cho phép thử, giới hạn tốc độ và cleanup/compensation đã được chấp thuận. Một request 201 trên sandbox **không chứng minh** production provider đã đối soát những giao dịch trong thời gian outage.

### 6.2. Ví dụ 201/202 và lỗi RFC 9457

~~~http
HTTP/1.1 201 Created
Location: /api/orders/ord-741
Content-Type: application/json
Cache-Control: no-store

{"id":"ord-741","status":"CREATED"}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /api/operations/op-741
Content-Type: application/json

{"operationId":"op-741","state":"PENDING"}
~~~

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"https://api.example.test/problems/idempotency-conflict",
 "title":"Conflicting idempotency intent","status":409,
 "code":"IDEMPOTENCY_KEY_REUSED"}
~~~

**201** mô tả resource đã được tạo; **202** chỉ là tiếp nhận xử lý chưa hoàn tất và cần cách theo dõi outcome. **Problem Details (RFC 9457)** cung cấp type/title/status/detail/instance với **code** là extension của API ví dụ. Sau recovery, schema lỗi phải giữ tương thích với OpenAPI và client cũ, không trả HTML mặc định từ gateway thay cho JSON có hợp đồng mà không được phát hiện.

### 6.3. Conditional GET, cache và authority

Sau restore hoặc rollback, **Cache-Control/ETag/Last-Modified** có thể không còn khớp version dữ liệu. Cần kiểm:

1. Source of truth đã có revision kỳ vọng.
2. Redis/local cache không giữ representation từ bản release/schema cũ.
3. CDN/browser có thể còn bản thể fresh theo TTL; xác định giới hạn stale thực tế.
4. **If-None-Match cũ** phải trả **200 body mới** khi origin có dữ liệu mới và không còn trong khoảng stale được cho phép.
5. **304** chỉ được quyết định **sau xác thực và kiểm quyền**, không dùng ETag để khẳng định order tồn tại cho principal đã bị thu hồi quyền.

Một bản thể cũ vẫn được trả 200 dưới cache TTL đôi khi đúng với **bounded staleness**, nhưng **không đúng** nếu checkout đọc giá chốt hoặc hợp đồng yêu cầu read-your-writes ngay sau commit. Không dùng **cache busting query random** như bằng chứng invalidation thành công: nó chỉ chuyển sang cache key khác.

### 6.4. OpenAPI và consumer compatibility

Đối chiếu **artifact OpenAPI đã công bố** với OpenAPI từ release phục hồi: paths, HTTP methods, required fields, enum, nullability, error codes, response headers và security schemes. **Backward-compatible schema** không đồng nghĩa runtime đúng, nên vẫn phải gửi request thực đến route canary, nhất là khi gateway có rewrite, WAF, auth policy hoặc CORS config riêng.

Nếu bản khôi phục không hiểu một field được client mới gửi, **đừng âm thầm bỏ field có ý nghĩa nghiệp vụ** để giữ 2xx. Xem xét giữ release tương thích, rollforward hoặc route theo phiên bản có hợp đồng rõ. **Không rollback authorization** về policy rộng hơn chỉ để contract tests chuyển xanh.

## 7. Xác minh phụ thuộc và sự cố dây chuyền

API có thể Ready trong khi dependency phục vụ **chậm, trả dữ liệu cũ hoặc sai quyền**. Kiểm “kết nối TCP thành công” không đủ để xác minh semantics.

| Phụ thuộc | Xác minh trong recovery | Thất bại thường gặp |
|---|---|---|
| **DNS/TLS/ingress** | Cert/hostname, chain, routing, HTTP version, timeouts | Cert cũ, route sai, 502 tại edge |
| **API gateway/WAF** | Rewrite, auth, rate limit, request size, caching, CORS | 401/403/429 ngoài app, response biến dạng |
| **OIDC/JWT issuer/JWKS** | Issuer/audience/key rotation, clock skew, refresh | Mới 401 hàng loạt, key cache cũ |
| **Database leader/replica** | Writable leader, transaction success, lag, migration level | Split-brain, stale reads, deadlocks |
| **Redis** | Connectivity, key namespace/TTL, version, eviction behavior | Cache poison, stampede khi restart |
| **Message broker/outbox** | Lag, DLQ, publish/consume, event version | HTTP 202 tốt nhưng job kẹt |
| **Payment/inventory** | Sandbox/real provider status, inquiry, idempotency contract | Unknown outcome sau timeout |
| **Object store/search** | Access, checksum/version, projection lag | Link hỏng, kết quả tìm kiếm stale |
| **Observability** | Scrape/trace/log coverage, timestamps, dashboard alert | “Không có lỗi” vì mất telemetry |

Kiểm tra theo **tuyến người dùng đi qua**, không chỉ host nội bộ. Khi phụ thuộc chậm, circuit breaker, retry và timeouts phải có ngân sách tổng; nhiều tầng cùng tự retry có thể nhân tải lên gấp nhiều lần sau failover.

### 7.1. Readiness, liveness, startup không phải một thứ

- **Liveness** trả lời: tiến trình có cần restart vì đã không thể tiến triển? Không nên gắn mọi downstream outage vào liveness, nếu không cả cluster có thể restart loop khi database hỏng.
- **Readiness** trả lời: instance có sẵn sàng **nhận traffic loại này** không? Nó cần phản ánh khả năng đáp ứng tối thiểu, nhưng tránh check tốn chi phí gây thêm tải khi dependency đang lỗi.
- **Startup** cho phép ứng dụng khởi động/làm ấm theo ngưỡng hợp lý trước khi các probe khác được đánh giá.

Spring Boot Actuator thường có health probe groups trong môi trường phù hợp, nhưng **readiness=UP không xác nhận business workflow hoặc tính đúng đắn dữ liệu**. Với một API có nhiều chức năng, readiness quá tổng quát cũng có thể chặn chức năng đọc khỏe vì payment API đang lỗi. Cân nhắc **degraded modes** theo endpoint, cùng sự phân loại 503 có ý nghĩa, thay vì ép mọi pod NotReady.

## 8. Java/Spring Boot: kiểm tra phục hồi bằng tín hiệu có ý nghĩa

Một API Spring Boot có thể xuất probe sức khỏe cho orchestrator và các phép kiểm nghiệp vụ riêng cho **đội vận hành**, nhưng không nên để probe tự tạo order, charge tiền hoặc scan bảng lớn mỗi giây.

### 8.1. Actuator và các probe

Ví dụ cấu hình Spring Boot trong môi trường có **spring-boot-starter-actuator**:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Liveness/readiness có thể được truy cập theo các nhóm health như **/actuator/health/liveness** và **/actuator/health/readiness** khi môi trường và phiên bản hỗ trợ. Đường **/actuator/prometheus** chỉ có khi có metrics registry tương ứng, và phải giới hạn qua mạng/identity policy. **Không xuất details về DB URL, secrets hoặc topology** cho người gọi công khai; có thể tách management port hoặc bảo vệ bằng auth/mTLS.

Không đặt **toàn bộ dependency** vào liveness. Với database đang failover, restart mọi pod đồng loạt thường làm phục hồi chậm hơn. Còn readiness nên phản ánh **điều kiện không thể phục vụ traffic**, không phải một bài kiểm thử nghiệp vụ đầy đủ. Với API nhiều chức năng, nếu chỉ checkout lỗi mà read-only healthy, cần cân nhắc policy route-level hoặc degraded response thay vì trừu tượng một cờ UP/DOWN toàn hệ thống.

### 8.2. HealthIndicator có giới hạn

Một kiểm tra phụ thuộc đủ nhẹ có thể trả DOWN/UNKNOWN cho dashboard nội bộ:

~~~java
import java.time.Duration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

interface DependencyProbe {
    // Kiểm đã có timeout và không thực thi side effects.
    boolean isReachableWithin(Duration timeout);
}

@Component("orderDatabase")
class OrderDatabaseHealthIndicator implements HealthIndicator {
    private final DependencyProbe probe;

    OrderDatabaseHealthIndicator(DependencyProbe probe) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        try {
            boolean ok = probe.isReachableWithin(
                Duration.ofMillis(250));
            return ok ? Health.up().build()
                      : Health.down().build();
        } catch (Exception failure) {
            // Không đính kèm exception/message nhạy cảm.
            return Health.down().build();
        }
    }
}
~~~

Đây là **fragment**: DependencyProbe và policy phân nhóm phải được triển khai riêng; không phải readiness group sẽ mặc nhiên bao gồm bean này. Nếu muốn thêm một indicator vào group, cần cấu hình inclusion tùy phiên bản. Không để probe tạo traffic quá dày khi DB đang lỗi, không hiển thị thông tin exception ra Internet, và không đưa một kiểm tra payment bên ngoài có độ trễ cao vào liveness.

### 8.3. Degraded mode kiểm được bằng HTTP

Ví dụ đường checkout được tạm đóng có kiểm soát trong thời gian đối soát:

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;

interface RecoveryGate {
    boolean acceptingNewOrders();
}

@RestController
@RequestMapping("/api/orders")
class OrdersRecoveryController {
    private final RecoveryGate gate;
    private final OrdersCommandService orders;

    OrdersRecoveryController(RecoveryGate gate,
                             OrdersCommandService orders) {
        this.gate = gate;
        this.orders = orders;
    }

    @PostMapping(consumes = "application/json")
    ResponseEntity<?> create(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody CreateOrderRequest input,
            @AuthenticationPrincipal Jwt jwt) {
        // Phải đi qua SecurityFilterChain (JWT, scope) trước.
        if (!gate.acceptingNewOrders()) {
            ProblemDetail p = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
            p.setTitle("Checkout temporarily unavailable");
            p.setProperty("code", "CHECKOUT_UNAVAILABLE");
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .header("Retry-After", "30")
                .cacheControl(CacheControl.noStore())
                .body(p);
        }
        return orders.createAuthorized(jwt, key, input);
    }
}
~~~

**Ví dụ chỉ minh họa gate**, không phải controller hoàn chỉnh: CreateOrderRequest, OrdersCommandService và logic phân quyền/validation/idempotency cần có. **Không triển khai duplicate route song song** với OrdersController thật; đặt gate ở handler/service/filter hiện hữu. Gắn **@Valid** và validation chặt tại thực tế; source of truth của gate phải được phân phối nhất quán giữa pods và có audit về người thay đổi.

Khi gate đóng, server phải chứng minh **không có business side effect mới**, không chỉ kiểm status 503. Nếu request đã vào app trước khi đóng gate, cần quy tắc xử lý in-flight requests/ledger; không kill transaction nửa chừng rồi mặc định chưa commit. Một cờ feature không tự bảo đảm transaction/side effect bên ngoài đã dừng.

## 9. Phục hồi bảo mật và cache sau thay đổi cấu hình

Trong sự cố auth, cách “bỏ JWT validator cho qua” có thể đưa HTTP 200 trở lại nhưng làm hệ thống **không phục hồi an toàn**. Sau failover, cần xác minh:

- **JWT verification:** chữ ký, issuer, audience, exp/nbf, JWKS rotation/cache, key availability. Không tin X-User/X-Tenant do client tự gửi.
- **Authorization:** scope/role đúng thao tác, tenant/owner/membership đúng object; GET user A không được đọc order B.
- **Service-to-service:** mTLS/credential rotation, audience và delegated identity; không cho fallback sang tài khoản admin toàn cục.
- **CORS/CSRF:** OPTIONS preflight cho frontend được duyệt; POST dùng cookie phải giữ CSRF defense. CORS không phải authentication.
- **Audit:** log thay đổi cấu hình, đóng/mở gate, data repair, replay, quyền thao tác; không log raw token, payment details hoặc PII.
- **Cache isolation:** cache key theo verified tenant/representation; token hết hạn/thu hồi quyền không thể tiếp tục nhận body riêng tư hoặc 304 nhờ ETag cũ.

### 9.1. Restore DB nhưng CDN/Redis vẫn phát phiên bản cũ

Giả sử DB đã restore/migrate tới generation **g42** nhưng Redis còn JSON serialization của release cũ **g41**. Một giải pháp có thể dùng key prefix **catalog:g42:...** hoặc bump cache namespace, kết hợp TTL/purge theo provider và warm-up có giới hạn. Không chỉ xóa Redis rồi mở ngay 100% traffic khiến DB bị stampede.

Nếu **đường ghi giao dịch** yêu cầu giá/tồn kho mới nhất, hãy đọc nguồn authoritative trong transaction hoặc kiểm version policy; không tin cached GET catalog. Nếu user đã mất quyền, **no-store** trên response mới cũng không tự xóa bản sao lưu dưới chính sách cũ: cần đánh giá cache purge/security incident response.

## 10. Kiểm thử tự động bằng MockMvc, HTTP client và DB

### 10.1. MockMvc kiểm 503 khi gate đóng

Ví dụ test Spring MVC với SecurityFilterChain, gate và command service đã được nạp/mocked đúng:

~~~java
@Test
void closedGateReturns503WithoutCreatingOrder() throws Exception {
    given(gate.acceptingNewOrders()).willReturn(false);

    mvc.perform(post("/api/orders")
            .with(jwt()
                .jwt(j -> j.subject("buyer-17")
                    .claim("tenant_id", "tenant-A"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.create")))
            .header("Idempotency-Key", "recovery-test-741")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"customerId":"cus-17",
                 "items":[{"sku":"BOOK-01","quantity":1}]}
                """))
        .andExpect(status().isServiceUnavailable())
        .andExpect(header().string("Retry-After", "30"))
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(jsonPath("$.code")
            .value("CHECKOUT_UNAVAILABLE"));

    verifyNoInteractions(orders);
}
~~~

Đây là **test fragment** cần JUnit 5, Mockito, MockMvc, Spring Security Test, JSON fixtures và imports. **jwt()** giả lập authenticated principal, không chứng minh JWT sai chữ ký/issuer/audience bị từ chối; kiểm decoder thật ở security integration test. **verifyNoInteractions** trên mock không chứng minh không tồn tại background consumer side effect: vẫn phải test DB/outbox/provider và in-flight behavior.

### 10.2. Reconciliation test với DB thật

Ví dụ các assertions có giá trị sau restore:

~~~text
Given: 2 POST attempts, CÙNG tenant, key, payload
When:  attempt đầu commit order và outbox, HTTP response bị mất
       attempt thứ hai retry với key cũ
Then:  1 order, 1 logical intent, 1 payment effect
       ledger fingerprint và outcome có thể replay

Given: consumer nhận 2 bản sao event OrderCreated(eventId=E)
When:  redrive qua broker
Then:  downstream effect chỉ được áp dụng 1 lần

Given: tenant A và B có order với dữ liệu fixture phân biệt
When:  user A GET order B
Then:  403/404 đúng policy, không rò JSON/cache/ETag
~~~

Dùng **Testcontainers** hoặc một môi trường DB/broker/provider sandbox đủ sát production; assert **unique constraints, transaction outcomes, event offsets, provider receipts** chứ không chỉ so response JSON. Test mất HTTP response **sau commit** đặc biệt quan trọng, vì đó là lúc client dễ nghĩ “thất bại” rồi tạo ý định mới. Với external provider thật, inquiry/reconciliation cần quyền và guard riêng, không gọi charge test tùy tiện.

### 10.3. WebTestClient hoặc Java HttpClient kiểm qua server thật

**WebTestClient.bindToServer** có thể kiểm một REST API bất kể implementation Spring MVC hay WebFlux:

~~~java
WebTestClient remote = WebTestClient.bindToServer()
    .baseUrl(recoveredBaseUrl)   // URL canary/test environment
    .responseTimeout(Duration.ofSeconds(5))
    .build();

remote.get()
    .uri("/api/orders/{id}", knownSafeOrderId)
    .headers(h -> h.setBearerAuth(validTestAccessToken))
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(knownSafeOrderId);
~~~

Code là fragment cần URL/identity fixture và test dependencies; **validTestAccessToken phải là token thật của test identity provider** khi gọi qua HTTP socket. Cơ chế **mockJwt()** trong mock-bound test không phát hành access token thật cho server. Kiểm thêm cùng request từ tenant khác bị 403/404, missing token 401 và CORS headers khi frontend cần.

Để kiểm **timeout/503 của downstream**, dùng **WireMock/MockWebServer** cho inventory/payment hoặc fault injection trong môi trường cho phép; xác minh client có deadline, backoff/jitter, Retry-After và **không retry POST không idempotent**. Test rollback schema với release binary cũ trong staging, không chờ phát hiện ở production.

## 11. Gate nghiệm thu và mở traffic từng phần

Một đợt mở traffic nên có **canary**, khoảng quan sát và điểm dừng. Số phần trăm là minh họa, không phải công thức chung:

~~~text
0% write traffic: restore + verify data/ledger/dependencies
1% canary:        safe read + synthetic create in sandbox/approved scope
5% -> 25%:       verify JWT, HTTP contract, DB/queue lag, 5xx/p99
50% -> 100%:     confirm real outcome SLI, no new duplicate/lost intents
after reopen:    watch longer workflow deadlines and reconciliation
~~~

Đặc biệt với **region failover**, không mở writes ở hai region đồng thời nếu cả hai có thể tự xem mình là leader. Cần **fencing/leader election/quorum** và quy tắc nhất quán dữ liệu. Canary có thể **đọc** từ vùng vừa khôi phục trong khi đường ghi còn khóa; chỉ mở POST sau khi ledger/payment reconciliation đủ tin cậy.

### 11.1. Release gate có thể ký duyệt

| Gate | Pass khi | Fail/rollback khi |
|---|---|---|
| **G1 – Runtime** | Pods/probes ổn, edge route/TLS đúng | Restart loop, 502/503 tăng |
| **G2 – HTTP contract** | CRUD/202/error/headers/OpenAPI đúng | 201→200, thiếu Location, sai JSON |
| **G3 – Security** | JWT issuer/audience, tenant ACL, CORS/CSRF đạt | BOLA, token sai được chấp nhận |
| **G4 – Data** | Không mất/trùng business intents ngoài RPO; ledger/outbox đối soát | Missing payment receipt, double charge |
| **G5 – Dependencies** | DB lag/Redis/cache/broker/provider trong ngưỡng | Queue lag tăng liên tục, stale vượt bound |
| **G6 – SLI** | Availability, latency, terminal outcome ổn định | Error-budget burn vượt guardrail |
| **G7 – Observation** | Metrics, logs, traces, audit có coverage | Không đủ dữ liệu để phát hiện tái phát |

Với gate chưa đạt nhưng sản phẩm cần phục vụ khẩn cấp, có thể **mở một tập endpoint read-only ít rủi ro** nếu security/data constraints cho phép. Quyết định này phải được phê duyệt và truyền đạt như **partial service**, không gọi là khôi phục hoàn toàn.

### 11.2. SLI và error budget khi khôi phục

Đừng chỉ nhìn 5xx ở application: gateway có thể đang trả 504 hoặc CDN trả 200 từ bản cache cũ, khiến app metrics đẹp giả. Tập tín hiệu nên gồm:

- **Request availability:** eligible requests thực qua edge, status/error classification, 5xx/429 theo chính sách.
- **Latency:** tỷ lệ dưới ngưỡng và p95/p99; tách edge queueing với app/downstream.
- **Business completion:** unique accepted intents đạt terminal state trong deadline; không chỉ 201/202.
- **Correctness:** duplicate order/charge, reconciliation backlog, DB vs provider mismatch, cache stale vượt giới hạn.
- **Saturation:** DB connections, CPU/memory, queue lag, Redis misses, cache stampede, thread/event-loop backlog.
- **Telemetry coverage:** metric scrape gaps, time skew, dashboard stale, sampling config và audit event stream.

**Burn rate** so tỷ lệ sự kiện xấu với error-budget fraction của SLO. Ví dụ availability 99,9% có bad budget 0,1%; nếu cửa sổ ngắn có 1% bad, burn xấp xỉ **10×**, cần đối chiếu traffic volume, incident severity và chính sách alert. Không lấy trace mẫu ngẫu nhiên làm mẫu số SLO khi sampling có thiên lệch.

### 11.3. Điều kiện tạm dừng canary

Tạm dừng hoặc giảm traffic nếu **bất kỳ điều kiện cứng** nào xuất hiện: mất quyền tenant, double charge, sai schema gây dữ liệu không đọc được, split-brain, idempotency ledger mất, dependency có dấu hiệu lan tải không kiểm soát. Các vấn đề **không gây hỏng dữ liệu** như p95 cao hơn mục tiêu có thể xử lý theo ngưỡng canary và error budget đã thống nhất.

**Không chỉ đo tỷ lệ 200 sau canary**: với một endpoint GET nhiều traffic, nó có thể che mất POST checkout hiếm nhưng quan trọng. Theo dõi theo operation/tenant tier/region ở mức đủ phát hiện, nhưng tránh log/metric labels có độ phân tán quá lớn hoặc lộ thông tin khách hàng.

## 12. Mẫu runbook ngắn có thể thực thi

Runbook phải **có tham số môi trường**, người duyệt, nguồn metric và link dashboard thực trong hệ thống thật. Mẫu dưới đây minh họa các bước **không destructive**:

~~~text
INCIDENT ID:                 INC-2026-XYZ
SERVICE:                     orders-api
REGION / RELEASE:            <region> / <build-digest>
IMPACTED METHODS:            POST /api/orders, GET /api/operations/{id}
RECOVERY LEAD:               <on-call>
DATA RECONCILIATION OWNER:   <data-owner>
LAST KNOWN GOOD:             <build + schema + config + policy revision>
TARGET:                      RTO <agreed>; RPO per dataset <agreed>

1. Freeze further rollout, limit new side effects.
2. Capture edge/app metrics, config digest, DB/queue/outbox offsets.
3. Choose rollback/rollforward/restore; record approval and risk.
4. Verify DB and provider reconciliation; no new duplicate charges.
5. Verify security + HTTP/OpenAPI contract with safe fixtures.
6. Verify dependent services and caching/queue convergence.
7. Canary 1% -> 5% -> 25% -> full per approved thresholds.
8. Mark recovered only after G1-G7 PASS; monitor delayed outcomes.
9. Publish timeline, customer impact and follow-up owners.
~~~

**Không dán lệnh database destructive** vào runbook chung mà ai cũng có thể chạy. Những bước như promote replica, point-in-time restore, reset offset hoặc redrive DLQ cần procedure riêng có preflight, dry-run khi hỗ trợ, thao tác có kiểm soát và rollback/compensation plan.

### 12.1. Quy tắc đối với thông báo khách hàng

Thông báo nên phân biệt **request thất bại**, **request có kết quả chưa xác định** và **giao dịch đã được đối soát**. Nếu user thấy timeout khi đặt hàng, đừng yêu cầu họ “ấn lại để chắc chắn” khi chưa bảo đảm idempotency. Cung cấp **operation status / order lookup** hoặc hỗ trợ đối soát theo reference; không để khách tự tạo thêm payment vì hệ thống không xác định được outcome.

## 13. Diễn tập định kỳ và cải tiến thiết kế

Phục hồi an toàn cần kiểm thử **trước khi có sự cố**. Các bài diễn tập có phạm vi được phê duyệt:

| Diễn tập | Thao tác giả lập | Điều phải chứng minh |
|---|---|---|
| **Rollback schema-compatible** | Deploy bản lỗi rồi rollback binary | Bản cũ đọc schema/data trung gian đúng |
| **DB failover** | Cô lập leader thử nghiệm | Không split-brain, writes được fencing, read lag kiểm soát |
| **Redis outage** | Chậm/ngắt cache | Không stampede DB, dữ liệu đúng, degraded response |
| **JWKS rotation** | Đổi key signing trong test issuer | Key mới xác minh được, key cũ hết hạn đúng policy |
| **Broker/consumer lag** | Tạm ngắt consumer, redrive event | Không mất/trùng business effect, lag giảm về ngưỡng |
| **Gateway fault** | 503/504 hoặc đổi header CORS | HTTP contract tests phát hiện, client retry an toàn |
| **Payment unknown outcome** | Commit provider rồi bỏ response | Inquiry và key cố định ngăn double charge |
| **CDN stale** | Hoãn purge sau cập nhật | Không phục vụ dữ liệu sai quá bound, không lộ ACL |
| **Observability loss** | Ngắt metrics scrape tạm | No-data alert, không gán 100% availability |

Ghi **RTO thực tế, RPO quan sát, mất dữ liệu/side effects, time-to-detection, manual steps và lỗi runbook**. Một bài thử chỉ kiểm “pod quay lại Running” không đo được năng lực khôi phục hợp đồng/dữ liệu/phụ thuộc.

## 14. Bài tập thực hành và hướng dẫn đáp án

**Bài 1 — Pod xanh, checkout vẫn kẹt.** Sau rollback, liveness/readiness đều UP, POST trả 202 nhưng 30% operation PENDING quá 10 phút. Đã recovered chưa? **Đáp án:** Chưa. Cần business completion SLI, queue/outbox lag, worker và provider reconciliation; 202 chỉ là tiếp nhận.

**Bài 2 — RTO và RPO.** API ngừng 20 phút; DB được khôi phục từ snapshot cách sự cố 45 phút, trong khi đã có order committed trong khoảng ấy. Có đạt RTO 30 phút và RPO 0 không? **Đáp án:** Có thể đạt RTO nếu service thật sự phục vụ đầy đủ trong 20 phút, nhưng **không đạt RPO 0** nếu committed writes mất. Phải đối soát/replay từ logs/provider/outbox theo cơ chế an toàn.

**Bài 3 — Token sau failover.** JWT hợp lệ do issuer mới ký bị 401 tại một pod nhưng thành công ở pod khác. **Đáp án:** Kiểm JWKS cache/rotation, issuer/audience/time skew và cấu hình decoder từng pod; không tắt signature validation để tránh 401.

**Bài 4 — Timeout sau commit.** Java client mất response POST nhưng DB có order và provider đã thu tiền. Client muốn gửi POST với Idempotency-Key khác. **Đáp án:** Không. Dùng cùng key/intent theo contract, inquiry operation/provider receipt và đối soát; key mới có thể nhân đôi side effect.

**Bài 5 — Event replay.** Consumer nhận cùng event OrderCreated ba lần sau khi broker phục hồi. **Đáp án:** Consumer cần idempotent processing, unique event/business key và transaction; kiểm ledger/outbox/payment effect chỉ một lần.

**Bài 6 — 304 sau khi thu hồi quyền.** User từng xem order, bị thu hồi membership; GET If-None-Match vẫn nhận 304 từ cache. **Đáp án:** Sai về bảo mật. Kiểm auth/tenant ACL trước conditional response; invalidate hoặc bypass cache riêng tư, dùng no-store khi phù hợp.

**Bài 7 — Rollback code sau DB migration.** Phiên bản cũ đọc sai cột đã đổi kiểu. **Đáp án:** Không tiếp tục rollback mù; cần plan expand-contract, compatibility matrix, hoặc rollforward patch/restore được phê duyệt và test với dataset thực.

**Bài 8 — Canary metrics xanh giả.** App báo 99,99% request 200, nhưng edge 504 tăng và khách hàng mất đơn. **Đáp án:** App không thấy traffic chết ở gateway; đo tại edge và theo intent/business completion, kiểm instrumentation coverage và reconciliation.

**Bài 9 — Cache stampede.** Để chữa dữ liệu stale, xóa mọi Redis keys rồi mở 100% traffic; DB connection pool cạn. **Đáp án:** Cần namespace version/targeted purge, warm-up, bounded load, staged traffic và DB concurrency limiter; không flush toàn bộ không có kế hoạch.

**Bài 10 — Ưu tiên gate.** Smoke GET trả 200, contract và JWT đúng, nhưng còn 17 payment receipts chưa gắn order. Có mở checkout 100% không? **Đáp án:** Không nếu reconciliation là gate bắt buộc. Phải quyết định scope, điều tra unknown outcomes và bảo vệ không double charge trước khi mở writes.

## 15. Checklist đóng sự cố

- [ ] Xác định incident scope, impact, RTO/RPO theo dữ liệu và thời điểm last-known-good?
- [ ] Có quyết định rollback/rollforward/restore có người duyệt, mốc và điều kiện dừng?
- [ ] Bản code, schema, config, auth policy, event schema tương thích với nhau?
- [ ] Source of truth được kiểm integrity; DB replica lag/fencing/transaction state an toàn?
- [ ] Idempotency ledger, outbox, broker offsets, DLQ và provider receipts đã đối soát?
- [ ] Không còn side effect trùng, missing committed order hoặc job bị kẹt ngoài ngưỡng?
- [ ] HTTP URI/method/status/content/schema, OpenAPI, ETag/304, 409/412 và 429/503 đạt?
- [ ] JWT issuer/audience/JWKS, scope/tenant/owner, CORS/CSRF và audit đúng policy?
- [ ] Cache Redis/CDN/browser, negative caching và data generation không phục vụ sai dữ liệu?
- [ ] Probes, gateway, database, message broker và các downstream chính ổn định?
- [ ] Smoke/contract, database integration và synthetic tests đạt; không chỉ mock controller?
- [ ] Canary có theo dõi 5xx/p95/p99/business outcomes, giới hạn tải và auto-stop rule?
- [ ] Metrics/logs/traces/audit còn coverage, không lộ tokens/PII trong báo cáo?
- [ ] Trạng thái gửi khách hàng phân biệt request thất bại và kết quả giao dịch chưa xác định?
- [ ] Có báo cáo timeline, nguyên nhân giả thuyết, bài diễn tập và action items có owner?

**Kết luận:** Khôi phục REST API sau sự cố là **phục hồi một hệ thống hợp đồng và trạng thái**, không đơn giản restart service hoặc rollback image. HTTP/OpenAPI phải còn đúng với client; dữ liệu, idempotency và workflow phải được đối soát với nguồn bền vững; auth, cache và downstream phải được kiểm chứng. Chỉ khi các cổng **runtime, contract, security, data, dependencies, SLI và observability** đều đạt, việc mở lại traffic mới là quyết định có căn cứ.
