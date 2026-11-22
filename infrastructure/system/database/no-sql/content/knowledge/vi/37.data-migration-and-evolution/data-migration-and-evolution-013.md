# Xóa dữ liệu cũ, giữ bản sao cần thiết và cập nhật tài liệu vận hành

Kết thúc một đợt **di chuyển dữ liệu NoSQL** không có nghĩa chỉ chuyển traffic sang cụm mới và thấy các API trả HTTP 200. Hệ thống có thể vẫn còn dữ liệu ở cluster cũ, tiến trình dual-write hoặc CDC đang chạy, một bản sao lưu phục vụ rollback, các index/search projection cũ, account/secret còn quyền truy cập, và những runbook hướng dẫn người trực vận hành xử lý sự cố theo kiến trúc đã không còn đúng.

**Dọn dẹp quá sớm** có thể khiến không thể rollback, mất dữ liệu chưa chuyển hết, phá kiểm toán hoặc gây lỗi cho một consumer bị bỏ sót. **Không dọn dẹp** lại làm tăng chi phí, rủi ro lộ dữ liệu, độ phức tạp vận hành và khả năng client ghi nhầm vào nguồn đã lỗi thời. Vì vậy cần một quy trình chứng minh được *những gì không còn cần, những gì buộc phải giữ và những gì phải cập nhật để vận hành hệ mới an toàn*.

Bài học này thuộc chương **Di chuyển và thay đổi** của module **Database No SQL**, tập trung vào giai đoạn **post-cutover decommission & data lifecycle**: xác nhận nguồn chuẩn đã đổi, bảo vệ dữ liệu còn cần, xóa theo từng lớp có kiểm soát, và hoàn thiện tài liệu vận hành cùng bằng chứng nghiệm thu.

> **Nguyên tắc:** *Không xóa chỉ vì migration job báo thành công.* Chỉ xóa sau khi có **đối soát dữ liệu, kiểm tra các phụ thuộc đọc/ghi, quyết định về rollback và retention, bản phục hồi đã kiểm chứng, approval phù hợp và bằng chứng tác động của thao tác xóa**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **cutover**, **decommission**, **logical deletion**, **physical reclamation**, **archive**, **backup**, **retention** và **rollback**.
2. Xác định chính xác dữ liệu, metadata, queues, logs, indexes, caches, secrets, connector offsets và backups cần giữ hoặc loại bỏ sau một migration NoSQL.
3. Lập **tiêu chí đủ điều kiện xóa** dựa trên nguồn dữ liệu chuẩn, reconciliation, dual-write/CDC, client traffic, retention và khả năng rollback.
4. Thiết kế **các giai đoạn ngừng sử dụng → cách ly → xác minh → xóa có giới hạn → thu hồi tài nguyên**, thay vì xóa toàn cluster ngay.
5. Phân biệt **bản sao phục vụ quay lui**, **bản backup/PITR**, **bản lưu trữ kiểm toán** và **read model có thể tái tạo**.
6. Xử lý các trường hợp **tombstones, TTL, compaction, replication, cached copies, snapshots, immutable backups và deletion requests**.
7. Biết những khác biệt trong MongoDB, Cassandra/ScyllaDB, Redis, DynamoDB, Cosmos DB và Elasticsearch/OpenSearch khi dọn dẹp dữ liệu.
8. Viết và kiểm tra **kế hoạch change/deletion có điều kiện, dry-run, approval, audit trail và rollback/forward recovery**.
9. Cập nhật **sơ đồ kiến trúc, SOP/runbook, on-call dashboards, alerting, IAM, IaC, backup policy và ownership** theo hệ mới.
10. Thiết kế **kiểm thử, bài tập và checklist nghiệm thu** cho giai đoạn dọn dẹp mà không gây sự cố dữ liệu.

## 2. Tình huống xuyên suốt: chuyển Order Service sang NoSQL mới

Giả sử đội phát triển vừa chuyển Order Service Java từ kho dữ liệu cũ sang một kiến trúc NoSQL mới. Ví dụ này không ngụ ý phải dùng hai sản phẩm cụ thể; logic áp dụng khi đổi cluster, key design, schema, region hoặc engine.

~~~text
TRƯỚC MIGRATION
 Java Order API ----read/write----> Legacy Orders Store
    |                                 |
    +-- search index/caches            +-- backups/CDC

TRONG MIGRATION
 Java Order API --primary?--> Old Store
               --shadow-->   New Store
                     CDC backfill/replay
                     reconcile counts, versions, deletes

SAU CUTOVER DỰ KIẾN
 Java Order API ----read/write----> New NoSQL Store
    |                                 |
    +-- new indexes/caches             +-- new backup/PITR
 Old Store: read-only / quarantined / retired?
~~~

**Mục tiêu nghiệp vụ** (ví dụ):

- Tất cả order writes mới chỉ có một authority được công bố.
- Các order đã xác nhận trước cutover không bị thiếu hoặc ghi đè.
- Payment, refund và idempotency data vẫn liên kết đúng.
- Không một client cũ có thể lặng lẽ tạo một “nhánh dữ liệu” ngoài nguồn chuẩn.
- Có recovery/rollback plan trong cửa sổ đã thỏa thuận.
- Dữ liệu phải giữ theo quy định được bảo vệ; dữ liệu hết thời hạn được xóa đúng chính sách.
- Runbook cho on-call mô tả **đường đọc/ghi hiện tại**, không còn khuyên sửa legacy cluster.

### 2.1. Một timeline thay đổi minh họa

~~~text
D0  Backfill và đối soát baseline
D1  Dual-write/shadow read để kiểm thử
D2  Chuyển read path sang hệ mới
D3  Chuyển write authority sang hệ mới
D4  Dừng dual-write/CDC cũ khi an toàn
D5  Đưa legacy store sang read-only/quarantine
D6  Hết rollback window + retention/approval gates
D7  Xóa dữ liệu/resource cũ theo kế hoạch
D8  Kiểm tra hậu xóa và chốt tài liệu vận hành
~~~

Các mốc là **minh họa**, không phải số ngày khuyến nghị. Một hệ có business obligations dài hạn có thể phải lưu bản sao nhiều năm; hệ khác có thể xóa sớm hơn khi chính sách cho phép.

### 2.2. Vì sao “migration successful” chưa đủ để xóa?

Những ca chưa được bao phủ chỉ bằng API smoke test:

- Một consumer ban đêm vẫn đọc database cũ.
- Billing reconciliation job chạy mỗi cuối tháng.
- Một tenant hiếm gặp chưa được migrate do partition filter.
- Delete/tombstone không được replay, record đã xóa bỗng xuất hiện ở kho mới.
- Snapshot mới chưa được restore thử, chỉ có bản cũ là đường hồi phục.
- App code đã đổi nhưng deployment trong một region chưa cập nhật.
- Outbox/CDC offset ở hệ cũ còn một nhóm events chưa xử lý.
- Backup cũ chứa data có yêu cầu xóa theo luật nhưng không có deletion replay policy.
- Runbook on-call còn ghi lệnh restart/cập nhật endpoint legacy.

Vì vậy, **quyết định xóa phải dựa trên bằng chứng vận hành và dữ liệu**, không dựa vào một boolean “migrationDone”.

## 3. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Không tự có nghĩa |
| --- | --- | --- |
| **Cutover** | Chuyển client traffic/authority sang target | Old data đã có thể xóa |
| **Source of truth** | Nơi authoritative writes được quyết định | Mọi bản sao khác vô giá trị |
| **Decommission** | Ngừng phục vụ và giải thể thành phần cũ | Data đã bị xóa an toàn |
| **Quarantine** | Cách ly nguồn cũ khỏi traffic thông thường | Đã đáp ứng retention |
| **Archive** | Lưu dữ liệu dài hạn theo mục đích/retention | Có thể restore ngay thành live DB |
| **Backup/PITR** | Bộ artifact phục hồi tới điểm hỗ trợ | Là bản copy để đọc nhanh tùy ý |
| **Rollback copy** | Bản/snapshot giúp quay lại kiến trúc cũ | Không cần log/cutover replays |
| **Soft delete** | Ghi marker để ẩn hoặc đánh dấu xóa | Bytes đã bị giải phóng |
| **Hard/logical delete** | Lệnh xóa bản ghi ở API/storage semantics | Mọi replicas/backups đã xóa vật lý |
| **Physical reclamation** | Thu hồi bytes sau compaction/GC/delete | Chỉ cần chạy lệnh DELETE |
| **Retention** | Thời gian/phạm vi bắt buộc giữ | Cho phép giữ mọi bản mãi mãi |
| **Legal hold** | Nghĩa vụ tạm giữ dữ liệu phục vụ pháp lý/kiểm toán | Bỏ mọi chính sách bảo mật |
| **Tombstone** | Marker/logical state ngăn bản cũ sống lại | Đã hết nhiệm vụ, xóa ngay được |
| **Fencing** | Ngăn writers/leader cũ tiếp tục nhận authority | Chỉ đổi DNS là xong |

### 3.1. “Đã xóa” là nhiều lớp

~~~text
Application: dữ liệu không còn được hiển thị
Database API: DELETE được xác nhận
Replica set: các replicas đã nhận/apply thay đổi
Storage engine: tombstone/obsolete files được reclaim
Backups: retention/deletion policy được áp
External copies: cache/search/analytics/blob/exports được xử lý
Credentials: client không còn quyền đọc/ghi nguồn cũ
~~~

Một yêu cầu compliance về “data erasure” có thể khác thao tác xóa namespace của DB; phải định nghĩa rõ **scope và tiêu chí kiểm chứng**.

### 3.2. Dọn dẹp không nhất thiết đồng nghĩa phá hủy ngay

Đúng thứ tự thường là:

~~~text
Đánh dấu không còn authoritative
  -> chặn writers
  -> lưu giữ artifacts cần thiết
  -> chứng minh không còn phụ thuộc
  -> thực hiện deletion có giới hạn
  -> xác nhận physical/resource cleanup
  -> lưu bằng chứng/audit
~~~

Đối với từng loại tài sản, các bước có thể khác; nhưng **nghĩa vụ chứng minh** trước khi xóa vẫn cần.

## 4. Nguồn chuẩn và cutover epoch

Đầu tiên phải xác định **sau cutover, ai có quyền chấp nhận write?**

### 4.1. Một write authority tại một thời điểm

Một pattern an toàn cho domain cần strict ordering:

~~~text
Before epoch E42:
  authoritative source = LEGACY

At controlled cutover:
  stop/admit-drain writes as required
  reconcile last committed legacy position L0
  activate NEW as authority
  increment authority epoch to E43

After epoch E43:
  authoritative source = NEW
  legacy refuses all business writes
~~~

Nếu hệ chủ ý active-active, sẽ cần conflict/merge authority protocol khác. Không tự gán “old is retired” khi vẫn có clients viết về old store.

### 4.2. Dual-write phải được kết thúc có điều kiện

Dual-write hữu ích khi migration nhưng tạo nhiều failure modes:

~~~text
Write to new succeeds.
Write to old times out but actually committed.
Application retry duplicates a side effect.
```

Trước khi dừng dual-write và xóa old data, cần biết:

- Protocol/order của hai writes.
- Kết quả các writes unknown/out-of-order.
- Idempotency keys/operation IDs có được giữ.
- Backfill và reconciliation đã xác minh.
- CDC/change replay đã bắt kịp một boundary rõ ràng.
- Không có standby jobs dựa vào old write acknowledgements.

### 4.3. Epoch/fence ngăn ghost writes

Một client Java còn chạy build cũ có thể kết nối tới legacy store qua connection pool không bị đổi khi DNS cutover. Chỉ xóa record cũ mà vẫn cho legacy writes sẽ làm dữ liệu mới **tái xuất hiện trong old** hoặc phát sinh divergent branches.

Giải pháp tùy engine:

- Revoke write role của client cũ.
- Drop inbound routes/deny legacy write service ở network tier.
- Rotate/change endpoint và fencing token.
- Disable old connector/producers sau checkpoint.
- Thêm generation/authority version check ở business layer.
- Quan sát metrics về any attempted legacy write.

### 4.4. Write ban đầu có unknown outcome

Nếu client timeout lúc cutover, write có thể đã commit vào legacy trước fence. Cần `operationId` và nguồn log/idempotency ledger để reconcile **đầy đủ các operations đã được nhận**. Không tự giả định tất cả timeout đều thất bại.

### 4.5. Read traffic cũng cần xác minh

Chặn writes thôi chưa đủ. Một report job chạy mỗi cuối quý có thể vẫn đọc source cũ. Phải inventory:

~~~text
online API reads
scheduled batch/exports
ad-hoc analytics/reporting
fraud/compliance tooling
search indexing
CDC connectors
backups
on-call/admin scripts
regional/tenant-specific clients
```

Không kết luận “0 reads” từ 24 giờ metrics nếu job chỉ chạy hàng tháng.

## 5. Phân loại tài sản trước khi quyết định giữ/xóa

Đừng bắt đầu bằng `DROP DATABASE`. Hãy tạo **inventory map** có owner và phương án cho từng thành phần:

| Nhóm | Ví dụ | Quyết định có thể phù hợp |
| --- | --- | --- |
| Data nguồn | Legacy Orders/OrderItems | Quarantine rồi delete sau gates |
| Data authoritative mới | New Orders database | **Giữ, bảo vệ backup/PITR** |
| Change history | WAL/oplog/CDC segments | Giữ theo rollback/replay/retention |
| Idempotency/ledger | Payment keys, refund/audit events | Giữ theo bất biến và quy định |
| Delete/tombstones | Marker xóa, TTL metadata | Giữ đến khi replay/replicas an toàn |
| Backup snapshots | Full, incremental, PITR chains | Giữ phụ thuộc RPO/retention/legal hold |
| Archive bản đọc | Audit exports, immutable objects | Giữ có giới hạn và bảo mật |
| Secondary indexes | Old DB indexes | Có thể xóa cùng DB sau cutoff |
| Search indexes | Legacy OpenSearch index | Rebuild/cut alias trước deletion |
| Caches | Old Redis keys/namespaces | Namespace rotate rồi expire theo policy |
| Object files | Invoice/blob versions | Giữ theo DB references và retention |
| Queue/CDC | Broker topics, connector offsets | Drain/stop/checkpoint, retention |
| Config/security | IAM, secrets, allowlists, DNS | Thu hồi có kiểm chứng |
| IaC/automation | Helm/Terraform, jobs, pipelines | Xóa code/resource sau review |
| Runbooks/alerts | On-call guides, old dashboards | Cập nhật trước decommission |

### 5.1. Có ba kết quả rõ ràng cho từng asset

**KEEP:** còn authoritative, cần rollback hoặc có nghĩa vụ giữ.

**ARCHIVE:** không còn phục vụ live traffic nhưng cần giữ dạng truy xuất/khôi phục theo policy.

**DELETE:** đã hết phụ thuộc, đủ bằng chứng, ngoài retention/hold và có approval.

Một số assets có thể **REBUILD** thay vì KEEP, ví dụ search index được tạo lại từ source. Ghi rõ tool, thời gian và dependency để RTO không bị coi nhẹ.

### 5.2. Một bảng quyết định đi kèm lý do

~~~yaml
asset: "legacy-orders-collection"
assetType: "source-data"
owner: "order-platform"
authorityAfterCutover: false
activeReadersObserved: 0
activeWritersObserved: 0
verificationWindow: "covers normal + monthly jobs"
reconciliationEvidence: "run-2026-11-14"
rollbackWindowEnds: "date-from-approved-policy"
legalHold: false
backupManifestRef: "immutable-reference"
decision: "QUARANTINE"
nextGate: "explicit-delete-approval"
~~~

