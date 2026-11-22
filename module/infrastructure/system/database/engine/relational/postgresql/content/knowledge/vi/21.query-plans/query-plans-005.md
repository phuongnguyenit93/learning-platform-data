# Sequential scan, index scan và bitmap scan trong PostgreSQL

## 1. Có chỉ mục rồi, tại sao PostgreSQL vẫn quét cả bảng?

Giả sử bảng `events` có 200.000 bản ghi và đã tạo chỉ mục trên cột `category`:

```sql
CREATE INDEX events_category_idx
ON scan_lab.events (category);
```

Ta chạy hai truy vấn:

```sql
-- Truy vấn A: gần như toàn bộ dữ liệu.
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'standard';

-- Truy vấn B: chỉ một nhóm tương đối nhỏ.
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

Cùng một cột, cùng một chỉ mục, nhưng PostgreSQL có thể chọn:

- **`Seq Scan`** cho A: đọc tuần tự các trang của bảng, kiểm tra điều kiện trên từng hàng.
- **`Bitmap Index Scan` + `Bitmap Heap Scan`** cho B: tìm các hàng liên quan qua chỉ mục, gom vị trí theo trang rồi đọc những trang bảng cần thiết.
- Hoặc **`Index Scan`** khi điều kiện chỉ tìm rất ít hàng, đặc biệt khi chỉ mục phù hợp và số lần đọc heap ngẫu nhiên nhỏ.

Tại sao? Bởi vì một chỉ mục **không tự động nhanh hơn** đọc bảng. PostgreSQL chọn kế hoạch dựa trên **ước lượng số hàng phù hợp, số trang phải đọc, tính phân bố vật lý, kiểu truy vấn, chi phí I/O, CPU, cache, yêu cầu sắp xếp và LIMIT**.

Bài học này giải thích ba phương án truy cập dữ liệu quan trọng nhất:

1. **Sequential scan** — đọc bảng lần lượt.
2. **Index scan** — đi từ chỉ mục đến hàng cần đọc.
3. **Bitmap scan** — dùng chỉ mục xác định tập trang/hàng rồi đọc heap theo cách ít ngẫu nhiên hơn.

Chúng là các **plan nodes** trong cây `EXPLAIN`, không phải ba kiểu câu lệnh SQL khác nhau.

> **Quy tắc cốt lõi:** PostgreSQL không hỏi “bảng này có index không?” rồi quyết định dùng index. Planner hỏi “trong các kế hoạch hợp lệ, kế hoạch nào được ước lượng có tổng chi phí thấp hơn cho toàn bộ truy vấn?”.

## 2. Mục tiêu sau bài học

Sau bài này, bạn có thể:

1. Nhận diện `Seq Scan`, `Index Scan`, `Index Only Scan`, `Bitmap Index Scan` và `Bitmap Heap Scan` trong `EXPLAIN`.
2. Phân biệt **truy cập heap tuần tự**, **lookup qua index đến heap** và **đọc heap theo bitmap**.
3. Giải thích **selectivity** và tại sao truy vấn trả nhiều hàng thường không cần index scan.
4. Đọc đúng `cost`, `rows`, `width`, `actual time`, `loops`, `Buffers`, `Index Cond`, `Filter` và `Recheck Cond`.
5. Hiểu bitmap exact/lossy, `Heap Blocks: exact/lossy` và `Rows Removed by Index Recheck`.
6. Giải thích `BitmapAnd` / `BitmapOr` khi có nhiều chỉ mục.
7. Hiểu vai trò của `ORDER BY` và `LIMIT` trong quyết định dùng index scan.
8. Biết khi nào `Index Only Scan` thực sự hạn chế truy cập heap nhờ visibility map.
9. Thực hành một bộ dữ liệu có thể tạo lại và so sánh nhiều kế hoạch.
10. Phân biệt **ước lượng của planner** với **thời gian thực tế của query**.
11. Biết ảnh hưởng của `ANALYZE`, thống kê phân bố dữ liệu, correlation, `work_mem` và tham số chi phí.
12. Tránh các giải pháp sai như ép vô hiệu hóa sequential scan trong production hoặc thêm index cho mọi cột.

## 3. Trước hết: PostgreSQL đọc gì khi truy vấn một bảng?

Một bảng PostgreSQL thông thường được lưu dưới dạng các **trang dữ liệu (*heap pages*)**. Mỗi trang chứa các tuple, cùng thông tin quản lý nội bộ.

Một chỉ mục B-tree lại có cấu trúc trang riêng, giúp tìm các khóa được lưu trong index. Đối với index scan thông thường, các index entries chỉ đến vị trí tuple trong heap.

Mô hình đơn giản:

```text
                         SQL query
                            |
                         Planner
                            |
                 Chọn một access path
                            |
           +----------------+----------------+
           |                |                |
           v                v                v
       Seq Scan         Index Scan        Bitmap path
           |                |                |
           v                v                v
      Heap pages       Index pages       Index pages
      đọc lần lượt          |                |
                            v                v
                       Heap tuple      Bitmap vị trí
                       theo TID              |
                                            v
                                       Heap pages
                                       theo tập cần đọc
```

### 3.1. TID là gì?

Một **tuple identifier (TID)** chỉ một vị trí vật lý của tuple, về khái niệm gồm **block number + offset** trong heap.

B-tree index entries có thể giúp truy cập tuple tương ứng qua vị trí này. Khi dùng index scan thường, PostgreSQL có thể cần truy cập heap để lấy những cột không có trong index và kiểm tra tính hiển thị MVCC.

**Không dùng TID làm khóa chính nghiệp vụ.** Vị trí vật lý có thể thay đổi do cập nhật hoặc tái tổ chức dữ liệu; ứng dụng nên dùng khóa chính logic.

### 3.2. “Index” không có nghĩa dữ liệu bảng nằm trong index

Một chỉ mục thông thường không lưu mọi cột của bảng. Nếu query yêu cầu:

```sql
SELECT event_id, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

và index chỉ có `account_id`, PostgreSQL phải đi từ index tới heap để lấy `payload`.

Ngoại lệ quan trọng là **Index Only Scan** khi **toàn bộ dữ liệu query cần** có trong index và điều kiện visibility được đáp ứng. Phần 14 sẽ phân tích kỹ.

### 3.3. “Scan” chỉ là một nút của kế hoạch lớn hơn

Ví dụ:

```text
Aggregate
  -> Bitmap Heap Scan on events
       -> Bitmap Index Scan on events_category_idx
```

Bộ máy có thể chọn scan path để tìm hàng, rồi những nút khác dùng kết quả để aggregate, join, sort hoặc limit.

Không nên đánh giá một scan node tách rời mà bỏ qua các yêu cầu của **toàn truy vấn**.

## 4. Chuẩn bị database thử nghiệm có thể lặp lại

Chỉ chạy trong database dành cho thực hành. Việc nạp 200.000 hàng, tạo chỉ mục và VACUUM có chi phí I/O/CPU; không chạy tùy tiện trên production.

### 4.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS scan_lab;

CREATE TABLE scan_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id integer NOT NULL,
    category text NOT NULL,
    status text NOT NULL,
    occurred_at timestamptz NOT NULL,
    amount numeric(12,2) NOT NULL,
    payload text NOT NULL
);
```

Bảng gồm:

- `event_id`: khóa chính, tự có B-tree index.
- `account_id`: ID tài khoản, nhiều sự kiện có cùng account.
- `category`: nhóm dữ liệu có tần suất rất khác nhau.
- `status`: trạng thái với độ phổ biến không đều.
- `occurred_at`: thời điểm sự kiện.
- `amount`: số tiền thử nghiệm.
- `payload`: cột văn bản để mô phỏng việc đọc nhiều dữ liệu từ heap.

### 4.2. Nạp 200.000 hàng

```sql
INSERT INTO scan_lab.events
    (
        account_id,
        category,
        status,
        occurred_at,
        amount,
        payload
    )
SELECT
    (g % 20000) + 1,
    CASE
        WHEN g % 11 = 0 THEN 'premium'
        ELSE 'standard'
    END,
    CASE
        WHEN g % 23 = 0 THEN 'FAILED'
        WHEN g % 5  = 0 THEN 'PENDING'
        ELSE 'DONE'
    END,
    timestamptz '2025-01-01 00:00:00+00'
        + (g * interval '1 minute'),
    (g % 10000)::numeric / 100,
    repeat('event-payload-', 10)
        || lpad(g::text, 7, '0')
FROM generate_series(1, 200000) AS s(g);
```

Bộ dữ liệu có tính chất hữu ích:

| Điều kiện | Độ phổ biến gần đúng |
| --- | ---: |
| `category = 'standard'` | Khoảng 91% |
| `category = 'premium'` | Khoảng 9% |
| `status = 'FAILED'` | Khoảng 4,3% |
| `status = 'PENDING'` | Khoảng 19% |
| `status = 'DONE'` | Khoảng 76% |
| `account_id = 4321` | Khoảng 10 hàng |
| `account_id BETWEEN 1000 AND 1499` | Khoảng 2,5% |

Các tỷ lệ chỉ là mô tả gần đúng của cách sinh dữ liệu; truy vấn đếm sẽ cho số cụ thể.

### 4.3. Cập nhật thống kê

```sql
ANALYZE scan_lab.events;
```

`ANALYZE` lấy mẫu thống kê để planner ước lượng số hàng của các điều kiện. Nếu không có thống kê đủ mới, planner có thể đánh giá sai tính chọn lọc.

### 4.4. Kiểm tra dữ liệu

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE category = 'premium'
    ) AS premium_rows,
    COUNT(*) FILTER (
        WHERE category = 'standard'
    ) AS standard_rows,
    COUNT(*) FILTER (
        WHERE status = 'FAILED'
    ) AS failed_rows,
    MIN(occurred_at) AS first_event,
    MAX(occurred_at) AS last_event
FROM scan_lab.events;
```

Lưu ý: câu query này **tự thực thi và quét dữ liệu**; nó phục vụ xác nhận dữ liệu trong lab, không phải bằng chứng về một kế hoạch tối ưu cố định.

### 4.5. Vì sao không in một kết quả EXPLAIN “chuẩn” duy nhất?

Cùng SQL có thể tạo kế hoạch khác nhau tùy:

- Phiên bản PostgreSQL.
- Kích thước bảng và index.
- Số hàng thực tế sau thay đổi.
- Thống kê `ANALYZE`.
- Thiết bị lưu trữ và tham số cost.
- Cache, parallel workers và `work_mem`.
- Index đã tồn tại tại thời điểm chạy.
- Cột được SELECT và ORDER BY/LIMIT.
- Mức chọn lọc giá trị, kể cả tham số của prepared statement.

Vì vậy, các plan bên dưới là **mẫu cấu trúc để nhận diện**, không phải cam kết rằng máy bạn sẽ chọn chính xác cùng node.

## 5. Đọc EXPLAIN trước khi tối ưu

`EXPLAIN` cho thấy kế hoạch mà PostgreSQL dự định thực thi mà **không thực thi câu SELECT** nếu không yêu cầu `ANALYZE`.

```sql
EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'standard';
```

Một kết quả minh họa:

```text
Seq Scan on events
  (cost=0.00..xxxx.xx rows=yyyy width=zzz)
  Filter: (category = 'standard'::text)
```

Các chữ `xxxx`/`yyyy`/`zzz` là ký hiệu minh họa, không phải số đo thực.

### 5.1. Ý nghĩa các phần thông dụng

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `Seq Scan` / `Index Scan` / `Bitmap Heap Scan` | Loại đường truy cập |
| `cost=A..B` | Chi phí ước lượng khởi động và tổng của node |
| `rows=N` | Số hàng đầu ra ước lượng của node |
| `width=W` | Độ rộng trung bình ước lượng của mỗi hàng đầu ra, tính theo byte |
| `Filter` | Điều kiện kiểm tra trên các hàng đã đến node |
| `Index Cond` | Điều kiện có thể dùng để giới hạn truy cập trong index |
| `Recheck Cond` | Điều kiện có thể cần kiểm tra lại khi đọc heap từ bitmap |
| `Rows Removed by Filter` | Số hàng bị loại ở bước filter trong ANALYZE |
| `Rows Removed by Index Recheck` | Số hàng bị loại khi recheck điều kiện index |
| `actual time` | Thời gian quan sát thực tế khi dùng ANALYZE |
| `actual rows` / `loops` | Hàng đầu ra thực tế và số lượt thực hiện |
| `Buffers` | Các khối truy cập trong hệ thống buffer/cache theo chỉ số EXPLAIN |

