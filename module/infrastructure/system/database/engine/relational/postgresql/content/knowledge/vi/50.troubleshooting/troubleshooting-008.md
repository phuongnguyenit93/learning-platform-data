# Độ trễ sao chép, slot bị bỏ quên và standby mất WAL

Streaming replication giúp PostgreSQL duy trì standby bằng cách gửi và phát lại WAL từ primary. Khi hệ thống hoạt động bình thường, standby nhận các bản ghi WAL mới, ghi chúng vào vùng lưu trữ cục bộ rồi replay để cập nhật dữ liệu. Nếu mạng chậm, standby xử lý WAL không kịp, replication slot giữ WAL quá lâu hoặc các segment cần thiết đã bị xóa, standby có thể bị trễ hoặc không thể tiếp tục đồng bộ.

Ba tình huống thường liên quan nhưng không giống nhau:

- **Replication lag:** standby vẫn nhận được WAL nhưng vị trí nhận, ghi, flush hoặc replay chậm hơn primary.
- **Replication slot bị bỏ quên:** slot không còn consumer hoạt động nhưng vẫn giữ WAL, có thể làm `pg_wal` tăng đến mức đầy đĩa.
- **Standby mất WAL:** standby yêu cầu một segment mà primary không còn giữ trong `pg_wal`; nếu archive cũng không có segment đó, standby không thể tiếp tục recovery từ vị trí hiện tại.

Điều tra đúng cần xác định vị trí WAL cuối cùng mà từng thành phần đã xử lý, slot nào đang giữ WAL, segment bị thiếu có còn trong archive hay không và standby có thể bắt kịp mà không cần dựng lại hay không. Không xóa file trong `pg_wal` thủ công và không xóa slot khi chưa xác định consumer sở hữu nó.

## 1. Cách PostgreSQL truyền và phát lại WAL

WAL (Write-Ahead Logging) ghi lại các thay đổi cần thiết để phục hồi database sau sự cố và đồng bộ sang standby. Trong streaming replication vật lý, luồng dữ liệu chính gồm:

1. Backend trên primary tạo WAL khi transaction thay đổi dữ liệu.
2. WAL sender đọc các WAL record và gửi qua kết nối replication.
3. WAL receiver trên standby nhận dữ liệu, ghi vào WAL segment cục bộ và flush theo yêu cầu.
4. Startup process trên standby đọc WAL đã nhận và replay để cập nhật các trang dữ liệu.
5. Standby báo cáo các vị trí WAL đã ghi, flush và replay để primary biết tiến độ.

Sơ đồ khái quát:

```text
Ứng dụng ghi
    |
    v
  PRIMARY
    |
    | WAL sender
    v
Mạng / replication connection
    |
    v
  STANDBY
    | WAL receiver
    v
WAL trên đĩa standby
    | startup / recovery process
    v
Replay vào data pages
    |
    v
Truy vấn đọc trên standby
```

Nhận WAL và replay WAL là hai giai đoạn khác nhau. Standby có thể nhận và flush gần sát primary nhưng replay chậm vì I/O, CPU, recovery conflict hoặc workload đọc. Ngược lại, WAL receiver có thể không nhận được dữ liệu mới do mạng hoặc primary, khiến cả receive và replay cùng đứng lại.

## 2. Phân biệt các loại replication lag

Trong PostgreSQL, “lag” có thể chỉ nhiều khoảng cách khác nhau. Cần phân biệt chúng trước khi thay đổi cấu hình.

| Giai đoạn | Ý nghĩa | Vấn đề có thể gặp |
|---|---|---|
| Send | WAL đã được primary gửi đến vị trí nào | WAL sender, mạng hoặc standby không nhận kịp |
| Write | WAL receiver đã ghi dữ liệu đến vị trí nào | Tốc độ ghi đĩa standby hoặc buffer |
| Flush | WAL đã được flush bền vững đến vị trí nào | I/O, fsync, storage latency |
| Replay | Standby đã áp dụng WAL đến vị trí nào | CPU, I/O, recovery conflict, transaction lớn |

Các LSN (Log Sequence Number) là vị trí trong luồng WAL. So sánh các LSN giúp xác định khoảng cách theo byte. Thời gian lag và byte lag không thể thay thế hoàn toàn cho nhau: WAL generation rate có thể thay đổi, và một khoảng cách byte nhỏ trong lúc primary phát WAL rất nhanh vẫn có thể tương ứng với độ trễ thời gian đáng kể.

## 3. Kiểm tra tiến độ standby từ primary

Trên primary, `pg_stat_replication` hiển thị trạng thái các kết nối standby trực tiếp:

```sql
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
FROM pg_stat_replication
ORDER BY application_name;
```

Các cột quan trọng:

- `state`: trạng thái gửi WAL, thường cần thấy `streaming` khi standby đang streaming bình thường.
- `sync_state`: trạng thái đồng bộ như `sync`, `async` hoặc các trạng thái liên quan đến cấu hình synchronous replication.
- `sent_lsn`: vị trí WAL cuối cùng đã gửi.
- `write_lsn`: vị trí standby đã ghi.
- `flush_lsn`: vị trí standby đã flush.
- `replay_lsn`: vị trí standby đã replay.
- `write_lag`, `flush_lag`, `replay_lag`: các khoảng trễ gần đây được ước lượng từ phản hồi standby; có thể là `NULL` khi không có giao dịch mới hoặc không có mẫu phù hợp.

### Tính khoảng cách WAL theo byte

Có thể tính khoảng cách giữa WAL hiện tại trên primary và các vị trí standby:

```sql
SELECT
    application_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)::bigint
    ) AS not_yet_sent,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn)::bigint
    ) AS not_yet_written,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn)::bigint
    ) AS not_yet_flushed,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint
    ) AS not_yet_replayed
FROM pg_stat_replication;
```

