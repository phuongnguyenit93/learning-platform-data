# Nâng cấp primary, standby và công cụ sao lưu theo thứ tự phù hợp

`pg_upgrade` là công cụ PostgreSQL hỗ trợ chuyển dữ liệu giữa các major versions; logical replication và dump/restore là hai lựa chọn khác. Khi cluster có primary, physical standbys và hệ thống backup, nâng cấp phải được lập kế hoạch cho toàn bộ chuỗi vận hành. Primary, standbys, replication slots, WAL archive, backup repository, backup agents và công cụ restore phải hiểu cùng một trạng thái cluster sau cutover.

Một con số version mới trên primary không có nghĩa các standby cũ có thể tiếp tục replay WAL. Physical replication dùng WAL và block layout ở mức vật lý; sau major upgrade, phải chuyển standby sang cluster mới bằng quy trình tương ứng. Backup tooling cũng cần được nâng và xác nhận tương thích trước khi thay đổi database để vẫn bảo vệ được cả old cluster lẫn target cluster.

```text
                 Backup repository
                        ^
                        | backup / WAL archive
                        |
       +----------------+----------------+
       |                                 |
       v                                 v
  +-----------+    physical WAL     +-----------+
  | Primary   | ------------------> | Standby 1 |
  | old/new   |                     | old/new   |
  +-----------+                     +-----------+
       |
       | logical changes (optional major upgrade path)
       v
  +-----------+
  | New       |
  | subscriber|
  +-----------+

  Backup tooling, repository metadata and restore binaries
  must be compatible with the cluster version being protected.
```

Bài thuộc chương **Nâng cấp** của module *Database Engine Relational PostgreSQL*. Trọng tâm là lập thứ tự thao tác để bảo vệ khả năng phục hồi, giữ HA trong giới hạn downtime đã chọn và tránh tạo ra primary/standby hoặc backup repository không tương thích.

Sau bài học, bạn có thể:

1. Phân biệt minor update và major upgrade.
2. Hiểu vì sao physical replication yêu cầu các node cùng major version và cùng cluster identity.
3. Lập inventory cho primary, standbys, replication slots, extensions và backup tools.
4. Nâng backup tooling và xác nhận khả năng restore trước khi thay đổi database.
5. Chọn giữa `pg_upgrade`, logical replication và dump/restore.
6. Thực hiện đúng thứ tự nâng primary và physical standbys.
7. Biết khi nào dùng rsync link-mode procedure và khi nào dựng lại standby bằng base backup.
8. Đồng bộ WAL archive, backup metadata, repository configuration và restore tools.
9. Kiểm tra replication, backup, restore, application behavior và performance sau cutover.
10. Xây dựng rollback plan có giới hạn rõ ràng và biết thời điểm không thể quay lại cluster cũ.

> **Nguyên tắc vận hành:** Trước khi nâng cấp, phải có backup có thể restore và một lần restore thử nghiệm gần đây. Không xóa old data directory, old binaries, old backup chain hoặc WAL archive cần cho recovery cho tới khi đã xác nhận cluster mới hoạt động và backup mới có thể restore.

---

## 1. Hiểu phạm vi nâng cấp

### 1.1. Minor release và major release

PostgreSQL minor release sửa lỗi, bảo mật và các vấn đề tương thích trong cùng major version. Minor releases giữ nguyên internal storage format; thông thường có thể thay binaries bằng bản minor mới rồi restart server theo kế hoạch. Primary và standbys vẫn thuộc cùng major version.

Major release có thể thay đổi catalog, internal storage format, WAL behavior, planner, replication features và extension APIs. Không thể chỉ thay binaries rồi mở data directory cũ bằng major version mới. Cần một phương pháp migration được hỗ trợ.

Ví dụ:

| Thay đổi | Loại | Cách tiếp cận |
|---|---|---|
| PostgreSQL 17.2 lên 17.6 | Minor update | Nâng binaries và restart theo quy trình HA |
| PostgreSQL 16 lên 17 | Major upgrade | `pg_upgrade`, logical replication hoặc dump/restore |
| pgBackRest 2.x lên minor 2.y | Backup tooling update | Kiểm tra release notes và repository compatibility |
| Backup agent lên bản hỗ trợ PostgreSQL mới | Tooling update | Nâng và test trước database cutover |

### 1.2. Ba lớp phiên bản cần theo dõi

Một cluster có thể có ba nhóm phiên bản độc lập:

- **Database server:** PostgreSQL major/minor version trên primary và mỗi standby.
- **Backup/replication tooling:** pgBackRest, Barman, WAL-G, pg_basebackup client, monitoring/agent binaries và automation.
- **Extensions và client drivers:** shared libraries, extension SQL scripts, JDBC/libpq/ORM drivers và application dependencies.

Một server mới không tự động bảo đảm extension binaries, backup agents hay application drivers đã tương thích.

### 1.3. Phạm vi của một cluster HA

Inventory không chỉ gồm primary và một standby. Cần tính cả:

- Physical standbys và cascading standbys.
- Synchronous replication settings và failover manager.
- Replication slots, WAL senders/receivers và archive command.
- Backup host, repository host, object storage và retention jobs.
- Monitoring, alerting, connection pool và proxy.
- Extensions, tablespaces, custom libraries và authentication.
- Scheduled jobs, cron/systemd services, secrets và certificates.

Mỗi thành phần có thể giữ một đường dẫn binary/data directory hoặc version pin riêng.

### 1.4. Chọn mục tiêu và downtime

Trước khi chọn phương pháp, xác định:

- Downtime tối đa cho phép.
- RPO/RTO yêu cầu.
- Kích thước database và tốc độ ghi.
- Số lượng standbys và topology.
- Khả năng có một máy/cluster mới chạy song song.
- Có thể tạo logical publication/subscription hay không.
- Backup retention và thời gian restore.
- Cửa sổ rollback và điều kiện kết thúc rollback.

`pg_upgrade` thường có downtime trong lúc chuyển cluster; logical replication có thể giảm downtime cutover nhưng yêu cầu chuẩn bị schema/data/sequence và đồng bộ kỹ hơn.

---

## 2. Các nguyên tắc tương thích phải nắm rõ

### 2.1. Physical replication không phải major-version migration

Streaming replication và WAL shipping truyền thay đổi ở mức physical blocks/WAL. Primary và standby phải dùng cùng major version và thuộc cùng một PostgreSQL cluster identity. Standby PostgreSQL 16 không thể tiếp tục replay WAL từ primary PostgreSQL 17 như một standby bình thường.

Do đó, major upgrade cần tạo cluster mới và chuyển standby sang data directory/cluster mới. Không chỉ cài PostgreSQL binary mới trên standby cũ rồi restart.

### 2.2. Minor versions trong cùng major

Minor releases trong cùng major version giữ tương thích physical storage. Tuy vậy, vẫn phải tuân theo thứ tự cập nhật binaries và restart HA do platform/failover tooling quy định. Với synchronous replication, hãy đánh giá ảnh hưởng khi restart standby hoặc primary tới commit latency và availability.

### 2.3. Một standby không phải bản sao độc lập để tự nâng tùy ý

Physical standby cần có cùng cluster identity, timeline/WAL history và state với primary. Nếu tự `initdb` hoặc chạy `pg_upgrade` riêng trên standby, cluster mới có thể có system identifier khác và không thể nhận WAL từ primary đã nâng.

Có hai đường xử lý phổ biến sau `pg_upgrade`:

1. Nếu dùng link mode, có thể sử dụng quy trình `rsync` chuyên biệt của PostgreSQL để chuyển các hard links của primary đã nâng sang standby cũ.
2. Nếu dùng copy/clone mode, không dùng rsync hard-link procedure đó; cách đơn giản là tạo lại standby từ primary mới bằng base backup hoặc phương pháp restore tương đương.

Không tự ghép các data directories nếu chưa theo đúng quy trình được tài liệu PostgreSQL hỗ trợ.

### 2.4. Logical replication là cơ chế khác

Logical replication chuyển row changes theo publication/subscription và có thể dùng giữa các major versions. Nó phù hợp để dựng subscriber trên version mới trong khi publisher cũ vẫn phục vụ writes.

Logical replication không tự chuyển toàn bộ cluster state. DDL/schema changes, sequence state, large objects, roles, tablespaces, extension state và một số loại objects cần quy trình riêng.

### 2.5. Backup vật lý và backup logic

Physical base backups và WAL archives gắn với cluster/version/timeline và yêu cầu PostgreSQL binaries phù hợp để restore. Không giả định backup vật lý của PostgreSQL 16 có thể được khôi phục trực tiếp thành PostgreSQL 17.

Logical dumps qua `pg_dump`/`pg_restore` có tính di động giữa các major versions cao hơn. Nên dùng pg_dump từ phiên bản mới hơn hoặc cùng phiên bản với server đích theo ma trận tương thích; một pg_dump cũ không thể dump server major mới hơn chính nó.

