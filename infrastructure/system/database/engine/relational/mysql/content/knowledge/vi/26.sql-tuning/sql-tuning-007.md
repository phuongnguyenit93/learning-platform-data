# Tối ưu EXISTS/IN và tránh truy vấn con lặp không cần thiết

Subquery giúp diễn đạt các câu hỏi quan hệ rất tự nhiên: khách hàng nào có đơn hàng, sản phẩm nào chưa từng được bán, hoặc mỗi khách hàng có bao nhiêu giao dịch. Tuy nhiên, nếu viết truy vấn con không đúng mục đích, một câu SQL có thể thực hiện nhiều lần tra cứu lặp lại cho từng hàng bên ngoài, đếm nhiều hàng dù chỉ cần biết có tồn tại hay không, hoặc tạo ra kết quả sai khi `NULL` xuất hiện trong `NOT IN`.

`EXISTS` và `IN` thường được dùng để kiểm tra sự tồn tại hoặc thành viên của một tập giá trị. MySQL có thể chuyển nhiều dạng subquery này thành semijoin hoặc antijoin, materialize kết quả trung gian, hoặc chọn chiến lược khác dựa trên cost. Vì vậy, tối ưu không đơn giản là thay mọi `IN` bằng `EXISTS` hay ngược lại. Cần chọn biểu thức đúng ngữ nghĩa, giúp optimizer nhận diện được phép biến đổi, cung cấp index phù hợp và kiểm chứng bằng execution plan.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là viết truy vấn kiểm tra tồn tại/không tồn tại đúng cách, tránh subquery lặp không cần thiết và nhận biết khi nào nên thay bằng join hoặc pre-aggregation.

Sau bài học, bạn có thể:

- Phân biệt ngữ nghĩa của `EXISTS`, `IN`, `NOT EXISTS` và `NOT IN`.
- Dùng `EXISTS` khi chỉ cần biết có ít nhất một hàng khớp.
- Hiểu semijoin và antijoin cùng các chiến lược MySQL có thể chọn.
- Tránh lỗi ba giá trị logic khi `NOT IN` gặp `NULL`.
- Nhận diện correlated subquery có thể gây lặp công việc theo từng hàng ngoài.
- Thay nhiều scalar subquery tương tự bằng một derived table/CTE tổng hợp.
- Chọn index cho điều kiện tương quan và điều kiện lọc.
- Đọc `EXPLAIN`/`EXPLAIN ANALYZE` để kiểm tra số hàng, loops và access path.
- Biết khi nào giữ subquery, khi nào dùng join, và khi nào materialization phù hợp.

## 1. Fixture thực hành

Dùng một bộ bảng đơn giản gồm khách hàng và đơn hàng. Các ví dụ chạy độc lập trên schema lab.

```sql
DROP TABLE IF EXISTS tuning_order_items;
DROP TABLE IF EXISTS tuning_orders;
DROP TABLE IF EXISTS tuning_customers;

CREATE TABLE tuning_customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    region_code VARCHAR(20) NULL,
    PRIMARY KEY (customer_id),
    KEY idx_tuning_customers_region (region_code)
) ENGINE = InnoDB;

CREATE TABLE tuning_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    order_date DATE NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_tuning_orders_customer_status (customer_id, order_status),
    KEY idx_tuning_orders_status_date_customer
        (order_status, order_date, customer_id)
) ENGINE = InnoDB;

CREATE TABLE tuning_order_items (
    item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_tuning_items_order (order_id)
) ENGINE = InnoDB;

INSERT INTO tuning_customers (customer_id, customer_name, region_code) VALUES
(1, 'An', 'NORTH'),
(2, 'Binh', 'SOUTH'),
(3, 'Chi', 'NORTH'),
(4, 'Dung', NULL),
(5, 'Ha', 'CENTRAL');

INSERT INTO tuning_orders
    (order_id, customer_id, order_status, order_date, total_amount)
VALUES
(101, 1, 'PAID',   '2026-11-01', 120.00),
(102, 1, 'OPEN',   '2026-11-04',  80.00),
(103, 2, 'CANCEL', '2026-11-05',  45.00),
(104, 3, 'PAID',   '2026-11-06', 210.00),
(105, 3, 'OPEN',   '2026-11-07',  90.00),
(106, 3, 'OPEN',   '2026-11-08',  35.00),
(107, 5, 'PAID',   '2026-11-09', 160.00);

INSERT INTO tuning_order_items
    (item_id, order_id, product_code, quantity)
VALUES
(1, 101, 'BOOK-A', 1),
(2, 101, 'PEN-B',  2),
(3, 102, 'BAG-C',  1),
(4, 104, 'BOOK-A', 2),
(5, 105, 'PEN-B',  4),
(6, 106, 'MUG-D',  1);
```

Kiểm tra dữ liệu:

```sql
SELECT * FROM tuning_customers ORDER BY customer_id;
SELECT * FROM tuning_orders ORDER BY order_id;
```

