# Theo dõi thất bại sao lưu và tổ chức diễn tập phục hồi trong PostgreSQL

## 1. Sao lưu chỉ có giá trị khi phục hồi được

Một hệ thống PostgreSQL có thể báo rằng job backup đã chạy thành công, nhưng điều đó chưa chứng minh database có thể phục hồi. File backup có thể thiếu WAL cần thiết, archive có thể bị gián đoạn, manifest có thể không hợp lệ, encryption key có thể không truy cập được hoặc bản backup có thể được tạo từ một cluster khác. Một sự cố chỉ được phát hiện khi cần restore sẽ biến backup thành một niềm tin chưa được kiểm chứng.

Quản lý backup vì vậy cần hai vòng kiểm soát song song:

1. **Theo dõi quá trình tạo và bảo vệ backup:** job có chạy đúng lịch, tạo đủ artifacts, archive WAL liên tục, lưu metadata/checksum và giữ dữ liệu theo retention policy hay không?
2. **Kiểm chứng khả năng phục hồi:** có thể dựng một PostgreSQL instance từ backup, phát lại WAL tới target mong muốn, kiểm tra database và ứng dụng, rồi đo thời gian thực tế hay không?

Bài này tập trung vào việc phát hiện thất bại sớm, hiểu tín hiệu giám sát, điều tra nguyên nhân và tổ chức các buổi diễn tập phục hồi có bằng chứng. Nó áp dụng cho physical base backup, WAL archiving/PITR và logical backup như §pg_dump§, đồng thời chỉ ra khác biệt giữa các loại backup.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Xác định mục tiêu RPO/RTO và chuyển chúng thành lịch backup, archive và restore test.
2. Phân biệt physical base backup, WAL archive và logical backup.
3. Xác định những tín hiệu quan trọng trong §pg_stat_archiver§, §pg_stat_wal§, replication views và PostgreSQL logs.
4. Theo dõi trạng thái job, backup catalog, manifest, checksum và retention.
5. Phân loại lỗi backup theo scheduling, permission, storage, network, archive, WAL continuity và restore.
6. Phát hiện archive backlog, replication slot giữ WAL và nguy cơ đầy disk.
7. Kiểm chứng base backup và WAL chain bằng công cụ phù hợp.
8. Tổ chức restore test, PITR drill, failover/disaster recovery drill và tabletop exercise.
9. Đo RTO/RPO thực tế, lưu bằng chứng và xử lý findings sau diễn tập.
10. Viết runbook ứng phó khi backup hoặc phục hồi thất bại.

### 1.2. Nguyên tắc vận hành

- Backup job thành công không đồng nghĩa restore thành công.
- Có base backup nhưng thiếu WAL cần thiết thì có thể không phục hồi tới target mong muốn.
- Có WAL archive nhưng không có base backup phù hợp cũng không đủ để dựng lại cluster.
- Một bản restore chạy được PostgreSQL chưa chắc ứng dụng đã đúng dữ liệu hoặc đáp ứng được traffic.
- Diễn tập phải đo thời gian và kiểm tra kết quả; không chỉ đánh dấu một checklist là hoàn thành.
- Không thử restore đè lên production trong một buổi diễn tập thông thường.
- Không xóa WAL, backup hoặc replication slots thủ công chỉ để làm disk usage giảm.

---

## 2. Các loại backup và phạm vi phục hồi

### 2.1. Physical base backup

Physical backup là bản sao vật lý của PostgreSQL cluster/data directory theo phương pháp được hỗ trợ. Một base backup phù hợp, kết hợp với WAL cần thiết, có thể phục hồi cluster tới một thời điểm trong khoảng WAL liên tục.

Công cụ PostgreSQL thường dùng là §pg_basebackup§; các hệ thống production cũng có thể dùng backup managers hoặc storage snapshots có tích hợp PostgreSQL backup protocol. Cách tạo backup phải bảo đảm consistency và lưu metadata cần thiết.

### 2.2. WAL archiving

WAL archive giữ các WAL segments hoàn chỉnh ở một nơi lưu trữ riêng để có thể phát lại sau base backup. Khi cấu hình continuous archiving/PITR, hệ thống cần:

- Base backup hợp lệ.
- Chuỗi WAL liên tục từ backup tới target recovery.
- Timeline history cần thiết khi có promotion/failover.
- Recovery configuration/target đúng.
- Archive storage có thể truy cập và giải mã.

Thiếu một segment bắt buộc có thể khiến recovery dừng trước target, dù base backup và các segment khác đều còn.

### 2.3. Logical backup

§pg_dump§ tạo bản dump logic của database objects/data; §pg_dumpall§ có thể dump cluster-wide globals và database definitions theo cách riêng. Logical backup hữu ích cho:
- Restore database hoặc objects chọn lọc.
- Di chuyển giữa một số phiên bản/kiến trúc.
- Kiểm tra schema/data độc lập.
- Khôi phục một số đối tượng mà physical restore toàn cluster quá rộng.

Logical dump **không phải physical base backup** và không tạo chuỗi WAL archive để PITR theo cùng cơ chế. Một logical backup có thể nhất quán theo snapshot trong phạm vi của nó, nhưng không thay thế kế hoạch physical recovery nếu yêu cầu RTO/RPO đòi hỏi dựng cả cluster.

### 2.4. Snapshot storage

Snapshot volume/VM có thể hữu ích nếu quy trình snapshot phối hợp đúng với PostgreSQL consistency, WAL và storage semantics. Snapshot crash-consistent không tự động tương đương một base backup hợp lệ. Kiểm tra nhà cung cấp, quiesce/freeze procedure, snapshot consistency group và restore instructions.

### 2.5. Bảng so sánh

| Phương pháp | Phạm vi | Khả năng PITR | Dùng tốt cho |
|---|---|---|---|
| Physical base backup + WAL archive | Toàn cluster/physical files | Có, khi WAL chain liên tục | Disaster recovery, PITR, standby seeding |
| §pg_dump§ | Một database/objects logic | Không theo WAL archive chain | Logical restore, migration, object-level recovery |
| §pg_dumpall§ | Globals và các database theo dump logic | Không thay physical PITR | Cluster logical export |
| Storage snapshot tích hợp đúng | Volume/instance theo snapshot design | Tùy cách kết hợp WAL | Fast recovery/clone khi consistency được bảo đảm |
| Replica/standby | Bản sao đang cập nhật | Không phải backup độc lập | HA/failover, giảm RTO khi đủ điều kiện |

### 2.6. Replica không thay backup

Replica có thể sao chép DELETE nhầm, UPDATE sai, corruption logic và thao tác phá hoại đã commit. Một lỗi vận hành được replicate có thể làm cả primary và standby cùng mất dữ liệu đúng theo WAL. Cần backup độc lập, retention và khả năng phục hồi về thời điểm trước sự cố.

### 2.7. Xác định yêu cầu theo loại sự cố

| Sự cố | Cơ chế cần cân nhắc |
|---|---|
| Mất một database/object | Logical restore hoặc object-level recovery từ bản dump |
| Hỏng/mất primary host | Physical base backup + WAL hoặc standby đủ điều kiện |
| Xóa nhầm dữ liệu đã commit | PITR tới trước thời điểm xóa, hoặc restore vào môi trường riêng rồi trích dữ liệu |
| Hỏng storage/region | Offsite backup, WAL archive và quy trình dựng hạ tầng ở site khác |
| Lỗi schema/deployment | PITR hoặc restore riêng để so sánh; có thể cần rollback ứng dụng |
| Ransomware/credential compromise | Bản backup immutable/offline, tách quyền và quy trình clean-room recovery |

---

## 3. RPO, RTO và mục tiêu bảo vệ dữ liệu

### 3.1. RPO — Recovery Point Objective

**RPO** là lượng dữ liệu tối đa mà tổ chức chấp nhận mất, thường biểu diễn bằng thời gian. Nếu RPO là 15 phút, khi xảy ra sự cố, mục tiêu là phục hồi tới điểm không cũ hơn quá 15 phút so với thời điểm sự cố, theo cách đo được tổ chức thống nhất.

RPO cần được xác định cho từng hệ thống/dataset. Không phải mọi database đều cần RPO bằng 0; mục tiêu phải cân bằng với chi phí, kiến trúc và tác động kinh doanh.

### 3.2. RTO — Recovery Time Objective

**RTO** là thời gian tối đa chấp nhận để đưa dịch vụ trở lại trạng thái hoạt động theo tiêu chí đã định. Cần xác định điểm bắt đầu và kết thúc đo:

- Bắt đầu: thời điểm incident được xác nhận hay thời điểm dịch vụ ngừng?
- Kết thúc: PostgreSQL process khởi động, ứng dụng kết nối được, hay người dùng hoàn tất giao dịch quan trọng?

RTO nghiệp vụ thường phải tính cả hạ tầng, restore, WAL replay, validation, DNS/routing, secret/config, smoke tests và mở traffic.

### 3.3. RPO không chỉ là lịch chạy backup

Giả sử base backup chạy mỗi đêm và WAL archive hoạt động liên tục. RPO có thể nhỏ hơn nhiều so với 24 giờ nếu WAL được archive an toàn và liên tục. Ngược lại, chạy full backup mỗi giờ không bảo đảm RPO một giờ nếu backup job hay WAL archive bị lỗi kéo dài.

### 3.4. RTO không chỉ là tốc độ đọc backup

Thời gian restore phụ thuộc:
- Kích thước data directory.
- Storage/network throughput.
- Số lượng WAL segments cần replay.
- CPU và I/O của target host.
- Recovery target.
- Extensions, tablespaces, configuration và credentials.
- Thời gian kiểm tra dữ liệu/ứng dụng.
- Quy trình DNS, routing, failover và quyền truy cập.

### 3.5. Đặt mục tiêu đo được

Ví dụ một service giả định:

| Chỉ tiêu | Mục tiêu minh họa |
|---|---|
| RPO | Không quá 15 phút |
| RTO | Không quá 90 phút |
| Base backup | Hàng ngày |
| WAL archive | Liên tục, theo dõi backlog theo phút |
| Restore drill | Hàng tháng |
| PITR drill | Hàng quý và sau thay đổi backup pipeline |
| Offsite copy | Có bản sao độc lập theo policy |
| Kiểm tra restore | Tự động tối thiểu mỗi lần backup mới theo mẫu; full restore định kỳ |

Các con số này chỉ minh họa cách biến mục tiêu thành lịch. Mỗi tổ chức phải chọn dựa trên business impact và khả năng thực tế.

### 3.6. Đo RPO thực tế

Một cách ước lượng RPO hiện tại là xác định thời điểm WAL cuối cùng đã được lưu an toàn ở archive hoặc một vị trí phục hồi có thể truy cập, rồi so với thời điểm hiện tại. Nhưng timestamps đơn lẻ có thể không đủ: cần xác nhận WAL chain liên tục và đúng timeline.

RPO thực tế tại một thời điểm nên là kết quả của:
1. Archive/backup metadata.
2. LSN/timeline continuity.
3. Timestamp tương ứng khi có thể xác định.
4. Kiểm tra restore/PITR thực tế.

### 3.7. Đo RTO thực tế

Đo từ lúc bắt đầu quy trình recovery tới lúc đạt **service recovery criteria** đã định. Lưu riêng các mốc:
- Provision infrastructure.
- Fetch/decrypt backup.
- Restore base backup.
- Replay WAL.
- Start PostgreSQL.
- Validate database.
- Validate application.
- Route traffic.
- Business sign-off.

Cách chia này cho biết nút thắt nằm ở storage, recovery, validation hay coordination.

---

## 4. Backup lifecycle và các điểm phải quan sát

### 4.1. Luồng physical backup

~~~text
Schedule / Orchestrator
        |
        v
Start base backup
        |
        +----> Copy data files / tablespaces
        |
        +----> Capture backup metadata / manifest
        |
        v
Complete base backup
        |
        v
Verify files, checksums, catalog
        |
        +---------------------------+
        |                           |
        v                           v
Archive WAL continuously       Copy to offsite/immutable storage
        |                           |
        +-------------+-------------+
                      |
                      v
             Retention / lifecycle
                      |
                      v
             Restore & recovery drills
                      |
                      v
              Evidence / sign-off
~~~

### 4.2. Job state không chỉ success/failure

Một backup job nên có trạng thái đủ chi tiết để điều tra:

- §scheduled§: đã lên lịch.
- §started§: đã bắt đầu.
- §running§: đang chạy.
- §completed§: tiến trình kết thúc thành công.
- §verified§: artifacts qua kiểm tra integrity phù hợp.
- §cataloged§: metadata được ghi vào backup catalog.
- §replicated/offsite§: bản sao đã tới storage độc lập.
- §restore_tested§: đã phục hồi thành công trong một test gần nhất.
- §failed§: job thất bại.
- §partial§: một phần artifacts thành công, phần khác thiếu.
- §expired/pruned§: đã hết retention và được xóa theo policy.

Không phải tool nào cũng có đủ các trạng thái này; có thể map chúng vào job catalog nội bộ.

### 4.3. Mỗi backup cần metadata

Nên lưu ít nhất:
- Backup ID duy nhất.
- Cluster/system identifier.
- PostgreSQL major version và build/tool version.
- Backup type (physical/logical/snapshot).
- Start/end timestamps.
- Start/stop LSN nếu có.
- Timeline.
- Source host/cluster/environment.
- Tablespaces và manifest/checksum metadata.
- WAL range cần cho backup recovery.
- Encryption/key identifier (không lưu secret).
- Storage locations và object versions.
- Retention/expiration date.
- Verification result và restore drill reference.

### 4.4. Backup catalog

Backup catalog là nơi theo dõi backup sets, dependencies, WAL ranges, status và retention. Catalog có thể thuộc backup manager hoặc hệ thống quản trị riêng.

Catalog nên:
- Có backup ID duy nhất và không tái sử dụng.
- Được backup/replicate độc lập.
- Lưu metadata đủ để chọn base backup và WAL chain.
- Phân biệt copy đang upload với copy đã verify.
- Ghi lịch sử failures và remediation.
- Không coi metadata success cũ là bằng chứng rằng object storage vẫn còn file.

