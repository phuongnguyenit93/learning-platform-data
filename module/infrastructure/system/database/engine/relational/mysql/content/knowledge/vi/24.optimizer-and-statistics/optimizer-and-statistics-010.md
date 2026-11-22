# Derived merge, materialization và đẩy điều kiện lọc

MySQL thường phải xử lý truy vấn có nhiều tầng: một truy vấn con trong `FROM`, một view hoặc một common table expression (CTE) có thể tạo ra kết quả trung gian để truy vấn bên ngoài tiếp tục lọc hoặc nối. Bộ tối ưu có hai cách chính để xử lý tầng trung gian đó: **merge** truy vấn con vào query block bên ngoài, hoặc **materialize** kết quả thành một bảng tạm nội bộ.

Nếu không thể merge, MySQL vẫn có thể tối ưu bằng **derived condition pushdown**: đưa các điều kiện từ truy vấn bên ngoài vào bên trong derived table trước khi materialize. Việc này giúp giảm số hàng cần tính và lưu trong kết quả trung gian. Hiểu ba cơ chế này giúp đọc execution plan, dự đoán chi phí và viết truy vấn dễ tối ưu hơn.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt merge và materialization đối với derived table, view và CTE.
- Nhận biết những cấu trúc truy vấn thường ngăn MySQL merge.
- Giải thích materialization trì hoãn, bảng tạm nội bộ và index tự động.
- Mô tả cách derived condition pushdown đưa điều kiện vào `WHERE` hoặc `HAVING`.
- Nhận biết vì sao `LIMIT` và một số ranh giới ngữ nghĩa ngăn đẩy điều kiện.
- Dùng `EXPLAIN`, `EXPLAIN ANALYZE` và optimizer trace để kiểm tra quyết định của optimizer.

Các ví dụ giả định MySQL 8.0 trở lên và InnoDB. `EXPLAIN ANALYZE` có từ MySQL 8.0.18; derived condition pushdown có từ MySQL 8.0.22. Hành vi chi tiết còn phụ thuộc phiên bản và cấu hình optimizer.

Các ví dụ chính dùng bảng giao dịch sau:

```sql
CREATE TABLE sales (
    sale_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(16) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_sales_status_customer (status, customer_id),
    KEY ix_sales_created_at (created_at)
) ENGINE = InnoDB;
```

## 1. Derived table là gì?

Derived table là một truy vấn con xuất hiện trong mệnh đề `FROM`. Kết quả của nó được đặt tên bằng alias để truy vấn bên ngoài sử dụng:

```sql
SELECT d.customer_id, d.amount
FROM (
    SELECT customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;
```

Trong ví dụ này, truy vấn bên trong tạo derived table `d`; truy vấn bên ngoài lọc các hàng của `d`. View và CTE cũng có thể tạo một query block trung gian tương tự:

```sql
WITH paid_sales AS (
    SELECT customer_id, amount
    FROM sales
    WHERE status = 'PAID'
)
SELECT customer_id, amount
FROM paid_sales
WHERE customer_id = 42;
```

Nếu MySQL luôn phải tạo toàn bộ kết quả `d` rồi mới lọc, truy vấn có thể tốn bộ nhớ, I/O và thời gian. Nhưng nếu có thể gộp hai tầng thành một query block, optimizer có thêm cơ hội chọn index, đổi thứ tự join và áp dụng điều kiện sớm.

## 2. Merge: gộp query block

**Derived table merge** thay derived table bằng phần truy vấn định nghĩa nó trong query block bên ngoài. Về khái niệm, ví dụ ở phần 1 có thể được gộp thành:

```sql
SELECT sales.customer_id, sales.amount
FROM sales
WHERE sales.status = 'PAID'
  AND sales.customer_id = 42;
```

Khi merge thành công, `d` không cần tồn tại như một bảng tạm độc lập. Optimizer có thể kết hợp điều kiện bên trong và bên ngoài, dùng index trên `sales`, và tối ưu các phép join như một truy vấn thống nhất.

### Khi nào merge có lợi?

Merge thường có lợi khi derived table chỉ chiếu các cột và lọc dữ liệu thông thường. Ví dụ:

```sql
SELECT d.sale_id, d.customer_id, d.amount
FROM (
    SELECT sale_id, customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;
```

Nếu bảng có index `(status, customer_id)`, optimizer có thể dùng cả hai điều kiện để định vị vùng nhỏ trong index. Không cần tạo bảng trung gian chứa tất cả giao dịch `PAID` trước khi lọc `customer_id`.

