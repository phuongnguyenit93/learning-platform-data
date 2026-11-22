# Primary, standby và luồng streaming replication trong PostgreSQL

**Streaming replication** là cơ chế PostgreSQL truyền các WAL records từ một server đang giữ vai trò **primary** tới một hoặc nhiều server **standby**. Standby nhận WAL, ghi WAL vào storage của nó rồi replay các records để cập nhật data pages. Nhờ vậy, standby duy trì một bản sao vật lý của cluster và có thể được dùng để phục vụ truy vấn đọc (hot standby) hoặc được promote thành primary khi cần failover.

Mô hình này là nền tảng của high availability (HA), disaster recovery và read scaling. Tuy nhiên, streaming replication không tự tạo ra một hệ thống HA hoàn chỉnh: cần base backup ban đầu, WAL retention, giám sát lag, quy trình promotion/fencing, cấu hình synchronous/asynchronous phù hợp và kiểm thử failover.

Luồng tổng quát:

```text
                 Ứng dụng ghi/COMMIT
                         |
                         v
                   +-----------+
                   |  PRIMARY  |
                   | WAL sender|
                   +-----------+
                         |
                  Streaming protocol
                         |
              +----------+----------+
              |                     |
              v                     v
        +-----------+         +-----------+
        | STANDBY A |         | STANDBY B |
        | WAL recv  |         | WAL recv  |
        | WAL replay|         | WAL replay|
        +-----------+         +-----------+
              |                     |
           Read-only             Read-only
              |                     |
         Promote khi failover theo quy trình
```

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt primary, standby, WAL sender và WAL receiver.
2. Giải thích physical streaming replication truyền WAL thay vì gửi từng câu SQL/row changes.
3. Mô tả vì sao standby cần base backup trước khi bắt đầu streaming.
4. Cấu hình primary cho physical replication bằng `wal_level`, `max_wal_senders`, replication role và `pg_hba.conf`.
5. Tạo standby bằng `pg_basebackup`, `-R`, physical replication slot và `primary_conninfo`.
6. Giải thích `standby.signal`, `primary_slot_name`, `restore_command` và `hot_standby`.
7. Phân biệt asynchronous và synchronous replication.
8. Chọn `synchronous_commit` phù hợp với durability/latency requirements.
9. Theo dõi sent, write, flush và replay LSN cũng như replication lag.
10. Quản lý WAL retention, physical replication slots và nguy cơ đầy disk.
11. Hiểu hot standby queries, recovery conflicts và `hot_standby_feedback`.
12. Thiết kế cascading replication và nhận biết giới hạn của chuỗi standby.
13. Thực hiện promotion/failover an toàn, hiểu timeline mới và tránh split-brain.
14. Rejoin primary cũ bằng `pg_rewind` hoặc base backup mới.
15. Bảo vệ replication bằng network ACL, TLS, role tối thiểu và secrets.
16. Xây dựng monitoring, runbook, recovery drills và RPO/RTO cho hệ thống.

## 2. Primary và standby là gì?

### 2.1. Primary

Primary là instance PostgreSQL hiện giữ vai trò cho phép read-write workload. Nó:

- Nhận connections từ ứng dụng.
- Thực hiện INSERT/UPDATE/DELETE/DDL và transaction commits.
- Tạo WAL records mô tả các thay đổi.
- Chạy WAL sender processes để gửi WAL tới standbys.
- Quản lý replication slots nếu được cấu hình.

Một cluster primary có thể có nhiều standby. Trong physical streaming replication truyền thống, chỉ một primary active được phép nhận writes cho cùng một replication topology tại một thời điểm.

### 2.2. Standby

Standby là instance được khởi tạo từ physical base backup của primary hoặc một backup vật lý tương thích. Nó:

- Kết nối tới primary hoặc upstream standby.
- Nhận WAL qua WAL receiver process.
- Ghi WAL vào local `pg_wal`.
- Replay WAL để cập nhật data files.
- Có thể phục vụ read-only queries nếu `hot_standby=on` và recovery state cho phép.
- Có thể được promote để trở thành primary.

Standby không nhận các câu SQL rồi chạy lại như một subscriber của logical replication. Nó áp dụng WAL records vật lý lên storage.

### 2.3. Physical replication sao chép ở cấp cluster

Physical streaming replication sao chép WAL cho **toàn bộ PostgreSQL cluster**, không cấu hình theo từng database hoặc từng table. Các databases, schemas, tables, indexes và Large Objects nằm trong cluster được cập nhật thông qua WAL.

Nếu chỉ muốn replicate một tập tables hoặc biến đổi schema/dữ liệu giữa hai hệ thống, xem logical replication. Không dùng physical standby để chỉ chọn một database.

### 2.4. Cùng PostgreSQL major version

Physical standby phải tương thích về PostgreSQL major version và định dạng data files với primary/base backup. Thông thường primary và standby chạy cùng major version; minor releases trong cùng major được thiết kế tương thích cho streaming replication, nhưng nên duy trì patch level được hỗ trợ và test nâng cấp.

Không thể dùng một physical standby để replicate trực tiếp từ PostgreSQL 16 sang PostgreSQL 17 như một bản sao physical bình thường. Major upgrade cần quy trình riêng (ví dụ `pg_upgrade` hoặc logical migration).

### 2.5. Primary và standby không có hai bộ dữ liệu độc lập

Standby là bản sao vật lý được cập nhật bằng WAL. Nó không phải nơi ứng dụng tùy ý ghi thêm dữ liệu. Khi đang ở recovery, các data modifications từ client bị từ chối; hot standby chỉ cho phép read-only queries.

### 2.6. Một primary, nhiều standby

Topology cơ bản:

```text
                 +------------------+
                 |      PRIMARY     |
                 +------------------+
                    /      |      \
                   /       |       \
                  v        v        v
             Standby A  Standby B  Standby C
```

Mỗi standby có thể có mục đích riêng: HA gần primary, disaster recovery ở vùng khác, hoặc read-only reporting. Cần xác định mỗi node có được synchronous acknowledgement hay không và WAL retention của từng node.

## 3. Streaming replication hoạt động như thế nào?

### 3.1. WAL là luồng dữ liệu replication

Khi primary thay đổi một page, PostgreSQL tạo WAL records. WAL sender đọc WAL từ vị trí cần gửi và truyền qua replication protocol. Standby nhận stream và ghi vào WAL files cục bộ.

Luồng:

```text
Primary transaction
       |
       v
  WAL records được tạo
       |
       v
  WAL sender đọc WAL
       |
       v
  TCP/TLS replication connection
       |
       v
  WAL receiver trên standby
       |
       v
  Ghi WAL local / flush theo tiến độ
       |
       v
  Startup/recovery process replay WAL
       |
       v
  Standby data pages tiến gần primary
```

### 3.2. WAL sender

Primary tạo một WAL sender process cho mỗi replication connection đang hoạt động. WAL sender phục vụ:

- Physical standby streaming.
- Logical replication walsender/replication protocol connections.
- `pg_basebackup` khi lấy base backup qua replication protocol.

Vì vậy, `max_wal_senders` phải đủ cho standbys, backup sessions và các replication consumers cần thiết, cộng thêm headroom cho failover/reconnect.

### 3.3. WAL receiver

Standby chạy WAL receiver để kết nối upstream. Receiver nhận WAL, ghi vào local WAL storage và báo tiến độ về primary. Trên standby có thể quan sát process qua `pg_stat_wal_receiver`.

### 3.4. Replay

WAL receiver và WAL replay là hai bước khác nhau:

- **Receive:** bytes WAL đã được nhận từ upstream.
- **Write/flush:** WAL đã được ghi hoặc flush vào local storage.
- **Replay:** recovery process đã áp dụng WAL records vào standby data files.

Standby có thể đã nhận WAL nhưng chưa replay hết. Khi đó một query read-only có thể thấy dữ liệu cũ hơn so với primary.

### 3.5. Replication feedback

Standby gửi feedback tới primary, bao gồm vị trí WAL đã write/flush/replay và thông tin transaction horizon liên quan. Primary dùng feedback để biết standby đang tiến tới đâu và, trong synchronous replication, xác định khi nào có thể xác nhận commit.

### 3.6. Streaming protocol

Physical replication dùng replication protocol qua kết nối PostgreSQL. Client thường kết nối với replication parameter phù hợp; `pg_hba.conf` có dòng `replication` để xác thực.

Không mở cổng database cho toàn Internet chỉ để standby kết nối. Giới hạn network source IP, TLS và role replication.

### 3.7. WAL stream không phải statement log

Standby không chạy lại `UPDATE accounts SET ...` theo SQL text. Nó nhận các WAL records vật lý và áp dụng thay đổi ở storage level. Do đó, physical replication giữ physical state của cluster, nhưng không cho phép subscriber có schema/data transformations độc lập.

### 3.8. Streaming và WAL archive

Streaming thường truyền WAL gần real time qua connection. WAL archiving lưu các WAL segments đã hoàn tất tới archive destination. Hai cơ chế bổ sung nhau:

- Streaming giúp standby theo kịp primary với độ trễ thấp.
- Archive cung cấp nguồn WAL khi standby bị disconnect lâu hơn lượng WAL local được giữ.

Một standby có thể dùng `restore_command` để lấy WAL từ archive rồi tiếp tục streaming khi kết nối upstream sẵn sàng.

## 4. Điều kiện tiên quyết và kiến trúc triển khai

### 4.1. Hai host/instance độc lập

Primary và standby nên có:

- Data directories riêng.
- Storage độc lập phù hợp failure domain.
- Hostname/IP và port được xác định rõ.
- Network route ổn định giữa standby và upstream.
- Clock synchronization để logs/metrics dễ tương quan.
- Disk capacity đủ cho data, WAL, temporary files và growth.

Đặt standby trên cùng host hoặc cùng storage failure domain với primary có thể hữu ích cho thử nghiệm, nhưng không tạo khả năng chịu lỗi host/storage thực sự.

### 4.2. Network và latency

Streaming replication cần network throughput đủ cho WAL generation rate. Với asynchronous replication, network lag có thể làm standby chậm. Với synchronous replication, latency/availability của standby có thể ảnh hưởng trực tiếp tới commit latency hoặc khả năng commit.

Đo:

- WAL bytes/sec trên primary.
- Network throughput và packet loss.
- Round-trip latency.
- Standby receive/flush/replay rate.
- Storage write latency trên standby.

### 4.3. Disk và WAL headroom

Ngoài data directory, dự trù:

- WAL segments đang hoạt động.
- WAL giữ bởi replication slots.
- WAL archive backlog.
- Base backup staging.
- Restore/rewind workspace.
- Log files và monitoring agents.

Một replication slot inactive có thể giữ WAL lâu dài và làm filesystem primary đầy.

### 4.4. Tài khoản replication

Tạo role chuyên dụng có quyền `REPLICATION` và `LOGIN`. Không dùng superuser chung cho standby nếu không cần.

### 4.5. Security baseline

- Chỉ cho standby/backup hosts được kết nối.
- Dùng SCRAM-SHA-256 hoặc authentication phù hợp.
- Bật TLS với certificate validation nếu kết nối qua network không tin cậy.
- Dùng secret/passfile được bảo vệ, không ghi password vào shell history.
- Theo dõi failed logins và replication disconnects.

## 5. Cấu hình primary cho physical streaming replication

Ví dụ dưới đây giả định primary là PostgreSQL trên host `db-primary`, port `5432`, standby có địa chỉ nguồn `10.20.0.12`. Thay các địa chỉ, role và path theo môi trường lab.

### 5.1. Kiểm tra version và role

```sql
SELECT version();
SHOW server_version_num;
SELECT pg_is_in_recovery();
```

Trên primary, `pg_is_in_recovery()` trả `false`.

