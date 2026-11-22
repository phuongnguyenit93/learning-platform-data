# Điều chỉnh checkpoint, WAL và tải ghi trong PostgreSQL

PostgreSQL ghi dữ liệu theo cơ chế Write-Ahead Logging (WAL): thay đổi được ghi vào WAL trước khi các data pages tương ứng cần được ghi xuống data files. Checkpoint định kỳ giúp xác định điểm phục hồi và đẩy các dirty buffers xuống storage. Cơ chế này cho phép PostgreSQL phục hồi sau crash, nhưng cũng tạo ra một workload ghi gồm WAL writes, data-page writes, checkpoint I/O, archive traffic và replication traffic.

Khi checkpoint quá thường xuyên, storage có thể xuất hiện các đợt ghi dữ liệu lớn, WAL tăng nhanh và full-page images làm lượng WAL phình lên. Khi checkpoint bị dồn vào thời điểm không phù hợp, latency của ứng dụng có thể tăng. Ngược lại, tăng ngưỡng WAL quá mức mà không tính disk capacity có thể khiến volume hết chỗ, nhất là khi replication slots hoặc archive đang giữ WAL.

Điều chỉnh checkpoint, WAL và tải ghi cần bắt đầu bằng số liệu: checkpoint nào đang xảy ra, WAL tạo ra bao nhiêu, backend đang chờ I/O hay WAL flush, storage có đủ throughput không và workload nào tạo nhiều writes. Sau đó thay đổi từng nhóm tham số, benchmark trên workload đại diện và xác minh cả hiệu năng lẫn durability.

Bài học này giải thích write path của PostgreSQL, checkpoint lifecycle, các tham số WAL/checkpoint quan trọng, commit durability, synchronous replication, cách giảm write amplification và quy trình tuning an toàn cho production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả vai trò của WAL trong crash recovery và durability.
2. Phân biệt WAL writes, data-page writes, commit flush và checkpoint.
3. Giải thích checkpoint được kích hoạt bởi thời gian hoặc WAL volume.
4. Hiểu tác động của checkpoint_timeout, max_wal_size và checkpoint_completion_target.
5. Phân biệt min_wal_size, wal_keep_size và max_slot_wal_keep_size.
6. Đọc checkpoint statistics, pg_stat_wal và I/O statistics.
7. Hiểu full_page_writes, full-page images và wal_compression.
8. Đánh giá wal_buffers, WAL writer và background writer.
9. Phân biệt synchronous_commit với synchronous replication.
10. Điều chỉnh commit batching và transaction size.
11. Giảm write amplification từ indexes, UPDATE patterns và bulk workloads.
12. Theo dõi archive backlog, replication lag và WAL retention.
13. Tuning theo baseline, benchmark và từng thay đổi nhỏ.
14. Xử lý checkpoint spikes, WAL growth và storage saturation.
15. Thiết kế monitoring, alerting và runbooks cho write-heavy PostgreSQL.

## 2. Tổng quan write path

Khi ứng dụng thay đổi một row, PostgreSQL không nhất thiết ghi ngay data page chứa row đó xuống data file. Thay vào đó, database tạo WAL records mô tả thay đổi. WAL được ghi theo thứ tự tuần tự, trong khi các data pages được cập nhật trong shared buffers và ghi xuống storage theo lịch phù hợp.

~~~text
Application transaction
        |
        v
Modify shared buffers
        |
        +---- Generate WAL records
        |          |
        |          v
        |      WAL buffers
        |          |
        |          v
        |      WAL files (pg_wal)
        |          |
        |          +---- Archive
        |          |
        |          +---- Replication stream
        |
        v
Dirty data pages
        |
        v
Checkpointer / background writer / backend writes
        |
        v
Data files on storage
~~~

### 2.1. WAL đi trước data pages

Write-Ahead Logging yêu cầu WAL records liên quan phải được ghi bền vững trước khi data pages tương ứng được flush xuống storage. Nếu server crash, PostgreSQL dùng WAL để redo những thay đổi cần thiết từ checkpoint gần nhất.

### 2.2. Commit không đồng nghĩa ghi mọi data page

Với synchronous_commit mặc định là on, commit thường đợi WAL của transaction được flush theo durability policy. Nó không phải chờ mọi data page đã thay đổi được ghi xuống table/index files. Checkpoint đảm nhiệm việc ghi các dirty buffers và cập nhật recovery point.

### 2.3. Hai loại I/O khác nhau

- WAL I/O: thường tuần tự, append-oriented và liên quan commit/replication/archive.
- Data-file I/O: ghi các pages của tables/indexes; checkpoint có thể tạo lượng ghi lớn.
- Temporary I/O: sort/hash spill hoặc temporary relations.
- Archive/replication I/O: truyền WAL ra nơi lưu trữ hoặc replica.

### 2.4. Vì sao tuning phải nhìn cả hai?

Tăng throughput WAL không đảm bảo data-page writes theo kịp. Tăng checkpoint frequency có thể giảm dirty buffers tích tụ nhưng tăng write bursts và full-page images. Tuning cần cân bằng latency, throughput, recovery time và disk capacity.

## 3. WAL là gì?

WAL là chuỗi records mô tả những thay đổi cần thiết để phục hồi database. WAL files được lưu trong thư mục pg_wal của data directory, trừ khi layout/deployment có cách bố trí storage riêng.

### 3.1. WAL records

Các thao tác như INSERT, UPDATE, DELETE, index changes và một số catalog/metadata changes tạo WAL. Một transaction có thể tạo nhiều WAL records trước khi commit.

### 3.2. WAL segments

WAL được chia thành các segment files. Segment size thường là 16 MB trong các bản build phổ biến, nhưng không nên hard-code assumption; có thể kiểm tra build/runtime hoặc dùng công cụ PostgreSQL phù hợp.

### 3.3. LSN

Log Sequence Number (LSN) xác định vị trí trong WAL stream.

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            '0/0'::pg_lsn
        )::bigint
    ) AS approximate_position_from_start;
~~~

LSN là vị trí logic trong WAL stream, không phải số bytes hiện có trong thư mục pg_wal.

### 3.4. WAL và backup/PITR

WAL archive kết hợp với base backup cho phép point-in-time recovery. Chỉ có streaming replication không thay thế backup; replication có thể truyền cả thao tác xóa nhầm hoặc dữ liệu bị hỏng logic.

### 3.5. WAL và replication

Physical standby nhận WAL để replay. Logical decoding đọc WAL và chuyển thành changes logic. Logical replication cần wal_level=logical trên publisher; physical replication cần wal_level=replica hoặc logical.

## 4. Checkpoint là gì?

Checkpoint là một mốc trong WAL/recovery process, tại đó PostgreSQL bảo đảm các dirty buffers cần thiết đã được ghi xuống data files và ghi checkpoint record vào WAL. Sau crash, PostgreSQL có thể bắt đầu redo từ checkpoint phù hợp thay vì replay toàn bộ WAL từ đầu lịch sử.

### 4.1. Dirty buffers

Khi transaction thay đổi page trong shared buffers, page đó trở thành dirty. Page có thể được ghi xuống disk bởi checkpointer, background writer hoặc backend process trong những tình huống nhất định.

### 4.2. Checkpointer

Checkpointer thực hiện checkpoint writes và sync các files cần thiết theo quy trình PostgreSQL. Một checkpoint có thể tạo lượng data-file I/O đáng kể.

### 4.3. Checkpoint record

Checkpoint record lưu thông tin recovery cần thiết trong WAL. Sau checkpoint thành công, WAL trước mốc checkpoint có thể được recycle/archive theo điều kiện về backup, archive, replication slots và các consumers khác.

### 4.4. Timed checkpoint

Checkpoint có thể được khởi động khi đạt checkpoint_timeout kể từ checkpoint trước.

### 4.5. Requested checkpoint

Checkpoint cũng có thể được yêu cầu khi WAL volume tiến gần/vượt ngưỡng max_wal_size. Checkpoint thủ công bằng lệnh CHECKPOINT cũng có thể xuất hiện trong thống kê.

### 4.6. Checkpoint không phải commit

Commit xác nhận transaction theo WAL durability policy. Checkpoint ghi dirty pages và thiết lập recovery point. Một transaction có thể được commit bền vững trước khi data pages của nó được ghi bởi checkpoint.

## 5. Checkpoint lifecycle

~~~text
Writes accumulate
      |
      v
Dirty buffers + WAL generation
      |
      +---- checkpoint_timeout reached
      |
      +---- WAL reaches checkpoint pressure
      |
      v
Checkpoint begins
      |
      v
Dirty buffers written over checkpoint interval
      |
      v
Required files synced
      |
      v
Checkpoint record / completion
      |
      v
Old WAL eligible for recycle when other retention rules allow
~~~

### 5.1. Checkpoint write phase

PostgreSQL cố gắng trải việc ghi dirty pages trên một phần của khoảng thời gian checkpoint để tránh dồn toàn bộ I/O vào một thời điểm.

### 5.2. Checkpoint sync phase

Các files đã ghi cần được sync theo durability requirements. Storage latency và filesystem behavior ảnh hưởng thời gian sync.

### 5.3. Checkpoint có thể gây latency

Nếu storage không đủ throughput, checkpoint writes cạnh tranh với application reads/writes. Backend có thể phải tự ghi buffers khi shared buffers cần chỗ trống.

### 5.4. Checkpoint quá thường xuyên

Checkpoint liên tục có thể:
- Tăng data-page write activity.
- Tăng số full-page images trong WAL.
- Tăng write amplification.
- Làm checkpoint I/O cạnh tranh với ứng dụng.
- Tạo cảnh báo checkpoint thường xuyên trong logs.

### 5.5. Checkpoint quá thưa

Checkpoint thưa hơn có thể giảm tần suất checkpoint và full-page-image overhead, nhưng:
- Cần giữ nhiều WAL hơn.
- Recovery sau crash có thể phải replay lượng WAL lớn hơn.
- Checkpoint có thể mất nhiều thời gian hơn.
- Disk pressure tăng nếu archive/slots giữ WAL.

