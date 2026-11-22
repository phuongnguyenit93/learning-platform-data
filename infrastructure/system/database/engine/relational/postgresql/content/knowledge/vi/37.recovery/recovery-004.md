# Khôi phục vật lý và yêu cầu tương thích trong PostgreSQL

**Khôi phục vật lý (physical recovery)** là quá trình đưa một PostgreSQL cluster trở lại trạng thái có thể hoạt động bằng cách sử dụng bản sao ở mức file/page cùng với WAL (Write-Ahead Log). Phương pháp này thường dùng để phục hồi sau sự cố máy chủ, mất storage, dựng standby, chuyển đổi data center hoặc khôi phục tới một thời điểm trong quá khứ (PITR).

Physical recovery phụ thuộc chặt vào **tính tương thích của data directory, binary PostgreSQL, hệ điều hành/kiến trúc, block size, WAL format, tablespaces, extension libraries và chuỗi WAL**. Một bản backup có đủ file nhưng được khởi động bằng binary không tương thích vẫn có thể không chạy hoặc gây lỗi nghiêm trọng.

Điểm quan trọng cần nhớ:

- Physical backup là bản sao của **toàn bộ cluster**, không phải công cụ chọn một table/database như `pg_dump`.
- Base backup cần WAL phù hợp để trở thành một bản sao nhất quán có thể khởi động.
- Physical restore thông thường yêu cầu cùng major version PostgreSQL và các tham số định dạng tương thích.
- WAL archive phải liên tục từ base backup tới điểm recovery mục tiêu.
- Tablespaces, config ngoài PGDATA, extension binaries, chứng thư và secrets có thể nằm ngoài backup.
- Một lần restore thành công cần được xác minh bằng recovery state, logs, query checks và ứng dụng thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt physical backup, logical backup, base backup, WAL archive và snapshot.
2. Giải thích vì sao physical backup cần WAL để đạt trạng thái nhất quán.
3. Tạo base backup bằng `pg_basebackup` và hiểu các tùy chọn WAL/standby.
4. Mô tả quy trình filesystem-level backup đúng cách.
5. Khôi phục một cluster từ physical backup và replay WAL.
6. Thiết lập PITR bằng `restore_command`, `recovery.signal` và recovery targets.
7. Dựng standby từ base backup và theo dõi WAL receiver/replay.
8. Phân biệt crash recovery, archive recovery, standby recovery và promotion.
9. Xác định yêu cầu tương thích major/minor version, OS, CPU architecture và PostgreSQL build.
10. Kiểm tra block size, WAL block size, WAL segment size, checksum version và system identifier.
11. Xử lý tablespaces, external configuration, extension libraries, collation và file permissions.
12. Hiểu timeline, timeline history và rủi ro phân nhánh sau promotion.
13. Dùng `pg_verifybackup`, `pg_controldata`, `pg_checksums` và các system views phù hợp.
14. Xây dựng runbook restore, validation, rollback và disaster recovery.

## 2. Physical recovery là gì?

### 2.1. Physical backup sao chép cấu trúc lưu trữ

Một PostgreSQL cluster gồm nhiều database, shared catalogs, WAL, control files, tablespaces và các relation files. Physical backup sao chép dữ liệu ở mức storage layout, giữ lại page formats, relation files và metadata cần thiết.

Ví dụ một data directory có thể chứa:

~~~text
PGDATA/
  base/                 # database relation files
  global/               # shared cluster catalogs
  pg_wal/               # WAL segments
  pg_xact/              # transaction status
  pg_multixact/
  pg_tblspc/            # links to tablespaces
  pg_twophase/
  pg_control            # cluster control information
  PG_VERSION
  postgresql.conf       # nếu đặt trong PGDATA
  pg_hba.conf           # nếu đặt trong PGDATA
  pg_ident.conf         # nếu đặt trong PGDATA
~~~

Đây là sơ đồ khái niệm; nội dung/thư mục cụ thể có thể khác theo major version, build, cấu hình và platform.

### 2.2. Physical restore phục hồi cả cluster

Khi restore physical backup, PostgreSQL phục hồi toàn bộ cluster như thời điểm base backup, sau đó có thể replay WAL để tiến tới trạng thái nhất quán hoặc một recovery target.

Không thể lấy một physical base backup thông thường rồi chỉ yêu cầu server mở riêng database `sales` trong khi bỏ qua phần còn lại của cluster. Muốn backup/restore chọn lọc database hoặc table, dùng logical dump/restore hoặc thiết kế export/import riêng.

### 2.3. Physical recovery dùng cho trường hợp nào?

- Phục hồi toàn cluster sau khi mất volume/máy chủ;
- Dựng standby vật lý để high availability;
- Clone cluster cho môi trường staging/test;
- Chuyển cluster sang storage mới;
- Khôi phục PITR sau thao tác xóa/sửa nhầm;
- Tái dựng node sau failover;
- Dùng snapshot nhất quán để tạo bản sao nhanh.

### 2.4. Physical recovery không tự sửa lỗi nghiệp vụ

Nếu một transaction hợp lệ đã xóa nhầm dữ liệu và WAL đã ghi nhận commit, crash recovery sẽ replay transaction đó. Muốn quay về trước thời điểm xóa, phải dùng PITR tới thời điểm trước transaction hoặc restore logical data từ nguồn khác.

### 2.5. Khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Base backup | Bản sao vật lý nền của cluster tại một khoảng thời gian backup |
| WAL archive | Chuỗi WAL segments được lưu ngoài `pg_wal` để phục hồi |
| Crash recovery | Replay WAL nội bộ sau khi server crash |
| Archive recovery | Replay WAL từ archive sau base backup |
| PITR | Dừng recovery tại một thời điểm/LSN/transaction target |
| Physical standby | Node phục hồi và tiếp tục nhận/replay WAL từ primary |
| Promotion | Chuyển standby thành primary có quyền nhận writes |
| Timeline | Nhánh lịch sử WAL sau khi cluster khởi tạo hoặc được promote |

## 3. Physical backup cần WAL vì sao?

### 3.1. Data files không được copy cùng một thời điểm tuyệt đối

Trong lúc backup, ứng dụng vẫn có thể ghi dữ liệu. Nếu copy file A lúc 10:00:00, file B lúc 10:00:10 và file C lúc 10:00:30, các files có thể phản ánh những trạng thái transaction khác nhau.

PostgreSQL dùng WAL để làm cho bản copy có thể được recovery tới trạng thái nhất quán.

### 3.2. Base backup là một khoảng thời gian

Base backup có thời điểm bắt đầu và kết thúc. Trong khoảng này, data pages có thể thay đổi. WAL records phát sinh trong và liên quan tới quá trình backup cho phép PostgreSQL redo các thay đổi cần thiết.

### 3.3. Consistent backup

Một base backup vật lý chỉ được xem là consistent khi có đủ WAL cần thiết để recovery theo cơ chế backup đã sử dụng. Không thể chỉ copy `base/` rồi mặc định cluster có thể start.

### 3.4. WAL phải được bảo vệ cùng backup

Nếu base backup còn nguyên nhưng WAL cần thiết bị thiếu/hỏng, PostgreSQL có thể không hoàn tất recovery. Vì vậy backup policy phải bao gồm:

- Base backup;
- WAL archive liên tục;
- Timeline history files;
- Manifest/checksums nếu công cụ tạo;
- Metadata về PostgreSQL version và cấu hình;
- Hướng dẫn restore đã kiểm thử.

### 3.5. Backup consistency và transaction commit

Transaction đang chạy lúc backup có thể được commit hoặc abort sau đó. WAL recovery và transaction status cho phép PostgreSQL quyết định trạng thái đúng theo quy tắc MVCC/commit, thay vì tin rằng mọi bytes được copy cùng thời điểm.

## 4. Physical backup và logical backup

| Tiêu chí | Physical backup | Logical backup |
| --- | --- | --- |
| Mức sao chép | Pages/files của cluster | SQL objects và rows |
| Phạm vi phổ biến | Toàn cluster | Có thể chọn database/schema/table |
| Phụ thuộc major version | Cao; physical format/WAL cần tương thích | Có thể dump ở version cũ và restore sang version mới theo hỗ trợ |
| Restore speed | Thường nhanh cho cluster lớn khi storage phù hợp | Có thể chậm hơn do parse/execute SQL và rebuild indexes |
| PITR | Kết hợp base backup + WAL archive | Không thay thế PITR physical; có thể replay business-level exports riêng |
| Cross-platform migration | Hạn chế bởi binary/storage format | Linh hoạt hơn |
| Dữ liệu hệ thống/cluster roles | Physical backup giữ cluster metadata | `pg_dump` database không tự chứa toàn bộ cluster-wide roles/tablespaces |
| Chọn một table | Không phải mục tiêu thông thường | Có thể |

### 4.1. Công cụ logical phổ biến

- `pg_dump`: dump một database;
- `pg_dumpall`: dump toàn cluster dưới dạng SQL, gồm globals theo khả năng;
- `pg_restore`: restore custom/directory/tar archive từ `pg_dump`;
- `psql`: thực thi plain SQL dump.

### 4.2. Không thay thế lẫn nhau

Physical backup phù hợp disaster recovery và standby. Logical backup phù hợp migration có chuyển đổi version/schema, selective restore và export/import. Hệ thống production thường cần cả hai theo mục tiêu RPO/RTO.

### 4.3. Dùng physical backup cho major upgrade?

Không dùng cách copy PGDATA của major version cũ rồi start bằng binary major version mới để nâng cấp. Dùng quy trình hỗ trợ như `pg_upgrade`, logical dump/restore hoặc logical replication migration. Physical backup vẫn cần để rollback/DR theo quy trình riêng.

## 5. Công cụ pg_basebackup

### 5.1. pg_basebackup làm gì?

`pg_basebackup` kết nối tới một PostgreSQL server có quyền replication và tạo base backup vật lý. Nó dùng replication protocol để copy data files/tablespaces và thu thập WAL theo phương thức được chọn.

Ưu điểm:

- Có cơ chế backup nhất quán được PostgreSQL hỗ trợ;
- Hỗ trợ backup từ primary và trong các điều kiện nhất định từ standby;
- Có thể stream WAL trong lúc copy;
- Có thể tạo cấu hình standby với `-R`;
- Có progress reporting và backup manifest ở các phiên bản hỗ trợ.

### 5.2. Quyền replication

Role chạy backup cần quyền `REPLICATION` hoặc superuser theo cấu hình server, và `pg_hba.conf` phải cho phép replication connection từ máy backup.

~~~sql
CREATE ROLE backup_user WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
~~~

Ví dụ chỉ minh họa quyền. Không hard-code mật khẩu production trong shell history, script, source control hoặc command line có thể bị process listing ghi nhận. Dùng `.pgpass`, service file, secret manager hoặc cơ chế xác thực được tổ chức phê duyệt.

### 5.3. pg_hba.conf cho replication

Ví dụ một rule giới hạn client backup:

~~~conf
host  replication  backup_user  10.20.30.40/32  scram-sha-256
~~~

Thay địa chỉ bằng IP/CIDR thực tế và dùng TLS/Network policy phù hợp. Không mở replication access cho toàn Internet.

### 5.4. Base backup từ primary

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backups/pg/base-2026-11-14 \
  -Fp \
  -X stream \
  -P \
  --manifest-checksums=SHA256
~~~

Giải thích:

- `-h`, `-p`, `-U`: server, port và role kết nối;
- `-D`: đích backup; thường cần không tồn tại hoặc rỗng theo yêu cầu của format;
- `-Fp`: plain format, tạo cấu trúc file trực tiếp;
- `-X stream`: stream WAL trong khi backup;
- `-P`: hiển thị progress;
- `--manifest-checksums`: chọn checksum algorithm cho backup manifest nếu version hỗ trợ.

Kiểm tra `pg_basebackup --help` của đúng major version trước khi dùng option. Tên và default của một số flags thay đổi theo version.

### 5.5. WAL methods

`pg_basebackup` có các cách xử lý WAL (tùy version):

- `-X stream`: mở replication connection thứ hai để stream WAL trong lúc backup;
- `-X fetch`: lấy WAL cần thiết ở cuối backup từ server;
- `-X none`: không đưa WAL vào backup; chỉ dùng khi đã có quy trình WAL/archive bảo đảm consistency.

`stream` thường phù hợp khi muốn backup tự mang theo WAL cần thiết và có đủ connection slots. `fetch` có thể yêu cầu server giữ đủ WAL tới cuối backup; nếu WAL bị recycle trước khi fetch, backup có thể thất bại.

### 5.6. Number of WAL sender connections

Khi dùng `-X stream`, backup cần một replication connection cho base backup và thêm một connection stream WAL. Cần tính `max_wal_senders`, connection capacity và `max_replication_slots` nếu dùng slot. Nhiều backup đồng thời có thể tiêu thụ tài nguyên đáng kể.

### 5.7. Tạo backup cho standby

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /var/lib/postgresql/standby \
  -Fp \
  -X stream \
  -P \
  -R
~~~

`-R` (write recovery configuration) tạo `standby.signal` và ghi các connection settings phù hợp vào `postgresql.auto.conf` theo options đã truyền. Với source standby, kiểm tra các hạn chế WAL method/slot theo phiên bản; không giả định mọi lựa chọn hoạt động giống backup từ primary.

Khi source là standby, `pg_basebackup` có các hạn chế riêng: WAL streaming mode `-X stream` không được hỗ trợ trong nhiều phiên bản vì nó cần một replication connection khác. Dùng WAL method được tài liệu version hỗ trợ, thường là `-X fetch` hoặc archive/streaming được quản lý riêng; xác nhận standby còn giữ đủ WAL tới khi backup kết thúc.

