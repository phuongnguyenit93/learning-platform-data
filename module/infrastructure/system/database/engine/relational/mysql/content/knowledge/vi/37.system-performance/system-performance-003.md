# Buffer pool hit/miss, dirty page và hoạt động flush

InnoDB dùng **buffer pool** làm vùng nhớ đệm các page dữ liệu và index được đọc từ tablespace. Khi truy vấn cần một page đã nằm trong buffer pool, engine có thể đọc trực tiếp từ RAM; nếu page chưa có, InnoDB phải nạp page từ tầng lưu trữ vào bộ nhớ. Khi transaction thay đổi page, page đó trở thành **dirty page** và cần được ghi xuống data file theo cơ chế flush.

Đánh giá buffer pool không chỉ là nhìn một tỷ lệ hit cao. DBA cần theo dõi đồng thời logical read, physical read, số dirty page, tốc độ flush, free buffer, wait khi cần page trống và tiến độ checkpoint. Bài học này thuộc phần **Hiệu năng hệ thống** của MySQL, tập trung vào cách đọc các chỉ số đó, hiểu LRU/flush list và điều chỉnh hoạt động page cleaner theo workload.

## 1. Buffer pool nằm ở đâu trong đường đi của truy vấn?

InnoDB lưu clustered index, secondary index và các page dữ liệu trong tablespace. Buffer pool giữ các bản page đang được sử dụng trong RAM để giảm truy cập storage.

```text
SQL statement
    |
    v
Optimizer chọn access path
    |
    v
InnoDB cần một page của index/dữ liệu
    |
    v
Page có trong buffer pool?
    |                         |
   Có                        Không
    |                         |
    v                         v
Đọc page trong RAM       Đọc page từ storage
    |                         |
    +------------+------------+
                 |
                 v
           Xử lý record
                 |
        UPDATE / INSERT / DELETE
                 |
                 v
           Page trở thành dirty
                 |
                 v
     Page cleaner ghi page xuống data file
```

Buffer pool không phải nơi lưu trữ bền vững duy nhất. Khi server dừng, page trong RAM không thay thế data file và redo log. InnoDB dùng write-ahead logging để bảo đảm thông tin redo cần thiết được ghi trước khi dirty page tương ứng được flush xuống vị trí cuối cùng trong data file.

## 2. Logical read, physical read, hit và miss

Hai bộ đếm cơ bản:

- `Innodb_buffer_pool_read_requests`: số yêu cầu đọc logical page từ buffer pool.
- `Innodb_buffer_pool_reads`: số lần InnoDB phải đọc page vào buffer pool vì page cần thiết chưa có sẵn trong pool.

Kiểm tra:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%';
```

Trong kết quả, `Innodb_buffer_pool_read_requests` thường lớn hơn `Innodb_buffer_pool_reads` rất nhiều khi working set được cache tốt. Tuy nhiên, đây là bộ đếm tích lũy; cần lấy chênh lệch trong một khoảng thời gian xác định thay vì so sánh số tuyệt đối sau nhiều ngày uptime.

### Ước lượng buffer pool hit ratio

Có thể ước lượng tỷ lệ logical read được phục vụ mà không cần đọc page mới từ storage:

\[
\text{Hit ratio} \approx
\left(1 - \frac{\Delta\text{physical reads}}
{\Delta\text{logical read requests}}\right) \times 100\%
\]

Ví dụ trong 5 phút:

- Logical read requests tăng 10.000.000.
- Physical reads tăng 50.000.

Khi đó:

\[
\left(1 - \frac{50.000}{10.000.000}\right) \times 100
= 99,5\%
\]

Đây là chỉ số tổng quan. Nó không có nghĩa 99,5% truy vấn chạy nhanh hoặc storage không phải nút thắt. Một truy vấn có thể đọc hàng triệu page dù phần lớn page đã cache; một số ít physical read trên đường truy vấn latency-sensitive vẫn có thể làm p99 tăng mạnh.

### Lấy delta thay vì dùng bộ đếm tích lũy

Chụp số liệu tại hai thời điểm cách nhau một khoảng đủ đại diện:

```sql
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads'
);
```

Ghi lại kết quả T1, đợi khoảng đo, rồi chạy lại ở T2. Tính delta cho từng biến. Nếu `delta read_requests` bằng 0, không tính hit ratio cho khoảng đó. Nếu server restart hoặc status counter reset giữa T1 và T2, phép tính delta không còn hợp lệ.

`Innodb_buffer_pool_reads` là số page InnoDB phải đọc vào buffer pool; nó không phải số câu SELECT bị miss và cũng không nhất thiết bằng số lần thiết bị vật lý phải truy cập platter/flash. OS cache, storage cache và read-ahead có thể ảnh hưởng đường đi I/O thực tế.

## 3. Những counter quan trọng của buffer pool

Lấy một nhóm status counter thường dùng:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_pages_data',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free',
    'Innodb_buffer_pool_read_ahead',
    'Innodb_buffer_pool_read_ahead_evicted',
    'Innodb_buffer_pool_pages_made_young',
    'Innodb_buffer_pool_pages_not_made_young'
);
```