## 6. Các tham số checkpoint quan trọng

| Tham số | Vai trò | Hướng điều chỉnh thường gặp |
| --- | --- | --- |
| checkpoint_timeout | Khoảng thời gian tối đa giữa timed checkpoints | Tăng nếu checkpoint quá thường xuyên và recovery budget cho phép |
| max_wal_size | Ngưỡng WAL mềm kích hoạt checkpoint pressure | Tăng nếu requested checkpoints quá nhiều và disk đủ |
| min_wal_size | Mức WAL tối thiểu được giữ/recycle | Điều chỉnh theo workload và WAL reuse |
| checkpoint_completion_target | Phần checkpoint interval dành để hoàn tất checkpoint | Giữ mức cao phù hợp để trải writes |
| checkpoint_warning | Ngưỡng cảnh báo checkpoint quá thường xuyên | Dùng để nhận biết pressure |
| log_checkpoints | Ghi log chi tiết checkpoint | Bật để quan sát và phân tích |

Giá trị mặc định thay đổi theo PostgreSQL major version và package/provider. Đọc SHOW hoặc pg_settings thay vì giả định một default chung.

## 7. checkpoint_timeout

checkpoint_timeout giới hạn thời gian giữa các timed checkpoints. Giá trị mặc định phổ biến là 5 phút, nhưng hãy kiểm tra phiên bản cụ thể.

~~~sql
SHOW checkpoint_timeout;
~~~

### 7.1. Khi tăng checkpoint_timeout

Có thể giảm số timed checkpoints và giảm tần suất full-page images. Đổi lại, mỗi checkpoint có thể bao phủ một khoảng WAL dài hơn và crash recovery có thể phải replay nhiều WAL hơn.

### 7.2. Khi giảm checkpoint_timeout

Có thể rút ngắn lượng WAL cần replay sau crash, nhưng checkpoint xuất hiện thường xuyên hơn, tạo thêm data-page writes và full-page-image activity.

### 7.3. Không dùng checkpoint_timeout riêng lẻ

Checkpoint còn bị kích hoạt bởi WAL volume. Nếu max_wal_size quá thấp, tăng checkpoint_timeout không ngăn requested checkpoints.

### 7.4. Recovery budget

Chọn checkpoint_timeout theo recovery time objective, WAL generation rate và storage capacity. Đo thời gian recovery trong rehearsal thay vì suy luận chỉ từ setting.

## 8. max_wal_size

max_wal_size là ngưỡng mềm để PostgreSQL quyết định khi nào cần checkpoint do lượng WAL. Nó không phải hard cap cho tổng dung lượng pg_wal.

~~~sql
SHOW max_wal_size;
~~~

### 8.1. Tăng max_wal_size

Nếu logs/statistics cho thấy requested checkpoints quá nhiều do WAL volume, tăng max_wal_size có thể làm checkpoint thưa hơn. Cần có đủ storage headroom và hiểu WAL retention do archive/replication slots.

### 8.2. Giảm max_wal_size

Có thể khiến checkpoint xảy ra sớm hơn, giới hạn lượng WAL được giữ trong một số tình huống bình thường nhưng làm tăng checkpoint frequency và FPI overhead. Đây không phải biện pháp an toàn để chữa volume đầy nếu nguyên nhân là slot/archive retention.

### 8.3. Vì sao pg_wal có thể vượt max_wal_size?

- Replication slots giữ WAL mà consumer chưa xác nhận.
- wal_keep_size yêu cầu giữ một lượng WAL cho standby.
- Archive command đang lỗi hoặc archive chưa hoàn tất.
- Workload burst tạo WAL nhanh hơn dự kiến.
- Checkpoint/recycle chưa giải phóng segment.
- Backup/recovery process cần WAL.

### 8.4. Capacity planning

Ước lượng WAL generation rate × outage/retention duration, cộng burst headroom. Tính riêng:
- Normal checkpoint working set.
- Physical/logical slot retention.
- Archive backlog.
- Backup/PITR retention.
- Temporary and maintenance headroom.

## 9. min_wal_size

min_wal_size là lượng WAL tối thiểu PostgreSQL cố gắng giữ để tái sử dụng, giúp tránh liên tục tạo/xóa segment trong workload có WAL generation dao động.

~~~sql
SHOW min_wal_size;
~~~

### 9.1. Giá trị quá thấp

Có thể làm PostgreSQL phải tạo thêm WAL segment files khi workload tăng trở lại. Tác động phụ thuộc storage/filesystem và workload.

### 9.2. Giá trị quá cao

Giữ lại nhiều WAL segment files hơn trong pg_wal sau khi không còn cần cho recovery/retention. Điều này tiêu tốn disk capacity.

### 9.3. min_wal_size không phải archive retention

Nó không quyết định thời gian giữ WAL trong archive và không thay thế backup retention policy.

## 10. checkpoint_completion_target

checkpoint_completion_target điều khiển phần thời gian checkpoint interval mà PostgreSQL cố gắng dùng để hoàn tất checkpoint writes. Giá trị cao giúp trải writes đều hơn thay vì dồn vào đầu interval.

~~~sql
SHOW checkpoint_completion_target;
~~~

### 10.1. Giá trị cao

Một giá trị gần 1 có thể giảm write bursts bằng cách phân tán checkpoint I/O. Cần chừa thời gian cho các hoạt động khác và xem behavior thực tế.

### 10.2. Giá trị thấp

Checkpoint writes được dồn vào khoảng thời gian ngắn hơn, có thể tạo I/O spikes và latency cao hơn.

### 10.3. Không phải write throttle tổng thể

Setting này điều chỉnh checkpoint pacing; nó không giới hạn toàn bộ writes của application, WAL writer, background writer hay backend processes.

## 11. checkpoint_warning và log_checkpoints

~~~sql
SHOW checkpoint_warning;
SHOW log_checkpoints;
~~~

### 11.1. checkpoint_warning

Setting này yêu cầu PostgreSQL ghi cảnh báo khi requested checkpoints xảy ra quá thường xuyên theo ngưỡng. Nó giúp nhận diện max_wal_size quá thấp so với WAL generation rate.

### 11.2. log_checkpoints

Khi bật, PostgreSQL ghi checkpoint statistics vào server logs, bao gồm thời gian write/sync và buffers theo version. Dùng logs để đối chiếu với latency và storage metrics.

### 11.3. Cấu hình logging

Bật log_checkpoints trong môi trường cần phân tích checkpoint. Đảm bảo log retention, log rotation và log volume được quản lý.

## 12. Full-page images và full_page_writes

Sau checkpoint, lần đầu một data page được sửa đổi có thể cần ghi full-page image vào WAL để bảo vệ khỏi torn-page writes trong một số failure scenarios.

### 12.1. Vì sao có full-page images?

Một page có thể được ghi xuống storage không nguyên tử. Nếu crash xảy ra giữa quá trình ghi, page có thể bị torn. Full-page image trong WAL giúp PostgreSQL phục hồi page về trạng thái nhất quán trước khi redo các changes tiếp theo.

### 12.2. full_page_writes

~~~sql
SHOW full_page_writes;
~~~

Trong production, thông thường giữ full_page_writes=on. Tắt setting này có thể khiến database dễ bị hỏng page sau crash/power failure nếu storage không bảo đảm atomic page writes.

### 12.3. Tác động checkpoint

Sau checkpoint, page được sửa lần đầu có thể tạo FPI. Checkpoint quá thường xuyên có thể làm cùng page phải tạo FPI lặp lại nhiều lần trong một khoảng thời gian ngắn.

### 12.4. WAL amplification

FPI làm WAL bytes tăng so với chỉ ghi delta records. Vì vậy, tuning checkpoint và WAL compression có thể ảnh hưởng đáng kể WAL volume.

### 12.5. Không tắt full_page_writes để giảm WAL

Giảm WAL bằng cách tắt cơ chế bảo vệ torn pages là trade-off durability/recovery nguy hiểm. Tìm nguyên nhân FPI cao và dùng các biện pháp phù hợp khác.

## 13. wal_compression

wal_compression cho phép nén full-page images trong WAL trên các versions hỗ trợ.

~~~sql
SHOW wal_compression;
~~~

Các lựa chọn cụ thể phụ thuộc PostgreSQL version và build, có thể gồm off/on hoặc các thuật toán nén được hỗ trợ như pglz, lz4, zstd.

### 13.1. Lợi ích

Nén FPI có thể giảm WAL bytes, archive bandwidth và replication traffic, đặc biệt khi FPI chiếm tỷ trọng lớn.

### 13.2. Chi phí

Compression dùng CPU. Nếu CPU đã bão hòa, giảm disk/network bytes có thể không cải thiện throughput tổng thể.

### 13.3. Đo trước và sau

So sánh:
- wal_bytes/sec.
- wal_fpi / wal_records.
- CPU usage.
- WAL archive throughput.
- Replication lag.
- Commit latency.

### 13.4. Không phải nén mọi WAL record

Setting này tập trung vào full-page images; nó không biến toàn bộ WAL stream thành một archive nén chung.

## 14. wal_level và tác động tới WAL

Các mức chính:

| Mức | Mục đích |
| --- | --- |
| minimal | Giảm một số WAL requirements trong những chế độ phù hợp, không dùng cho replication/archiving thông thường |
| replica | WAL cho crash recovery, archiving và physical replication |
| logical | Bổ sung thông tin cần cho logical decoding |

### 14.1. Không hạ wal_level khi cần replication

Physical standby và WAL archiving cần mức phù hợp, thường là replica hoặc logical. Logical decoding cần logical.

### 14.2. logical có thể tạo thêm WAL

Logical level có thể tăng WAL overhead do cần thông tin phục vụ logical decoding. Đo workload thật khi chuyển từ replica sang logical.

### 14.3. Restart requirement

