# Viết lại truy vấn con, JOIN và EXISTS theo ngữ nghĩa trong PostgreSQL

## 1. Vì sao tối ưu SQL phải bắt đầu từ ngữ nghĩa?

Một câu SQL có thể chạy chậm vì thiếu index, thống kê chưa chính xác hoặc kế hoạch thực thi chưa phù hợp. Nhưng cũng có những truy vấn chậm vì **diễn đạt sai điều mà nghiệp vụ thực sự muốn hỏi**.

Ví dụ yêu cầu:

> Tìm những khách hàng **đã từng có ít nhất một đơn hàng PAID**.

Một lập trình viên có thể viết:

```sql
SELECT c.customer_id, c.email
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Nếu một khách hàng có ba đơn PAID, câu `JOIN` này sẽ trả **ba dòng cho cùng khách hàng**. Nhưng nghiệp vụ chỉ hỏi khách hàng đó **có tồn tại** đơn PAID hay không, không cần liệt kê từng đơn.

Một cách diễn đạt sát yêu cầu hơn:

```sql
SELECT c.customer_id, c.email
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Câu `EXISTS` hỏi đúng một điều: **có ít nhất một hàng khớp hay không?** Nó không nhân hàng khách hàng theo số đơn.

Đây là một nguyên tắc nền tảng của tối ưu truy vấn:

> **Viết lại truy vấn phải bảo toàn kết quả theo đúng ngữ nghĩa nghiệp vụ, trước khi tìm kế hoạch chạy nhanh hơn.**

Không được thay một truy vấn bằng biến thể nhanh hơn nhưng:

- Trả thêm hàng.
- Làm mất khách hàng chưa có đơn.
- Nhân số tiền khi join bảng một-nhiều.
- Đổi ý nghĩa của `NULL`.
- Đánh đồng “không có đơn” với “không có đơn PAID”.
- Chọn nhầm hàng khi lấy đơn mới nhất.
- Chuyển lọc trong `ON` ra `WHERE` và vô tình làm mất tính chất outer join.

Trong PostgreSQL, optimizer có thể tự biến đổi nhiều truy vấn con thành **semi join**, **anti join** hoặc các kiểu join khác. Nhưng khả năng tự tối ưu không có nghĩa **mọi cú pháp khác nhau là tương đương**.

### Mục tiêu của bài

Sau bài này, bạn có thể:

1. Phân biệt ngữ nghĩa **tồn tại**, **không tồn tại**, **ghép hàng** và **tổng hợp**.
2. Biết khi nào `EXISTS`, `IN`, `JOIN` và `NOT EXISTS` thực sự tương đương.
3. Giải thích tại sao SQL có **bag semantics** (cho phép hàng trùng) và hệ quả đối với `JOIN`.
4. Viết lại correlated subquery thành JOIN/aggregate khi việc viết lại giữ nguyên cardinality.
5. Tránh bẫy `NOT IN` khi truy vấn con chứa `NULL`.
6. Hiểu sự khác biệt giữa điều kiện lọc đặt trong `ON` và `WHERE` với `LEFT JOIN`.
7. Dùng `LATERAL`, `DISTINCT ON` và window function cho các yêu cầu “lấy một hàng trong mỗi nhóm”.
8. Hiểu giới hạn của optimizer khi biến đổi subquery và CTE.
9. Đọc `EXPLAIN (ANALYZE, BUFFERS)` để nhận biết semi join, anti join, nested loop, hash join và subplan.
10. Kiểm chứng hai truy vấn tương đương bằng dữ liệu mẫu, `EXCEPT ALL` và các ca NULL/trùng khóa.
11. Áp dụng quy trình tối ưu dựa trên **tính đúng → kế hoạch → đo lường → vận hành**.

---

## 2. Trước tiên phải xác định câu hỏi mà SQL cần trả lời

Trước khi thay `JOIN` bằng `EXISTS`, hãy phân loại yêu cầu.

| Câu hỏi nghiệp vụ | Ngữ nghĩa | Cách diễn đạt thường hợp lý |
|---|---|---|
| Khách hàng có đơn PAID không? | **Tồn tại ít nhất một** | `EXISTS` hoặc `IN` phù hợp |
| Khách hàng không có đơn PAID? | **Không tồn tại** | `NOT EXISTS` |
| Liệt kê từng đơn của khách hàng? | **Ghép quan hệ một-nhiều** | `INNER JOIN` |
| Liệt kê mọi khách, kể cả chưa có đơn? | **Giữ hàng bên trái** | `LEFT JOIN` |
| Đếm số đơn mỗi khách, kể cả bằng 0? | **Tổng hợp theo khách** | `LEFT JOIN + GROUP BY` hoặc correlated COUNT |
| Lấy thời điểm đơn mới nhất? | **Tổng hợp MAX** | Scalar subquery hoặc aggregate JOIN |
| Lấy **toàn bộ hàng** của đơn mới nhất? | **Top 1 trong mỗi nhóm** | `LEFT JOIN LATERAL`, `DISTINCT ON` hoặc `ROW_NUMBER` |
| Đơn có ít nhất một thanh toán thành công? | **Tồn tại quan hệ phụ** | `EXISTS` |
| Đơn chưa có thanh toán thành công? | **Phủ định tồn tại** | `NOT EXISTS` |

Một mẹo phân biệt quan trọng:

- Câu hỏi **“có hay không?”** thường là phép **semi join**.
- Câu hỏi **“không có?”** thường là phép **anti join**.
- Câu hỏi **“cho tôi các cặp hàng khớp”** là join thông thường.
- Câu hỏi **“bao nhiêu, tổng, lớn nhất?”** là aggregate.
- Câu hỏi **“hàng nào đứng đầu mỗi nhóm?”** đòi chọn hàng có thứ tự rõ ràng.

Chọn đúng loại quan hệ ngay từ đầu thường hiệu quả hơn việc viết một JOIN quá rộng rồi dùng `DISTINCT` để vá số dòng.

## 3. SQL dùng bag semantics: JOIN có thể làm nhân hàng

Trong toán học tập hợp, một phần tử thường chỉ xuất hiện một lần. Nhưng kết quả truy vấn SQL thông thường là **multiset/bag**: có thể chứa nhiều hàng giống nhau.

Ví dụ quan hệ:

```text
customers:
  customer_id=1, email=an@example.test

orders:
  order_id=101, customer_id=1, status=PAID
  order_id=102, customer_id=1, status=PAID
```

JOIN:

```sql
SELECT c.customer_id, c.email
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

trả:

```text
1 | an@example.test
1 | an@example.test
```

Hai dòng có cùng giá trị cột SELECT vì chúng tương ứng với **hai cặp hàng match** khác nhau trong phép join.

Trong khi đó:

```sql
SELECT c.customer_id, c.email
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

chỉ trả:

```text
1 | an@example.test
```

**Sự khác biệt cardinality này là khác biệt ngữ nghĩa**, không chỉ là khác biệt hiệu năng.

### 3.1. JOIN tạo ra quan hệ hàng, EXISTS kiểm tra membership

`JOIN`:

```text
Mỗi hàng bên trái × tất cả hàng bên phải khớp điều kiện.
```

`EXISTS`:

```text
Mỗi hàng bên trái được giữ hoặc loại dựa vào
việc có ÍT NHẤT MỘT hàng bên phải khớp hay không.
```

Với trường hợp bên phải có nhiều hàng match, JOIN có thể tăng số dòng nhưng EXISTS không nhân bản dòng từ bên trái.

### 3.2. Vì sao lỗi nhân hàng đặc biệt nguy hiểm với SUM?

Giả sử mỗi order có nhiều order_items và nhiều payment attempts. Nếu join cả hai quan hệ một-nhiều:

```sql
SELECT ...
FROM orders o
JOIN order_items i ON i.order_id = o.order_id
JOIN payments p ON p.order_id = o.order_id;
```

một đơn có hai items và ba payments có thể tạo **2 × 3 = 6 hàng**. Nếu cộng `i.quantity * i.unit_price` trên kết quả này, tiền hàng có thể bị tính ba lần.

Do vậy, phải xác định **grain** của dữ liệu: “mỗi hàng kết quả đại diện cho một khách hàng, một đơn, một item hay một thanh toán?”

## 4. Dữ liệu thực hành có các trường hợp trùng và NULL

Các ví dụ tiếp theo dùng schema `rewrite283` trong một database PostgreSQL thử nghiệm. Không chạy trên dữ liệu production.

### 4.1. Tạo schema và bảng khách hàng

```sql
CREATE SCHEMA IF NOT EXISTS rewrite283;

CREATE TABLE rewrite283.customers (
    customer_id integer PRIMARY KEY,
    email text NOT NULL UNIQUE,
    segment text NOT NULL
        CHECK (segment IN ('VIP', 'STANDARD'))
);
```

### 4.2. Bảng đơn hàng

```sql
CREATE TABLE rewrite283.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES rewrite283.customers(customer_id),
    ordered_at date NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
```

### 4.3. Chi tiết đơn và lần thanh toán

```sql
CREATE TABLE rewrite283.order_items (
    order_id integer NOT NULL
        REFERENCES rewrite283.orders(order_id),
    line_no integer NOT NULL,
    product_id integer NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE rewrite283.payments (
    payment_id integer PRIMARY KEY,
    order_id integer NOT NULL
        REFERENCES rewrite283.orders(order_id),
    status text NOT NULL
        CHECK (status IN ('SUCCEEDED', 'FAILED', 'PENDING')),
    paid_amount numeric(12, 2) NOT NULL
        CHECK (paid_amount >= 0)
);
```

Một đơn có thể có nhiều `order_items` và nhiều `payments` (các lần thử thanh toán). Đây là nguồn tạo ra lỗi nhân hàng nếu JOIN không đúng mục đích.

### 4.4. Bảng phụ chứa NULL để kiểm thử NOT IN

```sql
CREATE TABLE rewrite283.contact_queue (
    queue_id integer PRIMARY KEY,
    customer_id integer
        REFERENCES rewrite283.customers(customer_id),
    source text NOT NULL
);
```

`customer_id` **được phép NULL**. Bảng này dùng để thấy rõ khác biệt giữa `NOT IN` và `NOT EXISTS`.

### 4.5. Nạp dữ liệu

```sql
INSERT INTO rewrite283.customers(customer_id, email, segment)
VALUES
    (1, 'an@example.test', 'VIP'),
    (2, 'binh@example.test', 'STANDARD'),
    (3, 'chi@example.test', 'STANDARD'),
    (4, 'dung@example.test', 'VIP'),
    (5, 'em@example.test', 'STANDARD'),
    (6, 'phuc@example.test', 'STANDARD');

INSERT INTO rewrite283.orders(
    order_id, customer_id, ordered_at, status, total_amount
)
VALUES
    (101, 1, DATE '2026-09-01', 'PAID',      500),
    (102, 1, DATE '2026-09-02', 'CANCELLED', 100),
    (103, 2, DATE '2026-09-04', 'PAID',      200),
    (104, 3, DATE '2026-09-05', 'NEW',       300),
    (105, 3, DATE '2026-09-06', 'PAID',      300),
    (106, 4, DATE '2026-09-07', 'PAID',      800),
    (107, 4, DATE '2026-09-09', 'PAID',      600),
    (108, 5, DATE '2026-09-10', 'NEW',       110);

INSERT INTO rewrite283.order_items(
    order_id, line_no, product_id, quantity, unit_price
)
VALUES
    (101, 1, 10, 1, 500),
    (103, 1, 20, 2, 100),
    (105, 1, 10, 1, 200),
    (105, 2, 30, 1, 100),
    (106, 1, 20, 2, 400),
    (107, 1, 30, 3, 200);

INSERT INTO rewrite283.payments(
    payment_id, order_id, status, paid_amount
)
VALUES
    (201, 101, 'SUCCEEDED', 500),
    (202, 103, 'FAILED',    200),
    (203, 103, 'SUCCEEDED', 200),
    (204, 105, 'SUCCEEDED', 300),
    (205, 106, 'SUCCEEDED', 800),
    (206, 107, 'PENDING',   600);

INSERT INTO rewrite283.contact_queue(
    queue_id, customer_id, source
)
VALUES
    (1, 1,    'campaign'),
    (2, NULL, 'legacy'),
    (3, 3,    'campaign');
```

Các câu INSERT trên chỉ nên chạy **một lần trên schema mới**. Chạy lại sẽ gặp lỗi khóa chính/unique, không phải lỗi của bài tối ưu.

### 4.6. Đặc điểm cố ý của dữ liệu