### 5.2. Tạo role replication

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-managed-secret';
```

Đây là cú pháp minh họa trong lab. Production nên tạo password qua secret manager/passfile và tuân thủ rotation policy. Không commit secret vào repository hoặc backup script.

### 5.3. wal_level

```conf
wal_level = replica
```

`wal_level=replica` ghi đủ WAL information cho physical replication và PITR. `logical` ghi thêm thông tin cần cho logical decoding; nó vẫn hỗ trợ physical replication nhưng có overhead/requirements tương ứng.

`wal_level=minimal` không đủ cho streaming standby.

### 5.4. max_wal_senders

```conf
max_wal_senders = 10
```

Đây là ví dụ. Chọn số lượng đủ cho tất cả standbys, base backup sessions và headroom failover. Nếu hết slots, standby/backup có thể không kết nối được.

### 5.5. max_replication_slots

```conf
max_replication_slots = 10
```

Giá trị phải đủ cho physical và logical slots được dùng trên primary. Slot count không đồng nghĩa với số connections đang active; một slot có thể tồn tại khi consumer offline.

### 5.6. max_wal_size và wal_keep_size

```conf
max_wal_size = '4GB'
wal_keep_size = '1GB'
```

Các con số chỉ là ví dụ. `wal_keep_size` giữ một lượng WAL tối thiểu cho standby streaming; nếu standby offline lâu hơn, vẫn có thể thiếu WAL. Replication slot/archive là các cơ chế retention khác. `max_wal_size` không phải hard disk quota.

### 5.7. archive_mode và archive_command

Nếu cần standby có thể bắt kịp sau disconnect dài hoặc cần PITR, cấu hình WAL archiving:

```conf
archive_mode = on
archive_command = 'test ! -f /archive/%f && cp %p /archive/%f'
```

Command chỉ minh họa cho filesystem lab; production cần xử lý atomic copy, checksum, permissions, retry, archive monitoring và storage failure. Không dùng một thư mục archive trên cùng disk duy nhất với primary như failure-domain backup.

### 5.8. Áp dụng cấu hình

`wal_level`, `max_wal_senders` và `max_replication_slots` cần restart primary để thay đổi có hiệu lực (context `postmaster`). Một số tham số WAL retention có thể reload theo version/context.

Kiểm tra:

```sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_wal_size',
    'archive_mode'
)
ORDER BY name;
```

Không restart primary đang phục vụ chỉ để làm theo ví dụ; dùng change window và HA plan.

### 5.9. pg_hba.conf

Thêm rule chỉ cho standby:

```conf
# TYPE       DATABASE      USER        ADDRESS         METHOD
hostssl      replication   replicator  10.20.0.12/32   scram-sha-256
```

`replication` là database field đặc biệt cho replication connections. `hostssl` yêu cầu TLS. Nếu môi trường lab chưa cấu hình TLS, có thể dùng `host` trong network cách ly; production nên bật TLS và kiểm tra chứng thư.

Reload HBA:

```sql
SELECT pg_reload_conf();
```

Xem log để xác nhận rule được nạp. `pg_hba.conf` dùng rule đầu tiên khớp; một dòng rộng đặt trước có thể làm rule hẹp phía sau không bao giờ được dùng.

### 5.10. Xác minh primary sẵn sàng

```sql
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;

SELECT * FROM pg_stat_replication;
```

Trước khi standby kết nối, `pg_stat_replication` có thể chưa có row. Sau khi standby streaming, kiểm tra application_name/state và LSN progress.

## 6. Tạo standby bằng pg_basebackup

Standby phải có một bản sao physical ban đầu. Không thể chỉ cài PostgreSQL trống rồi bật `primary_conninfo` để nó tự tải toàn bộ database từ primary; cần base backup trước.

### 6.1. Dừng instance đích và chuẩn bị data directory

Trên host standby, cài cùng PostgreSQL major. Dừng service/instance được tạo tự động nếu có. Data directory đích phải trống hoặc được chuẩn bị theo đúng quy trình; không ghi đè data directory chứa dữ liệu cần giữ.

### 6.2. Chạy pg_basebackup

Ví dụ tạo standby với streaming WAL và physical slot:

```bash
pg_basebackup \
  -h db-primary.example.net \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/17/main \
  -F plain \
  -X stream \
  -C \
  -S standby_a \
  -R \
  -P
```

Ý nghĩa:

- `-h`, `-p`, `-U`: kết nối tới primary bằng role replication.
- `-D`: data directory standby.
- `-F plain`: ghi data directory ở dạng plain.
- `-X stream`: stream WAL cần thiết trong lúc base backup.
- `-C`: tạo replication slot nếu slot chưa tồn tại.
- `-S standby_a`: tên physical replication slot.
- `-R`: ghi recovery configuration cho standby.
- `-P`: hiển thị tiến độ.

Kiểm tra đúng binary/version, quyền thư mục, kết nối, TLS và disk capacity trước khi chạy. Với PostgreSQL major khác, options vẫn cần đối chiếu documentation cụ thể.

### 6.3. `-R` tạo gì?

Option `-R` tạo file `standby.signal` trong data directory và ghi cấu hình kết nối upstream (như `primary_conninfo`, `primary_slot_name`) vào `postgresql.auto.conf` theo tùy chọn đã dùng.

`standby.signal` báo cho PostgreSQL khi start rằng instance này cần vào standby/recovery mode.

### 6.4. Kiểm tra các file

Trên standby:

```bash
ls -l /var/lib/postgresql/17/main/standby.signal
grep -E 'primary_conninfo|primary_slot_name' \
  /var/lib/postgresql/17/main/postgresql.auto.conf
```

Trên Windows, dùng PowerShell `Get-Item`/`Get-Content` thay cho `ls`/`grep`. Không in password từ cấu hình vào ticket/log chia sẻ.

### 6.5. primary_conninfo

Ví dụ cấu hình:

```conf
primary_conninfo = 'host=db-primary.example.net port=5432 user=replicator application_name=standby_a sslmode=verify-full sslrootcert=/etc/postgresql/certs/ca.crt'
primary_slot_name = 'standby_a'
```

`application_name` giúp nhận diện standby trong `pg_stat_replication`. `sslmode=verify-full` kiểm tra CA và hostname theo TLS setup. Cần bảo vệ password bằng passfile/secret management nếu dùng password authentication.

### 6.6. primary_slot_name

Khi cấu hình slot, standby yêu cầu primary giữ WAL từ slot restart LSN để nó có thể tiếp tục sau disconnect. Nếu slot không tồn tại hoặc bị invalidated, standby có thể không kết nối/không bắt kịp.

Không tạo slot cho mọi standby mà không có capacity/monitoring. Một slot inactive có thể giữ WAL không giới hạn nếu không đặt policy phù hợp.

### 6.7. Start standby

Khởi động instance standby bằng service manager hoặc `pg_ctl` đúng data directory/port. PostgreSQL đọc `standby.signal`, kết nối upstream và bắt đầu nhận WAL.

### 6.8. Xác minh standby mode

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn;
```

Trên standby, `pg_is_in_recovery()` trả `true` trong khi ở recovery/standby. Nếu trả `false`, instance có thể đã được promote hoặc không khởi động ở standby mode.

### 6.9. Xác minh trên primary

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

Standby hoạt động thường có `state='streaming'`. `sync_state` có thể là async/sync/quorum theo cấu hình. Một row ở trạng thái `startup`/`catchup` có thể xuất hiện khi node đang bắt kịp; xem log và tiến độ LSN.

### 6.10. Xác minh bằng read query

Nếu `hot_standby=on`, thử:

```sql
SELECT current_database(), pg_is_in_recovery();
SELECT count(*) FROM app.orders;
```

Không chạy INSERT/UPDATE/DDL trên standby. Kết quả có thể lag so với primary nếu replication asynchronous hoặc replay đang chậm.

## 7. Cấu hình standby và các tham số recovery

### 7.1. standby.signal

Sự hiện diện của `standby.signal` khiến PostgreSQL start trong standby mode và tiếp tục recovery. Nếu file bị xóa ngoài ý muốn, server có thể start như một instance độc lập (tùy trạng thái/config), điều này nguy hiểm nếu node vẫn chứa bản sao của primary.

Không xóa `standby.signal` để "sửa replication" nếu chưa có quy trình promotion rõ ràng.

### 7.2. primary_conninfo

`primary_conninfo` chứa connection string để WAL receiver kết nối upstream. Các thành phần thường có:

- host/hostaddr và port.
- user replication.
- application_name để giám sát.
- sslmode, sslrootcert và các TLS options.
- passfile hoặc password nếu policy cho phép.

Không hard-code password trong file có quyền đọc rộng. `postgresql.auto.conf` có thể chứa connection string do `pg_basebackup -R` ghi; bảo vệ file và kiểm soát quyền filesystem.

### 7.3. primary_slot_name

Nếu standby dùng physical replication slot, cấu hình `primary_slot_name` trỏ tới slot trên upstream. Slot giữ WAL cần thiết cho standby ngay cả khi standby tạm disconnect.

Nếu không dùng slot, standby phụ thuộc `wal_keep_size` và/hoặc WAL archive để bắt kịp. Một standby offline lâu hơn WAL còn giữ có thể cần base backup mới.

### 7.4. restore_command

Nếu WAL segment cần thiết không còn trong local `pg_wal` hoặc streaming chưa có, standby có thể lấy segment từ archive bằng `restore_command`.

```conf
restore_command = 'cp /archive/%f %p'
```

`%f` là tên WAL file cần lấy; `%p` là destination path PostgreSQL yêu cầu. Ví dụ chỉ dùng cho lab filesystem. Production cần xử lý not-found, retry, integrity, credentials và archive backend đúng.

### 7.5. hot_standby

```conf
hot_standby = on
```

Cho phép connections read-only trong khi standby replay WAL. Tham số này phải bật để sử dụng hot standby; một số thay đổi yêu cầu restart tùy context/version. Query chỉ được thực hiện trên các trạng thái recovery cho phép.

### 7.6. hot_standby_feedback

```conf
hot_standby_feedback = on
```

Standby có thể gửi feedback về xmin horizon để primary tránh vacuum loại bỏ row versions mà query standby còn cần. Điều này giảm recovery conflicts nhưng có thể giữ dead tuples trên primary và tăng bloat.

Chỉ bật sau khi đánh giá workload và vacuum impact. Nó không giải quyết mọi loại conflict và không thay thế query timeout/replication design.

### 7.7. max_standby_streaming_delay

Tham số này đặt khoảng thời gian tối đa standby có thể trì hoãn replay WAL để cho read queries hoàn tất khi có recovery conflict. Nếu vượt ngưỡng, query có thể bị cancel để standby tiếp tục replay.

Tăng giá trị giúp reporting query có thêm thời gian nhưng làm replay lag tăng và dữ liệu đọc cũ hơn. Giá trị lớn không phải cách chữa mọi query cancel.

### 7.8. max_standby_archive_delay

Tương tự, tham số này áp dụng khi standby replay WAL lấy từ archive. Đặt giá trị phù hợp với SLA query và yêu cầu catch-up.

### 7.9. wal_receiver_timeout và wal_sender_timeout

Các timeout này giúp phát hiện connection im lặng/mất phản hồi. Tuning cần cân nhắc network latency, firewall idle timeout và workload. Timeout quá thấp có thể tạo reconnect churn; quá cao có thể làm phát hiện lỗi chậm.

### 7.10. Kiểm tra cấu hình hiệu lực

```sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'primary_conninfo',
    'primary_slot_name',
    'restore_command',
    'hot_standby',
    'hot_standby_feedback',
    'max_standby_streaming_delay',
    'max_standby_archive_delay',
    'wal_receiver_timeout'
)
ORDER BY name;
```

Một số setting nhạy cảm có thể bị che trong output theo quyền/phiên bản. Kiểm tra log WAL receiver để xác định connection thực tế.

## 8. Asynchronous streaming replication

Asynchronous replication là chế độ mặc định phổ biến của physical streaming replication. Primary không phải chờ standby flush WAL trước khi trả COMMIT thành công cho ứng dụng.

### 8.1. Luồng commit asynchronous

```text
Client                Primary                 Standby
  |                     |                        |
  |--- UPDATE/COMMIT -->|                        |
  |                     |-- flush local WAL      |
  |<-- COMMIT success --|                        |
  |                     |---- stream WAL ------->|
  |                     |                        |-- write/flush
  |                     |                        |-- replay
```

Standby có thể nhận và replay sau khi client đã nhận COMMIT success. Điều này giảm latency và giúp primary không phụ thuộc vào việc standby xác nhận từng commit.

### 8.2. Rủi ro mất dữ liệu khi failover

Nếu primary crash ngay sau khi xác nhận transaction nhưng trước khi standby nhận/flush WAL tương ứng, standby có thể thiếu các transactions đã được client thấy thành công. Khi promote standby đó, các commits chưa được replicate có thể bị mất.

Khoảng dữ liệu có thể mất phụ thuộc network, WAL generation, standby receive/flush progress và thời điểm sự cố. Asynchronous replication vì vậy có RPO có thể lớn hơn zero.

### 8.3. Lợi ích và giới hạn

Lợi ích:

- Commit latency không phải chờ network round trip tới standby.
- Standby chậm/mất kết nối không trực tiếp block commit.
- Dễ mở rộng nhiều standby với mục đích reporting/DR.

Giới hạn:

- Failover có thể mất một phần WAL chưa nhận/flush.
- Read replica có thể stale.
- Một standby có thể bị lag lâu mà primary vẫn tiếp tục ghi.
- Cần chọn đúng standby khi failover để giảm data loss.

### 8.4. Async không có nghĩa WAL không được flush trên primary

Với `synchronous_commit=on` nhưng không cấu hình synchronous standby, COMMIT vẫn chờ WAL local flush theo durability behavior bình thường. Khác biệt là nó không chờ remote standby acknowledgement.

## 9. Synchronous streaming replication

Synchronous replication cho phép primary đợi một hoặc nhiều standbys xác nhận WAL trước khi trả COMMIT thành công, theo `synchronous_standby_names` và `synchronous_commit`.

### 9.1. Cấu hình standby được chọn đồng bộ

Ví dụ trên primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

Primary ưu tiên standby đầu tiên đang phù hợp và hoạt động. Nếu standby_a mất kết nối, standby_b có thể được chọn làm synchronous standby theo thứ tự priority.

### 9.2. Quorum synchronous replication

Ví dụ:

```conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
```

Primary cần acknowledgement từ bất kỳ một standby trong nhóm để đáp ứng quorum là 1. Có thể dùng số lượng lớn hơn nếu yêu cầu nhiều replicas xác nhận.

### 9.3. application_name phải khớp

Giá trị `application_name` trong `primary_conninfo` của standby được dùng để nhận diện node trong `synchronous_standby_names`. Nếu tên không khớp, standby có thể vẫn streaming nhưng không được chọn làm synchronous standby.

Kiểm tra:

```sql
SELECT
    application_name,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

### 9.4. synchronous_commit

Tham số này điều khiển mức acknowledgement mà transaction commit cần chờ:

| Giá trị | COMMIT chờ tới đâu? | Ý nghĩa |
| --- | --- | --- |
| `off` | Không chờ local WAL flush theo transaction. | Có thể mất các commits vừa được xác nhận khi crash; vẫn duy trì database consistency. |
| `local` | Chờ WAL local flush. | Không chờ remote synchronous standby. |
| `remote_write` | Chờ synchronous standby ghi WAL tới OS, chưa nhất thiết fsync bền vững. | Có thể mất dữ liệu nếu standby OS/storage crash trước flush. |
| `on` | Chờ synchronous standby flush WAL tới durable storage. | Mức phổ biến để giảm nguy cơ mất committed transactions khi failover sang standby đã xác nhận. |
| `remote_apply` | Chờ standby replay WAL. | Transaction đã được áp dụng trên standby trước khi COMMIT trả về; hữu ích cho read-after-write trên standby nhưng tăng latency. |

Các mức remote chỉ có hiệu lực khi synchronous standby được cấu hình/chọn. Nếu không có synchronous standby, `on` không tự biến asynchronous replication thành synchronous.

### 9.5. Ví dụ cấu hình synchronous

Trên primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

Trên standby, cấu hình `application_name=standby_a` hoặc `standby_b`. Reload cấu hình primary nếu context cho phép; kiểm tra `pg_settings` và `pg_stat_replication.sync_state`.

### 9.6. Commit latency

Synchronous commit thêm network round trip và thời gian write/flush/replay trên standby theo mức `synchronous_commit`. Với `remote_apply`, primary chờ replay, thường chậm hơn `on`.

Nếu standby đặt ở vùng địa lý xa, latency mạng có thể trở thành phần đáng kể của mỗi commit.

### 9.7. Availability trade-off

Nếu primary yêu cầu một synchronous standby nhưng không standby nào đáp ứng, các transactions cần remote acknowledgement có thể phải chờ. Đây là đánh đổi: hệ thống chọn không xác nhận commit khi chưa có bản sao đáp ứng durability policy.

Có thể đặt `synchronous_commit=local` cho một số transactions để không chờ remote, nhưng khi đó transaction đó không có cùng bảo đảm remote như các transactions dùng `on`/`remote_apply`.

### 9.8. Synchronous không tự động failover

Synchronous replication chỉ xác định commit acknowledgement. Nó không tự phát hiện primary chết, không fence primary cũ và không tự promote standby. Cần HA manager/orchestrator hoặc runbook failover riêng.

### 9.9. Synchronous không đồng nghĩa zero data loss trong mọi kịch bản

Độ an toàn còn phụ thuộc standby nào được promote, số synchronous standbys, quorum, fencing, timeline và việc có transaction dùng `local`/`off`. Nếu promote một standby không nằm trong synchronous acknowledgement set hoặc có diverged history, vẫn có thể mất dữ liệu.

### 9.10. synchronous_commit theo transaction

Có thể đặt theo session hoặc transaction:

```sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';

UPDATE app.orders
SET status = 'confirmed'
WHERE order_id = 1001;

COMMIT;
```

Chỉ dùng mức remote_apply cho giao dịch cần read-after-write guarantee hoặc durability requirement cụ thể; không nhất thiết mọi query đều cần chi phí này.

## 10. Monitoring replication lag và WAL positions

Monitoring phải phân biệt WAL đã gửi, đã nhận, đã ghi, đã flush và đã replay.

### 10.1. pg_stat_replication trên primary

```sql
SELECT
    pid,
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
    replay_lag,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
```

Các vị trí:

- `sent_lsn`: WAL đã được gửi tới standby.
- `write_lsn`: WAL standby đã ghi.
- `flush_lsn`: WAL standby đã flush.
- `replay_lsn`: WAL standby đã replay vào data files.

Khoảng cách giữa các LSN cho biết vị trí đang chậm ở giai đoạn nào.

### 10.2. Tính byte lag

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS bytes_not_written,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS bytes_not_flushed,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS bytes_not_replayed
FROM pg_stat_replication
WHERE state = 'streaming';
```

Các phép trừ chỉ có ý nghĩa khi LSN không NULL và cùng WAL history. Đây là khoảng cách byte, không trực tiếp là số giây lag.

### 10.3. Tính khoảng cách primary tới replay

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind_primary
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
```

Trên primary, hàm `pg_current_wal_lsn()` trả vị trí WAL hiện tại. Dữ liệu có thể thay đổi ngay sau snapshot query.

### 10.4. pg_stat_wal_receiver trên standby

```sql
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
```

View này có tối đa một row cho WAL receiver đang hoạt động. Một số cột có thể thay đổi theo PostgreSQL major; kiểm tra schema trên server.

### 10.5. Receive và replay LSN trên standby

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

Nếu receive LSN lớn hơn replay LSN, standby đã nhận WAL nhưng còn backlog replay.

### 10.6. Timestamp lag có thể gây hiểu nhầm

`pg_last_xact_replay_timestamp()` là thời điểm commit transaction cuối cùng được replay, không phải một phép đo chính xác luôn luôn của network lag. Khi primary không có writes, timestamp cũ có thể khiến biểu đồ “lag” tăng dù standby đã theo kịp WAL.

Kết hợp LSN distance, `pg_stat_replication` lag intervals, receive/replay rate và workload rate để đánh giá.

### 10.7. write_lag, flush_lag, replay_lag

Các interval fields trong `pg_stat_replication` mô tả độ trễ phản hồi gần đây của standby cho các vị trí WAL tương ứng. Chúng có thể NULL khi standby đã bắt kịp hoặc không có transaction mới để đo. Không dùng một giá trị NULL làm bằng chứng standby hỏng.

### 10.8. Xác định trạng thái streaming

`state` thường có các trạng thái như `startup`, `catchup`, `streaming`, `backup` hoặc `stopping` tùy loại connection/version. Đối với standby đã bắt kịp, `streaming` là trạng thái mong đợi. Điều tra thêm log và WAL progress khi state khác.

### 10.9. Monitor theo delta

Statistics và LSN thay đổi liên tục. Lưu snapshots theo chu kỳ rồi tính:

- WAL generated bytes/sec.
- Receive bytes/sec.
- Replay bytes/sec.
- LSN distance.
- Lag duration.
- Slot retained bytes.
- Archive backlog.

Một điểm dữ liệu đơn lẻ không đủ để chẩn đoán xu hướng.

### 10.10. Wait events

Có thể xem process replication và wait events:

```sql
SELECT
    pid,
    backend_type,
    application_name,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type IN (
    'walsender',
    'walreceiver'
)
ORDER BY backend_type, pid;
```

Trường backend_type và wait events phụ thuộc version/role; quyền xem chi tiết có thể bị giới hạn.

## 11. WAL retention và replication slots

Standby chỉ có thể tiếp tục streaming nếu primary còn giữ các WAL segments mà standby chưa nhận. Nếu WAL cần thiết đã bị recycle/xóa và không có archive thay thế, standby không thể bắt kịp bằng stream hiện tại.

### 11.1. Không có slot: wal_keep_size

`wal_keep_size` đặt lượng WAL tối thiểu mà primary cố giữ lại cho standby. Đây là cơ chế đơn giản, nhưng không bảo đảm standby offline lâu tùy ý vẫn bắt kịp.

Nếu standby cần WAL cũ hơn mức còn giữ, nó có thể nhận lỗi yêu cầu WAL segment không tồn tại và cần restore từ archive hoặc tạo base backup mới.

### 11.2. Physical replication slot

Physical slot giữ WAL cần thiết cho một standby cụ thể dựa trên restart LSN của slot. Standby kết nối với slot qua `primary_slot_name`.

Tạo slot thủ công:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
```

Hoặc để `pg_basebackup -C -S standby_a` tạo slot trong lúc tạo backup. Không tạo cùng tên slot đã tồn tại.