wal_level cần restart PostgreSQL. Kiểm tra pending_restart và kế hoạch rolling/restart theo HA topology.

## 15. wal_buffers

wal_buffers là shared memory dùng để đệm WAL records trước khi ghi ra WAL files.

~~~sql
SHOW wal_buffers;
~~~

### 15.1. Giá trị tự động

Giá trị -1 cho phép PostgreSQL tự chọn dựa trên shared_buffers với giới hạn theo version. Đây thường là điểm bắt đầu tốt.

### 15.2. Khi nào cần điều chỉnh?

Chỉ cân nhắc nếu có evidence cho thấy WAL buffers thường xuyên đầy hoặc WAL write path bị bottleneck. pg_stat_wal có counter wal_buffers_full ở các versions hỗ trợ.

### 15.3. Không tăng chỉ vì write volume cao

wal_buffers không làm storage chậm trở nên nhanh. Nếu bottleneck là fsync latency, disk throughput hoặc checkpoint writes, tăng buffer không giải quyết gốc rễ.

### 15.4. Kiểm tra

~~~sql
SELECT
    wal_buffers,
    shared_buffers
FROM pg_settings
WHERE name IN ('wal_buffers', 'shared_buffers');
~~~

## 16. WAL writer

WAL writer background process định kỳ ghi WAL buffers xuống WAL files. Một số settings ảnh hưởng nhịp ghi và flush.

### 16.1. wal_writer_delay

~~~sql
SHOW wal_writer_delay;
~~~

Điều khiển khoảng delay giữa các lần WAL writer hoạt động. Giảm delay có thể làm WAL được ghi thường xuyên hơn, nhưng tăng hoạt động I/O; tăng delay có thể gom writes nhưng ảnh hưởng độ trễ của một số commits khi synchronous_commit=off.

### 16.2. wal_writer_flush_after

~~~sql
SHOW wal_writer_flush_after;
~~~

Điều khiển lượng WAL ghi trước khi WAL writer thực hiện flush theo setting này. Behavior cụ thể phụ thuộc version/platform.

### 16.3. Không điều chỉnh khi chưa có evidence

WAL writer thường hoạt động tốt với defaults. Chỉ tuning sau khi đã xem wal_buffers_full, WAL write/sync times, commit latency và OS storage metrics.

## 17. Background writer và backend writes

Background writer cố gắng ghi dirty buffers trước khi backend cần chỗ trống trong shared buffers. Checkpointer có nhiệm vụ checkpoint; background writer hỗ trợ giảm công việc ghi đồng bộ mà backend phải tự làm.

### 17.1. bgwriter_lru_maxpages

Giới hạn số pages background writer cố gắng ghi trong một round theo setting.

### 17.2. bgwriter_lru_multiplier

Điều chỉnh mức dự đoán nhu cầu buffer sắp tới dựa trên recent consumption.

### 17.3. bgwriter_delay

Điều chỉnh thời gian nghỉ giữa các rounds của background writer.

### 17.4. buffers_backend

Ở các versions có counter tương ứng, backend writes có thể cho biết application backends phải tự ghi dirty buffers. Đây là một tín hiệu để xem background writer có theo kịp workload hay không.

### 17.5. Không nhầm bgwriter với checkpointer

Background writer không thay checkpoint. Tuning bgwriter không sửa được mọi checkpoint spikes hoặc WAL retention issues.

## 18. pg_stat_checkpointer và checkpoint statistics theo version

Tên/cấu trúc statistics views thay đổi theo major version.

### 18.1. PostgreSQL 17 trở lên

Checkpoint statistics được tách ra view pg_stat_checkpointer. Có thể khám phá các counters bằng:

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

Các trường bao gồm số timed/requested checkpoints, thời gian write/sync và số buffers written theo version.

### 18.2. Các phiên bản cũ hơn

Checkpoint counters thường nằm trong pg_stat_bgwriter:

~~~sql
SELECT *
FROM pg_stat_bgwriter;
~~~

Một số counters quen thuộc là checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time và buffers_checkpoint. Schema thay đổi ở PostgreSQL 17; không dùng query cột cũ trên server mới mà chưa kiểm tra.

### 18.3. Requested/timed ratio

Nếu requested checkpoints chiếm tỷ lệ cao so với timed checkpoints, WAL volume có thể đang kích hoạt checkpoint quá thường xuyên. Kiểm tra max_wal_size, WAL rate và logs.

### 18.4. Checkpoint duration

Checkpoint write/sync times cao có thể phản ánh storage chậm, volume contention hoặc checkpoint writes quá lớn. Đối chiếu OS-level latency.

### 18.5. Stats reset

Counters là số tích lũy từ stats reset. Lấy snapshots và tính delta; nếu stats_reset thay đổi, bắt đầu một series mới.

## 19. pg_stat_wal: đo WAL generation và write behavior

pg_stat_wal có từ PostgreSQL 14. Kiểm tra schema trên version đang chạy:

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

Các counters quan trọng có thể gồm:
- wal_records: số WAL records.
- wal_fpi: số full-page images.
- wal_bytes: số bytes WAL được tạo.
- wal_buffers_full: số lần WAL buffers đầy trong các tình huống được đếm.
- wal_write và wal_sync: số lần write/sync.
- wal_write_time và wal_sync_time: thời gian ghi/sync nếu timing được bật.
- stats_reset: thời điểm reset statistics.

### 19.1. WAL bytes/sec

Lấy hai snapshots của wal_bytes:

\[
\text{WAL bytes/sec} =
\frac{\text{current wal\_bytes} - \text{previous wal\_bytes}}
{\text{elapsed seconds}}
\]

Không tính delta nếu stats_reset đổi hoặc counter bị reset.

### 19.2. FPI ratio

So sánh wal_fpi với wal_records và wal_bytes. Một workload có nhiều page modifications sau checkpoint có thể tạo nhiều FPIs. Đọc cùng checkpoint frequency và wal_compression.

### 19.3. wal_buffers_full

Counter cao cần được so sánh với tổng WAL records/bytes và commit latency. Không kết luận chỉ từ một counter đơn lẻ.

### 19.4. Timing counters

Nếu wal_write_time/wal_sync_time bằng zero, kiểm tra setting thu thập timing theo version. Không mặc định zero nghĩa là storage không có latency.

## 20. pg_stat_io: quan sát I/O theo backend và context

pg_stat_io được giới thiệu từ PostgreSQL 16. Nó cung cấp thống kê I/O theo backend type, object và context; các cột cụ thể phụ thuộc version.

~~~sql
SELECT *
FROM pg_stat_io;
~~~

### 20.1. Đọc theo context

Context có thể giúp phân biệt normal operations, bulk operations và maintenance I/O theo semantics của version.

### 20.2. Backend type

Có thể xem I/O từ client backends, background writer, checkpointer, autovacuum và các process khác.

### 20.3. Không thay OS metrics

pg_stat_io cung cấp PostgreSQL-level view. Device latency, queue depth, saturation và filesystem behavior vẫn cần host/provider metrics.

### 20.4. Sampling

Lưu snapshots, tính deltas và gắn stats_reset. Tránh dùng cumulative counters như rate tức thời.

## 21. Wait events liên quan tới WAL và checkpoint

pg_stat_activity có wait_event_type và wait_event.

~~~sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    application_name,
    clock_timestamp() - query_start AS query_age,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE wait_event_type IN ('IO', 'LWLock', 'Activity')
ORDER BY query_start NULLS LAST;
~~~

Tên wait events cụ thể thay đổi theo PostgreSQL version. Một số event có thể liên quan WAL write/sync, checkpoint write/sync hoặc buffer I/O.

### 21.1. WALWrite/WALSync

Một backend có thể chờ WAL write hoặc sync. Nếu nhiều commits cùng chờ và OS reports high storage latency, WAL device có thể là bottleneck.

### 21.2. Checkpoint waits

Các process có thể chờ checkpoint-related activity hoặc I/O. Kết hợp checkpoint stats, logs và disk metrics.

### 21.3. LWLock

Một wait thuộc LWLock không tự chứng minh WAL bottleneck. Xác định tên event cụ thể và đối chiếu workload.

### 21.4. Snapshot sampling

Wait event có thể đổi nhanh. Lấy nhiều samples hoặc dùng tracing/monitoring để phân biệt transient waits với sustained contention.

## 22. Commit durability và synchronous_commit

synchronous_commit quyết định mức độ chờ WAL durability khi transaction commit. Nó không giống synchronous_standby_names, dù hai setting tương tác khi synchronous replication được cấu hình.

~~~sql
SHOW synchronous_commit;
~~~

### 22.1. on

Với local commit, đợi WAL transaction được flush bền vững trên local storage. Nếu synchronous standby được cấu hình, mức on thường đợi standby xác nhận WAL đã flush theo synchronous replication semantics.

### 22.2. off

Không đợi WAL flush trước khi báo commit thành công. Server vẫn ghi WAL theo cơ chế nền; crash có thể làm mất các transactions vừa được xác nhận trong một khoảng ngắn, nhưng database vẫn được bảo vệ về consistency theo thiết kế PostgreSQL.

Chỉ dùng cho dữ liệu có thể tái tạo hoặc chấp nhận mất một số transactions gần nhất. Không dùng như tuning mặc định cho dữ liệu tài chính/critical.

### 22.3. local

Đợi local WAL flush nhưng không đợi remote synchronous standby. Hữu ích trong một số thiết kế cần local durability nhưng không muốn remote wait.

### 22.4. remote_write

Khi synchronous standby được cấu hình, chờ standby ghi WAL tới operating system, nhưng chưa nhất thiết flush bền vững xuống storage. Mức bảo vệ phụ thuộc failure model của standby host/OS.

### 22.5. remote_apply

Chờ synchronous standby replay transaction để transaction visible trên standby. Có thể tăng commit latency đáng kể, nhưng phù hợp khi yêu cầu đọc-after-write trên standby theo semantics đã thiết kế.

### 22.6. Durability trade-off

