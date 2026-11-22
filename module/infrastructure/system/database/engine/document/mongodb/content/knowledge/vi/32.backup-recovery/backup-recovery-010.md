# Diễn tập phục hồi và xác minh dữ liệu, ứng dụng sau khôi phục trong MongoDB

Một bản sao lưu MongoDB có trạng thái **SUCCESS** chưa chứng minh rằng hệ thống có thể khôi phục sau sự cố. File backup có thể thiếu, khóa giải mã không dùng được, oplog không đủ lịch sử, chỉ mục chưa sẵn sàng hoặc ứng dụng không kết nối được đến cluster mới. Ngay cả khi một lệnh restore trả mã thoát 0, dữ liệu vẫn có thể chưa đáp ứng ràng buộc nghiệp vụ.

**Diễn tập phục hồi (restore drill/disaster recovery exercise)** là hoạt động lựa chọn một kịch bản sự cố, phục hồi dữ liệu từ backup vào môi trường được kiểm soát, kiểm tra tính đúng đắn của dữ liệu và chứng minh ứng dụng hoạt động theo mức dịch vụ đã cam kết. Đích đến không chỉ là một MongoDB server chạy được, mà là **dịch vụ nghiệp vụ dùng được với RPO/RTO đã định**.

Bài học thuộc chương **Sao lưu và phục hồi**, module **Database Engine Document MongoDB**, tập trung vào:

1. Định nghĩa RPO, RTO, recovery point, mức hoàn tất của bài diễn tập.
2. Chuẩn bị backup manifest, dữ liệu baseline, target cô lập và danh sách phụ thuộc.
3. Phục hồi qua công cụ phù hợp: snapshots, PITR, logical dump/restore, Atlas và những topology replica set/sharded cluster.
4. Xác minh collections, documents, hashes, indexes, validators, security, GridFS/object storage và consistency.
5. Thực thi smoke tests, API/integration tests, business workflows, kiểm tra cache, queues và external side effects.
6. Đo RPO/RTO thực tế, quyết định Go/No-Go, rollback, evidence và cải tiến runbook.

**An toàn:** Toàn bộ lệnh ghi hoặc khôi phục trong bài chỉ dành cho **target diễn tập cô lập được phép**. Không dùng tùy chọn phá hủy dữ liệu hoặc đổi DNS/connection string của production nếu chưa có một kế hoạch cutover độc lập được phê duyệt. Không thực hiện gửi email, thu tiền hoặc gọi webhook thật khi thử ứng dụng sau restore.

## 1. Phân biệt bốn loại thành công

| Cấp độ | Điều được chứng minh | Bằng chứng |
| --- | --- | --- |
| Backup available | Có backup truy xuất được | Backup ID, manifest, object/snapshot |
| Restore complete | Backup được đưa vào target | Restore job finished |
| Data valid | Nội dung đúng và nhất quán | Counts, sample hashes, invariants, indexes |
| Application usable | Nghiệp vụ quan trọng hoạt động | Login, read/write, API và end-to-end tests |

Một báo cáo chỉ ghi “mongorestore completed” mới đạt mức kỹ thuật thứ hai; nó không tự chứng minh ứng dụng có thể nhận booking mới, truy cập hợp đồng hay xử lý trạng thái thanh toán đúng.

### 1.1. Định nghĩa mức dịch vụ

Có thể phân loại:

- **Database reachable:** kết nối/ping thành công.
- **Database readable:** đọc các collections thiết yếu được.
- **Database writable:** ghi với write concern yêu cầu được.
- **Core business usable:** các luồng nghiệp vụ trọng yếu pass.
- **Full service restored:** cả search, files, queues, background jobs và integrations cần thiết hoạt động.

Nên chọn rõ mức nào được tính là **điểm hoàn thành RTO** trước khi diễn tập.

### 1.2. Success không đồng nghĩa không có lỗi

Một buổi diễn tập có thể kết thúc với dữ liệu đúng nhưng phát hiện search index rebuild quá lâu. Có thể ghi **PASS_WITH_ACTIONS** nếu tiêu chí bắt buộc đạt; không ghi PASS nếu các tiêu chí cần thiết thất bại.

## 2. RPO — mất dữ liệu được chấp nhận

**RPO (Recovery Point Objective)** biểu thị lượng dữ liệu tối đa tổ chức chấp nhận mất khi phải phục hồi.

Ví dụ:

~~~text
10:00  Recovery point còn khả dụng
10:03  Thêm writes hợp lệ
10:05  Sự cố bắt đầu
10:18  Restore bắt đầu
10:42  Database phục hồi
10:51  Ứng dụng dùng được
~~~

Nếu điểm mới nhất thực sự phục hồi được là 10:02, thì ở ví dụ này:

\[
RPO_{\text{observed}} = 10{:}05 - 10{:}02 = 3\ \text{phút}
\]

Đây là phép minh họa. Recovery point phải dựa trên trạng thái dữ liệu/logs có thể phục hồi, không chỉ thời điểm upload file backup.

### 2.1. Backup timestamp chưa chắc là recovery point

Một snapshot được tạo lúc T1 nhưng job kết thúc T2 không có nghĩa bản phục hồi chứa toàn bộ writes tới T2.

### 2.2. PITR thay đổi khả năng RPO

Với point-in-time recovery (PITR), có thể chọn mốc sau snapshot ban đầu nếu có logs/backup chain liên tục và được platform hỗ trợ. Điều đó phải được **thử bằng restore thực tế**, không chỉ đọc retention policy.

### 2.3. Replica set không phải backup chống xóa nhầm

Một lệnh drop collection hoặc update sai có thể replicate sang các secondary. Replication phục vụ availability, không cung cấp khả năng quay về mọi điểm trong quá khứ.

### 2.4. Clock và time zone

Ghi recovery points bằng UTC ISO-8601, ví dụ:

~~~text
2026-11-14T02:15:00Z
~~~

Không chỉ ghi “9 giờ sáng” vì có thể nhầm timezone, clock drift hoặc thời điểm sự kiện thực sự commit.

## 3. RTO — khi nào ứng dụng thật sự hoạt động?

**RTO (Recovery Time Objective)** là thời gian tối đa để khôi phục dịch vụ tới mức đã định.

Từ ví dụ trên, nếu sự cố bắt đầu 10:05 và các core business workflows pass lúc 10:51:

\[
RTO_{\text{observed}} = 46\ \text{phút}
\]

Không báo RTO là 24 phút chỉ vì database restore xong lúc 10:42 và job restore đã chạy 24 phút.

### 3.1. Ghi các mốc riêng

~~~text
incident_start
incident_detected
restore_authorized
target_ready
restore_started
restore_completed
db_readable
db_writable
app_started
core_smoke_passed
full_service_ready
~~~

### 3.2. RTO từ thời điểm nào?

SLA phải nói rõ bắt đầu khi sự cố xảy ra, khi phát hiện hay khi tuyên bố incident; mỗi định nghĩa cho kết quả khác nhau. **Không đổi định nghĩa sau khi xem kết quả**.

### 3.3. Thành phần thời gian

RTO end-to-end bao gồm phát hiện/phê duyệt, provision target, lấy backup, restore, index readiness, cấu hình app, các kiểm thử bắt buộc và routing/cutover nếu có.

## 4. Những kịch bản diễn tập cần ưu tiên

