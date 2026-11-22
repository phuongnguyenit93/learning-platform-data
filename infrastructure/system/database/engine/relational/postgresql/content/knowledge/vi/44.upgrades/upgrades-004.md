# Nâng cấp PostgreSQL bằng dump và restore

## 1. Tổng quan phương pháp

Nâng cấp PostgreSQL bằng dump và restore là phương pháp chuyển dữ liệu logic từ cluster nguồn sang cluster đích. Thay vì sao chép trực tiếp các data files, công cụ đọc schema và dữ liệu qua SQL/logical representation, ghi chúng vào một archive hoặc script, sau đó tạo lại objects và rows trên server mới.

Quy trình điển hình:

1. Kiểm kê cluster nguồn, database, roles, extensions và tablespaces.
2. Cài PostgreSQL phiên bản đích và các extension packages tương thích.
3. Tạo backup bằng pg_dump hoặc pg_dumpall.
4. Tạo roles, tablespaces và database trên cluster đích.
5. Restore schema/data bằng pg_restore hoặc psql.
6. Phân tích, kiểm tra dữ liệu, sequence, permissions và ứng dụng.
7. Chuyển ứng dụng sang cluster mới theo cutover plan.
8. Giữ cluster cũ và backup theo rollback/retention policy.

Phương pháp này thường phù hợp khi cần chuyển major version, đổi operating system/architecture, đổi storage layout hoặc muốn tái tạo database sạch. Nó cũng hữu ích khi cần chuyển một database cụ thể thay vì toàn bộ cluster.

Dump/restore thường cần downtime đáng kể đối với database lớn vì dữ liệu phải được export và import. Nếu yêu cầu downtime rất thấp, có thể cần kết hợp logical replication hoặc một phương pháp migration khác để đồng bộ các changes trong khi dump/restore baseline.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt pg_dump, pg_dumpall, pg_restore và psql.
2. Chọn plain, custom, directory hoặc tar archive phù hợp.
3. Lập kế hoạch dump/restore giữa các PostgreSQL major versions.
4. Sao lưu và khôi phục roles, tablespaces và global objects.
5. Xử lý extensions, large objects, sequences, ownership và privileges.
6. Chọn restore tuần tự hay song song.
7. Hiểu consistency snapshot và giới hạn khi database tiếp tục nhận writes.
8. Lập cutover window, validation và rollback.
9. Bảo vệ dump files và credentials.
10. Thực hành migration trong môi trường lab.

### 1.2. Khi nào dùng dump/restore?

Phù hợp khi:
- Nâng major version và muốn tạo cluster mới.
- Chuyển giữa operating systems hoặc CPU architectures.
- Chuyển database sang storage/host mới.
- Muốn đổi encoding, locale hoặc collation trong một migration được kiểm soát.
- Cần di chuyển một tập database/schema/table cụ thể.
- Có thể chấp nhận thời gian dump, restore và validation.

Cần cân nhắc phương án khác khi:
- Database rất lớn và downtime phải cực thấp.
- Có workload ghi liên tục, không thể freeze writes đủ lâu.
- Có nhiều large objects hoặc object phụ thuộc ngoài database cần quy trình riêng.
- Có các custom types/extensions khó tương thích.
- Yêu cầu chuyển toàn cluster với thời gian ngắn và pg_upgrade phù hợp hơn.

### 1.3. Dump/restore là logical migration

Dump chứa các lệnh tạo object và dữ liệu ở dạng logic. Nó không phải bản sao byte-for-byte của data directory, cũng không phải WAL archive.

Ưu điểm:
- Không phụ thuộc trực tiếp vào layout data files của phiên bản nguồn.
- Có thể restore vào PostgreSQL major version mới hơn theo compatibility rules.
- Có thể chọn database/schema/table/object để di chuyển.
- Có thể thay đổi một số thuộc tính khi restore như owner hoặc ACL.
- Có thể chạy restore song song với archive formats phù hợp.

Giới hạn:
- Export/import có thể chậm hơn sao chép physical.
- Không tự đồng bộ changes phát sinh sau snapshot.
- Không tự sao chép mọi external resources, secrets, operating-system files hoặc cluster configuration.
- Cần xử lý global objects và các phụ thuộc bên ngoài database.
- Restore phải tương thích với SQL/features/extensions ở server đích.

---

## 2. Công cụ và vai trò

### 2.1. pg_dump

`pg_dump` tạo dump của một database. Nó có thể xuất:
- Plain SQL script.
- Custom archive.
- Directory archive.
- Tar archive.

Một database dump chứa database objects và data được pg_dump hỗ trợ. Nó không thay thế việc sao lưu roles/tablespaces/global objects của cả cluster.

Ví dụ plain SQL:

~~~bash
pg_dump -h source-db -U backup_user -d appdb -F p > appdb.sql
~~~

Ví dụ custom archive:

~~~bash
pg_dump -h source-db -U backup_user -d appdb -F c -f appdb.dump
~~~

### 2.2. pg_dumpall

`pg_dumpall` dump tất cả databases trong cluster và các global objects như roles và tablespaces. Kết quả là plain SQL script, thường được thực thi bằng psql.

Ví dụ dump globals riêng:

~~~bash
pg_dumpall -h source-db -U postgres --globals-only > globals.sql
~~~

Ví dụ dump toàn cluster:

~~~bash
pg_dumpall -h source-db -U postgres > cluster.sql
~~~

Với database lớn cần parallel dump/restore, thường tiện hơn khi dùng pg_dump riêng từng database ở custom/directory format và dùng pg_dumpall --globals-only cho globals.

### 2.3. pg_restore

`pg_restore` đọc archive do pg_dump tạo ở custom, directory hoặc tar format. Nó cho phép:
- Chọn schema/data/table/object để restore.
- Liệt kê nội dung archive.
- Restore theo thứ tự dependency.
- Chạy nhiều jobs song song với custom/directory archives.
- Bỏ qua owner hoặc ACL.
- Clean objects cũ trước khi restore nếu được yêu cầu.

Ví dụ:

~~~bash
pg_restore -h target-db -U restore_user -d appdb_new appdb.dump
~~~

### 2.4. psql

`psql` thực thi plain SQL dump:

~~~bash
psql -X -h target-db -U restore_user -d appdb_new \
  -v ON_ERROR_STOP=1 -f appdb.sql
~~~

`-X` ngăn psql đọc startup files cá nhân, giúp restore lặp lại ổn định hơn. `ON_ERROR_STOP=1` khiến psql dừng khi gặp lỗi SQL thay vì tiếp tục như không có gì xảy ra.

Plain SQL restore không dùng được cơ chế parallel restore của pg_restore.

### 2.5. Công cụ liên quan

- `createdb`: tạo database đích.
- `dropdb`: xóa database, cần cẩn trọng vì destructive.
- `vacuumdb`: chạy VACUUM/ANALYZE trên database.
- `pg_isready`: kiểm tra server nhận kết nối.
- `pg_restore --list`: xem TOC (table of contents) trong archive.
- `pg_verifybackup`: xác minh physical backup manifest; không dùng để xác minh pg_dump archive.
- `pg_dump --version` / `pg_restore --version`: kiểm tra client tool versions.

---

## 3. Chọn dump format

### 3.1. Plain SQL format

Plain format là script SQL có thể đọc được, khôi phục bằng psql.

~~~bash
pg_dump -F p -f appdb.sql appdb
~~~

Ưu điểm:
- Dễ đọc và kiểm tra.
- Có thể sửa script nếu hiểu rõ hậu quả.
- Dễ đưa vào quy trình chỉ dùng SQL client.
- Không cần pg_restore.

Nhược điểm:
- Không hỗ trợ parallel restore.
- Không thể chọn objects linh hoạt như custom archive.
- File có thể lớn và cần đủ dung lượng.
- Sửa script thủ công có thể làm sai dependency hoặc dữ liệu.

Dùng khi database nhỏ, cần script dễ đọc hoặc hệ thống restore đơn giản.

### 3.2. Custom format

Custom format dùng `-F c` hoặc `--format=custom`:

~~~bash
pg_dump -Fc -f appdb.dump appdb
~~~

Ưu điểm:
- Nén archive.
- Có thể liệt kê objects.
- Chọn schema/data/table khi restore.
- Hỗ trợ parallel restore bằng pg_restore -j.
- Phù hợp backup database đơn lẻ.

Nhược điểm:
- Không đọc trực tiếp như SQL script.
- Phải dùng pg_restore.
- Không hỗ trợ parallel dump bằng pg_dump; parallel dump cần directory format.

Đây thường là lựa chọn linh hoạt cho database đơn lẻ.

### 3.3. Directory format

Directory format tạo một thư mục archive gồm nhiều file:

~~~bash
pg_dump -Fd -j 4 -f appdb_dir appdb
~~~

Ưu điểm:
- Hỗ trợ parallel dump bằng pg_dump -j.
- Hỗ trợ parallel restore bằng pg_restore -j.
- Mỗi table/data object có thể được lưu thành file riêng.
- Phù hợp database lớn và migration cần throughput cao.

Nhược điểm:
- Phải bảo toàn toàn bộ thư mục, không chỉ một file.
- Copy/upload phải giữ đủ file và permissions.
- Quản lý artifact nhiều file phức tạp hơn custom archive đơn.

### 3.4. Tar format

Tar format dùng `-F t`:

~~~bash
pg_dump -Ft -f appdb.tar appdb
~~~

Nó là archive dạng tar, có thể dùng pg_restore và chọn objects, nhưng không hỗ trợ parallel restore như custom/directory. Cần kiểm tra compatibility và giới hạn format trong tài liệu release.

### 3.5. So sánh

| Format | Output | Parallel dump | Parallel restore | Dùng công cụ nào để restore |
|---|---|---:|---:|---|
| Plain | SQL script | Không | Không | psql |
| Custom | Một archive file | Không | Có | pg_restore |
| Directory | Một thư mục nhiều file | Có | Có | pg_restore |
| Tar | Một tar archive | Không | Không | pg_restore |

### 3.6. Chọn format theo mục tiêu

- Cần đọc/chỉnh SQL: plain.
- Cần một file nén và restore chọn lọc: custom.
- Cần dump và restore song song: directory.
- Cần tar-compatible archive: tar.
- Cần dump nhiều databases cùng globals: pg_dumpall, nhưng lưu ý output là SQL script và không có parallel restore như directory archive.

### 3.7. Liệt kê archive trước khi restore

~~~bash
pg_restore --list appdb.dump > appdb.toc
~~~

TOC cho biết objects trong archive và hữu ích để review. Có thể chỉnh TOC rồi truyền qua `--use-list`, nhưng chỉ nên làm khi hiểu dependencies; bỏ nhầm object có thể khiến restore thất bại hoặc thiếu dữ liệu.

---

## 4. Version compatibility và nâng cấp major version

### 4.1. Dùng client tools phù hợp

Để dump từ server nguồn, dùng pg_dump có version phù hợp. pg_dump không thể dump từ server có major version mới hơn major version của chính nó; nó thường hỗ trợ server cùng major version hoặc cũ hơn trong phạm vi được tài liệu hóa.

Để nâng cấp sang major version mới, cách phổ biến là:
- Dùng pg_dump client từ version đích hoặc client đủ mới để đọc server nguồn.
- Dùng pg_restore/psql tương thích với target server.
- Kiểm tra output SQL và extension compatibility.

Không giả định client version cũ có thể đọc server mới hơn.

### 4.2. Dump format không phải version-neutral tuyệt đối

Archive chứa metadata và SQL do pg_dump version tạo ra. Server đích phải hiểu các commands, types, functions và options được phát ra. PostgreSQL thường hỗ trợ dump/restore sang server mới hơn, nhưng không bảo đảm mọi object/extension tùy biến đều tương thích.