| Mode | Local flush | Remote acknowledgement | Remote replay |
| --- | --- | --- | --- |
| off | Không chờ | Không chờ | Không chờ |
| local | Có | Không chờ | Không chờ |
| on | Có | Nếu sync standby được cấu hình, chờ remote flush | Không nhất thiết |
| remote_write | Có | Chờ remote OS write | Không nhất thiết |
| remote_apply | Có | Có | Chờ replay |

Bảng mô tả tổng quát; semantics chính xác cần đối chiếu documentation của version và synchronous standby configuration.

## 23. synchronous_standby_names và replication

Synchronous replication cần cấu hình standby đủ điều kiện trong synchronous_standby_names.

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

### 23.1. Commit latency

Primary có thể chờ remote acknowledgement. Network latency, standby storage flush và standby load đều ảnh hưởng commit latency.

### 23.2. Availability trade-off

Nếu không có synchronous standby đủ điều kiện, commits có thể bị chờ tùy cấu hình. Cần thiết kế quorum/priority và failover policy.

### 23.3. Remote apply

remote_apply thêm thời gian replay trước khi commit được xác nhận. Dùng khi application cần transaction visible trên synchronous standby ngay sau commit.

### 23.4. Đừng hạ durability để che replication lag

Nếu synchronous commits chậm, điều tra network, standby disk và replication topology. Đổi sang off có thể thay đổi RPO mà không giải quyết bottleneck gốc.

## 24. fsync, full_page_writes và wal_sync_method

Các setting này ảnh hưởng trực tiếp tới durability.

### 24.1. fsync

~~~sql
SHOW fsync;
~~~

Trong production, giữ fsync=on. Tắt fsync có thể làm mất dữ liệu hoặc gây corruption không thể phục hồi sau OS crash/power failure. Không dùng để tăng throughput production.

### 24.2. full_page_writes

Giữ on trong hầu hết deployment. Nó bảo vệ trước torn-page scenarios bằng full-page images.

### 24.3. wal_sync_method

Chọn cách PostgreSQL yêu cầu OS sync WAL. Default thường phù hợp với platform. Chỉ thay đổi sau khi benchmark trên đúng filesystem, kernel, storage driver và failure model.

### 24.4. Storage phải thực hiện đúng flush semantics

Durability phụ thuộc cả PostgreSQL, OS, controller, hypervisor, cloud volume và cache policy. Một storage layer nói đã flush nhưng không bảo đảm persistence sẽ làm yếu durability.

### 24.5. pg_test_fsync

Có thể dùng pg_test_fsync để benchmark các fsync methods trên host phù hợp. Đây là công cụ benchmark, không phải bằng chứng rằng có thể tắt fsync.

## 25. wal_keep_size và replication slots

wal_keep_size chỉ định lượng WAL tối thiểu PostgreSQL cố giữ cho standby trong một số điều kiện. Nó không phải hard cap và không thay replication slots.

~~~sql
SHOW wal_keep_size;
SHOW max_slot_wal_keep_size;
~~~

### 25.1. wal_keep_size

Hỗ trợ standby nhận WAL sau một khoảng gián đoạn ngắn nếu segment vẫn còn. Nếu standby lag quá xa, có thể cần archive hoặc base backup mới.

### 25.2. Physical replication slots

Physical slot giữ WAL cần thiết cho standby. Nếu standby offline, slot có thể giữ WAL lâu và làm pg_wal tăng.

### 25.3. Logical replication slots

Logical slot giữ WAL cho decoding/subscriber. Consumer dừng có thể giữ WAL và catalog history.

### 25.4. max_slot_wal_keep_size

Giới hạn retention do slots ở các versions hỗ trợ. Khi vượt giới hạn, slot có thể bị invalidated hoặc consumer không thể tiếp tục từ vị trí cũ, tùy version/behavior. Cần resync plan.

### 25.5. Capacity alerts

Theo dõi active, restart_lsn, confirmed_flush_lsn, safe_wal_size nếu có, retained WAL estimate và free space trên volume.

## 26. Archive và WAL retention

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

### 26.1. Archive backlog

Nếu archive command không thành công, WAL segments cần archive có thể không được recycle. Theo dõi failed_count, last_failed_time và logs.

### 26.2. archive_timeout

archive_timeout có thể ép switch WAL segment sau một khoảng thời gian để archive WAL trong workload ít writes. Đặt quá thấp có thể tạo nhiều segment partially filled và tăng archive storage/traffic.

### 26.3. Archive destination

Kiểm tra capacity, credentials, permissions, network và lifecycle policy của archive storage. Một archive target đầy có thể làm pg_wal tăng trên primary.

### 26.4. Backup retention

WAL archive retention phải đủ để đáp ứng PITR window. Không xóa archive segments chỉ để giải phóng disk khi chưa xác định backup dependency.

## 27. WAL compression và archive compression

Có hai lớp compression cần phân biệt:
- wal_compression nén full-page images bên trong WAL records.
- Archive tooling/provider có thể nén WAL segment files khi lưu trữ.

Compression trong WAL giảm bytes trước khi streaming/archive; archive compression giảm storage/network ở tầng archive theo tool. Đo CPU và throughput ở cả hai lớp.

## 28. Điều chỉnh checkpoint và WAL theo triệu chứng

| Triệu chứng | Dữ liệu cần kiểm tra | Hướng điều tra |
| --- | --- | --- |
| Requested checkpoints nhiều | Checkpoint stats, log_checkpoints, WAL rate | max_wal_size, checkpoint_timeout |
| Checkpoint write time cao | Checkpoint stats, storage latency | Disk throughput, checkpoint pacing |
| WAL bytes/sec tăng đột biến | pg_stat_wal, workload changes | Bulk writes, indexes, FPI, logical level |
| pg_wal gần đầy | Slots, archive, wal_keep_size, filesystem | Consumer/archive retention |
| Commit latency cao | WAL sync times, wait events, storage | fsync latency, synchronous replication |
| Backend writes tăng | bgwriter/checkpointer stats, pg_stat_io | Shared buffers, bgwriter, storage |
| FPI ratio cao | wal_fpi, checkpoint frequency | Checkpoint interval, wal_compression |
| Archive failures | pg_stat_archiver/logs | Archive target and command |
| Replica lag | pg_stat_replication/slots | Network, standby I/O, retention |
| Temporary writes tăng | pg_stat_database, query stats | Sort/hash spill and query plans |

Không thay đổi setting chỉ dựa trên một symptom. Thu thập baseline và tìm quan hệ nhân quả.

## 29. Giảm write amplification ở workload

Không phải mọi vấn đề write throughput đều giải quyết bằng checkpoint settings. SQL/schema design thường tạo ảnh hưởng lớn hơn.

### 29.1. Giảm indexes không cần thiết

Mỗi INSERT cần cập nhật các indexes liên quan. UPDATE trên indexed columns cũng có thể phải tạo index entries mới. Kiểm tra index usage, constraints và query plans trước khi loại bỏ index.

### 29.2. HOT updates

Heap-only tuple (HOT) update có thể tránh tạo index entries mới nếu update không thay đổi columns được index tham chiếu và page còn đủ free space. Điều này giảm index write amplification.

### 29.3. Fillfactor

Giảm fillfactor cho table có UPDATE thường xuyên có thể giữ chỗ trong page để tăng cơ hội HOT updates. Đổi lại table lớn hơn và cần benchmark theo update pattern.

### 29.4. Tránh no-op updates

Chỉ update rows thực sự thay đổi. Một câu UPDATE đặt lại cùng giá trị vẫn có thể tạo row version/WAL và kích hoạt index/trigger work.

### 29.5. Cập nhật ít columns

Không ghi lại payload lớn nếu chỉ một field nhỏ thay đổi. Thiết kế SQL và application updates để tránh churn không cần thiết.

### 29.6. Retention bằng partitioning

Với dữ liệu time-series/event, detach/drop partition cũ có thể hiệu quả hơn DELETE hàng triệu rows, giảm WAL, dead tuples và vacuum work. Phải xem foreign keys, publication, backup và retention semantics.

## 30. Batch writes và transaction sizing

Batching có thể tăng throughput bằng cách amortize commit/fsync overhead.

### 30.1. Multi-row INSERT

~~~sql
INSERT INTO app.events (event_id, event_type, created_at)
VALUES
    (1001, 'created', clock_timestamp()),
    (1002, 'updated', clock_timestamp()),
    (1003, 'deleted', clock_timestamp());
~~~

### 30.2. COPY

~~~sql
COPY app.events (event_id, event_type, created_at)
FROM STDIN WITH (FORMAT csv);
~~~

COPY thường hiệu quả cho bulk loading so với nhiều single-row INSERT round trips. Logged tables vẫn tạo WAL.

### 30.3. Batch transaction

Gom nhiều rows vào một transaction có thể giảm commit overhead, nhưng transaction quá lớn làm tăng:
- Lock duration.
- WAL burst.
- Rollback cost.
- Replication lag.
- Dead tuple/vacuum impact.
- Thời gian giữ snapshots.

### 30.4. Chọn batch size bằng benchmark

Thử nhiều batch sizes với dữ liệu và concurrency đại diện. Đo rows/sec, p95/p99 commit latency, WAL bytes/row, replication lag và rollback duration.

### 30.5. Group commit

PostgreSQL có thể group commits của nhiều transactions để chia sẻ WAL flush. Không cần bật commit_delay chỉ để có group commit trong đa số trường hợp.

## 31. commit_delay và commit_siblings

commit_delay có thể trì hoãn WAL flush một khoảng rất ngắn để tăng cơ hội group commit khi có đủ concurrent transactions. commit_siblings là ngưỡng số transactions active cần có để delay được áp dụng.

~~~sql
SHOW commit_delay;
SHOW commit_siblings;
~~~

### 31.1. Khi nào cân nhắc?

Chỉ trong workload có nhiều concurrent commits và fsync overhead đáng kể, sau khi benchmark. Với workload ít concurrency, delay chỉ tăng latency.

