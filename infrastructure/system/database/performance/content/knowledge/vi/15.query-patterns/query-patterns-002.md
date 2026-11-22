# CTE, bảng dẫn xuất và việc vật chất hóa theo hệ quản trị

Khi một truy vấn cần nhiều bước xử lý, lập trình viên thường chia nó thành các phần có tên bằng `WITH` hoặc đặt một truy vấn con trong mệnh đề `FROM`. Cách viết này giúp câu SQL dễ đọc, dễ kiểm tra và thể hiện rõ từng bước biến đổi dữ liệu. Tuy nhiên, một phần truy vấn được đặt tên không nhất thiết trở thành bảng tạm được lưu riêng trong bộ nhớ hay trên đĩa.

**CTE** (*Common Table Expression*) và **bảng dẫn xuất** (*derived table*) trước hết là cách tổ chức biểu thức truy vấn. Bộ tối ưu có thể mở rộng chúng vào truy vấn bên ngoài (*inline/merge/fold*), đẩy điều kiện lọc vào bên trong, hoặc vật chất hóa kết quả trung gian (*materialization*) tùy hệ quản trị, phiên bản, cấu trúc truy vấn và chi phí ước lượng. Lựa chọn đó ảnh hưởng đến số lần tính toán, khả năng dùng chỉ mục, lượng dữ liệu trung gian, bộ nhớ và I/O.

Trong module **DATABASE_PERFORMANCE**, cần phân biệt cấu trúc SQL với kế hoạch vật lý. Bài học này trình bày cách dùng CTE và bảng dẫn xuất, ý nghĩa của inline và materialization, các đánh đổi hiệu năng, cách kiểm chứng bằng execution plan và khác biệt phổ biến giữa PostgreSQL, SQL Server, MySQL và Oracle Database.

## 1. CTE và bảng dẫn xuất là gì?

### CTE: đặt tên cho một biểu thức truy vấn

CTE được khai báo bằng `WITH` ở đầu một câu lệnh. Truy vấn chính có thể tham chiếu đến tên CTE như một nguồn dữ liệu:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE payment_status = 'PAID'
)
SELECT customer_id, SUM(total_amount) AS paid_total
FROM paid_orders
GROUP BY customer_id;
```

`paid_orders` là tên của một biểu thức truy vấn trong phạm vi câu lệnh. CTE giúp tách bước lọc đơn hàng đã thanh toán khỏi bước tổng hợp theo khách hàng. Việc khai báo CTE không tự khẳng định hệ quản trị phải tạo một bảng vật lý chứa toàn bộ kết quả `paid_orders`.

Một câu lệnh có thể khai báo nhiều CTE, trong đó CTE sau tham chiếu CTE trước:

```sql
WITH recent_orders AS (
    SELECT order_id, customer_id, created_at, total_amount
    FROM orders
    WHERE created_at >= ?
), customer_totals AS (
    SELECT customer_id, COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM recent_orders
    GROUP BY customer_id
)
SELECT c.customer_id, c.full_name, t.order_count, t.total_amount
FROM customer AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id;
```

CTE thứ hai dùng kết quả logic của CTE thứ nhất. Bộ tối ưu có thể hợp nhất các phần này thành một kế hoạch lớn, hoặc tạo một bước trung gian tùy quy tắc của hệ quản trị.

### Bảng dẫn xuất: truy vấn con trong FROM

Bảng dẫn xuất là một truy vấn con có bí danh trong mệnh đề `FROM`:

```sql
SELECT x.customer_id, x.total_amount
FROM (
    SELECT customer_id, SUM(total_amount) AS total_amount
    FROM orders
    WHERE payment_status = 'PAID'
    GROUP BY customer_id
) AS x
WHERE x.total_amount >= ?;
```

Truy vấn con `x` tạo ra một nguồn dữ liệu logic cho truy vấn bên ngoài. Cũng như CTE, bảng dẫn xuất không mặc nhiên phải được ghi thành bảng tạm. Hệ quản trị có thể gộp nó vào truy vấn bên ngoài hoặc vật chất hóa nếu kế hoạch được chọn cần lưu kết quả trung gian.

### So sánh về cách tổ chức

| Đặc điểm | CTE | Bảng dẫn xuất |
|---|---|---|
| Cách viết | Khai báo tên trong `WITH` | Truy vấn con trong `FROM` |
| Phạm vi | Thường trong một câu lệnh | Tại vị trí khai báo trong câu lệnh |
| Khả năng đọc | Hữu ích khi có nhiều bước hoặc cần tham chiếu tên nhiều lần | Gọn cho một bước cục bộ |
| Đệ quy | Nhiều hệ quản trị hỗ trợ recursive CTE | Không có dạng đệ quy tương đương trực tiếp trong cùng cấu trúc |
| Vật chất hóa | Phụ thuộc hệ quản trị, số lần tham chiếu và cấu trúc truy vấn | Phụ thuộc hệ quản trị và khả năng merge/flatten |

Không nên chọn CTE chỉ vì nghĩ rằng nó luôn nhanh hơn bảng dẫn xuất, hoặc chọn bảng dẫn xuất vì nghĩ rằng nó luôn được nhúng vào truy vấn. Hai cách viết có thể được tối ưu thành kế hoạch tương tự khi ngữ nghĩa tương đương.

## 2. Inline và materialization

### Inline: hợp nhất biểu thức vào truy vấn chính

Khi inline, bộ tối ưu xem phần truy vấn được đặt tên như một phần của truy vấn lớn. Nó có thể đẩy điều kiện từ truy vấn bên ngoài vào bên trong, loại bỏ cột không cần thiết, chọn lại thứ tự join và tận dụng chỉ mục ở bảng gốc.

Ví dụ:

```sql
WITH customer_orders AS (
    SELECT customer_id, order_id, created_at, total_amount
    FROM orders
)
SELECT order_id, total_amount
FROM customer_orders
WHERE customer_id = ?
  AND created_at >= ?;
