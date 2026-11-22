# Hoàn thiện quyết định lựa chọn, sơ đồ và sổ tay vận hành bằng kết quả thực nghiệm

Một nhóm Java xây dựng nền tảng đặt phòng đa tenant đã nghiên cứu document database, key-value store và wide-column database. Họ có bảng benchmark point read, một bản demo lưu Order và một sơ đồ gồm ba hộp: API, database, cache. Cuộc họp chuẩn bị triển khai production bắt đầu với câu hỏi tưởng đơn giản: **“Chọn hệ nào và ai chịu trách nhiệm nếu cụm lỗi lúc nửa đêm?”**

Nhóm phát hiện ba khoảng trống:

1. Benchmark chỉ đo truy vấn theo ID, trong khi API quan trọng nhất là **giữ một suất phòng duy nhất khi nhiều khách đặt đồng thời**; chưa có test mất ACK, failover hoặc transaction scope.
2. Sơ đồ chỉ cho biết thành phần kết nối với nhau, chưa thể hiện **nguồn dữ liệu có thẩm quyền, partition key, vị trí giao dịch, outbox, cache, vùng dữ liệu, backup và đường phục hồi**.
3. “Có backup” và “managed service” xuất hiện trong quyết định, nhưng chưa ai thử restore, xác nhận RPO/RTO, ghi cảnh báo, người trực, điều kiện dừng khi index build hay câu lệnh đối soát sau sự cố.

Bài thực hành tổng hợp của module **Database No SQL** này hướng dẫn chuyển **kết quả thực nghiệm có thể truy vết** thành ba sản phẩm bàn giao nhất quán:

- **Quyết định lựa chọn (decision record/ADR):** chọn một phương án phù hợp, nêu bằng chứng, đánh đổi, rủi ro, điều kiện triển khai và khi nào phải đánh giá lại.
- **Sơ đồ kiến trúc (architecture/operation diagrams):** thể hiện hệ thống sẽ thực sự vận hành như thế nào, trách nhiệm nằm ở đâu, đường ghi/đọc, bất biến, backup, CDC và failure boundaries.
- **Sổ tay vận hành (runbook):** giúp người trực nhận diện tình huống, thực hiện bước an toàn, kiểm tra kết quả và phục hồi mà không phải suy đoán từ sơ đồ.

> **Quy tắc:** Mỗi lựa chọn quan trọng phải trỏ tới **yêu cầu → thí nghiệm → số đo và mức tin cậy → kết luận → thành phần trên sơ đồ → quy trình vận hành tương ứng**. Không có bằng chứng thì ghi `UNKNOWN` hoặc tạo thí nghiệm bổ sung, không biến một kỳ vọng thành một kết quả đã được chứng minh.

## 1. Ba tài liệu là ba góc nhìn của cùng một quyết định

| Sản phẩm | Nó trả lời | Tính chất |
|---|---|---|
| Decision record | Vì sao chọn cách này mà không chọn cách khác? | Lý do, bằng chứng, tradeoff |
| Sơ đồ | Dữ liệu và quyền ghi đi qua các thành phần nào? | Mô hình cấu trúc và luồng |
| Runbook | Làm gì khi thao tác bình thường, thay đổi hoặc lỗi? | Các bước thực thi và điều kiện dừng |

### 1.1. Decision record không phải bản quảng cáo công nghệ

Một ADR tốt có cả điểm mạnh và giới hạn: ví dụ point read của phương án A nhanh hơn, nhưng cần projection cho list-by-tenant; phương án B vận hành đơn giản hơn nhưng chi phí tăng khi query fan-out.

### 1.2. Sơ đồ không phải ảnh trang trí

Nếu ADR nói booking dùng conditional write để không bán trùng, sơ đồ phải chỉ rõ **nơi điều kiện được kiểm atomically** và nơi lưu receipt. Nếu runbook yêu cầu failover, sơ đồ phải hiện replica/quorum/region tương ứng.

### 1.3. Runbook không phải một danh sách lệnh thiếu bối cảnh

Một câu “restart node khi chậm” nguy hiểm nếu node đó là owner cuối cùng của dữ liệu chưa replicated. Runbook phải có tiền điều kiện, blast radius, lệnh từ tài liệu vendor/version, xác nhận sau thao tác và đường escalation.

### 1.4. Kết quả thực nghiệm là cầu nối

Kết quả stress test, recovery drill, index benchmark và tenant isolation test quyết định **đường kiến trúc nào được chọn** và **bảo vệ nào phải có** trong vận hành.

## 2. Định nghĩa “hoàn thiện” bằng tiêu chí bàn giao

Một bộ tài liệu chỉ có thể gọi là hoàn thiện khi:

1. Mọi yêu cầu quan trọng có mã ID, mức độ ưu tiên và phương pháp xác minh.
2. Mọi thí nghiệm ghi cấu hình, dataset, software version, thời gian và kết quả thô/summary có nguồn.
3. Decision record phân biệt **PASS, FAIL, CONDITIONAL và UNKNOWN**.
4. Sơ đồ nhất quán với backend được chọn, deployment topology và invariant.
5. Có runbook cho operation bình thường, thay đổi, incident và restore.
6. Có owner phê duyệt các security/legal/DR hard gates.
7. Biết điều kiện dẫn đến rollback, roll-forward, dừng triển khai hoặc nghiên cứu lại.
8. Tài liệu được versioned cùng ứng dụng, có lịch review khi workload/edition/license/service thay đổi.

### 2.1. Không lẫn “tài liệu hoàn thành” với “hệ thống đã QA”

Bài học hướng dẫn cách làm; mẫu kết quả trong bài **được giả lập để luyện quyết định**, không phải kết quả đo của một provider hay cam kết hiệu năng thực tế.

### 2.2. Một UNKNOWN có thể chặn production

Nếu chưa đo restore time nhưng RTO là hard requirement, không thể kết luận lựa chọn đáp ứng RTO chỉ vì nhà cung cấp có tính năng backup.

### 2.3. Review là một phần của định nghĩa hoàn thiện

Nếu SLO, data residency, retention, schema hoặc giá thay đổi, ADR/sơ đồ/runbook phải được cập nhật đồng thời, không giữ ảnh cũ rồi vận hành theo trí nhớ.

## 3. Bối cảnh capstone: dịch vụ đặt phòng nhiều tenant

Để thống nhất bài thực hành, giả sử nhóm phải chọn NoSQL cho Java 17/Spring Boot service:

~~~yaml
system: booking-api
environment: performance-staging
tenants:
  small: 2000
  large: 4
data:
  orders: 50000000
  averageOrderDocumentBytes: 2048
  growthPerYear: "40% (assumption)"
  retentionMonths: 24
traffic:
  peakPointReadsPerSecond: 8000
  peakListQueriesPerSecond: 1000
  peakMutationsPerSecond: 2000
  distribution: "hot-tenants + long-tail"
criticalInvariant:
  - "One active booking per room/time slot"
  - "No duplicate committed effect per business command"
  - "No acknowledged write loss in the agreed failure model"
targets:
  getByIdP99Ms: 120
  confirmBookingP99Ms: 250
  listBookingsP99Ms: 400
  unexpectedErrorRate: "at most 0.2%"
  rpoMinutes: 5
  rtoMinutes: 45
  residency: "approved region only"
~~~

**Toàn bộ số liệu, giới hạn, ứng viên và kết quả thử nghiệm trong bài là giả định phục vụ giảng dạy**, không phải cấu hình hoặc benchmark chính thức của một sản phẩm NoSQL.

### 3.1. Use cases chính

`GetBooking(tenantId, bookingId)`, `ListRecentBookings(tenantId, timeRange)`, `ReserveSlot(tenantId, roomId, timeSlot, commandId)`, `CancelReservation`, `PublishBookingEvent`, `RestoreFromBackup`.

### 3.2. Thành phần phụ trợ

Service xác thực/ủy quyền, outbox publisher, message broker, search/reporting projection, cache có TTL và hệ backup/observability. Cần định nghĩa rõ cái nào authoritative, cái nào eventual.

### 3.3. Các hard gates

No double-booking, tenant isolation, quyền sử dụng/license đúng, residency, RPO/RTO đã kiểm bằng drill và operational support theo yêu cầu.

### 3.4. Điều gì không nằm trong scope?

Chưa chọn provider thanh toán hay kênh gửi email thực; external side effects phải được thiết kế riêng với idempotency/provider receipts, không coi database transaction bao gồm chúng.

## 4. Từ yêu cầu văn xuôi sang Requirement ID

| ID | Yêu cầu | Mức độ | Cách kiểm |
|---|---|---|---|
| R01 | Không trùng room/slot reservation | Hard gate | Concurrent write test |
| R02 | Retry cùng command không double effect | Hard gate | Lost-ACK/idempotency test |
| R03 | Get booking p99 ≤120 ms ở peak | SLO | Open-loop load benchmark |
| R04 | Confirm p99 ≤250 ms ở peak | SLO | Conditional-write load |
| R05 | List booking p99 ≤400 ms | SLO | Tenant/time-range query test |
| R06 | Unexpected errors ≤0,2% | SLO | End-to-end run |
| R07 | RPO ≤5 phút, RTO ≤45 phút | Hard gate | Restore/failover drill |
| R08 | Không truy cập dữ liệu chéo tenant | Hard gate | Authorization/partition tests |
| R09 | Chạy trong khu vực được phê duyệt | Hard gate | Residency review |
| R10 | Vận hành với năng lực đội hiện có | Constraint | Runbook drill, staff review |
| R11 | TCO 36 tháng trong ngân sách | Constraint | Usage-based cost model |
| R12 | Có đường di chuyển và xuất dữ liệu | Risk gate | Export/import POC |

### 4.1. Requirement phải kiểm chứng được

“Nhanh”, “ổn định”, “rẻ” không thể tạo pass/fail. `p99 < 120 ms ở 8.000 reads/s` rõ hơn nhưng còn cần dataset, consistency, error handling và latency measurement window.

### 4.2. SLO khác hard invariant

Một run vượt p99 vài mili-giây có thể cần tuning/waiver có trách nhiệm; double-booking hoặc lộ dữ liệu tenant không thể đổi lấy điểm performance.

### 4.3. Thêm owner và review date

R07 cần owner SRE/DR; R08 cần security; R11 cần finance/engineering. Những người này duyệt bằng chứng, không chỉ nhận thông báo.

### 4.4. Đừng tự đặt RPO/RTO theo feature name

“Có replica”, “có backup” không cho biết **mất dữ liệu tối đa bao nhiêu** và **bao lâu dịch vụ chạy lại**. Cần đo recovery drill trong failure model.

