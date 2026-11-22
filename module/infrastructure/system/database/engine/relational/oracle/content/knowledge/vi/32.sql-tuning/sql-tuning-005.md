# Viết lại truy vấn JOIN/subquery theo đúng ngữ nghĩa

## 1. Mục tiêu của việc viết lại truy vấn

Trong Oracle Database, cùng một yêu cầu nghiệp vụ có thể được diễn đạt bằng `JOIN`, `EXISTS`, `IN`, `NOT EXISTS`, `NOT IN` hoặc subquery tương quan. Viết lại truy vấn có thể giúp câu SQL dễ đọc hơn, tạo cơ hội cho optimizer chọn một execution plan tốt hơn hoặc tránh một lỗi ước lượng/thiết kế cụ thể. Tuy nhiên, một phép viết lại chỉ đúng khi nó giữ nguyên **ngữ nghĩa của truy vấn**.

Ngữ nghĩa cần bảo toàn bao gồm:

- Tập dòng được trả về và số lần xuất hiện của mỗi dòng (duplicate rows).
- Cách xử lý `NULL` theo logic ba giá trị của SQL.
- Việc giữ hay loại các dòng không có bản ghi khớp ở bảng bên kia.
- Kết quả khi subquery trả về 0, 1 hoặc nhiều dòng.
- Thứ tự áp dụng điều kiện lọc, phép nhóm, phép tổng hợp và giới hạn số dòng.
- Giá trị trả về của biểu thức, kể cả trường hợp không có dòng phù hợp.

Một câu SQL ngắn hơn hoặc ít subquery hơn không mặc nhiên nhanh hơn. Oracle có thể tự chuyển một số subquery thành join, semi-join hoặc anti-join trong quá trình tối ưu hóa. Vì vậy, trước khi viết lại thủ công, cần hiểu plan hiện tại và xác định vấn đề thực sự nằm ở cardinality, access path, join method, số dòng trung gian hay cách diễn đạt truy vấn.

## 2. Phân biệt JOIN và subquery theo mục đích

### 2.1. JOIN để kết hợp dữ liệu

`JOIN` kết hợp các dòng của hai nguồn dữ liệu dựa trên điều kiện nối. Mỗi dòng bên trái có thể khớp với 0, 1 hoặc nhiều dòng bên phải.

```sql
SELECT c.customer_id,
       c.customer_name,
       o.order_id,
       o.order_date
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
```

Truy vấn trên trả về một dòng cho mỗi cặp khách hàng và đơn hàng khớp. Nếu một khách hàng có năm đơn hàng, thông tin khách hàng xuất hiện năm lần. Đây là hành vi đúng của quan hệ một-nhiều, không phải duplicate do Oracle tạo nhầm.

### 2.2. EXISTS để kiểm tra sự tồn tại

Nếu yêu cầu chỉ là tìm khách hàng có ít nhất một đơn hàng, ta không cần ghép từng đơn hàng vào kết quả. Dùng `EXISTS` thể hiện đúng ý định:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
);
```

`EXISTS` là phép kiểm tra có ít nhất một dòng thỏa điều kiện. Số dòng khớp bên trong subquery không nhân số dòng của truy vấn ngoài. Oracle có thể thực hiện truy vấn này bằng semi-join.

### 2.3. Scalar subquery để lấy một giá trị

Scalar subquery là subquery trả về một cột và tối đa một dòng trong ngữ cảnh thực thi:

```sql
SELECT c.customer_id,
       c.customer_name,
       (
         SELECT MAX(o.order_date)
         FROM orders o
         WHERE o.customer_id = c.customer_id
       ) AS last_order_date
FROM customers c;
```

Ở đây subquery tổng hợp trả về đúng một dòng cho mỗi khách hàng. Kết quả là ngày đặt hàng gần nhất; nếu khách hàng chưa có đơn hàng, `MAX` trả về `NULL`.

Scalar subquery không tổng hợp có quy tắc khác: không có dòng thì biểu thức trả về `NULL`; một dòng thì trả giá trị của dòng đó; nhiều hơn một dòng thì Oracle phát sinh lỗi `ORA-01427: single-row subquery returns more than one row`.

### 2.4. Chọn cấu trúc theo câu hỏi nghiệp vụ

| Yêu cầu | Cấu trúc thường phù hợp |
|---|---|
| Lấy dữ liệu từ cả hai bảng | `INNER JOIN` hoặc `OUTER JOIN` |
| Chỉ cần biết có dòng khớp | `EXISTS` |
| Chỉ cần biết không có dòng khớp | `NOT EXISTS` |
| So sánh một giá trị với tập giá trị | `IN` / `NOT IN`, sau khi hiểu rõ `NULL` |
| Lấy một giá trị từ truy vấn con | Scalar subquery |
| Tính tổng hợp theo từng khóa | Subquery `GROUP BY` kết hợp join hoặc scalar aggregate |

## 3. JOIN và EXISTS: tránh nhân dòng ngoài ý muốn

### 3.1. JOIN có thể tạo nhiều dòng cho một dòng cha

Giả sử một khách hàng có nhiều đơn hàng. Truy vấn sau trả về một dòng cho mỗi đơn hàng:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'SHIPPED';
```