Khách hàng 1 và 3 có đơn OPEN; khách hàng 2 và 5 không có đơn OPEN; khách hàng 4 không có đơn nào. Các ví dụ sau dùng tập dữ liệu này để so sánh kết quả và kế hoạch.

## 2. EXISTS: chỉ cần biết có ít nhất một hàng

`EXISTS (subquery)` trả về TRUE nếu subquery tạo ra ít nhất một hàng, FALSE nếu không có hàng. Giá trị các cột trong SELECT list của subquery không quan trọng; optimizer chỉ cần biết sự tồn tại của hàng phù hợp.

Ví dụ tìm khách hàng có ít nhất một đơn OPEN:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
ORDER BY c.customer_id;
```

Kết quả gồm An và Chi. Điều kiện bên trong tương quan với hàng hiện tại của `tuning_customers` qua `o.customer_id = c.customer_id`.

### 2.1. Vì sao SELECT 1?

Trong EXISTS, nội dung SELECT list không được dùng để tạo kết quả hiển thị. `SELECT 1`, `SELECT *` hoặc `SELECT o.order_id` đều biểu đạt cùng phép kiểm tra tồn tại trong trường hợp này. `SELECT 1` thường rõ ý định hơn: ta không cần lấy dữ liệu từ subquery.

Không cần viết `COUNT(*) > 0` nếu chỉ muốn kiểm tra tồn tại:

```sql
-- Không cần đếm tất cả hàng chỉ để biết có hay không
WHERE (
    SELECT COUNT(*)
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
) > 0
```

Viết bằng EXISTS:

```sql
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
```

Về ngữ nghĩa, EXISTS không yêu cầu đếm mọi hàng khớp. MySQL có thể dừng kiểm tra sau khi tìm thấy một hàng hoặc dùng chiến lược semijoin tương đương. `COUNT(*)` phải tạo ra số lượng phù hợp với toàn bộ tập khớp, dù optimizer có thể tối ưu một số trường hợp cụ thể.

### 2.2. EXISTS không nhân bản hàng bên ngoài

Nếu một khách hàng có ba đơn OPEN, truy vấn EXISTS vẫn trả khách hàng đó một lần. Nó kiểm tra quan hệ tồn tại, không tạo một kết quả cho mỗi hàng con.

Đây là khác biệt quan trọng so với JOIN:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'OPEN';
```

Khách hàng Chi xuất hiện hai lần vì có hai đơn OPEN. Muốn khử trùng bằng `DISTINCT` sẽ cần thêm bước xử lý. Nếu câu hỏi chỉ là “khách hàng có đơn OPEN hay không?”, EXISTS thể hiện đúng ý định và tránh fan-out từ bảng con.

## 3. IN: kiểm tra một giá trị thuộc tập kết quả