Các giá trị này là khoảng cách LSN tại thời điểm truy vấn, không phải thời gian lag. Nếu một LSN là `NULL`, kết quả phép tính cũng là `NULL`. Chỉ so sánh các LSN thuộc cùng timeline/luồng WAL có quan hệ hợp lệ.

### Xác định lag nằm ở giai đoạn nào

- `sent_lsn` xa `pg_current_wal_lsn()`: primary chưa gửi kịp hoặc chưa có phản hồi cập nhật; kiểm tra WAL sender, mạng và trạng thái kết nối.
- `write_lsn` thấp hơn `sent_lsn`: standby nhận hoặc ghi WAL chưa theo kịp.
- `flush_lsn` thấp hơn `write_lsn`: flush/storage standby có thể là nút thắt.
- `replay_lsn` thấp hơn `flush_lsn`: standby nhận WAL nhưng replay chưa theo kịp; xem recovery process, CPU, I/O và conflict.

Không kết luận chỉ từ một mẫu. Lấy nhiều mẫu theo thời gian để xác định khoảng cách đang tăng, giảm hay đứng yên.

## 4. Kiểm tra WAL receiver trên standby

Trên standby, `pg_stat_wal_receiver` cho biết trạng thái kết nối nhận WAL:

```sql
SELECT *
FROM pg_stat_wal_receiver;
```

Các cột thường hữu ích gồm trạng thái receiver, PID, host/port nguồn, `slot_name`, LSN nhận mới nhất và thời điểm thông điệp cuối. Cấu trúc view có thể thay đổi theo phiên bản PostgreSQL; dùng `SELECT *` để xem các trường thực tế trước khi viết dashboard cố định.

Có thể kiểm tra thêm các hàm LSN trên standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_at;
```

`pg_last_wal_receive_lsn()` phản ánh vị trí WAL nhận gần nhất, còn `pg_last_wal_replay_lsn()` phản ánh vị trí đã replay. Khoảng cách giữa hai vị trí giúp quan sát backlog replay. Nếu WAL receiver không chạy hoặc chưa nhận được WAL, các giá trị có thể `NULL` hoặc không tiến triển.

### Vì sao `now() - pg_last_xact_replay_timestamp()` có thể gây hiểu nhầm?

Đây là thời gian kể từ transaction cuối cùng được replay, không phải phép đo lag tuyệt đối trong mọi tình huống. Khi primary không có giao dịch mới, timestamp vẫn cũ dù standby đã theo kịp. Khi chưa replay transaction nào, kết quả có thể `NULL`. Với workload ít ghi, nên dùng heartbeat transaction hoặc so sánh LSN cùng tốc độ sinh WAL để đo độ mới đáng tin cậy hơn.

## 5. Phân biệt network lag và replay lag

Nếu WAL receiver có kết nối ổn định và `received_lsn` tiến lên nhưng `replayed_lsn` đứng lại, vấn đề nằm sau khâu nhận. Có thể kiểm tra:

- CPU của standby có bão hòa không.
- Storage latency và throughput ghi/đọc có bất thường không.
- Có transaction lớn hoặc đợt bulk load ở primary không.
- Có recovery conflict với truy vấn dài trên hot standby không.
- Có checkpoint, autovacuum hoặc tác vụ bảo trì gây tranh chấp I/O không.
- Các tiến trình recovery có tiến triển trong log và metric không.

Nếu cả receive và replay đều đứng, kiểm tra:

- Kết nối mạng và packet loss.
- DNS, firewall, route và TLS.
- WAL sender còn hoạt động hay không.
- `primary_conninfo` và thông tin xác thực.
- Primary có restart, failover hoặc thay đổi endpoint không.
- Replication slot có tồn tại và còn giữ WAL cần thiết không.

Không tăng `max_wal_senders` hoặc `work_mem` theo cảm tính. Trước tiên xác định giai đoạn bị nghẽn và đo tài nguyên liên quan.

## 6. Replication slot dùng để làm gì?

Replication slot là cơ chế để primary biết một consumer còn cần WAL từ vị trí nào. Slot giúp WAL cần cho consumer chưa bị tái sử dụng quá sớm.

Có hai loại chính:

- **Physical replication slot:** thường dùng cho physical standby. Nó giữ WAL cần thiết để standby tiếp tục streaming từ vị trí đã xác nhận.
- **Logical replication slot:** dùng cho logical decoding hoặc logical replication. Ngoài WAL, slot có thể giữ lại thông tin catalog cần thiết cho consumer.

Một slot không tự truyền dữ liệu. Nó chỉ theo dõi vị trí và ảnh hưởng đến việc giữ WAL. Consumer phải kết nối và tiến triển để slot được cập nhật.

### Tạo physical slot

Ví dụ tạo slot cho standby trên primary:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

Standby cần tham chiếu slot bằng `primary_slot_name` trong cấu hình recovery. Tên slot phải khớp và chỉ nên gắn với consumer được thiết kế sở hữu nó.

### Logical slot

Logical slot thường được tạo bởi logical replication subscription hoặc CDC connector. Logical slot giữ WAL đến khi consumer xác nhận đã xử lý đến vị trí tương ứng. Nếu connector ngừng hoạt động nhưng slot vẫn còn, WAL tiếp tục được giữ.

Slot logical cũng có thể giữ `catalog_xmin`, khiến vacuum không thể loại bỏ một số phiên bản catalog cũ. Do đó, slot logical bị bỏ quên có thể ảnh hưởng đến dung lượng WAL và khả năng vacuum dọn dẹp catalog.

## 7. Tìm slot bị bỏ quên hoặc không còn consumer

Trên primary, xem toàn bộ slot:

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn,
    xmin,
    catalog_xmin,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
```

Một số cột như `wal_status` và `safe_wal_size` có ở các phiên bản PostgreSQL mới hơn; nếu phiên bản đang dùng chưa hỗ trợ, bỏ các cột đó khỏi truy vấn. `confirmed_flush_lsn` chủ yếu có ý nghĩa với logical slot. `restart_lsn` là vị trí WAL sớm nhất slot còn cần giữ.

