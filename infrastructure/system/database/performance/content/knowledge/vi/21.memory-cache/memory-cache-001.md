# Buffer pool, shared buffers và bộ đệm trang của hệ điều hành

Đọc dữ liệu từ bộ nhớ thường nhanh hơn nhiều so với đọc từ thiết bị lưu trữ. Vì vậy, hệ quản trị cơ sở dữ liệu duy trì các trang dữ liệu thường dùng trong RAM để giảm I/O và rút ngắn thời gian truy vấn. Vùng nhớ này có tên gọi khác nhau tùy sản phẩm: **buffer pool** trong MySQL InnoDB và SQL Server, **shared buffers** trong PostgreSQL, **database buffer cache** trong Oracle. Bên cạnh đó, hệ điều hành cũng có **page cache** để lưu các trang dữ liệu của file trong RAM. Hai lớp bộ đệm có thể phối hợp hoặc tạo ra hiện tượng lưu trữ trùng lặp tùy cách hệ quản trị thực hiện I/O.

Bài học thuộc chương **Bộ nhớ và bộ đệm** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Do đó, hiểu buffer pool, shared buffers và OS page cache giúp phân biệt cache hit với I/O thật, nhận diện áp lực bộ nhớ, giải thích độ trễ và kiểm chứng thay đổi cấu hình bằng số liệu.

## 1. Vì sao cơ sở dữ liệu cần bộ đệm?

Các truy vấn thường đọc đi đọc lại một phần dữ liệu: hàng mới cập nhật, chỉ mục dùng thường xuyên, bảng danh mục hoặc những trang thuộc tập dữ liệu nóng. Nếu mỗi lần đọc đều truy cập thiết bị lưu trữ, độ trễ và thông lượng sẽ bị giới hạn bởi I/O.

Hệ quản trị chia dữ liệu thành các đơn vị lưu trữ gọi là **page** hoặc block. Khi truy vấn cần một page, DBMS thường kiểm tra vùng bộ nhớ quản lý của nó trước. Nếu page đã có trong bộ đệm, DBMS có thể sử dụng dữ liệu trong RAM. Nếu chưa có, DBMS phải yêu cầu đọc từ tầng lưu trữ; page sau đó có thể được đưa vào bộ đệm để những lần truy cập tiếp theo dùng lại.

Các lợi ích chính:

- Giảm số lần đọc từ thiết bị lưu trữ.
- Giảm độ trễ cho truy vấn đọc lặp lại cùng dữ liệu.
- Tăng throughput khi nhiều truy vấn cùng dùng một tập dữ liệu nóng.
- Cho phép DBMS quản lý page đã sửa đổi và ghi chúng xuống lưu trữ theo lịch phù hợp.
- Hạn chế việc mỗi truy vấn phải tự xử lý toàn bộ chi phí I/O.

Bộ đệm không làm cho dữ liệu lớn hơn RAM tự nhiên nằm hết trong bộ nhớ. DBMS phải lựa chọn page nào được giữ, page nào có thể thay thế và cách xử lý page đã bị sửa đổi. Hiệu quả phụ thuộc working set, mẫu truy cập, kích thước page, concurrency và chính sách ghi.

## 2. Phân biệt ba khái niệm: page, buffer và cache

Các thuật ngữ thường được dùng gần nhau nhưng không hoàn toàn giống nhau:

- **Page/block:** đơn vị dữ liệu mà hệ quản trị đọc hoặc ghi theo cấu trúc lưu trữ của nó. Kích thước page phụ thuộc hệ quản trị và cấu hình.
- **Buffer:** vùng RAM dùng để chứa nội dung một page trong quá trình DBMS xử lý.
- **Buffer pool/cache:** tập hợp các buffer cùng metadata và cơ chế quản lý vòng đời page, thay thế page, đồng bộ và ghi dữ liệu.
- **OS page cache:** bộ nhớ đệm của hệ điều hành dành cho nội dung file, được quản lý ở tầng filesystem/kernel.

Một page của DBMS có thể được giữ trong buffer pool của cơ sở dữ liệu. Trong một số cấu hình I/O, nội dung tương ứng của file cũng có thể nằm trong OS page cache. Khi dùng direct I/O hoặc cơ chế tương tự, DBMS có thể bỏ qua một phần OS page cache cho đường dữ liệu đó. Vì vậy, không thể suy luận rằng “đọc từ cache” luôn chỉ một tầng duy nhất.

## 3. Đường đi của một thao tác đọc

Một thao tác đọc khái quát có thể diễn ra như sau:

```text
Ứng dụng gửi truy vấn
        |
        v
Bộ tối ưu tạo kế hoạch
        |
        v
Executor yêu cầu page
        |
        v
DB buffer pool / shared buffers
        |
        +---- page đã có ----> đọc page trong RAM
        |
        +---- page chưa có --> yêu cầu I/O
                                  |
                                  v
                         OS page cache (nếu dùng)
                                  |
                                  v
                         Thiết bị lưu trữ
                                  |
                                  v
                         page được đưa vào buffer
        |
        v
Trả hàng cho truy vấn
```

Đây là mô hình khái quát. Thứ tự và cách phối hợp OS cache, direct I/O, asynchronous I/O, read-ahead và storage stack khác nhau theo hệ điều hành, hệ quản trị, storage engine và cấu hình.

