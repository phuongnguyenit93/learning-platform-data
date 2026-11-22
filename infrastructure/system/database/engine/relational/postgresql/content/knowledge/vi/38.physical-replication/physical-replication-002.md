# Đồng bộ vật lý dựa trên WAL và điều kiện tương thích trong PostgreSQL

Physical replication của PostgreSQL duy trì một standby bằng cách chuyển các bản ghi **Write-Ahead Log (WAL)** từ primary sang server dự phòng, sau đó replay các bản ghi đó để tái tạo thay đổi trên data files. PostgreSQL không gửi từng câu SQL hay từng row đã thay đổi; nó gửi luồng WAL ở cấp vật lý. Standby vì vậy duy trì một bản sao của toàn bộ cluster theo cùng định dạng lưu trữ.

Một standby vật lý phải được khởi tạo từ một **base backup** tương thích với primary. Sau đó, standby nhận WAL liên tục qua streaming replication, qua WAL archive, hoặc kết hợp cả hai. Khi standby replay WAL, dữ liệu và cấu trúc vật lý được đưa tới cùng trạng thái như primary tại một điểm LSN.

Physical replication có ràng buộc tương thích chặt chẽ:

- Primary và standby phải dùng cùng major PostgreSQL version; WAL và data format không phải giao thức nâng cấp major version.
- Kiến trúc phần cứng phải tương thích, đặc biệt không thể stream từ hệ thống 32-bit sang 64-bit.
- Các đường dẫn tablespace được truyền nguyên dạng; nếu có tablespace, standby cần mount paths tương ứng.
- Các build/data-format settings ảnh hưởng layout phải tương thích; không thể ghép tùy tiện cluster được tạo bằng các block formats khác nhau.
- Standby phải bắt đầu từ base backup của đúng cluster/system identifier và có đầy đủ WAL liên tục để replay.

```text
       PRIMARY                                  STANDBY
  +----------------+                       +----------------+
  | Transactions   |                       | WAL receiver   |
  | modify pages   |                       |                |
  +-------+--------+                       +--------+-------+
          |                                         |
          v                                         |
  +----------------+       WAL stream               |
  | WAL buffers    | ------------------------------>|
  | and pg_wal     |                                 v
  +----------------+                       +----------------+
          |                                | pg_wal         |
          v                                +--------+-------+
  +----------------+                                 |
  | WAL sender     |                                 v
  +----------------+                       +----------------+
                                           | Startup/replay |
                                           | process        |
                                           +--------+-------+
                                                    |
                                                    v
                                           +----------------+
                                           | Standby pages  |
                                           | (read-only if  |
                                           | hot_standby)   |
                                           +----------------+
```

Bài thuộc chương **Sao chép vật lý** của module *Database Engine Relational PostgreSQL*. Mục tiêu là hiểu cơ chế đồng bộ vật lý dựa trên WAL, cách dựng standby, cách giữ WAL đủ lâu, và cách xác định hai server có tương thích để tham gia cùng một physical replication stream hay không.

Sau bài học, bạn có thể:

1. Phân biệt physical replication, logical replication và file-based WAL archiving.
2. Giải thích vai trò của primary, walsender, walreceiver và startup/recovery process.
3. Hiểu base backup, system identifier, LSN và timeline.
4. Dựng physical standby bằng pg_basebackup.
5. Cấu hình replication role, pg_hba.conf, wal_level, wal_senders và replication slots.
6. Phân biệt asynchronous và synchronous physical replication.
7. Theo dõi WAL receive/replay lag và xác định nguyên nhân standby bị tụt.
8. Nêu các điều kiện tương thích về major version, architecture, data format và tablespace paths.
9. Xử lý WAL retention, archive recovery, cascading replication và failover.
10. Nhận diện khi cần pg_rewind hoặc base backup mới để đưa node cũ trở lại standby.

> **Phạm vi thực hành:** Các lệnh cấu hình replication, tạo slot, base backup, promote hoặc rewind chỉ chạy trên cluster lab hoặc theo quy trình vận hành đã được phê duyệt. Không chạy pg_basebackup vào data directory đang được PostgreSQL sử dụng; không promote một node khi primary cũ vẫn có thể nhận ghi nếu chưa có fencing.

---

## 1. Physical replication là gì?

### 1.1. Sao chép thay đổi ở cấp WAL

PostgreSQL ghi thay đổi cần thiết vào WAL trước khi data pages được ghi xuống các data files. Physical replication gửi các WAL records này từ primary sang standby. Standby ghi WAL nhận được vào khu vực WAL của nó và replay để cập nhật data pages.

Đây là sao chép ở cấp vật lý:

- Không phân tích câu SQL để phát lại câu lệnh trên standby.
- Không chọn riêng một table hoặc schema để stream.
- Không cần tạo publication/subscription.
- Standby phải có cùng physical cluster format và nhận WAL hợp lệ của primary.

### 1.2. Primary

Primary là server đang nhận các transaction đọc/ghi bình thường. Khi thay đổi dữ liệu:

1. Backend tạo WAL records.
2. WAL được ghi vào WAL buffers và WAL files.
3. WAL sender đọc các WAL records cần truyền.
4. Standby nhận stream và replay records.

Primary có thể phục vụ nhiều physical standbys cùng lúc, trong giới hạn cấu hình và tài nguyên.

### 1.3. Standby

Standby là một bản sao vật lý đang ở chế độ recovery. Nó liên tục đọc WAL từ archive hoặc primary, rồi áp dụng các records để theo kịp primary.

Standby không nhận transaction ghi trực tiếp như primary. Khi bật hot standby, nó có thể phục vụ read-only queries trong lúc recovery tiếp tục.

### 1.4. Vì sao không sao chép từng row?

WAL phản ánh các thay đổi ở cấp storage engine, bao gồm những thay đổi cần thiết cho heap, index, catalog và các thành phần khác. Stream WAL cho phép standby tái tạo trạng thái vật lý mà không phải thực thi lại SQL logic.

Điều này cũng giải thích vì sao physical replication gắn chặt với major version và data layout: standby phải hiểu cùng WAL record format và storage structures với primary.

### 1.5. Một stream bao phủ cả cluster

Physical replication sao chép cluster, không phải một table riêng lẻ. Một standby vật lý nhận WAL cho mọi database trong cùng cluster, cùng global catalogs và các objects liên quan.

Nếu chỉ cần replicate một số bảng hoặc cần subscriber chạy khác major version, hãy xem xét logical replication hoặc một pipeline export/import. Physical replication không phải công cụ chọn lọc dữ liệu.

---

## 2. Phân biệt physical replication, logical replication và WAL archiving

| Cơ chế | Đơn vị sao chép | Cách áp dụng | Phạm vi/đặc điểm |
|---|---|---|---|
| Physical streaming replication | WAL records vật lý | Standby replay WAL | Toàn cluster, standby physical phải tương thích |
| File-based WAL shipping | WAL segment files | Standby restore từng segment | Có thể trễ theo chu kỳ segment/archive |
| Logical replication | Logical changes của publications | Subscriber apply changes | Chọn bảng, có thể hỗ trợ nâng cấp major version |
| Base backup + WAL archive | Data directory snapshot và WAL liên tục | Restore base backup rồi replay WAL | Physical recovery, PITR và standby bootstrap |

### 2.1. Streaming replication

Primary stream WAL records qua kết nối replication. Standby có thể nhận thay đổi trước khi WAL segment đầy hoặc được archive, vì vậy độ trễ thường nhỏ hơn file shipping.

### 2.2. File-based log shipping

Primary archive các WAL segments và standby lấy từng file qua `restore_command`. Đây là cơ chế asynchronous: WAL được archive sau khi đã được tạo, nên có thể tồn tại một khoảng thời gian chưa chuyển sang standby.

### 2.3. Kết hợp archive và streaming

Một standby có thể dùng archive để bắt kịp các WAL segments cũ, rồi stream các records mới từ primary. Kết hợp cả hai giúp standby phục hồi khi kết nối mạng bị gián đoạn lâu hơn lượng WAL đang giữ trong primary.

### 2.4. Logical replication không phải physical standby

Logical replication chuyển các thay đổi ở mức logical publication/subscription. Subscriber có thể có schema riêng và thường không tự đồng bộ mọi sequence, DDL, roles hoặc mọi cluster objects.

Physical replication có semantics khác: standby nhận WAL và replay storage changes, nên data layout/major version compatibility quan trọng.

---

## 3. WAL, LSN và quá trình đồng bộ

### 3.1. WAL records và WAL segments

WAL records được append vào WAL stream. Các records được lưu trong các WAL segment files bên dưới thư mục `pg_wal`. Segment size thường là 16 MB theo mặc định, nhưng có thể thay đổi lúc initdb.

Standby không cần chờ toàn bộ segment được ghi đầy mới nhận WAL qua streaming replication.

### 3.2. LSN

