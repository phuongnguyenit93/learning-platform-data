# Tổng chi phí lưu trữ, nhân bản, chỉ mục, lưu lượng và nhân lực vận hành

Khi chọn **Database No SQL**, câu hỏi “Dịch vụ nào rẻ hơn?” thường bị trả lời quá sớm bằng giá **GB lưu trữ** hoặc giá **một máy chủ mỗi tháng**. Cách so sánh đó bỏ qua những khoản thường quyết định tổng chi phí: **số bản sao**, cấu trúc **chỉ mục**, mức **đọc/ghi và độ trễ** cần bảo đảm, **network traffic**, dữ liệu sao lưu/khôi phục, nhu cầu tăng capacity vào giờ cao điểm và **nhân lực vận hành**.

Ví dụ, một hệ lưu 2 TiB dữ liệu nghiệp vụ có thể cần 6 TiB trước khi tính chỉ mục nếu lưu **ba bản sao đầy đủ**. Sau đó còn có index files, log/commitlog, compaction, snapshots và phần trống để hệ phục hồi khi một node hỏng. Ngược lại, một dịch vụ managed có giá mỗi GB cao hơn nhưng có thể giảm đáng kể giờ trực vận hành, xử lý nâng cấp và khôi phục sau sự cố. Cả hai góc nhìn đều cần trong quyết định kiến trúc.

Bài học thuộc chương **Đánh giá và lựa chọn** của chủ đề **Database No SQL**. Mục tiêu là xây dựng một phương pháp **Total Cost of Ownership (TCO)** có thể giải thích, dự báo và kiểm chứng, thay vì lấy bảng giá đơn lẻ làm kết luận. Nội dung tập trung vào chi phí:

- Dữ liệu logic và dung lượng vật lý: nén, bản sao, sharding, metadata, index, log, tombstone, compaction.
- Đọc/ghi và capacity: provisioned/on-demand throughput, hot partitions, request sizes, transactions, consistency, tail latency.
- Truyền dữ liệu: cùng vùng, khác vùng/AZ, Internet egress, CDC, backup, replication và data migration.
- Vận hành: DBA/SRE/on-call, backup/restore drills, patching, security, monitoring, incident, vendor support và kiến thức chuyên môn.
- Quyết định kinh tế: mô hình chi phí 1–3 năm, kịch bản tăng trưởng, unit economics, rủi ro, độ nhạy và điểm hòa vốn.
- Khả năng áp dụng: so sánh MongoDB, DynamoDB, Cassandra, Redis và search/graph/document projections mà không giả vờ chúng có cùng mô hình định giá.

**Lưu ý:** mọi đơn giá, dung lượng, thời gian và hệ số trong các ví dụ tự đặt ra chỉ nhằm minh họa cách tính. Chúng **không phải báo giá thực tế** của AWS, MongoDB Atlas, Apache Cassandra, Redis, Azure, Google Cloud hay nhà cung cấp nào. Bảng giá thay đổi theo region, thời điểm, tier, hợp đồng, feature và chính sách chiết khấu; trước quyết định mua cần lấy báo giá/công cụ tính chi phí **cùng thời điểm và cùng workload**.

> **Nguyên tắc:** so các phương án khi chúng cùng đáp ứng một **hợp đồng dữ liệu, SLO, khả năng phục hồi và yêu cầu bảo mật**. Một phương án không đạt yêu cầu kỹ thuật không trở thành lựa chọn tốt chỉ vì rẻ hơn.

---

## 1. TCO là gì?

**Total Cost of Ownership** là tổng chi phí sở hữu, triển khai và vận hành hệ thống trong một khoảng thời gian đã xác định, thường tính bằng tháng hoặc năm.

Mô hình khái niệm:

\[
TCO_{H} = C_{\text{build}} +
\sum_{m=1}^{H}
(C_{\text{storage},m}+C_{\text{compute},m}
+C_{\text{operations},m}+C_{\text{network},m}
+C_{\text{people},m}+C_{\text{other},m})
+C_{\text{exit}}
\]

Trong đó:

- \(H\): số tháng của kỳ đánh giá.
- \(C_{\text{build}}\): thiết kế/migration/PoC/triển khai ban đầu.
- \(C_{\text{storage}}\): dữ liệu, replicas, indexes, backup, logs.
- \(C_{\text{compute}}\): nodes/instances, CPU/RAM, requests hoặc RU/RCU/WCU.
- \(C_{\text{operations}}\): giám sát, support, security, maintenance, restore tests.
- \(C_{\text{network}}\): dữ liệu qua mạng, cross-region/AZ và Internet egress.
- \(C_{\text{people}}\): công sức kỹ thuật, trực vận hành, đào tạo, ứng phó sự cố.
- \(C_{\text{other}}\): license, taxes theo cách lập ngân sách, compliance, observability, disaster recovery.
- \(C_{\text{exit}}\): di chuyển/loại bỏ hệ và chi phí khóa chặt nhà cung cấp khi hợp lý.

Cách nhóm chi phí có thể khác nhau giữa doanh nghiệp. Điều quan trọng là **không thiếu và không đếm trùng**.

## 2. TCO khác bill hàng tháng

Một hóa đơn cloud có thể hiển thị:

~~~text
Database instances
Storage volume
Data transfer
Backup snapshots
API requests
Support plan
```

Nó không nhất thiết hiển thị:

- 0,4 FTE của kỹ sư viết scripts migration.
- Thời gian SRE trực đêm khi primary election bất ổn.
- Rủi ro một restore không đạt RTO.
- Chi phí CI load test và staging clusters.
- Data cleanup/repair khi write conflict.
- Chi phí ứng dụng vì query fan-out phải đổi kiến trúc.
- Thời gian triển khai tính năng bị trì hoãn vì hệ lưu trữ.

**Bill** là một phần của TCO; TCO là **mô hình để đưa ra quyết định**.

## 3. Chi phí thực trả, chi phí cơ hội và rủi ro

Phân ba lớp để tránh gộp lẫn:

| Lớp | Bản chất | Ví dụ |
|---|---|---|
| **Direct cash cost** | Hóa đơn/chi tiêu thực tế | Nodes, API requests, transfer, support |
| **Allocated people cost** | Công sức đội ngũ được phân bổ | DBA, SRE, on-call, upgrade, backups |
| **Risk/option cost** | Tác động hoặc kịch bản xác suất | Downtime, migration failure, vendor lock-in |

Không nên cộng một con số “sự cố giả định” như chi phí chắc chắn vào bill. Có thể trình bày **expected loss**, kịch bản xấu và độ nhạy riêng, kèm điều kiện và bất định.

## 4. Chọn horizon và đơn vị tiền tệ

Tùy quyết định:

- 3–6 tháng: PoC hoặc migration ngắn hạn.
- 12 tháng: ngân sách thường niên.
- 24–36 tháng: lựa chọn nền tảng và chi phí vận hành dài hạn.
- 5 năm: hệ thống sống lâu, nhưng giả định giá/tải sẽ bất định hơn.

Cần ghi:

~~~yaml
evaluation:
  horizonMonths: 36
  currency: USD
  priceRegion: specifiedAtQuoteTime
  reportPeriod: monthly
  taxTreatment: stated
  fxAssumption: documentedIfNeeded
  environmentScope:
    - production
    - staging
    - disasterRecovery
~~~

Các số tiền của nhiều nhà cung cấp phải quy đổi theo cùng một **đơn vị tiền, kỳ thanh toán, thuế và tỷ giá**.

## 5. So sánh cùng functional contract

Trước khi ước lượng chi phí, mô tả:

- Data model: document/key-value/wide-column/graph/search.
- Access patterns: point lookup, range, filter, join/traversal, full-text.
- Write semantics: conditional update, transaction, idempotency.
- Consistency: eventual, strong, quorum, causal, per-document atomic.
- Availability target và failure domains.
- RPO/RTO cùng yêu cầu backup/restore.
- Encryption, network isolation, auditing và retention.
- Geographic locations và data residency.
- Scale, latency p95/p99, burst và growth.
- Phạm vi đội ngũ tự chịu trách nhiệm.

Nếu phương án A không đáp ứng một invariant bắt buộc còn B đáp ứng, phép so **$/GB** giữa A và B chưa có nghĩa.

## 6. So sánh cùng SLO

Hai giải pháp:

~~~text
A: 5,000 writes/s, p99=500ms
B: 5,000 writes/s, p99=50ms
```

chưa tương đương nếu ứng dụng yêu cầu p99 dưới 100 ms. Cần xem phần capacity phải mua thêm để A đạt p99 mục tiêu, hoặc loại A nếu kiến trúc không thể đạt.

Tương tự, một cluster 1 replica có vẻ rẻ hơn 3 replicas nhưng khác hoàn toàn về fault tolerance.

## 7. Baseline workload phải được đo

Các input quan trọng:

| Nhóm | Số đo |
|---|---|
| Data | Logical bytes, item/document size distribution |
| Access | Read/write ops/s theo query type, p50/p95/p99 |
| Traffic | Requests theo giờ/ngày/region và peak/burst |
| Index | Indexed fields, index count, key cardinality |
| Retention | TTL, archive, backups, legal retention |
| Reliability | RPO, RTO, availability, quorum/replication |
| Replication | Regions, replica count, consistency/write concern |
| Operation | DBA/SRE time, incidents, support burden |
| Growth | New items/day, churn, read/write growth |
| Tenant skew | Top tenants, hot keys/partitions |
| Network | Ingress, intra-region, cross-AZ, cross-region, Internet |

Lấy số đo từ một tháng có campaign bất thường cần ghi mùa vụ thay vì coi đó là trung bình thường xuyên.

## 8. Phân biệt trung bình, peak và burst

Một workload có:

~~~text
Average writes: 1,000/s
Daily peak:     5,000/s
Short burst:   40,000/s for 30 seconds
```

Không thể chọn capacity chỉ theo average rồi mong đạt tail latency khi burst. Nhưng nếu trả tiền cho 40.000 writes/s 24/7 cũng có thể rất lãng phí.

Các yếu tố quyết định:

- Provisioned vs on-demand pricing.
- Autoscaling response time.
- Queues/backpressure.
- Acceptable latency/throttling.
- Burst capacity/credits.
- Write distribution/hot partitions.
- Load shedding.
- SLA và cost of overprovisioning.

**Average billing** và **peak engineering** phải được mô hình hóa cùng lúc.

## 9. Dữ liệu logic khác dữ liệu vật lý

**Logical bytes** là kích thước dữ liệu có ý nghĩa ứng dụng, thường đo sau serialization hoặc bằng tập fields chuẩn. **Physical bytes** là storage thật phải duy trì gồm:

- Primary data.
- Replicas/copies.
- Secondary indexes.
- Storage-engine metadata.
- WAL/commitlog.
- Tombstones.
- Compaction/obsolete versions.
- Free-space headroom.
- Backup/snapshot hoặc PITR logs.
- Change streams/CDC retention.

Không có một hệ số “NoSQL tốn x3” chung cho mọi engine.

## 10. Mô hình storage sơ bộ

Giả sử:

- \(L\): dữ liệu logic trước nén.
- \(c\): tỷ lệ sau nén, ví dụ 0,6.
- \(i\): index size trên một bản sao như tỷ lệ data đã nén.
- \(r\): số bản sao đầy đủ.
- \(u\): mức lấp đầy storage được phép, ví dụ 0,7.
- \(M\): metadata/log/compaction/working space ngoài các thành phần đã tính.

Một ước lượng:

\[
S_{\text{allocated}}\approx
\frac{L\cdot c\cdot(1+i)\cdot r}{u}+M
\]

Công thức **không áp dụng máy móc** nếu engine dùng erasure coding, indexes không đồng vị trí, compression riêng cho index, shared storage của managed service hoặc license đã bao gồm replicas. Hãy dùng mô hình của nhà cung cấp khi có.

## 11. Ví dụ 500 GB, RF=3

Giả sử:

~~~text
Logical data L       = 500 GB
Compression ratio c = 0.65
Index ratio i       = 25% of compressed data
Replica factor r    = 3
Target utilization u = 80%
Extra logs/backups  = not included yet
```

Tính:

\[
S=\frac{500\times0.65\times1.25\times3}{0.8}
=1\,523.4375\text{ GB}
\]

Ước lượng khoảng **1,52 TB allocated raw capacity** theo hệ số đã cho, **trước** log/backup và giới hạn instance/disk khác. Đây không phải thông lượng/GB bill của dịch vụ managed cụ thể.

## 12. Compression không miễn phí

Nén làm giảm storage/network nhưng có thể đổi:

- CPU cho compression/decompression.
- Read latency.
- Cache efficiency.
- Index size.
- Compaction amplification.
- Recompress khi updates.
- Encryption/compression pipeline behavior.

Data có binary media đã nén sẵn thường nén kém; JSON text lặp keys có thể nén tốt. Đo trên **representative dataset**, gồm cấu trúc, size distribution và mutation rate.

## 13. Compression phải đo ở engine thật

Một document JSON 2 KB có thể được lưu trong BSON, Parquet, SSTable hoặc binary representation khác. Ratio khác nhau theo:

- Format và dictionary.
- Field types.
- Repeated values.
- Compression codec.
- Block/page size.
- Write/update churn.
- Encryption.
- Index key distribution.
- Engine version/config.

Không lấy “text gzip ratio” để suy chắc physical size của RocksDB/Cassandra/MongoDB indexes.

## 14. JSON/document metadata overhead

Một record logic nhỏ:

~~~json
{"id":"a","v":1}
~~~

khi lưu có thể cần key metadata, headers, row overhead, page alignment, pointers, timestamps, indexes và minimum billable item size.

Với hàng tỷ items rất nhỏ, **per-item overhead** và request billing units có thể quan trọng hơn lượng payload thuần.

Nên đo phân phối kích thước và chi phí **theo item type**, không chỉ tổng GB.

## 15. Replication factor thay đổi storage và write cost

Một cụm RF=3 thường có ba bản sao dữ liệu ở những replica nodes theo topology tương ứng. Nhưng cần phân biệt:

- **Full replicas** vs erasure-coded fragments.
- Storage shared giữa compute nodes hay không.
- Replica count tính trong bill managed hay đã nằm trong đơn giá.
- Cross-AZ/cross-region replication traffic.
- Read consistency và write acknowledgments.
- Rebuild một node hỏng.
- Compaction/index overhead trên replicas.

**Không nhân storage RF thêm lần nữa** nếu giá storage managed đã nêu là *billed logical data including replication* theo contract. Đó là lỗi double counting rất phổ biến.

## 16. Replication topology là một input kinh tế

Ví dụ:

~~~text
3 replicas in one region across 3 AZs
1 additional asynchronous regional replica
1 DR cold backup in another region
```

Có thể có:

- Storage của replicas.
- Compute của replicas.
- Transfer cross-AZ/region.
- Additional write propagation.
- More monitoring/support.
- DR test/recovery operations.
- Network cost khi đọc từ remote.
- Data residency/legal implications.

**RF=3** không nói đủ chi phí nếu chưa biết ba replicas nằm ở đâu và provider tính traffic thế nào.

## 17. Sharding không tự giảm chi phí

Sharding phân phối dữ liệu và tải trên nhiều nodes. Nó có thể:

- Tăng aggregate throughput.
- Giúp scale theo tenant/key.
- Giảm hotspot của một node.
- Tăng router/metadata/coordination cost.
- Tăng operational complexity.
- Tạo cross-shard scatter-gather queries.
- Phải re-balance/migrate data khi growth.
- Cần overprovisioning cho failure recovery.

Nếu thêm shards mà tổng compute/index/storage overhead tăng, bill có thể lớn hơn mặc dù mỗi shard nhỏ hơn.

## 18. Empty capacity cũng phải trả tiền

Một cụm 6 nodes nhưng đang dùng 30% CPU và 40% disk có thể đang trả tiền cho capacity dự phòng.

Phần trống có thể cần cho:

- Traffic burst.
- Node failure/rebalance.
- Compaction.
- Maintenance/index build.
- Recovery after outage.
- Migration.
- New tenant onboarding.

Mô hình nên tách **intentional headroom** (đáp ứng SLO) với **waste** (instance size không hợp workload). Không tối ưu tới 100% utilization nếu điều đó khiến recovery không thể đạt RTO.

## 19. Disk headroom và compaction

Một engine kiểu LSM có thể cần extra disk cho compaction, SSTables cũ, tombstones và rebuild. Một engine có page/file storage khác có write amplification và fragmentation riêng.

Câu hỏi chi phí:

- Max temporary disk multiplier khi compaction?
- Tombstone retention bao lâu?
- Compaction backlog khi peak?
- Repair/reindex cần disk trống thêm không?
- Tiến trình rebuild có chạy cùng live traffic được không?
- Khi disk watermark báo critical thì còn rollback space không?

**Used bytes hôm nay** không đồng nghĩa **allocated bytes cần mua** để vận hành an toàn.

## 20. Tombstone và TTL không làm storage biến mất ngay

Một TTL hết hạn có thể:

- Bị ẩn khỏi read path trước physical deletion.
- Cần background cleanup.
- Tạo tombstone/log records.
- Được giữ để đảm bảo delete reconciliation.
- Tiếp tục nằm trong snapshots/backups.
- Tăng read/compaction overhead cho tới khi dọn.

Đừng lấy `TTL = 7 ngày` rồi suy chính xác disk data chỉ bằng 7 lần bytes/ngày; cần xét compaction, delayed delete, backups, late replicas và retention semantics.

## 21. Dữ liệu cập nhật thường xuyên làm tăng write amplification

Một document được cập nhật 50 lần/ngày có thể tạo:

- Extra WAL/commitlog writes.
- Index maintenance.
- Old versions/MVCC.
- Replication traffic.
- CDC changes.
- Compaction.
- Cache invalidation.
- Backup incremental delta.

Cùng logical dataset 100 GB, **write-heavy workload** có thể tốn nhiều I/O/CPU/network hơn dataset gần như immutable.

## 22. Secondary indexes là một phần của dữ liệu vật lý

Một index trên `status` hoặc `email` không miễn phí. Nó cần:

- Storage keys/pointers.
- Updates khi indexed fields đổi.
- Cache/memory.
- Query-planner stats.
- Replication/snapshot/backup.
- Index build/rebuild time.
- Operational monitoring.

Hãy tính index size **per index, per replica, per table/collection và thời điểm đỉnh**.

## 23. Index cardinality và distribution

Hai indexes có cùng số records có thể khác lớn vì:

- Key dài/ngắn.
- Multi-valued fields tạo nhiều entries.
- Composite keys gồm nhiều components.
- Sparse/partial index.
- Text/token indexes sinh nhiều tokens.
- Geospatial structures.
- Stored/covering attributes.
- Collation/normalization metadata.

Đo **index size thực tế** qua representative data sau khi build, không dùng một tỷ lệ 20% cố định cho mọi chỉ mục.

## 24. Index tăng chi phí writes

Khi tạo `UPDATE status`:

~~~text
Update primary document
+ remove old status index entry
+ add new status index entry
+ WAL/replication
+ cache invalidation
```

