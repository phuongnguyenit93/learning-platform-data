# Sao lưu nền kết hợp lưu trữ WAL trong PostgreSQL

## 1. Vì sao một bản sao thư mục dữ liệu chưa đủ?

Một database PostgreSQL đang hoạt động liên tục thay đổi pages, WAL, control metadata và các file relation. Nếu chỉ copy thư mục dữ liệu khi server đang chạy bằng một lệnh sao chép file thông thường, ta có thể thu được một tập file không nhất quán về thời điểm. Một page có thể được copy trước thay đổi, page khác sau thay đổi; WAL cần để phục hồi cũng có thể chưa nằm trong bản sao.

PostgreSQL giải quyết bài toán backup vật lý bằng một **base backup nhất quán** kết hợp với **WAL (Write-Ahead Logging)**. Base backup cung cấp điểm bắt đầu đầy đủ; WAL archive cung cấp chuỗi thay đổi cần thiết để đưa bản sao tới trạng thái nhất quán và/hoặc một thời điểm phục hồi mong muốn.

```text
                 PRIMARY POSTGRESQL
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Base backup                WAL stream
       (snapshot nền)             (segments)
             |                       |
             v                       v
      Backup repository       WAL archive repository
             |                       |
             +-----------+-----------+
                         |
                         v
              Restore + WAL replay
                         |
                         v
              Consistent recovery point
                         |
                         v
                  Application online
```

Một chiến lược kết hợp base backup và WAL archiving hỗ trợ:

- Phục hồi sau mất ổ đĩa hoặc mất node.
- Phục hồi tới một thời điểm trước khi người dùng xóa nhầm dữ liệu.
- Tạo bản sao database nhất quán để khôi phục trên máy khác.
- Xây dựng standby từ base backup và tiếp tục nhận WAL.
- Đáp ứng mục tiêu RPO/RTO có thể đo lường.
- Giữ khả năng điều tra sự cố theo timeline khi có backup và WAL phù hợp.

**Base backup là điểm xuất phát; WAL liên tục là phần giúp tiến tới thời điểm phục hồi.** Có một trong hai mà thiếu phần còn lại thì khả năng PITR có thể không tồn tại.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt physical backup, logical backup, base backup và WAL archive.
2. Giải thích vì sao backup đang chạy phải được tạo bằng quy trình có tính nhất quán.
3. Hiểu WAL segment, WAL record, LSN, timeline và checkpoint ở mức vận hành.
4. Cấu hình các tham số cơ bản cho WAL archiving.
5. Dùng pg_basebackup để tạo base backup vật lý.
6. Hiểu các lựa chọn WAL method: stream, fetch và none.
7. Thiết kế archive command/library có tính lặp an toàn và không mất file.
8. Theo dõi pg_stat_archiver và archive backlog.
9. Lập retention policy giữ đủ WAL cho mọi base backup còn được hỗ trợ.
10. Khôi phục từ base backup và replay WAL tới một thời điểm cụ thể.
11. Hiểu recovery.signal, restore_command và recovery target.
12. Xử lý timeline sau failover/promotion.
13. Bảo vệ backup bằng encryption, access control, checksums và offsite copies.
14. Đo RPO/RTO và tổ chức restore drills.
15. Phân biệt backup thành công về mặt kỹ thuật với khả năng restore đã được chứng minh.

---

## 2. Physical backup và logical backup

PostgreSQL có hai nhóm backup phổ biến.

| Nhóm | Công cụ/ví dụ | Dữ liệu thu được | Mục đích |
|---|---|---|---|
| Physical backup | pg_basebackup, snapshot được hỗ trợ | Files vật lý của cluster hoặc phạm vi được hỗ trợ | Restore cluster, standby, PITR với WAL |
| Logical backup | pg_dump, pg_dumpall | SQL/custom/archive representation của objects/data | Di chuyển schema/data, backup object-level |

### 2.1. Physical backup

Physical backup sao chép cấu trúc lưu trữ của PostgreSQL, gồm relation files, metadata và các thành phần cần thiết. Để tạo bản backup nhất quán khi server đang hoạt động, phải dùng PostgreSQL backup protocol/tool hoặc quy trình snapshot được tài liệu hóa.

Base backup vật lý thường gắn với một PostgreSQL major version và các yêu cầu tương thích nền tảng/build. Không giả định có thể lấy PG 16 data directory rồi khởi động trực tiếp bằng PG 17. Major upgrade cần quy trình như pg_upgrade hoặc logical migration phù hợp.

### 2.2. Logical backup

Ví dụ:

```bash
pg_dump -Fc -d appdb -f appdb.dump
pg_dumpall --globals-only -f globals.sql
```

Logical backup hữu ích khi:
- Chỉ cần một database/schema/table.
- Muốn di chuyển giữa các major versions.
- Muốn kiểm soát objects được restore.
- Cần xuất dữ liệu portable hơn file vật lý.

Nhưng logical dump không phải WAL archive và không tự cung cấp continuous point-in-time recovery cho từng commit sau thời điểm dump.

### 2.3. Hai loại có thể bổ sung cho nhau

Một chiến lược có thể dùng:
- Physical base backup + WAL archive cho disaster recovery và PITR.
- Logical dump định kỳ cho portability, object-level recovery hoặc kiểm tra độc lập.
- Export dữ liệu quan trọng theo nhu cầu nghiệp vụ.

Không dùng logical dump thay cho WAL archive khi yêu cầu phục hồi tới từng thời điểm trong một cửa sổ liên tục.

## 3. Base backup là gì?

Base backup là một bản sao vật lý nhất quán của cluster hoặc phạm vi backup được PostgreSQL hỗ trợ, tại một khoảng thời gian bắt đầu/kết thúc xác định.

Một base backup có thể chứa:
- Các data files của cluster.
- System catalogs và relation files.
- Tablespace mappings cần thiết.
- Backup metadata/manifest.
- WAL cần để làm bản backup nhất quán, tùy cách tạo.

Khi backup một server đang hoạt động, các pages có thể được copy ở những thời điểm khác nhau. PostgreSQL ghi nhận backup start/stop và dùng WAL để phục hồi các thay đổi cần thiết, đưa bản sao về trạng thái nhất quán.

### 3.1. Base backup không phải snapshot đơn giản tại một mili giây

Một backup vật lý thường là một quá trình copy kéo dài. Khả năng restore phụ thuộc WAL cần thiết để hoàn tất recovery. Vì vậy không thể chỉ kiểm tra thư mục backup có đủ file rồi kết luận có thể start server.

### 3.2. Base backup và WAL phải thuộc cùng lịch sử

WAL cần cho backup phải liên tục và đúng timeline. Nếu thiếu segment ở giữa, recovery có thể dừng trước mục tiêu mong muốn hoặc không hoàn thành.

### 3.3. Backup consistency do PostgreSQL protocol quản lý

Dùng pg_basebackup hoặc giải pháp snapshot được PostgreSQL hỗ trợ. Không tự copy PGDATA đang chạy bằng robocopy/cp rồi coi đó là base backup hợp lệ.

## 4. WAL là gì?

WAL là nhật ký thay đổi theo thứ tự mà PostgreSQL sử dụng cho crash recovery, replication và một số khả năng backup/recovery.

Khi transaction thay đổi dữ liệu, PostgreSQL tạo WAL records mô tả các thay đổi cần thiết. Theo nguyên tắc write-ahead, WAL phải được ghi bền vững trước khi data pages tương ứng được ghi bền vững.

```text
SQL INSERT / UPDATE / DELETE
             |
             v
      Buffer / heap changes
             |
             v
        WAL records
             |
             v
       WAL flush at commit
             |
             v
       Commit acknowledged
             |
             v
     Data pages written later
```

### 4.1. WAL record

Một WAL record mô tả một thay đổi hoặc nhóm thay đổi nội bộ. Nó không phải câu SQL nguyên văn để replay như script SQL.

### 4.2. WAL segment

WAL được chia thành các segment files có kích thước do cấu hình/build xác định. Segment names mã hóa timeline và vị trí WAL; không tự đặt tên theo ngày tháng.

Kích thước segment phổ biến trong nhiều bản build là 16 MiB, nhưng phải kiểm tra server thực tế, ví dụ qua pg_controldata hoặc công cụ phù hợp. Không hard-code kích thước này vào hệ thống archive.

### 4.3. LSN

LSN (Log Sequence Number) xác định vị trí trong WAL stream, thường hiển thị dạng:

```text
0/16B6C50
```

LSN là vị trí log, không phải timestamp. Có thể dùng pg_wal_lsn_diff để tính khoảng cách byte giữa hai LSN.

### 4.4. WAL không phải audit log

WAL phục vụ recovery/replication. Không dùng nó như một bảng audit business dễ đọc. Nếu cần lưu actor, thời gian nghiệp vụ và nội dung hành động, thiết kế audit/event records riêng.

## 5. Continuous archiving là gì?

WAL archiving sao chép các WAL segments đã hoàn tất từ pg_wal tới một archive repository bền vững.

Khi bật archiving, PostgreSQL gọi cơ chế archive khi segment sẵn sàng. Nếu archive command/library báo thất bại, PostgreSQL có thể thử lại theo cơ chế của server.

```text
PostgreSQL primary
    |
    +-- pg_wal/segment A
    |       |
    |       v
    |    archive process
    |       |
    |       v
    |    durable archive storage
    |
    +-- pg_wal/segment B
            |
            v
         archive process
            |
            v
         durable archive storage
```