Đây là **record minh họa**, không phải một YAML để tool xóa dữ liệu. Trường `activeReadersObserved=0` chỉ có ý nghĩa khi **có nguồn quan sát và khoảng thời gian đủ bao phủ**.

## 6. Điều kiện tối thiểu trước khi xóa dữ liệu cũ

Một **deletion gate** có thể yêu cầu tất cả điều kiện sau:

1. **Cutover đã được chấp nhận:** Authority mới nhận writes theo contract; old source bị fence.
2. **Reconciliation complete:** Tập data và version/delete semantics trong target đạt tiêu chí đã ký duyệt.
3. **CDC/backfill complete:** Không còn missing/unknown change ranges cần replay.
4. **Đường đọc/ghi đã kiểm chứng:** Không còn clients hợp lệ cần legacy dataset.
5. **Rollback/forward recovery đã quyết định:** Rollback horizon qua, hoặc có phương án phục hồi bằng backup/log được chứng minh.
6. **Backup/retention:** Những bản cần giữ có manifest và restore rehearsal.
7. **Compliance/privacy:** Legal hold, retention và deletion obligations đã được áp.
8. **Dependencies:** Search, cache, reports, blob references, broker consumers, IAM và IaC đã chuyển.
9. **Change approval:** Scope, thời điểm, operator, reviewer, owner, blast radius rõ ràng.
10. **Verification and stop conditions:** Có dry-run, tiến độ, error budget và kế hoạch dừng.

Nếu một gate không đạt, trạng thái thường nên là **BLOCKED/QUARANTINED**, không tự đổi thành DELETED.

### 6.1. “Xóa được” không phải một điều kiện duy nhất

Quyết định có thể khác theo asset:

~~~text
Delete old search index?      Maybe, after alias cutover and rebuild proof.
Delete old source records?    Later, after reconciliation/rollback/retention.
Delete old KMS key?           Potentially much later; old backups may need it.
Delete old CDC offsets?       Only after no consumer/replay dependency.
Delete tombstones?            Let engine retention/compaction rules decide.
Delete old Terraform state?   No, may still manage other live resources.
~~~

### 6.2. Phân biệt deletion authorization với job credentials

Một service có `DELETE` permission **không chứng minh operator được phép xóa**. Quyền thực thi và quyền phê duyệt phải được quản lý riêng, nhất là với hành động irrecoverable.

## 7. Đối soát trước khi loại bỏ nguồn cũ

**Reconciliation** là cách chứng minh dữ liệu đích đủ và đúng sau migration. Một phép so sánh `COUNT(*)` hoặc đếm documents chỉ là một tín hiệu ban đầu.

### 7.1. Bốn cấp độ đối soát

**Cấp 1 — Coverage**

- Những collections/tables/tenant IDs/key ranges nào đã migrate?
- Có các documents/keys bất thường bị filter/skip?
- Có delete/tombstone và record TTL trong phạm vi không?
- Có nguồn dữ liệu hoặc region bị bỏ sót?

**Cấp 2 — Identity và version**

- Key identity có giống hoặc có mapping xác định?
- Không có duplicate records do retries?
- Generation/version/ETag có mapping đúng?
- Partition/schema-key transformation có deterministic?

**Cấp 3 — Giá trị và invariants**

- Status, amount, timestamps, arrays, nulls, precision đúng?
- Payment ledger tổng hợp không lệch?
- Unique constraints và idempotency semantics được giữ?
- External invoice/blob references còn tồn tại?

**Cấp 4 — Hành vi vận hành**

- API reads/writes theo SLO và consistency policy?
- CDC/outbox/consumers không còn gap?
- Backup/PITR từ target restore được?
- Các nghiệp vụ batch, monthly closing, reconciliation jobs có chạy đúng?

### 7.2. “Đếm bằng nhau” vẫn có thể sai toàn bộ

Ví dụ legacy có 1.000 Orders, target cũng có 1.000; nhưng target thiếu 10 Orders và lại chứa 10 Orders đã delete. Counts bằng nhau, **dữ liệu không khớp**.

### 7.3. Phải so trên một boundary hợp lệ

Nếu source tiếp tục nhận writes trong lúc đối soát, so counts tại hai thời điểm khác nhau tạo false positives/negatives. Một thiết kế có thể dùng:

~~~text
Legacy committed cut: L5000
Migration/checkpoint:   applied through L5000
Target snapshot:        includes all effects through L5000
Reconciliation:         compare data state for same logical cut
~~~

Nếu dữ liệu có nhiều shards, log positions không đồng nhất; cần source-specific watermark/transaction consistency protocol thay vì một scalar L5000 giả.

### 7.4. So sánh có phân tầng

Để tránh full-scan quá tốn kém:

1. So counts per tenant/shard/day/status theo consistent cut.
2. So stable key sets/hashed partition ranges.
3. So canonicalized payload fingerprints khi semantics cho phép.
4. Lấy mẫu có trọng số theo business risk và edge cases.
5. Full compare cho payment/ledger/critical balances hoặc các invariant bắt buộc.

Không coi sample không có lỗi là chứng minh tuyệt đối không thiếu record. Độ tin cậy phải tương xứng hậu quả.

### 7.5. Canonicalization khi đổi schema

Nếu nguồn cũ dùng `priceDecimal=12.30`, hệ mới dùng `priceMinorUnits=1230`, so bytes JSON sẽ khác dù nghiệp vụ tương đương. Nên chuẩn hóa:

~~~text
Legacy document -> canonical business representation
New document    -> canonical business representation
Compare key identity + normalized payload + version meaning
~~~

Ví dụ với tiền tệ, dùng decimal/int minor units chính xác, **không dùng số thực binary không kiểm soát**.

### 7.6. Deletes và absence

Đối soát chỉ các keys có mặt không phát hiện target giữ record cũ đã delete tại source. Cần delete history/tombstone audit hoặc comparison of keysets ở cùng boundary. Với TTL, phải xác định thời điểm kiểm tra và expiration semantics.

### 7.7. Không xóa trước khi giải quyết mismatches

Một mismatch chưa giải thích ở khách hàng ít hoạt động vẫn có thể là dữ liệu quan trọng. Tạo bảng:

| Loại mismatch | Quyết định |
| --- | --- |
| Schema transform khác nhưng business equivalent | Ghi normalization rule và test |
| Missing target record | Re-copy/replay và verify |
| Target stale version | Causal/version check, catch-up |
| Target extra deleted record | Replay tombstone/version guard |
| Duplicate payment | Block deletion; reconcile domain ledger |
| Unknown source write outcome | Tra operation ID/commit log |

Không “sửa” bằng cách giảm phạm vi đối soát đến khi biểu đồ xanh.

## 8. Cửa sổ rollback và điều kiện đóng

**Rollback horizon** là khoảng còn có thể/quyết định quay lại nguồn cũ, dựa trên hợp đồng và cơ chế duy trì state.

### 8.1. Chỉ giữ database cũ không tự bảo đảm rollback

Giả sử cutover lúc D3, từ D3 tới D7 writes chỉ đi vào new store. Tới D7, legacy store vẫn có dữ liệu snapshot D3 nhưng thiếu bốn ngày orders mới. **Đổi DNS ngược về legacy không phải rollback an toàn**.

Rollback cần:

- Backward-sync từ new sang legacy, nếu có protocol hợp lệ.
- Replay log/events đầy đủ theo domain semantics.
- Reconcile writes, deletes, idempotency, conflicts.
- Kiểm tra phiên bản application/schema tương thích.
- Fencing new authority lúc quay lại.
- Xác nhận dữ liệu, traffic và SLO.

Nếu không có backward path, “giữ old cluster để rollback” có thể là một **giả định sai**; khi ấy cần forward recovery/restore plan khác.

### 8.2. Bảng các cấp độ khả năng quay lui

| Mức | Đường quay lui | Hạn chế |
| --- | --- | --- |
| L0 | Chuyển lại reads cũ, writes vẫn new | Không tương đương rollback toàn nghiệp vụ |
| L1 | Old database giữ current state bằng dual-write/CDC | Phụ thuộc consistency/conflict protocol |
| L2 | Restore legacy snapshot + replay new changes | Cần transform ngược và complete history |
| L3 | Chỉ giữ immutable archive để forensic/audit | Không phải rollback production nhanh |
| L4 | Không còn old data, chỉ forward-fix target | Cần quyết định và approval rõ |

### 8.3. Gate đóng rollback

Trước khi đóng, có thể yêu cầu:

1. Business owner đồng ý hoàn tất migration.
2. Đã chạy qua một chu kỳ nghiệp vụ đủ đại diện (ngày, tuần, tháng khi cần).
3. Không còn đối soát pending.
4. Production incidents liên quan migration đã giải quyết.
5. Target backups/PITR đã restore rehearsal.
6. Nếu mất target, recovery plan không dựa duy nhất vào old live store.
7. All critical clients và batch jobs đã dùng target.
8. Nghĩa vụ lưu bản dữ liệu cũ đã được phân loại.
9. Operations/security/compliance phê duyệt.

### 8.4. Cửa sổ rollback không đồng nghĩa retention

Rollback có thể kết thúc sau 14 ngày, còn audit retention cần nhiều năm. Khi đó có thể **giải thể live legacy cluster** nhưng giữ archive/backup phù hợp, thay vì trả chi phí live DB suốt nhiều năm.

### 8.5. Quá hạn rollback nhưng còn legal hold

Không được xóa record/archive nằm trong legal hold chỉ vì rollback đã kết thúc. Đồng thời legal hold không mặc nhiên cho phép dữ liệu được dùng cho mục đích khác; cần chính sách truy cập, bảo mật và thời điểm giải phóng hold.

## 9. Giữ bản sao nào: live copy, immutable archive, backup/PITR hay read model?

### 9.1. Live legacy copy

Giữ cluster cũ đang hoạt động có thể hữu ích cho troubleshooting ngắn hạn, nhưng kéo theo:

- License/compute/storage/network cost.
- Security patches, backup, monitoring.
- Rủi ro client ghi nhầm hoặc đọc sai.
- Vấn đề divergence so với source mới.

Đặt **read-only/quarantine và owner/end date**; nếu cần active backward sync, mô tả riêng tính đúng và chi phí.

### 9.2. Immutable archive

Archive phù hợp khi cần:

- Audit/forensics.
- Đáp ứng retention.
- Tra cứu dữ liệu lịch sử hiếm.
- Bằng chứng migration cutover.

Nhưng archive **không tự là database restore-ready**. Cần schema, serializer/version, manifest, checksums, indexes/catalog và retrieval procedure nếu mục tiêu có thể truy vấn sau nhiều năm.

### 9.3. Backup/PITR

Backup phục vụ khôi phục **source hệ mới** hoặc **legacy snapshot** theo recovery point. Nó đòi:

- Base và incremental/log chain liên tục.
- Khóa giải mã còn dùng được.
- Version compatibility.
- Restore test.
- Retention và failure-domain isolation.

Đừng chỉ giữ `.tar.gz` rồi hứa có thể mở lại cluster cũ.

### 9.4. Search/cache/read models

Nếu có thể tái dựng từ authoritative source, không nhất thiết lưu bản đầy đủ dài hạn. Nhưng cần:

- Mapping/index definitions.
- Rebuild job/version.
- Source watermark và replay window.
- Ước lượng thời gian RTO.

Nếu search index chứa manual annotations không có nguồn nào khác, nó **không phải dữ liệu có thể tái dựng hoàn toàn**.

### 9.5. Bản sao để đối soát

Một sample/manifest/hash set giúp chứng minh migration, nhưng **hashes không thay thế raw data cần khôi phục**. Nên giữ đúng mức tối thiểu phù hợp mục đích, tránh sao chép PII tùy tiện ra logs/spreadsheets.

## 10. Thiết kế retention policy theo mục đích

Một retention policy tốt có các dimension:

~~~text
Dataset/asset classification
Business owner
Purpose of retention
Legal/compliance basis
Start and end of retention clock
Legal hold exceptions
Backup/PITR dependency
Privacy deletion handling
Allowed access/region
Deletion method and evidence
```

### 10.1. Các retention clock khác nhau

- Tuổi business record (`createdAt`, `closedAt`).
- Ngày kết thúc hợp đồng.
- Ngày cutover migration.
- Ngày tạo snapshot/backup.
- Ngày kết thúc legal hold.
- Thời hạn log archive phục vụ PITR.

Không mặc định mọi asset “xóa sau 30 ngày kể từ migration”.

### 10.2. Ví dụ ma trận chính sách (không phải luật áp dụng)

| Asset | Mục đích | Đề xuất xử lý |
| --- | --- | --- |
| Legacy live Orders | Rollback ngắn hạn | Read-only, giữ tới gate đóng rollback |
| Immutable cutover snapshot | Audit migration | Giữ theo retention được phê duyệt |
| New DB full/PITR backups | Operational recovery | Theo RPO/RTO và chính sách backup |
| WAL/oplog archive cũ | Reconstruct boundary | Giữ đủ chain; expire đúng dependency |
| Payment ledger | Regulatory/accounting | Theo policy riêng, không theo Order cache |
| Temporary backfill files | Migration staging | Xóa sau reconciliation + no hold |
| Old Redis cache namespace | Derived data | Expire sau cutover/rollback gate |
| Personal data in exports | Dữ liệu nhạy cảm | Xóa/sửa quyền theo privacy policy |
| KMS keys for retained backup | Decryption dependency | Giữ khả năng giải mã tới khi backup hết hạn |

**Không suy các khoảng thời gian cụ thể từ bảng này.** Mốc retention phải do policy/nguồn pháp lý phù hợp phê duyệt.

### 10.3. Retention không chỉ là số ngày

Nếu incremental backup I5 cần full backup F1, xóa F1 vì “quá 30 ngày” sẽ làm I5 vô dụng. Expiration cần dependency graph:

~~~text
Active restore point
  -> required baseline
  -> log/incremental segments
  -> metadata/manifest
  -> encryption keys
  -> external object versions
~~~

### 10.4. Key destruction có thể làm bản backup vô dụng

Trước khi vô hiệu hóa một KMS key cũ, kiểm tra mọi backup/archive còn giữ có cần nó không. Nếu còn cần, hoặc re-encrypt/migrate keys theo quy trình hỗ trợ, hoặc giữ quyền decrypt được kiểm soát. Không sao chép plaintext key để “dễ giữ”.

### 10.5. Xóa để bảo vệ quyền riêng tư

Khi có valid deletion request, có thể cần xóa hoặc hạn chế sử dụng dữ liệu trên:

- Old live store.
- New live store.
- Search/index/analytics projections.
- Cache.
- Exports/archives/backups theo obligations và exceptions.
- CDC/broker retention.
- External blobs.

Với backup immutable, chính sách có thể dùng hạn lưu ngắn có kiểm soát, hạn chế truy cập, crypto-erasure khi phù hợp, và **reapply deletion ledger before reactivating restored data**. Cần tham vấn chính sách/pháp lý áp dụng; không khẳng định có một cơ chế duy nhất phù hợp mọi trường hợp.

### 10.6. Storage reclaim không luôn diễn ra ngay

NoSQL thường có snapshot/reference counting, compaction, tombstones và TTL sweeps. Một `DELETE` thành công không tự đồng nghĩa SSD/free space tăng ngay. Phải theo dõi logical deletes và physical bytes reclaimed **tách biệt**.

## 11. Archive manifest và bằng chứng lưu giữ

Một archive có thể được mô tả bằng:

~~~yaml
archiveId: "orders-legacy-epoch42"
sourceSystem: "legacy-orders-cluster"
sourceRegion: "region-a"
authorityEpoch: "E42"
snapshotCut:
  sourcePosition: "opaque-committed-position"
createdAtUtc: "2026-11-14T09:00:00Z"
datasets:
  - "orders"
  - "order_items"
  - "payment_idempotency"
representation:
  format: "engine-supported-export-or-snapshot"
  schemaBundle: "orders-schema-v4"
artifacts:
  - uri: "private-archive://orders/object-0001"
    sha256: "calculated-not-placeholder-in-real-manifest"
dependencies:
  logChainManifest: "chain-epoch42"
  encryptionKeyRef: "kms-private-ref"
  objectVersionCatalog: "invoice-object-versions"
retention:
  policyId: "approved-policy-reference"
  legalHold: false
  expiresAt: "approved-date-not-auto-guessed"
recovery:
  drillId: "restore-drill-2026-11-14"
  lastVerifiedAt: "2026-11-14T10:00:00Z"
ownership:
  dataOwner: "order-platform"
  securityApprover: "authorized-role"
~~~

**Đây là metadata minh họa**, không phải chứng nhận tính đúng của một bản archive thật. Mọi placeholder phải được điền và kiểm chứng. Không đưa bí mật/PII vào manifest public.

### 11.1. Source lineage giúp tránh backup nhầm

Một file `orders-backup.zip` không cho biết:

- Backup từ source cũ hay target mới?
- Epoch trước hay sau cutover?
- Được tạo trước hay sau cuối rollback?
- Còn đủ incremental/log changes không?
- Có đang bị legal hold không?

Manifest có source identity, cut/watermark và ownership giúp tránh restore nhầm hoặc xóa nhầm.

### 11.2. Restore thử, không chỉ checksum

SHA-256 khớp chứng minh bytes lưu không bị thay đổi ngoài kỳ vọng theo phạm vi hash, **không chứng minh semantic completeness**. Cần restore vào môi trường cách ly, kiểm tra schema, dữ liệu, deletes, object references, user roles và business invariants.

### 11.3. Không giữ vô hạn bản live chỉ vì sợ restore

Nếu archive/backup không restore được, giải pháp là **sửa và kiểm chứng năng lực backup**, không phải giữ cluster legacy vô hạn trong trạng thái không ai patch/monitor.

## 12. Thứ tự dọn dẹp: từ thay đổi dễ đảo ngược đến không thể đảo ngược

Một chiến lược nhiều giai đoạn:

~~~mermaid
flowchart TD
    A["Inventory & reconcile"] --> B["Fence old writes"]
    B --> C["Disable old reads/dependencies"]
    C --> D["Quarantine / read-only old resource"]
    D --> E["Preserve verified backup/archive"]
    E --> F{"Rollback/retention/compliance gates met?"}
    F -->|No| H["Keep with owner, expiry and monitoring"]
    F -->|Yes| G["Approve scoped deletion"]
    G --> I["Dry-run / bounded deletion"]
    I --> J["Verify deletion and no regressions"]
    J --> K["Reclaim infra, revoke access, close docs"]
~~~

Trong các hệ khác nhau, archive có thể phải được tạo **trước hoặc trong cutover**, không chỉ sau quarantine. Sơ đồ nhấn mạnh rằng trước thao tác phá hủy phải có *đủ dữ liệu giữ và đủ bằng chứng*.

### 12.1. Stage A — Chỉ dừng dùng legacy

- Chuyển readers/writers theo routing config.
- Tắt feature flags cũ khi rollout đầy đủ.
- Đánh dấu old database là **not authoritative**.
- Cập nhật dashboard để phát hiện client còn chạm old.

Đây thường là giai đoạn dễ phục hồi nhất, nhưng cần ngăn dual authority.

### 12.2. Stage B — Chặn writes tại nguồn

Ứng dụng không còn gửi writes chưa đủ; cần kiểm soát ở phía server/IAM/network:

~~~text
Old database client role: READ_ONLY or DISABLED
Old write API endpoint: fenced
Old producer/connector: stopped after checkpoint
Legacy write attempts: alarm, not silently ignored
~~~

Đặt cảnh báo cho attempts để tìm clients bị bỏ sót. Không tắt log visibility ngay khi cần theo dõi.

### 12.3. Stage C — Quarantine

Quarantine có thể:

- Giữ dataset read-only trong một account/VPC cách ly.
- Chặn public application routes.
- Bật audit khi có truy cập.
- Giữ backups và khóa giải mã theo retention.
- Gắn owner, chi phí, planned deletion date.

Không nhầm quarantine với một backup: một live cluster read-only vẫn có thể hỏng storage, mất credentials hoặc bị thay đổi bởi admin.

### 12.4. Stage D — Dọn phụ thuộc có thể tái dựng

Sau khi authority đã ổn định, có thể bắt đầu với **old cache namespaces, shadow-read jobs, old search aliases/indexes** theo runbook và rebuild proof. Không xóa old source data cùng lúc, để còn quan sát tác động độc lập.

### 12.5. Stage E — Xóa data và thu hồi tài nguyên

Chỉ sau đủ gate:

- Xóa một tập rõ ràng; không wildcards thiếu review.
- Dùng API/tool được engine hỗ trợ.
- Đặt rate/timeout/stop conditions.
- Kiểm chứng kết quả và chi phí/bytes reclaim.
- Thu hồi credentials, networks, compute, storage và monitoring cũ theo thứ tự.

### 12.6. Stage F — Đóng chương trình migration

Hoàn thiện:

- Data retention/erasure records.
- Backup recovery ownership.
- Updated architecture + runbooks.
- New alerts/SLO baselines.
- Handoff/on-call training.
- Final decommission change record.

## 13. Xóa chọn lọc và kiểm soát blast radius

Một thao tác xóa có thể là:

~~~text
Delete 200 expired trial sessions in one tenant.
Drop legacy search index after alias switch.
Delete one unused collection.
Delete a table.
Delete an entire cluster/account.
Destroy an encryption key used by retained backups.
~~~

**Phạm vi và khả năng phục hồi của từng thao tác khác nhau rất lớn**. Không đặt chúng cùng một loại change approval.

### 13.1. Đặt delete scope bất biến

Một plan nên có:

~~~yaml
planId: "cleanup-legacy-order-2026-11-14"
environment: "production"
sourceClusterId: "legacy-order-cluster-immutable-id"
targetNamespace: "orders_legacy_v1"
targetGeneration: "migration-epoch-42"
operation: "delete-approved-legacy-records"
eligibleFilter:
  migrationStatus: "VERIFIED"
  sourceAuthority: "NOT_AUTHORITATIVE"
  retentionExpiresBefore: "approved-cutoff"
expectedMaximumCount: 50000
batchSize: 100
mode: "DRY_RUN"
approvalRecord: "change-ticket-id"
rollbackEvidence: "verified-backup-manifest"
~~~

Đây là **mẫu quyết định**, không phải job có thể chạy trực tiếp. Trong production cần kiểm tra identity/namespace qua API, phân quyền và tool thực thi thật.

### 13.2. Không dùng filter quá rộng

Ví dụ không an toàn:

~~~javascript
// Anti-pattern: thiếu tenant, generation, retention guard.
db.orders.deleteMany({})
~~~

Một câu lệnh hợp lệ về cú pháp có thể là một **thảm họa nghiệp vụ**. Với môi trường production, tránh công cụ chạy một `deleteMany({})` nếu không có data-scope fence rõ.

### 13.3. Filter đủ chưa nếu dữ liệu vẫn thay đổi?

Giả sử dry-run đọc 50.000 keys, rồi trước lúc xóa có job ghi một key cùng prefix. Một deletion theo prefix ở thời điểm thực thi có thể xóa luôn key mới.

Giảm rủi ro bằng:

- **Snapshot danh sách IDs** đủ điều kiện tại consistent cut.
- Gắn generation/authority epoch.
- Conditional delete theo expected version/ETag khi API hỗ trợ.
- Ngăn writers vào namespace đang retire.
- Giới hạn số lượng xóa tối đa.
- Có audit of actual affected IDs/counts.

### 13.4. Kiểm tra trước, trong và sau mỗi batch

~~~text
PRE:
  approval valid
  cluster identity and environment match
  asset state QUARANTINED
  backup/retention gate valid
  expected set of IDs selected
  count <= approved limit

EACH BATCH:
  no new legacy writes
  data/source identity unchanged
  delete only approved IDs/versions
  rate/errors within budget
  checkpoint durable

POST:
  actual deletes matched approved scope
  remaining data matches retained set
  new source and business operations healthy
  audit record stored
~~~

### 13.5. Batch deletion vs drop

**Batch deletion** cho phép kiểm soát tốc độ và phạm vi, nhưng có thể tạo nhiều tombstones, WAL writes, index updates, replication traffic. **Drop collection/table/index** có thể giải phóng logical namespace nhanh hơn, nhưng có thể phá toàn bộ data trong scope và không có rollback ngoài restore.

Không mặc định batch deletion tốt hơn trong mọi engine; chọn theo product-native behavior, workload và business constraints.

### 13.6. Stop conditions

Một deletion job nên tự dừng khi:

- Nguồn/cluster ID khác plan.
- Có bất kỳ legacy write attempt mới chưa giải thích.
- Count so với dry-run lệch ngoài tolerance cho phép.
- Có key ngoài approved scope.
- Lỗi auth/consistency/conditional conflict.
- Source/target p99 hoặc error rate vượt threshold.
- Backup/restore evidence hết hiệu lực.
- Legal hold/retention flag đổi.
- Rate physical reclamation gây áp lực storage/compaction.

Không tiếp tục vì “đã xóa được 80% rồi” nếu guard bị vi phạm.

### 13.7. Idempotency khi retry deletion

Một batch có thể timeout sau khi xóa một phần. Không assume timeout nghĩa không xóa. Giữ **operation IDs, batch manifests, checkpoint và compare state** để retry an toàn. Xóa idempotent theo key có thể an toàn hơn, nhưng vẫn phải tính tombstone/TTL/history và audit.

### 13.8. Dry-run phải sử dụng cùng selector

Nếu dry-run filter khác production delete filter, số đếm không có giá trị. Đề xuất tạo cùng một **immutable selection artifact** (ID + expected version + generation) được review; execution chỉ duyệt artifact ấy.

### 13.9. Đừng chạy nhiều destructive changes cùng lúc

Ví dụ xóa old index, đổi CDC checkpoint và xóa legacy source cùng một deploy. Khi error xuất hiện không biết bước nào gây ra. Giãn change windows và tạo observation checkpoints, trừ trường hợp có transaction/coordination đặc thù yêu cầu thao tác nguyên tử.

## 14. Tombstones và compaction: “xóa” không chỉ là DELETE

Một số NoSQL hệ LSM như Cassandra/ScyllaDB lưu deletion markers (tombstones) nhằm ngăn bản cũ ở SSTables/replicas hồi sinh.

### 14.1. Timeline xóa trong một LSM store

~~~text
t0 Key K v10 nằm trong SSTable cũ.
t1 DELETE K v11 tạo tombstone.
t2 Query K trả absent theo visibility semantics.
t3 Tombstone được replicate/repair khi cần.
t4 Compaction/GC thu hồi obsolete data theo rules.
```

Một query không trả record sau t1 **không chứng minh disk bytes đã được reclaim tại t1**.

### 14.2. Xóa tombstones quá sớm nguy hiểm

Nếu replica A đã apply delete v11, replica B offline vẫn giữ v10; nếu A loại bỏ tombstone trước khi B đồng bộ/repair, v10 có nguy cơ được tái đưa vào hệ ở một số recovery/repair paths. Chọn GC grace/repair/retention settings đúng engine; không tự giảm thời gian xuống zero để giải phóng disk nhanh.

### 14.3. TTL expiration cũng tạo cleanup load

TTL của Cassandra/DynamoDB/Cosmos/Redis/MongoDB có semantics rất khác:

- “Hết hạn theo field” không nhất thiết là xóa ngay tức thì.
- Background expiration/TTL service có thể chạy chậm.
- Deletes có thể tạo tombstone hoặc replication work.
- Snapshots/backups còn giữ old versions.

Muốn bảo đảm **business không nhìn thấy dữ liệu hết hạn sau thời điểm X**, ứng dụng có thể cần filter theo `expiresAt` ở read path thay vì chờ physical TTL job.

### 14.4. Xóa hàng triệu rows từng key có thể phản tác dụng

Một broad mass delete trong wide-column store có thể làm:

- Tombstones tăng mạnh.
- Read amplification/scan latency tăng.
- Compaction pressure.
- Replication backlog.
- Disk free space chưa cải thiện ngay.

Trong một số cases, dropping entire legacy table hoặc TTL/partition rotation theo supported procedure có thể phù hợp hơn, **nhưng chỉ khi toàn bộ namespace đủ điều kiện xóa**.

### 14.5. Search index segment deletion

Elasticsearch/OpenSearch có segment merge/recovery behavior; xóa documents có thể làm tăng tombstone/deletion markers và không giải phóng disk ngay, trong khi **xóa toàn index** có semantics khác. Không ép force merge trên cluster đang bận chỉ để lấy lại bytes mà không đánh giá I/O/disk headroom.

### 14.6. Backup snapshots giữ files sống

Một file không còn được live DB sử dụng vẫn có thể được snapshot/incremental backup reference. Repository GC/storage snapshots phải biết **referenced artifacts**; xóa một file bị snapshot giữ có thể làm hỏng restore chain.

### 14.7. Storage reclaim chậm không đồng nghĩa delete thất bại

Đo độc lập:

~~~text
Logical selected/deleted count
Read visibility (should be absent)
Replication/tombstone apply
Compaction/GC progress
Storage bytes reclaimed
Backup repository retained bytes
```

Không tiếp tục chạy DELETE lặp vô hạn chỉ vì disk usage chưa giảm.

## 15. Giai đoạn shadow read, dual-write và CDC phải được đóng có thứ tự

### 15.1. Shadow reads

Một shadow read gọi legacy và target để đối soát nhưng chỉ trả target cho client. Trước khi tắt:

- Mismatch rate và error budget đã đạt tiêu chí?
- Có đủ test theo traffic shape/tenant/region?
- Có sensitive payload logging cần xóa/retention?
- Shadow query gây tải legacy còn được theo dõi?

Sau khi tắt, legacy read activity phải giảm, nhưng **không suy bằng zero ngay nếu có batch jobs**.

### 15.2. CDC pipeline

Trước khi xóa connector/offset state:

1. Ghi source committed high-water per stream/partition.
2. Xác nhận target đã apply/durable tới boundary.
3. Reconcile late events và deletes.
4. Dừng producer/connector theo procedure.
5. Chặn source writes mới hoặc có fencing.
6. Giữ offset/manifest theo retention/recovery need.
7. Xóa connector và backlog khi không còn replay dependency.

`consumer lag=0` một mình không chứng minh target đủ data nếu connector trước đó bỏ lỡ source events.

### 15.3. Dual-write

Nếu source cũ vẫn nhận writes qua dual-write tới gần lúc xóa, phải có **drain/fence/checkpoint**. Không xóa source trước khi biết mọi acknowledged writes đã phản ánh vào target.

### 15.4. Retry queue và dead-letter queue

Queues chứa messages lỗi đang chờ xử lý có thể là **business work chưa hoàn tất**. Trước khi purge:

- Xác định số messages, event IDs, outcomes.
- Replay/reconcile hoặc có quyết định loại bỏ được duyệt.
- Lưu evidence và dead-letter export nếu policy cần.
- Không purge chỉ vì “pipeline đã chuyển”.

### 15.5. Outbox/Inboxes

Outbox có event đã commit nhưng chưa publish; inbox/dedup stores có khóa chống duplicate payment. Khi xóa old DB, kiểm tra **đường idempotency mới** giữ được các operation IDs cần thiết. Xóa old dedup store quá sớm có thể biến retry thành double effect.

### 15.6. Reprocessing after cleanup

Nếu một bản archive được restore lại sau này, connector/event generation từ epoch cũ có thể phát events trùng. Dùng **recovery generation, namespace isolation, replay flags và idempotency policy**; không kết nối trực tiếp restored instance vào production broker trước khi kiểm soát side effects.

## 16. MongoDB: collections cũ, indexes, TTL, change streams và backups

Trong MongoDB, quá trình chuyển đổi có thể là đổi collection schema, di chuyển shard key, chuyển replica set/cluster hoặc đổi region. Dọn dẹp phải theo đúng **deployment topology và data ownership**.

### 16.1. `deleteMany` khác `drop`

- `deleteMany(filter)` xóa documents thỏa filter, có thể tiêu tốn nhiều write/index/log/replication operations.
- `drop` xóa toàn bộ collection và cấu trúc liên quan theo semantics sản phẩm.
- `dropIndexes` chỉ loại index được chỉ định, có thể làm query cũ chậm hoặc mất unique validation.
- `dropDatabase` có phạm vi rộng và rủi ro cao hơn nhiều.

Không sử dụng `drop` khi chỉ một tập tenants/records trong collection chung đủ điều kiện xóa.

### 16.2. Preview trước khi xóa

Ví dụ MongoDB shell ở **môi trường được cấp quyền**, chỉ đọc để kiểm tra:

~~~javascript
const scope = {
  migrationEpoch: "E42",
  state: "RETIRED",
  retentionHold: { $ne: true }
};

const sample = db.legacyOrders
  .find(scope, { _id: 1, version: 1, migrationEpoch: 1 })
  .limit(20)
  .toArray();

const plannedCount = db.legacyOrders.countDocuments(scope);
printjson({ plannedCount, sample });
~~~

Đây là **preview**, không phải authorization. Một filter thay đổi theo thời gian, counts có thể khác giữa preview và delete. Khi cần xóa records production, hãy chọn exact IDs/versions/generation, kiểm tra bằng dry-run manifest và conditional guards.

### 16.3. TTL index không phải hard deadline

MongoDB TTL deletion là background process; một expired document có thể còn tồn tại một khoảng trước khi bị xóa. Nếu nghiệp vụ không được phục vụ record sau `expiresAt`, read path cần quy tắc expiration phù hợp, không chỉ tin TTL index.

### 16.4. Oplog/change streams

Nếu connector downstream còn đọc change stream từ legacy, drop collection/delete có thể phát events/invalidation theo semantics tương ứng. Phải drain/stop connector với checkpoint trước khi thay đổi namespace. Một change stream không thay thế hoàn toàn archive/PITR nếu retention không đủ.

### 16.5. Snapshot/Atlas backup

Một collection đã drop có thể vẫn tồn tại trong snapshots theo retention. Xóa live collection không tự xóa mọi backup generations; ngược lại, xóa backup generation không tự giải phóng collection sống. Quản lý **backup lifecycle và recovery needs** riêng.

### 16.6. Sharded MongoDB

Xác định namespace có chunk migrations/resharding đang diễn ra không. Không tự copy/drop từ từng shard node để “dọn nhanh”, vì cluster metadata và distributed transactions có protocol riêng. Dùng cluster-aware operations và xác minh config server/routers/routing state.

### 16.7. User/role cleanup

Khi không còn client dùng legacy, revoke database role/credentials phù hợp. Nhưng nếu **backup restore drill** còn cần quyền read/decrypt từ archive, giữ recovery role riêng với audit; không reuse application write principal cũ.

## 17. Cassandra/ScyllaDB: tombstones, TTL, token ranges và snapshots

Trong wide-column NoSQL, xóa hàng loạt có thể tạo **tombstone/compaction pressure**. Đặc biệt nguy hiểm nếu coi ngay lập tức xóa cứng dữ liệu như hành vi của một row store đơn giản.

### 17.1. Data expiration theo TTL

Một cell/row hết TTL có thể được coi là expired trong read semantics trước khi storage bytes được reclaim. Tombstone/dropped SSTable cleanup tùy grace period/compaction và replica health.

### 17.2. Đừng hạ `gc_grace_seconds` tùy tiện

Thời gian giữ tombstone ảnh hưởng khả năng sửa divergence của replica từng offline. Hạ xuống không xét repair/decommission/outage duration có thể tăng nguy cơ **resurrect old data** trong một số failure scenarios. Cần chính sách repair/tombstone theo sản phẩm và topology thực tế.

### 17.3. Cần xác định token ranges

Một migration có thể chuyển keyspace/table hoặc datacenter. Đối soát và xóa cũ cần kiểm tra **mọi token ranges và replicas**, không chỉ query trên coordinator/local datacenter. Một node chứa snapshot files nhưng chưa đồng bộ vẫn có thể giữ bản cũ.

### 17.4. Table/keyspace `DROP` khác delete theo partition

Nếu cả bảng legacy không còn dùng, drop table theo quy trình chính thức có thể phù hợp. Nếu chỉ xóa một tenant trong bảng chung, drop table không phù hợp. Ngoài data, cần xem:

- Secondary indexes/materialized views.
- Schema agreement.
- Commit log/incremental backup.
- Snapshots giữ SSTables.
- Repair/rebuild jobs.
- Application queries/routing.

### 17.5. Snapshot lưu giữ bytes

SSTable snapshots có thể tham chiếu files qua hardlink/backup mechanism. Live table trống hoặc bị drop chưa chắc disk usage giảm theo kỳ vọng vì snapshot vẫn giữ files. Trước khi xóa snapshots, kiểm tra backup retention/restore chain và legal hold.

### 17.6. Compaction và clean-up

Compaction/cleanup operations có thể tiêu tốn disk I/O, network và temporary disk space. Không ép các tác vụ nặng lên toàn cluster đồng thời khi còn hot partitions hoặc đang repair.

### 17.7. ScyllaDB/managed variations

Commands, tombstone lifecycle, compaction modes và backup manager khác nhau theo version/distribution. Dùng **vendor-supported restore/decommission/snapshot cleanup** thay vì áp từng lệnh Cassandra lên mọi hệ tương tự.

## 18. Redis: cache namespace, key expiration, RDB/AOF và cluster slots

Redis có thể dùng làm **cache**, store phiên làm việc, queue hoặc state authoritative. Quyết định dọn phụ thuộc vai trò đó.

### 18.1. Nếu chỉ là cache dẫn xuất

Một pattern an toàn:

~~~text
Redis old namespace: order-cache:v1:*
Redis new namespace: order-cache:v2:*

Switch application reads/writes to v2.
Monitor requests to v1.
Keep v1 until rollback horizon/TTL policy.
Remove v1 with approved bounded cleanup.
```

Không tự `FLUSHALL` nếu Redis instance dùng chung nhiều services/tenants.

### 18.2. `DEL` và `UNLINK`

Trong Redis, `DEL` xóa keys theo command semantics; `UNLINK` có thể tách unlink khỏi quá trình memory reclaim ở background cho những workloads phù hợp. Nhưng cả hai vẫn thay đổi logical keyspace; **chọn key đúng mới là yêu cầu hàng đầu**.

### 18.3. `SCAN` thay vì `KEYS` trong large production datasets

Một quy trình cleanup theo namespace có thể dùng `SCAN` incremental để hạn chế công việc chặn server so với `KEYS` trên keyspace lớn. Tuy nhiên `SCAN` **không phải snapshot nhất quán** khi keys được thêm/xóa đồng thời; có thể trả trùng, miss các keys biến động và cần idempotent deletion. Trước khi cleanup hãy **fence writers tới namespace v1**, hoặc chạy pass xác minh lại với bound phù hợp.

### 18.4. Redis Cluster

Keys trải hash slots trên multiple primaries; một client chỉ scan một primary không bao quát toàn cluster. Dùng cluster-aware tooling/clients và xác nhận per-slot coverage, topology refresh và failover behavior.

### 18.5. RDB/AOF và memory

Xóa keys không tự làm những RDB backups cũ biến mất; AOF rewrite/persistence có lifecycle riêng. Nếu cần data erasure, xử lý active keyspace, persistence artifacts, backups, replicas, archived files theo policy và kiểm tra khả năng recovery.

### 18.6. Session/idempotency data không đơn giản là cache

Nếu Redis giữ dedup keys chống double payment trong 90 ngày, xóa sớm namespace cũ có thể khiến retries được xử lý lại. Phải xác định retention theo **business operation window**, không theo tên sản phẩm “Redis cache”.

## 19. DynamoDB: table retirement, TTL, PITR và Global Tables

DynamoDB là managed service, không cần vận hành raw storage replicas; nhưng **xóa table/index và thay đổi stream/global replication** là những thao tác lifecycle có tác động lớn.

### 19.1. Table cleanup

Trước khi delete table cũ:

- Xác nhận table ARN/name/region/account cụ thể.
- Liệt kê active clients, DynamoDB Streams consumers.
- Xác nhận PITR/on-demand backup và restore drill.
- Kiểm tra IAM, alarms, export jobs.
- Xác nhận Global Tables replication mode/members.
- Phê duyệt deletion.

Không đồng nhất `old-orders-prod` ở hai regions chỉ qua tên table.

### 19.2. TTL không xóa ngay

DynamoDB TTL deletion bất đồng bộ; expired item có thể tồn tại một thời gian. Nếu muốn business query không thấy expired record, cần filter/check điều kiện thời hạn tại application; TTL là cơ chế lifecycle hỗ trợ, **không phải SLA xóa đúng ngay vào một millisecond**.

### 19.3. TTL và streams

TTL delete có thể tạo stream records theo semantics/mode/region của table. Nếu downstream consumer dựa vào deletes, phải kiểm tra **events thực sự được cung cấp** trong hệ đang triển khai; không assume mọi region có metadata/behavior y hệt.

### 19.4. GSI cleanup

Xóa index cũ giảm chi phí nhưng có thể làm endpoint/report còn phụ thuộc index lỗi. Inventory query patterns, throughput/errors và cutover index access trước khi remove.

### 19.5. Global Tables

Nếu nhiều regions có cùng logical table, deleting/retiring one replica/table cần hiểu replication membership, consistency mode và failover policy. **Không coi một table ở Region B là bản backup độc lập** nếu writes/deletes từ Region A có thể được replicate sang B.

### 19.6. PITR và deletion

On-demand backups/PITR có retention và service settings riêng; xóa live table không chứng minh mọi backups đã hết hạn, và hủy backup artifact có thể phá khả năng restore. Đánh giá chính xác service capability/mode trước quyết định.

## 20. Cosmos DB for NoSQL: container, TTL, change feed và multi-region

Cosmos DB có **containers, logical partitions, RU/s, region settings, backup/restore mode và change feed**.

### 20.1. Container-level vs record-level cleanup

Nếu một legacy container chỉ chứa migration v1, có thể cân nhắc drop container sau gates. Nếu nó chứa dữ liệu của nhiều tenants/versions, cần scoped deletion có partition key guards.

### 20.2. Partition key quyết định phạm vi thao tác

Một delete theo `id` đơn lẻ có thể cần partition key theo API contract. Không scan rồi delete all records chỉ bởi document ID được coi là unique toàn account; identity/partition semantics phải chính xác.

### 20.3. TTL và RU

TTL expiration và nhiều deletes có thể tiêu thụ tài nguyên/throughput theo service semantics, ảnh hưởng queries của users. Đặt rate/monitor RU throttling, 429/retries và backoff phù hợp.

### 20.4. Change feed

Trước khi đóng source feed, lưu continuation/checkpoint positions và xác nhận target projection áp hết event cần thiết. Change feed modes có coverage/deletes/retention khác nhau; **không coi mọi mode là audit log đầy đủ**.

### 20.5. Multi-region và backup mode

Sao lưu/restore container/account có phạm vi khác nhau theo backup mode, API, region; việc xóa một container có thể replicate theo cơ chế dịch vụ. Không nhầm multi-region replication với immutable historical backup.

## 21. Elasticsearch/OpenSearch: index aliases, templates và data streams

Trong search NoSQL, cutover phổ biến qua **alias** từ index v1 sang v2:

~~~text
orders-read alias
  old: orders-v1
  new: orders-v2

Read/write clients should use approved aliases.
```

### 21.1. Chuyển alias chưa cho phép xóa index

Sau alias switch, xác minh:

- Search queries/pagination/business filters.
- Ingest pipelines và write alias behavior.
- Data freshness/backfill completed.
- Consumers/callbacks còn gọi index name `orders-v1`?
- Snapshots/backup retention.
- Index templates/ILM policy và alerts.
- Rebuild path nếu cần.

### 21.2. Xóa index khác xóa documents

Xóa toàn index có semantics nhanh và rộng hơn xóa từng document; có thể làm queries trực tiếp tới tên index cũ lỗi tức thì. Xóa documents hàng loạt có thể tạo segment merge/storage pressure. Chọn theo scope và product-native lifecycle/ILM.

### 21.3. Search PIT/scroll contexts

Một số clients giữ Point-In-Time/search contexts hoặc scroll handles; xóa index khi các jobs còn chạy có thể gây lỗi hoặc kết quả không nhất quán. Đặt observation window bao phủ batch/reporting.

### 21.4. Snapshot repo và feature states

Search snapshots có thể giữ index data, templates/aliases/feature states tùy API/config. Khi cleanup, giữ **repository compatibility, manifest và restore drill** trước khi drop legacy index. Một index bị drop vẫn có thể tồn tại trong snapshot retention.

### 21.5. Derived index vs authoritative annotation

Nếu index v1 có manual moderation tags không còn ở source, nó **không thuần là derived data**. Trước khi xóa, phải migrate/backup tags hoặc quyết định có phê duyệt về data loss.

## 22. Không xóa nhầm tài nguyên infrastructure

Migration thường tạo tạm:

~~~text
Old VPC/security group/network endpoint
Old service account/IAM role
Old KMS key
Old bucket + backup repository
Temporary backfill workers and queues
Old secret/config map
Old metrics dashboards and alerts
Old Terraform/Helm resources
```

### 22.1. Resource dependency graph

~~~mermaid
flowchart TD
    APP["Java Order API"] --> NEW["New NoSQL"]
    CDC["Legacy CDC job"] --> OLD["Legacy NoSQL"]
    BAK["Retained backup"] --> KEY["KMS key"]
    BAK --> OBJ["Object storage"]
    REP["Restore procedure"] --> BAK
    REP --> KEY
    API["Legacy private endpoint"] --> OLD
~~~

Muốn xóa `KEY` phải kiểm tra `BAK`/restore còn cần. Muốn xóa `OLD` phải xem CDC/legacy endpoint; sau khi xóa `OLD`, còn cần xóa **IAM/network/secret drift** nhưng không phá backup access.

### 22.2. Terraform/Infrastructure-as-Code

Không chạy một `terraform destroy` rộng trên workspace chứa cả resources mới chỉ để dọn old cluster. Đọc plan đã được review, xác minh resource IDs, state ownership, dependencies và backup retention. Xóa IaC definitions phải phối hợp actual resource deletion để tránh **orphan resources** hoặc unintended recreation.

### 22.3. Secret/key rotation

Sau khi legacy clients dừng, revoke application write secrets. Nhưng encryption keys cho archives/backups có thể phải giữ lâu hơn. Phân biệt:

- Application access credential.
- Backup read/decrypt role.
- KMS key material/reference.
- Service-to-service certificates.
- Emergency restore access.

### 22.4. DNS và network routes

Đừng xoá một DNS name được client cũ dùng mà không có detection window; có thể gặp client hard-coded host gây outage hoặc kết nối sai. Chặn write authority trước, sau đó sunset aliases/routes với monitoring và documentation.

### 22.5. Phân biệt chi phí và an toàn

Live cluster shutdown thường tiết kiệm compute nhanh. Backup/archival có thể giữ storage nhỏ hơn nhưng còn chi phí truy xuất/KMS. Tính **total cost of ownership** cùng rủi ro phục hồi; không phá retained backup vì vài ngày chi phí object storage.