Nếu một khách hàng có ba đơn hàng `SHIPPED`, khách hàng đó xuất hiện ba lần. Nếu yêu cầu nghiệp vụ là “mỗi khách hàng xuất hiện một lần nếu có đơn hàng đã giao”, cách viết trên không diễn đạt đúng mục tiêu về cardinality.

Có thể sửa bằng `EXISTS`:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'SHIPPED'
);
```

Hoặc dùng tập khóa duy nhất rồi join:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
JOIN (
  SELECT DISTINCT customer_id
  FROM orders
  WHERE status = 'SHIPPED'
) o
  ON o.customer_id = c.customer_id;
```

`EXISTS` thường diễn đạt mục đích kiểm tra sự tồn tại rõ hơn. Cách dùng `DISTINCT` có thể phù hợp khi cần tái sử dụng tập khóa, nhưng việc loại duplicate có chi phí và phải được đặt ở đúng cấp độ dữ liệu.

### 3.2. IN và EXISTS trong điều kiện lọc

Ví dụ:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id IN (
  SELECT o.customer_id
  FROM orders o
  WHERE o.status = 'SHIPPED'
);
```

Trong ngữ cảnh `WHERE`, có thể diễn đạt cùng điều kiện tồn tại bằng:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'SHIPPED'
);
```

Với phép so sánh một cột như trên, hai truy vấn giữ cùng các dòng ngoài được chọn: phải tồn tại ít nhất một giá trị bằng nhau. `IN` không nhân dòng ngoài khi subquery có duplicate; `EXISTS` cũng không nhân dòng ngoài. Nếu chuyển sang `JOIN` trực tiếp, cần chú ý duplicate ở nguồn bên trong.

Trong biểu thức SQL tổng quát, `IN` có thể cho kết quả `UNKNOWN` khi không có giá trị khớp nhưng tập bên trong chứa `NULL`; `EXISTS` với điều kiện bằng sẽ trả `FALSE` trong tình huống không có dòng khớp. Trong mệnh đề `WHERE`, cả `FALSE` và `UNKNOWN` đều bị loại nên tập dòng được chọn có thể giống nhau. Không được suy rộng sự tương đương đó sang mọi vị trí biểu thức như `NOT`, `CASE` hoặc phép tính logic phức tạp.

## 4. NOT EXISTS, NOT IN và NULL

Đây là một trong những điểm dễ gây lỗi nhất khi viết lại subquery.

### 4.1. NOT EXISTS

`NOT EXISTS` đúng khi subquery không trả về dòng nào:

```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
);
```

Truy vấn chọn khách hàng không có đơn hàng khớp. Nếu `c.customer_id` là `NULL`, phép so sánh `o.customer_id = c.customer_id` không thể là `TRUE`; do đó subquery không tìm thấy dòng và `NOT EXISTS` là `TRUE`. Nếu khóa ngoài được khai báo `NOT NULL`, tình huống này không phát sinh.

### 4.2. NOT IN có thể bị ảnh hưởng bởi NULL trong subquery