`IN (subquery)` kiểm tra biểu thức bên ngoài có bằng một trong các giá trị do subquery trả về hay không:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM tuning_orders AS o
    WHERE o.order_status = 'OPEN'
)
ORDER BY c.customer_id;
```

Kết quả cũng gồm khách hàng 1 và 3. Subquery có thể trả `customer_id` trùng lặp; với phép kiểm tra thành viên IN, một giá trị trùng không làm hàng bên ngoài xuất hiện nhiều lần.

### 3.1. Khi IN và EXISTS tương đương trong WHERE

Trong trường hợp cột so sánh không gây khác biệt về NULL và phép so sánh giống nhau, hai dạng sau thường biểu đạt cùng tập hàng:

```sql
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM tuning_orders AS o
    WHERE o.order_status = 'OPEN'
)
```

```sql
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
```

`IN` diễn đạt membership trong tập kết quả; `EXISTS` diễn đạt có hàng con thỏa điều kiện tương quan. Hãy chọn cách dễ đọc nhất theo quan hệ dữ liệu, rồi dùng EXPLAIN để xem MySQL đã chuyển đổi và thực thi như thế nào.

### 3.2. IN với danh sách hằng

`IN` cũng phù hợp với một tập giá trị nhỏ đã biết:

```sql
SELECT order_id, order_status
FROM tuning_orders
WHERE order_status IN ('OPEN', 'PAID');
```

Đây là membership test trực tiếp, không phải lý do để tạo subquery hoặc join không cần thiết.

## 4. Semijoin: cách optimizer xử lý truy vấn chỉ cần hàng bên ngoài

Semijoin là phép kết hợp hai tập nhưng chỉ trả hàng từ phía bên ngoài khi tìm được ít nhất một hàng khớp ở phía bên trong. Nó phù hợp với câu hỏi “có ít nhất một hàng con hay không?”.

Với truy vấn EXISTS/IN ở trên, optimizer có thể chuyển subquery thành semijoin thay vì chạy một subquery độc lập theo cách ngây thơ cho từng hàng ngoài. MySQL có một số chiến lược semijoin:

| Chiến lược | Ý tưởng khái quát |
| --- | --- |
| Table pullout | Đưa bảng từ subquery lên query block ngoài khi phép biến đổi hợp lệ |
| FirstMatch | Dừng tìm trong nhánh con khi tìm được match đầu tiên cho hàng ngoài |
| LooseScan | Dùng index để chọn đại diện phù hợp từ các nhóm giá trị trong một số truy vấn |
| Duplicate Weedout | Thực hiện join rồi loại các hàng ngoài bị lặp bằng cơ chế khử trùng |
| Materialization | Tạo tập kết quả trung gian của subquery rồi tra cứu tập đó |

Optimizer lựa chọn chiến lược dựa trên query shape, index, thống kê và cost. Không cần tự viết lại query để mô phỏng một chiến lược cụ thể trước khi kiểm tra kế hoạch mặc định.

### 4.1. Điều kiện để subquery có thể được chuyển thành semijoin

Các điều kiện chi tiết phụ thuộc phiên bản, nhưng MySQL thường xem xét semijoin transformation cho subquery dạng `[NOT] IN`, `= ANY` hoặc `EXISTS` khi:

- Subquery là một SELECT đơn, không phải UNION.
- Subquery nằm ở vị trí top-level của `WHERE` hoặc `ON`, hoặc là một thành phần của biểu thức AND phù hợp.
- Subquery không chứa aggregate function, `GROUP BY`, `HAVING` hoặc `LIMIT` theo các điều kiện semijoin tương ứng.
- Cấu trúc query block và loại join cho phép biến đổi.
- Không có một số cấu trúc như `STRAIGHT_JOIN` làm hạn chế việc sắp xếp lại join.

Nếu không đủ điều kiện semijoin, MySQL vẫn có thể chọn materialization hoặc cách thực thi subquery khác. Đừng suy luận rằng mọi EXISTS đều tự động thành FirstMatch.

Từ MySQL 8.0.16, optimizer mở rộng semijoin transformation cho các EXISTS predicate đủ điều kiện. Trước đó, một số dạng IN được tối ưu thành semijoin nhưng EXISTS tương đương chưa được xử lý cùng cách. Kiểm tra đúng phiên bản server khi so sánh kế hoạch.

## 5. NOT EXISTS: tìm hàng không có quan hệ tương ứng

`NOT EXISTS` trả TRUE khi subquery không tạo ra hàng nào. Đây là cách rõ ràng để tìm khách hàng chưa từng có đơn hàng:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Kết quả là Dung vì customer 4 không có đơn. Đây là antijoin về mặt quan hệ: chỉ giữ hàng ngoài không có match ở phía trong.

Ví dụ tìm khách hàng không có đơn OPEN:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
ORDER BY c.customer_id;
```

Kết quả gồm Binh, Dung và Ha. Khách hàng 2 có đơn CANCEL nhưng không có đơn OPEN nên vẫn thỏa điều kiện.

## 6. NOT IN và bẫy NULL

`NOT IN` có thể cho kết quả bất ngờ khi subquery trả về `NULL`. SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. Nếu giá trị cần kiểm tra không bằng bất kỳ phần tử nào nhưng tập bên trong có `NULL`, phép `IN` có thể là UNKNOWN; phủ định UNKNOWN vẫn là UNKNOWN. WHERE chỉ giữ hàng có điều kiện TRUE.

Ví dụ tạo tập có NULL:

```sql
SELECT 1 AS customer_id
WHERE 2 NOT IN (1, NULL);
```

Truy vấn không trả hàng. `2` không bằng `1`, nhưng không thể kết luận nó khác `NULL`; kết quả của `2 IN (1, NULL)` là UNKNOWN, nên `NOT IN` cũng UNKNOWN.

### 6.1. So sánh NOT IN với NOT EXISTS

Giả sử một bảng import có `customer_id` nullable:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE c.customer_id NOT IN (
    SELECT i.customer_id
    FROM imported_customer_ids AS i
);
```

Nếu `imported_customer_ids.customer_id` có ít nhất một NULL, nhiều hoặc toàn bộ hàng bên ngoài có thể bị loại do kết quả UNKNOWN.

Viết bằng NOT EXISTS:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM imported_customer_ids AS i
    WHERE i.customer_id = c.customer_id
);
```

NULL trong bảng `i` không tự làm mọi hàng ngoài bị loại. Phép so sánh `i.customer_id = c.customer_id` với NULL không thành TRUE, nên nó không tạo match. Tuy nhiên, nếu `c.customer_id` cũng NULL, phép so sánh thường không TRUE với bất kỳ hàng nào, nên NOT EXISTS có thể giữ hàng đó. Hãy quyết định rõ nghiệp vụ có muốn giữ outer NULL hay không.

### 6.2. Nếu dùng NOT IN, phải xử lý NULL tường minh

Nếu semantics nghiệp vụ yêu cầu bỏ qua NULL trong tập con và khóa ngoài không NULL:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT i.customer_id
      FROM imported_customer_ids AS i
      WHERE i.customer_id IS NOT NULL
  );
