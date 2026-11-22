# Phân biệt sao lưu logic, vật lý và snapshot lưu trữ trong PostgreSQL

## 1. Ba cách sao lưu giải quyết những bài toán khác nhau

Khi xây dựng chiến lược backup cho PostgreSQL, có ba cách thường được nhắc đến:

- **Sao lưu logic (logical backup):** xuất schema và dữ liệu thành biểu diễn logic như SQL hoặc archive của pg_dump.
- **Sao lưu vật lý (physical backup):** sao chép các file dữ liệu của PostgreSQL ở cấp cluster, thường bằng pg_basebackup hoặc công cụ backup vật lý tương thích.
- **Snapshot lưu trữ (storage snapshot):** chụp trạng thái của volume, filesystem hoặc block storage tại một thời điểm bằng tính năng của storage platform.

Ba cách này có thể bổ sung cho nhau, nhưng khác nhau về phạm vi, tính nhất quán, tốc độ restore, khả năng phục hồi đến một thời điểm, tính di động và mức độ chi tiết khi khôi phục.

Ví dụ:

- Bạn chỉ cần khôi phục một bảng bị xóa nhầm: logical backup thường thuận tiện hơn.
- Bạn cần dựng lại toàn bộ PostgreSQL cluster sau khi mất máy chủ: physical backup thường phù hợp hơn.
- Bạn cần tạo nhanh một bản sao volume để phục vụ kiểm thử hoặc disaster recovery: storage snapshot có thể hữu ích nếu được tạo theo quy trình bảo đảm consistency.
- Bạn cần khôi phục database về 10:32 sáng trước khi một transaction lỗi commit: cần base backup phù hợp và chuỗi WAL liên tục để thực hiện Point-in-Time Recovery (PITR).

Không có lựa chọn nào tự động đáp ứng tất cả các tình huống.

```text
                 PostgreSQL cluster
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
       Logical dump   Physical     Storage
       pg_dump        backup       snapshot
       pg_dumpall     pg_basebackup volume / filesystem
             |           |           |
             v           v           v
       SQL / archive  Data files   Block-level image
       of objects     + WAL        at a point in time
             |           |           |
             +-----------+-----------+
                         |
                         v
               Restore and verify
                         |
              +----------+----------+
              |          |          |
              v          v          v
            Object     Whole       Fast clone /
            recovery   cluster     storage recovery
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích logical backup, physical backup và storage snapshot khác nhau ở đâu.
2. Chọn loại backup theo phạm vi khôi phục và mục tiêu RPO/RTO.
3. Dùng pg_dump để sao lưu một database.
4. Phân biệt plain SQL, custom, directory và tar dump formats.
5. Dùng pg_restore để xem nội dung và khôi phục archive.
6. Dùng pg_dumpall để sao lưu nhiều databases và global objects.
7. Hiểu vì sao roles và tablespaces cần được bảo vệ riêng khi dùng pg_dump.
8. Giải thích transaction snapshot bảo đảm tính nhất quán của logical dump.
9. Dùng pg_basebackup để tạo physical base backup.
10. Phân biệt base backup với WAL archive.
11. Kết hợp base backup và WAL để thực hiện PITR.
12. Hiểu vì sao physical backup gắn với PostgreSQL major version và môi trường tương thích.
13. Giải thích storage snapshot copy-on-write và crash consistency.
14. Phân biệt crash-consistent, filesystem-consistent và application-consistent snapshots.
15. Xác định rủi ro khi PGDATA, tablespaces và WAL nằm trên nhiều volumes.
16. Hiểu vai trò của PostgreSQL backup API khi tạo snapshot online.
17. Phân biệt snapshot lưu trữ với MVCC snapshot và replication standby.
18. Thiết kế backup retention, encryption, offsite copy và immutable storage.
19. Kiểm tra backup bằng manifest, checksum và restore drills.
20. Lập chiến lược kết hợp logical, physical, WAL archive và storage snapshots.

## 3. Logical backup là gì?

Logical backup lưu cấu trúc và nội dung database dưới dạng các đối tượng logic: schema, tables, sequences, views, functions, constraints, indexes, data và các object được công cụ hỗ trợ.

Trong PostgreSQL, công cụ phổ biến là:

- `pg_dump`: sao lưu một database.
- `pg_dumpall`: sao lưu tất cả databases trong một cluster theo định dạng SQL text, đồng thời có thể xuất global objects.
- `pg_restore`: khôi phục các archive formats do pg_dump tạo.
- `psql`: thực thi plain SQL dump.

### 3.1. Logical dump không phải bản sao file database

Một dump có thể chứa câu lệnh tạo table và INSERT/COPY data, hoặc archive entries đại diện cho các object. Khi restore, PostgreSQL tạo lại objects trong một database đích.

Ví dụ, logical dump của một bảng không sao chép nguyên page layout, heap tuple headers, index pages hay transaction status files. PostgreSQL tái tạo dữ liệu và indexes từ biểu diễn logic.

### 3.2. Phạm vi của pg_dump

pg_dump làm việc trên một database tại một thời điểm. Nó không tự sao lưu các global objects của cluster như roles và tablespaces.

Nếu database dùng role riêng, ownership hoặc grants, cần bảo đảm các roles tương ứng tồn tại khi restore. Có thể dùng pg_dumpall --globals-only để xuất global definitions.

### 3.3. Logical backup phù hợp khi nào?

- Khôi phục một database hoặc một tập objects.
- Di chuyển dữ liệu giữa các PostgreSQL major versions theo hướng tương thích.
- Xuất một schema hoặc một số tables.
- Tạo bản dữ liệu phục vụ kiểm thử, staging hoặc data migration.
- Lưu bản dump có thể kiểm tra, lưu trữ và xử lý bằng công cụ khác.
- Phục hồi một table sau lỗi logic bằng cách restore vào database tạm rồi copy object cần thiết.

### 3.4. Những gì logical dump không tự bao gồm

Tùy lệnh và options, cần chú ý:

- Roles và tablespaces cấp cluster.
- File cấu hình PostgreSQL đặt ngoài data directory.
- TLS certificates, secrets, key material và credentials.
- Extension binaries/shared libraries của hệ điều hành.
- Cron jobs, scripts, external services và object storage.
- Dữ liệu bên ngoài database mà ứng dụng cần để hoạt động.

Backup database không đồng nghĩa backup toàn bộ hệ thống ứng dụng.

## 4. Tạo logical backup bằng pg_dump

### 4.1. Plain SQL format

```bash
pg_dump \
  --host=db.example.internal \
  --port=5432 \
  --username=backup_user \
  --format=plain \
  --file=appdb-2026-11-14.sql \
  appdb
```

Plain format tạo file SQL text, có thể xem và chạy bằng psql.

Khôi phục:

```bash
createdb --host=db-restore.internal --username=restore_admin appdb_restore

psql \
  --host=db-restore.internal \
  --username=restore_admin \
  --dbname=appdb_restore \
  --file=appdb-2026-11-14.sql
```

Ưu điểm:

- Có thể đọc nội dung SQL.
- Dễ xử lý bằng text tools ở mức phù hợp.
- Không cần pg_restore; dùng psql.

Hạn chế:

- File có thể lớn.
- Restore thường theo thứ tự script, khó tận dụng parallel restore như custom/directory archives.
- Chọn lọc object và điều khiển restore ít linh hoạt hơn archive formats.

### 4.2. Custom format

```bash
pg_dump \
  --host=db.example.internal \
  --username=backup_user \
  --format=custom \
  --file=appdb-2026-11-14.dump \
  appdb
```

Custom format (-Fc) là archive format phổ biến cho backup một database. Có thể nén theo cơ chế của pg_dump, liệt kê nội dung và chọn objects khi restore.

Xem danh sách archive entries:

```bash
pg_restore --list appdb-2026-11-14.dump
```

Restore:

```bash
createdb --host=db-restore.internal --username=restore_admin appdb_restore

pg_restore \
  --host=db-restore.internal \
  --username=restore_admin \
  --dbname=appdb_restore \
  --verbose \
  appdb-2026-11-14.dump
```

### 4.3. Directory format

```bash
pg_dump \
  --host=db.example.internal \
  --username=backup_user \
  --format=directory \
  --jobs=4 \
  --file=appdb-2026-11-14.dir \
  appdb
```

Directory format (-Fd) lưu archive thành nhiều file trong một directory và hỗ trợ parallel dump. Cần bảo vệ toàn bộ directory như một đơn vị backup; không chỉ copy một vài file bên trong.

### 4.4. Tar format

```bash
pg_dump \
  --host=db.example.internal \
  --username=backup_user \
  --format=tar \
  --file=appdb-2026-11-14.tar \
  appdb
