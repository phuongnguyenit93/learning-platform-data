# Diễn tập, đo thời gian dừng và chuẩn bị phương án quay lui PostgreSQL

Một kế hoạch nâng cấp PostgreSQL chỉ đáng tin cậy khi đã được diễn tập trên môi trường gần với production, đo được thời gian của từng bước và có phương án quay lui có thể thực hiện trong giới hạn thời gian đã cam kết.

**Downtime** là khoảng thời gian dịch vụ không thể phục vụ nghiệp vụ theo mức chấp nhận được. Khoảng này có thể bắt đầu khi ứng dụng ngừng nhận writes, khi database dừng, hoặc khi traffic được chuyển khỏi cluster cũ; và chỉ kết thúc khi database mới được xác minh, ứng dụng reconnect thành công và các giao dịch quan trọng hoạt động bình thường.

**Rollback** là kế hoạch đưa dịch vụ về một trạng thái được chấp nhận khi upgrade thất bại. Rollback không đơn giản là đổi connection string về cluster cũ. Nếu cluster mới đã nhận writes, cluster cũ có thể thiếu những thay đổi đó. Nếu dùng hard-link mode, old cluster thậm chí không còn là một bản dữ liệu độc lập sau khi new cluster khởi động.

Bài **“Diễn tập, đo thời gian dừng và chuẩn bị phương án quay lui”**, thuộc chương **Nâng cấp** của module **Database Engine Relational PostgreSQL**, trình bày cách xác định RTO/RPO, xây dựng rehearsal, đo từng giai đoạn, chọn transfer mode, chuẩn bị backup/restore, xác định GO/NO-GO gates, xử lý data divergence và viết runbook cho cả đường thành công lẫn đường thất bại.

> **Nguyên tắc:** không có rollback đáng tin cậy nếu chưa xác định được dữ liệu nào là authoritative, thời điểm nào old cluster mất khả năng quay lại và cách khôi phục ứng dụng trong từng trường hợp. Hãy diễn tập cả đường thành công lẫn đường thất bại.

---

## 1. Vì sao cần diễn tập trước khi nâng cấp?

Một lần chạy thành công trong môi trường development không chứng minh production upgrade sẽ hoàn tất trong maintenance window.

Production thường có database lớn hơn, nhiều tablespaces, workload đồng thời, connection pools, extensions, replication, backup, monitoring, scheduled jobs và external consumers. Storage throughput cũng có thể khác môi trường test.

Diễn tập giúp tìm ra bước bị bỏ sót, đo thời gian thực tế, xác định dependency và kiểm tra rollback trước khi có áp lực production.

## 2. Xác định mục tiêu RTO và RPO

Hai mục tiêu cần được thống nhất trước khi thiết kế kế hoạch.

- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để dịch vụ trở lại hoạt động sau sự cố.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, thường biểu diễn bằng thời gian hoặc vị trí dữ liệu.

| Mục tiêu | Giá trị minh họa | Ý nghĩa |
|---|---:|---|
| RTO | 60 phút | Dịch vụ phải hoạt động lại trong tối đa 60 phút |
| RPO | 0 phút | Không chấp nhận mất transaction đã xác nhận |
| Maintenance window | 90 phút | Khoảng thời gian được phép gián đoạn có kế hoạch |

RTO và maintenance window không nhất thiết giống nhau. Maintenance window có thể bao gồm buffer, kiểm tra và truyền thông. RTO còn có thể áp dụng cho sự cố ngoài kế hoạch.

RPO=0 chỉ có ý nghĩa khi backup/replication và quy trình failover thực sự bảo vệ commits theo yêu cầu. Một bản backup được tạo trước upgrade không chứa writes phát sinh sau đó.

## 3. Định nghĩa chính xác downtime

Không dùng một mốc chung chung như “database đã start” để kết luận downtime kết thúc.

Nên xác định các mốc:

1. **Write freeze:** ứng dụng bắt đầu ngừng gửi writes.
2. **Traffic drain:** requests và transactions đang chạy được hoàn tất hoặc xử lý.
3. **Old cluster stop:** PostgreSQL cũ đã shutdown sạch.
4. **Upgrade start:** bắt đầu actual upgrade.
5. **Upgrade complete:** pg_upgrade kết thúc thành công.
6. **New cluster ready:** cluster mới khởi động và qua health checks.
7. **Validation complete:** schema, extensions, roles và các kiểm tra dữ liệu đạt.
8. **Application ready:** ứng dụng kết nối, smoke tests và giao dịch đại diện thành công.
9. **Traffic restored:** mở traffic theo kế hoạch.

Doanh nghiệp cần thống nhất downtime được tính từ mốc nào tới mốc nào. Có thể có nhiều chỉ số: write unavailability, read unavailability và full application outage.

## 4. Phân biệt write downtime và full downtime

Một số hệ thống có thể tiếp tục phục vụ read-only trong một phần maintenance window, nhưng điều đó cần được thiết kế và kiểm thử.

Ví dụ:

- Write freeze bắt đầu lúc 01:00.
- Read-only service tiếp tục tới 01:10.
- Database dừng lúc 01:10.
- New database sẵn sàng lúc 01:45.
- Application validation hoàn tất lúc 02:00.
- Full traffic mở lại lúc 02:05.

Khi báo cáo, nêu rõ write downtime, full database/application outage và khoảng thời gian validation/reconnect. Không báo downtime chỉ bằng thời gian pg_upgrade chạy.

## 5. Xác định scope của rehearsal

Một rehearsal có giá trị phải mô phỏng các yếu tố ảnh hưởng trực tiếp tới thời gian và kết quả:

- PostgreSQL source và target major versions.
- Data size và relation distribution.
- Số lượng databases, schemas, tables và indexes.
- Tablespaces và filesystem mounts.
- Extensions và external dependencies.
- Cấu hình memory, WAL, replication và authentication.
- Storage class, throughput và IOPS.
- CPU, RAM và memory limits.
- Ứng dụng, connection pools và background workers.
- Backup/restore và monitoring tools.

Nếu không thể sao chép toàn bộ production data, tạo dataset có quy mô và đặc tính truy cập gần thực tế. Ghi rõ khác biệt để điều chỉnh dự đoán.

## 6. Production-like environment

Rehearsal nên chạy trên hạ tầng tương đương production về những yếu tố có tác động trực tiếp tới upgrade.