```

Nếu CTE được inline, bộ tối ưu có thể áp dụng hai điều kiện trực tiếp lên `orders`, rồi dùng chỉ mục ghép phù hợp như `(customer_id, created_at)`. Nó không cần tạo trước một tập `customer_orders` gồm mọi đơn hàng.

### Materialization: tạo kết quả trung gian

Khi vật chất hóa, hệ quản trị tính một phần truy vấn và lưu kết quả tạm để bước sau đọc lại. Kết quả có thể nằm trong bộ nhớ hoặc được ghi ra vùng lưu trữ tạm nếu vượt giới hạn hay theo cách triển khai của hệ quản trị.

Vật chất hóa có thể hữu ích khi một phép tính tốn kém được dùng nhiều lần. Thay vì tính lại cùng một tập dữ liệu cho mỗi lần tham chiếu, hệ quản trị có thể tính một lần rồi tái sử dụng. Một số hệ quản trị còn có thể tạo chỉ mục tạm trên kết quả vật chất hóa để tăng tốc các lần tra cứu tiếp theo.

Đổi lại, hệ quản trị phải tạo, ghi và đọc tập trung gian. Nếu tập kết quả lớn, chi phí bộ nhớ, I/O tạm, sort hoặc ghi spill có thể cao. Vật chất hóa cũng có thể ngăn điều kiện bên ngoài được đẩy sâu vào truy vấn nguồn, khiến nhiều hàng được tính hơn mức cần thiết.

### Bảng so sánh đánh đổi

| Khía cạnh | Inline/merge | Materialization |
|---|---|---|
| Điều kiện lọc | Thường có cơ hội đẩy xuống nguồn | Có thể phải lọc sau khi tạo kết quả trung gian |
| Tái sử dụng kết quả | Có thể tính lại ở nhiều nhánh tham chiếu | Có thể tính một lần rồi đọc lại |
| Tối ưu toàn cục | Bộ tối ưu có nhiều cơ hội phối hợp join và index | Ranh giới trung gian có thể giới hạn một số phép biến đổi |
| Bộ nhớ và I/O tạm | Thường ít cần lưu toàn bộ kết quả riêng | Có chi phí lưu/đọc kết quả, có thể spill |
| Chi phí CPU | Có thể lặp lại phép tính nếu nhiều nhánh | Có thể tiết kiệm phép tính lặp nhưng phải tạo tập trung gian |
| Tính phù hợp | Truy vấn chọn lọc, cần pushdown hoặc nguồn dữ liệu nhỏ | Biểu thức đắt được tái sử dụng và kết quả có quy mô hợp lý |

Không có lựa chọn tốt nhất trong mọi tình huống. Cần đánh giá quy mô đầu vào, số lần tham chiếu, độ chọn lọc của bộ lọc, chi phí phép tính và khả năng tái sử dụng.

## 3. Predicate pushdown và ranh giới tối ưu

Predicate pushdown là việc đưa điều kiện lọc đến gần nguồn dữ liệu nhất có thể. Nếu truy vấn bên ngoài chỉ cần dữ liệu của một khách hàng, đẩy điều kiện `customer_id = ?` vào truy vấn đọc `orders` có thể giảm số hàng phải đọc, join và tổng hợp.

Xét ví dụ:

```sql
WITH order_data AS MATERIALIZED (
    SELECT order_id, customer_id, created_at, total_amount
    FROM orders
)
SELECT order_id, total_amount
FROM order_data
WHERE customer_id = ?;
```

Trong hệ quản trị hỗ trợ cú pháp này, `MATERIALIZED` yêu cầu tạo kết quả trung gian theo ngữ nghĩa của hệ thống. Nếu bảng `orders` có hàng trăm triệu dòng nhưng chỉ một khách hàng cần được tra cứu, việc tạo toàn bộ `order_data` trước rồi lọc có thể rất tốn kém.

Khi cho phép inline, bộ tối ưu có thể biến đổi truy vấn thành:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?;
```

