# Buffer pool, working set và đo nhu cầu bộ nhớ thực tế

InnoDB dùng buffer pool để giữ các page dữ liệu và index thường được truy cập trong RAM. Nếu tập page nóng (working set) phù hợp với buffer pool, nhiều lần đọc có thể được phục vụ từ bộ nhớ và giảm I/O lưu trữ. Nếu buffer pool nhỏ hơn nhu cầu thực tế, page bị đẩy ra rồi phải đọc lại; nếu cấp quá nhiều RAM cho buffer pool, MySQL có thể thiếu bộ nhớ cho connection, temporary table, Performance Schema, hệ điều hành và các tiến trình khác.

Vì vậy, sizing buffer pool không đơn giản là lấy một tỷ lệ cố định của RAM. Cần đo working set trong workload đại diện, quan sát hit/miss, dirty page, read-ahead và tốc độ I/O, sau đó lập ngân sách cho toàn bộ tiến trình `mysqld` cùng hệ điều hành. Mục tiêu là đủ RAM cho page nóng mà vẫn giữ headroom khi tải tăng, DDL chạy hoặc nhiều session hoạt động đồng thời.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích buffer pool lưu gì và working set khác tổng kích thước database như thế nào.
- Đo logical read, physical read, buffer pool hit ratio và xu hướng eviction.
- Đọc free page, dirty page, read-ahead và hoạt động flush để tìm áp lực bộ nhớ/I/O.
- Ước lượng working set từ kích thước bảng/index và workload thực tế.
- Lập ngân sách RAM cho buffer pool, connection, sort/join buffers, TempTable, Performance Schema và hệ điều hành.
- Thay đổi `innodb_buffer_pool_size` có kiểm soát và xác minh hiệu quả sau resize.
- Làm ấm cache sau restart bằng buffer pool dump/load và nhận biết giới hạn của cơ chế này.

Các ví dụ giả định MySQL 8.0 trở lên, InnoDB và page size mặc định 16 KiB. Một số biến, giới hạn online resize và cách hiển thị thống kê thay đổi theo phiên bản; kiểm tra giá trị thực tế trên instance trước khi áp dụng.

## 1. Buffer pool lưu gì?

Buffer pool là vùng bộ nhớ lớn nhất của nhiều MySQL instance chuyên dùng InnoDB. Nó cache page từ tablespace, chủ yếu gồm:

- **Index page:** page của clustered index và secondary index.
- **Data page:** với InnoDB, dữ liệu hàng được lưu trong leaf page của clustered index; đọc một hàng thường đồng nghĩa truy cập page index chứa hàng đó.
- **Undo-related page và các page nội bộ:** một số page phục vụ cấu trúc lưu trữ và giao dịch cũng được cache trong buffer pool.
- **Page mới đọc hoặc được tạo:** page được nạp từ tablespace hoặc được thay đổi trong bộ nhớ trước khi flush xuống đĩa.

Buffer pool không phải toàn bộ RAM mà `mysqld` sử dụng. Redo log buffer, connection/thread structures, sort/join/read buffers, TempTable, Performance Schema, data dictionary, table cache và nhiều cấu trúc khác nằm ngoài vùng page frame của buffer pool.

