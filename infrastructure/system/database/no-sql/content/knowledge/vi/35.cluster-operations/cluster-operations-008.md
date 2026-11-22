# Chính sách lưu log, dọn snapshot và phòng ngừa đầy đĩa

Một cụm NoSQL có ba node đang phục vụ bình thường. Trong vài tuần, dữ liệu tăng đều, các bản snapshot dùng cho backup được giữ lại, các ứng dụng Java ghi log truy vấn ở mức DEBUG, và một consumer CDC bị dừng khiến log nguồn không thể được giải phóng theo lịch dự kiến. Đến sáng thứ Hai, ổ đĩa của một node đạt 98%. Người trực ca thấy thư mục `commitlog` và `snapshots` rất lớn nên định xóa những file cũ nhất để “giải phóng nhanh 100 GB”.

Đó có thể là **một quyết định gây mất dữ liệu hoặc phá vỡ khả năng phục hồi**. File có tên “log” không nhất thiết là log để đọc cho con người; nó có thể là write-ahead log phục vụ crash recovery, history để replica/CDC bắt kịp hoặc thành phần của một checkpoint đang hoạt động. Snapshot có thể là bản sao duy nhất còn cho mục tiêu khôi phục; nó cũng có thể sử dụng hard link hoặc cơ chế copy-on-write khiến dung lượng “hiển thị” khác dung lượng vật lý thực sự được giải phóng sau dọn dẹp.

Trong chương **Vận hành cụm** của module **Database No SQL**, bài học này giải thích ba nhiệm vụ liên quan chặt chẽ:

1. Thiết kế **chính sách lưu và luân chuyển log** theo mục đích, chủ sở hữu và yêu cầu retention.
2. Thiết kế **vòng đời snapshot/backup** để dọn đúng dữ liệu hết hạn mà vẫn đáp ứng RPO, RTO và khả năng khôi phục.
3. **Phòng ngừa đầy đĩa** bằng đo tốc độ tăng trưởng, dự báo, alert, headroom, admission control và runbook an toàn.

Nội dung áp dụng cho NoSQL tự vận hành, triển khai Kubernetes và dịch vụ managed, nhưng lệnh và khả năng xóa phải luôn được đối chiếu với sản phẩm, phiên bản, topology và chính sách backup cụ thể.

> **Nguyên tắc cao nhất:** Không bao giờ xóa trực tiếp file bên trong data directory của database chỉ vì tên file giống log, snapshot hay temporary file. Trước khi dọn, phải biết **file do thành phần nào quản lý, có còn tham gia recovery/replication/PITR không, có bản sao khôi phục đã xác minh không và công cụ chính thức nào được phép dọn**.

## 1. Các khái niệm vận hành cần phân biệt

| Khái niệm | Mục đích | Ai thường quản lý? | Có thể xóa thủ công tùy ý không? |
|---|---|---|---|
| Application log | Ghi hoạt động service, lỗi và debug | Application/log collector | Không tùy ý; theo log policy |
| Access log | Ghi truy cập HTTP/proxy | Gateway/proxy/log pipeline | Theo retention và security |
| Audit log | Truy vết thao tác nhạy cảm | Security/audit subsystem | Không khi còn nghĩa vụ lưu |
| Slow-query/profiler log | Chẩn đoán truy vấn chậm | Database/monitoring | Theo cơ chế config của hệ |
| WAL/write-ahead log | Phục hồi mutations chưa checkpoint | Storage engine | **Không** |
| Commitlog | Bảo vệ writes trước/giữa flush | Database engine | **Không** |
| Oplog/replication history | Phục vụ replication/change streams | Replication engine | **Không** |
| CDC log/queue | Cấp dữ liệu cho change consumers | Source/connector/broker | **Không** khi chưa xác nhận checkpoint |
| Snapshot | Ảnh trạng thái dữ liệu tại mốc cụ thể | Database/backup system | Chỉ qua workflow hỗ trợ |
| Backup | Bản sao có thể phục hồi ngoài phạm vi lỗi nguồn | Backup platform/operator | Theo retention và restore evidence |
| Temp/compaction files | Không gian làm việc khi merge/rebuild | Database engine | **Không** khi engine còn dùng |
| Tombstone/deletion marker | Bảo đảm semantics của xóa/TTL/replicas | Storage engine | **Không** |

### 1.1. Log không phải một loại dữ liệu duy nhất

Một file `app.log.2026-11-01.gz` có thể là log chẩn đoán đã archive. Một file trong `commitlog/` có thể cần thiết để replay khi node crash. Cùng chữ “log”, nhưng quyền xóa và tác động hoàn toàn khác.

### 1.2. Snapshot khác backup độc lập

Snapshot lưu trên cùng volume/host vẫn có thể mất khi volume hỏng. Một backup đáng tin cho disaster recovery thường cần được sao chép tới vị trí/miền lỗi độc lập, có integrity verification và restore test.

### 1.3. Full disk là trạng thái, không phải nguyên nhân

Đầy đĩa có thể do tăng dữ liệu hợp lệ, index growth, compaction debt, snapshot giữ quá lâu, log retention sai hoặc replication/CDC checkpoint bị kẹt. Muốn sửa bền vững phải phân biệt **dung lượng đang được dùng cho việc gì**.

### 1.4. Retention là hợp đồng dữ liệu

“Giữ 7 ngày” không tự có nghĩa nên xóa mọi thứ quá 7 ngày. Mỗi lớp có một hợp đồng: log ứng dụng 7 ngày, audit 1 năm, backup theo chu kỳ, oplog theo nhu cầu replication và PITR theo chính sách.

## 2. Bản đồ những gì chiếm đĩa trong một node NoSQL

~~~mermaid
flowchart TD
    DISK["Filesystem / volume capacity"] --> LIVE["Live database data"]
    DISK --> IDX["Indexes / materialized views"]
    DISK --> LOGS["WAL / commitlog / translog / AOF"]
    DISK --> REP["Replication / CDC history"]
    DISK --> SNAP["Snapshots / backup staging"]
    DISK --> COMP["Compaction / flush / recovery temp"]
    DISK --> APP["App, audit and access logs"]
    DISK --> SYS["OS / container / filesystem overhead"]
~~~

### 2.1. Dung lượng logical không phải physical

Một collection có 300 GB dữ liệu logical có thể chiếm nhiều hơn do indexes, replicas, versions, tombstones, WAL, filesystem overhead hoặc backup snapshots. Compression có thể giảm physical bytes; compaction/rewrite có thể tăng tạm thời.

### 2.2. Replica count không đồng nghĩa capacity usable

Ba copies của một dataset không tự cho ba lần dung lượng hữu dụng. Trong cụm replicated, mỗi replica giữ phần dữ liệu của mình và có logs/snapshots riêng.

### 2.3. Đĩa hệ điều hành và data volume có thể khác

`/var/log`, container writable layer, `/var/lib/db`, backup staging và mounted object-store gateway có thể ở các filesystems khác nhau. Cần kiểm **đúng mount/volume** chạm ngưỡng.

### 2.4. Dữ liệu thực có thể vẫn tăng sau khi user xóa record

TTL/tombstone, delayed compaction, retained snapshots và replicas chưa bắt kịp khiến physical disk chưa giảm ngay. Logical delete không bảo đảm physical reclaim tức thời.

## 3. Chính sách retention bắt đầu từ mục đích phục hồi

Trước khi ấn định số ngày, trả lời:

- Nếu node crash hôm nay, phải replay log nào?
- Replica/CDC connector được phép chậm tối đa bao lâu?
- Có cần khôi phục dữ liệu tới một thời điểm trong quá khứ (PITR) không?
- RPO/RTO được business phê duyệt là bao nhiêu?
- Audit/security logs có yêu cầu pháp lý, điều tra hoặc tranh chấp nào?
- Backup nào là bản đầy đủ, incremental, base snapshot và dependency chain?
- Dữ liệu lưu ở region/tenant nào, có yêu cầu lưu giữ hoặc xóa theo chính sách riêng không?

### 3.1. RPO

**Recovery Point Objective** mô tả mức mất dữ liệu tối đa chấp nhận theo thời gian. Ví dụ RPO 15 phút là một yêu cầu; có snapshot mỗi 24 giờ **không tự đáp ứng** yêu cầu ấy nếu không có log/PITR hoặc replication phục hồi phù hợp.

### 3.2. RTO

**Recovery Time Objective** mô tả thời gian tối đa cho phép phục hồi dịch vụ. Có 30 snapshots không chứng minh RTO 30 phút: cần thời gian tìm bản sao, tải về, restore, rebuild indexes, replay logs và xác minh dữ liệu.

### 3.3. Retention theo lớp

Không dùng một biến `retentionDays=7` cho app logs, audit logs, snapshots, oplog, CDC, backups và security incidents. Mỗi lớp có purpose và owner.

### 3.4. Data lifecycle và recovery lifecycle khác nhau

TTL của Order session có thể 30 ngày, nhưng backup có thể giữ lịch sử theo policy riêng. Xóa ở primary không tự xóa ngay khỏi backup/replica/object-store; cần lifecycle/erasure policy phù hợp.

## 4. Nhóm log ứng dụng: có thể giới hạn theo thời gian và dung lượng

Java service thường ghi log4j2, Logback, SLF4J facade hoặc cấu hình của runtime/container.

### 4.1. Luân chuyển file

Thay vì một file `app.log` tăng không giới hạn, cấu hình **rolling** theo thời gian/kích thước. File đã đóng có thể được nén và dọn theo retention trong phạm vi ứng dụng quản lý.

### 4.2. Giới hạn tổng dung lượng

Retention ngày không đủ nếu mức ghi log tăng 100 lần vì lỗi lặp. Nên có **size cap** phù hợp, đồng thời có cơ chế ưu tiên giữ các log cần điều tra hơn là bật DEBUG toàn bộ.

### 4.3. Log level

DEBUG/TRACE toàn bộ request hoặc payload dễ gây disk I/O, chi phí log ingestion và rò PII. Bình thường nên dùng log levels hợp lý, sampling; khi incident bật debug có phạm vi, thời hạn và cơ chế quay về.

### 4.4. Structured log

JSON/log fields có requestId, operation, outcome, latency, instance, tenant tier giúp tra cứu mà không phải dump toàn bộ body. Không ghi password, tokens, raw queries có PII, full document hoặc secrets.

### 4.5. Không nhầm log ứng dụng với database engine log

Application có thể sở hữu thư mục `/var/log/myapp` và rolling policy. Nó **không** được tự nhận quyền dọn file bên trong data directory của MongoDB/Cassandra/Redis.

## 5. Ví dụ Logback: time + size rolling

