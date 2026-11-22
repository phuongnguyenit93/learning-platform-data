# work_mem theo thao tác, phiên và truy vấn song song trong PostgreSQL

## 1. Vì sao work_mem cần được hiểu theo nhiều cấp?

PostgreSQL dùng bộ nhớ cho các thao tác trung gian khi thực thi query, chẳng hạn sort, hash join và hash aggregate. Nếu một thao tác cần nhiều dữ liệu hơn ngân sách bộ nhớ được phép sử dụng, PostgreSQL có thể chia công việc thành nhiều phần và dùng temporary files trên disk. Điều này giúp query tiếp tục chạy, nhưng có thể làm latency và I/O tăng đáng kể.

Tham số `work_mem` thường bị hiểu nhầm là lượng RAM cấp cho một query hoặc một connection. Thực tế, nó là ngân sách cho **mỗi thao tác sort hoặc hash liên quan**, và một query có thể có nhiều thao tác như vậy. Nhiều query chạy đồng thời, nhiều backend và parallel workers có thể cùng sử dụng ngân sách riêng.

Vì vậy tăng `work_mem` toàn server từ 16 MB lên 256 MB không có nghĩa chỉ thêm 240 MB RAM. Trong tải đồng thời cao, tổng nhu cầu tiềm năng có thể tăng lên hàng GB.

```text
PostgreSQL instance
   |
   +-- Session A
   |     |
   |     +-- Query A
   |     |     +-- Sort node       -> work_mem budget
   |     |     +-- Hash Join       -> hash memory budget
   |     |     +-- Hash Aggregate  -> hash memory budget
   |     |
   |     +-- Other active query ...
   |
   +-- Session B
   |     +-- Query B / Sort / Hash ...
   |
   +-- Parallel query
         +-- Leader process
         +-- Worker 1
         +-- Worker 2
         +-- Worker 3
```

Mức tiêu thụ thực tế phụ thuộc execution plan, số thao tác đang hoạt động cùng lúc, số sessions, số workers, loại operator và dữ liệu thực. Cần đo bằng query plans, temp I/O, process/host memory và workload concurrency.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác `work_mem` áp dụng cho thao tác nào.
2. Phân biệt ngân sách mỗi operator, mỗi query, mỗi session và toàn server.
3. Nhận diện sort/hash spill qua EXPLAIN và statistics.
4. Hiểu `hash_mem_multiplier` và các hash-based operations.
5. Ước lượng memory pressure khi nhiều query chạy đồng thời.
6. Phân tích parallel query và memory của workers.
7. Phân biệt `work_mem` với `shared_buffers`, `maintenance_work_mem`, `temp_buffers` và các tham số khác.
8. Điều chỉnh memory ở session, transaction, role và database scope.
9. Dùng `SET LOCAL` để giới hạn phạm vi tuning.
10. Theo dõi temp files, temp blocks và memory contexts.
11. Tối ưu query plan trước khi tăng memory.
12. Thiết kế capacity budget, test concurrency và alert.
13. Tránh OOM, swap và ảnh hưởng chéo giữa workloads.
14. Xây runbook điều tra query spill và memory pressure.

---

## 2. work_mem là gì?

`work_mem` là lượng bộ nhớ cơ sở mà PostgreSQL cho phép một thao tác query cần sort hoặc hash sử dụng trước khi chuyển sang các chiến lược dùng disk hoặc batching.

Ví dụ các thao tác thường liên quan:

- Sort cho `ORDER BY`.
- Sort phục vụ `DISTINCT` hoặc một số plan cần sắp xếp.
- Sort trong merge join.
- Hash join build table.
- Hash aggregate cho `GROUP BY`.
- Một số hash-based operations khác.
- Một số executor nodes dùng tuplestore/memory tuỳ plan và implementation.

Điểm quan trọng: `work_mem` không phải giới hạn tổng RAM của một query. Một execution plan có thể chứa nhiều nodes dùng memory.

### 2.1. Một query có nhiều work_mem consumers

Ví dụ plan khái niệm:

```text
SELECT ...
  -> Sort                         (work_mem)
       -> Hash Join               (hash memory)
            -> Seq Scan orders
            -> Hash                (hash memory)
                 -> Seq Scan customers
```

Nếu nhiều nodes cần memory trong cùng giai đoạn thực thi, tổng memory của query có thể cao hơn một lần `work_mem`.

### 2.2. Nhiều query cùng chạy

Mỗi backend thực thi query có thể sử dụng ngân sách riêng. Nếu 30 sessions đồng thời chạy query có sort/hash, không thể chỉ tính một lần `work_mem` cho cả instance.

### 2.3. work_mem là ngân sách, không phải reservation

PostgreSQL không nhất thiết cấp phát toàn bộ giá trị `work_mem` ngay khi query bắt đầu. Bộ nhớ được dùng khi operator cần. Do đó số sessions nhân với work_mem là cách ước lượng rủi ro/ceiling, không phải dự báo RSS chính xác.

### 2.4. Không phải mọi plan node đều chạy đồng thời

Một số nhánh plan thực thi tuần tự, một số nodes có thể giữ state cùng lúc, một số memory được giải phóng khi node hoàn tất. Không cộng tất cả node một cách máy móc; cần đọc plan và quan sát workload.

## 3. Phân biệt các phạm vi bộ nhớ

| Phạm vi | Ví dụ | Ý nghĩa |
|---|---|---|
| Operator | Một Sort hoặc Hash node | Đơn vị cơ bản gắn với work_mem |
| Query | Một execution plan | Có thể có nhiều operators và workers |
| Session/backend | Một kết nối PostgreSQL | Có thể chạy nhiều query theo thời gian |
| Parallel query | Leader và parallel workers | Nhiều process cùng thực thi một query |
| Instance | Mọi sessions, workers, background processes | Tổng áp lực bộ nhớ lên host/container |

### 3.1. Không đặt work_mem theo tổng RAM

Nếu máy có 64 GB RAM, không có nghĩa có thể đặt `work_mem = 1 GB`. Shared buffers, OS cache, backend overhead, maintenance, parallel workers và concurrency đều cần memory.

### 3.2. Không đặt work_mem theo một query đơn lẻ

Một query chạy một mình có thể cần 256 MB và hoàn tất nhanh. Khi 50 query tương tự chạy đồng thời, mức tiêu thụ tiềm năng có thể vượt giới hạn host.

### 3.3. Đặt ngân sách theo workload

OLTP có concurrency cao thường cần giá trị mặc định thận trọng. Reporting/batch có thể được cấp mức cao hơn theo role hoặc transaction nếu concurrency được kiểm soát.

## 4. Sort operations và work_mem

Sort thường xuất hiện khi query yêu cầu thứ tự dữ liệu hoặc execution plan cần sắp xếp.

Ví dụ:

```sql
SELECT order_id, created_at, total
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC;
```

Nếu index phù hợp có thể cung cấp thứ tự cần thiết, planner có thể tránh explicit Sort. Nếu phải sort nhiều rows, operator cần memory.

### 4.1. Sort in memory

Nếu dữ liệu sort vừa ngân sách, PostgreSQL có thể dùng thuật toán sort trong memory, ví dụ quicksort hoặc top-N heapsort tuỳ query.

EXPLAIN ANALYZE có thể hiển thị:

```text
Sort Method: quicksort  Memory: 8192kB
```

### 4.2. External sort

Nếu dữ liệu vượt memory budget, PostgreSQL có thể dùng external merge sort và temporary files:

```text
Sort Method: external merge  Disk: 128000kB
```

Đây là bằng chứng operator đã spill ra disk. Không phải mọi external sort đều là incident; hãy so với latency SLO và workload baseline.

### 4.3. LIMIT và top-N

Với `ORDER BY ... LIMIT`, planner có thể dùng top-N heapsort hoặc index scan. Không mặc định cần tăng work_mem; xem plan trước.

### 4.4. Index có thể loại bỏ Sort

Một B-tree index có thứ tự phù hợp với filter/order direction có thể giúp đọc theo thứ tự thay vì sort toàn bộ kết quả. So sánh chi phí index scan, heap fetch và sort.

## 5. Hash join và hash memory

Hash join xây dựng một hash table từ một input (build side), rồi dùng input còn lại để probe.

```text
Build input
    |
    v
 Hash table in memory
    |
    v
Probe input -----> Match rows
```

Nếu hash table không vừa memory budget, PostgreSQL có thể chia dữ liệu thành nhiều batches và sử dụng temporary I/O.

EXPLAIN có thể hiển thị:

```text
Hash
  Buckets: 65536
  Batches: 8
  Memory Usage: 4096kB
```