| Kịch bản | Khả năng hỏng | Loại kiểm tra |
| --- | --- | --- |
| Drop collection nhầm | Namespace bị xóa | Restore subset/PITR |
| Update nhiều records sai | Data corruption logic | Chọn điểm trước bad write |
| Primary node mất | Failover | Replica election/read-write availability |
| Mất cả replica set | Toàn cluster không khả dụng | Full restore + app |
| Mất một region | Hạ tầng vùng | DR region/readiness |
| Sharded data hỏng | Nhiều shards/config | Backup topology consistency |
| Backup file bị lỗi | Artifact hỏng | Checksum/restore fail |
| Thiếu decryption key | Không giải mã được | KMS/IAM |
| Search index chưa ready | Derived index | Search readiness |
| Object ref mất | File ngoài DB hỏng | Object HEAD/GET |
| App workers replay event | Duplicate side effects | Queue/outbox reconciliation |

Một bài “tạo cluster mới rồi ping thành công” không thể đại diện cho mọi tình huống. Nên luân phiên các kịch bản trong kế hoạch DR.

## 5. Phạm vi bài diễn tập

Trước khi bắt đầu cần ghi:

- Sự cố giả định và service bị ảnh hưởng.
- Phạm vi dữ liệu: một collection, database hay toàn cluster.
- Loại backup thực sự đang dùng.
- Recovery point mong muốn và khả năng PITR.
- RPO/RTO mục tiêu.
- Target cluster, vùng mạng và mức cô lập.
- Những API/workflows phải pass.
- Những hệ thống ngoài MongoDB cần giả lập hoặc đồng bộ.
- Người phê duyệt, người thực hiện và người xác nhận.
- Ngưỡng dừng và rollback plan.

### 5.1. Ví dụ scope

~~~yaml
drillId: "DR-2026-11-14-01"
scenario: "full-cluster-loss"
source: "production"
target: "isolated-dr-cluster"
recoveryMethod: "supported-snapshot-plus-pitr"
recoveryPointUtc: "2026-11-14T02:00:00Z"
targets:
  rpoMinutes: 15
  rtoMinutes: 90
applicationMode: "isolated-staging"
externalPayments: "sandbox"
emailDelivery: "disabled"
decision: "PENDING"
~~~

Mọi giá trị là ví dụ, không phải một hệ thống đã được diễn tập thật.

### 5.2. Định nghĩa stop conditions

Dừng nếu URI chỉ tới production, target thiếu bảo vệ dữ liệu nhạy cảm, backup source không rõ, KMS key không truy cập được hoặc ứng dụng staging có khả năng phát sinh giao dịch thật.

### 5.3. Owner và trách nhiệm

| Vai trò | Trách nhiệm |
| --- | --- |
| Drill lead | Điều phối, stop/go, timeline |
| DBA/MongoDB operator | Restore, topology, index/data checks |
| SRE/Platform | Hạ tầng, network, storage, observability |
| Application owner | API, business invariants, readiness |
| Security | Secrets, IAM, dữ liệu nhạy cảm |
| QA/Business representative | Xác nhận workflows quan trọng |
| Scribe/Observer | Ghi logs, timestamps, artifacts |

Tách người thực hiện và người xác nhận khi có thể.

## 6. Sơ đồ phụ thuộc ứng dụng

~~~text
Client
  |
  v
API gateway
  |
  +--> Application services
  |       |
  |       +--> MongoDB cluster
  |       +--> Object storage / GridFS
  |       +--> Redis/cache
  |       +--> Queue / outbox consumers
  |       +--> Search / vector search
  |       +--> Payment / notifications
  |
  +--> Authentication / identity provider
  |
  +--> Observability
~~~

**MongoDB phục hồi chưa có nghĩa toàn bộ sơ đồ trên đã hoạt động.**

### 6.1. Dữ liệu nguồn so với dữ liệu tái tạo được

- Orders/booking/payment ledger: thường là dữ liệu nghiệp vụ quan trọng.
- Redis cache: thường có thể rebuild nhưng cần tránh stale state.
- Search/vector indexes: có thể cần sync/build từ dữ liệu nguồn, ảnh hưởng RTO.
- Object storage attachments: bytes nằm ngoài MongoDB nếu chỉ lưu reference.
- External payment: sự thật của hệ thống khác, không rollback theo MongoDB.

### 6.2. Dependency matrix

| Thành phần | Yêu cầu xác minh |
| --- | --- |
| Collections | Có đủ documents trong scope |
| Indexes | Correct definitions và readiness |
| Users/roles | Application credentials hoạt động |
| TLS/network | Hostnames, CA, allowlists đúng |
| GridFS | Files và chunks khớp |
| Object storage | Referenced versions tải được |
| Search/vector search | Required queries trả kết quả |
| Queues/CDC | Không bỏ sót hoặc duplicate ngoài kiểm soát |
| Payment/email | Sandbox/reconciliation |
| Monitoring | Logs/alerts đang ghi nhận |

## 7. Chuẩn bị dữ liệu baseline trước diễn tập

Muốn xác minh restore cần biết trước điều gì sẽ được coi là đúng.

Một manifest có thể gồm:

~~~yaml
backupId: "snapshot-example"
sourceCluster: "mongo-primary"
sourceTimeUtc: "2026-11-14T02:00:00Z"
databases:
  - rental
baseline:
  ordersCount: 125000
  usersCount: 33000
  ordersByStatus:
    confirmed: 64000
    cancelled: 12000
samples:
  - "order-test-001"
  - "order-test-002"
requiredIndexes:
  - "orders_tenant_createdAt"
  - "users_tenant_email_unique"
checksumArtifact: "data-hashes.json"
~~~

Đây là manifest minh họa. Số liệu baseline thực cần được tạo và lưu theo recovery point tin cậy.

### 7.1. Baseline phải cùng mốc thời gian

Count ở ngày T2 không nhất thiết bằng count khi restore về T1. Nếu không có mốc so sánh chính xác, báo cáo phải nêu giới hạn của phép so.

### 7.2. Tập sample cố định

Nên có documents:

- Nhiều tenants.
- Nested arrays và embedded objects.
- Decimal128/Date/ObjectId/Binary.
- Record lớn nhưng hợp lệ.
- Giao dịch nhiều collections.
- Tệp GridFS nhiều chunks.
- Dữ liệu tiếng Việt có dấu.
- Một record tạo trước recovery point.
- Một record tạo sau recovery point.
- Các trạng thái nghiệp vụ khác nhau.

### 7.3. Không chỉ dùng random sample

Sampling giúp phát hiện lỗi nhưng chưa chứng minh toàn corpus. Kết hợp counts, hashes, index inventory và business invariants.

## 8. Target phục hồi cô lập

Ưu tiên **restore sang cluster riêng** có tên, ID và vùng mạng xác định rõ. Không ghi đè cluster đang phục vụ.

Checklist:

1. Verify cluster identity/URI target.
2. Xác định target không phải production.
3. Đủ disk cho dữ liệu, indexes, logs và headroom.
4. MongoDB version/FCV và tool versions tương thích.
5. Network, DNS, firewall và TLS phù hợp.
6. Authentication/authorization kiểm soát chặt.
7. Encryption keys/KMS accessible.
8. Dữ liệu thật có chính sách privacy/retention.
9. External notification/payment/queue endpoints là sandbox.
10. Có owner cleanup, expiration và revoke credentials sau drill.

### 8.1. Không đặt passwords trong shell history

Dùng secret manager hoặc biến môi trường có phạm vi an toàn. Không ghi URI chứa mật khẩu vào Markdown/report/screenshot.

### 8.2. Môi trường tương đương production ở mức nào?

Nếu target thiếu shards, search nodes, loại index hoặc nhỏ hơn rất nhiều, kết quả latency/RTO có thể không đại diện. Ghi rõ khác biệt thay vì tự coi kết quả là bằng chứng toàn diện.

