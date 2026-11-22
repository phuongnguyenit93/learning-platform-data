# Đo tốc độ ghi bền vững sau giai đoạn tăng tốc ban đầu

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt tốc độ ghi bùng nổ ban đầu (burst) với throughput ghi bền vững khi bộ đệm và cache không còn hấp thụ được toàn bộ tải.
- Mô tả đường ghi của cơ sở dữ liệu, từ transaction log/WAL đến việc ghi các data page và checkpoint.
- Giải thích vì sao số liệu trong vài giây đầu có thể cao hơn đáng kể so với tốc độ duy trì lâu dài.
- Thiết kế benchmark ghi kéo dài với dữ liệu, transaction, concurrency và cấu hình durability đại diện.
- Theo dõi độ trễ commit, log flush, checkpoint, dirty page, I/O storage, hàng đợi và replication lag để tìm giới hạn.
- So sánh các phương án batching, commit frequency, index và storage mà không đánh đổi tính bền vững ngoài ý muốn.

## 1. Vì sao phải đo tốc độ ghi bền vững?

Một bài kiểm tra ghi ngắn có thể cho kết quả rất cao vì nhiều tầng trong hệ thống tạm thời hấp thụ dữ liệu. Ứng dụng gửi lệnh nhanh, cơ sở dữ liệu ghi log vào bộ đệm, hệ điều hành và thiết bị lưu trữ có cache, còn các data page đã thay đổi có thể được ghi xuống file dữ liệu ở thời điểm sau.

Khi các bộ đệm còn chỗ, hệ thống có thể chấp nhận một đợt ghi lớn hơn khả năng lưu trữ duy trì trong thời gian dài. Sau đó, log cần được flush, dirty page cần được ghi, checkpoint phải tiến lên và cache ghi của thiết bị có thể cạn. Throughput lúc này giảm về mức mà toàn bộ đường ghi có thể duy trì.

Đo tốc độ ghi bền vững (sustained write throughput) nhằm trả lời câu hỏi: hệ thống có thể tiếp nhận, commit và lưu trữ khối lượng ghi trong thời gian dài ở mức nào, với độ trễ và mức lỗi chấp nhận được?

Trong module DATABASE_PERFORMANCE, kết quả đo cần phản ánh cả workload SQL, index, transaction, cơ chế log, checkpoint, I/O và cấu hình durability. Một con số rows/second trong vài giây đầu không đủ để dự báo năng lực ghi của hệ thống chạy liên tục.

## 2. Burst và steady state

**Burst** là giai đoạn đầu khi hệ thống có thể tận dụng bộ đệm trống, cache ghi còn dung lượng, hàng đợi chưa đầy và các tác vụ nền chưa phải xử lý lượng dữ liệu tích lũy lớn.

**Steady state** là trạng thái vận hành tương đối ổn định, khi tốc độ tạo dữ liệu ghi và tốc độ xử lý/đẩy dữ liệu qua các tầng lưu trữ đã cân bằng. Trong trạng thái này, throughput và độ trễ dao động quanh một dải thay vì tiếp tục tăng hoặc giảm có xu hướng kéo dài.

```text
Throughput
   ^
   |  burst cao
   |  ********
   |           \
   |            \____
   |                 \________________ steady state
   |
   +----------------------------------------------> thời gian
       warm-up       cache/buffer       duy trì dài hạn
```

Sơ đồ chỉ minh họa hình dạng có thể gặp. Một hệ thống được cấu hình tốt có thể đạt steady state gần với burst; một hệ thống bị giới hạn bởi cache hoặc checkpoint có thể giảm rõ rệt sau giai đoạn đầu.

Không có một thời lượng benchmark cố định đúng cho mọi hệ thống. Thời gian chạy phải đủ để đi qua nhiều chu kỳ checkpoint/flush và đủ dài để quan sát cache, hàng đợi, nhiệt độ thiết bị và các tác vụ nền đạt trạng thái đại diện.

## 3. Đường ghi của một transaction

Đường ghi tổng quát có thể mô tả như sau:

```text
Ứng dụng / driver
       | SQL và tham số
       v
Database execution engine
       | cập nhật buffer page
       +------------------------------+
       |                              |
       v                              v
Transaction log / WAL / redo       Dirty data page
       |                              |
       v                              v
Log buffer và log writer          Background writer / checkpoint
       |                              |
       v                              v
Flush log bền vững                Data file / storage
       |
       v
COMMIT được xác nhận
```