LSN (Log Sequence Number) là vị trí byte trong WAL stream. Nó tăng dần khi WAL records được tạo. LSN giúp so sánh tiến độ:

- Primary đã ghi WAL tới đâu.
- Primary đã gửi tới đâu.
- Standby đã nhận/flush tới đâu.
- Standby đã replay tới đâu.

LSN là vị trí trong WAL, không phải timestamp.

### 3.3. Các mốc trên primary

```sql
SELECT
    pg_current_wal_lsn()        AS current_lsn,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_flush_lsn()  AS flush_lsn;
```

### 3.4. Các mốc trên standby

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn()  AS replay_lsn,
    pg_is_in_recovery()       AS is_standby;
```

`pg_last_wal_receive_lsn()` là vị trí WAL cuối cùng được nhận và ghi bởi standby; `pg_last_wal_replay_lsn()` là vị trí cuối cùng được replay. Hai vị trí có thể khác nhau khi standby nhận WAL nhanh hơn khả năng apply.

### 3.5. Hai giai đoạn: receive và replay

Standby có thể nhận WAL trước, ghi vào local WAL storage, rồi replay sau. Vì vậy cần phân biệt:

- **Receive lag:** WAL chưa đến được standby.
- **Replay lag:** WAL đã đến nhưng chưa được áp dụng vào database state.

Nếu receive LSN gần primary nhưng replay LSN tụt xa, vấn đề thường nằm ở replay capacity, recovery conflicts, I/O hoặc workload standby.

### 3.6. Minh họa

```text
Primary WAL:  [------------------------------- LSN 900]
                         |
                         | stream
                         v
Standby WAL:  [------------------------- LSN 850]  received
                         |
                         | replay
                         v
Standby data: [-------------------- LSN 820]       replayed

Receive gap = primary LSN - receive LSN
Replay gap  = receive LSN - replay LSN
```

### 3.7. WAL không phải transaction SQL replay

Standby replay WAL records theo thứ tự cần thiết. Nó không chạy lại câu INSERT/UPDATE từ client. Vì thế một query chỉ được thực thi trên primary và tạo ra WAL; standby không cần cùng application code để replay physical changes, nhưng vẫn cần cùng khả năng đọc storage/WAL format.

---

## 4. Thành phần của streaming replication

### 4.1. WAL sender

Trên primary, mỗi kết nối streaming standby được phục vụ bởi một WAL sender process. WAL sender gửi WAL stream và xử lý feedback/status từ standby.

Có thể xem các WAL sender:

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
    sync_state
FROM pg_stat_replication;
```

### 4.2. WAL receiver

Trên standby, WAL receiver kết nối primary và nhận WAL stream. View `pg_stat_wal_receiver` hiển thị trạng thái kết nối và vị trí WAL nhận được.

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
    latest_end_time
FROM pg_stat_wal_receiver;
```

Tên cột phụ thuộc PostgreSQL version; đối chiếu view schema với version đang chạy.

### 4.3. Startup/recovery process

Startup process đọc WAL từ archive, local `pg_wal` hoặc streaming receiver và replay records. Nó giữ standby ở chế độ recovery cho tới khi được promote.

### 4.4. Walreceiver status feedback

Standby gửi status feedback cho primary để thông báo WAL đã write/flush/replay tới đâu. Primary dùng thông tin này cho monitoring, synchronous replication và quản lý WAL retention/slots.

### 4.5. Replication protocol

Standby kết nối tới pseudo-database `replication` bằng một role có quyền REPLICATION. Kết nối được xác thực qua pg_hba.conf, thường dùng TLS và SCRAM/password hoặc certificate authentication theo môi trường.

### 4.6. Replication role

Tạo role chuyên dụng:

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-secret';
```

Không dùng superuser cho standby nếu không có lý do vận hành đặc biệt. Quyền REPLICATION rất mạnh vì WAL stream có thể chứa dữ liệu nhạy cảm; chỉ cấp cho host đáng tin và bảo vệ credentials.

---

## 5. Điều kiện tương thích của physical replication

### 5.1. Cùng major PostgreSQL version

Physical log shipping/streaming giữa hai server khác major version nhìn chung không được hỗ trợ. Ví dụ primary PostgreSQL 17 không thể có physical standby PostgreSQL 16 hoặc 18 chỉ bằng cách trỏ primary_conninfo sang server kia.

WAL format, system catalogs và storage internals có thể thay đổi giữa các major releases. Muốn nâng cấp major version, dùng quy trình như pg_upgrade, dump/restore hoặc logical replication phù hợp; không coi physical replication là đường upgrade major.

### 5.2. Minor version

PostgreSQL không chủ đích thay đổi disk format trong minor release updates, nên hai minor versions khác nhau có khả năng hoạt động cùng nhau. Tuy nhiên, tài liệu PostgreSQL không đưa ra bảo đảm hỗ trợ chính thức cho mọi tổ hợp minor versions.

Thực hành an toàn:

- Giữ primary và standby ở cùng minor release khi có thể.
- Khi cập nhật minor release, cập nhật standby trước rồi primary.
- Kiểm tra release notes, extension compatibility và quy trình restart.
- Không cố duy trì một tổ hợp phiên bản lệch nhau lâu dài.

### 5.3. Cùng kiến trúc phần cứng

Hardware architecture phải tương thích. Physical log shipping từ hệ thống 32-bit sang 64-bit không hoạt động. Hai máy không cần cùng model CPU hay cùng dung lượng RAM, nhưng phải cùng kiến trúc có thể đọc data/WAL representation của nhau.

### 5.4. Operating system và binary build

Nên dùng hệ điều hành và PostgreSQL build tương đồng để giảm rủi ro vận hành. Các định dạng lưu trữ phụ thuộc platform/build, chẳng hạn integer/float representation và các compile-time options. Không giả định một data directory có thể chuyển tự do giữa mọi OS hoặc mọi binary build.

### 5.5. Block size và WAL block size

PostgreSQL có các build-time settings ảnh hưởng data layout, ví dụ database block size (`BLCKSZ`) và WAL block size (`XLOG_BLCKSZ`). Thay đổi các giá trị build này làm thay đổi on-disk compatibility.

Primary và standby cần binary/data format tương thích. Dùng cùng PostgreSQL distribution/build configuration là cách giảm rủi ro; nếu tự build PostgreSQL với block sizes tùy chỉnh, phải xác minh các giá trị tương ứng trước khi tạo physical standby.

### 5.6. WAL segment size

WAL segment size được xác định khi khởi tạo cluster và có thể khác mặc định 16 MB. Standby vật lý được tạo từ base backup sẽ mang theo control/data state của cluster nguồn; không tự initdb một cluster độc lập với WAL layout khác rồi kỳ vọng có thể nối vào stream.

Khi dựng standby, dùng pg_basebackup từ primary để lấy đúng cluster layout. Với công cụ backup/restore tùy chỉnh, phải giữ nguyên các format parameters cần thiết.

### 5.7. Tablespace paths

Các đường dẫn tablespace được truyền qua WAL theo đường dẫn đã cấu hình. Nếu primary có tablespace mount tại `/data/pg_tblspc/fastspace` thì standby cần đường dẫn tương ứng khả dụng.

Khi tạo tablespace mới trên primary, phải chuẩn bị mount point/đường dẫn trên mọi standby trước khi lệnh CREATE TABLESPACE chạy. Nếu không, replay có thể thất bại vì path không tồn tại hoặc quyền filesystem không phù hợp.

### 5.8. System identifier

Primary và standby phải thuộc cùng một cluster lineage. Base backup tạo từ primary sẽ giữ system identifier của cluster đó. Một cluster được initdb riêng có system identifier khác, không thể trở thành physical standby chỉ bằng cách thêm standby.signal và primary_conninfo.

Kiểm tra bằng:

```sql
SELECT system_identifier
FROM pg_control_system();
```

Hàm này cần quyền phù hợp và chạy trên từng server để so sánh.

### 5.9. Locale, collation và extension

Physical standby kế thừa data directory và catalogs từ primary; không được tạo một database cluster mới với locale/collation khác rồi ghép WAL vào. Extension binaries cần tương thích với server build và có mặt trên standby khi cần load extension/library.

Với standby được tạo bằng base backup, extension SQL objects và dữ liệu đã có trong data directory. Tuy nhiên, các shared libraries, OS packages, custom modules và file cấu hình ngoài data directory vẫn phải được cài/đồng bộ riêng.

### 5.10. Bảng kiểm tương thích

