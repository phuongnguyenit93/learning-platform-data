# Khôi phục toàn cụm, một tập dữ liệu hoặc một nhóm bản ghi

Một cụm NoSQL lưu dữ liệu đặt chỗ gặp sự cố. Trong một trường hợp, toàn bộ cluster không thể phục vụ vì cấu hình lưu trữ bị hỏng. Ở trường hợp khác, một collection bị xóa nhầm nhưng phần còn lại của cluster vẫn khỏe. Trong trường hợp thứ ba, chỉ 37 booking của một tenant bị cập nhật sai giá tiền, còn mọi dữ liệu mới vẫn đang được ghi bình thường.

Cả ba đều được gọi là **phục hồi dữ liệu**, nhưng không thể giải quyết bằng cùng một thao tác. Khôi phục nguyên cụm từ backup cũ có thể làm mất các writes hợp lệ đã commit sau thời điểm sao lưu. Phục hồi một collection trực tiếp lên môi trường đang chạy có thể làm mất index, trigger, metadata hoặc sinh xung đột phiên bản. Ghi đè 37 bản ghi bằng dữ liệu lịch sử có thể xóa những thay đổi hợp lệ phát sinh sau lỗi, hồi sinh bản ghi đã bị xóa hoặc phát sinh sự kiện nghiệp vụ lần nữa.

Bài thuộc **Database No SQL → Sao lưu và phục hồi**, tập trung vào lựa chọn và triển khai ba cấp phục hồi:

1. **Khôi phục toàn cụm:** tái dựng toàn bộ cluster/deployment hoặc phần fault domain tương ứng, thường từ physical snapshot kết hợp nhật ký thay đổi nếu hệ hỗ trợ.
2. **Khôi phục một tập dữ liệu:** phục hồi một database, keyspace, collection, table, index hoặc tập partition có ranh giới rõ mà không thay thế mọi dữ liệu khác.
3. **Khôi phục một nhóm bản ghi:** xác định các key/document/row cần sửa hoặc đưa về trạng thái đúng, thường qua **staging restore + đối soát + ghi điều kiện**, không lấy snapshot cũ ghi đè mù.

Các quyết định phải được dẫn dắt bởi **mục tiêu nghiệp vụ, thời điểm phục hồi, phạm vi hỏng, RPO/RTO, khả năng backup/PITR và tính nhất quán của dữ liệu**.

> **Nguyên tắc:** Backup là **nguồn dữ liệu để phục hồi**, không phải một lệnh “undo” tự động an toàn. Cần xác định **muốn tái tạo trạng thái tại thời điểm nào, bảo tồn những writes nào, có những xóa nào không được hồi sinh và những hệ dẫn xuất nào cần đồng bộ lại**. Với phục hồi chọn lọc, ưu tiên restore vào môi trường cách ly để kiểm tra, rồi áp dụng thay đổi qua một quy trình có điều kiện và có thể audit.

> **Lưu ý:** Những sản phẩm NoSQL khác nhau có cơ chế snapshot, PITR, oplog/WAL, backup export, region failover và restore semantics khác nhau. Tên thao tác trong bài chỉ là hướng tư duy; trước khi thực hiện phải kiểm tra tài liệu và phiên bản engine/provider đang dùng, quyền thực thi, quota, encryption keys, read/write guarantees và kế hoạch rollback.

## 1. Khôi phục là đưa hệ về **trạng thái đúng**, không chỉ làm nó chạy lại

Có thể phân biệt bốn mục tiêu:

- **Availability recovery:** dịch vụ đọc/ghi được trở lại, ví dụ leader failover hoặc thay node hỏng.
- **Data recovery:** dữ liệu nguồn đã mất/hỏng phải được tái dựng từ backup, log hoặc nguồn có thẩm quyền khác.
- **Logical correction:** dữ liệu vẫn ở đó nhưng bị thay đổi sai, cần sửa chọn lọc theo nghiệp vụ.
- **Projection rebuilding:** read model, search index hoặc cache bị hỏng trong khi source of truth vẫn đúng.

Nếu chỉ một replica chết nhưng quorum/source còn đúng, việc thêm replica mới và đồng bộ có thể là **replica recovery**, không cần restore cả cluster từ bản sao ngày hôm qua.

Nếu cache Redis mất sạch nhưng source vẫn đúng, việc cache warm-up có thể tốt hơn khôi phục một cache snapshot cũ.

Nếu search index sai, có thể cần **reindex từ source** thay vì phục hồi bản index cũ đã stale.

### 1.1. Những câu hỏi đầu tiên

1. **Nguồn sự thật nào bị ảnh hưởng?** Cluster chính, collection, table, keyspace, cache hay projection?
2. **Dữ liệu thực sự bị mất hay chỉ không truy cập được?** Có node/replica/region còn giữ bản đúng?
3. **Lỗi vật lý hay logic?** Hỏng storage, ransomware, drop table, mass update, stale replica, schema migration?
4. **Thời điểm dữ liệu cuối cùng còn đúng là khi nào?** Xác định theo UTC, operation IDs và commit/version boundary.
5. **Dữ liệu mới sau thời điểm đó cần giữ không?** Đa số tình huống khôi phục chọn lọc là có.
6. **Có backup được kiểm chứng hay chỉ có job báo thành công?**
7. **Có PITR/log đủ để phục hồi đến một mốc giữa hai snapshots không?**
8. **RPO/RTO/SLO và nghĩa vụ lưu giữ/xóa dữ liệu là gì?**

## 2. Ba phạm vi khôi phục

| Tiêu chí | Toàn cụm | Một tập dữ liệu | Nhóm bản ghi |
| --- | --- | --- | --- |
| Ví dụ | Cluster mất toàn bộ storage | Collection bookings bị drop | 37 booking bị sửa sai |
| Nguồn dữ liệu | Physical/logical backup + logs, replicas theo contract | Namespace/table export/backup/PITR | Snapshot ở staging, audit/event log, authoritative source |
| Tác động | Rộng nhất, có thể đổi endpoint/topology | Trung bình, phụ thuộc metadata/index | Hẹp về key nhưng rủi ro nghiệp vụ cao |
| Thời gian | Thường dài và cần điều phối topology | Phụ thuộc kích thước và độ phụ thuộc | Phụ thuộc khả năng xác định key và conflict |
| Rủi ro chính | Mất writes sau restore point, thay cả hệ | Lệch với tập dữ liệu khác | Overwrite writes mới, resurrection, side effects |
| Kiểm chứng | Cluster health, dữ liệu, quorum, end-to-end invariants | Counts, schema/index, referential invariants | Per-key versions/hashes, quyền, audit |
| Cutover | DNS/routing/application endpoints hoặc replace deployment | Namespace/alias switch, app route | Conditional updates và kiểm chứng từng key |
| Rollback | Giữ cluster cũ/quy trình failback | Giữ bản namespace cũ | Reversal/operation ledger, version-aware correction |

**Phạm vi nhỏ không tự an toàn hơn:** Một tập 37 bản ghi thanh toán có thể cần kiểm chứng nghiêm ngặt hơn việc rebuild hàng triệu cache keys.

### 2.1. Tập dữ liệu là khái niệm phải định nghĩa

Tùy sản phẩm, “dataset” có thể là:
- MongoDB database/collection.
- DynamoDB table hoặc tập items theo partition key.
- Cassandra keyspace/table.
- HBase table/column family/range.
- Redis database, namespace/prefix keys hoặc một tập hash slots.
- Search index/alias.
- Một tenant hoặc business entity group trải trên nhiều stores.

Không giả định backup native của engine luôn hỗ trợ restore chọn lọc đúng phạm vi này.

## 3. RPO, RTO và mốc phục hồi

**RPO (Recovery Point Objective):** mức dữ liệu tối đa có thể mất theo thời gian, xét tới những writes đã được ghi nhận theo contract.

**RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục một chức năng/dịch vụ tới trạng thái chấp nhận được.

Ví dụ:
- RPO = 5 phút.
- RTO = 60 phút.
- Snapshot mỗi 6 giờ.
- Không có log replay/PITR.

Nếu snapshot cuối cùng trước sự cố cách 4 giờ, chỉ dựa vào snapshot đó **không đáp ứng RPO 5 phút**, dù restore được trong 20 phút.

### 3.1. Tính RPO thực tế

Giả sử:
- Sự cố bắt đầu lúc 14:00 UTC.
- Backup/PITR có thể khôi phục nhất quán tới 13:57 UTC.
- Thời điểm bắt đầu mất quyền truy cập là 14:00 UTC.

Khoảng chênh 3 phút là một ước tính về recovery gap **theo thời gian**, chưa đủ để khẳng định mọi write trong ba phút đều mất. Cần so operation ledger và commit guarantees.

### 3.2. RTO bao gồm nhiều bước

Một mô hình:

\[
RTO_{\text{actual}} =
T_{\text{detect}} + T_{\text{decide}} + T_{\text{provision}} +
T_{\text{restore}} + T_{\text{verify}} + T_{\text{cutover}}
\]

Nếu bỏ qua thời gian lấy encryption key, provisioning đủ storage, dựng index và verify dữ liệu, RTO trên giấy sẽ lạc quan.

### 3.3. “Point in time” không chỉ là timestamp

Một hệ có nhiều shards/regions/partitions có thể không có **một total order toàn cầu**. Ranh giới hợp lệ có thể:
- Consistent snapshot timestamp do provider cung cấp.
- Transaction commit sequence.
- Oplog/WAL position.
- Per-partition checkpoint vector.
- Snapshot ID + log chain.

Không tự chọn timestamp UTC làm bằng chứng rằng mọi shards đã chụp cùng một trạng thái atomic nếu công cụ không đảm bảo điều đó.

### 3.4. Phục hồi về quá khứ khác sửa một lỗi logic

Nếu một thao tác sai lúc 12:00 nhưng các writes khác từ 12:00 đến 14:00 là hợp lệ:
- Restore **toàn cụm** về 11:59 có thể xóa mọi writes hợp lệ sau đó.
- Phục hồi **37 records bị ảnh hưởng**, dựa trên bản đúng và đối soát thay đổi sau 12:00, phù hợp hơn.