Kiểm tra kích thước cấu hình và page size:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'innodb_page_size';
SHOW VARIABLES LIKE 'innodb_buffer_pool_instances';
SHOW VARIABLES LIKE 'innodb_buffer_pool_chunk_size';
```

Với page size 16 KiB, buffer pool 16 GiB có khoảng một triệu page frame trước khi tính metadata và cấu trúc quản lý. Đây chỉ là phép quy đổi dung lượng; không có nghĩa mọi page đều chứa dữ liệu ứng dụng hoặc được sử dụng cùng lúc.

## 2. Working set khác tổng kích thước database

**Working set** là tập page mà workload thực sự truy cập thường xuyên trong một khoảng thời gian. Nó phụ thuộc vào truy vấn, phân phối dữ liệu, thời điểm trong ngày, cache ở ứng dụng và các tác vụ nền.

Ví dụ, database có tổng data và index 2 TiB nhưng hệ thống bán hàng chỉ truy cập thường xuyên dữ liệu đơn hàng 14 ngày gần nhất cùng một số index tra cứu. Working set có thể nhỏ hơn rất nhiều so với tổng database. Ngược lại, một báo cáo chạy toàn lịch sử có thể mở rộng working set tạm thời và đẩy các page nóng của giao dịch ra khỏi buffer pool.

Ba khái niệm cần tách biệt:

| Khái niệm | Ý nghĩa | Dùng để làm gì |
|---|---|---|
| Database footprint | Tổng kích thước data và index trên storage | Dự báo dung lượng lưu trữ và giới hạn dữ liệu |
| Working set | Các page được workload truy cập trong cửa sổ quan sát | Ước lượng nhu cầu cache |
| Buffer pool size | Dung lượng RAM InnoDB cấp cho page cache | Giới hạn số page có thể giữ cùng lúc |

Không nên tăng buffer pool chỉ vì tổng database lớn hơn RAM. Cũng không nên giảm buffer pool chỉ vì database nhỏ: nhiều index, truy vấn đồng thời và workload ghi có thể cần headroom cho page churn, dirty page và cấu trúc nội bộ.

## 3. LRU, old/young page và eviction

InnoDB quản lý page trong buffer pool bằng các danh sách LRU. Page mới đọc thường được đưa vào vùng old; page được truy cập lại đủ điều kiện sẽ được đưa lên vùng young. Cơ chế này giúp page có khả năng được dùng lại tồn tại lâu hơn, trong khi page chỉ được đọc một lần có thể bị loại sớm hơn.

Thiết kế midpoint insertion giúp giảm hiện tượng một truy vấn quét tuần tự bảng lớn làm thay thế toàn bộ cache nóng. Các biến liên quan gồm:

```sql
SHOW VARIABLES LIKE 'innodb_old_blocks%';
```

- `innodb_old_blocks_pct` điều khiển tỷ lệ vùng old trong LRU.
- `innodb_old_blocks_time` điều khiển khoảng thời gian page phải nằm trong vùng old trước khi lần truy cập tiếp theo có thể đưa page lên young.

Không điều chỉnh các biến này theo cảm tính. Nếu workload có full scan hoặc báo cáo lớn, trước tiên hãy xác định truy vấn đó có làm tăng read-ahead eviction và đẩy page nóng ra khỏi cache hay không. Thay đổi LRU policy có thể giúp workload quét tuần tự, nhưng cũng có thể làm giảm hiệu quả cache cho truy vấn khác.

Khi buffer pool cần chỗ cho page mới mà không còn free page, InnoDB phải lấy page có thể loại khỏi LRU. Nếu page đó dirty, cần flush trước khi tái sử dụng. Vì vậy, áp lực buffer pool có thể biểu hiện qua cả read I/O lẫn flush I/O.

## 4. Đo logical read và physical read

Hai counter cơ bản:

- `Innodb_buffer_pool_read_requests`: số logical read request đến buffer pool.
- `Innodb_buffer_pool_reads`: số lần InnoDB phải đọc page vào buffer pool vì page không có sẵn trong cache.

Lấy số liệu:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%';
```

Hit ratio thường được ước lượng trên một khoảng đo bằng delta của hai counter:

\[
\text{Hit ratio} =
\left(1 - \frac{\Delta\text{physical reads}}
{\Delta\text{logical read requests}}\right) \times 100\%
\]

Ví dụ, trong 10 phút có 100 triệu logical read request và 50.000 buffer pool read miss:

\[
\left(1 - \frac{50{,}000}{100{,}000{,}000}\right) \times 100
= 99.95\%
\]

Đây là tỷ lệ tham khảo, không phải bằng chứng rằng truy vấn đã nhanh. Một hit ratio 99,95% vẫn có thể đi cùng latency cao nếu 50.000 miss tập trung trong vài giây, storage chậm hoặc workload bị lock wait. Ngược lại, một batch scan lớn có thể làm ratio giảm nhưng vẫn hoàn thành trong thời gian chấp nhận được.

### Lấy delta đúng cách

Counter GLOBAL thường tích lũy từ lúc server khởi động hoặc từ lần reset status. Hãy lấy hai snapshot cách nhau một khoảng đại diện, ghi timestamp, rồi tính delta. Nếu server restart hoặc counter bị reset giữa hai snapshot, bỏ cửa sổ đo đó và bắt đầu lại.

`Innodb_buffer_pool_reads` là số lần InnoDB phải nạp page vào buffer pool, không phải số IOPS vật lý chắc chắn đi đến thiết bị. OS cache, storage cache và cách hệ thống thực hiện I/O có thể ảnh hưởng số liệu ở tầng thiết bị. Muốn đo physical I/O thực, kết hợp metrics của hệ điều hành và storage.