Các dấu hiệu cần điều tra:

- `active = false` trong thời gian dài.
- Slot thuộc một standby hoặc connector đã bị gỡ bỏ.
- `restart_lsn` cũ hơn đáng kể so với WAL hiện tại.
- `wal_status` cho biết WAL đã được mở rộng giữ lại, không còn được bảo đảm hoặc đã mất theo trạng thái của phiên bản.
- `safe_wal_size` giảm gần 0 khi cấu hình giới hạn WAL cho slot.
- `xmin` hoặc `catalog_xmin` cũ kéo dài, ngăn vacuum loại bỏ phiên bản không còn cần thiết.

`active = false` không đủ để kết luận slot mồ côi. Consumer có thể chỉ tạm dừng để bảo trì, hoặc standby đang ngừng hoạt động có chủ đích. Đối chiếu tên slot với inventory cluster, cấu hình `primary_slot_name`, subscription, CDC connector, lịch triển khai và người sở hữu dịch vụ trước khi thay đổi.

### Ước lượng WAL bị slot giữ

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS wal_distance
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;
```

Đây là khoảng cách LSN từ slot đến vị trí WAL hiện tại, không nhất thiết bằng chính xác dung lượng file đang chiếm trong `pg_wal`. WAL segment được quản lý theo vòng đời, checkpoint, archive và các slot khác; hãy đối chiếu thêm dung lượng filesystem và `pg_wal` thực tế.

## 8. Vì sao slot bị bỏ quên làm đầy đĩa?

Primary chỉ có thể tái sử dụng hoặc xóa WAL segment khi segment đó không còn cần cho crash recovery, archive và các consumer đang giữ WAL. Một slot có `restart_lsn` cũ có thể buộc PostgreSQL giữ nhiều segment hơn mức workload bình thường cần.

Ví dụ:

1. Một CDC connector tạo logical slot để đọc WAL.
2. Connector bị xóa khỏi hạ tầng nhưng slot vẫn tồn tại.
3. Không còn consumer xác nhận tiến độ, `restart_lsn` không di chuyển.
4. Ứng dụng tiếp tục ghi dữ liệu, WAL phát sinh liên tục.
5. Primary giữ WAL vì slot vẫn yêu cầu các segment cũ.
6. Dung lượng `pg_wal` tăng và có thể làm đầy filesystem.

Nếu filesystem chứa `pg_wal` đầy, PostgreSQL có thể không ghi được WAL mới và database có nguy cơ ngừng phục vụ hoặc shutdown. Vì vậy, slot cần có owner, SLA tiến triển, cảnh báo lag và quy trình decommission rõ ràng.

### `max_slot_wal_keep_size`

`max_slot_wal_keep_size` giới hạn lượng WAL mà replication slot được phép giữ tại các checkpoint. Giá trị `-1` có nghĩa không đặt giới hạn theo tham số này; slot có thể giữ WAL không giới hạn cho đến khi consumer tiến lên hoặc slot bị xử lý. Một giá trị hữu hạn giúp giới hạn rủi ro dung lượng nhưng có thể khiến slot mất khả năng tiếp tục nếu consumer trễ vượt giới hạn và WAL cần thiết bị loại bỏ.

Khi slot không còn bảo đảm WAL cần thiết, PostgreSQL có thể đánh dấu trạng thái `lost` ở các phiên bản hỗ trợ. Consumer khi đó không thể tiếp tục đơn giản từ slot cũ; cần xác định có thể lấy WAL từ archive hay phải tạo lại consumer/standby.

### `wal_keep_size`

`wal_keep_size` yêu cầu primary giữ lại tối thiểu một lượng WAL trong `pg_wal` để hỗ trợ standby bị trễ trong một khoảng nhất định. Đây không phải giới hạn cứng cho tổng WAL được giữ và không thay thế replication slot. Nếu standby ngừng quá lâu hoặc WAL sinh ra vượt lượng giữ lại, các segment cũ vẫn có thể bị tái sử dụng.

## 9. Các cấu hình ảnh hưởng đến WAL retention

Những tham số sau thường cần được xem cùng nhau:

| Tham số | Vai trò | Rủi ro nếu cấu hình không phù hợp |
|---|---|---|
| `wal_level` | Mức thông tin WAL, ví dụ `replica` hoặc `logical` | Không đủ cho kiểu replication/decoding cần dùng |
| `max_wal_senders` | Số WAL sender tối đa | Không đủ kết nối standby hoặc consumer |
| `max_replication_slots` | Số replication slot tối đa | Không tạo được slot mới khi đạt giới hạn |
| `wal_keep_size` | Lượng WAL tối thiểu giữ lại cho standby | Quá thấp khiến standby offline lâu mất segment cần thiết |
| `max_slot_wal_keep_size` | Giới hạn WAL được giữ bởi slot tại checkpoint | Quá thấp có thể làm slot mất WAL cần thiết |
| `archive_mode` | Bật lưu trữ WAL archive | Tắt hoặc lỗi khiến không có nguồn WAL dự phòng |
| `archive_command` | Lệnh lưu segment vào archive | Lỗi kéo dài làm archive không tiến triển và WAL tích tụ |
| `primary_slot_name` | Slot standby dùng trên primary | Sai tên hoặc slot không tồn tại làm streaming không hoạt động |
| `restore_command` | Lấy WAL từ archive khi recovery cần | Sai lệnh hoặc archive thiếu segment khiến recovery dừng |
| `primary_conninfo` | Thông tin kết nối tới primary | Endpoint, role hoặc xác thực sai khiến receiver không kết nối |

Một số tham số cần restart PostgreSQL, số khác có thể reload hoặc áp dụng động. Kiểm tra cột `context` và `pending_restart` trong `pg_settings` trên phiên bản đang chạy thay vì giả định mọi thay đổi đều có hiệu lực ngay.

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
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'archive_mode',
    'archive_command'
)
ORDER BY name;
```

