# BUFFERS, WAL, SETTINGS và định dạng JSON

Một truy vấn PostgreSQL chạy mất 800 ms. Chỉ nhìn `Execution Time` chưa đủ để biết nó chậm vì quét nhiều trang dữ liệu, vì tràn bộ nhớ xuống file tạm, vì tạo quá nhiều WAL, vì trình lập kế hoạch đang dùng một thiết lập khác với môi trường kiểm thử, hay đơn giản vì cache chưa được làm nóng. Đặc biệt khi hai lần chạy cùng một SQL cho ra thời gian khác nhau, chỉ đọc chi phí `cost=...` và số hàng `rows=...` thường không giải thích được nguyên nhân.

PostgreSQL cung cấp các tùy chọn mở rộng của `EXPLAIN`:

- **`BUFFERS`:** báo số khối dữ liệu truy cập qua shared buffers, local buffers và các khối tạm; giúp phân tích cache và I/O ở mức executor.
- **`WAL`:** báo số WAL records, full-page images và số byte WAL được tạo khi thực thi; đặc biệt hữu ích cho `INSERT`, `UPDATE` và `DELETE`.
- **`SETTINGS`:** đưa các tham số cấu hình **ảnh hưởng tới lập kế hoạch** có giá trị khác mặc định tích hợp vào output, hỗ trợ so sánh hai môi trường.
- **`FORMAT JSON`:** xuất cây kế hoạch dưới dạng dữ liệu JSON thay vì text căn lề, thuận tiện cho công cụ, script và pipeline phân tích.

Các tùy chọn thường được kết hợp:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT *
FROM some_table
WHERE id = 42;
```

Trong ví dụ trên, `some_table` là tên minh họa; phần lab bên dưới cung cấp bảng chạy được. **`ANALYZE` khiến câu SQL được thực thi thật**, không chỉ dự đoán kế hoạch. Nếu SQL là lệnh sửa dữ liệu, các hiệu ứng của lệnh có thể xảy ra. Đây là phân biệt quan trọng nhất trước khi dùng các tùy chọn này.

Bài học trình bày cả **cú pháp**, **đọc số liệu**, **các giới hạn đo lường**, **lab có thể tái hiện**, **đọc JSON bằng Java/JDBC** và **quy trình chẩn đoán**.

> **Phạm vi và an toàn:** Những ví dụ dùng PostgreSQL hiện đại. Tên trường JSON, chi tiết instrumentation và khả năng hỗ trợ tùy chọn có thể thay đổi giữa các phiên bản. Chạy lệnh cập nhật/xóa/chèn có `EXPLAIN ANALYZE` trong database lab hoặc transaction có kế hoạch rollback rõ ràng; không chạy trực tiếp trên dữ liệu production chỉ để xem một plan.

## 1. EXPLAIN trả lời những câu hỏi nào?

`EXPLAIN` trình bày **kế hoạch thực thi** mà PostgreSQL chọn cho một statement: quét bảng bằng cách nào, dùng index nào, join theo thuật toán gì, sort/aggregate ở đâu, ước lượng bao nhiêu hàng và chi phí tương đối là bao nhiêu.

```sql
EXPLAIN
SELECT *
FROM pg_catalog.pg_class
WHERE relname = 'pg_class';
```

Đây là **plan-only**: chủ yếu cho thấy ước lượng của planner, không đo số hàng, thời gian và buffer sử dụng trong một lần thực thi query.

Khi thêm:

```sql
EXPLAIN (ANALYZE)
SELECT *
FROM pg_catalog.pg_class
WHERE relname = 'pg_class';
```

PostgreSQL chạy câu SELECT thật để đo các thông tin như:

- `actual time`: thời gian quan sát tại node.
- `actual rows`: số hàng thực tế được node tạo ra theo ngữ nghĩa thống kê node.
- `loops`: số lần node được gọi/thực thi.
- `Planning Time` và `Execution Time` khi được hiển thị.

Với `BUFFERS` và `WAL`, còn có dấu hiệu **bao nhiêu trang dữ liệu được chạm tới** và **bao nhiêu dữ liệu WAL được tạo**.

### EXPLAIN không phải SQL profiler toàn năng

Nó **không tự cung cấp**:

- Phân rã toàn bộ thời gian ứng dụng gồm HTTP, serialization, network và render UI.
- CPU time chính xác trên mỗi node.
- Danh sách tất cả file vật lý được OS đọc trên đĩa.
- Nguyên nhân mọi lần chờ khóa hoặc I/O ở tầng hệ điều hành.
- Lịch sử nhiều lần chạy của một câu SQL.
- Kết luận tự động rằng chỉ mục hay cấu hình nào là tối ưu.

`EXPLAIN` là một phần của điều tra hiệu năng, không phải toàn bộ bức tranh.

## 2. Tóm tắt những tùy chọn quan trọng

| Tùy chọn | Câu hỏi chính | Lưu ý |
|---|---|---|
| `ANALYZE` | Khi thực thi, thật sự mất bao lâu và tạo bao nhiêu hàng? | **Thực thi câu SQL thật**. |
| `BUFFERS` | Bao nhiêu buffer blocks được hit/read/dirty/write và bao nhiêu temp blocks? | Thường dùng cùng `ANALYZE` để xem executor. |
| `WAL` | Việc thực thi tạo bao nhiêu WAL records/FPI/bytes? | Dùng cùng `ANALYZE`; đặc biệt hữu ích cho DML. |
| `SETTINGS` | Những planner-relevant GUC nào khác mặc định tích hợp? | Không phải output của `SHOW ALL`. |
| `FORMAT JSON` | Cây kế hoạch dưới dạng dữ liệu có cấu trúc như thế nào? | Top-level thông thường là **mảng JSON**. |
| `FORMAT TEXT` | Xem plan dễ đọc trong terminal. | Dạng mặc định của `EXPLAIN`. |
| `VERBOSE` | Xem thêm output columns, schema và chi tiết plan. | Có thể khiến plan dài. |
| `TIMING OFF` | Giảm overhead đo thời gian node, vẫn có rows/loops. | Dùng với `ANALYZE`. |
| `SUMMARY` | Có hiển thị phần tóm lược như planning/execution time không? | Cấu hình hiển thị; không đổi logic SQL. |
| `COSTS OFF` | Ẩn cost/rows/width ước lượng khi trình bày. | Không có nghĩa planner bỏ dùng cost. |

Một lệnh tổng hợp dễ dùng để điều tra:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    VERBOSE,
    FORMAT TEXT
)
SELECT 1;
```

Nó hợp lệ cho SELECT đơn giản nhưng số liệu buffer/WAL có thể rất ít hoặc bằng 0. Muốn phân tích thực chất, dùng dữ liệu và truy vấn có đủ công việc để đo.

### Khi nào không cần ANALYZE?

Nếu chỉ cần xem lựa chọn plan và không được phép thực thi câu SQL:

```sql
EXPLAIN (SETTINGS, FORMAT JSON)
SELECT *
FROM pg_catalog.pg_class
WHERE oid = 1259;
```

Kế hoạch ước lượng không có `Actual Rows`/`Actual Loops` hay các counters WAL thực thi. Không suy diễn từ plan-only rằng query chắc chắn nhanh/chậm như một thời gian cụ thể.

## 3. Dữ liệu lab dùng xuyên suốt

Tạo schema và các bảng mẫu:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_plan_metrics;

CREATE TABLE lesson_plan_metrics.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE lesson_plan_metrics.sales (
    sale_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lesson_plan_metrics.customers(customer_id),
    sold_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'REFUNDED')),
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0),
    note TEXT NOT NULL
);
```

Tạo 1.000 khách hàng và 30.000 lượt bán giả lập:

```sql
INSERT INTO lesson_plan_metrics.customers (
    customer_id,
    customer_name
)
SELECT
    g,
    'Customer ' || g
FROM generate_series(1, 1000) AS g;

INSERT INTO lesson_plan_metrics.sales (
    customer_id,
    sold_at,
    status,
    amount,
    note
)
SELECT
    1 + (g % 1000),
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 minute',
    CASE WHEN g % 10 = 0
         THEN 'REFUNDED'
         ELSE 'PAID'
    END,
    ((g % 5000) + 1)::numeric / 100,
    repeat('x', 100) || '-' || g::text
FROM generate_series(1, 30000) AS g;
```

Dữ liệu nhân tạo có phân bố đều và dễ giải thích. Nó **không phản ánh dữ liệu production** có skew, thời gian phát sinh sự kiện hay kích thước row thực tế.

### Tạo index để so sánh

```sql
CREATE INDEX ix_sales_customer_recent
ON lesson_plan_metrics.sales (
    customer_id,
    sold_at DESC
);

CREATE INDEX ix_sales_status
ON lesson_plan_metrics.sales (status);

ANALYZE lesson_plan_metrics.customers;
ANALYZE lesson_plan_metrics.sales;
```

`ANALYZE` ở đây là câu lệnh thu thập thống kê planner cho bảng, **khác với tùy chọn `ANALYZE` bên trong `EXPLAIN`**.

### Câu hỏi cần nhớ trước khi xem kết quả

Không có output số liệu nào từ lab này được đảm bảo giống hệt giữa mọi máy. Buffer hits, page reads, plan nodes và thời gian phụ thuộc:

- Phiên bản PostgreSQL và cấu hình.
- Kích thước bảng, statistics và cache.
- Nền tảng hệ điều hành, RAM và storage.
- Các truy vấn chạy trước và cùng thời điểm.
- Checkpoint, autovacuum, tải hệ thống và parallel workers.

Vì vậy, ví dụ output trong bài là **minh họa**, không phải lời hứa sẽ nhận đúng từng con số.

## 4. Anatomy của một execution plan dạng TEXT

Truy vấn:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT TEXT
)
SELECT
    sale_id,
    sold_at,
    amount
FROM lesson_plan_metrics.sales
WHERE customer_id = 42
ORDER BY sold_at DESC
LIMIT 5;
```

Một bản minh họa được đơn giản hóa:

```text
Limit  (cost=0.29..12.10 rows=5 width=22)
       (actual time=0.020..0.065 rows=5 loops=1)
  Buffers: shared hit=4 read=2
  -> Index Scan using ix_sales_customer_recent on sales
       (cost=0.29..120.00 rows=30 width=22)
       (actual time=0.018..0.061 rows=5 loops=1)
       Index Cond: (customer_id = 42)
       Buffers: shared hit=4 read=2
Planning:
  Buffers: shared hit=15
Planning Time: 0.180 ms
Execution Time: 0.090 ms
```

Phân tích:

1. **`Limit`:** node trả tối đa năm hàng.
2. **`Index Scan`:** dùng chỉ mục tương ứng với `customer_id` và thứ tự `sold_at DESC`.
3. **`cost=...`:** ước lượng tương đối của planner, **không phải mili giây**.
4. **`rows=30`:** số hàng planner ước lượng ở node nguồn.
5. **`actual rows=5`:** thực tế node chỉ cần tạo năm hàng khi `LIMIT` dừng việc đọc.
6. **`loops=1`:** node chạy một lần trong ví dụ.
7. **`shared hit/read`:** đếm số khối được tìm thấy trong shared buffer cache và các khối phải nạp qua đường đọc buffer.
8. **`Planning Time`:** thời gian tạo plan được đo.
9. **`Execution Time`:** thời gian thực thi được đo cho statement.

**Không cộng hai lần `Buffers` của Limit và Index Scan.** Counters của một plan node thường phản ánh hoạt động tích lũy trong cả node và descendants theo cách instrument. Một parent có thể bao gồm công việc từ child.

## 5. BUFFERS đếm những gì?

Một buffer block là đơn vị dữ liệu mà PostgreSQL quản lý trong cơ chế bộ đệm, thông thường tương ứng với một trang database. PostgreSQL thường dùng page size **8 KiB** trên nhiều bản build, nhưng không nên mã hóa cố định giả định này trong tooling.

Kiểm tra:

```sql
SHOW block_size;
```

hoặc:

```sql
SELECT
    current_setting('block_size')::integer AS block_bytes;
```

Với `BUFFERS`, nhóm counters quan trọng gồm:

| Nhóm | Những số thường thấy | Nguồn sử dụng |
|---|---|---|
| **Shared** | `hit`, `read`, `dirtied`, `written` | Trang của bảng/index dùng shared buffer pool. |
| **Local** | `hit`, `read`, `dirtied`, `written` | Local buffers của temporary relations. |
| **Temp** | `read`, `written` | Khối của file tạm phục vụ các bước xử lý như sort/hash spill. |

Output text thường bỏ các counters bằng 0 để đỡ dài; vì thế không thấy dòng `temp` **không tự có nghĩa server không từng dùng file tạm** trong cả thời gian hoạt động, mà chỉ là không có giá trị được báo ở phạm vi kế hoạch đang đo.

### Một ví dụ dòng BUFFERS

```text
Buffers: shared hit=150 read=20 dirtied=3 written=2,
         local hit=5 read=1,
         temp read=80 written=120
```

Cách đọc:

- 150 lần tham chiếu page được thỏa từ shared buffers.
- 20 lần yêu cầu nạp page vào shared buffers qua đường read.
- 3 blocks được đánh dấu dirty từ trạng thái sạch trước đó trong phạm vi được ghi nhận.
- 2 dirty blocks được backend ghi ra theo cơ chế báo cáo.
- Temporary relation dùng local buffers theo counters.
- File tạm dùng trong xử lý query có 80 block reads và 120 block writes.

Không tự đổi những con số trên thành **MB đọc trực tiếp từ SSD** mà không xét cache, kích thước block, lặp node và hệ điều hành.

## 6. Shared Hit Blocks: “hit” nghĩa gì?

`shared hit=1000` nghĩa là có **1.000 lần tìm page** mà page cần thiết đã nằm trong **PostgreSQL shared buffer pool** và không cần nạp page mới vào pool cho lần tham chiếu đó.

Điều đó **không có nghĩa**:

- Query đọc đúng 1.000 trang **khác nhau**.
- PostgreSQL có đúng 1.000 trang trong RAM.
- Cache hit ratio của toàn server là 100%.
- Toàn bộ dữ liệu đã được phục vụ từ CPU cache.

Một trang có thể được truy cập nhiều lần, đặc biệt khi có Nested Loop, nhiều index lookups hoặc node được gọi nhiều lần.

### Shared hit cao là tốt hay xấu?

Phụ thuộc mục tiêu. Một query đọc 2 triệu blocks từ cache có thể vẫn rất tốn CPU và băng thông bộ nhớ, trong khi query đọc 50 blocks từ storage có thể rất nhanh trên hệ thống hiện đại.

**Hit cao không tự chứng minh plan hiệu quả.** Hãy xem cả:

- Số hàng cuối cùng cần trả.
- Tổng số blocks chạm tới.
- Kiểu scan/join và số loops.
- Execution Time so với SLO.
- Sự khác biệt giữa estimate và actual rows.

## 7. Shared Read Blocks: “read” không luôn là đọc đĩa vật lý

`shared read=500` nghĩa là 500 lần cần lấy page qua cơ chế đọc buffer thay vì đã có sẵn trong PostgreSQL shared buffers.

**Điều quan trọng:** page có thể được hệ điều hành giữ trong **OS page cache**. Vì vậy, `shared read` không đồng nhất với:

```text
500 lần truy cập SSD/HDD vật lý
```

Nó cho biết page **không sẵn trong PostgreSQL shared buffer pool** ở lúc tra cứu, và được nạp theo đường đọc. Việc truy cập storage thật sự hay trả từ OS cache nằm ở tầng dưới.

### Hai lần chạy khác nhau

```text
Lần 1:
  shared hit = 100
  shared read = 900
  Execution Time = 140 ms

Lần 2:
  shared hit = 980
  shared read = 20
  Execution Time = 35 ms
```

Đây là số liệu giả định. Một diễn giải có thể là lần đầu **làm ấm cache**, lần hai tái sử dụng buffer. Nhưng để kết luận cần kiểm tra workload, kế hoạch, row counts, I/O timing và các yếu tố đồng thời.

### Cache ấm không đảm bảo luôn nhanh

Plan cũng có thể đổi vì statistics, query parameters, thay đổi `work_mem`/`random_page_cost` hoặc prepared statement generic/custom plan. Đừng kết luận mọi khác biệt thời gian là do cache chỉ từ hai số hit/read.

## 8. Shared Dirtied Blocks và Shared Written Blocks

Hai counters dễ bị hiểu nhầm:

- **`dirtied`:** một page trước đó sạch đã bị thay đổi và trở thành dirty trong quá trình xử lý được ghi nhận.
- **`written`:** dirty pages được chính backend ghi ra theo phạm vi thống kê.

### Dirtied không bằng số rows UPDATE

Một block có thể chứa nhiều hàng. Cập nhật 100 rows không có nghĩa `dirtied=100`. Một truy vấn cũng có thể sửa index pages, visibility metadata và những page khác.

### Written không bằng toàn bộ ghi vật lý phát sinh từ transaction

PostgreSQL có **checkpointer**, background writer và các đường ghi khác. Một số dirty pages có thể được ghi ra **sau khi statement hoàn thành**, không nhất thiết bởi backend đang chạy câu SQL đó.

Vì vậy:

```text
Buffers: shared dirtied=500 written=0
```

không có nghĩa “500 pages chưa bao giờ được ghi ra đĩa” hay “query không làm phát sinh I/O ghi”. Nó chỉ mô tả phạm vi instrumentation của lần thực thi.

### Đọc cùng WAL

Một UPDATE có thể có:

```text
Buffers: shared hit=1000 dirtied=90 written=0
WAL: records=140 fpi=12 bytes=98000
```

Điều này phù hợp với việc **bản dữ liệu đang được thay đổi**, và WAL records được tạo để phục hồi/replication. Việc page dirty chưa được backend ghi ngay không ngăn transaction tạo WAL.

## 9. Local Buffers khác Temp Blocks

Tên gần giống nhưng ý nghĩa khác:

**Local buffers** phục vụ temporary relations thuộc session, chẳng hạn bảng tạm:

```sql
CREATE TEMP TABLE tmp_sale_ids (
    sale_id BIGINT
);

INSERT INTO tmp_sale_ids(sale_id)
SELECT sale_id
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM tmp_sale_ids;
```

Câu này có thể báo `local hit/read/dirtied/written` tùy cách truy cập và cache.

**Temp blocks** trong EXPLAIN thường đề cập **working files tạm** mà executor dùng cho:

- External sort khi không đủ memory.
- Hash join/aggregate cần phân lô hoặc tràn sang đĩa.
- Một số hoạt động materialization và cơ chế xử lý tạm khác.

Ví dụ:

```text
Buffers: temp read=1200 written=1900
```

không nhất thiết liên quan tới bảng `CREATE TEMP TABLE`; nó có thể là dấu hiệu một Sort node phải tạo file tạm.

### Câu hỏi debug đúng

- Thấy **local**: ứng dụng có đang đọc/ghi temporary relations không?
- Thấy **temp**: node sort/hash/materialize nào đã dùng file tạm, kích thước/số lần ra sao?

Trộn hai khái niệm sẽ dẫn đến tối ưu sai hướng.

## 10. Temp Read/Write và work_mem

`work_mem` là giới hạn bộ nhớ áp dụng cho **từng hoạt động sort/hash phù hợp**, không đơn giản là “mỗi connection dùng đúng từng ấy RAM cho mọi query”.

Một query có thể chứa nhiều sort/hash nodes; parallel workers và các tham số liên quan như `hash_mem_multiplier` còn ảnh hưởng tổng memory. Không tự tăng `work_mem` toàn server chỉ vì một truy vấn spill.

### Ví dụ tạo sort nhiều dữ liệu

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    sale_id,
    note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

Với 30.000 rows và `work_mem` nhỏ, Sort có thể phải spill:

```text
Sort
  Sort Key: (md5((sale_id)::text))
  Sort Method: external merge  Disk: 4500kB
  Buffers: shared hit=..., temp read=... written=...
```

Số `Disk` và temp counters là **minh họa**, không cố định. Một plan có thể chọn cách khác khi phiên bản, dữ liệu và cấu hình thay đổi.

### So sánh với work_mem lớn hơn

```sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    sale_id,
    note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

Bạn có thể thấy `Sort Method: quicksort  Memory: ...` và temp reads/writes giảm hoặc biến mất. Nhưng:

- Memory lớn hơn **không phải luôn nhanh hơn** nếu dữ liệu đã vừa trong memory.
- `work_mem` tăng có thể gây áp lực RAM lớn khi có nhiều session/plan nodes.
- Thay đổi `work_mem` có thể làm planner chọn plan khác.
- Một số query spill do hash batching/estimated cardinality sai, không chỉ thiếu một giá trị work_mem cố định.

**Mục tiêu là xử lý nguyên nhân**, không chỉ nâng cấu hình cho tới khi temp blocks bằng 0.

## 11. Đổi block counts sang dung lượng

Nếu `SHOW block_size` cho kết quả `8192` bytes:

```text
1 block = 8 KiB
1000 blocks = 1000 × 8192 = 8 192 000 bytes
            ≈ 7,8125 MiB
```

Trong SQL:

```sql
SELECT
    current_setting('block_size')::bigint AS bytes_per_block,
    1000::bigint *
        current_setting('block_size')::bigint
        AS estimated_bytes,
    pg_size_pretty(
        1000::bigint *
        current_setting('block_size')::bigint
    ) AS readable_size;
```

Đây là **quy đổi số block accesses sang đơn vị byte** nhằm đọc metric, không phải chứng cứ query đã chuyển đúng từng ấy byte từ disk vật lý.

### Tránh cộng shared hit và read rồi gọi “database size”

`hit + read` có thể đếm lặp lại những page đã được tham chiếu nhiều lần. Nó không phải dung lượng bảng hoặc dung lượng thực tế trên disk.

Muốn biết kích thước một bảng và indexes:

```sql
SELECT
    pg_size_pretty(
        pg_total_relation_size(
            'lesson_plan_metrics.sales'::regclass
        )
    ) AS total_relation_size;
```

Đây là câu hỏi **dung lượng đối tượng** khác với câu hỏi **buffer accesses của một statement**.

## 12. Counters tại node là tích lũy, không cộng tùy tiện

Một cây đơn giản:

```text
Limit
  Buffers: shared hit=10 read=2
  └── Index Scan
        Buffers: shared hit=10 read=2
```

Nếu bạn cộng:

```text
10 + 10 = 20 hits
2 + 2 = 4 reads
```

để suy ra tổng cho query, bạn **đã đếm trùng** công việc được phản ánh cả ở parent và child.

### Nguyên tắc

Đọc node-level counters để **tìm nguồn phát sinh công việc** theo cây plan, không lấy tổng mọi node như những nhóm độc lập.

- Node cha có thể bao gồm hoạt động của descendant.
- Nested Loop có thể gọi child nhiều lần.
- Parallel nodes có thể có worker-level counters.
- Planning buffers và execution buffers là những phạm vi khác nhau.

Khi so sánh hai plan, nên xem counters của **root** hoặc phần summary phù hợp rồi phân tích các node nào chiếm phần lớn công việc. Không giả định output root bao gồm mọi hoạt động bên ngoài executor hoặc background processes.

## 13. Actual Rows, Loops và sự khác nhau giữa rows với blocks

Một plan node có thể hiển thị:

```text
Index Scan ... (actual time=0.004..0.007 rows=3 loops=1000)
Buffers: shared hit=3100
```

`rows=3` trong số liệu per-loop không đồng nghĩa node chỉ trả tổng cộng ba hàng.

Với một node được thực thi nhiều lần, `actual rows` và `actual time` thường được biểu diễn là **giá trị trung bình trên mỗi lần thực thi**, theo cách PostgreSQL báo cáo. Một phép ước tính khối lượng đầu ra của node:

```text
3 rows/loop × 1000 loops ≈ 3000 rows
```

Nhưng `Buffers` có ý nghĩa riêng về hoạt động được tích lũy, và các số hàng/thời gian có thể được làm tròn trong text output.

### Nested Loop thường gây nhiều buffer hits

```text
Nested Loop
  ├── Seq Scan customers (1000 hàng)
  └── Index Scan sales ... (loops=1000)
```

Mỗi khách kích hoạt một lookup vào sales. Dù mỗi lookup rẻ, tổng số index page accesses có thể lớn. Đây là ví dụ điển hình vì sao phải đọc **loops cùng BUFFERS**, không chỉ nhìn một lần quét index.

### Actual time không cộng trực tiếp giữa parent và child

Thời gian node thường gồm thời gian thực hiện descendant theo cách instrument, nên cộng tất cả `actual total time` có thể đếm trùng. `Execution Time` ở cuối là chỉ dấu tổng thời gian của lần thực thi plan được đo.

## 14. BUFFERS và parallel query

Khi PostgreSQL chọn parallel scan/aggregate/sort, plan có thể có:

```text
Gather
  Workers Planned: 2
  Workers Launched: 2
  Buffers: shared hit=... read=...
  └── Parallel Seq Scan
        Buffers: shared hit=... read=...
```

Với `VERBOSE` hoặc format JSON, có thể có các mục thông tin cho **workers**.

### Những điều cần thận trọng

- Không nhân số `Buffers` tại node song song với số workers chỉ vì thấy `Workers Launched=2`.
- Các thống kê có thể đã được PostgreSQL tổng hợp theo phạm vi node/worker.
- `Actual Rows` và `Loops` có ngữ nghĩa quan sát cần đọc cùng các worker details.
- Thời gian chạy song song không bằng tổng thời gian CPU của workers.
- Số workers **planned** không đảm bảo số workers **launched** bằng nhau.

Khi trích xuất JSON, nên lưu lại cả workers nếu muốn phân tích bottleneck giữa leader và workers. Không chỉ lấy số liệu của root rồi đoán worker nào chậm.

## 15. BUFFERS trong giai đoạn lập kế hoạch

PostgreSQL đôi khi hiển thị buffer accesses trong phần **Planning**:

```text
Planning:
  Buffers: shared hit=30 read=5