### 4.5. Artifact inventory

Mỗi lần backup nên đối chiếu danh sách file/object mong đợi với những gì thực sự tồn tại. Kiểm tra:
- File count/size có hợp lý không.
- Tablespace links/objects có đủ không.
- Manifest có mặt và đọc được không.
- Checksum/size khớp không.
- WAL cần thiết có mặt không.
- Timeline history có được lưu không.
- Encryption metadata/key version có sẵn không.

### 4.6. End-to-end ownership

Một job có thể chạy qua scheduler, backup agent, database, archive process, object storage và catalog. Cần chỉ rõ owner của từng bước. Nếu một component chỉ ghi “request accepted”, không được xem là artifact đã bền ở destination.

---

## 5. Những nguồn tín hiệu trong PostgreSQL

### 5.1. pg_stat_archiver

View §pg_stat_archiver§ theo dõi trạng thái WAL archiver. Ví dụ:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Các trường quan trọng:
- §archived_count§: số lần archive thành công được ghi nhận kể từ lần reset stats.
- §last_archived_wal§: tên WAL file archive thành công gần nhất.
- §last_archived_time§: thời điểm archive thành công gần nhất.
- §failed_count§: số lần archive thất bại được ghi nhận.
- §last_failed_wal§ và §last_failed_time§: WAL file/time thất bại gần nhất.
- §stats_reset§: mốc reset counters.

### 5.2. Counter không thay thế freshness alert

§archived_count§ tăng cho biết có success, nhưng không chứng minh archive đang bắt kịp. Nếu WAL generation cao, một số archive successes vẫn có thể đi cùng backlog tăng. Theo dõi cả:
- Thời gian từ §last_archived_time§.
- WAL current position.
- WAL segment/file backlog nếu công cụ lưu trữ cung cấp.
- Disk usage của §pg_wal§.
- Archive destination health.
- Failure counters và log events.

### 5.3. Stats reset

Các counters có thể được reset; sau reset, §failed_count=0§ không chứng minh trước đó chưa từng có failure. Ghi lại §stats_reset§ và xử lý counters như time series có reset boundary.

### 5.4. pg_stat_wal

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    stats_reset
FROM pg_stat_wal;
~~~

Các counters có thể khác giữa major versions. Dùng để theo dõi WAL volume/rate và hoạt động write/sync; lấy hai mẫu theo thời gian để tính delta. Đây là counters cluster-wide, không quy trực tiếp cho một job nếu có workload khác.

### 5.5. pg_stat_progress_basebackup

Trong các PostgreSQL versions hỗ trợ, view §pg_stat_progress_basebackup§ giúp quan sát base backup đang chạy trên server:

~~~sql
SELECT
    pid,
    phase,
    backup_total,
    backup_streamed,
    tablespaces_total,
    tablespaces_streamed
FROM pg_stat_progress_basebackup;
~~~

Một số cột/phase phụ thuộc version. View này hữu ích để thấy backup có đang tiến triển và phase hiện tại; nó không chứng minh file đã được verify hay offsite copy hoàn tất.

### 5.6. pg_stat_replication

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Replication lag có thể liên quan backup retention vì standby/slot có thể giữ WAL. Nhưng streaming replication healthy không chứng minh archive destination hoặc base backup healthy.

### 5.7. pg_replication_slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots;
~~~

Các cột có thể thay đổi theo version. §restart_lsn§ giúp nhận biết WAL mà slot còn cần; slot inactive lâu có thể giữ WAL và làm §pg_wal§ tăng. Không drop slot chỉ dựa trên tuổi hoặc inactive state trước khi xác định consumer/owner.

### 5.8. pg_stat_database và relation metrics

Database stats có thể hỗ trợ hiểu workload/transaction volume, nhưng không thay backup manager logs. Kết hợp §pg_stat_database§, §pg_stat_wal§, §pg_stat_archiver§, §pg_stat_activity§ và host/storage metrics để phân biệt workload tăng với backup/archive chậm.

### 5.9. PostgreSQL logs

Logs thường là nguồn chi tiết nhất cho lỗi archive/backup:
- Archive command exit code/error.
- Permission denied.
- No space left on device.
- Connection timeout/refused.
- Missing segment/file.
- Checksum/manifest error.
- WAL corruption/read failure.
- Backup start/stop/failure.
- Recovery target not reached hoặc WAL file missing.

Đảm bảo log có timestamp, severity, PID/session context và được giữ đủ lâu. Không log credentials hoặc secrets của archive command.

---

## 6. Theo dõi job backup và pipeline bên ngoài

### 6.1. Scheduler

Kiểm tra:
- Job có được trigger đúng lịch?
- Có overlap với lần chạy trước không?
- Có bị disable/paused?
- Có timeout hoặc bị kill?
- Scheduler service có hoạt động?
- Job run ID có tương quan được với backup ID và PostgreSQL logs?

Một job không xuất hiện trong database logs có thể chưa hề bắt đầu, không phải database từ chối backup.

### 6.2. Backup process

Ghi nhận:
- Process exit code.
- Start/end time và elapsed duration.
- Bytes read/written/transferred.
- Throughput và retry count.
- Backup ID, manifest path.
- Error category và log location.
- Source/target host.
- Tool/version.

Exit code 0 chỉ là một tín hiệu; cần kiểm tra tool có thực sự hoàn thành mọi phase và commit catalog metadata hay không.

### 6.3. Storage destination

Theo dõi:
- Available capacity/quota.
- Object count/size và growth.
- Upload errors, throttling, request timeouts.
- Latency và throughput.
- Permission/credential expiration.
- Lifecycle/retention deletion events.
- Replication/copy status tới offsite.
- Object lock/immutability state nếu được dùng.

### 6.4. Encryption và key management

Backup encrypted chỉ có giá trị nếu key có thể lấy trong recovery scenario. Cần:
- Lưu key identifier/version trong backup metadata.
- Quản lý key ở hệ thống độc lập với nơi chứa backup.
- Có recovery access path khi primary identity provider/region gặp sự cố.
- Diễn tập quyền truy cập và giải mã.
- Không lưu plaintext key trong job logs/catalog.

### 6.5. Network

Theo dõi throughput, packet loss, DNS, TLS expiry, firewall changes và remote storage connectivity. Backup có thể thất bại ở tầng network dù PostgreSQL và backup process vẫn khỏe.

### 6.6. Backup duration regression

Nếu backup duration tăng dần:
- Data size tăng?
- WAL volume/FPI tăng?
- Storage throughput giảm?
- Backup compression/encryption CPU-bound?
- Network throttling?
- Snapshot/copy-on-write behavior thay đổi?
- Backup job cạnh tranh với workload production?

Alert nên so với baseline theo size/workload, không chỉ đặt một thời gian cố định cho mọi database.

### 6.7. Job overlap

Hai full backups chạy đồng thời có thể làm tăng I/O, storage bandwidth và backup window. Scheduler nên giới hạn concurrency theo cluster/storage capacity, đồng thời có timeout/cancel policy rõ ràng.

### 6.8. Không che lỗi bằng retry vô hạn

Retry giúp xử lý transient failures, nhưng retry vô hạn có thể che lỗi permanent và tạo storm. Phân loại retryable/non-retryable, dùng exponential backoff/jitter, giới hạn attempts và alert khi retry budget bị tiêu thụ.

---

## 7. Metrics, dashboard và cảnh báo

### 7.1. Nhóm metrics cần có

Một dashboard backup/recovery nên chia thành các nhóm để người trực vận hành hiểu failure đang ở đâu:

| Nhóm | Metrics/fields | Câu hỏi |
|---|---|---|
| Scheduler | last start, last success, next run, duration, exit code | Job có chạy đúng lịch không? |
| Backup artifacts | backup ID, size, manifest, checksum, catalog state | Có tạo đủ và xác minh được backup không? |
| WAL archiving | last archived time/file, success/failure deltas, backlog | WAL có được lưu liên tục không? |
| WAL generation | wal_bytes delta, FPI, WAL rate | Workload đang tạo WAL nhanh đến đâu? |
| Replication | sent/write/flush/replay LSN, slot restart LSN | Standby/slot có giữ WAL không? |
| Storage | capacity, free bytes, object errors, quota | Có nguy cơ hết dung lượng không? |
| Restore tests | last successful restore, duration, target, result | Backup có thật sự phục hồi được không? |
| Objectives | measured RPO/RTO, age of latest tested backup | Có đáp ứng mục tiêu business không? |

### 7.2. Theo dõi thời điểm archive gần nhất

~~~sql
SELECT
    now() AS observed_at,
    last_archived_wal,
    last_archived_time,
    EXTRACT(EPOCH FROM (clock_timestamp() - last_archived_time))
        AS seconds_since_last_archive,
    archived_count,
    failed_count,
    stats_reset
FROM pg_stat_archiver;
~~~

Đây là một tín hiệu freshness, không phải verdict độc lập. Nếu database idle lâu và không phát sinh WAL segment mới, last_archived_time cũ có thể bình thường. Chỉ alert stale archive khi có WAL generation/segment activity đáng lẽ cần archive hoặc khi backup policy yêu cầu archive timeout cụ thể.

### 7.3. Theo dõi failure counter

Không chỉ nhìn giá trị hiện tại; thu thập counters định kỳ và tính delta giữa hai samples. Nếu stats_reset thay đổi, bắt đầu một baseline mới. Một alert phù hợp thường dựa trên:
- Số failures tăng trong window.
- Last failure time gần đây.
- Failure lặp lại cùng file.
- Archive freshness vượt ngưỡng khi WAL đang được tạo.
- pg_wal usage tăng đồng thời.

### 7.4. Tính WAL generation rate

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    wal_bytes,
    wal_records,
    wal_fpi,
    stats_reset
FROM pg_stat_wal;
~~~

Lấy hai samples cách nhau một khoảng đã biết. Nếu wal_bytes tăng 600 MiB trong 10 phút thì WAL generation trung bình xấp xỉ 60 MiB/phút trong window. Kiểm tra stats_reset không đổi và hiểu đây là counter toàn cluster.

### 7.5. Theo dõi slot giữ WAL

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
      WHEN restart_lsn IS NULL THEN NULL
      ELSE pg_size_pretty(
          pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
      )
    END AS retained_wal_distance,
    wal_status
FROM pg_replication_slots
ORDER BY restart_lsn NULLS FIRST;
~~~

Khoảng cách LSN là estimate về WAL stream còn phía trước restart LSN, không phải chính xác dung lượng local disk bị slot giữ trong mọi tình huống. Một slot inactive có thể giữ WAL rất lâu. Trước khi can thiệp phải xác định owner, consumer và khả năng reinitialize.

### 7.6. Theo dõi base backup đang chạy

~~~sql
SELECT
    pid,
    phase,
    backup_total,
    backup_streamed,
    tablespaces_total,
    tablespaces_streamed
FROM pg_stat_progress_basebackup;
~~~

Dùng view để nhận biết backup đang tiến triển hay đứng lâu ở một phase. Kết hợp process logs, network throughput và storage metrics để xác định bottleneck. Backup progress không thay thế kiểm tra exit code và manifest.

### 7.7. Theo dõi WAL directory

Trên các versions hỗ trợ và role có quyền phù hợp, pg_ls_waldir() có thể liệt kê WAL files:

~~~sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size,
    max(modification) AS newest_file_time
FROM pg_ls_waldir();
~~~

Cách này chỉ quan sát thư mục WAL hiện tại. Để hiểu dung lượng thực tế, nên dùng filesystem metrics vì directory listing không thay thế kiểm tra mount capacity, inode usage, reserved space hoặc các file liên quan khác. Không xóa entries từ kết quả này.

### 7.8. Dashboard theo từng backup

Mỗi backup run nên có một dòng timeline hiển thị:
- Scheduled/start/end time.
- Duration và throughput.
- Backup ID/type.
- Exit code.
- File/object size.
- Manifest/checksum verification.
- WAL range/timeline.
- Offsite replication status.
- Retention expiry.
- Restore test status và ngày test gần nhất.

### 7.9. Dashboard theo từng cluster

Cluster-level dashboard nên hiển thị:
- Latest verified base backup age.
- Latest successful archive age khi WAL phát sinh.
- WAL generation rate.
- Archive failures trong 1h/24h.
- Disk usage của pg_wal và archive destination.
- Oldest inactive replication slot/restart LSN.
- Latest successful restore drill.
- Measured RPO/RTO so với objectives.

### 7.10. Thiết kế alert có ngữ cảnh

Không đặt alert duy nhất là failed_count > 0 mãi mãi, vì counters có thể reset và một lỗi cũ có thể không còn active. Alert tốt cần:
- Window/time context.
- Cluster/backup ID.
- Severity.
- Owner/on-call.
- Link tới runbook.
- Last success và last failure.
- Mức ảnh hưởng tới RPO/RTO.
- Điều kiện clear/recovery.

### 7.11. Ví dụ alert policy

| Alert | Điều kiện mẫu | Severity |
|---|---|---|
| Backup missed | Không có verified backup trong SLA window | Critical |
| Backup failed | Job exit nonzero hoặc artifact incomplete | High/Critical theo RPO |
| Archive stalled | Có WAL generation nhưng archive freshness vượt ngưỡng | Critical |
| Archive failures | Failure counter tăng trong window | High |
| WAL disk pressure | pg_wal filesystem vượt warning/critical capacity | High/Critical |
| Slot retention | Slot giữ WAL vượt budget và consumer inactive | High |
| Offsite copy lag | Backup verified local nhưng chưa có offsite copy trong SLA | High |
| Restore test stale | Không có restore test trong lịch quy định | Medium/High |
| Restore test failed | Restore/validation thất bại | Critical |
| RTO regression | Thời gian restore vượt objective | High |

Các ngưỡng phải lấy từ RPO/RTO, tốc độ WAL và disk headroom thực tế. Không dùng cùng một số phút cho mọi cluster.

### 7.12. Alert không được tạo false confidence