## 10. Kiểm tra archive và khả năng lấy WAL cũ

WAL archive là nguồn lưu các segment đã hoàn tất để phục hồi hoặc cấp WAL cho standby khi streaming không còn segment cần thiết trong `pg_wal`. Archive chỉ hữu ích nếu segment được lưu thành công và chưa bị xóa bởi chính sách retention.

Trên primary, xem trạng thái archiver:

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

Nếu `failed_count` tăng, `last_failed_wal` không đổi trong thời gian dài hoặc archive không có segment mới, kiểm tra log của `archive_command`, quyền ghi, dung lượng archive và lỗi mạng/storage.

### `restore_command` trên standby

Standby có thể dùng `restore_command` để lấy WAL segment từ archive trong recovery. Ví dụ cấu hình dạng khái quát:

```conf
restore_command = 'cp /wal-archive/%f %p'
```

Đây chỉ là ví dụ cho archive nằm trên filesystem mà standby truy cập được. Trong production, archive có thể nằm ở object storage hoặc hệ thống backup, khi đó dùng chương trình restore phù hợp. Lệnh phải trả mã thành công khi lấy được file và trả mã phù hợp khi file không tồn tại; tránh một lệnh luôn báo thành công dù không khôi phục được segment.

Archive phải giữ đủ chuỗi WAL liên tục từ checkpoint/base backup cần thiết đến vị trí hiện tại. Một vài segment rời rạc không đủ để phục hồi một khoảng bị thiếu ở giữa.

### Không xóa archive theo tuổi đơn giản

Một segment cũ có thể vẫn cần cho standby đang lag hoặc backup/PITR. Chính sách dọn archive phải tính đến base backup, recovery window và vị trí WAL của mọi standby/consumer liên quan. Không chạy `pg_archivecleanup` trên archive dùng chung nếu chưa xác định phạm vi và mốc an toàn.

## 11. Phát hiện standby đã yêu cầu WAL bị xóa

Một thông báo log điển hình có dạng:

```text
FATAL:  could not receive data from WAL stream:
ERROR:  requested WAL segment ... has already been removed
```

Thông báo này cho biết standby cần một segment mà primary không còn cung cấp qua luồng streaming hiện tại. Nguyên nhân có thể gồm:

- Standby ngừng hoạt động lâu hơn lượng WAL được giữ.
- Slot không được cấu hình hoặc slot đã bị xóa.
- Slot vượt `max_slot_wal_keep_size` và bị mất trạng thái bảo đảm WAL.
- Một slot được tạo lại ở vị trí mới trong khi standby vẫn cần WAL cũ.
- WAL archive thiếu segment hoặc retention đã xóa segment cần thiết.
- Sau failover, standby đang theo timeline cũ hoặc cấu hình kết nối sai primary.

Không thể kết luận phải rebuild chỉ từ một dòng log. Trước tiên xác định segment cụ thể, timeline, slot và archive. Nếu archive có đủ WAL liên tục, standby có thể tiếp tục recovery bằng `restore_command`. Nếu không có segment cần thiết ở bất kỳ nguồn nào, standby không thể replay qua khoảng trống đó và thường phải được dựng lại từ một base backup phù hợp.

## 12. Quy trình điều tra khi replication lag tăng

Thực hiện theo thứ tự để xác định điểm nghẽn:

1. Xác nhận node nào là primary và standby; kiểm tra timeline và endpoint hiện tại.
2. Trên primary, lấy mẫu `pg_stat_replication` và các LSN send/write/flush/replay.
3. Trên standby, lấy mẫu `pg_stat_wal_receiver`, receive LSN và replay LSN.
4. Xác định khoảng cách đang tăng ở giai đoạn gửi, ghi, flush hay replay.
5. Kiểm tra log PostgreSQL ở cả hai phía để tìm lỗi kết nối, authentication, WAL segment hoặc recovery conflict.
6. Đo CPU, memory, storage latency, throughput, network và workload trên standby.
7. Kiểm tra slot, `restart_lsn`, WAL retained, `wal_status` và `safe_wal_size` nếu có.
8. Kiểm tra `pg_stat_archiver` và khả năng truy xuất WAL archive.
9. Đánh giá lag theo yêu cầu nghiệp vụ và trạng thái synchronous/asynchronous replication.
10. Chọn biện pháp dựa trên nguyên nhân, rồi theo dõi nhiều mẫu để xác nhận tiến độ đã phục hồi.

### Kiểm tra conflict trên hot standby

Truy vấn dài trên standby có thể xung đột với việc replay WAL, đặc biệt khi primary cần dọn phiên bản hàng hoặc thay đổi cấu trúc. Xem thống kê conflict:

```sql
SELECT *
FROM pg_stat_database_conflicts;
```

Các bộ đếm conflict có thể giúp xác định query bị hủy trong recovery. `hot_standby_feedback` có thể giảm một số conflict bằng cách gửi thông tin xmin về primary, nhưng có thể khiến primary giữ dead tuples lâu hơn và tăng nguy cơ table bloat. Đây là một đánh đổi, không phải bật mặc định để xử lý mọi lag.

## 13. Quy trình xử lý replication slot bị bỏ quên

Slot bị bỏ quên cần được xử lý có kiểm soát vì nó có thể là nguồn WAL duy nhất cho một consumer đang tạm ngừng.

### Bước 1: xác định chủ sở hữu

Đối chiếu `slot_name`, `slot_type`, `database`, `active`, `active_pid`, `restart_lsn` với:

- Danh sách physical standby và cấu hình `primary_slot_name`.
- Logical subscription trên các subscriber.
- CDC connector và cấu hình slot name.
- Hệ thống backup hoặc công cụ logical decoding.
- Lịch bảo trì, migration và decommission gần đây.