Xét:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
  SELECT o.customer_id
  FROM orders o
);
```

`NOT IN` có ngữ nghĩa tương đương `<> ALL` trên tập kết quả. Nếu subquery trả về ít nhất một `NULL`, phép so sánh với giá trị không khớp có thể trở thành `UNKNOWN`, vì SQL không thể xác định giá trị `NULL` có bằng hay khác giá trị ngoài hay không. Điều kiện `WHERE` chỉ giữ dòng có kết quả `TRUE`, nên truy vấn có thể không trả dòng nào như người viết mong đợi.

Ví dụ tập bên trong:

| Giá trị `CUSTOMER_ID` trong ORDERS | Ý nghĩa khi đánh giá `1001 NOT IN (...)` |
|---|---|
| `1001` | `FALSE` vì có giá trị khớp |
| `1002`, `1003` | `TRUE` nếu không có `NULL` |
| `1002`, `NULL` | `UNKNOWN` vì không thể xác định phép so sánh với `NULL` |
| Không có dòng nào | `TRUE`, kể cả khi giá trị ngoài là `NULL`, do tập rỗng |

Vì vậy, thay `NOT IN` bằng `NOT EXISTS` mà không phân tích nullability có thể thay đổi kết quả.

### 4.3. Khi nào có thể thay NOT IN bằng NOT EXISTS?

Nếu cả biểu thức bên ngoài và cột subquery đều được bảo đảm `NOT NULL`, hai dạng phổ biến sau tương đương về tập dòng được chọn:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
  SELECT o.customer_id
  FROM orders o
  WHERE o.status = 'SHIPPED'
);
```

```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.status = 'SHIPPED'
    AND o.customer_id = c.customer_id
);
```

Nếu các cột có thể `NULL`, cần quyết định chính sách nghiệp vụ. Nếu mục tiêu là “không tồn tại dòng có khóa bằng nhau”, `NOT EXISTS` thường thể hiện đúng ý định. Nếu cần giữ đúng ngữ nghĩa của `NOT IN`, phải xử lý cả tập rỗng, giá trị ngoài `NULL` và `NULL` trong tập trong; không nên thêm một điều kiện `IS NOT NULL` tùy tiện rồi tuyên bố tương đương.

Với hai biểu thức vô hướng `x` và `y` trong subquery, một cách mô tả chính xác điều kiện chọn của `x NOT IN (subquery)` trong `WHERE` là:

```sql
NOT EXISTS (SELECT 1 FROM source_y)
OR (
  x IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM source_y WHERE y = x)
  AND NOT EXISTS (SELECT 1 FROM source_y WHERE y IS NULL)
)
```

Trong đó `source_y` phải là đúng tập dòng và điều kiện lọc của subquery ban đầu. Nhánh đầu giữ trường hợp tập con rỗng; nhánh sau yêu cầu giá trị ngoài không null, không có giá trị bằng và không có null trong tập con. Đây là biểu thức giải thích ngữ nghĩa, thường không phải cách viết dễ bảo trì nhất. Khi có thể, hãy dùng ràng buộc `NOT NULL` rõ ràng hoặc chọn `NOT EXISTS` theo đúng yêu cầu nghiệp vụ.

### 4.4. Ma trận quyết định cho phép phủ định

| Tình huống | `NOT IN` | `NOT EXISTS` với phép bằng |
|---|---|---|
| Có dòng khớp | Loại dòng ngoài | Loại dòng ngoài |
| Không có dòng khớp, không có NULL trong tập con | Giữ nếu giá trị ngoài không NULL | Giữ |
| Tập con có NULL nhưng không có dòng khớp | Kết quả `UNKNOWN`, bị loại | Giữ |
| Giá trị ngoài là NULL, tập con không rỗng | `UNKNOWN`, bị loại | Giữ vì không có phép bằng nào là TRUE |
| Tập con rỗng | Giữ, kể cả giá trị ngoài NULL | Giữ |

Ma trận cho thấy vì sao cần kiểm tra constraint và dữ liệu thực tế trước khi đổi giữa hai cấu trúc.

## 5. INNER JOIN và OUTER JOIN: giữ đúng dòng không khớp

### 5.1. INNER JOIN chỉ giữ cặp dòng khớp

```sql
SELECT c.customer_id,
       o.order_id
FROM customers c
INNER JOIN orders o
  ON o.customer_id = c.customer_id;
```

Khách hàng không có đơn hàng sẽ không xuất hiện. Đây là hành vi khác với `LEFT JOIN`.

### 5.2. LEFT JOIN giữ tất cả dòng bên trái

```sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id;
```

Mọi khách hàng đều xuất hiện. Nếu không có đơn hàng phù hợp, các cột lấy từ `ORDERS` được trả về dưới dạng `NULL`. Nếu có nhiều đơn hàng, khách hàng vẫn xuất hiện nhiều dòng, mỗi dòng cho một đơn hàng.

### 5.3. Đặt điều kiện ở ON hay WHERE có thể đổi ngữ nghĩa

