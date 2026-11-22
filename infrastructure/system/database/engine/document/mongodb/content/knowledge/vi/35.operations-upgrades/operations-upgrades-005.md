# Chuẩn bị nâng cấp: bản sao lưu, ma trận tương thích và thử nghiệm

Nâng cấp MongoDB không chỉ là thay số phiên bản của `mongod` rồi khởi động lại. Với một hệ thống đang phục vụ người dùng thật, việc nâng cấp có thể tác động đến **dữ liệu, khả năng phục vụ, giao thức kết nối của driver, replication, sharding, indexes, transactions, tính năng bảo mật và khả năng quay lại khi phát hiện sự cố**.

Một lần nâng cấp có thể thành công ở mức hạ tầng — tất cả tiến trình đã chạy bản mới — nhưng hệ thống vẫn gặp lỗi:

- Ứng dụng dùng MongoDB Driver cũ không tương thích với server mới.
- Một stage trong aggregation hoặc cơ chế query planner thay đổi làm p99 latency xấu đi.
- Một job định kỳ sử dụng API đã bị deprecate.
- Replica set mất quorum khi người vận hành restart các nodes không đúng thứ tự.
- Bản sao lưu tồn tại nhưng không phục hồi được trong thời gian RTO cam kết.
- Phiên bản mới kích hoạt tính năng không thể dùng trên binary cũ, khiến kế hoạch “downgrade nhanh” không còn hợp lệ.
- Atlas Search/Vector Search indexes phải xây lại hoặc chưa đủ điều kiện hoạt động trong vùng triển khai mới.
- Tài khoản quản trị không đủ quyền để kiểm tra hoặc thực hiện một số bước nâng cấp.
- Thử nghiệm trên 1.000 documents không dự báo được hành vi trên collection production hàng trăm triệu documents.

Bởi vậy, **chuẩn bị nâng cấp** là một quy trình có bằng chứng và điều kiện ra quyết định. Ba trụ cột chính là:

1. **Bản sao lưu và khả năng khôi phục:** có thể phục hồi đúng dữ liệu/trạng thái hệ thống nếu nâng cấp thất bại không?
2. **Ma trận tương thích:** mỗi thành phần có hỗ trợ phiên bản đích và thứ tự chuyển đổi đã chọn không?
3. **Thử nghiệm:** trên một môi trường đại diện, tính đúng đắn, hiệu năng, failover và vận hành có đạt yêu cầu không?

Bài học **“Chuẩn bị nâng cấp: bản sao lưu, ma trận tương thích và thử nghiệm”** thuộc chương **Vận hành và nâng cấp** trong module **Database Engine Document MongoDB**. Nội dung phù hợp cho **MongoDB Atlas** và **self-managed MongoDB**, bao gồm standalone, replica set và sharded cluster với những lưu ý khác nhau.

> **Nguyên tắc cốt lõi:** Chỉ quyết định nâng cấp production khi có **đường nâng cấp được tài liệu chính thức hỗ trợ**, **bản sao lưu đã thử khôi phục**, **môi trường thử nghiệm đại diện đã đạt tiêu chí**, và **kế hoạch dừng/khôi phục được phê duyệt**. “Có backup”, “binary chạy được” và “test vài query không lỗi” chưa đủ.

---

## 1. Phân biệt mục tiêu nâng cấp

Có nhiều loại thay đổi thường được gọi chung là “upgrade”.

| Loại thay đổi | Ví dụ | Nguy cơ chính |
|---|---|---|
| Patch upgrade | Nâng patch version trong cùng dòng server | Regression, restart/failover |
| Major version upgrade | Chuyển dòng MongoDB Server | Tương thích, FCV, deprecated features |
| MongoDB Driver upgrade | Java Sync Driver/Node/Python driver mới | API, TLS, retry, serializer, connection pool |
| OS/container upgrade | Linux distribution, kernel, image mới | Library support, certificates, filesystem |
| Atlas cluster tier change | Thay tier hoặc region/topology | Capacity, networking, SLA, cost |
| Replica set topology change | Thêm/bớt/vận chuyển members | Quorum, replication lag, availability |
| Sharded cluster upgrade | `mongos`, config servers, shards | Version ordering, balancer, routing |
| Storage/index change | Index rebuild, shard key, collation | Query performance, disk headroom |
| Security mechanism change | TLS CA, auth, KMS, key rotation | Client/member connectivity |
| Search/Vector Search change | Search nodes, mappings, embedding model | Indexing lag, search compatibility |

**Không nên gom nhiều thay đổi không liên quan vào cùng một cửa sổ nâng cấp** khi có thể tách ra. Nếu nâng server, đổi TLS CA, thay driver, di chuyển region và sửa hàng chục indexes cùng lúc, việc xác định nguyên nhân một lỗi sẽ khó hơn nhiều.

### 1.1. Patch upgrade không hoàn toàn “không rủi ro”

Patch releases thường nhắm tới bug fixes, security updates và cải tiến ổn định, nhưng vẫn có thể gây regression trên một workload hoặc môi trường đặc thù.

Vì vậy:

- Đọc release notes;
- Xem known issues;
- Kiểm tra phiên bản driver và tooling;
- Có canary/staging tests;
- Lên kế hoạch restart/failover;
- Có rollback/restore decision rõ ràng.

### 1.2. Major upgrade cần kiểm tra cả FCV

MongoDB phân biệt:

- **Binary version:** mã chương trình `mongod`/`mongos` đang chạy.
- **Feature Compatibility Version (FCV):** mức cho phép sử dụng một tập tính năng/định dạng có thể ảnh hưởng khả năng tương thích trong nâng cấp hoặc hạ cấp.

Một hệ có thể đã chạy binaries phiên bản mới trong khi **FCV vẫn ở mức trước đó** như một giai đoạn có chủ đích của quy trình nâng cấp.

Không coi “binary mới chạy” tương đương “đã hoàn tất mọi bước major upgrade”.

### 1.3. Giả định thời gian triển khai

Các thông tin về hỗ trợ phiên bản, FCV, operating systems, drivers và Atlas tiers có thể thay đổi theo từng MongoDB release. Vì vậy tài liệu này nêu **nguyên tắc và ví dụ cấu trúc**, còn các con số version tối thiểu và đường chuyển đổi cụ thể phải được xác nhận từ **Upgrade Procedures, Compatibility Matrix, Release Notes và Atlas upgrade policy** ứng với phiên bản đang dùng tại ngày triển khai.

Không mặc định có thể nhảy trực tiếp qua nhiều dòng major version hay rollback bằng cách cài binary cũ.

## 2. Mục tiêu và tiêu chí thành công của một upgrade

Trước khi làm bất cứ thao tác nào, trả lời:

1. Tại sao phải nâng cấp?
2. Phiên bản hiện tại và đích là gì?
3. Những tính năng nào sẽ được bật sau nâng cấp?
4. Có yêu cầu downtime hoặc maintenance window không?
5. Mức chấp nhận được của lỗi, latency và replication lag?
6. RPO/RTO là bao nhiêu?
7. Nếu lỗi xảy ra, khi nào rollback và bằng cách nào?
8. Ai có quyền đưa ra quyết định GO/NO-GO?

### 2.1. Ví dụ mục tiêu có thể đo

Một nhóm có thể đặt:

```text
Reason:
  Migrate from source release to supported target release,
  receive security fixes and newer query capabilities.

RPO:
  <= 15 minutes for declared disaster scenarios.

RTO:
  <= 2 hours to restore critical operations.

Availability:
  Critical API error rate within existing SLO.

Performance:
  Read p95 and write p95 regress no more than approved budget.
  No sustained p99 latency spike beyond release guardrail.

Correctness:
  No data loss, incorrect writes, cross-tenant access, or failed invariants.

Recovery:
  Restore drill completed and evidence approved.
```

Các ngưỡng là **ví dụ**; mỗi sản phẩm cần mục tiêu cụ thể theo mức độ quan trọng. Với hệ thanh toán, “không mất giao dịch” có thể cần một hợp đồng mạnh hơn một ứng dụng dữ liệu tạm thời.

### 2.2. Điều kiện hoàn thành

Upgrade chỉ được coi là hoàn tất khi:

- Tất cả các thành phần mục tiêu đã đạt version mong muốn;
- Topology bình thường, replication ổn;
- FCV ở mức được phê duyệt theo kế hoạch;
- Ứng dụng/drivers hoạt động;
- Business smoke tests và regression tests qua;
- Query latency và error rate đạt guardrails;
- Backup/monitoring vẫn hoạt động;
- Các tính năng Search/Vector/CDC liên quan được xác nhận;
- Runbook và system inventory được cập nhật.

“Không còn lỗi trong log lúc khởi động” chưa đủ.

## 3. Lập danh mục hệ thống trước nâng cấp

Cần inventory theo **cả hệ thống**, không chỉ `db.version()`.

Một ví dụ:

```text
Environment: production
Platform: MongoDB Atlas / self-managed
Topology: replica set / sharded
Source MongoDB Server version:
Target MongoDB Server version:
Current FCV:
Target FCV:
Operating systems / images:
MongoDB Drivers and versions:
Backup method:
PITR availability:
Recovery objectives:
Authentication and TLS:
KMS / encryption:
Search / Vector Search:
Change streams / CDC:
Analytics / BI consumers:
Data size / index size:
Current p95/p99:
Owners / approval:
```

### 3.1. Những thành phần thường bị quên

- `mongod` primary và secondaries;
- `mongos` routers;
- Config server replica set;
- Hidden/delayed/analytics members;
- Backup agent, monitoring exporter;
- Java/Python/Node/Go drivers;
- `mongosh` và MongoDB Database Tools;
- MongoDB Compass;
- ODM/frameworks như Spring Data MongoDB;
- Custom serializers/codecs;
- Change stream consumers và resume token processing;
- Atlas Search/Vector Search;
- Scheduled jobs chạy hiếm;
- Third-party connectors, BI, stream processors;
- Authentication integration, certificates và KMS;
- Kubernetes Operator hoặc automation tools nếu dùng.

Một upgrade chỉ thử API chính mà không thử job báo cáo cuối tháng có thể bỏ sót lỗi tương thích quan trọng.

### 3.2. Thu thập versions bằng lệnh chỉ đọc

Trong `mongosh`, khi có quyền:

```javascript
db.version();
```

Một cách xem server build metadata:

```javascript
db.adminCommand({
  buildInfo: 1
});
```

Kiểm tra FCV:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Trên deployment phù hợp, kiểm tra topology:

```javascript
db.hello();
```

Trong replica set:

```javascript
rs.status();
```

Trong sharded cluster qua `mongos`:

```javascript
sh.status();
```

Các lệnh này **đọc thông tin**; nhiều lệnh yêu cầu privileges. Không đăng raw outputs lên kênh công khai vì có thể lộ hostnames, topology, user/role metadata hoặc thông tin vận hành.

### 3.3. Không chỉ dùng version của node đang kết nối

Nếu client chọn một secondary hoặc `mongos`, `db.version()` phản ánh server endpoint đó, **không tự chứng minh mọi thành phần trong cluster cùng phiên bản**.

Cần xác minh từng node/nhóm thành phần thông qua monitoring/automation và thông tin topology phù hợp.

## 4. Khảo sát baseline trước thay đổi