| Khách | Đơn PAID | Đơn khác | Ghi chú |
|---|---:|---:|---|
| 1 — An | 1 | 1 CANCELLED | Có đơn PAID |
| 2 — Bình | 1 | 0 | Có đơn PAID |
| 3 — Chi | 1 | 1 NEW | Có đơn PAID |
| 4 — Dũng | 2 | 0 | **Hai đơn PAID** để kiểm tra nhân dòng |
| 5 — Em | 0 | 1 NEW | Có đơn nhưng **không có PAID** |
| 6 — Phúc | 0 | 0 | **Chưa có đơn** |

Các trường hợp cần quan sát:

- Khách **1, 2, 3, 4** có ít nhất một đơn PAID.
- Khách **4** có hai đơn PAID.
- Khách **5** có đơn nhưng chưa có đơn PAID.
- Khách **6** chưa có đơn nào.
- Order **105** có hai dòng item.
- Order **103** có hai payment attempts.
- `contact_queue` có một hàng `customer_id = NULL`.

### 4.7. Chuẩn bị thống kê

```sql
ANALYZE rewrite283.customers;
ANALYZE rewrite283.orders;
ANALYZE rewrite283.order_items;
ANALYZE rewrite283.payments;
ANALYZE rewrite283.contact_queue;
```

Bảng lab rất nhỏ, nên planner có thể dùng `Seq Scan` dù điều kiện/index hợp lý. Mục tiêu đầu là **so sánh kết quả đúng**, sau đó mới xem hành vi optimizer trên dữ liệu đại diện lớn hơn.

## 5. EXISTS: hỏi có ít nhất một hàng phù hợp

Cú pháp:

```sql
SELECT ...
FROM outer_table AS x
WHERE EXISTS (
    SELECT 1
    FROM inner_table AS y
    WHERE y.key = x.key
);
```

`EXISTS` trả boolean theo việc subquery có trả **ít nhất một hàng** hay không:

- Có hàng → `TRUE`.
- Không có hàng → `FALSE`.

Nó không phải phép đếm. Một hàng hay một nghìn hàng phù hợp đều khiến `EXISTS` là TRUE.

### 5.1. Tìm khách có đơn PAID

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả mong đợi:

```text
1 | an@example.test
2 | binh@example.test
3 | chi@example.test
4 | dung@example.test
```

Mỗi khách xuất hiện **một lần**, vì bảng ngoài `customers` vốn có mỗi customer_id duy nhất.

### 5.2. Vì sao chọn SELECT 1?

Trong `EXISTS (SELECT 1 ...)`, dữ liệu cột mà subquery định trả về **không phải mục tiêu**. PostgreSQL chủ yếu quan tâm subquery có hàng hay không.

Thường cả hai cách đều tương đương trong trường hợp đơn giản:

```sql
EXISTS (SELECT 1 FROM rewrite283.orders AS o WHERE ...)
```

```sql
EXISTS (SELECT * FROM rewrite283.orders AS o WHERE ...)
```

`SELECT 1` giúp người đọc thấy rõ mục đích kiểm tra tồn tại. Nó **không có cam kết luôn nhanh hơn SELECT ***. Có các ngoại lệ khi danh sách SELECT/biểu thức có ngữ nghĩa đặc biệt (ví dụ một số biểu thức tập hợp), nên không cần biến quy tắc này thành mẹo tối ưu tuyệt đối.

### 5.3. EXISTS không mặc nhiên cần LIMIT 1

Đôi khi viết:

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    LIMIT 1
)
```

`LIMIT 1` thường **không cần thiết** cho yêu cầu boolean đơn giản. Optimizer đã biết chỉ cần xác định có một hàng phù hợp hay không và có thể chọn semi join hoặc chiến lược dừng sớm.

Không nên thêm LIMIT 1 như một quy tắc “tăng tốc bắt buộc”; với các subquery phức tạp, LIMIT có thể thay đổi những cơ hội biến đổi kế hoạch.

## 6. JOIN khác EXISTS khi quan hệ một-nhiều

So sánh:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Trong dữ liệu lab, kết quả có **5 dòng**:

```text
1 | an@example.test
2 | binh@example.test
3 | chi@example.test
4 | dung@example.test
4 | dung@example.test
```

Khách Dũng xuất hiện hai lần do có order 106 và 107, cùng PAID.

Trong khi:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

trả **4 dòng**.

### 6.1. JOIN + DISTINCT có thể tương đương với EXISTS?

Với yêu cầu **chỉ lấy những cột khách hàng** và không dùng số lần lặp là thông tin nghiệp vụ:

```sql
SELECT DISTINCT c.customer_id, c.email
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

trả cùng tập khách hàng như `EXISTS` trong lab.

Nhưng cần phân biệt:

- `JOIN + DISTINCT` tạo các cặp hàng match rồi loại trùng theo các biểu thức SELECT (trừ khi optimizer tối ưu được).
- `EXISTS` diễn đạt trực tiếp “chỉ cần biết có match”.
- Hai dạng không tự tương đương nếu SELECT có cột từ orders, dùng aggregate tính trên join, hoặc cần giữ multiplicity của bảng ngoài.
- `DISTINCT` loại trùng **trên toàn bộ cột SELECT**, không chỉ trên customer_id.

Khi bài toán là membership, bắt đầu từ `EXISTS` thường rõ ràng hơn.

### 6.2. Không dùng DISTINCT để che lỗi JOIN thiếu điều kiện

Nếu lỡ thiếu predicate:

```sql
SELECT DISTINCT c.customer_id
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o ON TRUE;
```

bạn vẫn có thể nhận được danh sách customer_id mà không thấy dữ liệu bị nhân cực lớn ở bước trung gian. Nhưng đó là một phép ghép gần như Cartesian và có thể rất tốn tài nguyên.

**Sửa điều kiện JOIN**, không chỉ thêm DISTINCT vào cuối truy vấn.

## 7. Semi join: ý nghĩa của EXISTS và IN

Về mặt quan hệ, **semi join** giữ những hàng của phía trái có ít nhất một hàng phía phải phù hợp; nó **không trả cột hoặc nhân hàng theo phía phải**.

Ký hiệu khái niệm:

```text
customers SEMI JOIN orders
    ON customer_id match AND status=PAID

Output grain:
    Một hàng cho mỗi hàng customers thỏa điều kiện.
```

PostgreSQL có thể biến đổi những truy vấn `EXISTS` hay `IN` thích hợp thành những node kế hoạch như:

- `Nested Loop Semi Join`.
- `Hash Semi Join`.
- `Merge Semi Join`.

Không phải mọi subquery đều được decorrelate; khả năng biến đổi còn phụ thuộc cấu trúc, toán tử, volatile expressions và nhiều yếu tố khác.

### 7.1. EXISTS có thể “dừng ở match đầu tiên” không?

Về ngữ nghĩa, nó chỉ cần biết **có một match**. Một số chiến lược thực thi, nhất là nested-loop semi join với index phù hợp, có thể tránh đọc tiếp các match không cần thiết cho một hàng phía ngoài.

Nhưng không nên khẳng định mọi plan đều luôn chạy subquery từng hàng rồi dừng ở match đầu. Với hash semi join, PostgreSQL có thể quét và dựng hash từ phía trong trước; plan chính xác do optimizer quyết định.

### 7.2. Vì sao “EXISTS luôn nhanh hơn JOIN” là sai?

Một câu:

```sql
SELECT o.order_id, c.email
FROM rewrite283.orders AS o
JOIN rewrite283.customers AS c
  ON c.customer_id = o.customer_id;
```

thật sự cần cột của **cả hai bảng**. Thay bằng EXISTS không trả được email của khách theo cùng nghĩa.

Ngược lại, nếu phía phải được bảo đảm **tối đa một match** bởi UNIQUE constraint phù hợp, JOIN có thể không nhân hàng và đôi khi tối ưu tương đương. Chọn theo **cột cần trả và cardinality hợp lệ**, sau đó đo plan.

## 8. IN: kiểm tra một giá trị có thuộc tập hay không

Ví dụ:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM rewrite283.orders AS o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Trong dữ liệu lab, kết quả vẫn là khách **1, 2, 3, 4**.

### 8.1. IN và EXISTS khác cú pháp, thường có thể cùng kết quả khi lọc

`IN` kiểm tra một giá trị có nằm trong kết quả subquery hay không. Nếu customer_id bên ngoài NOT NULL, phép so bằng phù hợp và mục tiêu là **lọc các hàng có match**, hai dạng sau có thể cùng trả tập hàng:

```sql
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM rewrite283.orders AS o
    WHERE o.status = 'PAID'
)
```

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.status = 'PAID'
      AND o.customer_id = c.customer_id
)
```

Planner có thể triển khai dưới dạng semi join, hash/subplan hoặc cơ chế khác.

### 8.2. IN vẫn chịu logic NULL ba giá trị

Nếu subquery chứa NULL và không tìm thấy match, biểu thức `x IN (subquery)` có thể trả **NULL/UNKNOWN**, chứ không phải FALSE.

Trong `WHERE`, chỉ các hàng có điều kiện TRUE được giữ; FALSE và UNKNOWN đều bị loại. Vì vậy **positive IN và positive EXISTS có thể trả cùng các hàng ở điều kiện lọc** dù giá trị biểu thức boolean trong SELECT/CASE khác nhau.

Đừng tự mở rộng tính tương đương đó sang `NOT IN` hoặc ngữ cảnh cần phân biệt FALSE với UNKNOWN.

## 9. NOT EXISTS: kiểm tra không có hàng thỏa điều kiện

Yêu cầu:

> Khách hàng chưa có **bất kỳ đơn PAID nào**.

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Kết quả mong đợi:

```text
5 | em@example.test
6 | phuc@example.test
```

Cả hai đều chưa có đơn PAID, nhưng:

- Khách 5 có một đơn NEW.
- Khách 6 không có đơn nào.

Đây là ví dụ giúp thấy **“không có đơn PAID”** khác với **“không có đơn”**.

### 9.1. NOT EXISTS cho “không có đơn bất kỳ”

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả chỉ có **khách 6**.

Một thao tác tối ưu không được tự xóa điều kiện `o.status = 'PAID'` rồi vẫn tuyên bố giữ nguyên ngữ nghĩa.

### 9.2. Anti join

`NOT EXISTS` diễn đạt một **anti join**: giữ hàng phía ngoài khi **không tồn tại** hàng phía trong khớp điều kiện.

PostgreSQL có thể chọn:

- `Hash Anti Join`.
- `Merge Anti Join`.
- `Nested Loop Anti Join`.

Tuy nhiên, không phải mọi trường hợp sẽ được decorrelate thành anti join; một số query giữ `SubPlan` hoặc dùng kế hoạch khác.

## 10. NOT IN và bẫy NULL: khác biệt phải nhớ

Một lỗi rất nguy hiểm là thay `NOT EXISTS` bằng `NOT IN` mà không xét NULL trong phía subquery.

Bảng `contact_queue` có:

```text
queue_id | customer_id
---------+------------
1        | 1
2        | NULL
3        | 3
```

Giả sử muốn tìm khách **không có trong contact_queue theo customer_id**.

### 10.1. Truy vấn NOT IN

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE c.customer_id NOT IN (
    SELECT q.customer_id
    FROM rewrite283.contact_queue AS q
)
ORDER BY c.customer_id;
```

Trong dữ liệu lab, kết quả có thể là **0 hàng**.

Tại sao? Với `customer_id=2`:

```text
2 NOT IN (1, NULL, 3)

2 <> 1     = TRUE
2 <> NULL  = UNKNOWN
2 <> 3     = TRUE

TRUE AND UNKNOWN AND TRUE = UNKNOWN
```

`WHERE` chỉ giữ TRUE, nên khách 2 bị loại. Tương tự khách 4, 5, 6 cũng bị loại dù không có hàng customer_id tương ứng trong queue.

### 10.2. Truy vấn NOT EXISTS đúng yêu cầu membership

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.contact_queue AS q
    WHERE q.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả:

```text
2
4
5
6
```

Hàng `q.customer_id=NULL` không thỏa `q.customer_id=c.customer_id` đối với các customer_id NOT NULL. Vì vậy nó không khiến tất cả khách bị loại.

### 10.3. Có thể sửa NOT IN bằng IS NOT NULL?