### 11.3. Xem slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots;
```

Các cột `wal_status` và `safe_wal_size` có trên các major mới; query cần điều chỉnh nếu server cũ hơn. `restart_lsn` cho biết WAL cũ nhất slot còn cần giữ.

### 11.4. Slot inactive có thể làm đầy disk

Nếu standby mất kết nối nhưng slot vẫn tồn tại, primary phải giữ WAL để standby tiếp tục. Nếu standby không quay lại trong thời gian dài, WAL có thể tăng đến khi hết filesystem.

Giám sát:

- Slot inactive quá lâu.
- Restart LSN cũ.
- Retained WAL bytes.
- Disk free space.
- Consumer/standby last seen time.

### 11.5. max_slot_wal_keep_size

`max_slot_wal_keep_size` có thể giới hạn lượng WAL slot giữ lại trên các phiên bản hỗ trợ. Nếu vượt giới hạn, slot có thể bị invalidated hoặc không còn đảm bảo đủ WAL để consumer tiếp tục. Standby khi đó có thể phải lấy base backup mới.

Đây là biện pháp bảo vệ disk, không phải bảo đảm standby luôn bắt kịp. Đặt giới hạn phải phù hợp với outage duration và WAL generation peak.

### 11.6. Drop slot

Chỉ drop slot khi xác nhận standby/consumer không còn cần nó:

```sql
SELECT pg_drop_replication_slot('standby_a');
```

Không drop slot active hoặc đang được dùng trong production mà không hiểu tác động. Nếu standby quay lại sau khi slot bị drop và WAL đã recycle, nó có thể cần rebuild.

### 11.7. WAL archive bổ sung cho slot

Slot giữ WAL trên primary; archive lưu WAL segments bên ngoài primary. Một standby có thể dùng `restore_command` để lấy WAL đã archive nếu stream gap. Archive cũng phục vụ PITR và DR.

### 11.8. max_wal_size không phải giới hạn slot retention

`max_wal_size` là soft checkpoint target. Replication slots/archive có thể khiến `pg_wal` vượt giá trị đó. Đặt max_wal_size thấp không phải cách kiểm soát slot inactive.

### 11.9. Không xóa WAL thủ công

Không xóa file trong `pg_wal` bằng OS command để giải phóng disk. Việc đó có thể làm primary hoặc standby không thể crash-recover/replicate. Xử lý archive backlog, slot, standby lag và capacity theo quy trình PostgreSQL.

## 12. Hot standby và read-only queries

Khi `hot_standby=on`, standby có thể phục vụ SELECT trong khi recovery replay WAL. Đây là cách mở rộng read workload, nhưng query đọc một snapshot cũ có thể xung đột với các thay đổi mà WAL yêu cầu replay.

### 12.1. Read-only behavior

Standby trong recovery không cho phép writes thông thường:

- SELECT được hỗ trợ.
- INSERT/UPDATE/DELETE bị từ chối.
- DDL và nhiều thao tác quản trị thay đổi database không được phép.
- Một số temporary table/read-only session features được hỗ trợ theo giới hạn version.

Không coi standby là read-write replica độc lập.

### 12.2. Read-after-write

Trong asynchronous replication, một client có thể COMMIT trên primary rồi lập tức đọc từ standby và chưa thấy thay đổi. Nếu cần read-after-write:

- Đọc lại từ primary.
- Dùng synchronous replication với `synchronous_commit=remote_apply` cho transaction liên quan.
- Hoặc chờ standby replay tới LSN commit được ghi nhận (wait-for-replay pattern).

Không giả định tất cả standbys đã replay ngay sau COMMIT.

### 12.3. Recovery conflict

Standby phải replay WAL để giữ data files đúng với primary. Một read query dài có thể đang giữ snapshot cần row version cũ, trong khi WAL replay cần xóa/đổi cấu trúc đó. Đây là **recovery conflict**.

PostgreSQL có thể trì hoãn replay trong giới hạn cấu hình, sau đó cancel query nếu conflict vẫn tồn tại.

### 12.4. Các loại conflict

Recovery conflict có thể liên quan:

- Snapshot quá cũ cần row versions mà primary đã vacuum.
- Lock trên standby xung đột với lock được replay.
- Tablespace/database/object bị drop hoặc thay đổi.
- Buffer pin hoặc các điều kiện recovery khác.

Không phải mọi query cancel đều là lỗi mạng hoặc lỗi ứng dụng.

### 12.5. max_standby_streaming_delay

Tham số `max_standby_streaming_delay` đặt khoảng thời gian tối đa standby có thể trì hoãn replay WAL để cho read queries hoàn tất khi có recovery conflict. Nếu vượt ngưỡng, query có thể bị cancel để standby tiếp tục replay.

Tăng giá trị giúp reporting query có thêm thời gian nhưng làm replay lag tăng và dữ liệu đọc cũ hơn. Giá trị lớn không phải cách chữa mọi query cancel.

### 12.6. hot_standby_feedback

`hot_standby_feedback` gửi xmin feedback để primary biết không nên vacuum bỏ một số row versions còn cần cho query standby. Điều này giảm một số conflicts, nhưng có thể giữ dead tuples lâu hơn trên primary, gây bloat và tăng storage.

Feedback không giải quyết mọi conflict, ví dụ DDL/drop object hoặc lock conflicts. Đo bloat và vacuum impact trước khi bật.

### 12.7. Query design trên standby

- Giới hạn thời gian báo cáo và transaction duration.
- Tránh giữ transaction read-only mở lâu không cần thiết.
- Chạy batch/reporting theo khoảng thời gian có kiểm soát.
- Chấp nhận dữ liệu có độ trễ phù hợp với nghiệp vụ.
- Có retry/route-to-primary cho query bị cancel nếu đúng semantics.

### 12.8. Standby cho reporting

Một standby có thể dành riêng cho analytics/reporting. Nhưng workload báo cáo nặng có thể làm chậm replay do I/O/CPU và tạo conflicts. Cân nhắc thêm replica chuyên dụng hoặc logical replica nếu cần biến đổi schema/index độc lập.

### 12.9. Query lag và consistency

Một query trên standby thấy snapshot nhất quán tại trạng thái replay hiện tại, nhưng trạng thái đó có thể cũ hơn primary. Consistency của query snapshot không đồng nghĩa freshness so với primary.

## 13. Cascading replication

Cascading replication cho phép một standby truyền WAL tiếp cho standby khác, thay vì mọi standby đều kết nối trực tiếp primary.

### 13.1. Topology

```text
             +-----------+
             | PRIMARY   |
             +-----------+
                  |
            streaming WAL
                  |
                  v
             +-----------+
             | STANDBY A |
             +-----------+
                  |
            streaming WAL
                  |
             +----+----+
             |         |
             v         v
        STANDBY B  STANDBY C
```

Standby A vừa replay WAL vừa đóng vai trò upstream cho B/C.

### 13.2. Lợi ích

- Giảm số replication connections trực tiếp vào primary.
- Có thể đặt standbys theo region/site.
- Hữu ích khi WAN links hoặc primary egress cần được kiểm soát.

### 13.3. Giới hạn

- B/C không thể nhận WAL sớm hơn A nhận được.
- Lag có thể cộng dồn qua từng hop.
- A là dependency cho downstream B/C.
- Slot/WAL retention phải được quản lý trên upstream tương ứng.
- Failover/promote ở một tầng cần điều chỉnh topology downstream.

### 13.4. Cascading standby cần WAL sender capacity

Standby A phải có `max_wal_senders` đủ cho B/C và các connections khác. Nó cũng cần slot/retention phù hợp để giữ WAL cho downstream khi chúng disconnect.

### 13.5. Standby làm upstream

Trên standby A, cấu hình cho phép streaming/cascading theo tài liệu major và tạo replication slots nếu downstream cần. Downstream cấu hình `primary_conninfo` trỏ tới standby A, không phải primary.

### 13.6. Theo dõi từng hop

Quan sát `pg_stat_replication` trên mỗi upstream và `pg_stat_wal_receiver` trên mỗi downstream. Đừng chỉ nhìn primary → A rồi kết luận B/C đã bắt kịp.

### 13.7. Cascading và synchronous replication

Synchronous replication qua cascading topology cần được thiết kế kỹ: primary acknowledgement phụ thuộc các synchronous standbys được chọn và đường WAL/feedback qua các hops. Không giả định mọi downstream standby đều tham gia quorum chỉ vì chúng nằm phía sau một cascading standby.

## 14. Promotion và failover

Khi primary gặp sự cố, một standby có thể được **promote** thành primary mới. Đây là thao tác thay đổi vai trò của cluster, không đơn giản là khởi động lại một process.

### 14.1. Promotion là gì?

Promotion kết thúc recovery trên standby, cho phép nó nhận writes và tạo WAL mới. PostgreSQL tạo một **timeline mới** để phân biệt WAL history sau promotion với timeline của primary cũ.

### 14.2. Promote bằng SQL

Trên standby được chọn:

```sql
SELECT pg_promote(true, 60);
```

Hàm trả true nếu promotion thành công trong thời gian chờ. Nếu timeout, kiểm tra trạng thái/log trước khi retry; không promote nhiều nodes song song.

### 14.3. Promote bằng pg_ctl

Trên host standby:

```bash
pg_ctl -D /var/lib/postgresql/17/main promote
```

Dùng đúng data directory. Với service manager/HA orchestrator, thực hiện theo cơ chế promotion của công cụ đang quản lý cluster.

### 14.4. Xác minh sau promotion

```sql
SELECT pg_is_in_recovery();
SELECT pg_current_wal_lsn();
```

Primary mới trả `pg_is_in_recovery() = false` và có thể nhận writes. Kiểm tra log, timeline và kết nối ứng dụng trước khi mở traffic.

### 14.5. Chọn standby nào để promote?

Ưu tiên node:

- Có WAL receive/flush/replay tiến xa nhất.
- Có timeline phù hợp với primary cũ.
- Có storage/network/host khỏe.
- Có thể phục vụ workload và được cấu hình đủ capacity.
- Đáp ứng RPO đã định.

Không chỉ chọn node gần nhất về địa lý hoặc tên ưu tiên nếu nó bị lag nhiều.

### 14.6. Asynchronous failover có thể mất commits

Standby có replay LSN nhỏ hơn WAL đã commit trên primary có thể không chứa mọi commits đã được client xác nhận. Trước promotion, xác định khoảng WAL bị thiếu và RPO chấp nhận.

### 14.7. Synchronous failover

Nếu transaction commit đã chờ synchronous standby flush theo `synchronous_commit=on`, standby đã xác nhận có thể giữ các commits đó bền vững. Tuy nhiên, phải promote đúng standby đã tham gia acknowledgement policy và đảm bảo primary cũ không còn nhận writes.

### 14.8. Fencing primary cũ

**Fencing** bảo đảm primary cũ không thể tiếp tục phục vụ writes sau khi standby được promote. Có thể dùng:

- Tắt/stop instance cũ từ control plane.
- Thu hồi network access của ứng dụng.
- Fencing qua cloud/hypervisor/storage orchestration.
- STONITH hoặc cơ chế HA manager tương đương.

Không chỉ dựa vào ping hoặc mất kết nối từ một host để kết luận primary đã chết. Network partition có thể khiến primary vẫn chạy và nhận writes từ clients khác.

### 14.9. Split-brain

Split-brain xảy ra khi hai nodes cùng nhận writes như primary độc lập. Chúng tạo hai WAL timelines khác nhau; các writes sau thời điểm phân nhánh không tự merge.

Hậu quả có thể gồm:

- Mất một nhánh dữ liệu khi chọn primary mới.
- Duplicate business operations.
- Inconsistent external side effects.
- Khó khăn khi rejoin primary cũ.

Fencing và single-writer ownership là điều kiện bắt buộc của failover an toàn.

### 14.10. Không promote hai standby

Chỉ một standby được promote trong một failover event. Nếu nhiều standby tự promote vì health check/network partition không phối hợp, có thể tạo nhiều timelines độc lập. Dùng một HA authority/quorum và quy trình election/fencing.

### 14.11. Timeline sau promotion

Sau promotion, PostgreSQL chuyển sang timeline mới. Standbys khác phải nhận timeline history và follow đúng primary mới. WAL segments cùng LSN nhưng ở timelines khác nhau không thể được coi là cùng một WAL stream.

### 14.12. Repoint standbys còn lại

Sau khi primary mới ổn định:

1. Xác định primary mới và timeline.
2. Cấu hình các standbys còn lại trỏ tới primary mới (hoặc cascading upstream phù hợp).
3. Bảo đảm replication slots/credentials/HBA sẵn sàng.
4. Xác minh chúng follow timeline mới và replay tới.
5. Theo dõi lag và WAL retention.

Không chỉ sửa hostname; cần bảo đảm data history tương thích và node không đang ở một nhánh đã diverge.

## 15. Rejoin primary cũ sau failover

Primary cũ không thể đơn giản start lại như primary cùng với primary mới. Nó có thể chứa các WAL records thuộc timeline cũ sau điểm phân nhánh.

### 15.1. Vì sao cần rewind hoặc rebuild?

Sau promotion, primary mới tiếp tục tạo WAL trên timeline mới. Primary cũ có thể đã ghi thêm WAL độc lập trước khi bị fence. Hai data directories đã diverge.

Để đưa node cũ trở lại làm standby, cần:

- Dùng `pg_rewind` nếu thỏa preconditions và có đủ WAL history.
- Hoặc xóa/recreate data directory theo quy trình rồi lấy base backup mới từ primary mới.

### 15.2. pg_rewind làm gì?

`pg_rewind` so sánh timeline/history của source và target để xác định các data files/blocks đã thay đổi sau điểm phân nhánh, rồi copy phần cần thiết từ source sang target. Nó không phải một phép merge hai database histories.

### 15.3. Điều kiện pg_rewind

Các điều kiện quan trọng theo tài liệu PostgreSQL:

- Target cluster đã được shutdown sạch.
- Source và target có common ancestor timeline phù hợp.
- Data checksums đã bật khi initdb **hoặc** `wal_log_hints=on` được bật trước khi divergence.
- `full_page_writes=on` được duy trì.
- WAL cần thiết từ điểm phân nhánh còn sẵn ở target/source hoặc archive/restore path được cấu hình.
- Cùng PostgreSQL major version và binary tools tương thích.

Nếu không đáp ứng, dùng base backup mới thay vì ép rewind.

### 15.4. Kiểm tra trước rewind

Trên target cũ:

- Stop PostgreSQL và xác nhận không còn process sử dụng data directory.
- Xác minh đúng PGDATA và source connection string.
- Kiểm tra data checksums/`wal_log_hints` history.
- Bảo đảm WAL archive có đủ WAL từ divergence point.
- Có backup/snapshot của target nếu cần điều tra/rollback.

### 15.5. Ví dụ pg_rewind

Trên host target cũ đã stop:

```bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/17/old-primary \
  --source-server='host=new-primary.example.net port=5432 user=rewind_user dbname=postgres' \
  --write-recovery-conf