Nếu không biết hệ thống **trước nâng cấp** nhanh và ổn định đến đâu, sẽ khó xác định một regression sau nâng cấp.

### 4.1. Baseline bắt buộc

| Nhóm | Thông tin cần lưu |
|---|---|
| Dữ liệu | Số document, logical size, storage/index sizes |
| Đọc | Read ops/s, query p50/p95/p99, slow query rate |
| Ghi | Insert/update/delete throughput, write p50/p95/p99 |
| Lỗi | HTTP/database error rate, retries, timeout categories |
| Kết nối | Current/active/available, pool wait, connection churn |
| Cache | WiredTiger cache/eviction, dirty pages, cache misses |
| CPU/I/O | CPU, memory, disk IOPS/latency, free disk |
| Replica set | Member health, elections, replication lag, oplog window |
| Sharding | Per-shard load, chunk distribution, routing, balancer |
| Backup | Last successful backup, retention, last restore drill |
| Search | Search/Vector index readiness, indexing lag |
| CDC | Change stream consumer lag và error rate |
| Business | Checkout/search/order metrics, background jobs |

### 4.2. Ghi nhận biến động theo giờ/ngày

Một peak buổi tối có thể khác xa mức trung bình ban ngày. Nên lấy baseline đại diện:

- Giờ bình thường;
- Giờ cao điểm;
- Cuối tuần;
- Ngày báo cáo/batch;
- Import/export;
- Sự kiện flash sale hoặc campaign;
- Tenant lớn/nhỏ.

Không benchmark lúc 03:00 rồi kết luận nâng cấp không tác động traffic lúc 20:00.

### 4.3. Kiểm tra dung lượng trống

Upgrade/restart/initial sync/index build/restore có thể cần disk headroom. Một volume còn đúng vài phần trăm dung lượng là tín hiệu phải xử lý trước, ngay cả khi database hiện vẫn trả query.

Các câu hỏi:

- Dataset/indexes tăng bao nhanh?
- Có temporary files, journal hoặc backup staging không?
- Có đủ chỗ khi rollback/restore?
- Storage engine có tính năng mới ảnh hưởng footprint không?
- Có thể tăng disk an toàn không?
- Disk pressure có được alert không?

## 5. Bản sao lưu: bảo vệ dữ liệu trước khi nâng cấp

Một nguyên tắc quan trọng:

> **Không bắt đầu nâng cấp dữ liệu production quan trọng chỉ vì hệ thống nói “backup job SUCCESS”.** Cần biết backup đó **bao phủ đúng phạm vi**, **giữ được consistency**, **đã kiểm tra phục hồi**, và **có sẵn encryption keys/quyền truy cập**.

### 5.1. Các hình thức backup

| Hình thức | Đặc điểm | Lưu ý khi nâng cấp |
|---|---|---|
| Atlas Cloud Backup / snapshots | Managed backup theo tier/chính sách | Kiểm tra retention, restore target, region, PITR |
| Filesystem/block snapshots | Snapshot hạ tầng tại một thời điểm | Cần quy trình nhất quán cho MongoDB topology |
| `mongodump` / `mongorestore` | Logical export/import BSON | Không tự bảo đảm consistent point-in-time trên mọi workload/topology |
| Oplog / PITR | Có thể phục hồi tới thời điểm trong khoảng hỗ trợ | Cần backup base, oplog coverage, công cụ phù hợp |
| Third-party backup agent | Backup theo vendor/tool | Kiểm tra certification, encryption, restore semantics |

Không có một phương pháp tốt nhất cho mọi deployment. Sự lựa chọn phụ thuộc RPO/RTO, Atlas tier, collection size, sharding, write throughput và yêu cầu tuân thủ.

### 5.2. Logical backup không tự là snapshot nhất quán

Ví dụ công cụ:

```bash
mongodump \
  --uri "$MONGODB_URI" \
  --archive="/secure-backups/preupgrade.archive.gz" \
  --gzip
```

Đây là **lệnh minh họa**, không phải thao tác cần chạy ngay trên production. Lệnh trên theo shell Unix; trên Windows PowerShell, cách xuống dòng và biến môi trường khác.

Nếu dữ liệu tiếp tục được cập nhật, logical dump có thể thu dữ liệu ở các thời điểm khác nhau. Các lựa chọn như `--oplog` có **điều kiện triển khai và giới hạn riêng**, không phải áp dụng cho mọi sharded cluster hoặc mọi tình huống. Để có một restore point nhất quán, cần làm theo **backup procedure chính thức cho topology**.

### 5.3. Backup một sharded cluster

Một sharded cluster có:

```text
mongos
   ├── Config server replica set
   ├── Shard A replica set
   ├── Shard B replica set
   └── Shard C replica set
```

Không thể tự chụp snapshot từng shard ở những thời điểm tùy ý và mặc định bộ snapshots tương ứng với một ảnh toàn cluster nhất quán.

Cần quy trình được MongoDB/backup vendor hỗ trợ, giải quyết:

- Metadata của config servers;
- Dữ liệu trên mọi shards;
- Transactions/chunk migrations;
- Thứ tự/thời điểm snapshot;
- PITR khả dụng;
- Restore topology.

### 5.4. Backup file cũng là dữ liệu nhạy cảm

Backup có thể chứa tất cả collection, user data và dữ liệu đã không còn hiện ở ứng dụng.

Do đó cần:

- Encryption at rest;
- TLS khi truyền;
- IAM/ACL tối thiểu;
- KMS keys và rotation policy;
- Storage không public;
- Retention và deletion policy;
- Audit người truy cập;
- Bảo vệ chống xóa/sửa trái phép khi cần;
- Vị trí độc lập failure domain;
- Kiểm tra integrity.

Không lưu backup tạm lên ổ đĩa laptop cá nhân hoặc bucket công khai chỉ vì đó là “bản thử”.

## 6. RPO, RTO và thời điểm khôi phục

Trước nâng cấp, phải thống nhất:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất trong kịch bản sự cố đã định.
- **RTO (Recovery Time Objective):** thời gian tối đa để dịch vụ quan trọng được khôi phục.

Ví dụ:

```text
Business RPO: 15 phút
Business RTO: 2 giờ
Last snapshot: 12 giờ trước
PITR: Không có
```

Trong tình huống mất dữ liệu toàn cluster, hệ thống **không có bằng chứng đạt RPO 15 phút** chỉ bằng snapshot 12 giờ trước.

### 6.1. Mô hình phục hồi

```text
Base backup at T0
        │
        ├── Oplog/continuous changes T0 → T1
        ├── Oplog/continuous changes T1 → T2
        └── Target recovery point T2
```

PITR chỉ khả dụng khi giải pháp backup/cluster tier/retention hỗ trợ và đủ coverage của change log. Nó không phải thuộc tính mà mọi MongoDB database có sẵn theo cùng cách.

### 6.2. Khả năng khôi phục còn phụ thuộc vào keys

Nếu dữ liệu được mã hóa, phải có **khả năng sử dụng KMS/encryption keys** hợp lệ khi restore.

Một backup được mã hóa nhưng key đã mất hoặc bị thu hồi có thể không dùng được. Kế hoạch nâng cấp phải bảo vệ cả:

- Backup artifacts;
- Encryption keys;
- TLS/authentication secrets cần cho restore;
- Kết nối và quyền truy cập restore environment;
- Network/DNS dependency của hệ thống sau restore.

### 6.3. Backup success khác restore success

Đây là hai câu hỏi riêng:

1. Công cụ có tạo được backup artifact không?
2. Từ artifact đó có thể khôi phục dữ liệu đủ, đúng, nhanh và truy cập được không?

Chỉ câu hỏi thứ hai chứng minh khả năng phục hồi.

## 7. Restore drill: thử khôi phục trước upgrade

Một **restore drill** là lần thử khôi phục có tổ chức trên môi trường cô lập, với dữ liệu phù hợp mức bảo vệ và mục tiêu đo rõ ràng.

```text
Approved backup artifact
          │
          ▼
Isolated restore environment
          │
          ▼
Restore database/topology
          │
          ▼
Validate integrity and consistency
          │
          ▼
Run application smoke tests
          │
          ▼
Measure RPO/RTO
          │
          ▼
Record evidence and remediation
```

### 7.1. Các bước

1. Chọn backup mới nhất trong phạm vi phù hợp.
2. Ghi backup ID, timestamp, cluster/version, retention.
3. Chuẩn bị isolated restore target có bảo mật tương đương.
4. Xác nhận KMS keys/credentials và network.
5. Restore bằng công cụ/quy trình đã phê duyệt.
6. Kiểm tra collections, indexes, dữ liệu mẫu và invariants.
7. Chạy ứng dụng smoke tests.
8. Đo thời gian từ bắt đầu recovery tới trạng thái phục vụ.
9. Ghi dữ liệu có thể mất theo recovery point thực.
10. Lưu evidence đã redact và review kết quả.

### 7.2. Ví dụ `mongorestore` — chỉ trên đích cô lập

```bash
mongorestore \
  --uri "$ISOLATED_RESTORE_URI" \
  --archive="/secure-backups/preupgrade.archive.gz" \
  --gzip
```

**Không nhắm lệnh này vào production chỉ để thử.** Các tùy chọn như `--drop` có thể xóa collection trên restore target; chỉ sử dụng khi hiểu và đã xác minh môi trường đích đúng.

Bản restore phải được bảo vệ khỏi truy cập trái phép, đặc biệt nếu chứa PII. Không dùng dữ liệu production thật trong staging mà không có policy masking hoặc kiểm soát phù hợp.

### 7.3. Kiểm tra dữ liệu sau restore

Một số tiêu chí:

- Collections cần thiết đều có;
- Document counts hợp lý theo recovery point;
- Những unique constraints vẫn đúng;
- Indexes tồn tại hoặc được rebuild đúng;
- Tài khoản/roles và encryption hoạt động theo mô hình restore;
- Ứng dụng đọc/ghi dữ liệu thử hợp lệ;
- Transactions hoặc business invariants được thử;
- Replication/sharding topology ổn;
- Search/Vector indexes sẵn sàng khi có yêu cầu;
- Background consumers hoạt động;
- RPO/RTO đạt.

**Chỉ `db.stats()` trả về thành công không chứng minh khôi phục đã hoàn tất.**

## 8. Backup phải tương thích với kế hoạch rollback

Đừng đợi upgrade thất bại rồi mới hỏi “backup này khôi phục lên phiên bản nào được?”.

Cần xác minh:

- Restore vào server version nào được backup tool hỗ trợ?
- Có thể restore backup của bản mới về bản cũ không?
- Có metadata/index definitions đã thay đổi sau upgrade không?
- Có cần khôi phục toàn cluster thay vì một database không?
- Các dependent systems có cần phục hồi cùng thời điểm không?
- Cơ chế replication và resume tokens sau restore xử lý ra sao?
- Nếu schema đã được app mới ghi, app cũ có đọc được không?
- Nếu dùng feature mới, binary cũ có hiểu dữ liệu/config không?

Một số hướng downgrade chỉ khả dụng với **đường chuyển đổi, FCV và điều kiện cụ thể**; không phải tương đương restore từ một backup đã được chứng minh.

### 8.1. Backup snapshot trước mỗi mốc không thể đảo ngược

Một quy trình nâng cấp dài có thể có những cột mốc:

```text
Baseline backup / restore verified
          │
          ▼
Upgrade binaries
          │
          ▼
Verify mixed-version behavior
          │
          ▼
Set target FCV
          │
          ▼
Enable new-only features
```

Trước mốc khiến **downgrade khó hoặc không được hỗ trợ**, phải có backup/recovery point thích hợp và quyết định có thẩm quyền.

### 8.2. Backup sau upgrade cũng cần thiết

Sau khi xác nhận ổn định, cần kiểm tra backup/PITR vẫn chạy được trên deployment mới. Không coi backup trước upgrade là đủ cho toàn bộ vận hành sau này.

## 9. Ma trận tương thích: không chỉ server và driver

**Compatibility matrix** là bảng ghi từng thành phần, phiên bản hiện tại, phiên bản đích, bằng chứng hỗ trợ và người chịu trách nhiệm.

Mẫu:

| Thành phần | Hiện tại | Đích | Cần kiểm tra | Trạng thái |
|---|---|---|---|---|
| MongoDB Server | A | B | Supported upgrade path, release notes | PENDING |
| FCV | A | B | Preconditions và thứ tự `setFCV` | PENDING |
| Java Driver | X | Y/giữ X | Server compatibility, TLS, API changes | PENDING |
| Spring Data/ODM | X | Y | Driver range, codecs, transactions | PENDING |
| OS/container | X | Y | Supported platform, CPU, libraries | PENDING |
| Atlas tier/region | Current | Target | Version availability, maintenance policy | PENDING |
| MongoDB Tools | X | Y | Backup/restore feature compatibility | PENDING |
| Search/Vector Search | X | Y | Index/feature support, `mongot` | PENDING |
| Authentication | Current | Target | SCRAM, X.509, OIDC, LDAP/Kerberos as used | PENDING |
| Encryption/KMS | Current | Target | Queryable Encryption, keys, TLS | PENDING |
| CDC/BI connectors | X | Y | Change streams, resume token, FCV | PENDING |
| Monitoring/backup agent | X | Y | Server API/support matrix | PENDING |

A, B, X, Y là chỗ điền theo **inventory** thực tế. Không được biến bảng ví dụ này thành tuyên bố rằng một driver bất kỳ hỗ trợ mọi server tương lai.

### 9.1. Ba mức tương thích

Cần phân biệt:

1. **Có thể kết nối:** driver bắt tay và ping được server.
2. **Được nhà cung cấp hỗ trợ:** tổ hợp nằm trong support matrix.
3. **Đáp ứng workload của ứng dụng:** dữ liệu, queries, codecs, concurrency, security đều hoạt động đúng.

Một tổ hợp có thể “ping thành công” nhưng vẫn nằm ngoài phạm vi được hỗ trợ hoặc có hành vi lỗi với chức năng hiếm dùng.

### 9.2. Ma trận phải có nguồn và ngày kiểm tra

Nên có:

```text
Component:
Current version:
Target version:
Compatibility documentation:
Release note / advisory:
Checked on:
Verified by:
Evidence link:
Result: PASS / FAIL / UNKNOWN
```

Nếu thiếu nguồn hoặc version cụ thể, để `UNKNOWN`; không ghi PASS dựa trên trí nhớ hoặc tên major version.

## 10. Đường nâng cấp MongoDB Server và các bước trung gian

MongoDB có những **đường nâng cấp major version được hỗ trợ chính thức**, không phải luôn cho phép nhảy từ bất cứ dòng nào sang bất cứ dòng mới nào.

Một kế hoạch có thể phải đi qua các major versions trung gian:

```text
Source version
    │
    ▼
Supported intermediate release
    │
    ▼
Next supported release
    │
    ▼
Target version
```

Với mỗi chuyển tiếp, cần đọc đúng tài liệu **Upgrade a Replica Set** hoặc **Upgrade a Sharded Cluster** của release đích.

### 10.1. Vì sao không “copy binary mới nhất” là xong?

Các thay đổi có thể liên quan:

- WiredTiger/storage metadata;
- Feature Compatibility Version;
- Replication protocol/behavior;
- Index/catalog metadata;
- Query planner/aggregation semantics;
- Deprecated options;
- Driver wire protocol compatibility;
- Sharding metadata;
- Authentication defaults;
- Feature behavior theo server version.

**Nâng cấp quá nhiều bước cùng lúc làm mất khả năng xác minh và hồi phục theo từng ranh giới hỗ trợ.**

### 10.2. Kịch bản ví dụ

Một đội đang chạy MongoDB dòng A và muốn lên dòng C. Quy trình đúng:

1. Xác minh có hỗ trợ chuyển trực tiếp A→C không.
2. Nếu không, xác định A→B và B→C theo docs.
3. Kiểm tra điều kiện FCV ở mỗi chặng.
4. Thử từng chặng trên staging.
5. Kiểm tra backup/restore trước mốc quan trọng.
6. Ghi thời gian và các điều kiện go/no-go của mỗi chặng.

Đừng tự sáng tạo một đường chuyển tiếp dựa vào việc package manager cho phép cài bản mới.

## 11. Feature Compatibility Version: tại sao cần bước riêng?

**FCV** cho phép MongoDB điều khiển tập tính năng và một số hành vi liên quan dữ liệu/metadata trong quá trình major upgrade.

Một lộ trình khái quát:

```text
All nodes on old binary + old FCV
                  │
                  ▼
Rolling upgrade binaries to new version
                  │
                  ▼
All nodes on new binary + old FCV
                  │
        Validation / hold window
                  ▼
Set FCV to target version
                  │
                  ▼
Validation after FCV
```

Đây là **sơ đồ khái niệm**. Các yêu cầu chính xác, giá trị của command và bước chờ phụ thuộc release. Một số release có yêu cầu bổ sung; không áp máy móc sơ đồ cho mọi lần nâng cấp.

### 11.1. Kiểm tra FCV trước nâng cấp

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Có thể cần kết nối và privileges phù hợp. Lưu output làm evidence có kiểm soát.

### 11.2. Không nâng FCV ngay khi vừa nâng binaries

Sau khi binaries đã lên target, nên hoàn thành các bước xác minh mà procedure yêu cầu, đặc biệt:

- Cluster ổn định;
- Không còn node binary cũ;
- Replication healthy;
- Critical queries hoạt động;
- Driver compatibility;
- Backup path;
- Rollback decision.

**Nâng FCV có thể mở ra trạng thái/tính năng khiến đường downgrade bị hạn chế**. Không coi đây là một lệnh housekeeping vô hại.

### 11.3. `setFeatureCompatibilityVersion` là thao tác thay đổi

Một cú pháp lịch sử có dạng:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "<target-version>",
  confirm: true
});
```

`confirm` và yêu cầu chi tiết thay đổi theo MongoDB version. **Đây là ví dụ minh họa, không được chạy trực tiếp**: phải dùng đúng command/options và thủ tục chính thức của release cụ thể. Lệnh có thể tác động tương thích dữ liệu trên toàn deployment.

### 11.4. Downgrade FCV không đồng nghĩa downgrade binary được hỗ trợ

Một người vận hành có thể hạ FCV thành công nhưng binary downgrade vẫn phải tuân thủ release support matrix, trạng thái dữ liệu, feature usage và các hạn chế. **Không dùng thử nghiệm FCV đơn lẻ làm bằng chứng rollback.**

## 12. MongoDB Driver và ứng dụng: lớp tương thích quan trọng

Ứng dụng có thể sử dụng Java Sync Driver, Reactive Streams, Spring Data, Node.js Driver, Python PyMongo hoặc các connector khác.

### 12.1. Những gì cần kiểm tra

- Driver version hỗ trợ target server release không?
- Authentication mechanism và TLS/ciphers còn tương thích không?
- Driver kết nối được tới topology mới không?
- Read/write concern và retry behavior có khác không?
- Có Stable API/server API version được dùng không?
- BSON codecs/serializers có đọc được dữ liệu như cũ không?
- Transaction/session support có thay đổi?
- Change streams và resume token logic hoạt động?
- Pool settings, server selection, timeouts và monitoring events?
- ORM/ODM framework có pin một driver version cũ không?

### 12.2. MongoDB Stable API giúp gì?

MongoDB có **Stable API** để hỗ trợ tính ổn định của các command được bao phủ theo API version. Khi ứng dụng chọn Server API V1, nó có thể giảm một số rủi ro khi nâng server.

Tuy nhiên, Stable API **không bảo đảm**:

- Mọi query plan giống nhau;
- Mọi performance metric không đổi;
- Mọi tính năng ngoài API được bao phủ;
- Mọi server/driver combination được hỗ trợ mãi mãi;
- Không cần integration tests;
- Không còn thay đổi của dữ liệu, cache, replication.

Vì thế Stable API là **một cơ chế giảm rủi ro**, không phải giấy miễn kiểm tra regression.

### 12.3. Ví dụ Java cấu hình Stable API

Cấu trúc tham khảo với MongoDB Java Sync Driver phiên bản hỗ trợ:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ServerApi;
import com.mongodb.ServerApiVersion;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is required");
}

ServerApi serverApi = ServerApi.builder()
    .version(ServerApiVersion.V1)
    .build();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .serverApi(serverApi)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    var db = client.getDatabase("app");
    var result = db.runCommand(
        new org.bson.Document("ping", 1)
    );
    System.out.println(result.get("ok"));
}
```

Ví dụ dùng `ping` để kiểm tra connectivity. Nó không thay integration tests cho nghiệp vụ.

### 12.4. Strict/deprecation options

Server API có những cấu hình về strictness và deprecation errors trong các driver hỗ trợ. Trong staging, chúng có thể giúp phát hiện lời gọi nằm ngoài API contract hoặc dùng chức năng deprecated, nhưng phải thử với workload thực.

Không bật các kiểm tra có thể làm API cũ thất bại trên production mà chưa có kế hoạch chuyển đổi.

## 13. Framework, ODM và BSON compatibility

Java application dùng Spring Data MongoDB có thêm các lớp:

```text
Application repository / templates
           │
       Spring Data
           │
   MongoDB Java Driver
           │
      MongoDB Server
```

Khi đổi server hoặc driver:

- Kiểm tra Spring Data compatibility matrix;
- Kiểm tra cách serialize `LocalDateTime`, `Instant`, `BigDecimal`, UUID;
- Kiểm tra mapping `@Id`, enum, polymorphism;
- Kiểm tra `Decimal128` và custom codecs;
- Kiểm tra BSON types không còn được dùng;
- Kiểm tra null/missing semantics;
- Kiểm tra query pipeline được framework sinh tự động;
- Kiểm tra optimistic locking/version fields;
- Kiểm tra exception mapping và retry.

Một integration test nên **đọc/ghi document thật** với các field types quan trọng, không chỉ thực hiện `ping`.

### 13.1. Ví dụ test BSON round trip

```java
Document sample = new Document("_id", "UPGRADE-TEST-001")
    .append("tenantId", "T-01")
    .append("amount", new org.bson.types.Decimal128(
        new java.math.BigDecimal("12345.67")
    ))
    .append("createdAt", new java.util.Date())
    .append("active", true);
```

Trong staging, ghi document vào một collection riêng, đọc lại và so sánh các kiểu/giá trị được serialize. Không chạy test ghi trên production khi không có change window và dữ liệu test được kiểm soát.

### 13.2. Đừng sửa serializer cùng lúc khi nâng server nếu không bắt buộc