| Thành phần | Yêu cầu |
|---|---|
| PostgreSQL versions | Chính xác source/target |
| OS và architecture | Tương thích với production |
| Filesystem | Cùng loại và tính năng cần dùng |
| Storage | Throughput/latency gần production |
| Data size | Gần production hoặc có mô hình ngoại suy |
| Extensions | Cùng packages và versions |
| Configuration | Cùng settings liên quan |
| Application | Cùng driver và migration behavior |
| HA/backup | Cùng workflow hoặc mô phỏng được |

Một VM nhỏ hơn nhiều có thể dùng để kiểm tra command syntax, nhưng không đủ để dự đoán thời gian copy hàng terabytes.

## 7. Lập inventory trước rehearsal

Ghi lại thông tin old cluster:

~~~sql
SELECT version();

SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;

SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace;

SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

Cần ghi thêm roles và memberships, database owners/grants, replication slots/subscriptions, publications, foreign servers/wrappers, large objects, collations, shared_preload_libraries, SSL files, archive commands, scheduled jobs, ETL và application endpoints.

Inventory trở thành baseline để đối chiếu sau upgrade.

## 8. Chọn phương pháp upgrade trước khi đo

Nếu dùng pg_upgrade, chọn transfer mode trước rehearsal vì mỗi mode có thời gian, disk requirement và rollback semantics khác nhau.

| Mode | Cơ chế | Tác động |
|---|---|---|
| Copy | Tạo file dữ liệu độc lập | Đo full data copy và disk throughput |
| Link | Hard links cùng inode | Rất nhanh; old cluster không còn độc lập sau khi new start |
| Clone | Reflink/copy-on-write | Nhanh nếu filesystem hỗ trợ; đo copy-on-write growth |
| Copy-file-range | Kernel-assisted copy | File độc lập; phụ thuộc kernel/filesystem |

Không đo bằng copy mode rồi lấy thời gian đó dự báo cho link hoặc clone. Ngược lại, không dùng thời gian link mode để cam kết copy mode.

## 9. Kiểm tra khả năng tương thích trước rehearsal

Chạy pg_upgrade --check trên bản sao rehearsal:

~~~bash
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --check
~~~

Lưu output và logs. Xử lý source version không được hỗ trợ, extension thiếu binary/update path, prepared transactions, invalid indexes, tablespace paths, locale/collation differences, data checksums, disk capacity và objects cần can thiệp.

Chạy --check thành công không phải là phép đo actual upgrade. Nó xác nhận những điều kiện mà bước check có thể kiểm tra.

## 10. Backup và restore rehearsal

Trước khi đo upgrade, cần chứng minh có thể phục hồi cluster.

Một backup plan có thể gồm:

- Base backup.
- WAL archive.
- Backup cấu hình và certificates.
- Inventory extension packages.
- Snapshot storage nếu đảm bảo consistency.
- External secrets được lưu theo security policy.

Rehearsal restore phải kiểm tra backup có thể đọc, WAL archive liên tục, restore target đúng version/path, PostgreSQL khởi động, database/roles tồn tại, ứng dụng test kết nối và thời gian restore thực tế.

Backup chưa được restore test không phải rollback plan đã được chứng minh.

## 11. Đo thời gian backup riêng

Ghi riêng thời điểm bắt đầu/kết thúc, dung lượng nguồn, dung lượng backup, WAL cần replay, throughput, CPU/storage utilization, thời gian kiểm tra backup và thời gian restore.

Không gộp backup online vào downtime nếu nó được thực hiện trước maintenance. Nhưng phải tính backup/restore vào recovery time nếu rollback cần phục hồi từ backup.

## 12. Phân rã maintenance window

| Giai đoạn | Nội dung |
|---|---|
| A. Preflight | Kiểm tra backup, binaries, disk, extensions |
| B. Freeze | Dừng writes và scheduled jobs |
| C. Drain | Hoàn tất transactions, đóng connections |
| D. Shutdown | Dừng old PostgreSQL sạch |
| E. Upgrade | Chạy pg_upgrade |
| F. Startup | Khởi động new cluster |
| G. Post-upgrade | Analyze, extension updates, config |
| H. Validation | Kiểm tra DB và application |
| I. Cutover | Mở traffic và theo dõi |

Có thể thực hiện preflight, package installation và backup trước giờ downtime. Chỉ những bước thực sự yêu cầu cluster dừng mới nằm trong outage window.

## 13. Xác định critical path

Một số bước phụ thuộc tuần tự:

~~~text
Freeze writes
     |
     v
Drain sessions
     |
     v
Stop old cluster
     |
     v
pg_upgrade
     |
     v
Start new cluster
     |
     v
Post-upgrade validation
     |
     v
Application smoke tests
     |
     v
Open traffic
~~~

Một số công việc độc lập có thể chuẩn bị song song trước maintenance: cài target binaries, cài extension packages, chuẩn bị configuration, xác minh backup, chuẩn bị monitoring, kiểm tra endpoint routing và chuẩn bị test scripts.

Không cộng thời gian các công việc chạy song song như thể chúng chạy tuần tự. Ghi critical path và dependency thực tế.

## 14. Tạo timing worksheet

Mỗi bước cần có planned duration, actual duration và owner.

| Step | Planned | Actual | Start/end | Owner |
|---|---:|---:|---|---|
| Freeze writes | 5 phút |  |  | Application |
| Drain sessions | 5 phút |  |  | DBA |
| Stop old cluster | 3 phút |  |  | DBA |
| pg_upgrade | 25 phút |  |  | DBA |
| Start new cluster | 3 phút |  |  | DBA |
| Analyze | 10 phút |  |  | DBA |
| Validation | 10 phút |  |  | QA/App |
| Restore traffic | 4 phút |  |  | Operations |

Các số trên chỉ là ví dụ. Lấy số đo rehearsal của chính hệ thống để lập kế hoạch.

## 15. Ghi timestamp bằng một nguồn thời gian thống nhất

Tất cả operators nên dùng đồng hồ đồng bộ (NTP hoặc time service phù hợp). Runbook nên ghi timestamp có timezone.

~~~text
01:00:00+07:00  Write freeze requested
01:03:12+07:00  Application confirmed no new writes
01:07:45+07:00  Active transactions drained
01:10:02+07:00  Old cluster stopped
01:10:10+07:00  pg_upgrade started
01:34:28+07:00  pg_upgrade completed
01:37:15+07:00  New cluster ready
01:47:30+07:00  Validation passed
01:50:00+07:00  Application traffic restored
~~~