### 5.1. WAL archiving không phải streaming replication

- Streaming replication truyền WAL tới standby đang hoạt động qua replication protocol.
- WAL archiving lưu các segment vào kho archive để backup/recovery.
- Hai cơ chế có thể chạy song song, phục vụ mục đích khác nhau.

### 5.2. Archiving có độ trễ

Một WAL segment thường được archive khi hoàn tất hoặc được switch. Vì vậy WAL mới nhất có thể vẫn nằm trong segment đang mở ở pg_wal.

archive_timeout có thể buộc switch WAL theo khoảng thời gian trong workload ít ghi, nhưng không biến mỗi transaction thành một file archive riêng.

### 5.3. PITR cần WAL liên tục

Để restore một base backup tới target time, cần mọi WAL segment cần thiết từ điểm bắt đầu recovery tới mục tiêu, cùng timeline history files liên quan.

## 6. Những điều kiện cấu hình cần có

Các cấu hình chính thường gồm:

```conf
wal_level = replica
archive_mode = on
archive_command = '...'
```

### 6.1. wal_level

wal_level xác định lượng thông tin được ghi trong WAL cho các tính năng như replication/archiving. Với physical streaming replication và WAL archiving thông thường, mức replica là lựa chọn phổ biến.

### 6.2. archive_mode

archive_mode = on bật WAL archiving trên primary/standalone server. Thay đổi tham số này thường cần restart PostgreSQL, không chỉ reload.

Một số version hỗ trợ archive_mode = always để archive WAL trong recovery/standby contexts. Chỉ bật khi hiểu kiến trúc archive nhiều node/timeline và nguy cơ trùng tên/ghi đè.

### 6.3. archive_command hoặc archive_library

archive_command gọi chương trình ngoài để archive từng segment. Một số phiên bản hỗ trợ archive_library cho cơ chế archive qua library. Hai lựa chọn có semantics/cấu hình riêng và phụ thuộc version.

### 6.4. Kiểm tra cấu hình hiện tại

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'archive_mode',
    'archive_command',
    'archive_library',
    'archive_timeout',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_wal_size',
    'min_wal_size',
    'full_page_writes'
)
ORDER BY name;
```

Không phải mọi server version đều có mọi setting; query cần thích ứng với pg_settings thực tế.

## 7. Cấu hình archive_command

PostgreSQL cung cấp hai placeholder phổ biến:

- %p: đường dẫn đầy đủ tới file WAL cần archive.
- %f: tên file WAL.

Ví dụ minh họa trên một môi trường lab Unix:

```conf
archive_mode = on
archive_command = 'test ! -f /srv/pgarchive/%f && cp %p /srv/pgarchive/%f'
```

Đây là ví dụ tối giản, không phải script production hoàn chỉnh. Cần tạo thư mục trước, cấp quyền đúng và xử lý durability/atomicity.

### 7.1. Exit status rất quan trọng

- Exit code 0: PostgreSQL coi file đã được archive thành công.
- Exit code khác 0: PostgreSQL coi archive attempt thất bại và có thể retry.

Không trả về 0 trước khi file thực sự được lưu bền vững ở đích theo yêu cầu của hệ thống.

### 7.2. Archive command phải idempotent

PostgreSQL có thể gọi lại cùng một WAL file sau lỗi/restart. Archive script cần xử lý trường hợp file đích đã tồn tại:

- Nếu file đích giống hệt nguồn, có thể coi là đã archive.
- Nếu file đích khác nội dung, phải báo lỗi và điều tra.
- Không ghi đè file archive khác nội dung một cách âm thầm.

### 7.3. Không dùng tên file do user input

WAL filename được PostgreSQL cung cấp. Tuy vậy script vẫn phải quote/validate tham số theo shell và tránh ghép chuỗi không an toàn.

### 7.4. Atomic copy

Một quy trình chắc chắn thường:
1. Copy sang file tạm trong cùng filesystem/repository.
2. Xác minh kích thước/checksum.
3. Flush/durable write theo storage guarantees.
4. Atomic rename tới tên đích cuối cùng.
5. Chỉ trả exit 0 sau khi bước cần thiết hoàn tất.

Với object storage, dùng cơ chế upload multipart/commit và xác minh object hoàn chỉnh; không giả định copy lệnh đơn giản có cùng semantics.

### 7.5. Không xóa source WAL trong archive command

PostgreSQL quản lý WAL trong pg_wal. Archive command chỉ sao chép; không tự xóa source segment hoặc sửa các file WAL đang được server dùng.

## 8. Archive storage: local, network và object storage

Có thể lưu WAL archive tại:
- Filesystem riêng trên cùng host.
- Storage volume khác.
- NFS/SMB được hỗ trợ và kiểm thử.
- Backup server ở mạng riêng.
- Object storage qua công cụ/library phù hợp.
- Dịch vụ backup managed.

### 8.1. Cùng host không đủ chống thảm họa

Nếu PGDATA và archive nằm cùng một ổ/VM/region, một sự cố vật lý hoặc xóa nhầm có thể làm mất cả hai.

### 8.2. Offsite/independent failure domain

Archive nên nằm ở failure domain khác phù hợp với yêu cầu DR: máy khác, storage khác, region khác hoặc immutable backup repository.

### 8.3. Archive storage cần durability và availability

Một kho archive bị full, hết quota, mất credentials hoặc network timeout có thể làm archiver thất bại. Theo dõi dung lượng, quyền truy cập và lỗi upload.

### 8.4. Object storage cần semantics riêng

Đảm bảo object upload hoàn tất, không bị overwrite ngoài ý muốn, checksum được xác minh và lifecycle policy không xóa WAL cần cho base backups còn hiệu lực.

## 9. Bảo vệ archive_command và credentials

Archive command thường chạy dưới operating-system user của PostgreSQL server. Vì vậy:

- Chỉ cấp quyền cần thiết cho thư mục/archive client.
- Không hard-code cloud secret trong file config có quyền đọc rộng.
- Dùng credential provider/secret store phù hợp.
- Bảo vệ .pgpass nếu dùng password cho backup connection.
- Giới hạn network egress/ingress theo kiến trúc.
- Ghi log lỗi nhưng không ghi secret/token.
- Tách quyền đọc archive khỏi quyền xóa retention nếu có thể.

### 9.1. Encryption at rest và in transit

WAL archive có thể chứa nội dung dữ liệu nhạy cảm ở dạng vật lý. Bảo vệ bằng:
- Encryption at rest ở storage layer hoặc client-side encryption.
- TLS khi truyền qua mạng.
- Key management độc lập với server/database.
- Rotation và kiểm tra khả năng decrypt trong restore drill.

Encryption không thay checksum, access control hoặc restore tests.

### 9.2. Immutable/WORM storage

Đối với ransomware/credential compromise, cân nhắc object lock/immutable retention hoặc tài khoản backup riêng. Backup administrator không nên có cùng quyền xóa toàn bộ bản production và bản DR.

### 9.3. Backup cũng là dữ liệu production

Base backups và WAL archive chứa nhiều dữ liệu hơn một query result thông thường. Áp dụng phân loại dữ liệu, access logging, retention và xóa an toàn.

## 10. pg_basebackup: tạo base backup vật lý

pg_basebackup là công cụ client PostgreSQL dùng replication protocol để tạo base backup từ server đang chạy.

Ví dụ dạng plain:

```bash
pg_basebackup \
  -h db-primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backup/postgres/base/2026-11-14T010000Z \
  -F plain \
  -X stream \
  -P \
  -v
```

Đây là cú pháp minh họa. Đường dẫn, host, user và credential phải được điều chỉnh cho môi trường thật.

### 10.1. Các tham số chính

| Tham số | Ý nghĩa |
|---|---|
| -h | Host PostgreSQL |
| -p | Port |
| -U | User backup |
| -D | Thư mục đích |
| -F plain | Ghi cấu trúc thư mục giống data directory |
| -F tar | Ghi các tar archives |
| -X stream | Stream WAL cần thiết trong lúc base backup |
| -X fetch | Lấy WAL cần thiết ở cuối backup từ server/archive theo điều kiện |
| -X none | Không tự lấy WAL theo method này; caller phải bảo đảm WAL cần thiết |
| -P | Hiển thị progress |
| -v | Verbose |
| -c fast | Yêu cầu checkpoint nhanh thay vì spread |
| -R | Tạo cấu hình để backup directory dùng làm standby theo semantics công cụ/version |
| -C -S name | Tạo replication slot có tên trong những cấu hình phù hợp |

### 10.2. Chọn WAL method

stream thường tiện cho base backup độc lập vì WAL cần thiết được stream đồng thời vào backup. Nó cần đủ WAL sender capacity và có thể mở thêm replication connection.

fetch lấy WAL cần thiết ở cuối quá trình; các segment phải còn sẵn trên server hoặc trong archive theo điều kiện tool. Nếu WAL đã bị recycle trước khi fetch, backup có thể thất bại.

none không tự bảo đảm backup có đủ WAL để hoàn tất recovery. Chỉ dùng khi một quy trình khác đã bảo đảm WAL continuity.

### 10.3. Không nhầm -R với PITR

-R hỗ trợ cấu hình backup thành standby, ví dụ tạo standby.signal và connection settings phù hợp. Nó không tự cấu hình recovery target time để phục hồi một database độc lập tới thời điểm mong muốn.

### 10.4. Tar và plain format

- Plain format tạo cây thư mục backup; tiện cho restore vật lý trực tiếp sau khi xử lý target directory.
- Tar format tạo các archive files, thuận tiện lưu trữ/chuyển giao; cần giải nén đúng cách khi restore.

Kiểm tra tài liệu đúng phiên bản cho tên file tar, WAL tar và tablespace mapping.

## 11. Tạo backup user và quyền kết nối

pg_basebackup sử dụng replication protocol. User backup cần quyền phù hợp, thường gồm REPLICATION và LOGIN, cùng một rule trong pg_hba.conf.

Ví dụ SQL:

```sql
CREATE ROLE backup_user
    WITH LOGIN REPLICATION;