| Counter | Cách diễn giải |
| --- | --- |
| `Innodb_buffer_pool_read_requests` | Logical read requests; tăng nhanh là bình thường khi workload đọc nhiều. |
| `Innodb_buffer_pool_reads` | Page phải đọc vào buffer pool do chưa có sẵn; xem delta và tương quan latency/I/O. |
| `Innodb_buffer_pool_pages_data` | Số page dữ liệu đang nằm trong buffer pool. |
| `Innodb_buffer_pool_pages_dirty` | Số page đã sửa và chưa flush xuống data file. |
| `Innodb_buffer_pool_pages_free` | Số page frame đang trống để có thể cấp phát. |
| `Innodb_buffer_pool_pages_total` | Tổng page frame của buffer pool. |
| `Innodb_buffer_pool_pages_flushed` | Số page đã được flush; dùng delta để tính tốc độ flush. |
| `Innodb_buffer_pool_wait_free` | Số lần InnoDB phải chờ page trống; nếu tăng liên tục có thể cho thấy áp lực cấp phát/flush. |
| `Innodb_buffer_pool_read_ahead` | Số page được đọc trước vào buffer pool. |
| `Innodb_buffer_pool_read_ahead_evicted` | Page đọc trước bị đẩy khỏi pool trước khi được truy cập; tăng cao có thể gợi ý read-ahead không hữu ích. |
| `Innodb_buffer_pool_pages_made_young` | Số page được đưa vào vùng young của LRU. |
| `Innodb_buffer_pool_pages_not_made_young` | Số page không được đưa vào vùng young theo chính sách LRU. |

Tên counter và mức độ chi tiết có thể thay đổi theo phiên bản. Trước khi viết dashboard, kiểm tra danh sách biến thực tế trên server.

## 4. LRU: page nào được giữ lại?

Buffer pool quản lý page bằng danh sách LRU (Least Recently Used) có cơ chế phân vùng old/young. Page được truy cập có thể được đưa vào vùng young nếu đáp ứng quy tắc promotion; page ít được dùng dần di chuyển về phía cuối danh sách và có thể bị loại bỏ khi cần chỗ.

Việc chia old/young giúp giảm hiện tượng một lần quét bảng lớn đẩy toàn bộ working set nóng ra khỏi buffer pool. Page vừa được đọc do scan có thể được đặt vào vùng old và chỉ được nâng lên young khi có dấu hiệu được truy cập lại phù hợp.

Một số khái niệm:

- **Young pages:** phần LRU được xem là nóng hơn, thường chứa page được truy cập gần đây và đủ điều kiện promotion.
- **Old pages:** phần LRU dùng để cách ly page mới đọc hoặc ít nóng, hạn chế scan pollution.
- **Page eviction:** loại page khỏi buffer pool để giải phóng frame. Nếu page là dirty, InnoDB cần flush trước khi tái sử dụng frame.
- **Read-ahead:** đọc trước các page mà InnoDB dự đoán truy vấn sắp cần, dựa trên mẫu truy cập tuần tự hoặc vùng index.

