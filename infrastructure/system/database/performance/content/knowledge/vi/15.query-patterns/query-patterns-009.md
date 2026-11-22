# Kiểm chứng ngữ nghĩa, bản ghi trùng và giá trị NULL sau khi viết lại SQL

Viết lại SQL có thể giảm số lần đọc, loại bỏ một phép nối thừa, tận dụng chỉ mục hoặc giúp bộ tối ưu chọn kế hoạch tốt hơn. Nhưng hai câu truy vấn nhìn có vẻ tương đương chưa chắc trả về cùng kết quả. SQL thường xử lý kết quả theo **đa tập** (bag/multiset), nghĩa là một hàng có thể xuất hiện nhiều lần; đồng thời `NULL` làm các phép so sánh vận hành theo logic ba giá trị. Những khác biệt này dễ bị che khuất nếu chỉ so sánh số hàng tổng cộng hoặc thử trên dữ liệu đơn giản.

Bài học thuộc chương **Mẫu truy vấn** của module **DATABASE_PERFORMANCE**. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, mọi phép viết lại trong bài cần được kiểm chứng cả ngữ nghĩa lẫn hiệu năng trên workload đại diện. Một truy vấn nhanh hơn chỉ là cải thiện khi nó vẫn trả đúng những hàng cần thiết, đúng số lần xuất hiện và đúng quy tắc xử lý giá trị thiếu.

## 1. Tương đương SQL phải xét cả giá trị và số lần xuất hiện

Trong mô hình quan hệ cổ điển, một quan hệ thường được mô tả như tập hợp các bộ, không có hàng trùng. SQL trong thực tế thường giữ hàng trùng, trừ khi toán tử được yêu cầu loại trùng như `DISTINCT`, `UNION` hoặc một số phép toán tập hợp. Vì vậy, kết quả truy vấn thường là một đa tập.

Ví dụ bảng `orders` có hai đơn hàng cùng `customer_id = 10`. Truy vấn:

```sql
SELECT customer_id
FROM orders;
```

có thể trả về:

```text
customer_id
-----------
10
10
20
```

Nếu thay bằng:

```sql
SELECT DISTINCT customer_id
FROM orders;
```

kết quả chỉ còn `10` và `20`. Giá trị phân biệt giống nhau nhưng số lần xuất hiện khác nhau. Nếu tầng ứng dụng dựa vào số hàng để tính tổng, phân trang, lập hóa đơn hoặc đếm giao dịch, thay đổi này có thể làm sai nghiệp vụ.

Khi nói hai truy vấn tương đương, cần xác định rõ đang muốn:

- Cùng các giá trị phân biệt, bỏ qua số lần lặp (set equivalence).
- Cùng các hàng và cùng số lần xuất hiện của từng hàng (bag equivalence).
- Cùng thứ tự hàng được trả về, ngoài việc cùng giá trị và số lần xuất hiện (ordered-result equivalence).

Phần lớn truy vấn SQL không có `ORDER BY` chỉ cam kết tập kết quả theo đa tập, không cam kết thứ tự. Nếu API hoặc nghiệp vụ yêu cầu thứ tự, phải kiểm chứng riêng thứ tự đó bằng một `ORDER BY` xác định.

## 2. Bản ghi trùng thường phát sinh từ đâu?

### 2.1. JOIN một-nhiều và nhiều-nhiều

Một phép nối tạo một hàng kết quả cho mỗi cặp hàng thỏa điều kiện nối. Nếu một khách hàng có 3 đơn hàng, nối `customers` với `orders` theo `customer_id` sẽ tạo 3 hàng cho khách hàng đó. Đây là hành vi đúng của phép nối một-nhiều, không phải lỗi của hệ quản trị.

Ví dụ:

```sql
SELECT c.customer_id, c.full_name, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
```

Nếu bảng bên phải có nhiều hàng khớp, mỗi hàng bên trái được lặp lại tương ứng. Với phép nối nhiều-nhiều, số hàng có thể tăng theo tích số lượng hàng khớp ở hai phía. Nếu một khách hàng có 3 đơn hàng và mỗi đơn hàng có 4 dòng chi tiết, nối cả ba bảng có thể tạo 12 hàng cho khách hàng đó.

### 2.2. Dữ liệu khóa không duy nhất

Một phép nối được kỳ vọng là một-một nhưng cột nối ở bảng tham chiếu không có constraint duy nhất có thể tạo ra nhiều kết quả. Ví dụ:

```sql
SELECT o.order_id, p.product_name
FROM orders AS o
JOIN products AS p
  ON p.product_code = o.product_code;
```

Nếu `products.product_code` có hai hàng cùng mã, mỗi đơn hàng dùng mã đó sẽ xuất hiện hai lần. Trước khi tối ưu, cần xác nhận mô hình dữ liệu và constraint có phản ánh đúng giả định một-một hay không.

### 2.3. UNION ALL, dữ liệu nguồn lặp và phép chiếu