## 5. Đọc trạng thái page và áp lực buffer pool

Các status counter hữu ích:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_data',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_misc',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free',
    'Innodb_buffer_pool_read_ahead',
    'Innodb_buffer_pool_read_ahead_evicted'
);
```

| Counter | Cách đọc |
|---|---|
| `Innodb_buffer_pool_pages_total` | Tổng số page frame trong buffer pool |
| `Innodb_buffer_pool_pages_data` | Page chứa dữ liệu được tính trong buffer pool |
| `Innodb_buffer_pool_pages_dirty` | Page đã thay đổi nhưng chưa được flush |
| `Innodb_buffer_pool_pages_free` | Page frame hiện còn trống |
| `Innodb_buffer_pool_pages_misc` | Page dùng cho mục đích nội bộ/metadata của buffer pool |
| `Innodb_buffer_pool_pages_flushed` | Số page đã được flush; nên theo dõi delta |
| `Innodb_buffer_pool_wait_free` | Số lần InnoDB phải chờ free page; cần xem delta và workload |
| `Innodb_buffer_pool_read_ahead` | Page được đọc trước vào buffer pool |
| `Innodb_buffer_pool_read_ahead_evicted` | Page read-ahead bị loại trước khi được truy cập; có thể gợi ý prefetch không hữu ích |

`pages_free` thấp không tự động có nghĩa buffer pool thiếu RAM. InnoDB có thể sử dụng phần lớn pool cho page cache và chủ động thay thế page theo LRU. Dấu hiệu đáng lo hơn là `Innodb_buffer_pool_wait_free` tăng trong giờ tải cao, read miss tăng, flush không theo kịp và latency đọc/ghi xấu đi.

`pages_dirty` cao cũng không tự động là lỗi. Dirty page là dữ liệu đang chờ flush; cần quan sát tỷ lệ dirty, tốc độ flush, checkpoint pressure và khả năng storage. Nếu dirty page tăng liên tục trong khi page cleaner không theo kịp, write workload có thể gây áp lực lên buffer pool và redo log.

## 6. Read-ahead và cache pollution

InnoDB có thể đọc trước page mà nó dự đoán sẽ được truy cập tiếp theo, ví dụ khi phát hiện truy cập tuần tự hoặc theo extent. Read-ahead giúp giảm độ trễ khi workload thực sự dùng các page kế tiếp.

Nếu page được đọc trước nhưng không được truy cập, chúng có thể bị loại khỏi buffer pool. Theo dõi delta của:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read_ahead%';
```

Nếu `Innodb_buffer_pool_read_ahead_evicted` tăng nhanh so với `Innodb_buffer_pool_read_ahead`, có thể workload đang prefetch nhiều page không dùng. Hãy tìm query scan lớn, báo cáo toàn bảng hoặc pattern đọc tuần tự. Đừng kết luận chỉ từ một tỷ lệ: một số tác vụ batch có chủ đích vẫn tạo read-ahead eviction.

Các biện pháp thường hiệu quả hơn việc đổi LRU ngay lập tức:

- Chạy báo cáo nặng ở thời điểm ít ảnh hưởng workload giao dịch.
- Chỉ đọc cột và khoảng dữ liệu cần thiết.
- Dùng partition pruning và index phù hợp để giảm scan.
- Chia batch theo phạm vi khóa khi nghiệp vụ cho phép.
- Đo lại cache miss và latency của cả workload trước khi đổi biến read-ahead/LRU.

## 7. Ước lượng kích thước working set

### Bước 1: ước lượng data và index footprint

Thông tin `INFORMATION_SCHEMA.TABLES` có thể dùng để lập danh sách bảng InnoDB lớn:

```sql
SELECT TABLE_SCHEMA,
       TABLE_NAME,
       DATA_LENGTH,
       INDEX_LENGTH,
       DATA_FREE,
       DATA_LENGTH + INDEX_LENGTH AS data_and_index_bytes
FROM information_schema.tables
WHERE ENGINE = 'InnoDB'
  AND TABLE_SCHEMA = DATABASE()
ORDER BY data_and_index_bytes DESC
LIMIT 30;
```

