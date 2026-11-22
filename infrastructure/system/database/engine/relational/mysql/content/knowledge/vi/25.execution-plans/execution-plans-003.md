# Đọc cây thực thi, vòng lặp và quan hệ giữa các nhánh

Execution plan mô tả cách MySQL thực hiện một câu truy vấn: đọc bảng nào trước, dùng index nào, lọc ở đâu, nối các tập hàng ra sao, có cần sort hoặc materialize dữ liệu tạm không. Với `EXPLAIN FORMAT=TREE`, kế hoạch được trình bày dưới dạng cây iterator. Mỗi node là một bước xử lý; node cha nhận dữ liệu từ các node con rồi tạo kết quả cho bước phía trên.

Đọc cây thực thi đúng cách cần đi xa hơn việc tìm một dòng có chữ `Index lookup`. Bạn cần hiểu luồng dữ liệu từ leaf lên root, phân biệt nhánh outer và inner của nested-loop join, nhận biết nhánh nào chạy lặp lại, và so sánh số hàng ước lượng với số hàng thực tế. Những thông tin này giúp tìm đúng điểm làm truy vấn chậm: scan quá rộng, filter loại quá nhiều hàng, inner lookup lặp hàng nghìn lần hay sort/materialization phải xử lý tập dữ liệu lớn.

Trong module `DATABASE_MYSQL`, kỹ năng đọc cây thực thi là bước nối giữa thiết kế index và tối ưu truy vấn. Bài học dùng `EXPLAIN FORMAT=TREE` để đọc cấu trúc, `EXPLAIN ANALYZE` để quan sát số liệu thực thi, và các ví dụ JOIN để giải thích quan hệ giữa những nhánh trong kế hoạch.

## 1. Execution plan là gì?

SQL mô tả **kết quả cần lấy**. Optimizer chọn một cách thực hiện để tạo ra kết quả đó. Cùng một câu SQL có thể có nhiều execution plan hợp lệ, ví dụ:

- Quét toàn bộ bảng rồi lọc.
- Tra cứu một index rồi quay lại clustered index.
- Đọc một range của composite index.
- Đọc bảng A trước rồi tra cứu bảng B theo từng hàng.
- Dùng hash join để nối hai tập dữ liệu.
- Sort dữ liệu trước khi áp dụng LIMIT.
- Tạo bảng tạm để materialize derived table hoặc CTE.

Execution plan thể hiện lựa chọn của optimizer dựa trên SQL, schema, index, thống kê và các quy tắc/chi phí thực thi. Kế hoạch có thể thay đổi khi dữ liệu, thống kê, index, phiên bản MySQL hoặc cấu hình thay đổi.

### Plan không phải danh sách câu lệnh SQL theo thứ tự viết

Thứ tự bảng trong `FROM` không nhất thiết là thứ tự MySQL đọc bảng. Optimizer có thể đổi join order nếu thấy chi phí thấp hơn. Tương tự, một điều kiện trong `WHERE` có thể được đẩy xuống gần nơi đọc dữ liệu, thay vì chờ tới cuối truy vấn mới lọc.

Vì vậy, hãy đọc execution plan như một đồ thị các iterator và luồng dữ liệu, không đọc nó như bản sao có thụt lề của câu SQL.

## 2. Hai định dạng thường dùng: tabular và TREE

### EXPLAIN dạng bảng

Các lệnh minh họa trong phần này dùng bảng `customers` được tạo ở phần 5; hãy chuẩn bị schema và fixture trước khi chạy.

```sql
EXPLAIN
SELECT customer_id, email
FROM customers
WHERE email = 'linh@example.test';
```

Dạng bảng hiển thị mỗi bảng hoặc query block trong một dòng. Các cột như `type`, `possible_keys`, `key`, `rows`, `filtered` và `Extra` hữu ích để kiểm tra access path tổng quát, nhưng quan hệ giữa nhiều iterator hoặc các nhánh JOIN không phải lúc nào cũng trực quan.

### EXPLAIN FORMAT=TREE

```sql
EXPLAIN FORMAT=TREE
SELECT customer_id, email
FROM customers
WHERE email = 'linh@example.test';
```

TREE hiển thị iterator cha-con bằng cách thụt lề. Cách trình bày này làm rõ node nào tiêu thụ kết quả từ node nào, join được thực hiện bằng thuật toán gì và các bước sort/filter/aggregate nằm ở đâu.

`FORMAT=TREE` có từ MySQL 8.0.16. Nội dung và tên node cụ thể có thể thay đổi theo phiên bản, loại truy vấn và lựa chọn của optimizer.

### EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT customer_id, email
FROM customers
WHERE email = 'linh@example.test';
```

`EXPLAIN ANALYZE` thực thi câu SELECT và trả về cây iterator có số liệu thực tế như thời gian, số hàng và số vòng lặp. Tính năng này có từ MySQL 8.0.18. Vì truy vấn thật sự được chạy, hãy cẩn thận với câu SELECT quét bảng lớn, JOIN có fan-out cao hoặc truy vấn đang gây tải trên production.

## 3. Cách đọc cấu trúc cây: node cha nhận dữ liệu từ node con

Ví dụ cây khái niệm:

```text
-> Limit: 20 row(s)
    -> Sort: created_at DESC
        -> Filter: status = 'PAID'
            -> Index range scan on orders
```

Đọc theo quan hệ cha-con:

- `Index range scan` là node lá: đọc các entry trong khoảng index.
- `Filter` lấy các hàng từ node con và chỉ phát ra hàng thỏa điều kiện.
- `Sort` lấy dữ liệu từ Filter rồi sắp xếp theo `created_at`.
- `Limit` nhận dữ liệu đã sắp xếp và chỉ trả tối đa 20 hàng.

Luồng dữ liệu đi **từ dưới lên trên**: node lá tạo hàng, node cha xử lý, root của cây trả kết quả cuối cùng cho client.

Một số node có thể là bước xử lý chặn (blocking): chúng cần đọc nhiều hoặc toàn bộ dữ liệu đầu vào trước khi phát ra kết quả đầu tiên. `Sort` là ví dụ điển hình; một số dạng aggregate và materialization cũng có thể cần xử lý tập đầu vào trước. Các node khác như index lookup hoặc filter thường có thể phát dữ liệu theo luồng.

### Quy tắc đọc nhanh

1. Tìm node root ở dòng đầu tiên.
2. Đi xuống các node con để tìm nơi dữ liệu được đọc từ bảng/index.
3. Xem node cha làm gì với hàng do node con phát ra.
4. Với JOIN, xác định thuật toán và vai trò từng nhánh.
5. Với `EXPLAIN ANALYZE`, so sánh rows, loops và thời gian từ các node lá lên node cha.

Không nhầm dòng nằm trên với bước luôn chạy trước về mặt thời gian. Cây thể hiện quan hệ iterator và luồng dữ liệu; node cha thường yêu cầu dữ liệu từ node con khi cần.

## 4. Nhận diện các node thường gặp

Tên node có thể khác nhau giữa phiên bản và định dạng, nhưng các nhóm thao tác thường gặp gồm:

| Node/nhãn thường thấy | Ý nghĩa |
|---|---|
| `Table scan` | Đọc lần lượt các hàng của bảng. |
| `Index scan` | Duyệt toàn bộ hoặc một phần index theo thứ tự index. |
| `Index lookup` | Tìm hàng bằng giá trị khóa trong index. |
| `Index range scan` | Duyệt một khoảng khóa trong B+tree. |
| `Covering index lookup/scan` | Lấy đủ cột cần thiết từ index, không cần đọc thêm clustered record. |
| `Filter` | Loại các hàng không thỏa predicate. |
| `Nested loop join` | Lấy từng hàng từ nhánh outer rồi chạy nhánh inner tương ứng. |
| `Hash join` | Dùng hash table để nối hai tập dữ liệu theo điều kiện phù hợp. |
| `Sort` | Sắp xếp các hàng theo thứ tự yêu cầu. |
| `Aggregate` | Gom các hàng để tính tổng hợp. |
| `Materialize` | Tạo và lưu kết quả trung gian để node khác sử dụng. |
| `Limit` | Giới hạn số hàng phát ra phía trên. |

Đừng chỉ ghi nhớ tên node. Cần hiểu node đó nhận bao nhiêu hàng, phát ra bao nhiêu hàng, chạy bao nhiêu lần và có buộc phải đọc hết đầu vào hay không.

## 5. Chuẩn bị dữ liệu thực hành JOIN

Tạo hai bảng InnoDB: `customers` và `orders`. Bảng orders có index để lọc theo tenant, trạng thái và thời gian.

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    city VARCHAR(80) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_status_created (
        tenant_id,
        status,
        created_at
    ),
    KEY idx_orders_customer (customer_id)
) ENGINE=InnoDB;
```

Nạp fixture nhỏ để đọc kết quả dễ dàng:

```sql
INSERT INTO customers (customer_id, email, customer_name, city)
VALUES
    (1, 'an@example.test', 'An Nguyen', 'Da Nang'),
    (2, 'binh@example.test', 'Binh Tran', 'Ho Chi Minh City'),
    (3, 'chi@example.test', 'Chi Le', 'Ha Noi');

INSERT INTO orders (
    order_id,
    customer_id,
    tenant_id,
    status,
    created_at,
    total_amount
)
VALUES
    (101, 1, 10, 'PAID', '2026-01-03 09:00:00', 250.00),
    (102, 2, 10, 'PAID', '2026-01-04 10:00:00', 180.00),
    (103, 1, 10, 'NEW',  '2026-01-05 11:00:00', 120.00),
    (104, 3, 10, 'PAID', '2026-01-08 12:00:00', 450.00),
    (105, 2, 20, 'PAID', '2026-01-09 13:00:00',  90.00);
```