## 4. Backup không giống replication

Replication giúp availability và phục hồi node, nhưng:
- Một lệnh DELETE sai có thể được replicate tới mọi replicas.
- Ransomware/credentials bị xâm phạm có thể xóa dữ liệu trên các bản sao đang online.
- Corruption logic được sao chép.
- Replica lag không phải lịch sử dài hạn.

Backup cần:
- Ranh giới nhất quán.
- Retention.
- Isolation khỏi quyền ghi/xóa production.
- Encryption/key recovery.
- Tính toàn vẹn và kiểm chứng restore.
- Offsite/off-account theo threat model.
- Immutable/versioned copies phù hợp.

### 4.1. Physical snapshot

Lưu trạng thái storage/files/blocks theo cơ chế engine/provider:
- Có thể nhanh hơn cho cluster lớn.
- Restore thường yêu cầu topology/engine compatibility.
- Có thể bao gồm metadata nội bộ.
- Không tự hỗ trợ chọn vài records.

Một volume snapshot không được quiesce/checkpoint theo contract engine có thể **không nhất quán**, dù cơ chế storage báo snapshot thành công.

### 4.2. Logical export

Xuất documents/rows và có thể schema/metadata:
- Dễ lọc một namespace hoặc subset.
- Dễ chuyển sang môi trường staging.
- Phải xử lý datatype, index, TTL, version và consistency boundary.
- Full scan có thể rất tốn IO.
- Không tự bảo đảm transactional snapshot nếu scanner chỉ đọc từng page ở các thời điểm khác nhau.

### 4.3. Incremental backup và logs

- Full snapshot là mốc nền.
- Incremental snapshots/logs ghi những thay đổi tiếp theo.
- PITR cần chuỗi đầy đủ, đúng thứ tự/epoch và không có retention gap.
- Restore phải kiểm chứng mọi segment/checksum/metadata.

**Có file WAL/oplog không có nghĩa đã có một phương pháp PITR được engine bảo đảm**.

### 4.4. Snapshot của một replica

Nếu snapshot lấy từ secondary:
- Có thể lag so primary.
- Có thể chưa có write vừa ACK theo contract.
- Có thể có consistency restrictions.
- Phải ghi source replica, last applied position và snapshot boundary.

## 5. Sơ đồ quyết định phạm vi

~~~~mermaid
flowchart TD
    I["Incident: data unavailable / wrong"] --> A{"Authoritative source intact?"}
    A -->|Yes| P{"Only derived view/cache broken?"}
    P -->|Yes| REBUILD["Rebuild projection/cache from source"]
    P -->|No| LOGIC{"Small known key set affected?"}
    LOGIC -->|Yes| SELECT["Isolated restore + selective repair"]
    LOGIC -->|No| DATA["Restore affected dataset to staging"]
    A -->|No| EXTENT{"Whole cluster lost?"}
    EXTENT -->|Yes| CLUSTER["Cluster recovery from verified backups/logs"]
    EXTENT -->|No| DATA
    SELECT --> VERIFY["Consistency + business verification"]
    DATA --> VERIFY
    CLUSTER --> VERIFY
    REBUILD --> VERIFY
    VERIFY --> CUTOVER["Controlled cutover and monitoring"]
~~~~

### 5.1. Không quyết định chỉ dựa vào số bản ghi

Một logical update lỗi có thể tác động:
- Một số source records.
- Derived search index.
- CDC consumers.
- Cache.
- Financial ledger.
- Notification history.

“Chỉ 37 records” không có nghĩa chỉ 37 writes khi phục hồi: cần xem **các phụ thuộc và hệ dẫn xuất**.

## 6. Xây bản đồ phụ thuộc trước khi restore

Một booking có thể xuất hiện ở:

~~~~mermaid
flowchart LR
    API["Booking API"] --> MAIN[("NoSQL source")]
    MAIN --> CDC["CDC/outbox"]
    CDC --> INDEX[("Search index")]
    CDC --> COUNTS[("Aggregated counters")]
    MAIN --> CACHE[("Redis/cache")]
    MAIN --> AUDIT[("Audit/operation ledger")]
    MAIN --> BACKUP[("Backup/PITR")]
    PAY["Payment provider"] --> AUDIT
    RECON["Recovery coordinator"] -.-> MAIN
    RECON -.-> INDEX
    RECON -.-> COUNTS
    RECON -.-> CACHE
~~~~

Đặt câu hỏi:
- Nguồn nào là authority cho từng field?
- Những projections có thể rebuild từ source không?
- Có historical events phải bảo tồn không?
- Nếu ghi lại records phục hồi, CDC có phát event mới không?
- Có email/payment/webhook sẽ chạy lại ngoài ý muốn không?
- Có dữ liệu cá nhân đã bị xóa theo yêu cầu phải tiếp tục bị xóa không?

**Đừng restore cache/search từ backup cũ nếu source hiện tại đã thay đổi và có thể rebuild projection đúng hơn từ source.**

## 7. Phục hồi toàn cụm: khi nào phù hợp?

Cần cân nhắc whole-cluster recovery khi:
- Cluster/storage không còn bản authoritative hợp lệ.
- Nhiều shards/tables hỏng và không thể xác định phạm vi hẹp.
- Disaster recovery yêu cầu dựng cụm mới tại region khác.
- Mất quorum kèm mất dữ liệu đáng kể.
- Corruption lan rộng khiến việc phục hồi theo collection không đáng tin.
- Cần restore toàn bộ consistency boundary cho nhiều namespaces phụ thuộc lẫn nhau.

Không nhất thiết restore whole-cluster khi:
- Một node hỏng nhưng replica còn đúng.
- Chỉ search index cần rebuild.
- Một collection bị drop nhưng backup hỗ trợ selective recovery.
- Một tập records nhỏ cần sửa logic.

### 7.1. Whole-cluster recovery gồm những gì?

Không chỉ copy database files:
- Cluster/topology metadata.
- Shards/partitions/replica memberships.
- Schema, indexes, constraints/validators.
- Encryption keys và certificates.
- Users/roles/ACL theo policy.
- Application configuration/endpoints.
- CDC connector state/checkpoints.
- Backups, logs và thời điểm khôi phục.
- Capacity/storage/network.
- Read/write consistency.
- Data correctness verification.

### 7.2. Khu vực phục hồi phải cách ly

Ưu tiên dựng **recovery cluster** riêng:
- Không dùng production DNS/credentials mặc định.
- Chặn writes từ ứng dụng thông thường.
- Không để CDC/replay consumers gây side effects ngoài ý muốn.
- Dùng network và IAM giới hạn.
- Kết nối backup ở chế độ đọc.
- Có tags, TTL cho tài nguyên và audit.

Nếu restore trực tiếp trên cụm cũ, blast radius và khả năng rollback thường lớn hơn.

## 8. Phục hồi toàn cụm: quy trình tổng quát

### Bước 1 — Freeze phạm vi và bằng chứng

- Ghi incident ID.
- Xác định thời điểm sự cố và last known good time.
- Chụp logs/checkpoints/topology metadata có quyền.
- Bảo vệ backup chưa bị ảnh hưởng.
- Không làm thao tác phá hủy chứng cứ vô ý.

### Bước 2 — Chọn backup chain

Chọn:
- Full snapshot hợp lệ.
- Incremental/log segments liên tục nếu cần PITR.
- Backup revision và encryption key tương ứng.
- Region/account có thể đọc bản sao.
- Version compatibility.
- Integrity manifests/checksums.

Không dựa duy nhất vào dashboard “backup job succeeded”.

### Bước 3 — Provision cluster nhận

- Đủ storage theo data + indexes + compaction + catch-up headroom.
- Đúng engine version/config khả dụng.
- Network, TLS, IAM/ACL.
- Shard/partition layout theo restore plan.
- IOPS/throughput đủ cho restore và workloads sau cutover.

### Bước 4 — Restore và replay

- Apply snapshot theo công cụ chính thức.
- Replay incremental logs tới selected boundary nếu được hỗ trợ.
- Không skip missing segments.
- Tôn trọng epoch/partition ordering.
- Không chạy ứng dụng ghi trên cluster đang restore.

### Bước 5 — Verify

- Cluster membership/quorum/replication.
- Data counts/ranges/checksums.
- Schema/index/TTL.
- Business invariants.
- Query read/write test synthetic.
- Data freshness và version checks.
- Security/permissions.

### Bước 6 — Cutover

- Quyết định freeze/dual-write/routing theo runbook.
- Chặn split-brain giữa old và new authoritative clusters.
- Chuyển service discovery/connection strings đúng cách.
- Fencing old write owners.
- Theo dõi lỗi/rate/latency và data drift.

### Bước 7 — Post-recovery

- Ghi actual recovery point và RPO/RTO.
- Đối soát writes có nguy cơ mất.
- Rebuild cache/search/projections nếu cần.
- Lập kế hoạch failback.
- Retain evidence và backup theo policy.

## 9. Dữ liệu mới sau backup: rủi ro của whole-cluster restore

Một timeline:

~~~~text
11:00 Snapshot S
11:30 Booking A created
11:45 Booking B cancelled
11:50 User privilege revoked
12:00 Cluster damaged
~~~~

Nếu khôi phục nguyên cụm từ snapshot 11:00:
- Booking A không có trong bản khôi phục.
- Booking B có thể trở lại trạng thái cũ.
- Privilege vừa thu hồi có thể xuất hiện như còn hiệu lực.
- Các downstream systems có thể vẫn biết events sau 11:00.

Với hệ thống giao dịch, vấn đề không chỉ là “mất một giờ dữ liệu” mà là **mất đồng bộ nhân quả và bảo mật**.

### 9.1. Dùng PITR nếu có

Nếu có snapshot 11:00 và log chain có thể replay nhất quán tới 11:59, RPO thực có thể nhỏ hơn. Nhưng phải xác minh:
- Log segments đầy đủ.
- Commit ordering.
- Supported recovery semantics.
- Cross-shard transactions.
- Last durable position.
- External side effects từ thời gian sau mốc.