### 2.6. Cluster identity và system identifier

`system_identifier` định danh một PostgreSQL cluster. Kiểm tra bằng:

```bash
pg_controldata -D /path/to/data | grep "Database system identifier"
```

Trên Windows có thể chạy `pg_controldata.exe` trong thư mục `bin` và kiểm tra output tương ứng. Primary/standby vật lý phải thuộc cùng cluster identity. Sau major upgrade, xác nhận cluster mới và standby mới có identity phù hợp theo quy trình.

### 2.7. WAL và timeline

Sau promotion hoặc major migration, timeline có thể thay đổi. Archive destination, restore_command, replication slots và backup catalog phải theo dõi đúng cluster/timeline. Không trộn WAL từ old cluster vào archive path của new cluster nếu công cụ không quản lý riêng namespace/stanza.

---

## 3. Inventory và compatibility matrix

### 3.1. Ghi lại topology

Trên từng server:

```sql
SELECT
    version(),
    current_setting('server_version') AS server_version,
    pg_is_in_recovery() AS is_standby,
    current_setting('data_directory') AS data_directory,
    current_setting('wal_level') AS wal_level;
```

Trên primary, kiểm tra replication:

```sql
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
```

Trên standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

Lag timestamp có thể gây hiểu nhầm khi workload đang idle; đối chiếu LSN và trạng thái receiver/replay.

### 3.2. Inventory replication slots

```sql
SELECT
    slot_name,
    slot_type,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Ghi riêng physical và logical slots, owner/application sử dụng, retention implications và cách tái tạo sau upgrade. Slot không được tiêu thụ có thể giữ WAL và làm đầy pg_wal.

### 3.3. Inventory extensions

```sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS schema_name
FROM pg_extension AS e
JOIN pg_namespace AS n ON n.oid = e.extnamespace
ORDER BY e.extname;
```

Ghi version của shared libraries trên OS, không chỉ extversion trong catalog. Extension C cần binary build tương thích major version mới; nhiều extension cần package riêng cho target PostgreSQL.

### 3.4. Inventory configuration

Ghi các giá trị có ảnh hưởng đến replication, WAL, backup và startup:

```sql
SELECT name, setting, unit, source, pending_restart
FROM pg_settings
WHERE name IN (
    'shared_preload_libraries',
    'wal_level',
    'archive_mode',
    'archive_command',
    'restore_command',
    'max_wal_senders',
    'max_replication_slots',
    'hot_standby',
    'primary_conninfo',
    'primary_slot_name',
    'synchronous_standby_names',
    'wal_keep_size',
    'max_wal_size',
    'max_connections'
)
ORDER BY name;
```

Một số tham số chỉ tồn tại ở primary hoặc standby; query có thể cần điều chỉnh theo version. Lưu cả config files, include files, postgresql.auto.conf, service definitions và environment variables.

### 3.5. Compatibility matrix

Tạo bảng kiểm tra cho từng thành phần:

| Thành phần | Phiên bản hiện tại | Phiên bản mục tiêu | Bằng chứng tương thích |
|---|---|---|---|
| PostgreSQL primary |  |  | Release notes / upgrade docs |
| PostgreSQL standby |  |  | Physical replication procedure |
| pgBackRest/Barman/WAL-G |  |  | Version support matrix |
| Backup repository format |  |  | Tool documentation |
| Extensions |  |  | Vendor release notes/build |
| Monitoring/HA agent |  |  | Agent support matrix |
| JDBC/libpq/ORM |  |  | Driver release notes |
| OS/platform |  |  | PostgreSQL support matrix |

Không dùng câu “latest version supports PostgreSQL” thay cho việc xác nhận cụ thể old major, target major và repository format.

### 3.6. Đọc release notes của mọi major bị bỏ qua

Nếu nâng PostgreSQL 14 lên 18, đọc migration notes của 15, 16, 17 và 18, không chỉ notes của target. Kiểm tra reserved keywords, removed parameters, changed defaults, catalog changes, authentication, extension API và planner behavior.

---

## 4. Thứ tự nâng cấp backup tooling

### 4.1. Vì sao backup tooling thường phải được chuẩn bị trước?

Backup software phải có khả năng:

- Kết nối và đọc metadata từ old PostgreSQL cluster.
- Backup/restore target major version.
- Archive và retrieve WAL đúng cluster.
- Hiểu repository/catalog format hiện có.
- Chạy trên backup host và database hosts với đúng binaries/config.

Nếu target PostgreSQL major cần một backup tool version mới, hãy nâng tool trong khi old database vẫn đang hoạt động và xác nhận nó vẫn đọc được backup chain cũ trước cutover.

### 4.2. Không nâng repository format theo phỏng đoán

Backup tool binary version và repository format là hai việc khác nhau. Một số tool có thể đọc format cũ nhưng khi chuyển repository format thì thao tác có thể một chiều hoặc cần migration riêng.

Trước khi chạy lệnh nâng repository:

1. Đọc release notes của tool.
2. Xác nhận tương thích ngược với repository hiện tại.
3. Sao lưu/copy metadata hoặc repository theo hướng dẫn vendor.
4. Thử nâng trên bản repository clone.
5. Thử restore từ bản clone.
6. Chỉ nâng repository production khi đã có kế hoạch rollback.

### 4.3. Thứ tự tổng quát an toàn

Một thứ tự thường dùng:

1. Inventory backup chains, WAL archives, retention và restore procedures.
2. Nâng backup software/agents lên bản hỗ trợ old và target PostgreSQL major.
3. Xác nhận tool mới vẫn backup/restore được old cluster.
4. Tạo một backup đầy đủ trước upgrade và xác nhận WAL archiving hoạt động.
5. Restore thử backup đó vào môi trường cô lập.
6. Nâng PostgreSQL primary và physical standbys theo phương pháp đã chọn.
7. Cập nhật pg-path/server path và stanza/catalog metadata của backup tool cho cluster mới.
8. Tạo backup mới của target cluster.
9. Restore thử backup mới và xác nhận WAL recovery.
10. Giữ old backup chains trong thời gian retention/rollback đã phê duyệt.

Thứ tự chi tiết của lệnh tool phụ thuộc sản phẩm. Không áp dụng lệnh stanza-upgrade của pgBackRest cho Barman, WAL-G hoặc công cụ khác.

### 4.4. Ví dụ với pgBackRest

Với pgBackRest, sau khi PostgreSQL được nâng lên major version mới, cập nhật pg-path trong tất cả cấu hình liên quan rồi chạy stanza-upgrade cho từng repository được cấu hình. Nếu database offline, tài liệu pgBackRest có tùy chọn --no-online.

Ví dụ minh họa:

```bash
pgbackrest --stanza=main --repo=1 stanza-upgrade
```

Nếu có nhiều repositories, chạy thao tác theo từng repository theo cấu hình của hệ thống. Kiểm tra lệnh/options đúng với pgBackRest release đang cài trước khi thực hiện.

### 4.5. Cập nhật đường dẫn database

Sau major upgrade, PostgreSQL data directory hoặc binary path có thể thay đổi, ví dụ:

```text
/var/lib/postgresql/16/main
/var/lib/postgresql/17/main
```

Cập nhật path trên primary/standby/backup hosts, service configs và agent configs. Với cấu hình pgBackRest multi-host, kiểm tra cả primary path, standby path và repository host.

### 4.6. WAL archive phải được xác nhận

Trước cutover, xác nhận old primary archive WAL thành công. Sau cutover, xác nhận new primary archive WAL vào đúng namespace/repository cho cluster mới.

Không chỉ kiểm tra archive_mode = on; xem archive status và log:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

Các counters tích lũy nên được snapshot trước/sau. Một giá trị archived_count tăng không chứng minh restore chain đầy đủ; cần thử restore/PITR.

### 4.7. Retention và old WAL

Không chạy retention/prune trong giai đoạn chuyển đổi nếu chưa hiểu dependency giữa full/differential/incremental backups và WAL segments. Giữ old chain và WAL cần thiết để phục hồi old cluster trong cửa sổ rollback.

### 4.8. Barman và WAL-G

Với Barman, WAL-G hoặc backup manager khác, kiểm tra:

- Phiên bản server/agent hỗ trợ.
- Backup catalog metadata và compression/encryption formats.
- WAL archive naming/namespace.
- Restore command và recovery configuration.
- Repository migration/retention semantics.
- Credentials, object storage endpoints và encryption keys.

Dùng lệnh kiểm tra/backup/restore được tài liệu đúng version quy định. Không giả định các công cụ có cùng mô hình stanza hoặc catalog.

---

## 5. Chọn phương pháp major upgrade

### 5.1. So sánh ba phương pháp

| Phương pháp | Downtime | Ưu điểm | Đánh đổi |
|---|---|---|---|
| pg_upgrade | Thường cần downtime cutover | Nhanh, giữ data files, ít tạo bản dump lớn | Cần kiểm tra compatibility, thao tác standby riêng |
| Logical replication | Có thể rút ngắn downtime | Old primary tiếp tục phục vụ trong lúc copy/sync | DDL, sequences, large objects và cutover cần xử lý thủ công |
| Dump/restore | Thường dài với database lớn | Quy trình rõ, chuyển đổi schema/data tường minh | Tốn thời gian, storage và bandwidth |

Chọn theo kích thước dữ liệu, downtime, khả năng chạy song song, độ phức tạp schema và khả năng kiểm chứng.

### 5.2. Khi nào chọn pg_upgrade?

Chọn pg_upgrade khi:

- Cần giữ phần lớn data files và giảm thời gian migration.
- Có thể dừng writes trong cửa sổ cutover.
- Source/target platform và build đáp ứng yêu cầu tương thích.
- Extensions có binaries và update scripts cho target major.
- Có đủ storage hoặc hỗ trợ link/clone mode phù hợp.
- Có kế hoạch riêng cho physical standbys.

pg_upgrade chuyển cluster data/catalog; nó không thay thế việc nâng OS packages, extensions, backup software, application drivers hoặc kiểm tra behavior.

### 5.3. Khi nào chọn logical replication?

Chọn logical replication khi:

- Downtime cho phép ngắn hơn thời gian dump/restore.
- Có thể dựng target cluster mới chạy song song.
- Tables có replica identity phù hợp.
- Có thể đồng bộ schema/DDL và sequence state riêng.
- Có thể kiểm soát writes tại thời điểm cutover.
- Workload và WAL generation không làm subscriber tụt quá xa.

Đây là phương pháp migration dữ liệu, không phải physical standby của old primary. Subscriber là cluster độc lập với schema/data được đồng bộ qua publication/subscription.

### 5.4. Khi nào chọn dump/restore?

Dump/restore phù hợp khi:

- Database không quá lớn hoặc downtime dài có thể chấp nhận.
- Muốn thay đổi schema, encoding, tablespace hoặc object ownership có kiểm soát.
- Muốn loại bỏ một số objects cũ.
- Cần một migration dễ audit và có thể chạy theo từng database.

Để giữ global objects như roles và tablespaces, cần dump chúng riêng bằng pg_dumpall --globals-only. Dump từng database bằng pg_dump; restore bằng pg_restore hoặc psql tùy format.

### 5.5. Không có phương pháp nào tự động chuyển mọi thành phần

Dù dùng phương pháp nào, cần lập kế hoạch riêng cho:

- Roles, memberships, passwords và authentication.
- Tablespaces và file paths.
- Extensions, shared libraries và preload modules.
- Foreign servers, user mappings và external credentials.
- Publications/subscriptions, replication slots và HA agents.
- Large objects, sequences và scheduled jobs.
- Monitoring, backup catalog, WAL archive và restore procedures.

---

## 6. Chuẩn bị chung trước major upgrade

### 6.1. Đọc migration notes và kiểm tra ứng dụng

Đọc release notes của từng major bị bỏ qua. Kiểm tra:

- Removed/renamed configuration parameters.
- Changed defaults và planner behavior.
- Authentication/TLS changes.
- SQL behavior, reserved keywords và collation.
- Extension API và shared library requirements.
- Replication slot/WAL behavior.
- Driver compatibility.

Chạy application integration tests trên target version trước cutover.

### 6.2. Chuẩn bị target binaries

Cài PostgreSQL target major song song với old binaries nếu nền tảng hỗ trợ. Kiểm tra executable paths, service names, data directory paths và port. Không để service manager vô tình khởi động sai cluster.

### 6.3. Extensions và preload modules

Cài target-major binaries của mọi extension C trước khi chạy pg_upgrade hoặc tạo target cluster. Kiểm tra shared_preload_libraries và các module cần được load lúc startup.

Một số extension cần ALTER EXTENSION ... UPDATE sau migration. Đọc hướng dẫn của extension; không giả định pg_upgrade tự cập nhật tất cả extension SQL objects.

### 6.4. Tablespaces và custom files

Inventory tablespace locations, symlinks, relocated pg_wal, custom full-text search dictionaries, certificates, key files và external config files. Bảo đảm target paths tồn tại, ownership/permissions đúng và có backup.

### 6.5. Authentication và network

Chuẩn bị pg_hba.conf, pg_ident.conf, TLS certificates, postgresql.conf, include files, firewall rules, DNS/VIP/proxy và connection pool. Thử xác thực từ application hosts bằng target endpoint trong môi trường test.

### 6.6. Backup và restore rehearsal

Trước khi thay đổi:

1. Chạy backup đầy đủ theo tool hiện tại.
2. Xác nhận WAL archive/continuous archiving hoạt động.
3. Lưu backup metadata và encryption keys.
4. Restore thử vào môi trường độc lập.
5. Khởi động restored cluster và chạy kiểm tra dữ liệu.
6. Ghi thời gian backup, restore và recovery để xác nhận RTO.

Backup thành công về mặt exit code chưa đủ; restore test mới xác nhận có thể dùng được.

### 6.7. Quản lý writes trong cửa sổ cutover

Chuẩn bị cách:

- Dừng application writes hoặc bật maintenance mode.
- Drain connection pools và background workers.
- Tạm dừng scheduled jobs/ETL.
- Chặn writes từ các clients không được kiểm soát.
- Xác nhận không còn long-running transactions cần hoàn tất.

Đừng dựa vào một thông báo bảo trì nếu vẫn còn worker hoặc service có thể ghi vào old primary.

### 6.8. Ghi lại baseline

Lưu:

- Database/table/index sizes.
- Row counts và critical aggregates.
- Replication lag và slot inventory.
- Backup chain và last archived WAL.
- Query performance/pg_stat_statements snapshots.
- CPU, memory, I/O, connections và latency.

Baseline giúp so sánh behavior sau nâng cấp.

---

## 7. Nâng primary và physical standbys bằng pg_upgrade

### 7.1. Hiểu hai nhánh nâng standby

PostgreSQL có quy trình cụ thể cho physical standbys sau pg_upgrade:

- Nếu primary được nâng bằng link mode, có thể dùng rsync với hard links để tạo data directory target trên standby mà không copy lại toàn bộ relation files.
- Nếu không dùng link mode, không dùng rsync procedure đó, hoặc muốn cách đơn giản hơn, dựng lại standbys sau khi primary mới đã chạy.

Không chạy pg_upgrade độc lập trên từng standby rồi giả định chúng tự đồng bộ với primary mới.

### 7.2. Trước khi dừng cluster cũ

1. Xác nhận backup trước upgrade đã restore được.
2. Xác nhận mọi standbys đang streaming và caught up.
3. Kiểm tra replication slots, WAL archive và timeline.
4. Cài target PostgreSQL binaries và extension shared objects trên primary/standby hosts.
5. Tạo target data directory của primary theo hướng dẫn platform.
6. Kiểm tra target configuration, đặc biệt wal_level không được đặt thành minimal nếu cần replication.
7. Chọn copy, link hoặc clone mode và chạy pg_upgrade --check với đúng mode.

### 7.3. pg_upgrade --check

Chạy binary pg_upgrade của target version và kiểm tra compatibility trước cửa sổ downtime:

```bash
pg_upgrade \
  --old-datadir=/var/lib/postgresql/16/main \
  --new-datadir=/var/lib/postgresql/17/main \
  --old-bindir=/usr/lib/postgresql/16/bin \
  --new-bindir=/usr/lib/postgresql/17/bin \
  --link \
  --check