Planning Time: 0.320 ms
```

Planner có thể cần đọc catalog, statistics, index metadata và các cấu trúc liên quan để xây plan.

### Planning buffers khác execution buffers

- **Planning:** chi phí đọc metadata/thông tin trong khi lập kế hoạch.
- **Execution:** truy cập page khi thực thi các plan nodes.

Đừng gộp hai phạm vi thành một số “table read” rồi cho rằng tất cả đều đến từ truy vấn trên bảng nghiệp vụ.

### Vì sao planning buffers đôi khi tăng?

Một câu query có nhiều joins, relation partitions hoặc các object liên quan có thể cần nhiều metadata hơn. Một số lần đầu có catalog cache chưa ấm và phải đọc thêm page.

Để điều tra planning chậm, xem cấu trúc query, số bảng/partitions, catalog/statistics và cache context. Không chỉ tối ưu `work_mem` vốn thường tác động chủ yếu tới execution sort/hash.

## 16. Khi nào bật track_io_timing?

`BUFFERS` cho biết **số lần truy cập block**, nhưng **không tự cho thời gian chờ I/O chính xác**.

PostgreSQL có tham số `track_io_timing`:

```sql
SHOW track_io_timing;
```

Khi được bật và được hệ thống hỗ trợ, EXPLAIN có thể báo thời gian I/O, chẳng hạn:

```text
I/O Timings: shared read=... write=...
```

Thông tin cụ thể phụ thuộc phiên bản và kiểu I/O được theo dõi.

### Tại sao có giá trị?

Hai truy vấn cùng báo:

```text
shared read=10000
```

nhưng thời gian đọc có thể khác rất nhiều tùy OS cache, storage, contention và môi trường.

### Chi phí và quyền

Đo thời gian I/O có overhead vì cần đọc đồng hồ đo lường ở những điểm thích hợp. Tùy môi trường, việc bật thay đổi cấu hình có thể đòi quyền đặc biệt.

Không bật/tắt toàn server trên production chỉ để xem một truy vấn nếu chưa xem hướng dẫn vận hành và tác động. `track_io_timing` giúp chẩn đoán, nhưng không thay thế hệ thống telemetry ở OS/storage.

## 17. Khi BUFFERS tăng nhưng Execution Time không tăng

Một plan có thể đọc nhiều page nhưng vẫn nhanh vì dữ liệu có sẵn trong cache hoặc hardware có throughput tốt. Ngược lại, plan có ít reads vẫn chậm vì:

- CPU-heavy expression hoặc JSON processing.
- Hàm UDF tốn thời gian.
- Contention trên locks/LWLocks.
- Sort/hash tính toán phức tạp.
- Chờ client/network hoặc các overhead ngoài query.
- Sai ước lượng dẫn đến join strategy tốn kém.

### Quy trình đọc đúng

1. Nhìn `Execution Time`.
2. Nhìn `Actual Rows`, `Loops`.
3. Nhìn `Buffers` theo các node lớn.
4. Xem có temp spill không.
5. Nếu có, đọc I/O timings khi được bật.
6. Đối chiếu `wait_event_type` và workload ngoài.

**Không dùng duy nhất một counter để kết luận “query cần index mới”.**

## 18. WAL là gì?

**Write-Ahead Log (WAL)** là cơ chế ghi nhật ký thay đổi trước khi các page dữ liệu cần thiết được coi là bền vững theo mô hình crash recovery. PostgreSQL dùng WAL để phục hồi sau sự cố và hỗ trợ các hình thức replication/backup phù hợp.

Mô hình khái niệm:

```text
Transaction cập nhật dữ liệu
              │
              ▼
     Tạo thông tin WAL
              │
              ▼
     WAL được ghi/flush theo
     quy tắc commit và cấu hình
              │
              ▼
     Data pages có thể được
     ghi xuống storage về sau
```

Điểm quan trọng là **ghi WAL và ghi data pages là hai đường chi phí khác nhau**. Vì vậy một `UPDATE` có thể tạo nhiều WAL bytes nhưng dòng `Buffers: shared written=0` tại thời điểm đo.

### WAL không phải application audit log

WAL phục vụ cơ chế database, không được thiết kế là bảng lịch sử nghiệp vụ có thể truy vấn tùy ý “ai sửa trường nào”. Nếu cần audit, dùng bảng lịch sử, trigger, event log hoặc CDC theo yêu cầu.

## 19. EXPLAIN (ANALYZE, WAL) đo gì?

`WAL` trong `EXPLAIN` báo những chỉ số **WAL generation** trong phạm vi thực thi được instrument.

Lệnh:

```sql
EXPLAIN (ANALYZE, WAL)
SELECT 1;
```

trên SELECT đơn giản có thể không tạo WAL đáng kể, nên các số WAL có thể bằng 0 hoặc không được hiển thị khi format text bỏ counter 0.

Để thấy WAL rõ hơn, dùng DML trên lab:

```sql
BEGIN;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS
)
UPDATE lesson_plan_metrics.sales
SET amount = amount + 1
WHERE sale_id BETWEEN 10 AND 20;

ROLLBACK;
```

**Lệnh UPDATE đã thực sự chạy.** `ROLLBACK` hoàn nguyên thay đổi dữ liệu thường của transaction, nhưng **không xóa các WAL records đã được tạo**; các byte WAL đó vẫn có thể được ghi ra và sau đó được tái chế theo cơ chế WAL.

### Lưu ý an toàn với EXPLAIN ANALYZE DML

`EXPLAIN (ANALYZE)` chạy:

- `INSERT`: thực sự tạo hàng.
- `UPDATE`: thực sự cập nhật hàng.
- `DELETE`: thực sự xóa hàng.
- Các trigger, checks và tác động transactional liên quan.

Bọc trong `BEGIN ... ROLLBACK` là phương pháp lab hữu ích nhưng **không hoàn nguyên mọi hiệu ứng ngoài transaction**, như:

- Giá trị sequence đã cấp từ `nextval()`.
- Email/HTTP request do application/extension gửi ra hệ ngoài.
- WAL đã phát sinh.
- Một số tác động ngoài database tùy extension.

Chỉ benchmark DML trên production nếu có cơ chế an toàn được phê duyệt; không giả định rollback triệt tiêu mọi chi phí.

## 20. Ba số WAL cơ bản

Ví dụ text output minh họa:

```text
WAL: records=250 fpi=16 bytes=180000
```

| Counter | Diễn giải |
|---|---|
| **`records`** | Số WAL records được tạo trong phạm vi instrumentation. |
| **`fpi`** | Số **full-page images** (*FPI*) được ghi trong các WAL records liên quan. |
| **`bytes`** | Số bytes WAL được tạo theo cách PostgreSQL ghi nhận cho hoạt động được đo. |

### Tại sao records không bằng rows?

Một UPDATE có thể:

- Tạo tuple version mới trong heap.
- Cập nhật một hoặc nhiều indexes.
- Tác động các page khác liên quan.
- Kích hoạt trigger thực hiện SQL khác.
- Thực hiện những thao tác storage riêng tùy HOT/non-HOT update.

Do đó `WAL records=250` **không có nghĩa đã sửa đúng 250 rows**, và `WAL bytes` cũng không tỷ lệ một-một với `amount` hoặc kích thước payload người dùng.

### WAL bytes không bằng độ tăng kích thước bảng

WAL là thông tin phục hồi/logging; data files và indexes có cách mở rộng, tái sử dụng không gian, VACUUM và checkpoint riêng. Một transaction tạo nhiều WAL có thể làm file bảng tăng ít, hoặc ngược lại tùy bối cảnh.

## 21. Full-Page Image (FPI) và checkpoint

Trong những cấu hình phổ biến, PostgreSQL có cơ chế **full-page writes** để bảo vệ trước trường hợp page ghi không hoàn chỉnh khi crash. Sau một checkpoint, lần thay đổi đầu tiên trên một số page có thể cần ghi **full-page image** vào WAL.

Hình dung:

```text
Checkpoint
     │
     ▼
Page P được thay đổi lần đầu
     │
     └── WAL có thể chứa FPI của P

Page P được sửa tiếp trong cùng giai đoạn
     │
     └── Có thể không cần thêm FPI cho mỗi sửa đổi
```

Kết quả:

- Hai lần UPDATE số hàng tương đương có thể có **`WAL FPI` và `WAL Bytes` khác nhau**.
- Khi workload nằm gần mốc checkpoint, số FPI có thể tăng.
- Nén WAL/FPI và những thiết lập về logging có thể ảnh hưởng số byte.

**Không tự kết luận thay đổi query làm WAL tệ hơn chỉ từ một lần EXPLAIN** nếu điều kiện checkpoint, cache và trạng thái bảng khác nhau.

### Full-page writes không phải bản sao toàn bộ database

FPI liên quan tới những page nhất định và điều kiện logging. Không suy ra `fpi=100` nghĩa PostgreSQL sao chép 100 bảng hoặc 100 transaction.

## 22. WAL khi INSERT, UPDATE và DELETE

Ba kiểu DML có mẫu WAL khác nhau:

### INSERT

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
INSERT INTO lesson_plan_metrics.sales (
    customer_id,
    sold_at,
    status,
    amount,
    note
)
VALUES (
    1,
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    'PAID',
    99.00,
    'EXPLAIN WAL demo'
);

ROLLBACK;
```

INSERT ghi tuple vào heap và duy trì các indexes liên quan. Trong lab có **identity sequence**; giá trị sequence được lấy có thể không quay lại khi transaction rollback.

### UPDATE

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE lesson_plan_metrics.sales
SET amount = amount * 1.05
WHERE customer_id = 42
  AND status = 'PAID';

ROLLBACK;
```

UPDATE có thể tạo tuple versions mới. Nếu update đủ điều kiện **HOT update** và có không gian phù hợp trên page, có thể tránh cập nhật một số indexes; ngược lại, cập nhật key/indexed columns hoặc không đủ điều kiện HOT có thể tăng chi phí WAL/index.

### DELETE

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
DELETE FROM lesson_plan_metrics.sales
WHERE customer_id = 42;

ROLLBACK;
```

DELETE đánh dấu tuple theo cơ chế MVCC; không nhất thiết giải phóng toàn bộ file dữ liệu ngay. `VACUUM` và các cơ chế thu hồi không gian diễn ra riêng.

### Đừng so sánh WAL Bytes một cách thiếu công bằng

INSERT 1 row, UPDATE 30 rows và DELETE 30 rows không phải cùng khối lượng công việc. Cần chuẩn hóa theo số rows, row width và cùng tình trạng dữ liệu khi so sánh.

## 23. WAL counters có thể phát sinh ở nhiều node

Kế hoạch UPDATE có thể có:

```text
Update on sales
  Buffers: shared hit=...
  WAL: records=... fpi=... bytes=...
  -> Bitmap Heap Scan on sales
       Buffers: shared hit=...
```

Những counters có thể xuất hiện tại các node khác nhau tùy phạm vi instrumentation và cấu trúc plan.

**Đừng cộng WAL counters từ mọi node** rồi coi đó là số records toàn statement, vì counters ở parent và descendants có thể bao gồm cùng hoạt động. Hãy phân tích node nào tạo WAL và dùng số liệu tổng hợp thích hợp.

### Trigger và chi phí phụ

Nếu bảng có trigger ghi audit hoặc cập nhật bảng khác, `EXPLAIN ANALYZE` thực thi trigger và có thể hiển thị thông tin trigger timing/calls theo phiên bản/plan.

Không mặc định WAL của một UPDATE chỉ đến từ heap tuple của một bảng chính. Index maintenance, trigger DML, toast và cấu trúc phụ có thể góp phần.

## 24. WAL từ SELECT: có nhất thiết bằng 0?

Truy vấn đọc thông thường thường **không tạo WAL chính cho thay đổi nghiệp vụ**, nhưng không nên xây rule cứng rằng **mọi SELECT luôn có WAL Bytes = 0**.

Trong PostgreSQL, có những cơ chế như cập nhật **hint bits** và điều kiện logging liên quan `wal_log_hints`/data checksums/full-page images khiến hoạt động đọc có thể kéo theo write/WAL đặc biệt theo bối cảnh. Những function được gọi trong SELECT cũng có thể có side effects nếu không thật sự read-only.

Do đó:

- `SELECT 1` thường không có WAL đáng kể.
- `SELECT` thông thường quét dữ liệu thường có WAL thấp hoặc 0.
- Không coi WAL khác 0 là bằng chứng duy nhất ứng dụng đã thực hiện `UPDATE` tường minh.

Điều quan trọng là hiểu **ngữ nghĩa query và cơ chế server**, không diễn giải một counter đơn độc.

## 25. WAL Bytes không phải network replication throughput

`WAL Bytes` của một EXPLAIN phản ánh hoạt động WAL trong phạm vi đo, **không trực tiếp bằng**:

- Byte truyền qua mạng của physical replication.
- Byte ứng dụng gửi tới database.
- Byte lưu thêm trên bảng/index.
- File size của `pg_wal` sau một thời điểm.
- Thời gian flush WAL để commit.

Replication có thể dùng compression, batching, retry, protocol overhead và ghi WAL từ nhiều transactions khác nhau. WAL files có vòng đời retention/recycling riêng.

### Vì sao cần phân biệt?

Một lần benchmark DML tạo 10 MiB WAL không có nghĩa replica luôn nhận đúng 10 MiB TCP payload ngay lập tức. Muốn đánh giá replication, cần các metrics riêng như WAL sender/receiver lag, LSN positions, network và write/flush/replay lag.