### 5.1. Batches = 1

Thường cho biết hash table xử lý trong một batch, không cần partition nhiều batches ra disk. Vẫn cần xét plan, memory và latency.

### 5.2. Batches lớn hơn 1

Nhiều batches là dấu hiệu hash operation cần chia nhỏ, thường đi kèm temp I/O. Kiểm tra estimate, build-side size và actual rows.

### 5.3. Build side và cardinality

Planner chọn build/probe sides dựa trên estimates. Nếu statistics sai, hash table có thể lớn hơn dự kiến. Chạy ANALYZE và kiểm tra row estimates trước khi tăng memory.

### 5.4. Hash join không phải lúc nào cũng tốt hơn

Nested loop với index lookup hoặc merge join có thể hiệu quả hơn trong một số phân bố dữ liệu. Tối ưu join strategy và indexes trước khi tăng ngân sách toàn hệ thống.

## 6. Hash aggregate và GROUP BY

Hash aggregate gom rows theo grouping keys bằng hash table.

Ví dụ:

```sql
SELECT customer_id, count(*), sum(total)
FROM orders
GROUP BY customer_id;
```

Nếu số groups lớn hoặc row width rộng, hash table có thể tiêu thụ đáng kể memory. Khi không đủ, executor có thể spill/partition theo implementation và version.

### 6.1. Số groups quan trọng

GROUP BY một cột có vài chục giá trị khác với group theo nhiều cột gần unique. Ước lượng cardinality giúp dự đoán hash table size.

### 6.2. HashAggregate so với GroupAggregate

Planner có thể chọn HashAggregate hoặc GroupAggregate. GroupAggregate thường cần input được sắp xếp theo group keys; có thể tận dụng index/sort. HashAggregate cần hash table.

### 6.3. EXPLAIN evidence

Xem node type, actual rows, planned rows, memory usage và temp blocks. Không tăng work_mem chỉ vì query có GROUP BY.

### 6.4. Aggregation theo batch

Với dữ liệu lớn, chia aggregation theo partition/time window hoặc pre-aggregate có thể giảm memory và temp I/O.

## 7. hash_mem_multiplier

`hash_mem_multiplier` điều chỉnh giới hạn bộ nhớ cho hash-based operations tương đối với `work_mem`.

Cách hiểu khái quát:

```text
Hash operation memory limit
    ≈ work_mem × hash_mem_multiplier
```

Ví dụ nếu `work_mem` là 32 MB và `hash_mem_multiplier` là 2, giới hạn cơ sở cho hash operation có thể khoảng 64 MB theo semantics của phiên bản PostgreSQL đang dùng.

### 7.1. Vì sao có multiplier riêng?

Hash operations có thể cần memory khác sort. Multiplier cho phép cấp ngân sách hash cao hơn mà không tăng mọi sort operation tương ứng.

### 7.2. Version awareness

`hash_mem_multiplier` có mặt trong các PostgreSQL versions hiện đại; availability/default có thể khác theo major version. Kiểm tra `SHOW hash_mem_multiplier` hoặc `pg_settings` trước khi sử dụng.

### 7.3. Không tăng multiplier toàn cục thiếu capacity model

Nhiều hash joins/aggregates chạy đồng thời có thể làm memory pressure tăng nhanh. Multiplier cao không thay thế việc kiểm tra concurrency.

### 7.4. Xem riêng hash spill

Nếu query có hash batches lớn, xác định build-side size và estimates. Có thể tăng hash budget cho một workload cụ thể thay vì thay toàn bộ work_mem.

## 8. Các operator và query patterns tiêu thụ work_mem

| SQL pattern / plan | Operator có thể xuất hiện | Điều cần xem |
|---|---|---|
| ORDER BY | Sort | Sort Method, Disk, Memory |
| DISTINCT | Sort hoặc HashAggregate | Rows/groups, spill |
| GROUP BY | HashAggregate/GroupAggregate | Group count, hash batches |
| JOIN | Hash/Sort/Merge Join | Build side, batches, sort |
| UNION / set operations | Sort/Hash | Cardinality, duplicate elimination |
| Window functions | Sort/tuplestore tuỳ plan | Partition/order size |
| Materialization | Tuplestore | Temp files và plan shape |
| Memoize | Cache node | Evictions/hits, version behavior |

Không phải mọi query có các cú pháp trên đều dùng work_mem theo cùng cách. Execution plan quyết định operator thực tế.

### 8.1. Window functions

`ROW_NUMBER`, `RANK` và các window aggregates có thể cần sort theo PARTITION BY/ORDER BY. Dữ liệu partition lớn có thể làm spill.

### 8.2. DISTINCT và UNION

Việc loại duplicate có thể dùng sort hoặc hash strategy. Xem plan thay vì đoán theo câu SQL.

### 8.3. Materialize và tuplestore

Một số nodes giữ tuples tạm trong memory và có thể chuyển sang temporary files. Temp I/O có thể xuất hiện dù không có Sort node rõ ràng.

### 8.4. Memoize

Memoize cache kết quả parameterized scans trong một số plan. Memory/eviction behavior phụ thuộc executor và version; xem EXPLAIN details nếu node xuất hiện.

## 9. Nhận diện spill bằng EXPLAIN

Dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY)
SELECT customer_id, sum(total)
FROM orders
GROUP BY customer_id
ORDER BY customer_id;
```

### 9.1. Sort Method

- quicksort: sort in-memory.
- top-N heapsort: tối ưu khi LIMIT.
- external merge: sort spill ra disk.

Chi tiết output phụ thuộc version và plan.

### 9.2. Hash Batches

Xem số batches và memory usage. Nhiều batches có thể cho biết hash operation vượt ngân sách in-memory.

### 9.3. Buffers: temp read/written

EXPLAIN BUFFERS có thể hiển thị temporary blocks read/written cho query. Đây là tín hiệu hữu ích về spill I/O.

### 9.4. Planned rows và actual rows

Nếu actual rows cao hơn estimate nhiều, planner có thể chọn sai strategy hoặc cấp memory không đủ cho data volume thực.

### 9.5. EXPLAIN ANALYZE thực thi query

EXPLAIN ANALYZE chạy statement thật. Với DML, side effects có thể xảy ra; transaction rollback không đảo ngược mọi external side effects do trigger/function tạo ra. Chọn môi trường và cách chạy phù hợp.

## 10. So sánh estimated và actual cardinality

Memory demand phụ thuộc số rows, row width và operator structure. Planner dùng statistics để estimate.

Trong EXPLAIN:

```text
HashAggregate
  (cost=... rows=1000 ...)
  (actual time=... rows=800000 loops=1)
```

Chênh lệch lớn có thể khiến planner đánh giá thấp hash table hoặc sort volume.

### 10.1. ANALYZE

Chạy ANALYZE cho relation có statistics stale hoặc sau bulk load. Kiểm tra last_analyze/last_autoanalyze và n_mod_since_analyze.

### 10.2. Statistics target

Tăng statistics target cho column có skew/cardinality phức tạp khi cần, nhưng không dùng như tuning ngẫu nhiên.

### 10.3. Extended statistics

CREATE STATISTICS có thể giúp planner hiểu correlation/dependencies giữa columns. Điều này cải thiện row estimates trong một số predicates/grouping.

### 10.4. Row width

SELECT * có thể làm tuples rộng hơn cần thiết, tăng sort/hash memory. Chỉ chọn columns cần dùng.

## 11. Tính memory theo operation, không theo query count đơn giản

Một query có thể có:
- Hai sort nodes.
- Một hash join.
- Một hash aggregate.
- Một hoặc nhiều parallel workers.

Nếu tất cả các operations cùng cần memory ở cùng thời điểm, query có thể dùng nhiều lần ngân sách work_mem. Nhưng không phải mọi node đều active đồng thời và memory allocation có thể thấp hơn giới hạn.

### 11.1. Mô hình ước lượng bảo thủ

```text
Potential memory pressure
  ≈ concurrent active processes
    × simultaneous memory-consuming operations
    × per-operation budget
```

Với hash operations, dùng multiplier phù hợp.

### 11.2. Ví dụ workload

Giả sử:
- 20 query sessions đồng thời.
- Mỗi query có thể có 2 sort operations cùng active.
- work_mem = 32 MB.

Một ceiling minh họa cho sort budgets là:

```text
20 × 2 × 32 MB = 1280 MB
```

Đây là mô hình bảo thủ, không phải dự báo RSS. Thực tế phụ thuộc plan, lifetime, allocation và concurrency.

### 11.3. Thêm hash operation

Nếu mỗi query còn một hash operation với multiplier 2:

```text
Per-query modeled budget
  = 2 × 32 MB + 1 × (32 MB × 2)
  = 128 MB