```

`--write-recovery-conf` ghi recovery configuration để target có thể start như standby (bao gồm signal/config phù hợp theo phiên bản). Cấu hình slot/primary_conninfo và credentials cần được kiểm tra sau rewind.

Nếu WAL cần thiết ở archive, xem option `--restore-target-wal` và `restore_command` theo version. Không giả định pg_rewind tự tìm được mọi WAL đã bị xóa.

### 15.6. Sau rewind

Kiểm tra:

- `standby.signal` tồn tại.
- `primary_conninfo` trỏ tới primary mới.
- `primary_slot_name` đúng nếu dùng slot.
- HBA/network/TLS/credentials hoạt động.
- Standby start và `pg_is_in_recovery()` trả true.
- Primary mới thấy connection trong `pg_stat_replication`.
- Replay LSN tiến và không còn timeline errors.

### 15.7. Rebuild bằng base backup

Nếu rewind không thể dùng hoặc không đáng tin:

1. Stop và cô lập target cũ.
2. Chuẩn bị data directory mới.
3. Chạy `pg_basebackup` từ primary mới.
4. Tạo slot/standby config.
5. Start standby và kiểm tra replay.

Rebuild thường đơn giản và an toàn hơn khi target đã diverge nhiều hoặc thiếu WAL, nhưng tốn thời gian/network/storage.

### 15.8. Không start primary cũ như read-write để “xem có dữ liệu gì”

Một node diverged không được phép phục vụ writes hoặc traffic ứng dụng. Nếu cần forensic, tạo bản copy cô lập và giữ nguyên evidence; không đưa node đó trở lại topology trước khi rewind/rebuild.

## 16. Streaming replication không thay thế backup

Replication giữ standby gần trạng thái primary. Backup giữ các điểm phục hồi độc lập trong quá khứ. Hai cơ chế giải quyết những failure modes khác nhau.

### 16.1. Lỗi được replicate sang standby

Các thay đổi hợp lệ ở mức PostgreSQL đều được ghi WAL và truyền tới standby, bao gồm cả:

- Người dùng vô tình DELETE dữ liệu.
- DROP TABLE/SCHEMA.
- UPDATE nhầm hàng loạt rows.
- Ứng dụng ghi dữ liệu sai nghiệp vụ.
- Một số dạng logical corruption được ghi vào pages.

Standby không biết thay đổi nào là nhầm. Nó replay WAL và tái tạo chính thay đổi đó.

### 16.2. Replication không cung cấp lịch sử dài hạn

Standby thường theo kịp primary và không tự giữ các versions cũ của database để rollback về tuần trước. Nếu lỗi logic được phát hiện sau vài giờ, standby có thể đã replicate lỗi.

### 16.3. Backup + WAL archive + replication

Một chiến lược tốt thường kết hợp:

- Physical streaming standby cho HA/failover nhanh.
- Base backups định kỳ.
- WAL archiving liên tục để PITR.
- Backup copies ở failure domain độc lập/immutable.
- Restore drills để xác nhận khả năng phục hồi.

### 16.4. Physical backup khác standby data directory

Standby data directory là node đang tham gia replication và có thể được promote. Base backup là artifact được lưu giữ độc lập, dùng để tạo lại node/restore cluster. Không coi việc có một standby là đã có backup.

### 16.5. RPO và asynchronous replication

Asynchronous standby có thể thiếu WAL đã commit khi primary hỏng. RPO thực tế phụ thuộc lag tại thời điểm failover và khả năng chọn standby có replay/flush tiến xa nhất.

### 16.6. Synchronous replication và RPO

Synchronous commit có thể giảm nguy cơ mất acknowledged transactions khi failover sang đúng standby đã xác nhận theo policy. Nó không thay backup/PITR và không bảo vệ trước xóa nhầm được replicate.

### 16.7. RTO

Standby đã bắt kịp có thể được promote nhanh hơn restore một base backup lớn. Tuy nhiên RTO còn phụ thuộc phát hiện lỗi, fencing, quyết định promote, định tuyến ứng dụng, kiểm tra consistency và reconfiguration các standbys còn lại.

## 17. HA architecture và failover orchestration

### 17.1. Manual failover

Phù hợp môi trường nhỏ hoặc khi có người trực vận hành:

1. Phát hiện primary không phục vụ.
2. Xác minh lỗi và fencing primary cũ.
3. Chọn standby phù hợp với RPO.
4. Promote đúng một standby.
5. Cập nhật endpoint/DNS/proxy/service discovery.
6. Kiểm tra writes và business invariants.
7. Repoint các standbys còn lại.

Manual failover dễ hiểu nhưng phụ thuộc thời gian phản ứng và kỷ luật runbook.

### 17.2. Automated failover

HA manager có thể monitor nodes, quyết định leader, fence node cũ, promote standby và cập nhật routing. Công cụ tự động hóa không loại bỏ nhu cầu hiểu quorum, network partition, fencing và timeline.

### 17.3. Health check phải nhiều chiều

Một node trả lời TCP hoặc `SELECT 1` không chứng minh nó là primary có thể nhận writes an toàn. Health check cần xem:

- PostgreSQL process/service availability.
- `pg_is_in_recovery()` và role hiện tại.
- WAL receiver/replication state.
- Lag/LSN progress.
- Disk free space và WAL retention.
- Application connectivity/transaction test.
- Fencing/leader ownership.

### 17.4. Quorum và split-brain prevention

Trong HA cluster, quyết định primary cần một authority/quorum để tránh hai phía của network partition cùng promote. Chỉ có hai database nodes mà không có witness/quorum/fencing phù hợp có thể khó phân biệt primary chết thật với primary bị cô lập mạng.

### 17.5. Fencing trước promotion

Trình tự an toàn là bảo đảm primary cũ không thể nhận writes rồi mới mở writes trên standby mới. Nếu hạ tầng hỗ trợ STONITH/cloud instance fencing, tích hợp nó vào orchestration. DNS change một mình không fence primary cũ vì clients có thể vẫn kết nối qua IP cũ.

### 17.6. Client routing

Ứng dụng nên kết nối qua endpoint/proxy/service discovery có thể cập nhật khi failover. Tránh hard-code IP primary vào hàng trăm services. Connection pools cần phát hiện connection cũ và reconnect sau role change.

### 17.7. Retry transaction sau failover

Khi connection mất trong COMMIT, client có thể không biết transaction đã commit hay chưa. Application phải xử lý unknown outcome bằng idempotency key/business request ID hoặc kiểm tra trạng thái trước khi retry. Replication không giải quyết duplicate side effects ở tầng ứng dụng.

### 17.8. Switchover có kế hoạch

Switchover là chuyển primary có kiểm soát, thường chờ standby bắt kịp, chuyển writes/role và promote node đích theo quy trình. Khác failover, primary cũ vẫn hoạt động và có thể được dừng/đưa về standby có kế hoạch.

### 17.9. Không nhầm switchover với failover

Switchover có thể chuẩn bị trạng thái và xác nhận WAL positions trước chuyển vai trò. Failover xảy ra khi primary gặp sự cố, có thể không lấy được xác nhận cuối cùng từ primary. RPO và mức độ bất định khác nhau.

## 18. Bảo mật physical replication

### 18.1. Role tối thiểu

Role replication chỉ cần quyền kết nối replication và các quyền cần cho quy trình backup. Không dùng superuser nếu không cần. Tách role replication, backup, monitoring và application.

### 18.2. pg_hba.conf hẹp

Ví dụ:

```conf
hostssl replication replicator 10.20.0.12/32 scram-sha-256
hostssl replication backup_user 10.20.0.20/32 scram-sha-256
```

Chỉ cho đúng nguồn IP và role. Kiểm tra thứ tự rules vì PostgreSQL dùng rule đầu tiên khớp.

### 18.3. TLS và certificate

Nếu replication đi qua network không tin cậy, dùng TLS và xác minh server certificate. Với `sslmode=verify-full`, hostname phải khớp certificate SAN/CN và client phải có CA phù hợp. Quản lý certificate rotation để tránh standby disconnect bất ngờ.

### 18.4. Password/passfile

Dùng passfile hoặc secret manager với quyền filesystem giới hạn. Tránh:

- Password trong shell command line.
- Password trong Git.
- Connection string in ra logs.
- Dùng một password chung cho mọi standby.

### 18.5. Network segmentation

Replication traffic nên ở private network/VPN/VPC route được kiểm soát. Firewall chỉ mở port cần thiết từ standby/backup hosts tới primary; không mở public internet.

### 18.6. Base backup chứa toàn bộ dữ liệu

Người có quyền lấy base backup có thể truy cập gần như toàn bộ cluster data, bao gồm dữ liệu nhạy cảm. Bảo vệ quyền replication/backup như quyền đọc dữ liệu toàn hệ thống.

### 18.7. Encryption at rest và backup copies

TLS bảo vệ dữ liệu trên đường truyền, không mã hóa data files/backup tự động. Dùng encryption at rest, backup encryption, key management và access auditing theo chính sách tổ chức.

### 18.8. Kiểm soát logs

Không ghi password/secret vào PostgreSQL logs, orchestration logs hoặc tickets. Logs replication vẫn chứa hostnames, IPs, slot names, LSNs và thông tin vận hành cần được kiểm soát.

## 19. Monitoring và cảnh báo production

Một dashboard replication cần hiển thị từng standby riêng, không chỉ một con số “replication healthy”.

### 19.1. Primary metrics

- Số WAL senders active và trạng thái từng connection.
- `state`/`sync_state` và application_name.
- Sent/write/flush/replay LSN.
- Write/flush/replay lag.
- WAL generated bytes/sec.
- Replication slots inactive và retained WAL.
- Archive success/failure và backlog.
- Disk free space của filesystem chứa `pg_wal`.

### 19.2. Standby metrics

- WAL receiver status và upstream host.
- Receive LSN, replay LSN và khoảng cách.
- Replay throughput.
- Last message receive time.
- Recovery conflicts và query cancellations.
- Disk free space, WAL/data write latency.
- `pg_is_in_recovery()` để xác nhận role.

### 19.3. Alert examples

Thiết lập threshold theo workload và RPO, ví dụ:

- Không có standby connection khi HA policy yêu cầu.
- Standby lag vượt RPO budget.
- WAL slot retention tăng liên tục.
- Slot inactive quá ngưỡng.
- Archive command thất bại liên tục.
- `pg_wal` filesystem gần đầy.
- Standby không replay tiến trong khi primary có WAL writes.
- Synchronous standby không available và commits đang chờ.

Không copy một threshold chung cho mọi hệ thống; baseline và WAL rate khác nhau.

### 19.4. Replication lag bytes và time

Bytes lag cho biết backlog WAL; time lag cho biết độ trễ theo thời gian. Với workload burst, cùng 100 MB backlog có thể mất vài giây hoặc vài phút để replay tùy storage/CPU. Dùng cả hai.

### 19.5. No-write periods

Nếu primary không có writes, replay timestamp có thể cũ nhưng standby vẫn bắt kịp. Alert nên phân biệt “không có WAL mới” với “standby không tiến dù có WAL mới”.

### 19.6. Synchronous wait monitoring

Theo dõi sessions chờ synchronous replication, wait events và `pg_stat_replication.sync_state`. Một standby sync bị chậm có thể làm COMMIT latency tăng hoặc khiến transactions chờ lâu.

### 19.7. Logs

Bật logging phù hợp để điều tra:

- Connection/disconnection của WAL receiver/sender.
- Requested WAL segment missing.
- Slot invalidation/retention.
- Recovery conflict/query cancellation.
- Promotion/recovery timeline events.
- Archive command failures.

Log rotation và retention cần đủ để phân tích sự cố.

## 20. Runbook thiết lập standby mới

Runbook sau mô tả thứ tự thao tác cho một standby mới trong môi trường đã có primary ổn định.

### Bước 1. Xác định thông tin topology

Ghi nhận:

- Primary hostname/IP, port, PostgreSQL major.
- Standby hostname/IP, data directory và port.
- Replication role và authentication method.
- Standby application_name.
- Physical slot name.
- TLS certificate/CA và firewall rules.
- WAL retention, archive và disk capacity.

### Bước 2. Kiểm tra primary

Xác minh `pg_is_in_recovery()` trả false, `wal_level` tối thiểu replica, đủ `max_wal_senders`, `max_replication_slots`, HBA rule và network.

### Bước 3. Tạo role và slot

Tạo role replication tối thiểu. Chọn một trong hai cách:

- Để `pg_basebackup -C -S slot_name` tạo slot.
- Tạo slot trước bằng `pg_create_physical_replication_slot` và dùng lại tên đó.

Không tạo trùng slot.

### Bước 4. Chuẩn bị standby

Cài cùng major, dừng service mặc định, chuẩn bị data directory trống, kiểm tra owner/permissions và disk space.

### Bước 5. Chạy base backup

Chạy `pg_basebackup` với `-X stream`, `-R`, slot name và progress. Theo dõi exit code, log, network và disk. Không start instance khi base backup còn dở.

### Bước 6. Kiểm tra recovery config

Xác nhận `standby.signal`, `primary_conninfo`, `primary_slot_name`, `restore_command` (nếu dùng) và TLS credentials. Không in secrets ra log.

### Bước 7. Start standby

Start đúng data directory. Theo dõi log cho tới khi WAL receiver kết nối và state tiến tới streaming.

### Bước 8. Xác minh hai phía

Trên primary: `pg_stat_replication` có standby đúng application_name và state.

Trên standby: `pg_is_in_recovery()` true, `pg_stat_wal_receiver` có row, receive/replay LSN tiến.

### Bước 9. Kiểm tra read-only

Chạy SELECT kiểm tra dữ liệu trên standby. Xác minh writes bị từ chối và application không route write traffic tới standby.

### Bước 10. Bật monitoring

Đăng ký node vào dashboard/alerts cho connection, lag, slot retention, archive, recovery conflicts và disk headroom.

### Bước 11. Ghi nhận baseline

Ghi WAL rate, network throughput, replay throughput và lag trong workload bình thường/peak. Dùng số liệu này để đặt alert và RPO.

## 21. Runbook failover

Failover thay đổi primary ownership. Mọi thao tác phải theo một authority duy nhất để tránh split-brain.

### Bước 1. Xác nhận incident

Kiểm tra primary process, host/storage/network và logs. Phân biệt primary thật sự down với một network partition từ góc nhìn của monitor.

### Bước 2. Fencing

Đảm bảo primary cũ không thể tiếp tục nhận writes: stop instance, fence host/storage hoặc thu hồi quyền truy cập theo HA control plane. Không bỏ qua bước này chỉ vì ping thất bại.

### Bước 3. Chọn standby

So sánh receive/flush/replay LSN, lag, timeline, node health và synchronous acknowledgement state. Chọn node phù hợp RPO và đã được fencing/authority xác nhận.

### Bước 4. Promote một node

Gọi `pg_promote` hoặc `pg_ctl promote` trên đúng standby. Chỉ một node được promote.

### Bước 5. Xác minh primary mới

Kiểm tra `pg_is_in_recovery() = false`, logs, timeline và khả năng read/write. Chạy business smoke test trước khi mở toàn bộ traffic.

### Bước 6. Chuyển traffic

Cập nhật proxy/service discovery/connection endpoint. Đóng connections cũ hoặc yêu cầu clients reconnect. Đảm bảo write requests không còn tới primary cũ.

### Bước 7. Đánh giá data loss

Ghi lại LSN/standby lag tại thời điểm promote, ước lượng WAL bị thiếu và đánh giá transactions chưa chắc chắn với application. Xử lý unknown COMMIT outcomes bằng idempotency/business request ID.

### Bước 8. Reconfigure standbys

Repoint các standby còn lại tới primary mới và timeline mới. Rejoin primary cũ bằng rewind/rebuild sau khi đã fence.

### Bước 9. Bảo đảm backup

Sau khi hệ thống ổn định, tạo/kiểm tra base backup mới theo policy và xác nhận WAL archiving tiếp tục trên primary mới.

### Bước 10. Post-incident review

Ghi timeline, RTO/RPO thực tế, data loss/uncertainty, nguyên nhân, thời gian từng bước và các thay đổi cần làm cho topology.

## 22. Runbook khi standby mất kết nối hoặc không bắt kịp

### 22.1. WAL receiver không kết nối

Kiểm tra:

- Host/port/DNS/route/firewall.
- `pg_hba.conf` và role replication.
- TLS CA, hostname và certificate expiry.
- Password/passfile permissions.
- Primary còn đủ `max_wal_senders` không.
- Slot tồn tại và không bị invalidated.

Đọc log standby và primary để xác định phía nào từ chối kết nối.

### 22.2. WAL segment không còn

Nếu standby yêu cầu segment đã bị recycle:

1. Kiểm tra archive có segment đó không.
2. Xác minh `restore_command` và timeline history.
3. Nếu archive có, sửa restore path và để standby replay.
4. Nếu không có WAL cần thiết, tạo base backup mới từ primary.

Không copy segment ngẫu nhiên hoặc tự tạo file WAL rỗng.

### 22.3. Slot giữ quá nhiều WAL

Xác định slot nào inactive, standby nào dùng slot, last seen và restart LSN. Khôi phục standby hoặc drop slot chỉ khi xác nhận node không còn cần nó. Đặt alert/capacity limit để tránh tái diễn.

### 22.4. Receive tiến nhưng replay đứng

Kiểm tra storage I/O, CPU, recovery conflict, logs, long-running read queries và recovery process. Nếu query trên standby liên tục trì hoãn replay, xem `max_standby_streaming_delay`/feedback policy.

### 22.5. Standby cần rebuild

Nếu WAL history bị thiếu hoặc timeline không thể nối lại, stop standby, giữ log/metadata để điều tra, chuẩn bị data directory mới và chạy base backup từ primary đúng timeline. Không khởi động node diverged như một primary độc lập.

## 23. Lab 1: tạo primary và standby trong môi trường riêng

Lab này cần hai PostgreSQL instances cùng major version trên hai hosts hoặc hai data directories/ports riêng biệt. Không sử dụng cluster production.

### 23.1. Xác định địa chỉ

Ví dụ:

| Thành phần | Giá trị lab |
| --- | --- |
| Primary host | `db-primary` |
| Primary port | `5432` |
| Standby host | `db-standby` |
| Standby source IP | `10.20.0.12` |
| Replication role | `replicator` |
| Application name | `standby_a` |
| Slot | `standby_a` |

Thay bằng hostnames, IP, port và paths thực tế của môi trường lab.

### 23.2. Cấu hình primary

Trong postgresql.conf:

```conf
wal_level = replica
max_wal_senders = 5
max_replication_slots = 5
wal_keep_size = '512MB'
hot_standby = on
```

Tham số ví dụ chỉ đủ cho lab nhỏ. Restart primary nếu thay đổi tham số có context postmaster; reload các tham số cho phép.

### 23.3. Tạo replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'lab-only-secret';
```