Restore từ version mới xuống server cũ không phải đường downgrade được bảo đảm. Nếu buộc phải downgrade, cần migration logic riêng và kiểm tra từng feature.

### 4.3. Major upgrade

Một quy trình upgrade có thể chuyển từ PostgreSQL 14 sang 15, 15 sang 16 hoặc các cặp khác. Các con số chỉ là ví dụ; phải kiểm tra version pair cụ thể.

Khác biệt có thể nằm ở:
- System catalogs.
- SQL syntax và reserved keywords.
- Data type behavior.
- Collation provider/version.
- Extension versions.
- Planner/executor behavior.
- Authentication defaults.
- Replication features.
- Parameter names/defaults.
- Removed/deprecated features.

### 4.4. Client và server version

Kiểm tra:

~~~bash
pg_dump --version
pg_restore --version
psql --version
~~~

Trên source và target:

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
~~~

Không nhầm psql client version với server version. Client và server là các binary/version độc lập.

### 4.5. Extensions

Dump có thể chứa CREATE EXTENSION hoặc extension-owned objects theo cách PostgreSQL quản lý. Nhưng nó không mang theo shared library binaries của extension.

Trên target:
1. Cài package extension tương thích với major version và OS.
2. Kiểm tra extension control/SQL files.
3. Xác định extension version trên source.
4. Cài version phù hợp trên target.
5. Restore và kiểm tra CREATE EXTENSION/extension-owned objects.
6. Chạy ALTER EXTENSION UPDATE nếu migration plan yêu cầu.
7. Test functions, operators, types và indexes dùng extension.

Không copy file .so/.dll từ major version cũ vào thư mục mới nếu package chưa xác nhận tương thích.

### 4.6. Collation và locale

Database đích cần encoding/locale/collation phù hợp với yêu cầu ứng dụng. Khác libc/ICU version có thể làm sort/equality behavior thay đổi và ảnh hưởng indexes. Trước cutover:
- Ghi nhận database encoding và locale.
- Kiểm tra collation provider/version.
- Đọc warnings khi restore.
- Xác định reindex requirements.
- Test unique constraints và ordering logic.

### 4.7. Parameter changes

Không copy toàn bộ postgresql.conf cũ vào server mới. Một số settings đổi tên, đổi default hoặc bị bỏ. Tạo parameter inventory, so sánh target defaults và cấu hình lại có chủ đích. Kiểm tra `pg_settings` và release notes.

### 4.8. SQL/feature compatibility

Một restore có thể thành công nhưng application vẫn lỗi vì:
- Query dùng syntax thay đổi.
- Extension function không còn.
- Reserved keyword mới.
- Planner chọn plan khác.
- Collation/sort results thay đổi.
- Authentication/TLS defaults thay đổi.

Do đó phải chạy application smoke tests và workload regression tests sau restore.

---

## 5. Phạm vi dump: database và cluster globals

### 5.1. pg_dump chỉ dump một database

`pg_dump` hoạt động ở phạm vi một database. Nó có thể dump toàn database hoặc chọn schema/table/object cụ thể. Nó không tự sao lưu mọi roles, tablespaces và global objects của cả cluster.

### 5.2. Global objects

Các objects dùng chung toàn cluster gồm:
- Roles và role memberships.
- Tablespaces.
- Một số quyền/attributes ở cấp cluster.
- Các global settings/metadata không thuộc riêng database.

Dùng:

~~~bash
pg_dumpall --globals-only -f globals.sql
~~~

Sau đó restore globals trước khi restore databases, để owners và tablespaces đã tồn tại.

### 5.3. Roles và passwords

Globals dump có thể chứa role definitions và password verifiers nếu quyền/setting cho phép. File này rất nhạy cảm:
- Giới hạn file permissions.
- Mã hóa khi lưu/truyền.
- Không đưa vào source control.
- Không paste vào ticket/chat.
- Xử lý secret rotation và role ownership.
- Review superuser/CREATEDB/CREATEROLE/REPLICATION privileges.

Nếu không muốn mang nguyên password verifiers sang target, có thể tạo roles theo provisioning policy riêng và dùng `--no-owner`/ACL options phù hợp cho database restore.

### 5.4. Tablespaces

Nếu source dùng tablespaces, dump globals có thể chứa definitions với filesystem paths. Target cần:
- Tạo directories trên host đích.
- Gán owner và permissions phù hợp.
- Đảm bảo mount/storage tồn tại.
- Chọn path mới nếu layout khác.
- Tạo tablespaces trước khi restore database objects sử dụng chúng.

Nếu không muốn giữ tablespace mapping, dùng restore options phù hợp như `--no-tablespaces` hoặc remap theo kế hoạch; kiểm tra option support của pg_restore version.

### 5.5. pg_dumpall toàn cluster

`pg_dumpall` gọi pg_dump cho từng database và xuất globals trong một SQL script. Nó thuận tiện cho cluster nhỏ, nhưng:
- Output plain SQL, không có custom/directory archive.
- Restore thường tuần tự.
- Khó chọn parallel restore.
- Mỗi database dump có snapshot riêng; không phải một snapshot toàn cluster xuyên nhiều databases.
- Cần xem global objects/roles/tablespaces và quyền.

Với cluster lớn, có thể dump globals riêng rồi dump từng database bằng custom/directory format.

### 5.6. Cross-database consistency

PostgreSQL transaction không trải qua nhiều databases. Khi dump nhiều databases riêng, mỗi database có snapshot riêng tại thời điểm dump của nó. Nếu ứng dụng có business invariants xuyên databases, cần dừng writes/quiesce hoặc có cơ chế phối hợp để tạo một cutover boundary nhất quán.

### 5.7. Replication objects

Dump/restore không thay thế việc lập kế hoạch cho replication slots, logical subscriptions, physical replication configuration, WAL archive settings và external replication consumers. Một số publication definitions có thể được dump như database objects; subscription/slot connection state và secrets cần được xử lý riêng theo version và runbook.

### 5.8. Objects ngoài phạm vi

Kiểm kê riêng:
- postgresql.conf, pg_hba.conf, TLS certificates.
- OS users, filesystem paths, service units.
- Cron/jobs/schedulers.
- External tables/data sources, FDW endpoints.
- Secrets và credentials.
- Monitoring/backup agents.
- Replication slots và downstream consumers.
- Application connection strings/DNS/load balancers.

Dump database không phải bản backup toàn bộ hạ tầng.

---

## 6. Consistency, snapshot và downtime

### 6.1. Snapshot của pg_dump

`pg_dump` tạo một snapshot nhất quán của một database tại thời điểm bắt đầu dump. Trong khi dump chạy, các transactions khác có thể tiếp tục commit; dump sẽ nhìn thấy một snapshot theo MVCC thay vì trộn ngẫu nhiên rows từ nhiều thời điểm.

Điều này bảo đảm tính nhất quán nội bộ của database dump, nhưng không có nghĩa dump chứa mọi writes phát sinh sau khi snapshot được tạo.

### 6.2. Writes trong lúc dump

Giả sử dump bắt đầu lúc 10:00 và hoàn thành lúc 11:30. Một row được commit lúc 10:45 sau snapshot có thể không xuất hiện trong dump. Nếu ứng dụng tiếp tục ghi và DBA chỉ restore archive này, row đó sẽ thiếu ở target.

Vì vậy có hai cách triển khai chính:

- **Offline migration:** dừng writes trước dump, giữ write freeze cho đến khi restore/validation/cutover xong.
- **Online/low-downtime migration:** tạo baseline bằng dump rồi đồng bộ các changes phát sinh sau snapshot bằng logical replication hoặc một cơ chế delta được thiết kế và kiểm chứng.

Không được mở target làm primary nếu còn writes sau snapshot chưa được chuyển.

### 6.3. Cutover boundary

Với offline migration:
1. Thông báo maintenance window.
2. Chặn application writes và background jobs.
3. Chờ transactions đang mở kết thúc.
4. Tạo dump cuối cùng.
5. Restore và validate.
6. Đồng bộ sequences và các external state.
7. Chuyển connection routing.
8. Mở writes trên target.

Nếu dump/restore quá lâu, downtime cũng kéo dài tương ứng. Đo rehearsal trên dữ liệu gần production để ước lượng chính xác.

### 6.4. Consistency giữa nhiều databases

Mỗi pg_dump có snapshot riêng cho database của nó. pg_dumpall không tạo một global transaction snapshot xuyên tất cả databases. Nếu application lưu quan hệ logic giữa nhiều databases, phải dừng writes trên toàn hệ thống hoặc dùng một coordination marker/quiesce protocol.

### 6.5. Sequence values

Dump database thường chứa sequence definitions và sequence state được xuất bằng lệnh setval trong archive/script. Khi restore đúng, sequence state sẽ được khôi phục theo dump.

Tuy nhiên:
- Sequence operations không có MVCC semantics giống table rows.
- Writes tiếp tục sau snapshot có thể tạo sequence values không có row tương ứng trong dump.
- Nếu ứng dụng dùng sequences bên ngoài database dump hoặc nhiều tables dùng chung sequence, cần inventory riêng.
- Trước khi mở writes trên target, xác nhận next values không xung đột với keys đã restore.

### 6.6. Large objects

pg_dump hỗ trợ large objects và thường đưa chúng vào dump trừ khi bị loại trừ bằng option. Nếu dùng table/schema-specific dump hoặc data-only selection, kiểm tra rõ large objects có được bao gồm và reference OIDs có được giữ nguyên.

Có thể dùng `--blobs` để yêu cầu đưa large objects vào dump và `--no-large-objects` để loại trừ. Xác minh option theo pg_dump version và kiểm thử ứng dụng đọc LO trên target.

### 6.7. Consistency với external systems

Dump không đóng băng:
- Message queues.
- Object storage.
- Search indexes.
- Payment providers.
- Caches.
- External APIs.
- Filesystem uploads.

Nếu database rows tham chiếu các hệ thống này, cutover plan cần đồng bộ event offsets, object paths, consumer checkpoints và application state tương ứng.

---

## 7. Preflight inventory trước khi dump

### 7.1. Xác nhận versions

Trên source và target, ghi lại:
- PostgreSQL major/minor version.
- pg_dump/pg_restore/psql client versions.
- OS/architecture.
- Database encoding.
- Locale và collation provider/version.
- Installed extensions và versions.

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
SHOW server_encoding;
SHOW lc_collate;
SHOW lc_ctype;
~~~

Một số collation details cần xem qua catalogs và OS/provider metadata.

### 7.2. Kiểm kê databases

~~~sql
SELECT
    datname,
    pg_get_userbyid(datdba) AS owner,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype,
    datallowconn,
    datistemplate
FROM pg_database
ORDER BY datname;
~~~

Xác định databases cần migrate và databases hệ thống không được dump/restore như database ứng dụng.

### 7.3. Kiểm kê roles

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
ORDER BY rolname;
~~~

Không xuất password hashes vào tài liệu công khai. Kiểm tra role memberships, default privileges và grants trong database.

### 7.4. Kiểm kê extensions

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Kiểm tra extension packages trên target trước khi restore. Với extensions có native libraries, cài package phù hợp với target PostgreSQL major version.

### 7.5. Kiểm kê tablespaces

~~~sql
SELECT
    spcname,
    pg_get_userbyid(spcowner) AS owner,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
~~~

Ghi lại paths, owners và filesystem dependencies. Default tablespaces có location rỗng; không cố tạo lại pg_default/pg_global như user-defined tablespaces.

### 7.6. Kiểm kê dung lượng

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
~~~

