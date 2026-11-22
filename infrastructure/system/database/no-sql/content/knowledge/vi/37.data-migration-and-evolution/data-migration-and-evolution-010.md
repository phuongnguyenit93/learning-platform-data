# Chạy đối chiếu truy vấn giữa hai mô hình mà không gây tác dụng phụ

## 1. Bối cảnh: di chuyển dữ liệu nhưng chưa được phép đổi kết quả trả cho người dùng

Một ứng dụng Java lưu đơn hàng trong MongoDB. Mô hình hiện tại nhúng danh sách sản phẩm trực tiếp vào document đơn hàng; mô hình mới tách order header và order items để phục vụ truy vấn khác hiệu quả hơn.

~~~text
Mô hình cũ:
orders
  _id = O101
  tenantId = T17
  status = CONFIRMED
  items = [{sku: P1, qty: 2}, {sku: P2, qty: 1}]

Mô hình mới:
order_headers
  orderId = O101, tenantId = T17, status = CONFIRMED

order_items
  (orderId=O101, lineNo=1, sku=P1, qty=2)
  (orderId=O101, lineNo=2, sku=P2, qty=1)
~~~

Nhóm phát triển đã backfill dữ liệu lịch sử, bật pipeline đồng bộ thay đổi và muốn kiểm chứng rằng truy vấn mới trả về cùng ý nghĩa nghiệp vụ. Nhưng chưa thể thay ngay production GET /orders/O101 vì một sai lệch ở trạng thái, tổng tiền hoặc tenant isolation có thể ảnh hưởng người dùng.

Giải pháp thường dùng là **shadow query / differential read**:

1. GET hiện tại vẫn truy vấn mô hình cũ và trả kết quả cho người dùng.
2. Một luồng đối chiếu riêng truy vấn mô hình mới trên cùng ý định đọc, trong giới hạn tải cho phép.
3. Kết quả hai phía được chuẩn hóa theo cùng hợp đồng nghiệp vụ rồi so sánh.
4. Kết quả đối chiếu được ghi vào telemetry an toàn, **không thay đổi response và không thực hiện side effects**.
5. Chỉ khi đạt tiêu chí đã định mới chuyển một phần read traffic sang mô hình mới.

Một yêu cầu quan trọng: **Không được hiểu “chỉ đọc” theo nghĩa hẹp là gọi HTTP GET hay database find**. Nếu request shadow vô tình gửi email, ghi cache, update lastViewedAt, tính phí, phát audit event chứa dữ liệu nhạy cảm, gọi stored function hoặc gây read repair nặng, quá trình kiểm chứng có thể tự làm thay đổi hệ thống đang đo.

Bài nằm trong module **Database No SQL**, chương **Di chuyển và thay đổi**, tập trung vào cách chạy đối chiếu giữa hai mô hình an toàn, giải thích divergence đúng nguyên nhân và dùng bằng chứng để quyết định cutover.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Phân biệt shadow read, traffic replay, dual read, dark launch, canary read và dual write.
- Xây hợp đồng query comparison gồm input, semantics, consistency, projection, sort, pagination và error handling.
- Thiết kế **non-interference boundary** để shadow queries không thay đổi dữ liệu hoặc response của user.
- Đảm bảo dữ liệu hai mô hình ở các mốc đủ tương đương trước khi tính sai lệch.
- Chuẩn hóa document shape, null/missing, numeric precision, timestamps, thứ tự phần tử và duplicate rows.
- Thiết kế Java shadow-query executor có bounded concurrency, timeout, sampling, circuit breaker và không ảnh hưởng đường trả response.
- Đo match/mismatch/inconclusive bằng mẫu số phù hợp và tránh coi eventual lag là lỗi migration.
- Dùng read-only identities, network policy, audit và kiểm thử có chủ đích để chặn side effects.
- Phân tích các tình huống trên MongoDB, DynamoDB, Cassandra, Redis và search read models.
- Lập cutover gates, rollback và runbook khi phát hiện kết quả khác nhau.

## 2. Trước tiên phải định nghĩa “hai mô hình”

Hai mô hình có thể là:

| Tình huống | Mô hình A | Mô hình B | Điều muốn kiểm chứng |
|---|---|---|---|
| Denormalization | Orders embedded items | Header + items | Đơn hàng và items đúng |
| Partition-key migration | tenantId/orderId | tenantId/bucket/orderId | Lookup và range query đúng |
| MongoDB → DynamoDB | Document với secondary indexes | Access patterns theo PK/SK/GSI | Query contract đúng |
| Cassandra table redesign | Partition rộng | Partition bucketing | Trang kết quả không thiếu/trùng |
| Search migration | Elasticsearch index v1 | OpenSearch/index v2 | Filters, sort, aggregation tương đương |
| Cache redesign | Redis key schema v1 | Redis key schema v2 | Dữ liệu và TTL semantics chấp nhận |
| Schema evolution | status string, cents int | status enum, Decimal128 | Giá trị nghiệp vụ sau mapping đúng |
| Materialized projection | Source collection | CDC-built read model | Projection cuối cùng hội tụ đúng |

### 2.1. So sánh mô hình không có nghĩa so raw bytes

Document A có trường items nhúng; B có hai bảng. Byte-level equality không thể đạt dù chúng biểu diễn cùng đơn hàng. Cần một **canonical business view** để cả hai trả về giá trị tương đương.

### 2.2. So sánh cũng không nhất thiết yêu cầu identical latency

Một truy vấn cũ mất 40 ms, mới mất 55 ms nhưng trả cùng dữ liệu: semantic match. Performance là một dimension khác, cần quan sát riêng.

### 2.3. Mô hình B có thể cố ý khác hợp đồng

Nếu chuyển từ “mọi items” sang “chỉ active items”, một mismatch có thể là **intentional semantic change**, không phải bug. Phải ghi version của contract và tiêu chí so sánh đúng trước khi chạy.

### 2.4. Không thể giả định dữ liệu đã đồng bộ

Mô hình B có thể nhận CDC trễ 3 giây. Khi A đã lên version 12 nhưng B vẫn version 11, kết quả khác nhau không đủ chứng minh mapper sai. Đây là một loại inconclusive hoặc expected lag tùy test policy.

## 3. Shadow read, dual read, replay và canary khác nhau thế nào?

| Cách | Response cho user lấy từ đâu? | Có dùng kết quả B để quyết định response? | Rủi ro chính |
|---|---|---|---|
| Shadow read | A (baseline) | Không | Tải, privacy, side effects ngoài ý muốn |
| Dual read và compare đồng bộ | A hoặc logic đã thiết kế | Có thể | Tăng latency và dependency B |
| Traffic replay | Không thuộc request live hoặc chạy offline | Không | Replay operation không thuần đọc |
| Canary read | B cho một tỷ lệ user | Có | User có thể thấy lỗi mới |
| Dark launch B | A vẫn là authority | Không | Ngốn tài nguyên B và dependencies |
| Dual write | Một mutation ghi A và B | N/A | Side effects trùng, consistency giữa writes |

### 3.1. Shadow read nên tách đường chính

Nếu B timeout, API vẫn có thể trả kết quả A trong latency budget hiện tại. B timeout được ghi vào hệ đo, không biến thành HTTP 500 của user.

### 3.2. Dual read có thể nằm trên critical path

Nếu code đợi cả A lẫn B trước khi trả response, B trở thành dependency availability/latency. Đây không còn là non-intrusive shadow read.

### 3.3. Traffic replay cần lọc theo semantics

Không replay POST /checkout, DELETE /orders hoặc API GET có side effect chỉ vì HTTP verb là GET. Dùng trace đầu vào đã lọc cho **query command đã chứng minh chỉ đọc**.

### 3.4. Canary là giai đoạn sau

Shadow results giúp tìm lỗi trước canary; nhưng không thể chứng minh hoàn toàn canary behavior khi B trở thành response authority, nhất là timeout handling và user-specific caches. Cần canary thật với rollback.

## 4. Mục tiêu non-interference: shadow không làm thay đổi nghiệp vụ chính

Gọi A là đường chính, B là đường đối chiếu. Với một request r, xét hai lần chạy:

- **Without shadow:** chỉ có A.
- **With shadow:** A trả response như thường, B chạy ở nhánh tách biệt.

Một mục tiêu an toàn là kết quả và những tác động nghiệp vụ mà user thấy ở đường A **không khác do có B**:

\[
\operatorname{UserOutcome}(A,r,\text{shadow on})
\approx
\operatorname{UserOutcome}(A,r,\text{shadow off})
\]

Ký hiệu gần đúng vì B có thể gây thêm tiêu thụ CPU/network/cache hoặc observability. Ta không thể khẳng định hệ vật lý hoàn toàn không thay đổi; mục tiêu là **không tạo tác dụng phụ nghiệp vụ và không ảnh hưởng đáng kể tới SLO của A**.

### 4.1. Không mutate authoritative data

Không chạy INSERT/UPDATE/DELETE, stored procedure hay function có ghi như một phần compare; chỉ dùng documented read operations trên B.

### 4.2. Không phát side effect ngoài DB

Không gọi Payment Provider, email, analytics event, queue producer, webhook, audit event có ý nghĩa nghiệp vụ hoặc billing khi mirror request.

### 4.3. Không tác động response

Shadow mismatch, exception hoặc timeout không được sửa body/status/headers mà user nhận từ A. Quyết định chặn cutover nằm trong hệ monitoring/operations, không trong response lúc shadow.

### 4.4. Không làm A bị đói tài nguyên

Bounded concurrency, low priority, connection pool riêng và load shedding để tránh B ăn hết threads, CPU, network hay connection pool của A.

### 4.5. Có thể có side effect vật lý khó loại bỏ

Read query có thể làm nóng cache, tăng LRU counter, kích hoạt read repair, metrics/tracing hoặc tăng billed read capacity. Phân biệt **business side effect phải chặn tuyệt đối** với **operational side effect phải đo, giới hạn và chấp nhận có chủ đích**.

## 5. Sơ đồ kiến trúc shadow query

~~~mermaid
flowchart TD
    U["User GET /orders/O101"] --> API["Java API"]
    API --> A["Read A - authoritative model"]
    A --> RESP["Return response A to user"]
    API -. "sampled request metadata" .-> Q["Bounded shadow queue"]
    Q --> GUARD["Read-only policy + query compiler"]
    GUARD --> B["Read B - candidate model"]
    A -. "safe canonical view" .-> COMP["Comparator"]
    B --> COMP
    COMP --> METRIC["Metrics / safe mismatch samples"]
    B -. "timeout/error" .-> METRIC
    METRIC --> OPS["Migration dashboard and cutover gates"]
~~~

### 5.1. Quan hệ response

Response A được trả độc lập với việc B đã xong hay chưa. Nếu A thất bại, shadow B không tự ý “cứu request” trong giai đoạn baseline trừ khi dự án **có một yêu cầu fallback được duyệt riêng**.

### 5.2. Dữ liệu mang sang nhánh shadow

Chỉ truyền query intent cần thiết, context xác thực đã kiểm soát, tenant scope và correlation token. Không copy nguyên HTTP headers (Authorization/cookies), request body hay session tokens vào queue.

### 5.3. Kết quả A cần giữ bao lâu?

Để so sánh async, có thể giữ một canonical projection nhỏ với TTL ngắn hoặc dùng join-by-correlation trong hệ có memory bounds. Không đẩy toàn bộ PII/response dài hạn sang log chỉ để compare.

### 5.4. Tách trách nhiệm

Một worker có thể chuyên query B; một comparator xử lý canonical views; metrics aggregator tổng hợp. Việc tách giúp B failure không lan trực tiếp tới A.

## 6. Những side effects ẩn trong lệnh tưởng là đọc

| Đường đi | Side effect có thể có | Biện pháp |
|---|---|---|
| API GET /order | Update lastViewedAt | Dùng data-access read trực tiếp, không gọi full controller handler |
| ORM/repository callback | Save audit access record | Tắt callback side-effecting trong shadow executor |
| Cache-aside | Set Redis cache/miss marker | Shadow mode bypass cache writes hoặc cache riêng |
| Search endpoint | Emit analytics impression | Gọi search read API không trigger tracking |
| DynamoDB/managed NoSQL | Tốn read capacity/billing | Rate limit, cost budget, tags |
| Cassandra read | Read repair/compaction pressure | Theo dõi cluster metrics, read-only role không ngăn internal maintenance |
| Redis GET | Update LRU/LFU metadata, lazy expiry | Chấp nhận operational effect trong giới hạn, không coi là zero-effect tuyệt đối |
| Data loader | Materialize missing records | Chặn create-on-read hoặc seed-on-miss |
| GraphQL resolver | N+1 hoặc downstream calls | Query plan allowlist, reject effects |
| Signed URL / authentication | Token refresh | Không gọi identity flow từ shadow context |
| Debug/audit middleware | Log full payload/PII | Schema allowlist, safe audit |

### 6.1. Read-only role là điều kiện cần, không đủ

DB role chỉ chặn các mutations mà role không được phép. Nó không chặn ứng dụng gọi Kafka, ghi Redis cache qua credential khác hoặc gửi email sau truy vấn.

### 6.2. HTTP GET không chứng minh pure read