Khi đó chỉ mục trên `customer_id` hoặc `(customer_id, created_at)` có thể được dùng trực tiếp. Ví dụ đầu tiên có từ khóa `MATERIALIZED` theo cú pháp PostgreSQL; không phải hệ quản trị nào cũng hỗ trợ cú pháp này.

### Không phải mọi điều kiện đều có thể đẩy xuống

Một số phép toán làm thay đổi ngữ nghĩa nếu đẩy điều kiện qua ranh giới, ví dụ `LIMIT`, `OFFSET`, `DISTINCT`, `GROUP BY`, window function hoặc phép tổng hợp. Hệ quản trị chỉ đẩy điều kiện khi phép biến đổi được chứng minh là tương đương.

Ví dụ, giới hạn 10 hàng trước khi lọc khác với lọc trước rồi mới lấy 10 hàng. Tương tự, đẩy điều kiện qua phép tổng hợp có thể yêu cầu biến đổi thành `HAVING` hoặc thay đổi kết quả. Vì vậy, sự hiện diện của CTE hoặc bảng dẫn xuất không bảo đảm mọi predicate đều được pushdown.

## 4. Khi nào materialization có thể có lợi?

Vật chất hóa đáng xem xét khi chi phí tạo kết quả trung gian được bù lại bằng việc tái sử dụng hoặc đơn giản hóa các bước tiếp theo.

### Một phép tính đắt được dùng nhiều lần

Giả sử cần tổng hợp doanh thu theo khách hàng một lần, sau đó dùng tập tổng hợp đó để tạo hai nhóm báo cáo:

```sql
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_spend
    FROM orders
    WHERE payment_status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id, c.full_name, t.total_spend
FROM customer AS c
JOIN customer_totals AS t
  ON t.customer_id = c.customer_id
WHERE t.total_spend >= ?;
```

Trong ví dụ này CTE chỉ được tham chiếu một lần. Nếu cùng một kết quả tổng hợp được dùng ở nhiều nhánh, materialization có thể giảm việc tính lại, nhưng kết quả còn phụ thuộc cơ chế của hệ quản trị. Với một CTE được tham chiếu nhiều lần, một số hệ quản trị mặc định vật chất hóa; một số hệ quản trị khác có thể mở rộng định nghĩa tại từng vị trí.

### Tập trung gian nhỏ hơn đáng kể so với đầu vào

Nếu phép lọc hoặc tổng hợp tạo ra tập nhỏ, lưu tập đó có thể rẻ hơn việc lặp lại một phép join lớn. Ví dụ, tổng hợp hàng triệu giao dịch thành vài nghìn tài khoản rồi tái sử dụng kết quả có thể là lựa chọn hợp lý.

### Cần một ranh giới tính toán có chủ đích

Materialization có thể giúp kiểm soát việc tính một biểu thức đắt hoặc tránh lặp một phép biến đổi phức tạp. Tuy nhiên, ranh giới đó phải được xác nhận trên kế hoạch thực tế; không nên dùng nó như cách chữa mọi truy vấn chậm.

## 5. Khi nào inline thường có lợi?

Inline thường đáng ưu tiên khi truy vấn bên ngoài chỉ cần một phần nhỏ dữ liệu từ CTE hoặc bảng dẫn xuất.

- Bộ lọc ngoài có độ chọn lọc cao và có thể tận dụng index ở bảng gốc.
- CTE được tham chiếu một lần và chỉ chứa phép chiếu/lọc đơn giản.
- Join order tốt nhất cần được chọn trên toàn bộ truy vấn.
- Vật chất hóa sẽ tạo một tập lớn trong khi nhánh sau chỉ dùng ít hàng hoặc ít cột.
- Điều kiện bên ngoài có thể loại bỏ phần lớn dữ liệu trước khi thực hiện phép tổng hợp hoặc join đắt.