Kiểm tra fixture:

```sql
SELECT * FROM customers ORDER BY customer_id;
SELECT * FROM orders ORDER BY order_id;
```

Fixture nhỏ phù hợp để hiểu cú pháp và luồng JOIN. Optimizer có thể chọn table scan trên bảng nhỏ vì chi phí thấp; muốn đánh giá hiệu năng index cần dữ liệu có quy mô và phân bố gần workload thực tế.

## 6. Đọc một cây Nested Loop Join

Truy vấn lấy đơn hàng PAID của tenant 10 trong một khoảng thời gian và thông tin khách hàng:

```sql
EXPLAIN FORMAT=TREE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
ORDER BY o.created_at DESC, o.order_id DESC;
```

Một cây minh họa có thể có hình dạng:

```text
-> Nested loop inner join
    -> Index range scan on o using idx_orders_tenant_status_created
       over (tenant_id = 10, status = 'PAID', created_at in requested range)
    -> Single-row index lookup on c using PRIMARY
       (customer_id = o.customer_id)
```

Đây là hình dạng minh họa; tên node, cost, rows và thứ tự hiển thị có thể khác khi chạy trên phiên bản/dữ liệu cụ thể.

### Nhánh thứ nhất là outer input

Nhánh đầu tiên của nested loop đọc các đơn hàng từ index `idx_orders_tenant_status_created`. Các cột equality `tenant_id` và `status` xác định prefix; `created_at` giới hạn range tiếp theo.

Nếu index range scan phát ra 3 hàng orders, nested loop nhận 3 outer rows. Mỗi hàng mang `customer_id` để dùng trong nhánh thứ hai.

### Nhánh thứ hai là inner input

Với mỗi order từ outer input, nested loop tra bảng customers bằng primary key:

```sql
WHERE customer_id = o.customer_id
```

Do `customer_id` là primary key, mỗi lần lookup có thể tìm tối đa một khách hàng. Nhánh inner được gọi lại cho từng hàng outer; nếu outer có 3 hàng, inner lookup có khoảng 3 vòng lặp.

### Quan hệ giữa hai nhánh

```text
Outer: Index range scan orders
       rows = 3, loops = 1
                  |
                  | mỗi order cung cấp customer_id
                  v
Inner: PK lookup customers
       rows = 1, loops = 3
                  |
                  v
       Nested loop join output = 3 rows
```

Đây là ý nghĩa quan trọng của `loops`: một inner iterator có thể chỉ trả một hàng mỗi lần nhưng được chạy rất nhiều lần. Nếu outer input phát ra 50.000 hàng, inner lookup có thể phải chạy 50.000 lần.

## 7. Hiểu `rows` và `loops` trong EXPLAIN ANALYZE

`EXPLAIN FORMAT=TREE` hiển thị ước lượng, thường có dạng `cost=... rows=...`. `cost` là đơn vị chi phí nội bộ của optimizer, không phải mili giây và không phải thời gian chạy thực tế. `rows` là số hàng ước lượng iterator sẽ phát ra. `EXPLAIN ANALYZE` bổ sung số liệu thực tế:

```sql
EXPLAIN ANALYZE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
ORDER BY o.created_at DESC, o.order_id DESC;
```

Một đoạn output minh họa:

```text
-> Nested loop inner join
   (actual time=0.080..0.150 rows=3 loops=1)
    -> Index range scan on o
       (actual time=0.030..0.050 rows=3 loops=1)
    -> Single-row index lookup on c using PRIMARY
       (actual time=0.015..0.020 rows=1 loops=3)
```

Các con số trên chỉ nhằm minh họa cách đọc, không phải số đo từ database của bạn.

| Trường | Ý nghĩa |
|---|---|
| `actual time=a..b` | Thời gian thực tế từ lúc iterator tạo hàng đầu tiên tới khi hoàn tất, tính bằng mili giây theo cách đo của iterator; với iterator lặp nhiều lần, số liệu thời gian được báo trung bình mỗi loop. |
| `rows` | Số hàng thực tế iterator phát ra trung bình mỗi lần chạy. |
| `loops` | Số lần iterator được thực thi. |

Với iterator chạy nhiều vòng, `rows` thường là trung bình mỗi loop. Có thể ước lượng tổng hàng phát ra bằng `rows × loops`; số liệu có thể được làm tròn nên đây là phép tính gần đúng.