- Archive success mới không chứng minh segment chain trước đó liên tục.
- Backup file tồn tại không chứng minh file giải mã/đọc được.
- pg_verifybackup pass không chứng minh ứng dụng hoạt động sau restore.
- Replica lag bằng 0 không chứng minh có backup độc lập.
- Restore test pass tháng trước không chứng minh backup mới nhất pass.
- Monitoring xanh không chứng minh alert route tới người trực vẫn hoạt động.

---

## 8. Xác minh backup: từ artifact tới restore

### 8.1. Các tầng kiểm chứng

Có thể chia kiểm chứng thành sáu tầng:

1. **Execution:** job chạy xong, exit code hợp lệ, không bị timeout.
2. **Completeness:** mọi file/tablespace/object/manifest cần thiết đã được tạo và upload.
3. **Integrity:** checksum, size, manifest và format hợp lệ.
4. **Recoverability:** có base backup phù hợp và WAL chain cần thiết.
5. **Database validation:** PostgreSQL khởi động, recovery tới target và catalog/data truy cập được.
6. **Application validation:** ứng dụng đọc/ghi được, dữ liệu nghiệp vụ đúng và service đạt tiêu chí.

Một backup chỉ đạt tầng 1–3 chưa phải bằng chứng restore hoàn chỉnh.

### 8.2. pg_verifybackup

Với physical base backups được tạo theo phương pháp hỗ trợ manifest, pg_verifybackup có thể kiểm tra manifest và checksum của các files trong backup theo khả năng phiên bản.

Ví dụ:

~~~bash
pg_verifybackup /backups/base/backup_2026_11_14
~~~

Dùng binary tương thích với backup/server version. Đọc pg_verifybackup --help và tài liệu phiên bản đang vận hành để hiểu cách kiểm tra WAL, tablespaces và tùy chọn bỏ qua file. Một lần verify thành công không thay thế restore test thực tế.

### 8.3. Manifest và checksum

Manifest giúp xác định artifacts dự kiến, kích thước và checksum. Khi backup được copy qua object storage/offsite:
- Verify trước khi upload.
- Verify sau khi upload hoặc dùng storage checksum semantics phù hợp.
- Ghi object version/etag/checksum theo đúng loại storage.
- Không coi ETag luôn là MD5; multipart uploads và provider semantics có thể khác.
- Kiểm tra manifest có gắn với đúng backup ID và system identifier.

### 8.4. Kiểm tra WAL chain

Cần xác định:
- Backup bắt đầu/kết thúc tại đâu.
- WAL segment cần cho recovery bắt đầu từ đâu.
- WAL archive có liên tục tới recovery target không.
- Timeline history có đủ không.
- Các segments có đọc/giải mã được không.
- Archive retention có xóa mất một segment còn cần không.

Không chỉ kiểm tra “có file WAL mới nhất”; cần chứng minh cả dải liên tục cần cho base backup/target.

### 8.5. Logical backup validation

Với custom-format dump:
- Kiểm tra file có tồn tại và size hợp lý.
- Dùng pg_restore --list để đọc TOC.
- Test restore vào database riêng.
- Kiểm tra schema, extensions, owners/privileges và dữ liệu quan trọng.
- Chạy application queries/smoke tests sau restore.

pg_restore --list chỉ chứng minh có thể đọc TOC ở mức cơ bản; không thay restore đầy đủ.

### 8.6. Restore test có cách ly

Restore backup vào host/VM/network riêng:
- Không trùng port/service discovery với production.
- Không cho ứng dụng thật gửi email, thanh toán hoặc gọi external APIs.
- Dùng credentials test.
- Giới hạn egress/network.
- Bảo vệ dữ liệu nhạy cảm đã restore.
- Ghi rõ thời điểm và nơi lưu bản test.
- Xóa môi trường sau test theo quy trình đã được duyệt.

### 8.7. Kiểm tra sau khi PostgreSQL khởi động

Tối thiểu kiểm tra:
- Server start/recovery hoàn tất.
- pg_is_in_recovery() phản ánh trạng thái mong muốn.
- Database và schema mong đợi có mặt.
- Extensions/languages/tablespaces cần thiết sẵn sàng.
- Critical tables/rows có thể đọc.
- Constraints/indexes ở trạng thái hợp lệ theo nhu cầu.
- Application role có quyền kết nối và truy vấn.
- Logs không có recovery errors hoặc missing WAL warnings.

### 8.8. Kiểm tra nghiệp vụ

Một database mở được chưa chắc dữ liệu đúng. Chọn các invariants nghiệp vụ:
- Tổng số đơn hàng trong khoảng đã biết.
- Tổng tiền theo ngày/tenant.
- Số lượng tài khoản active.
- Foreign key orphan checks.
- Một vài transaction IDs/records gần recovery target.
- Outbox/event sequence.
- Quan hệ giữa các bảng quan trọng.

Dùng query kiểm tra có expected range/expected checksum được lưu trước. Không chỉ kiểm tra SELECT 1.

### 8.9. Kiểm tra logical consistency

Có thể dùng các constraints/queries của ứng dụng và công cụ chuyên dụng như amcheck cho một số cấu trúc B-tree khi phù hợp. Không phải mọi integrity check đều chạy nhanh hoặc không tác động tài nguyên; lập kế hoạch trên môi trường restore riêng.

### 8.10. Lưu bằng chứng

Mỗi test nên lưu:
- Backup ID/source.
- Restore target/time.
- PostgreSQL version/tool version.
- WAL timeline và recovery target.
- Logs/exit codes.
- Integrity check result.
- Application validation result.
- RTO/RPO measured.
- Findings và remediation owner.
- Người thực hiện/reviewer.

---

## 9. Retention, offsite và bảo vệ trước sự cố diện rộng

### 9.1. Retention policy

Retention xác định backup và WAL cần giữ trong bao lâu. Policy nên cân nhắc:
- RPO/RTO.
- Tần suất full/incremental backups nếu tool hỗ trợ.
- WAL archive volume.
- Legal/regulatory requirements.
- Chi phí storage.
- Thời gian phát hiện sự cố muộn (ví dụ corruption được phát hiện sau nhiều ngày).
- Khả năng restore từ backup cũ và WAL liên quan.

### 9.2. Giữ WAL đủ cho mọi base backup còn hiệu lực

Nếu còn một base backup được phép restore tới target, phải giữ WAL chain cần thiết cho target đó. Xóa WAL theo tuổi đơn thuần có thể làm base backup còn tồn tại nhưng không còn phục hồi được tới khoảng thời gian cần thiết.

Backup manager/catalog phải biết dependency giữa backup và WAL segments. Retention nên xóa theo backup set/dependency, không chỉ theo filename age.

### 9.3. Offsite copy

Bản backup trên cùng host/storage account/region với primary có thể bị mất cùng sự cố. Cần copy tới failure domain độc lập theo yêu cầu:
- Region khác.
- Account/project khác.
- Credential khác.
- Storage policy độc lập.
- Immutable/WORM hoặc offline copy khi phù hợp.

Offsite copy phải được kiểm tra truy cập và restore, không chỉ nhìn trạng thái replication xanh.

### 9.4. Immutability

Immutable storage/object lock giúp chống xóa/sửa backup trong một khoảng thời gian. Thiết kế phải cân bằng:
- Retention lock duration.
- Legal hold.
- Recovery account và break-glass access.
- Khả năng xử lý dữ liệu cần xóa theo policy.
- Chi phí và quota.
- Phân quyền quản trị lock khác với quyền vận hành database.

### 9.5. Tách credentials

Backup writer không nhất thiết có quyền xóa archive history. Restore operator cần quyền đọc/decrypt nhưng không nhất thiết có quyền sửa retention. Storage administrator và PostgreSQL DBA nên có separation of duties phù hợp.

### 9.6. Backup catalog cũng cần backup

Nếu catalog mất, việc tìm đúng backup/WAL chain có thể rất khó dù objects vẫn còn. Export/backup catalog, encryption metadata và restore instructions độc lập; thử khôi phục catalog như một phần DR exercise.

### 9.7. Retention deletion test

Trước khi chạy lifecycle deletion:
1. Xác định backup sets hết hạn.
2. Xác minh dependency WAL không còn cần.
3. Kiểm tra legal hold/retention locks.
4. Tạo inventory và dry run.
5. Log những object sẽ bị xóa.
6. Thực hiện theo policy.
7. Verify những backup còn trong retention vẫn restore được theo sample.

### 9.8. Ransomware và credential compromise

Một attacker có quyền xóa database có thể tìm cách xóa cả backup. Giảm blast radius bằng:
- Credentials riêng và least privilege.
- Immutable/offline copies.
- MFA/break-glass.
- Audit logs độc lập.
- Storage account/project khác.
- Khóa mã hóa không nằm chung với backup.
- Clean-room restore từ nguồn đã xác minh.

---

## 10. Thiết kế chương trình diễn tập phục hồi

### 10.1. Mục tiêu của drill

Một recovery drill cần trả lời được:
- Có tìm được backup đúng không?
- Có lấy được key/credentials không?
- Có provision được hạ tầng không?
- Có restore base backup không?
- Có replay WAL tới target không?
- Có xác minh được database và application không?
- Có đạt RPO/RTO không?
- Ai có quyền quyết định promote/cutover?
- Những dependency nào còn thiếu?

### 10.2. Các loại diễn tập

| Loại drill | Phạm vi | Tần suất gợi ý |
|---|---|---|
| Artifact verification | Manifest/checksum/file inventory | Mỗi backup hoặc theo sample tự động |
| Restore smoke test | Restore một backup vào isolated host | Hàng tuần/tháng tùy criticality |
| Full restore drill | Dựng cluster và chạy app validation | Hàng tháng/quý |
| PITR drill | Restore tới timestamp/LSN trước sự cố giả lập | Hàng quý |
| Object-level recovery | Khôi phục table/database/object | Theo nhu cầu và criticality |
| Region/site recovery | Dựng dịch vụ từ offsite backup | Hàng năm hoặc theo SLA |
| Tabletop exercise | Walk through roles/decisions/comms | Hàng quý |
| Backup pipeline failure drill | Giả lập archive/storage/credential failures trong môi trường test | Sau thay đổi lớn và định kỳ |

Tần suất cần căn cứ business risk, tốc độ thay đổi và compliance; đây là gợi ý, không phải tiêu chuẩn áp dụng cho mọi tổ chức.

### 10.3. Tabletop exercise

Tabletop là buổi mô phỏng bằng kịch bản, không nhất thiết restore dữ liệu thật. Nhóm đi qua:
- Ai tuyên bố incident?
- Ai quyết định target recovery?
- Ai sở hữu backup/storage/key?
- Làm sao truy cập runbook khi identity provider chính lỗi?
- Ai phê duyệt promotion/cutover?
- Cách thông báo downtime/data loss?
- Nếu WAL thiếu thì quyết định gì?
- Ai xác nhận business data sau restore?

Tabletop tìm lỗ hổng phối hợp, quyền hạn và tài liệu; nó không chứng minh kỹ thuật restore hoạt động.

### 10.4. Full restore drill

Một full drill nên:
1. Chọn backup ID và recovery target trước buổi test.
2. Lấy artifacts từ nơi lưu trữ thực sự sẽ dùng khi disaster.
3. Dựng host/network độc lập.
4. Restore base backup.
5. Cấu hình WAL archive/recovery target.
6. Chờ recovery hoàn tất.
7. Chạy database checks và app smoke tests.
8. Đo RTO/RPO.
9. Ghi findings.
10. Dọn môi trường và artifacts test theo policy.

### 10.5. PITR drill

Tạo một sự cố giả lập có timestamp/LSN đã biết:
- Ghi một marker transaction trước thời điểm lỗi.
- Ghi marker hoặc thao tác phá hoại sau thời điểm cần phục hồi.
- Restore base backup và WAL tới target trước thao tác phá hoại.
- Xác minh marker trước target tồn tại và thay đổi sau target không xuất hiện.
- Kiểm tra transaction boundaries và timezone/target semantics.

Không dùng thao tác phá hoại trên production. Dùng dataset test hoặc bản sao cô lập.

### 10.6. Restore test mới nhất

Một test thành công cách đây sáu tháng không chứng minh backup mới nhất restore được. Nên có:
- Test nhỏ tự động sau backup hoặc theo sample.
- Full restore định kỳ.
- PITR test định kỳ.
- Test sau thay đổi PostgreSQL major version, backup tool, encryption, storage hoặc archive pipeline.

### 10.7. Diễn tập thay đổi có kiểm soát

Drill không nhất thiết giả lập outage production. Có thể tạo failure ở test environment:
- Credential hết hạn.
- Archive destination read-only.
- Object storage unavailable.
- WAL segment missing trong bản sao test.
- Disk quota thấp.
- Backup manifest bị hỏng có chủ đích.
- Restore target sai timezone.
- KMS/key service không truy cập được.

Chỉ tạo failure trên môi trường kiểm thử có giới hạn và có cleanup plan.

### 10.8. Tiêu chí pass/fail

Pass không chỉ là PostgreSQL start. Xác định trước:
- Restore hoàn tất dưới RTO.
- Recovery point đáp ứng RPO.
- WAL chain liên tục và recovery target được đạt.
- Critical schemas/tables tồn tại.
- Business invariants đạt expected values.
- Application smoke tests pass.
- Access/secret/key process hoạt động.
- Evidence được lưu.
- Không có side effects sang production/external services.

Nếu một tiêu chí chưa đạt, ghi rõ partial success và gap; không đánh dấu toàn drill pass.

---

## 7. Metrics, dashboard và cảnh báo

### 7.1. Nhóm metrics cần có

Một dashboard backup/recovery nên chia thành các nhóm để người trực vận hành hiểu failure đang ở đâu:

| Nhóm | Metrics/fields | Câu hỏi |
|---|---|---|
| Scheduler | last start, last success, next run, duration, exit code | Job có chạy đúng lịch không? |
| Backup artifacts | backup ID, size, manifest, checksum, catalog state | Có tạo đủ và xác minh được backup không? |
| WAL archiving | last archived time/file, success/failure deltas, backlog | WAL có được lưu liên tục không? |
| WAL generation | wal_bytes delta, FPI, WAL rate | Workload đang tạo WAL nhanh đến đâu? |
| Replication | sent/write/flush/replay LSN, slot restart LSN | Standby/slot có giữ WAL không? |
| Storage | capacity, free bytes, object errors, quota | Có nguy cơ hết dung lượng không? |
| Restore tests | last successful restore, duration, target, result | Backup có thật sự phục hồi được không? |
| Objectives | measured RPO/RTO, age of latest tested backup | Có đáp ứng mục tiêu business không? |