Kiểm tra trên hệ thống quản lý cấu hình, không suy đoán owner chỉ từ tên slot. Slot có thể được dùng bởi một consumer ngoài nhóm đang trực tiếp quản trị database.

### Bước 2: xác nhận consumer đã ngừng vĩnh viễn

Kiểm tra ứng dụng/connector đã được retire, không còn kế hoạch khôi phục và dữ liệu downstream đã được xác nhận. Với logical slot, đánh giá cả tác động của `catalog_xmin`. Với physical slot, xác định standby có base backup mới và đã chuyển sang slot khác hay không.

### Bước 3: đánh giá dung lượng và rủi ro

Ước lượng WAL giữ bởi slot, tốc độ sinh WAL và dung lượng còn trống. Nếu `pg_wal` đang gần đầy, ưu tiên quy trình ứng phó dung lượng của hệ thống, nhưng vẫn phải xác định slot nào có thể giải phóng an toàn. Không xóa thủ công các WAL segment.

### Bước 4: gỡ slot đúng cách

Slot không hoạt động có thể được gỡ bằng SQL:

```sql
SELECT pg_drop_replication_slot('retired_cdc_slot');
```

Lệnh sẽ thất bại nếu slot đang active. Không cố ép xóa bằng cách kill process khi chưa xác định đúng consumer và tác động. Nếu slot thuộc subscription, quản lý subscription theo quy trình của nó; xóa slot thủ công trong khi subscription còn hoạt động có thể làm subscriber lỗi hoặc buộc đồng bộ lại.

### Bước 5: xác nhận WAL được giải phóng

Việc drop slot không nhất thiết làm filesystem giảm dung lượng ngay lập tức. PostgreSQL có thể chỉ tái sử dụng/xóa segment sau checkpoint và khi các yêu cầu WAL khác không còn cần segment đó. Theo dõi `pg_replication_slots`, `pg_stat_archiver`, checkpoint và dung lượng `pg_wal` theo thời gian.

## 14. Khi nào standby có thể bắt kịp mà không rebuild?

Standby có thể tiếp tục mà không cần base backup mới nếu mọi WAL cần thiết từ vị trí standby đang có đến WAL hiện tại vẫn có thể được cung cấp liên tục. Các nguồn có thể gồm:

- WAL còn trong `pg_wal` trên primary.
- WAL được giữ bởi replication slot hợp lệ.
- WAL segment đầy đủ trong archive và standby có `restore_command` hoạt động.
- Một nguồn WAL khác được thiết kế hỗ trợ recovery cho đúng timeline.

Nếu thiếu một segment ở giữa và không có bản archive/backup nào chứa segment đó, recovery không thể nhảy qua khoảng trống. Việc tạo slot mới ở LSN hiện tại không tái tạo được WAL cũ đã mất.

### Kiểm tra archive trước khi rebuild

1. Ghi lại tên segment và timeline từ log standby.
2. Tìm segment trong archive và xác minh checksum/kích thước nếu quy trình lưu trữ hỗ trợ.
3. Xác nhận các segment trước/sau tạo thành chuỗi liên tục.
4. Kiểm tra `restore_command` trên standby có thể đọc archive.
5. Theo dõi log recovery để xác nhận standby lấy được segment và replay tiến lên.
6. Khi standby bắt kịp, xác nhận streaming tiếp tục và slot có trạng thái hợp lệ.

Không tự đổi tên segment hoặc sửa nội dung WAL. WAL phải được phục hồi nguyên vẹn từ nguồn hợp lệ.

## 15. Dựng lại standby bằng base backup

Nếu WAL bắt buộc đã mất và archive không thể cung cấp, cách khôi phục thông thường là tạo standby mới từ base backup của primary hiện tại. Đây là thao tác thay thế data directory của standby, vì vậy cần dừng đúng instance và bảo đảm backup được lấy từ đúng primary/timeline.

### Chuẩn bị

- Xác nhận primary hiện tại, địa chỉ, database cluster và timeline.
- Xác nhận có đủ dung lượng để tạo base backup.
- Kiểm tra quyền replication của role backup.
- Xác định slot physical sẽ dùng; kiểm tra slot cũ có thể tái sử dụng hay cần tạo slot mới.
- Xác nhận `wal_level`, `max_wal_senders`, `max_replication_slots` và retention phù hợp.
- Dừng standby theo runbook và sao lưu/di chuyển data directory cũ nếu cần điều tra.
- Đảm bảo đích `-D` trống và đúng data directory của instance.

### Ví dụ dùng `pg_basebackup`

Trường hợp tạo slot mới có tên `standby_b_slot`:

```bash
pg_basebackup \
  -h primary.internal \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/data \
  -Fp \
  -Xs \
  -P \
  -R \
  -C \
  -S standby_b_slot
```

Các tùy chọn:

- `-D`: thư mục đích của base backup; phải phù hợp với layout cài đặt và thường cần trống.
- `-Fp`: định dạng plain directory.
- `-Xs`: stream WAL trong lúc base backup.
- `-P`: hiển thị tiến độ.
- `-R`: tạo cấu hình standby, bao gồm `standby.signal` và thông tin kết nối trong `postgresql.auto.conf`.
- `-C`: tạo replication slot được chỉ định bằng `-S`.
- `-S`: tên slot replication.

Nếu slot đã tồn tại và đã được xác nhận là slot dành cho standby này, bỏ `-C` và dùng `-S` để kết nối với slot hiện có. Không dùng `-C` khi tên slot đã tồn tại vì thao tác tạo sẽ thất bại. Cần kiểm tra tùy chọn theo phiên bản `pg_basebackup` và mô hình backup đang dùng.

### Khởi động và xác nhận

Sau khi backup hoàn tất, khởi động standby và theo dõi log. Xác nhận:

- `pg_is_in_recovery()` trả `true`.
- `pg_stat_wal_receiver` cho thấy receiver đang hoạt động.
- Primary hiển thị standby trong `pg_stat_replication`.
- `sent_lsn`, `write_lsn`, `flush_lsn`, `replay_lsn` tiến triển.
- Slot được sử dụng đúng và `restart_lsn` cập nhật theo tiến độ.
- Standby không còn báo thiếu WAL và không có lỗi xác thực/network.
- Truy vấn đọc trên standby trả kết quả hợp lệ trong giới hạn lag đã chấp nhận.

Không promote standby chỉ để thử xem nó có hoạt động hay không. Promotion làm thay đổi vai trò/timeline và có thể tạo split-brain nếu primary cũ vẫn ghi.

## 16. Phân biệt mất WAL với timeline divergence

Mất WAL và timeline divergence là hai vấn đề khác nhau. Mất WAL nghĩa là standby thiếu một đoạn WAL cần thiết để replay. Timeline divergence xảy ra khi hai node có lịch sử WAL khác nhau, thường sau khi một node được promote trong khi node khác vẫn thuộc timeline cũ.

Sau failover, primary mới có thể có timeline mới. Node cũ không thể đơn giản tiếp tục như standby nếu nó đã ghi các transaction riêng sau thời điểm phân nhánh. Cần đánh giá khả năng dùng `pg_rewind` hoặc dựng lại bằng base backup.

### Vai trò của `pg_rewind`

`pg_rewind` đồng bộ data directory của một node đã phân nhánh với node nguồn mới sau failover, bằng cách xác định và hoàn tác các thay đổi phân kỳ. Công cụ này không phải phương án chung để bù một WAL segment bị mất trong khi timeline vẫn liên tục.

Các điều kiện quan trọng thường gồm:

- Target phải được shutdown sạch trước khi chạy.
- `full_page_writes` phải được bật theo yêu cầu.
- Cluster cần data checksums được bật khi initdb hoặc `wal_log_hints` được bật theo yêu cầu.
- WAL cần thiết để xác định thay đổi phân kỳ phải còn truy cập được.
- Source và target phải là các cluster tương thích về lịch sử/timeline.

Kiểm tra tài liệu đúng phiên bản và chạy `pg_rewind --dry-run` khi phiên bản hỗ trợ trước khi thực hiện. Nếu không đáp ứng điều kiện, hãy dùng base backup mới. Sau rewind, cần cấu hình lại standby và xác minh streaming trước khi đưa vào phục vụ.

## 17. Phòng ngừa slot mồ côi và mất WAL

### Quản lý vòng đời slot

Mỗi slot nên có metadata quản trị bên ngoài PostgreSQL:

- Tên slot và loại slot.
- Owner/team và hệ thống consumer.
- Primary/database liên quan.
- Ngày tạo, mục đích và thời hạn dự kiến.
- Runbook dừng, migrate và decommission.
- Ngưỡng lag/WAL retention và cảnh báo.

Khi retire standby hoặc connector, phải gỡ subscription/consumer theo quy trình, xác nhận không còn sử dụng rồi mới drop slot. Không để slot chỉ tồn tại vì “có thể cần lại” mà không có owner và giới hạn dung lượng.

### Đặt giới hạn retention có chủ đích

Chọn `max_slot_wal_keep_size` dựa trên tốc độ sinh WAL, thời gian gián đoạn consumer có thể chấp nhận và dung lượng filesystem. Nếu đặt quá nhỏ, standby/connector có thể mất WAL trước khi được khôi phục. Nếu để không giới hạn, một consumer chết lâu có thể làm đầy đĩa.

`wal_keep_size` cũng cần phù hợp với thời gian offline dự kiến của standby không dùng slot. Tuy nhiên, đây không phải cơ chế bảo đảm catch-up cho thời gian outage dài. Archive và base backup là thành phần của chiến lược phục hồi.

### Giám sát archive

Theo dõi `pg_stat_archiver`, lỗi `archive_command`, khoảng thời gian từ lần archive thành công cuối, dung lượng archive và khả năng restore thực tế. Có archive nhưng chưa từng thử restore không chứng minh quy trình recovery hoạt động.

### Theo dõi tốc độ sinh WAL

Lấy hai mẫu LSN cách nhau một khoảng thời gian để ước lượng tốc độ sinh WAL:

```sql
SELECT pg_current_wal_lsn();
```

Nếu hai mẫu là `L1` và `L2` cách nhau `T` giây, tốc độ trung bình xấp xỉ `pg_wal_lsn_diff(L2, L1) / T` byte/giây. Dùng tốc độ cao điểm chứ không chỉ trung bình ngày để ước lượng retention. WAL generation thay đổi theo bulk load, index build, vacuum, update và workload giao dịch.

## 18. Giám sát dung lượng và cảnh báo

Các chỉ số nên có dashboard:

| Nhóm | Chỉ số | Cảnh báo khi |
|---|---|---|
| Replication | Send/write/flush/replay LSN gap | Khoảng cách tăng liên tục hoặc vượt SLA |
| Receiver | `status`, thời điểm nhận message cuối | Receiver dừng hoặc không có tiến triển bất thường |
| Slot | `active`, `restart_lsn`, `wal_status` | Slot inactive lâu, WAL gap tăng, trạng thái `lost` |
| Slot capacity | `safe_wal_size` | Dung lượng an toàn gần 0 |
| WAL | Dung lượng filesystem `pg_wal` | Sử dụng vượt ngưỡng vận hành |
| Archive | `failed_count`, `last_archived_time` | Archive thất bại hoặc không tiến triển |
| Standby | Replay timestamp, conflict, recovery state | Replay chậm hoặc query bị hủy nhiều |
| Host | Disk free, I/O latency, CPU, network | Gần đầy đĩa hoặc nghẽn tài nguyên |