```

Ví dụ pg_hba.conf cho một subnet được giới hạn:

```conf
host    replication    backup_user    10.20.30.40/32    scram-sha-256
```

Địa chỉ IP là ví dụ. Chỉ mở cho backup host cụ thể, dùng TLS khi phù hợp và quản lý mật khẩu bằng cơ chế an toàn.

### 11.1. Replication connections cần capacity

Kiểm tra:
- max_wal_senders.
- max_replication_slots.
- Các standby/CDC/backup jobs đang sử dụng sender.
- Connection limit của user.
- Network throughput.

### 11.2. Password không nên nằm trên command line

Dùng .pgpass với quyền file phù hợp trên Unix hoặc cơ chế credential an toàn của môi trường. Không đưa password trực tiếp vào script/log/process list.

### 11.3. Tách backup role khỏi superuser

Không cấp superuser chỉ để chạy pg_basebackup nếu role replication và quyền cần thiết đã đủ theo version/configuration.

## 12. Replication slots và pg_basebackup

Có thể yêu cầu pg_basebackup dùng/tạo replication slot trong những tình huống phù hợp.

Slot giúp giữ WAL cần thiết cho consumer, nhưng slot không tự archive WAL sang kho backup.

### 12.1. Slot là một ràng buộc retention

Nếu consumer ngừng hoạt động, slot có thể giữ WAL và làm pg_wal tăng dung lượng. Theo dõi slot inactive và WAL retention.

### 12.2. Temporary slot và permanent slot

pg_basebackup có các tùy chọn liên quan slot tùy version. Temporary slot có lifecycle khác permanent slot. Kiểm tra chính xác khi sử dụng các tùy chọn tạo/chọn slot.

### 12.3. Không tạo slot cho mọi backup mà không theo dõi

Slot tồn tại lâu có thể giữ WAL không giới hạn nếu consumer không tiến triển. Backup job phải cleanup slot theo policy khi kết thúc hoặc thất bại, nhưng không xóa slot thuộc standby/CDC khác.

### 12.4. max_slot_wal_keep_size

Một số version hỗ trợ giới hạn WAL giữ bởi replication slots qua tham số này. Giới hạn có thể khiến slot bị invalidated nếu consumer quá chậm; nó không thay monitoring.

## 13. Checkpoint và tác động của base backup

Để bắt đầu backup, PostgreSQL cần một checkpoint phù hợp. pg_basebackup có lựa chọn checkpoint behavior:

- fast: yêu cầu checkpoint nhanh, có thể tạo I/O burst.
- spread: phân bổ checkpoint work theo cơ chế server, giảm spike trong một số workload nhưng có thể kéo dài.

Kiểm tra tham số liên quan và lựa chọn theo SLO.

### 13.1. Backup có thể tăng I/O

Base backup đọc nhiều dữ liệu, có thể cạnh tranh cache/storage với query production. Hãy đo throughput đọc, latency database, CPU/network, WAL generation, replica lag và thời gian hoàn thành.

### 13.2. Chọn cửa sổ theo workload

Nếu backup full đọc 4 TB và storage chỉ có 300 MB/s khả dụng, duration tối thiểu đã đáng kể trước khi tính overhead. Dùng lịch theo tải và capacity thực tế.

### 13.3. Không ép checkpoint fast trong mọi lần

Checkpoint fast có thể tạo write burst lớn. Chọn theo khả năng chịu tải, không theo giả định nhanh hơn luôn tốt.

## 14. Backup manifest và kiểm tra base backup

Các phiên bản PostgreSQL hiện đại có thể tạo backup manifest chứa danh sách file/kích thước/checksum cho base backup được hỗ trợ.

Có thể dùng:

```bash
pg_verifybackup /backup/postgres/base/2026-11-14T010000Z
```

Công cụ này kiểm tra tính nhất quán của backup với manifest và checksums theo khả năng/version. Đây là bước verification hữu ích.

### 14.1. Verify không đồng nghĩa restore test

Manifest hợp lệ không chứng minh:
- Archive WAL đầy đủ tới recovery target.
- Restore host có đủ dung lượng/quyền.
- Credentials/KMS keys hoạt động.
- Application có thể kết nối và dữ liệu nghiệp vụ đúng.
- Timeline/recovery target được chọn chính xác.

### 14.2. WAL verification

Một số phiên bản/cách dùng có tùy chọn xác minh WAL liên quan. Đọc pg_verifybackup --help và tài liệu đúng phiên bản; không giả định mọi WAL archive bên ngoài được kiểm tra tự động chỉ bằng lệnh mặc định.

### 14.3. Checksum và manifest

Checksum giúp phát hiện file bị hỏng/thay đổi ngoài dự kiến. Nó không thay encryption, immutable storage hoặc kiểm tra semantics dữ liệu.

## 15. Base backup consistency và WAL cần thiết

Trong lúc base backup đang copy, một số page có thể đã được ghi trước thay đổi, một số page ghi sau. WAL chứa thông tin để server recovery đưa các file này về trạng thái nhất quán.

WAL cần thiết được xác định bởi quá trình backup và các mốc backup start/stop. Một bản backup không thể phục hồi nếu mất đoạn WAL bắt buộc để hoàn thành consistency recovery.

### 15.1. Base backup và archive chain

Một base backup hợp lệ thường cần WAL từ mốc bắt đầu recovery/backup tới điểm backup kết thúc, và sau đó tới target time nếu muốn PITR xa hơn.

### 15.2. Không tự xóa WAL cũ theo tuổi đơn giản

Giữ WAL phải dựa vào:
- Backup base nào còn được giữ.
- Recovery window cần hỗ trợ.
- Timeline nào cần thiết.
- Standby/replication consumers.
- Backup catalog/retention policy.

Một segment cũ hơn 7 ngày vẫn có thể là segment bắt buộc cho base backup được giữ 30 ngày.

### 15.3. Backup chain là một đơn vị

Khi xóa base backup, có thể giải phóng các WAL chỉ còn cần cho backup đó nếu không có backup/consumer khác cần. Việc tính toán cần dựa vào metadata, không đoán từ timestamp file.

## 16. Archive command retry và failure handling

Nếu archive command thất bại, PostgreSQL sẽ thử lại theo cơ chế archiver. Một lỗi kéo dài có thể làm WAL không được recycle như bình thường và khiến pg_wal đầy.

Các nguyên nhân:
- Archive filesystem hết dung lượng.
- Network/object storage outage.
- Credential hết hạn.
- Permission denied.
- Destination path không tồn tại.
- File đích đã tồn tại nhưng không giống source.
- Script timeout hoặc process crash.
- Archive server trả lỗi tạm thời.

### 16.1. Xem trạng thái archiver

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

### 16.2. failed_count tăng là tín hiệu cần điều tra

Xem log PostgreSQL và archive tool. Đừng chỉ reset statistics để làm dashboard xanh; phải xác định file nào chưa archive và vì sao.

### 16.3. last_archived_time cũ không luôn là lỗi

Nếu database gần như không tạo WAL, không có segment mới để archive. Kết hợp write rate, archive_timeout, current WAL segment và archive queue.

### 16.4. pg_wal tăng liên tục

Nếu archiver không theo kịp, source WAL có thể không được recycle. Kiểm tra filesystem free space, archive failures, replication slots và WAL retention settings.

## 17. Monitoring WAL archiving

Một query dashboard:

```sql
SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time,
    now() - last_archived_time AS time_since_last_archive
FROM pg_stat_archiver;
```

Theo dõi cùng:
- pg_wal disk usage.
- Archive destination growth.
- Archive upload latency/failures.
- WAL generation rate.
- Replication slot retention.
- Streaming replica lag.
- Backup job status.
- Alert nếu archive failures kéo dài hoặc backlog tăng.

### 17.1. Không suy ra backlog chỉ từ pg_stat_archiver

View này cung cấp counters và last success/failure, không phải một hàng đợi đầy đủ mọi segment pending. Cần metrics từ archive storage, server logs và WAL directory.

### 17.2. WAL generation rate

Trên primary có thể đo chênh LSN:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn;
```

Lưu giá trị theo thời gian rồi tính chênh lệch bằng pg_wal_lsn_diff. Đây là lượng WAL được tạo giữa hai lần đo, không phải dung lượng archive backlog chính xác.

### 17.3. Monitoring cần alert actionable

Alert nên nêu:
- Database/primary.
- Last successful archive.
- Failure count delta.
- Disk usage.
- Oldest pending segment hoặc ước lượng backlog.
- RPO window hiện tại.
- Owner/runbook xử lý.

## 18. archive_timeout và WAL switch