`DATA_LENGTH` và `INDEX_LENGTH` là số liệu ước lượng theo metadata/storage engine; chúng không cho biết chính xác page nào đang nóng. Với bảng partitioned, hãy xem cả số liệu theo partition khi cần.

### Bước 2: xác định workload truy cập

Phân loại truy vấn theo:

- Bảng và index được truy cập.
- Khoảng thời gian dữ liệu (ví dụ 7 ngày gần nhất hay toàn bộ lịch sử).
- Tần suất và concurrency.
- Tỷ lệ đọc/ghi.
- Truy vấn point lookup, range scan, join, aggregate hay full scan.

Kết hợp query digest, slow log và `EXPLAIN` để biết bảng/index nào được truy cập thường xuyên. Kích thước của các bảng nóng cộng với index cần thiết là điểm bắt đầu để ước lượng working set, không phải kết quả cuối cùng.

### Bước 3: đo miss trong giờ tải đại diện

Lấy delta `Innodb_buffer_pool_reads` và `Innodb_buffer_pool_read_requests` trong nhiều cửa sổ: giờ cao điểm, batch job, báo cáo, backup và sau restart. Nếu miss tăng mạnh chỉ trong lúc báo cáo, có thể cần cô lập workload thay vì tăng pool cho toàn server.

### Bước 4: thử nghiệm kích thước khác nhau

Trên staging hoặc trong cửa sổ kiểm soát, thay đổi pool theo từng bước, chạy cùng workload và so sánh:

- p95/p99 query latency và transaction latency.
- Delta physical reads và logical read requests.
- Read IOPS, write IOPS và storage latency.
- Dirty page, pending flush và checkpoint pressure.
- RSS/working set của `mysqld`, memory pressure và swap.
- Throughput và error/timeout rate.

Chỉ tăng buffer pool nếu giảm miss tạo ra cải thiện thực tế mà không làm memory pressure tăng ở tầng hệ điều hành/container.

## 8. Sizing buffer pool và ngân sách RAM toàn instance

`innodb_buffer_pool_size` là biến chính để điều khiển dung lượng buffer pool. Với server chuyên chạy MySQL, buffer pool thường chiếm phần lớn RAM; các tỷ lệ như 50-75% RAM vật lý có thể dùng làm điểm khởi đầu cho một số workload, nhưng không phải công thức áp dụng cho mọi hệ thống.

Trước khi chọn giá trị, lập ngân sách cho tất cả thành phần:

| Thành phần | Cách tiêu thụ RAM |
|---|---|
| InnoDB buffer pool | Vùng lớn, thường được cấp phát theo cấu hình |
| Redo log buffer và cấu trúc InnoDB khác | Bộ nhớ dùng chung cho hoạt động transaction/storage |
| Connection/thread | Thread stack, network buffer, session state và cấu trúc kết nối |
| Per-operation buffers | Sort, join, read, read-rnd buffer; có thể cấp phát theo truy vấn và nhiều lần trong một execution plan |
| TempTable | Ngân sách RAM toàn cục và các cấp phát thread-local theo phiên bản |
| Performance Schema | Instrument, history và memory summary |
| Table/open cache, data dictionary, adaptive hash và cấu trúc nội bộ | Bộ nhớ global và metadata |
| OS và tiến trình khác | Kernel, filesystem cache, agent, backup, monitoring, replication tools |

### Vì sao không nhân mọi buffer với max_connections?

`max_connections` là giới hạn kết nối đồng thời, không phải số lượng mọi buffer đã được cấp phát ngay khi server khởi động. Nhiều buffer được cấp phát khi một truy vấn cần dùng; một số được giữ trong session hoặc thread; một execution plan có thể dùng nhiều buffer cho các operation khác nhau.

Ước lượng thực tế nên dựa trên số session hoạt động đồng thời, phân phối query, số operation sort/join, kích thước kết quả, TempTable và peak workload. Dùng concurrency thực đo và quan sát memory high-water mark; không cộng mọi giá trị cấu hình như thể tất cả đều luôn được sử dụng bởi mọi connection.

### Ví dụ ngân sách minh họa

Giả sử máy có 64 GiB RAM, MySQL là workload chính nhưng cùng host còn có OS, backup agent và monitoring. Một kế hoạch ban đầu có thể dành 40 GiB cho buffer pool, để phần còn lại cho redo/undo structures, connection/query buffers, TempTable, Performance Schema, filesystem cache và headroom. Con số 40 GiB chỉ minh họa cách phân bổ; phải thay bằng kết quả đo peak memory và yêu cầu workload thực tế.