Ví dụ cấu hình **log ứng dụng** của một Java service, không dùng cho database data/WAL:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>4GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Các ngưỡng là **ví dụ**, không phải khuyến nghị production. Cần kiểm phiên bản Logback và quyền file system; nếu chạy trong Kubernetes, nhiều hệ ưu tiên stdout/stderr để log agent thu thập, tránh tự quản rolling file trên writable layer.

### 5.1. `maxHistory` và `totalSizeCap`

`maxHistory` giới hạn độ tuổi các archive theo rolling policy; `totalSizeCap` bổ sung trần tổng archive. Cả hai không thay nhu cầu security/audit retention ở nơi lưu trữ trung tâm.

### 5.2. App restart và active file

Rolling policy có lifecycle riêng. Không tự `rm` file đang được process giữ mở vì vẫn có thể tiếp tục chiếm disk qua file descriptor cho đến khi đóng.

### 5.3. Nhật ký bảo mật cần pipeline riêng

Security audit logs có thể phải được ship tới hệ immutable/controlled retention trước khi local rotation. Đừng gộp audit vào size cap của debug logs nếu policy yêu cầu giữ.

### 5.4. Khi log collector bị nghẽn

Appender/agent phải có bounded queues, backpressure hoặc fallback policy rõ; không cho hàng đợi log trong bộ nhớ/đĩa tăng vô hạn làm sập ứng dụng chính.

## 6. Access log, audit log và slow-query log

| Loại | Mục tiêu | Lưu ý |
|---|---|---|
| Access log | Ai gọi API, thời điểm, trạng thái, latency | Có thể rất lớn theo RPS |
| Audit log | Ai sửa/xóa dữ liệu, quyền, cấu hình | Cần toàn vẹn và retention theo policy |
| Slow-query log | Truy vấn nào chậm, plan/cost | Lưu data nhạy cảm nếu log raw query |
| Error log | Sự cố, retry, stack traces | Tránh ghi hàng triệu bản sao lỗi giống nhau |
| CDC processing log | Connector progress, retries, DLQ | Không thay actual CDC event retention |

### 6.1. Sampling slow-query

Ghi toàn bộ query chậm có thể làm sự cố tệ hơn khi query nào cũng chậm. Dùng threshold, sampling, aggregated query shapes và bounded output.

### 6.2. Dữ liệu nhạy cảm

Một truy vấn có filter email hoặc số tài khoản; raw query text trong logs có thể vi phạm data minimization. Redaction và access controls phải là một phần log design.

### 6.3. Audit không được xóa chỉ vì volume đỏ

Nếu audit retention bắt buộc, cần offload sang đích an toàn, kiểm durable delivery và được owner phê duyệt trước khi dọn local copies.

### 6.4. Logs có thể bị mất khi pod chết

Container stdout logs và ephemeral writable layers không phải backup lâu dài. Nếu cần truy vết sự cố, dùng centralized collection cùng chính sách độ tin cậy của pipeline.

## 7. WAL, commitlog, oplog: “log” do database quản lý

Một storage engine có thể nhận write và ghi trước vào log để có thể replay khi crash; khi data files/checkpoint an toàn, engine mới quyết định phần log nào được giải phóng.

~~~mermaid
flowchart LR
    WR["Client write"] --> WL["Durable log / WAL"]
    WL --> MEM["In-memory state"]
    MEM --> FL["Flush / checkpoint"]
    FL --> DATA["Persistent data files"]
    DATA --> REC["Engine-managed log reclamation"]
~~~

Sơ đồ chỉ mô tả ý tưởng phổ biến, không khẳng định mọi NoSQL thực hiện đúng một thứ tự và ACK level.

### 7.1. Không xóa file WAL khi database đang chạy

Việc này có thể phá crash recovery, mất dữ liệu chưa checkpoint, gây corruption hoặc làm node không khởi động lại được. Hãy dùng API/chức năng chính thức, theo hướng dẫn vendor.

### 7.2. Đã flush chưa chắc được xóa mọi log

Replication, change streams, PITR và checkpoint dependencies có thể giữ history lâu hơn. Thời điểm reclaim là quyết định của engine, không của script `find old files`.

### 7.3. Đĩa đầy có thể chặn flush

Nếu không còn chỗ để flush, engine có thể không thể giải phóng log nên phát sinh vòng kẹt. Cần dự phòng headroom cho **temporary work và recovery**, không chỉ đủ chỗ cho live data.

### 7.4. Log retention là vấn đề đúng đắn

Giảm oplog/CDC window có thể làm replica/consumer chậm không bắt kịp. Tăng/giảm cần xem lag, RPO/PITR và rebuild/rebootstrap plan.

## 8. MongoDB: oplog, journaling và backup

MongoDB có storage engine journal và **oplog** trong replica set; chức năng, dung lượng và retention phụ thuộc version/configuration/deployment.

### 8.1. Oplog phục vụ replication và change streams

Một secondary hoặc change-stream consumer cần history phù hợp để bắt kịp. Nếu lag vượt oplog window, có thể cần initial sync/rebootstrap thay vì chỉ reconnect.

### 8.2. Oplog không phải application log để rotation

Không vào directory của `mongod` xóa file journal hoặc “những file cũ” trong storage engine. Cần theo dõi server metrics và cơ chế cấu hình của MongoDB thay vì thao tác filesystem tùy ý.

### 8.3. Snapshot nhất quán

Filesystem snapshot của MongoDB phải phối hợp đúng với khả năng crash consistency/backup procedure của engine, deployment/sharding và journaling. Snapshot một volume tùy thời điểm không tự chứng minh có một backup nhất quán của toàn cluster.

### 8.4. `db.stats()` không phải tổng disk accounting

Collection/storage stats có thể không bao gồm mọi files, snapshots và filesystem metadata; cần đo cả DB-level và volume-level metrics.

### 8.5. Managed MongoDB

Trong managed deployment, nhà cung cấp có thể tự quản journaling/snapshot; operator cần dùng supported backup retention/storage APIs, alerts và capacity controls thay vì đòi shell access để dọn.

## 9. Cassandra/ScyllaDB: commitlog và snapshot hard links

Cassandra/ScyllaDB dùng các cơ chế commitlog, SSTables, compaction và snapshots theo cấu hình/phiên bản.

### 9.1. Commitlog

Commitlog bảo vệ mutations trước khi flush. Không xóa commitlog segments thủ công để lấy dung lượng; engine quyết định segment nào còn cần cho recovery.

### 9.2. Snapshots có thể dựa trên hard links

Trong nhiều triển khai Cassandra, snapshot SSTables dùng hard links, tạo ảnh dữ liệu tương đối nhanh mà chưa sao chép vật lý toàn bộ bytes ngay. Nhưng **khi live SSTables bị compaction/xóa**, snapshot còn giữ tham chiếu đến bytes cũ, khiến disk usage không giảm.

### 9.3. Kích thước snapshot dễ bị hiểu nhầm

`du` trên nhiều hard-linked paths có thể có cách đếm khác nhau theo lệnh/filesystem. Dung lượng “logical” của mỗi snapshot không luôn là số bytes thực giải phóng nếu xóa snapshot ấy.

### 9.4. Dọn qua công cụ của database

Chỉ dùng các thủ tục snapshot listing/clear snapshot được phiên bản Cassandra/ScyllaDB hỗ trợ và backup policy cho phép. Không tự xóa thư mục snapshot bằng script khi chưa xác nhận ownership/backup dependency.

### 9.5. Compaction cần không gian làm việc

Một tập SSTables lớn có thể cần chỗ để viết SSTables mới trước khi reclaim cũ. Nếu volume chỉ còn vài GB, engine có thể không thực hiện compaction/cleanup dù logical data đã xóa.

## 10. Redis: RDB, AOF, rewrite và persistence budget

Redis có các chế độ persistence như RDB snapshots và Append Only File (AOF), tùy version/configuration và vai trò cache/source of truth.

### 10.1. RDB snapshot

RDB ghi một biểu diễn dữ liệu tại thời điểm snapshot. Quá trình fork/copy-on-write và ghi file mới có thể tạo **đỉnh memory/disk tạm thời**, cần headroom đủ.

### 10.2. AOF

AOF lưu lịch sử thao tác ghi theo semantics persistence; file có thể tăng trước khi rewrite/compaction. Không xóa trực tiếp AOF đang dùng để “tiết kiệm” vì có thể mất khả năng restore.

### 10.3. Rewrite và đĩa trống

Rewrite thường cần file/các phần mới trong khi dữ liệu cũ còn tồn tại. Nếu đĩa gần đầy, rewrite có thể thất bại và tạo thêm áp lực disk.

### 10.4. Cache Redis khác nguồn có thẩm quyền

Nếu Redis chỉ là cache có thể rebuild, phương án recovery có thể khác Redis lưu state nghiệp vụ duy nhất. Không áp cùng retention/durability policy cho hai vai trò.

### 10.5. Dữ liệu đã xóa logic chưa chắc giúp ngay

Key expiration/eviction, allocator fragmentation, AOF rewrite và filesystem có timing khác nhau. Đo memory/RDB/AOF/disk usage riêng.

## 11. Elasticsearch/OpenSearch và những file được engine sở hữu

Hệ tìm kiếm như Elasticsearch/OpenSearch có index segments, translog, merges, snapshots và shard replicas.

### 11.1. Segment merge cần disk headroom

Khi merges, engine có thể cần ghi segment mới trước khi loại segments cũ. Nếu đĩa gần đầy, quá trình merge/shard relocation bị ảnh hưởng và disk pressure kéo dài.

### 11.2. Disk watermarks

Cluster có thể áp chính sách phân bố shards và write protection khi vượt mức disk watermarks, tùy product/version. Cần quan sát thresholds và recovery plan; không chỉ nhìn một phần trăm `df`.

### 11.3. Không xóa index directory bằng filesystem

Engine giữ metadata, checksums, shard state và logs. Xóa file bên dưới có thể tạo inconsistency/corruption. Xóa index là **data deletion** qua API được phép, không phải tự động giải phóng temporary bytes.

### 11.4. Snapshot repositories

Snapshot có thể dùng incremental/shared segments; xóa một snapshot phải qua API repository hỗ trợ để reference counting/cleanup đúng. Không xóa object files trong snapshot repository bằng lifecycle rule ngẫu nhiên.

### 11.5. Managed search

Một service managed có thể có disk watermark alarms, autoscaling hoặc storage constraints riêng. Dùng supported controls; không giả định host filesystem có thể can thiệp.

## 12. DynamoDB/Cosmos DB và ranh giới trách nhiệm của managed service

### 12.1. Không có “thư mục log” để tự dọn

