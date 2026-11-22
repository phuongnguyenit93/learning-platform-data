# Chuyển quyền ghi, định tuyến đọc và tiêu chí chấp nhận cắt chuyển

Một hệ thống dùng NoSQL cần chuyển dữ liệu từ cụm A sang cụm B mà người dùng vẫn đặt hàng liên tục. Nhóm kỹ thuật đã backfill hàng triệu documents, bật CDC để sao chép thay đổi và thấy số bản ghi ở hai cụm gần bằng nhau. Tuy nhiên, nếu API ghi đơn mới lên B trong khi một worker cũ vẫn ghi lên A, hai hệ có thể cùng trở thành “nguồn đúng” cho cùng một Order. Nếu client đọc B trước khi CDC bắt kịp, người dùng có thể không thấy đơn vừa tạo. Nếu cắt chuyển xong mới phát hiện lỗi và định tuyến ngược về A, những write chỉ tồn tại ở B có thể bị mất.

Vì vậy, **cutover** trong hệ phân tán không chỉ là sửa connection string hoặc đổi DNS. Đó là thao tác chuyển **quyền chấp nhận ghi**, điều khiển **đường đọc**, phối hợp **trạng thái dữ liệu**, và xác nhận các **điều kiện kinh doanh/khả năng phục hồi** trước khi công bố hoàn thành.

Bài học thuộc chương **Di chuyển và thay đổi**, module **Database No SQL**, giải thích quy trình từ chuẩn bị nguồn/đích, đồng bộ và quan sát, chuyển writer authority, chuyển dần read traffic, đến go/no-go, rollback/roll-forward và hậu kiểm.

Các ví dụ MongoDB, Cassandra/ScyllaDB, DynamoDB, Redis và search/read model chỉ minh họa **các lớp quyết định**. Không có cú pháp hoặc guarantee chung cho mọi sản phẩm; cơ chế fencing, CDC, snapshot, consistency và endpoint cutover phải được xác minh theo **engine, phiên bản, topology và ứng dụng thật**.

> **Bất biến trung tâm:** Tại một thời điểm được định nghĩa, đối với một business key và một scope cutover, chỉ một **nguồn ghi có thẩm quyền** được quyền xác nhận thay đổi; một request được trả thành công phải có kết quả nghiệp vụ có thể truy ra sau lỗi mạng, retry, rollout hoặc rollback.

## 1. Cutover khác copy dữ liệu và deploy ứng dụng

Phân biệt ba hoạt động:

| Hoạt động | Câu hỏi | Điều chưa được chứng minh |
|---|---|---|
| **Data migration/backfill** | Đã chuyển dữ liệu lịch sử? | Write mới có đi đúng? |
| **Deploy ứng dụng** | Code/client đã dùng cấu hình mới? | Workloads cũ đã ngừng ghi? |
| **Cutover quyền ghi/đọc** | Hệ nào là source of truth và client được route tới đâu? | Dữ liệu tại đích có hợp lệ, đủ mới và rollback được? |

Một bản backfill 100% không xác nhận CDC đã áp xong mọi update. Một deploy báo 100% ready không chắc cron jobs, queue consumers, admin scripts hoặc mobile clients đã ngừng dùng endpoint cũ. Một read benchmark nhanh không chứng minh mọi user đều thấy chính xác trạng thái sau write.

## 2. Mô hình hóa hai cụm theo quyền, không chỉ vị trí

Gọi:

- **A**: cụm NoSQL nguồn đang phục vụ.
- **B**: cụm đích được chuẩn bị.
- **W**: tập API/worker có thể ghi.
- **R**: tập API/client có thể đọc.
- **Sync**: cơ chế backfill + CDC/event propagation, nếu dùng.
- **Control plane**: nơi quyết định epoch/owner/routing và phát cấu hình.
- **Recovery ledger**: thông tin idempotency/commit outcome để đối soát.

Trạng thái logic:

~~~text
Trước:
  authoritativeWrite = A
  productionRead      = A
  B = shadow/replica candidate

Sau:
  authoritativeWrite = B
  productionRead      = B (theo policy của từng operation)
  A = frozen archive, rollback candidate hoặc decommissioned
~~~

Mục tiêu không chỉ thay giá trị `authoritativeWrite` mà phải bảo đảm **mọi tác nhân thực thi** tuân theo quyết định đó, kể cả những instance chưa nhận cấu hình mới.

## 3. Các bất biến phải viết ra trước khi đổi writer

Ví dụ hệ đặt hàng:

1. Một `orderId` chỉ có một kết quả commit có thẩm quyền.
2. Số ghế/stock được giữ không vượt capacity.
3. Cùng một `idempotencyKey` không tạo hai đơn hoặc thu tiền hai lần.
4. Customer tenant A không xem/sửa dữ liệu tenant B.
5. Một API cần read-your-writes phải thấy kết quả ghi theo hợp đồng.
6. Delete/TTL/privacy suppression phải có hiệu lực cả sau replay/rollback.
7. `OrderConfirmed` phải có dữ liệu nguồn và outbox/reconciliation state thích hợp.
8. Các write đã ACK trước cutover không được mất khi chuyển.
9. Các write đã ACK sau cutover không được mất khi xử lý rollback.

Cũng phải định nghĩa **scope**: toàn cluster, một tenant, một partition range hay một tập business keys. Có thể chuyển từng tenant độc lập, nhưng chỉ khi không có invariant hoặc unique constraint xuyên các tenant trong scope.

## 4. Những kiểu cutover thường gặp

| Phương án | Ý tưởng | Chi phí/điểm khó |
|---|---|---|
| **Dừng ghi ngắn (write freeze)** | Ngừng nhận write, đuổi CDC, khóa A, bật B | Có cửa sổ giảm availability nhưng dễ lập consistent cut |
| **Blue/green với single writer** | B shadow, chỉ A active; sau đó handoff | Cần fencing và quản lý in-flight |
| **Chuyển dần theo tenant/key** | Mỗi scope có owner A hoặc B | Routing, cross-key transactions, owner metadata phức tạp |
| **Dual writes chủ động** | App gửi write tới cả A và B | Partial commit, out-of-order, duplicate effects khó kiểm soát |
| **Source → outbox/CDC → target** | Một nguồn ghi, B bắt kịp bất đồng bộ | Lag và checkpoint/barrier correctness |
| **Read-first cutover** | Đọc B trước, ghi vẫn ở A | Chỉ phù hợp nếu freshness contract cho phép |

Không có lựa chọn tốt nhất độc lập với yêu cầu downtime, RPO, throughput, data model và consistency. Một phương án ít downtime hơn thường đổi lấy **độ phức tạp protocol cao hơn**, không phải miễn phí.

## 5. Quyền ghi có thẩm quyền: single-writer là một thuộc tính được thực thi

**Single-writer authority** không có nghĩa chỉ chạy một process. Nhiều API instances có thể cùng ghi, miễn mọi write cho cùng một scope đều đi qua **nguồn có thẩm quyền duy nhất** và tuân các điều kiện atomically enforced.

Sai:

~~~text
Operator flips DNS to B.
Old pod still resolves A.
Old pod commits Order O1 on A.
New pod commits Order O2 on B.
Both return HTTP 200.
~~~

Đây là nguy cơ **split brain ở application layer**, dù bản thân A và B đều khỏe. Việc cập nhật env var, DNS hoặc flag là *gợi ý route*, không đủ để rút quyền ghi khỏi tác nhân cũ.

Controls nên gồm:

- **Owner registry/epoch** cho từng scope.
- **Write gate** ở API hoặc storage boundary, ưu tiên có enforcement tại nơi commit.
- **Fencing token** khiến owner cũ không thể commit sau handoff.
- Thu hồi/giới hạn credentials hoặc network permission của A theo kế hoạch.
- In-flight operation handling và idempotency ledger.
- Audit ai đổi owner, lúc nào, recovery position nào.

## 6. Fencing epoch và token: ngăn writer cũ trở lại

Một cơ chế logic:

~~~text
Epoch 41:
  owner(scope X) = A

Cutover:
  transition under authoritative control
  epoch becomes 42
  owner(scope X) = B

Write request carries epoch.
Storage/gate rejects stale epoch 41.
~~~

Nếu worker A bị stop-the-world pause rồi chạy lại với epoch cũ, **stale write phải bị từ chối tại một nơi không chịu ảnh hưởng việc A chưa reload config**.

Ví dụ ý tưởng dùng conditional transaction trong một **authority store có semantics phù hợp**:

~~~text
if persistedOwner(scope) == A and epoch == 41:
    atomically set owner(scope) = B, epoch = 42
else:
    reject transition
~~~

Nhưng **chỉ kiểm tra epoch tại client trước khi ghi không đủ**: giữa lúc check và commit, quyền đã có thể đổi. Cần atomic fencing tại DB/gateway có thẩm quyền, hoặc một protocol freeze/drain khiến lệnh cũ không thể commit. Nếu A và B là hai storage systems độc lập, một registry không tự tạo atomic commit trên cả hai; phải thiết kế điểm cưỡng chế và failure handling thật.

## 7. Lease timeout không tự giải split brain

Một writer có lease 30 giây. Khi network partition, owner cũ có thể không nhận được revoke, bị GC pause và sau đó thức dậy. Nếu nó vẫn có credentials ghi A, việc lease “hết hạn” tại control plane không thể tự ngăn write cũ.

Cần phân biệt:

- **Lease:** quyết định ai *nên* được ghi theo thời gian.
- **Fencing token:** chứng minh write đến từ generation mới, bị kiểm tra ở nơi chấp nhận thao tác.
- **Write revocation:** chặn write ở endpoint cũ sau handoff.
- **Clock:** không dùng đồng hồ hệ điều hành trên hai nodes làm bằng chứng tuyệt đối về thứ tự commit.

Thứ tự epoch/token phải monotonic và durable theo semantics của authority mechanism. Với hệ không hỗ trợ enforcement cần thiết, chọn **freeze/drain + cutover có kiểm soát**, thay vì tuyên bố zero-downtime bằng một lease trong RAM.

## 8. Vì sao dual write trực tiếp dễ tạo trạng thái sai?

Tình huống:

~~~text
App writes Order O1 to A -> SUCCESS.
App writes Order O1 to B -> TIMEOUT.
App returns failure.
Client retries.
A may already have committed O1.
B may or may not have committed O1.
~~~

Hoặc:

~~~text
Update v10 reaches B after update v11.
B ends up with stale v10 unless version checks prevent it.
~~~

Dual write có thể có ích trong một giao thức migration được thiết kế chặt, nhưng phải trả lời:

1. Nguồn nào quyết định success của user?
2. Nếu một write commit và write kia fail, xử lý thế nào?
3. Nếu ACK bị mất, làm sao xác định outcome?
4. Có thứ tự theo business key không?
5. Delete và TTL được đồng bộ thế nào?
6. Có idempotency, retry/backoff và reconciliation không?
7. Khi cắt writer, có thể chấm dứt tất cả old-path writes ra sao?

Với đa số workflow, **single authoritative write + durable outbox/CDC đến B** có cấu trúc vận hành dễ lý giải hơn hai writes cạnh tranh.

## 9. Read routing không phải write authority

Read path có thể khác write path theo từng endpoint:

~~~mermaid
flowchart LR
    API["Application"] --> ROUTE{"Read router"}
    ROUTE -->|Authoritative| A[("Source A")]
    ROUTE -->|Shadow or allowed eventual| B[("Target B")]
    A --> SYNC["CDC / change log"]
    SYNC --> B
    WRITE["Write router / gate"] -->|Only authorized owner| A
~~~

Trong giai đoạn chưa cutover writer, B có thể phục vụ **shadow reads** hoặc reads chấp nhận độ cũ. Nhưng API hiển thị kết quả cho user phải tuân đúng consistency/freshness contract.

Một số endpoint cần:

- Point read sau khi create/update: read-your-writes.
- Inventory/checkout confirmation: authoritative hoặc điều kiện nhất quán phù hợp.
- Catalog browse: eventual read trong freshness budget.
- Search analytics: có thể stale có khai báo.
- Permission/revocation checks: đòi policy cập nhật theo security contract.

**Không chuyển 100% reads sang B chỉ vì tổng record counts gần bằng nhau.** Phải có chứng cứ B đã đủ mới và có đúng index/schema/query semantics cho nhóm request đó.

## 10. Read-your-writes và session consistency khi di chuyển

Giả sử client POST thành công ở A lúc 10:00:00. B có CDC lag 4 giây. Nếu GET ngay lập tức route B, response có thể trả 404 hoặc trạng thái cũ.

Các lựa chọn:

- Giữ reads nhạy cảm ở A tới khi write authority chuyển.
- Dùng **session watermark/commit token**; chỉ đọc B khi projection đã áp tới token.
- Cho user đọc từ authoritative owner theo request/session.
- Cho API phản hồi trạng thái pending/asynchronous khi business contract cho phép.
- Sử dụng native strong read/quorum semantics nếu B hỗ trợ trong phạm vi đúng.
- Route fallback có kiểm soát mà không làm lộ dữ liệu cross-tenant.

**Global CDC lag trung bình thấp không bảo đảm read-your-writes trên từng partition**. Cần biết position per partition/key hoặc một barrier đủ mạnh cho read path đang dùng.

## 11. Read target cần được kiểm tra query và quyền độc lập

Source và target có thể có dữ liệu giống nhau nhưng hành vi đọc khác vì:

- Index không giống hoặc chưa build xong.
- Query planner khác do engine/version.
- Null vs missing field, collation, numeric precision.
- Pagination/order tie-breaker không ổn định.
- TTL/soft delete/tombstone semantics.
- Tenant filter/authorization rules thiếu ở target.
- Sort/aggregate behavior hoặc case-insensitive search khác.
- Data model transform khiến một key không khớp.
- Cache warm-up và pool/connection limits.

Chuyển read traffic cần test **correctness và performance**, không chỉ đồng bộ bytes. Đặc biệt, đổi read target có thể làm mất tính phân trang ổn định hoặc trả thông tin từ tenant khác nếu query builder thay đổi.

## 12. Backfill + CDC: điều kiện để B thực sự bắt kịp

Trước khi handoff, B thường cần hai nguồn dữ liệu:

1. **Historical snapshot/backfill** của dữ liệu đã tồn tại.
2. **Change stream/CDC/outbox** ghi các thay đổi phát sinh trong lúc backfill.

Một pipeline logic:

~~~mermaid
flowchart TD
    S["Choose supported snapshot boundary S"] --> B["Backfill historical data"]
    B --> C["Replay ordered changes after S"]
    C --> D["Catch-up to target barrier T"]
    D --> E["Reconcile keys/versions/invariants"]
    E --> F["Eligible for cutover decision"]
~~~

Điều khó không phải chỉ là copy hết bytes, mà phải chứng minh:

- Không có gap giữa snapshot và CDC start.
- Mỗi change có idempotency hoặc version rule khi replay.
- Update/delete được áp đúng thứ tự theo scope.
- Từng partition/shard có recovery watermark đáng tin.
- Backfill ghi chậm hơn CDC không ghi đè bản mới.
- Consumer có quyền đọc đủ history; retention không hết.
- Từng entity có schema/encoding đúng ở target.
- Manifest và checkpoint tồn tại bền sau worker crash.

**CDC lag gần 0 không có nghĩa B đầy đủ** nếu backfill bỏ sót keys hoặc một partition không còn nhận events.

## 13. Watermark: phân biệt offset, source version và applied version

Một hệ có thể có:

- **Source committed position**: mốc mà A đã xác nhận write.
- **Captured position**: mốc connector đã đọc log.
- **Published position**: mốc đã ghi vào transport/broker.
- **Applied position**: mốc B đã thực thi và ACK theo durability contract.
- **Verified position**: mốc có bằng chứng dữ liệu/contract tương ứng.

Ví dụ:

~~~text
Source committed:  offset 12.450
CDC captured:      offset 12.449
Broker published:  offset 12.448
B durable applied: offset 12.402
B reconciliation:  verified through 12.350
~~~

Trong ví dụ này, không thể nói “B đã bắt kịp 12.450”. Cần xác định **mốc theo partition/shard**, vì nhiều CDC partitions không tự có một global total order.

Một offset tăng đều không chứng minh every write applied nếu consumer có cơ chế skip lỗi sang DLQ hoặc phép update không idempotent. Watermark phải gắn với **error/completeness accounting**.

## 14. Barrier cutover: đóng đoạn lịch sử của A

Một **barrier** là mốc có semantics để nhóm vận hành biết mọi write hợp lệ thuộc giai đoạn A đã được xử lý hoặc có kế hoạch recovery rõ.

Ví dụ với write freeze:

~~~text
T0: Stop accepting new writes to A.
T1: Wait for in-flight A writes/unknown outcomes.
T2: Record source stable position/barrier P.
T3: Wait B durably applies all required changes <= P.
T4: Reconcile business state through P.
T5: Revoke A write authority; grant B writer authority.
T6: Resume new writes only at B.
~~~

Trình tự này chỉ minh họa. Một protocol cụ thể phải xác định liệu freeze được thực thi tại API, gateway hay storage, cách xử lý write đang bay, offset per shard và cách chuyển quyền nếu control plane gặp sự cố.

Nếu A vẫn có thể nhận ghi sau P, barrier P **không còn đủ** để chứng minh B có toàn bộ những write của A trước chuyển. Đó là lý do **fencing, drain và revoke** là phần bắt buộc của giao thức.

## 15. Điểm nguy hiểm: request in-flight ở thời điểm handoff

Giả sử một request bắt đầu ở A lúc 10:00:00, mất 10 giây vì queue hoặc network:

~~~text
10:00:00: request R starts at A (epoch 41)
10:00:03: owner registry switches to B (epoch 42)
10:00:08: request R commits on A if not fenced
10:00:10: R returns success
~~~

Nếu B đã lấy ownership và CDC đã đóng ở barrier trước 10:00:08, write của R có thể bị mất khỏi thế giới mới.

Hướng kiểm soát:

- **Close admission** để không phát sinh A operations mới.
- **Drain** tất cả operations đang xử lý theo deadline hợp lý.
- **Fence** stale writer ở điểm commit; không chỉ sửa app flag.
- **Resolve unknown outcomes** bằng stable operation IDs.
- **Capture last source position** chỉ sau khi đáp ứng cut conditions.
- **Dedup** các requests được gửi lại sau handoff.
- Không xóa A logs cho đến khi backup/reconciliation bảo đảm.

Với operations vượt deadline, cần xác định liệu cancel được commit, hoặc kết quả là **UNKNOWN**. Không tự đổi một timeout thành “chắc chắn không ghi”.

## 16. Timeout, idempotency và kết quả chưa rõ

Trường hợp:

~~~text
Client sends POST /orders with idempotencyKey=K1 to A.
A commits Order O1001.
Network drops before client receives response.
Cutover to B occurs.
Client retries K1 on B.
~~~