Inline cũng có thể làm biểu thức được tính nhiều lần nếu có nhiều nhánh tham chiếu hoặc nếu bộ tối ưu không chia sẻ kết quả. Do đó, cần cân bằng khả năng pushdown với chi phí tính toán lặp.

## 6. CTE được tham chiếu nhiều lần

Số lần tham chiếu là một yếu tố quan trọng, nhưng cách hệ quản trị xử lý khác nhau. Hãy xem xét CTE được dùng hai lần:

```sql
WITH recent_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE created_at >= ?
)
SELECT 'HIGH_VALUE' AS group_name, COUNT(*) AS total
FROM recent_orders
WHERE total_amount >= 1000

UNION ALL

SELECT 'LOW_VALUE' AS group_name, COUNT(*) AS total
FROM recent_orders
WHERE total_amount < 1000;
```

Có hai khả năng khái quát:

1. Tính `recent_orders` một lần, lưu kết quả rồi áp dụng hai điều kiện cho hai nhánh.
2. Inline CTE vào từng nhánh, cho phép mỗi nhánh đẩy điều kiện riêng xuống nguồn nhưng có thể đọc và lọc `orders` nhiều lần.

Nếu điều kiện thời gian chọn ra một tập rất lớn nhưng mỗi nhánh chỉ cần một phần nhỏ, inline có thể giảm dữ liệu đọc cho từng nhánh. Nếu việc tạo `recent_orders` tốn kém và hai nhánh cùng cần phần lớn kết quả, materialization có thể tiết kiệm tính toán. Chỉ số và kế hoạch cụ thể quyết định phương án nào tốt hơn.

Nếu cần bảo đảm tái sử dụng một kết quả giữa nhiều câu lệnh riêng biệt, CTE không phải cơ chế lưu trữ thích hợp. Hãy cân nhắc bảng tạm hoặc bảng staging với vòng đời và chỉ mục được quản lý rõ ràng.

## 7. Khác biệt theo hệ quản trị

### PostgreSQL

PostgreSQL hỗ trợ `MATERIALIZED` và `NOT MATERIALIZED` cho CTE không đệ quy, không có tác dụng phụ và đáp ứng điều kiện inline của hệ thống. Từ PostgreSQL 12, CTE thông thường được tham chiếu một lần thường có thể được inline; CTE được tham chiếu nhiều lần mặc định thường được vật chất hóa. CTE có tính chất ngăn inline, chẳng hạn chứa hàm volatile hoặc một số cấu trúc đặc biệt, có thể có hành vi khác.

Ví dụ yêu cầu inline:

```sql
WITH customer_orders AS NOT MATERIALIZED (
    SELECT customer_id, order_id, created_at
    FROM orders
)
SELECT order_id
FROM customer_orders
WHERE customer_id = $1;
```

Ví dụ yêu cầu vật chất hóa:

```sql
WITH recent_orders AS MATERIALIZED (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    WHERE created_at >= $1
    GROUP BY customer_id
)
SELECT customer_id, order_count
FROM recent_orders
WHERE order_count >= 10;
```

`MATERIALIZED` và `NOT MATERIALIZED` là chỉ dẫn về cách xử lý CTE trong PostgreSQL, không phải cú pháp SQL dùng chung cho mọi nền tảng. `NOT MATERIALIZED` có thể khiến phần truy vấn được tính lại ở nhiều vị trí tham chiếu; chỉ dùng khi lợi ích của pushdown hoặc tối ưu riêng từng nhánh lớn hơn chi phí đó. Với phiên bản PostgreSQL trước 12, CTE thông thường thường hoạt động như ranh giới tối ưu và không được inline theo cách mặc định của phiên bản mới.

Kiểm tra bằng `EXPLAIN (ANALYZE, BUFFERS)`. Kế hoạch có thể hiển thị `CTE Scan`, `CTE`, `Materialize`, `Index Scan` hoặc các toán tử khác. Cần phân biệt tên toán tử `Materialize` trong plan với từ khóa điều khiển CTE; chúng liên quan đến lưu kết quả nhưng không phải lúc nào cũng là cùng một cơ chế.

### SQL Server

Trong SQL Server, CTE chủ yếu là biểu thức truy vấn có tên. CTE không mặc nhiên được lưu thành bảng tạm và không có từ khóa `MATERIALIZED`/`NOT MATERIALIZED` chuẩn để điều khiển như PostgreSQL.

```sql
WITH recent_orders AS (
    SELECT customer_id, order_id, created_at, total_amount
    FROM dbo.Orders
    WHERE created_at >= @StartDate
)
SELECT customer_id, COUNT(*) AS order_count
FROM recent_orders
GROUP BY customer_id;
```