Nếu **giá trị bên trái chắc chắn NOT NULL** và bạn muốn bỏ qua NULL phía phải, có thể viết:

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE c.customer_id NOT IN (
    SELECT q.customer_id
    FROM rewrite283.contact_queue AS q
    WHERE q.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
```

Trong fixture này, kết quả cũng là **2, 4, 5, 6**.

Tuy nhiên, đây là việc **thay đổi chính sách xử lý NULL** và cần chứng minh phù hợp nghiệp vụ. Nếu biểu thức phía ngoài cũng có thể NULL, `NOT IN` và `NOT EXISTS` vẫn có khác biệt.

### 10.4. Khi nào nên ưu tiên NOT EXISTS?

Khi câu hỏi là **“không có hàng liên quan thỏa predicate”**, `NOT EXISTS` thường rõ nghĩa và ít mắc bẫy NULL hơn `NOT IN`.

Không dùng `NOT IN` như công thức phủ định tự động cho mọi subquery. Kiểm tra cả nullable của hai phía và logic ba giá trị.

## 11. NULL và logic ba giá trị trong điều kiện phức tạp

SQL có ba trạng thái logic quan trọng:

- `TRUE`.
- `FALSE`.
- `UNKNOWN`, thường do phép so sánh với `NULL`.

Ví dụ:

```sql
SELECT
    2 IN (1, NULL, 3) AS value_in_set,
    2 NOT IN (1, NULL, 3) AS value_not_in_set,
    NOT EXISTS (
        SELECT 1
        FROM rewrite283.contact_queue AS q
        WHERE q.customer_id = 2
    ) AS no_queue_row;
```

Về ngữ nghĩa:

```text
value_in_set     = NULL (UNKNOWN)
value_not_in_set = NULL (UNKNOWN)
no_queue_row     = TRUE
```

### 11.1. Trong WHERE và trong SELECT có thể khác nhau

Hai biểu thức:

```sql
x IN (SELECT y ...)
```

và:

```sql
EXISTS (SELECT 1 ... WHERE y=x)
```

khi dùng làm bộ lọc **WHERE cần TRUE** có thể cho cùng tập hàng trong nhiều tình huống equality thường gặp. Nhưng khi đưa ra cột kết quả:

```sql
SELECT
    x IN (SELECT y ...) AS flag_in,
    EXISTS (SELECT 1 ... WHERE y=x) AS flag_exists
```

chúng có thể trả lần lượt `NULL` và `FALSE`. Nếu phía ứng dụng cần phân biệt UNKNOWN, đây là sự khác biệt quan trọng.

### 11.2. IS NOT DISTINCT FROM là so sánh NULL-safe, nhưng đổi nghĩa

`a IS NOT DISTINCT FROM b` xem hai NULL là **không khác nhau**. Nếu rewrite:

```sql
WHERE q.customer_id IS NOT DISTINCT FROM c.customer_id
```

thì một customer_id NULL phía ngoài **có thể match** một hàng NULL phía trong, khác điều kiện `=` chuẩn.

Chỉ dùng khi nghiệp vụ coi NULL tương đương một khóa thực sự. Không “sửa” NULL trong SQL bằng cách thay mọi `=` thành `IS NOT DISTINCT FROM` mà không xét semantics.

## 12. LEFT JOIN ... IS NULL và NOT EXISTS

Một dạng khác để tìm “không có bản ghi liên quan” là **anti join qua LEFT JOIN**.

Ví dụ khách không có đơn PAID:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Trong fixture, kết quả là khách **5, 6**, giống truy vấn `NOT EXISTS` cùng predicate.

### 12.1. Vì sao kiểm tra o.order_id IS NULL?

`order_id` là PRIMARY KEY và **không thể NULL** ở một hàng orders thực sự. Khi LEFT JOIN không tìm được đơn PAID, PostgreSQL tạo một hàng kết quả bên phải với các cột NULL; khi đó `o.order_id IS NULL` xác nhận **không match**.

Nếu chọn một cột phía phải vốn **có thể NULL** và viết:

```sql
WHERE o.some_nullable_column IS NULL
```

thì có thể giữ cả những khách **có match nhưng cột ấy NULL**, dẫn đến kết quả sai.

**Quy tắc:** trong mẫu LEFT JOIN anti-join, kiểm tra một cột phía phải chắc chắn NOT NULL khi match, thường là khóa chính.

### 12.2. ON và WHERE phải đặt đúng vị trí

Điều kiện xác định “loại đơn được xem là match” phải nằm trong `ON`:

```sql
LEFT JOIN rewrite283.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
WHERE o.order_id IS NULL
```

Nếu viết:

```sql
LEFT JOIN rewrite283.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.order_id IS NULL
```

thì kết quả **không còn đúng**. Với hàng không có match, `o.status` là NULL, nên `o.status='PAID'` không TRUE. Với hàng có match, `o.order_id` không NULL. Cả hai nhóm bị loại.

### 12.3. Chọn NOT EXISTS hay LEFT JOIN anti-join?

Cả hai có thể được optimizer biến đổi thành anti join phù hợp. `NOT EXISTS` thường biểu đạt ý nghĩa “không tồn tại hàng” trực tiếp, đặc biệt khi predicate phức tạp.

`LEFT JOIN ... IS NULL` cũng hữu ích, miễn:

- Đặt mọi predicate bên phải cần xác định match trong ON.
- Kiểm tra cột bên phải chắc chắn NOT NULL khi match.
- Không vô ý trả cột bên phải hoặc thay đổi mức nhân dòng.

## 13. LEFT JOIN với ON khác WHERE: giữ hay loại hàng bên trái?

Yêu cầu:

> Liệt kê **mọi khách hàng**, kèm đơn PAID nếu có. Khách chưa có đơn PAID vẫn phải xuất hiện.

Đúng:

```sql
SELECT
    c.customer_id,
    c.email,
    o.order_id,
    o.status
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Kết quả gồm:

- Khách 1: đơn 101.
- Khách 2: đơn 103.
- Khách 3: đơn 105.
- Khách 4: đơn 106 và 107.
- Khách 5: một hàng, phía orders NULL.
- Khách 6: một hàng, phía orders NULL.

Tổng **7 hàng**, vì khách 4 có hai đơn PAID.

### 13.1. Chuyển status sang WHERE làm thay đổi ngữ nghĩa

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Điều kiện WHERE loại các hàng mà `o.status` NULL. Truy vấn không còn giữ khách 5/6; trong trường hợp này nó có tác dụng giống INNER JOIN chỉ lấy PAID.

### 13.2. Predicate trên bảng trái có thể đặt WHERE

Ví dụ chỉ muốn mọi khách VIP, có hoặc không có đơn PAID:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.segment = 'VIP';
```

Lọc trên `c.segment` không vô tình làm mất hàng trái không match do NULL phía phải.

### 13.3. Không máy móc đẩy điều kiện qua outer join

Các phép biến đổi predicate pushdown hợp lệ phụ thuộc join type và tính chất điều kiện. Với INNER JOIN, điều kiện ON và WHERE thường dễ hoán đổi hơn; với OUTER JOIN, việc chuyển điều kiện từ ON sang WHERE có thể đổi kết quả.

## 14. Correlated subquery: truy vấn con phụ thuộc hàng bên ngoài

Một truy vấn con **correlated** dùng giá trị từ query bên ngoài.

Ví dụ lấy số đơn của mỗi khách:

```sql
SELECT
    c.customer_id,
    c.email,
    (
        SELECT COUNT(*)
        FROM rewrite283.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM rewrite283.customers AS c
ORDER BY c.customer_id;
```

Đây là **scalar correlated subquery**: mỗi khách nhận một giá trị số đếm.

Kết quả:

| customer_id | order_count |
|---:|---:|
| 1 | 2 |
| 2 | 1 |
| 3 | 2 |
| 4 | 2 |
| 5 | 1 |
| 6 | 0 |

### 14.1. Correlated không tự có nghĩa là “chạy vòng lặp chậm”

Một cách giải thích đơn giản là “với mỗi khách, chạy subquery”. Nhưng PostgreSQL có thể biến đổi hoặc chọn plan khác tùy cấu trúc. Nhiều subquery có thể được decorrelate; một số scalar correlated subquery vẫn thành `SubPlan` thực thi nhiều lần.

Muốn biết thực tế, dùng `EXPLAIN (ANALYZE, BUFFERS)` và quan sát `loops`, số hàng, I/O cùng kế hoạch.

### 14.2. COUNT(*) trả 0 khác scalar không có hàng

`SELECT COUNT(*) FROM ... WHERE ...` **trả một hàng với 0** khi không có bản ghi khớp, do aggregate không GROUP BY vẫn trả kết quả.

Nhưng một scalar subquery thông thường như:

```sql
(
  SELECT o.order_id
  FROM rewrite283.orders AS o
  WHERE o.customer_id = c.customer_id
)
```

có thể:

- Trả NULL nếu không có hàng.
- Trả giá trị nếu có đúng một hàng.
- **Lỗi nếu có hơn một hàng**: scalar subquery trả nhiều hàng.

Vì vậy không thể thay mọi scalar subquery bằng JOIN mà mặc định behavior tương đương.

## 15. Viết lại correlated COUNT thành LEFT JOIN + GROUP BY

Ví dụ correlated COUNT ở phần trước có thể viết lại:

```sql
SELECT
    c.customer_id,
    c.email,
    COUNT(o.order_id) AS order_count
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.email
ORDER BY c.customer_id;
```

Trong fixture, kết quả như correlated COUNT: khách 6 có count=0.

### 15.1. Bẫy COUNT(*) trên LEFT JOIN

Sai cho mục tiêu đếm đơn:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS order_count
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

Khách 6 không có đơn vẫn tạo **một hàng NULL mở rộng** từ LEFT JOIN, nên `COUNT(*)` trả **1**, không phải 0.

Đúng:

```sql
COUNT(o.order_id)
```

vì `o.order_id` là NOT NULL ở hàng orders thực. Khi không match, nó là NULL và không bị COUNT đếm.

### 15.2. Viết lại aggregate phải giữ đúng grain

Nếu JOIN thêm `order_items` rồi đếm orders:

```sql
SELECT c.customer_id, COUNT(o.order_id)
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
  ON o.customer_id=c.customer_id
LEFT JOIN rewrite283.order_items AS i
  ON i.order_id=o.order_id
GROUP BY c.customer_id;
```

order 105 có hai items nên khách 3 có thể bị **đếm thừa** một đơn. Muốn đếm đơn không trùng có thể cân nhắc:

```sql
COUNT(DISTINCT o.order_id)
```

hoặc tốt hơn, **tổng hợp trước theo đúng grain** ở orders, rồi mới join. Đừng thêm DISTINCT như phản xạ nếu có thể tránh nhân hàng ngay từ đầu.

## 16. Tổng hợp trước khi JOIN để tránh nhân số liệu

Yêu cầu:

> Với mỗi khách, lấy tổng tiền đơn PAID và số lần thanh toán thành công.

Nếu JOIN orders với payments rồi SUM total_amount, một order có nhiều payment attempts có thể làm **nhân tổng tiền đơn**.

Một cách an toàn là tổng hợp **mỗi nguồn ở grain thích hợp** trước khi ghép:

```sql
WITH paid_orders AS (
    SELECT
        customer_id,
        COUNT(*) AS paid_order_count,
        SUM(total_amount) AS paid_order_amount
    FROM rewrite283.orders
    WHERE status = 'PAID'
    GROUP BY customer_id
),
successful_payments AS (
    SELECT
        o.customer_id,
        COUNT(*) AS successful_payment_attempts,
        SUM(p.paid_amount) AS successful_paid_amount
    FROM rewrite283.orders AS o
    JOIN rewrite283.payments AS p
      ON p.order_id = o.order_id
    WHERE p.status = 'SUCCEEDED'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.email,
    COALESCE(po.paid_order_count, 0) AS paid_order_count,
    COALESCE(po.paid_order_amount, 0) AS paid_order_amount,
    COALESCE(sp.successful_payment_attempts, 0)
        AS successful_payment_attempts,
    COALESCE(sp.successful_paid_amount, 0)
        AS successful_paid_amount
FROM rewrite283.customers AS c
LEFT JOIN paid_orders AS po
  ON po.customer_id = c.customer_id
LEFT JOIN successful_payments AS sp
  ON sp.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Trong hai CTE:

- `paid_orders` có tối đa một hàng mỗi customer_id.
- `successful_payments` có tối đa một hàng mỗi customer_id.

JOIN hai tập đã tổng hợp **không nhân chéo** các hàng order và payment attempts.

### 16.1. Phải đặt tên metric đúng

`SUM(paid_order_amount)` là tổng **giá trị đơn đã có trạng thái PAID**, còn `SUM(successful paid_amount)` là tổng **các lần thanh toán SUCCEEDED** trong dữ liệu. Hai đại lượng có thể khác nhau, nhất là khi có refund, partial payment hoặc retry. Đừng tự xem chúng là cùng một “doanh thu” nếu nghiệp vụ chưa định nghĩa.

### 16.2. COUNT(DISTINCT) có phải luôn sai?

Không. `COUNT(DISTINCT o.order_id)` có thể đúng về kết quả khi bị nhân hàng. Nhưng nó có thể tốn chi phí và không sửa được mọi biểu thức aggregate khác. Tổng hợp trước hoặc dùng EXISTS đúng nghĩa thường rõ ràng hơn.

## 17. Scalar subquery với MAX: lấy thời điểm đơn mới nhất

Yêu cầu:

> Mỗi khách một hàng và ngày đặt đơn gần nhất; khách chưa có đơn trả NULL.

Dạng scalar correlated subquery:

```sql
SELECT
    c.customer_id,
    c.email,
    (
        SELECT MAX(o.ordered_at)
        FROM rewrite283.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS last_order_date
FROM rewrite283.customers AS c
ORDER BY c.customer_id;
```

`MAX` aggregate không GROUP BY trả **một giá trị** cho mỗi khách; nếu không có đơn, giá trị là NULL.

### 17.1. Viết lại bằng aggregate JOIN

```sql
SELECT
    c.customer_id,
    c.email,
    a.last_order_date
FROM rewrite283.customers AS c
LEFT JOIN (
    SELECT
        o.customer_id,
        MAX(o.ordered_at) AS last_order_date
    FROM rewrite283.orders AS o
    GROUP BY o.customer_id
) AS a
  ON a.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Hai dạng cùng ngữ nghĩa trên fixture, miễn:

- `customer_id` là khóa nhóm đúng.
- Cần `LEFT JOIN` để giữ khách 6.
- Không thay nhầm `MAX(ordered_at)` bằng một giá trị không xác định từ mỗi nhóm.

### 17.2. Dạng JOIN đơn giản hơn khi chỉ cần MAX

```sql
SELECT
    c.customer_id,
    c.email,
    MAX(o.ordered_at) AS last_order_date
FROM rewrite283.customers AS c
LEFT JOIN rewrite283.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.email
ORDER BY c.customer_id;
```

Dạng này cũng phù hợp nếu không JOIN thêm quan hệ một-nhiều khác có thể nhân hàng và các cột aggregate giữ đúng ý nghĩa.

### 17.3. Khi nào aggregate-first lợi hơn correlated MAX?

Tùy số khách cần trả và index:

- Nếu chỉ xem một vài khách và có index `(customer_id, ordered_at DESC)`, tìm MAX cho từng khách có thể rất hiệu quả.
- Nếu xem toàn bộ khách, một lần aggregate orders rồi join có thể hợp lý.
- PostgreSQL có thể chọn plan khác dự đoán; không biến “JOIN luôn nhanh hơn correlated subquery” thành quy tắc.

## 18. Lấy “ngày mới nhất” khác “hàng đơn mới nhất”

Hai yêu cầu:

1. Lấy ngày đặt đơn lớn nhất → `MAX(ordered_at)`.
2. Lấy **order_id, status, amount** của đơn mới nhất → cần chọn **một hàng cụ thể**.

Không nên viết:

```sql
SELECT customer_id,
       MAX(ordered_at),
       order_id
FROM rewrite283.orders
GROUP BY customer_id;
```

Câu này không hợp lệ nếu `order_id` không được group/aggregate hoặc được suy ra phụ thuộc hàm theo quy tắc SQL của PostgreSQL. Và dù DB cho phép trong một trường hợp khác, không có bảo đảm “order_id bất kỳ” thuộc hàng có MAX date.

Cũng không nên:

```sql
SELECT o.customer_id, o.order_id, o.ordered_at
FROM rewrite283.orders AS o
WHERE o.ordered_at = (
    SELECT MAX(i.ordered_at)
    FROM rewrite283.orders AS i
    WHERE i.customer_id = o.customer_id
);
```

rồi tuyên bố **chắc chắn một hàng mỗi khách**. Nếu hai đơn có cùng ngày mới nhất, query trả **cả hai**.

Muốn “một đơn mới nhất”, cần quy tắc tie-breaker, ví dụ:

```sql
ORDER BY ordered_at DESC, order_id DESC
```

## 19. LATERAL: lấy hàng đứng đầu cho từng hàng bên trái

PostgreSQL hỗ trợ `LATERAL` để một subquery trong FROM tham chiếu các cột của bảng trước nó.

Yêu cầu:

> Mỗi khách một hàng, lấy đơn mới nhất theo `ordered_at DESC, order_id DESC`. Khách chưa có đơn vẫn xuất hiện.

```sql
SELECT
    c.customer_id,
    c.email,
    latest.order_id,
    latest.ordered_at,
    latest.status,
    latest.total_amount
FROM rewrite283.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.ordered_at,
        o.status,
        o.total_amount
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY c.customer_id;
```

Giải thích:

- Với mỗi khách phía trái, subquery có thể xét các đơn của chính khách ấy.
- `ORDER BY ... LIMIT 1` chọn một đơn theo thứ tự xác định.
- `LEFT JOIN LATERAL ... ON TRUE` giữ khách không có đơn, với các cột latest=NULL.
- Index trên `orders(customer_id, ordered_at DESC, order_id DESC)` có thể phục vụ đường truy cập này.

### 19.1. Kết quả dự kiến

| customer_id | latest order_id | latest status |
|---:|---:|---|
| 1 | 102 | CANCELLED |
| 2 | 103 | PAID |
| 3 | 105 | PAID |
| 4 | 107 | PAID |
| 5 | 108 | NEW |
| 6 | NULL | NULL |

Lưu ý khách 1 có đơn mới nhất **CANCELLED**, dù cũng có một đơn PAID trước đó. Không được tự chuyển điều kiện “đơn mới nhất” thành “đơn PAID mới nhất” nếu nghiệp vụ không yêu cầu.

### 19.2. LEFT JOIN LATERAL và CROSS JOIN LATERAL

Nếu dùng:

```sql
CROSS JOIN LATERAL (...)
```

khách 6 không có order sẽ bị loại vì subquery không trả hàng. Muốn giữ khách 6, dùng `LEFT JOIN LATERAL ... ON TRUE` như trên.

### 19.3. LATERAL không luôn nhanh nhất

Khi bảng ngoài có rất nhiều khách, subquery có thể phải truy cập orders nhiều lần. Một kế hoạch dùng index lookup per customer có thể rất tốt cho tập khách nhỏ, nhưng không mặc định tốt hơn một lần scan+sort/group của toàn bộ orders.

## 20. DISTINCT ON: lựa chọn đặc trưng của PostgreSQL

PostgreSQL cung cấp `DISTINCT ON` để lấy **hàng đầu tiên** theo nhóm sau khi sắp xếp phù hợp.

Ví dụ đơn mới nhất mỗi khách **có đơn**:

```sql
SELECT DISTINCT ON (o.customer_id)
    o.customer_id,
    o.order_id,
    o.ordered_at,
    o.status,
    o.total_amount
FROM rewrite283.orders AS o
ORDER BY
    o.customer_id,
    o.ordered_at DESC,
    o.order_id DESC;
```

Kết quả có một hàng cho mỗi khách 1–5, **không có khách 6** vì khách 6 chưa có đơn.

### 20.1. Muốn giữ khách chưa có đơn

Bọc DISTINCT ON trong subquery, sau đó LEFT JOIN:

```sql
WITH latest_orders AS (
    SELECT DISTINCT ON (o.customer_id)
        o.customer_id,
        o.order_id,
        o.ordered_at,
        o.status,
        o.total_amount
    FROM rewrite283.orders AS o
    ORDER BY
        o.customer_id,
        o.ordered_at DESC,
        o.order_id DESC
)
SELECT
    c.customer_id,
    c.email,
    l.order_id,
    l.ordered_at,
    l.status
FROM rewrite283.customers AS c
LEFT JOIN latest_orders AS l
  ON l.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Dạng này trả khách 6 với NULL giống yêu cầu LATERAL ở trên.

### 20.2. ORDER BY phải chọn tie-breaker rõ ràng

`DISTINCT ON (customer_id)` giữ hàng đầu tiên của mỗi nhóm theo thứ tự. Nếu ORDER BY không xác định đủ hàng nào đứng đầu khi ngày trùng nhau, kết quả có thể phụ thuộc kế hoạch/thứ tự vật lý.

`order_id DESC` là tie-breaker rõ ràng khi order_id unique.

### 20.3. Quy tắc về prefix ORDER BY

Trong PostgreSQL, biểu thức `DISTINCT ON` phải khớp các biểu thức **đầu của ORDER BY** theo quy tắc cú pháp của nó. Ví dụ:

```sql
SELECT DISTINCT ON (customer_id) ...
ORDER BY customer_id, ordered_at DESC, order_id DESC
```

là dạng hợp lệ điển hình.

Đừng đổi:

```sql
ORDER BY ordered_at DESC, customer_id
```

rồi kỳ vọng nó vẫn biểu diễn đúng việc chọn hàng đầu tiên cho từng customer trong DISTINCT ON.

## 21. ROW_NUMBER(): cách thay thế bằng window function

Một phương án khác:

```sql
WITH ranked AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        o.status,
        o.total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM rewrite283.orders AS o
)
SELECT
    c.customer_id,
    c.email,
    r.order_id,
    r.ordered_at,
    r.status
FROM rewrite283.customers AS c
LEFT JOIN ranked AS r
  ON r.customer_id = c.customer_id
 AND r.rn = 1
ORDER BY c.customer_id;
```

Phương án này cũng trả một đơn mới nhất cho khách có đơn, và giữ khách 6.

### 21.1. Vì sao r.rn = 1 đặt trong ON?

Trong LEFT JOIN, đặt:

```sql
ON r.customer_id = c.customer_id AND r.rn = 1
```

giữ những khách không có hàng ranked tương ứng.

Nếu đưa:

```sql
WHERE r.rn = 1
```

sau LEFT JOIN, khách 6 có r.rn=NULL sẽ bị lọc, khiến query mất yêu cầu giữ mọi khách.

### 21.2. LATERAL, DISTINCT ON và ROW_NUMBER có giống nhau không?

Chúng **có thể** trả cùng kết quả khi:

- Cùng định nghĩa “mới nhất”.
- Cùng tie-breaker.
- Cùng yêu cầu giữ khách không có đơn.
- Không thay đổi filter/status.
- Mỗi cách chọn đúng một hàng mỗi customer.

Nhưng plan và chi phí khác nhau tùy số khách, số đơn/khách, index và số cột cần trả. Phải đo trên workload đại diện.

## 22. Điều kiện trong EXISTS đặt ở đâu để giữ đúng ý nghĩa?

Giả sử hỏi:

> Tìm khách có ít nhất một đơn PAID **và** đơn ấy có payment SUCCEEDED.

Đúng:

```sql
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND EXISTS (
          SELECT 1
          FROM rewrite283.payments AS p
          WHERE p.order_id = o.order_id
            AND p.status = 'SUCCEEDED'
      )
)
ORDER BY c.customer_id;
```

Kết quả fixture: **1, 2, 3, 4** (với khách 4, order 106 đã thành công; order 107 còn PENDING).

### 22.1. Bẫy viết hai EXISTS độc lập

Sai nếu nghiệp vụ yêu cầu **cùng một đơn** vừa PAID vừa được thanh toán:

```sql
WHERE EXISTS (
    SELECT 1 FROM rewrite283.orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
AND EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    JOIN rewrite283.payments p ON p.order_id=o.order_id
    WHERE o.customer_id = c.customer_id
      AND p.status='SUCCEEDED'
)
```

Hai EXISTS có thể đúng nhờ **hai đơn khác nhau**: một đơn PAID nhưng chưa thanh toán, một đơn khác NEW/CANCELLED có payment SUCCEEDED do dữ liệu bất thường hoặc workflow riêng. Khi yêu cầu “cùng một đối tượng thỏa đồng thời”, các predicate phải được **liên kết bằng đúng khóa**.

### 22.2. EXISTS lồng nhau không tự gây N×M thực thi

Optimizer có thể decorrelate hoặc chọn semi join nhiều cấp. Nhưng tính đúng của ràng buộc theo **cùng order_id** là yêu cầu đầu tiên. Sau đó mới tối ưu kế hoạch.

## 23. EXISTS khác COUNT(*) > 0 ở mục đích và chi phí

Hai dạng:

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
)
```

và:

```sql
WHERE (
    SELECT COUNT(*)
    FROM rewrite283.orders AS o
    WHERE o.customer_id = c.customer_id
) > 0
```

có cùng điều kiện boolean khi COUNT đơn giản không có lỗi khác: “có ít nhất một đơn”.

Nhưng:

- `EXISTS` biểu đạt kiểm tra **có/không**.
- `COUNT(*)` biểu đạt **đếm tất cả** các hàng phù hợp rồi so sánh.
- PostgreSQL có thể tối ưu chúng khác nhau; EXISTS tạo cơ hội semi join/dừng sớm tốt hơn ở một số plan.
- Không khẳng định EXISTS luôn nhanh hơn, đặc biệt nếu COUNT được dùng cho mục tiêu khác hoặc planner đã tối ưu hiệu quả.

### 23.1. COUNT >= 2 không thể đổi thành EXISTS thường

```sql
WHERE (
    SELECT COUNT(*)
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
) >= 2
```

hỏi **ít nhất hai đơn**.

`EXISTS` đơn thuần chỉ hỏi **ít nhất một đơn**. Đây là thay đổi ngữ nghĩa.

Nếu chỉ cần biết có tối thiểu hai đơn, có thể dùng aggregate/HAVING hoặc logic khác phù hợp. Không thay thành EXISTS chỉ vì thấy nó nhanh hơn trong ví dụ có ngưỡng 1.

## 24. Có thể chuyển EXISTS thành INNER JOIN khi nào?

Một điều kiện đủ trực quan là join phía phải bảo đảm **tối đa một hàng match cho mỗi hàng bên trái**.

Ví dụ bảng customers có `email UNIQUE`. Giả sử query gốc chỉ cần biết khách có một dòng profile trong một bảng `profiles(customer_id PRIMARY KEY, ...)`. Nếu `profiles.customer_id` UNIQUE/PRIMARY KEY thì:

```sql
WHERE EXISTS (
    SELECT 1
    FROM profiles AS p
    WHERE p.customer_id = c.customer_id
)
```

có thể tương đương về **các hàng khách** với:

```sql
JOIN profiles AS p
  ON p.customer_id = c.customer_id
```

khi chỉ SELECT các cột của c và các điều kiện tương ứng, vì mỗi khách match tối đa một profile.

Nhưng cần kiểm chứng:

- Khóa unique của phía phải có đúng phạm vi filter không?
- Predicate JOIN có bao gồm tất cả cột khóa ghép không?
- Một hàng phía phải có thể match nhiều lần vì phép nối không dùng equality khóa?
- Giá trị NULL có làm điều kiện khác biệt không?
- SELECT có làm lộ các cột phía phải hoặc thêm xử lý GROUP BY không?

Đối với `orders(customer_id)`, một khách có nhiều đơn, nên **không có bảo đảm tối đa một match**.

### 24.1. Join tới bảng một-một không tự tốt hơn EXISTS

Ngay cả khi tương đương, optimizer có thể tạo plan tương tự hoặc khác nhau. Hãy giữ câu SQL dễ đọc, đúng ngữ nghĩa, và đo bằng EXPLAIN khi cần.

## 25. Correlated subquery trong SELECT có thể trả nhiều hàng: lỗi quan trọng

Xét:

```sql
SELECT
    c.customer_id,
    (
        SELECT o.order_id
        FROM rewrite283.orders AS o
        WHERE o.customer_id=c.customer_id
    ) AS order_id
FROM rewrite283.customers AS c;
```

Khách 1, 3 và 4 có **nhiều đơn**, nên scalar subquery không thể tự chọn một order_id; PostgreSQL có thể báo:

```text
ERROR: more than one row returned by a subquery used as an expression
```

Một cách sửa sai là thêm `LIMIT 1` mà không ORDER BY:

```sql
SELECT o.order_id
FROM rewrite283.orders o
WHERE o.customer_id=c.customer_id
LIMIT 1
```

Nó chọn một hàng không có quy tắc thứ tự xác định, nên có thể thay đổi theo plan/dữ liệu.

### 25.1. Cần xác định yêu cầu trước khi sửa

- Nếu cần **tất cả đơn**: dùng JOIN, chấp nhận nhiều hàng mỗi khách.
- Nếu cần **đơn mới nhất**: dùng ORDER BY với tie-breaker, LATERAL/DISTINCT ON/ROW_NUMBER.
- Nếu cần **số đơn**: dùng COUNT.
- Nếu cần **có đơn hay không**: dùng EXISTS.
- Nếu cần **tổng tiền**: dùng SUM với grain rõ.
- Nếu cần **một đơn theo unique key**: bảo đảm unique constraint/predicate khớp.

Không thêm `LIMIT 1` chỉ để che lỗi nhiều hàng mà chưa biết business rule.

## 26. Aggregate và HAVING: câu hỏi về nhóm, không phải đơn lẻ

Yêu cầu:

> Tìm khách có **ít nhất hai đơn PAID**.

```sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count
FROM rewrite283.orders AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id
HAVING COUNT(*) >= 2
ORDER BY o.customer_id;
```

Dữ liệu lab chỉ có **khách 4** thỏa.

### 26.1. Không đổi thành EXISTS đơn thuần

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
)
```

còn đúng với khách 1,2,3, mỗi người chỉ có một đơn PAID. Nó không bảo toàn yêu cầu tối thiểu **hai**.

### 26.2. Nếu cần cột khách và số đếm

```sql
WITH paid_counts AS (
    SELECT
        customer_id,
        COUNT(*) AS paid_order_count
    FROM rewrite283.orders
    WHERE status='PAID'
    GROUP BY customer_id
    HAVING COUNT(*) >= 2
)
SELECT
    c.customer_id,
    c.email,
    pc.paid_order_count
FROM rewrite283.customers c
JOIN paid_counts pc
  ON pc.customer_id=c.customer_id
ORDER BY c.customer_id;
```

CTE làm rõ rằng truy vấn đang join từ tập **một hàng mỗi khách** đã được aggregate.

## 27. NOT EXISTS, EXCEPT và khác biệt bag/set

Một cách khác để tìm khách không có đơn PAID:

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c

EXCEPT

SELECT o.customer_id
FROM rewrite283.orders AS o
WHERE o.status='PAID';
```

Trong fixture, kết quả là khách **5,6**.

### 27.1. Vì sao EXCEPT không phải thay thế tự động?

Trong PostgreSQL, `EXCEPT` mặc định dùng **set semantics** và loại các hàng trùng. `NOT EXISTS` lọc các hàng phía ngoài, giữ multiplicity của chính phía ngoài nếu nguồn có hàng trùng.

Ví dụ nếu phía ngoài không phải customers PK mà là tập sự kiện có hai hàng cùng customer_id, NOT EXISTS có thể giữ cả hai hàng sự kiện, còn EXCEPT trên customer_id có thể rút thành một giá trị.

`EXCEPT ALL` có semantics multiset khác với EXCEPT thông thường, nhưng cũng **không mặc nhiên đồng nghĩa anti join**, vì nó trừ số lần xuất hiện giữa hai tập, không chỉ kiểm tra tồn tại.

### 27.2. NULL trong EXCEPT

Các set operations xử lý tính trùng của NULL theo quy tắc nhóm/set của SQL, khác phép equality `=` trong correlated NOT EXISTS.

Vì vậy, nếu cột khóa nullable, không thay `NOT EXISTS` bằng `EXCEPT` trước khi kiểm tra chính xác ngữ nghĩa NULL và duplicate mà nghiệp vụ cần.

## 28. CTE trong PostgreSQL: rõ ràng hơn, không luôn nhanh hơn

Common Table Expression:

```sql
WITH paid_customers AS (
    SELECT DISTINCT customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
)
SELECT c.customer_id, c.email
FROM rewrite283.customers AS c
JOIN paid_customers AS p
  ON p.customer_id=c.customer_id;
```

là một cách viết rõ phần chuẩn bị tập khách PAID. Nhưng không mặc định nó tốt hơn `EXISTS`.

### 28.1. MATERIALIZED và NOT MATERIALIZED

Ở các phiên bản PostgreSQL hỗ trợ, bạn có thể viết:

```sql
WITH paid_customers AS MATERIALIZED (
    SELECT DISTINCT customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
)
SELECT ...
```

hoặc:

```sql
WITH paid_customers AS NOT MATERIALIZED (
    SELECT DISTINCT customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
)
SELECT ...
```

Các dấu `...` trên chỉ là khuôn mẫu, không phải câu SQL hoàn chỉnh.

Ý nghĩa khái quát:

- `MATERIALIZED` yêu cầu CTE hoạt động như một kết quả trung gian được tính và lưu theo ngữ nghĩa hỗ trợ, có thể giới hạn predicate pushdown.
- `NOT MATERIALIZED` cho phép những CTE phù hợp được gộp vào truy vấn cha, có thể hỗ trợ tối ưu xuyên ranh giới.
- PostgreSQL hiện đại có thể inline một số CTE SELECT không có side effect, thường khi được tham chiếu một lần; CTE tham chiếu nhiều lần có những mặc định khác.
- Không phải mọi CTE đều được inline. Data-modifying CTE, recursive CTE và các trường hợp có volatile functions có quy tắc riêng.

**Không coi CTE là tối ưu tự động hoặc optimization fence trong mọi phiên bản PostgreSQL.** Kiểm tra phiên bản server và kế hoạch cụ thể.

### 28.2. Materialize có thể tốt hoặc xấu

Có lợi nếu cần dùng lại một kết quả trung gian đắt nhiều lần.

Có hại nếu bắt buộc tạo tập lớn trước khi query cha có thể lọc xuống rất ít hàng. Vì vậy phải đo theo số lần tham chiếu và selectivity.

## 29. Predicate pushdown: đúng cho INNER JOIN chưa chắc đúng cho OUTER JOIN

Optimizer có thể đẩy điều kiện lọc xuống gần bảng nguồn để giảm số hàng được xử lý. Nhưng chỉ khi điều kiện và join semantics cho phép.

Ví dụ INNER JOIN:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o
  ON o.customer_id=c.customer_id
WHERE o.status='PAID';
```

có thể tương đương về kết quả với:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
JOIN (
    SELECT order_id, customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
) AS o
  ON o.customer_id=c.customer_id;
```

vì điều kiện lọc bảng orders được áp dụng trước hay sau INNER JOIN thông thường đều loại các cặp hàng không đạt.

Nhưng với `LEFT JOIN`, chuyển điều kiện từ ON sang WHERE làm thay đổi việc giữ hàng trái không match, như đã thấy trong phần 13.

### 29.1. Không di chuyển LIMIT tùy tiện

Hai truy vấn này khác nghĩa:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers c
JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 3;
```

và:

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers c
JOIN (
    SELECT *
    FROM rewrite283.orders
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 3
) o
  ON o.customer_id=c.customer_id;
```

Trong fixture mọi order đều có khách hợp lệ, nhưng nếu có điều kiện khác trong JOIN/WHERE, hai cách có thể chọn tập ba hàng khác nhau. **LIMIT trước hay sau lọc/join là một thay đổi cardinality tiềm ẩn.**

### 29.2. Điều kiện với hàm volatile

Một số hàm PostgreSQL như `random()` hoặc `clock_timestamp()` mang tính volatile. Việc đổi số lần/thứ tự đánh giá có thể làm kết quả khác.

Không dùng các hàm có side effect hoặc phụ thuộc số lần gọi như một phép thử “EXISTS luôn đọc đến hàng đầu tiên”. PostgreSQL không bảo đảm mọi nhánh biểu thức boolean được đánh giá theo thứ tự nguồn SQL như imperative code.

## 30. EXISTS với UPDATE và DELETE: giữ đúng tập mục tiêu

EXISTS không chỉ dùng trong SELECT.

Ví dụ cập nhật phân khúc VIP cho khách có ít nhất một đơn PAID với tổng tiền >= 700:

```sql
UPDATE rewrite283.customers AS c
SET segment='VIP'
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
      AND o.total_amount >= 700
)
RETURNING c.customer_id, c.segment;
```

Trong fixture, customer 4 đã VIP và vẫn thỏa. Câu lệnh vẫn là một UPDATE cho hàng match, ngay cả nếu giá trị segment không đổi.

### 30.1. UPDATE ... FROM có thể nhân match

Một biến thể:

```sql
UPDATE rewrite283.customers AS c
SET segment='VIP'
FROM rewrite283.orders AS o
WHERE o.customer_id=c.customer_id
  AND o.status='PAID'
  AND o.total_amount >= 700;
```

Nếu mỗi khách match nhiều hàng nguồn, PostgreSQL phải chọn một hàng join để tác động đến cùng hàng đích; khi SET phụ thuộc các cột của nguồn, kết quả có thể không được dựa vào lựa chọn nguồn mơ hồ.

Với mục đích **chỉ kiểm tra có ít nhất một đơn đủ điều kiện**, EXISTS truyền đạt rõ nghĩa hơn và tránh giả định có một dòng nguồn duy nhất.

### 30.2. DELETE ... WHERE NOT EXISTS

Ví dụ khuôn mẫu xóa những bản ghi tạm chưa được tham chiếu:

```sql
DELETE FROM some_temp_objects AS t
WHERE NOT EXISTS (
    SELECT 1
    FROM object_links AS l
    WHERE l.object_id=t.object_id
);
```

Đây là khuôn mẫu, không chạy trực tiếp vì hai bảng không nằm trong fixture lab. Đối với xóa dữ liệu thật, cần thiết kế constraint, transaction và concurrency; kết quả NOT EXISTS đúng trong snapshot không tự bảo đảm không xuất hiện tham chiếu mới sau đó nếu không có cơ chế ràng buộc phù hợp.

### 30.3. INSERT ... WHERE NOT EXISTS không thay UNIQUE

Ví dụ:

```sql
INSERT INTO some_table(key, value)
SELECT $1, $2
WHERE NOT EXISTS (
    SELECT 1
    FROM some_table
    WHERE key=$1
);
```

Hai transaction có thể cùng thấy “khóa chưa tồn tại” rồi cùng INSERT. Nếu hệ thống cần duy nhất, **UNIQUE constraint/index** mới là hàng rào dữ liệu quan trọng; `INSERT ... ON CONFLICT` có thể là chiến lược phù hợp cho thao tác nguyên tử.

Dùng EXISTS để lọc truy vấn không có nghĩa đã giải quyết hết race condition khi ghi.

## 31. Các index phục vụ semi/anti join và correlated lookup

Một số index thường hữu ích cho workload trong bài:

```sql
CREATE INDEX idx_rewrite283_orders_customer_status
ON rewrite283.orders(customer_id, status);

CREATE INDEX idx_rewrite283_orders_customer_date
ON rewrite283.orders(
    customer_id,
    ordered_at DESC,
    order_id DESC
);

CREATE INDEX idx_rewrite283_payments_order_status
ON rewrite283.payments(order_id, status);
```

### 31.1. EXISTS tìm đơn PAID

```sql
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
)
```

Index `(customer_id,status)` cho phép truy cập các đơn theo khách và trạng thái. Khi cần tìm match đầu tiên, đây có thể là đường truy cập thuận lợi cho nested-loop semi join.

### 31.2. LATERAL lấy đơn mới nhất

```sql
WHERE o.customer_id=c.customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 1
```

Index `(customer_id, ordered_at DESC, order_id DESC)` phù hợp để tìm những đơn của khách và lấy hàng đầu theo thứ tự.

### 31.3. NOT EXISTS và index

Anti join có thể hưởng lợi từ index vì cần xác định liệu có match hay không. Nhưng nếu query quét gần như toàn bộ bảng bên trong và xây hash sẽ rẻ hơn, planner có thể chọn Hash Anti Join thay vì hàng nghìn index lookups.

### 31.4. Index không tự bảo đảm plan

Fixture có 6 khách và 8 đơn, nên Seq Scan thường hợp lý hơn. Hãy dùng dữ liệu đủ lớn/đại diện để so sánh hiệu năng và luôn xem chi phí duy trì index khi INSERT/UPDATE/DELETE.

## 32. EXPLAIN: nhìn plan thay vì đoán cú pháp

Câu lệnh:

```sql
EXPLAIN
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
);
```

có thể sinh plan dạng:

```text
Hash Semi Join
  Hash Cond: (...)
  -> Seq Scan on customers
  -> Hash
       -> Seq Scan on orders
            Filter: status = 'PAID'