Ghi cả thời điểm command bắt đầu, kết thúc và thời điểm người chịu trách nhiệm xác nhận kết quả. Không dựa vào trí nhớ sau maintenance.

## 16. Đo thời gian từng lệnh

Đo thời gian thực thi bằng công cụ shell phù hợp. Ví dụ Linux:

~~~bash
/usr/bin/time -v /path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --jobs=4 \
  --copy
~~~

Lưu elapsed wall-clock time, user/system CPU time, maximum resident set size nếu có, filesystem I/O, exit code và logs.

Thời gian command không bao gồm thao tác thủ công ngoài command như kiểm tra, chuyển endpoint hoặc chờ ứng dụng xác nhận.

## 17. Đo throughput và disk utilization

Với copy mode, thời gian thường phụ thuộc lượng data và tốc độ đọc/ghi thực tế.

Theo dõi read throughput của old data volume, write throughput của new data volume, IOPS, queue depth, latency, CPU utilization, filesystem free space và tablespace volumes riêng.

Nếu một volume đạt giới hạn IOPS, tăng jobs có thể không cải thiện throughput và có thể làm storage contention nặng hơn.

## 18. Ước lượng thời gian theo dữ liệu

Một mô hình thô:

~~~text
copy_time ≈ bytes_to_copy / effective_copy_throughput
~~~

Ví dụ, nếu cần copy 1.2 TB và throughput thực tế duy trì được 300 MB/s, thời gian lý thuyết vào khoảng 4.000 giây, xấp xỉ 67 phút.

Đây chỉ là ước lượng đơn giản. Thực tế còn có metadata, nhiều files, tablespaces, concurrent I/O, fsync, startup và post-upgrade work.

Không lấy tốc độ peak ngắn hạn làm throughput ổn định. Dùng kết quả rehearsal trên storage tương đương.

## 19. Đo tác động của --jobs

Thử một số mức jobs trong các lần rehearsal riêng:

| Jobs | Upgrade time | Storage latency | CPU | Ghi chú |
|---:|---:|---:|---:|---|
| 1 |  |  |  | Baseline |
| 2 |  |  |  |  |
| 4 |  |  |  |  |
| 8 |  |  |  |  |

Không giả định tăng gấp đôi jobs sẽ giảm một nửa thời gian. Tìm mức throughput tốt nhất mà storage và CPU vẫn ổn định.

## 20. Đo post-upgrade ANALYZE

Sau upgrade, planner statistics cần được thu thập theo kế hoạch.

~~~bash
/path/to/new/bin/vacuumdb \
  --all \
  --analyze-in-stages \
  --jobs=4
~~~

Ghi thời gian riêng cho analyze database nhỏ/lớn, bảng lớn, partitioned tables, jobs và CPU/I/O utilization, cũng như thời gian tới khi query plans đạt trạng thái chấp nhận được.

Có thể ưu tiên các bảng/query quan trọng trước nếu runbook cho phép, nhưng phải có kế hoạch hoàn tất statistics còn lại.

## 21. Đo startup và readiness

PostgreSQL process khởi động không có nghĩa service đã sẵn sàng.

Readiness gate nên xác minh process đang chạy, port/socket nhận kết nối, database mở được, recovery/primary role đúng topology, extensions load thành công, required schemas/roles tồn tại, không có startup errors và read/write probes hoạt động theo policy.

Với HA cluster, xác minh leader state và fencing/replication state theo runbook. Không mở writes chỉ vì health endpoint trả HTTP 200.

## 22. Đo application reconnect

Ứng dụng có thể mất thêm thời gian sau khi database sẵn sàng:

- DNS cache hết hạn.
- Load balancer cập nhật endpoints.
- Connection pools loại bỏ connections cũ.
- Drivers tạo connections mới.
- Workers restart.
- Retry/backoff hoàn tất.
- Cache ứng dụng warm-up.

Ghi thời điểm database ready và thời điểm giao dịch nghiệp vụ đầu tiên thành công. Khoảng cách giữa hai mốc là một phần downtime thực tế.

## 23. Xác định transaction drain

Trước khi dừng old cluster:

- Dừng nhận requests mới hoặc chuyển service sang maintenance mode.
- Đợi requests đang xử lý hoàn tất.
- Xử lý transactions lâu.
- Kiểm tra prepared transactions.
- Kiểm tra sessions idle in transaction.
- Dừng background jobs và schedulers.
- Xác nhận connection pools không reconnect vào old cluster.

Có thể quan sát:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Không terminate sessions hàng loạt mà chưa hiểu transaction owner và tác động nghiệp vụ.

## 24. Kiểm tra prepared transactions

Two-phase commit có thể để lại prepared transactions cần được coordinator xử lý.

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts;
~~~

Trước upgrade, phối hợp với ứng dụng/coordinator để quyết định commit hoặc rollback từng transaction theo nghiệp vụ. Đưa prepared transactions vào preflight checklist để tránh phát hiện blocker trong maintenance window.

## 25. Chuẩn bị write freeze

Runbook cần có hành động cụ thể:

- Bật maintenance mode ở application/API.
- Tắt consumer hoặc queue workers tạo writes.
- Pause scheduled jobs, ETL và batch imports.
- Chặn các nguồn ghi ngoài ứng dụng chính.
- Kiểm tra active sessions và transaction count.
- Xác nhận không còn writes mới.

Nếu có nhiều ứng dụng hoặc direct database clients, cần owner của từng nguồn xác nhận. Một banner bảo trì trên website không chứng minh database đã ngừng nhận writes.

## 26. Copy mode và old cluster

Với pg_upgrade copy mode:

- Relation files được copy sang new cluster.
- Old cluster giữ files độc lập.
- New cluster có thể được kiểm tra trong khi old cluster giữ nguyên trạng thái tại thời điểm upgrade.
- Cần disk space đủ cho cả hai clusters.

Đây là lựa chọn dễ lập kế hoạch rollback nhất nếu dung lượng cho phép.

Tuy nhiên, nếu new cluster đã nhận writes, old cluster không có các thay đổi đó. Việc old cluster còn khởi động được không đồng nghĩa có thể chuyển ứng dụng về mà không mất dữ liệu.

## 27. Rollback boundary của link mode

Với pg_upgrade link mode, old/new relation files chia sẻ cùng inode.

Trước khi new cluster được khởi động, quy trình có thể còn đường quay lại old cluster theo hướng dẫn của phiên bản cụ thể. Nhưng khi new cluster bắt đầu hoạt động và ghi vào các files liên kết, old cluster không còn là bản rollback độc lập.