Một endpoint GET có thể sửa lastAccessAt hoặc tạo recommendation impression. Muốn so sánh, gọi query port được thiết kế **pure**, không mirror toàn HTTP request một cách mù quáng.

### 6.3. GET có thể tốn tài nguyên và làm thay đổi hiệu năng

Đối chiếu hàng triệu queries song song có thể làm B chậm rồi lan sang A nếu dùng chung hạ tầng. Cần quotas, budgets, per-tenant sampling và circuit breaking.

## 7. Quy tắc “read-only từ đầu đến cuối”

Một shadow path được coi là phù hợp khi mọi thành phần trên đường đi đã được xác nhận:

~~~text
Input acquisition -> only permitted metadata
Query compilation -> allowlisted read operation
DB access -> read-only identity / endpoint
Enrichment -> pure computations, no outbound side effects
Comparison -> in-memory normalized values
Telemetry -> aggregates / redacted samples
Error handling -> log category, never mutate source
~~~

### 7.1. Tài khoản chuyên biệt

Identity của shadow executor chỉ được phép SELECT/GET/Query/find/read trên B theo mức engine hỗ trợ; không cấp admin, PutItem, UpdateItem, delete, index management hay execution quyền cao.

### 7.2. Network egress

Một worker chuyên compare có thể được hạn chế network chỉ tới read target và observability sink; không route đến payment, SMTP hoặc mutation APIs.

### 7.3. Query allowlist

Không nhận raw query string từ người dùng rồi tự mirror. Chỉ mirror các query templates được review như getOrderById, listOrdersByTenant hoặc searchProductsByFilter.

### 7.4. Kill switch

Cần một flag tắt shadow nhanh mà không thay đường trả lời A. Khi B overload hoặc có unexpected side effects, tắt ngay.

### 7.5. Audit và xác minh

Log safe metadata về các query classes đã chạy, phiên bản comparator, sampling policy và query counts; không cần ghi dữ liệu nhạy cảm nguyên văn.

## 8. Bắt đầu từ một hợp đồng truy vấn, không bắt đầu từ code SQL/NoSQL

Một truy vấn nghiệp vụ được định nghĩa:

~~~yaml
queryId: orders.getById.v2
input:
  tenantId: required
  orderId: required
semantics:
  includesCancelled: true
  missingOrder: NOT_FOUND
  itemsOrdering: lineNoAscending
output:
  fields:
    - orderId
    - tenantId
    - status
    - items
    - totalMinor
comparison:
  ignore:
    - internalDocumentVersion
    - migrationTrace
  numericPolicy: exactIntegerMinorUnits
  stalePolicy: requireComparableSourceVersion
~~~

Đây là YAML mô tả **contract do dự án định nghĩa**, không phải schema mặc định của MongoDB/DynamoDB.

### 8.1. Input phải bao gồm security scope

OrderId không đủ nếu tenants có ID giống nhau. Cả A và B phải lọc tenantId và thực thi authorization ở tầng đã định nghĩa.

### 8.2. Output là business view

A trả embedded items, B join header+items; comparator chỉ cần so canonical OrderView, không so raw documents.

### 8.3. Contract có version

Nếu định nghĩa trạng thái CANCELLED thay đổi, lưu queryId/contractVersion để metrics trước và sau không bị diễn giải như cùng một phép kiểm chứng.

### 8.4. So sánh query semantics, không so implementation

A có thể dùng MongoDB find; B dùng DynamoDB Query rồi hydrate items. Kết quả cùng hợp đồng mới là tiêu chí.

## 9. Chọn truy vấn nào được mirror?

Ưu tiên:

1. **Point lookup:** đọc theo key; dễ xác minh thiếu/sai record.
2. **Range query:** truy vấn một tenant và khoảng thời gian; cần sort/pagination.
3. **Filter query:** theo status/category; cần đúng selectivity và index paths.
4. **Aggregate query:** count, sum, grouped totals; cần hiểu precision, thời gian và eventual updates.
5. **Search query:** tokenization, ranking và refresh semantics; thường không bit-for-bit.
6. **Negative lookup:** key không tồn tại; rất hữu ích để phát hiện B tạo thừa record hoặc sai tenant scope.

### 9.1. Không chỉ mirror happy path

Một migration có thể trả đúng 99% hot orders nhưng sai các orders có zero items, cancelled status, legacy schema hoặc tenants lớn. Sampling phải cover các nhóm này.

### 9.2. Query shape quan trọng

Point GET trả 1 row và list query trả 10.000 rows khác nhau về tải, pagination và điều kiện so sánh.

### 9.3. Không query toàn table chỉ để compare từng request

Một shadow query phải đi qua access pattern được thiết kế. Nếu B thiếu index và buộc full scan, skip/report UNCOMPARABLE_PLAN hoặc giới hạn staging; không đốt capacity production để lấy một con số match.

## 10. Baseline, candidate và nguồn dữ liệu có thẩm quyền

Trong giai đoạn mirror:

~~~text
Model A: current read authority.
Model B: candidate under validation.
Backfill/CDC: keeps B updated from A or common event source.
Comparator: judges semantic equivalence under specified consistency.
~~~

### 10.1. A không phải chân lý tuyệt đối về nghiệp vụ

Nếu A vốn có bug và B sửa bug có chủ ý, kết quả khác không mặc nhiên là B sai. Cần owner phân loại divergence, dùng invariant/spec và ghi known differences.

### 10.2. Không để comparator sửa data

Comparator đọc và báo. Việc tự động repair dữ liệu B là một **migration writer workflow riêng** có quyền, audit và kiểm thử; không lén gọi repair trong nhánh shadow.

### 10.3. Chưa đủ dữ liệu không có nghĩa mismatch

Trong lúc backfill chưa tới tenant T17 hoặc CDC đang lag, đánh dấu NOT_READY/INCONCLUSIVE thay vì ghi B sai.

### 10.4. Có cutover gates trước khi đưa B làm authority

Chỉ số match cần đi cùng coverage, error/latency, consistency, security và rollback readiness. Một overall 99,9% match không đủ nếu 0,1% sai tập trung ở payments hoặc một tenant lớn.

## 11. Đồng bộ dữ liệu trước khi so sánh: backfill và CDC

Hai mô hình thường được duy trì bởi:

~~~text
             Historical backfill
Model A ------------------------------> Model B
    |
    +---- CDC / change stream / outbox --> Model B

Live writes continue on Model A.
~~~

### 11.1. Backfill chưa xong

Nếu B chưa chứa dữ liệu từ một partition, mọi query trên partition đó đều có thể trả NOT_FOUND. Không tính các case này vào tỷ lệ semantic mismatch của mô hình; báo BACKFILL_NOT_READY riêng.

### 11.2. Khoảng trống giữa snapshot và CDC

Backfill đọc trạng thái tại t0 nhưng CDC bắt đầu từ t0+5 phút có thể bỏ sót writes trong khoảng đó. Cần capture/replay log từ checkpoint phù hợp trước khi công bố B đã cover dữ liệu.

### 11.3. Backfill có thể ghi đè CDC mới

Ví dụ A Order O101 đã lên version 8; CDC cập nhật B lên v8. Một backfill worker chậm đọc snapshot v6 rồi ghi đè B về v6. Bảng B sau đó có divergence kéo dài. Dùng version-aware conditional apply, idempotency và ordering; comparator không được tự sửa lỗi.

### 11.4. CDC có thể gửi lặp hoặc đến muộn

At-least-once delivery, retries và failover có thể phát duplicate events. Projection B phải xử lý eventId, entityVersion/source sequence, chống stale overwrites.

### 11.5. Theo dõi readiness theo phạm vi

~~~text
backfill_coverage_by_partition
oldest_unprocessed_cdc_age_seconds
source_checkpoint
candidate_applied_checkpoint
candidate_entity_version
~~~

Một tỷ lệ hoàn tất chung 99% có thể che đúng 1% phân vùng enterprise trọng yếu chưa backfill.

## 12. Không thể so hai trạng thái ở hai thời điểm khác nhau như thể cùng một snapshot

Một race:

~~~text
10:00:00.000  Query A returns Order O101 version=7.
10:00:00.050  A writer commits version=8.
10:00:00.080  CDC applies v8 to B.
10:00:00.100  Shadow query B returns version=8.
~~~

A và B đều đúng tại thời điểm chúng được hỏi, nhưng raw data khác.

### 12.1. So sánh tại một mốc logic

Lý tưởng: hai reads cùng snapshot/commit watermark (nếu engine/architecture hỗ trợ), hoặc logic cho phép truy xuất đúng historical version.

### 12.2. Nếu không có snapshot chung

Sử dụng entityVersion, source offset, applied watermark và một quy tắc **eligibility**: chỉ gọi semantic mismatch khi đã đủ bằng chứng hai trạng thái có thể so sánh.

### 12.3. Đợi convergence có giới hạn

Một phương án cho validation không nằm trên request critical path là trì hoãn compare cho tới khi B đã bắt kịp source version đã quan sát, nhưng việc chờ cần bounded deadline và không được đẩy load vô hạn.

### 12.4. Source tiếp tục thay đổi

Ngay cả khi B đạt v7, A có thể lên v9. Việc nhìn B v7 và A hiện v9 không nói B sai; comparator cần giữ reference result/version A tại thời điểm đầu hoặc đọc historical snapshot được hỗ trợ.

### 12.5. Không tự giả định timestamp đồng bộ

Wall-clock times khác nhau trên services không là một distributed consistent snapshot. Prefer source-assigned version/sequence/commit token đủ mạnh theo phạm vi.

## 13. Các lớp consistency và cách diễn giải divergence

| Tình huống | A | B | Kết luận phù hợp |
|---|---|---|---|
| Cùng sourceVersion v8, khác status | CONFIRMED | CANCELLED | Semantic mismatch cần điều tra |
| B version v7 khi A v8 | CONFIRMED | PENDING | STALE / INCONCLUSIVE tùy contract |
| B chưa backfill partition | FOUND | NOT_FOUND | NOT_READY |
| B version v8, A version v7 do race | PENDING | CONFIRMED | RACE / INCOMPARABLE |
| Cùng version, khác thứ tự của set | [A,B] | [B,A] | MATCH nếu contract là set |
| Cùng version, page thiếu một item | [A,B] | [A] | MISMATCH nếu cùng page contract |
| B timeout | FOUND | error | CANDIDATE_ERROR, không gọi data mismatch |
| A timeout, B FOUND | error | FOUND | BASELINE_ERROR, không thể so response pair như bình thường |
| Cả hai NOT_FOUND, cùng scope | NOT_FOUND | NOT_FOUND | MATCH theo hợp đồng |

### 13.1. Read concern/consistency cấu hình phải được ghi nhận

MongoDB read preference/concern, DynamoDB eventually/strongly consistent read nơi được hỗ trợ, Cassandra consistency level và search refresh có thể làm dữ liệu quan sát khác nhau. Không so “kết quả A strong” với “B eventual” rồi cho rằng mọi khác biệt là bug.

### 13.2. Consistency policy là một phần query contract

Ví dụ listProducts cho phép stale 5s nhưng getPaymentStatus yêu cầu consistency chặt chẽ hơn. Chọn policy theo tác động nghiệp vụ, không dùng một ngưỡng cho mọi query.

### 13.3. Không masking mismatch vô hạn

Nếu B luôn lag, đánh dấu INCONCLUSIVE mãi sẽ tạo dashboard đẹp giả tạo. Theo dõi stale age và inconclusive ratio, đặt freshness SLO và ngưỡng investigation riêng.

## 14. Chuẩn hóa response: so nghĩa, không so cách lưu

Một canonical business projection:

~~~json
{
  "tenantId": "T17",
  "orderId": "O101",
  "status": "CONFIRMED",
  "totalMinor": 125000,
  "currency": "VND",
  "items": [
    {"lineNo": 1, "sku": "P1", "qty": 2},
    {"lineNo": 2, "sku": "P2", "qty": 1}
  ],
  "sourceVersion": 8
}
~~~

### 14.1. Không include storage-only metadata vào equality

MongoDB ObjectId, DynamoDB PK/SK prefix, Cassandra write timestamp, Kafka offset, migrationBatchId hoặc cache serializerVersion có thể khác hợp lệ.

### 14.2. Nhưng không ignore business fields sai

Không bỏ qua totalMinor, status, tenantId, currency chỉ để tăng match rate. Mỗi ignored field phải có lý do, chủ sở hữu và contract version.

### 14.3. Canonicalization có thể gây lỗi mới

Nếu normalizer biến cả giá trị sai và đúng thành cùng null/default, comparator sẽ bỏ sót bug. Cần ghi explicit MISSING, NULL và INVALID để không làm mất thông tin nghiệp vụ.

### 14.4. Compare một canonical type có phiên bản

Hai adapters A/B mỗi bên chuyển output sang cùng CanonicalOrderV2. Comparator không phụ thuộc internal storage schema, nhưng mappers cần được unit test bằng fixtures và invariants.

### 14.5. Hợp đồng canonical có thể có field-level policies

~~~text
tenantId       exact
orderId        exact
status         mapped-enum-exact
totalMinor     exact integer
updatedAt      version-aware canonical instant
items          ordered by lineNo
tags           set equality
metadata       ignore if storage-only
~~~

## 15. Null, missing, empty và default values

