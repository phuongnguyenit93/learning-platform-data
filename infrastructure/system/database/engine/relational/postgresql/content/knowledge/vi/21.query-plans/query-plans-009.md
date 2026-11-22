# Parallel scan, Gather và Gather Merge trong kế hoạch truy vấn PostgreSQL

Một truy vấn PostgreSQL quét bảng vài chục triệu hàng có thể mất nhiều thời gian nếu chỉ một tiến trình xử lý toàn bộ dữ liệu. Khi khối lượng công việc phù hợp, PostgreSQL có thể xây dựng **parallel query plan**: chia một phần công việc cho nhiều **parallel workers**, để các tiến trình cùng quét, lọc, tính toán hoặc sắp xếp dữ liệu rồi chuyển kết quả về **leader**. Trong cây `EXPLAIN`, những dấu hiệu dễ thấy nhất là **`Parallel Seq Scan`**, **`Parallel Index Scan`**, **`Parallel Index Only Scan`**, **`Parallel Bitmap Heap Scan`**, **`Gather`** và **`Gather Merge`**.

Điểm khó không chỉ là nhớ tên node. Khi phân tích truy vấn, phải hiểu:

- **Node nào có thể được thực hiện song song?** Một node nằm dưới `Gather` chưa chắc tự chia được dữ liệu giữa workers.
- **Workers chia công việc ra sao?** “Parallel-aware scan” phối hợp lấy từng phần dữ liệu; không phải mỗi worker quét nguyên bảng rồi trả kết quả trùng.
- **`Gather` và `Gather Merge` khác gì?** `Gather` gom các dòng về leader nhưng **không bảo toàn thứ tự toàn cục**; `Gather Merge` hợp nhất các luồng đã được sắp xếp để **giữ thứ tự theo khóa sort**.
- **Vì sao có `Workers Planned: 4` nhưng `Workers Launched: 2`?** Lập kế hoạch số worker khác với tài nguyên có sẵn lúc thực thi.
- **Vì sao query có parallel plan vẫn chậm hơn?** Chi phí khởi tạo workers, IPC, xử lý ở leader, bộ nhớ cho nhiều sort/hash và cạnh tranh I/O có thể vượt lợi ích.

Bài học đặt trong ngữ cảnh **PostgreSQL query planner và executor**. Các câu SQL tạo bảng, nạp dữ liệu và thay đổi GUC chỉ dùng cho **database lab**; kết quả `EXPLAIN` cụ thể có thể thay đổi theo phiên bản PostgreSQL, thống kê, phần cứng và cấu hình server.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

1. Mô tả mô hình **leader + parallel workers** và cách một parallel plan được thực thi.
2. Đọc cây `EXPLAIN` từ các node quét song song đến `Gather` / `Gather Merge`.
3. Phân biệt **parallel-aware** scan với node không tự chia việc và phân biệt **partial plan** với xử lý finalize ở leader.
4. Biết khi nào có `Parallel Seq Scan`, `Parallel Bitmap Heap Scan`, `Parallel Index Scan` và `Parallel Index Only Scan`.
5. Giải thích sự khác nhau giữa **`Gather`** và **`Gather Merge`**, đặc biệt dưới `ORDER BY`, `LIMIT` và các node `Sort`.
6. Phân tích `Partial Aggregate`, `Finalize Aggregate`, `Sort`, `Hash` và vị trí `Gather` trong plan.
7. Diễn giải `Workers Planned`, `Workers Launched`, `actual rows`, `loops`, worker-specific timing/buffers và leader participation.
8. Biết cách đo song song bằng `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` trên workload an toàn.
9. Hiểu những cấu hình như `max_parallel_workers_per_gather`, `max_parallel_workers`, `max_worker_processes`, `parallel_setup_cost`, `parallel_tuple_cost`, các ngưỡng kích thước.
10. Nhận diện giới hạn **parallel safety**, hàm `PARALLEL SAFE`/`RESTRICTED`/`UNSAFE` và lý do một số truy vấn không thể hoặc không nên chạy song song.
11. Đánh giá lợi ích, chi phí CPU/IO/RAM, ảnh hưởng concurrency và tiêu chí tuning.
12. Thực hành trên tập dữ liệu mẫu và giải thích những hiện tượng plan thay đổi mà không kết luận sai.

## 2. Truy vấn tuần tự và truy vấn song song

### 2.1. Truy vấn tuần tự

Giả sử một bảng `events` có 1 triệu hàng. Một query:

~~~sql
SELECT COUNT(*)
FROM events
WHERE event_type = 'purchase';
~~~

Với một kế hoạch tuần tự, một backend thực hiện việc quét/đếm tương ứng:

~~~text
Client
  |
  v
Backend PostgreSQL (leader)
  |
  +-- Aggregate
        |
        +-- Seq Scan on events
              Filter: event_type = 'purchase'
~~~

Quá trình chỉ có một tiến trình thực thi các node liên quan, nên có thể giới hạn tốc độ nếu CPU, dữ liệu hoặc phép tính đủ lớn.

### 2.2. Truy vấn song song

Khi planner xem chạy song song có lợi và truy vấn đáp ứng điều kiện an toàn, một kế hoạch có thể là:

~~~text
Client
  |
  v
Leader backend
  |
  +-- Finalize Aggregate
        |
        +-- Gather (Workers Planned: 2)
              |
              +-- Partial Aggregate
                    |
                    +-- Parallel Seq Scan on events
                         Filter: event_type = 'purchase'
~~~

Trong mô hình này, workers quét các phần của bảng và tính **kết quả đếm cục bộ**; leader nhận các kết quả partial và kết hợp thành số cuối cùng.

~~~mermaid
flowchart TD
    Q["Client gửi SELECT"] --> L["Leader backend"]
    L --> G["Gather"]
    G --> PA["Partial Aggregate / Parallel Scan subtree"]
    PA --> W1["Worker 1: quét phần dữ liệu"]
    PA --> W2["Worker 2: quét phần dữ liệu"]
    PA --> W3["Leader có thể tham gia quét"]
    W1 --> R["Kết quả partial"]
    W2 --> R
    W3 --> R
    R --> G
    G --> F["Finalize Aggregate"]
    F --> O["Kết quả trả client"]
~~~

Sơ đồ mang tính logic: **`Gather` là node trong cây thực thi của leader**, không phải ba bản sao của câu SQL độc lập. Workers chia sẻ cấu trúc cần thiết để phối hợp công việc và gửi tuple/partial results về leader.

### 2.3. Song song không đồng nghĩa nhanh hơn theo đúng số workers

Nếu có 4 workers, không thể mặc định query nhanh gấp 4:

- Có **chi phí khởi chạy** và kết thúc workers.
- Leader phải nhận/kết hợp dữ liệu; đôi khi trở thành nút thắt.
- Truy xuất dữ liệu có thể bị giới hạn bởi tốc độ I/O, cache, memory bandwidth.
- Các workers có thể cạnh tranh CPU với các backend khác.
- Một số node phía trên `Gather` vẫn chạy tuần tự.
- Workload nhỏ không đủ lớn để bù chi phí song song.

Parallel query là một **lựa chọn tối ưu theo chi phí**, không phải cơ chế luôn bật để càng nhiều worker càng tốt.

## 3. Leader, workers và cấu trúc partial plan

### 3.1. Leader là gì?

**Leader** là backend PostgreSQL đang xử lý yêu cầu của client. Khi truy vấn có parallel plan, leader:

- Tổ chức khởi chạy các parallel workers phù hợp;
- Thực hiện phần plan phía **trên `Gather`**;
- Thu nhận tuple/partial results do workers gửi tới;
- Có thể **tham gia thực thi** phần parallel plan tùy cấu hình và lượng công việc nhận từ workers;
- Trả kết quả cuối cùng cho client.

### 3.2. Worker là gì?

Parallel worker là **tiến trình PostgreSQL riêng** được tạo/điều phối để cùng thực thi **phần song song của một kế hoạch truy vấn**. Workers không phải threads nằm trong cùng một thread pool của ứng dụng Java.

Worker dùng tài nguyên CPU/RAM riêng cho một số thao tác, đồng thời chia sẻ/nhận những trạng thái cần thiết để phối hợp quét dữ liệu. Một backend khác cũng có thể yêu cầu workers; số lượng worker có sẵn là **tài nguyên hữu hạn** trên toàn instance.

### 3.3. Partial plan là gì?

Phần cây nằm **bên dưới `Gather`** (hay `Gather Merge`) được tổ chức như **partial plan** có thể cho các tiến trình tham gia thực thi để tạo ra **những phần kết quả**. Sau đó `Gather`/`Gather Merge` hợp nhất các phần ấy.

~~~text
                 [Leader-only phần trên]
                    Finalize Aggregate
                           |
                        Gather
                           |
                [Partial plan bên dưới]
                    Partial Aggregate
                           |
                   Parallel Seq Scan
~~~

Nhiều node trong partial plan như `Filter`, `Project`, `Partial Aggregate` có thể thực hiện trên những phần dữ liệu do parallel-aware scan phân phối.

**Quan trọng:** “nằm dưới Gather” không tự có nghĩa mọi node đều biết **chia việc**. Chỉ những node **parallel-aware** như `Parallel Seq Scan`/`Parallel Index Scan` có cơ chế phối hợp tránh quét trùng dữ liệu; những node khác có thể chỉ xử lý các hàng mà worker tương ứng đã nhận được.

### 3.4. Parallel-aware và parallel-safe khác nhau

Hai thuật ngữ:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Parallel-safe** | Phép toán/hàm có thể chạy trong parallel worker mà không vi phạm tính đúng/sự an toàn |
| **Parallel-aware** | Node có cơ chế phối hợp **chia công việc** giữa các workers, tránh mỗi worker quét lại toàn bộ nguồn |

Một `Filter` dùng phép nhân số học đơn giản có thể là parallel-safe nhưng không cần tự chia việc. `Parallel Seq Scan` vừa được đặt trong partial plan vừa có cơ chế **phân phối những block** cho nhiều tiến trình.

### 3.5. Một query có thể có nhiều vùng parallel

Plan có thể có nhiều node `Gather` trong các nhánh khác nhau, ví dụ với các truy vấn tổng hợp/join phức tạp. Không nên suy ra cứ thấy một `Gather` là **toàn bộ SQL** chạy song song từ đầu đến cuối.

## 4. Parallel Seq Scan: quét tuần tự nhưng có nhiều người cùng quét

### 4.1. Seq Scan và Parallel Seq Scan

`Seq Scan` đọc lần lượt các block phù hợp của một heap relation. `Parallel Seq Scan` cho phép nhiều worker/leader phối hợp nhận **các dải block** của cùng bảng để quét.

~~~text
Heap table events:
   Block 0 ... 9999

Worker 1: block 0..N, rồi lấy thêm block còn trống
Worker 2: block M..K, rồi lấy thêm block còn trống
Worker 3: ...

Mỗi block được phân phối để tránh quét trùng
giữa các người tham gia Parallel Seq Scan.
~~~

Phân công thực tế thường có tính **động**. Đừng hiểu mỗi worker luôn quét đúng `1/N` hàng theo khóa chính hay một khoảng event_id cố định.

### 4.2. Parallel Seq Scan không tạo thứ tự theo khóa

Một sequential scan vốn không có bảo đảm kết quả `ORDER BY` nếu SQL không yêu cầu. Parallel Seq Scan càng không có cam kết “worker 1 trả ID nhỏ, worker 2 trả ID lớn”.

**Muốn thứ tự**, phải có `ORDER BY` ở câu SQL và một kế hoạch đáp ứng thứ tự ấy, có thể bằng `Sort` hoặc `Gather Merge`.

### 4.3. Một plan minh họa

~~~text
Gather  (cost=1000.00..21000.00 rows=400000 width=...)
  Workers Planned: 3
  ->  Parallel Seq Scan on events e
        Filter: (event_type = 'purchase')
~~~

Đây là **plan mẫu**, số `cost`, `rows` và số workers **không phải kết quả được bảo đảm** từ bộ dữ liệu ở phần lab.

Nếu truy vấn trả **nhiều dòng**, leader có thể tốn đáng kể thời gian để thu hàng triệu tuple từ workers qua Gather. Với câu `COUNT(*)`, kết hợp thêm `Partial Aggregate` để workers gửi **một kết quả đếm nhỏ** thay vì gửi toàn bộ hàng thường hiệu quả hơn.

## 5. Bộ dữ liệu thực hành cho kế hoạch parallel

Để PostgreSQL có cơ hội cân nhắc parallel scans, bảng mẫu cần lớn hơn vài chục hàng. Dưới đây là **1.000.000 sự kiện** và bảng phân loại khách hàng. Hãy tạo trong database lab, trên môi trường đủ tài nguyên, và không nạp trực tiếp lên production.

> **Chi phí thực hành:** một triệu hàng với payload text chiếm dung lượng đáng kể và tạo WAL/index. Nếu laptop hoặc instance giới hạn tài nguyên, giảm `generate_series` xuống 100.000–300.000 rồi hiểu rằng planner có thể không chọn parallel plan; không cần ép máy quá tải để thấy một từ khóa trong EXPLAIN.

### 5.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA parallel_lab_273;

CREATE TABLE parallel_lab_273.events (
    event_id BIGINT PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('purchase', 'view')),
    amount NUMERIC(12, 2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE parallel_lab_273.customers (
    customer_id INTEGER PRIMARY KEY,
    segment TEXT NOT NULL
        CHECK (segment IN ('NEW', 'REGULAR', 'VIP'))
);
~~~

### 5.2. Nạp sự kiện

~~~sql
INSERT INTO parallel_lab_273.events (
    event_id,
    customer_id,
    event_type,
    amount,
    occurred_at,
    payload
)
SELECT
    g::bigint,
    (g % 10000 + 1)::integer,
    CASE
        WHEN g % 10 IN (0, 1, 2) THEN 'purchase'
        ELSE 'view'
    END,
    ((g % 100000)::numeric / 100 + 1)::numeric(12, 2),
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g % 15552000) * INTERVAL '1 second',
    repeat('x', 120)
FROM generate_series(1, 1000000) AS gs(g);
~~~

Trong dữ liệu được sinh:

- `event_id` nhận giá trị 1 đến 1.000.000, không trùng.
- `customer_id` lặp theo khoảng 1 đến 10.000.
- Cứ 10 sự kiện có 3 `purchase` và 7 `view`, nên có **300.000 purchase**.
- `amount` và `occurred_at` là những giá trị xác định, phù hợp cho thử nghiệm sort và filter.
- `payload` giúp các hàng có kích thước đáng kể, tăng cơ hội parallel scan trở nên có ý nghĩa.