```

Tar format tạo archive tar. Khả năng parallel restore và một số tính năng khác khác với custom/directory; xem tài liệu của phiên bản đang dùng.

### 4.5. So sánh các format

| Format | Cách restore | Parallel dump | Parallel restore | Điểm mạnh |
| --- | --- | --- | --- | --- |
| Plain (-Fp) | psql | Không | Không theo cơ chế pg_restore | SQL text, dễ kiểm tra |
| Custom (-Fc) | pg_restore | Không | Có | Linh hoạt, chọn object |
| Directory (-Fd) | pg_restore | Có | Có | Parallel dump/restore |
| Tar (-Ft) | pg_restore | Không | Hạn chế so với custom/directory | Archive tar |

Khả năng cụ thể phụ thuộc PostgreSQL version và options. Kiểm tra pg_dump --help và pg_restore --help của binary đang triển khai.

## 5. Khôi phục có chọn lọc bằng pg_restore

### 5.1. Xem nội dung trước khi restore

```bash
pg_restore --list appdb-2026-11-14.dump
```

Output là TOC (table of contents) của archive. Có thể lưu TOC ra file, chỉnh danh sách entries và dùng --use-list khi restore có chọn lọc.

### 5.2. Restore một schema

```bash
pg_restore \
  --dbname=appdb_restore \
  --schema=reporting \
  --verbose \
  appdb-2026-11-14.dump
```

### 5.3. Restore một table

```bash
pg_restore \
  --dbname=appdb_restore \
  --table=public.orders \
  --verbose \
  appdb-2026-11-14.dump
```

Restore chọn lọc có thể thiếu dependencies như types, functions, sequences hoặc referenced tables. Không mặc định rằng một table archive entry luôn tự chứa mọi object cần thiết để chạy ứng dụng.

### 5.4. Clean restore

`--clean` yêu cầu xóa objects trước khi tạo lại. Đây là option có thể phá dữ liệu trong database đích:

```bash
pg_restore \
  --clean \
  --if-exists \
  --dbname=appdb_restore \
  appdb-2026-11-14.dump
```

Chỉ chạy trong database đích đã được xác định rõ, thường là database restore riêng. Không dùng trên production database đang phục vụ ứng dụng nếu chưa có quy trình change/recovery được phê duyệt.

### 5.5. Ownership và privileges

Khi restore sang môi trường khác, có thể cần map ownership/privileges:

```bash
pg_restore \
  --no-owner \
  --no-acl \
  --dbname=appdb_restore \
  appdb-2026-11-14.dump
```

`--no-owner` và `--no-acl` thay đổi semantics của restore. Nếu cần bảo toàn quyền truy cập, phải tạo roles/grants tương ứng hoặc dùng cách restore phù hợp. Không bỏ qua security model chỉ để lệnh restore chạy thành công.

## 6. pg_dump và tính nhất quán của dữ liệu

### 6.1. Logical dump dùng consistent snapshot

pg_dump đọc database bằng một transaction snapshot nhất quán. Trong lúc dump, các transactions khác vẫn có thể tiếp tục đọc/ghi; dump phản ánh trạng thái dữ liệu theo snapshot mà nó sử dụng, thay vì trộn tùy tiện các thời điểm cho từng table.

### 6.2. Snapshot không có nghĩa DDL nào cũng an toàn đồng thời

pg_dump lấy locks cần thiết trên các objects. Một số DDL có thể xung đột với locks đó khiến dump thất bại. Cần phối hợp schema migrations và backup schedule.

### 6.3. Parallel dump

Directory format có thể dùng --jobs. Các worker cần dùng synchronized snapshot để xuất cùng một trạng thái logic. Hãy dùng đúng phiên bản client/server và bảo đảm quyền kết nối/đọc cần thiết.

### 6.4. Transaction snapshot không giữ database đứng yên

Dump không khóa toàn bộ database để ngăn mọi writes. Nó sử dụng MVCC snapshot; dữ liệu mới commit sau snapshot thường không xuất hiện trong dump đó.

### 6.5. Dump thành công không tự chứng minh restore thành công

File có thể tồn tại nhưng bị thiếu, corrupt, sai quyền, chứa object dependencies không được tạo hoặc không restore được vào target version. Phải thực hiện restore test.

## 7. Sao lưu global objects bằng pg_dumpall

### 7.1. Global objects là gì?

Một số objects thuộc phạm vi cluster, không thuộc riêng một database:

- Roles và role memberships.
- Tablespaces.
- Các thiết lập quyền/attributes của roles được hỗ trợ trong dump.

Nếu chỉ dùng pg_dump appdb, các objects này không được tự động mang theo.

### 7.2. Xuất global objects

```bash
pg_dumpall \
  --host=db.example.internal \
  --username=backup_admin \
  --globals-only \
  --file=cluster-globals.sql
```

Restore:

```bash
psql \
  --host=db-restore.internal \
  --username=postgres \
  --dbname=postgres \
  --file=cluster-globals.sql
```

Thực hiện trong môi trường restore có quyền phù hợp. Tablespaces có thể phụ thuộc đường dẫn filesystem, mount points và ownership trên máy đích.

### 7.3. Xuất toàn bộ cluster

```bash
pg_dumpall \
  --host=db.example.internal \
  --username=backup_admin \
  --file=all-databases.sql
```

pg_dumpall tạo SQL script cho các databases và global objects. Restore thường dùng psql với quyền cao phù hợp. Công cụ này không có archive format custom của pg_dump và không cung cấp cùng mức parallel restore.

### 7.4. Khi nào cần pg_dumpall?

- Muốn lưu roles/tablespaces riêng.
- Muốn tạo SQL script toàn cluster.
- Muốn kiểm kê và tái tạo global object definitions.

Một cách thực tế là lưu logical dump từng database cùng một bản globals dump được bảo vệ và kiểm thử.

## 8. Sao lưu vật lý là gì?

Physical backup sao chép các file vật lý mà PostgreSQL cần để mở lại một cluster: data files, control information, WAL cần thiết và các tablespace files liên quan.

Khác logical dump, physical backup giữ cấu trúc lưu trữ của PostgreSQL ở cấp cluster. Restore thường là đưa cluster về trạng thái có thể khởi động bằng một PostgreSQL installation tương thích.

### 8.1. Physical backup thường bao phủ cả cluster

Một physical base backup thường chứa tất cả databases trong cluster, cùng system catalogs, roles và database files. Nó không chọn một table đơn lẻ để restore trực tiếp.

### 8.2. Physical backup cần tương thích

Physical data directory gắn với PostgreSQL major version và các yêu cầu tương thích của platform/build. Không lấy data directory của PostgreSQL 15 rồi giả định PostgreSQL 16 có thể khởi động trực tiếp bằng nó.

Minor release trong cùng major thường có khả năng tương thích vật lý theo chính sách PostgreSQL, nhưng phải kiểm tra version, extension, OS/architecture, filesystem và quy trình vendor.

### 8.3. Physical backup phù hợp khi nào?

- Khôi phục toàn bộ cluster sau mất máy/volume.
- Dựng standby hoặc replica.
- Phục hồi nhanh dữ liệu lớn.
- Kết hợp WAL archive để PITR.
- Disaster recovery cần tái tạo trạng thái cluster.

### 8.4. Hạn chế

- Khôi phục một table riêng lẻ khó hơn: thường restore cluster/database tạm rồi dùng pg_dump/SQL để trích object.
- Không thuận tiện để di chuyển giữa major versions như logical dump.
- Phụ thuộc các file, tablespaces, WAL, extension binaries và môi trường tương thích.
- Backup directory cần được bảo vệ toàn vẹn; thiếu một phần có thể khiến cluster không khởi động.

## 9. Tạo physical base backup bằng pg_basebackup

pg_basebackup là công cụ PostgreSQL tạo base backup từ một server đang chạy thông qua replication protocol.

Ví dụ:

```bash
pg_basebackup \
  --host=db.example.internal \
  --port=5432 \
  --username=backup_user \
  --pgdata=/backups/pg-base-2026-11-14 \
  --format=plain \
  --wal-method=stream \
  --progress \
  --verbose
