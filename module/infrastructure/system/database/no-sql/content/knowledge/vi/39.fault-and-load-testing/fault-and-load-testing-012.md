# Kiểm chứng backup/restore và thời gian thực tế để phục hồi dịch vụ

## 1. Tình huống: backup báo thành công, khách hàng vẫn không đặt hàng được

Một hệ thống thương mại dùng MongoDB cho đơn hàng, Redis cho idempotency, Kafka cho outbox/CDC và Elasticsearch cho tìm kiếm. Dashboard hiển thị:

~~~text
Last backup job: SUCCESS
Last snapshot:   00:00 UTC
Backup size:     2.4 TiB
~~~

Đến 10:00, một thao tác sai xóa phần lớn đơn hàng. Đội vận hành khôi phục bản snapshot trong 90 phút và ghi sự cố đã “resolved”. Nhưng ứng dụng vẫn không thể hoạt động bình thường vì:

- Khóa KMS tại recovery account chưa được cấp quyền giải mã.
- Collection đã khôi phục nhưng index chưa xây xong; p99 của API cao hơn SLO.
- Một consumer giữ checkpoint Kafka mới hơn dữ liệu nguồn được restore nên bỏ qua sự kiện cần phát lại.
- Payment provider đã thu tiền của một số đơn sau mốc snapshot; những đơn đó chưa được đối soát.
- Một số yêu cầu xóa dữ liệu cá nhân xảy ra sau snapshot chưa được áp lại.
- Redis đã mất idempotency keys; retry có nguy cơ tạo tác vụ trùng.
- Đội ứng dụng phải đổi DNS, kiểm tra TLS và chờ connection pools ổn định mới nhận traffic.

**Backup thành công không chứng minh restore thành công; restore dữ liệu thành công cũng không chứng minh dịch vụ đã phục hồi.** Muốn kiểm chứng được khả năng khôi phục, phải **thực hiện diễn tập**, đo các mốc thời gian, đối chiếu dữ liệu và xác minh ứng dụng hoạt động ở mức cam kết.

Bài này thuộc module **Database No SQL**, chương **Kiểm thử lỗi và tải**, với chủ đề **“Kiểm chứng backup/restore và thời gian thực tế để phục hồi dịch vụ”**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt bản backup tồn tại, backup hợp lệ, có thể restore và dịch vụ phục hồi thực sự.
2. Diễn giải **Recovery Point Objective (RPO)**, **Recovery Time Objective (RTO)** cùng giá trị đo thực tế.
3. Chọn failure scenario và phạm vi dịch vụ cụ thể cho mỗi restore drill.
4. Kiểm tra backup chain gồm snapshot, incremental changes, WAL/oplog/change logs và metadata.
5. Xác nhận điểm phục hồi nhất quán khi dữ liệu trải qua shards, replicas và nhiều hệ thống.
6. Tính toán bottleneck về kích thước backup, băng thông, IOPS, replay, index build và warm-up.
7. Đo RTO từ đúng mốc sự cố đến đúng mốc ứng dụng đáp ứng điều kiện phục vụ.
8. Kiểm chính xác dữ liệu, invariants nghiệp vụ, idempotency, deletes, permissions và CDC sau restore.
9. Thiết kế diễn tập phù hợp MongoDB, Cassandra, DynamoDB, Redis, Elasticsearch/OpenSearch và Couchbase.
10. Tổ chức synthetic workload, fault injection, runtime metrics, go/no-go gates và báo cáo bằng chứng.
11. Viết mã Java/JUnit 5 cho kiểm tra dữ liệu sau restore và đo timeline.
12. Lập runbook đủ để người không trực tiếp tạo backup vẫn có thể khôi phục dưới sự giám sát phù hợp.

---

## 2. Bốn mức chứng cứ về backup

| Mức | Bằng chứng | Điều **chưa** chứng minh |
|---|---|---|
| **B1 — Job completed** | Scheduler báo `SUCCESS` | Tất cả artifacts có thể đọc/giải mã |
| **B2 — Artifacts verified** | Checksums, manifest, lineage, keys và log chain hợp lệ | Engine thực sự restore được và data đúng |
| **B3 — Restore verified** | Phục hồi vào môi trường cách ly và kiểm dữ liệu/schema | Ứng dụng phục vụ trong thời gian mục tiêu |
| **B4 — Service recovered** | API thực hiện read/write an toàn, dependency đúng, p99/goodput đạt SLO | Mọi failure scenario chưa được diễn tập |

Một quy trình chỉ có B1 không nên báo cáo “RTO tested”. Tốt hơn, bản báo cáo phải ghi từng lớp đã có bằng chứng và phần còn lại đang chờ kiểm chứng.

### 2.1. B1 chỉ là tín hiệu của job

Job có thể đã tạo file nhưng thiếu một shard, copy tới nơi cùng failure domain hoặc không giữ được encryption key. Một job hoàn tất không chứng minh tất cả dependency tồn tại.

### 2.2. B2 là kiểm vật lý và chuỗi khôi phục

Các phép kiểm như checksum và manifest giúp nhận diện file hỏng hoặc thiếu segment. Chúng không phát hiện một snapshot chứa lỗi logic do ứng dụng ghi sai trước thời điểm backup.

### 2.3. B3 cần dùng công cụ restore thật

Thực hiện restore trên version/config mục tiêu, mở database, đọc dữ liệu, kiểm metadata và business invariants. Không chỉ thử giải nén file.

### 2.4. B4 bắt buộc đo ở tầng dịch vụ

Ứng dụng phải có thể xử lý một tập operation classes đã định nghĩa, ví dụ `GetOrder`, `CreateOrder`, `ReserveStock`, `RevokeAccess`. Chỉ thấy node `UP` hoặc TCP port mở chưa đủ.

---

## 3. Hai chỉ số quan trọng: RPO và RTO

### 3.1. RPO — dữ liệu có thể bị lùi bao xa?

RPO là mục tiêu về **độ lùi điểm dữ liệu có thể phục hồi** khi xảy ra một loại sự cố.

~~~text
09:57:00  Latest verified recoverable commit position
10:00:00  Failure begins
10:30:00  Restored cluster opens
~~~

Nếu khôi phục được trạng thái đã commit đến 09:57:00, **recovery-point gap** so với sự cố 10:00 là 3 phút. Mốc 10:30 là thời gian mở cluster, **không phải recovery point**.

### 3.2. RTO — mất bao lâu tới mức phục vụ được cam kết?

RTO là mục tiêu thời gian tối đa từ **mốc khởi đầu đã thỏa thuận** đến khi dịch vụ đáp ứng **định nghĩa phục hồi**.

~~~text
10:00  Failure starts
10:04  Alert fires
10:15  Operator chooses recovery plan
10:35  DR environment provisioned
11:20  Data restored
11:42  Log replay completed
12:00  Business invariants verified
12:12  Cutover
12:25  API p99/goodput stable and writes safe
~~~

Với định nghĩa phục hồi là “API đọc/ghi quan trọng an toàn và ổn định”, RTO đo được là **2 giờ 25 phút**, không phải 1 giờ 20 phút (khi công cụ restore dừng).

### 3.3. Phân biệt mục tiêu và giá trị thực tế

- `targetRpo`: khoảng mất dữ liệu tối đa được business chấp nhận.
- `verifiedRecoverablePoint`: mốc/position mới nhất có thể restore trong failure scenario.
- `actualRecoveryGap`: độ lùi so với mốc sự cố.
- `targetRto`: thời gian phục hồi cam kết theo phạm vi.
- `actualRto`: thời gian đo từ fault start đến service-recovered gate.
- `observedBusinessLoss`: những transactions/side effects bị thiếu hoặc cần đối soát.

### 3.4. Không hứa RPO=0 chỉ vì có replica

Replicas có thể bất đồng bộ, và lỗi logic có thể được truyền tới tất cả replicas. Phải xét ACK/durability/replication policy và failure domain.

### 3.5. RTO có thể tách theo chức năng

Ví dụ mục tiêu minh họa:

| Chức năng | Recovery gate | RTO mục tiêu |
|---|---|---:|
| Xem đơn hàng | Point reads đúng và có authorization | 30 phút |
| Tạo đơn mới | Writes được commit an toàn và payment reconciliation | 60 phút |
| Tìm kiếm | Search index đạt coverage và freshness | 4 giờ |
| Analytics lịch sử | Báo cáo đúng, backfill hoàn tất | 24 giờ |

Không dùng một status “cluster healthy” để tuyên bố cả bốn gate đã đạt.

---

## 4. Mỗi diễn tập phải có một failure scenario rõ ràng

Các tình huống khác nhau dẫn tới quy trình và RPO/RTO khác nhau:

| Sự cố | Nguy cơ | Đường khôi phục điển hình |
|---|---|---|
| Một process chết | Connection gián đoạn | Restart/HA failover, thường không cần restore |
| Mất disk của một replica | Replica thiếu dữ liệu | Rebuild/reseed từ peers/backup |
| Mất nhiều replicas | Không đủ quorum/availability | Khôi phục copy hoặc seed mới |
| Mất Availability Zone | Một failure domain hạ tầng mất | Multi-AZ failover/capacity |
| Mất cả region | Source và nhiều backups nội vùng mất | Offsite/DR region restore hoặc failover |
| Xóa nhầm collection | Deletes lan tới replicas | PITR trước thao tác + reconcile |
| App ghi sai dữ liệu | Corruption hợp lệ về mặt schema | Tìm điểm sạch, restore một phần, replay an toàn |
| Ransomware/account bị chiếm | Source và backup có nguy cơ bị xóa | Immutable/offline copies, credentials độc lập |
| KMS key không còn | Không giải mã backup | Key recovery/custody và DR access |
| Restore từ snapshot cũ | Data đã xóa/revoke có thể hồi sinh | Deletion/revocation reconciliation |

**Không thực hiện network partition, wipe volumes, region failover hoặc key destruction trên production chỉ để diễn tập**. Dùng staging/DR cách ly hoặc chương trình chaos đã được phê duyệt.

### 4.1. Đo đúng failure domain

Một bản backup ở cùng AZ có thể vẫn tồn tại khi process crash, nhưng không giúp nếu toàn AZ bị hỏng. Bài test phải giả lập sự mất mát của **nguồn mà kế hoạch cần sống sót**, không vô tình sử dụng bản backup nằm trong vùng giả định đã mất.

### 4.2. Một bài test không chứng minh toàn bộ bảng

Diễn tập restore table từ snapshot không tự kiểm region outage hoặc compromised IAM. Ghi rõ scope và `NOT_COVERED` cho phần chưa thử.

---

## 5. Xác định phục hồi thành công ở mức nghiệp vụ

Một `Service Recovery Contract` nên ghi:

~~~yaml
recoveryContract:
  service: orders
  scenario: full-primary-region-loss
  businessOwner: order-domain
  technicalOwner: data-platform
  clockStart: incident-failure-start
  clockStop: critical-operations-stable
  rpoObjective: PT5M
  rtoObjective: PT1H
  criticalOperations:
    - GetOrder
    - CreateOrder
    - CancelOrder
  correctnessGates:
    - no-cross-tenant-access
    - no-double-charge
    - no-unreviewed-missing-acknowledged-order
    - deleted-or-revoked-data-reconciled
  performanceGates:
    - p99-within-approved-slo
    - error-rate-within-approved-slo
    - sufficient-throughput
  evidence:
    - backup-manifest
    - verified-checkpoint
    - restore-event-timeline
    - reconciliation-report
    - application-canary
~~~

Đây là mẫu **minh họa**. Các giá trị phải do owner phê duyệt; không có một RPO/RTO chuẩn cho mọi NoSQL hoặc mọi công ty.

### 5.1. `GetOrder` pass chưa bảo đảm `CreateOrder` pass

Một replica hoặc restored database có thể đọc được nhưng không có primary/quorum để ghi. Cần operation-level canaries.

### 5.2. “Ổn định” phải có ngưỡng

Ví dụ cần 5 phút liên tiếp đạt error rate/p99/throughput trong synthetic workload có tỷ lệ đủ đại diện, thay vì một request thành công đơn lẻ.

### 5.3. Khôi phục một phần

Có thể tuyên bố `PARTIAL_RECOVERY` nếu point reads hoạt động nhưng payment/new orders chưa an toàn; không ghi `FULL_RECOVERY` khi chỉ có một feature lên.

---

## 6. Dữ liệu nào phải đi cùng nhau khi restore?

Một hệ thường chứa:

~~~mermaid
flowchart TD
    API["Java Order API"] --> ORD["Authoritative Orders NoSQL"]
    API --> INV["Inventory ledger"]
    API --> REDIS["Redis: session/idempotency"]
    ORD --> OUTBOX["Outbox / CDC"]
    OUTBOX --> KAFKA["Event broker"]
    KAFKA --> SEARCH["Search projection"]
    KAFKA --> ANALYTICS["Analytics"]
    API --> PAY["Payment provider"]
    ORD --> OBJ["Invoice objects"]
    KMS["KMS / IAM / TLS"] -.-> ORD
    SCHEMA["Schemas / index definitions / IaC"] -.-> ORD
~~~

Nếu chỉ phục hồi `ORD` mà bỏ lại Kafka offsets ở tương lai, downstream có thể tưởng đã xử lý events không còn tồn tại trong Orders sau restore. Nếu chỉ phục hồi database mà mất KMS keys, dữ liệu mã hóa có thể không đọc được.

### 6.1. Lập Recovery Dependency Inventory

Mỗi thành phần cần ghi:

- Asset ID, owner, system of record.
- Regions/AZ/failure domains.
- Backup method và retention.
- Khóa mã hóa, quyền restore và secret references.
- Schema/index/driver version.
- Snapshot/log positions.
- Upstream/downstream connectors.
- Read/write consistency contract.
- Dữ liệu dẫn xuất có thể rebuild từ đâu.
- Reconciliation oracle.
- Phạm vi RPO/RTO của chính asset.

### 6.2. Cache có thể quan trọng hơn tên gọi

Redis chứa derived product cache khác Redis chứa **duy nhất** idempotency ledger hoặc pending jobs. Với dữ liệu mang business effect, không được tùy tiện đánh dấu disposable.

### 6.3. External systems không nằm trong backup DB

Payment capture, email đã gửi hoặc shipping request không tự rollback khi NoSQL restore về quá khứ. Phải có bước đối soát.

---

## 7. Các thành phần của một recovery chain

Một hệ có thể sử dụng:

~~~text
Full snapshot S0 (position 1000)
   +
Incremental I1 (1001..1500)
   +
Incremental I2 (1501..1900)
   +
Archived WAL/oplog/change records (1901..1950)
   =
Recoverable state through position 1950
~~~

### 7.1. Bản baseline

Phải có một snapshot/backup hợp lệ, bao gồm đúng phạm vi source (collection/table/shards) và đủ metadata.

### 7.2. Các đoạn incremental

Từng segment cần đúng lineage, thứ tự và checksum; không được thiếu đoạn giữa rồi vẫn tuyên bố phục hồi đến đoạn cuối.

### 7.3. Continuous logs hoặc PITR

Muốn dừng tại một mốc rất gần sự cố, phải có nguồn log/replay được engine hoặc công cụ hỗ trợ với retention và consistency phù hợp.

### 7.4. Snapshot position khác job completion time

Snapshot có thể bắt đầu lúc 02:00, kết thúc upload lúc 02:14 nhưng logical checkpoint là 02:00 hoặc một position cụ thể. Không tự coi recovery point là 02:14.

### 7.5. Điểm phục hồi phải sống sót failure domain

Một snapshot mới trên disk đã mất không tính là recoverable point của disk-loss test. Mốc cần lấy từ bản **thực sự còn truy cập được** trong bối cảnh lỗi.

### 7.6. Test chain cần cố ý thiếu một segment

Trong môi trường test cách ly, mô phỏng thiếu incremental segment để chắc rằng restore **fail closed** thay vì âm thầm bỏ qua records.

---

## 8. Các phép kiểm trước khi bắt đầu restore

Kiểm kê và xác minh:

1. Backup job metadata.
2. Artifact path/size/checksum.
3. Snapshot/base/incremental dependency graph.
4. Database/schema version compatibility.
5. Dữ liệu từ mọi shard/range cần thiết.
6. Snapshot/replay consistency scope.
7. Object storage permissions.
8. KMS keys và quyền decrypt ở recovery environment.
9. Retention và legal hold.
10. Backup repository không nằm trong failure domain giả lập đã mất.
11. Restore tool version và manifest schema.
12. Recovery target checkpoint/time hợp lệ.
13. Log continuity không có gaps.
14. Recovery destination có đủ disk, CPU, RAM, network.
15. Quyền restore không cho phép phá source production.
16. Restore runbook có operator/approver.

Nếu không biết một điều thiết yếu, ghi `UNKNOWN`/`BLOCKER`. Không xem field trống là PASS.

---

## 9. Snapshot nhất quán: vấn đề khó của NoSQL phân tán

Ví dụ:

~~~text
Shard A snapshot at 09:59:58
Shard B snapshot at 10:00:04
Shard C snapshot at 09:59:52

Order transfer crosses shards A and B at 10:00:01
~~~

Một bản snapshot ở ba thời điểm khác nhau có thể chứa một nửa của workflow, khiến sau restore lệnh chuyển tài nguyên không còn bảo toàn tổng.

### 9.1. Local crash-consistent khác cluster-consistent

Một snapshot volume có thể phù hợp cho crash recovery của **một node**. Nó chưa chứng minh consistency trên nhiều nodes/shards hay với external event systems.

### 9.2. Phải xác định logical cut

Lựa chọn phụ thuộc engine/công cụ:

- Engine-supported cluster backup/PITR.
- Consistent snapshots được điều phối.
- Base snapshot + log positions cho từng shard.
- Temporarily coordinated writes/quiesce nếu kiến trúc cho phép.
- Event ledger có thể reconcile khi không có global snapshot.

### 9.3. UTC timestamp không tự tạo transaction toàn cục

Đồng hồ các nodes có thể lệch. Hai snapshots “cùng phút” chưa bảo đảm tất cả causal dependencies được bao phủ.

### 9.4. Khi không thể có một cut nhất quán

Phải ghi rõ consistency gap, thiết kế reconciliation và chứng minh business invariants sau khôi phục.

---

## 10. Khôi phục dữ liệu không được bỏ sót delete và revocation

Một người dùng yêu cầu xóa thông tin lúc 10:15. Snapshot lúc 10:00 vẫn chứa record đó. Nếu sau region loss phục hồi snapshot 10:00 rồi mở API, dữ liệu đã xóa có thể xuất hiện lại.

### 10.1. Test deletion replay

Tạo synthetic record, snapshot, thực hiện delete hợp lệ, restore snapshot và áp deletion ledger/event theo policy. Kiểm mọi read paths có thể trả bản ghi đó.

### 10.2. Revoked permissions

Khôi phục credential/permission cũ có thể cấp lại quyền mà admin đã thu hồi. Đây là kiểm thử safety, không chỉ đếm records.

### 10.3. Tombstone và TTL

MongoDB TTL, Cassandra tombstones, DynamoDB TTL, Redis expiry và search deletion có cơ chế khác nhau. Bản restore phải tuân thủ expiration/deletion policy thực tế; physical deletion có thể bất đồng bộ.

### 10.4. Không phải lúc nào cũng replay mọi event

Nếu restore đến một mốc trước lỗi logic rồi replay cả delete nhầm, lỗi xuất hiện lại. Cần phân biệt **legitimate deletes/updates** với **corrupting operations** và phê duyệt bộ lọc/reconciliation.

### 10.5. Retention và pháp lý

Recovery phải phù hợp data residency, retention, deletion requirements và legal hold của từng asset. Không copy raw PII tới staging ngoài phạm vi được cho phép.

---

## 11. Data correctness gates sau restore

Một cơ sở dữ liệu mở được nhưng dữ liệu sai vẫn là phục hồi thất bại.

| Oracle | Ví dụ |
|---|---|
| **Record coverage** | Đếm logical IDs theo tenant/range/cohort |
| **Integrity** | Checksum/canonical hashes, không thiếu segment |
| **Schema** | Field types, validation, indexes và constraints |
| **Business invariant** | Không oversell, không negative balance |
| **Uniqueness** | Không trùng active identifiers |
| **State transitions** | Không có order status đi lùi trái policy |
| **Idempotency** | Retry không double-charge/duplicate order |
| **Security** | Tenant A không đọc được dữ liệu B |
| **Deletion** | Đã xóa/revoke không bị hồi sinh |
| **External reconciliation** | DB charges khớp payment provider |
| **CDC/outbox** | Không bỏ qua events và không nhân side effects |
| **Freshness** | Restored projection đạt checkpoint/lag contract |

### 11.1. Count bằng nhau chưa đủ

Hai tập đều có 1 triệu records nhưng khác 10.000 IDs vẫn có cùng count. Cần so identity và payload theo canonical representation.

### 11.2. Checksum raw bytes có thể vô nghĩa

Dữ liệu BSON/JSON/column formats khác nhau hoặc field order khác có thể dẫn đến byte hashes khác dù logical values đúng. Định nghĩa canonical data schema, currency precision, timestamp và null semantics.

### 11.3. Đọc ở consistency phù hợp

Một read từ replica stale có thể làm oracle báo sai. Lấy data từ authoritative source hoặc consistent snapshot/watermark theo engine.

### 11.4. Kiểm cả history, không chỉ state cuối

Nếu hai customers đã nhận cùng một vé rồi hệ sau đó compensation, snapshot cuối có thể “đẹp”. Cần đối chiếu successful receipts và audit history.

---

## 12. Unknown write outcome sau sự cố

Một request tạo đơn:

~~~text
Client sends CreateOrder(requestId=R42)
Database commits
Server crashes before ACK reaches Java client
Client sees timeout
~~~

Sau restore hoặc failover, client phải xác định liệu operation `R42` đã commit hay chưa. Retry với ID mới có thể tạo đơn trùng.

### 12.1. Stable operation ID

Idempotency key/request ID nên gắn với business operation, payload hash và authority đủ bền.

### 12.2. Verify từ nguồn độc lập

Đối soát record, request ledger và external provider receipts nếu tác vụ có side effect.

### 12.3. Không suy timeout là reject

Kết quả phải có thể biểu diễn `SUCCESS`, `DEFINITELY_REJECTED`, `UNKNOWN`.

### 12.4. Restore có thể làm mất ledger cũ

Nếu source restored tới mốc cũ hơn payment charge, idempotency ledger cần được rebuild/reconcile trước khi cho phép retry tiền thật.

---

## 13. RTO tính từ mốc nào đến mốc nào?

Chọn mốc **trước diễn tập**, không đổi sau khi thấy kết quả.

Một timeline gợi ý:

~~~mermaid
flowchart LR
    F["T0: Fault starts"] --> D["Detect"]
    D --> T["Triage / decision"]
    T --> P["Provision DR"]
    P --> R["Restore + replay"]
    R --> V["Validate data"]
    V --> C["Cutover / refresh clients"]
    C --> S["T1: Service SLO stable"]
~~~

### 13.1. Các mốc cần thu

- `failureStartedAt`.
- `failureDetectedAt`.
- `incidentDeclaredAt`.
- `recoveryDecisionAt`.
- `drProvisionedAt`.
- `backupAccessReadyAt`.
- `restoreStartedAt`.
- `restoreCompletedAt`.
- `replayCompletedAt`.
- `dataVerifiedAt`.
- `applicationCanaryPassedAt`.
- `trafficCutoverAt`.
- `serviceStableAt`.

### 13.2. Đo RTO business

\[
RTO_{\text{actual}} = T_{\text{serviceStable}}-T_{\text{failureStarted}}.
\]

Đây là cách đo khi hợp đồng định nghĩa start/stop như vậy. Nếu SLA chọn một điểm khởi đầu khác, phải công bố rõ; không thay cách tính âm thầm.

### 13.3. Recovery time và incident resolution khác nhau

Một số batch analytics có thể tiếp tục backfill sau khi critical API mở. Ghi `critical-service-restored` và `full-system-recovered` thành hai mốc.

### 13.4. Đừng trừ thời gian “chờ phê duyệt”

Nếu thời gian phê duyệt nằm giữa failure và service recovery, nó góp phần vào RTO theo contract. Runbook tốt phải giảm thời gian này bằng chuẩn bị trước.

---

## 14. Công thức critical path và performance budget

Một mô hình đơn giản:

\[
T_{\text{total}} \approx
T_{\text{detect}}+
T_{\text{triage}}+
T_{\text{provision}}+
T_{\text{transfer}}+
T_{\text{restore}}+
T_{\text{replay}}+
T_{\text{validate}}+
T_{\text{cutover}}+
T_{\text{warmup}}.
\]

Trong thực tế, một số bước có thể song song. Khi đó phải đo **critical path** và thời điểm bắt đầu/kết thúc thật, không cộng trùng.

### 14.1. Lập budget theo giai đoạn

| Giai đoạn | Budget minh họa |
|---|---:|
| Detection + incident declaration | 5 phút |
| Triage + approve recovery point | 10 phút |
| Provisioning/keys/network | 15 phút |
| Transfer + restore | 45 phút |
| Replay + indexes | 20 phút |
| Business validation | 15 phút |
| Cutover + warm-up | 10 phút |
| **Tổng tuần tự** | **120 phút** |

Nếu target RTO là 90 phút, thiết kế này **không khả thi theo mô hình tuần tự**; cần song song hóa, warm standby hoặc giải pháp khác trước khi sự cố xảy ra.

### 14.2. Đừng cắt validation để làm RTO đẹp

Một restored cluster phục vụ wrong-tenant data trong 30 giây không nên được coi là thành công chỉ vì đáp ứng target duration.

### 14.3. Đo lặp nhiều lần

Một drill tốt nhất 45 phút không chứng minh mọi DR drill sẽ dưới 60 phút. Báo cáo phân phối thực tế, max, p50/p95 khi có đủ samples và lý do variance.

---

## 15. Tính băng thông restore theo kích thước dữ liệu

Giả sử backup cần truyền \(S\) TiB, tốc độ truyền hữu hiệu \(B\) MiB/s:

\[
T_{\text{transfer}}(\text{seconds})
=
\frac{S\times1024\times1024}{B}.
\]

Với \(S=2\) TiB và \(B=400\) MiB/s:

\[
T \approx 5243\text{ giây}\approx87.4\text{ phút}.
\]

**Riêng việc tải backup đã vượt RTO 60 phút**, chưa tính decompression, disk writes, index builds, log replay, validation và cutover.

### 15.1. Effective throughput khác danh nghĩa

Một đường mạng 10 Gbps không có nghĩa backup restore đạt tốc độ tương ứng; còn object-storage limits, encryption, CPU, destination IOPS và parallelism.

### 15.2. Dữ liệu nén

Backup bytes ít hơn không nhất thiết restore nhanh hơn nếu giải nén CPU-bound hoặc tạo nhiều random writes.

### 15.3. Incremental restore

Một chuỗi dài incremental segments có thể tăng thời gian apply và số lần mở file dù tổng bytes nhỏ.

### 15.4. Search/index reconstruction

Sau restore dữ liệu, build indexes/compaction có thể là bottleneck lớn nhất; phải đo.

### 15.5. Throughput khi tải production traffic

Một lần restore trên cluster không nhận khách có thể nhanh hơn khi hệ còn chạy vừa phục vụ queries vừa reindex/replay. Với hot recovery, cần đo contention.

---

## 16. Tăng kích thước test để đo RTO đáng tin

Một bài restore 1 GiB trong 20 giây không thể ngoại suy tuyến tính đơn giản ra 10 TiB.

### 16.1. Chọn dataset đại diện

Cần:

- Logical data size và physical backup bytes.
- Number of documents/items/partitions.
- Size p50/p95/p99/max.
- Hot key/tenant distributions.
- Secondary indexes.
- TTL/deleted records/tombstones.
- Historical schema cohorts.
- Change-log volume.
- Compression ratio.
- Replication/shard layout.

### 16.2. Phân tầng test

- **Smoke:** vài MB/GB để bắt lỗi tool/credentials/schema.
- **Representative:** kích thước và phân phối phản ánh workload thật.
- **Scale/soak:** near-production size, log backlog và peak write rates.
- **Disaster rehearsal:** failure domain và DR topology được mô phỏng đúng.

### 16.3. Không đưa PII production vào staging tùy tiện

Dùng synthetic data có thống kê gần thật hoặc data được masking theo chính sách. Key space, histogram và mutation patterns có thể đại diện mà không phơi lộ nội dung nhạy cảm.

---

## 17. Thời gian bắt kịp các writes phát sinh trong lúc restore

Nếu source vẫn nhận writes trong lúc backfill/copy, target phải theo kịp **change rate**.

Giả sử:

- Historical restore/backfill còn lại 2 giờ.
- Source phát sinh 10.000 mutations/s.
- CDC/replay xử lý 12.000 mutations/s.

Nếu backlog đã lên 72 triệu events, công suất bắt kịp thuần chỉ 2.000 events/s và thời gian xóa backlog lý tưởng là 10 giờ, **chưa tính events đến thêm và variability**.

### 17.1. Công thức backlog

Khi arrival rate \(\lambda\) và replay capacity \(\mu\) ổn định, với \(\mu > \lambda\):

\[
T_{\text{catchup}}\approx\frac{Backlog}{\mu-\lambda}.
\]

Nếu \(\mu\le\lambda\), backlog không giảm trong mô hình ổn định.

### 17.2. Tránh chạy bù không kiểm soát

CDC replay, index builds, cache warm-up và client retries có thể cùng tranh disk/CPU/network. Cần admission control và rate limits, không chỉ tăng concurrency vô hạn.

### 17.3. Xem per-partition lag

Một vài hot partitions có thể trễ dù global average ổn. Cutover phải tính worst impacted cohort nếu hợp đồng yêu cầu.

### 17.4. Điểm dừng

Chỉ báo `replay complete` khi watermark/commit position và data oracle đạt, không chỉ khi consumer queue tạm bằng 0.

---

## 18. Cutover là một phần của bài restore

Sau khi database restore xong, ứng dụng còn phải:

1. Kiểm network/DNS/private endpoints.
2. Xác thực TLS certificate/SAN và IAM/RBAC.
3. Cập nhật secret/config/connection strings.
4. Đảm bảo drivers refresh topology.
5. Ngăn split-brain/dual-primary writes.
6. Xác nhận data authority mới và old source isolation.
7. Route traffic thử tới DR.
8. Kiểm p99/goodput/error rate.
9. Kiểm retries, idempotency và CDC consumer offsets.
10. Theo dõi một stability window trước khi dừng RTO clock.

### 18.1. DNS TTL không bằng thời gian client reconnect

Java apps có DNS caching, driver topology caches và connection pools; thay DNS không đảm bảo mọi request lập tức đi đúng cluster.

### 18.2. Failback khác failover

Sau khi DR trở thành nguồn ghi chính, quay lại region cũ có thể yêu cầu reverse replication và reconciled cut. Không coi rollback chỉ là đổi DNS.

### 18.3. Chặn writes không an toàn

Nếu chưa biết nguồn nào authoritative, nên tạm giới hạn writes gây side effects thay vì để cả old và new clusters cùng nhận writes không có conflict protocol.

---

## 19. MongoDB: kiểm chứng backup/restore ở phạm vi nào?

### 19.1. Replica-set failover không thay backup

Một replica set cho high availability; một thao tác `deleteMany` sai có thể propagate đến tất cả members. Diễn tập logical corruption cần PITR hoặc backups lịch sử, không chỉ promote secondary.

### 19.2. Logical backup

`mongodump`/`mongorestore` có thể phù hợp một số mục đích (dev, logical export/restore theo scope). Khi dữ liệu đang ghi, cần phương án nhất quán và log coverage phù hợp. Không coi dump riêng từng collection là snapshot atomic toàn sharded cluster.

### 19.3. Physical/snapshot backup

Storage snapshot/managed backup cần theo protocol engine để có dữ liệu nhất quán, oplog coverage và restore compatibility. Không copy file đang ghi trên live node tùy tiện.

### 19.4. PITR

Khi giải pháp backup hỗ trợ PITR, cần verified base và log sequence; một replica oplog window hữu hạn **không tự bảo đảm** PITR vô hạn hay một mốc bất kỳ.

### 19.5. Sharded cluster

Phải kiểm config metadata, shard topology, routing, indexes, users/roles và consistency point của mọi shards trong scope.

### 19.6. Sau restore

