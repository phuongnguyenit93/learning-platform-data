# Thiếu bộ nhớ, ổ đĩa đầy và transaction log tăng bất thường trong Neo4j

## 1. Mục tiêu của bài: xử lý sự cố mà không làm mất thêm dữ liệu

Một dịch vụ Java/Spring Data Neo4j dùng property graph để quản lý `(:Customer)-[:PLACED]->(:Order)` và `(:Supplier)-[:SUPPLIES]->(:Product)`. Sau khi triển khai một job nhập dữ liệu, đội vận hành thấy:

- API ghi đơn hàng timeout, một số request trả lỗi thiếu bộ nhớ.
- Pod Neo4j bị `OOMKilled` hoặc JVM ghi `OutOfMemoryError`.
- Dung lượng ổ đĩa giảm nhanh, nhất là ở thư mục `data/transactions`.
- Database từ `ONLINE` chuyển sang trạng thái không phục vụ được, mặc dù ứng dụng Java vẫn cố retry.

Ba hiện tượng **thiếu bộ nhớ, đầy đĩa, transaction log tăng** có thể liên quan nhau nhưng **không đồng nghĩa**. Một import khổng lồ có thể làm transaction state chiếm heap và tạo nhiều transaction logs; checkpoint chậm khiến logs không được dọn; ổ đĩa đầy có thể làm database không còn hoạt động, trong khi request retry làm quá tải thêm.

Bài thuộc chương **Xử lý sự cố**, cung cấp:

1. Quy trình triage và phân loại lỗi theo **JVM heap**, transaction limit, native/container memory, disk và log.
2. Lệnh quan sát **an toàn, chỉ đọc** ở OS, Neo4j và tầng Java.
3. Cơ chế transaction log **rotation → checkpoint → pruning**, nguyên nhân logs tăng và những cách xử lý nguy hiểm cần tránh.
4. Biện pháp giảm tải, sửa Cypher/transaction, kiểm soát Java Driver và Spring Data Neo4j.
5. Điều kiện phục hồi, xác minh tính toàn vẹn và kế hoạch phòng ngừa có số liệu.

> Ví dụ dùng các tên setting của Neo4j 5.x và dòng phát hành `2025.MM`/`2026.MM`. Edition, phiên bản, AuraDB và môi trường container có khác biệt. Mọi lệnh thay đổi dữ liệu/cấu hình phải được thử và phê duyệt riêng; không xem ví dụ là lệnh khẩn cấp có thể chạy vô điều kiện trên production.

## 2. Trong 5 phút đầu: khoanh vùng trước khi sửa

### 2.1. Một quyết định ưu tiên

Nếu thấy **disk đầy hoặc Neo4j không thể ghi**, hãy **dừng nguồn phát sinh ghi không thiết yếu**: import, batch update, retry storm, CDC worker ghi ngược và các job tạo index nặng. Giữ bằng chứng và kiểm tra trước khi restart. Nếu hệ thống đã có khả năng mất dữ liệu, kích hoạt **incident response** và người phụ trách database/storage.

Nếu JVM đang thiếu bộ nhớ, tránh đồng thời tăng tất cả heap, transaction limit và concurrency: hành động đó có thể khiến container hoặc OS bị kill sớm hơn.

### 2.2. Bảng nhận diện triệu chứng

| Tín hiệu | Khả năng cần kiểm tra | Bằng chứng quan trọng | Hành động đầu tiên |
| --- | --- | --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` | JVM heap không đủ cho live set/query | JVM heap used/max, GC, query log, transaction size | Giảm tải và xác định query/job gây cấp phát lớn |
| `Neo.TransientError.General.MemoryPoolOutOfMemoryError` | Pool bộ nhớ đạt limit | Thông báo setting, `SHOW TRANSACTIONS`, `dbms.listPools` | Tìm transaction lớn, không nới limit tùy ý |
| `OOMKilled`, exit code 137 | OS/container memory limit | Kubernetes events, cgroup, RSS, heap + page cache + native | Kiểm tra limit thực, ngừng job nặng |
| `No space left on device`/`ENOSPC` | Disk/inode/quota/volume đầy | `df -h`, `df -i`, PVC/volume quota, log DBMS | Ngừng ghi phát sinh, bảo toàn store và mở rộng dung lượng an toàn |
| `data/transactions` lớn dần | Tốc độ ghi cao, retention, checkpoint/pruning chậm | Log size theo thời gian, checkpoint duration, retention, backup/CDC | Kiểm tra cơ chế log trước; **không xóa file thủ công** |
| GC pause tăng, p99 tăng, RAM chưa hết | Heap pressure hoặc object churn | GC time, heap after-GC, allocation rate | Sửa query/batch, đo live set |
| Page faults cao, heap vẫn ổn | Page cache thiếu hoặc query đọc quá rộng | Page-cache hit/faults, `PROFILE`, disk latency | Xem index/query trước khi tăng RAM |
| DBMS báo database `OFFLINE` | Có thể do storage, recovery, config hoặc lỗi khác | `SHOW DATABASES`, `neo4j.log`/`debug.log` | Không ép `START`/restart liên tiếp khi nguồn lỗi chưa xử lý |
| Java Driver báo timeout khi DBMS khỏe | Pool, network, transaction lock hoặc overloaded server | Pool wait, server transactions, query latency | Khoanh vùng client/server, không mặc định tăng tài nguyên DB |

**Không biến một lỗi transient thành một vòng retry vô hạn.** Khi disk đầy hoặc quorum/DBMS chưa sẵn sàng, retry nhanh từ nhiều instance Java có thể khiến tình hình xấu hơn.

## 3. Bản đồ bộ nhớ và lưu trữ của Neo4j

```text
Host RAM / container memory limit
  |
  +-- JVM heap                  <= server.memory.heap.max_size
  |    +-- Cypher execution, sort/collect, transaction state
  |    +-- GDS graph / algorithm state nếu được sử dụng
  |    +-- Java objects, GC overhead
  |
  +-- Neo4j page cache          <= server.memory.pagecache.size
  |    +-- graph store, native indexes
  |
  +-- Native / direct / OS memory
       +-- thread stacks, metaspace, network buffers, kernel...

Disk / volumes (có thể trên những filesystem riêng)
  |
  +-- data/databases/<database>    graph store và indexes
  +-- data/transactions/<database> transaction log cho phục hồi/backup
  +-- data/cluster-state/...       metadata/raft log của cluster (nếu có)
  +-- logs/                       neo4j.log, debug.log, query.log, gc.log
  +-- backups/, dumps/, imports/  phụ thuộc thiết kế triển khai