Trong NoSQL, một document có thể thiếu field hoàn toàn:

~~~json
{"orderId":"O101"}
~~~

khác với:

~~~json
{"orderId":"O101","couponCode":null}
~~~

và khác:

~~~json
{"orderId":"O101","couponCode":""}
~~~

### 15.1. Có thể tương đương, nhưng phải được định nghĩa

Nếu nghiệp vụ coi missing/null là “không có mã giảm giá”, contract có thể normalize cả hai thành Optional.empty. Nhưng empty string có thể là input invalid chứ không tự tương đương.

### 15.2. Không mặc định missing numeric = 0

Thiếu totalMinor có thể là dữ liệu chưa migrate; biến missing thành 0 che mất lỗi nghiêm trọng.

### 15.3. Trường boolean

Missing paid=false khác việc paid=null chưa biết kết quả payment. Chỉ áp default nếu schema contract khẳng định điều đó.

### 15.4. Arrays

items missing, items=null và items=[] có thể mang ý nghĩa khác nhau. Nếu canonical contract coi “không có item” là empty list, phải xác minh invariant liên quan.

### 15.5. Field-level mismatch classification

~~~text
FIELD_MISSING
EXTRA_FIELD
NULL_MISMATCH
DEFAULT_VALUE_MISMATCH
INVALID_ENUM
TYPE_MISMATCH
~~~

Đếm theo loại lỗi giúp phân biệt mapper bug với backfill lag.

## 16. Thứ tự: list, set hay multiset?

Hai kết quả:

~~~text
A: [P1, P2, P2]
B: [P2, P1, P2]
~~~

Nếu output là **ordered list**, thứ tự khác → mismatch. Nếu là **multiset** (cho phép duplicate, không quan trọng thứ tự), hai kết quả tương đương. Nếu là **set**, chỉ quan tâm {P1,P2}; tuy nhiên việc bỏ duplicates có thể làm mất một vi phạm unique invariant.

### 16.1. Không sort bừa trước khi compare

Order items theo lineNo là có thứ tự nghiệp vụ. Sort theo sku có thể che bug line order. Chọn policy theo query semantics.

### 16.2. Query không ORDER BY có thể không bảo đảm thứ tự

MongoDB find, DynamoDB Query, Cassandra partition order và search results có các quy tắc sắp xếp khác nhau. Nếu API cần stable order, contract phải định nghĩa sort keys/tie-breakers rõ.

### 16.3. Stable tie-break

Sort theo createdAt có thể có nhiều records cùng timestamp. Bổ sung orderId làm tie-break giúp pagination nhất quán, nếu business contract cho phép.

### 16.4. Duplicates phải được đo

Projection B có thể tạo duplicate rows từ join hoặc CDC replay. Nếu adapter dùng toSet() trước compare, bug bị che. Đếm duplicate keys riêng trước khi set-based comparison.

### 16.5. Range query cần window rõ ràng

Theo thời gian [start,end) hay [start,end]? Nếu A dùng inclusive end và B exclusive end, chỉ một số boundary records lệch. Contract phải nhất quán.

## 17. Numeric precision, type conversion và currency

Một ví dụ:

~~~text
A.totalMinor = 125000 (int64)
B.total = Decimal128("125000") currency=VND
~~~

Hai giá trị chỉ tương đương nếu contract xác định chúng đều là đơn vị VND như nhau. Không tự chia 100 hoặc chuyển minor/major units theo một giả định áp dụng cho mọi đồng tiền.

### 17.1. Tránh so tiền bằng double epsilon tùy tiện

Nếu dữ liệu là tiền, dùng integer minor units hoặc BigDecimal + currency scale. Với exchange rates, contract cần rounding mode và precision cụ thể.

### 17.2. Decimal128 vs JSON double

Một converter serialize Decimal128 sang floating number có thể mất precision. Compare canonical BigDecimal hoặc integer unit thay vì kết quả đã qua double.

### 17.3. Numeric widening

int32(5) và int64(5) có thể tương đương về giá trị nhưng nếu overflow xảy ra khi chuyển từ int64 xuống int32, không được chấp nhận.

### 17.4. NaN/Infinity

Các giá trị floating đặc biệt có thể bị JSON serializer hoặc database xử lý khác. Nếu nghiệp vụ không cho phép, đánh dấu INVALID_DATA thay vì giả so equality.

### 17.5. Rounding policy

Một aggregate ở A dùng HALF_UP, B dùng HALF_EVEN có thể chênh một đơn vị ở edge cases. So theo contract đã định nghĩa, không “cho phép sai số 1” để lờ lỗi tài chính.

## 18. Timestamps, time zones và TTL

### 18.1. UTC instants

~~~text
2026-11-14T08:00:00Z
2026-11-14T15:00:00+07:00
~~~

Hai chuỗi cùng một instant. Canonicalization nên parse thành Instant và compare theo độ chính xác đã định.

### 18.2. Precision

Một DB lưu milliseconds, DB khác nanoseconds. Nếu contract chỉ bảo đảm ms, có thể normalize precision; nếu timestamps được dùng làm unique ordering thì truncation có thể gây duplicate/tie issues.

### 18.3. Timestamp được sinh bởi nguồn nào?

createdAt do client tạo khác server commit timestamp. Hai dữ liệu không nên so trực tiếp như sourceVersion nếu clock skew.

### 18.4. TTL và expiration

A có record với expiresAt 10:00:05, B đã xóa trước hoặc sau theo TTL scheduler, tạo mismatch tạm thời. Chọn một mốc semantic: record active tại reference time hay vật lý còn trong storage?

### 18.5. Soft delete

A giữ deletedAt, B không trả record đã soft-delete. Nếu query contract là “chỉ active orders”, hai behavior có thể tương đương; với audit query cần include deleted records thì khác.

### 18.6. Không so now() riêng tại A và B

Một filter “orders in last 15 minutes” được compile ở hai thời điểm khác nhau có thể chọn boundaries khác. Capture một referenceInstant và truyền cùng giá trị vào cả hai queries.

## 19. Pagination và sort: so một trang không đủ

Mô hình A trả trang 1:

~~~text
pageSize=3
sort=(createdAt desc, orderId desc)
A page 1: O9, O8, O7
~~~

B trả:

~~~text
B page 1: O9, O8, O6
~~~

Không thể kết luận chỉ bằng số bản ghi bằng nhau; phải xác định B thiếu O7, O6 xuất hiện sớm do sort key/tie-break/consistency, hoặc dữ liệu mới được ghi giữa hai reads.

### 19.1. Cursor khác offset

A dùng offset=20, B dùng PK-based cursor. Cần so cùng semantic window/range, không copy raw cursor token từ A sang B rồi mong nó hợp lệ.

### 19.2. Stable sort và tie-break

Nếu không có total ordering, hai queries hợp lệ có thể trả hàng bằng nhau nhưng vị trí khác. Định nghĩa order theo đủ keys trước khi kết luận mismatch.

### 19.3. Token mang snapshot state

Một số pagination tokens phụ thuộc partition/index checkpoint hoặc snapshot session. Không tự tái tạo token bằng client timestamp.

### 19.4. Compare complete bounded result

Với list API, có thể compare page 1, page 2 và kiểm tra no-duplicate/no-skip trong một capped window. Với deep pagination rất lớn, nên chạy offline validation bằng scan/partitioning được kiểm soát thay vì shadow mỗi request.

### 19.5. Empty page chưa chắc kết thúc

Ở một số query/scan APIs, trang có filtered records rỗng nhưng vẫn có continuation token. Một adapter B kết luận “hết dữ liệu” từ empty page có thể bỏ sót items.

### 19.6. Pagination under writes

Nếu records được insert/delete trong lúc hai hệ phân trang, offset pagination dễ drift. Mark INCONCLUSIVE khi không có snapshot-consistent read hoặc run offline dataset snapshot compare.

## 20. Aggregates: count, sum, distinct và window

Một query:

~~~text
COUNT orders WHERE tenantId=T17 AND status=CONFIRMED
SUM totalMinor WHERE createdAt in [t0,t1)
~~~

Thực tế có thể viết bằng MongoDB aggregation, DynamoDB app-side aggregation, Cassandra precomputed table hoặc search aggregations. Semantics phải nhất quán.

### 20.1. Count trên source và materialized count

B có thể là counter projection cập nhật eventual; lệch tạm thời với A là expected lag nếu version chưa đủ, không tự là bug. Nhưng lệch kéo dài tại cùng watermark cần điều tra.

### 20.2. DISTINCT semantics

Null/missing, casing, Unicode normalization và field type ảnh hưởng số distinct. Một index analyzer có thể làm lower-case text theo cách không giống data source.

### 20.3. Numerical aggregation

Đảm bảo cùng units, filtering và rounding. Dùng BigDecimal/integer accumulation cho tiền; tránh silently overflow int32.

### 20.4. Event windows

Định nghĩa event time vs processing time, timezone và late-arriving data policy. Một COUNT tại t1 không so với aggregate của B có watermark t0.

### 20.5. Approximate aggregation

Nếu B dùng HyperLogLog hoặc approximate distinct, không thể yêu cầu exact equality. Contract cần error bounds có căn cứ thống kê, test deterministic/reference data và guard against systematic bias.

## 21. Thiết kế bộ kết quả so sánh giàu thông tin

Thay vì một boolean equal, dùng taxonomy:

~~~text
MATCH
SEMANTIC_MISMATCH
SOURCE_STALE
CANDIDATE_STALE
NOT_BACKFILLED
UNCOMPARABLE_VERSION
INCOMPARABLE_QUERY_CONTRACT
BASELINE_ERROR
CANDIDATE_ERROR
COMPARISON_TIMEOUT
SKIPPED_BY_POLICY
RESOURCE_BUDGET_EXCEEDED
~~~

### 21.1. Match là một trạng thái có đủ điều kiện

Chỉ ghi MATCH khi cả hai reads hoàn tất, đủ điều kiện consistency, cùng contract và canonical views thực sự tương đương.

### 21.2. Inconclusive không được chảy vào Match

Nếu B timeout mà comparator trả true “để khỏi ảnh hưởng người dùng”, dashboard sẽ báo tỷ lệ match 100% giả tạo.

### 21.3. Candidate error khác dữ liệu sai

Nếu B query timeout, đó là độ tin cậy/readiness của mô hình mới. Không có dữ liệu để so nghĩa, nhưng vẫn là vấn đề cutover quan trọng.

### 21.4. Không phải mọi result đều terminal

Có thể retry compare ở một checkpoint sau khi B hội tụ. Ghi attempt/version để biết một mismatch ban đầu đã tự biến mất hay được repair có chủ đích.

### 21.5. Có severity

Tenant isolation breach hoặc sai monetary amount cần severity cao hơn khác biệt metadata không ảnh hưởng business. Không dùng tỷ lệ lỗi chung làm duy nhất điều kiện cutover.

## 22. Tỷ lệ match phải công bố mẫu số

Một workload:

~~~text
10,000 shadow candidates sampled
  8,000 eligible comparable pairs
  7,992 semantic matches
      8 semantic mismatches
  1,200 candidate stale
    500 not backfilled
    300 candidate query errors
~~~

### 22.1. Eligible match rate

\[
\mathrm{EligibleMatchRate}=\frac{7992}{8000}=99.9\%.
\]

Đây là chất lượng semantics **trong tập đã so được**, không phải tỷ lệ mọi request an toàn chuyển sang B.

### 22.2. Coverage

\[
\mathrm{ComparableCoverage}=\frac{8000}{10000}=80\%.
\]

20% không đủ điều kiện vẫn cần xử lý; không thể nói migration “99,9% hoàn tất”.

### 22.3. Mismatch rate

\[
\mathrm{EligibleMismatchRate}=\frac{8}{8000}=0.1\%.
\]

### 22.4. Unready và error ratio

\[
\mathrm{CandidateErrorRate}=\frac{300}{10000}=3\%.
\]

Phải ghi denominators, phân biệt sampled requests, eligible pairs và all live requests. Nếu sampling 1% traffic, 10.000 ở đây có thể chỉ đại diện subset cần weighted analysis.

### 22.5. Confidence không chỉ là point estimate

Một rate 100% trên 100 requests không bảo đảm 100% trên toàn tập, đặc biệt các nhóm hiếm chưa được lấy mẫu. Cần sample size, strata, confidence interval/upper bound theo mục tiêu rủi ro.

## 23. Sampling: tránh khuếch đại tải và thiên lệch

Một shadow service không cần chạy trên mọi request từ ngày đầu.

### 23.1. Deterministic sampling theo logical key

Ví dụ hash ổn định trên tenantId+orderId rồi lấy 1% keys. Điều này giúp so lại cùng key khi cần và ít phụ thuộc process restart.

### 23.2. Nhưng sample theo key khác sample theo request

Nếu hot key nhận 10.000 GETs, sample theo request có thể tập trung vào hot keys. Sample theo unique keys cho coverage tốt hơn, nhưng không phản ánh user traffic mix theo tần suất. Có thể cần hai chương trình đo riêng.

### 23.3. Stratified sampling

Lấy mẫu đủ ở nhóm:

~~~text
tenant tier
record age
record size bucket
status
query shape
country/region (when policy permits)
backfill partition
~~~