## 26. So sánh WAL với pg_stat_wal và pg_stat_statements

Khi cần bối cảnh rộng hơn:

- **`pg_stat_wal`** cung cấp thống kê WAL ở mức instance/cluster theo phiên bản hỗ trợ.
- **`pg_stat_statements`** (extension, nếu được cấu hình) có thể cung cấp counters WAL theo statement fingerprint/query được tổng hợp qua nhiều lần chạy.
- **`EXPLAIN (ANALYZE, WAL)`** cho số liệu gắn với **một lần thực thi đang instrument**, hữu ích để xem node và SQL cụ thể.

Ví dụ quan sát thống kê WAL toàn instance:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

View và cột có thể khác theo phiên bản server; không chạy công thức này trên server cũ khi chưa kiểm tra khả năng hỗ trợ.

### Không lấy hiệu pg_stat_wal làm WAL riêng của một query khi có concurrency

Nếu đo:

```text
wal_bytes_after - wal_bytes_before
```

trong hệ thống đang có hàng trăm session khác ghi đồng thời, kết quả là thay đổi **toàn instance** và không nhất thiết là WAL của một statement duy nhất.

`EXPLAIN WAL` phù hợp hơn cho việc nghiên cứu trực tiếp một statement, dù nó cũng không mô tả mọi chi phí background và các sự kiện ngoài executor.

## 27. WAL sau ROLLBACK vẫn đã được tạo

Một transaction:

```sql
BEGIN;
UPDATE lesson_plan_metrics.sales
SET note = note || '-edited'
WHERE sale_id BETWEEN 1 AND 100;
ROLLBACK;
```

không để lại thay đổi nghiệp vụ đã commit ở bảng, nhưng PostgreSQL vẫn có thể đã:

- Tạo tuple versions tạm thời trong quá trình thực thi.
- Ghi WAL cho những thao tác cần logging.
- Tiêu thụ buffer/cache/CPU/I/O.
- Tạo công việc cleanup cho VACUUM và hệ thống.

Đó là lý do không thể “benchmark UPDATE không mất chi phí” bằng cách chạy rồi rollback. Rollback bảo vệ **tính đúng đắn dữ liệu transactional** nhưng không đảo ngược mọi tài nguyên đã tiêu thụ.

### Benchmark DML trên production

Kể cả bọc ROLLBACK, DML có thể giữ locks và gây WAL/bloat ảnh hưởng hệ thống. Không dùng phương pháp đó trên bảng nóng mà không có điều kiện kiểm soát và phê duyệt.

## 28. SETTINGS cho biết điều gì?

`SETTINGS` trong EXPLAIN đưa ra những **configuration parameters ảnh hưởng planner** có giá trị khác **built-in defaults**.

Ví dụ:

```sql
EXPLAIN (SETTINGS)
SELECT *
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

Một output minh họa:

```text
Index Scan using ix_sales_customer_recent on sales ...
  Index Cond: (customer_id = 42)
Settings: work_mem = '64MB', random_page_cost = '1.1'
```

**Đây không phải output bắt buộc**: nếu các thiết lập tương ứng trùng built-in defaults, hoặc không thuộc nhóm được báo cáo, phần Settings có thể vắng mặt.

### Built-in default khác với giá trị mặc định môi trường

Nếu DBA đã đặt `random_page_cost=1.1` trong `postgresql.conf`, tham số này vẫn có thể được EXPLAIN SETTINGS hiển thị vì khác **built-in default**, dù mọi session của database đều kế thừa cấu hình ấy.

`SETTINGS` không có nghĩa “người chạy vừa dùng SET để đổi tham số”. Nó mô tả **giá trị hiệu lực có liên quan tại lúc tạo plan**, theo quy tắc báo cáo.

## 29. SETTINGS không phải SHOW ALL

`SHOW ALL` hoặc `pg_settings` có thể có hàng trăm GUC:

```sql
SHOW ALL;
```

`EXPLAIN (SETTINGS)` **không đưa mọi GUC** vào output.

Ví dụ:

- `work_mem`, `random_page_cost`, `enable_seqscan` có thể ảnh hưởng trực tiếp lựa chọn plan.
- `application_name` hữu ích cho monitoring nhưng không phải một planner cost parameter thông thường.
- `log_min_duration_statement` ảnh hưởng logging, không phải lựa chọn join method thông thường.

Không nhìn thấy `application_name` trong SETTINGS không có nghĩa session không có application name.

### Kiểm tra một GUC chính xác

```sql
SELECT
    name,
    setting,
    unit,
    source,
    boot_val,
    reset_val
FROM pg_catalog.pg_settings
WHERE name IN (
    'work_mem',
    'random_page_cost',
    'seq_page_cost',
    'effective_cache_size',
    'enable_seqscan',
    'max_parallel_workers_per_gather'
)
ORDER BY name;
```

Các cột giúp hiểu giá trị runtime, nguồn setting và giá trị tham chiếu, nhưng cách diễn giải built-in default/boot/reset cần tôn trọng ngữ nghĩa của từng GUC và phiên bản PostgreSQL.

## 30. SET LOCAL: thử cấu hình mà không làm bẩn session lâu dài

Một cách học rõ ràng là so sánh cùng SQL trong transaction với `SET LOCAL`:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT sale_id, note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

`SET LOCAL` có hiệu lực trong transaction hiện tại và được hoàn nguyên khi kết thúc transaction. Tương tự:

```sql
BEGIN;

SET LOCAL work_mem = '64MB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT sale_id, note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

So sánh:

1. Sort Method (in-memory/external merge).
2. Temp Read/Written Blocks.
3. Actual Rows/Loops.
4. Execution Time.
5. `SETTINGS` để xác nhận môi trường plan.

### Vì sao dùng SET LOCAL thay SET?

`SET` có thể tồn tại tới hết session nếu không reset. Trong connection pool, một thay đổi session setting không được quản lý đúng có thể ảnh hưởng request kế tiếp.

`SET LOCAL` giảm rủi ro rò rỉ setting qua transaction, nhưng cũng không thay thế việc transaction manager/pool reset connection state chính xác.

## 31. Thử enable_seqscan = off: công cụ học, không phải giải pháp mặc định

Đôi khi bạn muốn xem planner sẽ làm gì nếu hạn chế kế hoạch sequential scan:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT
    sale_id,
    customer_id
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;

ROLLBACK;
```

`enable_seqscan=off` **làm planner tránh ưu tiên seq scan khi có lựa chọn**, nhưng không có nghĩa tuyệt đối không thể xuất hiện Seq Scan trong mọi hoàn cảnh.

### Mục đích chính

Đây là thí nghiệm để:

- Xem có plan index nào khả dĩ.
- So sánh chi phí và buffer usage của alternative plan.
- Điều tra statistics/chi phí có thể khiến planner chọn khác mong đợi.

### Không dùng làm tuning chính thức một cách mù quáng

Tắt các plan methods toàn session có thể làm nhiều query khác chậm hơn. Nguyên nhân nên được giải quyết ở:

- Statistics, index design và predicate.
- Cost parameters phù hợp hardware.
- Query structure, filter selectivity và data skew.
- Runtime measurements đại diện.

`SETTINGS` giúp ghi lại thí nghiệm, không tự xác nhận plan được ép là tốt hơn.

## 32. random_page_cost, effective_cache_size và work_mem

Một số planner-relevant settings thường được điều tra:

| GUC | Ý nghĩa khái quát | Cần tránh |
|---|---|---|
| `seq_page_cost` | Chi phí tương đối cho sequential page access. | Diễn giải cost thành thời gian mili giây. |
| `random_page_cost` | Chi phí tương đối cho random page access. | Giảm tùy tiện để ép index scan mọi nơi. |
| `effective_cache_size` | Ước lượng lượng cache hữu ích planner có thể cân nhắc. | Hiểu là lượng RAM được PostgreSQL cấp phát ngay. |
| `work_mem` | Bộ nhớ cho một số tác vụ sort/hash. | Coi là giới hạn tổng bộ nhớ một session/query. |
| `max_parallel_workers_per_gather` | Giới hạn workers trong những plan parallel phù hợp. | Coi tăng luôn nhanh hơn. |
| `enable_hashjoin`, `enable_nestloop`... | Công tắc ảnh hưởng lựa chọn thuật toán join. | Dùng permanent khi chưa sửa nguyên nhân plan kém. |

**SETTINGS chỉ là bằng chứng về ngữ cảnh**, không chứng minh một giá trị GUC sai hay đúng. Muốn khuyến nghị thay đổi cần benchmark đại diện, thống kê và hiểu tải đồng thời.

## 33. SETTINGS khi dùng prepared statements

Ứng dụng Java thường dùng `PreparedStatement`. PostgreSQL có thể chọn **custom plan** hoặc **generic plan** trong những tình huống phù hợp, tùy cấu hình và số lần thực thi.

Ví dụ hai tenant:

```text
tenant_id = 1   → 1 triệu rows
tenant_id = 42  → 30 rows
```

Cùng SQL parameterized có thể có selectivity rất khác. Nếu plan thay đổi theo generic/custom behavior, việc so sánh:

```sql
EXPLAIN SELECT ... WHERE tenant_id = 42;
```

với SQL thực tế từ JDBC có thể không phản ánh chính xác cùng loại plan.

### Cách chẩn đoán

Kiểm tra SQL, parameters, driver/server prepared statement usage, statistics, `plan_cache_mode` và SETTING khác khi phù hợp. Không gán mọi sai khác cho `work_mem` chỉ vì nó là mục đầu tiên thấy trong SETTINGS.

`EXPLAIN EXECUTE prepared_statement(...)` có thể hữu ích khi bạn cần quan sát plan của prepared statement trên server theo giao diện phù hợp.

## 34. FORMAT JSON: vì sao cần?

TEXT plan rất hữu ích cho con người:

```text
Limit
  -> Index Scan
```

Nhưng một ứng dụng muốn so sánh 200 plans và phát hiện “truy vấn nào có temp writes > 100.000 blocks” sẽ khó parse text căn lề. `FORMAT JSON` trả cây plan ở dạng cấu trúc:

```sql
EXPLAIN (FORMAT JSON)
SELECT
    sale_id,
    amount
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

Một client thường nhận **một hàng kết quả** chứa giá trị JSON là một **mảng ở cấp cao nhất**, trong đó mỗi phần tử mô tả một statement explain.

### Lợi ích

- Không phải phân tích số khoảng trắng indent để xác định cây.
- Có key-value fields cho các counters.
- Có mảng `Plans` chứa các child nodes.
- Có thể lập trình tìm node theo `Node Type`.
- Dễ lưu kết quả giữa các benchmark và so sánh.
- Có thể kết nối với dashboard, CI hoặc tool phân tích SQL.

### Chi phí

- JSON dài và có nhiều keys.
- Schema output có thể thay đổi theo phiên bản/tùy chọn.
- Không phải tất cả trường đều luôn có.
- Tool phải diễn giải counters/loops/parallel đúng, không chỉ tính tổng naïve.

## 35. Cấu trúc JSON đầu ra

Một ví dụ **minh họa rút gọn, không phải số liệu đo trực tiếp từ lab**:

```json
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Startup Cost": 0.29,
      "Total Cost": 4.25,
      "Plan Rows": 5,
      "Plan Width": 22,
      "Actual Startup Time": 0.020,
      "Actual Total Time": 0.060,
      "Actual Rows": 5,
      "Actual Loops": 1,
      "Shared Hit Blocks": 4,
      "Shared Read Blocks": 2,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Index Name": "ix_sales_customer_recent",
          "Relation Name": "sales",
          "Alias": "sales",
          "Index Cond": "(customer_id = 42)",
          "Startup Cost": 0.29,
          "Total Cost": 40.0,
          "Plan Rows": 30,
          "Plan Width": 22,
          "Actual Startup Time": 0.018,
          "Actual Total Time": 0.055,
          "Actual Rows": 5,
          "Actual Loops": 1,
          "Shared Hit Blocks": 4,
          "Shared Read Blocks": 2
        }
      ]
    },
    "Settings": {
      "work_mem": "64MB"
    },
    "Planning Time": 0.150,
    "Execution Time": 0.085
  }
]
```

**Ghi chú:** Đây là JSON tổng hợp để giải thích shape. Những fields tùy chọn, số liệu và cách hiển thị Settings khác nhau theo query, cấu hình và version. Khi viết công cụ, phải chấp nhận key không xuất hiện.

### Các thành phần

| JSON path | Ý nghĩa |
|---|---|
| `[0]` | Phần tử đầu của mảng kết quả. |
| `[0].Plan` | Root plan node. |
| `Plan["Node Type"]` | Kiểu node: Seq Scan, Index Scan, Hash Join, Sort, Aggregate... |
| `Plan["Plans"]` | Mảng child plan nodes, nếu có. |
| `Plan["Actual Rows"]` | Số hàng thực tế theo cách PostgreSQL báo cáo khi ANALYZE. |
| `Plan["Actual Loops"]` | Số lần node được gọi/thực thi. |
| `Plan["Shared Hit Blocks"]` | Counter shared buffer hit, nếu được báo. |
| `[0].Settings` | Planner-relevant non-default GUCs khi SETTINGS bật và có dữ liệu. |
| `[0]["Planning Time"]` | Thời gian planning tính bằng ms khi được đo và xuất. |
| `[0]["Execution Time"]` | Thời gian execution tính bằng ms khi được đo và xuất. |

