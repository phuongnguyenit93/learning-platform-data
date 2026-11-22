# Phân biệt cập nhật bản phụ và nâng cấp bản chính PostgreSQL

## 1. Vì sao phải phân biệt minor update và major upgrade?

PostgreSQL phát hành các bản cập nhật ở hai mức. **Minor release update** cập nhật một server trong cùng major version line, thường để nhận bug fixes và security fixes. **Major version upgrade** chuyển cluster từ một major version sang major version khác, ví dụ PostgreSQL 16 lên PostgreSQL 17.

Hai công việc này khác nhau về compatibility, data directory, downtime, extensions, replication và rollback. Cài binary mới không đồng nghĩa dữ liệu cũ đã được chuyển đổi. Một cluster PostgreSQL có data directory được tạo bởi major version cụ thể; không thể mặc định khởi động binary major mới trực tiếp trên data directory major cũ.

| Nội dung | Minor update | Major upgrade |
|---|---|---|
| Ví dụ | 17.2 → 17.3 | 16 → 17 |
| Mục tiêu | Bug/security fixes trong cùng major line | Chuyển sang major line mới |
| Data directory format | Giữ tương thích trong major line | Có thể thay đổi |
| pg_upgrade | Thông thường không cần | Thường dùng được |
| Dump/restore | Không cần cho bản thân minor update | Một phương pháp phổ biến |
| Logical migration | Thường không cần | Có thể giảm downtime |
| Application compatibility | Thường ít thay đổi hơn, vẫn cần kiểm tra | Cần kiểm tra kỹ |
| Downtime | Thường cần restart server | Phụ thuộc phương pháp |
| Rollback | Không nên coi downgrade binary là rollback plan | Cần backup hoặc failback strategy |

```text
Minor update:
  PostgreSQL 17.2
       |
       | install compatible 17.3 binaries
       | stop / replace / start
       v
  PostgreSQL 17.3
  Same major data format

Major upgrade:
  PostgreSQL 16 cluster
       |
       | pg_upgrade OR dump/restore
       | OR logical replication migration
       v
  PostgreSQL 17 cluster
  New major data directory / catalogs
```

Một minor update thường đơn giản hơn, nhưng vẫn cần backup, kiểm tra package và restart plan. Một major upgrade là dự án thay đổi nền tảng database: cần đánh giá ứng dụng, extensions, drivers, HA topology, data migration, performance và rollback.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc đúng PostgreSQL version number và phân loại minor/major.
2. Giải thích minor update khác major upgrade ở data format và compatibility.
3. Lập kế hoạch cập nhật package/binary mà không nhầm với chuyển đổi cluster.
4. Chọn giữa pg_upgrade, dump/restore và logical replication.
5. Hiểu copy, link và clone modes của pg_upgrade.
6. Chuẩn bị extension, collation, driver và application compatibility.
7. Lập kế hoạch physical replication, logical replication và CDC consumers.
8. Xác định downtime, cutover và rollback strategy.
9. Chạy preflight checks và pg_upgrade --check.
10. Kiểm tra extensions, indexes, sequences, statistics, jobs và permissions sau upgrade.
11. Xây performance baseline và regression tests.
12. Quản lý managed PostgreSQL, container và package-managed clusters.
13. Thiết kế backup, PITR và recovery plan.
14. Tránh khởi động major binary trên data directory cũ hoặc xóa old cluster quá sớm.
15. Hoàn thành checklist và runbook cho minor update lẫn major upgrade.

---

## 2. Cách đọc PostgreSQL version number

Với PostgreSQL 10 trở lên, version number có dạng major.minor, ví dụ 16.4 hoặc 17.2:
- Số đầu là major version.
- Số thứ hai là minor release trong major line đó.

Ví dụ:
- 16.1 → 16.2: minor update.
- 16.2 → 17.0: major upgrade.

Trước PostgreSQL 10, cách đánh số khác. Ví dụ 9.6.24 thuộc major line 9.6; số cuối là minor release. Không dùng quy tắc hiện đại để đọc nhầm version cũ.

### 2.1. Kiểm tra server đang chạy

```sql
SELECT version();

SHOW server_version;
SHOW server_version_num;
```

server_version là version string của server. server_version_num là số nguyên hữu ích cho script so sánh version.

### 2.2. Client version không phải server version

```bash
psql --version
pg_dump --version
pg_config --version
```

Các lệnh này báo version của client/tool được gọi. Chúng không chứng minh server mà ứng dụng kết nối đang chạy cùng version.

### 2.3. Kiểm tra đúng endpoint

Trong môi trường có proxy, pooler, primary và standby, kết nối tới từng endpoint và ghi lại server version, role, cluster identity. Tránh kiểm tra một node rồi áp kết quả cho toàn topology.

### 2.4. Version của extension là thông tin riêng

Server có thể chạy PostgreSQL 17.2 nhưng extension PostGIS, pg_stat_statements hoặc extension nội bộ có version riêng. Ghi nhận cả server major, package version và extension version.

## 3. Minor release update là gì?

Minor release là bản cập nhật trong cùng major line. PostgreSQL project phát hành minor updates để sửa lỗi, lỗ hổng bảo mật và các vấn đề vận hành đã được xác định.

Một minor update thông thường:
- Giữ nguyên major data directory format.
- Không yêu cầu dump/restore.
- Không yêu cầu pg_upgrade.
- Cần thay binaries/packages theo quy trình hệ điều hành hoặc nhà cung cấp.
- Thường cần restart server để process mới chạy bằng binaries mới.
- Nên cập nhật các nodes trong HA topology theo quy trình được hỗ trợ.

### 3.1. Minor không có nghĩa là không rủi ro

Một bug fix có thể thay đổi behavior của code path từng có bug. Một security fix có thể yêu cầu thay đổi cấu hình hoặc client behavior. Kiểm tra release notes và test workload quan trọng.

### 3.2. Minor update không chuyển data directory

Nếu đang chạy major 16, update từ 16.2 lên 16.3 vẫn thuộc major 16. Không tạo cluster major 17 rồi mong package update tự chuyển dữ liệu.

### 3.3. Restart và downtime

PostgreSQL server process cần được restart để nạp binaries mới. Downtime thực tế phụ thuộc HA, orchestration, connection draining và thời gian startup/recovery.

### 3.4. Không trì hoãn security fixes tùy tiện

Theo dõi release announcements và policy patching của tổ chức. Lập kế hoạch cập nhật định kỳ, kiểm tra backup và áp dụng security updates theo mức độ rủi ro.

## 4. Major version upgrade là gì?

Major upgrade chuyển cluster sang một major version mới, ví dụ PostgreSQL 15 sang 16 hoặc 16 sang 17.

Major release có thể thay đổi:
- System catalogs và internal metadata.
- Data representation hoặc storage behavior.
- SQL syntax/semantics và reserved keywords.
- Planner/executor behavior.
- Replication, monitoring và configuration parameters.
- Extension APIs/ABI.
- Defaults và operational behavior.

Do đó, binary major mới không được giả định có thể mở trực tiếp data directory major cũ.

### 4.1. Các phương pháp phổ biến

- pg_upgrade: chuyển đổi cluster files/catalog sang major mới theo đường upgrade được hỗ trợ.
- Dump/restore: xuất logical objects/data rồi nạp vào cluster mới.
- Logical replication hoặc migration pipeline: đồng bộ changes sang cluster mới rồi cutover.
- Managed service workflow: nhà cung cấp điều phối quy trình được hỗ trợ.

### 4.2. Major upgrade có thể cần application changes

Driver, ORM, extension, SQL behavior, planner plans và configuration defaults có thể thay đổi. Kiểm tra ứng dụng như một phần của upgrade.

### 4.3. Không phải mọi major version đều có thể nhảy trực tiếp

pg_upgrade hỗ trợ các source versions nhất định theo tài liệu từng release. Nếu source quá cũ hoặc đường nâng cấp không được hỗ trợ, cần nâng qua intermediate version hoặc dùng dump/restore.

### 4.4. Không chỉ nâng binary

Major upgrade là chuyển đổi cluster, data và ecosystem. Kế hoạch phải gồm backup, validation, cutover và recovery.

## 5. Data directory compatibility

Data directory chứa database files, system catalogs, WAL và metadata của cluster. PostgreSQL major versions có thể thay đổi internal formats và catalogs.