Chỉ dùng password giả lập trong cluster disposable. Không dùng password này trong môi trường thật.

### 23.4. Cấu hình pg_hba.conf

```conf
host replication replicator 10.20.0.12/32 scram-sha-256
```

Lab network phải được cách ly. Production nên dùng hostssl/TLS và firewall allowlist.

### 23.5. Chuẩn bị standby data directory

Dừng PostgreSQL instance đích. Xác nhận data directory standby trống hoặc được tạo mới. Không chạy pg_basebackup lên PGDATA đang hoạt động.

### 23.6. Chạy base backup

```bash
pg_basebackup \
  -h db-primary \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/17/standby_a \
  -F plain \
  -X stream \
  -C \
  -S standby_a \
  -R \
  -P
```

Nếu slot đã được tạo trước, bỏ `-C` và dùng slot đúng tên. Cung cấp password qua passfile/secret mechanism thay vì command line.

### 23.7. Xác minh recovery configuration

Kiểm tra `standby.signal`, `primary_conninfo` và `primary_slot_name`. Đảm bảo application_name là `standby_a` và host trỏ đúng primary.

### 23.8. Start standby

Start instance với data directory/port riêng. Theo dõi logs cho tới khi WAL receiver kết nối và bắt đầu streaming.

### 23.9. Kiểm tra primary

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

Kỳ vọng một row cho standby với application_name đúng và state tiến tới `streaming`.

### 23.10. Kiểm tra standby

```sql
SELECT pg_is_in_recovery();
SELECT * FROM pg_stat_wal_receiver;
SELECT pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn();
```

Kỳ vọng `pg_is_in_recovery()` trả true, WAL receiver active và LSN tiến khi primary có writes.

### 23.11. Thử dữ liệu được replicate

Trên primary:

```sql
CREATE TABLE public.replication_lab (
    id integer PRIMARY KEY,
    note text NOT NULL
);

INSERT INTO public.replication_lab
VALUES (1, 'written-on-primary');
```

Trên standby:

```sql
SELECT *
FROM public.replication_lab;
```

Row sẽ xuất hiện sau khi WAL được nhận và replay. Không cố INSERT trên standby.

### 23.12. Dọn lab

Chỉ sau khi hoàn tất kiểm thử, stop các lab instances và xóa các data directories đã tạo riêng cho lab. Drop slot/role chỉ khi không còn consumer nào dùng. Không áp dụng lệnh cleanup vào production.

## 24. Lab 2: quan sát asynchronous replication lag

### 24.1. Xác nhận asynchronous

Trên primary, để `synchronous_standby_names` rỗng hoặc không chọn standby cho synchronous policy trong lab. Kiểm tra `sync_state` của standby là async.

### 24.2. Tạo workload WAL

Trên primary:

```sql
CREATE TABLE IF NOT EXISTS public.replication_load (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO public.replication_load(payload)
SELECT repeat(md5(g::text), 8)
FROM generate_series(1, 50000) AS g;
```

Khối lượng thực tế phụ thuộc storage, network và cấu hình. Tăng dần trong lab, tránh tạo workload không giới hạn.

### 24.3. Đo primary-to-standby lag

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind
FROM pg_stat_replication;
```

Lấy nhiều snapshots theo thời gian để xem backlog tăng hay giảm.

### 24.4. Đo receive và replay trên standby

```sql
SELECT
    pg_last_wal_receive_lsn() AS received,
    pg_last_wal_replay_lsn() AS replayed,
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS bytes_waiting_for_replay;
```

Nếu receive tiến nhanh nhưng replay chậm, xem storage/CPU/recovery conflicts.

### 24.5. Thử đọc stale data

Tạo một row trên primary rồi đọc ngay từ standby. Tùy thời điểm, standby có thể chưa thấy row cho tới khi replay. Điều này minh họa eventual freshness của asynchronous replication.

### 24.6. Dọn dữ liệu lab

```sql
DROP TABLE public.replication_load;
DROP TABLE public.replication_lab;
```

Chỉ drop các bảng do lab tạo.

## 25. Lab 3: synchronous replication trong cluster riêng

Lab này cần một primary và một standby lab đã streaming.

### 25.1. Đặt application_name

Trên standby, cấu hình trong primary_conninfo:

```conf
primary_conninfo = 'host=db-primary port=5432 user=replicator application_name=standby_a'
```

Reconnect/restart receiver theo cách phù hợp để application_name mới có hiệu lực.

### 25.2. Chọn synchronous standby

Trên primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a)'
synchronous_commit = on
```

Reload cấu hình và kiểm tra `pg_stat_replication.sync_state` trở thành sync khi standby được chọn.

### 25.3. Kiểm tra COMMIT

```sql
BEGIN;
INSERT INTO public.replication_lab(id, payload)
VALUES (900001, 'sync-commit');
COMMIT;
```

COMMIT phải chờ acknowledgement remote flush theo policy khi standby sync hoạt động.

### 25.4. So sánh remote_apply

Trong lab:

```sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';
INSERT INTO public.replication_lab(id, payload)
VALUES (900002, 'remote-apply-commit');
COMMIT;
```

Remote apply đợi standby replay WAL. Dùng query trên standby để xác nhận row đã visible sau COMMIT.

### 25.5. Thử standby disconnect

Ngắt standby trong môi trường lab. Thực hiện một transaction cần synchronous acknowledgement và quan sát wait behavior. Dùng timeout/session cancel có kiểm soát; sau đó khôi phục standby.

Không chạy thí nghiệm này trên production vì có thể block commits.

### 25.6. Quay lại asynchronous

Sau lab, khôi phục `synchronous_standby_names`/`synchronous_commit` theo cấu hình ban đầu và xác nhận `sync_state`/commit behavior.

## 26. Lab 4: promotion trong cluster disposable

Lab này làm standby thành primary mới. Chỉ chạy trên cluster riêng có thể bỏ đi.

### 26.1. Xác minh trước promotion

Trên standby:

```sql
SELECT pg_is_in_recovery();
SELECT pg_last_wal_replay_lsn();
```

Ghi lại LSN và xác nhận standby đã bắt kịp trong điều kiện lab.

### 26.2. Stop/fence primary lab

Dừng primary lab và xác nhận không còn process/endpoint nào nhận writes. Trong production, bước này cần fencing control plane thực sự.

### 26.3. Promote standby

```sql
SELECT pg_promote(true, 60);
```

Hoặc dùng pg_ctl promote trên đúng standby data directory.

### 26.4. Xác minh primary mới

```sql
SELECT pg_is_in_recovery();
SELECT pg_current_wal_lsn();
```

Kỳ vọng recovery kết thúc và instance nhận writes.

### 26.5. Kiểm tra timeline

