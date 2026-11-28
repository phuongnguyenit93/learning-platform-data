# Metric replay

**Metric replay** là nhóm chỉ số giúp quan sát khả năng phát hiện, từ chối và vận hành cơ chế **anti-replay** trong xác thực HTTP request bằng HMAC. Metric tốt trả lời được: một request đã có HMAC hợp lệ có bị gửi lại bằng cùng nonce hay không, replay authority có hoạt động đáng tin hay không, mức lỗi phân bố giữa các endpoint/client scope ra sao, và hệ thống có vô tình **cho qua request khi Redis/KMS/registry gặp lỗi** hay không.

Bài thuộc chương **Monitoring** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun thiết kế xác thực HTTP request bằng **shared-secret HMAC** và canonical request gồm method, URI, signed header hoặc body theo hợp đồng ký. Toàn hệ thống cần kiểm chữ ký, timestamp/nonce chống replay, key rotation, gateway/proxy, và giữ ranh giới giữa **authentication** với **authorization**.

> **Phân biệt cốt lõi:** `REPLAY` là kết luận có căn cứ từ một **atomic nonce admission** sau khi HMAC và freshness đã được xác minh; `UNKNOWN` là không có kết luận đáng tin từ replay store, **không được coi là NEW hay REPLAY**. Một `REPLAY` có thể là **retry hợp pháp**, bản sao request bị đánh cắp hoặc lỗi điều phối, không tự động chứng minh attacker đã compromise shared secret. Metric không thay việc từ chối request theo security policy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **replay attack**, signed nonce, timestamp freshness và replay authority trong HMAC.
2. Phân biệt `NEW`, `REPLAY`, `UNKNOWN`, malformed request, invalid MAC và stale timestamp.
3. Xác định **ranh giới tăng metric**: chỉ đếm replay khi request đủ điều kiện và nonce store trả kết luận đáng tin.
4. Đề xuất metric counters, timer, gauge và event/log/trace tương ứng.
5. Định nghĩa **denominator** đúng cho replay rate, hiểu tại sao `replay_rate` khác `authentication_failure_rate`.
6. Thiết kế metric names/labels dạng Micrometer/Prometheus mà không tạo **high cardinality** hoặc rò key IDs, nonce, signature.
7. Sử dụng `Counter`, `Timer`, `MeterRegistry` trong Java 17/Micrometer theo lifecycle đơn giản, testable.
8. Giải thích `rate()`, `increase()`, histogram/latency, counter resets và metric availability.
9. Viết PromQL cho replay volume, share of replay, store UNKNOWN, store latency và SLO.
10. Thiết lập cảnh báo có **volume gate**, tránh cảnh báo giả do traffic thấp, scraping lỗi hoặc retry deploy.
11. Kiểm thử concurrent requests qua nhiều verifier nodes, Redis atomic claim, TTL, key rotation và failover.
12. Phân biệt **security evidence**, diagnostic logs và business idempotency; thực hành incident runbook không làm lộ secret.

## 2. Vì sao phải giám sát replay trong HMAC?

Một signature HMAC chứng minh request bytes đã được ký bằng secret tương ứng, nhưng **không tự ngăn request đó bị gửi lại nguyên vẹn**. Nếu attacker thu được một HTTP request đã ký, họ có thể gửi lại trong khoảng timestamp còn hợp lệ.

Ví dụ:

~~~http
POST /signed-api/orders HTTP/1.1
Host: orders.example.test
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 0123456789abcdef0123456789abcdef
X-Signature: <Base64URL-HMAC-tag>
Content-Type: application/json

{"orderId":"O42","amount":250000}
~~~

Client ký method, URI, mandatory signed headers và digest của body theo canonical contract. Khi request đến:

1. Server parse metadata một cách strict.
2. Tra **exact key ID** trong trusted credential registry.
3. Kiểm key status, audience, validity và algorithm.
4. Dựng canonical bytes từ HTTP request thật.
5. Tính expected full HMAC tag và so với tag client.
6. Kiểm signed timestamp theo server clock.
7. Thử **atomic claim** nonce trong shared replay store.
8. Chỉ khi claim trả `NEW` mới tạo trusted principal và đi tiếp authorization.
9. Nếu claim trả `REPLAY`, từ chối request thứ hai.
10. Nếu claim trả `UNKNOWN`/error, **fail closed**; không đoán nó mới.

Metric giúp biết các bước 7–10 đang hoạt động như thiết kế. Không có metric, hệ thống có thể âm thầm tăng 401 do gateway retry, replay store bị partition hoặc TTL cấu hình sai mà đội vận hành không phân biệt được.

### 2.1. Metric không được trở thành đường xác thực thứ hai

**Sai:** nếu `replay_total` thấp thì bỏ kiểm nonce để giảm latency. **Đúng:** nonce admission vẫn bắt buộc; metrics chỉ ghi lại kết quả **đã xảy ra**. Không xây một “risk score” dựa trên metrics rồi accept nonce khi Redis timeout, trừ khi toàn security model định nghĩa cơ chế khác có guarantee tương đương và được đánh giá độc lập.

### 2.2. Một lần claim NEW không có nghĩa business thành công

Request có thể được authenticated với nonce `NEW`, nhưng sau đó:

- Principal không có quyền tenant/resource → `403`.
- Validation JSON thất bại → `400`.
- Order ID đã tồn tại → business idempotency từ chối duplicate.
- Handler/DB lỗi sau admission → `5xx`.
- Client mất kết nối và không thấy response.

Bởi vậy metric `nonce_claim_new` không phải số order tạo thành công; không dùng nó làm business success rate.

## 3. State machine của request và điểm tăng replay metric

~~~mermaid
flowchart TD
    A[HTTP signed request] --> B{Parse/canonical contract valid?}
    B -- No --> P[Parse failure metric]
    B -- Yes --> C{Exact key allowed?}
    C -- No or unavailable --> K[Key policy/lookup metric]
    C -- Yes --> D{Full HMAC tag matches?}
    D -- No --> M[Bad MAC metric]
    D -- Yes --> E{Signed timestamp fresh?}
    E -- No --> T[Stale timestamp metric]
    E -- Yes --> F[Atomic nonce claim on shared authority]
    F --> G{Result?}
    G -- NEW --> H[Record nonce NEW]
    G -- REPLAY --> I[Record replay rejection]
    G -- UNKNOWN or error --> J[Record store uncertainty and fail closed]
    H --> L[Trusted authenticated principal]
    L --> Z[Authorization and business policy]
~~~

**Bất biến quan trọng:**

- Một request với **MAC sai** không được claim nonce và **không được đếm là replay**.
- Một timestamp **ngoài cửa sổ** không được làm phát sinh replay-claim traffic, trừ khi protocol có thứ tự khác được thiết kế/công bố rõ.
- Chỉ increment `REPLAY` khi shared authority có kết luận **duplicate** theo namespace/TTL.
- Store outage, timeout, ambiguous acknowledgement, `Mono.empty()` hoặc unexpected null là `UNKNOWN`/infrastructure failure, không phải `REPLAY`.
- `NEW` chỉ mô tả **nonce admission accepted**, không mô tả authorization/business outcome.
- Counter/Timer instrumentation **không được ném lỗi khiến request fail open**. Nếu metrics backend hỏng, xử lý bảo mật vẫn dựa trên verifier và nonce authority.

### 3.1. Các biến khác nhau dễ bị nhầm

| Sự kiện | Ý nghĩa | Đếm replay? |
| --- | --- | --- |
| Missing nonce | Thiếu mandatory signed field | Không |
| Malformed nonce | Nonce sai grammar/entropy policy | Không |
| HMAC sai | Không có identity proof | Không |
| Key revoked | Credential policy deny | Không |
| Signed timestamp stale | Timestamp ngoài accepted window | Không |
| Nonce `NEW` | Claim thành công lần đầu trong namespace còn lưu | Không, đếm `new` |
| Nonce `REPLAY` | Atomic duplicate đã được xác định | Có |
| Nonce `UNKNOWN` | Không xác định được claim outcome | Không, đếm `unknown` |
| Valid HMAC + tenant denied | Authorization deny sau authentication | Không, trừ khi nonce là REPLAY |
| Business duplicate operation ID | Idempotency domain | Không tự động |
| Gateway retry cùng signed nonce | Request mới có thể được phát hiện là replay | Có nếu authority trả REPLAY |
| Retry bằng nonce mới | Một HMAC admission mới | Không nếu nonce NEW, nhưng business idempotency vẫn cần |

## 4. Thế nào là một “replay attempt”?

Trong vận hành, nên định nghĩa:

> **Observed replay event** = một HMAC request thỏa exact-key, MAC và timestamp freshness, nhưng **atomic nonce claim** trong trust namespace trả `REPLAY`.

Đây là định nghĩa **quan sát được**. Nó không chứng minh động cơ xấu. Replay có thể phát sinh từ:

- Gateway tự retry request sau timeout.
- Client SDK retry nguyên signed headers, signature và nonce.
- Service mesh/load balancer gửi duplicate request.
- Attacker chụp được một signed request và gửi lại.
- Client bug dùng lại nonce với một body/method khác (nếu nonce namespace theo credential); request vẫn có MAC hợp lệ nếu client biết secret.
- Các luồng retry đi qua nhiều pods hoặc regions với shared nonce authority.

### 4.1. Đừng tuyên bố metric cho biết mọi replay đã bị ngăn

`replay_detected_total` chỉ đếm **replay được authority nhận ra**. Nếu một vùng mất dữ liệu nonce do Redis failover hoặc replica lag, hệ thống có thể nhận cùng nonce như `NEW` hai lần mà metric `REPLAY` không tăng. Đó là **detection gap** và cần concurrency/failover tests, audit hoặc mô hình consistency mạnh hơn để đánh giá; không thể suy chỉ từ counter “replay thấp”.

### 4.2. Event 401 không đồng nghĩa replay

401 cũng có thể do key ID unknown, bad MAC, stale timestamp hoặc key revoked. Nếu dùng một metric `http_server_requests_seconds_count{status="401"}` để suy replay, kết luận sẽ sai. Hãy instrument **nonce decision** với outcome rõ, và giữ HTTP result metrics như nhóm riêng.

## 5. Công thức timestamp freshness, TTL và metric liên quan

Giả sử request ký timestamp `t_s`, thời gian server hiện tại `t_now`:

\[
t_{\mathrm{now}}-A \le t_s \le t_{\mathrm{now}}+F
\]

Trong đó:

- `A` = maximum past age, ví dụ 300 giây.
- `F` = maximum future clock skew, ví dụ 30 giây.
- Signed timestamp và nonce **phải nằm trong canonical bytes**.
- Nonce phải đủ khó trùng và có độ dài/grammar theo contract (ví dụ 16 random bytes encode 32 lowercase hexadecimal).

Một bound retention đơn giản, bảo thủ khi lưu nonce từ thời điểm claim:

\[
TTL_{\mathrm{nonce}}\ge A+F+M.
\]

Với `A=300s`, `F=30s`, `M=30s` ⇒ chọn TTL `360s` trong ví dụ. Việc đồng thời có future skew nghĩa là timestamp ký hơi “trong tương lai” có thể còn fresh lâu hơn 300 giây tính từ lần nhận đầu tiên.

### 5.1. Ví dụ replay gap nếu TTL thiếu

~~~text
Policy: A=300s, F=30s
TTL configured: 300s  (KHÔNG đủ cho mọi case)
Request timestamp: server now + 30s at initial claim
First nonce claim: T0, NEW
Redis expires nonce: T0 + 300s
Timestamp can stay fresh until: T0 + 330s
Retry at T0 + 310s:
  timestamp still fresh
  nonce key already gone
  => wrong second NEW is possible
~~~

Metric `REPLAY` có thể **không tăng** trong gap này. Vì thế bên cạnh replay ratio cần giám sát cấu hình TTL/window, verified redis expiry behavior và kiểm thử bound; không dùng metric replay “thấp” làm chứng cứ TTL đủ.

### 5.2. Cần phân biệt client clock skew và replay

Một request timestamp quá cũ bị freshness gate reject **trước nonce claim**. Nó phải tăng metric `timestamp_stale` thay vì `replay`. Nếu đồng hồ client lệch, stale failures có thể tăng mà replay count không đổi. Metrically tách lỗi clock giúp hỗ trợ đối tác chính xác, tránh đề nghị bỏ anti-replay.

### 5.3. Không gắn timestamp hoặc nonce vào metric labels