```

Đây là **sơ đồ minh họa**, không phải plan đã chạy thực tế.

Cùng truy vấn cũng có thể có:

- `Nested Loop Semi Join` với index lookup trên orders.
- `Merge Semi Join` nếu đầu vào có thứ tự phù hợp.
- Cách biến đổi/plan khác tùy PostgreSQL, dữ liệu và cấu trúc query.

### 32.1. EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
);
```

Xem:

- `actual rows`: số hàng thực.
- `loops`: số lần node thực thi.
- `Buffers`: số block hit/read và các hoạt động I/O có liên quan.
- `Hash Cond`, `Join Filter`, `Index Cond`, `Filter`: nơi predicate được thực hiện.
- Node `Semi Join` hoặc `Anti Join` nếu optimizer sử dụng.
- Ước lượng rows/cost so với actual rows.

### 32.2. EXPLAIN ANALYZE thực thi SQL

Với SELECT, `EXPLAIN ANALYZE` thực thi SELECT để đo.

Với INSERT/UPDATE/DELETE, nó **thực sự thay đổi dữ liệu** trước khi transaction kết thúc. Khi phân tích DML, chỉ chạy trong môi trường lab hoặc transaction có kế hoạch rollback phù hợp; không chạy tùy tiện trên production.

### 32.3. Đừng so sánh chỉ một lần trên bảng sáu dòng

