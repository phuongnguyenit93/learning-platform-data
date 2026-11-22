# pg_basebackup và bản sao cơ sở vật lý trong PostgreSQL

PostgreSQL có hai hướng sao lưu phổ biến: **logical backup** và **physical backup**. Logical backup xuất cấu trúc và dữ liệu ở mức SQL, thường bằng pg_dump/pg_dumpall. Physical backup sao chép các file vật lý của toàn bộ PostgreSQL cluster theo một quy trình nhất quán, sau đó dùng WAL để hoàn tất recovery khi restore.

**pg_basebackup** là công cụ PostgreSQL cung cấp để tạo physical base backup từ một server đang chạy. Công cụ sử dụng replication protocol và backup protocol của PostgreSQL, vì vậy có thể tạo backup online mà không cần dừng database. Một base backup là điểm bắt đầu cho crash recovery, dựng standby hoặc Point-in-Time Recovery (PITR) khi kết hợp với WAL phù hợp.

~~~text
PostgreSQL primary
      |
      | replication protocol / backup protocol
      v
  pg_basebackup
      |
      +----------------------------+
      |                            |
      v                            v
  Data files                  WAL cần thiết
  - base relations            - stream trong backup
  - indexes                   - hoặc lấy bằng archive
  - system catalogs
  - tablespaces
      |                            |
      +--------------+-------------+
                     |
                     v
              Physical base backup
                     |
           +---------+----------+
           |                    |
           v                    v
       Restore DB           Dựng standby
           |                    |
           v                    v
       Crash recovery       Streaming replication
           |
           v
       Có thể replay thêm archive WAL để PITR
~~~

Một file backup có thể được tạo thành công nhưng vẫn chưa phải một kế hoạch khôi phục hoàn chỉnh. Cần biết backup thuộc cluster/version nào, WAL nào cần thiết, tablespace nằm ở đâu, cấu hình nào ở ngoài PGDATA, retention giữ những file gì và đã từng thử restore hay chưa.

Bài này thuộc chương **Sao lưu** của module *Database Engine Relational PostgreSQL*, tập trung vào cách tạo, kiểm tra, lưu giữ và khôi phục bản sao vật lý bằng pg_basebackup.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt physical backup với logical backup.
2. Giải thích vì sao physical backup thường bao phủ toàn bộ cluster thay vì một bảng riêng.
3. Mô tả backup protocol và vai trò của WAL trong online backup.
4. Cấp quyền replication và cấu hình pg_hba.conf cho pg_basebackup.
5. Chọn format plain hoặc tar và hiểu cách lưu tablespaces.
6. Chọn WAL method stream, fetch hoặc none theo nhu cầu.
7. Sử dụng các tùy chọn checkpoint, rate limit, progress và tablespace mapping.
8. Hiểu tác động của max_wal_senders, replication slots và archive retention.
9. Tạo base backup từ primary hoặc standby với các điều kiện phù hợp.
10. Dùng tùy chọn -R để dựng cấu hình standby từ backup.
11. Kiểm tra backup manifest và checksum bằng pg_verifybackup.
12. Phân biệt kiểm tra backup file với thử restore end-to-end.
13. Khôi phục plain backup và tar backup đúng cách.
14. Chuẩn bị WAL archive và recovery settings để PITR.
15. Thiết kế retention dựa trên backup dependencies.
16. Đo thời gian, dung lượng, RPO và RTO qua restore drill.
17. Nhận diện các lỗi phổ biến khi tạo và phục hồi physical backup.

## 2. Physical backup là gì?

Physical backup là bản sao các file dữ liệu PostgreSQL ở mức filesystem/storage. Nó giữ nguyên cách PostgreSQL lưu heap, indexes, catalogs, WAL và các thành phần vật lý khác.

### 2.1. PostgreSQL cluster

Một cluster PostgreSQL là một vùng dữ liệu được quản lý bởi một server instance, thường có:

- Nhiều database.
- Shared catalogs và các global objects.
- Roles và quyền.
- Tablespaces.
- Data files, indexes và các relation phụ trợ.
- Các file cấu hình nằm trong hoặc ngoài data directory.

Physical base backup thông thường sao chép cluster, không chọn riêng một database hoặc một bảng.

### 2.2. File-level copy

Không thể đơn giản chạy lệnh copy thư mục PGDATA trong khi PostgreSQL đang ghi dữ liệu rồi coi kết quả là backup hợp lệ. Một file có thể được copy trước khi thay đổi, file khác được copy sau thay đổi; các file đó có thể không tạo thành một trạng thái nhất quán.

### 2.3. Online physical backup

pg_basebackup phối hợp với server để xác định điểm bắt đầu/kết thúc backup và bảo đảm có WAL cần thiết để làm cho bản sao nhất quán. Database vẫn có thể phục vụ truy vấn và ghi trong lúc backup, dù backup tạo thêm I/O và WAL load.

### 2.4. Base backup và WAL

Base backup là ảnh dữ liệu tại một khoảng thời gian. Vì các page có thể thay đổi trong khi được sao chép, WAL cần thiết để replay và đưa bản sao về trạng thái nhất quán.

### 2.5. Physical backup không phải bản export SQL

Không thể mở một physical backup như file SQL để đọc từng câu CREATE TABLE/INSERT. Để xem dữ liệu ở mức SQL, cần restore vào PostgreSQL hoặc dùng logical backup.

## 3. Physical backup và logical backup

| Tiêu chí | Physical backup | Logical backup |
| --- | --- | --- |
| Công cụ điển hình | pg_basebackup, pgBackRest | pg_dump, pg_dumpall |
| Nội dung | File vật lý của cluster | Schema và dữ liệu logic |
| Phạm vi thường dùng | Toàn cluster | Database/schema/table tùy chọn |
| Restore | Phục hồi file rồi replay WAL | Chạy SQL để dựng lại objects |
| Tốc độ backup/restore | Thường nhanh cho cluster lớn | Có thể chậm hơn với dữ liệu rất lớn |
| Di chuyển major version | Không dùng trực tiếp như bản restore cùng major | Có thể hỗ trợ migration qua dump/restore |
| Chọn một bảng | Không phải mục tiêu của base backup | Có |
| PITR | Kết hợp base backup và WAL | Không cung cấp physical WAL replay như vậy |
| Đọc/chỉnh sửa nội dung | Không trực tiếp | Dump có thể đọc/chỉnh sửa |

### 3.1. Khi nào chọn physical backup?

- Cần phục hồi toàn bộ cluster nhanh.
- Cần dựng standby/replica từ một bản sao.
- Database lớn và muốn tránh tái tạo mọi object bằng SQL.
- Cần PITR bằng base backup cộng WAL archive.

### 3.2. Khi nào chọn logical backup?

- Chỉ cần một database, schema hoặc table.
- Muốn di chuyển dữ liệu giữa major versions.
- Muốn xuất dữ liệu để kiểm tra/chuyển đổi.
- Muốn backup một tập object nhỏ thay vì cả cluster.

### 3.3. Dùng cả hai

Hệ thống quan trọng thường kết hợp physical backup/WAL archiving cho disaster recovery và logical dump cho migration, object-level recovery hoặc portability.

## 4. pg_basebackup hoạt động thế nào?

pg_basebackup kết nối tới PostgreSQL bằng replication protocol, yêu cầu server bắt đầu backup, sao chép các file cần thiết, thu thập WAL theo phương thức được chọn và kết thúc backup.

### 4.1. Backup start

Server ghi nhận một điểm bắt đầu backup và cung cấp metadata để xác định WAL cần thiết.

### 4.2. Copy data files

Client sao chép các relation files, catalogs, control file, cấu trúc tablespace và các thành phần được backup protocol cung cấp.

### 4.3. WAL trong khi copy

Các thay đổi vẫn diễn ra trên primary. WAL giúp recovery xử lý khác biệt giữa thời điểm từng file được copy và trạng thái nhất quán của backup.