### 5.1. Không khởi động binary major mới trực tiếp trên old data directory

Ví dụ không chạy PostgreSQL 17 binary trên data directory PostgreSQL 16 như thể đó là minor update. Server có thể từ chối khởi động hoặc cluster có thể bị hỏng nếu thao tác không đúng.

### 5.2. Minor release trong cùng major line

Minor releases được thiết kế tương thích với data format của major line đó. Quy trình cập nhật package/binary không cần chuyển đổi cluster bằng pg_upgrade.

### 5.3. Data directory path có thể khác

Package manager hoặc distribution có thể dùng cluster directories khác nhau theo major version. Xác minh data_directory, service unit và cluster manager trước khi dừng hoặc khởi động.

### 5.4. Không xóa old data directory sớm

Giữ old cluster/backup cho tới khi upgrade được xác minh, rollback window kết thúc và retention policy cho phép cleanup.

## 6. Lập inventory trước khi nâng cấp

Một inventory tốt cần có:
- PostgreSQL server version và package/build.
- Operating system, architecture và filesystem.
- Data directory, tablespaces và WAL directory.
- Database names, owners, sizes và encodings.
- Roles, memberships, grants và tablespaces.
- Extensions và versions.
- Collations/locales.
- Replication slots, publications, subscriptions và downstream consumers.
- Backup/PITR/archive status.
- Application drivers, ORM và connection poolers.
- Scheduled jobs, cron, extensions và external integrations.
- Configuration files, include directories và custom settings.
- Monitoring/exporters và backup agents.
- Current performance baseline và SLOs.

### 6.1. Server và database inventory

```sql
SELECT version();

SELECT
    datname,
    pg_get_userbyid(datdba) AS owner,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
```

### 6.2. Extensions

```sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS schema_name
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
ORDER BY e.extname;
```

### 6.3. Replication topology

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

Chạy trên primary; kết quả phụ thuộc role và version. Kiểm kê riêng logical slots, publications/subscriptions và CDC consumers.

### 6.4. Configuration inventory

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
ORDER BY name;
```

Không copy toàn bộ old configuration vào major version mới mà không review. Một số parameters có thể bị đổi tên, xóa, thay default hoặc không còn ý nghĩa.

## 7. Đọc release notes và compatibility changes

Trước upgrade, đọc:
- Release notes của mọi major version sẽ đi qua.
- Upgrade documentation của target major.
- Extension compatibility matrix.
- OS/package release notes.
- Cloud provider maintenance/upgrade documentation nếu dùng managed service.
- Driver/ORM release notes.
- HA manager/proxy/pooler compatibility.

### 7.1. Removed/renamed parameters

Một parameter cũ có thể bị bỏ hoặc thay thế. Server có thể log warning hoặc không khởi động nếu config chứa setting không hợp lệ tùy cách quản lý.

### 7.2. SQL behavior

Reserved keywords, planner behavior, function signatures và type behavior có thể thay đổi. Chạy integration tests và query corpus.

### 7.3. Authentication/TLS

Kiểm tra password encryption, authentication methods, certificates, TLS libraries và client compatibility.

### 7.4. Defaults

Một default mới có thể ảnh hưởng memory, planner, parallelism, WAL hoặc maintenance. So sánh pg_settings old/new thay vì copy cấu hình cũ nguyên xi.

## 8. Phương pháp 1: cập nhật minor release

Quy trình tổng quát:

1. Xác nhận major line hiện tại và target minor release.
2. Đọc release notes và security advisories.
3. Kiểm tra backup và restore readiness.
4. Kiểm tra package/binary đúng OS/architecture.
5. Lập kế hoạch restart/failover.
6. Drain hoặc chuyển traffic theo HA runbook.
7. Cập nhật binaries/packages.
8. Khởi động server bằng cùng major data directory.
9. Kiểm tra server version, logs, extensions và connectivity.
10. Kiểm tra replication, backups, jobs và application health.
11. Cập nhật các nodes còn lại theo topology plan.
12. Lưu kết quả và đóng change.

### 8.1. Backup vẫn cần thiết

Dù minor release tương thích data format, backup/PITR là lớp bảo vệ cho lỗi vận hành, package issue hoặc bug regression.

### 8.2. Không thay đổi nhiều thứ cùng lúc

Tránh kết hợp minor update với OS upgrade, major extension upgrade, schema migration và config overhaul nếu không có test riêng. Thay đổi tách biệt giúp rollback và root-cause analysis rõ hơn.

### 8.3. Kiểm tra package source

Dùng repository/package được hỗ trợ và xác minh binary path. Một máy có thể cài nhiều major versions song song.

### 8.4. Kiểm tra service thực sự chạy binary mới

psql --version chỉ cho biết client. Dùng SELECT version() từ server và kiểm tra process/service executable khi cần.

## 9. Minor update trong HA topology

Với physical streaming replication, primary và standby thường cần được duy trì trong cùng major line. Minor update có thể được triển khai theo thứ tự để giảm downtime, nhưng thứ tự và khả năng chạy tạm thời các minor builds khác nhau phải theo tài liệu PostgreSQL, HA manager và nhà cung cấp.

Một kế hoạch phổ biến trong hệ thống hỗ trợ rolling minor update:
1. Xác nhận standby khỏe, replay lag thấp và failover-ready.
2. Cập nhật standby theo quy trình.
3. Kiểm tra standby reconnect/replay.
4. Thực hiện switchover/failover nếu thiết kế hỗ trợ và đã test.
5. Cập nhật node trở thành standby.
6. Xác minh toàn topology cùng target minor.

### 9.1. Không tự suy ra rolling update được hỗ trợ

Một số orchestration/provider có quy trình riêng. Nếu không hỗ trợ mixed minor state hoặc yêu cầu restart toàn cluster, làm theo hướng dẫn đó.

### 9.2. Synchronous replication

Theo dõi synchronous_standby_names, sync_state và khả năng commit trong khi restart từng node. Một synchronous standby bị dừng có thể làm commit chờ hoặc giảm redundancy.

### 9.3. Failover readiness

Kiểm tra fencing, promotion policy, replication slots, archive và application routing. Không chỉ nhìn node process đang running.

### 9.4. Hoàn tất trên mọi node

Sau change window, ghi nhận version từng primary, standby, backup server và logical consumers. Tránh topology bị bỏ quên ở bản cũ.

## 10. Major upgrade: chọn phương pháp

| Phương pháp | Cách hoạt động | Downtime | Ưu điểm | Trade-off |
|---|---|---|---|---|
| pg_upgrade | Chuyển cluster files/catalog sang major mới | Cần cửa sổ cutover | Nhanh với cluster lớn | Cần tương thích source/target, extension và storage |
| Dump/restore | Export logical objects/data, import vào cluster mới | Có thể dài | Portable, tái tạo logical data | Chậm với dataset lớn, cần xử lý globals/ownership |
| Logical replication | Copy baseline rồi apply changes liên tục | Có thể giảm downtime | Blue-green/cutover linh hoạt | DDL/sequences và một số object phải quản lý riêng |
| Managed upgrade | Provider điều phối upgrade | Theo service workflow | Tích hợp hạ tầng dịch vụ | Ít quyền kiểm soát, phụ thuộc provider |

### 10.1. Không có một phương pháp tốt nhất cho mọi cluster

Quyết định dựa trên data size, downtime budget, version path, extensions, replication topology, disk capacity và khả năng test.

### 10.2. pg_upgrade phù hợp khi

Source/target versions được hỗ trợ, extensions tương thích và muốn chuyển đổi nhanh mà không dump/restore toàn bộ dữ liệu.

### 10.3. Dump/restore phù hợp khi

Muốn portability, thay đổi layout/schema, chuyển platform/architecture hoặc pg_upgrade không hỗ trợ source path. Thời gian restore có thể lớn.

### 10.4. Logical replication phù hợp khi

Cần đồng bộ changes sang cluster mới trong khi old cluster tiếp tục nhận writes, có khả năng thiết kế DDL/sequence/cutover và xử lý các limitations.

## 11. Phương pháp 2: pg_upgrade

pg_upgrade nâng cấp data files của một cluster sang format của major version mới theo đường upgrade được hỗ trợ. Nó không đơn giản là copy toàn bộ directory.

Quy trình tổng quát:
1. Cài binaries target major.
2. Cài extension libraries target-compatible.
3. Tạo/init target cluster với cấu hình phù hợp.
4. Dừng old cluster theo yêu cầu.
5. Chạy preflight/pg_upgrade --check.
6. Chạy pg_upgrade với mode đã chọn.
7. Chạy scripts sau upgrade do tool tạo/đề xuất.
8. Khởi động target cluster.
9. Validate và chuyển application traffic.

### 11.1. Kiểm tra upgrade path

Đọc tài liệu pg_upgrade của target version để xác nhận source major được hỗ trợ. Không đoán rằng có thể nhảy trực tiếp qua nhiều major versions.

### 11.2. Hai binary directories

pg_upgrade cần biết old và new executable directories cùng old/new data directories. Đảm bảo đúng binary của từng major, không nhầm PATH.

### 11.3. Old cluster phải được chuẩn bị đúng

Dừng server, kiểm tra không còn process ghi, xử lý prepared transactions và tuân theo các yêu cầu của pg_upgrade/version.

### 11.4. Preflight trước maintenance window

Chạy --check và xử lý mọi failure trước ngày cutover. Không để lần đầu chạy pg_upgrade là trong outage window.

## 12. pg_upgrade --check

Ví dụ command minh họa:

```bash
pg_upgrade \
  --old-bindir=/usr/lib/postgresql/16/bin \
  --new-bindir=/usr/lib/postgresql/17/bin \
  --old-datadir=/var/lib/postgresql/16/main \
  --new-datadir=/var/lib/postgresql/17/main \
  --check