## 23. Java: xây deletion gate theo nguyên tắc fail-closed

Trong một ứng dụng Java, nên **tách code quyết định có được xóa khỏi code gọi database DELETE**. Bằng cách đó, một lỗi phân loại trạng thái không vô tình biến thành thao tác xóa hàng loạt.

### 23.1. Dữ liệu của change plan

Ví dụ Java 17:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public final class CleanupModel {
    public enum Mode {
        DRY_RUN,
        EXECUTE
    }

    public record Candidate(
        String tenantId,
        String id,
        String generation,
        long expectedVersion
    ) {
        public Candidate {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(id);
            Objects.requireNonNull(generation);
            if (tenantId.isBlank() || id.isBlank() || generation.isBlank()) {
                throw new IllegalArgumentException("Blank identity field");
            }
            if (expectedVersion < 0) {
                throw new IllegalArgumentException("Invalid version");
            }
        }
    }

    public record Approval(
        String changeId,
        String sourceClusterId,
        String approvedNamespace,
        String approvedGeneration,
        Instant expiresAt,
        int maxRecords,
        boolean rollbackClosed,
        boolean reconciliationPassed,
        boolean restoreVerified,
        boolean legalHoldPresent
    ) {}

    public record LiveGate(
        String sourceClusterId,
        boolean oldWriteAuthorityDisabled,
        boolean dependenciesDrained,
        boolean backupStillRestorable,
        boolean newWritesToOldDetected
    ) {}

    public record Plan(
        Approval approval,
        String namespace,
        List<Candidate> candidates
    ) {
        public Plan {
            Objects.requireNonNull(approval);
            Objects.requireNonNull(namespace);
            candidates = List.copyOf(candidates);
        }
    }
}
~~~

`Plan` chứa tập candidates cố định. Với production, nên lưu **immutable approved selection manifest**, có chữ ký/hash hoặc store versioning để chứng minh không bị sửa giữa dry-run và execute. `tenantId`, `id`, `generation` phải cùng business identity/partition key của dữ liệu thực, không tự suy unique toàn cluster.

### 23.2. Preflight kiểm tra nhiều điều kiện

~~~java
import java.time.Instant;

public final class CleanupGate {
    private CleanupGate() {}

    public static void check(
        CleanupModel.Plan plan,
        CleanupModel.LiveGate live,
        Instant now
    ) {
        var a = plan.approval();

        require(a != null, "No approval");
        require(a.changeId() != null && !a.changeId().isBlank(),
                "Missing change ID");
        require(a.sourceClusterId().equals(live.sourceClusterId()),
                "Wrong cluster identity");
        require(a.approvedNamespace().equals(plan.namespace()),
                "Namespace not approved");
        require(a.maxRecords() > 0, "Invalid approved maximum");
        require(plan.candidates().size() <= a.maxRecords(),
                "Candidate count exceeds approval");
        require(now.isBefore(a.expiresAt()),
                "Approval expired");

        require(a.rollbackClosed(), "Rollback window still active");
        require(a.reconciliationPassed(), "Reconciliation incomplete");
        require(a.restoreVerified(), "No verified recovery copy");
        require(!a.legalHoldPresent(), "Legal hold present");

        require(live.oldWriteAuthorityDisabled(),
                "Legacy still accepts writes");
        require(live.dependenciesDrained(),
                "Readers/CDC dependencies remain");
        require(live.backupStillRestorable(),
                "Retained backup unavailable");
        require(!live.newWritesToOldDetected(),
                "Unexpected legacy writes detected");

        for (var c : plan.candidates()) {
            require(a.approvedGeneration().equals(c.generation()),
                    "Candidate generation differs from approval");
        }
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new IllegalStateException("CLEANUP BLOCKED: " + message);
        }
    }
}
~~~

**Chú ý về kiểm tra thời điểm:** Code trên minh họa ý tưởng. Trong hệ thật, `now` phải do trusted clock/source cung cấp; approval/retention/hold không thể chỉ là booleans do client tự gửi. Nguồn chính sách phải được truy vấn lại hoặc có **signed short-lived authorization token** và cơ chế thu hồi phù hợp.

### 23.3. `DRY_RUN` là mặc định

Một dispatcher có thể:

~~~java
public interface ConditionalLegacyStore {
    // Returns true only if a record with this exact identity/version
    // was deleted atomically under the database's documented semantics.
    boolean deleteIfVersionMatches(
        CleanupModel.Candidate candidate
    );
}

public interface LiveGateSource {
    CleanupModel.LiveGate currentGate();
}

public final class CleanupRunner {
    public static int run(
        CleanupModel.Plan plan,
        CleanupModel.Mode mode,
        LiveGateSource gates,
        ConditionalLegacyStore store
    ) {
        CleanupGate.check(
            plan, gates.currentGate(), java.time.Instant.now()
        );

        if (mode == CleanupModel.Mode.DRY_RUN) {
            return 0; // No DB mutations.
        }

        // An actual system also verifies a signed dry-run digest and
        // a separate execute authorization before reaching this branch.
        int deleted = 0;
        for (var candidate : plan.candidates()) {
            CleanupGate.check(
                plan, gates.currentGate(), java.time.Instant.now()
            );
            if (!store.deleteIfVersionMatches(candidate)) {
                throw new IllegalStateException(
                    "Conditional deletion failed for approved candidate"
                );
            }
            deleted++;
        }
        return deleted;
    }
}
~~~

Đây là **mô hình giáo dục** có các điểm còn cần hoàn thiện trước production:

- Không có signed selection digest, authorization service, retention policy source thực.
- Không có durable batch checkpoint/audit writer.
- Không bảo đảm transaction atomic trên toàn candidate list.
- Một process crash có thể khiến batch đã xóa một phần.
- `deleteIfVersionMatches` phải được triển khai bằng atomic conditional delete đúng engine, không phải “GET rồi DELETE” rời rạc.
- Không phân biệt record đã xóa trước đó và conditional conflict; production cần outcome classification/idempotency.
- Chưa có rate-limit, retries, metrics, error/latency SLO gates hay shutdown cancellation.
- Không tự xác minh toàn bộ source cluster vừa bị fence bởi một flag nếu có multiple writers/regions.

**Không triển khai và chạy trực tiếp một đoạn ví dụ vào dữ liệu production.** Nó minh họa nguyên tắc `DRY_RUN` + fail-closed + per-record/version scope.

### 23.4. Vì sao cần conditional delete thay vì read-then-delete?

Một lịch race:

~~~text
t0 Cleanup reads O900 version 18, marked RETIRED.
t1 Unexpected writer changes O900 to version 19.
t2 Cleanup deletes O900 by ID without version check.
~~~

Khi đó job xóa một giá trị **khác** với giá trị đã duyệt. Một atomic conditional delete có thể từ chối nếu version/generation thay đổi. Cần đi kèm **fencing writers**, vì CAS đơn lẻ không đảm bảo business policy toàn hệ.

### 23.5. Resume sau crash

Một deletion job cần ghi:

~~~text
planId
approved candidates manifest version
batchId
checkpoint of completed identities
last successful conditional delete
failures/conflicts
source region/cluster identity
audit timestamp
```

Sau restart, chỉ retry những candidates chưa có successful confirmed outcome hoặc đã kiểm tra state theo idempotency contract; không thay selector và mở rộng scope.

### 23.6. Không đưa PII vào audit mặc định

Log có thể ghi `hashedKey`, tenant partition/region tổng hợp, count, plan ID, outcome và error class. Nếu cần giữ identity để phục vụ pháp lý, dùng store audit riêng với encryption/limited access và thời hạn lưu phù hợp.

## 24. Đo lường sau cutover và trong cleanup

Một dashboard cleanup nên nối **di chuyển**, **an toàn xóa** và **sức khỏe hệ mới**:

| Nhóm | Metric/tín hiệu | Mục đích |
| --- | --- | --- |
| Legacy access | Reads/writes by client identity, region, app version | Phát hiện phụ thuộc còn sót |
| Authority | Old write ACKs, fencing rejection counts | Ngăn split authority |
| Reconciliation | Mismatch count, key coverage, missing deletes | Chứng minh data đủ |
| CDC | Source high-water, target applied high-water, DLQ count | Chứng minh không gap |
| Target | p95/p99/errors/throttles | Không gây ảnh hưởng khi cleanup |
| Backups | Last verified restore, archive chain coverage | Không xóa mất đường recovery |
| Retention | Assets due, legal holds, policy exceptions | Không vi phạm lưu giữ/xóa |
| Delete plan | Selected/approved/attempted/deleted/conflicted counts | Audit scope và dừng khi lệch |
| Storage | Tombstones, compaction, free bytes | Theo dõi physical reclamation |
| Operations | Stale alerts, decommissioned endpoints | Tránh monitoring sai sau migration |

### 24.1. Chú ý cardinality

Không đưa raw order IDs/PII vào metric labels; dùng `dataset`, `region`, `clientVersion`, `operationType`, `planId` nếu cardinality chấp nhận được. Per-record details nên ở một audit store có quyền hạn và retention riêng.

### 24.2. Window đo đủ dài

Một service có job cuối tháng sẽ không xuất hiện nếu chỉ xem 48 giờ traffic. Kết hợp:

- Service ownership/dependency inventory.
- IaC/config search thuộc hệ công ty.
- Network/database access logs.
- Scheduled job registry.
- On-call/admin script review.
- Periodic traffic observation.

Tối thiểu window phải bao phủ các chu kỳ nghiệp vụ **đã biết**; không có metric nào chứng minh tuyệt đối không tồn tại client ẩn.

### 24.3. Cảnh báo đáng giữ trong cleanup

- Any unexpected legacy write attempt.
- Stale reader discovered after deprecation.
- Reconciliation mismatch growth.
- DLQ backlog/CDC gap.
- Delete actual count > approved count.
- Target error/p99 regression.
- Restore drill/backup evidence expired.
- Legal hold issued after plan creation.
- Storage pressure/compaction spike.

### 24.4. Cảnh báo cần loại sau decommission

Alerts theo old instance CPU, old replica lag và obsolete endpoints có thể tạo noise. Nhưng **không xóa các alarms cần để phát hiện backup archive corruption/retention violations**. Chuyển ownership từ legacy ops sang recovery/archive ops khi phù hợp.

## 25. Cập nhật tài liệu vận hành: không phải một bước phụ

Tài liệu vận hành có thể tạo ra lỗi dữ liệu nếu nó sai. Ví dụ runbook ghi “Khi lỗi checkout, chạy lại sync từ legacy” sau khi legacy bị quarantine; một kỹ sư làm theo có thể overwrite Orders trong source mới bằng trạng thái cũ.

### 25.1. Tài liệu phải sửa ít nhất những gì?

1. **Sơ đồ kiến trúc/data flow** sau cutover.
2. **Source-of-truth/authority policy** cho từng domain.
3. **API endpoints và driver connection/discovery**.
4. **Schema/partition key/index design**, storage/retention policies.
5. **Read/write consistency/transaction/idempotency semantics**.
6. **Backup/PITR, archive, restore và RPO/RTO**.
7. **On-call runbooks** cho timeouts, stale reads, hot partitions, node/region outages.
8. **Alert/dashboard ownership** và target SLO baselines.
9. **CDC/outbox/queues** mới, offsets/replay/DLQ procedures.
10. **IAM/keys/network/IaC** và emergency access.
11. **Migration cleanup change history**, mốc archive/delete và cách tra cứu evidence.
12. **Rollback/forward recovery decision** sau khi đóng legacy.

### 25.2. Một sơ đồ “trước/sau” cần hiển thị authority

~~~mermaid
flowchart LR
    U["User"] --> API["Java Order API"]
    API --> NEW["New NoSQL: authoritative Orders"]
    NEW --> CDC["New CDC / Outbox"]
    CDC --> SEARCH["Search read model"]
    API --> CACHE["Redis cache v2"]
    OLD["Legacy DB"] -. "quarantined, no writes" .-> ARC["Retained archive"]
~~~

Không chỉ đổi hình logo database; phải chỉ rõ **nơi dữ liệu chuẩn**, connector paths và systems có thể tiếp tục tồn tại.

### 25.3. ADR: Architecture Decision Record

Một ADR hữu ích:

~~~markdown
# ADR: Retire Legacy Orders Store

## Context
Migration from legacy key schema to new NoSQL authority.

## Decision
New Orders DB is authoritative from approved epoch E43.
Legacy store is fenced/quarantined, then decommissioned by gates.

## Reasons
Reconciliation successful, consistency and SLOs accepted,
target PITR restore rehearsed, all known clients migrated.

## Consequences
No direct rollback to legacy without replay/repair.
Old archives retained under policy and isolated access.

## Rollout and safety
Per-region proof, conditional deletion, stop conditions,
owner and on-call escalation.

## Evidence
Links to reconciliation, restore drill, approvals and deletion manifest.
~~~

Đoạn này là **template**, không phải ADR đã được ký duyệt.

### 25.4. Changelog cho vận hành

Ghi mốc:

~~~text
Cutover authorized at epoch E43.
Legacy writes fenced.
Last CDC applied position per shard.
All known readers migrated.
Restore drill passed at approved source cut.
Legacy archive manifest published.
Rollback window formally closed.
Deletion approved/executed in batches.
Legacy IAM/endpoint retired.
On-call ownership moved to new platform team.
```

Một tài liệu vừa nói “đã xóa legacy” vừa có lệnh “khôi phục từ legacy host” mà không ghi về archive là inconsistency nguy hiểm.

### 25.5. Documentation-as-code

Giữ sơ đồ, runbooks, ADR và các config examples trong version control với review/change ticket. Có thể tự động kiểm tra links/hostnames/owner references trong pipeline, nhưng không xem grep không thấy tên legacy là bằng chứng mọi client đã chuyển.

### 25.6. Đào tạo on-call

On-call cần có drill:

- Tìm authoritative source hiện tại.
- Xem freshness/CDC backlog.
- Khôi phục từ target backup/PITR.
- Tra old archive chỉ khi được phép.
- Xử lý write timeout/duplicate idempotency.
- Dừng cleanup job khi gate fail.

Không giao tài liệu mới mà chưa kiểm tra người trực có thể dùng trong incident thực tế.

## 26. Runbook: dọn dẹp sau migration NoSQL

Runbook sau dành cho **người được phê duyệt vận hành**, không phải tập lệnh để chạy tự động trên production. Các lệnh cụ thể phải lấy từ procedure của engine và môi trường thật.

### Bước 1 — Mở change record và xác định phạm vi

Điền:

~~~text
Change ID / operator / reviewer / owner
Legacy cluster immutable identity / account / region
Target namespace and source generation
Dataset classification and retention policy
Rollback policy and close decision
Specific objects/IDs/table names to remove
Maximum affected records/bytes/resources
Scheduled window and communication channels
Stop conditions and escalation contacts
~~~

Không bắt đầu nếu plan chỉ ghi “xóa dữ liệu cũ” mà không xác định **đúng cluster, namespace, generation và owner**.

### Bước 2 — Kiểm tra source authority và fencing

- New DB được công bố authoritative cho reads/writes.
- Old DB bị vô hiệu hóa quyền ghi cho mọi client thường.
- Application deployments/region traffic maps hoàn tất.
- Không còn unmatched writes, unknown outcomes.
- Old write attempts có cảnh báo.

Nếu phát hiện một writer ngoài dự kiến, **dừng cleanup** và xử lý nguồn divergence.

### Bước 3 — Chốt đối soát dữ liệu

- Baseline count/key coverage per tenant/shard.
- Version/generation mapping.
- Deletes/tombstones/TTL states.
- Business invariant checks.
- Outbox/CDC completion and DLQ.
- External object references.
- Reconciliation evidence lưu bền và có owner.