```

Đây là ví dụ đường dẫn Linux; thay bằng paths và options đúng với package/platform thực tế. --check không thay thế rehearsal trên bản clone. Đọc toàn bộ output và xử lý extension/config incompatibilities trước cutover.

### 7.4. Chọn copy, link hay clone

| Mode | Cách hoạt động | Rollback |
|---|---|---|
| Copy (mặc định) | Copy relation files sang cluster mới | Old cluster vẫn có thể được giữ để quay lại |
| Link (--link) | Hard-link relation files giữa old và new directories | Không thể dùng old cluster sau khi new cluster đã khởi động |
| Clone (--clone) | Dùng copy-on-write/reflink khi filesystem hỗ trợ | Giữ old cluster độc lập về mặt logic |

Link/clone yêu cầu data directories trên cùng filesystem và được hỗ trợ bởi platform/filesystem. Link mode nhanh và ít cần disk space nhưng giới hạn rollback nghiêm ngặt. Clone mode cần hỗ trợ reflink. Chạy --check với đúng mode sẽ dùng trong production.

### 7.5. Đồng bộ primary/standby trước shutdown

Với phương pháp rsync link-mode của PostgreSQL, old primary và standbys cần được đồng bộ tới cùng checkpoint. Trong quá trình shutdown old primary, old standbys phải còn hoạt động để nhận các thay đổi cuối cùng.

Sau khi các cluster dừng, chạy pg_controldata trên old primary và từng old standby; so sánh Latest checkpoint location. Các giá trị cần khớp trước khi dùng standby-upgrade rsync procedure.

Nếu checkpoint LSN không khớp, không tiếp tục rsync. Điều tra WAL/replay lag và hoàn tất đồng bộ theo tài liệu.

### 7.6. Dừng old primary và chạy pg_upgrade

Sau khi đã drain writes, xác nhận standbys đã nhận/replay các thay đổi cuối cùng. Dừng old primary và old standbys theo thứ tự được runbook của cluster xác định; giữ chúng ở trạng thái dừng trong giai đoạn chuyển đổi.

Chạy pg_upgrade trên primary bằng binary target version. Ví dụ:

```bash
pg_upgrade \
  --old-datadir=/var/lib/postgresql/16/main \
  --new-datadir=/var/lib/postgresql/17/main \
  --old-bindir=/usr/lib/postgresql/16/bin \
  --new-bindir=/usr/lib/postgresql/17/bin \
  --jobs=8 \
  --link