### 5.3. Nạp khách hàng để thử join

~~~sql
INSERT INTO parallel_lab_273.customers (
    customer_id,
    segment
)
SELECT
    g::integer,
    CASE
        WHEN g % 10 = 0 THEN 'VIP'
        WHEN g % 3 = 0 THEN 'NEW'
        ELSE 'REGULAR'
    END
FROM generate_series(1, 10000) AS gs(g);
~~~

Các bảng có khóa chính, nên PostgreSQL có thể dùng index B-tree do `PRIMARY KEY` tạo ra.

### 5.4. Thống kê trước khi EXPLAIN

~~~sql
ANALYZE parallel_lab_273.events;
ANALYZE parallel_lab_273.customers;

SELECT
    COUNT(*) AS all_events,
    COUNT(*) FILTER (WHERE event_type = 'purchase')
        AS purchases
FROM parallel_lab_273.events;
~~~

**Kỳ vọng logic:** `all_events=1000000` và `purchases=300000`. Đây là kết quả của dữ liệu sinh, không phải yêu cầu plan phải giống nhau giữa các máy.

### 5.5. Không chạy VACUUM trong transaction

Nếu ở phần sau dùng:

~~~sql
VACUUM (ANALYZE) parallel_lab_273.events;
~~~

thì chạy ở chế độ autocommit/ngoài `BEGIN`, vì PostgreSQL không cho `VACUUM` thông thường chạy trong explicit transaction block. Trên bảng lớn, lệnh có thể dùng I/O đáng kể.

## 6. EXPLAIN cơ bản: xác định parallel plan

Trước hết chạy **EXPLAIN không ANALYZE**:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';
~~~

Nếu planner quyết định parallel, bạn có thể thấy dạng:

~~~text
Finalize Aggregate
  ->  Gather
        Workers Planned: 2
        ->  Partial Aggregate
              ->  Parallel Seq Scan on events
                    Filter: (event_type = 'purchase')
~~~

Nếu không, một dạng tuần tự có thể là:

~~~text
Aggregate
  -> Seq Scan on events
       Filter: (event_type = 'purchase')
~~~

Cả hai có thể **đúng về ngữ nghĩa** và là lựa chọn chi phí hợp lý trong những môi trường khác nhau.

### 6.1. Đọc cây từ dưới lên

- `Parallel Seq Scan`: quét chung bảng, mỗi người tham gia nhận các block/tuple phù hợp.
- `Partial Aggregate`: mỗi worker/leader tham gia tính count cục bộ.
- `Gather`: thu các hàng kết quả partial lên leader.
- `Finalize Aggregate`: kết hợp các count cục bộ thành tổng chính xác.

Truy vấn `COUNT(*)` không cần thứ tự, nên `Gather` phù hợp; **`Gather Merge` không có lợi nếu không cần sorted input**.

### 6.2. EXPLAIN ANALYZE có gì khác?

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';
~~~

`ANALYZE` làm PostgreSQL **chạy thật truy vấn** rồi ghi lại thông tin thực tế như `actual time`, `rows`, `loops` và `Workers Launched`. `BUFFERS` cho biết hoạt động buffer I/O; `VERBOSE` có thể cung cấp thêm thống kê theo worker.

Vì đây là `SELECT COUNT(*)` thuần, thực hành tương đối an toàn trên lab. **Nếu áp dụng `EXPLAIN ANALYZE` cho DML như `UPDATE`/`DELETE` thì câu lệnh sẽ ghi thật**, không chỉ in kế hoạch. Chỉ dùng khi đã đánh giá tác động và transaction phù hợp.

### 6.3. Cấu trúc actual plan minh họa

~~~text
Finalize Aggregate (actual time=... rows=1 loops=1)
  -> Gather (actual time=... rows=3 loops=1)
       Workers Planned: 2
       Workers Launched: 2
       -> Partial Aggregate (actual time=... rows=1 loops=3)
            -> Parallel Seq Scan on events
                 (actual time=... rows=100000 loops=3)
                 Filter: (event_type = 'purchase')
~~~

Trong ví dụ, hai workers cộng leader có thể cùng tham gia vào một node dưới Gather, nên `loops=3` có thể xuất hiện; nhưng **không mặc định số loops luôn bằng workers launched + 1**, vì leader participation và thời điểm thực thi khác nhau. Số actual rows dưới parallel node được báo cáo theo quy tắc thống kê của EXPLAIN, cần diễn giải cùng `loops`/thống kê worker, **không xem như số hàng global duy nhất**.

### 6.4. Tại sao không có Gather dù bảng lớn?

Parallel query là lựa chọn của planner. Có thể do:

- Scan cột qua index nhanh hơn;
- `max_parallel_workers_per_gather=0` hoặc không còn workers;
- Bảng/khối lượng công việc không đủ để bù startup;
- Query có parallel-unsafe operation;
- Nhiều điều kiện làm số hàng cần xử lý nhỏ;
- Query order/limit phù hợp single index scan;
- Chi phí planner, thống kê hoặc cấu hình không ưu tiên parallel;
- Môi trường transaction/statement có giới hạn đặc biệt.

Không cần “fix” một query chỉ vì không thấy chữ `Parallel` nếu latency/SLA đã tốt.

## 7. Workers Planned khác Workers Launched

Trong `EXPLAIN`:

~~~text
Workers Planned: 4
~~~

nghĩa là **planner muốn tối đa bốn parallel workers** cho Gather tương ứng (theo kế hoạch). Đến lúc thực thi, `EXPLAIN ANALYZE` có thể báo:

~~~text
Workers Launched: 2
~~~

nghĩa là PostgreSQL **chỉ khởi chạy được hai workers** ở lần chạy đó.

### 7.1. Vì sao thiếu workers?

Số workers bị giới hạn bởi:

- `max_parallel_workers_per_gather` — giới hạn cho mỗi Gather/query;
- `max_parallel_workers` — giới hạn số parallel query workers đang hoạt động trên instance;
- `max_worker_processes` — giới hạn nền cho các worker processes, bao gồm những loại khác;
- Workers đang bị các query khác chiếm;
- Tài nguyên hệ thống và điều kiện runtime.

Vì vậy, **`Workers Planned` không phải số workers thực sự chạy** và cũng không phải số CPU cores được dành riêng.

### 7.2. Khi không launch được workers

Một parallel plan có thể chạy với ít workers hơn, thậm chí chỉ leader trong những trường hợp phù hợp. Truy vấn vẫn cần tạo kết quả đúng, nhưng **thời gian** có thể thay đổi nhiều so với lúc planner ước tính.

Không suy ra PostgreSQL bị lỗi dữ liệu vì `Workers Launched < Workers Planned`; đó thường là dấu hiệu hạn chế tài nguyên/concurrency hoặc chính sách runtime.

### 7.3. Leader có tham gia scan không?

`parallel_leader_participation` điều khiển việc leader có thể tham gia thực thi phần bên dưới Gather. Mặc định thường là **on** trong các bản PostgreSQL hiện đại.

Tuy nhiên, **leader còn bận đọc tuple từ workers**. Với query trả hàng triệu dòng, leader có thể dành phần lớn thời gian thu kết quả thay vì chủ động quét. Với query có `Partial Aggregate` trả vài hàng, leader có thể có cơ hội tham gia quét nhiều hơn.

### 7.4. Không cộng trực tiếp "số workers" thành "số scan độc lập"

Một `Parallel Seq Scan` là **một công việc quét phối hợp**. Ba người cùng tham gia không có nghĩa bảng bị quét trọn ba lần. Đánh giá buffer/page scan và phân phối tuples phải dựa trên mô hình parallel-aware, không dựa trên phép nhân tùy tiện.

## 8. Gather: thu kết quả nhưng không giữ thứ tự

`Gather` là node xuất hiện ở ranh giới giữa **partial plan** và **phần xử lý ở leader**. Nó lấy các tuple do các participants tạo ra rồi đưa lên phía trên của plan.

~~~text
                  [Leader]
                     |
                   Gather
                     ^
          +----------+---------+
          |          |         |
       Worker A   Worker B  Leader
          |          |         |
       Tuple A1   Tuple B1  Tuple L1
       Tuple A2   Tuple B2  Tuple L2
       Tuple A3   Tuple B3  Tuple L3
~~~

Thứ tự đến Gather có thể phụ thuộc tiến độ workers:

~~~text
Worker A:  1,  3,  5,  7
Worker B:  2,  4,  6,  8

Gather có thể phát:
    1, 3, 2, 4, 6, 5, 8, 7
~~~

**Gather không hợp nhất các luồng theo một khóa sort**. Kể cả khi từng worker tự tạo một luồng đã sắp xếp, Gather **không hứa giữ thứ tự toàn cục**.

### 8.1. Gather không giống UNION ALL

Gather kết hợp output của **cùng một partial plan** đang được chia việc, không phải toán tử SQL `UNION ALL` nối những truy vấn độc lập. Hai thứ có thể đều tập hợp hàng, nhưng ý nghĩa điều phối khác nhau.

### 8.2. Gather + Sort

Nếu query có `ORDER BY` nhưng planner chọn Gather, một cấu trúc có thể là:

~~~text
Sort
  Sort Key: amount DESC, event_id DESC
  -> Gather
       Workers Planned: 2
       -> Parallel Seq Scan on events
~~~

Ở đây, **Sort phía trên Gather** do leader thực hiện để đảm bảo thứ tự toàn cục. Với output rất lớn, một sort lớn ở leader có thể là điểm nghẽn RAM/CPU hoặc cần ghi file tạm.

### 8.3. Gather không cho phép bỏ ORDER BY

~~~sql
SELECT event_id
FROM parallel_lab_273.events
WHERE event_type = 'purchase'
LIMIT 20;
~~~

Không có `ORDER BY`, **20 ID được trả không xác định theo hợp đồng SQL**, dù plan dùng `Gather`, `Seq Scan` hay `Index Scan`. Nếu người dùng cần “20 sự kiện mới nhất”, phải ghi:

~~~sql
SELECT event_id, occurred_at
FROM parallel_lab_273.events
WHERE event_type = 'purchase'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 20;
~~~

Planner có thể chọn serial index scan, Gather Merge, Gather + Sort hoặc cấu trúc khác; kết quả phải tuân theo `ORDER BY` nếu query đúng.

## 9. Gather Merge: hợp nhất các luồng đã có thứ tự

**`Gather Merge`** khác `Gather` ở chỗ nó dự kiến nhận các luồng output **đã sắp theo cùng một khóa** từ các participants và **merge** chúng thành một luồng đầu ra có thứ tự toàn cục.

~~~text
Worker A (sorted): 1, 3, 5, 7
Worker B (sorted): 2, 4, 6, 8
Leader   (sorted): 0, 9

Gather Merge:
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9
~~~

Sơ đồ minh họa theo giá trị số nguyên; thực tế `Gather Merge` so sánh các **sort keys** và thứ tự ASC/DESC/NULLS FIRST/LAST do plan quy định.

### 9.1. Tại sao phải có thứ tự trước Gather Merge?

Nếu worker A trả `1,7,3` và worker B trả `2,8,4`, chỉ nhìn phần tử đầu mỗi luồng không đủ để tạo kết quả sorted. Để merge đúng, **đầu vào của mỗi participant phải được sắp xếp tương thích**.

Vì thế plan thường có:

~~~text
Gather Merge
  Workers Planned: 3
  -> Sort
       Sort Key: amount DESC, event_id DESC
       -> Parallel Seq Scan on events
~~~

Hoặc một parallel index scan có thể cung cấp thứ tự tương thích trực tiếp, không cần Sort trên mỗi luồng:

~~~text
Gather Merge
  Workers Planned: 2
  -> Parallel Index Scan using idx_events_amount_event_id on events
~~~

**Hai sơ đồ đều chỉ là plan minh họa**, không có cam kết query cụ thể phải dùng chúng.

### 9.2. Gather Merge không có nghĩa toàn bảng được sort một lần ở leader

Trong plan có `Sort` nằm **bên dưới Gather Merge**, mỗi worker/participant sort **phần hàng của mình**. Gather Merge đọc đầu mỗi luồng và liên tục lấy phần tử tiếp theo đúng thứ tự, thay vì thu tất cả tuple về leader rồi sort toàn bộ ở cuối.

Đổi lại, leader phải thực hiện merge so sánh các khóa và phối hợp đọc tuple từ các workers. Với nhiều luồng/output lớn, công việc merge vẫn có chi phí.

### 9.3. ORDER BY với khóa trùng nhau

`Gather Merge` đảm bảo **thứ tự theo các sort keys**, không tự tạo một **thứ tự tổng quát duy nhất** cho những hàng có khóa bằng nhau.

Ví dụ:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC
LIMIT 20;
~~~

Nhiều sự kiện có thể cùng `amount`. PostgreSQL được phép trả các hàng có amount bằng nhau theo thứ tự bất kỳ. Nếu cần phân trang hoặc kết quả tái lập, thêm khóa tie-break duy nhất:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 20;
~~~

**Gather Merge chỉ giữ thứ tự bạn đã yêu cầu**, không tự bổ sung `event_id` để giải quyết ties.

### 9.4. Gather Merge so với Merge Join

Tên giống nhau nhưng ý nghĩa khác:

| Node | Nhiệm vụ |
| --- | --- |
| **Gather Merge** | Gộp các luồng **cùng partial plan** đã có thứ tự từ workers/leader |
| **Merge Join** | Kết hợp hai quan hệ đầu vào theo điều kiện join có thứ tự phù hợp |

Một plan có thể chứa cả hai node; không nhầm `Gather Merge` là phép join dữ liệu.

## 10. So sánh Gather và Gather Merge

| Tiêu chí | Gather | Gather Merge |
| --- | --- | --- |
| Vai trò | Thu tuple từ partial plan | Thu **và merge sorted streams** |
| Đầu vào có cần được sort? | **Không** | **Có**, theo khóa tương thích |
| Bảo toàn thứ tự toàn cục? | Không | Có, theo sort key đã cho |
| Thường đi với | Parallel Seq Scan, Partial Aggregate, trả kết quả không yêu cầu thứ tự | `ORDER BY`, sorted partial scans, Sort trong workers |
| Chi phí leader | Thu/chuyển tuple, xử lý phía trên | Thu/chuyển tuple **và merge theo khóa** |
| Có thể cần Sort riêng? | Có thể `Sort` **phía trên** Gather | Có thể `Sort` **phía dưới** Gather Merge |
| Có đảm bảo thứ tự giữa hàng có khóa bằng nhau? | Không | Không nếu `ORDER BY` thiếu tie-break |
| Query có thể chạy nhanh hơn với cái nào? | Tùy workload | Tùy số dòng, sort, index và chi phí merge |