Giá trị timestamp và nonce thay đổi theo mỗi request, tạo **vô hạn series** và có thể giúp tái dựng request patterns; tuyệt đối không đưa raw `nonce`, `X-Signature` hoặc signed timestamp vào label. Nếu cần forensic trace, dùng server-generated correlation ID trong secure logs với retention/ACL, không phải label Prometheus.

## 6. Thiết kế bộ metrics: Counter, Timer, Gauge, logs và traces

Không có một loại metric nào trả lời mọi câu hỏi. Để quan sát **Metric replay**, cần đo số quyết định, độ trễ authority, lỗi hạ tầng và outcome HTTP:

| Tên Micrometer gợi ý | Loại | Tags được kiểm soát | Thời điểm ghi |
| --- | --- | --- | --- |
| `hmac.replay.claims` | Counter | `outcome=new|replay|unknown`, `route` | Một invocation đến shared replay authority đã được kết luận hoặc thất bại |
| `hmac.replay.claim.duration` | Timer | `outcome`, `route` | Độ trễ gọi authority từ bắt đầu tới return/throw |
| `hmac.replay.store.errors` | Counter | `reason=timeout|connection|uncertain|other` | Dependency lỗi, **không** phải duplicate đã xác định |
| `hmac.replay.inflight` | Gauge | Bounded `route` nếu cần | Số claims đang chờ ở thời điểm scrape |
| `hmac.auth.rejects` | Counter | `stage=syntax|key|mac|freshness|replay|dependency|authorization` | Một request bị từ chối theo stage đã định nghĩa |
| `hmac.auth.admissions` | Counter | Bounded `route` | Authentication/admission thành công, **không** phải business success |
| `hmac.timestamp.rejects` | Counter | `reason=old|future|malformed` | Timestamp không đạt policy trước nonce claim |
| `hmac.replay.config.window` | Gauge/metadata | `kind=past|future|ttl` | Giá trị security policy theo giây từ trusted config |
| Framework HTTP server requests | Timer/Counter | Bounded URI template, status | HTTP outcome cuối, **không thay replay decision** |

Tên trên là **observability contract của ví dụ**. Micrometer Counter `hmac.replay.claims` thường được export sang Prometheus thành `hmac_replay_claims_total`, còn Timer thường có `_seconds_count`/`_seconds_sum`; cần kiểm output thực tế theo phiên bản/registry.

### 6.1. Ba outcome của claim loại trừ nhau

~~~text
NEW      = atomic create-if-absent thành công
REPLAY   = atomic create-if-absent xác nhận nonce đã tồn tại
UNKNOWN  = timeout, connection error, ambiguous ack, empty/null
~~~

Trong **cùng một tập requests thực sự tới authority**, nếu mỗi invocation có đúng một outcome event:

\[
N_{\mathrm{claim\ attempts}} =
N_{\mathrm{new}} + N_{\mathrm{replay}} + N_{\mathrm{unknown}}.
\]

Không áp dụng đẳng thức này cho **tổng HTTP requests**: nhiều requests bị chặn trước nonce store vì key sai, MAC sai hoặc timestamp stale. `UNKNOWN` là không biết kết quả authoritative, **không** phải replay được xác định; phải fail closed.

### 6.2. Thời gian claim, latency và saturations

`claim.duration` đo từ trước call storage tới khi kết thúc/lỗi. Giúp phân biệt:
- Replay tăng, store vẫn nhanh → tăng duplicate HTTP requests.
- Unknown tăng cùng latency → replay store timeout/partition.
- NEW tăng, latency tăng → load cao hoặc Redis hot partition.
- HTTP latency tăng nhưng claim duration ổn → registry/body canonicalization/business.

`Gauge hmac.replay.inflight` cho biết số calls đang chờ, nhưng scrape có thể bỏ lỡ spike ngắn. Kết hợp Timer, throughput và queue saturation; không bật percentile histograms bừa bãi trên mọi tổ hợp labels vì chi phí time series.

### 6.3. Counter cumulative và lifecycle

Counter tăng +1, không decrement. Sau pod restart counter có thể reset; PromQL `rate()`/`increase()` xử lý reset khi scrape đủ. Không lấy `counter.count()` trên một pod làm tổng lịch sử cluster. Retry đến pod khác được tính thành request observation khác, không nhất thiết business operation mới.

### 6.4. Logs và traces giúp điều tra

Structured audit log có thể có server-generated `trace_id`, route family, trusted credential version sau auth, `decision`, verifier node và latency. Span `nonce.claim` chỉ nên ghi bounded outcome/error type.

**Không** log raw secret, signature, nonce, sensitive body hoặc full replayable signed request. Counters cốt lõi không nên sample nếu mục tiêu là volume chính xác; có thể sample logs/traces theo chính sách.

## 7. Tách tầng đo: không gộp sai denominator

Một signed HTTP request đi qua:

~~~text
HTTP ingress
  -> strict parser/key-id lookup
  -> HMAC canonical verification
  -> signed timestamp freshness
  -> atomic nonce claim
  -> authenticated principal
  -> tenant/action/resource authorization
  -> business operation
~~~

| Tầng | Đơn vị quan sát | Không được suy diễn |
| --- | --- | --- |
| HTTP framework | Một response/request | Không có nghĩa nonce đã được claim |
| Parser | Syntax reject | Không có nghĩa replay |
| HMAC verifier | Bad MAC | Không claim nonce hoặc replay counter |
| Freshness | Too old/future | Không phải duplicate đã xác định |
| Nonce NEW | Một accepted claim | Không phải HTTP 2xx hay order success |
| Nonce REPLAY | Một duplicate decision | Không chứng minh actor ác ý |
| Nonce UNKNOWN | Không có kết luận authority | Không được đổi thành REPLAY |
| Authentication success | Một trusted principal admission | Còn authorization |
| Authorization deny | Thiếu quyền tenant/action | Không phải lỗi anti-replay |
| Domain idempotency duplicate | Operation ID đã xử lý | Không nhất thiết replay nonce |

### 7.1. Một metric hmac.replay.claims không phải tổng request

Nếu có 1.000 HTTP requests:
- 150 malformed/key/mismatch/stale,
- 800 nonce NEW,
- 30 nonce REPLAY,
- 20 nonce UNKNOWN,

thì claim total = 850, không phải 1.000. Replay **share trong các claim có kết luận** là 30/(800+30), không phải 30/1000. Cả hai ratios có thể dùng cho mục tiêu khác nhưng phải ghi tên rõ.

### 7.2. Phân biệt retry HTTP và idempotency business

Client có thể bị timeout sau một order thành công. Retry **cùng nonce** → nếu store còn record, `REPLAY`; retry với **nonce mới** → `NEW`, nhưng business operationId vẫn có thể duplicate. Đừng gọi `orders_idempotency_duplicate_total` là HMAC replay metric.

### 7.3. Không đo replay bằng mọi HTTP 401

`http_server_requests_seconds_count{status="401"}` bao gồm bad MAC, unknown key, stale timestamp, revoked key và replay. Muốn biết anti-replay gate, phải đo **claim result**, không suy từ response code.

## 8. Metric labels: cardinality và trust boundaries

Prometheus tạo một series cho mỗi metric name + tổ hợp labels. Nếu có 8 route families × 3 outcomes × 12 pods ⇒ khoảng 288 series trước khi tính histogram buckets. Thêm 10.000 client IDs thì series có thể tăng tới hàng triệu; label per nonce gần như tăng theo mỗi request.

### 8.1. Labels chấp nhận được

| Label | Ví dụ | Nguồn và giới hạn |
| --- | --- | --- |
| `outcome` | `new`, `replay`, `unknown` | Fixed enum |
| `route` | `orders_write`, `signed_webhook`, `other` | Server route registry, không raw URI |
| `reason` | `timeout`, `connection`, `uncertain`, `other` | Fixed enum, không exception.message |
| `audience_group` | `orders`, `billing` | Trusted config, bounded |
| `region`, `environment` | `ap-southeast-1`, `prod` | Infrastructure labels, không caller |
| `instance`/`pod` | Scrape target | Infrastructure identity, không per-request |
| `policy_cohort` | Stable bounded release group | Không raw database revision mỗi lần |

### 8.2. Labels tuyệt đối tránh

- `nonce`, `timestamp`, `signature`, `body_digest`, full canonical request.
- Raw `X-Key-Id`, đặc biệt IDs không tồn tại do attacker tự sinh.
- Raw `tenantId`/`clientId` nếu lượng giá trị lớn/nhạy cảm.
- Raw path/query có order IDs hoặc biến động vô hạn.
- `traceId`/`spanId`, exception.message, Redis nonce key.
- Caller-provided `X-Role`, `X-Partner` hoặc source IP như unbounded label.

### 8.3. Route phải được chuẩn hóa ở server

`POST /v1/orders/9232` và `POST /v1/orders/9233` đều được gắn route family `orders_write`, **không** lấy `request.getURI().toString()`. Cần một allowlist/enum. Trước khi authenticate, caller có thể tự khai `X-Tenant-Id`; không gắn nó làm một trusted label.

Nếu điều tra một client cụ thể, dùng secure audit logs/correlation ID và policy retention, thay vì tạo metric public per-client. Ngay cả after-auth per-tenant labels vẫn có cardinality/privacy cost.

## 9. Metric contract cụ thể cho Micrometer và Prometheus

Định nghĩa chuẩn cho ví dụ:

~~~text
Micrometer source                        Prometheus name (typical)
hmac.replay.claims         Counter       hmac_replay_claims_total
hmac.replay.claim.duration Timer         hmac_replay_claim_duration_seconds_count
                                        hmac_replay_claim_duration_seconds_sum
hmac.replay.inflight       Gauge         hmac_replay_inflight
hmac.auth.rejects          Counter       hmac_auth_rejects_total
~~~

**Chú ý:** Nếu Micrometer/registry tự thêm hậu tố `_total`, không tự thêm vào tên nguồn Counter để tránh double suffix. `Timer` không tạo histogram buckets trừ khi cấu hình tương ứng; chỉ dùng PromQL `_bucket` khi hệ thống thực sự export buckets.

### 9.1. Ý nghĩa tags phải được chốt trước dashboard

~~~text
metric: hmac.replay.claims
tag route: orders_write | signed_webhook | other
tag outcome: new | replay | unknown

metric: hmac.replay.claim.duration
tag route: same bounded set
tag outcome: same bounded set
unit: seconds when Prometheus exports

metric: hmac.replay.inflight
tag: none (single aggregate gauge in demo)
unit: pending claims
~~~

Bản thân label `route=other` nên được kiểm soát để không che một HTTP endpoint mới đã vô tình bỏ matcher. Khi onboarding route mới, cập nhật route registry, tests và dashboards.

### 9.2. Counter increments một lần theo claim invocation

Với một replay-store operation, instrumentation phải phát tối đa **một** trong các events:

~~~text
event route=orders_write outcome=new
event route=orders_write outcome=replay
event route=orders_write outcome=unknown
~~~

Nếu helper được dùng hai lần (một ở filter, một ở Redis adapter) cho cùng storage call, sẽ đếm trùng. Chọn **một owner** của replay claim metrics, ví dụ adapter quanh nonce store hoặc service orchestration; document ownership và test.

### 9.3. Timestamp freshness phải ghi riêng

Nếu timestamp quá cũ, nonce store không được gọi. Khi đó `hmac.timestamp.rejects{reason="old"}` tăng nhưng `hmac.replay.claims` không tăng. Nếu client đồng hồ lệch, sẽ có freshness spike mà replay ratio bình thường; không nhầm clock drift thành attacker.

### 9.4. Denominator phải rõ khi vẽ phần trăm

Có ít nhất ba tỷ lệ khác nhau:

\[
\text{Observed replay share} =
\frac{N_{\mathrm{replay}}}
 {N_{\mathrm{new}}+N_{\mathrm{replay}}}.
\]

\[
\text{Uncertain claim share} =
\frac{N_{\mathrm{unknown}}}
 {N_{\mathrm{new}}+N_{\mathrm{replay}}+N_{\mathrm{unknown}}}.
\]

\[
\text{Observed replay per HTTP request} =
\frac{N_{\mathrm{replay}}}{N_{\mathrm{HTTP\ requests}}}.
\]

Không dùng chung nhãn “replay rate” cho ba phép tính; phải chỉ rõ **ratio hay events/second** và sampling window. `NEW` cũng có thể tăng do signed retries **với nonce mới**, nên replay share không phản ánh toàn bộ duplicate business operations.