### 4.4. Backup stop

Server kết thúc backup, ghi metadata/record cần thiết và xác định WAL cuối cùng để backup nhất quán.

### 4.5. Backup label và manifest

Backup có thể chứa backup_label, tablespace_map và backup_manifest tùy format/version. Đây là metadata cần giữ nguyên khi restore và verify.

### 4.6. Không tự chỉnh sửa backup metadata

Không sửa backup_label hoặc manifest để “làm cho verify pass”. Những file này là một phần của bằng chứng và quy trình consistency.

## 5. Điều kiện phía PostgreSQL server

Trước khi chạy pg_basebackup, kiểm tra các tham số và tài nguyên server.

### 5.1. wal_level

Đối với physical replication/backup, cấu hình thường dùng:

~~~conf
wal_level = replica
~~~

Mức logical cũng bao gồm khả năng WAL của replica. Không dùng minimal cho quy trình cần physical replication/PITR.

### 5.2. max_wal_senders

Server cần đủ WAL sender processes cho standbys, backup jobs và các replication connections khác.

~~~conf
max_wal_senders = 10
~~~

Một pg_basebackup dùng WAL method stream có thể cần hai replication connections đồng thời: một cho base backup và một cho WAL stream. Hãy cộng thêm số standby/backup đang chạy đồng thời và chừa headroom.

### 5.3. max_replication_slots

Nếu dùng named replication slots, server cần đủ slot capacity:

~~~conf
max_replication_slots = 10
~~~

Chỉ tăng theo số consumer/backup slot thực tế và theo dõi slot không còn được dùng.

### 5.4. full_page_writes

Giữ full_page_writes bật theo cấu hình an toàn thông thường. Full-page images giúp recovery bảo vệ trước torn page trong các điều kiện cần thiết. Khi backup từ standby, cần đặc biệt bảo đảm primary có full_page_writes phù hợp.

### 5.5. hot_standby

Nếu backup từ standby, standby phải ở trạng thái cho phép truy vấn/read-only theo yêu cầu và được cấu hình phù hợp, thường có hot_standby bật.

### 5.6. Archive WAL

Nếu mục tiêu là PITR hoặc backup retention dài hạn, cấu hình WAL archiving trên primary/nguồn phù hợp. WAL được stream kèm một base backup chỉ bảo đảm phần cần cho backup đó; nó không tự tạo archive liên tục cho những thời điểm sau.

### 5.7. Disk headroom

Server cần đủ chỗ cho WAL phát sinh trong khi backup và các replication slots. Backup client cần đủ chỗ cho bản sao đích và có thể cần chỗ tạm khi nén/chuyển định dạng.

## 6. Tạo replication user và pg_hba.conf

pg_basebackup kết nối bằng replication protocol. User cần quyền LOGIN và REPLICATION hoặc quyền quản trị tương ứng theo chính sách server.

### 6.1. Tạo role backup

~~~sql
CREATE ROLE backup_user
WITH LOGIN REPLICATION PASSWORD 'replace-with-a-secret';
~~~

Không dùng mật khẩu mẫu trong production. Quản lý secret qua hệ thống phù hợp và xoay vòng theo policy.

### 6.2. Cho phép replication trong pg_hba.conf

Ví dụ cho kết nối TLS từ subnet backup:

~~~conf
hostssl replication backup_user 10.20.0.0/24 scram-sha-256
~~~

Địa chỉ mạng, TLS và authentication method phải khớp với hạ tầng thực tế. Không mở replication access ra toàn Internet.

### 6.3. Reload pg_hba.conf

~~~sql
SELECT pg_reload_conf();
~~~

### 6.4. Xác minh rule

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

View này giúp phát hiện lỗi parse và xem thứ tự rules. PostgreSQL áp dụng rule đầu tiên khớp; thứ tự có ý nghĩa.

### 6.5. Phân biệt quyền SQL và quyền OS

Replication role xác thực với PostgreSQL. File backup được ghi bởi process chạy pg_basebackup trên máy client, nên quyền filesystem đích thuộc user OS chạy client.

### 6.6. Dùng .pgpass

Để chạy automation không tương tác, có thể dùng password file theo chuẩn libpq. Trên Unix, file phải có permission chặt (thường 0600). Không đặt password plaintext trực tiếp trong shell history hoặc process arguments.

## 7. Cú pháp pg_basebackup cơ bản

Ví dụ tạo backup plain format:

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backup/base_2026_11_14 \
  -F plain \
  -X stream \
  -P \
  -v
~~~

Ý nghĩa:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| -h | Host PostgreSQL server |
| -p | Port |
| -U | Replication user |
| -D | Thư mục đích |
| -F plain | Lưu file theo cấu trúc data directory |
| -X stream | Stream WAL cần thiết đồng thời |
| -P | Hiển thị tiến độ |
| -v | Output chi tiết |

### 7.1. Destination directory

Thư mục đích thường phải chưa tồn tại hoặc rỗng theo điều kiện của phiên bản/tool. Không trỏ vào PGDATA đang chạy hoặc thư mục có dữ liệu cần giữ.

### 7.2. Không chạy với superuser OS không cần thiết

Chạy backup client bằng một OS account riêng có quyền ghi vào backup destination. Database replication user là danh tính khác với OS user.

### 7.3. Chọn đúng pg_basebackup binary

Dùng tool phù hợp với server major version và kiểm tra:

~~~bash
pg_basebackup --version
pg_basebackup --help
~~~

Các option mới có thể không tồn tại trong binary cũ. Dùng tài liệu của major version đang chạy.

## 8. Plain format và tar format

pg_basebackup có hai format phổ biến:

### 8.1. Plain format

~~~bash
pg_basebackup -h primary.example.internal \
  -U backup_user \
  -D /backup/base_plain \
  -F plain -X stream -P
~~~

Plain format tạo cấu trúc thư mục gần với data directory của PostgreSQL. Có thể dùng trực tiếp làm PGDATA sau khi chuẩn bị restore đúng cách.

### 8.2. Tar format

~~~bash
pg_basebackup -h primary.example.internal \
  -U backup_user \
  -D /backup/base_tar \
  -F tar -X stream -P
~~~

Tar format tạo archive tar, thường có base.tar, pg_wal.tar và tar riêng cho các tablespaces. Cần giải nén đúng vị trí trước khi khởi động server.

### 8.3. So sánh

| Tiêu chí | Plain | Tar |
| --- | --- | --- |
| Cấu trúc | Directory tree | Một hoặc nhiều tar files |
| Khởi động restore | Sau khi đặt đúng PGDATA/tablespaces | Cần extract đúng các tar |
| Tablespace | Directory/symlink theo backup | Archive riêng theo tablespace |
| Mapping tablespace | Hỗ trợ qua tùy chọn mapping trong workflow phù hợp | Thường xử lý khi extract/đặt tablespace |
| Verify manifest | pg_verifybackup hỗ trợ plain format | Không dùng pg_verifybackup trực tiếp như plain |
| Nén | Nén ở filesystem/tool backup khác | Có tùy chọn nén tar tùy version |

### 8.4. Chọn format nào?

Plain dễ restore trực tiếp và thuận tiện cho pg_verifybackup. Tar phù hợp khi muốn đóng gói/stream qua pipeline hoặc quản lý archive files. Cần chọn format dựa trên restore tooling và cách xử lý tablespace.

### 8.5. Không giải nén mọi tar vào cùng một thư mục

Tablespace tar phải được giải nén vào vị trí tablespace tương ứng; pg_wal.tar phải đi vào thư mục pg_wal trong data directory. Giải nén sai có thể làm backup không khởi động được.

## 9. WAL methods: stream, fetch và none

Tùy chọn -X chọn cách thu thập WAL cần thiết cho base backup.

### 9.1. stream