Với DynamoDB hay Cosmos DB managed, người sử dụng thường không có quyền vào host data directory. Chính sách storage được thể hiện qua TTL, backup, PITR, retention, throughput, account quotas và service APIs.

### 12.2. Theo dõi data growth và chi phí

Storage size, index/backup consumption, RU/RCU/WCU, logical partition limits, TTL cleanup behavior và billings vẫn quan trọng dù không thao tác `df`.

### 12.3. PITR cần được cấu hình chủ đích

Không suy “managed” nghĩa luôn có PITR được bật, retention vô hạn hoặc restore không tốn thời gian. Xác nhận account/table/container configuration và thực hành restore.

### 12.4. TTL không thay backup retention

TTL đánh dấu/xử lý data expiration theo API; backup/PITR history có thời hạn và semantics riêng. Đừng hứa xóa dữ liệu hoàn toàn chỉ bằng TTL.

### 12.5. Giới hạn dịch vụ không chỉ là GB

Một ứng dụng có thể gặp throughput/throttling, per-item/partition quotas, backup storage cost hoặc API limits trước khi chạm storage toàn account.

## 13. Snapshot: định nghĩa và tính nhất quán

**Snapshot** là một ảnh dữ liệu tại một mốc logic/vật lý theo cơ chế của engine hoặc storage layer. Có nhiều loại:

| Loại | Cơ chế tham khảo | Điều cần kiểm |
|---|---|---|
| Engine logical snapshot | DB chọn/checkpoint dữ liệu | Transaction/replication consistency |
| Filesystem/block snapshot | Copy-on-write hoặc volume snapshots | Crash consistency, nhiều volumes |
| Incremental snapshot | Chỉ lưu thay đổi so với base | Dependency chain |
| Hard-link snapshot | Trỏ tới data files hiện có | Reference counts và reclaim |
| RDB/image file | Serialize data tại thời điểm | Temp bytes, restore semantics |
| Object-storage backup | Upload data ngoài host | Upload verification, permissions |

### 13.1. Snapshot lúc file yên tĩnh khác lúc write liên tục

Application-consistent snapshot cần engine phối hợp để mọi components có checkpoint tương thích; snapshot lúc write liên tục có thể chỉ là crash-consistent và cần WAL replay.

### 13.2. Multi-node không tự là cluster-consistent

Chụp từng node lúc khác nhau không chứng minh có một trạng thái giao dịch tổng thể của cả cluster. Nhu cầu consistency phải xét product backup protocol, transaction scope và cluster topology.

### 13.3. Snapshot là một mốc, không phải PITR mặc định

Có snapshot lúc 00:00 không đồng nghĩa restore được lúc 13:47 nếu không có change/log history và công cụ replay tương ứng.

### 13.4. Snapshot cục bộ có thể mất cùng node

Một volume snapshot có thể tồn tại ngoài volume tùy provider, nhưng snapshot chỉ là hard links bên trong data volume không bảo vệ trước hỏng volume/host. Xác định failure domain rõ.

### 13.5. Restore mới chứng minh giá trị backup

Backup đã tạo không đảm bảo đọc được hoặc ứng dụng chạy được sau restore; cần checksum/integrity, version compatibility và bài diễn tập đầy đủ.

## 14. Hard link và copy-on-write khiến phép tính dung lượng khó

Một snapshot hard-link tới SSTable:

~~~text
data/live/SSTable-A
data/snapshots/2026-11-01/SSTable-A

Hai đường dẫn có thể trỏ cùng inode/bytes.
~~~

### 14.1. Khi snapshot mới tạo

File có thể chỉ được liên kết tham chiếu, nên gần như không tăng dung lượng data bytes, dù `ls -l` mỗi đường dẫn vẫn báo cùng file size.

### 14.2. Khi compaction thay SSTable

Live data chuyển sang file mới, snapshot giữ file cũ; bytes cũ chưa được reclaim. Lúc này snapshot retention có tác động storage lớn.

### 14.3. Không lấy tổng dung lượng paths làm physical usage

Đếm hard-linked files hai lần có thể làm con số logical snapshot size lớn hơn physical disk used. `df` và các counters của filesystem thường cho góc nhìn capacity thực; `du` và DB snapshot metadata phục vụ phân bổ nguyên nhân.

### 14.4. Xóa một snapshot có thể giải phóng ít hơn dự tính

Nếu nhiều snapshots cùng tham chiếu file, xóa một bản không giải phóng bytes cho đến khi mọi tham chiếu còn cần đều được loại.

### 14.5. CoW snapshot có khác biệt

Volume snapshots dạng CoW có thể giữ old blocks khi live data thay đổi. Độ lớn incremental có thể tăng theo tốc độ ghi và retention, không đơn giản bằng kích thước dữ liệu logic.

## 15. Thiết kế vòng đời snapshot: tạo, xác minh, chuyển, hết hạn

~~~mermaid
flowchart TD
    REQ["Backup policy / RPO"] --> CREATE["Create supported snapshot"]
    CREATE --> CHECK["Validate integrity + manifest"]
    CHECK --> COPY["Copy to independent backup destination"]
    COPY --> VERIFY["Verify completed upload / restore eligibility"]
    VERIFY --> CATALOG["Register in backup catalog"]
    CATALOG --> KEEP["Retain under policy + legal holds"]
    KEEP --> EXPIRE["Expire with dependencies checked"]
    EXPIRE --> CLEAN["Delete using supported API"]
    CLEAN --> MON["Reconcile actual reclaimed capacity"]
~~~

### 15.1. Một job backup “SUCCESS” cần định nghĩa

Thành công không chỉ là process exit 0; cần đủ files/segments/metadata, manifest, encryption, retention, restore dependencies và durable storage confirmation.

### 15.2. Local snapshot có thể chỉ là staging

Nếu snapshot tạo để upload lên object storage, chỉ dọn local khi upload đã verified, checksum/manifest hợp lệ và backup system xác nhận không còn cần local files.

### 15.3. Những bản sao bị legal hold

Retention expire job không được xóa snapshot/backup đang nằm trong điều kiện legal hold, incident investigation hoặc policy ngoại lệ.

### 15.4. Xóa snapshot bằng tool/API có hỗ trợ

Đảm bảo engine/backup catalog cập nhật trạng thái đúng. Không dùng filesystem script độc lập mà engine không biết.

### 15.5. Xóa xong vẫn phải đo lại

Kiểm physical disk available, inode count, snapshot catalog và backup restore coverage; không tin số bytes “ước tính giải phóng” trên UI.

## 16. Full backup, incremental backup và dependency chain

Giả sử:

~~~text
Sunday: full F1
Monday: incremental I2 (depends on F1)
Tuesday: incremental I3 (depends on F1 + I2)
Wednesday: incremental I4 (depends on prior chain)
~~~

### 16.1. Không xóa base nếu chain còn phụ thuộc

Xóa F1 có thể làm I2–I4 vô dụng nếu định dạng backup cần base. Retention phải được backup engine/catalog xử lý dependency-aware.

### 16.2. Synthetic full hoặc consolidation

Một số sản phẩm hỗ trợ tạo consolidated/synthetic full mới để cắt chain cũ. Điều này phải được thực hiện theo API được hỗ trợ và restore verified.

### 16.3. Chain dài ảnh hưởng RTO

Restore từ full + 100 incrementals có thể tốn nhiều thời gian, dù RPO tốt. Chọn lịch tạo full/base theo measured restore time.

### 16.4. Kiểm dependency theo tenant/region

Một backup có thể chứa data của nhiều tenants/regions với policy riêng. Không áp expire rule toàn bucket khi chưa kiểm data ownership và retention obligations.

### 16.5. Repository integrity

Backup repository có thể có manifest/ref counts, checksum và metadata; đừng xóa các object lẻ bằng lifecycle rules không tương thích với engine.

## 17. Restore test: điều kiện tiên quyết để tin retention

Một chương trình backup đáng tin cần định kỳ phục hồi tại môi trường cô lập.

### 17.1. Kiểm data integrity

So record counts chưa đủ; dùng checksums/manifests, sample domain invariants, index/query consistency và replay markers theo hệ.

### 17.2. Kiểm khả năng khởi động

Restore engine version/config, auth/keys, indexes, schema migrations, replica setup và application compatibility. Backup bytes tồn tại nhưng thiếu encryption key có thể không phục hồi được.

### 17.3. Đo RTO thực tế

Tính thời gian provision storage, fetch snapshot, restore, replay log, rebuild index, verify và chuyển traffic. Đừng lấy thời gian copy file làm toàn RTO.

### 17.4. Đo RPO

Chọn test timestamp, đối soát các writes đã ACK trước mốc; xác định lost/duplicate outcomes theo policy. PITR không chỉ là chọn timestamp trong UI.

### 17.5. Test theo các failure domains

Node loss, volume corruption, region outage, accidental deletion và logical corruption có yêu cầu khác nhau. Một local snapshot không bảo vệ khỏi tất cả.

## 18. PITR và retention log phụ thuộc nhau

**Point-in-time recovery** thường dựa trên một baseline backup/snapshot cùng lịch sử changes từ đó đến thời điểm muốn phục hồi.

~~~text
Snapshot S at 00:00
Change history 00:00 -> 14:00
Restore target 13:45

Needs S + a complete, applicable chain of changes
through 13:45.
~~~

### 18.1. Không xóa log cần cho PITR

Nếu retention policy yêu cầu restore 7 ngày trước, nhưng operator tự trim log/CDC sau 12 giờ, cửa sổ recovery có thể bị phá.

### 18.2. Replication lag cũng cần history

Replica bị ngắt lâu cần đủ oplog/stream changes để bắt kịp. Nếu history mất, phải initial sync/reseed; điều này có thể gây tải lớn vào node còn sống.

### 18.3. CDC consumer có retention window

Một consumer dừng quá lâu có thể không resume được. Nếu log nguồn không đủ, cần snapshot/bootstrap + change feed watermark; không tự tăng retention đến vô hạn mà không tính disk.

### 18.4. Cân bằng RPO và capacity

Giữ history dài hơn tăng khả năng recovery nhưng tốn storage. Có thể di chuyển recovery history tới tầng lưu trữ phù hợp nếu product hỗ trợ, không đơn giản xóa logs tại nguồn.

### 18.5. Ghi rõ “earliest restorable point”

Một dashboard backup nên nêu thời điểm cũ nhất có thể restore thực tế theo chain và trạng thái logs, không chỉ hiển thị số snapshots.

## 19. TTL, tombstone và compaction ảnh hưởng chính sách đĩa

Một NoSQL TTL 30 ngày không có nghĩa bytes được hoàn trả chính xác sau 30 ngày.

### 19.1. Logical expiry

