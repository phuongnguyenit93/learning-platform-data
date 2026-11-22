# B-tree và các dạng điều kiện được hỗ trợ trong PostgreSQL

## 1. B-tree là gì, và tại sao hiểu điều kiện truy vấn lại quan trọng?

Khi một bảng PostgreSQL có hàng triệu bản ghi, câu truy vấn:

```sql
SELECT *
FROM orders
WHERE order_id = 123456;
```

không nên phải đọc lần lượt tất cả hàng nếu có một cấu trúc cho phép tìm trực tiếp đến vùng chứa khóa `123456`. **B-tree index** là một trong những cấu trúc quan trọng nhất để làm việc đó.

B-tree (Balanced Tree) tổ chức các mục khóa theo **thứ tự có thể so sánh**, giúp PostgreSQL tìm một giá trị cụ thể, tìm một khoảng giá trị, hoặc đọc dữ liệu theo thứ tự khóa mà không nhất thiết quét và sắp xếp toàn bộ bảng. Trong PostgreSQL, B-tree là **phương pháp chỉ mục mặc định** của `CREATE INDEX`.

Nhưng tạo index chưa bảo đảm câu truy vấn sẽ sử dụng nó. PostgreSQL phải trả lời hai câu hỏi khác nhau:

1. **Điều kiện SQL có thể biến thành phép tìm trên B-tree hay không?**
2. **Dù có thể, sử dụng index có rẻ hơn các kế hoạch khác hay không?**

Ví dụ:

- `customer_id = 42` có thể là phép tìm theo khóa.
- `ordered_at >= t1 AND ordered_at < t2` có thể là quét phạm vi.
- `email LIKE 'user001%'` có thể tận dụng B-tree theo tiền tố trong điều kiện collation/operator class phù hợp.
- `email LIKE '%example.test'` không có tiền tố đầu chuỗi cố định, nên B-tree thông thường không cung cấp một phạm vi khóa hữu ích cho mẫu này.
- `lower(email) = 'abc'` không mặc nhiên dùng chỉ mục chỉ xây trên `email`; có thể cần **expression index** trên `lower(email)`.
- `ORDER BY ordered_at DESC LIMIT 20` thường là tình huống B-tree đáng giá, kể cả khi điều kiện WHERE không có phép so sánh bằng.

**Ý chính:** hiểu loại điều kiện và thứ tự cột trong index giúp viết truy vấn có thể tìm dữ liệu hiệu quả, nhưng **planner vẫn quyết định kế hoạch thực tế** dựa trên thống kê và chi phí.

### Mục tiêu bài học

Sau bài, bạn có thể:

1. Giải thích cách B-tree tổ chức khóa và vì sao hỗ trợ tìm chính xác, khoảng và thứ tự.
2. Nhận biết các toán tử `=`, `<`, `<=`, `>`, `>=`, `BETWEEN`, `IN`, `IS NULL` và cách chúng tương tác với B-tree.
3. Phân biệt điều kiện **có thể giới hạn index scan** với điều kiện chỉ được lọc sau khi tìm.
4. Hiểu ngoại lệ và giới hạn của `LIKE`, `ILIKE`, regular expression, `text_pattern_ops` và collation.
5. Thiết kế thứ tự các cột trong chỉ mục ghép theo **equality trước, range sau**, đồng thời hiểu rằng đây là một heuristic chứ không phải quy tắc tuyệt đối của mọi phiên bản planner.
6. Dùng B-tree hỗ trợ `ORDER BY`, `LIMIT`, phân trang keyset, `MIN`/`MAX` và một số thao tác DISTINCT/GROUP BY.
7. Dùng expression index, partial index và `INCLUDE` khi phù hợp.
8. Đọc `EXPLAIN` để phân biệt `Index Cond`, `Filter`, `Index Scan`, `Bitmap Index Scan` và `Index Only Scan`.
9. Giải thích vì sao index hợp lệ vẫn có thể không được sử dụng.
10. Tránh lạm dụng index, hiểu chi phí ghi, cập nhật, VACUUM và bảo trì.

---

## 2. Trực giác về cấu trúc B-tree

Một B-tree không lưu mọi hàng thành danh sách cần duyệt từ đầu. Nó phân chia không gian khóa thành các vùng có thứ tự, với các trang ở nhiều cấp:

```text
                     [ 30 | 70 ]
                    /     |      \
                   /      |       \
             keys <30   30..69   >=70
                 |        |        |
            [10|20]   [40|55]   [80|90]
                 \        |        /
                   Các mục ở lá
               dẫn tới dữ liệu của bảng
```

Sơ đồ chỉ minh họa ý tưởng; định dạng trang và chi tiết triển khai PostgreSQL phức tạp hơn.

B-tree có các đặc trưng quan trọng:

- Các khóa tuân theo một **thứ tự được xác định bởi operator class và collation** khi thích hợp.
- Có thể đi từ trang gốc qua các tầng trung gian đến vùng khóa cần tìm.
- Các trang lá phục vụ đọc những khóa gần nhau khi quét khoảng.
- Cây được giữ cân bằng khi dữ liệu được chèn, cập nhật hoặc xóa; người dùng không tự cân bằng cây.
- Một mục index không đồng nghĩa chứa đầy đủ bản ghi. PostgreSQL thường dùng **heap TID** để tìm phiên bản hàng trong bảng heap, trừ khi một **index-only scan** đáp ứng các điều kiện phù hợp.

### 2.1. Chi phí tìm và chi phí đọc

Khi truy vấn `order_id = 123456` và index rất chọn lọc, PostgreSQL có thể đi qua ít trang index rồi truy cập rất ít trang heap.

Nhưng nếu truy vấn trả 80% bảng, việc đi qua index rồi truy cập vô số heap pages có thể đắt hơn **sequential scan**. Vì vậy index **có khả năng hỗ trợ** một phép so sánh không có nghĩa planner **bắt buộc chọn index scan**.

### 2.2. B-tree không phải một loại lưu trữ thay thế bảng

PostgreSQL vẫn lưu dữ liệu bảng và các phiên bản hàng theo cơ chế heap/MVCC thông thường. B-tree là một **cấu trúc truy cập phụ trợ** được cập nhật khi dữ liệu thay đổi.

Một bảng có thể có nhiều B-tree indexes với các khóa khác nhau:

```sql
CREATE INDEX ON orders(customer_id);
CREATE INDEX ON orders(ordered_at);
CREATE INDEX ON orders(status, ordered_at);
```

Ba index phục vụ các kiểu truy cập khác nhau và tạo ra các chi phí lưu trữ/ghi riêng. Đừng tạo tất cả chỉ vì nhìn thấy các cột ấy trong SQL; cần đánh giá workload thực tế.

## 3. Tạo dữ liệu lab để quan sát kế hoạch

Dùng một database học tập và một schema riêng. Các lệnh tạo/chèn dữ liệu dưới đây **chỉ để chạy trong lab**, không áp dụng tự động trên production.

### 3.1. Bảng đơn hàng

```sql
CREATE SCHEMA IF NOT EXISTS btree250;

CREATE TABLE btree250.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id integer NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    ordered_at timestamptz NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
    reference_code text NOT NULL
);
```

Để có đủ hàng cho planner cân nhắc index, tạo 60.000 đơn giả lập bằng `generate_series`:

```sql
INSERT INTO btree250.orders(
    customer_id,
    status,
    ordered_at,
    amount_cents,
    reference_code
)
SELECT
    (g.n % 2000) + 1 AS customer_id,
    CASE
        WHEN g.n % 20 IN (0, 1) THEN 'CANCELLED'
        WHEN g.n % 20 IN (2, 3, 4, 5) THEN 'PAID'
        ELSE 'NEW'
    END AS status,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 365) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second' AS ordered_at,
    ((g.n % 5000) + 1) * 100::bigint AS amount_cents,
    'REF-' || lpad(g.n::text, 6, '0') AS reference_code
FROM generate_series(1, 60000) AS g(n);
```

Mỗi lần chạy script INSERT sẽ **thêm 60.000 hàng nữa**. Nếu đã chạy trước đó, dùng schema lab mới hoặc reset fixture có chủ ý.

Kiểm tra sơ bộ:

```sql
SELECT COUNT(*) AS total_orders
FROM btree250.orders;

SELECT status, COUNT(*)
FROM btree250.orders
GROUP BY status
ORDER BY status;
```

Kết quả với một lần insert dự kiến:

| status | Số đơn |
|---|---:|
| CANCELLED | 6.000 |
| NEW | 42.000 |
| PAID | 12.000 |

### 3.2. Bảng khách hàng cho truy vấn chuỗi

```sql
CREATE TABLE btree250.customers (
    customer_id integer PRIMARY KEY,
    email text NOT NULL UNIQUE,
    display_name text NOT NULL
);

INSERT INTO btree250.customers(
    customer_id, email, display_name
)
SELECT
    g.n,
    'user' || lpad(g.n::text, 5, '0') || '@example.test',
    'Khách hàng ' || g.n::text
FROM generate_series(1, 20000) AS g(n);
```

Ví dụ:

```text
customer_id = 1     email = user00001@example.test
customer_id = 100   email = user00100@example.test
customer_id = 1000  email = user01000@example.test
```

`PRIMARY KEY` và `UNIQUE` đã tạo các index phù hợp để bảo vệ tính duy nhất. Không tạo một index B-tree thứ hai có cùng định nghĩa mà không có mục đích cụ thể.

### 3.3. Cập nhật thống kê trong lab

```sql
ANALYZE btree250.orders;
ANALYZE btree250.customers;
```

`ANALYZE` cung cấp thống kê giúp planner ước lượng số hàng và lựa chọn kế hoạch. Trong production, autovacuum/autoanalyze thường đảm nhiệm công việc này theo cấu hình; không cần tự ANALYZE vô điều kiện sau mọi INSERT.

### 3.4. Kế hoạch có thể khác nhau

Các câu `EXPLAIN` trong bài để **quan sát khi bạn chạy thực tế**. Không coi một node được nêu là kết quả đã đo trên server của bạn.

Kế hoạch thay đổi theo:

- Số lượng và phân bố dữ liệu.
- Phiên bản PostgreSQL.
- Thống kê.
- Kích thước bảng và index.
- Workload/buffer cache.
- Collation, operator class, kiểu dữ liệu.
- Cấu hình planner và chi phí I/O.
- Có hay không các index khác trên cùng bảng.

## 4. B-tree hỗ trợ nhóm toán tử so sánh cốt lõi

Các B-tree operator classes thông dụng được thiết kế cho các chiến lược so sánh theo thứ tự:

| Toán tử | Ý nghĩa | Cách hình dung trên B-tree |
|---|---|---|
| `<` | Nhỏ hơn | Quét vùng khóa dưới ngưỡng |
| `<=` | Nhỏ hơn hoặc bằng | Quét vùng khóa đến ngưỡng |
| `=` | Bằng | Tìm khóa hoặc nhóm khóa cụ thể |
| `>=` | Lớn hơn hoặc bằng | Quét từ ngưỡng trở lên |
| `>` | Lớn hơn | Quét vùng khóa trên ngưỡng |

Ngoài ra, với kiểu dữ liệu/operator class phù hợp, B-tree có thể hỗ trợ `IS NULL` và `IS NOT NULL`, cũng như các dạng SQL được planner biến đổi thành phép tìm tương đương.

**Lưu ý:** không phải bất kỳ toán tử tự định nghĩa nào viết giống `=` hay `<` cũng tự động dùng mọi B-tree. Việc index hỗ trợ toán tử phụ thuộc **operator family/class**, kiểu dữ liệu và cách biểu thức truy vấn khớp với index.

### 4.1. Điều kiện bằng

```sql
SELECT order_id, status, amount_cents
FROM btree250.orders
WHERE order_id = 1250;
```