## 10. Java 17 + Micrometer: replay metric recorder

Dưới đây là **một recorder tự chứa về mặt API**, giả định project đã có Micrometer core và dependency injection tương ứng. Một số loại được khai báo trong cùng đoạn mã để làm rõ contract; khi dùng thật hãy tách public types thành files.

### 10.1. Tập nhãn cố định bằng enum

~~~java
public enum HmacRouteGroupV1 {
    ORDERS_WRITE("orders_write"),
    SIGNED_WEBHOOK("signed_webhook"),
    OTHER("other");

    private final String label;

    HmacRouteGroupV1(String label) {
        this.label = label;
    }

    public String label() { return label; }
}
~~~

~~~java
public enum NonceClaimOutcomeV1 {
    NEW("new"),
    REPLAY("replay"),
    UNKNOWN("unknown");

    private final String label;

    NonceClaimOutcomeV1(String label) {
        this.label = label;
    }

    public String label() { return label; }
}
~~~

Cả hai enums do server định nghĩa, không parse raw key ID, nonce hoặc caller-supplied URL thành tags.

### 10.2. Recorder pre-register counters và timers

~~~java
import java.time.Duration;
import java.util.EnumMap;
import java.util.concurrent.atomic.AtomicInteger;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class HmacReplayMetricsV1 {
    private final EnumMap<HmacRouteGroupV1,
            EnumMap<NonceClaimOutcomeV1, Counter>> counters =
                    new EnumMap<>(HmacRouteGroupV1.class);

    private final EnumMap<HmacRouteGroupV1,
            EnumMap<NonceClaimOutcomeV1, Timer>> timers =
                    new EnumMap<>(HmacRouteGroupV1.class);

    private final AtomicInteger inFlight = new AtomicInteger();

    public HmacReplayMetricsV1(MeterRegistry registry) {
        for (HmacRouteGroupV1 route : HmacRouteGroupV1.values()) {
            var routeCounters =
                    new EnumMap<NonceClaimOutcomeV1, Counter>(
                            NonceClaimOutcomeV1.class);
            var routeTimers =
                    new EnumMap<NonceClaimOutcomeV1, Timer>(
                            NonceClaimOutcomeV1.class);

            for (NonceClaimOutcomeV1 outcome
                    : NonceClaimOutcomeV1.values()) {

                Counter counter = Counter.builder(
                            "hmac.replay.claims")
                        .description(
                            "HMAC nonce authority decisions")
                        .tag("route", route.label())
                        .tag("outcome", outcome.label())
                        .register(registry);

                Timer timer = Timer.builder(
                            "hmac.replay.claim.duration")
                        .description(
                            "Latency of an HMAC nonce store claim")
                        .tag("route", route.label())
                        .tag("outcome", outcome.label())
                        .register(registry);

                routeCounters.put(outcome, counter);
                routeTimers.put(outcome, timer);
            }

            counters.put(route, routeCounters);
            timers.put(route, routeTimers);
        }

        // Keep a strong reference to inFlight for gauge lifetime.
        Gauge.builder("hmac.replay.inflight",
                    inFlight, AtomicInteger::get)
                .description("Pending HMAC nonce claims")
                .register(registry);
    }

    public void beginClaim() {
        inFlight.incrementAndGet();
    }

    public void endClaim() {
        inFlight.decrementAndGet();
    }

    public void record(
            HmacRouteGroupV1 route,
            NonceClaimOutcomeV1 outcome,
            Duration elapsed) {

        counters.get(route).get(outcome).increment();
        timers.get(route).get(outcome).record(elapsed);
    }
}
~~~

**Vì sao pre-register?** Có đúng `3 route groups × 3 outcomes = 9` Counter series và 9 Timer tag sets cho demo, không tạo meter mới theo key ID hay nonce từ request. `EnumMap` truy cập nhanh và labels được kiểm soát.

### 10.3. Đồng hồ của Timer không phải client-signed timestamp

Dùng `System.nanoTime()` để đo **elapsed duration**, không dùng `Instant.now()` rồi trừ signed timestamp client: client timestamp là input chưa xác minh trước MAC và chịu clock skew. `System.nanoTime` thích hợp cho duration trong cùng process.

### 10.4. Gauge inFlight cần finally

Nếu nonce store ném exception, counter inFlight phải giảm trong `finally`. Không giảm gauge trước khi operation kết thúc, không increment + decrement ở nơi khác khiến gauge âm. Giá trị là **gauge của instance hiện tại**; Prometheus có thể aggregate qua pods.

### 10.5. Instrumentation phải không đổi quyết định bảo mật

Nếu metrics registry đang gặp lỗi, không được `return NEW` hoặc bỏ qua verifier để tiếp tục. Có thể thiết kế `safeRecord` bắt riêng nonfatal telemetry exception, báo qua fallback diagnostic logger với rate limit, còn nonce decision vẫn là kết quả từ authority. **Không** nuốt exception từ nonce store chung với exception của metric recorder.

## 11. Java 17: instrument replay store tại đúng boundary

Một interface cô lập shared nonce authority:

~~~java
import java.time.Duration;

public interface AtomicNonceStoreV1 {
    enum Claim { NEW, REPLAY, UNKNOWN }

    Claim claimOnce(String nonceStoreKey, Duration ttl);
}
~~~

Tại production, implementation phải dùng một **atomic create-if-absent + expiry**, chẳng hạn Redis `SET key value NX EX ttl`. Không dùng `GET` rồi `SET` riêng, và không reset TTL khi request lặp lại.

### 11.1. ReplayClaimObserverV1

~~~java
import java.time.Duration;
import java.util.Objects;

public final class ReplayClaimObserverV1 {
    private final AtomicNonceStoreV1 authority;
    private final HmacReplayMetricsV1 metrics;

    public ReplayClaimObserverV1(
            AtomicNonceStoreV1 authority,
            HmacReplayMetricsV1 metrics) {
        this.authority = Objects.requireNonNull(authority);
        this.metrics = Objects.requireNonNull(metrics);
    }

    public AtomicNonceStoreV1.Claim claimOnce(
            HmacRouteGroupV1 route,
            String trustedNonceStoreKey,
            Duration ttl) {

        long startedNanos = System.nanoTime();
        NonceClaimOutcomeV1 recorded =
                NonceClaimOutcomeV1.UNKNOWN;

        metrics.beginClaim();
        try {
            AtomicNonceStoreV1.Claim result =
                    authority.claimOnce(trustedNonceStoreKey, ttl);

            if (result == AtomicNonceStoreV1.Claim.NEW) {
                recorded = NonceClaimOutcomeV1.NEW;
            } else if (result == AtomicNonceStoreV1.Claim.REPLAY) {
                recorded = NonceClaimOutcomeV1.REPLAY;
            }
            // null/UNKNOWN remain UNKNOWN. The caller MUST fail closed.
            return result == null
                    ? AtomicNonceStoreV1.Claim.UNKNOWN
                    : result;

        } finally {
            metrics.endClaim();

            long elapsed = System.nanoTime() - startedNanos;
            Duration duration = Duration.ofNanos(
                    Math.max(elapsed, 0L));

            // A local telemetry error must never rewrite
            // the security decision. Production fallback logs
            // need rate limiting and no secret/nonce disclosure.
            try {
                metrics.record(route, recorded, duration);
            } catch (RuntimeException telemetryUnavailable) {
                // Do not return NEW or call the business handler.
                // Report bounded telemetry failure separately.
            }
        }
    }
}
~~~

Một lần call `authority.claimOnce` → một `outcome` metric (nếu monitoring không mất event). Nếu authority ném RuntimeException, `finally` ghi `UNKNOWN` rồi **exception tiếp tục propagate**, không bị biến thành `NEW`. `metrics.beginClaim()`/`endClaim()` chỉ đo inflight; không phải security state.

**Lưu ý nâng cao:** Ví dụ bắt nonfatal metrics failure quanh `record`; trong production nên có telemetry-failure indicator phù hợp và kiểm cách runtime xử lý unexpected fatal errors. Nếu `beginClaim` đã lỗi trước khi vào try, chưa có store call; đó là instrumentation malfunction và cần test riêng. Có thể bọc cả lifecycle vào một adapter đã được harden khi dùng production.

### 11.2. Nơi gọi observer

~~~java
// Chỉ sau khi đã kiểm:
// 1) HTTP metadata/canonical request hợp lệ
// 2) exact key record ACTIVE, đúng audience
// 3) full HMAC tag khớp
// 4) signed timestamp fresh
AtomicNonceStoreV1.Claim claim = observer.claimOnce(
        HmacRouteGroupV1.ORDERS_WRITE,
        trustedReplayKey,
        Duration.ofSeconds(360));

switch (claim) {
    case NEW -> {
        // Create trusted Authentication then authorize.
    }
    case REPLAY -> throw new SecurityException(
            "Signed request replay");
    case UNKNOWN -> throw new IllegalStateException(
            "Replay authority uncertain: deny request");
}
~~~

Code `switch` là **minh họa orchestration**, phải gắn vào verifier/Spring Security failure mapping đúng contract. `trustedReplayKey` được tạo từ trusted audience, exact key ID và **signed nonce**, không phải raw caller tenant ID.

### 11.3. Counter không nên ở controller

Nếu chỉ tăng `replay` trong MVC/WebFlux controller, request bị anti-replay filter từ chối **trước controller** sẽ không bao giờ được đếm. Đặt recorder ngay tại replay claim decision, tách khỏi business endpoint. Authorization fail sau nonce NEW vẫn không làm `NEW` biến mất.

## 12. PromQL: đọc volume, replay share và store uncertainty

Các ví dụ giả định Prometheus nhìn thấy metric `hmac_replay_claims_total` với labels `route` và `outcome`. Trước khi dùng, kiểm tên/labels xuất thực tế từ `/actuator/prometheus` (nếu actuator endpoint đã được bảo vệ/cấu hình), registry version và scrape configuration. Không công khai metrics endpoint ra Internet nếu chưa có kiểm soát truy cập.

### 12.1. Replay attempts trong 5 phút

~~~promql
sum(increase(hmac_replay_claims_total{outcome="replay"}[5m]))
~~~

`increase` ước lượng số increments của cumulative counter trong cửa sổ 5 phút, xử lý counter reset khi có đủ samples. Do scrape/extrapolation, kết quả có thể **không phải số nguyên tuyệt đối**, đừng dùng làm forensic ledger duy nhất.

### 12.2. Replay attempts mỗi giây

~~~promql
sum(rate(hmac_replay_claims_total{outcome="replay"}[5m]))
~~~

Unit ở đây là **observed replay decisions/second**, không phải phần trăm. Không gọi nó là “replay attack probability”.

### 12.3. Replay ratio theo route

~~~promql
100 *
sum by (route) (
  increase(hmac_replay_claims_total{outcome="replay"}[10m])
)
/
clamp_min(
  sum by (route) (
    increase(hmac_replay_claims_total{outcome=~"new|replay"}[10m])
  ),
  1
)
~~~

Đây là **observed replay share (%) trong các claims có authoritative decision**. `UNKNOWN` không được đưa vào denominator “decided” vì store không biết kết quả; cần biểu đồ uncertainty riêng.

`clamp_min(...,1)` tránh chia số 0, nhưng với traffic thấp replay ratio vẫn dễ dao động. Trên dashboard, hiển thị thêm **decided attempts/10m**, và cảnh báo tỷ lệ phải có volume gate. Khi metric hoàn toàn missing do scrape down, không được đọc số trống như bảo mật hoàn toàn tốt.

### 12.4. Unknown count và unknown share

~~~promql
sum by (route) (
  increase(hmac_replay_claims_total{outcome="unknown"}[5m])
)
~~~

~~~promql
100 *
sum by (route) (
  increase(hmac_replay_claims_total{outcome="unknown"}[10m])
)
/
clamp_min(
  sum by (route) (
    increase(hmac_replay_claims_total{
      outcome=~"new|replay|unknown"
    }[10m])
  ),
  1
)
~~~

Đây là **replay authority uncertainty**: request phải bị fail closed, nhưng client có thể thấy 5xx/401 theo contract và hệ thống mất availability. Không gộp unknown vào replay. Một network timeout có thể xảy ra **sau khi Redis đã ghi key**; không được dựa vào retry claim ngay lập tức để khẳng định event trước là replay attack.

### 12.5. So sánh NEW, REPLAY, UNKNOWN trong Grafana

