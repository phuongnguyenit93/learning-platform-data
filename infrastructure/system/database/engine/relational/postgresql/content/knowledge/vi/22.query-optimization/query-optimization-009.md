# Xử lý sort hoặc hash tràn ra đĩa

Một báo cáo trước đây chạy trong 300 ms, hôm nay mất hơn 10 giây. `EXPLAIN (ANALYZE, BUFFERS)` cho thấy:

```text
Sort Method: external merge  Disk: 36000kB
Buffers: shared hit=..., temp read=... written=...
```

Hoặc một câu JOIN báo:

```text
Hash
  Buckets: ...  Batches: 64  Memory Usage: ...
  Buffers: temp written=...
```

Đây là hai dấu hiệu thường gặp của **sort hoặc hash tràn ra đĩa** (*spill to disk*). PostgreSQL cố xử lý công việc trung gian bằng bộ nhớ; khi dữ liệu/thuật toán vượt ngân sách thích hợp, executor có thể dùng các **temporary files** để hoàn thành phép sắp xếp hoặc chia lô hash. Query vẫn cho kết quả đúng, nhưng tốc độ, I/O và áp lực lên storage có thể thay đổi mạnh.

Bài học này tập trung vào câu hỏi: **Làm sao phát hiện đúng node bị spill, hiểu vì sao spill xảy ra và chọn phương án xử lý có lợi cho toàn hệ thống?**

Các nội dung chính:

- Phân biệt **sort in-memory**, **external sort**, **top-N heapsort**, **incremental sort**.
- Hiểu **Hash Join**, **HashAggregate**, **hash table**, **buckets**, **batches**, memory và temporary partitions.
- Đọc `Sort Method`, `Disk`, `Memory Usage`, `Batches` và `Buffers: temp read/written` trong execution plan.
- Hiểu đúng `work_mem`, `hash_mem_multiplier`, parallel workers và nguy cơ nhân mức dùng RAM khi có nhiều truy vấn đồng thời.
- Quan sát temp files qua `log_temp_files`, `pg_stat_database` và `pg_stat_statements` khi được cấu hình.
- Giảm spill bằng **index đúng thứ tự**, **lọc dữ liệu sớm**, **giảm row width**, **giảm cardinality**, **sửa ước lượng thống kê**, **đổi cách GROUP BY/JOIN** và điều chỉnh cấu hình có kiểm soát.
- Tái hiện bằng SQL lab, quy trình benchmark, troubleshooting và lưu ý tích hợp Java/JDBC.

> **Phạm vi:** PostgreSQL hiện đại, tập trung vào kế hoạch truy vấn và tối ưu executor. Kết quả plan và số liệu phụ thuộc phiên bản, cấu hình và dữ liệu; các con số minh họa không phải output cam kết của một server cụ thể. Các thí nghiệm thay đổi `work_mem`, hạn chế plan methods hoặc tạo tập dữ liệu lớn chỉ nên chạy trong môi trường lab có tài nguyên phù hợp.

## 1. Thế nào là một thao tác “tràn ra đĩa”?

PostgreSQL có các operator cần vùng nhớ tạm để thực hiện công việc:

- `ORDER BY` có thể đòi **Sort**.
- `DISTINCT` và `GROUP BY` có thể dùng **Sort/Unique**, **GroupAggregate** hoặc **HashAggregate**.
- `JOIN` có thể chọn **Hash Join**, cần dựng hash table cho một đầu vào.
- `WindowAgg` có thể cần dữ liệu đã được sắp xếp, và trong một số tình huống dùng tuplestore.
- `Materialize`, CTE materialization và các node khác cũng có thể cần lưu kết quả trung gian.

Nếu dữ liệu phù hợp ngân sách nhớ, PostgreSQL xử lý trong RAM. Nếu không, executor có thể **ghi và đọc lại dữ liệu trung gian trên temporary files**.

```text
                           Dữ liệu đầu vào
                                  │
                                  ▼
                         Sort / Hash operator
                                  │
                  ┌───────────────┴────────────────┐
                  │                                │
             Vừa ngân sách                   Vượt ngân sách
                  │                                │
                  ▼                                ▼
             Xử lý trong RAM                Chia lô / tạo run
                  │                         ghi temporary files
                  │                                │
                  │                                ▼
                  │                         Đọc lại, xử lý
                  │                         và/hoặc merge
                  └───────────────┬────────────────┘
                                  ▼
                           Kết quả đúng
```

Spill là **chiến lược thực thi hợp lệ**, không phải lỗi SQL. Nó trở thành vấn đề hiệu năng khi I/O, dung lượng temp, số lượt xử lý hoặc cạnh tranh tài nguyên vượt mức chấp nhận được.

## 2. Không phải cứ dùng đĩa là “spill”

Một query đọc các trang bảng/index từ storage không phải tự động là spill:

```text
Buffers: shared read=15000
```

đề cập đến việc nạp page qua shared-buffer mechanism.

Trong khi:

```text
Buffers: temp read=15000 written=22000
```

thường cho thấy temporary working files của executor.

Phân biệt:

| Hoạt động | Dấu hiệu thường thấy | Đối tượng |
|---|---|---|
| Đọc bảng/index | `shared hit/read` | Relation pages. |
| Ghi trang bảng/index | `shared dirtied/written` | Data/index pages. |
| Temporary table | `local hit/read/dirtied/written` | Temporary relation qua local buffers. |
| Spill sort/hash | `temp read/written`, Sort/Hash details | Working files trung gian. |
| Ghi WAL | `WAL records/fpi/bytes` | Write-ahead log, khác temp files. |

**Không nhầm `CREATE TEMP TABLE` với file temp sinh bởi external sort.** Cả hai đều có thể liên quan không gian tạm, nhưng các loại buffer, giới hạn và mục đích khác nhau.

## 3. Vì sao spill làm truy vấn chậm?

Một sort in-memory có thể thao tác trên dữ liệu trong RAM. Khi phải external sort, executor thường cần:

1. Đọc dữ liệu nguồn.
2. Tạo những phần đã sắp xếp (*runs*) phù hợp bộ nhớ.
3. Ghi runs ra temporary files.
4. Đọc lại các runs để merge.
5. Trả kết quả theo thứ tự yêu cầu.

Một Hash Join bị thiếu bộ nhớ có thể:

1. Phân phối dữ liệu theo hash value.
2. Giữ một phần trong RAM.
3. Ghi các partitions/batches còn lại ra file tạm.
4. Đọc lại từng batch và xử lý các cặp phù hợp.

Những lượt đọc/ghi bổ sung tiêu tốn:

- Băng thông I/O và IOPS.
- CPU tính toán hash, partition, compare và merge.
- Temporary disk capacity.
- Thời gian CPU và buffer cache cho các đoạn khác của query.
- Sự ổn định khi nhiều backend cùng spill.

**Spill không nhất thiết luôn chậm đáng kể**: nếu kích thước nhỏ, storage nhanh và tải thấp, chi phí có thể chấp nhận được. Tối ưu hiệu năng cần đánh giá theo **execution time, độ biến thiên và tải tổng**, không theo một quy tắc “temp_written phải bằng 0”.

## 4. work_mem là gì?

`work_mem` là cấu hình giới hạn ngân sách nhớ cơ bản dành cho **một số thao tác thực thi như Sort và Hash** trước khi ghi dữ liệu vào temporary files hoặc dùng phương án chia lô.

Kiểm tra:

```sql
SHOW work_mem;

SELECT
    name,
    setting,
    unit,
    source,
    context
FROM pg_catalog.pg_settings
WHERE name = 'work_mem';
```

### Không phải bộ nhớ tối đa của một query

Đây là hiểu nhầm lớn nhất:

> “work_mem = 64MB thì mỗi truy vấn chỉ dùng tối đa 64MB.”

Không đúng. Một query có thể có **nhiều Sort/Hash operators** cùng hoạt động và các parallel workers. Mỗi hoạt động thuộc loại áp dụng có thể dùng ngân sách nhớ riêng. Query còn có các loại memory khác như executor state, result building, caches, aggregation contexts và session memory.

```text
Một plan có thể có:

Sort A              → ngân sách work_mem
  └─ Hash Join       → ngân sách hash work_mem × multiplier
       ├─ Sort B     → ngân sách work_mem
       └─ Hash       → ngân sách hash phù hợp

Parallel workers có thể nhân phần sử dụng bộ nhớ.
```

Vì vậy **không lấy `work_mem` nhân một lần duy nhất để suy ra mức RAM cả database**.

## 5. Vì sao work_mem toàn server quá cao nguy hiểm?

Giả sử một workload có:

- Nhiều backend truy vấn đồng thời.
- Mỗi plan có nhiều Sort/Hash nodes.
- Một phần query dùng parallel workers.

Nếu tăng `work_mem` từ vài MiB lên hàng trăm MiB toàn instance mà không kiểm soát concurrency, tổng lượng RAM có thể tăng rất lớn.

Ví dụ **ước lượng khái niệm, không phải công thức phân bổ chính xác**:

```text
20 query đồng thời
× 3 operator ngốn memory mỗi query
× 64 MiB
= 3840 MiB ngân sách cho những operator đó

Chưa tính parallel workers, hash_mem_multiplier và memory khác.
```

Đó là lý do một giá trị tối ưu cho **một truy vấn đơn lẻ** có thể khiến server **thiếu RAM/OOM** khi hàng chục truy vấn chạy cùng lúc.

### Bộ nhớ không được phân bổ ngay toàn bộ

`work_mem=64MB` không có nghĩa mỗi query tự động allocate đủ 64 MB. Bộ nhớ được dùng theo nhu cầu của operator, nhưng cấu hình cao mở rộng khả năng sử dụng khi dữ liệu lớn.

### Chiến lược an toàn

Tối ưu **cấu trúc truy vấn** trước, sau đó thử `SET LOCAL work_mem` trong transaction cụ thể. Chỉ tăng giá trị toàn server khi đã phân tích concurrency và memory budget ở cấp instance.

## 6. hash_mem_multiplier là gì?

PostgreSQL có `hash_mem_multiplier` để điều chỉnh giới hạn bộ nhớ cho những phép xử lý hash phù hợp, **theo bội số của `work_mem`**.

Kiểm tra:

```sql
SHOW hash_mem_multiplier;

SELECT
    current_setting('work_mem') AS work_mem,
    current_setting('hash_mem_multiplier')
        AS hash_mem_multiplier;
```

Mô hình khái niệm:

```text
Ngân sách hash operation ≈ work_mem × hash_mem_multiplier
```

Ví dụ nếu `work_mem=16MB` và `hash_mem_multiplier=2`, một hash operation phù hợp có thể được cho ngân sách mục tiêu khoảng **32 MB**.

### Điều này khác Sort

Tăng `hash_mem_multiplier` hướng đến hash-based operations; nó không nhất thiết làm một `Sort` external merge biến thành quicksort.

### Tại sao không tăng hai thông số vô hạn?

Giống `work_mem`, ngân sách hash được áp dụng trên nhiều hoạt động và backend. Tăng multiplier có thể giảm hash spilling cho một truy vấn nhưng gây áp lực RAM khi có nhiều joins/aggregates đồng thời.

### Phiên bản và điều kiện

Các GUC và giới hạn hợp lệ phụ thuộc phiên bản PostgreSQL. Nếu server quá cũ không hỗ trợ `hash_mem_multiplier`, đừng áp dụng câu `SET` từ bài này mà không kiểm tra trước.

## 7. Các bộ nhớ khác không thay thế work_mem

| Tham số | Vai trò khái quát |
|---|---|
| `shared_buffers` | Vùng cache trang bảng/index chung của PostgreSQL. |
| `work_mem` | Bộ nhớ cơ bản cho một số executor operations như sort/hash. |
| `hash_mem_multiplier` | Hệ số nhân ngân sách cho hash operations. |
| `temp_buffers` | Local buffer memory cho temporary tables trong session. |
| `maintenance_work_mem` | Bộ nhớ cho những tác vụ maintenance nhất định như VACUUM/CREATE INDEX. |
| `autovacuum_work_mem` | Bộ nhớ phục vụ autovacuum khi được cấu hình, có cơ chế kế thừa tùy setting. |
| `effective_cache_size` | Ước lượng cache cho planner cost model, không phải cấp phát RAM. |

Một query `ORDER BY` thông thường không tự dùng `maintenance_work_mem` thay cho `work_mem` chỉ vì nó tạo Sort node. Và tăng `shared_buffers` không trực tiếp tăng bộ nhớ cho external sort.

**Phải xác định đúng operator và memory context** trước khi chỉnh tham số.

## 8. Sort trong PostgreSQL vận hành ra sao?

PostgreSQL có thể dùng những phương pháp sắp xếp khác nhau tùy kế hoạch và lượng dữ liệu:

- **Quicksort:** một trường hợp sắp xếp trong bộ nhớ.
- **Top-N heapsort:** giữ nhóm ứng viên tốt nhất khi chỉ cần vài hàng đầu của kết quả đã sắp xếp.
- **External merge sort:** dữ liệu vượt bộ nhớ, cần tạo runs và merge qua temporary files.
- **Incremental sort:** tận dụng thứ tự prefix đã có để sắp xếp từng nhóm nhỏ.

`EXPLAIN ANALYZE` có thể báo:

```text
Sort Method: quicksort  Memory: 4120kB
```

hoặc:

```text
Sort Method: top-N heapsort  Memory: 35kB
```

hoặc:

```text
Sort Method: external merge  Disk: 40520kB
```

Những con số này chỉ là minh họa. Kiểu thuật toán được báo phụ thuộc vào cách PostgreSQL thực thi plan trong lần chạy thực tế.

### Không phải mọi ORDER BY tạo Sort node

Nếu index hoặc đầu ra của một node đã đáp ứng thứ tự cần thiết, planner có thể **bỏ Sort node**. Đây là một trong những cách tốt nhất để tránh spill: **không sắp xếp lại dữ liệu nếu có thể nhận dữ liệu theo đúng thứ tự ngay từ đầu**.

## 9. Chuẩn bị SQL lab

Tạo schema:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_spill;
```

Một bảng dữ liệu giao dịch:

```sql
CREATE TABLE lesson_spill.sales (
    sale_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    sold_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'CANCELLED')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    note TEXT NOT NULL
);
```

Tạo 90.000 hàng với dữ liệu giả:

```sql
INSERT INTO lesson_spill.sales (
    sale_id,
    tenant_id,
    customer_id,
    product_id,
    sold_at,
    status,
    amount,
    note
)
SELECT
    g,
    1 + (g % 10),
    1 + (g % 2000),
    1 + (g % 45000),
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g * INTERVAL '1 minute'),
    CASE WHEN g % 11 = 0
         THEN 'CANCELLED' ELSE 'PAID' END,
    ((g % 100000) + 1)::numeric / 100,
    repeat('x', 140) || '-' || g::text
