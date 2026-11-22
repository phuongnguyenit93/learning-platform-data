# Thu nhỏ câu lệnh lỗi và kiểm chứng từng CTE hoặc truy vấn con

Một truy vấn SQL phức tạp có thể gồm nhiều CTE, JOIN, truy vấn con, phép tổng hợp, window function và bộ lọc. Khi kết quả sai hoặc câu lệnh phát sinh lỗi, việc đọc toàn bộ câu SQL rồi đoán nguyên nhân thường mất nhiều thời gian. Cách hiệu quả hơn là **thu nhỏ truy vấn theo từng bước, giữ lại điều kiện tái hiện lỗi và kiểm chứng từng phần độc lập**.

Mục tiêu không chỉ là làm câu SQL ngắn hơn. Ta cần tạo ra ví dụ nhỏ nhất có thể mà vẫn tái hiện được vấn đề, sau đó xác định chính xác thành phần gây lỗi:

- CTE nào tạo ra hàng sai hoặc kiểu dữ liệu không mong đợi?
- JOIN nào làm nhân bản hàng?
- Subquery nào trả về nhiều hàng trong khi biểu thức chỉ chấp nhận một giá trị?
- Điều kiện nào làm mất hàng hoặc xử lý NULL khác dự kiến?
- Phép GROUP BY, window function hay thứ tự phân trang nào làm thay đổi kết quả?
- Lỗi đến từ dữ liệu, schema, tham số, dialect hay query plan?

Bài học thuộc chương **Kiểm thử và gỡ lỗi** của module **Database SQL**. Nội dung sử dụng ví dụ SQL và Java/JDBC, đồng thời lưu ý khác biệt giữa PostgreSQL, MySQL, MariaDB, SQL Server, Oracle và SQLite.

> Các ví dụ dùng cú pháp SQL phổ biến; một số hàm, kiểu dữ liệu, toán tử so sánh tập hợp, cú pháp giới hạn hàng và cách tạo bảng tạm phụ thuộc DBMS. Hãy chạy trên database test có schema tương ứng. Không chạy câu lệnh phá hủy dữ liệu trên production để thử nghiệm.

## 1. Thu nhỏ truy vấn là gì?

Thu nhỏ truy vấn (*query reduction*) là quá trình loại bỏ dần những phần không cần thiết nhưng vẫn giữ được lỗi hoặc kết quả sai đang điều tra.

Giả sử truy vấn ban đầu dài 120 dòng, có 7 CTE và 4 subquery. Ta muốn tìm phần nhỏ nhất vẫn lỗi. Có thể bắt đầu từ:

```sql
WITH
base_orders AS (
    SELECT ...
),
eligible_customers AS (
    SELECT ...
),
item_totals AS (
    SELECT ...
),
payment_totals AS (
    SELECT ...
),
customer_summary AS (
    SELECT ...
),
ranked_customers AS (
    SELECT ...
),
final_rows AS (
    SELECT ...
)
SELECT ...
FROM final_rows;
```

Sau khi thu nhỏ, có thể phát hiện lỗi nằm ở JOIN giữa item totals và payment totals, hoặc một subquery trong CTE thứ ba. Khi đó ta có ví dụ nhỏ để kiểm chứng, sửa và viết regression test.

### 1.1. Ba mục tiêu khác nhau

| Mục tiêu | Câu hỏi cần trả lời | Cách kiểm chứng |
|---|---|---|
| Tái hiện lỗi | Phần SQL nhỏ nhất nào vẫn lỗi? | Chạy lại cùng tham số và dữ liệu |
| Xác định ngữ nghĩa | CTE/subquery tạo ra tập hàng nào? | SELECT trực tiếp, đếm hàng, xem khóa và NULL |
| Xác định hiệu năng | Phần nào gây chậm hoặc tốn tài nguyên? | EXPLAIN/actual plan, số hàng, thời gian |

Đừng trộn ba mục tiêu. Một query có thể trả kết quả đúng nhưng chậm; hoặc chạy nhanh nhưng trả kết quả sai. Thu nhỏ để tìm lỗi logic cần giữ tiêu chí kết quả sai; thu nhỏ để tìm lỗi hiệu năng cần giữ workload và đặc điểm cardinality tương ứng.

### 1.2. “Ngắn hơn” không có nghĩa là “tương đương”

Nếu bỏ một JOIN, predicate hoặc DISTINCT, truy vấn có thể không còn tái hiện lỗi vì ta đã thay đổi ý nghĩa.

Ví dụ, lỗi chỉ xảy ra khi một khách hàng có hai đơn và mỗi đơn có ba dòng hàng. Nếu thu nhỏ dữ liệu còn một đơn một dòng, hiện tượng nhân bản có thể biến mất.

Vì vậy, mỗi lần xóa hoặc thay đổi một phần, phải chạy lại **đúng phép thử đang thất bại**. Nếu lỗi biến mất, hoàn tác thay đổi đó hoặc tìm cách thu nhỏ khác vẫn giữ điều kiện cần thiết.

## 2. Trước khi thu nhỏ: ghi lại một lần chạy có thể tái hiện

Đừng bắt đầu bằng việc xóa SQL. Trước tiên, lưu bằng chứng của lần chạy lỗi.

### 2.1. Thu thập câu SQL và tham số thật

Ghi lại:

- SQL sau khi ứng dụng dựng query.
- Thứ tự placeholder và kiểu JDBC của từng tham số.
- Giá trị đại diện trong môi trường test; che dữ liệu nhạy cảm.
- DBMS và phiên bản.
- Driver JDBC và phiên bản.
- Schema liên quan: kiểu cột, NULL/NOT NULL, PK, FK, UNIQUE, index.
- Isolation level và transaction context.
- SQLSTATE/vendor error code nếu có.
- Kết quả mong đợi và kết quả thực tế.
- Điều kiện dữ liệu làm lỗi xuất hiện.

Ví dụ, hai tham số cùng in ra là `10` nhưng một tham số bind bằng INTEGER, tham số kia bind bằng VARCHAR. Ép kiểu ngầm có thể làm khác kết quả hoặc khiến index không được dùng.

### 2.2. Giữ kiểu tham số khi tái hiện

```java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setTimestamp(2, Timestamp.from(fromInstant));
    ps.setTimestamp(3, Timestamp.from(toInstant));
    ps.setString(4, status);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả để đối chiếu.
        }
    }
}
```

Khi chuyển query sang SQL console, cần giữ đúng kiểu dữ liệu, timezone và giá trị. Không thay tham số ngày giờ thành chuỗi tùy ý rồi kết luận query trong ứng dụng sai.

### 2.3. Giữ snapshot dữ liệu nhất quán

Nếu nhiều bảng thay đổi trong lúc kiểm tra, lần chạy query ban đầu và lần chạy từng CTE có thể nhìn thấy dữ liệu khác nhau.

Khi cần so sánh chính xác:

- Dùng database test với fixture cố định.
- Hoặc chạy các bước trong cùng transaction/snapshot nếu DBMS và isolation hỗ trợ.
- Ghi rõ thời điểm dữ liệu hoặc ID các hàng liên quan.
- Không so sánh kết quả lấy ở hai thời điểm khác nhau rồi quy mọi khác biệt cho SQL.

### 2.4. Viết lại tiêu chí tái hiện thành một câu kiểm tra

Ví dụ:

- “Query trả 8 dòng nhưng mong đợi 4 dòng.”
- “CTE payment_totals có hai hàng cho cùng order_id.”
- “Subquery scalar báo lỗi vì trả về nhiều hơn một hàng.”
- “Kết quả tháng 3 thiếu đơn có ngày cuối tháng.”
- “Query chạy 9 giây khi tenant có hơn 100.000 đơn.”

Tiêu chí càng cụ thể, việc thu nhỏ càng ít bị lệch hướng.

## 3. Sơ đồ phụ thuộc CTE và truy vấn con

CTE thường tham chiếu CTE được khai báo trước đó. Hãy vẽ đồ thị phụ thuộc trước khi tách.

