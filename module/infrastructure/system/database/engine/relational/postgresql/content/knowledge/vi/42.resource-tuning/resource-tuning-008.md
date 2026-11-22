# Parallel worker, giới hạn CPU và hiệu quả truy vấn song song

PostgreSQL có thể chia một số thao tác truy vấn hoặc bảo trì thành nhiều phần để nhiều tiến trình cùng thực hiện. Cơ chế này gọi là **parallel query** hoặc **parallel processing**. Khi dữ liệu lớn và CPU còn dư, nhiều workers có thể rút ngắn thời gian quét bảng, join, aggregate hoặc tạo index. Nhưng thêm workers không tự động làm truy vấn nhanh hơn: chúng tiêu thụ CPU, memory, I/O, worker slots và tài nguyên hệ điều hành; nhiều truy vấn song song chạy đồng thời có thể làm toàn hệ thống chậm hơn.

Tối ưu parallelism vì vậy cần phối hợp ba lớp:

1. **PostgreSQL planner/executor:** quyết định có tạo parallel plan không, cần bao nhiêu workers và những plan nodes nào có thể chạy song song.
2. **PostgreSQL worker limits:** giới hạn tổng background workers, parallel workers toàn cluster và workers cho mỗi Gather/Gather Merge.
3. **Operating system/container:** giới hạn CPU thực tế qua cgroups, systemd, cpuset, container quotas hoặc Kubernetes CPU requests/limits.

Mục tiêu là chọn mức parallelism phù hợp với kích thước truy vấn, số truy vấn đồng thời, số CPU được cấp và SLA của workload.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích PostgreSQL parallel query và vai trò của parallel workers.
- Phân biệt leader process, parallel worker, background worker và client backend.
- Đọc `Gather`/`Gather Merge` và `Workers Planned`/`Workers Launched` trong EXPLAIN.
- Hiểu parallel-safe, parallel-restricted và parallel-unsafe operations.
- Cấu hình `max_worker_processes`, `max_parallel_workers`, `max_parallel_workers_per_gather` và các cost/threshold settings.
- Ước lượng tổng worker demand khi nhiều truy vấn chạy đồng thời.
- Phân biệt giới hạn worker của PostgreSQL với giới hạn CPU của OS/container.
- Tuning CPU quotas, cpuset và Kubernetes requests/limits theo workload.
- Chẩn đoán worker không được cấp, CPU saturation, I/O bottleneck và parallel plan kém hiệu quả.
- Đánh giá lợi ích của parallel scans, joins, aggregation và parallel index maintenance.
- Thiết kế monitoring, benchmark và runbook để thay đổi parallelism an toàn.

## 2. Parallel query là gì?

### 2.1. Một truy vấn có thể dùng nhiều process

Trong execution thông thường, một backend process xử lý plan của truy vấn. Với parallel query, PostgreSQL có thể khởi chạy nhiều parallel workers để cùng thực hiện các phần độc lập của plan. Backend gửi yêu cầu, điều phối và thu kết quả; trong plan có `Gather` hoặc `Gather Merge` để kết hợp rows từ workers.

Ví dụ khái niệm:

```text
Client
  |
  v
Leader backend
  |  \        \
  |   \        +---- Parallel worker 2
  |    +------------- Parallel worker 1
  |
  +---- Gather / Gather Merge
             |
             v
        Final result
```

Leader backend có thể tự tham gia phần scan/compute cùng workers, sau đó nhận và xử lý tuples từ workers. Nó không chỉ là một proxy rảnh rỗi.

### 2.2. Chia công việc

Ví dụ một bảng có nhiều pages. Thay vì một process quét tất cả pages, parallel sequential scan có thể chia block ranges cho nhiều workers. Mỗi worker đọc một phần và tạo tuples. Kết quả được gửi về leader qua cơ chế shared memory/tuple queues; leader tiếp tục xử lý các plan nodes phía trên Gather.

### 2.3. Parallel query chạy trong một PostgreSQL instance

Parallel workers của một query chạy trên cùng PostgreSQL server instance, truy cập cùng database cluster và phối hợp bằng executor/shared-memory mechanisms. Đây không phải distributed query execution qua nhiều PostgreSQL servers hay shards.

Nếu cần chạy truy vấn trên nhiều nodes/shards, cần extension hoặc hệ thống distributed database phù hợp; `max_parallel_workers_per_gather` không tạo distributed cluster.

### 2.4. Không phải mọi truy vấn đều parallel

Planner chỉ chọn parallel plan khi:

- Có plan node hỗ trợ parallel execution.
- Query không chứa thao tác/biểu thức không an toàn trong parallel context.
- Cost estimate cho thấy parallel plan có lợi.
- Kích thước scan/threshold và worker limits cho phép.
- Worker slots có thể được cấp khi query chạy.

Truy vấn nhỏ thường không đáng chịu overhead khởi tạo workers và gather tuples.

### 2.5. Parallel query không bảo đảm kết quả nhanh hơn tuyến tính

Nếu một truy vấn serial mất 40 giây, dùng 4 workers không có nghĩa chắc chắn còn 10 giây. Overhead, leader work, skew, I/O bandwidth, memory contention và worker allocation làm speedup thấp hơn số workers.

## 3. Thành phần thực thi

### 3.1. Leader backend

Leader là backend process phục vụ client query. Khi plan parallel, leader yêu cầu parallel workers, khởi chạy chúng nếu còn slot, phối hợp executor và nhận rows.

Leader có thể:

- Tham gia scan/compute như một worker.
- Đọc tuples từ workers.
- Thực hiện plan nodes không parallel.
- Thực hiện final aggregation/sort hoặc các bước phía trên Gather.
- Điều phối cancellation/error và hoàn tất query.

### 3.2. Parallel workers

Parallel workers là PostgreSQL background worker processes được khởi chạy để thực hiện một phần parallel plan. Chúng không phải client sessions độc lập và không nhận connection trực tiếp từ ứng dụng.

Workers có thể bị giới hạn bởi:

- `max_worker_processes`: tổng worker processes được phép chạy.
- `max_parallel_workers`: giới hạn parallel workers cho toàn cluster.
- `max_parallel_workers_per_gather`: giới hạn workers mà một Gather/Gather Merge có thể yêu cầu.
- Số worker slots hiện đang được background workers/parallel queries khác sử dụng.
- OS process/resource limits và CPU availability.

### 3.3. Background workers khác parallel workers

PostgreSQL có nhiều loại background workers: logical replication workers, extension workers, parallel query workers và các tiến trình quản trị khác. `max_worker_processes` là pool cấp cao hơn; parallel workers chia sẻ giới hạn này với các worker processes khác.

Vì vậy, tăng `max_parallel_workers` vượt số slots còn lại trong `max_worker_processes` không tạo thêm worker capacity.

### 3.4. Client connections không phải worker slots

`max_connections` giới hạn client backends. `max_worker_processes` giới hạn worker processes. Hai tham số điều khiển hai nhóm process khác nhau, dù tất cả đều dùng CPU/memory và có thể tranh tài nguyên hệ thống.

Không tăng `max_connections` để giải quyết parallel worker allocation failure.

### 3.5. Worker lifetime

Parallel workers thường được khởi chạy khi query cần thực hiện parallel plan và kết thúc khi phần parallel execution hoàn tất hoặc query bị cancel. Một worker slot được giải phóng sau khi process kết thúc.

Nếu query thường xuyên yêu cầu nhiều workers, cần quan sát đồng thời active parallel queries, worker slots và process limits.

## 4. Gather và Gather Merge

### 4.1. Gather

`Gather` nhận tuples từ các parallel workers và leader rồi chuyển kết quả lên plan node phía trên. Thứ tự rows không được đảm bảo chỉ vì một số worker scan trước worker khác.

Ví dụ plan dạng:

```text
Gather
  Workers Planned: 4
  -> Parallel Seq Scan on orders
```

Plan node phía dưới `Gather` là phần parallel subtree. `Gather` là ranh giới mà leader gom kết quả.

### 4.2. Gather Merge

`Gather Merge` kết hợp các sorted streams từ workers theo thứ tự đã được sắp xếp. Nó có thể giữ ordering của plan, nhưng phải trả chi phí merge và coordination.

Ví dụ:

```text
Gather Merge
  Workers Planned: 4
  -> Sort
       -> Parallel Seq Scan on events
```

### 4.3. Workers Planned và Workers Launched

Trong `EXPLAIN (ANALYZE, VERBOSE)`, PostgreSQL có thể hiển thị:

- `Workers Planned`: số workers planner dự kiến dùng.
- `Workers Launched`: số workers thực sự được khởi chạy cho lần thực thi đó.

Hai số có thể khác nhau. Ví dụ plan yêu cầu 4 workers nhưng lúc chạy chỉ cấp được 2 do worker pool đang bận. Query vẫn có thể tiếp tục với ít workers hơn.

### 4.4. Planned workers không phải reserved capacity

Planner không giữ trước worker slots cho một truy vấn. `Workers Planned` là dự kiến trong plan, còn allocation thực tế diễn ra lúc execution. Vì vậy benchmark chạy đơn lẻ có thể launch đủ workers, nhưng production khi nhiều queries đồng thời có thể launch ít hơn.

### 4.5. Leader participation

`parallel_leader_participation` điều khiển leader có tham gia xử lý parallel portion hay không. Khi bật, leader có thể scan/compute cùng workers. Khi tắt, leader chủ yếu thu tuples và thực hiện các bước phía trên Gather.

Leader participation có lợi khi lượng tuples vừa phải và leader còn CPU. Với workers tạo output rất nhanh, leader có thể phải tập trung tiêu thụ tuples thay vì tiếp tục scan.

### 4.6. Parallel tuple transfer overhead

Rows từ workers cần được chuyển tới leader qua tuple queues/shared memory. Với plan tạo ra rất nhiều rows nhỏ, transfer/Gather overhead có thể chiếm tỷ lệ lớn. Pushdown filters, aggregate sớm hoặc giảm số tuples truyền qua Gather thường hữu ích.

## 5. Các loại thao tác parallel

### 5.1. Parallel sequential scan

Parallel sequential scan chia block ranges của heap cho nhiều workers. Nó phù hợp khi truy vấn cần đọc phần lớn bảng và bảng đủ lớn để bù overhead.

Nó có thể kém hiệu quả khi:

- Query chỉ cần vài rows và index scan phù hợp hơn.
- Storage bandwidth đã bão hòa.
- Table nhỏ.
- CPU quota thấp hơn tổng số workers.
- Rows bị lọc mạnh nhưng plan phải đọc nhiều pages.

### 5.2. Parallel bitmap heap scan

PostgreSQL có thể parallelize phần heap scan của bitmap heap scan trong các trường hợp hỗ trợ. Bitmap index scan và heap block processing có execution model riêng; không suy luận mọi index operation đều parallel.

### 5.3. Parallel index scan