### 3.1. Cache hit

Cache hit xảy ra khi page cần dùng đã có trong cache của lớp đang xét. DBMS có thể đọc nội dung từ RAM thay vì yêu cầu đọc page từ tầng lưu trữ. Cache hit thường giảm I/O và latency, nhưng truy cập vẫn cần CPU, đồng bộ và xử lý dữ liệu.

### 3.2. Cache miss

Cache miss xảy ra khi page chưa có trong cache đang xét. DBMS phải lấy page từ tầng thấp hơn. Tuy nhiên, một miss ở buffer pool không nhất thiết đồng nghĩa thiết bị vật lý phải đọc dữ liệu: nếu đường I/O dùng buffered I/O, OS page cache có thể đã giữ các byte tương ứng. Ngược lại, một page được DBMS báo là cache hit cũng không cho biết toàn bộ thời gian truy vấn, vì truy vấn còn có thể bị giới hạn bởi CPU, khóa, sort, join hoặc truyền dữ liệu.

### 3.3. Read-ahead và prefetch

Khi hệ quản trị dự đoán truy vấn sẽ đọc các page liên tiếp, nó có thể đọc trước một nhóm page (read-ahead/prefetch) để giảm thời gian chờ từng page riêng lẻ. Cơ chế này thường hữu ích cho scan tuần tự hoặc phạm vi lớn. Đọc trước quá nhiều dữ liệu không cần thiết có thể chiếm băng thông I/O và đẩy page nóng ra khỏi cache; mức độ và thuật toán phụ thuộc sản phẩm.

## 4. Đường đi của thao tác ghi và dirty pages

DBMS thường không ghi ngay từng thay đổi dữ liệu xuống file chính tại đúng thời điểm câu lệnh sửa một hàng. Thay vào đó, nó có thể sửa page trong bộ đệm và đánh dấu page là **dirty** (đã thay đổi, chưa được ghi xuống data file). Việc ghi page xuống lưu trữ được thực hiện bởi background writer, checkpoint hoặc cơ chế tương ứng của hệ quản trị.

Một mô hình khái quát:

```text
UPDATE / INSERT / DELETE
          |
          v
Thay đổi page trong buffer pool
          |
          +----> ghi log phục hồi theo quy tắc WAL/redo
          |
          v
Page trở thành dirty
          |
          v
Background writer / checkpoint / flush
          |
          v
Data files trên storage
```

Với hệ quản trị dùng write-ahead logging (WAL), log phục hồi cần được ghi bền vững theo quy tắc trước khi page dữ liệu tương ứng được phép ghi xuống data file. Điều này hỗ trợ phục hồi sau sự cố. Chi tiết thứ tự flush, group commit, checkpoint và durability phụ thuộc sản phẩm, transaction mode và cấu hình.

Dirty page vẫn có thể được đọc từ buffer pool. Nó không phải page lỗi hoặc dữ liệu chưa commit theo nghĩa đơn giản. Trạng thái dirty chỉ nói rằng nội dung trong RAM khác nội dung data file trên lưu trữ. DBMS phải bảo đảm transaction isolation và recovery để người dùng không đọc dữ liệu sai.

### 4.1. Checkpoint và áp lực ghi

Checkpoint giúp giới hạn lượng công việc phục hồi sau crash bằng cách bảo đảm một tập thay đổi đã được ghi đến mức cần thiết. Nếu checkpoint quá dồn dập hoặc phải flush quá nhiều dirty pages trong thời gian ngắn, hệ thống có thể gặp write I/O tăng đột biến, latency tăng và throughput giảm.

Nếu checkpoint quá thưa, lượng WAL cần replay sau sự cố có thể lớn hơn và yêu cầu lưu trữ log nhiều hơn. Cấu hình checkpoint là bài toán cân bằng; không nên thay đổi chỉ dựa vào một đợt ghi chậm mà cần xem checkpoint frequency, dirty page volume, WAL/log generation và storage latency.

### 4.2. Eviction của dirty page

Khi DBMS cần buffer trống nhưng page ứng viên đang dirty, hệ quản trị phải xử lý page đó theo chính sách ghi trước khi tái sử dụng buffer. Việc này có thể tạo write I/O ngay trong đường xử lý của truy vấn, hoặc được giảm thiểu bằng background writer và cơ chế flush trước. Vì vậy, tỷ lệ dirty pages cao, tốc độ tạo dirty pages và tốc độ ghi nền cần được theo dõi cùng nhau.

## 5. Buffer pool và shared buffers theo từng hệ quản trị

Tên gọi và cấu trúc nội bộ khác nhau, nhưng mục tiêu chung là giữ page dữ liệu và index trong RAM để phục vụ truy vấn.

| Hệ quản trị | Vùng đệm chính | Điểm cần nhớ |
|---|---|---|
| PostgreSQL | `shared_buffers` | Shared memory do PostgreSQL quản lý; với buffered I/O thông thường, OS page cache còn có thể giữ bản sao file data |
| MySQL InnoDB | InnoDB buffer pool | Chứa data pages, index pages và các cấu trúc liên quan; có thể cấu hình nhiều buffer pool instances tùy phiên bản |
| SQL Server | Buffer pool | Cache data/index pages trong memory manager; cùng tồn tại với memory grants và các vùng nhớ khác của SQL Server |
| Oracle Database | Database buffer cache trong SGA | Cache các database blocks; hoạt động cùng các thành phần SGA và cơ chế I/O của Oracle |