```

Đường dẫn là ví dụ; thay bằng package layout thực tế. Trên Windows hoặc managed environment, cách gọi và paths có thể khác.

### 12.1. --check không chuyển đổi cluster

Đây là preflight mode để kiểm tra các điều kiện upgrade. Nó không thay thế backup, rehearsal hoặc validation sau upgrade.

### 12.2. Đọc toàn bộ output

Một lỗi extension library, unsupported data type hoặc prerequisite có thể làm upgrade không thể tiếp tục. Lưu output và sửa từng blocker.

### 12.3. Kiểm tra lại sau khi sửa

Sau khi cài extension package, sửa config hoặc xử lý object, chạy lại --check để xác nhận.

### 12.4. Không bỏ qua warning

Một số warning yêu cầu review thủ công hoặc chạy script. Ghi owner và action trước cutover.

## 13. pg_upgrade copy, link và clone modes

pg_upgrade có các cách chuyển data files, tùy version/platform:

| Mode | Cách làm | Đặc điểm |
|---|---|---|
| Copy | Copy files sang new cluster | Tốn disk/time hơn, old cluster files được giữ độc lập |
| Link | Hard-link files khi điều kiện filesystem đáp ứng | Nhanh, tiết kiệm disk; old cluster không còn an toàn để chạy sau khi new cluster bắt đầu ghi |
| Clone | Dùng filesystem reflink/clone khi hỗ trợ | Có thể nhanh và tiết kiệm block ban đầu; phụ thuộc filesystem/platform |

### 13.1. Copy mode

Copy thường là lựa chọn dễ hiểu cho rollback storage vì old data files không dùng chung inode với new cluster. Cần đủ disk và thời gian copy.

### 13.2. Link mode

Hard links cho phép chuyển đổi nhanh, nhưng khi new cluster ghi vào shared files, old cluster không còn là bản rollback an toàn. Không khởi động old cluster như thể dữ liệu độc lập.

### 13.3. Clone mode

Clone/reflink phụ thuộc filesystem và support của pg_upgrade/platform. Kiểm tra hỗ trợ thực tế; không giả định mọi volume/cloud filesystem đều hỗ trợ.

### 13.4. Chọn mode theo rollback plan

Nếu cần giữ old cluster để quay lại, copy hoặc clone phù hợp hơn link, nhưng vẫn cần hiểu rằng new writes sau cutover không tự xuất hiện trong old cluster.

## 14. Dump/restore cho major upgrade

Dump/restore chuyển logical schema và data từ old cluster sang new cluster.

Ví dụ tạo custom-format dump:

```bash
pg_dump -Fc -d appdb -f appdb.dump
```

Tạo database mới và restore:

```bash
createdb -T template0 appdb
pg_restore -d appdb --jobs=4 appdb.dump
```

Global objects như roles và tablespaces cần được xử lý riêng, ví dụ:

```bash
pg_dumpall --globals-only > globals.sql
```

Các lệnh minh họa; xác minh version của tools, connection, permissions, owner và environment.

### 14.1. Dump format

Custom/directory formats hỗ trợ parallel restore qua pg_restore. Plain SQL phù hợp pipeline đơn giản nhưng không có cùng khả năng parallel restore.

### 14.2. Roles và grants

Database dump không tự thay thế đầy đủ global objects. Kiểm kê roles, memberships, password/auth settings và tablespaces.

### 14.3. Extensions

Cài extension binaries tương thích trên target trước khi restore các extension objects. Có thể cần tạo extension và restore dữ liệu theo hướng dẫn của extension.

### 14.4. Downtime

Nếu dump được lấy khi old cluster tiếp tục nhận writes, cần consistency/cutover strategy. Một dump đơn lẻ không tự đồng bộ các writes phát sinh sau snapshot.

## 15. Logical replication migration

Logical replication có thể giúp xây cluster major mới trong khi old cluster vẫn phục vụ writes:
1. Chuẩn bị schema tương thích trên target.
2. Tạo publication trên source.
3. Tạo subscription trên target.
4. Copy initial data.
5. Apply changes liên tục.
6. Theo dõi lag và errors.
7. Chuẩn bị cutover window.
8. Dừng writes vào source.
9. Chờ target apply hết changes.
10. Đồng bộ sequence state và các objects ngoài publication.
11. Chuyển application sang target.
12. Xác minh rồi mới retire source.

### 15.1. DDL không tự được logical replication truyền

Schema changes phải được áp dụng thủ công/qua migration pipeline trên target theo thứ tự tương thích.

### 15.2. Sequence state cần xử lý riêng

Logical replication không tự đồng bộ sequence values như table rows. Trước cutover, xác định và đồng bộ sequence state để tránh duplicate IDs.

### 15.3. Object limitations

Một số object/data paths không thuộc logical table replication, chẳng hạn large objects và global objects. Xác minh limitations theo version và extension.

### 15.4. Initial sync và data validation

Copy completion không chứng minh mọi business invariant đã đúng. So sánh row counts, key ranges, checksums/aggregates và constraints.

## 16. Blue-green upgrade

Blue-green là cách vận hành hai environments:
- Blue: cluster hiện tại đang phục vụ traffic.
- Green: cluster major mới được chuẩn bị và đồng bộ.
- Cutover: chuyển application traffic sang green sau khi đạt điều kiện.

Logical replication hoặc một migration pipeline khác có thể duy trì green gần kịp blue.

### 16.1. Blue tiếp tục phục vụ trong lúc chuẩn bị

Giảm downtime nhưng tạo thêm complexity: replication lag, DDL compatibility, writes và cutover coordination.

### 16.2. Freeze writes

Trước cutover, dừng/queue writes vào blue theo kế hoạch để xác định điểm đồng bộ cuối cùng.

### 16.3. Drain connections

Chuyển application pools, background workers, scheduled jobs và external integrations sang green. Không chỉ đổi endpoint cho web server.

### 16.4. Không dual-write tùy tiện

Ghi đồng thời vào cả blue và green có thể tạo divergence và ordering problems. Dùng một source of truth trong migration window.

## 17. Chuẩn bị extensions

Extensions có thể chứa SQL objects, shared libraries, C functions, background workers, types/operators, index access methods và upgrade scripts.

### 17.1. Binary compatibility

Extension shared libraries thường cần build/package tương thích với major PostgreSQL mới. Binary cũ không mặc định load được trên major mới.

### 17.2. Cài package trước pg_upgrade

Nếu pg_upgrade yêu cầu extension libraries trên target, cài đúng package/version trước khi chạy preflight.

### 17.3. SQL extension version

Kiểm tra extversion trên old cluster và available extension versions trên target.

```sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
```

### 17.4. ALTER EXTENSION UPDATE

Sau khi cài binary và update scripts tương ứng:

```sql
ALTER EXTENSION extension_name UPDATE;
```

Thay tên extension và version target theo tài liệu extension. Không phải extension nào cũng hỗ trợ mọi đường upgrade.

### 17.5. Extension-specific upgrade path

PostGIS, TimescaleDB, pg_partman và extension nội bộ có quy trình riêng. Theo dõi compatibility matrix, intermediate steps và required maintenance.

## 18. Collation và locale changes

Collation quyết định thứ tự/so sánh text. OS libc hoặc ICU version mới có thể thay đổi collation behavior.

### 18.1. Vì sao cần chú ý?

Index được xây theo collation cũ có thể không còn thứ tự phù hợp với collation mới. Điều này có thể làm kết quả sort/lookup sai nếu không xử lý.

### 18.2. Kiểm tra collation versions

Trên các version hỗ trợ:

```sql
SELECT
    oid,
    collname,
    collversion,
    pg_collation_actual_version(oid) AS actual_version