Xét yêu cầu “lấy tất cả khách hàng và các đơn hàng đang mở nếu có”:

```sql
SELECT c.customer_id,
       o.order_id,
       o.status
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.status = 'OPEN';
```

Điều kiện `o.status = 'OPEN'` nằm trong `ON`, nên nó giới hạn những dòng được coi là khớp. Khách hàng không có đơn hàng mở vẫn xuất hiện với các cột `o.*` là `NULL`.

Nếu chuyển điều kiện sang `WHERE`:

```sql
SELECT c.customer_id,
       o.order_id,
       o.status
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'OPEN';
```

Các dòng khách hàng không có đơn hàng bị loại vì `o.status` là `NULL` và điều kiện `NULL = 'OPEN'` là `UNKNOWN`. Truy vấn này có hiệu ứng giống inner join đối với predicate null-rejecting đó. Đây là thay đổi ngữ nghĩa, không chỉ là thay đổi cách trình bày.

### 5.4. Điều kiện trên bảng bên phải trong WHERE

Không phải mọi điều kiện trên bảng bên phải đều làm outer join thành inner join. Ví dụ:

```sql
WHERE o.status = 'OPEN' OR o.order_id IS NULL
```

Điều kiện này có thể giữ lại một số dòng không khớp. Do đó, hãy xét giá trị logic của predicate trên dòng được null-extend, thay vì áp dụng quy tắc máy móc “đưa điều kiện vào WHERE là inner join”.

### 5.5. Viết NOT EXISTS thành LEFT JOIN ... IS NULL

Một mẫu anti-join khác là:

```sql
SELECT c.customer_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

Mẫu này có thể tương đương với `NOT EXISTS` nếu `ORDER_ID` là cột được bảo đảm `NOT NULL` trên mọi dòng khớp, chẳng hạn primary key. Khi không có dòng khớp, Oracle tạo dòng null-extended nên `o.order_id IS NULL` đúng. Nếu dùng một cột bên phải có thể `NULL` trong dòng thật, truy vấn có thể nhầm dòng khớp có giá trị null với dòng không khớp. Vì vậy, hãy kiểm tra cột dùng làm dấu hiệu tồn tại.

## 6. Scalar subquery và JOIN

### 6.1. Scalar subquery không tổng hợp

Ví dụ:

```sql
SELECT c.customer_id,
       (
         SELECT o.order_date
         FROM orders o
         WHERE o.customer_id = c.customer_id
           AND o.is_primary = 'Y'
       ) AS primary_order_date
FROM customers c;
```

Truy vấn này giả định mỗi khách hàng có tối đa một đơn hàng `is_primary = 'Y'`. Nếu không có dòng, cột kết quả là `NULL`; nếu có nhiều hơn một dòng, Oracle báo `ORA-01427`.

Một phép `LEFT JOIN` tương ứng chỉ bảo toàn ngữ nghĩa nếu dữ liệu bảo đảm tối đa một dòng khớp:

```sql
SELECT c.customer_id,
       o.order_date AS primary_order_date
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.is_primary = 'Y';
```

Nếu có hai đơn hàng primary cho cùng một khách hàng, `LEFT JOIN` trả hai dòng trong khi scalar subquery báo lỗi. Không được coi hai truy vấn là tương đương chỉ vì trường hợp dữ liệu bình thường hiện tại có một dòng.

Có thể bảo đảm tính duy nhất bằng constraint phù hợp hoặc bằng logic nghiệp vụ rõ ràng. Nếu cần chọn một dòng trong nhiều dòng, phải xác định quy tắc chọn, chẳng hạn mới nhất theo thời gian và tie-break bằng khóa duy nhất:

```sql
SELECT c.customer_id,
       (
         SELECT o.order_date
         FROM orders o
         WHERE o.customer_id = c.customer_id
         ORDER BY o.order_date DESC, o.order_id DESC
         FETCH FIRST 1 ROW ONLY
       ) AS latest_order_date