**Không có quy tắc “Gather Merge luôn nhanh hơn Gather + Sort”.** Nếu output nhỏ, sort tại leader có thể rẻ. Nếu mỗi worker xử lý lượng dữ liệu lớn và có lợi từ sắp xếp song song, Gather Merge có thể hấp dẫn hơn. Planner ước tính chi phí và chọn kế hoạch phù hợp.

## 11. Thực hành Gather Merge với ORDER BY

Truy vấn sắp sự kiện theo số tiền, với `event_id` làm tie-break:

~~~sql
EXPLAIN
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 1000;
~~~

PostgreSQL có thể chọn một trong nhiều kế hoạch hợp lệ:

### 11.1. Plan có Sort tuần tự

~~~text
Limit
  -> Sort
       Sort Key: amount DESC, event_id DESC
       -> Seq Scan on events
~~~

Một backend quét bảng và sort các hàng cần thiết, có thể tối ưu kiểu top-N sort khi có LIMIT.

### 11.2. Plan có Gather + Sort

~~~text
Limit
  -> Sort
       Sort Key: amount DESC, event_id DESC
       -> Gather
            Workers Planned: 3
            -> Parallel Seq Scan on events
~~~

Workers giúp quét/filter, sau đó leader cần sắp xếp đầu ra do `Gather` không đảm bảo thứ tự.

### 11.3. Plan có Gather Merge

~~~text
Limit
  -> Gather Merge
       Workers Planned: 3
       -> Sort
            Sort Key: amount DESC, event_id DESC
            -> Parallel Seq Scan on events
~~~

Mỗi participant sort phần kết quả của mình theo cùng khóa. `Gather Merge` hợp nhất chúng và trả luồng đã sắp xếp cho `Limit` phía trên.

### 11.4. LIMIT và top-N sort

Với `ORDER BY ... LIMIT 1000`, PostgreSQL có thể dùng **top-N heapsort** thay vì lưu toàn bộ các hàng cần sort trong bộ nhớ. Trong parallel plan, từng worker có thể giữ tập ứng viên top-N của mình, rồi `Gather Merge`/leader kết hợp để chọn top-N toàn cục.

Khi xem `EXPLAIN (ANALYZE)`, nếu thấy:

~~~text
Sort Method: top-N heapsort  Memory: ...
~~~

đó là **phương thức sort thực tế** của node tương ứng, không phải một “kiểu index” hay một bảo đảm rằng toàn bộ pipeline không cần đọc phần còn lại của bảng.

### 11.5. Vì sao không phải query ORDER BY nào cũng chọn Gather Merge?

- Có index B-tree đã cung cấp thứ tự đủ tốt;
- `LIMIT` nhỏ, single index scan có thể dừng sớm;
- Số hàng lọc ra ít, sort ở leader rẻ;
- Workers không sẵn sàng hoặc chi phí startup lớn;
- Các phép toán trung gian chưa thể cung cấp sorted partial streams;
- Planner ước tính `Gather + Sort` hoặc truy cập tuần tự có cost thấp hơn.

Một `ORDER BY` chỉ khiến PostgreSQL phải **đáp ứng thứ tự**, không bắt buộc nó phải dùng một node cụ thể.

## 12. Parallel Index Scan: chia việc đọc index B-tree

`Parallel Index Scan` là node quét index trong partial plan với cơ chế phối hợp giữa participants. Trong PostgreSQL hiện đại, parallel index scans hỗ trợ **B-tree indexes**. Các participants nhận những phần công việc của index để cùng duyệt và trả tuple phù hợp.

### 12.1. Index scan thường

~~~text
Index Scan using idx_events_created_at on events
  Index Cond: occurred_at >= ...
~~~

Một tiến trình duyệt index rồi đọc heap tuples khi cần.

### 12.2. Parallel Index Scan

~~~text
Gather
  Workers Planned: 2
  -> Parallel Index Scan using idx_events_created_at on events
       Index Cond: occurred_at >= ...
~~~

Các workers phối hợp quét index B-tree. Không hiểu rằng mỗi worker được cấp hẳn một shard độc lập của bảng hay giữ một cursor tuần tự riêng trỏ từ đầu index đến cuối.

### 12.3. Tạo index thử nghiệm

~~~sql
CREATE INDEX idx_events_created_at_273
ON parallel_lab_273.events (occurred_at);

ANALYZE parallel_lab_273.events;
~~~

Truy vấn đọc nhiều hàng:

~~~sql
EXPLAIN
SELECT event_id, occurred_at
FROM parallel_lab_273.events
WHERE occurred_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00';
~~~

Tùy số hàng, độ chọn lọc, correlation và chi phí, PostgreSQL có thể chọn `Index Scan`, `Bitmap Heap Scan`, `Seq Scan` hoặc dạng parallel tương ứng.

**Chỉ mục có mặt không bảo đảm Parallel Index Scan xuất hiện.** Với một predicate chọn rất ít hàng, single index scan thường rẻ hơn khởi chạy workers. Với predicate bao phủ hầu hết bảng, Parallel Seq Scan có thể rẻ hơn đọc heap ngẫu nhiên qua index.

### 12.4. Thứ tự trong Parallel Index Scan

Một B-tree index có thể giúp tạo thứ tự theo index key, nhưng các participants xử lý **những phần riêng**. Muốn đầu ra tổng hợp theo thứ tự toàn cục, plan có thể dùng `Gather Merge` (nếu mỗi participant cung cấp thứ tự tương thích), hoặc dùng sort phù hợp ở nơi khác.

**Không kết luận có B-tree nghĩa là Gather tự động xuất sorted results.**

### 12.5. Index scan và heap access

`Parallel Index Scan` tìm TIDs qua index và thường đọc heap để lấy dữ liệu/kiểm tra visibility khi cần. Nó có thể bị ảnh hưởng bởi:

- Số lần truy cập heap;
- Mức độ dữ liệu đã nằm trong shared buffers;
- Correlation giữa thứ tự index và vị trí vật lý;
- Tỷ lệ hàng phù hợp và số tuple bị loại;
- Random I/O và cạnh tranh bộ đệm.

Đôi khi `Parallel Seq Scan` thắng do quét tuần tự các heap blocks hiệu quả hơn.

## 13. Parallel Index Only Scan: ít đọc heap hơn khi all-visible

`Index Only Scan` cố gắng trả kết quả từ dữ liệu có trong index mà không phải đọc toàn bộ heap tuple. Với B-tree phù hợp và các điều kiện cần thiết, PostgreSQL có thể tạo **`Parallel Index Only Scan`**.

### 13.1. Tạo B-tree index phục vụ query chỉ lấy khóa

~~~sql
CREATE INDEX idx_events_customer_273
ON parallel_lab_273.events (customer_id);
~~~

Một query:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE customer_id BETWEEN 1000 AND 8000;
~~~

có thể sử dụng `Parallel Index Only Scan` với B-tree trên `customer_id` nếu planner thấy có lợi.

Plan minh họa:

~~~text
Finalize Aggregate
  -> Gather
       Workers Planned: 2
       -> Partial Aggregate
            -> Parallel Index Only Scan using idx_events_customer_273
                 Index Cond: (customer_id >= 1000 AND customer_id <= 8000)
~~~

### 13.2. “Only” không có nghĩa không bao giờ đọc heap

PostgreSQL phải xác định tuple có visible với snapshot hay không. Index không lưu đủ thông tin MVCC cho mọi tình huống; **visibility map** cho biết những heap pages nào all-visible và có thể tránh heap access.

Nếu page chưa all-visible, `Index Only Scan` vẫn có thể **đọc heap để kiểm tra visibility**.

~~~text
Parallel Index Only Scan ...
  Heap Fetches: 12345
~~~

`Heap Fetches` là chỉ số thực tế đáng xem trong `EXPLAIN (ANALYZE)`. Đừng chỉ nhìn tên node “Index Only” rồi cho rằng mọi I/O heap bằng 0.

### 13.3. Thực hành VACUUM/visibility map

Sau khi tạo dữ liệu và index, có thể chạy **ngoài explicit transaction**:

~~~sql
VACUUM (ANALYZE) parallel_lab_273.events;
~~~

Sau VACUUM, một số pages có thể được đánh dấu all-visible, tạo cơ hội cho index-only scan tránh heap fetches. Nhưng số heap fetches cuối cùng còn phụ thuộc transaction đang hoạt động, cập nhật mới, visibility map và plan; **không cam kết phải về 0**.

### 13.4. INCLUDE để trả thêm cột

Nếu ứng dụng muốn đọc cả `event_id` theo `customer_id`, có thể cân nhắc:

~~~sql
CREATE INDEX idx_events_customer_cover_273
ON parallel_lab_273.events (customer_id)
INCLUDE (event_id);
~~~

`event_id` nằm trong index payload, có thể tạo cơ hội index-only scan cho:

~~~sql
SELECT customer_id, event_id
FROM parallel_lab_273.events
WHERE customer_id BETWEEN 1000 AND 1200;
~~~

**INCLUDE làm index lớn hơn** và tăng chi phí ghi. Không thêm mọi cột vào index chỉ để theo đuổi Index Only Scan.

## 14. Parallel Bitmap Heap Scan: chia các heap blocks sau khi xây bitmap

Khi điều kiện phù hợp và trả nhiều hàng hơn một index scan đơn lẻ hiệu quả, PostgreSQL có thể chọn **Bitmap Index Scan + Bitmap Heap Scan**.

### 14.1. Bitmap scan tuần tự

~~~text
Bitmap Heap Scan on events
  Recheck Cond: customer_id BETWEEN 1000 AND 8000
  -> Bitmap Index Scan using idx_events_customer_273
       Index Cond: customer_id BETWEEN 1000 AND 8000
~~~

Bitmap Index Scan tập hợp các vị trí heap liên quan; Bitmap Heap Scan thăm những heap pages đó để lấy/kiểm tra tuples.

### 14.2. Parallel Bitmap Heap Scan

Plan minh họa:

~~~text
Gather
  Workers Planned: 3
  -> Parallel Bitmap Heap Scan on events
       Recheck Cond: customer_id BETWEEN 1000 AND 8000
       -> Bitmap Index Scan using idx_events_customer_273
            Index Cond: customer_id BETWEEN 1000 AND 8000
~~~

**Điểm đặc thù:** phần tạo bitmap từ bitmap index scan thường được **leader** thực hiện, rồi bitmap heap scan có thể phối hợp nhiều workers xử lý các heap pages từ **shared bitmap**.

Không diễn giải rằng mỗi worker tự chạy lại `Bitmap Index Scan` đầy đủ rồi tạo bitmap giống nhau; phần được parallelize nổi bật là **đọc heap từ bitmap chung**.

### 14.3. Bitmap không có sorted order của kết quả

Bitmap Heap Scan chủ yếu thăm các heap pages theo cách tối ưu I/O, **không đảm bảo output theo index order**. Nếu query có `ORDER BY customer_id`, có thể vẫn cần `Sort` hoặc một đường truy cập khác cung cấp đúng thứ tự.

### 14.4. Recheck Cond có ý nghĩa gì?

`Recheck Cond` là điều kiện được kiểm tra lại trên heap tuple khi cần, đặc biệt với **lossy bitmap pages** hoặc những tình huống truy cập tương ứng. Trong `EXPLAIN ANALYZE`, bạn có thể thấy:

~~~text
Rows Removed by Index Recheck: ...
Heap Blocks: exact=... lossy=...
~~~

Khi bitmap trở thành **lossy** vì giới hạn bộ nhớ, nó chỉ còn đánh dấu ở mức block thay vì từng tuple, khiến executor phải kiểm tra nhiều tuples hơn.

### 14.5. work_mem ảnh hưởng bitmap

`work_mem` là một trong các tham số giới hạn memory cho bitmap/sort/hash operations, nhưng không nên tăng vô hạn để “loại bỏ lossy bitmap”. Khi truy vấn có nhiều workers và nhiều node tiêu thụ memory, tổng RAM có thể tăng đáng kể.

## 15. Bốn kiểu parallel scan: bảng so sánh

| Node | Nguồn truy cập | Cách chia công việc | Có hỗ trợ thứ tự trực tiếp? | Điều cần quan sát |
| --- | --- | --- | --- | --- |
| **Parallel Seq Scan** | Heap table | Phối hợp quét các heap blocks | Không bảo đảm order | Số block/hàng được quét, filter, buffers |
| **Parallel Index Scan** | B-tree index và heap | Phối hợp quét phần index | Có thể cung cấp sorted partial streams | Index Cond, heap I/O, Gather/Gather Merge |
| **Parallel Index Only Scan** | B-tree index, có thể cần heap | Phối hợp quét index; visibility map quyết định heap fetch | Có thể cung cấp sorted partial streams | Heap Fetches, all-visible pages, predicate |
| **Parallel Bitmap Heap Scan** | Bitmap index result + heap | Leader tạo bitmap; participants thăm heap blocks theo shared bitmap | Không bảo đảm order | Recheck Cond, exact/lossy blocks, bitmap cost |

Không có node nào là “tốt nhất tuyệt đối”. Planner cân bằng selectivity, số page, phân phối dữ liệu, thống kê, index, workers và phần xử lý ở trên.

### 15.1. Chọn index vs scan không chỉ dựa trên số dòng

Một query trả 100.000 dòng có thể dùng index nếu dữ liệu nằm gần nhau theo index, hoặc Parallel Seq Scan nếu dữ liệu rải khắp bảng và đọc tuần tự toàn bộ rẻ hơn. `rows` là yếu tố, nhưng không phải tiêu chí duy nhất.

### 15.2. Index Only Scan vẫn cần dữ liệu trong index

Nếu query muốn `payload` dài và index chỉ gồm `customer_id`, **Index Only Scan không thể tự trả payload**. Muốn index-only, mọi cột/biểu thức cần trả phải có thể lấy từ index và kiểm tra visibility đủ điều kiện.

### 15.3. Bitmap Heap Scan có thể có nhiều Bitmap Index Scans

Ví dụ query:

~~~sql
SELECT event_id
FROM parallel_lab_273.events
WHERE customer_id BETWEEN 1000 AND 2000
  AND occurred_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00';
~~~

Với các indexes tương ứng, PostgreSQL **có thể** kết hợp bitmaps bằng `BitmapAnd`/`BitmapOr` trong một plan. Điều đó khác với một `Parallel Index Scan` duyệt đúng một index, và không đảm bảo xảy ra chỉ vì có hai chỉ mục.