### 5.2. Cost không phải mili-giây

Ví dụ:

```text
cost=0.00..1340.00
```

không có nghĩa “mất 1340 ms”. Đây là **đơn vị chi phí của planner** dùng để so sánh kế hoạch, dựa trên các tham số I/O/CPU và thống kê.

`startup cost` là chi phí ước lượng trước khi node có thể trả hàng đầu; `total cost` là chi phí ước lượng khi node chạy đầy đủ theo mô hình planner.

Với `LIMIT`, chi phí trả vài hàng đầu có thể quan trọng hơn việc quét toàn bộ.

### 5.3. EXPLAIN ANALYZE thực sự chạy câu lệnh

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

`ANALYZE` yêu cầu **thực thi** câu SQL rồi ghi số hàng/thời gian thực tế.

**Cảnh báo:** với `INSERT`/`UPDATE`/`DELETE`, `EXPLAIN ANALYZE` **thực hiện cả thay đổi dữ liệu**.

Để khảo sát một lệnh UPDATE trong database lab mà không giữ thay đổi:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE scan_lab.events
SET amount = amount + 1
WHERE event_id = 1001;

ROLLBACK;
```

Rollback hủy thay đổi transactional, nhưng vẫn có thể có chi phí I/O, WAL, lock, sequence hoặc side effect ngoài database tùy câu lệnh/hàm được thực thi. Không coi `BEGIN...ROLLBACK` là giấy phép thử DML nguy hiểm trên production.

## 6. Sequential scan: đọc heap lần lượt

`Seq Scan` nghĩa là PostgreSQL đọc các trang của bảng theo đường quét heap và kiểm tra điều kiện trên các hàng có thể nhìn thấy.

Mô hình:

```text
Heap pages:
[0] [1] [2] [3] [4] [5] ... [N]
 |   |   |   |   |   |
 v   v   v   v   v   v
       Kiểm tra WHERE trên hàng
                |
                v
             Kết quả
```

### 6.1. Khi nào Seq Scan hợp lý?

Các tình huống phổ biến:

1. Query cần đọc **phần lớn hàng** trong bảng.
2. Bảng rất nhỏ và đọc vài trang rẻ hơn đi qua index rồi heap.
3. Điều kiện WHERE không có access path bằng index thích hợp.
4. Cột cần truy xuất nhiều, row width lớn; đi heap từng hàng qua index rất tốn.
5. Số hàng phù hợp cao khiến chi phí random heap access vượt chi phí đọc tuần tự.
6. Planner cân nhắc parallel scan hoặc các phương án join/aggregate toàn bảng.
7. Index tồn tại nhưng có độ chọn lọc quá thấp cho điều kiện.
8. Các bộ lọc biểu thức không phù hợp với index hiện có.

### 6.2. Query trả hầu hết sự kiện

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, payload
FROM scan_lab.events
WHERE category = 'standard';
```

Với dữ liệu lab, khoảng 91% hàng thỏa điều kiện. Nếu không có index `category`, sẽ dễ thấy `Seq Scan`. Ngay cả **sau khi tạo index**, planner vẫn có thể chọn Seq Scan vì cần trả về quá nhiều tuple.

Ví dụ phần kế hoạch:

```text
Seq Scan on events
  Filter: (category = 'standard'::text)
  Rows Removed by Filter: ...
  Buffers: shared hit=... read=...
```

Điều này **không tự chứng minh PostgreSQL bỏ qua index sai**.

### 6.3. Filter được áp dụng trong quá trình quét

```sql
SELECT event_id, amount
FROM scan_lab.events
WHERE amount >= 95.00;
```

Nếu không có index có thể dùng cho `amount`, Seq Scan vẫn có thể là kế hoạch hợp lý, vì PostgreSQL phải kiểm tra điều kiện trên các tuple được đọc.

Trong EXPLAIN, `Filter` thể hiện predicate được dùng để loại những hàng không phù hợp ở node đó.

### 6.4. Seq Scan không đồng nghĩa toàn bộ dữ liệu được đưa qua mạng

Nếu query dùng:

```sql
SELECT COUNT(*)
FROM scan_lab.events;
```

một Seq Scan có thể đọc bảng để đếm nhưng **không gửi 200.000 hàng cho client**. Nó đưa tuples lên một node `Aggregate`, rồi chỉ gửi một số đếm.

Phải phân biệt:

- Hàng được scan xử lý nội bộ.
- Hàng được node phát ra.
- Hàng cuối cùng trả về qua network.

### 6.5. PostgreSQL không mặc định lưu sẵn số hàng chính xác

Truy vấn `COUNT(*)` trên bảng lớn thường phải duyệt dữ liệu theo một cách phù hợp với MVCC visibility, chứ không chỉ đọc một bộ đếm tổng chính xác luôn được cập nhật.

Một số truy vấn COUNT có thể dùng `Index Only Scan` nếu index và visibility map thuận lợi, nhưng không phải vì B-tree chứa sẵn số lượng chính xác toàn bảng cho mọi snapshot.

## 7. Sequential scan trên bảng nhỏ thường là tối ưu

Tạo bảng tra cứu rất nhỏ:

```sql
CREATE TABLE scan_lab.event_types (
    event_type_id integer PRIMARY KEY,
    description text NOT NULL
);

INSERT INTO scan_lab.event_types
    (event_type_id, description)
VALUES
    (1, 'Payment'),
    (2, 'Refund'),
    (3, 'Adjustment');

ANALYZE scan_lab.event_types;
```

Thử:

```sql
EXPLAIN
SELECT *
FROM scan_lab.event_types
WHERE event_type_id = 2;
```

Dù có PRIMARY KEY và index, planner vẫn **có thể chọn Seq Scan**. Bảng chỉ vài hàng và vài trang; việc đọc toàn bộ có thể rẻ hơn thực hiện B-tree lookup.

**Không nên tạo thêm index hoặc ép index scan chỉ vì nhìn thấy Seq Scan trên bảng 3 hàng.** Kiểm tra chi phí thực tế trước khi kết luận đây là vấn đề hiệu năng.

## 8. Index Scan: tìm khóa trong index, rồi lấy hàng ở heap

Một `Index Scan` thông thường thường có hai phần:

1. Dùng index tìm các entries thỏa **Index Cond**.
2. Truy cập heap để lấy tuple, những cột còn thiếu và/hoặc kiểm tra visibility/filter.

Mô hình:

```text
B-tree index on account_id
           |
           v
     account_id = 4321
           |
      TID 1, TID 2, ...
           |
           v
   Heap page A, page F, page R ...
           |
           v
   Trả event_id, payload, ...
```

Nếu chỉ có vài kết quả, số lần truy cập heap nhỏ; index lookup có thể nhanh hơn quét toàn bộ bảng.

### 8.1. Thử trước với PRIMARY KEY

`event_id` là primary key, nên PostgreSQL có index sẵn. Truy vấn một hàng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, payload
FROM scan_lab.events
WHERE event_id = 12345;
```

Một cấu trúc có thể gặp:

```text
Index Scan using events_pkey on events
  Index Cond: (event_id = 12345)
  Buffers: shared hit=... read=...
```

Ở đây `event_id = 12345` là điều kiện được index hỗ trợ. Query lấy `payload` không có trong primary key index, nên thường cần truy cập heap.

### 8.2. Tạo index cho account_id

```sql
CREATE INDEX events_account_idx
ON scan_lab.events (account_id);

ANALYZE scan_lab.events;
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, occurred_at, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

Bộ dữ liệu sinh khoảng 10 sự kiện mỗi tài khoản. PostgreSQL có thể chọn `Index Scan using events_account_idx`.

### 8.3. Tại sao số hàng nhỏ phù hợp Index Scan?

Nếu chỉ cần 10 hàng từ 200.000 hàng:

- Đọc các index pages để định vị entries.
- Lấy khoảng 10 tuple ở heap.
- Không cần quét mọi heap page.

Ngược lại, nếu tìm 180.000 hàng:

- Có thể cần rất nhiều heap fetches.
- Các vị trí heap có thể nằm rải rác.
- Đọc tuần tự một lần có thể rẻ hơn nhiều lần truy cập rời rạc.

### 8.4. Index Cond và Filter

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, status, payload
FROM scan_lab.events
WHERE account_id = 4321
  AND status = 'DONE';
```

Nếu planner dùng chỉ mục `events_account_idx`, kế hoạch có thể thể hiện:

```text
Index Scan using events_account_idx on events
  Index Cond: (account_id = 4321)
  Filter: (status = 'DONE'::text)
  Rows Removed by Filter: ...
```

Giải thích:

- `Index Cond` dùng index để thu hẹp những entries cần xét.
- `Filter` kiểm tra điều kiện còn lại, thường trên những hàng đã được tìm.
- Một index trên `account_id` không tự chứa cấu trúc tìm kiếm cho mọi giá trị `status`.

Tùy schema/index và kế hoạch thực tế, điều kiện có thể phân chia khác đi.

### 8.5. Index Scan không phải lúc nào cũng đọc heap ngay theo thứ tự vật lý

B-tree thường sắp xếp index entries theo khóa. Nếu index cho một giá trị match các TID nằm rất xa nhau, index scan có thể tạo nhiều truy cập heap ngẫu nhiên.

Đây là một nguyên nhân quan trọng khiến PostgreSQL chọn **bitmap scan** khi số hàng match ở mức trung bình.

## 9. Bitmap scan: dùng index lập bản đồ rồi đọc heap

Đối với một điều kiện trả **không quá ít nhưng cũng không quá nhiều** hàng, một `Bitmap Heap Scan` có thể phù hợp.

Nó thường xuất hiện cùng một hoặc nhiều `Bitmap Index Scan`:

```text
Bitmap Heap Scan on events
  Recheck Cond: (category = 'premium'::text)
  -> Bitmap Index Scan on events_category_idx
       Index Cond: (category = 'premium'::text)
```

### 9.1. Hai giai đoạn thực thi

**Giai đoạn 1: tìm vị trí từ index**

`Bitmap Index Scan` đọc index để tìm các TID thỏa điều kiện. Thay vì ngay lập tức đọc từng heap tuple và trả cho node trên, nó xây **bitmap** mô tả các trang/hàng liên quan.

**Giai đoạn 2: đọc heap**

`Bitmap Heap Scan` đọc các heap blocks được bitmap xác định, thường theo **block order** để tránh truy cập heap rời rạc theo thứ tự index key.

Mô hình:

```text
B-tree index (category)
         |
  Find premium entries
         |
         v
 Bitmap of matching TIDs / heap blocks
         |
         v
 +-----------------------------------------+
 | heap block 4: offsets 2, 7               |
 | heap block 5: offsets 3                   |
 | heap block 9: offsets 1, 8, 11            |
 | ...                                      |
 +-----------------------------------------+
         |
         v
 Bitmap Heap Scan reads blocks 4, 5, 9...
         |
         v
 MVCC visibility + quals/recheck as required
         |
         v
 Output rows
```

### 9.2. Khi bitmap có thể tốt hơn Index Scan?

Giả sử có 18.000 premium rows rải trên nhiều heap pages. Một Index Scan thông thường có thể ghé heap theo thứ tự entries trong index, tạo nhiều random heap accesses.

Bitmap path gom những vị trí cần đọc trước, rồi xử lý heap theo trang. Nó trả giá bằng:

- Chi phí tạo bitmap ban đầu.
- Bộ nhớ bitmap.
- Mất khả năng giữ index key order trong đầu ra.
- Có thể phải recheck điều kiện.
- Không trả hàng sớm như index scan đơn giản trong nhiều trường hợp.

Vì vậy, bitmap không phải “index scan phiên bản luôn nhanh hơn”. Nó là một **sự đánh đổi khác**.

## 10. Thực hành Bitmap Index Scan và Bitmap Heap Scan

### 10.1. Tạo index cho category

```sql
CREATE INDEX events_category_idx
ON scan_lab.events (category);

ANALYZE scan_lab.events;
```

### 10.2. Query chọn khoảng 9% số hàng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, payload
FROM scan_lab.events
WHERE category = 'premium';
```