Chưa đạt threshold cho dữ liệu critical thì không xóa legacy để che mismatch.

### Bước 4 — Kiểm tra retained copies

- Legacy backup/archive có manifest và correct source cut.
- Incremental/log chain liên tục, key/permissions còn.
- Restore drill từ đúng artifacts đã chạy.
- RPO/RTO mới được đánh giá.
- Backup repository/region độc lập đúng threat model.
- Retention/hold exceptions đã được xác minh.

Không xóa live legacy vì “đã có file zip” chưa từng restore.

### Bước 5 — Xác nhận dependencies

| Thành phần | Câu hỏi |
| --- | --- |
| Java API | Mọi replicas/regions đã dùng new source? |
| Batch jobs | Last run và next run đã thử trên new? |
| Analytics | Báo cáo quý/tháng còn dùng old? |
| Search | Read alias/index/ingest đã chuyển? |
| Cache | Namespaces v1/v2 có tách? |
| Broker/CDC | Consumer offsets/backlog/DLQ còn cần? |
| Object storage | Reference versions còn đủ? |
| Backup pipeline | Old archive artifacts có cần engine/KMS? |
| IAM/Network | Legacy credentials/routes đã inventoried? |
| On-call | Runbook đã chỉ target mới? |

### Bước 6 — Quarantine có quan sát

Đưa old source sang read-only/restricted state, cảnh báo unexpected access, quan sát tối thiểu qua chu kỳ workload được chấp nhận. Không chọn bừa 24 giờ nếu có job tháng.

### Bước 7 — Dry-run và duyệt selection

- Dùng selector cố định gắn generation/tenant/partition.
- In candidate count, sample IDs/versions theo quyền phù hợp.
- So against approved maximum.
- Lưu immutable selection manifest.
- Hai vai trò độc lập kiểm tra nếu policy yêu cầu.
- Xác nhận legal hold không xuất hiện sau lần duyệt trước.

### Bước 8 — Xóa theo stage/batch

Chỉ thực thi qua tool giới hạn scope, default dry-run, có chính sách:

~~~text
max records per batch
batch count checkpoint
per-request timeout
rate limit
conditional version/ETag guard
retry budget
monitoring interval
stop on unexpected delete/lag/hold
```

Không tự chuyển sang `drop database` nếu batch deletion chậm; đó là một change scope khác.

### Bước 9 — Verify hậu xóa

- Đúng keys/namespace đã được xóa, không ảnh hưởng retained data.
- Old writes vẫn bị fence.
- New source API p95/p99, error, consistency metrics ổn.
- No CDC corruption/gap or reprocessing.
- Tombstone/compaction/snapshot storage behavior như kỳ vọng.
- Kết quả audit và actual affected counts được lưu.

### Bước 10 — Thu hồi infrastructure và quyền

- Tắt resources cũ theo dependency graph.
- Revoke old app secrets/roles.
- Retain keys/permissions cần cho backup.
- Xóa obsolete services, dashboards, DNS, routes, IaC references theo approved plan.
- Không đụng immutable archives và production target resources.

### Bước 11 — Cập nhật documentation và handoff

Architecture, ADR, SOP, alert dashboard, backup restore, IAM/on-call owners, incident drills và cost allocation. Chốt change record với **evidence** chứ không chỉ một checkbox.

### Bước 12 — Theo dõi sau decommission

Một số lỗi chỉ xuất hiện khi job theo lịch chạy lại. Duy trì các alerts về attempted legacy access, inconsistent business outcomes, missing reports và restore/archive availability theo observation window đã phê duyệt.

## 27. Ma trận kiểm thử trước khi dọn sạch nguồn

| Thí nghiệm | Điều gây lỗi / kiểm tra | Bằng chứng mong muốn |
| --- | --- | --- |
| Legacy write attempt | Client cũ cố ghi sau fence | Bị từ chối và có alarm |
| Legacy read attempt | Job còn đọc old source | Phát hiện principal/route |
| Incomplete CDC | Target applied position thiếu một event | Cleanup gate bị block |
| Missed tombstone | Target còn record đã delete | Reconciliation fail |
| Delayed scheduled job | Một batch chạy sau quan sát ngắn | Owner được phát hiện |
| Key recreation | ID giống nhưng generation mới | Không xóa nhầm |
| Version race | Record thay đổi sau dry-run | Conditional delete fail |
| Legal hold issued | Hold được bật trước execute | Job dừng |
| Restore copy unavailable | KMS/repository tạm lỗi | Job không tiếp tục |
| Archive manifest missing | Thiếu base/log artifact | Deletion blocked |
| Backup restore drill | Khôi phục retained copy riêng | Dữ liệu/invariants đúng |
| Wrong cluster ID | Kết nối nhầm account/region | Preflight fail |
| Excess candidate count | Count vượt approved max | Block trước mutation |
| Retry after timeout | Một batch xóa rồi mất ACK | Không xóa sai scope |
| Stop on p99 regression | New DB p99 tăng | Job pause/abort |
| Cassandra tombstones | Mass delete gây compaction load | Rate guard hoạt động |
| Redis Cluster SCAN | Một node/slot bị bỏ sót | Coverage check fail |
| Search alias remains | Client dùng index name cũ | Dependency scan phát hiện |
| Dynamo Global Table | Region khác còn app client | Region-scope audit fail |
| Old backup key dependency | Backup dùng KMS cũ | Key không bị xóa |
| Ghost CDC consumer | Consumer start từ old after cutover | Không publish duplicates |
| Cache future data | Restore new source về earlier epoch | Cache invalidation/rebuild |
| Deletion ledger | Privacy deletion bị quên sau restore | Reapply policy before serving |
| Infrastructure destroy plan | Terraform định xóa shared resource | Manual review block |

Không phải mọi thí nghiệm đều chạy trên production. **Staging/lab synthetic data** phù hợp cho fault injection và destructive-case tests; production cần canary nhỏ, approval và blast-radius controls.

### 27.1. Đặt exit criteria cho mỗi thí nghiệm

Một record có thể là:

~~~yaml
testId: "unexpected-legacy-write"
environment: "staging"
sourceCluster: "old-order-test"
expected:
  acceptsWrite: false
  triggersAlert: true
observed:
  accepted: false
  alertReceived: true
evidence:
  traceId: "synthetic-trace-id"
status: "PASS"
~~~

Đây là **mẫu ghi evidence**, không phải kết quả thử thật. Production launch gate cần kết quả có provenance.

## 28. Case study A — Client cũ còn ghi sau cutover

### Bối cảnh

Order API đã chuyển sang target, nhưng một cron job của bản Java cũ chạy mỗi Chủ nhật vẫn ghi adjustments vào legacy database.

~~~text
Monday:  migrated reads/writes work on new.
Friday:  team decides to delete old collection.
Sunday:  old cron runs and writes adjustment E55.
```

### Triệu chứng

Dashboard new source không có E55. Old source bị xóa nên không thể biết job đã xử lý adjustment thế nào; business report lệch.

### Nguyên nhân

Observation window và dependency inventory không bao phủ cron job; old write authority không được fence.

### Thiết kế đúng

Trước cleanup:

1. Inventory scheduled jobs, account principals, network logs.
2. Fence old writes.
3. Bật alarm cho mọi attempt.
4. Chạy job/đợi business cycle.
5. Reconcile unknown outcomes.
6. Chỉ xóa khi owner sign-off.

## 29. Case study B — Rollback nhưng dữ liệu cũ đã stale

### Bối cảnh

New source nhận writes suốt 12 ngày. Legacy cluster vẫn sống nhưng không có backward sync. Incident xảy ra, team quyết định đổi DNS về legacy.

### Hậu quả

Legacy thiếu 12 ngày Order writes; API có thể trả bản cũ hoặc làm phát sinh repeated payments.

### Bài học

**Giữ live cluster không đồng nghĩa rollback khả thi.** Cần replay/backward transform và idempotent reconciliation hoặc chọn forward recovery. Đóng rollback horizon phải dựa trên khả năng quay lui thật, không chỉ chi phí giữ cluster.

## 30. Case study C — Xóa sớm Payment idempotency keys

### Bối cảnh

Orders đã migrate nhưng dedup keys trong Redis/legacy table bị coi là cache và xóa hết.

~~~text
Payment capture request R42 completed before migration.
After cleanup, provider callback retries R42.
New system lacks durable idempotency mapping.
```

### Hậu quả

Ứng dụng có thể thực hiện lại side effect hoặc không biết trạng thái đã commit, tùy provider contract.

### Hành động đúng

Phân loại idempotency stores theo **business operation retention**, migrate/retain mappings, dùng provider reconciliation và stable request IDs. Không xóa chỉ vì tên service là cache.

## 31. Case study D — Dữ liệu đã delete được hồi sinh

### Bối cảnh

Legacy source có tombstone `DELETE Order O900 v20`, target backfill thiếu delete event. Team xóa old source sau khi counts nhìn tương đương.

### Hậu quả

Target còn Order O900 v19, có thể hiển thị dữ liệu lẽ ra đã bị xóa. Khi không còn old evidence, việc khôi phục delete history khó hơn.

### Giải pháp

Đối soát **absence/delete events** và version history, giữ tombstone/CDC evidence tới khi target applied, chặn cleanup nếu delete coverage mismatch.

## 32. Case study E — Xóa KMS key trước backup

### Bối cảnh

Legacy cluster đã tắt, nhưng retained immutable backup vẫn mã hóa bằng key K1. Automation thu hồi K1 cùng với application credentials.

### Hậu quả

Bytes backup và checksum vẫn tồn tại nhưng archive có thể không giải mã được, phá retention/recovery.

### Hành động đúng

Dependency graph `backup → key`, key lifecycle review, test decrypt trên isolated restore, phân tách app access credential với backup recovery key, giữ quyền truy cập tối thiểu.

## 33. Case study F — Dọn Cassandra sinh quá nhiều tombstones

### Bối cảnh

Một job xóa hàng chục triệu cells trong Cassandra theo từng key ngay trong giờ cao điểm; disk usage chưa giảm nên team tăng parallelism.

### Hậu quả

Write/compaction load tăng, read latency spike, tombstones tích lũy và storage free cải thiện chậm.

### Thiết kế đúng

Đánh giá **drop table/partition retention/TTL/compaction** theo schema và safety contract, throttle batch deletes, theo dõi pending compactions/IOPS/latency, giữ tombstones đủ lâu cho replica correctness. Không xóa tiếp vô hạn dựa vào disk free chưa tăng.

## 34. Case study G — Search alias đã chuyển, báo cáo vẫn gọi index cũ

### Bối cảnh

Online search dùng alias `orders-search` trỏ `orders-v2`; một analytics job chạy cuối tháng vẫn gọi thẳng `orders-v1`.

### Hậu quả

Khi index cũ bị xóa, báo cáo lỗi dù live API không có dấu hiệu.

### Phòng ngừa

Inventory direct index references, access logs và job owners; thử monthly report trong staging hoặc quan sát qua chu kỳ; deprecate direct access, update docs và alias/ILM controls trước khi drop.

## 35. Case study H — Chưa đổi runbook, on-call chạy lại backfill

### Bối cảnh

Sau migration, runbook cũ hướng dẫn “re-run legacy-to-new sync” khi thấy read mismatch. On-call thực hiện sau khi target đã có writes mới.

### Hậu quả

Một batch không có version guard có thể overwrite record mới bằng legacy data cũ.

### Hành động đúng

Thay runbook cùng cutover, đặt **authority epoch guard** trên migration job, revoke old sync credentials sau grace period, đào tạo on-call và lưu ADR giải thích vì sao old-to-new backfill bị cấm sau mốc E43.

## 36. Case study I — Backup base bị xóa nhầm theo ngày

### Bối cảnh

Retention script xóa full backup F1 vì hơn 30 ngày tuổi, nhưng incremental I5 mới vẫn cần F1.

### Hậu quả

Backup repository còn hàng trăm files nhưng không tạo được restore chain.

### Khắc phục

Chỉ expire artifact khi **không còn complete recovery set tham chiếu**, dry-run dependency graph, bảo vệ object versions và chạy restore drill sau retention changes.

## 37. Case study J — Mọi metric tốt nhưng thiếu một tenant

### Bối cảnh

98% requests và tổng document count gần đúng; một tenant chỉ có dữ liệu cuối năm nên chưa xuất hiện trong sample. Legacy table bị xóa.

### Hậu quả

Khi tenant truy cập lại, data thiếu; mất một nguồn kiểm tra và có thể mất khả năng sửa.

### Phòng ngừa

So key coverage per tenant/partition và test edge cases, không chỉ weighted API traffic; lưu reconciliation artifacts và archive đủ theo retention trước khi xóa.

## 38. Case study K — Multi-region replica bị coi nhầm là archive

### Bối cảnh

Một managed NoSQL table hoạt động ở Region A và có replication tới Region B. Sau khi migration sang table mới, team cho rằng Region B là “bản backup” và xóa mọi snapshot cũ.

### Rủi ro

Delete hoặc corruption logic ở Region A có thể tiếp tục replication sang Region B tùy protocol. Region B không phải immutable historical recovery point, nên team có thể mất cả đường khôi phục trước corruption.

### Giải pháp

Tách rõ:

- Multi-region availability/replication.
- Immutable backup/PITR.
- Retention và legal hold.
- Region failover authority.
- Per-region read/write routing.

Không dùng một replica vận hành như bằng chứng backup độc lập.

## 39. Case study L — Xóa trong lúc legal hold mới được áp

### Bối cảnh

Plan được duyệt ngày D1, dự kiến xóa ngày D7. Ngày D5 compliance đặt legal hold với một tập hồ sơ; deletion job dùng bản approval cũ không kiểm tra lại.

### Hậu quả

Job xóa dữ liệu đang phải lưu, tạo rủi ro pháp lý và không thể hồi phục nếu backup cũng đã hết hạn.

### Giải pháp

Approval có expiry và live retention/hold check ngay trước thực thi, stop khi scope/policy thay đổi, store audit riêng và quy trình xử lý exception.

## 40. Case study M — Redis Cluster cleanup chỉ quét một primary

### Bối cảnh

Một script Java dùng `SCAN` trên connection tới một Redis Cluster node. Nó tìm ít keys `order:v1:*`, xóa xong rồi báo namespace đã sạch.

### Nguyên nhân

Redis Cluster chia keys theo slots trên nhiều primaries; một node chưa bao quát toàn bộ cluster. Hơn nữa `SCAN` không là snapshot trong khi writers còn hoạt động.

### Giải pháp

Cluster-aware scan qua các primaries/slots, write fencing, bounded idempotent deletion, per-shard coverage và pass xác minh sau khi writers đã dừng.

## 41. Case study N — Data “ẩn” vẫn nằm trong backups

### Bối cảnh

Người dùng yêu cầu xóa thông tin cá nhân. Team xóa document ở old/new stores và search index nhưng còn hàng trăm snapshots chứa PII; một restore drill vô tình nạp lại snapshots vào public environment.

### Giải pháp

Privacy-oriented deletion policy cho backups/archives theo obligations, quyền truy cập giới hạn, encryption/key lifecycle, replay deletion ledger và **privacy gate trước restore cutover**. Không đồng nhất “không tìm thấy trong API” với “đã xử lý mọi bản sao”.

## 42. Case study O — Xóa old database khiến backup của target bị lỗi

### Bối cảnh

Migration setup tạm thời dùng một service account chung cho old cluster và target backup uploader. Cleanup revoke toàn bộ IAM principal mà không phân tích dependency.

### Hậu quả

Backup pipeline của target không còn ghi object storage; chưa có alarm nên vài ngày sau RPO vượt mục tiêu.

### Giải pháp

Quản lý IAM theo resource-specific principal/least privilege, vẽ dependency graph và chạy **post-decommission recovery/backup verification**, không chỉ nhìn API traffic.

## 43. Case study P — Thu hồi hạ tầng làm xóa cả data mới

### Bối cảnh

Terraform module cũ quản lý cả legacy table và shared KMS key/VPC endpoint mà target đang dùng. Change author xóa module rồi chạy plan mà không xem resource graph.

### Hậu quả

Một thao tác tưởng chỉ dọn legacy lại phá tài nguyên dùng chung của target.

### Giải pháp

Review exact Terraform plan/state IDs, tách ownership shared components, chuyển lifecycle vào module mới khi cần, có deletion protection và approval độc lập cho shared resources.

## 44. Bài tập thực hành

### Bài 1 — Có ba copies, xóa cái nào?

Một migration hoàn tất:

~~~text
Legacy live cluster: old Orders
New live cluster:    authoritative Orders
PITR backup:         latest verified target backup
Immutable archive:   cutover snapshot of old Orders
Search index:        legacy orders-v1
```