Kiểm `hello`, `rs.status()`/cluster topology bằng quyền test, read/write concerns, secondary lag, transaction/canary, change streams và index build progress. Lệnh `ping` không đủ chứng minh API ready.

### 19.7. Kịch bản kiểm thử

- Restore một collection bị xóa.
- Restore cả replica set/cluster.
- Replay oplog đến trước logical corruption.
- Reconcile writes sau selected restore point.
- Kiểm IDs/versions, transactions, deletion and payment ledgers.
- Chạy representative query load khi indexes còn lạnh.

### 19.8. Phân biệt managed vs self-hosted

Các backup/PITR/restore capabilities phụ thuộc MongoDB deployment và sản phẩm quản lý cụ thể. Ghi version, tool, storage và restore target thay vì suy từ tên “MongoDB” chung.

---

## 20. Cassandra: snapshot, SSTable, commit log và repair

Cassandra lưu dữ liệu theo token ranges và replicas. Snapshot của một node không đủ đại diện mọi dữ liệu nếu node đó không sở hữu đủ ranges.

### 20.1. Kiểm artifact coverage

Xác nhận toàn bộ keyspaces/tables/ranges cần bảo vệ, schema/roles và replication configuration. Mỗi cluster topology có kế hoạch backup/restore khác.

### 20.2. `nodetool snapshot`

Cassandra có snapshot SSTables. Để phục hồi đầy đủ đến một recovery point, phải biết snapshot scope và những writes chưa được bao phủ; incremental backup và commit log archive/PITR yêu cầu quy trình/công cụ phù hợp, không tự hình thành từ tên lệnh snapshot.

### 20.3. Restore không chỉ copy file

Có thể phải dùng engine-supported procedures để chuẩn bị data directories, schema, token placement, startup, streaming, compaction, repair hoặc rebuild theo version. Không tùy tiện copy SSTables từ node bất kỳ sang một node khác rồi start.

### 20.4. Tombstones và dữ liệu hồi sinh

Một replica cũ hoặc restored snapshot có thể thiếu tombstone/delete history. Cần kiểm repair horizon và xóa đã commit, tránh zombie data.

### 20.5. Consistency requirement

Một node `UN` không chứng minh queries theo `LOCAL_QUORUM` đều phục vụ được; cần đủ replicas/availability theo từng partition và DC.

### 20.6. Hiệu năng restore

Đo data streaming, compaction pressure, hints/repair backlog, read p99 và coordinator timeouts dưới tải. Có thể mất nhiều giờ sau khi node đã lên mới đạt SLO.

### 20.7. Bài diễn tập có giá trị

Khôi phục một node từ snapshot+rebuild, đo time to serving; một bài DR khác phục hồi cluster/data scope ở topology cách ly, kiểm mọi token ranges và deleted rows.

---

## 21. DynamoDB: test PITR/restore phải đo cả tái cấu hình

DynamoDB là managed service; người dùng không tự stop/start storage nodes. Trong phạm vi AWS được cấp quyền, có thể diễn tập on-demand backup/PITR và restore tới table mới.

### 21.1. Xác định cửa sổ PITR thật

Lấy earliest/latest restorable time từ service API/console của table hiện hành. Không suy `ACTIVE` đồng nghĩa PITR đang bật.

### 21.2. Restore tới table đích mới

Một quy trình restore phổ biến tạo new table; cần kiểm table status, items, keys/indexes và cấu hình bổ sung, không ghi đè source đang chạy bằng thao tác không kiểm soát.

### 21.3. Không mặc định mọi table settings được giữ

Kiểm thực tế các thành phần cần cho ứng dụng: GSIs, TTL, Streams, IAM/resource policies, encryption, autoscaling/capacity, tags, alarms, global-table relationships và backup policy. Tính công việc tái cấu hình vào RTO.

### 21.4. GSI consistency

Đừng dùng GSI eventual read làm oracle tức thời cho dữ liệu mới ghi nếu contract đòi read-your-writes. Dùng base table/authoritative read path khi phù hợp.

### 21.5. Read-only preflight ví dụ

~~~bash
aws dynamodb describe-continuous-backups \
  --table-name orders-dr-test

aws dynamodb describe-table \
  --table-name orders-dr-test
~~~

Lệnh giả định AWS CLI đã cấu hình tới **tài khoản và region thử nghiệm**. Chúng chỉ nhằm quan sát trạng thái, không thực hiện restore. Không chạy các thao tác tạo/xóa/restore có side effects khi chưa kiểm account/region/resource.

### 21.6. Đo service-ready

Table trở lại `ACTIVE` không chứng minh application đã cutover, SDK endpoint/IAM đúng, consumer Streams ổn, hot partition không throttle hoặc nghiệp vụ không double-charge.

### 21.7. Global tables

Cross-region replication không thay backup lịch sử chống logical deletion. Thử global tables conflicts/failover riêng nếu nằm trong recovery contract.

---

## 22. Redis: khôi phục persistence và tính đúng của cache/state

### 22.1. RDB và AOF

RDB snapshots và AOF có durability/restore behavior phụ thuộc cấu hình, fsync policy, failover và storage. Không suy một `PONG` sau restart chứng minh đã phục hồi mọi write đã ACK.

### 22.2. Redis chỉ là cache derived?

Nếu toàn bộ keys là recomputable cache, có thể quyết định không giữ RPO dữ liệu Redis, nhưng phải kiểm **cache cold-start** và tải tăng trên NoSQL source.

### 22.3. Redis chứa state quan trọng?

Nếu có idempotency, session, rate-limit, queue hay lock tokens, cần quy tắc RPO/RTO riêng. Mất active idempotency ledger có thể gây side effects trùng.

### 22.4. Cluster/Sentinel

Khôi phục snapshot của một master chưa đủ nếu slot ownership, Sentinel discovery, replication/failover topology và client routing không đúng.

### 22.5. TTL/expiration sau restore

Không phục hồi expired session rồi cho authorize. Hợp đồng application cần kiểm `expiresAt`, không dựa hoàn toàn vào physical removal.

### 22.6. Cache stampede

Thử warm-up bằng representative load có giới hạn, single-flight/circuit breaker/rate limiting; đừng cho tất cả clients refetch catalog cùng lúc.

---

## 23. Elasticsearch/OpenSearch: restore index và khôi phục search service

### 23.1. Repository/snapshot

Dùng snapshot API/repository phù hợp engine và version; copy live index directory không là backup tương đương.

### 23.2. Restore scope

Kiểm index mappings, templates, analyzers, aliases, pipelines, metadata, security context và data streams nếu dùng.

### 23.3. Snapshot có thể không cùng checkpoint với source NoSQL

Nếu Orders đã cập nhật tới version 8 nhưng search snapshot chỉ version 6, có thể rebuild/replay từ authoritative source và CDC watermark.

### 23.4. Health colors không là business oracle

Cluster `green`/`yellow`/`red` giúp nhìn shard allocation, nhưng không tự xác nhận search kết quả đúng hoặc latency đạt SLO.

### 23.5. Đo search RTO

Bao gồm restore repository, shard recovery, index warm-up, query canaries, alias cutover, search freshness và p99 under representative traffic.

### 23.6. Tách RTO search khỏi RTO order writes

Có thể ưu tiên khôi phục critical order writes trước, còn search được rebuild sau; ghi trạng thái `DEGRADED` một cách minh bạch.

---

## 24. Couchbase và các NoSQL khác: tránh dùng một playbook chung

Với Couchbase, cần xét buckets/scopes/collections, data/index/query services, CAS/transaction semantics, vBucket ownership, rebalance, backups và metadata theo product/version.

Một bài restore đúng cần:

- Chọn công cụ backup/restore được hỗ trợ cho bản cài.
- Xác định dữ liệu, indexes, users/roles và service configs cần đi cùng.
- Đo thời gian restore từng service.
- Kiểm ownership/replica placements và rebalancing.
- Kiểm SDK reconnect và query/KV readiness.
- Đo cluster goodput/p99 sau warm-up.
- Đối soát đúng version/CAS và business invariants.

Tương tự, với Neo4j, ScyllaDB, FoundationDB-based products hoặc RocksDB state stores, cần **runbook và semantics riêng**, không suy snapshots/backups tương thích giữa engines.

---

## 25. Khôi phục từ logical corruption cần một oracle “điểm sạch”

Nếu ứng dụng ghi sai giá cho 100.000 products lúc 10:10:

~~~text
10:00  Snapshot sạch
10:05  Đơn hàng hợp lệ tiếp tục được ghi
10:10  Bug bắt đầu sửa giá sai
10:17  Bug được phát hiện
10:20  Writes được dừng/quarantine
~~~

Nếu restore cả database về 10:00, bạn có thể mất các đơn hợp lệ từ 10:05. Nếu replay toàn bộ log tới 10:20, bạn áp lại bug.

### 25.1. Chiến lược có thể cần

- Xác định tập entities affected.
- Restore ra **môi trường cách ly** tại một mốc trước bug.
- So sánh với authoritative data/ledger.
- Chọn lọc các thay đổi hợp lệ sau điểm đó.
- Rebuild projections và index.
- Reconcile bên ngoài database.
- Phê duyệt cutover/repair có evidence.

### 25.2. Không xóa source đang lỗi trước khi điều tra

Giữ logs/backup manifests/affected IDs và audit evidence theo retention/security policy.

### 25.3. Time-to-detect ảnh hưởng khả năng PITR

Nếu corruption phát hiện sau 30 ngày nhưng PITR chỉ giữ 7 ngày, có thể không còn recovery point sạch. Recovery test nên thử các detection-delay scenarios phù hợp.

---

## 26. Backup integrity khác business correctness

Một file có SHA-256 khớp, giải mã được và parse được vẫn có thể chứa:

- Cùng email active bị trùng.
- Tồn kho âm.
- Payment chưa được đối soát.
- Record có `tenantId` sai.
- Trường `amount` bị làm tròn.
- Event version cũ ghi đè bản mới.
- Dữ liệu nhạy cảm đã delete nhưng hồi sinh.

### 26.1. Ba tầng verification

1. **Physical:** bytes, checksums, manifest, file decryptability.
2. **Logical:** schema, IDs, constraints, counts, index/query outputs.
3. **Business:** invariants, external receipts, tenant isolation, authorization, deletion, side effects.

### 26.2. Một oracle nên độc lập

Không lấy `deserialize(serialize(x)) == x` với cùng converter bị lỗi làm bằng chứng duy nhất. Với dữ liệu quan trọng có thể dùng canonical logical comparisons, independent ledger và domain owner review.

### 26.3. Điểm quan sát nhất quán

Không so source live và restored target ở hai mốc khác nhau mà không tính changes trong khoảng. Chọn logical cut/commit checkpoint rồi reconcile phần mới.

---

## 27. Java 17: ghi nhận timeline RTO có kiểm tra thứ tự

