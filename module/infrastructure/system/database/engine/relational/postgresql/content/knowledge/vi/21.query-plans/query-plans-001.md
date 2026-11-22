# EXPLAIN, EXPLAIN ANALYZE và lưu ý khi câu lệnh có tác dụng phụ trong PostgreSQL

Một câu SQL trả đúng kết quả vẫn có thể chạy chậm vì quét quá nhiều hàng, chọn phương pháp nối không phù hợp, sắp xếp dữ liệu lớn, ước lượng số hàng sai hoặc đọc nhiều trang từ bộ nhớ lưu trữ. Để biết PostgreSQL **dự định** chạy truy vấn như thế nào, ta sử dụng `EXPLAIN`. Để biết khi **thực sự chạy**, các node mất bao nhiêu thời gian và xử lý bao nhiêu hàng, ta sử dụng `EXPLAIN ANALYZE`.

Hai tên lệnh trông giống nhau nhưng có khác biệt vận hành rất lớn:

```sql
-- Chỉ lập kế hoạch, KHÔNG thực thi câu UPDATE ở ví dụ thông thường:
EXPLAIN
UPDATE orders
SET status = 'cancelled'
WHERE order_id = 100;

-- Thực sự chạy UPDATE để đo đạc:
EXPLAIN ANALYZE
UPDATE orders
SET status = 'cancelled'
WHERE order_id = 100;
```

Khi một lệnh có tác dụng thay đổi dữ liệu hoặc gọi hàm có **side effect**, thêm `ANALYZE` không còn là thao tác “xem trước vô hại”. `EXPLAIN ANALYZE` **thực thi statement**, kể cả thao tác ghi, trigger và các hiệu ứng có thể đi kèm. Ngay cả khi thử trong transaction rồi `ROLLBACK`, không phải **mọi hiệu ứng** đều được PostgreSQL hoàn tác: ví dụ giá trị được cấp qua sequence (`nextval()`), thay đổi bên ngoài database hoặc lời gọi dịch vụ mạng không tự đảo ngược cùng rollback.

Bài học thuộc chương **Kế hoạch truy vấn** trong module *Database Engine Relational PostgreSQL*, tập trung vào hai năng lực gắn liền:

1. **Đọc và giải thích execution plan**: `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, `Nested Loop`, `Hash Join`, `Merge Join`, `Sort`, `Aggregate`, chi phí ước lượng, số hàng, thời gian, số lần lặp và thống kê bộ đệm.
2. **Dùng EXPLAIN một cách an toàn**: phân biệt lập kế hoạch với thực thi; bảo vệ dữ liệu khi đo `INSERT`, `UPDATE`, `DELETE` và `MERGE`; hiểu `ROLLBACK`, sequence, trigger, function có tác dụng phụ, external I/O và các tình huống commit/transaction.

Sau bài này, bạn có thể tự dựng môi trường thử nghiệm, giải thích plan từ dưới lên, nhận ra dấu hiệu ước lượng sai hoặc truy vấn tốn nhiều tài nguyên, và tránh biến một lần “đo hiệu năng” thành sự cố xóa/sửa dữ liệu.

> **Nguyên tắc an toàn:** Chỉ chạy ví dụ có ghi dữ liệu trên schema riêng `explain_lab` trong database thực hành. Khi muốn kiểm tra kế hoạch mà **không thực thi DML**, dùng `EXPLAIN` **không có** `ANALYZE`. Đối với chức năng gửi email, chuyển tiền, gọi HTTP, cập nhật sequence hoặc trigger có external side effect, **không** coi `BEGIN; EXPLAIN ANALYZE ...; ROLLBACK;` là sandbox hoàn hảo.

---

## 1. Trước tiên: PostgreSQL xử lý truy vấn qua những giai đoạn nào?

Một truy vấn đi qua các bước khái quát:

```text
SQL text
   |
   v
Parser / analyzer
   |
   v
Rewrite (ví dụ rule, view expansion)
   |
   v
Planner / optimizer
   |   Chọn plan và ước lượng cost/rows
   v
Execution plan
   |
   v
Executor
   |   Đọc/ghi tuple, gọi hàm, xử lý JOIN, FILTER,
   |   SORT, AGGREGATE, trigger và các thao tác khác
   v
Kết quả / các tác động lên database
```

Đây là sơ đồ khái niệm, không diễn tả mọi chi tiết nội bộ. Điều quan trọng là **planner chọn cách chạy**, còn **executor thực hiện cách chạy ấy**.

### 1.1. EXPLAIN là góc nhìn của planner

```sql
EXPLAIN
SELECT *
FROM some_table
WHERE id = 42;
```

PostgreSQL lập kế hoạch, thường trình bày:

- Các node dùng để quét bảng hoặc chỉ mục.
- Cách nối, sắp xếp và tổng hợp.
- Số hàng và độ rộng hàng **ước lượng**.
- Chi phí ước lượng của từng phần.

**Không** nhận được kết quả hàng dữ liệu của `SELECT`; bạn nhận được văn bản/JSON diễn tả kế hoạch.

### 1.2. EXPLAIN ANALYZE là góc nhìn khi executor chạy thật

```sql
EXPLAIN (ANALYZE)
SELECT *
FROM some_table
WHERE id = 42;
```

Lần này PostgreSQL **chạy truy vấn**, sau đó bổ sung:

- Số hàng thực tế.
- Thời gian thực tế theo node.
- Số lần node được thực hiện.
- Thời gian lập kế hoạch và thời gian thực thi tổng.
- Các thông tin thực thi khác theo tùy chọn.

Vì thế `ANALYZE` trong `EXPLAIN ANALYZE` là **chế độ thực thi để đo**, không phải thao tác cập nhật thống kê giống lệnh `ANALYZE some_table;`.

### 1.3. Hai nghĩa khác nhau của từ ANALYZE

| Câu lệnh | Vai trò |
|---|---|
| `ANALYZE explain_lab.orders;` | Thu thập/cập nhật thống kê để planner ước lượng |
| `EXPLAIN SELECT ...;` | Xem kế hoạch ước lượng, không chạy truy vấn người dùng theo cách thông thường |
| `EXPLAIN (ANALYZE) SELECT ...;` | Chạy SELECT và đo plan thực tế |
| `EXPLAIN (ANALYZE) DELETE ...;` | **Chạy DELETE thật** rồi đo |

Không nhầm hai cách dùng từ `ANALYZE` này khi viết runbook hoặc hướng dẫn đồng nghiệp.

### 1.4. EXPLAIN không phải câu trả lời cho mọi vấn đề hiệu năng

Execution plan giúp tìm nguyên nhân ở phía database, nhưng tổng độ trễ mà người dùng cảm nhận còn có thể bao gồm:

- Thời gian chờ connection từ pool.
- Thời gian truyền dữ liệu qua mạng.
- Thời gian driver đọc hoặc ánh xạ hàng thành object.
- Chi phí xử lý ứng dụng, serialize JSON, render giao diện.
- Lock waits, transaction retries và queueing bên ngoài thời điểm đo.

Một câu `EXPLAIN ANALYZE` nhanh **không tự chứng minh** cả API nhanh, và một lần đo chậm chưa chứng minh plan luôn kém.

---

## 2. Cú pháp EXPLAIN cơ bản và các tùy chọn

### 2.1. Cách viết đơn giản

```sql
EXPLAIN SELECT ...;

EXPLAIN ANALYZE SELECT ...;

EXPLAIN (ANALYZE, BUFFERS)
SELECT ...;
```

`EXPLAIN` hỗ trợ một số loại statement ngoài `SELECT`, chẳng hạn `INSERT`, `UPDATE`, `DELETE`, `MERGE` và `EXECUTE`. Khi statement là loại có tác động, hãy quyết định **có bật ANALYZE hay không** trước khi chạy.

### 2.2. Các tùy chọn thực tế hay dùng

| Tùy chọn | Ví dụ | Ý nghĩa |
|---|---|---|
| `ANALYZE` | `ANALYZE TRUE` | Thực thi query và ghi nhận thống kê thực |
| `BUFFERS` | `BUFFERS TRUE` | Thông tin thao tác với các buffer/cache, khi áp dụng |
| `VERBOSE` | `VERBOSE TRUE` | Hiển thị chi tiết hơn về output, alias, một số biểu thức |
| `COSTS` | `COSTS FALSE` | Ẩn/hiện số liệu chi phí ước lượng |
| `SETTINGS` | `SETTINGS TRUE` | Hiển thị những cấu hình planner khác mặc định có ảnh hưởng |
| `TIMING` | `TIMING FALSE` | Khi ANALYZE, bỏ đo thời gian từng node để giảm overhead đo |
| `SUMMARY` | `SUMMARY TRUE` | Hiển thị thông tin tổng kết khi có |
| `WAL` | `WAL TRUE` | Thống kê WAL khi có ANALYZE và được hỗ trợ |
| `FORMAT` | `FORMAT JSON` | Định dạng `TEXT`, `JSON`, `XML` hoặc `YAML` |

Tùy chọn và mức chi tiết có thể khác nhau giữa các phiên bản PostgreSQL. Xem tài liệu của **phiên bản server đang chạy** khi một tùy chọn không được nhận diện.

### 2.3. Mẫu phổ biến để chẩn đoán SELECT

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT ...
```

Mẫu này **thực thi SELECT**. Nếu SELECT gọi hàm thay đổi trạng thái hoặc data-modifying CTE, nó vẫn có thể có tác dụng phụ. Mẫu chỉ phù hợp khi bạn đã xác nhận logic được thực thi an toàn.

### 2.4. Mẫu giảm overhead đo thời gian theo node

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT ...
```

`TIMING OFF` giúp giảm một phần chi phí lấy timestamp ở rất nhiều lần chạy node, trong khi vẫn thu nhận số hàng và số lần lặp. Nó không làm statement ngừng thực thi, và không loại bỏ mọi overhead do instrumentation.

### 2.5. Xem plan dạng JSON

```sql
EXPLAIN (FORMAT JSON)
SELECT *
FROM explain_lab.orders
WHERE order_id = 100;
```

Với `FORMAT JSON`, kết quả có cấu trúc máy đọc được, thuận tiện cho các công cụ so sánh plan. Một phần cấu trúc có dạng:

```json
[
  {
    "Plan": {
      "Node Type": "Index Scan",
      "Relation Name": "orders",
      "Alias": "orders",
      "Startup Cost": 0.0,
      "Total Cost": 0.0,
      "Plan Rows": 1,
      "Plan Width": 1
    }
  }
]
```

Các số `0.0` và `1` ở ví dụ JSON chỉ là **placeholder minh họa cấu trúc**, không phải plan thật của PostgreSQL. Đừng copy chúng làm ngưỡng kiểm định hiệu năng.

---

## 3. Phòng thực hành: tạo dữ liệu đủ đa dạng để xem plan

Tất cả ví dụ dưới đây dùng schema `explain_lab`. Tạo schema trên database **thực hành**, không trên database production.

### 3.1. Xác nhận môi trường

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Không chạy tiếp nếu chưa xác nhận đúng môi trường, đặc biệt trước các ví dụ đo `DELETE` và sequence.

### 3.2. Tạo bảng khách hàng

```sql
CREATE SCHEMA IF NOT EXISTS explain_lab;

CREATE TABLE explain_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    segment TEXT NOT NULL
        CHECK (segment IN ('standard', 'premium', 'enterprise'))
);
```

### 3.3. Tạo bảng đơn hàng

```sql
CREATE TABLE explain_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL
        REFERENCES explain_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled', 'refunded')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    archived BOOLEAN NOT NULL DEFAULT FALSE
);
```

Ở schema này, `customers.customer_id` là khóa toàn cục; `tenant_id` trên bảng orders có vai trò phục vụ bộ lọc và mẫu workload. Một ứng dụng multi-tenant thực tế cần thêm ràng buộc bảo đảm khách hàng và đơn hàng cùng tenant, ví dụ FK ghép, nếu hai cột có thể được ghi tùy ý.

### 3.4. Sinh 1.000 khách hàng

```sql
INSERT INTO explain_lab.customers
    (customer_id, tenant_id, customer_name, segment)