Bộ tối ưu thường mở rộng CTE vào truy vấn chính và thực hiện các phép biến đổi tương tự truy vấn con hoặc view. Nếu CTE được tham chiếu nhiều lần, định nghĩa có thể được thực thi lại ở các nhánh; tuy nhiên, optimizer cũng có thể chọn spool hoặc một cấu trúc vật lý khác nếu có lợi. Không nên dựa vào giả định rằng CTE được tính đúng một lần.

Trong actual execution plan, hãy tìm `Table Spool`, `Index Spool`, `Eager Spool`, `Lazy Spool`, số lần thực thi và số hàng. Spool là quyết định của kế hoạch vật lý, không phải cam kết do cú pháp CTE tạo ra. Nếu cần tái sử dụng kết quả giữa nhiều câu lệnh, có thể dùng bảng tạm `#temp`, tạo chỉ mục và kiểm tra thống kê của bảng tạm.

### MySQL

MySQL 8.0 hỗ trợ CTE và derived table. Bộ tối ưu có thể **merge** (gộp) biểu thức vào truy vấn ngoài hoặc **materialize** kết quả trung gian. Quy tắc merge áp dụng cho cả derived table và nhiều CTE; một số cấu trúc như aggregate, window function, `DISTINCT`, `GROUP BY`, `HAVING`, `LIMIT`, `UNION` hoặc subquery trong danh sách chọn có thể ngăn merge theo các điều kiện của phiên bản.

Ví dụ:

```sql
WITH recent_orders AS (
    SELECT customer_id, order_id, total_amount
    FROM orders
    WHERE created_at >= ?
)
SELECT order_id, total_amount
FROM recent_orders
WHERE customer_id = ?;
```

MySQL có thể merge CTE để kết hợp các điều kiện với truy vấn nguồn. Khi CTE được vật chất hóa và tham chiếu nhiều lần, MySQL có thể tạo kết quả tạm một lần rồi tái sử dụng; tùy trường hợp, optimizer có thể tạo chỉ mục trên kết quả vật chất hóa để hỗ trợ truy cập. Cơ chế này có thể tiết kiệm việc tính lại, nhưng vẫn phải trả chi phí tạo và lưu kết quả.

MySQL hỗ trợ optimizer hint như `MERGE()` và `NO_MERGE()` trong những phiên bản phù hợp để tác động đến lựa chọn merge/materialization. Các hint chỉ nên dùng sau khi đo, vì chúng phụ thuộc phiên bản và có thể làm mất cơ hội tối ưu khác. Có thể xem `EXPLAIN`, `EXPLAIN FORMAT=TREE` hoặc `EXPLAIN ANALYZE` tùy phiên bản; `SHOW WARNINGS` có thể cung cấp thêm thông tin về hint bị bỏ qua.

### Oracle Database

Oracle hỗ trợ subquery factoring bằng mệnh đề `WITH`. Optimizer có thể inline query block, merge view hoặc dùng temporary-table transformation để vật chất hóa kết quả trung gian. Quyết định dựa trên chi phí và các điều kiện biến đổi truy vấn.

```sql
WITH recent_orders AS (
    SELECT customer_id, order_id, total_amount
    FROM orders
    WHERE created_at >= :start_date
)
SELECT customer_id, COUNT(*) AS order_count
FROM recent_orders
GROUP BY customer_id;
```

Kế hoạch có thể hiển thị `TEMP TABLE TRANSFORMATION`, `LOAD AS SELECT` hoặc truy cập một đối tượng tạm nội bộ khi optimizer chọn vật chất hóa. Nếu inline, phần truy vấn có thể được hợp nhất vào query block bên ngoài.

Trong thực tế có các hint `MATERIALIZE` và `INLINE` được sử dụng để thử tác động lên hành vi của subquery factoring. Tuy nhiên, cần xác minh trạng thái hỗ trợ và tài liệu đúng phiên bản; không nên coi các hint này là hợp đồng ổn định cho mọi bản Oracle. Ưu tiên để optimizer chọn theo chi phí, sau đó chỉ điều khiển khi có bằng chứng và kế hoạch theo dõi. Dùng `DBMS_XPLAN.DISPLAY_CURSOR` để kiểm tra kế hoạch thực thi thực tế, số hàng và buffer gets.

### Bảng tổng hợp