### 5.1. PostgreSQL: shared_buffers

`shared_buffers` là vùng shared memory PostgreSQL dùng để cache các data block. Khi block cần đọc đã ở trong shared buffers, truy vấn có thể sử dụng page từ vùng này. Nếu chưa có, PostgreSQL yêu cầu đọc block; với đường I/O buffered thông thường, dữ liệu có thể được phục vụ từ OS page cache thay vì thiết bị vật lý.

Một số điểm quan trọng:

- `shared_buffers` là bộ nhớ do PostgreSQL quản lý, không phải toàn bộ RAM mà PostgreSQL có thể sử dụng.
- OS page cache vẫn có thể góp phần cache data files.
- `effective_cache_size` là ước lượng cho planner về lượng cache có thể dùng, không cấp phát bộ nhớ thật.
- `work_mem` là giới hạn/budget cho một số thao tác sort/hash, không phải kích thước shared buffers.
- Các truy vấn lớn có thể đọc nhiều block và làm thay đổi tập page được giữ trong cache.

Ví dụ xem cấu hình:

```sql
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW work_mem;
```

Có thể xem thống kê database ở mức tổng quát:

```sql
SELECT
    datname,
    blks_read,
    blks_hit,
    CASE
        WHEN blks_hit + blks_read = 0 THEN NULL
        ELSE round(
            100.0 * blks_hit / (blks_hit + blks_read), 2
        )
    END AS shared_buffer_hit_pct
FROM pg_stat_database
WHERE datname = current_database();
```

`blks_hit` là block được tìm thấy trong shared buffers; `blks_read` là block được yêu cầu đọc vào shared buffers. `blks_read` không khẳng định thiết bị vật lý đã thực hiện I/O, vì OS page cache có thể đáp ứng. Thống kê có phạm vi tích lũy theo database và có thể chịu ảnh hưởng của workload khác; cần lấy delta theo khoảng đo và ghép với OS/storage metrics.

### 5.2. MySQL InnoDB: buffer pool

InnoDB buffer pool là vùng cache trọng tâm cho data pages và index pages. Nó cũng quản lý các danh sách và trạng thái như free pages, clean pages và dirty pages. InnoDB sử dụng chính sách thay thế dựa trên LRU có điều chỉnh, không đơn giản là xóa page ít được truy cập nhất theo một danh sách duy nhất.

Ví dụ kiểm tra một số biến và trạng thái:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%';
SHOW ENGINE INNODB STATUS;
```

Các counter cần xem theo delta trong cùng khoảng thời gian, ví dụ số lần đọc cần lấy page từ tầng lưu trữ so với số lần đọc được đáp ứng từ buffer pool. Tên và ý nghĩa chi tiết của counter cần đối chiếu theo phiên bản. `SHOW ENGINE INNODB STATUS` có thể cung cấp thông tin về buffer pool, dirty pages, I/O và hoạt động nền.

InnoDB có thể sử dụng nhiều buffer pool instances để giảm contention nội bộ ở cấu hình phù hợp. Tăng số instance không mặc nhiên cải thiện mọi hệ thống; cần xem kích thước buffer pool, số CPU, mức đồng thời và khuyến nghị phiên bản.

### 5.3. SQL Server: buffer pool

SQL Server dùng buffer pool để giữ các data pages đã đọc từ data files. Khi truy vấn cần page, storage engine kiểm tra page trong buffer pool; nếu chưa có, page được đọc vào. SQL Server cũng dùng bộ nhớ cho plan cache, query execution memory grants, columnstore và các thành phần khác, vì vậy không nên coi toàn bộ memory của tiến trình là buffer pool.

Các DMV thường dùng để xem page và memory:

```sql
SELECT
    COUNT(*) AS cached_pages,
    COUNT(*) * 8.0 / 1024 AS cached_mb