### 31.2. Group commit đã có sẵn

PostgreSQL tự hỗ trợ group commit. Không mặc định cần tăng commit_delay.

### 31.3. Đo p95/p99

Nếu throughput tăng nhẹ nhưng tail latency tăng đáng kể, thay đổi có thể không phù hợp với OLTP SLA.

## 32. Unlogged tables và staging

Unlogged tables giảm WAL cho table data trong một số operations, nhưng không phải giải pháp chung để tăng write throughput.

### 32.1. Đặc điểm

Unlogged tables không được WAL-logged theo cách thông thường cho table contents, không được replicate như logged table rows và được truncate sau crash recovery theo semantics PostgreSQL.

### 32.2. Use cases

Chỉ dùng cho dữ liệu tạm, staging hoặc có thể tái tạo từ nguồn khác. Không dùng cho dữ liệu nghiệp vụ cần durability hoặc physical standby consistency.

### 32.3. Indexes và metadata

Hiểu rõ behavior của indexes/sequence/metadata đi kèm unlogged relations theo version. Test recovery và failover behavior.

### 32.4. Chuyển sang logged

Nếu dữ liệu staging trở thành dữ liệu chính thức, lập kế hoạch chuyển sang logged table và xác minh WAL/replication impact.

## 33. Bulk load và maintenance

Bulk loading có thể tạo WAL lớn và ảnh hưởng checkpoint/replication.

### 33.1. Chuẩn bị

- Tính disk cho table, indexes, WAL và temporary files.
- Kiểm tra replication/archive capacity.
- Chọn batch/chunk size.
- Lên lịch tránh peak application traffic.
- Xác định backup/recovery point.

### 33.2. Index strategy

Với bảng mới hoặc staging table, tạo data trước rồi build indexes có thể nhanh hơn duy trì nhiều indexes trong suốt load. Nhưng cần giữ constraints và cutover validation.

### 33.3. maintenance_work_mem

Tham số này ảnh hưởng một số maintenance operations như index build. Tăng có thể cải thiện tốc độ nhưng cần tính concurrent operations và memory budget.

### 33.4. Autovacuum

Không tắt autovacuum toàn cluster để tăng bulk load. Nếu cần điều chỉnh trên table staging, có kế hoạch vacuum/analyze và re-enable phù hợp.

### 33.5. ANALYZE sau load

Chạy ANALYZE để planner có statistics phù hợp trước khi workload production chuyển sang bảng vừa nạp.

## 34. Tác động của checkpoint tới full-page images

WAL có thể tăng mạnh ngay sau checkpoint vì lần đầu các pages được sửa đổi tạo FPI.

### 34.1. Workload page churn

Nếu workload sửa đổi nhiều pages khác nhau sau mỗi checkpoint, FPI volume có thể lớn. Nếu liên tục sửa cùng pages trong một interval, FPI chỉ cần cho lần sửa đầu tiên sau checkpoint theo semantics liên quan.

### 34.2. Checkpoint frequency

Checkpoint quá thường xuyên có thể lặp lại FPI generation trên các pages hot. Tăng checkpoint interval có thể giảm tần suất FPI nhưng làm tăng WAL working set/recovery exposure.

### 34.3. Compression

wal_compression có thể giảm bytes của FPI, đổi lại CPU.

### 34.4. Kiểm chứng

Theo dõi wal_fpi, wal_records, wal_bytes, checkpoint counters và CPU. Đo trước/sau thay đổi.

## 35. Background writer và shared buffers

shared_buffers là cache pages của PostgreSQL. Dirty pages phải được ghi xuống storage vào thời điểm phù hợp. Background writer cố gắng làm sạch buffers trước khi backend cần tái sử dụng chúng.

### 35.1. Backend writes

Nếu backend phải tự ghi nhiều dirty buffers trong lúc xử lý query, latency có thể tăng. Đây là một tín hiệu cần xem bgwriter/checkpointer behavior và I/O capacity.

### 35.2. bgwriter tuning

Tăng bgwriter_lru_maxpages hoặc multiplier có thể làm sạch nhiều buffers hơn, nhưng cũng tăng background I/O và cạnh tranh storage. Giảm quá thấp có thể đẩy công việc sang backend.

### 35.3. shared_buffers

Tăng shared_buffers có thể cải thiện cache hit rate trong một số workloads, nhưng không trực tiếp giải quyết checkpoint bottleneck và làm tăng memory usage. Tuning riêng theo RAM/OS cache/workload.

### 35.4. Đừng chỉ nhìn buffers_clean

Đối chiếu buffers_clean, buffers_backend, buffers_checkpoint (nếu version có), maxwritten_clean, pg_stat_io và OS device metrics.

## 36. Checkpoint pacing và storage throughput

Checkpoint writes cần storage throughput ổn định. checkpoint_completion_target giúp phân phối writes trong interval, nhưng nếu storage không đủ throughput thì checkpoint vẫn có thể kéo dài hoặc gây cạnh tranh.

### 36.1. Sequential WAL vs data-page writes

WAL writes thường có pattern tuần tự hơn; checkpoint data writes phân tán trên nhiều relation files. Storage có thể có latency khác nhau cho hai loại workload.

### 36.2. Storage latency

Theo dõi read/write latency, IOPS, throughput và queue depth. Cloud volumes có thể có burst credits hoặc throughput caps.

### 36.3. I/O saturation

Nếu volume đã ở mức throughput cap, tăng max_wal_size hoặc completion_target không tạo thêm physical capacity. Cần nâng storage class/IOPS, phân tách workloads hoặc giảm write amplification.

### 36.4. Filesystem flush behavior

WAL sync correctness phụ thuộc OS/storage honoring flush requests. Không chọn wal_sync_method chỉ dựa vào một benchmark synthetic.

## 37. Cấu hình minh họa cho write-heavy workload

Đây là ví dụ định hướng để benchmark, không phải cấu hình mặc định cho mọi cluster:

~~~conf
# WAL/recovery
wal_level = replica
archive_mode = on
archive_command = '...'
max_wal_size = 8GB
min_wal_size = 2GB

# Checkpoint pacing
checkpoint_timeout = 15min
checkpoint_completion_target = 0.9
checkpoint_warning = 30s
log_checkpoints = on

# WAL buffers and compression
wal_buffers = -1
wal_compression = on

# Durability
fsync = on
full_page_writes = on
synchronous_commit = on
~~~

### 37.1. Vì sao chỉ là ví dụ?

Cần điều chỉnh max_wal_size theo WAL rate và volume headroom; checkpoint_timeout theo recovery budget; wal_compression theo CPU/FPI ratio; synchronous_commit theo durability/RPO.

### 37.2. Replication requirements

Nếu dùng logical decoding, wal_level phải là logical. Nếu dùng synchronous standby, cấu hình synchronous_standby_names và test failover behavior.

### 37.3. Archive command

Dòng archive_command ở trên là placeholder. Production phải dùng command/provider integration đã kiểm thử, có escaping/credentials đúng và có monitoring cho failures.

## 38. Kiểm tra settings đang có hiệu lực

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'wal_buffers',
    'wal_compression',
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'checkpoint_warning',
    'max_wal_size',
    'min_wal_size',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'synchronous_commit',
    'fsync',
    'full_page_writes',
    'log_checkpoints'
)
ORDER BY name;
~~~

### 38.1. source

source cho biết setting đến từ đâu, ví dụ configuration file, command line, database/user/session setting hoặc default.

### 38.2. pending_restart

Nếu true, setting cần restart nhưng chưa được áp dụng vào server process hiện tại.

### 38.3. ALTER SYSTEM

ALTER SYSTEM ghi setting vào postgresql.auto.conf. Trong môi trường production có configuration management, nên quản lý một nguồn cấu hình nhất quán để tránh drift.

### 38.4. Reload và restart

Một số settings chỉ cần reload; một số settings cần restart. Dùng pg_settings.context và pending_restart để kiểm tra, sau đó theo deployment procedure.

## 39. Monitoring checkpoint

### 39.1. Checkpoint stats

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

Dùng trên PostgreSQL 17+ khi view này có sẵn. Trên các major versions trước đó, đọc checkpoint counters trong pg_stat_bgwriter.

### 39.2. Checkpoint logs

Bật log_checkpoints và phân tích:
- Timed hay requested.
- Buffers written.
- Write duration.
- Sync duration.
- WAL distance.
- Checkpoint frequency.

### 39.3. Requested checkpoints

Requested checkpoints tăng nhanh có thể chỉ ra max_wal_size nhỏ so với WAL generation. Xem cả archive/slot retention và storage headroom trước khi tăng.

### 39.4. Checkpoint write/sync time

Write time cao thường gợi ý nhiều buffers hoặc storage throughput hạn chế. Sync time cao gợi ý flush/fsync latency hoặc nhiều files cần sync.

### 39.5. Tính delta counters

Lấy snapshots định kỳ. Counter reset sau restart/reset statistics; ghi nhận stats_reset để không tính rate sai.

## 40. Monitoring WAL generation

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

### 40.1. WAL bytes rate

Tính delta wal_bytes chia elapsed seconds.

### 40.2. WAL per transaction

Có thể so WAL bytes delta với xact_commit delta từ pg_stat_database để ước lượng WAL bytes/commit. Đây là aggregate rough metric; một transaction có thể ghi lượng dữ liệu rất khác transaction khác.

### 40.3. WAL per row

Với benchmark có workload kiểm soát, chia WAL bytes delta cho rows inserted/updated/deleted để so sánh các schema/index designs.

### 40.4. FPI rate

Theo dõi wal_fpi delta. Nếu tăng đột biến sau checkpoint, xem checkpoint frequency và page churn.

### 40.5. WAL writes/syncs

So sánh wal_write, wal_sync, write_time, sync_time nếu có. Tính rates và average times; không dùng average một mình nếu tail latency là vấn đề.

## 41. Monitoring replication và archive