archive_timeout có thể buộc PostgreSQL switch WAL segment sau khoảng thời gian cấu hình nếu có hoạt động ghi phù hợp, giúp archive WAL mới thường xuyên hơn trong workload ít traffic.

Ví dụ:

```conf
archive_timeout = '5min'
```

### 18.1. Không phải commit timeout

archive_timeout không làm mỗi transaction chờ 5 phút và cũng không phải transaction durability timeout.

### 18.2. Segment archive có thể tốn dung lượng

Nếu switch thường xuyên trong workload ít ghi, archive có thể chứa nhiều segment chưa sử dụng hết payload thực tế nhưng file segment vẫn theo kích thước cố định.

### 18.3. Chọn dựa trên RPO và storage

Nếu cần archive freshness tối đa 5 phút, có thể cân nhắc archive_timeout phù hợp, nhưng phải đo WAL volume và archive costs.

### 18.4. pg_switch_wal

Có thể dùng pg_switch_wal() trong lab/điều tra để chuyển sang segment mới, giúp segment trước đó đủ điều kiện archive khi thích hợp:

```sql
SELECT pg_switch_wal();
```

Không gọi liên tục trong production chỉ để tạo nhiều file archive. Điều đó có thể tăng overhead/storage mà không cải thiện recovery thực tế.

## 19. WAL archive và streaming replication

```text
                 PRIMARY
                   |
          +--------+--------+
          |                 |
          v                 v
   Streaming WAL        Archive WAL
          |                 |
          v                 v
      Standby          Archive storage
          |                 |
          +--------+--------+
                   |
              Recovery/DR
```

### 19.1. Streaming replication

WAL được gửi gần liên tục tới standby qua replication connection. Độ trễ có thể thấp, nhưng standby vẫn phụ thuộc network, primary, replication configuration và retention.

### 19.2. WAL archive

Archive giữ các segment để recovery lâu dài theo retention. Nó có thể phục vụ restore độc lập hoặc standby fallback khi cần.

### 19.3. archive_timeout và replica lag khác nhau

Archive segment có thể chờ segment switch; streaming replication có thể nhận WAL sớm hơn. Không dùng thời gian archive cuối cùng làm số đo chính xác của standby replay lag.

### 19.4. Standby cần timeline và WAL continuity

Khi standby promote hoặc failover, timeline mới có thể xuất hiện. Backup/archive phải giữ timeline history files để recovery theo đúng nhánh lịch sử.

## 20. Timeline và timeline history files

PostgreSQL sử dụng timeline IDs để phân biệt các nhánh WAL history sau promotion/recovery.

```text
Timeline 1
    |
    +-- failover / promote
             |
             v
        Timeline 2
             |
             +-- further recovery
                      |
                      v
                  Timeline 3
```

Một timeline history file mô tả nhánh mới bắt đầu từ đâu so với timeline trước.

### 20.1. Vì sao cần giữ history files?

Khi recovery target yêu cầu timeline latest hoặc một timeline cụ thể, PostgreSQL cần biết quan hệ giữa các nhánh. Thiếu history file có thể làm chọn nhánh WAL sai hoặc không thể tiếp tục recovery.

### 20.2. Không chỉ giữ WAL segment

Retention cần giữ:
- WAL segments cần thiết.
- Timeline history files.
- Base backup metadata/manifest.
- Metadata xác định base backup và recovery range.

### 20.3. Không ghép WAL của hai timeline theo tên gần nhau

WAL filename có timeline ID. Không rename segment để làm cho một chuỗi trông liên tục. Dùng recovery timeline settings và history files đúng.

## 21. PITR là gì?

Point-in-Time Recovery (PITR) khôi phục một base backup rồi replay WAL tới một thời điểm, transaction ID, named restore point hoặc LSN được chọn, tùy recovery target hỗ trợ.

Ví dụ nghiệp vụ:
- 10:00 backup hoàn tất.
- 10:15 user xóa nhầm dữ liệu.
- 10:20 phát hiện lỗi.
- 10:30 DBA restore base backup và replay WAL tới 10:14:59.
- Database được khôi phục về trước thao tác xóa.

```text
Base backup
   |
   v
Replay WAL 10:00 -> 10:14:59
   |
   v
Pause / promote at target
   |
   v
Recovered database
```

### 21.1. PITR không phải rollback một transaction đang chạy

PITR thường tạo một cluster/data directory được phục hồi tới target. Nó không phải lệnh hoàn tác một transaction trong database production đang hoạt động.

### 21.2. Recovery target phải được chọn cẩn thận

Target quá muộn có thể chứa thao tác phá hoại. Target quá sớm có thể mất các giao dịch hợp lệ sau đó. Ghi lại timestamp/timezone, LSN và sự kiện cần phục hồi.

### 21.3. Dùng một restore instance cô lập trước

Trong nhiều tình huống, restore sang host/port/network riêng để xác minh dữ liệu trước khi đưa vào production hoặc trích xuất các rows cần thiết.

## 22. Cấu hình restore_command

Trong recovery, PostgreSQL cần lấy WAL segment từ archive. restore_command là command được gọi để lấy file WAL/history theo tên được yêu cầu.

Ví dụ trên Unix:

```conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
```

- %f: tên file cần lấy.
- %p: đường dẫn đích mà PostgreSQL yêu cầu.

Ví dụ này chỉ phù hợp kho local đơn giản; archive object storage cần client/tool riêng có retry, credential và checksum.

### 22.1. Exit status

Command phải trả exit 0 khi lấy được file thành công. Nếu file không tồn tại/không thể lấy, trả trạng thái thất bại phù hợp để recovery có thể tìm nguồn khác hoặc kết thúc theo semantics.

### 22.2. Không trả file sai timeline

Archive tool phải tìm đúng filename, không tự lấy segment mới nhất hay đổi timeline ID.

### 22.3. Kiểm tra integrity

Có thể kiểm tra checksum/size trong archive repository và ghi log source object. Không phục hồi từ file đã bị cắt cụt hoặc upload dở.

## 23. Recovery signal và các file điều khiển

Trong PostgreSQL 12 trở đi, recovery configuration sử dụng các signal files thay cho recovery.conf cũ.

Một restore PITR độc lập thường dùng recovery.signal trong data directory cùng các recovery settings phù hợp.

```text
restored-data-directory/
  PG_VERSION
  global/
  base/
  pg_wal/
  recovery.signal
  postgresql.auto.conf (có thể chứa settings được ghi bởi công cụ)
```

### 23.1. standby.signal khác recovery.signal

- standby.signal: yêu cầu server chạy như standby và tiếp tục recovery/streaming theo cấu hình.
- recovery.signal: yêu cầu recovery từ backup/WAL theo settings, thường dùng cho archive recovery/PITR.

Không đặt nhầm signal file rồi mong server tự hiểu mục tiêu.

### 23.2. PostgreSQL cũ hơn có recovery.conf

Các phiên bản trước PostgreSQL 12 dùng recovery.conf với cách cấu hình khác. Luôn đọc tài liệu đúng major version.

### 23.3. Signal file không tạo ra WAL

Phải có base backup và WAL archive cần thiết. Tạo recovery.signal mà thiếu segment sẽ không tạo được khả năng phục hồi.

## 24. Ví dụ recovery settings cho PITR

Ví dụ cấu hình minh họa:

```conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
recovery_target_time = '2026-11-14 10:14:59+07'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
```

Ý nghĩa:
- restore_command: lấy WAL/history từ archive.
- recovery_target_time: thời điểm dừng replay.
- recovery_target_timeline: chọn nhánh timeline.
- recovery_target_action: hành động khi tới target, ví dụ pause.

### 24.1. Timezone phải rõ

Timestamp PITR nên ghi timezone rõ ràng. Không nhập thời gian local rồi để hệ thống suy đoán timezone.

### 24.2. Inclusive/exclusive target

PostgreSQL có option liên quan target inclusive/exclusive cho một số recovery targets. Hiểu chính xác semantics của version trước khi chọn ranh giới transaction.

### 24.3. recovery_target_action

Các lựa chọn phổ biến gồm pause, promote hoặc shutdown, tùy version. Pause hữu ích để kiểm tra trạng thái trước khi tiếp tục/promote; promote tạo timeline mới; shutdown dừng server sau target theo semantics.

### 24.4. Pause để kiểm tra

Nếu recovery pause tại target, có thể kết nối read-only để kiểm tra dữ liệu theo quy trình. Trước khi cho ứng dụng ghi, cần quyết định promote/hoàn tất recovery phù hợp.

## 25. Các loại recovery target

Tùy version PostgreSQL, có thể dùng:

| Target | Ý nghĩa |
|---|---|
| recovery_target_time | Dừng tại thời điểm |
| recovery_target_xid | Dừng theo transaction ID |
| recovery_target_name | Dừng tại named restore point |
| recovery_target_lsn | Dừng theo LSN |
| recovery_target = immediate | Dừng ngay khi đạt trạng thái nhất quán đầu tiên theo semantics |

### 25.1. Named restore point

Trước sự kiện cần đánh dấu, có thể tạo:

```sql
SELECT pg_create_restore_point('before_release_2026_11_14');
```

Restore point ghi tên vào WAL; archive phải giữ WAL chứa restore point và các segment cần thiết.

### 25.2. Restore point không phải backup

Một restore point không sao chép data files. Nó chỉ đánh dấu một vị trí trong WAL history để phục hồi.

### 25.3. Transaction ID target