FROM sys.dm_os_buffer_descriptors
WHERE database_id = DB_ID();
```

Có thể xem tổng quan memory clerk và tình trạng memory pressure qua các DMV phù hợp. Quyền truy cập DMV phụ thuộc phiên bản và quyền server/database. Counter `Page life expectancy` từng được dùng như một tín hiệu, nhưng không nên áp một ngưỡng đơn lẻ cho mọi máy chủ; hãy xem xu hướng, NUMA node, workload và các memory pressure indicators khác.

### 5.4. Oracle: database buffer cache

Oracle duy trì database buffer cache trong System Global Area (SGA). Các database block được đọc vào cache và có thể ở trạng thái clean hoặc dirty. Buffer cache hoạt động cùng cơ chế redo, DB writer và checkpoint. Một số thao tác/direct path read có thể đi theo đường I/O khác với việc đưa page vào buffer cache thông thường.

Các view như `V$DB_CACHE_ADVICE`, `V$SYSSTAT`, `V$BUFFER_POOL` và `V$SGA_DYNAMIC_COMPONENTS` có thể hỗ trợ đánh giá cache, advice và memory component nếu quyền phù hợp. Không nên chỉ dựa trên một hit ratio tổng thể; hãy xem loại workload, physical reads, direct reads, wait events và thời gian phản hồi.

## 6. OS page cache là gì?

OS page cache là cơ chế của hệ điều hành giữ nội dung file trong RAM theo các page của filesystem/kernel. Khi một tiến trình đọc file bằng buffered I/O, kernel có thể trả dữ liệu từ page cache nếu dữ liệu đã được cache, tránh đọc lại từ storage.

OS page cache có thể phục vụ nhiều ứng dụng và file, không chỉ database. Kernel quản lý cache theo áp lực bộ nhớ toàn hệ thống; vùng nhớ này thường có thể được thu hồi khi ứng dụng cần RAM, nhưng việc reclaim và writeback vẫn có chi phí.

Các điểm cần hiểu:

- OS page cache không hiểu cấu trúc hàng, index hay transaction của DBMS; nó cache nội dung file ở mức hệ điều hành.
- DB buffer pool hiểu page của database và có thể quản lý trạng thái dirty, pin, latching, replacement theo quy tắc DBMS.
- Khi dùng buffered I/O, cùng dữ liệu có thể hiện diện ở cả DB buffer pool và OS page cache, tùy đường đọc/ghi.
- Khi dùng direct I/O hoặc cơ chế tương đương, một số I/O có thể bỏ qua OS page cache để tránh cache trùng lặp; yêu cầu căn chỉnh và hành vi cụ thể phụ thuộc nền tảng.
- OS page cache cũng được dùng cho các file khác, nên database có thể cạnh tranh bộ nhớ với filesystem cache và tiến trình khác.

### 6.1. Buffered I/O và direct I/O

Với buffered I/O, thao tác đọc/ghi đi qua page cache của hệ điều hành. Cách này tận dụng cache chung và cơ chế read-ahead/writeback của kernel. Với direct I/O, ứng dụng hoặc DBMS có thể yêu cầu truyền dữ liệu trực tiếp hơn giữa buffer của tiến trình và thiết bị, giảm hoặc bỏ qua một phần page cache.

Direct I/O không tự động nhanh hơn buffered I/O. Nó có thể tránh giữ hai bản sao của cùng dữ liệu, nhưng DBMS phải tự quản lý cache hiệu quả; yêu cầu alignment, kích thước I/O và đường ghi có thể phức tạp hơn. Lựa chọn phụ thuộc engine, filesystem, kernel, storage và workload. Chỉ thay đổi I/O mode theo hướng dẫn chính thức của hệ quản trị và kiểm chứng bằng benchmark.

### 6.2. Vì sao DBMS vẫn cần cache riêng nếu OS đã có page cache?

DBMS cần biết page nào thuộc bảng/index nào, page đang dirty hay clean, transaction nào đang sử dụng và có thể thay thế page nào mà không vi phạm đồng bộ. OS page cache không hiểu các ngữ nghĩa đó. Buffer pool cho phép DBMS kết hợp cache với transaction, recovery, read-ahead, eviction và quản lý page nội bộ.

Trong cấu hình buffered I/O, hai lớp cache có thể cùng có lợi nhưng cũng có thể tạo ra chi phí lưu trữ trùng lặp. Trong cấu hình direct I/O, DBMS dựa nhiều hơn vào cache riêng. Vì vậy, khi điều chỉnh memory, phải hiểu đường I/O của đúng hệ quản trị thay vì mặc định OS cache luôn được dùng hoặc luôn bị bỏ qua.

## 7. Cache hit ratio: hữu ích nhưng không đủ

Một chỉ số phổ biến là tỷ lệ hit:

```text
hit ratio = cache hits / (cache hits + cache misses)
```

Tùy hệ quản trị, numerator/denominator có thể được định nghĩa khác nhau. Hit ratio cao cho thấy nhiều lần truy cập được đáp ứng từ cache của lớp đang đo. Nhưng nó không trực tiếp cho biết truy vấn nhanh hay chậm.

Ví dụ:

- Một truy vấn đọc 10 triệu page, hit 99% vẫn có thể thực hiện 100.000 page reads và tốn nhiều CPU/I/O.
- Một truy vấn hiếm khi chạy có hit ratio thấp nhưng không ảnh hưởng đáng kể đến workload tổng thể.
- Một hệ thống hit ratio cao vẫn có thể chậm vì lock wait, CPU, sort spill, network hoặc log flush.
- Một số lần miss có thể được OS page cache đáp ứng nên không gây physical device read.
- Cache hit tổng thể có thể che giấu một bảng nóng hoặc một nhóm truy vấn có miss rate cao.

Do đó, hãy kết hợp hit ratio với số lượng page read, physical I/O, latency, throughput, working set, wait events và query-level metrics. Dùng delta trong cửa sổ đo thay vì so sánh counter tích lũy từ khi khởi động.

## 8. Working set và hiện tượng cache churn

**Working set** là tập dữ liệu được workload truy cập thường xuyên trong một khoảng thời gian. Nếu working set nóng vừa với cache, nhiều truy vấn có thể được đáp ứng từ RAM. Nếu working set lớn hơn nhiều so với vùng cache hữu hiệu, page liên tục bị đưa vào rồi đẩy ra; hiện tượng này có thể tạo cache churn và I/O lặp lại.

Ví dụ:

- Bảng giao dịch có 500 GB nhưng workload giờ cao điểm chỉ truy cập thường xuyên 40 GB gần đây và một số index nóng. Cache không nhất thiết phải giữ toàn bộ 500 GB để có hiệu quả.
- Một báo cáo quét 300 GB có thể đẩy các page OLTP nóng ra khỏi cache nếu cơ chế scan không hạn chế tác động.
- Một truy vấn ngẫu nhiên trên tập dữ liệu lớn có thể làm cache hit giảm dù buffer pool đã được tăng.

Không đánh giá working set chỉ bằng kích thước bảng. Hãy xem tần suất truy cập, độ rộng hàng, index, locality, thời gian giữ dữ liệu nóng và mẫu tải theo giờ/ngày.

### 8.1. Cache pollution

Cache pollution xảy ra khi một workload đọc nhiều dữ liệu ít tái sử dụng, làm đẩy page có giá trị tái sử dụng cao ra khỏi cache. Ví dụ full table scan hoặc báo cáo ad-hoc có thể ảnh hưởng cache OLTP nếu scan lớn và cơ chế cache không cách ly tốt.

Hướng xử lý có thể gồm:

- Giảm lượng dữ liệu scan bằng predicate và index phù hợp.
- Chạy báo cáo trên replica hoặc hệ phân tích riêng nếu kiến trúc cho phép.
- Lên lịch batch nặng vào thời gian ít ảnh hưởng.
- Dùng partition pruning để giới hạn phạm vi đọc.
- Điều chỉnh cách scan hoặc cache behavior nếu hệ quản trị hỗ trợ và có bằng chứng.

Không tăng buffer pool một cách máy móc nếu nguyên nhân là truy vấn đọc thừa hoặc workload phân tích cạnh tranh với OLTP.

## 9. Chính sách thay thế page và dirty-page management

Cache có dung lượng hữu hạn. Khi cần nạp page mới mà không còn buffer trống, DBMS phải chọn page có thể thay thế. Nhiều hệ quản trị dùng biến thể LRU (Least Recently Used), clock sweep hoặc thuật toán có nhiều danh sách và ưu tiên.

Không nên giả định mọi DBMS dùng một LRU đơn giản. Ví dụ InnoDB có cơ chế midpoint insertion để hạn chế scan đẩy page nóng ra quá nhanh; PostgreSQL dùng clock sweep để chọn buffer; các sản phẩm khác có thuật toán riêng.

### 9.1. Pin, latch và lock không phải một khái niệm

Khi đọc tài liệu về buffer pool, cần phân biệt:

- **Pin/reference:** giữ page trong trạng thái không thể bị tái sử dụng trong lúc một thao tác đang cần page, theo cơ chế của DBMS.
- **Latch:** đồng bộ ngắn hạn để bảo vệ cấu trúc bộ nhớ hoặc page trong lúc truy cập/cập nhật nội bộ.
- **Lock:** cơ chế đồng thời ở mức transaction/logic dữ liệu để bảo vệ tính nhất quán và isolation.

Một truy vấn có thể chờ latch hoặc buffer pin dù không chờ transaction lock. Chẩn đoán memory/cache contention cần đọc đúng loại wait event và tài liệu hệ quản trị.

### 9.2. Dirty pages và tốc độ ghi nền

Nếu tốc độ tạo dirty pages lớn hơn tốc độ DBMS có thể flush trong thời gian dài, số dirty pages có thể tăng và đến lúc tạo áp lực checkpoint hoặc buộc thao tác foreground chờ. Theo dõi:

- Số lượng và tỷ lệ dirty pages.
- Tốc độ tạo dirty pages và tốc độ flush.
- Checkpoint frequency và checkpoint duration.
- WAL/redo/log generation và log flush latency.
- Data-file write latency, queue depth và throughput.

Không phải cứ dirty pages nhiều là có vấn đề; đó có thể là trạng thái bình thường giữa hai checkpoint. Cần xem xu hướng, khả năng flush và ảnh hưởng đến latency.

## 10. Kích thước buffer pool và phân bổ bộ nhớ

Tăng buffer pool có thể giảm cache miss nếu workload có working set lớn hơn vùng cache hiện tại. Nhưng RAM của máy chủ không chỉ dành cho buffer pool. Cần để lại bộ nhớ cho:

- Hệ điều hành và OS page cache nếu đường I/O sử dụng.
- Các tiến trình DBMS ngoài buffer pool.
- Sort/hash memory grants hoặc work areas.
- Connection/session memory và worker stacks.
- Plan cache, metadata, shared memory và extension.
- Backup, monitoring, replication, agent và tiến trình phụ trợ.
- Các ứng dụng khác trên cùng máy chủ.

Nếu cấp phát quá nhiều cho cache, hệ điều hành có thể thiếu RAM, phải reclaim mạnh, swap hoặc gây memory pressure. Khi đó, page DB được cache nhiều hơn nhưng toàn hệ thống có thể chậm đi do swapping và cạnh tranh bộ nhớ.

### 10.1. Không đồng nhất cache với query execution memory

Buffer pool giữ page dữ liệu/index dùng lại giữa các truy vấn. `work_mem` của PostgreSQL, memory grant của SQL Server và work areas của Oracle phục vụ các toán tử thực thi như sort, hash join, hash aggregate. Đây là các nhóm bộ nhớ khác nhau.

Tăng query memory có thể giảm sort/hash spill nhưng làm mỗi truy vấn đồng thời tiêu thụ nhiều RAM hơn. Tăng buffer pool có thể cải thiện cache hit nhưng không giải quyết một hash join cần bộ nhớ tạm quá lớn. Hãy xác định loại bộ nhớ bị thiếu trước khi điều chỉnh.

### 10.2. Ước lượng theo working set, không theo phần trăm cố định

Một số hướng dẫn triển khai dùng tỷ lệ RAM tham khảo cho buffer pool, nhưng tỷ lệ phù hợp phụ thuộc:

- DBMS và phiên bản.
- Máy chủ chuyên dụng hay chia sẻ với ứng dụng.
- Kích thước working set và index nóng.
- Tỷ lệ đọc/ghi, scan lớn và workload đồng thời.
- Có dùng OS page cache hay direct I/O.
- Bộ nhớ cho sort/hash, connection và tiến trình nền.
- Yêu cầu headroom khi backup, failover hoặc tải tăng.

Hãy bắt đầu từ số liệu hiện trạng, thay đổi theo bước nhỏ trong môi trường kiểm thử, theo dõi memory pressure và latency, rồi mới áp dụng có kiểm soát.

## 11. Các chỉ số cần theo dõi

Không có một dashboard duy nhất phù hợp cho mọi DBMS, nhưng các nhóm chỉ số sau giúp phân tích.

| Nhóm | Chỉ số | Câu hỏi cần trả lời |
|---|---|---|
| Buffer pool | Cache hit, page reads, buffer usage | Page nóng có được giữ trong cache không? |
| Physical I/O | Read/write IOPS, throughput, latency, queue depth | Miss có dẫn đến I/O chậm ở storage không? |
| Dirty pages | Dirty count/percentage, flush rate | DBMS có ghi nền đủ nhanh không? |
| Memory pressure | Available memory, swap, reclaim, page faults | Cache có làm thiếu RAM cho hệ thống không? |
| Query | Logical reads, physical reads, rows, elapsed time | Truy vấn nào đọc nhiều hoặc miss nhiều? |
| Checkpoint/log | Checkpoint duration, WAL/redo rate, log flush latency | Đường ghi và recovery có gây chờ không? |
| Concurrency | Buffer/latch waits, pins, lock waits | Có tranh chấp nội bộ hoặc transaction không? |
| OS cache | Page cache, cache reclaim, direct/buffered I/O | OS có giữ dữ liệu file và bị áp lực bộ nhớ không? |

### 11.1. Đo theo khoảng thời gian

Counter đọc/ghi thường là số tích lũy từ lúc khởi động hoặc reset thống kê. Để hiểu workload, hãy lấy hai snapshot cách nhau một khoảng thời gian rồi tính delta. Ghép số liệu với timestamp, loại truy vấn, số request và tải đồng thời.

Không so sánh hai hệ thống chỉ bằng hit ratio nếu một hệ thống đã chạy nhiều ngày và hệ thống kia vừa khởi động. Hãy so sánh cùng cửa sổ tải, cùng loại workload và cùng cách khởi tạo cache.

### 11.2. Quan sát ở cả DBMS và hệ điều hành

DBMS có thể báo buffer miss nhưng OS page cache đáp ứng, hoặc DBMS cache hit cao trong khi hệ điều hành đang swap các vùng nhớ khác. Vì vậy, ghép database metrics với OS metrics:

- RAM available/used, swap-in/swap-out.
- Major/minor page faults và memory reclaim.
- I/O latency, throughput, queue depth và device utilization.
- CPU user/system/iowait và run queue.
- File cache/page cache nếu công cụ hệ điều hành cung cấp.

Trên Linux, các công cụ như `free`, `vmstat`, `iostat` và `/proc/meminfo` có thể giúp quan sát tổng quan. Cách diễn giải trường `available`, cache và buffer cần theo kernel version; không coi toàn bộ memory hiển thị là “đang bị chiếm” hoặc “còn trống” theo một phép trừ đơn giản.

## 12. Ví dụ truy vấn và cách đọc số liệu

Giả sử một truy vấn đọc đơn hàng theo khách hàng:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 50;
```