Không nên kết luận buffer pool quá nhỏ chỉ vì tỷ lệ young/old thay đổi. Hãy xem `read_ahead_evicted`, physical reads, wait_free và latency của workload cùng lúc.

### Theo dõi phân bố page theo schema/table

Sys schema có các view hỗ trợ xem page đang nằm trong buffer pool theo schema hoặc bảng, nếu có trong bản cài đặt:

```sql
SELECT *
FROM sys.innodb_buffer_stats_by_schema
ORDER BY allocated DESC;

SELECT *
FROM sys.innodb_buffer_stats_by_table
ORDER BY allocated DESC
LIMIT 20;
```

Các view này hữu ích để xác định schema hoặc bảng đang chiếm buffer pool. Chúng mô tả page hiện được cache tại thời điểm quan sát, không phải toàn bộ dung lượng bảng trên đĩa. Kiểm tra tên cột bằng `DESCRIBE` nếu sys schema khác phiên bản.

## 5. Dirty page là gì?

Khi InnoDB thay đổi nội dung page trong buffer pool, page được đánh dấu dirty. Dirty page chứa dữ liệu mới hơn bản page tương ứng trong data file. Nó phải được flush xuống storage trước khi InnoDB có thể tái sử dụng frame đó như một page sạch.

Các thao tác có thể tạo dirty page:

- `INSERT`: thêm record và thay đổi page/index liên quan.
- `UPDATE`: sửa record, có thể làm thay đổi nhiều page và index.
- `DELETE`: đánh dấu xóa record và cập nhật cấu trúc index.
- Một số hoạt động nội bộ của InnoDB: thay đổi metadata/page phục vụ quản lý storage.

Dirty page không đồng nghĩa transaction chưa commit. Một transaction đã commit vẫn có thể có page dirty chưa được flush; redo log cho phép InnoDB phục hồi các thay đổi nếu crash xảy ra trước khi page được ghi xuống data file.

Ngược lại, transaction chưa commit cũng có thể đã làm page trong buffer pool trở thành dirty. Khi crash recovery, redo có thể phát lại thay đổi cần thiết rồi undo transaction chưa commit. Vì vậy không thể suy ra trạng thái commit chỉ từ việc page đã được flush hay chưa.

### Tỷ lệ dirty page

Ước lượng tỷ lệ dirty page trên tổng page frame:

\[
\text{Dirty page ratio} =
\frac{\text{Innodb\_buffer\_pool\_pages\_dirty}}
{\text{Innodb\_buffer\_pool\_pages\_total}} \times 100\%
\]

Ví dụ có 8.000 dirty pages trên 100.000 page frame thì tỷ lệ là 8%. Đây là tỷ lệ tức thời, không phải tỷ lệ dirty page trung bình trong một giờ. Cần quan sát xu hướng và so sánh với ngưỡng cấu hình.

## 6. Vì sao InnoDB phải flush dirty page?

Flush dirty page có một số mục tiêu:

1. **Giải phóng frame:** khi cần page frame mới nhưng pool thiếu page sạch, InnoDB phải tìm và flush dirty page phù hợp.
2. **Tiến checkpoint:** checkpoint chỉ có thể tiến qua các thay đổi redo khi page cũ cần thiết đã được ghi xuống data file.
3. **Giữ redo log có chỗ:** nếu checkpoint tụt quá xa so với LSN hiện tại, vùng redo có thể bị chiếm dụng và gây áp lực ghi log.
4. **Giảm công việc khi shutdown/recovery:** flush nền đều đặn giúp giới hạn lượng dirty page cần xử lý, dù crash recovery vẫn dựa vào redo/undo.

InnoDB không chờ đến khi buffer pool đầy mới flush. Page cleaner chạy nền, phối hợp flush list và LRU list để duy trì lượng page sạch và tiến checkpoint.

## 7. Flush list, LRU flush và checkpoint

InnoDB có các mục tiêu flush khác nhau:

- **Flush list:** chứa dirty page được quản lý theo thứ tự liên quan đến LSN sửa đổi. Flush các page cũ nhất giúp tiến checkpoint.
- **LRU list:** khi cần frame trống, InnoDB tìm page ở vùng ít nóng. Nếu page được chọn là dirty, phải flush trước khi giải phóng frame.
- **Single-page flush:** một page riêng lẻ có thể được flush khi cần thiết; số lượng chờ và hoạt động liên quan có thể thấy trong InnoDB status.

Checkpoint là mốc redo mà các page cần thiết trước mốc đó đã được ghi xuống data file. Khi dirty page cũ được flush, checkpoint có thể tiến lên và giải phóng không gian redo log có thể tái sử dụng.

### Xem checkpoint và flush trong InnoDB status

```sql
SHOW ENGINE INNODB STATUS\G
```

Trong phần `BUFFER POOL AND MEMORY`, chú ý:

- `Buffer pool size`: tổng page frame.
- `Free buffers`: số frame đang trống.
- `Database pages`: số page dữ liệu/index trong pool.
- `Modified db pages`: số dirty page.
- `Pending reads`: số page read đang chờ.
- `Pending writes: LRU`, `flush list`, `single page`: hoạt động ghi đang chờ theo nhóm.
- `Pages made young` và `not young`: thông tin promotion của LRU.

Trong phần `LOG`, chú ý các mốc:

- `Log sequence number`: LSN hiện tại.
- `Log flushed up to`: vị trí redo đã flush.
- `Last checkpoint at`: LSN checkpoint gần nhất.
- `Pending log flushes` và `pending checkpoint writes`: công việc log/checkpoint đang chờ.

Chênh lệch giữa LSN hiện tại và checkpoint LSN phản ánh lượng redo chưa được checkpoint vượt qua. Đọc cùng dung lượng redo log, tốc độ ghi và tốc độ flush; không đánh giá chỉ bằng một snapshot.

## 8. Page cleaner và adaptive flushing

Page cleaner là các thread nền chịu trách nhiệm flush dirty page. InnoDB có thể điều chỉnh lượng page cần flush dựa trên mức dirty page, tốc độ tạo redo và khoảng cách checkpoint. Cơ chế này thường được gọi là **adaptive flushing**.

Một số biến cấu hình quan trọng:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'innodb_max_dirty_pages_pct',
    'innodb_max_dirty_pages_pct_lwm',
    'innodb_io_capacity',
    'innodb_io_capacity_max',
    'innodb_lru_scan_depth',
    'innodb_page_cleaners',
    'innodb_flush_neighbors',
    'innodb_redo_log_capacity'
);
```

| Biến | Vai trò |
| --- | --- |
| `innodb_max_dirty_pages_pct` | Ngưỡng tỷ lệ dirty page mục tiêu tối đa trước khi InnoDB tăng áp lực flush. |
| `innodb_max_dirty_pages_pct_lwm` | Low-water mark để adaptive flushing bắt đầu hoạt động mạnh hơn khi dirty page vượt ngưỡng thấp. |
| `innodb_io_capacity` | Ước lượng năng lực I/O nền mà InnoDB có thể dùng cho hoạt động background như flush. |
| `innodb_io_capacity_max` | Giới hạn cao hơn có thể dùng khi cần flush mạnh hơn. |
| `innodb_lru_scan_depth` | Số page được quét trong LRU mỗi vòng để tìm page có thể dùng/flush, theo cấu hình buffer pool instance. |
| `innodb_page_cleaners` | Số page cleaner thread trong các phiên bản có biến này. |
| `innodb_flush_neighbors` | Điều khiển việc flush các page lân cận khi flush một page; ý nghĩa giá trị phụ thuộc phiên bản. |
| `innodb_redo_log_capacity` | Dung lượng redo log mục tiêu ở các phiên bản hỗ trợ biến này. |

Không sao chép một bộ giá trị từ server khác. `innodb_io_capacity` cần phản ánh khả năng IOPS thực tế của storage và workload; đặt quá thấp có thể làm dirty page/checkpoint tích tụ, đặt quá cao có thể chiếm I/O của truy vấn foreground.

### Tại sao dirty page tăng liên tục?

Các nguyên nhân thường gặp:

- Workload ghi tạo dirty page nhanh hơn tốc độ page cleaner có thể flush.
- Storage có latency cao hoặc IOPS thấp.
- `innodb_io_capacity` được cấu hình thấp hơn năng lực thiết bị.
- Batch transaction quá lớn tạo burst ghi.
- Checkpoint bị tụt do redo generation rate cao.
- Hệ thống đồng thời chạy backup, sort, scan hoặc tác vụ I/O nặng.

Hãy đối chiếu tốc độ tạo redo, dirty page, flush rate, pending writes và latency storage để phân biệt nguyên nhân.

## 9. Đo tốc độ flush và áp lực I/O

Lấy counter trước và sau khoảng đo:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_data_reads',
    'Innodb_data_writes',
    'Innodb_data_fsyncs',
    'Innodb_os_log_written',
    'Innodb_log_waits'
);
```