FROM pg_collation
WHERE collversion IS DISTINCT FROM pg_collation_actual_version(oid);
```

Query cần được điều chỉnh cho catalog/version và quyền thực tế.

### 18.3. Reindex affected objects

Khi collation version thay đổi, xác định indexes phụ thuộc collation và reindex theo hướng dẫn. Không chỉ refresh metadata rồi coi index đã được xây lại.

### 18.4. Database default collation

Locale của database và collation riêng của columns có thể khác. Inventory tất cả collations quan trọng.

## 19. Application, driver và ORM compatibility

Major upgrade cần test:
- Driver libpq/JDBC/Npgsql/psycopg/Node clients.
- ORM dialect và generated SQL.
- Prepared statements.
- Connection pooler/proxy.
- Authentication/TLS.
- SQL syntax và reserved words.
- Data types, timestamps, JSON, arrays, ranges.
- Error handling và SQLSTATE.
- Transaction isolation assumptions.
- COPY/import/export workflows.

### 19.1. Driver support

Cập nhật driver theo version matrix và kiểm tra TLS/authentication. Không mặc định client binary cũ tương thích mọi server major mới.

### 19.2. Prepared statements

Planner hoặc server behavior thay đổi có thể ảnh hưởng prepared statements/generic plans. Test query paths và pooler mode.

### 19.3. ORM generated SQL

ORM upgrade hoặc PostgreSQL dialect change có thể tạo SQL khác. Lưu query corpus và chạy integration tests.

### 19.4. Authentication

Kiểm tra password encryption, SCRAM, certificate validation, pg_hba.conf và client library support.

## 20. Configuration review

Không copy nguyên file postgresql.conf cũ vào target.

Các nhóm cần review:
- Memory: shared_buffers, work_mem, maintenance_work_mem.
- WAL/checkpoints: max_wal_size, checkpoint_timeout, wal_compression.
- Replication: max_wal_senders, max_replication_slots, wal_level.
- Connections: max_connections, reserved connection settings.
- Parallelism: worker limits, parallel costs.
- Vacuum: autovacuum settings, freeze thresholds.
- Logging: log_line_prefix, duration, lock waits.
- Planner: cost parameters, statistics targets.
- SSL/authentication.
- Extension-specific settings.

### 20.1. Removed parameters

Xóa hoặc thay thế settings không còn được hỗ trợ theo target release notes.

### 20.2. Changed defaults

So sánh old effective values với new defaults. Không cần override mọi default cũ nếu target có behavior tốt hơn, nhưng phải test.

### 20.3. pending_restart

pg_settings.pending_restart giúp nhận biết setting cần restart sau khi thay đổi. Không phải mọi setting đều cần restart.

### 20.4. Configuration files

Kiểm tra include files, ownership, permissions, secrets, service environment và config management.

## 21. Replication và HA sau major upgrade

Physical streaming replication giữa các major versions khác nhau không phải cơ chế nâng cấp thông thường. Standby của major cũ không thể tiếp tục dùng data directory như physical standby của major mới.

### 21.1. Rebuild physical standbys

Sau khi primary được nâng cấp, lập kế hoạch tạo/rebuild physical standbys bằng base backup hoặc công cụ HA được hỗ trợ từ cluster major mới.

### 21.2. Synchronous configuration

Recreate synchronous_standby_names và kiểm tra sync_state, quorum/priority behavior. Không copy topology cũ mà không xác minh node identity.

### 21.3. Replication slots

Kiểm kê physical/logical slots và downstream consumers. Slot compatibility/state qua major upgrade phụ thuộc version/method; không giả định mọi slot tiếp tục hoạt động.

### 21.4. CDC consumers

Debezium, logical decoding consumers và data pipelines cần kiểm tra plugin, slot state, schema changes và offsets. Có thể cần resnapshot/reconfigure.

## 22. Backup và recovery plan trước upgrade

Trước cả minor update lẫn major upgrade:
- Xác minh backup gần nhất.
- Kiểm tra WAL archive liên tục.
- Kiểm tra restore procedure.
- Ghi lại recovery point/objective.
- Xác định storage location độc lập.
- Đảm bảo backup không phụ thuộc duy nhất vào cluster sắp nâng cấp.
- Rehearse restore trên môi trường riêng.

### 22.1. Backup chưa restore test chưa phải bằng chứng recovery

Kiểm tra file tồn tại không chứng minh backup usable. Thực hiện restore test và validation.

### 22.2. Base backup và WAL

PITR cần base backup cùng WAL liên tục tới recovery target. Xác minh archive status và retention.

### 22.3. Backup old cluster trước pg_upgrade

Giữ một backup độc lập. Old data directory không thay thế backup, nhất là khi dùng link mode.

### 22.4. Backup cấu hình và global objects

Lưu config, roles, grants, tablespaces, certificates, secrets references và service definitions theo policy.

## 23. Rollback minor update

Minor releases cùng major line có data format tương thích, nhưng không nên coi việc cài lại old binary là rollback được hỗ trợ trong mọi tình huống.

### 23.1. Đọc vendor/project guidance

Nếu gặp regression, làm theo hướng dẫn cụ thể cho release và package. Một rollback có thể cần restore backup hoặc package downgrade theo quy trình được hỗ trợ.

### 23.2. Không downgrade binary tùy tiện

Dù data format không đổi, bug fixes hoặc catalog behavior có thể làm việc quay lại old binaries không được hỗ trợ như một phương án vận hành.

### 23.3. Rollback qua restore

Nếu cần chắc chắn, restore backup/PITR vào cluster phù hợp và xác minh data loss window. Đây là recovery operation, không chỉ package rollback.

### 23.4. Quyết định trước maintenance

Ghi rõ điều kiện rollback, người quyết định, thời gian tối đa và cách chuyển traffic.

## 24. Rollback major upgrade

Major upgrade khó rollback hơn vì cluster mới có thể nhận writes sau cutover.

### 24.1. Giữ old cluster

Với copy/clone mode hoặc dump/restore, có thể giữ old cluster độc lập trong rollback window. Link mode không giữ old cluster an toàn sau khi new cluster bắt đầu ghi.

### 24.2. Writes sau cutover

Nếu application đã ghi vào new cluster, old cluster không tự nhận các writes đó. Quay lại old cluster có thể làm mất dữ liệu mới.

### 24.3. Failback strategy

Nếu cần rollback sau khi đã mở writes, phải có reverse replication/change capture hoặc business reconciliation plan được thiết kế trước. Không thể chỉ đổi connection string.

### 24.4. Rollback decision deadline

Đặt thời điểm chốt rollback. Sau khi vượt qua, có thể chọn forward-fix thay vì quay lại cluster cũ.

## 25. Downtime planning

Downtime gồm nhiều giai đoạn:
- Stop writes/drain traffic.
- Stop database hoặc freeze source.
- Upgrade/copy/restore/catch-up.
- Start target.
- Run scripts/ANALYZE.
- Validate critical paths.
- Switch application endpoints.
- Warm caches/connection pools.
- Resume background jobs.
- Monitor stabilization.

### 25.1. pg_upgrade

Thường rút ngắn thời gian so với full dump/restore, nhưng vẫn cần downtime cho cutover và thao tác chuyển đổi cuối.

### 25.2. Dump/restore

Thời gian phụ thuộc database size, network, compression, restore parallelism, index build và extension setup.

### 25.3. Logical replication

Có thể chuyển phần lớn copy/catch-up ra ngoài maintenance window, nhưng cutover vẫn cần dừng writes và xác minh target đã bắt kịp.

### 25.4. Rehearsal

Chạy thử trên bản sao production-sized và đo từng phase. Dùng số liệu thực tế để đặt maintenance window.

## 26. Chuẩn bị pg_upgrade target cluster

Trước ngày upgrade:
1. Cài target major binaries.
2. Cài compatible extension libraries.
3. Tạo target data directory.
4. Init target cluster theo yêu cầu pg_upgrade.
5. Review locale/encoding/checksum compatibility.
6. Xác định tablespaces và filesystem.
7. Chuẩn bị config mới.
8. Chạy pg_upgrade --check.
9. Đọc scripts generated sau upgrade.
10. Rehearse trên bản copy.

### 26.1. Tablespace paths

Xác minh tablespace paths và permissions trên target. Đừng để upgrade thành công nhưng service không thể truy cập mount.

### 26.2. Disk capacity

Copy mode cần thêm storage. Clone/link có điều kiện riêng. Tính thêm WAL, temporary files, logs và rollback copy.

### 26.3. Port và service isolation

Old và new clusters cần được khởi động đúng port/endpoint trong rehearsal. Tránh application vô tình kết nối nhầm target chưa validate.

### 26.4. Ownership/permissions

Service user cần quyền đọc/ghi data directory và tablespaces. Kiểm tra owner/group trước startup.

## 27. Cutover checklist cho pg_upgrade

1. Thông báo maintenance và dừng writes.
2. Drain application connections/jobs.
3. Xác minh không còn client sessions ngoài operator.
4. Kiểm tra prepared transactions.
5. Dừng old PostgreSQL cleanly theo yêu cầu.
6. Chạy pg_upgrade với mode đã chọn.
7. Đọc output và xử lý mọi error.
8. Chạy post-upgrade scripts được tạo.
9. Khởi động target cluster.
10. Kiểm tra server version, logs và database connectivity.
11. Chạy ANALYZE/statistics scripts.
12. Validate extensions, indexes, sequences, roles và applications.
13. Rebuild/rejoin HA replicas.
14. Chuyển traffic và theo dõi.
15. Giữ old cluster/backup tới hết rollback window.

### 27.1. Không bỏ qua post-upgrade scripts

pg_upgrade có thể tạo scripts như analyze_new_cluster hoặc delete_old_cluster. Đọc nội dung và thực hiện đúng thứ tự. Không chạy cleanup script trước khi rollback window kết thúc.

### 27.2. Statistics

Planner statistics không nên được giả định đã chuyển đầy đủ. Chạy ANALYZE theo hướng dẫn để planner có statistics phù hợp.

### 27.3. Application traffic

Chỉ mở traffic sau smoke tests và validation của critical operations.

### 27.4. Old cluster cleanup

Xóa old cluster là hành động không dễ đảo ngược. Chỉ cleanup sau khi backup, rollback window và approval/policy đã thỏa.

## 28. Post-upgrade extension validation

Kiểm tra:

```sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
```

Sau đó:
- Xác nhận shared libraries có mặt và đúng major.
- Kiểm tra extension version scripts.
- Chạy ALTER EXTENSION UPDATE khi được yêu cầu.
- Test extension functions/operators/indexes.
- Kiểm tra background workers và jobs.
- Xem server logs để tìm load errors.
- Xác nhận backup/restore hỗ trợ extension mới.

### 28.1. Extension package và SQL version khác nhau

Cài binary package không nhất thiết tự update SQL objects trong database. Kiểm tra cả hai.

### 28.2. Extension không còn được hỗ trợ

Nếu extension không có build cho target major, cần thay thế, nâng cấp theo intermediate path hoặc giữ cluster cũ tới khi có phương án.

### 28.3. Extension có data migration riêng

Một số extensions cần chạy migration scripts hoặc thay đổi storage. Đọc hướng dẫn của vendor/project.

### 28.4. Test index access methods

Extension có custom index access method/operator class cần kiểm tra indexes và query plans sau upgrade.

## 29. Post-upgrade sequence validation

Logical migration/blue-green cần đặc biệt chú ý sequence state. pg_upgrade thường xử lý sequence data trong cluster conversion, nhưng vẫn cần xác minh; dump/restore và logical replication workflows có quy trình riêng.

Liệt kê sequence:

```sql
SELECT
    schemaname,
    sequencename,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size,
    last_value