```

Các option tương ứng:

- --pgdata (-D): thư mục đích.
- --format=plain (-Fp): ghi cây file vật lý.
- --wal-method=stream (-X stream): stream WAL trong quá trình backup.
- --progress (-P): hiển thị tiến độ.
- --verbose (-v): tăng thông tin log.

### 9.1. Yêu cầu phía server

Tùy cách triển khai, cần:

- Role có quyền REPLICATION hoặc quyền phù hợp.
- Kết nối replication được cho phép trong pg_hba.conf.
- Đủ max_wal_senders.
- WAL settings và retention đủ để hoàn tất backup.
- Dung lượng destination và network throughput phù hợp.

Không dùng superuser làm credential backup nếu một role replication chuyên dụng đáp ứng yêu cầu.

### 9.2. WAL method

pg_basebackup cần bảo đảm backup có WAL cần thiết để đưa file data về trạng thái consistent. Các chế độ WAL method và default có thể khác theo version; đọc pg_basebackup --help trên client đang dùng.

-X stream stream WAL đồng thời với base backup, thường tránh phải chờ server giữ WAL đến cuối lần copy. Nó không thay thế WAL archiving dài hạn cho PITR.

### 9.3. Directory hoặc tar output

pg_basebackup có thể tạo plain directory hoặc tar output theo options/version. Tar format có thể phù hợp vận chuyển, nhưng restore phải giải nén đúng cấu trúc và xử lý tablespaces đúng cách.

### 9.4. Option -R

-R/--write-recovery-conf tạo cấu hình cần thiết để backup được dùng như standby, bao gồm signal/configuration phù hợp. Chỉ dùng khi mục tiêu là dựng standby. Một base backup dùng để restore primary độc lập không nên vô tình mang cấu hình kết nối replica không mong muốn.

## 10. Base backup khác WAL archive

Base backup là điểm khởi đầu để khôi phục cluster. WAL archive chứa chuỗi thay đổi phát sinh sau hoặc trong khoảng thời gian liên quan đến base backup.

### 10.1. WAL là gì?

Write-Ahead Log lưu các thay đổi database theo quy tắc write-ahead. PostgreSQL dùng WAL để crash recovery và replication. Nếu có đủ WAL liên tục từ điểm base backup cần thiết đến target recovery point, có thể replay thay đổi để tiến cluster đến thời điểm mong muốn.

### 10.2. WAL archive

Cấu hình archiving thường gồm:

- archive_mode bật theo yêu cầu.
- archive_command hoặc archive_library theo version/platform.
- Destination độc lập với storage chính.
- Kiểm tra archive failures, backlog và dung lượng.
- Retention không xóa WAL còn cần cho base backups hoặc standby.

Ví dụ cấu hình minh họa:

```conf
archive_mode = on
archive_command = 'archive-tool publish "%p" "%f"'
```

archive-tool là placeholder của công cụ triển khai. Command thực tế phải lưu WAL segment bền vững và chỉ trả success khi archive đã được publish đúng. Không dùng chuỗi ví dụ này như command chạy trực tiếp.

### 10.3. WAL archive không phải bản backup độc lập

Chỉ có WAL mà không có base backup phù hợp thì không đủ để dựng lại cluster từ đầu. Ngược lại, base backup mà thiếu WAL cần thiết có thể không restore được đến consistency point hoặc recovery target.

### 10.4. Giữ chuỗi WAL liên tục

Một segment bị mất có thể làm PITR không thể tiến qua khoảng thời gian cần thiết. Monitoring archive cần phát hiện gaps, failed uploads và WAL backlog.

## 11. Point-in-Time Recovery (PITR)

PITR cho phép khôi phục cluster về một điểm trong lịch sử, chẳng hạn ngay trước khi người dùng chạy nhầm lệnh DELETE.

Cần có:

1. Một base backup hợp lệ.
2. WAL liên tục từ điểm base backup cần thiết đến recovery target.
3. Cấu hình restore để PostgreSQL đọc WAL archive.
4. Recovery target được xác định chính xác.
5. Quy trình promotion/validation sau replay.

### 11.1. Ý tưởng recovery

```text
Base backup at T0
      |
      v
Restore data directory
      |
      v
Read archived WAL segments
      |
      v
Replay transactions in order
      |
      +---- Stop at target time / LSN / XID
      |
      v
Promote recovered cluster
      |
      v
Validate application data
```

### 11.2. Recovery configuration

Ví dụ cho các PostgreSQL versions dùng recovery signal file:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_time = '2026-11-14 10:32:00+07'
recovery_target_action = 'pause'
```

Tạo recovery.signal trong data directory khi chuẩn bị PITR theo procedure của version. Các recovery settings và file semantics thay đổi qua các major versions; dùng tài liệu tương ứng.

### 11.3. Target time cần timezone rõ

Nếu dùng recovery_target_time, xác định timezone và timestamp chính xác. Đồng bộ clock của hệ thống, log và ứng dụng giúp điều tra. Có thể chọn target theo LSN hoặc transaction marker trong các tình huống cần độ chính xác cao hơn.

### 11.4. PITR không tự chọn đúng business state

PostgreSQL có thể dừng replay ở target time, nhưng DBA vẫn cần kiểm tra dữ liệu và xác định target đó thực sự nằm trước transaction lỗi. Recovery có thể bao gồm các transaction khác đã commit trước thời điểm đó.

### 11.5. PITR tạo một cluster được phục hồi

Thường restore vào môi trường tách biệt, kiểm tra dữ liệu, sau đó quyết định cách đưa dữ liệu trở lại production. Không tự động ghi đè cluster hiện hành ngay khi recovery hoàn tất.

## 12. Storage snapshot là gì?

Storage snapshot là ảnh chụp trạng thái volume, filesystem hoặc block device tại một thời điểm do storage layer cung cấp.

Ví dụ nền tảng:

- LVM snapshots.
- ZFS snapshots.
- SAN/storage-array snapshots.
- Cloud block-volume snapshots.
- VM disk snapshots.
- Storage systems có copy-on-write hoặc redirect-on-write.

### 12.1. Copy-on-write

Một số snapshot systems không sao chép toàn bộ dữ liệu ngay lập tức. Chúng giữ metadata/blocks tham chiếu đến trạng thái ban đầu, sau đó ghi nhận các blocks thay đổi theo thời gian.

Điều này giúp tạo snapshot nhanh và tiết kiệm dung lượng ban đầu. Khi dữ liệu thay đổi nhiều hoặc snapshot giữ lâu, chi phí storage có thể tăng.

### 12.2. Snapshot không phải logical dump

Snapshot ghi trạng thái storage blocks. Nó không hiểu table, schema, role, SQL object hay business meaning. Muốn khôi phục một table từ snapshot thường phải khôi phục volume/cluster vào môi trường tạm, rồi dùng SQL/logical tools để trích dữ liệu.

### 12.3. Snapshot không tự động là backup độc lập

Nếu snapshot vẫn nằm trong cùng storage account, region, credentials hoặc failure domain với dữ liệu gốc, một sự cố lớn hoặc tài khoản bị xâm nhập có thể ảnh hưởng cả hai.

Cần copy/replicate snapshot tới failure domain khác và có retention/immutability phù hợp.

### 12.4. Snapshot không tự động cung cấp PITR

Một snapshot đơn lẻ đại diện một điểm thời gian. Muốn phục hồi đến thời điểm nằm giữa hai snapshots, cần WAL archive hoặc một cơ chế incremental/time-based khác có khả năng replay.

## 13. Tính nhất quán của storage snapshot

Đây là điểm quan trọng nhất khi dùng snapshot với PostgreSQL.

### 13.1. Crash-consistent snapshot

Crash-consistent snapshot phản ánh trạng thái storage tương tự như máy chủ mất điện đột ngột tại một thời điểm. Nếu snapshot bao gồm đầy đủ các file cần thiết và các volumes được chụp nhất quán, PostgreSQL có thể dùng WAL để crash recovery khi khởi động.

Tuy nhiên, crash-consistent phụ thuộc storage provider và cách snapshot được phối hợp. Một snapshot riêng lẻ của volume data không đảm bảo các WAL/tablespace volumes khác ở cùng thời điểm.

### 13.2. Filesystem-consistent snapshot

Filesystem-consistent có nghĩa filesystem metadata và writes được flush/đồng bộ theo semantics của filesystem/snapshot tool. Điều này giúp giảm rủi ro filesystem-level inconsistency, nhưng không tự chứng minh mọi file PostgreSQL trên nhiều volumes thuộc cùng một database point-in-time.

### 13.3. Application-consistent snapshot

Application-consistent snapshot được phối hợp với ứng dụng/database để đạt trạng thái nhất quán theo quy trình của ứng dụng. Với PostgreSQL online file-system backup, cần sử dụng backup procedure/API phù hợp major version và bảo đảm WAL cần thiết được lưu.

### 13.4. PostgreSQL có thể crash-recover không có nghĩa snapshot đã sẵn sàng cho PITR

Một snapshot crash-consistent có thể giúp cluster khởi động sau crash. PITR yêu cầu base backup và chuỗi WAL cần thiết, cùng metadata backup tương ứng. Không đồng nhất hai mục tiêu này.

### 13.5. Snapshot đồng thời nhiều volumes

Nếu PostgreSQL dùng:

- PGDATA trên volume A.
- Tablespaces trên volume B.
- WAL/pg_wal trên volume C.

thì cần snapshot group/consistency group bảo đảm các volumes đại diện cùng một thời điểm. Chụp volume A lúc 10:00, B lúc 10:02 và C lúc 10:05 có thể tạo một tập file không cùng trạng thái.

### 13.6. Không chỉ snapshot PGDATA

Tablespaces có thể nằm ngoài PGDATA. Cần xác định tất cả tablespace paths, WAL location, external configuration và các dependencies. Snapshot thiếu một phần có thể làm cluster không khởi động hoặc mất objects.