20 concurrent queries
  = 20 × 128 MB
  = 2560 MB
```

Mô hình này minh họa tại sao work_mem lớn có thể nguy hiểm khi concurrency cao.

### 11.4. Đừng cộng tất cả node mà không xem plan

Một số nodes chạy tuần tự hoặc giải phóng memory trước node khác. Dùng plan và load tests để hiệu chỉnh estimate.

## 12. work_mem theo session/backend

Có thể đặt work_mem trong session:

```sql
SET work_mem = '64MB';

SHOW work_mem;
```

Setting áp dụng cho session hiện tại, ảnh hưởng các query sau đó trong session theo scope của parameter.

### 12.1. Session kéo dài

Nếu session được giữ trong connection pool, setting có thể tồn tại sau request. Request tiếp theo có thể vô tình nhận mức memory khác dự kiến.

### 12.2. RESET

```sql
RESET work_mem;
```

RESET đưa parameter về default được kế thừa theo cấu hình role/database/session.

### 12.3. Pool hygiene

Khi dùng session pooling, đảm bảo pool reset session state khi trả connection hoặc dùng transaction-scoped settings.

### 12.4. Không để application client tự do SET giá trị lớn

Đặt allowlist/guardrail ở application hoặc database role. Một client có thể vô tình gây memory pressure cho cả instance.

## 13. work_mem theo transaction với SET LOCAL

`SET LOCAL` giới hạn thay đổi trong transaction hiện tại:

```sql
BEGIN;

SET LOCAL work_mem = '128MB';

SELECT customer_id, sum(total)
FROM orders
GROUP BY customer_id
ORDER BY customer_id;

COMMIT;
```

Sau COMMIT hoặc ROLLBACK, setting local hết hiệu lực và giá trị session trước đó được khôi phục.

### 13.1. Phù hợp với connection pooling

Trong transaction pooling, SET LOCAL nằm trong transaction và không rò sang transaction kế tiếp khi transaction kết thúc đúng cách. Không dùng session-level SET rồi giả định proxy sẽ giữ cùng backend.

### 13.2. Phạm vi chỉ trong transaction

Nếu query chạy ngoài transaction explicit, PostgreSQL vẫn chạy statement trong transaction ngầm; SET LOCAL phải nằm trong transaction block phù hợp để ảnh hưởng statement kế tiếp.

### 13.3. Exception/rollback

Nếu transaction rollback, local setting cũng được khôi phục. Đây là lý do SET LOCAL thường an toàn hơn cho tuning theo request.

### 13.4. Giữ transaction ngắn

Không mở transaction chỉ để giữ work_mem setting trong thời gian dài. Transaction dài có thể giữ snapshots/locks và gây vấn đề vacuum.

## 14. work_mem theo role

Có thể đặt default cho một database role:

```sql
ALTER ROLE reporting_user
SET work_mem = '64MB';
```

Setting có hiệu lực cho các sessions mới đăng nhập bằng role đó. Sessions đang mở thường không tự nhận default mới.

### 14.1. Reporting role

Một role dành cho reporting có thể có work_mem cao hơn nếu concurrency và query patterns được kiểm soát.

### 14.2. OLTP role

Role phục vụ API concurrency cao nên có baseline thận trọng; một số endpoint nặng có thể dùng SET LOCAL riêng.

### 14.3. Kiểm tra role defaults

```sql
SELECT
    rolname,
    rolconfig
FROM pg_roles
WHERE rolname IN ('reporting_user', 'api_user');
```

### 14.4. ALTER ROLE IN DATABASE

Có thể giới hạn default theo database:

```sql
ALTER ROLE reporting_user IN DATABASE analytics
SET work_mem = '96MB';
```

Cần kiểm tra session settings và thứ tự precedence khi có nhiều nguồn cấu hình.

## 15. work_mem theo database

Có thể đặt default database:

```sql
ALTER DATABASE analytics
SET work_mem = '48MB';
```

### 15.1. Khi nào dùng database default?

Khi database có workload profile riêng và hầu hết sessions trong database có nhu cầu tương tự.

### 15.2. Không phải mọi role đều giống nhau

Database có thể chứa API, reporting và jobs. Role-specific defaults hoặc transaction-level settings có thể chính xác hơn.

### 15.3. Sessions hiện tại

ALTER DATABASE SET ảnh hưởng sessions đăng nhập sau khi thay đổi, không tự động cập nhật mọi backend đang kết nối.

### 15.4. Ghi lại policy

Đưa defaults vào configuration management/migration process. Tránh thay đổi thủ công không có owner.

## 16. Precedence và cấu hình hiệu lực

Giá trị hiệu lực có thể đến từ:
- Compiled/default configuration.
- postgresql.conf hoặc include files.
- ALTER DATABASE / ALTER ROLE defaults.
- Connection startup options.
- SET trong session.
- SET LOCAL trong transaction.

Kiểm tra giá trị hiện tại:

```sql
SHOW work_mem;
SHOW hash_mem_multiplier;
```

Hoặc:

```sql
SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN ('work_mem', 'hash_mem_multiplier');
```

### 16.1. source

`pg_settings.source` giúp biết giá trị được lấy từ đâu, tùy context/version và quyền xem sourcefile.

### 16.2. Role/database defaults

Một ALTER ROLE hoặc ALTER DATABASE có thể override server default cho session mới.

### 16.3. Session SET

SET trong session override default đã được nạp.

### 16.4. SET LOCAL

SET LOCAL override trong transaction hiện tại và tự khôi phục khi transaction kết thúc.

## 17. work_mem không phải shared_buffers

| Parameter | Dùng cho | Scope |
|---|---|---|
| work_mem | Sort/hash/query execution operations | Mỗi operation/process |
| shared_buffers | Shared cache cho database pages | Toàn instance |
| maintenance_work_mem | Một số maintenance operations | Operation/maintenance worker |
| autovacuum_work_mem | Memory cho autovacuum worker | Mỗi worker theo config |
| temp_buffers | Local buffers cho temporary tables | Mỗi session |
| logical_decoding_work_mem | Logical decoding changes pending spill | Logical decoding process |
| wal_buffers | WAL records trước khi ghi WAL | Shared instance |

### 17.1. shared_buffers

Dùng để cache database pages. Tăng shared_buffers không trực tiếp tăng sort/hash memory budget.

### 17.2. maintenance_work_mem

Dùng cho các maintenance operations như VACUUM (một số phần), CREATE INDEX và các thao tác bảo trì phù hợp. Không dùng để thay work_mem cho SELECT.

### 17.3. autovacuum_work_mem

Có thể điều chỉnh memory riêng cho autovacuum workers. Nếu đặt -1, behavior có thể kế thừa maintenance_work_mem theo version/configuration.

### 17.4. temp_buffers

Dùng cho temporary tables, không phải ngân sách sort spill. Đừng tăng temp_buffers để chữa external sort.

### 17.5. logical_decoding_work_mem

Có scope riêng cho logical decoding transaction changes. Không nhầm với memory của query executor.

## 18. Parallel query nhân áp lực bộ nhớ như thế nào?

Parallel query có thể dùng leader và nhiều worker processes. Các workers thực hiện một phần công việc, có thể có sort/hash operators riêng.

```text
Parallel plan
      |
      v
 Gather / Gather Merge
      |
      +-- Leader process
      |
      +-- Worker 1
      |     +-- Sort / Hash
      |
      +-- Worker 2
      |     +-- Sort / Hash
      |
      +-- Worker 3
            +-- Sort / Hash
```

### 18.1. work_mem theo process/operator

Mỗi process thực thi operation có thể cần ngân sách riêng. Vì vậy một query parallel có thể tiêu thụ memory nhiều lần work_mem.

### 18.2. Workers planned và launched

EXPLAIN ANALYZE có thể cho biết Workers Planned và Workers Launched. Không phải lúc nào planner yêu cầu bao nhiêu workers thì thực tế cũng khởi chạy đủ.

### 18.3. Leader participation

Leader có thể tham gia xử lý tuples bên cạnh việc nhận kết quả từ workers, tùy plan và workload. Tính capacity cần xét leader khi nó thực thi operators.

### 18.4. Parallel Hash

Một số parallel hash plans dùng shared parallel hash table và cơ chế phối hợp giữa workers. Memory không phải lúc nào cũng bằng số workers nhân nguyên xi một hash table riêng; hãy đọc plan và xem memory behavior thực tế.

## 19. Ước lượng memory cho parallel query

Một mô hình capacity bảo thủ:

```text
Potential memory
  ≈ active parallel processes
    × simultaneously active memory operators
    × per-operator budget