## 9. Kiểm kê backup và khả năng truy xuất

Trước restore, xác minh:

- Backup ID và thời gian chụp.
- Phạm vi databases/collections.
- Full/incremental/snapshot/PITR.
- Recovery window và log chain.
- Artifacts, checksum, size.
- Backup storage/retention.
- Encryption/decryption key.
- Service account permissions.
- MongoDB tools versions.
- Topology được backup.

### 9.1. Backup job success không đủ

Có thể thiếu key, storage policy chặn GET, backup archive bị hỏng hoặc một segment log đã hết retention. Phải thử phục hồi định kỳ.

### 9.2. Log chain cho PITR

Nếu cần điểm phục hồi giữa hai snapshots, các logs cần thiết phải liên tục và phù hợp topology. Không chọn timestamp bên ngoài recovery window rồi kỳ vọng công cụ có thể tự tạo dữ liệu.

## 10. Chọn điểm khôi phục

Với lỗi logic lúc T_bad:

~~~text
T0 ------- T_good ---- T_bad ---- T_now
              |
              v
      Preferred restore point
~~~

Cần xem tình huống:

- Restore về trước bad write có thể loại bỏ các good writes sau đó.
- Restore toàn cluster có thể khiến payment/outbox states lệch hệ thống ngoài.
- Restore một collection riêng có thể làm dữ liệu liên quan ở collection khác không đồng bộ.

### 10.1. Điểm phục hồi cần nhất quán

Không đặt timestamp tùy ý nếu backup method không hỗ trợ. Với transactions nhiều collections, lựa chọn recovery point và backup consistency quyết định trạng thái commit có đúng không.

### 10.2. Nguy cơ mất good writes

Giả sử lúc 10:05 có một batch update sai, nhưng lúc 10:05:30 có đơn hàng hợp lệ. PITR về 10:04 giúp bỏ batch sai nhưng cũng mất đơn hàng mới. Cần kế hoạch replay/reconcile những writes hợp lệ từ application logs hoặc external ledger nếu phù hợp.

## 11. Các phương pháp restore

| Cơ chế | Đặc điểm | Điều cần lưu ý |
| --- | --- | --- |
| Atlas snapshot restore | Hạ tầng quản lý backup/restore | Availability theo tier/config |
| Atlas PITR | Chọn mốc trong recovery window | Retention, service capability |
| Ops Manager/Cloud Manager workflow | Theo công cụ quản trị | Compatibility và config |
| mongodump/mongorestore | Logical dump/restore | Namespace, consistency, index support |
| Storage snapshots | Tầng disk/filesystem | Snapshot consistency/topology |
| Oplog-aware backup | Dùng lịch sử writes của replica set | Window và tool constraints |

### 11.1. Không trộn phương pháp như thể giống nhau

Logical dump không tự tương đương snapshot nhất quán của cả sharded cluster. Một storage snapshot từng node không mặc định nhất quán trên toàn cluster nếu không có protocol phối hợp.

### 11.2. MongoDB Atlas

Nếu dùng Atlas, ưu tiên cơ chế restore được dịch vụ hỗ trợ. Kiểm tra backup policy, retention, target cluster choice, version/region constraints và trạng thái Search/Vector indexes sau restore.

### 11.3. Database Tools

MongoDB Database Tools có version riêng. Kiểm tra compatibility matrix và phạm vi hỗ trợ thay vì chỉ dựa vào version mongod.

## 12. mongodump/mongorestore minh họa

Tạo bản logical dump trong môi trường đã được phép:

~~~bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --archive="backup.archive.gz" \
  --gzip
~~~

Restore vào target cô lập:

~~~bash
mongorestore \
  --uri="$ISOLATED_RESTORE_URI" \
  --archive="backup.archive.gz" \
  --gzip
~~~

### 12.1. Lệnh mang tính minh họa

Các biến SOURCE_MONGODB_URI/ISOLATED_RESTORE_URI phải được cấp từ secrets/config an toàn. Không dùng trực tiếp với production nếu chưa xác định scope và permissions.

### 12.2. --drop là tùy chọn nguy hiểm

mongorestore có khả năng drop collections đích khi chọn tùy chọn tương ứng. **Không thêm --drop để “sửa lỗi” ngoài target cô lập đã xác nhận có thể xóa**.

### 12.3. Logical restore không phải PITR liên tục

Hai lệnh trên không cho phép chọn bất kỳ timestamp PITR nào. Cần phương án backup/log chain khác theo khả năng triển khai.

### 12.4. Restore scope

Nếu chỉ khôi phục một database hoặc namespace, cần xác định tương quan với collections khác để không phá business invariants.

## 13. Oplog-aware logical backup

Trong một số tình huống replica set, Database Tools hỗ trợ chế độ liên quan oplog cho full dump.

~~~bash
mongodump \
  --uri="$SOURCE_REPLICA_SET_URI" \
  --archive="rs.archive.gz" \
  --gzip \
  --oplog
~~~

Ví dụ restore theo cách được hỗ trợ:

~~~bash
mongorestore \
  --uri="$ISOLATED_RESTORE_URI" \
  --archive="rs.archive.gz" \
  --gzip \
  --oplogReplay
~~~

### 13.1. Có ràng buộc nghiêm ngặt

Các options liên quan oplog có giới hạn về phạm vi dump, namespace filters, topology và phiên bản. Không mặc định các lệnh hoạt động hoặc tạo consistency đúng khi chạy trên sharded cluster hay dump một vài collection.

### 13.2. Oplog window

Nếu backup mất quá lâu và lịch sử oplog cần thiết bị ghi đè, snapshot logic có thể không đạt yêu cầu. Diễn tập phải ghi nhận giới hạn này.

### 13.3. Chọn công cụ phù hợp workload

Với hệ thống lớn và yêu cầu DR nghiêm ngặt, dùng backup service/snapshot được hỗ trợ cho topology thay vì tự ghép các dumps.

## 14. Diễn tập Atlas snapshot/PITR

Luồng thực thi ở mức khái niệm:

1. Chọn project/cluster đúng.
2. Chọn backup snapshot hoặc PITR timepoint được hỗ trợ.
3. Tạo restore job sang **new isolated target**.
4. Kiểm tra target region, network và security.
5. Chờ job hoàn thành, lưu job ID/logs.
6. Kiểm tra topology và connectivity.
7. Xác minh documents, indexes, metadata.
8. Deploy application staging tới target.
9. Chạy smoke tests, đo RPO/RTO.
10. Cleanup target và quyền tạm.

### 14.1. Availability tùy tier/phiên bản

Không giả định mọi Atlas deployment đều có PITR, cross-region restore hay tự động dựng tất cả Search indexes giống nhau.

### 14.2. Search index readiness

Sau restore, khi ứng dụng dùng Atlas Search/Vector Search, cần xem definitions, trạng thái indexing và chạy query mẫu. BSON restore complete không đồng nghĩa search ready.

### 14.3. KMS

Nếu backup encryption phụ thuộc customer-managed key, quyền decrypt là một phần bắt buộc của diễn tập.

## 15. Replica set sau restore

Kiểm tra:

- Replica set name và member list.
- Primary/secondary health.
- Readable/writable state.
- Replication lag.
- Write concern/read concern.
- TLS/auth.
- Application driver URI đúng target.

Ví dụ trên target:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Với quyền thích hợp:

~~~javascript
rs.status();
~~~

### 15.1. Không reconfig bằng force theo cảm tính

Thay replica set config có thể gây mất dữ liệu/gián đoạn khi sai. Dùng runbook theo topology thực.