## 14. Dùng PostgreSQL backup API với snapshot online

Nếu storage snapshot được tạo trong khi PostgreSQL đang chạy, cần theo đúng quy trình backup filesystem của PostgreSQL major version.

PostgreSQL cung cấp backup API để báo cho server biết một physical backup đang diễn ra và xác định lúc backup hoàn tất. Tên hàm và semantics có khác biệt giữa các major versions; các bản mới dùng pg_backup_start/pg_backup_stop, trong khi các phiên bản cũ có API tên pg_start_backup/pg_stop_backup.

### 14.1. Quy trình ở mức khái niệm

1. Kiểm tra storage và backup procedure hỗ trợ online snapshot.
2. Bắt đầu backup mode bằng API phù hợp phiên bản.
3. Tạo snapshot nhất quán của toàn bộ volumes liên quan.
4. Kết thúc backup mode theo procedure.
5. Lưu các metadata/backup label/tablespace map mà API trả về nếu quy trình yêu cầu.
6. Bảo đảm WAL cần thiết được archive và giữ lại.
7. Tạo manifest ghi snapshot ID, thời gian, volume mapping, database version và WAL range.
8. Restore thử snapshot trên môi trường tách biệt.

Không tự viết một script snapshot online chỉ dựa trên lệnh tạo snapshot của cloud provider mà bỏ qua PostgreSQL backup semantics.

### 14.2. pg_basebackup thường an toàn hơn cho trường hợp phổ thông

pg_basebackup đã xử lý giao thức physical backup và WAL cần thiết theo cách PostgreSQL hỗ trợ. Nếu không có yêu cầu đặc thù về storage snapshot, đây thường là điểm bắt đầu dễ kiểm soát hơn.

### 14.3. Snapshot khi database đã dừng sạch

Một phương án khác là:

1. Dừng PostgreSQL bằng shutdown sạch.
2. Xác minh server đã dừng.
3. Snapshot tất cả volumes và tablespaces.
4. Ghi nhận cấu hình, version và snapshot metadata.
5. Khởi động lại server sau khi snapshot hoàn tất.

Khi database được shutdown sạch và tất cả file được snapshot đầy đủ, snapshot có thể đóng vai trò physical copy. Đổi lại, phải chấp nhận downtime và phối hợp mọi thành phần liên quan.

### 14.4. Không snapshot filesystem đang copy dở theo cách tùy tiện

Tự copy từng file trong PGDATA khi server đang chạy mà không dùng một backup method được hỗ trợ có thể tạo bản sao không nhất quán. Không coi Copy-Item, cp -r hoặc file sync thông thường là physical backup online.

## 15. So sánh logical, physical và snapshot

| Tiêu chí | Logical backup | Physical backup | Storage snapshot |
| --- | --- | --- | --- |
| Mức dữ liệu | Objects và rows | Cluster data files | Storage blocks/volumes |
| Công cụ PostgreSQL | pg_dump, pg_dumpall | pg_basebackup, backup tools | Storage provider/tool |
| Phạm vi | Một DB hoặc object subset | Thường toàn cluster | Volume/snapshot group |
| Restore một table | Thuận tiện hơn | Thường cần restore cluster tạm | Thường cần restore volume tạm |
| Restore toàn cluster | Tạo lại objects qua SQL/archive | Phù hợp | Phù hợp nếu consistent/complete |
| PITR | Không tự có từ dump đơn lẻ | Có khi kết hợp WAL | Cần WAL hoặc snapshot chain |
| Cross-major migration | Thường linh hoạt hơn | Không restore trực tiếp qua major | Không restore trực tiếp qua major |
| Thời gian tạo | Phụ thuộc scan/serialize data | Phụ thuộc copy volume/data | Có thể rất nhanh |
| Thời gian restore | Có thể dài do recreate objects/indexes | Thường nhanh hơn với dataset lớn | Có thể nhanh nếu attach/clone nhanh |
| Portability | Tốt hơn ở mức logic | Phụ thuộc version/platform | Phụ thuộc storage platform |
| Kiểm tra nội dung | Có thể đọc plain SQL/TOC | Manifest/file validation | Provider metadata/checksum |
| Dependencies | Roles/extensions/config cần chuẩn bị | Binary/extensions/config tương thích | Volume mapping, WAL, config, backup procedure |

Không nên suy ra một tốc độ restore cố định từ bảng trên. Dataset, indexes, compression, network, storage throughput, PostgreSQL version và parallelism đều ảnh hưởng kết quả.

## 16. Phân biệt snapshot lưu trữ với MVCC snapshot

Hai thuật ngữ có chữ snapshot nhưng chỉ hai cơ chế khác nhau.

### 16.1. MVCC snapshot

MVCC snapshot là thông tin transaction visibility dùng để xác định transaction nào đã commit và tuple versions nào có thể nhìn thấy. pg_dump dùng snapshot logic để đọc dữ liệu nhất quán.

### 16.2. Storage snapshot

Storage snapshot là trạng thái block/volume tại một thời điểm do storage system ghi nhận. Nó không hiểu transaction visibility hoặc schema.

### 16.3. Ví dụ

Giả sử một transaction chuyển 100 triệu đồng từ tài khoản A sang B:

1. UPDATE số dư A.
2. UPDATE số dư B.
3. COMMIT.

Một logical dump đọc bằng consistent MVCC snapshot sẽ thấy trạng thái trước hoặc sau transaction theo snapshot visibility.

Một storage snapshot cần đại diện nhất quán toàn bộ storage state. Nếu snapshot không đồng bộ giữa các volumes hoặc được chụp trong trạng thái không được hỗ trợ, cần WAL recovery và backup procedure để đưa cluster về trạng thái hợp lệ.

### 16.4. Snapshot không phải khóa database

Tạo storage snapshot thường không có nghĩa PostgreSQL dừng ghi. Copy-on-write snapshot có thể tiếp tục tồn tại trong khi database tiếp tục thay đổi. Cần hiểu semantics của provider và consistency group.

## 17. Logical backup và physical backup trong migration

### 17.1. Logical dump cho migration

Logical dump có thể hữu ích khi chuyển sang PostgreSQL major version mới hơn hoặc một server/platform khác, miễn là object definitions, extensions và data types tương thích.

Quy trình tổng quát:

1. Tạo target cluster.
2. Cài extensions cần thiết ở version tương thích.
3. Tạo roles/tablespaces hoặc map ownership.
4. Restore schema/data.
5. Chạy analyze và kiểm tra constraints/indexes.
6. Validate counts/checksums/business aggregates.
7. Chuyển ứng dụng theo cutover plan.

### 17.2. Physical backup cho migration

Physical backup thường phục vụ recovery/replication trong môi trường tương thích cùng major version. Không dùng copy data directory làm phương pháp upgrade major version.

### 17.3. pg_upgrade

Khi cần nâng major version và muốn giữ dữ liệu vật lý, pg_upgrade là công cụ riêng với prechecks và procedure cụ thể. Nó không đơn giản là restore physical backup của major cũ bằng server major mới.

### 17.4. Extensions và collation

Logical dump không mang theo binary extension libraries. Physical backup cũng không tự mang theo mọi dependency của operating system. Restore/migration cần chuẩn bị đúng extension packages, locale/collation và runtime dependencies.

## 18. Backup strategy: full, incremental và differential

Các thuật ngữ này mô tả lượng dữ liệu được lưu so với baseline.

- **Full backup:** bản backup đầy đủ theo scope.
- **Incremental backup:** chỉ lưu thay đổi kể từ một backup trước đó.
- **Differential backup:** lưu thay đổi kể từ full backup gần nhất.

### 18.1. Logical dump

pg_dump thường tạo một logical dump đầy đủ cho scope được chọn. Nó không tự cung cấp một chuỗi incremental logical backup tổng quát chỉ bằng cách chạy lại dump và so sánh files.

Có thể xây pipeline delta/export riêng, nhưng phải tự định nghĩa identity, deletes, ordering, consistency và reconciliation.

### 18.2. Physical incremental

Khả năng incremental physical backup phụ thuộc phiên bản PostgreSQL và công cụ. Một số PostgreSQL versions/công cụ mới có hỗ trợ incremental backup và utility để kết hợp backup. Không giả định option tồn tại trên mọi server; kiểm tra version và pg_basebackup --help/tài liệu tương ứng.

### 18.3. Snapshot incremental

Storage provider có thể lưu snapshots theo cơ chế incremental/copy-on-write. Đây là semantics của storage layer; nó không thay thế backup consistency và WAL requirements của PostgreSQL.

### 18.4. Incremental chain

Restore incremental backup có thể cần full base và các incremental layers theo đúng thứ tự. Nếu một layer bị mất hoặc corrupt, những snapshots sau có thể không dùng được. Manifest phải ghi dependency chain và retention.

## 19. RPO và RTO quyết định thiết kế backup