`order_id` là PRIMARY KEY nên đã có unique B-tree index. Đây là trường hợp tìm theo khóa rất chọn lọc; planner thường có cơ sở chọn Index Scan.

### 4.2. Điều kiện khoảng

Tạo chỉ mục thời điểm:

```sql
CREATE INDEX idx_btree250_orders_ordered_at
ON btree250.orders(ordered_at);
```

Sau đó:

```sql
SELECT order_id, ordered_at, amount_cents
FROM btree250.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-05-01 00:00:00+00';
```

Hai điều kiện xác định phạm vi **nửa mở**:

```text
[2026-04-01 00:00:00+00, 2026-05-01 00:00:00+00)
```

Ưu điểm của điều kiện nửa mở là không cần đoán độ chính xác của microsecond hoặc tạo một thời điểm “23:59:59.999999”.

### 4.3. BETWEEN

```sql
SELECT *
FROM btree250.orders
WHERE amount_cents BETWEEN 10000 AND 20000;
```

`BETWEEN a AND b` có ngữ nghĩa **bao gồm cả hai đầu**, tương tự:

```sql
amount_cents >= 10000 AND amount_cents <= 20000
```

Muốn index được sử dụng hiệu quả cho `amount_cents`, cần index thích hợp trên cột ấy hoặc một composite index có thể khai thác theo cấu trúc truy vấn.

### 4.4. Greater-than/less-than không luôn nhanh

```sql
SELECT *
FROM btree250.orders
WHERE amount_cents >= 100;
```

Nếu gần như tất cả hàng đều thỏa `amount_cents >= 100`, sequential scan có thể rẻ hơn index scan. **Khả năng hỗ trợ toán tử không bảo đảm lợi ích chi phí**.

## 5. Phân biệt Index Cond và Filter

Điều kiện trong WHERE có thể được thực hiện ở những bước khác nhau.

Ví dụ tạo index:

```sql
CREATE INDEX idx_btree250_orders_customer
ON btree250.orders(customer_id);
```

Truy vấn:

```sql
EXPLAIN
SELECT order_id, customer_id, status, amount_cents
FROM btree250.orders
WHERE customer_id = 42
  AND amount_cents > 200000;
```

Khi planner sử dụng index trên `customer_id`, plan có thể mô tả:

```text
Index Scan using idx_btree250_orders_customer ...
  Index Cond: (customer_id = 42)
  Filter: (amount_cents > 200000)
```

**Đây là cấu trúc minh họa**, không phải output chạy thực tế.

Diễn giải:

- **`Index Cond`**: điều kiện mà index access method dùng để định vị/giới hạn những index entries cần xét.
- **`Filter`**: điều kiện được đánh giá thêm sau khi các hàng ứng viên được lấy, tùy node plan.
- Nếu có `Rows Removed by Filter` trong `EXPLAIN ANALYZE`, ta biết bao nhiêu hàng đã bị loại ở tầng đó.

Lưu ý có thể thấy một điều kiện trong `Index Cond` nhưng vẫn phải quét nhiều entries nếu index ghép không có điều kiện trên các cột dẫn đầu, hoặc khi dạng phép tìm không thu hẹp nhiều phạm vi. **Có trong Index Cond** không đồng nghĩa mọi hàng không phù hợp đều được tránh đọc với chi phí bằng không.

### 5.1. Cùng WHERE nhưng index khác cho plan khác

Nếu tạo index ghép:

```sql
CREATE INDEX idx_btree250_orders_customer_amount
ON btree250.orders(customer_id, amount_cents);
```

thì:

```sql
WHERE customer_id = 42
  AND amount_cents > 200000
```

có thể được định vị bằng hai thành phần của B-tree: một điều kiện bằng ở cột dẫn đầu, rồi một điều kiện khoảng ở cột tiếp theo.

Ngược lại, index đơn trên customer_id thường phải đọc thêm các hàng ứng viên để kiểm tra điều kiện amount nếu nó không có sẵn trong index.

## 6. Tìm đúng một khóa và tính chọn lọc

Để tìm một đơn theo PRIMARY KEY:

```sql
SELECT *
FROM btree250.orders
WHERE order_id = 10000;
```

Index do PRIMARY KEY tạo ra là unique B-tree trừ khi bạn dùng cấu trúc chuyên biệt khác được hỗ trợ trong mô hình thiết kế. Cùng một `order_id` hợp lệ chỉ xuất hiện tối đa một hàng.

Đối với:

```sql
SELECT *
FROM btree250.orders
WHERE status = 'NEW';
```

dù index B-tree trên status có thể định vị vùng khóa `NEW`, dữ liệu lab có 42.000/60.000 đơn là NEW. Nếu phải đọc gần 70% bảng và cần nhiều cột không có trong index, planner có thể chọn Seq Scan.

### 6.1. Tại sao không nên index mọi cột boolean/trạng thái?

Một cột có ít giá trị khác nhau **không tự động vô dụng để index**, nhưng điều kiện phổ biến có thể trả tỷ lệ quá lớn.

Ví dụ:

- `status='NEW'`: 70% hàng → thường kém chọn lọc.
- `status='CANCELLED'`: 10% hàng → có thể có ích hơn trong một số truy vấn.
- `status='PAID' AND ordered_at >= yesterday`: kết hợp phạm vi thời gian có thể chọn lọc hơn.
- `status='NEW' ORDER BY ordered_at DESC LIMIT 20`: index ghép vẫn có thể rất hữu ích dù status phổ biến, vì chỉ cần các hàng đầu tiên theo thứ tự.

Đánh giá **tập điều kiện, thứ tự và số hàng cần trả**, không chỉ nhìn cardinality của một cột.

## 7. IN (...) và = ANY (...): nhiều giá trị chính xác

Ví dụ lấy đơn của một vài khách:

```sql
SELECT order_id, customer_id, status
FROM btree250.orders
WHERE customer_id IN (10, 42, 77);
```

Hoặc:

```sql
SELECT order_id, customer_id, status
FROM btree250.orders
WHERE customer_id = ANY (ARRAY[10, 42, 77]);
```

PostgreSQL có thể tận dụng B-tree index trên `customer_id` để xử lý các phép tìm bằng nhiều giá trị, tùy kế hoạch và chi phí.

### 7.1. IN không đồng nghĩa một khoảng liên tục

`IN (10, 42, 77)` có ba giá trị rời rạc; nó không phải điều kiện:

```sql
customer_id BETWEEN 10 AND 77
```

Vì BETWEEN sẽ lấy cả hàng có customer_id 11, 12, ... 76, không đúng tập mong muốn.

### 7.2. Danh sách IN rất lớn

Một IN-list chứa hàng nghìn hoặc hàng chục nghìn phần tử có thể khiến query dài, tốn parse/plan hoặc không còn tối ưu. Với tập khóa lớn, cân nhắc:

- Bảng tạm chứa khóa và JOIN.
- `= ANY($1::integer[])` với prepared statement khi phù hợp.
- Batch có giới hạn.
- Đánh giá plan và selectivity.

B-tree vẫn có thể tham gia, nhưng không thể mặc định một IN-list cực lớn sẽ tốt hơn một phép join.

### 7.3. NULL trong IN

`x IN (1, NULL)` tuân thủ logic ba giá trị. Khi không khớp 1, kết quả có thể UNKNOWN, không phải FALSE thông thường. Đặc biệt, `NOT IN` với tập có NULL dễ tạo kết quả không mong đợi.

Muốn kiểm tra hàng NULL rõ ràng, dùng `IS NULL`; muốn anti-join theo tập, cân nhắc `NOT EXISTS` với ngữ nghĩa NULL đã được thiết kế rõ.

## 8. IS NULL và IS NOT NULL trên B-tree

B-tree PostgreSQL có thể lưu những mục khóa có NULL và hỗ trợ việc tìm NULL theo cấu trúc phù hợp.

Ví dụ tạo bảng minh họa có giá trị nullable:

```sql
CREATE TABLE btree250.tasks (
    task_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    completed_at timestamptz
);

INSERT INTO btree250.tasks(title, completed_at)
VALUES
    ('Việc A', NULL),
    ('Việc B', TIMESTAMPTZ '2026-06-01 12:00:00+00'),
    ('Việc C', NULL);
```

Tạo index:

```sql
CREATE INDEX idx_btree250_tasks_completed_at
ON btree250.tasks(completed_at);
```

Hai truy vấn:

```sql
SELECT *
FROM btree250.tasks
WHERE completed_at IS NULL;

SELECT *
FROM btree250.tasks
WHERE completed_at IS NOT NULL;
```

Về khả năng toán tử, B-tree có thể hỗ trợ cả `IS NULL` và `IS NOT NULL`. Nhưng trong bảng lab **chỉ có ba hàng**, Seq Scan thường rẻ hơn.

### 8.1. NULLS FIRST và NULLS LAST

B-tree có thứ tự sắp xếp của NULL. Index tăng dần mặc định thường tương ứng:

```sql
CREATE INDEX ... ON some_table(column ASC NULLS LAST);
```

Quét ngược index có thể phục vụ thứ tự `DESC NULLS FIRST`. Nếu nghiệp vụ muốn `DESC NULLS LAST` hoặc một tổ hợp thứ tự khác, cần cân nhắc index với hướng/NULLS option phù hợp.

### 8.2. IS NULL không giống = NULL

Sai:

```sql
WHERE completed_at = NULL
```

Phép so sánh với NULL thông thường trả UNKNOWN, không phải true cho hàng NULL.

Đúng:

```sql
WHERE completed_at IS NULL
```

Đây là ngữ nghĩa SQL cơ bản, đồng thời ảnh hưởng khả năng biến điều kiện thành index qual.

## 9. Những điều kiện thường không tạo được một phạm vi B-tree hữu ích

### 9.1. Phủ định

Ví dụ:

```sql
WHERE status <> 'PAID'
```

Toán tử `<>`/`!=` không phải một trong các chiến lược so sánh cốt lõi dùng để tìm một khoảng B-tree liên tục. Tập phù hợp có thể lớn, nên planner thường không được lợi nhiều từ một B-tree status đơn.

**Không kết luận tuyệt đối rằng mọi câu có `<>` không bao giờ dùng index**: planner còn có thể dùng index vì điều kiện khác, thứ tự, partial index hoặc cách biến đổi biểu thức. Điều quan trọng là `<>` tự nó thường không hữu ích bằng một điều kiện chọn lọc `=` hoặc range trên khóa.

### 9.2. NOT LIKE và chuỗi chứa ở giữa

```sql
WHERE email NOT LIKE 'user001%'

WHERE email LIKE '%001%'

WHERE email LIKE '%@example.test'
```

Các dạng phủ định hoặc không có tiền tố đầu chuỗi cố định không ánh xạ tự nhiên thành **một khoảng khóa theo thứ tự B-tree văn bản**. Với truy vấn substring thực tế, thường cần đánh giá một phương pháp index khác, chẳng hạn `pg_trgm` với GIN/GiST.

### 9.3. Phép toán không khớp index expression

Có B-tree trên `ordered_at` không có nghĩa query dưới đây tự dùng được cùng index một cách hiệu quả:

```sql
WHERE ordered_at::date = DATE '2026-05-01'
```

Phép cast áp dụng lên cột làm biểu thức tìm kiếm khác `ordered_at` gốc. Với `timestamptz`, còn có vấn đề múi giờ.