Các khóa chứa **dấu cách** và phân biệt hoa/thường. Khi sử dụng JavaScript/Python/Jackson phải truy cập đúng tên key.

## 36. FORMAT JSON không biến EXPLAIN thành truy vấn JSON trong FROM

Một hiểu nhầm:

```sql
-- Không phải cú pháp SQL PostgreSQL hợp lệ:
SELECT *
FROM (
    EXPLAIN (FORMAT JSON)
    SELECT * FROM lesson_plan_metrics.sales
) AS plan;
```

`EXPLAIN` là một utility command, không phải một subquery SELECT thông thường dùng trực tiếp ở `FROM`.

### Làm sao xử lý JSON?

- Client `psql` xuất kết quả sang file.
- Java/JDBC nhận giá trị ở column 1 của result set.
- Python/Go hoặc client khác lấy result rồi parse.
- Một monitoring tool thực thi EXPLAIN và lưu/cấu trúc kết quả.

Không cần cố nhét EXPLAIN vào CTE như một hàm SQL để có thể truy vấn JSON bằng `jsonb_path_query`.

## 37. Dạng JSON với BUFFERS, WAL và SETTINGS

Một lệnh đầy đủ:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT
    s.sale_id,
    s.amount
FROM lesson_plan_metrics.sales AS s
WHERE s.customer_id = 42;
```

Đầu ra có thể có:

```json
[
  {
    "Plan": {
      "Node Type": "Bitmap Heap Scan",
      "Relation Name": "sales",
      "Alias": "s",
      "Plan Rows": 30,
      "Actual Rows": 30,
      "Actual Loops": 1,
      "Shared Hit Blocks": 19,
      "Shared Read Blocks": 2,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "WAL Records": 0,
      "WAL FPI": 0,
      "WAL Bytes": 0
    },
    "Planning Time": 0.3,
    "Execution Time": 0.2
  }
]
```

Đây cũng là **cấu trúc minh họa**, không phải output thật: nếu PostgreSQL chọn Bitmap Heap Scan, thực tế thường còn có `Plans` chứa Bitmap Index Scan, cùng những trường khác. Mục đích ví dụ là cho thấy **tên keys**, không mô phỏng đầy đủ một plan.

### Khi không có WAL

Một số versions/formats có thể bỏ một số counters zero hoặc vẫn biểu diễn chúng là 0. Parser cần chấp nhận **missing field** và **numeric zero** mà không lẫn với lỗi truy xuất JSON.

### JSON của UPDATE

Nếu chạy EXPLAIN ANALYZE UPDATE, root node có thể là `ModifyTable`/`Update` hoặc node tương ứng tùy version, và WAL metrics thường rõ hơn. Không viết parser chỉ chấp nhận `Node Type = "Select"` vì đó không phải dạng cây EXPLAIN chuẩn.

## 38. Các khóa JSON thường gặp

| Nhóm | Ví dụ keys |
|---|---|
| Cấu trúc | `Node Type`, `Plans`, `Parent Relationship`, `Relation Name`, `Alias`, `Index Name`. |
| Ước lượng | `Startup Cost`, `Total Cost`, `Plan Rows`, `Plan Width`. |
| Thực tế | `Actual Startup Time`, `Actual Total Time`, `Actual Rows`, `Actual Loops`. |
| Filter | `Filter`, `Index Cond`, `Recheck Cond`, `Rows Removed by Filter`. |
| Shared buffers | `Shared Hit Blocks`, `Shared Read Blocks`, `Shared Dirtied Blocks`, `Shared Written Blocks`. |
| Local buffers | `Local Hit Blocks`, `Local Read Blocks`, `Local Dirtied Blocks`, `Local Written Blocks`. |
| Temp blocks | `Temp Read Blocks`, `Temp Written Blocks`. |
| WAL | `WAL Records`, `WAL FPI`, `WAL Bytes`. |
| Sort | `Sort Key`, `Sort Method`, `Sort Space Used`, `Sort Space Type`. |
| Parallel | `Workers Planned`, `Workers Launched`, `Workers`. |
| Cấu hình/summary | `Settings`, `Planning Time`, `Execution Time`, `Triggers`, `JIT` (nếu có). |

Đây không phải danh sách bất biến cho mọi major PostgreSQL version. Một số fields chỉ xuất hiện khi node/tùy chọn tương ứng có ý nghĩa.

### Không hardcode tất cả keys là bắt buộc

Một plan-only JSON không có actual timings. Một query không có sort không có `Sort Method`. Một plan không dùng parallel workers không có `Workers`. Khi `SETTINGS` không có non-default planner settings được báo, `Settings` có thể không xuất hiện.

Tooling tốt sử dụng các phép đọc **optional** với default/nullable hợp lý, nhưng cũng cần lưu ý không nhầm 0 với “không đo”.

## 39. Xuất JSON từ psql

Trong `psql`, để lưu kết quả `FORMAT JSON` mà không có khung bảng, có thể cấu hình output:

```text
\pset format unaligned
\pset tuples_only on
\o explain-plan.json
```

Sau đó:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT
    sale_id,
    amount
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

Rồi trong `psql`:

```text
\o
```

`\o explain-plan.json` chuyển output query sang file; `\o` không đối số đưa output về terminal. Với định dạng unaligned và tuples-only, output một giá trị JSON có thể được lưu mà không bị bao thêm header/khung cột của psql.

### Lưu ý khi chạy qua script

- Các dòng bắt đầu `\` là **psql meta-commands**, không phải SQL cho JDBC.
- Tên file/đường dẫn là local phía client chạy `psql`.
- Cần đảm bảo không có output statement khác chen vào cùng file.
- Kiểm tra file JSON bằng JSON parser thay vì chỉ nhìn extension `.json`.
- Nếu có nhiều statements hoặc output khác, việc nối nhiều JSON documents có thể không phải một JSON document hợp lệ.

### Cách đọc trên terminal

Để quay lại output bình thường:

```text
\pset format aligned
\pset tuples_only off
```

Thiết lập đúng tùy nhu cầu. Đừng quên reset nếu tiếp tục dùng cùng session cho những query khác.

## 40. Đọc EXPLAIN FORMAT JSON bằng Java/JDBC

Java rất phù hợp để lấy một result set JSON và phân tích qua Jackson.

Ví dụ phương thức minh họa (giả định đã có Jackson trong classpath):

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import com.fasterxml.jackson.core.JsonProcessingException;

public final class ExplainReader {
    private static final ObjectMapper JSON = new ObjectMapper();

    public static void inspect(Connection connection, int customerId)
            throws SQLException, JsonProcessingException {
        String sql = """
            EXPLAIN (
                ANALYZE,
                BUFFERS,
                WAL,
                SETTINGS,
                FORMAT JSON
            )
            SELECT sale_id, amount
            FROM lesson_plan_metrics.sales
            WHERE customer_id = ?
            """;

        try (PreparedStatement statement =
                connection.prepareStatement(sql)) {
            statement.setInt(1, customerId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("EXPLAIN did not return a row");
                }

                String json = rs.getString(1);
                JsonNode document = JSON.readTree(json);
                JsonNode root = document.path(0);
                JsonNode plan = root.path("Plan");

                String nodeType =
                    plan.path("Node Type").asText("<unknown>");

                long sharedHits =
                    plan.path("Shared Hit Blocks").asLong(0L);

                long sharedReads =
                    plan.path("Shared Read Blocks").asLong(0L);

                double executionMs =
                    root.path("Execution Time").asDouble(Double.NaN);

                System.out.printf(
                    "Node=%s, hits=%d, reads=%d, executionMs=%s%n",
                    nodeType, sharedHits, sharedReads,
                    Double.toString(executionMs)
                );
            }
        }
    }
}
```

### Giải thích

1. `PreparedStatement` truyền `customer_id` như parameter, không ghép giá trị vào SQL string.
2. `EXPLAIN (FORMAT JSON)` trả một cột chứa JSON; `ResultSet.getString(1)` lấy biểu diễn chuỗi để parser xử lý.
3. Root JSON là mảng, nên lấy phần tử đầu bằng `document.path(0)`.
4. `Plan` là root plan node.
5. `Shared Hit Blocks` và `Shared Read Blocks` là keys chứa dấu cách.
6. `Execution Time` có thể không có nếu không dùng `ANALYZE` hoặc tùy chọn hiển thị; mẫu code dùng `Double.NaN` khi thiếu.

**Mẫu này chỉ nên dùng để phân tích SELECT lab hoặc truy vấn an toàn.** Đừng cho client gửi tùy ý SQL để ứng dụng bọc `EXPLAIN ANALYZE` rồi thực thi trên production.

### Parser khác với validator

`asLong(0)` tiện khi hiển thị, nhưng trong hệ thống đánh giá hiệu năng tự động, **thiếu counter** không luôn tương đương **đã đo và bằng 0**. Nên có model kiểu `OptionalLong` hoặc cờ `metricPresent` nếu cần phân biệt hai tình trạng.

## 41. Duyệt cây Plans đệ quy trong Java

Một plan có thể là:

```text
Aggregate
   └── Hash Join
         ├── Seq Scan sales
         └── Hash
              └── Seq Scan customers
```

Mỗi node con nằm trong mảng `Plans`. Để tìm toàn bộ Sort nodes, có thể duyệt đệ quy:

```java
import com.fasterxml.jackson.databind.JsonNode;

public static void visitPlan(JsonNode plan, int depth) {
    if (plan == null || plan.isMissingNode()) {
        return;
    }

    String nodeType =
        plan.path("Node Type").asText("<unknown>");

    String indent = "  ".repeat(Math.max(depth, 0));

    System.out.println(indent + nodeType);

    if ("Sort".equals(nodeType)) {
        String sortMethod =
            plan.path("Sort Method").asText("<not reported>");
        System.out.println(indent + "  method=" + sortMethod);
    }

    JsonNode children = plan.path("Plans");
    if (children.isArray()) {
        for (JsonNode child : children) {
            visitPlan(child, depth + 1);
        }
    }
}
```

Đây là phương thức minh họa, có thể đặt trong một class Java ở dự án đã có Jackson. Gọi:

```java
visitPlan(document.path(0).path("Plan"), 0);
```

### Điều không nên làm

Không tự động:

```java
totalSharedReads += plan.get("Shared Read Blocks").asLong();
```

ở **mọi node** rồi cho rằng đó là reads duy nhất của toàn statement. Như đã nêu, counters có thể tích lũy/bao gồm child; cần thiết kế phép tổng hợp dựa vào ngữ nghĩa metrics và phạm vi node.

## 42. So sánh hai plan JSON

Khi benchmark trước/sau thay đổi index, thường muốn so:

- Root node type và cấu trúc con.
- Số hàng ước lượng và thực tế.
- Loops của các nested-loop children.
- Shared hit/read.
- Temp read/write và sort method.
- WAL records/FPI/bytes nếu query ghi.
- Planner settings.
- Planning Time/Execution Time.

Một record kết quả có thể là:

```json
{
  "scenario": "customer-42-top-5",
  "postgres_major": 17,
  "iteration": 3,
  "metrics": {
    "execution_ms": 0.58,
    "shared_hit_blocks": 15,
    "shared_read_blocks": 1,
    "temp_written_blocks": 0,
    "wal_bytes": 0
  }
}
```

Đây là **schema benchmark tự thiết kế**, không phải JSON nguyên mẫu của PostgreSQL. Khi lưu dữ liệu, đừng quên metadata để có thể tái hiện:

- SQL và parameters (được redact khi chứa dữ liệu nhạy cảm).
- PostgreSQL major/minor version.
- Isolation level, transaction/connection mode.
- Relevant planner settings.
- Kích thước dữ liệu và thời điểm ANALYZE.
- Warm/cold cache context.
- Thời gian chạy và tác động workload song song.

### So sánh số liệu có ý nghĩa

Nếu query A nhanh 5 ms và query B nhanh 4 ms ở một lần chạy, chưa đủ kết luận B tốt hơn 20%. Cần nhiều lần đo, sự biến động và workload đại diện.

## 43. JSON keys không phải API bất biến qua mọi version

Các phiên bản PostgreSQL có thể thêm trường mới, đổi cách trình bày chi tiết hoặc mở rộng instrumentation.

Ví dụ các nhóm thông tin có thể khác:

- Chi tiết I/O timing.
- Các thuộc tính parallel workers.
- Node types mới hoặc thêm thuộc tính của plan nodes.
- JIT instrumentation.
- Memory/accounting fields.
- Các kế hoạch cho công nghệ scan mới.

Vì vậy:

1. Lưu version PostgreSQL cùng JSON.
2. Parser đọc fields quan trọng theo tên và cho phép thiếu field tùy chọn.
3. Không phụ thuộc **thứ tự keys** trong object JSON.
4. Không coi các số numeric luôn được serialize với cùng số chữ số thập phân.
5. Dùng tree traversal qua `Plans` thay vì đọc một vài vị trí cố định.
6. Kiểm tra lại tool khi upgrade PostgreSQL major version.