Kế hoạch trên dữ liệu nhỏ có thể không đại diện production. Muốn benchmark có ý nghĩa cần khối lượng, phân bố, số lượng đơn/khách, selectivity, thống kê, index, tham số và workload đồng thời tương tự thực tế.

## 33. SubPlan, InitPlan và decorrelation

Một truy vấn con có thể xuất hiện trong EXPLAIN dưới nhiều dạng.

### 33.1. SubPlan

Nếu subquery chưa được chuyển thành join, plan có thể ghi `SubPlan` và cho thấy số lần thực thi.

Ví dụ scalar correlated count:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id,
       (
          SELECT COUNT(*)
          FROM rewrite283.orders AS o
          WHERE o.customer_id=c.customer_id
       ) AS n
FROM rewrite283.customers AS c;
```

Trong một số kế hoạch, node subplan có `loops` tương ứng số hàng customers được xử lý. Đó là thông tin để đánh giá liệu index lookup lặp lại có đắt hay không.

### 33.2. InitPlan

Một subquery độc lập với hàng ngoài trong một số tình huống có thể được tính trước hoặc thực hiện theo dạng `InitPlan`, ví dụ một giá trị ngưỡng dùng chung:

```sql
SELECT *
FROM rewrite283.orders
WHERE total_amount > (
    SELECT AVG(total_amount)
    FROM rewrite283.orders
);
```

Không cần giả định AVG luôn chạy lại cho từng order; PostgreSQL có thể tính subquery độc lập một lần theo plan thích hợp.

### 33.3. Decorrelate không phải lúc nào cũng khả thi

Các cấu trúc như:

- Một số `LIMIT/OFFSET`.
- Aggregate có liên hệ phức tạp.
- Window functions.
- Volatile expressions.
- Outer join và NULL semantics đặc thù.
- Security barriers và các ranh giới ngữ nghĩa khác.

có thể giới hạn những phép biến đổi hợp lệ. Một câu subquery nhìn ngắn hơn không nhất thiết có plan rẻ hơn; một CTE nhìn gọn hơn cũng không bảo đảm inline.

## 34. Quy trình kiểm chứng hai truy vấn có tương đương hay không

Trước khi triển khai một rewrite:

1. Ghi rõ **grain**: mỗi dòng đầu ra đại diện gì?
2. Xác định **cột đầu ra**, kiểu dữ liệu, alias và NULL policy.
3. Xác định số dòng **tối đa/tối thiểu** trên một khóa.
4. Liệt kê các ca có **0, 1, nhiều match**.
5. Liệt kê các ca **NULL ở khóa và cột lọc** nếu schema cho phép.
6. Nếu có ORDER BY/LIMIT, ghi rõ thứ tự và tie-breaker.
7. Thử query gốc và query mới trên cùng snapshot dữ liệu.
8. So sánh theo **multiset**, không chỉ số lượng hoặc tập DISTINCT.
9. Chỉ khi tương đương mới so sánh EXPLAIN và latency.

### 34.1. Tại sao COUNT(*) kết quả chưa đủ?

Hai truy vấn đều trả 4 dòng nhưng có thể trả **bốn customer_id khác nhau**. Hoặc cả hai trả cùng tập ID nhưng multiplicity khác.

Ví dụ:

```text
Q1: 1, 2, 3, 4
Q2: 1, 1, 2, 3
```

Cả hai có COUNT(*)=4, nhưng không tương đương.

### 34.2. Tại sao EXCEPT mặc định chưa đủ?

`EXCEPT` loại trùng, nên có thể bỏ qua khác biệt multiplicity. Khi kiểm tra truy vấn cần bảo toàn số lần xuất hiện, hãy dùng `EXCEPT ALL`.

## 35. Dùng EXCEPT ALL để kiểm chứng multiset

Giả sử muốn so sánh hai cách tìm khách có đơn PAID, cùng trả hai cột `customer_id, email`:

```sql
WITH q_exists AS (
    SELECT c.customer_id, c.email
    FROM rewrite283.customers AS c
    WHERE EXISTS (
        SELECT 1
        FROM rewrite283.orders AS o
        WHERE o.customer_id=c.customer_id
          AND o.status='PAID'
    )
),
q_join_distinct AS (
    SELECT DISTINCT c.customer_id, c.email
    FROM rewrite283.customers AS c
    JOIN rewrite283.orders AS o
      ON o.customer_id=c.customer_id
    WHERE o.status='PAID'
),
differences AS (
    (
        SELECT * FROM q_exists
        EXCEPT ALL
        SELECT * FROM q_join_distinct
    )
    UNION ALL
    (
        SELECT * FROM q_join_distinct
        EXCEPT ALL
        SELECT * FROM q_exists
    )
)
SELECT COUNT(*) AS difference_rows
FROM differences;
```

Trong fixture, `difference_rows = 0`.

### 35.1. Thử so EXISTS với JOIN không DISTINCT

Đổi CTE `q_join_distinct` thành một JOIN thông thường không DISTINCT, rồi so hai hướng bằng EXCEPT ALL. Trong fixture, vì khách 4 có hai đơn PAID, sẽ có **một bản ghi dư** từ bên JOIN; truy vấn kiểm chứng phát hiện khác biệt.

### 35.2. Cần cùng schema kết quả

Các query dùng trong EXCEPT ALL phải có:

- Cùng số cột.
- Kiểu dữ liệu tương thích.
- Cùng ý nghĩa cột theo cùng thứ tự.

`EXCEPT ALL` kiểm tra **giá trị và multiplicity** chứ không kiểm tra thứ tự trả về. Nếu thứ tự là một phần hợp đồng API, cần kiểm thử ORDER BY/tie-breaker riêng.

### 35.3. Kiểm chứng snapshot và concurrency

Khi so sánh hai query trên hệ thống đang ghi liên tục, nếu chạy ở hai thời điểm khác nhau, dữ liệu có thể thay đổi và tạo khác biệt giả.

Để so sánh chính xác, chạy trong môi trường fixture ổn định hoặc một transaction đọc phù hợp với snapshot nhất quán. Với production, đừng khóa dữ liệu lớn chỉ để benchmark; nên dùng bản sao/fixture có kiểm soát.

## 36. Lập test matrix ngữ nghĩa

Một bộ test nên có tối thiểu:

| Tình huống | Điều cần kiểm chứng |
|---|---|
| Bên phải không có hàng | EXISTS FALSE, NOT EXISTS TRUE |
| Bên phải đúng một hàng match | EXISTS TRUE; JOIN một hàng |
| Bên phải nhiều hàng match | JOIN nhân hàng; EXISTS không nhân |
| Khách chỉ có đơn NEW | “Không có PAID” TRUE, “không có đơn” FALSE |
| Khách không có bất kỳ đơn nào | LEFT JOIN vẫn giữ khách |
| Subquery NOT IN có NULL | Có thể khiến kết quả UNKNOWN |
| Khóa bên trái nullable | So sánh NULL và anti join cần rõ policy |
| Hai đơn có cùng ordered_at | Phải có tie-breaker chọn “mới nhất” |
| Nhiều items + nhiều payments | Không nhân sai SUM/COUNT |
| Aggregate trên LEFT JOIN rỗng | COUNT(*) khác COUNT(o.id) |
| Predicate ở LEFT JOIN ON | Giữ hàng bên trái không match |
| Predicate chuyển sang WHERE | Có thể biến outer join thành inner |
| DISTINCT ON thiếu ORDER BY đủ | Hàng được chọn không ổn định |
| Scalar subquery trả nhiều dòng | Phải lỗi hoặc xác định cách chọn |
| ORDER BY/LIMIT đặt trước/sau JOIN | Có thể đổi tập đầu ra |
| Prepared query với tham số | Plan generic/custom có thể khác |
| DML có NOT EXISTS | UNIQUE/isolation phải bảo vệ race |
| Tenant filter thiếu một phía | Có thể match sai tenant/lộ dữ liệu |

**Đúng trên fixture nhỏ chưa chứng minh đúng với mọi dữ liệu.** Cần test các edge cases đại diện cho schema và invariant nghiệp vụ.

## 37. Hiệu năng: so sánh theo workload, không theo cảm tính

Các dạng truy vấn có thể được optimizer xử lý khác nhau.

| Dạng truy vấn | Điểm mạnh có thể có | Cần quan sát |
|---|---|---|
| `EXISTS` | Diễn đạt membership; semi join hoặc dừng sớm | Số outer rows, index, join strategy |
| `IN (subquery)` | Diễn đạt membership rõ | NULL semantics, hash/semi plan |
| `NOT EXISTS` | Anti join rõ, ít bẫy NULL hơn NOT IN | Anti join plan, selectivity |
| `INNER JOIN` | Trả được dữ liệu bên phải | Bội số match và row explosion |
| `JOIN + DISTINCT` | Khôi phục tập khóa sau join | Chi phí DISTINCT, không che thiếu JOIN condition |
| `Correlated scalar aggregate` | Gọn với một ít outer rows | SubPlan loops và index lookup |
| `Aggregate rồi JOIN` | Tính mỗi nhóm trước, tránh nhân metric | Số nhóm, memory, hash/sort |
| `LEFT JOIN LATERAL LIMIT 1` | Top-1 lookup thuận lợi với index | Lần lặp theo outer rows |
| `DISTINCT ON` | Top-1 theo nhóm trong PostgreSQL | Thứ tự index, sort, tie-breaker |
| `ROW_NUMBER()` | Linh hoạt cho top-N/ranking | WindowAgg, sort/scan footprint |
| `CTE MATERIALIZED` | Dùng lại kết quả trung gian | Có cản predicate pushdown không |

### 37.1. Đo bằng dữ liệu đại diện

Một plan dùng `Seq Scan` trên 8 hàng không nói rằng EXISTS “không được tối ưu”. Ngược lại, một plan dùng Index Scan trên 1 triệu hàng cũng không tự bảo đảm nhanh nếu có random I/O lớn.

Tập cần đo:

- Thời gian thực thi trung vị và p95/p99 ở workload phù hợp.
- Số block shared hit/read.
- Actual rows / loops.
- Memory/spill khi hash/sort.
- Số lần thực thi query.
- Tần suất ghi và tác động của index bổ sung.
- Độ ổn định kế hoạch theo tham số và phân bố dữ liệu.

### 37.2. Không tối ưu bằng cách thay ngữ nghĩa

Nếu JOIN trả 5 dòng còn EXISTS trả 4 dòng, việc giảm 20% số dòng **không phải bằng chứng EXISTS nhanh hơn nhưng cùng kết quả**. Hai query đang trả hai thứ khác nhau.

Trước tiên phải quyết định output đúng của nghiệp vụ là 4 khách duy nhất hay 5 cặp customer–order.

## 38. Các lỗi phổ biến khi viết lại subquery/JOIN

### Lỗi 1 — Đổi JOIN một-nhiều thành EXISTS dù cần các cột con

EXISTS không trả dữ liệu cụ thể của từng order. Nếu báo cáo cần order_id và status cho mọi đơn, JOIN là đúng.

### Lỗi 2 — Đổi EXISTS thành JOIN rồi quên nhân hàng

Khách 4 có hai đơn PAID, JOIN trả hai dòng. EXISTS chỉ giữ một hàng customer.

### Lỗi 3 — Thêm DISTINCT để che vấn đề

DISTINCT có thể che lỗi JOIN thiếu predicate, tốn sort/hash và không giải quyết SUM bị nhân.

### Lỗi 4 — Dùng NOT IN với nullable subquery

Một NULL phía trong có thể khiến kết quả NOT IN là UNKNOWN cho mọi giá trị không match, làm mất toàn bộ hàng cần tìm.

### Lỗi 5 — Dùng cột nullable để anti-join qua LEFT JOIN

`WHERE right.nullable_column IS NULL` có thể giữ cả hàng match có giá trị NULL. Dùng cột xác nhận match không-null, như primary key.

### Lỗi 6 — Đặt filter của bảng phải từ ON xuống WHERE trong LEFT JOIN

Có thể làm mất hàng phía trái không match, đổi OUTER JOIN thành kết quả kiểu INNER JOIN.

### Lỗi 7 — COUNT(*) trên LEFT JOIN để đếm hàng phía phải

Khách không có đơn vẫn có một hàng NULL mở rộng; COUNT(*) có thể là 1. Dùng COUNT(o.order_id).

### Lỗi 8 — Tổng hợp sau JOIN nhiều quan hệ một-nhiều

Tích chéo số item × số payment attempt làm SUM/COUNT bị nhân. Tổng hợp trước theo đúng grain.

### Lỗi 9 — Lấy MAX(date) rồi gán kèm order_id bất kỳ

Hàng có ngày MAX phải được xác định bằng query top-1/tie-breaker, không bằng cách GROUP BY rồi lấy một cột không thuộc aggregate.

### Lỗi 10 — LIMIT 1 không ORDER BY

Không bảo đảm “mới nhất” hoặc “đầu tiên” theo nghiệp vụ; kết quả có thể thay đổi theo plan.

### Lỗi 11 — Quên LEFT JOIN khi khách không có bản ghi con vẫn cần xuất hiện

INNER JOIN, CROSS JOIN LATERAL hoặc DISTINCT ON trực tiếp trên orders có thể bỏ khách 6.

### Lỗi 12 — Di chuyển LIMIT trước JOIN

Đổi phạm vi áp dụng LIMIT, có thể chọn tập hàng khác.

### Lỗi 13 — Chuyển COUNT >= 2 thành EXISTS

EXISTS chỉ kiểm tra ít nhất một match, không đảm bảo có hai.

### Lỗi 14 — Hai EXISTS độc lập dù yêu cầu cùng một order

Có thể một EXISTS đúng nhờ order A và EXISTS còn lại đúng nhờ order B, trong khi không có order nào thỏa cả hai predicate.

### Lỗi 15 — Tin CTE luôn nhanh hơn subquery

CTE có thể được inline hoặc materialize; mặc định khác theo phiên bản, số lần tham chiếu và side effects.

### Lỗi 16 — Tin EXISTS bắt buộc chạy từng outer row

Planner có thể decorrelate thành Hash Semi Join hoặc Merge Semi Join; không lập luận chi phí bằng giả định imperative.

### Lỗi 17 — Tin EXISTS luôn chạy nhanh hơn JOIN

Nếu JOIN cần trả dữ liệu bên phải, nó đúng ngữ nghĩa. Nếu phía phải unique, JOIN cũng có thể hiệu quả. Phải đo plan.

### Lỗi 18 — Quên NULL trong biểu thức SELECT/CASE

Positive IN và EXISTS có thể cùng lọc hàng ở WHERE nhưng trả boolean UNKNOWN/FALSE khác nhau khi dùng làm cột.

### Lỗi 19 — So sánh bằng COUNT hoặc EXCEPT không ALL

Có thể bỏ sót khác biệt giá trị/multiplicity. Dùng test hai chiều với EXCEPT ALL và kiểm tra order riêng.

### Lỗi 20 — INSERT WHERE NOT EXISTS mà không có UNIQUE

Hai transaction đồng thời có thể cùng thấy “chưa có” rồi cùng INSERT. Cần constraint/transaction phù hợp.

### Lỗi 21 — Tối ưu SQL nhưng bỏ điều kiện tenant

JOIN/EXISTS có thể match dữ liệu tenant khác nếu không nối đủ khóa tenant, gây cả lỗi nghiệp vụ lẫn bảo mật.

### Lỗi 22 — Dựa vào EXPLAIN trên fixture quá nhỏ

Planner chọn Seq Scan trên vài hàng là bình thường; không suy ra quyết định trên dữ liệu production.

## 39. Bài tập thực hành có lời giải

Các bài sau dùng schema `rewrite283`. Với bài liên quan UPDATE, nên làm trên database lab hoặc trong transaction rồi rollback có chủ ý.

### Bài 1. Tìm khách đã từng có đơn PAID

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
)
ORDER BY c.customer_id;
```