Nếu idempotency ledger không được sao chép/khôi phục và kiểm tra, B có thể tạo thêm Order O1002. Vì vậy:

- Deduplication state/idempotency key phải nằm trong **scope dữ liệu cần hội tụ**.
- Ledger cần lưu **intent fingerprint + final business outcome** khi phù hợp.
- Retry cùng key phải trả kết quả có thẩm quyền đã biết, không tạo intent mới.
- Nếu outcome còn UNKNOWN, phải reconcile với nguồn hoặc ledger trước hành động không đảo được.
- Provider side effects (payment/email) phải có stable external references và cơ chế đối soát.
- TTL của idempotency record phải đủ cho retry/cutover window.

**Không chỉ so đếm Orders trước/sau**: duplicate effect có thể xuất hiện ở hệ thanh toán hoặc event consumers.

## 17. Delete, TTL và tombstone không được bỏ qua

Backfill chỉ copy live documents có thể sai khi CDC replay:

~~~text
t0: A has customer C.
t1: Backfill exports C.
t2: Privacy request deletes C on A.
t3: CDC delete event delayed.
t4: B starts serving reads using backfilled C.
~~~

B có thể làm lộ record đã xóa. Cần:

- Durable delete/tombstone events trong sync path.
- Version/epoch checks để stale backfill không hồi sinh record.
- TTL policy và expiration timestamp phù hợp giữa A/B.
- Privacy suppression ledger bên ngoài data snapshot khi cần.
- Read authorization áp ở B, kể cả thời gian shadow/canary.
- Không chuyển read traffic khi deletion propagation chưa đạt contract.

Với LWW và timestamp-based merge, phải xét clock skew và event ordering; không dùng wall-clock từ nhiều hosts làm nguồn chân lý mặc định.

## 18. So sánh dữ liệu A/B: counts chỉ là bước đầu

Một checklist reconciliation:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Coverage | Tất cả partitions/tenants nằm trong scope? | Keyspace/range inventory |
| Count | Số documents/keys có phù hợp? | Per-tenant/per-partition counts |
| Identity | Có duplicate hoặc missing primary keys? | Key lists, bloom/digest theo cách tin cậy |
| Content | Giá trị field và type giữ đúng? | Canonical hash/sample/full compare |
| Version | B ở version nào so với A? | Source version/commit position |
| Deletion | Tombstones/TTL/privacy đã hội tụ? | Deleted-key suppression |
| Integrity | Business invariants còn đúng? | Stock, order-state, idempotency ledger |
| Schema | Index/validators/permissions đúng? | Explain/metadata diff |
| Derived | Search/cache/analytics freshness? | Watermark, sample queries |
| History | Outbox/CDC/side effects không bị bỏ? | Event IDs, inbox/dedup |

Nếu A và B đang có writes liên tục, so hash tại hai thời điểm tùy ý có thể cho false differences. Để so có nghĩa, cần **cùng logical cutoff** hoặc áp chính sách “B version ≥ source version đã chọn”, sau đó đánh giá business contract.

## 19. Reconciliation theo khóa, version và canonical hóa

Ví dụ document:

~~~json
{
  "tenantId": "t01",
  "orderId": "O1001",
  "status": "CONFIRMED",
  "totalMinor": 240000,
  "sourceVersion": 17
}
~~~

Một comparator có thể:

1. Chọn một scope/partition và cutoff.
2. Read A/B theo consistency cần thiết.
3. Chuẩn hóa type/field order mà **không loại những field ảnh hưởng nghiệp vụ**.
4. So content/primary identity, version và deleted state.
5. Phân loại missing/stale/divergent/transformed-intentionally.
6. Ghi mismatch vào work queue có owner và remediation.
7. Cập nhật counts và kiểm tra lại sau repair.

Hash nhanh hữu ích cho phát hiện thay đổi, nhưng cần lưu ý **hash collision, canonical serialization và cùng input scope**. Sample comparison chỉ cung cấp độ tin cậy theo mẫu, không chứng minh tuyệt đối tất cả keys đều trùng.

## 20. Chuyển theo từng tenant/key: điều kiện áp dụng

Đổi owner cho từng tenant có thể giảm blast radius:

~~~text
owner(tenant t01) = B, epoch 42
owner(tenant t02) = A, epoch 41
owner(tenant t03) = A, epoch 41
~~~

Nhưng chỉ an toàn nếu:

- Các invariants chủ yếu nằm trong phạm vi tenant.
- Unique indexes, quotas, counters hoặc payment ledger không phụ thuộc global writes ở hai nguồn.
- Mọi API, event worker, cron task và admin script có cùng rule định tuyến.
- Cross-tenant queries biết đọc nhiều nguồn/tổng hợp đúng.
- Cutover registry có tính nhất quán mạnh cho owner/epoch.
- Rebalancing và partial migration failures có workflow rõ.
- Rollback từng tenant không làm mất writes chỉ có ở B.

Một service có foreign references giữa tenants hoặc global monotonically increasing identifiers có thể không chuyển tenant độc lập mà không thiết kế lại semantics.

## 21. Pre-cutover compatibility: code hai đời phải cùng sống được

Trước đổi traffic, phải hỏi:

- Phiên bản app cũ có đọc được records do B/new schema ghi không?
- Phiên bản app mới có đọc được A/old schema trong rollback không?
- Schema/index đổi theo expand → backfill → switch → contract chưa?
- Serializers giữ number precision, enum unknown values, null/missing?
- Query capability, compound index, pagination, collation khác nhau?
- Quyền service account/TLS, DNS và endpoint đã hoạt động?
- Consumer events có chịu schema evolution không?
- TTL/retention/security policy ở B được kích hoạt đúng?

**Deploy code tương thích hai schema trước khi cutover** có thể giảm nguy cơ không thể rollback. Nhưng điều đó không đảm bảo revert được dữ liệu đã ghi theo model mới; cần có kế hoạch migration/reconciliation riêng.

## 22. Shadow reads và canary reads: đo kết quả mà không ảnh hưởng user

**Shadow read** gửi một truy vấn phụ tới B nhưng vẫn trả response từ A:

~~~text
User GET -> A response returned to user
           \-> B shadow query asynchronously for comparison
~~~

Yêu cầu:

- Shadow read không tạo side effects hoặc writes.
- Không để shadow latency chặn response chính.
- Giới hạn sampling, rate, concurrency và PII handling.
- So cùng identity/tenant/authorization context.
- Có cùng semantics query/fields, chấp nhận intentional transformations.
- Ghi mismatch category/version/lag, không log raw PII bừa bãi.
- Có circuit breaker nếu B chậm để không tác động A/ứng dụng.
- Đánh giá B index/CPU/connection pool khi traffic thử tăng.

Canary read có thể chuyển **một tỷ lệ nhỏ user-facing traffic** sang B nếu consistency contract đã cho phép. Shadow success không bảo đảm canary success, vì concurrency, cache locality và user-visible tail latency có thể khác.

## 23. Định tuyến đọc theo nhóm thao tác

Thay vì một nút `READ_TARGET=B` áp cho mọi API, nên chia theo hợp đồng dữ liệu:

| Operation | Khi A là writer | Khi B là writer | Điều kiện |
|---|---|---|---|
| Checkout/stock | A | B | Đọc trạng thái có thẩm quyền |
| Read Order vừa tạo | A | B | Read-your-writes |
| Catalog browse | A, shadow B | Canary rồi B | Freshness budget |
| Search/report | Shadow hoặc B nếu cho phép | B/read model | CDC watermark và query correctness |
| Admin export | A | B theo RBAC | Tenant scope, audit, PII |
| Permission/revocation | Nguồn quyền authoritative | Nguồn quyền mới có thẩm quyền | Security freshness |
| Diagnostics | A/B có hạn mức | B hoặc isolated replica | Không phá OLTP SLO |

Có thể có read paths chấp nhận eventual data, nhưng business confirmation hoặc quyền truy cập không được tự hạ consistency chỉ để cắt chuyển sớm.

## 24. Session stickiness và commit token

Client vừa ghi cần đọc lại kết quả chính xác. Các lựa chọn:

- **Sticky authoritative route:** reads sau write tiếp tục về writer có thẩm quyền.
- **Commit token/watermark:** write trả token; B chỉ trả read khi đã áp tới mốc này.
- **Version predicate:** B chỉ hợp lệ nếu `record.version >= requiredVersion`.
- **Bounded wait:** nếu chưa bắt kịp trong deadline, route về owner hoặc trả trạng thái theo contract.

Ví dụ:

~~~text
POST /orders -> 201, orderId=O1001, sourceVersion=23
GET /orders/O1001 requires version >= 23
B currently has version 21
=> wait within deadline OR route to authoritative owner
~~~

Token phải có semantics theo engine/replication. Timestamp tùy ý từ hai máy không chứng minh commit order; fallback phải luôn kiểm tra tenant/permissions và không tạo read loop hoặc load storm.

## 25. Route control plane có nhiều client bị sót

Một hệ có thể route qua application flags, DNS, service mesh, driver pools, worker config, scheduled jobs, admin scripts, đối tác hoặc mobile clients.

~~~text
10:00 route switch points to B.
10:01 most API pods use B.
10:03 old long-running worker still holds A connection.
10:05 delayed queue message causes write to A.
~~~

Thay config **không làm mọi clients chuyển cùng lúc**. Cần inventory tất cả write-capable actors và một lớp enforcement chặn old writers tại commit.