Chi tiết triển khai khác nhau giữa PostgreSQL, SQL Server, MySQL/InnoDB và các hệ quản trị khác, nhưng một nguyên tắc phổ biến là log ghi trước (write-ahead logging): thông tin cần để phục hồi thay đổi phải được ghi bền vững trước khi data page tương ứng được ghi xuống vị trí cuối cùng.

Vì vậy, một transaction có thể được xác nhận commit sau khi log bền vững, trong khi các data page đã thay đổi vẫn còn trong buffer pool và sẽ được ghi xuống file dữ liệu sau đó. Đây là cơ chế giúp commit không phải chờ ghi ngẫu nhiên mọi data page của transaction.

### Log flush và data page flush là hai việc khác nhau

- **Log flush:** ghi WAL/redo/transaction log đến vị trí cần thiết để bảo đảm khả năng phục hồi theo cấu hình durability.
- **Data page flush:** ghi các trang dữ liệu đã thay đổi từ buffer pool xuống data file.
- **Checkpoint:** ghi nhận một mốc phục hồi và bảo đảm các page/log cần thiết trước mốc đó đã được xử lý theo quy tắc của hệ quản trị.

Trong một workload ghi, log thường có mẫu ghi tuần tự hoặc gần tuần tự, còn data page có thể được ghi theo vị trí rải rác. Thiết bị có thể xử lý hai luồng I/O với hiệu năng rất khác nhau.

## 4. Vì sao tốc độ ban đầu có thể cao?

Có một số nguồn tạo ra kết quả burst:

1. **Buffer pool còn nhiều trang sạch:** hệ quản trị có thể thay đổi page trong RAM và trì hoãn việc ghi page xuống data file.
2. **Log buffer chưa đầy:** nhiều thay đổi có thể được gom trước khi log writer cần flush.
3. **Group commit:** nhiều transaction commit gần nhau có thể chia sẻ một lần flush log, giảm chi phí flush trên mỗi commit.
4. **Cache ghi của storage còn trống:** SSD có thể dùng vùng cache ghi nhanh, kể cả dynamic SLC cache, trước khi phải ghi vào vùng NAND TLC/QLC chậm hơn.
5. **Hàng đợi I/O chưa tích lũy:** trong vài giây đầu, số yêu cầu đang chờ có thể còn thấp.
6. **Dữ liệu và index còn nóng trong RAM:** một số thao tác đọc-modify-write không phải chờ đọc vật lý.
7. **Chưa có checkpoint hoặc tác vụ bảo trì lớn:** áp lực ghi nền có thể xuất hiện muộn hơn khi dữ liệu bẩn tích tụ.

Những yếu tố này không nhất thiết là lỗi. Bộ đệm và group commit là cơ chế tối ưu hợp lệ. Vấn đề là benchmark phải chạy đủ lâu để đo được khả năng hệ thống duy trì công việc sau khi các tầng hấp thụ ban đầu được sử dụng.

## 5. Durability quyết định ý nghĩa của số liệu commit

Trước khi đo, phải xác định chính xác khi nào ứng dụng được phép coi một transaction là thành công.

- Với **durable commit**, hệ quản trị chỉ xác nhận commit sau khi log cần thiết đã được flush theo cam kết của sản phẩm và cấu hình.
- Với **relaxed/asynchronous durability**, hệ quản trị có thể xác nhận sớm hơn khi log chưa được bảo đảm bền vững trên storage. Điều này có thể tăng throughput nhưng làm tăng nguy cơ mất các transaction vừa được xác nhận khi hệ thống gặp sự cố.

Không so sánh hai benchmark có chế độ durability khác nhau rồi kết luận hệ thống nhanh hơn. Ghi nhận rõ cấu hình commit, log flush, replication acknowledgement và cache storage.

### Ví dụ về cấu hình cần nhận biết

| Hệ quản trị | Cấu hình hoặc cơ chế liên quan | Ý nghĩa cần kiểm tra |
| --- | --- | --- |
| PostgreSQL | `synchronous_commit`, `fsync`, `full_page_writes` | Thời điểm commit chờ WAL flush và các bảo đảm phục hồi |
| MySQL InnoDB | `innodb_flush_log_at_trx_commit`, `sync_binlog` | Tần suất flush redo log và binary log theo cấu hình |
| SQL Server | Delayed durability và chế độ commit | Transaction có chờ log flush trước khi báo commit hay không |