Record có thể được coi là hết hạn theo query semantics và không còn hiển thị, trong khi storage engine vẫn cần metadata/tombstone cho consistency.

### 19.2. Physical reclamation

Compaction/garbage collection hoặc background cleanup có thể reclaim sau; thời điểm phụ thuộc replication/repair, storage engine và cấu hình.

### 19.3. Replica safety

Xóa tombstone/metadata quá sớm ở một số hệ có thể làm dữ liệu cũ từ replica chưa cập nhật xuất hiện lại. Không can thiệp bằng file deletion để “giải phóng ngay”.

### 19.4. Compaction amplification

Trong quá trình viết SSTables/segments mới, đĩa có thể chứa đồng thời old + new bytes. Cần headroom đủ để engine hoàn tất.

### 19.5. Retention policy phải xét write rate

Một bảng giữ dữ liệu 7 ngày nhưng ingest 50 GB/ngày có footprint khác bảng ingest 1 GB/ngày; cần đo write amplification và snapshot dependencies.

## 20. Dự báo đầy đĩa bằng tốc độ tăng trưởng

Gọi:

\[
C = \text{physical volume capacity},\quad
U(t) = \text{used bytes tại thời điểm }t.
\]

Dung lượng trống:

\[
F(t) = C-U(t).
\]

Nếu muốn giữ **dự phòng an toàn** \(H\) bytes và tốc độ tăng trưởng ròng trung bình \(g>0\) bytes/ngày, thời gian cho đến khi chạm ngưỡng an toàn:

\[
T_{\text{to headroom}} \approx \frac{F(t)-H}{g}.
\]

Đây là **ước lượng tuyến tính** trong đoạn quan sát, không bảo đảm tốc độ thực không tăng.

### 20.1. Ví dụ tính toán

Volume 2.000 GB, hiện dùng 1.600 GB, muốn giữ 200 GB dự phòng, tăng ròng 40 GB/ngày:

~~~text
Free now = 2,000 - 1,600 = 400 GB.
Free above reserve = 400 - 200 = 200 GB.
Time to reserve threshold = 200 / 40 = 5 days.
Time to physical full (naive) = 400 / 40 = 10 days.
~~~

Mốc quan trọng là **5 ngày đến vùng dự phòng**, không phải đợi 10 ngày đến đầy hoàn toàn.

### 20.2. Tăng trưởng ròng khác ingest rate

Nếu ingest 100 GB/ngày, xóa/compact reclaim 60 GB/ngày, net growth khoảng 40 GB/ngày. Nhưng tốc độ reclaim có thể dừng khi compaction nghẽn, nên phải đo biến động.

### 20.3. Nhu cầu peak/snapshot theo đợt

Giả sử mỗi cuối tuần cần thêm 150 GB để build snapshot/rewrite; dự báo dựa trên net 40 GB/ngày có thể bỏ qua peak. Reserve phải cộng cả transient space.

### 20.4. Phân biệt bytes và percent

20% free trên volume 100 GB là 20 GB; trên volume 10 TB là 2 TB. Ngưỡng percent và absolute bytes nên kết hợp với workload/compaction requirements.

### 20.5. Dự báo theo node thấp nhất

Node nhỏ nhất/đầy nhất có thể quyết định incident. Dự báo trung bình toàn cluster không thay dự báo từng volume, shard và availability zone.

## 21. Tính headroom có mục đích

Một công thức định hướng:

\[
H_{\text{required}}
\ge
H_{\text{compaction}}
 + H_{\text{backup staging}}
 + H_{\text{rebuild/rebalance}}
 + H_{\text{burst}}
 + H_{\text{OS/filesystem}}.
\]

Các thành phần có thể không độc lập hoặc cùng xảy ra; lựa chọn headroom phải dựa trên **đỉnh đồng thời có thể xảy ra**, không máy móc cộng tất cả max.

### 21.1. Compaction/merge

Giữ chỗ cho new SSTables/segments trước khi old files được reclaim. Kích thước cần thiết phụ thuộc compaction strategy và file sizes.

### 21.2. Backup staging

Nếu snapshot archive/nén tạm trên cùng volume, job có thể cần nhiều chỗ trước khi upload. Có thể dùng volume chuyên biệt nếu engine/backup workflow hỗ trợ.

### 21.3. Rebalancing và node loss

Khi mất một node, dữ liệu có thể được tái phân bố qua nodes còn lại. Những nodes này cần không gian để nhận replicas/shards mới.

### 21.4. Burst và retry

Flash sale, batch import hoặc retry storm có thể tăng write rate đột ngột. Headroom nên tính cả capacity degradation.

### 21.5. Không có ngưỡng phần trăm “chuẩn” cho mọi NoSQL

Một cụm 100 GB và một cụm 100 TB khác nhau; filesystem, database engine, growth rates và recovery procedures quyết định mức reserve. Ngưỡng như 70/80/90% chỉ là **điểm khởi đầu cần hiệu chỉnh**.

## 22. Phân tầng cảnh báo theo hành động

| Mức | Tín hiệu minh họa | Hành động |
|---|---|---|
| Information | Disk growth vượt baseline | Kiểm ingest/index/retention |
| Warning | Tốc độ tăng dự báo chạm headroom trong vài ngày | Lập kế hoạch capacity và cleanup |
| High | Một volume sắp chạm safety reserve, compaction/backup có nguy cơ thất bại | Escalate on-call, giảm tải/điều chỉnh capacity |
| Critical | Quá ít free bytes cho writes/recovery, errors/throttling xuất hiện | Incident runbook, bảo vệ durability |

### 22.1. Kết hợp percent, bytes và thời gian

Một cảnh báo tốt có thể dùng `freePercent`, `freeBytes`, `timeToReserve`, `compactionBacklog` và `writeErrorRate`.

### 22.2. Cảnh báo dự báo cần có cửa sổ

Nếu growth metric dao động mạnh theo compaction, dự báo tuyến tính 5 phút có thể sai. Dùng nhiều cửa sổ, seasonal patterns và tránh phát cảnh báo liên tục vì spikes bình thường.

### 22.3. Không chờ `df` = 100%

Đến 100%, nhiều công cụ không thể tạo temp files, metadata, snapshots, checkpoint hoặc log mới. Có thể đã quá muộn để cleanup an toàn.

### 22.4. Alert theo volume và shard

PVC node A đầy 95% trong khi các PVC khác 55% cần được phát hiện. Average usage không bảo vệ node nghẽn.

### 22.5. Alert cần owner và runbook

Một alert “disk high” không có link tới topology, volume, backup owner và hướng xử lý có thể dẫn đến thao tác xóa sai.

## 23. Metrics cốt lõi cho chính sách log/snapshot/disk

| Nhóm | Metric |
|---|---|
| Disk | Total/used/available bytes, percent free, inodes |
| Growth | GiB/day theo volume, 7d/30d trend, time-to-reserve |
| I/O | Read/write bytes/s, IOPS, latency, queue depth |
| Database data | Live size, index size, SSTables/segments, tombstones |
| Engine logs | WAL/commitlog/oplog/AOF/translog size, checkpoint health |
| Replication | Replica lag, retained history window, resync risk |
| CDC | Consumer lag, oldest unprocessed event, retention horizon |
| Snapshot | Count, age, estimated occupied bytes, upload status |
| Backup | Last successful, restore verified, chain dependency, encryption |
| Maintenance | Compaction/flush/rewrite backlog and errors |
| App logs | Bytes/day, archived count, exporter queue/backpressure |
| Capacity | PVC/resource quotas, per-node/skew, forecast |
| Correctness | Write failures, read-only mode, data recovery errors |

### 23.1. Không dùng `du` thay mọi metric

`du` tính phân bổ theo paths có thể bị hard-link accounting ảnh hưởng; `df` phản ánh filesystem blocks, DB metrics giải thích cấu trúc bên trong.

### 23.2. Log exporter queue có thể đầy đĩa

Nếu network tới log collector mất, agent spool có thể tăng nhanh. Nó thuộc log pipeline, không phải DB live data.

### 23.3. Snapshot success không đủ

Backup job báo success nhưng restore tests nhiều tháng chưa chạy là rủi ro. Theo dõi **age of last verified restore**.

### 23.4. Hướng thay đổi quan trọng hơn một số

80% used đang giảm sau compaction khác 80% used đang tăng 100 GB/giờ. Đo derivative và sự kiện maintenance.

## 24. Ví dụ Prometheus: cảnh báo free capacity

Trên host có node_exporter, metric names/labels có thể như:

~~~promql
node_filesystem_avail_bytes{mountpoint="/var/lib/db"}
  / node_filesystem_size_bytes{mountpoint="/var/lib/db"}
~~~

Tỷ số là **free capacity fraction**; nếu cần percent, nhân 100.

### 24.1. Dự báo với `predict_linear`

Một biểu thức minh họa:

~~~promql
predict_linear(
  node_filesystem_avail_bytes{mountpoint="/var/lib/db"}[6h],
  24 * 3600
) < 0
~~~

Ý tưởng là dự đoán free bytes âm trong 24 giờ, không phải lời hứa hệ thống sẽ đầy đúng giờ ấy. Chỉ dùng khi metric có chuỗi đo đủ dài và không bị snapshot/compaction/batch lifecycle làm méo; nên so với ngưỡng reserve thực tế.

### 24.2. `avail` khác `free`

Trên một số filesystems, blocks dành riêng cho privileged processes khiến `avail` khác tổng free. Chọn metric gần với không gian process database thực sự có thể dùng.

### 24.3. Volume labels cần đúng

Kubernetes/PVC có thể cần kubelet volume stats hoặc storage-provider metrics thay cho node exporter mountpoint. Kiểm nơi metric được scrape và filesystem type.

### 24.4. Tránh đếm pseudo filesystems

tmpfs, overlay, container ephemeral filesystem và data PV có semantics khác nhau. Dashboards nên có allowlist mounts/volumes thật sự cần alert.

### 24.5. Bổ sung điều kiện an toàn

PromQL trên chỉ là ví dụ đọc/dự báo; một alert production còn cần duration (`for`), severity, labels, owner, maintenance suppression và kiểm query version.

## 25. Lệnh kiểm tra filesystem chỉ đọc

Trong môi trường Linux được phép và phù hợp:

~~~bash
df -h /var/lib/db
df -i /var/lib/db
du -sh /var/lib/db
du -sh /var/log/my-service
ls -lh /var/log/my-service
~~~

Đây là **lệnh quan sát**, không xóa/sửa gì. Đường dẫn ví dụ phải thay bằng mount thực; `du` đệ quy trên data directory rất lớn có thể tạo I/O overhead, nên ưu tiên telemetry/snapshot metadata hoặc chạy lúc phù hợp.