Một index có thể làm reads nhanh nhưng tăng write latency và cost. Có những index được phép loại bỏ, nhưng không bỏ unique constraint có nhiệm vụ bảo vệ invariant chỉ để tiết kiệm.

TCO cần tính **net effect**: index tốn writes/storage nhưng có thể tiết kiệm reads/compute hơn rất nhiều so với full scans.

## 25. Chi phí index vs chi phí query thay thế

Giả sử query không có index phải đọc 1 triệu documents, có index chỉ xét 200 candidates. Cần so:

- I/O từ full scan.
- Query CPU.
- Network payload.
- Cache pollution.
- Tail latency.
- Index storage + maintenance.
- Build/rebuild time.
- Cost của một denormalized read model khác.

Một index “đắt” vẫn có thể là quyết định rẻ nếu loại bỏ hàng nghìn full scans mỗi ngày.

## 26. Chỉ mục không có cùng semantics giữa NoSQL engines

| Hệ/kiểu | Điểm cần tính |
|---|---|
| MongoDB indexes | BSON key size, multikey/text/compound, cache, replication, index build |
| DynamoDB GSI | Storage + read/write capacity và projection riêng; consistency/partition rules |
| DynamoDB LSI | Item collection/index constraints và billing/LSI semantics theo service |
| Cassandra materialized views/secondary indexes | Write fan-out, consistency, repair/operational burden |
| Redis secondary lookup structures | Memory cho sorted sets/hashes/sets; app phải duy trì consistency |
| Search index | Inverted index, analyzer, shard/replica, refresh/merge và search CPU |
| Graph projection | Node/edge storage, traversals, index, sync pipeline |

Không coi “5 indexes” là cùng chi phí giữa document, key-value và search engines.

## 27. DynamoDB GSI có capacity riêng

Với DynamoDB, Global Secondary Index có thể làm tăng:

- Index storage.
- Write capacity/requests khi base table thay indexed attributes.
- Read traffic của index.
- Backfill/index creation.
- Throttling khi index partition nóng.
- CDC/replication/cross-region implications theo config.

Cần tính **WCU/RCU ở cả table và từng GSI** hoặc model on-demand tương ứng, và hiểu projection type. Không cộng “table RCU” như thể index queries miễn phí.

## 28. Redis dùng RAM làm một nguồn chi phí lớn

Một Redis workload có thể tốn bộ nhớ cho:

- Keys + values.
- Object/allocator overhead.
- Hash buckets/pointers.
- Replication backlog.
- Client buffers.
- Persistence/fork copy-on-write overhead.
- Fragmentation.
- Sorted sets/streams indexes.
- Headroom cho eviction/peak.

Nếu so Redis với disk-backed database chỉ bằng `price per GB storage`, có thể sai bản chất. Cần nhìn **$ per working-set capacity**, latency và role (cache hay source-of-truth).

## 29. Backup không giống replication

Replication giúp duy trì availability và read capacity, nhưng có thể sao chép **delete nhầm, corruption hoặc malicious write** sang mọi replicas.

Backup/PITR giúp phục hồi mốc thời gian trước, trong phạm vi retention và recoverability. TCO cần tính:

- Snapshot/full/incremental bytes.
- PITR/WAL change retention.
- Archive tiers.
- Cross-region backup copy.
- Encryption/KMS.
- Restore compute/network.
- Backup storage lifecycle policies.
- Periodic restore drills.
- Immutability/ransomware controls khi cần.

Không bỏ backup vì “đã có RF=3”.

## 30. Backup size không nhất thiết bằng live storage

Snapshot có thể dùng copy-on-write/incremental deduplication, hoặc có thể sao chép đầy đủ tùy engine/dịch vụ.

Cần biết:

- Full backup size.
- Change rate mỗi ngày.
- Retention days/months.
- Compression/dedup behavior.
- Snapshot metadata.
- Index included or rebuild needed.
- Storage class và retrieval fees.
- Replication across regions.
- Delete lifecycle.

Lấy 3 snapshots × data size làm ước lượng sơ bộ được **nếu nêu giả định full independent copies**; không phải mọi snapshot technology đều tính như vậy.

## 31. PITR thay đổi đường chi phí

Point-in-time recovery cần lưu history đủ để khôi phục tới thời điểm yêu cầu. Với write-heavy workload, PITR/log retention có thể chi phí cao dù live dataset không tăng nhiều.

TCO phải xem:

- Daily changed bytes.
- Database log/CDC retention.
- Churn do TTL.
- Copy/restore job.
- Backup frequency.
- Restore verification.
- RPO và RTO.
- Multi-region copy.

Chi phí backup được đánh giá **cùng khả năng restore đáp ứng yêu cầu**, không chỉ giá storage trên hóa đơn.

## 32. RPO và RTO có chi phí

**RPO** là mức mất dữ liệu tối đa chấp nhận theo thời gian khi phục hồi. **RTO** là khoảng thời gian tối đa mục tiêu để phục hồi dịch vụ.

Một lựa chọn:

~~~text
RPO = 24 hours, RTO = 8 hours
```

có thể rẻ hơn:

~~~text
RPO near zero, RTO = 5 minutes
```

vì mục tiêu thứ hai thường cần replication, automation, capacity reserve, failover practice và testing nghiêm ngặt hơn. Không coi các mục tiêu này đã được đáp ứng chỉ vì tick một nút “high availability”.

## 33. DR capacity có thể ở chế độ warm/cold/hot

| Mô hình | Đặc điểm | Trade-off |
|---|---|---|
| Cold standby | Có backups/infrastructure plans, ít compute chạy | Chi phí nền thấp, RTO lớn hơn |
| Warm standby | Có hạ tầng DR hoạt động một phần | Chi phí trung bình, cần scale khi failover |
| Hot standby | Hạ tầng gần sẵn sàng nhận traffic | Chi phí cao, RTO nhỏ hơn nếu thiết kế đúng |
| Active-active | Nhiều region phục vụ traffic | Chi phí/consistency/coordination phức tạp |

Mỗi mô hình cần test **data consistency và traffic failover**, không chỉ đếm servers.

## 34. Data residency có thể tăng TCO

Một số tổ chức không được tự ý chuyển PII sang region ngoài phạm vi được phép. Điều đó có thể buộc:

- Chọn provider/region khác.
- Dùng region có giá cao hơn.
- Giữ copies trong khu vực.
- Thêm encryption/key residency.
- Triển khai per-region clusters.
- Tách tenants theo jurisdiction.
- Tăng compliance/audit work.

Chi phí rẻ nhất không phải lựa chọn hợp lệ nếu vi phạm dữ liệu cư trú/quyền riêng tư.

## 35. Storage tiers và archival

Hot/warm/cold tiers giúp giảm đơn giá bytes, nhưng phải tính:

- Retrieval fees.
- Access latency.
- Minimum retention.
- Restore/rehydration time.
- Request charges.
- Index/query availability.
- Lifecycle transitions.
- Security/data governance.
- Operational complexity.

Một archive rẻ theo GB có thể quá chậm nếu business yêu cầu query tức thời. Đưa dữ liệu cũ ra object storage có thể giảm NoSQL primary size nhưng tăng chi phí pipeline và query engine.

## 36. TTL và data lifecycle là đòn bẩy FinOps

Nếu business chỉ cần session 30 ngày nhưng giữ 3 năm, nguồn storage, index, backup, replication và scans đều có thể lớn hơn cần thiết.

Tối ưu theo lifecycle:

~~~text
Hot data (0-30 days) -> primary NoSQL
Warm data (30-180 days) -> lower-cost read path
Archive (>180 days) -> governed storage with restore policy
Deleted data -> enforce privacy/retention policy
```

Đây chỉ là ví dụ; retention đúng phụ thuộc nghiệp vụ/pháp lý. **Giảm retention hợp lệ** thường làm giảm nhiều lớp cost cùng lúc.

## 37. Mua nhiều storage nhưng nghẽn compute

Một cluster có 2 TiB dữ liệu nhưng p99 tăng khi CPU bận may cần thêm compute trước khi hết disk.

Tương tự, một hệ đòi RAM working set 500 GB có thể cần nhiều nodes dù dữ liệu disk chỉ 300 GB.

TCO thực tế thường bị quyết định bởi **resource bottleneck lớn nhất**:

\[
C_{\text{minimum architecture}} =
\text{cost of resources needed to satisfy all constraints}
\]

không phải tối ưu riêng từng GB hay từng request.

## 38. Memory working set và cache

Memory cần:

- Hot records.
- Hot indexes.
- Query plans/metadata.
- Compaction buffers.
- Connection/query buffers.
- Garbage collection/heap headroom.
- Replica catch-up.
- Write batching.

Nếu working set lớn hơn RAM, disk I/O và tail latency có thể tăng mạnh. Một phương án giá rẻ ở CPU nhưng thiếu RAM không đạt p99 mục tiêu và phải scale đắt hơn.

## 39. Node count theo nhiều giới hạn

Một capacity model sơ bộ có thể tính:

~~~text
nodesForStorage = ceil(allocatedStorage / safeStoragePerNode)
nodesForCPU     = ceil(requiredCpu / safeCpuPerNode)
nodesForRAM     = ceil(workingSet / safeRamPerNode)
nodesForIOPS    = ceil(requiredIOPS / safeIOPSPerNode)

requiredNodes = max(
  nodesForStorage,
  nodesForCPU,
  nodesForRAM,
  nodesForIOPS,
  minimumFailureDomainNodes
)
```

Đây là **capacity sketch**, không phải packing algorithm đầy đủ: per-shard constraints, workload skew, availability quorums và per-instance limits còn có thể buộc node count lớn hơn. Sau tính, cần benchmark.

## 40. Overprovisioning do hot partitions

Nếu 10% keys tạo 80% reads, một partition có thể thành hotspot trong khi cluster CPU trung bình thấp.

Chi phí có thể tăng vì:

- Scale cả cluster chỉ để phục vụ shard nóng.
- Dùng cache/replica đọc chuyên biệt.
- Repartition/hashing keys.
- Overhead các secondary indexes.
- Cross-partition fan-out nếu shard key đổi.
- Thêm application complexity.

TCO cần biết **skew theo tenant/key/partition**, không chỉ tổng RPS.

## 41. Request cost phụ thuộc bytes và consistency

Nhiều managed NoSQL products tính request capacity theo item size, read/write type, consistency hoặc transaction, chứ không chỉ tổng số calls.

Ví dụ những yếu tố:

- Item 1 KiB khác item 10 KiB.
- Strong read khác eventual read theo provider.
- Transactional write có thể tốn hơn ordinary write.
- Query/Scan đọc nhiều items dù chỉ trả một phần sau filter.
- GSI updates có billing riêng.
- Conditional failed write có pricing semantics theo API.
- Cross-region replicas làm tăng writes/network.

Phải lấy **pricing units đúng theo provider/API**, không áp hệ số của DynamoDB sang Cassandra hay MongoDB.

## 42. DynamoDB RCU/WCU: mô hình khái niệm

DynamoDB sử dụng khái niệm **read/write capacity units** trong một số modes. Số units bị chi phối bởi item size, consistency và transaction. Một read strongly consistent của item 4 KiB không có cùng cost units với một eventual read hoặc transactional read theo mô hình dịch vụ.

Khi lập dự toán, cần biết:

- Provisioned vs on-demand.
- RCU/WCU hoặc billed request units.
- Strong/eventual/transactional reads.
- Write item size rounding.
- GSI read/write consumption.
- Read/filter/Scan evaluated bytes.
- Hot partition limits.
- Global Tables replication.
- Streams/backup/PITR separate fees.

Các constants và prices cụ thể cần lấy từ **tài liệu chính thức theo region/tier/thời điểm**, không suy ngược từ tên `ReadCapacityUnits`.

## 43. Cosmos DB RU/s và throughput model

Một managed NoSQL có thể thu phí theo **request units** hoặc provisioned throughput. RU của một thao tác phụ thuộc:

- Document size.
- Indexing policy.
- Query complexity.
- Cross-partition fan-out.
- Consistency.
- Transaction/batch mode.
- Partition distribution.

Không suy “1 request = 1 RU” cho mọi query; cần đo **actual RU charge/query shape** và thêm peak/safety headroom.

## 44. MongoDB managed cluster thường có fixed + variable costs

Một MongoDB managed deployment có thể có các khoản:

- Dedicated cluster/node tier.
- Storage/IOPS/backup.
- Cross-region replica/transfer.
- Search/vector-specific services khi sử dụng.
- Data transfer/ingress-egress tùy contract.
- Monitoring/support options.
- Index/storage size.
- Scaling/upgrading time.

Một cluster nhàn rỗi vẫn có **fixed run-rate**; API requests tăng trong khoảng còn headroom có thể không tăng bill ngay, nhưng khi vượt ngưỡng sẽ phải nâng tier. Đó là hàm chi phí dạng **step function**, khác per-request billing thuần.

## 45. Cassandra self-managed: giá compute chưa phải TCO

Cassandra tự quản lý có thể không có license phí phần mềm cốt lõi, nhưng vẫn cần:

- Multi-node compute/RAM/storage.
- Network/replication.
- Repair/compaction planning.
- Cluster upgrades và patching.
- Schema/partition-key design.
- On-call/incident.
- Backup/restore drill.
- Capacity planning, ring changes.
- Monitoring/security.
- Thời gian đào tạo chuyên môn.

Một **software license=0** không có nghĩa **operation cost=0**. Lợi ích có thể là quyền kiểm soát và khả năng tùy biến, nhưng phải định lượng nhân lực và rủi ro.

## 46. Redis: memory utilization và role quyết định bill

Redis dùng làm cache có thể chấp nhận eviction/rebuild; Redis làm primary state store cần bảo đảm persistence/replication, RPO/RTO và data safety nghiêm ngặt hơn.

Chi phí phụ thuộc:

- RAM capacity và fragmentation.
- Replica count.
- Persistence/fork overhead.
- Network traffic/clients.
- Persistence disk/backup.
- Operations per second.
- Multi-AZ failover.
- DR topology.
- Application cache hit ratio.
- Invalidation complexity.

Không so cache có thể mất với primary ledger cần durable writes như thể cùng một dịch vụ.

## 47. Lưu lượng mạng không chỉ là client response

Một hệ NoSQL có nhiều dạng network traffic:

~~~text
Application -> database read/write requests
Database primary -> replicas
Replica -> replica during rebuild/repair
Change stream/CDC -> consumers
Database -> external search/cache/warehouse
Database -> backup/object storage
Cross-region replication and DR
Query results -> API -> Internet clients
Backfill/export -> migration target
Monitoring/telemetry -> observability backend
```

Mỗi đường có **pricing boundary** khác nhau. Data transfer bên trong một zone/cùng VPC, giữa AZs, giữa regions và ra Internet thường có chính sách khác. Phải xác nhận **ai bị tính phí, chiều truyền, nơi phát và nơi nhận** theo provider.

## 48. Ingress, egress và transfer charge

- **Ingress:** dữ liệu đi vào service/cloud/region.
- **Egress:** dữ liệu đi ra khỏi service/cloud/region.
- **Intra-region transfer:** dữ liệu giữa các nơi trong cùng region.
- **Cross-AZ:** đi giữa availability zones.
- **Inter-region:** đi giữa regions.
- **Internet egress:** dữ liệu ra Internet.
- **Private network endpoint:** có thể có phí attachment/hour/bytes theo provider.

Không phải mọi ingress miễn phí hoặc mọi internal traffic miễn phí; mô hình giá tùy service/network product. Hãy sử dụng **actual network path** thay vì dán một giá “egress per GB” lên mọi bytes.

## 49. Đếm bytes trên từng link, không trên một sơ đồ trừu tượng

Ví dụ topology:

~~~mermaid
flowchart LR
  API["API in AZ-A"] -->|requests/responses| DB1["Primary in AZ-A"]
  DB1 -->|replication| DB2["Replica in AZ-B"]
  DB1 -->|replication| DB3["Replica in AZ-C"]
  DB1 -->|CDC| SEARCH["Search in AZ-B"]
  DB1 -->|backup traffic| OBJ["Object storage"]
  DB1 -->|DR link| REM["Remote region"]
~~~

Mỗi arrow là một luồng cần đo. Nhưng **không phải mọi arrow đều bị tính phí riêng**: một managed product có thể đã bao gồm một phần replication/backup traffic trong đơn giá. TCO cần mapping từ topology sang **billable meters** thật, tránh double counting.

## 50. Replication data transfer có thể lặp nhiều lần

Nếu ứng dụng ghi 100 GB payload/tháng:

- Primary write nhận dữ liệu.
- Replica 1 có thể nhận log/data replication.
- Replica 2 cũng nhận replication.
- Cross-region replica có thể nhận stream khác.
- CDC có thể phát cho nhiều consumers.

**100 GB logical writes** không có nghĩa network usage là 100 GB. Trên đường truyền, encoding, log metadata, repeated mutations, compression và protocol overhead làm bytes khác logical data volume.

## 51. Ví dụ tính cross-region transfer

Giả sử một pipeline tự quản lý sao chép **250 GB mỗi ngày** sang region khác, có transfer charge giả định **0,02 USD/GB**.

Mỗi tháng 30 ngày:

\[
B=250\times30=7\,500\text{ GB}
\]

\[
C_{\text{transfer}}=7\,500\times0.02=150\text{ USD}
\]

**150 USD/tháng** là phép tính minh họa chỉ cho **một hạng mục truyền dữ liệu**. Chưa tính storage, compute, destination writes, return traffic, KMS hay provider-specific network tiers. Không dùng 0,02 USD/GB như giá cố định.

## 52. Query fan-out tạo network và CPU amplification

Một truy vấn không target được shard/partition có thể broadcast tới nhiều nodes:

~~~text
1 client query
  -> 32 shard requests
  -> 32 partial result sets
  -> merger/sort
  -> 1 final response
```