## 5. Thiết kế bằng chứng traceable

~~~mermaid
flowchart LR
    R["Requirement R01"] --> T["Test T-CONC-01"]
    T --> A["Artifact: logs, versions, receipts"]
    A --> G["Gate: PASS/FAIL"]
    G --> D["ADR-001: decision"]
    D --> S["Diagram: write authority"]
    S --> O["Runbook: concurrency incident"]
~~~

### 5.1. Evidence ID không chỉ là đường dẫn dashboard

Một dashboard thay đổi theo thời gian có thể không tái hiện được. Lưu export/histogram, test seed, dataset version, topology, time range, build commit và command/config của load generator.

### 5.2. Bằng chứng phải gắn phạm vi

`T-CONC-01 PASS` chỉ cho biết những điều kiện được test, ví dụ **một region, một primary source, hai API instances, 100 concurrent attempts, retry sau commit**. Nó không tự chứng minh active-active multi-region.

### 5.3. Khoảng trống cần được thấy rõ

Trạng thái `UNKNOWN` với owner, deadline và action tốt hơn bảng đầy dấu tick thiếu chứng cứ.

### 5.4. Nhiều tài liệu trỏ cùng ID

ADR trỏ `R01/T-CONC-01`; sơ đồ annotate component `AUTHORITY-RESERVE`; runbook `RB-DOUBLE-BOOKING` dẫn tới cùng invariant và metric.

## 6. Chọn ứng viên theo khả năng đáp ứng nghiệp vụ

Capstone so ba **phương án kiến trúc giả định**:

| Mã | Mô tả | Cách dự kiến bảo vệ booking |
|---|---|---|
| A | Managed document NoSQL + transactional aggregate | Conditional claim/transaction trong supported scope |
| B | Managed key-value NoSQL + conditional items | Unique slot key và transactional writes khi được hỗ trợ |
| C | Self-managed wide-column NoSQL + LWT/authority service | CAS cho slot, outbox/recovery protocol |

### 6.1. Tên phương án bao gồm kiến trúc

Chọn “DynamoDB” hay “MongoDB” trên logo chưa đủ. Cần key design, consistency/write concern, region, indexes, backups, managed tier và transaction scope.

### 6.2. Không biến kiến trúc B thành bản sao của A

B có thể cần một materialized view cho tenant listings; A có thể dùng compound index và document aggregates; C có thể tạo table theo access pattern. So cùng **kết quả API** chứ không nhất thiết dùng query syntax giống nhau.

### 6.3. Giới hạn ứng viên

Một phương án không có supported method để bảo vệ `R01` trong kiến trúc dự kiến phải bị loại hoặc thiết kế lại trước khi làm load test.

### 6.4. Đảm bảo cùng mức bảo vệ

Không cho một phương án dùng eventual read và bỏ uniqueness, trong khi phương án khác phải dùng transaction mạnh, rồi so p99 và kết luận bản thứ nhất nhanh hơn.

## 7. Ma trận thiết kế thí nghiệm

| Test ID | Kịch bản | Điều cần giữ cố định | Kết quả cần lưu |
|---|---|---|---|
| T-GET-01 | Read by ID | Data size, hot/cold ratio, consistency | p50/p95/p99, success/error |
| T-LIST-01 | Tenant/time-range list | Skew, page size, indexes | p99, scanned/returned, cost |
| T-CONC-01 | 100 writers tranh một slot | 1 slot, distinct commandIds | Một success, no duplicate |
| T-IDEM-01 | Retry cùng commandId | Lost response after commit | Một effect, same receipt |
| T-LOAD-01 | Mixed peak workload | Offered RPS, sizes, retries | p99, error, costs |
| T-FAIL-01 | Primary/leader failover | Write concern, clients | Availability, ACKed writes |
| T-DR-01 | Restore từ backup | Snapshot age/size, procedure | Measured RPO/RTO |
| T-SEC-01 | Cross-tenant attempts | Auth scopes, tenant keys | Không leak/unauthorized write |
| T-OPS-01 | Index build/rebalance under load | Peak traffic, monitors | Degraded SLO, recovery time |
| T-EXIT-01 | Export/import sample | Canonical records, events | Data fidelity, effort/time |

### 7.1. Chuẩn hóa workload trước khi chạy

Point reads 8.000/s, list queries 1.000/s, mutations 2.000/s, 4 whale tenants, long-tail 2.000 tenants, document size distribution và TTL/index mix phải có cùng ý nghĩa giữa các ứng viên.

### 7.2. Arrival model

Open-loop arrivals bộc lộ queueing khi DB chậm; closed-loop có thể giảm offered load theo response latency. Ghi scheduled, sent, successful, failed requests để tránh coordinated omission.

### 7.3. Ghi version chính xác

Server version/edition/SKU, Java driver, config, transaction options, schema/indexes và data generator seed. Kết quả của release cũ không tự động đúng cho release mới.

### 7.4. Không thử lỗi phá hủy trong production

Fault injection, node kill và restore drill thực hiện trong sandbox/performance environment được cho phép, có backup và giới hạn tốc độ/tài nguyên.

## 8. Mẫu evidence record cho một thí nghiệm

~~~yaml
evidenceId: "E-T-CONC-01-A-20261114"
requirementIds: ["R01", "R02"]
candidate: "A"
environment: "isolated-performance-staging"
engineVersion: "<record actual version>"
driverVersion: "<record actual version>"
appCommit: "<git-sha>"
dataSeed: "seed-20261114"
test:
  concurrentDistinctCommands: 100
  slotsAvailable: 1
  duplicateDelivery: true
  lostAckAfterCommit: true
result:
  uniqueCommittedReservations: 1
  stockRemaining: 0
  duplicateBusinessEffects: 0
  outcome: "PASS (illustrative)"
artifacts:
  rawRequestHistory: "<path>"
  authoritativeSnapshot: "<path>"
  driverMetrics: "<path>"
review:
  owner: "<role>"
  verifiedAt: "<timestamp>"
  knownLimits: ["single region", "one authoritative slot"]
~~~

### 8.1. Nguồn số đo phải có thể tái dựng

Không chỉ lưu screenshot `100% PASS`, mà lưu inputs, write receipts, entity versions và điều kiện failpoint để người khác có thể lặp lại.

### 8.2. Dữ liệu trong mẫu là minh họa

`PASS (illustrative)` không được chuyển nguyên xi thành chứng cứ dự án thật. Khi thực hành, thay bằng log/số đo thu được.

### 8.3. Privacy trong artifacts

Không lưu token, mật khẩu, raw PII/payment details vào test artifacts. Dùng synthetic IDs, redaction và giới hạn quyền truy cập.

## 9. Bảng kết quả thí nghiệm giả lập

Giả định các tests đã được thực hiện công bằng trong cùng SLO, dataset và điều kiện đo:

| Đo lường | Target | A | B | C |
|---|---:|---:|---:|---:|
| Get-by-ID p99 (ms) | ≤120 | 83 | 68 | 91 |
| Confirm p99 (ms) | ≤250 | 173 | 214 | 231 |
| Tenant list p99 (ms) | ≤400 | 248 | 510 | 365 |
| Unexpected error rate (%) | ≤0,2 | 0,08 | 0,14 | 0,17 |
| Double bookings in concurrency test | 0 | 0 | 0 | 0 |
| Duplicate effects after lost ACK | 0 | 0 | 0 | 0 |
| Restore RPO observed (minutes) | ≤5 | 2 | 2 | 4 |
| Restore RTO observed (minutes) | ≤45 | 31 | 38 | 52 |
| Cross-tenant leaks | 0 | 0 | 0 | 0 |

**Cảnh báo:** Đây là **dữ liệu bài tập giả lập**, không phải phép thử đã thực hiện trong cuộc hội thoại, không phải benchmark hoặc SLA của bất kỳ vendor nào.

### 9.1. Tại sao không chọn B chỉ vì point read nhanh nhất?

B đạt 68 ms ở Get nhưng **không đạt list-by-tenant p99 510 ms** với thiết kế đã thử. Có thể thêm read model/index, nhưng cần thử lại cả correctness, lag và chi phí trước khi thay `FAIL` thành `PASS`.

### 9.2. Tại sao C chưa thể đưa production?

C có restore RTO 52 phút, vượt hard gate 45 phút. C cần thay backup/restore design, giảm data footprint hoặc tăng recovery capacity rồi chạy lại T-DR-01.

### 9.3. A có điểm yếu không?

Có: Get không nhanh bằng B, giá managed/feature limitations chưa biết, và một số transaction/index operations có thể tăng chi phí. ADR phải giữ các đánh đổi này.

### 9.4. Không gộp hard gates thành điểm trung bình

Không dùng weighted score để bù `R07 FAIL` của C bằng p99 tốt hoặc giá thấp. Chỉ tính score cho các ứng viên đã qua gates.

### 9.5. Độ tin cậy

Một lần run không đủ kết luận chắc chắn. Báo percentile với số samples, repeated runs/variance, failure windows và môi trường; số minh họa này giả định đã được xác minh.

## 10. Tách PASS, FAIL, CONDITIONAL và UNKNOWN

| Status | Ý nghĩa | Hành động |
|---|---|---|
| PASS | Đáp ứng trong phạm vi test đã ghi | Tiếp tục nếu các gates khác đạt |
| FAIL | Không đạt ngưỡng hoặc vi phạm invariant | Loại/đổi design/thử lại |
| CONDITIONAL | Đạt nếu áp cấu hình hoặc biện pháp được ghi rõ | Chặn triển khai tới khi điều kiện có evidence |
| UNKNOWN | Chưa có bằng chứng đủ mạnh | Thực hiện thêm test/review |
| NOT_APPLICABLE | Không có trong scope đã được chấp thuận | Ghi lý do và owner |

### 10.1. Cấu hình có điều kiện phải được theo dõi

Ví dụ A chỉ đạt R07 khi PITR bật và restore script đã chạy, không được chuyển thành PASS cho tier không có PITR.

### 10.2. Unknown không thể mặc định thành Pass

Nếu chưa xác minh license hoặc dữ liệu backup có nằm đúng region hay không, dừng ở approval gate tương ứng.

### 10.3. Conditional có thể trở thành thiết kế

Nếu B chỉ đạt list p99 khi có materialized view, sơ đồ và runbook phải thêm projection/CDC, monitoring lag, reindex và rebuild.

## 11. Đọc kết quả theo từng bất biến

### 11.1. No double booking