Nên ưu tiên lọc bằng khoảng thời gian trên cột gốc:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-05-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-05-02 00:00:00+00'
```

hoặc tạo expression index thích hợp nếu truy vấn cụ thể thực sự cần dạng biểu thức và biểu thức đủ điều kiện lập chỉ mục.

## 10. LIKE tiền tố: khi B-tree có thể giúp tìm chuỗi

B-tree sắp xếp chuỗi theo operator class và collation thích hợp. Một mẫu có **tiền tố đầu chuỗi cố định** cho phép PostgreSQL trong nhiều trường hợp tìm một vùng khóa liên quan.

Ví dụ:

```sql
SELECT customer_id, email
FROM btree250.customers
WHERE email LIKE 'user001%';
```

Trong dữ liệu lab, các email dạng `user00100...user00199` là những ứng viên phù hợp.

### 10.1. Điều kiện cần chú ý: collation

Không nên khẳng định **mọi B-tree text mặc định** đều tối ưu được `LIKE 'abc%'` dưới mọi locale.

Với collation kiểu `C`, thứ tự chuỗi và phép khớp tiền tố thường thuận lợi cho B-tree thông thường. Với nhiều collation không phải C, PostgreSQL cần **pattern operator class** để hỗ trợ tìm theo mẫu tiền tố.

Chẳng hạn:

```sql
CREATE INDEX idx_btree250_customers_email_pattern
ON btree250.customers(email text_pattern_ops);
```

Index này dùng `text_pattern_ops` cho cột text, phục vụ những phép so khớp mẫu tiền tố phù hợp dưới các collation deterministic được hỗ trợ.

Sau đó:

```sql
EXPLAIN
SELECT customer_id, email
FROM btree250.customers
WHERE email LIKE 'user001%';
```

Planner có thể dùng index B-tree pattern với các phép ràng buộc tiền tố phù hợp. Plan có thể chứa các toán tử nội bộ của pattern operator class như `~>=~` và `~<~` bên cạnh bộ lọc LIKE; đừng hiểu chúng là toán tử nghiệp vụ cần tự gõ vào WHERE.

### 10.2. Pattern opclass không thay cho index thứ tự locale ở mọi trường hợp

`text_pattern_ops` sử dụng cách so sánh phù hợp cho pattern matching, có thể khác thứ tự ngôn ngữ mong muốn của `ORDER BY email` theo collation locale.

Nếu workload cần cả:

- tìm `LIKE 'abc%'`;
- so sánh phạm vi hoặc sắp xếp theo thứ tự ngôn ngữ;

thì có thể cần **hai index có opclass/collation khác nhau**, hoặc thiết kế collation nhất quán phù hợp dữ liệu.

Đừng tạo cả hai mặc định trên mọi bảng; đo workload trước.

### 10.3. varchar và char có opclass tương ứng

Các operator classes quen thuộc gồm:

- `text_pattern_ops` cho text.
- `varchar_pattern_ops` cho varchar.
- `bpchar_pattern_ops` cho kiểu char/bpchar tương ứng.

Chọn opclass khớp kiểu cột/biểu thức. Không thay đổi kiểu dữ liệu hoặc operator class tùy tiện chỉ để một ví dụ EXPLAIN dùng index.

## 11. LIKE tiền tố và LIKE chứa chuỗi khác nhau

Bảng so sánh:

| Điều kiện | Ý nghĩa | B-tree thông thường/pattern có thể hữu ích? |
|---|---|---|
| `email = 'user00100@example.test'` | Bằng chính xác | Có, unique B-tree |
| `email LIKE 'user001%'` | Tiền tố cố định | Có thể, nếu collation/opclass phù hợp |
| `email LIKE 'user%'` | Tiền tố quá rộng | Có thể về mặt toán tử, nhưng Seq Scan có thể rẻ hơn |
| `email LIKE '%001'` | Hậu tố | Thường không tạo phạm vi B-tree hữu ích |
| `email LIKE '%001%'` | Chứa chuỗi | Thường không phù hợp B-tree |
| `email LIKE 'u_er001%'` | Có wildcard trong phần đầu | Chỉ có thể tận dụng phần tiền tố chắc chắn trước wildcard, nếu đủ hữu ích |
| `email LIKE 'user001'` | Mẫu không wildcard | Có thể được tối ưu như tìm giá trị cụ thể, tùy kiểu/collation |
| `email ILIKE 'USER001%'` | Không phân biệt hoa thường | Không mặc nhiên tận dụng B-tree text thông thường như LIKE phân biệt hoa thường |

Điểm cần ghi nhớ là **phần tiền tố không chứa wildcard và bảo đảm đúng theo phép so sánh**. Phần tiền tố quá ngắn hoặc khớp phần lớn bảng dù có thể dùng index vẫn không bảo đảm nhanh.

### 11.1. Regular expression có neo đầu chuỗi

Trong những trường hợp phù hợp, PostgreSQL cũng có thể nhận diện tiền tố cố định từ regex phân biệt hoa/thường:

```sql
WHERE email ~ '^user001'
```

Tuy nhiên khả năng suy ra điều kiện index và collation/phép so khớp khác nhau theo mẫu. Với bài toán chỉ cần tiền tố đơn giản, `LIKE 'user001%'` thường dễ đọc và dễ kiểm chứng hơn.

### 11.2. Pattern matching phức tạp: cân nhắc pg_trgm

Nếu nhu cầu chính là:

```sql
WHERE email LIKE '%001%'
```

hoặc `ILIKE` linh hoạt, B-tree không phải cấu trúc chuyên dụng cho tìm substring. PostgreSQL có extension `pg_trgm` và các GIN/GiST operator classes phù hợp:

```sql
-- Chỉ là ví dụ thay thế cần kiểm tra extension/quyền:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_btree250_customers_email_trgm
ON btree250.customers
USING gin (email gin_trgm_ops);
```

Đừng mặc định extension đã được cài hoặc role có quyền cài trên hệ thống thật. Index trigram tạo chi phí lưu trữ/ghi riêng và hiệu quả phụ thuộc mẫu tìm kiếm, độ dài chuỗi và phân bố dữ liệu.

## 12. ILIKE và index trên biểu thức lower(...)

`ILIKE` thực hiện LIKE không phân biệt hoa/thường theo quy tắc phù hợp. Với tiền tố chứa chữ cái, B-tree trên giá trị nguyên bản **không tự chuyển thành** index cho mọi mẫu ILIKE.

Một cách thiết kế là **chuẩn hóa biểu thức ở cả index và query**:

```sql
CREATE INDEX idx_btree250_customers_lower_email_pattern
ON btree250.customers(
    (lower(email)) text_pattern_ops
);
```

Truy vấn:

```sql
SELECT customer_id, email
FROM btree250.customers
WHERE lower(email) LIKE 'user001%';
```

Giá trị được tìm trong index là **`lower(email)`**, đúng biểu thức mà query dùng. PostgreSQL có thể định vị tiền tố phù hợp qua expression index.

### 12.1. Vì sao không chỉ tạo index trên email?

```sql
CREATE INDEX ... ON customers(email);
```

Index trên `email` lưu thứ tự giá trị gốc, không mặc định lưu thứ tự của `lower(email)`. Khi WHERE dùng `lower(email)`, cần index biểu thức tương ứng hoặc một thiết kế khác phù hợp.

### 12.2. Nếu so sánh bằng không phân biệt hoa thường

Có thể dùng:

```sql
WHERE lower(email) = lower('USER00100@EXAMPLE.TEST')
```

với một expression index B-tree trên `lower(email)`. Nếu index `lower(email) text_pattern_ops` được tạo chủ yếu cho LIKE, hãy kiểm tra nó có phục vụ đúng các phép equality/range của workload hay không; có thể cần index riêng cho các phép thứ tự locale.

### 12.3. Unicode và collation

`lower` và các phép so sánh theo locale có các giới hạn/đặc điểm với Unicode, chữ hoa/thường và normalization. Không coi `lower(email)` là giải pháp tổng quát cho mọi yêu cầu **so sánh Unicode bất biến theo ngôn ngữ**.

Với thông tin định danh quan trọng, hệ thống cần một chính sách chuẩn hóa nhất quán, collation phù hợp, quy tắc uniqueness và test theo ngôn ngữ/dữ liệu thực.

## 13. Điều kiện bằng + khoảng với chỉ mục nhiều cột

B-tree index ghép có một **thứ tự các cột**. Ví dụ:

```sql
CREATE INDEX idx_btree250_orders_status_time
ON btree250.orders(status, ordered_at);
```

Khóa index có thể hình dung là các cặp:

```text
(status, ordered_at)

('CANCELLED', t1)
('CANCELLED', t2)
...
('NEW', t1)
('NEW', t2)
...
('PAID', t1)
('PAID', t2)
...
```

Với:

```sql
SELECT order_id, status, ordered_at
FROM btree250.orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-04-01 00:00:00+00';
```

planner có thể tìm vùng khóa:

```text
status = PAID
và ordered_at nằm trong [2026-03-01, 2026-04-01)
```

Đây là mẫu tiêu biểu:

> **Các cột dẫn đầu có equality, cột tiếp theo có range.**

### 13.1. Vì sao equality ở đầu hữu ích?

Nếu cột đầu tiên đã cố định `status='PAID'`, các giá trị `ordered_at` của nhóm đó nằm trong một khoảng có thứ tự trong index ghép. Có thể giới hạn đáng kể phạm vi phải quét.

Nếu chỉ có:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
```

trên index `(status, ordered_at)`, thứ tự toàn cục của index **được chia trước theo status**. Các thời điểm sau ngưỡng nằm rải trong các vùng status khác nhau; index ghép này thường kém trực tiếp hơn index `(ordered_at)` cho truy vấn chỉ lọc thời gian.

### 13.2. Quy tắc leftmost prefix là heuristic, không phải cấm tuyệt đối

Kinh nghiệm thiết kế phổ biến:

- Index `(a, b, c)` có lợi nhất khi điều kiện giới hạn cột `a`.
- Nếu có `a = ?` và `b = ?`, có thể tận dụng nhiều thành phần.
- Nếu có `a = ?` và `b > ?`, thường có thể định vị vùng phù hợp.
- Điều kiện trên `c` sau một cột range có thể được kiểm tra bằng index, nhưng không nhất thiết làm giảm toàn bộ phạm vi cần quét.

**Tuy nhiên:** PostgreSQL có các tối ưu và chiến lược scan khác nhau, bao gồm khả năng **skip scan** trong những phiên bản/tình huống thích hợp. Vì vậy, thiếu điều kiện trên cột đầu không phải bằng chứng rằng index ghép **không bao giờ được dùng**.

Hãy quan sát `EXPLAIN` thay vì biến leftmost prefix thành một lệnh cấm tuyệt đối.

## 14. Nhiều cột: equality, range và điều kiện phía sau

Xét index:

```sql
CREATE INDEX idx_btree250_orders_customer_status_time
ON btree250.orders(
    customer_id,
    status,
    ordered_at
);
```

Truy vấn:

```sql
SELECT order_id, customer_id, status, ordered_at
FROM btree250.orders
WHERE customer_id = 42
  AND status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00';
```

Đây là mẫu tốt vì:

1. `customer_id = 42` giới hạn cột đầu.
2. `status = 'PAID'` giới hạn cột thứ hai.
3. `ordered_at >= ...` giới hạn phạm vi cột thứ ba.

### 14.1. Nếu cột giữa không được cố định?

```sql
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
```

B-tree có thể định vị nhóm `customer_id=42` nhưng thời gian của từng status có thể nằm ở nhiều vùng con. Planner tùy phiên bản/điều kiện có thể áp dụng kiểm tra cột sau, skip scan hoặc chọn index khác.

Không nên tuyên bố điều kiện thời gian bị **bỏ qua hoàn toàn**; đúng hơn là nó không luôn đem lại hiệu quả giới hạn phạm vi tương tự khi các cột đứng trước được cố định bằng equality.

### 14.2. Nếu có range ở cột đầu?

```sql
WHERE customer_id > 100
  AND status = 'PAID'
```

Range của customer_id đã mở ra rất nhiều nhóm customer. Equality ở status có thể lọc những entries phù hợp, nhưng không tự tạo một dải PAID duy nhất trên toàn index. Đôi khi một index `(status, customer_id)` phù hợp hơn nếu query này là đường nóng.

### 14.3. Không chỉ áp dụng quy tắc “cột chọn lọc nhất đứng đầu”