```

Không khởi động new primary trước khi hoàn tất standby rsync nếu đi theo link-mode standby procedure.

### 7.7. Link-mode: chuẩn bị standby directories

Trên từng standby:

1. Cài target PostgreSQL binaries và cùng extension shared objects như primary mới.
2. Bảo đảm target standby data directory không tồn tại hoặc đang rỗng.
3. Nếu đã chạy initdb để tạo directory, xóa directory target rỗng theo đúng runbook và kiểm tra path trước khi làm.
4. Lưu các config files cần giữ: postgresql.conf, include files, postgresql.auto.conf, pg_hba.conf.
5. Dừng old standby nếu nó chưa dừng.

Không để target standby directory chứa dữ liệu cũ hoặc cluster được initdb riêng trước khi rsync.

### 7.8. Link-mode: rsync hard links

Chạy rsync từ primary đã nâng, ở directory cha chứa cả old và new cluster directories, cho từng standby:

```bash
rsync --archive --delete --hard-links --size-only --no-inc-recursive \
  old_cluster new_cluster standby-host:/path/to/cluster-parent
```

Đây là mẫu minh họa; thay paths/remote target theo cấu trúc thư mục thực tế. Dùng --dry-run trước và kiểm tra kỹ source/destination. --delete có thể xóa file trong destination nếu đường dẫn sai.

--hard-links là thành phần quan trọng của quy trình này: rsync tái tạo trên standby các hard links tương ứng với files đã được link giữa old/new clusters trên primary. Files không được link sẽ được copy.

Nếu có tablespaces, cần chạy rsync tương ứng cho từng tablespace directory. Nếu pg_wal được đặt ngoài data directory, đồng bộ cả đường dẫn đó theo tài liệu.

### 7.9. Link-mode: cấu hình replication và slots

Sau rsync:

- Khôi phục/cập nhật configuration files trên standby.
- Cấu hình primary_conninfo, primary_slot_name, restore_command và archive settings phù hợp.
- Kiểm tra synchronous standby names và failover manager.
- Kiểm tra/recreate replication slots theo major-version behavior.

Đặc biệt, nếu old primary trước PostgreSQL 17.0, không có slots nào được copy sang new standby trong quy trình này; cần tạo lại các slots cần thiết. Nếu old primary là PostgreSQL 17.0 trở lên, chỉ logical slots trên primary được copy sang new standby; các loại slots khác trên old standby vẫn cần được tạo lại thủ công.

Đừng bật các consumers dùng slot cho tới khi đã xác nhận slot name, type, plugin, database và restart LSN phù hợp.

### 7.10. Khởi động cluster mới

Sau khi hoàn tất primary upgrade, rsync standbys, restore configs và xác nhận WAL/replication settings:

1. Khôi phục pg_hba.conf và các config cần thiết trên primary.
2. Khởi động new primary.
3. Kiểm tra startup logs và post-upgrade scripts do pg_upgrade tạo ra.
4. Chạy các post-upgrade scripts được yêu cầu.
5. Khởi động từng new standby.
6. Xác nhận streaming, receive/replay LSN và synchronous state.

Không đưa traffic ứng dụng trở lại trước khi kiểm tra database và HA ở mức cần thiết.

### 7.11. Non-link mode: dựng lại standbys

Nếu dùng copy/clone mode hoặc không thực hiện rsync hard-link procedure:

1. Hoàn tất pg_upgrade trên primary.
2. Khởi động new primary và xác nhận cluster hoạt động.
3. Tạo standby mới từ primary mới bằng pg_basebackup, backup/restore tool hoặc phương pháp chuẩn của platform.
4. Cài cùng PostgreSQL major, extension binaries và config cần thiết.
5. Cấu hình replication slots/standby settings.
6. Khởi động standby và xác nhận streaming/replay.

Đây thường là đường đơn giản hơn nhưng cần thời gian truyền/restore toàn bộ dữ liệu và có thể kéo dài thời gian HA chưa được khôi phục.

---

## 8. Major upgrade bằng logical replication

### 8.1. Kiến trúc migration

Logical replication cho phép old primary tiếp tục nhận writes trong lúc target cluster mới copy dữ liệu ban đầu và apply các thay đổi tiếp theo:

```text
  Old PostgreSQL primary (publisher)
        |  publication + WAL logical decoding
        |  initial table copy and changes
        v
  New PostgreSQL cluster (subscriber)
        |
        | validate, sync sequences, cut over
        v
  New primary for applications
```

Đây không phải physical standby. Target cluster có data directory, system identifier, configuration và backup chain riêng.

### 8.2. Điều kiện trước khi thiết lập

- Target major version hỗ trợ logical replication từ source version.
- Publisher có wal_level = logical.
- Có đủ replication slots, WAL senders và logical workers.
- Mỗi bảng cần UPDATE/DELETE có replica identity phù hợp, thường là primary key.
- Schema target tương thích với row changes nhận được.
- Các extensions, types, collations và functions đã được cài trên target.
- Có đủ disk/IO để initial copy và apply changes.

Tham khảo max_replication_slots, max_wal_senders, max_logical_replication_workers, max_sync_workers_per_subscription và max_worker_processes.

### 8.3. Chuẩn bị schema và global objects

Logical replication không tự tạo database schema hoặc DDL. Có thể dump schema-only từ source và restore vào target trước khi tạo subscription:

```bash
pg_dump --schema-only --no-owner --no-privileges \
  --host=old-primary --username=admin --dbname=appdb \
  --file=appdb-schema.sql

psql --host=new-primary --username=admin --dbname=appdb \
  --file=appdb-schema.sql
```

Roles, memberships, tablespaces và các global objects cần dump/restore riêng. Đọc kỹ ownership, grants, default privileges và extension dependencies.

### 8.4. Tạo publication trên old primary

Ví dụ publication cho tất cả tables:

```sql
CREATE PUBLICATION upgrade_pub
FOR ALL TABLES;
```

Hoặc liệt kê cụ thể các tables:

```sql
CREATE PUBLICATION upgrade_pub
FOR TABLE public.customers, public.orders, public.order_items;
```

Chọn tập tables có chủ đích. Views, materialized views, foreign tables và một số object types không được logical replication hỗ trợ như ordinary tables.

### 8.5. Tạo subscription trên target

Ví dụ:

```sql
CREATE SUBSCRIPTION upgrade_sub
CONNECTION 'host=old-primary port=5432 dbname=appdb user=repl_user password=REDACTED sslmode=verify-full'
PUBLICATION upgrade_pub
WITH (copy_data = true, create_slot = true, enabled = true);
```

Không hard-code password thật trong file/script dùng chung. Dùng secret management hoặc cơ chế authentication được phê duyệt. Xác nhận SSL, network, grants và replication slot trước khi bắt đầu copy.

### 8.6. Theo dõi initial table sync

Trên subscriber:

```sql
SELECT
    srrelid::regclass AS table_name,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
```

Kiểm tra subscription worker:

```sql
SELECT
    subname,
    pid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