**Đáp án:** `1, 2, 3, 4`.

### Bài 2. JOIN cùng điều kiện có bao nhiêu dòng?

```sql
SELECT c.customer_id, o.order_id
FROM rewrite283.customers AS c
JOIN rewrite283.orders AS o
  ON o.customer_id=c.customer_id
WHERE o.status='PAID'
ORDER BY c.customer_id, o.order_id;
```

**Đáp án:** 5 dòng; khách 4 xuất hiện hai lần tương ứng order 106 và 107.

### Bài 3. Vì sao DISTINCT có thể trả đúng khách ở bài 1?

**Lời giải:** DISTINCT trên cột khách loại các dòng trùng do nhiều đơn PAID, nhưng có thể tốn chi phí và không còn đúng nếu cần liệt kê các đơn.

### Bài 4. Chuyển IN thành EXISTS

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE c.customer_id IN (
    SELECT customer_id
    FROM rewrite283.orders
    WHERE status='PAID'
);
```

**Lời giải:**

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders AS o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
);
```

### Bài 5. Tìm khách không có đơn PAID

```sql
SELECT c.customer_id
FROM rewrite283.customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
)
ORDER BY c.customer_id;
```

**Đáp án:** `5, 6`.

### Bài 6. Tìm khách không có đơn nào