### 9.2. Khôi phục không được tự hoàn tác những hành động ngoài DB

Một email đã gửi, payment đã charge hoặc webhook đã xử lý không thể “rollback” chỉ vì database trở về trạng thái cũ. Cần:
- Operation ledger.
- Provider reconciliation.
- Idempotency keys.
- Compensating workflow theo chính sách.
- Audit các sự kiện không thể đảo ngược.

### 9.3. Quyền bị thu hồi phải được đối soát lại

Khi restore snapshot cũ, dữ liệu quyền truy cập và privacy deletion cần có cơ chế tái áp dụng các revocations/deletions sau snapshot; nếu không có thể hồi sinh quyền hoặc PII đã được xóa.

## 10. Phục hồi một tập dữ liệu: định nghĩa namespace chính xác

Một tập dữ liệu thường là:
- Một collection/database.
- Một keyspace/table.
- Một index.
- Một nhóm partitions/tenant.
- Một tập cache keys có namespace.

Các câu hỏi:
- Backup có hỗ trợ selective restore native không?
- Nếu không, có thể restore toàn cụm vào staging rồi export namespace cần thiết?
- Namespace có phụ thuộc schema/index/ACL hoặc data khác không?
- Cần giữ writes mới sau backup không?
- Consumer/CDC nào đang ghi vào namespace?
- Có cần đổi alias/route thay vì ghi đè trực tiếp?

### 10.1. Restore collection không chỉ là restore documents

Cần xét:
- Indexes/unique constraints.
- Validators.
- TTL indexes.
- Collation.
- Sharding/partition metadata.
- Triggers/change streams.
- Roles/privileges.
- Search/CDC downstream.
- Application schema/serializer version.

Một logical export thiếu indexes có thể phục hồi documents nhưng khiến mọi truy vấn trở nên rất chậm.

### 10.2. Namespace naming và tenant isolation

Không import source namespace A sang production B nếu chưa rõ mapping. Dùng explicit source→target map, tránh wildcard quá rộng hoặc nhầm tenant.

### 10.3. Đối soát quan hệ chéo tập dữ liệu

NoSQL có thể lưu denormalized dữ liệu:
- Bookings.
- BookingByUser.
- BookingByDay.
- InventoryCounters.
- Payments.

Restore chỉ Bookings về thời điểm cũ có thể không đồng bộ với các bảng còn lại. Phải xác định:
- Authoritative stores.
- Derived copies.
- Invariants liên bảng.
- Repair/rebuild procedures.

## 11. Phục hồi dataset an toàn qua staging

Quy trình điển hình:

~~~~mermaid
flowchart TD
    B["Verified backup at time T"] --> S["Isolated staging restore"]
    S --> X["Extract target namespace and metadata"]
    X --> D["Diff against live dataset"]
    D --> P["Choose replace vs merge vs correction"]
    P --> W["Fence writers / guard versions"]
    W --> A["Apply bounded restore plan"]
    A --> V{"Counts, hashes and invariants pass?"}
    V -->|No| Q["Quarantine and repair"]
    Q --> A
    V -->|Yes| C["Controlled routing/alias cutover"]
    C --> M["Monitor and record RPO/RTO"]
~~~~

### 11.1. Restore vào staging là lớp bảo vệ quan trọng

Không ghi đè database sản xuất chỉ để xem bản sao:
- Có thể chụp key/version/TTL.
- Có thể chạy diff.
- Có thể kiểm tra schema/index.
- Có thể xuất đúng subset.
- Có thể thử nâng cấp/migration.
- Có thể quyết định cutover hoặc abandon mà không mất data đang chạy.

### 11.2. Replace và merge khác nhau

**Replace namespace:** dữ liệu đích sẽ phản ánh dataset tại selected boundary. Phù hợp khi cần khôi phục toàn namespace và đã xử lý writes mới.

**Merge/selective update:** chỉ sửa những keys cụ thể theo expected live version; phù hợp khi còn nhiều writes hợp lệ.

Không gọi một bulk upsert lên target hiện có là “restore exact snapshot” vì target vẫn có các keys cũ không còn ở snapshot.

### 11.3. Dataset đang có writes

Nếu source tiếp tục thay đổi:
- Restore scan có thể đọc nhiều thời điểm.
- Live writes có thể ghi đè staging.
- Backfill cũ có thể ghi đè version mới.
- Deletes có thể bị bỏ.
- Cần snapshot+CDC boundary hoặc maintenance/fencing phù hợp.

## 12. Chọn giữa in-place restore và clone/cutover

| Cách | Ưu điểm | Nguy cơ |
| --- | --- | --- |
| In-place restore | Đơn giản về đường truy cập | Trộn cũ/mới, khó rollback, partial visibility |
| Clone table/collection rồi cutover | Có kiểm chứng trước; rollback dễ hơn | Cần storage, routing/cutover logic |
| Targeted conditional repair | Hẹp, bảo toàn records khác | Cần xác định chính xác keys/conflicts |
| Rebuild derived view từ source | Không phụ thuộc backup cũ | Cần capacity, source còn đúng |
| Whole cluster restore sang cluster mới | Cô lập blast radius | Tốn thời gian/capacity và thay topology |

### 12.1. Cutover không tự tạo atomicity xuyên hệ thống

Đổi alias search có thể atomic trong phạm vi index routing của engine. Nó không tự atomic cùng:
- NoSQL source writes.
- CDC checkpoint.
- Redis cache invalidation.
- External service calls.

Phải thiết kế migration barrier, fencing, versioning và monitoring.

### 12.2. Rollback target cũ không luôn an toàn

Sau cutover, old target có thể thiếu writes mới. Khi rollback phải:
- Xác nhận old target vẫn đủ mới.
- Có kế hoạch tail changes hoặc tái dựng.
- Không tự đưa traffic về snapshot stale mà không biết RPO.
- Xử lý source-of-truth authority.

## 13. Phục hồi một nhóm bản ghi: bài toán chính là chọn đúng key và version

Ví dụ 37 booking của tenant T-42 bị cập nhật amountMinor sai lúc 12:00. Từ đó:
- 8 booking có trạng thái mới hợp lệ.
- 3 booking bị xóa.
- 2 booking được refund.
- 24 booking không thay đổi nữa.

Nếu lấy document lúc 11:59 rồi replace nguyên object cho 37 keys:
- 8 thay đổi trạng thái mới bị xóa.
- 3 deletes bị hồi sinh.
- 2 refunds có thể mất dấu.
- Version đi lùi làm downstream CDC/index lệch.

Cần **khôi phục theo field và nghiệp vụ**, không mù quáng replace object.

### 13.1. Xác định affected key set

Có thể tìm từ:
- Operation/audit ledger.
- Request IDs và batch job logs.
- CDC event log còn retention.
- Versioned backup snapshot.
- Delta manifests.
- Query fingerprints và tenant scope.
- Database query theo change marker nếu đáng tin.

Nếu chỉ biết “mọi records cập nhật trong một giờ” nhưng timestamp không đáng tin, phạm vi có thể không đủ. Không tự giả định tất cả affected keys đã được xác định.

### 13.2. Tách bản cũ và bản hiện tại

Với mỗi key:
- Snapshot state tại recovery point.
- Live authoritative state.
- Những thay đổi hợp lệ sau incident.
- Những thay đổi sai cần undo.
- Delete/TTL/version state.
- Domain invariants.
- External side effects.

### 13.3. Một record có thể cần nhiều quyết định

| Key | State ở snapshot | Live hiện tại | Quyết định |
| --- | --- | --- | --- |
| A | amount=100, status=PENDING, v7 | amount=999 sai, status=PENDING, v8 | Sửa amount nếu không có write mới |
| B | amount=200, status=PENDING, v4 | amount=999 sai, status=CONFIRMED, v6 | Giữ status mới; sửa amount theo policy |
| C | amount=300, status=CONFIRMED, v9 | Deleted at v10 | Không hồi sinh nếu delete hợp lệ |
| D | amount=400, status=CONFIRMED, v11 | Refund completed, amount metadata khác | Đối soát ledger trước correction |
| E | amount=500, status=PENDING, v2 | amount=500, v2 | Không cần sửa |

Kết luận phải dựa trên **authority và lịch sử nghiệp vụ**, không chỉ so số version.

## 14. Những chiến lược chọn lọc

### 14.1. Replace toàn document

Có thể phù hợp nếu:
- Record không có writes sau recovery point.
- Toàn bộ document được xác nhận hỏng.
- Có version/conditional update.
- Không có side effects từ restore.
- Restore policy cho phép full replace.

Nhưng cần cảnh giác schema/index/TTL và field mới không có trong snapshot.

### 14.2. Patch những fields sai

Thường phù hợp hơn cho logical corruption:
- Dữ liệu lỗi nằm ở một số fields.
- Các fields khác đã có updates hợp lệ.
- Có thể xác định giá trị đúng từ backup/ledger.
- Có conditional check trên live version.
- Domain validation được áp dụng.

### 14.3. Tái tạo từ event ledger

Nếu dữ liệu có operation history đầy đủ, có thể:
- Lấy state tại trước sự cố.
- Bỏ các operations sai theo policy.
- Replay các operations hợp lệ sau sự cố.
- Tạo một **new correction event** với version hiện tại.

Không tự giả định event log giữ mọi history hoặc replay có thể an toàn cho external side effects.

### 14.4. Phục hồi record đã xóa

Phải phân biệt:
- Xóa nhầm cần khôi phục.
- Xóa hợp lệ sau snapshot.
- Xóa vì privacy/legal retention.
- TTL expiry tự nhiên.
- Soft delete/tombstone.

Khôi phục một record từ backup có thể trái chính sách nếu nó đã được xóa hợp lệ.

## 15. Delete, tombstone và resurrection

Một dòng lịch sử:

~~~~text
11:59 B-901 exists, version 18
12:05 B-901 deleted, version 19
13:00 Restore from 11:59 without checking live state
13:01 B-901 exists again -> resurrection
~~~~

Nếu deletion là hợp lệ, đây là lỗi nghiêm trọng.