Một kế hoạch **có thể** là:

```text
Bitmap Heap Scan on events
  Recheck Cond: (category = 'premium'::text)
  Heap Blocks: exact=...
  Buffers: shared hit=... read=...
  -> Bitmap Index Scan on events_category_idx
       Index Cond: (category = 'premium'::text)
```

Vì khoảng 9% số hàng thỏa, bitmap path thường là một phương án có thể cạnh tranh với Index Scan và Seq Scan. Planner có quyền chọn kế hoạch khác theo ước lượng chi phí.

### 10.3. So lại cùng index với giá trị phổ biến

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, payload
FROM scan_lab.events
WHERE category = 'standard';
```

Khoảng 91% hàng match. Trong nhiều cấu hình, Seq Scan hợp lý hơn bitmap vì bitmap có thể phải xử lý gần như tất cả heap blocks.

### 10.4. Chọn ít hơn nữa

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

Số hàng ít, nên Index Scan có thể tiết kiệm hơn bitmap: không cần trả chi phí tạo bitmap cho 10 kết quả.

### 10.5. Chỉ một điểm dữ liệu không đủ để rút ra “ngưỡng phần trăm”

Không có quy tắc cố định rằng:

```text
< 1%  -> Index Scan
1-20% -> Bitmap Scan
> 20% -> Seq Scan
```

Các ngưỡng như trên chỉ là **kinh nghiệm suy đoán quá mức**, không phải luật PostgreSQL. Một bảng nhỏ, dữ liệu nằm trong cache, row width rộng, correlation cao hoặc yêu cầu `ORDER BY LIMIT` có thể thay đổi quyết định đáng kể.

## 11. Bitmap chính xác và bitmap mất chi tiết (*lossy*)

Bitmap có thể mô tả các tuple được chọn theo hai mức độ:

1. **Exact**: biết các vị trí tuple cần xét trong heap block.
2. **Lossy**: chỉ giữ thông tin ở cấp heap block, không đủ thông tin chỉ rõ toàn bộ offsets match.

Khi áp lực bộ nhớ bitmap tăng, PostgreSQL có thể chuyển một số phần từ exact sang lossy để giảm footprint.

### 11.1. Bitmap exact

Mô hình:

```text
block 105:
  matching offset 2
  matching offset 8
  matching offset 11

Các offset khác không thuộc bitmap.
```

`Bitmap Heap Scan` chủ yếu xét những TID được chỉ ra, cùng kiểm tra MVCC và các điều kiện còn lại.

### 11.2. Bitmap lossy

Mô hình:

```text
block 105:
  "Có thể có hàng phù hợp trong block này"

Không còn giữ chính xác danh sách offset match.
```

Khi đọc block đó, PostgreSQL phải xét thêm tuple và **recheck index qual** để loại những hàng không thực sự match.

### 11.3. Đọc `Heap Blocks`

Trong `EXPLAIN (ANALYZE, BUFFERS)` có thể thấy:

```text
Bitmap Heap Scan on events
  Recheck Cond: (...)
  Rows Removed by Index Recheck: ...
  Heap Blocks: exact=... lossy=...
```

| Dòng | Ý nghĩa |
| --- | --- |
| `Heap Blocks: exact=N` | Số heap blocks bitmap xử lý ở mức chính xác |
| `Heap Blocks: lossy=M` | Số blocks phải xử lý theo bitmap mất chi tiết |
| `Recheck Cond` | Predicate dùng để xác nhận hàng từ bitmap khi cần |
| `Rows Removed by Index Recheck` | Số tuple bị loại vì không thỏa predicate sau recheck |

### 11.4. Có `Recheck Cond` không có nghĩa bitmap đã lossy

Một plan có:

```text
Recheck Cond: (category = 'premium')
Heap Blocks: exact=...
```

**không đủ để kết luận bitmap đã lossy**. EXPLAIN có thể in `Recheck Cond` như điều kiện cần được áp dụng khi recheck; với bitmap exact, nhiều điều kiện có thể không cần kiểm tra lại theo cách gây loại hàng.

Muốn biết có lossiness hay không, xem `Heap Blocks: lossy` và `Rows Removed by Index Recheck` khi những thống kê này có mặt.

### 11.5. Chỉ số “Rows Removed by Index Recheck” không phải Filter

- `Rows Removed by Index Recheck`: hàng bị loại khi xác nhận lại predicate đã dùng cho bitmap.
- `Rows Removed by Filter`: hàng bị loại do predicate lọc ở node, không nhất thiết thuộc index recheck.

Ví dụ query:

```sql
SELECT *
FROM scan_lab.events
WHERE category = 'premium'
  AND amount > 50.00;
```

Nếu bitmap được xây theo `category` mà `amount` không thuộc index predicate của bitmap, `amount > 50` có thể xuất hiện như một `Filter` riêng.

### 11.6. Không phải lossy luôn có nghĩa “index lỗi”

Lossy bitmap là cơ chế tiết kiệm bộ nhớ hợp lệ của PostgreSQL, không phải dấu hiệu index bị hỏng.

Nó có thể tăng CPU do phải recheck nhiều tuple, nhưng đôi khi vẫn là kế hoạch tốt nhất so với đọc heap rời rạc hoặc quét toàn bộ.

## 12. `work_mem` ảnh hưởng bitmap ra sao?

`work_mem` là một giới hạn/budget bộ nhớ cho một số thao tác query, trong đó có bitmap và sort/hash, với các chi tiết phụ thuộc loại node và phiên bản.

Khi bitmap dùng nhiều bộ nhớ, nó có thể chuyển sang lossy representation.

### 12.1. Thử giới hạn thấp trên database lab

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';

ROLLBACK;
```

Có thể quan sát sự thay đổi số exact/lossy heap blocks, **nếu** planner chọn bitmap path và bitmap đủ lớn để bị áp lực bộ nhớ.

Không có bảo đảm query này sẽ tạo lossy bitmap trên mọi máy.

### 12.2. Thử giá trị cao hơn

```sql
BEGIN;

SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';

ROLLBACK;
```

So sánh:

- Có còn Bitmap Heap Scan không?
- Số exact/lossy blocks khác gì?
- `Rows Removed by Index Recheck` có thay đổi không?
- Buffers và actual time khác ra sao?

### 12.3. Đừng tăng `work_mem` toàn hệ thống chỉ vì một plan

`work_mem` không phải giới hạn RAM duy nhất cho cả PostgreSQL. Nhiều query đang chạy đồng thời, mỗi query có nhiều sort/hash/bitmap nodes, có thể dùng nhiều bộ nhớ tổng cộng.

Việc tăng giá trị toàn cục quá cao có thể làm tăng áp lực RAM. Thường nên đo và điều chỉnh ở scope hợp lý, xét workload tổng thể và concurrency.

### 12.4. Lossy bitmap cũng có thể do index access method

Một số loại index, đặc biệt những index trả kết quả ở cấp block/độ chính xác thấp, có thể yêu cầu recheck đáng kể. Ví dụ **BRIN** tóm tắt các range of pages và có thể tạo bitmap heap scan với lọc lại.

Vì vậy, lossiness/recheck không chỉ đến từ `work_mem`; nó còn phụ thuộc loại index và predicate.

## 13. BitmapAnd và BitmapOr: kết hợp nhiều chỉ mục

Bitmap scans có một ưu điểm lớn: PostgreSQL có thể kết hợp tập vị trí đến từ **nhiều index**.

### 13.1. Tạo index thứ hai trên status

```sql
CREATE INDEX events_status_idx
ON scan_lab.events (status);

ANALYZE scan_lab.events;
```

### 13.2. Điều kiện AND

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

Một dạng plan **có thể** là:

```text
Bitmap Heap Scan on events
  Recheck Cond: (
      (category = 'premium'::text)
      AND (status = 'FAILED'::text)
  )
  -> BitmapAnd
       -> Bitmap Index Scan on events_category_idx
            Index Cond: (category = 'premium'::text)
       -> Bitmap Index Scan on events_status_idx
            Index Cond: (status = 'FAILED'::text)
```

`BitmapAnd` lấy giao của hai tập TID/block positions.

Tuy nhiên, planner cũng có thể chỉ dùng **một** index rồi Filter điều kiện còn lại nếu phương án đó rẻ hơn. Không phải mọi `AND` đều dẫn tới BitmapAnd.

### 13.3. Điều kiện OR

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
   OR status = 'FAILED';
```

Một dạng plan có thể là:

```text
Bitmap Heap Scan on events
  Recheck Cond: (
      (category = 'premium'::text)
      OR (status = 'FAILED'::text)
  )
  -> BitmapOr
       -> Bitmap Index Scan on events_category_idx
            Index Cond: (category = 'premium'::text)
       -> Bitmap Index Scan on events_status_idx
            Index Cond: (status = 'FAILED'::text)
```

`BitmapOr` hợp nhất những vị trí từ hai bitmap. Nếu một hàng match cả hai điều kiện, nó vẫn được trả về theo semantics của query (không tạo bản sao chỉ vì TID xuất hiện ở cả hai bitmap).

### 13.4. Vì sao AND/OR bitmap có ích?

Có thể không cần tạo một index tổ hợp cho mọi cặp predicate nếu planner có thể kết hợp hai indexes sẵn có đủ hiệu quả.

Nhưng BitmapAnd/BitmapOr có chi phí xây bitmap; một **composite index** đúng thứ tự cột đôi khi nhanh hơn, đặc biệt với truy vấn rất phổ biến hoặc `ORDER BY LIMIT`.

Không nên suy luận rằng “tạo hai index đơn luôn tốt hơn một index nhiều cột”. Cần đo theo workload.

## 14. Index Only Scan: khi index đủ dữ liệu để trả query

`Index Only Scan` là access path liên quan nhưng **khác** `Index Scan` thông thường.

Để chỉ đọc index một cách hiệu quả, cần:

1. Access method hỗ trợ index-only scans theo thuộc tính truy vấn.
2. Những cột cần trả/kiểm tra đều có trong index (index keys hoặc INCLUDE columns phù hợp).
3. PostgreSQL biết heap pages liên quan đã đạt trạng thái visibility cần thiết, thông qua **visibility map**.

### 14.1. Tạo covering index phù hợp

```sql
CREATE INDEX events_account_time_cover_idx
ON scan_lab.events (account_id, occurred_at DESC)
INCLUDE (status, amount);
```

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id, occurred_at, status, amount
FROM scan_lab.events
WHERE account_id = 4321
ORDER BY occurred_at DESC
LIMIT 5;
```

B-tree index chứa:

- `account_id`: điều kiện lọc.
- `occurred_at DESC`: thứ tự.
- `status` và `amount`: payload của index để trả kết quả, nhờ `INCLUDE`.

Planner có thể chọn `Index Only Scan`, nhưng không bắt buộc.

### 14.2. Visibility map và `Heap Fetches`

PostgreSQL cần bảo đảm một tuple có thể nhìn thấy theo snapshot MVCC. Dữ liệu index **không tự mang đầy đủ thông tin visibility tương đương heap**.

Visibility map cho biết những heap pages có trạng thái **all-visible** phù hợp, giúp tránh phải đọc heap cho các tuple nằm trên những pages đó.

Kế hoạch có thể hiện:

```text
Index Only Scan using events_account_time_cover_idx
  Index Cond: (account_id = 4321)
  Heap Fetches: 0
```

Nhưng nếu một số pages chưa all-visible:

```text
Index Only Scan using events_account_time_cover_idx
  Heap Fetches: 5
```

Vẫn gọi là `Index Only Scan`, dù nó phải đọc heap **một số lần** để kiểm tra visibility.

### 14.3. VACUUM giúp khi điều kiện phù hợp

Trong database lab, sau khi dữ liệu đã được commit:

```sql
VACUUM (ANALYZE) scan_lab.events;
```

Lệnh này có thể cập nhật visibility map cho những pages đủ điều kiện, qua đó làm index-only scans hữu ích hơn. `VACUUM` phải chạy trong phạm vi được hỗ trợ, **không đặt lệnh VACUUM thường này trong transaction block tường minh**.

Không có bảo đảm mọi query sau VACUUM đều chọn `Index Only Scan`: còn phụ thuộc cột, thống kê, index và chi phí.

