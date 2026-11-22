# WAL tăng nhanh, checkpoint dày và tác động I/O

PostgreSQL ghi **Write-Ahead Log (WAL)** trước khi dữ liệu thay đổi trên các data pages được coi là bền vững. WAL giúp database phục hồi sau crash, hỗ trợ replication và point-in-time recovery. Cơ chế **checkpoint** định kỳ đồng bộ các dirty buffers cần thiết xuống data files và ghi nhận điểm bắt đầu phù hợp cho crash recovery.

Khi workload ghi tăng, WAL có thể sinh ra rất nhanh. Nếu PostgreSQL phải checkpoint quá thường xuyên, checkpointer tạo thêm các đợt ghi data pages, tăng I/O, gây cạnh tranh với queries và có thể làm phát sinh nhiều full-page images trong WAL. Nếu WAL giữ lại quá lâu vì archive hoặc replication slot bị chậm, thư mục pg_wal có thể tăng dung lượng dù checkpoint vẫn diễn ra. Hai hiện tượng này có liên quan nhưng không đồng nghĩa: **WAL generation** là tốc độ tạo log; **WAL retention** là lượng log chưa thể recycle.

Bài học này giải thích cách WAL và checkpoint phối hợp, vì sao checkpoint dày ảnh hưởng hiệu năng, cách đọc metrics và cách điều chỉnh an toàn. Mục tiêu không phải giảm WAL bằng mọi giá. WAL là nền tảng durability/recovery; mục tiêu là tạo WAL ở mức workload cần thiết, checkpoint với nhịp phù hợp, giữ I/O ổn định và đảm bảo WAL được archive/replicate/recycle đúng hạn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích WAL và nguyên tắc write-ahead.
2. Phân biệt WAL generation, WAL flush, WAL write, WAL archive và WAL retention.
3. Mô tả checkpoint, dirty buffers, redo point và crash recovery.
4. Phân biệt timed checkpoints với requested checkpoints.
5. Giải thích vai trò của max_wal_size, min_wal_size, checkpoint_timeout và checkpoint_completion_target.
6. Hiểu full-page images (FPI), full_page_writes và ảnh hưởng tới WAL volume.
7. Phân biệt checkpointer, background writer và backend writes.
8. Đọc metrics từ pg_stat_wal, checkpoint statistics, pg_stat_archiver và replication slots.
9. Theo dõi WAL generation rate, checkpoint frequency, checkpoint write/sync time và storage latency.
10. Phân biệt checkpoint pressure với WAL retention do archive/replication backlog.
11. Tuning checkpoint/WAL settings dựa trên số đo và recovery objectives.
12. Xử lý tình huống WAL tăng nhanh, checkpoint dày, archive chậm, replica lag hoặc disk gần đầy.

> **Phiên bản PostgreSQL:** Các view thống kê checkpoint thay đổi từ PostgreSQL 17. Bài có ví dụ tách theo phiên bản: PostgreSQL 16 trở xuống và PostgreSQL 17 trở lên. Luôn kiểm tra schema view và settings trên major version thực tế trước khi dùng dashboard/SQL cố định.

## 2. WAL là gì?

**Write-Ahead Log** là luồng records mô tả những thay đổi cần thiết để PostgreSQL phục hồi database. Khi transaction thay đổi row, index hoặc page metadata, PostgreSQL ghi WAL records tương ứng.

Nguyên tắc write-ahead:

```text
1. Ghi WAL mô tả thay đổi.
2. Đảm bảo WAL cần thiết được flush bền vững theo durability semantics.
3. Sau đó data pages có thể được ghi xuống data files.
```

WAL cho phép PostgreSQL không cần đồng bộ mọi data page ngay lúc transaction commit. Thay vào đó, transaction commit có thể đợi WAL flush; data pages sẽ được ghi dần bởi background processes/checkpointer.

### Vì sao không chỉ ghi data files?

Nếu server crash giữa lúc ghi một page, data page có thể bị ghi dở hoặc chứa một phần thay đổi. WAL cung cấp lịch sử đủ để replay các thay đổi cần thiết sau crash, trong giới hạn của recovery configuration.

### WAL chứa gì?

WAL records có thể mô tả:

- Heap tuple changes.
- Index page changes.
- Page initialization và metadata changes.
- Transaction commit/abort records.
- Full-page images khi cần bảo vệ trước torn-page writes.
- Các thay đổi hệ thống khác cần cho recovery/replication.

Không phải mỗi SQL statement tương ứng một WAL record. Một statement có thể sinh nhiều records, và một record có thể liên quan nhiều thao tác nội bộ.

## 3. WAL và transaction COMMIT

Một transaction thay đổi dữ liệu:

```text
BEGIN
  UPDATE rows
  INSERT index entries
  DELETE old versions
COMMIT
  ↓
WAL records đã được tạo
  ↓
WAL flush theo synchronous_commit/durability policy
  ↓
COMMIT được xác nhận cho client
  ↓
Data pages có thể được ghi xuống sau
```

Trong cấu hình mặc định phổ biến, synchronous_commit=on khiến commit chờ WAL flush trên primary. Nếu synchronous replication được cấu hình, mức chờ có thể còn phụ thuộc replica acknowledgment và synchronous_standby_names.

### WAL flush không phải checkpoint

Đây là điểm cần phân biệt:

- **WAL flush:** đảm bảo phần WAL cần thiết đã được ghi bền vững theo policy của transaction.
- **Checkpoint:** đồng bộ các data pages cần thiết và thiết lập recovery point mới.

Một transaction có thể đã commit bền vững dù data pages của nó chưa được ghi xuống data files; crash recovery dùng WAL để hoàn tất.

## 4. WAL generation, write, flush và archive

Các thuật ngữ thường gặp:

| Khái niệm | Ý nghĩa |
|---|---|
| WAL generation | Tốc độ PostgreSQL tạo WAL records |
| WAL write | WAL bytes được chuyển từ buffers tới OS/file |
| WAL flush | WAL được flush tới durable storage theo semantics của server |
| WAL archive | WAL segments được sao chép sang archive destination |
| WAL replay | Standby/recovery đọc và áp dụng WAL |
| WAL retention | WAL cũ chưa thể recycle/xóa vì còn cần cho archive, replication hoặc recovery |

### Một ví dụ

Primary tạo 200 GB WAL mỗi giờ. Archive destination chỉ nhận 100 GB mỗi giờ. Khi backlog tăng, WAL segments có thể được giữ lại trong pg_wal; dung lượng disk tăng dù checkpoint đang chạy.

### Không nhầm WAL archive với WAL flush

Transaction commit không cần đợi archive_command copy segment trừ khi có cấu hình/ứng dụng đặc biệt ở lớp ngoài. Archiving là một cơ chế giữ WAL để backup/PITR, độc lập với commit flush thông thường.

## 5. WAL segment và thư mục pg_wal

WAL được lưu theo các **segment files** trong thư mục pg_wal. Kích thước segment mặc định thường là 16 MB, nhưng có thể được chọn khi khởi tạo cluster.

Các segment được đặt tên theo timeline/log/segment identifiers. PostgreSQL có thể:

- Tạo segment mới khi cần.
- Recycle segment cũ bằng cách đổi tên để tái sử dụng.
- Xóa segment không còn cần thiết.
- Giữ segment vì archive, replication slots hoặc wal_keep_size.

### Tại sao số file trong pg_wal không chỉ phụ thuộc WAL generation?

Dung lượng pg_wal phụ thuộc cả:

- Tốc độ tạo WAL.
- Checkpoint và recycle policy.
- min_wal_size/max_wal_size.
- Archive backlog.
- Replication slots và restart LSN.
- wal_keep_size.
- Recovery/standby requirements.

max_wal_size là một ngưỡng mềm để điều phối checkpoint, **không phải hard quota đảm bảo thư mục pg_wal không bao giờ vượt mức đó**.

## 6. Checkpoint là gì?

Checkpoint là một mốc trong WAL/recovery process mà PostgreSQL đảm bảo các data pages cần thiết trước checkpoint đã được ghi xuống data files. Checkpoint record lưu thông tin cần cho crash recovery, trong đó có redo point phù hợp.

Ở mức khái niệm:

```text
Dirty buffers trong shared_buffers
       ↓
Checkpointer ghi các data pages cần thiết
       ↓
Flush/sync data files theo checkpoint protocol
       ↓
Ghi checkpoint record và cập nhật control metadata
       ↓
Crash recovery có thể bắt đầu từ redo point mới
```

### Vì sao cần checkpoint?

Nếu chỉ dựa vào WAL từ lúc database được tạo, crash recovery có thể phải replay một lượng WAL rất lớn. Checkpoint tạo recovery starting point mới, giới hạn phạm vi WAL cần replay trong crash recovery thông thường.

Checkpoint không có nghĩa mọi WAL trước checkpoint đều có thể bị xóa ngay. Archive, replication slots, standby và backup/PITR có thể vẫn cần một số WAL segments cũ hơn.

## 7. Dirty buffers là gì?

PostgreSQL cache data pages trong shared_buffers. Khi một page được thay đổi, page đó trở thành **dirty buffer** cho đến khi được ghi xuống data files.

Ví dụ:

1. UPDATE một row trên heap page.
2. PostgreSQL thay đổi page trong shared buffers và tạo WAL.
3. Transaction commit sau khi WAL được flush.
4. Heap page có thể vẫn dirty trong shared buffers.
5. Checkpointer/background writer hoặc backend ghi page xuống storage.

### Vì sao không flush data page ở mỗi COMMIT?

Một page có thể được cập nhật nhiều lần bởi nhiều transactions. Ghi data page ngay mỗi lần commit sẽ tạo nhiều random writes và tăng latency. WAL cho phép gom việc ghi data pages và thực hiện theo chiến lược quản lý buffer/checkpoint.

### WAL-before-data

Trước khi data page được ghi bền vững, WAL tương ứng phải được flush tới vị trí cần thiết. Điều này bảo vệ khả năng redo nếu data page bị ghi dở.

## 8. Timed checkpoint và requested checkpoint

PostgreSQL có thể tạo checkpoint vì hai nhóm lý do chính:

**Timed checkpoint:** đến giới hạn thời gian checkpoint_timeout.

**Requested checkpoint:** lượng WAL sinh ra từ checkpoint gần nhất đã vượt ngưỡng dựa trên max_wal_size, hoặc có yêu cầu checkpoint thủ công/đặc biệt.

### Vì sao requested checkpoints đáng chú ý?

Nếu workload tạo WAL nhanh, max_wal_size có thể bị chạm trước checkpoint_timeout. PostgreSQL phải checkpoint sớm hơn lịch dự kiến. Nếu điều này lặp lại, checkpoint frequency tăng, data write I/O dày và FPI có thể tăng.

### Không phải mọi requested checkpoint đều do WAL rate

Lệnh CHECKPOINT thủ công và một số hoạt động quản trị/recovery có thể yêu cầu checkpoint. Khi phân tích metrics, kết hợp logs và hoạt động hệ thống để hiểu nguyên nhân.