~~~promql
sum by (route, outcome) (
  rate(hmac_replay_claims_total[5m])
)
~~~

Stacked chart cho thấy trends theo route. Bổ sung:
- Signed ingress request volume để biết có nhiều request bị chặn **trước** nonce gate.
- HMAC failure và timestamp-stale counters.
- HTTP response status và business idempotency duplicates.
- Redis latency, evictions, node restarts, replicas/partitions.

### 12.6. Tổng claims theo outcomes

~~~promql
sum(increase(hmac_replay_claims_total[1h]))
~~~

Không cộng tổng này với HTTP request total nếu không chứng minh sampling/stage semantics giống nhau.

### 12.7. Timer median/p95 và histogram

Nếu chưa bật histogram, quan sát tổng latency/số calls:

~~~promql
sum(rate(hmac_replay_claim_duration_seconds_sum[5m]))
/
clamp_min(
  sum(rate(hmac_replay_claim_duration_seconds_count[5m])),
  0.001
)
~~~

Đây là **mean claim duration (giây)**, không phải p95. Với traffic thấp denominator clamp làm mean bị chệch; hiển thị count để đọc đúng hoặc filter trên số lượng calls đủ lớn.

Chỉ khi Micrometer Timer có histogram buckets:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(hmac_replay_claim_duration_seconds_bucket[5m])
  )
)
~~~

Công thức này ước lượng **p95 claim latency** tổng các routes/outcomes, không phải p95 end-to-end HTTP. Nếu cần theo route:

~~~promql
histogram_quantile(
  0.95,
  sum by (route, le) (
    rate(hmac_replay_claim_duration_seconds_bucket[5m])
  )
)
~~~

Bật histogram có chi phí buckets × labels × instances; chọn SLO buckets rõ ràng. Không copy query `_bucket` sang dashboard khi exporter không phát metric đó.

### 12.8. Inflight pressure

~~~promql
sum(hmac_replay_inflight)
~~~

Gauge aggregate cho số claim calls đang chờ trên các instances; không cho biết chính xác đỉnh giữa scrapes và không tự thay thế Redis connection pool/queue metrics.

### 12.9. Mất metrics không phải replay bằng zero

Nếu cả `hmac_replay_claims_total` biến mất khi scrape down, biểu đồ có thể trở nên trống, NaN hoặc bị dashboard render thành 0. Phải giám sát scrape health bằng `up`, target count và ingestion/remote-write health. Nếu đã pre-register metric, `absent_over_time(hmac_replay_claims_total[15m])` có thể giúp phát hiện không có series, nhưng **nếu vốn không có traffic và meter chưa từng được register**, absence chưa chứng minh scrape lỗi.

## 13. Dashboard: một trang vận hành chống replay

Một dashboard có ích nên trả lời ít nhất năm câu hỏi, không chỉ hiển thị một số “replay today”.

| Hàng dashboard | Panel | Cách đọc |
| --- | --- | --- |
| 1 — Security outcomes | NEW/REPLAY/UNKNOWN events/s, replay share và volume | Có duplicate requests không? |
| 2 — Replay authority | UNKNOWN count/share, latency p50/p95, inflight | Store có đáng tin/đang chậm không? |
| 3 — Upstream signing | HMAC mismatch, malformed headers, timestamp old/future | Có lỗi client clock, canonicalization, key rollout không? |
| 4 — HTTP effects | 401/403/429/5xx, retry counts, timeout | Replay rejection ảnh hưởng clients thế nào? |
| 5 — Infrastructure | Redis health/eviction/memory, failover, network partitions | Có detection gap tiềm ẩn không? |
| 6 — Cohorts/routes | Route family và controlled region/environment | Vấn đề cục bộ hay toàn cục? |
| 7 — Business | Idempotency duplicates, operation outcomes | Signed retries có gây side effects không? |
| 8 — Evidence | Links tới secure logs/traces theo trace ID | Có đủ dữ liệu điều tra không rò secret? |

### 13.1. Grafana dashboard “0 replay” cần xem thêm gì?

Nếu hiển thị:
- `REPLAY=0`,
- `NEW=0`,
- `UNKNOWN=0`,

có thể đơn giản là endpoint không có traffic, metrics ingestion down, security filter bị bypass, hoặc tất cả requests bị chặn trước nonce. Kết luận “không có tấn công” **không đủ căn cứ**.

Muốn tin dashboard, đối chiếu HTTP traffic, HMAC admissions và filter invocation/nonce claim counts. Dùng canary signed request trên một **test credential/route** được phê duyệt để xác nhận pipeline, không cố tình replay request production nhạy cảm để “kiểm thử dashboard”.

### 13.2. Dashboard không cần per-client labels

Khi incident liên quan partner cụ thể, người có thẩm quyền dùng secure logs / audit reference và trace ID để drill down. Dashboard tổng quan nên aggregate theo route, region hoặc trusted cohort nhỏ. Một panel hiển thị raw client/tenant IDs từ request chưa authenticated có thể vừa làm lộ metadata vừa tạo cardinality DoS.

## 14. Alerting: ngưỡng, volume gate và hành động cụ thể

Alert cần chỉ rõ mục đích: phát hiện **duplicate spike**, **replay authority uncertainty**, **cấu hình TTL sai** hay **mất giám sát**. Các ngưỡng dưới đây chỉ là **điểm khởi đầu minh họa**; cần hiệu chỉnh theo traffic baseline, gateway retry policy, SLA và threat model.

### 14.1. Alert “ReplayDuplicateSurge” — không gọi thẳng là attack

~~~promql
(
  sum by (route) (
    increase(hmac_replay_claims_total{outcome="replay"}[10m])
  )
  /
  clamp_min(
    sum by (route) (
      increase(hmac_replay_claims_total{
        outcome=~"new|replay"
      }[10m])
    ),
    1
  )
) > 0.15
and on (route)
sum by (route) (
  increase(hmac_replay_claims_total{outcome=~"new|replay"}[10m])
) > 200
~~~

Điều kiện: replay share `>15%` **và** có trên 200 decided claims/10 phút tại một route. Với 1 replay trên 2 requests không nên page ngay chỉ vì ratio 50%.

Khi alert, kiểm retry settings, gateway timeout, client SDK deploys và scoped secure audit logs trước khi gắn nhãn malicious activity.

### 14.2. Alert “ReplayAuthorityUncertain”

~~~promql
sum by (route) (
  increase(hmac_replay_claims_total{outcome="unknown"}[5m])
) > 3
~~~

Nếu một route sensitive có bất kỳ uncertainty nào, có thể dùng mức ngưỡng thấp hơn. Quan trọng là **fail-closed được giữ nguyên**; alert cho biết availability/reliability bị ảnh hưởng, không phải “cho phép tạm các requests”.

### 14.3. Alert “NonceStoreLatencyHigh”

Nếu có histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (route, le) (
    rate(hmac_replay_claim_duration_seconds_bucket[5m])
  )
) > 0.2
~~~

Ở đây 0.2 = **200 milliseconds**, chỉ là ví dụ. Trước khi page cần lượng mẫu đủ, xác nhận histogram buckets được bật, và so với store SLA thực tế.

### 14.4. Alert cấu hình freshness/TTL

Config telemetry nên phát các giá trị `nonce_ttl_seconds`, `max_past_age_seconds`, `max_future_skew_seconds` với bounded labels. Một policy mismatch condition về nguyên tắc là:

\[
TTL_{\mathrm{nonce}} <
A + F + M \Longrightarrow \text{configuration alert}.
\]

Các giá trị nên được kiểm từ cùng **trusted deployed policy**, không lấy từ client headers. Không chỉ giám sát config ở một pod nếu cluster có rollout nhiều versions; cần kiểm consistency xuyên nodes.

### 14.5. Một Prometheus rule group minh họa

~~~yaml
groups:
  - name: hmac-replay-observability
    rules:
      - alert: HmacReplayAuthorityUncertain
        expr: |
          sum(increase(hmac_replay_claims_total{outcome="unknown"}[5m])) > 3
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Replay nonce authority returned uncertain outcomes"
          description: "Keep fail-closed; inspect Redis/network health."

      - alert: HmacReplayDuplicateSurge
        expr: |
          (
            sum(increase(hmac_replay_claims_total{outcome="replay"}[10m]))
            /
            clamp_min(
              sum(increase(hmac_replay_claims_total{outcome=~"new|replay"}[10m])),
              1
            )
          ) > 0.15
          and
          sum(increase(hmac_replay_claims_total{outcome=~"new|replay"}[10m]))
            > 200
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Elevated signed-request duplicates detected"
          description: "Check gateway/client retries; not proof of attack."
~~~

Prometheus rule examples cần xác nhận trong môi trường monitoring thực và hiệu chỉnh theo traffic. `for` làm hạn chế spikes ngắn nhưng có thể trì hoãn incident detection; chọn phù hợp operational risk.

### 14.6. Một alert phải có runbook link và safe action

Đừng tạo alert chỉ nói “Replay attack!!” mà không có hướng xử lý. Cần gắn tài liệu kiểm gateway retries, signed-key policy, Redis failover/eviction, canonical protocol, từng route cohort, audit access và client communication. Không dùng alert như lệnh tự động tắt anti-replay.

## 15. SLI/SLO và giới hạn diễn giải metric replay

Một SLI operational phù hợp:

\[
\text{Replay authority decision availability}
= \frac{N_{\mathrm{new}}+N_{\mathrm{replay}}}
{N_{\mathrm{new}}+N_{\mathrm{replay}}+N_{\mathrm{unknown}}}.
\]

Ví dụ một mục tiêu nội bộ có thể là **99.99% authoritative decisions**, nhưng đây chỉ là minh họa. Chọn SLO thực dựa trên service tier, failure budget, redundancy và data consistency requirement.

### 15.1. Auth availability khác security effectiveness

- **Availability SLI**: store trả `NEW` hoặc `REPLAY` có kết luận (không UNKNOWN).
- **Security property**: không hai requests với cùng signed nonce/namespace được admit trong freshness window (theo consistency guarantee).
- **Latency SLI**: p95/p99 store claim duration dưới ngưỡng.
- **Observability SLI**: metrics scrape/ingestion không bị mất.

Chỉ số availability có thể rất tốt nhưng security property vẫn hỏng do **eviction/replica failover tạo double NEW**. Không đánh đồng tỷ lệ UNKNOWN thấp với việc anti-replay chắc chắn hiệu quả.

### 15.2. Error budget không phải giấy phép fail open

Khi SLO store bị vi phạm, response có thể tạm giảm availability để bảo vệ integrity. Không chuyển `UNKNOWN` thành `NEW` chỉ vì “error budget đã hết”. Cần xử lý reliability của nonce authority (capacity, durable consistency, timeout, failover) thay vì loại bỏ security gate.

### 15.3. SLO metric phải có cùng scope

Nếu replay claims được thu ở HMAC filter cho signed routes, đừng dùng HTTP traffic của toàn website (gồm login/session/public health) làm denominator. Gắn route family và so với request matcher thực tế, có test bảo đảm instrumentation coverage.

## 16. Retry qua gateway, client SDK và service mesh

Một event `REPLAY` không tự đồng nghĩa attack. Khi có retry tự động, chỉ cần **cùng signed nonce** xuất hiện lại trong freshness window, store sẽ trả `REPLAY` dù caller ban đầu hoàn toàn hợp lệ.

### 16.1. Timeline ví dụ

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant A as Verifier Pod A
    participant N as Shared Redis Nonce Store
    participant B as Verifier Pod B

    C->>G: POST /orders (signed nonce N)
    G->>A: First HTTP request
    A->>N: SET N NX EX TTL
    N-->>A: NEW
    A->>A: Metric outcome=new
    Note over G,A: Response delayed or connection lost
    G->>B: Retry same signed request N
    B->>N: SET N NX EX TTL
    N-->>B: REPLAY
    B->>B: Metric outcome=replay
    B-->>G: Generic authentication/replay reject
~~~

Nếu operation đầu tiên đã commit nhưng response bị mất, một retry có thể bị anti-replay từ chối; điều đó **không chứng minh order chưa được tạo**. Client cần một business operation ID và endpoint truy vấn trạng thái, hoặc ký retry bằng nonce mới rồi để idempotency layer trả kết quả cũ.

### 16.2. Đọc dashboard cùng retry signals