```sql
WITH
orders_in_range AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE tenant_id = ?
),
items_per_order AS (
    SELECT order_id, SUM(quantity) AS item_count
    FROM order_items
    GROUP BY order_id
),
payments_per_order AS (
    SELECT order_id, SUM(amount) AS paid_amount
    FROM payments
    GROUP BY order_id
),
customer_totals AS (
    SELECT
        o.customer_id,
        SUM(o.total_amount) AS order_total,
        SUM(p.paid_amount) AS paid_total
    FROM orders_in_range AS o
    LEFT JOIN payments_per_order AS p
      ON p.order_id = o.order_id
    GROUP BY o.customer_id
)
SELECT *
FROM customer_totals;
```

Đồ thị phụ thuộc:

```text
orders ───────> orders_in_range ──────┐
                                      |
payments ─────> payments_per_order ───┼──> customer_totals ──> final SELECT
                                      |
order_items ──> items_per_order ──────┘
```

Trong ví dụ này, items_per_order được khai báo nhưng chưa được sử dụng trong customer_totals; đó là một phần có thể loại khỏi bản thu nhỏ nếu không liên quan lỗi.

### 3.1. Xác định thứ tự kiểm chứng

1. Kiểm chứng CTE nguồn không phụ thuộc CTE khác.
2. Kiểm chứng CTE phụ thuộc một CTE nguồn.
3. Kiểm chứng CTE phụ thuộc nhiều CTE.
4. Kiểm chứng SELECT cuối cùng.
5. Kiểm chứng các biểu thức subquery nằm trong từng CTE.

Không cần chạy toàn bộ chuỗi mỗi lần. Có thể giữ các CTE phụ thuộc cần thiết rồi thay SELECT cuối bằng một phép kiểm tra nhỏ.

### 3.2. CTE không mặc nhiên là bảng tạm vật lý

CTE là cách đặt tên cho một biểu thức truy vấn. DBMS có thể inline, materialize hoặc tối ưu hóa lại tùy hệ quản trị, phiên bản và cấu trúc query.

- Dùng CTE để **tách logic và kiểm chứng kết quả**.
- Không mặc nhiên kết luận mỗi CTE được thực thi đúng một lần.
- Không coi CTE là ranh giới tối ưu hóa cố định.
- Dùng execution plan để hiểu cách DBMS thực thi.

Một CTE có thể rất hữu ích khi debug dù optimizer không tạo bảng tạm cho nó.
## 4. Quy trình thu nhỏ truy vấn theo từng bước

Quy trình dưới đây phù hợp khi một query lớn trả lỗi hoặc kết quả sai.

### Bước 1: Lưu nguyên bản

Tạo bản sao truy vấn ban đầu trong file hoặc SQL editor. Ghi tham số, kiểu dữ liệu, thời điểm và kết quả lỗi. Không chỉnh sửa trực tiếp bản duy nhất đang dùng để đối chiếu.

### Bước 2: Xác định lớp lỗi

Phân loại ban đầu:

- Lỗi parse/syntax.
- Lỗi tên bảng, cột hoặc alias.
- Lỗi kiểu dữ liệu/cast.
- Lỗi scalar subquery trả nhiều hàng.
- Lỗi constraint hoặc permission.
- Query chạy được nhưng thiếu/thừa hàng.
- Giá trị aggregate sai.
- Kết quả đúng nhưng query quá chậm.

Lỗi syntax thường có thể thu nhỏ bằng cách bỏ từng CTE/biểu thức cho tới khi parser chấp nhận. Lỗi logic cần giữ lại dữ liệu gây sai và so sánh kết quả. Lỗi hiệu năng cần giữ cardinality và phân bố dữ liệu đủ gần workload thực tế.

### Bước 3: Thay SELECT cuối bằng phép kiểm tra đơn giản

Thay vì đọc tất cả cột và tính toán cuối, hãy xem số hàng:

```sql
WITH
base_rows AS (
    SELECT ...
),
filtered_rows AS (
    SELECT ...
    FROM base_rows
)
SELECT COUNT(*) AS row_count
FROM filtered_rows;
```

Sau đó xem một số hàng:

```sql
WITH
base_rows AS (
    SELECT ...
),
filtered_rows AS (
    SELECT ...
    FROM base_rows
)
SELECT *
FROM filtered_rows
ORDER BY primary_key
FETCH FIRST 20 ROWS ONLY;
```

Cú pháp giới hạn hàng khác nhau giữa DBMS; PostgreSQL/MySQL thường dùng LIMIT, SQL Server có TOP/OFFSET FETCH, Oracle hỗ trợ FETCH FIRST ở các phiên bản hiện đại.

### Bước 4: Giảm projection nhưng giữ biểu thức gây lỗi

Nếu lỗi do một cột không tồn tại hoặc cast sai, bỏ projection không liên quan giúp tập trung hơn. Nhưng đừng xóa chính biểu thức đang gây lỗi.

```sql
SELECT
    order_id,
    customer_id,
    CAST(total_amount AS DECIMAL(12,2)) AS total_amount
FROM source_orders;
```

Nếu lỗi nằm ở phép CAST, giữ CAST và giảm các cột khác.

### Bước 5: Bỏ từng JOIN có kiểm soát

Mỗi lần bỏ một JOIN:

1. Ghi lại số hàng trước và sau.
2. Kiểm tra khóa nối có unique không.
3. Kiểm tra có hàng mồ côi hoặc NULL không.
4. Chạy lại tiêu chí lỗi.
5. Nếu lỗi biến mất, JOIN đó hoặc tương tác của nó là điều kiện cần.

Đừng xóa tất cả JOIN một lúc. Làm vậy có thể làm mất nguyên nhân nhân bản hàng hoặc mất hàng.

### Bước 6: Thu hẹp predicate và tập dữ liệu

Có thể giới hạn bằng một tenant, một khoảng ngày hoặc một tập ID. Nhưng phải giữ đặc điểm dữ liệu gây lỗi.

Ví dụ nếu lỗi do trùng khóa, hãy giữ ít nhất hai hàng có cùng giá trị khóa. Nếu lỗi do phép chia cho 0, phải giữ hàng có mẫu số bằng 0. Nếu lỗi do fan-out, phải giữ số hàng quan hệ đủ để tái hiện phép nhân.

### Bước 7: Tách từng CTE

Giữ các CTE nguồn cần thiết và chạy SELECT trực tiếp trên CTE đang điều tra:

```sql
WITH
source_rows AS (
    SELECT ...
),
normalized_rows AS (
    SELECT ...
    FROM source_rows
)
SELECT *
FROM normalized_rows;
```

Nếu normalized_rows đã sai, chưa cần kiểm tra CTE phía sau. Nếu nó đúng, chuyển sang CTE tiếp theo.

### Bước 8: Tách subquery

Thay subquery bằng một truy vấn độc lập với cùng correlation key và tham số. Xác định nó trả 0, 1 hay nhiều hàng; kiểm tra NULL và duplicate.

### Bước 9: Tạo truy vấn tối thiểu

Loại bỏ mọi thành phần không cần thiết nhưng vẫn tái hiện lỗi. Lưu nó cùng fixture dữ liệu nhỏ nhất. Đây là reproducer để sửa và viết test.

### Bước 10: Chạy lại truy vấn gốc

Sau khi sửa thành phần gây lỗi, chạy lại query tối thiểu, query đầy đủ, regression test với dữ liệu biên và query plan nếu lỗi liên quan hiệu năng.

## 5. Kiểm chứng một CTE độc lập

Giả sử query có:

```sql
WITH active_orders AS (
    SELECT order_id, customer_id, created_at, total_amount
    FROM orders
    WHERE status = 'CONFIRMED'
      AND created_at >= ?
),
large_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM active_orders
    WHERE total_amount >= 1000000
)
SELECT *
FROM large_orders;
```

### 5.1. Kiểm tra số hàng của từng CTE