## 9. max_wal_size và min_wal_size

max_wal_size điều khiển mức WAL được phép tích tụ trước khi PostgreSQL yêu cầu checkpoint sớm hơn. Đây là **soft limit**:

- WAL generation spike có thể làm vượt ngưỡng trước khi checkpoint hoàn tất.
- Archive/replication slot có thể giữ segment không được recycle.
- wal_keep_size có thể yêu cầu giữ lại WAL cho standby.
- Một số recovery/backup situations có thể giữ WAL lâu hơn.

min_wal_size là mức WAL tối thiểu PostgreSQL cố gắng giữ/recycle để tránh liên tục tạo/xóa segment khi workload dao động.

### Xem cấu hình

```sql
SHOW min_wal_size;
SHOW max_wal_size;
```

Ví dụ minh họa cấu hình:

```text
min_wal_size = 2GB
max_wal_size = 16GB
```

Các giá trị này không phải khuyến nghị cho mọi server. Cần tính theo WAL generation rate, disk headroom, checkpoint duration, recovery time objective và archive/replication requirements.

## 10. checkpoint_timeout

checkpoint_timeout là khoảng thời gian tối đa giữa các automatic checkpoints theo time-based scheduling.

```sql
SHOW checkpoint_timeout;
```

Nếu checkpoint_timeout ngắn:

- Timed checkpoints xảy ra thường xuyên hơn.
- Data pages có thể bị ghi dày hơn.
- Recovery thường có ít WAL phải replay hơn từ checkpoint gần nhất.

Nếu checkpoint_timeout dài:

- Có thể giảm timed checkpoint frequency.
- Có thể tăng lượng WAL cần giữ/replay trong crash recovery.
- Dirty buffers có thể tích tụ lâu hơn trước checkpoint.
- Requested checkpoint vẫn có thể xảy ra sớm nếu chạm max_wal_size.

### Không phải chỉ tăng checkpoint_timeout là đủ

Nếu max_wal_size quá thấp so với WAL rate, requested checkpoints vẫn dày. Cần đọc cả checkpoint reasons và WAL generation.

## 11. checkpoint_completion_target

checkpoint_completion_target điều khiển phần khoảng thời gian checkpoint được dùng để trải đều công việc ghi data pages, thay vì dồn writes vào một burst ngắn.

Ví dụ, giá trị 0.9 có nghĩa PostgreSQL cố gắng phân bố checkpoint writes trong phần lớn khoảng thời gian checkpoint cho phép, theo thuật toán scheduling của server.

```sql
SHOW checkpoint_completion_target;
```

### Tác động

- Target cao thường làm checkpoint writes trải đều hơn.
- Giảm khả năng tạo một write burst quá ngắn.
- Có thể làm I/O load ổn định hơn trong thời gian checkpoint.
- Checkpoint vẫn cần hoàn tất; nếu storage không theo kịp, checkpoint có thể vượt lịch.

### Không phải throttle tuyệt đối

checkpoint_completion_target không giới hạn mọi writes của database. Backend, background writer, WAL writer và các process khác vẫn có thể tạo I/O ngoài checkpoint write scheduling.

## 12. Full-page images (FPI)

Với full_page_writes=on, PostgreSQL có thể ghi **full-page image** của một page vào WAL ở lần thay đổi đầu tiên của page sau checkpoint. Điều này bảo vệ trước torn-page writes: nếu page chỉ được ghi một phần khi crash, recovery có thể khôi phục page image rồi replay các WAL records sau đó.

### Ví dụ

Sau checkpoint:

1. Page P chưa được sửa.
2. Transaction đầu tiên sửa P.
3. PostgreSQL ghi một FPI của P vào WAL.
4. Các thay đổi tiếp theo trên P trong cùng chu kỳ có thể chỉ ghi WAL records delta phù hợp, cho đến khi checkpoint tiếp theo thay đổi trạng thái.

### Vì sao checkpoint dày có thể làm WAL tăng thêm?

Checkpoint thường xuyên làm cửa sổ “lần sửa đầu tiên sau checkpoint” xuất hiện thường xuyên hơn. Với workload chạm nhiều pages, số FPI có thể tăng đáng kể. Vì vậy checkpoint quá dày có thể làm tăng cả data write I/O lẫn WAL generation.

## 13. full_page_writes và wal_compression

Kiểm tra:

```sql
SHOW full_page_writes;
SHOW wal_compression;
SHOW wal_level;
```

### full_page_writes

Thông thường nên giữ bật để bảo vệ trước torn-page writes. Tắt nó có thể giảm WAL volume trong một số workload nhưng làm tăng rủi ro corruption sau crash/storage failure. Không tắt chỉ để giảm disk I/O.

### wal_compression

wal_compression có thể nén full-page images trong WAL, giảm bytes ghi ra khi FPI lớn. Đổi lại, server dùng thêm CPU để nén/giải nén. Hiệu quả phụ thuộc dữ liệu/page patterns và thuật toán được hỗ trợ bởi version.

### WAL level

wal_level quyết định lượng thông tin WAL phục vụ standby/replication/logical decoding. logical có thể cần nhiều thông tin hơn replica cho logical decoding; không giảm WAL level nếu kiến trúc replication/CDC/backup yêu cầu mức hiện tại.

## 14. Vì sao FPI có thể tạo write amplification?

Giả sử một workload sửa 100.000 heap pages trong mỗi checkpoint cycle. Với full_page_writes bật, lần sửa đầu tiên của mỗi page sau checkpoint có thể tạo một full-page image. Nếu page size 8 KB, lượng FPI thô lý thuyết có thể lên tới hàng trăm MB cho một vòng, trước khi tính nén và các WAL records khác.

### Những yếu tố ảnh hưởng

- Số lượng pages khác nhau bị chạm sau checkpoint.
- Tần suất checkpoint.
- Kích thước page và tuple/page layout.
- full_page_writes và wal_compression.
- Workload update pattern: hot pages hay phân bố rộng.
- Các hoạt động như index build/bulk load và page initialization.

Một workload sửa đi sửa lại một nhóm pages nhỏ có thể tạo FPI profile khác với workload chạm ngẫu nhiên hàng triệu pages, dù số rows UPDATE giống nhau.

### Xem số FPI

View pg_stat_wal cung cấp bộ đếm wal_fpi ở các PostgreSQL versions hỗ trợ:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

wal_fpi là số full-page images được ghi trong WAL theo thống kê; dùng delta theo thời gian để hiểu xu hướng.

## 15. Checkpointer, background writer và backend writes

Ba nhóm hoạt động ghi data buffers thường được nhắc tới:

**Checkpointer:** ghi dirty buffers theo checkpoint process để bảo đảm recovery point.

**Background writer (bgwriter):** chủ động ghi một số dirty buffers để giữ sẵn buffers sạch, giảm khả năng backend phải tự ghi page khi cần cấp phát buffer mới.

**Backend processes:** query/transaction backends có thể phải ghi dirty buffers trong một số tình huống khi cần buffer sạch và bgwriter chưa kịp chuẩn bị.

### Khác nhau ở mục tiêu

| Process | Mục tiêu |
|---|---|
| Checkpointer | Hoàn tất checkpoint, đồng bộ pages cần thiết cho recovery |
| Background writer | Duy trì pool buffers sạch, làm mượt việc cấp phát buffer |
| Backend | Tiến hành query/update; đôi khi phải tự ghi buffer để tiếp tục |

Không nhầm background writer với checkpointer. Tăng bgwriter không thay việc checkpoint; checkpoint cũng không đơn giản là “bgwriter chạy mạnh hơn”.

## 16. Checkpoint tạo I/O như thế nào?

Một checkpoint có thể:

1. Xác định dirty buffers cần ghi.
2. Phân bố các write requests theo checkpoint scheduling.
3. Ghi data pages ra data files.
4. Sync các files cần thiết theo checkpoint protocol.
5. Hoàn tất checkpoint metadata/WAL record.

### Hai phần thời gian

Trong checkpoint statistics thường có:

- **write time:** thời gian checkpointer dành cho việc ghi buffers.
- **sync time:** thời gian đồng bộ files tới storage.

Nếu write time lớn, checkpointer đang phải ghi nhiều pages hoặc storage throughput thấp. Nếu sync time cao, fsync/storage flush latency có thể là vấn đề.

### Tại sao checkpoint spike làm query chậm?

Checkpoint writes dùng cùng storage bandwidth với foreground queries, WAL writes, autovacuum, index builds và replication/backup reads. Khi device queue dài hoặc IOPS/throughput bị giới hạn, query reads/writes có thể tăng latency dù SQL plan không đổi.

## 17. checkpoint_completion_target và I/O smoothing

Ví dụ minh họa:

```text
checkpoint interval ~ 5 minutes

target 0.5:
  cố gắng trải phần lớn writes trong khoảng ~2.5 minutes

target 0.9:
  cố gắng trải writes trong khoảng ~4.5 minutes
```

Đây là cách hình dung, không phải cam kết lịch chính xác. Checkpoint scheduling có các giới hạn và điều chỉnh dựa trên số buffers/dirty pages, thời gian trước đó và workload.

### Nếu target quá thấp

Writes có thể tập trung hơn, tạo burst lớn hơn và làm storage latency tăng trong một khoảng ngắn.

### Nếu target quá cao

Checkpointer cố gắng trải công việc gần hết khoảng checkpoint. Khi checkpoint tiếp theo đến sớm hoặc storage không đủ throughput, các checkpoint có thể chồng lấn về tải và tạo pressure. PostgreSQL không cho phép checkpoint writes kéo dài vô hạn mà không có giới hạn.

Mặc định thường gặp ở các bản PostgreSQL hiện đại là 0.9; hãy đọc SHOW thay vì dựa vào trí nhớ.

## 18. checkpoint_timeout và max_wal_size phối hợp

Hai settings này tạo hai giới hạn khác nhau:

- checkpoint_timeout tạo checkpoint theo thời gian.
- max_wal_size tạo áp lực requested checkpoint khi WAL tích lũy quá ngưỡng.

Ví dụ:

```text
checkpoint_timeout = 5 min
max_wal_size = 1 GB
WAL generation = 500 MB/min

WAL threshold có thể bị chạm sau khoảng 2 minutes,
trước khi timed checkpoint 5 minutes tới.
```

Ví dụ giả định bỏ qua overhead và WAL recycling details. Nó cho thấy tăng checkpoint_timeout không có tác dụng nếu WAL threshold vẫn bị chạm liên tục.

### Cách tư duy

Đầu tiên đo WAL bytes/second và checkpoint counts. Sau đó chọn max_wal_size đủ để tránh requested checkpoints quá dày trong workload bình thường, nhưng vẫn đảm bảo disk headroom và recovery objective.

## 19. WAL generation rate

Muốn biết WAL tăng nhanh đến đâu, cần đo **delta WAL bytes trong một khoảng thời gian**:

\[
\text{WAL rate}
= \frac{\Delta \text{wal\_bytes}}{\Delta t}
\]

Ví dụ:

```text
WAL bytes lúc 10:00 = 80 GB
WAL bytes lúc 10:05 = 92 GB

Delta = 12 GB / 300 seconds
Rate = 40 MB/s
```

Số liệu ví dụ dùng đơn vị thập phân. Trong dashboard nên ghi rõ MB/s hay MiB/s.

### Lưu ý

- pg_stat_wal counters là cumulative kể từ stats reset.
- Nếu statistics reset giữa hai samples, delta có thể âm/không hợp lệ.
- So sánh hai samples có timestamp rõ ràng.
- Không lấy wal_bytes hiện tại chia uptime nếu muốn phát hiện spike ngắn.

## 20. Đo WAL rate bằng pg_stat_wal

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

Lưu kết quả ở hai thời điểm rồi tính delta:

| Metric | Ý nghĩa |
|---|---|
| wal_records | Số WAL records |
| wal_fpi | Số full-page images |
| wal_bytes | Tổng bytes WAL được tạo |
| wal_buffers_full | Số lần WAL buffers đầy, dẫn tới process phải hỗ trợ flush WAL buffers |
| stats_reset | Thời điểm statistics reset |

### wal_buffers_full

Nếu counter tăng nhanh, workload có thể đang tạo WAL nhanh so với việc WAL buffers được tiêu thụ/flush. Không tự kết luận chỉ cần tăng wal_buffers; xem WAL write/flush latency, commit rate, storage và workload trước.

## 21. Đo WAL rate qua LSN

Một cách khác là lấy LSN ở hai thời điểm:

```sql
SELECT pg_current_wal_lsn();
```

Sau đó tính chênh lệch:

```sql
SELECT pg_size_pretty(
    pg_wal_lsn_diff(
        '0/90000000'::pg_lsn,
        '0/80000000'::pg_lsn
    )::bigint
) AS wal_generated;
```

Các LSN trong ví dụ là giá trị giả định để minh họa phép trừ; khi vận hành hãy thay bằng hai samples thật theo thứ tự mới trừ cũ.

### WAL bytes và LSN distance

LSN distance đo bytes trong WAL address space giữa hai vị trí; pg_stat_wal.wal_bytes đo lượng WAL bytes theo thống kê. Chúng thường hữu ích theo cách khác nhau và có thể khác do segment gaps, timeline/restart context và thời điểm sample.

## 22. Đo checkpoint statistics trên PostgreSQL 16 trở xuống

Ở PostgreSQL 16 và các phiên bản trước, nhiều checkpoint metrics nằm trong pg_stat_bgwriter:

```sql
SELECT
    checkpoints_timed,
    checkpoints_req,
    checkpoint_write_time,
    checkpoint_sync_time,
    buffers_checkpoint,
    buffers_clean,
    maxwritten_clean,
    buffers_backend,
    buffers_backend_fsync,
    buffers_alloc,
    stats_reset
FROM pg_catalog.pg_stat_bgwriter;
```

### Diễn giải

- checkpoints_timed: số timed checkpoints.
- checkpoints_req: số requested checkpoints.
- checkpoint_write_time: tổng thời gian ghi checkpoint buffers (milliseconds).
- checkpoint_sync_time: tổng thời gian sync checkpoint files (milliseconds).
- buffers_checkpoint: số buffers checkpointer ghi.
- buffers_clean: số buffers background writer ghi.
- maxwritten_clean: số lần bgwriter dừng vì chạm giới hạn pages trong một round.
- buffers_backend: số buffers do backends tự ghi.
- buffers_backend_fsync: số lần backend phải tự fsync vì cần flush.
- buffers_alloc: số buffers được cấp phát.

Các counters là cumulative; dùng delta theo khoảng thời gian và chia cho thời gian để hiểu rate.

## 23. Đo checkpoint statistics trên PostgreSQL 17 trở lên

Từ PostgreSQL 17, checkpoint statistics được tách sang pg_stat_checkpointer; pg_stat_bgwriter tập trung vào background writer. Trên server mới:

```sql
SELECT
    num_timed,
    num_requested,
    restartpoints_timed,
    restartpoints_req,
    restartpoints_done,
    write_time,
    sync_time,
    buffers_written,
    stats_reset
FROM pg_catalog.pg_stat_checkpointer;
```

Và background writer:

```sql
SELECT
    buffers_clean,
    maxwritten_clean,
    buffers_alloc,
    stats_reset
FROM pg_catalog.pg_stat_bgwriter;
```

### Không chạy query phiên bản sai

Các cột checkpoints_timed/checkpoints_req và checkpoint_write_time/checkpoint_sync_time không còn nằm trong pg_stat_bgwriter ở PG17 như các bản trước. Dashboard phải có query riêng theo major version.

Nếu một cột không tồn tại, kiểm tra schema:

```sql
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name IN (
      'pg_stat_checkpointer',
      'pg_stat_bgwriter',
      'pg_stat_wal'
  )
ORDER BY table_name, ordinal_position;
```

## 24. Checkpoint frequency và tỷ lệ requested checkpoints

Trên PostgreSQL 16 trở xuống:

```sql
SELECT
    checkpoints_timed,
    checkpoints_req,
    round(
        100.0 * checkpoints_req
        / NULLIF(checkpoints_timed + checkpoints_req, 0),
        2
    ) AS requested_pct
FROM pg_catalog.pg_stat_bgwriter;
```

Trên PostgreSQL 17 trở lên:

```sql
SELECT
    num_timed,
    num_requested,
    round(
        100.0 * num_requested
        / NULLIF(num_timed + num_requested, 0),
        2
    ) AS requested_pct
FROM pg_catalog.pg_stat_checkpointer;
```

### Cách diễn giải

Requested checkpoints chiếm tỷ lệ cao có thể cho thấy WAL generation vượt max_wal_size trước timed schedule. Nhưng phải xét cả checkpoint thủ công và hoạt động đặc biệt; một tỷ lệ không đủ để kết luận hệ thống bị cấu hình sai.

Quan trọng hơn là delta per minute, thời gian checkpoint và tác động tới I/O/latency.

## 25. Log checkpoint

Setting:

```sql
SHOW log_checkpoints;
SHOW checkpoint_warning;
```

`log_checkpoints=on` ghi log các checkpoint với thông tin như loại checkpoint, thời gian write/sync và buffers được ghi theo version. Đây là nguồn rất hữu ích để xác định checkpoint nào diễn ra thường xuyên và mất bao lâu.

`checkpoint_warning` có thể cảnh báo khi checkpoint do WAL xảy ra quá thường xuyên trong khoảng thời gian ngắn theo cấu hình.

### Ví dụ cách đọc log

Một log có thể thể hiện:

- checkpoint bắt đầu do time hoặc WAL request.
- số buffers được ghi.
- write time và sync time.
- tổng duration.
- WAL distance hoặc thông tin vị trí theo phiên bản.

Định dạng log thay đổi theo version. Dùng log parser theo major version và giữ timestamp/instance identity khi đưa vào dashboard.

### Đừng bật log mà không có retention

Với checkpoint dày, log_checkpoints có thể tạo nhiều log lines. Cấu hình log rotation/retention và alert theo log volume.

## 26. pg_stat_archiver: theo dõi archive

Nếu bật WAL archiving:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_catalog.pg_stat_archiver;
```

### Đọc kết quả

- `archived_count`: số WAL segments archive thành công theo stats.
- `failed_count`: số lần archive thất bại.
- `last_failed_wal`/`last_failed_time`: lần thất bại gần nhất.
- `last_archived_wal`/`last_archived_time`: lần archive thành công gần nhất.

Theo dõi **delta failed_count** và thời gian từ lần archive thành công gần nhất. Một failure đơn lẻ đã được khắc phục khác với failed_count tiếp tục tăng và last_archived_time đứng yên.

### Archive backlog

pg_stat_archiver không trực tiếp đưa ra số WAL segments đang chờ archive. Kết hợp:

- số lượng/dung lượng files trong pg_wal.
- last_archived_time và failed_count.
- log của archive_command hoặc archive library.
- disk usage của archive destination.

## 27. Archive command bị chậm hoặc thất bại

Kiểm tra:

```sql
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
```

Các nguyên nhân thường gặp:

- Destination hết dung lượng.
- Credentials/token hết hạn.
- Network/Object Storage chậm hoặc lỗi.
- Archive command timeout hoặc exit code khác 0.
- Permission/path sai.
- Archive consumer không xử lý kịp tốc độ WAL generation.

### Hệ quả

Nếu WAL segment chưa được archive thành công khi archiving đang yêu cầu, PostgreSQL phải giữ segment đó để retry. Khi backlog tăng, pg_wal có thể lớn lên và tiến tới disk exhaustion.

### Không xóa WAL files thủ công

Không xóa files trong pg_wal bằng filesystem commands. PostgreSQL quản lý lifecycle của WAL segments; xóa thủ công có thể làm hỏng khả năng recovery/replication và khiến cluster không khởi động được.

## 28. Replication slots giữ WAL

Replication slot giữ WAL cần thiết cho standby/logical consumer chưa xác nhận. Nếu consumer chậm hoặc ngừng hoạt động, slot có thể giữ nhiều WAL segments.

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

Ước lượng WAL distance được giữ bởi slot:

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
    ) AS retained_wal_estimate
FROM pg_catalog.pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    restart_lsn
) DESC;
```

Đây là ước lượng LSN distance, không phải phép đo chính xác dung lượng files sẽ bị giữ riêng cho slot nếu nhiều retention requirements chồng lấn.

### Slot inactive

Một slot inactive có thể giữ WAL dù không có consumer hiện đang kết nối. Trước khi drop slot, xác nhận consumer có thể được tạo lại, có cần snapshot lại hay không và ai sở hữu slot.

## 29. max_slot_wal_keep_size

`max_slot_wal_keep_size` giới hạn lượng WAL mà replication slots được phép giữ, với semantics theo checkpoint/version. Nếu vượt giới hạn, slot có thể bị mất khả năng tiếp tục từ WAL cũ và cần reinitialize/resnapshot.

```sql
SHOW max_slot_wal_keep_size;
SHOW wal_keep_size;
```

### Trade-off

- Không giới hạn slot retention: consumer chậm có thể làm pg_wal tăng rất lớn.
- Giới hạn quá thấp: slot có thể bị invalidated trước khi consumer bắt kịp.
- `wal_keep_size`: giữ WAL cho standby theo một mức tối thiểu; nó không thay thế slot logic và archive.

Thiết kế retention phải dựa trên khả năng outage/recovery của consumer, disk headroom và tốc độ WAL generation.

## 30. Theo dõi standby replay lag

Trên primary:

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(sent_lsn, replay_lsn)::bigint
    ) AS send_to_replay_bytes,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

### Phân biệt

- `sent_lsn`: WAL primary đã gửi.
- `write_lsn`: WAL standby đã ghi nhận.
- `flush_lsn`: WAL standby đã flush.
- `replay_lsn`: WAL standby đã replay vào database state.

Nếu sent-to-replay distance lớn, standby có thể đang nhận/replay chậm. `replay_lag` là thống kê thời gian trễ theo semantics view, không thay hoàn toàn LSN distance.