Trong ví dụ, inner lookup có `rows=1 loops=3`: mỗi lần tra cứu trả một khách hàng và iterator chạy ba lần. Không đọc `rows=1` rồi kết luận toàn nhánh chỉ xử lý một hàng.

### Đọc thời gian một cách thận trọng

Không cộng thời gian của node cha và tất cả node con như thể chúng là các tác vụ độc lập. Thời gian của iterator cha có quan hệ với thời gian tiêu thụ dữ liệu từ iterator con; các khoảng đo có thể lồng nhau. Hãy dùng thời gian để tìm node có chi phí đáng chú ý và so sánh cùng rows/loops, thay vì cộng tất cả thành tổng thời gian giả định.

## 8. Nhận biết fan-out trong nested loop

Fan-out là số hàng mà một bước JOIN tạo ra từ mỗi hàng đầu vào, hoặc mức nhân số hàng qua các bước JOIN. Fan-out lớn có thể làm số lần inner lookup tăng nhanh.

Ví dụ:

```text
Orders range scan:             20,000 rows
Customer PK lookup:            20,000 loops
Order items lookup:            20,000 loops
Average items per order:           8 rows
Rows after joining items:     160,000 rows
```

Một truy vấn có thể bắt đầu bằng 20.000 đơn hàng, rồi mở rộng thành 160.000 dòng sau khi nối order items. Nếu tiếp tục JOIN thêm bảng con, số hàng trung gian có thể tăng đáng kể.

Khi đọc plan, hãy hỏi:

- Outer branch phát ra bao nhiêu hàng?
- Inner branch chạy bao nhiêu loops?
- Mỗi loop trả trung bình bao nhiêu hàng?
- Sau mỗi JOIN, tổng rows tăng hay giảm?
- Có thể lọc sớm hơn mà vẫn giữ đúng ngữ nghĩa không?
- Có index phù hợp cho điều kiện lookup của inner branch không?

Đừng chỉ tối ưu một index lookup riêng lẻ. Một lookup 0,01 ms có vẻ nhỏ, nhưng lặp 100.000 lần vẫn tạo tổng chi phí đáng kể.

## 9. Filter node và tỷ lệ loại bỏ hàng

Filter nhận các hàng từ iterator con, đánh giá predicate và chỉ phát ra các hàng thỏa điều kiện.

Ví dụ:

```text
-> Filter: status = 'PAID'
    -> Table scan on orders
```

Nếu table scan đọc 100.000 hàng nhưng Filter chỉ phát ra 500 hàng, phần lớn dữ liệu bị loại sau khi đã đọc. Đây có thể là dấu hiệu predicate chưa được đẩy vào access path hoặc chưa có index phù hợp.

Với `EXPLAIN ANALYZE`, so sánh:

- Rows của node đọc bảng/index.
- Rows của node Filter.
- Số loops của từng node.
- Thời gian của iterator.

Nếu một Filter giảm từ 100.000 xuống 500 hàng, hãy xem điều kiện đó có thể trở thành index range/ref lookup hay index condition không. Nhưng không phải predicate nào cũng có thể dùng index; hàm trên cột, wildcard đầu chuỗi, kiểu dữ liệu không khớp hoặc độ chọn lọc thấp có thể làm index không hiệu quả.

### Filter khác access condition

Access condition giúp xác định entry/range cần đọc từ index. Filter/residual condition được kiểm tra sau khi iterator đã đọc candidate rows. Một predicate có thể được dùng một phần trong index access và phần còn lại được lọc sau. Đọc cây cùng với thông tin index và `EXPLAIN FORMAT=JSON` nếu cần biết rõ điều kiện được áp dụng ở đâu.

## 10. Sort node và tác động tới LIMIT

Một cây có thể chứa:

```text
-> Limit: 20 row(s)
    -> Sort: created_at DESC
        -> Table scan on orders
```

Node Sort cần nhận dữ liệu từ child rồi sắp xếp theo thứ tự. Khi sort phải xử lý toàn bộ tập đầu vào, `LIMIT 20` phía trên không có nghĩa MySQL chỉ đọc 20 hàng từ bảng. Engine có thể phải đọc và xử lý nhiều hàng trước khi biết 20 hàng đứng đầu.

Một index có thứ tự phù hợp có thể giúp tránh sort:

```sql
-- Index idx_orders_tenant_status_created đã được tạo ở phần chuẩn bị dữ liệu.
SHOW INDEX FROM orders;
```

Với equality trên `tenant_id`, `status` và order theo `created_at`, index có thể hỗ trợ thứ tự cần thiết. Vì `order_id` là primary key, InnoDB mang clustered key vào secondary index entry; vẫn phải kiểm tra kế hoạch thực tế để xác nhận thứ tự và chiều scan được đáp ứng.

