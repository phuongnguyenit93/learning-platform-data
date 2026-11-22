# Giám sát WAL, archive, replication slot và độ trễ sao chép trong PostgreSQL

PostgreSQL dùng Write-Ahead Log (WAL) để phục hồi database sau crash và truyền thay đổi từ primary tới standby. Trong production, chỉ nhìn thấy một standby có trạng thái `streaming` chưa đủ để kết luận hệ thống an toàn. WAL có thể được tạo nhanh hơn khả năng truyền hoặc replay; archive có thể ngừng hoạt động; replication slot có thể giữ quá nhiều WAL; filesystem `pg_wal` có thể đầy; và các chỉ số lag có thể gây hiểu nhầm khi workload tạm ngừng ghi.

Giám sát WAL cần trả lời bốn câu hỏi: primary đang tạo WAL với tốc độ nào, WAL đã được archive tới đâu, replication consumers đang giữ lại bao nhiêu WAL, và mỗi standby đã nhận/ghi/flush/replay tới vị trí nào. Các câu hỏi này liên quan nhưng không đồng nhất. WAL archive phục vụ backup/PITR và khôi phục sau gián đoạn; replication slot giữ WAL cần thiết cho một consumer; streaming replication chuyển WAL trực tiếp; lag đo khoảng cách giữa các vị trí trong WAL stream.

Bài học thuộc chương **Giám sát** của module *Database Engine Relational PostgreSQL*. Chúng ta sẽ đi từ cấu trúc WAL và archive đến catalog views, truy vấn SQL, metrics, cảnh báo, capacity planning, troubleshooting và bài lab vận hành. Tên cột và hàm có thể thay đổi theo major version; ví dụ tập trung vào PostgreSQL hiện đại và cần đối chiếu manual đúng phiên bản trước khi triển khai.

> **Nguyên tắc vận hành:** Theo dõi riêng WAL generation, archive progress, slot retention và replication progress. Không dùng một con số “replication lag” để đại diện cho tất cả các lớp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vai trò WAL trong crash recovery, replication và PITR.
2. Phân biệt WAL generated, written, flushed, sent, received và replayed.
3. Hiểu segment files, timeline history và archive status files.
4. Cấu hình và theo dõi WAL archiving bằng `archive_mode`, `archive_command` hoặc `archive_library`.
5. Giải thích vai trò của `archive_timeout` và `pg_switch_wal()`.
6. Đọc các chỉ số trong `pg_stat_archiver`.
7. Phân biệt archive failure, archive backlog và WAL retention.
8. Kiểm tra archive queue qua archive status directory khi phiên bản hỗ trợ.
9. Phân biệt physical và logical replication slots.
10. Đọc `restart_lsn`, `confirmed_flush_lsn`, `catalog_xmin` và slot status.
11. Ước lượng lượng WAL một slot đang giữ.
12. Hiểu tác động của `max_slot_wal_keep_size`, `wal_keep_size` và `max_wal_size`.
13. Theo dõi WAL sender bằng `pg_stat_replication`.
14. Theo dõi WAL receiver bằng `pg_stat_wal_receiver`.
15. Đo khoảng cách sent/write/flush/replay theo bytes.
16. Diễn giải các lag time fields và giới hạn của chúng.
17. Ước lượng WAL generation rate bằng `pg_stat_wal`.
18. Theo dõi logical replication consumers và slot inactivity.
19. Thiết kế alerts cho archive, slots, disk capacity và replication lag.
20. Xử lý archive command lỗi, slot giữ WAL, standby lag và WAL disk tăng.
21. Xây dựng retention policy cho archive và replication slots.
22. Thực hiện lab đo WAL, kiểm tra archive và mô phỏng slot backlog.
23. Lập dashboard và runbook giám sát WAL trong production.

## 2. WAL là gì và tại sao phải giám sát?

WAL ghi lại các thay đổi cần thiết để PostgreSQL có thể phục hồi database sau crash. Trước khi data pages được ghi xuống data files, WAL records tương ứng phải được ghi bền vững theo durability policy. Khi server khởi động lại, recovery đọc WAL để đưa data files về trạng thái nhất quán.

WAL còn được dùng cho:
- Physical streaming replication.
- WAL archiving và Point-in-Time Recovery (PITR).
- Logical decoding và logical replication.
- Một số hoạt động backup/recovery và replication tooling.

### 2.1. WAL generation

Mỗi transaction thay đổi dữ liệu có thể tạo WAL records. Khối lượng WAL phụ thuộc workload, index updates, full-page images, checkpoint timing, bulk operations, `wal_level`, `wal_compression` và nhiều yếu tố khác.

### 2.2. WAL segment

WAL được lưu thành các segment files trong thư mục `pg_wal`. Kích thước segment thường được khởi tạo khi tạo cluster và phổ biến là 16 MB, nhưng có thể khác nếu cluster được tạo với cấu hình khác. Không hardcode kích thước segment trong monitoring nếu chưa xác nhận cluster.

### 2.3. WAL LSN

Log Sequence Number (LSN) biểu diễn vị trí trong WAL stream. Một LSN có thể dùng để so sánh tiến độ giữa primary và standby trong cùng timeline/stream.

Trên primary:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_flush_lsn() AS flushed_lsn;
```

### 2.4. WAL không phải row change log dễ đọc

WAL là định dạng nội bộ phục vụ recovery/replication. Không dùng cách đọc file WAL thô như một audit log business. Logical decoding hoặc application audit events phù hợp hơn nếu cần diễn giải thay đổi ở mức nghiệp vụ.

### 2.5. Vì sao WAL cần monitoring riêng?

WAL là tài nguyên có thể tăng nhanh và ảnh hưởng trực tiếp đến availability:
- Archive không hoạt động có thể khiến WAL không được recycle.
- Replication slot bị bỏ quên có thể giữ WAL lâu dài.
- Standby chậm có thể tích tụ backlog.
- WAL disk đầy có thể khiến primary không tiếp tục ghi được.
- Archive thiếu segment có thể làm PITR hoặc standby recovery thất bại.

## 3. Các trạng thái WAL cần phân biệt

Một WAL record/segment có thể đi qua các mốc:

```text
Primary transaction
      |
      v
 WAL generated
      |
      +---- local write / flush
      |
      +---- WAL sender ----> standby receive
      |                         |
      |                         v
      |                      write
      |                         |
      |                         v
      |                      flush
      |                         |
      |                         v
      |                      replay
      |
      +---- completed segment ----> archive
```

- **Generated:** WAL records được tạo bởi backend và background operations.
- **Written:** WAL bytes được ghi qua hệ điều hành; written chưa chắc durable.
- **Flushed:** WAL đã được flush theo durability semantics của OS/storage.
- **Sent:** WAL sender đã gửi một phần WAL tới standby.
- **Received:** standby đã nhận WAL qua network; nhận chưa có nghĩa đã ghi hoặc flush.
- **Written/Flushed on standby:** standby ghi và flush WAL vào storage.
- **Replayed:** recovery process apply WAL vào data files.
- **Archived:** segment hoàn tất đã được chuyển thành công tới archive destination.

Archive tiến theo segment files, không phải mỗi transaction commit được upload thành một object riêng.

## 4. Các vị trí và hàm LSN thường dùng

Trên primary:

| Hàm | Ý nghĩa |
|---|---|
| `pg_current_wal_lsn()` | WAL insert/current position |
| `pg_current_wal_insert_lsn()` | Vị trí WAL đã insert |
| `pg_current_wal_flush_lsn()` | Vị trí WAL đã flush |
| `pg_wal_lsn_diff(a, b)` | Khoảng cách bytes giữa hai LSN |

Trên standby:

| Hàm | Ý nghĩa |
|---|---|
| `pg_last_wal_receive_lsn()` | LSN nhận gần nhất |
| `pg_last_wal_replay_lsn()` | LSN replay gần nhất |
| `pg_last_xact_replay_timestamp()` | Thời điểm transaction cuối cùng được replay |
| `pg_is_in_recovery()` | Cho biết instance đang ở recovery/standby mode |

### 4.1. LSN chỉ so sánh đúng trong cùng history

Khi failover tạo timeline mới, không tùy tiện so sánh LSN giữa hai histories mà bỏ qua timeline history. LSN là vị trí WAL, còn timeline xác định nhánh lịch sử.

### 4.2. LSN difference theo bytes

```sql
SELECT
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        '0/5000000'
    ) AS bytes_since_position;