### 15.2. Test quyền ứng dụng

Một admin có thể đọc/ghi được nhưng service account lại thiếu permissions. Smoke test phải chạy với role gần production.

### 15.3. Thử majority writes

Nếu application yêu cầu majority write concern, đừng chỉ kiểm tra một write w:1 trên single-node target rồi kết luận tương đương.

## 16. Sharded cluster sau restore

Một sharded cluster gồm:

~~~text
Applications
      |
      v
mongos
      |
      +--> config servers
      |
      +--> shard A
      +--> shard B
      +--> shard C
~~~

Cần xác minh:

- Shard data và config metadata nhất quán.
- mongos routing hoạt động.
- Shard keys/indexes đúng.
- Transaction queries xuyên shards.
- Namespace/database placement.
- Balancer/chunk migration state theo workflow.
- Query performance và shard targeting.

### 16.1. Không ghép dumps theo thời điểm khác nhau

Nếu shard A, B và config servers không cùng một recovery state, documents có thể bị thiếu/trùng hoặc routing sai.

### 16.2. Query qua mongos

Một shard riêng đọc được chưa chứng minh cluster hoạt động. Chạy ứng dụng qua mongos endpoints, và dùng explain khi cần để kiểm tra targeting.

### 16.3. Phục hồi toàn cluster theo công cụ hỗ trợ

Dùng phương án backup/restore thực sự hỗ trợ sharded topology; không tự phát minh một cơ chế restore từng shard rồi mong nhất quán.

## 17. Bắt đầu validation sau khi restore job hoàn tất

Các lớp xác minh theo thứ tự tăng dần:

~~~text
Tool completed
      |
      v
Server/topology healthy
      |
      v
Collections and options present
      |
      v
Data counts/hash/invariants
      |
      v
Indexes and permissions ready
      |
      v
External references valid
      |
      v
Application smoke and workflows
      |
      v
Measured RPO/RTO
~~~

Ghi kết quả mỗi lớp. Nếu bước trước thất bại, dừng hoặc đánh dấu blocking issue theo exit criteria.

## 18. Kiểm tra kết nối và inventory

Trên target:

~~~javascript
db.adminCommand({ ping: 1 });
~~~

Xem collections của database đúng:

~~~javascript
use rental

db.getCollectionNames();
~~~

Đếm documents:

~~~javascript
db.orders.countDocuments({});
~~~

### 18.1. Ping không phải data integrity test

Ping thành công chỉ chứng minh kết nối và server responsiveness; không chứng minh dữ liệu đúng, quyền ứng dụng đúng hay indexes hoàn chỉnh.

### 18.2. So collection inventory

Cần kiểm tra database/collection names, views, validators và các options như capped/time-series/clustered khi áp dụng.

### 18.3. Counts theo recovery point

Baseline counts phải thuộc cùng thời điểm hoặc có phương pháp giải thích chênh lệch.

### 18.4. countDocuments so với estimatedDocumentCount

Nếu cần đối chiếu chính xác, dùng countDocuments với semantics phù hợp; estimatedDocumentCount có thể ước lượng từ metadata và không phải bằng chứng toàn vẹn đầy đủ.

## 19. Counts phân nhóm để tránh false pass

Tổng số orders bằng nhau chưa chứng minh dữ liệu đúng. Một tenant có thể mất 100 orders trong khi tenant khác thừa 100 orders.

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      count: { $sum: 1 }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.status": 1
    }
  }
]);
~~~

### 19.1. Nhóm theo business dimensions

So counts theo tenant, trạng thái, ngày/tuần, khu vực hoặc shard key. Chọn những nhóm dễ phát hiện thiếu dữ liệu cục bộ.

### 19.2. Kiểm tra sample IDs

~~~javascript
db.orders.find({
  _id: {
    $in: [
      "order-test-001",
      "order-test-002"
    ]
  }
});
~~~

Các IDs chỉ minh họa, nên lấy từ manifest được xác nhận.

### 19.3. Không chỉ đếm

Hai documents có thể giữ nguyên số lượng nhưng giá trị amount/status bị đổi; cần hashes và business invariants.

## 20. Checksums và canonical data comparison

Checksum file backup phục vụ **artifact integrity**, còn checks trên documents phục vụ **data correctness**. Không đồng nhất hai việc.

### 20.1. Artifact checksum

Nếu backup là archive/files, so SHA-256 với giá trị expected trong manifest đáng tin để phát hiện artifact bị thay đổi hoặc thiếu.

### 20.2. Document hashes

Có thể so hash của một biểu diễn chuẩn cho tập record.

Cần chuẩn hóa:

- Thứ tự records.
- Thứ tự fields khi cần.
- BSON types: Date, Decimal128, Binary, ObjectId.
- Serialization/escaping.
- Những fields không nên so nếu chúng thay đổi hợp lệ.

### 20.3. Không coi JSON.stringify tùy tiện là canonical format

Serialization của BSON numeric/date types có thể khác. Chọn canonical Extended JSON hoặc một phép canonicalization được đặc tả trong pipeline đối chiếu.

### 20.4. Bảo vệ PII

Bằng chứng nên ưu tiên counts/hashes/masked IDs thay vì xuất raw customer data sang logs/biên bản không bảo vệ.

## 21. Business invariants quan trọng hơn raw counts

Ví dụ trong hệ thống đặt/cho thuê:

- Mỗi booking liên kết customer hợp lệ.
- Mỗi booking liên kết vehicle/resource hợp lệ.
- Không có hai active reservations xung đột ngoài policy.
- Confirmed booking có reservation record.
- Payment state phù hợp external ledger.
- Inventory allocations không vượt capacity.
- Counter/sequence không thấp hơn giá trị đã cấp.
- Tenant ownership không bị trộn.

### 21.1. Ví dụ tìm orphan customers

~~~javascript
db.bookings.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customers"
    }
  },
  {
    $match: {
      customers: { $size: 0 }
    }
  },
  {
    $limit: 100
  }
]);
~~~

Đây là mẫu kiểm tra. Nếu thiết kế cho phép xóa hoặc anonymize customer, phải điều chỉnh invariant theo nghiệp vụ thực.

### 21.2. Transactional consistency

Một transaction tạo order + inventory reservation + outbox phải hiện đúng commit boundary ở điểm phục hồi. Thiếu một phần có thể báo backup inconsistency hoặc lỗi logic đã có từ trước.

### 21.3. Monetary values

Dùng Decimal128/kiểu tiền chuẩn của ứng dụng, không so tổng tiền bằng float ngẫu nhiên.

### 21.4. Distinguish pre-existing defects

Nếu baseline đã có orphan record, restore tái tạo nó không nhất thiết là restore failure. Cần chứng cứ source/baseline để phân loại lỗi.

## 22. Kiểm tra indexes

Sau restore:

~~~javascript
db.orders.getIndexes();
~~~

Đối chiếu:

- Field order của compound indexes.
- Unique indexes.
- Partial/sparse indexes.
- TTL indexes.
- Collations.
- Hashed/geospatial/wildcard indexes khi dùng.
- Index readiness.
- Tên và option của index.

### 22.1. Unique index liên quan correctness

Nếu unique index tenantId+email thiếu sau restore, ứng dụng có thể insert duplicates dù dữ liệu ban đầu đủ.

### 22.2. Partial index/collation

Cùng tên index nhưng khác partialFilterExpression hoặc collation có thể thay đổi semantics. Không chỉ so danh sách tên.

### 22.3. TTL đặc biệt nhạy cảm sau restore