Không dùng một ngưỡng cố định cho mọi cluster. Hệ thống có tốc độ WAL cao cần ngưỡng byte và thời gian khác hệ thống ít ghi. Cảnh báo nên có cả xu hướng và dự báo thời gian đến khi chạm ngưỡng dung lượng.

### Ước lượng thời gian còn lại trước khi đầy đĩa

Nếu `pg_wal` còn `F` byte trống và mức tăng WAL ròng là `R` byte/giây, thời gian thô còn lại xấp xỉ `F / R`. Đây chỉ là ước lượng đơn giản: segment có thể được tái sử dụng sau checkpoint, archive có thể thay đổi, và nhiều slot/backup cùng ảnh hưởng retention. Dùng xu hướng nhiều mẫu và giám sát filesystem thực tế.

## 19. Xử lý sự cố khi `pg_wal` tăng nhanh

Khi dung lượng `pg_wal` tăng bất thường:

1. Xác nhận filesystem nào đang tăng và còn bao nhiêu dung lượng.
2. Kiểm tra `pg_replication_slots` để tìm slot giữ WAL lâu nhất.
3. Xác định owner và trạng thái consumer của từng slot.
4. Kiểm tra `pg_stat_replication`, `pg_stat_wal_receiver` và các LSN.
5. Kiểm tra `pg_stat_archiver` để xem archive có đang thất bại.
6. Kiểm tra tốc độ sinh WAL và workload vừa triển khai.
7. Nếu consumer hợp lệ đang lag, khôi phục consumer hoặc standby để slot tiến lên.
8. Nếu slot đã được retire chắc chắn, gỡ slot theo quy trình đã phê duyệt.
9. Theo dõi checkpoint, WAL reuse và dung lượng sau khi xử lý.

Không xóa file `.wal` trong `pg_wal`, không sửa tên segment và không dùng `rm` để giải phóng dung lượng. PostgreSQL quản lý WAL theo metadata nội bộ; xóa file thủ công có thể làm hỏng khả năng crash recovery và replication.

Nếu filesystem sắp đầy và database có nguy cơ dừng, ưu tiên runbook incident của tổ chức để mở rộng dung lượng hoặc xử lý consumer/slot đã xác định. Không xóa slot ngẫu nhiên chỉ để giảm disk usage.

## 20. Những tình huống dễ gây hiểu nhầm

### `active = false` không đồng nghĩa slot mồ côi

Standby có thể đang shutdown có kế hoạch, connector có thể tạm dừng hoặc consumer chỉ chạy theo lịch. Cần đối chiếu owner và lịch vận hành trước khi drop.

### Replay timestamp cũ không luôn đồng nghĩa lag

Nếu primary không có transaction mới, timestamp replay không thay đổi. Dùng LSN và heartbeat để phân biệt standby idle với standby bị tụt.

### Slot tồn tại không bảo đảm WAL còn đầy đủ

Slot có thể vượt giới hạn `max_slot_wal_keep_size` và mất WAL cần thiết. Kiểm tra `wal_status` và log, không chỉ kiểm tra tên slot có tồn tại.

### `wal_keep_size` không phải quota

Đây là mức WAL tối thiểu cần giữ cho standby, không phải giới hạn tối đa dung lượng `pg_wal`. Slot, archive, checkpoint và các yếu tố khác ảnh hưởng dung lượng thực tế.

### Archive không có nghĩa là recovery chắc chắn thành công

Archive có thể thiếu một segment, sai timeline, lỗi quyền truy cập hoặc không có base backup phù hợp. Cần kiểm tra chuỗi WAL liên tục và thử restore định kỳ.

### Tạo slot mới không khôi phục WAL cũ

Slot mới bắt đầu giữ WAL từ vị trí tạo. Nó không làm sống lại segment đã bị xóa. Nếu standby cần WAL trước vị trí đó, phải lấy từ archive hoặc dựng lại standby.

## 21. Runbook xử lý standby mất WAL

Khi log báo requested WAL segment đã bị xóa, có thể dùng runbook sau:

**Giai đoạn xác định**

1. Ghi lại tên segment, timeline và thời điểm lỗi từ log.
2. Xác định primary hiện tại và standby đang lỗi.
3. Trên primary, kiểm tra slot mà standby dùng và trạng thái WAL retention.
4. Kiểm tra archive có segment thiếu và các segment liên tiếp cần thiết không.
5. Xác nhận timeline có phân nhánh sau failover hay không.

**Giai đoạn phục hồi**

6. Nếu archive đầy đủ, sửa/kiểm tra `restore_command` và cho standby tiếp tục recovery.
7. Nếu WAL không có nhưng timeline không phân nhánh, lên kế hoạch base backup mới.
8. Nếu timeline phân nhánh, đánh giá `pg_rewind` với các điều kiện tiên quyết; nếu không đủ điều kiện, base backup mới.
9. Tạo hoặc gắn slot đúng consumer; chọn retention đủ cho thời gian catch-up dự kiến.
10. Khởi động standby và theo dõi log, receiver, sender và replay.

**Giai đoạn xác nhận**

11. Xác nhận standby đã streaming và LSN tiến triển.
12. Xác nhận lag giảm về ngưỡng vận hành.
13. Xác nhận archive và slot tiếp tục được cập nhật.
14. Ghi nhận nguyên nhân gốc, thời gian gián đoạn và thay đổi phòng ngừa.

## 22. Bài tập thực hành

### Bài 1: Quan sát send/write/flush/replay

Tạo primary và standby trong môi trường thử nghiệm. Chèn dữ liệu trên primary, lấy mẫu `pg_stat_replication` và so sánh bốn LSN. Ghi nhận trường hợp standby nhận WAL nhanh nhưng replay chậm.

### Bài 2: Tạo physical replication slot

Tạo một physical slot cho standby, cấu hình `primary_slot_name`, khởi động standby và xác nhận slot active. Dừng standby có kiểm soát rồi quan sát `restart_lsn` và dung lượng WAL.