~~~bash
pg_basebackup -D /backup/base_stream -X stream -P
~~~

WAL được stream đồng thời trong quá trình copy dữ liệu. Đây là lựa chọn phổ biến cho backup online vì giảm nguy cơ WAL cần thiết bị recycle trước khi client lấy xong.

### 9.2. fetch

~~~bash
pg_basebackup -D /backup/base_fetch -X fetch -P
~~~

WAL cần thiết được lấy sau khi phần data copy kết thúc. Server phải giữ các segment cần thiết đủ lâu cho tới lúc fetch; nếu WAL bị recycle trước đó, backup có thể thất bại.

### 9.3. none

~~~bash
pg_basebackup -D /backup/base_no_wal -X none -P
~~~

Không lấy WAL trong lệnh backup. Chỉ dùng khi một quy trình khác bảo đảm cung cấp đầy đủ WAL cần thiết. Nếu không có WAL phù hợp, bản sao không thể được đưa về trạng thái nhất quán để khởi động.

### 9.4. So sánh

| Method | Thời điểm lấy WAL | Yêu cầu chính |
| --- | --- | --- |
| stream | Đồng thời với data copy | Đủ WAL senders/connections |
| fetch | Sau khi data copy | WAL cần thiết vẫn còn trên server |
| none | Không lấy | Phải có cơ chế WAL ngoài lệnh |

### 9.5. WAL stream không phải archive liên tục

WAL stream trong pg_basebackup chỉ thu thập WAL cần cho backup đó. Muốn PITR tới thời điểm sau backup, cần WAL archive liên tục hoặc một cơ chế WAL retention/transfer khác.

## 10. Checkpoint mode và tốc độ backup

### 10.1. spread

Checkpoint spread cho phép checkpoint diễn ra dàn trải theo cấu hình, giúp giảm đột biến I/O. Đây là lựa chọn mặc định phổ biến.

### 10.2. fast

Checkpoint fast yêu cầu checkpoint hoàn tất nhanh hơn, có thể tạo I/O spike. Chỉ chọn khi có lý do vận hành và đã hiểu tác động.

Ví dụ:

~~~bash
pg_basebackup -D /backup/base_fast \
  -X stream --checkpoint=fast -P
~~~

### 10.3. Max rate

Có thể giới hạn tốc độ truyền để giảm ảnh hưởng tới production:

~~~bash
pg_basebackup -D /backup/base_limited \
  -X stream --max-rate=100M -P
~~~

Đơn vị và cú pháp cụ thể theo phiên bản pg_basebackup. Giới hạn thấp làm backup kéo dài, đồng thời kéo dài thời gian phải giữ WAL cần thiết.

### 10.4. Đo tác động

Theo dõi CPU, disk throughput, network, WAL generation, replication lag và query latency trong thời gian backup.

### 10.5. Backup song song

Nhiều backup đồng thời có thể tăng I/O và số WAL sender. Lập giới hạn concurrency và kiểm tra headroom trước khi chạy.

## 11. Progress, label và logging

### 11.1. Hiển thị progress

~~~bash
pg_basebackup -D /backup/base \
  -X stream -P -v
~~~

Progress giúp người vận hành biết bytes đã copy và tổng ước lượng. Nó không chứng minh backup có thể restore.

### 11.2. Backup label

~~~bash
pg_basebackup -D /backup/base \
  -X stream -l "nightly-2026-11-14" -P
~~~

Label giúp nhận diện backup trong log/metadata; không dùng label làm định danh duy nhất nếu tên có thể trùng.

### 11.3. Log

Lưu stdout/stderr, thời điểm bắt đầu/kết thúc, host nguồn, server version, tool version, backup ID, format, WAL method, kích thước và exit code.

### 11.4. Exit code

Automation chỉ đánh dấu backup thành công khi pg_basebackup kết thúc với exit code thành công và bước kiểm tra/đăng ký metadata tiếp theo đã hoàn tất.

### 11.5. Không bỏ qua lỗi vì có directory

pg_basebackup có thể để lại file một phần khi bị gián đoạn. Sự tồn tại của thư mục đích không có nghĩa backup hoàn chỉnh.

## 12. Tablespaces và mapping

Tablespace cho phép relation nằm ngoài PGDATA. Physical backup phải bảo toàn nội dung và quan hệ đường dẫn của các tablespaces.

### 12.1. Liệt kê tablespaces

~~~sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
~~~

### 12.2. Plain backup

Plain backup có thể tạo cấu trúc tablespace với các đường dẫn/symlink tương ứng. Nếu restore sang host có layout khác, cần mapping phù hợp.

### 12.3. Tablespace mapping

Tùy chọn -T hoặc --tablespace-mapping có dạng olddir=newdir:

~~~bash
pg_basebackup \
  -D /backup/base \
  -F plain \
  -X stream \
  -T /data/pg_ts_fast=/restore/pg_ts_fast
~~~

Đường dẫn cũ phải khớp tablespace nguồn và đường dẫn mới phải phù hợp với nơi sẽ restore. Cú pháp và hạn chế mapping phụ thuộc format/version.

### 12.4. Tar backup

Tar format thường tạo archive riêng cho tablespace. Khi extract, đặt nội dung vào đúng thư mục tablespace mới và bảo đảm cấu trúc PGDATA/pg_tblspc tham chiếu tới đúng nơi.

### 12.5. Không bỏ quên tablespace

Nếu chỉ copy base.tar mà thiếu tablespace tar, server sẽ thiếu relation files và không khởi động/hoạt động đúng.

### 12.6. Quyền và mount

Tablespace directory cần owner/mode phù hợp user PostgreSQL và phải được mount ổn định trước khi server start.

## 13. Tùy chọn tạo standby bằng -R

pg_basebackup có thể chuẩn bị backup để chạy như một standby.

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -U replicator \
  -D /var/lib/postgresql/16/standby \
  -X stream \
  -R \
  -P
~~~

### 13.1. -R làm gì?

Tùy chọn -R hoặc --write-recovery-conf tạo standby.signal và ghi các tham số kết nối cần thiết vào postgresql.auto.conf để server được cấu hình làm standby.

### 13.2. primary_conninfo

Chứa thông tin kết nối tới primary/replication source. Quản lý password/secret an toàn; không để lộ trong log hoặc repository.

### 13.3. standby.signal

File này yêu cầu PostgreSQL chạy standby mode khi khởi động.

### 13.4. primary_slot_name

Nếu backup dùng replication slot, -R có thể ghi cấu hình slot tương ứng để standby tiếp tục dùng slot đó. Kiểm tra postgresql.auto.conf trước khi start.

### 13.5. -R không phải recovery PITR

-R tạo cấu hình standby. Khi phục hồi một bản backup độc lập hoặc PITR, cần cấu hình archive recovery/target theo mục đích thay vì vô tình để standby.signal.

## 14. Replication slots khi backup

Replication slot giữ WAL cần thiết cho một consumer, giúp tránh server recycle WAL trước khi consumer nhận.

### 14.1. Tạo slot cùng backup

Ví dụ dùng slot có tên:

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -U replicator \
  -D /backup/standby_a \
  -X stream \
  -C \
  -S standby_a_slot \
  -R \
  -P
~~~

Tùy chọn -C yêu cầu tạo slot; -S chỉ định tên slot. Cần bảo đảm slot name chưa tồn tại hoặc xử lý lifecycle theo đúng phiên bản/tool.

### 14.2. Temporary và permanent slots

Một số workflow dùng temporary slot để giữ WAL trong thời gian backup. Permanent slot có thể tồn tại sau khi backup kết thúc và giữ WAL cho standby lâu dài.

### 14.3. Slot có thể làm đầy pg_wal

Nếu consumer dừng nhưng slot vẫn giữ WAL, pg_wal có thể tăng liên tục. Theo dõi retained WAL và trạng thái slot.