Nếu một backup cũ chứa expiresAt đã quá hạn so với thời gian hiện tại, TTL worker có thể xóa records sau khi target chạy. Cần dự kiến hành vi đó trong cách đo counts/retention.

### 22.4. Hidden indexes

Một index hidden hoặc không được chọn query planner có thể làm performance khác. Kiểm tra đúng state theo workload.

## 23. Explain các query chủ chốt

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

Quan sát:

- Index nào được dùng?
- Có COLLSCAN không mong muốn?
- Có blocking SORT?
- Documents/keys examined?
- Returned count và latency hợp lý?
- Môi trường đang cold cache hay warm cache?

### 23.1. Performance sau restore có thể chậm do cold cache

Không lấy một lần truy vấn cold-start để kết luận toàn bộ hệ thống kém. Ghi riêng cold-start vs steady-state.

### 23.2. Target sizing ảnh hưởng so sánh

Một target có CPU/IOPS khác production sẽ có latency khác. Report phải nêu khác biệt capacity.

## 24. Search và Vector Search

Một ứng dụng có thể dùng Atlas Search hoặc Vector Search. BSON documents đã restore không đủ chứng minh những indexes đó đã sẵn sàng.

Nếu deployment hỗ trợ:

~~~javascript
db.knowledgeChunks.getSearchIndexes();
~~~

Kiểm tra:

- Index definitions.
- Paths và filter fields.
- Vector numDimensions/similarity khi liên quan.
- Build/sync readiness.
- Query với dữ liệu kiểm thử.
- Tenant/status filter correctness.

### 24.1. Search index rebuild có thể ảnh hưởng RTO

Nếu chức năng tìm kiếm là core business, thời điểm search usable phải nằm trong điều kiện RTO, không được bỏ qua chỉ vì CRUD đã hoạt động.

### 24.2. Search synchronization là bất đồng bộ

Tài liệu MongoDB được ghi thành công không bảo đảm search index thấy ngay lập tức. Phải có readiness/visibility check trong ứng dụng.

## 25. Users, roles, network và encryption

Một dữ liệu phục hồi đúng có thể không dùng được nếu application không còn truy cập.

Kiểm tra:

- MongoDB auth mechanism.
- Application users/roles.
- TLS CA/certificates.
- Connection strings và replicaSet name.
- IP allowlists/private endpoints.
- Secret manager credentials.
- Customer-managed encryption keys/KMS.
- Audit logs và network policies.

### 25.1. Đừng chỉ dùng admin account để test

Admin có thể chạy mọi query nhưng application account thiếu quyền. Chạy smoke test qua credentials với **least privilege** tương tự production.

### 25.2. Không phát tán secrets

Không lưu password/connection string đầy đủ trong báo cáo hoặc screenshots. Mask/redact evidence.

### 25.3. KMS là dependency phục hồi

Nếu không có decryption key, backup có thể không sử dụng được. Kiểm tra key availability và quyền cấp trong DR target.

## 26. Collection options và validators

Tùy deployment/loại backup, phải xác minh:

- Collection validators và validationAction.
- Default collation.
- Capped collection options.
- Time-series settings.
- Views.
- Clustered collection options.
- Change stream pre/post-image settings nếu dùng.
- Các server-level settings/application configurations liên quan.

### 26.1. Validator mất có thể gây lỗi về sau

Ngay khi tất cả documents hiện tại hợp lệ, một validator bị thiếu có thể cho phép write dữ liệu sai sau cutover.

### 26.2. Views phụ thuộc source collections

Kiểm tra định nghĩa và chạy query qua view. Có collection đúng nhưng view definition thiếu vẫn khiến API báo lỗi.

## 27. TTL và sự khác biệt thời gian

Ví dụ:

~~~javascript
{
  _id: "session-001",
  expiresAt: ISODate("2026-11-13T00:00:00Z")
}
~~~

Nếu restore vào 2026-11-14 và TTL index hoạt động, document có thể sớm bị xóa vì đã quá hạn theo thời gian server.

### 27.1. Đừng chỉnh clock để “giữ” dữ liệu

Cần sử dụng target cô lập và phương án hợp lệ theo MongoDB version/retention policy. Thay đổi system clock tùy tiện có thể gây lỗi security, TTL, TLS và timestamps khác.

### 27.2. Counts trước và sau TTL

Nếu mục tiêu so sánh dữ liệu snapshot, ghi rõ thời điểm counts và TTL effects. Không báo corruption khi hệ thống đang làm đúng retention policy.

## 28. GridFS và file binary

Nếu ứng dụng lưu file bằng GridFS, backup cần bao gồm cả:

~~~text
fs.files
fs.chunks
~~~

hoặc bucket name tương ứng.

### 28.1. Kiểm tra file metadata

~~~javascript
db.fs.files.find(
  {},
  {
    filename: 1,
    length: 1,
    chunkSize: 1,
    uploadDate: 1
  }
).limit(10);
~~~

### 28.2. Kiểm tra bytes, không chỉ fs.files count

Dùng GridFS driver download mẫu file theo fileId, so expected length/checksum và kiểm tra file parse/open được.

### 28.3. Missing chunks

File metadata có thể tồn tại nhưng thiếu một chunk. Chỉ kiểm tra tên/size trên fs.files không phát hiện mọi lỗi download.

### 28.4. Orphan chunks

Một upload bị crash có thể tạo chunks không có file metadata. Không xóa tức thời trong khi có uploads đang diễn ra; cần grace period và runbook.

## 29. Object storage references

Nếu MongoDB lưu object references:

~~~javascript
{
  _id: "ATT-001",
  storage: {
    kind: "object",
    bucket: "private-attachments",
    key: "tenant-a/ATT-001/v3"
  },
  status: "ready"
}
~~~

MongoDB backup **không chứa bytes của object storage**.

### 29.1. Kiểm tra HEAD/GET

Với sample objects:

- Bucket/key/version tồn tại.
- Content-Length và checksum phù hợp.
- Quyền truy cập đúng.
- Download thành công.
- Attachment owner/tenant mapping hợp lệ.

### 29.2. Restore lệch mốc

Nếu MongoDB phục hồi về T1 còn object storage ở T2, có thể có:

- Orphan objects.
- Dangling references.
- Object versions không còn.
- Metadata và bytes lệch trạng thái.

### 29.3. Phối hợp DR hai hệ thống

Có object versioning/retention, backup strategy riêng và reconciliation. Không báo ứng dụng phục hồi hoàn toàn nếu critical files vẫn không tải được.

## 30. Change Streams sau restore

Nếu ứng dụng dùng MongoDB Change Streams:

- Resume token của cluster cũ có thể không còn phù hợp với oplog/history trên target.
- Downstream consumers có thể thiếu hoặc phát lại events.
- Search/caches/materialized views có thể lệch nguồn.

### 30.1. Quy trình

1. Dừng/đóng consumers trong target.
2. Xác định source checkpoint/watermark.
3. Kiểm tra resume token có còn hợp lệ không.
4. Quyết định resume hoặc full resync theo policy.
5. Bảo đảm idempotent downstream writes.
6. Mở consumers theo thứ tự được kiểm soát.
7. Theo dõi duplicates, lag và missing events.

### 30.2. Không reset token tùy tiện

Reset không có kế hoạch có thể bỏ sót dữ liệu hoặc replay quá nhiều events. Cần dùng watermark, idempotency keys hoặc rebuild snapshot.

## 31. Queues, outbox và external side effects

Ví dụ:

~~~text
Booking committed
      |
      v
MongoDB outbox
      |
      v
Queue consumer
      |
      +--> Charge payment
      +--> Send email
      +--> Update analytics
~~~

### 31.1. Replay risk