```

Nếu cột inner được khai báo `NOT NULL`, bẫy NULL ở phía inner không xảy ra, nhưng vẫn cần xem xét NULL phía outer và ý nghĩa kết quả.

### 6.3. MySQL antijoin transformation

Từ MySQL 8.0.17, nhiều predicate `NOT EXISTS`/`NOT IN` đủ điều kiện có thể được optimizer chuyển thành antijoin. Tuy nhiên, nullable expressions có thể ngăn transformation vì phải bảo toàn semantics ba giá trị. Một số dạng `IS NOT FALSE` hoặc `IS NOT TRUE` có thể cho optimizer thêm cơ hội biến đổi trong những trường hợp được hỗ trợ, nhưng chỉ dùng khi đã chứng minh semantics đúng.

Đừng thêm `IS NOT NULL` chỉ để ép optimizer nếu điều đó thay đổi kết quả nghiệp vụ. Tính đúng đắn của NULL phải được quyết định trước tối ưu.

## 7. LEFT JOIN ... IS NULL: cách viết anti-join khác

Có thể tìm hàng không có match bằng LEFT JOIN và kiểm tra một cột phía phải là NULL:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
LEFT JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

`order_id` là primary key và `NOT NULL` trong bảng bên phải. Vì vậy, nếu `o.order_id IS NULL`, đó là hàng NULL-extended do không tìm được match.

### 7.1. Đặt điều kiện bảng con trong ON

Muốn tìm khách hàng không có đơn OPEN, điều kiện trạng thái phải ở ON:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
LEFT JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'OPEN'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Nếu đặt `o.order_status = 'OPEN'` trong WHERE:

```sql
-- Sai cho mục tiêu anti-join này
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
LEFT JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'OPEN'
  AND o.order_id IS NULL;
```

Điều kiện WHERE trên bảng phải loại các hàng NULL-extended, khiến LEFT JOIN mất ý nghĩa giữ hàng không có match. Kết quả thường rỗng vì một hàng không thể vừa có status OPEN vừa có order_id NULL.

### 7.2. Chọn cột kiểm tra NULL đúng

Hãy kiểm tra cột bên phải chắc chắn `NOT NULL` khi có hàng thật. Dùng primary key là lựa chọn rõ ràng:

```sql
WHERE o.order_id IS NULL
```

Không tùy tiện kiểm tra một cột nullable như `o.note IS NULL`, vì hàng có match thật nhưng `note` NULL cũng có thể bị hiểu nhầm là không có hàng.

## 8. Correlated subquery và công việc lặp theo hàng ngoài

Correlated subquery tham chiếu cột từ query block bên ngoài. Ví dụ:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

Điều kiện `o.customer_id = c.customer_id` là tương quan. Về mặt logic, subquery phụ thuộc giá trị của hàng ngoài. Nếu optimizer không decorrelate hoặc chọn semijoin, kế hoạch có thể thực hiện một lần tra cứu cho mỗi hàng ngoài. Khi outer table có hàng triệu dòng và inner access path kém, chi phí lặp có thể lớn.

Điều đó không có nghĩa correlated subquery luôn chậm. Với index tốt, outer set nhỏ và EXISTS dừng sau match đầu tiên, correlated lookup có thể rất hiệu quả. Hãy kiểm tra `loops` và actual rows thay vì loại bỏ correlated subquery theo quy tắc máy móc.

### 8.1. Dấu hiệu truy vấn con lặp không cần thiết

- Một scalar subquery giống nhau xuất hiện nhiều lần trong SELECT list và WHERE.
- Cùng một bảng con được quét lại để tính COUNT, SUM và MAX cho cùng khóa ngoài.
- `EXPLAIN ANALYZE` cho thấy inner operator có loops gần bằng số hàng ngoài.
- Subquery trả aggregate theo từng hàng trong khi có thể tổng hợp một lần theo khóa rồi join.
- Query tính cùng một biểu thức tương quan trong nhiều cột output.

Không phải loops cao luôn là lỗi: nested-loop lookup với index có thể là kế hoạch tối ưu. Vấn đề là tổng công việc thực tế và có phần tính toán trùng nào có thể loại bỏ hay không.

## 9. Dùng EXISTS thay COUNT khi chỉ cần kiểm tra

Ví dụ kiểm tra khách hàng có đơn hàng hay không:

```sql
-- Cách đếm không cần thiết nếu chỉ cần true/false
SELECT c.customer_id
FROM tuning_customers AS c
WHERE (
    SELECT COUNT(*)
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
) > 0;
```

Viết lại:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Nếu cần số lượng đơn hàng để hiển thị, COUNT vẫn là yêu cầu đúng. EXISTS không thể thay thế một giá trị đếm mà ứng dụng thực sự cần.

### 9.1. Đừng dùng COUNT trong JOIN rồi DISTINCT để mô phỏng EXISTS

Nếu chỉ cần danh sách khách hàng có đơn:

```sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM tuning_customers AS c
JOIN tuning_orders AS o
    ON o.customer_id = c.customer_id;