Oracle là số reservation active cho một `(tenantId,roomId,timeSlot)` không vượt capacity, unique receipt per commandId và không có success response thiếu reservation.

### 11.2. Idempotency

Một HTTP timeout sau DB commit có thể tạo retry; cả hai attempts dùng cùng key. Không double decrement, double outbox hay double payment side effect.

### 11.3. Concurrency

Khi hai **khác commandIds** cùng giành một slot còn một, chỉ một commit. Khi hai **cùng commandId**, cả hai xem một committed result.

### 11.4. Acknowledged write durability

Nếu hệ ACK theo write concern/consistency policy rồi primary failover, kiểm những writes nào còn theo failure model đã cam kết; “không mất dữ liệu” không phải tuyên bố không giới hạn.

### 11.5. Recovery

RPO/RTO đo từ incident boundary và nguồn dữ liệu phục hồi thực, không suy từ backup job status. Kiểm TTL, indexes, outbox offsets và tenant authorization sau restore.

## 12. Đọc kết quả hiệu năng mà không bị che lỗi

### 12.1. Client-visible latency

Đo từ lúc client gửi đến khi nhận kết quả, bao gồm queue/pool/network/retry; không dùng riêng DB execution time để làm p99 của API.

### 12.2. Successful throughput và offered load

Khi hệ quá tải, generator closed-loop có thể tự giảm traffic. Báo cả scheduled/sent/success/error, không chỉ success RPS.

### 12.3. Latency của errors

Một run bỏ timeout khỏi histogram thành công có thể báo p99 đẹp trong khi availability xấu. Xem tail latency cùng error/deadline rate.

### 12.4. Hot tenants

Cluster average có thể che một whale tenant bị throttle; thêm breakdown theo tenant tier/shard/operation với nhãn cardinality có kiểm soát.

### 12.5. Repeated runs

Giữ median/range/interval của p99 qua nhiều runs. Nếu một candidate chỉ đạt SLO ở run tốt nhất mà thường xuyên fail, ADR phải nói rõ.

## 13. Từ workload đến mô hình chi phí

Một phương án đáp ứng SLO nhưng vượt ngân sách 36 tháng vẫn cần xem xét. Mô hình TCO phải bao gồm:

~~~text
TCO_36m =
    platform compute / request units
  + data + index + replica storage (theo đúng meter)
  + backup/PITR/restore drills
  + network/cross-zone/cross-region/egress
  + observability/KMS/support
  + staffing/on-call/upgrades
  + migration/dual run/exit reserve
~~~

### 13.1. Không nhân replica hai lần

Một managed service có thể đã bao gồm replication trong storage unit rate, hệ khác tính theo node/storage. Đọc meter thực.

### 13.2. Query shape làm thay bill

List 32 buckets có thể tiêu nhiều read units hơn một point lookup, dù chỉ một HTTP request. Index có thể giảm read cost nhưng tăng write/index storage.

### 13.3. Self-managed không miễn phí vận hành

CPU/disk/network, compaction/repair, 24/7 on-call, backup drills, bảo mật và incident response đều là chi phí.

### 13.4. Peak và DR

Provision peak/N−1 headroom, cross-region replica và temporary restore cluster có thể làm hai phương án đổi thứ hạng.

### 13.5. Giá giả định không là báo giá

Trong capstone, chi phí chỉ có ý nghĩa khi có chính sách unit pricing theo region/SKU/contract với ngày hiệu lực. Không tự suy từ số minh họa.

## 14. So sánh TCO giả lập

Giả sử nhóm lập báo giá minh họa cho cùng SLA/HA/backup requirements và ba kịch bản 36 tháng:

| Phương án | Base 36 tháng (USD giả định) | High growth (USD giả định) | DR/exit risk |
|---|---:|---:|---|
| A | 145.000 | 225.000 | Cần kiểm egress và vendor API |
| B | 128.000 | 245.000 | Read model/extra units chưa tối ưu |
| C | 118.000 | 190.000 | Nhiều giờ SRE, restore chưa đạt |

### 14.1. Bảng chưa đủ để mua

Giá là số giả lập, không chứa hợp đồng thực, thiếu xác minh license/SKU và support. Dùng để tập so phương án đã đạt hard gates.

### 14.2. Giá thấp hơn không thắng nếu thiếu RTO

C rẻ nhất base nhưng restore 52 phút vượt RTO 45; phải sửa và thử lại trước khi được cân nhắc.

### 14.3. B cần thử projection

Để sửa list p99, B có thể thêm event-driven read model; sau đó tính CDC lag, dual storage, consistency semantics, support, monitoring và chi phí mới.

### 14.4. Phân tích độ nhạy

Thử read traffic ×2, document size ×2, retention 24→36 tháng, thêm region và tăng peak 3×. Nếu thứ hạng đổi, ghi những biến quyết định thay đổi.

## 15. Ra quyết định có điều kiện

**Quyết định mẫu của bài lab:** chọn **phương án A** cho kiến trúc giai đoạn 1, **với điều kiện** xác minh commercial/license/service terms, backup residency, support, 36-month budget và thực hiện lại smoke/canary tests trong môi trường production-like trước cutover.

### 15.1. Vì sao A?

Trong bộ số liệu giả lập, A đạt tất cả gates kỹ thuật được đo với kiến trúc đã thử; B fail list query, C fail restore RTO. A chưa được nói là tối ưu toàn thế giới hoặc chắc chắn rẻ nhất.

### 15.2. Vì sao không B ngay?

B là phương án dự phòng nếu read model/index redesign làm list API đạt SLO với lag/cost chấp nhận được; cần thí nghiệm mới, không suy thành pass.

### 15.3. Vì sao không C ngay?

C có tiềm năng TCO nhưng nhóm phải giải quyết recovery time, on-call maturity và vận hành compaction/repair, rồi chạy lại drill.

### 15.4. Từ conditional đến approved

Decision status chỉ là `PROPOSED/CONDITIONAL` cho đến khi legal/security/operations phê duyệt tất cả gates. Không tự ghi `APPROVED` khi chưa có owner.

## 16. Mẫu ADR với bằng chứng và quyết định

~~~markdown
# ADR-001: Booking authoritative NoSQL

Status: PROPOSED (pending legal, DR and production-like verification)
Date: YYYY-MM-DD
Owners: Backend, SRE, Security, Finance

## Context
- Workload, tenants, size, peak and critical operations
- RPO/RTO, residency, audit and support requirements

## Requirements
- R01, R02, ... R12 with gates

## Candidates
- A: managed document, specified SKU/version/region
- B: managed key-value, specified mode/region
- C: self-managed wide-column, specified release/replication

## Evidence
| Requirement | Test ID | A | B | C | Artifact |
|---|---|---|---|---|---|
| R01 | T-CONC-01 | PASS | PASS | PASS | ... |
| R05 | T-LIST-01 | PASS | FAIL | PASS | ... |
| R07 | T-DR-01   | PASS | PASS | FAIL | ... |

## Decision
- Choose A for phase 1, conditional on named approvals.

## Consequences
- Use guarded reservation write path and durable receipts.
- Use outbox for downstream effects.
- Define backup/restore and tenant security controls.

## Rejected alternatives
- B: list query p99 failed under current design.
- C: measured restore RTO failed.

## Open risks, owner and date
- License/SKU validation; SRE restore drill; cost model.

## Revisit triggers
- Traffic growth, changed residency, API patterns,
  provider terms, repeated SLO violations, DR miss.
~~~

### 16.1. ADR ghi “vì sao” hơn là chỉ “đã chọn”

Khi người mới hỏi tại sao không dùng B, họ cần thấy kết quả T-LIST-01 và phạm vi đo, không phải lời kể “B chậm”.

### 16.2. Chỉ thay kết luận bằng bằng chứng mới

Nếu B sau redesign đạt list p99 200 ms và RPO tốt, tạo ADR revision/new ADR liên kết T-LIST-02, T-DR-02; không âm thầm sửa số liệu cũ.

### 16.3. Có quyết định nào không thể đảo dễ?

Shard/partition key, data model, API consistency và outbox semantics có thể làm migration tốn kém. Ghi cost of reversal và exit strategy.

## 17. Sơ đồ cần có những lớp nào?

Không phải một hình khổng lồ chứa mọi thông tin. Đề xuất bộ sơ đồ:

| Diagram ID | Nội dung chính | Người dùng |
|---|---|---|
| D01 | Context: clients, API, providers, tenant trust | Product, Security |
| D02 | Containers/services: API, DB, cache, outbox, broker | Backend, SRE |
| D03 | Deployment topology: region/AZ, replica, backup | SRE, DR |
| D04 | Critical write sequence: reserve + retry | Developers, QA |
| D05 | Read and projection flow | Backend, Analytics |
| D06 | Incident/restore/failover flow | On-call, DR |
| D07 | Data/key model: PK/index/TTL/authority | DB owners |

### 17.1. Mọi sơ đồ cần ghi scope và version

Một sơ đồ không có environment, engine version, region hoặc owner dễ bị dùng sai sau migration.

### 17.2. Vẽ ranh giới tin cậy

Nêu service nào kiểm identity/authorization, nơi xác định tenant, nơi dữ liệu có quyền ghi và nơi chỉ là cache/projection.

### 17.3. Dấu hiệu sơ đồ chưa đủ

Không nhìn ra component nào chứa idempotency receipt, outbox hoặc source of truth thì chưa thể suy runbook khôi phục duplicate/lost events.

## 18. Sơ đồ context và trust boundary

~~~mermaid
flowchart LR
    USER["Web / Mobile users"] --> GW["API Gateway"]
    GW --> AUTH["Identity and authorization"]
    GW --> API["Booking API (Java)"]
    AUTH --> API
    API --> DB["Authoritative NoSQL"]
    API --> CACHE["Non-authoritative cache"]
    API --> PAY["Payment provider (external)"]
    DB --> OUT["Outbox / CDC"]
    OUT --> BROKER["Event broker"]
    BROKER --> READ["Search / reporting projection"]
    OBS["Metrics, logs, traces"] --- API
    OBS --- DB
~~~

### 18.1. Không tin tenant từ HTTP body

Authentication layer xác minh principal; Booking API map quyền tenant và đưa trustedTenantId vào mọi query/conditional write. Database partitioning không thay kiểm quyền.

### 18.2. Cache không là source of truth

Cache miss/eviction không có nghĩa booking đã bị xóa. Nếu database bị lỗi, không cho phép cache tự biến thành authority để reserve slot.

### 18.3. Payment nằm ngoài DB transaction

Provider charge cần provider idempotency key, receipt và reconciliation. Không vẽ mũi tên `transaction` bao luôn remote payment.