XID target có semantics nội bộ và cần xác định đúng transaction. Không nhầm XID với application order ID.

### 25.4. LSN target

LSN target hữu ích khi có một mốc WAL đã ghi nhận. LSN phải thuộc đúng cluster/timeline history.

## 26. Timeline selection sau failover

Khi recovery tới một timeline mới, có thể cần:

```conf
recovery_target_timeline = 'latest'
```

latest yêu cầu PostgreSQL chọn timeline mới nhất có thể xác định theo history. Trong DR, cần hiểu timeline nào là nhánh chính xác để tránh replay nhầm một nhánh sau failover.

### 26.1. Keep timeline history

Archive tất cả .history files cùng WAL segments. Không dọn chúng chỉ vì nhỏ hoặc cũ.

### 26.2. Không tự promote nhiều bản restore cùng một nhánh vào production

Một restored copy được promote có thể tạo timeline mới. Nếu có nhiều bản copy, phải quản lý timeline/cluster identity rõ để tránh split-brain và archive collision.

### 26.3. Sau promote, cập nhật backup plan

Một primary mới có thể tiếp tục archive WAL trên timeline mới. Kiểm tra archive_mode, archive_command, replication slots và standby reconfiguration.

## 27. Restore một base backup: quy trình tổng quát

Quy trình phục hồi vật lý/PITR thường gồm:

1. Chọn base backup hợp lệ có WAL coverage phù hợp.
2. Xác minh manifest/checksums và metadata.
3. Chuẩn bị host, PostgreSQL major version và storage.
4. Dừng server đích nếu đang chạy.
5. Khôi phục data directory từ backup.
6. Khôi phục tablespaces đúng vị trí/ownership.
7. Cấu hình restore_command và recovery target.
8. Tạo recovery.signal cho archive recovery.
9. Khởi động PostgreSQL trong mạng cô lập.
10. Theo dõi logs và WAL replay.
11. Kiểm tra dữ liệu tại target.
12. Pause/promote theo kế hoạch.
13. Chạy kiểm tra ứng dụng/constraints/sequence/replication.
14. Mở traffic khi xác nhận consistency và routing.

### 27.1. Không restore đè lên data directory đang chạy

Đảm bảo server đích đã dừng và target path đúng. Không ghi đè một cluster đang hoạt động.

### 27.2. Ownership và permissions

Files phải có owner/group và permissions phù hợp với PostgreSQL OS user. Tablespace symlinks phải trỏ tới đúng storage và có quyền.

### 27.3. Configuration không phải lúc nào cũng nằm trong PGDATA

Một số hệ thống đặt postgresql.conf, pg_hba.conf, certificates và tablespaces ở vị trí ngoài data directory. Backup/DR documentation phải liệt kê các dependencies này.

### 27.4. Không tự động mở ứng dụng sau khi server start

Recovery có thể chưa tới target, đang pause hoặc đang ở timeline sai. Chỉ mở traffic sau verification.

## 28. Tablespaces và external dependencies

Base backup có thể chứa metadata/mappings cho tablespaces. Khi restore trên host khác, các đường dẫn tablespace phải được chuẩn bị phù hợp.

Một backup plan cần ghi:
- Tablespace names/locations.
- Mapping giữa source và destination paths.
- Permissions/ownership.
- Mount points và storage class.
- Capacity.
- Encryption/key dependencies.
- Symlink handling và restore tooling.

### 28.1. pg_basebackup và tablespace mapping

pg_basebackup có tùy chọn mapping tablespace tới vị trí mới trong những trường hợp phù hợp. Kiểm tra --tablespace-mapping và format/version trước khi restore.

### 28.2. Không chỉ backup thư mục PGDATA

Nếu relation files nằm trong tablespaces bên ngoài, copy PGDATA mà bỏ tablespace sẽ thiếu dữ liệu.

### 28.3. External files

Large objects nằm trong PostgreSQL storage, nhưng ứng dụng có thể còn file uploads, object storage, secrets, certificates hoặc configuration ngoài DB. DR plan phải bao gồm các dependencies này nếu muốn ứng dụng hoạt động đầy đủ.

## 29. WAL retention và backup retention

Một policy retention phải bảo đảm mỗi base backup còn được giữ đều có đủ WAL để restore tới recovery window mong muốn.

```text
Base backup A ---------------------> WAL A1 A2 A3 A4 A5
        |                                      |
        +-- restore target cần tới A5 --------+
                                                 
Base backup B ---------------------> WAL B1 B2 B3
        |                                      |
        +-- restore target cần tới B3 --------+
```

### 29.1. Không xóa WAL chỉ theo ngày

Một segment cũ có thể là đoạn bắt buộc của base backup vẫn còn hợp lệ. Retention engine phải hiểu dependency giữa backup và WAL.

### 29.2. Backup expiry

Khi hết hạn một base backup, có thể xóa backup và những WAL không còn được bất kỳ backup/consumer nào yêu cầu. Tính toán theo metadata và timeline.

### 29.3. Recovery window

Nếu policy hứa PITR 14 ngày, cần bảo đảm:
- Base backup đủ cũ để phủ toàn cửa sổ.
- WAL liên tục cho tới hiện tại.
- Timeline history giữ đầy đủ.
- Archive storage có đủ dung lượng.
- Restore tooling và encryption keys còn hoạt động.

### 29.4. Full/incremental backup

Một số PostgreSQL versions hỗ trợ incremental base backups với công cụ và quy trình combine tương ứng. Incremental chain cần metadata và mọi phần backup phụ thuộc; không xóa base/parent backup khi child incremental còn cần.

## 30. WAL archive và disk pressure trong pg_wal

Nếu archiving thất bại, WAL segments có thể tích tụ trong pg_wal vì PostgreSQL chưa thể recycle chúng theo nhu cầu archive.

Nguy cơ:
- Filesystem đầy.
- PostgreSQL không thể tiếp tục ghi WAL.
- Transaction/application bị lỗi.
- Replication bị chậm.
- Backup window không đạt.
- Cluster có thể phải xử lý sự cố khẩn cấp.

### 30.1. Monitoring dung lượng

Theo dõi:
- Dung lượng filesystem chứa PGDATA/pg_wal.
- WAL generation rate.
- pg_stat_archiver.failed_count.
- Replication slot retention.
- max_wal_size/checkpoint activity.
- Archive destination capacity.

### 30.2. max_wal_size không phải giới hạn cứng cho mọi WAL

max_wal_size là mục tiêu mềm liên quan checkpoint/WAL volume, không phải quota cứng bảo đảm pg_wal không vượt mức đó. Archive failure hoặc replication slot có thể giữ WAL nhiều hơn.

### 30.3. Không xóa file thủ công trong pg_wal

Xóa WAL files trực tiếp có thể phá recovery/replication và làm cluster không khởi động được. Dùng PostgreSQL tools/settings và xử lý nguyên nhân archiving/slot.

### 30.4. Không xóa archive để chữa pg_wal đầy

Archive và pg_wal là hai vị trí khác nhau. Cần xác định archiver/slot/retention blocker; xóa archive có thể phá PITR mà không giải quyết nguyên nhân.

## 31. Backup consistency và filesystem snapshots

Một số nền tảng cung cấp storage snapshots. Có thể dùng trong backup strategy nếu tuân thủ quy trình PostgreSQL hỗ trợ.

### 31.1. Snapshot một ổ duy nhất chưa chắc đủ

Nếu data files và tablespaces ở nhiều volumes, snapshot phải nhất quán giữa các volumes. Cần cơ chế quiesce/freeze hoặc backup mode/snapshot coordination phù hợp.

### 31.2. WAL cần được giữ

Snapshot vật lý vẫn cần WAL thích hợp để phục hồi về trạng thái consistent. Đừng coi snapshot crash-inconsistent là bản backup hoàn chỉnh mà không có quy trình recovery được kiểm chứng.

### 31.3. Managed database snapshots

Dịch vụ managed có thể cung cấp automated backups/PITR. Đọc giới hạn retention, cross-region restore, encryption key và RTO thực tế của nhà cung cấp.

### 31.4. Không tự áp quy trình pg_basebackup lên dịch vụ bị hạn chế

Một số managed services không cấp OS/replication access. Dùng cơ chế backup/restore chính thức của dịch vụ.

## 32. RPO và RTO

Hai mục tiêu vận hành quan trọng:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa chấp nhận mất, thường tính bằng thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa để khôi phục dịch vụ.

Ví dụ:
- RPO = 5 phút.
- RTO = 60 phút.

Muốn đạt RPO 5 phút, WAL archive/replication phải đảm bảo dữ liệu cần thiết được lưu an toàn với độ trễ phù hợp; archive_timeout=5min một mình không chứng minh RPO đạt 5 phút.

Muốn đạt RTO 60 phút, phải đo toàn bộ:
- Provision host/storage.
- Transfer/restore base backup.
- WAL replay duration.
- Verification.
- DNS/routing/application startup.
- Data reconciliation và sign-off.

### 32.1. Backup duration không phải RTO

Một base backup chạy 2 giờ không cho biết restore mất bao lâu. Restore test mới đo RTO.

### 32.2. Archive lag không phải RPO hoàn chỉnh

RPO còn phụ thuộc commit durability, WAL archiving success, storage guarantees, failure detection và sự kiện cần phục hồi.

### 32.3. Đo P95 restore time

Thực hiện nhiều restore drills với kích thước/dữ liệu đại diện để xây estimate đáng tin cậy.