```

Có thể viết gọn theo semantics:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

JOIN tạo hàng trung gian theo số đơn, rồi DISTINCT phải loại bản sao. EXISTS biểu đạt trực tiếp việc chỉ cần hàng ngoài có match.

## 10. Gộp nhiều scalar subquery bằng pre-aggregation

Một mẫu truy vấn dễ phát sinh công việc lặp là tính nhiều chỉ số cho từng khách hàng bằng các subquery tương quan riêng:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM tuning_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count,
    (
        SELECT SUM(o.total_amount)
        FROM tuning_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS lifetime_value,
    (
        SELECT MAX(o.order_date)
        FROM tuning_orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS last_order_date
FROM tuning_customers AS c;
```

Ba subquery cùng lọc theo `customer_id`. Một kế hoạch có thể phải thực hiện nhiều lần tra cứu cùng tập đơn hàng cho mỗi khách hàng. Có thể tổng hợp một lần theo khách hàng rồi join:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.order_count, 0) AS order_count,
    s.lifetime_value,
    s.last_order_date
FROM tuning_customers AS c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS lifetime_value,
        MAX(order_date) AS last_order_date
    FROM tuning_orders
    GROUP BY customer_id
) AS s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Derived table tạo một hàng tổng hợp cho mỗi customer có đơn. LEFT JOIN giữ khách hàng không có đơn; `COALESCE` đổi COUNT thiếu thành 0. `SUM` và `MAX` vẫn là NULL với khách hàng không có đơn, đây có thể là cách biểu đạt phù hợp. Nếu nghiệp vụ yêu cầu 0 hoặc ngày mặc định, hãy quyết định rõ thay vì tự động thay mọi NULL.

### 10.1. Khi pre-aggregation có lợi?

- Cần nhiều aggregate từ cùng một bảng con theo cùng khóa.
- Outer table có nhiều hàng và mỗi correlated subquery lặp cùng một phép lọc.
- Có thể quét tập con một lần, group theo khóa rồi join kết quả.
- Có index hoặc điều kiện lọc giúp giảm số hàng trước khi aggregate.

### 10.2. Khi correlated aggregate vẫn hợp lý?

Nếu outer query chỉ trả 5 khách hàng trong bảng hàng triệu khách hàng, index trên `tuning_orders(customer_id)` có thể khiến vài correlated lookups rẻ hơn việc aggregate toàn bộ bảng orders. Pre-aggregation không tự động tốt hơn; nó có thể đọc và group dữ liệu của mọi khách hàng dù query chỉ cần một vài khách hàng.

Có thể lọc outer set trước rồi tổng hợp chỉ các customer liên quan:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    s.order_count,
    s.total_amount
FROM tuning_customers AS c
JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS order_count,
        SUM(o.total_amount) AS total_amount
    FROM tuning_orders AS o
    JOIN tuning_customers AS selected_customer
        ON selected_customer.customer_id = o.customer_id
    WHERE selected_customer.region_code = 'NORTH'
    GROUP BY o.customer_id
) AS s
    ON s.customer_id = c.customer_id
WHERE c.region_code = 'NORTH';
```

Đây chỉ là một mẫu minh họa; optimizer có thể merge/materialize derived table theo query shape. Kiểm tra actual rows để biết có thực sự giảm công việc hay không.

## 11. EXISTS với điều kiện phức hợp và index

Ví dụ tìm khách hàng có đơn OPEN từ một ngày trở đi:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
      AND o.order_date >= '2026-11-01'
);
```

Index hiện có `(customer_id, order_status)` hỗ trợ hai điều kiện equality theo thứ tự đầu index, nhưng không chứa `order_date`. Nếu workload thường xuyên lọc theo cả ba cột, có thể cân nhắc:

```sql
CREATE INDEX idx_tuning_orders_customer_status_date
ON tuning_orders (customer_id, order_status, order_date);
```

Index này cho phép lookup theo customer và status rồi range scan theo ngày. Nhưng index mới làm tăng dung lượng và chi phí ghi. Chỉ thêm khi workload và EXPLAIN/ANALYZE chứng minh có lợi.

### 11.1. Index cho NOT EXISTS

Với:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
)
```

Index `(customer_id, order_status)` phù hợp vì optimizer có thể tìm nhanh hàng con theo hai equality. Nếu truy vấn chủ yếu lọc theo status toàn cục rồi ngày, index `(order_status, order_date, customer_id)` có thể phục vụ một workload khác. Không có một thứ tự index đúng cho mọi câu query.

### 11.2. Sargability

Giữ cột được index ở dạng có thể so sánh trực tiếp. Ví dụ tránh:

```sql
WHERE DATE(o.order_date) = '2026-11-04'
```

Vì `order_date` đã là DATE, điều kiện có thể viết trực tiếp:

```sql
WHERE o.order_date = '2026-11-04'
```

Với DATETIME, dùng khoảng nửa mở để tận dụng range access:

```sql
WHERE o.created_at >= '2026-11-04 00:00:00'
  AND o.created_at <  '2026-11-05 00:00:00'
