# Sao lưu replica set, sharded cluster và dịch vụ Atlas trong MongoDB

Một ứng dụng xử lý đơn hàng có thể mất dữ liệu vì xóa nhầm collection, lỗi phiên bản mới, thao tác migration sai, hỏng ổ đĩa hoặc mất toàn bộ vùng hạ tầng. MongoDB replica set cung cấp high availability khi một vài thành viên gặp sự cố, nhưng **replication không phải backup**: lệnh xóa nhầm hợp lệ cũng được sao chép sang các secondaries. Sharding mở rộng khả năng lưu trữ và xử lý, nhưng không tự biến snapshots riêng lẻ của các shards thành một bản khôi phục nhất quán. MongoDB Atlas có khả năng backup được quản lý, song tính năng cụ thể và chế độ khôi phục phụ thuộc tier, cloud provider, vùng triển khai và cấu hình backup.

**Backup** là tạo bản dữ liệu có thể sử dụng để phục hồi. **Restore** là tái lập dữ liệu từ bản đó, kiểm tra tính toàn vẹn và đưa dịch vụ về trạng thái hoạt động. Một file backup tồn tại không chứng minh rằng quá trình restore sẽ thành công hoặc đạt mức mất dữ liệu/thời gian ngừng dịch vụ mà doanh nghiệp chấp nhận.

Bài thuộc chương **Sao lưu và phục hồi** của module *Database Engine Document MongoDB*, gồm ba nhóm chính:

- **Replica set:** `mongodump`, `--oplog`, `mongorestore --oplogReplay`, backup vật lý và snapshot storage.
- **Sharded cluster:** dữ liệu trên nhiều shards, config server metadata, balancer, DDL, consistent point và restore orchestration.
- **MongoDB Atlas:** Cloud Backup snapshots, continuous backup/PITR khi được hỗ trợ, backup policy, chọn restore target và diễn tập.

Các hostname, đường dẫn và tài khoản trong bài là **giả lập**; thao tác restore và thay đổi backup policy chỉ nên chạy trong lab/target được phép. Database Tools, MongoDB server, Atlas và hệ thống cloud có những khác biệt phiên bản: cần đối chiếu tài liệu/version cụ thể trước khi áp dụng production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt replication, backup, snapshot, archive, high availability và disaster recovery.
2. Thiết lập **Recovery Point Objective (RPO)** và **Recovery Time Objective (RTO)**.
3. So sánh logical dump, physical snapshots, incremental/continuous backup.
4. Dùng `mongodump --oplog` đúng phạm vi cho replica set và nhận diện các giới hạn.
5. Khôi phục full dump vào môi trường cô lập qua `mongorestore --oplogReplay`.
6. Hiểu oplog window, replication lag và dữ liệu có thể mất khi backup secondary.
7. Giải thích vì sao cần storage/journal snapshot nhất quán với WiredTiger.
8. Lập kế hoạch backup **cluster-aware** cho sharded cluster, gồm config servers.
9. Nhận biết nguy cơ chunk/range migrations, metadata/DDL và snapshots khác thời điểm.
10. Phân biệt Atlas snapshots và PITR theo khả năng tier/cấu hình đang dùng.
11. Chọn thời điểm khôi phục trước sự cố, đánh giá tác động lên writes hợp lệ sau mốc đó.
12. Thiết kế retention, encryption, least privilege, backup inventory, audit và offsite copies.
13. Kiểm tra restore bằng document counts, indexes, business invariants và ứng dụng.
14. Xây dựng DR runbook, giám sát backup và diễn tập RPO/RTO thực tế.

## 2. Vì sao replication không phải backup?

Replica set gồm primary và các secondaries cùng lưu các bản sao dữ liệu theo oplog. Điều đó giúp failover khi một máy hoặc process gặp lỗi. Nhưng nếu tài khoản có quyền chạy:

~~~javascript
// Ví dụ thao tác nguy hiểm, KHÔNG chạy trên dữ liệu thật:
db.orders.deleteMany({})
~~~

thì secondary cũng áp dụng thao tác xóa. Sau khi dữ liệu sai đã được replicate tới mọi member, thêm một secondary **không tạo ra dữ liệu sạch từ hôm qua**.

| Sự cố | Replica set giúp gì? | Backup giúp gì? |
|---|---|---|
| Một node đột ngột hỏng | Có thể bầu primary mới khi đủ majority | Khôi phục trong tình huống tổn thất rộng hơn |
| Primary mất disk | Có thể tiếp tục từ secondary | Phòng các bản sao cùng gặp lỗi |
| Xóa nhầm collection | Xóa sẽ được replicate | Quay về bản trước thao tác |
| Migration cập nhật sai | Writes sai vẫn được replicate | Khôi phục snapshot/PITR sạch |
| Ransomware có quyền admin | Có thể ảnh hưởng toàn bộ nodes | Backup độc lập/immutable giảm ảnh hưởng |
| Mất cả region | HA trong một region có thể không đủ | Offsite/cross-region DR phù hợp |

**High availability** hướng tới tiếp tục phục vụ. **Backup/DR** hướng tới khôi phục dữ liệu hợp lệ khi trạng thái hiện tại không đáng tin.

## 3. RPO và RTO quyết định kiến trúc

### 3.1. RPO: có thể mất tối đa bao nhiêu dữ liệu?

RPO mô tả khoảng mất dữ liệu tối đa chấp nhận được, thường tính bằng thời gian. Nếu backup hợp lệ gần nhất cách sự cố 24 giờ, thực tế có thể mất gần 24 giờ thay đổi. Đối với hệ thống yêu cầu RPO 5 phút, chỉ chụp snapshot hằng ngày không đủ, trừ khi có cơ chế liên tục ghi nhận thay đổi và restore theo thời điểm.

### 3.2. RTO: dịch vụ được phép ngừng bao lâu?

RTO gồm thời gian phát hiện, ra quyết định, cấp cluster đích, chuyển dữ liệu, rebuild indexes, kiểm chứng và chuyển traffic. Một công cụ có thể báo “restore completed” nhưng ứng dụng vẫn chưa kết nối được vì TLS, roles hoặc network.

### 3.3. Ví dụ phân loại

| Nhóm dữ liệu | RPO minh họa | RTO minh họa | Phương án cần đánh giá |
|---|---:|---:|---|
| Báo cáo tái tạo được | 24 giờ | 8 giờ | Snapshot định kỳ |
| Hệ thống đơn hàng | 5 phút | 1 giờ | Continuous backup/PITR |
| Audit quan trọng | Gần 0 theo policy | 4 giờ | Giải pháp durability và recovery chuyên biệt |

Các mốc trên chỉ là **ví dụ yêu cầu nghiệp vụ**, không phải SLA mặc định của MongoDB/Atlas.

### 3.4. Phạm vi restore phải xác định trước

Bạn đang muốn:

- Khôi phục toàn bộ replica set?
- Khôi phục sharded cluster về cùng một logical point?
- Chỉ lấy lại collection `orders`?
- Chỉ lấy lại 25 documents bị xóa nhầm?
- Dựng cluster riêng để điều tra trước khi copy dữ liệu?

Backup toàn cluster có thể không cho phép restore chọn vài documents trực tiếp. Khi đó thường restore vào một môi trường riêng rồi xuất/merge chọn lọc.

## 4. Ba nhóm backup quan trọng

| Nhóm | Cách tạo | Ưu điểm | Giới hạn |
|---|---|---|---|
| **Logical backup** | Đọc documents/index metadata qua MongoDB API, ví dụ `mongodump` | Portable, dễ thao tác namespace, file BSON/archive | Có thể chậm và cần cơ chế consistency khi writes liên tục |
| **Physical snapshot** | Snapshot database files/journal ở storage layer | Hiệu quả trên dữ liệu lớn; restore có thể nhanh | Cần quiesce/snapshot consistency và version-compatible storage |
| **Managed/continuous backup** | Dịch vụ backup chụp snapshots và lưu thay đổi | Automation, retention, PITR nếu có | Phụ thuộc gói, chi phí, khả năng restore và khóa mã hóa |

### 4.1. Full, incremental và continuous

**Full** là một bản sao phạm vi được chọn. **Incremental** giữ các thay đổi so với mốc nền; **continuous** ghi nhận thay đổi đủ thường xuyên để khôi phục đến những thời điểm nằm trong cửa sổ được hỗ trợ. Không tự giả định một bản logical full dump đã có PITR kéo dài cả tuần.

### 4.2. Backup không đồng nghĩa export CSV