## 16. Partial Aggregate và Finalize Aggregate

Trong parallel query, **aggregation** là nơi song song thường đem lại lợi ích lớn vì giảm lượng tuple chuyển qua `Gather`.

### 16.1. COUNT(*) chia được

Với `COUNT(*)`:

~~~text
Worker 1 đếm: 100.000
Worker 2 đếm: 120.000
Leader đếm:    80.000
                     |
                     v
        Finalize = 300.000
~~~

Plan:

~~~text
Finalize Aggregate
  -> Gather
       -> Partial Aggregate
            -> Parallel Seq Scan on events
~~~

`Partial Aggregate` tính **trạng thái trung gian**; `Finalize Aggregate` kết hợp rồi xuất kết quả.

### 16.2. SUM/AVG/COUNT với GROUP BY

~~~sql
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS event_count,
    SUM(amount) AS total_amount
FROM parallel_lab_273.events
GROUP BY customer_id;
~~~

Tùy dữ liệu và chi phí, PostgreSQL có thể chọn:

~~~text
Finalize HashAggregate
  Group Key: customer_id
  -> Gather
       Workers Planned: 3
       -> Partial HashAggregate
            Group Key: customer_id
            -> Parallel Seq Scan on events
~~~

Mỗi worker tạo các nhóm cục bộ. Sau Gather, leader kết hợp trạng thái các nhóm có cùng `customer_id`.

### 16.3. Tại sao COUNT nhóm không cộng riêng DISTINCT?

`COUNT(DISTINCT customer_id)` không thể tính bằng cách lấy `COUNT(DISTINCT)` riêng của từng worker rồi cộng, vì một customer có thể xuất hiện ở nhiều workers. PostgreSQL có những hạn chế nhất định về **parallel partial aggregation** đối với các aggregate chứa `DISTINCT` hoặc `ORDER BY`.

Ví dụ:

~~~sql
EXPLAIN
SELECT COUNT(DISTINCT customer_id)
FROM parallel_lab_273.events;
~~~

Không mặc định plan sẽ có `Partial Aggregate` đơn giản như `COUNT(*)`. **Một phần scan có thể vẫn parallel**, nhưng việc aggregate distinct có thể cần tập hợp dữ liệu/trạng thái với phương thức khác.

### 16.4. GROUP BY và Gather Merge

Một plan khác cho `GROUP BY customer_id` có thể là:

~~~text
Finalize GroupAggregate
  Group Key: customer_id
  -> Gather Merge
       Workers Planned: 2
       -> Sort
            Sort Key: customer_id
            -> Partial HashAggregate
                 Group Key: customer_id
                 -> Parallel Seq Scan on events
~~~

**Vai trò Gather Merge:** mỗi stream đã sắp theo `customer_id` nên leader có thể xử lý các nhóm theo thứ tự, phục vụ `Finalize GroupAggregate`. Planner có thể chọn `HashAggregate`/`Sort`/`GroupAggregate` theo kiểu dữ liệu, số nhóm và cost.

### 16.5. Aggregate không phải lúc nào cũng hỗ trợ partial mode

Một hàm aggregate muốn chạy kiểu **Partial/Finalize** cần có khả năng tách/ghép trạng thái trung gian thích hợp. Một số aggregates do extension/UDF tạo ra không hỗ trợ partial mode. Ngay cả khi phép quét dữ liệu có thể song song, **Finalize Aggregate** hoặc toàn bộ phép tổng hợp có thể phải chạy ở leader.

Hãy xem plan và tài liệu hàm aggregate thay vì tự suy rằng mọi `SUM-like UDF` đều có thể chạy song song.

## 17. Gather Merge và Finalize GroupAggregate

Nếu đầu vào của `Finalize GroupAggregate` cần được sắp xếp theo khóa nhóm, `Gather Merge` là một giải pháp tự nhiên:

~~~text
                     Finalize GroupAggregate
                            Group Key: region
                                   |
                               Gather Merge
                            Sort Key: region
                                   |
                        Partial GroupAggregate
                            Group Key: region
                                   |
                               Sort/Index path
                                   |
                        Parallel-aware scan
~~~

Ý nghĩa:

1. Các participants thực hiện grouping cục bộ;
2. Kết quả nhóm cục bộ được cung cấp theo thứ tự khóa nhóm;
3. `Gather Merge` trộn các luồng theo khóa nhóm;
4. `Finalize GroupAggregate` kết hợp các partial states của cùng nhóm.

Đây là cấu trúc đặc biệt hữu ích để hiểu khi `EXPLAIN` có **Finalize GroupAggregate** ngay phía trên **Gather Merge**, nhưng **không phải plan duy nhất** cho GROUP BY.

### 17.1. ORDER BY cuối không đồng nghĩa luôn Gather Merge

~~~sql
SELECT customer_id, COUNT(*)
FROM parallel_lab_273.events
GROUP BY customer_id
ORDER BY customer_id;
~~~

PostgreSQL có thể chọn:

- `Partial HashAggregate -> Gather -> Finalize HashAggregate -> Sort`;
- `Partial GroupAggregate -> Gather Merge -> Finalize GroupAggregate`;
- Một đường scan/aggregate tuần tự có sort;
- Những biến thể khác.

Mỗi plan đều có thể đáp ứng yêu cầu `ORDER BY`. Không áp một sơ đồ duy nhất cho mọi query.

### 17.2. Gather Merge không tự giảm số nhóm

Nếu có 10.000 customer IDs, mỗi worker có thể tạo 10.000 partial group rows rồi leader vẫn phải finalize thành 10.000 nhóm. Số hàng đi qua `Gather Merge` phụ thuộc số nhóm riêng trên từng participant, không bằng số dòng base table và không luôn bằng số nhóm toàn cục.

### 17.3. Thứ tự của nhóm giống nhau

Trong `Finalize GroupAggregate`, các partial rows có cùng group key được đặt gần nhau nhờ `Gather Merge`. Nhưng nếu `ORDER BY` có thêm khóa kết quả aggregate như `COUNT(*) DESC`, PostgreSQL có thể vẫn cần **Sort cuối** theo aggregate result.

## 18. JOIN trong parallel plan: không phải mọi node đều chia việc

Một truy vấn:

~~~sql
EXPLAIN
SELECT
    c.segment,
    COUNT(*) AS event_count,
    SUM(e.amount) AS total_amount
FROM parallel_lab_273.events AS e
JOIN parallel_lab_273.customers AS c
    ON c.customer_id = e.customer_id
GROUP BY c.segment;
~~~

có thể có một phần scan/join/aggregate trong parallel plan. Tùy kích thước và thống kê, planner có thể chọn Nested Loop, Hash Join, Parallel Hash Join hoặc chiến lược khác.

### 18.1. Một plan minh họa có Hash Join dưới Gather

~~~text
Finalize GroupAggregate/Finalize HashAggregate
  -> Gather / Gather Merge
       -> Partial Aggregate
            -> Hash Join
                 Hash Cond: (e.customer_id = c.customer_id)
                 -> Parallel Seq Scan on events e
                 -> Hash
                      -> Seq Scan on customers c
~~~

Ở một số cấu trúc, **mỗi worker** có thể xây hoặc sử dụng bản sao/chiến lược hash phù hợp cho inner side nhỏ. `Hash Join` ở dưới Gather không có nghĩa bản thân nó là `Parallel Hash Join` được chia xây bảng băm chung.

### 18.2. Parallel Hash Join

Khi PostgreSQL chọn `Parallel Hash`/`Parallel Hash Join`, các participants có thể phối hợp **xây shared hash table** thay vì mỗi worker tự xây bản sao riêng. Đây là một tối ưu khác của parallel query, liên quan nhưng không đồng nghĩa với Parallel Seq Scan.

### 18.3. Phân biệt song song ở các nhánh

Quan sát vị trí của `Gather`. Nếu một join nằm **phía trên Gather**, một phần join đó có thể do **leader** xử lý, còn scan phía dưới là parallel. Nếu join nằm **dưới Gather**, nó thuộc phần plan được participants thực thi, nhưng cách chia việc cụ thể phụ thuộc node và loại join.

**Kỹ năng đọc plan:** xác định *ranh giới Gather*, rồi mới đánh giá node nào thực sự chạy trong workers.

## 19. Cấu hình song song: các tham số quan trọng

PostgreSQL có nhiều cấu hình liên quan. Các giá trị mặc định trong bảng là giá trị **tham khảo thường gặp ở PostgreSQL hiện đại**, không phải cam kết trên server của bạn.

| Tham số | Mặc định thường gặp | Ý nghĩa chính |
| --- | ---: | --- |
| `max_parallel_workers_per_gather` | 2 | Số workers tối đa được yêu cầu cho một Gather/Gather Merge |
| `max_parallel_workers` | 8 | Số parallel query workers có thể hoạt động trên instance |
| `max_worker_processes` | 8 | Giới hạn worker processes nền ở mức rộng hơn |
| `parallel_setup_cost` | 1000 | Chi phí planner ước tính khi thiết lập parallel worker plan |
| `parallel_tuple_cost` | 0.1 | Chi phí planner ước tính để chuyển tuple từ worker tới leader |
| `min_parallel_table_scan_size` | 8 MB | Ngưỡng kích thước liên quan lập kế hoạch parallel table scans |
| `min_parallel_index_scan_size` | 512 kB | Ngưỡng kích thước liên quan lập kế hoạch parallel index scans |
| `parallel_leader_participation` | on | Cho phép leader tham gia phần parallel plan |
| `enable_parallel_hash` | on | Cho phép planner cân nhắc Parallel Hash |
| `enable_parallel_append` | on | Cho phép planner cân nhắc Parallel Append |

### 19.1. Xem cấu hình hiện tại

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
SHOW parallel_setup_cost;
SHOW parallel_tuple_cost;
SHOW min_parallel_table_scan_size;
SHOW min_parallel_index_scan_size;
SHOW parallel_leader_participation;
~~~

Có thể xem nguồn giá trị (default/config/session) trong `pg_settings`:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context
FROM pg_catalog.pg_settings
WHERE name IN (
    'max_parallel_workers_per_gather',
    'max_parallel_workers',
    'max_worker_processes',
    'parallel_setup_cost',
    'parallel_tuple_cost',
    'min_parallel_table_scan_size',
    'min_parallel_index_scan_size',
    'parallel_leader_participation'
)
ORDER BY name;
~~~

### 19.2. max_parallel_workers_per_gather

~~~sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 4;

EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events;

ROLLBACK;
~~~

Giá trị `4` cho phép planner cân nhắc tối đa 4 workers cho Gather, nhưng **không ép nhất thiết phải dùng 4 workers**. Planner còn xem chi phí/size và runtime có thể khởi chạy ít hơn.

### 19.3. Giới hạn toàn instance

`max_parallel_workers` và `max_worker_processes` là giới hạn chia sẻ giữa nhiều query/backend và những loại worker khác. Một server chạy 50 truy vấn đồng thời không thể đảm bảo mỗi query đều được cấp 4 workers nếu tổng quota chỉ 8.

**Nếu nhiều query cùng tranh workers**, tăng `max_parallel_workers_per_gather` ở một query không làm hệ thống có thêm CPU vật lý.

### 19.4. min_parallel_table_scan_size

Nếu bảng quá nhỏ, planner thường không thấy lợi ích chia quét. Giảm ngưỡng có thể khiến những bảng nhỏ được xem xét cho parallel scan, nhưng đó chỉ là **điều kiện đầu vào cho costing**, không phải bắt buộc.

### 19.5. min_parallel_index_scan_size

Ngưỡng này liên quan lượng dữ liệu dự kiến trong parallel index scan, không nên hiểu máy sẽ launch workers nếu file index chỉ lớn hơn đúng 512 kB. Planner xem kích thước dữ liệu, scan selectivity và chi phí của toàn plan.

### 19.6. parallel_setup_cost và parallel_tuple_cost

Planner ước lượng:

- Chi phí khởi chạy/thiết lập parallel plan;
- Chi phí chuyển mỗi tuple qua Gather/Gather Merge.

Nếu query trả cực nhiều tuple, **chi phí chuyển hàng** có thể khiến planner chọn seq/serial path. Nếu query làm Partial Aggregate trước Gather, số tuple chuyển có thể rất ít nên parallel dễ có lợi hơn.

Giảm các tham số cost có thể thiên vị parallel nhưng cũng có thể khiến nhiều truy vấn nhỏ dùng workers không đáng, làm throughput toàn hệ thống kém đi.

## 20. Thực hành kiểm tra ảnh hưởng cấu hình, không sửa server-wide

Để tránh thay đổi server/những connection khác, dùng `SET LOCAL` trong transaction chỉ bao các câu `EXPLAIN`.

### 20.1. Kịch bản A — cố ý tắt parallel trong transaction

~~~sql
BEGIN;

SET LOCAL max_parallel_workers_per_gather = 0;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    COUNT(*),
    SUM(amount)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';

ROLLBACK;
~~~

Trong transaction này, planner không yêu cầu parallel workers qua Gather vì giới hạn `0`. Đây là baseline hữu ích để đo kế hoạch tuần tự.

### 20.2. Kịch bản B — cho phép và khuyến khích parallel trong lab

~~~sql
BEGIN;

SET LOCAL max_parallel_workers_per_gather = 4;
SET LOCAL min_parallel_table_scan_size = '1MB';
SET LOCAL parallel_setup_cost = 0;
SET LOCAL parallel_tuple_cost = 0;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    COUNT(*),
    SUM(amount)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';

ROLLBACK;
~~~

Các thiết lập này **thiên vị** kế hoạch parallel trên dữ liệu lab nhưng vẫn không tuyệt đối bắt buộc:

- Query phải parallel-safe.
- Global worker limits cho phép.
- Planner có thể có đường đi khác.
- Runtime có thể launch ít workers hơn planned.

### 20.3. Đừng dùng phép so “A chạy trước, B chạy sau” để kết luận ngay

Lần A có thể làm ấm shared buffers/OS cache; lần B chạy nhanh hơn dù cấu hình kém tối ưu. Hoặc ngược lại, hệ thống bị một workload khác cạnh tranh I/O.

So sánh nên:

1. Chạy nhiều lượt, xen kẽ/đổi thứ tự;
2. Thu `Execution Time`, `Buffers`, temp I/O và worker count;
3. Xác nhận **kết quả SQL giống nhau**;
4. Xem mức CPU/I/O và concurrency;
5. Đánh giá trung vị/phân phối latency thay vì chỉ một lần đo;
6. Đo **throughput toàn hệ thống**, không chỉ query riêng lẻ.