### 14.4. Vì sao INSERT/UPDATE liên tục làm index-only kém hiệu quả?

Những trang heap mới được ghi hoặc vừa có thay đổi có thể chưa có bit all-visible phù hợp. Index Only Scan có thể phải quay về heap để kiểm tra visibility nhiều lần.

Vì vậy, một covering index rất hiệu quả trên bảng ít thay đổi nhưng kém hấp dẫn hơn trên bảng cập nhật liên tục, dù SQL không đổi.

### 14.5. INCLUDE không miễn phí

`INCLUDE` làm index chứa thêm dữ liệu, có thể:

- Tăng dung lượng index.
- Tăng I/O và chi phí bảo trì index khi ghi.
- Giảm mật độ entries trên một trang.
- Ảnh hưởng các đặc tính lưu trữ/deduplication của B-tree.
- Không giúp điều kiện lọc theo một included column như một index key thông thường.

Chọn INCLUDE theo **các query quan trọng** thay vì thêm mọi cột để “cover” toàn bảng.

## 15. ORDER BY và LIMIT có thể làm Index Scan thắng Bitmap Scan

Một B-tree index có thứ tự theo các key. Vì vậy, nếu query cần đúng thứ tự đó, Index Scan hoặc Index Only Scan có thể trả hàng **đã sắp xếp** mà không cần một Sort riêng.

### 15.1. Lấy 5 sự kiện mới nhất của một tài khoản

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id, occurred_at, status, amount
FROM scan_lab.events
WHERE account_id = 4321
ORDER BY occurred_at DESC
LIMIT 5;
```

Index:

```sql
CREATE INDEX events_account_time_idx
ON scan_lab.events (account_id, occurred_at DESC);
```

Nếu index đã tồn tại, planner có thể đi theo thứ tự `(account_id, occurred_at DESC)` để trả 5 hàng đầu nhanh, không quét hết mọi hàng cùng account.

Nếu đồng thời có covering index trong phần 14, planner có thể chọn một trong các index tương đương tùy chi phí; đó là bình thường trong lab.

### 15.2. Bitmap mất thứ tự index key

Khi đi qua bitmap, PostgreSQL tổ chức truy cập heap theo trang. Do đó, kết quả `Bitmap Heap Scan` **không giữ nguyên thứ tự khóa B-tree** chỉ vì bitmap được xây từ B-tree.

Nếu SQL cần:

```sql
ORDER BY occurred_at DESC
```

thì một bitmap plan có thể cần thêm:

```text
Sort
  -> Bitmap Heap Scan
       -> Bitmap Index Scan
```

Trong khi một index scan theo index tương ứng có thể tránh Sort.

### 15.3. LIMIT làm startup cost quan trọng

Với `LIMIT 5`, PostgreSQL có thể ưu tiên plan trả nhanh **năm hàng đầu**, ngay cả khi một phương án khác có tổng cost tốt hơn nếu phải trả toàn bộ kết quả.

Chẳng hạn:

```sql
EXPLAIN
SELECT event_id, occurred_at
FROM scan_lab.events
ORDER BY occurred_at DESC
LIMIT 5;
```

Nếu có B-tree index thích hợp trên `occurred_at`, planner có thể scan index ngược/thuận theo cấu trúc key để lấy vài hàng mà không cần Sort toàn bảng.

### 15.4. LIMIT không có ORDER BY

```sql
SELECT event_id
FROM scan_lab.events
LIMIT 5;
```

Câu này không yêu cầu năm hàng theo một thứ tự xác định. Planner có thể chọn Seq Scan để nhanh chóng phát ra vài hàng.

Đừng giải thích đó là “Seq Scan đọc hết 200.000 hàng” khi chỉ cần năm kết quả: executor có thể **dừng sớm** khi node `Limit` đã nhận đủ hàng, tùy cấu trúc kế hoạch.

### 15.5. OFFSET sâu thường tốn công

```sql
SELECT event_id, occurred_at
FROM scan_lab.events
ORDER BY occurred_at DESC
LIMIT 20 OFFSET 100000;
```

Dù có index, query có thể phải đi qua một lượng lớn entries trước khi trả trang yêu cầu. Với pagination dài, **keyset pagination** theo key ổn định có thể phù hợp hơn, nhưng cần thiết kế điều kiện và thứ tự đúng.

## 16. So sánh trực tiếp ba đường truy cập

| Đặc điểm | Seq Scan | Index Scan | Bitmap Heap Scan |
| --- | --- | --- | --- |
| Bắt đầu từ | Heap | Index | Một hoặc nhiều indexes tạo bitmap |
| Dùng index? | Không bắt buộc | Có | Có ở giai đoạn bitmap index |
| Đọc heap theo cách | Tuần tự theo trang | Theo tuple locations từ index | Gom theo heap blocks |
| Trả hàng rất sớm? | Có thể | Thường tốt khi selective | Cần xây bitmap trước |
| Tốt với ít hàng match? | Thường kém trên bảng lớn | **Thường tốt** | Có thể overhead không đáng |
| Tốt với số match trung bình? | Tùy table/cache | Có thể tốn random I/O | **Thường đáng cân nhắc** |
| Tốt với gần hết bảng? | **Thường tốt** | Thường kém khi phải fetch nhiều heap | Có thể không còn lợi |
| Giữ thứ tự B-tree key? | Không tự bảo đảm | Có thể | Không |
| Kết hợp nhiều indexes qua AND/OR? | Không theo cách này | Thường cần index phù hợp khác | Có qua BitmapAnd/BitmapOr |
| Có thể tạo lossy bitmap? | Không | Không | Có |
| Có `Index Cond`? | Không | Thường có | Ở Bitmap Index Scan |
| Có `Recheck Cond`? | Không theo bitmap | Không như bitmap heap | Thường có |
| Có thể chạy song song? | Có biến thể Parallel Seq Scan | Có trong điều kiện/AM hỗ trợ | Có biến thể Parallel Bitmap Heap Scan |

Bảng là gợi ý kiến trúc, **không phải quy tắc planner tuyệt đối**.

## 17. Tính chọn lọc (*selectivity*) quyết định nhiều điều

**Selectivity** của một predicate thể hiện tỷ lệ hàng ước lượng thỏa predicate đó.

Ví dụ:

```sql
WHERE account_id = 4321
```

có thể chỉ match khoảng 10/200.000 hàng, tức ~0,005%.

```sql
WHERE category = 'standard'
```

có thể match ~91%.

### 17.1. Vì sao tỉ lệ match cao không thích hợp Index Scan thông thường?

Index Scan có thể phải:

1. Đọc index pages.
2. Truy cập rất nhiều heap pages để lấy hàng.
3. Lặp lại hàng loạt heap accesses.

Nếu phần lớn heap pages đều được chạm, Seq Scan chỉ đọc heap tuần tự một lần có thể rẻ hơn.

### 17.2. Vì sao tỉ lệ match thấp có thể vẫn dùng Seq Scan?

Nếu bảng chỉ có vài trang, chi phí lập kế hoạch và đi qua index có thể cao hơn đọc bảng thẳng.

Hoặc nếu predicate không được index hỗ trợ theo biểu thức/collation/operator class thích hợp, planner không có index path khả dụng.

Hoặc index quá lớn, không ở cache, khiến chi phí thực tế không như kỳ vọng.

### 17.3. Selectivity được ước lượng, không phải planner luôn đếm thật trước

PostgreSQL thường dùng:

- Số hàng ước lượng của bảng.
- Statistics cho từng cột.
- Most common values (MCV).
- Histogram.
- Số lượng distinct values.
- Null fraction.
- Correlation.
- Extended statistics trong một số truy vấn nhiều cột.

Planner không chạy `COUNT(*)` chính xác cho mọi giá trị ngay trước khi chọn plan.

## 18. `ANALYZE` và thống kê của planner

Xem statistics:

```sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname = 'scan_lab'
  AND tablename = 'events'
  AND attname IN (
      'account_id', 'category', 'status', 'occurred_at'
  )
ORDER BY attname;
```

### 18.1. Most common values

Nếu `category = 'standard'` chiếm khoảng 91% và `premium` 9%, statistics thường giúp planner biết hai giá trị có tần suất khác nhau.

Không nên ước lượng rằng `category` có hai giá trị thì mỗi giá trị luôn 50%.

### 18.2. `n_distinct`

Cho biết ước lượng về số giá trị phân biệt. Với cột có nhiều ID tài khoản, điều này ảnh hưởng ước lượng số hàng cho phép so sánh `=`.

### 18.3. Correlation

`pg_stats.correlation` liên quan mức độ tương quan giữa thứ tự giá trị cột và vị trí vật lý trong bảng.

- Correlation gần `+1` hoặc `-1` có thể cho biết thứ tự dữ liệu phù hợp đáng kể với khóa.
- Gần `0` cho thấy thứ tự ít tương quan hơn.

Planner dùng thông tin này trong các mô hình chi phí index access. Nếu những heap tuples có key gần nhau cũng nằm gần nhau về vật lý, index scan có thể gặp ít random I/O hơn so với dữ liệu bị xáo trộn.

### 18.4. Cập nhật lại sau thay đổi lớn

```sql
ANALYZE scan_lab.events;
```

Sau import/bulk delete/update lớn, thống kê cũ có thể khiến `rows` ước lượng sai. Autovacuum/autoanalyze giúp tự bảo trì stats theo chính sách hệ thống, nhưng với dataset thay đổi đột biến, có thể cần ANALYZE chủ động.

**Không dùng ANALYZE như một “lệnh bắt PostgreSQL dùng index”.** Nó chỉ cung cấp thông tin tốt hơn cho lựa chọn chi phí.

## 19. Sai số ước lượng: dấu hiệu cần điều tra

Xem:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

So sánh:

- `rows=...` trong phần planner estimate.
- `actual rows=...` trong phần ANALYZE.

Nếu estimate 10 hàng nhưng thực tế 10.000 hàng, planner có thể đã chọn access path hoặc join strategy không phù hợp.

### 19.1. Ví dụ về số liệu minh họa

```text
Index Scan on events
  (cost=0.40..18.20 rows=10 width=180)
  (actual time=0.080..40.000 rows=10000 loops=1)
```

**Đây không phải output đo thật từ bộ dữ liệu**. Nó minh họa một trường hợp ước lượng hàng sai rất lớn.

### 19.2. Nguyên nhân có thể

- Statistics cũ.
- Độ phân bố lệch.
- Quan hệ phụ thuộc giữa nhiều cột không được thống kê đầy đủ.
- Điều kiện chứa hàm/biểu thức khó ước lượng.
- Prepared statements dùng generic plan không phản ánh selectivity giá trị tham số cụ thể.
- Thống kê mẫu không đủ chi tiết.
- Query join nhiều bảng nhân sai số ước lượng.

### 19.3. Extended statistics khi các cột liên quan

Ví dụ:

```sql
CREATE STATISTICS events_category_status_stats
    (dependencies, mcv)
ON category, status
FROM scan_lab.events;

ANALYZE scan_lab.events;
```

PostgreSQL có thể dùng những thống kê nhiều cột này để cải thiện selectivity estimates trong các dạng predicate phù hợp.

Không suy ra `CREATE STATISTICS` tự tạo index mới hoặc bắt planner sử dụng BitmapAnd: nó chỉ cung cấp dữ liệu ước lượng.

### 19.4. Không chỉ nhìn node bị chậm

Một access path có thể chọn đúng trong một plan nhưng bị gọi lại nhiều lần vì cách join ở node cha.

Với `EXPLAIN ANALYZE`, chú ý `loops`. Số `actual rows` ở node thường được hiển thị theo trung bình mỗi lần thực hiện; để hiểu tổng khối lượng cần xét cả `loops`.

## 20. Physical locality và correlation: cùng selectivity, chi phí khác nhau

Hai bảng đều có 5% hàng match một điều kiện, nhưng:

- Ở bảng A, các hàng match tập trung trên ít heap blocks.
- Ở bảng B, các hàng match nằm rải rác gần như toàn bảng.

Đường truy cập tối ưu có thể khác vì **số heap pages phải đọc** và độ ngẫu nhiên khác.

### 20.1. Mô hình trực quan

```text
Bảng A: dữ liệu match tập trung
[XXXX][XXXX][XXXX][....][....][....]
    ^ số trang cần đọc ít hơn