Ước lượng:
- Dump archive size.
- Target database size sau restore.
- Temporary files.
- Index build overhead.
- WAL/archive growth.
- Disk headroom trong lúc source và target cùng tồn tại.

Archive compression có thể giảm dung lượng backup nhưng restore vẫn cần đủ disk cho database objects.

### 7.7. Kiểm kê objects đặc biệt

Tìm:
- Large objects.
- Partitioned tables.
- Foreign tables/FDW servers.
- Publications/subscriptions.
- Event triggers.
- Custom types/domains/enums.
- Extensions.
- Materialized views.
- Security labels.
- Row-level security policies.
- Unlogged tables.
- Scheduled jobs và application-owned metadata.

Đánh dấu object nào dump/restore xử lý được và object nào cần migration riêng.

### 7.8. Kiểm tra active transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Long-running transactions có thể ảnh hưởng snapshot horizon và gây khó khăn cho cutover. Xác định owner và workload trước khi bắt đầu maintenance window.

### 7.9. Preflight checklist

- [ ] Version pair và client tools đã xác nhận.
- [ ] Extensions có package tương thích trên target.
- [ ] Roles/tablespaces đã inventory.
- [ ] Encoding/locale/collation đã quyết định.
- [ ] Dung lượng source, archive, target và temp đã dự trù.
- [ ] Large objects và external dependencies có kế hoạch.
- [ ] Application write freeze hoặc delta sync strategy đã chọn.
- [ ] Backup encryption, retention và access controls sẵn sàng.
- [ ] Restore rehearsal đã chạy.
- [ ] Validation queries và rollback owner đã xác định.

---

## 8. Tạo dump bằng pg_dump

### 8.1. Dump custom format

~~~bash
pg_dump \
  -h source-db.example.net \
  -p 5432 \
  -U backup_user \
  -d appdb \
  --format=custom \
  --file=/backup/appdb.dump
~~~

Custom format phù hợp khi muốn một archive file, restore chọn lọc và parallel restore.

### 8.2. Dump directory format song song

~~~bash
pg_dump \
  -h source-db.example.net \
  -p 5432 \
  -U backup_user \
  -d appdb \
  --format=directory \
  --jobs=4 \
  --file=/backup/appdb_dir
~~~

Parallel dump chỉ được hỗ trợ với directory format. Chọn số jobs theo source CPU, I/O, network và connection capacity. Parallel dump dùng snapshot coordination; không có nghĩa database source bị khóa toàn bộ trong suốt quá trình.

### 8.3. Dump plain SQL

~~~bash
pg_dump \
  -h source-db.example.net \
  -U backup_user \
  -d appdb \
  --format=plain \
  --file=/backup/appdb.sql
~~~

Có thể nén bằng công cụ ngoài sau khi dump, nhưng restore sẽ cần giải nén/pipe phù hợp. Nếu cần chọn objects hoặc parallel restore, custom/directory thuận tiện hơn.

### 8.4. Dump một schema

~~~bash
pg_dump \
  -h source-db \
  -U backup_user \
  -d appdb \
  --schema=app \
  --format=custom \
  --file=app_schema.dump
~~~

Schema-only dump hữu ích để chuẩn bị target trước hoặc review DDL:

~~~bash
pg_dump --schema-only -Fc -d appdb -f schema.dump
~~~

### 8.5. Dump data-only

~~~bash
pg_dump --data-only -Fc -d appdb -f data.dump
~~~

Data-only dump không tạo đầy đủ schema definitions. Target phải có tables, types, sequences và constraints cần thiết; nếu không, restore có thể fail.

### 8.6. Chọn table

~~~bash
pg_dump -Fc -d appdb \
  --table=app.customers \
  --table=app.orders \
  -f selected_tables.dump
~~~

Chọn table có thể bỏ sót dependencies như types, functions hoặc referenced tables. Review archive TOC và chuẩn bị target schema đầy đủ.

### 8.7. Exclude objects

Có thể loại trừ table/schema hoặc data theo nhu cầu. Cẩn thận với:
- Exclude table data nhưng giữ table definition.
- Exclude schema có object được schema khác tham chiếu.
- Exclude large objects.
- Exclude extension-owned objects.
- Exclude sequences được tables sử dụng.

Dump chọn lọc là một migration plan, không đơn thuần là lọc file.

### 8.8. Blobs/large objects

Nếu ứng dụng dùng large objects, xác nhận archive có chúng. Ví dụ:

~~~bash
pg_dump -Fc --blobs -d appdb -f appdb_with_blobs.dump
~~~

Không dùng `--no-large-objects` nếu target cần các LO. Với table-specific/schema-specific dumps, kiểm tra rõ hành vi và test reference integrity.

### 8.9. Ghi log và exit code

Trong automation:
- Lưu stdout/stderr và exit code.
- Dùng shell strict error handling phù hợp môi trường.
- Không coi file archive tồn tại là dump thành công.
- Kiểm tra kích thước, checksum và `pg_restore --list`.
- Chỉ đánh dấu backup complete sau khi command exit 0 và artifact được xác minh.

### 8.10. Dump globals

~~~bash
pg_dumpall \
  -h source-db.example.net \
  -U cluster_backup \
  --globals-only \
  --file=/backup/globals.sql
~~~

Lưu file globals cùng backup database, mã hóa và bảo vệ quyền truy cập. Kiểm tra role/tablespace definitions trước khi restore vào target.

### 8.11. Password và authentication

Không truyền password trực tiếp trên command line vì có thể lộ trong process list/history. Dùng:
- .pgpass với file permissions phù hợp trên Unix.
- PGPASSFILE được quản lý an toàn.
- Secret manager/injected environment theo platform.
- TLS và certificate verification.

Không lưu connection string chứa password trong shell history hoặc dump manifest công khai.

### 8.12. Compression

Custom/directory formats có thể nén archive; compression level và thuật toán hỗ trợ phụ thuộc pg_dump version. Compression cao giảm network/storage nhưng tăng CPU và có thể làm dump/restore chậm hơn. Benchmark theo CPU, I/O và archive size thực tế.

---

## 9. Tạo database đích và chuẩn bị globals

### 9.1. Tạo target cluster

Cài PostgreSQL major version đích trên host/managed service. Trước restore:
- Xác nhận server start và nhận kết nối.
- Cấu hình authentication, TLS và pg_hba.
- Cài extension packages.
- Tạo filesystem directories/tablespace paths.
- Cấu hình disk, WAL, backup và monitoring.
- Xác nhận target có đủ RAM/CPU/I/O cho restore.

Không restore lên cluster production đang chứa dữ liệu mà chưa có kế hoạch clean/reconcile.

### 9.2. Restore global objects trước

Globals dump thường cần superuser hoặc quyền đủ cao để tạo roles/tablespaces:

~~~bash
psql -X \
  -h target-db \
  -U postgres \
  -d postgres \
  -v ON_ERROR_STOP=1 \
  -f /backup/globals.sql
~~~

Nếu không muốn mang nguyên roles/passwords từ source, tạo roles theo policy mới rồi điều chỉnh restore options. Kiểm tra globals script trước khi thực thi.

### 9.3. Tablespace directories

Tạo filesystem paths trước khi restore globals nếu script có CREATE TABLESPACE. Directory phải tồn tại trên target host và có owner/permissions phù hợp với PostgreSQL server process.

Không tạo tablespace path trên một mount chưa sẵn sàng; nếu restore thành công nhưng mount sau đó biến mất, database có thể không truy cập được objects trong tablespace.

### 9.4. Xử lý role conflicts

Nếu role đã tồn tại ở target:
- So sánh attributes/memberships.
- Quyết định giữ target role hay dùng source definition.
- Tránh vô tình hạ quyền hoặc cấp superuser.
- Xử lý ownership/default privileges.
- Chỉ sửa globals script khi hiểu toàn bộ references.

pg_dumpall --globals-only có thể tạo role definitions trùng tên. Không chạy mù trên cluster đích đã được provision.

### 9.5. Tạo database từ template0

Nếu cần chọn encoding/locale/owner riêng, tạo database đích trước:

~~~bash
createdb \
  -h target-db \
  -U postgres \
  --template=template0 \
  --owner=app_owner \
  --encoding=UTF8 \
  appdb_new
~~~

`template0` giúp tạo database sạch không kế thừa local objects từ template1. Locale/collation cần cấu hình theo requirements và option được client/server version hỗ trợ.

### 9.6. Kiểm tra database target

~~~sql
SELECT
    datname,
    pg_get_userbyid(datdba) AS owner,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
WHERE datname = 'appdb_new';
~~~

Đảm bảo target encoding/locale đúng trước khi restore. Không phải mọi locale source đều có trên OS target.

### 9.7. Role ownership và ACL strategy

Có hai hướng thường dùng:

**Giữ nguyên ownership/ACL:** restore globals trước, tạo roles và memberships giống source, rồi restore archive như source.

**Dùng ownership/ACL mới:** restore bằng `--no-owner` và `--no-acl`/`--no-privileges`, sau đó gán owner/grants theo provisioning scripts. Có thể dùng `--role` để chạy restore dưới role được chọn nếu quyền phù hợp.

Chọn một chiến lược nhất quán. Tránh restore với owner bị thiếu rồi xử lý thủ công từng object.

---

## 10. Restore custom/directory archive bằng pg_restore

### 10.1. Restore cơ bản

Với database target đã tạo và roles/schema prerequisites sẵn sàng:

~~~bash
pg_restore \
  -h target-db.example.net \
  -p 5432 \
  -U restore_user \
  -d appdb_new \
  --verbose \
  /backup/appdb.dump
~~~

pg_restore sẽ đọc archive và tạo objects/data theo dependency order trong archive TOC.

### 10.2. Restore song song

~~~bash
pg_restore \
  -h target-db.example.net \
  -U restore_user \
  -d appdb_new \
  --jobs=4 \
  --verbose \
  /backup/appdb_dir
~~~

Parallel restore được hỗ trợ cho custom và directory archives. Tar/plain không có cùng khả năng. Tăng jobs có thể giảm elapsed time nhưng tăng:
- Concurrent connections.
- CPU và I/O.
- Index build memory.
- Lock activity.
- Temporary files.
- WAL generation và checkpoint pressure.

Bắt đầu từ mức jobs vừa phải, đo rồi mới tăng.

### 10.3. Restore với owner/ACL mới

~~~bash
pg_restore \
  -h target-db \
  -U restore_admin \
  -d appdb_new \
  --no-owner \
  --no-acl \
  --verbose \
  appdb.dump
~~~

Sau restore, chạy provisioning scripts để gán ownership, grants và default privileges theo target policy.

### 10.4. Chạy dưới role cụ thể

`--role=app_owner` yêu cầu pg_restore kết nối bằng role có quyền thích hợp rồi thực hiện SET ROLE theo lựa chọn. Cần đảm bảo role login ban đầu có thể SET ROLE và có đủ quyền tạo objects/data.

### 10.5. Restore với create database

Có thể dùng `--create` khi muốn pg_restore tạo database theo database definition có trong archive:

~~~bash
pg_restore \
  -h target-db \
  -U postgres \
  --create \
  -d postgres \
  appdb.dump
~~~

Khi dùng `--create`, `-d` là database ban đầu để kết nối, thường là postgres. Nếu cần database đích có encoding/locale/owner riêng hoặc muốn kiểm soát tên, hãy tạo database thủ công rồi restore mà không dùng `--create`.

### 10.6. Clean existing objects

`--clean` yêu cầu pg_restore drop objects trước khi tạo lại. `--if-exists` giúp tránh lỗi khi object chưa tồn tại:

~~~bash
pg_restore \
  -h target-db \
  -U postgres \
  -d appdb_new \
  --clean \
  --if-exists \
  --exit-on-error \
  appdb.dump
~~~

Đây là thao tác destructive với objects hiện có. Không dùng trên target chứa dữ liệu cần giữ. Với migration lớn, database mới rỗng thường dễ kiểm soát hơn việc clean từng object.

### 10.7. Dừng khi có lỗi

`--exit-on-error` khiến pg_restore dừng khi gặp lỗi đầu tiên. Nếu không bật, pg_restore có thể tiếp tục và báo nhiều lỗi; database cuối cùng có thể thiếu objects/data.

Trong production migration, nên lưu log đầy đủ và xử lý mọi errors trước cutover. Không coi exit code 0 là đủ nếu restore command được wrapper che mất lỗi hoặc log đã bị cắt.

### 10.8. Single transaction

`--single-transaction` yêu cầu toàn bộ restore nằm trong một transaction; nếu lỗi, các changes có thể rollback cùng nhau. Nó không tương thích với parallel jobs (`-j`) và không phù hợp mọi archive/operation.

Với database lớn cần parallel restore, thường dùng target database mới và có quy trình xử lý failed restore thay vì ép toàn bộ vào một transaction.

### 10.9. Restore theo sections

Archive có các sections chính:
- `pre-data`: schema definitions và objects cần trước data.
- `data`: table data, large objects và sequence values theo archive.
- `post-data`: indexes, triggers, constraints và các objects sau data.

Có thể restore từng section:

~~~bash
pg_restore --section=pre-data -d appdb_new appdb.dump
pg_restore --section=data -d appdb_new appdb.dump
pg_restore --section=post-data -d appdb_new appdb.dump
~~~

Đây là kỹ thuật hữu ích để tùy chỉnh index/constraint timing, nhưng phải giữ dependency order và tránh chạy lặp trên target đã có objects.

### 10.10. Restore chọn lọc bằng TOC

~~~bash
pg_restore --list appdb.dump > appdb.list
pg_restore --use-list=appdb.list -d appdb_new appdb.dump
~~~

Có thể bỏ entries trong TOC để không restore một số objects. Phải hiểu dependencies, ownership, sequence/table relationships và data completeness trước khi bỏ.

### 10.11. Restore schema-only/data-only

~~~bash
pg_restore --schema-only -d appdb_new appdb.dump
pg_restore --data-only -d appdb_new appdb.dump
~~~

Chỉ dùng khi schema/data đã được phân tách có chủ đích. Data-only restore cần target schema tương thích và có thể cần disable/recreate constraints/indexes theo một plan cụ thể.

### 10.12. Restore vào database rỗng

Đây thường là cách dễ kiểm soát nhất:
1. Tạo database target mới.
2. Restore globals/prerequisites.
3. Restore archive.
4. Chạy validation.
5. Chuyển ứng dụng sau khi đạt readiness gate.

Nếu restore thất bại, có thể giữ logs, điều tra và tạo lại database lab/target sạch theo runbook. Đừng xóa database cũ trước khi migration được chấp nhận.

---

## 11. Restore plain SQL bằng psql

### 11.1. Restore cơ bản

~~~bash
psql \
  -X \
  -h target-db \
  -U restore_user \
  -d appdb_new \
  -v ON_ERROR_STOP=1 \
  -f appdb.sql
~~~

Plain SQL dump có thể chứa CREATE statements, COPY/INSERT, ALTER OWNER và GRANT commands. User restore phải có quyền cần thiết hoặc script phải được tạo với ownership/privileges strategy phù hợp.

### 11.2. Restore với log

~~~bash
psql -X \
  -h target-db \
  -U restore_user \
  -d appdb_new \
  -v ON_ERROR_STOP=1 \
  -f appdb.sql \
  > restore.stdout.log 2> restore.stderr.log
~~~

Kiểm tra exit code của psql và log. Với PowerShell/bash/CI, viết wrapper bảo toàn exit code thay vì chỉ kiểm tra file log có tồn tại.

### 11.3. Restore qua pipe

Có thể truyền plain dump đã nén vào psql qua pipeline. Phải kiểm tra exit code của cả decompressor và psql; một pipeline có thể trả exit code của command cuối tùy shell configuration.

### 11.4. Plain SQL không có parallel restore

Một SQL script có thứ tự statements cụ thể và được psql thực thi theo thứ tự. Muốn parallel restore, hãy dùng custom/directory archive và pg_restore -j, hoặc chia migration thành các phần độc lập có dependency được kiểm soát.

### 11.5. Script có thể chứa destructive commands

Nếu dump được tạo với options clean hoặc có custom SQL, script có thể DROP/CREATE objects. Đọc header và review nội dung trước khi chạy trên database đích đã có data. Chỉ restore vào đúng database đã xác nhận.

---

## 12. Restore performance và tài nguyên

### 12.1. Parallel jobs

Số jobs tốt phụ thuộc:
- Source archive read throughput.
- Target CPU.
- Target storage IOPS/throughput.
- Network bandwidth.
- Index build workload.
- Memory budget và maintenance_work_mem.
- WAL/checkpoint configuration.
- Number/size of tables và indexes.

Tăng jobs không đảm bảo restore nhanh hơn; storage saturation có thể làm throughput giảm.

### 12.2. maintenance_work_mem

Index creation trong restore có thể dùng maintenance_work_mem. Có thể đặt mức cao hơn trong restore session hoặc role riêng nếu memory budget cho phép. Vì pg_restore -j chạy nhiều jobs, phải tính số index builds concurrent và autovacuum/query workload.

### 12.3. work_mem

Restore thường không phải workload sort/hash query thông thường, nhưng maintenance scripts/triggers/functions có thể chạy SQL. Không tăng work_mem quá lớn chỉ vì restore chậm; đo đúng operation đang tiêu thụ resource.

### 12.4. WAL và checkpoints

Bulk restore tạo nhiều WAL. Theo dõi:
- WAL generation rate.
- Checkpoint frequency/duration.
- Disk throughput.
- WAL archive backlog.
- Replication lag nếu target đã có downstream replicas.
- Free space của pg_wal và data volume.

Tạm thay đổi checkpoint/WAL settings chỉ theo một kế hoạch có đo lường, backup và rollback. Không tắt durability settings tùy tiện trên target production.

### 12.5. Indexes và constraints

Restore archive mặc định sắp xếp object theo dependencies. Với một số migration, có thể restore pre-data/data/post-data riêng để index build sau khi load data. Việc tạo indexes sau data có thể nhanh hơn so với duy trì index cho từng row insert, nhưng cần disk headroom và validation.

### 12.6. Trigger và foreign key

Trigger/constraint có thể tăng restore cost hoặc gây lỗi nếu target schema khác. Không dùng `--disable-triggers` như giải pháp mặc định; option này yêu cầu quyền cao và có thể để lại dữ liệu vi phạm constraints nếu không validate lại.

### 12.7. Analyze sau restore

Sau khi restore, planner statistics có thể chưa phản ánh distribution mới. Chạy ANALYZE hoặc công cụ phù hợp:

~~~bash
vacuumdb -h target-db -U maintenance_user \
  --analyze-in-stages appdb_new
~~~

`--analyze-in-stages` chạy các giai đoạn analyze phù hợp để planner có statistics sớm, hữu ích cho database vừa được restore. Kiểm tra option trong vacuumdb version đang dùng.

### 12.8. Restore progress

pg_restore có verbose output nhưng không phải mọi command đều có progress view thống nhất. Theo dõi:
- Active sessions và query text.
- pg_stat_progress_create_index.
- pg_stat_progress_copy khi version hỗ trợ.
- CPU/memory/IO/network.
- Database size growth.
- WAL and checkpoint metrics.
- Restore job logs.

### 12.9. Khi nào giảm jobs?

Giảm parallel jobs khi:
- Target storage latency tăng mạnh.
- Host/container memory pressure.
- CPU đã bão hòa.
- WAL disk gần đầy.
- Application workloads cạnh tranh.
- Lock contention tăng.
- Tổng throughput giảm khi thêm jobs.

### 12.10. Restore rehearsal

Chạy ít nhất một rehearsal trên dữ liệu và cấu hình gần production. Ghi:
- Dump duration.
- Transfer duration.
- Restore duration.
- Analyze duration.
- Validation duration.
- Peak RAM/CPU/IO.
- Archive size.
- Cutover downtime ước tính.

Không dùng một benchmark database nhỏ để dự đoán chính xác thời gian cho production.

---

## 13. Validation sau restore

### 13.1. Kiểm tra restore command

Xác nhận:
- Command exit code bằng 0.
- Không có lỗi bị bỏ qua trong logs.
- Tất cả jobs đã kết thúc.
- Không còn restore sessions bị treo.
- Database nhận kết nối.
- Target database size hợp lý.
- Không còn objects invalid/incomplete do failed commands.

Nếu có errors, phân loại và sửa trước cutover. Một restore “gần xong” vẫn có thể thiếu indexes, constraints hoặc rows.

### 13.2. Kiểm tra database và schema

~~~sql
SELECT
    current_database(),
    current_user,
    version();

SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

So sánh table/schema inventory với source. Bỏ qua các system objects/version-specific objects khi diff.

### 13.3. Kiểm tra row counts

Với các bảng quan trọng, so sánh row counts source/target:

~~~sql
SELECT count(*) FROM app.customers;
SELECT count(*) FROM app.orders;
SELECT count(*) FROM app.order_items;
~~~

Với database lớn, count toàn bộ tables có thể tốn thời gian và I/O. Có thể chọn critical tables, partition-level counts hoặc validation aggregates theo business keys.

### 13.4. Kiểm tra business invariants

Ví dụ:
- Orders phải tham chiếu customers hợp lệ.
- Tổng order amount theo ngày phải khớp.
- Không có duplicate business keys.
- Status values thuộc domain cho phép.
- Timestamps nằm trong range hợp lý.
- Số lượng records theo tenant/region khớp.
- Các bảng ledger/debit-credit cân bằng.

Business validation thường phát hiện sai lệch mà row count không thấy.

### 13.5. Kiểm tra constraints và indexes

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated
FROM pg_constraint
WHERE connamespace NOT IN (
    'pg_catalog'::regnamespace,
    'information_schema'::regnamespace
)
ORDER BY conrelid::regclass::text, conname;
~~~

Kiểm tra constraints được validate và indexes hợp lệ. Dùng catalog query phù hợp version; partitioned indexes và extension objects có metadata riêng.

### 13.6. Kiểm tra sequence state

Có thể xem sequence state bằng các lệnh phù hợp với từng sequence. Ví dụ:

~~~sql
SELECT last_value, is_called
FROM app.orders_order_id_seq;
~~~

Kiểm tra max key trong table và next sequence value. Không gọi nextval chỉ để “thử” trên production nếu không muốn tiêu thụ một ID; sequence values không rollback như table changes.

### 13.7. Kiểm tra large objects

Nếu ứng dụng dùng large objects:
- Kiểm tra số lượng LO objects theo catalog/API phù hợp.
- Kiểm tra references trong application tables.
- Mở/đọc mẫu objects bằng ứng dụng.
- Kiểm tra permissions/ownership.
- Xác nhận không bị exclude trong dump.

### 13.8. Kiểm tra roles và permissions

Thử kết nối bằng application role thực tế. Kiểm tra:
- LOGIN và database CONNECT.
- Schema USAGE/CREATE.
- Table/sequence privileges.
- Function EXECUTE.
- Default privileges.
- RLS policies.
- Ownership và role memberships.

Không chỉ test bằng superuser; superuser có thể che lỗi permission của ứng dụng.