Một API request vẫn là **32 internal requests** cùng CPU/IO/network. TCO cần quan sát **fan-out factor, bytes scanned và CPU per query**, không chỉ số request từ ứng dụng.

Sharding key và index design có thể giảm chi phí mà không giảm số API calls.

## 53. Payload size và projection

Một request chỉ cần:

~~~json
{"id":"u1","displayName":"A"}
~~~

nhưng DB trả document 100 KiB, thì:

- Network bytes lớn hơn.
- Serialization/deserialization tốn CPU.
- Heap allocation/GC tăng.
- Connection occupancy dài.
- Cache bị ô nhiễm.
- API p99 có thể tăng.

**Projection chỉ fields cần** và query design tốt thường giảm TCO lẫn latency. Nhưng cần đánh giá overhead duy trì index covering hoặc denormalized model.

## 54. CDN/cache có thể giảm đọc nhưng không miễn phí

Một cache trước database có thể làm giảm source reads:

\[
R_{\text{db}}=R_{\text{user}}\times(1-h)
\]

với \(h\) là hit ratio, nếu mỗi request cache hit tránh một DB read theo mô hình đơn giản.

Nếu 90% hits, 10.000 reads/s thành 1.000 source reads/s. Tuy nhiên cần tính:

- Cache memory/instances/requests.
- Cache invalidation/CDC fan-out.
- Warmup và cache stampede.
- Staleness policy.
- Extra network hops.
- Operational maintenance.
- Cache misses bùng nổ khi restart.

TCO của **DB + cache** phải thấp hơn/đáp ứng SLO tốt hơn DB trực tiếp, không chỉ nhìn vào giảm read volume.

## 55. Cross-region active-active có thể tăng write cost

Trong active-active, nhiều regions nhận mutations. Chi phí có thể tăng vì:

- Replicated data/storage ở mỗi region.
- Inter-region transfer.
- Multiple write/transaction attempts.
- Conflict detection/merge.
- Version/log metadata.
- Coordination or consensus RTT.
- Repair/reconciliation tasks.
- Additional failover tests.
- Higher on-call complexity.

Nếu business thật sự cần low-latency writes ở nhiều vùng và tolerate/resolve conflicts, chi phí có thể hợp lý. Nếu không, single-writer region + local reads có thể rẻ và dễ đảm bảo invariant hơn.

## 56. CDC và event pipelines là chi phí liên quan

Một MongoDB Change Stream, DynamoDB Streams consumer hoặc Cassandra CDC connector có thể kéo theo:

- Broker/queue storage and throughput.
- Connector compute.
- Stream read capacity.
- Retry/DLQ/quarantine.
- Schema registry/serialization.
- Versioned event contract.
- Retention.
- Network egress.
- Destination indexes/storage.
- Consumer on-call.
- Replay/backfill operations.

**Chi phí database** khi ứng dụng cần search/read models nên bao gồm **cả pipeline để giữ các models nhất quán**, không chỉ source table.

## 57. Một nguồn nhưng nhiều read models

Kiến trúc:

~~~text
Orders source
  -> Search index
  -> Customer dashboard projection
  -> Analytics stream
  -> Fraud scoring lookup
```

Dữ liệu có thể được **nhân bản ở cấp ứng dụng** ngoài RF nội bộ của database. Các read models dùng dạng dữ liệu riêng, có chỉ mục và retention riêng.

Khi đánh giá DynamoDB vs MongoDB, cần tính **tổng kiến trúc đáp ứng access patterns**. Một engine source rẻ nhưng cần ba hệ bổ sung có thể đắt hơn engine đa mục đích đáp ứng trực tiếp một số queries, hoặc ngược lại.

## 58. Cost of data exports và vendor exit

Khi đổi provider/engine:

- Full scan/export bytes.
- Cross-cloud egress.
- Data transformation.
- Intermediate object storage.
- Reindex/backfill.
- CDC catch-up.
- Test/migration clusters.
- Dual-running costs.
- Verification.
- Downtime/rollback readiness.
- Engineering time.

Một đơn giá rất rẻ với **exit cost cao** có thể ảnh hưởng quyết định 3–5 năm. Nhưng không định giá vendor lock-in bằng con số giả tuyệt đối; dùng kịch bản **“nếu phải rời nền tảng trong 12 tháng”**.

## 59. Cost của dữ liệu chuyển để backup/restore

Một restore 4 TiB vào region khác có thể cần:

- Đọc dữ liệu từ backup tier.
- Egress/inter-region transfer.
- Restore target compute/storage.
- Recreate secondary indexes.
- Replay WAL/CDC.
- Verification scans.
- Temporary doubled storage.
- Recovery labor.

**Backup rẻ nhưng không khôi phục được trong RTO** là lựa chọn sai. TCO phải ghi chi phí thực hiện restore drills và capacity cần giữ cho recovery.

## 60. Lưu lượng đo theo tháng và peak bandwidth

Hai workload đều truyền 10 TB/tháng:

- A truyền đều mỗi ngày.
- B truyền 10 TB trong 2 giờ.

Hóa đơn total GB có thể tương tự ở một loại pricing, nhưng B có thể cần network capacity, parallelism, throttling budget hoặc đắt hơn trong các network products thu phí theo provisioned bandwidth.

Cần mô hình cả:

\[
B_{\text{monthly}}=\sum \text{bytes transferred}
\]

và:

\[
P_{\text{network}}=\max \text{bytes/s during required peak window}
\]

Đừng chọn link chỉ theo average MB/s.

## 61. Inter-AZ topology ảnh hưởng p99 và bill

Ứng dụng chạy AZ-A nhưng database writer ở AZ-B có thể tăng:

- Round-trip latency.
- Cross-AZ bytes.
- Connection time.
- Failure-domain dependency.
- Retry/failover behavior.

Đặt API cùng AZ primary có thể giảm một số traffic, nhưng mô hình HA/failover thay đổi theo thời điểm. Managed service có thể tự route requests hoặc tính phí khác.

Kiến trúc phải tối ưu **độ bền/availability trước**, sau đó định lượng network costs theo normal và failover routes.

## 62. Network compression có chi phí CPU

Nén CDC stream 5:1 giúp giảm egress bytes nhưng dùng CPU và có thể thêm latency.

TCO so:

~~~text
Transfer savings
- Compression/decompression compute
- Added latency or buffer requirements
- Monitoring/operational complexity
```

Payload đã nén/mã hóa thường không nén thêm tốt. Thử nhiều data shapes trước khi bật compression toàn bộ.

---

## 63. Nhân lực vận hành là phần thường bị bỏ sót

Một DBA/SRE dành thời gian cho NoSQL:

- Capacity planning.
- Design review for partition keys/indexes.
- Deploy upgrades/patches.
- Backup/restore.
- On-call.
- Incident investigation.
- Query tuning.
- Security/access audits.
- Cost monitoring.
- Failure/DR exercises.
- Data migrations/backfills.
- Documentation/training.

Những giờ này là **chi phí có thật** dù không có hóa đơn tách riêng từ provider.

## 64. FTE allocation là gì?

**FTE (full-time equivalent)** biểu diễn phần thời gian một nhân sự tương đương toàn thời gian.

Ví dụ:

~~~text
1 SRE spends 40% capacity on database = 0.4 FTE
1 DBA spends 30% = 0.3 FTE
1 Backend spends 10% tuning queries = 0.1 FTE
Total allocated = 0.8 FTE
```

Nếu loaded cost giả định 8.000 USD/FTE/tháng, con số sơ bộ:

\[
C_{\text{people}}=0.8\times8\,000=6\,400\text{ USD/tháng}
\]

Đây là **chi phí nhân lực được phân bổ**, không phải chi mới bằng tiền nếu đội ngũ đã tồn tại; khi báo cáo cần nêu rõ cơ sở kinh tế của việc phân bổ.

## 65. Fully loaded labor cost

Một phép tính nhân lực có thể gồm:

- Lương/thu nhập.
- Benefits và đóng góp của doanh nghiệp.
- Thiết bị/phần mềm/đào tạo.
- Quản lý/on-call allowances.
- Recruiting/turnover.
- Chi phí công ty phân bổ theo policy.

Không nhất thiết đưa toàn bộ overhead hành chính vào cùng một hệ nếu CFO đã phân bổ chúng chỗ khác; cần tránh **double counting**.

## 66. Managed không có nghĩa “không cần DBA”

Managed DB thường giảm gánh nặng cơ sở hạ tầng, nhưng khách hàng vẫn cần:

- Thiết kế data model/index/partition key.
- Query performance.
- Application retries và idempotency.
- Security permissions/data governance.
- Capacity/budget monitoring.
- Schema migrations.
- Incident assessment.
- Backup restore requirements verification.
- Data correctness/reconciliation.
- Vendor support escalation.

Số FTE có thể **giảm hoặc chuyển kỹ năng**, không tự bằng 0.

## 67. Self-managed yêu cầu ownership rõ

Nếu tự vận hành Cassandra/Redis/MongoDB, cần owner cho:

- OS/container/Kubernetes updates.
- Storage volumes/disk replacement.
- Cluster membership/replica repair.
- Backup jobs/restore scripts.
- Security patches.
- Monitoring/alerting.
- Incident response.
- Autoscaling/sharding.
- DR.
- Capacity forecasting.

Nếu doanh nghiệp không có đủ kỹ năng và on-call coverage, một phương án tự quản lý có giá compute thấp nhưng **không đáp ứng operational risk**.

## 68. FTE theo skill không thể thay thế trực tiếp

Một đội có 0,5 FTE SRE generalist không nhất thiết giải được Cassandra repair và data consistency incident như 0,5 FTE specialist.

Mô hình người cần xét:

- Skill set.
- Bus factor/backup operators.
- Business hours vs 24×7 support.
- Onboarding/learning curve.
- Tooling maturity.
- Vendor contract responsiveness.
- Release cadence.
- Regulatory/compliance expertise.

Không lấy một hourly rate duy nhất rồi bỏ qua khả năng giải quyết sự cố thực tế.

## 69. On-call cost và fatigue

Một hệ cần phản ứng 24×7 có thể đòi:

- Rotation ít nhất vài người.
- Pager and monitoring.
- Incident runbooks.
- Training.
- Postmortems.
- Maintenance windows.
- Backup/DR drills.
- Escalation support.

Dù số giờ khắc phục sự cố ít, việc **duy trì khả năng trực và kiến thức** có chi phí. SRE fatigue và turnover risk không dễ định giá chắc chắn nhưng cần nêu như operational constraint.

## 70. Sự cố làm tốn hơn giờ SRE

Một database incident có thể ảnh hưởng:

- Doanh thu/giao dịch.
- Customer support.
- Refunds/chargebacks.
- SLA credits.
- Regulatory reporting.
- Recovery/backfill costs.
- Engineering interruptions.
- Data correction.
- Brand/trust.

Không tự quy mỗi phút downtime ra một số USD chắc chắn nếu chưa có business data. Có thể dùng **bounded impact scenarios** với số giao dịch và contribution margin đã được đồng ý.

## 71. Đánh giá expected loss có điều kiện

Một cách khái niệm:

\[
E[L]=\sum_{i=1}^{n}p_i\times impact_i
\]

Với mỗi failure mode \(i\):

- \(p_i\): xác suất trong horizon dự báo.
- \(impact_i\): hậu quả kinh tế trong mô hình.
- Giả định có thể rất bất định.
- Các failures không độc lập thì không thể cộng tùy ý.
- Các events cực đoan có tail risk lớn hơn expected value.

Phục vụ **sensitivity/risk discussion**, không nên che một rủi ro không thể chấp nhận bằng average expected loss thấp.

## 72. Operability và developer productivity

Một NoSQL engine có API đơn giản cho access pattern sẽ giảm:

- Thời gian thiết kế queries.
- Migrations.
- Debugging.
- Data validation.
- Review concurrency logic.
- Test infrastructure.
- Incident recovery.
- Hiring/training.

Một engine giá mỗi request thấp hơn nhưng buộc viết nhiều denormalization/CDC consumers có thể tạo **application maintenance cost** cao hơn nhiều.

## 73. Support/license là những khoản riêng

Một số phương án có:

- Enterprise license.
- Managed database platform fee.
- Support tier.
- Advanced monitoring.
- Backup/restore support.
- Compliance features.
- Additional connectors.
- Search/vector specialized costs.
- Commercial SLA contract.

Cần xem license tính theo node, CPU/core, instance size, storage, usage hay contract; không gộp “open source = miễn phí toàn bộ” hoặc “managed tier đã bao gồm mọi support”.

## 74. Training và tuyển dụng ảnh hưởng thời gian triển khai

Nếu đội ngũ đã thông thạo MongoDB nhưng chưa từng vận hành Cassandra, lựa chọn Cassandra có thể cần:

- Study/labs.
- Senior specialist.
- Runbook design.
- Cluster tuning.
- On-call training.
- Proof-of-concept.
- Design migration.
- SLO validation.

Một số dự án vẫn đáng đầu tư vào năng lực mới, nhưng **time-to-production** và hidden training costs phải được đưa vào quyết định.

## 75. Chi phí PoC và performance benchmarking

Một PoC đúng nghĩa cần:

- Representative data/keys/indexes.
- Representative read/write mixes.
- Real concurrency.
- Peak load and long soak.
- Failure injection.
- Security setup.
- Backup/restore.
- Monitoring.
- Infrastructure teardown.
- Engineers' hours.

PoC không nên chỉ insert 1.000 records và đo throughput trên laptop rồi kết luận quy mô production.

## 76. Chi phí migration là một “one-time cost” có rủi ro

Một migration có thể cần:

~~~text
Data export -> transform -> import
          -> change stream catch-up
          -> verify -> shadow reads
          -> cutover -> rollback window
```

Chi phí gồm:

- Double-running source + target.
- Workers/brokers/temp storage.
- Cross-cloud transfer.
- Index rebuild.
- Verification queries.
- Engineers/QA/SRE.
- Incident response.
- Rollback/replay.
- Cleanup.

Nếu đánh giá TCO 36 tháng nhưng chỉ so recurring run-rate, bỏ chi phí migration có thể đảo ngược kết luận.

## 77. Không dàn đều one-time cost mà không chú thích

Một hệ A cần migration 150.000 USD, recurring tiết kiệm 4.000 USD/tháng so với B.

Thời gian hoàn vốn đơn giản:

\[
T_{\text{payback}}=
\frac{150\,000}{4\,000}=37.5\text{ tháng}
\]

Nếu horizon chỉ 24 tháng, migration có thể **không hoàn vốn** theo những giả định này. Payback không tính discount rate, risk hoặc tăng trưởng; có thể dùng NPV/sensitivity bổ sung.

## 78. NPV cho horizon nhiều năm

Nếu muốn tính present value, với monthly discount rate \(d\):

\[
PV(C_m)=\frac{C_m}{(1+d)^m}
\]

\[
NPV_{\text{cost}}=C_0+\sum_{m=1}^{H}\frac{C_m}{(1+d)^m}
\]

Đây là **present value của chi phí**: phương án thấp hơn có lợi hơn nếu functional/quality contracts tương đương. Discount rate lấy theo chính sách tài chính; không tự dùng một giá trị do kỹ thuật viên đoán.

## 79. Kịch bản baseline, growth và stress

Một dự báo tốt ít nhất gồm:

| Kịch bản | Inputs | Mục đích |
|---|---|---|
| Base | Dữ liệu và traffic tăng theo forecast được đồng ý | Budget bình thường |
| High growth | Gấp 2–4 lần records/requests | Chi phí scale |
| Write-heavy | Tần suất update và CDC cao | Log/index/compaction cost |
| Read-heavy | Queries/cache hit khác | Read capacity/index decision |
| Disaster | Failover, restore, extra replicas | Recovery/DR budget |
| Migration | Double-run source+target | One-time transition cost |

Không vẽ một đường chi phí thẳng nếu node tier/partition count tăng theo bậc.

## 80. Fixed và variable cost

Một cluster tự quản lý có **fixed infrastructure floor**: vài nodes phải chạy dù traffic thấp. Một dịch vụ thu request có **usage-proportional component**, có thể có minimum fee/feature charges.