PostgreSQL hỗ trợ parallel index scan cho một số access methods/plan shapes (ví dụ B-tree trong các phiên bản hiện đại). EXPLAIN là nguồn xác nhận thực tế; không phải mọi index type hay query đều được parallelize.

### 5.4. Parallel append

`Parallel Append` có thể phân phối công việc giữa các child plans, ví dụ partition scans, cho phép workers xử lý các partitions/subplans khác nhau.

Điều này hữu ích với partitioned tables nhưng phụ thuộc partition pruning, plan shape và kích thước từng partition. Một partition lớn duy nhất có thể gây skew.

### 5.5. Parallel aggregation

Parallel aggregation có thể dùng hai giai đoạn:

1. Partial aggregate trên workers.
2. Finalize aggregate trên leader sau khi gom partial states.

Ví dụ `Partial HashAggregate` và `Finalize HashAggregate`. Aggregate function cần hỗ trợ combine/parallel semantics phù hợp.

### 5.6. Parallel hash join

Một số hash join có thể dùng shared hash table hoặc parallel hash build/probe. Lợi ích phụ thuộc kích thước hai inputs, memory và data distribution. Hash table lớn có thể tạo memory pressure; parallelism không chữa được join cardinality estimate sai.

### 5.7. Parallel merge join

Merge join có thể xuất hiện trong parallel plans tùy sort/order và plan shape. Chi phí sort, merge coordination và data distribution quyết định hiệu quả.

### 5.8. Parallel sort

Sort có thể chạy trong workers ở phần parallel subtree; kết quả được merge qua Gather Merge hoặc xử lý tiếp. Sort memory là per-operation/per-process, nên nhiều workers có thể làm tổng memory tăng đáng kể.

### 5.9. Parallel maintenance

PostgreSQL còn dùng parallel workers cho một số maintenance operations, đặc biệt parallel index build. Tham số `max_parallel_maintenance_workers` kiểm soát workers cho các operations hỗ trợ. Đây là một budget riêng ở tầng operation nhưng vẫn chia sẻ `max_worker_processes`.

### 5.10. Không phải mọi SQL command đều parallelizable

Parallel query chủ yếu áp dụng cho các SELECT/plan portions đủ điều kiện. Một số command hoặc expression bị giới hạn do side effects, transaction semantics, locks, temporary state hoặc executor constraints.

## 6. Parallel safety

### 6.1. Vì sao cần phân loại safety?

Một worker chạy trong parallel context không thể tùy tiện thực hiện mọi operation mà một leader backend có thể làm. PostgreSQL cần biết function/expression có side effects, phụ thuộc session state hay truy cập tài nguyên không an toàn khi nhiều processes cùng thực hiện hay không.

### 6.2. PARALLEL SAFE

Function được đánh dấu `PARALLEL SAFE` có thể được thực hiện trong parallel worker nếu các điều kiện khác của plan cho phép. Function phải thực sự an toàn khi chạy đồng thời và không được giả định mọi lời gọi diễn ra trong cùng backend process.

### 6.3. PARALLEL RESTRICTED

`PARALLEL RESTRICTED` chỉ được thực hiện ở leader, không chạy trong parallel workers. Plan vẫn có thể chứa phần parallel ở dưới hoặc bên cạnh expression restricted nếu executor có thể đặt nó đúng vị trí.

### 6.4. PARALLEL UNSAFE

`PARALLEL UNSAFE` không cho phép query chạy trong parallel mode. Nếu một expression unsafe xuất hiện, planner thường phải chọn serial plan cho query.

### 6.5. User-defined functions

Không tự đánh dấu mọi function là safe để ép query parallel. Function ghi file, cập nhật sequence, thay đổi database state, truy cập session-specific state hoặc gọi code không thread/process safe có thể làm kết quả sai hoặc gây side effects trùng lặp.

Ví dụ khai báo function thuần:

```sql
CREATE FUNCTION normalize_code(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT upper(trim($1));
$$;
```

Chỉ dùng `PARALLEL SAFE` nếu implementation và mọi functions mà nó gọi thực sự đáp ứng điều kiện. `IMMUTABLE` và `PARALLEL SAFE` là hai thuộc tính khác nhau; immutable không tự chứng minh parallel safety.

### 6.6. Kiểm tra function properties

Có thể xem volatility và parallel classification trong catalog:

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    p.provolatile,
    p.proparallel
FROM pg_proc AS p
JOIN pg_namespace AS n ON n.oid = p.pronamespace
WHERE p.proname = 'normalize_code';
```

Giá trị `proparallel` thường là `s` (safe), `r` (restricted), `u` (unsafe).

### 6.7. Các trường hợp thường bị hạn chế

Tùy PostgreSQL version và plan context, parallel execution có thể bị hạn chế bởi:

- Temporary tables hoặc session-local state.
- Cursors/row locking và một số locking clauses.
- Data-modifying operations hoặc side-effecting functions.
- Sequence access/sequence modification.
- Một số foreign table/FDW hoặc custom scan providers.
- Một số transaction isolation/transaction state combinations.
- Function/aggregate/operator không có parallel safety phù hợp.

Danh sách cụ thể thay đổi theo version. Hãy đọc phần Parallel Plans trong PostgreSQL documentation của major version đang dùng và kiểm tra EXPLAIN.

### 6.8. Parallel-safe không có nghĩa function chạy nhanh

Function safe chỉ nói nó có thể chạy trong parallel context. Function có thể CPU-heavy, gọi I/O ngoài, lock shared resources hoặc có contention; chạy nhiều bản sao đồng thời có thể làm chậm hệ thống.

### 6.9. Extension và custom code

Extension có thể đăng ký functions, aggregates, custom scans hoặc background workers. Kiểm tra parallel safety markings và tài liệu extension. Nếu extension function mặc định unsafe, query chứa nó có thể mất parallel plan.

### 6.10. Khi query không parallel

Nếu plan không có Gather/Gather Merge, kiểm tra:

1. Có expression/function `PARALLEL UNSAFE` không?
2. Query có command/lock/temporary state bị hạn chế không?
3. Bảng có đủ lớn theo min parallel scan threshold không?
4. Planner cost có thấy parallel plan đáng giá không?
5. `max_parallel_workers_per_gather` có bằng 0 không?
6. Table statistics và row estimates có hợp lý không?

Không bật chế độ thử nghiệm force parallel hoặc tăng workers trước khi tìm nguyên nhân.

## 7. Các tham số giới hạn worker

### 7.1. max_worker_processes

`max_worker_processes` đặt giới hạn tổng số background worker processes mà server có thể chạy đồng thời. Pool này phục vụ parallel workers và một số background workers khác.

Đây là giới hạn nền. Nếu đặt quá thấp, parallel queries hoặc extension/logical replication workers có thể không có slot. Nếu đặt quá cao, server có thể tạo nhiều processes hơn khả năng CPU/memory của host.

### 7.2. max_parallel_workers

`max_parallel_workers` giới hạn tổng số parallel workers có thể chạy đồng thời trên toàn PostgreSQL cluster. Nó không bao gồm mọi loại background worker; nhưng parallel workers vẫn phải có slot từ `max_worker_processes`.

### 7.3. max_parallel_workers_per_gather

`max_parallel_workers_per_gather` giới hạn số parallel workers mà một Gather/Gather Merge node có thể yêu cầu. Đây là giới hạn theo plan node/truy vấn, không phải tổng cluster.

Nếu đặt 4, một query có thể yêu cầu tối đa 4 parallel workers cho một Gather; các Gather nodes/queries đồng thời vẫn bị giới hạn bởi global pool.

### 7.4. max_parallel_maintenance_workers

Tham số này giới hạn parallel workers cho maintenance commands hỗ trợ, ví dụ `CREATE INDEX`/`REINDEX` theo phiên bản và operation. Nó không cấp một pool tách biệt khỏi `max_worker_processes`.

### 7.5. Bảng tóm tắt

| Tham số | Phạm vi | Vai trò |
| --- | --- | --- |
| `max_worker_processes` | Toàn server | Trần background worker processes. |
| `max_parallel_workers` | Toàn cluster | Trần parallel workers đang chạy. |
| `max_parallel_workers_per_gather` | Mỗi Gather/Gather Merge | Trần workers một query plan node có thể yêu cầu. |
| `max_parallel_maintenance_workers` | Mỗi maintenance operation | Trần workers cho parallel maintenance. |
| `max_connections` | Toàn server | Client backend connections, không phải parallel worker pool. |

### 7.6. Ví dụ cấu hình khởi đầu

Ví dụ một server có khoảng 8 logical CPUs được cấp và workload vừa phải:

```conf
max_worker_processes = 16
max_parallel_workers = 8
max_parallel_workers_per_gather = 2
max_parallel_maintenance_workers = 2
```

Đây chỉ là điểm bắt đầu minh họa, không phải công thức. Cần tính cả extension workers, logical replication, CPU quotas, số query đồng thời, memory và workload latency.

### 7.7. Parameter context và restart

Một số worker limit là startup/postmaster parameters, thay đổi cần restart PostgreSQL; các tham số planner/runtime khác có thể reload hoặc set theo session tùy context. Kiểm tra `pg_settings.context`, `pending_restart` và tài liệu đúng major version trước khi thay đổi.

### 7.8. Kiểm tra giá trị hiện tại

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_worker_processes',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'max_parallel_maintenance_workers',
    'parallel_leader_participation'
)
ORDER BY name;
```

### 7.9. Worker demand và worker supply

Giả sử 5 queries đồng thời, mỗi query có một Gather cần 4 workers. Demand lý thuyết là 20 workers. Nếu `max_parallel_workers` là 8, toàn cluster chỉ cấp tối đa 8 parallel workers; các query còn lại có thể chạy với ít workers hơn hoặc không có worker bổ sung.

Nếu `max_worker_processes` chỉ còn 6 slots sau khi trừ background workers khác, effective supply còn thấp hơn nữa.

### 7.10. Không cộng workers như CPU count

`max_parallel_workers` là số processes, không phải số CPU được đảm bảo. Có thể cấu hình 16 workers trên máy 4 CPUs, nhưng chúng sẽ tranh CPU. Cấu hình worker capacity và CPU capacity là hai quyết định liên quan nhưng khác nhau.

## 8. Planner thresholds và cost settings

### 8.1. min_parallel_table_scan_size

`min_parallel_table_scan_size` là ngưỡng kích thước table scan tối thiểu để planner xem xét parallel sequential scan. Bảng nhỏ hơn ngưỡng thường không đáng chịu parallel setup overhead.

### 8.2. min_parallel_index_scan_size

`min_parallel_index_scan_size` là ngưỡng kích thước index scan tối thiểu để planner xem xét parallel index scan trong các trường hợp hỗ trợ.

### 8.3. parallel_setup_cost

