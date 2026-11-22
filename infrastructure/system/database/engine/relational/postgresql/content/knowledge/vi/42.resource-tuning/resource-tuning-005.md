# effective_cache_size và giả định của bộ lập kế hoạch PostgreSQL

`effective_cache_size` là một tham số cấu hình planner dùng để ước lượng lượng cache dữ liệu có thể sẵn sàng cho một query. PostgreSQL dùng giả định này khi ước lượng chi phí truy cập dữ liệu, đặc biệt khi so sánh index scan với sequential scan.

Điểm quan trọng nhất: **`effective_cache_size` không cấp phát bộ nhớ, không tạo cache và không buộc PostgreSQL giữ dữ liệu trong RAM**. Nó chỉ thay đổi giả định của bộ lập kế hoạch về khả năng dữ liệu đã có trong cache.

Nếu đặt quá thấp, planner có thể đánh giá index access đắt hơn thực tế và thiên về sequential scan trong một số trường hợp. Nếu đặt quá cao, planner có thể đánh giá index access rẻ hơn khả năng cache thực tế và chọn kế hoạch có nhiều random reads. Vì vậy, cần đặt giá trị dựa trên RAM, `shared_buffers`, OS page cache, workload đồng thời và bằng chứng từ query plans.

Bài **“effective_cache_size và giả định của bộ lập kế hoạch”**, thuộc chương **Tối ưu tài nguyên** của module **Database Engine Relational PostgreSQL**, trình bày:

- Vai trò của `effective_cache_size` trong cost estimation.
- Khác biệt giữa planner cache assumption, `shared_buffers` và OS page cache.
- Cách cache assumption ảnh hưởng tới index scan và sequential scan.
- Quan hệ với `random_page_cost`, `seq_page_cost`, `work_mem` và các setting liên quan.
- Cách ước lượng cache có thể dùng cho PostgreSQL.
- Cách kiểm chứng bằng `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)` và statistics.
- Quy trình điều chỉnh, đo lường và tránh tuning dựa trên một query đơn lẻ.

> **Cách nhớ:** `shared_buffers` là bộ nhớ PostgreSQL thực sự cấp phát; OS page cache là cache do hệ điều hành quản lý; `effective_cache_size` là giả định planner dùng để tính cost. Ba khái niệm có liên quan nhưng không thể thay thế nhau.

---

## 1. Planner cần ước lượng điều gì?

Trước khi thực thi query, PostgreSQL phân tích SQL, xem xét schema, statistics và các phương án truy cập dữ liệu. Query planner tạo các candidate plans rồi chọn kế hoạch có estimated cost thấp nhất theo cost model.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 420;
~~~

Planner có thể cân nhắc:

- Sequential scan toàn bộ bảng.
- Index scan trên index của `customer_id`.
- Bitmap index scan kết hợp bitmap heap scan.
- Index-only scan nếu index chứa đủ dữ liệu và visibility map cho phép.

Để chọn, planner phải ước lượng số rows phù hợp, số pages cần truy cập, chi phí CPU và khả năng các pages đã nằm trong cache.

`effective_cache_size` tham gia vào giả định về cache khi ước lượng chi phí index access.

## 2. effective_cache_size là gì?

`effective_cache_size` đặt **giả định về kích thước disk cache có thể dùng cho một query** theo góc nhìn của planner.

Tham số này giúp planner ước lượng xác suất các pages cần thiết đã có trong cache và do đó ước lượng chi phí đọc dữ liệu qua index.

- Giá trị cao hơn thường làm index scans có vẻ hấp dẫn hơn.
- Giá trị thấp hơn thường khiến sequential scans có vẻ hấp dẫn hơn.
- Tác động là trên estimated costs và lựa chọn plan.
- Giá trị không làm thay đổi lượng RAM PostgreSQL thực sự cấp phát.

Kiểm tra giá trị hiện tại:

~~~sql
SHOW effective_cache_size;
~~~

Có thể xem thêm metadata:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name = 'effective_cache_size';
~~~

`setting` là giá trị nội bộ theo đơn vị được hiển thị trong cột `unit`. Dùng `SHOW` hoặc `pg_settings` để xem cấu hình đang có hiệu lực thay vì suy đoán từ file cấu hình.

## 3. Đây là planner assumption, không phải cache thật

Giả sử cấu hình:

~~~text
shared_buffers = 8GB
effective_cache_size = 32GB
~~~

Điều đó không có nghĩa PostgreSQL đã cấp phát 32GB shared memory.

Nó có nghĩa planner được yêu cầu tính cost với giả định khoảng cache có thể sử dụng ở mức 32GB, dựa trên cả shared buffers và phần OS cache có thể phục vụ dữ liệu PostgreSQL.

Nếu hệ thống thực tế chỉ có ít memory khả dụng, setting cao có thể khiến planner lạc quan quá mức. Ngược lại, nếu có lượng cache khả dụng lớn nhưng setting quá thấp, planner có thể đánh giá index access quá bi quan.

## 4. Phân biệt ba lớp bộ nhớ/cache

| Thành phần | Ai quản lý? | Vai trò |
|---|---|---|
| `shared_buffers` | PostgreSQL | Shared buffer pool thực tế cho database pages |
| OS page cache | Hệ điều hành | Cache filesystem data, có thể phục vụ file reads |
| `effective_cache_size` | Planner configuration | Giả định tổng thể về cache có thể sẵn sàng khi tính cost |

PostgreSQL thường dùng cả shared buffers và OS page cache trong hoạt động đọc dữ liệu. Một page có thể có mặt ở nhiều lớp cache; vì vậy không cộng các con số một cách máy móc rồi coi đó là dung lượng độc lập hoàn toàn.

### 4.1. shared_buffers

`shared_buffers` là vùng shared memory PostgreSQL cấp phát để cache data pages.

~~~sql
SHOW shared_buffers;
~~~

Nó ảnh hưởng trực tiếp tới memory allocation của PostgreSQL và thường cần restart khi thay đổi.

### 4.2. OS page cache

Kernel có thể giữ nội dung file database trong page cache. PostgreSQL yêu cầu đọc file; hệ điều hành có thể phục vụ từ RAM thay vì storage device.

Dung lượng cache thực tế thay đổi theo:

- Memory còn trống.
- Workload của PostgreSQL.
- Các process khác trên host.
- File cache của những ứng dụng khác.
- Memory pressure và kernel reclaim.
- Container/VM memory limits.

Không có một con số OS cache cố định cho toàn bộ vòng đời server.

### 4.3. effective_cache_size

`effective_cache_size` không giữ page và không tạo reservation. Nó là một input của planner cost model.

Thay đổi setting không làm cache nóng lên hoặc giải phóng RAM. Nó cũng không ngăn hệ điều hành reclaim page cache.

## 5. Vì sao planner cần giả định về cache?

Index scan thường phải truy cập index pages và sau đó truy cập heap pages tương ứng với các row được tìm thấy.