Nếu restore về thời điểm outbox chưa đánh dấu processed nhưng payment đã charge thật, chạy lại consumer có thể tạo giao dịch trùng.

### 31.2. Sandbox trong bài diễn tập

Dùng payment sandbox, email sink, fake webhook và namespace queues riêng. Không để staging gọi endpoint production gây side effects.

### 31.3. Sự thật bên ngoài không rollback theo MongoDB

Thanh toán đã thực hiện ngoài MongoDB sau recovery point vẫn tồn tại. Sự cố thật cần reconcile với payment ledger để tránh double charge/refund.

### 31.4. Idempotency

Các operations cần idempotency keys và cách xử lý replay/dedup phù hợp với dữ liệu thực tế.

## 32. Smoke tests ứng dụng

Định nghĩa bộ tests tối thiểu:

| Test | Điều chứng minh |
| --- | --- |
| Start/health | App đọc config và kết nối |
| Login/auth | Identity và role mapping |
| Tenant isolation | Không đọc dữ liệu tenant khác |
| List orders | Query/sort/pagination/index |
| Read order detail | Reference data tồn tại |
| Create test order | Database writable |
| Update status | Validators/concurrency |
| Cancel test order | Workflow và cleanup |
| Download attachment | GridFS/object refs |
| Search | Search/Vector readiness |
| Background task | Queue sandbox và outbox |
| Audit/metrics | Observability hoạt động |

### 32.1. Health 200 không đủ

Một liveness endpoint trả 200 có thể chỉ chứng minh process còn sống. Chạy các business APIs với expected outputs.

### 32.2. Application credentials

Không dùng admin MongoDB credential để thay cho một user login bình thường.

### 32.3. Test data riêng

Dùng test tenant, seed records hoặc IDs đã được phép; không tạo đơn hàng/giao dịch thật.

## 33. Controlled read tests

Ví dụ API:

~~~text
GET /orders?status=confirmed
GET /orders/order-test-001
GET /customers/customer-test-001
GET /attachments/attachment-test-001
~~~

Xác minh:

- HTTP status và JSON schema.
- Business data/versions.
- Sort và pagination.
- Filter đúng tenant.
- Unicode tiếng Việt và timestamps.
- References đến records khác.
- Không lấy stale cache từ production.

### 33.1. Cache invalidation

Nếu Redis cache còn dữ liệu cũ, app có thể trả nội dung trước restore dù MongoDB đã đúng. Xác định namespace/flush/rebuild policy cho target.

### 33.2. Client connection pool

Khi đổi URI, clients có thể giữ connections cũ. Kiểm tra startup/readiness và request thực sự tới target.

## 34. Controlled write tests

Trên target diễn tập đã xác nhận:

~~~javascript
db.drValidation.insertOne({
  _id: "dr-smoke-2026-11-14",
  kind: "smoke",
  createdAt: new Date()
});
~~~

Đọc lại:

~~~javascript
db.drValidation.findOne({
  _id: "dr-smoke-2026-11-14"
});
~~~

Cleanup:

~~~javascript
db.drValidation.deleteOne({
  _id: "dr-smoke-2026-11-14"
});
~~~

### 34.1. Không chạy trên production

Bộ test ghi chỉ dùng trong target cô lập, sau khi đã xác minh cluster identity và quyền.

### 34.2. Test qua API

MongoDB insertOne thành công chưa đủ chứng minh application create/update flows. Chạy API tương ứng bằng application role.

### 34.3. Unique index

Có thể dùng test keys để thử duplicate bị từ chối đúng như thiết kế.

### 34.4. Transactions

Nếu ứng dụng dùng multi-document transaction, chạy commit và rollback test trong môi trường staging, xác minh tất cả collections có trạng thái đúng.

## 35. End-to-end workflow test

Một ví dụ nghiệp vụ:

~~~text
Search available car
      |
      v
Check time slot
      |
      v
Create reservation
      |
      v
Confirm booking
      |
      v
Update availability
      |
      v
Write outbox event
      |
      v
Retrieve booking
      |
      v
Cancel test booking
~~~

Các assertions:

- Correct tenant.
- No double booking.
- Reservation/order consistency.
- Status transitions đúng.
- Outbox được tạo nhưng không gây external side effect thật.
- API response và audit log đúng.
- Cleanup không để orphan test records.

### 35.1. Chọn critical path

RTO thường phụ thuộc một tập workflows quan trọng đã được chốt; không cần mọi performance test của sản phẩm chạy xong mới báo core service, trừ khi SLA quy định.

### 35.2. Ghi kết quả cụ thể

Thay vì “booking OK”, báo:

~~~text
Create reservation: PASS
Confirm booking: PASS
Availability update: PASS
Cross-tenant access denied: PASS
Payment sandbox callback: PASS
Cancel test booking: PASS
~~~

## 36. Hiệu năng và capacity sau restore

Ngay sau restore, hiệu năng có thể bị ảnh hưởng bởi:

- Cold cache.
- Index builds chưa hoàn tất.
- Replica lag.
- IOPS/CPU thấp hơn production.
- Search index rebuild.
- Query planner chọn plan khác.
- Network cross-region.
- Connection pool misconfiguration.

### 36.1. Tách cold-start và steady-state

Đo:

- Time to first byte.
- P50/P95 API latency.
- Read/write throughput.
- Error rate.
- Connection establishment.
- Database CPU/IOPS.
- Queue processing lag.

### 36.2. Load test trong giới hạn

Không gây flood lên hạ tầng dùng chung. Có owner/limit rõ để bảo vệ môi trường diễn tập và các hệ thống khác.

### 36.3. RTO phải tính search readiness nếu core service cần search

Nếu CRUD ready nhưng tìm kiếm xe chưa sử dụng được và UX phụ thuộc search, không báo full service recovered.

## 37. Tính observed RTO từ timeline

Bảng ví dụ:

| Mốc | UTC |
| --- | --- |
| Sự cố giả định | 02:00 |
| Phát hiện | 02:03 |
| Cho phép restore | 02:08 |
| Target ready | 02:13 |
| Restore start | 02:14 |
| Restore complete | 02:30 |
| DB read/write pass | 02:33 |
| App started | 02:37 |
| Core smoke pass | 02:42 |
| Full optional features pass | 02:48 |

Nếu objective là core app usable:

\[
RTO_{\text{observed}}=42\ \text{phút}
\]

Restore tool chạy 16 phút (02:14–02:30), nhưng đó không phải toàn bộ RTO.

### 37.1. RTO objective so với observed

Nếu objective 90 phút, observed 42 phút đạt mục tiêu trong kịch bản/tập điều kiện được thử, nhưng không tự chứng minh mọi sự cố đều phục hồi trong 42 phút.

## 38. Tính observed RPO

Giả sử:

~~~text
Incident at:     2026-11-14T02:00:00Z
Recoverable to:  2026-11-14T01:57:00Z
~~~

Observed RPO là 3 phút.

### 38.1. Marker records

Có thể tạo test markers với timestamps trước/sau recovery point và kiểm tra record nào xuất hiện sau restore. Phải kiểm soát commit acknowledgement và clock accuracy.

### 38.2. Document createdAt không phải commit time tuyệt đối

createdAt có thể do app set trước commit hoặc bằng clock lệch. Marker methodology cần xác định nguồn thời gian và write semantics phù hợp.

### 38.3. So RPO với dữ liệu nghiệp vụ

Nếu đã mất các writes hợp lệ giữa recoverable point và incident, báo rõ phạm vi mất dữ liệu và kế hoạch reconcile, không chỉ con số phút.