### 25.1. `df`

Cho biết capacity/free ở filesystem. Không giải thích được files nào tăng; phải xem đúng mountpoint.

### 25.2. `df -i`

Đĩa có thể còn GB nhưng hết **inodes** do quá nhiều file nhỏ, khiến tạo file mới thất bại. Một số storage implementations quản lý metadata khác nhau.

### 25.3. `du`

Giúp xem kích thước theo path nhưng có thể tốn tài nguyên; hard links, sparse files, snapshots và bind mounts ảnh hưởng cách hiểu.

### 25.4. Files đã xóa nhưng process còn mở

Trên Unix-like systems, file bị unlink nhưng vẫn được process giữ mở có thể vẫn chiếm blocks; vì vậy `df` chưa giảm dù không thấy file bằng `ls`. Cần xác minh qua công cụ quan sát file descriptors rồi thực hiện lifecycle/restart được phê duyệt, **không kill tùy tiện database**.

### 25.5. Lệnh phá hủy không thuộc bước chẩn đoán

Không `rm -rf` vào data directory, không truncate journal/AOF/oplog, không xóa snapshot repository object trực tiếp chỉ để thử giải phóng.

## 26. Kubernetes và container: hai loại disk pressure

### 26.1. PVC/PV

Database thường lưu dữ liệu bền trên PersistentVolumeClaim, có resize capability tùy StorageClass/backend. Xem `capacity`, `used`, `available`, PVC events và filesystem resize support.

### 26.2. Ephemeral storage

Container stdout/stderr logs, writable layers, temp files và emptyDir có thể dùng node ephemeral storage. Pod bị evict do ephemeral disk pressure **khác** PVC data đầy.

### 26.3. Log rotation của container runtime

Các container runtimes/kubelet có log rotation configs; application file logging có thể bỏ qua cơ chế ấy và lấp writable layer. Chọn logging architecture nhất quán.

### 26.4. PVC resize không phải luôn tức thời

Storage provider có thể tăng block capacity nhưng filesystem cần expand; có backend chỉ hỗ trợ offline resize hoặc có quota khác. Lập kế hoạch theo StorageClass/CSI driver version.

### 26.5. StatefulSet replica balance

Mỗi pod có PVC riêng. Một PVC đầy khi ba PVC khác còn trống không được giải quyết bằng “cluster has 40% free” nếu replicas không thể chuyển dữ liệu tức thời.

## 27. Lập chính sách cleanup: điều kiện trước và sau

Một cleanup job cần:

~~~text
DISCOVER CANDIDATES (read-only)
    -> CHECK owner/retention/legal hold
    -> CHECK backup/replica/CDC dependencies
    -> CHECK snapshot chain and verified restore
    -> APPROVE change in required scope
    -> DELETE through supported API
    -> VERIFY catalog, recoverability, actual free bytes
    -> AUDIT outcome
~~~

### 27.1. Không chọn ứng viên bằng mtime duy nhất

Một backup base cũ có thể cần cho incremental mới. Một log file cũ có thể chứa recovery history cần bởi lagging replica. Age không đủ chứng minh safe-to-delete.

### 27.2. Grace period

Thời gian trễ giữa “đủ điều kiện hết hạn” và “xóa thật” giúp kiểm replication, upload, legal hold và manual rollback trong giới hạn policy.

### 27.3. Dry run

Cleanup tool nên in candidates, reason, estimated bytes, backup chain, tenant/resource và policy decision trước khi xóa. Không để dry run tự thực hiện `delete`.

### 27.4. Idempotency

Chạy lại job không được xóa nhầm bản khác hoặc coi missing file là cho phép xóa chain. Dùng snapshot IDs và catalog state thay vì glob rộng.

### 27.5. Audit trail

Ghi ai/automation nào quyết định, policy version, resource ID, phê duyệt, deletion time, result và restore evidence. Không log credentials hoặc nhạy cảm.

## 28. Pseudocode cleanup snapshot an toàn

~~~text
function planSnapshotCleanup(catalog, policy, now):
    candidates = []
    for snapshot in catalog.listAll():
        if snapshot.age(now) < policy.minimumRetention:
            continue
        if snapshot.hasLegalHold:
            continue
        if not snapshot.backupUploadVerified:
            continue
        if not snapshot.restoreChainValidated:
            continue
        if catalog.isRequiredBaseForRetainedIncremental(snapshot):
            continue
        if catalog.isLastKnownGoodRestorePoint(snapshot):
            continue
        candidates.add({
            id: snapshot.id,
            reason: "expired-and-safe-to-review",
            estimatedReclaimBytes: snapshot.estimateExclusiveBytes()
        })
    return candidates   // NO DELETION

function executeApprovedCleanup(plan, approval, snapshotApi):
    assert approval.matches(plan)
    for item in plan:
        assert snapshotApi.revalidateEligibility(item.id)
        snapshotApi.deleteSnapshotUsingSupportedOperation(item.id)
    verifyBackupCatalogAndFilesystem()
~~~

### 28.1. “Plan” không được tạo side effect

Hàm đầu chỉ báo cáo candidates, không xóa dữ liệu. Quyết định cuối có thể phải qua backup owner/DB owner/security owner theo policy.

### 28.2. Revalidate ngay trước xóa

Một incremental backup mới có thể bắt đầu giữa lúc plan và execute. Eligibility check phải chạy lại dưới điều kiện phù hợp.

### 28.3. Exclusive bytes là ước lượng

Hard links, CoW và shared segments khiến xóa một snapshot có thể giải phóng ít bytes hơn dự kiến. Đừng dùng estimated reclaim để khẳng định incident đã được xử lý.

### 28.4. API của vendor giữ state

`deleteSnapshotUsingSupportedOperation` là abstract method. Implementation phải dùng API/tool chính thức của backend đã được review, không gọi shell xóa path ngẫu nhiên.

## 29. Khi disk đang 90–95%: xử lý bình tĩnh nhưng nhanh

### 29.1. Xác định mount/volume nghẽn

Là DB data, WAL, log exporter, backup staging hay node ephemeral storage? Kiểm `df`/PV stats và DB metrics.

### 29.2. Ngăn tình trạng xấu thêm

Khi được phép, tạm dừng noncritical bulk loads, giảm debug logging, giới hạn ingest hoặc throttle noisy tenants. **Không dừng durability/replication components tùy tiện** vì có thể làm log retention tăng hơn.

### 29.3. Ưu tiên phương án ít rủi ro

Tăng capacity/attach volume nếu supported và khả thi, chuyển ứng dụng log archive đã được upload verified, dọn staging files theo owner-approved procedure, thay vì xóa engine files.

### 29.4. Bảo vệ write correctness

Nếu write đã ACK, phải giữ recovery guarantees. Không đổi write concern, xóa WAL hay bỏ fsync chỉ để có throughput trong sự cố mà không có quyết định kiến trúc/phê duyệt.

### 29.5. Tránh tạo thêm temp data

Chạy full snapshot/reindex/large compaction trong lúc gần đầy có thể đẩy hệ sang 100%. Chọn hoạt động recovery theo engine runbook.

## 30. Khi disk đã đầy: runbook hướng ưu tiên

**Đây là sơ đồ ra quyết định**, không phải lệnh tự động cho mọi sản phẩm:

~~~mermaid
flowchart TD
    ALERT["Disk full / write errors"] --> SCOPE["Identify exact volume and owner"]
    SCOPE --> SAFE["Protect data integrity and limit new workload"]
    SAFE --> CAP["Can safely expand capacity?"]
    CAP -->|"Yes"| EXPAND["Approved volume expansion / add capacity"]
    CAP -->|"No"| ALT["Find independently owned reclaimable files"]
    ALT --> CHECK["Verified backup + dependency + legal checks"]
    CHECK --> API["Supported cleanup API only"]
    EXPAND --> VERIFY["Verify DB recovery / writes / replication"]
    API --> VERIFY
    VERIFY --> ROOT["Fix growth/root cause and alert policy"]
~~~

### 30.1. Xác nhận tính toàn vẹn trước thao tác

Nếu DB đã báo corruption/recovery errors, dừng can thiệp phá hủy và làm theo vendor incident procedure. Đừng xóa file ngẫu nhiên để ép database khởi động.

### 30.2. Có thể phải giảm tải/đóng nhận ghi

Tùy product, bounded admission, read-only fail-safe hoặc temporarily reject new writes có thể bảo vệ dữ liệu. Điều này phải được phối hợp với business và operational protocol.

### 30.3. Backup trước cleanup nếu còn khả thi?

Không tự chạy backup lớn lên cùng volume đang hết chỗ; nó có thể thất bại. Cần biết backup gần nhất verified và cách tạo backup ngoài volume nếu được hỗ trợ.

### 30.4. Sau reclaim cần re-evaluate

Write path, quorum, replication, compaction, CDC, snapshots và free bytes phải được kiểm trước khi tuyên bố hồi phục.

### 30.5. Tránh khôi phục bằng “delete temp directory”

Temp files đang được storage engine dùng có thể chứa state phục hồi, index merge hoặc transaction checkpoint. Chỉ dọn theo vendor/engine lifecycle.

## 31. Dung lượng tăng vì replica hoặc CDC quá chậm

Một secondary mất kết nối bốn ngày; primary giữ replication/change history lâu hơn bình thường theo cơ chế sản phẩm.

### 31.1. Nhận diện

Replication lag, oplog/history window, oldest retained checkpoint, consumer offset/lease, source log growth và số bytes/day.

### 31.2. Không xóa history để giải phóng trước khi hiểu

Xóa history có thể khiến secondary/consumer không bắt kịp và phải rebuild, tạo thêm tải I/O và network, có thể đẩy cụm đang yếu vào sự cố sâu hơn.

### 31.3. Các phương án

Khôi phục consumer/replica, tăng capacity, điều chỉnh retention phù hợp, rebootstrap có kế hoạch nếu window đã mất, hoặc chuyển backlog sang durable stream theo architecture được hỗ trợ.

### 31.4. Phân biệt queue retention và source log retention

CDC connector có thể đã checkpoint ở broker nhưng downstream consumer chưa xử lý. Dùng đúng checkpoint semantics của từng tầng, không coi một offset bất kỳ là safe-to-delete toàn bộ source history.

### 31.5. Theo dõi time-to-retention-expiry

Không chỉ monitor bytes; monitor khoảng cách giữa lagging consumer và oldest available event để alert trước khi mất khả năng resume.

## 32. Dung lượng tăng vì log level và pipeline quan sát

Một service được bật DEBUG tạm để điều tra, mỗi request ghi 10 KB JSON; với 10.000 requests/s:

\[
10{,}000\times 10\ \text{KB/s}
=100{,}000\ \text{KB/s}\approx100\ \text{MB/s}.
\]

Đó là khoảng 8,6 TB/ngày nếu giữ tốc độ suốt ngày theo đơn vị thập phân, chưa tính compression và traffic thực tế.

### 32.1. Tránh debug vô hạn

Debug sampling có TTL/time-bound flag, tự tắt khi hết window, có owner. Không log toàn payload user.

### 32.2. Rotate và size cap

File app log có rolling policy; log collector có quota/bounded buffering và remote retention. Local cache hết chỗ phải tạo alert, không lấp database PVC.

### 32.3. Central logging không tự nghĩa zero disk

Agent có thể spool trên node/volume khi network mất. Xem exporter backlog và local buffer capacity.

### 32.4. Security/privacy

Log payload có secrets có thể tạo sự cố bảo mật lớn hơn disk đầy. Redact, sample, IAM access và retention theo loại dữ liệu.

## 33. Dung lượng tăng vì snapshot retention sai

Một cluster tạo snapshot hàng ngày; backup job upload thành công nhưng local snapshot cleanup bị tắt.

~~~text
Day 1: first snapshot.
Day 2–20: compactions rewrite live files.
Old SSTables/blocks remain referenced by old snapshots.
Free disk shrinks even though live row count is stable.
~~~

### 33.1. Chẩn đoán bằng catalog

Đo snapshot count/age, upload verified, base/incremental dependencies, unique bytes estimate và physical disk delta.

### 33.2. Không xóa “all snapshots”

Một số có thể là bản gần nhất để rollback/restore. Xóa qua supported snapshot APIs theo policy và verified backup chain.

### 33.3. Dọn một bản có thể giải phóng ít bytes

Shared hard links/segments làm estimate khó. Cần đo `df` sau cleanup và tiếp tục dự báo.

### 33.4. Ngăn tái diễn

Cleanup job đi kèm snapshot create success, upload confirmation, retention checks và alert “oldest local snapshot age”.

## 34. Dung lượng tăng vì compaction bị nghẽn

Một LSM database ghi nhiều, compaction không kịp vì IOPS thiếu, node quá tải hoặc disk free quá thấp:

~~~text
Write input > sustainable compaction throughput
    -> L0/SSTable backlog grows
    -> read/write amplification increases
    -> more disk usage and latency
    -> less space available for compaction
~~~

### 34.1. Triệu chứng

Compaction pending tasks/bytes, SSTable count, disk write bandwidth, read amplification và latency tăng theo giờ dù ứng dụng không thêm dữ liệu tương ứng.

### 34.2. Không xóa SSTables thủ công

SSTables/segments có checksums/index/manifest và replica semantics. Xóa chúng có thể phá DB hoặc mất records. Compaction tuning phải theo engine.

### 34.3. Tăng storage có thể cần thiết

Nếu không đủ chỗ tạm cho compaction, capacity expansion an toàn có thể giúp engine tự thu hồi không gian; sau đó mới đo root write amplification.

### 34.4. Xem TTL/schema

Một partition cực lớn, nhiều tombstones hoặc update pattern làm tạo nhiều versions có thể đẩy compaction debt. Data model/retention cần được đánh giá.

## 35. Dung lượng tăng vì rebalancing và repair

Node mới thêm vào hoặc node cũ quay lại có thể làm hệ copy/stream lại SSTables/shards/replicas, tạo tăng disk/network tạm thời.

### 35.1. Đánh giá peak capacity

Khi tái phân bố dữ liệu, nguồn có thể còn giữ copy cũ cho tới khi đích verified, nên tạm thời tăng physical footprint.

### 35.2. Repair và anti-entropy

Một số NoSQL cần repair để bảo đảm replica consistency và deletion safety. Bỏ repair vì “tốn đĩa” có thể làm rủi ro dữ liệu cao hơn.

### 35.3. Mất node khi cluster gần đầy

Các nodes còn lại có thể không đủ headroom nhận replica mới. N−1 capacity planning phải tính trước.

### 35.4. Snapshot trước migration

Nếu cần snapshot an toàn để cutover, nó cũng dùng storage. Không bắt đầu migration khi chưa đủ staging/backup capacity.

## 36. Những trường hợp `df`, `du`, DB metrics không khớp nhau

| Triệu chứng | Nguyên nhân có thể |
|---|---|
 `df` used cao, `du` nhìn thấy thấp | Deleted-but-open files, mounts, snapshots, reserved blocks |
 `du` tổng nhiều paths cao hơn `df` used | Hard links/shared blocks, overlapping scans |
 DB logical size nhỏ, filesystem used cao | Indexes, WAL, snapshots, compaction, backups |
 Snapshot UI báo 1 TB, xóa xong free tăng 50 GB | Shared segments/hard links |
 Free bytes còn nhiều, writes fail | Inode exhaustion, quota, read-only mount, permission |
 PVC resized nhưng filesystem free không đổi | Filesystem resize chưa hoàn tất hoặc sai mount |

### 36.1. Deleted-but-open files

Trên Linux, unlink file không giải phóng blocks cho tới khi file descriptor cuối đóng. Đừng liên tục xóa thêm files; điều tra process owner.

### 36.2. Sparse files

Logical file length có thể lớn hơn allocated blocks; backup/snapshot behavior cũng có thể phụ thuộc sparse allocation.

### 36.3. Filesystem reserved space

Một phần blocks có thể dành riêng, usable bytes của process database khác free bytes tổng.

### 36.4. Node vs container view

Process trong container có thể thấy mount namespace/overlay khác host; dashboard phải gắn metric đúng PVC/volume.

### 36.5. Quota là một trần độc lập

User/volume/account có thể bị quota khi filesystem vật lý còn trống. Check permission, quota và storage-class limits.

## 37. Phân biệt disk full với các lỗi khác

Một write fail có thể do:

- Filesystem `ENOSPC` (hết blocks).
- Không còn inodes.
- Volume quota hoặc account storage limit.
- Read-only filesystem do I/O corruption hoặc policy.
- Disk latency quá lớn khiến timeout.
- Insufficient space cho compaction/rewrite/backup stage.
- Node unreachable, leader/quorum failure.
- Schema/transaction/authorization error không liên quan disk.

### 37.1. Error taxonomy

Không gom tất cả thành `database unavailable`. Ghi error code từ SDK/server, node/volume, requestId, operation và time window.

### 37.2. Unknown write outcome

Write timeout hoặc connection reset trong sự cố không bảo đảm mutation chưa commit. Dùng stable commandId/idempotency và authoritative reconciliation khi retry.

### 37.3. Không đánh đổi durability để “sống sót”

Tắt journal/WAL/fsync hoặc giảm write concern có thể làm ACK nhanh hơn nhưng phá durability contract. Đây không phải cách cleanup disk an toàn.

### 37.4. Read-only mode có thể là tính năng bảo vệ

Một số engines tự chặn writes khi thiếu disk. Không bỏ guardrails rồi tiếp tục ingest nếu engine không thể đảm bảo recovery.

## 38. Kế hoạch capacity theo vòng đời dữ liệu

Một model đơn giản:

~~~text
Live data growth
+ index growth
+ replicated copies per node/placement
+ log/CDC retention
+ snapshots retained
+ compaction/rewrite peak
+ backups staging
+ failure recovery headroom
+ OS/container overhead
= required physical capacity per failure domain
~~~

### 38.1. Sizing theo node, không chỉ dataset tổng

Partition skew và replica placement khiến node nóng có thể đầy trước. Dùng largest node utilization và expected rebalance cost.

### 38.2. Sizing theo ingestion và retention

50 GB/ngày × 30 ngày = 1,5 TB raw ingest trước khi compression/index/versioning; không gọi đó là physical used exact.

### 38.3. Phân biệt steady-state và peak

Compaction, backups, migrations và node replacement có thể tăng peak storage vượt steady footprint nhiều lần theo engine.

### 38.4. Capacity planning là quy trình định kỳ

Mỗi tuần/tháng xem growth, free bytes, retention window, cost và restore readiness. Chờ incident mới tính là quá muộn.

## 39. Phân quyền và kiểm soát automation cleanup

### 39.1. Least privilege

Backup job có quyền create/upload, cleanup job có quyền delete giới hạn đúng repositories/resources; public API và application runtime không được có quyền xóa snapshots.

### 39.2. Separation of duties

Người đề xuất dọn và người phê duyệt xóa backup quan trọng có thể là hai vai trò khác nhau, tùy security policy.

### 39.3. Object lock / immutable backup

Backup chống ransomware cần cơ chế immutable retention hoặc object lock tương thích, nhưng phải thiết kế với yêu cầu erasure/data governance và cost.

### 39.4. Idempotent workflows

Automation có manifest, jobId, candidate IDs và audit; retry không xóa nhiều hơn dự kiến khi response mất.

### 39.5. Kịch bản compromise

Nếu application credentials bị lộ, attacker không nên có quyền xóa cả live data lẫn backups. Tách identities và failure domains.

## 40. Kế hoạch triển khai chính sách log và snapshot

### Giai đoạn 1 — Inventory

Ghi danh sách mỗi volume, owner, database product/version, log types, snapshot repository, backup location, retention requirement, RPO/RTO và dữ liệu nhạy cảm.

### Giai đoạn 2 — Baseline

Đo daily log bytes, snapshot exclusive growth, live data/index size, compaction debt, CDC lag, max node utilization và restore times.

### Giai đoạn 3 — Policy

Định nghĩa loại nào được rotate, archive, snapshot, expire; ai phê duyệt; safe cleanup API; headroom thresholds và exceptions.

### Giai đoạn 4 — Automate safely

Tạo log rolling/sampling, backup verification, candidate dry run, retention-aware deletion, audit logs và alert forecast.

### Giai đoạn 5 — Validate recovery

Diễn tập restore, replica catch-up, CDC resume và failure N−1 trên môi trường phù hợp. Xem xét thông số nếu RPO/RTO hoặc safety margin không đạt.

### Giai đoạn 6 — Operate and refine

Theo dõi drift từ schema/index/write rate; review policy định kỳ, cập nhật sau incident và thay đổi topology.

## 41. Mẫu chính sách vận hành dạng YAML

Đây là **mẫu tài liệu**, không phải file cấu hình được database nào áp dụng tự động:

~~~yaml
database:
  module: "Database No SQL"
  productVersion: "<product/version>"
  topology: "<replicas/shards/regions>"
  dataVolume: "<volume id>"
  owner: "<DB team>"

