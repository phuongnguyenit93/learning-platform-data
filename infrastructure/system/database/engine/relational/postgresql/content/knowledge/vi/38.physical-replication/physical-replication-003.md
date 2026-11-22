# Tạo standby bằng base backup và cấu hình kết nối

PostgreSQL physical streaming replication tạo một máy chủ standby bằng cách sao chép trạng thái vật lý của một PostgreSQL cluster rồi liên tục nhận và replay WAL từ primary. Standby có thể phục vụ truy vấn đọc khi bật hot standby, hỗ trợ dự phòng, giảm tải read workload và làm nền tảng cho failover/disaster recovery.

Để tạo standby, cần ba phần phối hợp: **base backup nhất quán**, **kết nối replication được xác thực và mã hóa**, và **WAL stream liên tục**. Chỉ chạy pg_basebackup là chưa đủ nếu primary không cho phép replication connection, standby không biết địa chỉ primary, WAL bị giữ không đủ lâu hoặc service không thể đọc credentials.

Bài học này hướng dẫn quy trình tạo physical standby từ một primary đang chạy, cấu hình role và pg_hba.conf, chuẩn bị WAL sender/replication slots, chạy pg_basebackup, thiết lập standby.signal/primary_conninfo, khởi động standby và kiểm tra trạng thái replication. Các ví dụ tập trung PostgreSQL 12 trở lên, nơi cấu hình recovery nằm trong postgresql.conf/postgresql.auto.conf và file standby.signal; các phiên bản cũ dùng cơ chế recovery.conf khác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích physical streaming replication và vai trò của primary/standby.
2. Phân biệt base backup, WAL streaming và WAL archiving.
3. Chuẩn bị primary cho replication bằng các server settings cần thiết.
4. Tạo replication role với quyền tối thiểu.
5. Cấu hình pg_hba.conf, TLS và password file an toàn.
6. Chọn WAL method phù hợp khi chạy pg_basebackup.
7. Tạo và sử dụng physical replication slot.
8. Hiểu tác dụng của -R, -X stream, -S, -C, -P và -D.
9. Cấu hình standby connection bằng primary_conninfo và primary_slot_name.
10. Khởi động standby, xác nhận recovery mode và WAL receiver.
11. Theo dõi replication lag và xử lý lỗi kết nối/WAL.
12. Hiểu read-only queries, hot standby conflicts và failover boundaries.

> **Phiên bản:** Ví dụ chính dùng PostgreSQL 12+. Tên options và statistics views có thể khác ở các major versions. Physical replication yêu cầu các servers dùng cùng PostgreSQL major version; hãy đối chiếu tài liệu đúng version trước khi triển khai.

## 2. Primary và standby hoạt động như thế nào?

Trong physical streaming replication:

- **Primary** nhận writes từ clients, tạo WAL records và phục vụ transactions.
- **WAL sender** trên primary gửi WAL tới standby qua replication protocol.
- **WAL receiver** trên standby nhận và ghi WAL vào pg_wal.
- **Startup/recovery process** replay WAL để đưa data files của standby tiến tới trạng thái primary.
- **Hot standby** cho phép clients chạy read-only queries trong lúc standby tiếp tục replay WAL.

Sơ đồ:

```text
Application writes
       |
       v
  PostgreSQL PRIMARY
       |
       +--> WAL records --> pg_wal
       |
       +--> walsender ======================+
                                            |
                                      network/TLS
                                            |
                                            v
                                  PostgreSQL STANDBY
                                            |
                                      walreceiver
                                            |
                                         pg_wal
                                            |
                                      startup/replay
                                            |
                                      read-only queries
```

### Standby có nhận writes không?

Một physical standby đang ở recovery mode là read-only. Nó replay những thay đổi đã phát sinh trên primary; client không thể tự UPDATE/INSERT dữ liệu vào standby như một primary độc lập.

### Streaming replication không phải logical replication

Physical replication truyền WAL để tái tạo thay đổi ở cấp cluster/storage. Logical replication truyền các thay đổi logical của selected publications/tables và có thể áp dụng vào schema/database khác. Bài này tập trung physical standby.

## 3. Base backup là gì?

Base backup là bản sao vật lý nhất quán của PostgreSQL cluster tại một khoảng thời gian. Nó bao gồm data files và metadata cần thiết để server có thể bắt đầu recovery. Với physical standby, base backup là điểm xuất phát để standby replay WAL và bắt kịp primary.

Base backup có thể được tạo bằng:

- pg_basebackup.
- Backup tools như pgBackRest hoặc Barman.
- Storage snapshots được orchestration đúng cách với PostgreSQL và WAL.

### Vì sao không copy data directory bằng cp?

Trong khi primary đang chạy, data files có thể thay đổi đồng thời. Copy thư mục tùy tiện có thể thu được trạng thái không nhất quán giữa các files/pages. pg_basebackup sử dụng replication protocol và backup coordination của PostgreSQL để tạo physical backup nhất quán.

### Base backup cần WAL

Trong quá trình backup, các pages có thể được copy ở những thời điểm khác nhau. WAL cần thiết để đưa bản sao về trạng thái nhất quán. pg_basebackup có thể stream hoặc fetch WAL theo lựa chọn WAL method.

## 4. Điều kiện tương thích giữa primary và standby

Trước khi bắt đầu:

- Cùng PostgreSQL major version.
- Binary/extension compatibility phù hợp.
- Kiến trúc CPU/OS và định dạng data directory tương thích.
- Tablespaces có đường dẫn phù hợp ở standby.
- Standby có đủ disk cho base backup, WAL và tăng trưởng.
- Network cho phép standby kết nối primary.
- Có quyền replication và credentials.

### Không khởi tạo standby bằng initdb

Với physical standby được tạo từ base backup, data directory phải chứa cluster copy từ primary. Không chạy initdb lên cùng directory rồi ghi đè lẫn lộn. Hãy dùng data directory rỗng, backup destination đúng và service trỏ tới đúng đường dẫn.

### Minor versions

Physical standby thường cần cùng major release; minor releases trong cùng major được thiết kế tương thích replication. Tuy nhiên, nên giữ primary/standby ở minor release được hỗ trợ và triển khai security/bug-fix updates đồng bộ theo kế hoạch.

## 5. Kiến trúc ví dụ

Giả sử:

| Thành phần | Ví dụ |
|---|---|
| Primary host | db-primary.internal |
| Primary address | 10.20.0.10 |
| Standby host | db-standby.internal |
| Standby address | 10.20.0.20 |
| PostgreSQL port | 5432 |
| Replication role | replicator |
| Application name | standby_a |
| Physical slot | standby_a_slot |
| Data directory | /var/lib/postgresql/17/main |

Các hostname/IP là ví dụ tài liệu, thay bằng địa chỉ private/network thật của hệ thống. Không mở replication port ra public internet nếu không có kiến trúc bảo vệ phù hợp.