`UNION ALL` giữ tất cả hàng từ các nhánh, kể cả hàng giống hệt nhau. Bản ghi trùng cũng có thể đến từ bảng staging, đồng bộ dữ liệu, event log hoặc phép chiếu chỉ lấy một vài cột khiến các hàng khác nhau trở thành giống nhau trong kết quả.

Ví dụ hai đơn hàng khác `order_id` nhưng cùng `customer_id` sẽ trông như hai hàng trùng nếu chỉ chọn `customer_id`. Trước khi thêm `DISTINCT`, hãy xác định trùng theo khóa nghiệp vụ nào và liệu số lần xuất hiện có ý nghĩa hay không.

## 3. NULL ảnh hưởng đến phép nối và phép lọc

`NULL` biểu thị giá trị chưa biết hoặc không được xác định. So sánh thông thường với `NULL` trả về `UNKNOWN`, không phải `TRUE` hoặc `FALSE`:

```sql
NULL = NULL       -- UNKNOWN
NULL <> 10        -- UNKNOWN
NOT (NULL = 10)   -- UNKNOWN
```

`WHERE` chỉ giữ hàng khi điều kiện là `TRUE`; hàng có kết quả `FALSE` hoặc `UNKNOWN` đều bị loại. Vì vậy:

```sql
SELECT *
FROM customers
WHERE middle_name = NULL;
```

không tìm được các hàng có `middle_name` rỗng theo nghĩa `NULL`. Phải dùng:

```sql
WHERE middle_name IS NULL
```

### 3.1. NULL trong điều kiện JOIN

Với phép nối bằng thông thường:

```sql
SELECT a.external_code, b.description
FROM source_rows AS a
JOIN target_rows AS b
  ON a.external_code = b.external_code;
```

hai hàng có `external_code IS NULL` ở cả hai phía không khớp nhau, vì `NULL = NULL` là `UNKNOWN`. Nếu nghiệp vụ muốn hai giá trị thiếu được coi là tương đương, cần dùng phép so sánh null-safe được hệ quản trị hỗ trợ, chẳng hạn `IS NOT DISTINCT FROM` hoặc toán tử `<=>` của MySQL. Đây là thay đổi ngữ nghĩa, có thể làm tăng số cặp khớp nếu mỗi bên có nhiều hàng `NULL`.

### 3.2. NULL trong NOT IN

`NOT IN` có thể cho kết quả bất ngờ nếu tập bên phải chứa `NULL`:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers AS b
);
```

Nếu subquery trả về `10`, `20`, `NULL`, thì với `customer_id = 30`, các so sánh `30 <> 10` và `30 <> 20` đúng, nhưng `30 <> NULL` là `UNKNOWN`. Toàn bộ điều kiện không thành `TRUE`, nên hàng bị loại.

Nếu yêu cầu nghiệp vụ là “không tồn tại hàng chặn có cùng mã”, `NOT EXISTS` thường diễn đạt rõ hơn:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = c.customer_id
);
```

Nhưng `NOT EXISTS` có thể giữ hàng bên trái có `customer_id IS NULL`, vì không có phép so sánh nào tạo ra hàng khớp. `NOT IN` với tập bên phải không rỗng thường loại hàng đó. Nếu chỉ nhận mã khách hàng xác định, thêm `c.customer_id IS NOT NULL` theo đúng yêu cầu nghiệp vụ. Không thay `NOT IN` bằng `NOT EXISTS` một cách máy móc.

## 4. JOIN và EXISTS: khi nào phép nối làm nhân bản hàng?

Nếu mục tiêu chỉ là kiểm tra một hàng có ít nhất một hàng liên quan, `EXISTS` thường thể hiện ý định tốt hơn `JOIN`.

Giả sử muốn lấy khách hàng có ít nhất một đơn hàng:

```sql
-- Cách dùng JOIN
SELECT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
```

Khách hàng có nhiều đơn hàng sẽ xuất hiện nhiều lần. Nếu chỉ muốn mỗi khách hàng xuất hiện một lần, có thể dùng `DISTINCT`, nhưng phép nối vẫn tạo các cặp hàng trước khi loại trùng về mặt logic.

Diễn đạt trực tiếp mục tiêu tồn tại:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

`EXISTS` chỉ kiểm tra có ít nhất một hàng phù hợp, nên không nhân bản hàng khách hàng theo số đơn hàng. Bộ tối ưu thường có thể chuyển mẫu này thành semi-join và dừng tìm kiếm khi tìm thấy hàng khớp đầu tiên, nhưng kế hoạch cụ thể cần được xác nhận.

### 4.1. Chỉ thay JOIN bằng EXISTS khi không cần cột bên phải

Nếu truy vấn cần trả về `order_id`, `created_at` hoặc tính tổng theo từng đơn hàng, `EXISTS` không thay thế trực tiếp được phép nối vì nó không cung cấp các cột đó. Nếu muốn tổng hợp số đơn hàng theo khách hàng, cần giữ phép nối hoặc dùng subquery tổng hợp phù hợp.

### 4.2. EXISTS và bản ghi trùng bên phải