```

Chỉ xem initial copy hoàn tất khi các tables ở trạng thái ready và apply worker không có lỗi. Kiểm tra PostgreSQL logs nếu một table sync bị dừng.

### 8.7. Theo dõi replication lag

Theo dõi publisher/subscriber LSN, apply worker state, slot retained WAL và disk usage. Logical replication slot có thể giữ WAL trên publisher nếu subscriber ngừng apply; đặt monitoring/alerts cho retained WAL và disk free space.

### 8.8. Các giới hạn phải xử lý thủ công

Logical replication built-in có các giới hạn quan trọng:

- DDL và schema changes không được tự replicate; apply cùng thay đổi trên target theo thứ tự an toàn.
- Sequence values không được replicate. Identity/serial column values được copy như table data, nhưng sequence object trên target cần set lại.
- Large objects không được replicate.
- Roles, grants, tablespaces, functions, triggers, extensions và scheduled jobs cần migration riêng.
- Triggers/rules mặc định không chạy như trên publisher trong apply worker; kiểm tra side effects và business logic.
- Truncate và foreign-key relationships cần được lập kế hoạch cẩn thận.

Không cut over nếu còn object nghiệp vụ quan trọng chưa được chuyển.

### 8.9. Đồng bộ DDL trong thời gian migration

Mọi schema change trong migration window phải có runbook apply trên target. Một thay đổi schema ở publisher mà subscriber chưa có cột tương ứng có thể làm apply worker lỗi khi row changes đến.

Ưu tiên additive changes theo thứ tự an toàn: tạo cột/index/constraint tương thích trên target trước khi source bắt đầu phát sinh dữ liệu theo schema mới. Ghi lại từng migration đã chạy trên hai clusters.

### 8.10. Đồng bộ sequence values trước cutover

Sau khi dừng writes trên source và subscriber đã apply hết thay đổi, lấy sequence state từ source rồi đặt target sequence vượt qua giá trị đã dùng. Ví dụ với một sequence:

```sql
SELECT setval(
    'public.orders_order_id_seq',
    COALESCE((SELECT MAX(order_id) FROM public.orders), 1),
    EXISTS (SELECT 1 FROM public.orders)
);
```

Ví dụ này dùng max column value làm mốc. Nếu sequence có increment, min/max, cycle hoặc cache đặc thù, đồng bộ theo metadata/state thực tế; không áp dụng một câu lệnh chung cho mọi sequence.

### 8.11. Cutover logical replication

Một trình tự điển hình:

1. Đưa application vào maintenance/read-only mode hoặc chặn toàn bộ writes tới publisher.
2. Dừng background workers, schedulers và integration jobs có thể ghi.
3. Xác nhận mọi source transactions đã commit.
4. Ghi lại source LSN cuối và đợi subscriber apply tới vị trí tương ứng.
5. Xác nhận mọi tables đã ready và không còn apply errors.
6. Đồng bộ sequence states và các objects không replicate.
7. Chạy consistency checks và critical business queries.
8. Dừng/disable subscription theo runbook.
9. Chuyển application endpoint sang target.
10. Cho phép writes trên target và theo dõi lỗi.

Chỉ một phía được nhận writes trong thời điểm cutover. Không cho phép old và new primary cùng nhận writes độc lập nếu không có cơ chế multi-writer/conflict handling được thiết kế rõ.

### 8.12. Rollback sau logical cutover

Sau khi target đã nhận writes mới, source publisher cũ không tự nhận các writes đó. Muốn quay lại old cluster cần reverse replication hoặc một quy trình data reconciliation riêng. Vì vậy, định nghĩa rollback window và điểm chấp nhận không thể quay lại trước khi bật writes trên target.

---

## 9. Major upgrade bằng dump/restore

### 9.1. Dump global objects

Ví dụ:

```bash
pg_dumpall --globals-only \
  --host=old-primary --username=postgres \
  --file=globals.sql
```

Kiểm tra file trước khi restore; xử lý roles/tablespaces theo policy của môi trường đích. Không đưa passwords/secrets vào repository hoặc log.

### 9.2. Dump database

Custom format phù hợp với pg_restore và hỗ trợ parallel restore:

```bash
pg_dump -Fc \
  --host=old-primary --username=backup_user \
  --dbname=appdb \
  --file=appdb.dump
```

Có thể dump từng database song song nếu nguồn có đủ capacity. Ghi lại checksum, size và exit status.

### 9.3. Restore target

Tạo database đích với owner/encoding/locale/tablespace phù hợp:

```bash
createdb --host=new-primary --username=postgres \
  --owner=app_owner appdb

pg_restore --host=new-primary --username=restore_user \
  --dbname=appdb --jobs=8 appdb.dump
```

Kiểm tra extension creation, ownership, privileges, sequences và large objects. Nếu restore schema/data riêng, giữ đúng dependency order.

### 9.4. Thời gian và consistency

Dump nhất quán theo snapshot của từng database, nhưng nếu ứng dụng vẫn ghi sau thời điểm dump thì những thay đổi sau snapshot không tự có trên target. Cần downtime writes từ đầu hoặc cơ chế đồng bộ delta bổ sung.

### 9.5. Dựng physical standbys sau restore

Sau khi target cluster được restore và khởi động, tạo physical standbys mới từ target primary. Không sử dụng data directory của old standby.

---

## 10. Post-upgrade tasks cho PostgreSQL

### 10.1. Chạy post-upgrade scripts

pg_upgrade có thể tạo script xử lý các bước post-upgrade. Đọc warnings/output, chạy từng script theo hướng dẫn và lưu log. Không xóa scripts trước khi xác nhận chúng đã chạy thành công.

### 10.2. Cập nhật extensions

Trong từng database:

```sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
```

Chạy ALTER EXTENSION ... UPDATE theo hướng dẫn của extension và kiểm tra shared library version. Một số extension yêu cầu uninstall/reinstall hoặc bước migration riêng; không chạy update hàng loạt một cách mù quáng.

### 10.3. Statistics planner không được chuyển như dữ liệu bảng

Optimizer statistics không được pg_upgrade chuyển nguyên trạng. Chạy analyze script do pg_upgrade tạo hoặc thu thập statistics theo giai đoạn:

```bash
vacuumdb --all --analyze-in-stages
```

Trong lúc analyze, performance có thể chưa ổn định. Theo dõi tiến độ và tránh so sánh benchmark ngay khi planner statistics còn thiếu.

### 10.4. Kiểm tra configuration defaults

Không copy nguyên config cũ mà không xem xét. Một số parameters có thể đổi tên, bỏ hoặc đổi default. So sánh postgresql.conf cũ/mới, pg_settings, pending_restart, logs và release notes.

### 10.5. Kiểm tra startup và logs

Xác nhận:

- Primary start đúng data directory và port.
- Không có missing library/config errors.
- Extensions load thành công.
- Archive command chạy.
- Standbys kết nối và replay.
- Authentication và TLS hoạt động.
- Application connection pool kết nối đúng endpoint.

### 10.6. Recreate scheduled jobs và integrations

Kiểm tra cron/systemd, pg_cron hoặc scheduler khác, ETL, FDW, foreign servers, user mappings, monitoring exporters và secrets. Các thành phần bên ngoài không nhất thiết được migration tool chuyển tự động.

---

## 11. Đồng bộ lại backup và WAL archive sau cutover

### 11.1. Cập nhật backup tool sang cluster mới

Sau khi primary và standbys đã chạy target major:

1. Cập nhật server/data directory paths trong backup tool.
2. Cập nhật host/port và connection configuration.
3. Chạy metadata/stanza upgrade nếu sản phẩm yêu cầu.
4. Kiểm tra repository list và archive namespace.
5. Xác nhận backup tool kết nối đúng primary mới.
6. Chạy kiểm tra archive/backup theo hướng dẫn của tool.

Với pgBackRest, chạy stanza-upgrade sau khi cập nhật pg-path cho target major. Nếu có nhiều repositories, thao tác cho từng repository theo cấu hình. Khi cluster offline, xem xét tùy chọn no-online được tài liệu đúng version hỗ trợ.

### 11.2. Tạo backup mới của target cluster

Sau khi metadata đã được cập nhật, tạo backup mới theo chính sách. Đừng giả định incremental backup của old major có thể làm base cho target major. Backup tool sẽ quyết định cần full backup hay chain mới theo repository/version semantics.

### 11.3. Kiểm tra WAL archiving trên primary mới

Xác nhận archive command thành công và WAL segments của target cluster được lưu đúng nơi. Theo dõi archive failures và archive lag; kiểm tra object storage permissions, encryption, compression và credentials.

### 11.4. Không trộn old và new cluster WAL

Old cluster và new cluster có system identifier/timeline khác nhau. Giữ archive namespaces hoặc stanza/catalog metadata tách biệt theo yêu cầu tool. Không copy WAL cũ sang path của new cluster chỉ vì tên file trông tương tự.

### 11.5. Kiểm tra backup từ standby

Nếu backup tool hỗ trợ backup-standby, xác nhận standby mới đã replay đủ và tool có thể đọc đúng cluster. Một số công cụ cần kết nối primary để bắt đầu/kết thúc backup dù phần lớn data files được đọc từ standby.

### 11.6. Restore thử backup mới

Tạo restore test vào host/database cô lập:

- Restore đúng PostgreSQL target major.
- Dùng binaries/extensions tương thích.
- Replay WAL tới recovery target mong muốn.
- Xác nhận cluster start.
- Chạy kiểm tra schema, roles, row counts và critical queries.
- Ghi thời gian restore và recovery.

Backup mới chỉ được xem là operational khi restore test đạt yêu cầu.

### 11.7. Point-in-time recovery

Thử PITR từ backup target cluster tới một thời điểm nằm trong archive range mới. Kiểm tra:

- Base backup được nhận diện.
- WAL segments liên tục và đúng timeline.
- Restore command hoạt động.
- Recovery target được áp dụng.
- Cluster dừng/đạt target như mong đợi.

Không kết luận PITR sẵn sàng chỉ từ việc archive count tăng.

### 11.8. Giữ old backup chain

Old backup và WAL có thể cần để restore old cluster nếu migration rollback. Giữ chúng tới khi:

- New cluster qua thời gian ổn định đã định.
- New full backup restore được.
- PITR test đạt yêu cầu.
- Application owner chấp nhận dữ liệu/behavior.
- Rollback window kết thúc.

Chỉ sau đó mới prune theo retention policy đã được phê duyệt.

---

## 12. Rollback và giới hạn quay lui

### 12.1. Rollback trước khi new primary nhận writes

Nếu target cluster chưa nhận writes mới, rollback thường có thể dừng target và khởi động lại old cluster, miễn là old data directory còn nguyên và chưa bị phá hủy.

Với pg_upgrade copy mode, old cluster thường có thể giữ lại để quay về. Với link mode, sau khi new cluster đã khởi động, old cluster không còn dùng được vì relation files được hard-link chia sẻ; không dựa vào old cluster như rollback option.

### 12.2. Rollback sau khi new primary đã nhận writes

Khi target đã nhận writes, old cluster bị stale. Không chỉ đổi DNS/connection string quay về old primary. Cần reverse replication, replay các changes đã phát sinh hoặc khôi phục từ backup/restore point phù hợp.

Định nghĩa rõ:

- Thời điểm bắt đầu cho phép writes trên target.
- Thời điểm rollback window đóng.
- Ai có quyền quyết định rollback.
- Cách xử lý writes đã commit trên target.
- Cách đảm bảo không có split-brain.

### 12.3. Không chạy hai primary cùng nhận writes

Trong cutover, chỉ một primary được nhận writes. Cập nhật endpoint, pool và worker jobs có thể mất thời gian; dùng maintenance mode và xác nhận tất cả clients đã chuyển trước khi mở writes.

### 12.4. Rollback backup tooling

Giữ backup tool version cũ và bản sao metadata/config theo hướng dẫn. Nếu tool/repository format đã được nâng một chiều, có thể cần khôi phục repository clone hoặc dùng binary tương thích để đọc old backup chain.

### 12.5. Rollback failover manager

Kiểm tra HA manager, fencing, VIP/DNS và failover automation. Một node cũ còn đăng ký trong failover manager có thể bị promote ngoài ý muốn. Cập nhật membership và fencing policy trước khi cho phép tự động failover.

---

## 13. Kiểm tra sau nâng cấp

### 13.1. Server version và cluster role

```sql
SELECT
    version(),
    current_setting('server_version') AS server_version,
    pg_is_in_recovery() AS is_standby,
    current_setting('data_directory') AS data_directory;