Khi thấy `Sort` trong cây, hãy kiểm tra:

1. Bao nhiêu hàng đi vào Sort?
2. Sort nằm trước hay sau JOIN?
3. Có thể dùng index để đọc theo thứ tự yêu cầu không?
4. LIMIT có thể dừng đọc sớm hay Sort vẫn cần xử lý toàn bộ đầu vào?
5. Sort có làm phát sinh temporary storage khi dữ liệu lớn không?

## 11. Aggregate và quan hệ với các nhánh đầu vào

Aggregate node gom nhiều hàng để tạo giá trị tổng hợp hoặc một hàng cho mỗi nhóm.

Ví dụ:

```sql
EXPLAIN FORMAT=TREE
SELECT tenant_id, status, COUNT(*) AS order_count
FROM orders
GROUP BY tenant_id, status;
```

Một cây minh họa:

```text
-> Group aggregate: count(0)
    -> Index scan on orders using idx_orders_tenant_status_created
```

Nếu dữ liệu được đọc theo thứ tự nhóm phù hợp, engine có thể gom các nhóm khi duyệt index. Trong trường hợp khác, plan có thể cần sort hoặc temporary table trước/sau aggregate. Không kết luận chỉ từ câu `GROUP BY`; hãy đọc node thực tế.

Với aggregate không có GROUP BY:

```sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = 10;
```

Aggregate thường nhận nhiều hàng từ access iterator và trả một hàng kết quả. Vì vậy rows của node con có thể rất lớn trong khi rows của node aggregate chỉ bằng 1.

## 12. Hash Join và cách đọc nhánh build/probe

MySQL 8.0.18 trở lên hỗ trợ hash join cho các trường hợp phù hợp, đặc biệt khi optimizer không có access path index hiệu quả cho điều kiện equality join.

Hash join thường có hai vai trò:

- **Build side:** đọc một tập dữ liệu và xây hash table theo khóa JOIN.
- **Probe side:** đọc tập còn lại, tra hash table để tìm hàng khớp.

Cây minh họa:

```text
-> Inner hash join (a.key = b.key)
    -> Table scan on a
    -> Hash
        -> Table scan on b
```

Node `Hash` biểu diễn bước xây hash table trên một nhánh. Nhánh còn lại được dùng để probe. Hình dạng và thứ tự node có thể khác theo phiên bản và kế hoạch; hãy đọc điều kiện JOIN, node `Hash` và số liệu actual thay vì mặc định bảng đầu tiên trong SQL luôn là build side.

Hash join có thể tránh hàng loạt index lookup ngẫu nhiên khi hai tập dữ liệu cần được nối bằng equality. Tuy nhiên, nó vẫn phải đọc các tập đầu vào và xây cấu trúc hash; nếu tập build lớn, chi phí bộ nhớ và xử lý có thể cao. Hash join không phải lúc nào cũng tốt hơn nested loop.

### So sánh Nested Loop và Hash Join

| Tiêu chí | Nested loop | Hash join |
|---|---|---|
| Cách làm | Với mỗi hàng outer, chạy lookup/scan ở inner. | Xây hash table từ một nhánh rồi probe bằng nhánh kia. |
| Phù hợp | Outer nhỏ, inner có index lookup chọn lọc. | Hai tập cần join lớn, điều kiện equality phù hợp, lookup index không thuận lợi. |
| Dấu hiệu cần chú ý | Inner loops cao, mỗi loop tốn thời gian hoặc trả nhiều hàng. | Build side lớn, scan đầu vào rộng, hash processing tốn tài nguyên. |
| Tối ưu thường gặp | Giảm outer rows, thêm index cho inner predicate. | Lọc sớm hai đầu vào, giảm số cột/hàng cần hash và kiểm tra thống kê. |

## 13. Materialize, derived table và subquery

Một số truy vấn tạo kết quả trung gian trước khi JOIN hoặc lọc tiếp. Cây có thể hiển thị node `Materialize` hoặc node tương tự.

Ví dụ derived table:

```sql
EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_count
FROM customers AS c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    WHERE tenant_id = 10
    GROUP BY customer_id
) AS recent
  ON recent.customer_id = c.customer_id;
```

Optimizer có thể materialize derived table để tính số đơn theo khách hàng rồi JOIN với customers. Nếu derived table có thể được merge vào query block ngoài, cây có thể khác và không xuất hiện bước materialization riêng.

### Materialize một lần và re-execute nhiều lần

Hãy xem `loops` của node tạo hoặc đọc kết quả trung gian:

- Nếu materialization được tạo một lần rồi đọc lại, node tạo dữ liệu có thể có `loops=1`.
- Nếu một subquery phụ thuộc vào hàng outer và được thực thi lại theo từng hàng, các iterator bên trong có thể có loops cao.
- Optimizer có thể chuyển một số subquery thành semijoin, antijoin hoặc materialized subquery; plan phản ánh chiến lược được chọn.

Không mặc định mọi CTE đều materialize hoặc mọi derived table đều được materialize. MySQL có thể merge hoặc materialize tùy query block, hint, cấu trúc và điều kiện tối ưu.

## 14. Đọc quan hệ giữa các nhánh JOIN nhiều bảng

Giả sử truy vấn nối orders, customers và order_items:

Tạo bảng con và dữ liệu minh họa trước khi chạy truy vấn:

```sql
CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_order (order_id)
) ENGINE=InnoDB;

INSERT INTO order_items (order_item_id, order_id, product_id, quantity)
VALUES
    (1, 101, 501, 2),
    (2, 101, 502, 1),
    (3, 102, 503, 3),
    (4, 104, 504, 1),
    (5, 104, 505, 2);
```

Tiếp tục dùng các bảng `orders` và `customers` đã tạo ở phần chuẩn bị:

```sql
SELECT
    o.order_id,
    c.customer_name,
    i.product_id,
    i.quantity
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID';
```

Một kế hoạch nested loop có thể được hiểu như sau:

```text
Nested loop
├── Nested loop
│   ├── Access orders (lọc tenant/status)
│   └── Lookup customers theo customer_id
└── Lookup order_items theo order_id
```

Đây là sơ đồ logic, không phải output cố định. Nếu nhánh orders phát ra 1.000 hàng, lookup customers có thể chạy 1.000 lần; sau đó lookup order_items cũng có thể chạy theo số hàng của kết quả nested loop bên trong. Nếu mỗi order trung bình có 5 items, kết quả có thể tăng lên khoảng 5.000 hàng.

Khi đọc cây nhiều bảng:

1. Bắt đầu từ node access ở đáy.
2. Theo dõi số hàng sau mỗi node JOIN.
3. Xác định node inner nào lặp theo output của node cha.
4. Tìm nơi fan-out tăng mạnh.
5. Kiểm tra index cho từng điều kiện nối.
6. Xem optimizer có đổi join order so với câu SQL hay không.

## 15. Estimated rows và actual rows lệch nhau

Optimizer dùng thống kê để dự đoán số hàng. Nếu dự đoán sai đáng kể, nó có thể chọn join order hoặc access path không phù hợp.

Ví dụ:

```text
Index range scan on orders
    estimated rows = 100
    actual rows    = 50,000
```

Sai lệch lớn có thể làm nested loop thực hiện 50.000 inner lookups thay vì 100 như optimizer dự tính. Một kế hoạch nhìn có vẻ rẻ trên ước lượng có thể rất chậm khi chạy thật.

Các nguyên nhân thường gặp:

- Statistics cũ hoặc không đại diện cho phân bố hiện tại.
- Dữ liệu lệch (skew), một giá trị xuất hiện quá thường xuyên.
- Nhiều cột có tương quan nhưng optimizer ước lượng như thể độc lập.
- Predicate phức tạp hoặc hàm làm selectivity khó ước lượng.
- Histogram chưa có hoặc không phản ánh phân bố cần thiết.
- Parameter/value cụ thể khác xa giá trị thường gặp trong thống kê.

Hướng điều tra:

1. So sánh estimated rows với actual rows ở từng node.
2. Tìm node đầu tiên có sai lệch lớn; sai lệch ở node sớm thường lan lên các node cha.
3. Kiểm tra index và `SHOW INDEX`/cardinality.
4. Cân nhắc `ANALYZE TABLE` để cập nhật thống kê index.
5. Với cột lệch mạnh, đánh giá histogram phù hợp.
6. Chạy lại EXPLAIN/ANALYZE trên cùng điều kiện để so sánh.

Không cập nhật thống kê hoặc tạo histogram chỉ để ép một kế hoạch cụ thể. Trước hết cần xác nhận số liệu và workload có thực sự yêu cầu thay đổi.

## 16. Vì sao `loops` quan trọng hơn việc chỉ nhìn rows?

Một iterator có thể phát ít hàng mỗi lần nhưng chạy rất nhiều lần. Ví dụ:

```text
Single-row index lookup on customers
    actual rows = 1
    loops       = 100,000
```

Mỗi lookup chỉ trả một hàng, nhưng tổng cộng có thể xử lý khoảng 100.000 lần. Nếu mỗi lần cần random page access và page không nằm trong buffer pool, chi phí có thể đáng kể.

Ngược lại:

```text
Table scan on small_lookup_table
    actual rows = 500
    loops       = 1
```