Hãy phân loại từng thành phần thành **KEEP, ARCHIVE, QUARANTINE, DELETE hoặc REBUILD**, có điều kiện và lý do, không dựa vào tên.

### Bài 2 — Rollback giả

Cutover ngày D0, new store nhận writes đến D10; old store read-only và không backward-sync.

1. Có thể đổi DNS về old ở D10 để rollback không?
2. Dữ liệu nào bị thiếu ở old?
3. Phải bổ sung gì nếu muốn rollback thật?
4. Khi nào có thể đóng rollback horizon?

### Bài 3 — Count bằng nhau

Old và new đều có 500.000 records. Nhưng target thiếu 100 records còn sống, và có thêm 100 records đã bị delete ở old.

1. `COUNT` báo gì?
2. Có được xóa old không?
3. Đề xuất ít nhất ba phép đối soát bổ sung.
4. Các delete events/tombstones cần dùng thế nào?

### Bài 4 — Monthly job

Database access logs 7 ngày cho thấy zero legacy reads. Một billing job chạy ngày cuối mỗi tháng vẫn dùng old.

1. Mốc quan sát 7 ngày đủ chưa?
2. Làm sao tìm job không chạy hằng ngày?
3. Có thể dùng IAM principal access logs và job inventory thế nào?
4. Sau khi phát hiện job, cần kiểm thử trên new ra sao?

### Bài 5 — Ghost writer

Một Java client cũ có connection pool tới old cluster và gửi `reserveInventory` sau cutover.

1. Chỉ đổi DNS có chặn được không?
2. Fencing cần nằm ở đâu?
3. Cần theo dõi metrics nào?
4. Unknown outcome của một write timeout xử lý thế nào?

### Bài 6 — CDC checkpoint

Source commit log tới L9000; target áp đến L8700; consumer broker lag hiển thị 0.

1. Có được xóa source cũ không?
2. Vì sao broker lag=0 chưa đủ?
3. Cần những high-water/checkpoint nào?
4. Làm sao phát hiện 300 operations thiếu?

### Bài 7 — TTL không đúng giờ

Legacy Redis session TTL đã hết nhưng key vẫn có thể xuất hiện trong một snapshot. Business policy cấm dùng session sau 12:00.

1. Xóa vật lý có cần hoàn thành đúng 12:00 để đáp ứng business?
2. Read path cần làm gì?
3. Khi restore backup cũ, xử lý TTL/expiresAt thế nào?
4. Có nên coi Redis Session như cache thuần không?

### Bài 8 — Quarantine vs backup

Một live legacy cluster được đổi sang read-only và mất backup vì team cho rằng cluster là archive.

1. Những lỗi nào vẫn khiến mất data?
2. Vì sao read-only không thay immutable backup?
3. Cần manifest/checksum/key/restore drill gì?
4. Đặt owner và delete horizon như thế nào?

### Bài 9 — Xóa theo namespace

Một collection chung chứa records `migrationEpoch=E41` và `E42`, và một số records E42 đang legal hold.

1. Có nên drop collection?
2. Selector an toàn cần điều kiện gì?
3. Vì sao count dry-run có thể thay đổi?
4. Có thể dùng ID+generation+version như thế nào?

### Bài 10 — Delete race

~~~text
t0 Job previews O900 v18 as RETIRED.
t1 A writer changes O900 to v19 ACTIVE.
t2 Job deletes by ID.
```

1. Lỗi ở đâu?
2. Conditional delete với expectedVersion giải quyết phần nào?
3. Vì sao vẫn cần write fencing?
4. Nếu conditional conflict xảy ra, job nên làm gì?

### Bài 11 — Cassandra tombstones

Một cluster Cassandra được yêu cầu xóa dữ liệu cũ của một tenant trong shared table.

1. Vì sao `DROP TABLE` không phù hợp?
2. Mass DELETE gây loại overhead nào?
3. Vì sao không tùy ý giảm `gc_grace_seconds`?
4. Metrics nào đánh giá physical cleanup?

### Bài 12 — Redis Cluster

Một script chỉ scan primary P1 và xóa 1.000 keys; Redis Cluster có P1/P2/P3.

1. Namespace đã sạch chưa?
2. `SCAN` có bảo đảm snapshot không?
3. Cần cách duyệt cluster nào?
4. Có được `FLUSHALL` để “đảm bảo” không?

### Bài 13 — MongoDB TTL/index

Ứng dụng chuyển collection `orders_v1` sang `orders_v2`; TTL index của v1 đã kích hoạt nhưng collection chưa empty.

1. TTL có phải sync exact-time deletion không?
2. Vì sao vẫn cần archive/retention decision?
3. Có nên xóa index v1 nếu batch report còn dùng?
4. `drop` khác `deleteMany` ở scope như thế nào?

### Bài 14 — DynamoDB multi-region

Orders cũ là Global Table ở Regions A/B; code đã chuyển sang Orders mới chỉ ở A.

1. Có thể xóa Region B cũ ngay không?
2. Những clients/failover dependencies cần kiểm tra?
3. Global Table replica có thay PITR không?
4. Table backup/restore settings và IAM cần gì?

### Bài 15 — Cosmos DB

Legacy container shared có nhiều tenant, chỉ tenant A đã migrate.

1. Có được delete container không?
2. Partition key/`id` có ý nghĩa gì cho scoped delete?
3. Bulk delete ảnh hưởng RU/429 ra sao?
4. Change feed continuation cần xử lý gì?

### Bài 16 — Elasticsearch alias

Alias `orders-read` trỏ v2, nhưng một scheduled report truy vấn index `orders-v1` trực tiếp.

1. Nếu xóa v1 điều gì xảy ra?
2. Vì sao alias switch chưa đủ?
3. Cần kiểm tra templates/ILM/ingest pipeline nào?
4. Nếu v1 chứa manual annotations, có còn là derived index không?

### Bài 17 — KMS key dependency

Archive old DB có checksum chính xác, encryption key K1 còn duy nhất một bản và sắp bị disabled.

1. Có thể xóa K1 khi archive retention còn 2 năm không?
2. Cần backup/key dependency graph nào?
3. Làm sao verify khả năng decrypt?
4. Tại sao không lưu plaintext key cạnh archive?

### Bài 18 — Retention vs rollback

Rollback window 10 ngày; audit retention 7 năm; old cluster tốn 5.000 USD/tháng.

1. Có bắt buộc giữ old live cluster suốt 7 năm không?
2. Cần archive ở dạng nào?
3. Làm sao kiểm soát encrypted storage, access, restore RTO?
4. Khi nào được xóa live cluster?

### Bài 19 — Privacy deletion

Một người dùng xóa dữ liệu sau migration. Old store, new store, search, cache, exports, backups đều có thể chứa copies.

1. Tạo danh sách nơi phải xử lý.
2. Backups immutable cần policy/controls gì?
3. Khi restore snapshot cũ, tránh hồi sinh thế nào?
4. Legal hold thay đổi thứ tự xử lý ra sao?

### Bài 20 — Backup incremental

~~~text
F1 full backup at L1000
I1 covers L1001..L1200
I2 covers L1201..L1500
I3 covers L1501..L1800
```

Retention script muốn xóa F1 vì quá hạn nhưng I3 còn hiệu lực.

1. Tại sao nguy hiểm?
2. Khi nào xóa F1 được?
3. Có cần giữ KMS key của F1 không?
4. Bằng chứng nào cho thấy restore chain vẫn tốt?

### Bài 21 — Approval hết hạn

Plan được duyệt ngày D1, expiresAt D5. Job chạy lại D7 sau lỗi và vẫn có dữ liệu cần xóa.

1. Có được tái sử dụng approval không?
2. Phải kiểm tra lại những gì?
3. Vì sao signed plan chưa đủ nếu legal hold thay đổi?
4. Nếu đã xóa một phần trước D5, resume xử lý ra sao?

### Bài 22 — Write p99 tăng khi cleanup

Trong lúc cleanup legacy data:

~~~text
New DB p99:    100ms -> 500ms
Old DB disk:   50% -> 95% busy
CDC backlog:   0 -> 300,000 events
```

1. Có thể có shared dependency nào?
2. Vì sao cần pause/rate-limit?
3. Stop conditions nên là gì?
4. Khi nào được resume?

### Bài 23 — Undo data erasure

Đã xóa physical legacy collection, chỉ còn immutable archive ở một region khác. Product team muốn “rollback một cú click”.

1. Có thực hiện rollback tức thì không?
2. Cần rehydrate, schema/application compatibility, replay nào?
3. RTO khác live rollback thế nào?
4. Những unknown external side effects phải reconcile?

### Bài 24 — IaC shared resource

Terraform plan định xóa old DB, shared VPC endpoint và KMS key đang được new DB backup dùng.

1. Có thể apply không?
2. Làm thế nào tách resource ownership?
3. Cần kiểm tra exact plan/state nào?
4. Sau khi sửa plan, test phụ thuộc nào?

### Bài 25 — Documentation drift

Runbook cũ ghi “nếu query không trả dữ liệu, đọc legacy store và nạp lại vào new”, trong khi legacy đã bị cách ly và new đang authoritative.

1. Vì sao nguy hiểm?
2. Runbook mới nên hướng dẫn điều tra gì?
3. Cần cập nhật ADR/sơ đồ/data lineage thế nào?
4. Làm sao thông báo tới on-call?

### Bài 26 — Chi phí và backup

Live old cluster có 6 nodes; sau migration team vẫn duy trì mọi nodes 18 tháng chỉ vì “có thể cần audit” dù archive restore đã verified.

1. Có thể giải thể live nodes và giữ archive không?
2. Điều kiện nào phải đáp ứng?
3. Chi phí nào còn trong object storage/KMS?
4. Rủi ro nào của archive cần test?

### Bài 27 — Wrong-cluster failure

Một deletion plan chọn `orders_legacy` nhưng connection string trỏ sang target production cluster có cùng namespace name.

1. Filter namespace có đủ bảo vệ không?
2. Các immutable source IDs nào cần check?
3. Có thể thêm generation/tenant/ETag guards thế nào?
4. Một tool nên phản ứng sao nếu identity mismatch?

### Bài 28 — Cửa sổ quan sát và định nghĩa “0 reads”

Metrics không thấy traffic old trong 2 tuần. Có báo cáo cuối quý và một script DR 6 tháng/lần.

1. Có thể chứng minh không còn dependencies chỉ bằng 2 tuần metrics?
2. Dùng code/config/owner inventory như thế nào?
3. Cần chạy synthetic reporting drills ra sao?
4. Khi nào có thể dừng legacy network endpoint?

### Bài 29 — Thiết kế cleanup end-to-end

Một Order Service vừa chuyển từ cluster cũ sang new NoSQL:

~~~text
Old logical data:        18 TiB
New logical data:        18 TiB
Cutover:                15 days ago
Old write attempts:     3 in last 24 hours
CDC last source:        L9000
CDC target applied:     L8995
Mismatch by tenant:     0.01% in two tenants
Rollback window:        30 days
Retained archive:       uploaded, not restore-tested
End-of-month report:    not yet tested on new
```

Hãy thiết kế:

1. Quyết định hôm nay giữ/quarantine/delete?
2. Các blockers trước deletion.
3. Kế hoạch reconcile missing five events và two tenants.
4. Fencing/tracing clients còn ghi old.
5. Backup/restore drill cần làm.
6. Kiểm thử monthly reporting.
7. Retention/approval gates và future delete window.
8. Dashboard và runbook cần cập nhật.

### Bài 30 — Phản biện proposal

Đề xuất sau:

> “Sau khi chuyển API sang DB mới, chạy `drop` legacy ngay để tiết kiệm tiền. Bản backup tar nằm chung bucket với logs nên có lẽ đủ. Redis chỉ là cache nên `FLUSHALL` toàn account. Dừng tất cả alarms cũ. Xóa KMS key vì không còn DB. Không cần so dữ liệu vì cả hai bên cùng số dòng. Chỉ cần cập nhật wiki khi rảnh. Nếu lỗi, bật lại old cluster từ snapshot.”

Hãy tìm **ít nhất mười giả định sai/thiếu bằng chứng** và viết lại thành một kế hoạch hậu cutover an toàn.

## 45. Gợi ý lời giải và phương pháp quyết định

### 45.1. Bài 1 — Không phải bản nào cũng cần giữ live

**New live cluster**: KEEP và backup/PITR. **Legacy live cluster**: QUARANTINE tới hết rollback/retention gates, sau đó có thể decommission. **Immutable archive**: KEEP/ARCHIVE theo policy, restore test và security. **Legacy search index**: có thể DELETE sau khi không còn dependency, alias/queries đã chuyển và dữ liệu tái tạo được. **PITR target**: KEEP theo RPO/RTO; không thay thế bằng archive old.

### 45.2. Bài 2 — Old store không có 10 ngày writes

Nếu new store nhận writes D0–D10 và old không backward-sync, DNS rollback sẽ làm **thiếu 10 ngày changes**, kể cả deletes, status updates và idempotency. Cần backward transform/replay theo ordered history và reconciliation, hoặc chọn forward recovery. Không gọi old “ready to roll back” nếu chưa có test phục hồi theo cutover epoch.

### 45.3. Bài 3 — Count không chứng minh đúng

Counts đều 500.000 nhưng key sets/versions khác. **Không xóa old**. So consistent key coverage, normalized payload/value hashes, deleted/tombstone history, per-tenant groups và business invariants.

### 45.4. Bài 4 — Quan sát theo chu kỳ

7 ngày không bao phủ monthly billing. Ngoài metrics cần scheduled-job inventory, IAM/service account access, batch configs, domain owner sign-off và rehearsal của monthly close trên new store.

### 45.5. Bài 5 — Ghost writers

DNS chỉ ảnh hưởng discovery/resolution mới; existing pooled connections/hardcoded endpoints có thể vẫn hoạt động. Cần **server-side fencing/revoke write grants/authority epoch** và alert attempted writes. Với timeout, kiểm tra idempotency/commit outcome trước retry.

### 45.6. Bài 6 — Source L9000, target L8700

Chưa được xóa source. Có **300 units of progress difference** trong một mô hình log tuyến tính minh họa, nhưng không biết có đúng 300 business operations hay không nếu positions không liên tiếp hoặc log granularity khác. Broker consumer lag=0 có thể bỏ qua source-to-broker gap; cần compare true source high-water, connector read position và target applied/durable position.

### 45.7. Bài 9 — Collection chia sẻ

Không `DROP` collection chứa records E41/E42 mixed hoặc hold. Chọn exact IDs với `tenantId`, generation, version, retention state, hold check; freeze selector/manifest và dùng conditional deletes. Counts có thể biến động nếu writers/TTL/churn.