~~~text
pg_upgrade link complete
        |
        v
New cluster not started?
        |
    +---+---+
    |       |
   Yes      No
    |       |
    v       v
Rollback   Old cluster is not an
may be    independent fallback
possible  after linked writes
~~~

Không khởi động old cluster sau khi new cluster đã ghi dữ liệu trên linked files.

## 28. Clone mode và rollback

Clone/reflink tạo file logic độc lập bằng copy-on-write nếu filesystem hỗ trợ.

Điều này giúp giữ old cluster như một frozen fallback. Nhưng khi new cluster nhận writes, old cluster không tự nhận các transaction mới.

Nếu phải quay lại old cluster sau khi writes đã phát sinh trên new, phải xác định dữ liệu nào đã được xác nhận cho clients, writes nào cần giữ, có thể export/reconcile hay replay không và RPO thực tế nếu không thể bảo toàn mọi transaction.

Không coi copy-on-write là replication.

## 29. Copy-file-range và rollback

Copy-file-range là cơ chế kernel-assisted copy file ranges trên môi trường hỗ trợ. Nó tạo files độc lập, do đó old cluster có thể giữ nguyên.

Tuy vậy, giống copy/clone, old cluster là trạng thái trước upgrade. Các writes trên new cluster không tự động quay ngược về old. Rollback sau cutover vẫn cần xử lý write divergence.

## 30. Xác định rollback triggers

Không nên đợi tới khi maintenance window gần hết mới tranh luận có rollback hay không.

Định nghĩa triggers trước:

- pg_upgrade thất bại và không thể khắc phục trong thời gian còn lại.
- New cluster không khởi động được.
- Required extensions không load.
- Database hoặc tablespaces không đầy đủ.
- Role/authentication failures ảnh hưởng ứng dụng.
- Data validation sai lệch vượt ngưỡng.
- Critical query latency vượt SLO.
- Application smoke tests thất bại.
- Replication/backup không hoạt động theo yêu cầu.
- Không thể xác nhận single-writer hoặc HA safety.

Mỗi trigger cần có người quyết định và thời hạn quyết định.

## 31. Go/no-go gates

| Gate | Điều kiện GO | Nếu NO-GO |
|---|---|---|
| Preflight | Backup, binaries, disk, extensions sẵn sàng | Không bắt đầu |
| Freeze | Writes đã dừng và sessions được drain | Tiếp tục drain hoặc hủy |
| Upgrade | pg_upgrade thành công | Khắc phục trong time budget hoặc rollback |
| Startup | New cluster ready | Giữ traffic đóng, điều tra |
| Validation | Data/roles/extensions đạt | Rollback theo boundary |
| Application | Smoke tests và critical transactions đạt | Không mở traffic rộng |
| Cutover | Monitoring và owners sẵn sàng | Giữ maintenance mode |

Không bỏ qua gate chỉ vì đã gần hết maintenance window. Có thể cần chọn rollback sớm hơn để còn đủ thời gian phục hồi.

## 32. Đặt rollback decision deadline

Ví dụ maintenance window 90 phút:

- 0–10 phút: freeze/drain/shutdown.
- 10–40 phút: pg_upgrade.
- 40–55 phút: startup và post-upgrade checks.
- 55–70 phút: validation.
- 70–80 phút: application smoke tests.
- 80–90 phút: buffer/rollback decision.

Các mốc chỉ minh họa. Rehearsal phải cung cấp số liệu thật.

Đặt deadline cuối để quyết định tiếp tục hay rollback. Nếu tới deadline mà critical gate chưa đạt, thực hiện nhánh đã định trước, không tiếp tục thử vô thời hạn.

## 33. Rollback trước khi new cluster nhận writes

Đây là trường hợp đơn giản nhất với copy/clone mode:

1. Giữ application ở maintenance mode.
2. Chặn write endpoint tới new cluster.
3. Dừng new cluster sạch sẽ.
4. Giữ logs và data directory mới để điều tra.
5. Xác nhận old cluster còn độc lập và không bị thay đổi.
6. Khởi động old cluster bằng đúng old binaries.
7. Xác minh database và roles.
8. Chuyển endpoint về old cluster.
9. Reconnect ứng dụng.
10. Chạy smoke tests và mở traffic.

Đối với link mode, chỉ thực hiện rollback nếu new cluster chưa start/ghi và quy trình rollback của target version cho phép. Nếu không chắc, dừng và dùng backup recovery procedure.

## 34. Rollback sau khi new cluster đã nhận writes

Đây là trường hợp phức tạp hơn.

Old cluster không có các transaction đã commit trên new cluster. Chỉ đổi endpoint sẽ làm mất những writes mới khỏi trạng thái ứng dụng đang nhìn thấy.

Cần đánh giá:

- Những transaction nào đã được xác nhận?
- Có thể export changes từ new cluster không?
- Có logical audit/CDC stream không?
- Có business event log đủ để replay không?
- Có thể forward-fix trên new cluster không?
- Có thể restore một backup và replay WAL theo recovery design không?
- RPO cho phép mất những writes nào?

Một số hệ thống chọn forward-fix trên new cluster vì rollback dữ liệu không an toàn. Quyết định phải dựa trên failure type và data consistency, không chỉ vào thời gian.

## 35. Không đồng nhất rollback code với rollback data

Có thể rollback ứng dụng binary trong khi database schema/data đã thay đổi.

Ví dụ application release mới dùng schema mới; database migration đã thêm hoặc cập nhật data; rollback application code về bản cũ không làm schema tự quay lại. Old application có thể không tương thích với schema mới.

Chuẩn bị compatibility strategy:

- Expand/contract migrations.
- Backward-compatible schema changes.
- Feature flags.
- Versioned application deployment.
- Data migration checkpoints.
- Forward-fix plan.

Database major upgrade và application schema migration cần được quản lý như hai rủi ro liên quan nhưng khác nhau.

## 36. PITR không phải rollback tức thời

Point-in-time recovery có thể phục hồi cluster về một thời điểm trước sự cố bằng base backup và WAL archive.

Quy trình thường gồm:

1. Chọn base backup phù hợp.
2. Restore vào data directory riêng.
3. Cấu hình WAL archive recovery.
4. Chỉ định target time/LSN/transaction theo khả năng version.
5. Chạy recovery.
6. Xác minh dữ liệu.
7. Mở endpoint sau khi được phê duyệt.