Khi thiết kế index ghép, cân nhắc:

- Equality conditions thật sự xuất hiện trong workload.
- Range conditions.
- `ORDER BY` và `LIMIT`.
- Các query chỉ có một phần điều kiện.
- Tính chọn lọc và số lượng giá trị khác nhau.
- Khả năng index-only scan.
- Các index khác đã tồn tại.
- Thứ tự khóa và chi phí ghi.

Một quy tắc chung “cột nào selectivity cao nhất luôn đứng đầu” là quá đơn giản.

## 15. B-tree và thứ tự ORDER BY

B-tree lưu khóa có thứ tự, nên có thể giúp tránh một bước Sort.

Tạo:

```sql
CREATE INDEX idx_btree250_orders_time_desc
ON btree250.orders(ordered_at DESC);
```

Query:

```sql
SELECT order_id, ordered_at, status
FROM btree250.orders
ORDER BY ordered_at DESC
LIMIT 20;
```

Đây là trường hợp thường rất có lợi: PostgreSQL có thể đọc **20 hàng đầu theo thứ tự index** thay vì quét/sắp xếp toàn bộ 60.000 hàng, nếu plan và visibility/heap access cho phép.

### 15.1. Một index B-tree có thể quét ngược

Một B-tree một cột tăng dần có thể được quét ngược để phục vụ sắp xếp giảm dần:

```sql
CREATE INDEX idx_btree250_orders_time_asc
ON btree250.orders(ordered_at ASC);
```

Vì vậy, không nhất thiết tạo hai index giống nhau chỉ khác ASC/DESC cho **một cột**, trừ khi có lý do cụ thể như NULLS option hoặc workload khác.

### 15.2. NULLS FIRST/LAST ảnh hưởng matching

B-tree mặc định tăng dần thường có `NULLS LAST`; quét ngược cho `DESC NULLS FIRST`.

Nếu query cần:

```sql
ORDER BY completed_at DESC NULLS LAST
```

trên một cột nullable, index thích hợp có thể cần khai báo chiều/NULLS cụ thể. Không suy luận mọi cách sắp xếp NULL đều dùng một index bất kỳ mà không cần Sort.

### 15.3. ORDER BY không có WHERE vẫn có thể dùng index

Một index không chỉ phục vụ WHERE. Query:

```sql
SELECT *
FROM btree250.orders
ORDER BY ordered_at
LIMIT 10;
```

có thể tận dụng B-tree trên `ordered_at`, dù không có điều kiện lọc nào.

### 15.4. ORDER BY toàn bộ bảng

Nếu lấy và trả hầu như mọi hàng, index scan có thể phải truy cập nhiều heap pages. PostgreSQL đôi khi chọn Seq Scan + Sort thay vì đi qua index. Lợi ích của index cho ORDER BY đặc biệt rõ khi có **LIMIT nhỏ** hoặc dữ liệu cần trả đã có trong index.

## 16. ORDER BY nhiều cột: chiều sắp xếp có thể quyết định index

Tạo index:

```sql
CREATE INDEX idx_btree250_orders_status_time_id
ON btree250.orders(
    status ASC,
    ordered_at DESC,
    order_id DESC
);
```

Query:

```sql
SELECT order_id, status, ordered_at
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 25;
```

Vì `status` được cố định bằng equality, thứ tự `ordered_at DESC, order_id DESC` trong vùng PAID khớp thứ tự index. PostgreSQL có thể lấy các hàng gần nhất rồi dừng sớm.

### 16.1. Nếu không có WHERE status?

```sql
SELECT order_id, status, ordered_at
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 25;
```

Index `(status, ordered_at DESC, order_id DESC)` sắp trước theo status. Nó **không** tự cung cấp thứ tự toàn cục theo ordered_at của mọi status. Index `(ordered_at DESC, order_id DESC)` có thể phù hợp hơn.

### 16.2. Thứ tự hỗn hợp ASC/DESC

Index `(a ASC, b ASC)` quét xuôi theo:

```text
a ASC, b ASC
```

và quét ngược theo:

```text
a DESC, b DESC
```

Nhưng query:

```sql
ORDER BY a ASC, b DESC
```

không khớp trực tiếp toàn bộ thứ tự index ấy; có thể cần index khai báo hướng hỗn hợp:

```sql
CREATE INDEX example_mixed_order_idx
ON some_table(a ASC, b DESC);
```

Khi các cột leading đã được cố định equality, một số khác biệt thứ tự trở nên không còn ảnh hưởng tới nhóm được đọc; thiết kế theo **query thực tế**, không chỉ tên index.

## 17. Keyset pagination: B-tree với ORDER BY và so sánh tuple

`OFFSET` lớn có thể khiến PostgreSQL phải đi qua nhiều hàng bị bỏ qua:

```sql
SELECT order_id, ordered_at
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20 OFFSET 40000;
```

Nếu cần phân trang sâu/scroll vô hạn, **keyset pagination** thường phù hợp hơn.

Tạo index:

```sql
CREATE INDEX idx_btree250_orders_time_id_desc
ON btree250.orders(ordered_at DESC, order_id DESC);
```

Trang đầu:

```sql
SELECT order_id, ordered_at, status
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Lưu hai giá trị `ordered_at` và `order_id` của hàng cuối. Trang sau:

```sql
SELECT order_id, ordered_at, status
FROM btree250.orders
WHERE (ordered_at, order_id)
    < (TIMESTAMPTZ '2026-11-01 12:00:00+00', 12345)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Hai giá trị literal ở query trang sau là **ví dụ placeholder**; trong ứng dụng phải truyền giá trị thật của hàng cuối trang trước.

### 17.1. Vì sao dùng cả order_id?

Nếu nhiều đơn có cùng `ordered_at` mà chỉ sắp theo timestamp, thứ tự giữa các hàng trùng thời điểm không ổn định.

Cặp `(ordered_at, order_id)` tạo thứ tự xác định khi `order_id` là khóa duy nhất.

### 17.2. Điều kiện tuple và hướng DESC

Với thứ tự cả hai cột giảm dần, trang sau tương ứng với khóa **nhỏ hơn về thứ tự từ điển** của tuple cuối. PostgreSQL có thể sử dụng B-tree phù hợp cho row comparison với các operator classes tương thích.

Nếu ORDER BY trộn ASC và DESC hoặc có NULL, công thức tuple đơn giản như trên có thể **không đúng**; phải viết điều kiện lexicographic theo từng thành phần và thứ tự NULL thực tế.

### 17.3. Phân trang không tạo snapshot nhất quán vĩnh viễn

Khi các trang được tải qua nhiều request/transaction, dữ liệu có thể được INSERT/DELETE/UPDATE giữa các request. Keyset pagination ổn định hơn OFFSET ở nhiều trường hợp, nhưng không tự bảo đảm danh sách bất biến theo thời gian. Nếu nghiệp vụ cần snapshot cố định, thiết kế transaction/snapshot hoặc mốc dữ liệu thích hợp.

## 18. MIN, MAX, DISTINCT và GROUP BY

B-tree có thứ tự nên có thể hỗ trợ nhiều thao tác không chỉ WHERE.

### 18.1. MIN/MAX

```sql
SELECT MIN(ordered_at)
FROM btree250.orders;

SELECT MAX(ordered_at)
FROM btree250.orders;
```

Nếu có B-tree phù hợp, PostgreSQL đôi khi có thể tối ưu MIN/MAX bằng cách đọc đầu/cuối dải khóa thay vì quét toàn bảng. Không bảo đảm mọi phép MIN/MAX biểu thức đều có tối ưu đó.

### 18.2. DISTINCT

```sql
SELECT DISTINCT customer_id
FROM btree250.orders
ORDER BY customer_id;
```

Index trên `customer_id` có thể cung cấp đầu vào theo thứ tự, giúp một số kế hoạch DISTINCT/Unique. Nhưng nếu có nhiều trùng lặp hoặc phần lớn bảng phải đọc, hash aggregation hoặc Seq Scan vẫn có thể rẻ hơn.

### 18.3. GROUP BY

```sql
SELECT customer_id, COUNT(*) AS orders_count
FROM btree250.orders
GROUP BY customer_id
ORDER BY customer_id;
```

Planner có thể sử dụng order index cho `GroupAggregate` hoặc chọn `HashAggregate` tùy chi phí.

**Đừng tạo index chỉ vì SQL chứa GROUP BY**. Cần kiểm tra lượng dữ liệu, tập nhóm, query cạnh tranh và các plan được chọn.

### 18.4. Merge Join và Nested Loop

B-tree có thể giúp:

- Nested Loop khi bảng bên ngoài cho một khóa và bảng bên trong có index tìm nhanh.
- Merge Join khi hai phía được sắp theo khóa join, đôi khi tận dụng index order.
- Các phương án join khác có thể rẻ hơn khi dữ liệu lớn, ví dụ Hash Join.

Chỉ mục phù hợp không bắt planner buộc dùng Index Scan hoặc Merge Join.

## 19. B-tree và các kiểu dữ liệu

B-tree không chỉ dành cho số nguyên.

Các kiểu thường có operator classes B-tree thích hợp:

- Integer/bigint và nhiều kiểu số.
- `numeric`.
- `date`, `timestamp`, `timestamptz`.
- Text, varchar và một số kiểu chuỗi.
- Boolean.
- UUID.
- Một số kiểu mạng, enum và kiểu khác khi có operator class hỗ trợ.

Ví dụ:

```sql
CREATE INDEX idx_btree250_orders_amount
ON btree250.orders(amount_cents);

CREATE INDEX idx_btree250_orders_status
ON btree250.orders(status);
```

Tuy nhiên, các kiểu phức tạp như JSONB, mảng, dữ liệu không gian hay tìm kiếm văn bản toàn văn thường có những toán tử và mô hình truy vấn mà **GIN/GiST/SP-GiST/BRIN** hoặc giải pháp khác phù hợp hơn.

### 19.1. Kiểu dữ liệu và implicit casts

Giả sử `customer_id` là integer. Truy vấn:

```sql
WHERE customer_id = '42'
```

PostgreSQL có thể suy luận kiểu constant phù hợp trong nhiều trường hợp. Nhưng nếu application ép cột theo kiểu khác:

```sql
WHERE customer_id::text = '42'
```

thì biểu thức index trên `customer_id` nguyên bản **không nhất thiết khớp**.

Khi thiết kế prepared statement, truyền tham số đúng kiểu, tránh ép cột trong WHERE nếu không cần.

### 19.2. So sánh timezone