```

## 12. Subquery có GROUP BY/aggregate: khi semijoin không áp dụng trực tiếp

Semijoin transformation có giới hạn. Một subquery có `GROUP BY`, aggregate hoặc HAVING có thể không đủ điều kiện chuyển thành semijoin theo các quy tắc thông thường. Ví dụ:

```sql
SELECT c.customer_id
FROM tuning_customers AS c
WHERE (
    SELECT COUNT(*)
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
) >= 2;
```

Đây là scalar correlated aggregate: mỗi customer cần một giá trị count. Nếu cần lọc theo số đơn và/hoặc hiển thị nhiều aggregate, pre-aggregate thường là phương án đáng thử:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    s.order_count
FROM tuning_customers AS c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM tuning_orders
    GROUP BY customer_id
    HAVING COUNT(*) >= 2
) AS s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Derived table chỉ chứa customer có ít nhất hai đơn, nên INNER JOIN phù hợp. Nếu muốn giữ cả customer không có đơn và hiển thị count 0, dùng LEFT JOIN với aggregate không lọc HAVING rồi đặt điều kiện lọc đúng ở query ngoài theo yêu cầu.

## 13. Subquery lặp trong SELECT list và CTE

Nếu cùng một phép tính được tham chiếu nhiều lần, có thể đặt phép tính vào derived table hoặc CTE để query dễ đọc và tránh viết lại logic:

```sql
WITH customer_order_summary AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS total_amount
    FROM tuning_orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.order_count, 0) AS order_count,
    s.total_amount
FROM tuning_customers AS c
LEFT JOIN customer_order_summary AS s
    ON s.customer_id = c.customer_id;
```

CTE giúp đặt tên cho tập tổng hợp và tái sử dụng biểu thức trong câu SQL. Tuy nhiên, không nên giả định mọi CTE luôn được materialize đúng một lần hoặc luôn nhanh hơn derived table. MySQL có thể merge hoặc materialize CTE/derived table tùy cấu trúc và cost; CTE được tham chiếu nhiều lần có quy tắc tối ưu riêng. Hãy kiểm tra EXPLAIN.

## 14. IN subquery, materialization và semijoin

Subquery IN không tương quan có thể được materialize thành tập kết quả trung gian, sau đó dùng để kiểm tra membership. Ví dụ:

```sql
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM tuning_orders AS o
    WHERE o.order_status = 'PAID'
);
```

Materialization có thể phù hợp nếu tập con được tạo một lần và tra cứu nhiều lần. Với một số query shape, semijoin có thể tốt hơn vì optimizer sắp xếp join và chọn chiến lược như FirstMatch hoặc Duplicate Weedout.

Không thêm `DISTINCT` vào subquery IN chỉ để loại duplicate theo thói quen:

```sql
WHERE c.customer_id IN (
    SELECT DISTINCT o.customer_id
    FROM tuning_orders AS o
    WHERE o.order_status = 'PAID'
)
```

Đối với membership test, duplicate trong tập IN không làm thay đổi kết quả logic. DISTINCT có thể tạo thêm công việc sort/deduplicate hoặc ảnh hưởng khả năng semijoin transformation tùy query shape. Chỉ dùng khi có lý do ngữ nghĩa khác.

## 15. EXPLAIN: xem optimizer đã làm gì

Trước khi viết lại, lưu kế hoạch của query hiện tại:

```sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

Quan sát:

- Subquery còn là dependent subquery hay được chuyển thành semijoin.
- Có lookup theo `idx_tuning_orders_customer_status` hay không.
- Có materialization hoặc duplicate weedout không.
- Số hàng ước lượng ở outer và inner.
- Có sort, temporary table hoặc scan rộng không.

Trong traditional EXPLAIN, `DEPENDENT SUBQUERY` cho biết subquery phụ thuộc query block ngoài. Đây là tín hiệu cần xem loops và số hàng, không phải bằng chứng tự thân rằng query chậm. Một correlated lookup theo primary/unique index có thể rất rẻ.

### 15.1. EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT c.customer_id, c.customer_name
FROM tuning_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM tuning_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

`EXPLAIN ANALYZE` thực thi SELECT thật và hiển thị actual time, actual rows và loops. Đặc biệt chú ý:

- Inner lookup chạy bao nhiêu loops.
- Mỗi loop đọc bao nhiêu hàng.
- Có operator nào lặp hàng nghìn lần không cần thiết.
- Ước lượng rows có khác xa actual rows không.
- Thời gian thực tế tập trung ở operator nào.