recovery:
  rpo: "<approved duration>"
  rto: "<approved duration>"
  latestVerifiedRestore: "<timestamp>"
  pointInTimeRecoveryWindow: "<verified window>"
  requiredReplicationHistory: "<lag plus margin>"

logs:
  application:
    rotateByTime: true
    rotateBySize: true
    maxLocalBytes: "<measured limit>"
    retention: "<approved days>"
    sensitiveFieldsRedacted: true
    shipToCentralStore: true
  audit:
    retention: "<security/legal policy>"
    immutableStorage: "<if required>"
  engineRecovery:
    managedByDatabase: true
    manualFileDeletionAllowed: false
  cdc:
    retentionWindow: "<source capability>"
    monitorOldestConsumerLag: true

snapshots:
  creation: "<database-supported mechanism>"
  schedule: "<backup schedule>"
  localStagingRetention: "<policy>"
  remoteBackupRetention: "<policy>"
  uploadManifestVerification: required
  restoreTestFrequency: "<approved interval>"
  legalHoldAware: true
  incrementalDependencyAware: true
  deletion: "vendor-supported API after approval"

capacity:
  forecastWindow: "<hours/days>"
  reserveBytes: "<compaction/rebuild/backup need>"
  reservePercent: "<product-specific>"
  warningTimeToReserve: "<duration>"
  criticalFreeBytes: "<threshold>"
  trackPerNodeAndVolume: true

operations:
  deleteDryRun: required
  deleteApproval: "<policy owner>"
  incidentRunbook: "<link>"
  changeAudit: required
  retentionReview: "<cadence>"
~~~

### 41.1. Placeholders không phải default

Các trường cần được điền theo khả năng product/backup tool, measured growth và nghĩa vụ vận hành; không lấy một ngưỡng cố định cho mọi cụm.

### 41.2. Retention window phải kiểm thực

Khi `pointInTimeRecoveryWindow` là 7 ngày, cần verify có đủ snapshot/log chain, không chỉ thấy config ghi 7d.

### 41.3. Cleanup policy và incident runbook liên quan nhưng khác

Automation retention thường chạy định kỳ trên candidates an toàn; full-disk incident cần human intervention và recovery priority, không tự bỏ qua approval để xóa dữ liệu chưa rõ.

## 42. Checklist trước khi dọn snapshot/log

1. **Đây là log ứng dụng, audit, WAL, oplog, CDC hay snapshot?**
2. **Engine/vendor nào sở hữu file/resource?**
3. **Volume nào đang gần đầy, thực sự còn bao nhiêu free bytes/inodes?**
4. **Snapshot backup upload đã verified chưa?**
5. **Có manifest/checksum và catalog trạng thái đầy đủ không?**
6. **Có thử restore từ backup chain này chưa?**
7. **Có PITR/log dependency cần giữ không?**
8. **Có replica/CDC consumer lag vượt mức bình thường không?**
9. **Incremental backup nào phụ thuộc snapshot/base?**
10. **Có legal hold, audit retention hoặc security incident giữ bản sao không?**
11. **Chính sách retention theo tenant/region có cho phép xóa không?**
12. **Có thể xem candidates bằng dry run trước không?**
13. **Có approval và audit trail không?**
14. **Tool/API xóa có được nhà cung cấp hỗ trợ không?**
15. **Delete có thể làm engine mất recovery/replication consistency không?**
16. **Estimated reclaimed bytes có xét hard links/shared blocks không?**
17. **Có capacity cần cho compaction/rebuild sau cleanup không?**
18. **Có rollback/restore plan phù hợp khi phát hiện sai không?**
19. **Sau xóa sẽ kiểm free bytes, recovery, replicas và write path như thế nào?**
20. **Lý do snapshot/log tích lũy đã được sửa để không tái diễn chưa?**

## 43. Tình huống thực tế: log ứng dụng lấp node ephemeral disk

Một service Java bật TRACE 30 phút để xem lỗi retry, rồi quên tắt. Pods ghi file local trên container writable layer; kubelet bắt đầu báo ephemeral storage pressure.

### 43.1. Dấu hiệu

Node disk usage tăng; DB PVC vẫn ổn. Log bytes/request tăng mạnh cùng release/feature flag. Pod có thể bị evict dù persistent database còn nhiều dung lượng.

### 43.2. Mitigation

Tắt TRACE đúng phạm vi, khôi phục log sampling/rolling, kiểm log shipper backlog; không đụng database data directory.

### 43.3. Fix dài hạn

Time-bound debug flag, local log size cap, centralized retention, request redaction, alert log growth và ephemeral storage budgets.

### 43.4. Bài học

“Disk full” có thể xảy ra ở **node ephemeral** chứ không phải database PVC. Xác định mount trước khi can thiệp.

## 44. Tình huống thực tế: Cassandra snapshot giữ SSTables cũ

Một cụm Cassandra chạy hàng tuần, tạo snapshot trước migration nhưng không dọn. Dữ liệu live gần như không tăng; physical disk usage vẫn tăng vì compaction rewrite nhiều SSTables mà snapshots còn giữ hard links.

### 44.1. Dấu hiệu

Count/age snapshots tăng; live size ổn, old SSTables retained; disk free giảm. `du` có thể gây hiểu lầm về shared hard links.

### 44.2. Xác minh

Liệt kê snapshots theo công cụ Cassandra/ScyllaDB hỗ trợ, đối chiếu backup manifests và verified remote copies; xem incremental chain/legal hold.

### 44.3. Dọn an toàn

Chỉ xóa snapshots đủ điều kiện qua supported tool, quan sát physical reclaimed bytes và compaction health.

### 44.4. Ngăn tái diễn

Snapshot post-upload cleanup có approval/dry run, alert oldest local snapshot age và restore drill định kỳ.

## 45. Tình huống thực tế: oplog window rút ngắn khi write spike

MongoDB replica set có một secondary bị mất mạng trong lúc primary nhận write traffic tăng gấp nhiều lần.

### 45.1. Dấu hiệu

Replication lag tăng và amount of history cần để catch up có thể vượt oplog window theo cơ chế giữ history. Change-stream consumers cũng có thể bị ảnh hưởng nếu vượt available history.

### 45.2. Hành động sai

Xóa journal/oplog files thủ công hoặc giảm history không có kế hoạch để “lấy lại disk”.

### 45.3. Cách xử lý

Kiểm nguồn lag, available history và write capacity; khôi phục replica nếu còn trong window, hoặc chuẩn bị initial sync/rebootstrap theo supported runbook khi history thiếu.

### 45.4. Capacity

Lập retention/headroom với peak write rate và recovery time, không chỉ dựa trên average của tháng trước.

### 45.5. Bài học

Log có thể là **phần bắt buộc của tính sẵn sàng và khả năng phục hồi**, không phải cache có thể xóa.

## 46. Tình huống thực tế: Redis AOF rewrite thất bại

Redis được dùng để lưu trạng thái phải phục hồi; AOF tăng theo write load, rewrite dự kiến giảm kích thước nhưng đĩa không còn chỗ cho temporary output.

### 46.1. Dấu hiệu

AOF/rewrite status báo lỗi, disk free thấp, persistence error metrics tăng; writes có thể bị ảnh hưởng theo config.

### 46.2. Không xóa AOF đang dùng

Xóa AOF làm hỏng recovery chain; thay vào đó đánh giá được phép tăng dung lượng, chuyển staging hoặc khắc phục persistence qua supported procedure.

### 46.3. Cần tính peak

Dung lượng cần cho rewrite có thể vượt active AOF size tạm thời; reserve không chỉ bằng dự báo live key memory.

### 46.4. Restore test

Sau sự cố, kiểm AOF/RDB recovery với bản sao trong môi trường cô lập, xác minh state và mất dữ liệu cho phép.

## 47. Tình huống thực tế: CDC consumer dừng lâu hơn retention

Ứng dụng dùng change feed để dựng search projection. Consumer dừng nhiều ngày, source giữ change history có hạn.

### 47.1. Dấu hiệu

CDC lag và oldest unprocessed age tăng, resume token/offset có nguy cơ hết hiệu lực; source history có thể gây disk/capacity pressure ở hệ tự vận hành.

### 47.2. Sai lầm

Trim history để giảm disk khi consumer còn cần nó rồi tiếp tục từ offset mới, làm mất changes.

### 47.3. Xử lý

Phục hồi consumer/capacity, xác định earliest available position; nếu thiếu history, dùng supported snapshot + CDC bootstrap with consistent watermark và idempotent apply.

### 47.4. Ngăn tái diễn

Monitor consumer lag so với retention horizon, replay cost và restart runbook; có alerts trước khi quá cửa sổ.

## 48. Tình huống thực tế: Elasticsearch disk watermark

Search cluster ingest nhiều documents và cập nhật mạnh; segment merges/snapshot operations làm disk free giảm, cluster có thể áp disk watermarks và block writes tùy version.

### 48.1. Triệu chứng

Shards khó relocate, writes bị hạn chế, unassigned shards hoặc merge backlog; disk phân bố không đều.

### 48.2. Mitigation có kiểm soát

Điều chỉnh ingest, expand volume/nodes theo supported method, đánh giá index lifecycle/retention và snapshot repository. Không xóa segment/translog files.

### 48.3. Index deletion là business data deletion

Nếu một index đã hết retention và có backup/approval phù hợp, có thể dùng supported lifecycle/API. Không coi `DELETE index` là tương đương dọn log tạm.

### 48.4. Dài hạn

Index lifecycle policy, shard sizing, storage watermark headroom, snapshot repository validation và alert predict-to-full.

## 49. Những sai lầm thường gặp

### “Mọi file tên log đều có thể rotate”

Sai. WAL/commitlog/oplog/AOF và audit logs có retention/ownership riêng.

### “Snapshot đã có, backup chắc chắn an toàn”

Sai. Snapshot cục bộ có thể mất cùng volume, thiếu manifest, thiếu encryption key hoặc chưa từng được restore.

### “Snapshot hằng ngày nghĩa PITR đến mọi phút”

Sai nếu không có history chain và replay mechanism được hỗ trợ.

### “File cũ hơn 7 ngày thì xóa”

Sai nếu đó là backup base cho incremental, legal-hold object, replication history hoặc engine-managed file.

### “Snapshot chiếm 1 TB thì xóa sẽ trống 1 TB”

Sai với shared hard links/segments/CoW và những tham chiếu còn lại.

### “Đã TTL dữ liệu thì disk sẽ giảm ngay”

Sai vì tombstones/compaction/backup refs có thể giữ physical bytes.

### “CPU thấp nên disk full không nguy hiểm”

Sai. Engine có thể không ghi được log/checkpoint hoặc compaction ngay cả khi CPU rảnh.

### “Chỉ cần alert ở 95%”