Xuất CSV/JSON có thể phục vụ phân tích hoặc chuyển dữ liệu, nhưng thường không giữ toàn bộ BSON types, indexes, users/roles, metadata hoặc transaction-consistent state. Cần chọn phương pháp theo mục đích phục hồi, không chỉ khả năng xuất files.

## 5. Oplog và nhất quán thời điểm trong replica set

Replica set ghi thao tác replication vào **oplog** (thường là `local.oplog.rs`). Secondary đọc và áp dụng các records này. Khi một dump kéo dài nhiều phút, database có thể thay đổi trong lúc các collections được quét.

~~~text
10:00: orders có đơn hàng PENDING
10:01: dump đọc orders
10:02: transaction đổi order thành PAID
10:03: transaction ghi payment
10:04: dump đọc payments
~~~

Nếu backup lấy hai collections tại hai thời điểm khác nhau mà không tạo consistent point, bản phục hồi có thể có order ở trạng thái PENDING nhưng payment đã tồn tại.

### 5.1. Tác dụng của `--oplog`

Với **full backup phù hợp trên replica set**, `mongodump --oplog` ghi thêm những oplog entries xảy ra trong khoảng dump, cho phép `mongorestore --oplogReplay` áp chúng khi restore theo cơ chế công cụ. Mục tiêu là đưa dữ liệu đã dump về một điểm nhất quán theo phạm vi được hỗ trợ.

### 5.2. Oplog window

Oplog không lưu lịch sử vô hạn. Các entries cũ bị cuốn đi khi oplog vượt dung lượng/cửa sổ. Nếu dump quá lâu hoặc write rate quá cao, dữ liệu oplog cần thiết có thể không còn đủ. Cần giám sát độ dài oplog window, thời gian dump, tốc độ writes và lỗi liên quan.

### 5.3. Oplog không tự biến thành PITR dài hạn

Để khôi phục từ snapshot 01:00 đến 10:35, cần lưu liên tục các thay đổi từ snapshot tới thời điểm mục tiêu bên ngoài live oplog theo một cơ chế đáng tin, có checkpoint/ordering/transaction semantics. Một lần chạy `--oplog` chỉ thu khoảng lịch sử liên quan đến **lần dump đó**.

## 6. Chạy `mongodump --oplog` cho full replica set

Ví dụ trong môi trường tự quản:

~~~bash
# Chạy cho replica set được cấp phép. Không nhúng password vào URI.
mongodump \
  --uri="mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/?replicaSet=rs0&tls=true" \
  --tlsCAFile=/etc/mongodb/tls/ca-chain.pem \
  --username=backupOperator \
  --authenticationDatabase=admin \
  --oplog \
  --gzip \
  --archive=/backups/rs0-full-2026-11-14.archive.gz
~~~