`parallel_setup_cost` là cost ước tính overhead khởi tạo parallel workers và coordination. Giá trị cao khiến planner ít chọn parallel plans hơn; giảm quá thấp có thể khiến planner parallelize nhiều truy vấn nhỏ.

### 8.4. parallel_tuple_cost

`parallel_tuple_cost` là cost ước tính cho việc truyền mỗi tuple từ worker tới leader. Giá trị cao làm parallel plans có nhiều rows phải gather kém hấp dẫn hơn.

### 8.5. seq_page_cost và random_page_cost

Đây là cost assumptions ảnh hưởng scan/index choices. Chúng không phải latency đo được theo milliseconds. Tuning sai có thể làm planner chọn access path không phù hợp, từ đó làm đánh giá parallelism sai.

### 8.6. force_parallel_mode

Các PostgreSQL releases đã thay đổi/deprecate một số chế độ thử nghiệm liên quan force parallel mode. Không dùng setting thử nghiệm làm tuning production. Dùng EXPLAIN, planner settings chuẩn và benchmark theo version.

### 8.7. Giá trị mặc định không phải target

Default cost/threshold được thiết kế để hoạt động trên nhiều môi trường. Server NVMe, network storage, CPU quota container và workload OLTP/analytics có đặc điểm khác nhau. Điều chỉnh dựa trên số liệu, không copy cấu hình từ blog.

### 8.8. Session-level experimentation

Để so sánh planner behavior trong lab, có thể dùng `SET LOCAL` trong transaction cho các settings cho phép thay theo session:

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (COSTS, VERBOSE)
SELECT count(*)
FROM large_fact_table
WHERE event_date >= DATE '2026-01-01';
ROLLBACK;
```

Sau đó so sánh với giá trị hiện hành. Không dùng thay đổi session để kết luận production behavior nếu concurrency/resource limits khác.

### 8.9. Planner parallelism và statistics

Planner cần ước lượng row counts, selectivity và relation size. `ANALYZE`/autovacuum statistics lỗi thời có thể làm planner chọn plan sai, kể cả parallel plan. Trước khi tuning cost, kiểm tra estimates so với actual rows.

### 8.10. Không ép parallel query để che lỗi index/schema

Nếu query lọc rất chọn lọc nhưng thiếu index, planner có thể phải scan lớn. Thêm workers có thể giảm thời gian scan nhưng vẫn tốn nhiều I/O/CPU. Xem lại index, partitioning, predicate, join keys và statistics.

## 9. Leader participation và mức parallelism

### 9.1. parallel_leader_participation

Setting `parallel_leader_participation` thường mặc định bật. Khi bật, leader tham gia parallel subtree và có thể xử lý một phần công việc. Khi tắt, leader chủ yếu điều phối/thu tuples, giúp tránh leader vừa scan vừa gather trong một số workload.

### 9.2. Khi leader participation hữu ích

- Parallel subtree tạo output không quá lớn.
- Leader có CPU capacity.
- Query là scan/aggregate tương đối cân bằng.
- Worker count nhỏ và gather throughput không bão hòa.

### 9.3. Khi leader trở thành điểm nghẽn

Nếu workers tạo rows nhanh, leader phải liên tục nhận/deserialize/process tuples. Khi đó leader có thể ngừng tham gia scan để tập trung gather. Tăng workers có thể làm gather queue/leader CPU bottleneck nặng hơn.

### 9.4. Workers per Gather

Tăng `max_parallel_workers_per_gather` cho một query có thể cải thiện throughput scan, nhưng cũng tăng:

- CPU demand.
- Worker process count.
- Memory cho sort/hash/aggregate ở mỗi process.
- I/O concurrency.
- Tuple transfer/gather traffic.

Không đặt giá trị lớn nhất có thể cho tất cả workload.

### 9.5. Parallelism theo workload class

Có thể dùng role/database/session settings để giới hạn parallelism:

- OLTP interactive queries: ít workers hoặc serial để giữ latency và concurrency.
- Batch/reporting: cho phép nhiều workers khi có CPU headroom.
- Maintenance window: cho phép parallel index build có kiểm soát.
- Ad hoc analytics: giới hạn worker count/resource group để tránh ảnh hưởng ứng dụng.

PostgreSQL core settings không tự tạo workload scheduler hoàn chỉnh; có thể cần connection pool, job scheduler hoặc OS/container resource controls.

### 9.6. SET cho role/database

Ví dụ giới hạn per-query workers cho một role báo cáo:

```sql
ALTER ROLE reporting_user
SET max_parallel_workers_per_gather = 2;
```

Hoặc cho database:

```sql
ALTER DATABASE analytics
SET max_parallel_workers_per_gather = 4;
```

Setting có hiệu lực cho sessions mới sau khi reconnect. Server/global limits vẫn có quyền ưu tiên; per-role setting không thể vượt `max_parallel_workers`.

### 9.7. SET LOCAL cho transaction

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
-- Run latency-sensitive statements serially in this transaction.
SELECT ...;
COMMIT;
```

Dùng `SET LOCAL` khi muốn thay đổi tạm trong transaction và setting đó được phép set ở session context.

### 9.8. Connection pool và role settings

Với transaction pooling, session-level settings có thể không giữ qua transaction như ứng dụng kỳ vọng. Ưu tiên `SET LOCAL` trong transaction hoặc cấu hình role/database; kiểm tra behavior của PgBouncer mode.

### 9.9. Không đặt workers theo số sessions

Một pool có 100 connections không có nghĩa nên cấp 100 × 4 workers. Hãy tính số queries thực sự chạy song song, CPU budget, I/O và latency target.

## 10. Parallel maintenance

### 10.1. CREATE INDEX

Một số `CREATE INDEX` có thể sử dụng parallel workers cho phần build hỗ trợ. `max_parallel_maintenance_workers` giới hạn worker count của maintenance operation; `max_parallel_workers` và `max_worker_processes` vẫn giới hạn tổng supply.

### 10.2. REINDEX

`REINDEX` trên các index/access methods hỗ trợ có thể dùng parallel maintenance. Xem command options, version và EXPLAIN/command output để xác nhận.

### 10.3. VACUUM

VACUUM có thể sử dụng parallel workers cho một số phần xử lý index trong các phiên bản hỗ trợ. Parallel maintenance behavior không đồng nghĩa toàn bộ VACUUM heap scan chạy song song như parallel query.

### 10.4. maintenance_work_mem

`maintenance_work_mem` ảnh hưởng memory budget cho maintenance operations. Nhiều operations/worker processes có thể làm tổng memory demand tăng. Cần tính đồng thời các jobs, không chỉ một session.

### 10.5. Maintenance workers và query workers

Maintenance workers và parallel query workers chia sẻ worker process capacity. Chạy CREATE INDEX parallel trong giờ cao điểm có thể làm parallel SELECTs thiếu slots và cạnh tranh CPU/I/O.

### 10.6. Maintenance window

Đặt giới hạn worker count và schedule cho index build/reindex/vacuum lớn. Theo dõi replication lag, WAL generation, disk throughput và application latency.

## 11. Giới hạn CPU ở hệ điều hành

### 11.1. PostgreSQL worker limits không phải CPU limits

`max_parallel_workers` giới hạn số worker processes PostgreSQL có thể chạy. Nó không giới hạn số CPU mà một process được sử dụng, cũng không bảo đảm một worker có riêng một core.

CPU scheduling thuộc hệ điều hành hoặc container runtime. Một server có 32 parallel worker slots nhưng chỉ được cấp 4 CPUs sẽ có nhiều processes tranh 4 CPUs.

### 11.2. CPU affinity và cpuset

CPU affinity/cpuset xác định tập CPU mà process/container được phép chạy. Ví dụ một container chỉ được phép chạy trên CPUs 2–5 thì effective CPU set có 4 CPUs, dù host có nhiều cores hơn.

Affinity giới hạn vị trí chạy, không tự giới hạn tổng CPU time theo quota. Có thể kết hợp cpuset và quota.

### 11.3. CPU quota

CPU quota giới hạn lượng CPU time một cgroup có thể dùng trong một period. Với cgroup v2, `cpu.max` thường biểu diễn quota và period theo microseconds; quota/period xấp xỉ số CPUs được cấp.

Ví dụ:

```text
cpu.max = 400000 100000
CPU quota = 400000 / 100000 = 4 CPU equivalents
```

Container có thể chạy đồng thời trên nhiều cores trong period, rồi bị throttled khi đã tiêu hết quota.

### 11.4. CPU weight/share

CPU weight/share điều chỉnh tỷ lệ CPU tương đối khi các cgroups cạnh tranh. Nó không phải hard cap cố định nếu CPU còn dư. Đừng nhầm request/weight với quota/limit.

### 11.5. Docker CPU limit

Ví dụ chạy container với giới hạn khoảng 4 CPUs:

```bash
docker run --cpus=4 ...
```

Đây là minh họa. Cần tính CPU quota cùng cpuset, host contention và memory limit. Kiểm tra runtime/cgroup thực tế thay vì chỉ tin CLI configuration.

### 11.6. systemd CPUQuota

Với PostgreSQL chạy dưới systemd, có thể giới hạn CPU ở service slice/unit bằng `CPUQuota=` và kiểm soát tập CPUs bằng `AllowedCPUs=` trên các systemd versions hỗ trợ.

Ví dụ cấu hình unit override:

```ini
[Service]
CPUQuota=400%
AllowedCPUs=2-5
```

`CPUQuota=400%` biểu diễn tối đa khoảng bốn CPUs trên hệ thống systemd hỗ trợ; `AllowedCPUs=2-5` giới hạn tập CPU. Kiểm tra systemd/cgroup version và unit inheritance.

### 11.7. Kubernetes CPU requests và limits

Trong Kubernetes:

- `resources.requests.cpu` là lượng CPU được scheduler dùng để đặt Pod và là cơ sở tương đối cho CPU share/weight khi cạnh tranh.
- `resources.limits.cpu` đặt hard limit; vượt quota trong period có thể bị CPU throttling.
- CPU thường biểu diễn bằng cores hoặc millicores, ví dụ `2000m` tương đương 2 CPUs.

Một Pod có request `2` và limit `4` có thể được cấp scheduler reservation 2 CPUs nhưng được dùng tối đa 4 CPUs nếu node capacity cho phép.

### 11.8. Ví dụ Kubernetes resources

```yaml
resources:
  requests:
    cpu: "2"
    memory: "8Gi"
  limits:
    cpu: "4"
    memory: "12Gi"
```

Đây chỉ là ví dụ. Memory limit là hard boundary khác với CPU scheduling; PostgreSQL OOM kill có thể gây restart/failover. Tính memory riêng cho shared buffers, connections, sorts, hashes, workers và OS cache.

### 11.9. Kubernetes Guaranteed/Burstable QoS