Không tắt `fsync`, log flush hoặc durability chỉ để làm benchmark đẹp hơn nếu môi trường thực tế yêu cầu bảo vệ dữ liệu. Nếu muốn đo cấu hình relaxed durability, phải ghi rõ đó là một kịch bản khác với mức rủi ro khác.

## 6. Checkpoint và áp lực ghi dữ liệu

Trong hệ thống dùng WAL/redo, thay đổi dữ liệu thường tạo log trước rồi các data page được ghi xuống storage sau. Nếu tốc độ tạo dirty page cao hơn tốc độ background writer/checkpoint có thể xử lý trong thời gian dài, lượng dữ liệu bẩn và log chưa thể tái sử dụng sẽ tăng.

Checkpoint giúp giới hạn phần log cần phát lại khi khôi phục. Khi checkpoint đến gần hoặc hệ thống phải đẩy nhiều dirty page, hoạt động ghi có thể tăng đột biến và ảnh hưởng latency của transaction mới.

Các dấu hiệu cần theo dõi:

- Số lượng hoặc tỷ lệ dirty page tăng liên tục.
- Checkpoint thường xuyên, kéo dài hoặc ghi nhiều page trong thời gian ngắn.
- WAL/redo log tăng nhanh và không được tái sử dụng theo tốc độ dự kiến.
- Data file write latency hoặc queue depth tăng sau một khoảng chạy.
- Commit latency p95/p99 tăng trùng với hoạt động checkpoint hoặc log flush.
- Throughput giảm sau khi các buffer ban đầu đã đầy.

Checkpoint không phải một lỗi và không nên tắt để tránh thấy độ trễ. Cần cấu hình sao cho công việc ghi nền được dàn đều, không để checkpoint tạo ra các đợt I/O vượt khả năng storage.

## 7. Storage cache và giới hạn ghi dài hạn

SSD có thể ghi nhanh trong giai đoạn đầu nhờ cache nội bộ. Nhiều SSD consumer dùng một vùng NAND ở chế độ SLC để tăng tốc ghi; khi vùng này đầy, thiết bị phải ghi trực tiếp vào TLC/QLC hoặc chuyển dữ liệu trong nền, throughput có thể giảm.

Thiết bị enterprise có thể có cache, firmware và cơ chế bảo vệ mất điện khác. Controller RAID, SAN, cloud volume hoặc hypervisor cũng có thể thêm một tầng cache và hàng đợi.

Những yếu tố cần xem:

- Throughput ghi tuần tự và ngẫu nhiên sau khi cache ghi đã cạn.
- Latency p50/p95/p99 của lệnh flush và ghi đồng bộ.
- IOPS, băng thông, queue depth và thời gian chờ.
- Garbage collection, wear leveling và thermal throttling của SSD.
- Power-loss protection (PLP) đối với cache ghi của thiết bị/controller.
- Mức cạnh tranh giữa WAL, data file, temp file, backup và replication.

Không suy ra tốc độ ghi dài hạn từ thông số quảng cáo burst hoặc tốc độ ghi tuần tự trong một bài test rất ngắn. Hãy dùng cùng loại thiết bị, firmware, filesystem, mount option và cấu hình cache với môi trường dự kiến.

## 8. Định nghĩa workload ghi đại diện

Throughput chỉ có ý nghĩa khi biết hệ thống đang ghi loại dữ liệu nào. Một benchmark chỉ INSERT hàng nhỏ tuần tự có thể cho kết quả khác xa workload thực tế có nhiều index, foreign key, trigger, UPDATE ngẫu nhiên và transaction nhiều câu lệnh.

Trước khi chạy, xác định:

- Tỷ lệ INSERT, UPDATE, DELETE và UPSERT.
- Kích thước hàng trung bình và phân bố hàng rộng/hẹp.
- Số index, loại index, foreign key, trigger và constraint.
- Mẫu khóa: tuần tự, ngẫu nhiên, hot key hay phân tán.
- Tỷ lệ ghi log, audit, outbox hoặc bảng lịch sử.
- Số hàng trong mỗi transaction và số commit mỗi giây.
- Tỷ lệ đọc kèm ghi và truy vấn kiểm tra dữ liệu.
- Mức đồng thời và cách connection pool cấp kết nối.
- Yêu cầu replication, synchronous replica hoặc durability.