## 6. Kiểm tra trạng thái primary trước khi cấu hình

Kết nối vào primary bằng role quản trị phù hợp:

```sql
SELECT version();
SHOW data_directory;
SHOW port;
SHOW listen_addresses;
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
SHOW hot_standby;
```

Kiểm tra server đang là primary:

```sql
SELECT pg_is_in_recovery();
```

Kết quả false nghĩa là instance hiện không ở recovery mode. Nếu kết quả true, server đang ở recovery/standby và không thể dùng nó như primary writable trong ví dụ này.

### Xác nhận data directory

Ghi lại đường dẫn data directory và các tablespace locations. Trên standby, pg_basebackup cần destination trống và tablespaces phải có đường dẫn đích hợp lệ.

## 7. Cấu hình wal_level

Trên primary:

```sql
SHOW wal_level;
```

Physical streaming replication yêu cầu wal_level ít nhất là replica.

Trong postgresql.conf hoặc parameter group:

```ini
wal_level = replica
```

wal_level=logical cũng hỗ trợ physical replication, nhưng tạo thêm thông tin WAL phục vụ logical decoding. Chọn mức thấp nhất đáp ứng toàn bộ kiến trúc replication/CDC.

### Restart requirement

wal_level là setting cần restart server để có hiệu lực. Sau thay đổi, xác nhận bằng SHOW wal_level; trước khi chạy base backup.

## 8. Cấu hình WAL senders

Primary cần đủ WAL sender processes cho:

- Physical standbys.
- Logical replication connections.
- pg_basebackup đang chạy.
- Các công cụ backup/replication khác có dùng replication protocol.

Ví dụ:

```ini
max_wal_senders = 10
```

Đây là giá trị minh họa. Tính số connections đồng thời và để headroom cho backup/reconnect/failover. Nếu hết WAL sender slots, standby hoặc base backup có thể không kết nối được.

max_wal_senders là setting cần restart. Kiểm tra giá trị thực tế:

```sql
SHOW max_wal_senders;
```

## 9. Cấu hình replication slots capacity

Nếu dùng physical replication slots:

```ini
max_replication_slots = 10
```

Setting này quyết định số replication slots tối đa. Đặt đủ cho physical/logical slots và các backup workflows cần slot.

```sql
SHOW max_replication_slots;

SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_catalog.pg_replication_slots;
```

max_replication_slots cần restart khi thay đổi. Không tạo nhiều slots không có owner; slot inactive có thể giữ WAL và làm pg_wal tăng.

## 10. Cấu hình wal_keep_size và archive

wal_keep_size yêu cầu primary giữ lại một lượng WAL tối thiểu để standby có thời gian reconnect trong một số tình huống:

```ini
wal_keep_size = 2GB
```

Đây là ví dụ, không phải bảo đảm retention theo thời gian. WAL rate càng cao thì cùng một dung lượng tương ứng khoảng thời gian ngắn hơn.

Nếu cần standby bắt kịp sau outage dài hơn, dùng physical replication slot hoặc WAL archive phù hợp. Archive có thể cung cấp WAL khi standby cần segment không còn trong local pg_wal.

### Phân biệt

- wal_keep_size: giữ lượng WAL tối thiểu theo size.
- Physical replication slot: giữ WAL cần thiết theo restart_lsn.
- WAL archive: lưu WAL segments ở archive destination để phục hồi/standby lấy lại.

Các cơ chế này bổ sung cho nhau theo recovery design; không nên coi chúng là thay thế hoàn toàn.

## 11. Cấu hình listen_addresses và firewall

Primary phải lắng nghe trên interface mà standby có thể kết nối:

```ini
listen_addresses = '10.20.0.10'
port = 5432
```

Có thể dùng hostname/interface hoặc * theo network policy; tránh mở tất cả interfaces nếu không cần.

Firewall/security group chỉ cho phép standby host/network kết nối TCP 5432 tới primary. Cũng cần bảo đảm route, DNS, NAT và network ACL cho chiều phản hồi.

### Kiểm tra từ standby

Trên standby host, kiểm tra DNS và TCP reachability bằng công cụ hệ điều hành phù hợp. Một kết nối TCP thành công chưa chứng minh pg_hba/authentication/TLS đúng; bước pg_basebackup sẽ xác nhận toàn bộ PostgreSQL connection path.

## 12. Tạo replication role

Trên primary:

```sql
CREATE ROLE replicator
WITH LOGIN REPLICATION;
```

Đặt password bằng quy trình secret management phù hợp. Ví dụ đặt mật khẩu tương tác qua \password trong psql:

```sql
\password replicator
```

Không ghi password thật vào source code, ticket, command history hoặc tài liệu. Role physical replication cần LOGIN và REPLICATION; không cần SUPERUSER chỉ để streaming replication/pg_basebackup hoạt động.

### Quyền của role

Role REPLICATION có quyền kết nối replication protocol và tạo slot trong giới hạn cấu hình/quyền. Đây là quyền nhạy cảm; chỉ cho phép từ standby/backup hosts và giám sát việc sử dụng.

## 13. Cấu hình pg_hba.conf

Thêm rule trên primary cho standby address:

```text
# TYPE     DATABASE      USER         ADDRESS          METHOD
hostssl    replication   replicator   10.20.0.20/32    scram-sha-256
```

Token database replication trong pg_hba.conf dành cho replication connections. Dùng hostssl để chỉ chấp nhận kết nối TLS.

### Thứ tự rules

PostgreSQL dùng rule đầu tiên match. Nếu có một rule rộng hơn ở phía trên, rule hẹp có thể không được dùng. Kiểm tra file theo thứ tự và tránh vô tình mở replication access cho CIDR rộng.

### Reload cấu hình

Sau khi sửa:

```sql
SELECT pg_reload_conf();
```

Hoặc reload bằng pg_ctl reload/service manager theo cách vận hành. pg_hba.conf thay đổi thường chỉ cần reload, không cần restart. Kiểm tra logs nếu rule có syntax error.

## 14. Xác minh pg_hba.conf

Có thể xem cấu hình đã parse:

```sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_catalog.pg_hba_file_rules
ORDER BY line_number;
```

Nếu cột error không NULL, xử lý syntax/config issue trước khi chạy base backup.

### Kết nối bị từ chối

Log primary thường cho biết không có pg_hba.conf entry phù hợp hoặc authentication failed. Đừng phản ứng bằng cách đổi sang trust trong production. Kiểm tra source IP thực tế, database token replication, username, TLS mode và rule order.

## 15. TLS cho replication connection

Nếu dùng hostssl, primary cần SSL được bật và certificate/key hợp lệ:

```ini
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
```

Standby nên xác minh certificate chain và hostname, ví dụ connection string:

```text
host=db-primary.internal
port=5432
user=replicator
application_name=standby_a
sslmode=verify-full
sslrootcert=/etc/postgresql/certs/ca.crt
```