Nếu vừa nâng MongoDB major, vừa đổi UUID representation, timezone conversion và schema migrations, rất khó phân biệt lỗi nào đến từ đâu. Tách các thay đổi độc lập hoặc có test coverage rõ cho từng phần.

## 14. OS, CPU, package và runtime compatibility

Self-managed phải kiểm tra **supported platforms** của MongoDB Server release đích.

Các chiều quan trọng:

- Linux distribution/version;
- CPU architecture và instruction set;
- Kernel/library requirements;
- OpenSSL/TLS libraries;
- Filesystem/storage support;
- Container base image;
- Kubernetes/Operator version;
- Disk format/mount options;
- System limits (`ulimit`, file descriptors);
- Clock synchronization;
- Monitoring/backup tooling.

Không tự suy rằng một binary MongoDB mới sẽ chạy trên mọi Linux distribution mà bản cũ hỗ trợ.

### 14.1. Cảnh báo về package manager

Package manager có thể chọn một MongoDB version mới khi cập nhật repositories. Trước upgrade:

- Pin đúng package/repository;
- Xác nhận target build;
- Kiểm tra dependencies;
- Có package rollback artifact được hỗ trợ;
- Biết service unit/config paths;
- Không chạy blanket upgrade không có kiểm soát.

### 14.2. Runtime của client

Java runtime, TLS truststore, DNS client, connection pool và các native libraries cũng có thể ảnh hưởng kết nối. Upgrade server mới nhưng client dùng JRE/driver quá cũ có thể gặp TLS handshake hoặc authentication errors.

## 15. MongoDB Atlas: chuẩn bị có những điểm riêng

Với **MongoDB Atlas**, nhiều bước binary provisioning/restart do dịch vụ được quản lý, nhưng tổ chức vẫn chịu trách nhiệm về **compatibility, testing, release windows và dữ liệu**.

### 15.1. Những thông tin cần kiểm tra trên Atlas

1. Atlas tier/region có hỗ trợ target MongoDB version không?
2. Cluster có đủ điều kiện nâng không?
3. Atlas có maintenance window/auto-upgrade policy gì?
4. Backup/snapshot/PITR đang được bật và retention thế nào?
5. Có thể chọn thời điểm nâng hoặc bị giới hạn ở một số tier không?
6. Vùng mới/cấu hình network có làm thay đổi client connectivity không?
7. Search Nodes/Vector Search có feature restrictions không?
8. Có Global Cluster, multi-cloud, sharding hoặc private endpoints không?
9. KMS/customer-managed encryption keys có đầy đủ?
10. Có cảnh báo và người trực theo dõi thời gian nâng cấp không?

Các hành vi Auto-upgrade, version availability và backup retention phụ thuộc tier, region và chính sách Atlas hiện hành. Không dùng một hướng dẫn self-managed `apt upgrade` để thay quy trình Atlas.

### 15.2. Cluster tier cũng ảnh hưởng khả năng diễn tập

Một Free/Flex development cluster không nhất thiết mô phỏng đúng:

- Replica set capacity;
- Dedicated Search Nodes;
- IOPS/CPU/memory;
- HA/failover characteristics;
- Atlas monitoring/profiler;
- Backup/PITR features;
- Production network configuration.

Để dự báo production, staging nên gần với **topology, tier và data scale** thực tế, hoặc nêu rõ các hạn chế của bài thử.

### 15.3. Không đoán Atlas rollback chỉ bằng UI

Khả năng rollback version hoặc lựa chọn restore phụ thuộc loại cluster và tình trạng nâng cấp. Khi làm kế hoạch, xác minh **hành động Atlas thực sự hỗ trợ** và hậu quả của restore đối với URI, data loss window, Search indexes, users/roles và linked services.

## 16. Self-managed replica set: sơ đồ nâng cấp tuần tự

Một replica set điển hình:

```text
         Application
              │
              ▼
      MongoDB Replica Set
        ├── Primary P
        ├── Secondary S1
        └── Secondary S2
```

Một **rolling upgrade** được MongoDB hỗ trợ thường có logic khái quát:

1. Xác nhận backup, FCV và preconditions.
2. Nâng secondary theo thứ tự được thủ tục quy định.
3. Đợi mỗi member phục hồi/đồng bộ trước bước tiếp.
4. Nâng primary sau khi có quorum/secondaries sẵn sàng, có thể thông qua stepdown chủ động theo runbook.
5. Xác minh mọi members cùng target binary.
6. Kiểm tra clients, replication, latency và errors.
7. Chỉ thay FCV sau khi đáp ứng điều kiện của release.

### 16.1. Không restart toàn bộ members cùng lúc

Nếu cluster có ba voting members và người vận hành restart tất cả, hệ thống có thể mất majority và unavailable. Rolling upgrade nhằm giữ khả năng phục vụ trong giới hạn hỗ trợ, nhưng vẫn có failover blips.

### 16.2. Member đã nâng xong chưa đủ

Sau nâng một secondary, xác nhận:

- Process đang chạy đúng binary;
- Member trạng thái `SECONDARY`;
- Replication lag chấp nhận;
- Không có lỗi authentication/TLS;
- Không có disk/resource problems;
- Không có indexes/query issues;
- Connection từ monitoring/backup vẫn hoạt động.

Không chuyển sang node tiếp theo chỉ vì `systemctl` báo service started.

### 16.3. Primary stepdown có thể gây lỗi tạm thời

Một số operations có thể bị interrupted, retries hoặc server selection delays. Client/driver settings cần được thử trước:

- Retryable writes;
- Retryable reads theo command hỗ trợ;
- Transactions;
- Timeouts;
- Connection pool behavior;
- Read/write concern;
- Idempotency của nghiệp vụ.

Đừng hứa rolling upgrade **zero downtime tuyệt đối**. Nó giảm tác động và duy trì availability nếu điều kiện phù hợp, nhưng có thể có thời gian chuyển primary và transient errors.

## 17. Self-managed sharded cluster: nhiều tầng phụ thuộc

Một sharded deployment:

```text
Client
   │
 mongos
   │
   ├── Config Server Replica Set
   ├── Shard A Replica Set
   ├── Shard B Replica Set
   └── Shard C Replica Set
```

Quy trình major upgrade sharded cluster có thứ tự chính thức theo release. Một trình tự thường được tài liệu mô tả gồm **kiểm soát balancer/chunk migrations, nâng config servers, từng shard replica set, các `mongos` routers và FCV**, nhưng **phải xác nhận chính xác thứ tự và chi tiết cho phiên bản đích**.

### 17.1. Vì sao thứ tự quan trọng?

Các thành phần phải phối hợp qua metadata/config, chunk routing và protocol. Một tổ hợp phiên bản hỗn hợp có thể chỉ được hỗ trợ **trong cửa sổ rolling upgrade**, không phải trạng thái vận hành lâu dài.

### 17.2. Những bài thử riêng cho sharding

- Query targeting theo shard key;
- Scatter-gather queries;
- Cross-shard aggregation;
- Cross-shard transactions;
- Balancer/chunk migrations;
- Change streams;
- Shard key/unique index constraints;
- Query through multiple `mongos` routers;
- Replication lag của từng shard;
- Metadata/config server health.

### 17.3. Không tự thay balancer trong giờ cao điểm

Các thay đổi như dừng/khởi động balancer hoặc chunk migrations là thao tác vận hành có tác động. Không chạy tùy hứng để thử; thực hiện theo runbook có owner và version-specific procedure.

### 17.4. Mọi router phải được kiểm tra

Nếu có nhiều `mongos` instances sau load balancer, kiểm tra tất cả. Một router phiên bản cũ hoặc bị bỏ quên có thể tạo tình huống không được hỗ trợ dù phần lớn traffic hoạt động.

## 18. Tương thích với replication, oplog và change streams

Các dịch vụ downstream có thể phụ thuộc oplog/change streams:

```text
MongoDB → Change Stream Consumer → Queue → Data Warehouse
```

Khi nâng cấp, cần kiểm tra:

- Resume token persistence;
- Consumer reconnect/resume khi election;
- Thời gian downtime so với oplog window;
- Pre/post-images nếu dùng;
- Transaction events và ordering;
- Connector/SDK versions;
- Idempotency và duplicate delivery handling;
- Error/retry behavior;
- CDC lag.

### 18.1. Oplog window là giới hạn quan trọng

Nếu consumer ngừng trong maintenance window quá lâu và resume token không còn trong oplog window, nó có thể không resume như dự kiến.

Trước nâng cấp, xác minh **retention/window** của oplog, consumption lag và quy trình resnapshot/reconciliation.

### 18.2. Không coi change stream event là exactly-once end-to-end

Một consumer có thể nhận lại events sau reconnect/retry. Các downstream writes nên idempotent hoặc có cơ chế deduplication thích hợp. Upgrade test phải bao gồm restart và resume.

## 19. Tương thích với transactions

Nếu ứng dụng dùng multi-document transactions:

- Driver sessions còn hoạt động;
- Retry labels và retry policies đúng;
- Commit/abort semantics giữ nguyên;
- Write concern/read concern được hỗ trợ;
- Failover giữa transaction được xử lý;
- Transaction timeout/lifetime settings phù hợp;
- Sharded transactions có version/topology requirements;
- Không giữ transaction quá dài trong upgrade window.

### 19.1. Ví dụ kịch bản transaction test

Trong staging:

```text
1. Tạo đơn hàng.
2. Giảm tồn kho trong cùng transaction.
3. Commit thành công.
4. Đảm bảo cả hai thay đổi cùng tồn tại.
5. Tạo lỗi có chủ đích và kiểm tra rollback.
6. Thử primary stepdown theo kịch bản được phép.
7. Đảm bảo app retry đúng, không tạo đơn hàng kép.
```

Không thực hiện failover có chủ ý trên production chỉ để xem transaction có retry tốt không khi chưa được phê duyệt.

## 20. Compatibility của indexes và query plans

Một server upgrade có thể thay đổi query optimizer, index selection hoặc execution engine, ngay cả khi API và dữ liệu không đổi.

### 20.1. Inventory index definitions

```javascript
db.getSiblingDB("app")
  .orders.getIndexes();
```

Ghi nhận:

- Single/compound indexes;
- Unique/partial/sparse;
- TTL;
- Multikey;
- Collation;
- Hidden indexes;
- Text/geospatial/hashed/wildcard;
- Shard key-related requirements.

Nếu index cần rebuild hoặc tính năng index thay đổi behavior theo version, cần đưa vào ma trận tương thích.

### 20.2. Chọn query shapes để thử

Tập đại diện nên gồm:

- Query nóng theo `_id`;
- Compound filter/sort/limit;
- Range queries;
- Aggregation và `$lookup`;
- Multikey `$elemMatch`;
- Collation-sensitive search;
- Partial index predicates;
- Pagination (`skip`, keyset);
- Transaction read/write;
- Reporting queries;
- Geospatial/text/Search/Vector Search nếu có.

### 20.3. Dùng `explain` đúng cách

Ví dụ chỉ đọc:

```javascript
db.getSiblingDB("app").orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Quan sát:

```text
winningPlan
nReturned
totalKeysExamined
totalDocsExamined
executionTimeMillis
SORT / FETCH / IXSCAN / COLLSCAN theo plan format
```

Các tên stages khác nhau giữa classic/SBE và server versions; không xây test chỉ dựa vào chuỗi tên stage mà bỏ qua ngữ nghĩa.

### 20.4. Query plan thay đổi chưa chắc xấu

Nếu phiên bản mới chọn plan khác nhưng latency/resource đều tốt hơn, đó có thể là cải tiến. Ngược lại, plan vẫn có `IXSCAN` nhưng `keysExamined` tăng mạnh thì vẫn cần điều tra.

Sử dụng **measurements** trên workload thực, không coi plan shape giống bản cũ là điều kiện tuyệt đối.

## 21. Data model, validation và BSON compatibility

Một version upgrade có thể ảnh hưởng tới:

- Schema validation behavior;
- BSON type handling;
- Date/timezone conversions ở driver;
- Decimal128;
- UUID encoding;
- ObjectId;
- Null vs missing fields;
- Collation;
- Query expressions;
- Data migrations;
- Unique constraint handling.

### 21.1. Test bộ dữ liệu đa dạng

Không chỉ dùng documents “đẹp”. Có thể bao gồm:

```javascript
{
  _id: "MIGRATION-FIXTURE-1",
  tenantId: "T-01",
  amount: NumberDecimal("12345.67"),
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  tags: ["priority", "fragile"],
  attrs: { color: null },
  archived: false
}
```

Kiểm tra:

- Đọc/ghi round trip;
- Decimal precision;
- Date/timezone;
- Nested objects/arrays;
- Optional/missing fields;
- Validation reject paths;
- Unique constraints;
- BSON codec compatibility.

### 21.2. Schema migration và server upgrade nên tách mốc

Nếu bắt buộc schema migration trong cùng dự án, áp dụng chiến lược **expand-and-contract** nếu hợp:

```text
Old app compatible with old schema
         │
Add new optional schema fields
         │
Deploy dual-compatible app
         │
Backfill source data
         │
Upgrade server
         │
Validate both paths
         │
Remove obsolete fields after rollback window
```

Đường cụ thể phụ thuộc dữ liệu và ứng dụng; ý chính là **không làm app cũ không thể đọc dữ liệu ngay trước khi biết server upgrade có ổn hay không**.

## 22. Tính năng Search và Vector Search

MongoDB Search/Atlas Search và Vector Search sử dụng những Search indexes có vòng đời khác database B-tree indexes.

Trong một upgrade có thể cần kiểm tra:

- MongoDB Server version hỗ trợ `$search`, `$searchMeta`, `$vectorSearch`;
- Atlas tier/region/feature restrictions;
- `mongot` compatibility nếu self-managed;
- Search index definitions;
- Search Nodes size/topology;
- Lucene indexing lag;
- Search index rebuild/readiness;
- Embedding model/vector dimensions nếu có;
- Data access/ACL filters;
- Search result relevance và latency.

### 22.1. Search index có thể lag sau restore/thay đổi topology

Sau một thay đổi, MongoDB source data có thể query được qua `find()`, nhưng Search index vẫn đang initial sync/rebuild.

Phải kiểm tra cả:

```text
Source data available
Search index queryable
Search index caught up
Search result correctness
Search API latency
Authorization behavior
```

### 22.2. Kiểm tra danh sách Search indexes

Nếu deployment/version hỗ trợ:

```javascript
db.getSiblingDB("app").articles.aggregate([
  {
    $listSearchIndexes: {}
  }
]);
```

Đây là bước quan sát trạng thái/index definitions, không thay thế kiểm tra Search query và indexing lag.

### 22.3. Không dùng Search index như nguồn truth cho quyền

Một quyền vừa bị thu hồi trên source có thể chưa hiện trong Search index. Bất kể upgrade version nào, ứng dụng cần kiểm tra **authorization hiện hành** trước khi trả nội dung nhạy cảm. Upgrade test phải có trường hợp revoke rights khi Search lag.

## 23. Ma trận tính năng bị deprecate hoặc thay đổi

Một major upgrade có thể:

- Loại bỏ command/option cũ;
- Đổi default behavior;
- Đổi hệ thống query execution;
- Giới hạn một loại collection hoặc index;
- Thay cách driver xử lý retryable operations;
- Đổi hỗ trợ một authentication mechanism;
- Đổi support tier của Search/Vector;
- Cần điều chỉnh cấu hình hoặc monitoring exporter.

### 23.1. Không bỏ qua release notes

Với từng release chuyển tiếp, lập bảng:

| Thay đổi trong release | Ứng dụng có sử dụng? | Ảnh hưởng | Test |
|---|---|---|---|
| Deprecated command | Chưa rõ | Có thể bị lỗi | Static search + integration |
| FCV requirement | Có | Quy trình nâng cấp | FCV preflight |
| Query behavior | Có | Kết quả/performance | Regression dataset |
| Index changes | Có | Query plan, disk | Explain + benchmark |
| Auth/TLS updates | Có | Connectivity | Driver/CA tests |
| Backup tooling | Có | Recovery | Restore drill |
| Search version | Có | Index readiness | Search smoke/lag |
| Connector change | Có | CDC continuity | Resume/restart test |

Nếu một dòng là `Chưa rõ`, đó là **đầu việc cần kiểm chứng**, không phải mặc định không ảnh hưởng.

### 23.2. Kiểm tra deprecation cả ở ứng dụng

Có thể dùng:

- Static code search cho command names;
- Driver warnings/deprecation checks;
- Test suite;
- Query logs/profiler theo policy;
- Framework compatibility notes;
- API strict/deprecation options trên staging nếu phù hợp.

Không nhất thiết mọi lệnh cũ xuất hiện trong code đều được gọi trong production; cần test cả các luồng hiếm.

## 24. Thiết kế staging gần production

**Staging** là nơi thử quy trình nâng cấp trước khi chạm dữ liệu production.

### 24.1. Các yếu tố nên giống

- MongoDB source version/FCV;
- Target version;
- Topology replica set/sharded;
- Driver/ODM versions;
- Authentication/TLS/KMS;
- Query indexes;
- Data size/distribution hợp lý;
- App version;
- Background jobs;
- Workload read/write ratio;
- Shard key distribution;
- Search/Vector Search;
- Monitoring và backup agents.

Nếu staging chỉ có một standalone nhỏ trong khi production có sharded cluster nhiều tenant, **nó không kiểm thử được toàn bộ rủi ro topology**.

### 24.2. Dữ liệu thật hay dữ liệu tổng hợp?

Dùng dữ liệu đại diện nhưng phải bảo vệ privacy:

- De-identified/masked datasets khi policy cho phép;
- Synthetic data tái tạo cardinality/skew;
- Edge cases chọn lọc từ incidents đã được xử lý;
- Data volume đủ cho performance;
- Không đưa secrets/PII vào environment có security thấp.

Masking cũng cần giữ tính liên hệ giữa fields để test query behavior. Xóa hết giá trị đa dạng hoặc đổi mọi tenant thành cùng một tên có thể làm benchmark sai.

### 24.3. Không dùng staging để suy ra latency production nếu tier khác xa

Một staging cluster nhỏ có thể chậm hơn hoặc khác hoàn toàn production. Ngược lại một staging dataset nhỏ có thể làm mọi query nhanh giả tạo. Ghi rõ hạn chế và chạy **load tests/capacity tests** thích hợp.

## 25. Thử nghiệm chức năng: từ smoke đến regression

Một bộ kiểm thử nên phân tầng.

### 25.1. Smoke test

Các câu hỏi tối thiểu:

- App kết nối được?
- Authentication/TLS hoạt động?
- Ping/health check thành công?
- Đọc document theo `_id` được?
- Ghi thử vào collection staging được?
- Truy vấn index quan trọng không lỗi?
- Một transaction mẫu hoạt động?
- Change stream consumer resume?
- Backup/monitoring agent hoạt động?

Smoke test xác nhận hệ cơ bản sẵn sàng, **không đủ để chứng minh toàn bộ ứng dụng không có regression**.

### 25.2. Functional regression test

Nên bao gồm:

- CRUD;
- Bulk writes;
- Aggregations;
- Pagination/sorting;
- Unique constraints;
- TTL-dependent behavior;
- Transactions;
- Change streams;
- Search/Vector queries;
- Multi-tenant ACL;
- Error paths;
- Driver retry behavior;
- Background batch jobs.

### 25.3. Business regression tests

Với nền tảng bán hàng:

```text
Create order
→ Reserve inventory
→ Confirm payment
→ Update order status
→ Query customer history
→ Generate invoice
→ Fulfill or refund
```

Cần xác minh toàn bộ chuỗi logic, không chỉ các MongoDB calls riêng lẻ.

### 25.4. Kiểm tra dữ liệu không mất và không sai

Ngoài counts, test:

- Referential/business relationships;
- Uniqueness;
- Monetary totals;
- Status transition rules;
- Number/Decimal128 precision;
- Date/timezone rules;
- Tenant isolation;
- Idempotency;
- Soft deletes và retention.

Counts bằng nhau không chứng minh toàn bộ dữ liệu đúng.

## 26. Thử nghiệm hiệu năng: so cùng điều kiện

Một kế hoạch benchmark:

```text
Baseline: current server + current app
Candidate: target server + same app/config
Optional: target server + new driver (separate comparison)
```

Mục đích là **tách ảnh hưởng**.

### 26.1. Những chỉ số nên đo

| Chỉ số | Lý do |
|---|---|
| Read p50/p95/p99 | Trải nghiệm truy vấn |
| Write p50/p95/p99 | Chi phí ghi |
| Throughput | Năng lực xử lý |
| HTTP/business errors | Tác động user |
| Driver command failures/retries | Tương thích/topology |
| Connection pool wait | Bottleneck phía client |
| CPU, disk latency, WiredTiger cache | Resource pressure |
| Replication lag | Khả năng theo kịp writes |
| Query targeting | Index/query plan quality |
| Index sizes | Storage impact |
| Search QPS/lag | Derived search readiness |
| Backup/restore duration | Recovery budget |

### 26.2. Đừng chỉ đo average latency

Một upgrade có thể giữ read mean 20 ms nhưng p99 tăng từ 200 ms lên 2 giây. Với API nhiều traffic, tail latency có thể là vấn đề lớn.

### 26.3. Test warm cache và cold cache

- **Cold cache:** mô phỏng sau restart hoặc khi data mới cần đọc disk.
- **Warm cache:** steady-state workload.
- **Mixed load:** read/write/aggregation concurrency thực.
- **Peak load:** spike theo business.
- **Background jobs:** backup, index build, CDC, reports.

Không chọn lần chạy nhanh nhất làm chứng nhận performance.

### 26.4. Kiểm tra query plans

Ví dụ:

```javascript
db.getSiblingDB("app").orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

So sánh `totalKeysExamined`, `totalDocsExamined`, `nReturned` và latency. Nếu plan thay đổi, xem đó là improvement hay regression theo mục tiêu thực.

## 27. Thử nghiệm failover và khả năng phục vụ

Một major upgrade không hoàn chỉnh nếu chỉ thử trong điều kiện tất cả nodes khỏe và không xảy ra election.

### 27.1. Những kịch bản staging

- Restart một secondary;
- Primary stepdown theo runbook;
- Driver reconnect;
- Transaction đang mở khi election;
- Retryable writes;
- Change stream reconnect/resume;
- Read preference khi secondary không sẵn sàng;
- Network interruption;
- Một shard mất kết nối tạm thời;
- Search index rebuilding;
- Backup/monitoring agents restart.