SELECT
    g,
    1 + (g % 10) AS tenant_id,
    'Customer-' || g::text,
    CASE
        WHEN g % 20 = 0 THEN 'enterprise'
        WHEN g % 5 = 0 THEN 'premium'
        ELSE 'standard'
    END
FROM generate_series(1, 1000) AS gs(g);
```

### 3.5. Sinh 100.000 đơn hàng

```sql
INSERT INTO explain_lab.orders
    (tenant_id, customer_id, status,
     amount, created_at, archived)
SELECT
    1 + ((1 + (g % 1000)) % 10) AS tenant_id,
    1 + (g % 1000) AS customer_id,
    CASE
        WHEN g % 100 < 8 THEN 'pending'
        WHEN g % 100 < 80 THEN 'paid'
        WHEN g % 100 < 95 THEN 'cancelled'
        ELSE 'refunded'
    END AS status,
    ((g % 500) + 1)::numeric(12, 2) AS amount,
    TIMESTAMPTZ '2026-09-01 00:00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    (g % 100 < 5) AS archived
FROM generate_series(1, 100000) AS gs(g);
```

Phép tính tenant_id của order cố ý khớp với tenant_id của customer có `customer_id=1+(g%1000)`. Đây là dữ liệu mô phỏng theo quy tắc xác định, không đại diện phân bố dữ liệu production.

**Lưu ý:** Các khối `INSERT` sinh dữ liệu **không idempotent** nếu chạy lặp. Chỉ chạy một lần trên schema mới. Không dùng `TRUNCATE ... CASCADE` để reset bừa bãi trong database dùng chung.

### 3.6. Kiểm tra số hàng và trạng thái

```sql
SELECT COUNT(*) AS customers_count
FROM explain_lab.customers;

SELECT COUNT(*) AS orders_count
FROM explain_lab.orders;

SELECT status, COUNT(*) AS cnt
FROM explain_lab.orders
GROUP BY status
ORDER BY status;
```

Với dữ liệu được tạo một lần, dự kiến:

| status | Số hàng |
|---|---:|
| pending | 8.000 |
| paid | 72.000 |
| cancelled | 15.000 |
| refunded | 5.000 |
| **Tổng** | **100.000** |

### 3.7. Cập nhật thống kê

```sql
ANALYZE explain_lab.customers;
ANALYZE explain_lab.orders;
```

Planner cần các ước lượng về số hàng, phân bố giá trị, tương quan, số trang bảng... `ANALYZE` giúp cập nhật thống kê theo mẫu lấy từ dữ liệu; không phải một cam kết số hàng ước lượng luôn khớp chính xác số hàng thực tế.

---

## 4. Kế hoạch truy vấn là một cây node

Ví dụ query lấy đơn của một tenant:

```sql
EXPLAIN
SELECT order_id, customer_id, amount
FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'pending';
```

Kế hoạch có thể được trình bày như một cây:

```text
Một node cấp trên
    |
    +-- node quét dữ liệu
           |
           +-- điều kiện lọc
```

Một kế hoạch giả định:

```text
Seq Scan on orders
  (cost=0.00..2500.00 rows=800 width=28)
  Filter: ((tenant_id = 3) AND (status = 'pending'))
```

Số `2500.00`, `800` và `28` ở đây **chỉ để minh họa cách đọc**. Plan thật phụ thuộc thống kê, kích thước bảng, PostgreSQL version và các index đang có.

### 4.1. Đọc cây plan từ dưới lên

Với query phức tạp:

```text
Aggregate
  -> Sort
      -> Hash Join
          -> Seq Scan on orders
          -> Hash
              -> Seq Scan on customers
```

Thứ tự giải thích dễ hiểu:

1. Lấy các hàng từ `orders`.
2. Lấy các hàng từ `customers`.
3. Xây bảng băm từ đầu vào thích hợp.
4. Nối các hàng theo `Hash Join`.
5. Sắp xếp nếu node yêu cầu.
6. Tổng hợp và trả kết quả.

Đây là diễn giải **luồng dữ liệu** của các node, không phải bảo đảm executor luôn tính toàn bộ đầu vào mỗi node xong mới sang node sau. Nhiều node dùng cơ chế pull/iterator, xử lý theo luồng hoặc chia nhỏ.

### 4.2. Thụt lề thể hiện quan hệ cha–con

Trong `EXPLAIN` dạng text:

```text
Parent Node
  -> Child Node 1
  -> Child Node 2
```

Các dấu `->` cùng thụt lề cho biết **node nào cung cấp dữ liệu cho node nào**. Muốn giải thích vì sao một node cha chậm, thường phải xem các node con và khối lượng dữ liệu chúng chuyển lên.

---

## 5. Đọc cost, rows và width: dự báo, không phải phép đo

Một dòng plan giả định:

```text
Index Scan using orders_pkey on orders
  (cost=0.42..8.44 rows=1 width=36)
```

Có ba khái niệm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `cost=0.42..8.44` | **Startup cost** và **total cost** ước lượng |
| `rows=1` | Số hàng planner **ước lượng node trả về** |
| `width=36` | Kích thước hàng trung bình planner ước lượng, tính bằng byte |

### 5.1. Cost không phải milliseconds

`cost` là đơn vị chi phí **nội bộ của planner**, được cấu thành từ các tham số tương đối như:

- `seq_page_cost`, `random_page_cost`.
- `cpu_tuple_cost`, `cpu_index_tuple_cost`, `cpu_operator_cost`.
- Các chi phí và ước lượng khác liên quan đến I/O, CPU, parallelism.

`cost=8.44` **không có nghĩa 8,44 ms**. Nó là thước đo tương đối để PostgreSQL so sánh các phương án.

### 5.2. Startup cost và total cost

**Startup cost** là lượng chi phí dự kiến trước khi node có thể tạo hàng đầu tiên. **Total cost** là chi phí ước lượng để trả toàn bộ kết quả node theo mô hình planner.

Ví dụ:

- `Seq Scan` thường có startup cost thấp: có thể bắt đầu trả hàng khi quét.
- `Sort` thông thường cần thu nhận đủ dữ liệu đầu vào trước khi có hàng đầu theo thứ tự, nên startup cost có thể đáng kể.
- `Limit` có thể khiến một plan có **startup cost thấp** được ưu tiên hơn plan có total cost thấp hơn nhưng khởi đầu chậm, vì query chỉ lấy ít hàng.

### 5.3. Cost không cộng đơn giản theo dòng

Chi phí node cha **thường đã tính chi phí của node con** theo mô hình planner. Không cộng mọi `total cost` trong cây để báo “tổng chi phí”, vì dễ **đếm trùng**.

Muốn so sánh phương án, nhìn cost của root plan và đọc các node để hiểu thành phần tạo chi phí.

### 5.4. Rows là số hàng ở đầu ra của node

Nếu plan viết:

```text
Seq Scan on orders
  (cost=0.00..X rows=800 width=Y)
  Filter: (status = 'pending')
```

`rows=800` là **ước lượng số hàng sau lọc**, không phải mặc định toàn bộ hàng của bảng. Truy vấn thực tế có thể trả nhiều/ít hơn rất nhiều do thống kê hoặc tương quan dữ liệu.

### 5.5. Width ảnh hưởng tới tính toán

Khi query lấy cả cột lớn `payload JSONB`, planner có thể dự đoán width lớn hơn so với query chỉ lấy ID và thời gian. Chiều rộng đầu ra ảnh hưởng tới ước lượng chi phí xử lý, sắp xếp, hash và bộ nhớ.

Do vậy `SELECT *` trong query phân tích không tương đương với query production chỉ lấy vài cột; hãy dùng cùng projection khi so hiệu năng.

---

## 6. Đọc actual time, actual rows và loops

Khi bật `ANALYZE`:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM explain_lab.orders
WHERE order_id = 100;
```

Một node có thể hiển thị theo dạng:

```text
Index Scan using orders_pkey on orders
  (cost=0.42..8.44 rows=1 width=8)
  (actual time=0.025..0.027 rows=1 loops=1)
```

### 6.1. Actual time: thời gian thực tế được đo

`actual time=a..b` mô tả thời gian quan sát đến hàng đầu và khi hoàn tất node theo đơn vị **milliseconds**, chịu ảnh hưởng cách node được lặp và instrumentation.

Không so trực tiếp `cost=8.44` với `actual time=0.027`; chúng dùng hai **thước đo khác nhau**.

### 6.2. Actual rows thường là giá trị trung bình mỗi loop

Một lưu ý rất quan trọng: khi node được chạy nhiều lần, PostgreSQL hiển thị các con số `actual rows` và `actual time` theo cách **trung bình trên mỗi lần thực thi node** trong text plan, còn `loops` cho biết số lần.

Ví dụ:

```text
Index Scan on customers
  (actual time=0.004..0.005 rows=1 loops=1000)
```

Diễn giải gần đúng:

- Node được gọi **1.000 lần**.
- Mỗi lần trả trung bình khoảng **1 hàng**.
- Tổng số hàng qua node ở mọi lần gọi khoảng **1.000**, không phải một hàng duy nhất.

Không cộng số hàng node con một cách ngây thơ nếu chưa nhân/diễn giải `loops`.

### 6.3. Rows Removed by Filter

Một Seq Scan có thể báo:

```text
Rows Removed by Filter: 99000
```

Nó cho biết nhiều tuple đã được xem xét nhưng không vượt qua filter của node. Với node chạy nhiều lần, giá trị hiển thị cũng cần được đọc theo quy ước instrumentation/loops.

Tuy nhiên, `Rows Removed by Filter` **không đồng nghĩa** số trang đĩa đọc, số hàng trong bảng hoặc số phép gọi hàm ở mọi tầng.

### 6.4. So estimated vs actual đúng cách

Nếu:

```text
rows=10
actual rows=10000 loops=1
```

planner đã ước lượng thấp hơn khoảng **1.000 lần** tại node đó.

Đây là một **tín hiệu đáng điều tra**, vì sai lệch lớn có thể khiến planner chọn sai join hoặc sort. Nhưng chưa thể kết luận “cần thêm index” ngay; nguyên nhân có thể là:

- Thống kê cũ.
- Dữ liệu lệch phân bố.
- Tương quan giữa nhiều cột.
- Biểu thức/hàm khó ước lượng.
- Parameter-sensitive plan.
- Kết quả phụ thuộc dữ liệu biến động theo thời điểm.

### 6.5. Vì sao total Execution Time không bằng tổng actual time của mọi node?

Thời gian của node cha thường **bao gồm thời gian hoạt động của node con**. Nếu cộng mọi dòng `actual time`, bạn có thể đếm trùng nhiều lần. Node có `loops` lớn càng dễ gây nhầm.

Hãy đọc theo **cây thực thi**, tìm đường dẫn tốn thời gian/khối lượng, rồi đối chiếu thời gian tổng của plan. Đừng coi các con số là danh sách công việc độc lập có thể cộng tuyến tính.

---

## 7. Các node quét dữ liệu thường gặp

### 7.1. Seq Scan: quét bảng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM explain_lab.orders
WHERE status = 'paid';
```

Vì khoảng **72%** đơn trong dữ liệu seed có status paid, quét tuần tự có thể là một lựa chọn hợp lý: query cần xem rất nhiều hàng. Seq Scan **không mặc nhiên là lỗi**.

Khi thấy Seq Scan:

1. Bao nhiêu hàng/tỷ lệ hàng cần lấy?
2. Có index đúng predicate/key không?
3. Query chỉ lấy vài hàng hay gần toàn bộ bảng?
4. Có điều kiện dùng hàm khiến index key thông thường khó dùng?
5. Planner có ước lượng đúng số hàng không?

### 7.2. Index Scan: dùng chỉ mục rồi truy cập heap khi cần

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, amount
FROM explain_lab.orders
WHERE order_id = 100;
```

Khóa chính trên `order_id` tạo một B-tree index. Query tìm một khóa thường thích hợp với Index Scan, vì không cần quét 100.000 hàng để tìm một order.