PITR có thể mất nhiều thời gian và có thể làm mất transactions sau recovery target. Đo thời gian restore/replay trong rehearsal; không giả định PITR hoàn tất trong vài phút.

## 37. Rollback bằng restore backup

Nếu old cluster không còn sử dụng được hoặc link mode đã vượt rollback boundary:

- Cách ly cluster lỗi.
- Restore backup độc lập vào cluster mới.
- Replay WAL tới target point phù hợp.
- Kiểm tra database consistency.
- Cập nhật configuration và extensions.
- Xác minh ứng dụng.
- Chuyển endpoint.

Đây là recovery path riêng, có thể có RTO dài hơn việc khởi động old cluster. Phải diễn tập bằng backup thật.

## 38. Chọn old cluster hay backup để quay lui

| Tình huống | Recovery path cần cân nhắc |
|---|---|
| Copy/clone, new chưa nhận writes | Old frozen cluster có thể là đường quay lại |
| Link, new chưa start | Theo rollback procedure chính xác của version |
| Link, new đã ghi | Không dùng old cluster như bản độc lập; restore/recovery |
| New đã nhận writes, old thiếu data | Reconcile, forward-fix hoặc PITR theo policy |
| Old cluster bị hỏng | Restore backup và replay WAL |
| Data corruption đã replicate | PITR/backup tới thời điểm trước corruption |

Một old cluster không phải lúc nào cũng là lựa chọn đúng. Nếu upgrade thất bại do data corruption hoặc storage issue, old files có thể cũng bị ảnh hưởng tùy mode/hạ tầng.

## 39. Backup mới trước khi xóa old cluster

Sau khi new cluster ổn định:

- Tạo base backup của new major version.
- Xác minh WAL archiving.
- Thực hiện restore test.
- Xác minh monitoring và alerting.
- Ghi nhận backup retention.
- Giữ old cluster cho tới khi rollback window kết thúc theo policy.

Không chạy generated cleanup script hoặc xóa old data directory chỉ vì ứng dụng đã mở traffic.

## 40. Đo downtime bằng nhiều lần rehearsal

Một rehearsal đơn lẻ có thể bị ảnh hưởng bởi cache, storage noise và workload không đại diện.

Nên chạy nhiều lần trong môi trường có thể reset về baseline:

- Rehearsal 1: xác minh quy trình và tìm blockers.
- Rehearsal 2: đo timing sau khi sửa.
- Rehearsal 3: xác minh timing ổn định và diễn tập rollback.
- Rehearsal bổ sung: thử failure injection hoặc recovery path nếu cần.

Không cần lặp lại mọi bước nếu đã có bằng chứng ổn định; nhưng mọi thay đổi lớn về data size, storage, binaries hoặc extensions cần đánh giá lại.

## 41. Đo median và worst observed duration

Ghi duration của từng bước qua các lần rehearsal.

| Step | Run 1 | Run 2 | Run 3 | Worst observed |
|---|---:|---:|---:|---:|
| Drain |  |  |  |  |
| Shutdown |  |  |  |  |
| Upgrade |  |  |  |  |
| Startup |  |  |  |  |
| Analyze |  |  |  |  |
| Validation |  |  |  |  |
| App reconnect |  |  |  |  |

Dùng median để hiểu run điển hình và worst observed để đánh giá buffer. Với số mẫu ít, worst observed không phải percentile thống kê đáng tin cậy; ghi rõ số lần thử và điều kiện.

## 42. Ngoại suy khi production data lớn hơn rehearsal

Nếu rehearsal có dataset nhỏ hơn production:

- So sánh tổng relation bytes, không chỉ database count.
- So sánh số lượng files và tablespaces.
- So sánh index/TOAST proportions.
- So sánh storage throughput.
- Xác định phần thời gian cố định và phần tỷ lệ theo data size.
- Chạy thêm rehearsal trên snapshot lớn hơn nếu khả thi.

Không ngoại suy tuyến tính một cách mù quáng. Một cluster có hàng triệu small files có thể có metadata overhead lớn hơn dự kiến từ tổng bytes.

## 43. Data validation sau upgrade

Validation phải có checks phù hợp workload:

- Database/schema/table inventory.
- Row counts hoặc business aggregates quan trọng.
- Sequence values và ownership.
- Constraints và index validity.
- Extension state.
- Roles, owners và grants.
- Large objects nếu ứng dụng dùng.
- Collation warnings.
- Critical stored procedures.
- Representative query results.

Ví dụ business aggregate:

~~~sql
SELECT
    count(*) AS order_count,
    min(created_at) AS oldest_order,
    max(created_at) AS newest_order,
    sum(total_amount) AS total_amount
FROM public.orders;
~~~

Chọn các invariant có ý nghĩa nghiệp vụ. Không bắt buộc full table count cho mọi bảng nếu việc đó vượt maintenance window; có thể chuẩn bị validation queries có chọn lọc và kiểm tra sâu sau cutover.

## 44. Application smoke tests

Một bộ smoke tests nên bao gồm:

1. Login bằng application role.
2. Đọc một record quan trọng.
3. Ghi một transaction test nếu policy cho phép.
4. Commit và đọc lại kết quả.
5. Thực hiện update/delete trên test fixture có thể khôi phục.
6. Kiểm tra sequence-generated keys.
7. Chạy critical stored procedures.
8. Kiểm tra background jobs/queue consumers.
9. Kiểm tra connection pool và retry.
10. Xác nhận không còn kết nối tới old endpoint.

Smoke tests phải chạy trong maintenance rehearsal và có kết quả có thể lưu lại.

## 45. Kiểm tra extension và configuration

Sau khi new cluster start:

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;

SELECT
    name,
    setting,
    source,
    context
FROM pg_settings
WHERE source <> 'default'
ORDER BY name;
~~~

Đối chiếu với inventory trước upgrade. Kiểm tra extension libraries, shared_preload_libraries, authentication, TLS, archive settings, logging và memory parameters.

Một cluster có thể mở được database nhưng một extension quan trọng hoặc background worker vẫn lỗi.

## 46. Replication và HA validation

Nếu dùng physical replication:

- Xác minh standbys được rebuild/rejoin đúng version.
- Kiểm tra WAL receiver.
- Kiểm tra replay progress.
- Kiểm tra replication slots và WAL retention.
- Kiểm tra archive/restore.
- Diễn tập failover trên staging.

Nếu dùng logical replication/CDC:

- Kiểm tra publications/subscriptions.
- Xác minh logical slots và consumers.
- Theo dõi lag và WAL retention.
- Xác minh external connectors hỗ trợ target version.

Không mở production traffic nếu backup/replication requirements là một phần của service readiness mà chưa đạt.

## 47. Connection routing và DNS

Sau upgrade, endpoint có thể cần thay đổi:

- DNS record.
- Virtual IP.
- Load balancer backend.
- Service discovery.
- PgBouncer/HAProxy configuration.
- Application connection string.

Đo thời gian propagation và reconnect. DNS TTL không bảo đảm mọi client bỏ cache đúng hạn; connection pools có thể giữ session cũ.

Giữ old endpoint cách ly hoặc read-only theo thiết kế để tránh ứng dụng ghi nhầm vào cluster cũ sau cutover.

## 48. Communication plan và phân vai

Runbook cần nêu maintenance start/end, dịch vụ bị ảnh hưởng, read-only hay full outage, kênh cập nhật trạng thái, người ra quyết định GO/NO-GO, người điều phối DBA/application/infrastructure/QA, người có quyền rollback và kênh escalation.

Ví dụ phân vai:

| Vai trò | Trách nhiệm |
|---|---|
| Change owner | Chịu trách nhiệm tổng thể và quyết định |
| DBA lead | Backup, stop, pg_upgrade, startup, SQL validation |
| Infrastructure | Storage, filesystem, VM, network, monitoring |
| Application lead | Write freeze, drain, reconnect, smoke tests |
| QA | Chạy test cases và báo kết quả |
| Incident commander | Theo dõi timeline, quyết định rollback/escalation |
| Communications | Cập nhật trạng thái cho stakeholders |

Một bước quan trọng cần một owner rõ ràng. Tránh tình trạng “mọi người cùng chịu trách nhiệm”.

## 49. Chuẩn bị runbook thực thi

Runbook cần có:

- Preconditions.
- Exact commands với paths/ports thật.
- Expected output hoặc exit code.
- Log locations.
- Owner.
- Timeout.
- Verification query.
- Failure branch.
- Rollback action.
- Contact/escalation.

Không dùng placeholders trong bản runbook production cuối cùng. Ví dụ học tập có thể dùng /path/to/..., nhưng operator cần thay bằng paths thực tế và được review trước maintenance.

## 50. Command log và evidence

Mỗi bước nên lưu timestamp, operator, command/action, exit code, output/log reference, verification result và decision.

Không ghi password, tokens hoặc connection secrets vào command logs. Dùng credential manager hoặc secret injection theo policy.

Evidence giúp postmortem và so sánh giữa các lần rehearsal.

## 51. Failure injection có kiểm soát

Có thể diễn tập các lỗi trong staging:

- Thiếu disk space.
- Extension binary thiếu.
- pg_upgrade --check báo blocker.
- New cluster không start do config.
- Application authentication fail.
- DNS/endpoint update chậm.
- Standby không rejoin.
- Backup restore chậm.
- Một smoke test trả kết quả sai.

Mỗi thử nghiệm phải có môi trường reset được và người giám sát. Không inject failure trên production chỉ để kiểm tra runbook.

## 52. Diễn tập quyết định rollback

Không chỉ thử command rollback; cần thử cả quá trình ra quyết định:

1. Giả lập một critical validation failure.
2. Người chịu trách nhiệm đọc evidence.
3. So sánh với rollback trigger.
4. Ra quyết định trước deadline.
5. Đóng write paths tới new cluster.
6. Thực hiện recovery path phù hợp.
7. Xác minh old/restored cluster.
8. Reconnect ứng dụng.
9. Đo recovery time.
10. Ghi lại các bước runbook còn thiếu.

Một rollback procedure chưa từng được chạy là một giả thuyết, không phải khả năng đã được chứng minh.

## 53. Ví dụ runbook timeline

Bảng sau minh họa cách ghi nhận, không phải thời gian chuẩn:

| Thời điểm | Hành động | Gate |
|---|---|---|
| T-7 ngày | Restore rehearsal, extension check | Backup restore pass |
| T-1 ngày | Preflight, disk, pg_upgrade --check | No blockers |
| 01:00 | Write freeze | App owners confirm |
| 01:05 | Drain sessions | No active writes |
| 01:10 | Stop old cluster | Process stopped |
| 01:12 | Run pg_upgrade | Exit success |
| 01:40 | Start new cluster | Readiness pass |
| 01:48 | Analyze and extension checks | No critical errors |
| 02:00 | DB/application validation | All critical tests pass |
| 02:10 | Restore traffic | Monitoring healthy |
| 02:25 | End heightened watch | Owners sign off |

T-7 ngày và T-1 ngày là thời điểm chuẩn bị trước change window. Trong thực tế, một số bước có thể cần nhiều ngày hoặc nhiều lần rehearsal.

## 54. Quyết định GO sau rehearsal

Một rehearsal đạt yêu cầu khi:

- Các bước runbook có thể thực hiện lặp lại.
- Timing nằm trong maintenance window có buffer.
- Backup restore được chứng minh.
- Rollback được diễn tập theo mode đã chọn.
- Extensions và external dependencies sẵn sàng.
- Application smoke tests pass.
- Owners và escalation path rõ.
- Không còn blocker chưa có cách xử lý.
- RTO/RPO thực tế phù hợp mục tiêu.

Nếu thời gian thực tế vượt window, điều chỉnh phương pháp, hạ tầng hoặc scope rồi rehearsal lại. Không giảm tiêu chí validation chỉ để vừa lịch.

## 55. Sau cutover: heightened monitoring

Trong giai đoạn đầu sau cutover, tăng cường quan sát:

- Connection count và failed logins.
- Query latency và error rates.
- CPU, memory và storage I/O.
- Deadlocks và lock waits.
- Autovacuum/analyze.
- WAL generation và replication lag.
- Temp files.
- Checkpoint behavior.
- Backup jobs.
- Application queue backlog.
- Critical business transactions.

Xác định trước thời lượng heightened monitoring và người chịu trách nhiệm theo dõi.

## 56. Khi nào được xóa old cluster?

Chỉ xóa old cluster khi:

- New cluster đã hoạt động ổn định.
- Application owners xác nhận.
- Backup mới đã hoàn tất và restore được.
- WAL archive/replication đạt yêu cầu.
- Monitoring/alerts hoạt động.
- Rollback window đã hết hoặc được change owner đóng.
- Đã lưu logs, evidence và configuration inventory.