```

Với hash operators, nhân thêm hash_mem_multiplier theo semantics của version.

### 19.1. Ví dụ

Một query có 4 workers được launch, leader cũng tham gia, mỗi process có một sort operation đang hoạt động, work_mem = 32 MB:

```text
(4 workers + 1 leader) × 32 MB
= 160 MB modeled sort budget
```

Đây là estimate bảo thủ, không phải mức RAM thực tế chắc chắn được cấp.

### 19.2. Thêm concurrency

Nếu 10 queries parallel tương tự chạy cùng lúc, modeled budget có thể tăng theo concurrency. Đây là lý do cần giới hạn workload và parallelism.

### 19.3. max_parallel_workers_per_gather

Setting này giới hạn số workers cho một Gather/Gather Merge theo cấu hình. Tăng workers có thể cải thiện throughput nhưng làm tăng CPU, memory và I/O demand.

### 19.4. Parallel query có thể làm latency xấu hơn

Nếu host đã CPU/memory saturated, thêm workers tạo contention và có thể làm tất cả queries chậm hơn.

## 20. Khi nào tăng work_mem là đúng?

Có thể cân nhắc tăng khi:
- Plan cho thấy sort/hash spill đáng kể.
- Query có latency cao vì temp I/O.
- Query có cardinality estimates tương đối chính xác.
- Host còn memory headroom.
- Concurrency được kiểm soát.
- Workload có thể được scope theo role/session/transaction.

### 20.1. Evidence cần có

Lưu EXPLAIN ANALYZE, actual rows, sort/hash details, temp blocks, query duration, concurrency và host memory trước khi thay đổi.

### 20.2. Tăng nhỏ theo bước

Thử tăng từ 16 MB lên 32 MB hoặc 64 MB cho transaction cụ thể, đo lại và dừng khi không còn cải thiện đáng kể.

### 20.3. Kiểm tra toàn workload

Một query nhanh hơn không đáng nếu API queries khác bị OOM/swap hoặc connection failures.

### 20.4. So sánh throughput và latency

Đánh giá cả p95/p99, total throughput, temp I/O, memory peak và error rate.

## 21. Khi nào không nên tăng work_mem?

Không tăng chỉ vì:
- CPU cao.
- Database có RAM lớn.
- Query chậm nhưng đang lock-wait.
- Query plan scan quá nhiều rows vì thiếu index.
- Statistics sai.
- Connection pool bị nghẽn.
- Disk/network là bottleneck.
- Query trả quá nhiều rows không cần thiết.
- Nhiều concurrent queries đã gây memory pressure.

### 21.1. Lock wait

Tăng work_mem không giải phóng blocker transaction. Tìm lock graph.

### 21.2. Bad query plan

Một full table scan hoặc nested loop bất hợp lý cần query/index/statistics analysis.

### 21.3. Network bottleneck

Nếu query nhanh ở database nhưng response chậm do truyền hàng triệu rows, giảm output/round trips.

### 21.4. Pool saturation

Nếu request chờ connection, tăng work_mem không giúp; có thể còn làm query khi chạy tốn nhiều RAM hơn.

## 22. Tối ưu query trước khi tăng memory

Các hướng có thể giảm memory demand:
- Chỉ SELECT columns cần thiết.
- Giảm rows trước sort/aggregate.
- Tạo index hỗ trợ filter/order.
- Viết predicates có thể dùng index.
- Kiểm tra join keys và cardinality.
- Tránh DISTINCT không cần thiết.
- Chia batch hoặc partition aggregation.
- Cập nhật statistics.
- Giảm N+1 query pattern.
- Tránh materialize tập dữ liệu lớn không cần thiết.

### 22.1. Push filters xuống sớm

Giảm số rows đi vào sort/hash có thể giảm memory và temp I/O đáng kể.

### 22.2. Index order

Index phù hợp có thể loại Sort node. Đánh đổi write amplification, storage và index maintenance.

### 22.3. Join order và estimates

Kiểm tra actual rows, loops và join algorithm. Planner có thể chọn build side không phù hợp khi statistics thiếu chính xác.

### 22.4. Query rewrite

Một query rewrite hợp lý có thể giảm số rows/width hoặc tránh một operator nặng. Đo plan trước/sau bằng dữ liệu đại diện.

## 23. Theo dõi temp files ở cấp database

`pg_stat_database` có cumulative counters:

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

### 23.1. temp_files

Số temporary files được tạo theo database kể từ stats reset.

### 23.2. temp_bytes

Tổng bytes ghi vào temporary files. Dùng delta để tính temp write rate.

### 23.3. Counter không nói query nào

Dùng pg_stat_statements temp_blks_written hoặc logs để quy trách nhiệm tới query.

### 23.4. Reset awareness

Nếu stats_reset thay đổi hoặc server/database được reset, không lấy delta xuyên qua reset.

## 24. Theo dõi temp blocks bằng pg_stat_statements

Nếu extension/version hỗ trợ fields tương ứng:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    temp_blks_read,
    temp_blks_written,
    shared_blks_read,
    shared_blks_hit
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
```

### 24.1. temp_blks_written

Giúp tìm query đã ghi nhiều temporary blocks kể từ stats reset.

### 24.2. temp_blks_read

Cho biết query đọc temporary blocks. Một operation spill có thể vừa ghi vừa đọc temp data.

### 24.3. Tính delta

Các cột là counters tích lũy. Dùng samples liên tiếp để biết query nào đang spill nhiều trong window hiện tại.

### 24.4. Query identity và reset

Ghi queryid, calls và stats_reset. Query entries có thể bị deallocate/reset theo cấu hình/version.

## 25. log_temp_files

`log_temp_files` cho phép PostgreSQL log temporary files được tạo, dựa trên kích thước threshold.

Ví dụ cấu hình:

```sql
SHOW log_temp_files;
```

Giá trị minh họa:
- `-1`: không log temp files.
- `0`: log mọi temp file.
- Số dương: log temp files từ ngưỡng KB trở lên.

### 25.1. Dùng trong điều tra

Có thể đặt threshold để phát hiện query tạo temp files lớn. Kết hợp PID/query context và statement logs.

### 25.2. Log volume

Đặt 0 trên hệ thống có nhiều spill có thể tạo lượng logs rất lớn. Chọn threshold và retention hợp lý.

### 25.3. Parameter context

Khả năng thay đổi tại session/system và quyền cần thiết phụ thuộc parameter context/version. Kiểm tra pg_settings trước khi thay.

### 25.4. Log không thay EXPLAIN

Log cho biết temp file được tạo, nhưng plan mới giúp hiểu operator gây spill.

## 26. temp_file_limit

`temp_file_limit` giới hạn lượng disk space mà một process có thể sử dụng cho temporary files theo semantics PostgreSQL.

### 26.1. Vai trò

Nó là guardrail để một process không dùng quá nhiều temp disk. Khi vượt giới hạn, statement có thể bị terminate.

### 26.2. Không phải cách chữa spill

Giới hạn thấp có thể biến query chậm thành query lỗi. Nó không làm query cần ít memory hơn.

### 26.3. Per-process semantics

Đọc tài liệu đúng version để hiểu giới hạn tính theo process và tác động của parallel workers. Đừng coi nó là một quota tổng toàn instance.

### 26.4. Capacity planning

Theo dõi temp filesystem free space, temp bytes rate và số queries đồng thời. temp_file_limit là hàng rào cuối, không thay monitoring.

## 27. Memory contexts trong PostgreSQL

PostgreSQL dùng memory contexts để quản lý allocations theo lifetime. Khi context được reset/freed, nhiều allocations liên quan được giải phóng cùng lúc.

Trong các versions hỗ trợ, có thể xem contexts của backend hiện tại:

```sql
SELECT
    name,
    ident,
    parent,
    level,
    total_bytes,
    free_bytes,
    used_bytes
FROM pg_backend_memory_contexts
ORDER BY total_bytes DESC;
```

### 27.1. Backend hiện tại

View này mô tả memory contexts của backend chạy query, không phải dashboard tổng memory mọi backend.

### 27.2. Không nhầm used_bytes với RSS

Memory context accounting không bao gồm mọi loại memory/OS overhead và không trực tiếp bằng resident set size.

### 27.3. pg_log_backend_memory_contexts

Một số versions cung cấp function để yêu cầu backend khác ghi memory contexts vào server log. Cần quyền phù hợp và kiểm soát log volume.

### 27.4. Dùng khi cần chẩn đoán sâu

Memory contexts hữu ích khi nghi memory leak hoặc allocation bất thường, nhưng không thay host/cgroup memory metrics.