QoS class phụ thuộc requests/limits CPU và memory của tất cả containers trong Pod. Guaranteed QoS cần requests bằng limits cho CPU và memory ở từng container. Burstability/eviction behavior có thể ảnh hưởng stability; đừng chọn QoS chỉ vì muốn CPU performance mà bỏ qua memory.

### 11.10. CPU throttling

Khi container chạm quota, scheduler throttles cgroup cho phần còn lại của period. PostgreSQL workers vẫn tồn tại nhưng bị hạn chế CPU time. Điều này có thể làm query latency tăng, HA loop chậm và replication lag tăng.

### 11.11. Kiểm tra cgroup v2

Trong Linux cgroup v2, các files hữu ích gồm:

- `cpu.max`: quota và period.
- `cpu.stat`: usage, throttling periods và throttled time.
- `cpu.weight`: relative CPU weight.
- `cpuset.cpus.effective`: CPUs thực tế có thể sử dụng.

Đường dẫn cgroup phụ thuộc process/container. Đọc đúng cgroup của PostgreSQL service/container, không chỉ root cgroup.

### 11.12. CPU metrics trên Kubernetes

Dùng container metrics/Prometheus/cAdvisor hoặc metrics pipeline của cluster để xem:

- CPU usage cores.
- CPU throttled periods/time.
- CPU request/limit.
- Node CPU pressure.
- Pod restarts/OOM kills.
- Container memory working set.

CPU usage thấp không chứng minh hệ thống không bị throttled; kiểm tra throttling metrics cùng latency.

## 12. Tính worker budget theo CPU và concurrency

### 12.1. Effective CPU budget

Đặt:

- `C_quota`: số CPUs tương đương từ quota/period.
- `C_cpuset`: số CPUs trong effective cpuset.
- `C_host`: CPU capacity thực sự có thể dùng trên host sau các giới hạn khác.

Effective CPU budget gần đúng:

```text
C_effective = min(C_quota, C_cpuset, C_host)
```

Nếu không có quota, bỏ thành phần đó; nếu không có cpuset, dùng CPU set được host/container cấp. Đây là mô hình sizing gần đúng, không phải scheduler guarantee.

### 12.2. Ước lượng active processes

Với `Q` parallel queries đồng thời, mỗi query dùng tối đa `W` workers, số process runnable ở parallel portion có thể xấp xỉ:

```text
Parallel workers ≈ Q × W
Leader backends ≈ Q
Total parallel execution processes ≈ Q × (W + 1)
```

Con số thực tế thấp hơn khi query không launch đủ workers, leader không tham gia hoặc có ít active queries; nhưng cần tính cả background processes và các workload khác.

### 12.3. Ví dụ oversubscription

Giả sử container có CPU limit 4 cores. 4 queries đồng thời, mỗi query yêu cầu 4 workers và một leader:

```text
4 queries × (4 workers + 1 leader) = 20 processes
CPU budget = 4 cores
```

20 runnable processes sẽ tranh 4 CPU equivalents nếu tất cả đang CPU-bound. Tăng workers có thể tăng context switching và queueing thay vì tăng throughput.

### 12.4. Ví dụ budget thận trọng hơn

Với CPU budget 8 cores và 2 analytics queries đồng thời, mỗi query dùng 3 workers cộng leader:

```text
2 × (3 + 1) = 8 execution processes
CPU budget = 8 cores
```

Đây là một điểm thử nghiệm hợp lý hơn cho CPU-bound queries, nhưng còn phải trừ CPU cho autovacuum, WAL, checkpoints, connections, OS và background services.

### 12.5. Không phải mọi process đều CPU-bound

Query có thể chờ disk I/O, lock, network hoặc buffer reads. Khi I/O-bound, thêm workers có thể tăng queue depth và storage contention. Khi CPU-bound, thêm workers chỉ có lợi tới khi CPU capacity hoặc leader/gather trở thành bottleneck.

### 12.6. Công thức sizing không thay benchmark

Dùng process estimate để tránh cấu hình vô lý, sau đó benchmark với workload đại diện và concurrency thật. Không áp dụng một tỷ lệ workers/CPU cố định cho mọi database.

### 12.7. Chừa headroom

Không cấp toàn bộ CPU budget cho parallel query. Chừa headroom cho:

- Client backends và OLTP queries.
- WAL writer, checkpointer, background writer.
- Autovacuum và replication.
- OS kernel, monitoring/agents và storage/network interrupts.
- Bursty traffic và maintenance.

### 12.8. OLTP và analytics cùng server

Một query analytics có thể dùng nhiều workers và chiếm CPU trong thời gian dài, làm tăng p95/p99 latency của OLTP. Dùng role/database limits, workload separation hoặc dedicated read replica để kiểm soát impact.

### 12.9. CPU limits và parallelism phải tuning cùng nhau

Nếu Kubernetes CPU limit giảm từ 8 xuống 2 cores mà `max_parallel_workers` giữ nguyên, query có thể launch số workers cũ nhưng bị throttled. Sau khi đổi quota, đánh giá lại per-gather limit, query concurrency và maintenance budget.

### 12.10. NUMA và CPU topology

Máy nhiều sockets/NUMA nodes có thể có memory locality khác nhau. Shared buffers, worker processes và memory allocations có thể chịu remote NUMA access. Không pin workers vào cores tùy tiện; benchmark trên topology thật và xem OS NUMA policy/metrics.

## 13. Memory, I/O và các tài nguyên đi cùng parallelism

### 13.1. Parallel workers cũng dùng memory

Workers thực thi các plan nodes như sort, hash join và hash aggregate. Những operations này có thể dùng memory theo process. Tăng số workers có thể làm tổng memory demand tăng, kể cả khi query logic không đổi.

### 13.2. work_mem không phải memory limit toàn query

`work_mem` là memory budget cho một số operations như sort/hash trước khi spill ra disk. Một query có thể có nhiều sort/hash nodes và nhiều parallel processes. Vì vậy không tính memory bằng một lần `work_mem`.

Ước lượng thận trọng:

```text
Memory demand ≈ active processes
                × concurrent memory-heavy plan nodes
                × per-operation memory budget
```

Đây là upper-bound planning model, không phải mọi operation đều dùng hết budget cùng lúc. PostgreSQL version mới có thêm các controls như `hash_mem_multiplier`; kiểm tra đúng version.

### 13.3. Ví dụ memory amplification

Nếu 4 queries đồng thời, mỗi query có 3 workers + leader, và mỗi process có một hash operation có thể dùng tới 64 MB:

```text
4 queries × 4 processes × 64 MB = 1024 MB
```

Đây chỉ là một hash node trên mỗi process. Nếu có nhiều hash/sort nodes hoặc autovacuum/maintenance cùng chạy, tổng demand có thể cao hơn. Không đặt `work_mem` dựa vào RAM chia cho `max_connections` đơn giản.

### 13.4. Hash spill và sort spill

Khi memory không đủ, sort/hash có thể spill ra temporary files. Parallelism có thể tăng tổng I/O của temp files nếu nhiều workers cùng spill. Xem `EXPLAIN ANALYZE` temp read/write blocks, `log_temp_files` và filesystem capacity.

### 13.5. Shared buffers và OS page cache

Parallel workers truy cập shared buffers và OS cache. Nhiều workers có thể tăng concurrent page access, nhưng không tạo thêm RAM. Nếu working set đã vượt memory, storage reads có thể là bottleneck.

### 13.6. I/O bandwidth

Parallel sequential scan có thể tăng throughput khi storage còn dư bandwidth. Nếu disk/NVMe/network storage đã bão hòa, workers chỉ tăng queue depth và latency.

Theo dõi throughput, IOPS, queue depth, read latency, cache hit ratio và `pg_stat_io` trên các PostgreSQL versions hỗ trợ.

### 13.7. Buffer contention và locks

Một query song song có thể làm tăng concurrent buffer access, lightweight lock activity và contention ở shared structures. Nếu CPU usage không cao nhưng workers chờ lẫn nhau, tăng worker count có thể làm tình trạng tệ hơn.

### 13.8. WAL và replication

Parallel query read-only thường không tạo WAL cho mỗi row được đọc, nhưng parallel maintenance hoặc workload khác có thể tạo WAL đáng kể. CPU/I/O contention từ parallel jobs có thể làm WAL flush, checkpoints và replication replay chậm.

### 13.9. Temporary storage

Đảm bảo temp tablespace/filesystem đủ capacity và latency. Nhiều workers spill cùng lúc có thể làm đầy temp disk, gây query failures và ảnh hưởng workload khác.

### 13.10. Memory cgroup limits

Container memory limit là hard boundary. Shared buffers, backend private memory, worker private memory, maintenance, OS page cache và extension allocations cùng tiêu thụ cgroup memory. Nếu vượt limit, kernel có thể OOM-kill process/container.

Không tăng worker count nếu chưa đánh giá memory headroom và temp I/O.

## 14. Đọc và đo parallel plans

### 14.1. EXPLAIN trước khi tuning

Dùng `EXPLAIN` để xem planner chọn plan nào:

```sql
EXPLAIN (COSTS, VERBOSE, SETTINGS)
SELECT customer_id, count(*)
FROM large_orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY customer_id;
```

Tìm `Gather`, `Gather Merge`, `Parallel Seq Scan`, `Parallel Append`, partial/final aggregate hoặc các nodes khác có parallel behavior.

### 14.2. EXPLAIN ANALYZE

Để đo execution thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT customer_id, count(*)
FROM large_orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY customer_id;
```

`ANALYZE` thực thi câu query. Chỉ chạy trên statement an toàn với dữ liệu và tải production; với DML/DDL, phải hiểu side effects và có kế hoạch rollback phù hợp.

### 14.3. Đọc Gather

Ví dụ minh họa:

```text
Finalize Aggregate
  -> Gather
       Workers Planned: 4
       Workers Launched: 4
       -> Partial Aggregate
            -> Parallel Seq Scan on large_orders