Một class dùng `Instant`/`Duration` giúp báo cáo khách quan các mốc. `Clock` phải đồng bộ hoặc có giải thích clock source khi collector phân tán.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class RecoveryTimeline {

    public record Result(
        Duration detectionTime,
        Duration restorePhaseTime,
        Duration endToEndRto,
        boolean objectiveMet
    ) {}

    public static Result evaluate(
            Instant failureStart,
            Instant failureDetected,
            Instant restoreStarted,
            Instant restoreFinished,
            Instant serviceStable,
            Duration rtoTarget) {

        Objects.requireNonNull(failureStart);
        Objects.requireNonNull(failureDetected);
        Objects.requireNonNull(restoreStarted);
        Objects.requireNonNull(restoreFinished);
        Objects.requireNonNull(serviceStable);
        Objects.requireNonNull(rtoTarget);

        if (rtoTarget.isNegative()) {
            throw new IllegalArgumentException("Negative target");
        }

        if (failureStart.isAfter(failureDetected)
                || failureDetected.isAfter(restoreStarted)
                || restoreStarted.isAfter(restoreFinished)
                || restoreFinished.isAfter(serviceStable)) {
            throw new IllegalArgumentException(
                "Invalid ordered timeline"
            );
        }

        Duration detect = Duration.between(
            failureStart, failureDetected);
        Duration restore = Duration.between(
            restoreStarted, restoreFinished);
        Duration rto = Duration.between(
            failureStart, serviceStable);

        return new Result(
            detect,
            restore,
            rto,
            rto.compareTo(rtoTarget) <= 0
        );
    }
}
~~~

### 27.1. Điều hàm này làm

Nó tính khoảng thời gian và chống thứ tự mốc bất hợp lệ. Nó **không tự chứng minh** mốc `serviceStable` là thật. Điều đó phải đến từ canary/load/business correctness gates.

### 27.2. Timezone và monotonic clocks

`Instant` dùng timestamp có thể so nếu máy được đồng bộ và sources đủ tin cậy. Với phép đo latency nội bộ, `System.nanoTime()` là monotonic trên một process; không so trực tiếp các giá trị `nanoTime()` ở hai hosts.

### 27.3. RTO không phải backup age

Không đưa snapshot timestamp vào vị trí `restoreStarted`; hai đại lượng khác nhau.

---

## 28. Java JUnit 5: kiểm tính thời gian đã tính

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

public class RecoveryTimelineTest {

    @Test
    void endToEndExceedsRestoreOnly() {
        var result = RecoveryTimeline.evaluate(
            Instant.parse("2026-11-14T10:00:00Z"),
            Instant.parse("2026-11-14T10:04:00Z"),
            Instant.parse("2026-11-14T10:35:00Z"),
            Instant.parse("2026-11-14T11:20:00Z"),
            Instant.parse("2026-11-14T12:25:00Z"),
            Duration.ofHours(2)
        );

        assertEquals(
            Duration.ofMinutes(45),
            result.restorePhaseTime()
        );
        assertEquals(
            Duration.ofMinutes(145),
            result.endToEndRto()
        );
        assertFalse(result.objectiveMet());
    }

    @Test
    void invalidTimelineCannotReportPass() {
        assertThrows(
            IllegalArgumentException.class,
            () -> RecoveryTimeline.evaluate(
                Instant.parse("2026-11-14T11:00:00Z"),
                Instant.parse("2026-11-14T10:59:00Z"),
                Instant.parse("2026-11-14T11:10:00Z"),
                Instant.parse("2026-11-14T11:20:00Z"),
                Instant.parse("2026-11-14T11:30:00Z"),
                Duration.ofHours(1)
            )
        );
    }
}
~~~

### 28.1. Unit test không phải restore drill

JUnit xác nhận công thức/timeline validation; không tạo backup, không phục hồi database và không test canaries. Đừng báo `RTO VERIFIED` vì test Java này pass.

### 28.2. Đồng hồ ghi mốc trong drill

Dùng instrumentation/incident controller ghi events có nguồn đáng tin, đồng thời lưu logs để tra lại mốc. Không chỉnh timestamp bằng tay chỉ để khớp target.

---

## 29. Java: kiểm RPO từ verified recoverable point

Không lấy thời điểm backup job kết thúc làm recovery point.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class RecoveryPointCheck {

    public record Result(
        Duration recoveryGap,
        boolean objectiveMet
    ) {}

    public static Result evaluate(
            Instant failureStart,
            Instant latestVerifiedRecoverablePoint,
            Duration rpoTarget) {

        Objects.requireNonNull(failureStart);
        Objects.requireNonNull(latestVerifiedRecoverablePoint);
        Objects.requireNonNull(rpoTarget);

        if (rpoTarget.isNegative()) {
            throw new IllegalArgumentException("Negative RPO");
        }

        if (latestVerifiedRecoverablePoint.isAfter(failureStart)) {
            throw new IllegalArgumentException(
                "Recovery point after failure start"
            );
        }

        Duration gap = Duration.between(
            latestVerifiedRecoverablePoint,
            failureStart
        );

        return new Result(
            gap, gap.compareTo(rpoTarget) <= 0
        );
    }
}
~~~

### 29.1. Đầu vào phải verified

`latestVerifiedRecoverablePoint` chỉ hợp lệ nếu baseline + logs + keys + scope có thể khôi phục trong failure scenario. Không tự trả `Instant.now()` khi backup metadata thiếu.

### 29.2. Một point per shard?

Nếu mỗi shard có latest restorable point khác nhau, cần công cụ/logic xác định **cluster-consistent cut** hoặc công bố scope partial. Không lấy maximum point của shard tốt nhất làm RPO toàn cluster.

### 29.3. Unknown data loss

Nếu có gap log/commit history, kết quả nên là `UNKNOWN`/`UNRECOVERABLE`, không pass dựa trên một timestamp trang trí.

---

## 30. Java: kiểm business canary sau restore

Một chương trình restore integration test cần đọc **database thật** thông qua repository/driver thật và so dữ liệu đã seed trước sự cố.

Định nghĩa contract đơn giản:

~~~java
import java.util.Optional;

public interface RestoredOrderStore {
    Optional<OrderRecord> findByTenantAndId(
        String tenantId, String orderId
    );

    boolean createIfAbsent(
        String tenantId,
        String orderId,
        long amountMinor
    );

    record OrderRecord(
        String tenantId,
        String orderId,
        long amountMinor,
        String status
    ) {}
}
~~~

Một bộ acceptance tests có thể dùng với adapter production:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

public abstract class RestoreContractTest {

    protected abstract RestoredOrderStore restoredStore();

    // Các record phải được seed trong snapshot/source
    // theo kịch bản được phê duyệt trước restore.
    protected abstract String survivingOrderId();
    protected abstract String deletedOrderId();

    @Test
    void committedOrderIsRecoveredExactly() {
        var order = restoredStore()
            .findByTenantAndId(
                "tenant-A", survivingOrderId()
            ).orElseThrow();

        assertEquals("tenant-A", order.tenantId());
        assertEquals(10020L, order.amountMinor());
        assertEquals("PAID", order.status());
    }

    @Test
    void wrongTenantCannotSeeOrder() {
        assertTrue(
            restoredStore()
                .findByTenantAndId(
                    "tenant-B", survivingOrderId()
                ).isEmpty()
        );
    }

    @Test
    void deletedOrderIsNotVisibleAfterReconciliation() {
        assertTrue(
            restoredStore()
                .findByTenantAndId(
                    "tenant-A", deletedOrderId()
                ).isEmpty()
        );
    }

    @Test
    voidNewOrderCanBeWrittenSafely() {
        String id = "dr-canary-unique-id";
        assertTrue(
            restoredStore().createIfAbsent(
                "tenant-A", id, 2000L
            )
        );
        assertFalse(
            restoredStore().createIfAbsent(
                "tenant-A", id, 2000L
            )
        );
    }
}
~~~

### 30.1. Điều kiện để suite có giá trị

`RestoredOrderStore` phải nối đến restored target trong **môi trường cách ly**, không phải mock. IDs/canary data phải được seed và ghi trong manifest trước fault; không dùng dữ liệu production tùy tiện.

### 30.2. Xóa và idempotency

Test `deletedOrderIsNotVisibleAfterReconciliation` kiểm outcome cuối; cần thêm ledger/receipt tests khi có side effects hoặc deletion history phức tạp.

### 30.3. Write canary phải an toàn

Chỉ tạo dữ liệu trong test tenant/namespace đã được phê duyệt, có cleanup/idempotency và không tạo invoices/thanh toán/email thật.

### 30.4. Mã minh họa

Ví dụ không cung cấp một implementation driver cụ thể; mỗi đội cần adapter MongoDB/Cassandra/DynamoDB thật và test fixture có identity phù hợp. Đây là contract layer, không phải test đã được chạy.

---

## 31. Đo service stable thay vì một canary đơn lẻ

Ví dụ một yêu cầu gate trong 5 phút:

~~~text
Critical read success rate:       >= 99.9%
Critical write success rate:      >= 99.9%
p99 GetOrder:                     <= approved limit
p99 CreateOrder:                  <= approved limit
Error rate excluding valid 4xx:  <= approved limit
Cross-tenant violations:         0
Duplicate charge effects:        0
Reconciliation blockers:         0
Required replica/quorum:         satisfied
CDC lag:                         within approved window
~~~

Các ngưỡng phải theo business SLO, không mặc định những số ví dụ này phù hợp mọi ứng dụng.

### 31.1. Traffic volume phải có ý nghĩa

Một khoảng 5 phút không có request sẽ cho tỷ lệ thành công không đo được; phải có canary/synthetic load đủ đại diện.

### 31.2. Liveness khác readiness

Database process alive không bảo đảm read/write eligibility. Trong hệ quorum, có thể đọc được nhưng không thể commit writes theo consistency policy.

### 31.3. Không thay đổi consistency ngầm để pass

Giảm write concern hoặc chuyển sang stale reads để canary thành công có thể phá recovery contract.

### 31.4. Có thể phục hồi từng tier

Một service có thể tạm `READ_ONLY_RECOVERED` rồi `CRITICAL_WRITES_RECOVERED` rồi `FULLY_RECOVERED`; ghi rõ mốc và không gộp.

---

## 32. Chạy restore với tải nền và burst retries

RTO khi hệ không có traffic có thể thấp hơn thực tế.

### 32.1. Các nguồn tải khi recovery

- Database log replay.
- Index/shard rebuilding.
- Anti-entropy/repair/compaction.
- Warm caches.
- Retry storm từ Java clients.
- CDC consumer catch-up.
- Analytics/batch jobs.
- Connection pool ramp-up.
- Cross-region network transfer.

### 32.2. Điều khiển tải

Ưu tiên critical paths, giới hạn batch/repair/reindex, dùng bounded queue/admission, backoff+jitter, tránh retry amplification.

### 32.3. Test hai pha

1. Restore ở chế độ isolated để đo raw capability.
2. Restore/cutover trong môi trường có **representative workload** để đo user-visible RTO.

### 32.4. Không đẩy tải lên mức phá hủy