## 26. DNS TTL, connection pools và stale endpoints

DNS TTL không buộc driver đóng TCP connection đang mở. SDK có server discovery, topology caches, pools, TLS sessions, retries và client-side routing.

Cần hỏi:

1. Khi nào driver dùng endpoint mới?
2. Kết nối cũ có thể ghi A sau flag đổi?
3. Có cần controlled pool drain/restart?
4. Retry có thể chuyển giữa A/B và đổi business semantics không?
5. B có credentials/TLS/region policy tương ứng không?
6. Metrics có tách active connections/requests đến A và B không?
7. Có thể revoke quyền ghi A mà vẫn cho phép đọc/reconciliation A không?

**DNS TTL không phải fencing token.** Nếu A còn nhận commit, stale clients vẫn có thể gây split brain.

## 27. State machine của quá trình cutover

~~~mermaid
stateDiagram-v2
    [*] --> PREPARE
    PREPARE --> SHADOW
    SHADOW --> FREEZE_A
    FREEZE_A --> DRAIN_A
    DRAIN_A --> CATCH_UP_B
    CATCH_UP_B --> FENCE_A
    FENCE_A --> ACTIVATE_B
    ACTIVATE_B --> VERIFY_B
    VERIFY_B --> COMPLETE
    PREPARE --> ABORTED
    SHADOW --> ABORTED
    FREEZE_A --> ABORTED
    DRAIN_A --> ABORTED
    CATCH_UP_B --> ABORTED
    VERIFY_B --> RECOVERY
    RECOVERY --> COMPLETE
~~~

- **PREPARE/SHADOW:** A giữ quyền ghi; B chỉ sao chép/được đọc thử.
- **FREEZE/DRAIN:** ngăn ghi mới, giải quyết operations đã gửi và unknown outcomes.
- **CATCH_UP:** B hội tụ tới một barrier ổn định.
- **FENCE:** không còn đường commit mới vào A.
- **ACTIVATE:** quyền B được cấp cho generation mới.
- **VERIFY:** kiểm tra SLO, correctness và write exclusivity.
- **COMPLETE:** chỉ khi acceptance đạt và recovery plan khả thi.

Thứ tự thực tế phải theo engine và **điểm thực thi write gate**. Với một số protocol, cần fence trước khi chốt barrier; không lấy sơ đồ minh họa làm guarantee cho hai DB độc lập.

## 28. Preflight trước khi chuyển

Một checklist tác nghiệp:

1. Cluster, scope, tenant/key ranges, region, endpoints chính xác.
2. Owner/chỉ huy sự cố, DBA, CDC, app, SRE và support sẵn sàng.
3. Backup, checkpoint và phương án rollback/roll-forward đủ.
4. Schema, indexes, validators, TTL, roles của B phù hợp.
5. Backfill, CDC, DLQ và stream retention đầy đủ.
6. A/B quorum, replica, disk/memory/network capacity khỏe.
7. Lag/apply/reconciliation watermarks đạt tiêu chí từng partition.
8. App/driver old/new compatible, retry/idempotency đúng.
9. Freeze/drain/fencing/routing switch được diễn tập.
10. Dashboards, synthetic probes, on-call contacts sẵn sàng.
11. Shadow-read mismatches đã được phân loại và khắc phục.
12. Security: TLS, RBAC, tenant isolation, data residency.
13. Go/no-go threshold và quyền quyết định dừng được ghi.
14. Không có conflicting backup/rebalance/index jobs ngoài dự kiến.

Đây là checklist cho **vận hành cutover thật**, không phải chạy Content QA của pipeline soạn bài.

## 29. Write freeze và admission control

Khi dùng cutover có cửa sổ ngừng ghi:

- Chặn write mới ở API/gateway và cả workers/cron/admin paths.
- Cho phép reads trên A nếu phù hợp.
- Trả lỗi tạm thời hoặc queue có bảo đảm theo business contract.
- Giới hạn deadline, queue backlog và retries.
- Đo denied/deferred/queued writes.
- Không ACK success khi chỉ nhận message vào hàng đợi RAM.
- Chuẩn bị resume từ trạng thái an toàn khi chuyển không thành công.

HTTP 503 với header `Retry-After` có thể phù hợp vài API; checkout/payment có thể cần stable business intent/idempotency và response semantics riêng. **Freeze là hành động chặn admission, không tự giải quyết writes đã đang thực hiện.**

## 30. Drain in-flight và unknown write outcomes

Sau freeze, vẫn có:

- HTTP requests/driver operations đang chạy.
- Lệnh đã gửi DB nhưng chưa nhận ACK.
- Transaction đang mở hoặc conditional write đang đợi.
- Retries, queued tasks, background jobs.
- Outbox dispatch hoặc external side effects.

Drain gồm:

1. Đợi active writes xuống zero trong phạm vi được đo.
2. Chặn workers/cron tạo write mới.
3. Ghi danh sách operation IDs có kết quả UNKNOWN.
4. Đối soát authoritative ledger để biết committed/rejected.
5. Lấy stable source barrier phù hợp semantics.
6. Không tuyên bố drained chỉ vì HTTP in-flight=0.

Một request mất ACK **không đồng nghĩa chưa commit**. Stable idempotency key/result ledger phải đi vào B cùng dữ liệu; nếu chưa phân giải được, cần recovery policy trước khi cho retry gây effect mới.

## 31. Fencing tại A: chặn old writer ở nơi commit

| Tầng | Tác dụng | Giới hạn |
|---|---|---|
| App flag | Dễ rollout | Pod cũ chưa reload |
| API/gateway | Chặn đường public | Worker/internal direct write bỏ qua |
| Worker admission | Ngăn queue jobs mới | Old task còn chạy |
| DB role/ACL | Giảm quyền ghi tại nguồn | Revocation propagation, identity khác |
| Storage epoch/version check | Chặn stale generation tại commit | Cần DB/protocol hỗ trợ |
| Network policy | Cắt đường cũ | Existing connections/paths cần xem |
| Quiesce/offline A | Ngừng write mạnh hơn | Cần bảo trì/downtime |

Nên dùng **defense in depth**. Cấp quyền ghi B trước khi đã ngăn toàn bộ A writes có thể tạo overlap; nhưng khóa A quá sớm khi còn unknown outcomes có thể khiến reconciliation khó. Thứ tự cần do runbook có owner và được thử với failure cases.

## 32. Handoff quyền ghi phải có audit và trạng thái trung gian

Một chuỗi logical events:

~~~text
CUTOVER_STARTED(scope=t01, from=A, to=B, epoch=41)
ADMISSION_CLOSED(scope=t01)
OLD_WRITES_DRAINED(scope=t01, barrier=P)
TARGET_APPLIED_BARRIER(scope=t01, barrier=P)
OLD_WRITER_FENCED(scope=t01)
OWNER_SWITCHED(scope=t01, owner=B, epoch=42)
NEW_WRITER_PROBE_SUCCEEDED(scope=t01)
CUTOVER_VERIFIED(scope=t01)
~~~

Trạng thái cần được ghi bền, có owner, audit và access control. Nếu operator script chết giữa `OLD_WRITER_FENCED` và `OWNER_SWITCHED`, trạng thái **không writer tạm thời** có thể an toàn hơn mở lại cả A/B. Recovery path phải xác định cách resume/abort.

**Một registry update không tự là atomic transaction trên hai NoSQL databases độc lập.** Phải xem enforcement ở từng data plane.

## 33. Kiểm tra writer mới bằng operation có kiểm soát

Sau khi B có authority, dùng synthetic test hoặc transaction đã được bảo vệ:

- B chấp nhận write với durability/consistency đúng.
- Read B thấy write theo read-your-writes contract.
- Conditional update/version conflict được enforce.
- A từ chối stale write trong scope, kể cả old client path.
- Event/outbox từ B xuất hiện đúng downstream.
- Retry cùng idempotency key không tạo duplicate.
- Security/tenant permission checks đạt.
- Metrics và audit ghi rõ B là active owner.

Một `PING` thành công không chứng minh writer correctness. Probe production phải không làm sai business counters hoặc sinh dữ liệu rác trái policy.

## 34. Mở read traffic theo hợp đồng, không chỉ theo tỷ lệ

Một lịch thử:

~~~text
Shadow B only
 -> 1% canary for allowed noncritical reads
 -> 5% user-facing reads
 -> 25-50% if stability holds
 -> 100% eligible routes
 -> critical read-your-writes flows after specific checks
~~~

Tỷ lệ chỉ là ví dụ. Có workflows phải chuyển read+write nhất quán theo owner một lần, không thể tách rollout từng phần. Chọn scope dựa vào customer session, tenant, partition hoặc route semantics.

Giám sát:

- Missing results và wrong tenant reads.
- Version/read-after-write mismatches.
- p95/p99, request errors, timeouts và throttles.
- Target query plans/index coverage.
- Cache warmup, hot partitions và disk pressure.
- Fallback count và source load.
- CDC lag/read model age.
- Business outcomes: duplicate, oversell, invalid state.

## 35. Tiêu chí chấp nhận go/no-go có thể đo