### 45.8. Bài 10 — TOCTOU delete race

`read v18` rồi `DELETE by ID` có time-of-check/time-of-use race. Atomic conditional delete theo v18 có thể chặn xóa v19 nhưng phải fail-closed khi conflict và tiếp tục điều tra writer/generation. **Không retry bằng delete không điều kiện**.

### 45.9. Bài 11 — Tombstone pressure

Vì shared table còn dữ liệu tenant khác, drop table không phù hợp. Mass deletes có thể tạo tombstones, compaction và read overhead; giảm `gc_grace_seconds` mà bỏ qua repair/outage có nguy cơ data resurrection. Đo tombstone stats, pending compactions, disk I/O, p99 và replication/repair.

### 45.10. Bài 12 — Redis Cluster coverage

Scan P1 chưa bao quát P2/P3; SCAN không là stable snapshot khi keys thay đổi. Cần cluster-aware keyspace inventory, writer fencing và iterative idempotent cleanup. `FLUSHALL` trên shared service có blast radius quá lớn.

### 45.11. Bài 17 — KMS key là dependency

Nếu archive còn giữ 2 năm và phụ thuộc K1, không xóa/disable K1 trước khi có decryption plan thay thế đã kiểm chứng. Lưu key reference, authorized recovery role, thử decrypt/restore, theo dõi key lifecycle. Không bao giờ lưu plaintext key trong archive manifest.

### 45.12. Bài 18 — Giữ archive, không nhất thiết giữ live cluster

Audit retention 7 năm không buộc giữ six live DB nodes nếu hợp đồng cho phép archive và đã có **manifest, checksum, serializer/schema, decrypt rights và restore/retrieval process**. Decommission sau rollback/retention approvals, giữ archive an toàn với policy và tested recovery.

### 45.13. Bài 19 — Privacy deletion xuyên copies

Inventory new/old, caches, search, analytics, exports, broker, object files và backups/archives. Một restore từ snapshot cũ phải áp valid deletion ledger/policy trước khi phục vụ, trừ những ngoại lệ retention/hold hợp pháp. Không tự xóa immutable backup bằng lệnh trái với policy; privacy/legal review quyết định cơ chế.

### 45.14. Bài 20 — Full F1 vẫn cần

I1–I3 phụ thuộc F1 nên không được xóa F1 nếu không có alternative complete baseline/chain. Encryption key và manifests cũng là dependencies. Verify bằng dependency graph và restore drill thực sự; không chỉ kiểm tra files tồn tại.

### 45.15. Bài 21 — Approval có thời hạn

Expired approval **không hợp lệ** để execute. Refresh source identity, selection manifest, hold/retention, backup restore evidence, reader/writer state, counts, owner/reviewer approvals. Nếu đã xóa một phần, resume bằng durable per-ID outcome checkpoints và new authorization; không tự mở rộng scope.

### 45.16. Bài 22 — p99 và CDC backlog

Backup/cleanup có thể cạnh tranh disk/network/storage với migration CDC và target reads; cũng có thể job dùng shared workers. Nếu p99 từ 100→500 ms, CDC backlog tăng tới 300.000, đây là lý do **pause/rate-limit để chẩn đoán**, không tăng concurrency. Resume sau khi metrics về threshold, root cause và data correctness được xác minh.

### 45.17. Bài 24 — IaC shared resource

Không apply plan xóa shared KMS/VPC endpoint khi target backup còn phụ thuộc. Tách resource ownership/move state theo documented process, review IDs/diffs, validate target backup/decrypt/connectivity trước và sau cleanup.

### 45.18. Bài 25 — Runbook lỗi thời

Đọc legacy và nạp lại có thể overwrite dữ liệu authoritative mới. Runbook cần tra source version, target read paths, CDC/outbox and reconciliation, backup/PITR và owner escalation, với **cấm chạy old-to-new backfill không có epoch guard**. ADR và data flow updated cùng migration checkpoint, không chờ khi rảnh.

### 45.19. Bài 27 — Wrong cluster

Namespace name trùng không đủ bảo vệ. Preflight so `account/cluster identity`, region, environment, dataset generation, user role và approved scope. Tool phải **fail closed** ngay khi mismatch; không tự đổi cluster.

### 45.20. Bài 29 — Cleanup bị chặn

Với dữ kiện:

~~~text
Old write attempts >0
CDC source L9000, target L8995
Reconciliation mismatch 0.01% in two tenants
Rollback window 30 days, only 15 days elapsed
Archive not restore-tested
Monthly report not validated
```

Quyết định đúng lúc này là **không xóa**, có thể duy trì QUARANTINE/fencing và kiểm soát chi phí trong phạm vi cho phép. Cần điều tra 3 writers, apply/match remaining changes theo semantics log, sửa mismatches, restore drill, test monthly report, đợi rollback gate và lấy owner approval.

### 45.21. Bài 30 — Proposal còn nhiều lỗ hổng

Ít nhất:

1. API traffic switch không chứng minh mọi clients đã chuyển.
2. Chưa có old write fencing.
3. Chưa đối soát keys/versions/deletes; counts bằng nhau không đủ.
4. Backup tar không có manifest/log chain/restore drill.
5. Không biết encryption key dependencies.
6. `FLUSHALL` có thể xóa data không thuộc Order Service.
7. Không xét idempotency keys trong Redis.
8. Không có rollback horizon/forward recovery.
9. Chưa phân loại retention/legal hold/privacy.
10. Không có stage/quarantine/dry-run/approval.
11. Chưa xác định namespace/cluster immutable identity.
12. Xóa alarms làm mất khả năng quan sát legacy clients.
13. Không cập nhật runbook khiến người trực làm sai.
14. Chưa thử batch/monthly job.
15. KMS key deletion có thể làm backup không giải mã được.
16. Restore từ snapshot cũ không tự bao phủ writes mới.
17. Không kiểm tra target PITR/RPO/RTO.
18. Chưa có evidence về actual deletes, storage reclaim.

Kế hoạch thay thế: **fence → reconcile → quarantine → archive/restore-verify → đóng rollback/hold gates → approve immutable selection → dry-run → bounded conditional deletion → verify → retire infra/credentials → cập nhật docs và giám sát hậu xóa**.

## 46. Checklist nghiệm thu 60 điểm

Checklist dưới đây dành cho **thiết kế một quy trình**, không thay thế approval pháp lý/production của môi trường cụ thể.

### 46.1. Nguồn chuẩn và ranh giới migration

1. Đã công bố **new authoritative source** theo domain/region chưa?
2. Có ghi cutover epoch, source/target cluster IDs và time boundary không?
3. Old source đã được fence khỏi mọi business writes chưa?
4. Các unknown write outcomes đã được reconcile theo operation IDs chưa?
5. Dual-write đã dừng theo protocol, không tạo divergent branches chưa?
6. CDC đã apply hết tới high-water được chốt chưa?
7. Có kiểm tra mọi shards/partitions/tenants/regions không?
8. Có biết rollback thật sự khả thi hay chỉ forward recovery không?
9. Có owner/business sign-off cho việc đóng rollback chưa?
10. Có phát hiện/alert cho bất kỳ old writer attempt mới không?

### 46.2. Đối soát và dependency inventory

11. Có so key coverage chứ không chỉ record count không?
12. Có so normalized values, versions và schema transforms không?
13. Có kiểm tra deletes/tombstones/TTL và generation resets không?
14. Có kiểm tra payment/ledger/idempotency business invariants không?
15. Có kiểm tra outbox, DLQ, consumer checkpoint và hidden jobs không?
16. Có bản đồ direct client access theo app version/region/principal không?
17. Observation window có bao phủ daily/weekly/monthly/quarterly jobs cần thiết không?
18. Có kiểm tra search aliases, cache namespaces và materialized views không?
19. Có kiểm tra external blob/object versions và references không?
20. Mọi mismatches còn tồn tại đã được giải thích/approved chưa?

### 46.3. Retention, backup và privacy

21. Mỗi asset có KEEP/ARCHIVE/DELETE decision và owner không?
22. Có retention policy với start/end clocks rõ ràng không?
23. Có kiểm tra legal hold và exceptions mới nhất không?
24. Có backup/archive manifest chứa source identity và consistent cut không?
25. Có đủ baseline/incremental/log chain cho restore horizon không?
26. Có kiểm tra checksum, object version và repository durability không?
27. Có run isolated restore drill từ retained copy không?
28. Có KMS key/roles/certificates/schema compatibility để restore không?
29. Có privacy deletion handling cho old/new/search/cache/backup không?
30. Có policy reapply valid deletion records khi restore backup cũ không?

### 46.4. Xóa có giới hạn

31. Deletion plan có exact cluster/account/region/namespace/generation không?
32. Có approved immutable candidate list/filter, maximum count không?
33. Execution mặc định DRY_RUN và có separate execute authorization không?
34. Có per-ID/version conditional delete khi phù hợp không?
35. Có kiểm tra source write authority, hold và backup gate ngay trước execute không?
36. Có stop conditions cho unexpected count/identity/conflicts không?
37. Có bounded batches, retries, deadlines và rate limits không?
38. Có durable checkpoints/audit cho partial completion không?
39. Có theo dõi new API SLO và source/replication/compaction health khi xóa không?
40. Có actual affected records, exceptions và result summary được lưu không?

### 46.5. Cơ chế NoSQL và physical cleanup

41. Có hiểu difference giữa `DROP`, record DELETE, TTL và physical reclaim không?
42. Có biết tombstone/GC grace/repair effects ở wide-column systems không?
43. Có kiểm tra snapshot backup artifacts giữ physical files sống không?
44. Với Redis Cluster, cleanup có bao phủ tất cả primaries/slots không?
45. Với sharded/Global Tables/Cosmos, có hiểu region/partition scopes không?
46. Với search, alias/index/templates/ILM và direct clients đã được audit không?
47. Có tránh force cleanup/compaction gây cạn I/O hoặc disk free không?
48. Có đo logical deletion và bytes reclaimed riêng không?
49. Có phân biệt authoritative data với derived caches/indexes không?
50. Có xác nhận shared resource IaC/KMS/network dependencies trước destroy không?

### 46.6. Vận hành, tài liệu và hậu kiểm

51. Sơ đồ data flow/architecture sau cutover đã updated chưa?
52. ADR/decision về rollback, retention và source authority có reviewer chưa?
53. Runbook on-call không còn hướng dẫn ghi vào legacy source chưa?
54. Backup/PITR restore runbook đã được tested, có RPO/RTO không?
55. Dashboard/alerts đã chuyển sang target nhưng còn giám sát cần thiết chưa?
56. IAM/service accounts/secrets/endpoint cleanup đã qua dependency review chưa?
57. Có fault-injection/staging test cho ghost writers, gap, wrong cluster và hold không?
58. Có chốt evidence links (reconcile, restore, approval, delete audit) trong change record không?
59. Có owner chịu trách nhiệm archives, deletion policy và monitoring sau decommission không?
60. Có observation window và postmortem/lesson-learned follow-up sau xóa không?

## 47. Mẫu biên bản nghiệm thu decommission

~~~yaml
changeId: "cleanup-orders-legacy"
date: "approved-execution-date"
environment: "production"
legacyAsset:
  clusterId: "immutable-cluster-id"
  region: "region-a"
  namespace: "legacy-orders"
  authorityEpoch: "E42"
newAuthority:
  clusterId: "new-authoritative-cluster-id"
  authorityEpoch: "E43"
gates:
  reconciliation: "signed-evidence-reference"
  cdcDrained: "high-water-reference"
  clientInventory: "approved-dependency-report"
  rollbackClosed: "approved-record"
  retentionAndHold: "policy-check-reference"
  archiveVerified: "restore-drill-reference"
  operationsApproval: "change-approval-reference"
execution:
  mode: "bounded-conditional-delete"
  candidateManifest: "immutable-selection-reference"
  approvedMaximum: 50000
  actualDeleted: "measured"
  conflicts: "measured"
  aborted: false
  postDeleteVerification: "verification-report-reference"
operations:
  docsUpdated: true
  alertsUpdated: true
  iamReviewed: true
  retainedBackupOwner: "recovery-team"
  nextArchiveExpiryReview: "policy-derived-date"
~~~

**Biên bản mẫu không phải bằng chứng đã xóa trong một hệ thực.** Chỉ điền `true`/`measured` khi có evidence, approval và dữ liệu thực tế tương ứng. Các mục `actualDeleted`, `conflicts` và timestamps không được điền bằng suy đoán hoặc tự chấp nhận theo mặc định.

## 48. Kết luận

**Xóa dữ liệu cũ, giữ bản sao cần thiết và cập nhật tài liệu vận hành** là ba mặt của cùng một công việc hoàn tất migration:

- **Xóa dữ liệu cũ** nhằm loại nguồn sai lệch, giảm chi phí và giới hạn dữ liệu dư thừa; phải có fencing, reconciliation, retention/hold gates, dry-run và phạm vi xóa được duyệt.
- **Giữ bản sao cần thiết** nhằm đáp ứng rollback, PITR, kiểm toán, điều tra và yêu cầu pháp lý; phải có archive/backup manifests, log chains, khóa giải mã và restore drills, không chỉ một folder chứa file.
- **Cập nhật tài liệu vận hành** bảo đảm hệ mới được giám sát, khôi phục và xử lý sự cố theo authority, topology, schema, consistency và dependencies mới; tài liệu cũ có thể tạo lỗi dữ liệu nghiêm trọng.

Những bài học quan trọng nhất:

1. **Cutover thành công không đồng nghĩa old source được phép xóa.** Các client, jobs hiếm, CDC và legal obligations có thể còn phụ thuộc.
2. **Rollback là một capability phải được kiểm chứng**, không chỉ là giữ server cũ chạy.
3. **Đếm dữ liệu bằng nhau không chứng minh đúng.** So keys, values, versions, deletes và business invariants ở cùng consistency boundary.
4. **Không xóa ở nhiều scope cùng lúc.** Fence, quarantine, archive, approve, dry-run, delete có giới hạn rồi verify.
5. **`DELETE`, tombstone, TTL, compaction và physical reclaim là những giai đoạn khác nhau** theo từng engine.
6. **Bản sao để hồi phục khác replica đang vận hành.** Một region replica không thay immutable PITR backup.
7. **Backup retention cần dependencies**: baseline/incrementals/logs, schema, keys, permissions và external object versions.
8. **Privacy/legal hold không được bỏ qua** chỉ vì migration owner muốn giảm chi phí.
9. **Java/SDK và scheduler cũ phải bị fence**, kể cả khi connection pools/DNS chưa cập nhật.
10. **IaC, KMS, IAM và monitoring là một phần của data lifecycle**, vì chúng có thể quyết định hệ mới hoạt động hoặc backup còn giải mã được.
11. **Mọi thao tác destructive cần có fail-closed guard**, signed/approved scope, audit và stop conditions.
12. **Runbook mới phải sẵn sàng trước khi old source biến mất**, và on-call phải biết recovery path thực.

Câu hỏi cuối cùng trước khi nhấn “Delete” là:

> **“Đã chứng minh dữ liệu đích là nguồn chuẩn đầy đủ, mọi client và pipeline đã rời nguồn cũ, các bản phục hồi bắt buộc đã được bảo vệ và thử khôi phục, không còn nghĩa vụ phải giữ bản live này, và người trực vận hành có đủ tài liệu để xử lý mọi sự cố sau khi xóa chưa?”**

Nếu một phần câu trả lời chưa có **evidence**, hãy giữ tài nguyên ở trạng thái **quarantine có kiểm soát** thay vì xóa không thể đảo ngược. Khi mọi gate đều được chứng minh, dọn dẹp sẽ là bước **đóng vòng đời dữ liệu có trách nhiệm**, không phải một canh bạc vận hành.