Dùng `pg_control_checkpoint()` hoặc `pg_controldata` để quan sát timeline/checkpoint metadata. Ghi lại timeline mới theo lab version.

### 26.6. Không khởi động primary cũ read-write

Primary cũ có thể diverge. Không start nó như primary. Nếu muốn rejoin, thử pg_rewind trên disposable copy với preconditions đầy đủ hoặc tạo base backup mới từ primary mới.

### 26.7. Dọn lab

Stop tất cả instances và xóa data directories lab riêng sau khi lưu kết quả cần thiết.

## 27. Lab 5: recovery conflict trên hot standby

Mục tiêu là quan sát read query có thể xung đột với WAL replay.

### 27.1. Tạo bảng trên primary

```sql
CREATE TABLE public.hot_standby_lab (
    id integer PRIMARY KEY,
    payload text NOT NULL
);

INSERT INTO public.hot_standby_lab
SELECT g, repeat('x', 100)
FROM generate_series(1, 10000) AS g;
```

### 27.2. Mở transaction đọc lâu trên standby

Trên standby:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT count(*) FROM public.hot_standby_lab;
-- Giữ transaction mở trong thời gian lab.
```

### 27.3. Thay đổi dữ liệu trên primary

Trên primary:

```sql
DELETE FROM public.hot_standby_lab
WHERE id BETWEEN 1 AND 5000;
VACUUM public.hot_standby_lab;
```

WAL replay trên standby có thể gặp conflict với snapshot cũ.

### 27.4. Quan sát log và query

Tùy cấu hình delay/feedback, standby có thể trì hoãn replay hoặc cancel query. Xem server logs, recovery conflict statistics và replay LSN.

### 27.5. Kết thúc lab

COMMIT/ROLLBACK transaction standby. Drop bảng lab trên primary nếu không cần. Khôi phục tham số đã thay đổi.

## 28. Lab 6: kiểm tra WAL slot retention

### 28.1. Xác định slot

```sql
SELECT slot_name, active, restart_lsn
FROM pg_replication_slots;
```

### 28.2. Ngắt standby lab

Dừng standby disposable trong một khoảng thời gian ngắn, giữ slot. Tạo WAL có kiểm soát trên primary lab.

### 28.3. Quan sát retained WAL

```sql
SELECT
    slot_name,
    active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS retained_distance
FROM pg_replication_slots;
```

Khoảng cách LSN là một chỉ báo; không phải phép đo chính xác disk bytes retained vì segment recycling/other slots/archive conditions cũng ảnh hưởng.

### 28.4. Khởi động standby lại

Start standby và quan sát nó bắt kịp từ slot nếu WAL cần thiết vẫn còn. Nếu slot đã invalidated hoặc WAL thiếu, lab có thể cần base backup mới.

### 28.5. Dọn slot

Chỉ drop slot sau khi standby lab đã được dừng và không còn dùng slot.

## 29. Những sai lầm thường gặp

### 29.1. Chỉ bật primary_conninfo mà không có base backup

Standby cần data directory physical tương thích trước khi replay WAL. Tạo một instance trống rồi cấu hình upstream không thay thế base backup.

### 29.2. Nhầm physical replication với logical replication

Physical replication truyền WAL và sao chép toàn cluster. Logical replication truyền thay đổi logical ở publications/subscriptions, có thể chọn tables và hỗ trợ schema khác biệt trong giới hạn.

### 29.3. Dùng khác major version

Physical data directory không phải định dạng dùng chung giữa major versions. Dùng cùng major hoặc thực hiện major upgrade/migration theo quy trình riêng.

### 29.4. Quên wal_level

Nếu `wal_level` không đủ, primary không tạo đủ WAL information cho streaming standby. Kiểm tra setting và pending_restart trước khi tạo replica.

### 29.5. max_wal_senders quá thấp

Standby hoặc pg_basebackup có thể không kết nối được khi hết WAL sender slots. Tính cả standbys, backup sessions, logical consumers và headroom.

### 29.6. HBA rule sai hoặc quá rộng

Replication connection dùng database field đặc biệt `replication`. Rule sai thứ tự hoặc source IP có thể khiến connection bị từ chối hoặc mở rộng quyền ngoài ý muốn.

### 29.7. Quên standby.signal

Nếu standby không khởi động ở recovery mode, nó có thể không kết nối upstream và không replay WAL. Xác minh signal file sau base backup và sau thao tác rejoin.

### 29.8. Không dùng slot hoặc retention không đủ

Standby offline lâu có thể yêu cầu WAL segment đã bị recycle. Dùng physical slot/archive phù hợp hoặc rebuild bằng base backup khi gap không thể phục hồi.

### 29.9. Slot inactive không được giám sát

Slot giữ WAL và có thể làm đầy filesystem primary. Đặt alert cho inactive slots, restart_lsn cũ và disk free space.

### 29.10. Nghĩ max_wal_size là disk cap

Archive backlog và replication slots có thể giữ WAL vượt max_wal_size. Xử lý retention blockers, không xóa file thủ công.

### 29.11. Nghĩ standby nhận WAL tức là đã replay

Receive/write/flush/replay là các giai đoạn khác nhau. Read query chỉ thấy trạng thái đã replay.

### 29.12. Đọc từ standby ngay sau COMMIT rồi kết luận dữ liệu mất

Asynchronous standby có thể chưa replay transaction. Route read-after-write về primary hoặc dùng remote_apply/wait-for-replay khi cần.

### 29.13. Dùng timestamp replay làm lag duy nhất

Khi primary không có writes, timestamp cuối có thể cũ dù standby bắt kịp. Dùng LSN distances và workload rate cùng timestamp.

### 29.14. Tăng max_standby_streaming_delay vô hạn

Điều này có thể giữ query lâu nhưng làm replay lag tăng và WAL retention phình to. Xem query duration, hot_standby_feedback và workload routing.

### 29.15. Bật hot_standby_feedback mà không theo dõi bloat

Feedback có thể giữ dead tuples trên primary để query standby không bị cancel. Theo dõi vacuum, dead tuples và table bloat.

### 29.16. Dùng synchronous replication mà quên application_name

Standby có thể streaming nhưng không được chọn làm synchronous standby nếu tên không khớp `synchronous_standby_names`.

### 29.17. Nghĩ synchronous replication tự failover

Synchronous commit chỉ điều khiển acknowledgement. Cần fencing, leader election, promotion và routing riêng.

### 29.18. Promote trước khi fence primary cũ

Network partition có thể khiến primary cũ vẫn nhận writes. Hai primaries tạo timelines diverged và split-brain.

### 29.19. Promote nhiều standbys

Nhiều promotion độc lập tạo nhiều nhánh WAL. Dùng một HA authority và chỉ promote một node.

### 29.20. Bỏ qua timeline sau promotion

Standbys còn lại cần follow timeline mới. Không chỉ đổi hostname nếu data history đã diverge.

### 29.21. Start primary cũ read-write sau failover

Node cũ có thể có WAL divergent. Phải rewind/rebuild trước khi rejoin làm standby.

### 29.22. Dùng pg_rewind khi thiếu preconditions

Target phải shutdown sạch, có common timeline ancestor, checksums hoặc wal_log_hints phù hợp và WAL cần thiết. Nếu không đủ, lấy base backup mới.

### 29.23. Nghĩ replication thay backup

DELETE/DROP nhầm được replicate. Cần base backups, WAL archive, PITR và backup immutable.

### 29.24. Chạy read workload nặng trên standby mà không tính replay

Reporting query có thể tranh CPU/I/O với WAL replay và tạo recovery conflicts. Đo lag và tách workload khi cần.

### 29.25. Không test failover/rejoin

Một standby streaming hôm nay chưa chứng minh promotion, fencing, client routing và rewind hoạt động. Diễn tập đầy đủ trong môi trường tương tự production.

## 30. Bài tập thực hành

Các bài tập dùng topology lab hoặc yêu cầu phân tích cấu hình. Những bài promotion/fencing/rebuild chỉ thực hiện trên cluster disposable.

### Bài 1. Vai trò

Phân biệt primary, physical standby, WAL sender và WAL receiver.

### Bài 2. Physical vs logical

Vì sao physical replication sao chép toàn cluster còn logical replication có thể chọn tables?

### Bài 3. Base backup

Vì sao standby cần base backup trước khi streaming WAL?

### Bài 4. WAL stages

Phân biệt WAL sent, write, flush và replay. Stage nào quyết định dữ liệu visible cho read query trên standby?

### Bài 5. Cấu hình primary

Nêu mục đích của `wal_level`, `max_wal_senders` và `max_replication_slots`.

### Bài 6. Replication role

Viết SQL tạo role login có quyền REPLICATION.

### Bài 7. HBA

Viết một rule pg_hba.conf cho role replicator từ standby IP 10.20.0.12.

### Bài 8. pg_basebackup

Giải thích các options `-X stream`, `-C`, `-S`, `-R` và `-P`.

### Bài 9. standby.signal

File này có ý nghĩa gì? Vì sao không nên xóa nó để xử lý lỗi kết nối?

### Bài 10. primary_conninfo

Nêu các thành phần thường có trong connection string và vai trò của application_name.

### Bài 11. Replication slot

Slot giữ WAL như thế nào? Rủi ro của slot inactive là gì?

### Bài 12. wal_keep_size

Vì sao wal_keep_size không bảo đảm standby offline lâu vẫn bắt kịp?

### Bài 13. Async

Một transaction COMMIT thành công trên primary nhưng standby chưa nhận WAL. Nếu primary crash và standby được promote, điều gì có thể xảy ra?

### Bài 14. Sync

Viết cấu hình synchronous_standby_names chọn standby_a làm synchronous standby đầu tiên.

### Bài 15. synchronous_commit

Phân biệt remote_write, on và remote_apply.

### Bài 16. application_name

Standby streaming nhưng sync_state là async. Một nguyên nhân cấu hình phổ biến là gì?

### Bài 17. Monitoring

Viết SQL đọc sent_lsn, write_lsn, flush_lsn và replay_lsn từ pg_stat_replication.

### Bài 18. Byte lag

Viết SQL tính bytes phía sau giữa current WAL LSN và replay_lsn của từng standby.

### Bài 19. Standby receiver

View nào trên standby cho biết WAL receiver connection? Nêu ít nhất ba trường có thể xem.

### Bài 20. Replay timestamp

Vì sao pg_last_xact_replay_timestamp không phải thước đo lag duy nhất?

### Bài 21. Hot standby

Standby hot standby có cho phép UPDATE không? Vì sao read query có thể bị cancel?

### Bài 22. hot_standby_feedback

Nêu lợi ích và đánh đổi của tham số này.

### Bài 23. Cascading

Một standby A làm upstream cho B và C. Nêu hai lợi ích và ba giới hạn.

### Bài 24. Promotion

Viết SQL promote standby và query xác minh nó đã thoát recovery.

### Bài 25. Fencing

Vì sao phải fence primary cũ trước khi promote standby?

### Bài 26. Timeline

Timeline mới xuất hiện khi nào? Vì sao WAL cùng LSN ở hai timelines khác nhau không thể coi là cùng một stream?

### Bài 27. pg_rewind

Nêu ít nhất bốn preconditions quan trọng để dùng pg_rewind.

### Bài 28. Rebuild

Khi nào nên tạo base backup mới thay vì pg_rewind?

### Bài 29. Backup

Vì sao physical streaming replication không thay thế backup và PITR?

### Bài 30. HA design

Thiết kế topology cho một ứng dụng cần RPO thấp, read scaling và disaster recovery ở region khác. Nêu synchronous/asynchronous choices, backup, WAL archive, monitoring và failover steps.

## 31. Gợi ý lời giải bài tập

### Đáp án 1. Vai trò

- Primary nhận writes, tạo WAL và gửi WAL.
- Physical standby nhận/replay WAL để duy trì bản sao vật lý.
- WAL sender chạy trên upstream và truyền WAL.
- WAL receiver chạy trên standby và nhận WAL.

### Đáp án 2. Physical vs logical

Physical replication áp dụng WAL lên data files của toàn cluster, nên không chọn từng table. Logical replication đọc logical changes qua publications/subscriptions và có thể chọn tables theo thiết kế.

### Đáp án 3. Base backup

WAL chỉ mô tả thay đổi tiếp theo, không phải bản sao đầy đủ của mọi data pages. Standby cần một base backup làm nền rồi mới replay WAL tiếp tục.

### Đáp án 4. WAL stages

- Sent: primary đã gửi.
- Write: standby đã ghi vào WAL storage.
- Flush: WAL đã flush bền vững theo feedback.
- Replay: recovery process đã áp dụng WAL vào data files.

Read query trên standby nhìn thấy trạng thái đã replay.

### Đáp án 5. Cấu hình primary

`wal_level` quyết định loại thông tin WAL được ghi; `max_wal_senders` giới hạn WAL sender connections; `max_replication_slots` giới hạn số replication slots được tạo.

### Đáp án 6. Replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'managed-secret';
```