```

**Transaction log khác query log.**

- **Transaction log** lưu thay đổi đã thực hiện để bảo đảm recovery, backup differential, catch-up và CDC trong các điều kiện hỗ trợ.
- **Query log** là log quan sát truy vấn, duration, DB Hits, page faults, parameter theo cấu hình; không dùng để replay database.
- **`debug.log` và `neo4j.log`** giúp điều tra sự cố phần mềm/hệ thống.
- **Raft log** của cluster phục vụ replication đồng thuận; khác transaction log của database.

Không di chuyển/xóa file trong `data/databases`, `data/transactions` hay `data/cluster-state` bằng `rm` để lấy lại dung lượng. Neo4j cần biết checkpoint và thứ tự log để phục hồi nhất quán.

## 4. Runbook sự cố: ba giai đoạn có thể kiểm chứng

### Giai đoạn A — 0–10 phút: ngăn hư hỏng lan rộng

1. Ghi incident ID, thời điểm UTC, Neo4j version/edition, database và các service ảnh hưởng.
2. Tạm dừng **import/batch/write jobs không thiết yếu**; chuyển API ghi sang chế độ bảo trì nếu phù hợp, nhưng không giả rằng mọi bản sao cluster cũng ngừng ghi.
3. Giảm retry storm ở Java Driver/queue, giữ error logs và correlation ID.
4. Kiểm tra **dung lượng và inode của mọi filesystem liên quan**: database store, transaction logs, log quan sát, backup, temp.
5. Ghi trạng thái database/cluster. Không chạy `DROP`, restore, force checkpoint hay restart nhiều lần khi disk đang cạn.
6. Nếu nghi corruption, mất volume hoặc OOM lặp lại, giữ chứng cứ và liên hệ đội DBA/SRE/Neo4j Support.

### Giai đoạn B — 10–30 phút: xác định nguồn tăng

1. Phân biệt JVM heap exhaustion, transaction cap, host OOM và disk quota.
2. Kiểm tra số/tốc độ tăng transaction logs, tốc độ ghi thực tế, checkpoint/pruning.
3. Đối chiếu query log với job mới triển khai, `SHOW TRANSACTIONS`, `PROFILE` trên môi trường an toàn.
4. Kiểm tra thành viên cluster nào bị ảnh hưởng, logs có nằm trên volume riêng hay không.
5. Chọn **một hướng khắc phục** có giả thuyết và điều kiện dừng, ưu tiên phương án không phá dữ liệu.

### Giai đoạn C — phục hồi có kiểm soát

1. Đảm bảo storage đủ chỗ cho **recovery, checkpoint, log rotation và backup**, không chỉ vừa trống vài MB.
2. Nếu DBMS còn hoạt động, đánh giá khôi phục ghi từng phần sau khi nguồn lỗi đã dừng; nếu DBMS offline, theo quy trình startup/recovery và backup đã diễn tập.
3. Đối soát counts, constraint, graph relationships, transaction cuối cùng được commit.
4. Mở read traffic, sau đó write traffic có giới hạn; theo dõi p95/p99, heap, GC, disk free, log growth và error rate.
5. Ghi thời gian phục hồi và bằng chứng; chỉ kết thúc incident sau khi đã ổn định.

**Nguyên tắc:** restore từ backup là một phương án cho hỏng/mất data; **không phải phản xạ đầu tiên** khi một query dùng quá nhiều heap hoặc transaction logs tăng bình thường vì lượng ghi lớn.

## 5. Kiểm tra disk và filesystem: lệnh chỉ đọc

Trên host Linux (không chạy nếu không có quyền vận hành), ví dụ:

```bash
# Dung lượng thực trên các mount.
df -h

# Hết inode cũng có thể gây ENOSPC khi byte vẫn còn.
df -i