```

Diễn giải:

- Planner muốn 4 workers.
- Cả 4 workers được launch trong lần chạy này.
- Mỗi process tính partial aggregate trên phần dữ liệu của mình.
- Leader gather partial results và finalize aggregate.

### 14.4. Workers Launched thấp hơn Planned

Ví dụ `Workers Planned: 4` nhưng `Workers Launched: 1`. Kiểm tra:

- `max_parallel_workers` đã hết slot chưa?
- `max_worker_processes` còn capacity không?
- Background workers khác có chiếm slot không?
- Có process limit hoặc resource exhaustion không?
- Nhiều queries parallel đang chạy đồng thời không?
- Logs có thông báo worker launch failure không?

Không nhất thiết query thất bại; nó có thể chạy với fewer workers.

### 14.5. Actual rows và loops

`EXPLAIN ANALYZE` hiển thị actual rows/loops cho nodes. Với parallel nodes, số liệu có thể được tổng hợp theo worker/leader hoặc hiển thị chi tiết từng worker khi dùng `VERBOSE`. Hiểu cách PostgreSQL trình bày rows/loops trước khi cộng số liệu thủ công.

### 14.6. Per-worker skew

Nếu worker 0 xử lý nhiều rows hơn worker 1 rất nhiều hoặc có thời gian chạy dài hơn, workload có skew. Nguyên nhân có thể là block distribution, partition sizes, data clustering, join key distribution hoặc uneven task cost.

Tăng workers không nhất thiết chữa skew; cần xem partitioning, predicates, join distribution và plan.

### 14.7. Planning time và execution time

Parallel plan có planning/setup overhead. Với query nhỏ, execution có thể ngắn nhưng worker startup/gather làm total latency tăng. So sánh execution time và end-to-end latency trong cùng điều kiện.

### 14.8. Buffers

`BUFFERS` cho biết shared/local/temp blocks hit/read/dirtied/written. Parallel workers có thể làm aggregate buffer counts lớn. Dùng để phân biệt cache hits, physical reads và temp spill; không xem block count như CPU time.

### 14.9. Settings

`SETTINGS` giúp hiển thị planner-related settings khác default có ảnh hưởng plan. Lưu lại cấu hình session/server khi benchmark để so sánh công bằng.

### 14.10. So sánh serial và parallel

Trong lab, có thể so sánh:

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT count(*) FROM large_fact_table;
ROLLBACK;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT count(*) FROM large_fact_table;
```

Lần đầu ép serial trong transaction; lần sau dùng setting mặc định. Lặp lại nhiều lần và kiểm soát cache state/concurrency. Không so một lần cold-cache với một lần warm-cache.

## 15. Monitoring parallel workers

### 15.1. pg_stat_activity

`pg_stat_activity` cho biết các backends hiện hoạt động. Trên các PostgreSQL versions có hỗ trợ, có thể xem `backend_type`, `leader_pid`, `query`, `state`, `wait_event_type` và `wait_event` để nhận diện parallel workers và leader.

Ví dụ:

```sql
SELECT
    pid,
    leader_pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE backend_type = 'parallel worker'
   OR leader_pid IS NOT NULL
ORDER BY leader_pid NULLS FIRST, pid;
```

Một số columns phụ thuộc major version. Nếu server cũ không có `leader_pid` hoặc `backend_type`, điều chỉnh query theo catalog/view version.

### 15.2. Đếm worker processes

```sql
SELECT
    backend_type,
    state,
    count(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type, state
ORDER BY backend_type, state;
```

Đếm process snapshot chỉ phản ánh thời điểm query. Worker lifetime ngắn có thể không xuất hiện nếu lấy mẫu quá thưa.

### 15.3. Xem query leader và workers

```sql
SELECT
    pid,
    leader_pid,
    backend_type,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_text
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
```

Nhóm các rows có cùng `leader_pid` để hiểu worker processes thuộc query nào.

### 15.4. pg_stat_statements

`pg_stat_statements` giúp tổng hợp query workload: calls, total/mean execution time, rows, shared blocks, temp blocks và các counters khác tùy version. Dùng để xác định query classes cần tối ưu.

Stats thường tổng hợp theo normalized query identity; chúng không thay thế EXPLAIN cho một execution cụ thể. Không suy luận worker count chỉ từ mean execution time.

### 15.5. pg_stat_io

Trên PostgreSQL versions hỗ trợ `pg_stat_io`, view này cung cấp I/O statistics theo backend type/object/context. Nó giúp hiểu read/write patterns và I/O impact; không phải trực tiếp là CPU profile.

### 15.6. OS CPU metrics

Theo dõi:

- CPU user/system/iowait/steal.
- Run queue và load average.
- Context switches.
- CPU pressure stall information (PSI) nếu có.
- Per-process CPU của PostgreSQL backends/workers.
- Cgroup quota/throttling.

Load average cao có thể do runnable processes hoặc uninterruptible I/O waits; không dùng một con số load average để kết luận CPU saturation.

### 15.7. Kubernetes metrics

Theo dõi CPU usage và throttling theo container, Pod restart/OOM, node pressure và requests/limits. Một database Pod có thể hiển thị usage dưới limit nhưng bị throttled trong burst periods; dùng throttled periods/time cùng query latency.

### 15.8. Replication metrics

Parallel maintenance hoặc CPU pressure có thể làm standby replay chậm. Monitor receive/replay LSN, replication lag, WAL archive backlog và synchronous waits để biết parallel jobs có ảnh hưởng HA không.

### 15.9. Query latency percentiles

Đo p50/p95/p99 theo query class và endpoint. Parallelism có thể giảm runtime của batch query nhưng làm tail latency OLTP tăng do CPU contention. Throughput tổng thể và latency distribution quan trọng hơn một query benchmark riêng lẻ.

### 15.10. Dashboard tối thiểu

Dashboard parallelism nên có:

- CPU budget thực tế và quota/throttling.
- Active parallel queries và worker processes.
- Workers Planned/Launched từ representative EXPLAIN samples.
- `max_worker_processes`/`max_parallel_workers` usage headroom.
- CPU run queue/context switches.
- Memory/temp spill/I/O metrics.
- Query p95/p99 và throughput.
- Replication lag và maintenance activity.

## 16. Quy trình tuning parallelism

### 16.1. Bước 1: xác định mục tiêu

Xác định đang tối ưu:

- Runtime một analytics query lớn.
- Throughput batch workload.
- OLTP p95/p99 latency.
- Index build/reindex duration.
- CPU cost hoặc cloud/container cost.

Một setting có thể giúp query đơn lẻ nhưng làm giảm throughput tổng thể.

### 16.2. Bước 2: đo CPU capacity thật

Xác định CPU quota, cpuset, node capacity và các workloads dùng chung. Trong container, không lấy `nproc` trên host làm CPU budget nếu cgroup limit thấp hơn.

### 16.3. Bước 3: baseline query

Chọn query đại diện, ghi:

- SQL và bind values/selectivity.
- `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)`.
- Execution time, rows, loops, buffers, temp I/O.
- Workers planned/launched.
- CPU usage và I/O latency.
- Concurrent workload lúc benchmark.

### 16.4. Bước 4: kiểm tra query shape

Xem có index phù hợp, partition pruning, join order, row estimates và filter pushdown không. Sửa query/schema/statistics trước nếu plan đang scan/join quá nhiều dữ liệu do ước lượng sai.

### 16.5. Bước 5: điều chỉnh worker limits

Chọn `max_parallel_workers_per_gather` theo loại query và concurrency. Bảo đảm `max_parallel_workers` và `max_worker_processes` đủ nhưng không vượt worker/CPU/memory budget.

### 16.6. Bước 6: điều chỉnh planner costs

Chỉ sau khi baseline cho thấy planner chọn sai parallel/serial plan, thử thay đổi `parallel_setup_cost`, `parallel_tuple_cost` hoặc min scan thresholds. Thay đổi từng setting một và lưu lại kết quả.

### 16.7. Bước 7: benchmark concurrency thật

Chạy workload với số queries đồng thời gần production. Một query chạy đơn lẻ có thể nhanh hơn với 8 workers; 10 queries cùng lúc có thể tốt hơn khi mỗi query dùng 1–2 workers.

### 16.8. Bước 8: kiểm tra side effects

Đo OLTP latency, CPU throttling, temp files, memory, I/O, replication lag và maintenance duration. Không chấp nhận speedup một query nếu làm SLA hệ thống xấu đi.

### 16.9. Bước 9: rollout có kiểm soát

Thay đổi config theo maintenance/change process. Ghi config cũ, áp dụng trên staging, đo trước/sau, canary hoặc rolling change nếu phù hợp và chuẩn bị rollback.

### 16.10. Bước 10: xác nhận ổn định

Quan sát đủ chu kỳ peak/off-peak. Cấu hình tốt phải cải thiện mục tiêu mà không gây worker starvation, CPU throttling, memory pressure hoặc tail latency regression.

## 17. Chẩn đoán các tình huống thường gặp

### 17.1. Query không có Gather

Kiểm tra query size, parallel safety, cost thresholds, table statistics, `max_parallel_workers_per_gather` và plan shape. Dùng `EXPLAIN` để xác định planner đã chọn index scan/serial plan vì lý do nào.

### 17.2. Workers Planned lớn nhưng Launched thấp

Kiểm tra global parallel worker cap, background worker slots, concurrent queries và logs. So sánh worker demand theo thời điểm, không chỉ lúc query đơn lẻ.

### 17.3. Workers Launched bằng zero

Query có thể fallback thực thi parallel plan với leader nếu không có workers, tùy plan. Xem EXPLAIN ANALYZE, logs và worker pool. Không giả định mọi query sẽ fail khi không launch được worker.

### 17.4. Tăng workers nhưng query không nhanh hơn

Nguyên nhân có thể là CPU quota, storage bandwidth, leader gather, memory spill, skew, lock/buffer contention hoặc phần serial lớn. Xác định critical path thay vì tiếp tục tăng workers.

### 17.5. CPU usage thấp nhưng query chậm

Kiểm tra I/O wait, lock waits, storage latency, network/FDW, temp file I/O, CPU throttling và waits trong `pg_stat_activity`. CPU usage thấp có thể nghĩa là process đang chờ.

### 17.6. CPU usage 100% và latency tăng

Kiểm tra runnable queue, active queries, parallel worker count, background jobs và cgroup throttling. Giảm per-query workers hoặc concurrency có thể cải thiện tổng throughput.

### 17.7. CPU throttling tăng

So sánh CPU limit/quota với actual runnable processes. Nếu quota bị throttled liên tục, điều chỉnh CPU limit/request hoặc giảm parallelism/concurrency. Không chỉ tăng `max_parallel_workers`.

### 17.8. Temp files tăng mạnh

Kiểm tra sort/hash nodes, `work_mem`, worker count và concurrent memory-heavy queries. Xác định spill có phải do parallel worker multiplication hay plan cardinality sai.

### 17.9. Replication lag tăng khi chạy report

Kiểm tra CPU, storage I/O, checkpoint/WAL pressure và standby replay throughput. Giảm report concurrency/parallelism hoặc route report tới replica chuyên dụng.

### 17.10. Parallel plan xuất hiện cho query nhỏ

Planner costs/thresholds có thể quá thấp hoặc estimates sai. So sánh actual rows/size, tăng cost phù hợp hoặc sửa statistics. Tránh disable parallelism toàn cluster chỉ vì một query.

### 17.11. Query OLTP bị chậm khi batch chạy

Batch query có thể chiếm CPU, cache, I/O và worker slots. Giới hạn role/database, schedule batch, dùng resource isolation hoặc tách analytics workload.

### 17.12. Worker slots bị background jobs chiếm

Kiểm tra logical replication, extension workers và maintenance jobs. Định sizing `max_worker_processes` có headroom, nhưng không đặt quá cao so với host capacity.

### 17.13. Không thấy parallel worker trong pg_stat_activity