## 33. Restore drills: cách chứng minh backup dùng được

Một backup chưa từng restore chỉ là một giả định.

Một drill có thể:
1. Chọn base backup từ repository.
2. Chọn target time/LSN/restore point.
3. Provision môi trường cô lập.
4. Restore files và tablespaces.
5. Replay WAL.
6. Xác nhận recovery target.
7. Kiểm tra schema, row counts, constraints và application smoke tests.
8. Ghi thời gian từng phase.
9. Xác nhận keys/credentials/permissions.
10. Dọn môi trường drill theo policy.

### 33.1. Restore test phải dùng archive thật

Nếu test dùng một archive riêng được chuẩn bị hoàn hảo, nó chưa chứng minh archive production có đầy đủ segment/timeline/permissions.

### 33.2. Test cả failure cases

- Thiếu một WAL segment.
- Object bị hỏng checksum.
- Credential hết hạn.
- Tablespace không tồn tại.
- Recovery target nằm sau WAL cuối cùng.
- Timeline history thiếu.
- Disk không đủ.
- PostgreSQL major version sai.

Mục tiêu là phát hiện vấn đề khi còn thời gian sửa.

### 33.3. Không để drill truy cập production traffic

Restore instance phải được cô lập, tránh ứng dụng ghi nhầm hoặc dùng dữ liệu phục hồi cũ như production.

### 33.4. Ghi kết quả

Lưu backup ID, target, start/end time, WAL range, timeline, verification results, issues và người thực hiện.

## 34. Backup catalog và metadata

Một backup catalog tối thiểu nên ghi:

- Backup ID/label.
- PostgreSQL version/major.
- Source cluster/system identifier.
- Start/end timestamps.
- Start/stop LSN nếu có.
- Timeline.
- Backup format.
- Base backup path/object IDs.
- Manifest/checksum status.
- WAL range bắt buộc.
- Tablespace mappings.
- Encryption key reference.
- Retention expiry.
- Verification/restore drill status.

### 34.1. System identifier

System identifier giúp nhận diện cluster lineage. Có thể xem bằng công cụ pg_controldata trên data directory/backup phù hợp. Không ghép backup/WAL từ cluster khác chỉ vì tên database giống nhau.

### 34.2. Backup labels và manifest

Giữ các metadata file do tool tạo. Không rename/delete chúng nếu chưa hiểu ảnh hưởng tới restore/verification.

### 34.3. Backup ID phải bất biến

Không dùng tên folder cố định ghi đè base backup cũ. Dùng ID/time unique và catalog để theo dõi trạng thái.

## 35. Full, incremental và WAL-only retention

Một chiến lược có thể có:
- Base backup định kỳ.
- Incremental backups nếu version/tool hỗ trợ.
- Continuous WAL archive.
- Logical dumps theo chu kỳ riêng.

### 35.1. Full base backup

Dễ hiểu và thường là nền tảng đơn giản nhất, nhưng tốn storage/network/time.

### 35.2. Incremental backup

Có thể giảm dữ liệu copy, nhưng restore phải kết hợp đúng chain và công cụ. Giữ mọi ancestor/base cần thiết.

### 35.3. WAL-only không phải backup đầy đủ

Chỉ lưu WAL mà không có base backup hợp lệ thì không có điểm xuất phát để dựng cluster từ đầu.

### 35.4. Full backup không có WAL archive

Có thể restore về consistency point của backup nếu WAL cần cho backup được đóng gói theo quy trình, nhưng không có continuous PITR tới các thời điểm sau đó.

## 36. Archive cleanup và pg_archivecleanup

pg_archivecleanup là công cụ hỗ trợ xóa các WAL archive cũ hơn một segment được xác định, trong một số workflow standby/archive cleanup.

Ví dụ dạng sử dụng:

```bash
pg_archivecleanup /srv/pgarchive 0000000200000000000000A5
```

Đây là ví dụ minh họa; không chạy trên kho archive có nhiều base backups/PITR consumers nếu chưa tính dependency.

### 36.1. Cleanup cần biết oldest required WAL

Nếu base backup cũ nhất còn được giữ cần WAL từ segment A1, không được xóa A1 chỉ vì standby hiện đã replay tới A5.

### 36.2. Nhiều consumers cần retention hợp nhất

Một archive có thể phục vụ nhiều standby, base backups và PITR windows. Cleanup phải giữ segment cần cho consumer có yêu cầu dài nhất.

### 36.3. Object storage lifecycle policy có thể nguy hiểm

Một policy tự xóa object sau 7 ngày có thể phá backup 30 ngày. Retention của object store phải đồng bộ backup catalog.

## 37. Backup khi có standby

Có thể tạo base backup từ standby trong những cấu hình/version được hỗ trợ, giảm tải đọc trên primary. Nhưng cần hiểu:
- WAL receiver/replay state.
- WAL sender capacity trên standby.
- Backup consistency và WAL availability.
- Tablespace paths.
- Replication lag.
- Failover/timeline history.
- Các giới hạn của backup tool khi source là standby.

### 37.1. Standby backup không tự thay WAL archive từ primary

Cần bảo đảm WAL archive và timeline history đủ cho mục tiêu restore. Một standby backup có thể cần WAL từ primary/archive tùy điểm và quy trình.

### 37.2. Backup từ standby không loại bỏ I/O

Standby vẫn phải đọc data files và có thể ảnh hưởng query/reporting trên replica.

### 37.3. Đo tải riêng

Theo dõi replica query latency, replay lag và backup throughput.

## 38. WAL archive encryption và key lifecycle

Nếu client-side encrypt WAL archive:
- Dùng encryption authenticated phù hợp.
- Mỗi object/file cần metadata nhận biết key version/nonce/algorithm.
- Key phải được lưu ngoài archive repository.
- Có quy trình rotation không làm mất khả năng decrypt file cũ.
- Restore host có quyền lấy key đúng phạm vi.
- Kiểm thử decrypt trong restore drill.
- Bảo vệ logs để không lộ plaintext/credentials.

### 38.1. Mất key đồng nghĩa mất backup

Một object còn nguyên checksum nhưng không decrypt được vẫn không phục hồi được dữ liệu. Key recovery là một phần của DR.

### 38.2. Encryption at rest của cloud không giải quyết mọi threat

Nếu kẻ tấn công chiếm credentials có quyền đọc objects, họ có thể truy cập plaintext qua service. Cân nhắc client-side encryption và separation of duties.

### 38.3. Không thay đổi format archive âm thầm

Thay encryption/compression wrapper phải giữ khả năng đọc mọi backup còn trong retention window.

## 39. Compression và bandwidth

WAL archive có thể được nén bởi:
- Công cụ archive bên ngoài.
- Object storage compression nếu hỗ trợ.
- Cơ chế WAL compression cho một số nội dung WAL, tùy setting/version.

Cần phân biệt wal_compression với việc nén toàn bộ file WAL archive: wal_compression chủ yếu liên quan full-page images trong WAL record, không phải một lệnh nén toàn bộ segment file thành gzip.

### 39.1. Compression trade-off

- Giảm storage/network.
- Tăng CPU.
- Thêm bước decompress khi restore.
- Cần version/format compatibility.
- Cần kiểm tra integrity sau decompress.

### 39.2. Đo compression ratio

Lưu kích thước raw và compressed theo segment/time để biết workload thực sự tiết kiệm bao nhiêu. WAL có thể chứa nhiều loại record với tỷ lệ nén khác nhau.

### 39.3. Restore throughput

Một archive nén tốt nhưng decompress chậm có thể làm RTO xấu. Đo end-to-end, không chỉ storage cost.

## 40. Các failure scenarios và phản ứng

| Sự cố | Dấu hiệu | Hành động |
|---|---|---|
| Archive command lỗi | failed_count/log errors tăng | Sửa permission/network/storage, xác minh pending WAL |
| Archive storage full | Upload/copy fail, capacity alert | Tăng capacity/cleanup theo dependency, không xóa bừa |
| WAL segment thiếu | Restore dừng tại segment | Tìm bản sao/replica/archive khác, xác định RPO thực |
| Base backup hỏng | Manifest/checksum mismatch | Dùng backup khác, điều tra storage pipeline |
| Mất encryption key | Không decrypt được archive | Khôi phục key qua escrow/KMS DR |
| Long backup | I/O và latency tăng | Điều chỉnh window/throughput/checkpoint |
| pg_wal tăng bất thường | Filesystem usage tăng | Kiểm tra archiver và replication slots |
| Timeline mismatch | Recovery không tìm đúng WAL | Kiểm tra history files và recovery_target_timeline |
| Restore sai target | Dữ liệu sau sự kiện phá hoại vẫn còn | Chọn target sớm hơn, chạy lại isolated restore |
| Restore host thiếu disk | Copy/replay fail | Capacity plan, không start production traffic |
| Standby lag | Replay LSN chậm | Kiểm tra network, WAL sender, I/O và replay workload |
| Retention xóa WAL cần thiết | PITR window bị đứt | Dừng cleanup, tìm replica/offsite copies, sửa policy |

### 40.1. Xử lý archive failure trước khi pg_wal đầy

Alert phải đủ sớm để DBA có thời gian xử lý trước khi filesystem cạn. Theo dõi cả tốc độ WAL generation và dung lượng còn lại.

### 40.2. Không xóa WAL bằng tay