**Chỉ thực hiện các thử nghiệm gây gián đoạn trong staging hoặc môi trường được phê duyệt.** Không chạy `rs.stepDown()` trên production chỉ để thử mà không có change window.

### 27.2. Kiểm tra các thông số timeout

Các timeout thuộc lớp khác nhau:

- Server selection timeout;
- Connection checkout wait timeout;
- Connect/socket timeout;
- MongoDB operation `maxTimeMS`;
- HTTP/API timeout;
- Transaction lifetime;
- CDC resume/retry policy.

Không tăng mọi timeout lên rất lớn để “hết lỗi”. Điều đó có thể che sự cố và làm hệ thống treo request lâu hơn.

### 27.3. Xác nhận idempotency

Trong failover/retry, ứng dụng phải tránh tạo đơn hàng/thu tiền hai lần. Một retryable error không phải lúc nào có nghĩa lệnh chưa có hiệu lực. Cần test business idempotency keys và đối soát giao dịch.

## 28. Thử nghiệm bảo mật khi nâng cấp

Một upgrade có thể thay đổi:

- TLS libraries/ciphers;
- Certificate validation;
- Supported authentication mechanisms;
- Driver auth defaults;
- User/role behavior;
- OIDC/LDAP/Kerberos integrations;
- KMS/Queryable Encryption compatibility;
- Audit log format;
- Network/private endpoint connectivity.

### 28.1. Những câu hỏi bắt buộc

1. TLS certificate vẫn hợp lệ và hostname verification không bị bỏ qua?
2. Cả service accounts lẫn admin accounts hoạt động đúng?
3. Không có tài khoản được tự nâng quyền?
4. Role scopes vẫn đúng?
5. Tenant isolation tests qua?
6. Secrets không bị ghi ra logs?
7. KMS keys được truy cập khi đọc dữ liệu encrypted?
8. Audit events vẫn được ghi theo yêu cầu?
9. Backup encryption không bị ảnh hưởng?
10. Các connectors có dùng TLS và least privilege?

### 28.2. Không “sửa” lỗi kết nối bằng cách tắt kiểm tra TLS

Các tùy chọn như:

```text
tlsAllowInvalidCertificates=true
tlsAllowInvalidHostnames=true
tlsInsecure=true
```

không phải phương án hợp lệ để đưa production qua upgrade gate. Phải sửa đúng CA, SAN, truststore, DNS và certificates.

## 29. Thử nghiệm backup/restore sau nâng cấp

Một lỗi bị bỏ sót là **database nâng cấp thành công nhưng backup agent không còn tương thích**.

Do đó sau nâng cấp staging, thử:

1. Tạo backup theo công cụ chính thức.
2. Restore lên isolated target.
3. Xác nhận data integrity.
4. Xác nhận collection/indexes.
5. Xác nhận Search/Vector Search nếu có.
6. Đo RTO và recovery point.
7. Xác nhận keys, permissions và application smoke.
8. Ghi evidence.

Nếu backup tooling phiên bản đích chưa được hỗ trợ, đó là **BLOCKER** đối với hệ yêu cầu backup.

## 30. Load testing: phát hiện regression ở quy mô thật

Một bài load test cần ghi rõ:

```text
Dataset size and distribution:
Index definitions:
Traffic mix:
Read/write concurrency:
Duration:
Warm-up:
Ramp-up:
Peak:
Success/error definitions:
p95/p99 thresholds:
Cluster tier:
CPU/disk/network capacity:
```

### 30.1. Ví dụ read/write mix

Giả sử production:

```text
Read operations: 70%
Write operations: 25%
Other/aggregation: 5%
```

Nếu load test dùng 100% reads, không thể chứng minh update/write latency và replication vẫn tốt dưới workload thật.

### 30.2. Data skew ảnh hưởng kết quả

Một tenant chứa 80% records có thể gây hotspot hoặc query plan khác. Synthetic dataset phân bố đều có thể bỏ qua vấn đề này.

Nên có:

- Tenant lớn/nhỏ;
- Hot partitions;
- Missing/null fields;
- Arrays;
- Rare statuses;
- Old/new timestamps;
- Long/short strings;
- Mixed BSON types.

### 30.3. Ngưỡng chấp nhận phải có trước khi chạy

Nếu team chạy xong rồi mới quyết định “p99 1,5 giây cũng ổn”, bài test thiếu tính khách quan. Cần xác định guardrails và owners trước.

## 31. Canary rollout: giảm blast radius

Nếu hạ tầng/ứng dụng hỗ trợ, có thể nâng một môi trường/cụm ít quan trọng trước, hoặc canary app traffic theo kế hoạch.

Tuy nhiên, **không phải MongoDB major upgrade nào cũng cho phép canary từng node/tenant tùy ý**. Mixed-version topology chỉ được hỗ trợ trong các điều kiện rolling upgrade; không dùng nó như một A/B server lâu dài nếu docs không cho phép.

### 31.1. Những hình thức canary

- Staging production-like;
- Internal/test tenant traffic;
- Một replica set ít quan trọng;
- Một cluster khác trong hệ multi-cluster;
- Application canary sau server upgrade;
- Read-only shadow traffic với dữ liệu được bảo vệ.

### 31.2. Shadow query cần quan tâm dữ liệu nhạy cảm

Không gửi query chứa PII sang staging hoặc một cluster thử nghiệm kém bảo mật. Nếu replay production traffic, phải có policy masking/access phù hợp.

### 31.3. Gating trước mở rộng

```text
Canary pass
     │
     ├── Errors within SLO
     ├── Latency within guardrail
     ├── No data integrity failure
     ├── No tenant/ACL regression
     ├── Replication stable
     ├── Backup working
     └── No serious new warnings
           │
           ▼
       Wider rollout
```

Không tăng traffic chỉ vì chưa ai báo lỗi; cần metrics và thời gian quan sát đủ.

## 32. Kế hoạch rollback: ba khái niệm khác nhau

Người mới thường nói “có lỗi thì rollback”. Nhưng rollback có thể nghĩa là:

1. **Rollback ứng dụng:** deploy lại phiên bản app cũ.
2. **Downgrade MongoDB binaries/FCV:** quay lại phiên bản server cũ theo thủ tục được hỗ trợ.
3. **Restore dữ liệu:** khôi phục deployment từ backup/recovery point.

Ba việc **không tương đương**.

### 32.1. Rollback ứng dụng

Thường có thể nhanh hơn nếu schema/driver tương thích ngược. Nhưng nếu app mới đã ghi dữ liệu theo schema mới mà app cũ không hiểu, rollback có thể thất bại.

### 32.2. Downgrade MongoDB

Không phải lúc nào được hỗ trợ, đặc biệt khi:

- FCV đã chuyển;
- Feature mới đã được bật/sử dụng;
- Internal metadata hoặc storage format thay đổi;
- Release yêu cầu các bước trung gian;
- Driver/tooling không còn tương thích;
- Dữ liệu sau nâng cấp không còn phù hợp với binary cũ.

Cần tra đúng **downgrade procedure** của target/source versions và không cam kết khả năng hạ binary khi chưa kiểm chứng.

### 32.3. Restore từ backup

Restore có thể phục hồi một trạng thái dữ liệu trước nâng cấp, nhưng cũng có thể làm mất những writes sau recovery point nếu không có PITR/reconciliation phù hợp.

Nếu muốn phục hồi application behavior mà không mất dữ liệu mới, cần thiết kế kỹ:

```text
Post-upgrade writes
        │
        ├── Có thể replay/reconcile an toàn?
        ├── Đã backup thay đổi chưa?
        └── Có idempotency?
```

Không coi “restore snapshot trước upgrade” là một **rollback zero data loss** mặc định.

### 32.4. Rollback cũng cần diễn tập

Trong staging, thử rollback path đã chọn:

- Trở lại ứng dụng cũ;
- Đảm bảo schema vẫn đọc được;
- Xác minh binary/FCV downgrade chỉ khi docs hỗ trợ;
- Hoặc restore và replay theo RPO;
- Kiểm tra indexes/rights/CDC;
- Đo thời gian hoàn tất.

Nếu rollback plan chưa từng thử, phải ghi nó là **chưa được chứng minh**.

## 33. Những mốc không nên vượt qua khi chưa được phê duyệt

Một upgrade có các **decision gates**:

```text
GATE 0: Inventory + compatibility known
                 │
GATE 1: Backup and restore proven
                 │
GATE 2: Staging functional/performance/security pass
                 │
GATE 3: Production change window approved
                 │
GATE 4: Binary upgrade validation
                 │
GATE 5: FCV / new feature activation approved
                 │
GATE 6: Post-upgrade stabilization complete
```

GATE 5 đặc biệt quan trọng vì việc bật tính năng mới hoặc nâng FCV có thể thay đổi đường downgrade. Không để hệ thống tự động kích hoạt features trước khi đã xác định rollback window/approval.

## 34. Checklist lệnh kiểm tra chỉ đọc trước nâng cấp

Ví dụ `mongosh` để thu thập evidence trên deployment được phép:

### 34.1. Server identity/version

```javascript
const dbAdmin = db.getSiblingDB("admin");

printjson({
  version: db.version(),
  hello: db.hello()
});
```

### 34.2. FCV

```javascript
printjson(
  db.getSiblingDB("admin").runCommand({
    getParameter: 1,
    featureCompatibilityVersion: 1
  })
);
```

### 34.3. Replica set

```javascript
rs.status();
```

Chỉ dùng trên topology phù hợp và không để outputs công khai.

### 34.4. Sharding

```javascript
sh.status();
```

Chạy qua `mongos` khi cluster có sharding.

### 34.5. Collection/indexes

```javascript
const app = db.getSiblingDB("app");

printjson(app.orders.getIndexes());
printjson(app.orders.stats({ scale: 1024 * 1024 }));
```

### 34.6. Server status — đọc số liệu tối thiểu

```javascript
const s = db.serverStatus();

printjson({
  localTime: s.localTime,
  uptime: s.uptime,
  opcounters: s.opcounters,
  connections: s.connections,
  opLatencies: s.opLatencies
});
```

Output tùy version và privilege; một số counters là **tích lũy từ lúc server khởi động**, không tự là QPS hay latency percentile.

### 34.7. Phiên authentication hiện tại

```javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

### 34.8. Search index

Nếu có Search feature và quyền phù hợp:

```javascript
db.getSiblingDB("app").articles.aggregate([
  { $listSearchIndexes: {} }
]);
```

### 34.9. Tài liệu nhạy cảm trong output

Các kết quả inventory có thể chứa hostnames, node addresses, users/roles, collection names hoặc query metadata. Lưu tại nơi được kiểm soát và redact trước khi đưa vào báo cáo.

**Không biến preflight thành script tự restart, set FCV, drop indexes hoặc thay credentials.** Những việc đó cần kế hoạch thay đổi riêng.

## 35. Kế hoạch nâng cấp theo pha

Một quy trình chi tiết có thể gồm bảy pha.

### Pha A — Khởi tạo yêu cầu

- Chọn target version;
- Ghi security/support reason;
- Xác định environments;
- Gán người phụ trách;
- Đặt thời gian dự kiến;
- Khóa scope thay đổi;
- Xác định RPO/RTO và SLO.

### Pha B — Inventory và compatibility

- Liệt kê server members/router/config;
- Ghi current binary/FCV;
- Kiểm tra supported upgrade path;
- Driver/ODM/OS/tooling matrix;
- TLS/KMS/auth;
- Search/Vector/CDC;
- Release notes/deprecations.

### Pha C — Bảo vệ dữ liệu

- Kiểm tra backup policy/retention;
- Tạo restore point phù hợp;
- Restore drill;
- Data integrity validation;
- Kiểm tra PITR/oplog;
- Xác nhận key recovery;
- Ghi RPO/RTO thực.

### Pha D — Thử nghiệm

- Staging upgrade theo runbook;
- Functional tests;
- Performance/load tests;
- Failover tests;
- Security regression;
- Backup/restore after upgrade;
- Rollback rehearsal;
- Sign-off.

### Pha E — Production change window

- Freeze thay đổi không cần thiết;
- Notify stakeholders/on-call;
- Preflight backup/health;
- Chạy từng bước đã phê duyệt;
- Ghi timestamps, commands/versions và outcomes;
- Dừng khi gate fail.

### Pha F — Kiểm tra hậu nâng cấp

- Binary/FCV/topology;
- Replica/shard health;
- App smoke/regression;
- Query latency/errors;
- CDC/Search/indexes;
- Backup/monitoring;
- Security controls.

### Pha G — Stabilization và đóng thay đổi

- Observe đủ thời gian qua các workload peak/batch;
- Cập nhật inventory/architecture;
- Ghi bài học từ incident;
- Bàn giao runbook;
- Chỉ bật tính năng mới theo approval;
- Kết thúc rollback window theo quyết định có căn cứ.

## 36. Runbook production: những gì phải ghi

Một runbook tốt có thể được người khác thực hiện được, không phụ thuộc hoàn toàn vào người soạn.

Mẫu:

```text
CHANGE: MongoDB Server Upgrade

Change ID:
Source version/FCV:
Target version/FCV:
Deployment type/topology:
Change window:
Business impact:
RPO/RTO:
Owner:
DBA lead:
Security reviewer:
Application owner:
On-call:
Communication channel:

Preconditions:
  [ ] Approved compatibility matrix
  [ ] Version-specific official upgrade guide attached
  [ ] Backup validated
  [ ] Restore drill passed
  [ ] Staging test evidence approved
  [ ] Capacity headroom available
  [ ] Monitoring/alerts enabled
  [ ] Credentials/permissions verified
  [ ] Rollback decision points documented

Execution:
  Step ID:
  Target node/component:
  Preconditions:
  Command or Atlas action reference:
  Expected state:
  Evidence:
  Timeout:
  Stop condition:
  Rollback action:
  Approver:

Validation:
  [ ] Binary versions correct
  [ ] FCV expected
  [ ] Replica/shard health stable
  [ ] API smoke tests passed
  [ ] Latency/error guardrails met
  [ ] CDC/Search verified
  [ ] Backup/restore path checked

Decision:
  GO / HOLD / ROLLBACK / RECOVER

Closure:
  Owner sign-off:
  Post-upgrade monitoring:
  Incident findings:
```

### 36.1. Không ghi secrets trong runbook

Runbook nên trỏ tới nơi lưu secrets đã được phê duyệt, không chứa password/TLS private key/Atlas API key.

### 36.2. Mọi bước cần stop condition

Ví dụ:

```text
If secondary does not return to SECONDARY
or replication lag exceeds approved threshold
within the declared observation window:
  STOP before touching next member.
```

Không dùng một checklist dạng “nâng từng node” mà không có tiêu chí quyết định có được nâng node tiếp theo hay không.

## 37. Go/No-Go matrix

| Hạng mục | PASS khi nào? | NO-GO khi nào? |
|---|---|---|
| Upgrade path | Có hướng dẫn chính thức cho từng chặng | Không xác nhận được đường hỗ trợ |
| FCV | Có preconditions và gate riêng | FCV hiện tại không đáp ứng |
| Compatibility | Driver/OS/tools được hỗ trợ | Thành phần quan trọng không tương thích |
| Backup | Restore point phù hợp, integrity được xác minh | Backup thiếu hoặc lỗi |
| Restore | Restore drill đạt RPO/RTO | Chưa thử hoặc thất bại |
| Data integrity | Regression/data checks đạt | Sai/lost data |
| Performance | SLO/guardrails đạt | Tail latency hoặc throughput vượt ngưỡng |
| Replica/sharding | Health/failover tests đạt | Quorum/lag/topology lỗi |
| Security | Auth/TLS/KMS/RBAC hoạt động | Mất encryption/quyền sai |
| CDC/Search | Consumers/indexes hoạt động | Mất event/search availability nghiêm trọng |
| Rollback | Có phương án phù hợp, diễn tập được | Không có đường khôi phục khả thi |
| Ownership | Có người duyệt và trực | Không có người chịu trách nhiệm |

Một dòng `UNKNOWN` trong thành phần quan trọng không nên được coi như PASS để đủ số lượng ô xanh.

### 37.1. Ngoại lệ có kiểm soát

Đôi khi có rủi ro nhỏ được chấp nhận tạm thời. Ngoại lệ cần:

- Mô tả rõ;
- Owner;
- Risk assessment;
- Compensating controls;
- Expiration date;
- Approval đúng thẩm quyền.

Không dùng ngoại lệ không thời hạn để bỏ qua backup/recoverability hoặc lỗ hổng bảo mật nghiêm trọng.

## 38. Kịch bản thất bại và phương án ứng phó

### 38.1. Một secondary không bắt kịp

Triệu chứng:

```text
Secondary restarted on target binary
  ↓
Replication lag increases
  ↓