Thay điều kiện `NOT EXISTS` bằng kiểm tra không có order bất kỳ.

**Đáp án:** chỉ khách `6`.

### Bài 7. NOT IN trên contact_queue có hàng NULL sẽ ra sao?

```sql
SELECT customer_id
FROM rewrite283.customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM rewrite283.contact_queue
);
```

**Đáp án:** rỗng trong fixture này vì subquery chứa NULL và những giá trị không match trở thành UNKNOWN.

### Bài 8. Viết lại an toàn bằng NOT EXISTS

```sql
SELECT c.customer_id
FROM rewrite283.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM rewrite283.contact_queue AS q
    WHERE q.customer_id=c.customer_id
)
ORDER BY c.customer_id;
```

**Đáp án:** `2, 4, 5, 6`.

### Bài 9. Viết LEFT JOIN anti-join cho khách không có đơn PAID

```sql
SELECT c.customer_id
FROM rewrite283.customers c
LEFT JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id
 AND o.status='PAID'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

**Đáp án:** `5, 6`; order_id là NOT NULL khi match.

### Bài 10. Vì sao đổi o.status='PAID' xuống WHERE là sai?

**Lời giải:** WHERE loại các hàng NULL mở rộng của LEFT JOIN, nên khách không có PAID bị mất; điều kiện xác định match thuộc ON.

### Bài 11. Đếm mọi đơn từng khách, kể cả 0

```sql
SELECT c.customer_id,
       COUNT(o.order_id) AS n
FROM rewrite283.customers c
LEFT JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Đáp án:** `(1,2), (2,1), (3,2), (4,2), (5,1), (6,0)`.

### Bài 12. Vì sao COUNT(*) sai với khách 6?

**Lời giải:** LEFT JOIN tạo một hàng NULL mở rộng cho khách 6; COUNT(*) đếm nó là một, trong khi COUNT(o.order_id) không.

### Bài 13. Tìm khách có từ hai đơn PAID trở lên

```sql
SELECT customer_id, COUNT(*) AS n
FROM rewrite283.orders
WHERE status='PAID'
GROUP BY customer_id
HAVING COUNT(*)>=2;
```

**Đáp án:** chỉ khách `4` với hai đơn PAID.

### Bài 14. Có thể thay HAVING COUNT(*)>=2 bằng EXISTS không?

**Đáp án:** EXISTS thường chỉ đảm bảo có ít nhất một match, nên sẽ nhận cả khách 1,2,3; không tương đương.

### Bài 15. Lấy ngày đặt đơn mới nhất của mỗi khách

```sql
SELECT c.customer_id,
       MAX(o.ordered_at) AS last_order_date
FROM rewrite283.customers c
LEFT JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

**Đáp án:** khách 6 có NULL; mỗi khách còn lại có MAX date của orders.

### Bài 16. Lấy cả order_id của đơn mới nhất, có tie-breaker

```sql
SELECT c.customer_id, latest.order_id
FROM rewrite283.customers c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) latest ON TRUE
ORDER BY c.customer_id;
```

**Đáp án:** `1→102, 2→103, 3→105, 4→107, 5→108, 6→NULL`.

### Bài 17. DISTINCT ON phiên bản top-1

```sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at
FROM rewrite283.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
```

**Đáp án:** một đơn mới nhất cho mỗi khách **có đơn** (1–5); không có khách 6 nếu không LEFT JOIN từ customers.

### Bài 18. Window function thay thế

```sql
SELECT customer_id, order_id, ordered_at
FROM (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY ordered_at DESC, order_id DESC
           ) AS rn
    FROM rewrite283.orders o
) ranked
WHERE rn=1;
```

**Đáp án:** cùng các đơn mới nhất cho khách 1–5; muốn khách 6 cần LEFT JOIN phía ngoài.

### Bài 19. Có thể lấy “đơn mới nhất” chỉ bằng MAX(ordered_at) không?

**Đáp án:** không lấy đủ cột của một hàng duy nhất khi ngày bị trùng; cần tie-breaker và logic top-1.

### Bài 20. Tại sao JOIN order_items và payments dễ nhân SUM?

**Đáp án:** một order có thể có nhiều items và payment attempts, tạo tích số lượng match. Tổng hợp trước theo order/customer hoặc dùng semi join đúng nhu cầu.

### Bài 21. Đơn PAID có payment thành công

```sql
SELECT o.order_id
FROM rewrite283.orders AS o
WHERE o.status='PAID'
  AND EXISTS (
      SELECT 1
      FROM rewrite283.payments p
      WHERE p.order_id=o.order_id
        AND p.status='SUCCEEDED'
  )