```

Xác nhận endpoint ứng dụng trỏ tới primary mới và standbys vẫn ở recovery mode.

### 13.2. Physical replication

Trên primary:

```sql
SELECT
    application_name,
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
```

Trên standby, kiểm tra receiver/replay status và log. Xác nhận synchronous standbys theo đúng policy.

### 13.3. Replication slots

```sql
SELECT
    slot_name,
    slot_type,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Đối chiếu inventory trước upgrade; xác nhận consumers kết nối đúng slot và không có inactive slots giữ WAL không cần thiết.

### 13.4. Backup và archive

Chạy backup status/check, kiểm tra WAL archive và restore test. Xác nhận retention/prune jobs đang dùng đúng stanza/namespace mới.

### 13.5. Data consistency

Kiểm tra critical row counts, aggregates, foreign keys, constraints, sequences, large objects, ownership và privileges. Với logical migration, so sánh table-level counts/checksums trong phạm vi có thể.

### 13.6. Application behavior

Chạy smoke tests:

- Login/authentication.
- Read/write critical flows.
- Transactions và constraints.
- Prepared statements/driver behavior.
- Connection pool và reconnect.
- Background workers, schedulers và ETL.
- Reporting/analytics queries.

### 13.7. Performance

So sánh với baseline:

- TPS/throughput và latency.
- Query plans và pg_stat_statements.
- CPU, memory và storage I/O.
- WAL generation và replication lag.
- Autovacuum/analyze.
- Lock waits và connection counts.

Không giả định planner statistics đã được chuyển; chạy ANALYZE và theo dõi query regressions.

### 13.8. Monitoring và alerting

Đảm bảo dashboards/alerts dùng đúng version, view columns và metric names. Kiểm tra exporters, backup agents, replication lag alerts, disk/WAL alerts và certificate expiry.

---

## 14. Minor update và logical replication cluster upgrade

### 14.1. Minor update có thể rolling theo node

Vì minor releases trong cùng major version giữ storage format tương thích, có thể nâng binaries từng node trong topology HA theo kế hoạch rolling:

1. Xác nhận backup và failover readiness.
2. Nâng một standby trước, restart bằng minor binaries mới.
3. Chờ standby replay và xác nhận streaming ổn định.
4. Lặp lại với các standbys còn lại.
5. Thực hiện planned switchover nếu cần giảm downtime cho primary.
6. Nâng/restart node primary cũ sau khi đã trở thành standby.
7. Xác nhận tất cả nodes cùng minor version và failover hoạt động.

Đây là ví dụ trình tự phổ biến; failover manager, synchronous replication và nhà cung cấp dịch vụ có thể yêu cầu thứ tự riêng. Không nâng một node mà chưa có đường quay lại hoặc standby đủ khỏe.

### 14.2. Minor update vẫn cần backup và kiểm tra

Minor update thường không cần chuyển data directory, nhưng vẫn cần:

- Đọc release notes của minor version.
- Kiểm tra OS packages và extension binaries.
- Lưu config và backup gần nhất.
- Xác nhận primary/standby compatibility.
- Kiểm tra service manager và startup logs.
- Kiểm tra backup tools và monitoring agents.

Một minor update không thay thế major upgrade procedure.

### 14.3. Nâng logical replication cluster đang tồn tại

Nếu hệ thống hiện tại đã là một logical replication cluster, cần phân biệt với việc dùng logical replication làm đường migration sang cluster mới.

PostgreSQL 18 có thể dùng pg_upgrade để migrate logical replication slots và subscription dependencies trong một số trường hợp, nhưng chỉ hỗ trợ migration cluster này khi tất cả members của old logical replication cluster từ PostgreSQL 17.0 trở lên. Các prerequisites gồm:

- Publisher target có wal_level = logical.
- max_replication_slots đủ lớn.
- Output plugins tương ứng được cài trong target binaries và được cấu hình an toàn.
- Old logical slots đã replicate hết transactions/messages và còn usable.
- Subscriber tables ở trạng thái phù hợp và replication origins tồn tại.
- max_active_replication_origins đủ cho subscriptions.

Trước khi nâng publisher, disable subscriptions theo hướng dẫn; sau khi nâng và khởi động, enable lại. Nếu source cluster cũ hơn 17.0, pg_upgrade không tự migrate các logical slots/subscription dependencies theo cơ chế này; cần quy trình tái tạo riêng.

### 14.4. Không nhầm logical slot với physical standby slot

Logical replication slot giữ WAL cho logical decoding consumer. Physical replication slot giữ WAL cho physical standby. Mỗi loại có owner, lifecycle và yêu cầu migration khác nhau. Inventory và recreate theo đúng consumer, không tạo một slot mới chỉ dựa vào tên cũ.

---

## 15. Những sai lầm thường gặp

**1. “Cài PostgreSQL major mới trên standby rồi restart là xong.”** Sai. Physical replication không chuyển qua major versions như vậy; phải nâng/rebuild standby theo quy trình tương ứng.

**2. “Có thể chạy pg_upgrade độc lập trên từng standby.”** Sai trong mô hình thông thường. New cluster identity và data state có thể không khớp primary. Dùng rsync link-mode procedure hoặc dựng lại standby.

**3. “Primary mới chạy rồi có thể rsync standby sau.”** Sai với link-mode standby procedure. Hoàn tất rsync trước khi start new primary/standbys theo thứ tự tài liệu.

**4. “Link mode vẫn giữ old cluster để rollback.”** Sai. Sau khi new cluster được khởi động, old cluster không thể dùng vì relation files được hard-link chia sẻ.

**5. “pg_upgrade tự cập nhật mọi extension.”** Sai. Cần target shared libraries và các bước extension update riêng.

**6. “pg_upgrade chuyển planner statistics.”** Sai. Cần analyze lại để planner có statistics phù hợp.

**7. “Logical replication tự replicate DDL.”** Sai. Schema changes phải được đồng bộ riêng.

**8. “Logical replication chuyển sequence values.”** Sai. Phải đồng bộ sequence state trước cutover.

**9. “Logical replication chuyển large objects.”** Sai. Large objects không được built-in logical replication replicate.

**10. “Subscriber có thể nhận writes song song với publisher mà không có conflict.”** Sai. Cutover phải kiểm soát một phía nhận writes hoặc có thiết kế multi-writer riêng.