### 15.1. Không chỉ xử lý records có trong snapshot

Snapshot cũ chứa record đã bị xóa sau đó. Restore logic phải biết:
- Nguồn hiện tại có record không.
- Có delete tombstone/version không.
- Delete thuộc policy nào.
- Có request erasure hay không.
- TTL đã hết chưa.

### 15.2. Tombstone retention

Nếu tombstone bị garbage collected, absence của record không tự cho biết delete khi nào. Đôi khi cần:
- Deletion ledger.
- Audit.
- Backup lineage.
- Authoritative current state.
- Rebuild toàn target từ current source.

### 15.3. Không để late events hồi sinh

Nếu projector nhận DELETE v20 rồi UPSERT v19 tới muộn, cần version-aware apply hoặc tombstone/watermark. Selective restore không nên ghi lại snapshot v19 như event v21 vô điều kiện.

### 15.4. Privacy erasure

Khôi phục backup cũ có thể tái tạo PII đã bị xóa theo yêu cầu. Phải:
- Rà soát erasure ledger/policy.
- Reapply deletions trước khi mở traffic.
- Chặn search/cache tái index dữ liệu cần xóa.
- Tuân thủ retention/cơ chế xử lý backup theo luật và policy áp dụng.
- Kiểm tra môi trường staging không lưu PII quá thời hạn.

## 16. TTL, expiration và thời gian phục hồi

Một snapshot có key với TTL còn 5 phút tại thời điểm chụp. Sau 3 ngày, restore key với TTL mặc định mới 5 phút sẽ thay đổi semantics; restore không kiểm soát có thể kéo dài tuổi dữ liệu quá policy.

Cần ghi:
- Absolute expiry instant nếu có.
- TTL policy/version.
- Snapshot time.
- Restore time.
- Source clock and timezone semantics.
- Logical expiry vs physical reclaim.

### 16.1. Expiry policy minh họa

Nếu record có expiresAt=2026-11-14T12:00Z nhưng restore lúc 2026-11-15:
- Một policy có thể **không tái tạo** record đã hết hạn.
- Nếu nghiệp vụ yêu cầu audit, audit phải được lưu theo chính sách riêng.
- Không tự “reset TTL” cho mọi record.

### 16.2. Redis TTL khác expiry của source

Nếu Redis cache bị restore từ RDB cũ, trạng thái cache không nhất thiết còn khớp source. Dữ liệu cache có thể stale và cần:
- Flush namespace có kiểm soát.
- Rewarm từ source.
- Version/invalidation generation.
- TTL re-evaluation.

### 16.3. TTL và delete không luôn giống nhau

Đối với nhiều engines, logical expiry khiến query không còn thấy record trước khi background compaction dọn bytes. Không dùng thời điểm disk reclaim làm bằng chứng của logical state tại recovery point.

## 17. Độ nhất quán khi chụp backup nhiều shards/tables

Một lỗi phổ biến: đọc collection A lúc 10:00, collection B lúc 10:05, rồi gọi đó là “snapshot toàn hệ lúc 10:00”.

Trong 5 phút:
- Một booking đã được tạo.
- Inventory đã trừ.
- Payment metadata đã đổi.

Backup ghép từ hai thời điểm có thể vi phạm invariant.

### 17.1. Consistent snapshot boundary

Nếu engine/provider hỗ trợ:
- Một snapshot timestamp H.
- Transactionally consistent export.
- Snapshot plus log watermark.
- Coordinator quản lý consistent cut.

Dùng cơ chế đó và lưu metadata.

### 17.2. Khi không có snapshot xuyên bảng

Phải thiết kế một trong các cách:
- Quiesce writes trong một window có kiểm soát.
- App-level checkpoint/barrier.
- Event sourcing/log snapshot có guarantee rõ.
- Cross-store reconciliation sau restore.
- Chấp nhận và công bố consistency limitations.

Không tự tuyên bố strong consistency nếu tool chỉ copy từng file/partition không cùng mốc.

### 17.3. Replication và quorum

Một snapshot của follower/secondary có thể chưa thấy ACKed writes tùy read/write consistency contract. Cần ghi replica lag và commit watermark, không chỉ wall-clock snapshot time.

### 17.4. Backup từ nhiều regions

Mỗi region có log/token/epoch riêng. Không cộng offsets hoặc dùng một global latest timestamp nếu multi-region writes không có total ordering. Phải xác định authority và conflict-resolution policy.

## 18. PITR: snapshot kết hợp nhật ký thay đổi

Một PITR workflow lý tưởng:

~~~~text
Full snapshot S at H0
   |
   +-- continuous valid log records after H0
   |
   +-- selected recovery frontier H1
   |
   +-- replay supported changes to H1
   |
   v
State consistent at H1
~~~~

Cần:
- Log chain đầy đủ.
- Correct ordering/transactions.
- No missing/expired segments.
- Matching source lineage/topology.
- Compatible schemas/engine versions.
- Retention đủ.
- Integrity checks.
- Provider-supported replay protocol.

### 18.1. PITR không tự đảo một thao tác sai

Nếu muốn loại một mass update lỗi nhưng giữ những updates hợp lệ sau đó, PITR thuần túy tới trước lỗi sẽ bỏ cả những updates hợp lệ. Một chiến lược có thể là:
- Restore staging tới trước lỗi.
- Xác định giá trị đúng.
- So live state.
- Áp selective correction với conditional writes.
- Reconcile domain events.

### 18.2. Retention của logs

Một consumer/backup process offline vượt log retention có thể không thể replay tới mốc mong muốn. Không seek latest rồi giả như missing history đã được khôi phục.

### 18.3. Unknown commit

Nếu sự cố xảy ra khi một write bị timeout, không được coi chắc chắn rollback. Cần operationId/idempotency ledger và authoritative read tại recovery boundary.

## 19. Java 21: mô hình kế hoạch selective restore

Trước khi ghi vào database, xây một **kế hoạch có thể kiểm tra và audit**.

~~~~java
import java.time.Instant;

public record SnapshotRecord(
        String tenantId,
        String bookingId,
        long backupVersion,
        boolean deletedAtBackup,
        Long amountMinor,
        String status,
        Instant snapshotTime
) {}

public record LiveRecord(
        String tenantId,
        String bookingId,
        long currentVersion,
        boolean deletedNow,
        Long amountMinor,
        String status
) {}

public enum RestoreAction {
    NO_CHANGE,
    REVIEW_MANUALLY,
    PATCH_APPROVED_FIELDS,
    KEEP_DELETED,
    RESTORE_DELETED_WITH_APPROVAL
}

public record RestoreProposal(
        String bookingId,
        RestoreAction action,
        long expectedLiveVersion,
        String reason
) {}
~~~~

### 19.1. Quy tắc lên kế hoạch, không tự ghi

~~~~java
public final class RestorePlanner {
    private RestorePlanner() {}

    public static RestoreProposal propose(
            SnapshotRecord oldState,
            LiveRecord liveState,
            boolean amountWasCorrupted
    ) {
        if (oldState == null || liveState == null) {
            return new RestoreProposal(
                    oldState == null ? "unknown" : oldState.bookingId(),
                    RestoreAction.REVIEW_MANUALLY,
                    -1,
                    "Missing comparison state"
            );
        }

        if (!oldState.tenantId().equals(liveState.tenantId())
                || !oldState.bookingId().equals(liveState.bookingId())) {
            return new RestoreProposal(
                    liveState.bookingId(),
                    RestoreAction.REVIEW_MANUALLY,
                    liveState.currentVersion(),
                    "Identity or tenant mismatch"
            );
        }

        if (liveState.deletedNow()) {
            return new RestoreProposal(
                    liveState.bookingId(),
                    RestoreAction.KEEP_DELETED,
                    liveState.currentVersion(),
                    "Do not resurrect without explicit approval"
            );
        }

        if (!amountWasCorrupted) {
            return new RestoreProposal(
                    liveState.bookingId(),
                    RestoreAction.NO_CHANGE,
                    liveState.currentVersion(),
                    "No approved corrective field"
            );
        }

        return new RestoreProposal(
                liveState.bookingId(),
                RestoreAction.PATCH_APPROVED_FIELDS,
                liveState.currentVersion(),
                "Amount correction requires finance validation"
        );
    }
}
~~~~

**Đoạn mã không xác nhận amount từ backup là giá trị đúng.** Nó chỉ phân loại sơ bộ, không thể thay việc xét audit/ledger và các updates hợp lệ sau snapshot.

### 19.2. Nên ghi gì vào restore plan?

- RecoveryId.
- IncidentId.
- Backup ID/snapshot time.
- Live read boundary.
- Tenant/key.
- Old version và current version.
- Desired changed fields.
- Domain approval.
- Source evidence reference.
- Idempotency operation ID.
- Expected live version.
- Outcome, audit timestamp.
- Replay/CDC handling.
- Rollback/compensation reference.

Không đưa PII thô hoặc secret vào logs nếu không cần.

## 20. Conditional patch thay vì blind replace

Một ý tưởng với MongoDB:

~~~~java
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class ApprovedBookingRepair {
    public static boolean repairAmount(
            MongoCollection<Document> collection,
            String tenantIdFromTrustedRecoveryScope,
            String bookingId,
            long expectedCurrentVersion,
            long approvedAmountMinor
    ) {
        if (approvedAmountMinor < 0) {
            throw new IllegalArgumentException("negative amount");
        }

        // Caller must have approved this key, amount, and operationId.
        UpdateResult result = collection.updateOne(
                and(
                        eq("tenantId", tenantIdFromTrustedRecoveryScope),
                        eq("bookingId", bookingId),
                        eq("version", expectedCurrentVersion),
                        ne("deleted", true)
                ),
                combine(
                        set("amountMinor", approvedAmountMinor),
                        inc("version", 1L)
                )
        );

        return result.getMatchedCount() == 1L;
    }
}
~~~~

### 20.1. Những điều được bảo vệ

- Tenant không lấy từ untrusted client.
- Chỉ thay field đã duyệt.
- Có compare-and-set trên current version.
- Không vô tình thay status mới.
- Không hồi sinh document deleted.
- Tạo version mới theo quy tắc ví dụ thay vì đặt lùi về backupVersion.