Chaos/load test cần bounded budget. Không dùng backup drill làm cớ tạo load spike trên production dependencies.

---

## 33. Metrics bắt buộc của một restore drill

| Metric | Vai trò |
|---|---|
| `backup_last_success_timestamp` | Backup job hoàn tất lúc nào |
| `verified_recoverable_point_age_seconds` | Độ cũ của point thật có thể restore |
| `backup_chain_missing_segments` | Phát hiện PITR gap |
| `backup_artifact_checksum_failure_total` | Artifact hỏng |
| `backup_offsite_copy_lag_seconds` | Nguy cơ khi mất region |
| `restore_elapsed_seconds` | Raw restore phase |
| `restore_transfer_mib_per_second` | Actual data transfer throughput |
| `restore_replay_lag_seconds` | Backlog |
| `restore_index_rebuild_duration_seconds` | Index bottleneck |
| `dr_recovery_end_to_end_seconds` | RTO đo theo contract |
| `dr_data_invariant_failures_total` | Lỗi correctness |
| `dr_unreconciled_transactions` | Side effects cần đối soát |
| `dr_deleted_records_resurrected_total` | Delete safety |
| `dr_canary_read_write_success` | Application service |
| `dr_api_p99_seconds` | SLO sau cutover |
| `dr_client_retries_total` | Retry pressure |
| `dr_last_successful_drill_timestamp` | Độ mới của bằng chứng DR |

Tên metric là **mẫu đề xuất**, không nói exporters của mọi engine có sẵn.

### 33.1. Một metric `backup_success=1` rất yếu

Nó không cho biết dữ liệu đến mốc nào, khôi phục được trên vùng khác hay mất bao lâu để vào production service.

### 33.2. Tránh high cardinality

Không dùng order ID, email, request ID hoặc arbitrary tenant ID làm Prometheus labels. Dùng scope/tier/scenario và giữ evidence chi tiết trong secure artifacts.

### 33.3. Theo dõi lỗi của chính harness

Nếu checker không chạy hoặc mất trace, kết quả không được coi là `PASS`.

---

## 34. Báo cáo kết quả diễn tập: `PASS`, `FAIL`, `UNKNOWN`

| Kết quả | Khi nào dùng |
|---|---|
| `PASS` | RPO/RTO và correctness gates đạt trong scope được thử |
| `FAIL` | Một objective hoặc invariant bị vi phạm |
| `UNKNOWN` | Không đủ dữ liệu để kết luận |
| `NOT_RUN` | Test chưa được thực hiện |
| `NOT_REPRESENTATIVE` | Môi trường không mô phỏng failure/load đang khẳng định |
| `PARTIAL_RECOVERY` | Một số operation classes phục hồi, chưa đủ full contract |
| `SKIPPED_INFRA` | Thiếu cluster/account/key/runner nên không chạy |

### 34.1. Báo cáo một test xanh nhưng chưa đủ độ tin cậy

> “Restore 200 GiB dữ liệu trên staging thành công, RTO đo 38 phút, zero invariant violations trong dữ liệu test. Chưa kiểm restore 6 TiB production-size, region-loss failure domain, managed IAM restrictions và index warm-up dưới peak traffic.”

Đó là báo cáo **có thể hành động**, không phải thất bại.

### 34.2. Số lần PASS không đủ

Một lần pass hôm nay không chứng minh DR runbook còn đúng sau thay đổi schema, indexes, topology, key rotation hoặc tăng data size 10 lần.

### 34.3. Cần người chịu trách nhiệm

Business owner duyệt recovery objective và correctness; SRE/data team cung cấp evidence; security/privacy review dữ liệu nhạy cảm; incident commander quyết định cutover theo runbook.

---

## 35. Recovery report mẫu

~~~yaml
drillId: DR-ORDERS-2026-11-14
scenario: region-primary-unavailable
scope: order-read-and-write
environment: isolated-dr-staging
faultStartedAt: "2026-11-14T10:00:00Z"
faultDetectedAt: "2026-11-14T10:04:00Z"
restoreStartedAt: "2026-11-14T10:35:00Z"
restoreCompletedAt: "2026-11-14T11:20:00Z"
serviceStableAt: "2026-11-14T12:25:00Z"
recoverablePointAt: "2026-11-14T09:57:00Z"
objectives:
  rpoSeconds: 300
  rtoSeconds: 7200
observed:
  recoveryGapSeconds: 180
  endToEndRtoSeconds: 8700
  restorePhaseSeconds: 2700
  businessInvariantFailures: 0
  missingEvidenceCount: 0
result: FAIL
reason: "RTO exceeded; RPO and correctness checks met"
bottlenecks:
  - index-build-after-replay
  - application-cache-warmup
artifacts:
  - backup-manifest-with-verified-checkpoint
  - redacted-restore-timeline
  - reconciliation-report
  - api-canary-summary
limitations:
  - synthetic scale smaller than production
owner: data-platform
~~~

Các số trong mẫu nhất quán với timeline minh họa: 10:00→12:25 = 145 phút, target 120 phút → `FAIL` dù RPO 3 phút đạt mục tiêu 5 phút.

### 35.1. Không điền bản báo cáo bằng số đoán

Test runner phải ghi thời gian và artifact metadata quan sát được. Những trường chưa biết để UNKNOWN, không điền `0`.

### 35.2. Kết luận theo từng objective

Nên xuất `rpoPass`, `rtoPass`, `dataCorrectnessPass`, `serviceSloPass`, `securityPass` riêng. Kết quả tổng chỉ `PASS` khi tất cả gates bắt buộc đạt.

---

## 36. Runbook A: diễn tập restore thường kỳ

### Pha 0 — Phê duyệt và guardrails

1. Chọn một scenario cụ thể, ví dụ mất primary region.
2. Ghi owner, mục tiêu RPO/RTO và failure-domain assumptions.
3. Chọn test account/region/cluster cách ly.
4. Xác nhận không truy cập/chỉnh sửa dữ liệu production nếu không được phép.
5. Chuẩn bị synthetic canary records và unique operation IDs.
6. Khai báo stop conditions, rollback và cleanup.
7. Phân quyền operator, reviewer, incident commander.

### Pha 1 — Baseline và backup chain

8. Thu source checkpoint, các committed transaction IDs có thể đối chiếu.
9. Kiểm full snapshot/incremental/log manifests.
10. Kiểm offsite copy đã đến đúng failure domain.
11. Thử quyền decrypt/KMS và read backup artifacts.
12. Kiểm source/target engine/schema/tool compatibility.
13. Ghi source data size, mutation rate, indexes, CDC positions.

### Pha 2 — Fault và start clock

14. Gây lỗi **chỉ trong môi trường được cấp phép**.
15. Ghi `failureStartedAt` qua controller độc lập.
16. Theo dõi detection và escalation.
17. Chọn recovery point sạch và khả dụng.
18. Ghi quyết định để tránh lựa chọn point sau khi nhìn output.

### Pha 3 — Restore thực tế

19. Provision network, storage, compute, IAM/keys.
20. Restore baseline và segments.
21. Replay logs đến target point theo engine protocol.
22. Xác nhận cluster metadata/shards/indexes/roles.
23. Khôi phục CDC/outbox offsets có consistency.
24. Rebuild/reconcile search/cache và business dependencies.
25. Giám sát CPU/IOPS/network/log replay/index progress.

### Pha 4 — Dữ liệu và ứng dụng

26. Chạy physical/logical/business integrity checks.
27. Kiểm deletes/revocations/retention.
28. Đối soát external payment/fulfillment effects.
29. Chạy read/write canaries trong test namespace.
30. Thử tải thực tế và theo dõi error rate/p99/goodput.
31. Chuyển traffic test theo kế hoạch.
32. Ghi `serviceStableAt` khi tất cả gates đạt.

### Pha 5 — Báo cáo và cải thiện

33. Tính RPO/RTO actual từ mốc đã quy định.
34. Ghi PASS/FAIL/UNKNOWN theo từng contract.
35. Lưu manifests, timelines, logs, source versions, oracle results.
36. Phân tích bottlenecks, manual delays và failure domains chưa thử.
37. Lập corrective actions có owner và tiêu chí kiểm lại.
38. Dọn resource theo phê duyệt, giữ evidence hợp lệ.
39. Cập nhật tài liệu và lịch diễn tập tiếp theo.

---

## 37. Runbook B: node crash không cần restore toàn bộ

Đừng tự chọn full restore khi một node mất nhưng replica set/cluster còn healthy.

### 37.1. Triage

- Process crash hay host/network partition?
- Quorum/leader còn không?
- Writes đã ACK theo contract còn được phục vụ không?
- Data volume mất thật hay có thể rejoin?
- Replica có bị offline quá history/tombstone window?

### 37.2. Chọn đường phục hồi

- Automatic failover.
- Restart từ local WAL/journal.
- Replica rebuild/resync từ healthy peers.
- Restore snapshot nếu dữ liệu local không còn.
- Full DR only nếu failure domain lớn hơn.

### 37.3. Đo mục tiêu riêng

RTO của node failure có thể là thời gian từ loss đến API traffic ổn định, không phải thời gian rebuild replica background hoàn tất, **nếu recovery contract cho phép service ở degraded redundancy**. Tuy nhiên phải ghi degraded/repair debt riêng và điều kiện để tiếp tục maintenance.

### 37.4. Không dừng node tiếp theo

Nếu chưa có đủ replicas/quorum hoặc repair lag chưa giảm, hoãn rolling restart tiếp theo.

---

## 38. Runbook C: phục hồi lỗi xóa nhầm

### 38.1. Khoanh vùng và giữ chứng cứ

Ngừng writer gây lỗi, ghi delete operation IDs, affected collections/tables và timestamp/positions. Giữ logs theo policy.

### 38.2. Chọn mốc sạch

Xác định point trước logical deletion nhưng **không tự bỏ những writes hợp lệ sau mốc**. Cần chiến lược selective restore hoặc reconciliation.

### 38.3. Restore cách ly

Khôi phục vào namespace/table/cluster khác; không chạy lệnh kiểu `--drop` trên production theo thói quen. Xác nhận đúng target.

### 38.4. Reconcile

Lấy records sạch; áp lại những legitimate changes cần thiết; bảo vệ user deletion/revocation và external side effects.

### 38.5. Cutover

Chỉ cập nhật nguồn phục vụ khi business oracle và authorization đã đạt. Theo dõi events cũ đến muộn không ghi đè dữ liệu mới.

### 38.6. Đo RTO

Tính từ lúc xảy ra/fault bắt đầu theo contract, kể cả thời gian điều tra thời điểm corruption và quyết định mốc phục hồi.

---

## 39. Runbook D: mất region hoặc tài khoản cloud

### 39.1. Điều kiện đặc thù

- Source region/account có thể hoàn toàn unavailable.
- DNS, KMS, IAM hoặc control plane có thể bị ảnh hưởng.
- Offsite backup phải độc lập với failure domain.
- DR account phải có quyền restore từ trước.
- Dung lượng compute/network và quotas tại region đích phải đủ.