**11. “Backup vật lý old major có thể restore vào target major.”** Không được giả định như vậy. Giữ old binaries/restore environment để khôi phục old backups.

**12. “Backup command chạy thành công chứng minh restore dùng được.”** Sai. Phải thực hiện restore rehearsal và PITR test.

**13. “Nâng backup tool sau cùng luôn an toàn.”** Sai. Target PostgreSQL có thể cần tool version mới; chuẩn bị tooling trước khi cutover để old và target đều được bảo vệ.

**14. “Nâng tool version đồng nghĩa repository format đã được nâng.”** Sai. Binary version và repository format là hai việc khác nhau.

**15. “Chạy stanza-upgrade cho mọi backup tool.”** Sai. Đây là lệnh đặc thù pgBackRest; Barman/WAL-G có quy trình riêng.

**16. “Có thể prune old backups ngay sau cutover.”** Sai. Giữ old backup/WAL trong rollback window và retention đã phê duyệt.

**17. “Archive count tăng nghĩa là PITR hoạt động.”** Sai. Cần restore một backup và replay WAL đến target time.

**18. “Replication lag bằng 0 một lần là đủ.”** Sai. Kiểm tra state/LSN trong suốt cutover và xác nhận standby tiếp tục replay.

**19. “Đổi DNS là hoàn tất cutover.”** Sai. Còn connection pools, background workers, scheduled jobs, monitoring và failover manager.

**20. “Có thể quay lại old primary sau khi new primary nhận writes.”** Không trực tiếp. Old cluster đã stale; cần reverse replication hoặc reconcile changes.

**21. “pg_upgrade --check đảm bảo production upgrade sẽ thành công.”** Sai. Đây là kiểm tra compatibility; vẫn cần rehearsal, backup và cutover runbook.

**22. “Không cần đọc release notes của major versions trung gian.”** Sai. Các thay đổi tích lũy qua từng major có thể ảnh hưởng upgrade.

**23. “Old standby slot tự được copy đầy đủ.”** Sai. Hành vi phụ thuộc source major và slot type; kiểm tra và recreate theo tài liệu.

**24. “Một restore test của old cluster chứng minh backup mới restore được.”** Sai. Sau cutover phải tạo và thử restore backup target major riêng.

---

## 16. Runbook mẫu: PostgreSQL 16 lên 17 bằng pg_upgrade

### 16.1. Giả định topology

Ví dụ có:

- Primary PostgreSQL 16.
- Hai physical standbys PostgreSQL 16.
- Backup tool pgBackRest.
- Target PostgreSQL 17.
- Có cửa sổ downtime để dừng writes.
- Chọn pg_upgrade link mode để rút ngắn thời gian chuyển data files.

Đây là runbook minh họa, không phải lệnh copy/paste cho mọi distro. Paths, service names, repository IDs, extension packages và HA manager phải thay bằng thông tin thực tế.

### 16.2. Trước maintenance window

1. Đọc PostgreSQL 17 migration notes và pg_upgrade documentation.
2. Xác nhận pgBackRest release hỗ trợ PostgreSQL 17 và đọc được repository hiện tại.
3. Cài PostgreSQL 17 binaries và extension packages trên cả ba database hosts.
4. Kiểm tra đủ filesystem capacity và link mode support.
5. Tạo backup đầy đủ PostgreSQL 16 và kiểm tra WAL archive.
6. Restore thử backup vào môi trường cô lập.
7. Chạy pg_upgrade --check với --link.
8. Kiểm tra replication slots, tablespaces, relocated pg_wal và custom config.
9. Ghi baseline LSN/checkpoint và application metrics.
10. Thông báo downtime và chuẩn bị maintenance mode.

### 16.3. Bắt đầu cutover

1. Dừng application writes, workers, ETL và scheduled jobs.
2. Drain connection pools.
3. Chờ transactions cần thiết hoàn tất.
4. Xác nhận hai standbys đang caught up.
5. Dừng old primary theo runbook để old standbys nhận được WAL cuối cùng.
6. Dừng old standbys.
7. Dùng pg_controldata so sánh Latest checkpoint location trên primary và từng standby.
8. Nếu checkpoint locations không khớp, dừng quy trình và xử lý lag.

### 16.4. Nâng primary

1. Xác nhận target config có wal_level phù hợp cho replication.
2. Chạy pg_upgrade target binary với old/new data directories, old/new binary paths, jobs và --link.
3. Đọc output, warnings và generated scripts.
4. Không start new primary.

### 16.5. Nâng standbys bằng rsync

Trên từng standby:

1. Xác nhận target data directory không tồn tại hoặc rỗng.
2. Lưu config files cũ cần giữ.
3. Chạy rsync hard-link procedure từ primary đã nâng.
4. Đồng bộ riêng tablespaces và relocated pg_wal nếu có.
5. Cấu hình primary_conninfo, slots, archive/restore settings và HA manager.
6. Recreate slots theo source major/slot type.
7. Kiểm tra ownership và permissions.

### 16.6. Khởi động target cluster

1. Restore pg_hba.conf/config của primary.
2. Start new primary.
3. Kiểm tra logs và chạy post-upgrade scripts.
4. Chạy extension updates cần thiết.
5. Chạy vacuumdb --all --analyze-in-stages hoặc analyze scripts do pg_upgrade tạo.
6. Start từng standby.
7. Kiểm tra streaming, replay LSN, sync_state và slots.

### 16.7. Chuyển backup tooling

1. Cập nhật pgBackRest pg-path sang data directory PostgreSQL 17 trên tất cả hosts.
2. Chạy stanza-upgrade cho từng repository.
3. Kiểm tra stanza/info và WAL archive.
4. Chạy backup mới của PostgreSQL 17.
5. Restore thử backup mới và replay WAL.
6. Giữ PostgreSQL 16 backups/WAL trong rollback window.

### 16.8. Mở lại ứng dụng

1. Smoke test đọc/ghi và transaction critical.
2. Kiểm tra connection pool và endpoint.
3. Bật background workers và schedulers theo thứ tự.
4. Mở writes.
5. Theo dõi errors, latency, replication lag, WAL/archive và disk usage.
6. Ghi nhận thời điểm rollback window kết thúc.

---

## 17. Bài tập thực hành và đáp án

### Bài 1 — Minor và major

**Câu hỏi:** Nâng PostgreSQL 17.3 lên 17.6 có cần pg_upgrade không?

**Đáp án:** Không. Đây là minor update trong cùng major; thay binaries/restart theo quy trình tương thích của cluster.

### Bài 2 — Major version

**Câu hỏi:** Vì sao không thể thay binary PostgreSQL 16 bằng PostgreSQL 17 rồi start data directory cũ?

**Đáp án:** Major versions có thể thay đổi internal storage/catalog format; cần pg_upgrade, dump/restore hoặc replication migration.

### Bài 3 — Physical replication

**Câu hỏi:** Standby PostgreSQL 16 có thể replay WAL từ primary PostgreSQL 17 không?

**Đáp án:** Không. Physical replication cần cùng major version và cluster identity.

### Bài 4 — Standby link mode

**Câu hỏi:** Nếu primary dùng pg_upgrade --link, standby có thể được nâng bằng cách nào?

**Đáp án:** Dùng rsync hard-link procedure chính thức từ primary đã nâng, trước khi start cluster mới.

### Bài 5 — Standby non-link

**Câu hỏi:** Nếu dùng copy mode, cách đơn giản để nâng standby là gì?

**Đáp án:** Tạo lại standby từ new primary bằng base backup hoặc backup/restore procedure.

### Bài 6 — Checkpoint LSN

**Câu hỏi:** Trước rsync link-mode, cần xác nhận gì giữa old primary và standbys?

**Đáp án:** Latest checkpoint location trong pg_controldata phải khớp.

### Bài 7 — Link mode rollback

**Câu hỏi:** Có thể dùng old cluster sau khi new cluster đã start trong link mode không?

**Đáp án:** Không. Old/new relation files dùng hard links chung.

### Bài 8 — Extension

**Câu hỏi:** Vì sao cần cài extension shared objects target major trước pg_upgrade?

**Đáp án:** Server mới cần load đúng shared libraries; extension C binary phải tương thích target major.

### Bài 9 — Logical replication

**Câu hỏi:** Logical replication có replicate DDL không?

**Đáp án:** Không. Schema changes phải apply riêng trên subscriber.

### Bài 10 — Sequence

**Câu hỏi:** Vì sao phải sync sequence trước logical cutover?

**Đáp án:** Sequence state không được logical replication replicate; target có thể cấp ID trùng hoặc lùi.

### Bài 11 — Large objects

**Câu hỏi:** Built-in logical replication có replicate large objects không?

**Đáp án:** Không.

### Bài 12 — Publication

**Câu hỏi:** Object nào có thể đưa vào publication thông thường?