Không dùng rm/file manager để xóa files trong pg_wal. Với archive, chỉ cleanup bằng retention engine hiểu backup dependencies.

### 40.3. Khi thiếu WAL, đừng giả vờ PITR vẫn hoàn chỉnh

Có thể phục hồi tới điểm trước segment thiếu nếu base backup và chuỗi WAL trước đó hợp lệ. Ghi rõ RPO thực tế và dữ liệu có thể mất.

## 41. Runbook: tạo base backup và kiểm tra

**Bước 1 — Xác nhận source**

- Cluster/version/system identifier.
- Primary/standby source.
- Tablespaces và data directory.
- WAL/archive health.

**Bước 2 — Xác nhận destination**

- Dung lượng trống.
- Quyền truy cập.
- Encryption/credentials.
- Failure domain độc lập.
- Backup ID unique.

**Bước 3 — Chạy pg_basebackup**

Chọn format và WAL method phù hợp; ghi progress, start/end và exit status.

**Bước 4 — Kiểm tra backup**

- Manifest/checksum.
- File inventory.
- Tablespace mapping.
- WAL coverage.
- Catalog metadata.

**Bước 5 — Ghi catalog**

Lưu ID, version, timeline, LSN range, retention expiry và verification result.

**Bước 6 — Restore drill**

Thực hiện định kỳ trên môi trường cô lập để đo RTO và kiểm tra WAL chain.

## 42. Runbook: xử lý archive failure

1. Đọc pg_stat_archiver và PostgreSQL logs.
2. Xác định last_failed_wal, thời gian lỗi và failure count delta.
3. Kiểm tra archive destination capacity.
4. Kiểm tra permission, credentials, network và object store status.
5. Xác định archive command có trả exit code đúng không.
6. Kiểm tra file đích đã tồn tại và checksum có khớp không.
7. Sửa nguyên nhân.
8. Để PostgreSQL retry hoặc sử dụng quy trình được hỗ trợ để khôi phục archive state.
9. Xác minh archived_count tiến triển và last_archived_wal cập nhật.
10. Kiểm tra pg_wal usage đã ổn định.
11. Ghi lại khoảng thời gian archive bị gián đoạn và RPO risk.

Không reset statistics hoặc xóa WAL để che dấu sự cố.

## 43. Runbook: PITR sau khi xóa nhầm dữ liệu

1. Dừng hoặc cô lập ứng dụng gây ra thao tác phá hoại để tránh thêm writes.
2. Ghi lại thời điểm sự kiện và timezone.
3. Xác định target trước transaction phá hoại.
4. Chọn base backup gần nhất có WAL coverage liên tục tới target.
5. Xác minh manifest, timeline và encryption keys.
6. Restore sang host/data directory cô lập.
7. Cấu hình restore_command, recovery.signal và target settings.
8. Start server, theo dõi WAL replay và logs.
9. Pause tại target nếu cần kiểm tra.
10. Kiểm tra dữ liệu, constraints, sequences, roles và application queries.
11. Chọn phục hồi toàn cluster hay trích xuất dữ liệu cần thiết.
12. Promote/hoàn tất recovery theo kế hoạch.
13. Reconfigure replication và archive cho timeline mới.
14. Chỉ chuyển traffic sau khi xác nhận và phê duyệt vận hành.

### 43.1. Vì sao thường restore sang môi trường riêng?

Có thể cần chỉ lấy lại một số rows hoặc kiểm tra dữ liệu mà không thay thế toàn bộ production. Restore cô lập giảm rủi ro ghi đè dữ liệu hợp lệ sau target.

### 43.2. Nếu ứng dụng đã ghi dữ liệu sau sự cố?

Cần quyết định reconciliation: giữ writes hợp lệ, trích xuất records từ restored copy, hoặc cutover theo một mốc rõ ràng. PITR không tự merge hai lịch sử.

## 44. Checklist backup/DR

| Hạng mục | Cần xác nhận |
|---|---|
| Base backup | Được tạo bằng pg_basebackup hoặc phương pháp snapshot được hỗ trợ |
| WAL archiving | archive_mode và archive command/library hoạt động |
| WAL continuity | Không thiếu segment/history trong recovery window |
| Backup manifest | Có và đã verify khi tool hỗ trợ |
| System identity | Backup đúng cluster/version |
| Tablespaces | Paths/mappings được ghi lại |
| Credentials | Có thể truy cập backup/archive trong DR |
| Encryption keys | Có key escrow/recovery và test decrypt |
| Offsite | Failure domain độc lập |
| Immutable | Có protection trước xóa nhầm/ransomware |
| Retention | Giữ đủ base backups và WAL dependencies |
| Archive monitoring | Theo dõi failed_count/last archived/queue |
| pg_wal capacity | Alert trước khi filesystem đầy |
| Replication slots | Theo dõi inactive slots và retained WAL |
| Timeline history | Lưu .history files |
| Restore command | Được test với archive thật |
| Recovery target | Timestamp/LSN/timezone được xác định |
| Restore drills | Có kết quả và RTO thực đo |
| RPO | Archive freshness và commit durability phù hợp |
| RTO | Host, transfer, replay và verification được đo |
| Application | Có smoke tests sau restore |
| Roles/config | Có backup globals và external config cần thiết |
| Runbook | Có owner, escalation và bước xác minh |

## 45. Bài tập thực hành có đáp án

### Bài 1. Base backup là gì?

**Đáp án:** Một bản sao vật lý nhất quán của cluster/phạm vi được hỗ trợ, có thể kết hợp WAL để hoàn tất recovery.

### Bài 2. Vì sao không copy PGDATA đang chạy bằng lệnh copy file thông thường?

**Đáp án:** Các files có thể được copy ở thời điểm không đồng nhất; thiếu backup protocol/WAL consistency có thể làm bản sao không recoverable.

### Bài 3. Physical backup và logical backup khác nhau thế nào?

**Đáp án:** Physical backup sao chép storage-level cluster files; logical backup xuất objects/data thành representation có thể restore/import.

### Bài 4. pg_dump có tạo continuous PITR không?

**Đáp án:** Không. pg_dump tạo logical dump, không thay base backup + continuous WAL archive.

### Bài 5. WAL là gì?

**Đáp án:** Write-Ahead Log ghi lại thay đổi theo thứ tự để phục hồi/replication.

### Bài 6. LSN là timestamp?

**Đáp án:** Không. LSN là vị trí trong WAL stream.

### Bài 7. WAL segment phổ biến thường có kích thước bao nhiêu?

**Đáp án:** Nhiều build phổ biến dùng 16 MiB, nhưng phải xác minh kích thước build/server.

### Bài 8. WAL archiving và streaming replication giống nhau?

**Đáp án:** Không. Một cơ chế lưu segments vào archive, cơ chế kia gửi WAL tới standby đang hoạt động.

### Bài 9. archive_mode=on có thường cần restart không?

**Đáp án:** Có, thay đổi archive_mode thường cần restart server.

### Bài 10. %p và %f trong archive_command là gì?

**Đáp án:** %p là source path đầy đủ; %f là tên file WAL.

### Bài 11. Archive command trả exit 0 nghĩa gì?

**Đáp án:** PostgreSQL coi segment đã archive thành công; chỉ trả 0 khi file đã được lưu bền vững theo yêu cầu.

### Bài 12. Vì sao archive command phải idempotent?

**Đáp án:** PostgreSQL có thể retry cùng file sau lỗi/restart; không được tạo file sai hoặc ghi đè âm thầm.

### Bài 13. Archive storage cùng ổ với PGDATA có đủ chống thảm họa?

**Đáp án:** Không. Một sự cố ổ/host có thể làm mất cả hai.

### Bài 14. pg_basebackup -X stream làm gì?

**Đáp án:** Stream WAL cần thiết trong lúc base backup, giúp bản backup có WAL kèm theo theo method đó.

### Bài 15. -X none có tự bảo đảm PITR không?

**Đáp án:** Không. Quy trình khác phải bảo đảm WAL cần thiết và continuity.

### Bài 16. pg_basebackup -R có nghĩa PITR tới timestamp?

**Đáp án:** Không. Nó tạo cấu hình để dùng backup như standby theo semantics của tool/version.

### Bài 17. Backup user cần quyền gì?

**Đáp án:** Thường cần LOGIN và REPLICATION cùng pg_hba rule phù hợp; chi tiết theo version/config.

### Bài 18. Có nên để password trên command line?

**Đáp án:** Không. Dùng credential store/password file được bảo vệ hoặc secret provider.

### Bài 19. Replication slot có tự archive WAL không?

**Đáp án:** Không. Slot giữ WAL cho consumer; archive process mới sao chép WAL vào archive repository.

### Bài 20. Slot inactive có thể giữ WAL?

**Đáp án:** Có. Slot có thể giữ restart_lsn/xmin và làm tài nguyên tăng.

### Bài 21. pg_verifybackup chứng minh restore hoàn chỉnh?

**Đáp án:** Không. Nó kiểm tra backup theo manifest/checksums; cần restore drill để chứng minh WAL chain, keys, tablespaces và application hoạt động.

### Bài 22. pg_stat_archiver có cho biết toàn bộ archive queue?

**Đáp án:** Không. Nó cung cấp counters và last success/failure; cần thêm storage/log/WAL monitoring.

### Bài 23. Archive failure kéo dài có thể làm gì với pg_wal?