`EXPLAIN ANALYZE` còn có overhead đo đạc, đặc biệt với timing chi tiết; nếu cần khảo sát, có thể cân nhắc `TIMING OFF` để giảm một phần overhead đo:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*) FROM parallel_lab_273.events;
~~~

## 21. ALTER TABLE ... SET (parallel_workers) là gì?

PostgreSQL cho phép thiết lập reloption `parallel_workers` ở mức bảng để **gợi ý số workers** khi cân nhắc parallel scan:

~~~sql
-- Chỉ thực hành trong schema lab, có thể thay đổi metadata bảng.
ALTER TABLE parallel_lab_273.events
SET (parallel_workers = 4);
~~~

Sau đó:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events;
~~~

**Không coi reloption này là lệnh “cấp ngay 4 workers cho mọi SELECT”.** Số workers thực tế vẫn phải tuân thủ:

- Planner chọn có dùng parallel plan không;
- `max_parallel_workers_per_gather` và các giới hạn toàn instance;
- Parallel safety;
- Tài nguyên runtime;
- Cost và ràng buộc của toàn truy vấn.

### 21.1. Đặt lại reloption

~~~sql
ALTER TABLE parallel_lab_273.events
RESET (parallel_workers);
~~~

Không áp dụng `ALTER TABLE SET (parallel_workers)` rộng rãi cho production mà không đo concurrency, latency, worker starvation và tác động của các query khác.

### 21.2. Số workers không đồng nghĩa một worker cho mỗi partition

Nếu bảng được partition theo tháng, planner có thể dùng Parallel Append và những cách phân phối công việc khác. Đừng mặc định mỗi worker “sở hữu một partition” hoặc `parallel_workers=4` có nghĩa đúng 4 partition được quét đồng thời.

## 22. Tác động của LIMIT: ít hàng thường không cần nhiều workers

Một câu truy vấn:

~~~sql
SELECT
    event_id,
    occurred_at
FROM parallel_lab_273.events
ORDER BY event_id
LIMIT 10;
~~~

có thể dùng **Index Scan trên primary key** và dừng sau 10 hàng. Khởi chạy 4 workers để quét 1 triệu hàng rồi hợp nhất thường không có lợi.

Ngược lại:

~~~sql
SELECT
    event_id,
    amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 100000;
~~~

có thể phải xử lý/sắp xếp phần đáng kể dữ liệu. Planner có thể chọn các chiến lược khác nhau, bao gồm parallel scan + Gather Merge.

### 22.1. Tạo index theo ORDER BY

~~~sql
CREATE INDEX idx_events_amount_desc_273
ON parallel_lab_273.events (
    amount DESC,
    event_id DESC
);
~~~

Sau đó:

~~~sql
EXPLAIN
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 10;
~~~

Một `Index Only Scan`/`Index Scan` tuần tự theo index có thể rất nhanh cho LIMIT nhỏ. Đây là ví dụ **index đúng thứ tự có thể quan trọng hơn parallelism**.

### 22.2. OFFSET lớn có thể vẫn tốn công

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 20 OFFSET 500000;
~~~

Để trả trang thứ 25.001 theo kiểu OFFSET, executor vẫn phải bỏ qua nhiều hàng đã sắp xếp. Parallel scan/Gather Merge không tự làm `OFFSET` sâu trở thành miễn phí.

Với phân trang rất sâu, cân nhắc **keyset pagination** với khóa sắp xếp ổn định:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
WHERE (amount, event_id) < (500.00::numeric, 100000::bigint)
ORDER BY amount DESC, event_id DESC
LIMIT 20;
~~~

Đây là ví dụ điều kiện cho trang tiếp theo sau cặp khóa (`amount`, `event_id`) đã biết. Nó phù hợp với B-tree composite theo thứ tự và có thể tránh xử lý toàn bộ OFFSET sâu. Điểm chính: **tối ưu cách truy cập thường quan trọng hơn cố ép Gather Merge**.

## 23. Parallel safety: hàm và biểu thức có chạy trong worker được không?

Để PostgreSQL thực thi một node trong parallel worker, các phép toán tương ứng phải **an toàn đối với môi trường parallel execution**.

Hàm PostgreSQL có ba loại **parallel safety**:

| Khai báo | Mã trong `pg_proc.proparallel` | Ý nghĩa |
| --- | --- | --- |
| **`PARALLEL SAFE`** | `s` | Được phép chạy trong parallel worker |
| **`PARALLEL RESTRICTED`** | `r` | Chỉ nên/chỉ được thực thi ở leader, không trong worker |
| **`PARALLEL UNSAFE`** | `u` | Có thể khiến truy vấn không được chạy bằng parallel plan |

Phải phân biệt nhãn này với **volatility**:

| Nhãn | Trả lời câu hỏi |
| --- | --- |
| `IMMUTABLE` / `STABLE` / `VOLATILE` | Khi nào cùng đầu vào có thể tạo kết quả khác, hàm có side effects không? |
| `PARALLEL SAFE` / `RESTRICTED` / `UNSAFE` | Hàm có thể chạy trong worker song song hay chỉ leader/không được dùng cho parallel query? |

Một hàm có thể được khai báo `IMMUTABLE` nhưng `PARALLEL UNSAFE`; việc “bất biến về giá trị” **không tự chứng minh an toàn về transaction/session/worker state**.

### 23.1. Xem metadata bằng pg_proc

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid)
        AS arguments,
    CASE p.proparallel
        WHEN 's' THEN 'PARALLEL SAFE'
        WHEN 'r' THEN 'PARALLEL RESTRICTED'
        WHEN 'u' THEN 'PARALLEL UNSAFE'
    END AS parallel_safety,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.proname IN ('lower', 'random', 'clock_timestamp', 'now')
ORDER BY p.proname, arguments;
~~~

**Không suy đoán `proparallel` từ tên hàm**. Hàm overload có thể khác định nghĩa và metadata; đọc chữ ký cùng schema khi điều tra.

### 23.2. UDF mặc định không tự được coi là PARALLEL SAFE

Hàm do người dùng tạo **mặc định được đánh dấu PARALLEL UNSAFE** nếu không có khai báo khác, vì PostgreSQL không thể tự chứng minh mọi thao tác nội bộ của hàm an toàn trong workers.

Ví dụ một hàm đơn giản chỉ tính số:

~~~sql
CREATE FUNCTION parallel_lab_273.double_amount(value NUMERIC)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT value * 2
$$;
~~~

Truy vấn:

~~~sql
EXPLAIN
SELECT SUM(parallel_lab_273.double_amount(amount))
FROM parallel_lab_273.events
WHERE event_type = 'purchase';
~~~

Hàm này chỉ nhân một giá trị numeric nên việc khai báo `PARALLEL SAFE` có cơ sở. Tuy nhiên, việc thực tế xuất hiện parallel plan còn phụ thuộc toàn truy vấn và planner; đôi khi SQL function được inline nên bạn không thấy tên hàm riêng trong cây plan.

### 23.3. Những thao tác cần rất cẩn trọng

Theo hướng dẫn PostgreSQL về parallel safety, hãy đánh dấu **UNSAFE** cho hàm có thể:

- Sửa trạng thái database không phù hợp chạy song song;
- Thực hiện thay đổi transaction state;
- Truy cập sequence hay trạng thái session/worker không an toàn theo hợp đồng;
- Phụ thuộc các thao tác mà PostgreSQL không cho phép trong worker;
- Tạo ảnh hưởng side effect mà nhiều worker gọi đồng thời sẽ làm sai.

Hàm truy cập temporary tables, trạng thái local của backend, cấu hình, cursor, hoặc hành vi chỉ hợp lệ ở leader có thể cần **RESTRICTED**, tùy thao tác cụ thể và tài liệu của phiên bản. **Không gắn nhãn SAFE chỉ để ép EXPLAIN có Gather**.

### 23.4. PARALLEL RESTRICTED khác UNSAFE

Một hàm **PARALLEL RESTRICTED** có thể được phép chạy trong query song song **nhưng không chạy bên dưới Gather** ở workers. Nếu query phải đánh giá hàm đó trong quá trình scan/filter dưới Gather, planner có thể cần di chuyển biểu thức lên leader hoặc từ chối parallel path tương ứng.

**PARALLEL UNSAFE** có thể chặn việc tạo parallel plan cho truy vấn chứa hàm. Vì vậy nhãn function là một trong những lý do quan trọng khiến query trên bảng lớn vẫn không có parallel scan.

### 23.5. Hàm gọi hàm khác vẫn phải được review

Một UDF ghi `PARALLEL SAFE` nhưng gọi tiếp một hàm có side effect không an toàn là **khai báo sai**. PostgreSQL không đảm bảo sẽ phân tích sâu mọi đường gọi/hành vi tương lai để bác bỏ nhãn đó.

Đặc biệt khi extension, PL/pgSQL, SQL dynamic hoặc các function thay đổi theo deployment, cần audit:

1. Có đọc/ghi database trong function không?
2. Có dùng sequence, temporary table, backend-local state, cursor không?
3. Có gọi function ngoài được đánh dấu UNSAFE/RESTRICTED không?
4. Có dùng API bên ngoài hoặc side effect không?
5. Chạy đồng thời nhiều process có tái lập cùng kết quả không?

### 23.6. Query dùng hàm bình thường có thể vẫn serial

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE some_custom_function(amount);
~~~

Nếu `some_custom_function` là hàm giả định có `PARALLEL UNSAFE`, plan có thể không dùng parallel worker dù bảng hàng triệu hàng. **Đây không phải bằng chứng PostgreSQL không có tính năng parallel scan**, mà có thể là sự lựa chọn đảm bảo an toàn.

## 24. Giới hạn và tình huống không tạo parallel plan

PostgreSQL không parallelize mọi câu SQL. Các trường hợp có thể hạn chế/bỏ parallel plan bao gồm:

- Câu lệnh chứa thao tác **sửa dữ liệu** hoặc khóa dữ liệu không phù hợp song song;
- Hàm hoặc biểu thức **PARALLEL UNSAFE**;
- Truy cập cấu trúc chỉ có trong backend/session và không an toàn cho workers;
- Những dạng cursor/statement có thể thực thi từng phần theo cơ chế không hỗ trợ parallel;
- Một số tính năng đặc thù của transaction, DDL, temporary tables, query structure;
- Chi phí ước tính không đủ để parallel có lợi;
- Worker limits, transaction state hoặc cấu hình bị giới hạn.

### 24.1. Không suy ra INSERT/UPDATE được parallel hóa như SELECT

~~~sql
UPDATE parallel_lab_273.events
SET amount = amount + 1
WHERE event_type = 'purchase';
~~~

**Không chạy câu này trong lab nếu không muốn ghi lại 300.000 hàng.** Nó minh họa thao tác DML, không phải một query để thử parallel scan.

PostgreSQL đặt các giới hạn riêng cho parallel query có thao tác sửa dữ liệu. Trong nhiều phiên bản, một câu lệnh ghi ở top level không dùng parallel plan như một `SELECT` thuần. Một số đường thực thi SELECT phục vụ những câu lệnh tạo bảng/vật hóa có ngoại lệ theo phiên bản; phải đối chiếu tài liệu cụ thể.

**Không ép quy tắc “SELECT parallel thì UPDATE cùng WHERE cũng parallel”.**

### 24.2. SELECT ... FOR UPDATE

~~~sql
-- Chỉ minh họa; không chạy trên dữ liệu lớn:
-- SELECT *
-- FROM parallel_lab_273.events
-- WHERE event_id = 1
-- FOR UPDATE;
~~~

`FOR UPDATE` yêu cầu khóa row và dùng cơ chế phù hợp với backend/transaction. Nó có thể hạn chế parallel execution. Hãy phân biệt query phục vụ **đọc phân tích** với query cần **khóa để ghi**.

### 24.3. Temporary table và state của session

Parallel workers không đơn giản là các threads sử dụng toàn bộ temporary state của backend leader. Truy cập temporary tables có những hạn chế với parallel execution; một query chỉ quét temporary table thường không thể được parallelize như quét một permanent table bình thường.

Không đánh dấu các UDF truy cập temporary table thành `PARALLEL SAFE` chỉ để “chạy nhanh”; kết quả có thể lỗi hoặc sai.

### 24.4. CTE và barrier

Một số Common Table Expressions (đặc biệt data-modifying CTE hoặc những trường hợp phải materialize/đánh giá theo cách riêng) có thể ngăn planner đẩy phép toán xuống parallel subtree. Nhưng **không nên khái quát rằng “cứ có WITH là không parallel”**: một CTE SELECT đơn giản có thể được inline/optimized và query vẫn có parallel plan tùy PostgreSQL/version.

~~~sql
EXPLAIN
WITH recent AS (
    SELECT customer_id, amount
    FROM parallel_lab_273.events
    WHERE event_type = 'purchase'
)
SELECT COUNT(*)
FROM recent;
~~~

Đọc **cây plan thật** để xác định optimizer đã đặt ranh giới Gather ở đâu.

### 24.5. Function safety và Row-Level Security

Các chính sách Row-Level Security, security-barrier views, hàm trong điều kiện truy cập và quy tắc security có thể ảnh hưởng việc planner đẩy điều kiện xuống nơi thực thi. Đừng thay đổi chính sách bảo mật chỉ để có parallel plan. Mục tiêu trước hết là giữ **đúng quyền truy cập và tính đúng**.

### 24.6. Parallel query không phải distributed query

Parallel workers ở đây chạy trong **một PostgreSQL server/instance** để xử lý query của một leader; chúng không tự chia truy vấn sang nhiều server vật lý/standby hoặc nhiều database shard.

~~~text
PostgreSQL Parallel Query:
  1 instance
  1 leader backend
  N parallel worker processes

Không đồng nghĩa:
  1 query được phân tán tự động
  tới nhiều PostgreSQL replicas/shards
~~~

Để xử lý phân tán nhiều node cần kiến trúc khác (FDW/sharding/analytics distributed engine...) và có kế hoạch riêng, không suy từ node `Gather`.

## 25. Công thức hiệu năng: tăng workers có giới hạn

Để có trực giác, hãy tách thời gian truy vấn:

\[
T_{\text{query}}
\approx
T_{\text{setup}}
+
T_{\text{parallel work}}
+
T_{\text{transfer/merge}}
+
T_{\text{serial part}}
\]

Đây là **mô hình tư duy gần đúng**, không phải công thức mà PostgreSQL planner trực tiếp tính đúng bằng thời gian thực.

### 25.1. Speedup có giới hạn của phần tuần tự

Giả sử 70% thời gian tính toán có thể chia đều cho `N` workers, còn 30% buộc chạy tuần tự. Lý tưởng hóa:

\[
S(N) \leq \frac{1}{0.3 + 0.7/N}
\]

Với 4 workers:

\[
S(4) \leq \frac{1}{0.3 + 0.7/4}
\approx 2.11
\]

Đó là giới hạn **lý tưởng** chưa tính overhead; ngoài thực tế còn chi phí workers, IPC, contention và xử lý ở leader. Không thể mặc định 4 workers cho tốc độ ×4.

### 25.2. Query trả quá nhiều dòng

~~~sql
SELECT event_id, customer_id, amount, payload
FROM parallel_lab_273.events;
~~~

Nếu client cần nhận đủ 1 triệu hàng và payload dài, **leader/đường kết nối client** có thể trở thành điểm nghẽn. Parallel Seq Scan nhanh hơn không nhất thiết giảm thời gian end-to-end nhiều, vì các workers vẫn phải chuyển mọi tuple về leader.

### 25.3. Query tổng hợp giảm chi phí chuyển tuple

~~~sql
SELECT COUNT(*), SUM(amount)
FROM parallel_lab_273.events;
~~~

Với `Partial Aggregate`, mỗi worker chỉ gửi kết quả partial nhỏ thay vì hàng triệu dòng. Do đó câu query aggregation thường có nhiều cơ hội hưởng lợi từ song song hơn một query chỉ “SELECT *”.

### 25.4. I/O bottleneck

Nếu cả bảng không ở cache và disk chỉ cung cấp một mức throughput nhất định, nhiều workers cùng đọc có thể **không tăng tổng throughput I/O**. Họ có thể còn cạnh tranh với autovacuum/checkpointer/những query khác.

### 25.5. CPU bottleneck

Nếu server có 8 cores mà 10 request cùng dùng 4 workers + leader, số backend/worker active có thể vượt xa số cores. Context switching và contention có thể khiến throughput/latency xấu hơn.

### 25.6. Worker starvation

Một query lúc ít tải có `Workers Launched: 4` nhưng giờ cao điểm chỉ launch 0–1 worker. Khi đo hiệu năng, phải ghi lại **actual worker count**, không so hai Execution Time mà bỏ qua khác biệt tài nguyên thực tế.

## 26. Memory: work_mem là ngân sách theo operation, không phải theo query

`work_mem` không phải giới hạn tổng RAM cho một câu SELECT. Sort, hash và các operation có thể dùng bộ nhớ riêng trong mỗi participant.

Ví dụ:

~~~text
Query có Gather Merge:

  Worker 1: Sort -> dùng work_mem theo operation
  Worker 2: Sort -> dùng work_mem theo operation
  Worker 3: Sort -> dùng work_mem theo operation
  Leader  : có thể cũng thực thi partial Sort
  Leader  : Gather Merge + các node khác
~~~

Do đó, tăng `max_parallel_workers_per_gather` cùng `work_mem` có thể **nhân nhu cầu RAM tối đa** của workload. Hash operations còn có các quy tắc riêng như `hash_mem_multiplier`.

### 26.1. Quan sát spill-to-disk của Sort

Trong `EXPLAIN ANALYZE`:

~~~text
Sort Method: quicksort  Memory: ...
~~~

thường cho biết sort dùng memory; còn:

~~~text
Sort Method: external merge  Disk: ...
~~~

cho thấy đã dùng bộ nhớ tạm trên đĩa. Parallel plan có thể có số liệu **theo worker**, vì từng worker sort phần dữ liệu riêng.

### 26.2. Một cấu hình thử nghiệm an toàn

~~~sql
BEGIN;

SET LOCAL work_mem = '32MB';
SET LOCAL max_parallel_workers_per_gather = 3;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 100000;

ROLLBACK;
~~~

Trong lab, thay `work_mem` có thể làm thay đổi phương thức Sort và plan. **Không suy rằng tăng tới vài GB luôn tốt**: nhiều query song song có thể dùng rất nhiều RAM và gây OOM/swap.

### 26.3. Temp file và query log

Ở môi trường có giám sát phù hợp, các số liệu:

- `Buffers: temp read=... written=...`;
- `Sort Method` và kích thước Disk;
- `pg_stat_database.temp_files`/`temp_bytes`;
- `log_temp_files` nếu DBA cấu hình;

có thể giúp hiểu vì sao plan parallel có Sort tốn thời gian. Chúng cần được đối chiếu với query thật và mức load hệ thống.

## 27. Đọc actual rows, loops và thống kê từng worker

`EXPLAIN (ANALYZE, VERBOSE)` trên parallel plan có thể trông như:

~~~text
Gather (actual time=... rows=300000 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  -> Parallel Seq Scan on events
       (actual time=... rows=100000 loops=3)
       Filter: (event_type = 'purchase')
       Rows Removed by Filter: ...
       Worker 0: actual time=... rows=...
       Worker 1: actual time=... rows=...
~~~

### 27.1. actual rows bên dưới Gather

Khi một node thực thi nhiều lần, `rows` trong EXPLAIN ANALYZE thường là **số hàng trung bình trên một lần thực thi node**, còn `loops` là số lần node chạy. Với parallel nodes, các participants đóng góp vào số lần/thống kê được tổng hợp.

Ví dụ giả định:

~~~text
Parallel Seq Scan: actual rows=100000 loops=3
Gather:            actual rows=300000 loops=1
~~~

Cho phép suy luận gần đúng tổng quét/đầu ra, nhưng **không phải trong mọi plan đều lấy `rows × loops` rồi hiểu là hàng duy nhất ở cấp query**, vì:

- `Filter` loại bớt;
- Node có thể được rescanned nhiều lần;
- Aggregation biến nhiều input thành ít output;
- Worker/leader có thể xử lý phân phối không đều;
- `loops` không luôn là `Workers Launched+1`.

### 27.2. Workers Planned/Launched chỉ ở Gather

Thông tin `Workers Planned` và `Workers Launched` thường xuất hiện tại `Gather`/`Gather Merge`, không phải ở mỗi scan node. Worker-level timing và rows có thể xuất hiện ở các node dưới Gather khi bật `ANALYZE, VERBOSE`.

### 27.3. Vì sao một worker xử lý nhiều hơn?

Có thể do:

- Khởi chạy workers không đồng thời;
- Leader bận thu tuple;
- Cạnh tranh CPU/IO;
- Cache/khả năng cung cấp dữ liệu khác nhau;
- Các phần dữ liệu có độ chọn lọc khác nhau;
- Thiết kế phân chia công việc hoặc node không hoàn toàn cân bằng.

Sự mất cân đối nhẹ không nhất thiết là bug. Nhưng nếu worker 0 làm gần hết việc còn others gần 0 và query chậm, cần điều tra nguyên nhân trước khi tăng worker count.

### 27.4. Loops của Partial Aggregate

~~~text
Finalize Aggregate
  -> Gather (rows=3)
       -> Partial Aggregate (rows=1 loops=3)
            -> Parallel Seq Scan ...
~~~

`Partial Aggregate` thường sinh **một trạng thái tổng hợp cho mỗi participant** với một aggregate không GROUP BY; vì thế số hàng đi qua Gather có thể gần số participants, chứ không phải 300.000 purchase rows.

### 27.5. Cost và thời gian không cùng đơn vị

~~~text
cost=1000.00..25000.00
actual time=1.234..120.567
~~~

`cost` là **đơn vị ước lượng của planner**, không phải milliseconds. `actual time` là số đo thời gian thực tế trong lượt chạy EXPLAIN ANALYZE. Không lấy cost và actual time trừ trực tiếp để kết luận plan sai.

## 28. Nhận diện nút nghẽn tại leader

Vì leader là nơi chuyển kết quả lên phía trên của plan, một query có thể có scan workers rất nhanh nhưng tổng thời gian vẫn dài:

~~~text
Parallel Seq Scan: đủ workers, nhiều hàng được đọc nhanh
             |
           Gather: phải xử lý luồng hàng lớn
             |
        Sort / Join / Aggregate phía trên
             |
           Client: nhận dữ liệu chậm
~~~

### 28.1. Dấu hiệu cần điều tra

- Rất nhiều rows được chuyển qua Gather;
- `Gather`/node phía trên chiếm thời gian lớn;
- Sort sau Gather spill ra disk;
- CPU leader cao hơn nhiều workers;
- Query trả `SELECT *`, payload lớn, client consume chậm;
- Parallel workers hoàn tất sớm nhưng query vẫn chờ phần xử lý còn lại;
- Throughput chung giảm khi tăng per-gather workers.

### 28.2. Cách cải thiện có thể phù hợp hơn tăng workers

- Đẩy `WHERE` chọn lọc hợp lý trước Gather nếu planner/semantics cho phép;
- Dùng partial aggregation thay vì đưa hàng triệu hàng lên leader;
- Chọn index giúp không cần sort lớn;
- Chỉ SELECT những cột thực sự dùng;
- Dùng `LIMIT`/keyset pagination đúng nghiệp vụ;
- Cải thiện join condition/index/stats;
- Tối ưu client/server network và batch fetch;
- Giảm số query cạnh tranh nếu instance bị quá tải.

**Không có ý “ép” planner đặt một Aggregate dưới Gather bằng một parameter duy nhất.** Cần xem hàm aggregate có partial mode hay không, predicate có parallel-safe không, số nhóm và chi phí hợp lý.

## 29. Giám sát workers đang chạy

### 29.1. pg_stat_activity

Trên các phiên bản PostgreSQL hiện đại có cột `leader_pid` trong `pg_stat_activity`, có thể xem:

~~~sql
SELECT
    pid,
    leader_pid,
    backend_type,
    state,
    application_name,
    wait_event_type,
    wait_event,
    query
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'parallel worker'
   OR leader_pid IS NOT NULL
ORDER BY leader_pid NULLS FIRST, pid;
~~~

Nếu không thấy worker nào, có thể đơn giản vì **không có parallel query đang chạy đúng thời điểm quan sát**. Workers thường tồn tại trong thời gian thực thi query, không phải một đội worker cố định mãi mãi cho từng connection.

### 29.2. Dữ liệu theo worker trong EXPLAIN

Để hiểu phân phối công việc của **một query cụ thể**, `EXPLAIN (ANALYZE, VERBOSE, BUFFERS)` thường hữu ích hơn chỉ nhìn danh sách process tại một thời điểm.

### 29.3. Giới hạn quyền

Không phải mọi role xem được query text và thông tin phiên làm việc khác. Role giám sát nên có quyền được cấp theo chính sách (ví dụ `pg_monitor` nếu phù hợp), không cấp superuser chỉ để xem `pg_stat_activity`.

### 29.4. Backend type khác nhau

Phân biệt:

- `client backend` — kết nối phục vụ client;
- `parallel worker` — workers của parallel query;
- `autovacuum worker` — bảo trì bảng;
- `background writer` / `checkpointer` / `walwriter` — tiến trình hệ thống.

Không tính tất cả worker processes là parallel query workers khi điều tra `max_worker_processes`.

## 30. Tối ưu trong môi trường có nhiều request đồng thời

Một câu SELECT trên máy dev có thể chạy nhanh khi `max_parallel_workers_per_gather=8` nhưng production có hàng trăm requests đồng thời lại chậm hơn.

### 30.1. Concurrency và ngân sách CPU

Giả sử một instance có 8 CPU cores và 10 truy vấn nặng chạy đồng thời. Nếu mỗi query muốn 4 workers:

~~~text
10 leaders + 40 parallel workers = 50 processes muốn làm việc
trên 8 CPU cores (chỉ là yêu cầu giả định).
~~~

Hệ thống có thể không launch đủ 40 workers vì global limits, nhưng **nếu cấu hình quá rộng**, CPU contention, cache thrashing và context switching vẫn là rủi ro.

### 30.2. Latency của một query và throughput của hệ thống

Một thay đổi có thể:

- Giảm thời gian một query từ 2 giây xuống 1 giây khi chạy một mình;
- Nhưng làm throughput tổng thể giảm từ 100 req/s xuống 70 req/s khi nhiều query cùng tranh workers/RAM.

Chọn cấu hình dựa trên SLA/throughput và độ trễ ở tải thực, **không chỉ một EXPLAIN ANALYZE chạy không có cạnh tranh**.

### 30.3. Worker starvation và không ổn định độ trễ

Nếu query thiết kế dựa trên 4 workers nhưng lúc cao điểm chỉ launch 0, độ trễ có thể dao động mạnh. Một chiến lược gồm:

- Đặt per-gather limit có trách nhiệm;
- Giới hạn concurrency của những báo cáo nặng;
- Dùng replica đọc hoặc hệ phân tích riêng nếu kiến trúc cho phép;
- Chuyển truy vấn định kỳ sang pre-aggregation/materialized results khi phù hợp;
- Ưu tiên cải thiện query/index/filter trước khi nâng số workers;
- Đo thực tế Workers Launched.

### 30.4. Kế hoạch có thể thay đổi sau ANALYZE

Planner sử dụng thống kê. Sau `ANALYZE` hoặc khi dữ liệu phân phối khác, PostgreSQL có thể chọn từ Parallel Seq Scan sang Index Scan hay ngược lại. **Một plan khác sau khi dữ liệu đổi không tự là regression** — phải so latency/buffers/kết quả đúng.

### 30.5. Không dùng Gather Merge như một “cờ tối ưu”

Không có `SET enable_gather_merge=on` trong PostgreSQL thông thường như một lời giải mọi ORDER BY. Planner quyết định tạo Gather Merge khi tìm được **sorted partial paths** hợp lý. Thay vì cố tìm một công tắc riêng, hãy tối ưu index, sort key, query shape, costs và workload.

## 31. Các lỗi tư duy thường gặp khi đọc plan

| Cách hiểu sai | Điều đúng |
| --- | --- |
| “Parallel scan = mỗi worker quét lại toàn bộ bảng.” | Parallel-aware scan phối hợp chia các block/phần index |
| “Gather giữ thứ tự theo primary key.” | Gather **không bảo đảm thứ tự** |
| “Gather Merge luôn cần một Sort lớn ở leader.” | Nó merge **các luồng đã sort**, sort có thể nằm dưới Gather Merge |
| “Gather Merge là Merge Join.” | Một node gom sorted worker streams, một node join hai quan hệ |
| “ORDER BY luôn có Gather Merge.” | Có thể serial index scan, Sort trên Gather hoặc cách khác |
| “LIMIT 10 cần 10 workers để nhanh.” | Single index scan có thể dừng sớm, rẻ hơn |
| “Workers Planned: 4 nghĩa thực tế đã dùng 4.” | Phải xem `Workers Launched` ở `ANALYZE` |
| “Workers Launched < Planned là lỗi dữ liệu.” | Thường do runtime/global worker availability |
| “Số loops luôn bằng số workers.” | Leader có thể tham gia, node còn có rescan |
| “rows dưới Parallel Seq Scan là tổng hàng cả query.” | Cần xét loops/worker stats và node phía trên |
| “Node dưới Gather đều parallel-aware.” | Có node parallel-safe nhưng không tự chia việc |
| “Index có nghĩa planner sẽ chọn Parallel Index Scan.” | Cost/selectivity có thể ưu tiên scan khác |
| “Index Only Scan chắc chắn không đọc heap.” | Visibility map quyết định; xem `Heap Fetches` |
| “Bitmap Index Scan được tất cả workers chạy lại y hệt.” | Bitmap thường được leader xây, heap scan phối hợp song song |
| “Bitmap Heap Scan giữ thứ tự index.” | Không có bảo đảm order |
| “COUNT DISTINCT được cộng partial counts đơn giản.” | Distinct giữa workers cần xử lý trùng toàn cục, có giới hạn partial aggregate |
| “Tất cả SUM/aggregate đều có Partial/Finalize.” | Cần aggregate hỗ trợ partial mode |
| “Parallel query = query chạy qua nhiều replica.” | Đây là nhiều processes trong một PostgreSQL instance |
| “Bật nhiều workers luôn nhanh hơn.” | Có startup, memory, leader, CPU/IO contention |
| “work_mem là RAM tối đa cho toàn query.” | Nhiều sort/hash operations ở nhiều participants có ngân sách riêng |
| “SET parallel_setup_cost=0 luôn ép planner parallel.” | Chỉ thay đổi cost estimate, không vượt safety/giới hạn |
| “Một UDF IMMUTABLE là PARALLEL SAFE.” | Volatility và parallel safety là hai thuộc tính khác |
| “UDF mặc định được phép chạy trong worker.” | UDF mặc định PARALLEL UNSAFE trừ khi khai báo phù hợp |
| “EXPLAIN ANALYZE chỉ hiển thị, không chạy SQL.” | `ANALYZE` **thực thi câu SQL** |
| “Planner cost=10000 nghĩa là 10.000 ms.” | Cost không phải đơn vị thời gian |
| “Query SELECT * nhanh ở workers nên mạng không quan trọng.” | Leader vẫn phải trả tất cả tuple cho client |
| “Parallel chỉ giải quyết bằng tăng max_parallel_workers.” | Index/filter/query shape/concurrency cũng quan trọng |
| “Thêm ORDER BY đã đảm bảo stable pagination khi khóa trùng.” | Thêm tie-break key duy nhất |
| “Seq Scan trên bảng nhỏ chứng minh parallel index bị lỗi.” | Planner có thể chọn Seq Scan là hợp lý |

## 32. Tình huống chẩn đoán: nên nhìn node nào trước?

### Tình huống A — Query COUNT chậm, plan có Gather

~~~text
Finalize Aggregate
  -> Gather
       Workers Planned: 4
       Workers Launched: 4
       -> Partial Aggregate
            -> Parallel Seq Scan
~~~

Những câu hỏi cần trả lời:

1. `Parallel Seq Scan` đọc bao nhiêu buffers? Có I/O lớn không?
2. Mỗi participant có xử lý tương đối cân bằng không?
3. `Partial Aggregate` có giảm số tuple gửi về Gather như kỳ vọng không?
4. Tăng workers có làm giảm elapsed time hay chỉ tăng CPU?
5. Nếu query lặp nhiều, có index/filter/materialization nào tốt hơn không?

**Hướng đọc:** vì `Gather` chỉ nhận các partial aggregates nhỏ, đây có thể là parallel plan khá hiệu quả nếu bottleneck nằm ở quét/tính toán, không ở leader transfer.

### Tình huống B — Query ORDER BY chậm, Sort external merge

~~~text
Limit
  -> Gather Merge
       Workers Planned: 4
       -> Sort
            Sort Key: amount DESC, event_id DESC
            Sort Method: external merge  Disk: ...
            -> Parallel Seq Scan
~~~

Những điều cần cân nhắc:

- Workers đang sort bao nhiêu hàng? Có thể giảm bằng `WHERE`/`LIMIT`?
- Có B-tree composite index theo đúng `ORDER BY`/điều kiện đủ để tránh sort lớn không?
- `work_mem` có phù hợp với **concurrency tổng thể**, không chỉ một worker?
- Đã có index trên `(amount DESC,event_id DESC)` chưa?
- Việc dùng query với OFFSET lớn có buộc xử lý quá nhiều hàng không?

**Không mặc định tăng `work_mem` lên rất lớn** khi có nhiều query tương tự chạy đồng thời.

### Tình huống C — Planned 4, Launched 0

~~~text
Gather
  Workers Planned: 4
  Workers Launched: 0
  -> Parallel Seq Scan ...
~~~

Điều này cho biết planner định sử dụng workers nhưng thực thi **không launch được workers** ở lần đó. Cần kiểm tra worker limits, backend/worker hoạt động đồng thời và môi trường runtime. Không nên bắt đầu bằng việc tạo thêm index hoặc tăng `work_mem` vì nguyên nhân có thể là **worker starvation**.

### Tình huống D — Query có ORDER BY nhưng chỉ thấy Gather

~~~text
Sort
  Sort Key: occurred_at DESC
  -> Gather
       -> Parallel Seq Scan ...
~~~

Đây **không phải PostgreSQL bỏ qua ORDER BY**. `Sort` phía trên Gather đảm bảo thứ tự toàn cục. Muốn đánh giá hiệu năng, xem liệu sort có tốn RAM/temp I/O, và liệu Gather Merge hoặc index-ordered access có cost tốt hơn không.

### Tình huống E — Query trên bảng lớn vẫn Seq Scan

~~~text
Aggregate
  -> Seq Scan on events
~~~

Kiểm tra:

- `max_parallel_workers_per_gather` có bằng 0 không?
- Có UDF mặc định `PARALLEL UNSAFE` không?
- Có query shape/transaction mode không hỗ trợ parallel không?
- Thống kê cũ hoặc size estimate thấp không?
- `parallel_setup_cost`/`parallel_tuple_cost` có cao so với workload không?
- Có global worker limits thấp không?
- **Quan trọng nhất:** query tuần tự có thực sự vượt SLA không?

Nếu query chỉ chạy trong 2 ms, **không có Gather** có thể là điều hợp lý nhất.

### Tình huống F — Query có Parallel Index Only Scan nhưng Heap Fetches cao

~~~text
Parallel Index Only Scan using idx_events_customer_273
  Heap Fetches: 200000
~~~

Cần xem visibility map/all-visible, tần suất UPDATE, transaction dài giữ snapshot và tình trạng VACUUM. Không tạo thêm 4 workers rồi kỳ vọng heap fetches biến mất; **điều kiện visibility** khác với worker parallelism.

## 33. Bài tập thực hành

Các bài tập thực hiện trên schema `parallel_lab_273`. Khi một câu `EXPLAIN` không hiện đúng node dự đoán, đó **không nhất thiết là bài làm sai**. Hãy phân biệt **kết quả SQL cần đúng** với **plan phụ thuộc môi trường**, và diễn giải vì sao planner có thể có lựa chọn khác.

### Bài 1 — Đọc cây plan cơ bản

Cho:

~~~text
Finalize Aggregate
  -> Gather
       Workers Planned: 2
       -> Partial Aggregate
            -> Parallel Seq Scan on events
~~~

Hãy mô tả chức năng của từng node theo thứ tự **từ dưới lên**.

**Gợi ý:** quét dữ liệu → tính trạng thái aggregate cục bộ → Gather chuyển partial states → Finalize kết hợp.

### Bài 2 — Giải thích phân chia block

Một bảng có 10.000 heap blocks và dùng Parallel Seq Scan với 3 workers cùng leader.

**Câu hỏi:** PostgreSQL có buộc mỗi process quét đúng 2.500 block cố định không? Tại sao điều phối động có thể tốt hơn phân chia cứng?

### Bài 3 — Đếm purchases

Chạy:

~~~sql
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';
~~~

**Kỳ vọng trên dữ liệu mẫu:** 300.000.

Sau đó chạy `EXPLAIN` và xác định có `Partial Aggregate`/`Gather` không.

### Bài 4 — Cấu hình xem mức song song

Chạy:

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
~~~

**Câu hỏi:** nếu per-gather=4 nhưng max_parallel_workers=2 thì một query có thể chắc chắn launch 4 không?

**Đáp án:** không, vì global limit và availability.

### Bài 5 — Planned khác Launched

Đọc:

~~~text
Workers Planned: 4
Workers Launched: 2
~~~

**Câu hỏi:** câu nào cho biết dự kiến của planner, câu nào cho biết thực tế executor? Nêu ba lý do khiến số thực tế nhỏ hơn.

### Bài 6 — So sánh EXPLAIN và EXPLAIN ANALYZE

Viết hai câu:

~~~sql
EXPLAIN SELECT COUNT(*) FROM parallel_lab_273.events;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*) FROM parallel_lab_273.events;
~~~