FROM generate_series(1, 90000) AS g;
```

Thêm bảng kích thước tương đối lớn làm nguồn hash join:

```sql
CREATE TABLE lesson_spill.products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    description TEXT NOT NULL,
    category_id INTEGER NOT NULL
);

INSERT INTO lesson_spill.products (
    product_id,
    product_name,
    description,
    category_id
)
SELECT
    g,
    'Product ' || g::text,
    repeat('p', 180) || '-' || g::text,
    1 + (g % 500)
FROM generate_series(1, 45000) AS g;
```

Thu thập thống kê:

```sql
ANALYZE lesson_spill.sales;
ANALYZE lesson_spill.products;
```

### Cảnh báo về khối lượng

Số hàng/cột text trên đủ để nhiều máy lab quan sát spill khi `work_mem` nhỏ, nhưng không cam kết mọi version/planner đều chọn cùng node. Nếu môi trường hạn chế, giảm số hàng; khi đó spill có thể khó xuất hiện hơn.

Không tạo 90.000 hàng này trong database production đang dùng thật chỉ để thực hành.

## 10. Bài thử external sort đầu tiên

Chọn thứ tự không có index hỗ trợ trực tiếp:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT TEXT
)
SELECT
    sale_id,
    tenant_id,
    note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

### Vì sao dùng md5(sale_id::text)?

Trong lab không có index trên biểu thức `md5(sale_id::text)`, do đó một Sort node có khả năng được chọn. Lấy toàn bộ 90.000 hàng làm cho sort phải xử lý tương đối nhiều dữ liệu; `work_mem='64kB'` làm ngân sách nhỏ.

Plan có thể có:

```text
Sort
  Sort Key: (md5((sale_id)::text))
  Sort Method: external merge  Disk: ...kB
  Buffers: shared hit=..., temp read=... written=...
  -> Seq Scan on sales
       Buffers: shared hit=...
```

### Đọc từng dấu hiệu

1. `Sort` là node cần sắp xếp.
2. `Sort Method: external merge` cho thấy sort dùng phương án external.
3. `Disk` là thông tin dung lượng working space được báo cho Sort node.
4. `temp read/written` là số lần đọc/ghi temporary blocks trong phạm vi đo.
5. Child Seq Scan vẫn đọc bảng thật, thể hiện chủ yếu qua `shared hit/read`.

**Không gộp `shared read` và `temp read` thành một số “bảng đã đọc”.** Chúng phục vụ hai đường truy cập khác nhau.

## 11. So sánh với sort trong memory

Chạy lại cùng query với ngân sách lớn hơn, **chỉ trong transaction lab**:

```sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    sale_id,
    tenant_id,
    note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

Với dữ liệu lab này, bạn có thể thấy:

```text
Sort Method: quicksort  Memory: ...kB
```

và temp read/write giảm hoặc không còn. Nhưng một số môi trường vẫn có thể cần temp nếu working set, tuple overhead hoặc kế hoạch lớn hơn dự kiến.

### So sánh công bằng

- Giữ nguyên SQL và dữ liệu.
- Giữ các settings khác không đổi.
- Chạy nhiều lần, có lượt warm-up.
- Ghi `Sort Method`, `Disk/Memory`, temp blocks, runtime.
- Xem có plan khác nhau không.
- Đánh giá memory khi nhiều query chạy đồng thời.

Đây là **thử nghiệm nguyên nhân**; chưa phải bằng chứng cần tăng `work_mem` toàn server lên 64 MB.

## 12. Temp blocks trong EXPLAIN BUFFERS

Để quan sát spill:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
```

Dòng output thường có:

```text
Buffers: temp read=1500 written=2400
```

Đây là số temporary blocks trong phạm vi instrumentation của node. Nếu page size là 8 KiB, 1500 blocks tương đương khoảng 12 MiB **block accesses tính theo byte**, nhưng:

- Không phải khẳng định 12 MiB dữ liệu duy nhất.
- Một block có thể được đọc/ghi nhiều lượt.
- OS page cache có thể đáp ứng I/O mà không chạm vật lý tới SSD.
- Counters parent có thể bao gồm hoạt động của child.

Kiểm tra block size:

```sql
SHOW block_size;
```

### Vì sao temp read và written không nhất thiết bằng nhau?

External sort có thể tạo runs, rồi merge qua nhiều lượt. Một số blocks có thể được ghi nhưng chưa đọc lại trong phạm vi đo theo cùng cách; hoặc một nhóm blocks bị đọc lặp qua các passes. Không suy ra leak temp file nếu hai counters khác nhau.

### Không cộng mọi node

Ví dụ:

```text
Aggregate       temp read=100 written=150
  └── Sort      temp read=100 written=150
```

Không cộng thành 200 reads và 300 writes cho statement vì có thể **đếm lại cùng hoạt động** ở parent/child.

## 13. Sort Method: quicksort, external merge, top-N

| Dấu hiệu | Ý nghĩa điển hình | Hướng phân tích |
|---|---|---|
| `quicksort Memory: ...` | Sort được thực hiện trong memory. | Xem có cần sort, số rows/width, không mặc nhiên tối ưu rồi. |
| `external merge Disk: ...` | Sort sử dụng temporary files. | Tìm nguyên nhân số rows/width lớn, work_mem, chỉ mục, ORDER BY. |
| `top-N heapsort Memory: ...` | Chỉ giữ nhóm tốt nhất để đáp ứng giới hạn kết quả. | Xem LIMIT, lượng dữ liệu đầu vào, khả năng index top-N. |
| `Incremental Sort` | Tận dụng prefix đã được sắp xếp; xử lý theo nhóm. | Xem `Presorted Key`, số nhóm, bộ nhớ, temp spill của nhóm. |

### Top-N không có nghĩa chỉ đọc N hàng

```sql
SELECT sale_id
FROM lesson_spill.sales
ORDER BY md5(sale_id::text)
LIMIT 20;
```

Nếu không có index cung cấp thứ tự này, executor vẫn có thể phải **đọc hầu hết/toàn bộ 90.000 rows** để biết đâu là 20 giá trị tốt nhất, dù chỉ giữ 20 ứng viên trong heap.

Top-N thường giảm memory của sort, nhưng không tự giảm lượng quét đầu vào.

### Sort trong memory vẫn có thể tốn CPU

Một query sắp xếp 1 triệu hàng nhưng vừa RAM vẫn phải so sánh các khóa và duy trì cấu trúc dữ liệu. Không có temp spill không đồng nghĩa sort miễn phí.

## 14. ORDER BY và LIMIT: hai tối ưu khác nhau

Giả sử trang bán hàng cần 20 đơn mới nhất của một tenant:

```sql
SELECT
    sale_id,
    sold_at,
    amount
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Hai chiến lược có thể xảy ra:

**Không có index thứ tự phù hợp:**

```text
Seq Scan/Bitmap Scan các đơn tenant 3
  → Top-N Sort
  → 20 rows
```

**Có index khớp điều kiện và thứ tự:**

```text
Index Scan theo (tenant_id, sold_at DESC, sale_id DESC)
  → lấy 20 rows đầu phù hợp
```

Lựa chọn thứ hai vừa có thể **tránh Sort**, vừa có thể **giảm số hàng phải đọc** nhờ `LIMIT`.

## 15. Tạo index hỗ trợ thứ tự

```sql
CREATE INDEX ix_sales_tenant_recent
ON lesson_spill.sales (
    tenant_id,
    sold_at DESC,
    sale_id DESC
);

ANALYZE lesson_spill.sales;
```

Kiểm tra:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id,
    sold_at,
    amount
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Planner có thể dùng index để trả dữ liệu đã theo đúng thứ tự, **không cần Sort node**.

### Thứ tự cột quan trọng

`tenant_id` đầu tiên giúp lọc theo tenant. Các cột tiếp theo khớp `ORDER BY sold_at DESC, sale_id DESC`.

### Vì sao thêm sale_id?

`sold_at` có thể trùng giữa nhiều hàng. Thêm `sale_id` vào ORDER BY giúp kết quả có **tie-breaker ổn định**, hữu ích cho phân trang theo khóa.

### Không tạo index cho mọi ORDER BY

Một index mới tiêu tốn disk/WAL và tăng chi phí insert/update/delete. Chỉ tạo nếu workload quan trọng và lợi ích tổng thể rõ ràng; xem `EXPLAIN` thực tế chứ không tạo index theo trực giác.

## 16. ORDER BY expression có thể ngăn tận dụng index thường

So sánh:

```sql
ORDER BY sold_at DESC
```

với:

```sql
ORDER BY date_trunc('day', sold_at) DESC
```

Index trên `sold_at` không có nghĩa planner có thể dùng nó để thỏa trực tiếp mọi **thứ tự của biểu thức** liên quan.

Để tránh Sort, có thể cần:

- Viết lại query để dùng thứ tự phù hợp nghiệp vụ.
- Thiết kế expression index khi biểu thức đủ điều kiện và workload quan trọng.
- Dùng computed/generated column phù hợp.
- Chấp nhận Sort nếu số hàng nhỏ và chi phí tạo index không đáng.

**Không tạo expression index tùy tiện theo một function phụ thuộc timezone/session setting**. PostgreSQL có yêu cầu về tính bất biến (*IMMUTABLE*) cho index expressions.

## 17. DISTINCT ON và index sắp xếp

Ví dụ cần đơn mới nhất của mỗi khách trong tenant 3:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    sale_id,
    sold_at,
    amount
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY
    customer_id,
    sold_at DESC,
    sale_id DESC;
```

Nếu không có thứ tự phù hợp, PostgreSQL có thể cần Sort trước khi chọn bản đầu của mỗi nhóm.

Index có thể giúp:

```sql
CREATE INDEX ix_sales_tenant_customer_recent
ON lesson_spill.sales (
    tenant_id,
    customer_id,
    sold_at DESC,
    sale_id DESC
);
```

Với `tenant_id=3`, index sắp theo `customer_id` và thứ tự mới nhất trong từng khách, phù hợp với `DISTINCT ON`/`ORDER BY`.

### Quy tắc DISTINCT ON

Các biểu thức `DISTINCT ON` phải tương thích phần đầu của `ORDER BY` theo quy tắc PostgreSQL. Nếu không có tie-breaker rõ ràng, hàng “đầu tiên” trong mỗi nhóm có thể không xác định về nghiệp vụ.

### Đọc plan thật

Index có thể giúp bỏ Sort nhưng không đảm bảo query chỉ quét mỗi nhóm một hàng. Tùy plan/phiên bản, executor có thể vẫn phải duyệt nhiều entries rồi `Unique` chọn ra hàng đầu. Phải đo buffer accesses và runtime.

## 18. Incremental Sort là gì?

**Incremental Sort** tận dụng việc input **đã được sắp xếp theo một prefix** của `ORDER BY`.

Giả sử query cần:

```sql
ORDER BY tenant_id, amount DESC
```

nhưng index chỉ đảm bảo:

```text
tenant_id tăng dần
```

Thay vì gom toàn bộ dữ liệu rồi sort một lần, PostgreSQL có thể sort **từng nhóm tenant** theo amount.

```text
Input có prefix tenant_id đã có thứ tự

tenant 1: [amount chưa sắp]
tenant 2: [amount chưa sắp]
tenant 3: [amount chưa sắp]
             │
             ▼
Incremental Sort
  ├─ sort nhóm tenant 1
  ├─ sort nhóm tenant 2
  └─ sort nhóm tenant 3
             │
             ▼
Toàn bộ kết quả ORDER BY tenant_id, amount DESC
```

Trong plan, có thể thấy:

```text
Incremental Sort
  Sort Key: tenant_id, amount DESC
  Presorted Key: tenant_id
```

### Khi nào có lợi?

- Nhiều nhóm vừa phải thay vì một sort cực lớn.
- Input có prefix order đáng tin.
- Có `LIMIT` và có thể trả kết quả sớm hơn.
- Tránh một số lần tạo temporary runs lớn.

Nhưng nó không luôn tốt: nếu các nhóm quá lớn, skew hoặc ước lượng số nhóm sai, incremental sort vẫn có thể spill hoặc tốn nhiều thời gian.

## 19. Thử Incremental Sort trong lab

Tạo index prefix:

```sql
CREATE INDEX ix_sales_tenant_only
ON lesson_spill.sales (tenant_id);

ANALYZE lesson_spill.sales;
```

Thử:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, amount, sale_id
FROM lesson_spill.sales
ORDER BY tenant_id, amount DESC;
```

PostgreSQL **có thể chọn** Incremental Sort, full Sort hoặc plan khác tùy chi phí/phiên bản; không cam kết chắc chắn vì chỉ tạo index prefix.

Để quan sát một phương án trong lab:

```sql
BEGIN;

SET LOCAL enable_incremental_sort = on;
SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT tenant_id, amount, sale_id
FROM lesson_spill.sales
ORDER BY tenant_id, amount DESC;

ROLLBACK;
```

`enable_seqscan=off` chỉ là công cụ thử plan alternatives, không đảm bảo planner phải chọn đúng Incremental Sort và không nên duy trì tùy tiện trong production.

## 20. Hash Join sử dụng bộ nhớ thế nào?

Hash Join thường có hai nhánh:

1. Một nhánh được đưa vào **Hash** để dựng hash table.
2. Nhánh kia (**probe side**) quét dữ liệu và tìm các hash matches.

```text
                  Hash Join
                 /         \
          Probe input      Hash
                             |
                         Build input
```

Ví dụ:

```sql
SELECT
    s.sale_id,
    p.product_name,
    s.amount
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.status = 'PAID';
```

Planner có thể chọn Hash Join, Merge Join hoặc Nested Loop dựa trên statistics và cost.

### Hash table phải giữ gì?

Không nhất thiết toàn bộ cột của bảng nguồn. Executor cần những trường phục vụ hash key, join conditions và output ở các node tương ứng. **Projection** và pruning cột có thể giúp giảm width dữ liệu cần lưu.

### Khi thiếu bộ nhớ?

Hash Join có thể chia thành nhiều **batches**; những nhóm không xử lý ngay được ghi ra temporary files rồi đọc lại.

## 21. Buckets và Batches trong Hash Join

Một plan minh họa:

```text
Hash Join  (actual rows=... loops=1)
  Hash Cond: (s.product_id = p.product_id)
  Buffers: shared hit=..., temp read=... written=...
  -> Seq Scan on sales s
  -> Hash
       Buckets: 2048  Batches: 64  Memory Usage: 150kB
       Buffers: shared hit=..., temp written=...
       -> Seq Scan on products p
```

**`Buckets`:** số buckets được tổ chức cho hash table trong kế hoạch thực thi.

**`Batches`:** số nhóm/lượt phân vùng dữ liệu để xử lý khi hash table không thể xử lý toàn bộ tập cần thiết trong bộ nhớ được cấp.

**`Memory Usage`:** dung lượng nhớ được node Hash báo cáo theo cách instrumentation.