### 7.2. Theo dõi thời điểm archive gần nhất

~~~sql
SELECT
    now() AS observed_at,
    last_archived_wal,
    last_archived_time,
    EXTRACT(EPOCH FROM (clock_timestamp() - last_archived_time))
        AS seconds_since_last_archive,
    archived_count,
    failed_count,
    stats_reset
FROM pg_stat_archiver;
~~~

Đây là một tín hiệu freshness, không phải verdict độc lập. Nếu database idle lâu và không phát sinh WAL segment mới, last_archived_time cũ có thể bình thường. Chỉ alert stale archive khi có WAL generation/segment activity đáng lẽ cần archive hoặc khi backup policy yêu cầu archive timeout cụ thể.

### 7.3. Theo dõi failure counter

Không chỉ nhìn giá trị hiện tại; thu thập counters định kỳ và tính delta giữa hai samples. Nếu stats_reset thay đổi, bắt đầu một baseline mới. Một alert phù hợp thường dựa trên:
- Số failures tăng trong window.
- Last failure time gần đây.
- Failure lặp lại cùng file.
- Archive freshness vượt ngưỡng khi WAL đang được tạo.
- pg_wal usage tăng đồng thời.

### 7.4. Tính WAL generation rate

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    wal_bytes,
    wal_records,
    wal_fpi,
    stats_reset
FROM pg_stat_wal;
~~~

Lấy hai samples cách nhau một khoảng đã biết. Nếu wal_bytes tăng 600 MiB trong 10 phút thì WAL generation trung bình xấp xỉ 60 MiB/phút trong window. Kiểm tra stats_reset không đổi và hiểu đây là counter toàn cluster.

### 7.5. Theo dõi slot giữ WAL

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
      WHEN restart_lsn IS NULL THEN NULL
      ELSE pg_size_pretty(
          pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
      )
    END AS retained_wal_distance,
    wal_status
FROM pg_replication_slots
ORDER BY restart_lsn NULLS FIRST;
~~~

Khoảng cách LSN là estimate về WAL stream còn phía trước restart LSN, không phải chính xác dung lượng local disk bị slot giữ trong mọi tình huống. Một slot inactive có thể giữ WAL rất lâu. Trước khi can thiệp phải xác định owner, consumer và khả năng reinitialize.

### 7.6. Theo dõi base backup đang chạy

~~~sql
SELECT
    pid,
    phase,
    backup_total,
    backup_streamed,
    tablespaces_total,
    tablespaces_streamed
FROM pg_stat_progress_basebackup;
~~~

Dùng view để nhận biết backup đang tiến triển hay đứng lâu ở một phase. Kết hợp process logs, network throughput và storage metrics để xác định bottleneck. Backup progress không thay thế kiểm tra exit code và manifest.

### 7.7. Theo dõi WAL directory

Trên các versions hỗ trợ và role có quyền phù hợp, pg_ls_waldir() có thể liệt kê WAL files:

~~~sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size,
    max(modification) AS newest_file_time
FROM pg_ls_waldir();
~~~

Cách này chỉ quan sát thư mục WAL hiện tại. Để hiểu dung lượng thực tế, nên dùng filesystem metrics vì directory listing không thay thế kiểm tra mount capacity, inode usage, reserved space hoặc các file liên quan khác. Không xóa entries từ kết quả này.

### 7.8. Dashboard theo từng backup

Mỗi backup run nên có một dòng timeline hiển thị:
- Scheduled/start/end time.
- Duration và throughput.
- Backup ID/type.
- Exit code.
- File/object size.
- Manifest/checksum verification.
- WAL range/timeline.
- Offsite replication status.
- Retention expiry.
- Restore test status và ngày test gần nhất.

### 7.9. Dashboard theo từng cluster

Cluster-level dashboard nên hiển thị:
- Latest verified base backup age.
- Latest successful archive age khi WAL phát sinh.
- WAL generation rate.
- Archive failures trong 1h/24h.
- Disk usage của pg_wal và archive destination.
- Oldest inactive replication slot/restart LSN.
- Latest successful restore drill.
- Measured RPO/RTO so với objectives.

### 7.10. Thiết kế alert có ngữ cảnh

Không đặt alert duy nhất là failed_count > 0 mãi mãi, vì counters có thể reset và một lỗi cũ có thể không còn active. Alert tốt cần:
- Window/time context.
- Cluster/backup ID.
- Severity.
- Owner/on-call.
- Link tới runbook.
- Last success và last failure.
- Mức ảnh hưởng tới RPO/RTO.
- Điều kiện clear/recovery.

### 7.11. Ví dụ alert policy

| Alert | Điều kiện mẫu | Severity |
|---|---|---|
| Backup missed | Không có verified backup trong SLA window | Critical |
| Backup failed | Job exit nonzero hoặc artifact incomplete | High/Critical theo RPO |
| Archive stalled | Có WAL generation nhưng archive freshness vượt ngưỡng | Critical |
| Archive failures | Failure counter tăng trong window | High |
| WAL disk pressure | pg_wal filesystem vượt warning/critical capacity | High/Critical |
| Slot retention | Slot giữ WAL vượt budget và consumer inactive | High |
| Offsite copy lag | Backup verified local nhưng chưa có offsite copy trong SLA | High |
| Restore test stale | Không có restore test trong lịch quy định | Medium/High |
| Restore test failed | Restore/validation thất bại | Critical |
| RTO regression | Thời gian restore vượt objective | High |

Các ngưỡng phải lấy từ RPO/RTO, tốc độ WAL và disk headroom thực tế. Không dùng cùng một số phút cho mọi cluster.

### 7.12. Alert không được tạo false confidence

- Archive success mới không chứng minh segment chain trước đó liên tục.
- Backup file tồn tại không chứng minh file giải mã/đọc được.
- pg_verifybackup pass không chứng minh ứng dụng hoạt động sau restore.
- Replica lag bằng 0 không chứng minh có backup độc lập.
- Restore test pass tháng trước không chứng minh backup mới nhất pass.
- Monitoring xanh không chứng minh alert route tới người trực vẫn hoạt động.

---

## 8. Xác minh backup: từ artifact tới restore

### 8.1. Các tầng kiểm chứng

Có thể chia kiểm chứng thành sáu tầng:

1. **Execution:** job chạy xong, exit code hợp lệ, không bị timeout.
2. **Completeness:** mọi file/tablespace/object/manifest cần thiết đã được tạo và upload.
3. **Integrity:** checksum, size, manifest và format hợp lệ.
4. **Recoverability:** có base backup phù hợp và WAL chain cần thiết.
5. **Database validation:** PostgreSQL khởi động, recovery tới target và catalog/data truy cập được.
6. **Application validation:** ứng dụng đọc/ghi được, dữ liệu nghiệp vụ đúng và service đạt tiêu chí.

Một backup chỉ đạt tầng 1–3 chưa phải bằng chứng restore hoàn chỉnh.

### 8.2. pg_verifybackup

Với physical base backups được tạo theo phương pháp hỗ trợ manifest, pg_verifybackup có thể kiểm tra manifest và checksum của các files trong backup theo khả năng phiên bản.

Ví dụ:

~~~bash
pg_verifybackup /backups/base/backup_2026_11_14
~~~

Dùng binary tương thích với backup/server version. Đọc pg_verifybackup --help và tài liệu phiên bản đang vận hành để hiểu cách kiểm tra WAL, tablespaces và tùy chọn bỏ qua file. Một lần verify thành công không thay thế restore test thực tế.

### 8.3. Manifest và checksum

Manifest giúp xác định artifacts dự kiến, kích thước và checksum. Khi backup được copy qua object storage/offsite:
- Verify trước khi upload.
- Verify sau khi upload hoặc dùng storage checksum semantics phù hợp.
- Ghi object version/etag/checksum theo đúng loại storage.
- Không coi ETag luôn là MD5; multipart uploads và provider semantics có thể khác.
- Kiểm tra manifest có gắn với đúng backup ID và system identifier.

### 8.4. Kiểm tra WAL chain

Cần xác định:
- Backup bắt đầu/kết thúc tại đâu.
- WAL segment cần cho recovery bắt đầu từ đâu.
- WAL archive có liên tục tới recovery target không.
- Timeline history có đủ không.
- Các segments có đọc/giải mã được không.
- Archive retention có xóa mất một segment còn cần không.

Không chỉ kiểm tra “có file WAL mới nhất”; cần chứng minh cả dải liên tục cần cho base backup/target.

### 8.5. Logical backup validation

Với custom-format dump:
- Kiểm tra file có tồn tại và size hợp lý.
- Dùng pg_restore --list để đọc TOC.
- Test restore vào database riêng.
- Kiểm tra schema, extensions, owners/privileges và dữ liệu quan trọng.
- Chạy application queries/smoke tests sau restore.

pg_restore --list chỉ chứng minh có thể đọc TOC ở mức cơ bản; không thay restore đầy đủ.

### 8.6. Restore test có cách ly

Restore backup vào host/VM/network riêng:
- Không trùng port/service discovery với production.
- Không cho ứng dụng thật gửi email, thanh toán hoặc gọi external APIs.
- Dùng credentials test.
- Giới hạn egress/network.
- Bảo vệ dữ liệu nhạy cảm đã restore.
- Ghi rõ thời điểm và nơi lưu bản test.
- Xóa môi trường sau test theo quy trình đã được duyệt.

### 8.7. Kiểm tra sau khi PostgreSQL khởi động

Tối thiểu kiểm tra:
- Server start/recovery hoàn tất.
- pg_is_in_recovery() phản ánh trạng thái mong muốn.
- Database và schema mong đợi có mặt.
- Extensions/languages/tablespaces cần thiết sẵn sàng.
- Critical tables/rows có thể đọc.
- Constraints/indexes ở trạng thái hợp lệ theo nhu cầu.
- Application role có quyền kết nối và truy vấn.
- Logs không có recovery errors hoặc missing WAL warnings.

### 8.8. Kiểm tra nghiệp vụ

Một database mở được chưa chắc dữ liệu đúng. Chọn các invariants nghiệp vụ:
- Tổng số đơn hàng trong khoảng đã biết.
- Tổng tiền theo ngày/tenant.
- Số lượng tài khoản active.
- Foreign key orphan checks.
- Một vài transaction IDs/records gần recovery target.
- Outbox/event sequence.
- Quan hệ giữa các bảng quan trọng.

Dùng query kiểm tra có expected range/expected checksum được lưu trước. Không chỉ kiểm tra SELECT 1.

### 8.9. Kiểm tra logical consistency

Có thể dùng các constraints/queries của ứng dụng và công cụ chuyên dụng như amcheck cho một số cấu trúc B-tree khi phù hợp. Không phải mọi integrity check đều chạy nhanh hoặc không tác động tài nguyên; lập kế hoạch trên môi trường restore riêng.

### 8.10. Lưu bằng chứng

Mỗi test nên lưu:
- Backup ID/source.
- Restore target/time.
- PostgreSQL version/tool version.
- WAL timeline và recovery target.
- Logs/exit codes.
- Integrity check result.
- Application validation result.
- RTO/RPO measured.
- Findings và remediation owner.
- Người thực hiện/reviewer.

---

## 9. Retention, offsite và bảo vệ trước sự cố diện rộng

### 9.1. Retention policy

Retention xác định backup và WAL cần giữ trong bao lâu. Policy nên cân nhắc:
- RPO/RTO.
- Tần suất full/incremental backups nếu tool hỗ trợ.
- WAL archive volume.
- Legal/regulatory requirements.
- Chi phí storage.
- Thời gian phát hiện sự cố muộn (ví dụ corruption được phát hiện sau nhiều ngày).
- Khả năng restore từ backup cũ và WAL liên quan.

### 9.2. Giữ WAL đủ cho mọi base backup còn hiệu lực

Nếu còn một base backup được phép restore tới target, phải giữ WAL chain cần thiết cho target đó. Xóa WAL theo tuổi đơn thuần có thể làm base backup còn tồn tại nhưng không còn phục hồi được tới khoảng thời gian cần thiết.

Backup manager/catalog phải biết dependency giữa backup và WAL segments. Retention nên xóa theo backup set/dependency, không chỉ theo filename age.

### 9.3. Offsite copy

Bản backup trên cùng host/storage account/region với primary có thể bị mất cùng sự cố. Cần copy tới failure domain độc lập theo yêu cầu:
- Region khác.
- Account/project khác.
- Credential khác.
- Storage policy độc lập.
- Immutable/WORM hoặc offline copy khi phù hợp.

Offsite copy phải được kiểm tra truy cập và restore, không chỉ nhìn trạng thái replication xanh.

### 9.4. Immutability

Immutable storage/object lock giúp chống xóa/sửa backup trong một khoảng thời gian. Thiết kế phải cân bằng:
- Retention lock duration.
- Legal hold.
- Recovery account và break-glass access.
- Khả năng xử lý dữ liệu cần xóa theo policy.
- Chi phí và quota.
- Phân quyền quản trị lock khác với quyền vận hành database.

### 9.5. Tách credentials

Backup writer không nhất thiết có quyền xóa archive history. Restore operator cần quyền đọc/decrypt nhưng không nhất thiết có quyền sửa retention. Storage administrator và PostgreSQL DBA nên có separation of duties phù hợp.

### 9.6. Backup catalog cũng cần backup

Nếu catalog mất, việc tìm đúng backup/WAL chain có thể rất khó dù objects vẫn còn. Export/backup catalog, encryption metadata và restore instructions độc lập; thử khôi phục catalog như một phần DR exercise.

### 9.7. Retention deletion test

Trước khi chạy lifecycle deletion:
1. Xác định backup sets hết hạn.
2. Xác minh dependency WAL không còn cần.
3. Kiểm tra legal hold/retention locks.
4. Tạo inventory và dry run.
5. Log những object sẽ bị xóa.
6. Thực hiện theo policy.
7. Verify những backup còn trong retention vẫn restore được theo sample.