**Đáp án:** WAL không được recycle đúng lúc và pg_wal có thể tăng đến khi filesystem đầy.

### Bài 24. max_wal_size là quota cứng?

**Đáp án:** Không. Đây là mục tiêu mềm liên quan checkpoint; slot/archive failure có thể làm WAL vượt mức.

### Bài 25. archive_timeout là transaction timeout?

**Đáp án:** Không. Nó có thể buộc WAL segment switch để archive WAL mới thường xuyên hơn.

### Bài 26. pg_switch_wal() có nên chạy liên tục?

**Đáp án:** Không. Switch quá thường xuyên tăng số segment/archive và overhead.

### Bài 27. PITR là gì?

**Đáp án:** Restore base backup rồi replay WAL tới một recovery target cụ thể.

### Bài 28. PITR là rollback một transaction production?

**Đáp án:** Không. Thường tạo cluster restored tới target; có thể trích xuất dữ liệu hoặc cutover theo quy trình.

### Bài 29. restore_command dùng %f và %p ra sao?

**Đáp án:** %f là tên file cần lấy; %p là destination path PostgreSQL yêu cầu.

### Bài 30. PostgreSQL 12+ dùng file nào cho archive recovery?

**Đáp án:** recovery.signal; standby dùng standby.signal. Các phiên bản trước có recovery.conf.

### Bài 31. recovery_target_time nên ghi timezone không?

**Đáp án:** Có. Ghi timezone rõ để tránh chọn sai thời điểm.

### Bài 32. recovery_target_timeline='latest' giúp gì?

**Đáp án:** Yêu cầu chọn timeline mới nhất có thể xác định theo history; vẫn phải kiểm tra đúng nhánh DR.

### Bài 33. Restore point có phải base backup?

**Đáp án:** Không. Nó đánh dấu một vị trí trong WAL.

### Bài 34. Vì sao phải giữ .history files?

**Đáp án:** Chúng mô tả quan hệ giữa timelines để recovery chọn đúng nhánh WAL.

### Bài 35. WAL archive có thể xóa sau 7 ngày nếu base backup giữ 30 ngày?

**Đáp án:** Không nếu base backup còn cần WAL cũ hơn 7 ngày để phục hồi; retention phải xét dependency.

### Bài 36. VACUUM FULL có liên quan tới backup?

**Đáp án:** Không phải backup; nó rewrite table và có thể tạo I/O/WAL, cần tính tác động tới backup/replication.

### Bài 37. RPO khác RTO thế nào?

**Đáp án:** RPO là lượng dữ liệu tối đa chấp nhận mất; RTO là thời gian tối đa để khôi phục dịch vụ.

### Bài 38. archive_timeout=5min có tự chứng minh RPO 5 phút?

**Đáp án:** Không. Còn phụ thuộc archive success, storage durability, commit behavior và failure mode.

### Bài 39. Backup thành công nhưng chưa từng restore có đủ tin cậy?

**Đáp án:** Không. Cần restore drills định kỳ với archive thực tế.

### Bài 40. Một restore drill cần đo gì?

**Đáp án:** Backup ID, target, WAL range/timeline, transfer/restore/replay/verification duration, errors, RTO và data/application checks.

### Bài 41. Nếu archive file đã tồn tại nhưng checksum khác nguồn?

**Đáp án:** Không ghi đè âm thầm hoặc trả success; báo lỗi và điều tra collision/corruption.

### Bài 42. Có nên xóa WAL files thủ công trong pg_wal khi disk gần đầy?

**Đáp án:** Không. Điều đó có thể phá recovery/replication và làm cluster hỏng.

### Bài 43. Một base backup có tablespaces ngoài PGDATA cần làm gì?

**Đáp án:** Ghi nhận/mapping và restore mọi tablespace đúng đường dẫn, owner và permissions.

### Bài 44. Encryption key bị mất nhưng backup checksum đúng thì sao?

**Đáp án:** Backup vẫn không thể decrypt; key recovery là phần bắt buộc của DR.

### Bài 45. Một standby replay WAL nhanh có nghĩa archive cũng đã lưu WAL?

**Đáp án:** Không. Streaming replication và archive là hai đường riêng; theo dõi từng cơ chế.

### Bài 46. wal_compression có nén toàn bộ WAL archive thành file gzip?

**Đáp án:** Không. Nó chủ yếu liên quan full-page images trong WAL records; nén archive file là cơ chế khác.

### Bài 47. Có thể restore PG major version cũ bằng data directory của major version mới?

**Đáp án:** Không theo cách khởi động trực tiếp thông thường; physical backups cần tương thích major version, major upgrade dùng quy trình riêng.

### Bài 48. Khi PITR restore xong, có nên mở traffic ngay?

**Đáp án:** Không. Kiểm tra target/timeline, dữ liệu, sequences, roles, application behavior và replication trước.

## 46. Checklist thiết kế chính sách backup + WAL

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Base backup tạo bằng công cụ nào? | pg_basebackup/managed snapshot procedure |
| Backup có đúng cluster/version? | Version và system identifier |
| WAL method là gì? | stream/fetch/none và lý do |
| Archive command/library có retry-safe? | Test exit status/idempotency |
| Archive storage độc lập failure domain? | Architecture/network/storage |
| Có offsite/immutable copy? | Retention/immutability policy |
| Encryption keys có DR? | Escrow/KMS recovery test |
| WAL segments liên tục? | Archive inventory/monitoring |
| Timeline history được giữ? | .history objects |
| Backup manifest được verify? | pg_verifybackup output |
| Tablespaces được map? | Backup catalog/runbook |
| Retention giữ WAL cần thiết? | Dependency graph/catalog |
| pg_wal disk được monitor? | Filesystem alerts |
| Archive failures được alert? | pg_stat_archiver/logs |
| Replication slots được theo dõi? | Slot inventory/retention |
| RPO đã đo? | Archive lag/durability evidence |
| RTO đã đo? | Restore drill duration |
| Restore target có timezone? | Runbook |
| Restore drill có isolated network? | DR test environment |
| Application checks sau restore? | Smoke tests/data validation |
| Backup catalog có đủ metadata? | Backup ID/LSN/timeline/keys |
| Restore được thử với archive thật? | Drill report |

## 47. Tài liệu PostgreSQL chính thức

- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backup, WAL archiving, PITR và restore.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — tạo physical base backup.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html) — kiểm tra base backup manifest/checksums.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — wal_level, archive_mode, archive_timeout và WAL settings.
- [Archive Recovery Settings](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET) — recovery targets và restore settings.
- [pg_stat_archiver](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ARCHIVER-VIEW) — archive statistics.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — slot state và retained WAL.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — logical backup.
- [pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html) — globals và nhiều databases.
- [WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html) — WAL records, segments và LSN.
- [pg_create_restore_point](https://www.postgresql.org/docs/current/functions-admin.html) — tạo named restore point.

Cú pháp, recovery parameters, archive_library, incremental backup và một số view fields thay đổi theo PostgreSQL version. Trước khi áp dụng, xác minh server_version, pg_settings, pg_basebackup --help và tài liệu đúng major version đang vận hành.

## 48. Tổng kết

```text
1. Tạo base backup vật lý nhất quán
              |
              v
2. Archive WAL segments liên tục
              |
              v
3. Giữ đủ WAL + timeline history theo retention
              |
              v
4. Verify manifest/checksums và archive continuity
              |
              v
5. Restore base backup trên môi trường đích
              |
              v
6. Dùng restore_command lấy WAL
              |
              v
7. Replay tới recovery target / PITR
              |
              v
8. Verify dữ liệu, application và RPO/RTO
```

Những nguyên tắc cần nhớ:

1. **Base backup là điểm xuất phát; WAL archive là chuỗi thay đổi.** PITR cần cả hai và WAL phải liên tục.
2. **Không copy PGDATA đang chạy tùy tiện.** Dùng pg_basebackup hoặc snapshot procedure được hỗ trợ.
3. **WAL archiving khác streaming replication.** Theo dõi và thiết kế retention cho cả hai đường.
4. **Archive command chỉ trả thành công sau khi file đã được lưu bền vững.** Phải retry-safe, idempotent và phát hiện collision.
5. **Không xóa WAL theo tuổi đơn giản.** Giữ mọi segment/timeline history cần cho base backups còn hiệu lực.
6. **pg_basebackup WAL method phải được chọn có chủ đích.** stream, fetch và none có các yêu cầu khác nhau.
7. **Monitor archive failures và pg_wal capacity.** Một archive outage kéo dài có thể làm filesystem đầy.
8. **Timeline history là một phần của recovery chain.** Không rename hoặc ghép WAL giữa các nhánh.
9. **PITR cần target/timezone rõ ràng.** Restore vào môi trường cô lập và kiểm tra trước cutover.
10. **Encryption key, tablespaces, roles và configuration cũng thuộc DR.** Backup files một mình chưa đủ.
11. **RPO/RTO phải được đo bằng restore drills.** pg_verifybackup là một bước kiểm tra, không thay restore test.
12. **Retention phải hiểu dependency.** Xóa base backup/WAL chỉ khi không còn recovery consumer nào cần chúng.

**Một câu để nhớ:** *Base backup tạo nền phục hồi; WAL archive nối nền đó với các thời điểm sau. Chỉ khi chuỗi backup, WAL, timeline, keys và quy trình restore được kiểm chứng cùng nhau, PostgreSQL mới có một chiến lược PITR đáng tin cậy.*