Chỉ dùng trên truy vấn có phạm vi phù hợp; đây không phải lệnh chỉ đọc metadata. Không chạy một truy vấn nặng trên bảng production trong giờ cao điểm chỉ để thử nghiệm.

### 15.2. So sánh ba dạng query

Hãy đo cùng một yêu cầu bằng:

1. `EXISTS` correlated.
2. `IN (subquery)`.
3. JOIN với `DISTINCT` hoặc derived table tương ứng.

Đảm bảo các câu có semantics giống nhau, cùng filter và cùng tập dữ liệu. So sánh actual rows, loops, latency và tài nguyên. Đừng chỉ so sánh số dòng SQL hoặc cost ước lượng.

## 16. Khi nào nên giữ subquery, khi nào nên viết lại?

| Tình huống | Cách viết đáng thử trước | Lý do |
| --- | --- | --- |
| Chỉ cần biết có hàng con | `EXISTS` | Diễn đạt trực tiếp existence và không nhân bản hàng ngoài |
| Kiểm tra giá trị thuộc tập con | `IN (subquery)` | Diễn đạt membership rõ ràng; optimizer có thể semijoin/materialize |
| Tìm hàng ngoài không có match | `NOT EXISTS` | Tránh bẫy NULL của NOT IN |
| Tìm hàng ngoài không có match bằng join | `LEFT JOIN ... IS NULL` | Dùng được nếu kiểm tra cột inner NOT NULL và đặt điều kiện đúng trong ON |
| Cần nhiều aggregate của cùng bảng con theo cùng khóa | Derived table/CTE pre-aggregation | Tránh nhiều scalar subquery lặp cùng phép lọc |
| Outer set rất nhỏ, inner có index tốt | Correlated lookup có thể giữ nguyên | Chỉ đọc một vùng nhỏ thay vì aggregate toàn bộ inner table |
| Subquery chứa aggregate/HAVING | Scalar subquery hoặc pre-aggregation | Semijoin transformation có thể không áp dụng trực tiếp |
| Subquery có NULL và dùng phủ định | `NOT EXISTS` hoặc lọc NULL tường minh | Bảo toàn semantics ba giá trị |

Không có một phép rewrite luôn nhanh hơn. Mục tiêu là loại công việc trùng mà không tăng số hàng trung gian hoặc buộc quét toàn bộ bảng không cần thiết.

## 17. Những giới hạn và lưu ý về optimizer

- Semijoin/antijoin transformation chỉ áp dụng khi query shape đáp ứng điều kiện của MySQL.
- Subquery có aggregate, `GROUP BY`, `HAVING`, `LIMIT`, UNION hoặc vị trí biểu thức không phù hợp có thể không được chuyển theo cách mong muốn.
- Nullable expressions có thể hạn chế antijoin transformation vì optimizer phải bảo toàn semantics NULL.
- `IN` và `EXISTS` có thể có kết quả khác nhau trong biểu thức SELECT/CASE khi kết quả UNKNOWN được quan sát; đừng chỉ dựa vào việc WHERE loại UNKNOWN.
- `NOT IN` đặc biệt nhạy với NULL ở inner result.
- `DISTINCT` trong membership subquery thường không cần thiết nếu chỉ muốn loại trùng cho mục tiêu logic IN.
- Correlated subquery không mặc định chậm; index và số hàng outer quyết định nhiều tới chi phí.
- Derived table/CTE có thể được merge hoặc materialize; cần đọc plan thay vì giả định.
- `EXPLAIN ANALYZE` chạy truy vấn thật và có thể gây tải.

## 18. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `COUNT(*) > 0` chỉ để kiểm tra tồn tại | Đếm nhiều hàng không cần thiết | Dùng EXISTS |
| Dùng JOIN khi chỉ cần biết có hàng con | Nhân bản hàng ngoài rồi phải DISTINCT | Dùng EXISTS/semijoin |
| Cho rằng IN luôn chậm hơn EXISTS | Rewrite không có cơ sở và có thể làm plan kém hơn | So sánh semantics và EXPLAIN |
| Dùng NOT IN khi inner có thể chứa NULL | Kết quả UNKNOWN làm mất hàng ngoài | Dùng NOT EXISTS hoặc lọc NULL rõ ràng |
| Dùng LEFT JOIN anti-join rồi đặt điều kiện inner ở WHERE | Loại hàng NULL-extended | Đưa điều kiện match vào ON |
| Kiểm tra một cột nullable bằng IS NULL | Nhầm hàng match thật có NULL thành không match | Kiểm tra primary key/cột NOT NULL phía inner |
| Lặp nhiều scalar subquery cùng bảng con | Lặp scan/lookup và aggregate | Pre-aggregate một lần nếu workload phù hợp |
| Luôn thay correlated subquery bằng GROUP BY toàn bảng | Đọc và tổng hợp quá nhiều dữ liệu khi outer set nhỏ | So sánh với indexed correlated lookup |
| Thêm DISTINCT vào IN theo thói quen | Thêm công việc loại trùng không cần thiết | Bỏ DISTINCT nếu semantics membership không cần |
| Không có index cho correlation predicate | Inner lookup phải scan nhiều hàng | Index theo khóa tương quan và filter |
| Đánh giá chỉ bằng EXPLAIN estimated rows | Bỏ qua loops và actual runtime | Dùng EXPLAIN ANALYZE có kiểm soát |