Khi truy vấn chạy lần đầu với dữ liệu chưa có trong cache, DBMS có thể phải nạp các index/data pages. Những lần tiếp theo có thể nhanh hơn nếu các page vẫn còn trong buffer pool hoặc OS page cache.

Nếu logical reads cao, truy vấn có thể đang duyệt nhiều page trong cache dù không có nhiều physical I/O. Khi đó, tăng buffer pool có thể không giải quyết được lượng công việc CPU và page access; cần xem index, predicate, cardinality và execution plan.

Nếu physical reads hoặc storage reads cao cùng read latency cao, hãy xem working set, scan, cache churn và storage bottleneck. Nếu DBMS báo nhiều block reads nhưng storage device không có I/O tương ứng, OS page cache có thể đang đáp ứng một phần yêu cầu.

Nếu truy vấn nhanh khi chạy đơn lẻ nhưng chậm khi đồng thời, xem buffer/latch waits, memory pressure, cache churn, I/O queue và các transaction đang cạnh tranh. Không quy toàn bộ hiện tượng cho “cache nhỏ” chỉ từ việc latency tăng.

## 13. Quy trình điều tra khi nghi ngờ thiếu cache

Một quy trình có thể áp dụng:

1. **Xác định triệu chứng:** truy vấn nào chậm, ở thời điểm nào, p95/p99 thay đổi ra sao, workload đọc/ghi nào bị ảnh hưởng?
2. **Lấy baseline:** ghi planning/execution time, logical/physical reads, buffer metrics, storage latency, CPU, memory và wait events.
3. **Xác định tầng cache:** miss ở DB buffer pool, OS page cache hay storage thực sự? Kiểm tra I/O mode và counter phù hợp.
4. **Tìm working set:** xác định bảng/index nóng, phạm vi dữ liệu và query pattern; xem scan lớn có đẩy page nóng ra không.
5. **Đọc execution plan:** kiểm tra scan/seek, số page/row đọc, predicate, cardinality và sort/hash spill.
6. **Kiểm tra memory pressure:** RAM available, swap, reclaim, memory grant, connection/session memory và các tiến trình khác.
7. **Nêu giả thuyết:** ví dụ index scan đọc quá nhiều page, working set lớn hơn cache, hoặc OS đang swap.
8. **Thử một thay đổi:** tối ưu SQL/index, điều chỉnh cache hoặc tách workload; không thay nhiều yếu tố cùng lúc.
9. **Đo lại cùng workload:** dùng cùng dữ liệu, tham số, mức đồng thời, thời gian đo và trạng thái cache có thể so sánh.
10. **Đánh giá tác động phụ:** write latency, checkpoint, memory pressure, swap, throughput và workload khác.