### Lưu ý

`write_lag`, `flush_lag`, `replay_lag` có thể NULL khi không có sample phù hợp; không coi NULL là zero lag.

## 31. WAL generation cao và WAL retention cao là hai vấn đề khác

| Quan sát | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| wal_bytes/s cao, pg_wal size ổn định | Workload tạo WAL nhanh nhưng recycle/archive theo kịp | Tối ưu write workload, FPI, checkpoint |
| wal_bytes/s bình thường, pg_wal size tăng | Archive/slot/standby retention | pg_stat_archiver, slots, replication |
| wal_bytes/s cao, requested checkpoints dày | max_wal_size nhỏ so với generation rate | Checkpoint stats, max_wal_size, workload |
| WAL archive failures tăng | Destination/network/credentials | Archive logs, destination capacity |
| Slot retained distance tăng | Consumer lag/inactive | Slot owner, consumer progress |
| Replica replay lag tăng | Network, standby I/O/CPU, apply bottleneck | pg_stat_replication, standby metrics |

### Một tình huống kết hợp

Checkpoint dày có thể tăng FPI/WAL generation. Archive hoặc slot chậm có thể giữ lại WAL. Khi cả hai xảy ra, pg_wal có thể tăng rất nhanh: vừa tạo nhiều log hơn, vừa recycle chậm hơn.

## 32. Kiểm tra dung lượng pg_wal

Trên server có quyền thích hợp:

```sql
SELECT
    count(*) AS wal_files,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size
FROM pg_catalog.pg_ls_waldir();
```

`pg_ls_waldir()` trả danh sách WAL files và metadata. Quyền thực thi bị giới hạn; tài khoản giám sát có thể cần role/privilege phù hợp.

### Vì sao query không phải luôn đủ?

- File đang được tạo/recycle trong lúc sample.
- Có segment files được giữ vì nhiều lý do cùng lúc.
- max_wal_size là soft limit.
- Disk usage của toàn volume còn bao gồm archive/logs/data/temp files.

Kết hợp SQL metrics với OS/provider volume metrics. Không dùng riêng số WAL files để kết luận checkpoint bị lỗi.

## 33. WAL directory và disk headroom

Giám sát:

- Tổng size pg_wal.
- Free space của volume chứa pg_wal.
- Archive destination capacity.
- WAL generation rate.
- Slot retained WAL distance.
- Archive failures/backlog.
- Replica lag.

### Tại sao cần headroom?

WAL có thể tăng đột biến trong bulk load, index build, mass UPDATE/DELETE hoặc khi replica/archive ngừng hoạt động. Nếu volume đầy, PostgreSQL có thể không ghi được WAL và database có thể ngừng nhận writes.

### Alert theo tốc độ tăng

Một volume còn 100 GB free nhưng WAL tăng 20 GB/phút có thể sắp gặp sự cố trong vài phút. Theo dõi cả **absolute free bytes** và **time-to-full estimate** từ tốc độ tăng gần đây.
## 34. wal_buffers và WAL writer

WAL records được tạo trong WAL buffers trước khi được ghi ra WAL segment files. `wal_buffers` điều khiển dung lượng shared memory dành cho WAL buffers.

```sql
SHOW wal_buffers;
SHOW wal_writer_delay;
SHOW wal_writer_flush_after;
```

### wal_buffers

Giá trị `-1` thường cho phép PostgreSQL tự chọn kích thước dựa trên shared_buffers theo quy tắc của version. WAL buffers quá nhỏ có thể khiến processes thường xuyên phải hỗ trợ flush; nhưng tăng quá lớn không tự động cải thiện throughput nếu bottleneck là storage hoặc WAL sync latency.

### WAL writer

WAL writer ghi WAL buffers xuống WAL files theo lịch. `wal_writer_delay` và `wal_writer_flush_after` điều khiển một số hành vi flush/batching.

Không nhầm WAL writer với checkpointer: WAL writer ghi **WAL log**, còn checkpointer ghi **data pages** trong checkpoint process.

## 35. synchronous_commit không làm giảm WAL generation

```sql
SHOW synchronous_commit;
```

`synchronous_commit` ảnh hưởng commit acknowledgment/flush behavior, không phải một setting để giảm lượng WAL records được tạo.

Nếu đặt `synchronous_commit=off`, PostgreSQL có thể xác nhận commit trước khi WAL record tương ứng được flush bền vững. Database vẫn nhất quán sau crash, nhưng một số transactions đã được client nhận ACK có thể bị mất trong một cửa sổ crash tương ứng.

### Không dùng như mẹo checkpoint

- Không giảm số heap/index changes.
- Không giải quyết archive backlog.
- Không làm checkpoint biến mất.
- Có thể giảm commit latency trong một số workload, nhưng thay đổi durability guarantee.

Chỉ dùng khi ứng dụng chấp nhận semantics này và có recovery/replay policy rõ ràng. Không thay synchronous_commit để xử lý checkpoint dày.

## 36. fsync và wal_sync_method

Kiểm tra:

```sql
SHOW fsync;
SHOW wal_sync_method;
```

`fsync=on` là thiết lập quan trọng cho durability. Tắt fsync có thể tăng hiệu năng trong một số benchmark nhưng làm rủi ro mất/corrupt dữ liệu sau OS crash hoặc power failure tăng nghiêm trọng.

`wal_sync_method` chọn cơ chế sync WAL phù hợp với platform. Việc đổi method phải dựa trên OS/filesystem/storage semantics và benchmark có kiểm soát.

**Không tắt fsync trên production để xử lý I/O cao.** Nếu storage không đáp ứng fsync workload, giải quyết storage latency/capacity hoặc điều chỉnh workload.

## 37. wal_compression: giảm FPI bytes, đổi lấy CPU

Nếu pg_stat_wal cho thấy wal_fpi cao và WAL bytes tăng sau mỗi checkpoint, thử nghiệm `wal_compression` trong môi trường đại diện có thể giúp giảm bytes.

### Đo trước/sau

- WAL bytes per minute.
- FPI count.
- CPU utilization.
- WAL write/flush latency.
- Checkpoint write/sync time.
- Replica apply throughput.

### Kết quả không thể suy ra chỉ từ setting

Nén có thể tiết kiệm I/O nhưng tăng CPU. Nếu server đã CPU-bound, throughput tổng thể có thể xấu đi. Nếu workload chạm nhiều pages với FPI lớn, lợi ích có thể rõ hơn.

Không thay đổi nhiều settings cùng lúc; nếu đổi wal_compression, giữ workload/sample window tương đương để so sánh.

## 38. checkpoint_flush_after

Setting:

```sql
SHOW checkpoint_flush_after;
```

Trên các platform hỗ trợ, setting này điều khiển ngưỡng ghi bytes trước khi yêu cầu OS flush/writeback data files trong quá trình checkpoint. Mục đích là tránh dồn quá nhiều dirty data vào cuối checkpoint hoặc để writeback diễn ra có kiểm soát.

Hiệu quả phụ thuộc OS, filesystem, block device và storage cache. Không tăng/giảm theo một công thức chung; kiểm tra tài liệu đúng version/platform và benchmark.

## 39. Checkpoint write time và sync time

Trên PG16 trở xuống, lấy cumulative counters từ pg_stat_bgwriter; trên PG17+, lấy write_time/sync_time từ pg_stat_checkpointer.

Để hiểu xu hướng, tính delta:

\[
\text{average checkpoint write ms}
= \frac{\Delta \text{checkpoint\_write\_time}}
{\Delta \text{checkpoints}}
\]

\[
\text{average checkpoint sync ms}
= \frac{\Delta \text{checkpoint\_sync\_time}}
{\Delta \text{checkpoints}}
\]

Đây là average trên khoảng sample; không cho biết tail latency của từng checkpoint.

### Diễn giải

- Write time tăng cùng buffers_checkpoint: nhiều pages được ghi hoặc storage throughput thấp.
- Sync time tăng mạnh: fsync latency/storage flush behavior cần điều tra.
- Checkpoint duration dài nhưng frequency thấp: có thể I/O bị trải đều, cần xem completion target và throughput.
- Checkpoint count tăng nhanh cùng requested count: xem WAL rate và max_wal_size.

## 40. pg_stat_io và I/O theo process

PostgreSQL 16+ có view `pg_stat_io` để xem một số thống kê I/O theo backend type/object/context:

```sql
SELECT
    backend_type,
    object,
    context,
    sum(reads) AS reads,
    sum(writes) AS writes,
    sum(writebacks) AS writebacks,
    sum(fsyncs) AS fsyncs
FROM pg_catalog.pg_stat_io
GROUP BY backend_type, object, context
ORDER BY sum(writes) DESC;
```

### Cách dùng

- Tìm process types có write activity cao.
- So sánh checkpointer, background writer, client backends và autovacuum workers nếu view/version cung cấp các rows tương ứng.
- Xem reads/writes/fsyncs cùng thời gian I/O nếu cần.
- Dùng delta theo sample window, vì counters cumulative.

### Giới hạn

pg_stat_io không thay thế OS/provider metrics. Nó không nhất thiết thể hiện toàn bộ device queue, controller cache, cloud-volume throttling hay latency theo từng block request. Xem schema của version vì columns/backend contexts có thể thay đổi.

## 41. I/O saturation ở storage layer

Checkpoint có thể chỉ là tác nhân làm lộ giới hạn storage. Đo ở tầng OS/provider:

- Read/write IOPS.
- Read/write throughput MB/s.
- Average và p95/p99 latency.
- Queue depth / outstanding requests.
- Burst credits/throttling của cloud volumes.
- fsync latency.
- Disk free space và volume expansion.

### Ví dụ

Một volume giới hạn 500 MB/s. Checkpoint writes dùng 350 MB/s, WAL writes dùng 100 MB/s, foreground queries cần thêm 200 MB/s. Tổng nhu cầu vượt giới hạn, queue tăng và p99 query latency tăng.

### Không chỉ tăng max_wal_size

Tăng max_wal_size có thể giảm số checkpoint requests, nhưng không tạo thêm IOPS/throughput cho storage. Nếu storage bão hòa liên tục, cần giảm write amplification, tăng storage capacity hoặc điều tiết workload.

## 42. Checkpoint và crash recovery time

Checkpoint mới hơn thường làm giảm lượng WAL cần replay trong crash recovery thông thường. Tuy nhiên checkpoint quá thường xuyên tạo write overhead và có thể tăng FPI generation.

Checkpoint thưa hơn có thể giảm write overhead nhưng làm recovery cần replay nhiều WAL hơn sau crash. WAL replay time còn phụ thuộc tốc độ storage/CPU, lượng records và recovery workload.

### Trade-off