| Hệ quản trị | Hành vi thường gặp | Cách kiểm soát/quan sát |
|---|---|---|
| PostgreSQL | CTE một lần tham chiếu có thể inline; nhiều lần tham chiếu thường materialize theo mặc định ở phiên bản mới | `MATERIALIZED`, `NOT MATERIALIZED`; `EXPLAIN (ANALYZE, BUFFERS)` |
| SQL Server | CTE thường được mở rộng như biểu thức truy vấn; spool có thể xuất hiện do optimizer | Không có hint materialize cho CTE theo cú pháp chuẩn; actual plan và bảng tạm `#temp` |
| MySQL 8.0 | CTE/derived table có thể merge hoặc materialize; CTE vật chất hóa có thể được tái sử dụng | Optimizer hints `MERGE`/`NO_MERGE`; `EXPLAIN` và `EXPLAIN ANALYZE` |
| Oracle Database | Query block có thể inline/merge hoặc temporary-table transformation | Kiểm tra execution plan; hint theo phiên bản nếu thực sự cần |

Các mô tả trên là hành vi phổ biến, không thay thế tài liệu của đúng phiên bản, cấu hình và loại truy vấn đang vận hành.

## 8. Recursive CTE và lưu trữ trung gian

Recursive CTE dùng để duyệt cấu trúc phân cấp hoặc quan hệ có chiều sâu không cố định, chẳng hạn cây danh mục, sơ đồ tổ chức hoặc quan hệ cha-con. Cấu trúc thường có phần neo (*anchor member*) và phần đệ quy (*recursive member*):

```sql
WITH RECURSIVE category_tree AS (
    SELECT category_id, parent_id, category_name, 0 AS depth
    FROM category
    WHERE category_id = ?

    UNION ALL

    SELECT c.category_id, c.parent_id, c.category_name,
           t.depth + 1
    FROM category AS c
    JOIN category_tree AS t
      ON c.parent_id = t.category_id
)
SELECT category_id, parent_id, category_name, depth
FROM category_tree;
```

Đây là cú pháp recursive CTE được PostgreSQL và một số hệ quản trị hỗ trợ; SQL Server và Oracle có khác biệt cú pháp như `WITH` không dùng từ khóa `RECURSIVE` hoặc có cấu trúc riêng. Cần điều chỉnh theo nền tảng.

Quá trình đệ quy thường cần lưu hoặc quản lý tập hàng ở các vòng lặp để tạo vòng tiếp theo. Vì vậy, không nên áp dụng lập luận inline của CTE không đệ quy một cách máy móc cho recursive CTE. Cần chú ý điều kiện dừng, chu trình, số hàng phát sinh, giới hạn đệ quy và bộ nhớ/I/O của tập làm việc.

Nếu dữ liệu có chu trình, truy vấn cần cơ chế phát hiện hoặc ngăn lặp phù hợp. `UNION` có thể loại hàng trùng nhưng có chi phí so sánh và không phải lúc nào cũng giải quyết chu trình đúng theo khóa nghiệp vụ. `UNION ALL` thường tránh bước loại trùng nhưng cần bảo đảm điều kiện dừng. Hãy kiểm thử với cây sâu, nhánh rộng, dữ liệu lỗi và trường hợp chu trình.

## 9. CTE không phải bảng tạm

CTE có phạm vi trong một câu lệnh. Nó không tự tạo đối tượng bảng mà ứng dụng có thể tham chiếu trong câu lệnh kế tiếp. Ngay cả khi optimizer vật chất hóa CTE, kết quả tạm đó là chi tiết thực thi do hệ quản trị quản lý và không có vòng đời bảng tạm do ứng dụng điều khiển.

Nếu cần sử dụng cùng kết quả ở nhiều câu lệnh, cần tạo bảng tạm hoặc bảng staging rõ ràng:

```sql
-- Ví dụ SQL Server
SELECT customer_id, SUM(total_amount) AS total_spend
INTO #customer_totals
FROM dbo.Orders
WHERE payment_status = 'PAID'
GROUP BY customer_id;

CREATE INDEX IX_customer_totals_customer
ON #customer_totals (customer_id);

SELECT customer_id, total_spend
FROM #customer_totals
WHERE total_spend >= @MinimumSpend;
```

Bảng tạm cho phép chủ động tạo index, kiểm tra số hàng, dùng lại qua nhiều câu lệnh trong phạm vi kết nối hoặc transaction theo quy tắc hệ quản trị. Đổi lại, ứng dụng phải quản lý tạo/xóa, quyền, transaction, dung lượng tempdb hoặc tablespace tạm và đồng bộ dữ liệu.

### Khi nào chọn bảng tạm thay vì CTE?