### 20.2. Những điều vẫn thiếu

- OperationId/idempotency ledger atomic với write.
- Audit event và domain approval.
- Xác minh approvedAmountMinor từ ledger đúng.
- Quyền recovery và 4-eyes review.
- Bảo vệ các deletes không có cờ deleted mà đã hard-delete.
- Phân biệt matchedCount=0 do conflict/absence/permission.
- Unknown commit result khi timeout.
- Tác động tới CDC/projections.
- Schema migration.
- Transaction boundary nếu sửa nhiều records có invariant chung.

**Không chạy đoạn ví dụ trên production như một tiện ích sửa dữ liệu.** Nó minh họa pattern conditional patch.

## 21. Idempotency, retries và phục hồi theo batch

Một batch restore có thể:
- 100 keys đã commit.
- 20 keys timeout.
- 5 keys conflict.
- Process restart.

Nếu chạy lại nguyên batch:
- Những writes đã commit không nên tạo side effects lần hai.
- Những conflicts phải được review.
- Unknown commits phải được reconcile.
- Không tự set toàn bộ batch DONE.

### 21.1. Operation ledger

Một record:

~~~~json
{
  "recoveryId":"REC-517",
  "operationId":"REC-517:T42:B901:amount",
  "key":"T42#B901",
  "requestedChange":"amountMinor-correction",
  "expectedVersion":21,
  "state":"COMMITTED",
  "resultingVersion":22
}
~~~~

Ledger nên có consistency/transaction guarantees phù hợp với target, hoặc thiết kế reconcile với unknown outcomes.

### 21.2. Retry chỉ khi điều kiện còn đúng

Nếu expectedVersion=21 và live đã thành v23 do user update:
- Không retry cưỡng ép bằng cách thay expectedVersion theo giá trị mới.
- Reread, xác định thay đổi mới có hợp lệ không.
- Recalculate correction.
- Có thể yêu cầu manual approval.

### 21.3. Bulk upsert không phải atomic multi-record transaction

Một batch có thể partial success. Không ghi checkpoint whole batch nếu một số entries failed. Đếm:
- Planned.
- Applied.
- Skipped.
- Conflict.
- Unknown.
- Failed.
- Verified.

### 21.4. External side effects

Restore operations có thể kích hoạt event listeners. Cần phân biệt:
- State correction.
- Business command.
- Historical replay.
- Notification/payment.

Không replay lịch sử như thể user vừa xác nhận/cancel booking lần nữa.

## 22. Reconciliation: chứng minh dữ liệu sau restore đã đúng

Tối thiểu:
- **Membership:** key có/không đúng theo authority.
- **Version:** trạng thái không bị lùi trái policy.
- **Field values:** giá trị được phục hồi hoặc giữ lại đúng.
- **Schema:** kiểu/codec hợp lệ.
- **Index/query path:** queries nhìn thấy target state đúng theo freshness contract.
- **Cross-store invariants:** counters, references, constraints.
- **Security:** tenant/role/privacy effects.
- **Completeness:** affected key set đầy đủ.

### 22.1. Không chỉ so row counts

Source và target đều có 1 triệu rows nhưng một bên có A, bên kia có B. Count bằng nhau nhưng membership sai.

### 22.2. Canonical digest

Tính digest của những field authoritative cần so, sau khi:
- Chuẩn hóa thứ tự fields.
- Kiểu/precision số.
- Null vs absent.
- Timestamp/timezone.
- Unicode.
- Schema/transform version.
- Delete semantics.

So source/target cùng boundary và policy; raw JSON hash có thể khác dù business state tương đương.

### 22.3. Version cao hơn không tự là đúng

Một record v30 có thể là kết quả của mass update sai, trong khi v29 đúng. Không lấy max version làm winner nếu mục tiêu là undo một thao tác sai. **Version guard bảo vệ concurrency**, còn business correctness phải dựa vào nguồn sự thật/audit.

### 22.4. Snapshot boundary

Khi source vẫn ghi trong lúc verify:
- Source v31 tại T1.
- Projection v30 tại T2.
- Mismatch có thể là legitimate lag.

Cần consistent read boundary, versioned comparison hoặc grace window, không báo false corruption.

## 23. MongoDB: cluster, collection và document restore

Các cơ chế có thể gồm:
- Backup công cụ/quản trị hỗ trợ consistent snapshots.
- Physical backups.
- Logical dumps/exports.
- Oplog/change-stream history khi dùng đúng backup/PITR workflow.
- Restore vào deployment staging.
- Export/import một namespace.
- Selective document reconciliation.

### 23.1. Cluster/sharded deployment

Với sharded MongoDB, không nên tự copy snapshots rời từng shard rồi coi là một consistent cluster backup nếu không có coordinator được hỗ trợ. Cần:
- Topology/config server metadata.
- Consistency boundary.
- Shard identities.
- Transactions/chunk migrations.
- Index definitions.
- Authentication/encryption metadata.
- Restore version compatibility.

### 23.2. Logical namespace restore

Một logical dump có thể chứa documents/index metadata theo tool và options. Khi chỉ restore collection:
- Chọn namespace rõ.
- Tránh overwrite collection production khi chưa kiểm tra.
- Restore vào staging namespace.
- Xác minh unique indexes, validators, TTL, collation.
- So data types BSON.
- Cutover hoặc selective repair.

### 23.3. Document-level

Nếu chỉ cần 37 documents:
- Lấy bản lịch sử từ isolated restore.
- Dùng authoritative key và tenant scope.
- Xác minh versions và trường cần sửa.
- Conditional patch.
- Kiểm tra CDC/search/cache.

Không dùng raw dump of documents rồi replaceMany/replaceOne vô điều kiện.

### 23.4. Oplog/PITR caveats

Một snapshot logic và oplog được ghép tùy ý chưa chắc hỗ trợ PITR khi có topology change, transaction, balancer hoặc log gaps. Dùng quy trình đã được công cụ/nhà cung cấp xác nhận; không tự parse resume token rồi chọn mốc recovery.

### 23.5. Change streams

Một restore có thể làm change stream consumers cần rebootstrap hoặc thay token lineage. Không coi resume token cũ portable sang cluster mới. Lập kế hoạch checkpoint reset/rebuild và side effects.

## 24. DynamoDB: table backup/PITR và selective items

Với DynamoDB, các quy trình backup/PITR có semantics theo table và thời gian được dịch vụ hỗ trợ. Một điểm vận hành quan trọng là restore thường **tạo một table mới** thay vì ghi đè table đang chạy tại chỗ.

### 24.1. Table-level restore

- Chọn backup hoặc recovery time được hỗ trợ.
- Restore tới new table.
- Kiểm tra schema, indexes, encryption/capacity/settings theo kết quả thực.
- Áp dụng lại những cấu hình không tự được restore nếu cần.
- Rà IAM, streams, TTL, alarms, autoscaling và integrations.
- Dùng application routing/cutover có kiểm soát.

Không giả định mọi table settings, stream configurations, global-table replication và resource policies được copy nguyên vẹn: đối chiếu tài liệu của chế độ restore cụ thể.

### 24.2. Item-level restore

Nếu muốn sửa vài items:
- Restore source table backup tới staging table.
- Query/scan đúng keys với consistent read theo khả năng hỗ trợ.
- Đối chiếu live table.
- Dùng conditional PutItem/UpdateItem trên live table.
- Không dùng unconditional batch import ghi đè mới.
- Xử lý retries/idempotency, delete semantics.

### 24.3. PITR và global tables

Một table trong global-table deployment có region replication/conflict semantics riêng. Phải xác định:
- Region/table authority.
- Recovery point ở region nào.
- Restore tạo resource riêng.
- Cách tham gia global table sau restore.
- Replication/stream side effects.
- Write conflicts và ordering.

Không suy một restore ở region A tự khôi phục trạng thái transactionally consistent trên mọi regions.

### 24.4. DynamoDB Streams

Streams có retention hữu hạn; không mặc định nó đủ để replay lịch sử dài ngày từ table backup. Nếu cần current-state projection, staging table restore + rebuild có thể phù hợp hơn cố replay missing events.

## 25. Cassandra: keyspace/table snapshot và cluster consistency

Cassandra có cơ chế snapshot/backups của SSTables và commitlog tùy triển khai. Một số tình huống restore:
- Full cluster/new nodes.
- Keyspace/table snapshot.
- Selected partitions/rows qua query/export sau staging.
- Replica repair/rebuild khi chỉ một node lỗi.

### 25.1. Không copy SSTables vô điều kiện

SSTables gắn với:
- Table schema/IDs.
- Token ranges/ownership.
- Compression/format version.
- Tombstone/TTL state.
- Compaction/repair history.

Restore phải theo supported procedure/tooling. Không suy copy files vào data directory trên cluster đang chạy là đủ hoặc an toàn.

### 25.2. Snapshot theo node không tự có global atomicity

Mỗi replica/node có thể ở watermark khác nhau. Với cluster:
- Chọn consistency boundary.
- Bảo đảm schema/topology compatible.
- Xem commitlog retention.
- Xác minh replica synchronization.
- Repair/rebuild theo policy.

### 25.3. TTL/tombstones

Một snapshot chứa old SSTables có thể mang tombstones và TTL đã thay đổi theo thời gian. Không để import dữ liệu cũ hồi sinh records đã xóa hoặc tạo lại TTL từ đầu mà không kiểm soát.

### 25.4. Selective partition/row

Nếu chỉ vài partitions bị sai:
- Restore table/keyspace vào staging.
- Extract authoritative rows.
- Dùng app-level conditional restore nếu semantics cho phép.
- Kiểm tra wide partitions, clustering order, timestamps/TTL.
- Tránh viết back với timestamp làm stale write thắng unexpectedly.

## 26. HBase: table snapshots, clone và row-level repair

HBase có table/region snapshot, clone/restore và WAL/replication mechanisms theo phiên bản/triển khai.

### 26.1. Table-level