### Certificate requirements

- Primary certificate phải hợp lệ cho hostname được dùng.
- Standby trust store chứa CA phù hợp.
- Private key được bảo vệ bằng filesystem permissions.
- Certificate expiry/rotation phải được giám sát.
- Không dùng sslmode=disable nếu policy yêu cầu TLS.

## 16. Password file và credentials

Trên Linux/Unix, libpq có thể dùng .pgpass hoặc file được chỉ định bởi passfile. Một dòng có dạng:

```text
hostname:port:database:username:password
```

Với replication connection, database field dùng replication.

Ví dụ minh họa:

```text
db-primary.internal:5432:replication:replicator:REPLACE_WITH_SECRET
```

Đặt file trong home của service account hoặc đường dẫn riêng; giới hạn quyền đọc/ghi, thường là 0600 trên Unix. Nếu permissions quá rộng, libpq có thể từ chối dùng file.

### Escaping

Trong passfile, dấu : và \ trong field cần được escape theo quy tắc libpq. Không đặt secret chứa ký tự đặc biệt mà không xử lý đúng.

### Windows

Trên Windows, dùng file passfile với ACL chỉ cho service account và administrator cần thiết. Không áp dụng chmod trên Windows; dùng NTFS permissions.

## 17. Chọn replication slot hay không?

Physical replication slot giúp primary giữ WAL cần thiết cho standby ngay cả khi standby tạm ngắt kết nối.

### Ưu điểm

- Giảm nguy cơ standby mất WAL segment do primary recycle quá sớm.
- Standby có thể reconnect sau outage và tiếp tục nếu slot còn giữ đủ WAL.
- Không cần ước lượng retention chỉ bằng wal_keep_size.

### Rủi ro

- Slot inactive có thể giữ WAL vô thời hạn nếu không có giới hạn.
- Disk pg_wal có thể đầy khi standby chết hoặc lag lâu.
- Slot cần monitoring và owner rõ ràng.

Trên các version hỗ trợ, max_slot_wal_keep_size có thể giới hạn lượng WAL giữ bởi slot. Nếu vượt giới hạn, slot có thể bị invalidated và standby phải reinitialize/reseed.

## 18. Tạo physical replication slot

Có thể tạo trước trên primary:

```sql
SELECT *
FROM pg_catalog.pg_create_physical_replication_slot(
    'standby_a_slot'
);
```

Hoặc để pg_basebackup tạo slot bằng -C -S như ví dụ bên dưới.

Kiểm tra:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots
WHERE slot_name = 'standby_a_slot';
```

Các cột wal_status/safe_wal_size có ở các major versions mới hơn; nếu server cũ không có, truy vấn chỉ các columns được hỗ trợ.

### Slot đã tồn tại

Không tạo lại cùng tên slot. Kiểm tra slot thuộc standby nào, có đang active hay không và có cần giữ không. Tránh xóa slot đang được standby/consumer sử dụng.

## 19. Chuẩn bị standby host

Trên standby:

1. Cài PostgreSQL cùng major version với primary.
2. Cài các extensions/libraries cần thiết nếu physical files phụ thuộc.
3. Tạo filesystem/data volume đủ dung lượng.
4. Tạo service account PostgreSQL.
5. Xác định data directory chính xác.
6. Mở network tới primary port.
7. Chuẩn bị CA certificate và passfile.
8. Dừng PostgreSQL service nếu package đã tự tạo cluster rỗng.
9. Di chuyển/xóa cluster rỗng theo quy trình được kiểm soát; destination của base backup phải trống.

### Kiểm tra destination

pg_basebackup -D yêu cầu directory đích không chứa dữ liệu không liên quan. Đừng ghi base backup vào data directory đang được một PostgreSQL instance sử dụng.

### Ownership

Data directory và staging paths phải thuộc service account phù hợp. Sai owner/permissions có thể khiến PostgreSQL không start hoặc để lộ data files.

## 20. Cú pháp pg_basebackup cơ bản

Ví dụ:

```sh
pg_basebackup \
  -h db-primary.internal \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/17/main \
  -Fp \
  -X stream \
  -P \
  -R
```

Giải thích:

| Option | Ý nghĩa |
|---|---|
| -h | Hostname/address của primary |
| -p | Port PostgreSQL |
| -U | Replication role |
| -D | Destination directory |
| -Fp | Plain directory format |
| -X stream | Stream WAL trong lúc base backup chạy |
| -P | Hiển thị progress |
| -R | Tạo standby.signal và ghi recovery connection settings |

Lệnh chạy từ standby/backup host, dùng binary pg_basebackup tương thích với cluster. Có thể dùng -v để verbose output.

## 21. -X stream, -X fetch và -X none

-X stream mở replication connection riêng để stream WAL đồng thời với base backup. Đây là lựa chọn phổ biến khi tạo standby vì WAL cần thiết được lấy trong lúc backup.

-X fetch lấy các WAL segments cần thiết vào cuối backup. Phương thức này cần primary giữ đủ WAL cho toàn bộ thời gian backup; nếu segment cần thiết đã bị recycle trước khi fetch, backup có thể thất bại.

-X none không lấy WAL theo cách này; caller/tool phải đảm bảo WAL cần thiết được cung cấp bằng cơ chế khác.

### Chọn method

- Dùng stream khi cần một lệnh base backup tự lấy WAL liên tục.
- Dùng fetch khi retention và workload bảo đảm WAL cần thiết còn tồn tại đến cuối backup.
- Dùng none chỉ khi có một backup/WAL orchestration đã được thiết kế rõ.

-X stream thường dùng hai replication connections trong thời gian chạy: một cho base backup và một cho WAL streaming. Cần đủ max_wal_senders.

## 22. -R tạo standby configuration

Với PostgreSQL 12+, -R/--write-recovery-conf:

- Tạo file standby.signal trong data directory.
- Ghi connection settings vào postgresql.auto.conf.
- Nếu chỉ định slot bằng -S, ghi primary_slot_name phù hợp.

Khi server start và thấy standby.signal, PostgreSQL vào standby mode và kết nối primary theo primary_conninfo/recovery settings.

### Vì sao dùng -R?

Nó giảm lỗi cấu hình thủ công và đảm bảo data directory sau base backup có tín hiệu khởi động ở standby mode. Tuy nhiên, vẫn phải kiểm tra connection string, password file, TLS và slot.

### PostgreSQL 11 trở xuống

Các version cũ dùng recovery.conf với standby_mode và các recovery parameters. Không dùng hướng dẫn standby.signal cho version cũ; đọc tài liệu version tương ứng.

## 23. Tạo slot ngay trong pg_basebackup

Nếu muốn base backup và standby cùng dùng slot:

```sh
pg_basebackup \
  -h db-primary.internal \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/17/main \
  -Fp \
  -X stream \
  -P \
  -R \
  -C \
  -S standby_a_slot