Merge còn giúp optimizer xem xét các bảng từ nhiều query block cùng lúc. Điều này có thể cải thiện thứ tự join, lựa chọn access path và khả năng đẩy điều kiện đến bảng gốc.

### Những cấu trúc thường ngăn merge

Một derived table không thể merge trong nhiều trường hợp có thể làm thay đổi ý nghĩa nếu bỏ ranh giới truy vấn. Các cấu trúc thường khiến MySQL phải materialize gồm:

- Hàm tổng hợp như `SUM()`, `COUNT()`, `AVG()`.
- `GROUP BY` hoặc `HAVING`.
- `DISTINCT`.
- `LIMIT`.
- `UNION` hoặc `UNION ALL`.
- Hàm cửa sổ (window function).
- Một số truy vấn có subquery trong select list hoặc phép gán user variable.

Ví dụ, truy vấn tổng hợp theo khách hàng cần giữ ranh giới nhóm:

```sql
SELECT d.customer_id, d.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    GROUP BY customer_id
) AS d
WHERE d.total_amount > 1000;
```

Nếu gộp tùy tiện, phép lọc có thể thay đổi tập hàng trước khi tính tổng. MySQL cần giữ phép tổng hợp trong query block riêng, nên derived table này được materialize. Tuy vậy, optimizer vẫn có thể đẩy một số điều kiện an toàn từ bên ngoài vào trong, như phần sau trình bày.

`ALGORITHM=TEMPTABLE` của view cũng yêu cầu xử lý view bằng bảng tạm, vì vậy ngăn merge view. `ALGORITHM=MERGE` yêu cầu merge khi định nghĩa view và ngữ cảnh cho phép; `UNDEFINED` để MySQL chọn cách phù hợp.

## 3. Materialization: tạo kết quả trung gian

Khi không thể hoặc không được merge, MySQL có thể **materialize** derived table thành một bảng tạm nội bộ. Query block bên ngoài đọc kết quả này như một nguồn dữ liệu.

Quy trình khái niệm:

```text
Truy vấn con trong FROM
          |
          v
  Chạy query block bên trong
          |
          v
  Tạo bảng tạm nội bộ
          |
          v
  Truy vấn bên ngoài đọc
  và lọc/nối kết quả tạm
```

Bảng tạm là chi tiết thực thi do MySQL quản lý, không phải bảng ứng dụng cần tự tạo hoặc tự xóa. Tùy kích thước, kiểu cột và cấu hình, internal temporary table có thể dùng bộ nhớ hoặc chuyển sang lưu trữ trên đĩa.

### Materialization có thể được trì hoãn

MySQL có thể trì hoãn materialization cho đến khi thật sự cần kết quả derived table. Nếu một bảng khác trong join được xử lý trước và không có hàng nào, optimizer có thể bỏ qua việc materialize derived table vì không cần đọc nó nữa.

Điều này có nghĩa materialization không nhất thiết xảy ra ngay khi câu lệnh bắt đầu. Khi đọc execution plan, hãy xem cả thứ tự join và điều kiện có thể làm một nhánh không cần thực thi.

### Index tự động trên bảng tạm

Khi materialize, MySQL có thể tạo index nội bộ trên một hoặc nhiều cột của bảng tạm nếu optimizer dự đoán việc tra cứu theo các cột đó giúp giảm chi phí. Ví dụ, truy vấn bên ngoài join derived table theo `customer_id`; index tự động có thể giúp tìm các hàng trong kết quả tạm hiệu quả hơn.

Với CTE được materialize và được tham chiếu nhiều lần, MySQL có thể tạo index phù hợp cho các cách truy cập khác nhau. Việc tạo index này do optimizer quản lý, không phải một index bền vững trong schema.

Materialization có thể hữu ích khi kết quả trung gian được dùng nhiều lần hoặc cần giữ ranh giới tổng hợp. Nhưng nó cũng có chi phí tạo bảng tạm, ghi/đọc dữ liệu và xây dựng index. Nếu kết quả rất lớn, chi phí này có thể đáng kể.

## 4. Derived condition pushdown

Khi derived table phải materialize, MySQL vẫn có thể đưa điều kiện của truy vấn bên ngoài vào query block bên trong. Cơ chế đó gọi là **derived condition pushdown**. Mục tiêu là loại bỏ hàng sớm, trước khi kết quả trung gian được tạo.