### 14.4. max_slot_wal_keep_size

Có thể đặt giới hạn WAL một slot được phép giữ theo policy:

~~~conf
max_slot_wal_keep_size = 20GB
~~~

Giới hạn có thể khiến slot bị mất khả năng tiếp tục nếu consumer quá chậm và WAL cần thiết bị recycle; điều đó có thể yêu cầu tạo lại standby. Cân bằng giới hạn với disk headroom và RPO.

### 14.5. Kiểm tra slot

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Một số cột chỉ có ở phiên bản mới hơn; bỏ cột không tồn tại khi dùng PostgreSQL cũ.

## 15. Backup từ primary và standby

### 15.1. Backup từ primary

Đây là cách đơn giản và phổ biến. Backup dùng WAL senders trên primary và có thể tăng tải I/O/network trên primary.

### 15.2. Backup từ standby

Có thể giảm tải đọc/copy trên primary bằng cách backup từ standby. Tuy nhiên, standby vẫn cần đủ tài nguyên và có thể ảnh hưởng replay/replication lag.

### 15.3. Điều kiện standby

Đảm bảo standby đủ WAL sender capacity, đang hoạt động ổn định, hot_standby phù hợp và có thể cung cấp WAL cần thiết trong toàn bộ backup.

### 15.4. full_page_writes trên primary

Khi backup từ standby, full_page_writes phải được bật trên primary để hỗ trợ consistency của backup theo yêu cầu PostgreSQL.

### 15.5. WAL source

Backup từ standby có thể phụ thuộc vào WAL được replay/stream và cách công cụ lấy WAL. Cần kiểm tra hướng dẫn đúng major version, đặc biệt nếu dùng -X stream/fetch.

### 15.6. Không backup từ standby lag lớn mà không tính toán

Một backup bắt đầu từ standby có thể phản ánh state cũ hơn primary. Nếu yêu cầu backup mới nhất, đo replay LSN/lag và ghi lại thời điểm/LSN tương ứng.

## 16. Kiểm tra trạng thái backup và metadata

### 16.1. backup_label

Backup label ghi thông tin cần cho recovery của base backup. Giữ nguyên file này.

### 16.2. tablespace_map

File mô tả tablespace mappings trong backup ở các trường hợp cần thiết. Không bỏ file này khi restore.

### 16.3. backup_manifest

Các phiên bản PostgreSQL hỗ trợ manifest tạo file liệt kê backup files và checksum. Manifest giúp xác minh file có bị thiếu/thay đổi.

### 16.4. System identifier

Backup thuộc một PostgreSQL cluster có system identifier riêng. Khi ghép WAL, cần bảo đảm WAL thuộc đúng cluster history.

### 16.5. Version metadata

Ghi PostgreSQL major/minor version, build/architecture nếu cần, extension versions, locale/collation và các cấu hình cần để dựng môi trường tương thích.

## 17. Backup manifest và pg_verifybackup

pg_verifybackup kiểm tra backup dựa trên backup manifest và các kiểm tra WAL mà phiên bản hỗ trợ.

~~~bash
pg_verifybackup /backup/base_plain
~~~

### 17.1. Kiểm tra file

Công cụ so sánh danh sách file/checksum với manifest để phát hiện file thiếu, thêm hoặc thay đổi theo phạm vi kiểm tra.

### 17.2. WAL verification

Công cụ có thể kiểm tra WAL đi kèm backup theo cơ chế hỗ trợ, bao gồm parse WAL records trong phạm vi phù hợp.

### 17.3. Plain format

pg_verifybackup được thiết kế cho backup plain format; không dùng trực tiếp để verify tar-format backup như thể đó là directory plain. Nếu dùng tar, cần quy trình extract/verify phù hợp và restore test.

### 17.4. Checksum algorithm

Manifest có thể dùng checksum algorithm theo version/configuration. Khi cần, chỉ định thuật toán qua tùy chọn manifest-checksums ở phiên bản hỗ trợ.

### 17.5. Manifest không chứng minh archive tương lai

Verify pass chứng minh backup files khớp manifest trong phạm vi tool kiểm tra. Nó không chứng minh kho WAL bên ngoài còn đầy đủ tới recovery target tương lai.

### 17.6. Manifest không thay restore drill

Một backup có thể pass verify nhưng vẫn không restore được do thiếu WAL ngoài, sai tablespace path, cấu hình thiếu, extension không tương thích hoặc môi trường restore sai.

## 18. Những tùy chọn hữu ích khác

Các tùy chọn cụ thể thay đổi theo major version; kiểm tra pg_basebackup --help của binary đang sử dụng.

| Tùy chọn | Công dụng |
| --- | --- |
| -D | Thư mục đích |
| -F | Plain hoặc tar |
| -X | WAL method |
| -R | Viết cấu hình standby |
| -S | Replication slot name |
| -C | Tạo replication slot |
| -P | Hiển thị progress |
| -v | Verbose |
| -l | Backup label |
| -c | Checkpoint mode |
| -r | Giới hạn tốc độ truyền ở các phiên bản hỗ trợ |
| -T | Tablespace mapping |
| -z/-Z | Nén tar/backup tùy version |
| --no-sync | Bỏ đồng bộ file xuống storage; rủi ro khi mất điện/crash |
| --manifest-checksums | Chọn checksum manifest ở phiên bản hỗ trợ |

### 18.1. --no-sync

Không dùng trong backup production thông thường. Bỏ fsync cuối có thể khiến lệnh kết thúc trước khi dữ liệu backup được bảo đảm bền vững trên storage; mất điện hoặc crash có thể làm hỏng bản backup.

### 18.2. Compression

Các phiên bản mới có thể cung cấp nhiều phương pháp nén/level khác nhau. Compression giảm bytes truyền/lưu nhưng tiêu tốn CPU và có thể làm tăng thời gian backup/restore.

### 18.3. Incremental backup

PostgreSQL 17 trở lên bổ sung workflow incremental backup qua pg_basebackup và pg_combinebackup. Incremental backup phụ thuộc backup trước và không phải một bản full độc lập; cần giữ chain và combine đúng cách trước restore. Không dùng option incremental với server/client cũ không hỗ trợ.

## 19. Lưu trữ và bảo vệ bản backup

### 19.1. Tách khỏi server nguồn

Không chỉ giữ backup trên cùng disk/host với PGDATA. Mất host hoặc disk có thể làm mất cả dữ liệu lẫn backup.

### 19.2. Offsite copy

Giữ bản sao ở vùng failure domain khác, ví dụ region/account/storage độc lập theo chính sách tổ chức.

### 19.3. Encryption

Mã hóa khi truyền và khi lưu. Quản lý key độc lập với backup repository; mất key đồng nghĩa mất khả năng restore.

### 19.4. Access control

Chỉ backup service và restore operators cần thiết mới có quyền đọc/ghi. Bảo vệ trước xóa nhầm và ransomware bằng immutable retention/versioning nếu phù hợp.

### 19.5. Backup metadata

Lưu backup ID, timestamp, server identity, version, start/stop LSN, timeline, format, tablespace map, checksum và WAL dependencies.

### 19.6. Không sửa file sau khi manifest được tạo

Nén, mã hóa, đổi tên hoặc di chuyển file sau khi manifest tạo có thể khiến verify fail hoặc restore tooling không tìm thấy file. Nếu cần transform, ghi metadata và verify sau transform theo pipeline riêng.

## 20. Restore plain-format backup

Giả sử backup plain ở /backup/base_plain và data directory restore là /var/lib/postgresql/16/main.

### 20.1. Dừng server đích

~~~bash
pg_ctl -D /var/lib/postgresql/16/main stop
~~~

Không ghi đè data directory đang được server sử dụng.

### 20.2. Chuẩn bị data directory

Sử dụng directory rỗng, owner và permissions phù hợp user chạy PostgreSQL. Lưu lại cấu hình riêng cần thiết trước khi thay thế.