Index Scan có thể vẫn cần truy cập **heap** để lấy cột không nằm trong index hoặc kiểm tra visibility.

### 7.3. Index Only Scan: chỉ mục đủ cột nhưng MVCC vẫn quan trọng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM explain_lab.orders
WHERE order_id BETWEEN 100 AND 200;
```

Nếu mọi cột query cần đều có trong index, planner **có thể** chọn Index Only Scan. Nhưng PostgreSQL còn phải xét visibility map; nếu trang heap chưa được đánh dấu all-visible, vẫn có thể có **Heap Fetches**.

Không kết luận “Index Only Scan = không bao giờ đọc heap”.

### 7.4. Bitmap Index Scan và Bitmap Heap Scan

Một kế hoạch có thể dùng:

```text
Bitmap Heap Scan on orders
  Recheck Cond: (...)
  -> Bitmap Index Scan on some_index
       Index Cond: (...)
```

Khái quát:

1. Bitmap Index Scan xác định các vị trí tuple/page liên quan.
2. Bitmap Heap Scan lấy dữ liệu từ heap theo các vị trí đã thu thập.
3. Có thể phải recheck điều kiện, nhất là khi bitmap mất độ chính xác ở mức page (*lossy bitmap*).

Bitmap scan có thể hữu ích khi query lấy nhiều hàng hơn một Index Scan nhỏ nhưng chưa tới mức quét cả bảng là tốt nhất.

### 7.5. Index Cond khác Filter

Ví dụ plan:

```text
Index Scan using idx_orders_tenant_status on orders
  Index Cond: ((tenant_id = 3) AND (status = 'pending'))
  Filter: (amount > 200)
```

**Index Cond** là phần điều kiện dùng để định hướng truy cập index. **Filter** là bước loại thêm các hàng được lấy ra.

Không phải mọi điều kiện trong `WHERE` đều thành Index Cond chỉ vì có index trên bảng. Thứ tự index key, toán tử, kiểu dữ liệu, expression index và khả năng suy ra predicate đều ảnh hưởng.

---

## 8. Tạo index và quan sát thay đổi kế hoạch

### 8.1. Đo trước khi tạo index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, amount
FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'pending'
ORDER BY created_at DESC
LIMIT 20;
```

Hãy ghi lại plan, thời gian, buffer activity và số hàng.

### 8.2. Tạo index phù hợp bộ lọc

```sql
CREATE INDEX orders_tenant_status_created_idx
ON explain_lab.orders
    (tenant_id, status, created_at DESC);

ANALYZE explain_lab.orders;
```

### 8.3. Đo lại cùng query

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, amount
FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'pending'
ORDER BY created_at DESC
LIMIT 20;
```

Một B-tree trên `(tenant_id, status, created_at DESC)` có thể hỗ trợ:

- Tìm hàng theo `tenant_id` và `status`.
- Đi theo `created_at DESC` phù hợp `ORDER BY`.
- Dừng khi lấy đủ `LIMIT 20` mà không cần xử lý mọi hàng phù hợp.

Nhưng kế hoạch thực tế vẫn phụ thuộc dữ liệu, bộ nhớ, planner cost settings và phiên bản.

### 8.4. Tránh kết luận từ một phép đo

Lần chạy đầu có thể phải đưa trang vào cache, còn lần sau hưởng cache ấm. Do đó:

- So sánh cùng query, cùng tham số và dữ liệu tương đối ổn định.
- Chạy nhiều lần trong lab và xem sự biến thiên.
- Đối chiếu `Buffers`, không chỉ một giá trị `Execution Time`.
- Kiểm tra khối lượng truy vấn khác bị ảnh hưởng bởi index mới.
- Xem chi phí INSERT/UPDATE/DELETE do index bổ sung.

Không lấy kết quả “sau khi tạo index lần 2 nhanh hơn lần 1” làm bằng chứng duy nhất index mới mang lại toàn bộ cải thiện.

---

## 9. Các node JOIN: Nested Loop, Hash Join, Merge Join

### 9.1. Query mẫu

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.segment,
    COUNT(*) AS order_count,
    SUM(o.amount) AS total_amount
FROM explain_lab.orders AS o
JOIN explain_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
GROUP BY c.segment
ORDER BY total_amount DESC;
```

Query vừa lọc orders, vừa JOIN customers, vừa tổng hợp và sắp xếp.

### 9.2. Nested Loop

```text
Nested Loop
  -> Outer input
  -> Inner lookup (loops = số lần gọi cho outer rows)
```

Thích hợp trong nhiều trường hợp outer ít hàng và inner có index lookup nhanh. Nhưng nếu outer lớn và inner bị quét lại rất nhiều lần, chi phí có thể tăng mạnh.

Ví dụ phát hiện:

```text
Index Scan on customers
  (actual ... rows=1 loops=50000)
```

Không nhìn `rows=1` rồi nghĩ node chỉ làm một lookup; `loops=50000` là dấu hiệu nó có thể đã được gọi rất nhiều lần.

### 9.3. Hash Join

```text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  -> Scan on orders
  -> Hash
       -> Scan on customers
```

PostgreSQL xây hash table từ một phía, rồi dùng khóa hash để tìm các hàng tương ứng ở phía còn lại. Thường phù hợp với phép nối equality trên tập dữ liệu vừa/lớn, tùy phân bố, bộ nhớ và thống kê.

Các thông tin như `Buckets`, `Batches`, `Memory Usage` có thể xuất hiện khi ANALYZE. Nhiều batches có thể gợi ý hash table vượt ngân sách bộ nhớ và cần xử lý theo đợt/ghi temp.

### 9.4. Merge Join

```text
Merge Join
  Merge Cond: (a.key = b.key)
  -> Sort / ordered scan on a
  -> Sort / ordered scan on b
```

Merge Join hoạt động trên dữ liệu được sắp theo khóa nối. Nếu đầu vào đã có thứ tự phù hợp từ index, có thể tránh một số thao tác Sort; nếu không, chi phí sắp xếp cần được tính.

### 9.5. Không đánh giá JOIN chỉ bằng tên node

`Hash Join` không phải lúc nào cũng nhanh hơn `Nested Loop`, và `Merge Join` không phải luôn tốt nhất khi có index. Planner lựa chọn theo:

- Số hàng mỗi phía.
- Độ chọn lọc điều kiện.
- Kiểu phép nối.
- Khả năng lấy hàng theo index.
- Bộ nhớ dự kiến.
- Thứ tự dữ liệu.
- Chi phí I/O/CPU và parallelism.

Trước khi thử thay đổi cấu hình planner, hãy xác minh **ước lượng số hàng** và **query/index design**.

---

## 10. Sort, Aggregate, HashAggregate và GroupAggregate

### 10.1. Sort

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM explain_lab.orders
WHERE status = 'paid'
ORDER BY amount DESC
LIMIT 30;
```

Nếu không có đường truy cập đã sắp theo `amount DESC` phù hợp điều kiện, planner có thể cần node `Sort`. Với `LIMIT` nhỏ, có thể dùng **top-N heapsort**, tránh lưu toàn bộ thứ tự như một sort đầy đủ.

Thông tin hay gặp:

```text
Sort Key: amount DESC
Sort Method: top-N heapsort  Memory: ...
```

Không đoán chắc phương pháp Sort khi chưa xem `EXPLAIN ANALYZE`.

### 10.2. Sort tràn ra đĩa tạm

Khi khối lượng sort lớn hơn ngân sách bộ nhớ theo kế hoạch thực thi, PostgreSQL có thể dùng external sort và ghi/đọc temporary files.

Plan có thể báo:

```text
Sort Method: external merge  Disk: ...
Buffers: temp read=... written=...
```

Đây là dấu hiệu nên xem:

- Có thể giảm số hàng trước khi sort không?
- Có index cho điều kiện `ORDER BY` phù hợp không?
- Có thể đổi query để nhóm/lọc sớm hơn không?
- `work_mem` có phù hợp, xét nhiều sort/hash nodes và nhiều session đồng thời không?

Không tăng `work_mem` toàn hệ thống thật lớn chỉ để cải thiện một query: một session có thể có nhiều node cần bộ nhớ, và nhiều session chạy song song sẽ nhân nhu cầu tài nguyên.

### 10.3. Aggregate

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*), AVG(amount)
FROM explain_lab.orders
WHERE status = 'paid';
```

Một node `Aggregate` có thể tổng hợp hàng đã lọc thành một dòng. Đầu vào vẫn có thể phải đọc rất nhiều hàng; đừng thấy root trả `rows=1` rồi kết luận query nhẹ.

### 10.4. HashAggregate và GroupAggregate

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, status, SUM(amount)
FROM explain_lab.orders
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

PostgreSQL có thể:

- Dùng `HashAggregate` để gom nhóm qua hash table.
- Dùng `GroupAggregate` trên dữ liệu đã có thứ tự phù hợp.
- Kết hợp `Sort`/`Gather`/partial aggregation tùy plan.

Đánh giá theo số nhóm, số hàng đầu vào, memory, batches, temp I/O, độ phù hợp của ordering và mức song song.

---