```sql
WITH active_orders AS (
    SELECT order_id, customer_id, created_at, total_amount
    FROM orders
    WHERE status = 'CONFIRMED'
      AND created_at >= ?
)
SELECT COUNT(*) AS active_order_count
FROM active_orders;
```

Sau đó kiểm tra CTE thứ hai:

```sql
WITH active_orders AS (
    SELECT order_id, customer_id, created_at, total_amount
    FROM orders
    WHERE status = 'CONFIRMED'
      AND created_at >= ?
),
large_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM active_orders
    WHERE total_amount >= 1000000
)
SELECT COUNT(*) AS large_order_count
FROM large_orders;
```

Số hàng phải phù hợp với quy tắc nghiệp vụ và tập fixture. Nếu count thay đổi bất ngờ, xem predicate, NULL, kiểu dữ liệu và giá trị tham số.

### 5.2. Kiểm tra khóa và duplicate

Nếu order_id phải duy nhất trong CTE:

```sql
WITH active_orders AS (
    SELECT order_id, customer_id
    FROM orders
    WHERE status = 'CONFIRMED'
)
SELECT order_id, COUNT(*) AS occurrences
FROM active_orders
GROUP BY order_id
HAVING COUNT(*) > 1;
```

Nếu query trả hàng, giả định duy nhất đã sai hoặc JOIN bên trong CTE đã nhân bản hàng. Đừng thêm DISTINCT ngay để che hiện tượng; trước tiên tìm nguồn duplicate.

### 5.3. Kiểm tra NULL

```sql
WITH active_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE status = 'CONFIRMED'
)
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END) AS null_customer_ids,
    SUM(CASE WHEN total_amount IS NULL THEN 1 ELSE 0 END) AS null_amounts
FROM active_orders;
```

NULL có thể làm predicate, aggregate và JOIN hoạt động khác điều ta tưởng. Ví dụ total_amount >= 1000000 không giữ hàng có total_amount NULL; biểu thức trả UNKNOWN, không phải TRUE.

### 5.4. Kiểm tra min/max và miền giá trị

```sql
WITH active_orders AS (
    SELECT order_id, total_amount, created_at
    FROM orders
    WHERE status = 'CONFIRMED'
)
SELECT
    MIN(total_amount) AS min_amount,
    MAX(total_amount) AS max_amount,
    MIN(created_at) AS first_order,
    MAX(created_at) AS last_order
FROM active_orders;
```

Phép kiểm tra này giúp phát hiện dữ liệu ngoài miền dự kiến, ngày giờ lệch hoặc giá trị cực lớn.

## 6. Kiểm chứng chuỗi nhiều CTE theo thứ tự

Ví dụ cần tính tổng chi tiêu của khách hàng từ các đơn đã xác nhận:

```sql
WITH
confirmed_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE tenant_id = ?
      AND status = 'CONFIRMED'
),
order_payments AS (
    SELECT order_id, SUM(amount) AS paid_amount
    FROM payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
),
order_balances AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.total_amount,
        COALESCE(p.paid_amount, 0) AS paid_amount,
        o.total_amount - COALESCE(p.paid_amount, 0) AS balance
    FROM confirmed_orders AS o
    LEFT JOIN order_payments AS p
      ON p.order_id = o.order_id
),
customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS ordered_total,
        SUM(paid_amount) AS paid_total,
        SUM(balance) AS balance_total
    FROM order_balances
    GROUP BY customer_id
)
SELECT *
FROM customer_totals;
```

Hãy kiểm tra theo thứ tự:

1. confirmed_orders: mỗi hàng là một order? order_id có unique không?
2. order_payments: có đúng một hàng trên mỗi order_id không? Có payment status nào bị lọc nhầm?
3. order_balances: LEFT JOIN có giữ mọi order không? Có nhân bản hàng không?
4. customer_totals: tổng theo customer có khớp với tổng các order balance không?
5. SELECT cuối: thứ tự, lọc, phân trang hoặc join bổ sung có làm đổi kết quả không?

### 6.1. Chạy một CTE cùng các dependency của nó

Nếu CTE C phụ thuộc A và B, giữ A và B nhưng thay SELECT cuối bằng SELECT từ C. Không cần đưa các CTE phía sau vào.

```sql
WITH
a AS (
    SELECT ...
),
b AS (
    SELECT ...
),
c AS (
    SELECT ...
    FROM a
    JOIN b ON ...
)
SELECT *
FROM c;
```

Cách này giữ nguyên ngữ cảnh và tham số của CTE đang kiểm tra.

### 6.2. Kiểm tra invariant giữa các bước

Một invariant là điều kiện phải đúng sau mỗi bước. Ví dụ:

- CTE confirmed_orders: một hàng cho mỗi order_id.
- CTE order_payments: tối đa một hàng cho mỗi order_id vì đã GROUP BY.
- CTE order_balances: số hàng bằng số hàng confirmed_orders.
- CTE customer_totals: một hàng cho mỗi customer_id.

Có thể kiểm chứng bằng COUNT, GROUP BY/HAVING và so sánh khóa. Khi invariant đầu tiên bị phá vỡ, tập trung vào CTE đó thay vì đọc các phép tính cuối.
## 7. Thu nhỏ và kiểm chứng JOIN

JOIN là nguyên nhân phổ biến của kết quả thừa hàng hoặc aggregate sai.

### 7.1. Nhận diện fan-out

Giả sử:

- Một order có 2 dòng hàng.
- Một order có 3 payment.
- JOIN trực tiếp order_items với payments theo order_id.

Kết quả có thể có 2 × 3 = 6 hàng cho order đó. Khi SUM quantity hoặc SUM payment amount, giá trị bị nhân lên.

Ví dụ dễ gây sai:

```sql
SELECT
    o.order_id,
    SUM(i.quantity) AS item_quantity,
    SUM(p.amount) AS paid_amount
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
JOIN payments AS p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

### 7.2. Kiểm tra cardinality trước khi sửa

```sql
SELECT order_id, COUNT(*) AS item_rows
FROM order_items
GROUP BY order_id
HAVING COUNT(*) > 1;
```

```sql
SELECT order_id, COUNT(*) AS payment_rows
FROM payments
GROUP BY order_id
HAVING COUNT(*) > 1;
```

Sau đó kiểm tra số hàng sau JOIN:

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
JOIN payments AS p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

### 7.3. Tổng hợp riêng trước khi JOIN

```sql
WITH
item_totals AS (
    SELECT order_id, SUM(quantity) AS item_quantity
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id, SUM(amount) AS paid_amount
    FROM payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    i.item_quantity,
    p.paid_amount
FROM orders AS o
LEFT JOIN item_totals AS i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
  ON p.order_id = o.order_id;
```

Mỗi CTE tổng hợp có tối đa một hàng cho mỗi order_id, do đó tránh nhân chéo các dòng chi tiết.

### 7.4. INNER JOIN và LEFT JOIN không tương đương

Đổi INNER JOIN thành LEFT JOIN để “giữ tất cả hàng” có thể thay đổi ngữ nghĩa. Ngược lại, điều kiện đặt trong WHERE có thể làm LEFT JOIN hoạt động như INNER JOIN:

```sql
-- Hàng không có payment bị loại vì p.status là NULL.
SELECT o.order_id, p.amount
FROM orders AS o
LEFT JOIN payments AS p
  ON p.order_id = o.order_id
WHERE p.status = 'SETTLED';
```

Nếu muốn giữ order không có payment và chỉ ghép payment settled, predicate có thể cần đặt trong ON:

```sql
SELECT o.order_id, p.amount
FROM orders AS o
LEFT JOIN payments AS p
  ON p.order_id = o.order_id
 AND p.status = 'SETTLED';
```

Khi thu nhỏ, không di chuyển predicate giữa ON và WHERE nếu chưa xác định đó có phải nguyên nhân lỗi hay không.

## 8. Thu nhỏ và kiểm chứng truy vấn con

Có nhiều loại subquery và mỗi loại có quy tắc riêng.

### 8.1. Scalar subquery

Scalar subquery được dùng như một giá trị đơn:

```sql
SELECT
    o.order_id,
    (
        SELECT p.amount
        FROM payments AS p
        WHERE p.order_id = o.order_id
    ) AS payment_amount
FROM orders AS o;
```

Subquery này chỉ hợp lệ nếu mỗi order có tối đa một payment phù hợp. Nếu trả nhiều hàng, nhiều DBMS báo lỗi scalar subquery returns more than one row.

Kiểm tra độc lập:

```sql
SELECT order_id, COUNT(*) AS payment_count
FROM payments
GROUP BY order_id
HAVING COUNT(*) > 1;
```

Nếu nghiệp vụ cho phép nhiều payment, phải quyết định rõ cần tổng, payment mới nhất hay một loại payment cụ thể. Ví dụ dùng aggregate:

```sql
SELECT
    o.order_id,
    (
        SELECT SUM(p.amount)
        FROM payments AS p
        WHERE p.order_id = o.order_id
    ) AS paid_total
FROM orders AS o;
```

Không dùng MAX(amount) chỉ để tránh lỗi nhiều hàng nếu quy tắc nghiệp vụ thực sự là tổng thanh toán.

### 8.2. EXISTS và NOT EXISTS

EXISTS kiểm tra có ít nhất một hàng phù hợp:

```sql
SELECT o.order_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM payments AS p
    WHERE p.order_id = o.order_id
      AND p.status = 'SETTLED'
);
```

Kiểm tra subquery bằng cách chạy nó cho một order cụ thể:

```sql
SELECT p.payment_id, p.amount, p.status
FROM payments AS p
WHERE p.order_id = 1001
  AND p.status = 'SETTLED';