**Đáp án:** Tables, gồm partitioned tables theo quy tắc của PostgreSQL; views/materialized views/foreign tables không được replicate như ordinary tables.

### Bài 13 — Backup tool order

**Câu hỏi:** Vì sao nên nâng backup tool trước khi nâng PostgreSQL?

**Đáp án:** Tool mới có thể cần thiết để backup/restore target major; chuẩn bị trước giúp vẫn bảo vệ old cluster và target cluster trong cutover.

### Bài 14 — Repository format

**Câu hỏi:** Nâng backup tool binary có luôn đồng nghĩa repository format được nâng không?

**Đáp án:** Không. Hai việc riêng; phải theo tài liệu vendor.

### Bài 15 — pgBackRest

**Câu hỏi:** Sau major upgrade PostgreSQL, pgBackRest cần thao tác gì theo hướng dẫn?

**Đáp án:** Cập nhật pg-path và chạy stanza-upgrade cho các repositories tương ứng.

### Bài 16 — WAL archive

**Câu hỏi:** archived_count tăng có chứng minh PITR hoạt động không?

**Đáp án:** Không. Cần restore backup và replay WAL tới recovery target.

### Bài 17 — Optimizer statistics

**Câu hỏi:** pg_upgrade có chuyển planner statistics đầy đủ không?

**Đáp án:** Không. Chạy analyze sau upgrade.

### Bài 18 — Old backups

**Câu hỏi:** Có nên prune old backup chain ngay sau cutover?

**Đáp án:** Không. Giữ trong rollback/retention window và chỉ xóa sau khi backup mới restore được.

### Bài 19 — Cutover writes

**Câu hỏi:** Vì sao không cho old và new primary cùng nhận writes?

**Đáp án:** Có nguy cơ split-brain và divergence; chỉ một phía nhận writes trừ khi có kiến trúc multi-writer chuyên biệt.

### Bài 20 — Rollback

**Câu hỏi:** Sau khi target đã nhận writes mới, có thể chỉ đổi endpoint về old primary không?

**Đáp án:** Không. Old cluster stale; cần reverse replication hoặc reconciliation/restore.

### Bài 21 — Replication slots

**Câu hỏi:** Slot behavior trong standby rsync procedure có khác theo old major version không?

**Đáp án:** Có. Với old primary trước 17.0 không slots nào được copy; từ 17.0 chỉ logical slots trên primary được copy, các slots khác cần recreate theo tài liệu.

### Bài 22 — Restore test

**Câu hỏi:** Backup job exit code 0 đã đủ để chứng minh backup có thể dùng chưa?

**Đáp án:** Chưa. Cần restore rehearsal và PITR test.

### Bài 23 — Logical replication version upgrade

**Câu hỏi:** PostgreSQL 18 có thể migrate logical replication cluster bằng pg_upgrade trong mọi source version không?

**Đáp án:** Không. Cơ chế này chỉ hỗ trợ khi tất cả members của old logical replication cluster từ PostgreSQL 17.0 trở lên và đáp ứng prerequisites.

### Bài 24 — Release notes

**Câu hỏi:** Nâng PostgreSQL 14 lên 18 có cần đọc migration notes của 15, 16 và 17 không?

**Đáp án:** Có. Cần kiểm tra các thay đổi của mọi major bị bỏ qua.

---

## 18. Checklist thứ tự nâng cấp

### Trước khi thay đổi

1. Ghi source/target PostgreSQL major/minor versions.
2. Đọc migration notes của mọi major bị bỏ qua.
3. Inventory primary, standbys, cascading topology và failover manager.
4. Ghi system identifier, timeline, replication LSN và slots.
5. Inventory extensions, preload modules, tablespaces và custom files.
6. Ghi toàn bộ backup tools, agents, repository formats và restore commands.
7. Xác nhận backup tool hỗ trợ cả old và target PostgreSQL versions.
8. Nâng backup tooling trước nếu target major yêu cầu version mới.
9. Xác nhận tool mới vẫn đọc old backup chain và restore được.
10. Tạo backup đầy đủ và kiểm tra WAL archive.
11. Restore rehearsal và ghi thời gian recovery.
12. Chọn pg_upgrade, logical replication hay dump/restore.
13. Nếu dùng pg_upgrade, chạy --check với đúng mode.
14. Nếu dùng logical replication, chuẩn bị schema, publication, subscription, sequences và large objects.
15. Cài target PostgreSQL binaries/extensions trên mọi hosts.
16. Chuẩn bị target paths, configuration, authentication và network.
17. Ghi baseline metrics và chuẩn bị maintenance mode.

### Trong major cutover

18. Dừng writes, background workers và scheduled jobs.
19. Drain connections và chờ transactions hoàn tất.
20. Xác nhận old standbys caught up.
21. Với pg_upgrade link-mode standby procedure, xác nhận checkpoint locations khớp.
22. Nâng primary bằng pg_upgrade hoặc cutover logical/dump theo runbook.
23. Nâng/rebuild physical standbys theo nhánh link-mode hoặc non-link-mode.
24. Recreate replication slots cần thiết.
25. Cấu hình WAL archive/restore và failover manager.
26. Start new primary rồi standbys theo thứ tự phù hợp.
27. Chạy post-upgrade scripts, extension updates và analyze.

### Sau cutover

28. Cập nhật backup tool paths/catalog/stanza cho target cluster.
29. Tạo backup target major và kiểm tra WAL archiving.
30. Restore thử backup mới và thực hiện PITR test.
31. Kiểm tra replication, slots, sync state và failover readiness.
32. Kiểm tra data consistency, sequences, roles, grants và critical queries.
33. Smoke test application, drivers, pool, jobs và integrations.
34. Theo dõi latency, CPU, I/O, WAL, autovacuum và replication lag.
35. Giữ old backup/WAL và old binaries trong rollback/retention window.
36. Chỉ prune old backup chain khi backup mới đã restore được và rollback window kết thúc.

---

## 19. Tổng kết

Nâng cấp PostgreSQL có primary, physical standbys và backup tools là một quy trình đồng bộ nhiều thành phần. Minor update thường giữ nguyên storage format và có thể rolling theo node trong cùng major version. Major upgrade cần chuyển cluster bằng pg_upgrade, logical replication hoặc dump/restore; sau đó phải chuyển physical standbys và backup workflows sang cluster mới.

Các điểm cần nhớ:

- Physical replication yêu cầu primary/standby cùng major version và cùng cluster identity.
- Với pg_upgrade link mode, PostgreSQL có rsync hard-link procedure để nâng standby; không chạy pg_upgrade độc lập trên từng standby.
- Nếu dùng copy/clone mode hoặc bỏ rsync procedure, dựng lại standbys từ primary mới.
- Trước link-mode standby rsync, xác nhận old primary và standbys ở cùng latest checkpoint location.
- Backup tooling nên được chuẩn bị trước để hỗ trợ old và target versions; repository format phải được nâng theo tài liệu riêng.
- Với pgBackRest, cập nhật pg-path và chạy stanza-upgrade sau major upgrade theo từng repository.
- Logical replication có thể giảm downtime nhưng không tự replicate DDL, sequence state hoặc large objects.
- Dump/restore rõ ràng nhưng có thể tốn thời gian và cần xử lý global objects riêng.
- pg_upgrade không chuyển optimizer statistics đầy đủ; cần analyze sau upgrade.
- Sau cutover, tạo backup target major và thử restore/PITR.
- Không prune old backups trước khi new backups được xác nhận và rollback window kết thúc.
- Sau khi new primary nhận writes, old primary không còn là rollback target trực tiếp.
- Chỉ một primary nhận writes trong cutover để tránh split-brain.

**Câu hỏi tự kiểm tra:** Primary PostgreSQL 16 đã được nâng lên 17 bằng pg_upgrade link mode. Có thể bật lại PostgreSQL 16 standby cũ để nhận WAL từ primary mới không? Không. Phải nâng standby theo rsync hard-link procedure được hỗ trợ hoặc dựng lại standby từ cluster PostgreSQL 17 mới.

### Tài liệu PostgreSQL và backup tooling chính thức

- [Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/18/upgrading.html).
- [pg_upgrade](https://www.postgresql.org/docs/18/pgupgrade.html).
- [Logical Replication — Upgrade](https://www.postgresql.org/docs/18/logical-replication-upgrade.html).
- [Logical Replication — Restrictions](https://www.postgresql.org/docs/18/logical-replication-restrictions.html).
- [Logical Replication — Configuration Settings](https://www.postgresql.org/docs/18/logical-replication-config.html).
- [Logical Replication — Architecture](https://www.postgresql.org/docs/18/logical-replication-architecture.html).
- [pgBackRest User Guide](https://pgbackrest.org/user-guide.html).
- [pgBackRest Command Reference — stanza-upgrade](https://pgbackrest.org/command.html).
- [pgBackRest Release Notes](https://pgbackrest.org/release.html).
- [PostgreSQL Release Notes](https://www.postgresql.org/docs/release/).