Cột `timestamptz` biểu diễn mốc thời gian; literal có offset rõ ràng giúp xác định khoảng tìm kiếm độc lập với timezone của session:

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-05-01 00:00:00+00'
```

Nếu ứng dụng cần “ngày lịch theo Việt Nam”, phải tính đúng biên ngày trong múi giờ nghiệp vụ và chuyển thành các mốc `timestamptz`. Không tự đổi `ordered_at::date` rồi mặc định vừa đúng timezone vừa sử dụng index tối ưu.

## 20. Expression index: khi WHERE dùng hàm hoặc biểu thức

Một index thường:

```sql
CREATE INDEX idx_btree250_customers_email
ON btree250.customers(email);
```

lưu khóa `email`. Nếu query luôn dùng:

```sql
WHERE lower(email) = 'user00100@example.test'
```

cần xem xét index theo **cùng biểu thức**:

```sql
CREATE INDEX idx_btree250_customers_lower_email
ON btree250.customers(lower(email));
```

Bây giờ biểu thức `lower(email)` có thể được tìm theo B-tree.

### 20.1. Expression phải khớp ngữ nghĩa

Index `lower(email)` không phải index cho mọi hàm của email:

```sql
WHERE upper(email) = 'USER00100@EXAMPLE.TEST'
```

Truy vấn này dùng biểu thức khác; không tự giả định nó được tối ưu qua index lower(email).

### 20.2. Không phải mọi biểu thức đều lập index được

Hàm được dùng trong index expression cần đáp ứng quy tắc immutability và những yêu cầu khác của PostgreSQL.

Ví dụ với `timestamptz`, cast trực tiếp thành `date` phụ thuộc timezone của session, nên một expression index như:

```sql
-- Không nên giả định câu này được phép/có ngữ nghĩa ổn định:
CREATE INDEX ...
ON some_table((timestamptz_column::date));
```

có thể bị PostgreSQL từ chối do biểu thức không immutable.

Thay vì tìm mẹo để qua lỗi, hãy làm rõ timezone nghiệp vụ, chuyển đổi biểu thức theo cách được hỗ trợ/ổn định và xác minh trên phiên bản server mục tiêu.

### 20.3. Chi phí expression index

Mỗi khi INSERT hoặc UPDATE các cột liên quan, PostgreSQL có thể phải tính biểu thức và duy trì index. Với nhiều expression indexes, chi phí ghi tăng lên. Chỉ tạo khi query quan trọng thực sự được hưởng lợi.

## 21. Partial B-tree index: lập chỉ mục một tập con

Nếu đa số đơn ở trạng thái NEW nhưng hệ thống thường tìm **đơn PAID gần đây**, có thể thử:

```sql
CREATE INDEX idx_btree250_orders_paid_time
ON btree250.orders(ordered_at DESC, order_id DESC)
WHERE status = 'PAID';
```

Truy vấn:

```sql
SELECT order_id, ordered_at, amount_cents
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Index chỉ chứa những hàng thỏa predicate `status='PAID'`, vì vậy có thể nhỏ hơn một index thời gian cho mọi trạng thái.

### 21.1. Planner phải chứng minh WHERE của query hàm ý predicate

Một partial index chỉ hợp lệ cho query khi PostgreSQL biết các hàng cần lấy chắc chắn nằm trong tập được index.

Ví dụ:

```sql
WHERE status = 'PAID'
```

có thể hàm ý predicate `status='PAID'` một cách rõ ràng.

Nhưng:

```sql
WHERE status = $1
```

với một prepared statement dùng **generic plan** không nhất thiết hàm ý `status='PAID'` cho mọi giá trị tham số. Partial index có thể không được chọn ngay cả khi lần chạy hiện tại truyền 'PAID'.

### 21.2. Đừng viết predicate “gần đây” dựa trên now() trong index

Một partial index với điều kiện động kiểu:

```sql
-- Không phải một predicate index hợp lệ để tự trôi theo thời gian:
CREATE INDEX ...
ON some_table(ordered_at)
WHERE ordered_at > now() - INTERVAL '7 days';
```

Predicate index cần biểu thức đáp ứng yêu cầu immutability; `now()` là giá trị thay đổi theo thời gian. Hơn nữa, một tập index không tự “dịch cửa sổ 7 ngày” theo đồng hồ nếu dữ liệu không được bảo trì.

Có thể dùng predicate theo trạng thái ổn định, mốc cố định được quản lý theo quy trình, partition theo thời gian hoặc index phù hợp với range query trên cột thời gian.

### 21.3. Partial index không thay thế composite index trong mọi query

Nếu query đôi khi lấy mọi trạng thái, index chỉ cho PAID sẽ không đủ. Cần phân tích những đường truy cập chủ chốt trước khi thiết kế nhiều partial indexes.

## 22. INCLUDE và covering index

PostgreSQL hỗ trợ `INCLUDE` để lưu những cột **payload** trong index mà không đưa chúng thành khóa sắp xếp chính.

Ví dụ:

```sql
CREATE INDEX idx_btree250_orders_paid_lookup_cover
ON btree250.orders(
    status,
    ordered_at DESC,
    order_id DESC
)
INCLUDE (customer_id, amount_cents);
```

Truy vấn:

```sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    amount_cents
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Các cột cần trả đều có mặt trong index này. PostgreSQL **có thể** chọn `Index Only Scan` khi các điều kiện thích hợp.

### 22.1. INCLUDE không làm cột payload thành khóa tìm kiếm

Ở index trên:

- `status`, `ordered_at`, `order_id` là **key columns**.
- `customer_id`, `amount_cents` là **INCLUDE columns**.

Điều kiện:

```sql
WHERE customer_id = 42
```

không tự biến `customer_id` được INCLUDE thành một điều kiện dẫn đường B-tree giống khi nó là **key column**.

INCLUDE giúp index có đủ dữ liệu để trả/kiểm tra thêm trong một số kế hoạch; nó không thay thế việc chọn khóa index cho WHERE/ORDER BY.

### 22.2. Index Only Scan vẫn có thể đọc heap

Do MVCC, PostgreSQL phải biết phiên bản hàng có thể nhìn thấy theo snapshot. `Index Only Scan` thường dựa vào **visibility map** để tránh truy cập heap cho các trang đã được đánh dấu all-visible.

Nếu những trang heap chưa all-visible (ví dụ vừa có nhiều UPDATE), query có thể phải thực hiện **Heap Fetches** dù tên plan là Index Only Scan.

Đọc:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, ordered_at, amount_cents
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

và xem `Heap Fetches` khi plan dùng Index Only Scan.

### 22.3. INCLUDE cũng có giá

Cột payload làm index lớn hơn, tăng chi phí ghi và có thể hạn chế một số tối ưu nội bộ (ví dụ B-tree deduplication ở index có INCLUDE). Không thêm mọi cột SELECT vào INCLUDE một cách vô hạn.

### 22.4. UNIQUE và INCLUDE

Ở unique index có INCLUDE, tính duy nhất áp dụng cho **các key columns**, không phải payload được INCLUDE. Điều này hữu ích khi muốn bảo vệ unique key nhưng vẫn lưu thêm cột phục vụ đọc.

## 23. Unique B-tree và NULL

PRIMARY KEY và UNIQUE constraints thường được bảo vệ bằng unique B-tree index.

Ví dụ bảng customers:

```sql
email text NOT NULL UNIQUE
```

PostgreSQL tạo index để kiểm tra email không trùng. Query:

```sql
SELECT customer_id
FROM btree250.customers
WHERE email = 'user00100@example.test';
```

có thể dùng index phục vụ cả tính đúng và hiệu năng.

### 23.1. NULL trong unique index

Theo hành vi phổ biến của PostgreSQL, unique index thông thường cho phép nhiều giá trị NULL bởi vì NULL không được xem là bằng nhau cho quy tắc unique mặc định.

Các phiên bản PostgreSQL hiện đại có tùy chọn `NULLS NOT DISTINCT` khi muốn coi NULL là trùng nhau trong unique index/constraint:

```sql
CREATE TABLE btree250.unique_example (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code text,
    UNIQUE NULLS NOT DISTINCT (external_code)
);
```

Khi dùng tùy chọn này, nhiều hàng có `external_code=NULL` sẽ xung đột tính duy nhất.

**Lưu ý:** hỗ trợ cụ thể cần kiểm tra phiên bản server. Chỉ mục unique và `IS NULL` phục vụ hai mục đích khác nhau: bảo vệ quy tắc dữ liệu và tìm kiếm.

### 23.2. Operator class/collation và uniqueness

Với text, định nghĩa “hai chuỗi có bằng nhau hay không” có thể chịu ảnh hưởng collation và các lựa chọn biểu thức/kiểu dữ liệu. Khi thiết kế email/username unique không phân biệt hoa thường, cân nhắc expression unique index trên giá trị chuẩn hóa hoặc cơ chế phù hợp.

Không cho rằng một index `text_pattern_ops` tự định nghĩa đúng mọi quy tắc uniqueness phân biệt/không phân biệt chữ của ứng dụng.

## 24. B-tree không tương đương GIN, GiST hoặc BRIN

| Phương pháp index | Thường phù hợp với |
|---|---|
| **B-tree** | `=`, phạm vi có thứ tự, ORDER BY, LIMIT, equality/range theo khóa |
| Hash | Equality theo operator class phù hợp; không hỗ trợ sắp thứ tự/range như B-tree |
| GIN | Giá trị có nhiều thành phần, arrays, JSONB, full-text, trigram |
| GiST | Các toán tử/cấu trúc phù hợp như không gian, range, trigram hoặc ứng dụng chuyên biệt |
| SP-GiST | Một số cấu trúc phân hoạch không gian/khóa chuyên biệt |
| BRIN | Dữ liệu rất lớn có tương quan vật lý theo block range, ví dụ timestamp tăng dần trong append-only logs |

Cần chọn theo **toán tử và phân bố dữ liệu**. Ví dụ:

```sql
WHERE jsonb_column @> '{"type":"paid"}'
```

thường gợi ý xem xét operator class GIN phù hợp hơn là mặc định tạo B-tree trên JSONB để tìm điều kiện containment.

Tương tự, `LIKE '%chuoi%'` có thể phù hợp trigram hơn B-tree.

B-tree vẫn có thể hợp lý để lập chỉ mục một **biểu thức trích giá trị scalar** từ JSONB nếu query luôn so sánh giá trị ấy bằng/range và expression được hỗ trợ, ví dụ index trên `(payload->>'customer_id')` với kiểu/biểu thức phù hợp.

## 25. OR, AND và Bitmap Index Scan

PostgreSQL có thể kết hợp nhiều index.

Ví dụ có hai index:

```sql
CREATE INDEX idx_btree250_orders_customer_only
ON btree250.orders(customer_id);

CREATE INDEX idx_btree250_orders_status_only
ON btree250.orders(status);
```

Query:

```sql
SELECT order_id, customer_id, status
FROM btree250.orders
WHERE customer_id = 42
   OR status = 'CANCELLED';
```

Planner có thể dùng bitmap operations:

```text
BitmapOr
  Bitmap Index Scan trên customer_id
  Bitmap Index Scan trên status
    |
Bitmap Heap Scan
```

Với AND của hai điều kiện tương ứng, planner có thể cân nhắc `BitmapAnd`.

### 25.1. Bitmap scan là gì?

Một `Bitmap Index Scan` lấy danh sách/vị trí các heap rows ứng viên dưới dạng bitmap, sau đó `Bitmap Heap Scan` đọc heap theo kế hoạch phù hợp. Cách này có thể giảm random I/O khi nhiều hàng nằm trong một số trang.

Tuy nhiên, **Bitmap Heap Scan thường không giữ thứ tự B-tree của các hàng**. Nếu query có ORDER BY, planner có thể cần Sort thêm.

### 25.2. OR không bắt buộc dùng BitmapOr

Nếu một nhánh của OR trả quá nhiều hàng, Seq Scan có thể rẻ hơn. Nếu có composite index khác, planner có thể chọn kế hoạch không dùng bitmap.

`EXPLAIN` mới cho biết kế hoạch thực sự.

### 25.3. Không lạm dụng OR thay IN

Với nhiều phép bằng trên cùng cột:

```sql
WHERE customer_id = 1
   OR customer_id = 2
   OR customer_id = 3