### Batches > 1 là dấu hiệu rất đáng xem

Khi plan báo `Batches: 64`, hash operation thường đang dùng cơ chế chia lô và có thể sinh temporary I/O.

**Không tự kết luận mọi `Batches > 1` là sự cố nghiêm trọng.** Cần xem temp reads/writes, runtime, độ lớn dữ liệu và tài nguyên hệ thống.

### Batches không phải số workers

`Batches=64` không có nghĩa có 64 parallel workers hoặc PostgreSQL tạo 64 threads. Đây là khái niệm partitioning/batching trong hash algorithm.

## 22. Tái hiện Hash Join spill

Dùng dữ liệu sales/products lab:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';
SET LOCAL hash_mem_multiplier = 1.0;
SET LOCAL enable_mergejoin = off;
SET LOCAL enable_nestloop = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    s.sale_id,
    p.product_name,
    p.description,
    s.amount
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.status = 'PAID';

ROLLBACK;
```

Mục tiêu là **quan sát một Hash Join dưới ngân sách nhỏ**. Vẫn phải xem plan: các công tắc `enable_*` chỉ tác động cost/preference và PostgreSQL có thể còn lựa chọn khác theo ngữ nghĩa query và phiên bản.

### Những dấu hiệu cần ghi

- `Hash Join` có xuất hiện không?
- Có `Hash` node và `Buckets/Batches/Memory Usage` không?
- `Batches` lớn hơn 1?
- `Buffers: temp read/written` nằm ở node nào?
- Tổng `Execution Time` là bao nhiêu?
- Row counts ước lượng có sát actual không?
- Cột `description` dài có góp phần vào row width cần xử lý không?

Đừng cố tối ưu trước khi đã xác định chính xác **node nào tạo spill**.

## 23. So sánh Hash Join khi hash memory lớn hơn

Lặp lại với:

```sql
BEGIN;

SET LOCAL work_mem = '32MB';
SET LOCAL hash_mem_multiplier = 2.0;
SET LOCAL enable_mergejoin = off;
SET LOCAL enable_nestloop = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    s.sale_id,
    p.product_name,
    p.description,
    s.amount
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.status = 'PAID';

ROLLBACK;
```

Kết quả kỳ vọng trong một số môi trường:

- `Batches` giảm, có thể về 1.
- Temp blocks giảm.
- Execution Time cải thiện nếu hash spill là bottleneck.

Tuy nhiên:

- Plan có thể khác vì các GUC được thay đổi.
- Cache giữa hai lần chạy khác nhau.
- I/O không luôn là nút thắt.
- Một hash table nhỏ hơn mức ngân sách không tự chiếm toàn bộ 64 MB.

### Chọn tăng work_mem hay multiplier?

Nếu **sort** tràn: `work_mem` là tham số quan trọng hơn.

Nếu **hash** tràn: xem `work_mem` và `hash_mem_multiplier` cùng nhau.

Nếu **tất cả cùng tràn** hoặc workload có nhiều nodes: cần đo tổng RAM và cân nhắc sửa SQL/index/cardinality trước khi tăng global settings.

## 24. Hash Join: build side có vai trò gì?

Trong Hash Join, một đầu vào được dùng để dựng hash table. **Kích thước build side** thường ảnh hưởng mạnh tới khả năng vừa bộ nhớ.

Ví dụ join:

```sql
SELECT
    s.sale_id,
    p.product_name
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id;
```

Nếu PostgreSQL xây hash table từ products, số rows và độ rộng tuple cần lưu của products quan trọng.

### Không ép build side bằng thứ tự viết JOIN

Viết:

```sql
FROM sales s JOIN products p
```

không đảm bảo PostgreSQL phải xây hash table từ products trong mọi trường hợp. Planner có thể đảo vị trí các input hoặc chọn thuật toán khác.

### Cách giảm áp lực

- Lọc build side sớm nếu hợp lệ.
- Chỉ chọn những cột cần thiết; tránh đưa payload rộng qua hash unnecessarily.
- Cải thiện estimates để planner biết input nào nhỏ/lớn.
- Xem liệu index/nested loop/merge join có tốt hơn với selectivity thực tế.
- Dùng staging/pre-aggregation khi phù hợp ngữ nghĩa.

## 25. “Đưa SELECT * vào join” có thể làm spill tệ hơn

Ví dụ:

```sql
SELECT *
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id;
```

Kết quả mang `note` dài từ sales và `description` dài từ products, khiến row width và dữ liệu di chuyển qua pipeline lớn hơn truy vấn chỉ cần `sale_id`, `product_name`.

Hãy so sánh:

```sql
SELECT
    s.sale_id,
    p.product_name
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id;
```

### Không phải mọi projection đều làm hash table nhỏ lại

Planner có **column pruning/projection**; dù truy vấn ngoài chọn nhiều cột, không phải toàn bộ cột đều được giữ trong mọi node. Ngược lại, nếu một cột rộng thực sự cần đưa qua operator, nó có thể làm tăng memory/temp I/O.

Để chứng minh hiệu quả, xem `Plan Width`, actual memory, temp blocks và thời gian sau thay đổi. Đừng giả định `SELECT *` là nguyên nhân duy nhất khi dữ liệu còn bị trùng nhiều do JOIN cardinality.

## 26. HashAggregate là gì?

Với:

```sql
SELECT
    customer_id,
    COUNT(*) AS sale_count,
    SUM(amount) AS total_amount
FROM lesson_spill.sales
GROUP BY customer_id;
```

PostgreSQL có thể dùng **HashAggregate**:

```text
HashAggregate
  Group Key: customer_id
  -> Seq Scan on sales
```

Executor giữ một **aggregate state** cho các nhóm, thường được tra cứu theo hash key.

### Điều gì quyết định memory?

Không chỉ số rows đầu vào, mà còn:

- Số nhóm distinct.
- Kiểu/độ rộng group key.
- Số lượng aggregate states và kích thước state.
- Aggregate functions, đặc biệt những aggregate giữ state lớn.
- Data skew và số lượng bản ghi mỗi nhóm.
- Planner estimates và hash memory budget.

Nếu chỉ có 10 nhóm, HashAggregate có thể rất nhỏ dù đầu vào hàng triệu rows. Nếu gần như mỗi row là một nhóm, aggregate state có thể lớn.

## 27. HashAggregate và Batches/Disk Usage

Khi HashAggregate không thể giữ toàn bộ state theo ngân sách, PostgreSQL hiện đại có cơ chế xử lý spilling/batching trong những tình huống được hỗ trợ.

Một output minh họa:

```text
HashAggregate
  Group Key: (sale_id % 40000)
  Batches: 17
  Memory Usage: 321kB
  Disk Usage: 11520kB
  Buffers: shared hit=..., temp read=... written=...
```

### Ba thông tin cần đọc cùng nhau

1. **`Batches`:** số nhóm xử lý hash theo cơ chế batching.
2. **`Disk Usage`:** dung lượng làm việc trên disk được báo trong execution plan.
3. **`temp read/written`:** hoạt động temporary file I/O.

**Không dùng `Disk Usage` như dung lượng database tăng bền vững.** Đây là working space tạm phục vụ thực thi.

## 28. Tái hiện HashAggregate spill

Trên dữ liệu lab 90.000 rows:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';
SET LOCAL hash_mem_multiplier = 1.0;
SET LOCAL enable_sort = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    sale_id % 40000 AS group_key,
    COUNT(*) AS sale_count,
    SUM(amount) AS total_amount
FROM lesson_spill.sales
GROUP BY sale_id % 40000;

ROLLBACK;
```

Ở đây có nhiều group keys. `enable_sort=off` chỉ giúp khảo sát một plan thiên về hash; nó không buộc PostgreSQL dùng HashAggregate trong mọi phiên bản/ngữ nghĩa.

### Nếu không thấy HashAggregate?

PostgreSQL có thể chọn `GroupAggregate` với Sort hoặc một phương án khác. Đây không phải lỗi thí nghiệm. Hãy ghi nhận plan thật, sau đó cân nhắc:

- Kiểm tra `enable_hashagg` có bật không.
- Kiểm tra lựa chọn HashAggregate có phù hợp và được hỗ trợ không.
- Thử `SET LOCAL enable_hashagg = on` trong lab.
- Xem query/group cardinality và khả năng planner chọn plan thay thế.

**Không đổi cấu hình toàn server chỉ để “ép” ví dụ xuất hiện đúng node.**

## 29. HashAggregate so với GroupAggregate

Hai phương án phổ biến:

**HashAggregate:**

```text
Seq Scan
  → HashAggregate theo group keys
```

**GroupAggregate:**

```text
Seq Scan
  → Sort theo group keys
  → GroupAggregate
```

### So sánh

| Tiêu chí | HashAggregate | GroupAggregate |
|---|---|---|
| Cần dữ liệu đầu vào đã sort? | Không nhất thiết. | Thường cần dữ liệu theo thứ tự nhóm; Sort hoặc index có thể cung cấp. |
| Cấu trúc memory | Hash table của aggregate states. | Aggregate state theo nhóm đang xử lý; có thể cần sort trước. |
| Nguy cơ spill | Hash batching/spill. | Sort spill nếu đầu vào chưa có thứ tự phù hợp. |
| Phù hợp | Nhiều trường hợp GROUP BY không có thứ tự. | Khi input đã sắp theo group keys hoặc plan sort rẻ. |
| Kết quả có thứ tự? | Không được coi là ORDER BY bảo đảm. | Dù plan hiện trả theo group key, SQL vẫn cần ORDER BY nếu nghiệp vụ yêu cầu. |

### Bẫy khi tối ưu

Bạn thấy HashAggregate spill rồi ép GroupAggregate. Nhưng GroupAggregate phải Sort vài triệu rows và **sort lại spill còn nặng hơn**.

Do đó cần so sánh **cả plan**, không chỉ thay thuật toán để làm một loại spill biến mất.

## 30. Số nhóm (*group cardinality*) là yếu tố quan trọng

So sánh:

```sql
-- 10 tenant: ít nhóm.
SELECT tenant_id, COUNT(*)
FROM lesson_spill.sales
GROUP BY tenant_id;
```

với:

```sql
-- Nhiều nhóm khác nhau.
SELECT sale_id % 40000, COUNT(*)
FROM lesson_spill.sales
GROUP BY sale_id % 40000;
```

Cả hai đều quét 90.000 rows, nhưng số group states khác rất nhiều.

### Không suy luận memory từ số rows scan

Một triệu rows gom vào 5 nhóm có thể cần rất ít hash aggregate memory. Mười nghìn rows với mười nghìn nhóm và aggregate state lớn có thể cần nhiều memory hơn.

### Kiểm tra estimates

`EXPLAIN` báo `Plan Rows` tại Aggregate và `Actual Rows` khi ANALYZE. Nếu estimated groups thấp hơn thực tế nhiều lần, planner có thể đánh giá quá lạc quan về memory/cost.

Đó là cơ hội cải thiện statistics hoặc viết lại query, không nhất thiết là vấn đề cấu hình RAM.

## 31. Khi Hash Join và HashAggregate cùng spill

Một query có thể gồm:

```text
HashAggregate
  └── Hash Join
        ├── Seq Scan sales
        └── Hash
             └── Seq Scan products
```

Cả **Hash Join** và **HashAggregate** có thể tiêu thụ bộ nhớ đáng kể; một số plan có thêm Sort phía trên cho `ORDER BY`.

### Vì sao tăng work_mem khó dự đoán?

Một thay đổi có thể:

- Giảm số batch ở Hash Join.
- Giảm batch ở HashAggregate.
- Làm planner thay đổi chiến lược join/aggregate.
- Tăng memory peak của mỗi backend.
- Tăng áp lực RAM trên hệ thống có nhiều query tương tự.

**Đừng chỉ tối ưu một node rồi bỏ qua plan tổng và concurrency.**

## 32. Bật JSON để tìm node bị spill

Trên một query read-only:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT JSON
)
SELECT
    s.customer_id,
    COUNT(*),
    SUM(s.amount)
FROM lesson_spill.sales AS s
GROUP BY s.customer_id;
```

JSON root thường là một **mảng** có object chứa `Plan`. Các node con nằm trong `Plans`.

Một JSON fragment minh họa:

```json
[
  {
    "Plan": {
      "Node Type": "Sort",
      "Sort Method": "external merge",
      "Sort Space Used": 4500,
      "Sort Space Type": "Disk",
      "Temp Read Blocks": 900,
      "Temp Written Blocks": 1200,
      "Plans": [
        {
          "Node Type": "Seq Scan",
          "Relation Name": "sales"
        }
      ]
    },
    "Execution Time": 120.5
  }
]
```

**Ví dụ chỉ minh họa shape**, không phải output được đo từ query GROUP BY trên. Các trường và node thực tế phụ thuộc planner và phiên bản.

### Các keys thường cần

- `Node Type`.
- `Plans`.
- `Sort Method`, `Sort Space Used`, `Sort Space Type`.
- `Temp Read Blocks`, `Temp Written Blocks`.
- `Actual Rows`, `Actual Loops`.
- `Plan Rows` và `Plan Width`.
- Các trường memory/batch của Hash/HashAggregate nếu có.

Parser cần chấp nhận trường vắng mặt vì **không phải mọi node đều là Sort/Hash và không phải mọi metrics đều được báo ở mọi plan**.

## 33. Không cộng temp blocks của tất cả nodes

Ví dụ JSON plan:

```text
HashAggregate (Temp Written Blocks = 500)
  └── Sort (Temp Written Blocks = 500)
```

Không thể kết luận total = 1000 chỉ vì thấy cả hai số. Một plan node có thể báo counters gồm những hoạt động thuộc descendants, nên sẽ **đếm trùng** nếu cộng mọi node.

### Phương pháp

1. Đọc tổng temp activity ở root hoặc phạm vi tổng hợp được báo.
2. Duyệt cây để tìm operator có `Sort Space Type='Disk'` hoặc Hash batches/disk usage.
3. Xem temp counters **cục bộ theo quan hệ cha/con**, không cộng tùy tiện.
4. Đối chiếu với `Actual Rows` và `Loops`.
5. Khi cần định lượng chính xác từng operator, hiểu giới hạn instrumentation của version.

### Loops cũng quan trọng

Một Sort node có thể được gọi nhiều lần trong Nested Loop. Mỗi lần sort riêng có thể nhỏ nhưng tổng temp I/O lớn.

`actual rows=100 loops=1000` cần đọc khác với `rows=100 loops=1`. Cùng một node type, số lần thực thi có thể thay đổi hoàn toàn tổng chi phí.

## 34. Đừng nhầm số bytes temp với Disk Usage

`Disk Usage: 20MB` là thông tin footprint/working space theo một node và thời điểm instrumentation.

`temp written=10000 blocks` là hoạt động ghi các blocks trong phạm vi được báo; nếu block 8 KiB, 10000 block writes tương đương khoảng 78 MiB block transfers.

Hai phép đo **khác nhau**:

- **Working-space size**: dung lượng file/space được dùng.
- **I/O volume**: bao nhiêu block operations được phát sinh.

External merge có thể đọc/ghi lại cùng vùng file nhiều lần, nên I/O volume có thể lớn hơn peak disk footprint.

### Đừng coi pg_size_pretty của temp bytes là dung lượng đĩa còn chiếm

Temp files thường được PostgreSQL dọn khi không còn cần. Thống kê temp bytes tích lũy qua thời gian không có nghĩa file hiện tại vẫn đang chiếm tất cả dung lượng ấy.

## 35. Quan sát temp files qua log_temp_files

`log_temp_files` là GUC để log thông tin các temporary files được tạo trong quá trình xử lý, theo ngưỡng kích thước.

Kiểm tra:

```sql
SHOW log_temp_files;

SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name = 'log_temp_files';
```

Giá trị thường được hiểu:

| Giá trị | Ý nghĩa |
|---|---|
| `-1` | Tắt log temp files (giá trị mặc định thường gặp). |
| `0` | Log mọi temporary file phù hợp. |
| Số dương | Log temporary files đạt/vượt ngưỡng kích thước tính theo đơn vị cấu hình, thường là kB. |

Ví dụ log minh họa:

```text
LOG: temporary file: path "base/pgsql_tmp/pgsql_tmp123.0",
     size 18874368
```

### Vì sao log khác EXPLAIN?

- `EXPLAIN` cho **node-level plan** và temp counters của một statement được instrument.
- `log_temp_files` báo **files** đủ điều kiện trên server, giúp tìm query spill khi không chủ động EXPLAIN.
- Logs có thể ghi khi file được xóa/đóng, không nhất thiết đúng thời điểm temp file vừa được tạo.
- Một query có thể tạo nhiều files; một file không tương đương một Sort node.

### Quyền cấu hình

Không phải mọi role có thể thay đổi `log_temp_files` tùy ý; setting và quyền quản trị phụ thuộc cấu hình/phiên bản. Không bật log mọi file trên production mà chưa tính log volume, dữ liệu trong log và chi phí hoạt động.

## 36. Liên kết temp log với câu SQL

Một log file temp có thể hữu ích hơn khi `log_line_prefix` chứa:

- PID.
- Timestamp.
- Database/user.
- `application_name`.
- Transaction/session identifier nếu cấu hình cho phép.

Từ đó bạn có thể đối chiếu với SQL logs, tracing hoặc metrics.

### Application name không phải bằng chứng định danh an toàn

Client có thể tự đặt `application_name`; đây là nhãn chẩn đoán, không phải cơ chế xác thực. Không dùng nó thay user/role permissions.

### Không cố giữ PID cũ để quan sát

PID có thể được tái sử dụng khi backend kết thúc. Nếu đang chẩn đoán hiện tại, đối chiếu `backend_start` và thông tin session, không chỉ PID từ một log tuần trước.

## 37. Quan sát pg_stat_database.temp_files và temp_bytes

PostgreSQL có thống kê cumulative theo database:

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    pg_size_pretty(temp_bytes) AS temp_bytes_pretty,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

Ý nghĩa:

- `temp_files`: số temporary files được tạo theo phạm vi thống kê của database.
- `temp_bytes`: tổng bytes ghi vào temporary files theo cơ chế thống kê.
- `stats_reset`: thời điểm những thống kê này được reset.

Các counters có tính **tích lũy**, không phải chỉ của query vừa chạy. Trong môi trường có nhiều session đồng thời, thay đổi số liệu sau một lần đo có thể bao gồm công việc của người khác.

### Không suy ra temp_bytes là peak disk usage

Nếu `temp_bytes=200GB` tích lũy qua nhiều ngày, không có nghĩa đang tồn tại 200 GB temp files trên disk ngay lúc SELECT.

### Đo chênh lệch có kiểm soát

Trong lab gần như không có workload khác:

1. Ghi `temp_files`/`temp_bytes` trước.
2. Chạy một truy vấn spill.
3. Ghi lại sau khi truy vấn kết thúc.
4. So sánh hiệu.

Ngay cả vậy, thống kê có thể được cập nhật/quan sát theo cơ chế caching và thời điểm flush; nếu trong cùng transaction dài, snapshot thống kê có thể không đổi như mong đợi. Đo bằng những transaction giám sát ngắn.

## 38. pg_stat_statements để tìm query gây temp I/O nhiều

Nếu extension `pg_stat_statements` được cài và cấu hình, có thể phân tích theo query fingerprint:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    temp_blks_read,
    temp_blks_written,
    LEFT(query, 160) AS query_excerpt
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
```

**Điều kiện:** View `pg_stat_statements` chỉ tồn tại khi extension được cài đặt ở database thích hợp và module được nạp/cấu hình theo yêu cầu version. Nếu không có, câu query sẽ lỗi; không có nghĩa PostgreSQL không tạo temp files.

### Lợi ích

Nó trả lời “**SQL pattern nào** tạo nhiều temporary block I/O qua các lần thực thi?”, thay vì chỉ xem một EXPLAIN thủ công.

### Những hạn chế

- Là thống kê **tổng hợp**, không cho toàn bộ cây plan.
- Một query fingerprint có thể có nhiều lần gọi và input sizes khác nhau.
- Mean không phản ánh tail latency; cần xem tổng và phân bố nếu có thêm telemetry.
- Temp read/write không đồng nghĩa nguyên nhân chắc chắn là Sort (có thể Hash/Materialize/khác).
- Dữ liệu thống kê có giới hạn và có thể reset.

Để điều tra node cụ thể, hãy lấy `EXPLAIN ANALYZE BUFFERS` trong môi trường phù hợp.

## 39. Các GUC liên quan tới temporary files

| GUC | Vai trò | Lưu ý |
|---|---|---|
| `work_mem` | Ngân sách executor operations. | Nhiều operators/connections nhân hiệu ứng bộ nhớ. |
| `hash_mem_multiplier` | Hệ số nhân cho hash operations. | Không trực tiếp tăng bộ nhớ sort. |
| `temp_file_limit` | Giới hạn tổng dung lượng temporary files mà một process được dùng ở một thời điểm. | Khác với tổng ngân sách RAM, không bao gồm mọi loại temporary objects. |
| `temp_tablespaces` | Chọn tablespace cho temporary objects/files theo quy tắc PostgreSQL. | Có tác động storage, quyền và capacity. |
| `log_temp_files` | Ghi log temp files theo kích thước ngưỡng. | Tăng log volume khi bật chi tiết. |
| `track_io_timing` | Đo thời gian I/O khi cấu hình hỗ trợ. | Có overhead đo lường. |
| `statement_timeout` | Giới hạn thời gian statement. | Không giải quyết nguyên nhân spill. |

### temp_file_limit

Kiểm tra:

```sql
SHOW temp_file_limit;
```

Giá trị `-1` thường có nghĩa **không đặt giới hạn** theo cấu hình. `temp_file_limit` có thể giúp tránh một query làm đầy disk vì working files, nhưng khi vượt giới hạn câu lệnh sẽ **bị lỗi**, không tự tối ưu sang một thuật toán nhanh hơn.

### temp_tablespaces

Nếu storage khác nhau về tốc độ/dung lượng, DBA có thể cân nhắc vị trí của temporary files/objects. Tuy nhiên chuyển temp files sang một ổ nhanh không giải quyết nguyên nhân query xử lý dữ liệu trung gian quá lớn, và có thể tạo bottleneck khác.

## 40. Không nhầm temp_file_limit với temp_buffers

`temp_file_limit` chủ yếu giới hạn không gian **temporary files** mà backend dùng theo cơ chế áp dụng, ví dụ files của sort/hash spill.

`temp_buffers` điều chỉnh vùng nhớ local buffers cho **temporary tables**.

Tương tự:

- `temp_file_limit` không phải giới hạn kích thước tất cả dữ liệu trong bảng `CREATE TEMP TABLE`.
- `temp_buffers` không phải ngân sách cho `ORDER BY` external sort.

Nếu một query `CREATE TEMP TABLE AS SELECT` rồi sort dữ liệu, nó có thể sử dụng **cả temporary relation storage và working files** cho operator. Cần phân biệt khi đo tài nguyên.

## 41. Khi temp disk đầy

Một query spill lớn có thể bị lỗi vì:

- Filesystem/tablespace chứa temporary files hết chỗ.
- `temp_file_limit` bị vượt.
- Quyền/temp storage gặp sự cố.
- Có hàng loạt session cùng ghi temp files.

Kết quả có thể là statement thất bại, transaction tường minh chuyển sang trạng thái lỗi.

### Quy trình xử lý

1. Xác định SQL/các backend tạo temp nhiều.
2. Xem log, `pg_stat_database`, `pg_stat_statements` và plan.
3. Kiểm tra dung lượng/tablespace/OS metrics.
4. Phân biệt một query khổng lồ với rất nhiều query vừa spill.
5. Thực hiện rollback/cleanup transaction lỗi phù hợp.
6. Giảm lượng dữ liệu trung gian hoặc memory pressure.
7. Điều chỉnh temp storage/capacity/limit theo SLA.

**Không xóa thủ công những file đang được PostgreSQL quản lý trong thư mục temp** để “giải phóng nhanh” khi server đang chạy; thao tác có thể phá vỡ truy vấn hoặc trạng thái hệ thống.

## 42. Tại sao tăng work_mem không phải bước đầu tiên?

Giả sử query:

```sql
SELECT
    s.sale_id,
    p.description
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
ORDER BY p.description, s.sale_id;
```

Query có thể cần sort toàn bộ kết quả rộng. Nếu sản phẩm tăng từ 90.000 lên 90 triệu rows, “chỉ tăng work_mem” có thể trở nên không khả thi.

Đặt câu hỏi:

- Người dùng có thực sự muốn **mọi hàng** hay chỉ trang đầu?
- Có thể lọc tenant/time range trước không?
- Có thể chỉ chọn ID/khóa sort rồi lấy payload sau không?
- Có index cung cấp thứ tự chính xác không?
- Có thể tính toán/aggregate trước khi join payload lớn không?
- Có cần sort trên expression không?
- Kết quả được trình bày theo API pagination nào?

**Giảm công việc bắt buộc** thường có lợi hơn chỉ cấp thêm RAM cho công việc không cần thiết.

## 43. Lọc dữ liệu trước sort

Ví dụ không có điều kiện:

```sql
SELECT sale_id, sold_at, note
FROM lesson_spill.sales
ORDER BY sold_at DESC;
```

Phải xử lý tập nhiều hàng.

Nếu nghiệp vụ chỉ cần tenant 3 trong khoảng thời gian:

```sql
SELECT sale_id, sold_at, note
FROM lesson_spill.sales
WHERE tenant_id = 3
  AND sold_at >= TIMESTAMPTZ '2026-01-15 00:00:00+00'
  AND sold_at < TIMESTAMPTZ '2026-02-01 00:00:00+00'
ORDER BY sold_at DESC
LIMIT 100;
```

Số rows và cột cần giữ có thể giảm mạnh. Index `(tenant_id,sold_at DESC,sale_id DESC)` còn có khả năng cung cấp thứ tự.

### Điều kiện phải đúng nghiệp vụ

Không thêm `WHERE tenant_id=3` chỉ để plan đẹp nếu báo cáo cần tất cả tenants. Tối ưu là tìm cách thực hiện **đúng câu hỏi nghiệp vụ** với chi phí thấp, không phải âm thầm thay kết quả.

### Tránh filter bằng hàm không cần thiết trên cột

```sql
WHERE date(sold_at) = DATE '2026-01-15'
```

có thể khác với filter theo range trên `sold_at` về khả năng dùng index và timezone semantics. Với dữ liệu timestamp, dùng khoảng half-open thích hợp sau khi xác định timezone ứng dụng.

## 44. Tránh sort payload rộng: narrow-first pattern

Khi cần trả một tập rất nhỏ sau sắp xếp, có thể cân nhắc **chọn khóa/ID trước, lấy payload sau**.

Ví dụ phải sort theo expression không có index nhưng chỉ lấy 50 hàng:

```sql
WITH top_sale_ids AS MATERIALIZED (
    SELECT
        sale_id,
        md5(sale_id::text) AS sort_key
    FROM lesson_spill.sales
    WHERE tenant_id = 3
    ORDER BY md5(sale_id::text), sale_id
    LIMIT 50
)
SELECT
    s.sale_id,
    s.note,
    s.amount
FROM top_sale_ids AS top_ids
JOIN lesson_spill.sales AS s
  ON s.sale_id = top_ids.sale_id
ORDER BY top_ids.sort_key, s.sale_id;
```

Ý tưởng:

1. Truy vấn con chỉ cần `sale_id` + khóa sort.
2. Sort chỉ mang cột hẹp, có `LIMIT`.
3. Sau khi xác định 50 IDs, mới lấy `note` rộng.

### Khi nào không có lợi?

- Thêm 50 index lookups có thể tốn hơn việc sort rows vốn đã hẹp.
- `MATERIALIZED` tạo một ranh giới tối ưu hóa/tuplestore, có thể ảnh hưởng planner.
- Nếu query cần toàn bộ rows, pattern không giảm được lượng output.
- Nếu sort key không ổn định, phải giữ nguyên phép tính/ordering để tránh thay kết quả.

Đo `EXPLAIN ANALYZE BUFFERS` trước/sau; đừng áp dụng vì nghĩ mọi CTE đều nhanh hơn.

## 45. OFFSET lớn và chi phí sort/phân trang

Ví dụ:

```sql
SELECT
    sale_id,
    sold_at
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20 OFFSET 30000;
```

Dù chỉ trả 20 hàng, PostgreSQL vẫn cần **bỏ qua 30.000 hàng đầu theo thứ tự** để tới trang yêu cầu. Nếu không có index, sort/scan có thể phải xử lý lượng dữ liệu lớn.

### Keyset pagination

Nếu client đã biết cursor của trang trước:

```sql
SELECT
    sale_id,
    sold_at
FROM lesson_spill.sales
WHERE tenant_id = 3
  AND (sold_at, sale_id) <
      (
        TIMESTAMPTZ '2026-02-01 10:00:00+00',
        45000
      )
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Điều kiện tuple comparison tương ứng với chiều sort giảm dần của cả hai cột trong ví dụ, và index phù hợp có thể tìm vị trí tiếp theo mà không bỏ qua hàng chục nghìn rows.

### Lưu ý về semantics

- Cursor phải lấy từ hàng cuối cùng của trang trước.
- Thứ tự cần xác định đầy đủ, nên có tie-breaker duy nhất.
- Cần xử lý thay đổi dữ liệu đồng thời theo yêu cầu consistency của ứng dụng.
- Với sort key có NULL hoặc chiều ASC/DESC hỗn hợp, điều kiện cursor có thể phức tạp hơn.

Keyset pagination giải quyết **workload lấy trang**, không thay thế một báo cáo thật sự cần sắp xếp toàn bộ dataset.

## 46. GROUP BY ít cột hơn

Một báo cáo:

```sql
SELECT
    tenant_id,
    customer_id,
    COUNT(*)