Không gắn raw tenant/customer IDs vào metric tags. Dùng bucket/cohort có cardinality kiểm soát và tuân thủ privacy rules.

### 23.4. Oversample edge cases

Các records có missing fields, zero items, nhiều nested arrays, legacy enum hoặc TTL gần hết có thể ít xuất hiện nhưng dễ lộ migration bug.

### 23.5. Sampling rate theo tải

Tăng dần 0.1% → 1% → 5% sau khi xác minh resource budget. Khi B p99 hoặc throttle tăng, tự giảm tần suất hoặc tắt shadow; không làm hỏng A để “đạt 5% sample”.

### 23.6. Weighted reports

Nếu oversample nhóm lỗi/tenant lớn, overall tỷ lệ match từ mẫu không còn đại diện traffic thực. Báo per-stratum và weighted aggregate với weights đã biết; đừng trộn hai loại không nhãn.

## 24. Tài nguyên: giới hạn thời gian, concurrency, memory và cost

Shadow request tiêu thụ:

~~~text
CPU to normalize A and B
memory to hold bounded result
connection(s) to B
network bandwidth
read capacity / IOPS
telemetry storage
~~~

### 24.1. Bounded queue

Không cho request A chờ khi hàng đợi shadow đầy. Ghi SKIPPED_RESOURCE_BUDGET và trả response A như thường.

### 24.2. Bounded concurrency

Giới hạn số B queries in flight theo service/node/tenant. Nếu không, 5% shadow trên hệ 100.000 QPS vẫn tương đương 5.000 extra QPS.

### 24.3. Per-shadow deadline

Đặt timeout nhỏ hơn khả năng worker chịu tải; một B query treo không được giữ bộ nhớ/correlation result vô hạn. Cancellation ở client không chắc cancel server query ngay; cần query-level limits và đo in-flight thật.

### 24.4. Result-size cap

Nếu query trả hàng trăm MB, không giữ toàn bộ hai result bodies trong heap Java. Dùng pagination/hashing by canonical rows tại offline mode hoặc giới hạn compare scope.

### 24.5. Cost budget

DynamoDB RCUs, search request cost, Cosmos RU, MongoDB cluster CPU, Cassandra read repair hoặc Redis cache misses đều có chi phí. Phải theo dõi chi phí shadow riêng.

### 24.6. Low priority và kill switch

Nếu có cơ chế tách pool/node/priority/queue cho B, áp dụng để tránh SLO regression cho production path A.

## 25. Điều kiện an toàn để bắt đầu chạy production shadow reads

Trước khi tăng sample lên production:

1. Code path thực sự không invoke mutation handlers.
2. Shadow identity không có DB write privileges.
3. Network policy chặn dịch vụ side-effecting không cần thiết.
4. Không log raw queries, payloads hoặc PII.
5. Có cơ chế bounded concurrency, queue, timeouts và result size.
6. Có hard kill switch và rollback của feature flag.
7. Có telemetry candidate errors, resource usage, skipped and mismatch.
8. Backfill readiness và CDC watermarks đủ xác định eligible cohorts.
9. Có người/nhóm sở hữu việc phân loại discrepancies.
10. Đã thử fault injection ở môi trường được phép.

### 25.1. Không bật trên tất cả endpoints

Chỉ enable các query templates đã được review; những endpoints có business side effects phải bị từ chối ở compiler/policy.

### 25.2. Query plan review

B Query có thể là table scan không có index. Review explain/trace/cost theo engine trước khi mirror ở QPS đáng kể.

### 25.3. Ban đầu so với snapshot ổn định

Staging/offline snapshot comparison có thể phát hiện mapper bugs dễ hơn khi live A/B liên tục thay đổi; sau đó mới shadow traffic thực để tìm edge cases.

## 26. Một chương trình đối chiếu có hai nhánh

### 26.1. Offline exhaustive/batch validation

Đọc dữ liệu theo partition/bucket đã chọn trên snapshot/checkpoint nhất quán, so counts, hashes, business invariants. Bao phủ dữ liệu cold và record hiếm, không làm user queries chậm.

### 26.2. Online sampled shadow validation

Mirror những query intents thực đang chạy để phát hiện gaps của access patterns, sort/pagination, cache/consistency và tenant-specific behaviors.

### 26.3. Vì sao cần cả hai?

Offline full scan có thể chứng minh số lượng records đúng nhưng không biết API list query sorting sai. Shadow traffic có thể thấy query behavior đúng cho hot keys nhưng bỏ sót 50% cold historical records.

### 26.4. Không dùng kết quả một nhánh suy cho nhánh khác

Một offline data checksum match không chứng minh B p99 đủ tốt; một online shadow 99.99% eligible match không chứng minh retention/legacy records đã migrate hết.

## 27. Java: biểu diễn một query intent bất biến

Thay vì copy HTTP request hoặc gọi lại controller, đóng gói **ý định đọc** bằng kiểu dữ liệu nhỏ:

~~~java
import java.time.Instant;

public record GetOrderIntent(
        String tenantId,
        String orderId,
        Instant referenceTime,
        String queryContractVersion
) {
    public GetOrderIntent {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (referenceTime == null) {
            throw new IllegalArgumentException("referenceTime is required");
        }
    }
}
~~~

### 27.1. Không cho intent chứa credential

Không đưa Authorization header, session cookie, AWS token, raw access key hoặc toàn bộ JSON request vào record; shadow executor phải có read-only workload identity riêng.

### 27.2. Query contract version

Một thay đổi mapping status hoặc null semantics cần làm mới version; nếu không, metric MATCH trước và sau có thể không so được.

### 27.3. Reference time dùng cho filter

Capture một Instant từ đường chính để tính age/TTL-based predicate và dùng lại trên B. Nhưng Instant không tự thay thế source-assigned commit version để xác minh consistency.

### 27.4. Tenant scope

Query compiler của B luôn bao gồm tenantId/authorization scope tương đương A. Validation chỉ tại API layer không đủ nếu adapter B có bug bỏ tenant filter.

## 28. Java: canonical view và business semantics

~~~java
import java.util.List;

public record CanonicalOrderItem(
        int lineNo,
        String sku,
        long quantity
) {}

public record CanonicalOrder(
        String tenantId,
        String orderId,
        String status,
        long totalMinor,
        String currency,
        long sourceVersion,
        List<CanonicalOrderItem> items
) {
    public CanonicalOrder {
        items = List.copyOf(items);
    }
}

public interface OrderQueryReader {
    CanonicalOrder get(GetOrderIntent intent);
}
~~~

### 28.1. CanonicalOrder là model so sánh

Đây không nhất thiết là public API DTO. Có thể khác ở metadata/sourceVersion, nhưng fields dùng so semantics phải phản ánh đúng hợp đồng.

### 28.2. Adapter của mỗi engine

MongoOldOrderReader lấy embedded document rồi convert; DynamoNewOrderReader thực hiện GetItem/Query và hydrate items; cả hai trả CanonicalOrder.

### 28.3. Xử lý NOT_FOUND rõ ràng

Nếu reader trả null cho NOT_FOUND, comparator phải tách:

~~~text
A=null, B=null: MATCH_NOT_FOUND, nếu cùng scope/version.
A=object, B=null: MISSING_IN_B (sau eligibility).
A=null, B=object: EXTRA_IN_B (sau eligibility).
~~~

Không bỏ qua vì cả hai không có giá trị để so.

### 28.4. Không để raw object với mutable lists

Một reference view giữ cho async compare nên bất biến/copy dữ liệu cần thiết. Nếu controller tiếp tục mutate list A sau khi schedule, comparator có thể đọc trạng thái khác user đã thấy.

## 29. Java: comparator kiểm tra version trước khi so giá trị

Ví dụ tối giản, chỉ áp dụng khi cả A và B expose cùng entity sourceVersion có nghĩa:

~~~java
import java.util.Objects;

public enum ComparisonOutcome {
    MATCH,
    SEMANTIC_MISMATCH,
    INCOMPARABLE_VERSION
}

public final class OrderComparator {
    public ComparisonOutcome compare(
            CanonicalOrder a,
            CanonicalOrder b
    ) {
        if (a == null || b == null) {
            return a == b
                    ? ComparisonOutcome.MATCH
                    : ComparisonOutcome.SEMANTIC_MISMATCH;
        }

        if (a.sourceVersion() != b.sourceVersion()) {
            return ComparisonOutcome.INCOMPARABLE_VERSION;
        }

        boolean equal = Objects.equals(a.tenantId(), b.tenantId())
                && Objects.equals(a.orderId(), b.orderId())
                && Objects.equals(a.status(), b.status())
                && a.totalMinor() == b.totalMinor()
                && Objects.equals(a.currency(), b.currency())
                && Objects.equals(a.items(), b.items());

        return equal
                ? ComparisonOutcome.MATCH
                : ComparisonOutcome.SEMANTIC_MISMATCH;
    }
}
~~~

### 29.1. Giới hạn quan trọng của ví dụ

Khi một bên NOT_FOUND, đoạn code đơn giản chưa thể chứng minh **cùng mốc so sánh**, nên production comparator phải kiểm tra readiness/watermark và visibility trước khi gọi compare. Missing in B có thể do backfill chưa xong.

### 29.2. Không phải version nào cũng so bằng số

Trong một số engine, version token có scope partition, opaque string hoặc vector clock. Khi đó cần policy chuyên biệt thay vì so long.

### 29.3. Version equal không luôn có nghĩa snapshot global equal

Nếu B hydrate header và items từ hai source versions không nguyên tử, header.sourceVersion=v8 chưa chứng minh items cùng v8. Cần projection checkpoint hoặc consistency mechanism đảm bảo một canonical view đồng bộ.

### 29.4. Comparator không ghi database

Method compare là pure function trên immutable inputs. Việc persist mismatch ticket hoặc repair data là workflow khác; không thêm hidden repository.update() vào comparator.

## 30. Java: fail-isolated shadow dispatch với hàng đợi giới hạn

Ví dụ ý tưởng Java 17+:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class ShadowOrderService {
    private final OrderQueryReader baseline;
    private final OrderQueryReader candidate;
    private final OrderComparator comparator = new OrderComparator();
    private final ShadowRecorder recorder;

    private final ThreadPoolExecutor shadowPool =
            new ThreadPoolExecutor(
                    2, 4, 30, TimeUnit.SECONDS,
                    new ArrayBlockingQueue<>(256),
                    new ThreadPoolExecutor.AbortPolicy()
            );

    public ShadowOrderService(
            OrderQueryReader baseline,
            OrderQueryReader candidate,
            ShadowRecorder recorder
    ) {
        this.baseline = baseline;
        this.candidate = candidate;
        this.recorder = recorder;
    }

    public CanonicalOrder getOrder(GetOrderIntent intent) {
        // Only A determines the user-visible response.
        CanonicalOrder responseA = baseline.get(intent);

        if (recorder.enabled() && recorder.shouldSample(intent)) {
            try {
                shadowPool.execute(() -> compareLater(intent, responseA));
            } catch (RejectedExecutionException saturated) {
                recorder.skipped("queue_full");
            }
        }
        return responseA;
    }

    private void compareLater(GetOrderIntent intent, CanonicalOrder a) {
        try {
            CanonicalOrder b = candidate.get(intent);
            ComparisonOutcome outcome = comparator.compare(a, b);
            recorder.outcome(intent.queryContractVersion(), outcome.name());
        } catch (RuntimeException candidateError) {
            recorder.outcome(
                    intent.queryContractVersion(), "CANDIDATE_ERROR"
            );
        }
    }

    public void shutdown() {
        shadowPool.shutdown();
    }
}
~~~

Giả định ShadowRecorder là interface do ứng dụng định nghĩa (enabled/shouldSample/skipped/outcome), không phải thư viện Java chuẩn. Đoạn code chỉ mô tả kiến trúc; chưa bao gồm per-query deadline, tenant rate limiter, full readiness classification, executor lifecycle và protected diagnostics. Nó cũng **không bắt các loại Error nghiêm trọng**: không được tự nuốt lỗi runtime/VM của đường chính vì shadow.

### 30.1. B trả exception không ảnh hưởng A

Lỗi B chỉ được ghi qua recorder an toàn. Nếu việc ghi recorder có thể ném exception, caller cũng cần cách isolate để instrumentation không làm hỏng response chính.

### 30.2. Hàng đợi đầy thì skip

AbortPolicy từ chối task thay vì ép thread API thực hiện B; tránh CallerRunsPolicy khi mục tiêu là không đưa shadow query lên critical path.

### 30.3. Không khởi tạo pool riêng cho mỗi request

Pool là thành phần lifecycle của service, được quản lý đóng/mở an toàn. Không spawn unbounded threads/futures cho từng query.

### 30.4. Reader B phải thực sự read-only

Đoạn code không chứng minh candidate.get() không ghi. Bên trong adapter cần read-only credential, allowlisted query, timeout, network restrictions và kiểm thử side effects.

### 30.5. A có thể trả null

Vẫn có thể schedule để đối chiếu negative lookup. Với fallback hoặc error path của A, cần policy rõ và không chuyển request từ A sang B trong vô thức.

## 31. Java: deadline và cancellation có giới hạn

Một shadow executor cần query-level timeout tại driver:

~~~text
shadow overall budget: 500 ms
candidate database query timeout: 350 ms
normalization/compare budget: 100 ms
telemetry budget: best effort / nonblocking
~~~

Các con số chỉ minh họa, phải điều chỉnh theo query class, backend capacity và overhead.

### 31.1. CompletableFuture.orTimeout không xóa được server query

Một future có thể hoàn thành exceptionally khi quá timeout, nhưng database request vẫn có thể đang chạy nếu driver/server chưa cancel. Cần cấu hình driver timeout/maxTime/statement timeout và theo dõi actual in-flight.

### 31.2. Giữ bounded result

Nếu B trả hàng trăm nghìn docs, query timeout chưa chặn out-of-memory do materialization. Đặt page/limit/bytes cap và compare từng phần theo contract.

### 31.3. Không ghép timeout của A và B

A có API latency SLO; B có experiment budget. B timeout không nên kéo theo tăng HTTP timeout hay retry ở A.

### 31.4. Không retry B vô hạn

Một timeout B có thể được báo CANDIDATE_ERROR. Retry phục vụ validation có thể có budget riêng nếu cần, nhưng nhiều retries sẽ làm méo workload/cost.

### 31.5. Không chờ recorder

Nếu telemetry collector quá tải, shadow worker nên drop aggregated event hoặc lưu bounded sample theo policy, không làm hàng đợi application phình vô hạn.

## 32. Java: sampler deterministic và bảo vệ privacy

Ví dụ một policy hash-based:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ShadowSampler {
    public static boolean include(
            String tenantId, String orderId, int perTenThousand
    ) {
        if (perTenThousand < 0 || perTenThousand > 10_000) {
            throw new IllegalArgumentException("Invalid sampling rate");
        }
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] input = (tenantId + "\u0000" + orderId)
                    .getBytes(StandardCharsets.UTF_8);
            byte[] digest = md.digest(input);
            int hash = ((digest[0] & 0xff) << 8) | (digest[1] & 0xff);
            return (hash % 10_000) < perTenThousand;
        } catch (NoSuchAlgorithmException impossibleInStandardJDK) {
            throw new IllegalStateException(impossibleInStandardJDK);
        }
    }
}
~~~

### 32.1. Sampling này không phải security hashing

SHA-256 ở đây dùng để chia keys vào buckets; không dùng digest như anonymization của tenantId/orderId. Với ID đoán được, digest cũng có thể bị brute-force. Không log digest/raw ID khi policy không cho.

### 32.2. Một giới hạn của cách modulo

Hash modulo trên 16 bit có thể tạo độ lệch phân bố nhỏ và correlation nếu sampling logic thay đổi. Với sampling thống kê chặt chẽ/large-scale, dùng hash 64-bit ổn định hoặc HMAC keyed theo policy và xác minh phân bố. Đây chỉ là ví dụ đơn giản.

### 32.3. Stable sampling giúp đối chiếu lại

Cùng key luôn được include/skip tại cùng rate, giúp quan sát một tập keys qua các deployments, nhưng một key được đọc nhiều lần có thể làm sample theo request mất tính đại diện.

### 32.4. Strata vẫn cần

Nếu một nhóm hiếm chỉ có 5 records, sampling 1% có thể không lấy record nào. Kết hợp sampling theo bucket/coverage requirements.

## 33. Java: một recorder không chứa payload

Ví dụ API telemetry an toàn:

~~~java
public interface ShadowRecorder {
    boolean enabled();
    boolean shouldSample(GetOrderIntent intent);
    void skipped(String reason);
    void outcome(String queryContractVersion, String outcomeClass);
}
~~~

### 33.1. Chỉ ghi category và dimensions giới hạn

Một implementation bằng Micrometer có thể ghi counters theo queryClass, contractVersion, outcome, region và sizeBucket. Không gắn raw orderId, email, tenantId, payloadDigest hay raw query.

### 33.2. Cần mismatch samples để debug

Khi cần điều tra một mismatch cụ thể, có thể lưu record ID dưới HMAC/lookup token trong một hệ riêng được mã hóa, retention ngắn, RBAC/audit; không đặt toàn bộ A/B PII trong centralized logs mặc định.

### 33.3. Correlation qua logs/traces

TraceId cho biết request đường chính và shadow attempt; nó không thay stable entity/version reference khi chẩn đoán asynchronous compare. Không truyền authorization headers trong trace baggage.

### 33.4. Recorder không quyết định response

Comparator kết quả khác nhau chỉ tạo telemetry/evidence. Canary switch hoặc rollback phải là change-management action với owner.

## 34. MongoDB: truy vấn giữa embedded documents và collections tách rời

Giả sử A lưu:

~~~json
{
  "_id": "O101",
  "tenantId": "T17",
  "status": "CONFIRMED",
  "items": [
    {"lineNo": 1, "sku": "P1", "qty": 2},
    {"lineNo": 2, "sku": "P2", "qty": 1}
  ],
  "version": 8
}
~~~

B lưu order_headers và order_items, cùng orderId/tenantId.

### 34.1. Reader A

~~~javascript
db.orders.findOne(
  {_id: "O101", tenantId: "T17"},
  {projection: {tenantId: 1, status: 1, items: 1, version: 1}}
)
~~~

### 34.2. Reader B

~~~javascript
const header = db.order_headers.findOne(
  {orderId: "O101", tenantId: "T17"}
)
const items = db.order_items.find(
  {orderId: "O101", tenantId: "T17"}
).sort({lineNo: 1}).toArray()
~~~

Đoạn script minh họa ở đây chỉ đọc; không được gọi nó trực tiếp trong request path nếu việc hydrate items gồm nhiều round trips không nằm trong budget.

### 34.3. Multi-query consistency

Reader B có thể đọc header v8 rồi items v7 nếu CDC áp dụng theo hai collections chưa nguyên tử. A embedded read có thể phản ánh một document version nhất quán hơn. Cần transaction/snapshot/read model version marker hoặc tình trạng INCOMPARABLE để giải thích.

### 34.4. Aggregation stages có thể ghi

Không coi mọi aggregation là read-only: các stages như $out/$merge thực hiện writes, nên phải bị cấm trong query allowlist. Cẩn trọng với JavaScript functions/stored logic hoặc các extension có tác động ngoài mong muốn.

### 34.5. Connection isolation

Dùng MongoClient read-only credential cho shadow worker; cấu hình maxTimeMS/read preference/read concern theo contract và query plan. Query B có thể tạo load lớn dù không sửa business documents.

### 34.6. Change streams và lag

Change streams dùng để đồng bộ B có resume tokens/retention. Mirror queries cần biết B đã bắt kịp source version/checkpoint, không dùng sự tồn tại change stream làm bảo đảm B luôn current.

### 34.7. Phân loại mismatch

Missing header, missing items, duplicate lineNo, wrong status, wrong tenant, wrong total, candidate stale và projection join race cần là các categories riêng để xác định nơi sửa.

## 35. DynamoDB: GetItem, Query, GSI và chi phí của shadow

Giả sử A có item:

~~~text
PK=ORDER#O101
attributes: tenantId, status, totalMinor, version
~~~

B thiết kế single-table:

~~~text
PK=TENANT#T17#ORDER#O101
SK=META
PK=TENANT#T17#ORDER#O101
SK=ITEM#0001
PK=TENANT#T17#ORDER#O101
SK=ITEM#0002
~~~

### 35.1. Điểm đọc tương đương

A có thể GetItem theo PK; B Query PK để lấy META và ITEM records rồi convert thành canonical view. Đừng coi hai raw item sets bằng nhau.

### 35.2. Consistency của GSI

DynamoDB GSI có eventual read semantics; strongly consistent reads chỉ hỗ trợ ở các đường đọc được dịch vụ cho phép, không phải GSI. Nếu A dùng strongly consistent base-table GetItem và B dùng GSI, expected lag phải được mô hình hóa.

### 35.3. Consumed capacity

Shadow traffic tăng read capacity consumed, có thể dẫn đến throttling/hot partition và ảnh hưởng production nếu dùng chung capacity. Giới hạn QPS, bytes và per-tenant load.

### 35.4. Query pagination

DynamoDB Query có thể trả LastEvaluatedKey cần tiếp tục; Count/ScannedCount cũng không thay việc đọc các trang còn lại. Một adapter dừng ở trang đầu sẽ tạo false missing records.

### 35.5. Read-only IAM

Shadow principal nên được phép đúng GetItem/Query trên table/index cần thiết, không có PutItem/UpdateItem/DeleteItem/TransactWriteItems. Tách khả năng đọc source và candidate theo chính sách tenant.

### 35.6. Conditional writes thuộc pipeline khác

Nếu B có lỗi duplicate items hoặc miss events, không dùng UpdateItem trong nhánh shadow để “sửa ngay”; sửa bằng version-aware migration writer được audit riêng.

### 35.7. Query result sizes

Một B query nhiều items có read capacity/latency khác A GET một item. Semantic match chưa chứng minh B đạt cost/latency SLO.

## 36. Cassandra/ScyllaDB: partition key, clustering order và paging

Mô hình A:

~~~sql
SELECT * FROM orders_by_customer
WHERE customer_id = ?
LIMIT 20;
~~~

Mô hình B tách partition theo thời gian:

~~~sql
SELECT * FROM orders_by_customer_month
WHERE customer_id = ? AND order_month = ?
LIMIT 20;
~~~

### 36.1. Không thể copy nguyên query và so trực tiếp

B cần query nhiều months rồi merge/sort/deduplicate để tái tạo cùng “top 20 newest orders” của A. Nếu chỉ query tháng hiện tại, sẽ thiếu orders ở boundary.

### 36.2. Clustering order

ORDER BY bị ràng buộc bởi clustering columns/partition semantics trong CQL. Chuyển data model có thể thay thứ tự mặc định; contract cần stable sort/order by tương ứng.

### 36.3. Paging state

Paging state/cursor phụ thuộc query, driver/session và partition layout. Không dùng token A làm token B. Hãy so semantic page boundaries/sorted keys.

### 36.4. Consistency level

Hai CQL reads ở các CL khác nhau có thể thấy versions khác nhau. Ghi CL, serial consistency nếu có LWT liên quan và replica/region settings; đừng đồng nhất stale read với mapper bug.

### 36.5. TTL/tombstones

Cassandra có TTL và tombstones; B có thể có expired rows khác thời điểm cleanup. So canonical active state, không dựa vào SSTable physical presence. Queries có thể gây read repair hoặc read amplification; operational side effects không hoàn toàn bằng không.

### 36.6. Hot/wide partitions

Một shadow query vào very wide partition có thể tốn I/O và làm p99 tăng. Giới hạn partitions, response size và query budget; theo dõi coordinator saturation.

### 36.7. Chỉ dùng SELECT

Đừng gọi INSERT IF NOT EXISTS hay LWT để xác minh dữ liệu còn tồn tại; đó là mutation. Shadow identity cần SELECT-only trên đúng keyspace/tables.

## 37. Redis: GET không phải mọi lệnh trông giống GET đều thuần đọc

Nếu migration đổi Redis key format:

~~~text
Old: session:T17:U101
New: tenant:T17:session:U101
~~~

### 37.1. GET vs GETEX/GETDEL

GET chỉ đọc logical value, nhưng GETEX có thể thay TTL và GETDEL **xóa key**. Không dùng GETEX để “xem giá trị và refresh TTL” trong shadow path.

### 37.2. Cache-aside side effect

Một helper getSession() có thể tự SET key khi miss hoặc refresh session sliding expiration. Muốn compare, dùng dedicated read-only Redis client command path.

### 37.3. Redis internal effects

GET có thể ảnh hưởng LRU/LFU metadata và một số key có thể lazy expire. Đây không phải “zero operational effect”; cần giới hạn tải và phân biệt với business mutation.

### 37.4. Compare TTL thế nào?

TTL đếm ngược theo thời gian; so giá trị TTL bằng nhau ở hai lần GET cách nhau 100 ms không đáng tin. Contract có thể so absolute expiresAt nếu được lưu cùng source semantics hoặc so behavior “đang active tại reference time”.

### 37.5. Cache misses

Nếu A key còn, B key chưa warm, B NOT_FOUND có thể là cache coverage issue, không phải canonical data mismatch. Với derived cache, có thể quyết định cache warmup policy riêng, nhưng **shadow comparator không được tự SET cache mới**.

### 37.6. Redis scripts

Không dùng EVAL/EVALSHA trong shadow nếu scripts chưa được chứng minh read-only và restricted command access. Một script “lấy trạng thái” có thể ghi counters/TTL.

### 37.7. ACL và network

Dùng ACL user có quyền chỉ đọc các key patterns/lệnh cần; không cấp FLUSH, DEL, SET, EXPIRE hay admin. Test denial có chủ đích ở staging.

## 38. Search: ranking, analyzer và index refresh

Tình huống A/B là Elasticsearch/OpenSearch index v1 và index v2.

### 38.1. So set of matching documents trước

Nếu analyzer/ranking có thay đổi, không nên yêu cầu score floats và thứ tự xếp hạng khớp tuyệt đối, trừ khi sản phẩm thực sự cần contract đó. Có thể tách eligibility/filter match, top-K overlap và NDCG/ranking metrics.

### 38.2. Search visibility eventual