## 28. Theo dõi host và container memory

Database process memory phải được xem cùng memory của host/container.

Theo dõi:
- Available memory.
- RSS/working set.
- Swap in/out.
- Page faults.
- OOM kill events.
- Container/cgroup memory.current và memory.max.
- Memory pressure/stall signals nếu platform hỗ trợ.
- Shared memory usage.

### 28.1. OOM killer

Nếu tổng demand vượt memory limit, Linux/container runtime có thể kill backend hoặc postmaster tùy tình huống. Hệ quả có thể là query errors hoặc database restart.

### 28.2. Swap

Swap activity có thể làm latency tăng mạnh. PostgreSQL query có thể chậm dù CPU không bận.

### 28.3. Container limit

Host còn RAM nhưng container memory.max đã gần hết vẫn có thể bị OOM kill.

### 28.4. Shared memory accounting

Không cộng RSS của tất cả backends một cách ngây thơ vì shared memory mappings có thể bị tính lặp. Dùng cgroup/OS accounting và hiểu cách exporter đo.

## 29. Capacity model cho work_mem

Một cách lập ngân sách:
1. Xác định memory dành cho OS và page cache.
2. Trừ shared_buffers và các vùng instance-level.
3. Dự phòng backend baseline, autovacuum, maintenance, replication và monitoring.
4. Xác định số sessions có thể đồng thời chạy memory-heavy queries.
5. Ước lượng số operators đồng thời trên mỗi process.
6. Xét hash multiplier.
7. Xét parallel workers và leader.
8. Chừa headroom cho spikes và workload không dự đoán.

```text
Host / container memory limit
    |
    +-- OS + kernel + page cache reserve
    +-- shared_buffers / WAL shared memory
    +-- backend baseline memory
    +-- maintenance / autovacuum workers
    +-- parallel query workers
    +-- work_mem consumers
    +-- extensions / monitoring / safety headroom
```

### 29.1. Không dành hết RAM cho PostgreSQL query memory

OS cần page cache, kernel memory và headroom. Container còn có sidecars/agents nếu chạy chung.

### 29.2. Concurrency quan trọng hơn peak work_mem đơn lẻ

Một query 256 MB có thể ổn nếu chạy độc quyền. Một trăm queries 64 MB cùng chạy có thể nguy hiểm.

### 29.3. Model phải dựa trên workload thật

Dùng active query concurrency, plan distribution, workers launched và observed memory/temp I/O.

### 29.4. Capacity reserve

Giữ headroom cho deployment, backup, autovacuum, failover/recovery và unexpected traffic bursts.

## 30. Ví dụ chọn work_mem cho OLTP

OLTP thường có nhiều transactions ngắn và concurrency cao. Nhiều queries không cần sort/hash lớn, nhưng tổng active sessions có thể rất lớn.

Chiến lược:
- Dùng baseline work_mem thận trọng.
- Giữ pool concurrency có giới hạn.
- Tối ưu indexes để tránh sort.
- Dùng SET LOCAL cho endpoint/report đặc biệt.
- Theo dõi temp spill và p95/p99.
- Không tăng global setting chỉ để chữa một query.

### 30.1. Ví dụ baseline

Giả sử API role dùng work_mem 8–16 MB (chỉ là ví dụ). Một endpoint export dùng transaction riêng có thể được cấp 64 MB sau khi load test.

### 30.2. Kiểm soát concurrency

Nếu export job chạy 20 workers đồng thời, mức memory tiềm năng có thể lớn. Giới hạn job concurrency và parallel workers.

### 30.3. Tách pool

Có thể dùng pool riêng cho reporting/export để workload nặng không chiếm hết connection slots của OLTP.

### 30.4. Ưu tiên query optimization

Giảm rows/columns và tận dụng indexes thường bền vững hơn việc tăng work_mem.

## 31. Ví dụ chọn work_mem cho reporting/analytics

Reporting queries thường:
- Sort nhiều rows.
- Group theo nhiều dimensions.
- Hash join dữ liệu lớn.
- Dùng window functions.
- Chạy song song.

Chiến lược:
- Role/database riêng.
- Work_mem cao hơn có giới hạn.
- Pool concurrency thấp.
- Parallelism được kiểm soát.
- Temp filesystem đủ lớn.
- Query plans và memory được đo trước/sau.

### 31.1. Không để reporting chiếm memory của OLTP

Tách connection pools và giới hạn concurrency. Nếu dùng chung instance, đặt resource budget rõ ràng.

### 31.2. Pre-aggregation

Materialized views, summary tables hoặc ETL có thể giảm memory cần cho query tương tác.

### 31.3. Partition pruning

Lọc theo partition key có thể giảm rows đi vào sort/hash.

### 31.4. Workload schedule

Chạy report nặng vào thời gian phù hợp và theo dõi tác động tới backup/vacuum/replication.

## 32. Ví dụ tuning bằng SET LOCAL

Giả sử một báo cáo cụ thể spill nhiều và đã xác minh host còn headroom.

```sql
BEGIN;

SET LOCAL work_mem = '96MB';
SET LOCAL hash_mem_multiplier = 2.0;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT customer_id, date_trunc('month', created_at) AS month,
       sum(total)
FROM orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY customer_id, date_trunc('month', created_at)
ORDER BY month, customer_id;

COMMIT;
```

Đây là ví dụ thử nghiệm. Dùng query thực tế, data volume đại diện và đo memory/temp I/O. EXPLAIN ANALYZE chạy query.

### 32.1. So sánh baseline

Chạy cùng query với setting baseline, ghi duration, temp blocks, plan, actual rows và memory evidence.

### 32.2. Thử một biến mỗi lần

Thay work_mem trước, sau đó mới cân nhắc hash_mem_multiplier. Nếu thay nhiều tham số cùng lúc, khó biết nguyên nhân cải thiện.

### 32.3. Rollback không phải rollback setting sau COMMIT?

SET LOCAL tự hết hiệu lực khi transaction kết thúc, kể cả COMMIT. Không cần RESET sau transaction.

### 32.4. Kiểm tra concurrency

Một báo cáo đơn lẻ nhanh hơn chưa đủ. Chạy nhiều báo cáo cùng lúc và xem host memory/latency OLTP.

## 33. Tuning theo role và pool

Ví dụ cấu hình role:

```sql
ALTER ROLE analytics_reader
SET work_mem = '64MB';

ALTER ROLE api_reader
SET work_mem = '12MB';
```

### 33.1. Session mới

Role defaults được áp dụng khi session đăng nhập. Recycle pool connections nếu cần nhận cấu hình mới.

### 33.2. Per-request override

Một endpoint nặng có thể dùng SET LOCAL trong transaction, không cần thay toàn role.

### 33.3. Pool reset

Kiểm tra pooler có reset session state sau check-in. Nếu không, một request có thể để lại setting cho request sau.

### 33.4. Không chia role chỉ để có memory cao

Role nên phản ánh security/workload ownership. Không tạo role tràn lan nếu application không quản lý được.

## 34. Parallel workers và concurrency limits

Các settings liên quan:
- `max_parallel_workers_per_gather`.
- `max_parallel_workers`.
- `max_worker_processes`.
- `parallel_setup_cost`.
- `parallel_tuple_cost`.

### 34.1. max_parallel_workers_per_gather

Giới hạn số workers cho một Gather/Gather Merge. Tăng giá trị có thể tăng CPU/memory pressure.

### 34.2. max_parallel_workers

Giới hạn tổng parallel workers có thể chạy đồng thời trên instance theo cấu hình.

### 34.3. max_worker_processes

Giới hạn worker processes chung, gồm một số background workers và parallel workers. Kiểm tra các loại worker cùng chia sẻ giới hạn.

### 34.4. Worker launch failure

Nếu thiếu workers, query vẫn có thể chạy với ít workers hơn dự kiến. EXPLAIN ANALYZE giúp thấy Workers Planned/Launched.

### 34.5. Parallelism không thay memory planning

Giảm parallel workers có thể giảm memory/CPU pressure nhưng làm query lâu hơn. Đo throughput tổng thể, không chỉ query đơn.

## 35. work_mem và temp filesystem capacity

Khi query spill, temporary files sử dụng storage của PostgreSQL temp path/database tablespace theo cấu hình.

### 35.1. Temp I/O latency

Disk nhanh có thể làm external sort ít gây hại hơn, nhưng vẫn tiêu thụ bandwidth/IOPS và cạnh tranh data/WAL I/O.

### 35.2. Free space

Theo dõi free bytes trên filesystem chứa temp files, đặc biệt với reporting/batch workloads.

### 35.3. Temp tablespaces