FROM lesson_spill.sales
GROUP BY tenant_id, customer_id;
```

có thể tạo ít hơn hoặc nhiều hơn groups so với:

```sql
SELECT
    tenant_id,
    customer_id,
    sold_at,
    COUNT(*)
FROM lesson_spill.sales
GROUP BY tenant_id, customer_id, sold_at;
```

Thêm một cột timestamp phân biệt hầu như từng transaction có thể làm số groups tăng mạnh, khiến hash aggregate memory tăng.

### Không bỏ cột chỉ để giảm groups nếu làm sai số liệu

`GROUP BY tenant_id,customer_id` trả một kết quả nghiệp vụ **khác** `GROUP BY tenant_id,customer_id,sold_at`. Bạn chỉ có thể bỏ cột nếu báo cáo thật sự không cần phân biệt theo timestamp.

### Đánh giá “độ hạt” dữ liệu

Trước khi tối ưu, xác định:

- Một row đầu ra đại diện cho một sale, customer, product, ngày hay tenant?
- Cột nào xác định duy nhất một nhóm?
- Có join nào làm nhân bản hàng trước khi GROUP BY?
- Có cần aggregate trên toàn bộ dữ liệu chi tiết không?

Chọn đúng **grain** thường giảm các nhóm trung gian không cần thiết.

## 47. Aggregate trước JOIN khi ngữ nghĩa cho phép

Giả sử cần tổng doanh thu theo product kèm tên sản phẩm.

Một cách:

```sql
SELECT
    p.product_id,
    p.product_name,
    SUM(s.amount) AS revenue
FROM lesson_spill.products AS p
JOIN lesson_spill.sales AS s
  ON s.product_id = p.product_id
GROUP BY p.product_id, p.product_name;
```

Một cách khác tính tổng trước:

```sql
WITH revenue_by_product AS (
    SELECT
        product_id,
        SUM(amount) AS revenue
    FROM lesson_spill.sales
    GROUP BY product_id
)
SELECT
    p.product_id,
    p.product_name,
    r.revenue
FROM revenue_by_product AS r
JOIN lesson_spill.products AS p
  ON p.product_id = r.product_id;
```

Ý tưởng: từ rất nhiều sales rows, **gộp thành một hàng/product** trước khi join sang bảng dimension.

### Khi nào có thể giảm spill?

Nếu join tạo hàng rất rộng hoặc làm tăng lượng dữ liệu đi qua aggregate/sort, pre-aggregation có thể giảm intermediate rows/width.

### Khi nào không áp dụng được?

- Nếu aggregation phụ thuộc filter/columns ở bảng dimension và không thể pushdown một cách tương đương.
- Nếu join không phải 1:1 theo product, ví dụ product có nhiều rows trong dimension, pre-aggregation có thể làm sai tổng.
- Nếu SQL optimizer đã tự đưa ra phương án tốt.
- Nếu pre-aggregation tạo một HashAggregate lớn cũng bị spill.

**Chỉ rewrite khi hai SQL tương đương về kết quả** và xác nhận bằng test dữ liệu/thực thi theo quy trình dự án (Content QA thuộc giai đoạn riêng của workflow).

## 48. EXISTS thay JOIN khi chỉ kiểm tra tồn tại

Nếu mục tiêu là “lấy sales có product trong danh sách hợp lệ”, cần tránh một JOIN làm nhân bản hàng vì phía product/dimension không unique theo điều kiện.

Mẫu semi-join:

```sql
SELECT
    s.sale_id,
    s.amount
FROM lesson_spill.sales AS s
WHERE EXISTS (
    SELECT 1
    FROM lesson_spill.products AS p
    WHERE p.product_id = s.product_id
      AND p.category_id = 42
);
```

`EXISTS` diễn đạt đúng mục tiêu “có ít nhất một bản ghi phù hợp”. PostgreSQL có thể lập kế hoạch thành semi-join.

### Vì sao có thể giúp?

Một JOIN thông thường có thể trả nhiều rows nếu phía phải có multiple matches. `EXISTS` chỉ quan tâm tồn tại, tránh nhân cardinality không cần thiết.

### Trường hợp lab

`products.product_id` là primary key nên JOIN theo product_id vốn không nhân rows. Ví dụ này minh họa semantics; lợi ích lớn hơn khi điều kiện JOIN không bảo đảm 1:1.

**Không thay JOIN bằng EXISTS nếu bạn cần cột phía phải hoặc cần số lượng matches.**

## 49. Chọn thuật toán JOIN khác khi Hash Join spill

Nếu Hash Join bị spill nặng, PostgreSQL có thể có phương án:

- **Nested Loop** với index lookup phù hợp khi outer nhỏ.
- **Merge Join** khi hai input đã có thứ tự theo join key hoặc sort hợp lý.
- **Hash Join** với cấu hình/đầu vào cải thiện.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    s.sale_id,
    p.product_name
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.tenant_id = 3
  AND s.sale_id BETWEEN 1000 AND 1100;
```

Khi chỉ có một số ít sales rows, Nested Loop cùng index `products_pkey` có thể rất hiệu quả.

### Đừng “tắt hashjoin” để tối ưu vô điều kiện

```sql
BEGIN;
SET LOCAL enable_hashjoin = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
ROLLBACK;
```

Đoạn trên là **minh họa cách khảo sát**, chưa phải SQL chạy được vì `SELECT ...` là placeholder. `enable_hashjoin=off` giúp thử alternative plan, nhưng nếu query thật có hàng triệu probes, Nested Loop có thể tệ hơn Hash Join đã spill.

Chỉ chọn kế hoạch sau khi **đo tổng execution time và I/O**, không chỉ thấy temp bytes giảm.

## 50. Merge Join cũng có thể cần Sort

Một Merge Join có thể cần hai đầu vào đã được sắp theo join keys. Nếu không có index cung cấp thứ tự, PostgreSQL có thể sinh:

```text
Merge Join
  ├── Sort
  │    └── Seq Scan input A
  └── Sort
       └── Seq Scan input B
```

Nếu Sort lớn, hai nhánh này **cũng có thể spill**.

### Bài học

Chuyển Hash Join → Merge Join không đảm bảo loại bỏ temporary I/O; đôi khi bạn chỉ **đổi hash spill thành sort spill**.

Nếu hai nhánh có indexes phù hợp join keys và predicates, Merge Join có thể mạnh. Nếu không, cần so sánh chi phí sort hai nhánh với hash batching.

## 51. Statistics sai có thể gây spill như thế nào?

Planner dùng ước lượng về:

- Tổng số rows.
- Độ chọn lọc của filters.
- Số lượng distinct keys.
- Phân phối/skew và tương quan.
- Độ rộng trung bình của rows.
- Tính tương quan giữa các cột khi có statistics thích hợp.

Ví dụ:

```text
Ước lượng HashAggregate:
  500 nhóm

Thực tế:
  50.000 nhóm
```

Ngân sách hash có thể không phù hợp, dẫn đến batching/spill.

### Đọc estimated vs actual

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id % 40000 AS group_key,
    COUNT(*)
FROM lesson_spill.sales
GROUP BY sale_id % 40000;
```

So sánh `rows=...` ước lượng ở Aggregate với `actual rows=...` và số groups thật.

**Sai lệch lớn không luôn gây spill, nhưng là tín hiệu nên điều tra statistics** trước khi tăng memory.

## 52. ANALYZE và thống kê cũ

Sau khi bảng thay đổi dữ liệu đáng kể, statistics có thể không còn phản ánh phân bố hiện tại.

```sql
ANALYZE lesson_spill.sales;
ANALYZE lesson_spill.products;
```

`ANALYZE` thu thập statistics mới cho planner. Nó **không tăng `work_mem`**, không tự xóa temp files và không đảm bảo luôn chọn plan tốt nhất.

### Mục tiêu

Để planner:

- Ước lượng cardinality tốt hơn.
- Ước lượng group counts phù hợp hơn.
- Chọn join order/algorithms phù hợp hơn.
- Đánh giá chi phí Sort/Hash gần thực tế hơn.

### Không chạy ANALYZE theo thói quen sau mọi query chậm

Kiểm tra `last_analyze`, `last_autoanalyze` và khối lượng thay đổi dữ liệu trước. Trên production, ANALYZE có thể tốn tài nguyên nhất định; thực hiện theo quy trình vận hành.

## 53. Thống kê mở rộng cho cột tương quan

Ví dụ trên bảng sales, `tenant_id` và `customer_id` có thể không độc lập. Một query lọc hai cột có thể có ước lượng không tốt nếu planner coi chúng độc lập hoàn toàn trong trường hợp thông tin mặc định không đủ.

PostgreSQL hỗ trợ **extended statistics**:

```sql
CREATE STATISTICS st_sales_tenant_customer
    (dependencies, ndistinct, mcv)
ON tenant_id, customer_id
FROM lesson_spill.sales;

ANALYZE lesson_spill.sales;
```

Các loại statistics:

- **dependencies:** quan hệ phụ thuộc giữa những cột.
- **ndistinct:** số tổ hợp giá trị khác nhau.
- **mcv:** các tổ hợp giá trị xuất hiện thường xuyên.

### Khi nào hữu ích?

Khi nhiều predicate hoặc group key liên quan các cột tương quan và ước lượng mặc định sai.

### Giới hạn

Extended statistics không phải “thần dược” cho mọi join/cardinality, và không phải tất cả loại statistics được dùng ở mọi kiểu ước lượng. Đặc biệt, **khả năng áp dụng cho selectivity của join nhiều bảng có giới hạn** tùy phiên bản/ngữ nghĩa; không hứa một `CREATE STATISTICS` sẽ sửa mọi Hash Join spill.

Sau thay đổi, quan sát `EXPLAIN` và execution metrics thực tế.

## 54. Độ rộng row trong thống kê planner

`EXPLAIN` có `width=...` là ước lượng số bytes trung bình của row tại node, không phải số byte output JSON/HTTP.

Ví dụ:

```text
Hash  (cost=... rows=45000 width=220)
```

Một build-side với width lớn có thể cần nhiều memory.

### Độ rộng thực tế có thể khác

PostgreSQL có thể lưu giá trị lớn qua TOAST, expression và projection có thể biến đổi row width, và thống kê chỉ là ước lượng. Vì vậy:

- Kiểm tra cột nào thực sự đi qua hash/sort.
- Tránh `SELECT *` nếu không cần.
- Kiểm tra skew và row width của những giá trị lớn.
- Đừng áp dụng công thức `rows × width = exact work_mem`, vì còn pointer/tuple overhead/hash structures.

## 55. DISTINCT có thể dùng HashAggregate hoặc Sort

```sql
SELECT DISTINCT
    customer_id,
    status
FROM lesson_spill.sales;
```

PostgreSQL có thể thực hiện bằng:

```text
HashAggregate
```

hoặc:

```text
Sort
  → Unique
```

### Một sai lầm thường gặp

Thêm `DISTINCT` để “sửa” rows nhân đôi do JOIN sai điều kiện. Điều này có thể tạo một HashAggregate/Sort rất lớn và spill.

Cần sửa **join cardinality** ở nguồn:

- Join trên khóa đúng.
- Không join tới bảng nhiều hàng nếu chỉ cần EXISTS.
- Aggregate một phía trước khi join khi tương đương.
- Rà soát điều kiện tenant/organization để không join chéo dữ liệu.

Đừng che lỗi logic bằng `DISTINCT` rồi chỉ tăng memory để đỡ chậm.

## 56. Window functions có thể làm Sort lớn

Ví dụ:

```sql
SELECT
    tenant_id,
    customer_id,
    sale_id,
    ROW_NUMBER() OVER (
        PARTITION BY tenant_id, customer_id
        ORDER BY sold_at DESC, sale_id DESC
    ) AS row_no
FROM lesson_spill.sales;
```

WindowAgg thường cần input theo thứ tự của partition/order keys và PostgreSQL có thể sinh Sort/Incremental Sort.

Index hỗ trợ có thể là:

```sql
CREATE INDEX ix_sales_window_order
ON lesson_spill.sales (
    tenant_id,
    customer_id,
    sold_at DESC,
    sale_id DESC
);
```

### Khi nào tránh full window computation?

Nếu ứng dụng thực sự chỉ cần **một hàng mới nhất của mỗi customer**, `DISTINCT ON` với thứ tự thích hợp có thể là giải pháp. Nhưng phải so sánh:

- Semantics với ties và NULL.
- Số rows cần trả.
- Scan costs và index support.
- Khả năng window filter được tối ưu.

**Không thay window function bằng DISTINCT ON nếu nghiệp vụ cần đủ rank của mọi hàng.**

## 57. CTE MATERIALIZED và working data

`MATERIALIZED` có thể yêu cầu PostgreSQL ghi nhận kết quả CTE để tái sử dụng, tùy ngữ nghĩa và phiên bản:

```sql
WITH x AS MATERIALIZED (
    SELECT *
    FROM lesson_spill.sales
    WHERE tenant_id = 3
)
SELECT COUNT(*)
FROM x;
```

Không mặc định:

> “MATERIALIZED chắc chắn nhanh hơn vì chỉ tính một lần.”

Một CTE materialized có thể cản trở pushdown filters và khiến xử lý trung gian lớn hơn. Một tuplestore lớn có thể dùng temporary files; đây không nhất thiết là Sort/Hash spill, nhưng cùng là vấn đề data volume và memory/disk.

### Nguyên tắc

Chọn MATERIALIZED/NOT MATERIALIZED theo semantics và plan, không như một “hint tối ưu tổng quát” thiếu benchmark.

## 58. Planner settings ảnh hưởng tới spill

Một số GUC liên quan:

```sql
SELECT
    name,
    setting,
    unit,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'work_mem',
    'hash_mem_multiplier',
    'enable_hashjoin',
    'enable_hashagg',
    'enable_sort',
    'enable_incremental_sort',
    'max_parallel_workers_per_gather'
)
ORDER BY name;
```

### SETTINGS trong EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...
```

Đây là placeholder; thay `SELECT ...` bằng query lab thực.

`SETTINGS` có thể hiển thị những planner-relevant GUC khác **built-in defaults**, không phải mọi setting hiện hữu. Nếu không thấy `work_mem` ở đó, vẫn nên `SHOW work_mem` để biết giá trị đang dùng.

### So sánh hai máy

Nếu môi trường A có work_mem 4MB còn B có 64MB, chênh lệch spill có thể đến từ RAM budget. Nhưng còn có:

- Dữ liệu khác phân bố.
- Statistics khác.
- Indexes/constraints khác.
- PostgreSQL version.
- Cache/IO khác.
- Parallelism khác.

Phải cố định các yếu tố có thể so sánh trước khi quy kết nguyên nhân.