Khi replay tăng, so với:
- `upstream_retry_attempts` của gateway/service mesh (nếu có và được cấu hình).
- Timeouts, connection resets, 502/503/504.
- Deployment/rollout của client SDK.
- Latency của verifier, nonce store, backend handler.
- `order_idempotency_duplicate_total` hoặc transaction retry metrics (tách tầng).
- Unique source cohorts trong **secure logs** nếu được phép điều tra.

Không kết luận “adversarial replay” khi mọi dấu hiệu đều trùng với một gateway retry policy mới được rollout.

### 16.3. Không làm mất anti-replay để sửa HTTP retry

Các cách không an toàn:
- Bỏ nonce kiểm tra nếu header `X-Retry: true` do caller gửi.
- Cho cùng nonce pass `N` lần để hỗ trợ gateway.
- Đặt TTL nonce bằng 10 giây để request retry sau 10 giây được phép.
- Dùng local map trên mỗi pod để “giảm tranh chấp”.
- Khi Redis timeout, tự coi nonce là NEW.

Các phương án an toàn hơn: client re-sign mỗi **HTTP attempt** bằng nonce mới, domain idempotency ổn định, status lookup, retry budget/timeouts và gateway retry policy rõ cho non-idempotent methods.

### 16.4. Metric không nên gọi retry là security incident chắc chắn

Đặt alert `ReplayDuplicateSurge` hoặc `SignedRequestDuplicateSpike`, với mô tả “check retries and potential abuse”. Việc tự động revoke toàn bộ key chỉ vì replay count tăng có thể gây gián đoạn rộng, đặc biệt khi gateway đang timeout.

## 17. Redis nonce authority: atomicity, TTL, eviction và failover

Một replay store tốt phải có atomic claim và retention phù hợp. Với Redis, thao tác thường là:

~~~redis
SET hmac-replay:v1:orders-api:partner-a-k3:0123456789abcdef0123456789abcdef seen NX EX 360
~~~

Kết quả:
- SET thành công → `NEW`.
- Key đã tồn tại và NX không ghi → `REPLAY`.
- Timeout/connection error/ambiguous response → `UNKNOWN` và **fail closed**.

Không dùng `GET` rồi `SET`: hai requests song song có thể cùng thấy missing rồi cùng đi tiếp. Không dùng `SETNX` và `EXPIRE` thành hai operations thiếu transaction/atomicity, vì có thể ghi key không TTL hoặc gặp race.

### 17.1. Java 17 với Spring Data Redis (Servlet/blocking)

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisAtomicNonceStoreV1
        implements AtomicNonceStoreV1 {

    private final StringRedisTemplate redis;

    public RedisAtomicNonceStoreV1(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public Claim claimOnce(String key, Duration ttl) {
        final Boolean inserted;
        try {
            inserted = redis.opsForValue()
                    .setIfAbsent(key, "seen", ttl);
        } catch (RuntimeException unavailable) {
            // Do not return NEW on an exception.
            return Claim.UNKNOWN;
        }

        if (Boolean.TRUE.equals(inserted)) return Claim.NEW;
        if (Boolean.FALSE.equals(inserted)) return Claim.REPLAY;
        return Claim.UNKNOWN;
    }
}
~~~

Đây là ví dụ cho **Spring MVC/Servlet blocking service**. Không gọi đồng bộ `StringRedisTemplate` trên Netty event loop. Với **Spring WebFlux** dùng `ReactiveStringRedisTemplate`, kết hợp `Mono<Boolean>` bằng `flatMap`/`map`, đo duration theo reactive completion và không gọi `block()` trong request pipeline.

### 17.2. Dung lượng store phụ thuộc số nonce mới và TTL

Một xấp xỉ cho số keys tồn tại trong steady state:

\[
N_{\mathrm{live}}\approx\lambda_{\mathrm{new}}\times TTL
\]

Ví dụ `2.000 NEW nonce/giây` với TTL 360 giây ⇒ khoảng **720.000 nonce records đang sống**. Đây chỉ là số keys, không phải bytes; overhead thực tế phụ thuộc Redis encoding, allocator, key length, replication và workload.

Nếu Redis dùng memory eviction và đẩy nonce key ra trước TTL, request cũ có thể bị accept lại như `NEW` trong khi timestamp vẫn fresh. Khi đó **replay metric không nhất thiết tăng**. Phải giám sát eviction, memory, maxmemory policy, key TTL correctness và replay consistency tests, không dựa chỉ vào `REPLAY`/`UNKNOWN`.

### 17.3. Redis primary atomicity không tự bảo đảm mọi failover

Một Redis primary có thể chấp nhận claim `NEW` và gửi response, nhưng ghi chưa kịp replication trước failover. Replica trở thành primary mới có thể **không chứa nonce**, cho bản sao request tiếp theo lại `NEW`. Đây là **replay detection gap** có thể xảy ra dù mỗi `SET NX EX` riêng lẻ atomic trên một primary.

Nếu security contract yêu cầu mạnh hơn, cân nhắc replay authority với consistency/durability phù hợp, retention reconciliation, fencing hoặc commit protocols. Cần xác minh thực tế qua failover tests; đừng suy “Redis cluster” nghĩa là exactly-once global.

### 17.4. Metrics hỗ trợ nhưng không quan sát trực tiếp false NEW

Một second `NEW` sai do mất key trông giống một `NEW` bình thường trong counter. Phát hiện cần:
- Test duplicate nonce giữa nodes trước/sau failover.
- Storage health metrics: failover, replication lag, evictions, persistence.
- Structured audit/operation correlation cho security investigation nếu phù hợp.
- Analysis of accepted operations/idempotency anomalies với quyền hạn và retention rõ.

Không dùng `replay count = 0` làm chứng cứ datastore không mất record.

### 17.5. Timeout sau write thành công

Trường hợp khó:

~~~text
Verifier sends SET NX EX.
Redis applies write.
Network timeout prevents verifier from seeing response.
Verifier records UNKNOWN and fails closed.
Client retries same signed request.
Redis responds REPLAY.
~~~

Event đầu không được tự đổi thành `NEW` hay `REPLAY` dựa trên một response đến sau trong request khác. Security decision đã là **UNKNOWN** ở thời điểm cần quyết định, và response của client có thể là unavailable. Một `REPLAY` tiếp theo không chứng minh attacker; có thể là retry sau uncertain commit.

## 18. Multi-node, multi-region, tenants và credential rotation

### 18.1. Mọi verifier phải dùng chung nonce authority theo scope

Nếu cùng key ID/audience có thể vào Pod A/B/C, chúng phải claim trên một authoritative namespace. Một local `HashSet` sẽ tạo ba independent `NEW` decisions cho cùng nonce. Metrics per-pod có thể cùng tăng NEW, nhưng không tự phát hiện lỗi nếu không có cross-pod duplicate tests.

### 18.2. Namespace phải có identity boundary ổn định

Một key minh họa:

~~~text
hmac-replay:v1:orders-api:partner-a-k3:<signed-nonce>
~~~

`v1` và `audience` đến từ trusted contract/config; `partner-a-k3` phải là **exact key ID** đã được parse/chọn theo trusted registry, còn nonce đã được signed. Không lấy raw `X-Tenant-Id` hoặc `X-Partner` từ unauthenticated caller làm namespace.

Nếu key A và B độc lập cùng gửi chuỗi nonce giống nhau, đó **không nhất thiết** là replay khi namespace tách theo key. Nếu chung một secret được dùng dưới nhiều IDs, isolation đã yếu và cần xem lại key management.

### 18.3. Key rotation làm thay đổi namespace

Khi chuyển k2→k3, nonce của k2 và k3 nằm trong scopes khác nhau. Một k2 đã REVOKED không được accept chỉ vì nonce trên k2 NEW và chưa có key trong store. Key policy phải chặn **trước nonce claim**. Metrics key-policy rejects sẽ tăng, replay metric có thể không tăng.

Nếu partner dùng k3 key ID nhưng ký bằng secret k2, request fail MAC; **không đo là REPLAY**, không quét old secret để “giúp” retry.

### 18.4. Tenant authorization vẫn độc lập

Một HMAC k3 có tag đúng và nonce `NEW` nhưng principal không có permission trên tenant B phải bị authorization deny. Replay metric ghi `NEW` (claim đã xảy ra); authorization metric ghi `denied`. Không xóa/revert nonce chỉ vì authorization sau đó thất bại: làm vậy có thể cho request giống hệt được admit lại và lặp work.

### 18.5. Multi-region consistency

Nếu regions có nonce stores độc lập không đồng bộ, một signed request có thể `NEW` ở cả region A và B. Alert `REPLAY` thấp không chứng minh protection global. Architecture phải định nghĩa:
- Traffic pinned một region hay global active-active?
- Namespace/authority có shared consistency không?
- Replica lag/failover window là bao nhiêu?
- Partition khiến admission fail closed hay cho stale local claims?
- Có operational runbook khi failover không?

Tất cả câu trả lời cần gắn với **security guarantee thật**; không hứa global at-most-once khi backing store chỉ eventual-consistent.

## 19. Spring Security MVC và WebFlux: đặt instrumentation đúng chỗ

### 19.1. Servlet / Spring MVC

Trong MVC, một HMAC `AuthenticationFilter` hoặc custom `OncePerRequestFilter` có thể delegate tới verifier, và verifier gọi nonce adapter `ReplayClaimObserverV1` sau MAC/freshness. Controller không cần biết replay counter.

~~~text
Servlet filter
  -> strict HTTP metadata/body contract
  -> HMAC/key verifier
  -> freshness
  -> ReplayClaimObserverV1
  -> authenticated SecurityContext
  -> AuthorizationFilter
  -> controller
~~~

**Không** tạo authenticated principal chỉ từ header key ID. Nếu filter ném exception trước `ExceptionTranslationFilter`, phải có failure handler/`AuthenticationEntryPoint` đúng vị trí; không catch mọi `Exception` rồi cho request qua.

### 19.2. WebFlux / reactive

Reactive chain:

~~~text
ServerWebExchange
  -> body capture/replay if required
  -> AuthenticationWebFilter + ServerAuthenticationConverter
  -> ReactiveAuthenticationManager
  -> reactive nonce store
  -> metric observation on Mono termination
  -> ReactiveSecurityContextHolder
  -> authorization and handler
~~~

Một lỗi lớn là gọi:

~~~java
// SAI: subscription riêng có thể chạy sau handler.
reactiveNonceStore.claimOnce(key, ttl).subscribe();
return chain.filter(exchange);
~~~

Một reactive adapter đúng phải compose claim trước handler, ví dụ minh họa:

~~~java
return reactiveNonceStore.claimOnce(key, ttl)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Replay decision missing")))
        .flatMap(claim -> {
            if (claim == Claim.NEW) {
                return authenticatedNextStep();
            }
            if (claim == Claim.REPLAY) {
                return Mono.error(
                    new BadCredentialsException("Signed request replay"));
            }
            return Mono.error(
                new AuthenticationServiceException(
                    "Replay authority uncertain"));
        });
~~~

**Ví dụ chỉ minh họa control flow**: `Claim`, `BadCredentialsException`, `AuthenticationServiceException`, `authenticatedNextStep()` cần được cung cấp bởi project; metrics nên được ghi một lần tại authority adapter khi `Mono` phát result/error, không gọi `subscribe()` bên ngoài chain.

### 19.3. Reactive metrics không được tính khi xây Mono mà chưa subscribe

`Mono` là publisher. Một lệnh `counter.increment()` đặt khi **tạo** publisher có thể tăng metric dù HTTP request chưa thực thi; còn một `doOnNext` chỉ ghi khi có result và **bỏ sót exception/empty**. Dùng `Mono.defer`/`doFinally`/`materialize` hoặc thiết kế wrapper quanh publisher với state đảm bảo:
- Đếm `NEW`/`REPLAY` khi authoritative result được phát.
- Đếm `UNKNOWN` khi error/empty/cancel có outcome không rõ theo policy.
- Không ghi hai events cho cùng claim invocation.
- Không claim nonce lần hai khi client retries hoặc filter được subscribe lại ngoài dự kiến.

Cancellation cần được xem riêng: nếu client hủy subscriber sau khi Redis đã ghi nhưng trước khi trả response, kết quả **có thể chưa xác định**. Đừng coi cancel là `REPLAY`; đồng thời nên có event metric cho cancellation nếu cần.

### 19.4. Giám sát filter invocation count

Nếu HMAC filter được đăng ký kép ở Servlet container và security chain, một request có thể verify/claim nonce hai lần; lần thứ hai tự tạo `REPLAY`. Khi replay spike sau deployment, kiểm filter chain order, duplicate registration và async/error dispatch, không chỉ Redis.

## 20. Java 17 + JUnit 5: kiểm thử recorder bằng SimpleMeterRegistry

Micrometer cung cấp `SimpleMeterRegistry` để test counters/timers trong một JVM mà không cần chạy Prometheus. Test phải khẳng định **mỗi claim invocation sinh đúng một outcome**, `NEW` và `REPLAY` tách biệt, `UNKNOWN` không biến thành `REPLAY`, và gauge không giữ số inflight sau lỗi.

### 20.1. Fake atomic store trong một JVM

~~~java
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeAtomicNonceStoreV1
        implements AtomicNonceStoreV1 {

    private final Set<String> seen =
            ConcurrentHashMap.newKeySet();
    private volatile boolean fail;

    public void setFail(boolean value) {
        fail = value;
    }

    @Override
    public Claim claimOnce(String key, Duration ttl) {
        if (fail) {
            throw new IllegalStateException("Fake store outage");
        }
        return seen.add(key) ? Claim.NEW : Claim.REPLAY;
    }
}
~~~

Fake này chỉ có atomicity **trong process**, không TTL hoặc Redis failover. Không dùng kết quả test này làm bằng chứng bảo vệ replay multi-region.

### 20.2. JUnit Jupiter: NEW → REPLAY

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public final class HmacReplayMetricsV1Test {

    @Test
    void firstClaimNewSecondClaimReplay() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new HmacReplayMetricsV1(registry);
            var store = new FakeAtomicNonceStoreV1();
            var observer = new ReplayClaimObserverV1(
                    store, metrics);

            String key = "test:orders:client-a:nonce-123";
            Duration ttl = Duration.ofSeconds(360);

            assertEquals(AtomicNonceStoreV1.Claim.NEW,
                    observer.claimOnce(
                        HmacRouteGroupV1.ORDERS_WRITE,
                        key, ttl));

            assertEquals(AtomicNonceStoreV1.Claim.REPLAY,
                    observer.claimOnce(
                        HmacRouteGroupV1.ORDERS_WRITE,
                        key, ttl));

            assertEquals(1.0,
                    registry.get("hmac.replay.claims")
                        .tags("route", "orders_write",
                              "outcome", "new")
                        .counter().count());

            assertEquals(1.0,
                    registry.get("hmac.replay.claims")
                        .tags("route", "orders_write",
                              "outcome", "replay")
                        .counter().count());

            assertEquals(0.0,
                    registry.get("hmac.replay.claims")
                        .tags("route", "orders_write",
                              "outcome", "unknown")
                        .counter().count());

            assertEquals(1L,
                    registry.get("hmac.replay.claim.duration")
                        .tags("route", "orders_write",
                              "outcome", "new")
                        .timer().count());

            assertEquals(0.0,
                    registry.get("hmac.replay.inflight")
                        .gauge().value());
        }
    }
}
~~~