## 11. BUFFERS: plan đang chạm vào bộ nhớ như thế nào?

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM explain_lab.orders
WHERE status = 'cancelled';
```

Bạn có thể thấy thông tin dạng:

```text
Buffers: shared hit=120 read=8
```

Các số chỉ minh họa. Những nhãn thường gặp:

| Nhãn | Ý nghĩa khái quát |
|---|---|
| `shared hit` | Trang đã có trong PostgreSQL shared buffers |
| `shared read` | Trang được đưa vào shared buffers qua đường đọc, không nhất thiết thiết bị đĩa vật lý đã thực hiện I/O |
| `shared dirtied` | Trang shared buffer được sửa thành dirty trong quá trình quan sát |
| `shared written` | Trang shared buffer được ghi ra trong phạm vi công việc được theo dõi |
| `local ...` | Hoạt động với local buffers cho các loại quan hệ áp dụng |
| `temp read/written` | Đọc/ghi trang tạm, ví dụ Sort/Hash tràn ngân sách bộ nhớ |

### 11.1. Shared hit không có nghĩa “hoàn toàn miễn phí”

Đọc trang đã nằm trong shared buffers vẫn cần CPU, thao tác trên tuple, kiểm tra điều kiện, visibility và các bước xử lý khác. Query có hàng triệu `shared hit` vẫn có thể chậm do lượng công việc lớn.

### 11.2. Shared read không bằng số lần đọc đĩa vật lý

`shared read` phản ánh đường đọc của PostgreSQL vào buffer cache. Hệ điều hành có thể đã cache dữ liệu, nên một trang được báo “read” **không nhất thiết** phải truy cập ổ đĩa vật lý.

Đừng tính “số shared read × thời gian disk ước lượng” rồi coi đó là độ trễ thật.

### 11.3. Parent có thể bao gồm buffer của child

Các thống kê buffer ở node có quy tắc cộng dồn theo cây. Không cộng tất cả dòng `Buffers` trong plan nếu muốn số truy cập tổng; dễ đếm trùng công việc của node con.

### 11.4. I/O timing

Nếu server được cấu hình thu thập thời gian I/O theo cơ chế phiên bản tương ứng, `EXPLAIN ANALYZE` có thể bổ sung thông tin như `I/O Timings`. Việc đo I/O cũng có chi phí instrumentation và phụ thuộc thiết lập như `track_io_timing`.

Không khẳng định mọi server đều hiển thị I/O timing chỉ vì đã thêm `BUFFERS`.

### 11.5. Temp I/O gợi ý hướng điều tra

Nếu plan có:

```text
Buffers: temp read=... written=...
```

hãy tìm node `Sort`, `Hash`, `HashAggregate` hoặc các node liên quan có nhu cầu bộ nhớ. Xem dữ liệu đầu vào có lớn bất thường do JOIN fanout hoặc ước lượng sai không, thay vì chỉ tăng bộ nhớ.

---

## 12. Planning Time và Execution Time

Kết quả `EXPLAIN ANALYZE` thường có các dòng tổng kết:

```text
Planning Time: 0.250 ms
Execution Time: 3.400 ms
```

Đây là số **minh họa**.

### 12.1. Planning Time

Bao gồm công việc lập kế hoạch được báo cáo trong ngữ cảnh đo. Query phức tạp với nhiều JOIN, nhiều phương án index hoặc phân vùng có thể mất nhiều thời gian planning.

Khi một query chạy rất nhanh nhưng được thực thi hàng nghìn lần với tham số khác nhau, chi phí planning lặp lại có thể đáng kể. Prepared statements/generic plan có thể liên quan, nhưng không áp dụng một chiến lược cho mọi trường hợp.

### 12.2. Execution Time

Là thời gian executor chạy trong phạm vi instrumentation, bao gồm các công việc liên quan tới node và một số overhead thực thi. Nó **không đồng nhất** với thời gian đầy đủ mà ứng dụng nhận kết quả qua mạng và xử lý.

### 12.3. Độ dài câu trả về và serialization

Một query trả 1 triệu hàng có thể tốn nhiều thời gian **truyền, encode và xử lý ở client** sau khi executor đã có plan tương đối nhanh. Các phiên bản PostgreSQL mới cung cấp một số chế độ đo serialization có điều kiện; nếu môi trường không hỗ trợ, vẫn nên đo round-trip từ application để có bức tranh end-to-end.

### 12.4. Timing OFF không có nghĩa query thực thi không mất thời gian

`TIMING OFF` chỉ thay đổi **cách thu thập và trình bày đo thời gian node**. Statement vẫn được thực thi, bộ lọc vẫn chạy, dữ liệu vẫn được ghi nếu đó là DML, trigger vẫn có thể xảy ra.

---

## 13. Quan trọng nhất: EXPLAIN và EXPLAIN ANALYZE với câu lệnh ghi

### 13.1. So sánh an toàn của EXPLAIN DML

```sql
EXPLAIN
UPDATE explain_lab.orders
SET status = 'cancelled'
WHERE order_id = 100;
```

Với trường hợp thông thường, PostgreSQL **chỉ lập kế hoạch** và **không sửa status của order 100**. Nó có thể cho biết node `Update on orders` và đường truy cập để tìm hàng.

**Phân biệt tinh tế:** “không thực thi DML” không đồng nghĩa một lần lập kế hoạch tuyệt đối không thể gây hiệu ứng bên ngoài trong mọi cấu hình tùy biến: quá trình planning có thể sử dụng metadata, khóa cần thiết, gọi một số logic lập kế hoạch và có thể đánh giá các biểu thức hằng hoặc hàm được khai báo không đúng volatility. Không coi `EXPLAIN` là sandbox cho mã extension/hàm tùy biến không đáng tin. Nhưng với SQL PostgreSQL thông thường, nó là cách thích hợp để **xem plan mà không thực thi UPDATE/DELETE**.

### 13.2. EXPLAIN ANALYZE DML chạy thật

```sql
EXPLAIN ANALYZE
UPDATE explain_lab.orders
SET status = 'cancelled'
WHERE order_id = 100;
```

Lệnh này **thực thi UPDATE**. Nếu chạy ngoài transaction tường minh trong client autocommit, thay đổi có thể được commit ngay sau statement thành công.

Không chạy lệnh này trên production để “xem thử” nếu bạn không thực sự muốn và được phép thay đổi dữ liệu.

### 13.3. EXPLAIN ANALYZE DELETE chạy thật

```sql
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM explain_lab.orders
WHERE status = 'cancelled';
```

Trong dữ liệu seed, nhiều nghìn đơn có `status='cancelled'`. Lệnh sẽ **xóa các hàng phù hợp** khi thực thi và có thể gây:

- MVCC dead tuples.
- WAL, I/O và duy trì index.
- Kiểm tra FK và trigger.
- Locking, blocking hoặc deadlock trong workload đồng thời.
- Replication lag và tải autovacuum sau đó.

Do vậy **không bao giờ** dùng ví dụ này ngoài môi trường kiểm soát; ở đây nó chỉ để minh họa nguy cơ, không phải bài tập bắt buộc chạy.

### 13.4. EXPLAIN ANALYZE INSERT cũng chèn hàng

```sql
-- Chỉ chạy trong lab transaction theo phần tiếp theo.
EXPLAIN ANALYZE
INSERT INTO explain_lab.customers
    (customer_id, tenant_id, customer_name, segment)
VALUES (2001, 1, 'Test EXPLAIN', 'standard');
```

Nếu chạy trực tiếp thành công, hàng `2001` đã được chèn. `EXPLAIN ANALYZE` có thể chỉ hiển thị plan/thời gian, **không tự trả về hàng được chèn theo cách câu INSERT thường làm**, nhưng tác động đã xảy ra.

### 13.5. MERGE cũng có thể thay đổi dữ liệu

`MERGE` (PostgreSQL 15+) có thể chọn `INSERT`, `UPDATE` hoặc `DELETE` theo điều kiện. `EXPLAIN ANALYZE MERGE ...` **thực thi** những hành động tương ứng khi được server hỗ trợ và hợp lệ.

Không cho rằng lệnh có nhiều nhánh `WHEN MATCHED`/`WHEN NOT MATCHED` chỉ là mô tả kế hoạch: nó có thể ghi thật.

---

## 14. Thử EXPLAIN ANALYZE UPDATE trong transaction và ROLLBACK

Trong lab, có thể quan sát DML rồi hoàn tác những thay đổi **transactional**.

### 14.1. Xác nhận giá trị trước

```sql
SELECT order_id, status, amount
FROM explain_lab.orders
WHERE order_id = 100;
```

Đầu vào cụ thể có thể cho status `paid`, `pending`, v.v. tùy dữ liệu seed.

### 14.2. Thực thi trong transaction thử nghiệm

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE explain_lab.orders
SET status = 'cancelled'
WHERE order_id = 100;

-- Statement kế tiếp trong cùng transaction
-- sẽ nhìn thấy thay đổi do transaction của chính mình tạo:
SELECT order_id, status
FROM explain_lab.orders
WHERE order_id = 100;

ROLLBACK;
```

Ở giữa transaction, SELECT của chính connection này có thể thấy `cancelled`. Sau `ROLLBACK`, thay đổi ở bảng `orders` được hoàn tác.

### 14.3. Kiểm tra lại sau rollback

```sql
SELECT order_id, status
FROM explain_lab.orders
WHERE order_id = 100;
```

Giá trị sẽ trở lại trạng thái trước transaction thử nghiệm, **miễn không có giao dịch khác thay đổi hàng trong lúc bạn thử**.

### 14.4. ROLLBACK bảo vệ những gì?

Với hoạt động thông thường được quản lý bởi transaction PostgreSQL:

- `INSERT`/`UPDATE`/`DELETE` trên bảng được rollback.
- Các index entries tạo/thay đổi bởi thao tác transactional sẽ không trở thành trạng thái đã commit hợp lệ.
- Thay đổi của trigger viết vào **bảng PostgreSQL trong cùng transaction** cũng được rollback.

Nhưng vẫn có các loại hiệu ứng không được hoàn tác theo cách đó; xem phần sequence, external side effects và lock/WAL ở các mục tiếp.

### 14.5. Giới hạn thực tế của “đo rồi rollback”

- Statement vẫn phải làm việc thật, có thể tạo WAL, dead tuples và tải tài nguyên.
- Nó có thể giữ row/table locks trong lúc transaction thử nghiệm mở.
- Nó có thể bị trigger/constraint từ chối hoặc kích hoạt luồng xử lý khác.
- Nó có thể làm tăng replication/WAL pressure ngay cả khi rollback.
- `ROLLBACK` không đảo được side effects **ngoài database**.
- Một số thao tác như sử dụng sequence không rollback giá trị đã cấp.

**Vì vậy, với sản xuất, phương án ưu tiên là EXPLAIN không ANALYZE hoặc đo trên bản sao an toàn**. Transaction thử nghiệm chỉ phù hợp khi đã đánh giá rõ các hiệu ứng và chấp nhận tải.

---

## 15. EXPLAIN ANALYZE SELECT vẫn có thể có tác dụng phụ

Một cách nghĩ nguy hiểm là “`SELECT` thì chắc chắn chỉ đọc”.

PostgreSQL cho phép gọi **hàm VOLATILE**, thao tác sequence và thậm chí data-modifying CTE trong một statement trả kết quả theo dạng SELECT.

### 15.1. Sequence nextval()

Tạo sequence demo:

```sql
CREATE SEQUENCE explain_lab.test_seq
    START WITH 1
    INCREMENT BY 1;
```

Thử:

```sql
BEGIN;

EXPLAIN (ANALYZE)
SELECT nextval('explain_lab.test_seq'::regclass);

ROLLBACK;
```

Mặc dù transaction đã rollback, `nextval()` **đã được thực thi** trong quá trình đo, và lần tăng sequence **không được hoàn tác**.

### 15.2. Xác nhận sequence không rollback

```sql
SELECT last_value, is_called
FROM explain_lab.test_seq;

SELECT nextval('explain_lab.test_seq'::regclass)
    AS another_value;
```

Giá trị phụ thuộc các lần chạy trước, cache và các session khác; không bắt buộc phải bằng 1 hoặc 2. Điểm cần quan sát là **không có cam kết rollback trả lại giá trị sequence đã cấp**.

**Bài học:** Nếu chỉ muốn xem kế hoạch, đừng bật `ANALYZE` cho câu SELECT dùng `nextval()` trong môi trường mà sequence có ý nghĩa nghiệp vụ.

### 15.3. Vì sao sequence cố tình không rollback?

Sequences được thiết kế cho cấp số hiệu quả trong môi trường đồng thời. Nếu rollback một giao dịch mà tự “trả lại số” đã cấp, transaction khác có thể đã nhận/nhìn thấy các số sau đó, khiến thứ tự cấp số và tính đúng đắn đồng thời phức tạp.

Khoảng trống trong sequence sau rollback là hành vi bình thường. Không dùng sequence làm cam kết **không có số bị bỏ qua**.

### 15.4. Hàm gửi email, ghi file, gọi HTTP hoặc dịch vụ ngoài

Một SELECT có thể gọi hàm do extension/ứng dụng định nghĩa:

```sql
-- Chỉ minh họa. Không phải hàm PostgreSQL tích hợp.
-- SELECT external_service_send_notification(100);
```

Nếu thực thi thông qua `EXPLAIN ANALYZE`, hàm ấy có thể:

- Gửi email.
- Gọi HTTP API.
- Ghi file.
- Gửi thông điệp sang queue ngoài DB.
- Kích hoạt dịch vụ thanh toán.

`ROLLBACK` của PostgreSQL **không tự hoàn tác** một email đã gửi hoặc một giao dịch đã thực hiện ở hệ thống ngoài.

### 15.5. SELECT gọi hàm ghi database

PostgreSQL cho phép function với đặc tính VOLATILE thực hiện những thao tác side effect được phép trong ngữ cảnh tương ứng. Có thể:

```sql
-- Hàm tùy biến có thể ghi một bảng audit bên trong cùng transaction:
-- SELECT my_function_that_inserts_audit_row(...);
```

Nếu hàm ghi vào một bảng PostgreSQL **cùng transaction**, thay đổi đó thông thường được rollback khi transaction rollback. Nhưng nếu hàm giao tiếp một hệ thống khác hoặc cấp sequence, ngoại lệ đã nêu vẫn áp dụng.

Không suy ra “hễ SELECT là an toàn” chỉ từ động từ SQL.

---

## 16. Data-modifying CTE: SELECT có thể bao một UPDATE thật

PostgreSQL hỗ trợ các statement sửa dữ liệu trong `WITH` với cơ chế `RETURNING`.

Ví dụ:

```sql
WITH changed AS (
    UPDATE explain_lab.orders
    SET archived = TRUE
    WHERE order_id = 100
    RETURNING order_id
)
SELECT COUNT(*)
FROM changed;
```

Truy vấn ngoài cùng là SELECT, nhưng **CTE bên trong có UPDATE**. Khi chạy thật, `UPDATE` thực sự được thực hiện.