## 59. Parallel query và tổng memory

Một plan có `Gather`/`Gather Merge` và nhiều workers có thể tạo hoạt động sort/hash trên nhiều process.

```text
Gather Merge
  ├── worker 0 Sort ...
  ├── worker 1 Sort ...
  └── leader work ...
```

Mỗi worker có thể có ngân sách memory cho các thao tác phù hợp, dẫn tới **tổng RAM tăng**. Một số cơ chế shared hash table trong parallel hash join có cách quản lý riêng.

### Những lỗi suy luận

- `work_mem=16MB` không nghĩa toàn bộ parallel query dùng tối đa 16MB.
- Không nhân số lượng workers với mọi node một cách cơ học.
- `Workers Planned` không có nghĩa server đã khởi chạy đủ số workers.
- Temp counters có thể đã tổng hợp các worker activities; đừng nhân đôi.

### Khi nào điều chỉnh parallelism?

Nếu một query parallel spill nặng và cùng lúc nhiều queries cạnh tranh memory/I/O, cân nhắc mức parallel phù hợp, nhưng phải đo lại throughput toàn hệ thống. Đôi khi parallelism giảm latency của một query; đôi khi làm tăng tổng resource contention.

## 60. JIT, CPU và thời gian không tương ứng temp I/O

Một plan có temp writes đáng kể nhưng không nhất thiết thời gian chủ yếu nằm ở I/O. Ngược lại, temp=0 mà query vẫn chậm vì:

- CPU-heavy expressions.
- JIT compilation overhead.
- Row-by-row function calls.
- Lock waits.
- Dữ liệu quét nhiều và cache misses.
- Truyền kết quả lớn qua network/client.

### Công cụ bổ sung

- `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`.
- `track_io_timing` nếu được bật/cho phép.
- `pg_stat_activity.wait_event_type` và `wait_event`.
- OS/storage metrics.
- `pg_stat_statements` khi đã cấu hình.
- Application tracing.

Không coi mọi query chậm có `Sort` là chậm vì disk spill; phải xem **Sort Method** và temp counters thực.

## 61. track_io_timing và thời gian đọc/ghi temp

Kiểm tra:

```sql
SHOW track_io_timing;
```

Khi được cấu hình phù hợp, PostgreSQL có thể báo I/O timings trong EXPLAIN, gồm thời gian read/write được instrument cho các loại I/O có hỗ trợ.

Ví dụ:

```text
I/O Timings: temp read=... write=...
```

Thông tin/tên trường chính xác tùy version và instrumentation.

### Không lẫn timing với blocks

`temp read=10000 blocks` mô tả volume hoạt động; `temp read time=80ms` mô tả elapsed time I/O được đo. Hai query có cùng block count có thể có timings khác vì storage/OS cache và concurrency.

### Chi phí đo

`track_io_timing` có overhead thu thập timing. Không bật globally trên production chỉ vì cần một ví dụ mà chưa xem chính sách và tải.

## 62. So sánh warm cache và cold cache

Giả sử chạy external sort hai lần:

```text
Lần 1:
  shared read=3000
  temp read=1000 written=2000
  Execution Time=180ms

Lần 2:
  shared read=100
  shared hit=2900
  temp read=1000 written=2000
  Execution Time=140ms
```

Số liệu giả định. Nếu temp blocks gần tương tự mà shared reads giảm, có thể cache của bảng/index **ấm hơn** trong lần hai.

### Không tự coi temp files cũng được “cache” giống shared buffers

Temporary file I/O có thể được OS cache hỗ trợ, nhưng `shared_buffers` và executor temp files là các cơ chế khác. `shared hit` không bao gồm toàn bộ OS page cache của temp files.

### Lập benchmark

Đo nhiều lần, ghi môi trường/cache/IO timing, không chỉ chạy một lần trước và một lần sau rồi kết luận thay đổi work_mem cải thiện 22%.

## 63. work_mem và connection pool

Ứng dụng Java/Spring có pool 40 connections. Mỗi request chạy một báo cáo với 2 HashAggregate và 1 Sort:

```text
Nhiều HTTP requests
       │
       ▼
Pool connections (up to 40)
       │
       ▼
Mỗi query có thể dùng nhiều work_mem budgets
       │
       ▼
Tổng RAM / temp I/O tăng theo concurrency
```

### Sai lầm phổ biến

Điều chỉnh `work_mem=256MB` toàn server vì một query chạy nhanh trên laptop đơn lẻ. Khi 40 requests đồng thời, nhiều operators có thể dùng các ngân sách lớn và gây áp lực RAM rất cao.

### Cách thiết kế

- Kiểm soát số báo cáo nặng đồng thời bằng queue/rate limit.
- Dùng transaction-local setting cho đúng báo cáo khi hợp lý.
- Tối ưu SQL để giảm cardinality/width.
- Tránh giữ connection khi xử lý ứng dụng không cần database.
- Theo dõi memory, temp_files/temp_bytes và tail latency.
- Đặt timeout/limit phù hợp nhưng không dùng timeout thay cho tối ưu.

## 64. SET LOCAL work_mem trong JDBC

Mẫu Java (minh họa trong phương thức có `throws SQLException`):

```java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        try (Statement st = conn.createStatement()) {
            st.execute("SET LOCAL work_mem = '32MB'");
            st.execute("SET LOCAL hash_mem_multiplier = 2.0");
        }

        try (PreparedStatement ps = conn.prepareStatement("""
                SELECT customer_id, COUNT(*) AS sale_count
                FROM lesson_spill.sales
                WHERE tenant_id = ?
                GROUP BY customer_id
                """)) {
            ps.setInt(1, 3);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long customerId = rs.getLong("customer_id");
                    long saleCount = rs.getLong("sale_count");
                    // Xử lý kết quả, không giữ transaction lâu.
                }
            }
        }

        conn.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
}
```

Giả định đã khai báo `DataSource` và imports JDBC. Trong Spring-managed transaction, không tự gọi `setAutoCommit`/`commit` trên connection mà transaction manager đang quản lý.

### Vì sao SET LOCAL thích hợp?

`SET LOCAL` có scope transaction, nên không để một `work_mem` cao rò rỉ sang request khác sau khi transaction kết thúc trong một session/pool.

### Những rủi ro còn lại

- Transaction dài giữ connection lâu.
- Mức memory vẫn tăng theo concurrency.
- Một request có thể dùng nhiều operators và workers.
- Driver/ORM có thể chạy statement ở connection khác nếu transaction boundaries không được quản lý đúng.

**SET LOCAL giảm rủi ro rò setting, không biến work_mem cao thành vô hại.**

## 65. Spring @Transactional và SET LOCAL

Pseudo-code:

```java
@Service
public class SalesReportService {
    private final JdbcTemplate jdbcTemplate;

    public SalesReportService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(readOnly = true)
    public List<SalesCount> report(int tenantId) {
        jdbcTemplate.execute(
            "SET LOCAL work_mem = '32MB'"
        );

        return jdbcTemplate.query(
            """
            SELECT customer_id, COUNT(*) AS sale_count
            FROM lesson_spill.sales
            WHERE tenant_id = ?
            GROUP BY customer_id
            """,
            (rs, rowNum) -> new SalesCount(
                rs.getInt("customer_id"),
                rs.getLong("sale_count")
            ),
            tenantId
        );
    }
}
```

Đây là skeleton minh họa: `SalesCount`, imports và cấu hình Spring phải được cung cấp trong dự án thật.

### Điều kiện quan trọng

- `@Transactional` phải thực sự mở transaction thông qua proxy/transaction manager.
- Các câu SQL phải dùng connection gắn với transaction đó.
- `SET LOCAL` không hữu ích nếu statement báo cáo chạy sau khi transaction đã kết thúc.
- Với read replica, quy tắc quyền/cấu hình và workload có thể khác primary.

Không khai báo `@Transactional(readOnly=true)` rồi nghĩ PostgreSQL chắc chắn không thể sinh temp files. Một SELECT read-only vẫn có thể external sort/hash spill.

## 66. SQLSTATE khi vượt temp_file_limit

Nếu một query vượt giới hạn temporary file, PostgreSQL có thể báo lỗi và hủy statement.

Trong JDBC:

```java
try {
    ps.executeQuery();
} catch (SQLException e) {
    String sqlState = e.getSQLState();
    // Ghi SQLSTATE và thông báo đã được redact.
    // Rollback transaction nếu nó đã failed.
    throw e;
}
```

Không hardcode một SQLSTATE duy nhất cho mọi dạng “disk full” nếu hệ thống có nhiều nguyên nhân. Phân loại theo mã thật, error metadata, log và trạng thái storage.

### Transaction aborted

Sau lỗi trong transaction tường minh, câu lệnh tiếp theo có thể nhận:

```text
SQLSTATE 25P02
current transaction is aborted
```

Giải pháp là rollback/sử dụng savepoint hợp lệ; không tiếp tục spam SQL vào transaction đã lỗi.

### Retry có giúp không?

Nếu temp space hết vì query yêu cầu quá nhiều disk, retry ngay nhiều lần có thể làm tình trạng tệ hơn. Cần giảm workload, xử lý disk capacity, điều chỉnh giới hạn hoặc tối ưu kế hoạch trước khi retry.

## 67. EXPLAIN ANALYZE có chi phí

`EXPLAIN (ANALYZE)` **thực thi câu SQL thật** và thu thêm instrumentation.

Với SELECT nặng, nó có thể:

- Quét nhiều dữ liệu.
- Tạo temporary files.
- Làm ấm/ảnh hưởng cache.
- Sử dụng CPU/I/O đáng kể.
- Giữ locks/snapshots tùy câu SQL/isolation.

Với DML, còn có tác động ghi dữ liệu, triggers và WAL.

### TIMING OFF khi chỉ cần counters

```sql
EXPLAIN (
    ANALYZE,
    TIMING OFF,
    BUFFERS,
    SETTINGS
)
SELECT
    sale_id,
    note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);
```

`TIMING OFF` giảm một phần overhead đo thời gian từng plan node, nhưng statement **vẫn chạy** và temp I/O vẫn có thể phát sinh.

Không chạy một full external sort trên production nhiều lần chỉ để xem đúng ba con số.

## 68. Chạy EXPLAIN trên DML cần cẩn thận

Ví dụ:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE lesson_spill.sales
SET amount = amount + 1
WHERE sale_id BETWEEN 10 AND 20;

ROLLBACK;
```

Transaction rollback thường hoàn nguyên dữ liệu cập nhật, nhưng WAL đã phát sinh, locks/buffer activity đã xảy ra và có thể có side effects ngoài transaction. Sequence values cũng không rollback.

Bài học tập trung vào SELECT sorting/hashing để tránh tạo tác động ghi không cần thiết.

## 69. log_temp_files và file được xóa sau query

Một số log entries có thể xuất hiện **khi temporary file bị xóa**, ví dụ lúc query kết thúc hoặc cleanup một context.

Do đó trong lúc query đang chạy:

- File temp có thể đã chiếm disk nhưng **chưa có log hoàn chỉnh** cho file đó.
- `pg_stat_database.temp_files` là thống kê cumulative, thời điểm cập nhật khác với việc quan sát file live.
- OS-level disk usage có thể tăng tạm thời.

### Monitoring đúng

Kết hợp:

1. PostgreSQL metrics.
2. Temporary tablespace free space.
3. Log events.
4. Application/query tracing.
5. `EXPLAIN ANALYZE` khi có thể tái hiện an toàn.

Không xem log riêng lẻ là ảnh chụp toàn bộ storage đang bị chiếm.

## 70. Tác động của temp spill trên replication

Temporary files của sort/hash **không được xử lý như những thay đổi dữ liệu bền vững cần WAL replicate theo cách bảng thông thường**. Tuy vậy query chạy trên primary hay standby đều có thể tiêu tốn CPU/IO/temp capacity của node đó.

### Query read-only trên replica

Một báo cáo chạy trên standby có thể tạo temp files ở standby, gây I/O contention và làm chậm workload đọc, dù không tạo một transaction ghi dữ liệu nghiệp vụ.

### Không nhầm temp_bytes với WAL bytes

`temp_bytes` thống kê working files; `WAL Bytes` đo log generation. Một query sort lớn có thể tạo nhiều temporary I/O nhưng rất ít WAL.

Điều này giúp quyết định đặt workload đọc nặng ở đâu: replica có thể tách tải khỏi primary, nhưng vẫn cần tài nguyên temp disk/RAM riêng và phải xét replication lag, recovery conflicts.

## 71. Vì sao sort spill và hash spill có thể xảy ra ở cùng query?

Ví dụ:

```sql
SELECT
    p.category_id,
    COUNT(*) AS sale_count,
    SUM(s.amount) AS revenue
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
GROUP BY p.category_id
ORDER BY revenue DESC;
```

Plan có thể:

```text
Sort (ORDER BY revenue)
  └── HashAggregate (GROUP BY category_id)
       └── Hash Join
            ├── Seq Scan sales
            └── Hash
                 └── Seq Scan products
```

Các nơi có khả năng memory pressure:

- Hash build cho JOIN.
- HashAggregate group states.
- Sort output theo revenue.

Trong ví dụ cụ thể, số category chỉ khoảng 500 nên Sort cuối có thể nhỏ; HashAggregate cũng có thể nhỏ. **Không suy ra tất cả ba operator đều spill chỉ vì cây có ba loại node.**

### Tìm điểm nào tạo temp I/O thật

Đọc Sort Method, Hash Batches, HashAggregate Batches/Disk Usage và temp counters của từng node trên plan được đo.

## 72. Đổi ORDER BY có thể thay nhu cầu memory

Ví dụ:

```sql
SELECT
    customer_id,
    COUNT(*) AS n
FROM lesson_spill.sales
GROUP BY customer_id
ORDER BY n DESC;
```

Chỉ có khoảng 2000 khách trong lab, nên sort trên **2000 nhóm sau aggregate**, không phải 90.000 rows đầu vào.

Ngược lại, nếu query sort rows trước khi aggregate một cách không cần thiết:

```sql
WITH pre_sorted AS MATERIALIZED (
    SELECT *
    FROM lesson_spill.sales
    ORDER BY amount DESC
)
SELECT customer_id, COUNT(*)
FROM pre_sorted
GROUP BY customer_id;
```

thì Sort trong CTE có thể là công việc lãng phí cho tổng hợp cuối không yêu cầu thứ tự theo amount.

### Ý nghĩa

Hỏi: **ORDER BY nào thật sự cần cho output cuối?** Một thứ tự trung gian chỉ có ý nghĩa nếu downstream operator yêu cầu nó hoặc nghiệp vụ phụ thuộc. Bỏ sort không cần thiết thường tốt hơn tăng memory để xử lý sort ấy.

## 73. Những trường hợp phải giữ sort

Không thể bỏ `ORDER BY` nếu:

- API cam kết sắp xếp theo tiêu chí.
- `LIMIT` cần xác định đúng N hàng tốt nhất.
- Window function dùng một thứ tự xác định.
- `DISTINCT ON` cần thứ tự để chọn hàng đại diện.
- Phân trang cần thứ tự ổn định.
- Thuật toán downstream/operation cần ordered input theo kế hoạch.

### Tối ưu không đồng nghĩa bỏ semantics

Nếu report cần thứ tự doanh thu giảm dần, bỏ `ORDER BY revenue DESC` sẽ cho kết quả không được bảo đảm về thứ tự.

Hướng phù hợp là giảm số rows cần sort (aggregate trước), dùng index khi có thể, hoặc cấp ngân sách nhớ đúng phạm vi.

## 74. Correlated subquery và nhiều Sort nhỏ

Một query có thể gọi cùng loại Sort rất nhiều lần, ví dụ mỗi khách chọn 3 đơn mới nhất bằng subquery tương quan:

```sql
SELECT
    c.customer_id,
    recent.sale_id,
    recent.sold_at