### 18.4. Observability có truy cập nhạy cảm

Logs/traces có thể chứa IDs và metadata; cần redaction, IAM và retention.

## 19. Sơ đồ deployment và failure domains

~~~mermaid
flowchart TB
    subgraph REGION["Approved production region"]
      subgraph ZA["Zone A"]
        A1["Booking API A"]
        D1["DB replica / shard A"]
      end
      subgraph ZB["Zone B"]
        A2["Booking API B"]
        D2["DB replica / shard B"]
      end
      subgraph ZC["Zone C"]
        D3["DB replica / shard C"]
        W["Outbox worker"]
      end
      RT["Managed routing / control plane"] --- D1
      RT --- D2
      RT --- D3
      A1 --> RT
      A2 --> RT
      W --> RT
    end
    BK["Encrypted backup store in permitted location"] <-->|"Backup / tested restore"| REGION
    MON["Alerts / on-call system"] --- REGION
~~~

**Sơ đồ là mô hình khái niệm cho capstone**, không khẳng định một managed service cụ thể cho phép điều khiển trực tiếp replicas, đặt chính xác node theo zone hay expose control plane như hình.

### 19.1. Ghi failure domain

Một region nhiều AZ chịu được một số lỗi AZ, nhưng không tự bảo đảm region outage recovery. Muốn RPO/RTO khi mất region cần thiết kế DR riêng và test.

### 19.2. Ghi authority và commit policy

Sơ đồ deployment cần chú giải transaction/write concern/consistency và failover fencing; 3 replicas không tự nói bao nhiêu ACKs mới được coi committed.

### 19.3. Bảo vệ backup

Backup dùng encryption, IAM khác với account/service chính khi khả thi, retention và location hợp lệ. Không mặc định backup lưu trong cùng một AZ là DR.

### 19.4. Managed responsibility

Những hoạt động do provider thực hiện cần tham chiếu service runbook/SLA; application SRE vẫn xử lý client retry, alarms, restore verification và data reconciliation.

## 20. Sơ đồ đường ghi có điều kiện

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Booking API
    participant D as Authoritative NoSQL
    participant W as Outbox worker
    C->>A: Reserve(slot, commandId=K)
    A->>A: Validate and authorize tenant
    A->>D: Atomic slot claim + receipt + outbox
    alt One valid claim committed
      D-->>A: reservationId R, version v+1
      A-->>C: Confirm reservation R
      W->>D: Read outbox E
      W->>W: Publish E idempotently
    else Slot already owned
      D-->>A: Conflict / insufficient
      A-->>C: Business rejection
    end
~~~

### 20.1. Đường ghi bảo vệ R01

Guarded slot claim/unique key hoặc supported transaction là nơi chặn double-booking. Java `find-then-save` không có CAS không đủ.

### 20.2. Receipt bảo vệ R02

Cùng commandId/payload được replay, không reserve lần thứ hai. Same key/different fingerprint bị từ chối.

### 20.3. Atomic scope phải có thật

Nếu database không thể commit slot, receipt và outbox cùng transaction, sơ đồ phải thể hiện authority/state machine/recovery thay thế; không dán nhãn atomic cho hai writes độc lập.

### 20.4. Outbox có thể giao trùng

Worker publish at-least-once; consumer phải dedupe eventId. Transaction DB không bao gồm message broker ACK nếu không có protocol phù hợp.

## 21. Sơ đồ mất ACK và retry

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant D as DB
    C->>A: Reserve command K
    A->>D: Commit slot R + receipt K
    D-->>A: Committed
    Note over A,C: Response lost
    C->>A: Retry same K, same payload
    A->>D: Resolve receipt K
    D-->>A: Existing reservation R
    A-->>C: Replay R, no second claim
~~~

### 21.1. Timeout là unknown outcome

Không xem timeout là “chưa ghi” và cấp commandId mới. Client giữ cùng ID cho retry; server tra durable receipt ở authority.

### 21.2. Receipt hết TTL

Nếu delayed replay xuất hiện sau receipt expiry, domain uniqueness/bookingId phải tiếp tục bảo vệ trong phạm vi hợp đồng. Ghi retry horizon trong sơ đồ dữ liệu/runbook.

### 21.3. Các lớp retry chồng nhau

Mobile/gateway/SDK có thể cùng retry; mọi attempt của một business intent phải giữ ID và bounded budget. Monitor amplification.

## 22. Sơ đồ đường đọc và eventual projection

~~~mermaid
flowchart LR
    APP["Booking API"] -->|Get by ID / critical read| DB["NoSQL authoritative"]
    DB -->|Outbox / CDC with stable eventId| MQ["Broker"]
    MQ --> PROJ["Tenant list / search projection"]
    APP -->|List bookings, staleness contract| PROJ
    APP -->|Best-effort cache read| CACHE["Cache (TTL)"]
    CACHE -->|Miss fallback| DB
~~~

### 22.1. Read model cần hợp đồng consistency

Nếu `ListRecentBookings` đọc projection eventual, API phải nói độ trễ cho phép; không hứa read-your-writes ngay sau booking nếu projection có thể lag.

### 22.2. R05 cần đo projection thực

Một query list nhanh nhưng chậm cập nhật có thể không đáp ứng nghiệp vụ. Benchmark lưu cả p99 và CDC lag/missing/duplicate event correctness.

### 22.3. Cache invalidation

Cache TTL và event invalidation cần version guard để event cũ không hồi sinh bản đã xóa. Cache data không được dùng quyết định claim slot nếu không có authority bảo vệ.

### 22.4. Nếu không dùng projection

Vẽ trực tiếp compound index/range query trong authoritative DB và nêu chi phí index/scan. Không giữ hộp projection như thành phần tưởng tượng.

## 23. Sơ đồ data/key model

Mẫu logical schema:

~~~text
BookingSlotAuthority
  key: (trustedTenantId, roomId, timeSlot)
  ownerReservationId
  status
  version

Reservation
  key: (trustedTenantId, reservationId)
  roomId, timeSlot, state, version
  commandId

CommandReceipt
  key: (trustedTenantId, operationType, commandId)
  payloadFingerprint
  resultReservationId
  committedVersion
  expiresAt

OutboxEvent
  key: (trustedTenantId, eventId)
  aggregateId, aggregateVersion, type, payload
  publishStatus

TenantBookingIndex / Projection
  key/query: (trustedTenantId, createdAt, reservationId)
~~~

### 23.1. Logical schema chưa là physical partition key

Engine A/B/C có transaction scope và index khác nhau. D01–D07 phải ghi physical PK/SK, shard strategy, relevant indexes, unique constraint và TTL theo **adapter đã chọn**.

### 23.2. Bất biến booking slot

Unique slot owner có thể được thực hiện bằng conditional put/transaction; chọn một authoritative record, không chỉ đặt unique index ở projection eventual.

### 23.3. Tenant isolation

Mọi key và query chứa trusted tenant; index/sort/page token không được tiết lộ records tenant khác. Tenant trong body không quyết định quyền.

### 23.4. TTL không xóa nghiệp vụ gốc

Receipt TTL, cache TTL và booking retention là ba chính sách khác nhau. Xóa receipt không được cho phép một command cũ tạo booking trùng.

## 24. Từ kết quả performance sang index design

R05 yêu cầu list theo `tenantId` và thời gian. Một index có thể thiết kế theo:

~~~text
(tenantId, createdAt DESC, reservationId DESC)
~~~

### 24.1. Tại sao thêm reservationId?

Tạo deterministic tie-breaker khi nhiều reservations cùng timestamp, giúp pagination stable theo một snapshot/cursor contract.

### 24.2. Index không miễn phí

Mỗi mutation có thể cập nhật secondary index, tăng storage và write amplification. Post-index benchmark phải đo cả R04 Confirm latency.

### 24.3. Hot tenant

Nếu một tenant chiếm phần lớn writes, chỉ có partition key `tenantId` có thể nóng. Có thể hash-bucket theo bookingId nhưng list query sẽ fan-out; cần cân bằng workload.

### 24.4. Index build dưới tải

R05 được giải quyết bằng index mới cũng cần runbook tạo index, theo dõi progress, disk/RU headroom, p99, CDC lag và rollback/roll-forward.

## 25. Từ restore drill sang sơ đồ DR

~~~mermaid
flowchart TD
    LIVE["Authoritative DB in approved region"] --> SNAP["Encrypted backups / PITR"]
    SNAP --> REST["Restore into isolated recovery namespace"]
    REST --> VALID["Verify data, versions, indexes, tenant IAM"]
    VALID --> RECON["Reconcile command receipts and outbox offsets"]
    RECON --> SWITCH{"Recovery acceptance gates passed?"}
    SWITCH -->|Yes| CUT["Controlled traffic cutover"]
    SWITCH -->|No| STOP["Stop / escalate; keep source evidence"]
~~~

### 25.1. Recovery không chỉ là dựng DB

Restore có thể cần users/roles, indexes, encryption keys, DNS/routes, cache warming, CDC resume tokens và replay/reconciliation của external providers.

### 25.2. RPO và RTO có mốc đo

RPO: chênh thời gian/committed data giữa incident và điểm dữ liệu khôi phục. RTO: từ lúc dịch vụ không đáp ứng mục tiêu đến lúc **dịch vụ nghiệp vụ** hoạt động an toàn trở lại, theo phạm vi được thỏa thuận.

### 25.3. Unknown outcomes

Nếu client đã nhận ACK nhưng snapshot chưa chứa commit, cần dựa durability/backup chain/transaction logs hoặc reconciliation protocol. Không trả “khôi phục thành công” chỉ vì collections tồn tại.

### 25.4. Vùng dữ liệu được phê duyệt

Backup, scratch restore cluster, support snapshots và metrics/logs đều có yêu cầu residency, không chỉ primary DB.

## 26. Sơ đồ phải có nhãn kiểm chứng

Gợi ý chú thích ở dưới mỗi hình:

~~~text
Diagram: D04 - ReserveSlot write sequence
Architecture version: 1.0
Applies to: Candidate A, phase-1 managed cluster
Invariant: R01, R02
Experiment: T-CONC-01, T-IDEM-01
Read/write scope: one slot authority + receipt/outbox per supported transaction
Consistency/durability: <exact tested policy>
Runbook: RB-BOOKING-CONFLICT, RB-UNKNOWN-COMMIT
Owner: Backend lead / SRE
Last verified: <date>
~~~

### 26.1. Sơ đồ thay đổi khi config đổi