### 39.2. Khôi phục

Provision bằng IaC đã pin, gắn encryption keys/roles, restore mọi datasets/cut được hỗ trợ, replay logs và cấu hình endpoints.

### 39.3. Ngăn hai nguồn ghi

Nếu old region sống lại, không cho tự động nhận writes trước khi authority/fencing/failback protocol được quyết định.

### 39.4. Tính đủ thời gian

IAM/KMS approval, network policies, quota increase, DNS propagation, cache warm-up và client reconnect đều góp RTO.

### 39.5. Security drill

Không đưa backup nhạy cảm vào public endpoint/staging không bảo vệ. Separate account/immutable copy hữu ích khi primary admin credentials bị compromise.

---

## 40. Ma trận 40 ca kiểm thử backup/restore và thời gian phục hồi

| ID | Kịch bản | Điều cần chứng minh |
|---|---|---|
| DR01 | Backup job success nhưng artifact thiếu | Không báo backup recoverable giả |
| DR02 | Checksum một segment sai | Restore fail closed |
| DR03 | Incremental segment giữa chain mất | PITR không skip history |
| DR04 | Backup repo trong failure domain bị mất | Offsite copy thực sự còn |
| DR05 | KMS decrypt bị từ chối ở DR | Báo blocker, không PASS giả |
| DR06 | Source schema mới hơn restore binary | Compatibility được kiểm |
| DR07 | Snapshot hoàn tất sau logical checkpoint | RPO tính theo checkpoint |
| DR08 | Một shard có backup cũ hơn shards khác | Không lấy recovery point tốt nhất đại diện toàn cluster |
| DR09 | Restore có indexes nhưng mappings khác | Query correctness kiểm |
| DR10 | Restore source bị logical corruption | Chọn mốc sạch, không replay bug |
| DR11 | Restore xong nhưng DB TCP chưa ready | Không dừng RTO clock |
| DR12 | DB ready nhưng writes không đạt quorum | Chưa đạt write gate |
| DR13 | API read thành công, write fail | Partial recovery đúng |
| DR14 | Cache lạnh tạo backend burst | Admission/rate limit, đo p99 |
| DR15 | Stream replay tụt sau restore | Backlog và watermark đo |
| DR16 | Consumer offset mới hơn restored source | Không skip logical events |
| DR17 | Event retry/redelivery | Không double side effect |
| DR18 | Payment captured sau snapshot | Ledger reconciliation bắt được |
| DR19 | Idempotency ledger mất sau restore | Không double charge |
| DR20 | Legitimate delete xảy ra sau snapshot | Không resurrect dữ liệu |
| DR21 | Revoked permission hồi sinh từ snapshot | Security gate từ chối |
| DR22 | MongoDB single collection restore | IDs/indexes/business data đúng |
| DR23 | MongoDB sharded PITR | Cluster-consistent scope |
| DR24 | MongoDB restored transaction history | Không partial commits/unknown outcome sai |
| DR25 | Cassandra SSTable snapshot + schema | Đúng ranges và schema |
| DR26 | Cassandra stale replica/tombstone | Không zombie rows |
| DR27 | Cassandra compaction/streaming under load | p99 và capacity còn đạt |
| DR28 | DynamoDB restore new table | IAM, indexes, TTL/streams/cutover được kiểm |
| DR29 | DynamoDB PITR cutoff | Timestamp trong earliest/latest support |
| DR30 | DynamoDB hot partition sau restore | Throttle và SDK retries có hạn |
| DR31 | Redis RDB restore | Keys/expiry/persistence đúng contract |
| DR32 | Redis AOF failover | ACKed write loss theo policy được đo |
| DR33 | Redis lost cache | Warm-up không phá source DB |
| DR34 | Elasticsearch snapshot restore | Alias/query/analyzer/read index đúng |
| DR35 | Elasticsearch shard recovery | Readiness không chỉ `green` |
| DR36 | Couchbase KV/index services | Rebalance/warmup và data correctness |
| DR37 | 1 GiB smoke pass nhưng 3 TiB test fail | Scale test phát hiện RTO gap |
| DR38 | Slow object storage/network | Transfer bottleneck được ghi |
| DR39 | DR cluster ổn nhưng Java clients dùng DNS cũ | RTO gồm reconnect/cutover |
| DR40 | Restore pass nhưng không thu đầy đủ trace | UNKNOWN, không coi PASS |

Mỗi test có environment/permissions/retention/cleanup và owner. Không tạo destructive failures trên production ngoài chương trình được phê duyệt.

---

## 41. Một bộ acceptance criteria đủ mạnh

Đối với mỗi restore drill cần:

### 41.1. Data gates

- Backup chain valid.
- Recoverable point trong RPO budget.
- Đủ source entities/shards cần phục vụ.
- Không có unreviewed data corruption.
- Không có duplicated critical business effects.
- Deletes/revocations đã reconcile.
- Tất cả security/tenant checks đạt.

### 41.2. Service gates

- Database cluster có đúng role/quorum.
- Java apps kết nối được qua TLS và IAM đúng.
- Critical read/write operations thành công.
- p99/error rate/goodput đạt ngưỡng trong stability window.
- Search/CDC/index/cache đạt mức dịch vụ theo scope.
- Không có retry amplification hoặc throttling không kiểm soát.

### 41.3. Time gates

- RPO actual được tính từ verified checkpoint.
- RTO actual được tính từ fault đến service stable.
- Mọi manual approval/wait/cutover thời gian đã được tính.
- Các gaps/UNKNOWN được trình bày minh bạch.

### 41.4. Process gates

- Operator làm được theo runbook.
- Artifacts đủ để review và reproduce.
- Không có side effects ngoài environment phê duyệt.
- Corrective actions có owner khi không đạt.

---

## 42. Sự khác biệt giữa RTO thực tế và một “ước lượng DR”

Một spreadsheet có thể dự báo 45 phút nhưng chưa từng restore.

### 42.1. Những ước lượng thường sai

- Dùng băng thông lý thuyết thay effective throughput.
- Không tính download từ archive tier.
- Không tính thời gian tìm đúng backup/keys.
- Không tính IAM/network prerequisites.
- Bỏ qua index build, compaction hoặc reindex.
- Bỏ qua replay backlog khi writers còn hoạt động.
- Không có thử nghiệm client cutover.
- Chỉ kiểm một row/point read.
- Không tính approval, validation và warm-up.

### 42.2. Đo chứ không đoán

Báo cáo `estimated` và `observed` riêng. Khi test fail RTO, tìm critical-path stage thay vì đổi nghĩa “recovered”.

### 42.3. Lặp lại sau thay đổi

Kích thước dữ liệu, schema/indexes, driver, database version, cloud quotas, keys hoặc network topology thay đổi có thể làm kết quả drill trước hết hạn.

---

## 43. Lịch diễn tập và tần suất

Không có một cadence phù hợp mọi hệ. Có thể thiết kế theo risk:

- **Theo mỗi release có thay đổi backup/restore/schema quan trọng:** smoke restore.
- **Định kỳ ngắn:** representative restore và correctness checks.
- **Định kỳ dài hơn:** full-size restore/DR region rehearsal.
- **Sau incident hoặc architecture change:** kiểm lại scenario đã phát sinh.
- **Sau key rotation, account/IAM migration hoặc storage tier change:** verify recovery access.

### 43.1. Evidence freshness

Ghi last successful drill theo scenario/version/size. Một drill của MongoDB 3 phiên bản trước có thể chưa đủ cho cluster mới.

### 43.2. Người khác phải chạy được

Một bài chỉ thành công khi đúng tác giả script có mặt không đủ khả năng vận hành. Tabletop exercise, handoff và runbook cần được kiểm với người trực on-call khác.

### 43.3. Game day có guardrails

Xác định blast radius, fault boundaries, kill switch, recovery owner, communication plan và maximum cost.

---

## 44. Các lỗi thường gặp khi thực hiện backup/restore tests

| Hiểu nhầm | Cách kiểm chứng đúng |
|---|---|
| “Cron backup success là có DR.” | Restore + app canaries |
| “Checksum đúng thì dữ liệu nghiệp vụ đúng.” | Business invariants |
| “Backup mới nhất chắc sạch.” | Logical corruption cutoff |
| “RPO đo từ lúc restore hoàn tất.” | Từ failure tới recoverable point |
| “RTO là thời gian chạy lệnh restore.” | End-to-end service stable |
| “Node UP thì app đã phục hồi.” | Read/write/quorum/SLO |
| “Replica đủ nên không cần backup.” | Operator error/ransomware |
| “PITR luôn có mọi timestamp.” | Verified window/log chain |
| “Một shard mới nhất đại diện cluster.” | Consistent cut toàn scope |
| “Restore cùng account cũng chống compromise.” | Failure-domain isolation |
| “KMS key không liên quan file backup.” | Decryptability test |
| “Một GB restore nhanh thì vài TB cũng nhanh.” | Representative scale |
| “Backup nén nhỏ chắc restore nhanh.” | CPU/IOPS/index/replay |
| “DynamoDB table ACTIVE là cutover xong.” | IAM/SDK/Streams/GSI/canary |
| “MongoDB secondary là backup lịch sử.” | Deletion có thể replicate |
| “Cassandra snapshot một node là toàn cluster.” | Token ranges/replica coverage |
| “Redis PONG là không mất idempotency.” | Ledger/data reconciliation |
| “Search green thì search đúng.” | Mapping/alias/query/watermark |
| “Kafka offset có thể giữ nguyên sau DB rewind.” | Checkpoint reconciliation |
| “Restart cache vô hại.” | Cold-start source overload |
| “Deleted PII cũ có thể chờ cleanup.” | Deletion/revocation safety gate |
| “Timeout nghĩa write chắc thất bại.” | Unknown outcome handling |
| “Một canary success là SLO đạt.” | Stability window và load |
| “Không cần ghi giờ phê duyệt.” | End-to-end RTO |
| “Có thể giảm write concern để pass.” | Giữ nguyên durability contract |
| “Một lần diễn tập xanh là được mãi.” | Lặp theo data/version/topology |
| “Test chưa chạy có thể đánh PASS.” | NOT_RUN/UNKNOWN |
| “Không có bug vì count khớp.” | IDs/versions/business history |
| “DR xong là chuyển traffic ngay.” | Reconciliation/security gates |
| “Failback chỉ đổi DNS.” | Authority/reverse sync |

---

## 45. Checklist trước khi tuyên bố khả năng khôi phục đạt yêu cầu