```

Sau đó đối chiếu order có xuất hiện trong kết quả EXISTS không. EXISTS chỉ cần biết có hàng; duplicate trong subquery không nhân bản hàng ngoài như JOIN thông thường.

### 8.3. NOT IN và NULL

Một lỗi logic phổ biến:

```sql
SELECT customer_id
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM blocked_customers
);
```

Nếu subquery chứa NULL, phép so sánh NOT IN có thể trả UNKNOWN cho các hàng không khớp, khiến kết quả rỗng hoặc thiếu hàng ngoài dự kiến.

Kiểm tra NULL trong tập con:

```sql
SELECT COUNT(*) AS null_ids
FROM blocked_customers
WHERE customer_id IS NULL;
```

Nếu ý nghĩa là “không có hàng blocked nào khớp”, NOT EXISTS thường biểu đạt rõ hơn:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = c.customer_id
);
```

Tuy nhiên, NOT IN và NOT EXISTS không phải lúc nào cũng tương đương nếu NULL được phép và business semantics khác nhau. Hãy xác định cách xử lý NULL trước khi thay.

### 8.4. Derived table

Subquery trong FROM tạo một bảng dẫn xuất:

```sql
SELECT summary.customer_id, summary.order_total
FROM (
    SELECT customer_id, SUM(total_amount) AS order_total
    FROM orders
    GROUP BY customer_id
) AS summary
WHERE summary.order_total > 1000000;
```

Để debug, chạy riêng phần bên trong:

```sql
SELECT customer_id, SUM(total_amount) AS order_total
FROM orders
GROUP BY customer_id;
```

Rồi kiểm tra predicate bên ngoài. Nếu inner query đúng nhưng outer query sai, tập trung vào điều kiện lọc, kiểu dữ liệu, alias và phân trang bên ngoài.

### 8.5. Correlated subquery

Correlated subquery tham chiếu hàng của query ngoài:

```sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers AS c;
```

Để kiểm chứng, chọn một customer cụ thể và chạy inner query với đúng ID. Sau đó so sánh số đếm với kết quả outer query.

Khi chuyển correlated subquery thành JOIN/GROUP BY để tối ưu, phải kiểm tra lại:

- Customer không có order có còn xuất hiện không?
- COUNT(*) hay COUNT(column) được dùng?
- JOIN có nhân bản customer không?
- NULL ở khóa có được xử lý giống nhau?
- Bộ lọc có được đặt đúng trong ON/WHERE không?

## 9. Kiểm chứng GROUP BY, aggregate và window function

### 9.1. Aggregate có thể che khuất duplicate

Nếu query trả một tổng sai, đừng chỉ xem giá trị cuối. Xem hàng đầu vào trước GROUP BY:

```sql
SELECT
    order_id,
    payment_id,
    amount
FROM payments
WHERE order_id = 1001
ORDER BY payment_id;
```

Đếm số hàng và cộng thủ công trên fixture nhỏ để xác nhận aggregate. Nếu JOIN trước GROUP BY đã nhân hàng, SUM sẽ phản ánh tập hàng đã nhân đó.

### 9.2. GROUP BY có thể làm thay đổi cấp độ dữ liệu

Hỏi rõ mỗi hàng kết quả đại diện cho điều gì: một payment, một order, một customer, một ngày hay một customer trong một tháng?

Nếu CTE A có grain là một hàng/order, CTE B có grain một hàng/payment, JOIN hai CTE rồi GROUP BY customer có thể cần aggregate trước theo cùng grain.

### 9.3. Window function không làm giảm số hàng

Ví dụ:

```sql
SELECT
    order_id,
    customer_id,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at DESC, order_id DESC
    ) AS row_num
FROM orders;
```

Window function gắn thêm giá trị tính trên cửa sổ, nhưng vẫn giữ các hàng đầu vào. Nếu chỉ muốn hàng mới nhất, cần lọc kết quả window ở query ngoài:

```sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS row_num
    FROM orders
)
SELECT *
FROM ranked_orders
WHERE row_num = 1;
```

Khi debug, xem tất cả hàng và row_num trước khi lọc. Thêm khóa phụ vào ORDER BY giúp kết quả xác định khi thời gian trùng nhau.

### 9.4. HAVING khác WHERE

- WHERE lọc hàng trước GROUP BY.
- HAVING lọc nhóm sau aggregate.

Nếu chuyển điều kiện giữa hai nơi, kết quả có thể thay đổi. Thu nhỏ từng predicate và kiểm tra số hàng đầu vào, số nhóm đầu ra.
## 10. Kiểm chứng NULL, kiểu dữ liệu và phép chuyển đổi

Một CTE có thể tạo ra kết quả khác dự kiến dù syntax hoàn toàn đúng.

### 10.1. NULL không bằng NULL

```sql
WHERE customer_id = NULL
```

Không tìm thấy giá trị NULL theo cách này. Dùng:

```sql
WHERE customer_id IS NULL
```

Tương tự, NOT NULL và IS NOT NULL phải được kiểm tra ở từng bước.

### 10.2. COALESCE thay đổi ý nghĩa aggregate

```sql
SELECT
    SUM(amount) AS raw_total,
    SUM(COALESCE(amount, 0)) AS total_with_zero
FROM payments;
```

SUM bỏ qua NULL; COALESCE thay NULL bằng 0 trước khi tổng hợp. Hai biểu thức có thể giống kết quả số học trong một số trường hợp nhưng khác ý nghĩa khi toàn bộ giá trị là NULL hoặc khi cần phân biệt “không có dữ liệu” với “tổng bằng 0”.

### 10.3. Implicit cast và precision

Kiểm tra:

- INTEGER so với BIGINT.
- DECIMAL/NUMERIC precision và scale.
- FLOAT so với số thập phân chính xác.
- DATE so với TIMESTAMP.
- Timestamp có timezone so với không timezone.
- VARCHAR/NVARCHAR và collation.
- Chuỗi số có ký tự không hợp lệ.

Khi nghi ngờ cast, viết truy vấn nhỏ chỉ gồm cột và phép chuyển đổi:

```sql
SELECT
    raw_amount,
    CAST(raw_amount AS DECIMAL(12,2)) AS parsed_amount
FROM staging_payments;
```

Một hàng dữ liệu lỗi có thể khiến cả query thất bại. Hãy tìm hàng đó trong fixture hoặc dùng TRY_CAST/SAFE_CAST nếu DBMS hỗ trợ và mục tiêu kiểm tra phù hợp.

