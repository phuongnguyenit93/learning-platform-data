# Dựng primary, standby và diễn tập chuyển đổi vai trò trong PostgreSQL

PostgreSQL có thể duy trì một hoặc nhiều standby servers nhận WAL từ primary để phục vụ read-only workloads, tăng khả năng phục hồi và giảm thời gian gián đoạn khi node chính gặp sự cố. Tuy nhiên, có standby chưa đồng nghĩa với high availability. Một hệ thống HA cần chứng minh rằng standby nhận đủ WAL, replay đúng, có thể được promote, ứng dụng chuyển kết nối an toàn và node cũ không thể tiếp tục nhận writes sau failover.

Bài thực hành này xây dựng nền tảng physical streaming replication giữa một primary và một standby, thiết lập giám sát, sau đó diễn tập hai quy trình:

- **Switchover có kế hoạch:** chuyển vai trò khi primary còn khỏe và có thể phối hợp dừng writes, chờ standby bắt kịp rồi promote.
- **Failover khẩn cấp:** chuyển sang standby khi primary mất khả năng phục vụ; phải xác định node đủ mới, fencing primary cũ và chấp nhận/đo lường khả năng mất dữ liệu nếu replication bất đồng bộ.

Điểm quan trọng nhất của một lần chuyển vai trò là bảo đảm chỉ có một primary được phép nhận writes. Promote standby trước khi cô lập primary cũ có thể tạo split-brain: hai node cùng nhận các giao dịch độc lập, không thể ghép lịch sử WAL thành một lịch sử duy nhất. DNS change hoặc đổi connection string không phải fencing.

~~~mermaid
flowchart TD
    A["Primary đang phục vụ writes"] --> B["WAL streaming"]
    B --> C["Standby nhận và replay WAL"]
    C --> D{"Loại chuyển đổi"}
    D -->|"Planned switchover"| E["Quiesce writes và drain"]
    D -->|"Emergency failover"| F["Fence primary cũ"]
    E --> G["Xác nhận standby bắt kịp"]
    F --> H["Chọn standby có WAL mới nhất"]
    G --> I["Promote standby"]
    H --> I
    I --> J["Chuyển endpoint và connection pools"]
    J --> K["Verify writes, replication và application"]
    K --> L["Rebuild/rejoin node cũ thành standby"]
~~~

Bài học thuộc chương **Thực hành tổng hợp**, module **Database Engine Relational PostgreSQL**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích primary, physical standby, WAL sender, WAL receiver và replay.
2. Phân biệt streaming replication với WAL archiving.
3. Chuẩn bị primary cho physical replication.
4. Tạo replication role và cấu hình pg_hba.conf an toàn.
5. Bootstrap standby bằng pg_basebackup.
6. Cấu hình standby.signal, primary_conninfo và replication slot.
7. Xác minh WAL receive/replay và replication lag.
8. Hiểu synchronous và asynchronous replication, RPO và RTO.
9. Theo dõi replication slots, WAL retention và disk capacity.
10. Thực hiện switchover có kế hoạch.
11. Thực hiện failover khẩn cấp với fencing.
12. Promote standby và xác minh node mới là primary.
13. Chuyển application endpoint và xử lý connection pools.
14. Rejoin primary cũ bằng pg_rewind hoặc base backup.
15. Kiểm tra replication topology sau chuyển đổi.
16. Diễn tập lỗi mà không tạo split-brain.
17. Thu thập evidence và đánh giá RPO/RTO thực tế.

## 2. Kiến trúc và thuật ngữ

Trong physical streaming replication:

- **Primary:** node nhận transaction writes từ ứng dụng và tạo WAL.
- **Standby:** node nhận WAL, ghi WAL xuống local storage và replay để cập nhật data pages.
- **WAL sender:** process trên primary gửi WAL cho standby.
- **WAL receiver:** process trên standby nhận WAL.
- **Startup/recovery process:** replay WAL và giữ standby ở chế độ recovery.
- **Replication slot:** giữ WAL cần thiết cho một consumer.
- **WAL archive:** nơi lưu WAL segments để phục hồi hoặc bắt kịp khi streaming bị gián đoạn.
- **Promotion:** kết thúc recovery và biến standby thành primary có thể nhận writes.
- **Fencing:** bảo đảm node cũ không thể tiếp tục hoạt động như primary.

~~~mermaid
flowchart LR
    A["Application writes"] --> P["Primary"]
    P --> W["WAL"]
    W --> S["WAL sender"]
    S --> R["WAL receiver"]
    R --> D["Standby WAL"]
    D --> H["Replay / recovery"]
    H --> Q["Hot standby reads"]
~~~

Physical replication chuyển WAL ở mức cluster, không phải chỉ những rows thuộc một publication. Standby là bản sao vật lý của cluster và cần binary/data compatibility theo PostgreSQL version, architecture và upgrade policy.

## 3. Streaming replication và WAL archiving

Hai cơ chế thường được kết hợp:

**Streaming replication** tạo kết nối liên tục giữa primary và standby. WAL được gửi gần thời gian thực, giúp giảm replication lag khi mạng và node khỏe.

**WAL archiving** sao chép WAL segments đã hoàn tất sang archive. Standby có thể dùng archive để bắt kịp khi WAL segment không còn trên primary hoặc để phục hồi từ base backup.

| Tiêu chí | Streaming | WAL archive |
| --- | --- | --- |
| Cách truyền | Kết nối replication liên tục | Archive command / archive service |
| Độ trễ | Thường thấp | Phụ thuộc segment switch và archive pipeline |
| Mục đích | Standby gần realtime | Recovery, catch-up, PITR |
| Phụ thuộc | Network, WAL sender/receiver | Archive storage và restore_command |
| Khi gián đoạn | Có thể reconnect nếu WAL còn | Có thể fetch segment đã archive |
| Monitoring | Receiver state, LSN lag | Archive success/failure, archive freshness |

WAL archive không thay thế monitoring streaming. Streaming không thay thế backup hoặc archive retention.

## 4. Xác định topology và failure domains

Trước khi cài đặt, ghi rõ:

- Primary hostname/IP và data directory.
- Standby hostname/IP và data directory.
- PostgreSQL major/minor version.
- OS/architecture và storage layout.
- Network route, firewall và TLS policy.
- Replication mode: async hay sync.
- WAL archive destination.
- Replication slot ownership.
- Application endpoint/VIP/proxy.
- HA manager nếu có.
- Backup/PITR policy.
- RPO/RTO mục tiêu.
- Người có quyền promote/fence.

Primary và standby nên nằm ở failure domains độc lập phù hợp: khác host, storage fault domain hoặc availability zone tùy yêu cầu. Hai VM trên cùng host hoặc hai disks cùng storage array có thể cùng hỏng trong một sự cố.

Không đặt một standby ở vị trí xa đến mức network latency khiến synchronous commits vi phạm latency SLO nếu synchronous mode được chọn.

## 5. Kiểm tra phiên bản và identity trên hai node

Trên mỗi node, xác minh PostgreSQL version:

~~~sql
SELECT
    version(),
    current_setting('server_version_num') AS server_version_num,
    pg_is_in_recovery() AS is_standby,
    pg_postmaster_start_time();
~~~

Kiểm tra binary:

~~~bash
postgres --version
pg_basebackup --version
pg_ctl --version
~~~

Primary và physical standby cần version/format tương thích theo quy định của PostgreSQL. Không dùng pg_basebackup từ một major version không tương thích hoặc copy data directory đang chạy bằng filesystem copy tùy tiện.