Nếu dùng temp_tablespaces, cần giám sát từng tablespace/mount. Temp spill có thể phân bố theo cấu hình.

### 35.4. Disk full

Temporary file creation failure có thể làm query thất bại. Không dựa vào temp_file_limit thay cho capacity alerts.

## 36. Autovacuum và maintenance memory không phải work_mem

VACUUM/CREATE INDEX và các maintenance tasks có ngân sách riêng. Không tăng work_mem để giải quyết autovacuum chậm.

### 36.1. maintenance_work_mem

Có thể ảnh hưởng tốc độ/khả năng của một số maintenance operations. Cần xét concurrency của maintenance commands.

### 36.2. autovacuum_work_mem

Autovacuum workers có thể chạy đồng thời. Tổng memory phải xét số workers và setting tương ứng.

### 36.3. CREATE INDEX

Một số index build operations dùng maintenance_work_mem. Parallel index build có thêm process/resource behavior theo version.

### 36.4. Vacuum memory và work_mem

Đừng áp công thức work_mem cho mọi process. Dùng đúng parameter và view cho từng loại operation.

## 37. Work_mem và memory leaks/long-lived sessions

Một query hoàn tất thường giải phóng operation memory theo lifetime. Nhưng backend có thể giữ memory contexts/cache structures trong session theo cách implementation.

### 37.1. Session lâu dài

Theo dõi backend memory, transaction state và session churn. Một session lâu không tự chứng minh leak.

### 37.2. Prepared statements

Generic/custom plans và prepared statements ảnh hưởng plan reuse; chúng không biến work_mem thành một quota cố định theo session.

### 37.3. Memory contexts

Khi nghi memory growth, kiểm tra contexts theo backend và host RSS/cgroup. Không kết luận chỉ từ một snapshot.

### 37.4. Restart không phải cách tuning

Restart để giải phóng memory có thể gây downtime/connection disruption. Tìm allocation source và query pattern trước.

## 38. Monitoring dashboard cho work_mem

Một dashboard hữu ích có:
1. Query p50/p95/p99 duration.
2. Top query temp_blks_written.
3. Database temp_files/temp_bytes rate.
4. Sort Method external merge count/rate nếu thu thập được từ plans/logs.
5. Hash batches > 1 từ plan samples.
6. Active memory-heavy queries/concurrency.
7. Parallel workers planned/launched.
8. Host/container memory available/working set.
9. Swap/OOM/cgroup events.
10. Temp filesystem free space and I/O latency.
11. Pool active/waiters.
12. Query throughput and error rate.

### 38.1. Không có built-in gauge toàn instance cho tổng work_mem đang dùng

work_mem là budget theo operation, không phải một counter tổng đơn giản. Kết hợp plan/log instrumentation, memory contexts có chọn lọc, process/host metrics và workload model.

### 38.2. Sampling query plans

Không cần EXPLAIN mọi query trong production. Dùng pg_stat_statements để chọn candidates, slow logs/auto_explain có chọn lọc và tracing.

### 38.3. Query text cardinality

Không đưa raw SQL hoặc user parameters làm labels. Dùng queryid/normalized query class và bảo vệ thông tin nhạy cảm.

### 38.4. Correlate với deployments

Một release làm đổi query shape hoặc planner estimates có thể làm spill tăng. Annotate deployments/migrations.

## 39. Alerting cho memory và temp spill

Ví dụ alert conditions cần hiệu chỉnh theo baseline:
- Host/container available memory thấp kéo dài.
- Swap in/out tăng.
- OOM kill event xuất hiện.
- Temp bytes/s tăng đột biến.
- Temp filesystem free space dưới ngưỡng.
- p95 query latency và temp I/O cùng tăng.
- Pool waiters tăng trong khi active query count cao.
- Parallel workers contention.
- Một query class tạo temp files lớn lặp lại.

### 39.1. Alert symptom

p95 latency vượt SLO là user impact. Dùng nó làm page signal.

### 39.2. Alert cause/risk

Memory headroom thấp, temp disk gần đầy và OOM events là risk signals cần hành động.

### 39.3. Không alert chỉ vì có temp files

Spill có thể là hành vi bình thường. Alert theo tốc độ, kích thước, latency và capacity.

### 39.4. Chống alert noise

Dùng duration, hysteresis và severity. Một query report spill 20 MB có thể không đáng page nếu SLO vẫn đạt.

## 40. Troubleshooting: query sort spill

Triệu chứng:
- Query duration tăng.
- EXPLAIN cho thấy external merge.
- temp_blks_written tăng.

Quy trình:
1. Lưu query plan và parameters đã được bảo vệ.
2. Xem actual rows và width.
3. Kiểm tra filter selectivity.
4. Kiểm tra index có thể đáp ứng ORDER BY.
5. Kiểm tra LIMIT/top-N.
6. Xem sort spill bytes và temp filesystem.
7. Thử SET LOCAL work_mem tăng nhỏ trong staging/load test.
8. Đo query latency và memory dưới concurrency.
9. Chọn query rewrite/index hoặc scoped setting.
10. Theo dõi regression sau deploy.

### 40.1. Nếu actual rows vượt estimate

Chạy ANALYZE, xem skew/extended stats và plan stability.

### 40.2. Nếu index loại sort

Đánh giá write cost/storage của index và workload mix trước khi tạo.

### 40.3. Nếu chỉ một report spill

Dùng transaction/role scope thay global setting.

## 41. Troubleshooting: hash join/hash aggregate spill

Triệu chứng:
- Hash Batches lớn hơn 1.
- Temp blocks tăng.
- Query có Hash/HashAggregate node lớn.

Quy trình:
1. Xác định hash node và build side.
2. So sánh planned rows/actual rows.
3. Xem row width và group cardinality.
4. Kiểm tra statistics.
5. Kiểm tra join keys/indexes/filter.
6. Xem hash_mem_multiplier và work_mem hiệu lực.
7. Thử scoped adjustment.
8. Đo batches, temp I/O, latency và memory.
9. Đánh giá concurrency/parallel workers.
10. Chọn giải pháp có lợi cho toàn workload.

### 41.1. Hash table lớn vì nhiều groups

Có thể cần pre-aggregate, partitioning hoặc query rewrite.

### 41.2. Build side không phù hợp

Sai estimates có thể làm planner chọn build side lớn. Cập nhật stats và kiểm tra join order.

### 41.3. Không ép enable/disable hash join vĩnh viễn

Planner switches hữu ích cho diagnosis, nhưng không thay phân tích root cause. Tránh biến workaround tạm thành config toàn hệ thống.

## 42. Troubleshooting: memory pressure/OOM

Triệu chứng:
- Container memory gần limit.
- Swap tăng.
- OOM kill.
- Query failures hoặc backend restart.
- Latency tăng trên nhiều workloads.

Quy trình:
1. Xác định host/container memory limit và available memory.
2. Xem OOM/cgroup events và process RSS.
3. Đếm active sessions/parallel workers.
4. Xác định workloads đang chạy sort/hash-heavy.
5. Kiểm tra work_mem/hash_mem_multiplier hiệu lực theo role/session.
6. Xem pool concurrency và batch job parallelism.
7. Giảm concurrency hoặc parallel workers theo incident policy.
8. Hạ setting quá cao ở đúng scope.
9. Xác minh latency/throughput và error rate phục hồi.
10. Cập nhật capacity model và guardrails.

### 42.1. Không chỉ giảm work_mem toàn cục ngay lập tức

Nếu query workload cần memory, giảm mạnh có thể tạo temp I/O bùng nổ. Ưu tiên tìm sessions/roles gây áp lực và thay đổi có kiểm soát.

### 42.2. Không kill sessions tùy tiện

Xác định business operation, transaction safety và owner trước khi cancel/terminate backend.

### 42.3. OOM evidence

Giữ timestamp, cgroup memory, process, PostgreSQL logs, active queries và settings. Dùng evidence để điều chỉnh capacity.

## 43. Test strategy cho work_mem changes

Một thay đổi nên được thử với:
- Query representative và data volume tương đương production.
- Baseline và candidate work_mem.
- Concurrency thực tế.
- Parallel workers planned/launched.
- Temp I/O.
- Peak memory/working set.
- p50/p95/p99 latency.
- TPS/throughput.
- Error/OOM/swap.
- Tác động đến OLTP và background jobs.

### 43.1. Test đơn lẻ chưa đủ

Một query chạy một mình không mô phỏng memory pressure khi 20 queries cùng chạy.

### 43.2. Test peak window

Dùng workload mix giờ cao điểm, batch overlap và report concurrency.

### 43.3. So sánh cùng data state