### 19.1. RPO (Recovery Point Objective)

RPO là mức mất dữ liệu tối đa tổ chức chấp nhận đo theo thời gian.

Ví dụ:

- RPO 24 giờ: backup hằng ngày có thể đáp ứng nếu lịch và quy trình phù hợp.
- RPO 5 phút: cần WAL archiving/replication hoặc cơ chế khác có độ trễ thấp; dump hằng ngày không đáp ứng.

### 19.2. RTO (Recovery Time Objective)

RTO là thời gian tối đa chấp nhận để khôi phục dịch vụ.

Ví dụ:

- Logical restore một database rất lớn có thể mất nhiều giờ do recreate indexes/objects.
- Physical restore hoặc attach snapshot có thể rút ngắn thời gian dựng cluster, nhưng vẫn cần recovery, validation và cutover.
- Một standby sẵn sàng có thể giảm thời gian failover, nhưng không thay thế backup.

### 19.3. Bảng chọn theo mục tiêu

| Mục tiêu | Phương án thường phù hợp |
| --- | --- |
| Khôi phục một table | Logical dump/restore vào DB tạm |
| Khôi phục toàn cluster nhanh | Physical base backup hoặc snapshot đã kiểm chứng |
| PITR theo phút/giây | Base backup + WAL archive liên tục |
| Migration major version | Logical migration hoặc pg_upgrade |
| Clone nhanh cho test | Storage snapshot hoặc physical clone phù hợp |
| Bảo vệ khỏi logical corruption | Backup độc lập, giữ nhiều recovery points, PITR |
| Khôi phục role/global definitions | pg_dumpall --globals-only hoặc physical cluster backup |

### 19.4. Tính cả thời gian kiểm tra

RTO không kết thúc khi PostgreSQL process vừa start. Cần tính thời gian xác minh recovery, kiểm tra application, DNS/traffic cutover, cache warmup và thông báo vận hành.

## 20. Replication không phải backup

Một standby có thể giúp high availability, nhưng không thay thế backup.

### 20.1. Logical corruption có thể replicate

Nếu ứng dụng chạy nhầm DELETE FROM orders, thay đổi có thể được replicate sang standby. Nếu chỉ có primary và standby, cả hai có thể cùng mất dữ liệu logic.

### 20.2. Backup giữ recovery points cũ

Một backup độc lập hoặc WAL archive cho phép khôi phục về thời điểm trước thao tác lỗi, nếu retention còn đủ.

### 20.3. Standby và backup có vai trò khác nhau

| Cơ chế | Mục tiêu chính |
| --- | --- |
| Streaming replication | HA, read scaling, replica |
| Logical replication | Data movement, integration, selective replication |
| Physical base backup | Tạo cluster copy để restore/standby |
| WAL archive | PITR và recovery |
| Logical dump | Object-level backup/migration |
| Storage snapshot | Storage-level clone/recovery |

### 20.4. Replication slot có thể giữ WAL nhưng không phải archive strategy

Slot giúp giữ WAL cho consumer, nhưng nếu consumer chậm hoặc mất, storage có thể đầy. WAL archive cần retention, monitoring và backup policy riêng.

## 21. Mã hóa và bảo vệ backup

Backup thường chứa toàn bộ dữ liệu nhạy cảm của production. Cần bảo vệ như production data.

### 21.1. Encryption in transit

Dùng TLS cho kết nối backup client tới PostgreSQL và cho upload tới remote storage. Xác minh certificate/hostname theo chính sách.

### 21.2. Encryption at rest

Mã hóa file dump, backup repository, volumes và snapshots. Nếu công cụ không hỗ trợ encryption trực tiếp, dùng pipeline mã hóa trước khi upload và kiểm soát plaintext staging.

### 21.3. Key management

Giữ encryption keys tách biệt khỏi backup data. Có quy trình key rotation, recovery key escrow và kiểm thử khả năng giải mã sau nhiều năm.

### 21.4. Credentials

Không đặt password trực tiếp trong shell command hoặc log. Dùng .pgpass, secret manager hoặc cơ chế credential phù hợp, với file permissions chặt chẽ.

### 21.5. Access control

Giới hạn ai có thể:

- Tạo backup.
- Đọc/restore backup.
- Xóa backup.
- Xóa snapshots.
- Sửa retention/immutability.
- Truy cập encryption keys.

Tách quyền backup writer và backup deleter giúp giảm nguy cơ ransomware/xóa nhầm.

## 22. Retention, offsite và immutable copies

### 22.1. Retention policy

Định nghĩa số bản giữ theo loại:

- Daily backups.
- Weekly/monthly backups.
- Base backup retention.
- WAL retention liên quan đến base backup.
- Snapshot retention.
- Logical export retention.
- Incident hold/legal retention.

Không xóa WAL chỉ dựa trên tuổi segment nếu một base backup còn cần chuỗi WAL đó cho recovery.

### 22.2. Offsite copy

Giữ ít nhất một bản sao ngoài failure domain chính: account, region, storage system hoặc datacenter khác tùy threat model.

### 22.3. Immutable backup

Object lock/WORM/immutability có thể ngăn backup bị xóa hoặc sửa trong retention period. Cấu hình quyền quản trị và retention để một credential production bị xâm nhập không thể xóa tất cả recovery points.

### 22.4. 3-2-1 như nguyên tắc tham khảo

Một nguyên tắc phổ biến là giữ nhiều bản sao, trên nhiều loại storage và có ít nhất một bản offsite. Điều quan trọng là các copies không cùng chịu một failure mode và restore đã được thử.

### 22.5. Snapshot cùng storage account có giới hạn

Snapshot nhanh và tiện, nhưng nếu production credential có quyền xóa cả volume và snapshots, nó không đủ làm bản backup chống ransomware. Replicate/export snapshot ra miền bảo vệ khác và khóa retention.

## 23. Manifest và metadata cho mỗi backup

Một backup có ích phải có metadata để biết nó là gì và restore thế nào.

Manifest nên ghi:

| Field | Ví dụ/nội dung |
| --- | --- |
| backup_id | UUID hoặc stable identifier |
| backup_type | logical, physical, snapshot |
| source_cluster | Tên/ID cluster |
| database_version | PostgreSQL major/minor version |
| start_time / end_time | Thời gian backup |
| consistency_method | MVCC dump, base backup, backup API, clean shutdown |
| scope | Database, cluster, tablespaces, volumes |
| backup_format | plain/custom/directory/tar/physical |
| wal_start / wal_end | WAL range nếu áp dụng |
| snapshot_ids | ID của storage snapshots |
| tablespace_map | Tablespace locations/mapping |
| checksum | Digest/manifest checksum |
| encryption_key_ref | Reference tới key, không lưu secret |
| storage_uri | Vị trí lưu backup |
| retention_until | Thời điểm hết retention |
| tool_version | pg_dump/pg_basebackup/backup tool version |
| restore_test_id | Lần restore drill đã kiểm chứng |

### 23.1. Metadata phải đi cùng backup

Không lưu manifest duy nhất trên cùng volume dễ mất cùng backup. Giữ bản metadata trong backup catalog/remote storage độc lập.

### 23.2. Ghi rõ consistency contract

Một snapshot manifest cần nói rõ crash-consistent hay application-consistent, có dùng backup API không, volumes nào được chụp cùng lúc và WAL nào cần thiết.

### 23.3. Không ghi credentials vào manifest

Chỉ ghi secret reference hoặc key identifier. Manifest có thể được nhiều operator đọc để tìm backup.

## 24. Kiểm tra tính toàn vẹn của backup

### 24.1. Checksum

Tính checksum file dump hoặc backup objects sau khi upload. Khi download/restore, xác minh lại checksum.

Checksum phát hiện thay đổi byte, nhưng không chứng minh backup có thể khởi động hoặc ứng dụng có dữ liệu đúng.

### 24.2. pg_verifybackup

Với base backup có backup manifest được tạo bởi PostgreSQL versions hỗ trợ, pg_verifybackup có thể kiểm tra file list và checksums theo manifest:

```bash
pg_verifybackup /backups/pg-base-2026-11-14
```

Công cụ và khả năng hỗ trợ phụ thuộc version/format. Nó không thay thế một lần khởi động/recovery thử và không kiểm tra business semantics.

### 24.3. Logical archive listing

```bash
pg_restore --list appdb-2026-11-14.dump
```

Liệt kê archive entries là một kiểm tra hữu ích, nhưng chưa chứng minh restore toàn bộ thành công.

### 24.4. Kiểm tra object storage

Xác minh:

- File/object count.
- Total size.
- Checksum sau upload.
- Multipart upload đã complete.
- Snapshot state đã completed.
- Replication/copy status.
- Retention/immutability policy.
- Quyền đọc và giải mã.

### 24.5. Không chỉ kiểm tra exit code

Lệnh backup có exit code 0 là tín hiệu tốt, nhưng cần kiểm tra artifact, manifest, checksum và restoreability.