### 10.4. Timezone và khoảng ngày

Điều kiện:

```sql
WHERE created_at BETWEEN '2026-03-01' AND '2026-03-31'
```

có thể bỏ sót phần lớn ngày 31 nếu cột chứa timestamp và literal cuối ngày được hiểu là đầu ngày 31. Cách dùng khoảng nửa mở thường rõ hơn:

```sql
WHERE created_at >= ?
  AND created_at < ?
```

Bind thời điểm đầu tháng và đầu tháng kế tiếp với kiểu/timezone đúng. Khi thu nhỏ, giữ nguyên kiểu parameter và timezone của ứng dụng.

## 11. So sánh kết quả giữa hai bước

Khi nghi ngờ CTE trung gian đã thay đổi tập hàng, hãy so sánh hai kết quả bằng khóa hoặc phép tập hợp.

### 11.1. EXCEPT để tìm hàng chỉ có ở một phía

Trên DBMS hỗ trợ cú pháp tương ứng:

```sql
WITH
expected AS (
    SELECT order_id, customer_id, total_amount
    FROM expected_orders
),
actual AS (
    SELECT order_id, customer_id, total_amount
    FROM actual_orders
)
SELECT * FROM expected
EXCEPT
SELECT * FROM actual;
```

Sau đó đảo chiều để tìm hàng chỉ có ở actual. SQL Server, PostgreSQL, Oracle và SQLite có hỗ trợ toán tử tập hợp theo cú pháp/phiên bản tương ứng; MySQL có thể cần anti-join/NOT EXISTS tùy version.

### 11.2. EXCEPT có thể bỏ qua duplicate

EXCEPT thông thường là set operation và có thể loại duplicate. Nếu lỗi là số lần xuất hiện của hàng, so sánh bằng GROUP BY trên toàn bộ cột:

```sql
SELECT
    order_id,
    customer_id,
    total_amount,
    COUNT(*) AS occurrences
FROM actual_result
GROUP BY order_id, customer_id, total_amount
HAVING COUNT(*) > 1;
```

Hoặc tạo hai tập đã GROUP BY và so sánh số lần xuất hiện. Đừng kết luận hai kết quả tương đương chỉ vì EXCEPT không trả hàng.

### 11.3. So sánh theo khóa nghiệp vụ

Nếu một hàng có khóa duy nhất, so sánh expected và actual theo khóa:

- Hàng bị thiếu.
- Hàng thừa.
- Hàng có cùng khóa nhưng khác giá trị.
- Hàng duplicate.

Dùng JOIN theo khóa và điều kiện so sánh null-safe phù hợp dialect. Không dùng checksum/hash làm bằng chứng duy nhất nếu cần xác định chính xác hàng khác.

## 12. Tạo fixture nhỏ nhất vẫn giữ lỗi

Một reproducer tốt thường có ít bảng, ít hàng và ít cột nhất nhưng vẫn tái hiện chính xác lỗi.

Ví dụ lỗi fan-out chỉ cần:

```sql
CREATE TABLE test_orders (
    order_id INTEGER PRIMARY KEY
);

CREATE TABLE test_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL
);

CREATE TABLE test_payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    amount DECIMAL(10,2) NOT NULL
);

INSERT INTO test_orders VALUES (1);
INSERT INTO test_items VALUES (11, 1, 2);
INSERT INTO test_items VALUES (12, 1, 3);
INSERT INTO test_payments VALUES (21, 1, 100.00);
INSERT INTO test_payments VALUES (22, 1, 50.00);
```

Query lỗi:

```sql
SELECT
    o.order_id,
    SUM(i.quantity) AS total_quantity,
    SUM(p.amount) AS total_paid
FROM test_orders AS o
JOIN test_items AS i
  ON i.order_id = o.order_id
JOIN test_payments AS p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

Kết quả có thể là quantity 10 và payment 300, trong khi đúng phải là quantity 5 và payment 150. Fixture nhỏ giúp nhìn rõ nguyên nhân mà không cần dữ liệu production.

### 12.1. Giữ dữ liệu biên

Fixture cần có các hàng làm lộ vấn đề:

- Không có hàng con.
- Có nhiều hàng con.
- Giá trị NULL.
- Khóa trùng nếu schema cho phép.
- Ngày ở đúng ranh giới.
- Giá trị 0 hoặc âm nếu có thể tồn tại trong staging.
- Chuỗi có dấu/ký tự đặc biệt.
- Hàng thuộc tenant khác để kiểm tra predicate.
- Hai giá trị bằng nhau để kiểm tra tie-breaker.

Không cần đưa mọi trường hợp vào một fixture. Tạo fixture nhỏ riêng cho từng lỗi sẽ dễ đọc hơn.

### 12.2. Dùng transaction để dọn dữ liệu test

Nếu DBMS hỗ trợ rollback DML trong transaction:

```sql
BEGIN;

-- Tạo dữ liệu test và chạy reproducer.

ROLLBACK;
```

DDL có thể implicit commit hoặc không rollback giống nhau giữa các DBMS. Hãy kiểm tra behavior trước khi dùng transaction như cơ chế cleanup. Với SQLite/SQL Server/PostgreSQL/Oracle/MySQL, khả năng rollback DDL khác nhau theo engine và câu lệnh.

## 13. Thu nhỏ bằng cách bỏ predicate có hệ thống

Nếu query sai kết quả, có thể thử từng điều kiện:

```sql
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
  AND created_at < ?
  AND total_amount > 0
```

Ghi bảng theo dõi:

| Lần thử | Thay đổi | Lỗi còn tái hiện? | Nhận xét |
|---:|---|---|---|
| 0 | Query gốc | Có | Baseline |
| 1 | Bỏ điều kiện total_amount | Có/Không | Ghi kết quả |
| 2 | Bỏ status | Có/Không | Ghi kết quả |
| 3 | Giới hạn một tenant | Có/Không | Giữ đúng tenant gây lỗi |
| 4 | Giới hạn khoảng ngày | Có/Không | Giữ hàng biên |

Nếu nhiều predicate độc lập, có thể dùng cách chia đôi để giảm số lần thử. Nhưng với predicate phụ thuộc nhau, hãy bỏ từng điều kiện và chạy lại. Không loại bỏ điều kiện tenant/authorization trong môi trường có dữ liệu thật chỉ để query dễ chạy.

### 13.1. Không đổi điều kiện ON thành WHERE khi đang thu nhỏ

Điều kiện JOIN là một phần của ngữ nghĩa. Di chuyển predicate giữa ON và WHERE có thể đổi LEFT JOIN thành hành vi giống INNER JOIN. Hãy ghi rõ thay đổi đó là một phép thử riêng.

### 13.2. Không bỏ ORDER BY nếu lỗi liên quan pagination

Nếu query có LIMIT/OFFSET/FETCH, thứ tự quyết định hàng nào nằm trong trang. Bỏ ORDER BY có thể khiến lỗi biến mất vì tập hàng được chọn thay đổi.

Dùng ORDER BY có khóa tie-breaker duy nhất để kết quả trang ổn định.
## 14. Thu nhỏ subquery mà không làm mất correlation

Một lỗi thường gặp là copy inner query ra SQL editor nhưng quên tham số từ outer query.

Ví dụ:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = ?
);
```

Khi kiểm tra riêng, phải thay correlation c.customer_id bằng một ID cụ thể và bind cùng status:

```sql
SELECT 1
FROM orders AS o
WHERE o.customer_id = 1001
  AND o.status = 'CONFIRMED';
```

Nếu inner query đúng cho customer 1001 nhưng outer query thiếu customer đó, kiểm tra alias, correlation predicate, kiểu dữ liệu và các điều kiện khác ở outer query.

### 14.1. Kiểm tra subquery có trả nhiều hàng không

```sql
SELECT COUNT(*)
FROM (
    SELECT ...
) AS candidate_rows;
```