```

- -C yêu cầu tạo replication slot trước khi bắt đầu backup.
- -S đặt tên slot.
- -R ghi primary_slot_name vào recovery config để standby tiếp tục dùng slot đó sau khi start.

### Lưu ý

Nếu slot đã tồn tại, -C sẽ báo lỗi. Khi slot đã được tạo trước, dùng -S standby_a_slot mà không thêm -C.

Nếu lệnh thất bại giữa chừng, kiểm tra slot có được tạo nhưng không còn consumer không. Slot orphan có thể giữ WAL; cleanup theo owner/incident procedure.

## 24. Tablespaces và đường dẫn đích

Physical base backup có thể bao gồm tablespaces ở đường dẫn ngoài data directory. Nếu standby dùng đường dẫn khác, sử dụng --tablespace-mapping/-T:

```sh
pg_basebackup \
  -h db-primary.internal \
  -U replicator \
  -D /var/lib/postgresql/17/main \
  -X stream \
  -R \
  -T /primary/fast_ts=/standby/fast_ts
```

Mapping phải khớp source tablespace path chính xác và destination path đã chuẩn bị. Có thể cần mapping cho nhiều tablespaces.

### Không để tablespace đè dữ liệu

Kiểm tra destination path trống và mount đúng volume. Mapping sai có thể làm backup thất bại hoặc ghi vào filesystem không mong muốn.

## 25. Chọn format và compression

pg_basebackup hỗ trợ plain format (-Fp) và tar format (-Ft) trong các phiên bản tương ứng. Plain format tạo directory structure trực tiếp, thường thuận tiện để khởi động standby sau backup. Tar format cần giải nén/khôi phục trước khi server sử dụng.

Một số versions hỗ trợ nén output bằng -Z với các compression methods/levels nhất định. Compression giảm network/storage bytes nhưng dùng CPU và cần tương thích với cách restore.

### Chọn theo môi trường

- Dùng plain format cho destination data directory trực tiếp.
- Dùng tar format khi pipeline lưu artifact rồi giải nén ở bước restore.
- Đo CPU, network throughput, backup duration và restore duration.
- Không giả định options compression giống nhau giữa các major versions.

## 26. Chạy pg_basebackup an toàn

Trước khi chạy:

- Xác nhận primary role và settings.
- Xác nhận pg_hba rule đã reload.
- Xác nhận TCP/TLS và authentication.
- Xác nhận slot name/ownership.
- Xác nhận destination rỗng và đủ disk.
- Xác nhận max_wal_senders đủ connections.
- Xác nhận password file/secret path.
- Xác nhận tablespace mapping.

Trong khi chạy:

- Theo dõi progress.
- Theo dõi primary WAL generation và sender activity.
- Theo dõi disk/network throughput.
- Tránh xóa/di chuyển destination.
- Không kill process chỉ vì progress tạm thời đứng ở một phase.

Sau khi chạy:

- Xác nhận exit code thành công.
- Xác nhận data directory có standby.signal.
- Kiểm tra postgresql.auto.conf có primary_conninfo/slot.
- Kiểm tra manifest/backup validation nếu tool/version hỗ trợ.
- Bảo đảm credentials được đọc bởi service account.

## 27. Kiểm tra recovery configuration sau -R

Trên standby host, trước khi start PostgreSQL:

```sh
cat /var/lib/postgresql/17/main/postgresql.auto.conf
ls -l /var/lib/postgresql/17/main/standby.signal
```

Đây là lệnh minh họa trên Linux; dùng công cụ tương đương trên OS khác. File standby.signal thường là file rỗng, sự tồn tại của nó báo PostgreSQL khởi động ở standby mode.

Trong postgresql.auto.conf, kiểm tra:

- primary_conninfo có đúng host/port/user/application_name?
- sslmode/sslrootcert có đúng theo TLS policy?
- primary_slot_name có đúng slot name nếu dùng slot?
- Không có password plaintext bị ghi vào file.

### Tránh chỉnh cùng setting ở nhiều nơi

postgresql.auto.conf được ALTER SYSTEM/pg_basebackup -R dùng để lưu settings. Nếu postgresql.conf cũng định nghĩa primary_conninfo, cần hiểu precedence: postgresql.auto.conf được đọc sau postgresql.conf và có thể override. Giữ một nguồn cấu hình rõ ràng.

## 28. Cấu hình primary_conninfo

Nếu cần cấu hình thủ công hoặc hoàn thiện connection string do -R tạo, ví dụ:

```ini
primary_conninfo = 'host=db-primary.internal port=5432 user=replicator application_name=standby_a sslmode=verify-full sslrootcert=/etc/postgresql/certs/ca.crt passfile=/var/lib/postgresql/.pgpass'
```

Connection string dùng libpq parameters. `application_name` giúp nhận diện standby trong pg_stat_replication.

### Không nhúng password

Không đặt password trực tiếp trong primary_conninfo nếu có thể tránh. Dùng passfile được bảo vệ bởi filesystem ACL/permissions và service account.

### primary_conninfo không phải app connection string

Đây là kết nối nội bộ từ standby tới primary để nhận WAL. Nó cần user replication, host/port, TLS/authentication và application_name phù hợp.

## 29. Cấu hình primary_slot_name

Nếu standby dùng physical replication slot:

```ini
primary_slot_name = 'standby_a_slot'
```

Tên phải khớp slot tồn tại trên primary. Nếu slot không tồn tại hoặc đã bị invalidated, WAL receiver có thể không kết nối/tiếp tục được.

Khi dùng pg_basebackup với -R -S standby_a_slot, setting này thường được ghi tự động. Kiểm tra file config và primary pg_replication_slots sau khi standby start.

### Không dùng chung một slot cho nhiều standbys

Mỗi standby nên có slot riêng để primary theo dõi WAL retention độc lập. Dùng chung slot làm consumer progress/ownership khó xác định và không phù hợp cho nhiều physical standbys độc lập.

## 30. Standby signal và hot_standby

PostgreSQL 12+ dùng file standby.signal để chỉ định server phải tiếp tục ở standby mode:

```text
PGDATA/
  postgresql.conf
  postgresql.auto.conf
  standby.signal
  base/
  global/
  pg_wal/
  ...