### 5.8. Không dùng -R khi mục tiêu là standalone PITR restore

Nếu muốn khôi phục thành một server độc lập tới thời điểm mục tiêu, cấu hình archive recovery phù hợp và không để cluster vô tình khởi động ở standby mode. `-R` là lựa chọn cho standby; `standby.signal` làm thay đổi mode khởi động.

### 5.9. Tạo replication slot

Có thể dùng slot để giữ WAL cho standby/backup consumer:

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /var/lib/postgresql/standby \
  -Fp \
  -X stream \
  -C \
  -S standby_slot_01 \
  -R \
  -P
~~~

`-C` tạo slot trước khi sử dụng; `-S` chỉ định tên slot. Xác nhận phiên bản hỗ trợ và slot chưa tồn tại. Replication slot có thể giữ WAL không giới hạn khi consumer ngừng hoạt động; theo dõi disk và `max_slot_wal_keep_size` theo version.

### 5.10. Compression của backup

Backup có thể được tạo ở các formats/compression methods được phiên bản hỗ trợ. Plain format thường dễ đọc/kiểm tra file nhưng không phải container nén. Tar/custom options và compression algorithms có khác biệt theo version; dùng `pg_basebackup --help`.

### 5.11. Tablespace mapping

Nếu tablespaces nằm ở path khác trên máy restore, `pg_basebackup` có tùy chọn mapping:

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /restore/pgdata \
  -Fp \
  -X stream \
  -T /old/fastspace=/new/fastspace \
  -P
~~~

Mapping cần khớp đúng đường dẫn tablespace nguồn và đích. Với nhiều tablespaces, khai báo mapping cho từng path. Không để link trong `pg_tblspc` trỏ tới thư mục không tồn tại hoặc một volume chưa mount.

### 5.12. Check backup exit status

Chỉ coi backup thành công khi:

- `pg_basebackup` exit code bằng 0;
- Progress kết thúc và backup directory được tạo đầy đủ;
- Có manifest nếu phiên bản/format tạo manifest;
- WAL method hoàn tất;
- Log không có lỗi cuối quá trình;
- `pg_verifybackup` thành công khi áp dụng.

Một directory có vẻ đủ file nhưng command thất bại vẫn là backup chưa được xác nhận.

## 6. Filesystem-level backup và storage snapshot

### 6.1. Copy PGDATA khi server đang chạy là nguy hiểm

Không thực hiện lệnh copy thư mục PGDATA tùy tiện khi PostgreSQL đang chạy:

~~~bash
cp -a /var/lib/postgresql/data /backups/pgdata
~~~

Các files có thể được copy ở những thời điểm khác nhau, dirty pages chưa được ghi, WAL/data file không đồng bộ, tablespace link bị bỏ sót hoặc WAL segment bị recycle trong lúc copy. Kết quả có thể không consistent và không thể start.

### 6.2. Ba cách tạo filesystem backup có thể hợp lệ

1. Dừng PostgreSQL sạch rồi copy toàn bộ cluster files và tablespaces;
2. Dùng backup API của PostgreSQL (`pg_backup_start`/`pg_backup_stop`) và bảo đảm copy đủ files/WAL;
3. Dùng storage snapshot nhất quán theo hướng dẫn của storage provider, kết hợp backup mode và WAL archive nếu cần.

`pg_basebackup` thường là cách dễ quản lý hơn cho base backup online.

### 6.3. Cold backup

Cold backup cần shutdown sạch:

~~~bash
pg_ctl -D /var/lib/postgresql/data stop -m fast
~~~

Sau khi xác nhận server đã dừng hoàn toàn, copy:

- Toàn bộ PGDATA;
- Tất cả tablespaces bên ngoài;
- WAL directory nếu đặt ngoài PGDATA;
- Các config/cert/key ở ngoài data directory;
- Metadata version/build/paths.

Cold copy giữ trạng thái nhất quán vì không có backend đang thay đổi files. Cần bảo đảm không có PostgreSQL process khác dùng cùng data directory.

### 6.4. Backup API hiện đại

Các PostgreSQL versions hiện hành cung cấp SQL functions:

- `pg_backup_start(label, fast)` bắt đầu backup mode;
- `pg_backup_stop(wait_for_archive)` kết thúc backup mode và trả về metadata backup.

Ví dụ về trình tự ở mức khái niệm:

~~~sql
SELECT pg_backup_start('nightly-base-2026-11-14', true);
-- công cụ snapshot/copy toàn bộ PGDATA và tablespaces
SELECT * FROM pg_backup_stop(wait_for_archive => true);
~~~

Không chạy hai lệnh trên rồi bỏ qua việc copy files. Backup API chỉ đánh dấu/điều phối trạng thái backup; công cụ vẫn phải copy đúng toàn bộ files và lưu metadata do hàm trả về (như backup label/tablespace map theo định dạng). Phải bảo đảm WAL cần thiết được archive hoặc lưu cùng backup.

### 6.5. Legacy backup functions

Các phiên bản PostgreSQL cũ dùng `pg_start_backup` và `pg_stop_backup`. Tên, semantics và quyền đã thay đổi theo version. Khi viết automation, dùng functions được tài liệu của major version hiện tại khuyến nghị; không sao chép script cũ mà chưa kiểm tra.

### 6.6. Backup mode và fast checkpoint

Tham số `fast` có thể yêu cầu checkpoint nhanh khi bắt đầu backup, giảm thời gian chờ nhưng gây I/O burst. Chọn theo workload/storage và theo dõi latency. Không mặc định fast luôn tốt.

### 6.7. Snapshot consistency

Một storage snapshot chỉ hữu ích khi các volume có quan hệ với nhau được snapshot tại một thời điểm nhất quán. Nếu PGDATA, WAL và tablespaces ở nhiều volumes, snapshot từng volume lệch thời điểm có thể tạo backup không consistent.

Dùng cơ chế group snapshot/consistency group của storage provider hoặc backup API cùng WAL để bảo đảm consistency.

### 6.8. Snapshot không tự tạo WAL archive

Snapshot của data volumes không tự bảo đảm WAL segments cần thiết đã được lưu bền vững bên ngoài. Thiết kế retention và archive cho WAL, kiểm tra segment continuity và giữ timeline history files.

### 6.9. File-level backup cần giữ metadata

Khi copy/restore, bảo toàn:

- File ownership của OS user PostgreSQL;
- Permissions/modes;
- Symlinks của tablespaces và WAL;
- File timestamps khi công cụ cần;
- Sparse files/hard links nếu backup format dựa vào chúng;
- Extended attributes/ACL nếu nền tảng yêu cầu.

Không giải nén backup bằng tài khoản hoặc công cụ làm thay đổi ownership/permissions mà không kiểm tra.

## 7. Kiểm tra backup với pg_verifybackup

### 7.1. Backup manifest

`pg_basebackup` ở các phiên bản hỗ trợ tạo `backup_manifest` chứa danh sách files, kích thước và checksum metadata. Manifest giúp xác minh backup files không bị thiếu hoặc thay đổi ngoài dự kiến.

### 7.2. Chạy pg_verifybackup

~~~bash
pg_verifybackup /backups/pg/base-2026-11-14
~~~

Công cụ đọc manifest, kiểm tra các files được liệt kê và xác minh WAL liên quan theo khả năng/version/options. Sử dụng binary đúng major version và đọc exit status.

### 7.3. Chọn checksum algorithm

Manifest có thể dùng checksum algorithms khác nhau tùy version, ví dụ CRC32C hoặc SHA-256. SHA-256 có đặc tính chống collision mạnh hơn CRC cho mục tiêu kiểm tra file, nhưng không biến backup thành bản mã hóa hay xác thực chống attacker nếu manifest cũng bị thay đổi.

### 7.4. pg_verifybackup không phải restore test

Một backup có thể pass manifest verification nhưng vẫn không đáp ứng RTO, thiếu config ngoài PGDATA, thiếu extension binaries, sai permissions hoặc gặp lỗi khi start/replay. Chỉ restore test mới chứng minh được toàn bộ quy trình phục hồi thực tế.

### 7.5. WAL parsing

`pg_verifybackup` có thể kiểm tra WAL trong backup theo khả năng của version. Các options như bỏ qua WAL parsing hoặc chỉ định WAL directory thay đổi phạm vi xác minh. Không bật tùy chọn skip mà không hiểu mục tiêu của lần kiểm tra.

### 7.6. Kết quả verification

Ghi nhận:

- Backup path và timestamp;
- PostgreSQL major/minor version;
- Manifest checksum algorithm;
- Files missing/extra/modified;
- WAL verification results;
- Exit code;
- Tool version và command options.

### 7.7. Backup checksum khác data page checksum

Backup manifest checksum xác minh file backup so với manifest. Data page checksum là metadata bên trong page của cluster. Một backup có manifest checksum đúng không có nghĩa mọi page bên trong đều từng được xác minh checksum khi server tạo backup.

## 8. Incremental physical backups

### 8.1. Incremental backup là gì?

Incremental backup chỉ lưu các blocks thay đổi kể từ một backup trước đó theo cơ chế được PostgreSQL hỗ trợ. Nó có thể giảm dữ liệu phải truyền/lưu, nhưng restore phải kết hợp đúng chuỗi backup.

### 8.2. PostgreSQL 17+

PostgreSQL 17 giới thiệu incremental backup support trong `pg_basebackup` và công cụ `pg_combinebackup`. Tính năng và options phụ thuộc major version; đọc đúng tài liệu cài đặt.

Ví dụ tạo incremental backup dựa trên manifest của backup trước:

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /backups/incremental-2026-11-15 \
  --incremental=/backups/base/backup_manifest \
  -Fp \
  -X stream \
  -P
~~~

Đường dẫn manifest và cách chỉ định incremental chain phụ thuộc version/tool. Giữ nguyên manifest của base backup và từng incremental; không di chuyển/đổi tên theo cách làm mất metadata references.

### 8.3. pg_combinebackup

Một quy trình incremental cần kết hợp các incremental backups theo đúng base backup và manifest chain:

~~~bash
pg_combinebackup \
  /backups/base \
  /backups/incremental-01 \
  /backups/incremental-02 \
  -o /restore/combined
~~~

Đây là ví dụ minh họa dạng lệnh; options/ordering và yêu cầu metadata phải được xác nhận bằng `pg_combinebackup --help` của version. Output combined backup mới là input cho quy trình restore.

### 8.4. Không thể bỏ một incremental ở giữa tùy tiện

Incremental chain phụ thuộc backup trước đó và block references/manifests. Nếu thiếu một backup cần thiết, không thể giả định lấy incremental mới nhất là đủ. Quản lý catalog/manifest và retention toàn bộ chain.

### 8.5. Full backup vẫn cần thiết

Incremental backup không loại bỏ nhu cầu full/base backup và WAL archive. Cần tính tổng chi phí restore, thời gian combine, số incremental trong chain và rủi ro một artifact bị hỏng.

### 8.6. Restore test cho incremental chain

Kiểm thử cả:

- Tạo base + nhiều incrementals;
- Verify từng backup;
- Combine đúng chain;
- Restore combined backup;
- Replay WAL;
- Kiểm tra database và query.

Không chỉ kiểm tra từng incremental file độc lập.

## 9. WAL archive và điều kiện phục hồi

### 9.1. archive_mode

~~~sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
~~~

`archive_mode` bật WAL archiving. `archive_command` gọi lệnh để copy WAL segment đã hoàn tất tới archive storage. `archive_timeout` có thể buộc segment switch sau một khoảng thời gian để giảm độ trễ archive trong workload ít WAL.

### 9.2. archive_command

Ví dụ trên Unix:

~~~conf
archive_mode = on
archive_command = 'test ! -f /wal-archive/%f && cp %p /wal-archive/%f'
~~~

Đây là ví dụ lab đơn giản. Production cần cơ chế atomic publish, retry, kiểm tra exit code, quyền ghi, network failures, retention, encryption và monitoring. Lệnh phải trả exit code 0 chỉ khi archive thành công; nếu fail, PostgreSQL sẽ retry.

### 9.3. Không ghi đè WAL archive cũ

WAL segment name gắn với timeline/log sequence. Không dùng command ghi đè mù vào file archive đã tồn tại. Nếu file đã có, cần xác minh nội dung/identity; không coi mọi file cùng tên là giống nhau trong mọi timeline/recovery scenario.

### 9.4. Archive timeout và RPO

`archive_timeout` có thể giới hạn thời gian chờ segment switch trong workload thấp, nhưng không phải đảm bảo archive thành công. RPO phụ thuộc WAL được ghi bền vững, archive pipeline, network/storage và cách monitor failures.

### 9.5. Kiểm tra archive failures

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

Nếu `failed_count` tăng hoặc `last_archived_time` quá cũ so với workload, kiểm tra log archive command, filesystem capacity, credentials, network và destination.

### 9.6. WAL archive phải liên tục

PITR cần WAL segments liên tục từ điểm cần recovery. Một segment thiếu ở giữa có thể làm recovery dừng trước target, dù các segment sau vẫn tồn tại.

### 9.7. Timeline history

Khi standby được promote, PostgreSQL tạo timeline mới và một `.history` file mô tả nhánh lịch sử. WAL archive cần giữ các history files cùng WAL segments. Nếu thiếu timeline history, recovery có thể không biết phải theo nhánh nào.

### 9.8. WAL archive và replication slot khác nhau