### 9.8. Ransomware và credential compromise

Một attacker có quyền xóa database có thể tìm cách xóa cả backup. Giảm blast radius bằng:
- Credentials riêng và least privilege.
- Immutable/offline copies.
- MFA/break-glass.
- Audit logs độc lập.
- Storage account/project khác.
- Khóa mã hóa không nằm chung với backup.
- Clean-room restore từ nguồn đã xác minh.

---

## 10. Thiết kế chương trình diễn tập phục hồi

### 10.1. Mục tiêu của drill

Một recovery drill cần trả lời được:
- Có tìm được backup đúng không?
- Có lấy được key/credentials không?
- Có provision được hạ tầng không?
- Có restore base backup không?
- Có replay WAL tới target không?
- Có xác minh được database và application không?
- Có đạt RPO/RTO không?
- Ai có quyền quyết định promote/cutover?
- Những dependency nào còn thiếu?

### 10.2. Các loại diễn tập

| Loại drill | Phạm vi | Tần suất gợi ý |
|---|---|---|
| Artifact verification | Manifest/checksum/file inventory | Mỗi backup hoặc theo sample tự động |
| Restore smoke test | Restore một backup vào isolated host | Hàng tuần/tháng tùy criticality |
| Full restore drill | Dựng cluster và chạy app validation | Hàng tháng/quý |
| PITR drill | Restore tới timestamp/LSN trước sự cố giả lập | Hàng quý |
| Object-level recovery | Khôi phục table/database/object | Theo nhu cầu và criticality |
| Region/site recovery | Dựng dịch vụ từ offsite backup | Hàng năm hoặc theo SLA |
| Tabletop exercise | Walk through roles/decisions/comms | Hàng quý |
| Backup pipeline failure drill | Giả lập archive/storage/credential failures trong môi trường test | Sau thay đổi lớn và định kỳ |

Tần suất cần căn cứ business risk, tốc độ thay đổi và compliance; đây là gợi ý, không phải tiêu chuẩn áp dụng cho mọi tổ chức.

### 10.3. Tabletop exercise

Tabletop là buổi mô phỏng bằng kịch bản, không nhất thiết restore dữ liệu thật. Nhóm đi qua:
- Ai tuyên bố incident?
- Ai quyết định target recovery?
- Ai sở hữu backup/storage/key?
- Làm sao truy cập runbook khi identity provider chính lỗi?
- Ai phê duyệt promotion/cutover?
- Cách thông báo downtime/data loss?
- Nếu WAL thiếu thì quyết định gì?
- Ai xác nhận business data sau restore?

Tabletop tìm lỗ hổng phối hợp, quyền hạn và tài liệu; nó không chứng minh kỹ thuật restore hoạt động.

### 10.4. Full restore drill

Một full drill nên:
1. Chọn backup ID và recovery target trước buổi test.
2. Lấy artifacts từ nơi lưu trữ thực sự sẽ dùng khi disaster.
3. Dựng host/network độc lập.
4. Restore base backup.
5. Cấu hình WAL archive/recovery target.
6. Chờ recovery hoàn tất.
7. Chạy database checks và app smoke tests.
8. Đo RTO/RPO.
9. Ghi findings.
10. Dọn môi trường và artifacts test theo policy.

### 10.5. PITR drill

Tạo một sự cố giả lập có timestamp/LSN đã biết:
- Ghi một marker transaction trước thời điểm lỗi.
- Ghi marker hoặc thao tác phá hoại sau thời điểm cần phục hồi.
- Restore base backup và WAL tới target trước thao tác phá hoại.
- Xác minh marker trước target tồn tại và thay đổi sau target không xuất hiện.
- Kiểm tra transaction boundaries và timezone/target semantics.

Không dùng thao tác phá hoại trên production. Dùng dataset test hoặc bản sao cô lập.

### 10.6. Restore test mới nhất

Một test thành công cách đây sáu tháng không chứng minh backup mới nhất restore được. Nên có:
- Test nhỏ tự động sau backup hoặc theo sample.
- Full restore định kỳ.
- PITR test định kỳ.
- Test sau thay đổi PostgreSQL major version, backup tool, encryption, storage hoặc archive pipeline.

### 10.7. Diễn tập thay đổi có kiểm soát

Drill không nhất thiết giả lập outage production. Có thể tạo failure ở test environment:
- Credential hết hạn.
- Archive destination read-only.
- Object storage unavailable.
- WAL segment missing trong bản sao test.
- Disk quota thấp.
- Backup manifest bị hỏng có chủ đích.
- Restore target sai timezone.
- KMS/key service không truy cập được.

Chỉ tạo failure trên môi trường kiểm thử có giới hạn và có cleanup plan.

### 10.8. Tiêu chí pass/fail

Pass không chỉ là PostgreSQL start. Xác định trước:
- Restore hoàn tất dưới RTO.
- Recovery point đáp ứng RPO.
- WAL chain liên tục và recovery target được đạt.
- Critical schemas/tables tồn tại.
- Business invariants đạt expected values.
- Application smoke tests pass.
- Access/secret/key process hoạt động.
- Evidence được lưu.
- Không có side effects sang production/external services.

Nếu một tiêu chí chưa đạt, ghi rõ partial success và gap; không đánh dấu toàn drill pass.

---

## 11. Quy trình phục hồi physical backup và PITR

### 11.1. Chuẩn bị trước khi restore

Trước khi bắt đầu, xác định:
- Backup ID và system identifier đúng cluster.
- PostgreSQL major version tương thích.
- Base backup đầy đủ và đã verify.
- WAL archive location/credentials/key.
- Timeline history files.
- Tablespaces và mount points.
- Extensions/binaries cần thiết.
- Configuration, certificates và secrets.
- Recovery target (time, LSN, XID hoặc named restore point nếu đã tạo).
- Network isolation và service dependencies.

Không chọn backup chỉ vì timestamp gần nhất; phải chọn backup có WAL chain hợp lệ tới target.

### 11.2. Dựng môi trường riêng

Tạo host/VM/storage có đủ capacity và IOPS. Tách:
- Data directory của restore.
- WAL restore/cache location nếu cần.
- Network/security group.
- Port và DNS.
- Application credentials.
- Egress tới external services.

Nếu dùng dữ liệu production có PII, áp dụng policy bảo vệ tương đương hoặc mạnh hơn production.

### 11.3. Khôi phục base backup

Dùng quy trình/tool đã tạo backup để restore files và tablespaces. Giữ nguyên ownership/permissions cần thiết. Với physical backup, không chỉ copy một vài relation files bằng filesystem để tạo một cluster nhất quán.

### 11.4. Cấu hình WAL recovery

Trong PostgreSQL hiện đại, archive recovery dùng recovery configuration và signal file phù hợp (ví dụ §recovery.signal§ ở các phiên bản đã chuyển khỏi recovery.conf). Cấu hình §restore_command§ để lấy segment từ archive; chọn recovery target đúng với yêu cầu.

Ví dụ cấu hình khái niệm:

~~~conf
restore_command = 'fetch_wal %f %p'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
~~~

§fetch_wal§ là placeholder cho archive retrieval command của môi trường, không phải lệnh có sẵn. Cú pháp/timezone/target options phải kiểm tra theo PostgreSQL version. Dùng timestamp có timezone rõ ràng và xác nhận target có thể đạt từ backup/WAL chain.

### 11.5. Chạy recovery và theo dõi logs

Khởi động PostgreSQL trong isolated environment. Theo dõi:
- WAL segment requests và restore command exit status.
- Missing/corrupt WAL errors.
- Timeline switch/history.
- Recovery progress và replay.
- Target reached/pause/promote behavior.
- Filesystem capacity.
- Startup/recovery logs.

Nếu thiếu WAL, dừng việc tuyên bố restore thành công; xác định segment bị thiếu và target tối đa có thể đạt.

### 11.6. Xác nhận recovery target

Khi recovery đạt target:
- Xác nhận log thông báo target reached theo semantics version.
- Xác định server đang paused/in recovery hay đã promoted.
- Kiểm tra §pg_is_in_recovery()§.
- Kiểm tra transaction markers trước/sau target.
- Ghi lại LSN/timestamp/timeline cuối cùng.

Không chỉ dựa vào việc PostgreSQL accept connection.

### 11.7. Promote và cutover

Trong drill, thường không cần mở traffic thật. Nếu kịch bản yêu cầu promote:
- Chỉ promote sau khi recovery target và validation được xác nhận.
- Cập nhật routing trong môi trường test.
- Kiểm tra ứng dụng với credentials riêng.
- Ghi nhận timeline mới.
- Không cho primary cũ và node phục hồi cùng nhận writes ngoài kế hoạch fencing rõ ràng.

Trong production disaster recovery, fencing old primary và tránh split brain là bước bắt buộc trước khi cutover.

### 11.8. Sau recovery

Chạy database/business validations, đo RTO/RPO, lưu evidence và cleanup. Nếu drill đã promote test instance, ghi rõ timeline/instance để tránh nhầm nó với cluster production hoặc một replica thật.

---

## 12. Runbook khi backup job thất bại

### 12.1. Tiếp nhận cảnh báo

Ghi nhận:
- Cluster/environment.
- Backup ID/job run ID.
- Loại backup.
- Thời điểm start/last success/failure.
- Exit code và error category.
- RPO/RTO còn lại.
- Disk/storage headroom.
- WAL archive status.
- Owner và incident severity.

Xác định job có thật sự chạy hay scheduler chưa kích hoạt.

### 12.2. Kiểm tra scheduler và process

1. Kiểm tra lịch và scheduler service.
2. Xác nhận job run ID, process start/end.
3. Đọc stdout/stderr/log.
4. Kiểm tra timeout, kill signal, host restart.
5. Kiểm tra overlap/concurrency.
6. Xác định failure transient hay permanent.

Không xóa trạng thái job hoặc log để làm dashboard xanh.

### 12.3. Kiểm tra PostgreSQL

Xem:
- Server availability và connection errors.
- §pg_stat_progress_basebackup§ nếu base backup còn chạy.
- PostgreSQL logs.
- §pg_stat_archiver§ và §pg_stat_wal§.
- Replication slots/standby nếu WAL retention tăng.
- Locks/resource pressure nếu job bị chờ.

### 12.4. Kiểm tra storage/network/credentials

Xác nhận quota, free space, permissions, object lock, KMS/key access, DNS, TLS, network route và remote service health. Nếu credentials hết hạn, sửa bằng secret management; không đưa password vào shell history hoặc incident chat.

### 12.5. Quyết định retry

Retry khi:
- Lỗi transient đã được xử lý.
- Backup tool hỗ trợ resume/retry an toàn.
- Backup catalog không ghi một backup incomplete như complete.
- Storage đủ capacity.
- Retry không gây overlap hoặc I/O overload.

Nếu backup partial, dùng quy trình tool để đánh dấu/loại artifact partial. Không tự ghép các phần backup khác nhau thành một backup set.

### 12.6. Bảo vệ RPO

Nếu base backup thất bại nhưng WAL archive còn healthy, đánh giá xem có base backup cũ đủ mới để phục hồi trong RPO không. Nếu archive cũng lỗi, mức rủi ro tăng nhanh; escalates theo incident policy, bảo vệ disk và khôi phục archive pipeline trước khi WAL bị mất.

---

## 13. Runbook khi WAL archive thất bại hoặc backlog tăng

### 13.1. Xác định phạm vi

Lấy:
- §pg_stat_archiver§ counters/timestamps.
- PostgreSQL logs của archive command.
- Current WAL insert/write/flush LSN.
- §pg_stat_wal§ deltas.
- §pg_wal§ filesystem usage.
- Archive destination health.
- Replication slots và standby progress.

### 13.2. Phân biệt generation pressure và retention pressure

**Generation pressure:** workload tạo WAL nhanh hơn khả năng archive/write/storage xử lý.

**Retention pressure:** archive có thể đã chạy nhưng WAL không được recycle vì slot/standby/archive/checkpoint còn cần; hoặc archive failures làm segment giữ lại.

Hai trường hợp có thể cùng xảy ra. Không tăng storage quota một cách mù quáng nếu nguyên nhân là slot inactive giữ WAL vô thời hạn.

### 13.3. Archive command lỗi

Kiểm tra:
- Exit code và stdout/stderr.
- Permission/ownership.
- Destination path.
- Quota/disk.
- Network/DNS/TLS.
- KMS/key access.
- File naming/collision behavior.
- Retry/idempotency của archive command.

Archive command phải xử lý retry an toàn theo tài liệu PostgreSQL/tool; không overwrite segment khác hoặc báo success trước khi object bền ở destination.

### 13.4. WAL disk pressure

Khi pg_wal filesystem gần đầy:
1. Alert DBA/on-call và storage owner.
2. Đánh giá WAL generation rate và growth rate.
3. Khôi phục archive destination nếu lỗi.
4. Xác định slot/standby nào giữ WAL và owner.
5. Kiểm tra retention policy và disk headroom.
6. Throttle write-heavy jobs nếu cần và được phép.
7. Không xóa WAL segment thủ công.
8. Không drop slot chưa xác định consumer.
9. Sau remediation, theo dõi archive catch-up và WAL recycling.

### 13.5. Replication slot bị bỏ quên

Một inactive slot có thể giữ WAL để consumer đọc lại. Trước khi drop:
- Xác định slot type và application owner.
- Kiểm tra consumer có thể reconnect không.
- Xác định hậu quả nếu slot bị drop (logical consumer có thể phải reinitialize; standby có thể cần rebuild).
- Có phê duyệt theo incident procedure.
- Lưu evidence và update inventory.

### 13.6. Missing WAL segment

Nếu recovery báo thiếu WAL:
- Xác định chính xác filename/LSN/timeline.
- Kiểm tra local archive cache, offsite copy và storage version history.
- Kiểm tra archive logs/backup catalog.
- Xác định backup nào cần segment đó.
- Tìm timeline history/alternate archive location.
- Xác định recovery target tối đa có thể đạt nếu không khôi phục được segment.