```

Giá trị là khoảng cách byte, có thể là numeric. Dùng LSN thực tế từ cùng cluster/timeline.

### 4.3. NULL là trạng thái cần xử lý

Các hàm receive/replay có thể trả NULL nếu standby chưa nhận/replay WAL hoặc chưa có transaction phù hợp. Monitoring cần biểu diễn “chưa có dữ liệu” riêng, không ép NULL thành zero.

## 5. WAL directory và archive status

Trong data directory, PostgreSQL quản lý:
- `pg_wal`: WAL segments hiện tại, segments được recycle và một số trạng thái liên quan.
- `pg_wal/archive_status`: trạng thái segment cần archive hoặc đã archive.
- Các file timeline history và metadata phục vụ recovery.

### 5.1. .ready và .done

Khi segment đủ điều kiện archive, PostgreSQL tạo marker `.ready` trong archive status directory. Sau khi archive command/library báo thành công, marker được chuyển thành `.done`.

`.ready` biểu thị file cần được archiver xử lý; `.done` biểu thị archive đã được xác nhận thành công theo cơ chế PostgreSQL.

### 5.2. Không xóa marker bằng tay

Không xóa `.ready` hoặc đổi tên `.done` thủ công để “dọn backlog”. Có thể khiến PostgreSQL bỏ qua segment cần archive hoặc lặp archive sai cách. Xử lý nguyên nhân bằng archive mechanism và retention policy.

### 5.3. Archive destination

Destination có thể là local filesystem, network filesystem, object storage hoặc hệ thống backup. Cần bảo đảm:
- Tên WAL file không bị ghi đè sai.
- Upload atomic/immutable theo semantics phù hợp.
- Archive success chỉ được báo khi object thực sự sẵn sàng.
- Quyền truy cập và credential không bị hết hạn.
- Có monitoring dung lượng, request failures và latency.

## 6. WAL archiving hoạt động thế nào?

Khi bật archiving, PostgreSQL gọi archiver process để chuyển các WAL segments đã hoàn tất tới archive destination.

Các cấu hình chính:
- `archive_mode`
- `archive_command` hoặc `archive_library`
- `archive_timeout`

### 6.1. archive_mode

Các giá trị phổ biến:
- `off`: không archive WAL.
- `on`: archive WAL trên primary.
- `always`: archive cả WAL nhận được trong recovery/standby, phù hợp một số cascading/backup topologies.

`archive_mode` là tham số cần restart để thay đổi. Kiểm tra `pg_settings.context` và manual của major version đang chạy.

### 6.2. archive_command

`archive_command` là shell command được PostgreSQL gọi với placeholder:
- `%p`: path tới WAL file nguồn.
- `%f`: tên file WAL cần archive.

Ví dụ minh họa cho filesystem destination:

```conf
archive_mode = on
archive_command = '/usr/local/bin/archive-wal "%p" "%f"'
archive_timeout = '60s'
```

Script `/usr/local/bin/archive-wal` là ví dụ do hệ thống vận hành cung cấp. Script cần nhận source path và file name, copy/upload file hoàn chỉnh, kiểm tra thành công và trả exit code 0 chỉ khi archive object sẵn sàng.

### 6.3. Archive command phải idempotent

PostgreSQL có thể gọi lại command nếu lần trước thất bại hoặc process bị gián đoạn. Script cần xử lý trường hợp file đích đã tồn tại:
- Nếu file đích giống hệt source, có thể trả success.
- Nếu file đích khác nội dung, phải báo lỗi và giữ evidence.
- Không ghi đè âm thầm một object archive khác.
- Với filesystem, có thể copy vào temporary file rồi rename atomic trên cùng filesystem.
- Với object storage, dùng upload/commit semantics phù hợp và xác minh object hoàn chỉnh.

### 6.4. Không trả success quá sớm

Nếu script chỉ enqueue upload vào background rồi trả 0, PostgreSQL có thể đánh dấu segment archived trong khi upload thực tế chưa hoàn tất. Nếu worker upload chết, archive bị thiếu mà database nghĩ đã thành công.

### 6.5. archive_library

Các phiên bản PostgreSQL hiện đại có thể hỗ trợ `archive_library` thay cho `archive_command`. Library cung cấp archiving implementation qua extension/module. Không cấu hình đồng thời hai cơ chế trái với quy định của version; kiểm tra tài liệu phiên bản và trạng thái effective.

### 6.6. Archive command chạy dưới quyền OS của PostgreSQL

Script cần quyền đọc WAL file và ghi archive destination. Không cấp quyền rộng hơn cần thiết. Bảo vệ credentials và tránh đưa secret vào command line/log.

## 7. archive_timeout và WAL segment switch

Archiver chỉ xử lý segment đã hoàn tất. Với workload thấp, segment hiện tại có thể chưa đầy trong thời gian dài, làm archive mới chậm dù không có lỗi.

### 7.1. archive_timeout

`archive_timeout` buộc PostgreSQL chuyển segment sau một khoảng thời gian có WAL activity, giúp segment được archive sớm hơn trong workload thưa.

```conf
archive_timeout = '60s'
```

### 7.2. Timeout không phải upload deadline

`archive_timeout` không có nghĩa object archive sẽ xuất hiện chính xác sau 60 giây. Archiver còn phụ thuộc segment completion, process scheduling, archive destination và retry.

### 7.3. Segment có thể được archive với phần dữ liệu chưa đầy

Forced switch có thể tạo nhiều segment archive chưa dùng hết dung lượng, tăng số objects và overhead. Chọn timeout theo RPO/PITR freshness, chi phí storage và archive system capacity.

### 7.4. pg_switch_wal()

Trên primary, có thể chủ động yêu cầu switch sang WAL segment mới:

```sql
SELECT pg_switch_wal();
```

Lệnh này hữu ích trong lab hoặc sau một batch operation để kiểm tra archive flow. Nó không phải giải pháp thay thế monitoring và không cần chạy liên tục trong production.

### 7.5. Segment switch không đồng nghĩa archive thành công

Sau `pg_switch_wal()`, kiểm tra `pg_stat_archiver`, archive destination và `.ready`/`.done` status. Không kết luận từ kết quả LSN của hàm.

## 8. Monitoring bằng pg_stat_archiver

`pg_stat_archiver` là view thống kê archiver trên instance.

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

- `archived_count`: số lần archive thành công kể từ lần reset statistics gần nhất; đây là counter tích lũy, không phải số WAL đang chờ.
- `last_archived_wal`: tên WAL file được archive thành công gần nhất.
- `last_archived_time`: thời điểm archive thành công gần nhất; nếu workload idle, giá trị cũ không nhất thiết là lỗi.
- `failed_count`: số lần archive command/library báo thất bại. Theo dõi delta counter, không chỉ giá trị tuyệt đối.
- `last_failed_wal` và `last_failed_time`: file gần nhất có archive attempt thất bại và thời điểm.
- `stats_reset`: thời điểm reset statistics; exporter cần theo dõi để tránh tính delta âm hoặc báo lỗi giả.

### 8.1. pg_stat_archiver không cho biết backlog chính xác

View không trực tiếp hiển thị số `.ready` files, bytes đang chờ hoặc age của segment cũ nhất. Cần kết hợp archive status directory, filesystem/object storage metrics và WAL positions.

## 9. Đếm archive backlog

Trên các PostgreSQL versions có hàm `pg_ls_archive_statusdir()`, có thể xem các status files:

```sql
SELECT
    count(*) FILTER (WHERE name LIKE '%.ready') AS ready_files,
    count(*) FILTER (WHERE name LIKE '%.done') AS done_files