```

thường có thể viết dễ hiểu hơn:

```sql
WHERE customer_id IN (1, 2, 3)
```

Planner có thể tối ưu cả hai, nhưng cú pháp IN diễn đạt rõ tập các giá trị cùng khóa.

## 26. Chỉ mục ghép hay nhiều chỉ mục đơn?

Ví dụ workload:

```sql
SELECT order_id, ordered_at
FROM btree250.orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY ordered_at DESC
LIMIT 10;
```

Hai lựa chọn:

**A — Nhiều index đơn:**

```sql
CREATE INDEX ... ON orders(customer_id);
CREATE INDEX ... ON orders(status);
CREATE INDEX ... ON orders(ordered_at);
```

**B — Một index ghép phù hợp:**

```sql
CREATE INDEX idx_btree250_customer_status_time
ON btree250.orders(
    customer_id,
    status,
    ordered_at DESC
);
```

Index ghép có thể giới hạn đúng customer, đúng status và cung cấp thứ tự thời gian để lấy 10 hàng gần nhất.

### 26.1. Index ghép không tự thay mọi index đơn

Nếu ứng dụng cũng có query chủ đạo:

```sql
WHERE status = 'PAID'
ORDER BY ordered_at DESC
LIMIT 100
```

index `(customer_id,status,ordered_at)` không phải lựa chọn tối ưu mặc định, vì `customer_id` không được cố định. Có thể cần index `(status,ordered_at DESC)`.

Tương tự, nếu chỉ truy vấn:

```sql
WHERE ordered_at >= ...
```

có thể cần index `(ordered_at)`.

### 26.2. Không tạo index trùng lặp không cần thiết

Nếu có index `(customer_id,status,ordered_at)`, một index đơn `(customer_id)` có thể **đôi khi** thừa đối với một số truy vấn equality theo customer. Nhưng không tự động xóa: index đơn nhỏ hơn có thể rẻ hơn cho workload riêng; cần đo truy vấn và ảnh hưởng ghi.

Hãy quản lý index như một phần thiết kế hệ thống, không chỉ thêm index khi thấy query chậm rồi bỏ quên.

## 27. Index-only scan và MVCC: chọn cột chưa đủ

Một câu query có thể chỉ đọc cột nằm trong index nhưng vẫn chọn Index Scan/Seq Scan hoặc phải đọc heap.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, status, ordered_at, order_id
FROM btree250.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 15;
```

Nếu có index đủ cột, planner **có thể** chọn Index Only Scan. Nhưng hai điều kiện quan trọng:

1. Các cột/biểu thức cần được đọc có thể được phục vụ từ index.
2. Kiểm tra visibility theo snapshot có thể tránh heap ở những trang all-visible, hoặc phát sinh Heap Fetches nếu cần.

### 27.1. VACUUM giúp gì?

VACUUM có vai trò quản lý phiên bản hàng chết và visibility map. Một bảng đọc nhiều, thay đổi ít có thể cho index-only scans hiệu quả hơn một bảng UPDATE liên tục.

Không gọi VACUUM chỉ để ép plan trên production mà không hiểu workload/autovacuum, quyền và tác động vận hành.

### 27.2. Index-only scan không phải “không hề đụng bảng”

Trong `EXPLAIN ANALYZE`, `Heap Fetches` có thể khác 0. Tên node diễn tả **khả năng** truy cập cột từ index, không phải lời hứa mọi lần thực thi không bao giờ đọc heap.

## 28. Index selectivity, statistics và planner

PostgreSQL sử dụng thống kê để ước lượng số hàng ứng với điều kiện WHERE.

Xem thống kê đã thu thập:

```sql
SELECT
    schemaname,
    tablename,
    attname,
    n_distinct,
    null_frac,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'btree250'
  AND tablename = 'orders'
  AND attname IN ('customer_id','status','ordered_at');
```

Ý nghĩa:

- `n_distinct`: thông tin ước lượng độ đa dạng giá trị.
- `null_frac`: tỷ lệ NULL.
- `most_common_vals` và `most_common_freqs`: các giá trị phổ biến/tần suất nếu thống kê lưu.
- Histogram và correlation cũng ảnh hưởng cách planner ước lượng các khoảng và truy cập vật lý.

### 28.1. Ước lượng sai dẫn đến chọn plan chưa tốt

Nếu dữ liệu thay đổi nhiều hoặc phân bố có tương quan phức tạp, planner có thể ước lượng số hàng không sát thực tế.

Ví dụ:

```sql
WHERE status='PAID'
  AND ordered_at >= ...
```

nếu trạng thái PAID chỉ xuất hiện ở những tháng gần đây nhưng thống kê được giả định độc lập, ước lượng kết hợp có thể không chính xác. PostgreSQL có **extended statistics** cho một số trường hợp tương quan, chẳng hạn dependencies/MCV trên nhiều cột.

### 28.2. Extended statistics là một công cụ bổ sung

Ví dụ trong lab:

```sql
CREATE STATISTICS stats_btree250_status_customer
    (dependencies, mcv)
ON status, customer_id
FROM btree250.orders;

ANALYZE btree250.orders;
```

Không phải lúc nào tạo extended statistics cũng cải thiện mọi query; cần kiểm tra dữ liệu/correlation và plan.

### 28.3. Không ép planner dùng index quá sớm

Có thể điều chỉnh cờ planner trong session lab như `enable_seqscan` để so sánh chi phí, nhưng không nên sửa tham số toàn production như cách “chữa query” lâu dài.

Nguyên nhân thật có thể là:

- Index không phù hợp WHERE/ORDER BY.
- Selectivity thấp.
- Statistics cũ.
- Cột bị ép kiểu/hàm không khớp index.
- Query trả nhiều cột khiến heap access tốn chi phí.
- Bảng quá nhỏ để index có lợi.

## 29. Đọc EXPLAIN: các node quen thuộc

| Node/thuộc tính | Ý nghĩa |
|---|---|
| `Seq Scan` | Đọc bảng tuần tự |
| `Index Scan` | Dùng index định vị và thường đọc heap |
| `Index Only Scan` | Có thể lấy cột từ index; kiểm tra visibility có thể đọc heap |
| `Bitmap Index Scan` | Tạo bitmap các hàng phù hợp từ index |
| `Bitmap Heap Scan` | Đọc heap theo bitmap |
| `BitmapAnd` / `BitmapOr` | Kết hợp bitmap từ nhiều nguồn |
| `Sort` | Sắp xếp các hàng đầu vào |
| `Incremental Sort` | Tận dụng thứ tự một phần trong một số kế hoạch |
| `Index Cond` | Điều kiện được đưa vào thao tác tìm trên index |
| `Filter` | Điều kiện lọc thêm ở node hiện tại |
| `Recheck Cond` | Điều kiện được kiểm tra lại khi cần ở bitmap/heap |
| `Rows Removed by Filter` | Số hàng loại bởi filter tại node khi dùng ANALYZE |
| `Heap Fetches` | Lần truy cập heap để kiểm tra visibility trong Index Only Scan |
| `actual time`, `rows`, `loops` | Kết quả thực tế từ EXPLAIN ANALYZE |
| `Buffers` | Thông tin block hit/read/write và liên quan |

### 29.1. EXPLAIN và EXPLAIN ANALYZE khác nhau

```sql
EXPLAIN
SELECT *
FROM btree250.orders
WHERE customer_id = 42;
```

Chỉ dựng kế hoạch ước lượng, **không thực thi SELECT để đo thời gian thực**.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM btree250.orders
WHERE customer_id = 42;
```

**Thực thi SELECT** và báo số hàng/timing/buffers thực tế.

Cẩn trọng: `EXPLAIN ANALYZE` với `UPDATE/DELETE/INSERT` **thực sự thực thi DML**; dùng transaction rollback có chủ ý hoặc chỉ thực hiện trong môi trường lab, không chạy tùy tiện trên production.

### 29.2. Ước lượng rows so với actual rows

Ví dụ minh họa:

```text
Index Scan ...
  (cost=... rows=10 ...)
  (actual ... rows=30 loops=1)
```

Planner đoán 10 hàng nhưng thực tế 30. Nếu sai lệch lớn trên query quan trọng, có thể cần xem stats, correlated predicates, parameterization hoặc thiết kế index.

### 29.3. Đừng tối ưu chỉ bằng việc thấy chữ Index Scan

Một index scan có thể chậm hơn seq scan nếu phải đọc rất nhiều heap pages. Hiệu năng cần đo bằng latency, I/O, buffers, memory, throughput và tải đồng thời theo workload thực tế.

## 30. Thực hành so sánh các dạng điều kiện

Chạy từng câu `EXPLAIN` khi đã tạo dữ liệu và index thích hợp.

### 30.1. Equality

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM btree250.orders
WHERE customer_id = 42;
```

Xem planner chọn Index Scan, Bitmap scan hay Seq Scan, và số hàng thực tế.

### 30.2. Range

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at
FROM btree250.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-03 00:00:00+00';
```

Nếu có index `ordered_at`, đây là điều kiện khoảng phù hợp.

### 30.3. IN-list

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id
FROM btree250.orders
WHERE customer_id IN (42, 100, 999);
```

Xem có thể sử dụng index trên customer_id như thế nào.

### 30.4. ORDER BY LIMIT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 10;
```

Kiểm tra index tương ứng có giúp tránh Sort toàn bảng không.

### 30.5. LIKE tiền tố

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, email
FROM btree250.customers
WHERE email LIKE 'user001%';
```

Đối chiếu trước/sau khi có `text_pattern_ops` trong môi trường collation thích hợp.

### 30.6. LIKE chứa

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, email
FROM btree250.customers
WHERE email LIKE '%001%';
```

Không mặc định B-tree thường giúp nhiều cho mẫu này. Có thể so sánh thêm phương án trigram nếu lab cho phép cài extension.

### 30.7. Hàm trên cột

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, email
FROM btree250.customers
WHERE lower(email) LIKE 'user001%';
```

Nếu có expression index phù hợp trên `lower(email) text_pattern_ops`, planner có thêm lựa chọn.

## 31. Khi index được tạo nhưng vẫn không dùng

Một trong những câu hỏi phổ biến nhất:

> “Tôi vừa CREATE INDEX xong, tại sao EXPLAIN vẫn là Seq Scan?”

Các nguyên nhân thường gặp:

### 31.1. Bảng quá nhỏ

Với bảng 3–10 hàng, đọc tuần tự ít page có thể rẻ hơn tìm qua index rồi đọc heap.

### 31.2. Truy vấn trả phần lớn bảng

`status = 'NEW'` chiếm 70% dữ liệu lab. Index ít chọn lọc có thể tốn random access hơn.

### 31.3. Index sai thứ tự cột

Có index `(status,ordered_at)` nhưng query chỉ lọc `ordered_at`; index này không luôn là lựa chọn tốt.

### 31.4. Biểu thức không khớp

Có index `email` nhưng query `lower(email)`, hoặc có index `ordered_at` nhưng query `ordered_at::date`.

### 31.5. LIKE không có tiền tố cố định

`LIKE '%abc%'` không được chuyển đơn giản thành khoảng liên tục của B-tree.

### 31.6. Collation/opclass không tương thích

Một index text thông thường theo locale có thể không hỗ trợ phép tìm LIKE tiền tố như kỳ vọng; pattern operator class hoặc collation phù hợp là yếu tố quyết định.

### 31.7. Thống kê chưa đủ hoặc cũ

Planner ước lượng sai số hàng. Trong lab có thể ANALYZE, trong production xem autovacuum/statistics.

### 31.8. Query cần nhiều cột ngoài index

Index Scan phải đọc heap nhiều lần. Nếu điều kiện trả nhiều hàng, Seq Scan có thể rẻ hơn.

### 31.9. Partial index không được chứng minh áp dụng

Predicate index là `status='PAID'` nhưng generic plan với `status=$1` không biết giá trị chắc chắn là PAID.

### 31.10. Có index khác tốt hơn

PostgreSQL chọn một kế hoạch từ nhiều index và chiến lược. Index bạn mới tạo có thể không phải phương án rẻ nhất.

**Cách xử lý:** xem `EXPLAIN (ANALYZE, BUFFERS)`, stats, operator class, index definition và số hàng được chọn; không ép index theo cảm tính.

## 32. Chi phí duy trì B-tree khi ghi dữ liệu

Chỉ mục không miễn phí.

Khi INSERT:

- PostgreSQL ghi hàng mới vào heap.
- Những B-tree indexes liên quan phải được cập nhật với khóa mới.

Khi UPDATE:

- Tùy cột thay đổi và HOT update có thể sử dụng hay không, các index có thể cần duy trì.
- Index trên cột thường xuyên sửa gây thêm công việc và WAL.
- Index lớn có thể làm tăng đọc/ghi page và lưu trữ.

Khi DELETE:

- Hàng trở thành phiên bản không còn hợp lệ theo MVCC; việc dọn dẹp/giải phóng tài nguyên index liên quan tới VACUUM và cơ chế bảo trì PostgreSQL.
- Không suy luận xóa một hàng lập tức làm kích thước file index giảm tương ứng.

### 32.1. Index bloat và bảo trì

Với bảng churn cao, index có thể phình to. PostgreSQL có nhiều cơ chế tái sử dụng trang, VACUUM và các lựa chọn `REINDEX` khi thực sự cần.

Không chạy `REINDEX` hàng loạt trên production khi chưa có quan sát và kế hoạch vì có thể gây khóa/tốn tài nguyên tùy phương thức.

### 32.2. CREATE INDEX CONCURRENTLY

Trên bảng đang có traffic ghi, `CREATE INDEX CONCURRENTLY` có thể giảm mức chặn DML so với tạo index thông thường, nhưng:

- Tốn nhiều giai đoạn/quét và thời gian.
- Có các hạn chế (ví dụ không chạy trong một transaction block thông thường).
- Có thể để lại index chưa valid nếu thất bại, cần xử lý theo tài liệu.
- Không thay thế đánh giá dung lượng, lock và thời gian triển khai.

Ví dụ chỉ để tham khảo vận hành:

```sql
CREATE INDEX CONCURRENTLY idx_btree250_orders_ref
ON btree250.orders(reference_code);
```

Trong lab đã có dữ liệu, cú pháp hợp lệ khi chạy riêng ngoài explicit transaction. Với production cần review kế hoạch và quyền.

## 33. Kiểm tra những index đang tồn tại

Trong psql:

```text
\d+ btree250.orders
\d+ btree250.customers
```

Trong SQL:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'btree250'
ORDER BY tablename, indexname;
```

Xem kích thước index:

```sql
SELECT
    indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'btree250'
ORDER BY relname, indexrelname;
```

### 33.1. Giải thích thống kê index usage

- `idx_scan`: số lần index được sử dụng trong các lần scan theo thống kê đã thu thập.
- `idx_tup_read`: số index entries được đọc/trả theo các lần scan.
- `idx_tup_fetch`: số heap tuples được lấy theo các đường thực thi liên quan; không được suy luận đơn giản một-một với `idx_tup_read` trong mọi dạng scan.

Thống kê có thời điểm reset, phụ thuộc uptime/monitoring. **`idx_scan = 0` chưa đủ để xóa index** nếu workload chưa chạy đầy đủ hoặc index bảo vệ UNIQUE/PK/constraint quan trọng.

### 33.2. Kiểm tra index hợp lệ

Nếu có deployment tạo index concurrently gặp lỗi, cần xác định index đã valid hay chưa. Có thể xem catalog `pg_index.indisvalid` và định nghĩa qua `pg_get_indexdef`, hoặc dùng công cụ quản trị tương ứng. Không dựa vào sự tồn tại tên index trong catalog để khẳng định planner sẽ sử dụng được nó.

## 34. Bài tập thực hành có lời giải

Các bài dùng schema `btree250`. Khi một bài yêu cầu tạo index trùng ý nghĩa bài trước, đừng chạy lại cùng tên; có thể dùng một lab/schema mới hoặc đọc định nghĩa index hiện tại trước.

### Bài 1. B-tree mặc định của CREATE INDEX là gì?

```sql
CREATE INDEX idx_btree250_orders_customer_demo
ON btree250.orders(customer_id);
```

**Đáp án:** PostgreSQL dùng phương pháp **B-tree** khi không ghi `USING ...`.

### Bài 2. Viết phép tìm chính xác theo order_id

```sql
SELECT *
FROM btree250.orders
WHERE order_id = 12345;
```

**Giải thích:** khóa chính đã có B-tree unique; điều kiện bằng là dạng phù hợp.

### Bài 3. Lọc đơn trong tháng 4 UTC

```sql
SELECT order_id, ordered_at
FROM btree250.orders
WHERE ordered_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND ordered_at < TIMESTAMPTZ '2026-05-01 00:00:00+00';
```

**Giải thích:** khoảng nửa mở, có thể tận dụng B-tree ordered_at.

### Bài 4. Vì sao BETWEEN không phù hợp để chọn một ngày timestamp bằng hai đầu midnight?

**Đáp án:** BETWEEN bao gồm hai đầu. Nếu dùng BETWEEN 00:00 ngày 1 và 00:00 ngày 2, nó có thể bao gồm chính mốc bắt đầu ngày 2. Cách nửa mở `>= start AND < next_start` rõ hơn.

### Bài 5. IN (10,20,30) có tương đương BETWEEN 10 AND 30 không?

**Đáp án:** không. IN chọn ba giá trị, BETWEEN chọn mọi giá trị trong khoảng.

### Bài 6. Tìm tất cả task chưa hoàn tất

```sql
SELECT task_id, title
FROM btree250.tasks
WHERE completed_at IS NULL;
```

**Giải thích:** dùng IS NULL, không dùng `= NULL`; B-tree có thể hỗ trợ nhưng bảng nhỏ có thể Seq Scan.

### Bài 7. Vì sao status='NEW' có index mà planner vẫn chọn Seq Scan?

**Đáp án:** trong fixture 70% đơn NEW, index kém chọn lọc; đọc tuần tự có thể rẻ hơn nhiều heap fetches.

### Bài 8. Viết mẫu LIKE có thể tối ưu theo tiền tố

```sql
SELECT email
FROM btree250.customers
WHERE email LIKE 'user001%';
```

**Đáp án:** mẫu có tiền tố xác định; với collation/operator class phù hợp, B-tree pattern có thể hỗ trợ.

### Bài 9. LIKE '%001%' có dùng B-tree theo một dải khóa rõ ràng không?

**Đáp án:** thông thường không, vì không có tiền tố đầu chuỗi cố định. Cân nhắc trigram nếu workload là tìm substring.

### Bài 10. Dùng ILIKE cho prefix phải lưu ý gì?

**Đáp án:** B-tree text thông thường không tự hỗ trợ mọi tìm kiếm không phân biệt hoa thường. Có thể index `lower(email) text_pattern_ops` và viết query `lower(email) LIKE 'user001%'`, hoặc dùng phương án phù hợp khác.

### Bài 11. Chỉ mục (status,ordered_at) tốt cho WHERE nào?

```sql
WHERE status='PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-04-01 00:00+00'
```

**Giải thích:** equality ở cột dẫn đầu, range ở cột tiếp theo.

### Bài 12. Chỉ có WHERE ordered_at thì index (status,ordered_at) chắc chắn vô dụng?

**Đáp án:** không khẳng định tuyệt đối. Nó thường kém thuận lợi hơn index ordered_at cho đường truy cập này, nhưng planner có thể dùng các chiến lược khác/skip scan ở trường hợp thích hợp.

### Bài 13. Chọn index cho PAID mới nhất

```sql
CREATE INDEX idx_btree250_paid_recent_demo
ON btree250.orders(
    status,
    ordered_at DESC,
    order_id DESC
);
```

Truy vấn:

```sql
SELECT order_id, ordered_at
FROM btree250.orders
WHERE status='PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 10;
```

**Đáp án:** index có equality trên status và cung cấp thứ tự thời gian/ID trong vùng PAID.

### Bài 14. Vì sao DESC và NULLS quan trọng?

**Đáp án:** quét B-tree xuôi/ngược cho các thứ tự tương ứng, nhưng thứ tự NULL của chiều quét cũng thay đổi; index cho `DESC NULLS LAST` không phải lúc nào khớp index default `ASC NULLS LAST` khi có NULL.

### Bài 15. Phân trang keyset

Trang đầu:

```sql
SELECT order_id, ordered_at
FROM btree250.orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Trang sau dùng hai giá trị hàng cuối:

```sql
WHERE (ordered_at,order_id) < (:last_ordered_at,:last_order_id)
```

**Giải thích:** placeholder ở đây là cú pháp gợi ý ở phía application; trong psql phải thay bằng giá trị/literal thật hoặc dùng prepared statement. Index phù hợp là `(ordered_at DESC, order_id DESC)`.

### Bài 16. B-tree có thể giúp MAX(ordered_at) không?

**Đáp án:** có thể, vì index có thứ tự giúp đọc đầu/cuối vùng khóa trong một số kế hoạch.

### Bài 17. Có index email, WHERE lower(email)=... sẽ tự dùng không?

**Đáp án:** không mặc nhiên. Query dùng một biểu thức khác; có thể cần expression index trên lower(email).

### Bài 18. INCLUDE khác key column thế nào?

**Đáp án:** INCLUDE là payload giúp trả cột từ index; không tham gia thứ tự tìm kiếm và điều kiện unique của key columns.

### Bài 19. Vì sao Index Only Scan vẫn có Heap Fetches?

**Đáp án:** PostgreSQL kiểm tra tính hiển thị MVCC; những heap pages chưa all-visible có thể phải được đọc.

### Bài 20. Partial index PAID có dùng cho generic plan status=$1 không?

**Đáp án:** không bảo đảm. Generic plan phải hợp lệ cho nhiều giá trị parameter; không thể mặc định predicate status='PAID' luôn được thỏa.

### Bài 21. Viết query sử dụng hai điều kiện bằng và khoảng

```sql
SELECT *
FROM btree250.orders
WHERE customer_id = 42
  AND amount_cents >= 150000;
```

**Gợi ý index:** `(customer_id,amount_cents)`. Planner vẫn cân nhắc chi phí.

### Bài 22. Vì sao `customer_id::text = '42'` có thể bất lợi?

**Đáp án:** phép cast đặt trên cột làm biểu thức tìm khác chỉ mục integer gốc. Ưu tiên so sánh theo kiểu integer đúng hoặc expression index khi có nhu cầu đặc thù.

### Bài 23. SELECT ... WHERE customer_id=42 OR status='PAID' có thể dùng một hay hai index?

**Đáp án:** planner có thể cân nhắc BitmapOr từ hai index, hoặc một plan khác. Xem EXPLAIN để biết thực tế.

### Bài 24. Tìm nguyên nhân Seq Scan

**Đề:** một query vẫn Seq Scan dù đã CREATE INDEX.

**Lời giải:** kiểm tra dữ liệu có quá ít/điều kiện quá rộng không, index có khớp expression/opclass/collation không, thứ tự cột có đúng không, thống kê đã cập nhật chưa, cột SELECT có khiến heap access quá nhiều không, và plan có index khác rẻ hơn không.