Tốc độ flush trung bình:

\[
\text{Flush pages/sec} =
\frac{\Delta\text{Innodb\_buffer\_pool\_pages\_flushed}}
{\Delta t\ (seconds)}
\]

Tương tự, tính byte redo được tạo mỗi giây từ delta `Innodb_os_log_written` chia cho thời gian. So sánh redo generation rate với flush/checkpoint progress để xem hệ thống có đang tạo thay đổi nhanh hơn khả năng ghi bền vững hay không.

`Innodb_log_waits` tăng có thể cho thấy transaction phải chờ log buffer/redo log được xử lý; cần đọc cùng redo capacity, log write/flush và checkpoint. Không coi mọi lần tăng counter là sự cố nếu latency và throughput vẫn nằm trong SLA.

### Theo dõi file I/O trong Performance Schema

Có thể xem thống kê I/O theo file:

```sql
SELECT
    FILE_NAME,
    EVENT_NAME,
    COUNT_READ,
    ROUND(SUM_TIMER_READ / 1000000000000, 3) AS read_seconds,
    COUNT_WRITE,
    ROUND(SUM_TIMER_WRITE / 1000000000000, 3) AS write_seconds,
    COUNT_MISC
FROM performance_schema.file_summary_by_instance
WHERE FILE_NAME LIKE '%ibdata%'
   OR FILE_NAME LIKE '%.ibd'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 30;
```

Tên file và đường dẫn tùy cấu hình. Các timer là số tích lũy; lấy delta trong khoảng benchmark. Bảng này cần instrument file I/O được bật để có số liệu phù hợp.

## 10. Xem chi tiết buffer pool qua INFORMATION_SCHEMA

MySQL cung cấp `INFORMATION_SCHEMA.INNODB_BUFFER_POOL_STATS` để xem số liệu theo buffer pool instance:

```sql
SELECT
    POOL_ID,
    POOL_SIZE,
    FREE_BUFFERS,
    DATABASE_PAGES,
    OLD_DATABASE_PAGES,
    MODIFIED_DATABASE_PAGES,
    PENDING_READS,
    PENDING_FLUSH_LRU,
    PENDING_FLUSH_LIST,
    NUMBER_PAGES_READ,
    NUMBER_PAGES_WRITTEN,
    HIT_RATE
FROM information_schema.INNODB_BUFFER_POOL_STATS
ORDER BY POOL_ID;
```

`POOL_SIZE` là số page frame trong instance; `MODIFIED_DATABASE_PAGES` là số dirty page; `FREE_BUFFERS` là page frame trống. `HIT_RATE` là số liệu nội bộ tổng hợp theo cách tính của InnoDB; để phân tích theo một khoảng thời gian, vẫn nên dùng delta của global status counter và latency workload.

### Tránh quét INNODB_BUFFER_PAGE không cần thiết

`INFORMATION_SCHEMA.INNODB_BUFFER_PAGE` có thể liệt kê page đang nằm trong buffer pool, gồm schema, table, index và trạng thái page. Bảng này có thể rất lớn trên server có buffer pool nhiều GB và truy vấn nó có thể gây overhead đáng kể.