FROM pg_ls_archive_statusdir();
```

Hàm và quyền truy cập phụ thuộc major version. Kiểm tra manual và role permissions trước khi dùng trong exporter.

### 9.1. Ready count và ready age

Số `.ready` tăng liên tục có thể chỉ ra archiver không theo kịp, archive destination chậm hoặc command thất bại. Một file `.ready` tồn tại lâu có thể đáng lo hơn nhiều files mới xuất hiện trong một burst ngắn. Theo dõi age của file ready cũ nhất nếu có thể.

### 9.2. Done count

`.done` files không phải backlog. Chúng là trạng thái archive đã hoàn tất và được PostgreSQL quản lý. Không cảnh báo dựa trên số done đơn lẻ.

### 9.3. Đếm file từ OS

Nếu dùng OS exporter, đọc `pg_wal/archive_status` theo quyền được cấp và chỉ lấy file status. Không sửa/xóa file trong quá trình scrape.

## 10. Archive freshness và archive gap

Archive freshness đo thời gian kể từ khi WAL mới nhất được archive thành công. Archive gap đo khoảng cách giữa WAL hiện tại và WAL archive progress gần nhất.

Nếu primary không tạo WAL mới, `last_archived_time` cũ là bình thường. Cần so sánh với WAL generation gần đây, thời điểm segment hiện tại bắt đầu, archive queue `.ready` và backup/PITR SLA.

WAL file name mã hóa timeline và segment position. Để xác định gap, nên dùng công cụ hoặc code hiểu WAL filename/timeline thay vì so sánh chuỗi lexicographic đơn giản.

Sau promotion, PostgreSQL tạo timeline mới và history file. Archive system cần giữ cả WAL segments và timeline history files để recovery có thể đi theo nhánh đúng. Có thể còn gap ở giữa do một segment bị thiếu, dù object mới nhất vẫn tồn tại. Archive validation cần kiểm tra continuity từ base backup đến recovery target.

## 11. WAL archive và PITR

WAL archive cho phép replay WAL từ base backup đến một thời điểm mục tiêu.

Một recovery set cần:
- Base backup hợp lệ.
- WAL segments liên tục từ backup đến recovery target.
- Timeline history files liên quan.
- `restore_command`/archive access hoạt động.
- Backup metadata và encryption keys cần thiết.

### 11.1. restore_command

Ví dụ minh họa:

```conf
restore_command = 'cp /srv/pg-archive/%f "%p"'
```

Trong production, command cần trả non-zero khi file không có, xử lý quoting/path an toàn và hỗ trợ archive destination thật. Với object storage, dùng restore helper tương ứng.

### 11.2. Archive completeness

Một archive có hàng triệu objects vẫn có thể thiếu một WAL segment nhỏ. Restore drill là cách xác nhận tính liên tục thực tế.

### 11.3. Archive retention

Không xóa archive chỉ vì file đã được replay bởi một standby. PITR retention cần căn cứ vào backup sets còn được giữ, recovery window, replicas/standbys cần WAL, legal/compliance retention và archive lifecycle policy.

### 11.4. Archive và replication slot độc lập

Archive giữ WAL ngoài instance để recovery/backup; slot ngăn PostgreSQL recycle WAL mà consumer đang cần. Một archive đầy đủ không tự làm standby đang kết nối catch up nếu slot/stream configuration sai; một slot active không thay archive PITR.

## 12. Replication slots là gì?

Replication slot là trạng thái trên primary giữ WAL cần thiết cho một replication consumer. Slot giúp consumer reconnect sau gián đoạn mà không mất phần WAL đã được giữ lại.

Hai nhóm chính:
- Physical replication slot.
- Logical replication slot.

### 12.1. Physical slot

Dùng cho physical standby hoặc physical WAL consumer. `restart_lsn` cho biết WAL position sớm nhất còn cần giữ cho slot.

### 12.2. Logical slot

Dùng cho logical decoding/replication. Logical slot theo dõi tiến độ decoding/consumer và có thể giữ WAL cùng catalog tuples cần thiết.

### 12.3. Slot active/inactive

Slot active đang được một consumer sử dụng. Slot inactive có thể vẫn giữ WAL. Inactive lâu ngày là rủi ro disk growth.

### 12.4. Slot không phải bản sao dữ liệu

Slot chỉ là metadata và retention mechanism. Nó không chứa database rows, không phải backup và không tự archive WAL.

## 13. Tạo và quản lý physical replication slot

Tạo slot:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

Kiểm tra:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Xóa slot chỉ sau khi xác định consumer không còn cần nó:

```sql
SELECT pg_drop_replication_slot('standby_a_slot');
```

Không drop slot đang active hoặc còn được consumer sử dụng. Cần xác nhận standby đã được chuyển sang slot mới hoặc đã được rebuild.

Đặt tên theo cluster/consumer, lưu inventory owner và thời điểm tạo. Tránh slot orphan do consumer bị decommission mà quên cleanup. `pg_basebackup` có options tạo replication slot trong lúc backup; xác nhận slot được tạo đúng, standby dùng đúng `primary_slot_name`, và không để slot tạm inactive vô thời hạn.

Mỗi physical standby cần slot riêng nếu dùng physical slots. Nhiều consumers không nên chia sẻ một slot như một group identifier.

## 14. Xem replication slots

Query cơ bản tương thích rộng:

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    catalog_xmin
FROM pg_replication_slots
ORDER BY slot_name;
```

Một số cột có thể NULL hoặc không áp dụng cho slot type tương ứng.

- `restart_lsn`: WAL trước vị trí này có thể không còn cần cho slot. Nếu nó cũ so với current WAL, slot có thể giữ một lượng WAL lớn.
- `confirmed_flush_lsn`: đặc biệt hữu ích với logical slots; phản ánh vị trí consumer đã xác nhận xử lý. Không diễn giải như physical standby replay position.
- `catalog_xmin`: logical slot có thể giữ lại catalog tuples cần cho decoding. Giá trị cũ có thể cản vacuum cleanup và làm catalog bloat.
- `active`: false không có nghĩa slot vô hại. Slot inactive vẫn có thể giữ WAL tới khi được consumer dùng lại hoặc được cleanup theo policy.

Các PostgreSQL versions hiện đại có thể cung cấp thêm `wal_status`, `safe_wal_size`, `inactive_since`, `invalidation_reason` hoặc các cột khác. Kiểm tra schema của `pg_replication_slots` trên major version đang chạy trước khi viết exporter/query dùng các cột đó.

## 15. Ước lượng WAL mà slot giữ lại

Trên primary, có thể ước lượng khoảng cách giữa current WAL và slot restart position:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    CASE
        WHEN restart_lsn IS NOT NULL
        THEN pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
    END AS retained_wal_bytes