Không tạo file rỗng hoặc đổi tên segment khác để vượt qua lỗi; điều đó không tái tạo dữ liệu WAL.

---

## 14. Runbook khi restore thất bại

### 14.1. Không tiếp tục thử ngẫu nhiên trên cùng data directory

Restore/recovery có thể thay đổi data directory và recovery state. Khi failure:
- Lưu logs, backup ID, target và tool versions.
- Snapshot/copy failure evidence nếu cần.
- Xác định có thể retry an toàn hay phải tạo data directory mới.
- Không chỉnh sửa WAL/base backup gốc.
- Dùng bản copy test mới khi thử phương án khác.

### 14.2. Nhóm lỗi thường gặp

| Triệu chứng | Hướng điều tra |
|---|---|
| Base backup không khởi động | Version, manifest, file permissions, tablespaces, configuration |
| WAL segment not found | Archive continuity, timeline, retention, filename mapping |
| WAL checksum/corruption | Storage integrity, transfer, source archive, correct segment |
| Recovery target không đạt | Target timezone/LSN, WAL range, target semantics |
| Extension/library missing | Cài đúng version extension và shared libraries |
| Permission denied | Ownership, OS account, storage/KMS access |
| Disk full | Data restore capacity, WAL replay growth, temp space |
| Server starts nhưng app lỗi | Roles, secrets, extensions, schema, business data, external dependencies |
| Restore chậm hơn RTO | Storage throughput, WAL volume, parallelism/tool configuration, validation bottleneck |

### 14.3. Thiếu extension

Physical restore mang data files/catalogs nhưng host mới vẫn cần binaries/shared libraries của extensions tương thích. Lập inventory extension versions trước disaster và lưu package/source phù hợp. Không giả định extension có sẵn trên image mới.

### 14.4. Tablespaces

Tablespaces có thể nằm ngoài data directory. Restore target phải map tablespace paths đúng và có đủ capacity/permissions. Một base backup thiếu tablespace artifacts sẽ không được cứu bằng việc chỉ restore PGDATA.

### 14.5. Configuration drift

PostgreSQL config, postgresql.auto.conf, pg_hba.conf, certificates, service manager, environment variables và secrets có thể không nằm trọn trong base backup. Lưu cấu hình cần thiết riêng, có versioning và kiểm tra trong drill.

### 14.6. Recovery target sai

Timestamp có timezone không rõ, target LSN nằm trước backup start hoặc sau WAL cuối cùng có thể khiến recovery dừng sai điểm hoặc không đạt. Ghi rõ timezone/LSN, tạo marker transaction và test target semantics trước production use.

---

## 15. Thiết kế lịch diễn tập và phân vai

### 15.1. Vai trò

Một drill nên chỉ rõ:

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander | Điều phối, quyết định tiến trình và escalation |
| DBA/recovery operator | Chọn backup, restore, WAL replay, database validation |
| Infrastructure operator | Provision host/network/storage |
| Security/key custodian | Cấp recovery credentials/key theo break-glass policy |
| Application owner | Smoke tests và business validation |
| Business approver | Xác nhận dữ liệu và service recovery criteria |
| Observer/scribe | Ghi timeline, decisions, evidence và findings |

Một người có thể giữ nhiều vai trò ở đội nhỏ, nhưng quyền quyết định cutover và việc ghi nhận bằng chứng phải rõ.

### 15.2. Lịch theo mức độ quan trọng

| Tier | Backup verification | Restore test | PITR/site drill |
|---|---|---|---|
| Tier 0 / critical | Mỗi backup, automated | Hàng tuần/tháng | Hàng quý hoặc theo SLA |
| Tier 1 / high | Mỗi backup hoặc sample chặt | Hàng tháng | Hàng quý/nửa năm |
| Tier 2 / standard | Theo sample | Hàng quý | Hàng năm |
| Tier 3 / low | Theo policy | Định kỳ theo risk | Theo thay đổi/nhu cầu |

Đây là mẫu lập lịch; điều chỉnh theo RPO/RTO, compliance, data sensitivity và năng lực vận hành.

### 15.3. Drill sau thay đổi lớn

Bắt buộc cân nhắc drill sau:
- PostgreSQL major version upgrade.
- Backup tool/agent upgrade.
- Thay đổi archive command/storage provider.
- Thay encryption/KMS keys.
- Thay tablespace/layout hoặc storage.
- Thay network/identity policy.
- Thay retention/lifecycle rules.
- Di chuyển region/cloud account.

### 15.4. Lập kế hoạch trước buổi diễn tập

Tài liệu chuẩn bị cần:
- Objective và scenario.
- Scope, cluster, backup ID.
- Recovery target.
- Pass/fail criteria.
- RTO/RPO.
- Participants/roles.
- Test environment/network isolation.
- Access/keys.
- Expected artifacts.
- Rollback/cleanup plan.
- Business validation owner.

### 15.5. Kiểm soát blast radius

- Không trỏ ứng dụng production vào restored database.
- Chặn outbound email/payment/webhook/jobs.
- Không dùng DNS production.
- Không để restore instance tự động đăng ký service discovery.
- Không promote/cutover production khi chưa có incident authorization.
- Không dùng credentials có quyền ghi production.
- Xóa dữ liệu test theo policy sau khi lưu evidence.

### 15.6. Kết thúc drill

Sau test:
1. Dừng workloads/restore instance theo cleanup plan.
2. Thu thập logs/metrics/evidence.
3. Xác nhận không có writes hoặc outbound calls ngoài ý muốn.
4. Xóa temporary secrets/credentials.
5. Cập nhật backup catalog/drill history.
6. Mở action items có owner/due date.
7. Chia sẻ kết quả cho các stakeholder cần biết.

---

## 16. Kịch bản diễn tập mẫu

### 16.1. Kịch bản A — Backup job không chạy

**Inject:** Scheduler không kích hoạt backup trong một window.

**Mục tiêu:** Phát hiện missed backup, xác định RPO exposure và phục hồi lịch.

**Quan sát:**
- Alert scheduler/job age.
- Last verified backup.
- Owner/on-call route.
- Retry/backfill behavior.
- Catalog có ghi nhận missing run không?

**Pass criteria:** Alert tới đúng owner trong SLA; xác định backup gần nhất còn phục hồi được; job được khôi phục và backup mới được verify.

### 16.2. Kịch bản B — Archive destination unavailable

**Inject:** Archive storage từ chối ghi hoặc timeout.

**Mục tiêu:** Phát hiện archive failures, bảo vệ pg_wal disk headroom và khôi phục pipeline.

**Quan sát:**
- pg_stat_archiver.
- PostgreSQL logs.
- pg_wal capacity/growth.
- WAL generation rate.
- Alert/escalation.
- Archive catch-up sau khi destination phục hồi.

**Pass criteria:** Không xóa WAL thủ công; xác định generation/retention pressure; khôi phục archive; xác nhận segment backlog giảm và recovery chain liên tục.

### 16.3. Kịch bản C — Xóa nhầm dữ liệu

**Inject:** Trong test dataset, thực hiện DELETE/UPDATE sai sau một marker transaction.

**Mục tiêu:** PITR tới thời điểm trước thao tác lỗi.

**Quan sát:**
- Chọn base backup/WAL chain.
- Recovery target timezone.
- Target reached.
- Marker trước target còn, thay đổi sau target không còn.
- App validation và RTO.

**Pass criteria:** Phục hồi đúng point-in-time, không đưa restored test instance vào production, bằng chứng RPO/RTO được lưu.

### 16.4. Kịch bản D — Mất region

**Inject:** Giả định primary region không truy cập được.

**Mục tiêu:** Dựng cluster ở region khác từ offsite backup/WAL.

**Quan sát:**
- Access break-glass.
- KMS/key retrieval.
- Offsite data/WAL availability.
- Infrastructure provisioning.
- DNS/routing/fencing.
- Business sign-off.

**Pass criteria:** Restore ở failure domain độc lập và đáp ứng mục tiêu; không split brain; catalog/runbook có thể truy cập ngoài primary region.

### 16.5. Kịch bản E — Backup có checksum failure

**Inject:** Một bản copy test bị thay đổi một file có kiểm soát.

**Mục tiêu:** Chứng minh integrity verification phát hiện corruption và chọn được bản backup khác.

**Quan sát:**
- Manifest/checksum result.
- Alert.
- Backup catalog state.
- Quarantine bad artifact.
- Restore từ bản verified khác.

**Pass criteria:** Bản hỏng không được đánh dấu verified; có thể chọn bản khác; incident được ghi lại.

### 16.6. Kịch bản F — Encryption key unavailable

**Inject:** Recovery account không thể lấy key từ key management service chính.

**Mục tiêu:** Kiểm chứng break-glass access và tách biệt key backup.

**Quan sát:**
- Recovery identity.
- Key version/identifier.
- Approval path.
- Audit trail.
- Decryption time.

**Pass criteria:** Key truy cập được theo policy, không lộ secret, thời gian cấp quyền nằm trong RTO.

---

## 17. Phân tích findings và cải tiến sau diễn tập

### 17.1. Phân loại findings

- **Critical:** Không thể phục hồi trong RPO/RTO; thiếu base backup/WAL/key hoặc không có quyền phục hồi.
- **High:** Restore được nhưng vượt RTO, thiếu một phần dữ liệu hoặc validation không đạt.
- **Medium:** Tài liệu/alert/role coordination thiếu nhưng có workaround.
- **Low:** Vấn đề nhỏ không ảnh hưởng mục tiêu hiện tại.

### 17.2. Root cause và contributing factors

Không dừng ở “job failed”. Ghi:
- Trigger.
- Root cause kỹ thuật.
- Điều kiện góp phần.
- Vì sao alert không phát hiện sớm.
- Vì sao backup/restore verification không phát hiện.
- Tác động tới RPO/RTO.
- Biện pháp khắc phục.
- Biện pháp phòng ngừa tái diễn.

### 17.3. Action item có thể theo dõi

Mỗi finding nên có:
- ID.
- Mô tả cụ thể.
- Severity.
- Owner.
- Due date.
- Acceptance criteria.
- Link evidence.
- Trạng thái.
- Retest date.

“Cải thiện monitoring” không phải acceptance criteria đủ rõ. Ví dụ cụ thể hơn: “Alert khi WAL generation > 0 và last archived time vượt 5 phút liên tục; alert route tới DBA on-call; test bằng archive destination failure trên staging.”

### 17.4. Retest

Sau khi fix, chạy lại đúng scenario hoặc một test thu hẹp để chứng minh lỗi đã hết. Đóng finding khi evidence pass, không chỉ khi code/config được deploy.

### 17.5. Đưa kết quả vào kế hoạch capacity

Restore drill cung cấp số liệu thực về:
- Restore throughput.
- WAL replay throughput.
- Storage bandwidth.
- CPU/memory.
- Time to provision.
- Time to validate.
- Archive growth.
- Required disk headroom.

Dùng số liệu để dự báo RTO khi database tăng gấp đôi, WAL rate tăng hoặc storage provider thay đổi.

---

## 18. Mẫu báo cáo backup và recovery drill

### 18.1. Thông tin chung

~~~text
Drill ID:
Date/time:
Environment:
Cluster/system identifier:
PostgreSQL major version:
Backup ID:
Backup type:
Scenario:
Recovery target:
Participants/roles:
~~~

### 18.2. Mốc thời gian

| Milestone | Start | End | Duration |
|---|---|---|---|
| Declare scenario | | | |
| Provision environment | | | |
| Retrieve/decrypt backup | | | |
| Restore base backup | | | |
| Replay WAL | | | |
| Start PostgreSQL | | | |
| Database validation | | | |
| Application validation | | | |
| Sign-off | | | |

### 18.3. Kết quả

~~~text
Backup artifact verification:
WAL chain continuity:
Timeline/recovery target reached:
Database validation:
Application validation:
Measured RPO:
Measured RTO:
RPO objective:
RTO objective:
Overall result: PASS / PARTIAL / FAIL
Evidence location:
Findings:
Action owners and due dates:
Retest date:
~~~

### 18.4. Báo cáo failure riêng

Một backup failure report cần nêu:
- Job run ID/backup ID.
- Last successful backup.
- First failure timestamp.
- Error class/message (đã redact).
- WAL/archive impact.
- Current disk headroom.
- RPO exposure.
- Recovery action.
- Retry result.
- Whether restore capability is still proven.
- Incident owner.

### 18.5. Phân biệt PASS, PARTIAL và FAIL

- **PASS:** mọi acceptance criteria đã định trước đều đạt, gồm RPO/RTO và application validation.
- **PARTIAL:** một phần recovery thành công nhưng có tiêu chí chưa đạt hoặc chưa có evidence.
- **FAIL:** không thể phục hồi tới target hoặc service validation thất bại, hay vượt objective mà không có phương án được chấp thuận.

Không đổi PARTIAL thành PASS chỉ vì PostgreSQL process đã start.

---

## 19. Checklist vận hành định kỳ

### 19.1. Hàng ngày

- [ ] Có verified backup mới trong SLA window.
- [ ] WAL archive vẫn tiến khi có WAL generation.
- [ ] Không có archive failure mới chưa xử lý.
- [ ] pg_wal filesystem có đủ headroom.
- [ ] Offsite copy status phù hợp policy.
- [ ] Replication slots/standby không giữ WAL bất thường.
- [ ] Backup catalog cập nhật và có artifacts.
- [ ] Alert routing hoạt động.

### 19.2. Hàng tuần

- [ ] Xem backup duration/size/throughput trends.
- [ ] Xem failure/retry trends.
- [ ] Kiểm tra sample manifest/checksum.
- [ ] Kiểm tra retention/lifecycle events.
- [ ] Xem slot/archiver backlog và disk growth.
- [ ] Chạy restore smoke test theo lịch.
- [ ] Xác nhận key/credentials recovery path còn dùng được.

### 19.3. Hàng tháng/quý

- [ ] Full restore drill.
- [ ] PITR drill theo lịch.
- [ ] Offsite restore test.
- [ ] Kiểm tra RTO/RPO measured.
- [ ] Tabletop role/access/communication.
- [ ] Review findings/action items.
- [ ] Kiểm tra backup catalog recovery.
- [ ] Rà soát retention và capacity forecast.