Thường quá muộn cho staging/compaction/rebalance. Headroom phải dự báo theo tốc độ tăng.

### “Cluster còn 30% free là mọi node an toàn”

Sai khi một shard/PVC đầy gần 100%.

### “Dọn nhanh bằng rm -rf snapshots”

Không an toàn nếu chưa kiểm tool/backup chain/reference ownership.

### “Dữ liệu logical ổn thì disk không tăng”

Index growth, write amplification, snapshots, WAL, CDC và deleted-but-open files có thể làm used bytes tăng.

### “Backup upload thành công nghĩa restore chắc chắn chạy”

Chưa chắc: integrity, version, keys, manifests và restore rehearsal mới xác minh.

### “Managed service không cần capacity planning”

Sai; quota, storage cost, retention, PITR và per-partition limits vẫn cần quản lý.

### “Xóa bớt logs sẽ chữa mọi write error”

Sai; lỗi có thể do quota, inode exhaustion, read-only mount hoặc data corruption.

### “Tăng disk là sửa tận gốc”

Không nếu retention job lỗi, debug logging không giới hạn hoặc schema tạo dữ liệu tăng vô hạn.

### “Giảm write concern để qua incident”

Đó là thay đổi durability contract, không phải cleanup an toàn.

### “Một lệnh du đủ giải thích disk”

Không; cần `df`, hard-link/snapshot semantics, engine stats và volume mapping.

### “Xóa file mà df chưa giảm thì cứ xóa tiếp”

Có thể là deleted-but-open file hoặc shared blocks; cần xác định nguyên nhân trước.

## 50. Bài tập thực hành

### Bài 1 — Phân loại file

Phân biệt logback archive, MongoDB oplog, Cassandra commitlog, Redis AOF, audit log và snapshot; nêu owner và rủi ro nếu dọn bằng script filesystem.

### Bài 2 — Thiết kế retention

Ứng dụng yêu cầu RPO 15 phút, RTO 2 giờ, audit log 1 năm. Thiết kế policy riêng cho app logs, engine logs, snapshots, backups và PITR.

### Bài 3 — Phân biệt snapshot và backup

Một Cassandra snapshot hard-link còn trên cùng PVC. Điều gì xảy ra nếu PVC hỏng? Đề xuất offsite backup/restore verification.

### Bài 4 — Hard-link accounting

Ba snapshots cùng liên kết tới một SSTable 10 GB. Xóa một snapshot có chắc giải phóng 10 GB không? Giải thích reference semantics.

### Bài 5 — CoW snapshot

Một volume snapshot dùng copy-on-write, dữ liệu live thay đổi 100 GB sau snapshot. Vì sao physical snapshot cost có thể tăng dù logical snapshot size tương tự?

### Bài 6 — Đo `df` và `du`

`df` báo used 90 GB, `du` thấy 70 GB. Liệt kê ít nhất năm nguyên nhân có thể và cách kiểm an toàn.

### Bài 7 — Inode

Filesystem còn 100 GB nhưng không thể tạo file mới. `df -i` chỉ ra hết inodes. Nêu vì sao thêm GB chưa chắc là giải pháp đúng.

### Bài 8 — Dự báo time-to-headroom

Volume 2 TB, đang dùng 1,6 TB, cần reserve 200 GB, net growth 40 GB/ngày. Tính thời gian tới ngưỡng reserve và tới full trong mô hình tuyến tính.

### Bài 9 — Snapshot peak

Một node còn 300 GB, mỗi tuần cần 250 GB cho compaction và 180 GB backup staging có thể trùng. Nêu những thông tin cần để tính reserve trước job.

### Bài 10 — Disk alerts

Thiết kế warning/high/critical dựa trên percent free, absolute bytes, forecast time-to-reserve và write failures, có owner/runbook.

### Bài 11 — Logback

Viết cấu hình rolling application log theo size/time, nêu `maxHistory`, `totalSizeCap`, và phân biệt với audit log retention.

### Bài 12 — Log explosion

Service ghi 10 KB/request ở 10.000 requests/s. Ước lượng GB/ngày; thiết kế sampling, TTL debug flag và spool capacity.

### Bài 13 — Container ephemeral disk

Pod bị evicted do ephemeral storage pressure, nhưng DB PVC vẫn 60% free. Điều tra container logs/writable layer/emptyDir theo thứ tự nào?

### Bài 14 — PVC growth

Một database PVC sắp đầy nhưng cluster-wide free còn nhiều. Giải thích vì sao thêm capacity vào node khác không tự giải quyết.

### Bài 15 — MongoDB oplog

Secondary lag vượt available replication history. Vì sao không thể tiếp tục từ oplog position cũ? Thiết kế resync/rebootstrap kế hoạch.

### Bài 16 — Cassandra snapshot

Snapshot job hoàn thành upload nhưng local snapshot không dọn. Thiết kế dry-run cleanup theo verified manifest và supported snapshot API.

### Bài 17 — Redis persistence

Redis AOF rewrite cần temporary space, volume gần đầy. Đề xuất containment và capacity/recovery plan mà không xóa AOF.

### Bài 18 — Elasticsearch watermark

Search cluster báo write block khi một node gần đầy. Tại sao không xóa trực tiếp segment/translog? Thiết kế recovery và lifecycle management.

### Bài 19 — Incremental chain

Full backup F1 có ba incrementals còn giữ. Có thể xóa F1 vì quá 7 ngày không? Đề xuất dependency-aware retention.

### Bài 20 — Restore verification

Một backup có manifest và checksum nhưng chưa restore test. Liệt kê những điểm có thể thất bại trong recovery, kể cả encryption keys và application schema.

### Bài 21 — PITR

Snapshot lúc 00:00, log history chỉ giữ tới 12:00, cần restore 13:30. Giải thích điều kiện cần thêm và những gì không thể khẳng định.

### Bài 22 — CDC consumer

Connector dừng 5 ngày, change history chỉ còn 3 ngày. Thiết kế alert và recovery dựa trên consistent snapshot + CDC bootstrap.

### Bài 23 — Tombstone

Table có TTL 7 ngày nhưng used disk không giảm theo expected. Đưa ra các chỉ số compaction/tombstone/snapshot cần kiểm.

### Bài 24 — Compaction

Một LSM workload tạo 100 GB/ngày, compaction backlog tăng. Thiết kế soak test và hướng capacity/schema/TTL remediation.

### Bài 25 — Rebalancing

Node lỗi cần xây replica trên hai nodes còn lại vốn 85% used. Dự đoán rủi ro và đề xuất N−1 headroom policy.

### Bài 26 — Managed NoSQL

Với DynamoDB hoặc Cosmos DB, làm sao quản lý backup retention, PITR, TTL/storage cost khi không có quyền vào host filesystem?

### Bài 27 — Data erasure

Một tenant yêu cầu xóa dữ liệu. Phân biệt primary deletion, replica propagation, snapshot retention, backup legal hold và erasure policy.

### Bài 28 — Read-only diagnostic script

Lập checklist dùng `df`, `df -i`, volume stats, DB metrics và backup catalog. Không dùng lệnh sửa/xóa. Báo cáo dữ liệu nào còn chưa biết.

### Bài 29 — Deleted-open file

Ứng dụng đã xóa log 20 GB nhưng `df` không giảm. Giải thích file descriptor semantics và quy trình điều tra an toàn.

### Bài 30 — Cleanup approval

Viết pseudocode planner liệt kê snapshot hết retention, kiểm upload, legal hold, incremental base và recent restore test. Giải thích vì sao planner không trực tiếp xóa.

### Bài 31 — Metrics và PromQL

Thiết kế biểu đồ free bytes/percent, growth rate, disk errors, snapshot counts, retention horizon. Giải thích giới hạn của `predict_linear` khi compaction làm biến động.

### Bài 32 — Incident disk 98%

Data PV còn 2%, backup job sắp chạy, CDC lag cao. Ưu tiên công việc nào, công việc nào cần hoãn và điều gì tuyệt đối không làm?

### Bài 33 — Chuỗi nguyên nhân

Vẽ causal chain: TTL nhiều → tombstones → compaction backlog → disk usage → write timeout → retry amplification. Tìm metric phản chứng ở mỗi bước.

### Bài 34 — Bảo mật backup

Application credentials vô tình có quyền xóa backups. Thiết kế IAM, object lock/immutable retention và separation of duties.

### Bài 35 — Runbook

Viết runbook cho ba sự cố khác nhau: application log đầy node ephemeral disk, Cassandra snapshot giữ disk, MongoDB oplog window không đủ. Mỗi runbook phải giữ recovery correctness.

### Bài 36 — Review chính sách sai

Một policy ghi: “Mọi file trong `/var/lib/db` quá 7 ngày sẽ tự xóa; snapshot thành công nghĩa backup đã verified; alert ở 99% và tắt journal khi thiếu disk”. Hãy chỉ ra từng rủi ro và viết lại policy an toàn hơn.

### Bài 37 — Kế hoạch dung lượng

Cho cụm 6 nodes, 3 replicas, live data tăng 30 GB/ngày ở nhiều partitions, snapshot/compaction overlap và một hot shard. Lập kế hoạch capacity theo node với N−1 failure, growth forecast, backups và retention.

### Bài 38 — Tổng hợp kiến trúc

Thiết kế chính sách vận hành cho ứng dụng Java + Cassandra source + Redis cache + Kafka CDC + object-storage backup: owner của từng log, snapshot lifecycle, dashboard, alert, quyền cleanup, restore drill và độ an toàn khi từng thành phần đầy đĩa.

---

**Kết luận:** **Lưu log, dọn snapshot và phòng ngừa đầy đĩa** là một bài toán về **dữ liệu cần phục hồi**, không chỉ là tìm file lớn để xóa. Log ứng dụng có thể được rotate theo thời gian/kích thước, nhưng **WAL, commitlog, oplog, AOF, translog và CDC history là tài sản do engine quản lý** và có thể giữ những writes/changes chưa thể bỏ. Snapshot phải có vòng đời: tạo đúng cơ chế, upload/verify, bảo vệ backup chain, thử restore, áp retention/legal hold và chỉ xóa bằng supported API. Để tránh full disk, cần đo **physical volume và inode theo từng node**, hiểu hard links/CoW, compaction/TTL/tombstones và nguồn tăng trưởng, dự báo **time-to-headroom** chứ không đợi 100%, duy trì đủ chỗ cho backup, rebuild và failover. **Khi sự cố xảy ra, bảo vệ durability và khả năng khôi phục trước; mở rộng capacity hoặc giảm tải an toàn trước khi cân nhắc xóa thứ gì chưa xác minh được quyền và phụ thuộc của nó.**