Bảng B: dữ liệu match phân tán
[X...][.X..][..X.][...X][X...][.X..]
    ^ nhiều trang bị chạm dù số hàng match tương tự
```

### 20.2. `CLUSTER` và sắp xếp vật lý

PostgreSQL có lệnh `CLUSTER` để sắp xếp lại heap theo index được chọn:

```sql
-- Chỉ minh họa trên database lab:
CLUSTER scan_lab.events USING events_account_idx;
ANALYZE scan_lab.events;
```

Thao tác này **viết lại và tổ chức lại bảng**, cần khóa và tài nguyên đáng kể, không phải mẹo chạy tùy tiện trên production.

`CLUSTER` cũng **không tự giữ thứ tự vật lý mãi mãi** khi các hàng tiếp tục được INSERT/UPDATE.

### 20.3. Khi nào không cần CLUSTER?

Nếu một query có `WHERE account_id = ...` chỉ trả vài hàng, index scan có thể đã nhanh đủ. Việc tổ chức lại toàn bảng chỉ để cải thiện một truy vấn nhỏ có thể không xứng với chi phí khóa và bảo trì.

Hãy ưu tiên đo `EXPLAIN ANALYZE BUFFERS` và workload thật trước khi cân nhắc thay đổi physical layout.

## 21. Index nhiều cột có thể thay thế bitmap kết hợp index đơn

Tạo index:

```sql
CREATE INDEX events_category_status_idx
ON scan_lab.events (category, status);

ANALYZE scan_lab.events;
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

Planner bây giờ có thêm lựa chọn:

1. Seq Scan.
2. Index Scan/Bitmap Index Scan trên `events_category_idx`, rồi lọc status.
3. Index Scan/Bitmap Index Scan trên `events_status_idx`, rồi lọc category.
4. BitmapAnd của hai index đơn.
5. Index Scan hoặc Bitmap Index Scan trên **composite index**.

### 21.1. Thứ tự cột trong B-tree quan trọng

Index:

```sql
(category, status)
```

thường đặc biệt hữu ích khi truy vấn có điều kiện trên **leading column `category`** và cột kế tiếp.

Một query chỉ có:

```sql
WHERE status = 'FAILED'
```

không tự được tối ưu giống query lọc theo cả hai cột. PostgreSQL có các chiến lược đặc biệt tùy phiên bản và dữ liệu, nhưng **không nên coi mọi thứ tự composite index là tương đương**.

### 21.2. Composite index không luôn thắng BitmapAnd

Nếu workload chủ yếu chạy:

- Query chỉ theo `category`.
- Query chỉ theo `status`.
- Query OR phức tạp.
- Nhiều tổ hợp điều kiện khác nhau.

thì index đơn có thể vẫn có giá trị. Composite index cũng tăng chi phí ghi và lưu trữ.

Chọn index theo **những query thực tế có tần suất/latency quan trọng**, không phải tạo tất cả tổ hợp.

### 21.3. Khi nào partial index có ích?

Giả sử cần truy vấn thường xuyên các sự kiện `FAILED`:

```sql
CREATE INDEX events_failed_time_idx
ON scan_lab.events (occurred_at DESC)
WHERE status = 'FAILED';
```

Query:

```sql
SELECT event_id, occurred_at, payload
FROM scan_lab.events
WHERE status = 'FAILED'
ORDER BY occurred_at DESC
LIMIT 20;
```

Index một phần chỉ lưu những hàng thỏa predicate khi được cập nhật. Nó có thể nhỏ và phù hợp với query này.

Nhưng planner chỉ dùng partial index khi nó có thể **chứng minh predicate của query suy ra predicate của index** theo khả năng lập kế hoạch. Một generic prepared plan với tham số `status = $1` có thể không suy ra `status = 'FAILED'` cho mọi giá trị.

**Partial index không phải lối tắt buộc PostgreSQL dùng index trong mọi câu SQL có vẻ giống nhau.**

## 22. Không phải mọi loại index đều có cùng đường scan

Ví dụ phổ biến:

| Index access method | Đặc điểm liên quan |
| --- | --- |
| B-tree | Phù hợp `=`, range, sorting; hỗ trợ nhiều hình thức index access |
| Hash | Hữu ích cho equality theo operator class phù hợp; không cung cấp B-tree ordering |
| GIN | Thường dùng cho tập khóa/phần tử, array, JSONB, full-text; bitmap access thường gặp |
| GiST | Nhiều loại tìm kiếm không gian/tương đồng; có thể cần recheck tùy operator class |
| SP-GiST | Phân vùng không gian tìm kiếm theo cấu trúc hỗ trợ |
| BRIN | Tóm tắt **range of heap pages**, nhỏ và hữu ích với dữ liệu tương quan vật lý; thường cần recheck |

### 22.1. BRIN minh họa bitmap ở cấp trang

Giả sử `occurred_at` tăng theo thứ tự chèn, như bộ dữ liệu lab. Có thể tạo:

```sql
CREATE INDEX events_time_brin_idx
ON scan_lab.events
USING brin (occurred_at);
```

Query theo khoảng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM scan_lab.events
WHERE occurred_at >= timestamptz '2025-04-01 00:00:00+00'
  AND occurred_at <  timestamptz '2025-04-02 00:00:00+00';
```

BRIN tóm tắt các page ranges, nên có thể dẫn tới:

```text
Bitmap Heap Scan
  Recheck Cond: ...
  Rows Removed by Index Recheck: ...
  Heap Blocks: lossy=...
  -> Bitmap Index Scan on events_time_brin_idx
```

Đây là **một dạng plan có thể xảy ra**, không chắc chắn. BRIN đặc biệt hữu ích khi dữ liệu có correlation mạnh với vị trí vật lý và bảng đủ lớn.

### 22.2. Vì sao BRIN có thể trả nhiều hàng không thỏa range?

Index BRIN nói “page range này có thể chứa giá trị trong khoảng”, chứ không lưu từng TID đủ chính xác giống B-tree. Khi đọc pages, PostgreSQL phải **recheck** để loại những tuple không thực sự thỏa predicate.

### 22.3. Đừng đánh đồng “Bitmap Scan” với B-tree

Một `Bitmap Index Scan` có thể xuất phát từ các index methods khác B-tree. Quan trọng là **đường truy cập tạo bitmap + heap scan**, còn loại index quyết định khả năng hỗ trợ predicate, độ chính xác và chi phí.

## 23. Parallel Seq Scan và Parallel Bitmap Heap Scan

Khi bảng lớn và cấu hình cho phép, planner có thể chọn **parallel plan**.

### 23.1. Parallel Seq Scan

```text
Gather
  Workers Planned: ...
  -> Parallel Seq Scan on events
       Filter: ...
```

Các worker có thể phân chia công việc đọc heap và lọc dữ liệu.

Những phần liên quan:

- `Gather` thu kết quả từ workers.
- `Workers Planned` là số worker planner dự định.
- `Workers Launched` trong ANALYZE là số thực tế khởi chạy.
- Query/plan phải đáp ứng điều kiện parallel-safe tương ứng.

### 23.2. Parallel Bitmap Heap Scan

Một số kế hoạch có dạng:

```text
Gather
  -> Parallel Bitmap Heap Scan on events
       Recheck Cond: ...
       -> Bitmap Index Scan on ...
```

Cách tạo bitmap và chia công việc đọc heap có chi tiết implementation riêng, nhưng về logic vẫn gồm **xác định trang/hàng phù hợp rồi truy cập heap**.

### 23.3. Tại sao parallel chưa chắc nhanh hơn?

Parallelism cần chi phí:

- Khởi động và quản lý workers.
- Chia sẻ/phối hợp công việc.
- Thu kết quả qua Gather.
- Truy cập memory/I/O chung.

Một query nhỏ, trả rất ít hàng, có thể chạy nhanh hơn trên một backend. Số worker được cấp còn phụ thuộc tải hệ thống.

### 23.4. Có thể dùng parallel index scan không?

PostgreSQL hỗ trợ một số parallel index/index-only paths với index access methods phù hợp (ví dụ B-tree). Không suy rằng mọi index type và mọi predicate đều hỗ trợ dạng parallel tương đương.

Vì thế khi đọc `EXPLAIN`, hãy xem **tên node thực tế** chứ không chia đơn giản “mọi index scan đều tuần tự”.

## 24. Đọc `EXPLAIN (ANALYZE, BUFFERS)` đúng cách

Một ví dụ query:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE account_id BETWEEN 1000 AND 1499;
```

Chú ý:

### 24.1. Estimated rows và actual rows

```text
(cost=... rows=5000 width=...)
(actual time=... rows=4980 loops=1)
```

Nếu ước lượng sát thực tế, statistics có thể đang phù hợp. Nếu lệch rất lớn, điều tra stats/predicate trước khi chỉ đổi index.

### 24.2. Startup và total time

```text
actual time=0.050..12.300
```

Giá trị thứ nhất là thời gian quan sát trước khi node phát ra hàng đầu theo báo cáo; giá trị thứ hai là thời gian đến kết thúc node (trong ngữ cảnh instrumented execution).

Các thời gian của node **không đơn giản cộng thẳng** vì một node cha thường chứa thời gian thực hiện các node con.

### 24.3. Loops

```text
actual rows=10 loops=100
```

có nghĩa node chạy 100 lượt; actual rows hiển thị thường là **trung bình mỗi lượt**, không phải tổng tất cả lượt. Với nested-loop join, điều này đặc biệt quan trọng.

### 24.4. Shared hit/read

```text
Buffers: shared hit=300 read=50
```

Ý nghĩa khái quát:

- `shared hit`: block được tìm thấy trong shared buffer cache.
- `shared read`: block cần được đọc vào shared buffers; không thể từ con số đó đơn giản suy ra mọi read đều phát sinh physical disk I/O vì còn OS filesystem cache.
- Một số kế hoạch còn có `dirtied`, `written`, local/temp buffers tùy thao tác.

Một query có rất nhiều hits có thể vẫn tốn CPU hoặc chịu contention. Đừng chỉ so `read` giữa hai lần chạy khi cache đã nóng lên.

### 24.5. Planning Time và Execution Time

`Planning Time` và `Execution Time` khác nhau:

- Planning Time: thời gian planner xây kế hoạch trong điều kiện đo.
- Execution Time: thời gian executor chạy query được instrumented.

Không nhất thiết bao gồm mọi network transfer, định dạng phía client hay thời gian ứng dụng xử lý kết quả theo cách đo end-to-end.