### Một node có thể có nhiều child roles

`Parent Relationship` có thể biểu thị `Outer`/`Inner` hoặc vai trò khác theo loại node. Không assume một join luôn có đúng hai children với thứ tự cố định nếu bạn xây hệ thống phân tích tổng quát.

## 44. SETTINGS và JSON trong cùng một lệnh

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT
    sale_id,
    note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

Khi value `work_mem` khác built-in default và được báo cáo, JSON top-level có thể có:

```json
"Settings": {
  "work_mem": "64kB"
}
```

Đoạn trên là **fragment bên trong một object JSON**, không phải JSON document độc lập hợp lệ vì đang hiển thị một property. Để tạo JSON hợp lệ, nó phải nằm trong dấu `{ ... }`.

### Giá trị SETTINGS là string?

Trong output JSON, các setting values thường được biểu diễn ở dạng chuỗi cấu hình như `"64kB"` hoặc `"off"`. Parser không nên gán mặc định mọi value thành `int`; cần hiểu đơn vị và kiểu GUC khi so sánh.

### Không nhầm SETTINGS với SQL statement

`SETTINGS` không phát lại lệnh `SET LOCAL` đã chạy, cũng không hiển thị lịch sử thay đổi settings. Nó là thông tin của **bối cảnh planning** hiện tại.

## 45. Kịch bản 1: đọc nhiều shared blocks vì sequential scan

Ví dụ:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS
)
SELECT COUNT(*)
FROM lesson_plan_metrics.sales
WHERE note LIKE '%999%';
```

Index B-tree trên `customer_id` không hỗ trợ trực tiếp predicate chứa substring `'%999%'` ở note, nên planner có thể chọn `Seq Scan`.

Một kết quả có thể:

```text
Seq Scan on sales
  Filter: (note ~~ '%999%'::text)
  Rows Removed by Filter: ...
  Buffers: shared hit=... read=...
```

### Hướng điều tra

1. Mục đích query là tìm **substring** hay prefix?
2. Có cần hỗ trợ tìm kiếm text bằng `pg_trgm`/GIN/GiST hoặc full-text search?
3. Bảng và predicate selectivity ra sao?
4. Có index phù hợp workload thực không?
5. Khối lượng page accesses có tỷ lệ hợp lý với rows cuối cùng không?

**Không tự tạo index B-tree trên note chỉ vì Seq Scan hiện trong plan.** Chỉ mục cần phù hợp operator/predicate và workload.

## 46. Kịch bản 2: Nested Loop nhiều lần lookup

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    s.sale_id
FROM lesson_plan_metrics.customers AS c
JOIN lesson_plan_metrics.sales AS s
  ON s.customer_id = c.customer_id
WHERE c.customer_id <= 50;
```

Planner có thể chọn Nested Loop hoặc Hash Join tùy statistics/costs.

Nếu Nested Loop:

```text
Nested Loop
  -> Index Scan customers ...
  -> Index Scan sales ... (loops=50)
```

### Diễn giải

- Một child được gọi nhiều lần theo rows outer.
- Shared Hit Blocks có thể tăng vì tái truy cập index pages.
- Không nên cộng time giữa parent và inner child một cách trực tiếp.
- Một plan dùng nhiều random lookups có thể phù hợp khi outer rất nhỏ, không phù hợp khi outer hàng triệu rows.

**Đừng coi Nested Loop là lỗi.** Nó có thể là thuật toán tối ưu cho lookup/selective join.

## 47. Kịch bản 3: Sort spill xuống file tạm

Query:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    FORMAT TEXT
)
SELECT sale_id, note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);

ROLLBACK;
```

Dấu hiệu:

```text
Sort Method: external merge
Disk: ...
Buffers: temp read=... written=...
```

### Câu hỏi cần giải quyết

- Có thực sự cần sort tất cả rows không?
- Có `LIMIT` có thể thay cách xử lý không?
- Có index phù hợp `ORDER BY`/`WHERE` không?
- Có phải sort trên expression không được index?
- `work_mem` quá thấp với workload này không?
- Truy vấn chạy đồng thời bao nhiêu bản và có đủ RAM không?

Trước khi thay đổi setting toàn server, thử **SET LOCAL** ở transaction lab để đo. Nhớ rằng tăng work_mem có thể làm nhiều hoạt động cùng tiêu tốn RAM.

## 48. Kịch bản 4: HashAggregate/Hash Join spill

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) AS sales_count,
    SUM(amount) AS total_amount
FROM lesson_plan_metrics.sales
GROUP BY customer_id
ORDER BY total_amount DESC;
```

Planner có thể chọn HashAggregate, GroupAggregate hoặc một tổ hợp sort/aggregate khác.

Khi hash-based operations cần nhiều memory, PostgreSQL có thể dùng nhiều batch hoặc spilling. Tùy phiên bản/node, plan có thể báo:

```text
HashAggregate
  Batches: ...
  Memory Usage: ...
  Disk Usage: ...
  Buffers: temp read=... written=...
```

### Đừng nhầm hai nguyên nhân

Một query có thể:

- Sort cuối theo `total_amount DESC`.
- Hash aggregate theo `customer_id`.

Temp blocks có thể đến từ **một hoặc cả hai**. Đọc **node-level** Sort/HashAggregate và các chi tiết Memory/Disk, không chỉ xem root.

Nếu estimates về số groups sai nghiêm trọng, planner có thể chọn chiến lược không tối ưu. Cần kiểm tra statistics, data skew và query design, không chỉ tăng `work_mem`.

## 49. Kịch bản 5: UPDATE tạo WAL cao

```sql
BEGIN;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS
)
UPDATE lesson_plan_metrics.sales
SET note = note || '-changed'
WHERE sale_id BETWEEN 1 AND 1000;

ROLLBACK;
```

Khi thấy WAL cao, hãy xét:

- Bao nhiêu rows thật sự bị sửa?
- Những indexed columns có bị thay đổi không?
- Update có đủ điều kiện HOT không?
- Row trở nên dài hơn, tạo/chuyển TOAST data hay không?
- Checkpoint/FPI ảnh hưởng thế nào?
- Trigger audit có chạy không?
- Có cần update những hàng không thay đổi giá trị không?

### Tránh UPDATE vô ích

Nếu ứng dụng thường gửi:

```sql
UPDATE table_name
SET status = 'PAID'
WHERE id = ?;
```

ngay cả khi status đã `PAID`, PostgreSQL vẫn có thể tạo phiên bản mới cho một UPDATE thành công, làm tăng bloat/WAL tùy trường hợp.

Có thể cân nhắc:

```sql
UPDATE table_name
SET status = 'PAID'
WHERE id = ?
  AND status IS DISTINCT FROM 'PAID';
```

Đây là mẫu tổng quát với bảng `table_name` chưa tạo. Chỉ áp dụng khi semantics thực sự cho phép bỏ update không đổi; một số nghiệp vụ/trigger dựa vào việc mọi update đều được ghi nhận.

## 50. Kịch bản 6: Chỉ thấy SETTINGS khác nhau

Hai môi trường chạy cùng SQL:

```text
Environment A
  Settings: work_mem = '4MB'
  Sort Method: external merge
  temp written=...

Environment B
  Settings: work_mem = '64MB'
  Sort Method: quicksort
  temp written=0
```

Một giả thuyết hợp lý: `work_mem` khác nhau góp phần thay đổi Sort Method và temp I/O.

Nhưng nếu A/B cũng khác hardware, dataset, version và cache, **không thể khẳng định nguyên nhân duy nhất** là work_mem. Muốn phân tích nhân quả, thay từng yếu tố và giữ các yếu tố còn lại có thể so sánh.

### SETTINGS là chứng cứ chứ không phải giải pháp

Nó giúp xác nhận biến môi trường có ảnh hưởng planner và khác built-in defaults. Chỉ dựa vào SETTINGS không thể kết luận plan ước lượng đúng/sai hoặc số lượng buffer tối ưu.

## 51. Kịch bản 7: Planning Time tăng

Nếu:

```text
Planning Time: 20.0 ms
Execution Time: 2.0 ms
```

thì phần planning đáng chú ý so với executor.

Cần xét:

- Query join nhiều bảng và có nhiều phương án join.
- Partitioned table có nhiều partitions.
- Metadata/catalog cache chưa ấm.
- Phân bố statistics và planner search complexity.
- Prepared statement plan reuse/generic plan.
- Extension planner hooks hoặc môi trường liên quan.

**BUFFERS của phần Planning** có thể cho thấy metadata page accesses, nhưng không đo tất cả CPU time cho việc tìm kiếm plan.

### Vì sao không bỏ qua Planning Time?

Ứng dụng có thể chạy một query ngắn hàng nghìn lần mỗi giây. Khi mỗi lần phải lập kế hoạch lại, planning cost có thể là phần đáng kể tổng chi phí server. Cần phân biệt với execution bottleneck trước khi thêm index.

## 52. Kịch bản 8: Execution Time cao nhưng buffers thấp

Giả sử query dùng một expensive function:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id,
    md5(repeat(note, 10))
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

Nếu buffer accesses ít mà time lớn, CPU biểu thức hoặc các bước khác có thể chiếm ưu thế. Với hàm đơn giản trên data nhỏ, ví dụ có thể vẫn rất nhanh; chỉ là mô hình minh họa.

### Các câu hỏi

- Function được gọi bao nhiêu lần?
- `Rows Removed by Filter` có lớn không?
- Có phải chỉ trả ít rows nhưng xử lý nhiều rows trước đó?
- Có JIT compilation overhead?
- Có chờ lock/IO/network mà EXPLAIN chưa giải thích?

Không luôn giải quyết bằng thêm RAM hoặc index.

## 53. EXPLAIN với TIMING OFF

Trong các truy vấn rất nhanh nhưng có hàng triệu node invocations, việc đo đồng hồ ở từng node có thể tạo overhead đáng kể.

```sql
EXPLAIN (
    ANALYZE,
    TIMING OFF,
    BUFFERS,
    WAL,
    SETTINGS
)
SELECT COUNT(*)
FROM lesson_plan_metrics.sales;
```

Khi `TIMING OFF`:

- PostgreSQL vẫn thực thi statement và thu thập những counters được hỗ trợ như rows/loops.
- Thời gian **riêng từng plan node** có thể không được hiển thị.
- Tổng `Execution Time` vẫn có thể được đo để hiển thị khi summary được bật.
- Giảm một phần overhead do đo per-node timing, giúp benchmark thực tế hơn trong một số trường hợp.

### Không hiểu TIMING OFF là ANALYZE OFF

`ANALYZE` vẫn thực thi query. `TIMING OFF` chỉ thay đổi instrumentation về thời gian, không biến UPDATE thành thao tác giả lập.

### Khi nào nên dùng?

Khi bạn quan tâm tới **row counts, buffer usage, WAL counts và tổng thời gian** nhưng không cần per-node timings cho lượt đo đó.

## 54. COSTS OFF và SUMMARY OFF

Để làm output gọn hơn:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    COSTS OFF,
    FORMAT TEXT
)
SELECT *
FROM lesson_plan_metrics.sales
WHERE customer_id = 42;
```

`COSTS OFF` ẩn các trường ước lượng như cost/rows/width ở format được hỗ trợ, **không đổi phép tính của planner**.

`SUMMARY OFF` có thể ẩn phần summary:

```sql
EXPLAIN (
    ANALYZE,
    SUMMARY OFF,
    BUFFERS
)
SELECT 1;
```

Khi so sánh tự động, đừng tắt trường mà công cụ cần. Mục đích của các tùy chọn trình bày là kiểm soát output/instrumentation, không thay thế việc chọn kế hoạch tốt.

## 55. FORMAT JSON, YAML, XML, TEXT

PostgreSQL hỗ trợ nhiều kiểu output cho `EXPLAIN`:

```sql
EXPLAIN (FORMAT TEXT) SELECT 1;
EXPLAIN (FORMAT JSON) SELECT 1;
EXPLAIN (FORMAT YAML) SELECT 1;
EXPLAIN (FORMAT XML) SELECT 1;
```

| Format | Phù hợp |
|---|---|
| TEXT | Đọc nhanh bằng mắt, terminal, báo cáo sự cố. |
| JSON | Lập trình, trích xuất counters, so sánh có cấu trúc. |
| YAML | Cấu trúc dễ đọc thủ công trong workflow dùng YAML. |
| XML | Hệ thống tích hợp có công cụ XML. |

Khi yêu cầu là **phân tích bằng Java/Jackson**, JSON thường tiện vì phổ biến và biểu diễn tự nhiên thành cây.

### Chuyển format không làm đổi bản chất query

`FORMAT JSON` chỉ thay cách hiển thị, không tự làm query nhanh hơn hay giảm WAL. Việc bật `ANALYZE`, `BUFFERS`, `WAL` có thể tạo overhead instrumentation độc lập với định dạng trình bày.

## 56. Đọc plan nhiều tầng từ JSON

Ví dụ cấu trúc:

```json
[
  {
    "Plan": {
      "Node Type": "Nested Loop",
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Relation Name": "customers"
        },
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Inner",
          "Relation Name": "sales",
          "Actual Loops": 50
        }
      ]
    }
  }
]
```

Đây là JSON rút gọn để minh họa cấu trúc, không phải một full EXPLAIN output thực.

Một tool cần duyệt:

1. Root object `[0]`.
2. `Plan`.
3. Từng `Plans[i]`.
4. Đệ quy mọi children có `Plans`.

### Không chỉ tìm node bằng mảng vị trí

Nếu hôm nay plan là:

```text
Nested Loop
  ├── Index Scan
  └── Index Scan