## 39. Báo cáo kết quả và evidence

Một mẫu:

~~~yaml
drillId: "DR-2026-11-14-01"
scenario: "full-cluster-restore"
backupId: "snapshot-example"
target: "isolated-dr-cluster"
incidentPointUtc: "2026-11-14T02:00:00Z"
recoveryPointUtc: "2026-11-14T01:57:00Z"
observedRpoMinutes: 3
observedRtoMinutes: 42
targets:
  rpoMinutes: 15
  rtoMinutes: 90
validation:
  restoreJob: PASS
  dataCounts: PASS
  businessInvariants: PASS
  indexes: PASS
  appSmoke: PASS
  dependencies: PASS
issues:
  - "Search index ready later than core CRUD"
decision: "PASS_WITH_ACTIONS"
owner: "drill-lead"
~~~

### 39.1. Evidence artifacts

- Backup/source identifiers.
- Target configuration.
- Restore job logs/warnings.
- SHA-256 checks.
- Database inventories/counts.
- Business invariant assertions.
- Index definitions/readiness.
- Application smoke outputs.
- RTO/RPO timeline.
- Security/cutover reviews.
- Corrective actions có owner/deadline.

### 39.2. Không xuất raw secrets hoặc PII

Sanitize logs, URI, screenshots và raw documents trước khi chia sẻ báo cáo.

### 39.3. PASS_WITH_ACTIONS khác FAIL

Nếu tiêu chí bắt buộc đạt nhưng phát hiện cải tiến, có thể dùng PASS_WITH_ACTIONS. Nếu RTO/RPO hoặc critical business workflow fail, cần ghi FAIL theo exit criteria, không đổi tiêu chí sau khi thấy kết quả.

## 40. Go/No-Go trước cutover

Nếu diễn tập có kế hoạch chuyển traffic thực sự, cần checkpoint:

| Điều kiện | Pass/Fail |
| --- | --- |
| Recovery point được xác minh | |
| Data invariants passed | |
| Required indexes ready | |
| Application auth/ACL passed | |
| Core writes và reads passed | |
| File references usable | |
| External effects được kiểm soát | |
| Monitoring và alerting active | |
| Rollback plan hợp lệ | |
| Business owner approved | |

### 40.1. Không cutover chỉ vì ping pass

Nếu hệ thống chưa có unique indexes, search hoặc quyền phù hợp, những users đầu tiên có thể gặp lỗi hoặc tạo dữ liệu không hợp lệ.

### 40.2. DNS/TLS

Chuyển target có thể cần DNS, certificates, connection strings, connection pools và service discovery. Không tự đổi DNS production trong bài diễn tập cô lập.

## 41. Rollback không đơn giản là đổi URI về cluster cũ

Sau cutover, nếu cluster mới đã nhận writes:

~~~text
Old cluster frozen at T0
      |
      v
New cluster receives orders at T1
      |
      v
Error found at T2
~~~

Đổi URI về old cluster có thể làm mất những orders ghi ở T1.

### 41.1. Tránh split-brain

Không cho hai clusters nhận writes độc lập nếu không có cơ chế reconciliation/synchronization thiết kế trước.

### 41.2. Rollback gate

Quy định:

- Khi nào old cluster được đóng băng?
- Khi nào target bắt đầu nhận writes?
- Có thể replay writes mới không?
- Queues/outbox/payments đang trỏ đâu?
- Khi nào rollback bị cấm và phải forward-fix?

### 41.3. Forward-fix

Nếu target đã có writes hợp lệ quan trọng, sửa trực tiếp theo runbook có thể an toàn hơn quay về cluster cũ; quyết định dựa trên consistency và business impact.

## 42. Những sai lầm thường gặp

| Lỗi | Hậu quả |
| --- | --- |
| Chỉ kiểm tra status backup SUCCESS | Không chứng minh khả năng restore |
| Dùng URI sai target | Nguy cơ phá production |
| Dùng --drop không kiểm soát | Mất dữ liệu đích |
| Không lưu backup ID/timepoint | Không tái lập được drill |
| Thiếu KMS key | Không giải mã backup |
| Không kiểm tra oplog retention | PITR không khả dụng |
| Dump từng shard không nhất quán | Sai data/config |
| Chỉ so tổng count | Sai dữ liệu cục bộ khó phát hiện |
| So baseline ở mốc khác | False pass/fail |
| Không so hashes/invariants | Values sai vẫn được coi pass |
| Chỉ dùng admin credentials | Bỏ lỗi app roles |
| Không kiểm tra unique indexes | Duplicate writes sau restore |
| Bỏ TTL behavior | Documents bị xóa sau restore |
| Chỉ xem fs.files | Thiếu chunk không phát hiện |
| Không kiểm tra object storage | File references hỏng |
| Search index chưa ready | API search fail |
| Resume change stream token cũ | Miss/duplicate changes |
| Mở queue consumers thật | Duplicated side effects |
| Không sandbox payment | Charge/refund thật |
| RTO chỉ tính mongorestore | Quá lạc quan |
| RPO chỉ tính giờ file backup | Không phản ánh recoverable point |
| Không test writes | App có thể chỉ read-only |
| Không check tenant isolation | Rò dữ liệu |
| Không có rollback gate | Cutover gây split-brain |
| Target quá nhỏ/khác cấu hình | Hiệu năng không đại diện |
| Không lưu evidence | Không chứng minh kết quả |
| PASS dù critical workflow fail | Đánh giá sai DR readiness |
| Không cleanup target/secrets | Chi phí và rủi ro bảo mật |

## 43. Bài tập thiết kế kịch bản

### Bài 1 — RPO/RTO

Ứng dụng đặt xe có RPO mục tiêu 15 phút và RTO 60 phút. Hãy định nghĩa chính xác đồng hồ RTO và mức service usable.

### Bài 2 — Logic deletion

Một collection bị drop lúc 10:05. Snapshot lúc 09:00 và PITR tới 10:04. Chọn recovery point, nêu ảnh hưởng tới các writes hợp lệ sau đó.

### Bài 3 — Backup không decrypt được

Backup còn nguyên nhưng customer-managed encryption key đã bị revoke. Có thể đánh dấu DR pass không? Cần thêm bước nào trong key recovery?

### Bài 4 — Full cluster drill

Thiết kế scope, target cô lập, owners, stop conditions và acceptance criteria cho tình huống mất toàn cluster.

### Bài 5 — Sharded consistency

Vì sao các shards restore từ mốc khác nhau có thể gây lỗi? Cần kiểm tra config servers, mongos và shard keys thế nào?

## 44. Bài tập xác minh dữ liệu

### Bài 6 — Counts phân nhóm

Tổng count orders trước/sau restore giống nhau, nhưng 100 orders chuyển tenant. Thiết kế aggregation kiểm tra theo tenant/status.

### Bài 7 — Canonical hashes

Một record có ObjectId, Decimal128, Date và nested arrays. Hãy mô tả cách canonicalize trước khi hash để không tạo false mismatch.

### Bài 8 — Business invariants

Một booking confirmed phải có reservation và outbox event. Thiết kế assertions sau restore.

### Bài 9 — Unique index

Dữ liệu restore đủ nhưng unique index tenantId/email bị thiếu. Vì sao cần coi là lỗi correctness?

### Bài 10 — TTL

Restore sessions cũ và bật TTL index. Tại sao counts có thể thay đổi sau vài phút? Thiết kế kế hoạch validation.

### Bài 11 — GridFS

Thiết kế đọc thử file 50 MiB, kiểm tra length và checksum. Vì sao count fs.files không đủ?

### Bài 12 — Object storage