Chuyển từ one region sang multi-region, đổi partition key hoặc dùng event projection mới sẽ thay failure model. Không để ADR và runbook cũ tiếp tục được dùng nguyên xi.

### 26.2. Link diagram với runbook

Người trực nhìn hộp `Outbox Worker` cần biết alert khi lag, cách pause/replay an toàn và kiểm duplicate events.

### 26.3. Không phơi thông tin nhạy cảm

Sơ đồ tài liệu đào tạo không ghi hostnames, secrets, account IDs hoặc chính xác đường private network ngoài nhu cầu/quyền truy cập.

## 27. Định nghĩa runbook: mỗi procedure có cấu trúc

Một runbook đủ để người khác vận hành cần:

| Mục | Câu hỏi |
|---|---|
| Purpose | Thủ tục dùng cho tình huống gì? |
| Trigger | Alert/event/metric nào kích hoạt? |
| Scope | Cluster/tenant/region/API nào bị ảnh hưởng? |
| Preconditions | Quyền, backup, phiên bản, maintenance approval? |
| Risks | Hậu quả có thể xảy ra, blast radius? |
| Steps | Hành động cụ thể, thứ tự, checkpoints? |
| Safety gates | Ngưỡng phải dừng hoặc escalations? |
| Verification | Chứng minh hiệu quả bằng metrics + invariants nào? |
| Rollback/roll-forward | Có thể phục hồi thế nào theo state? |
| Owner | Ai trực, ai phê duyệt, ai có quyền thay đổi? |
| Evidence | Log/artifact/incident ID phải lưu? |

### 27.1. Không chép lệnh chưa xác minh theo engine

Lệnh Redis/Cassandra/MongoDB/cloud CLI có thể khác phiên bản/quyền. Runbook production nên trỏ chính xác vendor supported commands đã thử, không copy một pseudo-command bất kể deployment.

### 27.2. Tránh bước “xóa cho hết lỗi”

Không xóa WAL/oplog/commitlog/SSTables, sửa replica metadata hoặc bỏ quorum bằng tay để “dọn disk” nếu chưa có supported incident procedure.

### 27.3. Mỗi bước cần một tín hiệu đạt

“Chờ một lúc” không đủ. Thay bằng “đợi replication lag dưới giới hạn X trong Y phút và p99/error trở về guardrail”, với X/Y lấy từ SLO đã phê duyệt.

## 28. Runbook RB-READ-LATENCY: đọc chậm

**Trigger:** GET p99 vượt R03 trong nhiều cửa sổ có đủ samples, timeout rate tăng hoặc một tenant tier bị ảnh hưởng rõ.

**Phạm vi:** API GET, database point reads, cache, network, pool và workload hiện tại.

### 28.1. Xác nhận sự cố

Đo client p99, error rate, offered/successful RPS, cache hits, DB latency, pool wait và tenant/shard breakdown. Không đo riêng success latency rồi bỏ timeouts.

### 28.2. Phân loại

Cache misses tăng? Một shard hot? Index scan tăng? Connection pool hết? Node vừa failover/rebalance? Network latency giữa zones đổi?

### 28.3. Hành động an toàn

Giảm background build/scan theo supported procedure nếu tranh I/O; điều chỉnh concurrency/rate limits; khôi phục pool/network nếu đó là gốc. Không tùy tiện hạ consistency.

### 28.4. Điều kiện dừng

Nếu error budget/latency tiếp tục vượt ngưỡng, replica lag tăng nguy hiểm hoặc disk free thiếu, pause change và escalate.

### 28.5. Xác minh sau xử lý

p99/error stable trở lại, request rate đủ, không có divergence/lost ACKed writes, consumer/replication lag bình thường, không có new hotspot.

## 29. Runbook RB-WRITE-CONFLICT: nhiều lệnh đặt phòng cạnh tranh

**Trigger:** conditional conflict rate tăng cao hoặc alert no-double-booking invariant; customer booking failure spike.

### 29.1. Phân biệt conflict hợp lệ

Nếu chỉ còn một slot và 100 users cùng đặt, 99 business rejections có thể đúng. Không tự biến chúng thành DB availability errors.

### 29.2. Khi nào là incident?

Có hai active reservations cho một slot, API trả committed nhưng receipt thiếu, stock âm hoặc inconsistent version. Đây là **correctness incident**.

### 29.3. Phản ứng đầu

Ngăn thêm writes ảnh hưởng cohort/aggregate theo phương án đã phê duyệt, giữ logs/receipts/command IDs và tránh sửa thủ công làm mất bằng chứng. Escalate backend + incident commander.

### 29.4. Đối soát

Kiểm unique slot authority, reservation rows, receipts, outbox events và payment intents; phân biệt attempts trùng với business commands distinct.

### 29.5. Khôi phục

Dùng domain-specific reconciliation/compensation có audit, không tự xóa một booking đã ACK mà không giải quyết nghĩa vụ khách hàng. Test fix dưới cạnh tranh trước khi mở cohort.

## 30. Runbook RB-UNKNOWN-COMMIT: timeout ngay sau ghi

**Trigger:** API/driver báo transaction outcome unknown, client timeout sau lệnh reserve/confirm hoặc leader failover trùng thời điểm commit.

### 30.1. Đừng gửi lệnh mới

Giữ nguyên `(tenant,operation,commandId,payloadFingerprint)`, không generate key mới để retry cùng ý định.

### 30.2. Truy receipt ở authority

Dùng read semantics phù hợp; phân biệt COMMITTED, PENDING/unknown, terminal failure và absent thật. Eventual index not-found không đủ làm bằng chứng chưa commit.

### 30.3. Nếu COMMITTED

Trả result đã lưu, không decrement/charge/outbox lần nữa.

### 30.4. Nếu PENDING/UNKNOWN

Dùng bounded reconciliation theo transaction/command protocol, không cho hai workers cùng tự nhận quyền ghi mà thiếu fencing.

### 30.5. Nếu chắc chắn chưa commit

Retry cùng commandId có conditional business guards và retry budget. Nếu không thể xác định, escalate thay vì đoán.

## 31. Runbook RB-INDEX: tạo hoặc thay đổi chỉ mục

**Preflight:** index schema, query plan baseline, dataset skew, disk/RU headroom, current replicas, recent backup, change approval và rollback plan.

### 31.1. Bắt đầu

Chạy supported online/index build procedure tương ứng engine/version; ghi change ID, operator, timestamp và scope.

### 31.2. Theo dõi

Build progress, scanned/returned, disk IO/temp space, p99 reads/writes, throttle, compaction backlog, replica/CDC lag và alerts.

### 31.3. Guardrails

Nếu p99/error vượt gate, free disk dưới reserve, CDC sắp mất retention window hoặc quorum health không an toàn, dừng/tạm ngừng bằng thao tác được hỗ trợ.

### 31.4. Sau build

Kiểm index READY theo engine, query planner có dùng index, query p99 cải thiện theo T-LIST, write overhead chấp nhận và inserts/updates/deletes trong build vẫn query đúng.

### 31.5. Gỡ index

Không drop index đang được API phụ thuộc nếu chưa có plan/tính toán. Rollback có thể là một change khác, cần QA/approval.

## 32. Runbook RB-CAPACITY: scale và rebalance

### 32.1. Trigger

Hottest node/partition vượt headroom, sustained throttle, storage runway dưới ngưỡng, peak growth hoặc recovery capacity N−1 không còn đủ.

### 32.2. Preflight

Kiểm health, free space từng node, hot key distribution, replica quorum, backup, capacity target, network, residency và supported operations.

### 32.3. Thực hiện

Add nodes/change throughput/resize theo provider/engine runbook; ghi start time, topology version, cohorts/partitions affected.

### 32.4. Trong rebalance

Quan sát source/destination disk/network, cache, p99/error, CDC lag, duplicate/stale routes, rebalancing progress và temp storage.

### 32.5. Hồi phục

Không chỉ chờ “rebalance complete”; đợi catch-up, compaction, cache settling và test GET/CONFIRM/LIST cùng invariant.

### 32.6. Không tự thay shard key để chữa hotspot

Nếu một entity được cập nhật liên tục, hash theo entityId vẫn vào một partition. Phải xem invariant/serialization boundary và design alternatives.

## 33. Runbook RB-FAILOVER: mất node hoặc primary

**Trigger:** replica unavailable, leader election, quorum risk, majority writes unavailable hoặc error spike theo zone.

### 33.1. Phân loại failure domain

Một API pod, một DB node, một AZ, control plane hay network split? Quyết định phụ thuộc topology; không thao tác ngẫu nhiên trên replica còn lành.

### 33.2. Kiểm ACK policy

Xác định write concern/quorum đã dùng và các command outcomes unknown trong khoảng sự cố. Không mặc định mọi acknowledged writes đều tồn tại sau mọi kiểu lỗi.

### 33.3. Theo supported failover

Để engine/provider điều phối election/fencing theo API. Không chỉ đổi DNS về một replica lagging và cho phép hai authorities nhận ghi.

### 33.4. Sau leader change

Kiểm route refresh, pool health, p99, idempotency receipts, replica lag, CDC position và business reconciliation.

### 33.5. Escalation

Nếu không đạt quorum hoặc rollback/recovery semantics mơ hồ, ưu tiên bảo toàn dữ liệu và liên hệ DB on-call/vendor; không hạ durability tùy tiện.

## 34. Runbook RB-RESTORE: kiểm định và khôi phục

### 34.1. Preflight

Chỉ rõ loại sự cố, recovery point, approved backup, encryption key, location, tenant scope, target isolated cluster và nhân sự có quyền approve.

### 34.2. Restore vào namespace cô lập

Không ghi đè primary khi chưa hiểu hậu quả. Dựng môi trường khôi phục tương thích version/edition và storage capacity bằng supported procedure.

### 34.3. Verify data

So ID, version, receipts, tombstones/TTL, outbox, indexes, tenant ACL, encryption và sample business invariants. Đánh giá dữ liệu mất trong khoảng RPO.

### 34.4. Recover connectors

CDC resume tokens, queue offsets, projection rebuild và payment reconciliation phải có kế hoạch để không nhân đôi effects.

### 34.5. Cutover

Khi gates qua, fence/stop old authoritative writes, chốt watermark, cập nhật route/credentials, smoke tests rồi mở traffic theo cohort.

### 34.6. Đo RTO thật

Đo đến khi Booking API có thể xử lý đúng operations, không chỉ khi DB báo restore task finished.

## 35. Runbook RB-CDC: event backlog hoặc projection sai

### 35.1. Trigger

Oldest unprocessed age tăng, consumer lag gần history retention, event duplicates nhiều, search projection thiếu booking sau accepted writes.