## 25. Restore drill: bằng chứng backup có thể dùng

Backup chỉ thực sự đáng tin khi đã được restore thử.

### 25.1. Logical restore drill

1. Chọn một dump từ retention.
2. Tạo database đích tạm.
3. Tạo roles/extensions cần thiết.
4. Restore bằng psql hoặc pg_restore.
5. Kiểm tra schema, constraints, indexes và object counts.
6. Chạy smoke tests/business queries.
7. Ghi runtime, lỗi và kết quả vào restore report.

### 25.2. Physical restore drill

1. Chọn base backup đã được xác minh.
2. Tạo môi trường PostgreSQL cùng major version tương thích.
3. Khôi phục data directory và tablespaces.
4. Cấu hình WAL recovery/archive nếu cần.
5. Khởi động cluster và theo dõi recovery logs.
6. Xác minh databases, roles, extensions và application connectivity.
7. Đo thời gian đạt trạng thái phục vụ được.

### 25.3. Snapshot restore drill

1. Chọn snapshot và manifest.
2. Clone/attach snapshot vào môi trường tách biệt.
3. Gắn đầy đủ các volumes/tablespaces.
4. Cung cấp WAL/archive/configuration cần thiết.
5. Khởi động PostgreSQL theo consistency method của snapshot.
6. Kiểm tra recovery, objects và dữ liệu.
7. Đo thời gian attach, replay WAL và validation.

### 25.4. Restore drill phải có lịch

Thực hiện định kỳ, ví dụ hàng tháng hoặc theo mức criticality. Sau khi thay đổi PostgreSQL version, backup tooling, encryption keys, storage provider hoặc retention policy, cần diễn tập lại.

### 25.5. Test phải cô lập

Restore backup production vào network/environment kiểm thử có access controls. Không vô tình cho application test gửi email, thanh toán, webhook hoặc kết nối dịch vụ production bằng dữ liệu đã restore.

## 26. Kiểm tra dữ liệu sau restore

Không chỉ xác nhận PostgreSQL process đã start.

### 26.1. Structural checks

- Databases có tồn tại?
- Schemas/tables/views/sequences có đầy đủ?
- Constraints/indexes có được tạo?
- Extensions có đúng version?
- Roles và grants có phù hợp?
- Tablespaces có mapping đúng?

### 26.2. Data checks

- Row counts theo bảng quan trọng.
- Min/max IDs hoặc timestamps.
- Business aggregates.
- Key uniqueness và referential integrity.
- Checksum/partition checks nếu có.
- Các transaction gần recovery target có đúng semantics?

### 26.3. Application checks

- Ứng dụng kết nối được?
- Authentication/authorization đúng?
- Read/write smoke tests thành công?
- Background jobs có đang bị bật nhầm?
- External integrations đã được cách ly?
- Query plans và performance ở mức chấp nhận?

### 26.4. Recovery target checks

Với PITR, kiểm tra target timestamp/LSN thực tế trong recovery logs và xác nhận trạng thái cuối trước khi promote/cutover.

## 27. Backup cho bảng lớn và database lớn

### 27.1. Logical dump

Logical dump có thể tốn thời gian serialize data, truyền qua network, nén và recreate indexes khi restore. Dùng directory format/parallelism khi phù hợp; đo resource impact.

### 27.2. Physical backup

Physical backup thường copy pages/files và có thể phù hợp hơn cho dataset rất lớn. Tuy nhiên, network throughput, WAL volume và storage performance vẫn là giới hạn.

### 27.3. Snapshot

Snapshot có thể được tạo nhanh vì storage layer dùng metadata/COW, nhưng snapshot creation time không bằng restore time. Clone lớn có thể bị ảnh hưởng bởi lazy loading, copy-on-read, network attach hoặc performance tier.

### 27.4. Compression trade-off

Compression giảm storage/network nhưng tiêu thụ CPU và có thể làm backup/restore chậm hơn nếu CPU bottleneck. Đo cả hai chiều, không chỉ file size.

### 27.5. Parallelism trade-off

Nhiều workers tăng throughput khi storage/network còn headroom; quá nhiều workers gây contention với production workload. Thiết lập concurrency theo benchmark và SLA.

## 28. Backup khi dùng tablespaces và external configuration

### 28.1. Tablespaces

Tablespace có thể nằm ngoài PGDATA. Physical backup/snapshot phải bao gồm chúng hoặc có mapping đúng. Logical dump cần tạo tablespace/đường dẫn phù hợp nếu muốn giữ definitions.

### 28.2. Symbolic links và mount points

Data directory có thể dùng symlinks/mount points. Backup tooling cần hiểu chúng và preserve/restore đúng target. Snapshot một mount mà bỏ volume thực tế sẽ không bảo vệ dữ liệu.

### 28.3. Configuration files

Một số file cấu hình nằm ngoài PGDATA hoặc được quản lý bởi configuration management. Lưu riêng:

- postgresql.conf và include files.
- pg_hba.conf.
- pg_ident.conf.
- Service/unit configuration.
- TLS certificates.
- Environment variables/secret references.
- Archive/restore scripts.

### 28.4. Extension binaries

Physical data files có thể chứa objects của extension nhưng không chứa shared library trên máy chủ. Restore cần cài extension package tương thích trước khi truy cập các objects đó.

### 28.5. Locale và collation

Restore/migration cần xét OS locale/collation provider và version. Thay đổi collation có thể ảnh hưởng index ordering; theo version cần reindex hoặc refresh collation version theo procedure phù hợp.

## 29. Chiến lược backup kết hợp

Một thiết kế production thường kết hợp nhiều cơ chế.

Ví dụ minh họa cho ứng dụng cần RPO nhỏ và có khả năng restore object-level:

```text
             Production PostgreSQL
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
       pg_dump     Base backup   WAL archive
       daily       weekly        continuous
          |           |           |
          v           v           v
       Object      Full cluster  PITR chain
       recovery    restore       to target time
          |           |           |
          +-----------+-----------+
                      |
                      v
             Offsite immutable storage
                      |
                      v
               Scheduled restore drills

          Optional storage snapshots
          for rapid clone / volume recovery
```

### 29.1. Logical backup thường xuyên

Lưu logical dump theo database quan trọng để có thể restore table/schema hoặc migration.

### 29.2. Physical base backup

Tạo base backup theo lịch phù hợp với RTO, kích thước dữ liệu và chi phí storage.

### 29.3. WAL archive liên tục

Archive WAL để đạt RPO nhỏ và PITR. Monitor archive lag/failures và retention.

### 29.4. Storage snapshots

Dùng snapshot để clone nhanh hoặc phục hồi volume, nhưng chỉ sau khi consistency procedure và restore drill được xác nhận.

### 29.5. Global objects và configuration

Lưu roles/tablespaces, config, extension inventory, certificates/secret references và deployment metadata.

### 29.6. Backup catalog

Quản lý metadata để operator tìm đúng backup, WAL range, snapshot IDs, encryption keys và restore instructions.

## 30. Các kịch bản khôi phục thực tế

| Sự cố | Hướng xử lý thường dùng |
| --- | --- |
| Một table bị xóa nhầm | Restore logical dump vào DB tạm, trích table hoặc dùng PITR vào cluster tạm |
| Một database bị drop | Logical restore nếu dump mới đủ; nếu cần trạng thái chính xác hơn, physical + WAL PITR |
| Toàn bộ node mất | Restore physical base backup hoặc snapshot consistent rồi replay WAL |
| Volume data bị hỏng | Restore snapshot/physical backup và WAL theo procedure |
| Một transaction ghi sai dữ liệu | PITR đến trước transaction lỗi, thường trên cluster tách biệt |
| Cần chuyển major version | Logical migration hoặc pg_upgrade |
| Snapshot gần nhất đã chứa corruption | Chọn recovery point cũ hơn và replay WAL đến trước corruption |
| Role bị xóa | Restore globals dump hoặc tạo lại role theo audit/config |
| Tablespace volume mất | Restore volume/physical backup và kiểm tra tablespace mapping |
| Backup file bị corrupt | Dùng một copy khác, kiểm tra checksum và restore drill |

### 30.1. Table-level recovery từ physical backup

Physical backup không có chức năng restore một table trực tiếp như archive logical. Có thể:

1. Dựng một cluster tạm từ base backup.
2. Replay WAL đến thời điểm cần.
3. Dump table cần bằng pg_dump.
4. Restore table vào cluster production theo kế hoạch.
5. Kiểm tra constraints, sequences, dependencies và writes phát sinh sau thời điểm dump.

### 30.2. Table-level recovery từ PITR

Không thể chỉ rewind một table trong cluster production bằng recovery target toàn cluster. Thường tạo một cluster phụ được PITR đến target, sau đó export object cần thiết.

## 31. Những sai lầm thường gặp