Quét 500 hàng một lần có thể rẻ hơn nhiều lần lookup riêng lẻ trên một bảng lớn. Vì vậy, hãy đánh giá đồng thời:

- Số hàng trung bình mỗi loop.
- Số loops.
- Tổng hàng ước tính (`rows × loops`).
- Thời gian iterator.
- Loại access và locality của page.
- Số hàng mà node cha thực sự cần.

Không kết luận “rows càng nhỏ càng tốt” mà bỏ qua loops. Cũng không kết luận “table scan luôn xấu”; scan một tập nhỏ hoặc scan tuần tự có thể là lựa chọn rẻ.

## 17. Quy trình đọc cây thực thi từ đầu đến cuối

Khi nhận một truy vấn chậm, đọc plan theo trình tự sau:

1. **Xác nhận truy vấn và dữ liệu:** dùng đúng parameter/value, schema, index và isolation/configuration đang chạy.
2. **Lấy cây ước lượng:** chạy `EXPLAIN FORMAT=TREE`.
3. **Tìm root:** xác định kết quả cuối cùng là Limit, Sort, Aggregate, Join hay một iterator khác.
4. **Đi xuống leaf:** xác định mỗi bảng được đọc bằng table scan, index scan, range scan hay lookup.
5. **Đọc join order:** xem bảng/nhánh nào là outer, inner, build hoặc probe.
6. **Theo dõi rows:** xem mỗi node nhận và phát ra bao nhiêu hàng.
7. **Theo dõi loops:** tìm iterator được lặp nhiều lần, đặc biệt inner lookup và dependent subquery.
8. **Kiểm tra filter:** xác định điều kiện được dùng để truy cập index và điều kiện còn phải lọc sau.
9. **Kiểm tra sort/materialize:** xem các node này phải xử lý bao nhiêu hàng và có thể tránh bằng index hay rewrite không.
10. **Chạy EXPLAIN ANALYZE có kiểm soát:** lấy actual time, rows và loops nếu truy vấn an toàn để thực thi.
11. **Tìm sai lệch estimate:** bắt đầu từ node đầu tiên có estimated/actual rows lệch lớn.
12. **Đề xuất thay đổi nhỏ:** index, predicate, join order qua cấu trúc SQL, projection hoặc thống kê.
13. **Đo lại:** so sánh plan, kết quả đúng và thời gian trên cùng dữ liệu/điều kiện.

Đừng thay nhiều index hoặc viết lại toàn bộ truy vấn cùng lúc. Thay đổi từng yếu tố giúp xác định điều gì thực sự làm kế hoạch tốt hơn.

## 18. Những lỗi thường gặp khi đọc cây

| Lỗi | Hậu quả | Cách đọc đúng |
|---|---|---|
| Đọc cây từ dòng đầu xuống như thứ tự chạy SQL | Hiểu sai luồng iterator | Node cha tiêu thụ dữ liệu từ node con; đọc luồng từ leaf lên root. |
| Nghĩ bảng đầu tiên trong FROM luôn chạy trước | Bỏ qua join order của optimizer | Xem các nhánh access thực tế trong cây. |
| Thấy inner lookup có rows=1 và nghĩ chi phí rất nhỏ | Bỏ qua số lần lặp | Nhân rows trung bình với loops để ước lượng tổng hàng. |
| Chỉ nhìn cost, không xem actual | Bỏ qua sai lệch ước lượng | Dùng EXPLAIN ANALYZE và so estimated/actual rows. |
| Cộng thời gian mọi node | Tính trùng thời gian iterator cha-con | Đọc thời gian theo quan hệ lồng nhau, không cộng máy móc. |
| Thấy Filter và cho rằng index đã lọc hết | Có thể còn đọc nhiều candidate rows | So rows trước và sau Filter, kiểm tra access condition. |
| Thấy Limit 20 và nghĩ chỉ đọc 20 hàng | Sort/aggregate phía dưới có thể phải đọc nhiều hơn | Xem node nằm dưới Limit và khả năng dừng sớm. |
| Nghĩ nested loop luôn chậm | Bỏ qua trường hợp outer nhỏ và inner unique lookup | Đánh giá outer rows, inner loops và index. |
| Nghĩ hash join luôn tốt hơn nested loop | Bỏ qua chi phí build/probe và kích thước tập | Xem số hàng hai đầu vào và build-side footprint. |
| Nghĩ mọi CTE/derived table luôn materialize | Đọc sai plan khi optimizer merge query block | Dựa vào node thực tế, không suy từ cú pháp. |
| Chạy EXPLAIN ANALYZE trên truy vấn nguy hiểm ở production | Truy vấn thật có thể gây tải lớn | Đánh giá an toàn và dùng môi trường phù hợp. |

## 19. Bài tập thực hành