Giải nghĩa:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--uri` | Topology replica set + TLS |
| `--tlsCAFile` | Xác thực certificate của các MongoDB endpoints |
| `--username`, `--authenticationDatabase` | Danh tính có quyền backup |
| `--oplog` | Thu oplog liên quan đến full dump |
| `--gzip` | Nén output |
| `--archive` | Ghi backup dưới dạng một archive thay vì nhiều files |

### 6.1. Những giới hạn bắt buộc nhớ

- `--oplog` áp dụng cho **full dump theo phạm vi được hỗ trợ** của replica set, không kết hợp tùy ý với `--db`, `--collection`, `--query` hoặc các bộ lọc không tương thích.
- Không dùng `mongodump --oplog` thông qua `mongos` để khẳng định có backup nhất quán **toàn sharded cluster**.
- Không dùng trên standalone không có replica set oplog như với replica set.
- Không biến thành PITR tuỳ thời điểm ngoài những oplog entries thực sự được lưu.
- Không thay thế kiểm tra tool version, privileges, output integrity và restore test.

### 6.2. Tài khoản backup

MongoDB có built-in role `backup` phục vụ nhiều tác vụ backup, nhưng yêu cầu quyền cụ thể có thể khác theo namespace, chế độ backup, server/tool version. Dùng tài khoản riêng, least privilege; không dùng user ứng dụng `readWrite` hoặc root admin một cách mặc định.

### 6.3. TLS và bảo vệ secret

Sử dụng TLS và kiểm tra CA/SAN. Không đưa password thật vào URI hiển thị trong logs, cron, shell history. Cấp credentials bằng secret manager/prompt theo cơ chế công cụ. File archive cũng phải được mã hóa và phân quyền: `--gzip` **không phải encryption**.

### 6.4. Kết quả backup phải có exit code

Không coi archive tồn tại và có dung lượng là backup thành công. Job cần ghi exit code, stdout/stderr có lọc secrets, thời điểm bắt đầu/kết thúc, bytes written, upload storage status và integrity checksum.

## 7. Sao lưu từ secondary: lợi và hại

Một primary phục vụ writes có thể bị tăng CPU/disk/network nếu dump lớn. Backup từ secondary hoặc dedicated secondary có thể giảm tải primary, nhưng có đánh đổi:

- Secondary có thể **replication lag**, nên điểm dữ liệu phục hồi không phải lúc mới nhất của primary.
- Một secondary không ổn định có thể bị rollback.
- Disk/CPU load của backup có thể làm secondary áp oplog chậm hơn.
- Oplog window và tính nhất quán vẫn cần được kiểm tra.
- Read preference của tool/driver phải phù hợp topology.

### 7.1. Hidden/priority 0 secondary

Một dedicated hidden secondary có thể tách backup workload khỏi truy vấn ứng dụng nếu thiết kế đúng, nhưng vẫn cần replication health, storage và monitoring. Nó **không phải backup vĩnh viễn**: sai thao tác vẫn được replicate.

### 7.2. Backup source checklist

Trước khi chạy trên một member, xem `rs.status()`, replication lag, disk capacity, write throughput và mức tài nguyên. Không lock/restart nhiều voting members khiến replica set mất majority.

## 8. Metadata và manifest của backup

Một backup tốt nên đi kèm manifest được tạo bởi job, ví dụ:

~~~yaml
backupId: rs0-20261114-013000
topology: replicaSet
replicaSetName: rs0
sourceMongoVersion: "recorded-by-job"
sourceFCV: "recorded-by-job"
databaseToolsVersion: "recorded-by-job"
method: mongodump-oplog
startedAt: "2026-11-14T01:30:00Z"
completedAt: "2026-11-14T01:48:00Z"
archiveUri: secure-storage/rs0-full-2026-11-14.archive.gz
archiveSizeBytes: "measured"
sha256: "computed"
jobStatus: SUCCEEDED
restoreDrillStatus: PENDING
~~~

Đây là **mẫu dữ liệu**, không phải checksum thật. Một bản backup phải có ID duy nhất, nguồn rõ, tool/server versions, thời gian, phương thức, trạng thái và checksum đã tính thật. Manifest cũng cần ghi storage region, encryption key reference và retention theo chính sách.

### 8.1. SHA-256 của archive

Hash giúp phát hiện archive bị sửa/hỏng sau khi tính. Tuy nhiên, hash đúng **không chứng minh** backup có đầy đủ documents và có thể restore. Restore drill và business validation vẫn bắt buộc.

### 8.2. Upload offsite

Nếu backup được tạo trên disk của cùng máy chủ database, hỏng disk hoặc mất hạ tầng có thể phá cả nguồn và backup. Copy sang một storage location độc lập với quyền hạn/retention phù hợp.

## 9. Restore full dump với `mongorestore --oplogReplay`

Khôi phục nên bắt đầu ở **target mới, cô lập và trống**, không phải cluster production có dữ liệu đang chạy.

~~~bash
# Chạy trên target lab/isolated đã xác minh; không chỉ vào production.
mongorestore \
  --uri="mongodb://restore1.lab.internal:27017/?tls=true" \
  --tlsCAFile=/etc/mongodb/tls/lab-ca.pem \
  --username=restoreOperator \
  --authenticationDatabase=admin \
  --gzip \
  --archive=/backups/rs0-full-2026-11-14.archive.gz \
  --oplogReplay
~~~

`--oplogReplay` đọc dữ liệu oplog có trong backup được tạo với `--oplog` và áp theo cơ chế của Database Tools. Đây là thao tác cho **target được chuẩn bị hợp lệ**, không phải lệnh “khôi phục mọi cluster hiện tại” không cần xác minh.

### 9.1. Đừng dùng `--drop` không chủ ý

`mongorestore --drop` có thể xóa các collections trên target trước khi restore. Đây là hành động phá dữ liệu nếu target đang có business writes. Với DR drill, chuẩn bị target sạch để giảm rủi ro; với target có dữ liệu, phải có kế hoạch conflict/overwrite/phê duyệt riêng.

### 9.2. Khôi phục users/roles

Backup và restore system databases/users/roles có thể yêu cầu privileges khác và chịu các giới hạn tool options. Tài khoản có `readWrite` vào `shop` thường không đủ restore mọi users/roles. Kiểm tra quyền cần thiết, authSource và quy tắc restore metadata cho deployment thực tế.

### 9.3. Index rebuild cũng là restore

Logical restore có thể cần ghi hàng triệu documents và xây lại indexes. Với dataset lớn, index build và I/O có thể chiếm nhiều thời gian; RTO phải tính đến bước này, kiểm tra consistency và application cutover.

### 9.4. Không dùng `--oplogReplay` như replay toàn lịch sử

Nếu file backup có oplog của khoảng dump 01:30–01:48, công cụ không tự có events đến 10:35 khi bạn restore lúc 11:00. Muốn PITR xa hơn cần continuous backup lưu đủ changes và khả năng replay theo mốc.

## 10. Dump một collection có khác backup toàn replica set?

Ví dụ xuất `orders`:

~~~bash
mongodump \
  --uri="mongodb://mongo1.db.internal:27017/?tls=true" \
  --tlsCAFile=/etc/mongodb/tls/ca-chain.pem \
  --username=backupOperator \
  --authenticationDatabase=admin \
  --db=shop \
  --collection=orders \
  --archive=/backups/shop-orders.archive
~~~

Lệnh này có thể hữu ích cho export, investigation hoặc migration collection. Nhưng không thể tuyên bố `orders`, `payments` và `inventory` cùng một consistent transaction point nếu những collections khác đang thay đổi và không có cơ chế đồng bộ.

### 10.1. Khi chỉ vài documents bị xóa nhầm

Một hướng ít rủi ro:

1. Restore full backup/PITR đến thời điểm sạch vào target riêng.
2. Trích xuất đúng documents cần phục hồi, giữ BSON types và identity.
3. So sánh với documents hiện tại (có thể đã được sửa hợp lệ sau lỗi).
4. Merge có kiểm soát theo business rules và audit.

Không thay cả production bằng snapshot cũ nếu chỉ một phần dữ liệu bị ảnh hưởng và có thể khôi phục chọn lọc.

## 11. Physical snapshots và WiredTiger

Physical backup sao chép database files và journal cần thiết tại một **storage consistency point**. Với WiredTiger, phải đáp ứng quy tắc checkpoint, journaling, lock và atomic snapshots của storage engine/hệ thống đĩa.

### 11.1. Sao chép folder khi đang ghi là sai

~~~text
KHÔNG được coi lệnh sao chép từng file đang thay đổi:
cp -r /var/lib/mongodb /backup
là một physical snapshot nhất quán.
~~~

Các files có thể được copy ở những thời điểm khác nhau, trong khi WiredTiger metadata/journal thay đổi đồng thời. Snapshot đúng cần tính nhất quán của **toàn bộ volumes/files liên quan**.

### 11.2. Quy trình ở mức khái niệm

1. Chọn member phù hợp, kiểm tra replication lag/health.
2. Xác định storage backend và hỗ trợ atomic/coordinated snapshots.
3. Dùng cơ chế checkpoint/fsync/freeze được MongoDB + storage vendor khuyến nghị cho phiên bản đang dùng.
4. Snapshot tất cả dữ liệu/journal volumes cùng một mốc.
5. Bỏ trạng thái freeze/lock theo runbook.
6. Export/copy snapshot sang storage độc lập, tính checksum/metadata.
7. Restore thử đúng phiên bản và đánh giá recovery.

### 11.3. `fsyncLock` không thay snapshot

Một số quy trình có lệnh:

~~~javascript
// Chỉ minh họa API quản trị. Không chạy tùy tiện trên production.
db.fsyncLock()
// Thực hiện snapshot storage theo runbook phù hợp.
db.fsyncUnlock()
~~~

Lock có thể ảnh hưởng writes/replication. Nó không tự tạo backup, không đảm bảo nhất quán giữa nhiều volumes hay nhiều shards. Đừng áp dụng ví dụ này cho toàn sharded cluster mà thiếu coordination.

### 11.4. Crash-consistent khác business-consistent

Một snapshot có thể phù hợp để storage engine recovery, nhưng các bước nghiệp vụ liên quan Kafka, object storage hoặc một database khác vẫn có thể không cùng thời điểm. Backup ứng dụng cần xác định cross-service dependencies.

## 12. RPO của snapshot secondary

Ví dụ:

~~~text
Primary có writes tới thời điểm:  10:30
Secondary mới apply tới:          10:24
Storage snapshot secondary lúc:   10:26
~~~

Snapshot secondary chụp lúc 10:26 **không đồng nghĩa** chứa mọi writes của primary tới 10:26. Điểm dữ liệu còn phụ thuộc secondary đã áp tới đâu. Khi business yêu cầu RPO nhỏ, đo lag và tính thêm latency của backup pipeline.

### 12.1. Rollback và majority commit

Một số writes chưa được xác nhận durable theo write concern có thể bị rollback sau election. RPO cần hiểu trạng thái writes được ứng dụng xác nhận và write concern policy, không đơn thuần theo wall-clock của primary.

### 12.2. Backup node ảnh hưởng availability

Nếu chọn một voting secondary và khóa/restart nó, cần giữ majority. Tránh thao tác khiến replica set không đủ members bầu primary hoặc gây lag kéo dài.

## 13. Khi nào chọn logical hay physical cho replica set?

| Workload | Logical dump | Physical snapshot |
|---|---|---|
| Vài GB, cần export một số collections | Có thể thuận tiện | Có thể dư độ phức tạp |
| Vài TB, RTO ngắn | Có thể quá chậm | Thường đáng đánh giá |
| Cần đọc metadata BSON rõ ràng | Thuận lợi | Dữ liệu ở format storage |
| Muốn exact source storage state | Không phải physical format | Có thể phù hợp với version/storage constraints |
| Đang ghi nhiều và yêu cầu consistent point | Cần `--oplog`/quy trình hỗ trợ | Cần snapshot mechanism đúng |
| Sharded cluster | Không tự đủ consistency toàn cụm | Cần cluster-level coordination |

Không có phương pháp luôn tốt nhất. Kiểm tra dataset size, backup duration, oplog window, CPU/disk budget, khả năng restore target và tooling.

## 14. Vì sao sharded cluster khó backup hơn?

Một sharded cluster chứa:

- **Nhiều shard replica sets** giữ user data.
- **Config Server Replica Set (CSRS)** giữ catalog/sharding metadata.
- **`mongos` routers** dựa vào metadata để định tuyến truy vấn.
- **Balancer, chunk/range migrations và DDL** có thể làm ownership thay đổi khi cluster hoạt động.

~~~mermaid
flowchart TD
    App["Application"] --> Router["mongos"]
    Router --> Config["Config Server Replica Set"]
    Router --> ShardA["Shard A Replica Set"]
    Router --> ShardB["Shard B Replica Set"]
    Router --> ShardC["Shard C Replica Set"]
    Config -.-> Metadata["Routing/chunk ranges/catalog metadata"]
    ShardA -.-> Data["User data và indexes"]
    ShardB -.-> Data
    ShardC -.-> Data
~~~

### 14.1. Snapshots khác thời điểm nguy hiểm thế nào?

~~~text
10:00 Snapshot Shard A
10:02 Balancer chuyển range R từ A sang B
10:04 Snapshot Shard B
10:05 Snapshot Config Server
~~~

Các bản sao này có thể không thuộc **một logical cluster state**. Ranges có thể bị thiếu/trùng hoặc metadata cho biết range thuộc shard khác với data đã chụp. Ghép file backup theo tên ngày giờ không giải quyết consistency.

### 14.2. Config metadata là dữ liệu thiết yếu

Config servers giữ thông tin sharded namespaces, shard keys/ranges, catalog và nhiều trạng thái điều phối. Không thể chỉ backup user documents trên shards rồi tự dựng lại routing metadata bằng cách đoán.

### 14.3. “Đồng hồ cùng giờ” không đủ

Nhiều volume snapshots được trigger gần như đồng thời theo NTP cũng không tự tạo một **logical consistency point toàn sharded cluster**. Transactions, DDL commit và migrations cần được điều phối bằng công cụ phù hợp.

## 15. Không tự ghép `mongodump` của các shards

Một chiến lược sai:

~~~text
Dump Shard A lúc 10:00
Dump Shard B lúc 10:20
Dump Config lúc 10:40
Copy tất cả vào một thư mục và đặt tên backup-full
~~~

Nó không đảm bảo tính nhất quán, đặc biệt khi ứng dụng ghi và balancer chạy.

### 15.1. `mongodump --oplog` qua `mongos` không phải giải pháp

`--oplog` của Database Tools có giới hạn topology và **không phải cluster-wide snapshot qua mongos**. Đừng dùng lệnh dump router rồi quảng cáo RPO/consistency tương đương managed backup giải quyết nhiều shards.

### 15.2. Từng shard có oplog riêng

Oplog trên Shard A và B không tự cho biết cách replay cùng các metadata changes, cross-shard transactions và migration events thành một cluster state. Cần coordination/timestamp metadata mà một backup engine hiểu sharding mới xử lý được đúng.

### 15.3. Dừng balancer chưa đủ

`sh.stopBalancer()` có thể là một bước trong một quy trình được hỗ trợ, nhưng:

- Write traffic vẫn có thể tiếp tục.
- Có active migrations chưa xong.
- DDL, resharding hoặc manual migrations vẫn có thể phát sinh.
- Config metadata và shard datasets vẫn cần snapshot ở điểm phù hợp.

Đừng dùng “đã dừng balancer” làm tiêu chí duy nhất cho backup consistency.

## 16. Giải pháp cluster-aware cho sharded backup

Ưu tiên các phương pháp hiểu topology và consistent points:

1. **MongoDB Atlas Cloud Backup** nếu cluster được quản lý trên Atlas và tier/configuration hỗ trợ.
2. **MongoDB Ops Manager/Cloud Manager hoặc công cụ backup MongoDB chuyên dụng** phù hợp phiên bản, license và topology.
3. **Storage snapshots được điều phối toàn cluster** bằng runbook đã được tài liệu/vendor xác nhận.
4. **Logical export qua mongos** nếu mục đích là data extraction/migration với giới hạn được chấp nhận, không nhầm thành DR backup toàn cluster.

### 16.1. Những yếu tố cần điều phối

| Thành phần | Phải giữ/điều phối gì? |
|---|---|
| Shard replica sets | Dữ liệu và indexes tại consistent point |
| Config server replica set | Catalog/ranges/ownership tương ứng |
| Balancer/migrations | Không tạo trạng thái nửa chừng |
| DDL/resharding | Không đổi schema/routing bất nhất trong backup |
| Cross-shard transactions | Điểm commit nhất quán |
| Backup manifest | IDs, timestamps, versions và checksum |

### 16.2. Không đưa lệnh thủ công như lời giải universal

Sharded backup là thao tác nhạy cảm với phiên bản và topology. Một đoạn shell script ngắn chạy `fsyncLock` trên từng mongod không chứng minh đủ điều kiện consistency. Dùng giải pháp có tài liệu chính thức, thử restore trên cluster cô lập và giữ kế hoạch rollback.

## 17. Khôi phục sharded cluster

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    Backup["Backup cluster-aware có consistent point"] --> Target["Chuẩn bị isolated target"]
    Target --> Restore["Backup engine restore shards + config metadata"]
    Restore --> Router["Khởi tạo/kiểm tra mongos routing"]
    Router --> Verify["Verify ranges, indexes, transactions và app"]
    Verify --> Gate{"Đạt business invariants và RTO?"}
    Gate -->|"Không"| Fix["Điều tra, không chuyển traffic"]
    Gate -->|"Có"| Cutover["Controlled cutover theo change plan"]
~~~

Thứ tự restore thực tế do **công cụ được hỗ trợ** quy định; sơ đồ không phải hướng dẫn tự restore config trước hay sau shards bằng các thao tác thủ công.

### 17.1. Không tự sửa config collections

Nếu metadata không khớp data shards, đừng tự `updateOne` các config server collections để “sửa” routing. Đó là metadata do MongoDB quản lý và sửa tay có thể khiến tình trạng tệ hơn. Phải xử lý bằng backup engine/runbook được hỗ trợ.

### 17.2. Chọn target sạch

Khôi phục qua các snapshots vào cluster đã có dữ liệu production có thể gây conflict `_id`, metadata và ownership. Để diễn tập, ưu tiên target mới/cô lập và kiểm tra kỹ topology.

### 17.3. Kiểm tra cross-shard operations

Một cluster có thể báo router healthy nhưng một shard có range lỗi. Sau restore phải chạy các query theo nhiều shard key values và giao dịch nhiều shard mẫu, không chỉ đếm documents ở shard đầu tiên.

## 18. Atlas Backup: managed nhưng cần lựa chọn chính sách

**MongoDB Atlas** cung cấp các chức năng backup theo khả năng của cluster tier và cloud deployment:

- **Cloud Backup snapshots** để khôi phục bản sao ở những mốc xác định.
- **Continuous Cloud Backup/PITR**, nếu được bật/hỗ trợ, để chọn thời điểm trong cửa sổ lưu giữ.
- **Backup policy/retention**, có thể điều chỉnh tần suất và thời gian giữ tùy gói.
- **Restore workflows** vào cluster đích phù hợp, có thể dùng UI, API/CLI theo tính năng.

**Không mặc định** mọi cluster Free, Flex hoặc Dedicated, mọi cloud/region, mọi phiên bản Atlas đều có cùng loại backup, snapshot download, PITR hay restore cross-region. Cần xác minh khả năng **của chính cluster** và chính sách tài khoản.

### 18.1. Atlas replica set không thay Cloud Backup

Atlas có thể quản lý high availability bằng replica sets nhưng đó là replication, không phải snapshot lịch sử. Phải xem mục backup riêng để xác minh có khả năng khôi phục sau xóa nhầm.

### 18.2. Managed không miễn trách nhiệm của đội vận hành

Atlas làm nhiều việc tự động, nhưng đội ứng dụng vẫn phải chọn RPO/RTO, retention, quyền restore, KMS access, diễn tập, xác minh business logic và cutover an toàn.

## 19. Quy trình Atlas snapshot ở mức khái niệm

1. Xác minh đúng **organization, project và cluster**.
2. Mở phần backup/snapshots theo giao diện Atlas hiện tại.
3. Kiểm tra tính năng đã bật, lịch, retention, region và chi phí.
4. Tìm backup ID/snapshot timestamp phù hợp.
5. Nếu tier hỗ trợ, tạo on-demand snapshot trước migration quan trọng.
6. Chờ snapshot đạt trạng thái **available/completed** theo dịch vụ.
7. Thử restore vào cluster khác và xác nhận data.

### 19.1. Thời điểm click không phải restore point

Nếu yêu cầu snapshot lúc 09:00 nhưng job hoàn tất 09:12, cần đọc **snapshot timestamp/consistent point** mà dịch vụ thông báo; không suy ra restore point chỉ từ giờ nhấn nút.

### 19.2. Retention ảnh hưởng khả năng sửa lỗi lâu ngày

Nếu lỗi ghi dữ liệu sai diễn ra âm thầm 40 ngày nhưng snapshot chỉ giữ 14 ngày, tất cả snapshots còn lại có thể đã chứa dữ liệu lỗi. Retention cần dựa trên **thời gian phát hiện sự cố**, không chỉ tần suất backup.

### 19.3. Snapshot download không phải luôn có

Khả năng tải bản snapshot về local, restore cross-cloud hoặc các tùy chọn export có thể khác theo tier/cloud/version. Một số workflow khôi phục thẳng vào một Atlas target. Không hứa có file `.archive` cho mọi cloud backup.

## 20. Atlas Continuous Cloud Backup/PITR

Khi được hỗ trợ và đã bật đủ sớm, continuous backup có thể lưu các thay đổi giữa snapshots để chọn restore point trong **restorable window**.

~~~text
02:00 Snapshot nền
02:00–10:35 Backup service thu thay đổi theo policy
10:35:20 Một lệnh xóa nhầm bắt đầu
10:35:19 Mốc khôi phục mong muốn, trước thao tác lỗi
10:40 Team phát hiện sự cố
~~~

### 20.1. Điều kiện tiên quyết

- Tier/cloud/region và cấu hình hỗ trợ PITR.
- Continuous backup **đã bật trước** thời điểm lỗi.
- Snapshot nền và history changes vẫn nằm trong retention/restorable window.
- Được phép restore tới mốc chọn.
- Target có capacity, version/config compatibility và quyền.

### 20.2. Bật PITR sau sự cố không tạo lịch sử

Nếu continuous backup chưa được bật khi xóa nhầm, không thể bật lên sau đó để lấy lại oplog/backup history chưa bao giờ được lưu bởi dịch vụ.

### 20.3. Dùng timestamp UTC

Ghi theo chuẩn thời điểm tuyệt đối, ví dụ `2026-11-14T10:35:19Z`. Cần đối chiếu app logs/audit/operation start time và restorable range của Atlas. Giờ địa phương hiển thị trên UI có thể khác UTC.

### 20.4. PITR cả cluster có đánh đổi

Nếu chọn trạng thái trước khi xóa nhầm, mọi writes **hợp lệ** xảy ra sau restore point cũng không nằm trong target restored. Khi phạm vi lỗi nhỏ, restore vào cluster cô lập, trích xuất những dữ liệu bị mất và merge có kiểm soát sẽ giảm nguy cơ mất writes tốt.

## 21. Khôi phục Atlas: chọn target và kiểm soát thay đổi

Workflow thường gặp:

1. Ghi nhận sự cố, cluster nguồn, thời điểm dữ liệu còn sạch.
2. Kiểm tra snapshot/PITR range khả dụng.
3. Chọn **target mới, cô lập** hoặc existing target theo quyền và mức độ rủi ro.
4. Xác minh project, cluster IDs, MongoDB version, FCV, topology, cloud/region, disk, KMS.
5. Đảm bảo người có quyền thực hiện restore và có phê duyệt nếu tác động production.
6. Gửi restore request, theo dõi job trạng thái và log.
7. Kiểm chứng data, indexes, users/roles, kết nối TLS/network và ứng dụng.
8. Chỉ thực hiện cutover nếu kết quả đạt điều kiện vận hành.

### 21.1. Restore vào target mới

Đây là cách an toàn để điều tra vì production chưa bị thay đổi; có thể so sánh current/live với snapshot, chạy smoke tests và copy có chọn lọc. Phải tính chi phí cluster mới và hạn chế truy cập dữ liệu production được phục hồi vào staging.

### 21.2. Restore đè vào cluster hiện có

Có thể thay thế dữ liệu trên target, gây downtime hoặc hỏng dữ liệu đang có. Không lựa chọn chỉ vì thấy action trong UI. Cần change approval, backup trạng thái target hiện tại, rollback/cutover plan.

### 21.3. Một project có nhiều clusters

Để tránh nhầm staging với production, ghi rõ `sourceProjectId`, `sourceClusterId`, `snapshotId`/PITR timestamp, `targetProjectId`, `targetClusterId` vào change record. Với thao tác phá hủy, dùng four-eyes approval nếu policy yêu cầu.

### 21.4. Đích không nhất thiết kế thừa mọi thứ

Network access/IP allowlist, Private Endpoints, connection strings, users/roles, KMS, backup policy trên target và ứng dụng có thể cần cấu hình lại tùy phương thức restore. Restore có data không đồng nghĩa hệ thống sẵn sàng nhận traffic.

## 22. Atlas UI, CLI/API và quyền hạn

Atlas có nhiều bề mặt quản trị; các bước cụ thể và tên action thay đổi theo phiên bản/gói. Automation nên:

- Dùng API/service account với quyền ít nhất đủ thao tác.
- Không ghi API keys trong source code hoặc logs.
- Xác định backup/restore IDs chính xác, hỗ trợ retry/idempotency.
- Giám sát job status và tránh retry một restore phá hủy lên target sai.
- Lưu audit: ai yêu cầu, source/target, timestamp và kết quả.

### 22.1. Quyền backup khác quyền restore

Người xem snapshot không nhất thiết cần quyền phục hồi đè dữ liệu. Tách vai trò backup operator, restore operator, reviewer/approver theo khả năng Atlas project/org roles hiện có; những tên ở đây là **vai trò nghiệp vụ minh họa**, không nhất thiết tên built-in của Atlas.

### 22.2. Chính sách billing

Backup storage, PITR retention, on-demand snapshots, cross-region copies, restored cluster compute và egress có thể phát sinh chi phí. Chọn policy không chỉ dựa vào giá nhưng phải kiểm tra ngân sách và giới hạn.

## 23. Atlas KMS và khả năng giải mã backup

Nếu tổ chức dùng customer-managed encryption keys hoặc KMS integration, bản backup/restore có thể phụ thuộc khả năng truy cập khóa.

- Lưu key references/rotation history theo policy.
- Không vô hiệu hóa/xóa khóa cũ khi các backups trong retention còn cần nó.
- Kiểm tra KMS IAM permissions của restore workflow và target region.
- Diễn tập tình huống primary account mất quyền nhưng backup vẫn phải phục hồi.
- Tách quyền xóa/rotate KMS key khỏi quyền quản lý backup nếu cần.

Một snapshot tồn tại và nhìn thấy trên UI **không bảo đảm giải mã được** nếu khóa cần thiết đã bị xóa hoặc quyền đã bị thu hồi.

## 24. Chính sách retention và bản sao độc lập

Một hệ thống có thể đặt:

| Loại backup | Tần suất ví dụ | Retention ví dụ | Vai trò |
|---|---|---|---|
| Daily snapshot | Mỗi ngày | 7–30 ngày | Khôi phục lỗi phát hiện sớm |
| Weekly snapshot | Mỗi tuần | 4–12 tuần | Phục hồi lỗi trễ hơn |
| Monthly/archive | Mỗi tháng | 6–24 tháng | Nghĩa vụ dài hạn khi phù hợp |
| Continuous/PITR | Theo backup service | Restorable window được cấp | RPO ngắn |

Đây là **ví dụ policy**, không phải frequency/retention cố định của Atlas. Phải cân đối RPO, detection window, cost, legal hold và quy định bảo vệ dữ liệu cá nhân.

### 24.1. 3-2-1 và immutable backup

Một chiến lược phổ biến là giữ nhiều bản sao ở các môi trường/vị trí khác nhau, có bản offsite và nếu có rủi ro ransomware thì thêm bản **immutable/air-gapped** theo điều kiện storage. Các replica set members không được tính là những bản backup độc lập: chúng cùng replicate lỗi xóa nhầm.

### 24.2. Phân quyền xóa backup

Không cấp quyền xóa mọi backups cho ứng dụng đang sử dụng database. Bảo vệ storage backup bằng IAM riêng, MFA, object retention/lock nếu hỗ trợ, audit và review thay đổi retention.

### 24.3. Dữ liệu nhạy cảm trong bản sao

Backup có thể chứa PII, hồ sơ nội bộ, logs và khóa/credential đã lưu trong database. Cần encryption at rest, TLS khi vận chuyển, quyền truy cập tối thiểu và quy trình xóa theo retention. Khi restore vào staging, hạn chế việc phát tán dữ liệu thật.

## 25. Backup phải phù hợp disaster recovery toàn hệ thống

Một sản phẩm có thể dùng:

~~~text
MongoDB: Orders, Payments và Users
Kafka: Event stream
Object storage: Hình ảnh và invoice PDFs
Search engine: Search indexes
Identity provider: Users/SSO
KMS: Data encryption keys
~~~

Snapshot MongoDB **không tự backup** Kafka event log, object files, search index, IAM/KMS và application configurations. Có thể rebuild search indexes nếu source đủ dữ liệu, nhưng file nhị phân ở object storage mất thì không tự xuất hiện từ MongoDB reference.

### 25.1. Cross-system consistency

Nếu order đã ghi trong MongoDB nhưng event publish Kafka chưa xảy ra, backup/restore MongoDB một mình không giải quyết delivery semantics. Thiết kế outbox/inbox, idempotent consumers hoặc workflows để reconcile sau recovery.

### 25.2. Kế hoạch phục hồi dependencies

Runbook phải nêu thứ tự khởi động dịch vụ, khi nào resume consumers, reprocess events, reconcile invoices, mở traffic và tránh duplicate side effects.

## 26. Các bước kiểm chứng restore

Một lần restore được chấp nhận chỉ khi:

1. Backup/source/timestamp đúng như dự kiến.
2. Restore job hoàn thành không có lỗi chưa xử lý.
3. Số lượng databases/collections/indexes hợp lý.
4. Document counts, ID ranges và sample hashes/invariants khớp với restore point.
5. Users/roles, TLS, network và KMS hoạt động.
6. Replica set/sharded cluster topology healthy.
7. Application smoke tests chạy thành công.
8. RPO/RTO thực tế được ghi nhận.

### 26.1. Kiểm tra replica set target

~~~javascript
// Chỉ chạy trên target test được phép.
rs.status()
db.adminCommand({ ping: 1 })
db.getSiblingDB("shop").orders.countDocuments({})
db.getSiblingDB("shop").orders.getIndexes()
~~~

`rs.status()` healthy không chứng minh documents đã restore đúng; một cluster rỗng cũng có thể healthy.

### 26.2. Kiểm tra sharded cluster target

~~~javascript
// Chạy qua mongos trên cluster khôi phục với quyền phù hợp.
sh.status()
db.adminCommand({ ping: 1 })
~~~

Kiểm tra shard keys/ranges, config metadata, query routing theo nhiều shard key values, indexes và cross-shard transactions. Đừng chỉ query một shard rồi tuyên bố toàn cluster OK.

### 26.3. Business invariants

Ví dụ:

~~~text
Mỗi order PAID phải có payment hợp lệ.
Tổng payments phải khớp order total theo quy tắc.
Một invoice reference phải trỏ tới object còn tồn tại.
Inventory movement phải khớp các orders đã fulfill.
~~~

Số documents đúng chưa đủ: một backup không nhất quán có thể có đúng counts nhưng sai quan hệ giữa collections.

## 27. Kiểm tra source, target và timestamp

Trước restore, ghi rõ:

~~~yaml
incidentId: INC-2026-001
sourceCluster: mongo-prod-rs0
sourceTopology: replicaSet
backupId: rs0-20261114-013000
restoreTimestampUtc: "2026-11-14T01:48:00Z"
targetCluster: mongo-restore-isolated
targetEnvironment: recovery-lab
requestedBy: incident-operator
approvedBy: change-approver
restoreStatus: PENDING
~~~

Giá trị là **mẫu**. Một restore destructive được gửi nhầm target sẽ gây sự cố mới; cần xác minh immutable target IDs, environment và trạng thái trước khi chạy.

### 27.1. Chọn backup sạch, không chỉ mới nhất

Nếu một migration sai chạy từ 09:00 nhưng backup mới nhất là 10:00, backup đó đã chứa dữ liệu lỗi. Xem audit/application logs để xác định điểm khôi phục trước sự cố.

### 27.2. Mốc UTC và precision

Nên ghi timestamp tuyệt đối, không dùng “lúc 9 giờ hôm qua” thiếu timezone. Với PITR liên quan transaction boundary, đối chiếu log events/clock accuracy và restorable range mà công cụ thực sự hỗ trợ.

## 28. Theo dõi backup jobs

| Metric/quan sát | Ý nghĩa |
|---|---|
| Last successful backup age | Backup mới nhất còn đáp ứng SLA? |
| Backup duration | Job có kéo dài hơn oplog window/window backup? |
| Backup exit code | Có lỗi đã bị bỏ qua không? |
| Backup size delta | Có mất namespaces, giảm dữ liệu bất thường? |
| Checksum/integrity result | Archive có bị thay đổi không? |
| Restore drill success | Backup có thật sự dùng được? |
| Actual RPO/RTO | Đã đạt business objectives? |
| Secondary replication lag | Source snapshot có quá cũ? |
| Oplog window | Có đủ history cho backup/PITR method? |
| Atlas snapshot/PITR status | Dịch vụ có bật và khỏe không? |
| Retention remaining | Có backup sắp hết hạn cần xử lý? |
| KMS key access | Restore còn có thể giải mã? |

Các tên là **gợi ý hệ thống monitoring**, không phải MongoDB tự export toàn bộ dưới những tên này. Kết hợp metrics từ cron/job runner, Atlas, cluster health, storage và DR drill logs.

### 28.1. Backup file rỗng

Một job có thể ghi file nhỏ vì kết nối sai database, quyền thiếu hoặc filter sai. Kiểm tra logs, archive manifest, expected data size/namespaces và restore test. Không chỉ dựa vào “file có tồn tại”.

### 28.2. Cảnh báo PITR bị tắt

Nếu RPO nhỏ dựa vào continuous backup, cần giám sát tính năng vẫn bật và **restorable window** còn đáp ứng yêu cầu. Thay đổi policy hoặc tier có thể làm giảm khả năng phục hồi.

## 29. RPO và RTO đo trên một sự cố

~~~text
Sự cố bắt đầu:             10:37
Restore point an toàn:     10:30
Restore DB xong:           11:25
Ứng dụng phục vụ lại:      11:42
~~~

Theo ví dụ:

- Dữ liệu sau 10:30 đến lúc sự cố 10:37 có thể không tồn tại ở target: **7 phút** theo mốc thời gian.
- Từ 10:37 đến 11:42: **65 phút** phục hồi dịch vụ.

Nếu RPO mục tiêu là 5 phút và RTO là 60 phút, cả hai **chưa đạt**. Việc restore DB thành công lúc 11:25 không thay đổi RTO toàn dịch vụ vốn kết thúc lúc 11:42.

### 29.1. RTO không chỉ là thời gian chép bytes

~~~text
Detection + decision + provision + restore/index build
          + verify + credentials/network + cutover + smoke tests
~~~

Kế hoạch dự phòng cần đo toàn bộ chuỗi này.

## 30. Quy trình diễn tập DR

Một buổi drill có thể:

1. Chọn snapshot/backup thật trong retention.
2. Tạo isolated target với đủ compute/storage/version.
3. Khôi phục đầy đủ theo runbook, không chạm production.
4. Kiểm tra restore status, collection/index/transaction invariants.
5. Chạy ứng dụng trên target với test data/traffic phù hợp.
6. Đo recovery point, RTO, tài nguyên và chi phí.
7. Xác nhận user/roles, TLS/KMS/network.
8. Ghi problems, action items và chủ sở hữu.
9. Xóa target theo policy sau khi hoàn thành.

**Đọc một file hướng dẫn** hoặc chạy `mongodump --version` không được coi là restore drill.

### 30.1. Kịch bản nên thử

- Xóa nhầm một collection.
- Cả replica set mất khả năng phục vụ.
- Restore dữ liệu về trước migration lỗi.
- Một shard/config server gặp sự cố lớn.
- Mất một region.
- Backup quá hạn hoặc key KMS không còn.
- Atlas project/cấu hình network thay đổi.

Mỗi kịch bản có target RPO/RTO và quyền phê duyệt riêng.

## 31. Runbook DR tối thiểu

~~~text
1. Incident trigger và người chịu trách nhiệm
2. Source cluster ID, topology, version, FCV
3. RPO/RTO mục tiêu, mốc dữ liệu sạch
4. Backup inventory + snapshot/oplog ID
5. Quyền backup/restore, secrets/KMS
6. Target riêng, network/TLS và resources
7. Lệnh hoặc Atlas restore workflow đã kiểm chứng
8. Cách theo dõi job và xử lý failed state
9. Validation: counts, indexes, invariants, application
10. Cutover, writes đã phát sinh sau restore point
11. Rollback/fallback nếu cutover thất bại
12. Audit và retrospective
~~~

Runbook phải có đủ chi tiết để một operator khác thực hiện đúng, không phụ thuộc trí nhớ của người đã viết script.

## 32. Backup và chi phí hiệu năng

### 32.1. Logical dump lớn

Dump có thể quét nhiều collections, tiêu thụ disk reads/network bandwidth và CPU nén. Trên primary, ảnh hưởng latency phục vụ writes; trên secondary, ảnh hưởng replication apply. Cân nhắc thời điểm, concurrency và resource budgets.

### 32.2. Compression

`--gzip` giảm số bytes lưu/truyền trong nhiều trường hợp nhưng tiêu tốn CPU. Trên dữ liệu vốn đã nén, tỷ lệ nén có thể không lớn. Benchmark bằng dataset thực.

### 32.3. Index rebuild

Restore logical datasets lớn có thể mất rất lâu để tạo indexes, kể cả khi chép BSON nhanh. Cần đủ disk headroom và xác định tác động của index uniqueness khi data sai.

### 32.4. Sharded backups

Cluster-aware backup còn phải điều phối metadata và nhiều sources, có thể gây I/O trên các shards. Nếu chọn snapshot từng node, phải tính aggregate throughput, mạng, capacity storage và tác động đến balancer/app.

### 32.5. Atlas restore

Khả năng chọn tier/cluster đích, bandwidth và resource allocation ảnh hưởng thời gian restore. Một backup hoàn tất nhanh không chứng minh DR RTO ngắn; chỉ **diễn tập thực tế** mới đo được.

## 33. Những lỗi và tình huống thường gặp

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| `mongodump` permission denied | Backup user thiếu privileges | Cấp role/phạm vi phù hợp |
| TLS handshake failed | CA/SAN/expiry sai | Sửa certificate/trust/hostname |
| Archive nhỏ bất thường | URI/filter sai, job thất bại | Kiểm tra exit code/manifests |
| `--oplog` không dùng được với `--collection` | Tùy chọn không tương thích | Chọn full-scope hoặc công cụ khác |
| `--oplog` qua `mongos` lỗi | Sai topology cho oplog dump | Dùng cluster-aware backup |
| Oplog không đủ | Window ngắn, write rate cao | Điều chỉnh phương pháp/capacity |
| Restore duplicate keys | Target không sạch hoặc data/index conflict | Restore isolated, kiểm tra policy |
| Restore thiếu indexes | Scope/options/metadata chưa đúng | Đối chiếu restore logs và indexes |
| Snapshot khôi phục nhưng dữ liệu lệch | Snapshot files/volumes không nhất quán | Dùng supported snapshot method |
| Sharded restore sai ranges | Metadata/data khác logical point | Dùng cluster-consistent backup |
| Atlas PITR không hiện | Tier/configuration/retention không hỗ trợ | Kiểm tra khả năng thật của cluster |
| Restore không giải mã được | KMS key/quyền đã mất | Khôi phục quyền key theo chính sách |
| App lỗi sau restore | Users/roles/TLS/network/schema | Smoke test và readiness checklist |
| Backup quá hạn | Retention không phù hợp | Cập nhật policy và archive |
| Restore RTO vượt SLA | Dữ liệu lớn/index rebuild/provision chậm | Diễn tập, tối ưu resources/architecture |

## 34. Những anti-pattern cần tránh

1. **Coi replication là backup.** Writes xóa nhầm cũng được replicate.
2. **Có backup nhưng chưa từng restore thử.** Không biết có thể khôi phục được không.
3. **Ghép snapshots từng shard tại các mốc khác nhau.** Không có consistent cluster state.
4. **Dùng `mongodump --oplog` qua mongos như giải pháp cluster-wide.** Sai phạm vi.
5. **Chỉ stop balancer rồi kết luận toàn sharded backup nhất quán.** Còn writes/DDL/migrations.
6. **Chạy restore production để thử nghiệm.** Có thể xóa/ghi đè dữ liệu.
7. **Bật PITR sau sự cố và mong có lịch sử.** Chưa lưu changes thì không có gì để replay.
8. **Tin gzip là encryption.** Không bảo vệ dữ liệu khỏi người có quyền đọc file.
9. **Lưu password/backup credentials trong script public.** Dễ bị lộ.
10. **Không lưu KMS keys đủ lâu.** Backup có thể không giải mã được.
11. **Retention ngắn hơn detection window.** Tất cả backup còn lại đã chứa lỗi.
12. **Không đo application readiness trong RTO.** Chỉ đo lệnh restore chưa đủ.
13. **Copy WiredTiger files khi đang ghi mà không có snapshot consistency.** Có nguy cơ hỏng dữ liệu.
14. **Không backup external dependencies.** MongoDB sống nhưng ứng dụng không phục hồi được.
15. **Không giám sát job failure.** Có thể không có backup mới trong nhiều ngày.

## 35. Lab A — chọn backup cho replica set

Một replica set 3 nodes có 30 GiB dữ liệu, 15 GiB indexes, RPO 24 giờ và RTO 4 giờ. Hãy:

1. Đề xuất logical dump hay physical snapshot, phân tích chi phí/restore.
2. Xác định có cần `--oplog` khi các writes tiếp tục trong dump.
3. Nếu backup từ secondary, kiểm tra gì về lag và oplog window?
4. Thiết kế manifest, checksum và offsite retention.
5. Nêu các bước restore drill.

## 36. Lab B — phát hiện lệnh sai

~~~bash
mongodump \
  --uri="mongodb://mongo1.db.internal:27017/?replicaSet=rs0&tls=true" \
  --tlsCAFile=/etc/mongodb/tls/ca-chain.pem \
  --username=backupOperator \
  --authenticationDatabase=admin \
  --db=shop \
  --collection=orders \
  --oplog \
  --archive=/backups/orders.archive
~~~

Vì sao tổ hợp `--oplog` với scope collection là vấn đề? Nếu chỉ xuất orders, có thể bảo đảm payments/inventory nhất quán cùng thời điểm không? Phương án nào khi cần full replica set consistent backup?

## 37. Lab C — restore có kiểm soát

Giả sử bạn có archive full dump với oplog. Thiết kế buổi thực hành:

- Tạo isolated target mới.
- Kiểm tra checksum và tool/server compatibility.
- Chạy `mongorestore --oplogReplay`.
- Kiểm tra `rs.status()`, counts, indexes, orders/payments invariants.
- Đo RPO/RTO.
- Không bật application production traffic trước khi validation hoàn tất.

Giải thích tại sao không dùng `--drop` trên target production có dữ liệu.

## 38. Lab D — replica set secondary lag

~~~text
Primary writes đã tới 10:30
Secondary apply oplog mới tới 10:24
Secondary snapshot lúc 10:26
~~~

Snapshot có thể thiếu những writes nào? Có thể gọi đó là backup đến 10:26 theo thời gian primary không? Cách bạn sẽ xử lý RPO nhỏ hơn 5 phút là gì?

## 39. Lab E — sharded range migration

~~~text
Snapshot Shard A: 10:00
Balancer chuyển range R: 10:02
Snapshot Shard B: 10:04
Snapshot CSRS:    10:05
~~~

Hãy giải thích khả năng dữ liệu bị thiếu/trùng hoặc metadata sai sau restore. Tại sao stop balancer một mình chưa đủ? Công cụ backup nên hiểu các thành phần gì?

## 40. Lab F — Atlas PITR

Giả sử một Atlas cluster **có PITR đang bật** và cửa sổ khôi phục 48 giờ (giả định bài tập). Một lệnh xóa sai bắt đầu lúc `2026-11-14T10:15:20Z`, phát hiện lúc 10:20. Hãy:

1. Chọn mốc restore an toàn trước thao tác sai.
2. Nêu cách xác nhận timestamp qua logs/audit.
3. Giải thích vì sao nên restore vào cluster cô lập.
4. Nêu ảnh hưởng tới writes hợp lệ nếu restore toàn cluster về mốc cũ.
5. Nêu tình huống không thể PITR dù đã có Atlas cluster.

## 41. Lab G — tính RPO/RTO

Sự cố 10:37, restore point sạch 10:30, ứng dụng hoạt động lại 11:42. Tính RPO thực tế theo kịch bản và RTO. Với mục tiêu RPO 5 phút, RTO 60 phút, đã đạt chưa?

## 42. Lab H — KMS và retention

Tổ chức giữ monthly backups 12 tháng nhưng xóa khóa KMS được dùng để mã hóa backup sau 30 ngày. Điều gì có thể xảy ra khi cần restore tháng thứ sáu? Thiết kế key rotation/retention policy.

## 43. Lab I — hệ thống nhiều services

Ứng dụng lưu orders trong MongoDB, invoice PDFs trong object storage và events trong Kafka. Sau khi phục hồi MongoDB về trước sự cố 20 phút, cần reconcile những thành phần nào để tránh invoice thiếu, event lặp hoặc order state không khớp?

## 44. Lab J — audit và approval

Viết một phiếu DR request gồm source project/cluster, backup ID/timestamp, target cluster, người phê duyệt, chính sách quyền, KMS/TLS config, bước validation và điều kiện cutover. Nêu cách ngăn vô tình chọn staging làm source và production làm target bị ghi đè.

## 45. Lab K — số lượng documents đúng nhưng business sai

Sau restore, `orders.countDocuments({})` đúng nhưng một order PAID không có payment. Hãy đề xuất cách điều tra inconsistent dump point, cross-collection transactions, restore scope và logic ứng dụng. Có nên công bố hệ thống đã phục hồi thành công ngay chưa?

## 46. Gợi ý đáp án thực hành

**A:** Logical full dump có thể đủ với 30 GiB nếu backup/restore thực đo đạt RTO; physical snapshot nên được đánh giá nếu I/O/index rebuild quá lâu. Có writes liên tục thì full `--oplog` khi công cụ hỗ trợ. Kiểm tra lag, oplog, offsite và restore drill.

**B:** `--oplog` không tương thích tùy tiện với `--db`/`--collection`; export orders không đảm bảo consistent point của payments. Dùng full replica set backup có oplog hoặc phương án consistent snapshot.

**C:** Restore vào target cô lập, không dùng `--drop` lên production. Kiểm tra data/index/invariants; archive checksum không thay restore test.

**D:** Secondary có thể chưa áp writes sau 10:24, dù chụp 10:26. Cần đo lag, chọn source/method đủ RPO và monitor.

**E:** Range R chuyển ownership giữa các snapshots, metadata/data có thể không cùng trạng thái. Cần cluster-aware backup coordination, gồm CSRS, shards, DDL và migrations.

**F:** Chọn timestamp trước 10:15:20Z nằm trong restorable window sau khi đối chiếu audit. Restore isolated để chọn lọc dữ liệu, tránh mất writes tốt. Nếu PITR không được hỗ trợ/bật trước hoặc quá retention thì không có điểm đó.

**G:** Khoảng mất dữ liệu 7 phút; gián đoạn dịch vụ 65 phút. Cả RPO 5 phút và RTO 60 phút chưa đạt.

**H:** Khi khóa cũ bị hủy, backup có thể không giải mã được. Giữ khả năng truy cập key trong backup lifetime hoặc re-encrypt theo quy trình hỗ trợ.

**I:** MongoDB snapshot không phục hồi object files/Kafka offsets. Cần xác minh external backups, event replay/idempotency/outbox và invoice references.

**J:** Ghi immutable identifiers, approval và explicit target check, không chỉ tên hiển thị. Chọn target mới để giảm nguy cơ phá production.

**K:** Count không bảo đảm invariant. Kiểm tra backup consistent point, transaction state và dữ liệu payment; chưa nên mở traffic nếu trạng thái business sai.

## 47. Câu hỏi ôn tập

**1. Replica set có cần backup không?** — Có, vì writes sai/xóa nhầm cũng được replicate.

**2. RPO là gì?** — Mức mất dữ liệu chấp nhận được, thường theo thời gian.

**3. RTO là gì?** — Thời gian phục hồi khả năng phục vụ chấp nhận được.

**4. `mongodump` thuộc loại backup nào?** — Logical.

**5. `mongodump --oplog` làm gì?** — Thu oplog trong khoảng full dump của replica set để hỗ trợ nhất quán khi replay.

**6. Có thể dùng `--oplog` cho một collection tùy ý không?** — Không; công cụ có giới hạn scope và option compatibility.

**7. Có thể dùng `--oplog` qua mongos để backup toàn sharded cluster không?** — Không, không phải cluster-wide consistent method.

**8. `mongorestore --oplogReplay` có phải PITR bất kỳ thời điểm không?** — Không; chỉ dùng dữ liệu oplog được lưu phù hợp.

**9. Oplog có lưu mãi không?** — Không, dữ liệu cũ sẽ bị xoay vòng.

**10. Secondary snapshot có luôn mới nhất không?** — Không; có thể lag primary.

**11. Copy folder WiredTiger đang ghi có phải snapshot an toàn không?** — Không; phải đảm bảo storage/journal consistency.

**12. Vì sao sharded backup cần config servers?** — Vì chứa sharding catalog/routing metadata.

**13. Snapshots từng shard khác thời điểm có bảo đảm consistency không?** — Không.

**14. Stop balancer đã đủ cho backup sharded cluster?** — Chưa; writes/DDL/transactions và metadata cần điều phối.

**15. Atlas có Cloud Backup/PITR ở mọi tier không?** — Không; phụ thuộc tier/cloud/region/cấu hình.

**16. PITR có cần được bật trước sự cố không?** — Có; phải có lịch sử thay đổi được lưu trong restorable window.

**17. Daily snapshot tự đáp ứng RPO 5 phút không?** — Không nếu không có continuous changes tương ứng.

**18. Tại sao nên restore vào cluster mới?** — Giảm rủi ro ghi đè và hỗ trợ đối soát/merge chọn lọc.

**19. `--drop` nguy hiểm ra sao?** — Có thể xóa dữ liệu target trước restore.

**20. SHA-256 của archive đúng thì restore chắc chắn OK?** — Không; còn data completeness, compatibility và business invariants.

**21. KMS key bị xóa có thể làm gì?** — Khiến encrypted backup không còn giải mã được.

**22. RTO có bao gồm application cutover không?** — Có, không chỉ database copy.

**23. PITR toàn cluster có thể làm mất writes tốt không?** — Có, mọi thay đổi sau restore point không nằm trong target.

**24. Backup có cần TLS/encryption/access control không?** — Có, nó chứa dữ liệu nhạy cảm như production.

**25. DR drill nên làm gì?** — Restore thật ở target cô lập, kiểm tra dữ liệu/ứng dụng, đo RPO/RTO và cải thiện runbook.

## 48. Bảng ghi nhớ nhanh

| Yêu cầu | Phương án/điểm cần nhớ |
|---|---|
| Full logical backup replica set | `mongodump` |
| Oplog khi dump có writes | `mongodump --oplog` với full-scope hỗ trợ |
| Restore dump có oplog | `mongorestore --oplogReplay` trên target tách biệt |
| Physical backup | Storage snapshot nhất quán theo WiredTiger/journal |
| Backup secondary | Kiểm tra lag/oplog window |
| Sharded backup | Công cụ cluster-aware phối hợp shards và CSRS |
| Không nên | Ghép snapshots shards khác logical point |
| Atlas snapshot | Cloud Backup khi tier/cấu hình hỗ trợ |
| Atlas PITR | Continuous backup đã bật + restorable window |
| Mất một nhóm documents | Restore isolated + merge chọn lọc |
| RPO | Mức mất dữ liệu tối đa |
| RTO | Thời gian dịch vụ gián đoạn tối đa |
| Backup security | TLS, encryption, least privilege, audit |
| Backup reliability | Manifest + checksums + restore test |
| DR runbook | Source, point, target, versions, keys, validation, cutover |

## 49. Checklist triển khai

- [ ] Đã xác định topology và mục tiêu RPO/RTO?
- [ ] Có danh sách namespaces, indexes, users/roles và external dependencies?
- [ ] Đã chọn logical/physical/managed backup dựa trên size/consistency?
- [ ] Nếu dùng `--oplog`, scope/replica set requirements đúng?
- [ ] Có giám sát oplog window và secondary lag?
- [ ] Physical snapshots chụp đủ database/journal volumes tại consistent point?
- [ ] Không copy active database files tùy tiện?
- [ ] Sharded backup có cơ chế cluster-wide metadata consistency?
- [ ] Không ghép snapshots nhiều shards ở các thời điểm không phối hợp?
- [ ] Atlas tier/cloud/region hiện tại thực sự hỗ trợ backup/PITR đã thiết kế?
- [ ] PITR đã bật trước khi cần và restorable range được theo dõi?
- [ ] Retention đủ dài so với thời gian phát hiện sai dữ liệu?
- [ ] Backup user có least privilege, TLS, không hardcode secrets?
- [ ] Backups được mã hóa và KMS keys còn khả dụng?
- [ ] Có offsite/immutable copies phù hợp risk model?
- [ ] Backup job checks exit code, manifests, checksum và upload success?
- [ ] Restore target được cô lập, có đủ storage, version/FCV compatibility?
- [ ] Không dùng `--drop`/overwrite production ngoài approved change?
- [ ] Đã kiểm tra collection counts, indexes và business invariants?
- [ ] Với sharding, đã test routing/ranges và cross-shard transactions?
- [ ] Có kiểm tra TLS, network, users/roles, KMS trên target?
- [ ] Có application smoke test và cutover/rollback plan?
- [ ] Có DR drill định kỳ và đo RPO/RTO thực tế?
- [ ] Có alert backup failure, stale backups, retention, PITR và key access?
- [ ] Có audit restore/snapshot/retention changes và data privacy policy?

## 50. Kết luận

Sao lưu MongoDB phải bắt đầu từ **topology, nhất quán dữ liệu và mục tiêu RPO/RTO**. Với **replica set**, `mongodump --oplog` là phương pháp logical backup có thể hỗ trợ consistent restore trong phạm vi công cụ; physical snapshots cần capture đồng bộ WiredTiger data/journal và phải xét replication lag của secondary. Với **sharded cluster**, dữ liệu trên shards và catalog ở config servers cần một **cluster-wide consistent point**; không được ghép snapshots từng shard ở những thời điểm khác nhau rồi xem đó là bản khôi phục hợp lệ.

Với **MongoDB Atlas**, managed snapshots và Continuous Cloud Backup/PITR có thể giảm đáng kể khối lượng vận hành nếu **tier, region và cấu hình** hỗ trợ. Dù vậy, đội ứng dụng vẫn cần hiểu retention, tính năng restore, KMS keys, đích khôi phục, dữ liệu được phép mất và những writes hợp lệ sau restore point.

Cuối cùng, **backup thành công chưa có nghĩa restore thành công**. Hãy bảo vệ bản sao như dữ liệu production, dùng manifest/checksum, giám sát jobs và thực hiện restore drills vào môi trường cô lập. Khả năng khôi phục đáng tin cậy được chứng minh bằng **dữ liệu nhất quán, ứng dụng chạy được và RPO/RTO thực tế đạt mục tiêu**, không chỉ bằng sự tồn tại của một file backup.