- Xác định table snapshot ID.
- Chọn clone snapshot sang table mới khi cần staging.
- Kiểm tra column families, compression, version/TTL, region assignment.
- Phục hồi bằng supported admin procedure.
- Reconcile application index/read models.
- Cutover với quyền và endpoint phù hợp.

### 26.2. Row-level

Một row có thể có nhiều cell versions và delete markers. Chọn row từ snapshot không đủ nếu:
- Column family TTL đã làm dữ liệu hết hạn.
- Delete marker hợp lệ sau snapshot.
- Timestamp cells quyết định visibility.
- Application-level version có semantics khác HBase timestamp.

Cần xem lịch sử và domain policy trước khi Put/Delete.

### 26.3. Region split/merge

Không dùng một region snapshot/token từ topology cũ một cách tùy tiện trên region mới. Theo supported restore/clone workflow.

## 27. Redis: RDB/AOF thường mang phạm vi instance/dataset

Redis RDB/AOF giúp khôi phục persistent state của Redis theo cấu hình và durability contract, nhưng không tự tương đương selective restore một tập key.

### 27.1. Nếu Redis chỉ là cache

Thường nên:
- Giữ source of truth.
- Rebuild/warm-up cache.
- Giới hạn origin load.
- Invalidate namespace/generation.
- Không phục hồi stale entries từ RDB cũ nếu làm sai source state.

### 27.2. Nếu Redis giữ dữ liệu có authority

Cần xét:
- RDB/AOF persistence configuration.
- Last fsync/ACK guarantees.
- Replication/failover.
- Cluster shards/hash slots.
- Memory/eviction policies.
- TTL/expiry state.
- Lua/stream consumer groups.
- Key ACL/namespace.

Không cho rằng Redis replication là backup.

### 27.3. Chọn lọc keys

Một hướng:
- Restore snapshot vào Redis staging riêng.
- Trích keys thuộc allowlist/namespace.
- Kiểm tra type, TTL, owner/tenant và live state.
- Apply có điều kiện hoặc rebuild từ authoritative source.
- Không dùng restore command để ghi đè key hiện tại mù.

### 27.4. Redis Streams

Nếu Streams dùng làm event log, trimming/retention có thể khiến một phần history không còn. RDB snapshot cũ không tự đảm bảo khôi phục exactly-once consumer effects. Cần event IDs, consumer checkpoints và idempotency/reconciliation.

## 28. Search index: restore hay rebuild?

Elasticsearch/OpenSearch có index snapshot/restore và alias/index routing. Nhưng search index thường là **dữ liệu dẫn xuất**.

Nếu source NoSQL còn đúng:
- Reindex từ source thường có lợi hơn restore snapshot search cũ.
- Cần bảo vệ source trước backfill quá tải.
- Dùng staging index.
- Reapply CDC tail cho writes sau snapshot.
- Verify membership/versions/digests.
- Controlled alias cutover.

Nếu source mất nhưng search còn:
- Search projection có thể thiếu fields/transactions.
- Không tự coi search index là source authority.
- Có thể dùng như một nguồn bằng chứng bổ sung, phải ghi rõ giới hạn.

### 28.1. Alias cutover và ongoing CDC

Alias switch không tự đồng bộ cùng source commit/consumer checkpoint. Cần capture boundary, version guard và active tail sau cutover.

### 28.2. Search visibility

Write được index nhận không tự được query thấy ngay nếu refresh chưa xảy ra. Verification phải xét visibility semantics, không báo corruption ngay chỉ vì search chưa refresh.

## 29. Bảo mật phục hồi: backup cũng là dữ liệu nhạy cảm

Backup có thể chứa:
- Personal data.
- Credentials/hash/token.
- Payment metadata.
- Internal identifiers.
- Business secrets.
- Audit trails.

Cần:
- Encryption at rest/in transit.
- KMS/key vault và key recovery.
- Least-privilege backup-reader/restore-writer separation.
- Immutable/off-account copies khi phù hợp.
- Audit access.
- Retention/deletion.
- Quarantine staging networks.
- Không cho staging phát email/payment.
- Không upload raw backup vào code repo/ticket.
- Redaction/synthetic fixtures cho dev/test.

### 29.1. 4-eyes approval

Với selective restore ảnh hưởng tiền/quyền:
- Người lập diff.
- Người phê duyệt.
- Người chạy.
- Audit evidence.
- Independent verify.

Nếu một script có thể sửa 37 booking, nó cần quyền chặt hơn công cụ xem logs thông thường.

### 29.2. Backup keys cũng cần được khôi phục

Một backup được mã hóa nhưng key bị xóa, revoked hoặc region KMS không khả dụng có thể không restore được trong RTO. Disaster recovery drill phải thử khả năng decrypt với quyền và quy trình thật.

### 29.3. Offsite và immutability

Lưu backup trong cùng cluster/account mà attacker có thể xóa không đủ cho threat model ransomware. Có thể cần versioned/immutable/off-account/off-region copies theo policy và recovery capabilities của provider.

## 30. Cutover, fencing và tránh split-brain

Khi restore cluster mới:
- Có thể old cluster phục hồi trở lại và bắt đầu nhận writes.
- Một service giữ connection tới old endpoint.
- Một CDC connector ghi tới target cũ.
- Two regions có thể cùng nhận writes nếu routing/fencing lỗi.

Cần:
- Write-owner election/fencing.
- Explicit authority epoch.
- Routing config review.
- Connection pool refresh.
- Producer/consumer checkpoints.
- Rollback conditions.
- Monitoring writes trên old endpoint.

**Không chỉ đổi DNS rồi tin rằng mọi clients lập tức chuyển đúng**, vì DNS cache và connections hiện hữu còn sống.

### 30.1. Recovery epoch

Một generation/epoch mới có thể giúp:
- Gắn nguồn authoritative.
- Chặn stale worker ghi.
- Phân biệt checkpoint cũ/mới.
- Ghi audit.

Cơ chế phải được engine/app hỗ trợ, không tự thêm số epoch rồi cho rằng mọi components đều kiểm tra.

### 30.2. Rollback sau cutover

Rollback có thể làm mất writes đã ghi trên cluster mới nếu old cluster không bắt kịp. Cần kế hoạch failback/reconciliation, không xem route-back là miễn phí.

## 31. Backup integrity và restore verification

Một backup job báo SUCCESS chưa đủ. Phải kiểm tra:
- Backup manifest có đủ files/segments.
- Checksum/integrity.
- Decrypt khả dụng.
- Engine version compatible.
- Snapshot/log boundary hợp lệ.
- Schema/index/ACL.
- Restore chạy được trên cluster mới.
- Counts và canonical digests.
- Query correctness.
- Domain invariants.
- RPO/RTO đo thực tế.

### 31.1. Không chỉ so row count

Hai datasets cùng 1 triệu rows vẫn có thể khác key membership. So:
- Key sets.
- Per-key version.
- Canonical payload digest.
- Delete markers.
- Aggregate sums/invariants.

### 31.2. Checksums của backup không là business correctness

Checksum chứng minh file không đổi so với dữ liệu đã ghi khi checksum được tạo. Nếu source đã bị corrupt trước backup, checksum vẫn có thể đúng cho dữ liệu sai.

### 31.3. Sampling vs full verification

- Full verification tốt hơn cho dữ liệu tài chính/cực kỳ quan trọng nếu khả thi.
- Sampling có thể dùng cho dataset lớn để lấy nhanh confidence nhưng không chứng minh tuyệt đối.
- Buckets/Merkle digests hỗ trợ khoanh vùng.
- Bao gồm hot partitions và deletes trong scope.

### 31.4. Recovery success là một kết luận có bằng chứng

Không đánh dấu COMPLETE chỉ vì restore command exit 0. Cần:
- Data state matches intended contract.
- No unresolved critical conflicts.
- Access control đúng.
- Applications read/write thành công.
- No stale side effects.
- Performance ổn định.
- Monitoring đã hoạt động.

## 32. Metrics trước và trong phục hồi

| Metric | Ý nghĩa |
| --- | --- |
| Backup age | Bản gần nhất cách hiện tại bao lâu |
| Last verified restore | Lần gần nhất restore thử thành công |
| Backup bytes / throughput | Dự kiến thời gian sao lưu |
| Restore bytes/s | RTO khả thi |
| Snapshot/log gap | PITR có đủ chuỗi không |
| Available retention horizon | Có khôi phục được tới mốc cần không |
| Actual recovery point | RPO thực tế |
| Restore phase durations | Detect/provision/apply/verify/cutover |
| Data checksum mismatch | Tính toàn vẹn |
| Missing/phantom keys | Membership sai |
| Version conflicts | Live writes va chạm correction |
| Unresolved unknown commits | Các thao tác chưa biết có commit không |
| CDC/index lag | Read models đã bắt kịp chưa |
| TTL/tombstone anomalies | Nguy cơ hồi sinh dữ liệu |
| Auth/tenant mismatches | Nguy cơ lộ data |
| Error rate / p99 / source load | Chất lượng dịch vụ sau cutover |
| Old-cluster writes after cutover | Split-brain/stale connections |
| Security/erasure reconciliation | Xóa hợp lệ có được bảo tồn không |

### 32.1. Cần lưu kết quả drill

Mỗi restore drill nên ghi:
- Recovery scenario.
- Backup ID.
- Snapshot timestamp.
- Source/target versions.
- Duration từng phase.
- Integrity/consistency results.
- Người thực hiện/phê duyệt.
- Gaps và blockers.
- Runbook updates.

## 33. Diễn tập DR: các kịch bản nên có