Có thể lập ngân sách theo thứ tự:

```text
RAM khả dụng cho host/container
- phần dự phòng cho OS và tiến trình ngoài mysqld
- headroom cho peak workload và tác vụ bảo trì
= ngân sách tối đa dự kiến cho mysqld

ngân sách mysqld
- memory ngoài buffer pool ở peak concurrency
= giới hạn khởi điểm để đánh giá buffer pool
```

Đo memory ngoài buffer pool bằng workload đại diện và memory instrumentation; đừng lấy tổng các giá trị cấu hình per-operation làm số đã cấp phát thực tế.

Không để `mysqld` chạm sát memory limit của container hoặc RAM vật lý. Khi kernel phải swap mạnh hoặc container bị OOM kill, latency có thể tăng đột ngột và instance có thể bị dừng.

## 9. Thay đổi buffer pool size

`innodb_buffer_pool_size` hỗ trợ thay đổi động trên các phiên bản MySQL hiện đại:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';

SET GLOBAL innodb_buffer_pool_size = 42949672960;
```

Giá trị ví dụ ở trên là 40 GiB tính bằng byte; chỉ dùng khi ngân sách RAM cho phép. Thay đổi online có thể mất thời gian vì InnoDB phải điều chỉnh số page, flush hoặc loại page. Trong lúc resize, một số hoạt động có thể bị hạn chế hoặc chờ.

Các điểm cần kiểm tra:

- `innodb_buffer_pool_chunk_size` và số buffer pool instance ảnh hưởng đơn vị resize hợp lệ trên các phiên bản hỗ trợ chunk.
- Giá trị yêu cầu có thể được làm tròn theo bội số chunk/instance; đọc lại biến sau resize để biết kích thước hiệu lực.
- Không phải mọi thay đổi đều có thể hoàn tất ngay; theo dõi error log và trạng thái InnoDB.
- Không shrink xuống dưới mức cần cho active workload hoặc khiến working set nóng bị đẩy ra hàng loạt.
- Thay đổi GLOBAL chỉ ảnh hưởng instance hiện tại; muốn giữ sau restart cần cấu hình startup/persist phù hợp với chính sách vận hành.

Trước khi resize, ghi lại baseline. Sau resize, theo dõi latency, read miss, free/dirty pages, RSS, swap và storage I/O qua ít nhất một chu kỳ workload đại diện. Nếu memory pressure tăng hoặc throughput giảm, rollback về giá trị trước theo quy trình cấu hình.

## 10. Buffer pool instances và chunk

Buffer pool có thể được chia thành nhiều instance để giảm tranh chấp cấu trúc nội bộ trong workload có nhiều thread. Mỗi instance quản lý một phần page và metadata riêng. Với workload hiện đại, lợi ích phụ thuộc concurrency và phiên bản; không nên tăng số instance mà không đo.

`innodb_buffer_pool_chunk_size` xác định đơn vị cấp phát/resize theo chunk trên các phiên bản sử dụng cơ chế này. Kết hợp với số instance, nó ảnh hưởng kích thước buffer pool hiệu lực và mức điều chỉnh online. Kiểm tra:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_instances';
SHOW VARIABLES LIKE 'innodb_buffer_pool_chunk_size';
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
```

Số instance và chunk size có ràng buộc theo phiên bản, có thể chỉ thiết lập khi khởi động. Hãy tham khảo tài liệu đúng phiên bản trước khi thay đổi. Nhiều instance hơn không làm working set nhỏ đi và cũng không tự tăng tốc storage.

## 11. Dirty page, page cleaner và năng lực storage

Khi transaction sửa page, page trong buffer pool trở thành dirty. InnoDB phải flush dirty page xuống tablespace theo checkpoint, áp lực free page và chính sách flush. Các biến có liên quan:

```sql
SHOW VARIABLES LIKE 'innodb_max_dirty_pages_pct';
SHOW VARIABLES LIKE 'innodb_io_capacity';
SHOW VARIABLES LIKE 'innodb_io_capacity_max';
SHOW VARIABLES LIKE 'innodb_page_cleaners';
```