| Điều kiện | Yêu cầu thực tế | Cách kiểm tra |
|---|---|---|
| Major version | Phải cùng major | `SHOW server_version` |
| Minor version | Nên cùng release; khác minor không có formal support | `SELECT version()` và release notes |
| Hardware architecture | Phải cùng kiến trúc tương thích | OS/CPU architecture |
| Data/WAL build format | Block/layout settings tương thích | Build metadata, initdb/build options |
| WAL segment layout | Phải lấy đúng từ cluster nguồn | Base backup/control data |
| System identifier | Cùng cluster lineage | `pg_control_system()` |
| Tablespace paths | Mount paths tương ứng phải tồn tại | `pg_tablespace_location()` và filesystem |
| Extension binaries | Có build tương thích trên standby | Installed packages/shared libraries |
| Replication protocol | Kết nối và auth replication hợp lệ | pg_hba.conf, role, logs |

---

## 6. Chuẩn bị primary để gửi WAL

### 6.1. Bật wal_level phù hợp

Trên primary, `wal_level` phải đủ để tạo WAL phục vụ physical replication:

```conf
wal_level = replica
```

`replica` là mức thường dùng cho physical standby. `logical` cũng bao gồm khả năng cần thiết cho physical replication và bổ sung thông tin cho logical decoding. `minimal` không phù hợp cho streaming standby.

### 6.2. Cấu hình số WAL senders

```conf
max_wal_senders = 10
```

`max_wal_senders` giới hạn số WAL sender connections đồng thời. Hãy tính cả:

- Physical standby connections.
- pg_basebackup dùng streaming WAL.
- Các chương trình nhận WAL như pg_receivewal.
- Kết nối dự phòng khi cần failover/rebuild.

Để giá trị quá thấp có thể khiến standby hoặc base backup không kết nối được.

### 6.3. Replication slots

Nếu dùng physical replication slots, cấu hình đủ số slots:

```conf
max_replication_slots = 10
```

Slot giúp primary giữ lại WAL mà standby chưa nhận được. Nó giảm nguy cơ WAL cần thiết bị recycle khi standby tạm mất kết nối.

### 6.4. WAL retention dự phòng

```conf
wal_keep_size = 2GB
```

`wal_keep_size` chỉ đặt mức WAL tối thiểu giữ lại để standby có cơ hội bắt kịp. Nó không phải cam kết giữ đúng mọi WAL cần cho một standby bị offline lâu. Nếu lag vượt lượng WAL còn giữ, standby có thể phải lấy từ archive hoặc được tạo lại từ base backup.

### 6.5. Giới hạn WAL do replication slots giữ

```conf
max_slot_wal_keep_size = 20GB
```

Giá trị ví dụ này giới hạn lượng WAL được giữ bởi replication slots theo checkpoint. Nếu slot tụt quá xa và WAL cần thiết bị xóa, standby có thể mất khả năng tiếp tục stream bằng slot đó và cần archive hoặc reinitialize.

Giá trị `-1` có nghĩa không đặt giới hạn theo tham số này; một slot không được consumer có thể làm `pg_wal` tăng rất lớn. Cần theo dõi dung lượng đĩa.

### 6.6. Bật WAL archiving khi cần

```conf
archive_mode = on
archive_command = 'test ! -f /archive/%f && cp %p /archive/%f'
```

Đây là ví dụ minh họa trên môi trường lab. Production nên dùng archive destination bền vững, retry/error handling, kiểm tra checksum và retention policy. Không dùng lệnh copy đơn giản nếu không bảo đảm quyền, atomic publish và quản lý trùng file.

### 6.7. listen_addresses

Primary phải lắng nghe trên interface mà standby có thể truy cập:

```conf
listen_addresses = '*'
port = 5432
```

Trong production, giới hạn interface cụ thể và firewall rules thay vì mở mọi interface nếu không cần.

### 6.8. pg_hba.conf

Cho phép replication user từ địa chỉ standby:

```conf
# TYPE  DATABASE      USER         ADDRESS         METHOD
hostssl replication   replicator   10.20.0.12/32   scram-sha-256
```

Database field phải là pseudo-database `replication` cho replication connection. Dùng hostssl khi yêu cầu TLS; kết hợp certificate verification ở client và firewall/network policy.

### 6.9. Reload hoặc restart

Một số replication settings cần restart; một số khác có thể reload. Kiểm tra context trong pg_settings:

```sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'archive_mode',
    'listen_addresses'
)
ORDER BY name;
```

`wal_level`, `max_wal_senders`, `max_replication_slots`, `archive_mode` và `listen_addresses` thường cần restart theo context/version. Thực hiện restart có kiểm soát.

---

## 7. Tạo replication role và xác thực kết nối

### 7.1. Tạo role chuyên dụng

Trên primary:

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-a-strong-secret';
```

Role REPLICATION được phép mở replication connection và đọc WAL stream. Bảo vệ role như một credential nhạy cảm; WAL có thể chứa nội dung dữ liệu ở cấp vật lý.

### 7.2. Không ghi password trực tiếp vào script dùng chung

Tránh commit password vào repository hoặc lưu trong command history. Có thể dùng:

- libpq password file với quyền filesystem phù hợp.
- Secret manager.
- Certificate authentication.
- Service configuration được bảo vệ.

### 7.3. Password file

Trên Unix-like systems, file `~/.pgpass` có dạng:

```text
hostname:port:replication:replicator:secret
```

Đặt quyền file chỉ cho owner đọc/ghi:

```bash
chmod 0600 ~/.pgpass
```

Trên Windows, pgpass file dùng vị trí cấu hình tương ứng và ACL bảo vệ; không áp dụng chmod.

### 7.4. Kiểm tra quyền và kết nối

Có thể kiểm tra role:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication,
    rolsuper
FROM pg_roles
WHERE rolname = 'replicator';
```

Không dùng một kết nối database bình thường để kết luận replication authentication đã hoạt động. Test bằng pg_basebackup hoặc replication protocol client từ host standby.

### 7.5. Firewall và TLS

Chỉ cho phép standby hosts kết nối port PostgreSQL. Nếu đi qua network không tin cậy:

- Bật TLS trên primary.
- Dùng sslmode=verify-full khi phù hợp với PKI.
- Xác minh CA và hostname.
- Bảo vệ passfile/certificate private key.
- Không dùng `trust` cho replication network production.

---

---

## 8. Dựng standby bằng pg_basebackup

### 8.1. Base backup là điểm khởi đầu

Standby phải có bản sao vật lý nhất quán của data directory. `pg_basebackup` lấy base backup từ một server đang chạy và bảo đảm có đủ WAL để khôi phục backup về trạng thái nhất quán.

Không tự copy data directory đang hoạt động bằng file copy thông thường. File copy không phối hợp với checkpoint/WAL và có thể tạo một tập file không nhất quán.

### 8.2. Chuẩn bị data directory

Standby target phải:

- Dùng PostgreSQL major version tương thích.
- Có data directory đích trống hoặc được chuẩn bị theo hướng dẫn của công cụ.
- Có owner/permissions phù hợp với OS account chạy PostgreSQL.
- Có đủ dung lượng cho data files, WAL và tablespaces.
- Có các mount paths tablespace tương ứng nếu primary dùng tablespaces.

Không ghi đè một cluster đang chạy.

### 8.3. Base backup dạng plain

Ví dụ chạy từ standby host:

```bash
pg_basebackup \
  --host=primary.example.net \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/18/main \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf
```

`--wal-method=stream` stream WAL song song với quá trình copy data files để base backup có WAL cần thiết. `--write-recovery-conf` (viết tắt `-R`) tạo cấu hình để server khởi động ở standby mode, gồm `standby.signal` và các thông tin kết nối phù hợp.

### 8.4. Tạo và dùng physical replication slot

Nếu muốn pg_basebackup tạo slot:

```bash
pg_basebackup \
  --host=primary.example.net \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/18/main \
  --format=plain \
  --wal-method=stream \
  --create-slot \
  --slot=standby_a \
  --progress \
  --write-recovery-conf
```

`--create-slot` tạo slot có tên chỉ định; `--slot` xác định slot sử dụng. Nếu slot đã tồn tại, không dùng create-slot lần nữa; chọn slot phù hợp và bảo đảm slot không thuộc một standby khác.

### 8.5. WAL method

`pg_basebackup` hỗ trợ các cách lấy WAL như:

- `stream`: nhận WAL streaming trong lúc base backup chạy.
- `fetch`: tải các WAL segments cần thiết từ primary ở cuối quá trình backup; các segments đó phải còn trong `pg_wal` cho tới khi được lấy, nên cần đủ WAL retention.
- `none` ở các version hỗ trợ: backup không tự lấy WAL; chỉ dùng khi quy trình khác bảo đảm WAL đầy đủ.

Với standby mới, `stream` thường là lựa chọn dễ vận hành hơn, nhưng cần thêm WAL sender connection và tài nguyên network.

### 8.6. Directory format

`pg_basebackup` cũng hỗ trợ tar hoặc manifest/checksum options tùy version. Dù dùng format nào, mục tiêu vẫn là tạo một base backup nhất quán và đủ WAL. Đọc `pg_basebackup --help` và documentation đúng major version.

### 8.7. Sau base backup

Kiểm tra:

- Data directory có dữ liệu cluster và control file.
- File `standby.signal` được tạo bởi `-R`.
- `postgresql.auto.conf` chứa primary_conninfo/slot nếu đã cấu hình.
- Owner và permissions đúng.
- Tablespace symlinks/paths hợp lệ.
- WAL archive hoặc streaming source truy cập được.

### 8.8. Khởi động standby

Khởi động PostgreSQL bằng service manager/pg_ctl theo môi trường. Trên standby:

```sql
SELECT pg_is_in_recovery();
```

Kết quả `true` cho biết server đang trong recovery/standby mode.

### 8.9. Không chạy initdb trước rồi trộn file

Nếu đã initdb một cluster khác ở data directory đích, không copy đè một phần file để biến nó thành standby. Dùng data directory trống và pg_basebackup, hoặc restore base backup theo công cụ phù hợp.

---

## 9. Cấu hình standby kết nối primary

### 9.1. standby.signal

PostgreSQL nhận biết standby mode khi file `standby.signal` tồn tại trong data directory lúc server khởi động.

`pg_basebackup -R` tự tạo file này. Nếu cấu hình thủ công, tạo signal file đúng data directory và đảm bảo quyền truy cập.

### 9.2. primary_conninfo

Trong `postgresql.conf` hoặc `postgresql.auto.conf`:

```conf
primary_conninfo = 'host=primary.example.net port=5432 user=replicator application_name=standby_a sslmode=verify-full'
```

`application_name` giúp primary nhận diện standby trong `pg_stat_replication` và chọn synchronous standby. Đừng nhúng password dạng plain text nếu có thể dùng passfile/secret management.

### 9.3. primary_slot_name

```conf
primary_slot_name = 'standby_a'
```

Slot phải tồn tại trên primary. Standby dùng slot này để primary giữ WAL cần thiết trong lúc standby offline hoặc bị chậm.

### 9.4. restore_command

Nếu dùng WAL archive:

```conf
restore_command = 'cp /archive/%f %p'
```

Production cần xử lý lỗi khi file chưa tồn tại, retry và xác minh archive. Ví dụ cp chỉ phù hợp lab khi archive ở cùng host/filesystem.

### 9.5. hot_standby

```conf
hot_standby = on
```

Hot standby cho phép read-only queries trong lúc recovery. Một số cấu hình hot_standby là mặc định on, nhưng hãy kiểm tra giá trị và version.

### 9.6. Kết nối từ standby

WAL receiver kết nối tới primary bằng replication connection. Trên primary, `pg_stat_replication` nên hiển thị một row cho standby; trên standby, `pg_stat_wal_receiver` nên hiển thị trạng thái streaming.

### 9.7. Đường dẫn tablespace

Kiểm tra mọi mount path mà primary sử dụng. Nếu base backup tạo symlink dưới `pg_tblspc`, đích của symlink phải tồn tại và có quyền phù hợp trên standby.

---

## 10. Replication slots và WAL retention

### 10.1. Vấn đề WAL bị recycle

Primary không giữ mọi WAL segment mãi mãi. Sau checkpoint, các segment cũ có thể được recycle hoặc xóa khi không còn cần cho recovery, archiving hoặc replication.

Nếu standby bị ngắt kết nối lâu và WAL cần thiết đã bị recycle, standby không thể tiếp tục từ LSN cũ chỉ bằng streaming. Nó cần lấy WAL từ archive nếu còn đầy đủ, hoặc được khởi tạo lại từ base backup mới.

### 10.2. Physical replication slot

Physical replication slot giữ WAL cần thiết cho một standby. Standby cấu hình `primary_slot_name` trỏ tới slot trên upstream primary.

Tạo slot thủ công:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
```

Xóa slot khi chắc chắn standby không còn dùng:

```sql
SELECT pg_drop_replication_slot('standby_a');
```

Không xóa slot chỉ vì thấy inactive; standby có thể đang tạm dừng hoặc cần slot để bắt kịp sau bảo trì.

### 10.3. Slot giữ WAL và nguy cơ đầy đĩa

Một slot không active vẫn có thể giữ WAL. Nếu standby ngừng hoạt động nhưng slot còn tồn tại, primary có thể tích lũy nhiều WAL trong `pg_wal`.

Theo dõi:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
```

Một số cột chỉ có ở PostgreSQL versions mới hơn. Với query dùng trên nhiều major versions, chỉ chọn các cột phổ biến như `slot_name`, `slot_type`, `active` và `restart_lsn`.

### 10.4. max_slot_wal_keep_size

`max_slot_wal_keep_size` giới hạn dung lượng WAL mà replication slots được phép giữ theo cơ chế checkpoint. Nếu giới hạn bị vượt, slot có thể mất khả năng bảo đảm WAL cần thiết và standby phải lấy WAL từ archive hoặc tạo lại.

Giá trị `-1` cho phép slot giữ WAL không giới hạn bởi tham số này. Điều đó giúp standby có thể bắt kịp sau outage dài nhưng có rủi ro làm đầy filesystem.

### 10.5. wal_keep_size

`wal_keep_size` giữ tối thiểu một lượng WAL trong `pg_wal` để standby có cơ hội bắt kịp mà không cần slot. Đây là mức tối thiểu, không phải bảo đảm tuyệt đối rằng mọi WAL cần thiết sẽ còn.

### 10.6. Archive là đường phục hồi bổ sung

Nếu WAL segments được archive bền vững, standby có thể dùng `restore_command` để lấy các segments còn thiếu rồi quay lại streaming. Archive nên được lưu độc lập với primary storage để primary failure không đồng thời làm mất bản WAL duy nhất.

### 10.7. Chọn slot, wal_keep_size hay archive?

| Cơ chế | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|
| Replication slot | Giữ chính xác WAL cần cho consumer | Slot inactive có thể làm đầy primary disk |
| wal_keep_size | Đơn giản, không cần slot riêng | Chỉ giữ mức tối thiểu; standby lag quá lâu vẫn mất WAL |
| WAL archive | Phục hồi WAL theo segment từ kho độc lập | Cần archive_command, retention, monitoring và đủ throughput |
| Kết hợp slot + archive | Có đường bắt kịp linh hoạt hơn | Nhiều thành phần phải giám sát |

### 10.8. Không để slot orphan

Mỗi slot cần owner và mục đích rõ ràng. Khi decommission standby:

1. Xác nhận node đã dừng và không còn cần WAL.
2. Gỡ cấu hình primary_slot_name ở node nếu còn sử dụng.
3. Kiểm tra slot trên primary.
4. Xác nhận slot không phục vụ node khác.
5. Drop slot theo change procedure.
6. Theo dõi WAL disk usage sau khi slot được xóa.

---

## 11. Asynchronous và synchronous physical replication

### 11.1. Asynchronous là mặc định

Streaming replication mặc định là asynchronous. Primary không phải chờ standby xác nhận WAL trước khi trả COMMIT thành công cho client.

Điều này giảm commit latency và không phụ thuộc standby sẵn sàng để tiếp tục ghi. Đổi lại, khi primary hỏng đột ngột, các transaction đã commit nhưng WAL chưa tới standby có thể mất nếu standby được promote.

### 11.2. Synchronous replication

Synchronous replication cho phép primary chờ một hoặc nhiều synchronous standbys xác nhận WAL theo policy. Cấu hình chính trên primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

`application_name` trong `primary_conninfo` của standby phải khớp một tên trong danh sách. Standby được chọn phải có state streaming trong `pg_stat_replication`.

### 11.3. Mức synchronous_commit

| Giá trị | Điều kiện ACK liên quan standby |
|---|---|
| `off` | Không chờ local WAL flush cho từng commit; không chờ standby |
| `local` | Chờ local WAL flush, không chờ standby |
| `remote_write` | Chờ standby ghi WAL tới OS, chưa cần flush durable storage |
| `on` | Chờ standby flush WAL theo policy synchronous replication |
| `remote_apply` | Chờ standby replay WAL để transaction visible cho query |

Nếu không có synchronous standby được cấu hình, `on` vẫn chờ local flush nhưng không tự tạo remote durability.

### 11.4. FIRST và ANY