1. Coi logical dump là bản sao vật lý của data directory.
2. Dùng pg_dump và cho rằng roles/tablespaces đã được backup.
3. Dùng physical backup của major version cũ để start bằng major version mới.
4. Coi một base backup là đủ cho PITR mà không có WAL liên tục.
5. Coi WAL archive là backup đầy đủ không cần base backup.
6. Coi storage snapshot của riêng PGDATA là đủ khi tablespaces nằm ngoài.
7. Chụp nhiều volumes ở các thời điểm khác nhau rồi giả định consistency.
8. Copy PGDATA đang chạy bằng file copy thông thường và gọi đó là online backup.
9. Coi crash-consistent snapshot tự động là application-consistent.
10. Coi storage snapshot là MVCC snapshot.
11. Coi standby/replica là backup chống logical corruption.
12. Coi snapshot trong cùng account là bản sao chống ransomware.
13. Không giữ config, extension binaries hoặc encryption keys.
14. Không ghi WAL range và snapshot IDs trong manifest.
15. Chỉ kiểm tra backup command exit code.
16. Không restore thử trong môi trường tách biệt.
17. Dùng pg_restore --clean nhầm database production.
18. Bật -R khi không định dựng standby.
19. Xóa WAL quá sớm làm hỏng PITR chain.
20. Đánh giá RTO chỉ bằng thời gian copy/attach, bỏ qua replay và application validation.

## 32. Bài tập thực hành có đáp án

Các bài tập giả định bạn có một PostgreSQL lab và thư mục backup riêng. Các lệnh restore destructive chỉ nên chạy trong database đích dùng cho lab.

### Bài 1. Logical backup là gì?

**Đáp án:** Backup schema/data dưới dạng object logic như SQL hoặc archive, được tái tạo bằng restore tools.

### Bài 2. Physical backup là gì?

**Đáp án:** Sao chép các file dữ liệu PostgreSQL ở cấp cluster cùng các thành phần cần thiết để khôi phục cluster.

### Bài 3. Storage snapshot là gì?

**Đáp án:** Ảnh chụp trạng thái block/volume/filesystem do storage layer quản lý tại một thời điểm.

### Bài 4. pg_dump sao lưu một hay tất cả databases?

**Đáp án:** Một database cho mỗi lần chạy.

### Bài 5. Công cụ xuất global objects?

**Đáp án:** pg_dumpall --globals-only.

### Bài 6. pg_dumpall khác pg_dump thế nào?

**Đáp án:** pg_dumpall xuất nhiều databases và global objects theo SQL script; pg_dump xuất một database với nhiều archive formats.

### Bài 7. Plain dump restore bằng gì?

**Đáp án:** psql.

### Bài 8. Custom dump restore bằng gì?

**Đáp án:** pg_restore.

### Bài 9. Custom format tạo bằng option nào?

**Đáp án:** pg_dump -Fc.

### Bài 10. Directory format có ưu điểm gì?

**Đáp án:** Hỗ trợ parallel dump/restore và lưu archive thành nhiều files.

### Bài 11. Xem TOC của custom archive bằng gì?

**Đáp án:** pg_restore --list.

### Bài 12. pg_dump có khóa database để ngăn mọi writes không?

**Đáp án:** Không. Nó dùng consistent MVCC snapshot và locks cần thiết trên objects.

### Bài 13. Logical dump có tự chứa roles không?

**Đáp án:** Không. Roles là global objects; xuất riêng bằng pg_dumpall globals-only hoặc backup cluster vật lý.

### Bài 14. Vì sao cần bảo vệ tablespace definitions?

**Đáp án:** Tablespaces có thể nằm ngoài PGDATA và cần path/mount/ownership phù hợp khi restore.

### Bài 15. pg_restore --clean làm gì?

**Đáp án:** Xóa objects trước khi tạo lại; có thể phá dữ liệu ở target nên phải xác định đúng database.

### Bài 16. --no-owner thay đổi điều gì?

**Đáp án:** Không khôi phục ownership theo owner gốc; objects được tạo theo role thực hiện restore hoặc semantics tương ứng.

### Bài 17. Physical backup thường bao phủ phạm vi nào?

**Đáp án:** Toàn bộ PostgreSQL cluster và các thành phần physical liên quan, không chỉ một table.

### Bài 18. Công cụ PostgreSQL phổ biến tạo base backup?

**Đáp án:** pg_basebackup.

### Bài 19. pg_basebackup dùng protocol nào?

**Đáp án:** Replication protocol.

### Bài 20. -X stream có mục đích gì?

**Đáp án:** Stream WAL đồng thời với base backup để bảo đảm backup có WAL cần thiết theo phương thức đó.

### Bài 21. pg_basebackup -R thường dùng khi nào?

**Đáp án:** Khi chuẩn bị backup làm standby, vì nó ghi recovery/connection configuration phù hợp.

### Bài 22. Base backup có thay WAL archive cho PITR dài hạn không?

**Đáp án:** Không. Cần giữ WAL liên tục đến recovery target.

### Bài 23. WAL archive thiếu một segment có thể gây gì?

**Đáp án:** PITR có thể không replay qua được khoảng thời gian cần thiết.

### Bài 24. PITR cần những gì?

**Đáp án:** Base backup hợp lệ, WAL liên tục, restore configuration và recovery target.

### Bài 25. RPO là gì?

**Đáp án:** Recovery Point Objective, mức mất dữ liệu tối đa chấp nhận được theo thời gian.

### Bài 26. RTO là gì?

**Đáp án:** Recovery Time Objective, thời gian tối đa chấp nhận để khôi phục dịch vụ.

### Bài 27. Storage snapshot có hiểu schema/table không?

**Đáp án:** Không. Nó chụp storage blocks/volumes.

### Bài 28. Copy-on-write snapshot hoạt động khái quát thế nào?

**Đáp án:** Giữ tham chiếu/metadata tới trạng thái ban đầu và lưu các blocks thay đổi theo cơ chế storage.

### Bài 29. Crash-consistent snapshot là gì?

**Đáp án:** Trạng thái storage tương tự máy bị crash tại một thời điểm; PostgreSQL cần WAL crash recovery và đầy đủ file/volume.

### Bài 30. Crash-consistent có đồng nghĩa application-consistent không?

**Đáp án:** Không. Application-consistent cần phối hợp với ứng dụng/database và backup procedure phù hợp.

### Bài 31. Snapshot riêng volume PGDATA có luôn đủ?

**Đáp án:** Không nếu tablespaces/WAL hoặc các dependencies nằm trên volumes khác.

### Bài 32. Vì sao multi-volume snapshot cần consistency group?

**Đáp án:** Để mọi volumes đại diện cùng một point-in-time, tránh data và WAL/tablespaces lệch thời điểm.

### Bài 33. MVCC snapshot khác storage snapshot thế nào?

**Đáp án:** MVCC snapshot là transaction visibility state; storage snapshot là ảnh block/volume.

### Bài 34. Khi snapshot online, PostgreSQL backup API dùng để làm gì?

**Đáp án:** Phối hợp physical backup với server, xác định backup interval và metadata/WAL cần thiết theo version.

### Bài 35. Có thể copy PGDATA đang chạy bằng cp -r để backup online không?

**Đáp án:** Không nên. Dùng pg_basebackup hoặc file-system backup procedure được PostgreSQL hỗ trợ.

### Bài 36. Snapshot khi PostgreSQL shutdown sạch có lợi gì?

**Đáp án:** Có thể tạo physical copy nhất quán nếu mọi volumes/tablespaces được snapshot đầy đủ; đổi lại cần downtime.

### Bài 37. Physical backup có thể restore trực tiếp qua major version không?

**Đáp án:** Không. Cần môi trường tương thích cùng major; dùng pg_upgrade/logical migration cho major upgrade.

### Bài 38. Extension binaries có nằm trong logical dump không?

**Đáp án:** Không. Cần cài extension packages tương thích trên target.

### Bài 39. Standby có thay backup không?

**Đáp án:** Không. Logical corruption có thể replicate sang standby.

### Bài 40. Snapshot cùng storage account có chống ransomware đầy đủ không?

**Đáp án:** Không. Credential bị xâm nhập có thể xóa cả volume và snapshot; cần offsite/immutable copy.

### Bài 41. pg_verifybackup dùng để làm gì?

**Đáp án:** Kiểm tra physical backup manifest/file checksums trên các version/format được hỗ trợ.

### Bài 42. pg_verifybackup chứng minh ứng dụng hoạt động đúng không?

**Đáp án:** Không. Cần restore/boot test và application validation.

### Bài 43. Checksum backup chứng minh điều gì?

**Đáp án:** Phát hiện nội dung bytes thay đổi so với digest đã lưu; không chứng minh semantics/recoverability.

### Bài 44. Logical restore drill nên kiểm tra gì?

**Đáp án:** Schema, data, constraints, indexes, roles/extensions và business smoke tests.

### Bài 45. Physical restore drill cần kiểm tra gì?