FROM pg_replication_slots
ORDER BY retained_wal_bytes DESC NULLS LAST;
```

### 15.1. Đây là ước lượng theo LSN

Khoảng cách LSN không nhất thiết bằng chính xác số bytes filesystem đang chiếm. WAL segments được giữ theo segment boundaries, có thể gồm files được recycle và các retention constraints khác.

### 15.2. Nhiều slots có thể cùng giữ một vùng WAL

Không cộng retained bytes của mọi slots để suy ra `pg_wal` usage. Nhiều slots có thể cùng cần những segment giống nhau. Xác định oldest required WAL position để hiểu retention floor.

### 15.3. Slot inactive lâu ngày

Một slot inactive với `restart_lsn` cũ là tín hiệu cần điều tra. Tìm consumer owner, last connection, decommission status và khả năng reseed.

### 15.4. Logical slot và catalog retention

Ngoài WAL bytes, logical slots có thể giữ `catalog_xmin`. Theo dõi transaction ID age và vacuum pressure, không chỉ disk usage.

## 16. Giới hạn WAL retention

Các tham số liên quan:
- `max_slot_wal_keep_size`
- `wal_keep_size`
- `max_wal_size`
- `min_wal_size`
- `max_replication_slots`
- `max_wal_senders`

### 16.1. max_slot_wal_keep_size

Giới hạn lượng WAL mà replication slots được phép giữ lại. Nếu slot vượt giới hạn, PostgreSQL có thể recycle WAL cần thiết và slot trở nên không còn sử dụng được cho consumer đó.

Giá trị `-1` có nghĩa không giới hạn bởi tham số này, vì vậy slot bị bỏ quên có thể làm `pg_wal` tăng tới khi hết dung lượng.

### 16.2. wal_keep_size

Giữ một lượng WAL tối thiểu cho standby có thể cần catch up. Đây không phải hard cap và không thay thế slot hoặc archive.

### 16.3. max_wal_size

Là mục tiêu/soft limit cho WAL volume giữa các checkpoints trong điều kiện bình thường. Nó không bảo đảm `pg_wal` không vượt giá trị này khi archive hoặc replication slot giữ WAL.

### 16.4. min_wal_size

Điều khiển mức WAL files PostgreSQL giữ lại để recycle. Không phải dung lượng tối thiểu cần cấp cho filesystem.

### 16.5. max_replication_slots và max_wal_senders

Đảm bảo capacity đủ cho physical/logical consumers, backup clients và connections dự kiến. Quá ít slots/senders có thể khiến consumer mới không kết nối được.

### 16.6. Không chọn limit chỉ theo disk size

Ước lượng peak WAL generation rate, thời gian standby/consumer có thể offline, archive outage tolerance, disk headroom, reseed duration, recovery SLA, số slots và loại consumers.

## 17. Slot invalidation và consumer bị mất WAL

Nếu PostgreSQL recycle WAL mà slot cần, consumer có thể không tiếp tục từ vị trí cũ.

### 17.1. wal_status

Trên các phiên bản hỗ trợ, `wal_status` có thể chỉ ra trạng thái như `reserved`, `extended`, `unreserved` hoặc `lost`. Ý nghĩa chi tiết phụ thuộc phiên bản; `lost` cho biết slot không còn đủ WAL để tiếp tục theo vị trí yêu cầu.

### 17.2. safe_wal_size

Một số versions cung cấp `safe_wal_size` để ước lượng lượng WAL có thể được tạo thêm trước khi slot có nguy cơ vượt giới hạn retention. Không dùng như dự báo tuyệt đối vì WAL generation rate thay đổi.

### 17.3. Consumer không thể bắt kịp

Nếu required WAL đã bị recycle, standby/consumer cần được xử lý theo đúng loại:
- Physical standby: reseed/rebuild từ base backup nếu WAL không còn.
- Logical subscriber: đánh giá slot, consistency và resnapshot/reinitialize theo tool.
- Backup/PITR: tìm archive segment từ WAL archive nếu còn đầy đủ.

### 17.4. Không tạo slot mới để che lỗi

Tạo slot mới tại current WAL không khôi phục WAL đã mất trước đó. Nó chỉ bắt đầu retention từ vị trí mới; consumer cần được reinitialize để có consistency.

## 18. Physical và logical slot: khác nhau ở đâu?

| Tiêu chí | Physical slot | Logical slot |
|---|---|---|
| Consumer | Physical standby/WAL receiver | Logical decoding/subscriber |
| Retention position | `restart_lsn` | `restart_lsn` và `confirmed_flush_lsn` |
| Data format | Physical WAL | Logical changes decoded từ WAL |
| Catalog retention | Thường không giữ catalog_xmin như logical slot | Có thể giữ `catalog_xmin` |
| Consumer recovery | Catch up/reseed standby | Resume decoding hoặc resnapshot |
| Use case | HA/DR standby | CDC, logical replication, integration |

Logical slot có thể giữ WAL dù subscriber dừng. Nếu consumer ngừng lâu và slot còn tồn tại, WAL có thể tích tụ. `catalog_xmin` cũ có thể ngăn cleanup catalog tuples và cần theo dõi transaction ID age/vacuum.

Các khả năng failover-slot và synchronization giữa primary/standby thay đổi theo major version. Nếu dựa vào logical slots qua failover, kiểm tra feature support và configuration của đúng PostgreSQL version/tooling.

## 19. WAL sender và pg_stat_replication

Trên primary, `pg_stat_replication` hiển thị các standbys kết nối trực tiếp.

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    sync_priority,
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

- `state`: có thể gồm startup, catchup và streaming; replication ổn định thường mong đợi streaming.
- `sent_lsn`: vị trí WAL cuối đã gửi tới standby connection.
- `write_lsn`: vị trí standby xác nhận đã ghi WAL tới OS.
- `flush_lsn`: vị trí standby xác nhận đã flush WAL.
- `replay_lsn`: vị trí standby đã replay WAL.
- `sync_state`: async, potential, sync hoặc quorum theo cấu hình.

View này hiển thị các replication connections trực tiếp tới primary. Standbys downstream trong cascading topology không xuất hiện như connection trực tiếp của primary gốc.

## 20. Tính các khoảng cách WAL giữa primary và standby

Ví dụ trên primary:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS sent_to_write_bytes,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS write_to_flush_bytes,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS flush_to_replay_bytes,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS current_to_replay_bytes
FROM pg_stat_replication
WHERE state = 'streaming'
ORDER BY application_name;
```

- **Sent-to-write gap:** có thể phản ánh network/receiver/write pressure. Nếu tăng liên tục, điều tra network throughput, receiver process và standby I/O.
- **Write-to-flush gap:** có thể phản ánh standby flush/storage delay. Đặc biệt quan trọng với synchronous commit `on`.
- **Flush-to-replay gap:** có thể phản ánh recovery/replay bottleneck, CPU/I/O hoặc hot standby query conflicts.
- **Current-to-replay gap:** tổng khoảng cách từ primary current WAL tới standby replay; hữu ích như byte lag nhưng không trực tiếp cho biết thời gian catch-up.

Một số LSN có thể NULL trong startup/disconnected state. Monitoring cần tách `no data`, `not streaming` và `zero lag`.

## 21. Monitoring phía standby bằng pg_stat_wal_receiver

Trên standby:

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

- `status`: trạng thái receiver như streaming hoặc trạng thái kết nối khác. Không có row có thể có nghĩa không có active receiver connection tại thời điểm query.
- `written_lsn` và `flushed_lsn`: theo dõi WAL receiver đã ghi và flush tới đâu.
- `last_msg_receipt_time`: phát hiện receiver không nhận status messages gần đây; cần kết hợp network/primary state.
- `latest_end_lsn`: vị trí cuối cùng receiver biết từ sender.
- Khi receiver disconnect, kiểm tra logs, `primary_conninfo`, credentials, TLS, pg_hba, network và slot configuration.

## 22. Replay lag và timestamp lag

Trên standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_at,
    CASE
        WHEN pg_last_xact_replay_timestamp() IS NULL THEN NULL
        ELSE clock_timestamp() - pg_last_xact_replay_timestamp()
    END AS age_of_last_replayed_transaction;
```

### 22.1. Age không phải replication lag tuyệt đối

Nếu primary không có transaction mới trong 30 phút, standby replay timestamp có thể cũ 30 phút dù standby đã theo kịp hoàn toàn.

### 22.2. Clock skew

Timestamp giữa primary và standby có thể bị ảnh hưởng bởi clock skew. Đồng bộ clocks và không dùng timestamp age như nguồn duy nhất để quyết định failover.

### 22.3. Dùng LSN gap cùng WAL generation rate

Bytes lag và WAL bytes/second giúp ước lượng catch-up time tốt hơn. Tuy nhiên, replay throughput có thể khác WAL generation rate, nên đo thực tế.

### 22.4. Heartbeat transaction

Có thể tạo bảng heartbeat được cập nhật định kỳ trên primary. Standby đọc timestamp/sequence để đo end-to-end visibility. Heartbeat tạo WAL thật, nhưng cần cadence hợp lý và không thay thế LSN monitoring.

## 23. WAL generation rate với pg_stat_wal

Các phiên bản PostgreSQL hiện đại cung cấp `pg_stat_wal`:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
```

- `wal_bytes`: tổng bytes WAL được tạo kể từ lần reset statistics gần nhất. Dùng delta giữa hai lần scrape để ước lượng WAL generation rate.
- `wal_records` và `wal_fpi`: số WAL records và full-page images.
- `wal_buffers_full`: counter liên quan WAL buffers đầy; diễn giải cùng workload/version.
- `wal_write` và `wal_sync`: counters số lần write/sync theo thống kê PostgreSQL.
- `wal_write_time`/`wal_sync_time`: timing có ý nghĩa khi WAL timing statistics được bật theo cấu hình/version.

Exporter nên lấy mẫu theo interval cố định:

```text
wal_rate_bytes_per_second =
    (wal_bytes_now - wal_bytes_previous)
    / elapsed_seconds
```

Nếu `stats_reset` thay đổi hoặc counter giảm, reset baseline thay vì tạo rate âm.

## 24. Ước lượng thời gian catch-up

Một ước lượng đơn giản:

```text
estimated_catchup_seconds =
    outstanding_wal_bytes
    / effective_replay_bytes_per_second
```

Đây chỉ là approximation. Cần đo outstanding WAL bytes, standby receive throughput, standby replay throughput, primary WAL generation rate trong lúc catch-up và network/storage contention.

Nếu generation rate cao hơn replay rate, standby không thể catch up khi workload tiếp tục tạo WAL nhanh hơn tốc độ replay. Cần tăng capacity hoặc giảm workload/lag source. Nếu generation rate thấp hơn replay rate, standby có thể thu hẹp backlog.

Đo riêng receive và replay. Standby có thể nhận WAL nhanh nhưng replay chậm. Nếu chỉ đo network throughput, có thể bỏ sót recovery bottleneck.

Không dùng một threshold bytes cho mọi cluster. 100 MB lag có ý nghĩa khác nhau với cluster tạo 1 MB/s và cluster tạo 500 MB/s. Alert cần kết hợp bytes, time estimate và SLA.

## 25. Logical replication monitoring

Với logical replication, các views khác physical replication.

### 25.1. pg_stat_subscription

Trên subscriber, view này hiển thị worker/subscription state và LSN progress theo version.

```sql
SELECT *
FROM pg_stat_subscription;
```

### 25.2. pg_stat_subscription_stats

Một số versions có thống kê lỗi subscription như apply errors và sync errors. Kiểm tra schema đúng version.