### 20.3. Copy/extract backup

Nếu backup đã là plain directory, đặt toàn bộ cấu trúc backup vào data directory đích theo đúng layout. Đảm bảo các tablespace symlinks trỏ tới nơi đã restore.

### 20.4. Quyền file

~~~bash
chown -R postgres:postgres /var/lib/postgresql/16/main
chmod 700 /var/lib/postgresql/16/main
~~~

Ví dụ cho Linux với user/group postgres; thay theo package/OS thực tế. Không áp dụng lệnh recursive chown mù quáng vào tablespace mount không thuộc backup.

### 20.5. Cấu hình server

Kiểm tra postgresql.conf, pg_hba.conf, ident, SSL files, archive settings, port, listen_addresses, shared_preload_libraries và các cấu hình external path.

### 20.6. Start và theo dõi recovery

~~~bash
pg_ctl -D /var/lib/postgresql/16/main start
~~~

PostgreSQL đọc control/backup metadata và replay WAL cần thiết để đưa base backup tới trạng thái nhất quán. Đọc server log để xác nhận recovery hoàn tất.

### 20.7. Không chạy initdb lên backup

initdb tạo cluster mới và có thể phá hủy nội dung backup nếu chạy vào data directory đó. Restore physical backup không cần initdb.

## 21. Restore tar-format backup

Tar backup cần giải nén theo đúng layout:

~~~bash
mkdir -p /restore/pgdata
tar -xf /backup/base_tar/base.tar -C /restore/pgdata
~~~

Nếu có pg_wal.tar:

~~~bash
mkdir -p /restore/pgdata/pg_wal
tar -xf /backup/base_tar/pg_wal.tar -C /restore/pgdata/pg_wal
~~~

Các tablespace tar phải được extract vào directory tương ứng với tablespace đã map.

### 21.1. Kiểm tra danh sách tar

~~~bash
tar -tf /backup/base_tar/base.tar | head
~~~

### 21.2. Tablespace archive

Tên tar của tablespace thường liên quan OID. Đối chiếu tablespace_map và catalog metadata để đặt đúng đích.

### 21.3. Owner và mode

Sau khi extract, bảo đảm owner/mode đúng theo OS account PostgreSQL. Symlink tablespace phải trỏ đúng path.

### 21.4. WAL tar

Nếu WAL được lưu trong archive riêng, phải đặt vào pg_wal theo đúng layout. Không extract pg_wal.tar vào root của PGDATA.

### 21.5. Verify sau extract

Đối chiếu file inventory/checksum theo manifest nếu có cách verify phù hợp với format. Sau đó thực hiện restore drill.

## 22. Restore PITR từ base backup

Base backup giúp tạo data directory ban đầu; WAL archive giúp replay tới một target sau đó.

### 22.1. Chuẩn bị archive

Đảm bảo restore host đọc được các WAL segment và timeline history cần thiết.

### 22.2. restore_command

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
~~~

Command phải trả file raw đúng tại %p và exit code chính xác. Nếu archive nén/mã hóa, giải nén/giải mã vào %p.

### 22.3. recovery.signal

Trên PostgreSQL 12 trở lên, tạo recovery.signal trong PGDATA để yêu cầu archive recovery.

~~~bash
touch /restore/pgdata/recovery.signal
~~~

### 22.4. Recovery target time

~~~conf
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
~~~

Dùng timezone offset rõ ràng. Các target khác gồm LSN, named restore point và transaction ID.

### 22.5. Timeline

~~~conf
recovery_target_timeline = 'latest'
~~~

Chọn timeline theo mục tiêu. Nếu cần phục hồi một nhánh lịch sử cụ thể, đặt timeline ID thay vì tự động chọn latest.

### 22.6. Theo dõi recovery

Đọc PostgreSQL log, xem recovery state và xác nhận target đã đạt. Nếu action là pause, server dừng replay tại target cho phép kiểm tra trước khi promote/tiếp tục.

### 22.7. Recovery signal và standby signal

recovery.signal dùng cho archive recovery/PITR; standby.signal dùng để chạy standby. Không để nhầm hai file trong một quy trình restore.

## 23. Cấu hình external files và môi trường restore

Không phải mọi thứ PostgreSQL cần đều nằm trong physical backup.

### 23.1. Config file ngoài PGDATA

Nếu config_file, hba_file hoặc ident_file trỏ ra ngoài PGDATA, pg_basebackup không tự sao chép các file ngoài đó. Backup config riêng và bảo đảm đường dẫn restore đúng.

### 23.2. SSL certificates

Certificate/key có thể nằm ngoài data directory. Restore cần đúng file, owner/mode và secret.

### 23.3. Extensions

Physical backup có thể chứa catalog objects của extension, nhưng binary/shared libraries và OS packages cần có trên restore host với version tương thích.

### 23.4. Locale và collation

Khác biệt OS/locale/collation có thể ảnh hưởng index semantics và vận hành. Giữ môi trường restore tương thích, kiểm tra collation version sau recovery khi cần.

### 23.5. OS/architecture

Physical backup không phải định dạng portable như SQL dump. Dùng cùng PostgreSQL major version và nền tảng/build tương thích; không restore file-level backup trực tiếp sang major version khác.

## 24. Version compatibility và incremental backups

### 24.1. Same major version

Base backup vật lý thường được restore bởi server cùng major version. Minor release compatibility thường nằm trong cùng major, nhưng vẫn nên dùng bản vá phù hợp và kiểm tra extension/platform.

### 24.2. Khác major version

Không dùng pg_basebackup như cách nâng cấp trực tiếp từ PostgreSQL 15 sang 16 hoặc 17. Dùng pg_upgrade hoặc logical migration theo kế hoạch.

### 24.3. Tool version

Dùng pg_basebackup/pg_verifybackup từ bộ công cụ phù hợp với server. Các option và manifest features có thể khác giữa các major.

### 24.4. Incremental backup từ PostgreSQL 17

PostgreSQL 17 bổ sung incremental physical backup. Lệnh incremental tham chiếu manifest của backup trước; chain phụ thuộc vào các backup liên quan.

### 24.5. pg_combinebackup

Dùng pg_combinebackup để kết hợp full backup và incremental backups thành một data directory đầy đủ trước khi restore theo workflow được hỗ trợ.

### 24.6. Retention của incremental chain

Không xóa full backup hoặc incremental backup nền khi backup mới còn phụ thuộc vào chúng. Quản lý chain như một tập dependency.

## 25. Kiểm tra backup có thể restore

Một pipeline backup đáng tin cậy có nhiều lớp xác minh:

1. pg_basebackup exit code thành công.
2. Destination file inventory hợp lý.
3. Backup manifest có mặt nếu format/version hỗ trợ.
4. pg_verifybackup pass với plain backup.
5. WAL cần thiết có thể đọc và đúng cluster/timeline.
6. Tablespace paths và external config có đủ.
7. Restore thử vào host cô lập thành công.
8. PostgreSQL đạt trạng thái ready.
9. Business queries/invariants pass.
10. RTO được đo và đáp ứng mục tiêu.

### 25.1. File tồn tại chưa đủ

Một backup có đủ dung lượng có thể vẫn thiếu file, checksum mismatch hoặc thiếu WAL.

### 25.2. Verify pass chưa đủ

Verify không kiểm tra toàn bộ hạ tầng, secrets, extension libraries, DNS, network, application credentials hoặc WAL archive tới mọi target.

### 25.3. Restore test là bằng chứng mạnh nhất

Chỉ thử restore thực tế mới xác nhận các bước extract, ownership, config, WAL replay và application validation hoạt động cùng nhau.

## 26. Backup retention và WAL retention

Một base backup cần WAL từ điểm start của backup tới lúc backup nhất quán; PITR window cần thêm WAL sau đó tới target.

### 26.1. Full backup retention