```conf
# Chọn một standby theo priority
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'

# Chờ bất kỳ hai standby trong nhóm
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

`FIRST` chọn theo priority trong danh sách. `ANY` dùng quorum: commit chờ số acknowledgements tối thiểu từ nhóm.

### 11.5. Availability tradeoff

Nếu policy cần một synchronous standby nhưng không có node phù hợp đang streaming, các commits yêu cầu synchronous acknowledgement có thể bị chặn. Synchronous replication nâng mức bảo vệ transaction đã ACK theo failure model, nhưng làm write availability phụ thuộc standby/network.

### 11.6. Synchronous standby phải kết nối trực tiếp

Primary chọn synchronous standbys từ các standby kết nối trực tiếp với nó. Primary không xem một downstream standby sau cascading node là synchronous standby trực tiếp của primary.

Nếu cần quorum hoặc commit acknowledgement ở nhiều site, thiết kế topology và synchronous policy phải tính các kết nối trực tiếp và latency thực tế.

### 11.7. Không nhầm synchronous replication với backup

Synchronous standby replay cả các thay đổi hợp lệ lẫn thao tác sai logic được commit. Nó không bảo vệ khỏi DROP TABLE, DELETE nhầm, ransomware có quyền ghi hoặc lỗi ứng dụng. Cần backup và WAL archive độc lập.

---

## 12. Timeline, promotion và failover

### 12.1. Timeline là gì?

Timeline đánh dấu các nhánh lịch sử WAL. Khi standby được promote thành primary, PostgreSQL tạo timeline mới để phân biệt WAL history mới với history của primary cũ.

Timeline history file mô tả điểm phân nhánh. Nó giúp recovery hiểu nhánh WAL nào thuộc lịch sử của cluster sau failover.

### 12.2. Promote standby

Khi quyết định failover:

```sql
SELECT pg_promote(wait => true);
```

Hoặc dùng:

```bash
pg_ctl promote -D /path/to/standby-data
```

Promotion chuyển standby ra khỏi recovery và cho phép nó nhận writes. Đây là thao tác thay đổi vai trò cluster; phải xác minh primary cũ đã bị fencing hoặc không thể tiếp tục nhận writes.

### 12.3. Split brain

Split brain xảy ra khi primary cũ và standby được promote cùng lúc đều nhận writes độc lập. Hai nhánh WAL sẽ diverge; PostgreSQL không tự hợp nhất các transaction đã ghi trên hai primary.

Trước promote:

- Xác định primary thực sự đã down hoặc bị cô lập.
- Dùng fencing/STONITH hoặc cơ chế hạ tầng tương đương.
- Ngăn client tiếp tục ghi vào primary cũ.
- Chọn standby có WAL state phù hợp nhất theo failover policy.
- Ghi nhận timeline/LSN và quyết định RPO.

### 12.4. Automatic failover không nằm trong streaming replication core

Streaming replication truyền WAL và replay trên standby. Việc phát hiện primary failure, bầu chọn node, fencing, cập nhật endpoint và promote thường do operator hoặc HA manager điều phối.

Không coi việc có standby streaming là tự động có failover an toàn.

### 12.5. Rejoin primary cũ

Sau khi standby mới được promote, primary cũ không thể đơn giản khởi động lại như primary độc lập. Nó có timeline history khác và có thể chứa writes không tồn tại trên primary mới.

Để đưa node cũ trở lại topology:

- Dùng `pg_rewind` nếu thỏa điều kiện.
- Hoặc xóa/recreate data directory từ base backup mới.
- Cấu hình node trở lại standby, xác minh nó theo timeline mới.

### 12.6. recovery_target_timeline

Standby có thể chọn timeline cần theo dõi qua:

```conf
recovery_target_timeline = 'latest'
```

`latest` yêu cầu standby theo timeline mới nhất mà nó tìm thấy qua WAL/archive. Cần giữ timeline history files trong archive và kiểm tra đúng cluster lineage.

---

---

## 13. Cascading physical replication

### 13.1. Standby làm upstream cho standby khác

Cascading replication cho phép một standby nhận WAL từ primary rồi stream tiếp WAL tới downstream standbys. Điều này giảm số WAL sender connections trực tiếp trên primary và có thể phân phối WAL giữa các site.

```text
                 PRIMARY
                    |
              WAL streaming
                    |
                    v
                STANDBY A
                    |
              WAL streaming
                 /      \
                v        v
           STANDBY B  STANDBY C
```

### 13.2. Yêu cầu cấu hình

Node trung gian cần cấu hình đủ khả năng gửi WAL downstream, bao gồm `wal_level` phù hợp và `max_wal_senders` đủ lớn. Downstream standby cấu hình `primary_conninfo` trỏ tới standby upstream.

### 13.3. Giới hạn synchronous policy

Primary chỉ biết các standby kết nối trực tiếp. Nó không trực tiếp chọn standby B/C nằm sau standby A làm synchronous standby của mình.

Nếu A bị lag hoặc down, B/C có thể mất nguồn WAL dù primary vẫn hoạt động. Cần thiết kế upstream failover và slot/archive cho từng nhánh.

### 13.4. Replication slot theo từng upstream

Downstream có thể dùng physical slot trên standby upstream nếu cấu hình hỗ trợ. Slot cần được quản lý tại node đang gửi WAL cho downstream. Theo dõi slot ở mọi tầng để tránh một node giữ WAL quá lâu.

### 13.5. Khi nào dùng cascading?

- Có nhiều standbys và muốn giảm kết nối trực tiếp tới primary.
- Có standby đặt tại site/region khác.
- Muốn phân phối read replicas theo topology.
- Cần giới hạn băng thông hoặc số connections từ primary.

Đổi lại, downstream lag có thể cộng dồn qua nhiều tầng và phụ thuộc sức khỏe từng upstream.

---

## 14. Theo dõi replication và đo lag

### 14.1. Trên primary: pg_stat_replication

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
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

Ý nghĩa:

- `sent_lsn`: WAL cuối cùng đã gửi tới standby.
- `write_lsn`: WAL standby đã ghi tới OS/file layer.
- `flush_lsn`: WAL standby đã flush.
- `replay_lsn`: WAL standby đã replay.
- `sync_state`: standby có trạng thái async, potential, sync hoặc quorum theo cấu hình.

### 14.2. Khoảng cách LSN trên primary

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)
        AS bytes_not_sent,
    pg_wal_lsn_diff(sent_lsn, write_lsn)
        AS bytes_sent_not_written,
    pg_wal_lsn_diff(write_lsn, flush_lsn)
        AS bytes_written_not_flushed,
    pg_wal_lsn_diff(flush_lsn, replay_lsn)
        AS bytes_flushed_not_replayed
FROM pg_stat_replication;
```

Đây là các khoảng cách tại thời điểm query. LSN có thể thay đổi liên tục khi primary đang ghi WAL; không dùng một snapshot duy nhất để kết luận standby bị hỏng.

### 14.3. Trên standby: receive và replay

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

`pg_last_xact_replay_timestamp()` là thời điểm commit transaction cuối cùng được replay, không phải phép đo chính xác network lag trong mọi workload. Nếu primary không có writes, timestamp có thể cũ dù standby hoàn toàn caught up.

### 14.4. WAL receiver

```sql
SELECT
    status,
    sender_host,
    sender_port,
    slot_name,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time
FROM pg_stat_wal_receiver;
```

Nếu không có row, standby có thể đang lấy WAL từ archive, chưa được cấu hình streaming, đã promote hoặc kết nối đang lỗi. Kiểm tra logs và `primary_conninfo`.

### 14.5. Tính lag theo thời gian

Có thể dùng `write_lag`, `flush_lag` và `replay_lag` từ `pg_stat_replication` để xem độ trễ gần đây. Các trường này là thống kê thời gian phản ánh quá trình WAL được gửi/ghi/flush/replay; chúng có thể NULL khi idle hoặc không đủ mẫu mới.

Không coi `now() - pg_last_xact_replay_timestamp()` là lag tuyệt đối nếu primary không có traffic ghi. Kết hợp LSN gap, transaction activity và WAL rate.

### 14.6. Trạng thái replication

`state` thường có giá trị `streaming` khi standby đang nhận stream liên tục; các trạng thái khác có thể phản ánh startup/catchup/backup. Dùng state kết hợp logs, LSN và receiver view để chẩn đoán.

### 14.7. Replication conflicts trên hot standby

Trên standby:

```sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
```

Các counters cho biết query trên standby bị cancel vì recovery conflicts. Tên/các cột có thể thay đổi theo major version; kiểm tra schema hiện hành.

### 14.8. Monitoring checklist

- Primary có WAL sender đang streaming?
- Standby có WAL receiver active?
- Receive LSN có tăng?
- Replay LSN có tăng?
- Khoảng cách receive/replay có tăng liên tục?
- Slot có giữ WAL quá lớn?
- Archive có lỗi hoặc backlog?
- Có recovery conflicts/cancelled queries?
- Storage/network có đủ throughput?
- `sync_state` có đúng policy mong muốn?

---

## 15. Đưa primary cũ trở lại bằng pg_rewind hoặc base backup

### 15.1. Vì sao không chỉ khởi động lại node cũ?

Sau failover, primary mới tiếp tục ghi trên timeline mới. Primary cũ có thể có WAL/data changes trên timeline cũ mà primary mới không có. Nếu node cũ tự khởi động ở chế độ primary, hai nhánh sẽ diverge và gây split brain.

### 15.2. pg_rewind

`pg_rewind` đồng bộ một data directory đã diverge với một source cluster bằng cách xác định các blocks thay đổi kể từ điểm chung và copy lại blocks cần thiết. Nó thường nhanh hơn full base backup khi chỉ một phần nhỏ data files thay đổi.