Với scalar subquery, count phải không vượt quá 1 cho mỗi correlation key. Nếu cần chọn một hàng, dùng quy tắc rõ ràng như MAX/MIN hoặc ORDER BY + FETCH FIRST/LIMIT; không tùy tiện lấy hàng đầu tiên khi chưa có thứ tự xác định.

### 14.2. Kiểm tra correlation key

Một lỗi alias có thể khiến subquery vô tình trở thành uncorrelated hoặc so sánh sai cột:

- o.customer_id = c.customer_id có đúng alias?
- Có dùng nhầm tenant_id?
- Có thiếu điều kiện tenant trong bảng con?
- Cột hai phía có cùng kiểu?
- NULL có thể xuất hiện ở khóa?

Kiểm tra từng predicate trong inner query độc lập.

## 15. CTE đệ quy: kiểm tra anchor và recursive member riêng

Với recursive CTE, có hai phần:

- Anchor member: tạo tập hàng ban đầu.
- Recursive member: sinh hàng tiếp theo từ kết quả trước.

Ví dụ dạng phổ biến:

```sql
WITH RECURSIVE org_tree AS (
    SELECT employee_id, manager_id, 0 AS depth
    FROM employees
    WHERE employee_id = ?

    UNION ALL

    SELECT e.employee_id, e.manager_id, t.depth + 1
    FROM employees AS e
    JOIN org_tree AS t
      ON e.manager_id = t.employee_id
)
SELECT *
FROM org_tree;
```

Cú pháp WITH RECURSIVE khác SQL Server (dùng CTE đệ quy không có từ khóa này), và có thể cần giới hạn recursion tùy DBMS.

### 15.1. Kiểm chứng anchor

Chạy riêng SELECT anchor. Xác nhận:

- Có đúng node gốc?
- Có trùng node?
- Depth bắt đầu đúng?
- Predicate có dùng đúng tenant/organization không?

### 15.2. Kiểm chứng recursive member

Chạy một bước nối từ anchor, sau đó bước tiếp theo nếu cần. Kiểm tra:

- Join key có đúng hướng?
- Có chu trình trong dữ liệu không?
- Có điều kiện dừng?
- Có duplicate do nhiều đường đi?
- Depth/level có tăng đúng?

### 15.3. Giới hạn độ sâu trong lúc debug

Dùng giới hạn recursion theo cơ chế của DBMS hoặc thêm điều kiện depth trong recursive member. Không chỉ giới hạn SELECT cuối nếu recursive CTE vẫn sinh quá nhiều hàng trước khi lọc.

Khi query đệ quy chạy mãi, kiểm tra chu trình và điều kiện kết thúc trước khi tăng giới hạn recursion.

## 16. Phân biệt lỗi logic và lỗi query plan

Sau khi các CTE/subquery cho ra tập hàng đúng, query vẫn có thể chậm. Khi đó cần kiểm tra plan.

### 16.1. EXPLAIN

Các DBMS có công cụ tương ứng:

- PostgreSQL: EXPLAIN, EXPLAIN (ANALYZE, BUFFERS).
- MySQL: EXPLAIN, EXPLAIN ANALYZE theo version.
- MariaDB: EXPLAIN, ANALYZE theo version.
- SQL Server: actual execution plan, STATISTICS IO/TIME.
- Oracle: execution plan và runtime statistics.
- SQLite: EXPLAIN QUERY PLAN.

Actual plan có thể thực thi query và tạo tải; chỉ dùng trên môi trường phù hợp, đặc biệt với DML.

### 16.2. So sánh estimated rows và actual rows

Nếu optimizer ước lượng 10 hàng nhưng thực tế có 1 triệu, join order hoặc access path có thể kém. Kiểm tra statistics, skew, predicate, parameter sensitivity và index.

### 16.3. CTE không phải lúc nào cũng materialize

Một số DBMS có thể inline CTE hoặc materialize tùy query và version. Không thêm CTE mới với kỳ vọng chắc chắn query sẽ chạy theo thứ tự viết. Đọc plan thay vì suy từ hình thức SQL.

### 16.4. Không dùng EXPLAIN để chứng minh kết quả đúng

Plan trả lời cách DBMS dự định hoặc đã thực thi query. Nó không xác nhận business logic đúng. Dùng fixture và so sánh kết quả để xác nhận correctness; dùng plan để xác nhận performance.

## 17. Các khác biệt DBMS khi thu nhỏ query

| DBMS | Điểm cần chú ý |
|---|---|
| PostgreSQL | CTE có thể được inline hoặc materialize tùy cấu trúc/version; EXPLAIN ANALYZE chạy thật query |
| MySQL | CTE hỗ trợ trong các phiên bản hiện đại; derived table/CTE có thể merge hoặc materialize |
| MariaDB | Hành vi CTE/derived table và EXPLAIN phụ thuộc version; kiểm tra plan thực tế |
| SQL Server | CTE không phải materialized table; recursive CTE và TOP/OFFSET có quy tắc riêng |
| Oracle | Subquery factoring có thể được optimizer biến đổi; execution plan và hints cần hiểu kỹ |
| SQLite | CTE có thể có materialization hints ở phiên bản hỗ trợ; query plan được xem qua EXPLAIN QUERY PLAN |

Không viết một query debug trên dialect khác rồi kết luận lỗi trong production. Dùng cùng DBMS/version/driver khi có thể.

## 18. Thu nhỏ query từ ứng dụng Java/JDBC

Nếu lỗi chỉ xuất hiện khi gọi từ Java:

### 18.1. Log SQL template và bind metadata

Ghi SQL template, vị trí placeholder, JDBC type và giá trị test đã che dữ liệu nhạy cảm. Không nối giá trị trực tiếp vào SQL log rồi chạy lại mà bỏ qua kiểu bind.

### 18.2. Kiểm tra cách bind

```java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, status);
    ps.setTimestamp(3, Timestamp.from(start));
    ps.setTimestamp(4, Timestamp.from(end));

    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
```

Nếu code vô tình bind nhầm thứ tự, ví dụ status vào placeholder tenant, query có thể hợp lệ nhưng trả kết quả sai. Tạo test kiểm tra thứ tự bind và kiểu dữ liệu.

### 18.3. So sánh SQL console và ứng dụng

Nếu query trong SQL console đúng nhưng Java sai, so sánh:

- Connection/session timezone.
- Current schema/search_path.
- Database user/role.
- Transaction isolation.
- Parameter type và value.
- Collation/NLS settings.
- Session variables.
- Autocommit và transaction boundary.
- DBMS/driver version.
- Prepared statement behavior.

Không chỉ copy SQL text mà bỏ qua session context.

### 18.4. Dùng test repository với fixture

Tạo integration test chạy query qua đúng repository/driver, nạp fixture nhỏ, assert số hàng và giá trị. Test này bắt được lỗi bind, mapping và dialect mà việc chạy SQL thủ công có thể bỏ sót.

## 19. Khi query có dynamic SQL

Một số query được dựng từ danh sách filter, sort hoặc tên cột. Khi thu nhỏ, phải ghi lại **SQL cuối cùng** và nguồn của từng fragment.

- Value phải bind bằng parameter.
- Identifier/keyword phải chọn từ allowlist.
- Các fragment optional phải được ghi nhận bật/tắt.
- Không dùng dữ liệu client làm raw SQL.
- Test các tổ hợp filter có thể sinh query khác nhau.

Ví dụ, sort field được chọn từ allowlist:

```java
String sortColumn = switch (requestedSort) {
    case "created" -> "created_at";
    case "amount" -> "total_amount";
    case "id" -> "order_id";
    default -> throw new IllegalArgumentException("Unsupported sort");
};

String sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE tenant_id = ?
    ORDER BY %s
    """.formatted(sortColumn);
```

Chỉ fragment do code kiểm soát được đưa vào cấu trúc SQL; tenant vẫn bind. Khi debug, lưu lại sortColumn đã chọn để tái hiện đúng query.
## 20. Kiểm chứng kết quả bằng fixture và assertion