- Kết quả trung gian được sử dụng trong nhiều câu lệnh riêng biệt.
- Cần tạo index riêng trên kết quả trung gian.
- Cần thống kê hoặc kiểm tra số hàng trung gian trước bước tiếp theo.
- Truy vấn quá phức tạp và việc chia thành các giai đoạn vật lý giúp kiểm soát tài nguyên.
- Cần lưu một snapshot dữ liệu trung gian trong phạm vi xử lý đã xác định.

Nếu chỉ cần đặt tên cho một phần truy vấn trong cùng câu lệnh, CTE hoặc bảng dẫn xuất thường đơn giản hơn. Đừng tạo bảng tạm cho mọi CTE; việc ghi/đọc tạm và quản lý vòng đời cũng có chi phí.

## 10. Cách đọc execution plan để nhận biết materialization

Khi điều tra, cần tìm dấu hiệu của việc inline, merge, spool hoặc tạo kết quả tạm. Tên toán tử thay đổi theo hệ quản trị, nhưng có thể tập trung vào các câu hỏi sau:

1. Truy vấn nguồn có được gộp vào query block bên ngoài không?
2. Điều kiện lọc của truy vấn ngoài có được đẩy xuống bảng gốc không?
3. Có bước tạo kết quả trung gian hoặc spool không?
4. Kết quả trung gian được đọc bao nhiêu lần và có được tái sử dụng không?
5. Số hàng ước lượng và thực tế ở mỗi bước có chênh lệch lớn không?
6. Có sort, hash, memory grant lớn hoặc spill ra vùng lưu trữ tạm không?
7. Chỉ mục ở bảng nguồn có được dùng sau khi biến đổi truy vấn không?

### Các chỉ số cần thu thập

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Quy mô trung gian | estimated rows, actual rows | Tập kết quả được tạo lớn đến đâu và ước lượng có đúng không |
| Số lần xử lý | loops, executions, rebinds/rewinds nếu có | Một biểu thức có bị tính lại nhiều lần không |
| Đọc dữ liệu | logical reads, physical reads, buffer hits | Chi phí truy cập bảng và kết quả tạm |
| CPU | CPU time, operator cost tham khảo | Chi phí tính biểu thức, join, sort và aggregate |
| Bộ nhớ | memory grant, memory usage, hash/sort spill | Tập trung gian có vượt khả năng xử lý trong bộ nhớ không |
| Độ trễ | elapsed time, p95/p99 | Tác động thực tế đến người dùng và workload |
| Tải tổng thể | throughput, I/O, temp space, wait | Tác động đến toàn hệ thống khi chạy đồng thời |

Chi phí ước lượng trong plan là mô hình của optimizer, không phải số đo thời gian thực. Hãy ưu tiên actual plan và số liệu runtime khi có thể, đồng thời tránh chạy phép đo gây tải lớn trực tiếp trên production nếu chưa đánh giá tác động.

## 11. Quy trình tối ưu CTE và bảng dẫn xuất

1. **Xác định mục tiêu:** truy vấn cần dễ đọc, tránh tính lại, đẩy bộ lọc xuống nguồn hay chia nhỏ xử lý?
2. **Ghi nhận baseline:** lưu SQL, tham số đại diện, số hàng, thời gian, logical reads, CPU và actual plan.
3. **Kiểm tra số lần tham chiếu:** CTE chỉ dùng một lần hay nhiều nhánh cùng dùng?
4. **Xác định độ chọn lọc:** truy vấn ngoài chỉ cần một phần nhỏ dữ liệu hay gần như toàn bộ kết quả trung gian?
5. **Kiểm tra phép toán cản merge:** aggregate, `DISTINCT`, window function, `LIMIT`, `UNION` và các cấu trúc đặc biệt.
6. **Đọc kế hoạch:** xác định inline, materialization, spool, temp table transformation hoặc phép scan.
7. **Thử một thay đổi:** viết lại CTE/bảng dẫn xuất, điều khiển materialization nếu hệ quản trị hỗ trợ, hoặc chuyển sang bảng tạm khi có lý do.
8. **Đo lại cùng điều kiện:** giữ nguyên dữ liệu, tham số, cache, mức đồng thời và thời gian đo.
9. **Đánh giá workload liên quan:** bảo đảm truy vấn khác, thao tác ghi và temp space không suy giảm đáng kể.
10. **Theo dõi sau triển khai:** kiểm tra khi dữ liệu, thống kê, phiên bản hoặc phân bố tham số thay đổi.

### Ví dụ so sánh hai hướng

Giả sử bảng `orders` có 100 triệu hàng, một khách hàng chỉ có vài trăm đơn hàng. Truy vấn cần lấy đơn hàng gần đây của một khách hàng:

```sql
WITH all_orders AS (
    SELECT order_id, customer_id, created_at, total_amount
    FROM orders
)
SELECT order_id, created_at, total_amount
FROM all_orders
WHERE customer_id = ?
  AND created_at >= ?;
```

Nếu CTE bị vật chất hóa toàn bộ, hệ thống có thể tạo một tập trung gian rất lớn trước khi lọc. Nếu được inline, truy vấn có thể dùng index `(customer_id, created_at)` để đọc trực tiếp một vùng nhỏ. Với ví dụ này, inline thường là hướng đáng thử đầu tiên.

Ngược lại, nếu một phép tính đắt tạo ra tập vài nghìn hàng được tham chiếu nhiều lần, materialization có thể giảm công việc lặp. Hãy so sánh số lần tính, kích thước tập trung gian, số lần đọc và chi phí lưu tạm trước khi chọn.

## 12. Những sai lầm thường gặp

1. **Cho rằng CTE luôn được vật chất hóa:** nhiều hệ quản trị inline hoặc merge CTE vào truy vấn ngoài.
2. **Cho rằng CTE luôn chạy đúng một lần:** SQL Server có thể mở rộng định nghĩa tại nhiều tham chiếu; kế hoạch vật lý quyết định việc tính lại hoặc spool.
3. **Ép materialization cho mọi truy vấn:** có thể tạo tập trung gian lớn và chặn predicate pushdown.
4. **Luôn ép inline:** biểu thức đắt được tham chiếu nhiều lần có thể phải tính lại và làm tăng CPU/I/O.
5. **Đồng nhất CTE với bảng tạm:** CTE có phạm vi câu lệnh; vật chất hóa nội bộ không tạo bảng do ứng dụng quản lý.
6. **Bỏ qua các phép toán cản merge:** aggregate, window, `DISTINCT`, `LIMIT` hoặc `UNION` có thể giới hạn biến đổi của optimizer.
7. **Chỉ nhìn thời gian một lần chạy:** cache nóng, tải nền và tham số khác nhau có thể làm kết quả sai lệch.
8. **Không kiểm tra số hàng trung gian:** estimated rows sai có thể khiến optimizer chọn chiến lược join, memory grant hoặc materialization không phù hợp.
9. **Dùng hint như cam kết lâu dài:** hint có thể thay đổi ý nghĩa hoặc không còn phù hợp sau nâng cấp và thay đổi dữ liệu.
10. **Không quản lý temp space:** spool, hash, sort và bảng tạm có thể gây I/O hoặc đầy vùng lưu trữ tạm.

## 13. Danh sách kiểm tra trước khi thay đổi

- [ ] Đã xác định phần truy vấn cần đặt tên bằng CTE hay bảng dẫn xuất.
- [ ] Đã xác minh CTE/bảng dẫn xuất được tham chiếu một lần hay nhiều lần.
- [ ] Đã kiểm tra khả năng inline/merge và các cấu trúc cản biến đổi.
- [ ] Đã đánh giá lợi ích predicate pushdown so với chi phí tính lại.
- [ ] Đã đo quy mô, số lần đọc và chi phí tạo tập trung gian.
- [ ] Đã đọc actual execution plan để nhận diện spool, materialize hoặc temporary-table transformation.
- [ ] Đã kiểm tra estimated rows, actual rows, loops, logical reads, CPU và spill.
- [ ] Đã dùng đúng cú pháp và cơ chế của phiên bản hệ quản trị đang chạy.
- [ ] Đã cân nhắc bảng tạm nếu cần tái sử dụng giữa nhiều câu lệnh hoặc tạo index riêng.
- [ ] Đã đo lại dưới workload đại diện và theo dõi tác động lên truy vấn khác.

CTE và bảng dẫn xuất giúp tổ chức SQL thành các phần dễ hiểu, nhưng chúng không tự quyết định dữ liệu trung gian được lưu hay tính lại. Inline có thể mở rộng cơ hội pushdown và tối ưu toàn cục; materialization có thể tiết kiệm phép tính lặp khi kết quả được tái sử dụng, nhưng phải trả chi phí tạo và lưu tập trung gian. PostgreSQL, SQL Server, MySQL và Oracle có quy tắc khác nhau, vì vậy hãy kiểm tra đúng phiên bản và execution plan thực tế. Chọn cách viết theo ngữ nghĩa, đo số hàng và tài nguyên, rồi chỉ điều khiển vật chất hóa khi kết quả kiểm thử chứng minh lợi ích trên workload của hệ thống.