Ví dụ workload đơn giản có thể mô phỏng cập nhật tồn kho và ghi ledger trong cùng transaction:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501
  AND quantity >= 1;

INSERT INTO inventory_ledger
    (product_id, change_quantity, reason, created_at)
VALUES
    (501, -1, 'ORDER', CURRENT_TIMESTAMP);

COMMIT;
```

Đây là một transaction gồm cả cập nhật số dư tồn kho và ghi lịch sử. Benchmark phải kiểm tra số hàng UPDATE thực sự bị tác động; nếu không đủ tồn kho, không nên ghi ledger như thể thao tác đã thành công. Tập dữ liệu và quy tắc kiểm tra cần phản ánh nghiệp vụ thật.

## 9. Dữ liệu thử nghiệm phải đại diện cho trạng thái lâu dài

Benchmark trên một bảng rỗng hoặc dữ liệu rất nhỏ có thể bỏ qua các chi phí xuất hiện khi hệ thống lớn lên.

Chuẩn bị dữ liệu với:

- Tổng số hàng và kích thước bảng gần với quy mô cần dự báo.
- Số lượng và kích thước index tương tự production.
- Phân bố khóa và độ lệch (skew) gần thực tế.
- Mẫu cập nhật thay đổi giữa hàng mới và hàng cũ.
- Tỷ lệ hàng bị xóa, cập nhật lặp và dữ liệu đến muộn.
- Cơ chế vacuum, purge, archive hoặc cleanup giống vận hành.

Nếu benchmark luôn cập nhật cùng vài trăm hàng, các page đó có thể nằm nóng trong cache và tạo hotspot không giống workload có hàng triệu khóa. Ngược lại, tạo dữ liệu ngẫu nhiên hoàn toàn có thể làm cache locality xấu hơn thực tế.

Cần quyết định rõ mục tiêu: đo năng lực của một bảng mới, một bảng đã lớn, hay hệ thống hoạt động ổn định sau nhiều giờ/ngày ghi. Mỗi mục tiêu cần tập dữ liệu và thời gian chạy khác nhau.

## 10. Thiết kế thời lượng benchmark

Một phép đo dài hạn nên có các giai đoạn rõ ràng:

1. **Chuẩn bị:** kiểm tra schema, index, storage, durability, replication và dữ liệu nền.
2. **Warm-up:** cho ứng dụng, connection pool và database đạt trạng thái hoạt động đại diện; không lấy toàn bộ giai đoạn này làm kết quả steady state.
3. **Burst observation:** ghi riêng throughput ban đầu để hiểu khả năng hấp thụ tải ngắn hạn.
4. **Sustained load:** tiếp tục phát tải đủ lâu để đi qua nhiều lần log flush, checkpoint và chu kỳ cache/storage liên quan.
5. **Drain:** dừng phát tải và quan sát backlog, dirty page, log và hàng đợi được xử lý hết hoặc trở về mức ổn định.
6. **Validation:** kiểm tra tính đúng của dữ liệu, số transaction commit, số lỗi và độ bền theo cấu hình.

Không có một ngưỡng thời gian chung. Một workload cần chạy đủ lâu để biểu đồ throughput, commit latency, dirty page, log và storage không còn cho thấy xu hướng tích lũy liên tục. Với storage có cache ghi lớn, có thể cần khối lượng ghi vượt dung lượng cache đó; cần biết đặc tính thiết bị hoặc thử nghiệm đủ dài.

### Lấy mẫu theo cửa sổ thời gian

Không chỉ ghi một giá trị tổng sau khi benchmark kết thúc. Thu thập số liệu theo các cửa sổ cố định, ví dụ mỗi 10 hoặc 30 giây:

- Transactions committed và rows affected.
- Commit latency p50/p95/p99.
- Log bytes generated và log flush latency.
- Data write bytes, IOPS và storage latency.
- Dirty page, checkpoint progress và backlog.
- CPU, memory, queue depth và replication lag.

Biểu đồ theo thời gian giúp phát hiện throughput giảm sau cache exhaustion, checkpoint spike hoặc queue buildup. Một giá trị trung bình của cả bài chạy có thể che mất các giai đoạn này.

## 11. Open-loop và closed-loop load generation

**Closed-loop load** thường gửi request mới sau khi request trước hoàn tất. Khi hệ thống chậm, generator tự giảm tốc độ gửi. Điều này có thể che khuất mức tải mà hệ thống không còn đáp ứng được và tạo coordinated omission trong phép đo latency nếu không ghi nhận thời gian chờ bị bỏ qua.

**Open-loop load** phát request theo tốc độ mục tiêu độc lập tương đối với thời gian phản hồi. Khi hệ thống không theo kịp, hàng đợi tăng và độ trễ phản ánh rõ sự quá tải. Cần giới hạn queue và ghi nhận request bị từ chối hoặc bỏ lỡ.

Để đo capacity, có thể thử nhiều mức offered load tăng dần và tìm vùng mà throughput hoàn tất không còn tăng tương ứng, trong khi queue và p95/p99 bắt đầu tăng nhanh.

Không nên chỉ tăng concurrency vô hạn. Quá nhiều client có thể làm benchmark đo overhead của load generator hoặc connection pool thay vì giới hạn database. Theo dõi CPU, network và queue của cả máy phát tải lẫn máy chủ.

## 12. Chỉ số cốt lõi của sustained write

| Nhóm | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| Throughput | Transactions committed/s, rows committed/s, bytes/s | Khối lượng công việc hoàn tất, không chỉ được gửi |
| Latency | Commit p50/p95/p99, transaction duration | Thời gian người dùng chờ và độ ổn định |
| Log | WAL/redo/log bytes/s, log flushes/s, flush latency | Năng lực ghi log và xác nhận commit |
| Data I/O | Data pages written/s, bytes written, write IOPS | Khả năng đẩy dirty page xuống file dữ liệu |
| Buffer | Dirty pages, buffer pool pressure, page eviction | Mức tích lũy thay đổi chưa được ghi |
| Checkpoint | Số lần, thời gian, pages/bytes flushed, checkpoint age | Áp lực ghi nền và khả năng duy trì log |
| Storage | Write latency, queue depth, throughput, utilization | Giới hạn thiết bị hoặc volume |
| Concurrency | Active sessions, lock waits, deadlocks, connection waits | Mức tranh chấp và bão hòa |
| Replication | Send/redo/apply lag, log backlog | Khả năng bản sao theo kịp luồng ghi |
| Correctness | Commit count, rollback, duplicate, constraint errors | Tính đúng của kết quả benchmark |

Throughput cần tính trên transaction đã commit thành công theo yêu cầu durability. Không lấy số request được gửi hoặc số câu lệnh được enqueue làm số ghi hoàn tất.

## 13. Đọc dấu hiệu burst rồi giảm tốc

### Throughput giảm nhưng CPU còn thấp

Có thể storage log hoặc data file đã bão hòa, thiết bị bước ra khỏi cache ghi, hoặc transaction đang chờ flush đồng bộ. Kiểm tra log flush latency, storage queue và write latency.

### Commit latency tăng đồng thời log flush latency tăng

Đường log có thể là nút thắt. Kiểm tra vị trí log, thiết bị chứa log, độ trễ flush, group commit, cấu hình durability và cạnh tranh với các workload khác.

### Dirty page tăng liên tục rồi xuất hiện checkpoint spike

Data page writer/checkpoint có thể không theo kịp tốc độ tạo dirty page. Kiểm tra cấu hình checkpoint, số page được ghi, write bandwidth và thời gian checkpoint.

### Throughput giảm khi tăng concurrency nhưng I/O chưa bão hòa

Có thể xảy ra lock contention, latch contention, hotspot trên index/page, CPU saturation hoặc connection scheduling. Xem wait events, deadlock, lock duration, index design và phân bố khóa.

### Replication lag tăng dần

Primary có thể ghi nhanh hơn replica có thể nhận hoặc apply log. Nếu yêu cầu xác nhận đồng bộ, replica lag hoặc network latency cũng có thể tác động commit. Đo cả primary và replica, không chỉ throughput tại primary.

## 14. Benchmark với transaction size và batch size

Batch size và commit frequency tác động mạnh đến write path.

- Transaction rất nhỏ tạo nhiều commit và nhiều lần cần flush log; group commit có thể giảm chi phí nhưng vẫn có overhead.
- Transaction lớn amortize commit overhead trên nhiều hàng, nhưng giữ khóa lâu, tăng lượng log cho một transaction và làm rollback đắt hơn.
- Batch lớn có thể tăng memory usage, lock duration, transaction log growth và replication lag.
- Batch quá nhỏ tăng round trip và overhead parse/execute.

Hãy thử một dải batch size có căn cứ theo kích thước hàng và workload, chẳng hạn 100, 500, 1.000 hoặc 5.000 hàng, rồi đo. Những con số này chỉ là điểm bắt đầu; không phải khuyến nghị chung.

Giữ cùng tổng số hàng, schema, index, durability và mức đồng thời khi so sánh. Đo cả throughput, commit latency, lock wait, log bytes, storage queue và thời gian drain sau khi ngừng phát tải.

## 15. Chỉ mục và write amplification

Mỗi INSERT thường phải thêm mục vào các index liên quan. UPDATE có thể phải sửa index nếu cột khóa thay đổi hoặc index chứa cột được cập nhật. DELETE cần đánh dấu/xóa mục index theo cơ chế của engine. Vì vậy, nhiều index có thể làm tăng lượng dữ liệu ghi so với payload nghiệp vụ.

**Write amplification** là tỷ lệ dữ liệu vật lý phải ghi so với lượng dữ liệu logic ứng dụng yêu cầu. Một hàng 200 byte có thể tạo nhiều log record, cập nhật nhiều index page, page split, checkpoint write và replication bytes.

Khi đo sustained write, ghi nhận:

- Số lượng index và kích thước của chúng.
- Tỷ lệ log bytes trên bytes dữ liệu logic.
- Số page split hoặc index maintenance nếu hệ quản trị cung cấp.
- Mức cập nhật các cột được index.
- Tác động của fill factor, clustered key và khóa ngẫu nhiên.

Không xóa index cần thiết chỉ để tăng benchmark. Một hệ thống production cần cả hiệu năng đọc và ghi; chỉ giữ index hỗ trợ workload thực tế và cân bằng tổng chi phí.

## 16. Các hệ quản trị: nơi quan sát write path

### PostgreSQL

Những nguồn quan sát thường dùng:

- `pg_stat_wal` để xem lượng WAL được tạo và các số liệu WAL theo phiên bản.
- `pg_stat_bgwriter` và các view thống kê checkpoint tương ứng phiên bản để theo dõi background writer/checkpoint.
- `pg_stat_io` trên các phiên bản hỗ trợ để phân tích I/O theo backend/object/context.
- `pg_stat_database` và `pg_stat_statements` để liên hệ hoạt động với database/query.
- Log checkpoint và `EXPLAIN (ANALYZE, BUFFERS)` cho truy vấn đại diện.

Ví dụ xem thống kê WAL trên phiên bản có `pg_stat_wal`:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

Đây là bộ đếm tích lũy; hãy lấy chênh lệch theo cửa sổ thời gian và kiểm tra tên cột theo phiên bản. Để xem I/O của truy vấn, `EXPLAIN (ANALYZE, BUFFERS)` hữu ích nhưng không thay thế quan sát I/O storage ở cấp hệ điều hành.

### MySQL InnoDB

Các nguồn quan sát gồm:

- `SHOW ENGINE INNODB STATUS` để xem log sequence, checkpoint, buffer pool và trạng thái transaction.
- Performance Schema và các bảng `INNODB_METRICS` phù hợp phiên bản để xem redo, buffer pool, flush và I/O.
- `SHOW GLOBAL STATUS` để theo dõi counters; cần lấy chênh lệch theo thời gian.
- Thống kê file I/O trong Performance Schema để so sánh redo log, data file và binary log.

Ví dụ lấy trạng thái InnoDB:

```sql
SHOW ENGINE INNODB STATUS\G
```

Đọc các phần LOG, BUFFER POOL AND MEMORY, FILE I/O và TRANSACTIONS. Tên và độ chi tiết metric có thể thay đổi theo phiên bản MySQL.

### SQL Server

Các nguồn quan sát thường dùng:

- `sys.dm_io_virtual_file_stats` để xem read/write bytes, số lần I/O và stall theo database file.
- `sys.dm_os_wait_stats` để xem wait liên quan đến log flush, data I/O và latch.
- Performance counters như Log Bytes Flushed/sec, Log Flushes/sec, Log Flush Wait Time và Checkpoint pages/sec.
- `sys.dm_db_log_stats` và các DMV về log để xem trạng thái transaction log theo phiên bản.
- Query Store và actual execution plan để tìm statement tạo nhiều log hoặc ghi nhiều hàng.

Ví dụ đọc thống kê I/O file:

```sql
SELECT
    DB_NAME(vfs.database_id) AS database_name,
    mf.type_desc,
    mf.name AS logical_file_name,
    vfs.num_of_writes,
    vfs.num_of_bytes_written,
    vfs.io_stall_write_ms
FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS vfs
JOIN sys.master_files AS mf
  ON mf.database_id = vfs.database_id
 AND mf.file_id = vfs.file_id;
```

Các giá trị DMV thường là tích lũy từ lúc khởi động hoặc từ thời điểm reset phù hợp. Lấy snapshot hai thời điểm để tính tốc độ và latency trung bình; không dùng một snapshot làm tốc độ hiện tại.

## 17. Kiểm tra độ bền và tính đúng của benchmark

Benchmark ghi phải xác minh dữ liệu, không chỉ đạt một con số throughput.

Kiểm tra:

- Số transaction được gửi, commit, rollback và timeout.
- Số hàng được insert/update/delete thực tế.
- Khóa duy nhất, foreign key, check constraint và trigger có được thực thi như production không.
- Không có mất dữ liệu hoặc trùng lặp do retry.
- Dữ liệu đã commit còn tồn tại sau restart kiểm thử theo quy trình phù hợp khi cần xác nhận durability.
- Replica đã apply đến vị trí log tương ứng nếu workload yêu cầu replication.
- Không có backlog lớn còn tồn tại sau khi dừng phát tải.

Không cố tình tắt durability rồi dùng số liệu đó để dự báo hệ thống production có durability. Nếu cần thử chế độ relaxed durability để hiểu giới hạn, ghi riêng cấu hình và không trộn với kết quả durable commit.

## 18. Quy trình benchmark sustained write

1. **Chốt mục tiêu.** Xác định cần đo transaction/s, rows/s hay bytes/s, với mức durability và latency mục tiêu nào.
2. **Ghi cấu hình.** Lưu phiên bản database, schema, index, isolation, commit mode, checkpoint, log path, storage và replication.
3. **Tạo dữ liệu đại diện.** Dùng số hàng, phân bố khóa, độ rộng hàng và index gần workload dự kiến.
4. **Kiểm tra load generator.** Đảm bảo client, network, connection pool và CPU máy phát tải không phải nút thắt.
5. **Chọn mô hình tải.** Dùng open-loop hoặc closed-loop có chủ đích; ghi offered load và completed throughput.
6. **Warm-up có kiểm soát.** Tách kết quả warm-up khỏi steady-state measurement.
7. **Chạy đủ lâu.** Đi qua nhiều chu kỳ checkpoint/flush và khoảng thời gian cần thiết để cache/storage đạt trạng thái đại diện.
8. **Lấy metric theo cửa sổ.** Ghi throughput, commit latency, WAL/redo, dirty page, checkpoint, storage queue, CPU và replication lag.
9. **Drain và kiểm tra.** Dừng tải, quan sát backlog được xử lý, kiểm tra số transaction và tính đúng dữ liệu.
10. **Lặp lại có kiểm soát.** Chạy lại để xác định độ biến thiên, tránh so sánh hai bài test bị ảnh hưởng bởi tác vụ nền khác nhau.
11. **So sánh cấu hình.** Thay một yếu tố mỗi lần như batch size, index, storage hoặc commit mode để biết nguyên nhân thay đổi.
12. **Báo cáo giới hạn.** Ghi rõ workload, thời lượng, cấu hình durability, phần trăm burst và steady state, p95/p99 cùng các nút thắt.

## 19. Ví dụ đọc một kết quả benchmark

Giả sử một bài test ghi có kết quả theo từng phút:

| Giai đoạn | Transactions committed/s | Commit p95 | WAL/log write | Storage write latency |
| --- | ---: | ---: | ---: | ---: |
| Phút 1 | 18.000 | 8 ms | 140 MB/s | 1,2 ms |
| Phút 2 | 15.000 | 11 ms | 125 MB/s | 1,8 ms |
| Phút 5 | 9.500 | 35 ms | 105 MB/s | 7 ms |
| Phút 10 | 8.800 | 42 ms | 98 MB/s | 8 ms |
| Phút 20 | 8.900 | 40 ms | 100 MB/s | 8 ms |

Các số liệu chỉ minh họa. Throughput phút đầu cao nhưng giảm dần; từ phút 10 đến 20, throughput và latency gần ổn định. Mức khoảng 8.800–8.900 transaction/s có thể là steady-state của cấu hình đó, trong khi 18.000/s chỉ là burst.

Để tìm nguyên nhân, đối chiếu:

- Storage write latency có tăng cùng thời điểm throughput giảm không?
- Log flush latency hay data file write latency tăng?
- Dirty page hoặc checkpoint backlog có tích lũy trước phút 5 không?
- Có sự kiện cache ghi của SSD cạn hoặc thiết bị bị thermal throttling không?
- CPU có còn dư hay đã bão hòa?
- Lock wait, latch wait hoặc connection queue có tăng không?
- Replication lag có tăng cùng log generation không?

Không kết luận storage là nguyên nhân chỉ từ một cột latency. Cần phân biệt file log và data file, loại I/O, queue depth và các wait của database.

## 20. Những sai lầm thường gặp

- **Chạy benchmark quá ngắn.** Kết quả chủ yếu phản ánh buffer/cache ban đầu và bỏ qua checkpoint hoặc cache exhaustion.
- **Đếm request gửi thay vì transaction commit.** Request có thể còn trong queue, thất bại hoặc chưa được xác nhận bền vững.
- **So sánh cấu hình durability khác nhau.** Throughput cao hơn có thể đến từ việc giảm cam kết bảo vệ dữ liệu.
- **Chỉ đo INSERT hàng nhỏ.** Không phản ánh UPDATE ngẫu nhiên, index maintenance, FK, trigger hoặc transaction thực tế.
- **Dùng tập dữ liệu quá nhỏ.** Cache nóng và index nhỏ tạo locality không giống hệ thống lâu dài.
- **Bỏ qua checkpoint và dirty page.** Log flush tốt không có nghĩa data page writer cũng theo kịp.
- **Chỉ xem throughput trung bình.** Burst cao có thể che p95/p99 tăng và throughput giảm theo thời gian.
- **Bỏ qua replication.** Primary có thể ghi nhanh nhưng replica không theo kịp.
- **Tăng batch vô hạn.** Transaction lớn làm lock duration, log burst và rollback cost tăng.
- **Đổ lỗi cho SSD mà không xem wait.** CPU, lock, latch, connection pool hoặc log configuration cũng có thể là nút thắt.
- **Chạy nhiều benchmark đồng thời.** Các bài test cạnh tranh cùng storage và làm kết quả không thể so sánh.
- **Không kiểm tra dữ liệu sau test.** Throughput cao không có ý nghĩa nếu số hàng hoặc kết quả nghiệp vụ sai.

## 21. Danh sách kiểm tra trước khi công bố năng lực ghi

- [ ] Workload có tỷ lệ INSERT/UPDATE/DELETE, row size và index đại diện.
- [ ] Durability và commit acknowledgement giống cấu hình mục tiêu.
- [ ] Benchmark chạy đủ lâu để quan sát nhiều chu kỳ flush/checkpoint.
- [ ] Đã tách warm-up, burst, sustained load và drain.
- [ ] Throughput tính theo transaction/row đã commit thành công.
- [ ] Đã đo commit p50/p95/p99 và transaction duration.
- [ ] Đã theo dõi WAL/redo/log generation và flush latency.
- [ ] Đã theo dõi dirty page, checkpoint và data file write.
- [ ] Đã theo dõi storage latency, queue depth, IOPS và throughput.
- [ ] Đã kiểm tra CPU, memory, lock/latch contention và connection pool.
- [ ] Đã kiểm tra replication lag và backlog sau khi dừng tải.
- [ ] Đã xác minh dữ liệu, số transaction và ràng buộc sau benchmark.
- [ ] Đã chạy lặp lại và ghi rõ biến động giữa các lần thử.
- [ ] Báo cáo nêu rõ burst throughput và sustained throughput riêng biệt.

## Kết luận

Tốc độ ghi trong những giây đầu có thể được nâng đỡ bởi buffer pool, log buffer, group commit và cache ghi của storage. Khi dirty page, checkpoint, log flush và giới hạn thiết bị trở thành yếu tố chi phối, throughput có thể giảm về mức duy trì lâu dài. Vì vậy, hãy đo trên workload và dữ liệu đại diện, giữ nguyên yêu cầu durability, chạy đủ lâu qua các chu kỳ ghi nền, lấy số liệu theo thời gian và tính throughput từ transaction đã commit. Phân tích đồng thời commit latency, WAL/redo, checkpoint, data I/O, queue, contention và replication mới giúp xác định năng lực ghi bền vững và nút thắt thực sự.