Ghi lại system identifier bằng pg_controldata trên mỗi cluster. Primary và standby physical replica phải thuộc cùng cluster lineage; base backup từ primary tạo ra standby cùng system identifier.

## 6. Cấu hình primary cho physical replication

Các tham số phổ biến:

~~~conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = 2GB
max_slot_wal_keep_size = 20GB
hot_standby = on
archive_mode = on
archive_command = 'test ! -f /archive/%f && cp %p /archive/%f'
~~~

Đây là ví dụ để giải thích các thành phần, không phải cấu hình production dùng nguyên xi. Đường dẫn archive, capacity, permissions và cơ chế upload phải phù hợp môi trường. Archive command mẫu dùng local filesystem và cần được thay bằng archive service đáng tin cậy khi triển khai thực tế.

Ý nghĩa:

- wal_level = replica: ghi đủ WAL cho physical replication.
- max_wal_senders: giới hạn WAL sender connections.
- max_replication_slots: số replication slots được phép.
- wal_keep_size: lượng WAL tối thiểu giữ lại theo cấu hình, không thay thế slot/archive.
- max_slot_wal_keep_size: giới hạn WAL giữ bởi replication slots trên version hỗ trợ.
- hot_standby: cho phép read-only queries khi standby đang replay.
- archive_mode/archive_command: lưu WAL segments ra archive.

Một số tham số yêu cầu restart. Xem context trước khi thay đổi:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'hot_standby',
    'archive_mode'
)
ORDER BY name;
~~~

Không đặt max_slot_wal_keep_size thành giá trị quá thấp mà không hiểu slot behavior; slot có thể bị invalidated khi WAL cần thiết bị recycle. Cũng không để unlimited mà thiếu capacity alerts.

## 7. Tạo replication role

Trên primary, tạo role chuyên dùng cho replication:

~~~sql
CREATE ROLE replicator
    WITH LOGIN
    REPLICATION
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT;
~~~

Đặt password qua secret manager hoặc quy trình credential an toàn. Không đưa password vào source control, shell history hoặc log.

Kiểm tra role:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication,
    rolsuper
FROM pg_roles
WHERE rolname = 'replicator';
~~~

Role REPLICATION cho phép kết nối replication protocol. Hạn chế source IP trong pg_hba.conf, yêu cầu TLS theo policy và rotate credential.

## 8. Cấu hình pg_hba.conf

Trên primary, cho phép standby host kết nối replication:

~~~conf
hostssl replication replicator 10.20.30.12/32 scram-sha-256
~~~

Thay địa chỉ ví dụ bằng IP/CIDR của standby. Nếu môi trường không dùng TLS, đánh giá policy trước khi dùng host rule; ưu tiên hostssl và xác thực certificate khi phù hợp.

Reload cấu hình:

~~~sql
SELECT pg_reload_conf();
~~~

Kiểm tra parse errors:

~~~sql
SELECT *
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
~~~

pg_hba.conf rule được xét theo thứ tự. Rule rộng hơn đứng trước có thể khiến rule cụ thể không được áp dụng. Kiểm tra cả network firewall/security groups.

## 9. Xác minh WAL archiving

Trên primary:

~~~sql
SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Theo dõi:

- failed_count tăng.
- last_archived_time quá cũ so với WAL generation.
- Archive destination đầy.
- Archive command trả lỗi.
- WAL segment tồn đọng trong pg_wal.

Nếu archive command thất bại, PostgreSQL có thể retry và giữ WAL trên primary; disk có thể tăng nhanh. Cần alert và runbook.

Một archive pipeline chỉ đáng tin cậy khi có kiểm tra tồn tại, integrity, retention, access control và restore test. Không xóa WAL archive bằng tay nếu chưa xác định PITR/standby dependencies.

## 10. Tạo replication slot cho standby

Physical replication slot giúp primary giữ WAL cho standby khi standby tạm ngắt kết nối.

Tạo slot:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
~~~

Kiểm tra:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
WHERE slot_type = 'physical';
~~~

Một số columns chỉ có trên PostgreSQL versions mới. Nếu query column không tồn tại, xem schema của pg_replication_slots trên version đang chạy.

Slot cần có owner rõ ràng. Không tạo nhiều slot dự phòng không được sử dụng vì inactive slots vẫn có thể giữ WAL. Nếu standby được cấu hình dùng slot, slot name phải khớp.

Có thể để pg_basebackup tạo slot bằng các option phù hợp, nhưng không vừa tạo thủ công vừa yêu cầu công cụ tạo lại cùng slot.

## 11. Bootstrap standby bằng pg_basebackup

Standby cần một base backup nhất quán từ primary. pg_basebackup sử dụng replication protocol để lấy data files và có thể stream WAL trong lúc backup.

Ví dụ:

~~~bash
pg_basebackup \
  --host=primary.example.internal \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/17/standby \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf \
  --create-slot \
  --slot=standby_a
~~~

Cú pháp và option có thể khác theo client version. Chạy pg_basebackup --help và đọc tài liệu đúng major version.

Trước khi chạy:

- Data directory đích phải rỗng hoặc được chuẩn bị theo quy trình an toàn.
- User hệ điều hành sở hữu data directory phải đúng.
- Đủ disk cho base backup và WAL.
- Network/pg_hba cho phép replication connection.
- Role có quyền REPLICATION.
- Slot capacity và slot name đã được kiểm tra.
- Backup source là primary đúng cluster.

Không chạy pg_basebackup vào data directory đang được một PostgreSQL server sử dụng.

## 12. standby.signal và recovery configuration

Với PostgreSQL hiện đại, file standby.signal xác định data directory khởi động ở standby mode. Option --write-recovery-conf của pg_basebackup tạo standby.signal và ghi các connection settings cần thiết vào cấu hình.

Ví dụ:

~~~conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_a sslmode=verify-full'
primary_slot_name = 'standby_a'
recovery_target_timeline = 'latest'
restore_command = 'cp /archive/%f %p'
~~~

Các giá trị certificate, password và archive path phải được cấu hình an toàn. Tránh lưu password plaintext trong file có quyền truy cập rộng.

- primary_conninfo: kết nối tới upstream primary.
- application_name: tên standby hiển thị trên primary.
- primary_slot_name: physical replication slot.
- recovery_target_timeline = latest: theo dõi timeline mới nhất có thể phục hồi.
- restore_command: lấy WAL từ archive khi cần.

Với version cũ, recovery configuration có thể nằm trong recovery.conf; không trộn cú pháp cũ và mới. Xác minh tài liệu theo major version.

## 13. Khởi động và xác minh standby

Khởi động PostgreSQL bằng service manager/pg_ctl theo môi trường. Trên standby, xác nhận:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

Kết quả mong đợi:

- is_standby = true.
- Receive/replay LSN tiến triển khi primary tạo WAL.
- Standby không nhận writes thông thường.
- WAL receiver có trạng thái streaming.

Kiểm tra WAL receiver:

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

Columns có thể khác theo version. Nếu không có row, receiver có thể chưa kết nối, đã disconnect hoặc standby đang nhận WAL từ archive tại thời điểm truy vấn.

## 14. Xác minh từ primary

Trên primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

Mong đợi standby xuất hiện với:

- application_name đúng.
- state = streaming.
- sync_state phản ánh async/sync/quorum policy.
- LSN tiến triển theo workload.

Không coi một snapshot state = streaming là đủ. Quan sát nhiều mẫu và xác nhận LSN tiến lên.