### 35.2. Xác định nguồn có thẩm quyền

Booking DB + outbox là authority; projection không được tự cập nhật business state gốc khi nó lag.

### 35.3. Kiểm ordering/idempotency

EventId dedupe, aggregate version monotonic, tombstone handling và consumer ownership; redelivery không gửi external effect thêm lần nữa.

### 35.4. Giải backlog

Tăng consumer capacity/reduce expensive queries/pause competing background tasks khi được duyệt. Không rewind offset mù nếu consumer side effects không idempotent.

### 35.5. Rebuild projection

Nếu mất history window, rebuild từ authoritative snapshot rồi catch-up với consistent watermark/protocol. Verify per-tenant counts/versions trước khi công bố bình thường.

## 36. Runbook RB-SECURITY: tenant isolation hoặc credential sự cố

### 36.1. Trigger

Cross-tenant read/write, leaked credential, unexpected DB admin access, suspicious bulk reads, policy misconfiguration hoặc backups ở location sai.

### 36.2. Chặn có kiểm soát

Thu hồi credential/permission hoặc chặn route/caller theo incident policy; giữ forensic evidence phù hợp. Không xóa logs trước khi điều tra.

### 36.3. Kiểm blast radius

Tra service principals, query filters, tenant key design, backups, index paths, cache keys và analytics exports. Một tenant boundary trong API không đủ nếu batch worker bypass.

### 36.4. Khôi phục

Rotate keys/secrets theo protocol, verify least privilege, replay smoke tests/tenant-negative tests, báo privacy/security owners theo quy định.

### 36.5. Ưu tiên đúng dữ liệu

Không cố giữ SLO bằng mọi giá nếu đang có data exposure; bảo vệ tenant và tuân thủ thông báo sự cố.

## 37. Runbook RB-COST: hóa đơn tăng đột biến

### 37.1. Trigger

Budget forecast vượt ngưỡng, RU/RCU/WCU tăng, scan-to-return ratio xấu, index size tăng bất thường hoặc cross-region egress spike.

### 37.2. Khoanh vùng

Query/tenant tier/index mới, retry amplification, CDC duplicates, backups, autoscale capacity và service SKU/region.

### 37.3. Không tối ưu bằng cách phá correctness

Không giảm write concern, bỏ transaction, tắt audit hoặc xóa backup/PITR bắt buộc chỉ để giảm chi phí.

### 37.4. Hành động

Fix query plan, giới hạn scan, TTL/index policy theo retention, capacity mode adjustments hoặc rate limit hợp lệ sau kiểm performance/correctness.

### 37.5. Xác minh

Billable units giảm, p99/error giữ SLO, không tăng CDC lag hay làm sai data residency; cập nhật forecast 36 tháng.

## 38. Runbook mẫu dưới dạng YAML

~~~yaml
runbookId: "RB-UNKNOWN-COMMIT"
title: "Resolve ambiguous reservation commit"
scope: "Booking API / authoritative NoSQL / production"
owner: "Backend on-call"
approver: "Incident commander when severity >= SEV1"
references:
  adr: "ADR-001"
  diagram: "D04"
  requirements: ["R01", "R02"]
  experiments: ["T-CONC-01", "T-IDEM-01"]
trigger:
  alert: "unknown_commit_outcome_rate > approved threshold"
  symptom: "client timeout after reservation write"
preconditions:
  - "Authorized access to receipt lookup"
  - "Confirmed backend and consistency policy"
steps:
  - "Preserve tenant+operation+commandId+fingerprint"
  - "Read authoritative command receipt"
  - "If COMMITTED, replay recorded reservationId"
  - "If PENDING/UNKNOWN, follow recovery state machine"
  - "If definite no-commit, bounded retry with same commandId"
stopCriteria:
  - "Conflicting authoritative receipts"
  - "Double-booking invariant violation"
  - "Lost acknowledged write suspected"
verification:
  - "One active reservation per slot"
  - "One business effect per commandId"
  - "Outbox event IDs consistent with commits"
artifacts:
  - "incident timeline"
  - "redacted receipt and transaction metadata"
  - "reconciliation report"
~~~

### 38.1. Đây là mẫu logic, không phải automation runnable

Cần bổ sung đúng dashboard URLs, hỗ trợ ACL, supported DB/API commands và thresholds theo môi trường thực trước khi dùng production.

### 38.2. Runbook không được chứa secrets

Sử dụng secret manager/service account role đã được cấp quyền; không chèn token hoặc private keys trong repository.

### 38.3. Incident mode có ưu tiên

Khi nghi ngờ double-booking, không coi giảm latency là nhiệm vụ đầu tiên. Bảo vệ invariant, cô lập lỗi và giữ bằng chứng.

## 39. Đo mức tin cậy của recovery

Một restore drill cần ghi:

~~~text
Failure declared at 10:00
Last recoverable committed point at 09:58
Backup restored at 10:20
Permissions/indexes/CDC verified at 10:26
Booking API smoke/invariant checks passed at 10:31
Traffic resumed safely at 10:31

Observed:
    RPO = 2 minutes
    RTO = 31 minutes
~~~

**Đây là timeline giả định**, không phải kết quả đã đo. Dự án thực phải định nghĩa rõ sự kiện bắt đầu/kết thúc RTO và xác minh commit boundary.

### 39.1. Không so RTO bằng thời gian download backup

Restore tool có thể hoàn tất sau 20 phút nhưng API chưa có indexes, auth, CDC offsets hay DNS; RTO của nghiệp vụ dài hơn.

### 39.2. Drill phải phản ánh data size

Restore 1 GB không chứng minh RTO 45 phút với 100 TB. Size, index footprint, replication, disk/network bandwidth và KMS/API quotas phải phù hợp.

### 39.3. DR chưa hoàn chỉnh khi còn external state

Payment provider có thể đã charge sau backup point; cần reconciliation để tránh tạo charges/booking state sai sau restore.

### 39.4. Chạy lại định kỳ

Backup format/version, dataset growth và topology đổi khiến số đo cũ hết giá trị. Định lịch drills và lưu evidence IDs.

## 40. Capacity và failure headroom

Một cluster hoạt động bình thường ở 60% CPU trung bình có thể không chịu nổi mất một node khi hot tenant traffic dồn cục bộ.

### 40.1. N−1

Thử node/zone failure ở representative peak và giữ latency/error gates trong failure window theo SLO. Không chỉ tính tổng CPU trung bình.

### 40.2. Rebalance window

Thêm node hoặc chuyển shard có thể dùng disk/network tạm thời, làm p99 xấu trước khi cải thiện. Sơ đồ phải phản ánh placement và runbook scale có stop criteria.

### 40.3. Storage headroom

Compaction/index build/restore/snapshot có thể cần temp space. “Còn 10% disk” không chắc đủ; dự báo physical bytes theo engine.

### 40.4. Hot partition

Một tenant hoặc roomId cực nóng không thể tự được chữa bằng tăng số node nếu aggregate chỉ có một authority. Có thể cần queuing/escrow/quota partition design nhưng phải giữ invariant.

### 40.5. Diễn giải ứng viên

Nếu A pass peak nhưng fail N−1, chưa đủ cho production có availability requirement; phải chỉnh topology/tier và test lại.

## 41. Lựa chọn consistency và versioning phải được ghi vào ADR

### 41.1. Critical booking writes

Claim slot cần conditional/transactional semantics đủ để ngăn double booking; response success chỉ sau commit/durability theo contract.

### 41.2. Critical booking reads

Đọc xác nhận reservation cần có đường authoritative có consistency phù hợp; không dùng search projection eventual để quyết định xác nhận đã thành công chưa.

### 41.3. Analytics/list projection

Có thể eventual nếu nghiệp vụ cho phép, nhưng phải công bố staleness bound và monitor lag.

### 41.4. Version monotonic

Outbox/CDC consumers áp aggregateVersion và tombstones để event cũ không ghi đè bản mới hoặc hồi sinh booking đã hủy.

### 41.5. Multi-region

Nếu active-active writes, phải có conflict protocol/authority cho room slot. LWW đơn thuần có thể bỏ một booking đã ACK, không đáp ứng R01.

## 42. Java: business port không để lộ ràng buộc vendor

~~~java
import java.util.Objects;

public record ReserveSlotCommand(
    String trustedTenantId,
    String roomId,
    String timeSlot,
    String commandId,
    String fingerprint
) {
    public ReserveSlotCommand {
        Objects.requireNonNull(trustedTenantId);
        Objects.requireNonNull(roomId);
        Objects.requireNonNull(timeSlot);
        Objects.requireNonNull(commandId);
        Objects.requireNonNull(fingerprint);
        if (trustedTenantId.isBlank() || roomId.isBlank()
                || timeSlot.isBlank() || commandId.isBlank()) {
            throw new IllegalArgumentException("invalid identity");
        }
    }
}

public sealed interface ReservationOutcome
    permits ReservationCommitted, SlotUnavailable, KeyReuseConflict,
            ReservationPending {
}

public record ReservationCommitted(
    String reservationId, long committedVersion)
    implements ReservationOutcome {}
public record SlotUnavailable() implements ReservationOutcome {}
public record KeyReuseConflict() implements ReservationOutcome {}
public record ReservationPending() implements ReservationOutcome {}

public interface ReservationAuthority {
    // Must be guarded by the real NoSQL atomic/transaction
    // boundary or an explicitly recoverable protocol.
    ReservationOutcome reserveOrReplay(ReserveSlotCommand command);
}
~~~

### 42.1. Business contract độc lập persistence API

Service không gọi MongoDB transaction objects hoặc DynamoDB conditions trực tiếp trong controller. Adapter nắm chi tiết theo engine, test contract áp chung cho các adapters.

### 42.2. Interface không tạo atomicity

Định nghĩa method `reserveOrReplay` không làm ba writes bên dưới trở thành một transaction. Driver adapter phải hiện thực guard/receipt/outbox theo khả năng backend.

### 42.3. `ReservationPending` nghĩa gì?

Command có thể đang xử lý hoặc outcome cần reconcile. Không trả pending vĩnh viễn khi không có recovery worker/status lookup và timeout policy.

### 42.4. Trusted tenant

API xác thực principal, quyết định tenant scope rồi mới tạo command. Không cho client tự gán trustedTenantId tùy ý.

## 43. Java: biểu diễn kết quả thử nghiệm bằng dữ liệu typed

~~~java
import java.util.List;
import java.util.Map;

public enum GateStatus {
    PASS, FAIL, CONDITIONAL, UNKNOWN
}