### 24.6. Tùy chọn TIMING OFF

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT event_id
FROM scan_lab.events
WHERE account_id = 4321;
```

`TIMING OFF` có thể giảm overhead lấy thời gian cho từng plan node, nhưng vẫn thu được số hàng thực tế và thời gian thực thi tổng ở đầu ra tương ứng.

Điều này hữu ích khi đo query rất ngắn hoặc plan có nhiều loops.

### 24.7. I/O timings

Nếu `track_io_timing` được bật theo cấu hình, EXPLAIN BUFFERS có thể bao gồm số liệu thời gian I/O phù hợp. Việc bật tracing I/O có overhead tùy hệ thống.

Không tự suy luận “shared read=100” nghĩa đúng 100 lần đọc vật lý chậm như nhau.

## 25. Cost model: vì sao index có vẻ nhanh nhưng planner chọn Seq Scan?

Một số tham số được dùng trong mô hình chi phí:

```sql
SHOW seq_page_cost;
SHOW random_page_cost;
SHOW cpu_tuple_cost;
SHOW cpu_index_tuple_cost;
SHOW cpu_operator_cost;
SHOW effective_cache_size;
SHOW effective_io_concurrency;
```

### 25.1. `seq_page_cost` và `random_page_cost`

`seq_page_cost` là đơn vị chi phí tham chiếu cho đọc tuần tự page. `random_page_cost` thể hiện chi phí ước lượng đọc random page tương đối.

Index Scan truyền thống có thể phát sinh nhiều random heap accesses. Vì thế chênh lệch hai tham số ảnh hưởng đánh giá Seq Scan so với Index Scan/Bitmap.

Trên SSD, sự khác biệt random/sequential I/O có thể ít hơn một số thiết bị lưu trữ cũ, nhưng cấu hình đúng vẫn phụ thuộc workload và cache.

### 25.2. `effective_cache_size` không phải RAM cấp phát

`effective_cache_size` là ước lượng về dung lượng bộ nhớ đệm hữu dụng (bao gồm shared buffers và OS cache theo mô hình planner), **không phải một lệnh cấp phát thêm RAM cho PostgreSQL**.

Giá trị này ảnh hưởng giả định rằng bao nhiêu trang sẽ có sẵn trong cache khi tính cost.

### 25.3. CPU costs

`cpu_tuple_cost`, `cpu_index_tuple_cost` và `cpu_operator_cost` đóng góp vào cost khi xử lý tuple, index entries và predicates.

Một query có nhiều giá trị match có thể tốn CPU lọc/giải mã tuple, dù dữ liệu đã trong cache.

### 25.4. Đừng sửa cost parameters trước khi xác minh số hàng ước lượng

Nếu planner ước lượng 1% nhưng thực tế 80%, vấn đề chính có thể nằm ở statistics chứ không phải random_page_cost.

Quy trình tốt:

1. Đọc plan và actual rows.
2. Kiểm tra statistics.
3. Xem indexes và predicates.
4. Xem I/O và wait events.
5. Chỉ cân nhắc tuning cost model có kiểm soát khi có bằng chứng.

Tối ưu hóa không phải cuộc thi “đặt random_page_cost thật thấp để plan dùng index nhiều nhất”.

## 26. Dùng `enable_seqscan` và `enable_bitmapscan` để học, không để chữa cháy

PostgreSQL có tham số planner method configuration:

```sql
SHOW enable_seqscan;
SHOW enable_indexscan;
SHOW enable_indexonlyscan;
SHOW enable_bitmapscan;
```

Trong một **transaction thử nghiệm**, bạn có thể thay đổi chúng tạm thời:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'standard';

ROLLBACK;
```

Planner sẽ cố tránh Seq Scan nếu có alternative phù hợp. Nhưng việc tắt không có nghĩa phương án thay thế sẽ **nhanh hơn**.

### 26.1. So sánh bitmap và index path

```sql
BEGIN;

SET LOCAL enable_bitmapscan = off;

EXPLAIN
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';

ROLLBACK;
```

Khi bitmap bị hạn chế, planner có thể chọn Seq Scan hoặc Index Scan tùy cost và các alternatives.

### 26.2. Vì sao `enable_seqscan = off` không tuyệt đối ngăn Seq Scan?

PostgreSQL không thể loại bỏ hoàn toàn sequential scan khỏi mọi query vì đôi khi không có alternative hợp lệ. Tham số này **khuyến khích tránh** Seq Scan, thường bằng việc làm path đó kém hấp dẫn hơn.

Không coi nó là cam kết “database tuyệt đối không quét bảng”.

### 26.3. Không ép scan method trong production như một “fix” lâu dài

Việc ép planner dùng index có thể:

- Làm hại những query trả nhiều hàng.
- Gây hàng triệu random heap fetches.
- Tăng I/O/latency.
- Tạo plan không phù hợp cho giá trị tham số khác.
- Giấu nguyên nhân sai statistics hoặc thiếu index phù hợp.

Dùng `SET LOCAL` trên lab để hiểu alternatives, rồi trả lại config bình thường.

## 27. Vì sao planner chọn khác giữa prepared statements?

Ứng dụng JDBC hoặc service backend thường dùng bind parameters:

```sql
SELECT event_id, payload
FROM scan_lab.events
WHERE category = $1;
```

Một tham số `$1 = 'standard'` có selectivity ~91%, còn `$1 = 'premium'` ~9%.

### 27.1. Custom plan

Một custom plan có thể tính đến giá trị tham số cụ thể. Vì thế PostgreSQL có cơ hội chọn Seq Scan cho một giá trị phổ biến và bitmap/index path cho giá trị ít phổ biến.

### 27.2. Generic plan

Một generic plan được tái dùng giữa nhiều giá trị tham số; nó không thể giả định mọi lần `$1` là `premium`. Vì vậy access path của generic plan có thể là sự đánh đổi.

### 27.3. Thí nghiệm bằng PREPARE

```sql
PREPARE event_by_category(text) AS
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = $1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE event_by_category('standard');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE event_by_category('premium');

DEALLOCATE event_by_category;
```

Kết quả có thể thay đổi do cơ chế chọn generic/custom plan và số lần thực thi.

### 27.4. Kiểm tra bằng plan_cache_mode trong lab

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

PREPARE event_by_category_demo(text) AS
SELECT event_id, payload
FROM scan_lab.events
WHERE category = $1;

EXPLAIN EXECUTE event_by_category_demo('standard');
EXPLAIN EXECUTE event_by_category_demo('premium');

DEALLOCATE event_by_category_demo;

ROLLBACK;
```

Trên phiên bản PostgreSQL hỗ trợ `plan_cache_mode`, đây là cách minh họa đường lập kế hoạch khi biết tham số.

Tương tự có thể thử `force_generic_plan` trong lab. Không nên tùy tiện đổi cấu hình cho tất cả application connections chỉ vì một query có plan chưa như mong muốn.

## 28. Index scan trong JOIN: phải xem số lần lặp

Không phải mọi plan có Index Scan đều là một query đơn bảng.

Ví dụ tạo bảng khách hàng:

```sql
CREATE TABLE scan_lab.accounts (
    account_id integer PRIMARY KEY,
    account_name text NOT NULL
);

INSERT INTO scan_lab.accounts (account_id, account_name)
SELECT g, 'account-' || g::text
FROM generate_series(1, 20000) AS s(g);

ANALYZE scan_lab.accounts;
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    a.account_name,
    e.event_id,
    e.occurred_at
FROM scan_lab.accounts AS a
JOIN scan_lab.events AS e
  ON e.account_id = a.account_id
WHERE a.account_id BETWEEN 4000 AND 4010;
```

Planner có thể dùng một dạng:

```text
Nested Loop
  -> Index Scan on accounts
  -> Index Scan on events
       Index Cond: (account_id = a.account_id)
```

Ở đây index scan của `events` có thể chạy **nhiều lần**, một lần cho mỗi account bên ngoài.

### 28.1. Loops có thể nhân chi phí

Giả sử inner index scan mất một khoảng thời gian nhỏ nhưng bị gọi 10.000 lần. Tổng chi phí có thể lớn.

Không nhìn riêng một lần `actual time` rồi kết luận inner scan vô hại. Cần kết hợp `loops` và số buffer accesses.

### 28.2. Khi join nhiều hàng, Seq Scan có thể lại đúng

Nếu join gần như **tất cả sự kiện** với bảng accounts, PostgreSQL có thể chọn:

```text
Hash Join
  -> Seq Scan on events
  -> Hash
       -> Seq Scan on accounts
```

Đây không nhất thiết là kế hoạch kém chỉ vì có hai Seq Scan. Đọc mỗi bảng lớn một lần rồi hash join có thể tốt hơn 200.000 index lookups rải rác.

### 28.3. Chỉ tối ưu scan node khi hiểu cả join tree

Một index có thể giúp một điều kiện nhưng làm planner chọn nested loop kém hơn hash join do ước lượng sai. Hãy đánh giá cả **plan tree**, không chỉ số lượng Index Scan.

## 29. Khi nào thêm index thực sự giúp?

Một index thường có ích khi nhiều yếu tố cùng phù hợp:

- Predicate sargable và index hỗ trợ operator.
- Selectivity đủ cao để loại nhiều hàng.
- Bảng đủ lớn để tránh quét toàn bộ.
- Độ rộng hàng/cột trả về và số heap fetches hợp lý.
- Query có `ORDER BY` hoặc `LIMIT` tương thích index.
- Index có thể cover query với visibility map thuận lợi.
- Workload chạy đủ thường xuyên để xứng đáng với chi phí bảo trì.

### 29.1. Không tạo index chỉ vì thấy Filter

```sql
EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'standard';
```

Nếu 91% match, index có thể không cải thiện; thậm chí tăng chi phí ghi. Cần biết query trả bao nhiêu hàng và kiểu truy cập nào rẻ hơn.

### 29.2. Index trên cột rất ít giá trị vẫn có trường hợp hữu ích

`category` chỉ có hai giá trị, nhưng `premium` tương đối hiếm. Index có thể giúp truy vấn premium trong những điều kiện phù hợp.

Tần suất giá trị **quan trọng hơn** việc đơn giản nói “cột có hai giá trị thì tuyệt đối không index”.

### 29.3. Index trên account_id khi query chọn vài hàng

```sql
SELECT event_id, account_id, occurred_at
FROM scan_lab.events
WHERE account_id = 4321;
```

Index `account_id` rất phù hợp với lookup ít hàng trên bảng lớn. Đây là một tình huống điển hình để planner cân nhắc Index Scan.

### 29.4. Lợi ích đọc phải cân với chi phí ghi

Mỗi index bổ sung có thể làm:

- `INSERT` phải cập nhật thêm index.
- `UPDATE` đổi cột được index cần bảo trì index.
- Tăng dung lượng lưu trữ.
- Tăng WAL.
- Tăng thời gian REINDEX/backup/maintenance.
- Thay đổi khả năng HOT update và chi phí VACUUM trong các tình huống liên quan.

Đừng tạo index cho mọi cột mà không xét workload ghi.

## 30. Tìm query cần tối ưu trước khi nhìn plan

Trong hệ thống thực tế, vấn đề thường không phải “Seq Scan có xuất hiện không?” mà là “query nào đang gây tổng chi phí lớn nhất hoặc vi phạm SLA?”.

Các dấu hiệu để ưu tiên:

1. Tổng thời gian SQL của query cao.
2. Tần suất gọi lớn.
3. Latency P95/P99 tăng.
4. Số buffer reads lớn.
5. Tỉ lệ đọc hàng rồi lọc bỏ cao.
6. Lỗi estimate nhiều bậc độ lớn.
7. Kế hoạch thay đổi đột ngột sau dữ liệu tăng.
8. Join loops tăng rất lớn.
9. Truy vấn phải sort/aggregate dữ liệu không cần thiết.
10. Dùng một query quét toàn bảng cho mỗi request trong khi dữ liệu có thể được truy xuất hẹp hơn.

### 30.1. Một Seq Scan nhỏ không đáng ưu tiên bằng một Index Scan lặp hàng triệu lần

Nếu một bảng tra cứu 3 hàng dùng Seq Scan mất microseconds, tối ưu nó thường vô nghĩa.

Ngược lại, một Index Scan nhìn qua có vẻ tốt nhưng được nested loop gọi 1.000.000 lần có thể là bottleneck chính.

### 30.2. Quan sát thống kê query

Nếu môi trường có extension `pg_stat_statements` được cài/enable, có thể dùng nó để chọn những query tiêu thụ nhiều thời gian/buffers. Extension này **không tự có sẵn mọi nơi** và có yêu cầu cấu hình/quyền.

Ở mức bài học, điều quan trọng là đo **workload thực** rồi mới tối ưu access path.

### 30.3. Bật logging/monitoring có kiểm soát

Có thể dùng slow query logging theo chính sách, EXPLAIN cho query đại diện và số liệu từ monitoring hiện có.

Không bật mọi tùy chọn logging/ANALYZE cho mọi query production một cách tùy tiện; overhead và rủi ro lộ dữ liệu SQL có thể đáng kể.

## 31. Quy trình so sánh kế hoạch thực tế

Một quy trình thực hành đáng tin cậy:

### Bước 1. Mô tả query và dữ liệu

Ghi rõ:

- SQL và parameters.
- Schema, loại index hiện có.
- Dung lượng bảng và số hàng.
- Phân bố key.
- Số hàng dự kiến trả.
- SLA và tần suất.

### Bước 2. Cập nhật statistics khi phù hợp

```sql
ANALYZE scan_lab.events;
```

Không làm `ANALYZE` trên production đang quá tải nếu chưa đánh giá thời điểm/tài nguyên, nhưng với lab thì đây là bước bình thường.

### Bước 3. Đọc plan ước lượng

```sql
EXPLAIN
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

Ghi lại Seq / Index / Bitmap nodes, cost, rows, width.

### Bước 4. Đo thực thi trên SELECT đại diện

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

So estimate/actual và buffers.