Ví dụ:

```sql
SELECT d.sale_id, d.customer_id, d.amount
FROM (
    SELECT sale_id, customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;
```

Nếu vì một lý do nào đó derived table được materialize, điều kiện `d.customer_id = 42` có thể được đẩy vào truy vấn bên trong:

```sql
SELECT sale_id, customer_id, amount
FROM sales
WHERE status = 'PAID'
  AND customer_id = 42;
```

Thay vì materialize tất cả giao dịch đã thanh toán, MySQL chỉ cần tạo kết quả phù hợp với khách hàng 42. Điều kiện được đẩy xuống giúp giảm số hàng trung gian, bộ nhớ và I/O.

Derived condition pushdown được hỗ trợ từ MySQL 8.0.22 và được điều khiển bằng cờ `derived_condition_pushdown` trong `optimizer_switch`.

## 5. Đẩy điều kiện qua GROUP BY: WHERE và HAVING

Với derived table có `GROUP BY`, điều kiện bên ngoài có thể thuộc hai nhóm:

- Điều kiện trên cột nhóm có thể được đẩy vào `WHERE` trước khi tổng hợp.
- Điều kiện trên kết quả tổng hợp phải được đẩy vào `HAVING`, sau khi tính aggregate.

Ví dụ:

```sql
SELECT d.customer_id, d.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
WHERE d.customer_id = 42
  AND d.total_amount > 1000;
```

Optimizer có thể biến đổi query block bên trong thành dạng tương đương:

```sql
SELECT customer_id, SUM(amount) AS total_amount
FROM sales
WHERE status = 'PAID'
  AND customer_id = 42
GROUP BY customer_id
HAVING SUM(amount) > 1000;
```

`customer_id = 42` được áp dụng trước khi nhóm, nhờ đó MySQL chỉ phải đọc các giao dịch của khách hàng đó. Điều kiện `total_amount > 1000` phụ thuộc kết quả `SUM(amount)`, nên phải được đánh giá sau tổng hợp trong `HAVING`.

Không thể đưa điều kiện tổng hợp vào `WHERE` vì ở thời điểm `WHERE` chạy, giá trị `SUM(amount)` chưa tồn tại. Giữ đúng thứ tự ngữ nghĩa là điều kiện bắt buộc của mọi phép pushdown.

## 6. Đẩy điều kiện vào từng nhánh UNION

Derived table có `UNION` hoặc `UNION ALL` không thể merge như một query block đơn giản. Tuy nhiên, MySQL có thể đẩy điều kiện phù hợp từ bên ngoài vào từng nhánh:

```sql
SELECT u.customer_id, u.amount
FROM (
    SELECT customer_id, amount
    FROM sales
    WHERE status = 'PAID'

    UNION ALL

    SELECT customer_id, amount
    FROM sales_archive
    WHERE status = 'PAID'
) AS u
WHERE u.customer_id = 42;
```

Trong ví dụ này, giả sử bảng lưu trữ `sales_archive` có cùng các cột và kiểu dữ liệu với `sales`; có thể tạo bảng thử nghiệm bằng `CREATE TABLE sales_archive LIKE sales` rồi nạp dữ liệu lịch sử.

Điều kiện có thể được đưa vào cả hai nhánh:

```sql
SELECT customer_id, amount
FROM sales
WHERE status = 'PAID'
  AND customer_id = 42

UNION ALL

SELECT customer_id, amount
FROM sales_archive
WHERE status = 'PAID'
  AND customer_id = 42;
```

Mỗi nhánh có thể sử dụng index riêng của bảng nguồn. Kết quả trung gian sau `UNION ALL` nhỏ hơn vì không phải gom mọi khách hàng rồi mới lọc ở bên ngoài.

## 7. Vì sao không thể đẩy mọi điều kiện xuống?

Optimizer chỉ được pushdown khi phép biến đổi bảo toàn kết quả truy vấn. `LIMIT` là ví dụ rõ ràng:

```sql
SELECT d.sale_id, d.customer_id
FROM (
    SELECT sale_id, customer_id
    FROM sales
    ORDER BY created_at DESC
    LIMIT 10
) AS d
WHERE d.customer_id = 42;
```