| Điều chỉnh | Lợi ích có thể có | Chi phí/rủi ro |
|---|---|---|
| Tăng max_wal_size | Ít requested checkpoints hơn | WAL/disk headroom lớn hơn, recovery có thể replay nhiều hơn |
| Tăng checkpoint_timeout | Ít timed checkpoints hơn | Khoảng recovery từ checkpoint có thể dài hơn |
| Tăng completion_target | Ghi checkpoint trải đều hơn | Writes kéo dài trong khoảng checkpoint, storage vẫn phải đủ nhanh |
| Bật wal_compression | Giảm FPI bytes | Tăng CPU |
| Giảm write workload | Giảm WAL và data writes | Có thể ảnh hưởng throughput/business latency |

Không tối ưu checkpoint mà bỏ qua **RTO (Recovery Time Objective)** và dung lượng WAL có thể giữ.

## 43. Checkpoint trên standby: restartpoints

Standby đang replay WAL có cơ chế **restartpoint**. Restartpoint tương tự checkpoint ở primary về mục tiêu tạo recovery point trong quá trình recovery, nhưng phụ thuộc các checkpoint records được replay từ primary.

Trên PG17+, pg_stat_checkpointer có các counters restartpoints trong những versions hỗ trợ. Trên các version cũ hơn, checkpoint/restartpoint stats có cách hiển thị khác.

### Vì sao standby vẫn cần I/O?

- Replay WAL làm thay đổi data pages.
- Restartpoint cần ghi dirty buffers.
- Read queries trên standby cạnh tranh I/O với replay/restartpoint.
- Replica lag có thể tăng nếu storage không theo kịp WAL replay.

Không chỉ tối ưu primary; kiểm tra disk/CPU và read workload trên standby nếu replay lag tăng.

## 44. Checkpoint và base backup/PITR

WAL archiving kết hợp base backup cho phép point-in-time recovery (PITR). Checkpoint và WAL retention liên quan đến:

- Base backup cần một chuỗi WAL nhất quán.
- Archive phải giữ WAL liên tục từ backup tới recovery target.
- Replication slots có thể giữ WAL cho logical/physical consumers.
- Xóa archive files quá sớm có thể làm mất khả năng PITR.

### Nguyên tắc

Không xem checkpoint là tín hiệu để tự xóa WAL archive. Retention archive phải theo backup catalog, recovery window, timeline và chính sách bảo vệ dữ liệu.

## 45. Checkpoint dày ảnh hưởng backup như thế nào?

Checkpoint tạo thêm data page writes; base backup cũng đọc data files; archive/backup jobs lại đọc hoặc copy WAL. Nếu cùng lúc chạy checkpoint dày, full backup, index build và mass update, storage có thể chịu nhiều luồng I/O cạnh tranh.

### Lập lịch

- Tránh chồng nhiều maintenance jobs không cần thiết.
- Theo dõi backup throughput và checkpoint logs.
- Đảm bảo archive throughput cao hơn WAL generation trung bình và có headroom cho peaks.
- Kiểm tra replica lag khi backup/maintenance chạy.

Backup không nên bị bỏ qua chỉ để làm checkpoint metrics đẹp hơn; hãy cân bằng theo recovery objectives.

## 46. Những thao tác thường làm WAL tăng nhanh

Các nguồn phổ biến:

- UPDATE/DELETE hàng loạt.
- INSERT tốc độ cao vào bảng có nhiều indexes.
- UPSERT làm nhiều heap/index updates.
- Index creation/rebuild.
- Bulk load và ETL.
- FPI tăng sau checkpoint khi workload chạm nhiều pages.
- Logical decoding/replication configuration cần thêm WAL information.
- Các thay đổi metadata/page initialization.

### Không phải mọi SQL có cùng WAL cost

Một UPDATE sửa một cột không được index có thể tạo chi phí khác với UPDATE sửa indexed columns và tạo index entries mới. Một bảng có nhiều secondary indexes thường tạo thêm WAL so với heap-only changes.

Để tìm nguồn, phân tích workload theo application_name, query patterns, table/index activity và WAL bytes trong cùng time window.

## 47. Indexes và WAL amplification

Mỗi INSERT/UPDATE có thể phải duy trì các indexes liên quan. Một bảng có primary key, unique indexes và nhiều secondary indexes sẽ tạo thêm page changes/WAL records.

### Ví dụ

```text
INSERT một row vào bảng có:
  heap page
  primary key index
  unique business key index
  5 secondary indexes

Một row logic có thể tạo nhiều page changes
và WAL records ở heap lẫn các indexes.
```

### Cách điều tra

- Xem số indexes và kích thước.
- Kiểm tra indexes có được query workload dùng không.
- Dùng EXPLAIN để hiểu access paths.
- Đo WAL rate trước/sau trên clone hoặc staging.

Không drop indexes production chỉ để giảm WAL. Index có thể bảo vệ uniqueness, foreign key lookup hoặc query SLA; mọi thay đổi phải xét correctness và dependencies.

## 48. UPDATE pattern và HOT

HOT updates có thể giảm index maintenance khi không đổi indexed columns và có đủ free space trên page. Nếu workload liên tục update các cột được index, HOT rate thường thấp hơn và WAL/index churn có thể tăng.

Kiểm tra:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    CASE
        WHEN n_tup_upd > 0
        THEN round(
            100.0 * n_tup_hot_upd / n_tup_upd,
            2
        )
        ELSE 0
    END AS hot_update_pct
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_tup_upd DESC
LIMIT 20;
```

### Tối ưu có điều kiện

- Tránh indexes không có giá trị.
- Xem lại fillfactor trên bảng update-heavy.
- Hạn chế update cùng một row nhiều lần trong một batch nếu có thể gộp logic.
- Chỉ thay đổi schema sau khi đo query/index dependencies.

HOT giảm index churn trong các trường hợp phù hợp; nó không loại bỏ WAL và dead tuple generation.

## 49. Bulk load và WAL

COPY vào bảng logged vẫn tạo WAL để bảo vệ durability/replication. Một số bulk-load patterns có thể có WAL behavior khác khi target là bảng mới, chưa được logged/replicated và cluster chạy cấu hình phù hợp.

### Những điều cần cân nhắc

- COPY vào bảng logged hiện hữu: WAL và index/constraint work vẫn diễn ra.
- Nạp vào UNLOGGED staging: có thể giảm WAL cho staging nhưng dữ liệu không crash-safe và không replicate như logged data.
- Tạo indexes sau load trên bảng mới: có thể giảm per-row index maintenance, nhưng cần thiết kế offline/cutover và đảm bảo constraints.
- wal_level=minimal: chỉ phù hợp với những điều kiện cluster/recovery/replication rất cụ thể, không phải thay đổi tùy tiện trên primary có standby/logical replication.

### Không đánh đồng tốc độ COPY với WAL-free

COPY là giao thức nạp hiệu quả, nhưng không mặc định bỏ WAL. Hãy xem requirements về crash recovery, PITR, streaming replication và logical decoding trước khi chọn đường nạp.

## 50. CHECKPOINT thủ công và pg_switch_wal()

Hai lệnh thường bị nhầm:

```sql
CHECKPOINT;

SELECT pg_switch_wal();
```

**CHECKPOINT** yêu cầu PostgreSQL thực hiện checkpoint. Nó có thể tạo một đợt data page I/O lớn và không phải cách giảm WAL generation.

**pg_switch_wal()** yêu cầu chuyển sang WAL segment tiếp theo. Nó hữu ích trong một số quy trình archive/backup/testing, nhưng không tương đương checkpoint.

### Không dùng như nút “dọn WAL”

Checkpoint không xóa WAL còn cần bởi archive/slots/standby. pg_switch_wal() chỉ đổi segment, có thể khiến archive có thêm segment để xử lý; gọi liên tục có thể tạo nhiều segment nhỏ/đẩy thêm công việc archive.

Chỉ dùng các lệnh này khi có mục đích vận hành rõ ràng.

## 51. Vì sao max_wal_size có thể bị vượt?

max_wal_size là soft limit, không phải quota filesystem. PostgreSQL có thể vượt trong các tình huống:

- WAL generation tăng nhanh giữa hai checkpoints.
- Checkpoint đang chạy và cần thời gian để hoàn tất.
- WAL segments còn được giữ bởi archive/replication slots/wal_keep_size.
- Workload spike lớn hơn mức baseline.
- WAL retention cần thiết cho backup/recovery.

### Phân biệt hai câu hỏi

1. Vì sao PostgreSQL yêu cầu checkpoint sớm? Xem WAL rate và checkpoint stats.
2. Vì sao pg_wal vẫn lớn sau checkpoint? Xem archive, slots, standby và retention.

Đừng tăng max_wal_size để chữa archive backlog; setting này không làm consumer archive nhanh hơn.

## 52. max_wal_size và disk capacity planning

Khi cân nhắc tăng max_wal_size:

1. Đo WAL generation rate trung bình và peak.
2. Đo checkpoint duration và requested checkpoint frequency.
3. Tính dung lượng cần giữ trong khoảng checkpoint/backup/replication.
4. Kiểm tra pg_wal volume free space và growth rate.
5. Xem archive/slot retention độc lập.
6. Xác định recovery time objective.
7. Tăng theo bước có kiểm soát rồi quan sát.

### Ví dụ lập kế hoạch

Nếu workload tạo 30 MB/s WAL và bạn muốn có khoảng 10 phút trước khi WAL-size pressure yêu cầu checkpoint, lượng WAL tương ứng khoảng:

\[
30 \text{ MB/s} \times 600 \text{ s}
= 18,000 \text{ MB}
\]

Đây chỉ là ước lượng đầu tiên, không phải công thức cấu hình max_wal_size chính xác. PostgreSQL còn có checkpoint timing, WAL segment accounting, peaks, retention và disk headroom.

### Đừng cấp toàn bộ disk cho max_wal_size

Volume còn cần chỗ cho data growth, temp files, archive staging, logs, replication backlog và emergency headroom. Dùng alert trước khi free space xuống thấp.

## 53. Checkpoint timeout và recovery objective

Khi tăng checkpoint_timeout, bạn có thể giảm timed checkpoint frequency nhưng cần cân nhắc:

- Crash recovery phải replay WAL xa hơn từ checkpoint.
- Dirty buffers có thể tích tụ nhiều hơn.
- Một checkpoint có thể cần ghi nhiều pages hơn.
- Nếu WAL rate cao, max_wal_size vẫn có thể yêu cầu checkpoint trước.

Đặt checkpoint_timeout theo cả workload và recovery time objective. Đo recovery trên bản sao/staging nếu RTO quan trọng; không suy ra recovery duration chỉ từ số phút checkpoint.

## 54. Tuning checkpoint_completion_target

Quy trình:

1. Đọc setting hiện tại.
2. Bật/đọc checkpoint logs.
3. Lấy checkpoint write/sync times và storage latency.
4. Xác định writes có bị dồn thành burst không.
5. Điều chỉnh completion target nếu checkpoint scheduling phù hợp là bottleneck.
6. Đo lại p95/p99 latency, write throughput và checkpoint duration.

Nếu storage đã bị bão hòa liên tục, trải checkpoint lâu hơn có thể chỉ làm I/O cạnh tranh kéo dài. Completion target làm mượt timing; nó không tăng năng lực thiết bị.

## 55. Tuning WAL generation trước khi tăng checkpoint

Nếu wal_bytes/s cao bất thường:

- Xác định application/query tạo nhiều writes.
- Kiểm tra UPDATE/UPSERT patterns.
- Xem indexes và HOT update rate.
- Đo FPI count sau checkpoint.
- Xem bulk load/index build jobs.
- Kiểm tra wal_level và replication/CDC requirements.
- Xem wal_compression có giúp giảm FPI bytes không.

### Ví dụ

Một job cập nhật cùng một row 20 lần trong một transaction có thể được viết lại để chỉ cập nhật final state một lần, nếu business semantics cho phép. Điều này có thể giảm heap/index churn và WAL.

Không gộp updates nếu từng thay đổi cần audit/event history hoặc có trigger/business side effects riêng.

## 56. Điều tiết write workload

Khi storage gần giới hạn:

- Chia bulk updates thành batches.
- Giới hạn concurrency của ETL/import jobs.
- Tránh đồng thời chạy nhiều index builds/maintenance tasks.
- Schedule backup/archive copies hợp lý.
- Áp dụng backpressure cho writers nếu cần.
- Theo dõi queue depth và query latency.

Điều tiết workload có thể giảm peak I/O nhưng làm job hoàn thành lâu hơn. Chọn mức concurrency theo throughput tổng và SLA của OLTP.

## 57. Checkpoint và replication synchronous

Synchronous replication ảnh hưởng commit acknowledgment và network/standby flush waits. Checkpoint vẫn là hoạt động ghi data pages trên primary; nó không đồng nghĩa standby đã replay xong.

### Phân biệt latency

- WAL flush latency trên primary.
- Synchronous standby acknowledgment latency.
- Checkpoint write/sync duration.
- Standby replay lag.

Một ứng dụng có commit latency cao có thể đang chờ synchronous standby, dù checkpoint stats bình thường. Ngược lại, checkpoint I/O có thể làm storage primary chậm dù synchronous replication không bật.

## 58. Thử nghiệm WAL/checkpoint có kiểm soát

Trong lab hoặc staging, tạo bảng:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_wal;

CREATE TABLE lesson_wal.write_demo (
    id BIGINT PRIMARY KEY,
    group_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO lesson_wal.write_demo (
    id, group_id, payload
)
SELECT
    g,
    g % 100,
    repeat('x', 500)
FROM generate_series(1, 500000) AS g;
```