### 15.3. Điều kiện quan trọng

Để pg_rewind hoạt động, cần:

- Target và source có chung cluster history trước khi diverge.
- Target đã được shutdown sạch trước khi rewind.
- `wal_log_hints` đã bật trên cluster trước khi divergence, hoặc data checksums đã được bật từ initdb.
- `full_page_writes` phải bật.
- Có WAL cần thiết để xác định block changes kể từ checkpoint chung; nếu thiếu, phải có WAL archive hoặc chọn base backup mới.

Kiểm tra điều kiện trước khi chạy. Không bật wal_log_hints sau khi divergence rồi cho rằng nó hồi tố đủ thông tin cho pg_rewind.

### 15.4. Ví dụ pg_rewind

Ví dụ chạy trên host của node cũ đã dừng:

```bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/18/old-primary \
  --source-server='host=new-primary.example.net port=5432 user=rewind_user dbname=postgres'
```

Lệnh yêu cầu source server có quyền đọc các thông tin cần thiết và target data directory đã shutdown. Tùy version, cần cấu hình `--restore-target-wal` hoặc cung cấp WAL archive nếu WAL cần thiết không có trong target.

### 15.5. Sau rewind

1. Cấu hình `standby.signal`.
2. Cập nhật `primary_conninfo` tới primary hiện tại.
3. Cấu hình replication slot phù hợp nếu dùng.
4. Xác minh tablespace paths, extension libraries và permissions.
5. Khởi động node.
6. Kiểm tra `pg_is_in_recovery()` trả true.
7. Kiểm tra WAL receiver, sender và replay LSN.

### 15.6. Khi nào cần base backup mới?

Dùng base backup mới nếu:

- pg_rewind không đủ điều kiện.
- WAL cần thiết đã mất và không có archive.
- Target bị corruption hoặc không xác định được cluster lineage.
- Major version/format không tương thích.
- Muốn tái tạo node sạch theo quy trình chuẩn.

Không cố ép pg_rewind chạy trên hai cluster không cùng lineage.

---

## 16. Điều kiện tương thích và nâng cấp major version

### 16.1. Physical replication không phải major upgrade

Một primary PostgreSQL 17 và standby PostgreSQL 18 không thể stream WAL vật lý trực tiếp như hai minor releases cùng major. WAL record formats và internal catalog/storage structures thay đổi qua major versions.

### 16.2. Lựa chọn nâng cấp

Khi nâng major version, cân nhắc:

- pg_upgrade: nâng cấp data directory theo quy trình hỗ trợ.
- Dump/restore: tạo cluster mới và nạp logical backup.
- Logical replication: đồng bộ changes sang cluster major version mới trong quá trình migration.

Physical replication có thể được dùng sau khi hai node đã cùng major version và cluster lineage phù hợp.

### 16.3. Minor upgrade

Minor releases được thiết kế giữ disk format tương thích, nhưng không nên coi mọi phiên bản minor lệch nhau là được hỗ trợ chính thức. Cập nhật standby trước là hướng an toàn được tài liệu khuyến nghị, rồi cập nhật primary trong maintenance procedure.

### 16.4. Binary packages và extension

Đảm bảo:

- PostgreSQL binaries tương thích với data directory major version.
- Extension shared libraries được cài đúng version/build.
- Custom C modules, preload libraries và background workers có mặt trên standby.
- OS packages, locale libraries và collation providers tương thích.
- Các file cấu hình ngoài PGDATA được quản lý riêng.

### 16.5. Tablespace migration

Nếu cần đổi mount paths giữa primary và standby, physical replication trực tiếp có thể không phù hợp vì WAL mang các tablespace paths theo cluster. Hãy thiết kế mount path tương ứng hoặc chọn phương án migration/restore có khả năng ánh xạ tablespaces rõ ràng.

### 16.6. Ma trận quyết định

| Primary | Standby | Physical replication |
|---|---|---|
| PostgreSQL 18.x | PostgreSQL 18.x | Phù hợp khi các điều kiện format khác khớp |
| PostgreSQL 18.x | PostgreSQL 18.y | Có thể hoạt động, nhưng nên đồng bộ minor releases |
| PostgreSQL 17.x | PostgreSQL 18.x | Không hỗ trợ physical streaming xuyên major |
| 32-bit | 64-bit | Không tương thích |
| Cùng major nhưng data block/build format khác | Khác format | Không tương thích |
| Cùng cluster, base backup đúng, tablespace paths sẵn sàng | Standby | Điều kiện nền tảng phù hợp |

---

## 17. Troubleshooting physical replication

### 17.1. Standby không kết nối được primary

Kiểm tra theo thứ tự:

1. DNS/hostname và network route.
2. Firewall/security group có cho phép port PostgreSQL không.
3. Primary có listen trên interface/port đúng không.
4. pg_hba.conf có rule cho pseudo-database replication và đúng client address không.
5. Role có LOGIN và REPLICATION không.
6. Password/passfile/certificate có hợp lệ không.
7. `max_wal_senders` còn capacity không.
8. `primary_conninfo` có host, port, user và application_name đúng không.

Đọc log của cả hai node; lỗi authentication, connection refused và timeout có nguyên nhân khác nhau.

### 17.2. FATAL: no pg_hba.conf entry for replication connection

Rule pg_hba.conf có thể thiếu database field `replication`, user hoặc địa chỉ IP standby. Kiểm tra thứ tự rule vì PostgreSQL dùng rule đầu tiên khớp.

Sau chỉnh sửa, reload cấu hình:

```sql
SELECT pg_reload_conf();
```

### 17.3. requested WAL segment has already been removed

Standby cần một WAL segment đã bị recycle/xóa trên primary. Các hướng xử lý:

- Kiểm tra WAL archive có segment đó không và `restore_command` có hoạt động không.
- Kiểm tra replication slot có bị invalidated hoặc mất WAL không.
- Nếu không còn WAL liên tục, tạo base backup mới.

Không copy một segment bất kỳ từ cluster khác vào pg_wal. WAL phải thuộc đúng system identifier/timeline và liên tục theo recovery history.

### 17.4. Standby nhận WAL nhưng replay chậm

Nếu receive LSN tăng nhưng replay LSN không theo kịp:

- Kiểm tra storage read/write latency trên standby.
- Kiểm tra CPU và I/O contention.
- Xem recovery conflicts và query lâu trên hot standby.
- Kiểm tra WAL record rate từ primary.
- Xem standby có đủ tài nguyên để replay workload không.

Tăng WAL sender count không giải quyết bottleneck replay.

### 17.5. Standby lag tăng dần

So sánh:

- Primary current LSN.
- Sent/write/flush/replay LSN.
- Network throughput/packet loss.
- Standby storage throughput.
- WAL generation rate.

Nếu gap giữa current và sent tăng, primary/network sender có thể là bottleneck. Nếu sent gần receive nhưng replay lag lớn, tập trung vào standby apply.

### 17.6. pg_wal trên primary tăng nhanh

Kiểm tra:

- Replication slots inactive/lagging.
- `restart_lsn` của slot.
- `max_slot_wal_keep_size`.
- Archive command failures.
- Standby không kết nối.
- Backup/replication consumers khác.

Không xóa thủ công các WAL files đang cần cho recovery/replication.

### 17.7. Tablespace path missing

Standby có thể lỗi replay nếu mount point tablespace không tồn tại hoặc permission sai. Đối chiếu `pg_tablespace_location()` trên primary, symlinks trong `pg_tblspc` trên standby và mount configuration.

### 17.8. Standby bị cancel query do recovery conflict

Nếu hot standby query bị cancel:

- Xem `pg_stat_database_conflicts`.
- Kiểm tra query age và wait events.
- Đánh giá `max_standby_streaming_delay` và `max_standby_archive_delay`.
- Cân nhắc `hot_standby_feedback` nếu phù hợp.
- Theo dõi bloat trên primary nếu bật feedback.

Không tăng delay vô hạn mà không đánh giá WAL replay lag và disk growth.

### 17.9. WAL receiver không xuất hiện

Kiểm tra:

- File `standby.signal` có ở đúng data directory không.
- `primary_conninfo` có được đọc không.
- Server có khởi động đúng cluster không.
- Standby có đang replay WAL archive trước khi bắt đầu streaming không.
- Logs có authentication/network error không.

Nếu node đã được promote, nó không còn là standby và không có WAL receiver theo topology cũ.

### 17.10. Base backup thất bại

Kiểm tra:

- Data directory có đúng trạng thái trống/đích không.
- Role có quyền replication.
- Số WAL sender slots đủ cho streaming backup.
- Replication slot name có trùng không.
- Dung lượng destination và tablespace mounts.
- Network timeout và logs.