Ý nghĩa của truy vấn là: lấy 10 giao dịch mới nhất trên toàn bảng, sau đó chỉ giữ giao dịch của khách hàng 42. Nếu đẩy `customer_id = 42` vào trong trước `LIMIT`, truy vấn sẽ trở thành lấy 10 giao dịch mới nhất của riêng khách hàng 42. Hai kết quả không tương đương.

Vì vậy, derived table chứa `LIMIT` không cho phép derived condition pushdown theo cách làm thay đổi tập hàng được giới hạn. Tương tự, điều kiện liên quan đến kết quả window function hoặc các biểu thức có ngữ nghĩa đặc biệt phải được đặt đúng giai đoạn. Không nên tự viết lại truy vấn chỉ để đẩy điều kiện nếu chưa chứng minh được hai cách có cùng kết quả.

Các giới hạn khác có thể phụ thuộc loại query block, loại biểu thức và phiên bản MySQL. Nếu optimizer không pushdown một điều kiện, hãy kiểm tra execution plan và tài liệu của phiên bản đang chạy thay vì giả định đó là lỗi.

## 8. Derived table, view và CTE

| Cấu trúc | Merge | Materialization | Điểm cần nhớ |
|---|---|---|---|
| Derived table trong `FROM` | Có thể, nếu cấu trúc cho phép | Khi không merge hoặc bị yêu cầu materialize | `derived_merge` điều khiển nỗ lực merge |
| View `ALGORITHM=MERGE` | Merge nếu định nghĩa cho phép | Không dùng materialization như lựa chọn chính của view | Giúp optimizer kết hợp view với query bên ngoài |
| View `ALGORITHM=TEMPTABLE` | Không merge | Tạo kết quả trung gian | Giữ ranh giới thực thi của view |
| View `ALGORITHM=UNDEFINED` | Optimizer quyết định | Có thể materialize khi cần | Là lựa chọn mặc định thường gặp |
| CTE không đệ quy | Có thể merge hoặc materialize | Có thể materialize, nhất là khi được tham chiếu nhiều lần hoặc không mergeable | Materialized CTE có thể được dùng lại trong cùng câu lệnh |
| CTE đệ quy | Không xử lý như một derived table merge thông thường | Dùng cơ chế materialization cho kết quả đệ quy | Cần xem riêng quy tắc CTE đệ quy |

Ví dụ tạo view:

```sql
CREATE ALGORITHM = MERGE VIEW paid_sales AS
SELECT sale_id, customer_id, amount
FROM sales
WHERE status = 'PAID';

SELECT sale_id, amount
FROM paid_sales
WHERE customer_id = 42;
```

Với `ALGORITHM=MERGE`, view có thể được gộp vào truy vấn ngoài để điều kiện `customer_id = 42` cùng tham gia tối ưu trên bảng `sales`. Nếu dùng `ALGORITHM=TEMPTABLE`, view được materialize và điều kiện ngoài có thể được xem xét cho derived condition pushdown khi đáp ứng điều kiện hỗ trợ.

CTE có thể được tham chiếu nhiều lần:

```sql
WITH customer_sales AS (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT a.customer_id,
       a.total_amount AS current_total,
       benchmark.total_amount AS benchmark_total
FROM customer_sales AS a
JOIN customer_sales AS benchmark
  ON benchmark.customer_id = 42
WHERE a.total_amount > benchmark.total_amount;
```

Nếu CTE được materialize, MySQL có thể tạo kết quả một lần rồi dùng lại cho các tham chiếu trong câu lệnh. Ở ví dụ này, CTE cung cấp cả tập tổng doanh thu của từng khách hàng và tổng doanh thu của khách hàng 42 làm mốc so sánh. Optimizer có thể thêm index nội bộ để hỗ trợ các cách truy cập khác nhau. Điều này có thể tránh chạy lại toàn bộ phép tổng hợp, nhưng vẫn cần chi phí tạo và lưu kết quả trung gian.

## 9. Điều khiển optimizer để thử nghiệm

Hai cờ `optimizer_switch` liên quan trực tiếp:

| Cờ | Vai trò |
|---|---|
| `derived_merge` | Bật/tắt nỗ lực merge derived table và view có thể merge |
| `derived_condition_pushdown` | Bật/tắt nỗ lực đẩy điều kiện từ query bên ngoài vào derived table materialized |

Kiểm tra giá trị hiện tại:

```sql
SELECT @@SESSION.optimizer_switch;
```

Có thể tạm lưu cấu hình session, tắt hai cơ chế để so sánh kế hoạch, sau đó khôi phục:

```sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch =
    'derived_merge=off,derived_condition_pushdown=off';

EXPLAIN FORMAT=TREE
SELECT d.sale_id, d.customer_id, d.amount
FROM (
    SELECT sale_id, customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;

SET SESSION optimizer_switch = @saved_optimizer_switch;
```

Lệnh trên chỉ thay đổi cấu hình của session hiện tại. Trong ứng dụng dùng connection pool, không để lại thay đổi session sau khi thử nghiệm; luôn khôi phục giá trị đã lưu trước khi trả connection về pool. Nếu một câu lệnh lỗi giữa chừng, vẫn phải chạy bước khôi phục.

Có thể dùng optimizer hint `MERGE()` hoặc `NO_MERGE()` cho alias của derived table để thử nghiệm một query cụ thể:

```sql
SELECT /*+ NO_MERGE(d) */
       d.sale_id, d.customer_id, d.amount
FROM (
    SELECT sale_id, customer_id, amount
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;
```

Các hint điều khiển derived condition pushdown cũng có trên các phiên bản hỗ trợ, nhưng cần kiểm tra phiên bản và cú pháp tương ứng. Hint là công cụ chẩn đoán hoặc giải quyết trường hợp đã đo đạc rõ ràng; không nên thêm hàng loạt chỉ để ép optimizer theo một kế hoạch cố định.

## 10. Quan sát bằng EXPLAIN và optimizer trace

### EXPLAIN FORMAT=TREE

```sql
EXPLAIN FORMAT=TREE
SELECT d.customer_id, d.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
WHERE d.customer_id = 42
  AND d.total_amount > 1000;
```

Trong tree plan, tìm các node thể hiện materialize, scan bảng tạm, aggregate và điều kiện lọc. Tùy phiên bản, tên node và cách trình bày có thể khác. Nếu derived table được merge, plan thường thể hiện trực tiếp bảng gốc mà không có node materialize cho derived table đó. Nếu được materialize, plan có thể thể hiện node `Materialize` hoặc nguồn `<derivedN>`. Nếu điều kiện được pushdown, bạn có thể thấy nó xuất hiện ở query block bên trong thay vì chỉ ở node ngoài. `Using temporary` trong định dạng tabular không tự nó chứng minh một derived table đã được materialize; temporary table còn được dùng cho các thao tác khác như một số kiểu grouping hoặc sorting.

### EXPLAIN ANALYZE

Từ MySQL 8.0.18, `EXPLAIN ANALYZE` thực thi câu `SELECT` và hiển thị số liệu thực tế như thời gian, số hàng và số vòng lặp:

```sql
EXPLAIN ANALYZE
SELECT d.customer_id, d.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM sales
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS d
WHERE d.customer_id = 42
  AND d.total_amount > 1000;
```

Lệnh này thực sự chạy truy vấn. Hãy cân nhắc tải hệ thống và phạm vi dữ liệu trước khi chạy trên production; không dùng `EXPLAIN ANALYZE` một cách tùy tiện cho câu lệnh có tác dụng ghi.

### Optimizer trace

Khi cần hiểu vì sao optimizer chọn merge hoặc materialization, có thể bật optimizer trace trong session:

```sql
SET optimizer_trace = 'enabled=on';

SELECT d.sale_id, d.customer_id
FROM (
    SELECT sale_id, customer_id
    FROM sales
    WHERE status = 'PAID'
) AS d
WHERE d.customer_id = 42;

SELECT TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;

SET optimizer_trace = 'enabled=off';
```

Trace chứa chi tiết các bước optimizer đã cân nhắc. Cấu trúc JSON khá dài và thay đổi theo phiên bản; hãy tìm các phần liên quan đến derived table, merge, materialization và condition pushdown. Tắt trace sau khi hoàn tất để tránh thu thập thông tin không cần thiết trong các câu lệnh tiếp theo.

## 11. Derived condition pushdown khác gì ICP?

Hai khái niệm đều nói đến việc lọc sớm nhưng hoạt động ở những tầng khác nhau:

| Cơ chế | Tầng thực hiện | Mục tiêu |
|---|---|---|
| Derived condition pushdown | Giữa query block ngoài và query block derived bên trong | Giảm hàng trước khi materialize derived table |
| Index Condition Pushdown (ICP) | Phối hợp giữa MySQL server và storage engine khi quét secondary index | Lọc index entry trước khi phải đọc đầy đủ hàng từ clustered index |
| Partition pruning | Giai đoạn chọn partition | Bỏ qua partition không thể chứa hàng thỏa điều kiện |