FROM (
    SELECT DISTINCT customer_id
    FROM lesson_spill.sales
) AS c
CROSS JOIN LATERAL (
    SELECT
        sale_id,
        sold_at
    FROM lesson_spill.sales AS s
    WHERE s.customer_id = c.customer_id
    ORDER BY sold_at DESC, sale_id DESC
    LIMIT 3
) AS recent;
```

Nếu không có index `(customer_id, sold_at DESC, sale_id DESC)`, mỗi subquery có thể quét/sort nhiều hàng.

### Index thích hợp

```sql
CREATE INDEX ix_sales_customer_recent
ON lesson_spill.sales (
    customer_id,
    sold_at DESC,
    sale_id DESC
);
```

Khi index giúp tra cứu top 3 theo customer, nhiều repeated Sorts có thể biến mất hoặc giảm đáng kể.

### Khi nào LATERAL chưa chắc tối ưu?

Với hàng triệu customers, nhiều index lookups có thể tốn I/O; WindowAgg/Distinct On plan toàn cục có thể tốt hơn. Cần benchmark workload thật.

## 75. Index-only scan có giải quyết spill?

Index-only scan giảm nhu cầu đọc heap pages trong những điều kiện phù hợp, nhưng nó **không tự loại bỏ Sort/Hash**.

Ví dụ index bao gồm columns cần thiết, song query sắp theo một biểu thức khác:

```sql
SELECT sale_id, amount
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);
```

Ngay cả khi một index có thể cung cấp sale_id/amount, thứ tự md5 không được index hỗ trợ thì vẫn có thể cần Sort.

### Visibility map cũng quan trọng

Index-only scan thực sự tránh heap fetch phụ thuộc visibility map/MVCC. Không coi index có `INCLUDE` là bảo đảm mọi dữ liệu được phục vụ hoàn toàn từ index trong mọi lần chạy.

## 76. TEMP files không phải permanent bloat

External sort tạo working files thường được dọn khi không còn cần. Trong khi bloat bảng/index là vấn đề phiên bản tuple, VACUUM và phân bổ storage của relation.

| Vấn đề | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Spill temp files | `temp read/written`, log_temp_files, Sort/Hash disk usage. | Giảm data/intermediate, work_mem/hash budgets, index/SQL. |
| Table/index bloat | Dung lượng relation tăng, dead tuples, VACUUM visibility. | Điều tra MVCC, autovacuum, update patterns. |
| WAL growth | WAL records/bytes, replication slots/retention. | Điều tra write activity, replication, retention. |
| Shared cache misses | `shared read` nhiều, I/O timings. | Index/query pattern, cache, storage, data locality. |

Không chạy `VACUUM FULL` chỉ để “dọn temp files của Sort”. Đây là hai vấn đề khác nhau và VACUUM FULL có locking/chi phí riêng.

## 77. Phân biệt một operator spill với hệ thống thiếu RAM

Một Sort spill không tự chứng minh server hết RAM.

PostgreSQL có thể chủ động dùng temporary files vì **`work_mem` giới hạn** cho operator, dù OS còn nhiều RAM.

Ngược lại, không spill có thể đi cùng việc server memory pressure cao nếu rất nhiều operators/connections dùng RAM đồng thời.

### Hai lớp câu hỏi

**Ở mức câu query:**

- Operator nào spill?
- Vì sao input/intermediate lớn?
- Có index/SQL rewrite?
- Memory budget nào được dùng?

**Ở mức instance:**

- Bao nhiêu truy vấn đồng thời?
- Peak RSS/memory consumption?
- OS có swap/OOM?
- Temp disk bandwidth và free space?
- Connection pool/quyền concurrency?

Không dùng một câu `EXPLAIN` để khẳng định trạng thái RAM của toàn máy.

## 78. Khi nào nên cân nhắc nâng work_mem?

Nâng `work_mem` có thể hợp lý khi:

- Query thật cần sort/hash khối dữ liệu trung gian lớn.
- Index/SQL rewrite hợp lý đã được xem xét.
- Spill rõ ràng là nút thắt.
- Có RAM budget cho concurrent workload.
- Benchmarks cho thấy latency/throughput cải thiện.
- Có kế hoạch rollback setting nếu gặp memory pressure.

### Khi nào không nên?

- Query lẽ ra chỉ trả 20 hàng nhưng đang sort cả triệu vì thiếu index.
- Join sai làm nhân hàng.
- Reports chạy đồng thời rất nhiều.
- Memory pressure/OOM đã tồn tại.
- Có data skew/stale statistics nghiêm trọng.
- Temporary file I/O nhỏ và không ảnh hưởng SLA.

**Tăng RAM cho một plan chưa tốt có thể làm plan ấy nhanh hơn, nhưng vẫn để lại chi phí không cần thiết và rủi ro dưới concurrency.**

## 79. Chỉnh work_mem theo user, role hoặc workload

PostgreSQL có nhiều phạm vi cấu hình, ví dụ:

- Server-level setting.
- Database/role-level setting khi quyền cho phép.
- Session `SET`.
- Transaction-local `SET LOCAL`.

Với báo cáo cần nhiều memory nhưng chỉ chạy vài lần/ngày, transaction-local setting thường dễ kiểm soát hơn nâng global setting cho mọi request.

### Cần lưu ý

- Role-level tuning có thể ảnh hưởng nhiều query khác cùng role.
- Connection pool có thể tái sử dụng session.
- `SET` không reset có thể rò setting qua nhiều request.
- `SET LOCAL` chỉ hiệu lực trong transaction tương ứng.
- Những trường hợp dùng transaction pooling/proxy cần kiểm tra ngữ nghĩa session/transaction.

Không dùng role admin chung cho toàn ứng dụng rồi nâng work_mem cho mọi endpoint một cách thiếu phân loại.

## 80. Bộ câu lệnh lab so sánh nhanh

**A — Sort spill:**

```sql
BEGIN;
SET LOCAL work_mem = '64kB';
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sale_id, note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);
ROLLBACK;
```

**B — Sort trong RAM:**

```sql
BEGIN;
SET LOCAL work_mem = '64MB';
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sale_id, note
FROM lesson_spill.sales
ORDER BY md5(sale_id::text);
ROLLBACK;
```

**C — Hash Join có ngân sách nhỏ:**

```sql
BEGIN;
SET LOCAL work_mem = '64kB';
SET LOCAL hash_mem_multiplier = 1.0;
SET LOCAL enable_mergejoin = off;
SET LOCAL enable_nestloop = off;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT s.sale_id, p.description
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id;
ROLLBACK;
```

**D — HashAggregate nhiều nhóm:**

```sql
BEGIN;
SET LOCAL work_mem = '64kB';
SET LOCAL hash_mem_multiplier = 1.0;
SET LOCAL enable_sort = off;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sale_id % 40000, COUNT(*)
FROM lesson_spill.sales
GROUP BY sale_id % 40000;
ROLLBACK;
```

**E — Index tránh Sort top-N:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at
FROM lesson_spill.sales
WHERE tenant_id = 3
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

**F — Temp counters toàn database:**

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

**G — Kế hoạch JSON:**

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT JSON
)
SELECT customer_id, COUNT(*)
FROM lesson_spill.sales
GROUP BY customer_id;
```

Trong mọi lượt đo, lưu **SQL, dữ liệu, PostgreSQL version, settings và plan thật**, không chỉ đánh dấu “tốt” khi temp_written=0.

## 81. Runbook chẩn đoán sort/hash spill

### Bước 1 — Xác định đúng câu SQL

Tìm query có latency hoặc temp I/O cao theo log, application tracing, `pg_stat_statements`. Lưu parameter values ở mức có thể dùng để tái hiện, nhưng tránh thu thập secrets/PII.

### Bước 2 — Xác định data volume

Số rows, group cardinality, row widths, filter selectivity và các JOIN multiplicities. Dữ liệu của một tenant lớn có thể khác hẳn tenant nhỏ.

### Bước 3 — Lấy execution plan trong môi trường phù hợp

`EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)`; cân nhắc `TIMING OFF` nếu chỉ cần counters. Không chạy DML nguy hiểm trên production để đo.

### Bước 4 — Tìm node bị spill

Sort Method external merge, Sort Space Type Disk, Hash Batches>1, HashAggregate Disk Usage, Temp Read/Written Blocks.

### Bước 5 — Kiểm tra estimates

`Plan Rows`/`Actual Rows`, loops, group count, width. Nếu sai lớn, kiểm tra ANALYZE/stats/extended statistics.

### Bước 6 — Hỏi có thể loại operator không

Index đáp ứng ORDER BY, keyset pagination, chỉ trả top-N, WHERE sớm, DISTINCT ON, tránh materialize/sort không cần.

### Bước 7 — Giảm intermediate size

Giảm columns rộng, tránh SELECT *, pre-aggregate, sửa JOIN cardinality, EXISTS thay JOIN khi chỉ cần existence, loại DISTINCT che lỗi logic.

### Bước 8 — Tối ưu hoặc so sánh algorithm

Hash Join vs Merge Join vs Nested Loop; HashAggregate vs GroupAggregate. Đo temp I/O và total execution time, không ép planner mù quáng.

### Bước 9 — Thử memory budget có kiểm soát

`SET LOCAL work_mem` và `hash_mem_multiplier` trong transaction lab; đánh giá RAM/concurrency và song song.

### Bước 10 — Xem temp capacity và bảo vệ hệ thống

`temp_file_limit`, `temp_tablespaces`, free space, OS metrics, rate limiting heavy reports. Một query nhanh đơn lẻ không đủ nếu 100 query cùng chạy gây OOM.

### Bước 11 — Benchmark nhiều lần

Warm-up, dữ liệu tương đương, cache context, version/settings. So sánh median/tail latencies và throughput, không chỉ một lần EXPLAIN.

### Bước 12 — Theo dõi sau triển khai

Ghi `pg_stat_database.temp_bytes`, top temp-consuming queries, thời gian query, disk free, memory và error trends. Có kế hoạch rollback nếu ảnh hưởng workloads khác.

## 82. Bảng lựa chọn biện pháp khắc phục

| Dấu hiệu | Giả thuyết | Hướng xử lý nên thử trước |
|---|---|---|
| Sort external merge, ORDER BY+LIMIT | Sort nhiều hàng trước khi chọn ít hàng. | Index theo filter/order, keyset, top-N; giảm projection. |
| Sort spill trên toàn bộ báo cáo | Dataset/row width lớn. | Giảm cột, lọc hợp lệ, pre-aggregate, rồi thử work_mem. |
| Hash Join Batches cao | Build side lớn hoặc ít memory. | Lọc build side, giảm width, stats, join alternative, hash budget. |
| HashAggregate nhiều batches | Rất nhiều nhóm/aggregate states. | Kiểm tra group cardinality, pre-aggregate, stats, GroupAggregate/index. |
| Temp writes cao nhưng Sort nhỏ | Spill có thể ở Hash/Materialize khác. | Đọc toàn cây plan, không chỉ root. |
| Temp blocks tăng sau deploy | Query plan, input/cardinality hoặc concurrency đổi. | So plan/version/stats/settings/dataset. |
| Không spill nhưng vẫn chậm | CPU, IO bảng/index, locks hoặc client. | EXPLAIN khác metrics, wait events, profiling. |
| Temp disk đầy | Query lớn hoặc quá nhiều query spill. | Limit/rate-limit workload, capacity, sửa SQL, không xóa file thủ công. |
| A nhanh, B spill với cùng SQL | Config, dataset, statistics, plan/parallelism khác. | So SETTINGS, size, stats, execution plan thực tế. |

## 83. Những hiểu nhầm phổ biến

**“Có Sort node nghĩa là tràn đĩa.”** Không. Cần `Sort Method` hoặc temp counters; quicksort/top-N có thể dùng RAM.

**“Hash Join luôn tràn khi bảng lớn.”** Không. Phụ thuộc build-side size, projection và memory budget.

**“Batches>1 nghĩa query sai.”** Không. Đây là cơ chế batching hợp lệ; cần đánh giá runtime/IO.

**“work_mem là giới hạn RAM toàn backend.”** Không. Nó áp dụng cho nhiều operations riêng, không bao trọn toàn bộ memory process.

**“work_mem=64MB thì 100 queries vẫn chỉ dùng 64MB.”** Không. Concurrency và parallelism nhân khả năng dùng memory.

**“hash_mem_multiplier tăng sẽ chữa Sort external merge.”** Không trực tiếp. Nó dành cho hash operations.

**“shared_buffers tăng thì sort sẽ có nhiều work_mem hơn.”** Không. Chúng là memory contexts khác nhau.

**“temp_buffers điều chỉnh sort spill.”** Không; nó liên quan temporary relation local buffers.

**“temp_file_limit giảm I/O mà không có tác dụng phụ.”** Không. Đạt giới hạn có thể làm query lỗi.

**“temp_bytes là dung lượng temp files còn tồn tại.”** Không. Đây là thống kê cumulative.

**“Temp read=1000 nghĩa SSD đã làm đúng 1000 lượt đọc vật lý.”** Không. OS caching và cách đếm block accesses cần được xét.

**“Temp read + written là dữ liệu duy nhất của temp files.”** Không. Một block có thể được ghi/đọc nhiều lần.

**“Disk Usage và temp_bytes là cùng phép đo.”** Không. Working-space footprint khác I/O volume.

**“Cộng temp counters mọi node để lấy tổng.”** Sai nếu parent/child cùng báo activity.

**“Tăng work_mem đến khi temp=0 là tối ưu.”** Không. Query có thể tiêu tốn RAM quá lớn trong giờ cao điểm.

**“Không có temp=0 thì PostgreSQL sẽ không tạo file nào khác.”** Không; temp file từ những operations khác vẫn có thể tồn tại theo context.

**“Top-N heapsort chỉ đọc N rows.”** Không. Nếu không có index thỏa order, thường phải xét nhiều rows.