### Bước 5. Chọn một thay đổi có lý do

Ví dụ tạo index còn thiếu:

```sql
CREATE INDEX IF NOT EXISTS events_account_lookup_idx
ON scan_lab.events (account_id);
```

Với lab đã tạo `events_account_idx`, index này sẽ là **một index trùng công năng đáng kể**, nên trong thực hành thật **không cần tạo thêm**. Ví dụ chỉ minh họa cú pháp khi **thực tế index chưa tồn tại**.

Một thay đổi có lý do hơn có thể là index composite cho query order/limit hoặc cập nhật statistics cũ.

### Bước 6. Đo lại cùng query

Cần so sánh:

- Actual Execution Time qua nhiều lượt chạy.
- Buffer hits/reads.
- Rows estimated/actual.
- Plan path.
- Tần suất query.
- Chi phí INSERT/UPDATE.
- Mức cạnh tranh khi workload đồng thời.

### Bước 7. Xem cache và phương pháp đo

Lượt chạy đầu có thể phải đọc nhiều data pages; lượt sau có cache nóng. Đo một lượt duy nhất có thể sai lệch.

Không cố làm lạnh cache production bằng các lệnh nguy hiểm chỉ để có số liệu benchmark “công bằng”. Dùng môi trường thử nghiệm với phương pháp lặp được ghi rõ.

## 32. Những ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| Có index thì PostgreSQL phải dùng | Planner chọn phương án ước lượng rẻ hơn |
| Seq Scan luôn chậm | Có thể tối ưu cho bảng nhỏ hoặc phần lớn hàng |
| Index Scan luôn nhanh hơn Seq Scan | Random heap accesses có thể tốn hơn quét tuần tự |
| Bitmap Scan là quét bảng không dùng index | Nó thường gồm Bitmap Index Scan + Bitmap Heap Scan |
| Bitmap Scan luôn nhanh hơn Index Scan | Có overhead tạo bitmap và không giữ index order |
| Bitmap dùng 100% TID chính xác | Có thể exact hoặc lossy |
| Có Recheck Cond nghĩa là bitmap bị lossy | Không nhất thiết; xem Heap Blocks lossy và recheck removal |
| Recheck Cond và Filter là cùng một thứ | Recheck predicate bitmap; Filter kiểm tra điều kiện lọc khác |
| Nhiều index đơn không thể kết hợp | BitmapAnd/BitmapOr có thể kết hợp |
| AND luôn tạo BitmapAnd | Planner có thể chỉ dùng một index hoặc Seq Scan |
| Bitmap giữ ORDER BY của B-tree | Nó đọc heap theo blocks; có thể cần Sort |
| SELECT LIMIT 5 luôn đọc đúng 5 hàng | Có thể cần scan/sort nhiều hơn, tùy plan |
| Seq Scan + LIMIT luôn quét hết bảng | Executor có thể dừng sớm khi đủ hàng |
| Index Only Scan tuyệt đối không đọc heap | Có thể có Heap Fetches do visibility |
| INCLUDE biến mọi điều kiện thành Index Cond | Included columns không phải search keys |
| Tạo composite index theo thứ tự cột nào cũng được | Leading keys và ORDER BY rất quan trọng |
| Index trên cột ít distinct values luôn vô ích | Giá trị hiếm có thể đủ selective |
| Index trên mọi cột sẽ tối ưu toàn database | Tăng write cost, WAL, storage và maintenance |
| EXPLAIN cost là milliseconds | Cost là đơn vị ước lượng của planner |
| EXPLAIN ANALYZE không thực thi câu SQL | Nó thực thi; với DML có thể sửa dữ liệu |
| Buffers shared read bằng physical disk reads tuyệt đối | OS cache còn ảnh hưởng |
| actual rows luôn là tổng node output | Với loops, thường hiển thị bình quân mỗi lượt |
| Hai lần EXPLAIN khác thời gian là plan sai | Cache/tải/measurement có thể đổi |
| ANALYZE sẽ bắt dùng index | ANALYZE cập nhật thống kê, không ép plan |
| correlation không ảnh hưởng path | Physical locality ảnh hưởng random heap I/O |
| random_page_cost thấp nhất luôn tốt | Cần mô hình storage/cache thực tế |
| effective_cache_size cấp RAM cho server | Chỉ là ước lượng cache cho planner |
| work_mem tăng là mọi bitmap sẽ nhanh | Có overhead và nguy cơ RAM theo concurrency |
| enable_seqscan=off là fix production | Chỉ là công cụ khám phá alternatives |
| Prepared statement luôn có plan tối ưu cho từng giá trị | Generic/custom plans có thể khác nhau |
| BRIN hoạt động như B-tree từng TID chính xác | BRIN tóm tắt range pages và thường recheck |
| Parallel luôn giảm latency | Worker/Gather overhead có thể vượt lợi ích |
| Một Seq Scan trong Hash Join là lỗi | Có thể là cách nhanh nhất khi join phần lớn bảng |

## 33. Bài tập thực hành có hướng dẫn

Các bài thực hành dựa trên `scan_lab.events`. Hãy ghi **plan thực tế trên máy** thay vì cố ép kết quả giống ví dụ; việc PostgreSQL chọn path khác cũng là dữ liệu để giải thích.

### Bài 1. Không có index cho cột amount, dự đoán scan

```sql
EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE amount >= 95.00;
```

**Gợi ý đáp án:** nếu chưa có index phù hợp với `amount` và bảng đủ lớn, Seq Scan thường là lựa chọn tự nhiên. Không phải lúc nào một predicate selective cũng có index path.

### Bài 2. Tìm một hàng theo khóa chính

```sql
EXPLAIN
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE event_id = 12345;
```

**Gợi ý:** có B-tree PRIMARY KEY index; Index Scan thường phù hợp với lookup một hàng và cột `payload` phải lấy từ heap.

### Bài 3. Truy vấn account_id hẹp

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

**Gợi ý:** khi có `events_account_idx`, lookup khoảng 10 hàng thường phù hợp Index Scan. Quan sát actual rows.

### Bài 4. Cùng cột category, hai giá trị có độ phổ biến khác nhau

```sql
EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'standard';

EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

**Gợi ý:** giá trị standard ~91%, premium ~9%. Hai query có thể được chọn access paths khác nhau dù cùng index.

### Bài 5. Đọc `Index Cond` và `Filter`

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, status, payload
FROM scan_lab.events
WHERE account_id = 4321
  AND status = 'DONE';
```

**Gợi ý:** nếu dùng index chỉ trên account_id, `Index Cond` có thể là account_id còn status xuất hiện ở Filter. Với những indexes bổ sung, plan có thể khác.

### Bài 6. Bitmap Index Scan có đọc payload không?

**Đáp án:** không phải cách hoạt động chính của node này. Nó xác định tập vị trí từ index để tạo bitmap; `Bitmap Heap Scan` đọc các heap blocks phù hợp để lấy payload và áp dụng kiểm tra cần thiết.

### Bài 7. Vì sao bitmap có thể nhanh hơn index scan khi nhiều tuple match?

**Đáp án:** nó gom các heap locations theo trang, giảm số truy cập heap rời rạc so với index scan phải đi từng TID theo thứ tự index.

### Bài 8. Bitmap có trả dữ liệu đã sắp theo B-tree key không?

**Đáp án:** không được bảo đảm. Nó đi heap theo blocks; query cần ORDER BY có thể phải Sort.

### Bài 9. Recheck Cond xuất hiện có chắc chắn lossy không?

**Đáp án:** không. Kiểm tra `Heap Blocks: lossy` và `Rows Removed by Index Recheck` trong EXPLAIN ANALYZE.

### Bài 10. Bitmap exact khác bitmap lossy ở đâu?

**Đáp án:** exact biết những offsets/TIDs cần xét trong block; lossy giữ thông tin ở cấp block, cần recheck nhiều tuple hơn.

### Bài 11. `Rows Removed by Filter` khác `Rows Removed by Index Recheck`?

**Đáp án:** Filter loại bởi predicate lọc ở node; Index Recheck loại tuple sau khi xác minh lại predicate của bitmap/index access path.

### Bài 12. BitmapAnd có thể dùng điều kiện nào?

```sql
SELECT *
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

**Gợi ý:** có thể kết hợp bitmap của hai index đơn bằng BitmapAnd, nhưng planner có thể chọn path khác.

### Bài 13. BitmapOr có thể dùng điều kiện nào?

```sql
SELECT *
FROM scan_lab.events
WHERE category = 'premium'
   OR status = 'FAILED';
```

**Gợi ý:** có thể kết hợp hai bitmap bằng BitmapOr; không yêu cầu hai index entries bị trùng thành hai hàng output.

### Bài 14. Tại sao AND không chắc chắn dùng BitmapAnd?

**Đáp án:** planner so cost của một index + Filter, composite index, BitmapAnd và Seq Scan. BitmapAnd có overhead và không luôn thắng.

### Bài 15. `work_mem` thấp ảnh hưởng bitmap thế nào?

**Đáp án:** có thể làm bitmap mất độ chính xác ở một số pages, chuyển sang lossy và tăng recheck. Không đảm bảo mọi query có low work_mem sẽ tạo lossy.

### Bài 16. Tại sao không tăng work_mem toàn hệ thống ngay?

**Đáp án:** nhiều query đồng thời và nhiều memory-using nodes trong mỗi query có thể tiêu thụ RAM lớn. Cần đo workload và chọn phạm vi cài đặt.

### Bài 17. Index Only Scan có cần heap không?

**Đáp án:** có thể phải đọc heap để kiểm tra MVCC visibility nếu page chưa all-visible. Xem `Heap Fetches`.

### Bài 18. Visibility map dùng để làm gì trong Index Only Scan?

**Đáp án:** giúp xác định heap pages có trạng thái all-visible, cho phép tránh heap fetches khi index đã chứa đủ dữ liệu query cần.

### Bài 19. Vì sao VACUUM có thể cải thiện Index Only Scan?

**Đáp án:** nó có thể đặt/cập nhật all-visible bits cho pages đủ điều kiện. Nhưng quyết định plan còn phụ thuộc thống kê, chỉ mục, cột và chi phí.

### Bài 20. ORDER BY LIMIT thường hợp với index nào?

```sql
SELECT account_id, occurred_at
FROM scan_lab.events
WHERE account_id = 4321
ORDER BY occurred_at DESC
LIMIT 5;
```

**Gợi ý:** B-tree trên `(account_id, occurred_at DESC)` có thể trả đúng thứ tự và dừng sau một số ít entries.

### Bài 21. Tại sao Bitmap Heap Scan có thể cần Sort?

**Đáp án:** bitmap không bảo tồn thứ tự index key, nên ORDER BY có thể cần Sort node.

### Bài 22. Query không có ORDER BY với LIMIT 5 có phải quét hết bảng?

**Đáp án:** không nhất thiết. Executor có thể dừng một Seq Scan khi node Limit đã nhận đủ hàng, tùy plan.

### Bài 23. `cost=0.00..100.00` có phải 100 ms không?

**Đáp án:** không. Đây là đơn vị chi phí ước lượng cho planner.

### Bài 24. Ước lượng rows sai 100 lần cần xem gì trước?

**Đáp án:** thống kê ANALYZE, phân bố giá trị, điều kiện query, sự phụ thuộc giữa cột và generic/custom plans trước khi vội ép scan method.

### Bài 25. Xem thống kê category

```sql
SELECT
    most_common_vals,
    most_common_freqs,
    n_distinct
FROM pg_stats
WHERE schemaname = 'scan_lab'
  AND tablename = 'events'
  AND attname = 'category';