Replication slot giữ WAL trên primary để một consumer còn có thể đọc. Archive command sao chép WAL segments ra kho lưu trữ. Slot không thay thế archive backup; archive cũng không tự giữ WAL trong `pg_wal` cho streaming standby.

## 10. Khôi phục vật lý từ base backup

### 10.1. Chuẩn bị trước khi restore

Trước khi chạm vào data directory:

1. Xác nhận backup artifact và timestamp cần khôi phục;
2. Xác định major/minor version, build và platform nguồn;
3. Xác minh base backup bằng manifest/tool phù hợp;
4. Xác nhận WAL cần thiết đã có và không thiếu segment;
5. Xác định tablespaces, WAL path, config và external dependencies;
6. Đảm bảo target storage đủ dung lượng và ownership;
7. Cô lập instance cũ để tránh hai primary cùng nhận writes;
8. Lập kế hoạch giữ lại data directory cũ để rollback/forensics.

### 10.2. Không ghi đè data directory đang hoạt động

Không giải nén backup lên PGDATA của server đang chạy. Không xóa thư mục cũ trước khi xác minh backup và quyết định restore. Nếu cần thay thế instance, dừng service sạch, kiểm tra process, giữ bản cũ ở path an toàn và tạo data directory mới.

### 10.3. Restore plain-format base backup

Nếu backup plain format đã được tạo ở `/srv/pgbackup/base`, quy trình khái niệm:

~~~bash
pg_ctl -D /var/lib/postgresql/data stop -m fast
mv /var/lib/postgresql/data /var/lib/postgresql/data.pre-restore
mkdir -p /var/lib/postgresql/data
rsync -a /srv/pgbackup/base/ /var/lib/postgresql/data/
chown -R postgres:postgres /var/lib/postgresql/data
chmod 700 /var/lib/postgresql/data
~~~

Đây là ví dụ Unix minh họa, không phải script dùng nguyên xi. Xác minh paths, owner/group và tablespaces trước. Nếu backup có symlink tới tablespaces ngoài PGDATA, phải khôi phục các target paths trước khi start.

### 10.4. Restore tar format

Với tar format, giải nén các archive theo layout/metadata do `pg_basebackup` tạo và xử lý tablespaces theo đúng mapping. Không giải nén mọi tar file vào một thư mục tùy tiện; tablespace archives phải đến đúng đích.

### 10.5. Kiểm tra PG_VERSION

File `PG_VERSION` ghi major version của data directory. Đọc file và so với `postgres --version`. Nếu major version không khớp, dừng lại và dùng đúng binary; không thử start nhiều binary để xem cái nào chạy.

### 10.6. Kiểm tra tablespaces

Thư mục `pg_tblspc` chứa symbolic links tới tablespaces. Kiểm tra:

~~~bash
ls -la /var/lib/postgresql/data/pg_tblspc
~~~

Mỗi link phải trỏ tới path tồn tại, đúng volume và có permissions phù hợp. Nếu restore sang path mới, dùng `-T` lúc tạo backup hoặc mapping/copy có kiểm soát.

### 10.7. Khôi phục config

Xác định vị trí thực tế của:

- `postgresql.conf`;
- `postgresql.auto.conf`;
- `pg_hba.conf`;
- `pg_ident.conf`;
- SSL certificate/private key;
- `archive_command` và `restore_command`;
- Service manager/unit, environment và secrets.

Một số config được đặt ngoài PGDATA bằng command-line options hoặc `config_file`/`hba_file`. Physical backup không tự mang theo mọi config ngoài data directory.

### 10.8. Kiểm tra quyền file

PostgreSQL yêu cầu data directory và private key có permissions an toàn. Nếu owner/mode sai, server có thể từ chối start hoặc tạo nguy cơ bảo mật. Dùng tài khoản service phù hợp và giữ permissions theo tài liệu platform.

### 10.9. Khởi động lần đầu

~~~bash
pg_ctl -D /var/lib/postgresql/data start -l /var/log/postgresql/restore.log
~~~

Theo dõi log từ đầu tới khi server báo sẵn sàng. Nếu backup cần crash recovery, PostgreSQL sẽ tự replay WAL có trong data directory. Nếu cần archive recovery, phải chuẩn bị recovery configuration trước khi start.

### 10.10. Kiểm tra server đã recovery

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction;
~~~

`pg_is_in_recovery()` cho biết server còn đang recovery/standby. Trên standalone server sau khi hoàn tất crash recovery, giá trị thường là false; trên standby đang replay WAL, giá trị là true.

### 10.11. Không promote khi chưa hiểu timeline

Nếu mục tiêu là dựng standby, giữ standby mode và tiếp tục nhận WAL. Nếu mục tiêu là PITR standalone, chọn target và recovery action có chủ đích. Promote sẽ tạo timeline mới và khiến node bắt đầu nhận writes; phải fencing primary cũ trước.

## 11. Archive recovery và PITR

### 11.1. Recovery signal files

Trong PostgreSQL 12 trở lên, recovery mode được điều khiển bằng signal files:

- `recovery.signal`: yêu cầu archive recovery/PITR;
- `standby.signal`: khởi động ở standby mode.

Các phiên bản trước PostgreSQL 12 dùng `recovery.conf`. File này đã bị loại bỏ trong các phiên bản mới; không dùng hướng dẫn recovery.conf cũ cho PostgreSQL 12+.

### 11.2. restore_command

`restore_command` gọi lệnh lấy một WAL segment từ archive:

~~~conf
restore_command = 'cp /wal-archive/%f %p'
~~~

- `%f`: tên file cần lấy;
- `%p`: đường dẫn đích nơi PostgreSQL muốn đặt file.

Command phải trả exit code 0 khi tìm và restore file thành công; trả non-zero khi file không có/không thể lấy. Production thường dùng công cụ archive/restore riêng, có retry, checksum, credentials và logging.

### 11.3. Cấu hình PITR cơ bản

Trong PostgreSQL 12+ có thể đặt trong `postgresql.conf` hoặc `postgresql.auto.conf`:

~~~conf
restore_command = 'cp /wal-archive/%f %p'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
~~~

Tạo signal file:

~~~bash
touch /var/lib/postgresql/data/recovery.signal
~~~

Khởi động server với đúng binary. Ví dụ thời gian chỉ minh họa; phải dùng timezone và target thực tế. Không để `standby.signal` nếu mục tiêu là standalone PITR.

### 11.4. Recovery target types

PostgreSQL hỗ trợ nhiều loại target theo version:

- `recovery_target_time`: thời điểm timestamp;
- `recovery_target_xid`: transaction ID;
- `recovery_target_name`: restore point name;
- `recovery_target_lsn`: WAL LSN.

Chọn target dựa trên dữ liệu và log. Target time không nhất thiết là thời điểm wall-clock mà người dùng bấm nút; đồng hồ server, timezone và transaction commit time cần được hiểu rõ.

### 11.5. Restore point

Trước một thay đổi rủi ro, có thể tạo named restore point:

~~~sql
SELECT pg_create_restore_point('before_schema_change');
~~~

Tên restore point được ghi trong WAL. PITR có thể chọn `recovery_target_name` tương ứng nếu WAL từ base backup tới điểm đó còn đầy đủ.

### 11.6. recovery_target_inclusive

`recovery_target_inclusive` điều khiển có áp dụng transaction/target event tại điểm recovery hay dừng ngay trước target theo semantics của target type. Với time target, hiểu transaction timestamp và commit ordering trước khi chọn.

### 11.7. recovery_target_action

Các hành động thường gặp:

- `pause`: dừng replay tại target để DBA kiểm tra;
- `promote`: promote sau khi đạt target;
- `shutdown`: dừng server sau khi đạt target.

`pause` hữu ích khi muốn kiểm tra dữ liệu trước khi cho phép writes. Đừng promote sớm khi chưa xác nhận đúng target.

### 11.8. recovery_target_timeline

`latest` yêu cầu recovery theo timeline mới nhất có thể tìm thấy trong archive, dựa trên timeline history. Khi cần khôi phục vào một nhánh lịch sử cụ thể, có thể chọn timeline ID hoặc cấu hình phù hợp theo version.

### 11.9. Kiểm tra sau khi pause

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
~~~

Kiểm tra business data, row counts, timestamps, constraints và query quan trọng. Khi đã xác nhận:

~~~sql
SELECT pg_promote(wait => true);
~~~

Promote kết thúc recovery và tạo timeline mới. Lệnh promotion phải được thực hiện đúng node sau khi primary cũ đã được fencing.

### 11.10. Thiếu WAL giữa chừng

Nếu `restore_command` không lấy được WAL segment cần thiết, recovery không thể tiến qua khoảng thiếu đó. PostgreSQL có thể dừng ở WAL cuối cùng hợp lệ hoặc báo lỗi tùy bối cảnh. Không copy một segment có tên gần giống để lấp khoảng trống.

### 11.11. Xác định điểm phục hồi

Dùng:

- Application audit logs;
- Transaction/event timestamps;
- WAL/restore point metadata;
- Monitoring/incident timestamps;
- Known-good query results;
- Timeline history.

Tạo một bản restore thử ở target gần nhất trước khi quyết định cutover production.

### 11.12. Recovery target và dữ liệu đã commit

PITR replay WAL theo thứ tự và target semantics. Một transaction lớn có thể commit trước/sau thời điểm mong muốn; không suy ra row state chỉ từ thời điểm statement bắt đầu. Kiểm tra transaction commit và business records sau recovery.

## 12. Dựng physical standby và failover

### 12.1. Standby là một bản physical copy đang theo primary

Physical standby bắt đầu từ base backup của primary (hoặc một nguồn phù hợp), sau đó nhận WAL qua streaming replication hoặc archive recovery và replay để cập nhật data pages.

### 12.2. standby.signal

PostgreSQL 12+ nhận biết standby mode khi có file `standby.signal` trong PGDATA. `pg_basebackup -R` tạo file này và ghi recovery connection settings vào `postgresql.auto.conf`.

### 12.3. primary_conninfo

Ví dụ:

~~~conf
primary_conninfo = 'host=db-primary.example.internal port=5432 user=replicator application_name=standby01 sslmode=verify-full'
~~~

Đặt thông tin kết nối phù hợp; bảo vệ password bằng passfile/secret management thay vì nhúng rõ trong file nếu policy không cho phép. TLS certificate/CA và DNS/network routes cũng phải được cài trên standby.

### 12.4. primary_slot_name

~~~conf
primary_slot_name = 'standby_slot_01'
~~~

Slot giúp primary giữ WAL cho standby đã đăng ký. Nếu standby dừng lâu, slot có thể làm `pg_wal` tăng nhanh. Theo dõi slot activity, retained WAL và `max_slot_wal_keep_size` theo version.

### 12.5. restore_command kết hợp streaming

Standby có thể dùng `restore_command` để lấy WAL từ archive trước, rồi tiếp tục streaming từ primary khi có kết nối. Điều này hữu ích khi standby bị gián đoạn network hoặc cần catch up từ archive.

### 12.6. Kiểm tra WAL receiver

Trên standby:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

View cho biết receiver state, sender host/port, slot, received LSN và trạng thái streaming. Các cột thay đổi theo version; xem tài liệu tương ứng.

### 12.7. Kiểm tra replication trên primary

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
FROM pg_stat_replication;
~~~

So sánh sent/write/flush/replay LSN để xác định standby đang chậm ở giai đoạn nào. Lag time có thể NULL khi không có transaction mới hoặc stats không thể tính trong khoảng quan sát; dùng cả LSN distance và monitoring.

### 12.8. Read-only trên standby

Standby đang recovery không nhận writes thông thường. Có thể cho phép read-only queries nếu `hot_standby` và các điều kiện version/config phù hợp. Một số queries có thể bị cancel do recovery conflicts.

### 12.9. Hot standby conflicts

Recovery cần replay WAL có thể xung đột với query đang đọc snapshot/locks trên standby. PostgreSQL có thể chờ hoặc cancel query theo settings như `max_standby_streaming_delay`, `max_standby_archive_delay` và feedback policy.

Tăng delay có thể giảm query cancellations nhưng làm replay lag tăng. `hot_standby_feedback` có thể giảm một số conflicts nhưng giữ xmin trên primary, ảnh hưởng vacuum. Tuning phải cân bằng reporting workload và primary bloat.

### 12.10. Promote standby

Khi primary mất và failover được quyết định:

~~~sql
SELECT pg_promote(wait => true);
~~~

Hoặc dùng công cụ quản trị phù hợp. Trước promotion, phải xác định node được chọn, mức WAL đã replay, dữ liệu có thể mất theo RPO và primary cũ đã được fencing.

### 12.11. Split brain

Nếu primary cũ vẫn nhận writes trong khi standby được promote, hai nodes có thể tạo hai lịch sử dữ liệu độc lập. Không có cách tự merge physical WAL branches một cách an toàn.

Dùng fencing: tắt/cô lập node cũ, thu hồi VIP/load balancer/write routing hoặc dùng cơ chế cluster manager để bảo đảm chỉ một primary hoạt động.

### 12.12. Rejoin node cũ

Sau failover, node cũ không tự trở thành standby hợp lệ chỉ bằng cách đổi hostname. Tùy độ phân kỳ và WAL availability, có thể dùng `pg_rewind` nếu đủ prerequisites; nếu không, tạo lại base backup từ primary mới.

### 12.13. Failback

Failback là quy trình có chủ đích: dựng lại standby, chờ catch up, xác minh health, lên lịch chuyển role và fence node hiện tại. Không đơn giản promote lại node cũ vì nó từng là primary.