## 14. Warm cache và cold cache

Kết quả benchmark phụ thuộc trạng thái cache. **Warm-cache test** đo hệ thống sau khi working set đã được nạp một phần hoặc phần lớn vào cache. **Cold-cache test** cố gắng đo khi dữ liệu chưa có trong cache liên quan.

Hai trạng thái trả lời câu hỏi khác nhau:

- Warm cache gần với workload lặp lại ổn định, nơi dữ liệu nóng được truy cập nhiều lần.
- Cold cache gần với lần đọc đầu, sau restart, failover hoặc khi truy vấn chạm vùng dữ liệu mới.

Cold-cache test khó tái tạo chính xác vì page có thể còn trong OS cache, storage controller cache hoặc cache của thiết bị. Restart DB không nhất thiết làm sạch OS page cache hoặc cache của storage. Không chạy lệnh xóa cache toàn hệ thống trên máy chủ production chỉ để tạo cold-cache benchmark.

Khi so sánh hai cấu hình, phải ghi rõ cách chuẩn bị cache. Một lượt chạy warm-cache không thể so trực tiếp với lượt cold-cache rồi kết luận cấu hình nào nhanh hơn.

## 15. Những ngộ nhận thường gặp

- **Hit ratio cao đồng nghĩa truy vấn nhanh:** truy vấn vẫn có thể đọc hàng triệu page trong cache hoặc bị chờ khóa/CPU.
- **DB buffer miss luôn là disk read:** OS page cache hoặc tầng storage cache có thể đáp ứng.
- **OS page cache thay thế được DB buffer pool:** OS không quản lý transaction, dirty page và metadata theo ngữ nghĩa DBMS.
- **Tăng cache càng nhiều càng tốt:** có thể gây thiếu RAM, swap và memory pressure.
- **Buffer pool và work memory là một:** chúng phục vụ mục đích khác nhau.
- **Mọi hệ quản trị đều dùng LRU giống nhau:** thuật toán thay thế và scan resistance khác nhau.
- **Dirty page là dữ liệu chưa commit hoặc bị lỗi:** dirty chỉ mô tả page đã thay đổi so với data file.
- **Restart DB tạo cold cache hoàn toàn:** OS page cache và các cache tầng dưới có thể vẫn còn nóng.
- **Chỉ nhìn counter tích lũy:** không thể so sánh workload nếu không lấy delta theo thời gian.
- **Chỉ nhìn database metrics:** bỏ qua swap, page reclaim, I/O queue và áp lực bộ nhớ của hệ điều hành.