Đừng chỉ xem vài hàng đầu tiên. Viết các assertion có thể chạy lặp lại.

Ví dụ các điều kiện cần đúng:

- Mỗi order xuất hiện tối đa một lần trong CTE order-level.
- Mỗi customer chỉ có một hàng trong customer summary.
- Tổng paid amount không vượt quá tổng payment hợp lệ nếu domain yêu cầu.
- Không có order thuộc tenant khác.
- Không có hàng có quantity không hợp lệ.
- Ngày bắt đầu được tính, ngày kết thúc loại trừ theo quy ước.
- Số hàng trước và sau JOIN phù hợp cardinality.

Có thể viết assertion SQL:

```sql
WITH candidate AS (
    SELECT order_id, customer_id
    FROM ...
)
SELECT order_id, COUNT(*)
FROM candidate
GROUP BY order_id
HAVING COUNT(*) > 1;
```

Nếu kết quả rỗng, invariant uniqueness được giữ cho fixture hiện tại. Cần test nhiều fixture để bao phủ các trường hợp biên.

### 20.1. Kiểm tra tổng đối chiếu

Nếu một CTE tổng hợp tiền từ payment, so sánh với truy vấn độc lập từ bảng payment trên cùng filter. Hai bên phải cùng định nghĩa “payment hợp lệ” và cùng snapshot dữ liệu.

### 20.2. Kiểm tra khóa bị thiếu

Dùng anti-join hoặc NOT EXISTS để tìm hàng nguồn không có trong kết quả:

```sql
SELECT o.order_id
FROM confirmed_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM order_balances AS b
    WHERE b.order_id = o.order_id
);
```

Nếu không mong đợi mất order, kết quả phải rỗng.

## 21. Cách ghi lại quá trình thu nhỏ

Một log ngắn giúp người khác tái hiện mà không phải đọc lịch sử thao tác.

| Trường | Nội dung |
|---|---|
| Query ID | Tên query/repository method |
| DBMS/version | Hệ quản trị và version |
| Driver/version | JDBC driver |
| Input | Param types và fixture IDs |
| Baseline | Kết quả hoặc error code ban đầu |
| Reduction | Phần đã bỏ/thay đổi |
| Observation | Count, duplicate, NULL, error |
| Root cause candidate | CTE/JOIN/subquery/predicate |
| Minimal reproducer | SQL + DDL/fixture tối thiểu |
| Regression test | Tên test và kết quả |

Không ghi raw dữ liệu khách hàng hoặc secrets trong log debug.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm tốt hơn |
|---|---|---|
| Xóa nhiều CTE cùng lúc | Mất điều kiện tái hiện | Bỏ từng bước và chạy lại |
| Chỉ xem SELECT cuối | Không biết CTE nào đã sai | SELECT trực tiếp từng CTE |
| Thêm DISTINCT để che duplicate | Che fan-out và sai aggregate | Kiểm tra cardinality của JOIN |
| Chạy subquery riêng nhưng quên correlation | Kết quả debug khác query gốc | Thay correlation key bằng ID cụ thể |
| Bỏ ORDER BY khi có pagination | Tập hàng trên trang thay đổi | Giữ thứ tự và tie-breaker |
| Thay tham số bằng literal khác kiểu | Không tái hiện lỗi bind | Giữ JDBC type/value |
| Chạy từng CTE ở snapshot khác | Dữ liệu giữa bước không nhất quán | Fixture/snapshot cố định |
| Nghĩ CTE luôn materialize | Hiểu sai execution plan | Xem plan của DBMS/version |
| Chỉ dùng EXPLAIN để kiểm tra correctness | Plan không chứng minh kết quả nghiệp vụ | Fixture + assertions |
| So sánh bằng EXCEPT rồi bỏ qua duplicate | Không phát hiện số lần xuất hiện khác | So sánh multiplicity |
| Đổi LEFT JOIN thành INNER JOIN khi thu nhỏ | Làm mất hàng không có quan hệ | Giữ đúng semantics |
| Chuyển predicate ON sang WHERE | Đổi kết quả outer join | Thử riêng và ghi nhận |
| Thu nhỏ fixture đến mức mất fan-out | Lỗi biến mất giả tạo | Giữ cardinality gây lỗi |
| Bỏ tenant predicate trong môi trường thật | Có nguy cơ lộ dữ liệu | Dùng fixture cô lập |
| Chỉ kiểm tra 10 hàng đầu | Bỏ sót lỗi ở phần còn lại | Count, key checks và full fixture |
| Sửa query trước khi lưu reproducer | Không thể chứng minh nguyên nhân | Lưu baseline và fixture trước |

## 23. Quy trình thực hành đầy đủ

Khi một query nhiều CTE gặp lỗi:

1. Lưu SQL gốc, tham số, kiểu bind, DBMS/version và lỗi.
2. Tạo fixture hoặc snapshot đủ để tái hiện.
3. Ghi một assertion cụ thể: sai count, duplicate, thiếu hàng, sai giá trị hay timeout.
4. Vẽ dependency graph CTE.
5. Kiểm tra CTE nguồn bằng SELECT, COUNT, NULL và duplicate checks.
6. Đi theo dependency order, kiểm tra từng CTE.
7. Tách từng subquery, giữ correlation key và tham số.
8. Kiểm tra JOIN cardinality, ON/WHERE, NULL và grain dữ liệu.
9. Kiểm tra GROUP BY/window/pagination sau khi các tập trung gian đúng.
10. Loại từng predicate/CTE/column không liên quan nhưng chạy lại assertion sau mỗi thay đổi.
11. Lưu minimal reproducer nhỏ nhất.
12. Sửa nguyên nhân, chạy reproducer và query gốc.
13. Viết regression test với dữ liệu biên.
14. Nếu lỗi hiệu năng, đo actual plan trên workload phù hợp.
15. Ghi lại root cause và cách xác nhận.

### 23.1. Sơ đồ quyết định

```text
Query lỗi hoặc kết quả sai
          |
          v
Có thể tái hiện với input cố định?
      |               |
     Không            Có
      |               |
Thu thập bind,     Phân loại lỗi
schema, snapshot       |
                      v
             Vẽ dependency CTE
                      |
                      v
             Kiểm chứng CTE nguồn
                      |
                      v
             Kiểm chứng từng CTE
                      |
                      v
             Tách từng subquery
                      |
                      v
             Kiểm tra JOIN/cardinality
                      |
                      v
             Tạo minimal reproducer
                      |
                      v
             Sửa + regression test
                      |
                      v
             Chạy query gốc / xem plan
```

## 24. Bài tập thực hành có đáp án

### Bài 1. Query có sáu CTE và trả sai tổng

**Hỏi:** bắt đầu debug ở đâu?

**Đáp án:** lưu baseline, vẽ dependency graph, chạy SELECT trực tiếp từng CTE theo thứ tự phụ thuộc. So sánh count, key và aggregate để tìm CTE đầu tiên sai.

### Bài 2. CTE nguồn trả 100 hàng, CTE tiếp theo trả 20

**Hỏi:** đây có nhất thiết là lỗi không?

**Đáp án:** không. CTE tiếp theo có thể lọc 80 hàng theo nghiệp vụ. Kiểm tra predicate và các hàng bị loại, không chỉ so sánh count.

### Bài 3. JOIN làm tổng payment tăng gấp đôi

**Tình huống:** một order có hai item và hai payment.

**Đáp án:** JOIN chi tiết tạo bốn hàng. Tổng hợp item và payment riêng theo order trước khi JOIN; kiểm tra cardinality.

### Bài 4. Scalar subquery báo nhiều hàng

**Hỏi:** kiểm tra gì?

**Đáp án:** chạy inner query với một correlation key, đếm hàng. Quyết định aggregate, filter hoặc chọn hàng theo ORDER BY có tie-breaker; không tùy tiện thêm LIMIT.

### Bài 5. NOT IN trả về rỗng

**Tình huống:** subquery chứa một customer_id NULL.