Chỉ dùng khi cần điều tra có mục tiêu, lọc sớm theo schema/table và chạy trong cửa sổ phù hợp. Để xem phân bố theo bảng thường ngày, ưu tiên các view `sys.innodb_buffer_stats_by_table` hoặc `sys.innodb_buffer_stats_by_schema`.

## 11. Buffer pool sizing và working set

Buffer pool quá nhỏ so với working set có thể làm physical read tăng, page nóng bị đẩy ra thường xuyên và truy vấn phải đọc lại từ storage. Tuy nhiên, tăng buffer pool không phải lúc nào cũng cải thiện hiệu năng.

Khi đánh giá kích thước, cần xét:

- Tổng RAM vật lý và giới hạn memory của container/VM.
- Bộ nhớ cho connection, sort/join buffers, Performance Schema, table cache và các thành phần khác.
- Kích thước working set thường xuyên truy cập, không chỉ tổng kích thước data file.
- Tỷ lệ đọc/ghi và mức độ tuần tự/ngẫu nhiên của truy vấn.
- Khả năng cache của OS và storage.
- Dung lượng dự phòng để tránh swap và memory pressure.

Kiểm tra:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'innodb_buffer_pool_size',
    'innodb_buffer_pool_instances',
    'innodb_buffer_pool_chunk_size'
);
```

Một số phiên bản MySQL đã thay đổi vai trò hoặc loại bỏ nhu cầu cấu hình thủ công `innodb_buffer_pool_instances`; hãy kiểm tra biến có tồn tại trên bản đang dùng. Thay đổi buffer pool size động có thể chịu ràng buộc chunk/instance và tiêu thụ RAM lớn trong quá trình resize. Lên kế hoạch theo phiên bản và quan sát memory sau thay đổi.

### Dấu hiệu buffer pool có thể thiếu

- Delta physical reads cao trong giờ tải bình thường.
- Working set nóng liên tục bị đọc lại.
- `Innodb_buffer_pool_wait_free` tăng cùng pending flush hoặc storage latency.
- p95/p99 truy vấn đọc tăng khi working set vượt pool.
- `sys.innodb_buffer_stats_by_table` cho thấy các bảng/index nóng lớn hơn đáng kể so với pool có thể giữ.

Không dùng riêng hit ratio thấp để quyết định tăng RAM. Trước hết xác định truy vấn có scan quá nhiều page, index có phù hợp, workload có đọc dữ liệu lạnh hay batch scan làm nhiễu cache.

## 12. Read-ahead và cache pollution

Read-ahead giúp nạp trước page khi InnoDB nhận thấy mẫu truy cập tuần tự hoặc vùng index có khả năng sắp được đọc. Nó hữu ích cho scan lớn và một số workload phân tích. Nhưng nếu dự đoán sai, page đọc trước có thể bị loại khỏi buffer pool trước khi được sử dụng.

Theo dõi:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_read_ahead',
    'Innodb_buffer_pool_read_ahead_evicted',
    'Innodb_buffer_pool_pages_made_young',
    'Innodb_buffer_pool_pages_not_made_young'
);
```

Nếu `read_ahead_evicted` tăng nhanh so với read-ahead pages, có thể có nhiều page được nạp nhưng không được truy cập kịp trước khi bị loại. Đây là tín hiệu cần xem query scan, working set và cấu hình read-ahead; không tự động tắt read-ahead khi chưa benchmark.

Một truy vấn báo cáo quét bảng lớn có thể đẩy page nóng của OLTP ra khỏi cache. Có thể giảm cache pollution bằng cách tối ưu điều kiện lọc, chạy báo cáo trên replica, chia batch hoặc điều chỉnh lịch chạy. Partitioning và covering index có thể giảm số page phải đọc nếu phù hợp với truy vấn.

## 13. Thí nghiệm đo hit ratio và dirty page

Tạo bảng thử nghiệm có index:

```sql
CREATE TABLE buffer_pool_lab (
    id BIGINT NOT NULL,
    category_id INT NOT NULL,
    payload VARCHAR(200) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_category_updated (category_id, updated_at)
) ENGINE = InnoDB;
```

Nạp dữ liệu đủ lớn để quan sát nhiều page, sau đó chạy:

```sql
ANALYZE TABLE buffer_pool_lab;

SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_read_requests',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free'
);
```

**Thử nghiệm A — đọc lặp working set nhỏ:**

```sql
SELECT id, payload
FROM buffer_pool_lab
WHERE id BETWEEN 1 AND 1000;
```

Chạy lặp nhiều lần. Lần đầu có thể phải nạp page; các lần sau thường tận dụng cache tốt hơn nếu working set vẫn nằm trong buffer pool và không bị workload khác đẩy ra.

**Thử nghiệm B — scan phạm vi lớn:**

```sql
SELECT COUNT(*), SUM(category_id)
FROM buffer_pool_lab;
```

Quan sát logical read, physical read, read-ahead và tỷ lệ page bị evict. Thay đổi kích thước bảng và lặp lại để xem ảnh hưởng khi working set vượt pool.

**Thử nghiệm C — tạo dirty page:**

```sql
UPDATE buffer_pool_lab
SET payload = CONCAT(payload, '-updated'),
    updated_at = CURRENT_TIMESTAMP
WHERE id BETWEEN 1 AND 5000;

COMMIT;
```

Ghi lại `Innodb_buffer_pool_pages_dirty` và `Innodb_buffer_pool_pages_flushed` trước/sau, sau đó quan sát khi page cleaner flush nền. Dirty page có thể vẫn còn sau commit; không mong đợi tất cả page biến mất ngay lập tức.

Kết thúc thí nghiệm, xóa bảng lab nếu không còn cần:

```sql
DROP TABLE buffer_pool_lab;
```

Không chạy phép thử scan lớn hoặc update nhiều dòng trên production chỉ để tạo số liệu. Dùng môi trường test có RAM, storage và dữ liệu đủ gần với workload cần đánh giá.

## 14. Cách đọc một tình huống vận hành

| Dấu hiệu | Khả năng cần kiểm tra | Hành động tiếp theo |
| --- | --- | --- |
| Hit ratio thấp và physical reads tăng | Working set vượt pool, scan lớn, index chưa phù hợp hoặc cache vừa lạnh. | Xem query digest, `EXPLAIN ANALYZE`, bảng/index chiếm pool và I/O latency. |
| Hit ratio cao nhưng query vẫn chậm | Quét nhiều logical page, CPU, lock wait, sort, network hoặc result set lớn. | Xem rows examined, stage/wait, lock và lượng dữ liệu trả về. |
| Dirty page tăng kéo dài | Tốc độ ghi vượt flush capacity hoặc checkpoint bị tụt. | Đo redo rate, flush rate, pending writes và storage IOPS/latency. |
| `Innodb_buffer_pool_wait_free` tăng | Thiếu page sạch khi cần cấp phát frame hoặc flush không theo kịp. | Đối chiếu free buffers, dirty pages, LRU flush, page cleaner và workload scan. |
| Pending flush list tăng | Page cần flush để tiến checkpoint đang tích tụ. | Xem LSN/checkpoint age, redo capacity và tốc độ I/O. |
| Read-ahead evicted tăng | Page đọc trước không được dùng kịp hoặc scan gây cache pollution. | Kiểm tra mẫu truy cập, read-ahead và query scan trước khi chỉnh cấu hình. |
| Flush mạnh làm latency ghi tăng | Page cleaner cạnh tranh I/O với foreground workload. | Đánh giá `innodb_io_capacity`, `innodb_io_capacity_max`, storage và batch size. |

Các dấu hiệu này là điểm bắt đầu điều tra, không phải kết luận nguyên nhân duy nhất. Hãy so sánh delta theo cùng khoảng thời gian và workload.

## 15. Quy trình điều chỉnh an toàn