Một document source mới được ghi có thể chưa visible ở một trong hai indexes do refresh/CDC lag. Trước khi kết luận mismatch, xem projection watermark và index refresh behavior.

### 38.3. Pagination và stable sort

search_after/PIT contexts có semantics riêng; không copy opaque token của index A sang B. So normalized results trên cùng query parameters và point-in-time context phù hợp khi được hỗ trợ.

### 38.4. Total hits có thể là estimate hoặc capped

Một số search APIs không trả exact total hits theo mặc định hoặc cấu hình. Nếu A trả 10.000+ và B trả chính xác 11.234, không so hai giá trị như số nguyên chính xác.

### 38.5. Scoring changes có chủ đích

Nếu B đổi tokenizer/synonyms, lower-case normalization hoặc boost weights, top-K khác có thể là intended improvement. Contract phải nêu metrics phù hợp như recall@K, precision@K hoặc ranking relevance qua test corpus.

### 38.6. Không lẫn query với mutation

Index refresh, reindex, update_by_query, delete_by_query là các operations có tác động, không thuộc shadow compare. Dùng search API read-only, client role và query allowlist.

### 38.7. User personalization

Search result có thể phụ thuộc user profile/location/entitlements. Shadow context phải đủ an toàn và thống nhất để reproduce filter, nhưng không copy auth tokens hay dữ liệu nhạy cảm sang index không được phép.

## 39. Multi-region và cross-datacenter comparison

Một hệ có:

~~~text
Source A in Region East.
Candidate B in Region West.
CDC replication lag: variable 0-10 seconds.
~~~

### 39.1. Vấn đề do khác Region

Latency network, replica placement, current write owner và data residency làm kết quả khác nhau ngoài mapper logic. Báo region pair/consistency mode trong telemetry.

### 39.2. Data residency

Không mirror PII hoặc queries sang Region không được phép. Nếu policy không cho B đọc tenant ở Region khác, phải skip theo policy chứ không cố bypass.

### 39.3. Failover window

Khi Region leader thay đổi, hai mô hình có thể tạm nhìn khác source watermark. Đánh dấu failover cohort và có thể pause compare cho những queries chưa đủ stability.

### 39.4. Cross-region bandwidth

Mirror nhiều result bodies không chỉ tăng latency/cost mà còn làm lộ dữ liệu qua thêm network hop. Nên gửi query intent/summary trong phạm vi cho phép, không dump raw documents.

### 39.5. B về nguồn authority nào?

Một active-active model có conflict resolution khác A. Phải quyết định semantic authority và convergence contract; một “newer timestamp” không luôn là phiên bản thắng nếu clock skew.

## 40. Tenant isolation và authorization của hai adapters

### 40.1. Không compare cross-tenant

Nếu A trả order theo tenant T17 còn B reader quên tenant filter, B có thể trả order của T18 có trùng ID; đây là lỗi nghiêm trọng cần dừng rollout, không chỉ tỷ lệ mismatch 0.001%.

### 40.2. Shadow worker không cần user credential

Thay vì forward JWT/cookies, xác thực API ở đường chính và truyền scope đã kiểm soát vào query intent; shadow workload identity có quyền đọc hạn chế đúng dữ liệu được phép.

### 40.3. Authorization policy cần tương đương

Nếu API GET lọc orders theo user membership, A và B cần enforce cùng policy. Một compare chỉ trên data equality bỏ qua unauthorized extra records là nguy hiểm.

### 40.4. Không log query values nhạy cảm

OrderId/tenantId/PII nằm trong request parameters; metric labels chỉ chứa query class, tenant tier hoặc cohort. Các mismatch samples có thể lưu trong encrypted restricted store.

### 40.5. Canary security tests

Chủ động test ID collision giữa tenants, disabled accounts, deleted resources, ACL changes và GDPR/retention states trong môi trường được phép, không dùng dữ liệu thật không được ủy quyền.

## 41. Lộ trình từ offline compare đến canary cutover

Một kế hoạch có thể chia thành:

~~~mermaid
flowchart TD
    A["Freeze query contract and security scope"] --> B["Offline dataset/backfill verification"]
    B --> C["Shadow sample 0.1 percent"]
    C --> D["Shadow 1-5 percent with budgets"]
    D --> E["Triage mismatches and close CDC gaps"]
    E --> F{"Readiness gates pass?"}
    F -->|No| B
    F -->|Yes| G["Canary B serves small user cohort"]
    G --> H{"Correctness + latency + error gates pass?"}
    H -->|No| I["Rollback response routing to A"]
    H -->|Yes| J["Increase canary gradually"]
    J --> K["B becomes read authority"]
~~~

### 41.1. Phase 0: offline fixtures

So deterministic canonical datasets, including old schemas, missing fields, duplicates, TTL/deletes, high-cardinality tenants và query boundaries.

### 41.2. Phase 1: backfill completeness

Đo coverage theo source partitions, entity versions, CDC watermarks. Không mirror large-scale trước khi B có index/query plan đủ an toàn.

### 41.3. Phase 2: sampled production shadow

A vẫn phục vụ tất cả requests; B chỉ đối chiếu. Metrics phải phân biệt skipped/not-ready/error/mismatch/match.

### 41.4. Phase 3: canary serving

Một nhóm user/tenants do policy lựa chọn đọc B thật; có rollback flag và canary-specific SLO. Không còn gọi đây là pure shadow vì kết quả B đã ảnh hưởng người dùng.

### 41.5. Phase 4: tăng tỷ lệ

Theo dõi read correctness, latency, cost, p99 by tenant/query class, CDC/backfill lag, retries và sự cố security. Giữ A/rollback readiness trong khoảng cần thiết.

### 41.6. Phase 5: retire model A

Chỉ sau khi đường viết/đọc, rollback horizon, retention, audit và downstream dependencies được xử lý; không xóa A ngay khi B vừa đạt 100% GET traffic.

## 42. Dashboard: đếm đủ những trường hợp không được so

Đề xuất metrics:

~~~text
shadow_candidates_total{query_class}
shadow_selected_total{query_class,cohort}
shadow_skipped_total{reason,query_class}
shadow_outcomes_total{outcome,query_class,contract_version}
shadow_compare_duration_seconds{query_class}
shadow_candidate_query_duration_seconds{query_class}
shadow_candidate_read_errors_total{category,query_class}
shadow_queue_depth
shadow_in_flight
shadow_cdc_lag_seconds
shadow_backfill_coverage_ratio
shadow_record_size_bytes
shadow_candidate_read_capacity
~~~

Các tên metrics là ví dụ do ứng dụng tự instrument; đừng cho rằng MongoDB/DynamoDB/Prometheus tự phát đúng tất cả trường này.

### 42.1. Không tính MATCH trên all sampled khi nhiều INCONCLUSIVE

Ví dụ 7.992 match trên 10.000 sampled tương ứng 79,92% sample có verified match, **không có nghĩa** 20,08% là semantic bugs. Trong 20,08% có not-ready/stale/errors.

### 42.2. Candidate error rate riêng

B timeout hoặc throttle không phải semantic mismatch, nhưng có thể chặn cutover vì không đạt availability/performance SLO.

### 42.3. Skipped là tín hiệu quan trọng

Nếu queue full 60% requests, match rate trên phần còn lại không đại diện workload. Đo sampling eligible/selected/executed/completed.

### 42.4. Không trộn response A và B trong một p99

Đo p99 A live, p99 B shadow, p99 B canary và end-to-end user response riêng. B shadow có cache state khác B serving nên latency chỉ là một chỉ dấu.

### 42.5. Per-stratum dashboard

Phân nhóm queryClass, tenant tier, record age, size bucket, region, candidate lag bucket và test phase; tránh raw IDs.

### 42.6. Dòng thời gian thay đổi

Overlay deployment, schema/backfill version, index build, CDC worker changes và feature flag ramp để gắn divergence spike với thay đổi.

## 43. Một vài công thức giám sát

Định nghĩa:

\[
S=\text{selected shadow intents},\quad
E=\text{eligible comparable pairs},\quad
M=\text{matches},\quad
D=\text{semantic mismatches}.
\]

Khi E=M+D theo một contract:

\[
\mathrm{MatchRate}=\frac{M}{E},\quad
\mathrm{MismatchRate}=\frac{D}{E},\quad
\mathrm{Coverage}=\frac{E}{S}.
\]

### 43.1. Độ trễ của B

~~~text
Candidate read p50 / p95 / p99
Candidate query error/timeout rate
CDC source-to-candidate watermark lag
Shadow queue wait p99
~~~

### 43.2. Bounded resource rate

\[
\mathrm{ShadowAmplification}=
\frac{\text{B read calls issued}}
{\text{A read calls observed in comparable class}}.
\]

Nếu B cần nhiều GetItem/Query calls để dựng một logical result, phân biệt logical shadow query rate với physical DB calls/read capacity.

### 43.3. Coverage theo sample vs toàn population

Nếu chỉ mirror 1% live requests, Coverage=95% nói về tập **được chọn**, không phải “95% dữ liệu đã được migrate”. Cần backfill inventory/offline verification riêng.

### 43.4. Định nghĩa window/cohort

Shadow B có thể hoàn thành sau khi A response đã gửi và sau khi metric A được ghi. Counter tỷ lệ trong một cửa sổ rất ngắn có thể bị lệch do completion lag; đo cohort và mature windows khi cần.

### 43.5. Confidence

Với 0 mismatches trong n comparable independent samples, một quy tắc gần đúng cho upper 95% bound của true mismatch rate là khoảng 3/n trong điều kiện sampling/độc lập phù hợp. Không áp dụng máy móc khi samples phụ thuộc cùng key hoặc có selection bias.

## 44. Runbook: phát hiện semantic mismatch thật

### Bước 1 — Không tự sửa response user

Giữ A làm authority trong shadow phase. Một mismatch ở B không nên làm thay đổi A hoặc tạo retry update.

### Bước 2 — Kiểm tra eligibility

Hai results có cùng queryContractVersion, tenant scope, referenceInstant, sourceVersion/watermark phù hợp không?

### Bước 3 — Chốt mismatch class

Missing/extra item, wrong field, invalid enum, wrong currency precision, sort order, duplicate row, tenant leak hay aggregate diff?

### Bước 4 — Lưu evidence an toàn

Ghi query class, migration version, source/candidate version, reason và một secure lookup token; raw customer data chỉ trong restricted evidence store có retention.

### Bước 5 — Kiểm tra nguồn phát lỗi

Có bug trong B adapter, backfill, CDC projector, query plan, mapping, TTL, pagination, index hoặc A baseline contract?

### Bước 6 — Chặn rollout nếu severity cao

Tenant isolation, monetary correctness, orders missing, data exposure cần ưu tiên cao và có thể kích hoạt kill switch/cutover gate ngay.

### Bước 7 — Sửa ở workflow có thẩm quyền

Nếu B thiếu dữ liệu, sửa backfill/CDC writer qua code có audit và version checks; **không mutate từ comparator**.

### Bước 8 — Đối chiếu lại

Sau fix và CDC catch-up, chạy offline affected partition + shadow cohort, lưu kết quả theo code/version mới.

## 45. Runbook: tỷ lệ INCONCLUSIVE tăng nhưng mismatch gần bằng 0

### 45.1. Đừng tuyên bố thành công

Nếu 50% selected queries trả CANDIDATE_STALE, 49.9% MATCH và 0.1% MISMATCH thì candidate chưa đủ coverage/freshness. MatchRate trên eligible có thể cao, nhưng migration vẫn chưa ready.

### 45.2. Kiểm tra CDC lag

Check oldest event age, source/candidate checkpoints, consumer errors, backfill/CDC races, failover và dead-letter queue.

### 45.3. Kiểm tra candidate query errors

Nếu B timeout/throttle, INCONCLUSIVE có thể do overload từ shadow traffic chứ không phải data freshness.

### 45.4. Kiểm tra comparator gating

Một gate quá nghiêm ngặt có thể đánh dấu mọi version different là inconclusive dù có thể so tại stable snapshot; nhưng không nới gate chỉ để tăng match rate.

### 45.5. Dùng cohort mature

Một query được mirror ngay sau write rất dễ thấy B lag. Đo sau convergence deadline và per-age bucket để hiểu thời gian hội tụ.

## 46. Runbook: shadow traffic làm production chậm

### 46.1. Phát hiện

~~~text
Shadow sampling rises from 1% to 10%.
DB read capacity consumed doubles.
A API p99 rises from 80ms to 300ms.
Shadow queue depth grows continuously.
~~~

### 46.2. Hành động đầu

Giảm/tắt shadow sample, giữ A phục vụ bình thường. Không retry B đến khi match vì làm tăng load.

### 46.3. Kiểm tra tài nguyên chia sẻ

Candidate B có chung cluster/connection pool, CPU/disk/network, IAM read quota, cache hay thread pool với A không?

### 46.4. Bounded concurrency

Nếu queue vô hạn, lượng request tích tụ gây OOM hoặc recovery storm. Giảm worker concurrency, giới hạn queue/result bytes và loại các query classes đắt.

### 46.5. Sau khi ổn định

So A p99 trước/sau shadow off; review indexes, statement limits, reserved capacity hoặc clone cluster nếu cần. Chỉ ramp lại khi có resource budget được duyệt.