```

Setting:

```sql
SHOW hot_standby;
```

hot_standby=on cho phép read-only queries trong recovery khi server đã đạt trạng thái phù hợp. Đây là setting trên standby; thay đổi cần restart theo context của setting.

### Nếu thiếu standby.signal

Một data directory có base backup nhưng không có standby.signal có thể không tiếp tục chạy như standby theo cấu hình mong muốn. Với PostgreSQL 12+, kiểm tra file này và recovery configuration trước khi start.

## 31. Khởi động standby

Đảm bảo service đang dừng và data directory là bản base backup vừa tạo. Khởi động bằng service manager hoặc pg_ctl phù hợp với cách cài đặt.

Ví dụ:

```sh
pg_ctl -D /var/lib/postgresql/17/main -l /var/log/postgresql/standby.log start
```

Nếu dùng systemd/package-managed cluster, dùng service unit/cluster manager tương ứng thay vì chạy pg_ctl tạo một instance thứ hai trên cùng data directory.

### Theo dõi log startup

Tìm các thông điệp:

- entering standby mode/recovery.
- started streaming WAL from primary.
- consistent recovery state reached.
- database system is ready to accept read-only connections.

Wording thay đổi theo version. Nếu server không start, đọc log đầu tiên có ERROR/FATAL; không xóa files trong pg_wal để thử khởi động lại.

## 32. Xác nhận standby đang ở recovery mode

Kết nối trực tiếp tới standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    current_setting('server_version') AS version,
    inet_server_addr() AS server_address;
```

Kết quả mong đợi:

- is_standby = true.
- Server version tương thích primary.
- Kết nối tới đúng standby host/port.

### Kiểm tra read-only behavior

Thử một SELECT vào bảng cần thiết. Một lệnh INSERT/UPDATE trên hot standby sẽ bị từ chối vì standby đang recovery/read-only.

## 33. Kiểm tra WAL receiver trên standby

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
FROM pg_catalog.pg_stat_wal_receiver;
```

View có một row khi WAL receiver đang chạy; không có row có thể nghĩa là chưa kết nối, đang reconnect, server không ở standby hoặc receiver đã dừng.

### Diễn giải

- status thường là streaming khi đang nhận WAL.
- written_lsn và flushed_lsn thể hiện vị trí nhận/ghi.
- latest_end_lsn là WAL end position gần nhất được báo.
- last_msg_receipt_time giúp nhận biết lần nhận message gần nhất.
- slot_name cho biết slot đang dùng nếu có.

Các columns có thể khác giữa versions; dùng SELECT * hoặc information_schema để khám phá schema trên major version thực tế.

## 34. Kiểm tra WAL sender trên primary

Trên primary:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

Khi standby kết nối thành công, thường có row với application_name standby_a và client_addr là standby host.

### Các trạng thái

- startup/catchup/streaming có thể xuất hiện tùy replication state/version.
- streaming cho thấy WAL sender đang gửi WAL liên tục.
- sync_state phản ánh synchronous replication status nếu có cấu hình; async standbys thường có trạng thái async.

Nếu không có row, kiểm tra standby log, pg_hba, authentication, network và slot.

## 35. Đo receive lag và replay lag

Trên standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_last_wal_receive_lsn(),
            pg_last_wal_replay_lsn()
        )::bigint
    ) AS receive_replay_bytes;
```

Khoảng cách receive-to-replay cho biết WAL đã nhận nhưng chưa replay, theo LSN address distance.

Trên primary, có thể so current WAL LSN với standby replay_lsn từ pg_stat_replication:

```sql
SELECT
    application_name,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            replay_lsn
        )::bigint
    ) AS primary_to_replay_bytes
FROM pg_catalog.pg_stat_replication;
```

### Timestamp lag caveat

pg_last_xact_replay_timestamp() cho thời điểm transaction gần nhất được replay. Nếu primary không có writes, timestamp có thể cũ dù standby đang bắt kịp hoàn toàn. Dùng LSN distance và message timestamps cùng workload context; không alert chỉ dựa trên timestamp khi database idle.

## 36. Kiểm tra slot đang active và WAL retention