### Bài 25. Đọc thời gian và buffers thật

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM btree250.orders
WHERE customer_id = 42;
```

**Đáp án:** xem actual rows, actual time, buffers và Index Cond/Filter. Không khẳng định index nhanh chỉ bằng tên node.

### Bài 26. Có nên REINDEX mỗi ngày để giữ B-tree “cân bằng”?

**Đáp án:** không. PostgreSQL tự duy trì cấu trúc index; VACUUM/bảo trì và REINDEX cần dựa trên quan sát bloat, workload và quy trình vận hành, không chạy vô điều kiện.

### Bài 27. Tìm index ít được dùng

```sql
SELECT relname, indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE schemaname='btree250'
ORDER BY idx_scan;
```

**Đáp án:** số lần dùng ít là tín hiệu để điều tra, **không đủ** để xóa index UNIQUE/PK hoặc index phục vụ workload hiếm nhưng quan trọng.

### Bài 28. So sánh B-tree với trigram

**Đề:** người dùng tìm mọi email chứa `'001'` ở giữa.

**Đáp án:** B-tree không có dải khóa hữu ích khi thiếu tiền tố cố định. `pg_trgm` với GIN/GiST có thể phù hợp hơn; cần đo và đánh giá quyền extension.

## 35. Các lỗi cần tránh

### Lỗi 1: “Có index thì câu query chắc chắn dùng index”

Sai. Planner so chi phí Index/Bitmap/Seq Scan và nhiều kế hoạch khác.

### Lỗi 2: “B-tree chỉ hỗ trợ dấu bằng”

Sai. Nó còn hỗ trợ các chiến lược khoảng có thứ tự và những thao tác ORDER BY/LIMIT.

### Lỗi 3: “Tất cả toán tử LIKE đều dùng B-tree”

Sai. Mẫu không có tiền tố đầu chuỗi cố định thường không tận dụng được phạm vi B-tree thông thường.

### Lỗi 4: “LIKE prefix luôn dùng index text mặc định ở mọi locale”

Sai. Collation và pattern operator class có vai trò quan trọng.

### Lỗi 5: “ILIKE prefix chắc chắn giống LIKE”

Không đúng. Case folding có thể yêu cầu expression index hoặc phương pháp khác.

### Lỗi 6: “Đã tạo index(a,b) thì WHERE b=? luôn nhanh”

Không chắc. Thứ tự khóa ảnh hưởng phạm vi quét; skip scan và lựa chọn planner tùy dữ liệu/phiên bản.

### Lỗi 7: “Cột chọn lọc nhất phải luôn đứng đầu index ghép”

Quá đơn giản. Equality, range, ORDER BY, LIMIT và nhiều kiểu query quyết định thứ tự tối ưu.

### Lỗi 8: “IN (1,10,100) tương đương BETWEEN 1 AND 100”

Sai. BETWEEN lấy tất cả giá trị trong khoảng.

### Lỗi 9: “IS NULL phải viết = NULL”

Sai về logic SQL. Dùng IS NULL.

### Lỗi 10: “B-tree index ordered_at luôn dùng tốt cho ordered_at::date”

Không mặc nhiên. Cast/hàm làm thay đổi biểu thức tìm, và `timestamptz::date` phụ thuộc timezone.

### Lỗi 11: “Có index nên ORDER BY LIMIT không bao giờ Sort”

Không chắc. Thứ tự cột, hướng ASC/DESC, NULLS, điều kiện và chi phí đều ảnh hưởng.

### Lỗi 12: “Index-only scan nghĩa là không đọc heap lần nào”

Không nhất thiết; xem Heap Fetches và visibility map.

### Lỗi 13: “INCLUDE(customer_id) tương đương key(customer_id)”

Sai. INCLUDE không phải cột dẫn đường/sắp xếp.

### Lỗi 14: “Partial index dùng được cho mọi parameter”

Sai. Planner phải chứng minh WHERE hàm ý predicate; generic prepared plan có thể không làm được.

### Lỗi 15: “<> là điều kiện khoảng tốt như =”

Thường không. Phủ định có thể chọn quá nhiều hàng, không tương đương một khoảng hữu ích.

### Lỗi 16: “Index mới tạo không dùng thì PostgreSQL bị lỗi”

Có thể index sai biểu thức, thiếu thống kê, bảng nhỏ hoặc Seq Scan thực sự rẻ hơn.

### Lỗi 17: “Tạo càng nhiều index càng nhanh”

Index tăng chi phí INSERT/UPDATE/DELETE, WAL, storage, VACUUM và thời gian migration.

### Lỗi 18: “EXPLAIN ANALYZE an toàn cho mọi DML”

Sai. Với INSERT/UPDATE/DELETE, EXPLAIN ANALYZE thực thi statement; phải kiểm soát transaction/dữ liệu.

### Lỗi 19: “idx_scan=0 nên xóa ngay index”

Sai. Có thể index phục vụ constraint, workload hiếm hoặc stats mới reset.

### Lỗi 20: “Dùng index để giải quyết mọi loại tìm kiếm”

Sai. JSONB containment, full-text, substring, không gian và dữ liệu rất lớn theo vật lý có thể cần GIN/GiST/BRIN hoặc chiến lược khác.

## 36. Bảng tra cứu: điều kiện và chỉ mục gợi ý

| Nhu cầu | SQL minh họa | B-tree phù hợp khi |
|---|---|---|
| Tìm một khóa | `id = ?` | B-tree trên id |
| Khoảng số | `amount >= ? AND amount < ?` | B-tree trên amount |
| Khoảng ngày | `time >= t1 AND time < t2` | B-tree trên time |
| Nhiều giá trị | `id IN (?,?,?)` | B-tree trên id; selectivity hợp lý |
| NULL | `col IS NULL` | Index col và tính chọn lọc phù hợp |
| Không NULL | `col IS NOT NULL` | Có thể, chi phí phụ thuộc tỷ lệ |
| Chuỗi bắt đầu với | `email LIKE 'abc%'` | Collation/opclass thích hợp |
| Không phân biệt hoa thường | `lower(email) LIKE 'abc%'` | Expression index lower(email) + pattern ops |
| Chuỗi chứa | `email LIKE '%abc%'` | B-tree thường không; cân nhắc trigram |
| Lọc equality + range | `a=? AND b>=?` | Index `(a,b)` |
| Lọc ba cột | `a=? AND b=? AND c>=?` | Index `(a,b,c)` |
| Mới nhất theo trạng thái | `WHERE status=? ORDER BY time DESC LIMIT 20` | Index `(status,time DESC)` |
| Chỉ mới nhất toàn bảng | `ORDER BY time DESC LIMIT 20` | Index bắt đầu bằng time |
| Phân trang sâu | `(time,id)<(?,?) ORDER BY time DESC,id DESC` | Index `(time DESC,id DESC)` |
| Lấy MIN/MAX | `MAX(time)` | Index có thứ tự phù hợp |
| Chỉ dữ liệu active | `WHERE active=true` | Partial index predicate khớp |
| Query chỉ cần vài cột | `SELECT keys,payload ...` | Key columns + INCLUDE; visibility phù hợp |
| Tìm theo biểu thức | `lower(email)=?` | Expression B-tree khớp query |
| OR trên hai cột | `a=? OR b=?` | Có thể kết hợp BitmapOr từ các index |
| DISTINCT/GROUP BY | `GROUP BY a` | Có thể hưởng lợi từ thứ tự index; phụ thuộc chi phí |

## 37. Checklist trước khi tạo một B-tree index

1. Truy vấn quan trọng là equality, range, prefix LIKE hay ORDER BY?
2. Kiểu dữ liệu/operator class/collation có hỗ trợ phép so sánh đang dùng không?
3. Điều kiện WHERE sử dụng **cột gốc** hay biểu thức/cast?
4. Có bao nhiêu phần trăm hàng thỏa điều kiện?
5. Query có `ORDER BY ... LIMIT` không?
6. Với chỉ mục ghép, các cột equality và range nằm ở thứ tự nào?
7. Có query khác cần sử dụng tiền tố của index ghép không?
8. Có cần thứ tự DESC hỗn hợp hoặc NULLS LAST/FIRST cụ thể không?
9. Có partial predicate nào ít thay đổi và được query chứng minh không?
10. Có cần expression index hoặc pattern operator class không?
11. Có thể dùng INCLUDE để tránh heap access, và liệu visibility map có thuận lợi không?
12. Có index sẵn nào gần như trùng lặp không?
13. Tần suất INSERT/UPDATE/DELETE là bao nhiêu?
14. Dung lượng index/WAL/chi phí VACUUM tăng bao nhiêu?
15. Đã quan sát `EXPLAIN (ANALYZE, BUFFERS)` với dữ liệu đại diện chưa?
16. Có cần CREATE INDEX CONCURRENTLY để giảm tác động ghi không?
17. Nếu là index unique/partial, có kiểm chứng đúng quy tắc nghiệp vụ và NULL semantics không?
18. Có kế hoạch đo hiệu quả và loại bỏ index dư thừa **sau khi được đánh giá** không?

## 38. Tài liệu PostgreSQL chính thức

Tham khảo tài liệu tương ứng với phiên bản PostgreSQL đang dùng:

- [Index Types — PostgreSQL](https://www.postgresql.org/docs/current/indexes-types.html): các phương pháp index và toán tử được hỗ trợ.
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html): thứ tự cột, equality/range và đặc điểm index nhiều cột.
- [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): sắp xếp ASC/DESC, NULLS và LIMIT.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): index trên biểu thức như lower(email).
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): predicate và điều kiện sử dụng partial index.
- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html): INCLUDE và visibility map.
- [Operator Classes and Operator Families](https://www.postgresql.org/docs/current/indexes-opclass.html): `text_pattern_ops`, toán tử và collation.
- [Examining Index Usage](https://www.postgresql.org/docs/current/indexes-examine.html): quan sát index usage và lựa chọn kế hoạch.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): hiểu EXPLAIN và các node.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): cú pháp B-tree, partial, INCLUDE, CONCURRENTLY.

Một số tối ưu planner và khả năng opclass/collation thay đổi theo phiên bản. Kiểm tra server thực tế:

```sql
SHOW server_version;
SHOW lc_collate;
```

Nếu cần đánh giá riêng cột text trong bảng, kiểm tra collation ở **định nghĩa cột/index** thay vì chỉ dựa vào `lc_collate` của database.

## 39. Tổng kết: từ điều kiện SQL đến phạm vi khóa B-tree

B-tree là index rất mạnh cho dữ liệu **có thứ tự so sánh được**:

```text
WHERE id = ?
       |
       +-- Tìm khóa chính xác

WHERE time >= t1 AND time < t2
       |
       +-- Quét vùng khóa liên tiếp

WHERE status=? AND time>=?
       |
       +-- Index(status,time):
           cố định tiền tố rồi quét range

ORDER BY time DESC LIMIT 20
       |
       +-- Đọc theo thứ tự index,
           có thể dừng sớm

WHERE email LIKE 'abc%'
       |
       +-- Có thể dùng B-tree pattern
           khi collation/opclass phù hợp

WHERE email LIKE '%abc%'
       |
       +-- Không có tiền tố đầu chuỗi cố định;
           xem xét trigram/chiến lược khác
```

Những điều cốt lõi:

1. **B-tree hỗ trợ so sánh theo thứ tự**, đặc biệt `=`, `<`, `<=`, `>`, `>=` và nhiều dạng SQL tương đương như BETWEEN, IN, IS NULL.
2. **Index Cond khác Filter.** Một điều kiện có mặt trong WHERE không đồng nghĩa nó giảm phạm vi quét index.
3. **Index ghép có thứ tự cột.** Equality ở những cột đầu rồi range ở cột tiếp theo thường là mẫu hiệu quả, nhưng planner có thể có tối ưu khác nên không cấm tuyệt đối index thiếu điều kiện cột đầu.
4. **B-tree giúp ORDER BY/LIMIT**, đôi khi hữu ích hơn cả WHERE, nhất là truy vấn lấy top-N.
5. **Chuỗi cần hiểu collation/operator class.** LIKE tiền tố có thể dùng pattern B-tree; LIKE chứa và ILIKE chung chung không mặc nhiên được hỗ trợ như nhau.
6. **Hàm/cast trên cột thay đổi biểu thức tìm kiếm.** Có thể cần viết lại thành range trên cột gốc hoặc dùng expression index.
7. **INCLUDE và index-only scans có giới hạn.** Payload không phải key; MVCC có thể vẫn cần heap.
8. **Partial index chỉ dùng khi predicate được chứng minh phù hợp**; prepared generic plan và điều kiện động là bẫy thường gặp.
9. **Planner quyết định bằng chi phí.** Index hợp lệ có thể thua Seq Scan vì điều kiện quá rộng hoặc bảng nhỏ.
10. **Mỗi index có chi phí ghi và vận hành.** Chỉ tạo sau khi hiểu workload và đo bằng EXPLAIN, không tạo theo cảm giác.

**Một câu để nhớ:** B-tree hiệu quả nhất khi điều kiện và thứ tự truy vấn có thể biến thành **một vùng khóa có thứ tự được giới hạn rõ ràng**; việc PostgreSQL thực sự chọn index còn phụ thuộc dữ liệu, thống kê và chi phí.