# Thay <NEO4J_HOME> bằng thư mục triển khai thực tế.
du -sh /var/lib/neo4j/data/databases/* 2>/dev/null
du -sh /var/lib/neo4j/data/transactions/* 2>/dev/null
du -sh /var/log/neo4j 2>/dev/null

# Nếu backup/dump có volume riêng, kiểm tra đúng mount đó.
```

Các path chỉ là ví dụ theo một kiểu package; dùng `server.directories.data`, `server.directories.transaction.logs.root`, `server.directories.logs` và topology triển khai thực tế để tìm vị trí chính xác. **Đừng chạy lệnh với wildcard trên filesystem lớn rồi quy tổng `du` thành database size tức thời**; nó có thể tốn I/O và chỉ là ảnh chụp tại một thời điểm.

### 5.1. Khi `df` và `du` không khớp

Có thể do:
- File đã bị xóa nhưng process còn giữ descriptor mở.
- Snapshot/overlay filesystem hoặc reserved blocks.
- Container writable layer và mounted volumes không trùng đường dẫn.
- Quota/project quota của volume.
- Inode đã hết dù bytes còn.

Cần nhờ đội OS/storage kiểm tra open files, quota và mount, **không tự kill Neo4j chỉ để “giải phóng file đã xóa”** khi chưa đánh giá rủi ro mất dữ liệu.

### 5.2. Container và Kubernetes

Khi chạy trong container, kiểm tra đồng thời:
- Memory **request/limit** và dấu hiệu `OOMKilled`; host RAM rảnh không chứng minh pod đủ limit.
- PVC capacity/usage và backing filesystem; có thể đầy **volume transaction log** trong khi volume data còn chỗ.
- Node disk pressure, ephemeral storage và log container.
- Quyền truy cập/ownership sau khi mở rộng volume hoặc chuyển mount.
- Nếu pod restart liên tục, log trước restart và Kubernetes events có thể chứa bằng chứng quan trọng.

Khi mở rộng PVC, xác minh filesystem đã thực sự resize, không chỉ nhìn capacity trên control plane.

## 6. Đọc trạng thái và cấu hình hiệu lực của Neo4j

Nếu DBMS còn phục vụ câu lệnh quản trị:

```cypher
SHOW DATABASES;
```

Trên self-managed Neo4j với quyền phù hợp, xem các setting liên quan:

```cypher
SHOW SETTINGS
YIELD name, value, isDynamic, startupValue
WHERE name IN [
  'server.memory.heap.initial_size',
  'server.memory.heap.max_size',
  'server.memory.pagecache.size',
  'dbms.memory.transaction.total.max',
  'db.memory.transaction.total.max',
  'db.memory.transaction.max',
  'server.directories.transaction.logs.root',
  'db.tx_log.preallocate',
  'db.tx_log.rotation.size',
  'db.tx_log.rotation.retention_policy',
  'db.checkpoint',
  'db.checkpoint.interval.time',
  'db.checkpoint.interval.tx'
]
RETURN name, value, isDynamic, startupValue
ORDER BY name;
```

**Không coi `SHOW SETTINGS` là công cụ có sẵn trên AuraDB**. Với cluster, kết quả phản ánh **member đang thực thi lệnh**, cần kiểm tra các thành viên liên quan nếu nghi cấu hình khác nhau.

**Dynamic ≠ persistent:** lệnh `dbms.setConfigValue` trên self-managed Enterprise chỉ đổi runtime của member hiện tại đối với những setting động; không tự ghi `neo4j.conf` hoặc áp lên toàn cluster. Khi sự cố qua đi, mọi thay đổi tạm thời cần được rà soát và đưa vào quản lý cấu hình có version/rollback.

## 7. Phân biệt các kiểu thiếu bộ nhớ

### 7.1. Java heap `OutOfMemoryError`

JVM heap lưu object của Neo4j runtime, kết quả trung gian, transaction state và một phần plugin như Graph Data Science. Nguyên nhân thường thấy:

- Một transaction dùng `UNWIND` trên list quá lớn hoặc cập nhật hàng triệu node trước commit.
- Query dùng `collect(...)`, `ORDER BY`, Cartesian product hoặc traversal path gây bùng nổ `Rows`.
- Nhiều transaction đồng thời giữ memory/lock quá lâu.
- GDS projection/algorithm hoặc plugin giữ graph lớn trên heap.
- Heap quá nhỏ so với workload **sau khi** đã tối ưu query và concurrency.

**Hướng xử lý:** trước hết xem query nào dùng heap, giảm fan-out/batch và concurrency; sau đó mới cân nhắc tăng `server.memory.heap.initial_size` và `server.memory.heap.max_size` trong ngân sách RAM thực.

```properties
# Ví dụ lab trên máy đủ RAM, KHÔNG phải cấu hình chung cho production.
server.memory.heap.initial_size=8G
server.memory.heap.max_size=8G
server.memory.pagecache.size=12G
```

Đừng cộng 8G heap + 12G page cache trên pod 16G rồi coi còn đủ cho JVM native, OS, thread, Lucene/vector index và GDS. Đo **container RSS, host RAM và GC** sau khi thay đổi.

### 7.2. Transaction memory limit bị chạm

Neo4j có ba ngưỡng phổ biến:

| Setting | Phạm vi | Khi chạm ngưỡng |
| --- | --- | --- |
| `dbms.memory.transaction.total.max` | Tổng transaction memory trong DBMS | Các transaction có thể bị terminate để bảo vệ server |
| `db.memory.transaction.total.max` | Tổng transaction memory của một database | Giới hạn theo database |
| `db.memory.transaction.max` | Một transaction | Ngăn một transaction chiếm quá nhiều memory |

**Bị terminate do transaction cap không đồng nghĩa JVM đã OOM.** Cơ chế giới hạn là hàng rào an toàn. Tăng limit không cấp thêm RAM; nếu trăm transaction đều lớn, việc nới limit có thể biến một lỗi transaction thành lỗi JVM/container nghiêm trọng hơn.

Neo4j ghi nhận mức dùng bộ nhớ transaction theo **ước lượng**, có thể sai khác thực tế khi object được chia sẻ. Nếu có false positive nghi ngờ, thử trên staging với dữ liệu giống thật và sự giám sát chặt, không tắt hàng rào an toàn trong production bằng mặc định.

### 7.3. Container/OS `OOMKilled`

Nếu kernel/cgroup kill process:
- Xem tổng RSS so với container memory limit, không chỉ `heap.used`.
- Tính thêm Neo4j page cache, memory ngoài heap, thread stacks, buffer và những tiến trình cùng cgroup.
- Sự cố có thể xuất hiện dù heap used chỉ ở 60%.
- Kiểm tra cả CPU throttling, swap và volume cạn, vì những áp lực này có thể kéo dài transaction và tăng memory giữ lại.

Không tự kết luận `OOMKilled = Java heap leak`.

### 7.4. Java client bị OOM

Nếu service Java Driver gọi:

```java
var all = session.run("MATCH (n) RETURN n").list();
```

thì **heap của ứng dụng Java** có thể hết vì materialize toàn bộ graph, trong khi heap Neo4j vẫn khỏe. Với Java Driver/SDN:
- Trả projection/DTO theo use case.
- Dùng `LIMIT`/keyset pagination để giới hạn dữ liệu hợp lệ.
- Streaming theo luồng hoặc tiêu thụ result theo batch; không `collectList()` vô hạn trong Reactor.
- Đo heap của **cả hai JVM** trước khi sửa `server.memory.heap.max_size`.

## 8. Điều tra transaction/query đang tiêu thụ tài nguyên

Với quyền quản trị trên database cần kiểm tra:

```cypher
SHOW TRANSACTIONS
YIELD transactionId, currentQuery, status, elapsedTime,
      estimatedUsedHeapMemory
RETURN transactionId, status, elapsedTime,
       estimatedUsedHeapMemory, currentQuery
ORDER BY estimatedUsedHeapMemory DESC;
```

```cypher
CALL dbms.listPools();
```

Các trường/khả năng hiển thị phụ thuộc edition/version và quyền. `estimatedUsedHeapMemory` là một **ước lượng**, không nên cộng lại thành số RAM vật lý chính xác.

Nếu nhận diện một query hoặc transaction gây mất ổn định, có thể xem xét **terminate có mục tiêu** với transaction ID thực tế, sau khi xác minh đó không phải backup/migration hay giao dịch quan trọng:

```cypher
// Chỉ dùng sau khi được phê duyệt và đã xác minh đúng transaction.
TERMINATE TRANSACTIONS 'neo4j-transaction-123';
```

**Đây là ID minh họa, không tồn tại thực.** Terminate có thể rollback thay đổi chưa commit và khiến Java Driver retry; nên đồng thời ngăn job gây lỗi khởi chạy lại. Không terminate tất cả transaction hoặc chạy truy vấn phá dữ liệu hàng loạt khi chưa hiểu hậu quả.

### 8.1. Phân tích plan của query nghi ngờ

```cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)-[:HAS_LINE]->(p:Product)
RETURN p.sku AS sku, count(*) AS lines
ORDER BY lines DESC
LIMIT 10;
```

Trên database thử nghiệm có dữ liệu mẫu và quyền tương ứng, có thể chạy `PROFILE` để xem `Rows`, `DB Hits`, sort/aggregation và memory. **`PROFILE` thực thi truy vấn thật**; không dùng cho câu ghi trên production chỉ để quan sát.

Điều cần tìm:
- Có `NodeIndexSeek` theo `customerId` hoặc quét nhãn rộng?
- `Expand(All)` có tạo rất nhiều row trung gian?
- `collect`, `Sort`, `EagerAggregation` có giữ quá nhiều state?
- Có nhiều branch một-nhiều tạo tích Descartes?
- Một API có gọi N+1 query qua repository hay không?

Đôi khi giảm từ một triệu row trung gian xuống vài nghìn bằng index/bộ lọc giúp cả heap lẫn transaction logs giảm mà **không cần tăng cấu hình**.

## 9. Sửa transaction lớn trước khi tăng heap

### 9.1. Anti-pattern: một transaction chứa cả import

```cypher
// Chỉ minh họa anti-pattern: $rows có thể là hàng triệu phần tử.
UNWIND $rows AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name;
```

Một transaction giữ các thay đổi chưa commit, index updates và intermediate states. Nếu dữ liệu đầu vào quá lớn, query có thể bị terminate bởi transaction memory cap hoặc gây OOM. Có index/uniqueness constraint cho `Product.sku` để tránh quét toàn label, nhưng index **không loại bỏ hoàn toàn** chi phí giữ transaction lớn.

### 9.2. Chia theo batch với `CALL ... IN TRANSACTIONS`

Với một nguồn rows được đọc theo luồng/`LOAD CSV`:

```cypher
LOAD CSV WITH HEADERS FROM $csvUrl AS row
CALL (row) {
  MERGE (p:Product {sku: row.sku})
  SET p.name = row.name
} IN TRANSACTIONS OF 1000 ROWS;
```

**Điều kiện:**
- `CALL (row)` là variable scope clause của Cypher mới; xác minh version hỗ trợ.
- `CALL ... IN TRANSACTIONS` cần **implicit/auto-commit transaction**, không được bọc trong `session.executeWrite(...)` managed transaction.
- Batch 1000 chỉ là ví dụ; chọn theo dữ liệu/IO và đo memory/commit latency.
- Mỗi batch commit riêng; nếu job lỗi giữa chừng, có thể đã ghi **một phần**. Dùng khóa/`MERGE` và cơ chế checkpoint/idempotency để chạy lại an toàn.
- Chia nhỏ transaction thường giảm peak heap nhưng **không đồng nghĩa giảm tổng bytes transaction log**. Số lần commit nhiều vẫn tạo hoạt động log; phải đo cả memory và tốc độ log.

### 9.3. Không chuyển OOM thành disk-full

Một sự điều chỉnh thiếu kiểm soát:

```text
Transaction 1 triệu rows -> heap OOM
    |
    +-- Chia 1.000 rows/batch -> heap ổn
                                |
                                +-- Commit liên tục, log ghi nhanh
                                +-- Checkpoint/rotation/pruning không theo kịp
                                +-- Volume transaction logs đầy
```

Vì thế, cùng một kế hoạch import phải có **hai ngân sách**: peak memory/transaction và disk write/log-growth headroom. Tính thêm index build, backup, log rotation và thời gian checkpoint.

## 10. Khi ổ đĩa đầy: hành động nào an toàn?

### 10.1. Những việc nên làm theo thứ tự

1. **Tạm dừng nguồn ghi** đang làm tình trạng xấu đi, gồm import, test load, API writes ngoài thiết yếu.
2. Xác định **filesystem đầy**: dữ liệu chính, transaction logs, log quan sát, backup, mount bên ngoài hay overlay.
3. Kiểm tra **byte, inode, quota, PVC limit**, dung lượng đĩa thực được cấp và log lỗi.
4. Ưu tiên **mở rộng volume / cấp thêm dung lượng** theo quy trình storage/Kubernetes; giữ nguyên sự nhất quán của filesystem.
5. Nếu cần giải phóng chỗ, chỉ xử lý **artifact ngoài Neo4j đang hoạt động**, ví dụ backup cũ đã vượt retention được owner chấp thuận, file export/tạm độc lập đã đối chiếu, hoặc log ứng dụng ngoài Neo4j theo cơ chế rotation được quản lý.
6. Đợi Neo4j có điều kiện thực hiện checkpoint/pruning **theo cơ chế của nó**, nếu phù hợp.
7. Kiểm tra startup/health, consistency và backup sau sự cố.

**Không “dọn nhanh” bằng `rm data/transactions/*`, `rm data/databases/*` hay `rm data/cluster-state/*`.** Việc đó có thể làm mất khả năng recovery, backup, CDC catch-up hoặc phá sự nhất quán của cluster.

### 10.2. Vì sao chỉ trống vài MB chưa đủ?

Neo4j cần thêm dung lượng cho:
- Transaction log preallocation/rotation.
- Checkpoint flush, recovery và file metadata.
- Chỉ mục, temporary spill và các transaction đang chờ.
- Log quan sát, backup/dump hoặc index rebuild.

Vì vậy phải có **headroom đủ lớn theo tốc độ tăng thực tế**. Nếu import đang tạo 300 MiB log/phút và đĩa chỉ còn 100 MiB, một lần resume sẽ làm nó đầy lại gần như ngay lập tức.

### 10.3. Khi database đã `OFFLINE`

Không giả định chỉ tăng dung lượng là đủ chữa mọi lỗi; hãy:
- Thu `neo4j.log`, `debug.log` và OS storage errors.
- Xác định có corruption, transaction log thiếu hay checkpoint dở không.
- Khôi phục đúng dung lượng, quyền file và đường dẫn.
- Thực hiện startup/recovery theo tài liệu; nếu lỗi integrity, dùng backup/recovery runbook đã diễn tập.
- Kiểm tra bằng lệnh consistency trên **database offline hoặc artifact đủ điều kiện**, không chạy trên store đang mount.
- **Không đặt `db.recovery.fail_on_missing_files=false` để lờ đi log thiếu** trừ khi đang làm việc theo quy trình phục hồi được phê duyệt và hiểu nguy cơ integrity; mặc định an toàn là thất bại khi thiếu file cần thiết.

## 11. Transaction logs: cơ chế rotation → checkpoint → pruning

Transaction log lưu các bản ghi thay đổi của từng database để Neo4j có thể khôi phục sau crash và hỗ trợ backup/cluster/CDC.

```text
Transaction writes
      |
      v
Active transaction log
      | (đạt db.tx_log.rotation.size)
      v
Log rotation --> log mới
      |
      v
Checkpoint: ghi những trang dirty cần thiết xuống store
      |
      v
Kiểm tra retention + điểm checkpoint hợp lệ
      |
      v
Pruning: Neo4j tự dọn các log cũ đủ điều kiện
```

Hai điều kiện tối thiểu để một file transaction log có thể được prune:

1. File đã được **rotate**, không còn là log hiện hành.
2. Có **checkpoint mới hơn ở một file log khác**, bảo đảm store đã được flush đủ để không cần log cũ khi recovery.

Vì vậy, **retention là chính sách**, không phải một giới hạn dung lượng vật lý cứng được thực thi ngay lập tức. Neo4j chỉ xem xét pruning sau khi checkpoint hoàn tất; nếu checkpoint chậm, tắc hoặc không xảy ra, log có thể tăng **vượt xa dung lượng retention dự định**.

### 11.1. Các setting chính (kiểm tra lại trên phiên bản thực)

| Setting | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `server.directories.transaction.logs.root` | Thư mục gốc lưu transaction logs | Có thể đặt trên volume riêng, cần cấu hình và di chuyển có kế hoạch |
| `db.tx_log.preallocate` | Có preallocate file log không | Mặc định `true` theo tài liệu hiện hành |
| `db.tx_log.rotation.size` | Kích thước xấp xỉ trước khi rotate file | Mặc định `256 MiB`, **không giới hạn tổng log** |
| `db.tx_log.rotation.retention_policy` | Quy tắc giữ log cũ | Mặc định hiện hành `2 days 2G`; kiểm tra mỗi bản |
| `db.checkpoint` | Chọn chiến lược checkpoint | Mặc định `PERIODIC` |
| `db.checkpoint.interval.time` | Khoảng thời gian theo policy | Mặc định hiện hành `15m`, còn phụ thuộc policy |
| `db.checkpoint.interval.tx` | Số transaction giữa checkpoint khi áp dụng | Mặc định hiện hành `100000` |
| `db.checkpoint.iops.limit` | Giới hạn I/O của checkpoint | Chỉ đổi khi có ngân sách IOPS |
| `db.transaction.timeout` | Chặn transaction chạy quá lâu | Không giải quyết trực tiếp checkpoint/log thiếu |
| `dbms.memory.transaction.total.max` | Tổng memory transaction | Ngăn OOM nhưng không tạo disk space |

**Không kết luận từ `retention_policy=2 days 2G` rằng ổ đĩa sẽ không bao giờ dùng quá 2 GiB cho logs.** Policy phụ thuộc thời điểm checkpoint, rotation và điều kiện giữ log phục vụ các hoạt động khác.

### 11.2. Retention và backup/CDC/cluster

Transaction logs không chỉ phục vụ crash recovery:
- Enterprise differential backup cần đủ logs để chuyển thay đổi từ lần backup trước.
- Cluster catch-up dùng các log phù hợp khi một member bị trễ; log mất sớm có thể dẫn tới phải store-copy toàn bộ.
- CDC/consumer phụ thuộc retention để tiếp tục từ điểm thay đổi đã đọc.

Rút retention quá ngắn có thể **giảm disk usage nhưng tăng rủi ro mất khả năng differential backup, CDC catch-up hoặc replica catch-up**. Cần đối chiếu SLA và thời gian offline tối đa của các consumer/member trước khi thay đổi.

## 12. Vì sao transaction logs không được prune như mong đợi?

| Giả thuyết | Bằng chứng cần thu | Việc nên làm |
| --- | --- | --- |
| **Write throughput tăng đột biến** | Bytes appended/s, số transaction/s, job deployment | Xác định job/điểm bắt đầu, giảm tốc import |
| **Checkpoint chưa chạy hoặc thất bại** | Checkpoint completion, lỗi trong debug.log | Xử lý disk, I/O, lock/OS và lỗi storage trước |
| **Checkpoint chạy quá lâu** | Checkpoint duration gần khoảng giữa checkpoint, disk queue | Đo IOPS/latency và nguồn ghi cạnh tranh |
| **File quá lớn chưa rotate** | File count/size, `db.tx_log.rotation.size` | Kiểm tra rotation và điều kiện checkpoint mới hơn |
| **Retention để `keep_all`** | `SHOW SETTINGS`, file config | Điều chỉnh chính sách có cân nhắc backup/CDC |
| **Retention thay đổi runtime chưa persist** | `value` khác `startupValue`, config management | Đồng bộ cấu hình theo quy trình |
| **Backup/CDC/replica lag** | Lịch backup, backup success, CDC lag, raft/tx lag | Tránh cắt log cần cho downstream; giải quyết backlog |
| **Volume thật đầy bởi nơi khác** | `df` và `du`, backup/export/container logs | Xử lý đúng filesystem và artifact |
| **Log preallocation gây size nhảy bậc** | Tốc độ rotate, kích thước file mới | Phân biệt reserved space với dữ liệu transaction thật |

**Chưa có bằng chứng thì không chọn “xóa log cũ nhất”**. File cũ nhất nhìn bằng timestamp OS không tự cho biết còn cần cho crash recovery hoặc chain backup không.

## 13. Chẩn đoán checkpoint và pruning từng bước

### 13.1. Đọc tình trạng, không vội ép checkpoint

Quan sát:
1. Có checkpoint gần nhất thành công lúc nào?
2. `checkpoint duration` có tăng cùng với I/O wait không?
3. DBMS báo lỗi ghi, fsync hoặc `ENOSPC` không?
4. File log đã rotate chưa?
5. Retention hiện có và các điều kiện backup/CDC/cluster là gì?

Nếu volume đang **hoàn toàn đầy**, ép checkpoint có thể cũng thất bại vì cần flush và ghi metadata/log. Đưa hệ thống về trạng thái còn dung lượng đủ và ổn định trước.

### 13.2. Force checkpoint khi đã giải quyết nguyên nhân

Trên database đúng, sau khi đã đủ disk, I/O hoạt động, không còn lỗi storage, operator có thể cân nhắc:

```cypher
// Không chạy trên volume đang đầy hay database đang gặp corruption.
// Chạy trong database mục tiêu, sau khi có quyền và kế hoạch vận hành.
CALL db.checkpoint();
```

Lệnh yêu cầu checkpoint, **không bảo đảm lập tức dọn tới đúng mức retention**; phải đáp ứng điều kiện rotation và policy. Nếu lệnh thất bại, đọc log và dừng thử lặp vô hạn.

Nếu checkpoint thường xuyên kéo dài, không mặc định tăng `db.checkpoint.iops.limit`: khi disk đã bão hòa, tăng tốc flush có thể làm latency commit hoặc query xấu hơn. Cần đo IOPS headroom.

### 13.3. Thay retention có kế hoạch

Ví dụ một chính sách thay thế được review:

```properties
# neo4j.conf — chỉ là ví dụ để so sánh chính sách.
db.tx_log.rotation.retention_policy=2 days 2G
db.tx_log.rotation.size=256M
```

Không sao chép giá trị vào production chỉ để “giảm logs”; đây gần với mặc định của Neo4j hiện hành. Những dạng khác như `10 files`, `30 days`, `500k txs` hoặc `keep_all` cần được thiết kế dựa trên RPO/backup/cluster/CDC.

**`keep_none`/`false` không phải biện pháp khẩn cấp mặc định**: nó chỉ giữ log hiện hành tối thiểu, có thể khiến Enterprise differential backup hoặc CDC không tiếp tục được. Nếu sử dụng trong một kịch bản import lab đã đánh giá rủi ro, cần khôi phục retention sau import và xác minh backup/consumer. Không dùng khi đang xử lý sự cố chưa rõ backup chain.

### 13.4. Log monitoring khác transaction log

Có thể cấu hình rotation/retention của `query.log`, `debug.log` theo **Log4j 2** và setting liên quan. Việc dọn query log theo quy trình log management **không giống** việc xóa file transaction log. `debug.log` cần được giữ để hỗ trợ điều tra; từ Neo4j 2025.01 định dạng mặc định JSON, nên script parse log cũ phải xem version.

Nếu log quan sát chiếm nhiều dung lượng, xác nhận log nào đang tăng, mức `VERBOSE`/threshold và parameter logging. Không bật log chứa mật khẩu/PII hoặc xóa chứng cứ khi incident chưa kết thúc.

## 14. Những metric cần xem cùng nhau

| Nhóm | Metric/đo đạc | Ý nghĩa |
| --- | --- | --- |
| Host/container | Free bytes, free inode, RSS, memory limit, swap/OOM | Nguy cơ cạn tài nguyên thật |
| JVM heap | `dbms.vm.heap.used`, `max`, GC time/pause | Heap có đạt ngưỡng và GC làm chậm request không |
| Page cache | `dbms.page_cache.hit_ratio`, `usage_ratio`; `page_cache.page_faults` | Cache thiếu hay query đọc quá rộng |
| Transaction | Started/committed/rolled back, active, memory estimate | Workload tăng hay transaction bị giữ lâu |
| Transaction log | `log.appended_bytes`, `log.rotation_events`, `log.rotation_duration` | Tốc độ sinh log và dấu hiệu rotation |
| Checkpoint | `database.<db>.check_point.duration` và count/events | Checkpoint có theo kịp workload không |
| Store size | `store.size.database` và `store.size.full` | Dung lượng data store so với data + transaction logs |
| Client Java | Pool wait, retry, p95/p99, request error, JVM heap | Lỗi ở client hoặc retry storm |
| Storage | IOPS, read/write await, utilization, quota | Disk thực sự nghẽn hay hết chỗ |

Những tên trên là **hậu tố hoặc minh họa trong hệ metrics**; prefix và sự sẵn có phụ thuộc Neo4j version, edition và loại exporter. Neo4j Enterprise có tài liệu đầy đủ hơn về CSV/JMX/Prometheus; AuraDB cung cấp metrics theo gói dịch vụ.

### 14.1. Đổi counter thành tốc độ

```text
log_bytes_per_second =
  (log.appended_bytes tại t2 - tại t1) / (t2 - t1)

page_faults_per_second =
  (page_faults tại t2 - tại t1) / (t2 - t1)
```

Ví dụ **giả định**: log appended tăng 9 GiB trong 30 phút; tốc độ trung bình khoảng 307 MiB/phút. Nếu volume chỉ còn 2 GiB và nguồn ghi không đổi, headroom rất ngắn. **Đó không phải bằng chứng file log sẽ tăng đúng cùng tốc độ**: pruning, rotation, checkpoint và các job khác còn ảnh hưởng footprint thực.

Đừng suy từ **counter tổng** rằng hiện tại đang tăng nhanh; phải đo chênh lệch trong cùng cửa sổ, xét reset sau restart.

### 14.2. Ngưỡng cảnh báo phải có lead time

Đặt ngưỡng theo:
- Free disk bytes và **thời gian dự kiến tới khi đầy** ở tốc độ tăng gần đây.
- Đỉnh memory/RSS và thời gian GC pause.
- Checkpoint duration so với checkpoint interval.
- Differential backup lag, CDC backlog và replica catch-up lag.
- SLO request p95/p99/error và write availability.

Ví dụ cảnh báo khi storage có nguy cơ đầy trong vài giờ, **không đợi `free disk=0`**. Mức phần trăm đơn thuần không phản ánh tốc độ tăng; 10% trống của volume 10 TiB khác hẳn 10% của volume 10 GiB.

## 15. Kịch bản thực hành A: `UNWIND` khổng lồ gây OOM

Giả định ứng dụng gửi danh sách một triệu sản phẩm vào một transaction và gặp memory cap.

**Bước xác minh:**
1. Tìm currentQuery/estimated memory của transaction.
2. Kiểm tra `EXPLAIN`, index `Product.sku` và cardinality.
3. Xem GC, JVM heap, tổng memory các job cùng lúc.
4. Xác định transaction có commit hay bị rollback; không đoán từ error string một cách tùy tiện.

**Giải pháp theo thứ tự:**
- Đưa dữ liệu vào file/stream được Neo4j cho phép, xử lý theo batch.
- Chọn batch size dựa trên memory và số write/row.
- Thêm uniqueness constraint cho khóa phù hợp.
- Giới hạn concurrency của job.
- Theo dõi transaction log growth/checkpoint khi chuyển sang batch.
- Chỉ điều chỉnh heap/transaction limits nếu đã chứng minh workload hợp lý mà thiếu tài nguyên.

**Không dùng `db.memory.transaction.max=0` như cách “khắc phục” mặc định.** Bỏ giới hạn có thể đẩy server tới OOM.

## 16. Kịch bản thực hành B: transaction log tăng 40 GiB qua một đêm

Các con số sau là **giả định**:

| Tín hiệu | Số liệu thu thập |
| --- | --- |
| Database | `orders`, Enterprise, còn `ONLINE` |
| Dung lượng log trước batch | 3 GiB |
| Dung lượng log sau batch | 43 GiB |
| Retention hiện tại | `2 days 2G` |
| Số commit/s | Tăng 20 lần |
| Checkpoint duration | Tăng mạnh, có checkpoint chưa hoàn thành |
| Disk free | 8 GiB |

**Không thể kết luận retention đã bị Neo4j “bỏ qua”** chỉ vì log >2 GiB. Có thể:
- Batch tăng transaction bytes rất nhanh.
- Log chưa đủ điều kiện prune vì checkpoint chậm.
- Disk bận ghi nên checkpoint chưa kết thúc.
- Có CDC/differential backup/catch-up cần logs.
- Một số file chưa rotate.

**Kế hoạch xử lý:**
1. Ngừng batch import không thiết yếu.
2. Thu checkpoint logs/metrics, tình trạng disk và backup.
3. Mở rộng dung lượng nếu mức dự trữ không đủ để checkpoint an toàn.
4. Giải quyết I/O hoặc job gây chậm checkpoint.
5. Đợi rotation/checkpoint/pruning theo cơ chế Neo4j; chỉ cân nhắc `CALL db.checkpoint()` sau khi đã có đủ điều kiện.
6. Xác minh log size ổn định, backup/CDC không bị hỏng, database có thể ghi lại.
7. Điều chỉnh batch rate và capacity; không dựa vào một thay đổi retention để che chi phí nhập dữ liệu.

## 17. Kịch bản thực hành C: Kubernetes `OOMKilled` nhưng heap chỉ dùng 6 GiB

Giả định:
- Pod memory limit 16 GiB.
- JVM heap max 8 GiB, heap used cao nhất 6 GiB.
- Page cache 10 GiB.
- Native/JVM overhead và sidecar còn dùng memory.

Như vậy, **đã cấp heap max + page cache = 18 GiB vượt pod limit**, chưa tính native/sidecar. Pod có thể bị kernel kill mặc dù JVM chưa đạt `-Xmx`.

Hướng giải quyết:
1. Xem pod events, RSS/cgroup và `OOMKilled`.
2. Dừng batch nặng và hạ concurrent load trong thời gian xử lý.
3. Dựa trên **pod limit**, lập ngân sách heap + page cache + native + OS/sidecar.
4. Cân nhắc giảm page cache hoặc tăng memory limit theo năng lực cluster, thay đổi một biến có kiểm soát.
5. Restart theo runbook khi cần, theo dõi cache warm-up và trạng thái database/recovery.
6. Chạy lại load test cùng lưu lượng, đo GC, page faults, p95/p99 và OOM.

Đừng tăng heap lên 12 GiB vì nhìn thấy từ “OOM” trong Kubernetes; việc đó có thể làm tổng memory vượt limit nặng hơn.

## 18. Java Driver/Spring Data Neo4j: tránh làm nặng thêm incident

### 18.1. Vòng retry có giới hạn

Java Driver có managed transaction:

```java
try (var session = driver.session(
        org.neo4j.driver.SessionConfig.forDatabase("neo4j"))) {

    session.executeWriteWithoutResult(tx ->
        tx.run("""
            MERGE (o:Order {orderId: $id})
            ON CREATE SET o.status = 'NEW'
            """, java.util.Map.of("id", "o9001"))
          .consume()
    );
}
```

Callback có thể bị driver retry sau lỗi transient, vì vậy:
- Dùng **unique constraint** trên business key.
- Không gửi email/charge payment trực tiếp bên trong callback.
- Giới hạn retry budget, concurrency và queue depth ở ứng dụng.
- Khi disk đầy hoặc Neo4j offline, **trả lỗi rõ/đưa hàng đợi có kiểm soát**, không để 100 instance đồng thời retry liên tục.
- Nếu phản hồi write bị mất, phải xác minh trạng thái theo business ID; timeout không chứng minh chưa commit.

### 18.2. Session/result lifecycle

- **Driver** là đối tượng dùng chung, có connection pool.
- **Session** sống ngắn theo operation và phải đóng.
- **Result** phải được consume trong phạm vi transaction/session.
- Trong Java Driver async, đóng bằng `closeAsync()` sau khi stage hoàn tất.
- Trong reactive, gắn cleanup vào vòng đời publisher và cancellation.
- Không dùng `list()`/`collectList()` để tải hàng triệu node vào client heap.
- Với Spring Data Neo4j, tránh hydrate entity graph sâu nếu API chỉ cần vài field; dùng DTO/projection và phân trang.

Trên hệ thống đang thiếu bộ nhớ, một REST endpoint đọc toàn graph hoặc một batch writer quá lớn có thể làm **cả client và server** thiếu RAM.

## 19. Khi nào cần backup/restore và kiểm tra tính nhất quán?

Tình trạng **transaction log tăng** không tự đồng nghĩa dữ liệu hỏng. Nhưng nếu đĩa đầy làm database offline hoặc log thiếu/corrupt, cần kích hoạt quy trình recovery.

| Tình trạng | Hướng xử lý |
| --- | --- |
| DBMS `ONLINE`, log tăng nhưng store khỏe | Đo write/checkpoint/pruning; giải quyết tải và dung lượng |
| Disk full, database mất khả năng ghi | Giảm tải, tăng dung lượng, thu log; kiểm tra trạng thái rồi mới resume |
| Restart xong database trở lại `ONLINE` | Đối soát transaction/schema, theo dõi I/O/log và làm backup |
| Startup báo missing/corrupt transaction log | **Không tự xóa log còn lại**; dùng recovery runbook và đánh giá backup |
| Store inconsistency | Dừng/nhân bản môi trường theo quy trình; chạy `neo4j-admin database check` trên store offline hoặc artifact phù hợp |
| Mất volume hoặc database không thể cứu | Restore từ backup hợp lệ, kiểm tra consistency, schema và ứng dụng |

**Chỉ chạy `neo4j-admin database check` trên database không còn được DBMS sử dụng**, hoặc backup/dump đủ điều kiện theo tài liệu. Không dùng lệnh này như một “health query” live.

Với Enterprise, online full/differential backup phụ thuộc transaction logs đủ dài; với Community, offline dump/load có giới hạn khác. Cluster có thể giúp failover khi một member bị lỗi disk, nhưng **không thay thế backup**, vì các giao dịch xóa nhầm hợp lệ có thể được replicate.

## 20. Checklist khôi phục và nghiệm thu sau incident

### 20.1. Cổng nghiệm thu kỹ thuật

1. Filesystem data/transactions/logs/backup có headroom hợp lý, inode/quota bình thường.
2. DBMS và database cần thiết `ONLINE`, không có lỗi corruption hoặc missing logs.
3. JVM/RSS/GC ổn định, không có `OOMKilled`/`OutOfMemoryError` mới.
4. Transaction memory không vượt ngân sách; các job lớn đã được điều tiết.
5. Checkpoint thành công, log rotation/pruning diễn ra bình thường.
6. Backup gần nhất còn phục hồi được; CDC/replica có khả năng tiếp tục catch-up.
7. `SHOW INDEXES`/`SHOW CONSTRAINTS` và dữ liệu graph đạt kiểm tra nghiệp vụ.
8. Java Driver và SDN thực thi read/write canary với credentials ít quyền.
9. p95/p99, throughput và error rate đạt SLO; không có retry storm.
10. Các thay đổi config khẩn cấp được lưu/rollback đúng quy trình.

### 20.2. Bảng ghi chép incident

| Trường | Ví dụ minh họa |
| --- | --- |
| Incident ID | `neo4j-disk-memory-2026-11` |
| Database/members | `orders` trên 3 primary |
| Triệu chứng đầu | `ENOSPC` và write timeout |
| Thời điểm phát hiện | Timestamp UTC, kèm timezone báo cáo |
| Nguồn ghi bất thường | Batch import mới triển khai |
| Heap/cgroup | Used, max, RSS, pod limit |
| Disk | Free bytes/inodes, mount bị đầy |
| Transaction logs | Bytes, append rate, rotation count |
| Checkpoint | Lần thành công gần nhất, duration, lỗi |
| Can thiệp | Ngừng batch, tăng volume, điều chỉnh tốc độ |
| Điều kiện mở lại | DB `ONLINE`, checkpoint/log ổn, read/write canary PASS |
| RPO/RTO thực tế | Ghi số đo, không điền theo mục tiêu |
| Hậu kiểm | Sửa job, capacity alert, diễn tập và owner |

**Không đóng incident chỉ vì đã xóa được vài file hoặc một request thành công**. Phải chứng minh hệ thống không tăng log/bộ nhớ ngoài khả năng chịu đựng khi load bình thường trở lại.

## 21. Phòng ngừa theo vòng đời ứng dụng

### 21.1. Trước triển khai job lớn

- Đếm node/relationship và tốc độ import, tính tổng lượng ghi/byte transaction dự kiến.
- Ước lượng heap của job và transaction state, chọn batch size có thể rollback/retry.
- Có uniqueness constraint/index cho khóa `MERGE`.
- Xác nhận free space trên **đúng filesystem** cho logs, store, backup.
- Đảm bảo checkpoint và retention hỗ trợ CDC/differential backup/cluster catch-up.
- Đặt concurrency limit, timeout, rate limit và phương án tạm dừng job.
- Thử trên dataset thể hiện high-degree nodes và property payload lớn.

### 21.2. Alert vận hành

- Cảnh báo trên **time-to-full** của disk/log volume, không chỉ phần trăm trống.
- Cảnh báo JVM heap/GC, cgroup RSS và OOMKilled.
- Cảnh báo checkpoint quá chậm hoặc nhiều lần thất bại.
- Cảnh báo transaction log append rate tăng so với baseline.
- Cảnh báo backup/CDC/cluster lag nếu retention có nguy cơ không đủ.
- Cảnh báo Java Driver retry/pool wait tăng cùng lúc database lỗi.
- Kiểm tra backup restore định kỳ thay vì chỉ tin kết quả backup job.

### 21.3. Sau nâng cấp Neo4j

- Xác minh tên setting hiện hành và giá trị `startupValue`/`value`.
- Rà soát retention defaults và checkpoint policy của phiên bản mới.
- Đối chiếu log format và cách export metrics.
- Kiểm tra filesystem mount, permissions và cấu hình container.
- Chạy lại benchmark có read/write mix thật; so kết quả trước/sau.

## 22. Những ngộ nhận nguy hiểm

| Ngộ nhận | Thực tế |
| --- | --- |
| “`OutOfMemoryError` nghĩa phải tăng `-Xmx` ngay.” | Có thể do query quá rộng; tăng heap chỉ trì hoãn lỗi hoặc lấy RAM của page cache |
| “`OOMKilled` là do heap đã đầy.” | Pod/host giới hạn **toàn bộ RSS/cgroup**, không chỉ heap |
| “Transaction limit bị chạm nghĩa database cần thêm RAM.” | Limit có thể đang bảo vệ server; cần giảm transaction size trước |
| “Page cache trống thì heap sẽ tự dùng phần đó.” | Hai vùng được quản lý riêng, phải có ngân sách RAM |
| “Disk đầy thì xóa file log lâu đời nhất.” | **Không xóa transaction logs thủ công** vì phụ thuộc recovery/checkpoint/backup/CDC |
| “`2 days 2G` bảo đảm logs dưới 2 GiB.” | Pruning chỉ sau checkpoint/rotation hợp lệ; còn file active và backlog |
| “Cứ tăng `db.tx_log.rotation.size` để logs ít hơn.” | Log file lớn hơn có thể trì hoãn điều kiện prune |
| “Tăng checkpoint IOPS luôn tốt.” | Có thể cạnh tranh với commit khi storage bão hòa |
| “Force checkpoint liên tục chữa disk full.” | Khi đĩa đầy hoặc I/O lỗi, checkpoint có thể thất bại |
| “Đặt retention `keep_none` là vô hại.” | Có thể phá differential backup/CDC/cluster catch-up |
| “`query.log` và transaction log là một.” | Query log là quan sát; transaction log phục vụ recovery |
| “Chia batch thì tổng log chắc chắn giảm.” | Batch giảm peak transaction state; nhiều commit vẫn có log overhead |
| “`SHOW SETTINGS` trên một member chứng minh toàn cluster giống nhau.” | Setting runtime có thể khác giữa member |
| “Đã restart thành công là không mất data.” | Cần kiểm tra consistency, counts, transaction và backup |
| “Retry cho đến khi hết lỗi là tốt.” | Có thể gây retry storm, duplicate effects hoặc giữ tài nguyên |
| “Tăng PVC xong thì có thể resume hết job ngay.” | Phải xác minh filesystem resize, checkpoint/pruning, nguyên nhân gốc |

## 23. Bài tập tự luyện

1. Một Neo4j pod có memory limit 16 GiB, heap max 8 GiB và page cache 10 GiB. Vì sao pod có thể `OOMKilled` dù heap used chỉ 5 GiB? Nêu cách đo.
2. Một job `UNWIND $rows` trong một transaction bị memory cap terminate. Hãy thiết kế batch import và giải thích vì sao không nên chỉ tăng `db.memory.transaction.max`.
3. Transaction logs của database `orders` tăng từ 4 GiB lên 34 GiB trong hai giờ, retention là `2 days 2G`. Liệt kê tối thiểu bốn giả thuyết cần kiểm tra trước khi sửa config.
4. Giải thích hai điều kiện cần để Neo4j prune transaction log cũ. Vì sao retention không phải hard disk cap?
5. Một hệ thống có `df -h` báo 80% free nhưng `ENOSPC` vẫn xuất hiện. `df -i`, quota và mounted volume có thể giải thích ra sao?
6. Một team đề xuất `rm -rf data/transactions/orders/*` để lấy lại 20 GiB. Hãy giải thích rủi ro và trình tự xử lý an toàn hơn.
7. Khi nào `CALL db.checkpoint()` có thể là thao tác hợp lý, và vì sao không nên chạy khi volume đang đầy?
8. Một Java service gọi `Result.list()` trên 5 triệu node. Database JVM heap khỏe nhưng Java container OOM. Nên sửa phía nào trước?
9. Differential backup hôm qua thành công, CDC consumer đang lag 6 giờ. Nếu đổi `db.tx_log.rotation.retention_policy=keep_none`, có những hệ quả nào?
10. Viết câu `SHOW TRANSACTIONS` để tìm các transaction có memory estimate lớn và giải thích vì sao không được coi metric đó là RAM vật lý chính xác.
11. Thiết kế hai ngưỡng cảnh báo: một theo **disk time-to-full**, một theo **checkpoint duration**; nêu điều kiện cần để tránh false positives sau restart.
12. Lập runbook 30 phút cho tình huống `disk full + write timeout`, phân biệt hành động được phép và bị cấm, ghi rõ điều kiện mở traffic trở lại.

## 24. Ghi nhớ

- **Phân loại đúng lỗi**: JVM heap OOM, transaction cap, container OOMKill, page cache và disk đầy là các vấn đề khác nhau.
- **Ngăn nguồn ghi gây áp lực trước**, giữ bằng chứng và đo tài nguyên theo đúng database/volume/member.
- **Không xóa thủ công transaction logs hoặc store files**. Rotation, checkpoint và retention do Neo4j điều phối để bảo đảm recovery.
- `db.tx_log.rotation.retention_policy` là chính sách giữ log, **không bảo đảm kích thước vật lý luôn dưới ngưỡng** khi checkpoint/rotation chưa hoàn tất.
- Rút retention quá ngắn có thể làm **differential backup, CDC và cluster catch-up** gặp sự cố.
- Sửa query/index, giảm fan-out, chia batch và kiểm soát concurrency **trước khi tăng heap/transaction limits tùy ý**.
- Khi disk đầy, ưu tiên **mở rộng đúng volume, dừng nguồn ghi và khôi phục checkpoint an toàn**, không ép restart/force checkpoint liên tục.
- Quan sát `SHOW TRANSACTIONS`, `dbms.listPools`, log, metrics, `EXPLAIN`/`PROFILE` và cả memory Java client.
- Chỉ khôi phục API ghi sau khi database khỏe, dữ liệu được đối soát, backup/CDC không bị bỏ quên và các metric ổn định.
- **Diễn tập và cảnh báo có lead time** giúp tránh chuyển một lỗi tài nguyên nhỏ thành sự cố mất dữ liệu.

### Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
- [Neo4j Operations Manual — Transaction logging](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-logs/)
- [Neo4j Operations Manual — Checkpointing and log pruning](https://neo4j.com/docs/operations-manual/current/database-internals/checkpointing/)
- [Neo4j Operations Manual — Database transactions](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)
- [Neo4j Operations Manual — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Neo4j Operations Manual — Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
- [Neo4j Operations Manual — Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Operations Manual — Dynamic configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/dynamic-settings/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Consistency checker](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Data Ingestion Guide — Transactional and concurrent Cypher ingestion](https://neo4j.com/docs/data-ingestion-guide/best-practices/transactional-and-concurrent-cypher-ingestion/)
- [Neo4j Java Driver Manual — Managed transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