Với mục tiêu kiểm tra tồn tại, một hay một trăm hàng khớp đều cho cùng kết quả `TRUE`. Vì vậy, `EXISTS` không bị ảnh hưởng bởi số bản ghi trùng bên phải theo cách `JOIN` bị nhân hàng. Tuy nhiên, bản ghi trùng vẫn có thể làm phép nối hoặc phép tổng hợp khác sai nếu truy vấn phụ thuộc số lượng hàng.

## 5. LEFT JOIN và điều kiện lọc: ON khác WHERE

`LEFT JOIN` giữ hàng bên trái ngay cả khi không tìm thấy hàng phù hợp bên phải; các cột bên phải được điền `NULL`. Vị trí điều kiện lọc có thể thay đổi điều đó.

Muốn lấy tất cả khách hàng và thông tin đơn hàng đang mở nếu có:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'OPEN';
```

Điều kiện `o.status = 'OPEN'` nằm trong `ON`, nên khách hàng không có đơn hàng mở vẫn được giữ với cột `order_id` là `NULL`.

Nếu chuyển điều kiện xuống `WHERE`:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'OPEN';
```

các hàng không có đơn hàng sẽ có `o.status = NULL`; điều kiện trong `WHERE` trả về `UNKNOWN` và loại chúng. Truy vấn lúc này có hành vi gần với inner join đối với điều kiện đó.

### 5.1. Anti-join bằng LEFT JOIN ... IS NULL

Để tìm khách hàng không có đơn hàng mở:

```sql
SELECT c.customer_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'OPEN'
WHERE o.order_id IS NULL;
```

Điều kiện kiểm tra phải dùng cột bên phải được bảo đảm `NOT NULL` khi có hàng khớp, thường là khóa chính như `order_id`. Nếu dùng một cột nghiệp vụ cho phép `NULL`, hàng đã khớp vẫn có thể bị hiểu nhầm là không khớp.

Mẫu này thường có thể được bộ tối ưu biến thành anti-join, tương tự `NOT EXISTS`. Hãy kiểm tra kế hoạch và đo thực tế trước khi chọn cú pháp.

## 6. UNION, UNION ALL và DISTINCT

`UNION ALL` ghép kết quả của các nhánh và giữ nguyên số lần xuất hiện. `UNION` loại hàng trùng trong kết quả ghép. Ví dụ:

```sql
SELECT email FROM customers_2025
UNION ALL
SELECT email FROM customers_2026;
```

Nếu một email có ở cả hai bảng, nó xuất hiện hai lần. Thay bằng `UNION` sẽ gộp các hàng giống nhau thành một.

Loại trùng có thể cần sort hoặc hash aggregate, sử dụng CPU, bộ nhớ và có thể spill ra đĩa. Nếu nghiệp vụ yêu cầu giữ từng bản ghi nguồn, `UNION ALL` thường đúng hơn và tránh công việc loại trùng. Nếu nghiệp vụ yêu cầu danh sách giá trị duy nhất, `UNION` hoặc `DISTINCT` có thể là bắt buộc.

### 6.1. DISTINCT không phải cách sửa mọi phép JOIN

Thêm `DISTINCT` có thể che giấu nguyên nhân nhân hàng do điều kiện join sai hoặc dữ liệu khóa không duy nhất. Nó cũng có thể loại bỏ hai hàng khác nhau về mặt nghiệp vụ nhưng giống nhau ở các cột đang chọn.

Trước khi thêm `DISTINCT`, hãy hỏi:

- Vì sao có nhiều hàng cùng giá trị được chọn?
- Các hàng đó là bản ghi trùng thật hay các thực thể khác nhau bị chiếu thành cùng một kết quả?
- Có cần một hàng cho mỗi khóa nghiệp vụ hay cần giữ mọi giao dịch?
- Có thể sửa điều kiện nối hoặc dùng `EXISTS` nếu chỉ cần kiểm tra tồn tại không?

Chỉ bỏ `DISTINCT` khi đã chứng minh dữ liệu hoặc constraint bảo đảm không có hàng trùng trong phạm vi kết quả. Chỉ thêm `DISTINCT` khi yêu cầu nghiệp vụ thật sự là loại trùng.

## 7. Tổng hợp sau JOIN: tránh đếm hoặc cộng nhiều lần

Một phép nối một-nhiều có thể nhân bản các giá trị ở phía một. Nếu cộng doanh thu đơn hàng sau khi nối với bảng chi tiết, mỗi đơn hàng có nhiều dòng sẽ làm doanh thu đơn hàng bị cộng lặp.

Ví dụ:

```sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS revenue
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

Nếu một đơn hàng có 4 dòng chi tiết, `o.total_amount` được lặp 4 lần trong đầu vào của `SUM`. Kết quả có thể lớn hơn doanh thu thật.

Nếu cần doanh thu từ bảng `orders`, không cần nối `order_items`:

```sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

Nếu cần cả điều kiện liên quan đến chi tiết đơn hàng, có thể dùng `EXISTS` để lọc đơn hàng mà không nhân bản:

```sql
SELECT o.customer_id, SUM(o.total_amount) AS revenue
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM order_items AS i
    WHERE i.order_id = o.order_id
      AND i.product_id = :product_id
)
GROUP BY o.customer_id;
```