### 13.9. Kiểm tra extensions

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

Xác nhận versions đúng, extension functions/operators hoạt động và index methods/types được nhận diện.

### 13.10. Kiểm tra application

Smoke tests nên bao gồm:
- Login/connectivity.
- Read critical records.
- Insert/update/delete trong test transaction.
- Queries có joins/sorts/aggregates.
- Stored functions/triggers.
- Background jobs.
- Reports/exports.
- Transactions và rollback.
- Authentication/TLS/connection pool.

Chạy workload regression tests để phát hiện planner/extension/collation changes.

### 13.11. Analyze và vacuum

Sau restore, chạy ANALYZE hoặc §vacuumdb --analyze-in-stages§ để planner có statistics. Nếu cần, chạy VACUUM theo policy. Không mặc định phải VACUUM FULL sau restore.

### 13.12. Kiểm tra monitoring/backup

Trước khi mở traffic:
- Monitoring target đã nhận metrics.
- Alert rules và dashboards đã trỏ đúng cluster.
- Backup job chạy thành công.
- WAL archiving/PITR đã cấu hình nếu yêu cầu.
- Restore test của backup mới có kế hoạch.
- Replication/standby downstream được tạo lại nếu cần.

---

## 14. Cutover, downtime và rollback

### 14.1. Chuẩn bị cutover

Trước maintenance window:
- Rehearse dump/restore trên dữ liệu gần production.
- Đo tổng downtime cần thiết.
- Xác định freeze window và owner.
- Chuẩn bị DNS/connection string/load balancer changes.
- Xác định job/worker/consumer cần dừng.
- Chuẩn bị validation queries.
- Xác định rollback deadline và decision maker.
- Đảm bảo source backup còn phục hồi được.

### 14.2. Offline cutover runbook

1. Thông báo maintenance window.
2. Dừng nhận writes từ ứng dụng.
3. Dừng background workers, scheduled jobs và integrations có thể ghi.
4. Chờ transactions đang mở kết thúc hoặc rollback theo policy.
5. Tạo final dump và globals nếu có thay đổi.
6. Kiểm tra archive, checksum và TOC.
7. Restore vào target database/cluster.
8. Chạy ANALYZE và validation.
9. Đồng bộ external state và xác nhận sequence values.
10. Chuyển application connections tới target.
11. Chạy smoke tests.
12. Mở writes.
13. Theo dõi errors, latency, locks, replication và business metrics.

Nếu source tiếp tục nhận writes sau khi dump snapshot bắt đầu, các writes đó có thể không nằm trong target. Freeze phải bắt đầu trước snapshot hoặc phải có delta sync.

### 14.3. Cutover với baseline + delta

Nếu cần giảm downtime:
1. Tạo baseline dump trong khi source hoạt động.
2. Restore baseline lên target.
3. Thiết lập logical replication/delta capture từ source tới target theo thiết kế.
4. Theo dõi apply lag và xác minh schema compatibility.
5. Dừng writes source trong cutover window.
6. Chờ target apply hết changes tới final marker/LSN.
7. Kiểm tra sequences và external state.
8. Chuyển ứng dụng sang target.
9. Chỉ sau khi xác nhận mới cho phép target nhận writes.

Đây là migration phức tạp hơn dump/restore offline. Cần kiểm tra logical replication support, DDL coordination, sequence handling và cutover correctness; không tự giả định dump snapshot tự đồng bộ delta.

### 14.4. Rollback trước khi target nhận writes

Nếu chưa mở writes trên target:
- Chuyển ứng dụng về source.
- Xác minh source vẫn nguyên vẹn.
- Gỡ/disable target theo change plan.
- Lưu logs và archive để điều tra.
- Sửa nguyên nhân rồi rehearsal lại.

Đây là thời điểm rollback đơn giản nhất vì source vẫn là write authority.

### 14.5. Rollback sau khi target nhận writes

Sau khi target đã nhận writes mới, source không có những changes đó. Không thể đơn giản đổi connection string quay lại source mà vẫn giữ toàn bộ dữ liệu.

Cần một trong các chiến lược đã chuẩn bị:
- Reverse replication nếu đã thiết kế và test.
- Data reconciliation theo keys/transactions.
- Restore/replay từ target backup/WAL nếu kiến trúc cho phép.
- Forward fix trên target thay vì rollback.

Không mở writes đồng thời trên source và target nếu không có conflict resolution strategy.

### 14.6. Giữ source trong rollback window

Sau cutover, giữ source ở read-only hoặc fenced state theo policy:
- Không cho application vô tình ghi vào source.
- Không drop source cluster ngay.
- Giữ backups và logs.
- Ghi lại final source snapshot/LSN.
- Theo dõi target ổn định trước khi retire source.

### 14.7. RTO/RPO

Dump/restore offline thường có RPO bằng 0 cho writes đã freeze và được dump/restore đầy đủ; nó không bảo vệ writes phát sinh sau snapshot nếu không có delta sync. RTO phụ thuộc dump, transfer, restore, validation và cutover duration.

Đặt RPO/RTO dựa trên workload và test thực tế, không dựa vào tốc độ một lần chạy nhỏ.

---

## 15. Security, integrity và retention của dump files

### 15.1. Dump có thể chứa toàn bộ dữ liệu nhạy cảm

Archive có thể chứa PII, credentials trong table data, password verifiers trong globals, application secrets và business records. Bảo vệ dump tương đương bảo vệ database production.

### 15.2. File permissions

- Chỉ cấp quyền đọc cho backup/restore service accounts.
- Tránh thư mục world-readable.
- Tách quyền operator và application.
- Hạn chế download vào workstation cá nhân.
- Xóa bản tạm theo retention policy sau khi migration hoàn tất.

### 15.3. Encryption

Mã hóa archive khi lưu và khi truyền. Quản lý encryption keys riêng với backup files; kiểm tra restore access trước migration. Không lưu key trong cùng thư mục hoặc cùng artifact manifest không bảo vệ.

### 15.4. Integrity checksum

Tạo checksum sau dump và kiểm tra lại sau transfer:

~~~bash
sha256sum appdb.dump > appdb.dump.sha256
sha256sum -c appdb.dump.sha256
~~~

Trên hệ điều hành khác, dùng công cụ hash tương ứng. Checksum chứng minh file không đổi trong transfer; nó không chứng minh database dump logic đầy đủ hay restore thành công.

### 15.5. Kiểm tra archive

~~~bash
pg_restore --list appdb.dump > appdb.toc
~~~

Lệnh này đọc metadata/TOC và giúp phát hiện archive không đọc được. Nó không thay thế restore test.

### 15.6. Restore test

Backup chỉ đáng tin khi có thể restore. Lập lịch restore test sang môi trường cách ly:
- Kiểm tra archive integrity.
- Restore bằng đúng major version target.
- Chạy schema/data validation.
- Ghi duration và resource usage.
- Kiểm tra extension/large objects.
- Lưu kết quả và owner.

### 15.7. Retention

Định nghĩa:
- Số bản dump giữ lại.
- Thời gian giữ trước/sau cutover.
- Backup encryption key retention.
- Offsite/immutable copies nếu yêu cầu.
- Cách xóa an toàn.
- Legal/compliance retention.
- Ai được phép restore/download.

### 15.8. Trust boundary

Dump là input có thể chứa SQL definitions, functions, triggers và commands. Chỉ restore archive từ nguồn tin cậy vào môi trường được kiểm soát. Không restore dump không rõ nguồn vào cluster có credentials hoặc network access nhạy cảm.

---

## 13. Validation sau restore

### 13.1. Kiểm tra restore command

Xác nhận:
- Command exit code bằng 0.
- Không có lỗi bị bỏ qua trong logs.
- Tất cả jobs đã kết thúc.
- Không còn restore sessions bị treo.
- Database nhận kết nối.
- Target database size hợp lý.
- Không còn objects invalid/incomplete do failed commands.

Nếu có errors, phân loại và sửa trước cutover. Một restore “gần xong” vẫn có thể thiếu indexes, constraints hoặc rows.

### 13.2. Kiểm tra database và schema

~~~sql
SELECT
    current_database(),
    current_user,
    version();

SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

So sánh table/schema inventory với source. Bỏ qua các system objects/version-specific objects khi diff.

### 13.3. Kiểm tra row counts

Với các bảng quan trọng, so sánh row counts source/target:

~~~sql
SELECT count(*) FROM app.customers;
SELECT count(*) FROM app.orders;
SELECT count(*) FROM app.order_items;
~~~

Với database lớn, count toàn bộ tables có thể tốn thời gian và I/O. Có thể chọn critical tables, partition-level counts hoặc validation aggregates theo business keys.

### 13.4. Kiểm tra business invariants

Ví dụ:
- Orders phải tham chiếu customers hợp lệ.
- Tổng order amount theo ngày phải khớp.
- Không có duplicate business keys.
- Status values thuộc domain cho phép.
- Timestamps nằm trong range hợp lý.
- Số lượng records theo tenant/region khớp.
- Các bảng ledger/debit-credit cân bằng.

Business validation thường phát hiện sai lệch mà row count không thấy.

### 13.5. Kiểm tra constraints và indexes

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated
FROM pg_constraint
WHERE connamespace NOT IN (
    'pg_catalog'::regnamespace,
    'information_schema'::regnamespace
)
ORDER BY conrelid::regclass::text, conname;
~~~

Kiểm tra constraints được validate và indexes hợp lệ. Dùng catalog query phù hợp version; partitioned indexes và extension objects có metadata riêng.

### 13.6. Kiểm tra sequence state

Có thể xem sequence state bằng các lệnh phù hợp với từng sequence. Ví dụ:

~~~sql
SELECT last_value, is_called
FROM app.orders_order_id_seq;
~~~

Kiểm tra max key trong table và next sequence value. Không gọi nextval chỉ để “thử” trên production nếu không muốn tiêu thụ một ID; sequence values không rollback như table changes.

### 13.7. Kiểm tra large objects

Nếu ứng dụng dùng large objects:
- Kiểm tra số lượng LO objects theo catalog/API phù hợp.
- Kiểm tra references trong application tables.
- Mở/đọc mẫu objects bằng ứng dụng.
- Kiểm tra permissions/ownership.
- Xác nhận không bị exclude trong dump.

### 13.8. Kiểm tra roles và permissions

Thử kết nối bằng application role thực tế. Kiểm tra:
- LOGIN và database CONNECT.
- Schema USAGE/CREATE.
- Table/sequence privileges.
- Function EXECUTE.
- Default privileges.
- RLS policies.
- Ownership và role memberships.

Không chỉ test bằng superuser; superuser có thể che lỗi permission của ứng dụng.

### 13.9. Kiểm tra extensions

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

Xác nhận versions đúng, extension functions/operators hoạt động và index methods/types được nhận diện.

### 13.10. Kiểm tra application

Smoke tests nên bao gồm:
- Login/connectivity.
- Read critical records.
- Insert/update/delete trong test transaction.
- Queries có joins/sorts/aggregates.
- Stored functions/triggers.
- Background jobs.
- Reports/exports.
- Transactions và rollback.
- Authentication/TLS/connection pool.

Chạy workload regression tests để phát hiện planner/extension/collation changes.

### 13.11. Analyze và vacuum

Sau restore, chạy ANALYZE hoặc `vacuumdb --analyze-in-stages` để planner có statistics. Nếu cần, chạy VACUUM theo policy. Không mặc định phải VACUUM FULL sau restore.

### 13.12. Kiểm tra monitoring/backup