### 25.3. Logical slot trên publisher

Trên publisher, xem `pg_replication_slots` để biết active state, restart_lsn, confirmed_flush_lsn và catalog_xmin.

### 25.4. Logical lag khác physical replay lag

Logical subscriber apply changes theo table/publication semantics. Không so trực tiếp `confirmed_flush_lsn` với physical `replay_lsn` như cùng một metric.

### 25.5. Long-running transaction

Logical decoding có thể cần giữ WAL từ vị trí transaction chưa hoàn tất. Một transaction mở lâu có thể khiến slot restart_lsn không tiến, làm WAL retention tăng.

## 26. Archive và slot retention tương tác ra sao?

WAL có thể bị giữ bởi nhiều lý do:
- Chưa được archive thành công.
- Physical replication slot cần.
- Logical replication slot cần.
- Standby cần theo `wal_keep_size`.
- Backup/recovery operation đang cần.
- WAL chưa thể recycle theo checkpoint/recovery state.

Một consumer có restart position rất cũ có thể giữ các segments mà các consumers khác đã xử lý. Kiểm tra từng slot và archive progress để tìm retention bottleneck.

Nếu archiver thất bại và slot cũng inactive, WAL retention có thể tăng nhanh. Cần alert cả archive failures và slot retained bytes.

Khi WAL bị giữ bởi slot/archive, `max_wal_size` không phải hard ceiling. Filesystem vẫn có thể đầy.

Theo dõi filesystem free bytes/inodes và tổng size của `pg_wal`. Dùng OS metrics hoặc `pg_ls_waldir()` nếu phiên bản/quyền hỗ trợ. Không xóa files trong thư mục này bằng OS command.

## 27. Kiểm tra WAL files qua SQL

Trên các versions hỗ trợ `pg_ls_waldir()` và role có quyền:

```sql
SELECT
    count(*) AS wal_file_count,
    sum(size) AS wal_file_bytes,
    max(modification) AS newest_file_time,
    min(modification) AS oldest_file_time
FROM pg_ls_waldir();
```

Đây không phải toàn bộ filesystem usage. WAL directory có thể chứa các files khác và storage allocation có thể khác logical size. So sánh với OS filesystem metrics.

Listing nhiều files liên tục có thể tạo overhead. Dùng exporter interval phù hợp và giới hạn permissions. WAL directory còn có status files, history files và các files nội bộ; đừng giả định mọi entry đều là segment cần archive.

## 28. Dashboard giám sát WAL

Một dashboard thực tế nên có các panel sau:

**WAL generation**
- WAL bytes/sec.
- WAL records/sec.
- Full-page images/sec.
- WAL write/sync counters và latency.

**Archive**
- `archived_count` rate.
- `failed_count` rate.
- Last archived time.
- Last failed WAL/time.
- Ready file count và oldest ready age.
- Archive destination upload failures/latency.
- Archive storage capacity.

**Replication slots**
- Active/inactive slot count.
- Retained WAL bytes theo slot.
- Oldest restart_lsn.
- Logical catalog_xmin age.
- Slot wal_status/safe_wal_size khi version hỗ trợ.
- Slot owner/consumer identity.

**Physical replication**
- Standby state/sync_state.
- Sent-to-write, write-to-flush, flush-to-replay gaps.
- Current-to-replay bytes.
- Receiver last message time.
- Estimated catch-up time.

**Capacity**
- `pg_wal` filesystem bytes/inodes.
- Archive storage bytes/objects.
- WAL generation forecast.
- Remaining slot headroom.

Mỗi metric nên gắn cluster ID, node name, role, PostgreSQL major version và standby application_name. Tránh trộn số liệu giữa nhiều clusters.

`wal_bytes`, `archived_count`, `failed_count` là counters. Ready files, retained bytes, free disk và lag bytes là gauges. Exporter cần phân biệt để tính rate đúng.

## 29. Alerting: archive

Các cảnh báo gợi ý:

| Alert | Điều kiện tham khảo | Ý nghĩa |
|---|---|---|
| Archive failures increasing | failed_count delta tăng | Command/library/destination lỗi |
| Archive stalled | Có WAL activity nhưng last archive quá cũ | Archiver không theo kịp |
| Ready backlog growing | .ready count/oldest age tăng liên tục | Archive queue bị nghẽn |
| Archive destination unavailable | Object store/filesystem errors | WAL không được lưu ngoài instance |
| Archive freshness SLA missed | Archive age vượt recovery objective | PITR window có nguy cơ |
| Archive storage low | Free space dưới headroom | Có thể không tiếp tục archive |

Nếu không có WAL mới, archive không tạo file mới là bình thường. Dùng WAL activity/segment switch để xác định có công việc cần archive.

Một archive failure đơn lẻ có thể tự retry thành công. Alert theo số lần liên tiếp, age và backlog growth để giảm noise, nhưng không bỏ qua critical failures.

## 30. Alerting: replication slots và WAL disk

| Alert | Điều kiện tham khảo | Ý nghĩa |
|---|---|---|
| Inactive slot too long | Slot inactive quá policy | Consumer có thể bị bỏ quên |
| Retained WAL high | Retained bytes vượt budget | Slot giữ WAL nhiều |
| Slot near invalidation | safe_wal_size thấp khi có cột này | WAL sắp vượt limit |
| Slot lost | wal_status báo lost | Consumer có thể cần reseed |
| Catalog xmin old | catalog_xmin quá cũ | Vacuum/catalog bloat risk |
| pg_wal disk high | Disk usage vượt threshold | Primary có nguy cơ hết disk |
| WAL disk growth rapid | Growth rate vượt forecast | Archive/slot/standby backlog |

Không chỉ alert tổng số slots. Gắn slot name với consumer owner và loại consumer để operator biết ai cần xử lý. Một slot có thể tạm inactive trong maintenance; alert phải dựa vào expected consumer schedule và retention budget.

Disk alert cần nhiều ngưỡng. Ví dụ warning khi headroom còn 30%, critical khi còn 10% hoặc thời gian dự kiến tới full dưới một khoảng an toàn. Chọn số theo WAL rate và thời gian can thiệp thực tế.

## 31. Alerting: replication lag

Các tín hiệu:
- Byte lag hiện tại.
- Lag growth rate.
- Receive/write/flush/replay gap.
- Receiver last message age.
- Estimated catch-up time.
- Sync standby state/quorum.
- Application read-after-write SLA.

Có thể dùng threshold bytes để phát hiện backlog lớn, nhưng phải scale theo WAL rate và storage. Ước lượng thời gian catch-up có thể hữu ích hơn byte lag nếu replay throughput đo được ổn định.

Nếu hệ thống yêu cầu sync, alert khi không đủ synchronous standbys hoặc sync_state thay đổi ngoài dự kiến. Điều này có thể làm commit chờ hoặc giảm durability policy.

Không có WAL receiver row hoặc last message quá cũ có thể chỉ ra connection failure. Kiểm tra standby role và expected maintenance windows.

## 32. Capacity planning cho WAL và archive

Dự báo capacity cần:
1. Đo peak và average WAL generation rate.
2. Đo archive upload throughput và latency.
3. Xác định archive outage duration có thể chịu.
4. Xác định standby offline window.
5. Tính slot retention budget.
6. Dự phòng backup/restore traffic và burst workloads.
7. Giữ filesystem headroom cho checkpoint/recovery.
8. Xác định tốc độ scale storage và alert lead time.

### 32.1. Ví dụ tính dung lượng

Giả sử peak WAL generation là 20 MB/s và hệ thống cần chịu archive outage 30 phút:

```text
20 MB/s × 30 × 60 s = 36,000 MB
approximately 36 GB of generated WAL
```

Đây chỉ là baseline tính theo peak rate giả định. Cần cộng headroom, slot retention, concurrent consumers và segment overhead.

### 32.2. Archive destination capacity

Archive có thể giữ nhiều tuần/tháng để PITR. Dự báo theo WAL generation trung bình, retention days, compression ratio và backup lifecycle.

### 32.3. WAL compression

Có thể dùng compression trong archive tool/object storage để giảm storage, nhưng cần đo CPU, throughput và restore latency. Đừng giả định compression ratio cố định.

### 32.4. Growth bursts

Index rebuild, bulk load, large updates và checkpoint/full-page images có thể làm WAL generation tăng đột biến. Thiết kế theo peak hoặc burst duration, không chỉ average.

## 33. Troubleshooting: archive failures

Triệu chứng:
- `failed_count` tăng.
- `last_failed_wal`/`last_failed_time` cập nhật.
- `.ready` files tồn tại lâu.
- `pg_wal` tăng.
- Logs báo archive command failed.