Worker có thể kết thúc trước khi query monitor snapshot; query có thể không parallel; hoặc version/view columns khác. Dùng EXPLAIN ANALYZE và lấy mẫu nhanh hơn trong lab.

### 17.14. Một worker chậm hơn hẳn

Kiểm tra skew của data/partition, worker CPU affinity, NUMA, storage path và plan nodes. Một straggler có thể quyết định total query completion time.

### 17.15. CREATE INDEX làm OLTP chậm

Parallel maintenance tiêu thụ CPU, memory và I/O. Hạ `max_parallel_maintenance_workers`, schedule ngoài peak và monitor replication/WAL.

### 17.16. Container restart sau khi tăng workers

Kiểm tra OOM events, memory limit, `work_mem`, parallel sort/hash nodes và active query concurrency. CPU worker count không phải nguyên nhân duy nhất; workers có thể khuếch đại memory use.

## 18. Labs thực hành

Các lab cần PostgreSQL instance disposable hoặc staging có tải kiểm soát. Thay table names, paths và values theo môi trường. Không thay đổi global settings hay chạy stress tests trên production nếu chưa có change plan.

### Lab 1. Quan sát một parallel sequential scan

#### Bước 1. Tạo bảng dữ liệu

```sql
CREATE TABLE parallel_lab AS
SELECT
    g AS id,
    md5(g::text) AS payload,
    (g % 1000)::integer AS bucket
FROM generate_series(1, 5000000) AS g;

ANALYZE parallel_lab;
```

#### Bước 2. Xem cấu hình hiện tại

```sql
SHOW max_worker_processes;
SHOW max_parallel_workers;
SHOW max_parallel_workers_per_gather;
SHOW min_parallel_table_scan_size;
SHOW parallel_setup_cost;
SHOW parallel_tuple_cost;
```

#### Bước 3. Xem plan

```sql
EXPLAIN (COSTS, VERBOSE, SETTINGS)
SELECT count(*)
FROM parallel_lab
WHERE bucket < 500;
```

Tìm `Gather` và `Parallel Seq Scan`. Nếu không có, xem table size, cost, statistics và parallel safety.

#### Bước 4. Chạy thực tế

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT count(*)
FROM parallel_lab
WHERE bucket < 500;
```

Ghi Workers Planned/Launched, actual time, rows, buffers và temp I/O nếu có.

#### Bước 5. So sánh serial

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT count(*) FROM parallel_lab WHERE bucket < 500;
ROLLBACK;
```

Chạy nhiều lần và so sánh trong điều kiện cache/concurrency tương đương.

### Lab 2. Thay đổi workers per Gather

#### Bước 1. Lưu baseline

Ghi giá trị hiện tại và EXPLAIN ANALYZE của query Lab 1.

#### Bước 2. Thử mức thấp

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 1;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT bucket, count(*)
FROM parallel_lab
GROUP BY bucket;
ROLLBACK;
```

#### Bước 3. Thử mức trung bình

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 2;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT bucket, count(*)
FROM parallel_lab
GROUP BY bucket;
ROLLBACK;
```