Trước khi mở traffic:
- Monitoring target đã nhận metrics.
- Alert rules và dashboards đã trỏ đúng cluster.
- Backup job chạy thành công.
- WAL archiving/PITR đã cấu hình nếu yêu cầu.
- Restore test của backup mới có kế hoạch.
- Replication/standby downstream được tạo lại nếu cần.

---

## 14. Cutover, downtime và rollback

### 14.1. Chuẩn bị cutover

Trước maintenance window:
- Rehearse dump/restore trên dữ liệu gần production.
- Đo tổng downtime cần thiết.
- Xác định freeze window và owner.
- Chuẩn bị DNS/connection string/load balancer changes.
- Xác định job/worker/consumer cần dừng.
- Chuẩn bị validation queries.
- Xác định rollback deadline và decision maker.
- Đảm bảo source backup còn phục hồi được.

### 14.2. Offline cutover runbook

1. Thông báo maintenance window.
2. Dừng nhận writes từ ứng dụng.
3. Dừng background workers, scheduled jobs và integrations có thể ghi.
4. Chờ transactions đang mở kết thúc hoặc rollback theo policy.
5. Tạo final dump và globals nếu có thay đổi.
6. Kiểm tra archive, checksum và TOC.
7. Restore vào target database/cluster.
8. Chạy ANALYZE và validation.
9. Đồng bộ external state và xác nhận sequence values.
10. Chuyển application connections tới target.
11. Chạy smoke tests.
12. Mở writes.
13. Theo dõi errors, latency, locks, replication và business metrics.

Nếu source tiếp tục nhận writes sau khi dump snapshot bắt đầu, các writes đó có thể không nằm trong target. Freeze phải bắt đầu trước snapshot hoặc phải có delta sync.

### 14.3. Cutover với baseline + delta

Nếu cần giảm downtime:
1. Tạo baseline dump trong khi source hoạt động.
2. Restore baseline lên target.
3. Thiết lập logical replication/delta capture từ source tới target theo thiết kế.
4. Theo dõi apply lag và xác minh schema compatibility.
5. Dừng writes source trong cutover window.
6. Chờ target apply hết changes tới final marker/LSN.
7. Kiểm tra sequences và external state.
8. Chuyển ứng dụng sang target.
9. Chỉ sau khi xác nhận mới cho phép target nhận writes.

Đây là migration phức tạp hơn dump/restore offline. Cần kiểm tra logical replication support, DDL coordination, sequence handling và cutover correctness; không tự giả định dump snapshot tự đồng bộ delta.

### 14.4. Rollback trước khi target nhận writes

Nếu chưa mở writes trên target:
- Chuyển ứng dụng về source.
- Xác minh source vẫn nguyên vẹn.
- Gỡ/disable target theo change plan.
- Lưu logs và archive để điều tra.
- Sửa nguyên nhân rồi rehearsal lại.

Đây là thời điểm rollback đơn giản nhất vì source vẫn là write authority.

### 14.5. Rollback sau khi target nhận writes

Sau khi target đã nhận writes mới, source không có những changes đó. Không thể đơn giản đổi connection string quay lại source mà vẫn giữ toàn bộ dữ liệu.

Cần một trong các chiến lược đã chuẩn bị:
- Reverse replication nếu đã thiết kế và test.
- Data reconciliation theo keys/transactions.
- Restore/replay từ target backup/WAL nếu kiến trúc cho phép.
- Forward fix trên target thay vì rollback.

Không mở writes đồng thời trên source và target nếu không có conflict resolution strategy.

### 14.6. Giữ source trong rollback window

Sau cutover, giữ source ở read-only hoặc fenced state theo policy:
- Không cho application vô tình ghi vào source.
- Không drop source cluster ngay.
- Giữ backups và logs.
- Ghi lại final source snapshot/LSN.
- Theo dõi target ổn định trước khi retire source.

### 14.7. RTO/RPO

Dump/restore offline thường có RPO bằng 0 cho writes đã freeze và được dump/restore đầy đủ; nó không bảo vệ writes phát sinh sau snapshot nếu không có delta sync. RTO phụ thuộc dump, transfer, restore, validation và cutover duration.

Đặt RPO/RTO dựa trên workload và test thực tế, không dựa vào tốc độ một lần chạy nhỏ.

---

## 15. Security, integrity và retention của dump files

### 15.1. Dump có thể chứa toàn bộ dữ liệu nhạy cảm

Archive có thể chứa PII, credentials trong table data, password verifiers trong globals, application secrets và business records. Bảo vệ dump tương đương bảo vệ database production.

### 15.2. File permissions

- Chỉ cấp quyền đọc cho backup/restore service accounts.
- Tránh thư mục world-readable.
- Tách quyền operator và application.
- Hạn chế download vào workstation cá nhân.
- Xóa bản tạm theo retention policy sau khi migration hoàn tất.

### 15.3. Encryption

Mã hóa archive khi lưu và khi truyền. Quản lý encryption keys riêng với backup files; kiểm tra restore access trước migration. Không lưu key trong cùng thư mục hoặc cùng artifact manifest không bảo vệ.

### 15.4. Integrity checksum

Tạo checksum sau dump và kiểm tra lại sau transfer:

~~~bash
sha256sum appdb.dump > appdb.dump.sha256
sha256sum -c appdb.dump.sha256
~~~

Trên hệ điều hành khác, dùng công cụ hash tương ứng. Checksum chứng minh file không đổi trong transfer; nó không chứng minh database dump logic đầy đủ hay restore thành công.

### 15.5. Kiểm tra archive

~~~bash
pg_restore --list appdb.dump > appdb.toc
~~~

Lệnh này đọc metadata/TOC và giúp phát hiện archive không đọc được. Nó không thay thế restore test.

### 15.6. Restore test

Backup chỉ đáng tin khi có thể restore. Lập lịch restore test sang môi trường cách ly:
- Kiểm tra archive integrity.
- Restore bằng đúng major version target.
- Chạy schema/data validation.
- Ghi duration và resource usage.
- Kiểm tra extension/large objects.
- Lưu kết quả và owner.

### 15.7. Retention

Định nghĩa:
- Số bản dump giữ lại.
- Thời gian giữ trước/sau cutover.
- Backup encryption key retention.
- Offsite/immutable copies nếu yêu cầu.
- Cách xóa an toàn.
- Legal/compliance retention.
- Ai được phép restore/download.

### 15.8. Trust boundary

Dump là input có thể chứa SQL definitions, functions, triggers và commands. Chỉ restore archive từ nguồn tin cậy vào môi trường được kiểm soát. Không restore dump không rõ nguồn vào cluster có credentials hoặc network access nhạy cảm.

---

## 16. Troubleshooting dump/restore

### 16.1. pg_dump báo server version không được hỗ trợ

Nguyên nhân thường là pg_dump client cũ hơn major version của server source. Dùng client có version đủ mới để đọc server đó và kiểm tra compatibility theo release. Không sửa version string hoặc ép binary cũ tiếp tục.

### 16.2. Permission denied khi dump

Kiểm tra:
- Role có CONNECT database.
- Quyền SELECT trên tables/sequences cần dump.
- Quyền đọc large objects nếu ứng dụng dùng chúng.
- Row-level security và dump options.
- Quyền xem objects/metadata.
- Role membership và default privileges.

Dùng một backup role được thiết kế với quyền cần thiết; không mặc định cấp superuser nếu không cần.

### 16.3. Archive bị lỗi hoặc không đọc được

Kiểm tra:
- Exit code của pg_dump.
- Disk full hoặc filesystem error.
- Network disconnect.
- Archive bị copy thiếu/truncated.
- Compression/decompression errors.
- Checksum trước/sau transfer.

Dùng pg_restore --list để kiểm tra TOC. Nếu archive hỏng, tạo dump mới từ source hoặc khôi phục từ một backup đã xác minh; không dùng một file truncated để cutover.

### 16.4. Role does not exist khi restore

Restore database archive có thể tham chiếu owner/grantee không tồn tại. Restore globals trước, hoặc dùng no-owner/no-acl rồi provision roles/privileges theo target policy. Kiểm tra default privileges và role memberships sau restore.

### 16.5. Tablespace location does not exist

Globals script có thể tạo tablespace với path của source. Tạo path trên target với permissions đúng hoặc remap/bỏ tablespace theo kế hoạch. Đừng để object restore vào tablespace path không tồn tại.

### 16.6. Extension control file missing

Target chưa cài extension package tương thích hoặc package path không đúng. Cài extension package cho target major version, restart nếu library/configuration yêu cầu, sau đó restore lại trên database sạch.

### 16.7. Collation/locale errors

Locale source không có trên target OS hoặc provider/version khác. Kiểm tra database locale, encoding, ICU/libc support và collation definitions. Có thể phải tạo database đích với locale khác có chủ đích và kiểm tra/rebuild indexes; không đổi locale tùy tiện sau restore.

### 16.8. Duplicate key hoặc unique violation

Có thể do:
- Target table đã có data trước restore.
- Restore bị chạy lặp.
- Data archive có rows xung đột.
- Target schema có unique constraint khác source.
- Một application/job đang ghi vào target trong lúc restore.

Ưu tiên database mới rỗng, dừng local writes và xác định nguồn authoritative. Không bỏ constraint để che conflict nếu chưa có reconciliation plan.

### 16.9. Foreign key violation

Kiểm tra thứ tự restore, target baseline, excluded tables/data, constraints khác nhau và triggers. Nếu dùng partial dump, có thể thiếu referenced rows. Không tắt FK vĩnh viễn để restore “thành công”.

### 16.10. Function/language errors

Target có thể thiếu procedural language, extension, function dependency hoặc OS library. Kiểm tra function definitions, language packages, permissions và extension versions trước khi chạy restore.

### 16.11. Restore chậm

Phân loại bottleneck:
- Archive read/decompression.
- Network transfer.
- Target storage writes.
- Index builds.
- WAL/checkpoint.
- Constraint validation.
- Lock waits.
- Too many/too few parallel jobs.
- CPU/memory pressure.

Dùng logs/progress/OS metrics để điều chỉnh đúng thành phần.

### 16.12. Restore thành công nhưng application lỗi

Kiểm tra application role, schema search_path, ownership/grants, sequences, extensions, collations, functions, connection parameters và query plans. Database-level restore success không chứng minh application behavior tương thích.

### 16.13. Sequence cấp trùng ID sau cutover

Kiểm tra sequence current state, maximum key, is_called, increment/cache và sequences dùng chung. Đồng bộ sequence sau khi writes đã freeze và trước khi mở traffic. Không gọi setval dựa trên một bảng nếu sequence được chia sẻ bởi nhiều bảng.

### 16.14. Dump thiếu writes mới nhất

pg_dump chỉ chứa snapshot tại thời điểm bắt đầu. Writes sau snapshot không có trong archive. Giữ write freeze trước dump hoặc triển khai delta sync/replication đã test; không mở target nếu chưa xử lý phần delta.

---

## 17. So sánh dump/restore với các phương pháp upgrade khác

### 17.1. pg_upgrade

pg_upgrade chuyển data files/catalog structures theo quy trình hỗ trợ giữa các major versions tương thích. Thường nhanh hơn dump/restore vì không phải export/import toàn bộ rows, nhưng có yêu cầu về binary compatibility, extension binaries, OS/layout và quy trình chuẩn bị.

Chọn pg_upgrade khi:
- Muốn nâng major version tại chỗ/side-by-side theo supported path.
- Có thể đáp ứng yêu cầu binaries và filesystem.
- Muốn giảm thời gian chuyển dữ liệu.
- Có rollback/backup strategy rõ.

### 17.2. Physical backup/restore