Kiểm tra theo thứ tự:
1. PostgreSQL logs và exact exit status.
2. Archive destination reachable không?
3. Disk/object quota còn không?
4. OS permissions/credentials có đúng?
5. Script path và quoting `%p`/`%f` đúng?
6. Destination file đã tồn tại nhưng khác nội dung?
7. TLS/API credential hết hạn?
8. Archive tool có bị timeout/rate limit?
9. Script có trả success trước upload completion?
10. Storage/network latency có vượt budget?

Sửa nguyên nhân, chạy lại cơ chế retry tự nhiên và xác nhận `archived_count` tăng, `last_archived_wal` tiến lên, ready backlog giảm. Không xóa marker để ép trạng thái.

Nếu command trả success, xác minh object có kích thước/nội dung đúng và có thể đọc lại. Archive success ở PostgreSQL chỉ phản ánh exit success của command/library.

Không dùng OS command để xóa files trong `pg_wal`. PostgreSQL quản lý lifecycle WAL; xóa file có thể làm hỏng recovery.

## 34. Troubleshooting: WAL disk tăng liên tục

Tìm nguyên nhân retention:

**Archiving**
- Archive command thất bại?
- Ready backlog tăng?
- Destination quota/network lỗi?

**Replication slots**
- Slot inactive?
- `restart_lsn` cũ?
- Consumer bị decommission?
- Logical transaction giữ slot lâu?

**Standby**
- WAL receiver disconnected?
- Network/write/flush/replay lag?
- Standby không đủ capacity?

**Configuration**
- `max_slot_wal_keep_size = -1`?
- `wal_keep_size` lớn?
- `max_wal_size` bị hiểu nhầm là hard cap?

Sau khi tìm ra nguyên nhân, khôi phục archive/consumer, reconnect standby, reseed consumer nếu WAL đã mất, drop orphan slot chỉ sau khi xác nhận không còn consumer, hoặc điều chỉnh retention limits theo RPO/capacity.

## 35. Troubleshooting: replication lag tăng

- **Sent-to-write tăng:** có thể do network bandwidth, packet loss, receiver scheduling hoặc standby write throughput.
- **Write-to-flush tăng:** có thể do standby storage latency, fsync behavior hoặc I/O contention.
- **Flush-to-replay tăng:** có thể do replay CPU/I/O bottleneck, checkpoint activity hoặc hot standby conflicts.
- **Receiver không hoạt động:** kiểm tra `pg_stat_wal_receiver`, logs, `primary_conninfo`, authentication, TLS, pg_hba, DNS và slot.
- **Lag chỉ tăng trong peak workload:** so sánh WAL generation rate với receive/replay throughput. Nếu generation liên tục cao hơn capacity, cần scale standby/network/storage hoặc giảm WAL workload.

## 36. Troubleshooting: slot giữ WAL dù consumer không hoạt động

1. Liệt kê slot name/type/active/restart_lsn.
2. Xác định owner/consumer.
3. Kiểm tra consumer logs và connection state.
4. Ước lượng retained bytes.
5. Xem `catalog_xmin` nếu logical.
6. Xác định slot có còn được dùng không.
7. Nếu consumer cần dữ liệu, khôi phục/reseed trước khi thay slot.
8. Nếu orphan, xác nhận owner trước khi drop.
9. Theo dõi `pg_wal` sau cleanup; WAL có thể được recycle theo checkpoint/other retention needs, không nhất thiết giảm ngay tức thì.

## 37. Troubleshooting: archive freshness cũ nhưng không có failure

Kiểm tra:
- Có WAL activity mới không?
- Segment hiện tại đã switch chưa?
- `archive_timeout` có phù hợp không?
- Có `.ready` files không?
- `last_archived_time` có cũ do workload idle không?
- Có timeline change hoặc archive path khác không?

Nếu workload idle và không có segment cần archive, freshness cũ có thể bình thường. Nếu cần heartbeat archive freshness cho PITR monitoring, có thể tạo WAL activity/segment switch có kiểm soát hoặc kiểm tra archive restore workflow định kỳ.

## 38. Troubleshooting: slot lost hoặc standby không thể catch up

Kiểm tra slot status và logs. Nếu `wal_status` báo lost hoặc receiver yêu cầu WAL đã recycle, consumer không thể tiếp tục từ vị trí đó bằng cách reconnect đơn thuần.

Với physical standby, tìm WAL trong archive nếu cấu hình restore path hỗ trợ và đủ liên tục. Nếu không, tạo lại standby từ base backup.

Với logical consumer, kiểm tra khả năng resnapshot/reinitialize. Không chỉ tạo slot mới và tiếp tục apply từ current LSN vì có thể bỏ qua changes giữa hai thời điểm.

Để tránh tái diễn, đặt slot retention cap, monitor `safe_wal_size` khi có, alert inactive slots và capacity-plan consumer outage.

## 39. Troubleshooting: logical slot gây catalog bloat

Kiểm tra `catalog_xmin` trên slot, long-running transactions, consumer progress/confirmed_flush_lsn, logical decoding worker state, vacuum activity và transaction ID age.

Nếu slot không còn cần, xác nhận owner trước khi drop. Nếu consumer cần, khôi phục tiến độ hoặc reinitialize theo tool. Không hạ vacuum thresholds một cách mù quáng để xử lý catalog bloat do slot.

## 40. Archive trên standby và cascading topology

Một standby có thể được cấu hình để archive WAL nhận được, tùy mục đích topology và PostgreSQL version.

### 40.1. archive_mode=always

Chế độ `always` cho phép archive WAL trong recovery/standby. Điều này có thể hữu ích trong cascading/backup setups.

### 40.2. Archive target phải được thiết kế

Nếu primary và standby cùng archive vào một destination, cần xử lý timeline, file identity và duplicate segments an toàn. Tốt nhất dùng archive system hiểu WAL/timeline và có immutable/idempotent semantics.

### 40.3. Standby archive không thay primary archive policy

Cần xác định nguồn archive authoritative, failover behavior và cách đảm bảo WAL continuity qua timeline change.

### 40.4. Kiểm tra archive process trên đúng node

`pg_stat_archiver` là statistics của từng instance. Scrape cả primary lẫn standby có archive enabled, gắn nhãn node/role để tránh gộp counters.

## 41. Archive cleanup và retention

Archive cleanup phải phối hợp với backup catalog và recovery windows.

- Không xóa theo tuổi đơn thuần. Một WAL file cũ có thể vẫn cần cho base backup còn được giữ.
- Dùng backup catalog/tool có thể xác định WAL cần cho backup sets. Archive lifecycle policy cần hiểu backup retention và WAL dependencies.
- `pg_archivecleanup` có thể được dùng trong một số standby/archive cleanup workflows để xóa các WAL files cũ hơn điểm cần thiết. Không dùng như global PITR retention manager nếu chưa tính các base backups khác còn được giữ.
- Object storage lifecycle expiration phải phù hợp với backup retention và recovery objectives. Test restore từ object còn nằm trong retention window.
- Đừng bỏ timeline history files cần thiết khi cleanup. Chúng giúp recovery biết WAL thuộc timeline nào và nhánh nào được chọn.

## 42. Archive verification và restore drills

Một archive khỏe cần được kiểm tra bằng recovery thật.

Quy trình định kỳ:
1. Chọn một base backup.
2. Xác định recovery target.
3. Tạo môi trường restore riêng.
4. Cấu hình `restore_command`.
5. Restore base backup.
6. Replay WAL tới target.
7. Kiểm tra PostgreSQL startup và consistency.
8. Chạy smoke queries/application checks.
9. Ghi nhận thời gian restore và WAL gaps.
10. Sửa archive/backup process nếu có segment thiếu hoặc latency vượt RTO.

File tồn tại có thể bị truncate, corrupt hoặc mã hóa key không còn. Restore drill kiểm tra cả readability và continuity. `pg_stat_archiver` có thể báo success nhưng không chứng minh một base backup cụ thể có đủ WAL để restore.

## 43. Monitoring WAL write/sync latency

`pg_stat_wal` có thể cung cấp counters và timing nếu tính năng timing được bật.

```sql
SELECT
    wal_bytes,
    wal_records,
    wal_fpi,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
```

Timing counters có thể cần `track_wal_io_timing` hoặc cấu hình phù hợp theo version. Bật timing có thể có overhead nhỏ; đo trên workload thật.

Lấy delta timing/delta operations để tính average, nhưng dùng OS/storage metrics hoặc tracing để hiểu tail latency. Một lần sync rất chậm có thể ảnh hưởng commit p99 mà average vẫn thấp.