`innodb_io_capacity` và `innodb_io_capacity_max` giúp InnoDB ước lượng năng lực I/O nền và giới hạn flush trong một số tình huống. Đặt quá thấp có thể làm dirty page/checkpoint tích tụ; đặt quá cao có thể tranh chấp I/O với truy vấn foreground. Hãy đo năng lực storage thực tế, latency và dirty page trước khi điều chỉnh.

`Innodb_buffer_pool_pages_dirty` nên được xem cùng `Innodb_buffer_pool_pages_data`, `Innodb_buffer_pool_pages_total`, tốc độ `Innodb_buffer_pool_pages_flushed`, redo/checkpoint pressure và write latency. Một snapshot đơn lẻ không đủ kết luận page cleaner bị nghẽn; cần xu hướng theo thời gian.

## 12. Làm ấm buffer pool sau restart

Sau restart, buffer pool có thể gần như rỗng. Các truy vấn đầu tiên phải đọc page từ tablespace, khiến latency cao hơn cho đến khi working set nóng được nạp lại. MySQL hỗ trợ dump danh sách page trong buffer pool trước shutdown và load lại sau startup:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_dump_at_shutdown';
SHOW VARIABLES LIKE 'innodb_buffer_pool_load_at_startup';
SHOW VARIABLES LIKE 'innodb_buffer_pool_dump_pct';
```

Có thể cấu hình:

```ini
[mysqld]
innodb_buffer_pool_dump_at_shutdown=ON
innodb_buffer_pool_load_at_startup=ON
```

`innodb_buffer_pool_load_at_startup` là tùy chọn lúc khởi động trên các phiên bản hiện đại; không giả định có thể bật nó bằng `SET GLOBAL` trong một instance đang chạy. Để chủ động dump/load ngay trong runtime, dùng các biến điều khiển động:

```sql
SET GLOBAL innodb_buffer_pool_dump_now = ON;
SET GLOBAL innodb_buffer_pool_load_now = ON;
```

Dump lưu thông tin page cần nạp lại, không phải bản sao nội dung page. Khi startup, InnoDB đọc các page đó từ tablespace để làm ấm cache. File dump thường được lưu trong data directory dưới tên `ib_buffer_pool`; vị trí và cách xử lý phụ thuộc cấu hình/phiên bản.

Dump/load không phải backup và không bảo đảm mọi page nóng đều được nạp. `innodb_buffer_pool_dump_pct` có thể giới hạn phần page được dump. Sau startup, theo dõi tiến trình load, physical reads và latency; workload thực tế vẫn cần thời gian để ổn định.

## 13. Theo dõi bộ nhớ bằng Performance Schema và hệ điều hành

Performance Schema có thể thống kê memory instrument nếu chúng được bật:

```sql
SELECT EVENT_NAME,
       CURRENT_NUMBER_OF_BYTES_USED,
       HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'memory/innodb/%'
   OR EVENT_NAME LIKE 'memory/sql/%'
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 30;
```

Instrument có thể không bao phủ mọi vùng cấp phát hoặc không được bật trong cấu hình hiện tại. Vì vậy, số liệu Performance Schema là góc nhìn theo instrument, không thay thế RSS/working set của tiến trình và mức dùng memory của container/host.

Kết hợp các nguồn:

- `innodb_buffer_pool_size`: dung lượng pool được cấu hình.
- `SHOW GLOBAL STATUS`: page count, logical read, physical read, dirty page, wait-free và read-ahead.
- `SHOW ENGINE INNODB STATUS`: LRU, buffer pool, pending reads/flush và thông tin I/O.
- Performance Schema memory summary: các vùng cấp phát đã instrument.
- Hệ điều hành: process RSS/working set, available memory, swap-in/swap-out và OOM event.
- Container/cgroup: memory current, memory limit, memory pressure và OOM kill count nếu MySQL chạy trong container.
- Storage: IOPS, throughput, queue depth và read/write latency.

Không suy ra buffer pool đang thiếu chỉ vì RSS của `mysqld` lớn. Một instance được cấu hình pool lớn sẽ có RSS cao là bình thường; điều cần tìm là memory pressure, swap, OOM risk và latency thực tế.

## 14. Quy trình đo và điều chỉnh working set

1. Ghi lại RAM vật lý/container limit, buffer pool size, page size, max connections và các giới hạn TempTable.
2. Lấy kích thước data/index theo bảng và xác định các bảng/index nóng từ query digest, workload trace.
3. Chọn cửa sổ đại diện gồm peak OLTP, batch/reporting và workload sau restart.
4. Chụp hai snapshot status cách nhau một khoảng; tính delta logical reads, physical reads, wait-free, read-ahead và pages flushed.
5. Đối chiếu hit ratio với p95/p99 latency, storage I/O, dirty page và application throughput.
6. Kiểm tra query gây scan lớn, index thiếu, pagination hoặc truy cập dữ liệu lịch sử không cần thiết.
7. Lập ngân sách RAM toàn instance, tính peak connection/query/TempTable và headroom cho OS/container.
8. Thay đổi buffer pool theo bước có kiểm soát trên staging hoặc cửa sổ bảo trì; xác minh kích thước hiệu lực.
9. Chạy lại workload tương đương và so sánh latency, miss, I/O, RSS, swap và OOM risk.
10. Lưu baseline, cấu hình đã chọn, lý do và kế hoạch rollback.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Database lớn hơn RAM nên buffer pool phải bằng toàn bộ RAM | Working set có thể nhỏ hơn database; cần dành RAM cho các thành phần khác |
| Hit ratio 99,9% nghĩa là truy vấn nhanh | Miss có thể tập trung, storage chậm hoặc query bị lock wait |
| `pages_free = 0` nghĩa là buffer pool hết bộ nhớ | InnoDB dùng LRU để tái sử dụng page; cần xem wait-free và latency |
| Dirty page càng thấp càng tốt | Flush liên tục có thể tăng write I/O; cần cân bằng checkpoint và storage |
| Tăng buffer pool luôn giảm I/O | Có thể chỉ tăng RSS, làm OS swap hoặc không cải thiện workload |
| `max_connections × mọi buffer` là memory requirement | Nhiều buffer cấp phát theo nhu cầu; phải dùng concurrency và workload thực đo |
| Buffer pool dump là backup | Dump chỉ lưu danh sách page để warm-up; dữ liệu vẫn nằm trong tablespace/backup |
| Nhiều buffer pool instance luôn tốt hơn | Lợi ích phụ thuộc concurrency, phiên bản và overhead quản lý |

## 16. Bài thực hành

Trên MySQL instance thử nghiệm có dữ liệu đại diện:

1. Ghi lại `innodb_buffer_pool_size`, `innodb_page_size`, số instance và chunk size.
2. Lấy hai snapshot `Innodb_buffer_pool_read_requests` và `Innodb_buffer_pool_reads` cách nhau 10 phút; tính hit ratio từ delta.
3. Ghi nhận pages total/data/dirty/free, wait-free và read-ahead counters. Giải thích vì sao free page thấp không tự động là lỗi.
4. Truy vấn `INFORMATION_SCHEMA.TABLES` để xếp hạng bảng theo data và index size; so sánh với bảng/index thực sự xuất hiện trong workload.
5. Chạy workload OLTP rồi chạy một full scan lớn; quan sát physical reads và read-ahead eviction trước/sau.
6. So sánh latency và storage I/O khi tăng buffer pool trên staging; theo dõi RSS, swap và container memory limit.
7. Bật buffer pool dump/load trên môi trường thử nghiệm, restart và đo thời gian warm-up cùng latency trong giai đoạn đầu.
8. Lập ngân sách RAM gồm buffer pool, connection, query buffers, TempTable, Performance Schema, OS và headroom; giải thích giả định concurrency.
9. Viết runbook khi `Innodb_buffer_pool_wait_free` tăng liên tục và storage read latency cao.

## Ghi nhớ

- Buffer pool cache page InnoDB; working set là page workload thực sự truy cập, không phải toàn bộ database footprint.
- Dùng delta logical reads và physical reads để ước lượng cache behavior; hit ratio không thay thế latency và I/O metrics.
- `pages_free`, dirty page, read-ahead eviction và wait-free phải được đọc cùng nhau theo thời gian.
- Sizing cần tính cả connection/query buffers, TempTable, Performance Schema, OS, container limit và peak concurrency.
- Thay đổi `innodb_buffer_pool_size` cần kiểm tra chunk/instance, kích thước hiệu lực, error log và tác động tới RSS/latency.
- Buffer pool dump/load giúp warm-up sau restart; nó không phải backup và không thay thế dữ liệu trên tablespace.
- Chỉ tăng buffer pool khi số liệu cho thấy working set bị thiếu cache và host/container vẫn còn headroom an toàn.