Nếu dùng link mode, không dùng old cluster làm rollback sau khi new cluster start. Nhưng vẫn cần backup độc lập trước khi upgrade.

## 57. Checklist production upgrade

**Trước maintenance**

1. Xác định source/target major versions được hỗ trợ.
2. Đọc release notes và pg_upgrade docs.
3. Inventory databases, roles, tablespaces và extensions.
4. Xác minh backup/restore và WAL archive.
5. Rehearse trên bản sao production-like.
6. Chọn copy/link/clone/copy-file-range theo rollback, disk và filesystem.
7. Cài target binaries và extension packages.
8. Initdb cluster mới với compatible settings.
9. Chạy pg_upgrade --check.
10. Chốt maintenance window và rollback boundary.

**Trong maintenance**

11. Dừng writes và scheduled jobs.
12. Shutdown old cluster sạch.
13. Xác nhận data directories và tablespaces.
14. Chạy actual pg_upgrade.
15. Lưu logs và generated scripts.
16. Review configuration mới.
17. Start new cluster và đọc logs.

**Sau upgrade**

18. Chạy ANALYZE theo kế hoạch.
19. Update extensions khi cần.
20. Kiểm tra roles, grants, databases, tablespaces và objects.
21. Kiểm tra collation/index warnings.
22. Khôi phục backup, monitoring và replication.
23. Chạy application smoke tests và representative workload.
24. Chuyển traffic sau khi được xác nhận.
25. Chỉ xóa old cluster sau khi rollback window kết thúc.

## 58. Bài tập thực hành

### Bài 1 — RTO

RTO đo điều gì?

**Gợi ý:** thời gian tối đa để dịch vụ phục hồi.

### Bài 2 — RPO

RPO đo điều gì?

**Gợi ý:** lượng dữ liệu có thể mất theo mục tiêu recovery.

### Bài 3 — Downtime

Vì sao thời gian pg_upgrade chạy không phải toàn bộ downtime?

**Gợi ý:** còn freeze, drain, startup, validation và reconnect.

### Bài 4 — Rehearsal

Vì sao cần môi trường production-like?

**Gợi ý:** timing phụ thuộc data size, filesystem, storage và workload.

### Bài 5 — Timing worksheet

Mỗi bước nên ghi những trường nào?

**Gợi ý:** planned/actual duration, timestamps, owner và result.

### Bài 6 — Critical path

Vì sao phải phân biệt công việc tuần tự và song song?

**Gợi ý:** không cộng thời gian parallel tasks như chúng chạy nối tiếp.

### Bài 7 — Backup

Một backup chưa restore test có chứng minh rollback được không?

**Gợi ý:** không.

### Bài 8 — Copy mode

Copy mode giữ old cluster ra sao?

**Gợi ý:** relation files độc lập, giữ trạng thái trước upgrade.

### Bài 9 — Link mode

Khi nào old cluster mất tính độc lập?

**Gợi ý:** sau khi new cluster bắt đầu sử dụng/ghi các hard-linked files.

### Bài 10 — Clone mode

Clone khác copy ở điểm nào?

**Gợi ý:** copy-on-write/reflink có thể chia sẻ extents ban đầu.

### Bài 11 — Writes sau cutover

Vì sao không thể chỉ đổi endpoint về old cluster?

**Gợi ý:** old cluster thiếu writes đã commit trên new.

### Bài 12 — Write freeze

Những nguồn nào cần dừng?

**Gợi ý:** API, workers, ETL, schedulers và direct clients.

### Bài 13 — Transaction drain

View nào giúp xem sessions và transaction start?

**Gợi ý:** pg_stat_activity.

### Bài 14 — Prepared transactions

View nào liệt kê prepared transactions?

**Gợi ý:** pg_prepared_xacts.

### Bài 15 — Readiness

PostgreSQL process chạy có đủ để mở traffic không?

**Gợi ý:** không; cần DB, extension, role và application validation.

### Bài 16 — Application reconnect

Những yếu tố nào làm reconnect chậm?

**Gợi ý:** DNS cache, connection pool, retry/backoff và worker restart.

### Bài 17 — Rollback trigger

Nêu ba ví dụ trigger cần rollback.

**Gợi ý:** startup failure, critical validation mismatch, application smoke test failure.

### Bài 18 — Decision deadline

Vì sao cần deadline cho GO/NO-GO?

**Gợi ý:** giữ đủ thời gian cho nhánh rollback.

### Bài 19 — PITR

PITR cần những thành phần nào?

**Gợi ý:** base backup và WAL archive liên tục.

### Bài 20 — Link rollback

Có thể dùng old cluster như bản rollback sau khi new cluster ghi linked files không?

**Gợi ý:** không an toàn.

### Bài 21 — Copy rollback

Copy mode có tự đồng bộ writes mới về old không?

**Gợi ý:** không.

### Bài 22 — RTO measurement

Cần đo từ mốc nào tới mốc nào?

**Gợi ý:** theo định nghĩa service recovery đã thống nhất, thường tới khi ứng dụng giao dịch thành công.

### Bài 23 — ANALYZE

Vì sao post-upgrade ANALYZE có thể nằm trong maintenance plan?

**Gợi ý:** planner statistics cần được thu thập lại.

### Bài 24 — Storage throughput

Vì sao cần đo IOPS và latency cùng throughput?

**Gợi ý:** bottleneck có thể là IOPS/latency, không chỉ MB/s.

### Bài 25 — Parallel jobs

Tăng jobs có luôn giảm thời gian không?

**Gợi ý:** không; storage contention có thể tăng.

### Bài 26 — Data validation

Nêu một business invariant có thể kiểm tra.

**Gợi ý:** order count, tổng amount hoặc aggregate quan trọng.

### Bài 27 — Extension readiness

Vì sao extension packages cần chuẩn bị trước?

**Gợi ý:** target server cần native libraries/control files tương thích.

### Bài 28 — HA readiness

Sau major upgrade, vì sao phải xác minh standbys?

**Gợi ý:** old standbys có thể cần rebuild/reseed theo target version.

### Bài 29 — Old cluster cleanup

Khi nào được xóa old cluster?

**Gợi ý:** sau validation, backup/restore test, monitoring và rollback window.

### Bài 30 — Rehearsal result

Một rehearsal đạt GO cần những bằng chứng nào?

**Gợi ý:** timing, backup restore, rollback drill, validation và owner sign-off.

## 59. Câu hỏi thường gặp

### Downtime có bắt đầu khi database stop không?