Mô hình:

\[
C(Q)=F+vQ
\]

trong một phạm vi tuyến tính, với:

- \(F\): minimum fixed monthly.
- \(v\): variable price/unit.
- \(Q\): usage.

Các tier upgrades, quota, discounts tạo **stepwise/nonlinear pricing**; công thức là khung so sánh, không phải mô tả đầy đủ mọi giá.

## 81. Điểm hòa vốn giữa hai cấu trúc giá

Giả sử:

\[
C_A=1\,000+0.0002Q,\quad
C_B=3\,000+0.0001Q
\]

với \(Q\) là số **request units/tháng** theo giả định và cả hai đáp ứng cùng SLO. Giải:

\[
1\,000+0.0002Q=3\,000+0.0001Q
\]

\[
Q=20\,000\,000
\]

Dưới 20 triệu units, A có chi phí thấp hơn theo mô hình; trên đó B thấp hơn. **Đơn giá hoàn toàn minh họa**, và nếu throughput provisioned có giới hạn peak thì lựa chọn phải xét thêm capacity constraints.

## 82. Volume discount và commitment

Một số nhà cung cấp có:

- Reserved/provisioned capacity.
- Committed spend.
- Enterprise contracts.
- Tiered pricing.
- Credits.
- Storage discounts.
- Support bundles.

Cần so **real effective cost** sau chiết khấu, nhưng cẩn thận:

- Commitment có lock-in và underutilization.
- Credits hết hạn.
- Overages có đơn giá khác.
- Termination fees.
- Capacity scaling/failover.
- Usage categories không được giảm giá.

Không dùng giá “discounted best case” cho tất cả kịch bản mà quên điều kiện hợp đồng.

## 83. Reserved capacity vs on-demand

Nếu tải ổn định, reserved/provisioned có thể hợp lý; nếu tải biến động lớn, on-demand có thể tránh trả cho capacity nhàn rỗi.

Một quyết định cần:

- Utilization theo giờ.
- Peak/traffic spikes.
- Autoscaling speed.
- Minimum/maximum throughput.
- Hot partitions.
- Discount commitment.
- Forecast uncertainty.
- Burst and throttle SLO.

Một phương án có mức monthly average thấp vẫn có thể **không đáp ứng peak latency** mà ứng dụng yêu cầu.

## 84. Chi phí môi trường ngoài production

Một database platform thường cần:

~~~text
Production
Staging
Pre-production/performance
Disaster recovery
Developer sandboxes
CI integration tests
Data migration temporary cluster
```

Các môi trường có thể được giảm capacity hoặc dùng ephemeral mode tùy security/testing contract. Nhưng không thể xóa staging multi-node nếu cần kiểm elections/failover.

TCO cần mô hình **full environment inventory**, không chỉ một cluster production.

## 85. Chi phí quan sát và logs

Một hệ có thể xuất:

- Query logs.
- Slow query traces.
- CDC lag/offset.
- Node metrics.
- Audit logs.
- Access logs.
- Backup status.
- Partition heatmaps.
- Error traces.

Chi phí có thể tính theo **bytes ingested, retained, queried, traces/s và alert platform**. Nếu bật verbose logging cho mọi request trong thời gian dài, observability bill có thể lớn. Không giảm logging xuống mức không thể điều tra critical consistency incidents chỉ để tối ưu tiền.

## 86. KMS/encryption cost

Khi dữ liệu được mã hóa, chi phí có thể gồm:

- Managed KMS key fees.
- Cryptographic API calls.
- Envelope encryption metadata.
- Key rotation.
- Secrets management.
- Audit.
- HSM/dedicated key infrastructure.
- Re-encryption/migration workloads.
- Cross-region key requirements.

Không tính KMS chỉ theo dữ liệu GB: một thiết kế gọi KMS cho **mỗi record** có thể tốn nhiều API calls hơn thiết kế envelope encryption có cache và key lifecycle an toàn.

## 87. Data governance và compliance operations

Một hệ xử lý PII hoặc records chịu quy định có thể yêu cầu:

- Retention/deletion policies.
- Audit and evidence.
- Encryption.
- Access reviews.
- Backup policies.
- Data residency.
- Disaster tests.
- Incident reports.
- Data subject deletion handling.
- Policy exceptions/reviews.

Chi phí thực thi compliance thuộc TCO khi các phương án có mức tự động hóa/trách nhiệm khác nhau. Không chỉ dùng “provider certified” để giả định ứng dụng đã compliant.

## 88. Chi phí quyền truy cập và security design

Một database tự quản lý có thể cần:

- Network segmentation.
- Private endpoints.
- IAM/RBAC.
- Secret rotation.
- TLS certificates.
- Security patching.
- Vulnerability scanning.
- Bastion/admin access.
- Audit trail.
- Pen-test/review.

Managed service có thể cung cấp một phần, nhưng **application-level tenant isolation và least privilege** vẫn thuộc trách nhiệm hệ thống.

## 89. Nâng cấp phiên bản có chi phí

Một nâng cấp NoSQL có thể kéo theo:

- Compatibility test drivers/queries.
- Schema validation.
- Rolling upgrades.
- Cluster restarts/elections.
- Index rebuild.
- Query plan changes.
- Backups/rollback.
- Incident monitoring.
- Engineering time.

Nếu tự quản lý và để version cũ quá lâu, security/support risk tăng. TCO nhiều năm phải dự phòng **upgrades không thể tránh khỏi**.

## 90. Chi phí xây dựng tự động hóa

Một cluster tự quản lý lúc đầu có thể “rẻ” vì scripts thủ công, nhưng để đạt SLA nghiêm ngặt cần:

- Infrastructure as Code.
- Backup scheduler.
- Restore automation.
- Alert rules.
- Auto-remediation guardrails.
- Scaling control.
- Chaos/fault tests.
- Runbooks.
- Cost allocation tags.
- Rotation/deletion lifecycle jobs.

Đây là **one-time engineering investment + maintenance**, không phải chi phí infrastructure hàng tháng thuần.

---

## 91. Xây mô hình TCO từ các meters

Thay vì hỏi “dịch vụ giá bao nhiêu?”, hãy bắt đầu bằng một **measurement inventory**:

~~~text
Raw measurements
  |
  +-- dataset bytes, index bytes, replica count
  +-- operations/s by class and item size
  +-- partition heatmaps and peak distributions
  +-- WAN/AZ/region transfer
  +-- backup delta/retention
  +-- staffed engineer hours
  |
  v
Technical sizing
  |
  +-- safe storage and compute capacity
  +-- write/read throughput and latency targets
  +-- failover and DR headroom
  |
  v
Pricing meters
  |
  +-- instances/GB/IOPS/request-units/egress
  +-- support/license/backup/monitoring
  +-- migration and on-call allocations
  |
  v
Monthly scenario totals and 36-month TCO
~~~

Nếu một meter không đo được, ghi **assumption với uncertainty range**, không lén cho bằng 0.

## 92. Một data dictionary cho mô hình

| Tên biến | Đơn vị | Định nghĩa rõ |
|---|---|---|
| `logicalDataGiB` | GiB | Dữ liệu ứng dụng trước replication |
| `compressedRatio` | ratio | Physical data/logical data theo engine |
| `indexGiBPerReplica` | GiB | Index physical trên một replica |
| `replicaCount` | count | Full replica equivalents |
| `storageHeadroom` | ratio | Phần capacity dự phòng |
| `monthlyReadOps` | count | Successful/logical reads theo class |
| `monthlyWriteOps` | count | Logical writes, trước retries |
| `averageReadKB` | KiB | Size/consumption distribution |
| `peakReadOpsPerSec` | ops/s | P99 hoặc planned peak window |
| `crossRegionGiB` | GiB | Billable remote transfer |
| `backupGiBMonth` | GiB-month | Billable storage trong tháng |
| `opsFte` | FTE | Fraction of loaded labor |
| `migrationOneTime` | currency | Initial and transitional cost |
| `riskReserve` | currency | Contingency, trình bày riêng |

Không dùng “GB” và “GiB” hoán đổi không có conversion; storage invoice có thể tính decimal GB còn OS tooling hiển thị binary GiB.

## 93. GB và GiB khác nhau

\[
1\text{ GB}=10^9\text{ bytes}
\]

\[
1\text{ GiB}=2^{30}\text{ bytes}
\]

Nên:

\[
1\text{ GiB}\approx1.073741824\text{ GB}
\]

Ví dụ 500 GiB ≈ 536,9 GB. Với hàng trăm TiB, unit mismatch có thể gây chênh lệch báo giá đáng kể.

Mô hình phải chuẩn hóa units ở một sheet/config/ledger.

## 94. Requests/second sang operations/tháng

Với average rate \(r\) ops/s và tháng 30 ngày:

\[
N_{\text{month}}=r\times30\times24\times60\times60
=r\times2\,592\,000
\]

Nếu đọc 3.000/s và ghi 500/s:

- Reads: \(3\,000\times2\,592\,000=7\,776\,000\,000\).
- Writes: \(500\times2\,592\,000=1\,296\,000\,000\).

Nhưng nếu `r` là peak 10 phút/ngày, không được nhân như thể giữ liên tục 30 ngày. Dùng **hourly histogram/time series** để mô phỏng bill chính xác hơn.

## 95. Reads và writes có cost units khác nhau

Một read query có thể đọc 100 documents nhưng trả 5 sau filter; một batch write có thể cập nhật nhiều indexes.

Cần phân lớp:

~~~text
pointGet small
pointGet large
rangeQuery pages
filter/scan
strongRead
eventualRead
transactionalRead
insertSmall
updateIndexedFields
conditionalUpdate
transactionalWrite
delete
bulk/backfill
```

Với từng class, đo:

- Ops count.
- Mean/p95 billed units.
- Bytes scanned/returned.
- p95/p99 latency.
- Failure/retry attempts.
- Index/update amplification.
- Consistency policy.

Một giá “per one million requests” không đủ nếu workload mix khác nhau.

## 96. Billed operation vs logical business operation

Một logical Order update có thể gồm:

~~~text
Read order
Validate version
Conditional update order
Write outbox event
Update two indexes
CDC consumer writes projection
```

Nếu giá database tính theo API/backend operations, một **business operation** phát nhiều **billed operations**.

Unit economics nên đo:

\[
\text{cost per business action}
=\frac{\text{attributed platform cost}}{\text{successful business actions}}
\]

Không chỉ `database bill / total SDK calls`, vì SDK retries và read amplification làm denominator đánh lạc hướng.

## 97. Failed attempts có thể tiêu tốn capacity

Một request failed do:

- Conditional conflict.
- Throttling.
- Network timeout.
- Server error.
- Query validation.

có thể tiêu thụ khác nhau theo provider/API. Một số failed conditional checks vẫn phát sinh read/other capacity; một số network errors có thể đã commit.

Mô hình phải đo **attempts by outcome và consumed units**, không giả định mọi failure miễn phí.

## 98. SDK retries làm tăng request volume

Nếu \(A\) là số attempts trung bình trên một logical operation:

\[
N_{\text{attempts}}\approx N_{\text{logical}}\times A
\]

Ví dụ 1 triệu writes, trung bình 1,1 attempts = 1,1 triệu backend attempts. Nhưng billed capacity phải tính theo **từng outcome**; network attempt không đến server không giống server đã process rồi response mất.

Lưu cả retry count/timeouts trong telemetry, vì **retry storm** vừa tăng cost vừa làm nghẽn hệ.

## 99. Query anti-pattern tạo cost amplification

Một query phải scan nhiều partitions vì thiếu shard key có thể có:

\[
\text{amplification}
=\frac{\text{bytes examined}}{\text{bytes returned}}
\]

Ví dụ examine 2 GiB để trả 2 KiB là rất đắt về scan/cache/CPU. Tối ưu data model/index thường mang lại hiệu quả lớn hơn chuyển sang service có GB rẻ hơn vài phần trăm.

Không suy exact bill từ amplification ratio nếu provider thu theo provisioned instance, nhưng nó dự báo **capacity headroom bị tiêu thụ**.

## 100. Đo per-request cost thay vì chỉ average DB bill

Một hệ có 3 nhóm tenants:

~~~text
Small tenant:  1,000 requests/day
Medium:      100,000 requests/day
Large:    10,000,000 requests/day
```

Nếu cùng chia bill theo số tenants, tenant nhỏ bị phân bổ không hợp lý và khó biết khách hàng nào tạo hot partitions.

Có thể phân bổ:

- Read/write units theo tenant.
- Storage/index bytes theo tenant.
- Network bytes.
- Dedicated isolation infrastructure.
- Shared platform fixed costs bằng rule rõ.
- Support/on-call nếu account-specific và được phép.

Không dùng tenant ID làm Prometheus label cho hàng triệu tenants; dùng billing aggregation/log data hoặc controlled high-cardinality analytics.

## 101. Phân bổ chi phí shared cluster

Một công thức:

\[
C_t=C_{\text{variable},t}+w_tC_{\text{shared}}
\]

với \(\sum_t w_t=1\).

Chọn trọng số theo:

- Storage footprint.
- Workload units.
- Reserved capacity.
- SLA tier.
- Tenant-specific dedicated resources.
- Hoặc hybrid weights.

Đây là **phương pháp kế toán nội bộ**, không phải phí thực mà cloud provider tính trực tiếp cho từng tenant. Cần ghi rõ denominator và refresh period.

## 102. Chi phí trên 1.000 customers hay 1.000 actions?

Một chỉ số:

\[
\text{DB cost/1,000 active users}
=\frac{C_{\text{DB}}}{DAU}\times1\,000
\]

Có thể hữu ích nhưng dễ gây hiểu nhầm nếu:

- User activity khác nhau.
- Một tenant vài heavy users.
- Background jobs chiếm phần lớn cost.
- Cùng user có nhiều operations.
- Data retention khác nhau.
- Hệ có idle minimum tier.

Nên theo dõi **cost per successful business transaction, cost per retained GiB, cost per active tenant** cùng nhau.

## 103. Cost per 1 triệu operations phải nói rõ loại operations

Một điểm quan trọng:

~~~text
$ per 1M point reads of 1 KiB
```

khác:

~~~text
$ per 1M range queries scanning 10 MiB each
```

Cả hai có 1 triệu API calls nhưng cost và resource usage khác lớn. Ghi query class, item size, consistency, index, cache hit và region khi công bố đơn giá chuẩn hóa.

## 104. Throughput bền vững khác throughput peak ngắn hạn

Một benchmark chạy 60 giây có thể thấy 100k ops/s nhờ cache và burst credits. Sau 5 giờ, CPU/IO/compaction/GC có thể giảm throughput hoặc p99 tăng.

Sizing cho TCO cần:

- Warm and cold cache.
- Multi-hour soak.
- Dataset lớn hơn RAM.
- Compaction cycles.
- Replica rebuild.
- Node failure.
- Index builds.
- Real item sizes.
- Production p99 SLO.

Không dùng **peak microbenchmark** làm sustained capacity của mỗi node.

## 105. Availability reserve phải đi vào sizing

Nếu cluster có N nodes và cần chịu một node/AZ failure:

~~~text
Healthy state: N nodes share traffic.
Failure state: N-k nodes serve all required traffic.
```

Capacity per remaining node cần đủ cho failover load trong SLO. Ví dụ RF=3 nhưng CPU healthy 80% trên từng replica có thể không còn chỗ xử lý failover traffic.

**N+1** hay AZ reserve là **chi phí đáp ứng availability**, không mặc định lãng phí.

## 106. Replica rebuild làm tăng cost trong lúc sự cố

Khi một node hỏng, hệ có thể phải:

- Copy dữ liệu sang node mới.
- Rebuild indexes.
- Repair/migrate partitions.
- Read data from surviving replicas.
- Tăng network/IO.
- Chạy double writes trong transition.
- Maintain quorum.

Sizing 100% disk utilization khiến rebuild khó thực hiện. TCO cần kể **temporary capacity và network** trong recovery scenarios.

## 107. Multi-AZ SLA thường có điều kiện

Một dịch vụ managed nhiều AZ có thể có cam kết availability theo tier/config, nhưng:

- Client driver phải retry/reconnect.
- App pool/transactions có timeout.
- Connection routing phải đúng.
- Quorum behavior có thể làm write unavailable khi mất quá nhiều nodes.
- RPO/RTO không tự bằng 0.
- SLA credits không bù đầy đủ tổn thất kinh doanh.

Không trả tiền HA tier rồi bỏ kiểm thử failover ở ứng dụng.

## 108. Giá rẻ nhưng không đạt latency là sai mục tiêu

Giả sử:

| Phương án | Monthly run-rate | p99 under peak | RPO/RTO | Kết luận |
|---|---:|---:|---|---|
| A | 6.000 USD | 350 ms | Đạt | Không đạt SLO p99 100 ms |
| B | 9.000 USD | 80 ms | Đạt | Hợp lệ để so |
| C | 7.000 USD | 90 ms | Không đạt | Không hợp lệ |
| D | 10.000 USD | 70 ms | Đạt | Hợp lệ để so |

Bảng dùng số giả định. Chỉ B và D đủ để bước tiếp theo so chi phí; A/C cần được resized/redesigned rồi tính lại TCO.

## 109. Một lựa chọn nên được chứng minh bằng workload, không bằng nhãn

Không có quy luật đúng cho mọi hệ:

- “Cassandra luôn rẻ hơn DynamoDB.”
- “MongoDB Atlas luôn đắt hơn self-hosted.”
- “Redis nhanh nên tiết kiệm nhất.”
- “NoSQL luôn rẻ hơn RDBMS.”
- “Serverless rẻ khi ít traffic.”
- “Open source không có license nên TCO thấp.”

Đúng hơn: đo workload, tính physical footprint, scale tới SLO, cộng labor/DR/egress và so scenario distributions.

## 110. Service ownership boundary

Một bảng hữu ích:

| Trách nhiệm | Self-managed | Managed |
|---|---|---|
| OS/node patch | Khách hàng | Thường provider xử lý một phần/lớn |
| Cluster topology | Khách hàng | Provider hỗ trợ, khách hàng chọn config |
| Data model/index | Khách hàng | Khách hàng |
| Query tuning | Khách hàng | Khách hàng |
| Security IAM/app roles | Khách hàng | Chia sẻ trách nhiệm |
| Backup enable/retention | Khách hàng | Khách hàng cấu hình, provider thực thi tùy tier |
| Restore verification | Khách hàng | Khách hàng vẫn phải kiểm |
| Incident root cause | Khách hàng | Provider + khách hàng |
| Application retries | Khách hàng | Khách hàng |
| Cost allocation | Khách hàng | Khách hàng |

Từng hàng phụ thuộc hợp đồng/feature cụ thể. Cần **RACI** hoặc shared responsibility matrix, không suy “managed nghĩa là mọi thứ do provider chịu”.

## 111. Time-to-market là biến kinh tế

Nếu phương án A cần sáu tháng xây cluster custom và phương án B triển khai hai tháng, bốn tháng khác biệt có thể ảnh hưởng:

- Product launch.
- Opportunity cost.
- Engineering roadmap.
- Compliance deadline.
- Hiring.
- Revenue.

Nên báo cáo như **business scenario** thay vì tự cộng một khoản revenue hypothetical không có dữ liệu. Chi phí chuyển đổi và time-to-market đôi khi quan trọng hơn giá storage hàng tháng.

## 112. Vendor lock-in không thể đo chỉ bằng API name

Một hệ dùng một API khá chuẩn nhưng:

- Proprietary query semantics.
- Specialized consistency tokens.
- TTL/stream behaviors.
- Unique indexing and transactions.
- KMS/backup/export integration.
- Large data egress.
- Operational runbooks riêng.

đều tạo chi phí chuyển đổi. Ngược lại, dùng open-source engine nhưng schema/CDC pipeline phức tạp vẫn có lock-in vào kiến trúc tự xây.

TCO exit scenario nên mô tả **data portability, schema/query portability và operational portability** riêng.

## 113. Định giá một lần migration với double-run

Ví dụ giả định:

~~~text
Old cluster run-rate: 12,000 USD/month
New cluster run-rate:  9,000 USD/month
Double-running: 2 months
Migration workers/temp infra: 8,000 USD
Engineering allocation: 30,000 USD
```

Nếu cả hai chạy song song hai tháng, chi phí trong transition có thể là:

\[
2\times(12\,000+9\,000)+8\,000+30\,000
=80\,000\text{ USD}
\]

Không được **cộng 80.000 như hoàn toàn incremental** nếu baseline đã bao gồm chi phí vận hành old cluster trong hai tháng. Phần incremental so với tiếp tục old cluster là:

\[
80\,000-2\times12\,000=56\,000\text{ USD}
\]

Đó là khoản phù hợp hơn cho payback **nếu** không còn hạng mục khác và engineering allocation được tính theo cách nhất quán.

## 114. Tính break-even sau migration

Với tiết kiệm steady-state:

~~~text
Old monthly TCO = 12,000
New monthly TCO = 9,000
Monthly saving = 3,000
Incremental migration investment = 56,000
```

Payback:

\[
56\,000/3\,000\approx18.7\text{ tháng}
\]

Nếu còn 30 tháng sau cutover trong horizon, mô hình đơn giản có thể tiết kiệm \(30\times3\,000-56\,000=34\,000\) USD, chưa tính growth/risk/discount. Cần tính cả **double-run duration thực tế** và khả năng migration kéo dài.

## 115. Một TCO 36 tháng với ba nhóm chi phí

Giả sử một lựa chọn managed:

~~~text
Storage+compute+requests:  8,000 USD/month
Network+backup+support:   1,500 USD/month
Ops people allocation:    2,000 USD/month
Initial/migration:       40,000 USD
```

Recurring total:

\[
8\,000+1\,500+2\,000=11\,500
\]

TCO không discount trong 36 tháng:

\[
36\times11\,500+40\,000=454\,000\text{ USD}
\]

Đây là **giả định hằng tháng không tăng trưởng**; để lập ngân sách thật cần growth/time series, contract discounts và khả năng thay đổi tier.

## 116. Một TCO 36 tháng self-managed

Giả sử self-managed:

~~~text
Compute+storage:          5,000 USD/month
Network+backup+tools:     2,000 USD/month
Ops people allocation:    6,000 USD/month
Initial/automation:      55,000 USD
```

Recurring:

\[
5\,000+2\,000+6\,000=13\,000
\]

36-month TCO:

\[
36\times13\,000+55\,000=523\,000\text{ USD}
\]

Trong **hai kịch bản ví dụ** 115–116, managed thấp hơn 69.000 USD. **Không rút ra kết luận chung về managed vs self-managed**: chỉ thay 0,5 FTE, footprint hoặc giá contract, thứ hạng có thể đổi.

## 117. Chi phí người có thể đổi kết quả

Giả sử self-managed chỉ cần 2.000 USD/tháng nhân sự thay vì 6.000 (đã có tooling/automation/skill), thì:

\[
C_{\text{self}}=36\times(5\,000+2\,000+2\,000)+55\,000
=379\,000
\]

Thấp hơn managed ví dụ 454.000 USD. Điều này minh họa **sensitivity của people cost**.

Nhưng cần hỏi liệu 2.000 USD/tháng có thực sự đủ on-call, backups, security, upgrades và DR trong SLO yêu cầu, không tự giả định.

## 118. Độ nhạy khi data growth 2× nhưng traffic 4×

Một mô hình dự báo:

~~~text
Year 1: storage 1x, requests 1x
Year 2: storage 1.5x, requests 2x
Year 3: storage 2x, requests 4x
```

Không thể nhân cả database bill với 2x hoặc 4x như một đơn giá duy nhất. Cần phân từng thành phần:

- Storage theo data growth.
- Compute theo CPU/RAM/IO bottleneck.
- Request billing theo operations/size.
- Network theo bytes flow.
- Backup theo data/change rate.
- Staffing theo complexity/scale, không nhất thiết tuyến tính.
- Tier upgrades/contract bands.

## 119. Dự báo data size từ arrivals và retention

Nếu mỗi ngày thêm \(n\) records cỡ \(b\) bytes, giữ \(d\) ngày và ít updates:

\[
L_{\text{steady}}\approx n\times b\times d
\]

Ví dụ 1 triệu records/ngày × 1 KiB × 30 ngày ≈ 28,6 GiB logical data.

Nhưng nếu mỗi record có 5 updates/ngày, **write/CDC/log volume** có thể lớn dù live storage vẫn 28,6 GiB; nếu soft-delete giữ 1 năm thì không thể dùng retention 30 ngày.

## 120. Data churn khác growth

Phân biệt:

- **Net growth:** new bytes minus physical removals.
- **Gross writes:** inserts + updates + deletes.
- **Changed bytes:** data rewritten for incremental backups/CDC.
- **Tombstone churn:** deletes/expiry markers.
- **Compaction bytes:** internal storage rewrite.
- **Replication bytes:** transmitted changes.

Một dataset đứng yên ở 1 TB nhưng bị rewrite mỗi ngày có thể tạo nhiều backup/IO/network bills hơn một dataset 2 TB gần như read-only.

## 121. Dự báo peak growth với seasonality

Một e-commerce workload có traffic:

~~~text
Normal days: 3,000 reads/s
Campaign peak: 30,000 reads/s for 2 hours
Annual promotion: 80,000 reads/s for 10 minutes
```

Chỉ average theo tháng có thể cho bill đúng gần đúng theo usage-based meter nhưng **thiếu capacity peak** để đạt SLO. Nên mô hình **hourly profile** hoặc ít nhất percentile và peak duration, cùng autoscaling/burst limits.

## 122. Rủi ro forecast không chính xác

Một provider billing model có thể rẻ ở dự báo +20% tăng trưởng nhưng rất đắt ở +300%. Cần bảng scenarios:

| Input thay đổi | TCO sensitivity cần xem |
|---|---|
| Data 2× | Storage, index, backup, replicas |
| Read RPS 5× | Read capacity, cache, network, CPU |
| Write RPS 3× | WCU/IOPS, replication, CDC, compaction |
| Index count +3 | Storage, write amplification, search |
| Multi-region replication | Storage, compute, transfer, ops |
| RTO từ 4h xuống 5m | Warm/hot DR, on-call, automation |
| Team skill thiếu | Staffing, migration, incident risk |
| Egress price tăng | Cross-cloud/region and exit economics |

Mục tiêu là tìm **điểm khiến thứ hạng lựa chọn thay đổi**, không chỉ tính một con số “chính xác đến cent”.

## 123. Unit economics có thể cải thiện dù bill tăng

Nếu database bill từ 10.000 lên 20.000 USD/tháng nhưng số successful orders từ 100.000 lên 300.000:

- Cũ: 0,10 USD/order.
- Mới: khoảng 0,0667 USD/order.

Bill tăng nhưng **cost per completed order giảm**. Không tối ưu mọi tháng để bill tuyệt đối giảm khi business đang mở rộng, miễn chi phí đơn vị và SLO tốt.

## 124. Unit economics có thể xấu dù storage không tăng

Nếu số API reads tăng do N+1 query hoặc polling nhưng business transactions đứng yên, cost per order tăng.

Tối ưu:

- Batching.
- Caching.
- Query projection.
- Eliminating unused indexes.
- Avoiding repeated scans.
- Changing data model.
- Reducing chatty network calls.
- Index coverage.
- Client-side dedupe.
- TTL/retention hygiene.

**Tối ưu truy cập dữ liệu** đôi khi tiết kiệm nhiều hơn đàm phán đơn giá 5%.

## 125. Tách cost savings và performance impact

Một đề xuất bỏ secondary index có thể tiết kiệm 500 USD/tháng nhưng làm p99 search tăng 50→800 ms, không đạt SLO.

Bảng quyết định:

| Hành động | Chi phí | Độ đúng và SLO | Kết luận |
|---|---|---|---|
| Bỏ index không dùng | Có thể giảm | Không đổi nếu thật sự unused | Cân nhắc |
| Bỏ index critical | Giảm writes | Query chậm/uniqueness lỗi | Không hợp lệ |
| Giảm RF=3→1 | Giảm bytes | Mất fault tolerance | Không hợp lệ nếu HA bắt buộc |
| Giảm log retention | Giảm bytes | Có thể mất CDC replay/DR | Cần risk review |
| Dùng batch writes | Có thể giảm overhead | Có thể mất conditional safety | Chỉ khi semantics phù hợp |
| Cache hot reads | Có thể giảm DB reads | Freshness/correctness cần bảo vệ | Benchmark và model |

Chi phí thấp không được mua bằng **mất bất biến nghiệp vụ**.

## 126. Cho dù có autoscaling vẫn cần limit

Một on-demand service có thể scale theo usage nhưng:

- Per-partition limits vẫn tồn tại.
- Account quotas.
- Sudden traffic surge.
- Provisioning latency.
- Budget runaway.
- Retry amplification.
- Hot key pressure.

Cần **budget alerts, rate limits, workload control và query safety**. Autoscaling không có nghĩa performance vô hạn hoặc bill có trần tự động.

## 127. Cost spike có thể do bug

Ví dụ:

- Một endpoint bỏ cache.
- Retry vô hạn sau timeout.
- Query filter bị mất index.
- CDC consumer replays toàn stream.
- Schema migration tạo duplicate index writes.
- Truy vấn cross-region ngoài ý muốn.
- Background scan chạy quá nhiều workers.
- Backup retention lifecycle lỗi.
- TTL không dọn item.
- Log volume tăng bất thường.

FinOps monitoring nên xem **cost anomaly như incident signal** và đối chiếu deployment/traffic, không chỉ chờ hóa đơn cuối tháng.

## 128. Cost allocation và trách nhiệm

Gắn metadata/tag/labelling phù hợp:

~~~text
environment: production
team: platform
service: checkout
project: no-sql-core
region: ...
costCenter: ...
dataClass: ...
```

Nếu provider billing hỗ trợ, tags giúp phân bổ. Nhưng chi phí shared managed service có thể không gắn trực tiếp mỗi request; cần **internal allocation model** đã được thống nhất.

Không gắn tenant ID/card number hoặc PII vào billing tags/metric labels.

## 129. Budget guardrails

Ví dụ:

~~~yaml
finops:
  monthlyBudgetUsd: 20000
  warningAtPercent: 75
  criticalAtPercent: 90
  monitor:
    - databaseCompute
    - storageAndIndexes
    - backupAndPitr
    - crossRegionTransfer
    - queryRequests
    - dataPipelines
  actions:
    warning: investigateUsageChange
    critical: pageOwnerAndAssess
```

**Số 20.000 USD chỉ minh họa.** Không tự động tắt critical database khi budget threshold bị vượt, vì downtime/corruption có thể đắt và nguy hiểm hơn. Tự động hóa nên ưu tiên giới hạn **background/noncritical workloads** theo runbook.

## 130. Đo chi phí đến đủ gần thời gian thực

Provider billing thường có delay và aggregation. Một dashboard tốt kết hợp:

- Actual billed cost khi có.
- Usage units near real-time.
- Estimated variable cost.
- Provisioned capacity/instance floor.
- Budget vs forecast.
- Anomaly by service/region.
- Per-tenant/workload attribution.
- Data storage/index growth.
- Backup retention.
- Retry/scan amplification.

Ghi rõ **estimated vs finalized billed**. Không tuyên bố con số realtime chính xác khi provider usage data chưa đầy đủ.

## 131. Chi phí tăng do migration backfill

Một data migration có thể vừa:

- Đọc tất cả source data.
- Ghi target data.
- Xây indexes.
- Duy trì CDC catch-up.
- Giữ source và target 2 tháng.
- Chạy validation scans.
- Transfer cross-region/cloud.

Một dự toán phải tính **temporary peaks** về RCU/WCU, storage, network, worker compute và on-call. Không lấy monthly steady-state cost của target để dự báo migration bill.

## 132. Cost of observability under incidents

Trong sự cố, bật debug logs hoặc tracing 100% có thể tăng ingested GB. Nhưng cắt observability quá mạnh có thể kéo dài MTTR.

Một runbook hợp lý:

- Sampling bình thường.
- Escalation sampling có giới hạn.
- Redaction/PII control.
- Short retention cho debug.
- Preserve critical audit logs.
- Automate revert debug verbosity.
- Budget alert ở log platform.
- Link traces to database operations.

Không dùng giảm log volume như biện pháp duy nhất để giải bill tăng nếu underlying query/retry bug vẫn tồn tại.

## 133. License/support tier cũng có floor

Một cloud support plan hoặc enterprise database license có thể thu theo:

- Percentage of monthly spend.
- Node/vCPU count.
- Annual minimum.
- SLA tier.
- Named support contacts.
- Feature bundles.
- Contract commitments.

Khi tăng compute/service footprint, support bill có thể tăng không tuyến tính. Đưa support/license vào từng scenario, không chỉ base case.

## 134. Bảo mật và data deletion có thể đòi capacity riêng

Data erasure/compliance jobs có thể:

- Đọc/write nhiều bảng/indexes.
- Chạy CDC invalidation.
- Cleanup backups/projections.
- Ghi audit logs.
- Verify deletion coverage.
- Tốn engineering time.
- Có deadline pháp lý.

Nếu dữ liệu được giữ lâu không cần thiết, cost tăng; nhưng xóa nhanh hơn retention policy hoặc không khôi phục được audit cũng không hợp lệ. TCO luôn nằm trong **hàng rào compliance**.

## 135. Query SLO thay đổi cost curve

Một cấu hình đạt p99 300 ms có thể không đạt p99 30 ms với cùng throughput. Để giảm latency:

- Larger nodes.
- More memory/cache.
- More read replicas.
- Better index.
- Sharding.
- Local-region copy.
- Additional cache.
- Denormalized projection.

Cần định giá **cost at p99 target**, không lấy đơn giá công bố cho “đạt bao nhiêu ops/s” không kèm tail-latency condition.

## 136. Thay đổi consistency cũng thay cost

Một ứng dụng yêu cầu strong read sau write ở mọi region có thể phải:

- Trả multi-region coordination RTT.
- Dùng read quorums.
- Dùng single writer authority.
- Retry conflicts.
- Duy trì thêm replicas.
- Giữ sessions/causal tokens.
- Cấp capacity cho consensus.

Nếu eventual consistency đủ, một read model ở region gần có thể rẻ/nhanh hơn. Nhưng **không đổi từ strong sang eventual chỉ để giảm cost** nếu sẽ làm sai payment/inventory/authorization invariants.

## 137. Cost of poor data model là nợ kỹ thuật

Một partition key không phù hợp có thể tạo:

- Hot partitions.
- Scattered queries.
- Secondary indexes dày.
- Client fan-out.
- Expensive repair/repartition.
- Data duplication.
- CDC projections.
- Cross-tenant co-location issues.
- Increased operational time.

Chi phí ban đầu tiết kiệm vài tuần thiết kế có thể tạo years of cost amplification. TCO nên tính **khả năng tiến hóa schema/query** khi business requirements thay đổi.

## 138. Có nên tính giá theo transaction hay request?

Nếu business logic quan trọng, nên xem cả hai:

- **Request metering:** hợp billing model và capacity.
- **Business transaction cost:** gắn với unit economics.

Một checkout có thể gồm hàng chục SDK requests. Tối ưu một số queries/transactions không nhất thiết giảm số orders nhưng có thể giảm cost per successful checkout.

## 139. Benchmarks phải report failures và retries

Một benchmark báo “100k ops/s” nhưng 20% operations timeout hoặc dữ liệu sai là không hợp lệ để sizing.

Cần:

- Offered operations/s.
- Successful business operations/s.
- Error rates and types.
- p95/p99.
- Resource usage.
- Retry attempts.
- Correctness assertions.
- Test duration.
- Data size and hot-key distribution.
- Failover/repair behavior.

Đo **successful throughput under SLO** làm đầu vào capacity/price.

## 140. Chọn đại diện dữ liệu

Nếu production document sizes có phân phối:

~~~text
50%  = 1 KiB
40%  = 8 KiB
9%   = 64 KiB
1%   = 1 MiB
```