```

nhưng sau ANALYZE planner chọn:

```text
Hash Join
  ├── Seq Scan
  └── Hash
       └── Seq Scan
```

thì `Plans[1]` không còn chỉ cùng một node logic. Tool nên định danh node theo **type, relation, index, role và vị trí trong cây** khi cần so sánh chi tiết, không dựa vào một đường dẫn cứng cố định.

## 57. Dữ liệu JSON có thể nhạy cảm

Plan JSON có thể chứa:

- Tên schema, bảng, index và cột.
- Filter condition với một số literal values.
- Query structure/SQL expressions.
- Số hàng/thời gian có thể tiết lộ quy mô dữ liệu.
- Settings cho biết cấu hình server.

Vì vậy:

- Không đưa plan JSON nguyên vẹn vào log công khai khi có dữ liệu nhạy cảm.
- Redact literal/PII trước khi gửi bên ngoài tổ chức.
- Giới hạn quyền đọc/thu thập và thời gian lưu.
- Kiểm tra mục tiêu bảo mật khi dùng công cụ phân tích SQL bên thứ ba.

`FORMAT JSON` giúp tự động hóa, nhưng cũng khiến việc thu thập toàn bộ cấu trúc database trở nên rất dễ; cần quản trị tương xứng.

## 58. Không dùng EXPLAIN ANALYZE như câu lệnh health check thường xuyên

Một request health check chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE important_table
SET value = value + 1
WHERE id = 1;
```

là thiết kế sai. Nó **thực sự UPDATE** và gây side effects.

Ngay cả trên SELECT lớn, EXPLAIN ANALYZE:

- Chạy query thật, có thể tốn CPU/I/O.
- Có overhead đo lường.
- Có thể tạo temp files hoặc ảnh hưởng cache.
- Có thể giữ locks/snapshot phù hợp với statement.

Không đưa lệnh EXPLAIN ANALYZE của truy vấn nặng vào request health check tần suất cao. Dùng metrics, sampling và diagnostic access có kiểm soát.

## 59. EXPLAIN, pg_stat_statements và auto_explain

Ba công cụ có mục tiêu khác nhau:

### EXPLAIN

Cho plan của **một SQL** khi bạn chủ động yêu cầu. Với ANALYZE, đo **một lần thực thi**.

### pg_stat_statements

Extension (khi đã được cài/config) thu thập thống kê aggregate cho các statement fingerprints qua **nhiều lần thực thi**:

- Số lần gọi.
- Tổng/trung bình thời gian theo những counters được hỗ trợ.
- Buffer hits/reads và một số metrics WAL theo phiên bản.

Nó giúp tìm “SQL nào đang tiêu thụ nhiều thời gian tổng thể”, nhưng không thay thế cây plan chi tiết.

### auto_explain

Extension/tooling có thể ghi execution plans của những câu SQL đạt ngưỡng thời gian vào log, với cấu hình phù hợp.

**Cảnh báo:** Bật `auto_explain.log_analyze` hoặc các tùy chọn instrumentation khác có overhead đáng kể tùy workload. Không bật tràn lan trên production mà không đánh giá log volume, performance và mức lộ thông tin query.

### Workflow phổ biến

```text
Quan sát latency/pg_stat_statements
            │
            ▼
Chọn query cần điều tra
            │
            ▼
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)
trong môi trường phù hợp
            │
            ▼
Lưu FORMAT JSON, so sánh qua nhiều lần chạy
            │
            ▼
Thay đổi index/query/settings có kiểm soát
            │
            ▼
Đo lại và xác nhận trong workload thật
```

## 60. EXPLAIN không tự đo lock wait history

Một query có thể chậm vì chờ lock:

```sql
UPDATE lesson_plan_metrics.sales
SET amount = amount + 1
WHERE sale_id = 42;
```

Nếu transaction khác giữ lock xung đột, UPDATE phải đợi. `EXPLAIN ANALYZE` có thể phản ánh elapsed time của statement nhưng không tự cung cấp một **wait-for graph** đầy đủ.

Để xác định blocker đang hoạt động:

```sql
SELECT
    a.pid,
    a.wait_event_type,
    a.wait_event,
    pg_catalog.pg_blocking_pids(a.pid) AS blockers
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

### Phân biệt

- Nhiều shared reads + I/O timing cao: giả thuyết bottleneck I/O.
- Temp writes lớn: giả thuyết spill sort/hash.
- Query chờ `Lock`: cần tìm blocker và transaction lifecycle.
- Buffers/WAL thấp nhưng time cao: cân nhắc CPU, function, JIT hoặc loại wait khác.

Không đòi `BUFFERS` tự trả lời câu hỏi mà nó không đo.

## 61. Một runbook chẩn đoán chậm từ EXPLAIN

Khi gặp query chậm:

**Bước 1 — Tìm đúng SQL và parameter.** Đảm bảo EXPLAIN đang chạy query tương đương request thật, không phải query giả khác selectivity.

**Bước 2 — Kiểm tra execution safety.** Nếu DML, tạo môi trường lab/dataset clone hoặc transaction có phương án rollback và hiểu side effects.

**Bước 3 — Lấy plan-only khi cần.** Dùng `EXPLAIN (SETTINGS, FORMAT JSON)` nếu chưa thể thực thi.

**Bước 4 — Lấy actual metrics khi được phép.** Dùng `EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)`.

**Bước 5 — Nhìn actual vs estimated rows.** Sai lệch lớn có thể kéo theo chọn join/scan/sort không phù hợp.

**Bước 6 — Đọc BUFFERS.** Phân loại shared hits/reads, local buffers và temp spills, chú ý counters tích lũy.

**Bước 7 — Đọc WAL nếu là DML.** Xem records, FPI, bytes, row counts, indexes/triggers và ảnh hưởng checkpoint.

**Bước 8 — Đọc SETTINGS.** So sánh runtime configuration với môi trường đối chứng, không nhầm với SHOW ALL.

**Bước 9 — Đối chiếu thời gian.** Execution Time, Planning Time, I/O timings, lock waits, JIT, CPU và workload đồng thời.

**Bước 10 — Thực hiện một thay đổi có kiểm soát.** Index, statistics, query rewrite hoặc tham số phù hợp, rồi benchmark lại nhiều lần.

**Bước 11 — Đánh giá chi phí toàn hệ thống.** Index mới có thể tăng chi phí ghi/WAL; work_mem mới có thể tăng RAM dưới concurrency; một query nhanh hơn không được đổi lấy hệ thống kém ổn định.

**Bước 12 — Lưu bằng chứng.** Lưu plan JSON cùng SQL fingerprint, version, settings, dataset và kết quả đo.

## 62. Mẫu báo cáo benchmark có thể tái hiện

Một nhóm vận hành có thể ghi:

| Thông tin | Trước | Sau |
|---|---|---|
| SQL fingerprint | `sales-by-customer` | `sales-by-customer` |
| Query parameters | customer_id=42 | customer_id=42 |
| PostgreSQL version | Cùng version | Cùng version |
| Dataset rows | 30.000 | 30.000 |
| Plan root | Bitmap Heap Scan | Index Scan |
| Execution Time | 4,2 ms | 0,8 ms |
| Shared Hit Blocks | 200 | 12 |
| Shared Read Blocks | 60 | 2 |
| Temp Written Blocks | 0 | 0 |
| WAL Bytes | 0 | 0 |
| Settings | Đã lưu | Đã lưu |

**Số liệu trong bảng chỉ là ví dụ hư cấu.** Muốn công bố kết quả thật cần đo trên môi trường có thể so sánh, lưu nhiều lần chạy và ghi lại sự biến động.

### Không chỉ báo cáo một số “nhanh hơn 5 lần”

Nếu query chạy một lần dưới cache lạnh và một lần sau cache ấm, chênh lệch không nhất thiết đến từ index mới. Một benchmark tốt ghi **cache context**, runs warm-up, median/percentiles và lượng workload đồng thời.

## 63. Những lỗi thường gặp khi đọc BUFFERS

### 63.1. “Shared read=1000 nghĩa SSD đã đọc 1000 lần”

Không nhất thiết. Page có thể từ OS page cache, và số lần nạp buffer không phải số disk I/O requests vật lý.

### 63.2. “Shared hit=100000 chứng minh index tốt”

Không. Có thể query đang quét/tái truy cập quá nhiều page. So sánh với rows cuối, loops và plan khác.

### 63.3. “hit + read là số pages duy nhất”

Không. Page accesses có thể lặp lại.

### 63.4. “shared written=0 nghĩa query không ghi”

Không. Backend có thể dirty pages, tạo WAL, và page được checkpointer/background writer ghi sau.

### 63.5. “dirtied bằng số rows UPDATE”

Không. Một page chứa nhiều tuples; index/visibility data cũng có thể thay đổi.

### 63.6. “Local buffer chính là temp spill”

Không. Local buffers phục vụ temporary relations; temp blocks thường là working files của executor.

### 63.7. “Cộng BUFFERS của mọi plan node là tổng blocks”

Không. Parent và child có thể phản ánh cùng activity, dẫn tới double-counting.

### 63.8. “Temp writes >0 thì chỉ cần tăng work_mem”

Không. Cần kiểm tra Sort/Hash node, data volume, query rewrite, indexes và memory concurrency.

### 63.9. “Planning Buffers là data pages của bảng chính”

Không nhất thiết. Planner có thể đọc catalog/statistics metadata.

### 63.10. “Block size luôn 8192 ở mọi server”

Thường là 8KiB nhưng hãy kiểm tra `SHOW block_size` thay vì hardcode trong monitoring.

## 64. Những lỗi thường gặp khi đọc WAL

### 64.1. “WAL records bằng số rows”

Không. Một row update có thể tạo nhiều WAL records, tùy heap/index/TOAST/trigger.

### 64.2. “WAL bytes bằng số byte bảng tăng”

Không. WAL phục vụ crash recovery/replication, khác file size của table.

### 64.3. “ROLLBACK loại hết WAL đã sinh”

Không. WAL cho những thay đổi thực thi có thể đã được tạo dù transaction rollback.

### 64.4. “UPDATE tạo shared written=0 thì không có WAL”

Không. WAL và data page write là hai phạm vi riêng.

### 64.5. “FPI cao chỉ do query xấu”

Chưa chắc. Checkpoint timing, full_page_writes và compression/settings ảnh hưởng FPI.

### 64.6. “SELECT lúc nào WAL=0”

Không nên coi là quy tắc tuyệt đối do hint-bit/WAL conditions và function side effects.

### 64.7. “EXPLAIN WAL bằng bandwidth replica”

Không. WAL generation, WAL persistence và replication network throughput là các phép đo khác nhau.

### 64.8. “Tăng/giảm WAL của một lần chạy đủ kết luận tối ưu”

Không. Cần cùng số rows, index state, checkpoint, dataset và nhiều lần benchmark.

## 65. Những lỗi thường gặp với SETTINGS và JSON

### 65.1. “SETTINGS liệt kê mọi GUC”

Không. Nó tập trung vào những cài đặt ảnh hưởng planner và khác built-in defaults theo quy tắc PostgreSQL.

### 65.2. “Không thấy work_mem nghĩa work_mem không ảnh hưởng”

Không. Có thể setting trùng built-in default hoặc không được báo theo context; xem `SHOW work_mem` khi cần.

### 65.3. “SETTINGS khác nhau chắc chắn là nguyên nhân plan khác”

Chưa chắc. Statistics, dataset, server version và parameter selectivity cũng quan trọng.

### 65.4. “FORMAT JSON là object duy nhất ở top-level”

Output thông thường là **JSON array** chứa object có `Plan`.

### 65.5. “Plan JSON luôn có Actual Rows”

Không nếu không bật ANALYZE hoặc field không phù hợp.

### 65.6. “Root JSON luôn có Settings”

Không. Nó có thể vắng mặt nếu không có setting đủ điều kiện được báo.

### 65.7. “Field thiếu tương đương số 0”

Không trong mọi công cụ. Phân biệt counter không được thu thập và counter được đo nhưng bằng 0.

### 65.8. “JSON key order có ý nghĩa”

Không nên dựa vào thứ tự keys của JSON object để phân tích.

### 65.9. “Thứ tự children trong mọi plan luôn cố định qua version”

Không. Planner có thể chọn cây khác; parser phải duyệt cấu trúc.

### 65.10. “EXPLAIN FORMAT JSON có thể SELECT từ nó như bảng”

Không. `EXPLAIN` là utility command, cần client/tool lấy kết quả nếu muốn parse.

### 65.11. “FORMAT JSON tự làm query nhanh hơn”

Không. Nó thay output representation, còn chi phí instrument phụ thuộc tùy chọn khác.

### 65.12. “EXPLAIN ANALYZE chỉ kiểm tra, không thay đổi dữ liệu”

Sai nghiêm trọng với DML. Nó **thực thi** câu lệnh và trigger liên quan.

## 66. Bộ câu lệnh thực hành nhanh

Sau khi tạo schema và dữ liệu lab, có thể chạy lần lượt:

**A — Kế hoạch ước lượng:**

```sql
EXPLAIN (SETTINGS, FORMAT TEXT)
SELECT sale_id, sold_at
FROM lesson_plan_metrics.sales
WHERE customer_id = 42
ORDER BY sold_at DESC
LIMIT 5;
```

**B — Số liệu shared buffers:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at
FROM lesson_plan_metrics.sales
WHERE customer_id = 42
ORDER BY sold_at DESC
LIMIT 5;
```