| Kịch bản | Mục tiêu |
| --- | --- |
| Mất một replica | Xác nhận repair/rebuild không cần whole-cluster restore |
| Toàn cụm mất storage | Test restore full backup + logs |
| Backup cuối cách 6 giờ | Đo actual RPO không có PITR |
| Một collection bị drop | Dataset-level staging restore |
| Một bảng được update sai | Selective correction không làm mất writes mới |
| Một nhóm records bị hard-delete | Xác định tombstone/erasure semantics |
| Restore snapshot trước privilege revocation | Không hồi sinh quyền |
| Backup encryption key không sẵn | Xác nhận DR dependency |
| Log segment mất trong PITR chain | Fail rõ, không skip rồi tuyên bố recovered |
| Multi-region failover | Không split-brain / routing sai |
| CDC consumer token invalid sau restore | Rebootstrap/reindex an toàn |
| Search index mất | Rebuild từ source và cutover |
| Redis cache mất | Cache warm-up không làm origin quá tải |
| Schema/driver version đổi | Compatibility/migration checks |
| Huge dataset và slow storage | RTO đo thực tế |
| 100 selective updates, 20 timeouts | Idempotent/resumable repair |
| Source bị corrupt trước backup | Không xem checksum backup là correctness |
| Partial batch restore | Track successes/conflicts/unknowns |
| TTL hết hạn khi staging | Không kéo dài tuổi dữ liệu trái policy |
| Concurrent live writes khi repair | Conditional version guard |
| Restore kích hoạt notification | Không gửi lại side effects |
| Restore privacy-deleted records | Erasure ledger prevents resurrection |

### 33.1. Fault injection có giới hạn

Không gây mất dữ liệu thật hoặc ảnh hưởng khách hàng chỉ để thử. Dùng:
- Isolated test cluster.
- Synthetic tenant.
- Approved backup copies.
- Bounded workload.
- Kill switch.
- Clear recovery ownership.

### 33.2. Test nên có assertions

- RPO ≤ objective hoặc incident được đánh dấu vi phạm đúng.
- RTO ≤ objective hoặc đưa vào kế hoạch cải thiện.
- Không có lost acknowledged writes vượt contract.
- Không có unauthorized resurrection.
- Không có cross-tenant leakage.
- Không có duplicate external business effects.
- Invariants vẫn giữ.
- Search/cache/CDC sync đúng.
- Recovery records traceable và repeatable.

## 34. Runbook: khôi phục toàn cụm

### Bước 1 — Chốt authority

Xác định cluster cũ còn ghi hay không, quorum còn không, có nguy cơ split-brain không. Fencing old writers nếu cần theo supported protocol.

### Bước 2 — Chọn recovery point

- Xác minh full snapshot.
- Xác minh incremental/log chain.
- Tính estimated RPO.
- Chốt recovery boundary.
- Ghi những writes có thể mất.

### Bước 3 — Lấy keys và provision môi trường

- KMS/access.
- Engine version.
- Cluster capacity.
- Network/TLS.
- Backup manifest.
- Disk/IO headroom.

### Bước 4 — Restore

Thực hiện supported cluster restore; không trộn file copies tùy ý giữa shards hoặc regions.

### Bước 5 — Verify

- Cluster health.
- Schema/index.
- Data counts/membership.
- Business invariants.
- Security/permissions.
- Synthetic reads/writes.
- RPO/unknown transactions.

### Bước 6 — Cutover

- Route applications.
- Fence old endpoints.
- Reconfigure CDC/projections.
- Monitor.
- Prepare failback.

### Bước 7 — Hậu kiểm

- Incident report.
- Actual RPO/RTO.
- Đối soát lost-write candidates.
- Backup retention/key issues.
- DR drill remediation.

## 35. Runbook: khôi phục một dataset

### Bước 1 — Xác nhận phạm vi

Collection/table/keyspace/index nào, schema nào, tenant nào? Phụ thuộc liên bảng/CDC gì?

### Bước 2 — Phục hồi staging

Restore backup tới namespace hoặc cluster cách ly; không overwrite production ngay.

### Bước 3 — Chọn chiến lược

- Full namespace replace.
- Clone + alias/routing cutover.
- Merge có điều kiện.
- Rebuild từ authoritative source nếu là projection.

### Bước 4 — Bảo vệ updates mới

- Snapshot/CDC boundary hoặc maintenance window.
- Version guards.
- Fencing writers.
- Tombstone/delete handling.
- Schema/index/permission checks.

### Bước 5 — Apply, verify, cutover

- Counts/key sets/hashes.
- Business invariants.
- Tenant permissions.
- Index visibility/CDC lag.
- Controlled routing.
- Rollback readiness.

## 36. Runbook: khôi phục một nhóm bản ghi

### Bước 1 — Lập affected key set

Dùng audit/CDC/log/backup diff đáng tin. Ghi completeness/confidence. Không lấy vài IDs từ ticket rồi tự cho là toàn bộ.

### Bước 2 — Lấy historical state an toàn

Restore backup vào staging để đọc đúng backup version/time. Ghi schema/types/TTL.

### Bước 3 — Đọc live authoritative state

Cùng tenant scope, consistency phù hợp, version, deleted status, later valid writes, external ledger.

### Bước 4 — Lập diff và approval

Mỗi record có:
- ExpectedLiveVersion.
- Desired fields.
- Preservation of later writes.
- Side-effect policy.
- Delete/privacy decision.
- Owner/approver.

### Bước 5 — Conditional patch

Không blind replace. Dùng operation IDs, bounded batches, version guard, tracking conflicts/unknown commits.

### Bước 6 — Đối soát

- Per-key source state.
- Fields không được chạm.
- Cross-store views.
- Audit/financial ledger.
- Cache/CDC/index freshness.
- Tenant/erasure compliance.

### Bước 7 — Kết thúc

Ghi applied/skipped/conflicted/unknowns/failed, kết quả verify, actual RPO/RTO cho phạm vi, và những records còn cần xử lý.

## 37. Những hiểu nhầm thường gặp

1. **“Replica là backup.”** Xóa/corruption có thể replicate.
2. **“Backup SUCCESS nghĩa restore được.”** Cần diễn tập restore.
3. **“Physical volume snapshot luôn transactionally consistent.”** Cần engine-supported boundary.
4. **“Một timestamp UTC là global snapshot.”** Multi-shard có thể cần checkpoint vector.
5. **“Restore full cluster luôn an toàn nhất.”** Có thể làm mất writes hợp lệ.
6. **“Restore từ snapshot chỉ làm mất thời gian, không làm đổi dữ liệu mới.”** Sai.
7. **“PITR luôn có sẵn nếu có WAL/oplog.”** Cần chain và protocol.
8. **“Log chain có gap cứ skip rồi replay tiếp.”** Không chứng minh state đúng.
9. **“RPO theo lịch snapshot bằng RPO thực.”** Phải xác minh backup/log frontier.
10. **“RTO chỉ là restore command duration.”** Còn detect/provision/verify/cutover.
11. **“Restore collection chỉ cần documents.”** Còn indexes, TTL, ACL, schema.
12. **“Import backup namespace trực tiếp vào live luôn ít rủi ro.”** Có partial visibility/overwrite.
13. **“Bulk upsert đồng nghĩa exact restore.”** Phantom keys có thể còn.
14. **“Một record trong backup cũ luôn đúng hơn live.”** Live có updates hợp lệ.
15. **“Dùng backupVersion ghi đè currentVersion.”** Làm version lùi.
16. **“Version guard tự xác nhận business correctness.”** Không.
17. **“Nếu document bị hard-delete thì cứ hồi sinh từ backup.”** Có delete/privacy policy.
18. **“TTL có thể reset tùy ý khi restore.”** Có thể kéo dài retention sai.
19. **“Search index là authority khi source mất.”** Có thể incomplete/stale.
20. **“Cache snapshot nên restore dù source hiện tại đúng.”** Có nguy cơ stale.
21. **“DynamoDB table restore tự ghi đè table cũ.”** Thường tạo table mới.
22. **“Mọi table settings đều tự copy đúng sau restore.”** Phải xác minh.
23. **“SSTable files copy tùy ý là Cassandra restore.”** Cần supported procedure.
24. **“HBase row version giống app sourceVersion.”** Không tự đồng nhất.
25. **“Redis RDB/AOF luôn hỗ trợ chọn vài keys native.”** Không tự suy.
26. **“Backup từ một secondary luôn có mọi ACKed writes.”** Phụ thuộc consistency/lag.
27. **“Một collection được restore là các collections khác tự nhất quán.”** Có cross-table invariants.
28. **“CDC sẽ tự replay an toàn sau restore.”** Có token/side-effect issues.
29. **“Restore events có thể gửi email/payment lại.”** Nguy cơ duplicate side effects.
30. **“Timeout restore write nghĩa không commit.”** Có UNKNOWN.
31. **“Retry batch không cần operationId.”** Có thể áp hai lần.
32. **“MatchedCount=0 nghĩa record không tồn tại.”** Có thể conflict.
33. **“Một lần compare counts đủ verify.”** Có thể membership/value mismatch.
34. **“Checksum backup chứng minh source đúng.”** Chỉ integrity từ lúc checksum.
35. **“Một alias switch tự đồng bộ cùng checkpoint.”** Không.
36. **“DNS cutover làm mọi connections đổi ngay.”** Cache/connections có thể còn.
37. **“Rollback routing không thể mất writes.”** Có thể old cluster stale.
38. **“Whole cluster restore không liên quan security.”** Có ACL/PII/revocations.
39. **“Backup encryption key luôn có sẵn lúc DR.”** Phải thử.
40. **“Snapshot cũ chứa user bị xóa có thể mở lại bình thường.”** Privacy risk.
41. **“DR drill có thể dùng production data tùy tiện.”** Cần quyền/cách ly.
42. **“Restore success không cần business invariants.”** Cần.
43. **“Không cần đo restore speed với full-sized dataset.”** RTO có thể sai.
44. **“Replication region A giúp PITR mọi region.”** Semantics khác.
45. **“Record-level restore luôn chỉ một write.”** Có domain consistency và projections.
46. **“Source corrected thì search/cache tự đúng tức thì.”** Có eventual lag.
47. **“Một lỗi logical mass update nên restore cả cụm ngay.”** Thường mất nhiều writes đúng.
48. **“Không cần lưu recovery ledger.”** Khó retry/audit.
49. **“COMPLETE khi command exit 0.”** Chưa verify.
50. **“Kế hoạch restore có thể lập sau khi thảm họa xảy ra.”** Không đảm bảo RPO/RTO.