Các PostgreSQL versions mới có `pg_stat_io` để xem I/O statistics theo backend/object/context. Dùng khi version hỗ trợ và hiểu cách map WAL I/O; không thay thế `pg_stat_wal`/OS metrics.

## 44. Checkpoint, full-page images và WAL bursts

WAL generation có thể tăng sau checkpoint vì full-page images được ghi khi page được sửa lần đầu sau checkpoint, tùy `full_page_writes` và WAL settings.

`wal_fpi` tăng có thể phản ánh nhiều full-page images. So sánh với `wal_records` và `wal_bytes`.

Checkpoint frequency và `checkpoint_timeout`/`max_wal_size` có thể ảnh hưởng WAL volume, I/O và FPI. Thay đổi checkpoint settings cần dựa trên workload và crash recovery objectives.

`full_page_writes` là durability/corruption protection quan trọng. Không tắt tùy tiện để giảm archive size.

Bulk load, index rebuild, large updates và vacuum-related operations có thể tạo WAL burst. Lập kế hoạch capacity/maintenance window và theo dõi archive/standby throughput trong các đợt này.

## 45. Security và permissions cho monitoring

Một số views/functions yêu cầu quyền cao hoặc role monitoring.

- Dùng predefined monitoring roles phù hợp thay vì cấp superuser cho exporter nếu không cần.
- Các hàm như `pg_ls_waldir()` và `pg_ls_archive_statusdir()` có thể bị giới hạn quyền. Chỉ cấp quyền cần thiết và tránh expose filesystem metadata cho application roles.
- Không ghi cloud credentials/password vào command text hoặc logs. Dùng secret store, service identity hoặc passfile với file permissions phù hợp.
- Dùng TLS, encryption at rest, access controls và immutable retention nếu business yêu cầu. Monitoring phải cảnh báo auth failures và encryption key expiry.

## 46. Lab: xem WAL positions

Trong một PostgreSQL lab, trên primary chạy:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
```

Trên standby chạy:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

Tạo table lab và insert một lượng dữ liệu vừa phải trên primary. Quan sát LSN tăng, ghi lại LSN ở primary và standby theo thời điểm, rồi dùng `pg_wal_lsn_diff()` để tính byte gap.

Ngừng ghi và quan sát timestamp lag. Ghi nhận vì sao timestamp cũ không nhất thiết có nghĩa standby đang lag.

## 47. Lab: kiểm tra archive

Chỉ thực hiện trên lab có archive destination riêng.

1. Bật `archive_mode` theo yêu cầu restart.
2. Cấu hình `archive_command` hoặc `archive_library` dùng destination lab.
3. Đặt `archive_timeout` phù hợp.
4. Tạo WAL activity.
5. Chạy trên primary:

```sql
SELECT pg_switch_wal();
```

6. Kiểm tra archiver:

```sql
SELECT *
FROM pg_stat_archiver;
```

7. Dùng `pg_ls_archive_statusdir()` nếu version hỗ trợ hoặc kiểm tra filesystem qua công cụ OS.
8. Xác nhận `.ready` được xử lý và archive object tồn tại.
9. Trong lab, làm destination không ghi được; quan sát failed_count/last_failed_wal, logs và ready backlog.
10. Khôi phục destination và xác nhận archiver retry thành công.

## 48. Lab: tạo physical replication slot

Trên primary lab:

```sql
SELECT *
FROM pg_create_physical_replication_slot('lab_standby_slot');
```

Kiểm tra:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_replication_slots;
```

Cấu hình `primary_slot_name` trên standby và xác nhận `pg_stat_wal_receiver` cho thấy slot tương ứng.

Trên primary, xem active và restart_lsn. Tạo workload ghi và quan sát slot position tiến theo consumer.

Dừng standby có kiểm soát trong lab, tạo WAL trên primary và quan sát slot inactive/retained WAL bytes tăng. Start standby lại và xác nhận catch-up nếu required WAL vẫn còn. Không đặt giới hạn nhỏ khiến slot invalidation ngoài ý muốn trong lab này.

## 49. Lab: logical slot và consumer lag

Trong lab riêng có logical decoding support:
1. Tạo publication/subscription hoặc logical slot phù hợp.
2. Tạo workload thay đổi rows.
3. Quan sát `pg_replication_slots`.
4. Dừng consumer.
5. Theo dõi `restart_lsn`, `confirmed_flush_lsn`, `catalog_xmin`.
6. Khởi động consumer và xác nhận progress.
7. Ghi nhận tác động khi consumer bị dừng lâu.

Không tạo logical slot trên production để thử nếu chưa có owner/cleanup plan; slot có thể giữ WAL và catalog tuples.

## 50. Lab: đo WAL generation rate

Chụp mẫu `pg_stat_wal` hai lần với khoảng thời gian xác định:

```sql
SELECT
    clock_timestamp() AS sampled_at,
    wal_bytes,
    wal_records,
    wal_fpi,
    stats_reset
FROM pg_stat_wal;
```

Tính delta bytes chia elapsed seconds bên ngoài hoặc trong monitoring system. Nếu stats_reset thay đổi, reset baseline.

So sánh idle, insert workload và bulk update trong lab. Ghi WAL bytes/sec, replication lag và archive rate. Dùng cluster disposable, workload giới hạn và storage riêng; đừng chạy benchmark trên production.

## 51. Lab: xây dựng alert theo trend

Tạo dashboard/alert rule thử nghiệm cho:
- Archive failed_count tăng.
- `.ready` queue tăng.
- Inactive slot giữ WAL quá lâu.
- Retained bytes vượt budget.
- Standby sent-to-write gap tăng.
- Flush-to-replay gap tăng.
- `pg_wal` disk headroom giảm.
- Receiver mất kết nối.
- Sync standby không còn đáp ứng quorum.

Tạo idle period, maintenance window và WAL burst để xem alert có phân biệt idle với stall hay không.

Alert phải chỉ rõ cluster, node, slot/archive file, metric, current value, threshold và runbook link. Tránh cảnh báo chung “replication unhealthy”.

## 52. Runbook: archive bị nghẽn

**Triệu chứng:** `failed_count` tăng, `.ready` backlog tăng, `pg_wal` tăng.

1. Kiểm tra PostgreSQL logs và archive command exit errors.
2. Kiểm tra destination/network/quota/permissions.
3. Xác định WAL file đầu tiên bị kẹt.
4. Kiểm tra destination có object trùng tên hay object corrupt.
5. Sửa archive script/config theo change process.
6. Xác nhận archiver retry và archived_count tăng.
7. Xác nhận ready backlog giảm.
8. Xác minh archive object đọc được.
9. Đánh giá PITR gap và backup restore risk.
10. Theo dõi disk headroom cho đến khi WAL được recycle.

Không xóa `.ready` hoặc WAL segment để giảm disk pressure.

## 53. Runbook: slot giữ WAL quá nhiều

**Triệu chứng:** retained bytes tăng, slot inactive lâu, `pg_wal` gần đầy.

1. Xác định slot name/type/owner.
2. Kiểm tra active state và last consumer connection.
3. Xác định consumer có cần tiếp tục từ restart_lsn không.
4. Ước lượng thời gian/bytes tới disk exhaustion.
5. Khôi phục consumer nếu còn WAL và cần dữ liệu.
6. Nếu WAL đã mất, lập kế hoạch reseed/resnapshot.
7. Nếu slot orphan, xác nhận owner và decommission.
8. Drop slot theo quy trình có audit.
9. Theo dõi WAL recycling và filesystem.
10. Đặt alert/retention limit để tránh tái diễn.

Không drop slot đang phục vụ consumer hoặc chỉ vì active=false.

## 54. Runbook: standby lag tăng

1. Xác định standby/application_name và state.
2. Kiểm tra receiver connection và last message time.
3. Đo sent-to-write, write-to-flush, flush-to-replay gaps.
4. So sánh WAL generation rate với receive/replay throughput.
5. Kiểm tra network RTT/bandwidth/loss.
6. Kiểm tra standby disk latency/CPU/I/O.
7. Kiểm tra hot standby query conflicts.
8. Kiểm tra slot status và WAL retention.
9. Đánh giá có đủ WAL để catch up hay cần reseed.
10. Đánh giá failover eligibility và RPO nếu primary gặp sự cố.

## 55. Runbook: pg_wal filesystem gần đầy