FROM pg_sequences
ORDER BY schemaname, sequencename;
```

### 29.1. Sequence không giống table rows

Logical replication không tự đồng bộ sequence progression như table changes. Một target có thể có rows mới nhất nhưng sequence next value vẫn thấp hơn key hiện có.

### 29.2. Cutover sequence

Dừng source writes, xác định sequence values an toàn và đặt target state theo migration procedure. Chú ý sequence cache và các sessions đang giữ cached values.

### 29.3. Identity columns

Identity columns dùng sequence bên dưới. Kiểm tra ownership/dependency và next generated value.

### 29.4. Test INSERT thực tế

Dùng transaction/test table phù hợp để xác nhận generated IDs không trùng; không thử bằng cách tạo dữ liệu production tùy tiện.

## 30. Post-upgrade index và constraint validation

Kiểm tra invalid indexes:

```sql
SELECT
    n.nspname,
    c.relname AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_index AS i
JOIN pg_class AS c
  ON c.oid = i.indexrelid
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE NOT i.indisready OR NOT i.indisvalid
ORDER BY n.nspname, c.relname;
```

### 30.1. Indexes sau collation changes

Xác định indexes phụ thuộc collations thay đổi và reindex theo tài liệu.

### 30.2. Constraints

Kiểm tra primary keys, unique, foreign keys, check constraints và validation state.

### 30.3. Extension indexes

Index dùng extension operator classes/access methods cần được test và rebuild nếu extension yêu cầu.

### 30.4. Query plan regression

Một index valid không đảm bảo planner chọn plan tốt. Chạy representative queries và so sánh EXPLAIN.

## 31. Post-upgrade ANALYZE và planner statistics

Sau upgrade, chạy ANALYZE để planner có statistics phù hợp cho target major và data distribution hiện tại.

Một công cụ thường dùng:

```bash
vacuumdb --all --analyze-in-stages
```

Xác minh options và workflow theo target version, database size và maintenance window.

### 31.1. Analyze in stages

Công cụ có thể phân tích statistics theo các giai đoạn để planner có thông tin cơ bản sớm hơn trong lúc hoàn thiện statistics.

### 31.2. Statistics targets

Một số columns có skew/cardinality đặc biệt cần statistics targets hoặc extended statistics riêng. Reapply configuration cần thiết.

### 31.3. Không chạy full maintenance đồng thời tùy tiện

ANALYZE, vacuum, index rebuild và application peak traffic đều dùng tài nguyên. Lập lịch và theo dõi.

### 31.4. Performance baseline

So sánh latency, TPS, query plans, I/O, CPU và temp spill trước/sau. Không kết luận upgrade thành công chỉ vì server start.

## 32. Planner và performance regression

Major upgrade có thể thay đổi planner estimates, cost model và execution strategies. Một số queries nhanh hơn, một số queries chậm hơn.

### 32.1. Query corpus

Thu thập top queries từ pg_stat_statements và critical business operations. Chạy trên staging với data volume tương tự.

### 32.2. Compare plans

Lưu EXPLAIN (ANALYZE, BUFFERS, SETTINGS) trước/sau. So sánh estimated/actual rows, join order, scans, sorts, hash batches và parallelism.

### 32.3. Không force planner settings toàn cục ngay

Nếu một query regression, điều tra statistics/index/query rewrite trước. Planner GUC overrides chỉ dùng có mục tiêu và có owner.

### 32.4. SLO regression gate

Đặt threshold p95/p99, error rate và throughput cho canary/cutover. Nếu vượt ngưỡng, kích hoạt mitigation/rollback decision.

## 33. Major upgrade với logical replication: sequence và DDL

Logical replication hỗ trợ row changes theo publication. Nó không tự thay thế schema deployment hoặc sequence synchronization.

### 33.1. Schema-first

Tạo target schema tương thích trước khi copy/apply. DDL cần được deploy ở hai bên theo thứ tự an toàn.

### 33.2. DDL freeze

Trong migration window, hạn chế schema changes hoặc có quy trình phát chúng đồng thời sang target. Một DDL không đồng bộ có thể làm apply worker lỗi.

### 33.3. Sequence freeze

Trước cutover, dừng writes, xác định final source sequence state và cập nhật target. Chú ý concurrent sessions/sequence cache.

### 33.4. Non-table objects

Roles, grants, functions, procedures, extensions, large objects và configuration phải được xử lý riêng theo phạm vi replication/migration.

## 34. CDC và logical replication slots

Nếu downstream systems đọc WAL/logical decoding, major upgrade có thể ảnh hưởng slots, plugins và offsets.

### 34.1. Inventory consumers

Liệt kê consumer name, slot, plugin, restart_lsn, confirmed_flush_lsn và owner.

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

Một số columns phụ thuộc version/slot type.

### 34.2. Slot không chỉ là metadata

Slot có thể giữ WAL hoặc catalog state. Mất slot có thể yêu cầu consumer resnapshot/resync.

### 34.3. Plugin compatibility

Logical decoding plugin phải có build tương thích với target major và protocol/behavior phù hợp.

### 34.4. Consumer offset coordination

Đồng bộ target cluster với consumer offsets theo migration plan. Không để old/new cluster phát cùng stream gây duplicate side effects mà consumer không deduplicate.

## 35. Managed PostgreSQL upgrade

Managed database providers thường có workflow riêng cho minor patching và major upgrades.

Cần kiểm tra:
- Supported source/target versions.
- Maintenance window.
- Backup/snapshot behavior.
- Failover/replica upgrade order.
- Extension availability.
- Parameter group changes.
- Endpoint behavior.
- Downtime estimates.
- Rollback/restore options.
- Cross-region replicas/read replicas.
- CDC/replication integrations.

### 35.1. Provider-managed không có nghĩa không cần validation

Provider có thể xử lý infrastructure/cluster conversion, nhưng application, SQL, extension và business validation vẫn thuộc hệ thống của bạn.

### 35.2. Read replicas

Xác minh provider nâng cấp/rebuild read replicas như thế nào. Endpoint có thể bị thay đổi hoặc replicas cần tạo lại.

### 35.3. Parameter groups

Một parameter group của major cũ có thể không áp dụng được cho major mới. So sánh và tạo target parameter set.

### 35.4. Restore path

Snapshot restore sang major khác có thể có giới hạn. Đọc provider documentation và test restore/cutover.

## 36. PostgreSQL trong container/Kubernetes

Container image version và data directory version là hai thứ riêng.

### 36.1. Pin image tag

Tránh dùng tag trôi nổi cho production. Pin major/minor hoặc immutable image digest theo release process.

### 36.2. Volume persistence

Thay image từ major 16 sang 17 không tự chuyển data volume. Entry point có thể từ chối data directory cũ hoặc tạo behavior không mong muốn.

### 36.3. StatefulSet rollout

Rolling restart pod không tự là major upgrade. Physical replicas cần cùng major data format và orchestration phù hợp.

### 36.4. Backup/restore volume

Snapshot volume trước maintenance và test restore. Snapshot storage không thay thế logical validation hoặc application cutover plan.

## 37. OS packages và nhiều PostgreSQL versions

Một host có thể cài nhiều major binaries song song. Package manager có thể cập nhật binary package mà không tự chuyển data cluster.

### 37.1. Binary path

Kiểm tra which postgres, pg_config --bindir, service unit và executable thực tế. PATH có thể trỏ tới client/tool version khác.

### 37.2. Cluster manager

Một số distributions có cluster manager quản lý nhiều clusters/ports. Dùng lệnh chính thức của distribution, không giả định systemctl restart postgresql điều khiển đúng cluster.

### 37.3. Service identity

Đảm bảo service chạy đúng user, data directory và config file. Không đổi owner/permissions tùy tiện.

### 37.4. Package repository

Dùng package source tin cậy, kiểm tra signing keys và security updates. Ghi lại package versions để audit.

## 38. Security và compliance trong upgrade

Major/minor updates có thể chứa security fixes hoặc thay đổi crypto/authentication behavior.

Kiểm tra:
- Security advisories.
- CVEs và fixed versions.
- TLS protocols/ciphers/certificates.
- Password authentication method.
- pg_hba.conf rules.
- Role privileges.
- Extension security updates.
- Audit logging.
- Backup encryption.
- Secret rotation.
- Network access/firewall rules.

### 38.1. Không chỉ update server package

Client drivers, extension libraries, backup tools và monitoring agents cũng có thể chứa vulnerabilities hoặc compatibility requirements.

### 38.2. Least privilege

Review roles sau migration. Không cấp superuser cho application chỉ để khắc phục permission mismatch.

### 38.3. Data handling

Dump files có thể chứa toàn bộ production data. Mã hóa, giới hạn access và xóa theo retention policy.

### 38.4. Change evidence

Lưu version, package checksums, backup IDs, approvals, commands, timestamps và validation outcomes.

## 39. Preflight checklist

Trước khi bắt đầu:

- [ ] Xác định source/target major/minor chính xác.
- [ ] Đọc release notes và upgrade documentation.
- [ ] Xác nhận upgrade path được hỗ trợ.
- [ ] Inventory databases, sizes, roles, tablespaces và collations.
- [ ] Inventory extensions và target binaries.
- [ ] Kiểm tra driver, ORM, pooler và application compatibility.
- [ ] Kiểm tra physical/logical replicas, slots và CDC consumers.
- [ ] Xác minh backup, WAL archive và restore test.
- [ ] Rehearse trên bản copy production-sized.
- [ ] Chạy pg_upgrade --check nếu dùng pg_upgrade.
- [ ] Xác nhận disk, temp và rollback capacity.
- [ ] Review target configuration/parameter groups.
- [ ] Đặt downtime window và communication plan.
- [ ] Ghi rõ owner, stop conditions và rollback decision maker.
- [ ] Chuẩn bị validation queries và smoke tests.

## 40. Cutover checklist

Trong cửa sổ nâng cấp:

1. Freeze schema changes và thông báo maintenance.
2. Dừng/queue writes theo migration strategy.
3. Drain application pools, jobs và external writers.
4. Xác minh source không còn writes ngoài kế hoạch.
5. Ghi final LSN/backup/snapshot identifiers.
6. Thực hiện pg_upgrade, restore hoặc logical cutover.
7. Start target và kiểm tra logs.
8. Kiểm tra role/version/database connectivity.
9. Kiểm tra extensions, indexes, constraints và sequences.
10. Chạy ANALYZE theo kế hoạch.
11. Kiểm tra replication/CDC/backup.
12. Chạy smoke tests và critical transactions.
13. Chuyển application traffic.
14. Theo dõi latency, errors, throughput và resource headroom.
15. Giữ old cluster/backup trong rollback window.

## 41. Post-upgrade validation

### 41.1. Server identity và version

```sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
SELECT pg_is_in_recovery();
```

### 41.2. Database accessibility

Kết nối từng database cần thiết; kiểm tra owners, grants, schemas, tablespaces và critical queries.

### 41.3. Extensions

So sánh extension inventory với target compatibility plan. Test extension functions và background workers.

### 41.4. Indexes/constraints

Kiểm tra invalid indexes, constraint validation, collation-dependent indexes và application query plans.

### 41.5. Sequences

Kiểm tra sequence state và generated IDs, đặc biệt sau dump/restore hoặc logical migration.

### 41.6. Jobs và external integrations

Xác minh cron/schedulers, backup, monitoring, CDC, ETL, queue consumers, notifications và reporting.

### 41.7. Application smoke tests

Thực hiện create/read/update/delete theo test data, login/authentication, transaction rollback, prepared statements và critical business flows.

## 42. Performance validation

So sánh baseline old/new:
- p50/p95/p99 query/API latency.
- TPS và business throughput.
- Error/timeout/deadlock rate.
- CPU, memory, swap và disk I/O.
- Connection pool acquire wait.
- Top query plans/durations.
- Temp files and blocks.
- Checkpoint/WAL rate.
- Autovacuum progress và XID age.
- Replication lag/freshness.
- Backup/archive completion.

### 42.1. Warm-up

Target mới có cache state khác. Phân biệt cold-cache startup effects với regression ổn định.

### 42.2. Query plans

Một query thay plan sau upgrade có thể cần ANALYZE hoặc query-specific optimization. Không lập tức revert toàn major upgrade nếu chỉ một query regression.

### 42.3. Representative workload

Chạy peak/batch/reporting workload trong điều kiện kiểm soát. Một smoke test vài queries không đủ.

### 42.4. SLO gate

Đặt điều kiện tiếp tục traffic, giảm traffic hoặc rollback dựa trên metrics và business impact.

## 43. Disaster recovery và PITR sau upgrade

Sau upgrade, cập nhật backup system để tạo base backups tương thích với target major và archive WAL của target cluster.

### 43.1. Backup target mới

Không dựa mãi vào backup old major. Tạo backup mới sau khi target được xác minh.

### 43.2. Restore test target

Thử restore backup của target vào môi trường độc lập và kiểm tra application connectivity.

### 43.3. WAL archive path

Kiểm tra archive command, credentials, object storage permissions, retention và monitoring trên target.

### 43.4. Recovery documentation

Cập nhật runbook: binary path, data directory, service name, version, extension packages, replication topology và PITR instructions.

## 44. Common failure modes

- Khởi động binary major mới trực tiếp trên old data directory.
- Chọn source/target path sai trong pg_upgrade.
- Chạy pg_upgrade lần đầu trong maintenance window.
- Thiếu extension shared library trên target.
- Bỏ qua extension SQL update.
- Dùng pg_dump/pg_restore version không phù hợp.
- Quên roles/global objects/tablespaces.
- Không đồng bộ sequence trước logical cutover.
- Không xử lý collation version changes.
- Không rebuild physical standbys.
- Bỏ sót logical slots/CDC consumers.
- Copy old config nguyên xi sang target.
- Không chạy ANALYZE sau upgrade.
- Xóa old cluster trước khi hết rollback window.
- Quay lại old cluster sau khi target đã nhận writes mà không reconcile.
- Không test drivers, poolers và authentication.
- Không kiểm tra invalid indexes.
- Chỉ xác nhận server start mà không test business transactions.
- Không cập nhật backup/PITR và monitoring.
- Không lưu change evidence.

## 45. Ví dụ lựa chọn phương pháp

### Tình huống A: cluster nhỏ, downtime vài giờ được chấp nhận

Dump/restore có thể phù hợp nếu extension và global objects được hỗ trợ. Rehearse thời gian dump/restore và validate ownership.

### Tình huống B: cluster lớn, downtime ngắn

pg_upgrade có thể phù hợp nếu source/target path được hỗ trợ và đủ extension binaries. Rehearse với bản copy để đo conversion time.

### Tình huống C: workload cần cutover ngắn

Logical replication/blue-green có thể phù hợp nếu application cho phép schema compatibility, sequence synchronization và write freeze ngắn. Thiết kế DDL và CDC trước.

### Tình huống D: managed database

Dùng provider-supported major upgrade workflow, đọc limitations về extensions, replicas, parameter groups, snapshots và endpoints. Test trên staging.

### Tình huống E: source major quá cũ

Xác minh pg_upgrade path. Có thể cần intermediate major hoặc dump/restore. Không tự ý bỏ qua version constraints.

## 46. Bài tập thực hành có đáp án

### Bài 1. Minor update là gì?

**Đáp án:** Cập nhật trong cùng major version line, thường chứa bug fixes và security fixes, giữ data format tương thích trong major line.

### Bài 2. Major upgrade là gì?

**Đáp án:** Chuyển cluster sang major version mới, có thể cần chuyển đổi data directory/catalog format và kiểm tra compatibility.

### Bài 3. 16.2 lên 16.3 là loại thay đổi nào?

**Đáp án:** Minor update.

### Bài 4. 16 lên 17 là loại thay đổi nào?

**Đáp án:** Major upgrade.

### Bài 5. PostgreSQL 9.6.24 được đọc thế nào?

**Đáp án:** Major line là 9.6; 24 là minor release trong line đó.

### Bài 6. Minor update thường có cần pg_upgrade không?

**Đáp án:** Không. Nó được thiết kế để dùng cùng major data directory format.

### Bài 7. Minor update có cần restart server không?

**Đáp án:** Thông thường có để process sử dụng binaries mới; downtime phụ thuộc HA/provider workflow.

### Bài 8. Có thể mở PostgreSQL 16 data directory trực tiếp bằng PostgreSQL 17 binary không?

**Đáp án:** Không. Phải dùng major upgrade procedure được hỗ trợ.

### Bài 9. pg_upgrade làm gì?

**Đáp án:** Chuyển cluster files/catalog từ old major sang new major theo upgrade path được hỗ trợ.

### Bài 10. pg_upgrade --check làm gì?

**Đáp án:** Kiểm tra prerequisite/compatibility mà không thực hiện conversion cuối cùng.

### Bài 11. pg_upgrade copy mode có ưu điểm gì?

**Đáp án:** Old data files độc lập với new cluster, thuận tiện hơn cho rollback storage; đổi lại tốn disk/time.

### Bài 12. Link mode có rủi ro gì?

**Đáp án:** Old và new cluster hard-link chung files; khi new cluster bắt đầu ghi, old cluster không còn an toàn để chạy.

### Bài 13. Clone mode cần gì?

**Đáp án:** Filesystem/platform hỗ trợ reflink/clone và pg_upgrade version hỗ trợ mode đó.

### Bài 14. Dump/restore có thể chuyển gì?

**Đáp án:** Logical schema/data và object definitions theo phạm vi dump/restore; global objects cần xử lý riêng.

### Bài 15. Roles/tablespaces có tự đầy đủ trong pg_dump database dump?

**Đáp án:** Không. Cần inventory và dump/restore global objects riêng khi cần.

### Bài 16. pg_dump -Fc tạo format nào?

**Đáp án:** Custom archive format, có thể dùng pg_restore và parallel restore.

### Bài 17. Vì sao phải kiểm tra pg_dump version?

**Đáp án:** Tool version có compatibility rules; pg_dump không hỗ trợ dump server mới hơn major của chính nó.

### Bài 18. Logical replication có replicate DDL tự động không?

**Đáp án:** Không. Schema changes cần migration riêng.

### Bài 19. Logical replication có tự đồng bộ sequence state không?

**Đáp án:** Không theo cách bảo đảm next value; cần sequence cutover procedure.

### Bài 20. Vì sao blue-green có thể giảm downtime?

**Đáp án:** Green được chuẩn bị/catch up trong khi blue còn phục vụ, chỉ cutover sau khi freeze writes và đồng bộ xong.

### Bài 21. Có nên dual-write blue và green tùy tiện?

**Đáp án:** Không. Có thể tạo divergence/order conflicts; cần một source of truth hoặc protocol được thiết kế.

### Bài 22. Extension binary có cần tương thích major mới?

**Đáp án:** Có. Shared libraries thường cần build/package phù hợp target major.

### Bài 23. ALTER EXTENSION UPDATE dùng để làm gì?

**Đáp án:** Chạy extension SQL update path khi version script tương ứng có sẵn.

### Bài 24. Cài extension package có tự update SQL objects không?

**Đáp án:** Không nhất thiết. Binary package và SQL extension version là hai việc cần xác minh.

### Bài 25. Collation version change có thể yêu cầu gì?

**Đáp án:** Xác định/rebuild các indexes phụ thuộc collation theo hướng dẫn.

### Bài 26. Vì sao không copy postgresql.conf cũ nguyên xi?

**Đáp án:** Một số parameters bị đổi/xóa/default thay đổi hoặc không còn phù hợp target major.

### Bài 27. pg_settings.pending_restart cho biết gì?

**Đáp án:** Setting đã thay đổi nhưng cần restart để có hiệu lực.

### Bài 28. Physical standby old major có thể tiếp tục làm standby cho new major không?

**Đáp án:** Không theo physical streaming replication thông thường; cần rebuild/rejoin từ cluster major mới.

### Bài 29. Replication slots có nên được giả định giữ nguyên qua upgrade?

**Đáp án:** Không. Inventory và kiểm tra behavior theo version/method; downstream consumers có thể cần resync.

### Bài 30. Vì sao cần kiểm tra CDC consumers?

**Đáp án:** Slot/plugin/protocol/offset có thể thay đổi hoặc cần snapshot/resync sau major upgrade.

### Bài 31. Backup file tồn tại có chứng minh restore được?

**Đáp án:** Không. Cần restore test và validation.

### Bài 32. Vì sao cần giữ old cluster sau major upgrade?

**Đáp án:** Làm nguồn rollback/recovery trong thời gian được xác định, nhưng cần xử lý writes phát sinh trên target.

### Bài 33. Có thể rollback bằng cách đổi endpoint về old cluster sau khi target đã nhận writes?

**Đáp án:** Không an toàn nếu không có reverse replication/reconciliation; có thể mất writes mới.

### Bài 34. Vì sao link mode không phù hợp nếu muốn old cluster độc lập?

**Đáp án:** Files dùng hard links; new cluster writes có thể làm old cluster không còn usable.

### Bài 35. Vì sao cần ANALYZE sau pg_upgrade?

**Đáp án:** Planner cần statistics phù hợp để chọn plans tốt; statistics cũ không nên được giả định đầy đủ.

### Bài 36. pg_stat_statements có thể giúp gì sau upgrade?

**Đáp án:** So sánh query calls, total/mean execution time và temp activity để phát hiện regression.

### Bài 37. Vì sao phải test query plans?

**Đáp án:** Planner/executor có thể chọn plan khác giữa major versions.

### Bài 38. Index indisvalid = false có nghĩa gì?

**Đáp án:** Index không được coi là valid để planner sử dụng bình thường; cần điều tra/rebuild theo runbook.

### Bài 39. Sequence state cần chú ý đặc biệt ở phương pháp nào?

**Đáp án:** Dump/restore và logical replication migration; pg_upgrade cũng cần validation nhưng thường xử lý sequence data trong cluster conversion.

### Bài 40. Managed provider upgrade có loại bỏ trách nhiệm validation không?

**Đáp án:** Không. Application, extension, SQL, performance và business validation vẫn cần thực hiện.

### Bài 41. Container image major mới có tự upgrade persistent volume không?

**Đáp án:** Không. Image binary và data directory version là hai thứ riêng.

### Bài 42. Vì sao cần rehearsal trên production-sized copy?

**Đáp án:** Đo thời gian, disk, extension issues, plan behavior và validation với data volume thực tế.

### Bài 43. Major upgrade cần downtime bao nhiêu?

**Đáp án:** Phụ thuộc method, size, network, index build, extension và cutover plan; phải đo qua rehearsal.

### Bài 44. Tại sao phải test driver/ORM?

**Đáp án:** Client protocol, auth, generated SQL, prepared statements và type handling có thể bị ảnh hưởng.

### Bài 45. Khi nào cần intermediate major upgrade?

**Đáp án:** Khi pg_upgrade không hỗ trợ source-to-target direct path hoặc release documentation yêu cầu intermediate step.

### Bài 46. Logical replication có thay backup/PITR không?

**Đáp án:** Không. Nó là migration/replication mechanism, không thay backup và restore strategy.

### Bài 47. Một minor update có cần đọc release notes không?

**Đáp án:** Có. Bug/security fixes và behavior changes có thể ảnh hưởng workload.

### Bài 48. Sau cutover cần kiểm tra những gì?

**Đáp án:** Version/role, extensions, indexes/constraints, sequences, application smoke tests, performance, replication, backup và logs.

### Bài 49. Khi nào nên cleanup old cluster?

**Đáp án:** Chỉ sau khi validation, rollback window, backup và retention policy cho phép.

### Bài 50. Điều kiện hoàn tất major upgrade?

**Đáp án:** Target cluster ổn định, application/business tests đạt, performance/SLO đạt, HA/backup/CDC hoạt động, recovery plan được kiểm chứng và old cluster cleanup theo policy.

## 47. Checklist sau nâng cấp và đóng change

| Nhóm | Xác nhận |
|---|---|
| Version | Server version đúng target trên mọi node? |
| Role | Primary/standby/managed endpoint đúng topology? |
| Data | Databases, schemas, owners, tablespaces đủ? |
| Extensions | Binary và SQL extension versions tương thích? |
| Collation | Version mismatch đã xử lý và indexes cần thiết đã reindex? |
| Indexes | Không còn invalid indexes ngoài kế hoạch? |
| Constraints | FK/unique/check constraints hợp lệ? |
| Sequences | Next generated values an toàn? |
| Config | Parameters đã review, không còn deprecated/unknown settings? |
| Application | Driver, ORM, auth, pool và smoke tests đạt? |
| Performance | Query plans, p95/p99, TPS và resource headroom đạt? |
| HA | Standbys đã rebuild/rejoin và replication khỏe? |
| CDC | Slots, plugins và consumers đã catch up? |
| Backup | Base backup/PITR mới đã chạy? |
| Restore | Restore test target đạt? |
| Jobs | Schedulers, ETL, backup và maintenance hoạt động? |
| Security | TLS, roles, secrets và audit đúng? |
| Rollback | Rollback window và data reconciliation đã chốt? |
| Cleanup | Old cluster chỉ được xóa theo policy? |
| Evidence | Change log, version, backup IDs và validation lưu lại? |

## 48. Tài liệu PostgreSQL chính thức

- [Release Versioning Policy](https://www.postgresql.org/support/versioning/) — major/minor releases và support lifecycle.
- [PostgreSQL Release Notes](https://www.postgresql.org/docs/release/) — thay đổi, bug fixes và security fixes theo release.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) — nâng cấp cluster giữa major versions.
- [Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html) — các phương pháp upgrade.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — logical dump.
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — restore archive và parallel jobs.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher/subscriber và giới hạn.
- [Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html) — DDL, sequences và các giới hạn.
- [ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html) — extension update.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html) — collation behavior/versioning.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backup, PITR và recovery.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — replication và database health.

Luôn mở tài liệu đúng source/target major versions thay vì chỉ đọc current. Extension vendors và managed service providers có thể có compatibility/upgrade procedures riêng.

## 49. Tổng kết: chọn phương pháp theo compatibility và recovery

```text
Identify current version and target
             |
             v
       Same major line?
         /       \
       Yes        No
        |          |
        v          v
   Minor update  Major upgrade
        |          |
        v          v
  Backup +       Choose method
  release notes     |
  package/restart   +-- pg_upgrade
  verify            +-- dump/restore
                    +-- logical replication
                    +-- managed workflow
                         |
                         v
                Preflight + rehearsal
                         |
                         v
                 Cutover + validation
                         |
                         v
             Backup/HA/CDC + rollback window
                         |
                         v
                  Close change safely