Trên primary:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
WHERE slot_name = 'standby_a_slot';
```

Với physical slot, confirmed_flush_lsn có thể NULL/không mang ý nghĩa như logical slot. Theo dõi restart_lsn và active state.

### Slot active nhưng standby lag?

Active chỉ nói có consumer đang dùng slot. Nó không chứng minh standby đã replay tới current LSN. So sent/write/flush/replay positions và standby receiver/replay state.

## 37. Standby read-only queries và hot standby conflicts

Khi hot_standby bật, standby có thể phục vụ SELECT. Tuy nhiên WAL replay có thể xung đột với query đang đọc dữ liệu mà primary đã thay đổi/vacuum.

Các conflict có thể liên quan:

- Access Exclusive locks từ primary.
- Cleanup records do VACUUM trên primary.
- Snapshot quá cũ trên standby.
- Buffer pin hoặc tablespace/database removal.

Kiểm tra:

```sql
SELECT *
FROM pg_catalog.pg_stat_database_conflicts
WHERE datname = current_database();
```

### max_standby_streaming_delay

Setting này giới hạn thời gian standby trì hoãn WAL replay để chờ query conflict. Tăng delay có thể giảm query cancellations nhưng làm replay lag lớn hơn và WAL retention pressure tăng.

### hot_standby_feedback

Bật feedback có thể giúp primary giữ tuple versions để giảm cleanup conflicts trên standby, nhưng có thể làm dead tuples/bloat tăng trên primary. Chỉ bật khi hiểu trade-off và có monitoring.

## 38. Synchronous và asynchronous standby

Physical streaming replication mặc định thường là asynchronous: primary không cần chờ standby replay để xác nhận commit.

Synchronous replication cần cấu hình thêm ở primary, ví dụ:

```ini
synchronous_standby_names = 'FIRST 1 (standby_a)'
```

application_name trong primary_conninfo phải khớp tên được cấu hình. Commit behavior còn phụ thuộc synchronous_commit và sync state.

### Trade-off

- Async: primary có thể ACK commit trước khi standby nhận/flush WAL; có nguy cơ mất một lượng transactions nếu primary mất đột ngột trước khi standby nhận.
- Sync: có thể giảm nguy cơ mất dữ liệu theo mức acknowledgment được chọn, nhưng commit latency phụ thuộc standby/network.

Đừng bật synchronous replication chỉ bằng cách đặt synchronous_standby_names mà không xác định policy RPO, timeout, quorum và behavior khi standby down.

## 39. Streaming replication và WAL archive phối hợp

Standby có thể dùng restore_command để lấy WAL từ archive khi segment không có sẵn trong streaming source/primary. Một standby configuration có thể phối hợp:

- primary_conninfo để stream WAL.
- primary_slot_name để giữ WAL trên primary.
- restore_command để lấy archived WAL.

### Thứ tự và mục đích

Recovery process có thể tìm WAL từ archive và streaming theo cơ chế/version. Cấu hình cụ thể cần đảm bảo archive path đúng và WAL timeline phù hợp. Không thiết lập restore_command trỏ vào repository không có quyền hoặc không verify được segment.

### Khi nào archive hữu ích?

- Standby ngắt kết nối lâu hơn local WAL retention.
- Cần disaster recovery từ backup repository.
- Muốn tách WAL retention khỏi primary local storage.

Archive không thay monitoring replication slot hoặc backup chain.

## 40. Kiểm tra backup bằng pg_verifybackup

Các PostgreSQL versions có hỗ trợ pg_verifybackup có thể xác minh backup manifest và file checksums:

```sh
pg_verifybackup /var/lib/postgresql/17/main
```

Đây là lệnh kiểm tra offline trên backup directory, không thay thế việc start standby và xác minh streaming. Khả năng/option phụ thuộc version và backup format.

### Giới hạn

- Không chứng minh network connection vẫn hoạt động.
- Không chứng minh WAL archive/streaming liên tục sau thời điểm backup.
- Không thay restore drill.
- Không thay business-level data validation.

## 41. Nhiều standbys

Một primary có thể phục vụ nhiều physical standbys. Mỗi standby nên có:

- application_name riêng.
- replication slot riêng nếu dùng slots.
- replication identity/connection policy rõ ràng.
- network path và capacity.
- monitoring riêng cho receive/replay lag.

### Capacity planning

Tính tổng số WAL sender connections, network egress, disk retention của slots và write load do archiving/backup. Một standby lag lâu có thể giữ WAL nhiều hơn các standbys còn lại.

### Cascading replication

Standby có thể làm upstream cho standby khác nếu cấu hình phù hợp. Điều này giảm connections/egress từ primary nhưng thêm một failure/lag hop; cần theo dõi chain và đảm bảo WAL đủ trên upstream standby.

## 42. Restart và reconnect behavior

Khi standby restart:

1. Đọc standby.signal.
2. Load primary_conninfo/primary_slot_name.
3. Khởi tạo recovery.
4. Kết nối primary hoặc lấy WAL từ archive.
5. Replay WAL đến vị trí mới nhất có thể.
6. Tiếp tục streaming.

Nếu primary đã recycle WAL cần thiết và không có slot/archive giữ segment đó, standby có thể không bắt kịp. Khi đó phải tạo lại standby bằng base backup mới hoặc quy trình reseed được hỗ trợ.

### Không xóa pg_wal trên standby

Không xóa files trong pg_wal thủ công để “reset replication”. Điều đó có thể làm recovery không thể tiếp tục. Dùng stop/reseed procedure chuẩn.

## 43. Failover và promotion

Tạo standby không tự tạo một hệ thống HA hoàn chỉnh. Promotion là thao tác chuyển standby thành primary mới.

Trong một quy trình failover được kiểm soát, có thể dùng:

```sql
SELECT pg_promote();
```

Hoặc:

```sh
pg_ctl -D /path/to/standby promote
```

### Chống split brain

Trước khi promote, phải chắc chắn primary cũ đã được fence/đảm bảo không còn nhận writes. Nếu hai nodes cùng writable, có thể tạo hai lịch sử dữ liệu phân kỳ và gây mất dữ liệu nghiêm trọng.

### Sau promotion

- Standby mới trở thành primary và tạo timeline mới.
- Cập nhật routing/service discovery.
- Reconfigure các standbys còn lại để follow primary mới.
- Đánh giá old primary có thể rewind/rejoin hay cần reseed.
- Cập nhật backup/archive configuration.

Failover orchestration thường cần Patroni/repmgr/managed-service control plane hoặc runbook riêng; pg_basebackup chỉ tạo replica ban đầu.

## 44. Rebuild standby khi mất WAL

Nếu log báo standby cần WAL segment đã bị removed/recycled:

1. Xác định LSN/WAL segment bị thiếu.
2. Kiểm tra archive có segment đó không.
3. Kiểm tra physical slot và restart_lsn.
4. Xác định standby có thể lấy lại WAL từ archive hay không.
5. Nếu không thể nối tiếp, lập kế hoạch reseed.
6. Dừng standby theo service procedure.
7. Tạo base backup mới vào destination trống.
8. Xác nhận slot/credentials/connection settings.
9. Start và kiểm tra streaming/replay.

Không cố tạo file WAL giả hoặc thay segment bằng file khác cùng tên.

## 45. Troubleshooting: connection refused

Nguyên nhân có thể:

- PostgreSQL primary không chạy.
- listen_addresses không chứa interface cần thiết.
- Port sai.
- Firewall/security group chặn.
- DNS trỏ sai IP.
- Primary chỉ lắng nghe localhost.

Kiểm tra theo lớp:

1. DNS resolve.
2. TCP reachability.
3. PostgreSQL listening socket.
4. Network/firewall rules.
5. Server logs.

Connection refused khác với authentication failure; xử lý network trước khi sửa credentials.

## 46. Troubleshooting: no pg_hba.conf entry

Thông báo thường cho biết client address, user và database/replication request. Kiểm tra:

- Source IP thực tế của standby.
- Rule dùng database token replication.
- Username đúng.
- Rule là hostssl nếu yêu cầu TLS.
- Rule order không bị match bởi rule khác.
- pg_hba.conf đã reload.

Không thêm rule 0.0.0.0/0 trust để khắc phục nhanh. Giới hạn đúng standby IP/CIDR và authentication method.

## 47. Troubleshooting: password authentication failed

Kiểm tra:

- Password được set cho đúng role.
- User có LOGIN và REPLICATION.
- Passfile match host/port/database/user.
- Passfile escaping đúng.
- Service account đọc được passfile.
- Không có password cũ trong process/service environment.
- Authentication method của pg_hba khớp credential.

Nếu đổi password, cập nhật passfile/secret store ở standby rồi reload/restart connection theo quy trình; không ghi secret vào log.

## 48. Troubleshooting: requested WAL segment has already been removed

Standby cần một WAL segment mà primary không còn giữ. Kiểm tra:

- Slot có được dùng và còn tồn tại?
- Slot có bị invalidated do max_slot_wal_keep_size?
- Standby đã ngắt kết nối bao lâu?
- wal_keep_size có phù hợp WAL generation rate?
- Archive có WAL segment cần thiết?
- restore_command có hoạt động?

Nếu archive không có segment, cần reseed standby từ base backup mới. Tăng wal_keep_size sau khi segment đã mất không thể tái tạo segment đó.

## 49. Troubleshooting: too many WAL senders

Nếu primary không còn WAL sender slots:

- Đếm standbys, logical subscribers và backup jobs.
- Kiểm tra pg_stat_replication và pg_stat_activity.
- Xác định connection bị treo/orphan.
- Tăng max_wal_senders có kế hoạch nếu capacity phù hợp.
- Restart primary nếu setting yêu cầu.

Không terminate WAL sender đang phục vụ standby khỏe mạnh mà chưa hiểu tác động. Đảm bảo max_wal_senders có headroom cho pg_basebackup -X stream vì nó có thể dùng nhiều hơn một replication connection.

## 50. Troubleshooting: replication slot inactive giữ disk

Kiểm tra:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS retained_distance
FROM pg_catalog.pg_replication_slots
WHERE restart_lsn IS NOT NULL;
```