Physical backup/replication chuyển data files và WAL theo cơ chế physical. Nó thường gắn với cùng major version/physical compatibility rules và không dùng như cách chung để đổi major version trừ workflow upgrade được hỗ trợ.

### 17.3. Logical replication

Logical replication có thể stream changes từ publisher cũ sang subscriber mới để giảm downtime. Cần schema coordination, sequence handoff, DDL management và failover/cutover plan. Dump baseline có thể kết hợp với logical replication trong một số migration designs.

### 17.4. Dump/restore

Dump/restore linh hoạt về objects, encoding và môi trường, nhưng có thể chậm do export/import và cần downtime nếu không có delta mechanism.

### 17.5. Bảng so sánh

| Phương pháp | Điểm mạnh | Giới hạn chính | Use case |
|---|---|---|---|
| pg_dump/pg_restore | Linh hoạt, logical, chọn objects | Dump/restore time, downtime nếu offline | Major migration, platform move, selective migration |
| pg_upgrade | Thường nhanh, giữ data files theo workflow | Binary/version/layout prerequisites | Major upgrade theo supported path |
| Physical backup/restore | Phục hồi nhanh, phù hợp HA/DR | Physical compatibility, thường cùng major | Backup/DR, standby |
| Logical replication | Có thể giảm downtime | DDL/sequence/schema coordination | Online migration, cross-version replication được hỗ trợ |

Không chọn phương pháp chỉ theo tốc độ. Cân nhắc RPO/RTO, database size, extension compatibility, operating system, downtime budget và khả năng rehearsal.

---

## 18. Runbook tổng quát dump/restore major upgrade

### 18.1. Trước maintenance window

1. Inventory versions, databases, roles, tablespaces, extensions và external dependencies.
2. Chọn archive format và compression.
3. Ước lượng archive size, transfer, restore và analyze durations.
4. Provision target cluster và extension packages.
5. Tạo roles/tablespaces/database theo target policy.
6. Chạy full rehearsal trên dữ liệu gần production.
7. Chuẩn bị validation queries, smoke tests và rollback decision points.
8. Xác nhận backup retention và encryption.

### 18.2. Dump

1. Freeze DDL hoặc kiểm soát schema changes.
2. Nếu offline, freeze application writes trước snapshot.
3. Dump globals.
4. Dump database(s) bằng custom/directory format.
5. Ghi logs/exit code.
6. Tạo checksum.
7. Kiểm tra archive TOC.
8. Copy archive sang target storage an toàn.

### 18.3. Restore

1. Cài target binaries/extensions.
2. Restore globals/tablespaces.
3. Tạo database target đúng encoding/locale/owner.
4. Restore archive bằng pg_restore/psql.
5. Điều chỉnh parallel jobs theo memory/I/O.
6. Dừng và xử lý errors.
7. Chạy ANALYZE.
8. Kiểm tra sequences, permissions và large objects.

### 18.4. Validation

1. So sánh schema/table inventory.
2. So sánh row counts/critical aggregates.
3. Kiểm tra constraints/indexes.
4. Kiểm tra extensions và functions.
5. Kiểm tra application roles.
6. Chạy application smoke/regression tests.
7. Xác nhận backup/monitoring/replication.
8. Đạt readiness gate trước cutover.

### 18.5. Cutover

1. Dừng writes/jobs.
2. Xác nhận final dump/delta đã đủ.
3. Chuyển application routing.
4. Chạy smoke tests trên target.
5. Mở writes.
6. Theo dõi business metrics/latency/errors.
7. Giữ source fenced/read-only trong rollback window.
8. Retire source sau khi owner chấp nhận.

### 18.6. Khi nào dừng cutover?

Không mở writes nếu:
- Restore còn errors chưa giải thích.
- Critical table counts/business checks lệch.
- Application role không truy cập được.
- Sequence có nguy cơ cấp trùng IDs.
- Extension/function quan trọng lỗi.
- Có writes sau snapshot chưa được chuyển.
- Backup/rollback path không còn khả dụng.
- Target chưa có monitoring/alerting cần thiết.

---

## 19. Bài lab: dump và restore một database

Thực hiện trên hai PostgreSQL instances lab hoặc một cluster source/target cô lập. Dùng database test; không drop database production.

### 19.1. Chuẩn bị source database

~~~sql
CREATE DATABASE dump_lab;
~~~

Kết nối vào dump_lab:

~~~sql
CREATE SCHEMA app;