### 41.1. Physical standby

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

### 41.2. Slot retention

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;
~~~

### 41.3. Archive

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

### 41.4. Tác động lên disk

Replication lag hoặc archive failures có thể khiến WAL không được recycle. Theo dõi volume free space song song với WAL metrics.

### 41.5. Không drop slot để xử lý triệu chứng

Xác định consumer owner, recovery options và resync cost trước khi drop. Một slot bị xóa có thể khiến standby/CDC consumer phải rebuild.

## 42. Monitoring I/O và wait events

### 42.1. pg_stat_io

Trên PostgreSQL 16+:

~~~sql
SELECT *
FROM pg_stat_io;
~~~

### 42.2. Activity waits

~~~sql
SELECT
    backend_type,
    wait_event_type,
    wait_event,
    count(*) AS processes
FROM pg_stat_activity
WHERE wait_event IS NOT NULL
GROUP BY backend_type, wait_event_type, wait_event
ORDER BY processes DESC;
~~~

### 42.3. OS metrics

Trên Linux, các công cụ phổ biến gồm:

~~~bash
iostat -xz 1
vmstat 1
pidstat -d 1
~~~

Chọn tool/flags theo platform và quyền. Trên managed services, dùng provider metrics.

### 42.4. Kết hợp nhiều lớp

Nếu PostgreSQL báo sync time cao và OS báo device latency cao, storage là nghi phạm mạnh. Nếu WAL bytes tăng nhưng storage latency bình thường, tìm workload hoặc write amplification.

## 43. Benchmark tuning

Không thể tuning tốt chỉ bằng cách đọc cấu hình hiện tại.

### 43.1. Baseline

Ghi lại:
- TPS và rows/sec.
- p50/p95/p99 commit latency.
- WAL bytes/sec và bytes/transaction.
- Checkpoint count/duration.
- WAL write/sync timing.
- Device IOPS/throughput/latency.
- CPU/memory.
- Replication lag.
- Archive backlog.
- Disk free bytes.

### 43.2. Workload đại diện

Dùng dataset, indexes, concurrency, transaction size và read/write mix tương tự production. Synthetic workload quá đơn giản có thể bỏ qua bottleneck thật.

### 43.3. Một thay đổi mỗi lần

Thay một nhóm settings, restart/reload đúng cách, chạy cùng test duration và so sánh metrics. Không đổi đồng thời checkpoint, WAL compression, synchronous_commit và storage tier rồi kết luận nguyên nhân.

### 43.4. Đo nhiều lần

Chạy đủ lâu để đi qua nhiều checkpoints, warm-up và workload peaks. Một test 30 giây có thể chưa quan sát được checkpoint cycle.

### 43.5. Kiểm tra correctness

Sau benchmark, xác nhận durability settings, replication health, backup/archive và data consistency. Throughput cao không có ý nghĩa nếu thay đổi làm yếu RPO ngoài yêu cầu.

## 44. Tuning theo thứ tự

Một trình tự thường dễ kiểm soát:

1. Xác minh storage latency/throughput và volume capacity.
2. Bật log_checkpoints và thu checkpoint/WAL baseline.
3. Đo wal_bytes/sec và checkpoint frequency.
4. Xác định requested checkpoints có quá nhiều không.
5. Điều chỉnh max_wal_size nếu storage headroom cho phép.
6. Đánh giá checkpoint_timeout theo recovery budget.
7. Đặt checkpoint_completion_target phù hợp để trải writes.
8. Đo FPI ratio và cân nhắc wal_compression.
9. Chỉ xem wal_buffers/WAL writer khi counters chỉ ra bottleneck.
10. Xem backend writes/background writer và pg_stat_io.
11. Đánh giá commit latency và synchronous replication.
12. Giảm write amplification ở schema/SQL/workload.
13. Benchmark và kiểm tra failover/PITR sau thay đổi.

## 45. Tuning checkpoint khi requested checkpoints nhiều

1. Xác nhận checkpoints_req hoặc num_requested tăng nhanh.
2. Đọc log_checkpoints để xác định WAL-triggered checkpoints.
3. Đo WAL bytes/sec và peak WAL generation.
4. Kiểm tra max_wal_size hiện tại.
5. Tính storage headroom và slot/archive retention.
6. Tăng max_wal_size theo một bước có kiểm soát.
7. Giữ checkpoint_completion_target ở mức phù hợp.
8. Chạy workload đủ lâu để quan sát nhiều cycles.
9. So sánh requested/timed checkpoints, latency và pg_wal size.
10. Kiểm tra recovery time và backup/replication behavior.

Không tăng max_wal_size nếu pg_wal đã phình do slot inactive hoặc archive failure mà chưa xử lý retention.

## 46. Tuning khi commit latency cao

1. Đo p95/p99 commit latency ở application.
2. Xem synchronous_commit và synchronous_standby_names.
3. Đo WAL sync time/counters.
4. Xem WALSync/WALWrite wait events.
5. Kiểm tra OS storage latency và fsync behavior.
6. Kiểm tra synchronous standby network/flush/apply lag.
7. Phân biệt local WAL bottleneck với remote acknowledgement bottleneck.
8. Kiểm tra group commit và transaction batching.
9. Benchmark storage hoặc synchronous policy trong môi trường an toàn.
10. Không đổi durability mode nếu chưa phê duyệt RPO trade-off.

## 47. Tuning khi WAL tăng bất thường

1. Đo wal_bytes/sec.
2. So sánh transaction rate và write workload.
3. Kiểm tra wal_fpi ratio.
4. Kiểm tra checkpoint frequency.
5. Kiểm tra indexes và update patterns.
6. Kiểm tra logical decoding/replication workload.
7. Kiểm tra full-page image compression.
8. Kiểm tra bulk loads, large updates và deletes.
9. Kiểm tra archive/slot retention để phân biệt generation với retained size.
10. Chọn tối ưu workload hoặc settings dựa trên nguồn tạo WAL.

## 48. Tuning khi backend writes cao

1. Xem backend write counters theo version.
2. Kiểm tra pg_stat_io và wait events.
3. Xem shared_buffers và memory pressure.
4. Kiểm tra bgwriter settings và maxwritten_clean.
5. Kiểm tra checkpoint frequency/duration.
6. Xem storage saturation.
7. Thử điều chỉnh bgwriter từng bước nếu evidence phù hợp.
8. Đo backend latency và background I/O sau thay đổi.

## 49. Các setting không nên tắt để tăng tốc

| Setting | Lý do cần giữ |
| --- | --- |
| fsync=on | Bảo vệ durability qua OS/power failures |
| full_page_writes=on | Giảm nguy cơ torn-page corruption |
| wal_level phù hợp | Cần cho recovery, archiving và replication |
| archive_mode khi cần PITR | Giữ WAL archive cho recovery objectives |
| synchronous_commit theo RPO | Quyết định khi nào commit được xác nhận |

### 49.1. fsync=off

Tắt fsync có thể dẫn đến mất dữ liệu hoặc database corruption sau crash. Không dùng trên production để giải quyết disk latency.

### 49.2. full_page_writes=off

Có thể làm giảm WAL volume nhưng làm yếu bảo vệ trước torn-page writes. Không tắt chỉ để giảm FPI.

### 49.3. synchronous_commit=off

Đây là trade-off khác: có thể mất các transactions vừa được xác nhận nếu OS/server crash trước khi WAL flush, nhưng không giống fsync=off về nguy cơ database corruption. Chỉ dùng cho workload có thể chấp nhận mất một số commits gần nhất.

### 49.4. wal_level=minimal

Không dùng nếu cần physical/logical replication hoặc WAL archiving theo kiến trúc production.

## 50. Checkpoint và crash recovery

Checkpoint frequency ảnh hưởng lượng WAL cần replay sau crash, nhưng recovery time còn phụ thuộc:
- WAL generation rate.
- Số lượng WAL segments kể từ checkpoint.
- Storage read throughput.
- Số data pages cần redo.
- Shared buffers/cache state.
- Hardware/VM startup.
- Recovery conflicts và replay behavior.

### 50.1. Không suy ra recovery time chỉ từ max_wal_size

max_wal_size là ngưỡng mềm và WAL có thể nhiều hơn do retention. Thực hiện crash-recovery drills trên môi trường đại diện.

### 50.2. Checkpoint không thay backup

Checkpoint giúp crash recovery của cluster hiện tại. Nó không cung cấp lịch sử bất biến để khôi phục dữ liệu bị xóa hoặc database bị phá hủy.

### 50.3. PITR

PITR cần base backup và WAL archive liên tục theo retention window. Đo thời gian restore/replay như một phần RTO validation.

## 51. Checkpoint và standby restartpoints

Physical standby cũng cần restartpoints để quản lý recovery state trong lúc replay WAL. Các checkpoint settings và WAL retention có thể ảnh hưởng restartpoint behavior.

### 51.1. Standby lag

Nếu standby replay chậm, primary slot có thể giữ WAL. Đừng chỉ tuning checkpoint trên primary mà bỏ qua standby disk/network/replay capacity.

### 51.2. Restartpoint stats

Một số checkpoint statistics views có các counters restartpoints. Diễn giải theo version.

### 51.3. Recovery conflicts

Hot standby queries có thể xung đột với replay. Điều chỉnh max_standby_streaming_delay/hot_standby_feedback có trade-off về query availability, replay lag và bloat upstream; không trộn với checkpoint tuning mà không đo riêng.

## 52. Tác động của archive_timeout

archive_timeout ép PostgreSQL switch sang WAL segment mới sau khoảng thời gian được cấu hình trong workload ít writes.

### 52.1. Khi có ích

Có thể giảm thời gian chờ trước khi segment được archive trong workload WAL thấp nhưng yêu cầu archive freshness.

### 52.2. Khi quá thấp

Có thể tạo nhiều archive files nhỏ/partially filled, tăng request/metadata/storage overhead. Chọn theo RPO, archive tooling và storage behavior.