FROM customers c;
```

Khi viết lại bằng analytic function hoặc inline view, cần giữ cùng quy tắc `ORDER BY` và tie-break. Chỉ dùng `MAX(order_date)` nếu mục tiêu thật sự là giá trị ngày lớn nhất; `MAX` không tự chọn toàn bộ dòng có ngày lớn nhất.

### 6.2. Scalar aggregate và GROUP BY

Subquery aggregate không có `GROUP BY` thường trả đúng một dòng, kể cả khi không có dòng đầu vào:

```sql
SELECT c.customer_id,
       (
         SELECT COUNT(*)
         FROM orders o
         WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers c;
```

Nếu khách hàng chưa có đơn hàng, `COUNT(*)` trả `0`. Có thể viết lại bằng bảng tổng hợp:

```sql
SELECT c.customer_id,
       NVL(o.order_count, 0) AS order_count
FROM customers c
LEFT JOIN (
  SELECT customer_id,
         COUNT(*) AS order_count
  FROM orders
  GROUP BY customer_id
) o
  ON o.customer_id = c.customer_id;
```

`NVL` cần thiết vì inline view `GROUP BY` không tạo nhóm cho khách hàng không có đơn hàng; outer join trả `NULL` cho `order_count`. Scalar `COUNT(*)` ban đầu trả `0`, nên bỏ `NVL` sẽ đổi kết quả.

Với `SUM`, `AVG`, `MIN` hoặc `MAX`, scalar aggregate trên tập rỗng thường trả `NULL`. Khi viết lại bằng outer join với bảng aggregate, giá trị không có nhóm cũng là `NULL`, thường bảo toàn kết quả. Tuy vậy, cần kiểm tra `COUNT(expr)`, biểu thức có `NVL`/`COALESCE` và điều kiện lọc để không đổi hành vi.

### 6.3. Điều kiện tương quan phải được giữ đầy đủ

Khi chuyển correlated subquery thành inline view hoặc join, phải giữ mọi cột tham gia tương quan. Nếu subquery ban đầu lọc theo `customer_id` và `status`, việc chỉ join theo `customer_id` có thể trộn kết quả của các trạng thái khác nhau.

Ngoài ra, điều kiện có thể nằm trong `ON`, trong phần `WHERE` của inline view hoặc ở truy vấn ngoài. Chuyển vị trí điều kiện có thể đổi kết quả khi có outer join, aggregate hoặc null extension.

## 7. Correlated subquery và unnesting

### 7.1. Correlated subquery

Correlated subquery tham chiếu cột từ truy vấn bên ngoài:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'OPEN'
);
```

Subquery có tham chiếu `c.customer_id`. Về mặt logic, điều kiện tồn tại được đánh giá cho từng dòng khách hàng; về mặt thực thi, Oracle có thể biến đổi truy vấn để tránh chạy một phép tra cứu độc lập theo cách ngây thơ cho từng dòng.

### 7.2. Subquery unnesting

Subquery unnesting là phép biến đổi optimizer đưa subquery vào cấu trúc join của truy vấn ngoài khi điều kiện cho phép. Ví dụ `EXISTS` có thể được chuyển thành semi-join; `NOT EXISTS` có thể được chuyển thành anti-join. Optimizer khi đó có nhiều cơ hội lựa chọn join order, join method và access path.

Vì Oracle đã có khả năng biến đổi nhiều dạng subquery, việc đổi mọi `EXISTS` thành `JOIN` bằng tay thường không tạo lợi ích. Một truy vấn viết rõ ý định nghiệp vụ thường giúp cả người đọc lẫn optimizer hiểu đúng quan hệ cần thực hiện.

Không phải mọi subquery đều có thể unnest. Các yếu tố như aggregate, `GROUP BY`, `DISTINCT`, set operator, row limiting, outer join và biểu thức phức tạp có thể giới hạn hoặc thay đổi điều kiện biến đổi. Hãy xem execution plan thực tế thay vì giả định optimizer chắc chắn đã unnest hoặc chắc chắn chạy subquery lặp lại.

### 7.3. Semi-join và anti-join

Hai dạng join logic thường gặp:

- **Semi-join:** chỉ trả dòng từ phía ngoài nếu có ít nhất một dòng khớp ở phía trong. `EXISTS` và `IN` thường có thể được thực hiện theo cách này.
- **Anti-join:** chỉ trả dòng từ phía ngoài nếu không có dòng khớp ở phía trong. `NOT EXISTS` thường có thể được thực hiện theo cách này.

Trong execution plan Oracle, có thể gặp operation như `HASH JOIN SEMI`, `NESTED LOOPS SEMI`, `HASH JOIN ANTI` hoặc biến thể tương ứng. Tên operation phản ánh chiến lược thực thi, không làm thay đổi ngữ nghĩa SQL mà truy vấn yêu cầu.

## 8. Những lỗi ngữ nghĩa thường gặp khi viết lại

### 8.1. Bỏ mất điều kiện join

```sql
-- Đúng: có điều kiện kết nối
SELECT c.customer_id, o.order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
```

Nếu quên `ON` hoặc viết thiếu một phần của khóa ghép, kết quả có thể thành Cartesian product hoặc ghép sai dòng. Với khóa gồm nhiều cột, phải giữ đầy đủ các thành phần:

```sql
ON d.company_id = e.company_id
AND d.department_id = e.department_id
```

Chỉ nối theo `department_id` có thể ghép nhân viên của công ty này với phòng ban cùng mã ở công ty khác.

### 8.2. Dùng DISTINCT để che duplicate

`DISTINCT` loại các dòng trùng nhau trên toàn bộ danh sách cột được chọn. Nó có thể che lỗi nhân dòng do join thiếu điều kiện, nhưng cũng có thể loại các dòng hợp lệ có giá trị hiển thị giống nhau. Thay vì thêm `DISTINCT` ngay lập tức, hãy xác định quan hệ khóa và cardinality mong muốn.

Nếu yêu cầu chỉ là “có ít nhất một dòng con”, dùng `EXISTS` thường chính xác hơn. Nếu cần tổng hợp dữ liệu con, dùng `GROUP BY` theo khóa phù hợp. Nếu thực sự cần loại duplicate theo nghiệp vụ, xác định rõ tập cột và quy tắc chọn.

### 8.3. Đưa predicate qua ranh giới aggregate

Ví dụ:

```sql
SELECT customer_id, SUM(amount) AS total_amount
FROM orders
WHERE status = 'SHIPPED'
GROUP BY customer_id;
```

Điều kiện `status` lọc dòng trước khi tính tổng. Nếu viết lại bằng cách tổng hợp tất cả trạng thái rồi lọc sau, tổng số tiền sẽ khác. Với điều kiện trên kết quả aggregate, cần dùng `HAVING` hoặc predicate ở truy vấn ngoài theo đúng mục tiêu.

### 8.4. Thay đổi thứ tự xử lý TOP-N

`ORDER BY` kết hợp `FETCH FIRST` hoặc `ROWNUM` tạo giới hạn trên một tập dòng theo thứ tự nhất định. Đưa điều kiện lọc vào trước hay sau phép giới hạn có thể làm thay đổi tập kết quả. Ví dụ “10 đơn hàng mới nhất đã giao” khác với “10 đơn hàng mới nhất rồi chỉ giữ những đơn đã giao”.

Khi viết lại truy vấn top-N, phải giữ đúng thứ tự logic giữa lọc, sắp xếp và giới hạn dòng; thêm tie-break duy nhất nếu nghiệp vụ cần kết quả ổn định khi nhiều dòng có cùng giá trị sắp xếp.

### 8.5. Chuyển điều kiện NULL thành phép bằng

`x = NULL` không bao giờ là điều kiện đúng; phải dùng `x IS NULL`. Tương tự, `x <> NULL` phải là `x IS NOT NULL`. Khi chuyển predicate giữa JOIN, EXISTS và NOT EXISTS, hãy nhớ phép so sánh bằng với `NULL` trả `UNKNOWN`, không phải `TRUE`.

### 8.6. Dùng UNION thay cho UNION ALL

`UNION` loại duplicate giữa các nhánh, còn `UNION ALL` giữ tất cả dòng. Nếu viết lại một điều kiện `OR` thành hai nhánh `UNION ALL`, một dòng thỏa cả hai nhánh sẽ xuất hiện hai lần. Nếu dùng `UNION`, duplicate có thể bị loại ngoài ý muốn. Cần chứng minh hai nhánh rời nhau hoặc có quy tắc loại duplicate đúng với nghiệp vụ.

## 9. Phương pháp viết lại an toàn

### Bước 1: Xác định kết quả mong muốn

Trước khi sửa SQL, diễn đạt bằng ngôn ngữ nghiệp vụ:

- Một dòng kết quả đại diện cho khách hàng, đơn hàng hay cặp khách hàng-đơn hàng?
- Có phải giữ khách hàng không có đơn hàng không?
- Chỉ cần biết có bản ghi con hay cần hiển thị dữ liệu con?
- Nếu có nhiều bản ghi con thì lấy tất cả, đếm, tổng hợp hay chọn một bản ghi theo thứ tự?
- Giá trị `NULL` có ý nghĩa gì trong nghiệp vụ?

### Bước 2: Xác định cardinality và constraint

Kiểm tra primary key, unique constraint, foreign key và `NOT NULL`. Một phép rewrite từ scalar subquery sang join có thể dựa vào tính duy nhất; một rewrite từ `NOT IN` sang `NOT EXISTS` có thể dựa vào nullability. Những giả định này nên được bảo đảm bằng constraint hoặc bằng dữ liệu/logic có thể chứng minh.

### Bước 3: Viết lại đúng cấu trúc logic

- Dùng `JOIN` khi cần kết hợp cột từ nhiều nguồn.
- Dùng `EXISTS` khi cần kiểm tra ít nhất một dòng phù hợp.
- Dùng `NOT EXISTS` khi cần kiểm tra không có dòng khớp.
- Giữ `NOT IN` nếu cần ngữ nghĩa của `<> ALL`, hoặc chỉ thay bằng `NOT EXISTS` sau khi xử lý `NULL` đúng.
- Với scalar subquery, bảo toàn quy tắc 0/1/nhiều dòng và giá trị aggregate khi tập rỗng.
- Với outer join, kiểm tra kỹ vị trí của predicate trong `ON` và `WHERE`.

### Bước 4: So sánh kết quả, kể cả duplicate

Không nên chỉ so sánh bằng `MINUS` trên kết quả thô vì `MINUS` loại duplicate. Để kiểm tra bag semantics, có thể nhóm theo toàn bộ cột kết quả và so sánh số lần xuất hiện của từng tổ hợp giá trị.

Ví dụ khung kiểm tra giữa truy vấn cũ và truy vấn mới:

```sql
WITH old_q AS (
  -- Truy vấn trước khi viết lại
  SELECT customer_id, order_id
  FROM ...
),
new_q AS (
  -- Truy vấn sau khi viết lại
  SELECT customer_id, order_id
  FROM ...
),
old_counts AS (
  SELECT customer_id, order_id, COUNT(*) AS row_count
  FROM old_q
  GROUP BY customer_id, order_id
),
new_counts AS (
  SELECT customer_id, order_id, COUNT(*) AS row_count
  FROM new_q
  GROUP BY customer_id, order_id
)
SELECT 'OLD_MINUS_NEW' AS difference_type,
       customer_id, order_id, row_count
FROM (
  SELECT customer_id, order_id, row_count FROM old_counts
  MINUS
  SELECT customer_id, order_id, row_count FROM new_counts
)
UNION ALL
SELECT 'NEW_MINUS_OLD' AS difference_type,
       customer_id, order_id, row_count
FROM (
  SELECT customer_id, order_id, row_count FROM new_counts
  MINUS
  SELECT customer_id, order_id, row_count FROM old_counts
);
```

Nếu kết quả rỗng, hai truy vấn có cùng tổ hợp giá trị và số lần xuất hiện đối với các cột được so sánh. Khi kết quả có kiểu dữ liệu không hỗ trợ `GROUP BY` hoặc `MINUS` trực tiếp (ví dụ một số kiểu LOB), cần chọn khóa định danh phù hợp hoặc phương pháp so sánh khác. Cũng cần kiểm tra các cột kết quả, kiểu dữ liệu và alias để tránh so sánh thiếu thành phần.

Với truy vấn có side effect qua hàm không thuần, sequence, nondeterministic function hoặc dữ liệu thay đổi trong lúc kiểm tra, không nên chạy hai phiên bản độc lập rồi coi khác biệt là do rewrite. Hãy so sánh trên cùng snapshot dữ liệu hoặc trong môi trường kiểm thử có dữ liệu ổn định.

### Bước 5: So sánh execution plan và runtime

Sau khi xác nhận kết quả tương đương, mới đánh giá hiệu năng. Có thể thu thập runtime statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'SHIPPED'
);
```

Sau đó xem cursor:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +PREDICATE +ALIAS'
  )
);
```