Hoặc tổng hợp bảng chi tiết trước khi nối, tùy mục tiêu và cardinality. Việc đẩy aggregate xuống trước join chỉ an toàn khi phép biến đổi giữ đúng quan hệ và số lần xuất hiện.

### 7.1. COUNT(*) và COUNT(column)

`COUNT(*)` đếm mọi hàng đầu vào. `COUNT(column)` chỉ đếm các giá trị không `NULL` của cột. Với `LEFT JOIN`, hai cách có thể khác nhau:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

Khách hàng không có đơn hàng vẫn tạo một hàng mở rộng bởi `LEFT JOIN`: `COUNT(*)` là 1, còn `COUNT(o.order_id)` là 0 nếu `order_id` không `NULL` khi có đơn hàng. Nếu join thêm `order_items`, số hàng có thể tăng theo số dòng chi tiết; khi đó `COUNT(o.order_id)` cũng có thể đếm lặp một đơn hàng nhiều lần.

`COUNT(DISTINCT o.order_id)` có thể đếm số đơn hàng phân biệt, nhưng phát sinh công việc loại trùng và chỉ đúng nếu định nghĩa nghiệp vụ là số đơn hàng duy nhất. Hãy xem xét pre-aggregation hoặc `EXISTS` để tránh tạo fan-out không cần thiết.

### 7.2. SUM(DISTINCT ...) không phải cách sửa fan-out tổng quát

`SUM(DISTINCT o.total_amount)` chỉ cộng một lần mỗi giá trị tổng tiền khác nhau. Hai đơn hàng độc lập có cùng `total_amount` sẽ bị gộp, dù cả hai đều phải được tính. Đây không phải cách sửa an toàn cho phép nối nhân hàng. Cần tổng hợp theo khóa thực thể trước khi nối hoặc loại bỏ phép nối không cần thiết.

## 8. Các phép viết lại phổ biến và điều kiện tương đương

| Phép viết lại | Có thể giữ tương đương khi | Rủi ro cần kiểm tra |
|---|---|---|
| `JOIN` thành `EXISTS` | Chỉ cần kiểm tra có hàng khớp và không cần cột phía nối | `JOIN` có thể trả nhiều hàng; `EXISTS` chỉ giữ một hàng trái |
| `NOT IN` thành `NOT EXISTS` | Nullability và chính sách khóa trái/phải được xác định phù hợp | `NULL` trong subquery hoặc vế trái làm kết quả khác |
| `LEFT JOIN ... IS NULL` thành `NOT EXISTS` | Điều kiện nối và cột nhận diện hàng khớp được chọn đúng | Dùng cột nullable hoặc đặt điều kiện sai vị trí |
| `UNION` thành `UNION ALL` | Nghiệp vụ cần giữ mọi lần xuất hiện hoặc đã chứng minh các nhánh không trùng | Có thể tạo thêm bản ghi trùng |
| Bỏ `DISTINCT` | Có constraint hoặc chứng minh dữ liệu bảo đảm duy nhất | Hàng trùng xuất hiện sau join hoặc projection |
| Đẩy điều kiện từ WHERE vào ON | Phù hợp với mục tiêu giữ hàng của outer join | Có thể thay đổi tập hàng được giữ |
| Tổng hợp trước JOIN | Khóa nhóm và quan hệ nối bảo toàn cardinality cần thiết | Aggregate trước có thể làm mất chi tiết hoặc nhân kết quả khác |
| Thay `OR` bằng `UNION ALL` | Hai nhánh được chứng minh không giao nhau hoặc có cơ chế khử trùng phù hợp | Một hàng thỏa cả hai nhánh có thể xuất hiện hai lần |

Không có phép viết lại nào được chứng minh chỉ bằng việc hai câu SQL trông giống nhau. Cần xác định constraint, nullability, tính duy nhất, cardinality và mục tiêu nghiệp vụ.

## 9. Thay OR bằng UNION hoặc UNION ALL

Đôi khi điều kiện `OR` làm kế hoạch khó tận dụng chỉ mục. Có thể thử tách thành các nhánh, nhưng phải kiểm tra phần giao nhau.

Truy vấn gốc:

```sql
SELECT ticket_id, owner_id
FROM tickets
WHERE priority = 'HIGH'
   OR owner_id = :owner_id;
```

Nếu thay bằng `UNION ALL`:

```sql
SELECT ticket_id, owner_id
FROM tickets
WHERE priority = 'HIGH'

UNION ALL

SELECT ticket_id, owner_id
FROM tickets
WHERE owner_id = :owner_id;
```

một ticket vừa có priority cao vừa thuộc owner đang xét sẽ xuất hiện hai lần, trong khi truy vấn gốc chỉ trả một hàng cho ticket đó. Dùng `UNION` có thể loại trùng nhưng thêm chi phí và có thể gộp các hàng giống nhau ở projection mà không nhất thiết cùng định danh nghiệp vụ.

Một cách giữ ngữ nghĩa đa tập của truy vấn gốc là làm cho hai nhánh không giao nhau:

```sql
SELECT ticket_id, owner_id
FROM tickets
WHERE priority = 'HIGH'

UNION ALL

SELECT ticket_id, owner_id
FROM tickets
WHERE owner_id = :owner_id
  AND (priority <> 'HIGH' OR priority IS NULL);
```

Điều kiện nhánh hai loại các hàng đã được chọn ở nhánh đầu, đồng thời giữ các hàng có `priority IS NULL` nếu chúng thỏa `owner_id`. Phép viết lại vẫn cần kiểm tra kiểu dữ liệu, biểu thức, collation và khả năng dùng chỉ mục. Có thể không nhanh hơn truy vấn `OR` ban đầu.

## 10. Kiểm chứng tương đương bằng dữ liệu có chủ đích

Không nên chỉ chạy hai truy vấn trên dữ liệu sản xuất hiện tại rồi so sánh tổng số hàng. Bộ dữ liệu kiểm thử cần có những trường hợp có thể làm lộ khác biệt ngữ nghĩa.

### 10.1. Ma trận trường hợp biên

| Trường hợp | Vì sao quan trọng | Ví dụ kiểm tra |
|---|---|---|
| Không có hàng khớp | Kiểm tra outer join, anti-join và tập rỗng | Khách hàng chưa có đơn hàng |
| Một hàng khớp | Trường hợp cơ bản | Một khách hàng có một đơn hàng |
| Nhiều hàng khớp | Phát hiện fan-out và duplicate | Một khách hàng có nhiều đơn hàng |
| Khóa trùng ở bảng phải | Kiểm tra giả định một-một | Hai bản ghi tham chiếu cùng mã |
| NULL ở vế trái | Phát hiện khác biệt NOT IN/NOT EXISTS | `customer_id IS NULL` |
| NULL ở vế phải | Phát hiện UNKNOWN trong NOT IN | Subquery chứa `NULL` |
| Tập con rỗng | Kiểm tra ngữ nghĩa `NOT IN` | Bảng bị chặn không có hàng |
| Hàng trùng hoàn toàn ở projection | Kiểm tra bag semantics | Hai đơn hàng khác ID nhưng cùng cột được chọn |
| Hàng thỏa nhiều nhánh OR | Phát hiện nhân bản khi tách UNION ALL | Ticket vừa high priority vừa thuộc owner |
| Nhóm không có giá trị tổng hợp | Kiểm tra COUNT/SUM/AVG và NULL | Nhóm không có chi tiết hoặc mọi giá trị đều NULL |
| Giá trị biên | Kiểm tra điều kiện khoảng và kiểu dữ liệu | Thời điểm đúng tại đầu/cuối khoảng |
| Dữ liệu thay đổi đồng thời | Tránh so sánh hai snapshot khác nhau | Hàng được thêm/xóa giữa hai lần chạy |

### 10.2. So sánh đa tập thay vì chỉ so sánh số hàng

Giả sử truy vấn cũ và truy vấn mới đều trả về hai cột `customer_id`, `status`. Cùng số hàng tổng cộng không chứng minh kết quả giống nhau: một hàng có thể bị mất và một hàng khác bị lặp thêm.

Một cách tổng quát là gom nhóm theo toàn bộ cột kết quả và đếm số lần xuất hiện của từng tổ hợp. Sau đó so sánh các bộ giá trị cùng multiplicity. Ví dụ theo PostgreSQL, dùng `IS NOT DISTINCT FROM` để so sánh null-safe:

```sql
WITH old_result AS (
    -- Truy vấn trước khi viết lại
    SELECT customer_id, status
    FROM ...
),
new_result AS (
    -- Truy vấn sau khi viết lại
    SELECT customer_id, status
    FROM ...
),
old_counts AS (
    SELECT customer_id, status, COUNT(*) AS copies
    FROM old_result
    GROUP BY customer_id, status
),
new_counts AS (
    SELECT customer_id, status, COUNT(*) AS copies
    FROM new_result
    GROUP BY customer_id, status
)
SELECT
    o.customer_id AS old_customer_id,
    n.customer_id AS new_customer_id,
    o.status AS old_status,
    n.status AS new_status,
    o.copies AS old_copies,
    n.copies AS new_copies
FROM old_counts AS o
FULL OUTER JOIN new_counts AS n
  ON o.customer_id IS NOT DISTINCT FROM n.customer_id
 AND o.status IS NOT DISTINCT FROM n.status
WHERE COALESCE(o.copies, 0) <> COALESCE(n.copies, 0);
```

Nếu truy vấn không trả về hàng nào, hai kết quả có cùng các tổ hợp giá trị và cùng số lần xuất hiện trong snapshot được so sánh. Thay `...` bằng truy vấn thực tế và bảo đảm hai nhánh có kiểu dữ liệu đầu ra tương thích.

Các hệ quản trị có cú pháp so sánh null-safe khác nhau:

- PostgreSQL và một số hệ quản trị hỗ trợ `IS NOT DISTINCT FROM`.
- MySQL hỗ trợ toán tử `<=>` cho null-safe equality.
- SQL Server có thể biểu diễn từng cột bằng `(a.col = b.col OR (a.col IS NULL AND b.col IS NULL))`.