**Câu hỏi:** câu nào chạy thật? Trường hợp nào cần tránh `ANALYZE` vì tác động ghi?

### Bài 7 — Bật/tắt parallel bằng SET LOCAL

Trong hai transaction lab, chạy cùng `COUNT(*)` nhưng với `max_parallel_workers_per_gather=0` và `=4`. So sánh plan/time/buffers.

**Kết luận cần nêu:** cho phép 4 workers không bảo đảm planner/runner sử dụng đủ 4.

### Bài 8 — Gather không đảm bảo order

Cho hai worker:

~~~text
A: 1,3,5
B: 2,4,6
~~~

Liệt kê một đầu ra **hợp lệ về tập hàng** của `Gather` nhưng **không sorted**. Giải thích vì sao SQL cần `ORDER BY` khi đòi thứ tự.

### Bài 9 — Gather Merge

Cùng hai luồng sorted ở bài 8, kết quả `Gather Merge` theo ASC sẽ là gì?

**Đáp án:** `1,2,3,4,5,6`.

### Bài 10 — Sort trên Gather so với Sort dưới Gather Merge

Vẽ hai cây:

~~~text
Sort -> Gather -> Parallel Seq Scan
Gather Merge -> Sort -> Parallel Seq Scan
~~~

**Câu hỏi:** ở sơ đồ nào leader có một Sort toàn cục, ở sơ đồ nào participants sort trước khi merge? Vì sao hai kiểu đều có thể đúng?

### Bài 11 — ORDER BY có tie

Trên dữ liệu mẫu có nhiều dòng cùng `amount`, so sánh:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC
LIMIT 20;
~~~

với:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 20;
~~~

**Câu hỏi:** phiên bản nào có tie-breaker xác định? `Gather Merge` có tự thêm tie-breaker không?

### Bài 12 — Thêm index đúng order

Tạo B-tree `(amount DESC, event_id DESC)` và `EXPLAIN` cho `ORDER BY amount DESC, event_id DESC LIMIT 10`.

**Câu hỏi:** tại sao single Index Scan/Index Only Scan có thể thắng parallel scan + sort với LIMIT rất nhỏ?

### Bài 13 — Parallel Index Scan

Tạo index `(occurred_at)` rồi chạy `EXPLAIN` cho một query range trên thời gian.

**Câu hỏi:** sự khác biệt giữa `Index Scan`, `Parallel Index Scan` và `Parallel Seq Scan` nằm ở đường truy cập và cơ chế chia việc nào?

### Bài 14 — Parallel Index Only Scan

Trên B-tree `(customer_id)`, chạy `EXPLAIN (ANALYZE, BUFFERS)` của query count theo range customer ID.

**Câu hỏi:** nếu plan có `Parallel Index Only Scan` mà `Heap Fetches` lớn, có phải PostgreSQL đã đặt tên node sai không?

**Đáp án:** không; cần kiểm tra visibility map và heap visibility checks.

### Bài 15 — Parallel Bitmap Heap Scan

Cho:

~~~text
Gather
 -> Parallel Bitmap Heap Scan
      Recheck Cond: ...
      -> Bitmap Index Scan
~~~

**Câu hỏi:** phần nào phối hợp nhiều workers, phần tạo bitmap thường do ai thực hiện? Tại sao đây không phải mỗi worker tạo bitmap riêng?

### Bài 16 — Bitmap và thứ tự

Một query lọc qua Bitmap Heap Scan nhưng yêu cầu `ORDER BY customer_id`. Có cần thêm `Sort` không?

**Gợi ý:** bitmap scan không bảo đảm thứ tự; PostgreSQL phải có đường đáp ứng order, có thể là Sort hoặc scan khác.

### Bài 17 — Lossy bitmap

Đọc `EXPLAIN ANALYZE` có:

~~~text
Heap Blocks: exact=... lossy=...
Rows Removed by Index Recheck: ...
~~~

**Câu hỏi:** vì sao lossy pages tăng khi bitmap memory thiếu? `Recheck Cond` bảo vệ tính đúng thế nào?

### Bài 18 — Partial Aggregate

Giả sử ba participants đếm purchases lần lượt `95.000`, `110.000` và `95.000`.

**Câu hỏi:** `Finalize Aggregate` trả bao nhiêu? Gather chuyển bao nhiêu partial count rows thay vì bao nhiêu purchase rows?

**Đáp án:** 300.000; về logic là ba kết quả count cục bộ thay vì 300.000 hàng purchase.

### Bài 19 — COUNT(DISTINCT)

Vì sao không thể đơn giản cộng `COUNT(DISTINCT customer_id)` của hai workers nếu một customer có ở cả hai?

**Gợi ý:** duplicate xuất hiện giữa partitions, cần phối hợp loại trùng toàn cục hoặc trạng thái phù hợp.

### Bài 20 — GROUP BY và Gather Merge

Thực hiện:

~~~sql
EXPLAIN
SELECT customer_id, COUNT(*)
FROM parallel_lab_273.events
GROUP BY customer_id
ORDER BY customer_id;
~~~

**Bài tập:** nếu thấy `Finalize GroupAggregate -> Gather Merge`, giải thích vì sao đầu vào phải sorted theo `customer_id`. Nếu chỉ thấy `HashAggregate + Sort`, tại sao đó vẫn là plan hợp lệ?

### Bài 21 — Partial HashAggregate

Cho 1.000.000 events nhưng chỉ 10.000 customer IDs. Vì sao aggregation cục bộ có thể giảm số tuple phải chuyển từ workers về Gather? Khi số nhóm gần bằng số hàng, lợi ích này thay đổi thế nào?

### Bài 22 — Parallel join