1. Xác định free bytes/inodes và tốc độ tăng.
2. Kiểm tra archive failures/backlog.
3. Kiểm tra slots và oldest restart_lsn.
4. Kiểm tra disconnected standbys/consumers.
5. Kiểm tra WAL generation burst.
6. Xác định nguyên nhân giữ WAL lớn nhất.
7. Khôi phục archive/consumer hoặc xử lý orphan slot có kiểm soát.
8. Nếu cần, mở rộng filesystem theo platform procedure.
9. Không xóa WAL files thủ công.
10. Xác nhận WAL usage ổn định và capacity headroom phục hồi.

Không chỉ tăng `max_wal_size`. Nếu WAL bị giữ bởi slot/archive, tăng max_wal_size có thể làm filesystem pressure tệ hơn và không giải quyết nguyên nhân. Không drop mọi slot cùng lúc; mỗi slot có thể đại diện một standby/CDC consumer quan trọng.

## 56. Best practices

- Dùng archive destination độc lập với primary storage.
- Làm archive command idempotent và atomic theo semantics destination.
- Chỉ trả success khi archive object thực sự sẵn sàng.
- Monitor cả `pg_stat_archiver` lẫn ready backlog.
- Theo dõi archive freshness cùng WAL activity.
- Duy trì base backup và PITR restore drills.
- Mỗi standby/consumer có slot riêng khi cần.
- Inventory slot owner, purpose và decommission process.
- Monitor inactive slots, retained bytes và catalog_xmin.
- Chọn `max_slot_wal_keep_size` theo capacity và recovery policy.
- Hiểu `max_wal_size` là soft target, không phải disk cap.
- Theo dõi send/write/flush/replay gaps riêng.
- Không dùng timestamp lag một mình khi workload idle.
- Đo WAL generation rate và replay throughput.
- Alert theo trend, age và disk headroom.
- Không xóa thủ công files trong `pg_wal` hoặc archive status.
- Kiểm tra schema/version của monitoring views trước khi triển khai exporter.
- Giữ monitoring credentials ở least privilege.
- Đồng bộ labels giữa PostgreSQL, DCS, backup và infrastructure monitoring.

## 57. Những hiểu lầm thường gặp

### 57.1. “pg_stat_archiver không báo lỗi là archive hoàn chỉnh”

Không đúng. View thống kê archiver không chứng minh archive có đủ WAL liên tục cho một base backup cụ thể. Cần kiểm tra queue, object storage và restore drill.

### 57.2. “archived_count là số file đang lưu”

Không đúng. Đây là counter số lần archive thành công kể từ stats reset.

### 57.3. “last_archived_time cũ nghĩa archive hỏng”

Không nhất thiết. Primary có thể không tạo WAL segment mới hoặc segment hiện tại chưa hoàn tất.

### 57.4. “replication slot inactive không giữ tài nguyên”

Không đúng. Slot inactive vẫn có thể giữ WAL và catalog tuples.

### 57.5. “max_wal_size giới hạn tối đa pg_wal”

Không đúng. Slot/archive retention có thể làm WAL vượt mức này.

### 57.6. “wal_keep_size thay thế replication slot”

Không đúng. Nó giữ một lượng WAL tối thiểu, không đảm bảo mọi consumer offline lâu vẫn bắt kịp.

### 57.7. “Standby streaming nghĩa replay đã theo kịp”

Không đúng. Received, written, flushed và replayed LSN có thể khác nhau.

### 57.8. “Replay timestamp là lag chính xác”

Không đúng. Workload idle và clock skew có thể làm age của transaction cuối cùng gây hiểu nhầm.

### 57.9. “Drop slot sẽ chỉ xóa metadata”

Không đúng. Nó có thể làm consumer mất WAL cần để tiếp tục và buộc phải reseed/resnapshot.

### 57.10. “Archive thành công nghĩa standby đã nhận WAL”

Không đúng. Archive và streaming replication là hai đường riêng.

## 58. Bảng tra cứu nhanh

| Nhu cầu | View/hàm/tham số |
|---|---|
| Current WAL position | `pg_current_wal_lsn()` |
| Primary WAL flush | `pg_current_wal_flush_lsn()` |
| WAL bytes generated | `pg_stat_wal.wal_bytes` |
| Archive success/failure | `pg_stat_archiver` |
| Archive mode | `archive_mode` |
| Archive command | `archive_command` |
| Archive library | `archive_library` |
| Segment switch timeout | `archive_timeout` |
| Force segment switch (primary) | `pg_switch_wal()` |
| Archive status queue | `pg_ls_archive_statusdir()` nếu version hỗ trợ |
| WAL directory listing | `pg_ls_waldir()` nếu version hỗ trợ |
| Slot inventory | `pg_replication_slots` |
| Slot oldest WAL | `restart_lsn` |
| Logical consumer progress | `confirmed_flush_lsn` |
| Logical catalog retention | `catalog_xmin` |
| Slot WAL status | `wal_status`, version-dependent |
| Slot headroom | `safe_wal_size`, version-dependent |
| Primary standby status | `pg_stat_replication` |
| Standby receiver | `pg_stat_wal_receiver` |
| Standby receive position | `pg_last_wal_receive_lsn()` |
| Standby replay position | `pg_last_wal_replay_lsn()` |
| LSN byte difference | `pg_wal_lsn_diff()` |
| Logical subscriber workers | `pg_stat_subscription` |
| Slot retention limit | `max_slot_wal_keep_size` |
| Minimum WAL retention | `wal_keep_size` |
| Checkpoint WAL target | `max_wal_size` |

## 59. Tài liệu chính thức tham khảo

- [PostgreSQL 18 — WAL Internals](https://www.postgresql.org/docs/18/wal-internals.html): WAL files, records và segment layout.
- [PostgreSQL 18 — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/18/continuous-archiving.html): archive setup, restore_command và PITR.
- [PostgreSQL 18 — WAL Configuration](https://www.postgresql.org/docs/18/runtime-config-wal.html): archive_mode, archive_command, archive_timeout và WAL parameters.
- [PostgreSQL 18 — Replication Configuration](https://www.postgresql.org/docs/18/runtime-config-replication.html): WAL senders, replication slots và retention settings.
- [PostgreSQL 18 — Monitoring Statistics](https://www.postgresql.org/docs/18/monitoring-stats.html): pg_stat_archiver, pg_stat_wal, pg_stat_replication, pg_stat_wal_receiver và các views khác.
- [PostgreSQL 18 — Administrative Functions](https://www.postgresql.org/docs/18/functions-admin.html): WAL, replication slot và filesystem inspection functions.
- [PostgreSQL 18 — Logical Decoding](https://www.postgresql.org/docs/18/logicaldecoding.html): logical slots và decoding.
- [PostgreSQL 18 — Replication](https://www.postgresql.org/docs/18/high-availability.html): physical/logical replication overview.

Các views, columns và functions có thể khác giữa major versions. Trước khi triển khai exporter hoặc query production, kiểm tra manual đúng phiên bản và quyền truy cập cần thiết.

## 60. Tổng kết

Giám sát WAL cần theo dõi toàn bộ vòng đời từ generation tới archive và replay. Mỗi cơ chế giữ WAL giải quyết một nhu cầu khác nhau: archive hỗ trợ PITR/backup, replication slot giữ WAL cho consumer, streaming truyền WAL trực tiếp, còn LSN/lag metrics cho biết các node đang tiến tới đâu.

1. **WAL positions:** phân biệt generated, sent, received, written, flushed và replayed.
2. **Archive:** dùng `pg_stat_archiver`, ready backlog, archive freshness và restore drills. Archive success không tự chứng minh PITR completeness.
3. **Replication slots:** theo dõi active state, restart_lsn, retained bytes và catalog_xmin. Slot inactive vẫn có thể giữ WAL.
4. **Retention:** `max_slot_wal_keep_size`, `wal_keep_size` và `max_wal_size` có semantics khác nhau. `max_wal_size` không phải hard cap cho `pg_wal`.
5. **Replication lag:** đo riêng send-to-write, write-to-flush và flush-to-replay. Kết hợp bytes, WAL rate và catch-up throughput.
6. **Alerts:** cảnh báo archive failures/backlog, slot retention, receiver disconnect, sync state, WAL disk headroom và lag growth.
7. **Recovery:** không xóa WAL/status files thủ công; nếu slot mất WAL, consumer có thể cần reseed/resnapshot.
8. **PITR:** duy trì base backups, WAL continuity, archive retention và restore tests định kỳ.

Một dashboard WAL tốt phải giúp operator trả lời nhanh: WAL đang được tạo nhanh đến mức nào, thứ gì đang giữ WAL lại, archive có liên tục không, standby đang chậm ở khâu nhận/ghi/flush/replay nào, và còn bao lâu trước khi tài nguyên lưu trữ chạm ngưỡng nguy hiểm.