### Bài tập A — Đọc parent/child iterator

1. Tạo bảng `customers`, `orders` và fixture ở phần chuẩn bị.
2. Chạy `EXPLAIN FORMAT=TREE` cho truy vấn JOIN.
3. Xác định node root, node access và node join.
4. Vẽ lại luồng dữ liệu từ index range scan tới kết quả cuối.
5. Giải thích node cha nhận hàng từ node con như thế nào.

### Bài tập B — Quan sát loops của Nested Loop

1. Chạy `EXPLAIN ANALYZE` cho truy vấn JOIN.
2. Ghi rows và loops của outer index scan.
3. Ghi rows và loops của inner primary-key lookup.
4. Tăng số orders trong fixture lên vài nghìn hàng.
5. Giải thích vì sao inner loops tăng theo số outer rows.

### Bài tập C — Nhận biết fan-out

1. Tạo bảng `order_items` có nhiều item cho mỗi order.
2. JOIN orders với order_items.
3. Dùng EXPLAIN ANALYZE ghi số hàng trước và sau JOIN.
4. Tính fan-out trung bình.
5. Tìm cách giảm tập hàng đầu vào mà vẫn giữ đúng kết quả nghiệp vụ.

### Bài tập D — Filter, Sort và Limit

1. Chạy truy vấn có filter và `ORDER BY ... LIMIT`.
2. Xem cây có Sort hay không.
3. Tạo index phù hợp với equality prefix và order key.
4. Chạy lại EXPLAIN để xem Sort có biến mất không.
5. So sánh số hàng được đọc khi có và không có index hỗ trợ thứ tự.

### Bài tập E — Nested Loop và Hash Join

1. Tạo hai bảng có tập dữ liệu lớn hơn và điều kiện equality JOIN.
2. Chạy EXPLAIN TREE và nhận diện thuật toán JOIN.
3. Quan sát node Hash/build/probe nếu optimizer chọn hash join.
4. Thử thêm index phù hợp và đo lại.
5. Giải thích vì sao optimizer thay đổi giữa nested loop và hash join.

### Bài tập F — Estimate và actual

1. Chạy EXPLAIN và ghi estimated rows của từng node.
2. Chạy EXPLAIN ANALYZE và ghi actual rows/loops.
3. Tìm node đầu tiên có sai lệch lớn.
4. Chạy `ANALYZE TABLE` nếu thống kê cần cập nhật.
5. Đo lại và giải thích thay đổi của optimizer.

Bạn hoàn thành bài khi có thể đọc luồng dữ liệu từ leaf lên root, giải thích quan hệ outer/inner hoặc build/probe, tính được tác động của loops/fan-out và tìm node đầu tiên có sai lệch giữa estimated rows với actual rows.

## 20. Nguyên tắc cần ghi nhớ

- Execution plan là cách optimizer thực hiện SQL; nó không phải bản sao thứ tự viết của câu SQL.
- Trong TREE, node cha nhận dữ liệu từ node con; luồng kết quả đi từ leaf lên root.
- `EXPLAIN FORMAT=TREE` hiển thị quan hệ iterator; `EXPLAIN ANALYZE` thực thi SELECT và bổ sung số liệu actual.
- Nested loop dùng nhánh outer làm đầu vào và gọi inner iterator cho từng outer row.
- `loops` cho biết iterator được chạy bao nhiêu lần; rows thường là số hàng trung bình mỗi loop.
- `rows × loops` giúp ước lượng tổng hàng của iterator lặp, có thể sai khác do làm tròn.
- Fan-out lớn có thể nhân số hàng qua nhiều JOIN và làm inner lookup lặp nhiều lần.
- Filter giảm hàng sau iterator con; so sánh rows trước/sau để tìm nơi loại bỏ nhiều dữ liệu.
- Sort, aggregate và materialize có thể là bước xử lý chặn, khiến LIMIT phía trên không dừng đọc sớm.
- Hash join có build/probe side; đánh giá kích thước hai tập đầu vào và chi phí hash.
- Estimated rows lệch actual rows có thể làm optimizer chọn join order/access path kém.
- Không cộng thời gian node cha-con máy móc; các phép đo iterator có quan hệ lồng nhau.
- Dùng EXPLAIN TREE, EXPLAIN ANALYZE, thống kê và workload thật để xác minh thay đổi.

Khi đọc execution plan như một cây iterator và theo dõi rows cùng loops trên từng nhánh, bạn sẽ nhìn thấy nơi dữ liệu được đọc, nơi số hàng tăng hoặc giảm và bước nào bị lặp nhiều lần. Đây là cơ sở để chọn index, thu hẹp đầu vào JOIN, xử lý sort/materialization và tối ưu truy vấn dựa trên bằng chứng thực thi.