```

Những nguyên tắc cần nhớ:

1. **Minor update giữ cùng major data format.** Thông thường thay binaries/packages và restart, không cần pg_upgrade.
2. **Major upgrade là chuyển đổi cluster.** Không mở old data directory bằng major binary mới trực tiếp.
3. **Đọc release notes và kiểm tra đường nâng cấp.** Không giả định có thể nhảy trực tiếp từ mọi source major.
4. **Chọn pg_upgrade, dump/restore hoặc logical migration theo downtime và compatibility.**
5. **pg_upgrade --check phải chạy trước maintenance window.** Rehearse trên bản sao production-sized.
6. **Copy, link và clone có trade-offs khác nhau.** Link mode không giữ old cluster an toàn sau khi new cluster ghi.
7. **Extension binaries và SQL versions phải tương thích.** Cài package và chạy extension update theo hướng dẫn.
8. **Collation, sequences, DDL và global objects cần validation riêng.** Đặc biệt với logical migration.
9. **Physical standbys cần được rebuild/rejoin theo major mới.** Không giả định old-major standby tiếp tục streaming.
10. **Backup/restore test là nền tảng rollback.** Giữ old cluster không giải quyết writes phát sinh sau cutover.
11. **ANALYZE và performance tests sau upgrade rất quan trọng.** Query plans có thể thay đổi.
12. **Chỉ đóng change khi HA, CDC, backup, application và business flows đều được xác minh.**

**Một câu để nhớ:** *Minor update thay bản sửa lỗi trong cùng major line; major upgrade chuyển cả cluster sang major line mới, nên phải chọn migration method, chuẩn bị extensions/replication, kiểm thử ứng dụng và xác định rollback trước cutover.*