public record MeasuredGate(
    String requirementId,
    String testId,
    GateStatus status,
    String evidenceRef,
    String scopeNote
) {}

public record CandidateAssessment(
    String candidateId,
    List<MeasuredGate> gates,
    Map<String, Double> measuredP99Ms
) {
    public boolean hasUnresolvedHardGate(
            java.util.Set<String> hardRequirements) {
        return gates.stream()
            .filter(g -> hardRequirements.contains(g.requirementId()))
            .anyMatch(g -> g.status() != GateStatus.PASS);
    }
}
~~~

### 43.1. `UNKNOWN` không là một score thấp

Với hard gate, cả FAIL, CONDITIONAL và UNKNOWN đều chặn approval cho đến khi resolution có evidence.

### 43.2. Đây là model, không phải bộ chứng nhận

Một string evidenceRef không chứng minh test đã chạy. Cần artifact immutable/versioned, result provenance và owner approval.

### 43.3. Không trộn ngưỡng khác nhau

P99 GET, Confirm và List có thresholds khác nhau; `Map` theo operation là minh họa, production dùng typed unit/schema/observation windows.

### 43.4. Audit decision evolution

Khi POC chạy lại, tạo assessment version mới và giữ record cũ để biết lý do thay đổi kiến trúc.

## 44. JUnit: hard gate không thể được bù bằng score

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

final class CandidateAssessmentTest {
    @Test
    void rejectsCandidateWithUnprovenRecovery() {
        CandidateAssessment c = new CandidateAssessment(
            "C",
            List.of(
                new MeasuredGate("R01", "T-CONC-01",
                    GateStatus.PASS, "E1", "one region"),
                new MeasuredGate("R07", "T-DR-01",
                    GateStatus.FAIL, "E2", "RTO 52 min")),
            Map.of("getById", 91.0));

        assertTrue(c.hasUnresolvedHardGate(
            Set.of("R01", "R07")));
    }

    @Test
    void unknownIsNotApproval() {
        CandidateAssessment a = new CandidateAssessment(
            "A",
            List.of(new MeasuredGate("R09", "T-SEC-02",
                GateStatus.UNKNOWN, "", "backup residency pending")),
            Map.of());

        assertTrue(a.hasUnresolvedHardGate(Set.of("R09")));
    }
}
~~~

### 44.1. Cần completeness check ở decision tooling thật

Code này kiểm các gate **đã có trong danh sách**; nếu `R07` không được ghi vào `gates`, method minh họa có thể không nhận ra dữ liệu thiếu. Trong hệ quyết định production phải đối chiếu tập tất cả required IDs, reject missing/duplicate/invalid evidence, và phân biệt `N/A` được duyệt.

### 44.2. Test kết luận, không test vendor

JUnit trên model không chứng minh performance/correctness của NoSQL. Nó chỉ chứng minh một rule “hard gate chưa pass thì chưa approve” được biểu diễn nhất quán.

### 44.3. Test tính bất biến

Việc thêm điểm performance cao không được làm `FAIL R07` biến thành eligible.

## 45. Bằng chứng cho correctness của reservation

Các chỉ số cần ghi khi T-CONC-01/T-IDEM-01:

~~~text
Initial slots: 1
Distinct command IDs: 100
Concurrent attempts: 100
After quiescence:
  committed unique reservation IDs: 1
  active slot owners: 1
  duplicate effects: 0
  stock remaining: 0

Then retry winning command 100 times:
  same reservation ID returned
  additional business effects: 0
~~~

### 45.1. Một slot chỉ có một owner

Nếu hai API responses báo success nhưng database cuối chỉ còn một owner do last-write-wins, **test FAIL**: có thể hai khách đã nhận xác nhận.

### 45.2. Không dựa trên HTTP statuses

Timeout sau commit có thể không báo success dù một reservation đã được commit. Đối soát authoritative receipts và business records.

### 45.3. Test mixed duplicates/distinct commands

Tổ hợp 100 intents và 200 retries giúp phát hiện cả contention lẫn double effect. Một test chỉ có retries không chứng minh unique-claim safety.

### 45.4. Multi-process

Chạy qua nhiều Java instances và DB thật; in-memory locks trong một JVM có thể pass test nhưng không bảo vệ cluster.

## 46. Cập nhật ADR khi thí nghiệm mới trái kết quả cũ

Giả sử sau ba tháng workload thay đổi: tenant list queries tăng gấp năm, A p99 vượt R05. Không nên xóa ADR cũ hay giả định chọn A vĩnh viễn.

### 46.1. Tái lập

Xem query plans, new filters, index selectivity, data skew, disk/RU, cache, version và billing. Thu evidence T-LIST-03.

### 46.2. Chọn cách xử lý

Thêm index hoặc read projection, scale theo hot partitions, thay query/API contract, hoặc cân nhắc lại B nếu đã có PoC redesign.

### 46.3. Tài liệu thay đổi cùng nhau

ADR ghi quyết định mới; D05 thể hiện projection hoặc index; RB-CDC và RB-INDEX cập nhật; metrics/alerts cho lag/scan được bổ sung.

### 46.4. Không xóa evidence trước

Giữ ADR-001 và test artifacts để biết giả định nào không còn đúng. Đây là quyết định điều chỉnh theo evidence, không phải lỗi vì “đã chọn sai công nghệ từ đầu”.

## 47. CI/CD và change management

### 47.1. Những thay đổi cần re-evaluate

Engine major upgrade, driver retry behavior, shard key/partitioning, index schema, consistency policy, backup retention, traffic mix, license/SKU hoặc multi-region deployment.

### 47.2. Pipeline guardrails

Smoke tests cho auth, transaction/conditional writes, idempotency, TTL/deletes, schema compatibility và migration contracts; production release có canary và rollback/roll-forward plan.

### 47.3. Data migration

Backfill + CDC catch-up cần watermark, version guards, tombstones, fencing old writer và reconciliation trước cutover. Không chỉ copy data rồi đổi endpoint.

### 47.4. Change freeze

Trong DR incident hoặc heavy rebalance, không tự ý tạo index/upgrade cùng lúc nếu có nguy cơ vượt headroom/consistency. Policy phải dựa khả năng hệ thực.

### 47.5. Runbook versioning

Mỗi change request ghi ứng dụng/DB version và runbook version; sau deploy, xác nhận docs phù hợp topology mới.

## 48. Mẫu release checklist theo bằng chứng

1. ADR đúng ứng viên, edition/SKU, region và approved status?
2. Hard requirements R01–R12 có status và owner?
3. Test artifacts đủ thông tin để tái lập?
4. Transaction/isolation/consistency/write concern đã được ghi?
5. Sơ đồ D01–D07 khớp physical deployment?
6. Backup/PITR được bật và đã thử restore trên dataset đại diện?
7. RPO/RTO đo bằng nghiệp vụ end-to-end?
8. Tenant authn/authz, network/KMS/audit được phê duyệt?
9. No double booking và idempotency tests pass trên DB thật?
10. External payment/notification có dedupe/reconciliation?
11. Có runbook read/write/CDC/index/rebalance/failover/restore/security?
12. Alarms có owner, severity, thresholds và on-call route?
13. Load test giữ p99/errors khi peak và N−1?
14. Có free disk/capacity/CDC history margin?
15. Có SLO/correctness canary gates và roll-forward/rollback plan?
16. Cost budgets/alerts/TCO đã được cập nhật?
17. Có đường export/exit và license/service terms review?
18. Evidence nào còn UNKNOWN? Ai chịu trách nhiệm đóng?
19. Có runbook để dừng rollout khi invariant vi phạm?
20. Đã xác định ngày review kế tiếp khi workload thay đổi?

## 49. Những ngộ nhận làm hỏng quyết định cuối

### “Database nhanh nhất trong benchmark là tốt nhất”

Sai nếu không giữ consistency, invariant, RPO/RTO, workload mix và chi phí như nhau.

### “Một dashboard green là đủ evidence”

Không nếu không biết dataset, version, sampling, threshold và raw/immutable results.

### “Có replica nên không mất acknowledged writes”

Không tự động; cần write concern/replication/failover model và kiểm chứng.

### “Backup configured nghĩa RTO đạt”

Không: phải restore và khởi động lại nghiệp vụ, indexes, permissions, CDC, external reconciliation.

### “Có transaction là không thể double booking”

Không nếu transaction scope/isolation không bao được invariant hoặc side effects nằm ngoài commit.

### “Sơ đồ chỉ cần hộp API và database”

Không khi backup, outbox, cache, authorization, consistency boundary và on-call controls quyết định tính đúng.

### “Runbook chỉ cần lệnh restart”

Không: cần trigger, preflight, safety gates, verified actions, recovery/rollback và escalation.

### “Chi phí tháng đầu quyết định TCO”

Không: storage growth, index, queries, regions, backup, staff, migration và exit cost thay đổi.

### “Managed service không cần SRE”

Không: customer vẫn quản schema, IAM, application SLO, backup drills, budgets và incident response.

### “Chưa biết license có thể làm sau”

Sai nếu legal use/residency là hard gate. Việc tìm hiểu muộn có thể buộc re-platform.

### “Một POC pass có nghĩa không cần thử lại”

Không khi version, workload, region, SKU hoặc key design thay đổi.

### “CDC lag chỉ gây search chậm”

Không nếu backlog vượt event retention: consumer có thể không resume được, phải rebuild.

### “Cache có state thì luôn đọc cache để cứu outage”

Không nếu cache không authoritative và dữ liệu có thể stale/evicted, nhất là no-double-booking.

### “Chỉ cần tính trung bình p99 các nodes”

Không: cần merge latency distributions đúng và đo worst tenant/shard.

### “Sau cutover chỉ cần đổi flag để rollback”

Không nếu target đã nhận writes authoritative; reverse migration/roll-forward cần sync/fencing/version protocol.

### “ADR đã APPROVED thì không được đổi”

ADR là lịch sử quyết định có giả định; evidence mới có thể dẫn tới revision được phê duyệt, không phải im lặng giữ quyết định cũ.

## 50. Bài tập thực hành

### Bài 1 — Requirement IDs

Cho hệ booking gồm Get, List, Reserve, Cancel, Outbox và Restore, viết tối thiểu 12 requirements có hard gates, SLO và experiment IDs.

### Bài 2 — Không dùng chữ “nhanh”

Viết lại “database phải nhanh” thành ba SLO đo được cho GET/CONFIRM/LIST, ghi dataset, peak traffic và consistency.

### Bài 3 — Traceability