**Ý nghĩa:** Test xác minh instrumentation owner và labels fixed; nó chưa kiểm verifier HMAC đặt claim sau MAC đúng. Thêm test integration của verifier orchestration để chắc chắn khi `BAD_MAC` hoặc `STALE_TIMESTAMP` thì observer **không được gọi**.

### 20.3. JUnit: store outage tăng UNKNOWN và không “NEW”

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public final class ReplayUnknownMetricV1Test {
    @Test
    void thrownStoreErrorRecordsUnknownAndPropagates() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new HmacReplayMetricsV1(registry);
            var store = new FakeAtomicNonceStoreV1();
            store.setFail(true);

            var observer = new ReplayClaimObserverV1(
                    store, metrics);

            assertThrows(IllegalStateException.class,
                () -> observer.claimOnce(
                    HmacRouteGroupV1.ORDERS_WRITE,
                    "test:key:nonce",
                    Duration.ofSeconds(360)));

            assertEquals(1.0,
                registry.get("hmac.replay.claims")
                    .tags("route", "orders_write",
                          "outcome", "unknown")
                    .counter().count());

            assertEquals(0.0,
                registry.get("hmac.replay.claims")
                    .tags("route", "orders_write",
                          "outcome", "replay")
                    .counter().count());

            assertEquals(0.0,
                registry.get("hmac.replay.inflight")
                    .gauge().value());
        }
    }
}
~~~

### 20.4. JUnit: null response cũng là UNKNOWN

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public final class ReplayEmptyDecisionMetricV1Test {
    @Test
    void missingStoreResultNeverBecomesNew() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new HmacReplayMetricsV1(registry);

            AtomicNonceStoreV1 broken = (key, ttl) -> null;
            var observer = new ReplayClaimObserverV1(
                    broken, metrics);

            assertEquals(AtomicNonceStoreV1.Claim.UNKNOWN,
                observer.claimOnce(
                    HmacRouteGroupV1.OTHER,
                    "test:key:nonce",
                    Duration.ofSeconds(360)));

            assertEquals(1.0,
                registry.get("hmac.replay.claims")
                    .tags("route", "other",
                          "outcome", "unknown")
                    .counter().count());
        }
    }
}
~~~

### 20.5. Những test vẫn cần ngoài unit recorder

- `Invalid HMAC` → nonce observer không được gọi; replay counters không tăng.
- `Revoked credential` → không gọi store, key policy rejects tăng.
- `Timestamp stale` → chỉ freshness metric tăng, không claim nonce.
- `Valid HMAC + nonce NEW + authorization deny` → NEW tăng, authorization deny tăng riêng.
- `Unknown replay store result` → không tạo principal, không gọi controller.
- `Gateway retry cùng signed nonce` → second claim REPLAY, business không chạy lần hai.
- `Two keys A/B cùng nonce text` → hai scoped keys khác nhau đều có thể NEW.
- `Metrics disabled/backend outage` → security decision vẫn fail closed khi authority lỗi, không cho phép vì metrics không sẵn.
- `Counter tag combinations` chỉ là cố định, không tồn tại label raw key ID/nonce.
- `Pod restart` không làm dashboard hiểu counters giảm đột ngột thành âm traffic.

## 21. Concurrency, multi-pod và fault injection

### 21.1. Một trăm claims đồng thời cùng nonce