Nếu các pages đã có trong cache, chi phí truy cập thấp hơn so với việc phải đọc từ storage.

Nếu cache nhỏ hoặc working set lớn hơn cache, nhiều random reads có thể phải đi xuống storage và trở nên đắt hơn.

Planner không biết chính xác mọi page sẽ có mặt trong cache ở thời điểm query chạy. `effective_cache_size` cung cấp một giả định để cost model ước lượng số page fetch có thể phải thực hiện.

## 6. effective_cache_size và index scan

Với query chọn lọc:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 420;
~~~

Nếu chỉ một tỷ lệ nhỏ rows phù hợp và index phù hợp tồn tại, index scan có thể tránh đọc toàn bộ heap.

Khi planner giả định cache lớn hơn, việc đọc index/heap pages có thể được đánh giá rẻ hơn. Vì vậy index scan có thể trở thành phương án được chọn.

Điều này không bảo đảm index scan luôn tốt hơn. Nếu query cần nhiều rows hoặc các heap pages phân tán rộng, sequential scan có thể vẫn rẻ hơn.

## 7. effective_cache_size và sequential scan

Sequential scan đọc các pages của relation theo thứ tự. Với query cần phần lớn bảng, đọc tuần tự thường hiệu quả hơn việc đi qua index rồi fetch nhiều heap pages rời rạc.

Một giá trị `effective_cache_size` cao không ép planner dùng index scan. Planner vẫn so sánh tổng chi phí của các candidate plans.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE created_at >= DATE '2024-01-01';
~~~

Nếu phần lớn bảng đáp ứng điều kiện, sequential scan có thể hợp lý ngay cả khi cache lớn.

## 8. Index scan, bitmap scan và index-only scan

| Plan type | Cách truy cập | Yếu tố cần xét |
|---|---|---|
| Sequential scan | Đọc heap theo thứ tự | Tỷ lệ rows cần đọc, table size, sequential I/O |
| Index scan | Dùng index rồi fetch heap rows | Selectivity, heap locality, cache và random I/O |
| Bitmap heap scan | Gom tuple locations rồi đọc heap pages theo bitmap | Số heap pages cần truy cập, tính locality |
| Index-only scan | Đọc dữ liệu từ index nếu đủ columns và visibility cho phép | Index coverage, visibility map, heap fetches |

`effective_cache_size` tham gia vào cost estimation, nhưng không thay thế các yếu tố như selectivity, correlation, index definition hoặc visibility map.

## 9. Cache assumption và random_page_cost

`random_page_cost` là cost parameter mô tả chi phí tương đối của random page access so với đơn vị cost chuẩn.

~~~sql
SHOW random_page_cost;
SHOW seq_page_cost;
~~~

Giá trị `random_page_cost` thấp hơn thường làm index access hấp dẫn hơn; giá trị cao hơn làm random reads có vẻ đắt hơn.

`effective_cache_size` và `random_page_cost` có liên quan nhưng mô tả hai giả định khác nhau:

- `effective_cache_size`: mức cache có thể sẵn sàng.
- `random_page_cost`: chi phí tương đối của random page access.

Không giảm `random_page_cost` chỉ để ép index scan, đồng thời cũng không tăng `effective_cache_size` chỉ để chữa một query chậm. Cần kiểm chứng cả hai bằng workload thực tế.

## 10. Cost units không phải milliseconds

Planner hiển thị estimated costs trong các đơn vị tương đối:

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 420;
~~~

Ví dụ:

~~~text
Index Scan ... (cost=0.42..18.50 rows=12 width=...)
~~~

Các con số cost không phải milliseconds và không thể so trực tiếp với wall-clock execution time.

Planner so sánh các candidate plans trong cùng cost model. Việc scale các cost parameters có thể làm thay đổi lựa chọn plan, nhưng không tự làm CPU hoặc storage nhanh hơn.

## 11. effective_cache_size không phải work_mem

Hai setting phục vụ mục đích khác nhau:

| Setting | Mục đích | Có cấp phát memory? |
|---|---|---|
| `effective_cache_size` | Planner giả định cache | Không |
| `shared_buffers` | Cache pages trong PostgreSQL | Có |
| `work_mem` | Workspace cho sort/hash và một số operations | Có thể cấp phát khi operation chạy |
| `maintenance_work_mem` | Workspace cho maintenance operations | Có |
| `temp_buffers` | Buffer cho temporary tables của session | Có |

Tăng `effective_cache_size` không giúp một sort lớn tránh temporary files. Nếu query spill do sort/hash, hãy xem `work_mem` và query plan.

## 12. effective_cache_size không phải shared_buffers

Một số hiểu nhầm phổ biến:

- Đặt `effective_cache_size = 32GB` không cấp 32GB RAM cho PostgreSQL.
- Đặt `effective_cache_size` cao không làm tăng số pages trong shared buffers.
- Đặt `effective_cache_size` thấp không giới hạn cache thực tế.
- Thay đổi setting không làm sạch cache hiện tại.
- Setting không phải quota memory cho mỗi query.

`shared_buffers` là memory allocation; `effective_cache_size` là planner assumption.

## 13. Ước lượng giá trị phù hợp

Không có một giá trị phù hợp cho mọi máy chủ. Khi ước lượng, xem xét:

1. Tổng RAM thực sự khả dụng cho host/VM/container.
2. `shared_buffers`.
3. Phần OS page cache có thể phục vụ PostgreSQL.
4. Memory cần cho backend processes và workload đồng thời.
5. Các dịch vụ khác chạy trên cùng host.
6. Working set của database.
7. Số query đồng thời truy cập các tập dữ liệu khác nhau.
8. Memory limits và cgroup/container constraints.
9. Cache behavior quan sát được trong workload thực tế.

Tài liệu PostgreSQL khuyên xem xét cả shared buffers và phần kernel disk cache có thể dùng cho database files, đồng thời tính đến các query đồng thời phải chia sẻ cache.

### 13.1. Không dùng một tỷ lệ RAM cố định

Các công thức kiểu “effective_cache_size luôn bằng 75% RAM” chỉ có thể là điểm bắt đầu trong một số môi trường, không phải quy tắc chung.

Ví dụ hai host đều có 64GB RAM nhưng:

- Host A chỉ chạy PostgreSQL.
- Host B còn chạy application servers, agents và batch jobs.
- Host C bị giới hạn memory bởi container.
- Host D có working set lớn hơn RAM nhiều lần.

Cache assumption phù hợp của từng host có thể khác nhau.

## 14. Ví dụ lập ngân sách cache

Giả sử một host có 64GB RAM. PostgreSQL dùng `shared_buffers` 16GB. OS còn cần memory cho kernel, backend processes, connection overhead và các ứng dụng khác.

Không nên tự động đặt `effective_cache_size` bằng 64GB. Hãy ước lượng phần cache có thể thực sự phục vụ database workload, tránh tính trùng pages và tính tới các query đồng thời.