Tạo bảng `R01 → T-CONC-01 → E-... → ADR → D04 → RB-...` có owner và thời điểm xác minh.

### Bài 4 — Đọc kết quả

Từ bảng giả lập A/B/C, giải thích vì sao A được chọn có điều kiện, còn B/C cần thí nghiệm gì để thành ứng viên hợp lệ.

### Bài 5 — Hard gates

Một candidate rẻ hơn 40% nhưng RTO 60 phút >45 phút. Vì sao weighted score không được bù?

### Bài 6 — Số đo và bằng chứng

Tạo evidence YAML cho test point read gồm build SHA, engine version, data seed, offered load, p99, error và raw artifact refs.

### Bài 7 — Fairness

Phương án A dùng consistent reads, B dùng eventual reads, C không dùng CAS. Bạn chuẩn hóa benchmark thế nào để có cùng nghĩa business?

### Bài 8 — Query plan

List-by-tenant chậm. Thiết kế composite index hoặc projection và phép thử đo p99, scanned/returned, index write cost.

### Bài 9 — Candidate B redesign

Thêm projection cho B để giảm list p99. Những requirements mới nào liên quan CDC lag, event ordering và rebuild cần kiểm?

### Bài 10 — TCO

Lập cost model 36 tháng có data growth 40%/năm, backups, support, staffing, egress và exit; vì sao giá mỗi request không đủ?

### Bài 11 — Sensitivity

Nếu read traffic ×2, retention 24→36 tháng và thêm AZ, phân tích yếu tố nào có thể đổi thứ hạng phương án.

### Bài 12 — ADR

Viết ADR-001 theo mẫu: context, candidates, evidence, hard gates, decision, rejected alternatives, tradeoffs, risk owners, revisit triggers.

### Bài 13 — Sơ đồ context

Vẽ clients, gateway, Java API, identity provider, authoritative database, cache, broker và payment provider; đánh dấu trust boundary.

### Bài 14 — Sơ đồ transaction

Vẽ sequence ReserveSlot với conditional claim, receipt và outbox; chỉ rõ đâu là atomic commit boundary thực.

### Bài 15 — Mất ACK

Vẽ retry sequence sau commit nhưng response mất. Giải thích tại sao client không được dùng commandId mới.

### Bài 16 — Tenant isolation

Một mobile client gán `tenantId=T2` trong body dù token thuộc T1. Sơ đồ và runbook cần có guard nào?

### Bài 17 — Cache

Cache không thấy booking. Có được trả “slot còn trống” và reserve trực tiếp từ cache không? Đề xuất source-of-truth path.

### Bài 18 — Read projection

Thiết kế path list bookings eventual, nêu staleness contract và reindex/rebuild path.

### Bài 19 — TTL và tombstone

Receipt TTL hết sớm hơn delayed retry. Làm sao vẫn chặn duplicate business effect và chống event cũ hồi sinh record?

### Bài 20 — Deployment topology

Vẽ ba zones, API replicas, DB data replicas, backup và on-call. Ghi chính xác failure domains, không suy quorum chỉ từ số hộp.

### Bài 21 — Backup

Từ timeline 10:00 failure, 09:58 recovery point, 10:31 service restored, tính RPO/RTO và nêu thành phần nào phải kiểm.

### Bài 22 — Runbook template

Viết RB-UNKNOWN-COMMIT có trigger, preconditions, steps, stop criteria, verification, owner và evidence.

### Bài 23 — Read latency

Get p99 tăng gấp năm khi index build. Runbook cần đo node/shard/tenant, CPU/IO/network và hành động dừng an toàn nào?

### Bài 24 — Double booking incident

Hai active reservations cùng room/slot đã được ACK. Nêu các bước cô lập, đối soát, giao tiếp và bồi hoàn có audit.

### Bài 25 — Failover

Primary mất khi commit. Phân biệt ACKed, unacknowledged và unknown outcomes; cách kiểm receipt, replicas và route fencing.

### Bài 26 — Restore drill

Khôi phục 100 triệu documents từ backup, rebuild indexes, restart CDC và Booking API. Định nghĩa mốc RTO đúng.

### Bài 27 — CDC backlog

Consumer apply chậm hơn source 10.000 events/s trong 30 phút. Tính backlog tăng và điều kiện dừng index build.

### Bài 28 — Scale/rebalance

Thêm hai nodes giữa peak traffic. Ghi các metrics/stop criteria bảo vệ p99, disk headroom, quorum, replication và tenant hotspots.

### Bài 29 — Multi-region

Hai regions nhận booking cùng room/slot trong network partition. Vì sao LWW không bảo vệ invariant? Đề xuất một authority rõ.

### Bài 30 — License và service terms

So Community self-managed và managed tier, cần những bằng chứng nào cho quyền sử dụng, backups, residency và support?

### Bài 31 — Java port

Định nghĩa `ReservationAuthority` có outcome COMMITTED/UNAVAILABLE/KEY_CONFLICT/PENDING, tách vendor adapter khỏi domain.

### Bài 32 — JUnit hard gate

Viết test cho `CandidateAssessment` loại ứng viên có RTO fail hoặc residency UNKNOWN dù p99 rất tốt.

### Bài 33 — Missing evidence

Sửa decision tool để một requirement bị thiếu hẳn trong list gates vẫn chặn approval, không chỉ những `UNKNOWN` đã có record.

### Bài 34 — Operational handoff

Tạo ma trận on-call: backend, SRE, security, finance, vendor support và incident commander; ai phê duyệt thao tác nào?

### Bài 35 — Revisit triggers

Ứng dụng tăng 4× data, chuyển từ một region sang hai và thêm CDC consumer. Những ADR/sơ đồ/runbook/test nào phải cập nhật?

### Bài 36 — Incident drill

Diễn tập restore bằng production-shaped synthetic data, có operator giả lập mất index, stale CDC token và một unknown payment charge.

### Bài 37 — Release gate

Thiết kế canary 1% →10% →50% →100% với p99, error, tenant leak, duplicate booking và rollback/roll-forward conditions; không tự chuyển tiếp nếu gate thiếu số liệu.

### Bài 38 — Final deliverables

Bàn giao một thư mục kiến trúc giả định gồm ADR-001, D01–D07, RB-READ/RB-WRITE/RB-FAILOVER/RB-RESTORE/RB-CDC, evidence manifest, budget forecast và risk register. Mỗi tài liệu phải trỏ tới cùng requirement IDs.

### Bài 39 — Đánh giá lại

Giả sử B sau tạo projection có list p99=190 ms nhưng CDC lag 12 phút trong peak. Hãy đánh giá lại R05 và consistency requirements, không chỉ đổi ô `FAIL` thành `PASS`.

### Bài 40 — Phân tích giới hạn

Viết đoạn “Known limits of evidence” nêu những gì POC một region, 50 triệu records, 100 concurrent writers và một restore drill **chưa** chứng minh.

---

## 51. Checklist cuối: ba tài liệu phải đồng thuận

| Câu hỏi đối soát | ADR | Sơ đồ | Runbook |
|---|---|---|---|
| Nguồn có thẩm quyền ở đâu? | Nêu lựa chọn | Chỉ hộp/commit scope | Đọc/restore từ authority |
| Bảo vệ double booking thế nào? | R01 + test | Conditional/transaction path | RB-WRITE-CONFLICT |
| Retry mất ACK xử lý ra sao? | R02 + test | Receipt sequence | RB-UNKNOWN-COMMIT |
| List query có stale không? | R05 + agreement | Projection/CDC path | RB-CDC |
| Failover bảo đảm gì? | R07 + failure model | Replica/fencing domains | RB-FAILOVER |
| Backup và RTO? | T-DR evidence | Backup/restore flow | RB-RESTORE |
| Tenant isolation và residency? | Hard gates | Trust/region boundaries | RB-SECURITY |
| Index và rebalance? | Performance consequences | Placement/query indexes | RB-INDEX/RB-CAPACITY |
| Bill và growth risk? | 36-month TCO | Data flow/cost meters | RB-COST |
| Khi nào quyết định hết hiệu lực? | Revisit triggers | Diagram revision | Runbook review |

### 51.1. Nếu ADR nói “transactional” nhưng sơ đồ có hai independent writes

Chưa đồng thuận. Phải sửa kiến trúc hoặc quyết định, không chỉ đổi nhãn trong sơ đồ.

### 51.2. Nếu runbook restore dựa backup chưa xuất hiện trên sơ đồ

Chưa đồng thuận. Bổ sung backup region/key/restore path và thí nghiệm RPO/RTO.

### 51.3. Nếu test cho thấy projection lag vượt hợp đồng

Chưa được kết luận R05 đạt chỉ vì p99 list query thấp. Cần cải thiện event pipeline/contract và re-test.

### 51.4. Nếu license hoặc tier chưa được xác minh

Quyết định vẫn conditional/unknown dù kỹ thuật tốt. Legal/service terms là hard gate độc lập.

## 52. Tổng kết bài thực hành

Việc **hoàn thiện quyết định lựa chọn, sơ đồ và sổ tay vận hành bằng kết quả thực nghiệm** có thể xem như một vòng khép kín:

~~~text
Business requirements and invariants
    -> Measurable gates and experimental design
    -> Raw evidence, results, confidence and limitations
    -> Conditional/approved architectural decision (ADR)
    -> Accurate context/data/deployment/transaction diagrams
    -> Runnable and safe operations/incident/DR runbooks
    -> Monitoring, canaries and periodic revalidation
    -> New evidence when workload or technology changes
~~~

Trong tình huống minh họa, **phương án A được đề xuất có điều kiện**, không phải vì “managed luôn tốt hơn” mà vì các kết quả giả lập cho thấy nó đạt tập gates đã đo trong thiết kế đang xét, trong khi B cần cải thiện list queries và C chưa đạt restore RTO. Quyết định chỉ trở thành phê duyệt production khi những hard gates còn lại về license, residency, support, ngân sách và môi trường thật có bằng chứng phù hợp.

**Bài học cốt lõi:** Đừng chọn NoSQL chỉ bằng tên sản phẩm, một benchmark hay điểm tổng. Hãy chọn **một kiến trúc có thể chứng minh bất biến, hiệu năng, bảo mật, khả năng phục hồi và chi phí trong workload thật**, rồi vẽ đúng kiến trúc đó và viết runbook cho những sự cố mà phép thử đã chỉ ra. Khi ADR, sơ đồ và runbook cùng truy vết tới một bộ bằng chứng, quyết định không còn là ý kiến nhất thời: nó trở thành **hợp đồng kỹ thuật có thể kiểm chứng, vận hành và đánh giá lại**.