## 38. Bài tập tình huống: khôi phục Bookings trên ba phạm vi

Hệ thống:
- Java 21 services, MongoDB source chính.
- DynamoDB table cho một read model theo tenant.
- Redis cache.
- OpenSearch search index.
- CDC/outbox events.
- Multi-region replication.
- Daily snapshots lúc 00:00 UTC.
- PITR nếu chuỗi log còn đủ.
- RPO target 5 phút, RTO target 60 phút.
- Một số writes vừa ACK có thể còn kết quả UNKNOWN ở phía client.
- Dữ liệu chứa PII và có yêu cầu xóa hợp lệ.

### A. Phục hồi toàn cụm

Cluster không truy cập được lúc 12:00, backup snapshot cuối lúc 00:00 và logs liên tục tới 11:57.

1. Recovery point nào khả thi nếu PITR hợp lệ?
2. Estimated RPO theo thời gian?
3. Vì sao restore tới 00:00 vi phạm RPO?
4. Những steps nào tính vào RTO?
5. Cách đảm bảo old cluster không nhận writes sau cutover?
6. Cần verify what data/ACL/index/CDC?

### B. Một collection bị drop

Collection bookings bị drop nhưng các collections khác còn đúng.

1. Có nên restore whole cluster về 00:00 không?
2. Làm sao restore collection vào staging?
3. Index, validators, TTL và sharding metadata cần làm gì?
4. Làm sao bảo tồn writes mới của các collections liên quan?
5. Khi nào chọn cutover namespace thay selective merge?

### C. 37 records cập nhật sai

Một batch job thay amountMinor cho 37 bookings lúc 12:00; 8 records có update trạng thái hợp lệ sau đó, 3 bị delete, 2 được refund.

1. Vì sao blind document replace là sai?
2. Thiết kế per-key diff cần field/version nào?
3. Nhóm deleted có được restore không?
4. Nhóm refund cần đối soát nguồn nào?
5. Conditional patch và operationId dùng để làm gì?
6. Nếu currentVersion thay đổi giữa read và write, xử lý thế nào?

### D. PITR

Có snapshot S0 lúc 00:00 nhưng thiếu một segment log lúc 11:20.

1. Có thể khẳng định restored state ở 11:57 không?
2. Nếu chỉ có dữ liệu nguồn hiện tại, có thể rebuild mọi historical events không?
3. Có thể dùng alternate archive/event ledger nào?
4. Recovery coordinator nên báo trạng thái gì?

### E. TTL và tombstone

Một record đã hết TTL lúc 10:00; một record khác bị xóa theo privacy request lúc 11:00.

1. Có được reset TTL khi restore lúc 13:00?
2. Làm sao ngăn privacy record resurrection?
3. Tombstone/erasure ledger cần được xử lý thế nào?
4. Có nên rebuild Redis cache từ source hiện tại?

### F. DynamoDB

Restore một table từ PITR:
1. Target table mới ảnh hưởng routing thế nào?
2. Cần kiểm tra index, TTL, IAM, streams, capacity ra sao?
3. Nếu chỉ cần sửa vài items, nên làm thế nào?
4. Global table multi-region có caveats gì?
5. Conditional writes khi import có ý nghĩa gì?

### G. Cassandra/HBase

1. Vì sao SSTable snapshot không tự là global atomic cluster snapshot?
2. Token/region assignments quan trọng gì?
3. TTL/tombstone có thể gây resurrection thế nào?
4. Có nên copy files trực tiếp vào cluster đang chạy không?
5. Row-level restore cần app version và source policy ra sao?

### H. Redis/Search

1. Khi Redis chỉ là cache, restore snapshot cũ hay rewarm từ source?
2. Nếu search index mất, có thể reindex từ MongoDB thế nào?
3. Dùng staging index và alias switch ra sao?
4. Vì sao alias cutover chưa tự đồng bộ CDC checkpoint?
5. Làm sao không làm source quá tải khi rebuild?

### I. Security và governance

1. Ai được đọc production backup chứa PII?
2. Backup keys/KMS phục hồi thế nào?
3. Có cần 4-eyes approval với price corrections?
4. Evidence store ghi recoveryId/manifests ra sao?
5. Retention và privacy erasure được bảo toàn thế nào?

### J. Fault injection

Lập ít nhất 12 tests:
- Một replica chết.
- Whole-cluster storage loss.
- Missing PITR log segment.
- Backup key không sẵn.
- Collection drop.
- 37 records mass update.
- Concurrent writes during restore.
- Delete/TTL resurrection attempt.
- CDC token invalid after cutover.
- Search reindex lag.
- Redis cache cold-start stampede.
- Batch timeout/partial success.
- Multi-region split-brain.
- Old clients ghi vào old cluster sau DNS switch.
- Schema mismatch.
- Backup corruption đã tồn tại trước snapshot.

Mỗi test ghi:
- Recovery scope.
- Backup/log selection.
- Expected boundary.
- Conditional write/rollback strategy.
- RPO/RTO.
- Verification evidence.
- Pass/fail criteria.

### K. Đánh giá một đề xuất sai

Đồng nghiệp nói:

> “Hệ có daily backups. Cứ restore cả cluster về 00:00 mỗi khi xảy ra lỗi dữ liệu. Nếu chỉ vài booking sai, lấy document trong backup ghi đè. Không cần so live version vì dữ liệu trong backup chắc chắn đúng. Records bị xóa cũng khôi phục để khỏi thiếu. Khi index có count bằng source là xong. Thêm DNS switch là kết thúc DR.”

Phản biện:
- RPO/RTO.
- Writes sau snapshot.
- Scope và cost.
- Concurrency/version guard.
- Deleted/TTL/privacy.
- Audit/financial side effects.
- Counts vs membership/hash.
- CDC/index lag.
- Split-brain/fencing.
- Backup restore verification.

### Hướng giải

Một kế hoạch đúng có thể:
1. Xác định authority, phạm vi lỗi và recovery boundary.
2. Chọn whole cluster/dataset/records theo impact và dependency.
3. Kiểm chứng backup/PITR chain, encryption keys và restore compatibility.
4. Restore vào isolated staging khi khả thi.
5. So source historical/live state, xác định writes hợp lệ cần giữ.
6. Dùng version-aware, idempotent conditional patch cho selective repair.
7. Không hồi sinh deletes/TTL/PII trái policy.
8. Rebuild/verify cache/search/CDC.
9. Fencing old write owners và controlled cutover.
10. Verify counts, key membership, digests, domain invariants, auth.
11. Đo actual RPO/RTO, ghi recovery ledger và postmortem.
12. Diễn tập định kỳ để phát hiện blockers trước sự cố.

## 39. Checklist sẵn sàng vận hành

1. **Đã định nghĩa RPO/RTO theo ứng dụng và dữ liệu?**
2. **Biết nguồn authoritative của từng entity/field?**
3. **Có phân biệt replica failover với data restore?**
4. **Có inventory full/incremental/log backups và retention?**
5. **Backup chain có checksum/integrity manifests?**
6. **Có thử restore/decrypt với keys thực?**
7. **Có offsite/immutable copies theo threat model?**
8. **Có xác định consistent snapshot/PITR boundary?**
9. **Không tự ghép snapshots nhiều shards ở khác thời điểm?**
10. **Có lưu topology/schema/index/TTL/ACL metadata?**
11. **Có recovery environment tách khỏi production?**
12. **Có kế hoạch full-cluster provision/storage capacity?**
13. **Có fencing old writers, tránh split-brain?**
14. **Có kế hoạch region/DNS/service routing cutover?**
15. **Có xử lý old connections/caches?**
16. **Có kiểm chứng data mới sau backup sẽ mất hay được replay?**
17. **Có operation ledger cho unknown commit outcomes?**
18. **Có chọn đúng namespace/dataset khi partial restore?**
19. **Có so cross-dataset invariants sau restore?**
20. **Có staging clone/cutover hoặc merge policy?**
21. **Có affected key set đáng tin cho selective repair?**
22. **Có per-key historical vs live diff?**
23. **Có conditional version guard?**
24. **Có idempotent operation IDs và batch checkpoints?**
25. **Có manual approval khi sửa money/security state?**
26. **Không hồi sinh hard-deleted/privacy-deleted records?**
27. **Có TTL/tombstone retention semantics?**
28. **Có bảo tồn writes hợp lệ sau incident?**
29. **Không replay payment/email side effects tùy tiện?**
30. **Có plan CDC reconnect/rebootstrap khi token invalid?**
31. **Có search/cache rebuild thay restore stale copy khi phù hợp?**
32. **Có test schema/index/driver compatibility?**
33. **Có verify membership, versions, canonical digests?**
34. **Có query/authorization/tenant invariants?**
35. **Có rate limits cho backfill/reindex và source protection?**
36. **Có đo restore phase times và actual RPO/RTO?**
37. **Có rollback/failback strategy không gây lost writes?**
38. **Có logs/audit/recoveryId và 4-eyes approval phù hợp?**
39. **Có DR drills đủ quy mô và fault injection?**
40. **Chỉ đánh dấu RECOVERED sau verified state, không chỉ exit code 0?**

**Kết luận:** Khôi phục NoSQL phải chọn đúng **phạm vi** và **mốc nhất quán**. Khi toàn bộ authority bị mất, cần cluster restore theo backup/PITR chain được xác minh, dựng topology, kiểm chứng dữ liệu và chuyển traffic có fencing. Khi chỉ một tập dữ liệu hỏng, nên restore namespace vào staging, bảo vệ những writes hợp lệ ở các tập khác, kiểm tra schema/index/TTL và cutover có kiểm soát. Khi chỉ một nhóm bản ghi sai, vấn đề lớn nhất là **không ghi đè những thay đổi hợp lệ sau snapshot**: cần affected-key manifest, đối soát historical/live state, selective field repair, conditional version guards và idempotency. Trong cả ba trường hợp, phải bảo vệ deletes/erasure, external business side effects, tenant permissions và CDC/cache/search projections. Backup chỉ thực sự có giá trị khi **khôi phục, kiểm chứng và đo được RPO/RTO trên kịch bản diễn tập**.