Trong production, dùng secret manager/passfile và không đưa password vào shell history hoặc source control.

### Đáp án 7. HBA

```conf
hostssl replication replicator 10.20.0.12/32 scram-sha-256
```

Rule yêu cầu TLS; host/IP và role phải khớp standby thực tế.

### Đáp án 8. pg_basebackup

- `-X stream` stream WAL trong lúc backup.
- `-C` tạo replication slot nếu chưa tồn tại.
- `-S` chọn slot name.
- `-R` tạo standby.signal và recovery connection config.
- `-P` hiển thị progress.

### Đáp án 9. standby.signal

File này khiến PostgreSQL start trong standby/recovery mode. Xóa nó có thể khiến node không còn follow primary; không dùng xóa file để chữa connection issue vì có nguy cơ tạo instance độc lập/diverged.

### Đáp án 10. primary_conninfo

Gồm host/port/user, application_name, TLS options và passfile/password theo policy. application_name nhận diện standby trong pg_stat_replication và được dùng để chọn synchronous standby.

### Đáp án 11. Replication slot

Slot giữ WAL từ restart_lsn cũ nhất mà consumer còn cần. Slot inactive lâu có thể giữ nhiều WAL và làm đầy filesystem primary.

### Đáp án 12. wal_keep_size

Đây là lượng WAL tối thiểu cố giữ, không phải retention vô hạn. Standby offline lâu hơn lượng WAL được giữ có thể cần archive hoặc base backup mới.

### Đáp án 13. Async

Standby có thể thiếu transaction đã được primary xác nhận. Nếu promote standby đó, transaction chưa nhận/flush/replay có thể mất. RPO phụ thuộc lag tại thời điểm failover.

### Đáp án 14. Sync

```conf
synchronous_standby_names = 'FIRST 1 (standby_a)'
```

Tên phải khớp application_name trên standby.

### Đáp án 15. synchronous_commit

- `remote_write` chờ standby ghi WAL tới OS nhưng chưa nhất thiết fsync.
- `on` chờ standby flush WAL bền vững.
- `remote_apply` chờ standby replay WAL trước khi COMMIT trả về.

### Đáp án 16. application_name

Tên trong primary_conninfo không khớp với danh sách synchronous_standby_names nên standby không được chọn làm synchronous standby.

### Đáp án 17. Monitoring

```sql
SELECT
    application_name,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

### Đáp án 18. Byte lag

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
```

Đây là khoảng cách bytes, không phải thời gian lag chính xác.

### Đáp án 19. Standby receiver

View `pg_stat_wal_receiver`. Có thể xem status, sender_host, sender_port, written_lsn, flushed_lsn, latest_end_lsn, latest_end_time và slot_name (cột phụ thuộc major).

### Đáp án 20. Replay timestamp

Nếu primary không có writes, timestamp cuối replay không đổi dù standby đã bắt kịp. Kết hợp timestamp với LSN distance, WAL generation rate và receive/replay progress.

### Đáp án 21. Hot standby

Không. Hot standby chỉ cho read-only queries trong recovery. Query có thể bị cancel nếu xung đột với WAL replay, ví dụ snapshot cũ cần row versions mà primary đã vacuum.

### Đáp án 22. hot_standby_feedback

Nó gửi xmin feedback để primary giữ row versions cần cho standby queries, giảm một số recovery conflicts. Đánh đổi là dead tuples có thể tồn tại lâu hơn trên primary, tăng bloat.

### Đáp án 23. Cascading

Lợi ích: giảm connections trực tiếp tới primary và đưa WAL qua các regions/sites. Giới hạn: downstream không thể nhận sớm hơn upstream, lag có thể cộng dồn, upstream trở thành dependency và cần WAL retention cho downstream.

### Đáp án 24. Promotion

```sql
SELECT pg_promote(true, 60);
SELECT pg_is_in_recovery();
```

Sau promotion, query thứ hai trả false. Chỉ chạy sau khi fencing primary cũ và chọn đúng standby.

### Đáp án 25. Fencing

Primary cũ có thể vẫn chạy và nhận writes trong network partition. Nếu standby được promote trước fencing, hai nodes cùng nhận writes và tạo split-brain/divergent timelines.

### Đáp án 26. Timeline

Timeline mới được tạo khi standby promote. Nó phân biệt WAL history mới với nhánh cũ. Cùng một LSN ở hai timelines có thể chứa các records khác nhau nên không thể nối tùy ý.

### Đáp án 27. pg_rewind

Ví dụ preconditions:

1. Target shutdown sạch.
2. Source/target có common timeline ancestor.
3. Data checksums bật từ initdb hoặc wal_log_hints bật trước divergence.
4. full_page_writes bật.
5. WAL cần thiết từ divergence point còn sẵn.
6. Cùng PostgreSQL major version.

### Đáp án 28. Rebuild

Khi thiếu WAL cần thiết, timeline history không tương thích, preconditions rewind không đáp ứng, target diverged lâu hoặc cần phương án đơn giản/đáng tin hơn. Tạo base backup mới từ primary hiện tại.

### Đáp án 29. Backup

Replication cũng replicate DELETE/DROP/corruption logic. Nó không giữ lịch sử dài hạn và không cung cấp PITR. Cần base backups, WAL archive và backup copies độc lập.

### Đáp án 30. HA design

Một thiết kế có thể:

1. Primary ở region chính.
2. Synchronous standby gần primary cho durability/HA và RPO thấp; dùng synchronous_commit phù hợp.
3. Asynchronous standby ở region DR để tránh WAN latency làm mọi commits chậm, với RPO được chấp nhận và WAL archive liên tục.
4. Standby reporting riêng nếu cần read scaling; theo dõi replay lag và recovery conflicts.
5. Base backups định kỳ, WAL archive ở failure domain độc lập/immutable.
6. Monitor pg_stat_replication, pg_stat_wal_receiver, slots, archive backlog, disk và lag.
7. Failover: phát hiện incident, fence primary, chọn standby theo RPO, promote đúng một node, chuyển traffic, rejoin các nodes còn lại.
8. Test restore/PITR và failover định kỳ; ghi RTO/RPO thực tế.

Không thể đạt RPO thấp chỉ bằng việc tạo nhiều standby; cần synchronous acknowledgement, fencing và chọn đúng node khi failover.



## 32. Checklist thiết kế và vận hành streaming replication

### 32.1. Topology và base backup

1. Primary và standby có cùng PostgreSQL major version không?
2. Standby được tạo từ base backup physical tương thích không?
3. PGDATA, tablespaces và WAL storage có được inventory không?
4. Có xác định failure domains của primary/standby không?
5. `pg_basebackup` có lấy WAL cần thiết và kiểm tra exit code không?
6. `standby.signal` và recovery configuration có đúng không?

### 32.2. Primary configuration và security

7. `wal_level` có ít nhất là replica không?
8. `max_wal_senders` đủ cho standbys/backups/consumers và headroom không?
9. `max_replication_slots` đủ cho slots được sử dụng không?
10. Replication role có quyền tối thiểu không?
11. `pg_hba.conf` chỉ cho đúng IP/role và authentication method không?
12. TLS/hostname verification và secret management có được cấu hình không?
13. `application_name` có unique và rõ ràng cho từng standby không?

### 32.3. WAL retention và replication slots

14. Mỗi standby có physical slot hay retention/archive policy phù hợp không?
15. Inactive slots có alert và owner không?
16. `max_slot_wal_keep_size` có được cân nhắc để bảo vệ disk không?
17. Archive command có được giám sát và WAL chain có liên tục không?
18. Disk alert cho `pg_wal` có đủ headroom không?
19. Có cấm xóa WAL files thủ công trong runbook không?

### 32.4. Consistency, lag và read scaling

20. Monitoring phân biệt sent/write/flush/replay LSN không?
21. Có đo cả byte lag và time lag không?
22. Có phân biệt idle/no-WAL với standby không replay không?
23. Read-after-write có route đúng theo consistency requirement không?
24. Hot standby queries có giới hạn duration và recovery conflict monitoring không?
25. `hot_standby_feedback` có được cân nhắc cùng vacuum/bloat impact không?
26. Cascading topology có monitor từng hop không?

### 32.5. Synchronous replication

27. `synchronous_standby_names` có khớp `application_name` không?
28. Quorum/priority có phù hợp availability policy không?
29. `synchronous_commit` có được chọn theo durability/latency không?
30. Có biết transactions dùng local/off không có cùng remote acknowledgement không?
31. Có cảnh báo synchronous standby unavailable và commits chờ không?

### 32.6. Failover và recovery

32. Có một HA authority/quorum duy nhất không?
33. Có fencing primary cũ trước promotion không?
34. Có chỉ promote một standby không?
35. Có đánh giá lag/RPO và chọn node phù hợp không?
36. Có quy trình timeline/repoint các standbys còn lại không?
37. Primary cũ được rewind/rebuild trước khi rejoin không?
38. `pg_rewind` preconditions có được kiểm tra không?
39. Có base backups và WAL archive độc lập với replication không?
40. Có failover, switchover, rewind, PITR và restore drills định kỳ không?

## 33. Tổng kết

**Physical streaming replication** giữ một hoặc nhiều standbys gần trạng thái primary bằng cách truyền WAL records. Primary tạo WAL và WAL sender gửi stream; standby dùng WAL receiver để nhận, ghi, flush và replay WAL lên physical data files. Base backup tạo nền ban đầu cho standby.

Những nguyên tắc quan trọng:

- Physical replication sao chép toàn cluster và cần tương thích PostgreSQL major version.
- Standby phải có base backup; `standby.signal` và `primary_conninfo` đưa instance vào recovery/streaming mode.
- `pg_basebackup -R -X stream` là cách phổ biến tạo standby; physical slot giúp giữ WAL cần thiết nhưng phải giám sát retention.
- Asynchronous replication giảm commit latency nhưng có thể mất acknowledged transactions khi failover.
- Synchronous replication dùng `synchronous_standby_names` và `synchronous_commit` để chờ remote write/flush/apply theo policy, đổi lại latency và availability trade-off.
- Sent, write, flush và replay LSN là các giai đoạn khác nhau; read query trên standby chỉ thấy trạng thái đã replay.
- Hot standby phục vụ read-only queries nhưng có recovery conflicts; `hot_standby_feedback` giảm một số conflicts và có thể tăng bloat trên primary.
- Cascading replication giảm connections trực tiếp tới primary nhưng lag/dependency có thể cộng dồn qua các hops.
- Promotion tạo timeline mới; fencing primary cũ và single-writer ownership ngăn split-brain.
- Primary cũ cần `pg_rewind` khi đủ điều kiện hoặc base backup mới trước khi rejoin.
- Replication không thay backup: lỗi logic được replicate; cần base backups, WAL archive và PITR.
- Monitoring phải bao gồm lag, slots, archive, disk, recovery conflicts, synchronous waits và role state.
- Failover chỉ hoàn tất khi traffic được chuyển, data consistency được xác nhận và các standbys được reconfigure.

Nguyên tắc thực hành:

> **Thiết kế streaming replication cùng WAL retention, fencing, backup và recovery drills; chỉ coi HA hoạt động khi failover và rejoin đã được kiểm thử end-to-end.**

## 34. Tài liệu tham khảo

Tài liệu PostgreSQL chính thức; chọn đúng major version của primary/standby:

- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication, standby modes và cascading.
- [Streaming Replication Protocol](https://www.postgresql.org/docs/current/protocol-replication.html): replication protocol và WAL streaming.
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION): WAL sender/receiver, base backup và standby setup.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION): synchronous_standby_names và synchronous_commit behavior.
- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html): read-only queries, recovery conflicts và feedback.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): wal_level, wal_keep_size, max_wal_senders, slots và WAL settings.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): primary/standby replication parameters.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): tạo physical base backup và recovery configuration.
- [Replication Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-REPLICATION): pg_create_physical_replication_slot, pg_drop_replication_slot, pg_promote và LSN functions.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_replication, pg_stat_wal_receiver và replication statistics.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): đưa cluster đã diverge trở lại cùng timeline.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archive và PITR.
- [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html): start/stop/promote server.
- [Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html): pg_hba.conf, authentication methods và TLS.