### 52.3. Không thay synchronous replication

Archive freshness không đồng nghĩa standby đã nhận/replay WAL. Archive và replication phục vụ mục tiêu khác nhau.

## 53. Viết ít WAL hơn bằng thiết kế workload

### 53.1. Giảm số index

Mỗi index thêm write work. Đánh giá query benefit, uniqueness và constraint requirements trước khi bỏ.

### 53.2. HOT-friendly schema

Không index columns thay đổi liên tục nếu không cần; chọn fillfactor hợp lý để có free space cho HOT updates.

### 53.3. Batch changes

Gom operations phù hợp để giảm round trips/commit overhead, nhưng giữ transaction đủ ngắn để không tạo lock/rollback/vacuum issues.

### 53.4. Tránh rewrite toàn row

Chỉ update columns thay đổi và lọc các rows có giá trị thực sự khác.

### 53.5. Partition lifecycle

Drop/detach partitions theo retention thay vì delete từng row khi mô hình dữ liệu phù hợp.

### 53.6. Bulk import

Dùng COPY và staging strategy; kiểm tra WAL/replication/backup impact. Logged data vẫn cần WAL để bảo vệ durability.

## 54. Capacity planning cho WAL

Ước lượng WAL retained cần dựa trên rate và thời gian consumer có thể gián đoạn.

~~~text
WAL retention budget
  = normal WAL working set
  + peak WAL rate x outage duration
  + archive/replication recovery margin
  + operational headroom
~~~

### 54.1. Peak rate

Dùng peak/percentile WAL rate thay vì average thấp nhất. Bulk loads và batch jobs có thể tạo spikes.

### 54.2. Outage duration

Chọn thời gian đủ để phát hiện, sửa và khôi phục archive/standby/CDC consumer.

### 54.3. Disk safety

Đặt alerts ở mức warning/critical trước khi volume đầy. Nếu WAL volume riêng, alert theo volume đó.

### 54.4. Slot cap

max_slot_wal_keep_size có thể bảo vệ disk nhưng làm slot mất khả năng resume. Runbook phải có quy trình resync consumer.

## 55. Thay đổi settings an toàn

### 55.1. Kiểm tra context

pg_settings.context cho biết setting cần restart, reload hay có thể đổi ở session/user/database scope.

### 55.2. Kiểm tra pending_restart

~~~sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_wal_size',
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'wal_compression',
    'wal_buffers'
)
ORDER BY name;
~~~

### 55.3. Thay đổi bằng configuration management

Giữ một nguồn cấu hình chuẩn, review thay đổi và ghi lại lý do/owner. Tránh chỉnh trực tiếp nhiều nơi khiến config drift.

### 55.4. Restart/reload

Thực hiện reload/restart theo HA topology, rolling strategy và maintenance policy. Settings cần restart phải có kế hoạch failover/availability.

### 55.5. Rollback settings

Ghi lại giá trị trước thay đổi và cách revert. Sau khi revert, theo dõi thêm ít nhất một checkpoint cycle và workload peak.

## 56. Monitoring dashboard đề xuất

| Panel | Metrics | Mục đích |
| --- | --- | --- |
| WAL generation | wal_bytes/sec, wal_records/sec | Tốc độ tạo WAL |
| FPI ratio | wal_fpi, wal_records | Full-page-image overhead |
| Checkpoint frequency | timed/requested checkpoints | Nhận diện checkpoint pressure |
| Checkpoint duration | write/sync time | Storage/checkpoint latency |
| WAL directory | pg_wal bytes/files | Disk retention |
| Replication lag | sent/write/flush/replay LSN | Standby progress |
| Slot retention | restart_lsn, confirmed_flush_lsn | WAL giữ bởi consumers |
| Archive status | archived_count, failed_count | Archive health |
| Commit latency | p50/p95/p99 | Application durability path |
| Wait events | WAL/IO/checkpoint waits | Backend bottlenecks |
| Storage | IOPS, throughput, latency, queue | Device capacity |
| Backend writes | backend/checkpointer/bgwriter I/O | Dirty buffer behavior |

### 56.1. Alert examples

- Requested checkpoints vượt baseline trong nhiều intervals.
- Checkpoint sync time tăng đột biến.
- WAL bytes/sec vượt capacity budget.
- pg_wal volume free bytes dưới reserve.
- Archive failed_count tăng.
- Slot inactive giữ WAL quá lâu.
- Replication lag vượt RPO budget.
- p99 commit latency vượt SLA.
- Storage latency/queue depth vượt baseline.

### 56.2. Alert có context

Đưa vào alert: current value, baseline, delta/rate, affected volume, slot name, checkpoint count, database, thời điểm và dashboard link.

## 57. Troubleshooting: checkpoint xảy ra quá thường xuyên

Nguyên nhân có thể:
- max_wal_size thấp so với WAL generation.
- Workload bulk write.
- FPI volume cao.
- Logical WAL overhead.
- Archive/slot retention làm pg_wal tăng và pressure khó quan sát.
- Manual CHECKPOINT hoặc maintenance jobs.

Cách xử lý:
1. Xem checkpoint stats và logs.
2. Tính WAL bytes/sec.
3. Phân biệt timed với requested checkpoints.
4. Kiểm tra max_wal_size và checkpoint_timeout.
5. Kiểm tra pg_wal, slots và archive.
6. Tăng max_wal_size nếu storage/recovery budget cho phép.
7. Benchmark và đo checkpoint/commit latency.

## 58. Troubleshooting: pg_wal tăng đến gần đầy

1. Đo dung lượng pg_wal và filesystem free.
2. Kiểm tra pg_stat_archiver.
3. Kiểm tra pg_replication_slots và inactive consumers.
4. Kiểm tra standby/logical subscriber lag.
5. Kiểm tra wal_keep_size và max_slot_wal_keep_size.
6. Đo WAL generation rate.
7. Khắc phục archive/consumer trước khi drop slot.
8. Mở rộng volume nếu cần để có thời gian xử lý.
9. Không xóa WAL segment thủ công.
10. Xác minh segment recycle sau khi retention issue được giải quyết.

## 59. Troubleshooting: commit latency tăng

1. Đo p95/p99 commit latency.
2. Xem synchronous_commit.
3. Kiểm tra synchronous standby state.
4. Đọc WAL write/sync timing.
5. Kiểm tra wait events.
6. Đo storage flush latency.
7. Kiểm tra network latency tới standby.
8. Kiểm tra group commit/transaction batching.
9. Không đổi durability mode khi chưa đánh giá RPO.
10. Re-test với workload đại diện.

## 60. Troubleshooting: storage write latency tăng khi checkpoint

1. Đọc checkpoint logs và write/sync times.
2. Đối chiếu storage IOPS/throughput/queue depth.
3. Kiểm tra checkpoint_completion_target.
4. Kiểm tra max_wal_size và checkpoint_timeout.
5. Xem backend writes và background writer.
6. Kiểm tra concurrent bulk loads/index builds.
7. Tính headroom trước khi tăng WAL thresholds.
8. Benchmark checkpoint pacing.
9. Cân nhắc nâng storage throughput nếu device saturation là nguyên nhân.
10. Kiểm tra application latency sau thay đổi.

## 61. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Giảm max_wal_size để ngăn pg_wal tăng | Checkpoints dày hơn, không giải quyết slot/archive retention | Tìm nguyên nhân WAL được giữ |
| Tăng max_wal_size vô hạn | Volume có thể đầy, recovery/retention budget mất kiểm soát | Tính WAL rate và disk headroom |
| Tắt fsync | Nguy cơ mất dữ liệu/corruption sau crash | Giữ durability và sửa storage bottleneck |
| Tắt full_page_writes | Tăng nguy cơ torn-page damage | Giữ protection, xem FPI/compression |
| Đặt synchronous_commit=off cho toàn workload | Thay đổi RPO ngoài ý muốn | Chỉ áp dụng có chọn lọc cho dữ liệu chấp nhận mất |
| Nhầm checkpoint với commit | Tuning sai mục tiêu | Phân biệt WAL flush và data-page writes |
| Chỉ xem wal_bytes | Không biết WAL đang được giữ ở đâu | Theo dõi pg_wal, slots, archive |
| Chỉ xem pg_wal size | Không biết WAL generation rate | Dùng pg_stat_wal deltas |
| Tăng wal_buffers không đo | Không cải thiện storage bottleneck | Kiểm tra wal_buffers_full và sync latency |
| Tăng bgwriter không benchmark | Tăng background I/O contention | Theo dõi backend writes và pg_stat_io |
| Tuning nhiều setting cùng lúc | Không biết thay đổi nào tạo kết quả | Thay một nhóm mỗi lần |
| Dùng benchmark ngắn | Bỏ qua checkpoint cycles | Test qua nhiều cycles |
| Không đo p99 | Throughput tốt nhưng tail latency xấu | Đo percentile latency |
| Bỏ qua replication lag | WAL retention và RPO có thể vượt budget | Monitor standby/slots |
| Bỏ qua archive failure | pg_wal có thể tăng đến đầy disk | Alert archive errors |
| Dùng unlogged table cho dữ liệu critical | Mất dữ liệu sau crash và không replication như mong đợi | Chỉ dùng cho dữ liệu tái tạo được |
| Batch transaction quá lớn | Lock, rollback và WAL bursts | Benchmark batch size |
| Không ghi lại cấu hình cũ | Khó rollback | Version config và change log |

## 62. Bài tập thực hành PostgreSQL

Thực hiện trên lab/staging. Không tắt fsync/full_page_writes hoặc thay đổi durability settings của production để thử nghiệm.