Xác định slot owner trước khi drop. Nếu standby đã mất, cần quyết định reattach hay reseed. Slot không có owner có thể được cleanup sau approval; slot còn cần có thể phải giữ WAL.

## 51. Troubleshooting: standby start như primary

Nếu standby nhận writes hoặc pg_is_in_recovery() trả false:

- Xác nhận service trỏ đúng PGDATA.
- Kiểm tra standby.signal tồn tại trong data directory thực tế.
- Kiểm tra startup logs.
- Kiểm tra không dùng nhầm một cluster initdb khác.
- Kiểm tra service unit/environment override PGDATA.

Không tạo standby.signal trong một data directory khác rồi nghĩ service đã dùng nó.

## 52. Troubleshooting: base backup destination not empty

pg_basebackup yêu cầu destination trống theo format. Nếu directory có cluster mặc định:

1. Dừng đúng PostgreSQL service.
2. Xác nhận path service đang dùng.
3. Backup/di chuyển dữ liệu cũ nếu cần.
4. Xác nhận destination mới trống.
5. Kiểm tra mount/owner/permissions.
6. Chạy lại base backup.

Không xóa data directory trước khi xác nhận đúng host/path và có bản sao nếu dữ liệu cũ còn quan trọng.

## 53. Troubleshooting: tablespace mapping failure

Nếu backup báo lỗi tablespace:

- Lấy source paths từ pg_tablespace/pg_tablespace_location.
- Xác nhận destination mount tồn tại.
- Dùng mapping chính xác với source path.
- Đảm bảo destination đủ disk và quyền.
- Kiểm tra symlinks/ownership.

Đừng mapping nhiều tablespaces vào cùng destination nếu tool/cluster yêu cầu paths riêng.

## 54. Bảo mật replication connection

Checklist:

- Replication role riêng, không dùng postgres superuser.
- Password được quản lý bởi secret manager/passfile.
- TLS với certificate validation.
- pg_hba chỉ cho standby IP/CIDR.
- Firewall chỉ mở port cần thiết.
- Service account riêng và file permissions chặt.
- Application_name rõ ràng để audit/monitor.
- Slot ownership/retention có alert.
- Audit role changes, pg_hba edits và replication connections.

Physical replication truyền dữ liệu ở cấp cluster; quyền replication là quyền nhạy cảm và cần bảo vệ tương ứng.

## 55. Standby và backups

Standby không thay thế backup. Lỗi logic, DELETE nhầm, corruption được replay hoặc ransomware có thể lan tới standby qua WAL.

Vẫn cần:

- Base backups định kỳ.
- WAL archiving cho PITR.
- Offsite/immutable copies.
- Restore tests.
- Encryption/access control.

Standby giúp availability/failover; backup giúp recovery tới thời điểm trước lỗi hoặc dựng lại cluster. Hai cơ chế bổ sung cho nhau.

## 56. Quy trình tổng hợp tạo standby

### Trên primary

1. Kiểm tra version, role và data directory.
2. Set wal_level=replica.
3. Set max_wal_senders và max_replication_slots đủ capacity.
4. Cấu hình wal_keep_size/archive/slot policy.
5. Cấu hình listen_addresses và firewall.
6. Tạo replication role.
7. Thêm hostssl replication rule vào pg_hba.conf.
8. Reload pg_hba và xác nhận rule parse.
9. Chuẩn bị slot hoặc quyết định dùng -C -S.

### Trên standby

10. Cài cùng major version và chuẩn bị data directory trống.
11. Cấu hình TLS trust và passfile.
12. Chạy pg_basebackup với -X stream, -R, progress và slot options phù hợp.
13. Xác nhận standby.signal và postgresql.auto.conf.
14. Xác nhận primary_conninfo/primary_slot_name và không có password plaintext.
15. Start PostgreSQL.
16. Xác nhận pg_is_in_recovery() = true.
17. Kiểm tra pg_stat_wal_receiver trên standby.
18. Kiểm tra pg_stat_replication và slot active trên primary.
19. Đo receive/replay lag.
20. Kiểm tra read-only query và hot standby behavior.

### Sau khi triển khai

21. Đặt monitoring/alerts.
22. Kiểm tra archive/slot retention và disk headroom.
23. Thử restart standby và xác nhận reconnect.
24. Tài liệu hóa failover/fencing/reseed procedure.
25. Kiểm thử restore độc lập.

## 57. Bài tập thực hành

### Bài 1 — Primary và standby

Giải thích vai trò của primary, walsender, walreceiver và startup/recovery process trong physical streaming replication.

### Bài 2 — Base backup

Vì sao không thể dùng cp đơn giản để copy data directory đang chạy? pg_basebackup đảm bảo consistency như thế nào ở mức khái niệm?

### Bài 3 — Version compatibility

Một primary chạy PostgreSQL 16 và standby chạy PostgreSQL 17. Vì sao không nên dùng physical base backup để tạo standby như vậy?

### Bài 4 — wal_level

Giải thích vì sao physical replication cần wal_level=replica tối thiểu. Setting này có cần restart không?

### Bài 5 — WAL senders

Primary có 3 physical standbys, 2 logical replication clients và một pg_basebackup đang chạy với -X stream. Hãy ước lượng capacity max_wal_senders cần có và headroom nên tính.

### Bài 6 — Replication slots

Giải thích max_replication_slots và rủi ro khi tạo slot không có owner.

### Bài 7 — wal_keep_size

Một primary tạo 100 MB WAL/phút. wal_keep_size=1GB tương ứng khoảng bao lâu theo ước lượng thô? Vì sao không phải retention time guarantee?

### Bài 8 — Replication role

Tạo role LOGIN REPLICATION tên replicator. Vì sao không cấp SUPERUSER cho physical streaming replication?

### Bài 9 — pg_hba.conf

Viết rule hostssl replication cho standby IP 10.20.0.20/32, user replicator và SCRAM. Giải thích database token replication.

### Bài 10 — Rule order

Một rule host rộng nằm trước rule hostssl cụ thể. Giải thích first-match behavior và cách xác minh qua pg_hba_file_rules.

### Bài 11 — TLS

Thiết kế primary_conninfo dùng sslmode=verify-full và CA certificate. Vì sao sslmode=require chưa tương đương hostname verification?

### Bài 12 — Password file

Giải thích format .pgpass và permissions cần thiết trên Unix. Nếu file không match database=replication thì chuyện gì xảy ra?

### Bài 13 — pg_basebackup options

Giải thích -h, -p, -U, -D, -Fp, -X stream, -P và -R trong một lệnh tạo standby.

### Bài 14 — WAL methods

So sánh -X stream, -X fetch và -X none. Trong tình huống nào fetch có thể thất bại vì WAL bị recycle?

### Bài 15 — -R