| Nhóm | Chứng cứ cần có |
|---|---|
| **Coverage** | Tất cả partitions/shards/tenants thuộc scope đã di chuyển |
| **CDC** | B applied ≥ stable A barrier, không gap/DLQ chưa xử lý |
| **Integrity** | Không có mismatch bất biến nghiệp vụ chưa giải thích |
| **Write ownership** | A không còn nhận commit mới; B nhận commit sau handoff |
| **Read semantics** | Đủ session freshness/consistency, đúng schema/filter/index |
| **Security** | TLS, RBAC, tenant boundaries, deletion/privacy policy |
| **Latency/availability** | SLO errors/p99/throughput đạt trên traffic đại diện |
| **Cluster health** | Quorum/replica, headroom, I/O, background jobs ổn |
| **Recovery** | Backup, owner rollback/forward-repair, RPO/RTO rõ |
| **Client inventory** | All write-capable API/worker/admin paths đã được kiểm soát |
| **Observability** | Epoch, route, source and target attempts, lag, mismatches visible |
| **Governance** | Change/approval, explicit GO và quyền dừng |

**Lag gần 0 không đủ** nếu consumer tắt, thiếu partition hoặc skip DLQ. Cần source progress, target applied state, coverage và business reconciliation.

## 36. Ngưỡng acceptance ví dụ cho hệ đặt hàng

Các số sau **chỉ minh họa**, phải điều chỉnh theo SLO/dung lượng thực tế:

~~~yaml
cutover:
  scope: "tenant-batch-7"
  freezeDeadlineSeconds: 90
  maxUnknownWritesBeforeActivation: 0
  requireSourceWriteFenced: true
  requireTargetAppliedThroughBarrier: true
  requireNoUnresolvedCdcGaps: true
  requireNoCriticalBusinessMismatch: true
  canary:
    minimumRequests: 10000
    maxErrorRate: 0.001
    maxP99Ms: 350
  approvals:
    - application-owner
    - database-operator
    - incident-commander
~~~

Một hệ có **unknown operations** có thể cho handoff khi mọi operation đã có durable reconciliation ledger và trạng thái an toàn, không nhất thiết luôn bằng 0. Ví dụ chọn 0 để người học thấy policy cần **định lượng và có điều kiện**; không sao chép trực tiếp cho production.

Ngoài p99, hãy so business success/unknown, data-loss risk, replication lag, quyền và chi phí failback. Một số key/tenant ít traffic cần synthetic checks hoặc cửa sổ quan sát dài hơn.

## 37. Stop conditions: dấu hiệu khiến cutover phải dừng

- Owner A/B không thể được xác nhận hoặc hai nguồn cùng chấp nhận write.
- Một partition/shard không áp được barrier.
- CDC log gap, DLQ lỗi chưa có xử lý, dữ liệu delete chưa hội tụ.
- Duplicate business effects/oversell/invalid state transition.
- Reconciliation mismatch không giải thích trong critical collections.
- Quorum/replication health suy giảm hoặc disk headroom không đủ.
- p99/error-budget burn vượt giới hạn chấp nhận.
- Security policy/tenant isolation vi phạm.
- B chưa có key/certs/restore readiness.
- API/worker cũ còn ghi A sau fence.
- Config/route effective state không thể xác minh.
- Chủ incident không còn khả năng phục hồi an toàn theo plan.

**Stop không nhất thiết đồng nghĩa ngay lập tức route về A.** Nếu B đã nhận authoritative writes, việc quay lại A mà không đồng bộ ngược có thể gây mất dữ liệu. Trạng thái cần xác định **abort trước activation**, **pause sau activation**, hoặc **roll forward/repair**.

## 38. Rollback trước và sau khi B nhận quyền ghi là hai bài toán khác nhau

### 38.1. Trước khi B trở thành writer

Nếu A vẫn là owner và B chỉ nhận shadow/CDC:

- Dừng pipeline/canary.
- Cho read/write tiếp tục trên A theo trạng thái cũ.
- Chỉnh sửa schema, index, transform hoặc dữ liệu tại B.
- Chạy lại backfill/replay khi đã xử lý nguyên nhân.
- Không có write nghiệp vụ nào **chỉ tồn tại ở B** cần chuyển ngược.

Rollback thường đơn giản hơn, nhưng vẫn cần bảo đảm **shadow queries không gây effects** và không ảnh hưởng A qua overload.

### 38.2. Sau khi B đã nhận authoritative writes

Giả sử:

~~~text
10:00 cutover owner A -> B
10:02 B commits Order O2001
10:03 B commits Order O2002
10:04 query performance on B degrades
10:05 operator proposes routing everything back to A
~~~

Nếu A chưa nhận O2001/O2002, failback lập tức làm mất các business facts đã ACK. Đây không phải rollback bằng env var đơn giản.

Lựa chọn:

- **Roll forward**: giữ B writer, sửa index/config/query hoặc giảm traffic.
- **Temporary read routing**: tiếp tục write B, chỉ chuyển read nào bảo đảm semantics.
- **Reverse synchronization**: B → A với checkpoint, conflict handling và fence B trước khi kích hoạt A.
- **Controlled pause/repair**: tạm ngừng writes, reconcile và handoff ngược như một migration mới.

Không chọn “A đang ổn nên route write lại A” khi chưa có **đầy đủ B-only writes** và kế hoạch replay kết quả side effects.

## 39. Reverse CDC/failback cần cùng điều kiện như cutover ban đầu

Nếu dự kiến failback B→A, từ trước cutover nên xác định:

1. B có phát log/CDC đủ thông tin để reconstruct writes không?
2. A có schema/fields tương thích với data do B tạo không?
3. Delete/TTL/privacy changes được áp ngược thế nào?
4. Event IDs, versions, idempotency ledger có giữ nguyên không?
5. Các writes có side effects bên ngoài sẽ không bị chạy lại chứ?
6. Có conflict nếu A nhận accidental write sau khi bị fence không?
7. Có thể chốt stable barrier trên B và xác minh A đã áp tới barrier không?
8. Có thể thu hồi quyền writer B trước khi bật lại A không?
9. Khi B bị hỏng hoàn toàn, RPO tối đa cho failback là gì?
10. Nếu không có reverse path, ai có quyền quyết định roll forward hoặc disaster restore?

Một reverse stream **chạy song song** không tự chứng minh failback an toàn. Cần quản lý ordering, schema, source versions và chính xác committed outcomes.

## 40. Roll forward có thể an toàn hơn rollback

Ví dụ B có một index/query plan chưa tối ưu nhưng writes đang đúng:

- Giảm read traffic nặng trên B theo policy.
- Tạm chuyển một số read-only analytics sang bản sao phù hợp.
- Build/repair index có throttle và kiểm soát I/O.
- Giới hạn report concurrency/retry budgets.
- Duy trì B là writer, bảo toàn acknowledged writes.
- Theo dõi correctness và p99 sau từng thay đổi.

Roll forward không có nghĩa “tiếp tục dù đang mất dữ liệu”. Nếu có nguy cơ oversell/unauthorized access/data corruption, cần **pause/contain** theo stop policy rồi repair hoặc khôi phục đúng protocol. Quyết định dựa trên **bất biến nghiệp vụ và khả năng bảo toàn committed writes**, không chỉ độ khó vận hành.

## 41. Read rollback khác write rollback

Khi B là writer, có thể không an toàn để đọc từ A vì A đã cũ. Chỉ nên fallback read về A khi:

- A có replication/reverse sync bắt kịp tới phiên bản cần đọc.
- Read là eventual với freshness budget phù hợp.
- Session token/version check được kiểm tra.
- Thông tin permission/deletion ở A không vi phạm security contract.
- Ứng dụng có cách phân biệt nguồn trả lời và không tạo một chuỗi fallback vô hạn.

Một fallback dạng “B timeout → cứ hỏi A” có thể trả **giá hoặc tồn kho cũ**, làm caller thực hiện business decision sai. Fallback phải có điều kiện theo operation, không áp đồng loạt mọi endpoint.

## 42. Mở rộng theo nhiều region: quyền ghi và tính nhất quán không đơn giản là một địa chỉ

Trong multi-region topology:

- Có hệ chỉ một region được ghi, regions khác đọc eventual.
- Có hệ multi-writer nhưng xử lý conflicts theo rules của engine.
- Có hệ có consensus/quorum scope đặc biệt.
- Có data residency/latency constraints.
- Có region-local write queue nhưng commit authoritative ở nơi khác.

Trước đổi region writer phải xác nhận:

1. Region nào giữ commit authority theo sản phẩm?
2. Có thể có concurrent writes cùng key ở hai region không?
3. Engine giải conflicts bằng gì? Có giữ domain invariant không?
4. Mất link liên vùng thì write ACK theo contract nào?
5. Remote reads có monotonic/read-your-writes không?
6. Network RTT, cost, failover và cache warm-up ảnh hưởng SLO ra sao?
7. Sau region failover, có bảo đảm không mở lại old writer ngoài ý muốn?

**Đừng đồng nhất replication đa vùng với một protocol single-writer có fencing.** Thay region routing, đổi consistency level và đổi authoritative writer là ba quyết định liên quan nhưng riêng biệt.

## 43. MongoDB: replica set failover khác migration sang cluster mới

Với MongoDB cần phân biệt:

- **Replica set election:** primary thay đổi bên trong một replica set theo cơ chế native. Client/driver phải khám phá topology; không tự thực hiện “dual primary”.
- **Cluster-to-cluster migration:** một cluster A và cluster B độc lập, cần snapshot/change stream/backup–restore hoặc công cụ migration được hỗ trợ, cùng protocol cutover riêng.
- **Sharded cluster:** router/shards/config metadata có constraints khác replica set đơn.

Khi chuyển A→B, kiểm tra:

- Read/write concern, read preference, driver server selection.
- Change streams resume tokens/oplog window và sharded semantics.
- Unique indexes, validators, TTL indexes, collation.
- Số documents/keys và canonical field types.
- Update/delete ordering, oplog-backed catch-up.
- Transactions/related collections và outbox state.
- Quản lý client credentials/connectivity và không để old app write A.
- Backup/PITR và restore drill target B.

Một `majority` acknowledgement trong **A** không tự sao chép record sang **B**. Một change stream consumer applied watermark có ích nhưng phải xác minh **coverage** và các failure cases.

### 43.1. Ví dụ migration Order document

~~~json
{
  "tenantId": "t01",
  "orderId": "O1001",
  "status": "CONFIRMED",
  "sourceVersion": 42,
  "idempotencyKey": "req-opaque-1001"
}
~~~

Target không được chấp nhận một update version 41 tới muộn sau version 42 nếu mô hình có version đơn điệu; tuy nhiên việc dùng version field và update predicate phải được thiết kế atomic theo cách engine hỗ trợ, không chỉ so ở application memory.

## 44. Cassandra/ScyllaDB: chuyển writer và routing theo token/DC

Với wide-column deployments, chú ý:

- Partition key và token-aware routing.
- Replication factor/placement và keyspace schema.
- Consistency level cho read/write, đặc biệt local vs cross-DC.
- Repair/streaming/compaction/tombstone status.
- Driver contact points/topology discovery.
- Timestamp-based conflict resolution và clock skew.
- Lightweight transactions/CAS khi có, giới hạn phạm vi/chi phí.
- TTL và delete tombstones.
- Partition hot spots và write load trên B.

Thay contact points để client ưu tiên một DC **không tự đồng nghĩa write fencing tại DC cũ**, nhất là khi khác cluster hoặc các ứng dụng cũ còn quyền gửi CQL. Nếu dùng native replicas trong cùng ring, phân biệt **đổi preferred coordinator** với **đổi authoritative data source**; semantics không giống migration độc lập.

Không giả định Cassandra/ScyllaDB cung cấp distributed transaction xuyên toàn bộ keys chỉ nhờ consistency level. Business invariant cần atomic model phù hợp hoặc workflow reconciliation.

## 45. DynamoDB: table migration, Streams và global replication

Một kịch bản từ table A sang table B:

- Backfill bằng export/scan phù hợp và kiểm soát capacity.
- Bắt thay đổi qua Streams hoặc pipeline khác, với retention và retry semantics.
- Giữ keys/conditional writes/idempotency state.
- Xử lý GSIs, TTL, policies, IAM, encryption/KMS.
- Quan sát read/write capacity, throttling, errors và hot keys.
- Chuyển application table mapping/route có kiểm soát.
- Ngăn các IAM principals cũ tiếp tục write A sau handoff.
- Phân biệt on-demand backup/PITR với live CDC/cutover.

Một số thao tác hỗ trợ strong read trên table trong những điều kiện cụ thể, nhưng không suy điều đó cho mọi GSI/region hoặc mọi topology. Nếu dùng global tables/multi-region, conflict resolution và consistency phải được hiểu theo **khả năng dịch vụ thực tế**; không tự tạo single-writer guarantees bằng cách chỉ đổi region env var.

Ví dụ source/target table count giống nhau **không chứng minh Streams không mất delete hoặc business condition checks vẫn giữ đúng**.

## 46. Redis: chuyển owner khi key TTL, lock và session state liên quan

Redis có thể là:

- Cache có thể warm lại.
- Session/token store.
- Lock/lease/idempotency state.
- Data store cho queue/counter hoặc business state.

Nếu Redis là **cache**, có thể chuyển read cache dần và chấp nhận misses theo source-load budget. Nếu chứa **authoritative coordination/business state**, cutover rủi ro hơn:

- TTL absolute/remaining lifetime phải được bảo toàn đúng policy.
- Keyspace/slot routing và hot keys.
- Persistence/replication/failover semantics.
- Lock owner/lease và stale worker fencing.
- In-flight commands/pipelining.
- Idempotency keys, session invalidation, revocation state.
- Redis ACL/network permissions.

**Chuyển Redis lock key sang instance mới không tự ngăn old worker thực hiện effect.** Với lock bảo vệ thao tác tại downstream DB, downstream phải có cơ chế fencing hoặc invariant enforcement, nếu không old worker vẫn có thể ghi sau khi lease mất.

## 47. Search index và cache: đọc có thể cắt chuyển độc lập, ghi thường không

Search/OpenSearch/Elasticsearch index và cache thường là **derived read models**, không phải authoritative writer cho Orders/Inventory.

Có thể:

1. Dựng index B từ snapshot A.
2. Replay CDC, giữ tombstone/delete semantics.
3. Shadow search queries và so kết quả/score/sort theo quy tắc phù hợp.
4. Kiểm tra freshness watermark và index mapping.
5. Chuyển read alias/router dần với canary.
6. Ngừng old index theo retention policy sau thời gian an toàn.

Tuy nhiên score/rank có thể thay đổi hợp lệ giữa engine/index versions; không luôn yêu cầu byte-for-byte result equality. Cần test semantic requirements: required records, tenant isolation, deletion, pagination, freshness và p99. Không dùng eventual search results làm quyết định cấp stock hoặc xác nhận thanh toán.

## 48. Security và quyền vận hành khi đổi nguồn

Một cutover có thể sai dù latency/data counts đều đẹp:

- B có service account rộng quyền hơn A.
- Tenant filter bị thiếu ở query path mới.
- Service cũ vẫn giữ credential superuser A.
- Firewall của B mở tạm để debug mà không thu hồi.
- CDC connector đọc dữ liệu ngoài scope.
- Backfill/logs chứa PII, secret hoặc access token.
- Backup/restore key không hoạt động ở target region.
- Audit không ghi được owner epoch hoặc write revocation.
- Failback không có phê duyệt.

Điều kiện chuyển phải có **security acceptance**: RBAC/tenant isolation, TLS/certificate verification, network routes, credential lifecycle, access audit và privacy-delete propagation. Không tắt authentication để tránh downtime.

## 49. Java: write gate theo epoch chỉ là một phần fencing

Một hợp đồng minh họa:

~~~java
public record WriteAuthority(
        String scope, String owner, long epoch) {}

public record WriteIntent(
        String scope, String operationId,
        String expectedVersion, byte[] payload) {}

public record CommitOutcome(
        String operationId, String status, String objectId) {}

public interface AuthorityRegistry {
    WriteAuthority current(String scope) throws Exception;
}

public interface ConditionalOrderWriter {
    CommitOutcome commitWithEnforcedEpoch(
        WriteIntent intent, long requiredEpoch) throws Exception;
}

public final class CutoverAwareOrderService {
    private final AuthorityRegistry registry;
    private final ConditionalOrderWriter targetWriter;

    public CutoverAwareOrderService(
            AuthorityRegistry registry,
            ConditionalOrderWriter targetWriter) {
        this.registry = registry;
        this.targetWriter = targetWriter;
    }

    public CommitOutcome writeToB(WriteIntent intent)
            throws Exception {
        WriteAuthority authority = registry.current(intent.scope());
        if (!"B".equals(authority.owner())) {
            throw new IllegalStateException(
                "Target B is not authoritative");
        }
        // Real fencing must happen atomically at a trusted
        // commit boundary; this precheck alone is not enough.
        return targetWriter.commitWithEnforcedEpoch(
            intent, authority.epoch());
    }
}
~~~

**Đây là ví dụ hợp đồng, không phải một implementation an toàn có thể cài đặt ngay.** Đọc owner rồi ghi là một chuỗi có race. `commitWithEnforcedEpoch` phải thực sự enforce quyền tại storage/trusted gateway; nếu hai DB độc lập không chia sẻ atomic authority, cần freeze/drain/revoke protocol khác. `operationId` phải có ledger idempotency để retries không tạo duplicate effects.

## 50. Change manifest cho một lần handoff

~~~yaml
changeId: CHG-533-EXAMPLE
scope:
  type: tenant-batch
  ids: [t01, t02]
source: A
target: B
phase: CATCH_UP
epochBefore: 41
epochAfter: 42
sourceBarrier:
  shard-a: "position-101"
  shard-b: "position-230"
requirements:
  noUnresolvedCdcGap: true
  targetAppliedThroughBarrier: true
  oldWriterFenced: true
  criticalBusinessMismatches: 0
  readYourWritesProbe: required
  securityAndDeletionProbe: required
readCanaryPercent: 1
recovery:
  beforeActivation: abort-to-A
  afterActivation: roll-forward-or-reverse-handoff
owners: [application, database, oncall]
~~~

Đây là **mẫu tài liệu change**, không phải configuration của một sản phẩm. Thực tế cần durable state transitions, validation, concurrent-change prevention, permissions, audit, rollback approval và recovery khi orchestration chết giữa chừng.

## 51. Dashboard cho thời điểm cutover

| Panel | Tín hiệu |
|---|---|
| Người dùng | Rate, p95/p99, errors, business success/unknown |
| Read route | A/B request distribution theo endpoint và client version |
| Write owner | Owner, epoch, denied stale writer attempts |
| A source | Writes/s sau freeze, active operations, connections |
| B target | Committed writes, conditional conflicts, errors |
| CDC | Source/captured/published/applied position per shard |
| Completeness | Backfill ranges, DLQ, reconciled keys/mismatches |
| Freshness | Read-your-writes failures, data age/version |
| Integrity | Oversell, duplicate intents, invalid transitions |
| Hạ tầng | Quorum, disk, CPU, cache, pool wait, hot partitions |
| Security | Authorization denials, TLS, privacy suppression |
| Recovery | Backup age, barrier, reverse path readiness |