Statistics, cache state, dataset và query parameters ảnh hưởng plan/performance. Ghi lại điều kiện test.

### 43.4. Rollback criteria

Định nghĩa trước ngưỡng memory, latency, temp disk và error rate khiến phải revert.

## 44. Best practices theo scope

| Scope | Cách dùng | Khuyến nghị |
|---|---|---|
| Global | postgresql.conf | Baseline thận trọng cho workload hỗn hợp |
| Database | ALTER DATABASE | Chỉ khi workload database tương đối đồng nhất |
| Role | ALTER ROLE | Phân biệt API/reporting roles |
| Session | SET | Dùng cẩn thận với pooled connections |
| Transaction | SET LOCAL | Thường phù hợp cho query-specific tuning |
| Parallel query | Worker-aware budget | Xét workers và concurrency |
| Hash operations | hash_mem_multiplier | Tuning riêng sau khi xem plan |

### 44.1. Baseline thấp, override có mục tiêu

Giữ default an toàn và cấp thêm memory cho workloads có evidence.

### 44.2. Giới hạn concurrency

Một reporting pool nhỏ có thể an toàn hơn việc cho hàng trăm sessions chạy query memory-heavy.

### 44.3. Ghi lại owner

Mỗi override cần owner, lý do, phạm vi, ngày review và rollback plan.

### 44.4. Kiểm tra sau upgrade

PostgreSQL major version mới có thể thay planner/executor behavior. Re-test memory assumptions sau upgrade.

## 45. Các hiểu lầm phổ biến

1. **work_mem là RAM tối đa của một query.** Sai: một query có thể có nhiều operators.
2. **work_mem là RAM của một connection.** Sai: setting áp dụng cho từng operation phù hợp.
3. **Tăng work_mem luôn làm query nhanh hơn.** Sai: có thể không ảnh hưởng hoặc làm memory pressure tăng.
4. **Mọi Sort node đều spill.** Sai: nhiều sort chạy trong memory.
5. **Hash Batches = 1 là query chắc chắn tối ưu.** Sai: còn cần xét CPU, row estimates và latency.
6. **temp_bytes là disk usage hiện tại.** Sai: đây là cumulative counter.
7. **work_mem bao gồm shared_buffers.** Sai: hai vùng có mục đích khác nhau.
8. **temp_buffers chữa sort spill.** Sai: temp_buffers dành cho temporary tables.
9. **Parallel query chỉ dùng một work_mem.** Sai: nhiều process/operators có thể tiêu thụ ngân sách riêng.
10. **Nhân workers × work_mem luôn là exact RAM.** Sai: plan/operator behavior và shared parallel structures làm thực tế phức tạp.
11. **ALTER ROLE cập nhật sessions đang mở.** Thường không; defaults áp dụng khi login mới.
12. **SET trong connection pool luôn an toàn.** Sai nếu state không được reset.
13. **SET LOCAL tồn tại sau COMMIT.** Sai: local setting hết hiệu lực khi transaction kết thúc.
14. **Hash multiplier tăng memory mọi sort.** Sai: nó điều chỉnh hash-based operation budget.
15. **Temp files luôn là lỗi.** Sai: spill có thể là trade-off bình thường.
16. **CPU thấp nghĩa memory còn đủ.** Sai: có thể đang swap hoặc chờ I/O.
17. **Một query benchmark đủ để chọn setting.** Sai: phải test concurrency.
18. **work_mem thay maintenance_work_mem.** Sai: các parameter có mục đích riêng.
19. **Giảm work_mem không có rủi ro.** Sai: temp I/O và latency có thể tăng.
20. **Chỉ cần nhìn free RAM.** Sai: cần cgroup limits, shared memory, swap, process concurrency và headroom.

## 46. Bài tập thực hành có đáp án

### Bài 1. work_mem là gì?

**Đáp án:** Ngân sách bộ nhớ cho mỗi thao tác query phù hợp, chủ yếu sort và hash operations, trước khi phải dùng chiến lược spill/batching.

### Bài 2. work_mem là giới hạn tổng memory của một query?

**Đáp án:** Không. Một query có thể có nhiều memory-consuming operators.

### Bài 3. work_mem áp dụng theo connection hay operation?

**Đáp án:** Theo từng operation phù hợp trong executor; mỗi backend/process có thể chạy nhiều operations theo plan.

### Bài 4. Vì sao tăng work_mem toàn cục có thể nguy hiểm?

**Đáp án:** Nhiều sessions, operators và parallel workers có thể cùng dùng ngân sách riêng, làm tổng memory demand tăng lớn.

### Bài 5. Sort spill là gì?

**Đáp án:** Sort vượt memory budget và dùng temporary files/external sort.

### Bài 6. EXPLAIN có thể hiện dấu hiệu external sort nào?

**Đáp án:** Sort Method như external merge và Disk usage.

### Bài 7. Hash Batches lớn hơn 1 gợi ý gì?

**Đáp án:** Hash operation chia dữ liệu thành nhiều batches, thường có spill/temp I/O.

### Bài 8. Hash join dùng memory cho phần nào?

**Đáp án:** Build-side hash table và các structures liên quan.

### Bài 9. Hash aggregate cần memory vì sao?

**Đáp án:** Nó giữ hash table cho grouping keys và aggregate states.

### Bài 10. hash_mem_multiplier dùng làm gì?

**Đáp án:** Nhân work_mem để xác định memory limit tương đối cho hash-based operations.

### Bài 11. work_mem = 32 MB, hash_mem_multiplier = 2; hash budget cơ sở xấp xỉ?

**Đáp án:** Khoảng 64 MB theo semantics/version tương ứng.

### Bài 12. Tăng hash_mem_multiplier có tăng sort budget không?

**Đáp án:** Không; nó áp dụng cho hash operations.

### Bài 13. Vì sao actual rows quan trọng?

**Đáp án:** Cardinality thực tế quyết định lượng tuples đi vào sort/hash và có thể khác planner estimate.

### Bài 14. Statistics stale có thể gây gì?

**Đáp án:** Planner estimates sai, chọn plan và memory behavior không phù hợp.

### Bài 15. EXPLAIN ANALYZE có thực thi query không?

**Đáp án:** Có. Cần thận trọng với DML và side effects.

### Bài 16. pg_stat_database.temp_bytes là counter hay gauge?

**Đáp án:** Counter tích lũy; lấy delta/time để tính temp write rate.

### Bài 17. pg_stat_statements temp_blks_written giúp gì?

**Đáp án:** Tìm query entries ghi nhiều temporary blocks.

### Bài 18. log_temp_files = 0 có nghĩa gì?

**Đáp án:** Log mọi temporary files theo semantics của parameter.

### Bài 19. temp_file_limit có làm query dùng ít memory hơn?

**Đáp án:** Không. Nó giới hạn temp disk mà process được sử dụng; vượt mức có thể làm query fail.

### Bài 20. pg_backend_memory_contexts cho biết memory của ai?

**Đáp án:** Backend/session chạy query view đó, không phải toàn instance.

### Bài 21. Vì sao RSS cộng tất cả backends có thể đếm trùng?

**Đáp án:** Shared memory mappings có thể được tính trong RSS của nhiều processes.

### Bài 22. SET work_mem ảnh hưởng scope nào?

**Đáp án:** Session hiện tại và các query sau đó cho tới khi reset hoặc session kết thúc.

### Bài 23. SET LOCAL khác SET thế nào?

**Đáp án:** SET LOCAL chỉ tồn tại trong transaction hiện tại và tự hết hiệu lực khi COMMIT/ROLLBACK.

### Bài 24. Vì sao SET LOCAL phù hợp connection pooling?

**Đáp án:** Nó giới hạn setting trong transaction, giảm nguy cơ rò session state sang request tiếp theo.

### Bài 25. ALTER ROLE SET work_mem áp dụng khi nào?

**Đáp án:** Là default cho sessions đăng nhập mới bằng role đó; sessions đang mở không tự nhận thay đổi.

### Bài 26. ALTER DATABASE SET có thay đổi mọi backend đang chạy?

**Đáp án:** Không. Default thường được áp dụng cho sessions mới.

### Bài 27. shared_buffers khác work_mem thế nào?

**Đáp án:** shared_buffers là shared page cache; work_mem là budget cho query operations.

### Bài 28. maintenance_work_mem dùng cho gì?

**Đáp án:** Một số maintenance operations như VACUUM/CREATE INDEX theo semantics của version.

### Bài 29. temp_buffers dùng cho gì?

**Đáp án:** Local buffers cho temporary tables, không phải sort spill budget.

### Bài 30. Parallel query có thể nhân memory pressure ra sao?