Với nhiều cột kết quả, phải so sánh null-safe tất cả cột. Nếu kết quả chứa kiểu dữ liệu không thể `GROUP BY` hoặc so sánh trực tiếp, hãy dùng khóa ổn định/biểu diễn phù hợp hoặc kiểm tra theo từng phần có thể đối chiếu chính xác.

### 10.3. EXCEPT và INTERSECT không luôn kiểm tra được số lần xuất hiện

`EXCEPT`, `MINUS` hoặc `INTERSECT` thường thực hiện phép toán trên tập giá trị phân biệt, tức loại trùng theo ngữ nghĩa của sản phẩm. Chúng hữu ích để tìm giá trị chỉ có ở một phía nhưng có thể không phát hiện khác biệt multiplicity.

Ví dụ truy vấn cũ trả `A, A, B`, truy vấn mới trả `A, B, B`. Nếu chỉ dùng phép so sánh tập, cả hai đều có tập `{A, B}` và có thể bị xem như tương đương. So sánh số lần xuất hiện theo từng tổ hợp như phần trên sẽ phát hiện `A` giảm từ 2 xuống 1 và `B` tăng từ 1 lên 2.

Một số hệ quản trị hỗ trợ `EXCEPT ALL` hoặc phép toán bag tương ứng; khả năng hỗ trợ khác nhau. Hãy xác nhận phiên bản và ngữ nghĩa trước khi dùng. Không giả định `EXCEPT` thông thường bảo toàn số lần xuất hiện.

### 10.4. So sánh thứ tự khi thứ tự là một phần hợp đồng

Nếu API yêu cầu thứ tự cụ thể, trước tiên cả hai truy vấn phải có `ORDER BY` xác định, bao gồm khóa phụ duy nhất. Có thể gán `ROW_NUMBER()` theo cùng thứ tự rồi so sánh hàng ở từng vị trí. Không so sánh thứ tự của hai truy vấn không có `ORDER BY`, vì hệ quản trị không cam kết thứ tự đó.

## 11. Bảo đảm hai lần so sánh dùng cùng dữ liệu

Kết quả có thể khác chỉ vì dữ liệu thay đổi giữa lúc chạy truy vấn cũ và truy vấn mới. Để phép so sánh có ý nghĩa:

- Dùng cùng snapshot dữ liệu hoặc transaction isolation phù hợp để cả hai truy vấn nhìn thấy cùng một trạng thái.
- Giữ nguyên tham số, kiểu dữ liệu tham số, timezone, collation và session settings.
- Không chạy một truy vấn trước khi một tác vụ nền cập nhật dữ liệu rồi chạy truy vấn còn lại sau đó.
- Ghi lại thời điểm đo, phiên bản schema, constraint và thống kê liên quan.
- Với bảng lớn, có thể tạo bản sao/snapshot kiểm thử đại diện để lặp lại phép so sánh.

Isolation level và cú pháp transaction snapshot khác nhau giữa hệ quản trị. Snapshot quá dài có thể giữ phiên bản dữ liệu cũ, tăng áp lực lưu trữ hoặc ảnh hưởng vacuum/cleanup. Hãy chọn cách kiểm chứng phù hợp với nền tảng và thời lượng thử nghiệm.

## 12. Kiểm tra hiệu năng sau khi ngữ nghĩa đã được xác nhận

Sau khi chứng minh kết quả tương đương theo yêu cầu, mới so sánh hiệu năng. Thu thập cùng bộ chỉ số trước và sau:

| Nhóm | Chỉ số | Mục tiêu phân tích |
|---|---|---|
| Độ trễ | p50, p95, p99, elapsed time | Truy vấn có nhanh hơn ở các phân vị quan trọng không? |
| Thông lượng | requests/sec, transactions/sec | Hệ thống có xử lý được nhiều yêu cầu hơn không? |
| Cardinality | Estimated rows, actual rows, loops | Bộ tối ưu có ước lượng đúng và tránh fan-out không? |
| CPU | CPU time, số lần biên dịch | Phép viết lại có tăng công việc tính toán không? |
| I/O | Logical reads, physical reads, temp reads/writes | Có giảm lượng trang đọc hoặc sort/hash spill không? |
| Bộ nhớ | Memory grant, memory used, spill | Kế hoạch có gây áp lực bộ nhớ hoặc ghi tạm không? |
| Đồng thời | Lock waits, blocking, deadlocks | Có làm tăng thời gian giữ khóa hoặc tranh chấp không? |
| Tác động phụ | Chi phí ghi, dung lượng index, lỗi/timeout | Cải thiện truy vấn có gây hại workload khác không? |

Giữ dữ liệu, tham số, mức đồng thời, tốc độ tải, cache và thời lượng đo tương đương. Lặp lại đủ lần để phân biệt cải thiện thật với dao động tự nhiên. Không chỉ chạy một truy vấn đơn lẻ nếu vấn đề xuất hiện trong workload đồng thời.