Ghi lại metrics baseline từ pg_stat_wal, checkpoint view, disk I/O và query latency.

Sau đó:

```sql
UPDATE lesson_wal.write_demo
SET payload = payload || '-changed',
    updated_at = clock_timestamp()
WHERE id % 2 = 0;
```

Quan sát:

- WAL bytes delta.
- wal_fpi delta.
- checkpoint count delta.
- checkpoint write/sync time delta.
- pg_wal directory size.
- storage write throughput/latency.

Đây là lab tạo churn có chủ đích; chạy trên dữ liệu test, không chạy mass UPDATE này trên bảng production chỉ để thử.

## 59. So sánh checkpoint dày và checkpoint thưa

Để benchmark có ý nghĩa:

1. Dùng cùng data volume và cùng query/write mix.
2. Giữ concurrency, cache state và storage class tương đương.
3. Đo cùng thời lượng đủ dài để có nhiều checkpoint cycles.
4. Ghi nhận checkpoint count/timed/requested.
5. Đo WAL bytes, FPI, disk I/O và latency.
6. Đo crash recovery trên disposable clone nếu cần so RTO.

### Không chỉ so throughput

Một cấu hình có TPS cao hơn nhưng recovery lâu hơn hoặc WAL retention vượt disk headroom có thể không phù hợp production. So cả durability, availability và recovery objectives.

## 60. Không thay đổi nhiều settings cùng lúc

Một đợt tuning có thể thay đổi:

- max_wal_size.
- checkpoint_timeout.
- checkpoint_completion_target.
- wal_compression.
- wal_buffers.
- autovacuum cost/worker settings.
- storage throughput/IOPS.

Nếu đổi tất cả cùng lúc, bạn không biết thay đổi nào tạo kết quả. Tạo baseline, đổi một nhóm liên quan, quan sát đủ lâu rồi mới tiếp tục.

## 61. Xác định PostgreSQL major version

Trước khi tạo dashboard hoặc chạy truy vấn stats:

```sql
SHOW server_version;
SHOW server_version_num;
```

Một số ví dụ:

- PG16: checkpoint counters nằm trong pg_stat_bgwriter.
- PG17+: checkpoint counters nằm trong pg_stat_checkpointer; pg_stat_bgwriter có schema mới.
- pg_stat_io có từ PG16.
- Một số slot/replication columns được bổ sung ở các major versions khác nhau.

Đừng copy query từ một dashboard PG16 sang PG17 mà không kiểm tra columns.

## 62. Xem query nào tạo WAL nhiều

Nếu đã cài và bật pg_stat_statements với version có WAL counters:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    wal_records,
    wal_fpi,
    wal_bytes,
    left(query, 160) AS query_preview
FROM pg_catalog.pg_stat_statements
ORDER BY wal_bytes DESC
LIMIT 20;
```

### Cách diễn giải

- wal_bytes cao tổng cộng có thể do query chạy rất nhiều lần.
- WAL bytes per call giúp phát hiện query có chi phí lớn mỗi lần.
- wal_fpi cao có thể cho thấy query chạm nhiều pages tạo FPI.
- Query text có thể bị normalize/ẩn literals tùy cấu hình.

### Giới hạn

pg_stat_statements không thay WAL-level cluster metrics; counters có thể reset và chỉ bao phủ query statements được extension theo dõi. Một số background/internal activities không được gán vào query theo cách bạn kỳ vọng.

## 63. WAL bytes per call

Ví dụ:

```sql
SELECT
    queryid,
    calls,
    pg_size_pretty(wal_bytes) AS total_wal,
    pg_size_pretty(
        (wal_bytes / GREATEST(calls, 1))::bigint
    ) AS wal_per_call,
    left(query, 120) AS query_preview
FROM pg_catalog.pg_stat_statements
WHERE calls > 0
ORDER BY wal_bytes / GREATEST(calls, 1) DESC
LIMIT 20;
```

Đây là cách xếp hạng tương đối, không có nghĩa query có wal_per_call cao nhất là query cần tối ưu trước. Cân nhắc tổng bytes, call frequency, business importance và latency.

## 64. Snapshot metrics theo thời gian

Một dashboard cần lưu samples:

```text
timestamp
server_id / instance_id
pg_stat_wal.wal_bytes
pg_stat_wal.wal_fpi
checkpoint counters
checkpoint write/sync time
pg_wal directory bytes
archive failures
replication slot retained distance
replica replay lag
storage IOPS/throughput/latency
```

Từ samples, tính:

- WAL MB/s.
- FPI/s.
- Checkpoints/minute.
- Requested checkpoints/minute.
- Average checkpoint write/sync time per checkpoint.
- pg_wal bytes growth/minute.
- Replica replay lag trend.

### Đừng chỉ ghi số liệu hiện tại

Checkpoint/WAL là hiện tượng theo thời gian. Một ảnh chụp đơn lẻ không cho biết rate, spike, duration hay liệu backlog đang tăng/giảm.

## 65. pg_stat_activity và wait events

Khi query latency tăng trong checkpoint:

```sql
SELECT
    pid,
    backend_type,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 160) AS query_preview
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Wait events có thể giúp phân biệt:

- WALWrite/WALSync: process chờ WAL write/flush.
- DataFileRead/DataFileWrite hoặc các wait events I/O tương ứng version: data file I/O.
- Lock: chờ lock, không nhất thiết là checkpoint I/O.
- Client waits: backend đang chờ client/network.

Tên wait events thay đổi theo version. Dùng pg_wait_events catalog khi cần tra cứu.

## 66. Checkpoint và WAL wait events

Các wait events liên quan WAL có thể xuất hiện khi backend phải chờ WAL buffers được ghi hoặc WAL được sync. Nếu nhiều client backends cùng chờ WALWrite/WALSync:

- Kiểm tra WAL storage latency.
- Kiểm tra WAL writer và wal_buffers_full.
- Xem commit rate và synchronous replication.
- Xem synchronous_commit policy.
- Kiểm tra storage saturation.

Không mặc định checkpoint là nguyên nhân duy nhất. WAL flush latency có thể tăng vì WAL device chậm hoặc standby acknowledgment, trong khi checkpoint write time bình thường.

## 67. Kiểm tra I/O qua pg_stat_io

Một query chi tiết hơn (PG16+; xác nhận columns trên version):

```sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    writebacks,
    writeback_time,
    fsyncs,
    fsync_time,
    stats_reset
FROM pg_catalog.pg_stat_io
ORDER BY backend_type, object, context;
```

read_time, write_time, fsync_time phụ thuộc track_io_timing/configuration và có thể bằng 0 nếu timing chưa được thu thập. Bật timing có overhead; đánh giá trước trên workload thật.

## 68. I/O timings và track_io_timing

```sql
SHOW track_io_timing;
```

Khi bật track_io_timing, PostgreSQL thu thập thời gian I/O trong một số stats views/EXPLAIN. Điều này giúp phân biệt số operations với thời gian chờ, nhưng có thể có overhead tùy platform.

### Sử dụng

- Bật có chủ đích trong môi trường phù hợp.
- So sánh trước/sau trong cùng workload.
- Dùng EXPLAIN (ANALYZE, BUFFERS) cho query đại diện.
- Đối chiếu với OS/provider latency.

Không coi tổng read_time/write_time trong stats là latency của một request riêng lẻ.

## 69. Checkpoint logs và metrics phải khớp nhau

Nếu dashboard cho thấy requested checkpoints tăng:

1. Xem log_checkpoints để xác nhận loại checkpoint và thời điểm.
2. So wal_bytes delta trong khoảng đó.
3. Kiểm tra max_wal_size/checkpoint_timeout.
4. Xem checkpoint write/sync time.
5. So storage latency và query p99.
6. Xem archive/slot retention riêng.

Nếu requested count tăng nhưng WAL rate không cao, kiểm tra manual CHECKPOINT, backup/maintenance jobs hoặc stats reset/version interpretation.

## 70. Một bảng dashboard đề xuất

| Nhóm | Metrics | Câu hỏi trả lời |
|---|---|---|
| WAL generation | wal_bytes/s, wal_records/s, wal_fpi/s | WAL đang được tạo nhanh tới đâu? |
| WAL buffers | wal_buffers_full delta | Có áp lực ở WAL buffers không? |
| Checkpoint | timed/requested per minute | Checkpoint dày vì time hay WAL? |
| Checkpoint I/O | write_time, sync_time, buffers_written | Checkpointer mất bao lâu và ghi bao nhiêu? |
| Background writer | buffers_clean, maxwritten_clean, buffers_alloc | Bgwriter có chuẩn bị buffers kịp không? |
| Backend writes | buffers_backend (version cũ) | Backends có phải tự ghi nhiều không? |
| WAL retention | pg_wal bytes, slot distance, archive failures | Vì sao WAL chưa recycle? |
| Replication | send/write/flush/replay LSN, lag | Standby/consumer có bắt kịp không? |
| Storage | IOPS, MB/s, latency, queue depth | Thiết bị có bị bão hòa không? |
| Application | commit latency, p95/p99, throughput | Người dùng chịu tác động gì? |