So sánh `E-Rows` với `A-Rows`, `Starts`, `Buffers`, `Reads` và thời gian thực thi. Kiểm tra operation như `HASH JOIN`, `NESTED LOOPS`, `HASH JOIN SEMI` hoặc `HASH JOIN ANTI`, nhưng không chọn plan chỉ vì tên operation có vẻ tốt hơn. Hãy đo trên workload đại diện, với bind values và dữ liệu tương đương.

### Bước 6: Chấp nhận rewrite khi có bằng chứng

Giữ phiên bản mới khi:

- Kết quả và duplicate semantics đã được kiểm chứng.
- Các trường hợp `NULL`, không có dòng khớp và nhiều dòng khớp đã được xét.
- Execution plan hoặc runtime cho thấy cải thiện có thể giải thích được.
- Câu SQL vẫn dễ hiểu và có thể bảo trì.

Nếu plan không đổi và runtime không cải thiện, không cần rewrite chỉ để thay đổi hình thức. Nếu kết quả khác, quay lại xác định chính xác giả định ngữ nghĩa nào đã thay đổi trước khi tiếp tục tuning.

## 10. Ví dụ tổng hợp: tìm khách hàng có và không có đơn hàng

Giả sử `CUSTOMERS.CUSTOMER_ID` là primary key và `ORDERS.CUSTOMER_ID` có thể `NULL`.