**Đáp án:** Data directory, tablespaces, WAL recovery, server startup, roles/extensions và application connectivity.

### Bài 46. Snapshot restore drill cần kiểm tra gì?

**Đáp án:** Snapshot metadata, tất cả volumes, consistency procedure, WAL, configuration và cluster recovery.

### Bài 47. Vì sao cần manifest?

**Đáp án:** Để biết backup identity, version, scope, time, consistency method, WAL range, snapshot IDs, checksum và restore instructions.

### Bài 48. Full backup khác incremental backup thế nào?

**Đáp án:** Full lưu toàn bộ scope; incremental chỉ lưu changes kể từ một backup trước đó.

### Bài 49. pg_dump mặc định là incremental không?

**Đáp án:** Không. Mỗi dump là logical export cho scope được chọn; incremental logical semantics cần pipeline riêng.

### Bài 50. Snapshot incremental có tự hiểu PostgreSQL WAL không?

**Đáp án:** Không. Nó là cơ chế incremental của storage layer; consistency/WAL vẫn cần xử lý riêng.

### Bài 51. Vì sao phải giữ backup encryption keys?

**Đáp án:** Không có key phù hợp thì backup đã mã hóa có thể không restore được.

### Bài 52. Vì sao backup copy nên offsite?

**Đáp án:** Để giảm rủi ro cùng một failure domain, region, account hoặc sự cố vật lý ảnh hưởng mọi bản sao.

### Bài 53. Immutable backup giúp gì?

**Đáp án:** Ngăn backup bị sửa/xóa trong retention period theo policy, giảm tác động của ransomware hoặc credential compromise.

### Bài 54. Có nên xóa WAL chỉ vì đã quá 7 ngày?

**Đáp án:** Không nếu một base backup còn cần chuỗi WAL đó cho PITR hoặc standby recovery.

### Bài 55. Khôi phục một table từ physical backup thế nào?

**Đáp án:** Restore cluster tạm, replay đến trạng thái cần, dump table rồi import vào production theo change plan.

### Bài 56. Khôi phục trước một transaction lỗi bằng gì?

**Đáp án:** Base backup + WAL PITR đến trước transaction lỗi, thường trên cluster tạm.

### Bài 57. pg_dump có thể dùng cho major-version migration không?

**Đáp án:** Có thể, nếu client/server/object compatibility phù hợp; cần kiểm tra extensions, roles, collations và target version.

### Bài 58. Vì sao RTO phải tính cả validation?

**Đáp án:** Server start chưa đồng nghĩa ứng dụng đã an toàn để nhận traffic; cần kiểm tra dữ liệu, integrations và cutover.

### Bài 59. Tại sao không nên chỉ có một loại backup?

**Đáp án:** Mỗi loại có strengths/limitations khác nhau; kết hợp logical, physical, WAL và snapshot giúp nhiều kiểu recovery.

### Bài 60. Lập checklist chọn loại backup cho một PostgreSQL service

**Đáp án gợi ý:**

1. Xác định RPO/RTO và phạm vi cần restore.
2. Dùng pg_dump cho object/database-level recovery và migration.
3. Lưu global objects/roles/tablespaces riêng khi cần.
4. Dùng pg_basebackup hoặc backup tool vật lý tương thích cho whole-cluster recovery.
5. Thiết lập WAL archive liên tục nếu cần PITR.
6. Chỉ dùng storage snapshot sau khi xác định consistency semantics và mọi volumes.
7. Lưu config, extension inventory, certificates/secret references và tablespace mapping.
8. Mã hóa, offsite, immutable retention và tách quyền xóa.
9. Tạo manifest, checksum và kiểm tra backup artifact.
10. Restore drill định kỳ, đo RPO/RTO thực tế và cập nhật runbook.

## 33. Checklist production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| RPO/RTO | Được xác định theo business impact |
| Logical backups | Có cho database/object recovery |
| Global objects | Roles/tablespaces được bảo vệ |
| Physical base backup | Có lịch và restore procedure |
| WAL archive | Liên tục, có monitoring gaps |
| PITR | Có recovery target/runbook |
| Storage snapshots | Consistency method được ghi rõ |
| Multi-volume | Có consistency group hoặc quy trình phối hợp |
| Tablespaces | Được bao gồm/map chính xác |
| PGDATA/WAL | Đầy đủ trong backup scope |
| PostgreSQL version | Restore target tương thích |
| Extensions | Binary packages và versions được lưu inventory |
| Config files | Có bản sao ngoài data directory |
| TLS/secrets | Có quy trình phục hồi an toàn |
| Encryption | At-rest và in-transit |
| Key management | Có rotation/escrow/recovery test |
| Offsite copy | Khác failure domain |
| Immutability | Có retention lock phù hợp |
| Backup manifest | Có IDs, scope, version, time, checksum |
| WAL retention | Không xóa segment còn cần |
| Snapshot retention | Không chỉ giữ trong cùng account |
| pg_verifybackup | Chạy khi format/version hỗ trợ |
| Logical archive listing | Kiểm tra archive entries |
| Restore drills | Định kỳ và có báo cáo |
| Data validation | Counts, keys, aggregates, smoke tests |
| Recovery environment | Có capacity và network isolation |
| Application cutover | Có runbook và rollback decision |
| Monitoring | Backup age, duration, size, failures |
| Restore duration | Được đo thực tế |
| Access control | Backup writer/deleter tách quyền |
| Incident hold | Có khả năng giữ backup khi điều tra |

## 34. Tổng kết

Logical backup, physical backup và storage snapshot bảo vệ dữ liệu ở ba lớp khác nhau. Logical dump lưu object/data representation; physical backup lưu cluster files; storage snapshot lưu trạng thái storage blocks. Lựa chọn đúng phụ thuộc vào đối tượng cần phục hồi, consistency contract, RPO/RTO và khả năng restore đã được kiểm chứng.

Những nguyên tắc quan trọng:

1. **Logical backup phù hợp object-level recovery và migration.** pg_dump xuất một database; pg_dumpall có thể xuất nhiều databases và global objects.
2. **Plain SQL và archive formats có cách restore khác nhau.** Dùng psql cho plain dump, pg_restore cho custom/directory/tar.
3. **Logical dump dùng consistent MVCC snapshot.** Nó không sao chép physical page layout.
4. **Roles và tablespaces không tự có trong pg_dump.** Bảo vệ global objects riêng khi cần.
5. **Physical backup phù hợp whole-cluster recovery.** Dùng pg_basebackup hoặc công cụ được hỗ trợ.
6. **Physical backup cần PostgreSQL major version tương thích.** Không dùng nó như major-version upgrade method.
7. **Base backup và WAL archive bổ sung cho nhau.** PITR cần base backup cùng WAL liên tục.
8. **Storage snapshot chỉ chụp storage state.** Nó không hiểu schema, transaction visibility hoặc business objects.
9. **Crash-consistent không tự động là application-consistent.** Dùng backup API/procedure đúng version khi snapshot online.
10. **Snapshot phải bao gồm mọi volumes liên quan.** PGDATA, tablespaces và WAL không được lệch point-in-time.
11. **Replication không thay backup.** Logical corruption có thể lan sang standby.
12. **Snapshot trong cùng failure domain chưa đủ.** Giữ offsite/immutable copies.
13. **Checksum và manifest giúp kiểm chứng artifact.** Chúng không thay restore drill.
14. **Restore drill là bằng chứng thực tế.** Kiểm tra cả PostgreSQL và application.
15. **RPO/RTO phải đo bằng recovery hoàn chỉnh.** Tính cả WAL replay, validation và cutover.
16. **Bảo vệ keys/config/extensions.** Backup data không tự chứa mọi dependency để vận hành cluster.
17. **Giữ WAL theo dependency của base backups.** Xóa segment quá sớm có thể phá PITR.
18. **Kết hợp nhiều loại backup.** Logical cho objects, physical cho cluster, WAL cho PITR và snapshot cho storage-level clone/recovery.

Mô hình lựa chọn:

```text
Cần restore một object?
        |
        +---- Có ----> Logical dump / restore
        |
        +---- Không
                |
                v
       Cần whole-cluster recovery?
                |
                +---- Có ----> Physical base backup
                |                 + WAL archive cho PITR
                |
                +---- Cần clone volume nhanh?
                                  |
                                  v
                         Storage snapshot
                         + consistency procedure
                         + WAL khi cần recovery
                                  |
                                  v
                         Restore drill và verify
```

**Câu hỏi review cuối cùng:** “Nếu một table bị xóa nhầm, nếu toàn bộ node mất, nếu một transaction lỗi commit và nếu một storage volume bị hỏng, chúng ta có chọn được backup phù hợp, biết chính xác các dependencies cần thiết và đã chứng minh restore thành công trong thời gian RTO hay chưa?” Một chiến lược backup đáng tin phải trả lời được từng tình huống bằng artifact, WAL/metadata, manifest và restore drill thực tế.