## 47. Cutover gates: điều kiện cần đồng thời

Một proposal về gate (ngưỡng thực tế do business owner phê duyệt):

| Gate | Tiêu chí |
|---|---|
| Data coverage | Backfill đạt mọi partitions cần thiết, không có log gaps |
| Consistency | CDC lag trong freshness SLO |
| Semantic | Không còn mismatch severity cao; eligible mismatch trong ngưỡng |
| Comparable coverage | Đủ tỷ lệ/strata, không che bằng INCONCLUSIVE |
| API behavior | Point/range/filter/pagination/search contract đạt |
| Tenant security | Không có cross-tenant access, role phù hợp |
| Performance | B p95/p99/error/throughput trong target |
| Cost | Candidate read budget và write amplification chấp nhận |
| Operations | Dashboards, alerts, runbooks, rollback ready |
| Recovery | Backups và migration checkpoint phù hợp rollback horizon |

### 47.1. Một tỷ lệ tổng không thay gate theo severity

99.999% match vẫn không chấp nhận nếu 0.001% còn lại là user T17 đọc được Order của T18.

### 47.2. Cần thời gian đủ dài

Một giờ traffic có thể không cover batch jobs, monthly reports, rare filters hay di chuyển TTL. Kết hợp offline tests và các chu kỳ thực tế.

### 47.3. Gate phải được lưu như quyết định thay đổi

Lưu date, owners, code build, query contract versions, sample coverage, mismatch/inconclusive evidence và rollback plan, không chỉ ảnh chụp một dashboard.

### 47.4. Có manual override được kiểm soát

Một số intentional semantic changes có thể cho phép cutover dù raw diff; nhưng override phải có owner/justification và tests mới, không xóa mismatches khỏi metrics.

## 48. Khi B bắt đầu phục vụ user: canary và rollback

### 48.1. Routing có sticky cohort

Chọn một tập user/tenant theo policy, tránh flip-flop mỗi request nếu consistency/session behavior phụ thuộc route.

### 48.2. Theo dõi response thực

Khi B là authority, các errors/latency B ảnh hưởng user; phải có rollback decision nhanh. Đừng chỉ dựa trên shadow monitor cũ.

### 48.3. Rollback read route không rollback data

Chuyển GET trở lại A có thể nhanh nếu A vẫn được cập nhật và hợp lệ. Nhưng nếu ứng dụng đã chuyển writes sang B hoặc dừng CDC tới A, rollback còn là một migration khác.

### 48.4. Dual-write và shadow là workflow khác

Shadow read không sửa B. Nếu cutover cần writes mới sang B, bảo đảm dual-write/outbox protocol, idempotency và reverse sync đã được thiết kế riêng.

### 48.5. Retire A có điều kiện

Sau canary 100%, vẫn cần backup, retention, rollback horizon, audit/consumer inventory trước khi xóa A hoặc tắt data sync.

## 49. Kiểm thử non-interference bằng quan sát side effects

Một test trên môi trường cô lập:

~~~text
Given: canonical A and candidate B, no side-effecting dependencies.
When: run N shadow read queries with known intents.
Then:
  business writes A == 0
  business writes B == 0
  payments/emails/webhooks == 0
  cache SET/DEL/EXPIRE commands == 0 (if forbidden by contract)
  user-visible A responses unchanged
  candidate query calls bounded
  metrics classify results, errors and skips
~~~

### 49.1. Kiểm tra bằng quyền DB

Cấp read-only credentials cho B; cố tình chạy query mutation trong test và assert authorization denied. Không làm destructive tests trên production.

### 49.2. Spy/mocks cho downstream side effects

Trong integration tests, thay Payment/SMTP/Kafka publishers bằng spies và assert không có calls; chặn egress tới production endpoints.

### 49.3. A/B interference test

So distribution p95/p99, CPU, DB read capacity và errors của A khi shadow off/on dưới cùng offered load. Không chỉ assert status code 200.

### 49.4. Failure injection

B timeout, connection refused, slow scan, malformed JSON, CDC lag, candidate missing key, queue full, metric collector unavailable; A response phải giữ nguyên.

### 49.5. Internal side effects cần phân loại

GET Redis có thể làm LRU accounting hoặc Cassandra read repair xảy ra. Không cam kết physical database bytes bất biến nếu engine tự maintenance; mục tiêu là no business mutations và bounded operational effects.

## 50. Những sai lầm dễ gặp

| Sai lầm | Vì sao nguy hiểm | Thay thế |
|---|---|---|
| Mirror toàn HTTP GET | GET có thể ghi lastViewedAt/analytics | Pure query port allowlist |
| Dùng cùng admin DB credential | Shadow có khả năng mutate dữ liệu | Read-only scoped identity |
| Gọi B trên critical path | B timeout khiến A response chậm | Async bounded dispatch |
| CallerRunsPolicy khi queue đầy | Request thread trực tiếp chạy B | Reject-and-skip nonblocking |
| Mismatch sau CDC lag = migration bug | Hai bản ở hai versions khác | Watermark/eligibility |
| B stale nhưng vẫn MATCH | Dashboard gian lệch | INCONCLUSIVE riêng |
| Ignore tất cả null/missing | Che lỗi mapping | Field semantics versioned |
| Sort mọi arrays | Che sai business order | Ordered/set/multiset policy |
| So currency bằng double | Mất precision hoặc sai đơn vị | BigDecimal/integer minor units |
| Copy A page token sang B | Opaque cursor khác engine | Semantic window/tie-break |
| Dừng DynamoDB query ở empty page | Có thể còn LastEvaluatedKey | Follow continuation token |
| So search score đúng từng bit | Ranking engines/analyzers khác | Relevance/overlap contract |
| Shadow GETEX Redis | Thay TTL khi chỉ định so đọc | GET-only path |
| MongoDB aggregation có $merge | Thực hiện write | Stage allowlist |
| Comparator tự repair B | Nảy sinh side effects/race | Separate migration writer |
| Queue shadow vô hạn | OOM/retry storms | Hard queue and QPS caps |
| Log raw A/B responses | PII/credential leak | Aggregate + restricted samples |
| Chỉ lấy hot keys | Bỏ sót legacy/rare records | Stratified + offline |
| Dùng 99.9% match làm cutover duy nhất | Có thể che tenant leak | Severity, coverage, performance gates |
| Tắt source A ngay sau canary | Mất rollback path | Retention/rollback plan |

## 51. Bài tập 1 — thiết kế luồng shadow không thay response

Một API GET /orders/O101 đang đọc MongoDB model A. Model B là DynamoDB single-table, cần hai Query calls để dựng một OrderView. Yêu cầu người dùng **không thấy khác biệt dù B timeout**.

1. Vẽ sequence diagram từ HTTP request đến response A.
2. Chỉ rõ khi nào schedule B và khi nào user nhận A.
3. Nếu B mất 5 giây và A mất 50 ms, response latency phải phụ thuộc vào đâu?
4. Nếu queue shadow đầy, bạn chọn reject-and-skip hay chạy B trên request thread? Vì sao?
5. B cần read-only IAM actions nào?
6. Metrics phải phân biệt skipped, timed out, match và mismatch ra sao?

## 52. Bài tập 2 — GET có tác dụng phụ

Một method hiện tại:

~~~java
public Order getOrder(String id) {
    Order order = repository.findById(id);
    repository.updateLastViewedAt(id, clock.instant());
    auditPublisher.publish("ORDER_VIEWED", id);
    return order;
}
~~~

1. Vì sao gọi lại method này trong shadow path là sai?
2. Đề xuất tách pure query interface khỏi interaction/analytics.
3. Nếu A GET vẫn update lastViewedAt do business policy hiện hành, có được để B làm vậy lần thứ hai không?
4. Nếu shadow principal được cấp quyền read-only, method trên sẽ lỗi ở đâu?
5. Nếu auditPublisher vẫn có quyền publish, read-only DB credential có ngăn được side effect không?
6. Thiết kế integration test assert không có UPDATE/audit publish do shadow.

## 53. Bài tập 3 — null, missing và default

Mô hình A có:

~~~json
{"orderId":"O1", "couponCode":null, "paid":false, "items":[]}
~~~

Mô hình B có:

~~~json
{"orderId":"O1", "paid":null}
~~~

1. Trường couponCode nên được coi tương đương hay khác? Hãy nêu điều kiện của contract.
2. paid=false và paid=null có thể khác nghiệp vụ như thế nào?
3. items missing có được chuẩn hóa thành empty list không?
4. Thiết kế canonical representation giữ trạng thái MISSING/NULL trước khi áp policy.
5. Nếu normalizer tự đặt totalMinor=0 khi field missing, rủi ro là gì?
6. Làm sao gắn contractVersion vào metrics khi policy thay đổi?

## 54. Bài tập 4 — version và CDC lag

Timeline:

~~~text
10:00:00.000 A returns O101 version 8.
10:00:00.020 A updates O101 to version 9.
10:00:00.050 CDC applies version 9 to B.
10:00:00.080 B returns version 9.
~~~

1. A và B trả khác status thì có thể kết luận B sai không?
2. Một sourceVersion giúp phân loại hai results thế nào?
3. Nếu B đang v7 khi A ở v8 và policy freshness 2 giây, cần biết thêm những mốc nào?
4. Nếu B v8 nhưng items nội bộ vẫn v7, sourceVersion ở header đủ chưa?
5. Thiết kế một delayed comparison sau watermark phù hợp.
6. Trường hợp nào đánh dấu SEMANTIC_MISMATCH, trường hợp nào INCOMPARABLE_VERSION?

## 55. Bài tập 5 — backfill và CDC race

Một backfill job đọc O101 v4. Trước khi nó ghi B, CDC projector đã ghi O101 v6. Backfill tiếp tục overwrite B thành v4.

1. Đây là lỗi của comparator hay migration writer?
2. Dùng conditional upsert theo sourceVersion như thế nào để tránh regress?
3. Nếu CDC events đến lặp và sai thứ tự, ứng dụng B cần idempotency/version handling gì?
4. Nếu B thiếu O101, phân biệt “chưa backfill” với “lệch dữ liệu” ra sao?
5. Metrics nào giúp thấy candidate_applied_version đã đi lùi?
6. Shadow comparator có được tự ghi lại O101 v6 không?

## 56. Bài tập 6 — so sánh list/set/multiset

Kết quả:

~~~text
A: [SKU-A, SKU-B, SKU-B]
B: [SKU-B, SKU-A, SKU-B]
C: [SKU-A, SKU-B]
~~~

1. A và B có bằng nhau nếu contract là ordered list?
2. A và B có bằng nhau nếu contract là multiset?
3. A và C có bằng nhau nếu contract là set?
4. Nếu duplicates là vi phạm nghiệp vụ, được phép normalize thành set trước compare không?
5. Order items có lineNo; policy nào hợp lý hơn?
6. Chọn canonical key và deterministic tie-break cho item ordering.

## 57. Bài tập 7 — pagination khi đổi partition key

A trả orders sorted by (createdAt desc, orderId desc) dùng offset pagination. B chia dữ liệu theo tháng, trả continuation token riêng theo từng partition.

1. Vì sao không copy page token A sang B?
2. Nếu pageSize=20, B cần merge các tháng liên quan ra sao để lấy top 20?
3. Nếu createdAt trùng nhau, cần tie-break gì?
4. Nếu một Query page rỗng nhưng còn continuation token, adapter nên làm gì?
5. Khi writes diễn ra giữa trang 1 và trang 2, những race nào có thể tạo duplicates/skips?
6. Đề xuất offline test trên frozen snapshot và online INCONCLUSIVE policy.

## 58. Bài tập 8 — so tiền bằng BigDecimal

Mô hình A lưu totalMinor=123456 (currency USD, minor unit=cent); B lưu Decimal128("1234.56") major units.

1. Tạo canonical monetary type phù hợp.
2. A và B có tương đương không sau conversion theo currency scale?
3. Nếu B lưu 1234.559999, có nên dùng epsilon=0.01 để bỏ qua?
4. Rounding mode khác nhau có thể tạo sai lệch thế nào?
5. Vì sao không dùng float/double cho money equality?
6. Với một currency không có minor decimals, conversion policy cần thay đổi ra sao?

## 59. Bài tập 9 — timestamp/TTL/soft delete

Hai records:

~~~text
A expiresAt=2026-11-14T08:00:00Z, deletedAt=null.
B expiresAt=2026-11-14T15:00:00+07:00, deletedAt absent.
~~~

1. expiresAt có cùng instant không?
2. deletedAt null và absent nên so theo policy nào?
3. Nếu một bên vật lý vẫn giữ key đã expire, có phải semantic mismatch không?
4. Khi query “active at now”, vì sao cần cùng referenceInstant?
5. Nếu TTL scheduler chạy khác tốc độ, metric nào nên phản ánh stale/lag?
6. Thiết kế test cho boundary ngay trước và ngay sau expiration.

## 60. Bài tập 10 — tính tỷ lệ từ nhiều mẫu số

Một shadow run:

~~~text
Selected intents:       20,000
Executed B queries:     18,000
Comparable pairs:       15,000
Matches:                14,970
Semantic mismatches:        30
Not ready / stale:       2,000
Candidate errors:        1,000
Skipped by budget:       2,000
~~~