**Đáp án:** Leader và workers có thể thực thi các memory-consuming operators với ngân sách riêng.

### Bài 31. Workers Planned và Workers Launched khác nhau?

**Đáp án:** Planned là số planner dự kiến; Launched là số thực tế được khởi chạy.

### Bài 32. Parallel Hash luôn có hash table riêng cho mỗi worker?

**Đáp án:** Không. Một số plan dùng shared parallel hash structures; phải xem implementation/plan.

### Bài 33. Công thức modeled sort budget cho 4 workers và leader, work_mem 32 MB?

**Đáp án:** Khoảng 5 × 32 = 160 MB nếu cả 5 processes có một sort operation cùng active; đây là estimate bảo thủ.

### Bài 34. Có nên cộng mọi Sort/Hash nodes trong plan?

**Đáp án:** Không máy móc. Xem node lifetime và operations thực sự active cùng lúc.

### Bài 35. Khi nào tăng work_mem có thể đúng?

**Đáp án:** Khi evidence cho thấy sort/hash spill gây latency, estimates hợp lý, host còn headroom và concurrency được kiểm soát.

### Bài 36. Khi nào không nên tăng work_mem?

**Đáp án:** Khi bottleneck là lock, CPU, network, pool queue, bad query plan hoặc host memory đã thiếu.

### Bài 37. Index có thể giúp giảm work_mem demand thế nào?

**Đáp án:** Index phù hợp có thể loại explicit sort hoặc giảm rows phải xử lý.

### Bài 38. Vì sao SELECT * có thể làm sort tốn memory hơn?

**Đáp án:** Tuple rộng hơn, làm tăng dữ liệu cần giữ/sort.

### Bài 39. OLTP nên dùng strategy nào?

**Đáp án:** Baseline thận trọng, pool concurrency có giới hạn, query optimization và scoped overrides cho query nặng.

### Bài 40. Reporting nên được quản lý thế nào?

**Đáp án:** Role/pool riêng, concurrency và parallelism giới hạn, temp capacity và memory được theo dõi.

### Bài 41. Vì sao test một query đơn lẻ không đủ?

**Đáp án:** Không mô phỏng nhiều sessions/workers cùng tiêu thụ memory.

### Bài 42. OOM event yêu cầu xem metrics nào?

**Đáp án:** Host/cgroup memory, swap, OOM events, process RSS, active sessions, workers và settings.

### Bài 43. Tăng max_parallel_workers_per_gather có trade-off gì?

**Đáp án:** Có thể tăng query parallelism nhưng cũng tăng CPU, memory và I/O demand.

### Bài 44. work_mem có thay autovacuum_work_mem không?

**Đáp án:** Không. Autovacuum có memory configuration riêng.

### Bài 45. Vì sao temp files không luôn là incident?

**Đáp án:** Spill là cơ chế xử lý query vượt memory budget; chỉ đáng can thiệp khi gây latency/capacity impact.

### Bài 46. hash Batches = 1 có đảm bảo query nhanh?

**Đáp án:** Không. CPU, scans, locks, I/O và plan vẫn có thể là bottleneck.

### Bài 47. Tuning work_mem nên thay đổi bao nhiêu lần một lúc?

**Đáp án:** Nên thử một biến/nhóm nhỏ mỗi lần để đo được nguyên nhân và giữ rollback rõ.

### Bài 48. Sau khi thay role default, cần làm gì với pool connections?

**Đáp án:** Recycle/reconnect sessions nếu cần nhận default mới và kiểm tra session state reset.

### Bài 49. Một alert work_mem tốt cần những gì?

**Đáp án:** Temp spill trend, query latency, host memory/headroom, temp disk capacity, duration và runbook.

### Bài 50. Điều kiện kết thúc tuning work_mem?

**Đáp án:** Query/workload đạt latency mục tiêu dưới concurrency đại diện, không gây memory/OOM/temp capacity regression và có rollback/owner rõ ràng.

## 47. Checklist điều chỉnh work_mem

| Bước | Câu hỏi |
|---|---|
| Query | Operator nào đang tiêu thụ memory? |
| Plan | Sort, Hash, HashAggregate hay tuplestore? |
| Spill | External sort, batches, temp blocks/files? |
| Estimate | Planned rows có gần actual rows? |
| Width | Có SELECT thừa columns? |
| Index | Có thể tránh sort hoặc giảm build side? |
| Stats | ANALYZE/extended stats có phù hợp? |
| Scope | Global, database, role, session hay transaction? |
| Concurrency | Bao nhiêu query memory-heavy cùng chạy? |
| Parallel | Workers planned/launched và leader? |
| Hash | hash_mem_multiplier hiệu lực? |
| Host | Available memory, swap, cgroup limit, OOM? |
| Disk | Temp filesystem free space và latency? |
| Pool | Active sessions/waiters và job concurrency? |
| Test | Baseline/candidate dưới load đại diện? |
| Outcome | p95/p99, throughput, temp I/O, memory? |
| Safety | Có timeout, rollback và owner? |
| Rollback | Có cách phục hồi setting trước đó? |
| Review | Có version-specific validation sau upgrade? |

## 48. Tài liệu PostgreSQL chính thức

- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — work_mem, hash_mem_multiplier, shared_buffers và memory settings.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — đọc sort/hash nodes, estimates và actual execution.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_database, pg_stat_activity và statistics.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query-level execution/temp block statistics.
- [Parallel Query](https://www.postgresql.org/docs/current/parallel-query.html) — leader, workers và parallel execution behavior.
- [Resource Consumption: Memory](https://www.postgresql.org/docs/current/runtime-config-resource.html#RUNTIME-CONFIG-RESOURCE-MEMORY) — memory parameters.
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html) — role-level defaults.
- [ALTER DATABASE](https://www.postgresql.org/docs/current/sql-alterdatabase.html) — database-level defaults.
- [SET](https://www.postgresql.org/docs/current/sql-set.html) — session và transaction-local configuration.
- [Logging Configuration](https://www.postgresql.org/docs/current/runtime-config-logging.html) — log_temp_files và query logging.
- [Monitoring I/O](https://www.postgresql.org/docs/current/monitoring-stats.html) — I/O stats theo version.

Các parameter, EXPLAIN fields, parallel memory behavior và statistics views có thể thay đổi theo PostgreSQL major version. Kiểm tra server_version, pg_settings, view definitions và tài liệu đúng phiên bản trước khi đưa cấu hình vào production.

## 49. Tổng kết: cấp memory đúng nơi, trong đúng thời gian

```text
Query plan
   |
   +-- Sort node       -> work_mem
   |
   +-- Hash node       -> work_mem × hash_mem_multiplier
   |
   +-- More operators  -> more possible consumers
   |
   +-- Parallel workers/leader -> more processes
   |
   v
Concurrent sessions and workloads
   |
   v
Total memory pressure + temp I/O
   |
   v
Measure -> scope setting -> load test -> verify
```

Những nguyên tắc cần nhớ:

1. **work_mem áp dụng theo operation.** Một query có thể có nhiều sort/hash consumers.
2. **Session không phải đơn vị duy nhất.** Nhiều sessions và parallel workers có thể đồng thời sử dụng memory.
3. **Hash operations có multiplier riêng.** Xem hash_mem_multiplier và version.
4. **Spill là tín hiệu cần phân tích.** External sort, hash batches và temp blocks cho biết operator đang dùng disk.
5. **Actual rows và row width quan trọng.** Statistics sai hoặc SELECT thừa columns có thể làm memory demand tăng.
6. **SET LOCAL giúp tuning có phạm vi.** Nó phù hợp với query/request cụ thể và connection pooling khi transaction được quản lý đúng.
7. **Role/database defaults cần tính tới sessions mới.** Pool connections cũ có thể giữ settings đã nạp.
8. **Parallel query tăng resource demand.** Xem Workers Launched, leader participation và concurrency.
9. **Không nhầm work_mem với shared_buffers hay maintenance_work_mem.** Mỗi parameter có vai trò riêng.
10. **Tối ưu query trước khi tăng memory.** Index, filters, join strategy và statistics có thể giảm nhu cầu.
11. **Theo dõi cả RAM lẫn temp disk.** Tăng memory có thể giảm spill nhưng tạo rủi ro OOM; giảm memory có thể làm temp I/O tăng.
12. **Test dưới tải đồng thời.** Một query chạy đơn lẻ không đại diện production concurrency.

**Một câu để nhớ:** *work_mem là ngân sách cho từng thao tác, vì vậy hãy chọn mức mặc định theo concurrency và chỉ tăng có kiểm soát ở session/transaction cần thiết sau khi đã đo plan, spill, parallel workers và memory headroom.*