Node remains RECOVERING
```

Hành động:

1. Dừng trước khi nâng node khác.
2. Kiểm tra logs, network, disk, FCV và compatibility.
3. Xác minh quorum còn đủ.
4. Đối chiếu official procedure;
5. Chỉ khôi phục/nâng tiếp sau khi có quyết định.

### 38.2. Driver kết nối thất bại sau binary upgrade

Triệu chứng:

```text
Server healthy
Application sees server selection timeout / TLS handshake error
```

Kiểm tra:

- Driver/version compatibility;
- TLS CA/certificate SAN;
- Authentication mechanism;
- DNS/seed list;
- Network/firewall;
- Topology discovery;
- Connection pool behavior.

**Không tắt TLS verification** để chữa lỗi kết nối.

### 38.3. Read p99 tăng, writes vẫn bình thường

Kiểm tra:

- Query plans thay đổi;
- Index/collation;
- Cache cold/warm;
- Disk I/O;
- Aggregation stages;
- Application concurrency;
- Pool waits;
- Background index builds.

Không vội rollback server nếu nguyên nhân là cấu hình pool hoặc một query mới được deploy song song; cần evidence.

### 38.4. Write p99 tăng sau FCV

Kiểm tra:

- Replication lag;
- Storage/cache;
- Transaction/workload;
- Index maintenance;
- Write concern;
- Background operations;
- Known release notes.

Nếu ngưỡng dừng bị vượt, thực hiện **rollback/recovery path được hỗ trợ**, không thử hạ FCV tùy hứng.

### 38.5. Backup agent thất bại sau nâng cấp

Đây có thể là blocker để đóng change. Kiểm tra backup tool compatibility, credentials, storage/KMS, APIs và chạy lại restore drill khi cần.

### 38.6. Search queries không tìm thấy dữ liệu vừa ghi

Search index đồng bộ bất đồng bộ. Kiểm tra index status, lag, `mongot`/Search Nodes, mapping và quyền. Không kết luận source data lost chỉ từ Search result rỗng.

## 39. Các anti-pattern nguy hiểm

| Anti-pattern | Rủi ro | Cách đúng |
|---|---|---|
| Upgrade không backup | Không có đường restore | Backup + restore drill |
| Backup job SUCCESS là đủ | Artifact có thể không restore | Đo RPO/RTO thực |
| Không biết FCV hiện tại | Sai preconditions | Inventory FCV |
| Skip major versions tùy ý | Đường không được hỗ trợ | Theo official upgrade path |
| Upgrade all replica members cùng lúc | Mất quorum | Rolling procedure |
| Upgrade sharded components ngẫu nhiên | Routing/metadata không tương thích | Version-specific order |
| Nâng FCV ngay sau startup | Hạn chế rollback | Validation gate |
| Dùng binary cũ để mở data mới tùy tiện | Hỏng dữ liệu/incompatibility | Downgrade procedure |
| Coi rollback app = rollback DB | Schema/FCV mismatch | Kế hoạch tách biệt |
| Không thử change streams | Consumers mất events | Resume/retry tests |
| Không thử transactions/failover | Duplicate/missing writes | Fault-injection staging |
| Test chỉ 1000 docs | Không đại diện | Dataset đủ và data skew |
| Test chỉ `ping` | Không chứng minh workload | Functional/regression/load |
| Không đo p95/p99 | Bỏ qua tail regression | Metrics/tracing |
| Thay schema, driver, server cùng lúc | Khó cô lập lỗi | Tách pha |
| Bỏ TLS verification khi lỗi | Rủi ro MITM | Sửa CA/cert/DNS |
| Không kiểm KMS | Restore/encryption có thể thất bại | Key recovery drill |
| Bỏ qua Search/Vector | Search outage/index rebuild | Feature-specific tests |
| Không có owner on-call | Không phản ứng kịp | Runbook và trực |
| Không có stop criteria | Tiếp tục khi cluster đang lỗi | Gates/hold conditions |
| Dựa vào staging khác topology | Không thấy sharding/failover risk | Production-like staging |
| Benchmark lúc cache nóng duy nhất | Giấu cold-start regression | Warm/cold/mixed tests |
| Khôi phục không thử quyền | Có thể rò dữ liệu | Auth/RBAC smoke |
| Không xem release notes | Bỏ qua deprecations | Compatibility matrix |
| Coi Atlas managed là không cần test | App/data vẫn có rủi ro | Shared-responsibility review |

## 40. Bài tập thực hành

### Bài 1 — Phân loại thay đổi

Một dự án cùng lúc định:

- Nâng MongoDB major version;
- Nâng Java Driver;
- Thay TLS CA;
- Đổi index cho `orders`;
- Chuyển Atlas region.

Hãy phân loại rủi ro của từng thay đổi và đề xuất thứ tự tách pha, kế hoạch test và các mốc rollback.

### Bài 2 — Kiểm tra inventory

Cho thông tin:

```text
Primary MongoDB: A
Secondary 1: A
Secondary 2: A
FCV: Unknown
Java Driver: X
Backup agent: Y
CDC connector: Z
```

1. Có đủ thông tin để nâng cấp chưa?
2. Cần kiểm tra thêm những components nào?
3. Vì sao FCV không thể để Unknown?
4. Nguồn evidence nào phù hợp?
5. Có thể quyết định dựa vào `db.version()` trên primary thôi không?

### Bài 3 — Compatibility matrix

Tạo bảng gồm MongoDB Server, FCV, Java Driver, Spring Data, OS, backup tools, TLS/auth và Search. Với mỗi hàng ghi current/target/source docs/PASS/FAIL/UNKNOWN.

Giải thích vì sao một dòng Unknown quan trọng có thể dẫn tới NO-GO.

### Bài 4 — Backup và RPO

Một hệ thống:

```text
RPO = 15 phút
RTO = 2 giờ
Backup mỗi đêm
Không có PITR
```

1. Có chứng minh được RPO không?
2. Cần loại backup/continuous recovery nào?
3. Sự khác biệt giữa replica set và backup?
4. Vì sao backup file tồn tại chưa đủ?
5. Khi mã hóa, key recovery quan trọng thế nào?

### Bài 5 — Restore drill

Thiết kế một lần restore trước upgrade:

1. Chọn backup ID và target;
2. Bảo vệ dữ liệu staging;
3. Restore source;
4. Verify collections/indexes;
5. Run business smoke tests;
6. Đo RPO/RTO;
7. Lưu evidence/approval.

### Bài 6 — FCV và binary

Giải thích:

```text
Binaries đã nâng target version
FCV vẫn giữ old value
```

1. Tại sao có giai đoạn này?
2. Khi nào được nâng FCV?
3. Downgrade FCV có bảo đảm downgrade binary không?
4. Có thể dùng feature mới trước gate không?
5. Những bằng chứng nào cần có?

### Bài 7 — Rolling replica set

Replica set có P, S1 và S2.

1. Đề xuất thứ tự khái quát nâng members theo guide phù hợp.
2. Sau khi nâng S1, cần kiểm tra gì?
3. Điều gì xảy ra khi restart cả P/S1/S2 cùng lúc?
4. Driver xử lý election thế nào?
5. Viết stop criteria khi replication lag cao.

### Bài 8 — Sharded cluster

Có `mongos` x3, config server replica set và 4 shard replica sets.

1. Vì sao không áp trình tự replica set đơn lẻ cho toàn hệ?
2. Những thành phần nào cần inventory?
3. Balancer/chunk migration cần chú ý gì?
4. Query targeting và cross-shard transaction test ra sao?
5. Có cần kiểm tra cả ba `mongos` không?

### Bài 9 — Driver test

Một Java app kết nối target MongoDB và `ping` trả OK.

1. Có đủ để kết luận tương thích không?
2. Thử BSON types nào?
3. Thử transactions/change streams/retries ra sao?
4. Stable API giải quyết phần nào?
5. Framework/ODM có vai trò gì?

### Bài 10 — Query plan regression

Trước nâng cấp:

```text
Read p95 = 40 ms
Docs examined = 25
```

Sau nâng cấp:

```text
Read p95 = 350 ms
Docs examined = 150000
```

1. Nghi ngờ điều gì?
2. Kiểm tra indexes/collation/query shapes thế nào?
3. So `explain` ra sao?
4. Có nên ép `hint` ngay trong production không?
5. Khi nào HOLD hoặc rollback?

### Bài 11 — Bảo mật TLS

Sau upgrade, Java service chỉ kết nối khi bật:

```text
tlsAllowInvalidHostnames=true
```

1. Vì sao đây là blocker?
2. Cần kiểm tra CA/SAN/DNS gì?
3. Có thể xử lý bằng nâng driver/truststore không?
4. Tại sao không để cấu hình insecure trong release?
5. Làm sao test rotation trước?

### Bài 12 — CDC resume

Một change stream consumer bị ngừng 3 giờ trong khi oplog window còn 2 giờ.

1. Có thể resume tự động theo token không?
2. Cần phương án resnapshot/reconciliation nào?
3. Làm sao tránh duplicate processing?
4. Metric nào cần monitor?
5. Vì sao cần test consumer ngoài API chính?

### Bài 13 — Search/Vector readiness

MongoDB `find()` hoạt động sau nâng cấp, nhưng `$vectorSearch` báo index unavailable.

1. Source data có nhất thiết mất không?
2. Cần kiểm tra Search index status gì?
3. Có cần kiểm tra model dimensions/mapping không?
4. API fallback thế nào?
5. Vì sao phải đo indexing lag?

### Bài 14 — Performance plan

Thiết kế benchmark với:

```text
Dataset: 10 triệu documents
Traffic: 70% read, 25% write, 5% aggregation
Peak: 1500 operations/s
Target: p95 read < 100 ms, p95 write < 120 ms
```

Xác định warm-up, peak duration, data skew, measurements và stop criteria.

### Bài 15 — Rollback kế hoạch

Giả sử app mới và MongoDB mới đã được đưa vào production, sau đó một schema change chỉ app mới hiểu.

1. Có thể đơn giản deploy app cũ không?
2. Downgrade server có được bảo đảm không?
3. Restore snapshot trước nâng cấp có thể làm mất writes nào?
4. Cần dữ liệu/replay/reconciliation thế nào?
5. Khi nào nên dùng expand-and-contract?

### Bài 16 — Go/No-Go

Một checklist:

```text
Compatibility matrix: PASS
Staging functional tests: PASS
Staging load tests: PASS
Backup: SUCCESS
Restore drill: NOT DONE
Rollback procedure: UNKNOWN
On-call owner: READY
```

1. Quyết định GO hay NO-GO?
2. Vì sao backup SUCCESS chưa đủ?
3. Cần làm gì để chuyển status?
4. Ai có quyền chấp nhận rủi ro?
5. Ghi evidence thế nào?

### Bài 17 — Release runbook

Soạn runbook gồm:

- Source/target versions và FCV;
- Nodes/components;
- Backup ID/recovery point;
- Official upgrade procedure links;
- Thứ tự nâng;
- Dấu hiệu PASS mỗi bước;
- Stop conditions;
- Rollback/recovery;
- Monitoring/alert;
- Owners/approvals.

### Bài 18 — Post-upgrade validation

Một ngày sau nâng cấp, API bình thường nhưng backup agent liên tục thất bại.

1. Có được đóng change không?
2. Những chỉ số phục hồi nào bị tác động?
3. Cần xử lý compatibility thế nào?
4. Có cần restore drill lại không?
5. Cách theo dõi cho đến khi hệ ổn định?

## 41. Checklist đầy đủ trước nâng cấp

### Inventory và tương thích

- [ ] Biết current/target MongoDB Server version trên mọi thành phần.
- [ ] Đã ghi đúng FCV hiện tại và FCV target.
- [ ] Có đường nâng cấp chính thức cho từng chặng.
- [ ] Đã đọc release notes và known issues.
- [ ] Đã kiểm tra OS/CPU/container support.
- [ ] Driver/ODM/framework tương thích.
- [ ] MongoDB Tools/backup/monitoring versions tương thích.
- [ ] TLS/auth/KMS/Queryable Encryption tương thích.
- [ ] Search/Vector/CDC consumers được đưa vào phạm vi.
- [ ] Có topology inventory cho replica set/sharded cluster.

### Backup và restore

- [ ] Backup gần nhất thành công theo policy.
- [ ] Đã xác định recovery point phù hợp.
- [ ] PITR/oplog coverage đáp ứng RPO.
- [ ] Backup encryption/keys được xác minh.
- [ ] Backup độc lập failure domain chính nếu yêu cầu.
- [ ] Restore drill đã hoàn tất.
- [ ] Data integrity kiểm tra sau restore.
- [ ] RPO/RTO được đo và được phê duyệt.
- [ ] Có restore target/capacity/credentials sẵn sàng.
- [ ] Có chính sách bảo vệ dữ liệu phục hồi.

### Thử nghiệm và vận hành

- [ ] Staging đủ đại diện topology/data/workload.
- [ ] Functional/regression tests đạt.
- [ ] Business invariants/tenant ACL tests đạt.
- [ ] Transactions/retry/failover tests đạt.
- [ ] CDC resume tests đạt.
- [ ] Search/Vector query/index tests đạt nếu có.
- [ ] Read/write p95/p99 và errors trong budget.
- [ ] Resource/capacity headroom đủ.
- [ ] Có change window và freeze scope.
- [ ] Có rollback/recovery đã thử theo khả năng.
- [ ] Có stop criteria và người ra quyết định.
- [ ] Có alert/on-call và communication channel.
- [ ] Chỉ nâng FCV tại gate được phê duyệt.
- [ ] Có post-upgrade monitoring và closure criteria.

## 42. Tài liệu chính thức tham khảo

Đối với **một cuộc nâng cấp thật**, phải dùng tài liệu chính thức cho **đúng MongoDB release đích, source version và deployment topology**, không chỉ dùng các nguyên tắc tổng quát của bài này.

- [MongoDB Upgrade Procedures](https://www.mongodb.com/docs/manual/release-notes/upgrade/)
- [MongoDB Release Notes](https://www.mongodb.com/docs/manual/release-notes/)
- [MongoDB Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB `getParameter`](https://www.mongodb.com/docs/manual/reference/command/getParameter/)
- [MongoDB Compatibility Changes](https://www.mongodb.com/docs/manual/release-notes/)
- [MongoDB Platform Support](https://www.mongodb.com/docs/manual/administration/production-notes/)
- [MongoDB Drivers](https://www.mongodb.com/docs/drivers/)
- [MongoDB Stable API](https://www.mongodb.com/docs/manual/reference/stable-api/)
- [MongoDB Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB `mongodump`](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB `mongorestore`](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Atlas Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/)
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitoring-alerts/)
- [MongoDB Replica Set Administration](https://www.mongodb.com/docs/manual/administration/replica-set-deployment/)
- [MongoDB Sharded Cluster Administration](https://www.mongodb.com/docs/manual/administration/sharded-cluster-administration/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Query Plans and Explain](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Search](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)

## Kết luận

**Chuẩn bị nâng cấp MongoDB** là công việc bảo vệ **tính đúng đắn, khả năng phục vụ và khả năng khôi phục** của toàn hệ thống, không chỉ cài đặt một binary mới.

Một kế hoạch an toàn phải bắt đầu bằng **inventory và baseline**: biết rõ MongoDB Server, FCV, topology, drivers, frameworks, OS, indexes, backup agents, Search/Vector Search, CDC và những query shapes quan trọng. Từ đó xây dựng **ma trận tương thích có nguồn và ngày kiểm chứng**, xác nhận đường nâng cấp chính thức cùng thứ tự từng thành phần.

**Bản sao lưu** chỉ thực sự có giá trị khi tổ chức đã **restore thử**, đo được RPO/RTO, xác minh data integrity và có đủ encryption keys, quyền truy cập và capacity để phục hồi. **Rollback ứng dụng, downgrade MongoDB và restore backup** là ba chiến lược khác nhau, có giới hạn và rủi ro riêng; không thể coi “có snapshot” là bảo đảm quay lại không mất dữ liệu.

Cuối cùng, phải **thử trên môi trường gần production** với dữ liệu và workload đại diện: CRUD, aggregation, indexes, transactions, change streams, Search/Vector Search, authentication/TLS, failover và latency p95/p99. Trước mỗi bước production, có **GO/NO-GO gate**, người phụ trách, quan sát liên tục và tiêu chí dừng rõ ràng. Đặc biệt, **không nâng FCV hoặc kích hoạt tính năng mới chỉ vì binaries đã khởi động**, khi chưa hoàn tất xác minh và quyết định về khả năng khôi phục.

**Một cuộc nâng cấp thành công không được định nghĩa bằng việc server in ra số phiên bản mới. Nó thành công khi dữ liệu vẫn đúng, người dùng vẫn được phục vụ theo SLO, hệ thống tiếp tục được sao lưu, và đội vận hành biết chính xác phải làm gì nếu bất kỳ bước nào thất bại.**