### Tìm khách hàng có đơn hàng đã giao

Diễn đạt bằng `EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'SHIPPED'
);
```

Đây là lựa chọn rõ ràng nếu chỉ cần danh sách khách hàng. Chuyển thành join trực tiếp có thể nhân khách hàng khi có nhiều đơn hàng đã giao.

### Tìm khách hàng không có đơn hàng

Diễn đạt bằng `NOT EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
);
```

Không nên viết `NOT IN (SELECT customer_id FROM orders)` nếu `ORDERS.CUSTOMER_ID` có thể chứa `NULL`, vì một giá trị null trong subquery có thể làm điều kiện `NOT IN` trở thành `UNKNOWN` cho các khách hàng không khớp. `NOT EXISTS` diễn đạt trực tiếp việc không có dòng đơn hàng liên kết.

### Lấy số đơn hàng của mỗi khách hàng

Scalar aggregate:

```sql
SELECT c.customer_id,
       (
         SELECT COUNT(*)
         FROM orders o
         WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers c;
```

Hoặc aggregate rồi outer join:

```sql
SELECT c.customer_id,
       NVL(o.order_count, 0) AS order_count
FROM customers c
LEFT JOIN (
  SELECT customer_id, COUNT(*) AS order_count
  FROM orders
  GROUP BY customer_id
) o
  ON o.customer_id = c.customer_id;
```