**C — Temp spill dưới work_mem nhỏ:**

```sql
BEGIN;
SET LOCAL work_mem = '64kB';
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sale_id, note
FROM lesson_plan_metrics.sales
ORDER BY md5(sale_id::text);
ROLLBACK;
```

**D — WAL của UPDATE trong transaction lab:**

```sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE lesson_plan_metrics.sales
SET amount = amount + 1
WHERE sale_id BETWEEN 10 AND 20;
ROLLBACK;
```

**E — JSON để tool phân tích:**

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT customer_id, COUNT(*)
FROM lesson_plan_metrics.sales
GROUP BY customer_id;
```

**F — Tổng execution time ít overhead per-node timing hơn:**

```sql
EXPLAIN (
    ANALYZE,
    TIMING OFF,
    BUFFERS,
    WAL,
    SETTINGS,
    FORMAT JSON
)
SELECT COUNT(*)
FROM lesson_plan_metrics.sales;
```

Không dự đoán cứng node type hoặc exact counters; hãy đọc kết quả thực tế của server đang chạy.

## 67. Bài tập thực hành

### Bài 1 — EXPLAIN và EXPLAIN ANALYZE

Trên bảng sales, so sánh `EXPLAIN SELECT ...` với `EXPLAIN (ANALYZE) SELECT ...`. Các trường nào chỉ có khi câu lệnh thực thi thật? Tại sao không thể lấy cost=100 và hiểu là 100 ms?

### Bài 2 — BUFFERS cơ bản

Chạy `EXPLAIN (ANALYZE, BUFFERS)` lọc `customer_id=42`. Ghi các số `shared hit`, `shared read`. Chúng nói điều gì về PostgreSQL shared buffers và điều gì **không chứng minh** về SSD?

### Bài 3 — Lặp query và cache

Chạy cùng SELECT ba lần liên tiếp. So sánh shared hit/read và Execution Time; đề xuất hai nguyên nhân có thể dẫn đến sự khác biệt và cách kiểm soát benchmark.

### Bài 4 — Đọc block_size

Dùng `SHOW block_size` và quy đổi 1500 blocks sang KiB/MiB. Tại sao đó không phải dung lượng đọc đĩa vật lý chính xác?

### Bài 5 — Dirtied khác written

Chạy DML với `EXPLAIN (ANALYZE, BUFFERS, WAL)` trong transaction rollback. Giải thích tình huống `shared dirtied>0` nhưng `shared written=0`.

### Bài 6 — Local buffers

Tạo `TEMP TABLE` và dùng `EXPLAIN (ANALYZE, BUFFERS)` đọc nó. `local hit/read` khác `temp read/write` ở đâu?

### Bài 7 — Temp spill sort

Trong transaction, `SET LOCAL work_mem='64kB'` rồi sort 30.000 dòng theo `md5(sale_id::text)`. Tìm `Sort Method`, `Disk` và `temp read/write` nếu có.

### Bài 8 — work_mem cao hơn

Lặp bài 7 với `work_mem='64MB'`. So sánh plan, temp counters, execution time và lượng RAM; vì sao không nên tăng `work_mem` vô hạn trên nhiều kết nối đồng thời?

### Bài 9 — Node-level counters

Trong plan có Limit và Index Scan, cả hai báo shared hit/read giống nhau. Vì sao cộng các counters của hai node sẽ đếm trùng?

### Bài 10 — Nested Loop loops

Tìm một plan có Nested Loop; ghi `Actual Rows`, `Actual Loops` của inner child. Nếu rows=3 và loops=100, ước lượng tổng rows được tạo là bao nhiêu? Vì sao vẫn phải cẩn thận với rounding/parallel?

### Bài 11 — Parallel plan

Quan sát một plan có Gather/parallel scan nếu planner chọn. Phân biệt `Workers Planned` và `Workers Launched`. Vì sao không nhân BUFFERS của node với workers?

### Bài 12 — Planning Buffers

Trong plan có phần `Planning: Buffers`, giải thích chúng khác execution buffers. Planner có thể cần đọc loại metadata nào?

### Bài 13 — track_io_timing

Kiểm tra `SHOW track_io_timing`. Nếu được bật, quan sát I/O Timings. Vì sao cùng shared reads có thể mang thời gian thực khác nhau?

### Bài 14 — WAL của INSERT

Trong lab, bọc `EXPLAIN (ANALYZE, WAL) INSERT` vào transaction rollback. Giải thích WAL Records, WAL FPI và WAL Bytes; vì sao identity sequence có thể tạo gap dù rollback?

### Bài 15 — WAL của UPDATE

UPDATE 100 rows trong lab, đo WAL. Vì sao WAL Records không bằng số rows? Những nguồn WAL nào ngoài heap chính có thể xuất hiện?

### Bài 16 — WAL của DELETE

Thực hiện `EXPLAIN ANALYZE DELETE` trong transaction rồi rollback. Vì sao dữ liệu được phục hồi nhưng WAL đã phát sinh không biến mất?

### Bài 17 — FPI và checkpoint

Giải thích tại sao cùng một UPDATE có thể có `fpi` rất khác tùy checkpoint. Vì sao không nên so sánh hai lần đo WAL Bytes mà không biết điều kiện môi trường?

### Bài 18 — WAL và replication

Một query tạo 5 MiB WAL. Có thể kết luận replica nhận đúng 5 MiB bytes network trong cùng thời điểm không? Nêu các khác biệt giữa WAL generation, WAL flush và replication lag.

### Bài 19 — SETTINGS

Chạy `EXPLAIN (SETTINGS)`, sau đó `SET LOCAL work_mem='64kB'` trong transaction và chạy lại. Vì sao SETTINGS có thể hiển thị tham số nhưng không liệt kê toàn bộ `SHOW ALL`?

### Bài 20 — enable_seqscan

Trên lab, dùng `SET LOCAL enable_seqscan=off` rồi xem plan. Tại sao đây chỉ là thí nghiệm, không phải khuyến nghị bật trên production?

### Bài 21 — JSON top-level

Chạy `EXPLAIN (FORMAT JSON) SELECT ...`. Xác định phần tử mảng đầu, `Plan` và `Node Type`. Vì sao parser không nên giả định kết quả là một object `{"Plan": ...}` ở top-level?

### Bài 22 — JSON optional metrics

So sánh JSON plan-only với JSON có `ANALYZE, BUFFERS, WAL`. Những fields nào có thể không xuất hiện? Làm sao phân biệt metric chưa đo và giá trị 0?

### Bài 23 — Duyệt tree

Viết hàm Java/Python duyệt `Plan` và mọi `Plans` children, in danh sách node types. Nếu plan thay đổi từ Nested Loop sang Hash Join, parser có tiếp tục hoạt động không?

### Bài 24 — JSON WAL fields

Với EXPLAIN UPDATE có WAL, tìm `WAL Records`, `WAL FPI` và `WAL Bytes` trong cấu trúc JSON thực tế. Vì sao không được cộng counters từ mọi node?

### Bài 25 — psql export JSON

Dùng `\pset format unaligned`, `\pset tuples_only on` và `\o` để ghi một EXPLAIN FORMAT JSON vào file lab. Kiểm tra file bằng JSON parser và trả lại cấu hình output bình thường.

### Bài 26 — JDBC parse JSON

Viết `PreparedStatement` có `EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)` trên SELECT; lấy `ResultSet.getString(1)` rồi dùng Jackson đọc `Plan["Node Type"]` và `Execution Time`.

### Bài 27 — TIMING OFF

Chạy hai bản `EXPLAIN ANALYZE` của cùng SELECT, một bản `TIMING OFF`. Những thông tin nào vẫn còn? Điều gì giảm overhead instrumentation?

### Bài 28 — Benchmark có kiểm soát

Thiết kế một thử nghiệm thay index: cùng dataset, cùng SQL/parameters, thống kê đã cập nhật, chạy warm-up và nhiều lần đo. Bạn sẽ ghi những metrics nào từ plan JSON?

### Bài 29 — Planning vs Execution

Một query có `Planning Time=15ms`, `Execution Time=1ms`. Tối ưu index để giảm executor từ 1ms xuống 0,8ms có thể không giải quyết bottleneck nào? Bạn sẽ điều tra điều gì trước?

### Bài 30 — Chậm nhưng ít BUFFERS

Một query có shared read thấp, temp=0 nhưng Execution Time cao. Liệt kê ít nhất năm nguyên nhân khác ngoài disk reads và cách kiểm chứng từng giả thuyết.

### Bài 31 — Lock wait

Session A giữ row lock, session B chờ UPDATE. Vì sao BUFFERS không chỉ ra trực tiếp blocker PID? Viết query dùng `pg_blocking_pids` và `pg_stat_activity`.

### Bài 32 — Tìm query tốn WAL tổng thể

So sánh mục tiêu của `EXPLAIN WAL`, `pg_stat_wal` và `pg_stat_statements`. Khi nào một hiệu WAL bytes toàn instance không thể quy về một statement?

### Bài 33 — Auto-explain

Một hệ thống có slow queries không dễ tái hiện. Bạn sẽ cân nhắc auto_explain/log_lock_waits/pg_stat_statements như thế nào để thu thập bằng chứng mà không bật instrumentation quá nặng?

### Bài 34 — So sánh SETTINGS hai môi trường

Hai môi trường có `random_page_cost`, `work_mem` và dữ liệu khác nhau. Lập kế hoạch so sánh có kiểm soát để phân biệt tác động của settings với thống kê và cache.

### Bài 35 — Report JSON không lộ dữ liệu

Plan JSON chứa filter với literal ID khách hàng và tên bảng nhạy cảm. Hãy đề xuất chiến lược redact, quản lý quyền truy cập và metadata cần lưu để vẫn có thể benchmark lại.

### Bài 36 — Điều tra một UPDATE chậm

Trên lab, dùng `EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)` cho UPDATE trong transaction rollback. Đọc actual rows, shared hits/reads, dirtied/written, WAL Records/FPI/Bytes, settings; giải thích rủi ro khi áp dụng cùng phép thử trên production.

## Kết luận

**`EXPLAIN` cho biết PostgreSQL định thực thi câu SQL theo cách nào; `ANALYZE` cho phép đo một lần thực thi thật; `BUFFERS`, `WAL` và `SETTINGS` mở rộng góc nhìn từ kế hoạch truy vấn sang chi phí truy cập bộ đệm, ghi WAL và ngữ cảnh cấu hình của planner. `FORMAT JSON` biến cây kế hoạch thành dữ liệu có cấu trúc để lưu trữ, phân tích và so sánh tự động.**

Khi đọc **BUFFERS**, hãy phân biệt `shared hit` với `shared read` (không đồng nhất disk I/O vật lý), `dirtied` với `written` (không đồng nhất WAL), **local buffers** với **temporary working files**, và tránh cộng counters của mọi node vì parent có thể bao gồm descendant. Đọc `Actual Rows` cùng `Loops` và các chi tiết Sort/Hash/Parallel để hiểu nguồn phát sinh hoạt động.

Khi đọc **WAL**, phân biệt `records`, `fpi` và `bytes` với số rows, dung lượng bảng và replication network. Một transaction có thể tạo WAL ngay cả khi sau đó rollback; số FPI còn chịu ảnh hưởng checkpoint và cấu hình, nên benchmark phải kiểm soát điều kiện thí nghiệm.

Khi dùng **SETTINGS**, hãy nhớ output không phải `SHOW ALL`: nó tập trung vào những cài đặt ảnh hưởng planner khác built-in defaults. Khi dùng **FORMAT JSON**, root thông thường là **mảng** chứa `Plan`, các node con nằm trong `Plans`, còn metrics có thể vắng mặt tùy options/version. Công cụ cần đọc JSON linh hoạt, không trộn “không được đo” với 0, và không cộng số liệu tích lũy một cách sai.

Cuối cùng, **`EXPLAIN ANALYZE thực sự chạy câu lệnh`**. Với DML, luôn hiểu hậu quả của trigger, WAL, locks, sequence và side effects trước khi thử. Một quy trình tối ưu đáng tin không chỉ thu được plan đẹp mà còn so sánh **cùng workload, cùng bối cảnh, nhiều lần đo**, rồi cân nhắc chi phí toàn hệ thống. Kết hợp bốn tùy chọn này đúng cách giúp bạn chuyển từ việc đoán “query chậm vì database” sang chẩn đoán có bằng chứng và lựa chọn cải thiện hiệu năng PostgreSQL có cơ sở.