- [ ] Recovery scenario và failure domain được định nghĩa.
- [ ] Business owner phê duyệt RPO/RTO và recovery gates.
- [ ] Xác định authoritative data, derived data và phụ thuộc.
- [ ] Có backup manifest/snapshot lineage/checkpoints.
- [ ] Có baseline và incremental/log chain đầy đủ.
- [ ] Có checksum và verified artifact availability.
- [ ] Backup copy nằm ngoài failure domain đang thử.
- [ ] Restore credentials, IAM, KMS keys hoạt động ở DR.
- [ ] Schema/index/engine/driver compatibility được kiểm.
- [ ] Có recovery destination cách ly và đủ capacity.
- [ ] Data không bị copy vào nơi vi phạm PII/residency policy.
- [ ] Có mốc `failureStartedAt` rõ ràng.
- [ ] Có mốc `latestVerifiedRecoverablePoint` đúng scope.
- [ ] Không dùng `backup job completedAt` thay recovery point.
- [ ] Có timeline detect/triage/provision/restore/replay/validate/cutover.
- [ ] Có đo effective transfer/replay/index throughput.
- [ ] Có dữ liệu đại diện về size, hot keys, shard distributions.
- [ ] Có canary read/write và business invariant checks.
- [ ] Có ID-based reconciliation, không chỉ counts.
- [ ] Có xử lý unknown writes và idempotency ledger.
- [ ] Có đối soát với external payments/fulfillment.
- [ ] Có deletion/revocation reconciliation.
- [ ] CDC consumer offsets/watermarks được khớp với source restored.
- [ ] Không replay logical corruption vào restored data.
- [ ] Có test index/search projections và stale-read contract.
- [ ] Có cấu hình TLS/IAM/DNS/driver connections đúng.
- [ ] Có kiểm quorum/replication/roles theo engine.
- [ ] Có load/stability window để đo p99/error/goodput.
- [ ] Có định nghĩa rõ `PARTIAL_RECOVERY` và `FULL_RECOVERY`.
- [ ] Có RPO/RTO actual từ mốc đo, không chỉ estimates.
- [ ] Có status riêng PASS/FAIL/UNKNOWN/NOT_RUN.
- [ ] Có logs/traces/manifests/synthetic seeds được lưu và redacted.
- [ ] Có owner cho mọi corrective action và test lại.
- [ ] Có kế hoạch failback, không tạo double-primary.
- [ ] Không tắt security/durability để làm drill pass.
- [ ] Không phá production khi kiểm thử.
- [ ] Có lịch kiểm lại sau schema, version, size và key changes.
- [ ] Runbook đủ rõ để người trực khác thực hiện.

---

## 46. Bài tập 1 — Tính RPO và RTO từ timeline

Cho:

~~~text
Latest verified recoverable point: 08:56:30
Failure starts:                  09:00:00
Alert:                           09:05:00
Restore starts:                  09:28:00
Restore finishes:                10:36:00
Data checks finish:              10:59:00
Traffic cutover:                 11:09:00
Service stable:                  11:22:00

RPO objective: 5 phút
RTO objective: 2 giờ
~~~

1. Tính recovery point gap.
2. Tính restore-only duration.
3. Tính end-to-end RTO.
4. Objective nào đạt, objective nào không?
5. Vì sao không lấy `cutover` làm RTO endpoint nếu SLO chỉ ổn lúc 11:22?
6. Nếu latest recoverable copy ở **region đích** chỉ là 08:40, kết quả region-loss RPO đổi thế nào?
7. Đề xuất ba cải tiến giảm critical path.

---

## 47. Bài tập 2 — Dự báo tốc độ restore

Backup cần tải 4 TiB, effective throughput 600 MiB/s. Sau truyền:

~~~text
Decompression + storage ingest: 35 phút
Index rebuild:                  50 phút
Validation:                     20 phút
Cutover + warm-up:              15 phút
~~~

1. Tính transfer time.
2. Ước lượng tổng tuần tự.
3. Nếu RTO 120 phút, có khả thi không?
4. Nếu index rebuild chạy song song một phần với ingest, cần đo critical path thế nào?
5. Khi tăng parallel streams mà disk đã full IOPS, điều gì xảy ra?
6. Thiết kế bài load test để đo performance sau cutover.

---

## 48. Bài tập 3 — Restore MongoDB sau delete nhầm

Tình huống:

~~~text
10:00 Snapshot sạch
10:05 Khách A đặt đơn hợp lệ
10:07 Khách B thanh toán
10:10 Admin chạy deleteMany sai
10:13 Phát hiện
~~~

Yêu cầu:

1. Chọn recovery point sạch.
2. Nếu restore toàn DB về 10:00, thiếu điều gì?
3. Dùng authoritative payment ledger đối soát ra sao?
4. Thiết kế selective repair hoặc replay có lọc.
5. Chọn schema/index/role tests.
6. Tạo ba negative tests về privacy deletion.
7. Đo RTO đến mức CreateOrder phục vụ an toàn.
8. Nêu điểm nào cần manual approval.

---

## 49. Bài tập 4 — Cassandra restore và tombstone

Một node đã offline lâu, snapshot cũ thiếu delete events. Cluster còn peers đã garbage-collect tombstones.

1. Vì sao rejoin mù quáng có thể làm zombie data?
2. Cần kiểm repair/tombstone horizon nào?
3. Đâu là khác biệt giữa `nodetool snapshot`, rebuild và repair?
4. Làm thế nào xác nhận dữ liệu mọi token ranges đủ?
5. Thiết kế test restore staging có deleted rows.
6. Đo thời gian streaming/compaction.
7. Khi nào `UN` chưa đủ để mở writes?
8. Viết RPO/RTO report có caveats.

---

## 50. Bài tập 5 — DynamoDB PITR sang table mới

Một table đã bật PITR và cần khôi phục mốc trước lỗi ứng dụng.

1. Kiểm earliest/latest restorable timestamp.
2. Tạo table đích trong tài khoản thử nghiệm.
3. Ghi lại restoration timeline.
4. Kiểm GSI, TTL, Streams, policies, autoscaling/capacity theo actual restore settings.
5. Thiết kế idempotent cutover.
6. Test SDK/IAM connectivity.
7. Kiểm consistency của list queries qua GSI.
8. Đối soát writes sau selected restore point.
9. Đặt service-stable gate gồm p99/throttling.
10. Ghi những điểm chưa chứng minh vì chỉ dùng DynamoDB Local.

---

## 51. Bài tập 6 — Redis cold-start và side effects

Redis chứa:

~~~text
product-cache:*       Derived cache
session:*             Authentication sessions
idempotency:*         Payment request IDs
ratelimit:*           Abuse-control counters
~~~

1. Namespace nào có thể rebuild từ nguồn?
2. Namespace nào mất sẽ làm vi phạm correctness/security?
3. Nếu mất idempotency key, test double charge thế nào?
4. Tạo RDB/AOF restore drill cho test environment.
5. Tạo controlled cache warm-up và đo load source MongoDB.
6. Test expired tokens vẫn denied dù key còn.
7. Kiểm primary/replica failover nếu dùng Redis Cluster/Sentinel.
8. Ghi trạng thái partial recovery của ứng dụng.

---

## 52. Bài tập 7 — Thiết kế báo cáo diễn tập DR

Bạn có kết quả:

~~~text
Backup job: SUCCESS
Checksum: PASS
Restore: SUCCESS after 55 minutes
Source checkpoint: 17 minutes before fault
Order API read: PASS
Order API write: FAIL
Search: 40% documents still rebuilding
Idempotency ledger: UNKNOWN
RPO objective: 5 minutes
RTO objective: 90 minutes
~~~

1. RPO có đạt không?
2. Có thể tuyên bố RTO đạt nếu mới đo restore duration không?
3. Dữ liệu nào vẫn chưa an toàn?
4. Khi nào trạng thái là `PARTIAL_RECOVERY`?
5. Tại sao `Idempotency ledger: UNKNOWN` không phải PASS?
6. Lập corrective actions và phân công owners.
7. Soạn một report có limitations và evidence links.
8. Nêu điều kiện chính xác để tuyên bố full service recovered.

---

## 53. Bài tập 8 — Lập kế hoạch game day phục hồi dịch vụ

Hệ có:

~~~text
5 Java API instances
MongoDB primary replica set
Redis Cluster
Kafka outbox consumers
Elasticsearch search indexes
Payment provider sandbox
Cross-region backup repository
~~~

Thiết kế game day:

1. Chọn failure scenario: logical deletion hoặc region outage.
2. Chốt start/stop clocks và RPO/RTO objectives.
3. Tạo synthetic dataset với deletes/idempotency/transactions.
4. Xác minh backup chain và encryption-key access.
5. Đo restore/replay/index/cutover times.
6. Định nghĩa authorization, inventory và payment oracles.
7. Kiểm CDC offset và search projection.
8. Tạo representative API load có giới hạn.
9. Đưa ra fault-injection schedule an toàn.
10. Ghi PASS/FAIL/UNKNOWN và repro artifacts.
11. Thiết kế failback và cleanup.
12. Lên kế hoạch lặp khi dữ liệu tăng gấp đôi.

---

## 54. Tổng kết

**Kiểm chứng backup/restore là một thí nghiệm vận hành có đo lường và oracle, không phải một lần nhìn thấy `SUCCESS` trên scheduler.** Một hệ có thể phục hồi bytes dữ liệu nhưng chưa phục hồi khả năng phục vụ, có thể phục vụ nhanh nhưng bỏ sót committed transactions, hoặc có dữ liệu đầy đủ nhưng vô tình hồi sinh quyền truy cập đã revoke.

Những nguyên tắc quan trọng:

1. **Bắt đầu từ failure scenario, data authority và business contract.** RPO/RTO không có ý nghĩa nếu không rõ loại sự cố và operation scope.
2. **Backup file tồn tại khác restore được.** Kiểm chain, consistency, checksum, encryption keys và failure-domain independence.
3. **Restore được khác phục hồi dịch vụ.** Tính cả index build, log replay, reconciliation, application cutover và warm-up.
4. **RPO phải đo từ verified recoverable point** của đúng failure domain, không từ giờ backup job hoàn tất.
5. **RTO phải đo end-to-end từ sự cố đến service stable**, không dừng đồng hồ khi database process lên.
6. **Dữ liệu phục hồi phải đúng nghiệp vụ**: uniqueness, inventory, payments, tenant isolation, deletes/revocations và CDC checkpoint.
7. **Tải thực tế ảnh hưởng RTO**: transfer bandwidth, destination IOPS, backlog, cold cache và retries có thể chiếm phần lớn thời gian.
8. **Quy trình phụ thuộc engine/topology**: MongoDB, Cassandra, DynamoDB, Redis và search index có công cụ, metadata và giới hạn riêng.
9. **Không có bằng chứng thì ghi UNKNOWN/NOT_COVERED**, không biến backup job xanh thành báo cáo phục hồi xanh.
10. **Phải diễn tập định kỳ với môi trường và kích thước đại diện**, giữ timeline/artifacts và cải thiện runbook theo kết quả đo.

**Câu cần nhớ: “Backup chỉ có giá trị khi bạn khôi phục được đúng dữ liệu; phục hồi chỉ có giá trị khi khách hàng dùng lại được dịch vụ đúng và an toàn. RPO, RTO và bằng chứng kiểm thử thực tế phải cùng chứng minh điều đó.”**