Không nhất thiết. Nếu application đã ngừng nhận writes trước đó thì write downtime bắt đầu từ mốc write freeze. Cần định nghĩa service metric cụ thể.

### RTO có bằng maintenance window không?

Không. RTO là mục tiêu recovery; maintenance window là khoảng thời gian thay đổi được lên lịch. Có thể liên quan nhưng không đồng nhất.

### Rehearsal có cần dữ liệu production thật không?

Không bắt buộc, nhưng dataset phải đủ đại diện về kích thước, relation layout, extensions và workload. Nếu dùng dữ liệu đã ẩn danh hoặc thu nhỏ, ghi rõ giới hạn ngoại suy.

### Có thể đo pg_upgrade trên máy nhỏ rồi nhân theo dung lượng không?

Chỉ là ước lượng thô. Filesystem metadata, tablespaces, IOPS và file count làm scaling không tuyến tính. Nên rehearsal trên storage gần production.

### Backup trước upgrade có rollback được mọi tình huống không?

Không. Cần xác minh restore, WAL continuity, RPO và thời gian phục hồi. Backup cũng không tự xử lý writes phát sinh sau backup.

### Copy mode có cho phép quay lại sau khi new cluster nhận writes không?

Old cluster vẫn độc lập nhưng thiếu writes mới. Muốn quay lại mà không mất dữ liệu cần reconciliation/replay hoặc recovery plan riêng.

### Clone mode có tương đương replication không?

Không. Clone tạo bản copy-on-write độc lập tại thời điểm clone; các thay đổi sau đó không được đồng bộ giữa hai clusters.

### Link mode có rollback được không?

Chỉ trong giới hạn trước khi new cluster sử dụng/ghi linked files và theo procedure của version. Sau đó old cluster không còn độc lập.

### Nếu new cluster start nhưng chưa nhận application writes thì sao?

Vẫn cần đánh giá các ghi nội bộ và thao tác phát sinh trong quá trình startup. Với link mode, không tự giả định old cluster an toàn; làm theo chính xác rollback procedure của target version và rehearsal đã chứng minh.

### Nếu smoke test thất bại sau khi đã có writes thì sao?

Giữ traffic theo incident policy, xác định writes đã commit, rồi chọn forward-fix, reconciliation hoặc recovery path. Không đổi endpoint về old một cách máy móc.

### PITR có thể thay thế old cluster không?

Có thể là một recovery path, nhưng thời gian restore/replay và dữ liệu mất phụ thuộc backup/WAL. Phải đo trong rehearsal.

### Có nên chạy tất cả validation trước khi mở traffic?

Các critical validations nên hoàn tất trước khi mở writes. Một số deep checks có thể tiếp tục sau cutover nếu đã được đánh giá rủi ro và có owner.

### Có cần rehearsal rollback nếu chọn copy mode?

Có. Copy mode chỉ giữ old files độc lập; operator vẫn cần chứng minh dừng new, khởi động old, chuyển endpoint và xác minh ứng dụng.

### Khi nào nên kết thúc heightened monitoring?

Khi metrics và business transactions ổn định qua khoảng thời gian đại diện cho workload, backup/replication đạt và các owners sign off.

## 60. Tổng kết

Một kế hoạch rehearsal và rollback có thể triển khai cần:

1. Định nghĩa downtime, RTO và RPO.
2. Dựng môi trường rehearsal tương đương production.
3. Inventory cluster, extensions, tablespaces, HA và application dependencies.
4. Kiểm tra backup và restore thực tế.
5. Chạy pg_upgrade --check.
6. Chọn copy/link/clone/copy-file-range dựa trên filesystem, disk và rollback requirement.
7. Tách preflight khỏi maintenance window.
8. Đo freeze, drain, shutdown, upgrade, startup, analyze, validation và reconnect.
9. Ghi timestamp, owner, exit code và evidence.
10. Xác định critical path, buffer và decision deadline.
11. Đặt rollback triggers và GO/NO-GO gates.
12. Diễn tập rollback trước production change.
13. Không quay về old cluster một cách máy móc nếu new đã nhận writes.
14. Kiểm tra extension, roles, data invariants, replication và application.
15. Tạo backup mới, xác minh restore trước khi xóa old cluster.

Những nguyên tắc cần nhớ:

- Downtime phải được đo theo khả năng phục vụ của ứng dụng, không chỉ thời gian database process dừng.
- RTO/RPO phải được thống nhất và kiểm chứng.
- Rehearsal cần dữ liệu, storage, binaries và extensions đại diện.
- pg_upgrade --check là preflight, không phải actual timing.
- Copy giữ old data độc lập nhưng không đồng bộ writes mới.
- Link có rollback boundary nghiêm ngặt sau khi new cluster start/ghi.
- Clone/reflink giữ clusters độc lập nhưng không phải replication.
- Backup chỉ có giá trị khi restore được và thời gian recovery đã đo.
- Đặt rollback deadline trước khi hết maintenance window.
- Validation critical phải pass trước khi mở traffic.
- Nếu đã có writes trên new cluster, phải xử lý data divergence trước khi quay lại old.
- Giữ logs, evidence và old cluster cho tới khi rollback window đóng.
- Chỉ kết thúc change khi application, backup, replication và monitoring đều được xác nhận.

Sơ đồ quyết định:

~~~text
             Rehearsal completed
                     |
                     v
          Backup restore proven?
               /          \
             No            Yes
             |              |
             v              v
          NO-GO       pg_upgrade --check
                            |
                            v
                   Actual upgrade rehearsal
                            |
                            v
                   Startup + validation
                            |
                     All critical gates?
                       /          \
                     No            Yes
                     |              |
                     v              v
              Rollback drill    Open traffic
                     |              |
                     v              v
             Recovery verified  Heightened monitoring
                                    |
                                    v
                         Backup/replication stable?
                              /           \
                            No             Yes
                            |               |
                            v               v
                         Continue       Close rollback
                         monitoring     window safely
~~~

**Kết luận:** Diễn tập nâng cấp phải đo toàn bộ hành trình từ write freeze tới khi ứng dụng thực hiện thành công giao dịch đầu tiên trên cluster mới. Phương án quay lui phải phù hợp với transfer mode, backup và trạng thái writes sau cutover. Khi đã đo được từng bước, xác định critical gates và diễn tập cả rollback, đội vận hành mới có cơ sở cam kết maintenance window và đưa ra quyết định GO/NO-GO có kiểm soát.