### Bài 3: Mô phỏng slot không hoạt động

Trong cluster thử nghiệm, tạo slot và ngừng consumer. Theo dõi `pg_replication_slots`, `pg_wal_lsn_diff` và dung lượng filesystem. Xác định thời điểm cần cảnh báo.

### Bài 4: Quan sát archive

Bật WAL archiving trong môi trường lab, tạo workload ghi và xem `pg_stat_archiver`. Mô phỏng archive command lỗi rồi khôi phục; ghi nhận log và thời gian archive tiến triển trở lại.

### Bài 5: Phục hồi WAL từ archive

Tạo standby thử nghiệm có `restore_command`. Tạm ngắt streaming nhưng giữ archive đầy đủ, sau đó khôi phục kết nối và xác nhận standby lấy segment từ archive khi cần.

### Bài 6: Mô phỏng mất WAL

Chỉ trong môi trường lab có thể dựng lại, cấu hình retention nhỏ và ngừng standby đủ lâu để slot không còn giữ WAL. Quan sát log khi segment không còn; không thực hiện thí nghiệm này trên cluster có dữ liệu cần giữ.

### Bài 7: Dựng lại standby

Dùng `pg_basebackup -R -X stream` để tạo standby mới. Kiểm tra slot, receiver, sender, replay LSN và trạng thái recovery sau khi khởi động.

### Bài 8: Phân biệt lag với idle primary

Để primary không phát sinh transaction trong một khoảng thời gian. So sánh replay timestamp với LSN và heartbeat. Giải thích vì sao timestamp cũ không đủ để kết luận replica lag.

## 23. Câu hỏi ôn tập

**1. Replication lag gồm những giai đoạn nào?**

Send, write, flush và replay. Mỗi giai đoạn phản ánh một phần của quá trình chuyển WAL từ primary sang standby.

**2. Vì sao standby nhận WAL nhưng vẫn trễ?**

WAL receiver có thể ghi nhanh hơn startup process replay. CPU, I/O, transaction lớn hoặc recovery conflict có thể làm backlog replay tăng.

**3. Physical replication slot giữ lại điều gì?**

Nó giữ WAL từ vị trí mà physical consumer còn cần để tiếp tục streaming, chịu ảnh hưởng của giới hạn retention được cấu hình.

**4. Vì sao slot inactive có thể làm đầy đĩa?**

Nếu slot không tiến triển, `restart_lsn` cũ buộc PostgreSQL giữ các WAL segment cần thiết cho slot. WAL mới tiếp tục phát sinh và filesystem có thể tăng đến đầy.

**5. `wal_keep_size` có thay thế replication slot không?**

Không. Nó giữ một lượng WAL tối thiểu cho standby nhưng không theo dõi tiến độ của từng consumer như slot và không bảo đảm catch-up sau outage dài.

**6. `max_slot_wal_keep_size` giúp gì và có rủi ro nào?**

Nó giới hạn WAL được giữ cho slot tại checkpoint để kiểm soát dung lượng. Nếu consumer trễ vượt giới hạn, slot có thể mất WAL cần thiết và phải phục hồi từ archive hoặc dựng lại.

**7. Khi nào standby có thể tiếp tục mà không rebuild?**

Khi toàn bộ WAL cần thiết vẫn có thể được cung cấp liên tục từ `pg_wal`, slot hợp lệ hoặc archive qua `restore_command`.

**8. Vì sao tạo slot mới không giải quyết được WAL đã mất?**

Slot mới bắt đầu giữ WAL từ vị trí tạo, không tái tạo segment cũ đã bị xóa. Standby vẫn cần nguồn WAL cũ hoặc base backup mới.

**9. Khi nào dùng `pg_rewind`?**

Khi node target đã phân nhánh khỏi source sau failover và đáp ứng các điều kiện tiên quyết của `pg_rewind`. Nó không phải công cụ bù một segment WAL bị thiếu trong timeline liên tục.

**10. Vì sao không được xóa WAL file thủ công?**

PostgreSQL quản lý WAL cho crash recovery, archive và replication. Xóa file ngoài cơ chế quản lý có thể làm hỏng khả năng phục hồi và khiến cluster không thể khởi động hoặc đồng bộ.

## 24. Tài liệu tham khảo PostgreSQL

- PostgreSQL Documentation — Monitoring Database Activity: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — Replication Progress Reporting: https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW
- PostgreSQL Documentation — Replication Slots: https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS
- PostgreSQL Documentation — Runtime WAL Configuration: https://www.postgresql.org/docs/current/runtime-config-wal.html
- PostgreSQL Documentation — Archive Recovery Settings: https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-ARCHIVE-RECOVERY
- PostgreSQL Documentation — Continuous Archiving and Point-in-Time Recovery: https://www.postgresql.org/docs/current/continuous-archiving.html
- PostgreSQL Documentation — `pg_basebackup`: https://www.postgresql.org/docs/current/app-pgbasebackup.html
- PostgreSQL Documentation — `pg_rewind`: https://www.postgresql.org/docs/current/app-pgrewind.html
- PostgreSQL Documentation — Warm Standby and Streaming Replication: https://www.postgresql.org/docs/current/warm-standby.html
- PostgreSQL Documentation — Hot Standby: https://www.postgresql.org/docs/current/hot-standby.html

Độ trễ replication, slot bị bỏ quên và standby mất WAL đều cần được xử lý dựa trên vị trí WAL và vai trò của consumer. Theo dõi riêng tiến độ send/write/flush/replay, quản lý owner và vòng đời slot, giới hạn retention có chủ đích, kiểm tra archive và diễn tập dựng lại standby sẽ giúp giảm nguy cơ mất khả năng đồng bộ hoặc đầy đĩa. Khi segment cần thiết đã mất, chỉ archive đầy đủ hoặc một base backup phù hợp mới có thể khôi phục chuỗi WAL hợp lệ.