benchmark chỉ dùng 1 KiB item sẽ đánh giá thấp memory, network, WCU/RCU rounding, serialization và p99 latency.

Nên dùng distribution đại diện, có edge cases gần provider item limits. Tính bill theo **size buckets và operation classes** thay vì một item size trung bình không đủ.

---

## 141. Quy trình đánh giá ba phương án

Giả sử đang so:

- **A:** NoSQL managed key-value/document trả theo requests và storage.
- **B:** Document database dedicated cluster managed.
- **C:** Wide-column cluster self-managed.

Không nên bắt đầu từ giá. Quy trình:

1. Ghi business data invariants và queries.
2. Loại phương án không đạt API/consistency requirements nếu không redesign.
3. Định nghĩa cùng failover/RPO/RTO requirements.
4. Đo dataset/workload representative.
5. Benchmark successful throughput ở p99 target.
6. Sizing cả normal và failure states.
7. Ánh xạ sizing sang billable meters riêng.
8. Cộng index/replication/backup/network/people.
9. Thêm migration và exit scenarios.
10. Tính 12/36-month scenarios và độ nhạy.
11. Chọn phương án đạt requirements với **risk-adjusted TCO** hợp lý.
12. Lưu assumptions và review định kỳ.

## 142. Một bảng chi phí chuẩn hóa

| Hạng mục | Phương án A | Phương án B | Phương án C |
|---|---|---|---|
| Storage primary | GB-month/meter | Volume/GB-month | Disk per node |
| Replica cost | Included? explicit? | Replicas/tiers | Node/disk/network |
| Index cost | GSI/index meters | Storage/compute | Per-node index + write load |
| Read/write | Request units | Cluster capacity | Provisioned CPU/IO |
| Network | Egress/region | Egress/region | Cluster links/egress |
| Backup/PITR | Separate or included | Separate or included | Tooling/storage/labor |
| DR | Region replicas | Cluster replicas | Full standby/restore |
| People | Application + platform | Application + platform | Application + DBA/SRE |
| Support/license | Contract | Contract | Vendor/support optional |
| Migration | Export/import/CDC | Export/import/CDC | Bootstrap/backfill |
| Exit | Egress + rewrite | Data/API conversion | Data/API conversion |

Chỉ sau khi điền số liệu cụ thể từ provider quotes mới tính total. “Included?” phải được trả lời bằng hợp đồng, không mặc định.

## 143. Đặt cùng dữ liệu workload đầu vào

Ví dụ dataset để so:

~~~yaml
workload:
  retainedLogicalDataGiB: 800
  annualDataGrowthPercent: 50
  documentSize:
    p50KiB: 1
    p95KiB: 8
    p99KiB: 64
  operations:
    averagePointReadsPerSecond: 3000
    peakPointReadsPerSecond: 15000
    averageConditionalWritesPerSecond: 500
    peakConditionalWritesPerSecond: 2500
    occasionalRangeQueriesPerSecond: 30
  indexes:
    - tenantAndStatus
    - emailCanonicalUnique
    - createdAtRange
  availability:
    zoneFailureTolerance: required
    writeRpoSeconds: strictBusinessPolicy
    restoreRtoMinutes: 60
  security:
    encryptionAtRest: required
    privateNetworking: required
    audit: required
  regions:
    primary: regionA
    disasterRecovery: regionB
~~~

Chưa thể tính chi phí ngay vì còn thiếu provider pricing, read/write size distributions, physical compression, index sizes và DR strategy. Việc nêu **thiếu dữ liệu** là một phần của sizing có trách nhiệm.

## 144. Tách khâu sizing và pricing

**Sizing** trả lời:

~~~text
How many nodes/GB/RUs/IOPS/replicas are needed
to satisfy the SLO and failure model?
```

**Pricing** trả lời:

~~~text
How does provider contract bill that configuration
and usage in a chosen region and time period?
```

Trộn hai bước làm khó giải thích tại sao bill thay đổi. Nếu p99 benchmark khiến cần 8 nodes thay vì 4, đó là **sizing change**. Nếu provider tăng price per node, đó là **pricing change**.

## 145. Đo capacity từ load test

Một load test cần phát biểu:

~~~text
Service configuration
Dataset: representative size and index distribution
Concurrency: realistic client count
Operation mix: reads/writes/scans
Consistency: documented
Duration: sufficient for steady-state
Fault state: healthy vs one AZ/node unavailable

Observed:
  successful ops/s
  p50/p95/p99
  error/throttle rates
  CPU/RAM/disk IO/cache
  replication lag
  compaction and GC
```

Capacity được chấp nhận khi **sustained successful throughput** đạt p99 và error budgets, gồm reserve cho failure; không chỉ đạt peak RPS 1 phút.

## 146. Benchmark phải tách warm/cold cache

Một dataset 100 GiB trên RAM 200 GiB có thể trả reads rất nhanh. Production data 5 TiB nhưng RAM chỉ 300 GiB sẽ khác.

Nên đo:

- Data larger than hot cache.
- Cold-start/warm-up.
- Cache hit/miss distribution.
- Query projection/index behavior.
- Scan-induced cache churn.
- Replica rebuild.
- Varying item sizes.
- Seasonal peaks.

Đây là lý do không được lấy kết quả benchmark công khai của vendor làm sizing cuối cùng mà không mô tả workload/constraints tương đương.

## 147. Công thức node count nên có utilization target

Giả sử mỗi node xử lý bền vững 2.000 writes/s ở p99 SLO khi khỏe. Ứng dụng cần 6.000 writes/s, muốn duy trì khi mất một node.

Nếu mỗi node đạt 2.000 trong failure state và các constraints khác không giới hạn:

\[
(N-1)\times2000\ge6000
\]

\[
N\ge4
\]

Cần **ít nhất 4 nodes** theo mô hình đơn giản. Trên thực tế consistency/RF/placement/partition skew có thể buộc nhiều hơn; phần minh họa chỉ cho thấy capacity failover tạo chi phí dự phòng.

## 148. Cost per capacity unit không đủ để chọn node

Một instance A giá 1 USD/h và 1.000 writes/s; instance B giá 2 USD/h và 3.000 writes/s.

B có throughput/$ tốt hơn theo benchmark đó, nhưng:

- RAM/index fit?
- Latency p99 ở peak?
- Query mix?
- Storage/network limits?
- Replica topology?
- Failure reserve?
- Cost of larger instance step?
- Scaling granularity?

Không chọn B chỉ bằng writes/$. Khi traffic thấp, A có thể rẻ hơn vì không cần capacity B; khi cao, B có thể kinh tế hơn.

## 149. Chi phí index build một lần và duy trì lâu dài

Khi thêm index:

- **Build cost:** full scan, CPU/IO, temporary disk, network, possible maintenance risk.
- **Ongoing storage:** index bytes × replicas.
- **Ongoing write cost:** index updates.
- **Savings:** fewer scans/reads, lower query latency.
- **Operations:** rebuild/repair/monitoring.

Một index có thể có payback khi query frequency đủ cao. Đừng đánh giá chỉ bằng GB tăng sau index creation.

## 150. Index ROI ví dụ

Giả sử index làm giảm compute/query cost được quy đổi theo workload từ 900 xuống 200 USD/tháng, nhưng index storage + write overhead thêm 250 USD/tháng và build một lần tốn 1.000 USD.

Monthly net saving:

\[
900-200-250=450\text{ USD}
\]

Payback sơ bộ:

\[
1000/450\approx2.22\text{ tháng}
\]

Nếu index còn giúp p99 đạt SLO bắt buộc, giá trị của nó không chỉ là net dollar. Các số là giả định minh họa, cần verify bằng bill/capacity measurements.

## 151. Query projection và index có thể thay nhau một phần

Một workload:

~~~text
Find top 100 orders by tenant/status/date
```

có thể dùng:

- Compound index.
- DynamoDB GSI.
- Denormalized key-based projection.
- Search engine.
- Materialized view.
- Precomputed report.

Mỗi lựa chọn có **read cost, write amplification, CDC complexity, latency, consistency và operations burden** khác. TCO so **toàn pipeline** để đạt query guarantee, không chỉ chi phí lưu một index.

## 152. Cân đối backup retention

Giả sử 1 TB live data và backup delta 100 GB/ngày; giữ 30 ngày. Không thể suy bill bằng `1 TB × 30` nếu snapshots incremental có shared blocks, nhưng cũng không thể chỉ tính 1 TB nếu changed blocks cần giữ.

Cần lấy:

- Actual billed snapshot bytes over time.
- Full/partial backup semantics.
- PITR log retention.
- Retention after deletion.
- Compression/dedup.
- Copy across region.
- Restore/retrieval charges.

Một tuần thử nghiệm với sample dataset có **churn đại diện** thường giúp dự báo chính xác hơn lý thuyết.

## 153. Backup compression làm thay recovery time

Backup nén nhiều có thể giảm storage và transfer nhưng tăng CPU khi restore. Nếu RTO 15 phút, restore job có thể cần nhiều parallel restore workers/IOPS hơn.

TCO không tối ưu backup $ mà làm **không đạt RTO**.

## 154. Network transfer trong managed service có thể đã bao gồm một phần

Không phải mọi replica byte đều hiện thành một dòng charge. Provider có thể:

- Include some intra-region replication.
- Charge regional/global replica writes.
- Charge inter-region egress.
- Charge private-link bytes.
- Charge object-storage export separately.

Một cost model cần **bill item mapping**:

~~~text
Physical event
  -> Provider meter
  -> Rate tier/discount
  -> Billed units
```

Nếu không có meter độc lập, đánh dấu **included**, không nhân bytes rồi tính lại.

## 155. Double counting checklist

Những lỗi cộng trùng:

- Tính RF=3 raw bytes nhưng managed billed storage đã bao gồm replicas.
- Tính CPU in node price rồi cộng compute line từ benchmark khác.
- Tính snapshots và PITR logs trùng cùng block delta.
- Tính egress hai lần ở source và destination theo cùng meter.
- Tính một kỹ sư toàn thời gian ở cả team platform và application.
- Tính support percentage trên spend đã bao gồm support.
- Cộng cost of downtime và SLA credits như hai khoản độc lập không có quy tắc.
- Cộng migration gross cost nhưng không trừ baseline old cluster đã có.

Ghi rõ **cost scope** và identity của từng meter.

## 156. Sunk cost không phải lý do giữ kiến trúc

Nếu doanh nghiệp đã đầu tư 100.000 USD vào một cluster cũ, phần tiền đã chi không phải **future incremental cost** của lựa chọn hôm nay.

Nên so:

- Future cost if keep.
- Future cost if migrate.
- One-time migration costs.
- Contract termination fees.
- Risks/benefits.
- Depreciation/capital policy khi cần báo cáo tài chính.

Không giữ một hệ đắt chỉ vì “đã lỡ đầu tư”. Nhưng cũng không phớt lờ exit cost hay unamortized contractual obligations thực tế.

## 157. TCO vs cash-flow budget

TCO có thể phân bổ nhân lực và chi phí cơ hội, còn CFO có thể muốn **cash expenditure theo tháng**.

Nên báo hai góc:

1. **Cash flow:** vendor invoices, salaries/new hires, infra commitments, migration expenses.
2. **Economic TCO:** cash + allocated engineering effort + quantified expected costs theo policy.

Không giả vờ hai số phải bằng nhau; mô hình có mục đích khác.

## 158. Một template bảng dự toán tháng

| Cost category | Sizing basis | Unit price | Monthly estimated |
|---|---|---|---|
| Database compute | Nodes × hours | Quote | Calculated |
| Data storage | Billed GB-month | Quote | Calculated |
| Index | Index GB/RU/WCU | Quote | Calculated |
| Read capacity | Units or requests | Quote | Calculated |
| Write capacity | Units or requests | Quote | Calculated |
| Replication | Additional nodes/meter | Quote | Calculated |
| Cross-region transfer | Billable GB | Quote | Calculated |
| Backup/PITR | GB-month/change bytes | Quote | Calculated |
| Monitoring | Ingest/retained GB | Quote | Calculated |
| KMS/security | Keys/calls/tools | Quote | Calculated |
| Support/license | Contract | Quote | Calculated |
| Engineering operations | FTE × loaded cost | Internal | Calculated |
| Migration | One-time event | Plan | Separate |
| Risk/contingency | Scenario/budget policy | Internal | Separate |

Tất cả rows có **source of assumption, date/region/version** và owner. Đây là cấu trúc mô hình, không phải file Excel được tạo ở STEP 4.

## 159. Quy tắc estimate vs observed

Mỗi hạng mục nên có trạng thái:

~~~text
OBSERVED: provider billing, actual resource usage
BENCHMARKED: measured with representative workload
QUOTED: official provider/contract rate for chosen region
ASSUMED: explicit estimate with sensitivity range
UNKNOWN: requires investigation
```

Không gộp `ASSUMED` và `OBSERVED` dưới một cột “actual”. Khi ra quyết định lớn, cố giảm các `UNKNOWN` có ảnh hưởng cao.

## 160. Chuẩn hóa sources và effective dates

Bảng giá có thể đổi theo:

- Date.
- Region.
- Storage class/tier.
- Billing mode.
- Discount contract.
- Feature.
- Data transfer boundaries.
- Support plan.
- Currency.
- Account-specific credits/commitments.

Mỗi số được dùng trong mô hình cần metadata:

~~~yaml
priceAssumption:
  source: providerQuoteOrContract
  asOfDate: explicitDate
  region: explicitRegion
  productSku: explicitSku
  currency: USD
  taxIncluded: false
  discountApplied: documented
  sourceOwner: procurementOrFinOps
~~~

Các fields này giúp 6 tháng sau biết tại sao dự toán khác bill, không phải đoán.

## 161. Khi pricing không minh bạch

Một số enterprise contracts cần sales quote hoặc có custom tiers không công khai.

Cách làm:

- Request written itemized quote.
- Cung cấp workload/SLO/region đồng nhất.
- Yêu cầu nêu assumptions/scaling thresholds.
- Làm rõ support, backup, egress, overages.
- Hỏi pricing khi growth 2× và 5×.
- Kiểm termination/export conditions.
- So quote với usage meter khả dụng.

Nếu chưa có giá, dùng **range với explicit uncertainty** và ghi blocker cho quyết định, không bịa số.

## 162. Tối ưu theo thứ tự tác động

Một chuỗi thường hiệu quả:

1. Loại queries full scan/anti-pattern gây amplification.
2. Bỏ indexes không dùng (sau verification).
3. Tối ưu projection/key/partitioning.
4. Kiểm TTL/retention hợp lệ.
5. Giảm duplicate writes/retry storms.
6. Cache đúng access pattern và invalidation.
7. Chọn node/tier phù hợp working set và p99.
8. Dùng autoscaling/commitment phù hợp.
9. Tối ưu network/data locality.
10. Đàm phán đơn giá khi đã hiểu usage.

Không tối ưu bằng cách giảm replication/RPO hoặc consistency cần thiết cho dữ liệu critical.

## 163. Cost optimization phải có correctness gates

Ví dụ hành động:

~~~text
Reduce write concern to save latency/capacity
Disable audit logging
Shorten CDC retention
Remove unique index
Use eventual reads for inventory
```

Mỗi hành động có thể đe dọa durability, compliance hoặc invariant. Mọi proposal cần review:

- What SLO/invariant changes?
- What new failure mode?
- Does RPO/RTO change?
- How is data loss prevented?
- Can behavior be tested under failover?
- Is rollback safe?
- Who approves?

Không đặt **savings** lên trước một business invariant bắt buộc.

## 164. FinOps dashboard cho NoSQL

Một dashboard nên có:

**Chi phí**

- Total billed vs budget.
- Compute/storage/requests/network/backup.
- Estimated current-month cost.
- Unit economics.
- Reserved vs idle capacity.
- Anomaly alerts.

**Kỹ thuật**

- Logical/physical data.
- Index/storage growth.
- Read/write throughput by class.
- p95/p99 SLO.
- Replication lag/CDC lag.
- Hot partitions.
- Backup success/restore drill.
- Cache efficiency.
- Node utilization and headroom.
- Compaction/IOPS.

Không chỉ vẽ tiền mà thiếu **nguyên nhân workload** làm bill biến đổi.

## 165. Một SLO/cost dashboard cần time alignment

Nếu bill tăng sau deploy, đối chiếu:

~~~text
Deployment/version changes
Read/write volume changes
Average item size
Query scanned/returned ratio
New indexes
Retry rate
Cross-region traffic
Backup retention
Cluster tier upgrade
Production p99
```

Tránh kết luận “deploy X gây cost spike” chỉ vì trùng thời điểm nếu còn campaign/traffic spike hoặc thay đổi billing SKU.

## 166. Anomaly budget và automated background throttling

Một policy có thể:

~~~text
If historical backfill consumes too many read units:
  throttle background scan.