Một dashboard tốt cho phép đặt các metrics trên cùng timeline và drill down theo server/role/application.

## 71. Runbook: checkpoint xảy ra quá thường xuyên

Khi checkpoint count tăng nhanh:

1. Lấy delta timed/requested checkpoints theo phút.
2. Đọc checkpoint logs để xác định trigger reason.
3. Đo WAL bytes/s và FPI/s.
4. Kiểm tra max_wal_size và checkpoint_timeout.
5. Kiểm tra checkpoint write/sync duration.
6. Đối chiếu storage latency/queue depth và application p95/p99.
7. Tìm bulk jobs/index builds hoặc mass updates trùng thời điểm.
8. Xác nhận checkpoint thủ công có đang được scheduler/job gọi không.
9. Thay đổi một setting có căn cứ, ví dụ max_wal_size hoặc completion_target.
10. Đo lại trong workload tương đương và kiểm tra RTO/disk headroom.

### Dấu hiệu thường gặp

- Requested checkpoints tăng: nghi WAL threshold bị chạm sớm hoặc có yêu cầu thủ công.
- Timed checkpoints ổn định nhưng I/O burst cao: xem completion_target, storage và các writers khác.
- WAL rate tăng mạnh cùng wal_fpi: kiểm tra checkpoint frequency và pages bị chạm.

## 72. Runbook: WAL directory tăng liên tục

Khi pg_wal size tăng:

1. Xem WAL generation rate từ pg_stat_wal.
2. Kiểm tra pg_stat_archiver: failed_count và last_archived_time.
3. Kiểm tra archive destination capacity/network/credentials.
4. Kiểm tra replication slots: active, restart_lsn và retained distance.
5. Kiểm tra wal_keep_size và max_slot_wal_keep_size.
6. Xem primary/standby replay lag.
7. Đối chiếu WAL generation với archive/replication consumption.
8. Kiểm tra volume free space và time-to-full.
9. Khắc phục consumer/archive theo owner và recovery policy.
10. Theo dõi pg_wal giảm/recycle sau khi retention blockers được giải quyết.

### Không xóa file trực tiếp

Không xóa segment trong pg_wal bằng shell. Nếu cần giải phóng disk khẩn cấp, xử lý nguyên nhân retention qua PostgreSQL/archive/replication policy hoặc mở rộng volume theo runbook.

## 73. Runbook: archive failures

1. Đọc pg_stat_archiver và server logs.
2. Xác định file WAL thất bại gần nhất.
3. Kiểm tra archive_command exit code.
4. Kiểm tra network, credentials, permissions và destination.
5. Kiểm tra destination còn đủ dung lượng.
6. Khôi phục archive service.
7. Xác nhận failed_count không tiếp tục tăng và last_archived_time tiến triển.
8. Đảm bảo WAL backlog được xử lý hết.
9. Kiểm tra backup/PITR continuity.
10. Ghi nhận thời gian gián đoạn và recovery impact.

### Không bỏ qua file lỗi

Archive cần chuỗi WAL liên tục theo timeline. Một segment bị thiếu có thể làm backup/PITR chain không sử dụng được cho recovery target cần nó.

## 74. Runbook: replication slot giữ WAL quá lâu

1. Xác định slot owner và loại slot.
2. Kiểm tra active/inactive và consumer health.
3. Đo restart_lsn distance với current WAL LSN.
4. Kiểm tra consumer logs, network và apply throughput.
5. Xác định slot có giữ xmin/catalog_xmin hay không.
6. Đánh giá disk headroom và max_slot_wal_keep_size.
7. Khôi phục consumer hoặc lập kế hoạch resnapshot nếu cần.
8. Chỉ drop/recreate slot sau khi xác nhận owner và downstream recovery.
9. Theo dõi WAL recycling sau khi slot tiến triển.
10. Đặt alert khi inactive duration/retained bytes vượt policy.

Không drop slot chỉ vì active=false; logical consumer có thể cần slot để không mất changes.

## 75. Runbook: checkpoint I/O làm query latency tăng

1. Đặt checkpoint logs, checkpoint stats và query latency trên cùng timeline.
2. Kiểm tra write_time/sync_time và buffers_written.
3. Xem storage IOPS/throughput/latency/queue.
4. Kiểm tra background writer và backend writes.
5. Xem có bulk load, index build, autovacuum hoặc backup đồng thời không.
6. Đo WAL rate/FPI để biết write amplification.
7. Xem checkpoint_completion_target có đang làm burst quá tập trung không.
8. Cân nhắc điều tiết batch/concurrency hoặc tăng storage capacity.
9. Thay đổi max_wal_size/checkpoint settings có kiểm soát nếu metrics chứng minh cần.
10. Đo lại p95/p99 và recovery time.

Không mặc định tăng max_wal_size sẽ giải quyết storage saturation; nó chủ yếu thay đổi checkpoint frequency.

## 76. Runbook: WAL rate tăng bất thường sau deploy

1. So wal_bytes/s trước và sau deploy.
2. Xác định query/application_name có WAL contribution tăng.
3. So pg_stat_statements WAL counters nếu có.
4. Kiểm tra UPDATE/UPSERT behavior và số rows bị tác động.
5. Kiểm tra indexes mới hoặc migration vừa chạy.
6. Xem wal_fpi tăng có trùng checkpoint frequency không.
7. Kiểm tra trigger/audit/outbox writes.
8. So workload input volume và concurrency.
9. Rollback/điều chỉnh code nếu có regression đã xác định và policy cho phép.
10. Reconcile dữ liệu/replication/backup sau thay đổi.

### Lưu ý

Một deploy thêm index có thể làm writes tạo thêm index maintenance WAL. Một trigger ghi audit có thể nhân số rows ghi. Đo tác động trên clone/staging trước khi kết luận.

## 77. Recovery khi volume pg_wal gần đầy

Đây là tình huống vận hành khẩn cấp:

1. Xác nhận volume nào đầy và tốc độ tăng.
2. Không xóa WAL files thủ công.
3. Kiểm tra archive failures và replication slot retention.
4. Kiểm tra standby/consumer nào đang giữ WAL.
5. Khắc phục archive/consumer nếu có thể.
6. Mở rộng volume theo quy trình storage/platform nếu cần.
7. Điều tiết workload ghi không thiết yếu để giảm tốc độ phát sinh WAL.
8. Kiểm tra database còn ghi được WAL và health.
9. Theo dõi archive/replication bắt kịp, WAL recycle.
10. Sau sự cố, kiểm tra backup/PITR và slot continuity.

Không restart hoặc chạy CHECKPOINT liên tục với hy vọng tự giải phóng WAL. Nếu segment còn cần bởi archive/slot, checkpoint không thể xóa nó.

## 78. Checklist trước khi tăng max_wal_size

- Đã đo WAL generation rate trung bình/peak chưa?
- Requested checkpoints có thực sự tăng không?
- Timed checkpoints có đang chiếm đa số?
- Checkpoint write/sync time và storage latency thế nào?
- pg_wal có đủ headroom cho mức tăng mới không?
- Archive và replication slots có đang giữ WAL không?
- RTO có chấp nhận checkpoint thưa hơn không?
- Backup/PITR/standby policy đã được xét chưa?
- Thay đổi có được thử trong workload tương đương chưa?
- Có dashboard/rollback plan sau thay đổi không?

Nếu vấn đề thực tế là archive backlog hoặc slot inactive, xử lý retention blocker trước khi tăng checkpoint size.

## 79. Checklist vận hành checkpoint/WAL

### WAL generation

- wal_bytes/s và wal_fpi/s.
- Query/application tạo nhiều WAL.
- Index/trigger/update patterns.
- WAL buffers pressure.

### Checkpoint

- Timed/requested counts per minute.
- Checkpoint write/sync time.
- Checkpoint buffers written.
- Checkpoint logs và completion target.

### Retention

- pg_wal directory size.
- Archive failures/backlog.
- Replication slot restart_lsn distance.
- wal_keep_size/max_slot_wal_keep_size.
- Replica replay lag.

### Storage/application

- IOPS/throughput/latency/queue depth.
- Free disk/time-to-full.
- Commit latency và p95/p99.
- Concurrent ETL/index build/backup/autovacuum.

### Recovery

- RTO/RPO.
- Base backup và archive continuity.
- Standby catch-up capacity.
- Emergency runbook đã thử chưa?

## 80. Các nguyên tắc dễ hiểu nhầm

**“COMMIT đồng nghĩa data page đã được ghi xuống data file.”** Không. WAL flush có thể đủ để xác nhận commit; data pages được ghi sau.

**“WAL flush là checkpoint.”** Không. Flush bảo đảm WAL bytes bền vững theo policy; checkpoint ghi data pages và tạo recovery point.

**“max_wal_size là hard limit.”** Không. Đây là soft limit, có thể bị vượt.

**“pg_wal lớn nghĩa là WAL generation quá cao.”** Không nhất thiết. Archive/replication retention có thể là nguyên nhân.

**“Checkpoint càng nhiều càng an toàn.”** Không. Checkpoint dày tăng I/O/FPI; cần cân bằng recovery time.

**“Checkpoint thưa luôn tốt.”** Không. Recovery có thể phải replay nhiều WAL hơn và dirty pages có thể tích tụ.

**“Tăng checkpoint_timeout luôn giảm checkpoint.”** Không nếu max_wal_size bị chạm trước.

**“Tăng max_wal_size làm storage nhanh hơn.”** Không. Nó chỉ có thể giảm requested checkpoint frequency.

**“checkpoint_completion_target giới hạn mọi I/O.”** Không. Nó điều phối checkpoint writes, không kiểm soát toàn bộ workload.

**“Background writer và checkpointer là một process.”** Không. Chúng có mục tiêu khác nhau.

**“wal_buffers lớn luôn tốt.”** Không. Cần xem wal_buffers_full, WAL flush latency và storage.

**“Tắt full_page_writes là cách giảm FPI an toàn.”** Không. Nó làm tăng rủi ro torn-page corruption sau crash.

**“synchronous_commit=off làm WAL ít đi.”** Không. Nó thay đổi commit flush acknowledgment semantics, không loại bỏ WAL records.

**“pg_switch_wal() tạo checkpoint.”** Không. Nó chuyển segment.

**“CHECKPOINT xóa hết WAL cũ.”** Không. Archive, slots và standby có thể còn cần WAL.

**“wal_compression luôn tăng tốc.”** Không. Nó đổi CPU lấy giảm FPI bytes.

**“Tăng max_wal_size giải quyết archive failures.”** Không. Phải khắc phục archive consumer/destination.

**“Drop replication slot inactive là vô hại.”** Không. Consumer có thể cần resnapshot và mất continuity.