ORDER BY o.order_id;
```

**Đáp án:** `101, 103, 105, 106`. Order 107 chỉ có payment PENDING.

### Bài 22. Vì sao hai EXISTS độc lập có thể sai?

**Đáp án:** mỗi EXISTS có thể đúng vì một order khác nhau. Nếu nghiệp vụ cần cùng một order vừa PAID vừa được thanh toán, phải liên kết EXISTS payment với `o.order_id` của order PAID.

### Bài 23. Index gợi ý cho kiểm tra đơn PAID theo khách

```sql
CREATE INDEX idx_rewrite283_customer_status_lab
ON rewrite283.orders(customer_id, status);
```

**Đáp án:** có thể hỗ trợ lookup theo `customer_id` và `status`; planner vẫn có thể dùng Seq Scan trên fixture nhỏ.

### Bài 24. Index gợi ý cho LATERAL mới nhất

```sql
CREATE INDEX idx_rewrite283_latest_lab
ON rewrite283.orders(customer_id, ordered_at DESC, order_id DESC);
```

**Đáp án:** có thể hỗ trợ `WHERE customer_id=? ORDER BY ordered_at DESC, order_id DESC LIMIT 1`.

### Bài 25. EXPLAIN nào để đo thực tế?

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id
FROM rewrite283.customers c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
      AND o.status='PAID'
);
```

**Đáp án:** xem plan thực tế, actual rows/loops/buffers. Không tự suy luận EXISTS luôn là Nested Loop.

### Bài 26. Cách kiểm chứng hai query đúng cả multiplicity?

**Đáp án:** dùng đối chiếu hai chiều bằng `EXCEPT ALL` và kiểm thử NULL/duplicate; nếu có ORDER BY/LIMIT, kiểm tra thứ tự riêng.

### Bài 27. Vì sao EXCEPT không ALL có thể bỏ sót lỗi?

**Đáp án:** EXCEPT mặc định loại trùng nên hai truy vấn có cùng tập giá trị nhưng số lần xuất hiện khác nhau có thể được coi là giống nhau.

### Bài 28. CTE MATERIALIZED có luôn tốt hơn không?

**Đáp án:** không. Materialization có thể giúp dùng lại kết quả đắt, nhưng cũng có thể ngăn predicate pushdown; tùy số lần tham chiếu và plan.

### Bài 29. Dùng NOT EXISTS để ngăn hai INSERT trùng có đủ không?

**Đáp án:** không trong mọi lịch concurrency. Cần UNIQUE constraint/index và chiến lược `ON CONFLICT` hoặc transaction/locking phù hợp.

### Bài 30. Hai truy vấn cùng trả 4 dòng có chắc tương đương?

**Đáp án:** không. Cần so giá trị từng hàng, NULL semantics, multiplicity và hợp đồng thứ tự nếu có.

## 40. Checklist tối ưu truy vấn theo ngữ nghĩa

| Câu hỏi cần trả lời | Hậu quả nếu bỏ qua |
|---|---|
| Một dòng kết quả đại diện cho gì? | Nhân hàng hoặc mất hàng |
| Nghiệp vụ hỏi tồn tại hay chi tiết? | Dùng JOIN thay EXISTS sai |
| Có quan hệ một-nhiều không? | COUNT/SUM nhân chéo |
| Có thể có 0 hoặc nhiều match không? | JOIN/Scalar subquery khác nhau |
| Bảng trái có phải được giữ cả khi không match? | Đổi LEFT JOIN thành INNER |
| Predicate thuộc ON hay WHERE? | Mất hàng NULL mở rộng |
| Cột dùng anti-join IS NULL có chắc NOT NULL khi match? | Nhận nhầm hàng match |
| NOT IN có NULL ở subquery hay bên ngoài? | UNKNOWN làm mất hàng |
| Kiểu dữ liệu và phép so có cùng ngữ nghĩa không? | Lệch NULL/collation/cast |
| Có dùng LIMIT/ORDER BY không? | Chọn khác hàng hoặc ngẫu nhiên |
| Có tie-breaker cho top-1 không? | Kết quả không ổn định |
| Aggregate thực hiện ở grain nào? | Sai số tiền/số đơn |
| Có cần COUNT hay chỉ EXISTS? | Tốn tài nguyên hoặc sai ngưỡng |
| Có khác biệt DISTINCT/EXCEPT ALL không? | Bỏ sót duplicate |
| Có ranh giới CTE MATERIALIZED không? | Cản tối ưu hoặc tính thừa |
| Có index cho correlation/join key không? | Nhiều lookup tốn I/O |
| Đã xem actual rows/loops/buffers chưa? | Đoán hiệu năng từ cú pháp |
| Đã test trên snapshot dữ liệu ổn định chưa? | So sánh sai do dữ liệu đổi |
| Có ngữ cảnh multi-tenant/RLS không? | Match sai và rò rỉ dữ liệu |
| DML có chống race bằng constraint/isolation không? | Hai transaction cùng ghi |
| Có đo cả read lẫn write overhead của index mới? | Tối ưu một query nhưng làm chậm tổng workload |

## 41. Bảng tra cứu nhanh

| Bài toán | Mẫu SQL phù hợp | Lưu ý quyết định |
|---|---|---|
| Có ít nhất một bản ghi con | `WHERE EXISTS (...)` | Không nhân hàng cha |
| Khóa thuộc một tập | `WHERE x IN (SELECT y...)` | Cẩn trọng NULL khi phủ định |
| Không có bản ghi con | `WHERE NOT EXISTS (...)` | Anti join rõ nghĩa |
| Không có match bằng outer join | `LEFT JOIN ... ON ... WHERE right.pk IS NULL` | Predicate match ở ON, kiểm tra cột NOT NULL |
| Liệt kê từng cặp cha–con | `INNER JOIN` | Một cha có thể có nhiều dòng |
| Giữ mọi cha | `LEFT JOIN` | Filter phải tương thích NULL |
| Đếm bản ghi con kể cả 0 | `LEFT JOIN + COUNT(child.pk)` | Không COUNT(*) nếu có NULL mở rộng |
| Aggregate nhiều nguồn 1-n | `Aggregate each source → JOIN` | Tránh nhân SUM |
| Giá trị lớn nhất mỗi nhóm | `MAX(value) GROUP BY key` | Chỉ trả giá trị, không tự chọn cả hàng |
| Hàng mới nhất mỗi nhóm | `LATERAL ORDER BY ... LIMIT 1` | Có index tốt cho top-1 |
| Một hàng đầu mỗi nhóm ở PostgreSQL | `DISTINCT ON (...) ORDER BY ...` | Tie-breaker rõ |
| Top-N theo nhóm | `ROW_NUMBER() OVER (...)` | Lọc rn ở đúng tầng |
| Đếm ít nhất N | `GROUP BY ... HAVING COUNT(*) >= N` | EXISTS thường chỉ bảo đảm >=1 |
| Query phụ thuộc hàng ngoài | `Correlated subquery` | Xem SubPlan loops |
| Reuse kết quả trung gian | `WITH ...` | Materialization/inline theo phiên bản |
| So kết quả có duplicate | `EXCEPT ALL` hai chiều | Không kiểm tra ORDER BY |
| Chọn kế hoạch thật | `EXPLAIN (ANALYZE, BUFFERS)` | Với DML sẽ thực thi thay đổi |
| Ghi nếu chưa tồn tại | UNIQUE + `ON CONFLICT` phù hợp | NOT EXISTS đơn thuần có race |

## 42. Tài liệu PostgreSQL nên tham khảo

Đọc tài liệu theo phiên bản PostgreSQL của hệ thống:

- [Subquery Expressions](https://www.postgresql.org/docs/current/functions-subquery.html): `EXISTS`, `IN`, `NOT IN`, `ANY`, `ALL` và logic kết quả.
- [Table Expressions](https://www.postgresql.org/docs/current/queries-table-expressions.html): JOIN, `ON`/`WHERE`, `LATERAL` và xử lý outer joins.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): `DISTINCT ON`, `ORDER BY`, `LIMIT` và ngữ nghĩa SELECT.
- [WITH Queries](https://www.postgresql.org/docs/current/queries-with.html): CTE, materialization, recursive và data-modifying CTE.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): hiểu kế hoạch, join algorithms, SubPlan và actual execution.
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): selectivity và ước lượng cardinality.
- [Indexes](https://www.postgresql.org/docs/current/indexes.html): index keys, operator classes và cách phục vụ lookup.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshot và tính đúng khi truy vấn được dùng để đưa ra quyết định ghi.

Kiểm tra server đang dùng:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

Kế hoạch tối ưu có thể thay đổi giữa phiên bản PostgreSQL; ngữ nghĩa của một phép viết lại hợp lệ thì phải được kiểm chứng độc lập với planner.

## 43. Tổng kết: viết lại đúng câu hỏi trước khi tối ưu kế hoạch

Nhớ ba câu hỏi nền tảng:

**1. Tôi muốn các hàng ghép hay chỉ muốn biết có hàng liên quan?**

```sql
-- Muốn mỗi cặp customer-order:
SELECT c.customer_id, o.order_id
FROM rewrite283.customers c
JOIN rewrite283.orders o
  ON o.customer_id=c.customer_id;

-- Muốn mỗi customer có ít nhất một order:
SELECT c.customer_id
FROM rewrite283.customers c
WHERE EXISTS (
    SELECT 1
    FROM rewrite283.orders o
    WHERE o.customer_id=c.customer_id
);
```

**2. Tôi muốn không có match hay muốn phép phủ định chứa NULL?**

```sql
-- Thường phù hợp hơn cho "không có bản ghi liên quan":
WHERE NOT EXISTS (
    SELECT 1
    FROM related_table r
    WHERE r.key = outer_table.key
)

-- NOT IN có thể ra UNKNOWN nếu phía trong chứa NULL:
WHERE outer_table.key NOT IN (
    SELECT r.key FROM related_table r
)
```

Hai đoạn trên là **khuôn mẫu WHERE**, cần đặt trong câu SELECT hoàn chỉnh với các bảng tương ứng.

**3. Tôi cần một giá trị tổng hợp hay cả hàng đứng đầu?**

```sql
-- Chỉ ngày lớn nhất:
SELECT customer_id, MAX(ordered_at)
FROM rewrite283.orders
GROUP BY customer_id;

-- Cả hàng mới nhất, xử lý tie:
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, ordered_at, status
FROM rewrite283.orders
ORDER BY customer_id, ordered_at DESC, order_id DESC;
```

Khi viết lại truy vấn PostgreSQL:

1. **Xác định grain** và quan hệ một-nhiều.
2. **EXISTS/NOT EXISTS** diễn đạt membership và anti-membership.
3. **JOIN** dùng khi thực sự muốn các cặp hàng, nhớ multiplicity.
4. **LEFT JOIN** giữ hàng bên trái, nên `ON` và `WHERE` không tùy tiện hoán đổi.
5. **NULL và NOT IN** cần được kiểm thử cụ thể.
6. **Aggregate trước JOIN** khi nhiều nguồn một-nhiều có thể nhân số liệu.
7. **Top-1 phải có thứ tự và tie-breaker**; chọn LATERAL, DISTINCT ON hoặc window theo workload.
8. **Optimizer có thể decorrelate** một số subquery, nhưng không bảo đảm mọi dạng đều cùng plan.
9. **EXCEPT ALL hai chiều** giúp kiểm tra khác biệt multiplicity trước khi tối ưu.
10. **EXPLAIN ANALYZE** và benchmark dữ liệu đại diện mới quyết định chiến lược nhanh hơn, sau khi kết quả đã đúng.

**Một câu để nhớ:** khi tối ưu truy vấn con, JOIN và EXISTS, điều cần bảo toàn không chỉ là “có vẻ ra cùng danh sách ID”, mà là **toàn bộ ngữ nghĩa kết quả: hàng nào được giữ, bao nhiêu lần, NULL được xử lý ra sao và mỗi hàng đại diện cho điều gì**.