If CDC retention margin decreases:
  prioritize change capture/catch-up.

If monthly budget approaches limit:
  alert owners, inspect anomalies.

If critical production SLO violated:
  pause noncritical migration job.
```

Không tự động shutdown authoritative writes khi chi phí vượt budget: việc mất dịch vụ có thể vi phạm SLA và gây thiệt hại lớn hơn.

## 167. Bài thực hành với Java: tính monthly operations

Một utility Java 17+ cho phần **unit conversion** (không gọi provider):

~~~java
import java.math.BigDecimal;

public final class WorkloadUnits {
    private static final long SECONDS_PER_DAY = 86_400L;

    public static long operationsPerMonth(
            long averageOpsPerSecond, int days) {
        return Math.multiplyExact(
            averageOpsPerSecond,
            Math.multiplyExact(days, SECONDS_PER_DAY)
        );
    }

    public static BigDecimal costFromMillions(
            long operations, BigDecimal usdPerMillion) {
        return BigDecimal.valueOf(operations)
            .multiply(usdPerMillion)
            .divide(BigDecimal.valueOf(1_000_000L));
    }

    public static void main(String[] args) {
        long reads = operationsPerMonth(3_000, 30);
        long writes = operationsPerMonth(500, 30);
        System.out.println("reads=" + reads);
        System.out.println("writes=" + writes);
    }
}
~~~

Output theo mô hình average cố định:

~~~text
reads=7776000000
writes=1296000000
```

`costFromMillions` chỉ hợp lệ với **đơn giá thật sự tính theo 1 triệu operations đồng loại**. Nếu provider tính units theo item size/consistency, cần chuyển thành billed units trước. `Math.multiplyExact` giúp phát hiện overflow với input cực lớn thay vì wrap âm.

## 168. Java: mô hình physical storage theo BigDecimal

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class StorageEstimate {
    public static BigDecimal allocatedGb(
            BigDecimal logicalGb,
            BigDecimal compressionFactor,
            BigDecimal indexRatio,
            int fullReplicas,
            BigDecimal utilization) {

        if (logicalGb.signum() < 0
                || compressionFactor.signum() <= 0
                || indexRatio.signum() < 0
                || fullReplicas <= 0
                || utilization.signum() <= 0
                || utilization.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("Invalid sizing inputs");
        }

        return logicalGb
            .multiply(compressionFactor)
            .multiply(BigDecimal.ONE.add(indexRatio))
            .multiply(BigDecimal.valueOf(fullReplicas))
            .divide(utilization, 2, RoundingMode.CEILING);
    }
}
~~~

Đây là **mô hình sơ bộ**, không phải bill estimator vendor. Nó giả định index ratio tính trên data đã nén, replicas đầy đủ, chưa gồm backups/log/metadata và phần utilization là disk target. Khi tính thực tế cần tránh double counting với billing SKU.

## 169. Java: truy vết cost per operation

Một Java service có thể instrument:

~~~java
record DbOperationMeter(
    String operationClass,
    String targetTableOrCollection,
    long inputBytes,
    long outputBytes,
    double consumedCapacityUnits,
    int attempts,
    boolean businessSuccess,
    long elapsedNanos) {}
~~~

Một collector theo **query class** có thể ghi:

- Billed/consumed units khi SDK expose.
- Bytes/operation.
- Retry count.
- p95/p99 latency.
- Business success.
- Collection/table scope.
- Route/service.

Không đưa raw user/tenant keys vào metric labels có cardinality lớn hoặc PII. Bên thu thập nên phân biệt **SDK estimated units vs provider billed units**.

## 170. Java: `System.nanoTime()` cho latency

~~~java
long started = System.nanoTime();
try {
    return databaseCall();
} finally {
    long nanos = System.nanoTime() - started;
    operationLatency.record(nanos);
}
~~~

Đo duration trong cùng JVM bằng monotonic timer; không dùng `Instant.now()`/wall time delta vì NTP step có thể làm sai elapsed. Cần đo **end-to-end retry attempt** và per-attempt latency riêng khi muốn biết cost amplification.

`operationLatency` là dependency ứng dụng giả định, không phải class Java chuẩn.

## 171. Java instrumentation không tự đo provider cost

Một app có thể đo SDK calls, nhưng:

- Replica traffic nằm ở server side.
- Internal compaction không đi qua SDK.
- Provisioned idle capacity vẫn bill.
- Backup/PITR do service quản lý.
- Cross-region fees có network meters.
- Support/license nằm trong contract.
- FTE không đo bằng Java.

Vì vậy telemetry ứng dụng là một phần của **usage model**, phải reconcile với provider billing và infrastructure metrics.

## 172. Tự động reconcile dự toán và hóa đơn

Mỗi tháng:

~~~text
Estimated cost by meter
  -> provider billing export
  -> variance by SKU/region/environment
  -> root cause of variance
  -> update assumptions and forecast
```

Hãy phân biệt:

- Unit price variance.
- Usage variance.
- Workload shape change.
- Index/replication amplification.
- Feature/tier changes.
- Billing delay/correction.
- Discount/credit differences.
- Currency/tax effects.
- Cost allocation mismatch.

Một số mục không thể gắn exact invoice line tới một Java operation; cần xác định reconciliation granularity.

## 173. Phân tích độ nhạy có thứ tự ưu tiên

Một cách:

1. Xác định base TCO.
2. Thay từng input ±20–50% theo uncertainty hợp lý.
3. Xem input nào thay thứ hạng lựa chọn.
4. Thử combinations/realistic correlated growth.
5. Thu thập đo lường tốt hơn cho top uncertain drivers.
6. Chỉ mua/di chuyển khi cost confidence đủ để quyết định.

Ví dụ nếu people cost thay từ 2.000 tới 6.000 USD/tháng khiến self-managed đảo từ rẻ sang đắt, đây là input cần team staffing estimate thật.

## 174. Khi nào nên tạm dừng quyết định chọn engine?

Nếu còn thiếu:

- Access pattern và data size distribution.
- p99 under load.
- Operational ownership.
- RPO/RTO.
- CDC/backup requirements.
- Hot partition distribution.
- Real quotes hoặc pricing units.
- Compliance/region.
- Migration and exit cost.
- Functional correctness proof.

Không nên chỉ chốt vì có một bảng vendor so sánh đơn giá GB. Trạng thái đúng có thể là **“chưa đủ dữ liệu, cần benchmark/quote”** với danh sách việc rõ, không phải bịa một winner.

## 175. Decision record cho lựa chọn NoSQL

Một Architecture Decision Record có thể chứa:

~~~text
Context:
  Workload, business invariants, scale and growth.

Constraints:
  SLO, RPO/RTO, data residency and budget.

Candidates:
  A, B, C with versions and deployment models.

Evaluation:
  Functional fit and compliance gates.
  Benchmark methodology/results.
  Sized topology normal and failure states.
  Billing meters and vendor quotes.
  Storage/index/replication/traffic estimates.
  People/support/migration/exit costs.
  12/36-month TCO under base/high/stress.
  Sensitivity and uncertainty.

Decision:
  Chosen option, accepted trade-offs and reasoning.

Consequences:
  Operational responsibilities, monitoring,
  rollback/exit plan, next review date.
```

Một ADR minh bạch giúp đội ngũ hiểu **vì sao phương án được chọn đúng lúc đó** và khi workload/contract thay đổi thì nên xem lại.

---

## 176. Bài tập A — Physical storage với RF

**Đề:** logical data 500 GB, compression ratio 0,65, indexes bằng 25% compressed data, RF=3, target utilization 80%. Chưa tính logs/backups.

**Hướng giải:**

\[
500\times0.65\times1.25\times3/0.8
=1523.4375\text{ GB}
\]

Khoảng 1,52 TB allocated theo mô hình. Không nhân RF nữa nếu billed storage đã bao gồm replication.

## 177. Bài tập B — Không có index

**Đề:** giữ dữ liệu của bài A, không có secondary indexes, các yếu tố khác giữ nguyên. Dung lượng?

**Hướng giải:**

\[
500\times0.65\times3/0.8=1218.75\text{ GB}
\]

Chênh lệch khoảng **304,69 GB allocated** theo giả định, nhưng cần xét query CPU/IO nếu bỏ index.

## 178. Bài tập C — Giảm compression ratio

**Đề:** logical 1000 GB, compression 0,5 thay 0,8, RF=3, chưa indexes/headroom. Tiết kiệm physical bytes?

**Hướng giải:**

\[
1000\times(0.8-0.5)\times3=900\text{ GB}
\]

Nhưng compression CPU và actual engine/index ratio phải benchmark.

## 179. Bài tập D — GB và GiB

**Đề:** 500 GiB trong bảng OS bằng bao nhiêu GB decimal gần đúng?

**Hướng giải:**

\[
500\times2^{30}/10^9\approx536.87\text{ GB}
\]

Không nhân 500 với đơn giá GB khi dữ liệu được báo bằng GiB mà không quy đổi.

## 180. Bài tập E — Average RPS sang tháng

**Đề:** 3.000 reads/s trong 30 ngày đều đặn.

**Hướng giải:** \(3\,000\times2\,592\,000=7\,776\,000\,000\) reads/tháng.

## 181. Bài tập F — Writes/tháng

**Đề:** 500 writes/s trong 30 ngày đều đặn.

**Hướng giải:** \(500\times2\,592\,000=1\,296\,000\,000\) writes/tháng.

## 182. Bài tập G — Peak khác average

**Đề:** bình thường 1.000 writes/s, đỉnh 10.000 writes/s chỉ 2 giờ/ngày.

**Hỏi:** có thể nhân 10.000 × 30 ngày để tính mọi monthly writes?

**Hướng giải:** không. Cần hourly profile. Peak có vai trò sizing, average/time integral quyết định usage billing theo meter tương ứng.

## 183. Bài tập H — Cache hit rate

**Đề:** user requests=10.000/s, hit rate=90%, mỗi hit tránh đúng một source read.

**Hướng giải:** source reads ≈1.000/s. Nhưng cộng chi phí RAM/cache infrastructure, network, invalidation và failure cache-miss storm.

## 184. Bài tập I — Cost per million units

**Đề:** 20 triệu homogeneous billed units/tháng, đơn giá giả định 0,20 USD/1 triệu units.

**Hướng giải:** \(20\times0.20=4\) USD/tháng, **chỉ** cho meter giả định ấy, không phải tổng database bill.

## 185. Bài tập J — Unit rounding

**Đề:** một write 1,2 KiB vào dịch vụ tính units theo mỗi 1 KiB làm tròn lên. Dự toán có được xem như một write 1 KiB?

**Hướng giải:** không nếu API price unit thật làm tròn theo size; có thể cần hai units. Xác minh exact rounding per service/API và transaction semantics.

## 186. Bài tập K — Full Scan

**Đề:** query trả 100 records nhưng đọc 100.000 records theo metrics.

**Hỏi:** source cost nên theo returned count hay scanned work?

**Hướng giải:** tùy meter nhưng scanned/evaluated bytes thường quan trọng; đừng dùng 100 returned records làm workload nếu hệ đã xem xét 100.000.

## 187. Bài tập L — Hot partition

**Đề:** cluster CPU trung bình 40%, một partition đang throttled 100%. Có nên tăng global rate-limit?

**Hướng giải:** không. Cần per-partition diagnostics, key distribution, schema/query change hoặc dedicated capacity, tránh scale vô ích.

## 188. Bài tập M — Read replicas

**Đề:** chọn RF=3 thay RF=1 để đạt AZ tolerance. Có phải khoản replication là “waste” nên loại?

**Hướng giải:** không nếu HA contract bắt buộc. Cần so các phương án **cùng fault tolerance** hoặc nêu rõ risk/SLO trade-off.

## 189. Bài tập N — Managed billing included replica

**Đề:** provider báo storage price đã tính ba replicas, engineer lại nhân stored GB × RF=3.

**Hướng giải:** double counting. Cần kiểm SKU meter (logical billed bytes vs raw physical replicas) trước khi nhân.

## 190. Bài tập O — Index write amplification

**Đề:** thêm 4 indexes làm write latency và WCU tăng nhưng queries nhanh hơn.

**Hỏi:** quyết định theo tiêu chí nào?

**Hướng giải:** đo **incremental storage+write cost** so với **saved scans/read compute, p99 SLO và correctness constraints**, không chỉ số indexes.

## 191. Bài tập P — Index ROI

**Đề:** index giảm query cost từ 900 xuống 200 USD/tháng; index overhead 250 USD/tháng; build 1000 USD.

**Hướng giải:** recurring saving 450 USD/tháng; payback ≈2,22 tháng nếu assumptions giữ.

## 192. Bài tập Q — Backups và replicas

**Đề:** hệ có ba replicas, chưa có backup. Có được bỏ PITR vì đã có HA?

**Hướng giải:** không, replication có thể sao chép delete/corruption; backup/PITR và restore drills bảo vệ failure modes khác.

## 193. Bài tập R — TTL và storage

**Đề:** sessions TTL 7 ngày, nhưng backup retention 30 ngày.

**Hỏi:** có thể dự toán toàn hệ chỉ có 7 ngày dữ liệu?

**Hướng giải:** không. Backups/PITR/tombstone/log/cleanup delay và full copies có retention riêng.

## 194. Bài tập S — DR cold vs hot

**Đề:** cần RTO 5 phút; phương án chỉ lưu backup object storage và tạo cluster khi có incident.

**Hỏi:** đã chứng minh RTO chưa?

**Hướng giải:** chưa. Phải restore drill và capacity plan; có thể cần warm/hot standby để đạt mục tiêu.

## 195. Bài tập T — Cross-region network

**Đề:** 250 GB/ngày truyền cross-region, đơn giá minh họa 0,02 USD/GB, 30 ngày.

**Hướng giải:** \(250\times30\times0.02=150\) USD/tháng cho meter này, chưa gồm receiving writes/backup/compute.

## 196. Bài tập U — Network fees included

**Đề:** provider bundle replication transfer vào một price tier, spreadsheet vẫn tính riêng tất cả replica bytes.

**Hướng giải:** có thể double count. Cần ánh xạ physical flow tới billable meters hợp đồng.

## 197. Bài tập V — Egress khi exit

**Đề:** một provider giá storage thấp nhưng egress, migration rewrite và double-run cao.

**Hỏi:** chỉ so monthly storage đủ chưa?

**Hướng giải:** chưa. Thêm exit scenario/horizon và các chi phí một lần, cả engineering capacity.

## 198. Bài tập W — Nhân sự FTE

**Đề:** 0,4 SRE + 0,3 DBA + 0,1 backend FTE; loaded cost 8.000 USD/FTE/tháng.

**Hướng giải:** 0,8 FTE × 8.000 = 6.400 USD/tháng allocated labor.

## 199. Bài tập X — Managed staffing

**Đề:** chuyển sang managed, provider làm backup và OS patch. Có thể đặt ops FTE=0?

**Hướng giải:** không mặc định; còn data model, monitoring, restore verification, security, migrations, SDK retries và incident coordination.

## 200. Bài tập Y — License miễn phí

**Đề:** self-hosted Cassandra không trả license core. Có chắc TCO bằng 0 cho phần vận hành?

**Hướng giải:** không. Compute, disk, network, repair, on-call, backup, security, automation và DR vẫn có cost.

## 201. Bài tập Z — Payback

**Đề:** migration incremental investment 150.000 USD, recurring saving 4.000 USD/tháng.

**Hướng giải:** 37,5 tháng simple payback, chưa discount/growth/risk.

## 202. Bài tập AA — Cost of double-running

**Đề:** old=12k USD/tháng, new=9k, double-run 2 tháng, workers=8k, labor=30k.

**Hướng giải:** gross transition=80k USD, nhưng **incremental** so với 2 tháng chỉ giữ old=56k USD. Không cộng gross như thể không có baseline.

## 203. Bài tập AB — TCO managed

**Đề:** recurring 11.500 USD/tháng, initial 40.000, horizon 36 tháng.

**Hướng giải:** \(36\times11\,500+40\,000=454\,000\) USD.

## 204. Bài tập AC — TCO self-hosted

**Đề:** recurring 13.000 USD/tháng, initial 55.000, horizon 36.

**Hướng giải:** \(36\times13\,000+55\,000=523\,000\) USD, trong giả định này cao hơn managed ví dụ 69.000 USD.

## 205. Bài tập AD — Staffing sensitivity

**Đề:** self-hosted labor giảm 6.000→2.000 USD/tháng, mọi giả định khác như bài AC.

**Hướng giải:** \(36\times9000+55000=379\,000\) USD. Thứ hạng có thể đổi; phải kiểm realism of on-call coverage.

## 206. Bài tập AE — NPV

**Đề:** 1.000 USD chi sau 12 tháng, monthly discount rate 1% giả định.

**Hướng giải:** giá trị hiện tại:

\[
PV=1000/(1.01)^{12}\approx887.45\text{ USD}
\]

Chỉ dùng discount rate theo finance policy, không coi 1%/tháng là chuẩn.

## 207. Bài tập AF — Cost per successful order

**Đề:** DB cost 20.000 USD/tháng, 300.000 orders thành công.

**Hướng giải:** khoảng \(20\,000/300\,000=0.0667\) USD/order. Nên so trend và scope attribution cùng nhau.

## 208. Bài tập AG — Node failure reserve

**Đề:** mỗi node chịu tối đa 2.000 writes/s ở SLO; cần 6.000 writes/s khi mất một node.

**Hướng giải:** \((N-1)\times2\,000\ge6\,000\), nên tối thiểu N=4 theo mô hình đơn giản; constraints RF/partitions có thể đòi nhiều hơn.

## 209. Bài tập AH — Growth không đồng nhất