Một attachment metadata trỏ object version đã xóa. Đề xuất cách phát hiện/khôi phục và xử lý permission.

## 45. Bài tập xác minh ứng dụng

### Bài 13 — Smoke tests

Chọn 8 API tests cần thiết cho một ứng dụng đặt xe để chứng minh restored app usable.

### Bài 14 — Payment replay

Database phục hồi về trước outbox processed nhưng payment ngoài hệ thống đã charge thành công. Nếu consumer chạy lại sẽ có rủi ro gì? Thiết kế idempotency.

### Bài 15 — Change Stream

Resume token không còn valid trên target. Đề xuất snapshot resync/watermark và deduplication.

### Bài 16 — Search readiness

Dữ liệu BSON đã phục hồi nhưng Vector Search index còn rebuild. Khi nào được coi RTO đạt nếu search là core workflow?

### Bài 17 — Application role

Admin query thành công nhưng app connection lỗi auth. Nêu các kiểm tra users/roles/TLS/network.

### Bài 18 — Cache stale

Sau restore, Redis vẫn chứa document version cũ. Thiết kế invalidation/rebuild và kiểm chứng API read.

### Bài 19 — UTC

Giải thích cách tránh restore nhầm recovery point vì người vận hành dùng giờ địa phương.

## 46. Bài tập vận hành và evidence

### Bài 20 — Tính RPO

Incident 10:05, latest recoverable 10:01, RPO mục tiêu 3 phút. Observed RPO và kết luận?

### Bài 21 — Tính RTO

Incident 10:05, DB ready 10:30, app read-only 10:35, full core business pass 10:48. RTO observed nếu objective là full core business?

### Bài 22 — Go/No-Go

Soạn checklist trước chuyển traffic, xác định ai có quyền phê duyệt.

### Bài 23 — Rollback

Cluster mới đã nhận 100 bookings sau cutover. Vì sao không đổi URI trở lại ngay? Phân tích rollback vs forward-fix.

### Bài 24 — Evidence report

Thiết kế YAML báo cáo gồm backup ID, target, recovery point, RPO/RTO, validation results, issues, owners và actions.

### Bài 25 — Backup checksum mismatch

Artifact hash sai nhưng mongorestore hoàn tất. Có thể gọi cuộc diễn tập PASS không nếu integrity là tiêu chí bắt buộc?

### Bài 26 — Cô lập notifications

Một staging worker có quyền gửi email/SMS thật. Cần các bước nào trước khi khởi động app sau restore?

### Bài 27 — Multi-scenario DR

Lập kế hoạch diễn tập luân phiên: logical delete, region loss, PITR, object mismatch và Search readiness. Có nên báo cùng một RTO cho tất cả?

## 47. Checklist trước diễn tập

1. Kịch bản, scope và mục tiêu RPO/RTO được chốt.
2. Điểm bắt đầu RTO và mốc service usable được định nghĩa.
3. Owner, approval và stop conditions rõ.
4. URI/cluster ID target cô lập được xác minh.
5. Backup ID, recovery point và retention window có evidence.
6. Quyền backup storage và KMS đã kiểm tra.
7. MongoDB/tools/FCV compatibility phù hợp.
8. Disk, index capacity và networking đủ.
9. Target có security/retention phù hợp dữ liệu thật.
10. Email/SMS/payment/webhook/queue được sandbox.
11. Baseline counts/hashes/invariants tại recovery point.
12. Có required index/validator/role inventories.
13. Có data sample và GridFS/object file references.
14. Có critical API/business workflow tests.
15. Có kế hoạch rollback và cleanup.

## 48. Checklist trong và sau diễn tập

16. Ghi timestamps thực, không hồi tưởng.
17. Restore bằng công cụ được hỗ trợ cho topology.
18. Không dùng lệnh phá dữ liệu ngoài target được phép.
19. Kiểm tra job warnings/errors, không chỉ exit code.
20. Kiểm tra ping/topology/read/write.
21. Kiểm tra database/collection inventory.
22. So counts theo tenant/status và time-aligned baseline.
23. So hashes và business invariants.
24. Kiểm tra unique/compound/TTL/partial indexes.
25. Kiểm tra validators, collation, views.
26. Kiểm tra credentials, TLS, KMS và app user roles.
27. Download/verify GridFS và object sample files.
28. Xác minh Search/Vector index readiness.
29. Khởi chạy application với target URI.
30. Chạy auth, tenant isolation, CRUD và transaction tests.
31. Chạy core end-to-end workflow trong sandbox.
32. Kiểm tra outbox/queues/change-stream recovery.
33. Đo latency/error rate và database impact.
34. Tính observed RPO/RTO theo tiêu chí ban đầu.
35. Lưu logs/evidence đã redacted secrets/PII.
36. Phân loại PASS/FAIL/PASS_WITH_ACTIONS.
37. Giao corrective actions với owner/deadline.
38. Cleanup target/resources và thu hồi quyền tạm.

## 49. Mẫu runbook tóm lược

~~~text
NAME:
  MongoDB restore drill and application validation

SCENARIO:
  Approved failure scenario

SAFETY:
  Isolated authorized target
  No destructive operations on production
  External side effects disabled or sandboxed

INPUTS:
  Backup ID
  Recovery point
  Target cluster ID
  Validation manifest

RESTORE:
  Provision target
  Run supported restore workflow
  Record timestamps and logs

DATABASE CHECKS:
  Topology/roles/TLS
  Collections/counts/hashes/invariants
  Indexes/validators/TTL
  GridFS/object references
  Search/Vector readiness

APPLICATION CHECKS:
  Auth/tenant isolation
  Core reads and writes
  Booking transaction
  Files/search/queue sandbox
  Monitoring and alerts

METRICS:
  Observed RPO
  Observed RTO
  Restore duration
  Validation pass/fail

DECISION:
  PASS / FAIL / PASS_WITH_ACTIONS

CLEANUP:
  Preserve sanitized evidence
  Revoke temporary access
  Delete drill resources according to policy
  Track corrective actions
~~~

## 50. Kết luận

Một cuộc diễn tập MongoDB restore chỉ thành công khi chứng minh được ba tầng: **hạ tầng dữ liệu phục hồi được, dữ liệu đúng theo recovery point và ứng dụng tiếp tục xử lý nghiệp vụ quan trọng**.

Các điểm cần ghi nhớ:

- **RPO** phải dựa trên điểm dữ liệu thực sự khôi phục được.
- **RTO** phải đo tới thời điểm ứng dụng usable theo định nghĩa trước, không chỉ thời gian chạy lệnh restore.
- **Backup availability không bằng recovery readiness**. Diễn tập đều đặn giúp phát hiện thiếu log chain, KMS key, compatibility hoặc capacity.
- **Counts không đủ**: phải so hashes, invariant và sample records; kiểm tra indexes, validators, TTL và permissions.
- **Database không độc lập**: GridFS, object storage, search, caches, queues, change streams, payment và notifications có thể quyết định sự thành công của hệ thống.
- **An toàn là điều kiện bắt buộc**: restore sang target cô lập, sandbox external side effects, không dùng lệnh phá dữ liệu trên production.
- **Kết quả phải đo và truy vết được**: timeline, evidence, RPO/RTO, owner và corrective actions.

Một backup chỉ tạo ra **khả năng** phục hồi. Việc chứng minh khả năng đó bằng một restore drill đầy đủ, có dữ liệu kiểm chứng và có smoke tests ứng dụng mới biến sao lưu thành năng lực vận hành thực tế.

## Tài liệu tham khảo

- [MongoDB Manual — Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Atlas — Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