## 13. Timeline và lịch sử WAL

### 13.1. Timeline là gì?

Timeline là nhánh lịch sử của WAL. Một cluster mới thường bắt đầu timeline 1. Khi standby được promote hoặc recovery được kết thúc bằng promotion, PostgreSQL tạo timeline ID mới và ghi timeline history.

### 13.2. Vì sao cần timeline?

Sau failover, node mới có thể tạo WAL ở cùng LSN range với lịch sử cũ nhưng nội dung khác. Timeline phân biệt các nhánh WAL để recovery không nhầm lẫn records từ hai histories.

### 13.3. Timeline history file

File dạng `00000002.history` mô tả timeline mới được tách từ timeline trước ở LSN nào và có thể chứa thông tin reason/comment. Archive phải lưu các `.history` files.

### 13.4. recovery_target_timeline

`recovery_target_timeline='latest'` yêu cầu recovery chọn timeline mới nhất có thể tìm thấy theo history. Khi cần khôi phục một nhánh cụ thể, đặt timeline ID theo tài liệu version và bảo đảm history/WAL của nhánh đó có đủ.

### 13.5. Không trộn WAL từ hai timeline

Không đổi tên WAL segment của timeline A thành tên timeline B hoặc copy file cùng tên từ archive khác mà không xác minh timeline. Một nhầm lẫn có thể khiến recovery thất bại hoặc đi sai lịch sử.

### 13.6. WAL archive phải hỗ trợ nhiều timeline

Archive storage nên giữ file theo tên đầy đủ và timeline history. Không xóa `.history` chỉ vì file nhỏ; đây là metadata cần để chọn nhánh recovery.

### 13.7. Xác định timeline hiện tại

Có thể xem control data:

~~~bash
pg_controldata -D /var/lib/postgresql/data
~~~

Output cung cấp checkpoint/timeline metadata theo version. Khi server đang chạy, dùng `pg_control_checkpoint()` nếu quyền/version cho phép hoặc các công cụ monitoring/replication phù hợp.

## 14. pg_rewind và tái đồng bộ node phân kỳ

### 14.1. Khi nào dùng pg_rewind?

Sau failover, primary cũ có thể đã nhận writes mà primary mới không có. `pg_rewind` so sánh timeline divergence và cập nhật data files của node cũ để đưa nó về nhánh primary mới, tránh phải copy lại toàn bộ cluster trong các điều kiện phù hợp.

### 14.2. Prerequisites

Các yêu cầu thường gồm:

- Cùng PostgreSQL major version;
- Data checksums đã bật hoặc `wal_log_hints=on` theo yêu cầu version;
- WAL đủ để xác định thay đổi kể từ checkpoint phù hợp (hoặc có thể lấy từ archive);
- Source/target data directories hợp lệ và target đã shutdown;
- Quyền truy cập và config phù hợp;
- `full_page_writes` được bật theo điều kiện tài liệu.

Đọc trang `pg_rewind` của đúng major version trước khi dùng. Không bật `wal_log_hints` sau khi divergence rồi giả định các WAL cũ đã ghi đủ thông tin.

### 14.3. Ví dụ pg_rewind

~~~bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/old-primary \
  --source-server='host=new-primary.example.internal user=rewind_user dbname=postgres'
~~~

Ví dụ minh họa; source connection cần quyền/credentials thích hợp và target server phải dừng. Sau rewind, cấu hình node thành standby, tạo `standby.signal`, `primary_conninfo`/slot và khởi động.

### 14.4. pg_rewind không phải công cụ merge dữ liệu

Nếu node cũ đã có writes cần giữ, `pg_rewind` không merge business transactions từ hai nhánh. Các writes divergent trên target sẽ bị thay thế để node theo source timeline. Xuất dữ liệu cần giữ bằng logical process trước khi rewind nếu nghiệp vụ yêu cầu.

### 14.5. Khi nào phải dùng pg_basebackup lại?

Nếu WAL cần thiết không có, checksum/hint prerequisites không đáp ứng, target/source không tương thích hoặc rewind thất bại, tạo standby mới từ base backup của primary hiện tại thường là cách rõ ràng hơn.

## 15. Yêu cầu tương thích PostgreSQL version

### 15.1. Major version phải tương thích

Physical data directory được tạo bởi một major version PostgreSQL cụ thể. Không thể khởi động PGDATA của PostgreSQL 16 bằng PostgreSQL 17 rồi coi đó là một upgrade tự động.

Ví dụ:

| Data directory | Binary | Kết quả |
| --- | --- | --- |
| PostgreSQL 16 | PostgreSQL 16 | Cùng major; kiểm tra minor/build và các yêu cầu khác |
| PostgreSQL 16 | PostgreSQL 17 | Không phải cách nâng cấp được hỗ trợ |
| PostgreSQL 17 | PostgreSQL 16 | Không tương thích; không downgrade physical |
| PostgreSQL 17 | PostgreSQL 17 | Cùng major; kiểm tra build/cluster parameters |

Muốn chuyển major version, dùng **pg_upgrade**, logical dump/restore hoặc logical replication migration theo hướng dẫn của version đích.

### 15.2. PG_VERSION

File PG_VERSION trong PGDATA ghi major version của cluster, ví dụ 16 hoặc 17. Đây là kiểm tra nhanh, nhưng vẫn cần dùng pg_controldata để xác minh metadata cluster.

### 15.3. Minor releases trong cùng major

PostgreSQL minor releases được thiết kế để giữ tương thích định dạng data files trong cùng major version, do đó data directory thường có thể được mở bằng một minor release mới hơn trong cùng major theo hướng dẫn release. Tuy vậy:

- Physical streaming replication/standby nên giữ primary và standby ở cùng minor release theo khuyến nghị hỗ trợ của version;
- Không chạy binary minor cũ hơn trên data files đã được sử dụng bởi minor mới nếu chưa xác minh rõ hỗ trợ;
- Áp dụng minor update theo quy trình chính thức, update tất cả nodes theo thứ tự HA;
- Kiểm tra release notes nếu có thay đổi liên quan WAL, recovery hoặc extension.

Với restore incident, cách ít bất ngờ nhất là bắt đầu bằng đúng major/minor/build được ghi trong backup metadata, khôi phục xong rồi áp dụng minor update theo kế hoạch.

### 15.4. WAL compatibility

WAL là định dạng nội bộ gắn với major version và build parameters. Không giả định WAL từ major version khác có thể replay trên server hiện tại. Không ghép WAL segments từ nhiều clusters chỉ vì tên file có vẻ khớp.

### 15.5. System identifier

Mỗi PostgreSQL cluster có system identifier. Base backup/standby physical thuộc cùng cluster history có identifier tương ứng. Có thể kiểm tra bằng:

~~~bash
pg_controldata -D /var/lib/postgresql/data
~~~

Tìm dòng Database system identifier. Đây là metadata quan trọng để xác định cluster source. Không dùng cách sửa system identifier để ép một data directory không tương thích.

### 15.6. Catalog version

pg_controldata cũng hiển thị catalog version number. Catalog format thay đổi giữa major releases; đây là một lý do physical data directory không thể được nâng cấp bằng cách chỉ thay executable.

### 15.7. Không dùng pg_resetwal để đổi version

pg_resetwal là công cụ cứu hộ khi WAL/control information bị hỏng trong tình huống đặc biệt. Nó không chuyển đổi storage format, không thay thế recovery từ backup và không phải cách khởi động PGDATA bằng major version khác.

## 16. Tương thích OS, CPU architecture và build

### 16.1. Physical files không phải portable interchange format

Relation files chứa page/tuple representations phụ thuộc build, alignment, endianness và các đặc tính platform. Physical backup không tương đương một SQL dump portable.

### 16.2. OS và architecture

Khi chuyển physical data directory giữa máy:

- Ưu tiên cùng operating system family và CPU architecture;
- Giữ cùng endianness và word size;
- Kiểm tra ABI/runtime dependencies;
- Dùng PostgreSQL build tương thích;
- Kiểm tra filesystem semantics, symlinks và ownership.

Không copy physical PGDATA giữa x86_64 và ARM64, hoặc giữa little-endian và big-endian, rồi mặc định server có thể đọc. Nếu cần cross-platform migration, ưu tiên logical dump/restore hoặc phương thức migration được PostgreSQL hỗ trợ.

### 16.3. Block size

PostgreSQL build có BLCKSZ (database block size), thường 8 KB. Physical data pages được tạo theo block size này. Binary có block size khác không thể đọc data directory theo cách tương thích.

### 16.4. WAL block size

WAL có block size riêng theo build. Physical recovery/replication phải dùng binary có WAL format parameters tương thích với cluster.

### 16.5. WAL segment size

WAL segment size được xác định khi tạo cluster/build theo cơ chế của version. Các cluster dùng WAL segment size khác nhau không nên được coi là physical peers tương thích. Xác minh Bytes per WAL segment trong pg_controldata.

### 16.6. Các build options khác

Một số build options/compile-time constants có thể ảnh hưởng physical compatibility hoặc extension ABI. Khi dùng custom builds, ghi lại:

- PostgreSQL version và source commit/vendor build;
- BLCKSZ;
- WAL block size;
- WAL segment size;
- Compiler/ABI/platform;
- Optional features và linked libraries;
- Extension package versions.

### 16.7. pg_controldata để kiểm tra metadata

~~~bash
pg_controldata -D /var/lib/postgresql/data
~~~

Các trường cần lưu:

- Database system identifier;
- Database cluster state;
- Latest checkpoint location;
- Latest checkpoint's REDO location;
- Latest checkpoint's TimeLineID;
- Database block size;
- WAL block size;
- Bytes per WAL segment;
- Data page checksum version;
- Catalog version number.

Tên trường có thể thay đổi nhẹ theo major version. Dùng binary pg_controldata đúng version của cluster.

### 16.8. Kiểm tra server build

~~~sql
SELECT version();
SHOW server_version;
SHOW block_size;
SHOW wal_block_size;
SHOW wal_segment_size;
SHOW data_checksums;
~~~

Không phải mọi GUC đều tồn tại trên mọi major release; nếu SHOW wal_segment_size không được hỗ trợ, dùng pg_controldata.

### 16.9. Tablespace paths và filesystem

Một cluster có thể lưu relation files trên nhiều mount points. Restore lên máy mới cần mount đúng volumes hoặc map tablespaces sang paths mới. Kiểm tra case sensitivity, path length, filesystem permissions, symlink support và storage capacity.

### 16.10. Không đồng nhất disk sector size với PostgreSQL block size

BLCKSZ, WAL block size và sector size của storage là các khái niệm khác nhau. Cùng dùng 8 KB PostgreSQL page không bảo đảm hai storage devices có durability/atomic write semantics giống nhau.

## 17. Tablespaces, config và external dependencies

### 17.1. Tablespaces có thể nằm ngoài PGDATA

PostgreSQL lưu metadata tablespace trong catalog và link dưới PGDATA/pg_tblspc. Nội dung thực tế của tablespace nằm ở đường dẫn riêng. Nếu chỉ backup PGDATA mà bỏ qua tablespace targets, restore có thể thiếu relation files.

### 17.2. Kiểm tra tablespaces trong SQL

~~~sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location,
    pg_tablespace_size(oid) AS size_bytes
FROM pg_tablespace
ORDER BY spcname;
~~~

Tablespace mặc định có location rỗng theo semantics của hàm. Ghi lại tablespace name, path, owner, mount/volume và dung lượng trước backup/restore.

### 17.3. pg_basebackup và tablespaces

`pg_basebackup` có thể copy tablespaces và tạo directories tương ứng theo format. Khi đích khác path nguồn, dùng tablespace mapping (`-T`) phù hợp. Kiểm tra output backup, symlinks và mọi tablespace archive.

### 17.4. External WAL directory

`pg_wal` có thể được đặt ở filesystem riêng bằng symlink. Khi restore, cần khôi phục WAL directory đúng path và permissions; nếu backup format có WAL riêng, xử lý theo format/tool.

### 17.5. Config ngoài PGDATA

Các files sau có thể được đặt ngoài data directory:

- `postgresql.conf`;
- `pg_hba.conf`;
- `pg_ident.conf`;
- SSL CA/cert/private key;
- `archive_command`/`restore_command` scripts;
- Include files và environment files;
- Service manager definitions.

Ghi lại đường dẫn hiệu lực bằng:

~~~sql
SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW ssl;
SHOW ssl_cert_file;
SHOW ssl_key_file;
~~~

### 17.6. postgresql.auto.conf

File `postgresql.auto.conf` nằm trong PGDATA và có thể chứa settings do ALTER SYSTEM hoặc `pg_basebackup -R` ghi. Sau restore, kiểm tra hostnames, paths, slots, `primary_conninfo`, archive commands và parameters còn phù hợp với node mới.

### 17.7. Không mang nguyên config của primary sang mọi node

Một số settings là node-specific:

- `listen_addresses`, port;
- `primary_conninfo`, `primary_slot_name`;
- `restore_command`, `archive_command`;
- SSL paths;
- `hot_standby`, `synchronous_standby_names`;
- `archive_mode` và các settings cho role hiện tại.

Cấu hình copy nguyên xi có thể làm standby kết nối nhầm primary, archive sai đích hoặc hai node dùng cùng identity/service endpoint.

### 17.8. Extension binaries

Physical backup giữ SQL catalogs và objects của extensions, nhưng không tự cài shared libraries/packages vào hệ điều hành đích. Trước khi start:

1. Cài extension packages tương thích major version;
2. Đảm bảo shared libraries nằm đúng library path;
3. Kiểm tra `shared_preload_libraries`;
4. Cài dependencies hệ thống;
5. Xác minh extension versions trong catalogs.

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

### 17.9. shared_preload_libraries

Nếu config yêu cầu preload một extension library không có trên máy restore, PostgreSQL có thể không start. Kiểm tra:

~~~sql
SHOW shared_preload_libraries;
~~~

Trên server chưa start, đọc config files và cài package tương ứng hoặc điều chỉnh config theo recovery plan. Không xóa extension catalogs để làm server khởi động.

### 17.10. Extension version upgrade

Sau physical restore, extension SQL version thường giống trạng thái tại backup. Nếu môi trường đích cài binary extension version khác, có thể phát sinh mismatch. Cài đúng package version trước; sau khi server hoạt động và backup/rollback đã sẵn sàng, thực hiện `ALTER EXTENSION ... UPDATE` theo hướng dẫn vendor.

### 17.11. Foreign data wrappers và external services

FDW definitions có thể được lưu trong catalogs, nhưng drivers, client libraries, certificates, remote credentials, network routes và remote systems không nằm trong physical backup. Kiểm tra chúng như external dependencies.

### 17.12. Encryption keys và KMS

Nếu storage encryption, TDE-like extension hoặc application-level encryption dùng key bên ngoài PGDATA, restore cần quyền truy cập key/KMS và version-compatible libraries. Backup ciphertext mà không có key recovery process có thể không sử dụng được.

### 17.13. Secrets

Không đặt passwords, private keys hoặc KMS credentials vào source control hay backup manifest. Quản lý secrets qua secret manager, rotate theo quy trình và kiểm tra quyền truy cập từ host restore.

## 18. Collation, locale và compatibility của indexes

### 18.1. Vì sao locale ảnh hưởng physical restore?

PostgreSQL có thể dùng libc hoặc ICU để so sánh/sắp xếp text theo locale. B-tree indexes trên text/collation phụ thuộc thứ tự so sánh đó. Khi restore sang máy có libc/ICU version khác, thứ tự collation thực tế có thể thay đổi.

### 18.2. Data files có thể start nhưng index ordering đã cũ

Physical restore vẫn có thể thành công, nhưng nếu collation behavior thay đổi, một số indexes được xây dưới version cũ có thể không còn phản ánh thứ tự hiện tại. Điều này có thể dẫn tới query results/order hoặc index lookups không đúng kỳ vọng nếu không xử lý.

### 18.3. Kiểm tra database collation version

~~~sql
SELECT
    datname,
    datcollversion,
    pg_database_collation_actual_version(oid) AS actual_version
FROM pg_database
WHERE datcollversion IS DISTINCT FROM
      pg_database_collation_actual_version(oid);
~~~

Tên function/cột và khả năng có mặt tùy major version. Có thể cần kiểm tra từng collation trong `pg_collation` bằng `pg_collation_actual_version(oid)`.

### 18.4. Xử lý collation version mismatch

Khi actual version khác recorded version:

1. Xác định database/collation nào bị ảnh hưởng;
2. Tìm indexes và objects phụ thuộc collation;
3. Lập kế hoạch REINDEX các indexes cần thiết;
4. Chạy REINDEX trong maintenance window hoặc concurrent nếu loại index/version cho phép;
5. Sau khi rebuild xong, refresh recorded collation version bằng lệnh phù hợp;
6. Kiểm tra query results và application behavior.

Không chạy `ALTER DATABASE ... REFRESH COLLATION VERSION` rồi cho rằng indexes đã được rebuild. Lệnh refresh chỉ cập nhật metadata version; nó không tự sửa các indexes đã xây theo collation cũ.

### 18.5. ICU/libc version phải được ghi lại

Ghi nhận:

- Operating system distribution/release;
- libc version;
- ICU version;
- Database locale/encoding;
- Collation provider và recorded collation version;
- Kế hoạch REINDEX sau OS upgrade.

### 18.6. Encoding

Database encoding cũng là thuộc tính của database. Physical backup giữ encoding hiện có; không thể đổi encoding chỉ bằng cách restore bằng binary khác. Muốn chuyển encoding, dùng logical migration và kiểm tra dữ liệu có thể biểu diễn trong encoding đích.

## 19. Các yêu cầu compatibility khác

### 19.1. Data checksums

Checksum state là metadata của cluster. Kiểm tra bằng:

~~~sql
SHOW data_checksums;
~~~

Khi restore physical backup, không bật/tắt checksum tùy tiện trên từng node. Nếu cần chuyển đổi trạng thái, dùng `pg_checksums` offline theo đúng major version và đồng bộ quy trình trên topology.

### 19.2. WAL segment size và backup metadata

WAL segment size phải tương thích với cluster/build dùng để phục hồi/replication. Ghi lại `Bytes per WAL segment` từ `pg_controldata`; không tự tạo segment rỗng để bù file thiếu.

### 19.3. Shared memory và OS limits

Server mới có thể cần điều chỉnh:

- Shared memory limits;
- Huge pages;
- `max_connections`;
- `shared_buffers`;
- File descriptor limits;
- Process/thread limits;
- Kernel settings;
- Cgroup/container memory and CPU limits.

Các settings này thường không làm thay đổi data format nhưng có thể khiến server không start hoặc hoạt động kém sau restore.

### 19.4. Architecture-specific extension

Extension binary có thể phụ thuộc CPU architecture, compiler ABI và system libraries. Một extension package cho x86_64 không thể được dùng nguyên trạng trên ARM64; cài đúng package/build cho host đích.

### 19.5. Locale provider và collation

Locale provider libc/ICU, ICU locale data và OS packages có thể khác. Physical copy không tái tạo môi trường locale của host nguồn. Kiểm tra trước khi mở traffic production.

### 19.6. Encryption at rest

Storage encryption có thể ở block device, cloud volume, filesystem hoặc extension. Restore cần key, KMS permissions và quy trình mount/decrypt tương ứng. Key rotation không được làm mất khả năng đọc backup cũ.

### 19.7. Hostname, DNS và network identity

Config có thể giữ hostname primary cũ, TLS SAN, DNS aliases hoặc endpoint. Khi restore sang host mới, kiểm tra service discovery, certificates, firewall, `pg_hba.conf`, routing và monitoring labels.

### 19.8. Version của client không phải server compatibility

Client `psql` mới thường có thể kết nối server cũ trong giới hạn protocol/features, nhưng điều đó không có nghĩa server binary có thể đọc physical data files của major version khác. Phân biệt client/server protocol với on-disk compatibility.

### 19.9. Logical replication và extensions

Nếu sau restore chuyển sang logical replication hoặc migration, kiểm tra publication/subscription state, replication slots, replica identity, extension support và DDL synchronization. Các objects trong catalogs không đảm bảo external consumers đã được khôi phục.

### 19.10. Configuration drift

Giữ cấu hình bằng infrastructure-as-code hoặc config management. So sánh server parameters trước/sau restore; không chỉ dựa vào config nằm trong PGDATA vì một số values đến từ command line, environment, auto.conf, include files hoặc managed service.

## 20. Ma trận tương thích khi physical restore

### 20.1. Bảng quyết định nhanh

| Thành phần | Yêu cầu/khuyến nghị | Nếu không khớp |
| --- | --- | --- |
| PostgreSQL major version | Cùng major version | Physical start/replay không được hỗ trợ; dùng upgrade/migration |
| Minor version | Cùng minor là lựa chọn ít rủi ro; minor releases trong cùng major giữ data format theo policy | Kiểm tra release notes, WAL/replication support; không dùng binary cũ hơn tùy tiện |
| OS/CPU architecture | Cùng platform/ABI/endianness được hỗ trợ | Ưu tiên logical migration |
| Database block size | Phải khớp build/cluster | Binary không đọc được page format |
| WAL block/segment size | Phải tương thích | WAL/recovery/replication có thể không hoạt động |
| Catalog version | Phải phù hợp major version | Data directory không thể mở bằng binary khác major |
| Tablespaces | Phải có đủ files và paths hợp lệ | Relation files missing hoặc server không start |
| Checksums | Giữ trạng thái cluster và công cụ đúng version | Checksum validation/rewind có thể lỗi |
| Extensions | Shared libraries/dependencies tương thích | Startup error hoặc extension functions không hoạt động |
| Collation/locale | Provider/version phải được xác minh | Cần REINDEX indexes phụ thuộc collation |
| Config/SSL/secrets | Phải có và phù hợp host đích | Connection, TLS, archive hoặc startup failure |
| WAL archive/timeline | WAL liên tục và đúng timeline | Recovery không thể tới target |

### 20.2. Những trường hợp nên chọn logical migration

Ưu tiên logical dump/restore hoặc logical replication khi:

- Chuyển major version;
- Chuyển OS/CPU architecture hoặc endianness;
- Muốn thay database encoding;
- Muốn chọn lọc databases/schemas/tables;
- Cần thay đổi schema/data model trong quá trình di chuyển;
- Physical build parameters không tương thích;
- Cần tái tổ chức tablespaces hoặc indexes theo thiết kế mới.

### 20.3. Physical restore và pg_upgrade khác nhau

Physical restore phục hồi cluster ở cùng on-disk major format. `pg_upgrade` là quy trình nâng cấp major version có kiểm tra catalog/data compatibility và thực hiện chuyển đổi cần thiết. Không dùng base backup như một bước thay thế cho pg_upgrade.

### 20.4. Không suy ra tương thích từ version string đơn lẻ

Hai server cùng hiển thị PostgreSQL 17 vẫn có thể khác:

- Build options;
- BLCKSZ;
- WAL segment size;
- OS/CPU;
- Extension libraries;
- Locale provider/version;
- Checksum state;
- Tablespace layout.

Ghi inventory cả build/cluster metadata, không chỉ server_version.

## 21. Kiểm tra cluster trước và sau restore

### 21.1. Lập inventory ở source

Trước backup, ghi:

~~~sql
SELECT version();
SHOW server_version;
SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW block_size;
SHOW wal_block_size;
SHOW wal_segment_size;
SHOW data_checksums;
SHOW archive_mode;
SHOW archive_command;
SHOW full_page_writes;
SHOW fsync;
~~~

Không phải mọi setting có mặt ở mọi major version. Lưu cả output `pg_controldata`, `pg_extension`, `pg_tablespace`, database encodings/collations và config files.

### 21.2. Ghi database inventory

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype,
    datlocprovider,
    datcollversion
FROM pg_database
ORDER BY datname;
~~~

Một số cột như `datlocprovider`/`datcollversion` phụ thuộc major version. Trên version cũ, query cần điều chỉnh. Lưu ý các template databases và database-level settings.

### 21.3. Ghi tablespace inventory

~~~sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location,
    pg_tablespace_size(oid) AS size_bytes
FROM pg_tablespace
ORDER BY spcname;
~~~

### 21.4. Ghi extension inventory

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS schema_name
FROM pg_extension AS e
JOIN pg_namespace AS n ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

### 21.5. Ghi role/global objects

Physical backup giữ global catalogs trong cluster. Tuy vậy, backup plan nên ghi roles, memberships, tablespaces, replication users, passwords/authentication dependencies và external secrets. Nếu chuyển sang logical restore, phải dump globals bằng công cụ phù hợp.

### 21.6. Sau restore: kiểm tra recovery state

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
~~~

Trên standalone primary, receive/replay LSN có thể NULL sau recovery hoàn tất. Trên standby, theo dõi khoảng cách receive/replay và timestamp.

### 21.7. Kiểm tra database availability

~~~sql
SELECT
    datname,
    datallowconn,
    datconnlimit,
    pg_database_size(oid) AS database_bytes
FROM pg_database
ORDER BY datname;
~~~

Kết nối thử vào các database quan trọng bằng application roles; không chỉ dùng superuser.

### 21.8. Kiểm tra tablespace locations

Chạy lại query inventory ở 21.3 và đối chiếu từng path với mount/volume thực tế. Thử truy cập tablespace objects có dữ liệu ở path ngoài PGDATA.

### 21.9. Kiểm tra archive và replication

Trên primary sau cutover:

~~~sql
SELECT * FROM pg_stat_archiver;
SELECT * FROM pg_stat_replication;
~~~

Trên standby:

~~~sql
SELECT * FROM pg_stat_wal_receiver;
~~~

Xác nhận archive đang tiến triển, standby kết nối đúng primary và LSN lag nằm trong ngưỡng.

### 21.10. Kiểm tra extension functions

Chạy smoke tests cho từng extension quan trọng: PostGIS, pgcrypto, timescaledb, pg_partman, FDW hoặc extension nội bộ nếu có. Kiểm tra shared libraries và external services, không chỉ catalog rows.

## 22. Restore validation và integrity checks

### 22.1. Restore test là bằng chứng quan trọng nhất

Backup job xanh không chứng minh database có thể phục hồi. Restore test phải thực hiện trên môi trường tách biệt, dùng đúng binary, config, tablespaces, extension packages, secrets và WAL archive.

### 22.2. Các lớp kiểm tra

| Lớp | Công cụ/cách kiểm tra | Điều xác minh |
| --- | --- | --- |
| Backup files | `pg_verifybackup` | Manifest/files và WAL checks theo tool |
| Cluster metadata | `pg_controldata` | System identifier, versions, block/WAL metadata |
| Page checksums | `pg_checksums --check` khi offline | Page checksums trên cluster đã bật checksum |
| WAL | Recovery logs, `pg_waldump` | WAL có thể đọc/parse theo mục tiêu kiểm tra |
| Indexes | `pg_amcheck`/`amcheck` | Một số cấu trúc heap/index consistency |
| SQL/application | Smoke tests, business queries | Dữ liệu và ứng dụng hoạt động đúng |
| DR | Restore/PITR drill | RPO/RTO thực tế |