### 16.1. EXPLAIN ANALYZE với data-modifying CTE

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
WITH changed AS (
    UPDATE explain_lab.orders
    SET archived = TRUE
    WHERE order_id = 100
    RETURNING order_id
)
SELECT COUNT(*) AS affected
FROM changed;

SELECT order_id, archived
FROM explain_lab.orders
WHERE order_id = 100;

ROLLBACK;
```

Trong transaction thử nghiệm, `archived` đã bị chuyển thành TRUE. `ROLLBACK` hoàn tác thay đổi transactional của bảng.

### 16.2. Data-modifying CTE không phải “không làm gì nếu SELECT không đọc đủ”

Các statement sửa dữ liệu trong `WITH` có ngữ nghĩa thực thi riêng. Không dựa vào `LIMIT 0` hoặc việc SELECT ngoài cùng không lấy hết dữ liệu để kết luận phần UPDATE/DELETE sẽ chắc chắn không xảy ra.

Muốn tránh thay đổi khi đo, **không dùng `EXPLAIN ANALYZE` trên statement chứa DML**.

### 16.3. RETURNING không phải cơ chế dry-run

`RETURNING` hiển thị giá trị hàng được ghi, nhưng hành động ghi vẫn xảy ra:

```sql
UPDATE explain_lab.orders
SET archived = TRUE
WHERE order_id = 100
RETURNING order_id, archived;
```

Kết quả `RETURNING` giúp kiểm tra phạm vi thao tác, không biến câu SQL thành truy vấn đọc.

---

## 17. Trigger và foreign-key cascade: tác dụng phụ vượt khỏi bảng đích

Một câu `DELETE` có thể xóa hàng con do `ON DELETE CASCADE`, dù chỉ định một bảng đích.

### 17.1. Tạo bảng thử riêng

```sql
CREATE TABLE explain_lab.demo_parent (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE explain_lab.demo_child (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL
        REFERENCES explain_lab.demo_parent(id)
        ON DELETE CASCADE,
    note TEXT NOT NULL
);

INSERT INTO explain_lab.demo_parent(id, label)
VALUES (1, 'Parent for EXPLAIN lab');

INSERT INTO explain_lab.demo_child(id, parent_id, note)
VALUES
    (10, 1, 'Child A'),
    (11, 1, 'Child B');
```

### 17.2. EXPLAIN không ANALYZE cho DELETE

```sql
EXPLAIN
DELETE FROM explain_lab.demo_parent
WHERE id = 1;
```

Lệnh này không thực thi phép xóa trong trường hợp thông thường. Hai hàng `demo_child` vẫn còn.

### 17.3. EXPLAIN ANALYZE chạy cả cascade

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM explain_lab.demo_parent
WHERE id = 1;

SELECT COUNT(*) AS remaining_parent
FROM explain_lab.demo_parent;

SELECT COUNT(*) AS remaining_child
FROM explain_lab.demo_child;

ROLLBACK;
```

Trong transaction, `remaining_parent=0` và `remaining_child=0`. Đây là hai hàng con bị xóa qua cascade, không phải “kế hoạch trên giấy”.

Sau `ROLLBACK`, cả parent và children transactional được khôi phục.

### 17.4. Thông tin trigger trong EXPLAIN ANALYZE

Một số plan có thể hiển thị các dòng thời gian `Trigger for constraint ...` hoặc thông tin trigger khác. Đây là dấu hiệu chi phí thực thi không chỉ nằm ở các node scan/update của bảng đích.

Nhưng không mặc định `EXPLAIN` không ANALYZE sẽ ước lượng đầy đủ mọi chi phí trigger/cascade. Với DML phức tạp, đo trong môi trường an toàn và xem cả dependency.

### 17.5. Trigger dùng external side effects nguy hiểm hơn

Nếu bảng có trigger gọi HTTP hoặc phát thông báo qua hạ tầng ngoài database, `ROLLBACK` không đảm bảo thu hồi tác động đó. Trước khi thử `EXPLAIN ANALYZE DELETE` hoặc `UPDATE` trên một bảng thực:

1. Kiểm tra FK và `ON DELETE`.
2. Kiểm tra trigger và function được trigger gọi.
3. Xác định có gọi extension, queue ngoài, email hoặc hệ thống thanh toán không.
4. Dùng bản sao cô lập nếu không thể đảm bảo side effects được vô hiệu hóa an toàn.

Không tự tắt trigger/constraint trong production chỉ để đo nhanh: đó có thể làm phép đo sai và vi phạm tính toàn vẹn dữ liệu.

---

## 18. ROLLBACK không hoàn tác mọi thứ: bảng phân loại

| Tác động khi chạy EXPLAIN ANALYZE | Thường được ROLLBACK trong cùng transaction? | Lưu ý |
|---|---|---|
| `UPDATE` hàng trong bảng PostgreSQL | **Có** | Chưa commit, không có cơ chế ngoài transaction |
| `INSERT`/`DELETE` PostgreSQL | **Có** | Kể cả thay đổi transactional do trigger/FK cascade |
| Ghi vào bảng audit PostgreSQL bằng trigger trong cùng transaction | **Có** | Miễn thực sự nằm trong cùng transaction |
| `nextval()` trên sequence | **Không** | Số đã cấp không bị trả lại sau rollback |
| Gửi email qua hệ thống ngoài | **Không** | Email không tự thu hồi |
| HTTP POST đến dịch vụ khác | **Không tự động** | Cần idempotency/compensation theo hệ ngoài |
| Ghi file ngoài database | **Không tự động** | Không bị database transaction quản lý |
| Tạo WAL/áp lực I/O phục vụ transaction | **Không “thu hồi thời gian/tài nguyên”** | Rollback không xóa việc đã tiêu thụ tài nguyên |
| Thay đổi trong một hệ thống DB khác | **Không mặc định** | Cần giao thức phân tán riêng nếu có |
| Gửi thông báo bất đồng bộ ở hệ ngoài | **Không mặc định** | Có thể đã được gửi trước rollback |

### 18.1. Phân biệt “không còn hiệu lực” với “chưa từng chạy”

Sau rollback, một `UPDATE` transactional không còn được thấy là đã commit. Nhưng câu UPDATE **đã được executor thực hiện**, có thể:

- Gây chờ khóa.
- Tạo WAL và tuple versions sẽ cần dọn.
- Kích hoạt trigger.
- Tăng các bộ đếm/thống kê hoạt động.
- Tiêu thụ CPU, I/O và thời gian.

Do đó, `ROLLBACK` giúp khôi phục **ngữ nghĩa dữ liệu transactional**, chứ không quay ngược thời gian hoặc mọi hành vi bên ngoài.

### 18.2. Database clone là ranh giới an toàn hơn cho benchmark

Nếu muốn đo một câu `DELETE` xóa hàng triệu record và có trigger phức tạp, cách an toàn hơn thường là:

- Tạo database clone/staging từ dữ liệu đã được ẩn danh theo chính sách.
- Vô hiệu hóa một cách có thiết kế các tích hợp gửi email/thu tiền bên ngoài.
- Kiểm tra quyền và địa chỉ dịch vụ.
- Đo `EXPLAIN ANALYZE` tại đó.
- Đối chiếu plan với production bằng `EXPLAIN` không ANALYZE và các thống kê có sẵn.

Clone cần tương đồng về schema, index, thống kê, phân bố dữ liệu, config và phần cứng để phép đo có ý nghĩa; không mặc định staging nhỏ giống production.

---

## 19. WAL, thời gian thực thi và chi phí của câu lệnh ghi

### 19.1. WAL dùng để làm gì?

PostgreSQL ghi **Write-Ahead Log** cho nhiều thay đổi liên quan đến dữ liệu và phục hồi. Một `UPDATE` hoặc `DELETE` có thể tạo WAL, ảnh hưởng replication và tốc độ checkpoint.

Khi muốn quan sát:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE explain_lab.orders
SET archived = TRUE
WHERE order_id BETWEEN 100 AND 200;

ROLLBACK;
```

Phần `WAL` trong plan có thể cho biết số WAL records, full-page images và bytes tùy phiên bản/hoàn cảnh.

### 19.2. Tại sao rollback không “xóa WAL đã phát sinh”?

Transaction cần ghi log đủ để bảo vệ tính nhất quán, và rollback cũng có thể phát sinh công việc dọn dẹp/trạng thái liên quan. Những tài nguyên và log đã ghi không tự biến mất chỉ vì kết quả bảng quay về trước transaction.

Do vậy **benchmark DML bằng rollback vẫn tạo tải thật**. Nếu workload đang nhạy cảm với replica lag, autovacuum, disk I/O hoặc lock, cần môi trường riêng.

### 19.3. EXPLAIN không cung cấp ảnh chụp đầy đủ tác động hệ thống

Một plan `UPDATE` không thay cho:

- Theo dõi WAL generation và replication lag.
- Thống kê autovacuum.
- Lock wait/deadlock metrics.
- Kích thước heap và index bloat.
- Tác động đến cache của query khác.
- Thời gian commit/checkpoint/replication ở ngữ cảnh vận hành cụ thể.

EXPLAIN là một công cụ **chẩn đoán query plan**, không phải toàn bộ hệ thống quan sát.

---

## 20. Prepared statements: generic plan và custom plan

Một ứng dụng có thể gửi câu truy vấn tham số:

```sql
PREPARE lookup_orders(INTEGER, TEXT) AS
SELECT order_id, amount, created_at
FROM explain_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC
LIMIT 20;
```

### 20.1. Giải thích vấn đề

Kế hoạch tối ưu cho:

```text
tenant_id = 3
status = 'pending'
```

có thể khác plan tối ưu cho:

```text
tenant_id = 3
status = 'paid'
```

vì `pending` và `paid` có độ phổ biến rất khác nhau trong dữ liệu seed.

### 20.2. Custom plan

Khi PostgreSQL lập **custom plan**, giá trị parameter của lần thực thi có thể được xem xét trong planning.

```sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN EXECUTE lookup_orders(3, 'pending');
EXPLAIN EXECUTE lookup_orders(3, 'paid');
```

### 20.3. Generic plan

Generic plan phải hợp lệ cho những giá trị parameter khác nhau:

```sql
SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE lookup_orders(3, 'pending');
EXPLAIN EXECUTE lookup_orders(3, 'paid');
```

Kết thúc:

```sql
RESET plan_cache_mode;
DEALLOCATE lookup_orders;
```

`plan_cache_mode` hỗ trợ ba lựa chọn phổ biến `auto`, `force_custom_plan`, `force_generic_plan` trên các PostgreSQL hiện đại. `force_*` nên dùng để **chẩn đoán**, không thay đổi toàn ứng dụng một cách tùy tiện.

### 20.4. EXPLAIN EXECUTE và ANALYZE EXECUTE

`EXPLAIN EXECUTE lookup_orders(...)` xem plan đã chọn mà không chạy SELECT để trả dữ liệu. `EXPLAIN (ANALYZE) EXECUTE lookup_orders(...)` **thực thi prepared statement**.

Nếu prepared statement thực hiện DML hoặc gọi hàm có tác dụng phụ, thêm `ANALYZE` vẫn gây những tác động đã thảo luận. Việc query được chuẩn bị trước **không làm nó thành read-only**.

### 20.5. Không ép index trước khi hiểu plan cache

Nếu một truy vấn thi thoảng dùng index, thi thoảng Seq Scan, cần xác định:

- Nó có thật sự là cùng SQL/parameter value không?
- Generic hay custom plan?
- Thống kê đã thay đổi?
- Dữ liệu thay đổi mạnh?
- Query có `LIMIT`/`ORDER BY` khác?
- Session settings/role có khác?

Một plan khác không tự chứng minh planner hoạt động sai.

---

## 21. Query có JOIN và thống kê tương quan

Giả sử tenant và status có tương quan mạnh: tenant 1 phần lớn paid, tenant 2 phần lớn pending. Nếu planner chỉ có thống kê riêng từng cột, việc nhân xác suất độc lập có thể ước lượng sai.

### 21.1. Dấu hiệu trong EXPLAIN ANALYZE

```text
Index Scan ...
  (cost=... rows=20 ...)
  (actual ... rows=4000 ...)
```

Sai lệch lớn có thể ảnh hưởng tới việc chọn Nested Loop hay Hash Join.

### 21.2. Cập nhật thống kê cơ bản

```sql
ANALYZE explain_lab.orders;
```

Nếu thống kê cũ là nguyên nhân, cập nhật thống kê có thể cải thiện ước lượng.

### 21.3. Extended statistics

Với trường hợp nhiều cột phụ thuộc/có tương quan:

```sql
CREATE STATISTICS orders_tenant_status_stats
    (dependencies, mcv)
ON tenant_id, status
FROM explain_lab.orders;

ANALYZE explain_lab.orders;
```

PostgreSQL có thể dùng extended statistics như functional dependencies hoặc multivariate most-common-values cho một số loại ước lượng. **Không** bảo đảm mọi JOIN, mọi biểu thức và mọi truy vấn đều được cải thiện nhờ statistics object.

### 21.4. Vì sao không lấy actual rows làm số hàng cố định?

`actual rows` là kết quả tại thời điểm statement chạy với snapshot/parameter lúc ấy. Trong hệ thống có ghi đồng thời, lượng dữ liệu và phân bố có thể thay đổi. Planner cần ước lượng cho những lần thực thi tiếp theo, không thể “hardcode” actual rows của một lần đo.

---

## 22. Parallel Query, Gather và Gather Merge

PostgreSQL có thể chia một số công việc SELECT cho nhiều worker.

```text
Gather
  -> Parallel Seq Scan on orders
```

hoặc:

```text
Gather Merge
  -> Sort
      -> Parallel Seq Scan ...
```

### 22.1. Gather khác Gather Merge

- `Gather` gom các tuple từ workers; không tự bảo đảm thứ tự toàn cục của kết quả.
- `Gather Merge` hợp nhất các luồng **đã có thứ tự tương thích**, duy trì thứ tự yêu cầu ở đầu ra.

### 22.2. Số worker thực tế

Plan có thể hiển thị:

```text
Workers Planned: 2
Workers Launched: 1
```

Planner dự định dùng hai worker nhưng runtime chỉ khởi chạy một trong ví dụ. Nguyên nhân có thể liên quan cấu hình và tài nguyên hiện có; không mặc định planned bằng launched.

### 22.3. Loops và rows khi parallel

Trong plan parallel, số hàng và số lần node thực thi cần được diễn giải cùng thông tin workers. Không lấy trực tiếp `actual rows` của một worker làm tổng toàn hệ thống nếu plan đang phân phối công việc.

### 22.4. Parallel không phải luôn tốt

Với truy vấn nhỏ, chi phí tổ chức worker, trao đổi tuple và gom kết quả có thể lớn hơn lợi ích. PostgreSQL lựa chọn dựa vào chi phí; muốn hiểu plan cần đọc cả node chính và worker instrumentation.

---

## 23. CTE, Materialize và các node trung gian

### 23.1. CTE không mặc định luôn materialized

`WITH` giúp tổ chức query, nhưng PostgreSQL có thể inline/fold một số CTE chỉ đọc không volatile khi phù hợp. Các tùy chọn `MATERIALIZED` và `NOT MATERIALIZED` (PostgreSQL 12+) ảnh hưởng quyết định đó trong những trường hợp được phép.

```sql
EXPLAIN
WITH recent_paid AS (
    SELECT order_id, customer_id, amount
    FROM explain_lab.orders
    WHERE status = 'paid'
)
SELECT COUNT(*)
FROM recent_paid;
```

Không mặc định phải có node `CTE Scan` chỉ vì SQL dùng `WITH`.

### 23.2. Materialize node

Một node `Materialize` có thể cache kết quả trung gian để tái sử dụng khi node cha yêu cầu đọc lại. Nó không giống hệt một **materialized view** lưu dữ liệu bền vững trên database.

Đừng xóa CTE hoặc ép `NOT MATERIALIZED` chỉ vì thấy một node Materialize; cần hiểu lý do plan cần lặp/lưu dữ liệu và đo workload.

### 23.3. CTE có tác dụng phụ phải được nhìn khác

Như phần 16: CTE chứa `INSERT`/`UPDATE`/`DELETE` không chỉ là cấu trúc tổ chức SELECT. Khi bật `EXPLAIN ANALYZE`, statement sửa dữ liệu trong CTE **được thực thi** theo ngữ nghĩa PostgreSQL.

---

## 24. Có thể dùng EXPLAIN cho query trên production như thế nào?

Không có một quy tắc “tất cả EXPLAIN đều an toàn” hay “tất cả EXPLAIN đều nguy hiểm” áp dụng trong mọi hoàn cảnh.

### 24.1. Nhóm A — Lập kế hoạch không thực thi DML

Ví dụ:

```sql
EXPLAIN
DELETE FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'cancelled';
```

Là cách thích hợp để **xem kế hoạch ước lượng**, không thực thi DELETE theo cơ chế bình thường. Dù vậy, query parsing/planning vẫn dùng tài nguyên và lock thích hợp cho việc truy cập metadata; không coi hoạt động lập kế hoạch là “không tốn gì”.

### 24.2. Nhóm B — SELECT chỉ đọc thông thường

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM explain_lab.orders
WHERE order_id BETWEEN 100 AND 200;
```

Câu này thực thi SELECT, nhưng không chứa side effect rõ ràng. Có thể dùng có kiểm soát để đo, với lưu ý:

- SELECT có thể gây tải CPU/I/O.
- Có thể chờ locks hoặc tài nguyên.
- Với query nặng, vẫn ảnh hưởng workload khác.
- Cần xác nhận không gọi hàm tác dụng phụ và không có data-modifying CTE.

### 24.3. Nhóm C — DML hoặc SELECT có side effects

```sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE explain_lab.orders
SET archived = TRUE
WHERE tenant_id = 3;
```

Đây là **thực thi ghi**. Với production:

- Ưu tiên `EXPLAIN` không `ANALYZE` nếu chỉ cần biết kế hoạch.
- Muốn đo thật, dùng staging/clone được kiểm soát.
- Nếu bắt buộc thử trong transaction trên môi trường có dữ liệu thật, cần phê duyệt, hiểu mọi trigger/side effect và kế hoạch rollback/khôi phục.
- Không bỏ qua nguy cơ từ sequence, hệ thống ngoài và tài nguyên đã tiêu thụ.

### 24.4. Nhóm D — SQL động và hàm/extension không rõ

Nếu query gọi hàm tùy biến hoặc extension có tác dụng bên ngoài:

```sql
SELECT my_unknown_function(...);
```

chưa được kiểm tra, đừng tùy tiện bật `ANALYZE`. Với hàm khai báo volatility sai hoặc mã đặc biệt, ngay cả planning cũng có thể có hệ quả không hiển nhiên. Cần hiểu function definition và quyền trước.

---

## 25. Các kỹ thuật benchmark có trách nhiệm

### 25.1. Chọn truy vấn đại diện

Một plan của:

```sql
WHERE tenant_id = 1 AND status = 'paid'
```

không chắc đại diện cho:

```sql
WHERE tenant_id = 9 AND status = 'pending'
```

Độ chọn lọc, phân bố và loại dữ liệu khác nhau có thể dẫn đến plan khác. Cần lấy mẫu parameter values thường gặp và trường hợp xấu.

### 25.2. Kiểm soát snapshot, transaction và đồng thời

Đo khi bảng đang có job bulk insert/delete có thể tạo sai lệch lớn so với một lúc yên tĩnh. Nếu mục tiêu là hiệu năng thực tế giờ cao điểm, cần đo trong điều kiện đại diện, nhưng bảo đảm không gây hại.

Không giữ transaction benchmark lâu sau khi đo; nó có thể giữ snapshot/locks và ảnh hưởng VACUUM hoặc các writer khác.

### 25.3. Không bật/tắt cấu hình planner trong production tùy tiện

```sql
-- Chỉ minh họa kiểm tra plan trong session riêng:
SET enable_seqscan = off;
```

Ép tắt Seq Scan có thể hữu ích để hỏi “nếu chọn index thì plan thế nào?”, nhưng:

- Nó không làm index thiếu biến thành index tồn tại.
- Nó chỉ tăng bất lợi chi phí của một lựa chọn, không bảo đảm tuyệt đối không có Seq Scan.
- Plan bị ép không chứng minh index nên được dùng trong workload thật.
- Cần `RESET enable_seqscan;` và không áp cấu hình thử nghiệm cho toàn ứng dụng.

### 25.4. SET LOCAL để giới hạn cấu hình thử trong transaction

```sql
BEGIN;

SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT status, COUNT(*)
FROM explain_lab.orders
GROUP BY status;

ROLLBACK;
```

`SET LOCAL` hữu ích để giới hạn một thay đổi setting cho transaction hiện tại trong bối cảnh tương ứng. Nhưng **ROLLBACK không hoàn tác external side effects của statement**. Mẫu này chỉ dùng SELECT thường không có side effects.

### 25.5. Dùng LIMIT đúng ngữ nghĩa

`LIMIT 10` có thể làm plan và thời gian rất khác so với query không LIMIT. Nếu ứng dụng thật cần toàn bộ 100.000 hàng, benchmark bằng `LIMIT 10` không đại diện.

Ngược lại, với API pagination lấy 20 hàng đã sắp, index hỗ trợ ORDER BY + LIMIT là hướng tối ưu quan trọng.

### 25.6. Không đánh tráo dữ liệu bằng một bảng giả quá nhỏ

Trên bảng 10 hàng, PostgreSQL chọn Seq Scan rất hợp lý; điều đó không nói rằng nó sẽ chọn Seq Scan cho bảng 10 triệu hàng.

Lab có 100.000 orders nhằm tạo đủ đa dạng để xem các plan, nhưng hiệu năng production còn phụ thuộc phần cứng, dữ liệu thật, concurrency, cache và statistics.

---

## 26. Quan sát query chậm ngoài EXPLAIN

### 26.1. pg_stat_activity

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Giúp nhận ra session đang chạy, idle in transaction hoặc chờ điều gì đó. Quyền nhìn thông tin phiên khác phụ thuộc role và cấu hình monitoring.

### 26.2. pg_stat_statements

Extension `pg_stat_statements` (nếu đã được cài và cấu hình phù hợp) cung cấp thống kê tích lũy theo query fingerprint, ví dụ thời gian, số lần gọi, số row và buffer activity.

Không tự cho rằng view này luôn có; hệ thống phải bật extension và các tham số cần thiết. Nó giúp **chọn query nào cần EXPLAIN**, nhưng không thay plan thực tế với parameter cụ thể.

### 26.3. auto_explain

Module `auto_explain` có thể ghi kế hoạch của những truy vấn chậm vào server log theo thiết lập, có tùy chọn đo runtime.

Các lưu ý:

- Phải được cấu hình và cho phép theo quy trình vận hành.
- Ghi plan/log dày đặc tạo overhead, có thể chứa thông tin nhạy cảm.
- Không bật `log_analyze` và `log_buffers` tràn lan mà không cân nhắc chi phí.
- Dùng nó để quan sát query thực tế khó tái tạo, không coi log tự động là kết quả QA đầy đủ.

### 26.4. pg_stat_user_tables và thống kê autovacuum

```sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'explain_lab'
ORDER BY relname;
```

Các giá trị là thống kê tích lũy/ước lượng, không nên xem là ảnh chụp chính xác tuyệt đối của mọi truy vấn hay mọi tuple tại từng thời điểm.

---

## 27. Quy trình điều tra một query chậm

Một quy trình thực tế:

### Bước 1 — Xác định câu SQL và ngữ cảnh

Ghi lại:

- SQL thật (hoặc template) và các giá trị tham số đã được bảo vệ dữ liệu nhạy cảm.
- PostgreSQL version và database.
- Thời điểm chậm, số lần lặp, concurrency.
- Isolation level, role/RLS nếu liên quan.
- Mục tiêu latency và số hàng trả về dự kiến.

### Bước 2 — Xác định câu lệnh có side effects không

- `SELECT` chỉ đọc thuần?
- Có gọi `nextval()`?
- Có volatile function, gọi HTTP/email hoặc data-modifying CTE?
- Là `UPDATE`/`DELETE`/`INSERT`/`MERGE`?
- Có trigger/FK cascade?

Nếu có side effects, **không bật `ANALYZE` trên production** chỉ để đo.

### Bước 3 — EXPLAIN trước

```sql
EXPLAIN (VERBOSE, SETTINGS)
SELECT ...;
```

Hiểu plan dự kiến trước khi quyết định có thể/đáng đo thực.

### Bước 4 — Chỉ ANALYZE nếu an toàn

Trên SELECT thuần hoặc bản sao cô lập:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT ...;
```

Ghi nhận số hàng, loops, buffers, total execution và dấu hiệu temp I/O.

### Bước 5 — Tìm node sai lệch hoặc tốn tài nguyên

Ví dụ:

- Estimated rows 10, actual rows 100.000.
- Nested Loop inner index probe chạy hàng trăm nghìn loops.
- Sort external với temp I/O cao.
- Seq Scan đọc gần toàn bảng trong khi query chỉ cần 0,01%.
- Index Scan phải fetch nhiều heap tuples vì projection hoặc selectivity.
- Hash Join chia nhiều batches do bộ nhớ.

Không tối ưu chỉ bằng tên node; đọc nguyên cây.

### Bước 6 — Đưa ra giả thuyết có thể kiểm chứng

Các hướng:

- Index phù hợp hơn với bộ lọc + ORDER BY.
- Viết lại query để lọc sớm/hạn chế fanout.
- Thu thập thống kê mới hoặc extended statistics.
- Giảm số cột trả về.
- Xem prepared statement generic/custom plan.
- Tối ưu khóa/transaction khi vấn đề thực tế là waiting.
- Cân nhắc partitioning khi dữ liệu và vòng đời phù hợp.

### Bước 7 — Đo lại và kiểm tra tác dụng phụ của tối ưu

Sau mỗi thay đổi:

- So sánh cùng workload.
- Đo nhiều lần.
- Xem chi phí ghi/index maintenance.
- Kiểm tra tính đúng đắn của kết quả.
- Theo dõi ảnh hưởng đến query khác.
- Có rollback plan cho migration/index/config.

---

## 28. Lỗi phổ biến khi đọc và sử dụng EXPLAIN

**1. “EXPLAIN và EXPLAIN ANALYZE đều chỉ xem trước.”** Sai. `EXPLAIN ANALYZE` thực thi statement.

**2. “EXPLAIN ANALYZE UPDATE không sửa dữ liệu vì chỉ trả plan.”** Sai. UPDATE được chạy thật.

**3. “EXPLAIN ANALYZE DELETE an toàn trên production nếu chạy ngoài transaction.”** Sai. Ở autocommit, thao tác có thể được commit ngay.

**4. “BEGIN ... ROLLBACK hoàn tác mọi hiệu ứng trên thế giới.”** Sai. Sequence, email, HTTP và I/O ngoài PostgreSQL không tự rollback.

**5. “nextval() rollback trả lại số.”** Sai. Sequence có thể có khoảng trống.

**6. “SELECT chắc chắn không có side effects.”** Sai nếu gọi volatile function, sequence hoặc data-modifying CTE.

**7. “RETURNING hoặc WITH làm DML chỉ là truy vấn đọc.”** Sai. DML vẫn được thực thi khi ANALYZE.

**8. “EXPLAIN không ANALYZE có nghĩa là hệ thống không tốn tài nguyên gì.”** Không. Planning vẫn có chi phí, cần metadata và có thể tương tác với mã tùy biến.

**9. “Cost 100 nghĩa là 100 milliseconds.”** Sai. Cost là đơn vị planner tương đối.

**10. “Rows 1000 trong EXPLAIN là số hàng thực tế.”** Sai. Đó là ước lượng.

**11. “Actual rows 1 loops 10000 nghĩa là chỉ có một hàng tổng cộng.”** Sai. Cần nhân/diễn giải theo số lần node chạy.

**12. “Cộng actual time của mọi node cho ra Execution Time.”** Sai. Chi phí node cha có thể bao gồm con và loops.

**13. “Seq Scan luôn xấu.”** Không. Khi cần đọc phần lớn bảng, Seq Scan có thể tốt.

**14. “Index Scan luôn nhanh hơn Seq Scan.”** Không. Random I/O, selectivity và heap fetch có thể làm index đắt.

**15. “Index Only Scan tuyệt đối không cần heap.”** Sai. Cần visibility checks và có thể có Heap Fetches.

**16. “Shared read chắc chắn là đọc trực tiếp từ ổ đĩa vật lý.”** Không. OS cache có thể đáp ứng.

**17. “Shared hit là không tốn CPU.”** Sai. Truy cập tuple vẫn có chi phí.

**18. “Buffers ở từng node có thể cộng thẳng để ra tổng.”** Sai vì có thể cộng dồn qua node.

**19. “Sort external chỉ cần tăng work_mem vô hạn.”** Sai. RAM được dùng bởi nhiều node/query/session; cần cân nhắc toàn hệ thống.

**20. “Nested Loop là sai trong mọi trường hợp.”** Không. Nó tốt khi outer nhỏ và inner lookup hiệu quả.

**21. “Một query được benchmark nhanh trên bảng 10 dòng sẽ nhanh trên 10 triệu dòng.”** Không đủ căn cứ.

**22. “Thêm index lúc nào cũng tốt cho mọi workload.”** Sai. Index tốn disk/WAL/ghi và có thể ảnh hưởng HOT updates.

**23. “ANALYZE table và EXPLAIN ANALYZE là cùng việc.”** Sai. Một cái cập nhật thống kê; một cái thực thi để đo plan.

**24. “EXPLAIN ANALYZE chỉ đo database CPU thuần, không có overhead.”** Sai. Instrumentation có overhead; còn I/O và nhiều yếu tố khác.

**25. “TIMING OFF làm query không chạy.”** Sai. Nó chỉ giảm việc đo thời gian từng node.

**26. “Không thấy Index Cond trên WHERE nghĩa là query không dùng filter.”** Không. Filter và Index Cond có vai trò khác nhau.

**27. “Planner luôn ước lượng đúng mọi tương quan nhiều cột.”** Sai. Có thể cần extended statistics hoặc viết lại query.

**28. “Prepared statement luôn dùng một plan duy nhất giống mọi tham số.”** Không. Có generic/custom plan và lựa chọn theo chi phí.

**29. “Có LIMIT thì query không cần xử lý nhiều dữ liệu.”** Không luôn. ORDER BY/aggregate trước LIMIT có thể vẫn phải đọc/sort lượng lớn.

**30. “Tạo index mới rồi một lần đo nhanh hơn là đủ chứng minh.”** Không. Cache, dữ liệu, workload và nhiều yếu tố cần kiểm soát.

**31. “EXPLAIN ANALYZE trên clone giống hệt production.”** Chưa chắc. Statistics, dữ liệu, config và tài nguyên có thể khác.

**32. “EXPLAIN không có ANALYZE luôn gọi mọi hàm trong SQL để tính kết quả.”** Không. Nó lập plan; nhưng không nên tin tưởng mù quáng mọi hàm/extension không rõ tác dụng trong planning.

**33. “DML rollback không tạo WAL hoặc dead tuples.”** Sai. Thao tác đã chạy, rollback không xóa mọi chi phí đã phát sinh.

**34. “Có trigger thì EXPLAIN không ANALYZE đã đo đầy đủ chi phí trigger.”** Không. Trigger chạy khi statement thực sự thực thi.

**35. “Một lần EXPLAIN ANALYZE SELECT chứng minh API end-to-end nhanh.”** Không. Networking, serialization, driver và ứng dụng còn chi phí.

**36. “pg_stat_statements thay được EXPLAIN.”** Không. Nó đo workload tích lũy, không cho cây plan giống EXPLAIN trong mọi điều kiện.

**37. “Parallel workers planned luôn bằng launched.”** Không. Tài nguyên thực tế có thể giới hạn.

**38. “EXPLAIN dưới một role giống hệt dưới role khác có RLS.”** Không đảm bảo. Role, policies và settings có thể ảnh hưởng đường truy cập.

**39. “Có nhiều temp reads thì cứ tăng RAM server là đủ.”** Không. Có thể cần sửa query, giảm JOIN fanout hoặc thêm index.

**40. “Không có Index Scan nghĩa là query chắc chắn sai.”** Không. Correctness của SQL khác với lựa chọn execution plan.

---

## 29. Bài tập thực hành có đáp án

### Bài 1 — Phân biệt hai lệnh

**Câu hỏi:** `EXPLAIN DELETE FROM orders WHERE id=1` và `EXPLAIN ANALYZE DELETE ...` khác nhau điều gì?

**Đáp án:** `EXPLAIN` không ANALYZE lập kế hoạch, thường không thực thi DELETE. `EXPLAIN ANALYZE` **chạy DELETE** rồi hiển thị thông tin thực tế.

### Bài 2 — Đọc cost

Plan:

```text
Index Scan (cost=0.43..8.45 rows=1 width=32)
```

**Đáp án:** Startup cost 0.43, total cost 8.45 theo đơn vị ước lượng của planner; dự kiến một hàng, mỗi hàng rộng 32 bytes. **Không** suy ra thời gian 8.45 ms.

### Bài 3 — Đọc loops

Plan:

```text
Index Scan (actual time=0.003..0.004 rows=1 loops=5000)
```

**Đáp án:** Node được gọi 5.000 lần, trung bình một hàng mỗi lần; tổng số hàng trả qua node khoảng 5.000. Không chỉ một hàng tổng cộng.

### Bài 4 — Giải thích Seq Scan

Query đọc 90% hàng trong bảng. Planner chọn Seq Scan.

**Đáp án:** Có thể hợp lý. Quét bảng tuần tự có thể rẻ hơn truy cập index rồi fetch phần lớn heap. Cần đo thực tế, không gán nhãn lỗi.

### Bài 5 — Index Cond và Filter

Plan có:

```text
Index Cond: (tenant_id = 2)
Filter: (amount > 100)
```

**Đáp án:** Index dùng điều kiện tenant để xác định vị trí truy cập; sau khi lấy hàng, filter loại các hàng không đạt amount. Cân nhắc index nếu workload cho thấy việc lọc sau quá tốn.

### Bài 6 — Đo query lấy ít đơn

**Yêu cầu:** xem plan thực và buffers cho đơn ID 100.

**Đáp án:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM explain_lab.orders
WHERE order_id = 100;
```

Đây là SELECT đọc thuần trên bảng lab.

### Bài 7 — So sánh trước/sau index

**Yêu cầu:** đề xuất index cho query lọc tenant/status, sort theo created_at DESC.

**Đáp án:**

```sql
CREATE INDEX orders_tenant_status_created_idx_ex
ON explain_lab.orders (tenant_id, status, created_at DESC);
```

Bảng lab đã có index `orders_tenant_status_created_idx` tương tự trong bài; index mới chỉ minh họa cú pháp. Trên production không giữ hai index trùng lặp nếu không có lợi ích riêng.

### Bài 8 — Vì sao BUFFERS hữu ích?

**Đáp án:** Cho biết thao tác với shared/local/temp buffers, giúp phân biệt query dùng cache, đọc nhiều trang hoặc Sort/Hash tràn temp. Không trực tiếp đồng nhất shared read với I/O đĩa vật lý.

### Bài 9 — Đọc Sort spill

Plan ghi:

```text
Sort Method: external merge Disk: 20480kB
Buffers: temp read=... written=...
```

**Đáp án:** Sort đã phải dùng dữ liệu tạm trên disk. Điều tra số hàng cần sort, index/ORDER BY, fanout và work_mem; không mặc định tăng work_mem toàn server.

### Bài 10 — Hash Join vs Nested Loop

**Câu hỏi:** Nested Loop inner index lookup có `loops=100000`. Điều gì đáng điều tra?

**Đáp án:** Số lượt inner lookup rất lớn, có thể tốn I/O/CPU. Xem cardinality, selectivity, join order, index và khả năng planner ước lượng sai. Không kết luận chỉ từ tên node.

### Bài 11 — WAL của UPDATE

**Yêu cầu:** thử đo WAL do UPDATE 101 đơn trong lab và rollback.

**Đáp án:**

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE explain_lab.orders
SET archived = TRUE
WHERE order_id BETWEEN 100 AND 200;

ROLLBACK;
```

Chỉ chạy ở lab. UPDATE chạy thật, rollback hoàn tác bảng nhưng **không thu hồi chi phí WAL/I/O**.

### Bài 12 — Sequence và ROLLBACK

**Câu hỏi:** Tại sao `EXPLAIN ANALYZE SELECT nextval('explain_lab.test_seq')` nguy hiểm nếu chỉ định “xem plan”?

**Đáp án:** SELECT được thực thi, `nextval()` cấp số thật và **không rollback** số đã cấp. Sequence có thể tăng dù transaction thử nghiệm bị rollback.

### Bài 13 — SELECT gọi side effect

**Câu hỏi:** SELECT gọi hàm gửi email có an toàn khi bọc trong BEGIN/ROLLBACK không?

**Đáp án:** Không. Email là tác động ngoài PostgreSQL nên không được rollback tự động. Chỉ đo trên môi trường/hàm giả lập hoặc xác nhận không có external side effect.

### Bài 14 — Data-modifying CTE

**Câu hỏi:** `EXPLAIN ANALYZE WITH changed AS (UPDATE ... RETURNING ...) SELECT ...` có thay đổi bảng không?

**Đáp án:** Có. UPDATE trong CTE được thực thi theo ngữ nghĩa statement, dù truy vấn ngoài là SELECT.

### Bài 15 — Cascade

**Câu hỏi:** Xóa parent có 2 child với FK `ON DELETE CASCADE`. `EXPLAIN ANALYZE DELETE parent` có ảnh hưởng child không?

**Đáp án:** Có. Nếu DELETE chạy thành công, hai child bị cascade. `ROLLBACK` trong cùng transaction sẽ hoàn tác các thay đổi transactional của parent/child.

### Bài 16 — An toàn xem kế hoạch DELETE

**Yêu cầu:** chỉ xem kế hoạch xóa đơn cancelled của tenant 3, không xóa dữ liệu.

**Đáp án:**

```sql
EXPLAIN
DELETE FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'cancelled';
```

Không thêm `ANALYZE` nếu không được phép thực thi.

### Bài 17 — Format JSON

**Yêu cầu:** lấy plan dạng JSON cho SELECT theo order_id.

**Đáp án:**

```sql
EXPLAIN (FORMAT JSON)
SELECT order_id
FROM explain_lab.orders
WHERE order_id = 100;
```

Kết quả là cấu trúc JSON của plan, không phải JSON hàng dữ liệu order.

### Bài 18 — Timing OFF

**Câu hỏi:** `EXPLAIN (ANALYZE, TIMING OFF)` có làm query dừng thực thi không?

**Đáp án:** Không. Nó chỉ tắt việc đo thời gian chi tiết từng node; query vẫn được chạy.

### Bài 19 — Rows estimate lệch nhiều

Plan ước lượng 20 hàng nhưng thực tế 20.000.

**Đáp án:** Điều tra statistics, dữ liệu lệch, correlation, parameter/plan cache và cấu trúc query. Sai lệch lớn có thể làm planner chọn join/sort không phù hợp.

### Bài 20 — Generic và custom plan

**Yêu cầu:** mô tả cách quan sát khác biệt plan của một prepared statement.

**Đáp án:** Dùng `SET plan_cache_mode=force_custom_plan` và `EXPLAIN EXECUTE ...`, rồi `force_generic_plan` và EXPLAIN cùng tham số. `RESET` sau khi đo. Không ép settings lâu dài thiếu căn cứ.

### Bài 21 — Plan vs API latency

**Câu hỏi:** EXPLAIN ANALYZE báo 5 ms nhưng API trả 600 ms. Có chắc database không liên quan?

**Đáp án:** Không đủ để kết luận. Có thể còn network transfer, connection pool wait, transaction/lock khác, thời gian serialize/deserialize và tham số/plan khác giữa app với phép đo.

### Bài 22 — EXPLAIN ANALYZE trên production?

**Câu hỏi:** Có thể chạy `EXPLAIN (ANALYZE) DELETE ...` trên production nếu sau đó rollback không?

**Đáp án:** Không mặc định an toàn. Lệnh xóa vẫn chạy, có thể gây lock/WAL/trigger/sequence/external side effect. Ưu tiên EXPLAIN không ANALYZE hoặc clone an toàn; chỉ dùng transaction thử nghiệm khi đã kiểm soát mọi hệ quả và được cho phép.

### Bài 23 — Đo COUNT(*)

**Câu hỏi:** Root Aggregate trả actual rows=1, có nghĩa toàn query chỉ đọc một hàng không?

**Đáp án:** Không. Node Aggregate có thể tiêu thụ hàng triệu hàng từ node con để tính COUNT(*), rồi trả một hàng kết quả. Xem toàn cây.

### Bài 24 — Nhìn kế hoạch Parallel

```text
Workers Planned: 4
Workers Launched: 2
```

**Đáp án:** Planner dự kiến bốn workers nhưng runtime chỉ khởi chạy hai. Cần phân tích tài nguyên/settings và số hàng worker xử lý, không mặc định số planned = launched.

### Bài 25 — Lập checklist runbook đo DML

**Đáp án gợi ý:** Xác nhận môi trường, đối tượng thay đổi, FK/trigger/function, external side effects, sequence, transaction scope, replica/WAL, quyền/approval, phương án rollback và hậu kiểm; nếu không kiểm soát được, chỉ dùng `EXPLAIN` hoặc database clone.

### Bài 26 — Lỗi dùng EXPLAIN ANALYZE SELECT trên custom function

**Câu hỏi:** Nếu không biết function `do_work()` có gọi HTTP hay ghi file, có thể xem nó như SELECT thuần không?

**Đáp án:** Không. Cần đọc hợp đồng/implementation và xác định side effects trước. Chạy `EXPLAIN ANALYZE SELECT do_work()` sẽ thực thi hàm nếu nó nằm trên đường thực thi; `ROLLBACK` không hoàn tác external side effect.

---

## 30. Checklist trước khi dùng EXPLAIN trong dự án

1. **Đúng database/role:** xác nhận server, schema và quyền trước khi thử.
2. **Đúng statement:** SQL có thật sự giống câu application gửi không?
3. **Đúng tham số:** chạy mẫu tham số đại diện, nhất là tenant/status và range thời gian.
4. **Đúng mục tiêu:** chỉ cần estimated plan hay cần actual runtime?
5. **Có tác dụng phụ không:** DML, CTE ghi, volatile function, `nextval()`, trigger, HTTP, email?
6. **Nếu chỉ xem plan DML:** dùng `EXPLAIN`, không thêm `ANALYZE`.
7. **Nếu đo actual DML:** ưu tiên clone/staging cô lập và kiểm soát side effects.
8. **Nếu dùng transaction thử:** không ngộ nhận `ROLLBACK` hoàn tác sequence và hệ thống ngoài.
9. **Đã kiểm tra FK/trigger:** phạm vi tác động có vượt bảng được nhắc tên không?
10. **Có thể gây tải không:** CPU/I/O/WAL/locks/replication lag khi chạy thật?
11. **Đã cập nhật thống kê chưa:** `ANALYZE table` khi phù hợp, không nhầm với EXPLAIN ANALYZE.
12. **Đọc từ root và các child:** không nhìn một node rồi kết luận.
13. **Phân biệt cost và milliseconds:** cost là ước lượng tương đối, actual time là đo.
14. **Đọc rows cùng loops:** actual rows của node lặp cần tính theo loops.
15. **Đọc Index Cond/Filter:** query có tận dụng index hay lọc thêm quá nhiều?
16. **Đọc temp buffers:** sort/hash có spill không?
17. **Đọc shared hit/read đúng:** không đồng nhất read với đọc đĩa vật lý.
18. **Đọc Join/SORT/Aggregate:** nguyên nhân tốn tài nguyên nằm ở node nào?
19. **Xem generic/custom plan:** prepared statement có plan nhạy theo tham số?
20. **Kiểm soát độ biến thiên đo:** cache, concurrency và bộ dữ liệu.
21. **Không ép planner toàn hệ thống:** thí nghiệm settings phải được reset.
22. **Không tạo index chỉ từ một EXPLAIN:** xem chi phí ghi và workload tổng.
23. **Đo end-to-end khi cần:** network, connection pool, ORM, response encoding.
24. **Ghi nhận kết quả và thay đổi:** SQL, tham số, plan, phiên bản, thời điểm và phương án rollback.
25. **Không xem EXPLAIN là bảo vệ nghiệp vụ:** permission, RLS, constraint và concurrency control vẫn cần.

---

## 31. Tổng kết

**`EXPLAIN` giúp hiểu PostgreSQL dự định chạy một statement như thế nào; `EXPLAIN ANALYZE` thực sự chạy statement rồi báo số liệu thực tế.** Khác biệt này vừa là chìa khóa tối ưu hiệu năng vừa là một ranh giới an toàn dữ liệu.

Để đọc plan đúng:

- Bắt đầu từ **cây node**, không chỉ nhìn dòng trên cùng.
- Phân biệt **`cost`/`rows` ước lượng** với **`actual time`/`actual rows` thực tế**.
- Luôn xem **`loops`**, `Index Cond`, `Filter`, `Rows Removed by Filter`, `BUFFERS` và các dấu hiệu temp I/O.
- Hiểu rằng **Seq Scan không mặc nhiên xấu**; Nested Loop, Hash Join, Merge Join, Sort và Aggregate đều là lựa chọn có ngữ cảnh.
- Dùng thống kê, phân bố dữ liệu, index, join order, prepared-plan behavior và phép đo lặp để giải thích sự khác biệt.

Để sử dụng an toàn:

- **`EXPLAIN` không `ANALYZE`** là cách thích hợp khi chỉ cần xem plan của lệnh ghi.
- **`EXPLAIN ANALYZE INSERT/UPDATE/DELETE/MERGE` thực thi thay đổi thật**.
- **`EXPLAIN ANALYZE SELECT` cũng có thể có tác dụng phụ** nếu query gọi sequence, volatile function hoặc chứa data-modifying CTE.
- **`BEGIN ... ROLLBACK` không hoàn tác mọi thứ**: sequence, email, HTTP, external queue/file và chi phí tài nguyên đã phát sinh vẫn có thể để lại hậu quả.
- Khi cần đo DML lớn hoặc phụ thuộc bên ngoài, ưu tiên **môi trường thực hành/clone cô lập**, hiểu trigger/FK và kiểm soát transaction trước.

**Nguyên tắc cuối cùng:** trước khi gõ `ANALYZE` vào một lệnh `EXPLAIN`, hãy hỏi **“nếu toàn bộ statement này thực sự chạy ngay bây giờ, nó sẽ đọc, ghi, khóa, gọi hàm và gây tác dụng gì?”**. Nếu chưa trả lời được, chưa nên chạy `EXPLAIN ANALYZE` trên dữ liệu quan trọng.

### Tài liệu PostgreSQL chính thức

- [EXPLAIN — cú pháp và tùy chọn](https://www.postgresql.org/docs/current/sql-explain.html).
- [Using EXPLAIN — cách đọc execution plans](https://www.postgresql.org/docs/current/using-explain.html).
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html).
- [ANALYZE — cập nhật thống kê bảng](https://www.postgresql.org/docs/current/sql-analyze.html).
- [Sequences — Function nextval() và semantics](https://www.postgresql.org/docs/current/functions-sequence.html).
- [WITH Queries — Data-Modifying Statements](https://www.postgresql.org/docs/current/queries-with.html).
- [CREATE TRIGGER và foreign keys](https://www.postgresql.org/docs/current/sql-createtrigger.html).
- [Resource Consumption — work_mem](https://www.postgresql.org/docs/current/runtime-config-resource.html).
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