Trên PostgreSQL 12+, -R tạo những file/settings nào? Vai trò của standby.signal là gì?

### Bài 16 — Replication slot options

Giải thích kết hợp -C và -S trong pg_basebackup. Nếu slot đã tồn tại, nên chạy lệnh thế nào?

### Bài 17 — primary_conninfo

Viết connection string có host, port, user, application_name, sslmode, sslrootcert và passfile. Vì sao không nhúng password?

### Bài 18 — primary_slot_name

Vì sao mỗi standby nên có slot riêng? Slot name không tồn tại sẽ ảnh hưởng WAL receiver thế nào?

### Bài 19 — Tablespaces

Primary có tablespace ở /primary/fast_ts nhưng standby mount ở /standby/fast_ts. Viết mapping -T phù hợp và nêu các điều cần xác nhận.

### Bài 20 — Destination directory

pg_basebackup báo destination directory exists and is not empty. Hãy mô tả quy trình kiểm tra/dọn destination an toàn.

### Bài 21 — Khởi động standby

Sau khi base backup hoàn tất, nêu các bước kiểm tra trước khi start service.

### Bài 22 — Recovery mode

Truy vấn pg_is_in_recovery(). Kết quả true/false có ý nghĩa gì trong primary/standby?

### Bài 23 — WAL receiver

Đọc pg_stat_wal_receiver. Các cột status, flushed_lsn, latest_end_lsn, sender_host và slot_name cho biết điều gì?

### Bài 24 — WAL sender

Đọc pg_stat_replication trên primary. Làm thế nào nhận biết standby đang streaming và xác định application_name/client_addr?

### Bài 25 — Replication lag

Dùng pg_last_wal_receive_lsn, pg_last_wal_replay_lsn và pg_wal_lsn_diff để tính bytes đang chờ replay.

### Bài 26 — Timestamp lag

Vì sao pg_last_xact_replay_timestamp có thể cũ khi primary idle dù standby không lag? Đề xuất metrics bổ sung.

### Bài 27 — Slot retention

Một slot active nhưng retained WAL distance tăng nhanh. Những metrics nào cần kiểm tra để biết standby có nhận/replay kịp không?

### Bài 28 — Hot standby

Giải thích hot_standby và vì sao physical standby chỉ phục vụ read-only queries trong recovery.

### Bài 29 — Query conflicts

Một SELECT dài trên standby bị cancel do VACUUM cleanup từ primary. Giải thích max_standby_streaming_delay và hot_standby_feedback trade-off.

### Bài 30 — Synchronous replication

Giải thích synchronous_standby_names và application_name matching. So sánh durability/latency trade-off với asynchronous replication.

### Bài 31 — WAL archive fallback

Thiết kế restore_command để standby lấy WAL từ archive khi streaming không có segment cần thiết. Vì sao phải bảo đảm timeline và WAL chain đúng?

### Bài 32 — pg_verifybackup

pg_verifybackup chứng minh điều gì và không chứng minh điều gì? Vì sao vẫn cần start standby/restore test?

### Bài 33 — Multiple standbys

Một primary có 5 standbys. Hãy thiết kế application_name, slots, sender capacity và monitoring riêng cho từng standby.

### Bài 34 — Cascading replication

Giải thích cascading standby giảm tải primary thế nào và thêm failure/lag hop ra sao.

### Bài 35 — Reconnect

Standby restart sau 10 phút. Mô tả cách nó đọc standby.signal, lấy primary_conninfo, kết nối lại và replay WAL.

### Bài 36 — Missing WAL

Standby báo requested WAL segment has already been removed. Hãy điều tra slot, wal_keep_size, archive và quyết định reseed khi cần.

### Bài 37 — Connection refused

Liệt kê các lớp kiểm tra từ DNS, TCP, listen_addresses, firewall tới PostgreSQL logs.

### Bài 38 — Authentication failure

Một standby bị password authentication failed. Hãy kiểm tra role, passfile match, escaping, service permissions và pg_hba method.

### Bài 39 — Failover

Giải thích vì sao tạo standby không tự động tạo HA. Trước khi pg_promote, cần fence primary cũ như thế nào để tránh split brain?

### Bài 40 — Thiết kế triển khai end-to-end

Một PostgreSQL primary có 2 TB dữ liệu, 3.000 writes/second, WAL generation peak 80 MB/s. Cần tạo hai physical standbys:

- Standby A ở cùng region để phục vụ read-only queries.
- Standby B ở region DR.
- RPO mục tiêu 30 giây.
- Một standby có query reporting dài.
- Network DR đôi lúc gián đoạn 15 phút.
- Cần tránh pg_wal volume tăng không kiểm soát.

Hãy thiết kế:

1. wal_level, max_wal_senders và max_replication_slots.
2. Replication roles, pg_hba rules, TLS và passfiles.
3. pg_basebackup command/options cho mỗi standby.
4. Slot strategy và max_slot_wal_keep_size/wal_keep_size.
5. WAL archive fallback cho DR standby.
6. primary_conninfo/application_name và standby.signal.
7. Monitoring receive/replay lag, slot retention và disk headroom.
8. Hot standby conflict policy cho reporting query.
9. Failover/fencing/rejoin procedure.
10. Rebuild/reseed runbook khi standby mất WAL.

## Kết luận

**Tạo physical standby bắt đầu bằng một base backup nhất quán và kết thúc khi WAL receiver/recovery process kết nối, replay và được giám sát ổn định.** Primary cần wal_level phù hợp, đủ WAL senders/slots, listen address và pg_hba rule giới hạn đúng standby. Replication role chỉ cần LOGIN/REPLICATION; kết nối nên dùng TLS, xác minh server identity và credentials được giữ trong passfile/secret manager.

**pg_basebackup -X stream -R là quy trình phổ biến cho PostgreSQL 12+.** -X stream lấy WAL trong lúc backup, -R tạo standby.signal và connection settings, còn -S/-C cho phép standby dùng physical replication slot. Phải xác nhận destination trống, tablespace mapping đúng, slot có owner và service dùng đúng PGDATA trước khi start.

Sau khi khởi động, kiểm tra pg_is_in_recovery() trên standby, pg_stat_wal_receiver ở standby và pg_stat_replication trên primary. Theo dõi receive/replay LSN, lag, slot retention, WAL archive và disk headroom. Standby hỗ trợ read-only workload và failover, nhưng không thay backup/PITR; query conflicts, WAL loss, credential expiry và network outage đều cần runbook.

Cuối cùng, **physical replication là một cơ chế truyền trạng thái, không phải một quy trình HA hoàn chỉnh**. Promotion phải có fencing để tránh split brain, các standbys cần được reconfigure sau failover và old primary phải được rewind/reseed theo lịch sử timeline. Triển khai tốt là kết hợp base backup, WAL continuity, security, monitoring, backup độc lập và restore/failover drills đã thử nghiệm.