Không một tool nào thay thế các lớp còn lại.

### 22.3. pg_checksums

Nếu cluster có data checksums, có thể shutdown sạch và chạy:

~~~bash
pg_checksums --check -D /var/lib/postgresql/data --progress
~~~

Đây là scan I/O toàn cluster. Dùng binary đúng major version. Nếu checksum state đang off, lệnh không thể chứng minh page integrity bằng data checksums.

### 22.4. pg_amcheck

Ở các version hỗ trợ:

~~~bash
pg_amcheck --all
~~~

`pg_amcheck` dùng các kiểm tra của extension `amcheck` để phát hiện một số bất thường trong heap/index structures. Options và quyền phụ thuộc version; có thể cần superuser hoặc role có quyền thích hợp. Đây không phải checksum scan toàn bộ bytes và không thay thế backup.

### 22.5. WAL inspection

`pg_waldump` có thể đọc WAL records để điều tra LSN/timeline/record types:

~~~bash
pg_waldump -p /var/lib/postgresql/data/pg_wal
~~~

Dùng cho diagnostics và kiểm tra format/records theo mục tiêu; không sửa WAL bằng công cụ này. Options/path khác nhau theo version.

### 22.6. Checkpoint metadata

`pg_controldata` cho biết cluster state, checkpoint, REDO location và timeline. Khi recovery vừa hoàn tất, đối chiếu log và metadata nếu cần điều tra. Không chỉnh trực tiếp `pg_control`.

### 22.7. SQL consistency checks

Chạy các truy vấn nghiệp vụ đã định nghĩa trước:

- Row counts và aggregate totals;
- Referential integrity và foreign key checks;
- Duplicate detection cho business keys;
- Date/time range của dữ liệu gần target;
- Sequence values và identity columns;
- Materialized views/derived data freshness;
- Application smoke tests và read/write tests có kiểm soát.

Không dùng một query `COUNT(*)` duy nhất làm bằng chứng toàn database đúng.

### 22.8. Sequence values

Physical backup giữ sequence state tại backup/recovery point. Sau PITR, sequence có thể ở trạng thái khác so với các business records nếu logic ứng dụng quản lý sequence ngoài transaction hoặc dữ liệu được import đặc biệt. Kiểm tra sequences quan trọng và đảm bảo next value không đụng primary keys hiện có.

### 22.9. Foreign keys và constraints

Physical recovery bảo tồn catalog definitions và data state theo WAL. Tuy nhiên, chạy business validation sau restore vẫn hữu ích, đặc biệt nếu trước incident có constraint disabled, replication apply hoặc bulk load. Không tự disable constraints để làm restore pass.

### 22.10. Kiểm tra performance sau restore

Sau restore/cutover:

- Kiểm tra query plans;
- Xác nhận statistics/ANALYZE theo nhu cầu;
- Kiểm tra cache warm-up;
- Kiểm tra I/O latency và storage throughput;
- Kiểm tra connection pools;
- Kiểm tra autovacuum và background workers;
- Kiểm tra replication lag và archive throughput.

Một server restored có thể đúng dữ liệu nhưng hiệu năng khác do cache lạnh, storage khác, OS settings hoặc collation/index differences.

## 23. Backup architecture, retention và RPO/RTO

### 23.1. RPO

Recovery Point Objective là lượng dữ liệu tối đa có thể chấp nhận mất khi sự cố. RPO phụ thuộc tần suất base backup, WAL archiving/streaming, archive latency và khả năng giữ WAL liên tục.

### 23.2. RTO

Recovery Time Objective là thời gian mục tiêu để dịch vụ trở lại hoạt động. RTO phụ thuộc:

- Kích thước base backup;
- Tốc độ storage/network;
- Số incremental backups phải combine;
- WAL volume cần replay;
- Extension/config readiness;
- Validation và cutover steps;
- Capacity/automation của DR site.

### 23.3. Full backup + WAL archive

~~~text
PostgreSQL primary
      |
      +---- base backup schedule
      |           |
      |           v
      |      Backup repository
      |
      +---- WAL archive pipeline
                  |
                  v
             WAL repository
                  |
                  v
          Restore/PITR environment
~~~

Base backup cung cấp data files; WAL archive đưa cluster tới target. Hai phần phải được quản lý như một recovery set.

### 23.4. Backup retention

Giữ base backups đủ lâu để đáp ứng retention policy và WAL cần thiết cho từng backup. Không xóa WAL segments chỉ vì đã qua một số ngày nếu chúng vẫn cần cho backup còn được giữ.

### 23.5. Archive cleanup

Dùng công cụ như `pg_archivecleanup` hoặc backup manager có catalog để xác định WAL không còn cần thiết. Không dùng `rm *.wal` hoặc xóa theo timestamp tùy tiện; cần xét backup chains, timeline history, standbys và replication slots.

### 23.6. Backup failure domain

Giữ backup ở storage/location tách biệt với primary. Với hệ thống quan trọng, cân nhắc immutable/object-lock, cross-region copy, encryption, restricted delete permissions và monitoring riêng.

### 23.7. 3-2-1 và bản offline

Một nguyên tắc vận hành thường dùng là nhiều bản sao, nhiều loại storage và ít nhất một bản ngoài site/offline/immutable. Số lượng cụ thể tùy policy, nhưng phải có phương án khi primary và backup storage cùng bị ảnh hưởng.

### 23.8. WAL archive monitoring

Theo dõi:

- Archive success/failure counters;
- Thời điểm WAL cuối cùng được archive;
- WAL bytes per minute/hour;
- Disk usage và object count;
- Replication slot retained WAL;
- Archive upload/download latency;
- Missing segment/timeline history alarms.

### 23.9. Restore drill

Lập lịch drill có mục tiêu:

1. Chọn một base backup và target time;
2. Restore vào môi trường cô lập;
3. Replay WAL;
4. Validate cluster/application;
5. Đo thời gian từng giai đoạn;
6. Ghi RPO/RTO đạt được;
7. Cập nhật runbook và khắc phục blockers.

### 23.10. Backup có encrypted nhưng key mất

Backup không sử dụng được nếu mất key cần giải mã. Kiểm tra quy trình key escrow/rotation, KMS recovery, IAM roles và quyền của DR environment; thử restore khi không phụ thuộc vào credentials của primary.

## 24. Troubleshooting khi physical restore

### 24.1. Server báo wrong database system identifier

Nguyên nhân có thể là WAL/standby source thuộc một cluster khác, backup không đúng nguồn hoặc trộn files từ nhiều clusters. Xác minh system identifier bằng `pg_controldata`, backup metadata và nguồn WAL. Không sửa system identifier để ép recovery.

### 24.2. Server báo database files are incompatible with server

Kiểm tra:

- Major version trong PG_VERSION;
- Binary PostgreSQL đang dùng;
- Catalog version;
- Block size và WAL format;
- Restore có copy nhầm PGDATA của cluster khác không.

Dừng thử start bằng binary khác một cách ngẫu nhiên; xác định đúng nguồn backup và version.

### 24.3. WAL segment not found

Kiểm tra `restore_command`, archive path, credentials, filename mapping, compression/encryption và timeline history. Xác định segment bị thiếu thực sự hay command không thể truy cập file.

Không tạo file rỗng hoặc đổi tên segment để làm recovery đi tiếp.

### 24.4. WAL record CRC error

Đây có thể là WAL corruption do storage/transfer/archive. Giữ bản segment lỗi và logs; so sánh với archive/standby copies, kiểm tra device/network/storage và chọn backup/WAL chain còn nguyên. Không sửa CRC bytes bằng tay.

### 24.5. Invalid checkpoint record

Có thể control file hoặc WAL liên quan bị hỏng/không khớp. Bảo vệ bản copy gốc, kiểm tra `pg_controldata`, logs, WAL archive và backup. Không chạy `pg_resetwal` như phản xạ đầu tiên.

### 24.6. Missing tablespace directory

Kiểm tra `pg_tblspc` links, mount points, mapping options và owner. Restore đúng tablespace files trước khi start. Không tạo thư mục rỗng với cùng tên để đánh lừa server.

### 24.7. Could not load library

Thường do extension shared library hoặc dependency không có trên host đích. Cài package tương thích, kiểm tra library path và preload settings. Nếu extension không cần cho lần startup cứu hộ, chỉ điều chỉnh config sau khi hiểu ảnh hưởng; không xóa catalog objects.

### 24.8. Permission denied

Kiểm tra owner/group, data directory mode, private key permissions, tablespace permissions, SELinux/AppArmor policy và service user. Tránh chmod 777 để “chữa” lỗi.

### 24.9. Address already in use

Một instance khác đang dùng port/socket hoặc service cũ chưa được dừng. Xác nhận process và data directory; không start hai server cùng dùng một PGDATA.

### 24.10. Server starts but application cannot connect

Kiểm tra `listen_addresses`, port, `pg_hba.conf`, TLS certificates, DNS, firewall, role/password, database name và connection pool. Physical restore không tự cập nhật external network identity.

### 24.11. Checksum mismatch after restore

Ghi relation/block và server/node/time. Xác minh backup manifest, data checksums, WAL, storage/transfer path và checksum state. Một backup manifest pass không chứng minh page checksum đã pass. Chạy offline verification trên bản sao phù hợp và cân nhắc restore từ một backup khác.

### 24.12. Collation version mismatch

Xác định collations bị ảnh hưởng, lập kế hoạch REINDEX objects phụ thuộc và chỉ refresh recorded version sau khi xử lý indexes. Không bỏ qua cảnh báo nếu database dùng text indexes cho uniqueness/order.

### 24.13. Recovery stops at the wrong time

Kiểm tra timezone, timestamp literal, transaction commit time, `recovery_target_inclusive`, target timeline và archive WAL availability. Dựng một bản restore thử khác trước khi cutover.

### 24.14. Standby cannot connect to primary

Kiểm tra `primary_conninfo`, DNS/network/TLS, replication role, `pg_hba.conf`, port, slot name và `max_wal_senders`. Xem log receiver và `pg_stat_wal_receiver`.

### 24.15. Standby is stuck or replay lag grows

Kiểm tra WAL receiver state, replication slot retention, archive availability, recovery conflicts, disk I/O và WAL generation rate. Đừng xóa slot hoặc WAL segment chỉ để giảm disk usage.

### 24.16. pg_rewind prerequisites not met

Xác minh checksums hoặc `wal_log_hints` đã bật trước khi divergence, WAL cần thiết còn có, target đã shutdown và source/target cùng major version. Nếu không đủ, tạo lại standby từ base backup.

### 24.17. pg_verifybackup fails

Phân loại file missing, checksum mismatch, unexpected file, WAL parse failure hoặc tool/version mismatch. Giữ nguyên backup gốc; không chỉnh manifest để ép pass. Tạo backup mới nếu artifact không thể xác minh.

### 24.18. Incremental backup cannot be combined

Kiểm tra đúng base backup, toàn bộ incremental chain, manifests, backup ordering và `pg_combinebackup` version. Không bỏ qua incremental giữa chuỗi hoặc combine backups từ các clusters khác nhau.

### 24.19. Disk fills during restore

Kiểm tra dung lượng PGDATA, tablespaces, `pg_wal`, temporary restore path, incremental combine output và WAL archive cache. Dừng/cô lập quy trình có kiểm soát trước khi storage hết hoàn toàn. Không xóa file relation/WAL để giải phóng disk.

### 24.20. Recovery succeeds but data is not what user expects

Kiểm tra base backup timestamp, recovery target, timeline, inclusive/exclusive behavior, timezone, application audit logs và transaction commit times. Một recovery thành công về kỹ thuật vẫn có thể chọn sai target nghiệp vụ.
## 25. Runbook: phục hồi toàn cluster sau khi mất primary

### 25.1. Kích hoạt DR

Khi primary mất hoàn toàn:

1. Xác nhận incident và phạm vi ảnh hưởng;
2. Fencing primary cũ để không có khả năng nhận writes trở lại;
3. Chọn backup/WAL archive gần nhất đã xác minh;
4. Xác nhận RPO dự kiến và điểm WAL cuối cùng có sẵn;
5. Chọn host/storage restore tương thích;
6. Chuẩn bị tablespaces, config, extension packages, secrets và certificates;
7. Thông báo trạng thái DR/cutover theo incident process.

### 25.2. Chọn base backup

Chọn base backup có:

- Manifest/verification hợp lệ;
- Major version/build metadata rõ;
- Tablespaces đầy đủ;
- WAL archive continuity từ backup start/stop;
- Timeline history cần thiết;
- Backup timestamp nằm trong retention.

Nếu có nhiều bản backup, chọn bản đáp ứng RPO và WAL chain có thể replay tới target.

### 25.3. Restore vào host đích

1. Cài PostgreSQL binary đúng major version;
2. Chuẩn bị filesystem/PGDATA rỗng và tablespace paths;
3. Restore backup files và ownership;
4. Cài extension libraries;
5. Đặt config và secrets;
6. Xác nhận WAL archive/restore command;
7. Tạo `recovery.signal` nếu cần archive recovery;
8. Khởi động server và theo dõi logs.

### 25.4. Replay WAL tới latest available

Nếu mục tiêu là khôi phục tối đa dữ liệu, cấu hình archive recovery theo timeline mới nhất phù hợp. Kiểm tra archive command có thể đọc mọi WAL segment và `.history` file cần thiết.