Xóa/di chuyển artifact dở dang theo quy trình, rồi chạy lại vào destination sạch. Không tiếp tục khởi động một base backup chưa hoàn chỉnh như cluster hợp lệ.

---

## 18. Vận hành và bảo trì physical standby

### 18.1. Theo dõi sức khỏe thường xuyên

Thiết lập cảnh báo cho:

- Standby không còn streaming.
- Receive/replay lag vượt ngưỡng.
- WAL slot giữ quá nhiều dung lượng.
- Archive command lỗi.
- Filesystem gần đầy.
- Recovery conflict tăng bất thường.
- Standby restart hoặc timeline thay đổi.

### 18.2. Kiểm tra tương thích trước thay đổi

Trước minor upgrade, OS upgrade, extension upgrade, thay tablespace hoặc đổi storage:

1. Kiểm tra PostgreSQL major/minor versions.
2. Xác nhận data/WAL build settings.
3. Xác nhận hardware architecture.
4. Kiểm tra tablespace mount paths.
5. Kiểm tra extension libraries và preload modules.
6. Xem release notes và compatibility notes.
7. Lập kế hoạch cập nhật standby trước primary nếu là minor release.

### 18.3. Thêm standby mới

Quy trình:

1. Chuẩn bị host, storage và mount paths.
2. Cài PostgreSQL cùng major/build tương thích.
3. Tạo replication role/pg_hba rules.
4. Cấu hình sender/slot capacity và retention.
5. Chạy pg_basebackup.
6. Cấu hình primary_conninfo, slot, archive.
7. Khởi động standby.
8. Xác minh streaming, receive/replay và system identifier.
9. Thêm vào monitoring/alerting.

### 18.4. Decommission standby

1. Chuyển read traffic sang node khác nếu có.
2. Dừng standby theo quy trình.
3. Xác nhận slot không còn cần.
4. Xóa slot trên upstream khi an toàn.
5. Gỡ cấu hình HA/monitoring/DNS.
6. Thu hồi replication credentials.
7. Xử lý data directory theo retention/security policy.

### 18.5. Backup cho primary và standby

Standby không thay thế backup. Nếu primary và standby cùng nhận DELETE nhầm hoặc corruption logic, cả hai có thể cùng mang trạng thái sai. Cần backup độc lập, WAL archive và restore drills.

### 18.6. Read scaling

Hot standby có thể phục vụ read-only queries, nhưng:

- Đọc từ standby có thể stale so với primary.
- Long-running queries có thể xung đột với recovery.
- Read workload làm giảm tài nguyên dành cho WAL replay.
- Các transaction read-only không được ghi dữ liệu vào standby.

Ứng dụng cần chấp nhận replication lag và xử lý read-after-write routing rõ ràng.

### 18.7. Failover drill

Thử nghiệm định kỳ trong lab/staging:

- Mất primary.
- Chọn standby theo LSN/policy.
- Fencing primary cũ.
- Promote standby.
- Kiểm tra dữ liệu và application connectivity.
- Rewind/rebuild node cũ.
- Đo RTO và xác định RPO thực tế.

Chỉ khi đã kiểm thử, runbook failover mới phản ánh behavior của topology đang triển khai.

---

## 19. Những hiểu lầm thường gặp

**1. “Physical replication gửi câu SQL từ primary sang standby.”** Sai. Nó truyền WAL records ở cấp vật lý.

**2. “Có thể physical replicate một bảng riêng lẻ.”** Không. Physical standby nhận WAL cho toàn cluster.

**3. “Standby có thể dùng major version mới hơn primary.”** Không trong physical streaming thông thường. Hai node cần cùng major version.

**4. “Minor version khác nhau luôn được hỗ trợ.”** Không. Minor disk format được giữ tương thích theo chính sách, nhưng tài liệu khuyến nghị cùng release level và không cam kết chính thức mọi tổ hợp.

**5. “Hai máy phải cùng model CPU.”** Không. Hardware không cần giống hệt, nhưng kiến trúc phần cứng phải tương thích; 32-bit và 64-bit không thể physical log ship với nhau.

**6. “Khác OS luôn hoạt động vì WAL là bytes.”** Sai. Data/WAL format phụ thuộc architecture/build; cần môi trường tương thích và nên giữ OS/build tương đồng.

**7. “Chỉ cần cùng major version là đủ.”** Chưa đủ. Cần đúng cluster lineage, data/WAL format, tablespace paths, extension libraries và các điều kiện vận hành khác.

**8. “Một cluster initdb độc lập có thể nối vào primary.”** Không. Standby cần base backup thuộc cùng system identifier/cluster lineage.

**9. “Copy data directory bằng cp khi primary đang chạy tương đương base backup.”** Sai. File copy thông thường không bảo đảm consistency; dùng pg_basebackup hoặc backup method được hỗ trợ.

**10. “Streaming replication mặc định synchronous.”** Sai. Mặc định là asynchronous.

**11. “Primary luôn đợi standby trước khi trả COMMIT.”** Không. Chỉ synchronous replication với policy tương ứng mới chờ remote acknowledgement.

**12. “Synchronous replication tự chọn mọi standby trong topology.”** Không. Primary chọn standby trực tiếp theo synchronous_standby_names; cascading downstream không được primary chọn trực tiếp.

**13. “Replication slot làm WAL retention không có rủi ro.”** Sai. Slot inactive có thể giữ WAL tới khi filesystem đầy.

**14. “wal_keep_size giữ mọi WAL cần thiết vô thời hạn.”** Không. Nó chỉ đặt mức tối thiểu.

**15. “Nếu standby lag, chỉ cần tăng max_wal_senders.”** Không. Bottleneck có thể là network, storage hoặc replay.

**16. “Receive LSN bằng replay LSN luôn luôn.”** Không. Standby có thể nhận WAL nhanh hơn khả năng replay.

**17. “pg_last_xact_replay_timestamp() luôn đo lag chính xác.”** Không. Khi primary idle, timestamp cũ không có nghĩa standby tụt.

**18. “Một standby streaming tự động failover khi primary chết.”** Không. Promotion/fencing/endpoint orchestration cần operator hoặc HA manager.

**19. “Có thể bật standby cũ lại làm primary sau failover.”** Không an toàn. Hai timeline có thể diverge; cần pg_rewind hoặc base backup mới.

**20. “pg_rewind luôn có thể chạy.”** Không. Nó có điều kiện về common history, clean shutdown, WAL, wal_log_hints/data checksums và full_page_writes.

**21. “WAL archive thay thế replication slot trong mọi tình huống.”** Không. Archive cần đầy đủ segments liên tục và consumer phải có restore_command đúng.

**22. “Standby hot standby không ảnh hưởng primary.”** Có thể ảnh hưởng qua WAL retention, slot và hot_standby_feedback.

**23. “Synchronous standby đồng nghĩa có backup.”** Không. Nó replicate cả thao tác xóa nhầm và corruption logic.

**24. “Physical replication có thể dùng để major upgrade.”** Không. Dùng pg_upgrade, dump/restore hoặc logical replication.

**25. “Có row trong pg_stat_replication nghĩa standby khỏe.”** Chưa đủ. Xem state, LSN gaps, sync_state, logs và disk/network.

---

## 20. Bài tập thực hành và đáp án

### Bài 1 — Physical replication

**Câu hỏi:** Physical replication truyền loại dữ liệu nào?

**Đáp án:** WAL records ở cấp vật lý để standby replay và tái tạo data files.

### Bài 2 — Scope

**Câu hỏi:** Có thể physical replicate riêng schema sales không?

**Đáp án:** Không. Physical replication áp dụng cho toàn cluster.

### Bài 3 — Version

**Câu hỏi:** Primary PostgreSQL 17 và standby PostgreSQL 18 có thể stream WAL trực tiếp không?

**Đáp án:** Không. Physical replication cần cùng major version.

### Bài 4 — Architecture

**Câu hỏi:** Có thể stream từ 32-bit primary sang 64-bit standby không?

**Đáp án:** Không. Hardware architecture phải tương thích.

### Bài 5 — Tablespace

**Câu hỏi:** Vì sao standby cần mount path tablespace tương ứng?

**Đáp án:** Tablespace paths được truyền nguyên dạng trong physical recovery; standby cần các đường dẫn đó tồn tại và có quyền phù hợp.

### Bài 6 — System identifier

**Yêu cầu:** Kiểm tra system identifier.

```sql
SELECT system_identifier FROM pg_control_system();
```

### Bài 7 — wal_level

**Câu hỏi:** Giá trị nào phù hợp cho physical streaming replication?

**Đáp án:** replica hoặc logical; minimal không đủ cho standby.

### Bài 8 — Replication role

**Yêu cầu:** Tạo role replication.

```sql
CREATE ROLE replicator LOGIN REPLICATION PASSWORD 'replace-with-secret';
```

### Bài 9 — pg_hba

**Yêu cầu:** Cho phép standby 10.20.0.12 kết nối TLS.