## 16. Ví dụ thực hành: phân biệt cache miss và truy vấn đọc quá nhiều

Một API tra cứu đơn hàng có p95 tăng từ 40 ms lên 180 ms khi tải tăng. Dashboard cho thấy buffer hit ratio vẫn khoảng 98%, nhưng logical reads mỗi request tăng và CPU cao.

Các bước điều tra:

1. Lấy execution plan của truy vấn ở mức tải thấp và cao.
2. So sánh estimated rows, actual rows, số loops và index/table scan.
3. Xem logical reads theo query; xác định truy vấn có đọc nhiều page trong cache hay không.
4. Kiểm tra tham số có phân bố lệch khiến kế hoạch chọn scan hoặc lookup lặp lại không.
5. Kiểm tra buffer pool reads và OS/storage I/O riêng biệt.
6. Nếu logical reads lớn nhưng physical I/O thấp, ưu tiên giảm công việc truy cập page bằng SQL/index phù hợp.
7. Nếu physical I/O và storage latency cùng tăng, đánh giá working set, cache churn, read-ahead và storage capacity.
8. Chạy lại workload cùng concurrency để xác nhận p95, CPU, reads và throughput.

Trong tình huống này, tăng buffer pool có thể không giải quyết nguyên nhân nếu phần lớn page đã được cache nhưng truy vấn vẫn đọc quá nhiều page. Cần giảm lượng công việc trước khi tăng dung lượng cache.