**Đáp án:** NULL làm phép NOT IN có thể UNKNOWN. Kiểm tra NULL và cân nhắc NOT EXISTS nếu đúng semantics.

### Bài 6. EXISTS và JOIN trả số hàng khác nhau

**Đáp án:** EXISTS chỉ kiểm tra sự tồn tại và không nhân bản hàng ngoài vì duplicate trong subquery; JOIN có thể tạo nhiều hàng cho một hàng ngoài.

### Bài 7. LEFT JOIN mất hàng không có payment

**Tình huống:** điều kiện p.status đặt trong WHERE.

**Đáp án:** hàng không có payment có p.status NULL nên bị lọc. Nếu muốn giữ order, predicate phù hợp có thể đặt trong ON.

### Bài 8. CTE có duplicate order_id

**Hỏi:** dùng DISTINCT ngay có tốt không?

**Đáp án:** chưa. Kiểm tra JOIN và nguồn duplicate trước; DISTINCT có thể che sai cardinality hoặc làm sai aggregate.

### Bài 9. Query chỉ sai khi tenant có dữ liệu lớn

**Đáp án:** giữ cardinality/skew của tenant đó trong fixture. Nếu lỗi performance, cần dữ liệu gần workload thật và actual plan; fixture vài hàng không đủ.

### Bài 10. Query console đúng nhưng JDBC sai

**Đáp án:** so sánh bind order/type/value, timezone, schema/search_path, role, isolation, autocommit, session setting và driver version.

### Bài 11. Subquery debug độc lập trả đúng, outer query vẫn sai

**Đáp án:** kiểm tra correlation predicate, alias, điều kiện outer query, kiểu khóa và tenant filter.

### Bài 12. EXCEPT không tìm thấy khác biệt nhưng count khác

**Đáp án:** EXCEPT thông thường loại duplicate. So sánh multiplicity bằng GROUP BY trên toàn bộ cột hoặc khóa và COUNT(*).

### Bài 13. Window function trả nhiều hàng hơn mong đợi

**Đáp án:** window function giữ nguyên hàng đầu vào. Lọc row_number ở query ngoài nếu chỉ muốn top row mỗi nhóm.

### Bài 14. Kết quả cuối thiếu ngày cuối tháng

**Đáp án:** kiểm tra kiểu DATE/TIMESTAMP, timezone và ranh giới. Dùng khoảng nửa mở từ đầu tháng tới đầu tháng kế tiếp với bind type phù hợp.

### Bài 15. CTE đúng khi chạy riêng nhưng query đầy đủ sai

**Đáp án:** kiểm tra JOIN/aggregate/predicate ở CTE sau hoặc SELECT cuối; cũng xác nhận snapshot dữ liệu giữa hai lần chạy giống nhau.

### Bài 16. Recursive CTE chạy mãi

**Đáp án:** kiểm tra chu trình, điều kiện dừng, anchor và recursive member; thêm giới hạn độ sâu phù hợp DBMS để debug.

### Bài 17. Bỏ ORDER BY làm lỗi biến mất

**Đáp án:** nếu có pagination, thứ tự quyết định tập hàng được chọn. Giữ ORDER BY ổn định với khóa tie-breaker khi thu nhỏ.

### Bài 18. Query lỗi cast

**Đáp án:** giữ biểu thức CAST và thu nhỏ dữ liệu đầu vào để tìm hàng có giá trị không chuyển đổi được. Kiểm tra type/precision và TRY_CAST/SAFE_CAST nếu DBMS hỗ trợ.

### Bài 19. CTE có vẻ chạy nhiều lần

**Hỏi:** CTE có phải bảng tạm vật lý không?

**Đáp án:** không mặc định. Optimizer có thể inline hoặc materialize tùy DBMS/version. Xem execution plan.

### Bài 20. Cần biết CTE nào làm query chậm

**Đáp án:** xem actual plan và operator/row estimates, IO, spills, join strategy. CTE là cách tổ chức logic; plan mới cho biết cách thực thi.

### Bài 21. Fixture thu nhỏ không còn tái hiện lỗi

**Đáp án:** đã loại mất điều kiện cần. Xem dữ liệu gây lỗi như duplicate, NULL, fan-out, giá trị biên hoặc cardinality; thêm lại tối thiểu.

### Bài 22. Aggregate khác tổng nguồn

**Đáp án:** kiểm tra hàng đầu vào aggregate, fan-out JOIN, predicate, NULL, grain và snapshot; đối chiếu bằng query độc lập cùng filter.

### Bài 23. Có nên bỏ tenant predicate để query dễ debug?

**Đáp án:** không trên dữ liệu thật. Tạo fixture cô lập và giữ tenant predicate; không biến việc debug thành truy cập chéo tenant.

### Bài 24. SQL Server báo lỗi CTE syntax sau khi thu nhỏ

**Đáp án:** kiểm tra dấu chấm phẩy trước WITH trong batch SQL Server và alias CTE; cú pháp giữa dialect khác nhau.

### Bài 25. Query có 4 subquery lồng nhau

**Đáp án:** tách từ trong ra ngoài. Chạy inner query với correlation key cố định, kiểm tra cardinality/NULL, rồi thêm dần từng lớp.

### Bài 26. Sau sửa query, làm gì tiếp?

**Đáp án:** chạy minimal reproducer, query gốc, integration test với fixture biên và kiểm tra actual plan nếu vấn đề liên quan hiệu năng. Lưu regression test để ngăn lỗi quay lại.

## 25. Tài liệu chính thức để tra cứu

Cú pháp và hành vi optimizer phụ thuộc DBMS/phiên bản:

- **PostgreSQL — WITH Queries (CTE):** https://www.postgresql.org/docs/current/queries-with.html
- **PostgreSQL — EXPLAIN:** https://www.postgresql.org/docs/current/sql-explain.html
- **PostgreSQL — Subquery Expressions:** https://www.postgresql.org/docs/current/functions-subquery.html
- **MySQL — WITH (Common Table Expressions):** https://dev.mysql.com/doc/refman/8.4/en/with.html
- **MySQL — EXPLAIN:** https://dev.mysql.com/doc/refman/8.4/en/explain.html
- **MariaDB — WITH / Common Table Expressions:** https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/selecting-data/common-table-expressions
- **SQL Server — WITH common_table_expression:** https://learn.microsoft.com/en-us/sql/t-sql/queries/with-common-table-expression-transact-sql
- **SQL Server — Execution Plans:** https://learn.microsoft.com/en-us/sql/relational-databases/performance/execution-plans
- **Oracle — SELECT:** https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html
- **Oracle — EXPLAIN PLAN:** https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXPLAIN-PLAN.html
- **SQLite — WITH Clause:** https://www.sqlite.org/lang_with.html
- **SQLite — EXPLAIN QUERY PLAN:** https://www.sqlite.org/eqp.html
- **Java JDBC — PreparedStatement:** https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html

## Kết luận

Thu nhỏ truy vấn là một kỹ thuật điều tra có kiểm soát:

- Lưu query gốc, tham số, schema, DBMS và điều kiện tái hiện trước khi sửa.
- Vẽ dependency graph rồi kiểm chứng từng CTE theo thứ tự.
- Tách subquery nhưng giữ correlation key, kiểu tham số và semantics.
- Kiểm tra cardinality, duplicate, NULL, JOIN, aggregate, window và pagination.
- Dùng fixture nhỏ nhất vẫn tái hiện lỗi; so sánh cả giá trị lẫn số lần xuất hiện.
- Dùng execution plan để điều tra hiệu năng, không dùng plan thay cho kiểm chứng kết quả.
- Sau khi sửa, chạy lại reproducer, query đầy đủ và regression test.

**Nguyên tắc quan trọng nhất: mỗi lần thu nhỏ chỉ thay đổi một phần có chủ đích, rồi chạy lại đúng phép thử đang thất bại.** Cách làm này giúp xác định CTE hoặc subquery đầu tiên làm sai kết quả, thay vì sửa theo phỏng đoán ở câu SQL cuối cùng.