1. **WAL:** mô tả write-ahead logging bằng sơ đồ.
2. **Commit:** giải thích commit flush khác checkpoint thế nào.
3. **Dirty buffers:** tạo workload UPDATE và quan sát checkpoint behavior.
4. **LSN:** đọc pg_current_wal_lsn().
5. **WAL delta:** tính bytes giữa hai LSN.
6. **WAL files:** đo dung lượng pg_wal bằng phương pháp được hỗ trợ.
7. **wal_level:** đọc wal_level hiện tại.
8. **Replication:** xác định wal_level cần cho physical replication.
9. **Logical:** xác định wal_level cần cho logical decoding.
10. **Checkpoint timeout:** đọc checkpoint_timeout.
11. **Max WAL:** đọc max_wal_size và min_wal_size.
12. **Completion target:** đọc checkpoint_completion_target.
13. **Logging:** bật log_checkpoints trong lab.
14. **Checkpoint warning:** cấu hình checkpoint_warning và đọc logs.
15. **Timed checkpoints:** lấy checkpoint statistics.
16. **Requested checkpoints:** so sánh timed/requested counters.
17. **Version:** so sánh checkpoint stats trên PostgreSQL 16 và 17+.
18. **WAL stats:** đọc pg_stat_wal.
19. **WAL rate:** tính wal_bytes/sec từ hai snapshots.
20. **FPI:** theo dõi wal_fpi.
21. **FPI ratio:** so sánh FPI với WAL records.
22. **Compression:** đọc wal_compression.
23. **WAL compression:** benchmark compression trong lab.
24. **wal_buffers:** đọc wal_buffers và shared_buffers.
25. **Buffer full:** theo dõi wal_buffers_full.
26. **WAL writer:** đọc wal_writer_delay.
27. **Flush after:** đọc wal_writer_flush_after.
28. **Background writer:** đọc pg_stat_bgwriter.
29. **pg_stat_io:** đọc I/O stats trên PostgreSQL 16+.
30. **Backend writes:** quan sát backend write counters theo version.
31. **Checkpoint pacing:** thử hai checkpoint_completion_target values trong lab.
32. **Checkpoint interval:** thử checkpoint_timeout khác nhau.
33. **Max WAL:** thay max_wal_size và quan sát requested checkpoints.
34. **Recovery:** đo crash recovery time trên lab snapshots.
35. **WAL retention:** tạo physical replication slot và theo dõi retained WAL.
36. **Logical slot:** tạo logical consumer lab và theo dõi restart_lsn.
37. **Archive:** đọc pg_stat_archiver.
38. **Archive failure:** mô phỏng archive failure và quan sát pg_wal growth.
39. **wal_keep_size:** đọc setting và giải thích semantics.
40. **Slot cap:** tìm hiểu max_slot_wal_keep_size và invalidation risk.
41. **Wait events:** quan sát WALWrite/WALSync nếu version hiển thị.
42. **Checkpoint waits:** quan sát I/O/checkpoint wait events.
43. **Storage:** chạy iostat hoặc provider metrics trong workload test.
44. **Commit latency:** đo p50/p95/p99 commit latency.
45. **synchronous_commit:** đọc mode hiện tại.
46. **Commit off:** benchmark synchronous_commit=off chỉ trong lab và đánh giá data-loss window.
47. **Local:** so sánh local với on.
48. **Remote write:** nghiên cứu remote_write semantics.
49. **Remote apply:** nghiên cứu remote_apply và visibility.
50. **Synchronous standby:** cấu hình synchronous_standby_names trong lab.
51. **Replication latency:** đo network/flush/apply latency.
52. **fsync:** xác nhận fsync=on và đọc documentation.
53. **Full page writes:** xác nhận full_page_writes=on.
54. **Sync method:** chạy pg_test_fsync trên host test.
55. **Commit delay:** đọc commit_delay/commit_siblings.
56. **Group commit:** tạo concurrent commit workload và đo throughput.
57. **Batch insert:** so sánh single-row và multi-row INSERT.
58. **COPY:** benchmark COPY so với INSERT.
59. **Batch size:** thử nhiều transaction batch sizes.
60. **WAL per row:** tính WAL bytes/inserted row trong controlled test.
61. **Index overhead:** benchmark insert với số lượng indexes khác nhau.
62. **HOT update:** tạo workload HOT-friendly và kiểm tra n_tup_hot_upd.
63. **Fillfactor:** benchmark hai fillfactor values trên table lab.
64. **No-op update:** đo WAL khi update cùng giá trị và khi bỏ qua unchanged rows.
65. **Partition retention:** so sánh DELETE hàng loạt với drop partition.
66. **Unlogged:** tạo unlogged staging table và quan sát crash/replication semantics trong lab.
67. **Bulk load:** đo WAL/checkpoint impact khi import dữ liệu lớn.
68. **Maintenance:** benchmark index build và maintenance_work_mem.
69. **Vacuum:** quan sát autovacuum trong write-heavy workload.
70. **WAL compression:** so sánh WAL bytes và CPU.
71. **Checkpoint alert:** tạo alert khi requested checkpoints tăng bất thường.
72. **WAL alert:** tạo alert theo WAL bytes/sec.
73. **Disk alert:** tạo alert khi pg_wal volume free space dưới reserve.
74. **Slot alert:** cảnh báo inactive slot giữ WAL.
75. **Archive alert:** cảnh báo archive failed_count tăng.
76. **Runbook:** viết quy trình xử lý checkpoint quá thường xuyên.
77. **Runbook:** viết quy trình xử lý commit latency cao.
78. **Runbook:** viết quy trình xử lý pg_wal gần đầy.
79. **Benchmark:** so sánh baseline và tuned configuration qua nhiều checkpoint cycles.
80. **Thiết kế tổng hợp:** xây kế hoạch tuning cho workload write-heavy với checkpoint/WAL capacity, durability, synchronous replication, SQL write amplification, monitoring, benchmark và rollback strategy.

## 63. Checklist tuning checkpoint, WAL và tải ghi

### Baseline

- [ ] Đo TPS, rows/sec và commit latency percentiles.
- [ ] Đo WAL bytes/sec và WAL bytes/transaction.
- [ ] Ghi checkpoint timed/requested counts.
- [ ] Ghi checkpoint write/sync duration.
- [ ] Đo FPI ratio.
- [ ] Đo replication lag và archive backlog.
- [ ] Đo storage IOPS, throughput, latency và queue.
- [ ] Ghi filesystem free space và WAL retention.

### Checkpoint/WAL

- [ ] checkpoint_timeout phù hợp recovery budget.
- [ ] max_wal_size phù hợp WAL rate và disk headroom.
- [ ] min_wal_size phù hợp WAL reuse.
- [ ] checkpoint_completion_target trải writes hợp lý.
- [ ] log_checkpoints bật trong giai đoạn điều tra.
- [ ] wal_compression được benchmark.
- [ ] wal_buffers giữ auto nếu chưa có evidence cần đổi.
- [ ] Slots/archive/standby retention được theo dõi.

### Durability

- [ ] fsync vẫn bật.
- [ ] full_page_writes vẫn bật.
- [ ] wal_level phù hợp replication/archiving.
- [ ] synchronous_commit phù hợp RPO.
- [ ] Synchronous standby policy được test.
- [ ] Storage flush semantics được xác minh.

### Write workload

- [ ] Indexes được review.
- [ ] HOT update opportunities được xem xét.
- [ ] Fillfactor được benchmark.
- [ ] No-op updates được loại bỏ khi phù hợp.
- [ ] Batch size được benchmark.
- [ ] COPY dùng cho bulk loads khi phù hợp.
- [ ] Partition retention được xem xét.
- [ ] Transaction duration không quá dài.

### Change control

- [ ] Một nhóm settings được đổi mỗi lần.
- [ ] Test kéo dài qua nhiều checkpoint cycles.
- [ ] p95/p99 latency được so sánh.
- [ ] WAL/disk/replication/backup health được kiểm tra.
- [ ] Giá trị cũ và rollback procedure được ghi lại.

## 64. Tổng kết

Checkpoint, WAL và tải ghi là ba phần liên kết trong write path PostgreSQL:

~~~text
APPLICATION WRITES
       |
       v
WAL RECORD GENERATION
       |
       v
WAL BUFFER / WAL FILE
       |
       +---- Commit durability / replication
       |
       v
DIRTY DATA PAGES
       |
       v
CHECKPOINT / BACKGROUND WRITER
       |
       v
DATA FILES
~~~

Những nguyên tắc quan trọng:

- **WAL flush và checkpoint là hai công việc khác nhau.** Commit có thể bền vững trước khi data pages được checkpoint.
- **Checkpoint có thể được kích hoạt bởi thời gian hoặc WAL volume.** Phân biệt timed và requested checkpoints trước khi điều chỉnh.
- **max_wal_size là ngưỡng mềm, không phải hard cap.** Replication slots, archive và WAL retention có thể làm pg_wal lớn hơn.
- **checkpoint_completion_target giúp trải checkpoint writes.** Nó không làm tăng physical storage throughput.
- **Full-page images bảo vệ khỏi torn-page writes.** Giữ full_page_writes bật; cân nhắc wal_compression nếu FPI chiếm nhiều WAL và CPU còn headroom.
- **wal_buffers và background writer chỉ nên tuning khi counters chỉ ra bottleneck.** Chúng không thay thế storage đủ nhanh.
- **synchronous_commit quyết định durability/acknowledgement.** Đánh giá RPO trước khi thay đổi, đặc biệt với off hoặc remote modes.
- **Không tắt fsync hoặc full_page_writes để tăng tốc production.** Hãy xử lý storage, write amplification và checkpoint pressure.
- **SQL/schema design ảnh hưởng WAL lớn.** Giảm indexes không cần thiết, tận dụng HOT updates, tránh no-op updates và chọn transaction batch hợp lý.
- **Benchmark phải kéo dài qua nhiều checkpoint cycles.** Đo throughput, p99 latency, WAL rate, checkpoint stats, replication và recovery behavior.

Tuning tốt không phải là làm WAL ít nhất hoặc checkpoint thưa nhất. Mục tiêu là duy trì durability theo RPO, giữ recovery trong budget, phân phối I/O ổn định, tránh WAL volume vượt capacity và phục vụ write workload với latency có thể dự đoán.