### 12.1. Đọc kế hoạch để hiểu vì sao nhanh hơn hoặc chậm hơn

Sau khi viết lại, kiểm tra:

- Có thay đổi loại join, thứ tự join hoặc số hàng ở đầu vào không?
- Có loại bỏ được phép nối hoặc phép sort không cần thiết không?
- Có phát sinh `DISTINCT`, hash aggregate hoặc sort để loại trùng không?
- Số loops ở nhánh trong nested loop có tăng mạnh không?
- Có dùng chỉ mục mới hoặc điều kiện seek tốt hơn không?
- Estimated rows có gần actual rows không?
- Kế hoạch có spill hoặc chờ I/O/khóa không?

Một phép viết lại có thể làm câu SQL ngắn hơn nhưng kế hoạch xấu hơn. Ngược lại, một truy vấn có thêm CTE hoặc subquery vẫn có thể được optimizer inline và tạo kế hoạch hiệu quả. Không suy luận hiệu năng từ độ dài câu SQL.

## 13. Ví dụ tổng hợp: bỏ JOIN thừa nhưng giữ đúng số hàng

Yêu cầu: lấy danh sách khách hàng có ít nhất một đơn hàng đã thanh toán. Truy vấn ban đầu:

```sql
SELECT DISTINCT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

`JOIN` tạo một hàng cho mỗi đơn hàng đã thanh toán; `DISTINCT` sau đó gộp các hàng khách hàng giống nhau. Nếu chỉ cần kiểm tra sự tồn tại, có thể viết:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Hai truy vấn có thể trả cùng một hàng cho mỗi khách hàng nếu `customer_id` định danh duy nhất một khách hàng và projection giống nhau. Trước khi kết luận, kiểm tra:

1. `customers.customer_id` có unique/primary key không?
2. Truy vấn gốc có chủ ý loại hàng trùng theo đúng hai cột đang chọn không?
3. Có khách hàng với `customer_id IS NULL` không, và phép nối bằng xử lý các hàng đó thế nào?
4. `orders.customer_id` có thể `NULL` không? Hàng đó không khớp bằng thông thường.
5. Có hàng trùng trong `customers` theo projection hay không?
6. So sánh multiplicity của kết quả cũ và mới trên cùng snapshot.
7. Kiểm tra kế hoạch: phép nối và distinct có được thay bằng semi-join hay không?
8. Đo p95, CPU, logical reads và throughput với nhiều khách hàng có số đơn khác nhau.

Nếu `customers.customer_id` không duy nhất, truy vấn `EXISTS` vẫn giữ mỗi hàng vật lý bên trái một lần, trong khi `DISTINCT` của truy vấn gốc có thể gộp nhiều hàng khách hàng giống nhau ở hai cột được chọn. Khi đó hai truy vấn không tương đương. Constraint và projection quyết định kết quả.

## 14. Những sai lầm thường gặp khi kiểm chứng

- **Chỉ so sánh COUNT(*):** hai kết quả có thể cùng số hàng nhưng khác giá trị hoặc khác multiplicity.
- **Chỉ dùng EXCEPT:** phép toán tập hợp có thể bỏ qua khác biệt số lần xuất hiện.
- **Bỏ qua NULL:** `NOT IN`, `JOIN`, outer join và phép so sánh có thể thay đổi kết quả.
- **Thêm DISTINCT để che lỗi:** có thể loại các thực thể khác nhau hoặc tăng chi phí sort/hash.
- **Thay JOIN bằng EXISTS mà không xem projection:** `EXISTS` không cung cấp cột từ bảng bên phải và không nhân hàng.
- **Thay UNION ALL bằng UNION hoặc ngược lại:** làm thay đổi số lần xuất hiện.
- **Tổng hợp sau phép nối nhiều-nhiều:** có thể cộng/đếm lặp các thực thể phía trước.
- **Dùng SUM(DISTINCT value) để sửa fan-out:** có thể gộp hai thực thể độc lập có cùng giá trị.
- **Đặt điều kiện sai chỗ trong LEFT JOIN:** có thể loại hàng không khớp hoặc thay đổi outer join.
- **So sánh trên hai trạng thái dữ liệu khác nhau:** kết quả chênh lệch không phản ánh phép viết lại.
- **Chỉ thử dữ liệu sạch:** không phát hiện khóa trùng, NULL, tập rỗng hoặc phân bố lệch.
- **Đo hiệu năng trước khi xác nhận ngữ nghĩa:** có thể tối ưu một truy vấn đang trả sai kết quả.

## 15. Bài tập tự kiểm tra

### Bài tập 1: JOIN hay EXISTS?

Một khách hàng có 5 đơn hàng đã thanh toán. Truy vấn nối `customers` và `orders` chỉ chọn `customer_id`, `full_name`.

**Câu hỏi:** vì sao khách hàng có thể xuất hiện 5 lần? Nếu chỉ cần biết khách hàng có đơn hàng đã thanh toán, viết lại thế nào?

**Gợi ý trả lời:** mỗi hàng đơn hàng khớp tạo một hàng join. Dùng `WHERE EXISTS (...)` để kiểm tra có ít nhất một đơn hàng phù hợp mà không nhân bản hàng khách hàng. Cần xác nhận khóa khách hàng và projection của truy vấn gốc.

### Bài tập 2: NOT IN có NULL

Subquery trả về `4`, `7` và `NULL`. Truy vấn ngoài lọc `item_id NOT IN (subquery)`. Hàng có `item_id = 12` có được giữ không?

**Gợi ý trả lời:** không. So sánh với `NULL` làm kết quả tổng thể là `UNKNOWN`; `WHERE` chỉ giữ `TRUE`. Nếu nghiệp vụ là không có hàng khớp, cân nhắc `NOT EXISTS` và xác định riêng cách xử lý `item_id` bên trái `NULL`.

### Bài tập 3: UNION ALL tạo hàng trùng

Một ticket vừa thỏa `priority = 'HIGH'` vừa thỏa `owner_id = :owner_id`. Truy vấn `OR` trả ticket một lần, nhưng bản viết lại ghép hai nhánh bằng `UNION ALL` trả ticket hai lần.

**Câu hỏi:** sửa cách viết lại như thế nào để giữ bag semantics?

**Gợi ý trả lời:** làm hai nhánh không giao nhau, ví dụ nhánh thứ hai thêm điều kiện loại các hàng đã thỏa nhánh thứ nhất, đồng thời xử lý `NULL` đúng theo logic ba giá trị. Hoặc dùng `UNION` nếu nghiệp vụ thực sự yêu cầu loại trùng theo projection, nhưng phải tính chi phí và định nghĩa trùng.

### Bài tập 4: SUM bị nhân sau JOIN

Mỗi đơn hàng có 4 dòng chi tiết. Truy vấn nối `orders` với `order_items` rồi `SUM(orders.total_amount)`.

**Câu hỏi:** vì sao tổng tiền bị nhân và nên xử lý thế nào?

**Gợi ý trả lời:** mỗi đơn hàng được lặp theo số dòng chi tiết. Nếu chỉ cần doanh thu từ đơn hàng, bỏ join; nếu cần lọc theo chi tiết, dùng `EXISTS`; nếu cần cả hai tập thông tin, cân nhắc tổng hợp chi tiết theo khóa trước khi nối. Không dùng `SUM(DISTINCT total_amount)` vì hai đơn hàng khác nhau có thể có cùng tổng tiền.

### Bài tập 5: So sánh kết quả trước và sau

Hai truy vấn đều trả 1.000 hàng. Truy vấn cũ trả khóa `A` ba lần và khóa `B` một lần; truy vấn mới trả khóa `A` hai lần và khóa `B` hai lần.

**Câu hỏi:** so sánh số hàng tổng cộng có phát hiện sai khác không? Cần kiểm chứng thế nào?

**Gợi ý trả lời:** không. Cả hai có tổng 1.000 hàng nhưng multiplicity theo khóa khác nhau. Gom nhóm theo toàn bộ cột kết quả, đếm số lần xuất hiện và so sánh null-safe từng tổ hợp trên cùng snapshot.

### Checklist trước khi chấp nhận một phép viết lại SQL

- [ ] Đã xác định kết quả cần so sánh theo set, bag hay cả thứ tự.
- [ ] Đã kiểm tra khóa duy nhất, khóa ngoại và nullability của các cột nối.
- [ ] Đã xác định quan hệ một-một, một-nhiều hay nhiều-nhiều.
- [ ] Đã xem bản ghi trùng phát sinh từ JOIN, projection, UNION ALL hay nguồn dữ liệu.
- [ ] Đã kiểm tra NULL ở cả hai phía, tập con rỗng và logic UNKNOWN.
- [ ] Đã xác nhận điều kiện ON/WHERE của outer join.
- [ ] Đã xem tác động của DISTINCT, UNION, COUNT và SUM lên multiplicity.
- [ ] Đã kiểm thử các trường hợp không khớp, nhiều hàng khớp, khóa trùng và NULL.
- [ ] Đã so sánh từng tổ hợp giá trị cùng số lần xuất hiện, không chỉ tổng số hàng.
- [ ] Đã dùng cùng snapshot, tham số và session settings khi so sánh.
- [ ] Đã đọc execution plan và đo độ trễ, throughput, CPU, I/O, bộ nhớ sau khi xác nhận ngữ nghĩa.
- [ ] Đã ghi lại giả thuyết, kết quả, giới hạn và cách khôi phục.

Một phép viết lại SQL đúng phải giữ được ý nghĩa của dữ liệu, số lần xuất hiện và chính sách xử lý `NULL` mà nghiệp vụ yêu cầu. JOIN, EXISTS, NOT IN, NOT EXISTS, UNION, DISTINCT và aggregate có thể tạo ra kết quả khác nhau dù câu lệnh nhìn gần giống nhau. Hãy kiểm thử trường hợp biên, so sánh đa tập trên cùng snapshot, sau đó mới đánh giá execution plan và số liệu tải để chọn phương án có hiệu năng tốt mà vẫn bảo toàn kết quả.