Không promote chỉ vì server đã start; đợi recovery hoàn tất hoặc dừng tại target được chọn.

### 25.5. Validate trước cutover

- `pg_is_in_recovery()` phản ánh trạng thái mong muốn;
- Databases và tablespaces mở được;
- Extensions load được;
- Critical business queries trả dữ liệu hợp lý;
- Sequences/constraints được kiểm tra;
- Checksum/backup verification theo khả năng;
- Application roles có thể kết nối;
- Monitoring, backup và WAL archiving được cấu hình.

### 25.6. Promote và cutover

Khi dữ liệu được xác nhận và primary cũ đã fencing:

~~~sql
SELECT pg_promote(wait => true);
~~~

Chuyển DNS/VIP/load balancer/connection endpoint sang node mới. Theo dõi application errors, connection pool, write throughput và replication setup.

### 25.7. Sau cutover

- Tạo base backup mới từ primary mới;
- Bắt đầu WAL archive trên timeline mới;
- Dựng lại standby;
- Xác nhận backup/restore chain;
- Ghi lại RPO/RTO thực tế;
- Điều tra nguyên nhân primary mất;
- Giữ bản cũ cho forensics tới khi được phép xử lý.

## 26. Runbook: PITR sau thao tác dữ liệu sai

### 26.1. Ngăn sự cố lan rộng

Khi phát hiện DELETE/UPDATE/DDL sai:

1. Dừng hoặc hạn chế writer/job gây lỗi;
2. Ghi lại thời điểm bắt đầu, transaction/user/job và database;
3. Bảo vệ WAL archive và base backups;
4. Xác định transaction commit time/target;
5. Không phục hồi đè trực tiếp primary trước khi có bản thử.

### 26.2. Tạo môi trường restore tách biệt

Restore base backup vào một host/PGDATA riêng. Không chạy PITR trên cùng PGDATA primary đang phục vụ ứng dụng. Dùng WAL archive tới ngay trước/sau target theo business requirement.

### 26.3. Chọn recovery target

Có thể dùng timestamp, transaction ID, named restore point hoặc LSN. Nếu không chắc target, tạo nhiều restore candidates trên môi trường riêng và so sánh dữ liệu.

### 26.4. Pause tại target

Cấu hình `recovery_target_action='pause'`, tạo `recovery.signal` và start. Khi replay dừng:

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
~~~

Xác nhận transaction gây lỗi chưa được replay hoặc target đã giữ đúng dữ liệu mong muốn. Cần xem commit order và transaction boundary.

### 26.5. Xuất dữ liệu cần khôi phục

Nếu chỉ một vài tables/rows bị ảnh hưởng, có thể export dữ liệu từ restored cluster bằng logical dump/query rồi import có kiểm soát vào production. Điều này thường giảm downtime so với thay toàn bộ production cluster.

Nếu toàn bộ cluster cần quay về target, lập kế hoạch cutover toàn bộ và chấp nhận mất transactions sau target theo RPO/business approval.

### 26.6. Promote restored cluster

Nếu dùng restored cluster thay production, chỉ promote sau khi xác nhận target và fencing primary hiện tại. Khi promote, timeline mới bắt đầu. Thiết lập lại archive, backup và standby.

### 26.7. Không import dữ liệu bằng cách copy relation files

Không copy table/index files từ restored cluster vào primary đang chạy. Dùng logical export/import, replication hoặc một phương thức physical recovery toàn cluster được hỗ trợ.

## 27. Runbook: chuyển physical cluster sang storage mới

### 27.1. Chọn phương pháp

Các lựa chọn:

- `pg_basebackup` tới storage mới rồi cutover;
- Cold copy sau shutdown sạch;
- Backup API + consistent storage snapshot;
- Dựng standby trên storage mới rồi switchover.

Chọn dựa trên downtime, data size, network bandwidth, tablespaces và RPO.

### 27.2. Dùng standby để giảm downtime

1. Tạo base backup trên storage mới;
2. Khởi động node mới ở standby mode;
3. Stream WAL và chờ replay lag về gần zero;
4. Kiểm tra extensions/config/collation;
5. Dừng writes hoặc chuyển ứng dụng vào maintenance;
6. Chờ standby replay hết WAL đã gửi;
7. Promote/switchover theo HA runbook;
8. Chuyển endpoint và xác nhận application.

### 27.3. Xác minh storage mới

Đo IOPS, latency, throughput, flush semantics, filesystem capacity và error counters. Không chỉ so dung lượng tổng. Storage mới cần đáp ứng durability và workload profile.

### 27.4. Giữ đường quay lại

Sau switchover, node cũ có thể bị divergent khi node mới nhận writes. Không start node cũ như primary. Giữ offline hoặc rewind/rebuild nó thành standby sau khi xác nhận quy trình.

## 28. Checklist tương thích trước khi restore

### 28.1. PostgreSQL

- [ ] Đúng major version của backup.
- [ ] Đã ghi minor version và chọn binary phù hợp.
- [ ] Đã xác minh `PG_VERSION`.
- [ ] Đã kiểm tra system identifier/catalog version.
- [ ] Đã kiểm tra block size/WAL block size/WAL segment size.
- [ ] Đã xác nhận checksum state.
- [ ] Không dùng `pg_resetwal` để ép start hoặc đổi version.

### 28.2. Platform

- [ ] OS/CPU architecture/endianness phù hợp.
- [ ] PostgreSQL build và ABI tương thích.
- [ ] Filesystem hỗ trợ permissions/symlinks cần thiết.
- [ ] Tablespace và WAL mount points đã sẵn sàng.
- [ ] Đủ disk, memory, CPU, file descriptors và shared memory.
- [ ] Storage flush/durability semantics đã xác minh.

### 28.3. Dependencies

- [ ] Extension packages/libraries đã cài đúng version/architecture.
- [ ] Shared preload libraries có sẵn.
- [ ] Locale/libc/ICU version đã đối chiếu.
- [ ] Collation mismatch đã được xử lý theo kế hoạch REINDEX.
- [ ] FDW drivers/remote services có sẵn.
- [ ] SSL certificates, private keys, KMS keys và secrets sẵn sàng.
- [ ] DNS, network, firewall và `pg_hba.conf` đúng host đích.

### 28.4. Backup/WAL

- [ ] Base backup được xác minh.
- [ ] WAL archive liên tục từ backup tới target.
- [ ] Timeline history files có đầy đủ.
- [ ] Backup manifest/metadata được giữ.
- [ ] Incremental chain đầy đủ nếu dùng incremental backup.
- [ ] Tablespaces đã được backup/mapping.
- [ ] Backup có restore test thành công.

### 28.5. Cutover/DR

- [ ] Primary cũ đã fencing.
- [ ] RPO/RTO được hiểu và ghi nhận.
- [ ] Recovery target đã được kiểm chứng.
- [ ] Business validation đã pass.
- [ ] Monitoring/archive/backup trên node mới hoạt động.
- [ ] Standby được dựng lại hoặc có kế hoạch rõ.
- [ ] Endpoint/application connection đã chuyển đúng.
- [ ] Có incident notes và rollback/rebuild plan.

## 29. Bài tập thực hành: physical recovery và compatibility

Các bài tập dùng PostgreSQL lab hoặc tình huống giả lập. Không chạy restore/overwrite/pg_resetwal trên production chỉ để làm bài. Với câu hỏi phụ thuộc version, kiểm tra documentation của major version đang học.

### Bài 1 — Physical vs logical

So sánh physical backup và logical backup theo phạm vi, version compatibility, tốc độ restore và khả năng chọn một table.

### Bài 2 — Base backup

Giải thích base backup là gì và vì sao physical restore thường phục hồi toàn bộ cluster.

### Bài 3 — WAL requirement

Một base backup được copy trong khi ứng dụng vẫn ghi dữ liệu. Vì sao cần WAL để biến bản copy thành trạng thái nhất quán?

### Bài 4 — Copy PGDATA đang chạy

Một DBA dùng `cp -a` copy PGDATA khi PostgreSQL vẫn hoạt động. Liệt kê ít nhất bốn nguyên nhân backup có thể không consistent.

### Bài 5 — pg_basebackup

Viết lệnh tạo plain-format backup từ primary, stream WAL và hiển thị progress. Giải thích các flags.

### Bài 6 — WAL method

So sánh `-X stream`, `-X fetch` và `-X none`. Khi nào fetch có thể thất bại do WAL bị recycle?

### Bài 7 — Replication permissions

Role backup cần quyền nào? `pg_hba.conf` phải cho phép loại connection nào?

### Bài 8 — Backup slot

Giải thích `-C` và `-S` trong `pg_basebackup`. Rủi ro disk nếu consumer không dùng slot trong thời gian dài là gì?

### Bài 9 — Standby configuration

Một backup cần được dùng làm standby. `-R` tạo những file/settings nào trên PostgreSQL 12+?

### Bài 10 — PITR standalone

Vì sao không nên vô tình giữ `standby.signal` khi mục tiêu là restore thành standalone server tới một target?

### Bài 11 — Tablespace mapping

Một source tablespace ở `/fast/pgdata` nhưng destination là `/mnt/nvme/ts1`. Viết ví dụ `-T` và giải thích việc cần làm với mount/permissions.

### Bài 12 — Backup manifest

`backup_manifest` chứa loại thông tin nào? `pg_verifybackup` kiểm tra điều gì?

### Bài 13 — Verification vs restore test

Một backup pass `pg_verifybackup` nhưng không có extension library trên host đích. Vì sao vẫn có thể không start được?

### Bài 14 — Cold backup

Viết thứ tự shutdown sạch, copy PGDATA/tablespaces và khởi động lại. Những metadata nào cần bảo toàn?

### Bài 15 — Backup API

Mô tả vai trò của `pg_backup_start` và `pg_backup_stop`. Vì sao gọi hai functions mà không copy files không tạo thành backup?

### Bài 16 — Storage snapshot

PGDATA, WAL và tablespaces nằm trên ba volumes. Vì sao snapshot ba volume ở ba thời điểm khác nhau có thể không consistent?

### Bài 17 — Incremental backup

PostgreSQL 17 giới thiệu tính năng incremental backup nào? Vai trò của `pg_combinebackup` là gì?

### Bài 18 — Incremental chain

Base backup + incremental 1 + incremental 2. Nếu mất incremental 1, có thể combine incremental 2 với base backup một cách tùy tiện không? Giải thích.

### Bài 19 — archive_command

Viết ví dụ `archive_command` đơn giản và giải thích exit code 0/non-zero. Vì sao command production cần idempotency và atomic publish?

### Bài 20 — WAL continuity

Một WAL segment ở giữa archive bị mất nhưng các segment sau còn. PITR có thể replay qua khoảng trống không?

### Bài 21 — Timeline

Một standby được promote. Timeline mới có ý nghĩa gì và vì sao cần giữ `.history` files?

### Bài 22 — Recovery signals

Phân biệt `recovery.signal` và `standby.signal`. PostgreSQL trước version 12 dùng cơ chế nào?

### Bài 23 — restore_command

Giải thích `%f` và `%p` trong `restore_command`. Command nên trả exit code nào khi WAL file không tồn tại?

### Bài 24 — Recovery target time

Viết cấu hình PITR tới timestamp có timezone và đặt `recovery_target_action='pause'`. Vì sao timezone quan trọng?

### Bài 25 — Restore point

Viết SQL tạo restore point tên `before_release`. Nêu điều kiện WAL cần thiết để recovery tới restore point.

### Bài 26 — Promote

Viết lệnh SQL promote một standby và giải thích vì sao primary cũ phải được fencing trước.

### Bài 27 — Split brain

Hai nodes cùng nhận writes sau failover. Vì sao physical WAL branches không thể tự merge? Thiết kế một cơ chế fencing.

### Bài 28 — pg_rewind

Nêu các prerequisites chính của `pg_rewind`. Vì sao bật `wal_log_hints` sau divergence không bù được WAL cũ?

### Bài 29 — Rebuild standby

Khi nào nên dùng lại `pg_basebackup` thay vì `pg_rewind`? Nêu các trường hợp thiếu WAL hoặc không tương thích.

### Bài 30 — Major version mismatch

Một base backup PostgreSQL 16 được start bằng PostgreSQL 17. Vì sao đây không phải major upgrade hợp lệ?

### Bài 31 — Minor version

Giải thích vì sao minor releases trong cùng major giữ data format nhưng vẫn nên đồng bộ primary/standby minor version theo hỗ trợ của version.

### Bài 32 — PG_VERSION

Đọc file `PG_VERSION` trong backup. Nó cho biết điều gì và không cho biết điều gì?

### Bài 33 — System identifier

Dùng `pg_controldata` tìm Database system identifier. Vì sao không được sửa identifier để ép standby join primary?

### Bài 34 — Block size

Một cluster được tạo với BLCKSZ 8 KB, binary đích dùng build block size khác. Vì sao physical restore không tương thích?

### Bài 35 — WAL segment size

Nêu cách kiểm tra Bytes per WAL segment. Vì sao không nên ghép WAL từ cluster khác chỉ vì segment filename giống nhau?

### Bài 36 — Architecture

Một nhóm muốn copy physical PGDATA từ x86_64 Linux sang ARM64 Linux. Nêu các rủi ro và phương án migration an toàn.

### Bài 37 — Cross OS

Vì sao physical backup không phải format portable giữa Linux và Windows? Khi nào logical dump/restore phù hợp hơn?

### Bài 38 — Tablespaces

Một tablespace nằm ngoài PGDATA bị thiếu khi restore. Server có thể gặp lỗi gì? Viết query liệt kê tablespace names và locations.