```conf
hostssl replication replicator 10.20.0.12/32 scram-sha-256
```

### Bài 10 — Base backup

**Yêu cầu:** Viết lệnh tạo standby từ primary và stream WAL.

```bash
pg_basebackup \
  --host=primary.example.net \
  --username=replicator \
  --pgdata=/var/lib/postgresql/18/main \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf
```

### Bài 11 — standby.signal

**Câu hỏi:** File nào báo server khởi động ở standby mode?

**Đáp án:** `standby.signal` trong data directory.

### Bài 12 — primary_conninfo

**Câu hỏi:** application_name dùng để làm gì?

**Đáp án:** Nhận diện standby trên primary và khớp tên trong synchronous_standby_names.

### Bài 13 — Receive/replay

**Câu hỏi:** Receive LSN tăng nhưng replay LSN đứng yên gợi ý điều gì?

**Đáp án:** Standby nhận WAL nhưng replay bị chậm hoặc bị chặn; kiểm tra I/O, CPU, recovery conflicts và logs.

### Bài 14 — Streaming mặc định

**Câu hỏi:** Streaming replication mặc định synchronous hay asynchronous?

**Đáp án:** Asynchronous.

### Bài 15 — Replication slot

**Yêu cầu:** Tạo physical slot.

```sql
SELECT * FROM pg_create_physical_replication_slot('standby_a');
```

### Bài 16 — Slot inactive

**Câu hỏi:** Vì sao slot inactive có thể làm đầy đĩa?

**Đáp án:** Slot giữ WAL cần thiết cho consumer ngay cả khi consumer không kết nối.

### Bài 17 — WAL retention

**Câu hỏi:** wal_keep_size có phải giới hạn WAL cần giữ chính xác cho từng standby không?

**Đáp án:** Không. Đây là mức tối thiểu; slot hoặc archive cần thiết để bảo đảm catch-up dài hơn.

### Bài 18 — Synchronous commit

**Câu hỏi:** synchronous_commit=on cần cấu hình nào để chờ remote standby?

**Đáp án:** synchronous_standby_names phải chỉ định standby phù hợp đang streaming.

### Bài 19 — FIRST/ANY

**Yêu cầu:** Chờ hai trong ba standby theo quorum.

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

### Bài 20 — Monitoring

**Yêu cầu:** Xem sender state và sync_state.

```sql
SELECT application_name, state, sync_state,
       sent_lsn, write_lsn, flush_lsn, replay_lsn
FROM pg_stat_replication;
```

### Bài 21 — Standby receiver

**Yêu cầu:** Xem receiver state.

```sql
SELECT status, sender_host, written_lsn, flushed_lsn
FROM pg_stat_wal_receiver;
```

### Bài 22 — Lag

**Câu hỏi:** Vì sao timestamp replay có thể cũ dù standby caught up?

**Đáp án:** Nếu primary không có transaction mới, timestamp commit cuối cùng vẫn cũ; cần so sánh LSN và WAL activity.

### Bài 23 — Promote

**Yêu cầu:** Promote standby trong lab.

```sql
SELECT pg_promote(wait => true);
```

### Bài 24 — Split brain

**Câu hỏi:** Việc gì phải bảo đảm trước khi promote?

**Đáp án:** Primary cũ phải bị fencing/cô lập để không thể tiếp tục nhận writes.

### Bài 25 — Timeline

**Câu hỏi:** Vì sao PostgreSQL tạo timeline mới sau promotion?

**Đáp án:** Để đánh dấu nhánh WAL history mới sau điểm phân kỳ.

### Bài 26 — pg_rewind

**Câu hỏi:** Nêu hai điều kiện quan trọng để pg_rewind chạy.

**Đáp án:** Target shutdown sạch và wal_log_hints đã bật trước divergence hoặc data checksums đã bật; full_page_writes phải on và WAL cần thiết phải có.

### Bài 27 — Reinitialize

**Câu hỏi:** Khi nào cần base backup mới?

**Đáp án:** Khi thiếu WAL cần thiết, không đủ điều kiện pg_rewind, target corruption hoặc cluster lineage không khớp.

### Bài 28 — Cascading

**Câu hỏi:** Primary có thể trực tiếp chờ standby downstream sau một cascading standby không?

**Đáp án:** Không. Primary chỉ chọn synchronous standbys kết nối trực tiếp.

### Bài 29 — Major upgrade

**Câu hỏi:** Nêu ba cách nâng major version.

**Đáp án:** pg_upgrade, dump/restore hoặc logical replication.

### Bài 30 — Backup

**Câu hỏi:** Physical standby có thay thế backup độc lập không?

**Đáp án:** Không. Standby replicate cả lỗi logic và xóa nhầm; cần backup và restore test.

---

## 21. Checklist triển khai và vận hành

### Tương thích

1. Xác nhận primary và standby cùng major version.
2. Lập kế hoạch cập nhật minor releases và ưu tiên standby trước.
3. Xác nhận hardware architecture tương thích.
4. Kiểm tra PostgreSQL build/data-format settings.
5. Chuẩn bị tablespace mount paths giống nhau.
6. Xác nhận system identifier/cluster lineage từ base backup.
7. Cài extension libraries và custom modules phù hợp.

### Primary

8. Đặt wal_level=replica hoặc logical.
9. Cấu hình max_wal_senders và max_replication_slots.
10. Thiết kế wal_keep_size, slots và max_slot_wal_keep_size.
11. Cấu hình archive_mode/archive_command nếu cần.
12. Cấu hình listen_addresses, firewall và pg_hba.conf.
13. Tạo role REPLICATION chuyên dụng và bảo vệ credentials.
14. Xác nhận TLS/authentication từ standby.

### Standby

15. Tạo base backup bằng pg_basebackup.
16. Chọn WAL method phù hợp và đủ sender connections.
17. Tạo/đặt slot đúng node nếu sử dụng.
18. Xác nhận standby.signal và primary_conninfo.
19. Xác nhận tablespace paths và filesystem permissions.
20. Khởi động và kiểm tra pg_is_in_recovery().
21. Xác nhận pg_stat_wal_receiver và pg_stat_replication.

### Monitoring/HA

22. Theo dõi sent/write/flush/replay LSN.
23. Theo dõi receive/replay lag và WAL generation rate.
24. Theo dõi slot retention và disk usage.
25. Theo dõi archive failures và recovery conflicts.
26. Đặt alert khi standby disconnected hoặc lag vượt ngưỡng.
27. Kiểm thử failover, fencing và promote.
28. Rewind/rebuild node cũ theo runbook.
29. Kiểm thử restore backup độc lập.
30. Ghi lại RPO/RTO thực tế từ failover drills.

---

## 22. Tổng kết

Physical replication trong PostgreSQL dùng WAL để tái tạo trạng thái vật lý của toàn cluster trên standby. Base backup cung cấp điểm khởi đầu nhất quán; streaming hoặc archive đưa WAL mới tới standby; recovery process replay WAL để giữ bản sao cập nhật.

Các điểm cần nhớ:

- Physical replication sao chép WAL ở cấp vật lý, không sao chép SQL và không chọn lọc từng bảng.
- Standby cần base backup của đúng cluster/system identifier.
- Primary và standby phải cùng major version, cùng hardware architecture tương thích và data/WAL formats tương thích.
- Minor releases khác nhau có thể hoạt động nhưng nên đồng bộ và cập nhật standby trước.
- Tablespace mount paths được truyền nguyên dạng; cần chuẩn bị trên standby.
- Replication slots giữ WAL nhưng có thể làm đầy đĩa; kết hợp retention limits và archive monitoring.
- Streaming mặc định asynchronous; synchronous replication tăng durability nhưng có thể chặn commit khi không có standby đáp ứng.
- Receive lag và replay lag là hai vấn đề khác nhau.
- Promotion tạo timeline mới; fencing ngăn split brain.
- Primary cũ cần pg_rewind hoặc base backup mới trước khi trở lại standby.
- Standby không thay backup độc lập, WAL archive hoặc restore tests.

**Câu hỏi tự kiểm tra:** Nếu primary đang chạy PostgreSQL 18 trên máy 64-bit và standby chạy PostgreSQL 17 trên máy 64-bit, vì sao kết nối streaming vẫn không thể tạo physical replica? Điều kiện major version quan trọng vì WAL và storage formats phải được hiểu giống nhau; kiến trúc phần cứng tương thích không thể bù cho khác biệt major version. Khi dựng node mới, hãy dùng base backup từ đúng primary, kiểm tra tablespace paths và xác minh WAL receive/replay trước khi đưa standby vào HA topology.

### Tài liệu PostgreSQL chính thức

- [Log-Shipping Standby Servers — Planning and Standby Operation](https://www.postgresql.org/docs/current/warm-standby.html).
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION).
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION).
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html).
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html).
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html).
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html).
- [WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html).
- [Monitoring Statistics — Replication Views](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html).
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html).