Giữ số lượng/thời gian base backups phù hợp RPO/RTO, compliance và chi phí storage.

### 26.2. WAL dependency

Mỗi backup có một required WAL range. Nếu còn giữ backup đó, không được xóa các WAL segment cần thiết cho khả năng restore của backup và target window cam kết.

### 26.3. Không xóa theo ngày đơn giản

Xóa mọi WAL cũ hơn 7 ngày có thể làm hỏng khả năng restore một base backup cũ hơn vẫn còn trong retention.

### 26.4. Backup catalog

Quản lý backup ID, start/stop LSN, timeline, required WAL, manifest checksum, tablespaces và trạng thái verify.

### 26.5. Công cụ chuyên dụng

pgBackRest, WAL-G và các backup managers có thể quản lý repository, retention và archive lifecycle. Chọn một hệ thống có owner rõ ràng và không để hai retention jobs xung đột.

## 27. RPO, RTO và lịch backup

### 27.1. RPO

Recovery Point Objective là mức dữ liệu tối đa chấp nhận mất. Với physical base backup cộng WAL archive, RPO phụ thuộc độ trễ archive và khả năng lấy WAL mới nhất.

### 27.2. RTO

Recovery Time Objective là thời gian mục tiêu khôi phục dịch vụ. RTO phụ thuộc dung lượng backup, throughput restore, WAL replay volume, startup và application validation.

### 27.3. Base backup thường xuyên

Backup thường xuyên hơn làm giảm lượng WAL phải replay và có thể giảm RTO, nhưng tăng storage, network và tải nguồn.

### 27.4. WAL archive thường xuyên

Archive liên tục giúp PITR tới mốc gần hiện tại. Segment switch/timeout và archive throughput ảnh hưởng độ trễ.

### 27.5. Lịch theo workload

Chọn lịch dựa trên database growth, WAL rate, restore time test, retention và khung tải thấp. Không có một lịch phù hợp mọi cluster.

## 28. Monitoring pg_basebackup và backup repository

Theo dõi các chỉ số:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Backup start/end time | Thời gian backup |
| Backup duration | Ảnh hưởng tải và RTO |
| Backup bytes | Tốc độ tăng storage |
| Backup exit status | Thành công/thất bại |
| Source server/cluster ID | Đúng nguồn |
| Start/stop LSN | WAL dependency |
| WAL method | stream/fetch/none |
| Tablespace inventory | Đủ mọi tablespace |
| Manifest verify result | Integrity |
| WAL archive lag | Khả năng PITR |
| Restore drill result | Khả năng phục hồi |
| Repository free space | Headroom |
| Retention age | Policy compliance |

### 28.1. Theo dõi WAL senders

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

pg_basebackup connections có thể xuất hiện trong trạng thái replication phù hợp. Diễn giải theo server version và client application_name.

### 28.2. Theo dõi replication slots

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    wal_status
FROM pg_replication_slots;
~~~

Nếu slot không active lâu và restart_lsn cũ, kiểm tra lượng WAL đang bị giữ.

### 28.3. Backup logs

Ghi stdout/stderr, exit code và tool version. Không chỉ lưu dòng “backup completed” mà không có metadata định danh.

## 29. Lỗi thường gặp khi chạy pg_basebackup

### Lỗi 1. Replication permission denied

Role thiếu LOGIN/REPLICATION hoặc không được pg_hba.conf cho phép.

### Lỗi 2. No pg_hba.conf entry

Rule không khớp host, user, database=replication, SSL mode hoặc thứ tự rule.

### Lỗi 3. Too many replication connections

max_wal_senders không đủ cho backup, WAL streaming và standbys đồng thời.

### Lỗi 4. Replication slot limit reached

max_replication_slots không đủ hoặc slot name đã tồn tại.

### Lỗi 5. Destination not empty

Thư mục backup có file cũ hoặc không đúng điều kiện. Dùng destination riêng đã kiểm tra.

### Lỗi 6. Disk full

Backup destination hết dung lượng hoặc filesystem quota cạn.

### Lỗi 7. WAL removed before fetch

Dùng WAL method fetch nhưng server recycle segment cần thiết trước khi fetch hoàn tất. Dùng stream hoặc tăng retention đúng cách.

### Lỗi 8. Server restart/failover during backup

Connection bị gián đoạn; backup có thể không hoàn chỉnh. Kiểm tra log và tạo backup mới theo quy trình.

### Lỗi 9. Password authentication failed

Secret sai/hết hạn, pgpass format/permissions sai hoặc authentication policy không khớp.

### Lỗi 10. TLS verification failure

Certificate, CA hoặc hostname không khớp. Không tắt TLS verification như cách chữa mặc định.

### Lỗi 11. Tablespace path unavailable

Tablespace mount không tồn tại hoặc user OS không có quyền.

### Lỗi 12. Backup folder exists

Directory đích đã tồn tại và không rỗng. Không ghi đè backup cũ đang cần giữ.

### Lỗi 13. Manifest mismatch

File bị thay đổi, thiếu hoặc hỏng sau khi backup. Dùng pg_verifybackup và đối chiếu repository.

### Lỗi 14. Restore server major version mismatch

Physical files không thể dùng như bản restore trực tiếp cho major version khác.

### Lỗi 15. Missing WAL during recovery

Backup không có WAL cần thiết hoặc archive chain bị gap/retention xóa sớm.

### Lỗi 16. Missing tablespace files

Không backup/extract mọi tablespace hoặc symlink trỏ sai path.

### Lỗi 17. Extension library missing

Catalog chứa extension nhưng restore host không có shared library/package tương thích.

### Lỗi 18. Wrong ownership

Data directory hoặc tablespace không thuộc OS user PostgreSQL.

### Lỗi 19. -R tạo standby ngoài ý muốn

Backup được restore như một primary độc lập nhưng còn standby.signal/primary_conninfo. Kiểm tra mục tiêu restore trước khi start.

### Lỗi 20. Backup thành công nhưng chưa test restore

Không phát hiện các lỗi config, path, extension, WAL và secret cho tới khi sự cố xảy ra. Lập restore drill định kỳ.

## 30. Quy trình backup hằng ngày mẫu

Một pipeline cơ bản có thể gồm:

~~~text
Scheduler
   |
   v
Preflight
   |-- source reachable?
   |-- replication role works?
   |-- enough disk and WAL senders?
   |-- destination isolated and empty?
   |
   v
pg_basebackup
   |-- plain format
   |-- WAL stream
   |-- progress + log
   |
   v
Verify
   |-- exit code
   |-- manifest
   |-- pg_verifybackup
   |-- tablespace inventory
   |
   v
Publish backup metadata
   |
   v
Offsite copy / immutable retention
   |
   v
Periodic restore drill
~~~

### 30.1. Preflight

Kiểm tra server, replication access, sender capacity, slot capacity, disk space, mount và destination.

### 30.2. Backup

Chạy pg_basebackup với format/WAL method phù hợp và lưu log.

### 30.3. Verify

Với plain backup có manifest, chạy pg_verifybackup. Kiểm tra cả các file metadata và tablespaces.

### 30.4. Publish

Chỉ đánh dấu backup usable sau khi backup command và verify pass. Có thể dùng trạng thái temporary/in-progress rồi publish backup ID cuối.

### 30.5. Offsite

Copy backup và metadata sang repository khác failure domain. Verify checksum sau khi chuyển.

### 30.6. Retention

Dọn backup/WAL theo dependency đã được backup catalog xác định.

## 31. Restore drill và kiểm tra ứng dụng

Một restore drill cần được thực hiện trên host/volume cô lập:

1. Chọn một backup theo policy và xác nhận manifest.
2. Lấy WAL archive cần thiết nếu mục tiêu là PITR.
3. Chuẩn bị PostgreSQL cùng major version và extension binaries tương thích.
4. Restore plain files hoặc extract tar/tablespaces.
5. Khôi phục cấu hình ngoài PGDATA và secrets.
6. Cấu hình archive recovery nếu cần.
7. Start PostgreSQL và theo dõi recovery log.
8. Xác nhận server ready và đạt recovery target.
9. Chạy truy vấn kiểm tra schema, dữ liệu và business invariants.
10. Đo thời gian, throughput, WAL replay và RTO.
11. Lưu kết quả, lỗi và thay đổi runbook.

### 31.1. Không test restore trên production

Không ghi đè PGDATA production hoặc thay đổi primary chỉ để thử. Dùng một môi trường restore riêng.

### 31.2. Test cả failure cases

Thử backup thiếu WAL, checksum mismatch, tablespace mount lỗi, credential thiếu hoặc extension package không có trong lab để xác nhận runbook phát hiện được.

### 31.3. Restore point và PITR

Nếu cần khôi phục trước một thao tác sai, tạo target time/LSN/named restore point theo backup chain và kiểm tra dữ liệu sau target.

### 31.4. Đo RTO

Ghi riêng thời gian transfer, extract, startup/replay và validation. Tổng thời gian thực tế mới là RTO gần với trải nghiệm ứng dụng.

## 32. Backup, WAL và checkpoint

### 32.1. Checkpoint

Checkpoint ghi dirty buffers và tạo điểm recovery trong WAL. Checkpoint không phải base backup và không thay thế backup repository.

### 32.2. WAL

WAL bảo đảm recovery consistency và cho phép replay thay đổi sau base backup.

### 32.3. Base backup

Base backup chứa các data files tại một khoảng thời gian và metadata recovery.

### 32.4. Archive

WAL archive lưu lịch sử segment bên ngoài server để có thể replay sau khi WAL trong pg_wal đã được recycle.

### 32.5. Kết hợp

Checkpoint, WAL và base backup là các thành phần khác nhau trong durability/recovery. Không thay một thành phần bằng một thành phần khác.

## 33. pg_basebackup và các công cụ quản lý backup

### 33.1. pg_basebackup

Công cụ tích hợp, đơn giản, dùng replication protocol. Phù hợp để tạo physical base backup và dựng standby.

### 33.2. pgBackRest

Công cụ backup/restore chuyên dụng với repository, compression, encryption, retention, parallelism và WAL archiving theo cấu hình.

### 33.3. WAL-G

Công cụ backup/WAL archiving phổ biến, hỗ trợ object storage và các workflow backup/restore.

### 33.4. pg_verifybackup

Công cụ kiểm tra plain-format backup manifest theo khả năng phiên bản.

### 33.5. pg_combinebackup

Dùng với incremental backup workflow từ PostgreSQL 17 trở lên để kết hợp các backup cần thiết.

### 33.6. Chọn công cụ

Nếu chỉ cần một base backup cơ bản, pg_basebackup có thể đủ. Nếu cần retention phức tạp, incremental/differential workflows, parallelism, encryption và repository management, cân nhắc backup manager chuyên dụng.

## 34. Bài tập thực hành

Các bài tập dùng một PostgreSQL lab riêng. Không chạy các lệnh tạo backup/restore ghi đè dữ liệu trên production.

### Bài 1. Physical backup

Physical backup sao chép dữ liệu ở mức nào?

### Bài 2. Logical backup

Nêu một khác biệt quan trọng giữa pg_basebackup và pg_dump.

### Bài 3. Cluster

Vì sao pg_basebackup thường backup cả cluster thay vì một bảng?

### Bài 4. Online backup

Vì sao không thể copy PGDATA đang chạy bằng một lệnh filesystem thông thường?

### Bài 5. WAL

WAL đóng vai trò gì trong online physical backup?

### Bài 6. Replication role

Role chạy pg_basebackup cần quyền nào?

### Bài 7. pg_hba

Viết một ví dụ rule hostssl cho replication user từ subnet riêng.

### Bài 8. max_wal_senders

Vì sao -X stream có thể cần hai WAL sender connections?

### Bài 9. max_replication_slots

Tham số này liên quan tới workflow nào?

### Bài 10. Plain format

Plain format lưu backup theo cấu trúc nào?

### Bài 11. Tar format

Vì sao tar backup cần extract tablespace riêng?

### Bài 12. WAL stream

Ưu điểm chính của -X stream là gì?

### Bài 13. WAL fetch

Rủi ro chính của -X fetch là gì?

### Bài 14. WAL none

Khi nào có thể dùng -X none?

### Bài 15. Progress

Tùy chọn nào hiển thị tiến độ backup?

### Bài 16. Checkpoint

Khác biệt giữa checkpoint fast và spread?

### Bài 17. Rate limit

Khi nào nên giới hạn tốc độ backup?

### Bài 18. Tablespace

Viết SQL liệt kê tablespace và location.

### Bài 19. Mapping

Ý nghĩa tùy chọn -T olddir=newdir?

### Bài 20. -R

-R tạo những file/cấu hình gì?

### Bài 21. Replication slot

Vì sao slot inactive có thể làm pg_wal tăng?

### Bài 22. Backup from standby

Nêu hai điều kiện cần chú ý khi backup từ standby.

### Bài 23. Manifest

backup_manifest giúp ích gì?

### Bài 24. pg_verifybackup

Công cụ này xác minh điều gì và format nào được hỗ trợ trực tiếp?

### Bài 25. Restore

Vì sao không chạy initdb lên data directory đã restore?

### Bài 26. Tar restore

pg_wal.tar phải được extract vào đâu?

### Bài 27. PITR

Nêu ba thành phần cần có để restore base backup tới một recovery target.

### Bài 28. recovery.signal

File này dùng cho mục đích gì trong PostgreSQL 12+?

### Bài 29. Major version

Có thể restore physical backup PostgreSQL 15 trực tiếp bằng PostgreSQL 16 không?

### Bài 30. External config

Vì sao config_file nằm ngoài PGDATA cần backup riêng?

### Bài 31. Incremental backup

PostgreSQL 17 incremental backup cần công cụ nào để combine chain?

### Bài 32. Retention

Vì sao không xóa WAL chỉ dựa trên tuổi file?

### Bài 33. RPO

WAL archive lag ảnh hưởng RPO thế nào?

### Bài 34. RTO

Nêu ba yếu tố làm tăng thời gian restore.

### Bài 35. Backup metadata

Nêu ít nhất năm trường nên ghi cho mỗi backup.

### Bài 36. Backup failure

Kể bốn nguyên nhân khiến pg_basebackup thất bại.

### Bài 37. Verify failure

Manifest mismatch có thể chỉ ra điều gì?

### Bài 38. Restore drill

Nêu năm bước quan trọng của một restore drill.

### Bài 39. Logical và physical

Khi cần backup riêng một table, chọn hướng nào?

### Bài 40. Thiết kế

Đề xuất pipeline từ pg_basebackup tới verify, offsite retention và restore test.

## 35. Lời giải tham khảo

### Bài 1–5. Physical và WAL

Physical backup sao chép file storage của cluster. pg_basebackup tạo bản sao vật lý toàn cluster qua replication/backup protocol; pg_dump xuất schema/data ở mức SQL và có thể chọn database/table. Không copy PGDATA đang chạy tùy tiện vì các file có thể phản ánh những thời điểm khác nhau. WAL cho phép replay và làm backup nhất quán.

### Bài 6–9. Quyền và capacity

Role cần LOGIN và REPLICATION (hoặc quyền quản trị tương ứng). Ví dụ:

~~~sql
CREATE ROLE backup_user WITH LOGIN REPLICATION PASSWORD 'use-a-secret';
~~~

pg_hba:

~~~conf
hostssl replication backup_user 10.20.0.0/24 scram-sha-256
~~~