```

**Gợi ý:** tìm phân bố lệch standard/premium; planner có thể chọn path khác cho từng giá trị.

### Bài 26. `correlation` ảnh hưởng gì?

**Đáp án:** nó phản ánh phần nào quan hệ giữa thứ tự giá trị cột và vị trí vật lý; độ tập trung theo trang ảnh hưởng random heap access cost.

### Bài 27. Seq Scan trên bảng event_types 3 hàng có phải vấn đề?

**Đáp án:** thường không. Đọc toàn bảng nhỏ có thể rẻ hơn B-tree lookup, ngay cả khi có primary key index.

### Bài 28. Tại sao BRIN hay có recheck?

**Đáp án:** BRIN tóm tắt giá trị theo page ranges, nên chỉ xác định những vùng **có thể** chứa hàng match; Bitmap Heap Scan phải kiểm tra lại các tuple.

### Bài 29. `shared hit` có nghĩa mọi trang đến từ RAM mà không phát sinh I/O hệ thống ngoài?

**Đáp án:** chỉ cho biết block đã có trong shared buffers. `shared read` cho biết phải đọc vào shared buffers, nhưng lần đọc đó vẫn có thể được OS cache phục vụ thay vì đĩa vật lý.

### Bài 30. EXPLAIN ANALYZE UPDATE có sửa bảng không?

**Đáp án:** có. Nó thực thi DML. Trong lab, có thể dùng transaction rồi rollback để giữ dữ liệu transactional, nhưng vẫn có chi phí/side effects cần hiểu.

### Bài 31. Khi node Index Scan có loops=10000, cần xem gì?

**Đáp án:** tổng số lượt inner scan của nested loop, total buffers và actual rows per loop. Một lookup rẻ nhân 10.000 có thể vẫn đắt.

### Bài 32. Có nên tạo cả index trên từng cột dù workload ghi lớn?

**Đáp án:** không. Mỗi index tăng storage, WAL, write/maintenance cost. Chọn theo query tốn thời gian và giá trị thực tế.

### Bài 33. Hai query với `status = $1` có thể dùng plan khác nhau không?

**Đáp án:** có thể. Custom plan có cơ hội xét giá trị tham số; generic plan dùng chung cho nhiều giá trị và có thể khác nhau trong lựa chọn access path.

### Bài 34. `enable_seqscan=off` có phải sửa lỗi query chậm?

**Đáp án:** không phải fix production. Nó hữu ích để khám phá alternatives trong lab, nhưng có thể khiến nhiều query trả nhiều hàng chạy chậm hơn.

### Bài 35. Tổng hợp cách chọn theo truy vấn

Cho ba truy vấn trên bảng 200.000 hàng:

```sql
-- A: tìm một hàng.
SELECT event_id, payload
FROM scan_lab.events
WHERE event_id = 12345;

-- B: nhóm ~9%.
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';

-- C: nhóm ~91%.
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'standard';
```

**Gợi ý:** A thường thuận lợi cho Index Scan; B có thể thuận lợi cho Bitmap Heap Scan; C thường thuận lợi cho Seq Scan. Nhưng kết quả thực tế phải theo `EXPLAIN`, thống kê và chi phí của hệ thống.

### Bài 36. Vì sao ba query trên không có ngưỡng phân chia cố định?

**Đáp án:** table size, cache, cost parameters, locality, index design, LIMIT, row width, storage và thống kê cùng ảnh hưởng planner. Không có một tỷ lệ phần trăm duy nhất đúng cho mọi query.

### Bài 37. So sánh một query trước và sau tạo index

Thực hành trên bảng lab theo thứ tự:

```sql
-- 1. Khi index category chưa tồn tại:
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';

-- 2. Tạo index (chỉ một lần):
CREATE INDEX events_category_idx
ON scan_lab.events (category);

ANALYZE scan_lab.events;

-- 3. Đo lại cùng query:
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

**Gợi ý:** nếu bạn đã tạo `events_category_idx` ở phần 10, **không tạo lại lần thứ hai**; có thể bỏ bước CREATE INDEX hoặc làm trên một database lab mới. So sánh plan, rows, buffers và thời gian qua nhiều lần, tránh kết luận từ một lượt chạy/cache.

### Bài 38. Tại sao có composite index không nghĩa planner ngừng dùng BitmapAnd?

**Đáp án:** cost phụ thuộc predicates, thống kê và giá trị cụ thể. Planner vẫn có quyền chọn các index đơn kết hợp hoặc scan khác nếu rẻ hơn.

### Bài 39. Trong Join, vì sao Seq Scan cả bảng có thể tốt hơn nhiều Index Scan?

**Đáp án:** join phần lớn dữ liệu có thể hiệu quả hơn nếu đọc mỗi bảng tuần tự một lần rồi hash join, thay vì rất nhiều random index lookups.

### Bài 40. Viết báo cáo EXPLAIN có ý nghĩa

**Đáp án gợi ý:** báo cáo không chỉ viết “có Seq Scan”. Nên nêu query, tham số, schema/indexes, số hàng, estimate/actual rows, node structure, loops, buffers, thời gian qua các lượt, điều kiện cache và lý do thay đổi giúp toàn query nhanh hơn hay chậm hơn.

## 34. Bộ truy vấn tổng hợp để tự so sánh

Sau khi đã tạo các indexes trong bài, chạy từng truy vấn trên database lab và ghi plan thực tế.

### Trường hợp 1: giá trị hiếm theo khóa chính

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE event_id = 54321;
```

Dự đoán: Index Scan thường thuận lợi.

### Trường hợp 2: tra vài sự kiện theo account

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

Dự đoán: Index Scan có thể thuận lợi khi index trên account_id tồn tại.

### Trường hợp 3: lấy hàng ở mức trung bình

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

Dự đoán: Bitmap Heap Scan là một khả năng đáng xem xét khi có index.

### Trường hợp 4: lấy gần toàn bảng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'standard';
```

Dự đoán: Seq Scan thường hợp lý.

### Trường hợp 5: AND giữa hai index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

Dự đoán: có thể có BitmapAnd, composite index hoặc một index kết hợp Filter.

### Trường hợp 6: OR giữa hai index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
   OR status = 'FAILED';
```

Dự đoán: BitmapOr có thể cạnh tranh.

### Trường hợp 7: ORDER BY + LIMIT với covering index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id, occurred_at, status, amount
FROM scan_lab.events
WHERE account_id = 4321
ORDER BY occurred_at DESC
LIMIT 5;
```

Dự đoán: Index Scan hoặc Index Only Scan theo composite B-tree phù hợp, có thể tránh Sort.

### Trường hợp 8: COUNT gần toàn bảng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM scan_lab.events;
```

Dự đoán: có thể có Seq Scan/Parallel Seq Scan hoặc Index Only Scan trên một index nhỏ nếu planner đánh giá tốt, tùy visibility map và chi phí.

### Trường hợp 9: khoảng thời gian theo BRIN

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM scan_lab.events
WHERE occurred_at >= timestamptz '2025-04-01 00:00:00+00'
  AND occurred_at <  timestamptz '2025-04-02 00:00:00+00';
```

Dự đoán: có thể dùng Bitmap Index Scan trên BRIN kết hợp Bitmap Heap Scan có recheck; kết quả phụ thuộc kích thước bảng và các indexes khác.

### Trường hợp 10: bảng nhỏ

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM scan_lab.event_types
WHERE event_type_id = 2;
```

Dự đoán: Seq Scan hoàn toàn có thể là lựa chọn tốt.

## 35. Checklist đánh giá access path trong dự án thực tế

| Câu hỏi | Gợi ý hành động |
| --- | --- |
| Bảng nhỏ hay lớn? | Xem số hàng/trang, không tự ép index trên bảng nhỏ |
| Truy vấn trả bao nhiêu % hàng? | Kiểm tra selectivity, estimated/actual rows |
| Có index hỗ trợ đúng predicate? | Xem Index Cond và index definition |
| Có index nhưng Seq Scan? | So cost, rows, width, cache và ORDER BY |
| Có nhiều heap fetches ngẫu nhiên? | Xem khả năng bitmap/composite/covering |
| Bitmap có lossy? | Xem Heap Blocks exact/lossy và Recheck |
| Filter loại nhiều hàng sau index? | Xem composite/partial index phù hợp |
| Có ORDER BY LIMIT? | Dùng B-tree theo thứ tự key nếu hợp lý |
| Cần nhiều cột trả về? | Xem index-only/INCLUDE nhưng cân nhắc write cost |
| Index Only có nhiều Heap Fetches? | Xem visibility map, VACUUM và workload ghi |
| Có AND/OR nhiều predicate? | Xem BitmapAnd/BitmapOr và composite |
| Statistics có mới? | ANALYZE sau thay đổi lớn |
| Estimate chênh actual nhiều? | Kiểm tra MCV, histogram, extended stats |
| Correlation thấp? | Random heap access cost có thể cao |
| Table/index đang nóng trong cache? | Đánh giá buffers và lặp đo |
| Query chạy trên SSD/HDD? | Hiểu cost parameters theo workload |
| `work_mem` có gây lossy bitmap? | Đo ở scope phù hợp, tránh tăng global tùy tiện |
| Có parallel plan? | Xem workers planned/launched và overhead |
| Query trong nested loop? | Xem loops của inner access nodes |
| Prepared statement có params lệch phân bố? | So custom/generic plans |
| Có query thay đổi dữ liệu đang đo? | EXPLAIN ANALYZE thực thi DML |
| Có index trùng lặp? | Đánh giá trước khi thêm index mới |
| Có thể dùng partial index? | Predicate query phải suy ra predicate index |
| Có thể dùng BRIN? | Phù hợp dữ liệu tương quan vật lý theo range |
| Có ngăn planner bằng enable flags? | Chỉ dùng trong lab để khám phá alternatives |
| Đã đo toàn plan chưa? | Không chỉ nhìn một scan node |
| Đã đo qua nhiều lượt chưa? | Cân nhắc cache, concurrency, variance |
| Thay đổi có làm ghi chậm hơn? | Đo INSERT/UPDATE/WAL/storage |
| Tần suất và SLA của query? | Ưu tiên bottleneck có tác động thực |
| Có cần giữ plan ổn định qua phiên bản/data? | Theo dõi và đánh giá lại sau nâng cấp/thay đổi |
| Có hiểu vì sao planner chọn path đó? | Ghi rõ evidence từ cost, statistics, buffers |

## 36. Tổng kết: ba đường truy cập, ba đánh đổi

### Sequential Scan

`Seq Scan` đọc heap lần lượt, thích hợp khi:

- Bảng nhỏ.
- Truy vấn cần phần lớn hàng.
- Index không phù hợp.
- Đọc tuần tự rẻ hơn rất nhiều heap lookups rời rạc.

**Không xem Seq Scan là lỗi tự thân.**

### Index Scan

`Index Scan` dùng index để định vị những tuple cần đọc, thích hợp khi:

- Có ít hàng phù hợp.
- Predicate selective.
- Index hỗ trợ WHERE.
- ORDER BY/LIMIT có thể khai thác thứ tự B-tree.
- Số heap fetches không quá lớn.

**Không xem Index Scan luôn thắng khi truy vấn trả rất nhiều hàng.**

### Bitmap Scan

`Bitmap Index Scan` kết hợp `Bitmap Heap Scan` tạo bitmap các vị trí phù hợp và đọc heap theo trang, thích hợp khi:

- Số hàng match ở mức trung gian và phân bố trên nhiều heap pages.
- Cần giảm random heap I/O.
- Có thể kết hợp nhiều indexes bằng BitmapAnd/BitmapOr.
- Không nhất thiết cần giữ index key order.

**Nhớ kiểm tra exact/lossy bitmap và chi phí recheck.**

### Index Only Scan: đường truy cập bổ sung

Khi index cover đủ dữ liệu và visibility map thuận lợi, `Index Only Scan` có thể giảm đọc heap. Tuy nhiên, nó **vẫn có thể phát sinh `Heap Fetches`** và index rộng có chi phí bảo trì riêng.

### Công thức tư duy cuối cùng

```text
SQL + dữ liệu + statistics + index definitions
                  |
                  v
               Planner
                  |
     Estimate selectivity + I/O/CPU cost
                  |
                  v
         Seq / Index / Bitmap / ...
                  |
                  v
          EXPLAIN ANALYZE BUFFERS
                  |
                  v
   So estimate với actual, nhìn toàn plan tree
                  |
                  v
    Đưa ra thay đổi có bằng chứng và đo lại
```

**Quy tắc cốt lõi:** khi thấy `Seq Scan`, `Index Scan` hay `Bitmap Heap Scan`, hãy hỏi **“truy vấn cần bao nhiêu hàng, các hàng nằm ở những heap pages nào, index giúp giảm những truy cập nào và toàn bộ query còn cần sort/join/aggregate ra sao?”**. Trả lời những câu hỏi đó quan trọng hơn việc cố làm cho mọi query hiện chữ `Index Scan`.