CREATE TABLE app.customers (
    customer_id bigint PRIMARY KEY,
    full_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app.orders (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES app.customers(customer_id),
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app.customers(customer_id, full_name)
VALUES
    (1, 'An Nguyen'),
    (2, 'Binh Tran');

INSERT INTO app.orders(customer_id, amount)
VALUES
    (1, 125.50),
    (1, 80.00),
    (2, 240.00);
~~~

### 19.2. Dump custom format

~~~bash
pg_dump -Fc -d dump_lab -f dump_lab.dump
~~~

Kiểm tra exit code và archive:

~~~bash
pg_restore --list dump_lab.dump
~~~

### 19.3. Dump directory format

~~~bash
pg_dump -Fd -j 2 -d dump_lab -f dump_lab_dir
~~~

Directory output là một folder; bảo toàn toàn bộ nội dung khi copy sang target.

### 19.4. Tạo target database

Trên target cluster:

~~~bash
createdb -T template0 -E UTF8 dump_lab_new
~~~

Nếu dùng owner/locale khác, thêm options phù hợp với target environment.

### 19.5. Restore

~~~bash
pg_restore \
  -d dump_lab_new \
  --exit-on-error \
  --verbose \
  dump_lab.dump
~~~

Thử parallel restore trên directory archive trong một database lab mới khác:

~~~bash
pg_restore -j 2 -d dump_lab_parallel dump_lab_dir
~~~

### 19.6. Kiểm tra dữ liệu

~~~sql
SELECT count(*) FROM app.customers;
SELECT count(*) FROM app.orders;

SELECT
    c.customer_id,
    c.full_name,
    count(o.order_id) AS order_count,
    coalesce(sum(o.amount), 0) AS total_amount
FROM app.customers AS c
LEFT JOIN app.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Chạy cùng queries trên source và target rồi so sánh results.

### 19.7. Kiểm tra sequence/identity

Kiểm tra sequence gắn với identity column và giá trị lớn nhất trong orders. Sau restore, thử insert một row lab và xác nhận ID mới không trùng. Thực hiện trong database test; rollback transaction không hoàn lại sequence value.

### 19.8. Thử restore plain SQL

~~~bash
pg_dump -Fp -d dump_lab -f dump_lab.sql
createdb dump_lab_plain
psql -X -v ON_ERROR_STOP=1 -d dump_lab_plain -f dump_lab.sql
~~~

So sánh thời gian/khả năng đọc script và restore behavior giữa plain và custom formats.

### 19.9. Dọn lab

Sau khi ghi lại kết quả, xóa database lab theo quy trình an toàn. Không dùng DROP DATABASE nếu có session hoặc dữ liệu cần giữ.

---

## 20. Bài lab: globals, roles và restore options

### 20.1. Tạo role thử nghiệm

Trên source:

~~~sql
CREATE ROLE dump_lab_owner NOLOGIN;
CREATE ROLE dump_lab_app LOGIN;
GRANT dump_lab_owner TO dump_lab_app;
ALTER SCHEMA app OWNER TO dump_lab_owner;
GRANT USAGE ON SCHEMA app TO dump_lab_app;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO dump_lab_app;
~~~

Trong lab, dùng password/secret an toàn nếu cần login. Không ghi password thật vào script.

### 20.2. Dump globals

~~~bash
pg_dumpall --globals-only -f globals_lab.sql
~~~

Review file để hiểu role/tablespace statements. File có thể chứa sensitive role metadata.

### 20.3. Restore globals trên target

~~~bash
psql -X -v ON_ERROR_STOP=1 -d postgres -f globals_lab.sql
~~~

Nếu role đã tồn tại, xử lý conflict có chủ đích trước khi chạy.

### 20.4. Restore không owner/ACL

Tạo database target rỗng rồi chạy:

~~~bash
pg_restore \
  -d dump_lab_no_acl \
  --no-owner \
  --no-acl \
  --exit-on-error \
  dump_lab.dump
~~~

Sau đó chạy provisioning SQL để gán owner/grants theo target policy. Kiểm tra bằng application role thay vì superuser.

### 20.5. Thử clean có kiểm soát

Trên database lab có thể tái tạo:
- Restore một lần.
- Restore lại với `--clean --if-exists`.
- Quan sát objects bị drop/recreate.
- Ghi lại ảnh hưởng tới local-only objects.

Không dùng clean option trên database có dữ liệu cần giữ.

---

## 21. Bài tập thực hành

Các bài dùng PostgreSQL lab. Không drop/clean database production để kiểm tra một giả thuyết.

### Bài 1 — Logical dump

Dump/restore khác physical backup như thế nào?

### Bài 2 — pg_dump

pg_dump dump phạm vi nào? Nó có tự dump roles/tablespaces toàn cluster không?

### Bài 3 — pg_dumpall

pg_dumpall --globals-only chứa những loại objects nào?

### Bài 4 — pg_restore

pg_restore dùng cho những archive formats nào?

### Bài 5 — Plain format

Plain SQL dump được restore bằng công cụ nào? Có parallel restore không?

### Bài 6 — Custom format

Custom archive có lợi ích gì so với plain SQL?

### Bài 7 — Directory format

Vì sao directory format phù hợp parallel dump và parallel restore?

### Bài 8 — Tar format

Tar archive có parallel restore như custom/directory không?

### Bài 9 — Version compatibility

Vì sao pg_dump client cũ không thể dump server có major version mới hơn nó?

### Bài 10 — Upgrade direction

Vì sao dump/restore thường thuận tiện để chuyển từ major version cũ sang mới?

### Bài 11 — Globals

Vì sao nên restore roles/tablespaces trước database archive?

### Bài 12 — Tablespaces

Điều gì xảy ra nếu target không có filesystem path được khai báo trong tablespace definition?

### Bài 13 — Extensions

Dump có mang theo extension shared library binaries không?

### Bài 14 — Large objects

Cần làm gì nếu ứng dụng dùng large objects?

### Bài 15 — Sequence state

Dump có thể lưu sequence state như thế nào? Vì sao cần xác nhận trước cutover?

### Bài 16 — Snapshot

pg_dump tạo snapshot nhất quán có nghĩa gì?

### Bài 17 — Writes after snapshot

Một row được commit sau khi dump snapshot bắt đầu có chắc xuất hiện trong archive không?

### Bài 18 — Multiple databases

pg_dumpall có tạo một snapshot xuyên tất cả databases không?

### Bài 19 — Parallel restore

Custom archive có thể restore với -j không? Parallel restore tác động những resources nào?

### Bài 20 — Single transaction

Vì sao --single-transaction không dùng chung với parallel restore?

### Bài 21 — --clean

--clean có tác động gì? Vì sao cần thận trọng?

### Bài 22 — --no-owner/--no-acl

Hai options này hữu ích trong tình huống nào?

### Bài 23 — Restore errors

Vì sao nên dùng --exit-on-error và kiểm tra logs/exit code?

### Bài 24 — Analyze

Vì sao cần ANALYZE sau restore?

### Bài 25 — Validation

Row count có đủ chứng minh migration đúng không? Nêu các validation bổ sung.

### Bài 26 — Security

Vì sao dump archive và globals.sql phải được bảo vệ như dữ liệu production?

### Bài 27 — Rollback

Vì sao rollback đơn giản nhất trước khi target nhận writes?

### Bài 28 — Low downtime

Làm thế nào kết hợp baseline dump với logical replication để giảm downtime? Những rủi ro nào phải xử lý?

### Bài 29 — Cutover

Nêu trình tự offline cutover an toàn.

### Bài 30 — Tổng hợp

Một restore kết thúc nhưng app role không truy cập được table, sequence có thể cấp trùng ID và extension function báo missing library. Hãy nêu thứ tự điều tra và điều kiện chưa được mở writes.

---

## 22. Lời giải — bài 1 đến 15

### Bài 1 — Logical dump

Dump/restore chuyển schema và dữ liệu ở dạng logic bằng SQL/archive. Physical backup sao chép data files/WAL theo cơ chế physical và có version/layout compatibility requirements khác.

### Bài 2 — pg_dump

pg_dump dump một database, toàn bộ hoặc chọn schema/table/object. Nó không tự dump roles/tablespaces toàn cluster; dùng pg_dumpall --globals-only hoặc provisioning riêng.

### Bài 3 — pg_dumpall

Globals dump gồm roles, memberships, tablespaces và các global definitions được công cụ hỗ trợ. Bảo vệ file vì nó có thể chứa password verifiers và metadata nhạy cảm.

### Bài 4 — pg_restore

pg_restore đọc custom, directory và tar archives do pg_dump tạo. Plain SQL script được restore bằng psql.

### Bài 5 — Plain format

Dùng psql để thực thi script. Plain SQL restore tuần tự và không có parallel restore mode của pg_restore.

### Bài 6 — Custom format

Custom format nén archive, có TOC để liệt kê/chọn objects và hỗ trợ parallel restore. Nó phù hợp khi cần một archive file linh hoạt.

### Bài 7 — Directory format

Directory format lưu objects/data thành nhiều file và hỗ trợ parallel dump cũng như parallel restore. Nó hữu ích cho database lớn, nhưng phải copy toàn bộ thư mục.

### Bài 8 — Tar format

Không. Tar format dùng pg_restore nhưng không hỗ trợ parallel restore như custom/directory.

### Bài 9 — Version compatibility

pg_dump client cần hiểu protocol/catalog của server. Client cũ không được thiết kế để đọc major version mới hơn; dùng client đủ mới theo compatibility rules.

### Bài 10 — Upgrade direction

Dump logic tách dữ liệu khỏi physical file format cũ và có thể restore vào server mới hơn nếu SQL/features/extensions tương thích. Downgrade về server cũ không được mặc định hỗ trợ.

### Bài 11 — Globals

Database objects có thể tham chiếu owner/roles và tablespaces. Tạo global objects trước giúp restore không gặp lỗi role/tablespace missing và giữ ownership đúng.

### Bài 12 — Tablespaces

CREATE TABLESPACE có thể fail vì path không tồn tại hoặc permissions sai; objects phụ thuộc tablespace sẽ không restore được. Tạo/remap path trước khi restore.

### Bài 13 — Extensions

Không. Dump có thể chứa CREATE EXTENSION/extension-owned SQL metadata, nhưng không mang shared library binaries. Cài package tương thích trên target trước restore.

### Bài 14 — Large objects

Xác nhận pg_dump có bao gồm large objects, không dùng option loại trừ, và kiểm tra references/OIDs. Sau restore, test đọc/ghi LO bằng application.

### Bài 15 — Sequence state

Archive/script có thể lưu sequence definitions và setval state. Xác nhận max keys, is_called, increment/cache và writes trong snapshot/cutover để next value không xung đột.

---

## 23. Lời giải — bài 16 đến 30

### Bài 16 — Snapshot

pg_dump dùng MVCC snapshot để nhìn thấy một trạng thái nhất quán của database tại thời điểm dump bắt đầu. Các commits sau snapshot không nhất thiết xuất hiện trong dump.

### Bài 17 — Writes after snapshot

Không. Một row commit sau khi snapshot bắt đầu có thể bị loại khỏi archive. Cần freeze writes trước snapshot hoặc đồng bộ delta sau baseline.

### Bài 18 — Multiple databases

Không. pg_dumpall dump từng database riêng, mỗi database có snapshot riêng; không có một transaction snapshot xuyên toàn cluster.

### Bài 19 — Parallel restore

Có. Custom archive có thể restore bằng pg_restore -j. Parallel jobs tăng connections, CPU, memory/index-build demand, storage I/O, WAL và checkpoint pressure.

### Bài 20 — Single transaction

Parallel restore chạy nhiều workers/transactions độc lập; single transaction yêu cầu một transaction duy nhất. Hai chế độ không tương thích, và single transaction có thể làm transaction rất lớn.

### Bài 21 — --clean

Nó drop objects trước khi tạo lại. Có thể xóa dữ liệu/objects hiện có và local-only objects nếu dùng sai. Chỉ dùng trên target đã xác nhận hoặc database lab.

### Bài 22 — --no-owner/--no-acl

Dùng khi target có role/ownership policy khác source hoặc roles được provision riêng. Sau restore phải gán owners/grants/default privileges theo policy target.

### Bài 23 — Restore errors

Không dừng ở lỗi có thể khiến archive chỉ được restore một phần. --exit-on-error giúp fail fast; logs và exit code cho biết command thành công hay thất bại. Cần xử lý mọi errors trước cutover.

### Bài 24 — Analyze

Restore không bảo đảm planner statistics phản ánh distribution mới. ANALYZE cập nhật statistics để planner chọn plans phù hợp và giảm query regression sau cutover.

### Bài 25 — Validation

Không. Row count không phát hiện type/constraint/ownership/function/sequence errors hoặc business semantics. Bổ sung aggregates, referential checks, duplicate checks, extension/function tests, permissions, sequences và application smoke/regression tests.

### Bài 26 — Security

Dump có thể chứa PII, credentials trong rows, password verifiers trong globals và business data. Giới hạn permissions, mã hóa, retention, checksum và restore access.

### Bài 27 — Rollback

Trước khi target nhận writes, source vẫn là write authority và có thể tiếp tục phục vụ ứng dụng. Sau target writes, source thiếu changes mới; rollback cần reverse sync hoặc reconciliation.

### Bài 28 — Low downtime

Dump baseline trong lúc source chạy, restore lên target rồi thiết lập logical replication/delta capture. Trước cutover, freeze writes, chờ apply tới final marker/LSN, kiểm tra sequence/DDL/schema/external state và chuyển traffic. Rủi ro gồm DDL drift, slot retention, apply lag, sequence state và conflict/rollback.

### Bài 29 — Cutover

Freeze writes/jobs; drain transactions; tạo final dump hoặc xác nhận delta complete; restore; validate schema/data/business rules; sync sequences; chuyển connection routing; smoke test; mở writes; monitor; giữ source fenced trong rollback window.

### Bài 30 — Tổng hợp

1. Giữ target read-only và chưa mở writes.
2. Kiểm tra role ownership, schema/table grants, sequence privileges và default privileges; test bằng app role.
3. Xác định sequence gắn với identity/serial, so max key, last_value/is_called, increment/cache và đồng bộ trước writes.
4. Cài extension package đúng target major version, kiểm tra control/library path và extension version; xác nhận function/type/operator hoạt động.
5. Chạy smoke tests bằng app role, kiểm tra data/business invariants và backup/monitoring.
6. Chỉ mở writes khi permissions, sequences, extensions và validation đều đạt. Nếu không sửa được trong window, rollback trước khi target nhận writes.

---

## 24. Checklist cutover cuối cùng

### Trước dump
- [ ] Đã kiểm tra source/target versions và client tools.
- [ ] Đã kiểm kê roles, tablespaces, extensions, locales và objects đặc biệt.
- [ ] Đã xác định write freeze hoặc delta sync strategy.
- [ ] Đã ước lượng archive, target disk, WAL và temporary space.
- [ ] Đã chạy restore rehearsal và xác nhận duration.

### Sau dump
- [ ] pg_dump exit code thành công.
- [ ] Archive/SQL script có thể đọc.
- [ ] TOC và checksum được lưu.
- [ ] Globals dump được bảo vệ.
- [ ] Archive được copy đầy đủ và checksum khớp.

### Sau restore
- [ ] Không còn restore errors chưa giải thích.
- [ ] Roles/tablespaces/ownership/ACL đúng.
- [ ] Extensions và large objects hoạt động.
- [ ] Tables, indexes, constraints và sequences hợp lệ.
- [ ] Row counts và business invariants đạt.
- [ ] ANALYZE đã chạy.
- [ ] App role và smoke tests thành công.

### Trước mở writes
- [ ] Không còn writes source sau final snapshot chưa chuyển.
- [ ] External state và background jobs đã sẵn sàng.
- [ ] Connection routing trỏ đúng target.
- [ ] Monitoring, alerting và backup target hoạt động.
- [ ] Rollback owner, window và decision criteria rõ.

---

## 25. Tài liệu tham khảo PostgreSQL

Ưu tiên tài liệu đúng major version của pg_dump/pg_restore và server:

- [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): formats, selection, snapshot và dump options.
- [PostgreSQL — pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html): cluster dump và globals.
- [PostgreSQL — pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html): archive restore, parallel jobs, clean/create/sections.
- [PostgreSQL — psql](https://www.postgresql.org/docs/current/app-psql.html): plain SQL restore và error handling.
- [PostgreSQL — CREATE DATABASE](https://www.postgresql.org/docs/current/sql-createdatabase.html): template, encoding và locale.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): ANALYZE và statistics.
- [PostgreSQL — Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html): các phương pháp major upgrade.

Các trang /current/ có thể trỏ tới major version mới nhất. Kiểm tra options, defaults và version compatibility theo client/server đang vận hành.

---

## 26. Tổng kết

Dump và restore là phương pháp logical migration linh hoạt cho PostgreSQL major upgrades, platform moves và database migrations có thể chấp nhận thời gian export/import. Nó yêu cầu chuẩn bị đầy đủ global objects, extension binaries, tablespaces, locale, permissions, sequence state và external dependencies.

Các nguyên tắc cần nhớ:

1. pg_dump dump một database; pg_dumpall có thể dump nhiều databases và global objects.
2. Plain SQL restore bằng psql; custom/directory/tar restore bằng pg_restore.
3. Directory format hỗ trợ parallel dump và restore; custom hỗ trợ parallel restore.
4. pg_dump client phải đủ mới để đọc source server; không giả định downgrade tương thích.
5. Restore roles/tablespaces và cài extensions trước khi restore database objects.
6. pg_dump snapshot nhất quán cho một database, nhưng không chứa writes sau snapshot.
7. pg_dumpall không tạo một snapshot xuyên tất cả databases.
8. Sequence state có thể nằm trong archive nhưng cần xác nhận next values trước cutover.
9. Dump không sao chép cluster configuration, external systems, replication slots và mọi secrets.
10. Parallel restore tăng CPU, memory, I/O, WAL và checkpoint pressure.
11. Dùng database target mới, kiểm tra logs/exit codes và không bỏ qua restore errors.
12. Chạy ANALYZE, kiểm tra permissions, constraints, indexes, extensions, large objects và business invariants.
13. Dump archive và globals phải được mã hóa, checksum và bảo vệ như production data.
14. Offline cutover cần freeze writes trước snapshot; low-downtime migration cần delta sync có thiết kế.
15. Sau target writes, rollback đòi hỏi reverse sync hoặc reconciliation; không chỉ đổi connection string.
16. Chỉ mở writes khi validation, sequence handoff, application smoke tests và rollback criteria đã đạt.

Quy trình tổng quát: **inventory → chọn format/version → dump globals và database → kiểm tra archive/checksum → provision target → restore → analyze/validate → freeze writes hoặc apply delta → sequence/external handoff → cutover → monitor và giữ rollback window**.