1. Thu thập baseline trong thời gian có tải đại diện: read requests, physical reads, dirty pages, pages flushed, wait_free, redo written và latency storage.
2. Xác định vấn đề là cache miss, cache pollution, thiếu free page, checkpoint pressure hay storage saturation.
3. Kiểm tra query/index trước khi tăng buffer pool hoặc I/O capacity.
4. Chỉ thay đổi một nhóm biến liên quan trong môi trường test hoặc cửa sổ thay đổi được phê duyệt.
5. Đo lại throughput, p95/p99 latency, physical reads, dirty page trend, flush rate và lock wait.
6. Theo dõi đủ lâu để thấy chu kỳ peak, checkpoint và hoạt động batch; tránh kết luận từ vài giây đầu sau thay đổi.
7. Ghi lại giá trị cũ, giá trị mới, phiên bản MySQL, loại storage và điều kiện rollback.

Không đặt `innodb_max_dirty_pages_pct` quá thấp chỉ để ép dirty page luôn gần 0; điều đó có thể khiến flush liên tục và cạnh tranh I/O. Không đặt `innodb_io_capacity` theo con số IOPS quảng cáo mà chưa đo năng lực thực tế dưới workload đồng thời. Không tăng buffer pool đến mức hệ điều hành phải swap.

## 16. Lỗi diễn giải thường gặp

- **Hit ratio 99% nghĩa là database khỏe.** Tỷ lệ cao vẫn có thể đi cùng scan lớn, CPU cao, lock wait hoặc p99 latency xấu.
- **Mọi miss đều là truy cập thiết bị vật lý chậm.** InnoDB đọc page vào pool; OS/storage cache có thể phục vụ mà không chạm thiết bị theo cách đơn giản.
- **Dirty page nghĩa là transaction chưa commit.** Page có thể còn dirty sau khi transaction đã commit.
- **Commit đồng nghĩa page đã ghi xuống data file.** Commit durability chủ yếu dựa vào redo flush theo cấu hình; dirty data page có thể được flush sau.
- **Dirty page càng thấp càng tốt.** Flush quá mạnh có thể gây cạnh tranh I/O; cần cân bằng checkpoint, redo và workload.
- **Tăng buffer pool luôn cải thiện tốc độ.** Query scan kém, index sai hoặc lock contention không được giải quyết chỉ bằng thêm RAM.
- **`Innodb_buffer_pool_wait_free` tăng chắc chắn do pool quá nhỏ.** Flush chậm, scan lớn hoặc workload burst cũng có thể tạo áp lực page frame.
- **`INNODB_BUFFER_PAGE` luôn an toàn để quét.** Bảng có thể rất lớn và bản thân truy vấn quan sát gây overhead.
- **Counter tích lũy có thể so sánh trực tiếp giữa hai thời điểm.** Cần tính delta và xác nhận server không restart/reset counter giữa khoảng đo.

## 17. Bài tập tự kiểm tra

1. Phân biệt logical read request với physical page read.
2. Tính hit ratio nếu logical read tăng 20 triệu và physical reads tăng 100 nghìn trong cùng khoảng đo.
3. Vì sao phải dùng delta thay vì số counter tích lũy?
4. Dirty page được tạo ra khi nào? Một transaction đã commit có thể còn dirty page không?
5. Phân biệt flush list và LRU flush.
6. Checkpoint liên quan thế nào đến LSN và khả năng tái sử dụng redo log?
7. `Innodb_buffer_pool_wait_free` tăng liên tục gợi ý điều gì?
8. `innodb_io_capacity` và `innodb_io_capacity_max` ảnh hưởng hoạt động background như thế nào?
9. Vì sao read-ahead có thể làm tăng cache pollution?
10. Thiết kế một phép đo trước/sau để xác định buffer pool có phải nguyên nhân gây latency cao.

Đánh giá buffer pool đúng cách cần kết hợp **logical read và physical read → working set/LRU → dirty page → flush list và checkpoint → I/O capacity → latency thực tế**. Chỉ số hit ratio là một tín hiệu hữu ích, nhưng quyết định tối ưu phải dựa trên xu hướng và tác động lên workload.