**Đề:** storage tăng 2× nhưng writes tăng 5×. Có thể nhân total bill=2×?

**Hướng giải:** không. Tách storage, compute, write request units, CDC, replication traffic, compaction, staff và tier step changes.

## 210. Bài tập AI — Storage đứng yên nhưng bill tăng

**Đề:** live data vẫn 1 TB, write workload và daily changed bytes tăng 10×.

**Hỏi:** bill nào có thể tăng?

**Hướng giải:** IOPS/WCU, WAL/commitlog, backups/PITR, CDC, replication, compute, network và monitoring, dù logical live storage không tăng.

## 211. Bài tập AJ — Cost per request class

**Đề:** 1 triệu queries scan 10 MiB mỗi query so với 1 triệu point gets 1 KiB.

**Hướng giải:** API call count bằng nhau không nghĩa cost như nhau; xem scanned bytes/index/CPU/request units.

## 212. Bài tập AK — Support plan

**Đề:** support tính theo tỷ lệ spend và có minimum annual fee; dự toán quên.

**Hướng giải:** TCO thấp giả. Cần đưa support fee theo hợp đồng và tránh cộng trùng nếu bundle.

## 213. Bài tập AL — KMS per item

**Đề:** mỗi record backfill đều gọi KMS dù dữ liệu có thể dùng envelope key caching an toàn.

**Hỏi:** tác động?

**Hướng giải:** KMS API charges/latency tăng, có thể tạo throttling. Đánh giá security design/caching/rotation, không bỏ encryption.

## 214. Bài tập AM — Chi phí tiết kiệm không đạt SLO

**Đề:** phương án A chi 6k/tháng p99=350 ms, SLO phải dưới 100 ms; B 9k/tháng p99=80 ms.

**Hướng giải:** A không hợp lệ theo sizing hiện tại; phải resize/rearchitect hoặc loại. B được xem xét tiếp nếu đáp ứng các requirements khác.

## 215. Bài tập AN — Managed hay self-managed?

**Đề:** managed đắt hơn 1.500 USD/tháng vendor bill nhưng giảm 0,5 FTE. Loaded FTE 8.000 USD/tháng.

**Hướng giải:** labor savings giả định 4.000 USD/tháng, lớn hơn premium 1.500; net 2.500 USD/tháng theo scope, trước migration/license/risk.

## 216. Bài tập AO — Đếm trùng nhân sự

**Đề:** Platform allocates 0,4 DBA FTE, product cost model cũng tính cùng 0,4 FTE cho đúng người và cùng workload.

**Hướng giải:** cần loại double allocation hoặc phân bổ tổng 0,4 FTE một lần theo agreed cost center.

## 217. Bài tập AP — Giá chưa rõ region

**Đề:** một quote không có region/SKU/as-of-date.

**Hỏi:** có nên công bố winner chính xác tới USD?

**Hướng giải:** chưa. Ghi unknown/high uncertainty, yêu cầu itemized quote và sensitivity range.

## 218. Bài tập AQ — Autoscaling bill runaway

**Đề:** SDK retry storm làm on-demand request meter tăng đột ngột.

**Hướng giải:** limit retries/concurrency, monitor failed attempts, cap background scans, điều tra root cause; không tự tắt critical writes để giảm tiền.

## 219. Bài tập AR — Tối ưu retention

**Đề:** logs chỉ cần 30 ngày theo policy nhưng giữ 2 năm, dùng nhiều object/backup storage.

**Hướng giải:** định nghĩa lifecycle/retention theo chính sách đã được phê duyệt, sau đó tính savings trên storage, indexes, backups và retrieval.

## 220. Bài tập AS — Shadow cost khi load test

**Đề:** PoC chạy 20 phút trên 1.000 documents, production dự kiến 20 TB và 50.000 QPS.

**Hướng giải:** benchmark chưa đại diện cho working set, peak, compaction, replicas và p99; không đủ sizing/cost estimate.

## 221. Bài tập AT — Risk discount

**Đề:** một phương án rẻ hơn 10% nhưng không thể đạt required RPO khi một AZ hỏng.

**Hướng giải:** phương án không hợp lệ nếu RPO bắt buộc, không tính expected loss thấp để bỏ qua constraint.

---

## 222. Checklist thu thập dữ liệu và tính TCO

**Phạm vi và ràng buộc**

1. Horizon (12/36 tháng) và currency được thống nhất chưa?
2. Có ghi region, date, pricing tier và discount không?
3. Có so các engine theo cùng API/business contract không?
4. Có liệt kê access patterns/query types không?
5. Có nêu consistency requirement per operation không?
6. Có định nghĩa RPO/RTO và availability SLO không?
7. Có yêu cầu data residency, privacy và encryption không?
8. Có phân biệt functional fail với performance fail không?
9. Có benchmark ở successful p99 under representative load không?
10. Có sizing cho một node/AZ failure không?

**Dữ liệu và physical storage**

11. Đã đo logical bytes và item size distribution chưa?
12. Có dùng GB/GiB nhất quán không?
13. Compression ratio có từ engine thật/representative dataset không?
14. Replica topology/count được ghi rõ chưa?
15. Có xác định provider billed logical vs raw storage không?
16. Có tránh nhân replica cost hai lần không?
17. Có index count, key sizes và physical index bytes không?
18. Có write amplification do indexes không?
19. Có tính log/WAL/metadata/tombstones không?
20. Có headroom cho compaction và node rebuild không?
21. Có đo fragmentation/cache/memory working set không?
22. Có phân biệt data growth và data churn không?
23. Có xác định TTL, retention và cleanup delay không?
24. Có tính backup/PITR và archived copies không?
25. Có restore drill, retrieval/rebuild cost không?
26. Có sizing storage cho DR/extra regions không?

**Thông lượng và chi phí đọc/ghi**

27. Có average/peak/burst RPS theo giờ không?
28. Có read/write query classes và billed units không?
29. Có consistency/transactional multiplier theo provider không?
30. Có count failed/conditional/retry attempts không?
31. Có đo bytes scanned vs returned không?
32. Có nhận diện full-scan/anti-pattern queries không?
33. Có đo hot partitions/tenant skew không?
34. Có sizing CPU/RAM/IOPS/storage riêng không?
35. Có node count theo max bottleneck và min RF/quorum không?
36. Có tính capacity tại failure state không?
37. Có benchmark long-soak/cache-cold/index build không?
38. Có tính GSI/materialized views/index maintenance không?
39. Có tách read-model CDC operations khỏi source operations không?
40. Có ghi read cache hit ratio và chi phí cache không?

**Network, backup và phụ trợ**

41. Có topology traffic cross-AZ/cross-region/Internet không?
42. Có map từng traffic flow sang billable meter thật không?
43. Có xác định transfer nào included trong service không?
44. Có tính CDC/broker/search destinations không?
45. Có tính export/import/backfill/egress lúc migration không?
46. Có network peak bandwidth requirement không?
47. Có compute/transfer/storage để phục hồi sau sự cố không?
48. Có observability log/metrics/traces cost không?
49. Có KMS/encryption/license/security tooling cost không?
50. Có compliance/audit/deletion operations cost không?

**People, support và migration**

51. Có DBA/SRE/on-call hours được phân bổ rõ không?
52. Có fully loaded FTE cost và tránh double counting không?
53. Có đủ skill/rotation/runbooks để đạt SLA không?
54. Có support/licensing tier và hợp đồng thật không?
55. Có effort patch/upgrade/backups/restore drills không?
56. Có training/hiring và documentation maintenance không?
57. Có migration PoC/backfill/dual-run/verification không?
58. Có chi phí exit/rewrite/cross-cloud egress không?
59. Có phân biệt sunk cost với future incremental cost không?
60. Có tách one-time investment khỏi recurring cost không?

**Decision modeling**

61. Có base/high-growth/write-heavy/disaster scenarios không?
62. Có sensitivity trên top uncertain inputs không?
63. Có fixed vs variable/tier-step cost curves không?
64. Có reserved/on-demand commitments và overages không?
65. Có unit economics cost per successful business action không?
66. Có tính cost under peak SLO thay vì average-only không?
67. Có so monthly run-rate và 36-month TCO không?
68. Có xem payback/NPV theo finance policy khi cần không?
69. Có ghi uncertainty/unknown và nguồn số liệu không?
70. Có dự kiến review lại khi workload/price thay đổi không?
71. Có budget alerts và cost anomaly drilldown không?
72. Có phân biệt bill actual với estimate/reallocation không?
73. Có guardrail không hy sinh correctness/SLO để giảm cost không?
74. Có ADR nêu accepted trade-offs/owners không?
75. Có rollback/exit contingency và trách nhiệm hỗ trợ không?
76. Có kiểm vendor quote theo region/SKU/as-of-date không?
77. Có đo production query/index behavior sau cutover không?
78. Có kế hoạch xử lý cost spike do retry/scan bugs không?
79. Có phân biệt direct cash cost với allocated labor/risk không?
80. Có so phương án chỉ sau khi các ràng buộc kỹ thuật đều đạt không?

Danh sách trên nhằm tạo **hợp đồng đánh giá TCO**. Không phải mọi khoản đều phát sinh cho mọi NoSQL, và một khoản có thể đã được bundle. Người thực hiện phải đánh dấu **included/excluded/unknown** cho từng hạng mục trước khi cộng.

## 223. Một mẫu dữ liệu TCO dùng lại

~~~yaml
decision:
  project: ExampleNoSqlPlatform
  owner: DataPlatform
  horizonMonths: 36
  currency: USD
  priceAsOf: explicitQuoteDate
  regions:
    primary: RegionA
    dr: RegionB
  priceSource: providerQuoteOrActualContract
  status: draftUntilEvidenceComplete

requirements:
  dataModel: documentAndKeyValue
  authoritativeWrites: conditionalPerAggregate
  p99ReadMs: defined
  p99WriteMs: defined
  availabilitySlo: defined
  rpo: defined
  rto: defined
  compliance: documented

workload:
  logicalDataGiB: measured
  averageItemSizeKiB: measured
  itemSizeP95KiB: measured
  dataGrowthByYear: forecasted
  dailyChurnGiB: measured
  readOperationsByClass: observed
  writeOperationsByClass: observed
  peakReadOpsPerSecond: observed
  peakWriteOpsPerSecond: observed
  hotPartitionSkew: observed
  retriesByOutcome: measured
  averageQueryScannedBytes: measured
  cacheHitRate: measured

storageSizing:
  compressionFactor: benchmarked
  replicaTopology: explicitlySpecified
  replicaCostIncludedInProviderStoragePrice: verify
  indexGiBByIndex: benchmarked
  metadataAndLogGiB: measuredOrAssumed
  compactionHeadroomPercent: defined
  backupRetentionDays: specified
  pitrRetentionDays: specified
  archiveGiBMonth: estimated
  drCapacityGiB: estimated

computeSizing:
  normalStateNodes: benchmarked
  failureStateNodes: benchmarked
  safeCpuUtilization: specified
  safeMemoryUtilization: specified
  safeStorageUtilization: specified
  p99SloUnderPeak: required
  concurrencyLimits: recorded
  provisionedOrOnDemand: selected

network:
  appToDatabaseGiBMonth: estimated
  replicaCrossAzGiBMonth: meteredIfBilled
  replicaCrossRegionGiBMonth: estimated
  cdcTransferGiBMonth: estimated
  internetEgressGiBMonth: estimated
  backupTransferGiBMonth: estimated
  sourceExportGiB: oneTimeIfMigration
  pricingBoundaryPerFlow: documented

operations:
  sreFte: allocated
  dbaFte: allocated
  backendTuningFte: allocated
  fullyLoadedMonthlyCostPerFte: internalPolicy
  supportContract: quoted
  upgradeAndPatchHoursPerYear: planned
  restoreDrillsPerYear: planned
  monitoringAndSecurityToolCosts: estimated
  trainingAndHiring: oneTimeIfNeeded

oneTime:
  proofOfConceptCost: estimated
  migrationEngineeringCost: estimated
  temporaryDoubleRunningMonths: planned
  backfillComputeAndRequestCost: estimated
  reconciliationCost: estimated
  exitAndRollbackCost: scenarioBased

pricing:
  storageUnitRate: quoted
  computeUnitRate: quoted
  readUnitRateByClass: quoted
  writeUnitRateByClass: quoted
  backupAndPitrRates: quoted
  transferRatesByBoundary: quoted
  licenseAndSupport: quoted
  discountsCreditsCommitments: documented

scenarios:
  - name: base
    dataGrowthMultiplier: 1
    readGrowthMultiplier: 1
    writeGrowthMultiplier: 1
  - name: growth
    dataGrowthMultiplier: 2
    readGrowthMultiplier: 3
    writeGrowthMultiplier: 4
  - name: disaster
    primaryRegionUnavailable: true
    backupRestoreOrDrFailover: true

outputs:
  monthlyVendorBillByMeter: calculate
  monthlyAllocatedPeopleCost: calculate
  cashFlowByMonth: calculate
  totalCost36Months: calculate
  costPerSuccessfulBusinessOperation: calculate
  paybackMonthsIfMigrating: calculate
  sensitivityAndUncertainty: calculate
  businessAndTechnicalRisks: separatelyPresented

decisionGate:
  requiredCorrectness: pass
  requiredSlo: pass
  requiredRpoRto: pass
  requiredSecurityAndCompliance: pass
  candidateWithinBudget: evaluate
  exitPlan: documented
  evidenceOwner: assigned
~~~

Đây là **YAML hợp đồng đầu vào và quyết định**; chưa phải schema cấu hình tự chạy của một cloud calculator, DynamoDB, MongoDB, Cassandra hoặc Redis. Các giá trị `measured`, `quoted`, `estimated` là placeholders **cần được thay bằng dữ liệu thực** trước khi tính. Nhờ vậy, không ai có thể nhầm một bảng thiếu số liệu với dự toán đã được phê duyệt.

## 224. Runbook khi bill NoSQL tăng bất thường

~~~text
TRIGGER
  Monthly forecast, daily spend or usage rate exceeds guardrail.

VERIFY DATA
  1. Check invoice/billing data latency and correction status.
  2. Identify SKU, region, account, project and environment.
  3. Compare observed usage with prior baseline.

CORRELATE
  4. Inspect deploys, traffic seasonality and retries.
  5. Inspect new indexes/GSI, full scans and query plans.
  6. Inspect item size, data growth, TTL and backup retention.
  7. Inspect replication/CDC/cross-region transfer.
  8. Inspect autoscaling, instance tiers and commitments.
  9. Inspect logging, KMS and secondary read models.

CONTAIN
 10. Throttle noncritical backfills and runaway scans.
 11. Limit retries/queues according to safe policy.
 12. Correct query/filter/index regression.
 13. Restore intended retention or capacity configuration.
 14. Preserve production correctness/SLO/RPO/RTO.

VALIDATE
 15. Compare usage meters and bill rate after mitigation.
 16. Confirm no data loss, stale reads or critical errors.
 17. Update forecast, alerts, cost attribution and ADR.
~~~

Không giải quyết cost spike bằng cách tắt encryption, xóa backups bắt buộc, giảm RF dưới fault-tolerance requirement hoặc dừng authoritative database một cách bất ngờ.

## 225. Kết luận

**Tổng chi phí NoSQL** không phải một phép nhân “số GB × giá GB”. Một hệ đáng mua và vận hành cần đạt **hợp đồng đúng dữ liệu, hiệu năng, khả năng phục hồi và bảo mật**, rồi mới so đầy đủ chi phí trên horizon thích hợp.

Những nguyên tắc cốt lõi:

- **Storage logic khác physical storage**; tính nén, bản sao, index, metadata, compaction và phần trống an toàn.
- **Replication và backup giải các bài toán khác nhau**; RF không thay PITR/restore drills.
- **Index tiết kiệm reads nhưng tăng storage/writes**; đánh giá cost cả hai chiều theo query mix.
- **Read/write pricing phụ thuộc API/consistency/item size**; không thể chỉ đếm số SDK calls.
- **Average RPS dùng cho usage, peak RPS dùng cho capacity**; cần cả hai để đạt SLO và dự báo bill.
- **Network/CDC/read models/DR** có thể nhân data movement ngoài dataset gốc.
- **Managed không có nghĩa zero operations** và **open source không có nghĩa zero labor**.
- **Migration/double-run/exit cost** có thể quyết định payback nhiều năm.
- **Độ nhạy nhân lực, growth và tier step changes** có thể đảo thứ hạng của các phương án.
- **TCO phải gắn với evidence**: benchmark, measured usage, provider quote, internal staffing estimate và assumptions có ngày/region rõ.
- **Đừng giảm chi phí bằng cách bỏ invariant bắt buộc**; correctness, security, SLO và RPO/RTO là cổng kiểm tra trước.

> **Hệ NoSQL kinh tế nhất không nhất thiết có đơn giá thấp nhất. Đó là hệ đáp ứng đúng yêu cầu với tổng chi phí vận hành và rủi ro được hiểu rõ, đo được và kiểm soát được theo thời gian.**

Khi đứng trước một lựa chọn MongoDB, DynamoDB, Cassandra, Redis hoặc hệ NoSQL khác, hãy hỏi: **dữ liệu thật sự chiếm bao nhiêu sau khi nhân bản và lập chỉ mục; mỗi business action tạo bao nhiêu work; traffic đi qua những biên tính phí nào; ai phải trực và phục hồi khi sự cố; và nếu tải tăng gấp ba hoặc phải đổi nền tảng, phương án nào vẫn hợp lý?** Trả lời các câu hỏi ấy bằng số liệu và một hợp đồng kỹ thuật rõ ràng mới là cơ sở của quyết định TCO đáng tin cậy.