Một unit concurrency test có thể dùng barriers trên fake store:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.ArrayList;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public final class ReplayConcurrentMetricV1Test {
    @Test
    void oneNewNinetyNineReplayForOneJvmAuthority()
            throws Exception {

        try (var registry = new SimpleMeterRegistry()) {
            var store = new FakeAtomicNonceStoreV1();
            var metrics = new HmacReplayMetricsV1(registry);
            var observer = new ReplayClaimObserverV1(
                    store, metrics);

            var pool = Executors.newFixedThreadPool(16);
            var start = new CountDownLatch(1);
            try {
                var tasks =
                    new ArrayList<Callable<AtomicNonceStoreV1.Claim>>();

                for (int i = 0; i < 100; i++) {
                    tasks.add(() -> {
                        start.await();
                        return observer.claimOnce(
                            HmacRouteGroupV1.ORDERS_WRITE,
                            "test:key:same-signed-nonce",
                            Duration.ofSeconds(360));
                    });
                }

                var futures = tasks.stream()
                    .map(pool::submit)
                    .toList();

                start.countDown();

                long newCount = 0;
                long replayCount = 0;
                for (var f : futures) {
                    var result = f.get(10, TimeUnit.SECONDS);
                    if (result == AtomicNonceStoreV1.Claim.NEW)
                        newCount++;
                    if (result == AtomicNonceStoreV1.Claim.REPLAY)
                        replayCount++;
                }

                assertEquals(1, newCount);
                assertEquals(99, replayCount);

                assertEquals(1.0,
                    registry.get("hmac.replay.claims")
                        .tags("route", "orders_write",
                              "outcome", "new")
                        .counter().count());

                assertEquals(99.0,
                    registry.get("hmac.replay.claims")
                        .tags("route", "orders_write",
                              "outcome", "replay")
                        .counter().count());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
~~~

**Lưu ý:** Đây là test trên `ConcurrentHashMap` JVM đơn, không chứng minh Redis/distributed durability. Nó cũng chỉ test behavior khi tất cả claims cùng một namespace; throughput/latency benchmark cần measurement environment riêng.

### 21.2. Integration qua hai hoặc nhiều pods

Một test mạnh hơn:

1. Dùng **cùng test credential** trong trusted registry cho hai pods A/B.
2. Ký request đúng HMAC, timestamp fresh, nonce N.
3. Gửi đồng thời tới A và B qua ingress/load balancer hoặc direct trusted test channels.
4. Dùng shared replay authority thật với atomic create-if-absent.
5. Đếm authoritative decisions: kỳ vọng **≤1 NEW** trong configured consistency guarantee.
6. Đo metrics aggregate: một NEW, còn lại REPLAY hoặc UNKNOWN nếu có timeout.
7. Kiểm không có duplicate business side effects; business idempotency vẫn là lớp riêng.
8. Lặp khi network delay, Redis failover, pod restart, cache eviction và cross-region routing.

Không suy “at most one global NEW” nếu authority chỉ đảm bảo primary-local atomicity hoặc failover có thể mất writes. Phải ghi kết quả test cùng topology/consistency assumptions.

### 21.3. Các fault injection cần test

| Fault | Metric mong đợi | Bất biến bảo mật |
| --- | --- | --- |
| Redis timeout trước khi biết kết quả | UNKNOWN tăng | No business on uncertain claim |
| Redis write applied nhưng response lost | UNKNOWN ở request đầu, retry có thể REPLAY | Không tự suy request đầu thành replay |
| Redis returns existing key | REPLAY tăng | Request hiện tại bị deny |
| Redis key evicted sớm | Có thể sai NEW | Cần phát hiện qua storage health/tests |
| Key registry unavailable | Key dependency metric, không claim | No replay metric vì chưa tới gate |
| Bad HMAC flood | HMAC mismatch tăng, replay không tăng | Không poison nonce |
| Timestamp old | Freshness reject tăng | Không claim nonce |
| Key REVOKED | Credential policy reject tăng | No principal |
| Gateway retries same signed headers | REPLAY có thể tăng | Domain effects không double apply |
| Client re-signs new nonce same operation | NEW tăng | Domain idempotency prevents double effect |
| Cross-pod independent nonce maps | NEW có thể tăng trên nhiều pods | Violation; cần shared authority |
| Clock drift after signed request | Stale/future rejects tăng | No mistaken replay classification |
| Metrics scrape down | Target up/absence alert | Security still enforced |

### 21.4. Test non-blocking runtime riêng

Trong Spring WebFlux, `SimpleMeterRegistry` operations là local in-process, nhưng Redis/JDBC/KMS clients có thể blocking. Dùng reactive store hoặc bounded offload cho các dependency blocking và đo event-loop latency/queue saturation. Không biến `Mono` thành blocking bằng `block()` hoặc tự `subscribe()` vì có thể làm request chạy business trước nonce decision.

## 22. Runbook: khi Metric replay tăng bất thường

Runbook phải tách **duplicate traffic**, **anti-replay dependency failure** và **security bypass**. Không coi mọi sự kiện REPLAY là tấn công, và không tắt nonce gate chỉ vì error rate tăng.

### 22.1. Bước 1 — Xác minh monitoring còn sống

1. Kiểm `up`, scrape target counts, Prometheus ingestion lag/remote-write errors.
2. Đối chiếu `http_server_requests` với `hmac.auth.admissions` và `hmac.replay.claims`.
3. Kiểm route matcher, feature flags và security chain có chạy không.
4. Xem deployments vừa thay instrumentation, renaming metric hoặc exporter registry.
5. Xác nhận counters reset do pod restart được PromQL `increase/rate` xử lý.
6. Nếu biểu đồ rỗng, không tự báo “replay = 0”.

### 22.2. Bước 2 — Phân loại spike

| Quan sát | Giả thuyết ban đầu | Cần xác minh |
| --- | --- | --- |
| REPLAY tăng, UNKNOWN thấp | Retry hoặc deliberate duplicate | Gateway retry counts, signed request audit |
| REPLAY tăng sau deploy gateway | Retry config/filter double registration | Rollout, chain ordering, timeouts |
| UNKNOWN tăng, Timer latency tăng | Replay authority timeout | Redis/network/connection pool |
| UNKNOWN tăng đột ngột không có REPLAY | Store outage | Health, partitions, exceptions |
| REPLAY thấp, NEW tăng sau Redis failover | Có thể đã mất nonce records | Failover, replication lag, idempotency anomalies |
| Key policy rejects tăng, REPLAY không đổi | Credential rotation/revocation | Trusted registry events |
| Freshness rejects tăng, REPLAY thấp | Client clock skew/timestamp protocol | Client SDK time sync, server clock |
| Bad MAC tăng, REPLAY thấp | Client signing mismatch, proxy rewrite hoặc attack | Golden canonical fixtures, gateway changes |
| Authenticated NEW tăng nhưng order duplicates tăng | Idempotency issue | Domain operation IDs/transactions |
| Replay rải rác trên một route | Client retry bug hoặc intermittent network | Safe cohort analysis qua secure logs |

### 22.3. Bước 3 — Kiểm các security invariants

1. HMAC full-tag verification vẫn bắt buộc và **đặt trước nonce claim**?
2. Key ID exact lookup và credential status còn enforced?
3. Signed timestamp/nonce có trong canonical request?
4. Redis insert-if-absent + expiry thực hiện **atomic**?
5. TTL đủ bao phủ `A+F+margin`?
6. Unknown/outage có **fail closed**?
7. Có eviction/replica failover/region partition gây false NEW không?
8. Nhiều pods đang dùng cùng namespace/authority?
9. Authorization tenant/resource còn enforced sau authentication?
10. Domain idempotency vẫn ngăn duplicate side effects?

Nếu một invariant bị vi phạm, ưu tiên containment, điều tra accepted requests và sửa root cause theo incident policy. Không chỉ chỉnh alert threshold để tắt cảnh báo.

### 22.4. Bước 4 — Kiểm HTTP retry và gateway behavior

- Client retry có reuse exact signature/nonce hay re-sign?
- Gateway có retry non-idempotent methods như POST không?
- Có HTTP 502/503/504, idle timeout hoặc connection reset tăng cùng lúc?
- Service mesh có duplicate delivery/restart policy?
- Một Servlet filter có bị registered cả trong container và Spring Security không?
- WebFlux authentication publisher có bị subscribed lại trong error/async path không?
- Host/URI rewrite có khiến clients tự retry do HMAC mismatch trước đó không?

Nếu retry policy gây duplicate, sửa client/gateway/idempotency và test, không thay đổi anti-replay contract để accept cùng nonce.

### 22.5. Bước 5 — Điều tra hành vi đáng ngờ an toàn

Nếu spike không giải thích được bởi retries hoặc rollout:

- Correlate server-generated trace IDs và **trusted principal** sau MAC (nếu security/privacy policy cho phép).
- Xem route/action/tenant scopes với authorization logs, không log raw nonce/signature.
- Đánh giá unusual request rates, geographic/ASN patterns theo approved security process, không kết luận từ nguồn IP duy nhất.
- Kiểm key compromise indicators (fresh signed requests bất thường, scope misuse); replay metric **không đủ** để kết luận secret leak.
- Nếu nghi compromise, revoke key bị ảnh hưởng, cấp secret/key ID mới và rà soát accepted side effects.
- Giữ evidence trong privileged audit store đúng retention/consent/company policy.

### 22.6. Bước 6 — Kết thúc sự cố

1. Ghi rõ start/end time theo UTC và route/region scope.
2. Phân loại nguyên nhân: client retry, gateway, Redis outage, TTL, failover, rotation, abuse hoặc unknown.
3. Đánh giá có mất **availability** hay **security guarantee**, không gộp hai khái niệm.
4. Đối chiếu business operations đã commit hoặc đang uncertain.
5. Cập nhật thresholds, runbook, test matrix và client SDK guidance nếu phù hợp.
6. Giữ các metric definitions ổn định để so trend trước/sau fix.

## 23. Những sai lầm phổ biến khi giám sát replay

### 23.1. “Replay count bằng 0 là hệ thống an toàn”

Không. Một nonce store bị eviction hoặc replica failover có thể trả NEW lần hai. Metric thấp cũng có thể do security filter bypass hoặc không có traffic.

### 23.2. “Mọi 401 đều là replay”

Không. 401 có thể do unknown key ID, bad MAC, timestamp stale, revoked credential. Chỉ count REPLAY khi nonce authority trả authoritative duplicate.

### 23.3. “Redis timeout là replay”

Không. Timeout có thể xảy ra trước hoặc sau write; request hiện tại **không có quyết định chắc chắn**. Đếm UNKNOWN và fail closed.

### 23.4. “Metric nằm trong controller là đủ”

Không. Request bị replay filter deny trước controller sẽ không tới handler. Đặt ở replay claim boundary; test invocation count.

### 23.5. “Dùng nonce làm label giúp debug”

Không. Nó tạo high-cardinality, có nguy cơ lộ signed metadata và làm Prometheus quá tải. Dùng secure correlation logs.

### 23.6. “Client retry cùng nonce thì cứ cho qua lần hai”

Không. Anti-replay và business idempotency là hai lớp độc lập. Điều chỉnh client re-sign/idempotency/retry policy, không phá replay guarantee.

### 23.7. “Counter rate 20 nghĩa là 20%”

Không. `rate(counter[5m])` là số sự kiện/giây. Tỷ lệ phần trăm cần numerator/denominator trong cùng scope và window.

### 23.8. “UNKNOWN có thể nhập vào REPLAY vì đều fail”

Không. Về availability/security evidence, chúng khác nhau. REPLAY là duplicate được xác nhận; UNKNOWN là dependency không cho kết luận.

### 23.9. “Mỗi tag route cứ lấy full URI”

Không. Raw path/query chứa resource IDs và số biến vô hạn; chỉ dùng server-defined route family.

### 23.10. “Pod A có 100 replay, pod B 0 là bất thường chắc chắn”

Có thể traffic bị load-balanced lệch, các retries được sticky hoặc pods có workloads khác nhau. Tổng hợp theo route/region, kiểm upstream routing trước khi kết luận. Nhưng nếu cùng nonce bị NEW trên cả hai pods, đó là vấn đề security cần điều tra.

### 23.11. “Observed replay share giảm sau failover là tốt”

Có thể nonce records đã mất và duplicate requests đang bị nhận `NEW`. Xem failover, evictions, accepted operation anomalies và tests, không chỉ share.

### 23.12. “P95 từ sum/count là đúng”

`sum(rate(_sum))/sum(rate(_count))` là **mean**, không phải p95. Muốn p95 cần histogram buckets hoặc phương pháp quantile được triển khai đúng.

### 23.13. “Chỉ cần metric, không cần logs và audit”

Counters không cung cấp request identity/causality. Secure logs/traces cho correlation và forensic, nhưng không được chứa secret hoặc full replayable HTTP request.

### 23.14. “Khi metrics exporter lỗi thì tắt security verification để đỡ load”

Instrumentation không được quyết định authentication. Sửa monitoring backend và bảo đảm security gates vẫn chạy; tránh để telemetry failure gây accept sai.

### 23.15. “REPLAY luôn có nghĩa secret bị lộ”

Một attacker có thể replay signed request bị lộ **mà không biết secret**, còn client/gateway retries có thể tạo REPLAY hợp pháp. Ngược lại attacker có secret bị lộ có thể ký **nonce mới**, không làm replay metric tăng. Cần threat model và nhiều signals.

### 23.16. “Không cần test TTL vì đã có SET NX”

NX chỉ ngăn duplicate **khi key còn tồn tại**. TTL quá ngắn, eviction hoặc failover vẫn có detection gap; test freshness/retention/replication riêng.

## 24. Bài tập thực hành

### Bài tập 1 — Định nghĩa replay metric

Cho request pipeline `parse → key → MAC → timestamp → nonce → authorization`. Xác định chính xác điểm increment `outcome=replay`. Giải thích vì sao bad MAC, stale timestamp, wrong tenant và nonce store outage **không** tự tăng replay counter.

### Bài tập 2 — Đọc bảng số liệu

Trong 10 phút, một route có 800 NEW, 160 REPLAY, 40 UNKNOWN. Tính:
- Tổng claim attempts.
- Replay share trong decided claims.
- Unknown share trong all claims.
- Authority decision availability.

So sánh với HTTP request total 1.400 và giải thích vì sao không được dùng 1.400 làm denominator mà không ghi rõ mục đích.

### Bài tập 3 — PromQL có volume gate

Viết query cảnh báo replay share >20% **chỉ nếu decided claims >100/10 phút**. Dùng `increase` và `clamp_min`; xác nhận biểu thức không nhầm events/s với phần trăm.

### Bài tập 4 — Chống high-cardinality

Một developer muốn thêm labels `keyId`, `nonce`, `rawPath` và `clientIP`. Tính các rủi ro cardinality và privacy, rồi thay bằng `route`, `outcome` và `reason` enums. Đề xuất cách drill down bằng secure audit logs.

### Bài tập 5 — Java17 recorder

Dùng `SimpleMeterRegistry` và `HmacReplayMetricsV1`. Gọi observer 1 NEW, 2 REPLAY, 1 UNKNOWN. Assert counts và `inflight=0`. Không dùng raw key ID làm label.

### Bài tập 6 — Wrong MAC không poison nonce

Tạo verifier fake trả `BAD_MAC` trước replay stage; assert `hmac.auth.rejects{stage="mac"}` tăng, `hmac.replay.claims` không tăng và replay store không được gọi. Sau đó gửi MAC thật cùng nonce, assert NEW.

### Bài tập 7 — Gateway retry

Cho gateway tự retry POST cùng signed nonce sau timeout. Vẽ hai requests A/B, đọc NEW/REPLAY counts, giải thích vì sao một 401 ở retry không chứng minh order chưa commit. Thiết kế operation ID/status lookup.

### Bài tập 8 — Clock skew

Dùng fixed server clock, `A=300`, `F=30`. Gửi timestamp quá cũ/tương lai và nonce mới. Đếm freshness rejects, không claim nonce. Kiểm exact boundary timestamps.

### Bài tập 9 — TTL replay gap

Dùng TTL 300s với `A=300`, `F=30`; minh họa nonce expire trước khi timestamp hết freshness. Đổi TTL ≥360s (có margin), lập test fake clock/store expiration.

### Bài tập 10 — Redis eviction

Giả lập nonce key bị eviction sớm. Cùng request có thể claim NEW lần hai. Giải thích vì sao replay metric không tăng, tìm những infrastructure/forensic signals cần thêm, đề xuất thay đổi memory/eviction policy.

### Bài tập 11 — Multi-pod concurrency

Gửi 100 signed requests cùng nonce qua hai pods dùng shared Redis authority. Kiểm at most one NEW theo configured guarantee. Lặp với intentionally broken local stores; so sánh metrics và accepted business operations.

### Bài tập 12 — Redis failover

Đặt barrier sau khi primary chấp nhận SET NX nhưng trước replica replication; failover rồi retry same nonce. Quan sát possible false NEW, ghi rõ consistency assumptions và mitigation path. Không khẳng định atomic primary operation tự đảm bảo global durability.

### Bài tập 13 — Spring WebFlux

Dùng `ReactiveAuthenticationManager`/`ReactiveStringRedisTemplate` và `StepVerifier`; bảo đảm metrics ghi khi publisher được subscribe/completed, không khi dựng Mono, không tự `subscribe()`. Test timeout, cancellation và replay.

### Bài tập 14 — Alert calibration

Từ baseline traffic 500 requests/phút, gateway retries 2%, chọn warning thresholds cho duplicate surge và UNKNOWN. Thử low-traffic route 1 request/giờ; giải thích tại sao replay ratio 100% một sample không nên gọi pager ngay.

### Bài tập 15 — Incident response

Dashboard cho thấy REPLAY tăng sau client SDK release, UNKNOWN ổn, Redis latency bình thường, 504 tăng. Xây runbook kiểm retry code và business idempotency, không tự động rotate key khi chưa có dấu hiệu compromise.

### Bài tập 16 — Secret compromise

Một attacker có stolen secret ký request mới bằng nonce ngẫu nhiên khác nhau. Replay counter có thể vẫn thấp. Thiết kế các tín hiệu bổ sung: action rate, scope/tenant anomalies, credential revocation evidence và secure audit correlation.

## 25. Checklist triển khai Metric replay trong HMAC HTTP

### 25.1. Định nghĩa event chính xác

- [ ] Một replay event chỉ được ghi khi **shared atomic authority trả REPLAY**.
- [ ] `NEW`, `REPLAY`, `UNKNOWN` loại trừ nhau cho một claim invocation.
- [ ] MAC sai, key revoked/unknown và timestamp stale không được đếm là replay.
- [ ] Claims metrics chỉ có scope **requests thực sự tới nonce store**, không phải mọi HTTP request.
- [ ] `UNKNOWN` bao gồm timeout/empty/null/ambiguous commit; không bị đổi thành NEW hoặc REPLAY.
- [ ] Nonce chỉ được claim **sau** exact key lookup, full HMAC tag và freshness checks.
- [ ] Metric instrumentation là observer, không thay security decision.
- [ ] Business idempotency duplicate có metric riêng, không dùng nonce metric thay thế.
- [ ] Cách tính replay share, unknown share và claims per second được tài liệu hóa với denominator/window.
- [ ] Metric names, units và export name Micrometer→Prometheus được kiểm trên runtime thật.

### 25.2. Anti-replay guarantee

- [ ] Key ID, timestamp và nonce nằm trong signed canonical request.
- [ ] Full HMAC tag được strict decode/compare trước nonce admission.
- [ ] Server clock freshness window dùng max past age, future skew rõ.
- [ ] Replay TTL ≥ `A + F + margin` theo contract và được test boundary.
- [ ] Nonce store dùng atomic conditional insert + expiry.
- [ ] Một shared authority hoặc topology phù hợp cho tất cả relevant verifier nodes.
- [ ] Key namespace bao gồm trusted version/audience/exact key ID và signed nonce.
- [ ] Redis failover, replica lag, eviction và early expiry được đánh giá.
- [ ] Replay store lỗi/UNKNOWN fail closed; không cho business qua.
- [ ] Key REVOKED bị deny dù MAC đúng và nonce NEW.
- [ ] Tenant/action/resource authorization giữ tách biệt sau authentication.
- [ ] Có tests multi-node/region tương ứng với consistency guarantee thực tế.

### 25.3. Metric cardinality và privacy

- [ ] `outcome` và `reason` là enums đóng.
- [ ] `route` là server-defined family/template, không raw URI.
- [ ] Không label bằng raw nonce, timestamp, signature, secret, key ID.
- [ ] Không label bằng arbitrary client/tenant IDs hay user input chưa authenticated.
- [ ] Không dùng trace ID/exception.message làm label.
- [ ] Cấu hình `Gauge`/histogram buckets có memory/series budget.
- [ ] Metrics endpoint có network/authz protections phù hợp.
- [ ] Logs/traces có correlation ID nhưng không chứa replayable signed request.
- [ ] Forensic client drill-down dùng privileged audit access và retention policy.
- [ ] Không tạo negative-cache/metrics state vô hạn vì random key ID flood.

### 25.4. Dashboard, SLO và alerts

- [ ] Dashboard hiển thị NEW, REPLAY, UNKNOWN counts/rates.
- [ ] Replay share loại UNKNOWN khỏi **decided** denominator và gắn nhãn rõ.
- [ ] Unknown share đo riêng replay authority reliability.
- [ ] Store claim duration và inflight có units chính xác.
- [ ] HTTP 401/403/5xx, freshness, MAC mismatch và key policy metrics được hiển thị riêng.
- [ ] Redis evictions, memory, failovers, connection/replication health có panels.
- [ ] Gateway retry/timeout signals có thể correlate với replay spike.
- [ ] Business idempotency/operation metrics không bị đánh đồng với anti-replay.
- [ ] Alert replay ratio có volume gate và baseline theo route.
- [ ] Alert UNKNOWN ưu tiên fail-closed availability và có runbook.
- [ ] Metrics missing/scrape down có alert riêng, không render thành “0 replay tốt”.
- [ ] Không diễn giải replay spike là chứng cứ duy nhất của attack/secret compromise.
- [ ] SLO availability và anti-replay security guarantee được phân biệt.

### 25.5. Code và test coverage

- [ ] Một component chịu trách nhiệm duy nhất cho replay claim metric.
- [ ] Java17 Micrometer tests dùng `SimpleMeterRegistry` cho NEW/REPLAY/UNKNOWN.
- [ ] Timer đo monotonic elapsed time; không dùng client timestamp làm duration.
- [ ] Gauge inflight được decrement trong `finally`.
- [ ] Không sinh meter mới theo raw key/nonce mỗi request.
- [ ] Metrics recording failure không thể tạo security bypass.
- [ ] Test invalid MAC/stale timestamp không gọi replay store.
- [ ] Test nonce NEW rồi REPLAY cho cùng namespace.
- [ ] Test UNKNOWN/timeout không tạo principal và không vào business.
- [ ] Test concurrent requests qua fake store rồi qua Redis/multi-pod thật.
- [ ] Test TTL bound và early expiry/eviction/failover behavior.
- [ ] Test gateway signed retries, client new-nonce retry và business idempotency.
- [ ] Test Spring MVC filter order/duplicate registration hoặc WebFlux subscription lifecycle.
- [ ] Test Prometheus metric names, labels, rule expressions và scrape health.
- [ ] Incident drill không gửi signed production secrets hoặc replay sensitive requests.

## 26. Câu hỏi tự kiểm tra

1. **Metric replay đo gì?** Những nonce claims được authority xác định là duplicate, cùng các outcome/health liên quan.
2. **HMAC đúng có tự ngăn replay không?** Không, phải có freshness và shared nonce admission.
3. **Khi nào ghi REPLAY?** Sau full MAC/freshness pass, store trả authoritative duplicate.
4. **Bad MAC có làm replay counter tăng không?** Không, không claim nonce.
5. **Timestamp stale có được coi là replay không?** Không; đó là freshness reject.
6. **UNKNOWN nghĩa là gì?** Không có kết luận chắc từ store; phải fail closed.
7. **Có được coi UNKNOWN là NEW khi cần availability không?** Không.
8. **NEW nghĩa là order đã commit chưa?** Chưa, chỉ nonce admission.
9. **Replay detected có đồng nghĩa hacker có secret không?** Không; replay một signed request không cần biết secret, retries cũng tạo duplicates.
10. **Secret bị lộ nhưng attacker ký nonce mới có làm REPLAY tăng không?** Không nhất thiết.
11. **Tại sao không dùng mọi 401 làm replay count?** 401 gồm nhiều authentication failures.
12. **Công thức replay share decided là gì?** REPLAY/(NEW+REPLAY) trong cùng scope/window.
13. **UNKNOWN nên ở đâu trong SLI?** Phần authority decision uncertainty, denominator availability gồm NEW+REPLAY+UNKNOWN.
14. **`rate` trả gì?** Events/second cho cumulative counter.
15. **`increase` trả gì?** Ước lượng số counter increments trong window, có xử lý resets.
16. **Vì sao ratio cần volume gate?** Traffic nhỏ làm tỷ lệ biến động lớn.
17. **Metric cardinality là gì?** Số series từ tổ hợp metric name+labels.
18. **Nonce có nên là label không?** Không, unbounded và có rủi ro security/privacy.
19. **Raw URI có nên làm route label không?** Không; dùng server-defined route template/family.
20. **Có nên gắn unknown keyId thành Prometheus label?** Không, attacker tự tạo vô hạn IDs.
21. **Timer `_sum / _count` là p95 không?** Không, đó là mean.
22. **Khi nào `histogram_quantile` hợp lệ?** Khi exporter thực sự phát histogram buckets.
23. **Counter có thể reset sau restart không?** Có; PromQL rate/increase xử lý theo scrape history.
24. **Metric hoàn toàn missing có nghĩa zero replay không?** Không, cần scrape/ingestion health.
25. **Hai pods local nonce maps có gì sai?** Cùng nonce có thể NEW ở cả hai.
26. **SET NX EX bảo vệ gì?** Atomic conditional insert và expiry tại authority phù hợp.
27. **Redis async failover có thể làm gì?** Mất nonce record và tạo false second NEW.
28. **TTL bao phủ gì?** Cả past-age acceptance và future-skew window cộng margin.
29. **Eviction khiến replay metric thay đổi thế nào?** Có thể gây false NEW mà REPLAY không tăng.
30. **Gateway timeout có thể làm REPLAY tăng không?** Có, nếu retry nguyên signed nonce.
31. **Retry nonce mới với cùng orderId có phải replay nonce không?** Không, nhưng có thể duplicate business operation.
32. **Nên instrument trong controller không?** Không, bị replay reject trước controller.
33. **Reactive WebFlux có nên tự subscribe nonce publisher không?** Không, compose vào security pipeline.
34. **Làm sao test recorder mà không chạy Prometheus?** Micrometer `SimpleMeterRegistry`.
35. **100 calls cùng nonce trên một atomic authority kỳ vọng gì?** At most one NEW; còn lại REPLAY/UNKNOWN theo outcomes thực.
36. **Store outage có được làm authentication bypass không?** Không, fail closed.
37. **HMAC success nhưng thiếu tenant grant được tính thế nào?** Nonce có thể NEW, authorization deny metric riêng.
38. **Một replay spike nên tự revoke key ngay không?** Không; kiểm retries, traffic và compromise indicators trước theo runbook.
39. **SLO decision availability có chứng minh anti-replay security không?** Không; false NEW do failover/eviction vẫn có thể xảy ra.
40. **Bài học quan trọng nhất?** Đo chính xác authoritative nonce decisions, không biến quan sát thành quyền, và đối chiếu replay metrics với hạ tầng/retry/business trước khi kết luận.

## 27. Tài liệu tham khảo và hướng đọc thêm

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Nền tảng HMAC, sự khác biệt giữa message integrity và replay detection.
- **RFC 4231 — HMAC-SHA-224/256/384/512 Test Vectors.** Known-answer tests cho primitive.
- **RFC 9110 — HTTP Semantics.** HTTP request methods, authentication và error responses.
- **RFC 9112 / RFC 9113 — HTTP/1.1 và HTTP/2.** Proxy, headers, framing và retry/conversion behavior.
- **RFC 3986 — Uniform Resource Identifier Generic Syntax.** Canonical URI/path/query signing boundaries.
- **Micrometer Reference — Counters, Timers, Gauges và MeterRegistry.** In-process measurements và lifecycle.
- **Micrometer Prometheus Registry documentation.** Exported metric names, tags, units và scraping.
- **Prometheus documentation — Querying, rate/increase, histogram_quantile, recording/alerting rules.** Phân tích cumulative counters và alerts.
- **Prometheus best practices — Metric and label naming, instrumentation, alerting.** Cardinality/operational hygiene.
- **Grafana documentation — Dashboards, variables và alerts.** Visualization/alert workflow.
- **Redis command reference — SET NX EX, key expiration, eviction, persistence/replication.** Atomic nonce operations và giới hạn durable failover.
- **Spring Security Reference — Servlet Filters và Reactive WebFlux Authentication.** Đặt replay instrumentation đúng security boundary.
- **Reactor Reference — Mono/Flux, cancellation, doFinally, Context và StepVerifier.** Reactive lifecycle và đo outcomes.
- **Java SE 17 — SecureRandom, Clock, Instant và System.nanoTime.** Random nonce/time/latency primitives.
- **OWASP API Security, Authentication và Secrets Management guidance.** Key rotation, replay threat model, audit/log hygiene và authorization.

## 28. Kết luận

**Metric replay không phải chỉ là một bộ đếm HTTP 401.** Nó là một hợp đồng quan sát rõ về **atomic nonce claim** sau HMAC verification và timestamp freshness: `NEW` cho nonce được admit lần đầu, `REPLAY` cho duplicate được xác định và `UNKNOWN` cho kết quả không chắc khi authority lỗi. Cả ba cần được đo riêng bằng counters/timers có labels ít giá trị, không rò secret, key ID, nonce hoặc replayable request.

Một dashboard đúng phải kết hợp replay share với **số lượng quyết định**, unknown share/latency, HTTP error metrics, clock/credential failures, gateway retries, Redis eviction/failover và business idempotency. Replay spike có thể là retry hợp pháp hoặc abuse; replay count thấp không chứng minh không có replay gap. **Không bao giờ đổi UNKNOWN thành NEW để “giữ availability”**: nếu nonce authority không quyết định được, hệ thống phải fail closed theo chính sách đã thiết kế.

Khi dùng Java 17/Micrometer, đặt instrumentation tại đúng replay claim boundary, pre-register bounded labels, kiểm bằng `SimpleMeterRegistry`/JUnit 5, rồi test thật multi-node/gateway/failover. Mục tiêu cuối cùng là vừa có **security evidence đáng tin**, vừa có signals để vận hành sửa đúng root cause mà không làm yếu HMAC authentication, authorization hoặc business integrity.