**“Index chỉ cần chứa cột WHERE là tránh Sort.”** Không. Thứ tự và chiều `ORDER BY` cũng quan trọng.

**“Incremental Sort luôn tốt hơn full Sort.”** Không. Groups lớn/skew và estimates sai có thể khiến nó kém.

**“HashAggregate ra kết quả có thứ tự.”** Không. Nếu cần thứ tự, dùng `ORDER BY`.

**“GroupAggregate luôn tránh disk vì không hash.”** Không. Input sort của nó cũng có thể spill.

**“Merge Join luôn tốt hơn Hash Join khi hash spill.”** Không. Merge có thể cần hai external sorts.

**“Chỉ cần SELECT * bỏ đi là Hash Join chắc chắn không spill.”** Không. Planner pruning và cardinality mới quyết định.

**“CTE MATERIALIZED luôn giảm tính toán.”** Không. Nó có thể cản predicate pushdown và tạo working set lớn.

**“DISTINCT để sửa duplicate do JOIN là miễn phí.”** Không. Nó có thể tạo Sort/HashAggregate rất lớn.

**“ANALYZE làm query không spill nữa.”** Không. Statistics giúp planner ước lượng nhưng không tăng memory hoặc thay nghĩa vụ tính toán.

**“EXPLAIN ANALYZE chỉ dự đoán plan.”** Không. Nó chạy SQL thật.

**“log_temp_files=0 tắt log.”** Không. Giá trị 0 yêu cầu log mọi temp file phù hợp; -1 mới là chế độ tắt thường gặp.

**“Nâng temp storage nhanh là sửa được sai JOIN.”** Không. Nó chỉ có thể giảm chi phí I/O, vẫn giữ logic/cost thừa.

**“Một lần chạy nhanh hơn chứng minh tuning thành công.”** Không. Cần nhiều runs và tính tới cache/concurrency.

## 84. Bài tập thực hành

### Bài 1 — Phân biệt shared và temp

Chạy `EXPLAIN (ANALYZE, BUFFERS)` cho một Sort trên sales. Giải thích sự khác nhau giữa `shared read` và `temp read`. Tại sao chúng không đồng nghĩa cùng một loại disk access?

### Bài 2 — External sort

Với `SET LOCAL work_mem='64kB'`, sắp 90.000 hàng theo `md5(sale_id::text)`. Tìm `Sort Method`, `Disk`, `Temp Read Blocks`, `Temp Written Blocks`.

### Bài 3 — Memory sort

Lặp bài 2 với `work_mem='64MB'`. Nếu Sort Method đổi sang quicksort và temp I/O giảm, những yếu tố nào khác cần giữ cố định trước khi kết luận tăng memory giúp nhanh hơn?

### Bài 4 — Tính block bytes

Dùng `SHOW block_size` và đổi 2.000 temporary blocks sang MiB. Vì sao đó không bằng dung lượng SSD đang bị chiếm tại một thời điểm?

### Bài 5 — Top-N

Chạy cùng `ORDER BY md5(...)` có và không có `LIMIT 20`. Quan sát Sort Method và shared-buffer accesses. Vì sao Top-N có thể vẫn đọc gần hết bảng?

### Bài 6 — Index tránh Sort

Tạo index `(tenant_id,sold_at DESC,sale_id DESC)`. Kiểm tra query tenant 3 lấy 20 đơn mới nhất. Plan còn Sort node không? Việc đọc ít rows có liên quan gì tới LIMIT?

### Bài 7 — Thứ tự cột của index

So sánh index `(sold_at,tenant_id)` với `(tenant_id,sold_at DESC)` cho query `WHERE tenant_id=3 ORDER BY sold_at DESC`. Vì sao order cột trong index có thể ảnh hưởng khả năng tránh Sort?

### Bài 8 — DISTINCT ON

Lấy đơn mới nhất mỗi customer trong tenant 3 bằng `DISTINCT ON`. Đề xuất index phù hợp. Tại sao `sale_id` tie-breaker cần được xem xét?

### Bài 9 — Incremental Sort

Tạo index trên `tenant_id`, chạy `ORDER BY tenant_id,amount DESC`. Nếu plan có Incremental Sort, ghi `Presorted Key`. Khi nào sort theo nhóm có thể giảm memory?

### Bài 10 — Hash Join nhỏ bộ nhớ

Trong transaction lab, `SET LOCAL work_mem='64kB'`, `hash_mem_multiplier=1.0`. Chạy JOIN sales/products và quan sát Hash node. `Buckets`, `Batches`, `Memory Usage` nghĩa là gì?

### Bài 11 — Hash Join tăng memory

Lặp bài 10 với `work_mem='32MB'`, multiplier 2.0. Ghi thay đổi `Batches`, temp reads/writes và execution time. Vì sao không nên đưa cấu hình đó lên server production ngay?

### Bài 12 — Build-side width

So sánh JOIN chỉ chọn `product_name` với JOIN cần `description` dài. Đọc `Plan Width` và temp I/O; giải thích vì sao projection có thể giúp, nhưng không cam kết mọi node đều lưu nguyên mọi cột.

### Bài 13 — HashAggregate ít nhóm

Chạy `GROUP BY tenant_id`. HashAggregate có bao nhiêu nhóm? So sánh số group states với `GROUP BY sale_id % 40000`.

### Bài 14 — HashAggregate spill

Đặt `work_mem='64kB'` và thử `GROUP BY sale_id % 40000`. Nếu PostgreSQL dùng HashAggregate, tìm `Batches` và `Disk Usage`. Nếu nó chọn GroupAggregate, giải thích vì sao không thể khẳng định spill hash từ SQL text.

### Bài 15 — GroupAggregate so với HashAggregate

So sánh hai kế hoạch cho cùng GROUP BY bằng những thí nghiệm enable_* trong transaction. Trường hợp nào có Sort external merge trước GroupAggregate? Vì sao chỉ nhìn temp bytes bằng 0 là chưa đủ?

### Bài 16 — Thống kê sai

Tạo dữ liệu thêm vào lab rồi xem estimates và actual rows trước/sau `ANALYZE`. Khi ước lượng groups sai, HashAggregate có thể bị ảnh hưởng thế nào?

### Bài 17 — Extended statistics

Tạo `CREATE STATISTICS ... (dependencies,ndistinct,mcv) ON tenant_id,customer_id` và ANALYZE. Giải thích việc thống kê tổ hợp có thể cải thiện ước lượng, và vì sao không bảo đảm sửa mọi join selectivity.

### Bài 18 — DISTINCT do JOIN sai

Một query join order lines với tags làm nhân hàng rồi dùng DISTINCT trên toàn bộ output. Hãy phân tích liệu `EXISTS`/semi-join có thể diễn đạt ý định tốt hơn và giảm Sort/HashAggregate không.

### Bài 19 — Aggregate trước JOIN

Viết hai query tổng doanh thu theo product: aggregate sau join và aggregate sales trước rồi join products. Nêu điều kiện để hai query tương đương và phương án nào có thể giảm intermediate width.

### Bài 20 — Lọc sớm

Một báo cáo chỉ cần tenant 3 và tháng 1/2026 nhưng query đang xử lý toàn bảng. Viết filter theo khoảng timestamptz half-open, rồi đo số rows và temp blocks.

### Bài 21 — Narrow-first

Một API chỉ trả 50 hàng sau ORDER BY expression nhưng còn cần `note` dài. Thiết kế query chọn sale IDs/khóa sort trước, rồi join để lấy payload. Khi nào phương pháp này có thể không lợi?

### Bài 22 — Keyset vs OFFSET

So sánh `LIMIT 20 OFFSET 30000` với keyset pagination theo `(sold_at,sale_id)` giảm dần. Những điều kiện gì cần có để phân trang ổn định?

### Bài 23 — Parallel workers

Nếu plan dùng Gather Merge và nhiều workers có Sort, giải thích vì sao `work_mem` có thể được dùng nhiều lần và vì sao không được nhân temp counters của root một cách cơ học với số workers.

### Bài 24 — log_temp_files

Giải thích `log_temp_files=-1`, `0` và ngưỡng dương. Vì sao bật log mọi temporary file trên production có thể gây quá nhiều log?

### Bài 25 — pg_stat_database

Đọc `temp_files`, `temp_bytes`, `stats_reset`. Vì sao `temp_bytes` không phải dung lượng temp files đang tồn tại?

### Bài 26 — pg_stat_statements

Nếu extension sẵn có, lấy top SQL theo `temp_blks_written`. Vì sao một query có tổng temp blocks cao nhưng mean runtime thấp vẫn có thể đáng tối ưu ở quy mô toàn hệ thống?

### Bài 27 — temp_file_limit

Giải thích `temp_file_limit` bảo vệ storage thế nào. Nếu query vượt giới hạn, PostgreSQL có tự tăng work_mem hoặc chọn index khác giữa chừng không? Ứng dụng cần làm gì sau lỗi?

### Bài 28 — temp_tablespaces

Một hệ thống có ổ NVMe riêng cho temp files. Hãy đánh giá khi nào chuyển temp tablespace có ích, và vì sao tối ưu SQL để không spill vẫn là hướng quan trọng.

### Bài 29 — Workload đồng thời

Giả sử pool có 40 connections và mỗi query có ba operators nặng. Thảo luận rủi ro khi tăng `work_mem` toàn server, thêm parallel workers và `hash_mem_multiplier`. Đề xuất quota/concurrency control.

### Bài 30 — JDBC SET LOCAL

Viết một method JDBC đặt `SET LOCAL work_mem` trong transaction, chạy GROUP BY, commit/rollback và đóng connection. Vì sao không dùng `SET` session-level vô điều kiện trong connection pool?

### Bài 31 — Spring transaction

Một method `@Transactional(readOnly=true)` chạy báo cáo spill. Vì sao “readOnly” không cấm tạo temp files? Làm sao bảo đảm `SET LOCAL` và query dùng cùng transaction?

### Bài 32 — Timings vs blocks

Hai queries có cùng temp written blocks nhưng execution times khác xa. Nêu cách kiểm tra `track_io_timing`, OS cache, CPU và tải đồng thời.

### Bài 33 — JSON parser

Trích `Plan` và duyệt mọi `Plans` trong `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. Phát hiện Sort Method external merge, Hash Batches lớn và Temp Written Blocks. Vì sao parser cần chấp nhận fields vắng mặt?

### Bài 34 — Node-level double counting

Một Sort và parent Aggregate cùng báo `temp read=1000`. Tại sao không cộng thành 2000? Nếu muốn biết node gây spill, bạn sẽ đọc thêm trường nào?

### Bài 35 — Tối ưu ORDER BY expression

Một query ORDER BY `lower(product_name)` và không có index expression. Hãy so sánh giữ Sort, tạo expression index hoặc canonical generated column. Chú ý collation/immutability và chi phí ghi.

### Bài 36 — Một truy vấn vừa hash vừa sort

Cho query JOIN sales/products, GROUP BY category và ORDER BY doanh thu. Vẽ cây có thể gồm Hash Join, HashAggregate, Sort. Operator nào **có thể** spill? Vì sao phải kiểm tra plan thực?

### Bài 37 — Temp disk đầy

Một báo cáo gây lỗi hết dung lượng temp. Viết runbook gồm xác định query, kiểm tra temporary files/capacity, ứng dụng transaction rollback, giảm data volume, memory tuning và alert.

### Bài 38 — Benchmark đúng

Thiết kế benchmark so sánh hai giá trị work_mem với cùng SQL và dataset, cache warm-up, nhiều lần chạy và nhiều mức concurrency. Chọn metrics cho cả latency và memory/temp I/O.

### Bài 39 — Sự khác nhau giữa WAL và temp files

Một SELECT sort lớn tạo 500 MB temp I/O; một UPDATE nhỏ tạo WAL. Phân biệt working files, data page writes và WAL durability/replication.

### Bài 40 — Tình huống tổng hợp

Ứng dụng đa tenant có query báo cáo:

```sql
SELECT
    s.tenant_id,
    p.category_id,
    COUNT(*) AS sale_count,
    SUM(s.amount) AS revenue
FROM lesson_spill.sales AS s
JOIN lesson_spill.products AS p
  ON p.product_id = s.product_id
WHERE s.status = 'PAID'
GROUP BY s.tenant_id, p.category_id
ORDER BY revenue DESC
LIMIT 100;
```

Hãy đưa ra kế hoạch tối ưu:

1. Kiểm tra `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` và node nào spill.
2. So estimated vs actual rows, group counts và join cardinality.
3. Xem index/filter và khả năng pre-aggregate mà không đổi semantics.
4. Cân nhắc `work_mem`/`hash_mem_multiplier` tại transaction của report.
5. Đánh giá khi 50 báo cáo chạy đồng thời.
6. Đề xuất logging/metrics để phát hiện hồi quy sau deploy.

## Kết luận

**Sort hoặc hash tràn ra đĩa không phải lỗi SQL, mà là dấu hiệu executor phải dùng temporary working files hoặc chia lô xử lý khi bộ nhớ dành cho thao tác không đủ.** Sort spill thường bộc lộ qua `Sort Method: external merge` và `Disk`; Hash Join/HashAggregate spill có thể biểu hiện bằng `Batches`, `Disk Usage` và `Buffers: temp read/written`. Để hiểu đúng, phải đọc **toàn bộ cây plan**, số hàng ước lượng/thực tế, độ rộng hàng, loops và các counters có phạm vi tích lũy.

`work_mem` là **ngân sách cho các thao tác thích hợp**, không phải trần RAM của một query hay cả PostgreSQL. `hash_mem_multiplier` có tác dụng với hash-based operations. Cả hai thông số đều có thể tăng sử dụng RAM khi có nhiều nodes, parallel workers và requests đồng thời; vì vậy không tăng toàn server chỉ để làm một truy vấn trong lab hết spill.

Phương pháp tối ưu bền vững là **loại bỏ hoặc thu hẹp công việc trung gian** trước: dùng index đáp ứng `WHERE` + `ORDER BY` + `LIMIT`, lọc sớm, keyset pagination, giảm row width, tránh `SELECT *` và `DISTINCT` không cần thiết, sửa join cardinality, pre-aggregate khi tương đương, cập nhật statistics và so sánh HashAggregate/GroupAggregate hoặc các join algorithms trên cùng workload. Khi công việc thật sự cần nhiều memory, thử cấu hình bằng `SET LOCAL`, đo temp I/O, runtime và memory dưới concurrency thực tế.

Cuối cùng, kết hợp `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`, `log_temp_files`, `pg_stat_database`, `pg_stat_statements` và telemetry hệ điều hành để xác định **query nào spill, operator nào chịu trách nhiệm, mức độ ảnh hưởng và cách phòng tái phát**. Một tối ưu thành công không chỉ giảm `temp written` mà phải trả kết quả đúng, cải thiện latency/throughput và giữ hệ thống ổn định khi nhiều người dùng cùng chạy truy vấn.