#### Bước 4. Thử mức cao hơn nếu budget cho phép

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 4;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT bucket, count(*)
FROM parallel_lab
GROUP BY bucket;
ROLLBACK;
```

#### Bước 5. Ghi kết quả

Tạo bảng so sánh workers planned/launched, execution time, CPU, buffers, temp I/O và latency của workload đồng thời. Chọn mức tốt nhất theo mục tiêu throughput/SLA, không nhất thiết là mức nhanh nhất cho một query isolated.

### Lab 3. Parallel safety của function

#### Bước 1. Tạo function lab

```sql
CREATE FUNCTION parallel_lab_upper(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT upper($1);
$$;
```

#### Bước 2. Dùng function trong query

```sql
EXPLAIN (VERBOSE)
SELECT count(*)
FROM parallel_lab
WHERE parallel_lab_upper(payload) LIKE 'A%';
```

#### Bước 3. Đổi classification trong lab

```sql
ALTER FUNCTION parallel_lab_upper(text) PARALLEL UNSAFE;
```

Chạy EXPLAIN lại để quan sát planner có loại parallel plan hay không. Kết quả phụ thuộc query/cost/plan nodes; không phải mọi query sẽ thay đổi.

#### Bước 4. Khôi phục classification

```sql
ALTER FUNCTION parallel_lab_upper(text) PARALLEL SAFE;
```

Chỉ đánh dấu safe nếu implementation thực sự an toàn. Lab function này chỉ gọi upper() trên text.

### Lab 4. Quan sát worker allocation khi có concurrency

#### Bước 1. Chuẩn bị query chạy lâu vừa phải

Chọn một query scan/aggregate đủ lớn trên bảng lab. Không dùng workload không giới hạn.

#### Bước 2. Mở nhiều sessions

Chạy query đồng thời ở 2–4 sessions trong môi trường lab. Cấu hình mỗi session yêu cầu một số workers vừa phải.

#### Bước 3. Quan sát active processes

```sql
SELECT
    pid,
    leader_pid,
    backend_type,
    state,
    now() - query_start AS age
FROM pg_stat_activity
WHERE backend_type = 'parallel worker'
   OR leader_pid IS NOT NULL
ORDER BY leader_pid, pid;
```

#### Bước 4. So sánh planned và launched

Lấy EXPLAIN ANALYZE cho từng query. Quan sát worker allocation khi các sessions cạnh tranh cùng `max_parallel_workers`.

#### Bước 5. Giảm per-query demand

Giảm `max_parallel_workers_per_gather` trong lab và lặp lại. So sánh tổng throughput và p95 latency của sessions.

### Lab 5. Quan sát CPU quota/throttling

#### Bước 1. Chọn môi trường container lab

Dùng container riêng với CPU limit thấp có thể kiểm soát. Không thay quota của production database.

#### Bước 2. Ghi CPU limit

Trong Linux cgroup v2, đọc `cpu.max`, `cpu.stat` và `cpuset.cpus.effective` của container chứa PostgreSQL.

#### Bước 3. Chạy workload CPU-bound

Chạy query lab scan/aggregate với workers per Gather thấp, rồi tăng dần. Thu thập query latency, CPU usage và throttled periods/time.

#### Bước 4. Đối chiếu

Nếu CPU throttling tăng cùng lúc query latency tăng, thử giảm workers hoặc concurrency. Không chỉ tăng `max_parallel_workers`.

#### Bước 5. Lưu kết quả

Ghi CPU quota, cpuset, worker count, concurrent query count, throttling và throughput. So sánh trước/sau.

### Lab 6. Parallel maintenance

#### Bước 1. Tạo index lab

```sql
CREATE INDEX parallel_lab_bucket_idx
ON parallel_lab(bucket);
```

#### Bước 2. Rebuild index

Trong một cluster disposable, thử:

```sql
REINDEX INDEX parallel_lab_bucket_idx;
```

#### Bước 3. Thử maintenance workers

Xem `max_parallel_maintenance_workers` và giới hạn global worker pool. Nếu môi trường hỗ trợ, so sánh operation với worker setting khác nhau.

#### Bước 4. Theo dõi side effects

Đo CPU, I/O, WAL generation, disk space, replication lag và application latency. Không chạy nhiều index builds lớn đồng thời nếu chưa có capacity plan.

### Lab 7. Dọn môi trường

```sql
DROP FUNCTION IF EXISTS parallel_lab_upper(text);
DROP TABLE IF EXISTS parallel_lab;
```

Chỉ dọn các objects do lab tạo. Khôi phục session/global settings đã thay đổi và xác nhận không còn workload lab đang chạy.

## 19. Ví dụ sizing và quyết định cấu hình

### 19.1. Server analytics 16 CPUs

Giả sử database có 16 CPUs thực sự được cấp và workload chủ yếu là 2–3 analytics queries đồng thời cùng một số maintenance jobs. Có thể bắt đầu thử với per-Gather 2–4 workers, global parallel workers ở mức đủ cho concurrency mục tiêu và chừa CPU headroom. Đo trước khi tăng.

### 19.2. PostgreSQL OLTP 4 CPUs

Với workload OLTP latency-sensitive trên 4 CPUs, nhiều queries nhỏ thường không hưởng lợi từ parallel query. Giữ per-Gather thấp hoặc 0 cho role OLTP nếu benchmark chứng minh tốt hơn; dành workers cho báo cáo có giới hạn riêng.

### 19.3. Kubernetes Pod limit 2 CPUs

Nếu Pod chỉ có 2 CPUs quota, per-Gather 8 workers có thể oversubscribe nặng. Bắt đầu với parallelism thấp, theo dõi throttling, p95/p99 và concurrency. CPU request không được coi là hard cap nếu limit khác.

### 19.4. Dedicated reporting replica

Một replica dành cho reporting có thể cho phép per-query parallelism cao hơn vì không cạnh tranh trực tiếp với write primary. Nhưng vẫn phải monitor CPU, I/O, replay lag, recovery conflicts và synchronous/HA policy.

### 19.5. Index build maintenance window

Trong maintenance window, có thể tăng maintenance workers nếu CPU/storage còn headroom. Khi ứng dụng trở lại peak, khôi phục giới hạn phù hợp để tránh cạnh tranh.

### 19.6. Không có cấu hình universal

Hai server cùng CPU count vẫn có thể cần cấu hình khác vì khác storage, NUMA, CPU generation, cgroup quota, query shape, cache hit ratio, memory, concurrency và SLA.

## 20. Những sai lầm thường gặp

### 20.1. Càng nhiều workers càng nhanh

Workers có diminishing returns và có thể làm CPU, memory, I/O, gather và context switching quá tải. Benchmark ở concurrency thực tế.

### 20.2. Nhầm worker count với CPU count

Worker là process; CPU là tài nguyên scheduling. Có thể có nhiều workers hơn CPUs nhưng chúng sẽ time-share và tranh quota.

### 20.3. Chỉ tăng max_parallel_workers_per_gather

Global limits, worker slots, CPU quota, memory và background workers vẫn giới hạn execution. Tăng một per-query cap không tạo thêm capacity.

### 20.4. Bỏ qua max_worker_processes

Parallel worker pool phải có slots trong background worker pool. Đặt global parallel cap cao hơn available worker slots không giúp launch thêm processes.

### 20.5. Nhầm max_connections với worker capacity

Client backend connections và background worker processes là hai nhóm khác nhau. Tăng max_connections không sửa worker allocation.

### 20.6. Nghĩ Workers Planned là số worker chắc chắn chạy

Đây chỉ là planner target. Workers Launched phản ánh execution thực tế và có thể thấp hơn khi global pool bận.

### 20.7. Dùng benchmark một query làm đại diện production

Query đơn lẻ có thể nhận đủ workers; production concurrency khiến worker slots và CPU cạnh tranh. Benchmark với workload mix.

### 20.8. Bỏ qua parallel safety

Function/extension unsafe có thể khiến query không parallel. Không tự đánh dấu SAFE nếu function có side effects hoặc phụ thuộc session state.

### 20.9. Nhầm IMMUTABLE với PARALLEL SAFE

Volatility và parallel safety là thuộc tính riêng. IMMUTABLE không tự chứng minh function có thể chạy trong workers.

### 20.10. Dùng force parallel để sửa query

Ép planner không sửa missing index, bad statistics, poor join order hay I/O bottleneck. Tìm nguyên nhân plan trước.

### 20.11. Hạ parallel_setup_cost quá thấp

Planner có thể parallelize query nhỏ, làm tăng startup overhead và worker churn.

### 20.12. Hạ parallel_tuple_cost quá thấp

Planner có thể chọn plan phải gather quá nhiều tuples, tạo leader bottleneck.

### 20.13. Bỏ qua statistics

Row estimates sai có thể khiến planner chọn parallel plan không phù hợp hoặc không chọn parallel plan khi đáng lẽ có lợi. Chạy ANALYZE và kiểm tra estimate/actual.

### 20.14. Tính work_mem một lần cho cả query

Nhiều plan nodes và parallel processes có thể dùng memory riêng. Tính theo active operations và concurrency, không theo một process duy nhất.

### 20.15. Bỏ qua temp spill

Parallel sort/hash có thể spill nhiều temp files cùng lúc. Monitor temp I/O và temp filesystem.

### 20.16. Tăng workers khi storage đã bão hòa

Nếu I/O bandwidth đã hết, thêm workers chỉ làm queue depth/latency tăng. Kiểm tra disk throughput và latency.

### 20.17. Bỏ qua leader gather bottleneck

Leader phải tiêu thụ tuples và thực hiện final nodes. Workers nhanh hơn không giúp nếu leader/gather là bottleneck.

### 20.18. Tăng workers trên container CPU limit thấp

PostgreSQL không tự nhận worker count theo quota trong mọi setup. Tuning theo CPU budget thực tế và monitor throttling.

### 20.19. Nhầm CPU request với CPU limit

Kubernetes request là scheduling reservation/relative share; limit là hard quota. Đọc cả hai.

### 20.20. Chỉ xem CPU usage, bỏ throttling

Container có thể bị throttled theo quota dù average usage không luôn ở 100%. Kiểm tra cgroup `cpu.stat`/container metrics.

### 20.21. Chỉ xem load average

Load average có thể bao gồm I/O waits. Dùng run queue, CPU utilization, iowait, PSI và process-level metrics.

### 20.22. Tuning song song nhiều settings

Không biết setting nào tạo thay đổi. Thử từng setting, lưu baseline và rollback rõ.

### 20.23. Chạy EXPLAIN ANALYZE trên DML/DDL không an toàn

EXPLAIN ANALYZE thực thi statement. Cần hiểu side effects, transaction rollback behavior và lock impact trước khi chạy.

### 20.24. Chạy lab stress trên production

Stress query có thể làm CPU/I/O/worker pool bão hòa. Dùng disposable/staging và giới hạn concurrency.

### 20.25. Bỏ qua maintenance contention

Parallel index build có thể tranh worker slots, CPU và I/O với SELECT workload. Schedule và giới hạn maintenance workers.

### 20.26. Không xem p95/p99

Một query nhanh hơn không có nghĩa ứng dụng tốt hơn nếu OLTP tail latency xấu đi. Theo dõi latency distribution.

### 20.27. Không monitor background workers

Logical replication/extension workers có thể chiếm max_worker_processes capacity. Tính chúng trong worker budget.

### 20.28. Không xem replication lag

CPU/I/O pressure có thể làm standby replay chậm. Parallel maintenance/reporting có thể ảnh hưởng HA.

### 20.29. Pin workers tùy tiện

CPU affinity/NUMA pinning không đúng có thể làm memory locality và scheduling kém hơn. Chỉ thay đổi sau benchmark trên hardware thật.

### 20.30. Không rollback sau tuning

Mỗi thay đổi phải có baseline, owner, rollout window và rollback procedure. Giữ config cũ để phục hồi khi latency hoặc resource pressure xấu đi.

## 21. Bài tập thực hành

### Bài 1. Khái niệm

Parallel query của PostgreSQL là gì? Nó khác distributed query execution như thế nào?

### Bài 2. Process roles

Phân biệt leader backend, parallel worker, background worker và client connection.

### Bài 3. Gather

Vai trò của Gather và Gather Merge khác nhau ở điểm nào?

### Bài 4. Worker allocation

Workers Planned và Workers Launched có ý nghĩa gì? Vì sao hai số có thể khác nhau?

### Bài 5. Parallel safety

Phân biệt PARALLEL SAFE, PARALLEL RESTRICTED và PARALLEL UNSAFE.

### Bài 6. Function properties

Vì sao IMMUTABLE không tự động có nghĩa function PARALLEL SAFE?

### Bài 7. Worker limits

Phân biệt max_worker_processes, max_parallel_workers và max_parallel_workers_per_gather.

### Bài 8. Maintenance

max_parallel_maintenance_workers dùng cho loại operations nào? Nó có pool độc lập không?

### Bài 9. Planner thresholds

min_parallel_table_scan_size và min_parallel_index_scan_size ảnh hưởng planner ra sao?

### Bài 10. Cost

parallel_setup_cost và parallel_tuple_cost đại diện cho loại overhead nào?

### Bài 11. Leader participation

parallel_leader_participation điều khiển điều gì? Khi nào leader có thể trở thành gather bottleneck?

### Bài 12. CPU quota

Một container có `cpu.max` là `200000 100000`. CPU quota xấp xỉ bao nhiêu CPU equivalents?

### Bài 13. Kubernetes

Phân biệt `resources.requests.cpu` và `resources.limits.cpu`.

### Bài 14. Worker demand

Có 3 queries đồng thời, mỗi query yêu cầu 2 workers và một leader. Ước lượng số parallel execution processes nếu tất cả workers được cấp.

### Bài 15. Oversubscription

Vì sao 20 parallel workers trên container có CPU limit 4 cores có thể làm latency xấu đi?

### Bài 16. Memory

Vì sao tăng workers có thể làm memory demand tăng ngay cả khi work_mem không đổi?

### Bài 17. I/O

Nêu hai tình huống parallel scan không giúp query nhanh hơn vì storage.

### Bài 18. EXPLAIN

Trong EXPLAIN ANALYZE, cần xem những dấu hiệu nào để đánh giá parallel plan?

### Bài 19. Monitoring

View nào giúp quan sát parallel workers và leader_pid? Nêu các metrics OS/container cần theo dõi.

### Bài 20. CPU throttling

Một query có Workers Launched đủ nhưng latency tăng cùng throttled periods. Nên điều tra/điều chỉnh gì?

### Bài 21. Parallel maintenance

Vì sao CREATE INDEX parallel có thể ảnh hưởng OLTP queries?

### Bài 22. Query không parallel

Nêu ít nhất bốn nguyên nhân khiến query không có Gather.

### Bài 23. Worker launch shortage

Workers Planned là 4, Workers Launched là 1. Nêu các nhóm nguyên nhân cần kiểm tra.

## 22. Gợi ý lời giải bài tập

### Đáp án 1. Khái niệm

Parallel query chia một query plan thành các phần được thực thi đồng thời bởi leader và parallel workers trên cùng PostgreSQL instance. Distributed query execution phân phối công việc qua nhiều database servers/nodes; parallel workers core không tự tạo distributed database.

### Đáp án 2. Process roles

- Leader backend: process phục vụ client, điều phối parallel query và nhận kết quả.
- Parallel worker: background worker thực thi một phần parallel plan.
- Background worker: nhóm process nền rộng hơn, có thể gồm logical replication, extension và parallel workers.
- Client connection: kết nối ứng dụng tạo backend session; không phải worker slot.

### Đáp án 3. Gather

`Gather` gom tuples từ leader/workers mà không giữ ordering tổng thể. `Gather Merge` merge các sorted streams để giữ thứ tự của plan.

### Đáp án 4. Worker allocation

Workers Planned là số planner dự kiến yêu cầu; Workers Launched là số thực tế khởi chạy. Chúng khác nhau khi global pool bận, `max_worker_processes` thiếu slots, background workers chiếm capacity hoặc OS/process resource không đủ.

### Đáp án 5. Parallel safety

- SAFE: được chạy trong parallel workers.
- RESTRICTED: chỉ chạy ở leader, không chạy trong workers.
- UNSAFE: query không được chạy trong parallel mode.

### Đáp án 6. Function properties

IMMUTABLE mô tả function không thay đổi kết quả theo database state/arguments theo semantics volatility. PARALLEL SAFE mô tả khả năng chạy trong parallel context mà không gây side effects/race. Hai thuộc tính kiểm tra hai khía cạnh khác nhau.

### Đáp án 7. Worker limits

- `max_worker_processes`: trần background worker processes toàn server.
- `max_parallel_workers`: trần parallel workers toàn cluster.
- `max_parallel_workers_per_gather`: trần workers cho một Gather/Gather Merge node.

Parallel workers phải thỏa cả global parallel cap và available background worker slots.

### Đáp án 8. Maintenance

`max_parallel_maintenance_workers` điều khiển workers cho maintenance operations hỗ trợ như một số index builds/reindex. Nó không có pool process độc lập; workers vẫn dùng `max_worker_processes` và global parallel capacity.

### Đáp án 9. Planner thresholds

Hai tham số đặt kích thước tối thiểu để planner cân nhắc parallel table scan hoặc index scan. Threshold thấp hơn có thể làm planner xem xét parallelism cho relation nhỏ hơn; quá thấp dễ tạo startup overhead không cần thiết.

### Đáp án 10. Cost

`parallel_setup_cost` ước tính startup/coordination overhead của parallel workers. `parallel_tuple_cost` ước tính chi phí chuyển tuples từ workers tới leader.

### Đáp án 11. Leader participation

`parallel_leader_participation` quyết định leader có tham gia parallel subtree hay chủ yếu gather kết quả. Leader có thể thành bottleneck khi workers tạo tuples nhanh hơn leader có thể nhận/consume và xử lý final plan nodes.

### Đáp án 12. CPU quota

Quota là 200000 microseconds trong period 100000 microseconds, tức khoảng 2 CPU equivalents.

### Đáp án 13. Kubernetes

`resources.requests.cpu` dùng cho scheduling reservation và relative CPU share/weight; `resources.limits.cpu` đặt hard quota có thể dẫn tới throttling khi chạm giới hạn.

### Đáp án 14. Worker demand

Có 3 leaders và 3 × 2 = 6 parallel workers. Tổng khoảng 9 processes trong parallel execution, chưa tính background processes và workload khác.

### Đáp án 15. Oversubscription

20 workers trên 4 CPU equivalents tạo nhiều runnable processes tranh CPU time. Có thể tăng context switching, queueing và throttling; latency có thể xấu hơn dù worker count cao hơn.

### Đáp án 16. Memory

Sort/hash operations có memory budget theo process/operation. Thêm workers làm nhiều operations chạy đồng thời; nhiều plan nodes và queries có thể khuếch đại tổng memory demand và temp spill.

### Đáp án 17. I/O

Ví dụ:

- Storage bandwidth/IOPS đã bão hòa; workers chỉ tăng queue depth.
- Working set không nằm trong cache và random reads chờ storage latency; thêm workers không tăng tốc độ thiết bị.

### Đáp án 18. EXPLAIN

Xem Gather/Gather Merge, Workers Planned/Launched, Parallel Scan/Append/Partial Aggregate, actual rows/time/loops, per-worker skew, buffers, temp I/O, planning/execution time và settings.

### Đáp án 19. Monitoring

`pg_stat_activity` với `backend_type` và `leader_pid` giúp quan sát leader/parallel workers trên các versions hỗ trợ. OS/container metrics gồm CPU usage, run queue, throttling, quota, cpuset, context switches, iowait, PSI, memory và temp I/O.

### Đáp án 20. CPU throttling

Kiểm tra `cpu.max`/CPU limit, `cpu.stat` throttled periods/time, cpuset, số queries đồng thời và runnable processes. Có thể giảm `max_parallel_workers_per_gather`/concurrency hoặc tăng CPU limit/request nếu capacity cho phép; benchmark lại.

### Đáp án 21. Parallel maintenance

CREATE INDEX có thể dùng nhiều CPU, memory, worker slots và storage bandwidth. Điều đó làm OLTP backends chờ CPU/I/O và có thể làm latency tăng.

### Đáp án 22. Query không parallel

Ví dụ:

- Function/expression PARALLEL UNSAFE.
- Table scan nhỏ hơn threshold.
- Planner cost không thấy parallel plan có lợi.
- `max_parallel_workers_per_gather = 0`.
- Worker/plan node không hỗ trợ parallel.
- Statistics/row estimates sai.
- Query có lock/temporary/session semantics bị hạn chế.

### Đáp án 23. Worker launch shortage

Kiểm tra `max_parallel_workers`, available slots trong `max_worker_processes`, background workers, concurrent parallel queries, process limits, resource exhaustion và logs.

### Đáp án 24. Tuning methodology

Thay từng setting giúp quy kết nguyên nhân của thay đổi. Benchmark concurrency thật phản ánh worker pool/CPU/memory/I/O contention mà benchmark đơn lẻ không thể hiện.

### Đáp án 25. Thiết kế

Một policy thử nghiệm:

1. Xác nhận 8 CPUs là capacity thật, không phải host cores vượt container quota.
2. Chừa CPU headroom cho WAL/checkpoints/autovacuum/OS và OLTP.
3. Giới hạn role OLTP bằng `max_parallel_workers_per_gather=0` hoặc 1 nếu benchmark cho thấy giảm tail latency.
4. Cho role analytics 2 workers per Gather làm điểm bắt đầu; tăng lên 3–4 chỉ khi CPU/I/O còn headroom.
5. Đặt `max_parallel_workers` theo concurrency analytics dự kiến, nhưng không vượt worker slots/capacity.
6. `max_worker_processes` phải đủ cho parallel, logical replication và extension workers, có headroom vừa phải.
7. Schedule maintenance parallel ngoài peak và đặt `max_parallel_maintenance_workers` thấp khi OLTP đang bận.
8. Monitor CPU throttling, worker launch, p95/p99, temp spill, I/O, memory và replication lag.
9. Test staging, rollout canary, đo trước/sau và giữ rollback config.

Các con số cần được xác nhận bằng workload benchmark và concurrency thực tế.

## 23. Checklist vận hành parallel query

### 23.1. Capacity

1. CPU quota/cpuset có được xác định từ OS/container không?
2. Có tính background workloads và CPU headroom không?
3. Worker demand theo concurrency có phù hợp capacity không?
4. Memory/temp filesystem có đủ cho sort/hash workers không?
5. Storage bandwidth/IOPS có còn headroom không?

### 23.2. PostgreSQL settings

6. `max_worker_processes` có đủ cho mọi background workers không?
7. `max_parallel_workers` có phù hợp tổng CPU/worker budget không?
8. `max_parallel_workers_per_gather` có phù hợp từng workload class không?
9. `max_parallel_maintenance_workers` có được giới hạn theo maintenance window không?
10. Planner thresholds/costs có dựa trên benchmark không?
11. Parallel safety của functions/extensions có đúng không?

### 23.3. Query plans

12. Có baseline EXPLAIN ANALYZE cho query quan trọng không?
13. Workers Planned/Launched có được so sánh không?
14. Actual rows/estimates và worker skew có được xem không?
15. Gather overhead, buffers và temp spill có được xem không?
16. Indexes/partitioning/statistics có được xem trước khi tăng workers không?

### 23.4. Monitoring

17. Có theo dõi active parallel workers và leader sessions không?
18. Có CPU usage, throttling, run queue và iowait không?
19. Có p95/p99 latency và throughput theo query class không?
20. Có memory pressure/temp files/IOPS không?
21. Có replication lag và maintenance activity không?

### 23.5. Change management

22. Có baseline/config snapshot trước tuning không?
23. Thay đổi từng setting và test staging chưa?
24. Có benchmark concurrency thật không?
25. Có rollback procedure và owner không?
26. Có kiểm tra lại peak/off-peak sau rollout không?

## 24. Runbook tuning hoặc xử lý parallel worker pressure

### Bước 1. Xác định impact

Ghi query class bị chậm, thời điểm, p95/p99, throughput, CPU, I/O và replication lag. Xác định ảnh hưởng toàn server hay một query.

### Bước 2. Xác định CPU capacity thực tế

Đọc container CPU limits/requests, cgroup quota/cpuset hoặc systemd settings. Tính effective CPU budget và kiểm tra throttling.

### Bước 3. Xác định worker demand

Dùng `pg_stat_activity`, EXPLAIN samples và concurrency để ước lượng active leaders/workers. Kiểm tra global caps và background worker usage.

### Bước 4. Kiểm tra plan

Lấy EXPLAIN ANALYZE an toàn. Xem parallel nodes, workers planned/launched, row estimates, skew, gather, buffers và temp I/O.

### Bước 5. Chọn biện pháp

- Giảm per-query workers/concurrency nếu CPU oversubscribed.
- Tăng CPU quota/capacity nếu có thể và workload cần throughput.
- Sửa statistics/index/query shape nếu plan kém.
- Giảm memory pressure/temp spill.
- Tách analytics workload hoặc schedule maintenance.

### Bước 6. Thay đổi có kiểm soát

Thử trên staging/session/role trước. Lưu config cũ và thay từng setting. Restart chỉ khi parameter yêu cầu.

### Bước 7. Đo lại

So sánh query latency, throughput, CPU/throttling, I/O, memory, worker launch và replication lag.

### Bước 8. Rollback khi SLA xấu đi

Khôi phục settings cũ hoặc giảm parallelism/concurrency. Kiểm tra workload trở về baseline và ghi lại kết quả.

## 25. Tổng kết

PostgreSQL parallel query cho phép leader backend và parallel workers cùng thực hiện một số phần của query plan. `Gather` gom tuples; `Gather Merge` merge các sorted streams. Parallel scans, append, aggregation, joins và một số maintenance operations có thể tận dụng workers khi plan, query semantics và resource limits cho phép.

Những nguyên tắc quan trọng:

- Parallel query chạy trong một PostgreSQL instance; nó không tự tạo distributed query execution.
- `PARALLEL SAFE`, `PARALLEL RESTRICTED` và `PARALLEL UNSAFE` quyết định function/operation có thể chạy ở worker hay không.
- `max_worker_processes`, `max_parallel_workers` và `max_parallel_workers_per_gather` kiểm soát các tầng worker capacity khác nhau.
- `Workers Planned` là dự kiến; `Workers Launched` là thực tế tại execution time.
- Planner cost/thresholds quyết định parallel plan có đáng giá không; statistics và query shape ảnh hưởng lựa chọn.
- CPU quota/cpuset/Kubernetes limits điều khiển CPU thực tế; worker count không bảo đảm CPU cores.
- Nhiều queries đồng thời có thể oversubscribe CPU và worker slots.
- Parallel workers có thể khuếch đại memory, temp I/O và storage contention.
- Leader/gather, skew, I/O và CPU throttling có thể giới hạn speedup.
- Tuning cần benchmark ở concurrency thật, đo p95/p99 và giữ headroom cho OLTP/HA/background work.
- Parallel maintenance phải được schedule/limit để không làm ảnh hưởng ứng dụng.
- Monitoring phải kết hợp PostgreSQL views, EXPLAIN, OS/container metrics và replication health.

Nguyên tắc thực hành:

> **Chọn số workers theo CPU budget và concurrency thực tế; đo plan và resource pressure trước khi tăng parallelism.**

## 26. Tài liệu tham khảo

Chọn tài liệu đúng major version PostgreSQL đang chạy vì parallel capabilities và configuration details thay đổi theo release:

- [PostgreSQL Parallel Plans](https://www.postgresql.org/docs/current/parallel-plans.html): Gather/Gather Merge, parallel scans, joins và aggregation.
- [How Parallel Query Works](https://www.postgresql.org/docs/current/how-parallel-query-works.html): leader, workers và tuple gathering.
- [When Can Parallel Query Be Used?](https://www.postgresql.org/docs/current/when-can-parallel-query-be-used.html): planner conditions và parallel safety.
- [Parallel Safety](https://www.postgresql.org/docs/current/parallel-safety.html): SAFE/RESTRICTED/UNSAFE function classification.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): worker process limits, work_mem và maintenance memory.
- [Query Planning Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html): planner costs, thresholds và parallel settings.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_activity và statistics views.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query workload statistics.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): execution plans và ANALYZE/BUFFERS/SETTINGS.
- [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): parallel index build considerations.
- [PostgreSQL VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): vacuum options và maintenance behavior.
- [Linux cgroup v2 CPU Controller](https://docs.kernel.org/admin-guide/cgroup-v2.html): cpu.max, cpu.stat, cpu.weight và cpuset.
- [Docker CPU constraints](https://docs.docker.com/engine/containers/resource_constraints/): container CPU quota/cpuset.
- [Kubernetes Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU requests, limits, memory and QoS.
- [systemd.resource-control](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html): CPUQuota, CPUWeight và AllowedCPUs.


### Bài 24. Tuning methodology

Vì sao nên thay đổi từng setting một và benchmark ở concurrency thật?

### Bài 25. Thiết kế

Thiết kế parallelism policy cho PostgreSQL 8 CPU cores chạy OLTP và analytics đồng thời. Nêu worker limits, role settings, CPU headroom, monitoring và rollout.