## 19. Bài tập thực hành

1. Viết truy vấn lấy khách hàng có ít nhất một đơn OPEN bằng EXISTS và IN. So sánh kết quả.
2. Viết lại JOIN tạo duplicate khách hàng thành EXISTS. Xác nhận Chi chỉ xuất hiện một lần.
3. Viết truy vấn lấy khách hàng không có đơn nào bằng NOT EXISTS.
4. Tạo bảng import có customer_id NULL. So sánh `NOT IN` và `NOT EXISTS`, giải thích kết quả bằng logic ba giá trị.
5. Viết anti-join bằng LEFT JOIN. Đặt điều kiện status trong ON; sau đó cố ý chuyển sang WHERE và giải thích kết quả thay đổi.
6. Thay `COUNT(*) > 0` bằng EXISTS. Dùng EXPLAIN ANALYZE để so sánh loops và actual rows.
7. Viết truy vấn có ba scalar subquery tính COUNT, SUM và MAX cho mỗi customer. Viết lại bằng derived table pre-aggregation.
8. Lọc outer set chỉ còn khách hàng ở NORTH. So sánh correlated aggregate với aggregate toàn bảng rồi join.
9. Thêm index `(customer_id, order_status, order_date)`. Chạy EXPLAIN cho EXISTS có điều kiện ngày trước và sau index.
10. Viết truy vấn IN có DISTINCT và không DISTINCT. So sánh plan và giải thích vì sao duplicate không làm thay đổi membership.
11. Thử một subquery có GROUP BY/HAVING và quan sát optimizer có còn dùng semijoin transformation hay không.
12. Chạy EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE cho các dạng tương đương; ghi nhận operator đầu tiên có loops hoặc actual rows cao.

## 20. Checklist tối ưu EXISTS/IN và subquery

- [ ] Đã xác định yêu cầu là existence, membership, non-existence hay aggregate value.
- [ ] Dùng EXISTS khi chỉ cần biết có hàng khớp.
- [ ] Không dùng COUNT chỉ để kiểm tra số lượng lớn hơn 0.
- [ ] Đã kiểm tra NULL ở cả outer expression và inner result trước khi dùng NOT IN.
- [ ] NOT EXISTS/LEFT JOIN anti-join giữ đúng semantics và cột kiểm tra NULL là NOT NULL.
- [ ] Điều kiện match của LEFT JOIN nằm trong ON khi cần giữ hàng không có match.
- [ ] Không thêm DISTINCT vào IN nếu chỉ để loại duplicate không ảnh hưởng membership.
- [ ] Đã rà soát scalar subquery lặp cùng một phép tính.
- [ ] Đã cân nhắc pre-aggregation khi nhiều aggregate dùng cùng tập con.
- [ ] Đã cân nhắc correlated lookup khi outer set nhỏ và inner index tốt.
- [ ] Có index phù hợp cho correlation predicate và filter.
- [ ] Đã kiểm tra query shape có đủ điều kiện semijoin/antijoin hay không.
- [ ] Đã đọc EXPLAIN và actual loops/rows bằng EXPLAIN ANALYZE an toàn.
- [ ] Đã so sánh các phương án có cùng semantics và dữ liệu đại diện.
- [ ] Không rewrite hoặc thêm hint chỉ dựa trên quy tắc “IN chậm hơn EXISTS”.

## 21. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể viết truy vấn existence bằng EXISTS, membership bằng IN, anti-join bằng NOT EXISTS hoặc LEFT JOIN đúng cách, giải thích bẫy NULL của NOT IN, nhận biết correlated subquery có thể lặp công việc, gộp nhiều aggregate bằng pre-aggregation khi phù hợp và kiểm chứng semijoin/materialization bằng EXPLAIN/EXPLAIN ANALYZE. Bạn cũng cần giải thích được vì sao một rewrite đúng về cú pháp vẫn có thể chậm hơn nếu thay đổi cardinality, access path hoặc lượng dữ liệu phải đọc.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Semijoin and Antijoin Transformations](https://dev.mysql.com/doc/refman/8.4/en/semijoins-antijoins.html)
- [MySQL 8.4 Reference Manual — Optimizing Subqueries, Derived Tables, and View References](https://dev.mysql.com/doc/refman/8.4/en/subquery-optimization.html)
- [MySQL 8.4 Reference Manual — Optimizing IN and EXISTS Subquery Predicates](https://dev.mysql.com/doc/refman/8.4/en/subquery-optimization-with-exists.html)
- [MySQL 8.4 Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