### 19.4. Sau thay đổi

- [ ] Test backup sau PostgreSQL/backup tool upgrade.
- [ ] Test restore sau thay storage/network/KMS.
- [ ] Test WAL archive sau đổi command/provider.
- [ ] Test tablespace/config/extensions sau migration.
- [ ] Cập nhật runbook và inventory.
- [ ] Chạy lại scenario liên quan.

---

## 20. Tài liệu tham khảo PostgreSQL

Ưu tiên tài liệu chính thức đúng major version server:

- [PostgreSQL — Backup and Restore](https://www.postgresql.org/docs/current/backup.html): tổng quan các chiến lược backup.
- [PostgreSQL — SQL Dump](https://www.postgresql.org/docs/current/backup-dump.html): pg_dump/pg_restore và logical backup.
- [PostgreSQL — File System Level Backup](https://www.postgresql.org/docs/current/backup-file.html): physical backup.
- [PostgreSQL — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): WAL archive và PITR.
- [PostgreSQL — pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): tạo base backup.
- [PostgreSQL — pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): kiểm tra backup manifest/checksums.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_archiver, pg_stat_wal và replication statistics.
- [PostgreSQL — pg_stat_progress_basebackup](https://www.postgresql.org/docs/current/progress-reporting.html): progress reporting.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): WAL/archiving settings.
- [PostgreSQL — Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication và standby.
- [PostgreSQL — Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): recovery target và restore command.
- [PostgreSQL — amcheck](https://www.postgresql.org/docs/current/amcheck.html): kiểm tra một số cấu trúc index.

Đường dẫn /current/ có thể trỏ tới phiên bản mới hơn phiên bản đang chạy. Xác minh command options, view columns, recovery signal files và configuration semantics theo đúng major version.

---

## 21. Bài tập thực hành

Các câu hỏi dùng PostgreSQL lab hoặc hệ thống giả lập. Không chạy lệnh phá hoại trên production; mọi failure injection phải ở môi trường kiểm thử đã cách ly.

### Bài 1 — Backup thành công

Một backup job exit code 0 và ghi trạng thái SUCCESS. Vì sao chưa thể kết luận database có thể restore?

### Bài 2 — Physical và logical

Phân biệt physical base backup + WAL archive với pg_dump. Loại nào hỗ trợ PITR theo WAL chain?

### Bài 3 — Replica

Vì sao một standby khỏe không thay thế backup độc lập?

### Bài 4 — RPO

Giải thích RPO bằng ví dụ database có RPO 15 phút.

### Bài 5 — RTO

Một cluster khởi động sau 30 phút nhưng application smoke test hoàn tất sau 75 phút. Nếu RTO định nghĩa service usable, RTO thực tế là bao nhiêu?

### Bài 6 — Backup schedule

Base backup chạy mỗi đêm, WAL archive liên tục. RPO có nhất thiết bằng 24 giờ không? Điều kiện gì quyết định?

### Bài 7 — Backup metadata

Liệt kê ít nhất tám trường metadata nên lưu cho mỗi backup.

### Bài 8 — pg_stat_archiver

Nêu ý nghĩa archived_count, failed_count, last_archived_time và stats_reset. Vì sao phải theo dõi stats_reset?

### Bài 9 — Archive freshness

last_archived_time đã cũ 2 giờ nhưng database không phát sinh WAL. Có nên lập tức báo archive failure không? Vì sao?

### Bài 10 — WAL generation

pg_stat_wal.wal_bytes tăng 300 MiB trong 5 phút. Tính tốc độ WAL trung bình MiB/phút. Nêu một giới hạn của phép đo.

### Bài 11 — Replication slot

Một logical replication slot inactive giữ restart_lsn cũ và pg_wal tăng. Vì sao không nên drop slot ngay?

### Bài 12 — Base backup progress

pg_stat_progress_basebackup cho biết backup_total và backup_streamed. Những trường này chứng minh điều gì và không chứng minh điều gì?

### Bài 13 — pg_ls_waldir

Viết query đếm số WAL files và tổng size theo pg_ls_waldir().

### Bài 14 — Backup verification

pg_verifybackup có thể kiểm tra gì? Vì sao vẫn cần restore drill?

### Bài 15 — Logical dump

pg_restore --list thành công. Điều đó chứng minh restore đầy đủ thành công chưa? Cần làm gì tiếp?

### Bài 16 — WAL continuity

Có base backup và WAL segment cuối cùng nhưng thiếu một segment ở giữa. Có thể PITR qua khoảng bị thiếu không? Giải thích.

### Bài 17 — Encryption

Backup encrypted nhưng key chỉ truy cập được từ production region. Rủi ro là gì và cần diễn tập điều gì?

### Bài 18 — Offsite

Vì sao backup copy trong cùng cloud account/region có thể không đủ bảo vệ trước disaster hoặc attacker?

### Bài 19 — Retention

Vì sao không nên xóa WAL theo tuổi file đơn thuần?

### Bài 20 — Backup catalog

Catalog bị mất nhưng objects vẫn còn. Vì sao recovery vẫn có thể khó? Cần backup thêm gì?

### Bài 21 — Archive failures

failed_count tăng và pg_wal usage tăng. Nêu năm bước điều tra theo thứ tự.

### Bài 22 — Generation và retention pressure

Phân biệt WAL generation pressure với WAL retention pressure. Có thể cùng tồn tại không?

### Bài 23 — Missing WAL

Recovery báo thiếu segment. Nêu thông tin cần xác định trước khi kết luận không thể phục hồi.

### Bài 24 — Restore isolation

Nêu ít nhất năm biện pháp để restore test không gây side effects sang production.

### Bài 25 — Recovery target

Vì sao recovery_target_time cần timezone rõ ràng? Cần kiểm chứng target như thế nào?

### Bài 26 — PITR marker

Thiết kế test với một marker trước và một marker sau thời điểm recovery target. Kết quả mong đợi là gì?

### Bài 27 — Application validation

Vì sao SELECT 1 không đủ để đánh giá restore thành công? Nêu bốn business checks.

### Bài 28 — RTO breakdown

Liệt kê các mốc thời gian nên đo trong full restore drill.

### Bài 29 — Tabletop

Tabletop exercise có thể phát hiện vấn đề gì? Nó không chứng minh điều gì?

### Bài 30 — Pass criteria

Một drill restore PostgreSQL thành công nhưng vượt RTO 2 lần. Kết quả nên là PASS, PARTIAL hay FAIL? Giải thích theo acceptance criteria.

### Bài 31 — Backup job không chạy

Scheduler không trigger job. Nêu cách phân biệt lỗi scheduler với lỗi PostgreSQL.

### Bài 32 — Storage failure

Archive destination báo permission denied. Vì sao retry vô hạn không giải quyết được lỗi này? Cần sửa gì?

### Bài 33 — WAL disk gần đầy

pg_wal filesystem còn 5% capacity, archive failures tăng và có slot inactive. Nêu trình tự ứng phó an toàn.

### Bài 34 — Backup duration regression

Backup duration tăng từ 20 lên 90 phút dù database size tăng 10%. Nêu các nguyên nhân cần kiểm tra.

### Bài 35 — Base backup thiếu tablespace

Restore báo tablespace path không tồn tại. Cần kiểm tra metadata và hạ tầng nào?

### Bài 36 — Extension missing

Physical backup restore được nhưng PostgreSQL không start vì extension library thiếu. Vì sao điều này có thể xảy ra và chuẩn bị thế nào?

### Bài 37 — Snapshot consistency

Một VM snapshot được tạo khi database đang hoạt động. Vì sao chưa thể mặc định snapshot đó là valid backup?

### Bài 38 — Immutability

Backup immutable trong 30 ngày nhưng RPO/RTO yêu cầu restore một điểm 60 ngày trước. Cần đánh giá policy nào?

### Bài 39 — Restore test stale

Backup mới chạy hàng ngày nhưng restore drill gần nhất cách đây 9 tháng. Rủi ro là gì và cần lập kế hoạch nào?

### Bài 40 — Failure classification

Một backup được tạo và verify local, nhưng offsite upload thất bại. Job nên được ghi nhận thế nào trong backup catalog?

### Bài 41 — RPO calculation

Sự cố xảy ra 12:00. WAL cuối cùng được xác nhận archive an toàn là 11:52, nhưng segment chain liên tục chỉ được chứng minh tới 11:45. RPO có thể công bố là bao nhiêu?

### Bài 42 — Drill sau thay đổi

Backup tool upgrade và KMS key rotation vừa hoàn tất. Những test nào nên chạy trước khi coi pipeline ổn định?

### Bài 43 — Restore từ backup cũ

Backup mới nhất checksum pass nhưng WAL chain thiếu một segment; backup cũ hơn có chain đầy đủ. Nên chọn backup nào và vì sao?

### Bài 44 — Action item

Một finding ghi “monitoring chưa tốt”. Viết lại thành action item có acceptance criteria đo được.

### Bài 45 — Runbook production

Base backup thất bại, archive cũng có failure, pg_wal usage tăng nhanh và RPO đang bị đe dọa. Viết các bước ứng phó ưu tiên.

---

## 22. Lời giải — bài 1 đến 25

### Bài 1 — Backup thành công

Exit code 0 chỉ xác nhận process kết thúc theo cách tool báo success. Cần kiểm tra completeness, manifest/checksum, WAL chain, offsite copy, restore test và application validation. Backup có thể thiếu file hoặc không giải mã được dù job báo success.

### Bài 2 — Physical và logical

Physical base backup là bản sao vật lý của cluster; kết hợp WAL archive liên tục có thể PITR. pg_dump là logical dump của database/objects; nó không thay thế physical base backup và WAL archive chain.

### Bài 3 — Replica

Replica có thể nhận và áp dụng DELETE nhầm, UPDATE sai hoặc corruption logic từ primary. Replica phục vụ HA/failover; backup độc lập với retention và PITR mới giúp quay về trước lỗi đã replicate.

### Bài 4 — RPO

RPO 15 phút nghĩa là tổ chức chấp nhận mất tối đa lượng dữ liệu tương đương 15 phút trước sự cố theo cách đo đã thống nhất. Nếu điểm phục hồi gần nhất có thể chứng minh chỉ tới 11:40 khi sự cố lúc 12:00, RPO thực tế là 20 phút và không đạt mục tiêu.

### Bài 5 — RTO

Nếu tiêu chí là service usable sau application smoke test, RTO là 75 phút, không phải 30 phút lúc PostgreSQL start.

### Bài 6 — Backup schedule

Không. Base backup là nền để phục hồi; WAL archive liên tục có thể đưa recovery point gần thời điểm sự cố hơn 24 giờ. Điều kiện là archive liên tục, đúng timeline, truy cập/giải mã được và có base backup phù hợp.

### Bài 7 — Backup metadata

Ví dụ: backup ID, system identifier, PostgreSQL version, backup type, start/end time, start/stop LSN, timeline, tablespaces, manifest/checksum, WAL range, encryption key ID, storage object version, retention expiry, verification status.

### Bài 8 — pg_stat_archiver

archived_count là số archive success từ stats reset; failed_count là failures; last_archived_time là lần success gần nhất; stats_reset là mốc reset counters. Khi reset, delta/count baseline phải khởi tạo lại; giá trị zero không chứng minh chưa từng lỗi.

### Bài 9 — Archive freshness

Chưa nên alert failure chỉ từ timestamp. Nếu database idle, không có segment mới cần archive thì last_archived_time cũ có thể bình thường. Correlate với WAL generation, segment switch/archive timeout policy và destination health.

### Bài 10 — WAL generation

300 MiB / 5 phút = **60 MiB/phút**. Đây là counter cluster-wide, có thể bao gồm mọi sessions/background activity và cần kiểm tra stats_reset.

### Bài 11 — Replication slot

Slot có thể là dependency của logical consumer; drop có thể làm consumer không thể tiếp tục từ vị trí cũ và phải reinitialize/re-snapshot. Xác định owner, consumer, restart_lsn và business impact trước khi drop.

### Bài 12 — Base backup progress

View cho biết phase và lượng data đã stream/ước lượng total trong tiến trình. Nó không chứng minh process kết thúc thành công, manifest/checksum pass, offsite copy xong hoặc restore được.

### Bài 13 — pg_ls_waldir

~~~sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_size
FROM pg_ls_waldir();
~~~

Cần quyền phù hợp và version hỗ trợ; dùng filesystem metrics để theo dõi capacity thực.

### Bài 14 — pg_verifybackup

Nó kiểm tra manifest và checksum/files của physical backup theo khả năng version. Nó không thay thế full restore, WAL replay, key retrieval, application validation và RTO measurement.

### Bài 15 — Logical dump

Chưa. --list chỉ đọc TOC. Cần restore vào database riêng, xác nhận extensions, roles/owners, schema/data và chạy application/business checks.

### Bài 16 — WAL continuity

Không thể replay qua một segment bắt buộc bị thiếu. Recovery sẽ dừng tại điểm trước gap hoặc thất bại theo target. Cần tìm segment ở archive/offsite/version history hoặc chọn recovery target sớm hơn.

### Bài 17 — Encryption

Khi mất region chính, backup và key có thể cùng không truy cập được; RTO không đạt dù objects còn. Diễn tập break-glass identity, key version retrieval, approval/audit và decryption từ region khác.

### Bài 18 — Offsite

Một incident, account compromise, region outage hoặc lifecycle misconfiguration có thể xóa/khóa cả primary lẫn backup cùng failure domain. Tách account/region/credentials và dùng immutable/offline copies theo policy.

### Bài 19 — Retention

WAL là dependency của base backup/PITR. Xóa theo tuổi có thể tạo gap trong chuỗi cần thiết cho một backup còn được retention. Phải xóa theo backup set/dependency và policy.

### Bài 20 — Backup catalog

Không có catalog sẽ khó tìm backup ID, version, timeline, WAL range, key ID, tablespace mapping và retention. Cần backup catalog, encryption metadata, runbooks và configuration inventory độc lập.

### Bài 21 — Archive failures

1. Đọc pg_stat_archiver và logs, xác định file/error đầu tiên.
2. Kiểm tra destination/quota/permissions/network/KMS.
3. Đo WAL generation và pg_wal disk headroom.
4. Kiểm tra slots/standby/restart_lsn giữ WAL.
5. Khôi phục archive pipeline, theo dõi catch-up và continuity; không xóa WAL thủ công.

### Bài 22 — Generation và retention pressure

Generation pressure là WAL được tạo nhanh hơn khả năng xử lý/archive. Retention pressure là WAL không thể recycle vì archive/slot/standby/checkpoint còn cần. Hai loại có thể xảy ra đồng thời.

### Bài 23 — Missing WAL

Xác định filename, LSN, timeline, base backup ID, recovery target, archive catalog, logs, offsite copies và version history. Chỉ sau khi tìm hết nguồn mới kết luận target tối đa có thể đạt.

### Bài 24 — Restore isolation

Ví dụ: network riêng, port/DNS riêng, chặn outbound email/payment/webhooks, dùng test credentials, giới hạn egress, không đăng ký service discovery production, không dùng role có quyền ghi production.

### Bài 25 — Recovery target

Timezone không rõ có thể làm target bị diễn giải sai và phục hồi lệch thời điểm. Dùng timestamp có offset rõ, marker trước/sau target và kiểm tra recovery logs/target reached cùng data state.

---

## 23. Lời giải — bài 26 đến 45

### Bài 26 — PITR marker

Ghi marker A trước target, rồi marker B sau target. Restore tới thời điểm giữa hai markers. Kết quả mong đợi: A tồn tại; B và các changes sau target không xuất hiện. Kiểm tra timestamp/timezone và transaction commit boundary.

### Bài 27 — Application validation

SELECT 1 chỉ chứng minh server nhận query đơn giản. Business checks nên gồm:
- Tổng đơn hàng/tổng tiền theo ngày.
- Số lượng tài khoản active.
- Kiểm tra foreign key/orphan.
- Đọc một số transaction/order IDs đã biết.
- Kiểm tra outbox/event sequence hoặc invariants quan trọng.

### Bài 28 — RTO breakdown

Provision host, lấy/decrypt backup, restore base backup, replay WAL, start PostgreSQL, database validation, application validation, route/cutover và sign-off.

### Bài 29 — Tabletop

Tabletop tìm thiếu sót về quyền, role, escalation, communication, recovery target decision, key access, dependency và runbook. Nó không chứng minh artifacts restore được hoặc PostgreSQL có thể replay WAL.

### Bài 30 — Pass criteria

Nếu RTO là acceptance criterion và restore mất gấp đôi RTO, kết quả là FAIL hoặc PARTIAL theo policy đã định; không thể PASS chỉ vì server start. Báo cáo phải giữ rõ tiêu chí không đạt.

### Bài 31 — Backup job không chạy

Kiểm tra scheduler logs, next run, job enabled/paused, trigger history, host/service health và job run ID. Nếu scheduler không tạo process thì lỗi ở orchestration; nếu process đã chạy, xem backup tool logs và PostgreSQL logs để phân biệt lỗi server/connection.

### Bài 32 — Storage failure

Permission denied là lỗi cấu hình/quyền thường mang tính permanent; retry vô hạn chỉ lặp lỗi và có thể tạo log storm. Sửa IAM/ACL/ownership/secret theo least privilege, xác minh bằng test upload và chỉ retry sau khi destination có thể ghi.

### Bài 33 — WAL disk gần đầy

1. Báo incident và ghi disk headroom/WAL growth.
2. Kiểm tra pg_stat_archiver/logs/destination.
3. Khôi phục archive connectivity/permissions.
4. Kiểm tra generation rate và replication slots/standby.
5. Xác định owner của inactive slot; không drop nếu chưa biết consumer.
6. Throttle write-heavy jobs nếu được phép.
7. Không xóa WAL thủ công.
8. Theo dõi archive catch-up, slot progress và recycling.
9. Xác minh WAL chain/backup recoverability sau remediation.

### Bài 34 — Backup duration regression

Kiểm tra data size thực, throughput, I/O latency, CPU/compression/encryption, network throttling, object storage, backup concurrency, WAL generation/FPI, snapshot behavior và backup tool/version changes. Đo bytes/sec thay vì chỉ so elapsed time.

### Bài 35 — Tablespace

Kiểm tra backup manifest/catalog liệt kê đủ tablespaces, path mapping, symlinks/objects, mount point, permissions, capacity và restore tool options. Provision đúng paths hoặc mapping sang vị trí mới theo quy trình được hỗ trợ.

### Bài 36 — Extension missing

Physical backup lưu catalog/data nhưng không nhất thiết chứa binary shared libraries cần để server load extension trên host mới. Duy trì inventory tên/version/package, cài binaries tương thích trước restore và đưa việc kiểm tra extension vào drill.

### Bài 37 — Snapshot consistency

Snapshot có thể bắt gặp writes đang diễn ra, nhiều volumes không cùng thời điểm, hoặc không phối hợp PostgreSQL backup/WAL semantics. Phải xác minh crash-consistency/application-consistency, snapshot group, WAL capture và restore instructions của provider.

### Bài 38 — Immutability

Retention 30 ngày không đáp ứng recovery point 60 ngày nếu không có backup/WAL chain còn giữ tới đó. Review retention horizon, archive lifecycle, legal policy, capacity và dependency; immutable lock không tự kéo dài backup đã hết hạn.

### Bài 39 — Restore test stale

Backup tool/storage/key/config có thể đã đổi, corruption có thể tích lũy, RTO có thể tăng và key access có thể hết hạn. Lập restore smoke test ngay, full restore/PITR drill và retest sau mọi thay đổi lớn.

### Bài 40 — Catalog state

Nên ghi là local verified nhưng offsite pending/failed (partial), không đánh dấu backup hoàn chỉnh theo policy yêu cầu offsite. Alert owner, retry upload sau khi xử lý, rồi verify destination và update catalog state.

### Bài 41 — RPO calculation

Mặc dù một segment được archive tới 11:52, continuity chỉ được chứng minh tới 11:45. Recovery point an toàn đã được chứng minh là 11:45, nên RPO bảo thủ là **15 phút** tại thời điểm sự cố 12:00. Không công bố 8 phút nếu WAL chain còn gap chưa giải quyết.

### Bài 42 — Drill sau thay đổi

Chạy manifest/checksum verification, restore smoke test, PITR/WAL archive test, offsite retrieval, key retrieval/decryption qua recovery identity, application validation và đo RTO. Test cả rollback/recovery path nếu tool upgrade có migration/catalog changes.

### Bài 43 — Backup cũ hơn

Chọn backup cũ hơn có WAL chain đầy đủ nếu mục tiêu recovery cần thiết nằm trong khoảng đó. Backup mới hơn nhưng thiếu segment không thể đạt target; timestamp gần hơn không thắng tính recoverability.

### Bài 44 — Action item

Ví dụ: “Trong 10 ngày, thêm alert khi WAL generation > 0 và last_archived_time vượt 5 phút liên tục; alert phải gắn cluster ID, last archived WAL, failed_count delta, pg_wal free space và route tới DBA on-call. Chạy staging test bằng cách làm archive destination read-only và lưu alert event làm evidence.”

### Bài 45 — Runbook production

1. Declare incident, ghi current RPO exposure, disk headroom và last verified backup.
2. Kiểm tra archive failure logs, pg_stat_archiver, WAL generation và destination.
3. Xác định base backup gần nhất còn restore được và WAL chain.
4. Khôi phục destination credentials/network/quota.
5. Kiểm tra replication slots/standby giữ WAL, xác định owner trước mọi action.
6. Throttle write-heavy imports/jobs nếu được phê duyệt để giữ disk headroom.
7. Không xóa WAL, không drop slots vô danh.
8. Theo dõi archive catch-up, disk usage và continuity.
9. Tạo backup mới khi pipeline ổn định; verify artifacts/offsite.
10. Chạy restore/PITR validation nếu chain đã bị ảnh hưởng.
11. Cập nhật incident status/RPO và escalation theo policy.

---

## 24. Bảng quyết định nhanh

| Tín hiệu | Diễn giải có thể | Bước tiếp theo |
|---|---|---|
| Backup job không xuất hiện | Scheduler/agent chưa trigger | Kiểm tra scheduler, lịch, host và job history |
| Job exit nonzero | Backup tool/DB/storage failure | Đọc log và phân loại error |
| Job success nhưng manifest missing | Artifact incomplete | Đánh dấu partial, không catalog là verified |
| pg_stat_archiver failures tăng | Archive command/destination lỗi | Kiểm tra logs, permissions, network, quota |
| Last archive cũ, WAL idle | Có thể bình thường | Đối chiếu WAL generation và archive policy |
| Last archive cũ, WAL đang tăng | Archive có thể bị stall | Alert và kiểm tra destination/backlog |
| pg_wal usage tăng | Generation hoặc retention pressure | Kiểm tra wal_bytes, slots, archive, standby |
| Slot inactive giữ restart_lsn cũ | Consumer không tiến | Xác định owner; phục hồi consumer hoặc xử lý có phê duyệt |
| pg_verifybackup fail | Manifest/file/checksum issue | Quarantine artifact, chọn backup khác |
| Verify pass nhưng restore fail | WAL/config/extension/key/restore path issue | Full restore runbook |
| PostgreSQL start nhưng app fail | Roles/schema/secrets/data/dependencies | Application validation và business checks |
| RTO vượt target | Restore capacity/process chưa đạt | Phân tích time breakdown, tune và retest |
| Offsite copy pending | Failure domain protection chưa hoàn tất | Alert, retry và verify remote copy |
| Restore drill quá cũ | Khả năng phục hồi chưa được chứng minh gần đây | Lập smoke/full restore test |

---

## 25. Mẫu lịch và hồ sơ diễn tập

Một lịch đơn giản có thể ghi mỗi lần test như sau:

| Field | Ví dụ |
|---|---|
| Drill ID | DR-2026-11-01 |
| Cluster | orders-prod |
| Backup ID | base-2026-11-14-0001 |
| Scenario | PITR before accidental DELETE |
| Target | 2026-11-14 10:30:00+07 |
| Start | 10:00 |
| Database ready | 10:42 |
| App validation complete | 10:55 |
| Measured RTO | 55 minutes |
| Measured RPO | 7 minutes |
| Result | PASS nếu objectives và mọi checks đạt |
| Findings | Không có / danh sách |
| Owner | DBA on-call |
| Retest | Theo findings |

Dữ liệu trong bảng chỉ minh họa. Drill record thật cần lưu evidence path và version cụ thể.

### 25.1. Lịch backup và restore phải liên kết

Backup schedule chỉ có ý nghĩa khi restore test dùng một backup ID thực tế trong schedule. Không tạo restore test bằng một bản backup được chuẩn bị riêng nếu mục tiêu là chứng minh production pipeline.

### 25.2. Lịch phải tính thời gian phát hiện lỗi

Nếu corruption có thể tồn tại nhiều ngày trước khi phát hiện, retention cần đủ dài để còn một backup trước thời điểm corruption. Chỉ giữ vài ngày backup có thể khiến mọi restore point đều đã mang lỗi.

### 25.3. Thời gian kiểm tra cũng là một phần RTO

Nếu restore xong trong 20 phút nhưng cần 2 giờ để xác minh dữ liệu nghiệp vụ thủ công, service chưa đạt RTO nếu acceptance criteria yêu cầu validation. Tự động hóa các checks quan trọng và lưu expected values an toàn.

---

## 26. Tổng kết

Theo dõi backup phải trả lời được ba câu hỏi: **bản backup mới nhất có đầy đủ và toàn vẹn không, WAL có liên tục tới recovery point cần thiết không, và tổ chức đã thực sự phục hồi thành công gần đây chưa?**

Các nguyên tắc cần nhớ:

1. **Backup success không phải restore success:** xác minh artifacts, WAL, database và application.
2. **Physical backup và logical dump có mục đích khác nhau:** pg_dump không thay base backup/WAL PITR.
3. **Replica không phải backup độc lập:** lỗi logic có thể được replicate.
4. **RPO/RTO phải đo được:** định nghĩa start/end và recovery point rõ.
5. **pg_stat_archiver cần được đọc theo ngữ cảnh:** freshness, failure deltas, stats reset và WAL generation.
6. **WAL generation khác retention:** disk tăng có thể do workload hoặc slot/archive/standby giữ segments.
7. **Manifest/checksum chỉ là một tầng:** pg_verifybackup không thay full restore.
8. **WAL chain phải liên tục và đúng timeline:** một segment thiếu có thể giới hạn recovery target.
9. **Offsite/key access cần được diễn tập:** backup encrypted nhưng không giải mã được cũng là backup không dùng được.
10. **Restore phải cách ly:** chặn DNS, outbound calls, credentials và service discovery production.
11. **Application validation là bắt buộc:** server start và SELECT 1 không chứng minh dữ liệu nghiệp vụ đúng.
12. **Tabletop và technical drill bổ sung nhau:** một bên kiểm tra coordination, bên kia kiểm chứng kỹ thuật.
13. **Đo RTO theo từng milestone:** provision, retrieve, restore, replay, validate và cutover.
14. **Findings cần owner, due date và retest:** không đóng issue chỉ vì config đã deploy.
15. **Retention phải giữ dependency:** không xóa WAL theo tuổi file nếu còn base backup cần chuỗi đó.
16. **Catalog, key và runbook cũng cần backup:** recovery phụ thuộc metadata và quyền truy cập.
17. **Không xóa WAL hoặc drop slots theo phản xạ:** xác định owner/dependency trước.
18. **Diễn tập sau thay đổi lớn:** tool, version, storage, KMS, network và retention đều có thể làm recovery hỏng.

Một chương trình đáng tin cậy đi theo vòng lặp: **lên lịch backup → xác minh artifacts → theo dõi WAL/archive/retention → restore thử từ nơi lưu trữ thật → kiểm tra database và ứng dụng → đo RPO/RTO → xử lý findings → diễn tập lại**.