1. Tính EligibleMatchRate.
2. Tính ComparableCoverage trên selected.
3. Tính CandidateErrorRate trên selected.
4. Tính tỷ lệ skipped do budget.
5. Vì sao không gọi (20.000 - 14.970)/20.000 là tỷ lệ semantic mismatch?
6. Nếu 30 mismatches đều là tenant isolation, tỷ lệ 0,2% có chấp nhận cutover không?
7. Những mẫu số nào cần phân biệt theo queryClass/tenant tier?

## 61. Bài tập 11 — Java bounded executor

Một hệ có 20.000 GET requests/sec và muốn mirror 5%. Shadow executor có 4 threads, queue=256 và mỗi B query mất trung bình 200 ms.

1. Tính tốc độ shadow attempts dự kiến khi mirror 5%.
2. Nếu mỗi thread xử lý tuần tự, 4 threads có thể xử lý khoảng bao nhiêu B queries/sec ở latency trung bình đó, bỏ qua overhead?
3. Điều gì xảy ra với queue nếu offered rate cao hơn throughput?
4. Vì sao CallerRunsPolicy nguy hiểm đối với request thread A?
5. Thiết kế rate limit/sampling giảm tải tự động.
6. Nếu B query timeout nhưng underlying server vẫn chạy, việc gọi future.cancel() có đủ không?
7. Viết danh sách driver-level timeouts và metrics cần cấu hình.

## 62. Bài tập 12 — MongoDB aggregation và side effects

Một developer muốn so truy vấn listOrders từ MongoDB A với collection B:

~~~javascript
db.order_headers.aggregate([
  {$match: {tenantId: "T17"}},
  {$lookup: {from: "order_items", localField: "orderId",
             foreignField: "orderId", as: "items"}},
  {$merge: "comparison_results"}
])
~~~

1. Stage nào gây side effect?
2. Vì sao một aggregation chưa chắc read-only?
3. Thiết kế allowlist stages an toàn hơn cho pure query.
4. Khi lookup items, còn thiếu filter/tenant isolation nào?
5. Nếu header và items từ hai versions khác nhau, classification nào phù hợp?
6. Nếu query B trả quá nhiều docs, dùng limit/maxTime/index review thế nào?

## 63. Bài tập 13 — DynamoDB GSI và pagination

A đọc strongly consistent base table GetItem; B Query trên GSI eventual, có items được cập nhật bởi CDC.

1. Có thể yêu cầu Strongly Consistent Read trên mọi GSI không?
2. Khi A version=9, B version=8, có nên coi là semantic mismatch ngay không?
3. Nếu Query B trả Items=[] và LastEvaluatedKey khác null, adapter nên làm gì?
4. Một B logical query cần 10 SDK Query calls; physical read amplification được tính thế nào?
5. Nếu B throttling làm A p99 tăng vì chung thread pool, non-interference đã bị vi phạm ở đâu?
6. Thiết kế IAM read-only của shadow principal.

## 64. Bài tập 14 — Cassandra partition bucketing

A lưu orders_by_customer với partition customerId. B chuyển sang orders_by_customer_month theo customerId+month.

1. Nếu GET last20 của A trả nhiều orders cuối tháng trước, reader B query tháng hiện tại có đúng contract không?
2. B cần merge các partitions nào và có thể dừng lúc nào?
3. Cần stable sort/tie-break ra sao?
4. Cassandra read repair, tombstone scanning có thể gây operational side effects gì?
5. Nếu consistency levels khác nhau, metric stale/incomparable cần ghi gì?
6. Làm sao đo hot-partition cost khi shadow reads?

## 65. Bài tập 15 — Redis GET so với GETEX

Một migration đổi key session từ session:U101 sang tenant:T17:session:U101.

~~~text
A: GET session:U101
B: GETEX tenant:T17:session:U101 EX 1800
~~~

1. B có còn thuần đọc theo business state không?
2. Tác động tới TTL/session expiration là gì?
3. Nếu cả hai GET trả cùng value, comparator đã chứng minh không có side effect chưa?
4. Thay GETEX bằng cách đọc nào an toàn hơn?
5. Redis GET có thể thay đổi metadata nội bộ gì?
6. ACL/command permissions nào cần chặn trong shadow worker?

## 66. Bài tập 16 — search index v1/v2

Index A dùng tokenizer cũ, B dùng synonyms và boost mới. Truy vấn “wireless earbuds” trả:

~~~text
A top5 = [P1,P2,P3,P4,P5]
B top5 = [P2,P1,P6,P3,P4]
~~~

1. Exact list equality có phải metric duy nhất hợp lý không?
2. Tính tập giao top5 và overlap@5.
3. Nếu contract muốn cải thiện relevance, cần đánh giá bằng metric nào ngoài overlap?
4. Nếu B thiếu P1 vì CDC lag, phải phân loại thế nào?
5. Nếu B trả unauthorized products, severity ra sao dù overlap cao?
6. Những index mappings, analyzers và refresh policies nào cần ghi trong experiment report?

## 67. Bài tập 17 — tenant isolation regression

Hai tenants T17 và T18 đều có orderId=O101. A query có tenantId=T17; B adapter chỉ filter orderId=O101.

1. Dữ liệu B có thể trả sai gì?
2. Vì sao tỷ lệ mismatch overall 0.01% vẫn có thể là stop-the-line?
3. Test fixtures cần thiết kế thế nào để phát hiện ID collision?
4. Dùng authorization scope và read-only workload identity ra sao?
5. Những fields nào cần redact/HMAC trong mismatch evidence?
6. Shadow comparator có được dùng data của T18 để trả fallback cho T17 không?

## 68. Bài tập 18 — sampling và độ tin cậy thống kê

Một hệ có 5 triệu unique keys nhưng top 1% keys nhận 50% GET traffic. Bạn mirror ngẫu nhiên 1% **requests**, thu được 100.000 comparisons và không thấy mismatch.

1. Có thể tuyên bố chắc chắn mọi key đều đúng không?
2. Vì sao request-level random sampling thiên về hot keys?
3. Một sample theo unique key khác sample theo request ra sao?
4. Đề xuất stratified sampling cho tenant tier, data age, record size và query shape.
5. Nếu 100.000 observations gồm 90.000 lần đọc cùng một hot key, mô hình independent Bernoulli còn phù hợp không?
6. Trong trường hợp samples độc lập phù hợp, quy tắc gần đúng 3/n cho zero mismatches cho upper 95% bound là bao nhiêu?
7. Báo cáo risk của rare legacy records thế nào khi chưa có offline scan?

## 69. Bài tập 19 — test non-interference trong môi trường cô lập

Bạn cần thử một shadow compare service Java có candidate MongoDB và Redis, nhưng production flows còn có notification, analytics và Payment Provider.

Thiết kế một test plan gồm:

1. Baseline A response khi shadow off.
2. Shadow on với B success.
3. Shadow B timeout và malformed document.
4. Queue full và telemetry collector unavailable.
5. MongoDB read-only principal từ chối write.
6. Redis ACL chặn SET/DEL/EXPIRE và không dùng GETEX.
7. Spies xác minh không gửi payment/email/Kafka business event.
8. Network egress policies khiến side-effecting API không truy cập được.
9. So p99 A latency, CPU, query capacity khi shadow off/on dưới cùng load.
10. Kill switch tắt B ngay mà không thay routing A.
11. Không chứa raw PII/authorization trong logs/traces.

## 70. Bài tập 20 — quyết định có được cutover hay không

Một migration MongoDB → DynamoDB đã chạy shadow trong bảy ngày:

~~~text
Sampled reads:                 1,000,000
Comparable:                     920,000
Matches:                        919,990
Semantic mismatches:                 10
Candidate stale:                50,000
Candidate query errors:         20,000
Skipped by budget:              10,000

Critical mismatch detail:
  8 differences in coupon totalMinor
  2 cross-tenant result leaks

Candidate p99:
  Point GET = 55ms
  List query = 2,000ms

Backfill:
  95% partitions done
  5% legacy partitions not complete
~~~

1. Tính eligible match rate, comparable coverage, candidate error rate và skip rate.
2. Chỉ nhìn eligible match rate rất cao có đủ quyết định cutover không?
3. Cross-tenant leak có thể chấp nhận theo tỷ lệ thống kê không?
4. List query p99 cao có tác động tới canary thế nào?
5. Backfill 95% ảnh hưởng tới coverage và readiness thế nào?
6. Đề xuất thứ tự ưu tiên sửa: tenant filter, monetary mapping, query plan, CDC/backfill, instrumentation.
7. Những điều kiện bắt buộc nào cần hoàn thành trước canary?
8. Khi B canary 1%, đề xuất rollback threshold và owner.
9. Tại sao không tắt A và xóa dữ liệu cũ ngay khi canary 1% thành công?
10. Tạo mẫu decision record gồm evidence, known gaps, contract version, risks và sign-off.

## 71. Tổng kết: đối chiếu đáng tin phải không làm thay đổi hệ mà nó đang kiểm chứng

Khi di chuyển mô hình NoSQL, shadow query là một công cụ giúp phát hiện sai lệch **trước khi người dùng dựa vào mô hình mới**. Nhưng giá trị của nó phụ thuộc vào hai điều kiện độc lập: **phép so phải đúng nghĩa** và **phép đo không gây side effect hoặc làm hỏng đường chính**.

Các nguyên tắc trọng tâm:

1. **So theo business query contract.** Không so MongoDB document với DynamoDB items hay Cassandra rows bằng raw equality khi mô hình dữ liệu khác nhau.
2. **A là response authority trong shadow phase.** B error/timeout/mismatch không được sửa response A hoặc kích hoạt mutation.
3. **GET không tự thuần đọc.** Application handlers có thể ghi lastViewedAt, phát events, cập nhật Redis TTL hoặc gọi downstream; dùng pure read port và query allowlist.
4. **Read-only credentials là hàng rào mạnh nhưng chưa đủ.** Cần network egress restrictions, bỏ business publishers và kiểm soát instrumentations.
5. **Không thể bảo đảm zero physical effect tuyệt đối.** Reads có thể tiêu tốn capacity, làm nóng cache, gây read repair hoặc lazy expiry; đo và giới hạn operational effects.
6. **Dữ liệu phải có eligibility trước khi so.** Backfill coverage, CDC watermark, sourceVersion và snapshot/checkpoint tránh false mismatches do hai trạng thái khác thời điểm.
7. **INCONCLUSIVE khác MATCH.** Stale candidate, not-ready partition, timeout, queue skip và incomparable versions là các trạng thái riêng, không được che.
8. **Canonicalization có policy rõ.** Null/missing/defaults, enum mapping, currency precision, timestamps, TTL và dữ liệu legacy đều cần contract version.
9. **Định nghĩa list/set/multiset và stable ordering.** Đừng sort bừa hay toSet trước compare nếu duplicate/order có ý nghĩa nghiệp vụ.
10. **Pagination cần query semantics giống nhau.** Offset, cursor, LastEvaluatedKey, search_after và partition merge không thể tráo tokens tùy tiện.
11. **Tách semantic correctness khỏi hiệu năng.** B trả đúng vẫn có thể quá chậm, tốn read capacity hoặc gây load ảnh hưởng A.
12. **Tách offline và online validation.** Offline snapshot scan tìm missing cold records; online sampled shadow tìm lỗi access patterns và user queries thực.
13. **Sampling có thể sai lệch.** Hot keys/large tenants chiếm traffic; cần stratified sampling và coverage báo minh bạch thay vì chỉ một tỷ lệ tổng.
14. **Bounded mọi tài nguyên shadow.** Queue, concurrency, query duration, result bytes, logs, cost và retries; queue đầy thì skip, không chạy B trên request thread.
15. **Telemetry không được lộ dữ liệu.** Dùng queryClass, outcome, version và cohort; raw IDs/payloads chỉ trong restricted evidence workflow khi được cho phép.
16. **Có severity và ownership cho mismatch.** Sai tổng tiền, thiếu đơn hàng và cross-tenant leaks quan trọng hơn vài khác biệt metadata không ảnh hưởng nghiệp vụ.
17. **Comparator không được tự repair B.** Nếu lỗi nằm ở CDC/backfill writer, khắc phục qua migration workflow có audit, version checks và kiểm thử.
18. **Feature flag và cutover gates là bắt buộc.** Match rate phải đi cùng comparable coverage, lag, security, p99, errors, cost và rollback readiness.
19. **Canary là giai đoạn khác shadow.** Khi B thực sự trả response, phải quan sát user-visible metrics, routing và rollback có kiểm soát.
20. **Đừng retire A quá sớm.** Khi writes đã chuyển hoặc sync bị tắt, rollback read route có thể không còn đơn giản; cần kế hoạch giữ nguồn và dữ liệu hợp lệ trong rollback horizon.

Trước mỗi đợt tăng shadow traffic hoặc canary, hãy hỏi:

> **“Hai truy vấn đã đọc cùng một trạng thái có thể so sánh chưa, chúng có thật sự cùng ý nghĩa nghiệp vụ không, và nếu mô hình B chậm/sai/không có dữ liệu thì có bất kỳ cách nào nhánh đối chiếu gây thêm ghi, phát tác dụng phụ hoặc ảnh hưởng đến người dùng đang dùng mô hình A không?”**