### Bài 39 — Config ngoài PGDATA

Nêu ít nhất năm external files/settings cần kiểm kê trước restore và giải thích vì sao physical backup không luôn chứa chúng.

### Bài 40 — Extension binaries

Catalog có extension nhưng shared library không có trên host đích. Điều gì có thể xảy ra khi server start hoặc gọi function?

### Bài 41 — shared_preload_libraries

Một extension trong `shared_preload_libraries` chưa được cài. Vì sao PostgreSQL có thể không start? Xử lý ra sao?

### Bài 42 — Collation mismatch

Restore cluster sang OS có ICU/libc version khác. Vì sao B-tree indexes trên text có thể cần REINDEX? Vì sao REFRESH COLLATION VERSION không tự rebuild indexes?

### Bài 43 — Encoding

Có thể đổi database encoding bằng physical restore sang binary mới không? Nêu phương án migration.

### Bài 44 — Checksum state

Một backup có data checksums on, host đích có binary phù hợp nhưng kiểm tra offline báo lỗi. Nêu các bước điều tra và vì sao không disable checksums để che lỗi.

### Bài 45 — pg_verifybackup

Backup manifest pass nhưng restore test fail do thiếu tablespace. Vì sao verification không đủ chứng minh DR readiness?

### Bài 46 — pg_amcheck

Phân biệt `pg_amcheck` với `pg_checksums`. Mỗi tool kiểm tra lớp nào?

### Bài 47 — RPO/RTO

Một cluster 5 TB có base backup mỗi tuần và WAL archive liên tục. Những yếu tố nào quyết định RPO và RTO?

### Bài 48 — WAL archive gap

Một archive có đầy đủ mọi segment trừ một segment giữa chuỗi. Thiết kế quy trình phát hiện gap trước khi incident xảy ra.

### Bài 49 — Restore test

Thiết kế một restore drill hàng tháng gồm backup verification, restore, WAL replay, application validation, đo thời gian và báo cáo RPO/RTO.

### Bài 50 — Capstone: DR plan cho hệ thống production

Một hệ thống PostgreSQL 4 TB có primary/standby, ba tablespaces trên volumes riêng, PostGIS và extension nội bộ, WAL archive ở object storage, collation ICU, backup incremental hàng ngày và full backup hàng tuần. Một ngày primary volume hỏng, standby bị lag 15 phút và DR site dùng OS minor release mới hơn.

**Yêu cầu:**

1. Chọn node/backup source và xác định RPO có thể đạt.
2. Kiểm tra base/incremental backup chain và dùng `pg_combinebackup` đúng cách.
3. Xác minh major/minor version, architecture, block size, WAL segment size và checksum state.
4. Lập kế hoạch restore cả ba tablespaces và các external config/keys.
5. Cài PostGIS/extension libraries đúng version/architecture.
6. Kiểm tra ICU collation version và lập kế hoạch REINDEX.
7. Khôi phục WAL archive đúng timeline, xác minh history files và replay tới target.
8. Xác định khi nào có thể promote standby, khi nào cần restore backup.
9. Lập kế hoạch fencing primary cũ và tránh split brain.
10. Kiểm tra data integrity bằng manifest, `pg_checksums`, `pg_amcheck` và business queries.
11. Xác minh archive/replication/monitoring sau cutover.
12. Đo RTO thực tế, cập nhật runbook và đề xuất cải thiện backup cadence/storage.

**Tiêu chí đạt:** chứng minh được physical backup, WAL chain, binary/platform, tablespaces và external dependencies cùng tương thích; chọn recovery path có thể kiểm chứng và không làm mất dữ liệu ngoài RPO đã thống nhất.

## 30. Câu hỏi thường gặp

### 30.1. Physical backup có backup một database riêng được không?

Thông thường không. Physical backup là ở mức cluster. Nếu chỉ cần một database hoặc table, dùng logical backup/restore.

### 30.2. Có thể copy PGDATA khi server đang chạy không?

Không thể copy tùy tiện. Dùng `pg_basebackup`, backup API + consistent snapshot/WAL hoặc shutdown sạch trước khi cold copy.

### 30.3. Vì sao base backup cần WAL?

Các data files được copy trong một khoảng thời gian và có thể phản ánh nhiều trạng thái. WAL giúp recovery đưa chúng về một trạng thái nhất quán.

### 30.4. pg_basebackup có copy WAL không?

Có thể, tùy WAL method. `-X stream` stream WAL trong lúc backup; `-X fetch` lấy ở cuối; `-X none` yêu cầu một quy trình WAL bên ngoài bảo đảm consistency.

### 30.5. pg_basebackup có tạo standby không?

Có thể dùng `-R` để tạo `standby.signal` và recovery settings. Nếu muốn standalone PITR, chọn recovery mode phù hợp và không để standby signal ngoài ý muốn.

### 30.6. pg_verifybackup có thay restore test không?

Không. Nó kiểm tra backup files/manifest/WAL theo khả năng version, nhưng không chứng minh extension, config, tablespace paths và application sẽ hoạt động sau restore.

### 30.7. Physical backup có thể restore sang major version mới không?

Không bằng cách start trực tiếp với binary major mới. Dùng `pg_upgrade`, logical dump/restore hoặc logical replication migration.

### 30.8. Có thể restore backup minor cũ bằng minor mới không?

Minor releases trong cùng major được thiết kế giữ data format compatibility, nhưng hãy theo release notes và dùng quy trình cập nhật chính thức. Với physical replication, đồng bộ primary/standby minor versions là lựa chọn an toàn theo hỗ trợ version.

### 30.9. Có thể chuyển physical backup giữa Linux và Windows không?

Không coi physical files là portable cross-OS. Dùng logical migration hoặc phương thức được hỗ trợ cho platform đích.

### 30.10. Physical backup có chứa extension binaries không?

Không. Catalog objects có thể được giữ, nhưng shared libraries/packages và system dependencies phải được cài trên host đích.

### 30.11. Tablespaces có nằm trong PGDATA không?

Metadata/link nằm dưới PGDATA, nhưng dữ liệu thực tế thường nằm ở path riêng. Phải backup/restore cả tablespace targets.

### 30.12. WAL archive có thay replication slot không?

Không. Archive là kho WAL cho recovery/PITR; slot giữ WAL trên primary cho một consumer. Hai cơ chế phục vụ mục đích khác nhau.

### 30.13. PITR có thể phục hồi một table không?

PITR physical phục hồi cả cluster tới một target. Nếu chỉ muốn lấy lại một table, restore sang cluster tạm rồi export/import logical table.

### 30.14. Vì sao cần timeline history files?

Chúng mô tả các nhánh WAL sau promotion/failover. Thiếu history có thể khiến recovery không chọn được timeline đúng.

### 30.15. Khi nào dùng pg_rewind?

Khi một node cũ đã diverge sau failover và đủ prerequisites để đồng bộ lại theo timeline mới. Nếu không đủ WAL/checksum/hint prerequisites, tạo standby mới bằng base backup.

### 30.16. Có thể start hai copies từ cùng base backup cùng lúc không?

Có thể chạy các clones tách biệt cho test, nhưng không để cả hai cùng được coi là primary trong cùng hệ thống ghi. Phải cô lập network/identity để tránh split brain.

### 30.17. Checksum state có thể bật riêng một database không?

Không. Data checksums là thiết lập toàn cluster.

### 30.18. Nếu collation version khác thì database không start được?

Không nhất thiết. Server có thể start nhưng indexes phụ thuộc collation có thể cần REINDEX để khớp thứ tự mới. Xử lý warning trước khi mở traffic.

### 30.19. pg_checksums có chạy trên server đang hoạt động không?

Không. Công cụ yêu cầu cluster shutdown sạch.

### 30.20. pg_resetwal có phải công cụ restore?

Không. Đây là công cụ cứu hộ đặc biệt khi WAL/control state bị hỏng. Nó có thể làm mất consistency và không thay thế backup/WAL recovery.

### 30.21. Backup manifest pass có nghĩa không có page corruption?

Không. Manifest xác minh backup files theo checksums của manifest. Data page checksums là lớp khác; cần offline check và restore test.

### 30.22. Restore xong có cần REINDEX không?

Không mặc định. Chỉ REINDEX khi có collation version mismatch, index corruption được xác nhận hoặc một lý do kỹ thuật/hiệu năng cụ thể.

### 30.23. Có thể đổi tablespace path sau restore không?

Có thể map lúc backup/restore hoặc dùng quy trình DDL/storage migration được hỗ trợ. Phải đảm bảo link, ownership và data files đúng path trước khi start.

### 30.24. Standby lag 15 phút có nghĩa mất 15 phút dữ liệu?

Không thể kết luận chỉ từ thời gian lag. Kiểm tra received/replay LSN, WAL generation và synchronous/asynchronous replication policy để xác định RPO thực tế.

### 30.25. Sau PITR có cần backup mới không?

Có. Sau promotion/PITR, cluster tạo timeline mới. Tạo base backup mới và bắt đầu archive WAL theo timeline mới để có recovery chain rõ ràng.

### 30.26. Có thể xóa WAL archive cũ sau khi restore?

Chỉ khi retention/catalog xác nhận không còn backup/PITR target/standby nào cần chúng. Giữ cả timeline history và WAL liên quan tới backup còn được retention.

### 30.27. Vì sao restore có thể chậm dù backup local?

Do storage throughput, nhiều tablespaces, WAL replay volume, incremental combine, extension startup, checksum/validation scan, cold cache hoặc filesystem layout.

### 30.28. Restore test nên chạy bao lâu một lần?

Tần suất dựa trên RPO/RTO và criticality. Điều quan trọng là chạy đủ thường xuyên để chứng minh backup chain, keys, dependencies và runbook vẫn hoạt động sau thay đổi hệ thống.

### 30.29. Logical dump có thể thay physical backup hoàn toàn không?

Không nhất thiết. Logical dump hữu ích cho migration/selective restore nhưng có thể tốn thời gian và không cung cấp cùng khả năng PITR toàn cluster. Hệ thống quan trọng thường cần cả physical và logical backups.

### 30.30. Điều gì quyết định physical recovery thành công?

Base backup nhất quán, WAL/timeline đầy đủ, binary/platform tương thích, tablespaces/config/dependencies đầy đủ, permissions đúng và validation sau restore.

## 31. Tài liệu PostgreSQL chính thức

Các liên kết dưới đây trỏ tới tài liệu hiện hành. Luôn chọn đúng major version của source/target vì options, recovery settings và backup features thay đổi theo version:

- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backup, WAL archive và PITR.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): tạo physical base backup, WAL methods, standby và tablespace mapping.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): kiểm tra backup manifest và files.
- [pg_combinebackup](https://www.postgresql.org/docs/current/app-pgcombinebackup.html): kết hợp incremental backups.
- [Backup Manifest Format](https://www.postgresql.org/docs/current/backup-manifest-format.html): metadata và checksums của backup.
- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication và standby operation.
- [Recovery Configuration](https://www.postgresql.org/docs/current/recovery-config.html): restore command, recovery signals, target time/LSN/timeline và recovery actions.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): đồng bộ node đã diverge sau failover.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html): kiểm tra control information và cluster metadata.
- [pg_checksums](https://www.postgresql.org/docs/current/app-pgchecksums.html): verify/enable/disable data page checksums offline.
- [pg_amcheck](https://www.postgresql.org/docs/current/app-pgamcheck.html): kiểm tra heap/index structures.
- [pg_waldump](https://www.postgresql.org/docs/current/pgwaldump.html): đọc và phân tích WAL records.
- [pg_archivecleanup](https://www.postgresql.org/docs/current/pgarchivecleanup.html): dọn WAL archive theo recovery requirements.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html): nâng cấp major version bằng phương thức được hỗ trợ.
- [CREATE TABLESPACE](https://www.postgresql.org/docs/current/sql-createtablespace.html): quản lý tablespace paths.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html): locale providers và collation version.
- [ALTER COLLATION](https://www.postgresql.org/docs/current/sql-altercollation.html): refresh collation version metadata.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): archive, replication và database statistics.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): WAL/archiving configuration.

## 32. Tổng kết

Khôi phục vật lý PostgreSQL là một quy trình gồm **base backup + WAL + tương thích binary/platform + external dependencies + validation**. Một bản copy file đơn lẻ không đủ; recovery cần đúng WAL chain, timeline và môi trường tương thích.

| Thành phần | Vai trò trong recovery |
| --- | --- |
| Base backup | Cung cấp nền data files nhất quán |
| WAL archive | Replay thay đổi sau base backup tới recovery target |
| Timeline history | Xác định nhánh WAL sau promotion/failover |
| PostgreSQL binary/build | Đọc đúng data/catalog/WAL formats |
| Tablespaces | Cung cấp relation files nằm ngoài PGDATA |
| Config/extensions/keys | Cho phép server start và hoạt động trên host đích |
| Collation/locale | Bảo đảm indexes và text ordering phù hợp |
| Verification/restore test | Chứng minh backup chain có thể phục hồi |

Trước khi restore, xác minh major version, platform, block/WAL parameters, system identifier, tablespaces, extensions, collation và WAL continuity. Sau restore, kiểm tra recovery state, business data, application connectivity, archive/replication và hiệu năng.

**Backup chỉ đáng tin khi có thể restore được.** Hãy thực hiện restore/PITR drills định kỳ, đo RPO/RTO, giữ WAL/timeline history đúng retention và cập nhật runbook mỗi khi thay đổi version, OS, extension, storage hoặc topology.