Một giá trị thử nghiệm có thể được chọn sau khi xem memory pressure và cache behavior. Đây là giả định để planner dùng, không phải cam kết OS sẽ giữ đủ dung lượng đó.

### 14.1. Workload đồng thời

Nếu một query làm việc trên bảng A và query khác làm việc trên bảng B, cả hai cùng cần cache. Planner setting cần phản ánh khả năng cache chia sẻ giữa những query dự kiến chạy đồng thời.

Không tính cache như thể mọi query có toàn bộ RAM dành riêng.

## 15. Working set

**Working set** là tập dữ liệu mà workload thường truy cập trong một khoảng thời gian có ý nghĩa.

Ví dụ:

- OLTP: các customer/order rows gần đây và index thường xuyên dùng.
- Reporting: partition của một tháng/quý.
- Analytics: nhiều bảng lớn, scans rộng.
- Mixed workload: hot rows cho giao dịch cùng data ranges cho báo cáo.

Nếu working set vừa với cache khả dụng, index access có thể có chi phí thấp hơn nhiều so với trường hợp working set lớn hơn cache.

`effective_cache_size` nên phản ánh giả định hợp lý về cache mà workload có thể tận dụng, không chỉ dung lượng database trên disk.

## 16. Cache hit ratio không trực tiếp cho ra effective_cache_size

Có thể xem database counters:

~~~sql
SELECT
    datname,
    blks_hit,
    blks_read,
    round(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_percent
FROM pg_stat_database
WHERE datname = current_database();
~~~

Hit ratio cao cho biết nhiều block requests được phục vụ từ shared buffers. Nó không cho biết toàn bộ OS page cache hoặc lượng cache có thể dùng cho một query.

Hit ratio thấp cũng không tự chứng minh `effective_cache_size` đặt sai. Workload sequential scan lớn có thể làm nhiều blocks được đọc một lần.

## 17. Dùng pg_statio để quan sát theo relation

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_tables
ORDER BY heap_blks_read + idx_blks_read DESC
LIMIT 30;
~~~

View này giúp tìm relation có nhiều block reads/hits. Nó không cho biết chính xác cache size mà planner nên giả định.

Đọc cùng `pg_stat_user_tables`, `pg_stat_user_indexes`, query plans và OS metrics.

## 18. pg_buffercache

Extension `pg_buffercache` có thể quan sát pages hiện diện trong PostgreSQL shared buffer cache.

Sau khi cài extension trong database phù hợp:

~~~sql
CREATE EXTENSION pg_buffercache;
~~~

Ví dụ tổng quan:

~~~sql
SELECT
    count(*) AS buffer_count,
    count(*) FILTER (WHERE relfilenode IS NOT NULL) AS relation_buffers
FROM pg_buffercache;
~~~

Có thể nhóm theo database/relation để xem buffer distribution. Schema và quyền cần kiểm tra theo version/extension.

`pg_buffercache` chỉ quan sát PostgreSQL shared buffers. Nó không hiển thị toàn bộ OS page cache và không trực tiếp tính ra giá trị `effective_cache_size`.

## 19. OS memory và page cache

Cần theo dõi memory ở cấp hệ điều hành:

- RAM available/free.
- Page cache.
- Swap activity.
- Major/minor page faults.
- Memory pressure.
- Process resident memory.
- Container memory limit/usage.
- Storage read latency và throughput.

Trên Linux có thể tham khảo `free`, `vmstat`, `iostat` và metrics từ node exporter. Trên Windows dùng Performance Monitor hoặc công cụ monitoring tương ứng.

Không lấy một snapshot memory tại một thời điểm rồi xem đó là cache capacity cố định. Quan sát qua peak workload và batch windows.

## 20. EXPLAIN để xem planner lựa chọn plan

Dùng `EXPLAIN` để xem plan mà không thực thi query:

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE customer_id = 420;
~~~

Quan sát:

- Node type: Seq Scan, Index Scan, Bitmap Heap Scan, Index Only Scan.
- Estimated rows.
- Estimated cost.
- Filter và Index Cond.
- Join strategy nếu query nhiều bảng.

`effective_cache_size` có thể làm estimated cost của các phương án thay đổi và dẫn tới plan khác.

## 21. EXPLAIN ANALYZE, BUFFERS

Để xem execution thực tế trong môi trường kiểm soát:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 420;
~~~

Các thông tin hữu ích:

- Estimated rows và actual rows.
- Planning time và execution time.
- Shared hit/read blocks.
- Local/temp blocks nếu có.
- Heap fetches đối với index-only scan.
- Actual loops và rows per loop.

`BUFFERS` cho biết buffer activity ở PostgreSQL. `shared read` nghĩa là block phải được đọc vào shared buffers; OS page cache vẫn có thể phục vụ request đó.

`EXPLAIN ANALYZE` thực sự chạy query. Dùng cẩn trọng với DML, functions có side effects và queries nặng. Thử trên staging hoặc dữ liệu an toàn trước.

## 22. So sánh estimated rows với actual rows

Planner dựa trên statistics để ước lượng số rows. Nếu estimated rows khác xa actual rows, nguyên nhân có thể là:

- Statistics cũ.
- Data distribution skew.
- Correlation giữa columns.
- Predicate phức tạp.
- Expression chưa có statistics phù hợp.
- Parameter-sensitive workload.

Trước khi quy lỗi cho `effective_cache_size`, kiểm tra estimates và chạy ANALYZE khi phù hợp.

Một cache assumption tốt không thể sửa một cardinality estimate sai nghiêm trọng.

## 23. Statistics và ANALYZE

Query planner dùng column statistics để ước lượng selectivity.

~~~sql
ANALYZE public.orders;
~~~

Có thể xem một số statistics trong catalog:

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders';
~~~

Nếu table thay đổi lớn mà statistics không được cập nhật, planner có thể chọn plan không phù hợp dù `effective_cache_size` được đặt hợp lý.

## 24. Correlation và heap locality

Index scan có thể nhanh khi các rows được tìm thấy gần nhau trên heap hoặc index order tương quan với physical row order.

Statistics column correlation giúp planner ước lượng locality của index access.

Nếu index entries dẫn tới heap pages phân tán, index scan có thể gây nhiều random accesses. Nếu data có locality tốt, chi phí có thể thấp hơn.

`effective_cache_size` chỉ là một yếu tố trong cost estimation; không thay thế correlation statistics.

## 25. Selectivity và số rows cần đọc

Index scan thường hấp dẫn hơn khi predicate chọn lọc cao, nghĩa là chỉ một phần nhỏ rows phù hợp.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE order_id = 12345;
~~~

Nếu `order_id` là primary key, query thường chỉ cần một row.

Ngược lại:

~~~sql
SELECT *
FROM orders
WHERE status = 'active';
~~~

Nếu 90% rows có status active, sequential scan có thể hiệu quả hơn việc dùng index rồi fetch hầu hết heap rows.

Tỷ lệ rows cần đọc thường quan trọng hơn việc chỉ nhìn cache setting.

## 26. Cache size và index-only scan

Index-only scan có thể tránh heap access nếu:

- Index chứa mọi column query cần.
- Visibility map cho phép PostgreSQL xác nhận pages tương ứng all-visible.
- Plan thực sự chọn Index Only Scan.

Ví dụ:

~~~sql
CREATE INDEX orders_customer_created_idx
ON public.orders (customer_id)
INCLUDE (created_at);
~~~

Query:

~~~sql
SELECT customer_id, created_at
FROM public.orders
WHERE customer_id = 420;
~~~

Dù cache lớn, index-only scan vẫn phụ thuộc visibility map và index coverage. Nếu heap fetches nhiều, lợi ích có thể giảm.

## 27. Bitmap heap scan

Bitmap scan gom các tuple locations từ index thành bitmap, sau đó truy cập heap pages theo thứ tự phù hợp hơn.

Nó thường được cân nhắc khi query chọn lọc vừa phải: nhiều rows cần lấy nhưng vẫn ít hơn toàn bảng.

Planner có thể chọn giữa index scan, bitmap scan và sequential scan dựa trên selectivity, page fetch estimate, cost parameters và cache assumption.

Không cố ép một plan type duy nhất cho mọi query trên cùng bảng.

## 28. effective_cache_size và random_page_cost cùng nhau

Hai setting có thể cùng ảnh hưởng tới lựa chọn index access.

| Thay đổi | Xu hướng cost model |
|---|---|
| Tăng `effective_cache_size` | Giả định cache nhiều hơn; index access có thể rẻ hơn |
| Giảm `effective_cache_size` | Giả định cache ít hơn; index access có thể đắt hơn |
| Giảm `random_page_cost` | Random reads có vẻ rẻ hơn |
| Tăng `random_page_cost` | Random reads có vẻ đắt hơn |

Đây là xu hướng, không phải quy tắc đảm bảo plan sẽ đổi. Các yếu tố khác có thể chi phối kết quả.

Điều chỉnh một biến tại một thời điểm để hiểu tác động, sau đó thử workload đại diện.

## 29. seq_page_cost

`seq_page_cost` là cost tương đối của sequential page fetch. Giá trị hiện tại:

~~~sql
SHOW seq_page_cost;
~~~

Không cần thay đổi chỉ vì sequential scan xuất hiện. Sequential scan thường là plan tối ưu khi cần đọc phần lớn relation.

Cost parameters là đơn vị tương đối. Điều chỉnh chúng cần dựa trên đặc tính storage và workload, không phải một con số tuyệt đối.

## 30. effective_io_concurrency

`effective_io_concurrency` điều khiển mức I/O concurrency mà PostgreSQL có thể dùng trong một số bitmap heap scan và các paths hỗ trợ.

~~~sql
SHOW effective_io_concurrency;
~~~

Setting này khác `effective_cache_size`:

- Một bên mô tả khả năng cache theo giả định planner.
- Một bên liên quan đến concurrency của một số hoạt động I/O khi thực thi.

Availability và tác động phụ thuộc OS, storage và PostgreSQL version.

## 31. Tuning theo từng loại workload

| Workload | Đặc điểm | Điều cần quan sát |
|---|---|---|
| OLTP | Nhiều query nhỏ, truy cập hot rows | Working set, index access, shared/OS cache |
| Reporting | Scan và aggregate lớn | Sequential I/O, temp spills, query plans |
| Data warehouse | Working set lớn, parallel scans | Memory pressure, storage throughput, cache churn |
| Mixed workload | OLTP cùng reporting | Cache contention, concurrency, query latency |
| Batch | Ghi/đọc theo đợt | Peak memory, cache warm/cold, I/O burst |

Một giá trị cache assumption phù hợp với OLTP không nhất thiết tối ưu cho analytics chạy đồng thời trên cùng host.

## 32. Tuning sai: đặt quá thấp

Khi `effective_cache_size` thấp hơn khả năng cache thực tế, planner có thể đánh giá index access đắt hơn.

Dấu hiệu có thể gặp:

- Query chọn sequential scan dù predicate rất chọn lọc.
- Estimated index cost cao.
- Index phù hợp tồn tại nhưng không được chọn trong một số query.
- Plan thay đổi sau khi tăng setting thử nghiệm.

Tuy nhiên, cũng cần loại trừ stale statistics, thiếu index, predicate không sargable, data type casts và query cần phần lớn bảng.

## 33. Tuning sai: đặt quá cao

Khi setting cao hơn cache có thể phục vụ, planner có thể quá lạc quan về index access.

Dấu hiệu có thể gặp:

- Index scan được chọn nhưng runtime có nhiều block reads.
- Random I/O tăng khi workload chạy đồng thời.
- Query chậm hơn so với sequential/bitmap alternative trong thử nghiệm.
- OS memory pressure hoặc storage latency tăng.

Không kết luận chỉ từ một query. So sánh nhiều lần, workload đồng thời và điều kiện cache tương tự production.

## 34. Không dùng effective_cache_size để chữa mọi query chậm

Query chậm có thể do:

- Lock waits.
- CPU saturation.
- Network latency.
- Bad join order.
- Cardinality estimates sai.
- Thiếu index hoặc index không phù hợp.
- Temp files do sort/hash.
- Storage latency.
- Connection pool saturation.
- Transaction quá dài.

`effective_cache_size` chỉ ảnh hưởng một phần của planner cost model. Xác định bottleneck trước khi thay đổi.

## 35. Kiểm tra cấu hình planner hiện tại

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
    'effective_cache_size',
    'shared_buffers',
    'work_mem',
    'maintenance_work_mem',
    'random_page_cost',
    'seq_page_cost',
    'effective_io_concurrency'
)
ORDER BY name;
~~~

Query này giúp xem giá trị hiện hành, đơn vị và nguồn cấu hình.

`source` có thể cho biết setting đến từ default, configuration file, command line, database/role setting hoặc session override tùy trường hợp.

## 36. Thử nghiệm setting theo session

Nếu setting cho phép thay đổi ở session context, có thể thử trong session riêng:

~~~sql
SET effective_cache_size = '24GB';

EXPLAIN
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 420;
~~~

Sau đó thử một giá trị khác:

~~~sql
SET effective_cache_size = '40GB';

EXPLAIN
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 420;
~~~

So sánh estimated costs và plan nodes. Dùng lệnh `RESET effective_cache_size` để trở lại giá trị mặc định của session hoặc đóng session thử nghiệm.

Đây là thử nghiệm planner, không phải benchmark runtime. Muốn đánh giá performance phải chạy workload có kiểm soát với điều kiện tương đương.

## 37. Thay đổi cấu hình lâu dài

Có thể cấu hình qua `postgresql.conf` hoặc cơ chế quản trị phù hợp:

~~~text
effective_cache_size = 32GB
~~~

Sau thay đổi, kiểm tra setting đang có hiệu lực:

~~~sql
SHOW effective_cache_size;
~~~

Context của setting quyết định có cần restart, reload hay chỉ áp dụng ở session. Kiểm tra `pg_settings.context` thay vì mặc định rằng mọi memory parameter đều cần restart.

Một số môi trường quản lý cấu hình bằng operator/config management; thay đổi trực tiếp file có thể bị automation ghi đè.

## 38. Đo lường trước và sau tuning

Một lần thử nghiệm nên ghi lại:

- Giá trị setting cũ và mới.
- PostgreSQL major version.
- RAM/VM/container limits.
- `shared_buffers`.
- Workload và thời gian lấy mẫu.
- Query plans.
- Estimated/actual rows.
- Execution time.
- Shared hit/read blocks.
- Temp blocks.
- CPU, memory pressure và storage latency.
- Số query đồng thời.

Không so sánh hai lần chạy nếu một lần cache nóng và lần kia cache lạnh mà không ghi nhận điều kiện đó.

## 39. Giữ điều kiện benchmark nhất quán

Khi so sánh plan/runtime:

1. Dùng cùng dataset và schema.
2. Bảo đảm statistics không thay đổi giữa hai lần.
3. Dùng cùng parameter values.
4. Ghi nhận concurrent workload.
5. So sánh cache warm/cold một cách có chủ đích.
6. Chạy đủ lần để tránh kết luận từ một outlier.
7. Đo cả latency và resource consumption.
8. Kiểm tra query plans sau mỗi lần thay đổi.

Không xóa cache trên production chỉ để tạo cold-cache benchmark.

## 40. Dùng pg_stat_statements chọn query đại diện

Nếu extension `pg_stat_statements` được cài, có thể tìm query có total execution time cao:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Tên cột có thể khác trên các PostgreSQL versions cũ hơn. Kiểm tra extension version/schema trước khi dùng query.

Chọn một nhóm query đại diện, không tuning theo một query hiếm hoặc query không quan trọng với workload.

## 41. Kết hợp EXPLAIN với statistics

Một quy trình điều tra:

1. Dùng `pg_stat_statements` tìm query tốn thời gian.
2. Lấy SQL và parameter values phù hợp.
3. Chạy `EXPLAIN` để xem plan.
4. Chạy `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường an toàn.
5. So estimated rows với actual rows.
6. Xem shared hit/read và temp blocks.
7. Kiểm tra index definitions và table statistics.
8. Thử thay đổi `effective_cache_size` theo session.
9. So sánh plans và runtime trong điều kiện tương đương.
10. Chỉ triển khai khi workload tổng thể có lợi.

## 42. Khi nào nên chạy ANALYZE?

Nếu table data distribution thay đổi đáng kể, chạy ANALYZE để planner có statistics mới:

~~~sql
ANALYZE public.orders;
~~~

Đặc biệt sau bulk load, partition attach/load hoặc thay đổi dữ liệu lớn, planner estimates có thể cần cập nhật.

Đừng cố bù statistics lỗi bằng cách tăng cache assumption. Hai yếu tố giải quyết hai phần khác nhau của cost estimation.

## 43. Parameterized queries và generic plans

Prepared statements có thể dùng custom plan hoặc generic plan tùy cách PostgreSQL quyết định.

Một generic plan không biết chính xác parameter value ở mỗi lần thực thi như custom plan. Nếu selectivity thay đổi mạnh theo parameter, plan có thể không tối ưu cho mọi giá trị.

`effective_cache_size` không tự giải quyết parameter sensitivity. Khi plan thay đổi giữa literal và prepared execution, hãy kiểm tra plan caching, parameter distribution và `EXPLAIN EXECUTE`.

## 44. Partitioning và cache assumption

Với partitioned tables, partition pruning có thể giảm đáng kể số relations/pages cần đọc.

Trước khi thay đổi `effective_cache_size`, kiểm tra:

- Partition pruning có hoạt động?
- Query predicate có cho phép pruning?
- Statistics của partitions có cập nhật?
- Plan có scan quá nhiều partitions?
- Partition size và working set ra sao?

Nếu planner không prune được partitions, vấn đề có thể nằm ở query predicate hoặc plan-time/runtime pruning chứ không phải cache size.

## 45. Index design vẫn quan trọng

Một cache assumption lớn không thể làm index không phù hợp trở nên tốt.

Xem xét:

- Leading columns của multicolumn index.
- Predicate operators.
- Data type và implicit casts.
- Partial index predicate.
- INCLUDE columns cho index-only scan.
- Selectivity và correlation.
- Index bloat và maintenance cost.

Nếu query cần 70% bảng, một index scan có thể đắt hơn sequential scan dù cache lớn.

## 46. Cache pressure do nhiều query đồng thời

Planner assumption phải tính tới việc nhiều queries chia sẻ cache.

Ví dụ một query OLTP liên tục truy cập hot index pages, trong khi một report scan bảng lớn. Report có thể làm cache churn và đẩy hot pages ra khỏi cache.

Nếu chỉ đặt cache assumption dựa trên dung lượng RAM mà bỏ qua concurrency, planner có thể lạc quan quá mức.

Theo dõi:

- Query concurrency.
- Buffer hit/read rates.
- OS memory pressure.
- Storage latency.
- Workload mix.
- Cache warm-up sau batch windows.

## 47. Memory limits trong container/VM

Trong môi trường container:

- Host có thể có nhiều RAM nhưng container bị giới hạn thấp hơn.
- PostgreSQL có thể thấy/được cấp memory theo cgroup limits.
- OS page cache có thể chịu giới hạn memory cgroup.
- OOM killer có thể chấm dứt process khi vượt limit.

Đừng dùng tổng RAM host làm cache assumption nếu PostgreSQL chỉ có một phần memory đó.

Đo memory limit và usage trong đúng namespace/container, sau đó xác định phần cache thực tế có thể phục vụ database.

## 48. effective_cache_size và parallel query

Parallel workers có thể làm query đọc dữ liệu nhanh hơn nhờ dùng nhiều CPU/I/O paths, nhưng cũng tăng cạnh tranh tài nguyên.

`effective_cache_size` không cấp memory riêng cho từng worker và không điều khiển số parallel workers.

Khi đánh giá parallel plans, xem:

- `max_parallel_workers_per_gather`.
- `max_parallel_workers`.
- `max_worker_processes`.
- CPU saturation.
- I/O throughput.
- Cache contention.
- Worker availability.

Không tăng cache assumption để thay thế tuning parallelism.

## 49. Các câu hỏi cần trả lời trước khi tuning

- PostgreSQL có thực sự chọn plan không phù hợp?
- Query nào bị ảnh hưởng?
- Estimated rows có gần actual rows?
- Index có phù hợp predicate?
- Cache hiện tại gồm shared buffers và OS page cache ở mức nào?
- Workload đồng thời ra sao?
- `random_page_cost` và `seq_page_cost` đang đặt thế nào?
- Storage là local SSD, network storage hay cloud volume?
- Memory có bị pressure/swap/OOM?
- Thay đổi có cải thiện workload tổng thể không?

Nếu chưa có bằng chứng về plan/cost mismatch, giữ nguyên setting và thu thập thêm dữ liệu.

## 50. Troubleshooting: planner chọn sequential scan

Điều tra theo thứ tự:

1. Xem `EXPLAIN` và estimated rows.
2. Kiểm tra query có cần phần lớn bảng không.
3. Xác minh index phù hợp và predicate có dùng được index.
4. Chạy ANALYZE nếu statistics cũ.
5. Xem `random_page_cost`, `seq_page_cost`.
6. Ước lượng cache khả dụng.
7. Thử `effective_cache_size` theo session.
8. So sánh candidate plans và runtime trong môi trường an toàn.

Không dùng `enable_seqscan = off` như giải pháp production mặc định. Planner switches chỉ hữu ích cho chẩn đoán plan alternatives.

## 51. Troubleshooting: planner chọn index scan nhưng query chậm

Kiểm tra:

- Actual rows có lớn hơn estimate?
- Heap fetches có nhiều?
- Shared read blocks có cao?
- Index scan có random I/O nhiều?
- Working set có vượt cache?
- Cache assumption có quá lạc quan?
- Query có thể dùng bitmap hoặc sequential scan hiệu quả hơn?
- Storage latency và concurrency ra sao?

Nếu cần thử, so sánh plan alternatives trong staging và thay đổi từng cost setting riêng biệt.

## 52. Troubleshooting: tăng effective_cache_size nhưng plan không đổi

Điều này hoàn toàn có thể xảy ra.

Nguyên nhân:

- Cost difference vẫn nghiêng rõ về cùng plan.
- Query selectivity quá cao/thấp để setting làm đổi quyết định.
- Cardinality estimate chi phối mạnh hơn cache assumption.
- Planner không có index phù hợp.
- Query dùng một plan node khác không nhạy với setting.
- Giá trị setting mới chưa có hiệu lực trong session.
- Query đang chạy với prepared/generic plan.

Xác minh bằng `SHOW effective_cache_size`, `pg_settings` và `EXPLAIN`.

## 53. Những sai lầm thường gặp

### 53.1. effective_cache_size cấp phát RAM

Sai. Đây là planner assumption.

### 53.2. effective_cache_size phải bằng shared_buffers

Sai. Nó có thể tính cả phần OS cache có thể dùng cho database.

### 53.3. effective_cache_size bằng toàn bộ RAM

Không nhất thiết. Cần tính memory cho hệ điều hành, backend, services khác, concurrency và cache overlap.

### 53.4. Giá trị cao luôn tốt hơn

Sai. Quá cao có thể làm planner đánh giá index access quá lạc quan.

### 53.5. Hit ratio thấp nghĩa là setting thấp

Không đủ căn cứ. Hit ratio chỉ quan sát một phần buffer behavior và phụ thuộc workload.

### 53.6. Sequential scan luôn là dấu hiệu thiếu index

Sai. Sequential scan có thể rẻ nhất khi query đọc phần lớn bảng.

### 53.7. Chỉ cần đổi effective_cache_size là query nhanh hơn

Sai. Nó có thể đổi plan, nhưng không thay đổi phần cứng hoặc cache thật.

### 53.8. work_mem và effective_cache_size giống nhau

Sai. Một setting mô tả cache assumption; setting kia điều khiển workspace memory cho operations.

### 53.9. EXPLAIN cost là milliseconds

Sai. Cost units là đơn vị tương đối trong planner.

### 53.10. Tuning một query bảo đảm mọi query tốt hơn

Sai. Một setting planner ảnh hưởng workload rộng hơn; phải kiểm tra query mix.

## 54. Lab: xem cấu hình cache và cost

Trong PostgreSQL lab:

~~~sql
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW random_page_cost;
SHOW seq_page_cost;
SHOW work_mem;
~~~

Xem metadata:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'effective_cache_size',
    'random_page_cost',
    'seq_page_cost',
    'work_mem'
)
ORDER BY name;
~~~

Ghi lại giá trị trước khi thử nghiệm.

## 55. Lab: so sánh plan với hai cache assumptions

Tạo dữ liệu đủ lớn:

~~~sql
CREATE TABLE cache_lab_orders AS
SELECT
    g AS order_id,
    (g % 100000)::integer AS customer_id,
    (g % 10)::integer AS status_id,
    now() - (g % 365) * interval '1 day' AS created_at
FROM generate_series(1, 2000000) AS g;

ALTER TABLE cache_lab_orders
ADD PRIMARY KEY (order_id);

CREATE INDEX cache_lab_customer_idx
ON cache_lab_orders (customer_id);

ANALYZE cache_lab_orders;
~~~

Thử một query chọn lọc:

~~~sql
SET effective_cache_size = '2GB';

EXPLAIN
SELECT *
FROM cache_lab_orders
WHERE customer_id = 420;
~~~

Thử một giả định khác:

~~~sql
SET effective_cache_size = '24GB';

EXPLAIN
SELECT *
FROM cache_lab_orders
WHERE customer_id = 420;
~~~

Ghi lại plan và estimated cost. Plan có thể giống nhau nếu cost difference không đủ để thay đổi lựa chọn.

Sau lab:

~~~sql
RESET effective_cache_size;
~~~

## 56. Lab: so sánh với predicate chọn lọc thấp

Dùng cùng bảng:

~~~sql
EXPLAIN
SELECT *
FROM cache_lab_orders
WHERE status_id = 1;
~~~

Điều kiện này có thể khớp một phần đáng kể rows. So sánh với query theo `customer_id`.

Mục tiêu là quan sát selectivity ảnh hưởng plan ra sao, không phải buộc planner chọn index scan.

## 57. Lab: EXPLAIN ANALYZE và BUFFERS

Trong lab an toàn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM cache_lab_orders
WHERE customer_id = 420;
~~~

Ghi lại estimated rows, actual rows, execution time, shared hit/read blocks và plan node. Nếu có index-only scan, ghi cả heap fetches.

Chạy lại trong điều kiện cache tương tự và so sánh. Không xóa OS cache hoặc shared buffers trên production để tái tạo cache lạnh.

## 58. Lab: theo dõi cache counters theo thời gian

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

Lấy hai mẫu cách nhau một khoảng thời gian, tính delta `blks_read` và `blks_hit`, ghi nhận workload chạy trong khoảng đó.

Tách hoạt động của lab query khỏi workload nền nếu muốn kết quả dễ diễn giải.

## 59. Checklist tuning

**Trước khi thay đổi**

1. Xác định query/workload cần cải thiện.
2. Ghi nhận PostgreSQL version và cấu hình hiện tại.
3. Đo RAM và memory limits.
4. Xem `shared_buffers` và OS page cache.
5. Kiểm tra query plans và row estimates.
6. Kiểm tra statistics và index definitions.
7. Ghi nhận workload concurrency.

**Trong thử nghiệm**

8. Thay đổi setting theo session nếu phù hợp.
9. So sánh estimated costs.
10. Chạy runtime benchmark trong điều kiện an toàn.
11. Ghi nhận buffers, latency, CPU và storage I/O.
12. Kiểm tra query mix khác có bị ảnh hưởng không.

**Khi triển khai**

13. Chọn giá trị dựa trên evidence.
14. Cập nhật qua configuration management.
15. Xác nhận setting có hiệu lực.
16. Theo dõi plan regressions và latency.
17. Có rollback value/runbook.
18. Đánh giá lại khi RAM, workload hoặc topology thay đổi.

## 60. Bài tập thực hành

### Bài 1 — effective_cache_size

Tham số này điều khiển điều gì?

**Gợi ý:** planner assumption về disk cache có thể sẵn sàng cho một query.

### Bài 2 — Memory allocation

Đặt `effective_cache_size = 32GB` có cấp phát 32GB RAM không?

**Gợi ý:** không.

### Bài 3 — shared_buffers

Setting này khác effective_cache_size thế nào?

**Gợi ý:** shared_buffers là cache memory PostgreSQL cấp phát thật.

### Bài 4 — OS page cache

Hệ điều hành tham gia cache database files thế nào?

**Gợi ý:** page cache có thể phục vụ file reads từ RAM.

### Bài 5 — Cache overlap

Vì sao không cộng shared_buffers và OS cache một cách máy móc?

**Gợi ý:** pages có thể được cache ở nhiều lớp và nhiều queries chia sẻ.

### Bài 6 — Planner cost

Planner dùng effective_cache_size để làm gì?

**Gợi ý:** ước lượng chi phí truy cập dữ liệu, đặc biệt index access.

### Bài 7 — Giá trị cao

Giá trị cao hơn thường làm plan nào hấp dẫn hơn?

**Gợi ý:** index scans có thể được đánh giá rẻ hơn.

### Bài 8 — Giá trị thấp

Giá trị thấp có thể khiến planner thiên về plan nào?

**Gợi ý:** sequential scans trong một số trường hợp.

### Bài 9 — Sequential scan

Sequential scan có luôn xấu không?

**Gợi ý:** không; đọc phần lớn bảng thường phù hợp.

### Bài 10 — Index scan

Index scan thường có lợi khi nào?

**Gợi ý:** predicate chọn lọc và cần ít heap rows.

### Bài 11 — Bitmap scan

Bitmap heap scan giải quyết trade-off nào?

**Gợi ý:** gom tuple locations để truy cập heap pages hiệu quả hơn.

### Bài 12 — Index-only scan

Điều kiện nào giúp index-only scan tránh heap fetches?

**Gợi ý:** index có đủ columns và visibility map cho phép.

### Bài 13 — random_page_cost

Setting này mô tả điều gì?

**Gợi ý:** chi phí tương đối của random page access.

### Bài 14 — seq_page_cost

Setting này mô tả điều gì?

**Gợi ý:** chi phí tương đối của sequential page access.

### Bài 15 — Cost units

Estimated cost có phải milliseconds không?

**Gợi ý:** không, là đơn vị tương đối.

### Bài 16 — work_mem

work_mem dùng cho mục đích gì?

**Gợi ý:** workspace cho sort/hash operations và một số executor operations.

### Bài 17 — maintenance_work_mem

Setting này thường phục vụ nhóm hoạt động nào?

**Gợi ý:** maintenance như VACUUM hoặc index creation theo semantics phù hợp.

### Bài 18 — Working set

Working set là gì?

**Gợi ý:** tập dữ liệu workload thường truy cập.

### Bài 19 — Concurrency

Vì sao phải tính query concurrency khi ước lượng cache?

**Gợi ý:** các queries chia sẻ cache khả dụng.

### Bài 20 — Cache hit ratio

Hit ratio có trực tiếp cho biết OS page cache không?

**Gợi ý:** không; nó chủ yếu phản ánh shared buffer hits/reads.

### Bài 21 — pg_buffercache

Extension này quan sát cache nào?

**Gợi ý:** PostgreSQL shared buffers.

### Bài 22 — EXPLAIN

EXPLAIN không ANALYZE có thực thi query không?

**Gợi ý:** không; nó hiển thị planned execution.

### Bài 23 — EXPLAIN ANALYZE

Vì sao cần cẩn trọng với DML?

**Gợi ý:** nó thực sự thực thi statement và có thể gây side effects.

### Bài 24 — BUFFERS

shared read trong EXPLAIN có nhất thiết là physical disk read không?

**Gợi ý:** không; OS page cache có thể phục vụ.

### Bài 25 — Cardinality estimate

Nếu estimated rows sai xa actual rows, nên kiểm tra gì?

**Gợi ý:** ANALYZE, data distribution và planner statistics.

### Bài 26 — Correlation

Correlation ảnh hưởng điều gì?

**Gợi ý:** locality của heap accesses qua index.

### Bài 27 — Selectivity

Query cần phần lớn rows có thường phù hợp index scan không?

**Gợi ý:** không nhất thiết; sequential scan có thể rẻ hơn.

### Bài 28 — effective_io_concurrency

Setting này khác effective_cache_size thế nào?

**Gợi ý:** điều khiển I/O concurrency của một số paths, không phải cache assumption.

### Bài 29 — Container memory

Vì sao không dùng tổng RAM host làm cache assumption trong container?

**Gợi ý:** container có thể bị giới hạn memory riêng.

### Bài 30 — Parallel query

effective_cache_size có cấp memory cho parallel workers không?

**Gợi ý:** không.

### Bài 31 — Setting metadata

View nào hiển thị context/source của GUC?

**Gợi ý:** pg_settings.

### Bài 32 — Session test

Có thể thử cache assumption theo session khi setting cho phép không?

**Gợi ý:** dùng SET rồi so sánh EXPLAIN.

### Bài 33 — Statistics freshness

Vì sao cần ANALYZE trước khi tuning cache assumption?

**Gợi ý:** stale estimates có thể làm plan sai vì nguyên nhân khác.

### Bài 34 — pg_stat_statements

Extension này giúp chọn query nào để benchmark?

**Gợi ý:** query có calls/time/block activity đáng chú ý.

### Bài 35 — Plan regression

Vì sao phải kiểm tra nhiều query sau khi thay setting?

**Gợi ý:** planner setting ảnh hưởng nhiều query khác nhau.

### Bài 36 — Cache pressure

Batch scan lớn có thể ảnh hưởng OLTP cache thế nào?

**Gợi ý:** gây cache churn và đẩy hot pages ra.

### Bài 37 — Tuning quá cao

Rủi ro chính là gì?

**Gợi ý:** planner đánh giá index access quá lạc quan.

### Bài 38 — Tuning quá thấp

Rủi ro chính là gì?

**Gợi ý:** planner đánh giá index access quá bi quan.

### Bài 39 — Benchmark

Vì sao cần cùng điều kiện cache/concurrency khi so sánh?

**Gợi ý:** tránh kết luận sai do cache warm/cold hoặc workload khác nhau.

### Bài 40 — Quyết định tuning

Nêu các bằng chứng cần có trước khi đổi effective_cache_size.

**Gợi ý:** memory budget, working set, EXPLAIN plans, actual buffers, workload concurrency và runtime measurements.

## 61. Câu hỏi thường gặp

### effective_cache_size có làm database cache nhiều dữ liệu hơn không?

Không. Nó chỉ ảnh hưởng giả định của planner. Muốn thay đổi shared buffer allocation, xem `shared_buffers`; OS cache do hệ điều hành quản lý.

### Có nên đặt effective_cache_size bằng shared_buffers không?

Không nhất thiết. Planner cần xét cả phần OS page cache có thể phục vụ database files và mức cache phải chia sẻ giữa queries.

### Có nên đặt bằng toàn bộ RAM?

Không theo mặc định. Cần trừ/ước lượng memory cho OS, backend processes, ứng dụng khác, container limits và cache overlap.

### Giá trị cao có luôn làm query nhanh hơn?

Không. Nó có thể làm planner chọn plan khác; plan mới có thể tốt hoặc xấu tùy workload và cache thực tế.

### effective_cache_size có ảnh hưởng execution sau khi plan đã được tạo không?

Nó tác động tới planning/cost estimation. Nó không cấp phát cache hoặc thay đổi trực tiếp cơ chế đọc dữ liệu trong executor.

### Vì sao planner vẫn chọn sequential scan khi cache lớn?

Query có thể cần phần lớn bảng, index không phù hợp, estimates hoặc cost parameters khiến sequential scan rẻ hơn.

### Vì sao planner chọn index scan nhưng query chậm?

Có thể heap fetches phân tán, cache không đủ, actual rows lớn hơn estimates hoặc storage latency cao.

### Hit ratio 99% có nghĩa effective_cache_size đặt đúng?

Không. Hit ratio chỉ là một tín hiệu; cần xem query plans, OS cache, working set và latency.

### Có cần restart sau khi đổi effective_cache_size?

Phụ thuộc GUC context và cách cấu hình. Kiểm tra `pg_settings.context`, sau đó xác nhận giá trị có hiệu lực bằng `SHOW`.

### Có thể thử nhiều giá trị mà không đổi cấu hình server không?

Có thể dùng `SET` trong session nếu context cho phép, rồi so sánh `EXPLAIN`. Đây là thử nghiệm planner; runtime benchmark cần điều kiện riêng.

### effective_cache_size có thay thế random_page_cost không?

Không. Một setting mô tả cache assumption; setting kia mô tả chi phí tương đối của random page access.

### effective_cache_size có giúp sort tránh spill không?

Không trực tiếp. Sort/hash workspace liên quan `work_mem` và query execution.

### pg_buffercache có hiển thị toàn bộ cache của OS không?

Không. Nó quan sát PostgreSQL shared buffers.

### Khi nào cần đánh giá lại setting?

Khi thay đổi RAM, container limits, shared_buffers, workload mix, concurrency, storage hoặc working set đáng kể.

## 62. Tổng kết

Các lệnh quan sát và thử nghiệm quan trọng:

~~~sql
-- Planner cache assumption.
SHOW effective_cache_size;

-- Các memory/cost settings liên quan.
SHOW shared_buffers;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW random_page_cost;
SHOW seq_page_cost;
SHOW effective_io_concurrency;

-- Metadata của setting.
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'effective_cache_size',
    'shared_buffers',
    'work_mem',
    'random_page_cost',
    'seq_page_cost'
);

-- Database-level buffer counters.
SELECT
    datname,
    blks_read,
    blks_hit,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();

-- Relation-level I/O.
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_tables
ORDER BY heap_blks_read + idx_blks_read DESC
LIMIT 20;

-- Planner estimate.
EXPLAIN
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 420;

-- Runtime và buffer evidence trong môi trường an toàn.
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 420;
~~~

Những nguyên tắc cần nhớ:

1. `effective_cache_size` là giả định cache của planner, không phải memory allocation.
2. `shared_buffers` là shared memory cache PostgreSQL cấp phát thật.
3. OS page cache có thể phục vụ database file reads.
4. Planner cần xét shared buffers, OS cache, overlap và query concurrency.
5. Giá trị cao hơn thường làm index access có vẻ rẻ hơn; giá trị thấp hơn có thể làm sequential scan hấp dẫn hơn.
6. Không có một tỷ lệ RAM cố định đúng cho mọi host.
7. `random_page_cost` và `seq_page_cost` là cost assumptions khác với cache size.
8. Cost units không phải milliseconds.
9. Selectivity, cardinality estimates, correlation và index design vẫn quyết định plan.
10. Sequential scan không mặc định là xấu.
11. `work_mem` giải quyết workspace của sort/hash, không phải cache assumption.
12. `pg_stat_database` và `pg_statio_user_tables` cho tín hiệu buffer I/O nhưng không đo toàn bộ OS cache.
13. `pg_buffercache` quan sát PostgreSQL shared buffers, không phải page cache của OS.
14. `EXPLAIN` cho biết planned costs; `EXPLAIN (ANALYZE, BUFFERS)` cung cấp runtime/buffer evidence.
15. Sửa statistics trước khi quy lỗi cho cache assumption.
16. Thử setting theo session khi có thể và thay đổi từng biến một.
17. So sánh nhiều query đại diện trong điều kiện cache/concurrency tương đương.
18. Kiểm tra memory limits trong VM/container thay vì dùng tổng RAM host.
19. Theo dõi plan regressions sau khi triển khai.
20. Đánh giá lại khi memory budget, workload hoặc topology thay đổi.

Sơ đồ tư duy:

~~~text
Planner cần chọn access path
             |
             v
      Ước lượng page costs
             |
             v
      effective_cache_size
             |
             v
   Giả định pages có thể cached
             |
       +-----+------+
       |            |
       v            v
    Index path   Sequential path
       |            |
       +-----+------+
             |
             v
       So sánh estimated cost
             |
             v
       Chọn plan có cost thấp
             |
             v
       EXPLAIN / BUFFERS
             |
             v
   Đối chiếu runtime và cache thật
             |
             v
     Điều chỉnh có bằng chứng
~~~

**Kết luận:** `effective_cache_size` giúp planner ước lượng lượng cache có thể phục vụ query để đánh giá chi phí truy cập dữ liệu, đặc biệt khi so sánh index access với sequential scan. Giá trị phù hợp phải phản ánh **shared buffers, OS page cache, memory budget và mức cạnh tranh giữa các queries**. Hãy kết hợp query plans, row estimates, buffer statistics và runtime measurements trước khi điều chỉnh; thay đổi tham số này không cấp phát RAM và không tự làm cache lớn hơn.