**“Checkpoint write_time cao luôn có nghĩa storage chậm.”** Không. Nó cũng có thể cao vì checkpointer ghi nhiều buffers.

**“Checkpoint sync_time thấp nghĩa toàn bộ I/O nhanh.”** Không. Foreground query/WAL I/O vẫn có thể bị nghẽn.

**“Một snapshot stats là đủ để tìm rate.”** Không. Cần delta samples với timestamp và stats_reset.

## 81. Bài tập thực hành

### Bài 1 — WAL là gì?

Giải thích Write-Ahead Log và vì sao PostgreSQL phải ghi WAL trước khi data pages được ghi bền vững.

### Bài 2 — WAL flush và checkpoint

Một transaction đã COMMIT và client nhận ACK, nhưng heap page chưa được ghi xuống data file. Vì sao database vẫn có thể phục hồi sau crash?

### Bài 3 — Phân biệt WAL stages

Phân biệt WAL generation, write, flush, archive, replay và retention. Cho một ví dụ trong đó archive backlog làm pg_wal tăng dù WAL generation không đổi.

### Bài 4 — WAL segment

Giải thích segment file trong pg_wal, segment recycling và vì sao số WAL files không chỉ phụ thuộc wal_bytes/s.

### Bài 5 — Checkpoint

Mô tả dirty buffers, checkpointer, checkpoint record và redo point. Checkpoint giúp crash recovery thế nào?

### Bài 6 — Timed và requested

Phân biệt timed checkpoint và requested checkpoint. Những tình huống nào có thể tạo requested checkpoint ngoài việc chạm max_wal_size?

### Bài 7 — max_wal_size

Vì sao max_wal_size là soft limit? Nêu ít nhất ba lý do pg_wal có thể vượt giá trị cấu hình.

### Bài 8 — checkpoint_timeout

Giải thích trade-off khi tăng checkpoint_timeout. Vì sao requested checkpoints vẫn có thể xảy ra trước timed checkpoint?

### Bài 9 — checkpoint_completion_target

So sánh target 0.5 và 0.9 theo cách checkpoint writes được trải thời gian. Vì sao setting này không giới hạn toàn bộ I/O?

### Bài 10 — FPI

Giải thích full-page image và torn-page protection. Vì sao lần sửa đầu tiên sau checkpoint có thể tạo WAL lớn hơn?

### Bài 11 — Checkpoint dày và WAL

Một workload chạm 500.000 pages mỗi checkpoint cycle. Giải thích vì sao checkpoint thường xuyên có thể tăng FPI count và WAL bytes.

### Bài 12 — full_page_writes

Vì sao không nên tắt full_page_writes chỉ để giảm WAL volume? Nêu rủi ro sau crash/power failure.

### Bài 13 — wal_compression

Giải thích trade-off CPU và WAL bytes khi bật wal_compression. Những metrics nào cần so sánh trước/sau?

### Bài 14 — Checkpointer và bgwriter

Phân biệt checkpointer, background writer và backend writes. Vì sao tăng bgwriter không thay thế checkpoint?

### Bài 15 — Checkpoint write/sync time

Một server có checkpoint write_time cao nhưng sync_time thấp. Nêu các giả thuyết cần kiểm tra trước khi kết luận storage chậm.

### Bài 16 — Checkpoint stats PG16

Truy vấn checkpoints_timed, checkpoints_req, checkpoint_write_time và buffers_checkpoint từ pg_stat_bgwriter. Giải thích từng metric.

### Bài 17 — Checkpoint stats PG17

Truy vấn num_timed, num_requested, write_time, sync_time và buffers_written từ pg_stat_checkpointer. Vì sao dashboard PG16 không thể dùng nguyên xi?

### Bài 18 — WAL stats

Truy vấn wal_records, wal_fpi, wal_bytes, wal_buffers_full và stats_reset từ pg_stat_wal. Metric nào phản ánh WAL generation?

### Bài 19 — Tính WAL rate

wal_bytes tăng từ 120 GB lên 150 GB trong 10 phút. Tính WAL rate theo MB/s thập phân. Nêu điều cần kiểm tra nếu stats_reset thay đổi giữa hai samples.

### Bài 20 — LSN distance

Dùng pg_current_wal_lsn và pg_wal_lsn_diff để đo WAL bytes giữa hai samples. Vì sao đây là LSN address distance, không nhất thiết giống hệt pg_stat_wal.wal_bytes delta?

### Bài 21 — Requested checkpoint ratio

Một giờ có 40 timed checkpoints và 160 requested checkpoints. Tính requested percentage. Vì sao cần đọc log trước khi kết luận max_wal_size quá thấp?

### Bài 22 — Archive stats

Truy vấn pg_stat_archiver. Nếu failed_count tăng và last_archived_time không đổi, hãy lập danh sách kiểm tra destination/network/credentials.

### Bài 23 — Replication slot

Một logical slot inactive giữ restart_lsn cách current WAL LSN 80 GB. Giải thích nguy cơ disk và vì sao không drop slot ngay.

### Bài 24 — wal_keep_size

Phân biệt wal_keep_size với replication slot retention và archive retention. Vì sao một setting không thay thế hai cơ chế còn lại?

### Bài 25 — Replica lag

Truy vấn sent_lsn, write_lsn, flush_lsn, replay_lsn trên primary. Giải thích khoảng cách nào thể hiện standby chưa replay kịp.

### Bài 26 — pg_wal directory

Dùng pg_ls_waldir() để đếm files và tổng size. Vì sao phải kết hợp với OS free space và archive/slot metrics?

### Bài 27 — pg_stat_io

Trên PG16+, group I/O stats theo backend_type/object/context. Nêu giới hạn của view so với OS/provider storage metrics.

### Bài 28 — WAL writer

Phân biệt wal_buffers, wal_writer_delay, wal_writer_flush_after và checkpointer. Vì sao tăng wal_buffers không tự động giải quyết WAL storage latency?

### Bài 29 — synchronous_commit

Giải thích tại sao synchronous_commit=off có thể giảm commit wait nhưng không giảm WAL generation. Rủi ro durability là gì?

### Bài 30 — fsync

Giải thích vì sao tắt fsync trên production không phải cách xử lý I/O cao. Nêu điều cần đo nếu fsync latency lớn.

### Bài 31 — Query nào tạo WAL?

Dùng pg_stat_statements WAL counters nếu version hỗ trợ để xếp hạng query theo wal_bytes. Phân biệt total WAL với WAL per call.

### Bài 32 — Index amplification

Một bảng có 8 indexes. Giải thích tại sao INSERT/UPDATE có thể tạo nhiều WAL hơn heap-only changes và cách đánh giá index không cần thiết.

### Bài 33 — HOT updates

Truy vấn n_tup_upd và n_tup_hot_upd. Vì sao update cột không được index có thể giảm index churn trong điều kiện phù hợp?

### Bài 34 — Bulk load

So sánh COPY vào bảng logged hiện hữu với UNLOGGED staging và xây indexes sau load trên bảng mới. Nêu durability/replication trade-offs.

### Bài 35 — CHECKPOINT và pg_switch_wal

Giải thích hai lệnh CHECKPOINT và pg_switch_wal() khác nhau thế nào. Vì sao gọi pg_switch_wal liên tục có thể tăng archive work?

### Bài 36 — Storage saturation

Một volume giới hạn 500 MB/s, checkpoint dùng 350 MB/s, WAL dùng 100 MB/s và queries cần 200 MB/s. Giải thích queue/latency sẽ thay đổi thế nào và đề xuất cách giảm peak.

### Bài 37 — Tuning max_wal_size

Thiết kế quy trình tăng max_wal_size có đo baseline, disk headroom, requested checkpoint rate, archive/replication retention và RTO.

### Bài 38 — Runbook pg_wal tăng

Viết runbook khi pg_wal tăng nhanh: theo dõi wal_bytes/s, archive failures, replication slots, replica lag, free disk và các bước khôi phục.

### Bài 39 — Checkpoint dày sau deploy

Một deploy thêm audit trigger và index mới. WAL rate, requested checkpoints và query p99 đều tăng. Hãy xác định metrics cần đối chiếu và kế hoạch rollback/tuning an toàn.

### Bài 40 — Thiết kế WAL/checkpoint cho production

Một PostgreSQL primary có:

- 4 TB dữ liệu.
- OLTP 5.000 transactions/second.
- Batch ETL tạo 50 MB/s WAL trong 20 phút.
- Hai physical standbys, một logical replication slot.
- Archive destination đôi khi chậm 5 phút.
- Storage có giới hạn IOPS và p99 query latency là SLA quan trọng.
- Recovery time objective là 15 phút.

Hãy thiết kế:

1. Bộ dashboard WAL rate, FPI, checkpoint counts, write/sync time.
2. Cách xác định requested checkpoints có do max_wal_size hay do manual operation.
3. Chính sách max_wal_size/checkpoint_timeout/completion_target theo workload và RTO.
4. Disk headroom cho pg_wal khi archive chậm và slot giữ WAL.
5. Alert theo WAL generation, archive failure, slot retained distance và time-to-full.
6. Kế hoạch điều tiết ETL để bảo vệ OLTP latency.
7. Cách đánh giá wal_compression và full_page_writes.
8. Phân biệt primary checkpoint I/O với standby replay I/O.
9. Runbook khi archive/slot backlog làm volume gần đầy.
10. Cách benchmark/recovery-test trước khi áp dụng cấu hình production.

## Kết luận

**WAL bảo vệ durability và khả năng recovery của PostgreSQL.** Transaction commit có thể được xác nhận sau khi WAL cần thiết được flush, trong khi data pages vẫn còn dirty trong shared buffers. Checkpoint ghi các pages cần thiết xuống data files và tạo recovery point mới để giới hạn WAL phải replay sau crash.

**Checkpoint quá dày có thể làm I/O tăng và WAL generation tăng thêm qua full-page images.** Timed checkpoints phụ thuộc checkpoint_timeout; requested checkpoints thường liên quan WAL vượt max_wal_size. checkpoint_completion_target giúp trải checkpoint writes, còn max_wal_size điều phối checkpoint frequency theo lượng WAL. Các setting này cần được chọn cùng disk headroom và recovery time objective.

**WAL generation và WAL retention là hai việc khác nhau.** pg_stat_wal cho biết WAL được tạo; pg_stat_checkpointer/pg_stat_bgwriter và checkpoint logs cho biết checkpoint activity; pg_stat_archiver, replication slots và standby LSNs giúp tìm WAL bị giữ. Nếu pg_wal tăng, phải xác định đang tạo quá nhanh hay recycle/archive không theo kịp.

Cuối cùng, hãy đo WAL rate, FPI, checkpoint counts, write/sync time, storage latency, archive backlog và replica lag trên cùng timeline. Tuning tốt thường kết hợp giảm write amplification ở workload, checkpoint scheduling phù hợp, storage đủ năng lực và retention policy rõ ràng. **Không tắt durability protections hoặc xóa WAL thủ công để làm dashboard đẹp hơn; giữ WAL đúng cách là giữ khả năng phục hồi của database.**