## 17. Bài tập tự kiểm tra

### Bài tập 1: Buffer miss có phải physical I/O?

PostgreSQL ghi nhận `blks_read` tăng, nhưng storage device gần như không có read IOPS tương ứng.

**Câu hỏi:** có thể giải thích hiện tượng này thế nào?

**Gợi ý trả lời:** `blks_read` phản ánh block được đọc vào shared buffers, không khẳng định thiết bị vật lý đã đọc. Với buffered I/O, OS page cache có thể cung cấp dữ liệu. Cần xem I/O mode, OS cache và storage metrics cùng thời điểm.

### Bài tập 2: Hit ratio cao nhưng p95 xấu

Một hệ thống có buffer hit ratio 99,5%, nhưng p95 tăng mạnh khi tải cao; logical reads/request và CPU cũng tăng.

**Câu hỏi:** nên điều tra gì trước khi tăng buffer pool?

**Gợi ý trả lời:** xem execution plan, số page đọc, scan/lookup, cardinality, loops và query pattern. Cache hit cao không loại trừ việc đọc quá nhiều page trong RAM. Ưu tiên giảm logical reads và công việc CPU nếu đó là nguyên nhân.

### Bài tập 3: Buffer pool lớn làm hệ thống chậm hơn

Sau khi tăng buffer pool, máy chủ bắt đầu swap và latency tăng dù cache hit ratio cao hơn.

**Câu hỏi:** vì sao và cần làm gì?

**Gợi ý trả lời:** cấp phát cache có thể lấy mất RAM của OS, tiến trình DB khác hoặc query memory, gây reclaim/swap. Cần xem available memory, swap-in/out, memory grants, OS cache và workload. Thử mức cache thấp hơn, giữ headroom và đo toàn hệ thống.

### Bài tập 4: Dirty pages tăng liên tục

Trong giờ cao điểm, số dirty pages tăng nhanh, checkpoint kéo dài và write latency tăng.

**Câu hỏi:** cần theo dõi những gì để xác định nút thắt?

**Gợi ý trả lời:** so sánh tốc độ tạo dirty pages với tốc độ flush, checkpoint duration/frequency, WAL/redo generation, log flush latency, data-file write latency và storage queue. Xem workload ghi, batch và cấu hình checkpoint trước khi điều chỉnh.

### Bài tập 5: Cold-cache benchmark

Một nhóm restart DB rồi chạy benchmark và gọi đó là cold-cache test.

**Câu hỏi:** kết luận này có đủ chắc chắn không?

**Gợi ý trả lời:** chưa. OS page cache, storage controller hoặc device cache có thể còn dữ liệu. Cần mô tả rõ cache nào được làm lạnh, cách chuẩn bị và giới hạn phép đo; không xóa cache hệ thống production một cách tùy tiện.

### Checklist điều tra buffer pool và OS page cache

- [ ] Đã xác định DBMS, phiên bản và đường I/O đang sử dụng.
- [ ] Đã phân biệt page, buffer pool/shared buffers và OS page cache.
- [ ] Đã hiểu cache hit/miss của counter đang đo thuộc tầng nào.
- [ ] Đã lấy delta counter theo cửa sổ thời gian.
- [ ] Đã đo logical reads, physical I/O và storage latency.
- [ ] Đã xác định working set, page nóng và workload scan lớn.
- [ ] Đã theo dõi dirty pages, flush, checkpoint và log generation.
- [ ] Đã kiểm tra RAM available, swap, reclaim và memory grants.
- [ ] Đã phân biệt buffer cache với query execution memory.
- [ ] Đã kiểm tra execution plan và lượng dữ liệu truy vấn thực sự đọc.
- [ ] Đã so sánh warm-cache/cold-cache với điều kiện chuẩn bị rõ ràng.
- [ ] Đã đo lại toàn workload và kiểm tra tác động phụ sau điều chỉnh.

Buffer pool, shared buffers và OS page cache là các lớp bộ đệm có vai trò khác nhau trong đường đọc/ghi dữ liệu. DBMS dùng cache riêng để quản lý page theo ngữ nghĩa transaction và lưu trữ; hệ điều hành có thể cache file data ở tầng filesystem tùy cơ chế I/O. Hit ratio chỉ là một tín hiệu, cần kết hợp logical reads, physical I/O, working set, dirty pages, memory pressure và execution plan. Tối ưu hiệu năng phải xác định đúng tầng gây chậm, giảm công việc truy cập dữ liệu khi cần, phân bổ RAM có headroom và kiểm chứng bằng workload có thể lặp lại.