Giữ **cùng scope/time window** khi so A/B. p99 đẹp ở 1% canary không chứng minh chịu được 100% traffic. Chèn annotations cho freeze, barrier, fence, owner switch, canary percent và rollout version.

## 52. Runbook cắt chuyển có thể diễn tập

**Chuẩn bị**

1. Chốt scope, invariants, business RPO/RTO/downtime.
2. Xác nhận approvals, on-call, stop authority, recovery plan.
3. Kiểm tra schema/index/permissions/secrets/backup ở B.
4. Kiểm chứng backfill, CDC ordering/coverage và client inventory.
5. Dựng dashboard, synthetic probes và fence mechanism.

**Shadow và quyết định**

6. Chạy shadow reads, so correctness/lag/latency theo version.
7. Reconcile tombstone/privacy, DLQ, hot partitions.
8. So capacity và performance với traffic đại diện.
9. Ghi rõ trạng thái rollback trước activation.
10. Ra quyết định GO/NO-GO có owner.

**Chuyển writer**

11. Đóng write admission ở API/worker/admin paths.
12. Drain in-flight, xác định UNKNOWN results.
13. Chốt stable source barrier theo supported protocol.
14. Đảm bảo B applied durable qua barrier và các invariant checks đạt.
15. Fence old writer A; kiểm tra stale requests bị từ chối.
16. Chuyển owner/epoch tới B theo cơ chế authoritative.
17. Bật write B và thử conditional/idempotent write.

**Chuyển read và hậu kiểm**

18. Mở reads dần theo consistency policy.
19. Theo dõi p99, errors, freshness, privacy và business effects.
20. Khi vượt guardrail, pause/contain, **không tự failback writes**.
21. Xác minh mọi write-capable client đã chuyển; giữ A cho recovery.
22. Công bố COMPLETE chỉ sau acceptance window đủ.
23. Cập nhật backup/DR, routing, IAM, audit và runbook.

Thứ tự barrier/fence/owner có thể phải thay theo point-of-enforcement của engine. Runbook production phải được cụ thể hóa và diễn tập, không copy nguyên lệnh giả định.

## 53. Failure matrix theo giai đoạn

| Sự cố | Pha | Cách ứng phó |
|---|---|---|
| B thiếu partition | PREPARE | Dừng, backfill/repair |
| CDC gap/retention hết | CATCH_UP | Không công bố caught up; reseed |
| A commit sau barrier | FREEZE/FENCE | Dừng, sửa fencing, reconcile |
| Old worker vẫn ghi A | Post-switch | Contain, đánh giá split brain |
| B thiếu idempotency state | Activation | Pause affected intents, reconcile |
| B read stale | READ_CANARY | Tắt route không phù hợp, kiểm tra watermark |
| B p99 rất cao | VERIFY | Giảm load/roll forward, không rollback mù |
| Cross-tenant read | Bất kỳ | Stop/contain, sửa policy |
| KMS/backup không sẵn | Preflight | NO-GO cho đến khi recovery ready |
| B write ACK mất | Post-activation | Ledger/outcome reconciliation |
| Control plane chết | Handoff | Giữ no-writer/safe owner state |
| Hai nguồn cùng commit | Post-switch | Fencing/contain, audit, repair |

Điều quyết định là **phase, source of truth và writes đã ACK**, không chỉ metric đang xấu.

## 54. Fault injection và chaos rehearsal

Trong staging/môi trường cô lập thử:

1. Kill backfill worker sau artifact write nhưng trước checkpoint.
2. Gây CDC lag và retention gap.
3. Replay duplicate/out-of-order updates một business key.
4. Để stale app vẫn giữ A connection.
5. Cho write commit nhưng mất ACK.
6. Làm control plane chết đúng lúc owner epoch đổi.
7. Đổi schema B khi worker cũ vẫn gửi payload cũ.
8. Làm B read p99 tăng khi canary.
9. Delete/privacy event đến trong lúc backfill.
10. Tạo worker write sau khi freeze admission.
11. Gây conflict giữa hai migration scopes.
12. Crash process sau business commit nhưng trước outbox dispatch.

Đầu ra phải chứng minh **single-writer authority, không mất acknowledged outcomes, không vi phạm tenant/privacy, và recovery path có thể thực hiện**; chỉ “các pods đều Running” chưa đủ.

## 55. Sự cố A — Hai cụm cùng nhận write sau cutover

Tình huống:

~~~text
10:00 owner registry says B, epoch=42.
10:01 new pods write only B.
10:02 old worker commits O3001 to A.
10:03 B commits a different update to O3001.
10:04 reconciliation detects divergent records.
~~~

Không nên chỉ chọn record có `updatedAt` mới nhất, bật bidirectional sync mù quáng hoặc xóa một trong hai bản. Cần:

1. **Contain:** dừng old writer, xác nhận fence.
2. **Preserve:** audit, operation IDs, versions và source logs.
3. **Scope:** tìm writes sau barrier trên A và B.
4. **Classify:** committed/unknown/rejected, duplicate side effects.
5. **Resolve:** xác định kết quả đúng theo invariant, không chỉ wall-clock.
6. **Repair:** replay idempotent/compensate theo domain policy.
7. **Verify:** không mất acknowledged Orders, không oversell, không lộ PII.
8. **Prevent:** commit-boundary fencing và fault tests.

**Split brain là lỗi correctness**, có thể cần dừng affected writes ngay cả khi p99 vẫn đẹp.

## 56. Sự cố B — B trả 404 ngay sau một POST thành công

~~~text
10:00:00 POST commits O1 on A; response 201.
10:00:01 GET routed to B.
10:00:01 B has not applied O1.
10:00:01 Client sees false 404.
~~~

Các giả thuyết: CDC lag, thiếu partition, read routing sớm, index chưa refresh, wrong key transform, tenant filter sai hoặc thiếu session watermark.

Hướng giải: giữ GET ở authoritative owner; chỉ đọc B khi version ≥ commit token; bounded wait hoặc error/pending response theo contract; fix missing CDC/index trước mở rộng canary. Không cache false 404 lâu và không để client tạo duplicate Order vì đọc không thấy.

## 57. Sự cố C — CDC lag không thể catch up

Giả định:

~~~text
Source new writes:     8,000 events/s
Target apply capacity: 6,500 events/s
Current backlog:      1,800,000 events
~~~

Nếu tốc độ giữ nguyên, backlog **tăng khoảng 1.500 events/s**. Khi nguồn ngừng tạo event, lower bound để xử lý backlog cũ ở 6.500 events/s là khoảng **277 giây**, chưa tính retries, partition skew và reconciliation.

Hành động:

1. Đo per-partition apply throughput, lag, DLQ.
2. Xem capacity throttling, hot keys, index build, CPU/I/O.
3. Giảm backfill cạnh tranh với CDC.
4. Chỉ tăng parallelism nếu không phá ordering per key.
5. Nới log retention/archive theo hỗ trợ engine.
6. Xem bounded write freeze để source position ổn định.
7. Tính drain window với measured apply capacity.
8. Đặt NO-GO nếu tồn tại log gap/target missing events.

“Consumer đang chạy” không chứng minh nó đang tiến tới cutover barrier.

## 58. Sự cố D — Write timeout ở ranh giới chuyển

~~~text
Client sends reservation with idempotencyKey K.
A commits reservation.
ACK lost, client sees timeout.
Cutover to B.
Client retries K at B.
~~~

Nếu ledger cho K chưa có ở B, app có thể cấp thêm một reservation hoặc tạo duplicate external effect.

Thiết kế:

- Dùng stable intent ID/fingerprint và outcome ledger.
- Chuyển ledger/outbox cùng business state.
- Khi retry, không tạo intent mới nếu K đã committed.
- Dùng conditional state transition có enforcement ở storage.
- Khi UNKNOWN, đưa vào reconciliation flow có owner/deadline.
- Dùng stable external payment references, không gửi lại bằng ID mới.
- Phân biệt network retry với business conflict.

**Một cutover thành công phải bảo vệ cả những requests đã gửi nhưng mất ACK**, không chỉ documents tại checkpoint.

## 59. Bài tập A — Thiết kế writer handoff cho hệ Orders

Bối cảnh:

~~~text
A receives 5,000 writes/s.
B backfill complete.
CDC lag ranges from 2 to 20 seconds.
API has 20 pods and 6 background workers.
Some writes use conditional stock updates.
A and B are independent NoSQL clusters.
Business accepts at most 60 seconds write downtime.
~~~

Hãy:

1. Định nghĩa authority A/B trong từng pha.
2. Liệt kê writers ngoài HTTP API.
3. Thiết kế barrier với 6 workers đang chạy.
4. Xác định ledger/idempotency state cần chuyển.
5. Đặt freeze/drain và unknown outcome policy.
6. Giải thích vì sao đổi connection string chưa đủ.
7. Thiết kế fencing hoặc phương án ngừng ghi được hỗ trợ.
8. Đặt thứ tự barrier–fence–owner switch và lý do.
9. Khi lag 20 giây, cần metric gì để dự đoán cửa sổ 60 giây?
10. Đặt probes xác nhận B writer.
11. Nếu B commit 100 writes mới rồi read p99 xấu, rollback thế nào?
12. Viết ít nhất năm điều kiện NO-GO.

## 60. Bài tập B — Định tuyến đọc theo consistency

Các endpoint:

~~~text
POST /orders            creates order, returns 201.
GET  /orders/{id}       users expect immediate result.
GET  /catalog           accepts staleness <= 15 seconds.
GET  /inventory/final   must not oversell.
GET  /search            eventual index.
GET  /admin/export      sensitive multi-tenant data.
~~~

Yêu cầu:

1. Endpoint nào có thể chuyển read sang B khi A vẫn writer?
2. Endpoint nào cần authoritative read hoặc version token?
3. Viết chính sách khi CDC lag 8 giây và khi 30 giây.
4. Tạo shadow read metrics và sampling plan.
5. GET trả 404 ở B nhưng A có record là lỗi gì?
6. Cache/index nào có thể stale dù CDC lag thấp?
7. Tenant boundary phải enforce ở đâu?
8. Khi search score/rank khác hợp lệ, so bằng tiêu chí nào?
9. Sau khi B là writer, read fallback A có thể chấp nhận khi nào?
10. Chọn dashboard SLI và các stop conditions.

## 61. Bài tập C — Quyết định GO/NO-GO

Giả định:

| Tín hiệu | Quan sát |
|---|---|
| Backfill key ranges | 100% |
| CDC partitions applied qua barrier | 17/18 |
| Unresolved DLQ records | 3 |
| Business inventory mismatch | 0 |
| Tenant authorization test | Pass |
| Shadow read mismatch | 0,03%, chưa phân loại |
| API p99 canary | 280 ms |
| API p99 SLO | 350 ms |
| Disk free ở B | 23% |
| Old worker write path revoked | Chưa xác nhận |
| Restore drill B | Pass |
| Change owner/on-call | Sẵn sàng |

Hãy:

1. Có được GO ngay không? Vì sao?
2. Chỉ ra hard blockers, soft warnings và evidence còn thiếu.
3. Khi nào một mismatch 0,03% có thể chấp nhận?
4. Vì sao 17/18 partitions chưa đủ cho toàn scope?
5. Canary p99 đạt SLO giải quyết được rủi ro nào, chưa giải quyết rủi ro nào?
6. Cần xác minh old worker đã bị fence thế nào?
7. Hãy đưa ra remediation và điều kiện chạy lại preflight.
8. Khi disk free giảm nhanh, có cần điều chỉnh rollout không?
9. Ai ký quyết định GO/NO-GO, lưu audit gì?
10. Nếu B đã active rồi mới phát hiện lỗi, có thể failback khi nào?

**Gợi ý:** Khi một partition chưa vượt barrier và old writer chưa bị fence, không nên kích hoạt B làm writer cho toàn scope chỉ vì throughput và p99 đều tốt.

## 62. Các hiểu nhầm thường gặp

| Nhận định sai | Vì sao sai | Cách đúng |
|---|---|---|
| “Backfill 100% là cutover xong” | Write mới/delete có thể thiếu | CDC + barrier + reconcile |
| “Hai cụm đều online nghĩa là HA” | Có thể dual authority | Fencing/single writer |
| “DNS switch là khóa old writer” | Pool, cache và old connections | Commit-boundary enforcement |
| “Lease timeout đủ chống stale worker” | GC/network pause có thể làm chạy lại | Fencing token |
| “Dual write luôn tốt hơn CDC” | Partial commit, ordering | One authority + durable sync |
| “Lag=0 nghĩa dữ liệu trùng” | Có thể thiếu partition/DLQ | Coverage + applied watermark |
| “Count bằng nhau là đủ” | Version/deletion/PII khác nhau | Reconcile by key/invariant |
| “Mọi GET có thể đọc eventual” | Read-your-writes/rights khác | Per-operation read contract |
| “Canary nhanh thì production nhanh” | Traffic mix/load khác | Representative load/SLI |
| “POST timeout chắc chắn chưa commit” | ACK có thể mất | Ledger/idempotency |
| “Sau cutover muốn route writer A lúc nào cũng được” | B-only ACK writes sẽ mất | Reverse sync/roll forward |
| “Read fallback về A luôn an toàn” | A có thể stale | Owner/version/freshness checks |
| “Check epoch ở client là đủ” | Race check–commit | Enforcement at commit boundary |
| “Wall-clock timestamp xác định order” | Clock skew/reordering | Source commit position/version |
| “CDC có thứ tự toàn cluster” | Nhiều streams chỉ per partition | Ordering/cut semantics |
| “Delete không cần replay” | Backfill có thể hồi sinh record | Tombstones/suppression |
| “Index tên giống nhau thì query giống nhau” | Planner/collation/types khác | Query semantics tests |
| “Data ở B đúng nên quyền ở B cũng đúng” | IAM/RBAC độc lập | Security acceptance |
| “Pod Ready nghĩa cutover an toàn” | Worker cũ/CDC/quorum chưa đủ | Multi-layer gates |
| “Gặp lỗi mở cả A và B để cứu” | Split brain, phá invariant | Safe owner/no-writer state |
| “GO/NO-GO là cảm nhận của operator” | Không có evidence | Measurable contract |
| “Hạ consistency để chữa timeout” | Có thể phá correctness | Bảo vệ business invariants |

## 63. Câu hỏi tự kiểm tra

1. Backfill, deploy ứng dụng và cutover khác nhau thế nào?
2. Source of truth và write authority khác với địa chỉ server ở đâu?
3. Single-writer có nghĩa chỉ một process được chạy không?
4. Vì sao hai independent clusters cùng nhận writes tạo split brain?
5. Fencing epoch khác lease timer thế nào?
6. Check epoch trước khi ghi tại client có race gì?
7. Dual write trực tiếp có thể partial commit ra sao?
8. Captured, published và applied CDC watermark khác gì?
9. Stable source barrier cần những điều kiện nào?
10. Vì sao log retention ảnh hưởng khả năng cutover?
11. In-flight write có thể commit sau khi route switch ra sao?
12. Unknown write outcome cần xử lý thế nào trước retry?
13. Idempotency ledger có cần nằm trong migration scope không?
14. Vì sao tombstones và TTL cần đồng bộ?
15. Count bằng nhau chưa chứng minh data equivalence ở đâu?
16. So hai databases tại cùng logical cutoff có ý nghĩa gì?
17. Khi nào chuyển từng tenant/key độc lập là hợp lệ?
18. Shadow read và canary read khác nhau ở đâu?
19. Read-your-writes cần route/token/version gì?
20. Vì sao read B có thể trả 404 giả?
21. DNS TTL có revoke old writer được không?
22. Freeze admission khác drain in-flight thế nào?
23. State machine cutover cần ghi những pha nào?
24. Chứng cứ nào cho thấy A đã bị fence thật?
25. Một GO/NO-GO cần evidence về business, DB, SLO, security nào?
26. Vì sao lag=0 chưa đủ để GO?
27. Rollback trước activation khác sau activation thế nào?
28. Reverse CDC có tự động bảo đảm failback không?
29. Khi nào roll forward phù hợp hơn quay về A?
30. Read fallback sau khi B là writer cần điều kiện nào?
31. MongoDB replica election khác cluster-to-cluster migration thế nào?
32. Cassandra consistency level có tạo global cutover fence không?
33. DynamoDB Streams có tự thay backup/PITR không?
34. Vì sao Redis lease cần downstream fencing?
35. Có thể cắt chuyển search alias độc lập với nguồn giao dịch không?
36. Security regression tại B có thể phát hiện bằng tests nào?
37. Vì sao dashboard cần scope/epoch?
38. Old background worker có thể tạo incident gì?
39. Nếu CDC áp 17/18 partitions, toàn scope có đủ điều kiện không?
40. Thế nào là COMPLETE, ai có quyền chấp nhận?

## 64. Tổng kết: chuyển quyền, không chỉ chuyển kết nối

Chuyển NoSQL từ A sang B phải bảo vệ đồng thời **nguồn ghi có thẩm quyền duy nhất**, **định tuyến đọc phù hợp consistency contract**, và **tính đầy đủ của dữ liệu và business outcomes**. Backfill, CDC, connection strings và canary là các công cụ hỗ trợ, không thay thế được giao thức handoff. Mọi write đã ACK ở A cần được hội tụ hoặc đối soát khi B nhận quyền; mọi write đã ACK ở B phải được bảo toàn khi cân nhắc failback.

Chu trình thực hành:

~~~text
1. Định nghĩa business invariants, scope, SLO và RPO/RTO.
2. Inventory tất cả writers, readers, workers, secrets và routes.
3. Dựng B với schema/index/security/backup đầy đủ.
4. Backfill + CDC với checkpoint, tombstones và version rules.
5. Shadow read và reconcile tại cùng logical cutoff.
6. Xác minh capacity, query correctness và go/no-go evidence.
7. Freeze admission, drain in-flight và đối soát unknown outcomes.
8. Chốt source barrier; B áp durable đến mốc đó.
9. Fence A và chuyển owner/epoch sang B.
10. Bật B write, kiểm tra conditional/idempotent operations.
11. Chuyển read traffic theo consistency contracts.
12. Giám sát p99, business invariants, privacy và stale routes.
13. Nếu lỗi, chọn abort/contain/roll forward/reverse handoff đúng pha.
14. Ghi audit, cập nhật backup/DR và decommission old paths an toàn.
~~~

**Kết luận cốt lõi:** *Chỉ tuyên bố cắt chuyển thành công khi có bằng chứng không còn writer cũ nào có thể commit ngoài thẩm quyền, mọi kết quả nghiệp vụ đã xác nhận vẫn được bảo toàn và đường đọc/khôi phục đáp ứng đúng hợp đồng với người dùng.*