-X stream có thể mở một kết nối cho backup và một kết nối stream WAL. max_wal_senders phải đủ cho hai kết nối đó cộng standbys/backups khác. max_replication_slots giới hạn số replication slots.

### Bài 10–14. Format và WAL method

Plain lưu cấu trúc data directory; tar đóng gói base/WAL/tablespace thành tar archives. Tar tablespaces cần extract đúng path. stream lấy WAL đồng thời; fetch lấy sau nên WAL phải còn trên server; none yêu cầu một quy trình WAL độc lập bảo đảm consistency.

### Bài 15–17. Tốc độ

-P hiển thị progress. Checkpoint fast hoàn tất nhanh nhưng có thể gây I/O spike; spread dàn tải. Rate limit hữu ích khi cần hạn chế ảnh hưởng production, nhưng kéo dài backup và WAL retention.

### Bài 18–20. Tablespace và standby

~~~sql
SELECT spcname, pg_tablespace_location(oid)
FROM pg_tablespace;
~~~

-T remap old tablespace path sang new path theo format/version hỗ trợ. -R tạo standby.signal và ghi connection settings vào postgresql.auto.conf.

### Bài 21–22. Slots và standby

Slot inactive giữ WAL từ restart_lsn để consumer còn có thể đọc, có thể làm đầy pg_wal. Khi backup từ standby, kiểm tra standby state/hot_standby, sender capacity, WAL availability và full_page_writes trên primary.

### Bài 23–24. Verify

backup_manifest liệt kê file/checksum. pg_verifybackup xác minh plain-format backup theo manifest và các kiểm tra WAL hỗ trợ; không thay restore test và không dùng trực tiếp như plain format với tar backup.

### Bài 25–30. Restore

Không chạy initdb vì nó tạo cluster mới. pg_wal.tar extract vào PGDATA/pg_wal. PITR cần base backup, WAL chain và restore settings/target. recovery.signal bắt đầu archive recovery trong PostgreSQL 12+. Physical backup không restore trực tiếp qua major version. Config file nằm ngoài PGDATA phải backup riêng.

### Bài 31. Incremental

Dùng pg_combinebackup để kết hợp full và incremental backup theo workflow PostgreSQL 17+.

### Bài 32–34. Retention và objectives

WAL cũ có thể còn cần cho base backup đang giữ. Archive lag làm tăng lượng dữ liệu có thể mất và ảnh hưởng RPO. Restore chậm do backup lớn, storage/network chậm, WAL replay nhiều và application validation lâu.

### Bài 35. Metadata

Ví dụ: backup ID, source host, system identifier, PostgreSQL/tool version, timestamp, start/stop LSN, timeline, format, WAL method, tablespace map, manifest/checksum, verify status.

### Bài 36–37. Lỗi

Nguyên nhân: quyền replication/pg_hba sai, max_wal_senders thiếu, slot limit, disk full, destination không rỗng, WAL bị recycle khi fetch, network/TLS lỗi, tablespace mount lỗi. Manifest mismatch chỉ ra file thiếu/thay đổi/hỏng hoặc backup bị sửa sau khi tạo.

### Bài 38. Restore drill

Chọn backup; verify manifest và WAL dependencies; restore vào môi trường cô lập; cấu hình tablespaces/config/recovery; start/replay WAL; kiểm tra business data; ghi thời gian và kết quả.

### Bài 39–40. Chọn giải pháp

Backup riêng table thường dùng pg_dump hoặc logical export. Pipeline physical backup gồm preflight, pg_basebackup, exit/log check, pg_verifybackup nếu plain, inventory metadata, offsite copy, retention theo WAL dependency và restore drill định kỳ.

## 36. Bảng tra cứu nhanh

| Nhu cầu | Công cụ/tùy chọn |
| --- | --- |
| Tạo physical backup | pg_basebackup |
| Chọn thư mục đích | -D |
| Chọn plain/tar | -F |
| Stream WAL | -X stream |
| Fetch WAL sau copy | -X fetch |
| Không lấy WAL | -X none |
| Hiển thị progress | -P |
| Verbose | -v |
| Backup label | -l |
| Checkpoint mode | -c fast hoặc spread |
| Giới hạn tốc độ | --max-rate |
| Mapping tablespace | -T olddir=newdir |
| Tạo standby config | -R |
| Tạo replication slot | -C |
| Dùng slot name | -S |
| Verify plain backup | pg_verifybackup |
| Kết hợp incremental chain | pg_combinebackup |
| Liệt kê tablespaces | pg_tablespace |
| Theo dõi WAL senders | pg_stat_replication |
| Theo dõi slots | pg_replication_slots |
| PITR signal | recovery.signal |
| Standby signal | standby.signal |
| Recovery lấy WAL | restore_command |

## 37. Checklist vận hành physical backup

1. Xác định backup là physical hay logical và scope cần bảo vệ.
2. Ghi PostgreSQL major/minor version và cluster system identifier.
3. Dùng pg_basebackup binary phù hợp với server.
4. Bật wal_level phù hợp và kiểm tra full_page_writes.
5. Cấp role LOGIN/REPLICATION với quyền tối thiểu.
6. Cấu hình pg_hba replication rule, TLS và secret storage.
7. Đảm bảo max_wal_senders đủ cho backup/standby concurrency.
8. Đảm bảo max_replication_slots đủ nếu dùng named slots.
9. Kiểm tra slot lifecycle và WAL retention headroom.
10. Kiểm tra destination rỗng, disk quota và offsite repository.
11. Chọn plain hoặc tar theo restore/verify tooling.
12. Chọn WAL stream/fetch/none có chủ đích.
13. Đánh giá checkpoint mode, max rate và thời gian backup.
14. Lập inventory mọi tablespaces.
15. Mapping tablespace khi restore sang path khác.
16. Lưu backup_label, tablespace_map và backup_manifest.
17. Lưu start/stop LSN, timeline và backup ID.
18. Ghi log/exit code và chỉ publish backup sau khi hoàn tất.
19. Chạy pg_verifybackup với plain backup có manifest.
20. Kiểm tra WAL archive dependencies.
21. Backup riêng config/SSL/secrets ngoài PGDATA.
22. Giữ extension binaries và OS dependencies tương thích.
23. Mã hóa backup và giới hạn quyền truy cập.
24. Copy sang failure domain khác.
25. Retention theo dependency của base backup và WAL.
26. Không xóa WAL chỉ dựa trên tuổi file.
27. Theo dõi backup duration, size, error rate và repository free space.
28. Restore thử vào môi trường cô lập.
29. Kiểm tra PostgreSQL startup và business invariants.
30. Ghi RTO thực tế, cập nhật runbook và diễn tập định kỳ.

## 38. Tổng kết

pg_basebackup tạo **physical base backup** của một PostgreSQL cluster đang chạy bằng replication/backup protocol. Nó sao chép data files và phối hợp WAL để bản sao có thể được phục hồi nhất quán. Chọn plain hoặc tar format, stream/fetch/none WAL method, checkpoint mode, rate limit và tablespace mapping theo mục tiêu restore cũng như tải hệ thống.

Để chạy an toàn, cần replication access đúng, đủ WAL senders/slots, disk headroom và archive retention phù hợp. Backup có thể được dùng để restore độc lập, dựng standby bằng -R hoặc làm nền cho PITR với WAL archive. Manifest và pg_verifybackup giúp phát hiện một số lỗi file, nhưng chỉ restore drill mới kiểm chứng được toàn bộ đường đi từ backup tới database hoạt động.

Hãy quản lý mỗi backup cùng metadata về cluster, version, LSN, timeline, tablespaces, checksum và WAL dependencies. Giữ backup ở failure domain riêng, bảo vệ key/config, retention theo chain và thường xuyên thử khôi phục. Một bản physical backup chỉ thực sự có giá trị khi tổ chức có thể tìm đúng file, replay đúng WAL và đưa ứng dụng trở lại trong RPO/RTO đã cam kết.