Chạy `EXPLAIN` cho query join `events` với `customers` và aggregate theo `segment`.

**Câu hỏi:** phân biệt `Hash Join` dưới Gather với `Parallel Hash Join`. Node nào quyết định chia nguồn scan?

### Bài 23 — Kiểm tra function safety

Truy vấn `pg_proc` để xem `proparallel` của hàm hệ thống. Một UDF có `provolatile='i'` nhưng `proparallel='u'` có tự được chạy trong worker không?

**Đáp án:** không; immutability và parallel safety là hai thuộc tính riêng.

### Bài 24 — UDF mặc định

Tạo function SQL chỉ nhân số nhưng **không ghi `PARALLEL SAFE`**. Sau đó so metadata với `parallel_lab_273.double_amount` đã khai báo safe.

**Câu hỏi:** vì sao UDF mặc định thường được đánh dấu UNSAFE? Cần xem xét điều gì trước khi sửa thành SAFE?

### Bài 25 — Temp table/parallel worker

Một developer muốn tạo UDF đọc temporary table của session leader rồi khai báo `PARALLEL SAFE`.

**Bài tập:** giải thích vì sao sai, và vì sao `PARALLEL RESTRICTED` hoặc thiết kế lại dữ liệu có thể phù hợp hơn tùy hàm.

### Bài 26 — work_mem theo operation

Một query có 4 workers, mỗi worker có Sort và Hash riêng, plus leader có node bổ sung. Vì sao không thể kết luận tổng RAM tối đa bằng **một** giá trị `work_mem`? Bạn sẽ xem metric nào để biết sort đã spill ra disk?

### Bài 27 — Worker starvation

Trong lab ít tải, query launch 4 workers và chạy 0,8 giây. Giờ cao điểm, cùng SQL và plan chỉ launch 1 worker, chạy 2,4 giây.

**Câu hỏi:** yếu tố runtime nào giải thích khác biệt? Vì sao không thể đánh giá tuning chỉ từ Workers Planned?

### Bài 28 — CPU bottleneck và throughput

Một instance có 8 cores, 20 queries chạy đồng thời. Nhóm muốn đặt `max_parallel_workers_per_gather=8` để mọi query nhanh hơn.

**Bài tập:** nêu ít nhất năm rủi ro/lý do cần đo: workers toàn instance, contention CPU, memory, Gather overhead, I/O, throughput vs latency, worker starvation.

### Bài 29 — SET LOCAL và phạm vi transaction

Viết transaction:

~~~sql
BEGIN;
SET LOCAL parallel_setup_cost = 0;
SET LOCAL parallel_tuple_cost = 0;
EXPLAIN SELECT COUNT(*) FROM parallel_lab_273.events;
ROLLBACK;
~~~

**Câu hỏi:** sau ROLLBACK, các giá trị `SET LOCAL` còn áp dụng cho session không?

**Đáp án:** không; chúng chỉ có hiệu lực trong transaction.

### Bài 30 — Deep OFFSET

Giải thích vì sao `ORDER BY amount DESC, event_id DESC LIMIT 20 OFFSET 500000` phải xử lý/bỏ qua lượng lớn dữ liệu, và tại sao **keyset pagination** có thể phù hợp hơn.

### Bài 31 — Đọc actual rows/loops

Cho:

~~~text
Gather actual rows=300000 loops=1
Parallel Seq Scan actual rows=100000 loops=3
~~~

**Câu hỏi:** `rows=100000` ở scan là toàn query hay số trung bình mỗi lần node chạy? Vì sao không được lấy mọi `rows × loops` như “số hàng duy nhất” của toàn SQL?

### Bài 32 — Leader bottleneck

Một `Parallel Seq Scan` xử lý nhanh nhưng query `SELECT payload` trả 2 triệu dòng qua `Gather` rất chậm.

**Câu hỏi:** ngoài tăng workers, có những giải pháp nào? Gợi ý: giảm cột/dòng cần gửi, aggregate, pagination, index, client throughput.

### Bài 33 — Cost khác actual time

Với:

~~~text
cost=1000.00..20000.00
actual time=0.500..600.000
~~~

**Câu hỏi:** có thể nói “PostgreSQL dự đoán 20 giây” không?

**Đáp án:** không, `cost` là đơn vị mô hình ước tính, không phải ms.

### Bài 34 — Phân biệt parallel query và replication

Một báo cáo có `Gather Merge`. Nó có tự chạy trên hai standby replicas không? Vì sao câu trả lời khác với tính năng đọc replica/distributed SQL?

### Bài 35 — Code review tình huống tổng hợp

Đồng nghiệp đề xuất:

~~~sql
SET max_parallel_workers_per_gather = 16;
SET work_mem = '1GB';

SELECT *
FROM parallel_lab_273.events
ORDER BY amount DESC
LIMIT 50 OFFSET 200000;
~~~

Hãy chỉ ra ít nhất tám điểm phải xem:

1. Server có bao nhiêu CPU và workers toàn instance?
2. Có bao nhiêu query đồng thời?
3. `work_mem` có thể dùng nhiều lần theo node/participant không?
4. Vì sao `SELECT *` gửi nhiều payload?
5. Có index phù hợp `ORDER BY` không?
6. `OFFSET` sâu làm tăng khối lượng xử lý ra sao?
7. `ORDER BY amount` thiếu tie-break có ảnh hưởng phân trang không?
8. Planned vs Launched workers?
9. Benchmark plan/buffers/temp I/O trên dữ liệu thật?
10. Có nên thay bằng keyset pagination và chọn cột cần thiết?

**Đáp án định hướng:** tối ưu câu SQL/đường truy cập trước; không tăng cực lớn workers và work_mem chỉ để “ép query chạy song song”.

## 34. Quy trình phân tích một parallel plan trong thực tế

Một quy trình có thể dùng lại khi điều tra performance:

<escape>**Bước 1 — Xác định kết quả SQL cần có.**</escape> Có `ORDER BY` không? `LIMIT` cần tie-break không? Query có trả quá nhiều cột/hàng không?

<escape>**Bước 2 — Đọc plan từ dưới lên.**</escape> Phần truy cập là `Parallel Seq Scan`, `Parallel Index Scan`, `Parallel Index Only Scan` hay `Parallel Bitmap Heap Scan`? Có Filter/Recheck Cond không?

<escape>**Bước 3 — Tìm ranh giới Gather.**</escape> Node nào chạy dưới Gather trong parallel portion, node nào chạy ở leader phía trên?

<escape>**Bước 4 — Phân biệt Gather và Gather Merge.**</escape> Có yêu cầu thứ tự? Input streams đã sorted? Sort nằm dưới Gather Merge hay trên Gather?

<escape>**Bước 5 — Xác định Partial/Finalize.**</escape> Aggregate có được chia cục bộ không? Bao nhiêu partial rows phải chuyển về leader?

<escape>**Bước 6 — Xem Workers Planned/Launched.**</escape> Có thiếu workers khi runtime? Leader có tham gia không? Công việc có cân bằng không?

<escape>**Bước 7 — Xem actual stats.**</escape> `rows`, `loops`, filters, `Heap Fetches`, buffer hits/reads, temp I/O, worker sort methods, Execution Time.

<escape>**Bước 8 — Tìm bottleneck lớn nhất.**</escape> Quét I/O, sort, bitmap lossy, worker startup, leader transfer/merge, hash, client output, concurrency?

<escape>**Bước 9 — Chọn thay đổi nhỏ nhất.**</escape> Query rewrite, index, thống kê ANALYZE, giảm output, partial aggregation, worker limits, memory — theo bằng chứng.

<escape>**Bước 10 — Đo lại trên workload đại diện.**</escape> So serial vs parallel ở nhiều lần chạy, xem đồng thời latency và throughput, có kế hoạch rollback nếu regression.

### 34.1. Mẫu bảng ghi kết quả benchmark

| Thuộc tính cần ghi | Lượt A | Lượt B |
| --- | --- | --- |
| Query/parameters | Cùng SQL | Cùng SQL |
| Config | Parallel off | Parallel allowed |
| Plan root | `Aggregate` | `Finalize Aggregate` |
| Gather type | Không có | `Gather` |
| Workers planned | 0 | Theo EXPLAIN |
| Workers launched | 0 | Theo ANALYZE |
| Execution Time | Đo thực tế | Đo thực tế |
| Buffers shared hit/read | Đo thực tế | Đo thực tế |
| Temp disk | Đo thực tế | Đo thực tế |
| CPU / concurrency | Quan sát | Quan sát |
| Kết quả SQL | Phải tương đương | Phải tương đương |

Không điền “điểm chuẩn mặc định” cho thời gian. Phải dùng số đo từ môi trường thực tế.

### 34.2. Quyết định theo nhu cầu

| Workload | Điểm cần cân nhắc trước |
| --- | --- |
| `COUNT(*)` trên bảng lớn | Parallel Seq/Index Only Scan + Partial Aggregate |
| `GROUP BY` nhiều dữ liệu | Partial/Finalize Aggregate, Hash vs Group, Gather vs Gather Merge |
| `ORDER BY ... LIMIT` nhỏ | B-tree theo thứ tự, tránh sort/parallel startup không đáng |
| `ORDER BY` nhiều dòng | Gather Merge + local sorts hoặc Gather + global sort |
| Range index có số hàng vừa/lớn | Parallel Index Scan hoặc Bitmap Heap Scan tùy selectivity |
| Filter theo customer ID có B-tree tốt | Xem Index Scan/Index Only, visibility map |
| Query trả hàng triệu dòng | Leader transfer/client network, giảm output |
| Nhiều concurrent analytics queries | Worker quota toàn instance, RAM và throughput |
| UDF trong WHERE | `pg_proc.proparallel` và review parallel safety |
| Truy vấn dùng temp table/DML | Kiểm tra giới hạn parallel của dạng câu lệnh |

## 35. Tài liệu PostgreSQL chính thức

Nên đối chiếu tài liệu **đúng major version** đang dùng, vì parallel query planner, chỉ số `EXPLAIN` và các tính năng worker có thể thay đổi:

- [How Parallel Query Works](https://www.postgresql.org/docs/current/how-parallel-query-works.html): leader/workers, Gather và Gather Merge, cách phân tích song song.
- [Parallel Plans](https://www.postgresql.org/docs/current/parallel-plans.html): partial plan, Parallel Sequential Scan, Parallel Bitmap Heap Scan, Parallel Index/Index Only Scan, parallel joins và aggregates.
- [When Can Parallel Query Be Used?](https://www.postgresql.org/docs/current/when-can-parallel-query-be-used.html): những điều kiện giới hạn parallel plan.
- [Parallel Safety](https://www.postgresql.org/docs/current/parallel-safety.html): `PARALLEL SAFE`, `RESTRICTED`, `UNSAFE` và cách ghi nhãn UDF.
- [Parallel Query](https://www.postgresql.org/docs/current/parallel-query.html): tổng quan chương Parallel Query.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): cách xem plan, `ANALYZE`, `BUFFERS`, `VERBOSE` và `SETTINGS`.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): chi phí, actual rows/loops, scan methods, sort và phân tích.
- [Planner Cost Constants](https://www.postgresql.org/docs/current/runtime-config-query.html#RUNTIME-CONFIG-QUERY-CONSTANTS): `parallel_setup_cost`, `parallel_tuple_cost` và các cost parameters.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): `max_parallel_workers_per_gather`, `max_parallel_workers`, `max_worker_processes`, `work_mem`.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): khai báo parallel safety và volatility của UDF.
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW): backend types, leader PID và quan sát workers.
- [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): thứ tự index, `ORDER BY` và hiệu quả của `LIMIT`.
- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html): visibility map, heap fetches, INCLUDE và index-only performance.
- [Bitmap Scan / EXPLAIN examples](https://www.postgresql.org/docs/current/using-explain.html): `Bitmap Index Scan`, `Bitmap Heap Scan` và những plan lựa chọn theo chi phí.

Liên kết `/docs/current/` trỏ tới tài liệu của phiên bản ổn định hiện hành. Nếu hệ thống dùng một phiên bản PostgreSQL cụ thể, hãy chọn **bộ tài liệu có số version tương ứng** trước khi áp dụng những giới hạn cú pháp hoặc cấu hình.

## 36. Tổng kết

**Parallel query** giúp PostgreSQL sử dụng nhiều tiến trình cho **một truy vấn** khi khối lượng công việc đủ lớn và các phép toán an toàn để thực thi song song. Leader là backend phục vụ client; parallel workers cùng thực thi một **partial plan**, trong đó các node **parallel-aware** như `Parallel Seq Scan`, `Parallel Index Scan`, `Parallel Index Only Scan` và `Parallel Bitmap Heap Scan` có cơ chế phối hợp chia công việc thay vì mỗi worker xử lý lại toàn bộ dữ liệu.

Ở ranh giới phần song song, **`Gather`** thu kết quả về leader **không đảm bảo thứ tự toàn cục**. **`Gather Merge`** hợp nhất những luồng đã được sắp xếp theo cùng sort key, nhờ đó giữ thứ tự phục vụ `ORDER BY` hoặc `Finalize GroupAggregate`. Cả hai không tự giải quyết chuyện thiếu tie-break khi khóa sắp xếp trùng: nếu ứng dụng cần thứ tự tái lập, hãy ghi `ORDER BY` đầy đủ.

Với `COUNT`/`SUM` và những aggregates hỗ trợ partial mode, cấu trúc **`Partial Aggregate -> Gather -> Finalize Aggregate`** có thể giảm mạnh số tuple chuyển về leader. Trong khi đó, các truy vấn trả rất nhiều hàng hoặc phải sort lớn có thể bị giới hạn bởi **IPC, leader, bộ nhớ, I/O và client output**; tăng workers không đảm bảo tăng tốc.

Khi đọc `EXPLAIN`, hãy nhìn **Workers Planned** và **Workers Launched** riêng biệt, cùng `actual rows`, `loops`, buffer/temp I/O, `Heap Fetches`, Sort Method và vị trí của `Gather`. Kiểm tra chức năng **`PARALLEL SAFE`** của UDF và giới hạn query trước khi tìm cách ép planner dùng worker.

**Nguyên tắc thực hành:** tối ưu **tính đúng và cách truy cập dữ liệu** trước, sau đó mới điều chỉnh workers/cost/memory bằng số đo thực tế. Parallel scan, Gather và Gather Merge không phải những từ khóa “càng nhiều càng nhanh”, mà là những thành phần trong một kế hoạch được tối ưu để **chia công việc phù hợp, phối hợp kết quả đúng và giữ chi phí tổng thể ở mức hợp lý**.