Một truy vấn có thể hưởng lợi từ nhiều cơ chế cùng lúc. Ví dụ, derived condition pushdown đưa `customer_id = 42` vào truy vấn bên trong; sau đó truy vấn bên trong có thể dùng index `(status, customer_id)` để định vị hàng. ICP là một tối ưu khác, có thể tiếp tục lọc điều kiện phù hợp ngay khi quét index.

## 12. Quy trình phân tích truy vấn có derived table

Khi một truy vấn nhiều tầng chạy chậm, hãy kiểm tra theo thứ tự:

1. Xác định query block nào tạo derived table, view hoặc CTE; ghi rõ điều kiện trong và ngoài.
2. Kiểm tra derived table có cấu trúc ngăn merge như aggregate, `GROUP BY`, `DISTINCT`, `LIMIT`, `UNION` hoặc window function không.
3. Nếu có thể merge, xem `EXPLAIN` để xác nhận optimizer đã gộp và chọn index nào.
4. Nếu phải materialize, xem điều kiện ngoài nào có thể pushdown và số hàng trung gian còn lại.
5. Với `GROUP BY`, phân loại điều kiện thuộc cột nhóm (`WHERE`) và điều kiện aggregate (`HAVING`).
6. Kiểm tra index trên bảng gốc và index tự động của bảng tạm nếu có.
7. Dùng `EXPLAIN ANALYZE` trên môi trường phù hợp để so sánh số hàng ước lượng với số hàng thực tế.
8. Chỉ thử tắt/bật optimizer switch hoặc dùng hint trong session kiểm soát; khôi phục cấu hình sau thử nghiệm.

Không phải materialization luôn chậm hoặc merge luôn tốt. Nếu kết quả trung gian nhỏ, được dùng nhiều lần hoặc có thể tạo index nội bộ hữu ích, materialization có thể rẻ hơn việc mở rộng và tính lại query block. Quyết định cuối cùng phải dựa trên dữ liệu và số đo.

## 13. Bài thực hành

Giả sử có bảng `sales(sale_id, customer_id, status, amount, created_at)` và index `(status, customer_id)`.

1. Viết derived table chỉ chọn giao dịch `PAID`, sau đó lọc `customer_id = 42`. Chạy `EXPLAIN` và xác định query block có được merge hay không.
2. Thêm `GROUP BY customer_id` và `SUM(amount)` vào derived table. Quan sát materialization trong execution plan.
3. Thêm điều kiện ngoài `customer_id = 42` và `total_amount > 1000`. Xác định điều kiện nào có thể đi vào `WHERE`, điều kiện nào phải thành `HAVING`.
4. Tạo derived table chứa `UNION ALL` từ `sales` và `sales_archive`. Quan sát điều kiện khách hàng có được đẩy vào cả hai nhánh không.
5. Thêm `ORDER BY created_at DESC LIMIT 10` vào derived table. Giải thích vì sao điều kiện khách hàng không thể được đẩy vào trước `LIMIT` mà vẫn giữ nguyên kết quả.
6. So sánh kế hoạch khi tắt `derived_merge` và `derived_condition_pushdown` trong session thử nghiệm. Khôi phục `optimizer_switch` sau khi hoàn tất.
7. Dùng `EXPLAIN ANALYZE` để so sánh số hàng trung gian và thời gian thực thi giữa các cách viết truy vấn.

## Ghi nhớ

- Merge gộp derived query block vào truy vấn ngoài, giúp optimizer có thêm cơ hội chọn index và tối ưu join.
- Materialization tạo bảng tạm nội bộ; quá trình này có thể trì hoãn và có thể được hỗ trợ bởi index tự động.
- Derived condition pushdown giảm dữ liệu trung gian bằng cách đưa điều kiện an toàn vào truy vấn bên trong.
- Với `GROUP BY`, điều kiện cột nhóm có thể vào `WHERE`, còn điều kiện aggregate phải vào `HAVING`.
- `LIMIT` và các ranh giới ngữ nghĩa có thể ngăn merge hoặc pushdown để giữ nguyên kết quả.
- Dùng `EXPLAIN`, `EXPLAIN ANALYZE` và optimizer trace để hiểu kế hoạch thực tế; luôn khôi phục cấu hình session sau thử nghiệm.