Hai cách trên bảo toàn kết quả `0` cho khách hàng không có đơn hàng. Nếu bỏ `NVL`, kết quả từ outer join sẽ là `NULL`, khác với `COUNT(*)` trong scalar subquery.

## 11. Những nguyên tắc cần ghi nhớ

1. `JOIN` kết hợp dòng; `EXISTS` kiểm tra sự tồn tại. Hai cấu trúc không tự động thay thế nhau vì join có thể nhân dòng.
2. `IN` không nhân dòng ngoài dù tập bên trong có duplicate; chuyển sang join phải xử lý cardinality.
3. `NOT IN` nhạy với `NULL`; `NOT EXISTS` thường an toàn hơn cho yêu cầu anti-match nhưng không phải luôn tương đương với `NOT IN`.
4. `LEFT JOIN` giữ dòng bên trái; predicate trên bảng phải ở `WHERE` có thể loại các dòng null-extended. Vị trí `ON`/`WHERE` là một phần của ngữ nghĩa.
5. Scalar subquery trả `NULL` khi không có dòng và lỗi khi có nhiều hơn một dòng; join không tự có cùng hành vi.
6. Aggregate cần giữ đúng kết quả trên tập rỗng, đặc biệt `COUNT(*)` trả `0` trong khi outer join đến nhóm không tồn tại thường cho `NULL`.
7. Oracle có thể tự unnest subquery thành semi-join/anti-join. Không nên rewrite thủ công nếu chưa xác định vấn đề hiệu năng.
8. So sánh kết quả phải tính đến duplicate, `NULL`, kiểu dữ liệu, giới hạn dòng và thứ tự nghiệp vụ; sau đó mới so sánh execution plan và runtime.

Viết lại JOIN/subquery tốt là diễn đạt chính xác yêu cầu dữ liệu, giữ nguyên hành vi ở mọi trường hợp biên và tạo điều kiện để Oracle tối ưu hóa. Bảo toàn ngữ nghĩa là điều kiện tiên quyết; hiệu năng phải được xác nhận bằng execution plan và số liệu thực tế.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html)
- [Oracle Database 19c SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html)
- [Oracle Database 19c SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html)
- [Oracle Database 19c SQL Tuning Guide — Query Transformations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html)