## 15. Kiểm tra replication bằng test transaction

Trên primary, tạo bảng thử riêng nếu có quyền và change window phù hợp:

~~~sql
CREATE TABLE IF NOT EXISTS public.replication_smoke_test (
    id bigint PRIMARY KEY,
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.replication_smoke_test (id, message)
VALUES (1, 'replication-check')
ON CONFLICT (id) DO UPDATE
SET message = EXCLUDED.message,
    created_at = now();
~~~

Trên standby, đọc:

~~~sql
SELECT *
FROM public.replication_smoke_test
WHERE id = 1;
~~~

Standby hot standby cho phép read-only queries. Nếu query chưa thấy row, kiểm tra receive/replay LSN, replication connection, recovery conflicts và WAL logs. Không thực hiện INSERT/UPDATE trên standby.

Xóa test row từ primary sau khi hoàn thành theo policy. Ghi lại thời điểm commit và thời điểm row xuất hiện trên standby để ước lượng apply delay.

## 16. Physical replication là asynchronous hay synchronous?

Mặc định physical streaming replication thường là asynchronous nếu chưa cấu hình synchronous_standby_names.

**Asynchronous replication:** primary không phải chờ standby flush/replay WAL trước khi xác nhận commit. Hiệu năng commit tốt hơn, nhưng primary có thể mất các giao dịch đã commit gần nhất nếu failover sang standby chưa nhận đủ WAL.

**Synchronous replication:** commit có thể chờ một hoặc nhiều standby xác nhận WAL theo synchronous_commit và synchronous_standby_names. Durability được cải thiện nhưng commit latency và availability phụ thuộc standby/network.

| Tiêu chí | Asynchronous | Synchronous |
| --- | --- | --- |
| Commit latency | Thường thấp hơn | Có thêm network/standby wait |
| RPO khi primary mất đột ngột | Có thể lớn hơn 0 | Có thể gần 0 cho commits được xác nhận theo policy |
| Phụ thuộc standby | Ít hơn | Nhiều hơn |
| Availability khi standby mất | Primary vẫn commit | Có thể bị chặn tùy cấu hình |
| Complexity | Thấp hơn | Cần thiết kế quorum/failover |

Synchronous replication không tự bảo đảm zero data loss trong mọi topology/failure. Phải hiểu số standby cần ack, failure domains và cách failover manager chọn node.

## 17. Cấu hình synchronous replication

Ví dụ ưu tiên một synchronous standby:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

Ví dụ quorum: chờ bất kỳ một trong các standby được liệt kê:

~~~conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

Tên trong synchronous_standby_names phải khớp application_name mà standby gửi trong primary_conninfo.

Các mức synchronous_commit:

- off: không chờ local WAL flush cho mỗi commit; PostgreSQL vẫn bảo đảm crash consistency nhưng có thể mất giao dịch gần nhất khi OS/server crash.
- local: chờ local WAL flush, không chờ standby.
- remote_write: chờ synchronous standby ghi WAL tới OS, chưa nhất thiết flush bền vững xuống storage.
- on: chờ remote flush trên synchronous standby theo policy.
- remote_apply: chờ standby replay transaction, phù hợp khi cần read-after-write từ standby nhưng tăng latency.

on là lựa chọn phổ biến khi cần synchronous durability. Chọn remote_apply chỉ khi application thực sự cần transaction được replay trước khi commit trả về.

### Kiểm tra trạng thái sync

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

sync_state có thể là async, potential, sync hoặc quorum tùy cấu hình/version.

## 18. RPO và RTO

**RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất khi phục hồi sau sự cố.

**RTO (Recovery Time Objective):** thời gian tối đa để dịch vụ trở lại trạng thái chấp nhận được.

Với async replication, RPO phụ thuộc lượng WAL primary đã xác nhận cho client nhưng standby chưa nhận/flush trước sự cố.

Với synchronous replication, commits được xác nhận sau khi standby đáp ứng mức ack cấu hình có thể giảm RPO đáng kể. Tuy nhiên, cần xét:
- Có bao nhiêu standby sync.
- Commit level đang dùng.
- Failover có chọn đúng standby đã ack không.
- Standby và storage có failure domain độc lập không.
- Có thể xảy ra split-brain hay không.

RTO bao gồm detection, fencing, promotion, endpoint cutover, connection pool recovery và validation. Promote database chỉ là một phần của RTO.
## 19. Monitoring replication lag

Lag cần đo theo nhiều góc nhìn:

- Primary sent LSN.
- Standby write/flush/replay LSN.
- Slot restart_lsn và confirmed_flush_lsn.
- Time since last message.
- WAL retained bytes.
- Application read freshness.

Trên primary:

~~~sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_behind_replay,
    pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS bytes_behind_flush
FROM pg_stat_replication;
~~~

Trên standby:

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS received_not_replayed_bytes;
~~~

Các phép đo LSN cần lấy trong cùng thời điểm tương đối và hiểu đúng node. Bytes behind là khoảng cách vị trí WAL, không trực tiếp là số giây lag.

pg_last_xact_replay_timestamp() có thể cũ khi primary không có writes; không coi chênh lệch timestamp lớn là lag nếu workload đang idle. Kết hợp LSN, last message timestamps và workload heartbeat.

## 20. Monitoring replication slots và WAL capacity

Trên primary:

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
    END AS wal_distance
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Theo dõi disk free trên filesystem chứa pg_wal và archive. LSN distance chỉ là một chỉ báo, không phải phép đo trực tiếp file bytes do segment retention, checkpoint và các consumers khác.

Alert nên có:

- Standby disconnected.
- Replay lag vượt threshold.
- Slot inactive lâu.
- WAL distance tăng liên tục.
- safe_wal_size thấp hoặc slot invalidated.
- Archive failures.
- Disk free dưới reserve.
- Replication connection authentication errors.

Không drop slot tự động khi inactive. Xác định slot owner và recovery path trước.

## 21. Switchover và failover khác nhau

**Switchover** là chuyển vai trò có kế hoạch. Primary còn khỏe, có thể dừng writes có kiểm soát, chờ standby nhận/replay WAL tới điểm mục tiêu và chuyển vai trò không mất giao dịch đã drain.

**Failover** là chuyển vai trò khẩn cấp khi primary không thể tiếp tục phục vụ hoặc cần bị cô lập. Có thể không biết chính xác primary đã xác nhận những commits nào mà standby chưa nhận. Async replication có thể mất dữ liệu gần nhất.

| Tiêu chí | Switchover | Failover |
| --- | --- | --- |
| Primary cũ | Còn truy cập được | Có thể mất kết nối/hỏng |
| Writes | Có thể quiesce/drain | Có thể dừng đột ngột |
| WAL catch-up | Có thể chờ đến target LSN | Chọn standby có WAL mới nhất |
| RPO | Có thể đạt 0 nếu drain đúng | Phụ thuộc sync/async và WAL đã nhận |
| Fencing | Vẫn cần trước khi mở writes trên node mới | Bắt buộc trước promotion |
| Mục tiêu | Maintenance/rotation | Khôi phục dịch vụ |

Không dùng từ switchover cho một lần promote bất ngờ khi primary chưa được fencing và writes chưa được drain.

## 22. Điều kiện trước khi diễn tập

Một bài diễn tập phải có:

- Môi trường staging hoặc cluster drill được phê duyệt.
- Backup/PITR được xác minh.
- Primary/standby healthy.
- Replication lag nằm trong ngưỡng.
- WAL archive hoạt động.
- Application endpoint có thể chuyển đổi.
- Fencing mechanism đã được kiểm tra.
- Test workload và dữ liệu kiểm chứng.
- Stop conditions và rollback/recovery path.
- Ghi lại RPO/RTO mục tiêu.

Không diễn tập failover bằng cách kill primary production nếu chưa có change/incident authorization và HA procedure được duyệt.

## 23. Switchover có kế hoạch: tổng quan

Một switchover an toàn gồm:

1. Kiểm tra primary/standby health.
2. Xác nhận standby là candidate phù hợp.
3. Dừng nhận writes mới từ application.
4. Drain transactions và background writers theo plan.
5. Ghi nhận target LSN trên primary.
6. Chờ standby replay tới target LSN.
7. Fence/stop primary cũ.
8. Promote standby.
9. Xác nhận node mới không còn recovery mode.
10. Chuyển application endpoint.
11. Mở writes có kiểm soát.
12. Rebuild/rejoin node cũ làm standby.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant P as Old Primary
    participant S as Standby
    App->>P: Stop new writes
    App->>P: Drain active transactions
    P->>P: Record target LSN
    P->>S: Continue WAL streaming
    S->>S: Replay through target LSN
    P->>P: Fence / stop
    S->>S: Promote
    App->>S: Connect to new primary
    App->>S: Smoke write and verify
    P->>S: Rejoin old primary as standby
~~~

## 24. Switchover: kiểm tra candidate standby

Trên primary:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Trên standby:

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
~~~

Xác nhận:

- Standby streaming ổn định.
- Replay không bị pause ngoài ý muốn.
- Không có recovery conflicts nghiêm trọng.
- Disk còn đủ chỗ.
- Standby không bị quá tải bởi read workload.
- Archive/WAL availability đủ cho recovery.
- Node được chọn là candidate đã được HA policy phê duyệt.

Nếu có nhiều standby, chọn candidate theo replay/flush position và failure-domain policy, không chỉ chọn node có hostname dễ nhớ.

## 25. Switchover: quiesce và drain writes

Dừng writes từ mọi producer:

- Web/API.
- Background workers.
- Scheduled jobs.
- ETL/CDC control writes.
- Admin scripts.
- Batch jobs.
- Other services dùng trực tiếp database.

Dùng maintenance mode, traffic gate hoặc application-level write pause. Sau đó chờ transactions đang chạy kết thúc hoặc xử lý theo runbook.

Kiểm tra active transactions:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Không terminate mọi session một cách máy móc. Một transaction dài có thể là công việc quan trọng; xác định owner và cách drain.

## 26. Switchover: ghi nhận target LSN và chờ replay

Khi writes đã dừng và transactions đã drain, trên primary lấy target LSN:

~~~sql
SELECT pg_current_wal_lsn() AS switchover_target_lsn;
~~~

Ghi lại giá trị trả về. Trên standby, kiểm tra replay LSN:

~~~sql
SELECT
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_wal_receive_lsn() AS receive_lsn;
~~~

Chỉ tiếp tục khi replay LSN đạt hoặc vượt target LSN:

~~~sql
SELECT
    pg_last_wal_replay_lsn() >= '0/50000A0'::pg_lsn
        AS standby_replayed_target;
~~~

LSN ví dụ phải được thay bằng giá trị thực vừa ghi. Nếu standby chưa đạt target, chờ streaming/replay hoặc điều tra; không promote sớm khi mục tiêu là zero-loss planned switchover.

Một transaction commit cuối cùng có thể cần flush/replay WAL và standby có thể đang xử lý recovery. Xác minh trạng thái ổn định trước bước tiếp theo.

## 27. Switchover: dừng primary cũ và promote

Khi standby đã replay tới target, dừng primary cũ theo quy trình:

~~~bash
pg_ctl -D /path/to/old-primary-data stop -m fast
~~~

Hoặc dùng service manager của môi trường. Xác nhận node cũ đã dừng và được fencing khỏi application writes.

Sau đó trên standby, promote:

~~~sql
SELECT pg_promote(wait => true, wait_seconds => 60);
~~~

Có thể dùng:

~~~bash
pg_ctl -D /path/to/standby-data promote
~~~

Chỉ dùng một phương thức promotion phù hợp. Nếu HA manager như Patroni hoặc repmgr đang quản lý cluster, dùng workflow của manager; không promote thủ công ngoài state machine của nó.

Xác minh trên node mới:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_current_wal_lsn() AS current_lsn,
    pg_postmaster_start_time();
~~~

Mong đợi is_standby = false. Node mới đã trở thành primary về mặt PostgreSQL, nhưng chưa nên mở toàn bộ traffic trước khi endpoint, role, archive và replication được xác minh.

## 28. Failover khẩn cấp: nguyên tắc chọn node

Khi primary mất khả năng phục vụ:

1. Xác định primary thật sự down hay chỉ network-partitioned.
2. Fence primary cũ bằng cơ chế hạ tầng.
3. Inventory tất cả standbys.
4. Chọn standby có WAL receive/flush/replay position mới nhất có thể xác minh.
5. Đánh giá data loss theo replication mode.
6. Ghi nhận decision maker và thời điểm.
7. Promote duy nhất một candidate.
8. Chuyển application endpoint.
9. Khởi động lại replication topology.

Không promote một standby chỉ vì nó reachable trong khi primary cũ có thể vẫn nhận writes ở network segment khác.

### Fencing có thể gồm

- Power off node qua hypervisor/cloud API.
- STONITH qua cluster manager.
- Isolate network/storage để node cũ không thể nhận writes.
- Stop PostgreSQL và disable service restart.
- Revoke route/VIP/credentials theo HA design.

Fencing phải được chứng minh bằng hạ tầng. Chỉ đổi DNS hoặc load balancer backend không đảm bảo primary cũ không thể được client khác truy cập trực tiếp.

## 29. Failover: xác định khả năng mất dữ liệu

Với asynchronous replication, primary có thể đã trả COMMIT cho client nhưng WAL tương ứng chưa tới standby được chọn.

Thu thập:

- Last confirmed application commit nếu có audit.
- Primary last known LSN/metrics.
- Standby receive/flush/replay LSN.
- Last heartbeat/event watermark.
- Replication lag trước sự cố.
- Broker/CDC offsets nếu downstream liên quan.

Không thể biết chính xác data loss chỉ từ pg_last_xact_replay_timestamp() khi workload idle hoặc clocks lệch. Dùng LSN metrics và application-level commit markers.

Nếu primary không thể truy cập, last primary LSN có thể không biết chính xác. Ghi nhận RPO thực tế là estimate hoặc unknown, không bịa một giá trị.

## 30. Failover: fence rồi promote

Sau khi xác nhận primary cũ đã bị fencing, trên standby candidate:

~~~sql
SELECT pg_promote(wait => true, wait_seconds => 60);
~~~

Xác minh:

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_current_wal_lsn(),
    pg_postmaster_start_time();
~~~

Mong đợi pg_is_in_recovery() = false.

Kiểm tra logs để xác nhận promotion/timeline switch hoàn tất. Không chạy pg_promote trên nhiều standby đồng thời. Chỉ một candidate được quyền trở thành primary.

## 31. Timeline sau promotion

Mỗi lần standby được promote, PostgreSQL tạo timeline mới. Timeline history mô tả nhánh WAL mới bắt đầu từ đâu.

Kiểm tra timeline và WAL state bằng:

~~~bash
pg_controldata /path/to/new-primary-data
~~~

Và xem WAL files/history theo đúng version/tool.

Standby còn lại cần theo timeline mới. Với cấu hình recovery_target_timeline = latest, standby có thể theo timeline mới nếu WAL history/segments cần thiết có sẵn.

Timeline là một phần của WAL recovery model; không xóa history files hoặc WAL segments bằng tay.

## 32. Chuyển application endpoint

Sau khi node mới được promote và xác minh:

- Cập nhật VIP/load balancer/service discovery/DNS theo HA architecture.
- Chuyển connection pool sang endpoint mới.
- Đóng hoặc recycle connections cũ.
- Khôi phục write traffic theo canary.
- Kiểm tra transaction commits.
- Kiểm tra background workers và scheduled jobs.
- Kiểm tra read routing nếu có replicas.

DNS TTL có thể khiến một số clients giữ IP cũ. Connection pool có thể giữ socket lâu hơn TTL. Có thể cần explicit pool recycle hoặc proxy failover.

Không chỉ kiểm tra một application instance. Xác nhận tất cả services, scripts và integrations sử dụng endpoint mới.

## 33. Smoke test sau promotion

Sau khi mở một phần traffic, chạy kiểm tra có kiểm soát:

~~~sql
SELECT
    current_database(),
    current_user,
    pg_is_in_recovery(),
    pg_current_wal_lsn();
~~~

Thử transaction nhỏ có marker duy nhất:

~~~sql
CREATE TABLE IF NOT EXISTS public.ha_drill_marker (
    drill_id text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    note text NOT NULL
);

INSERT INTO public.ha_drill_marker (drill_id, note)
VALUES ('drill-2026-11-14-a', 'post-promotion-write-check')
ON CONFLICT (drill_id) DO UPDATE
SET created_at = now(),
    note = EXCLUDED.note;
~~~

Xác minh marker đọc lại được và application role có đúng quyền. Dùng tên bảng/marker phù hợp drill environment; tránh tạo object test trong production nếu chưa được phê duyệt.

Kiểm tra:
- Application connection success.
- Read/write path.
- Error rate và latency.
- Transaction commits.
- Sequence/identity behavior.
- Roles/grants.
- Background jobs.
- Replication/archiving.
- CDC/downstream health.

## 34. Rebuild replication topology sau failover

Sau promotion, node mới là primary. Standby cũ có thể cần cấu hình upstream mới. Primary cũ có thể đã diverge và không thể đơn giản khởi động lại như standby.

Các bước:

1. Xác định node nào được giữ làm standby.
2. Fence primary cũ nếu chưa.
3. Kiểm tra node cũ có thể rewind hay cần base backup.
4. Tạo/recreate physical replication slot trên new primary.
5. Cấu hình primary_conninfo trỏ tới new primary.
6. Cấu hình primary_slot_name nếu dùng slot.
7. Đảm bảo standby.signal tồn tại.
8. Start standby.
9. Xác minh WAL receiver và replay.
10. Theo dõi lag và archive.

Không khởi động node cũ như writable primary. Nó có thể chứa một timeline khác.

## 35. Dùng pg_rewind để rejoin primary cũ

pg_rewind có thể đưa một data directory đã diverge trở lại cùng timeline history với source mới, khi thỏa điều kiện. Nó không phải phép merge hai primary histories.

Điều kiện quan trọng thường gồm:

- Target cluster đã shutdown sạch.
- Source và target có common ancestor timeline.
- Target đã bật data checksums hoặc wal_log_hints từ trước khi divergence.
- full_page_writes được bật.
- WAL cần thiết từ divergence point còn có trong pg_wal hoặc có thể lấy qua archive theo cấu hình.
- PostgreSQL binaries tương thích.

Xác minh prerequisites theo tài liệu version trước khi chạy.

Ví dụ lệnh khái niệm:

~~~bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/17/old-primary \
  --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user" \
  --write-recovery-conf
~~~

Các option/role requirements phụ thuộc version. Source connection cần quyền đọc thông tin phù hợp; credential không nên ghi plaintext vào shell history.

Sau pg_rewind, kiểm tra recovery configuration, primary_conninfo, slot, permissions và standby.signal. Nếu pg_rewind không đáp ứng điều kiện hoặc thiếu WAL, tạo standby mới bằng pg_basebackup thường an toàn và dễ chứng minh hơn.

## 36. Khi nào phải rebuild bằng pg_basebackup?

Dùng base backup mới khi:

- Không có common timeline history phù hợp.
- Target không được chuẩn bị wal_log_hints/checksums từ trước.
- WAL cần thiết đã bị mất.
- Target data directory không thể shutdown sạch.
- pg_rewind báo lỗi không thể phục hồi.
- Data directory có corruption/uncertainty.
- Cần cách phục hồi đơn giản, có thể kiểm chứng.

Không cố chạy pg_rewind nhiều lần bằng cách thay flags để bỏ qua prerequisite. Nếu tool không thể chứng minh target/source relationship, rebuild từ primary mới.

## 37. Replication slots sau promotion

Replication slots gắn với cluster và cần được kiểm tra sau failover. Không giả định mọi physical/logical slots sẽ tự xuất hiện và hoạt động giống trước promotion trên mọi PostgreSQL version/topology.

Inventory trên primary mới:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Tạo slot cho standby/consumer theo owner và runbook. Với logical CDC, đánh giá failover slot support và synchronized standby slots nếu PostgreSQL version/connector hỗ trợ. Nếu slot không thể tiếp tục, connector có thể cần snapshot/rebootstrap/reconciliation.

Không drop các logical slots còn được consumer sử dụng. Xác định owner, retention và WAL capacity trước khi cleanup.

## 38. Synchronous replication và failover behavior

Synchronous configuration ảnh hưởng cả durability và availability.

Nếu cấu hình yêu cầu một synchronous standby nhưng standby mất kết nối, commits có thể chờ cho đến khi có synchronous standby khác hoặc policy thay đổi. Một số workload có thể bị block.

Trước drill, xác định:

- synchronous_standby_names.
- synchronous_commit ở database/role/session.
- Standby application_name.
- FIRST vs ANY quorum.
- Số node đủ điều kiện.
- Behavior khi một/all synchronous standbys down.
- Failover manager có promote đúng node đã xác nhận commit không.

Không giảm synchronous_commit để “làm hệ thống chạy lại” mà không hiểu RPO mới và ghi nhận change. Thay đổi durability policy cần owner approval.

## 39. Cascading replication

Một standby có thể làm upstream cho standby khác (cascading replication). Cấu hình này giảm số WAL sender connections trên primary hoặc đưa replication tới site xa.

Rủi ro:

- Lag tích lũy qua nhiều hops.
- Upstream standby down làm downstream mất WAL stream.
- Promotion cần xác định timeline/ancestry.
- Monitoring phải đo từng hop.
- Slot/WAL retention ở upstream cần capacity.

Không chọn cascading node làm failover candidate chỉ dựa trên reachability. Xác nhận nó đã nhận/replay đủ WAL và có timeline hợp lệ.

## 40. Dùng HA manager hay thao tác thủ công?

Trong production, thường nên dùng một hệ thống HA có state management như Patroni, repmgr, Pacemaker/Corosync hoặc managed database failover service, tùy platform.

HA manager có thể điều phối:

- Leader election.
- Health checks.
- Fencing.
- Promotion.
- Endpoint/VIP changes.
- Rejoin/rebuild.
- Replication configuration.
- Failover history.

Các công cụ có semantics và prerequisites khác nhau. Đọc runbook riêng và chọn một hệ thống làm authority duy nhất.

Không kết hợp manual pg_promote với manager đang chạy nếu không theo procedure của manager. Có thể tạo hai leaders hoặc state mismatch.

## 41. Split-brain: nguyên nhân và hậu quả

Split-brain xảy ra khi hai node cùng được coi là primary và nhận writes độc lập.

Nguyên nhân thường gặp:

- Network partition khiến node cũ không thấy standby nhưng vẫn phục vụ clients.
- Promote standby trước khi fence primary cũ.
- Hai HA managers cùng điều khiển cluster.
- VIP/DNS thay đổi nhưng direct connections vẫn tới old primary.
- Fencing thất bại hoặc chưa xác nhận.
- Operator chạy promote trên nhiều node.

Hậu quả:

- Hai WAL timelines diverge.
- Không thể ghép các writes một cách tự động.
- Data loss hoặc business conflict.
- Khó xác định nguồn sự thật.
- Recovery có thể cần chọn một branch và reconcile writes từ branch còn lại.

Biện pháp:
- Single leader authority.
- Reliable fencing/STONITH.
- Quorum/lease policy phù hợp.
- Endpoint control và direct access restrictions.
- Promotion authorization.
- Runbook rõ và drill định kỳ.

DNS hoặc application config chỉ điều hướng client; nó không thay thế fencing.

## 42. Diễn tập planned switchover trong staging

Một drill có thể dùng checklist:

### Chuẩn bị

- Xác nhận primary/standby healthy.
- Ghi LSN và replication lag baseline.
- Xác nhận backup/restore.
- Bật application write pause.
- Ghi start time.
- Xác nhận endpoint cutover procedure.
- Chuẩn bị test transaction marker.

### Thực hiện

1. Dừng writes mới.
2. Drain transactions.
3. Ghi target LSN trên primary.
4. Chờ standby replay target.
5. Stop/fence primary cũ.
6. Promote standby.
7. Chuyển endpoint.
8. Mở canary writes.
9. Verify marker và application.
10. Rejoin old primary thành standby.

### Kết quả

Ghi:
- Thời gian detection/preparation.
- Thời gian drain.
- Thời gian promotion.
- Thời gian endpoint cutover.
- Thời gian tới first successful write.
- RPO thực tế.
- RTO thực tế.
- Replication lag sau rejoin.
- Issues và follow-up.

## 43. Diễn tập unplanned failover trong staging

Drill failover cần mô phỏng node failure có kiểm soát, chẳng hạn stop PostgreSQL service hoặc isolate host/network trong test environment.

Không dùng kill -9 như phương pháp duy nhất để mô phỏng mọi failure; nó chỉ mô phỏng một lớp crash. Có thể cần drill riêng cho host loss, network partition, storage failure và availability-zone outage.

Quy trình:

1. Bắt đầu workload ghi có marker/sequence.
2. Ghi replication lag và last acknowledged commit.
3. Simulate primary outage.
4. Thực hiện fencing.
5. Chọn standby đủ mới.
6. Ghi nhận WAL/replay position.
7. Promote một node.
8. Chuyển endpoint.
9. Xác minh application.
10. Đối chiếu các marker/transactions.
11. Rebuild old primary.
12. Khôi phục topology.
13. Tính RPO/RTO thực tế.

Nếu primary mất đột ngột trong async mode, một số commits có thể chưa tới standby. Đừng đánh dấu drill zero-loss nếu không chứng minh được bằng commit markers.

## 44. Kiểm tra data consistency sau failover

Các kiểm tra nên bao gồm:

- Primary/standby role state.
- Database identity và timeline.
- Critical row counts/aggregates.
- Last committed business marker.
- Sequence/identity values.
- Constraints và index validity.
- Replication catch-up.
- Application write/read tests.
- CDC event completeness.
- Downstream reconciliation.

Ví dụ business watermark:

~~~sql
SELECT
    max(event_sequence) AS latest_sequence,
    count(*) AS event_count
FROM public.integration_events;
~~~

Đối chiếu với producer/consumer watermark. Một aggregate count khớp không chứng minh mọi row khớp; với dữ liệu quan trọng, so sánh theo key ranges/chunks hoặc checksums.

## 45. Backup và PITR trước/sau role transition

Physical standby không phải backup độc lập. Nếu dữ liệu bị xóa nhầm trên primary, thay đổi có thể được replay sang standby.

Cần có:
- Base backups.
- WAL archive liên tục.
- Restore test.
- Retention phù hợp.
- Offsite/independent storage.
- Encryption keys.
- Runbook PITR.
- Snapshot của config/package inventory.
- Plan cho writes phát sinh sau cutover.

Backup trước upgrade là baseline recovery, nhưng nếu target đã nhận writes, quay lại backup cũ sẽ mất các writes đó trừ khi có reverse sync/replay strategy.

Sau promotion, kiểm tra archive_command/archive service trên primary mới. Nếu archive destination hoặc timeline handling sai, PITR chain có thể bị gián đoạn.

WAL archive phải giữ timeline history files. Không xóa segment theo filename/time đơn giản mà bỏ qua archive retention policy.

## 46. Security và access control cho replication

Replication mở một kênh truy cập dữ liệu toàn cluster. Bảo vệ:

- Dedicated replication role.
- TLS/mTLS theo policy.
- pg_hba.conf giới hạn source.
- Network ACL/security groups.
- Secret manager và rotation.
- OS file permissions.
- Archive encryption/access controls.
- Audit connection attempts.
- HA manager credentials.
- Fencing API permissions.

Không dùng superuser cho replication role nếu không có lý do kỹ thuật được xác minh. Tách quyền operator được phép promote khỏi quyền application runtime.

## 47. Monitoring dashboard cho HA

Dashboard nên bao gồm:

| Nhóm | Metrics |
| --- | --- |
| Role | Current primary, standby state, timeline |
| Connectivity | WAL receiver status, sender count, connection errors |
| Progress | Sent/write/flush/replay LSN |
| Lag | Bytes behind, time since last message, replay delay |
| Slots | Active, restart_lsn, retained WAL, safe_wal_size |
| Archive | Archived/failed count, last archived time |
| Storage | Data/WAL/archive free space |
| Workload | Connections, latency, errors, transactions/sec |
| Recovery | Last backup, restore test, PITR coverage |
| HA manager | Leader, quorum, fencing, failover events |
| Application | Endpoint, pool errors, successful writes |
| Drill | Last switchover/failover, RPO/RTO achieved |

Alert phải có owner và action. Ví dụ: standby disconnected thì kiểm tra network/receiver; retained WAL tăng thì kiểm tra slot; replay lag tăng thì kiểm tra I/O/recovery conflicts.

## 48. Stop conditions trong drill

Dừng drill hoặc không promote khi:

- Không xác định được primary thật sự.
- Fencing chưa được chứng minh.
- Có nhiều candidate nhưng không biết node nào có WAL mới nhất.
- Standby không có WAL/slot/archive cần thiết.
- Disk/WAL capacity không đủ.
- Backup/PITR không khả dụng với drill có rủi ro cao.
- HA manager state không rõ.
- Endpoint có thể tiếp tục gửi writes tới old primary.
- Data consistency check thất bại.
- Người điều phối không thể xác định RPO/data loss risk.

Trong production incident, có thể phải chọn phương án ít xấu nhất để khôi phục dịch vụ; khi đó ghi rõ unknowns và data reconciliation plan thay vì giả vờ các điều kiện đã đạt.

## 49. Runbook: primary mất kết nối nhưng chưa biết đã down hay chưa

Đây là tình huống nguy hiểm vì network partition có thể khiến standby không thấy primary trong khi primary vẫn nhận writes từ một số clients.

1. Kiểm tra health từ nhiều network paths.
2. Kiểm tra host/cloud control plane.
3. Kiểm tra application connections tới primary cũ.
4. Kiểm tra HA manager quorum/lease.
5. Fence primary cũ.
6. Xác nhận fencing state.
7. Chọn candidate và promote.
8. Chặn direct connections tới node cũ.
9. Chỉ mở endpoint mới sau xác minh.
10. Giữ old node isolated cho tới khi quyết định rejoin.

Không dùng ping failure đơn lẻ làm bằng chứng node đã tắt.

## 50. Runbook: standby không bắt kịp

1. Kiểm tra pg_stat_wal_receiver.
2. Kiểm tra network và authentication.
3. Kiểm tra primary pg_stat_replication.
4. Kiểm tra standby receive/replay LSN.
5. Kiểm tra recovery conflicts và long-running queries.
6. Kiểm tra WAL slot active/restart_lsn.
7. Kiểm tra WAL archive và restore_command.
8. Kiểm tra disk/I/O trên cả hai node.
9. Xác định WAL cần thiết còn tồn tại không.
10. Nếu WAL bị mất, rebuild standby bằng base backup theo plan.

Không xóa slot hoặc pg_wal files để giải quyết lag.

## 51. Runbook: old primary rejoin thất bại

1. Giữ old primary fenced.
2. Xác nhận target đã shutdown sạch.
3. Xác minh source/target timeline history.
4. Kiểm tra data checksums hoặc wal_log_hints prerequisite.
5. Kiểm tra full_page_writes.
6. Xác minh WAL từ divergence point.
7. Chạy pg_rewind theo version docs.
8. Nếu không đạt prerequisites, bỏ qua rewind và tạo base backup mới.
9. Kiểm tra standby.signal/primary_conninfo/slot.
10. Start và xác minh pg_stat_wal_receiver.
11. Theo dõi replay lag.
12. Chỉ mở node cho read traffic sau khi recovery state được xác nhận.

Không khởi động old primary như writable node để “xem còn dữ liệu không”.

## 52. Checklist trước, trong và sau switchover

### Trước

- [ ] Xác nhận primary/standby identity.
- [ ] Version và configuration tương thích.
- [ ] Standby streaming/replay khỏe.
- [ ] Replication lag trong ngưỡng.
- [ ] WAL archive và slots khỏe.
- [ ] Backup/PITR readiness.
- [ ] Application endpoint cutover plan.
- [ ] Fencing plan đã kiểm chứng.
- [ ] RPO/RTO mục tiêu rõ.
- [ ] Owner và incident commander rõ.

### Trong

- [ ] Dừng writes mới.
- [ ] Drain transactions (planned).
- [ ] Ghi target LSN.
- [ ] Chờ replay target.
- [ ] Fence primary cũ.
- [ ] Promote duy nhất một standby.
- [ ] Xác nhận pg_is_in_recovery() = false.
- [ ] Chuyển endpoint.
- [ ] Mở canary traffic.
- [ ] Ghi timeline và timestamps.

### Sau

- [ ] Application read/write smoke tests.
- [ ] Data marker/reconciliation.
- [ ] Roles/grants/sequence checks.
- [ ] WAL archive trên primary mới.
- [ ] Standby slots và receiver.
- [ ] Old primary rewind/rebuild.
- [ ] Replication lag trong ngưỡng.
- [ ] CDC/downstream consumers healthy.
- [ ] Backup/PITR verified.
- [ ] RPO/RTO thực tế được ghi.
- [ ] Evidence và sign-off đầy đủ.

## 53. Những sai lầm thường gặp

1. **Promote standby trước khi fence primary cũ**, tạo split-brain.
2. **Coi DNS/VIP update là fencing**, trong khi old primary vẫn có thể nhận direct writes.
3. **Chọn standby chỉ theo hostname/reachability**, bỏ qua replay LSN.
4. **Coi asynchronous replication là zero data loss**, không đánh giá WAL chưa tới standby.
5. **Cấu hình synchronous replication nhưng không hiểu commit blocking**, gây outage khi standby/network mất.
6. **Dùng application_name không khớp synchronous_standby_names**, standby không được chọn như mong đợi.
7. **Bỏ quên replication slots**, làm pg_wal đầy.
8. **Đặt max_slot_wal_keep_size quá thấp**, slot bị invalidated trước khi consumer bắt kịp.
9. **Dùng wal_keep_size thay cho slot/archive strategy**, không bảo đảm WAL retention.
10. **Chạy pg_basebackup vào data directory đang dùng**, làm hỏng node.
11. **Không xác minh pg_basebackup version/option**, dùng cú pháp hoặc behavior sai.
12. **Quên standby.signal hoặc primary_conninfo**, node khởi động như primary hoặc không kết nối upstream.
13. **Đặt password plaintext trong config/log**, lộ credential replication.
14. **Chỉ nhìn last replay timestamp khi cluster idle**, kết luận lag sai.
15. **Coi LSN byte distance là seconds lag**, nhầm đơn vị.
16. **Promote nhiều standby**, tạo nhiều primary candidates.
17. **Mix manual promotion với Patroni/repmgr**, làm state manager mất đồng bộ.
18. **Khởi động lại old primary sau failover như writable node**, tạo diverged writes.
19. **Dùng pg_rewind khi thiếu prerequisites**, làm recovery thất bại.
20. **Không rebuild standby khi rewind không phù hợp**, kéo dài outage.
21. **Không tạo lại slots trên primary mới**, standby/CDC không tiếp tục được.
22. **Không kiểm tra archive timeline history**, PITR chain bị gián đoạn.
23. **Chuyển endpoint nhưng quên connection pools/workers**, clients vẫn ghi vào node cũ.
24. **Không kiểm tra sequence sau cutover**, gặp duplicate key.
25. **Không reconcile data sau async failover**, bỏ sót commits bị mất.
26. **Coi physical standby là backup**, không thể phục hồi logical deletion.
27. **Không diễn tập network partition**, chỉ thử stop service đơn giản.
28. **Không ghi RPO/RTO thực tế**, không biết HA đáp ứng mục tiêu hay không.

## 54. Bài tập thực hành có đáp án

### Bài 1. Primary và standby khác nhau thế nào?

**Đáp án:** Primary nhận writes và tạo WAL; standby nhận/replay WAL và thường chỉ phục vụ read-only queries khi hot standby.

### Bài 2. Physical streaming replication truyền gì?

**Đáp án:** WAL ở mức vật lý cho toàn cluster, không phải chỉ rows trong một publication.

### Bài 3. wal_level cần gì cho physical replication?

**Đáp án:** Thông thường replica là đủ; logical cũng bao gồm khả năng physical replication.

### Bài 4. Replication role cần attribute nào?

**Đáp án:** LOGIN và REPLICATION, cùng grants/network policy tối thiểu cần thiết.

### Bài 5. pg_hba.conf rule hostssl có ý nghĩa gì?

**Đáp án:** Chỉ cho phép kết nối SSL phù hợp với address/user/database hoặc replication target đã khai báo.

### Bài 6. pg_basebackup dùng để làm gì?

**Đáp án:** Tạo base backup nhất quán từ primary để bootstrap standby hoặc backup physical.

### Bài 7. Option -R của pg_basebackup làm gì?

**Đáp án:** Tạo standby.signal và ghi recovery connection settings theo behavior của version.

### Bài 8. standby.signal biểu thị điều gì?

**Đáp án:** Data directory khởi động trong standby/recovery mode trên PostgreSQL hiện đại.

### Bài 9. Replication slot giữ gì?

**Đáp án:** WAL cần thiết cho consumer và replication progress state.

### Bài 10. pg_stat_replication xem gì?

**Đáp án:** WAL sender/standby connection state và LSN/lag fields trên primary.

### Bài 11. pg_stat_wal_receiver xem gì?

**Đáp án:** Trạng thái WAL receiver và upstream connection trên standby.

### Bài 12. pg_is_in_recovery() trả false có nghĩa gì?

**Đáp án:** Node không còn ở recovery/standby mode và đang hoạt động như primary về mặt PostgreSQL.

### Bài 13. Async replication có thể mất dữ liệu khi failover không?

**Đáp án:** Có; primary có thể đã xác nhận commits chưa được standby nhận/flush.

### Bài 14. Synchronous replication cải thiện điều gì?

**Đáp án:** Chờ standby xác nhận WAL theo commit policy, giảm nguy cơ mất commits đã được xác nhận.

### Bài 15. synchronous_commit = remote_apply khác on thế nào?

**Đáp án:** remote_apply chờ transaction được replay trên standby; on chờ remote flush theo synchronous replication semantics.

### Bài 16. RPO là gì?

**Đáp án:** Mục tiêu về lượng dữ liệu tối đa có thể mất khi phục hồi.

### Bài 17. RTO là gì?

**Đáp án:** Mục tiêu về thời gian tối đa để khôi phục dịch vụ.

### Bài 18. Switchover khác failover thế nào?

**Đáp án:** Switchover có kế hoạch và có thể drain writes; failover là chuyển đổi khẩn cấp khi primary mất khả năng phục vụ.

### Bài 19. Vì sao cần ghi target LSN trong switchover?

**Đáp án:** Để chứng minh standby đã replay tới tất cả WAL cần thiết trước promotion.

### Bài 20. Vì sao fencing bắt buộc trong failover?

**Đáp án:** Để primary cũ không thể tiếp tục nhận writes và tạo split-brain.

### Bài 21. pg_promote dùng để làm gì?

**Đáp án:** Promote standby thành primary.

### Bài 22. Promotion tạo timeline mới không?

**Đáp án:** Có; PostgreSQL chuyển sang timeline mới để ghi nhánh WAL mới.

### Bài 23. Vì sao phải xử lý connection pools sau endpoint cutover?

**Đáp án:** Existing connections có thể tiếp tục trỏ tới node cũ dù DNS/VIP đã đổi.

### Bài 24. pg_rewind dùng khi nào?

**Đáp án:** Đưa một target cluster đã diverge trở lại timeline của source khi common history và prerequisites phù hợp.

### Bài 25. pg_rewind cần prerequisites nào quan trọng?

**Đáp án:** Target shutdown sạch, common timeline history, data checksums hoặc wal_log_hints từ trước divergence, full_page_writes và WAL cần thiết.

### Bài 26. Khi nào nên dùng pg_basebackup thay pg_rewind?

**Đáp án:** Khi thiếu prerequisites, WAL cần thiết không còn, timeline không phù hợp hoặc target state không đáng tin.

### Bài 27. Physical standby có thay backup không?

**Đáp án:** Không; lỗi logical như DELETE nhầm có thể được replay sang standby.

### Bài 28. Vì sao phải kiểm tra archive sau promotion?

**Đáp án:** Primary mới cần tiếp tục tạo/archive WAL để bảo vệ PITR và các standby/consumers.

### Bài 29. Split-brain là gì?

**Đáp án:** Hai node cùng hoạt động như primary và nhận các writes độc lập.

### Bài 30. Một drill HA cần ghi kết quả gì?

**Đáp án:** RPO/RTO thực tế, timeline, replication lag, promotion time, endpoint recovery, data checks và issues.

## 55. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html) — streaming replication, standby và archive recovery.
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION) — cấu hình primary/standby.
- [Log-Shipping Standby Servers](https://www.postgresql.org/docs/current/warm-standby.html#STANDBY-SERVER-OPERATION) — recovery/standby behavior.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — bootstrap physical standby.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html) — rejoin diverged cluster.
- [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html) — start, stop và promote server.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — WAL sender, slots và synchronous standby settings.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — WAL behavior và durability.
- [Replication Monitoring](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_replication, pg_stat_wal_receiver và slots.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — REPLICATION role attribute.
- [pg_hba.conf](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html) — client authentication rules.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backup, WAL archive và recovery.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — synchronous commit semantics.
- [Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — recovery_target_timeline và related settings.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html) — cluster identity/checkpoint metadata.

Các URL /current/ mô tả tài liệu hiện hành. Option pg_basebackup/pg_rewind, slot failover support, view columns, configuration parameters và HA manager behavior có thể khác theo PostgreSQL major version và platform. Đọc tài liệu đúng version và công cụ HA đang quản lý cluster trước khi thực hiện production failover.

## 56. Tổng kết

**Primary/standby chỉ tạo thành HA khi replication được giám sát, promotion có fencing và ứng dụng có thể chuyển endpoint an toàn.** Streaming replication giữ standby gần primary; WAL archive hỗ trợ catch-up/PITR; switchover và failover cần các quy trình khác nhau.

1. **Bootstrap standby bằng base backup nhất quán.** Cấu hình role, HBA, WAL sender, slot và standby recovery settings.
2. **Xác minh receive và replay.** Dùng pg_stat_replication, pg_stat_wal_receiver và LSN metrics.
3. **Thiết kế sync/async theo RPO/RTO.** Synchronous giảm rủi ro mất commits đã xác nhận nhưng có thể tăng latency và giảm availability.
4. **Theo dõi slot, archive và disk.** Standby disconnected hoặc slot inactive có thể làm WAL tăng và đầy filesystem.
5. **Switchover cần drain writes và chờ target LSN.** Đây là cơ hội chuyển đổi có kiểm soát.
6. **Failover cần fencing trước promotion.** Không mở writes trên node mới khi primary cũ còn có thể nhận writes.
7. **Promote đúng một candidate.** Xác minh pg_is_in_recovery() và timeline sau promotion.
8. **Chuyển endpoint và recycle connection pools.** Kiểm tra cả web, workers, jobs và integrations.
9. **Rejoin old primary bằng pg_rewind khi đủ điều kiện.** Nếu không, rebuild bằng pg_basebackup.
10. **Kiểm tra slots và archive trên primary mới.** Recreate/reconfigure consumers theo ownership và recovery policy.
11. **Physical standby không thay backup/PITR.** Cần restore tests và independent backup.
12. **Diễn tập thường xuyên và ghi RPO/RTO thực tế.** Chỉ số đạt được trong drill mới cho biết HA design có đáp ứng mục tiêu.

Một HA drill thành công không chỉ là promote được standby. Nó phải chứng minh không có hai primary cùng nhận writes, ứng dụng quay lại phục vụ trong thời gian mục tiêu, dữ liệu nằm trong RPO đã cam kết và topology có thể được dựng lại sau chuyển đổi.
