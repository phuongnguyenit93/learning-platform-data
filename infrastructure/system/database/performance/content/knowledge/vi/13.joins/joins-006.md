# EXISTS, NOT EXISTS và phép nối bán phần theo nhu cầu kiểm tra tồn tại

Nhiều truy vấn cần trả lời một câu hỏi đơn giản: một khách hàng có đơn hàng hay chưa, một sản phẩm có thuộc danh mục đang hoạt động hay không, hoặc một tài khoản có giao dịch bị đánh dấu rủi ro không. Trong các trường hợp này, truy vấn chỉ cần biết có ít nhất một hàng thỏa điều kiện. Nó không cần lấy toàn bộ cột của bảng liên quan và cũng không cần nhân bản hàng kết quả theo số lượng bản ghi khớp.

SQL cung cấp `EXISTS` để kiểm tra sự tồn tại và `NOT EXISTS` để kiểm tra sự vắng mặt. Bộ tối ưu thường có thể chuyển các điều kiện này thành **semi-join** hoặc **anti-semi-join**, là các phép nối chỉ quan tâm có khớp hay không. Chọn đúng dạng truy vấn giúp thể hiện rõ ý định, tránh hàng trùng không cần thiết và tạo cơ hội cho bộ tối ưu chọn kế hoạch phù hợp.

Trong module **DATABASE_PERFORMANCE**, cần biết khi nào dùng `EXISTS`, khi nào dùng `NOT EXISTS`, cách viết truy vấn tương quan, cách xử lý `NULL`, và cách thiết kế chỉ mục cho phép kiểm tra tồn tại. Hiệu quả cuối cùng phải được xác nhận bằng execution plan, số hàng đọc và tải thực tế; bản thân cú pháp không bảo đảm một kế hoạch vật lý cụ thể.

## 1. EXISTS: kiểm tra có ít nhất một hàng phù hợp

`EXISTS` trả về giá trị đúng nếu truy vấn con tạo ra ít nhất một hàng. Nội dung các cột trong danh sách `SELECT` của truy vấn con không được dùng để tạo kết quả bên ngoài; điều quan trọng là có hàng nào thỏa điều kiện hay không.

Ví dụ, tìm khách hàng có ít nhất một đơn hàng:

```sql
SELECT c.customer_id, c.full_name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Truy vấn bên ngoài duyệt các khách hàng. Với mỗi khách hàng về mặt logic, truy vấn con kiểm tra xem có đơn hàng nào có cùng `customer_id` hay không. Khách hàng có một đơn hàng hay một nghìn đơn hàng vẫn chỉ xuất hiện một lần trong kết quả, miễn là hàng khách hàng đó chỉ xuất hiện một lần ở đầu vào bên ngoài.

`SELECT 1` là quy ước dễ đọc vì cho thấy truy vấn con chỉ kiểm tra sự tồn tại. Có thể viết `SELECT *` hoặc chọn một cột khác; kết quả boolean của `EXISTS` không phụ thuộc giá trị được chọn.

### EXISTS không tạo hàng trùng từ bảng con

Giả sử khách hàng 10 có ba đơn hàng. Với truy vấn `EXISTS`, khách hàng 10 được trả về một lần. Truy vấn chỉ hỏi “có ít nhất một đơn hàng không?”. Nó không đưa từng hàng đơn hàng vào tập kết quả.

Đây là khác biệt quan trọng với `INNER JOIN`:

```sql
-- Có thể trả về một hàng khách hàng cho mỗi đơn hàng khớp.
SELECT c.customer_id, c.full_name
FROM customer AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;

-- Chỉ trả về mỗi hàng khách hàng một lần theo tập kết quả bên ngoài.
SELECT c.customer_id, c.full_name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Nếu mục tiêu là lấy dữ liệu từ cả hai bảng, `JOIN` thường là cách biểu đạt phù hợp. Nếu mục tiêu chỉ là lọc bảng bên ngoài theo việc có bản ghi liên quan, `EXISTS` thể hiện ý định chính xác hơn và không cần `DISTINCT` chỉ để loại hàng lặp do quan hệ một-nhiều.

## 2. Semi-join là gì?

Semi-join là phép nối trả về hàng từ một phía khi tồn tại ít nhất một hàng khớp ở phía còn lại. Trong truy vấn SQL thông thường, `EXISTS` là một cách biểu đạt phổ biến để yêu cầu phép nối bán phần.

Với hai tập dữ liệu `Customer` và `Orders`, điều kiện:

```sql
WHERE EXISTS (
    SELECT 1
    FROM Orders o
    WHERE o.customer_id = c.customer_id
)
```

chỉ trả về cột của `Customer`. Dữ liệu `Orders` được dùng để xác định có khớp hay không, không được ghép vào kết quả.

<escape>Minh họa quan hệ:</escape>

```text
Customer                  Orders
+-------------+           +------------------+
| customer_id |           | customer_id      |
+-------------+           +------------------+
| 10          |---------->| 10                |
| 20          |----+       | 10                |
| 30          |    |       | 20                |
+-------------+    |       +------------------+
                   |
EXISTS trả về:     |
+-------------+   |
| customer_id |
+-------------+
| 10          |   Có ít nhất một đơn hàng
| 20          |   Có ít nhất một đơn hàng
+-------------+
```

Trong kế hoạch thực thi, hệ quản trị có thể dùng nested loops semi-join, hash semi-join, merge semi-join hoặc một chiến lược tương đương. Tên và dạng toán tử hiển thị phụ thuộc hệ quản trị. Không nên giả định rằng `EXISTS` luôn chạy truy vấn con một lần cho từng hàng bên ngoài; bộ tối ưu có thể biến đổi hoặc giải tương quan truy vấn để tạo kế hoạch join khác.

## 3. Truy vấn tương quan và truy vấn không tương quan

### Truy vấn con tương quan

Truy vấn con tương quan (*correlated subquery*) tham chiếu đến cột của truy vấn bên ngoài:

```sql
SELECT c.customer_id, c.full_name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Điều kiện `o.customer_id = c.customer_id` liên kết truy vấn con với hàng khách hàng hiện tại. Về mặt logic, kết quả kiểm tra phụ thuộc khách hàng đang xét. Tuy nhiên, bộ tối ưu có thể chuyển truy vấn này thành semi-join và chọn thứ tự truy cập thích hợp thay vì thực hiện một lần tìm kiếm độc lập theo cách tuần tự cho từng hàng.

### Truy vấn con không tương quan

Truy vấn con không tham chiếu đến hàng bên ngoài:

```sql
SELECT c.customer_id, c.full_name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM system_feature
    WHERE feature_name = 'ORDER_MODULE'
      AND enabled = TRUE
);
```

Điều kiện này kiểm tra xem tính năng có đang bật hay không. Nếu truy vấn con có ít nhất một hàng, mọi hàng khách hàng đi qua các điều kiện còn lại đều thỏa điều kiện `EXISTS`; nếu không có hàng, không hàng khách hàng nào được trả về từ điều kiện này. Hệ quản trị có thể đánh giá truy vấn con một lần hoặc xử lý theo chiến lược khác phù hợp.

### Không nhầm tương quan logic với số lần thực thi vật lý

Từ “correlated” mô tả quan hệ tham chiếu giữa hai cấp truy vấn, không khẳng định truy vấn con chắc chắn được chạy lại từ đầu cho từng hàng. Bộ tối ưu có thể decorrelate, đẩy điều kiện, tạo hash table hoặc chọn nested loops tùy thống kê và chi phí. Khi phân tích hiệu năng, hãy đọc actual execution plan và số lần thực thi thực tế của từng toán tử.

## 4. NOT EXISTS: kiểm tra không có hàng phù hợp

`NOT EXISTS` đúng khi truy vấn con không trả về hàng nào. Ví dụ, tìm khách hàng chưa từng có đơn hàng:

```sql
SELECT c.customer_id, c.full_name
FROM customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Đây là một dạng **anti-semi-join**: trả về hàng ở phía ngoài khi không có hàng tương ứng ở phía trong. Bảng `orders` chỉ tham gia kiểm tra sự vắng mặt; các cột của nó không xuất hiện trong kết quả.

Một ví dụ khác là tìm sản phẩm chưa có dòng hàng tồn kho tại kho được chỉ định:

```sql
SELECT p.product_id, p.product_name
FROM product AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM warehouse_stock AS s
    WHERE s.product_id = p.product_id
      AND s.warehouse_id = ?
);
```

Truy vấn này hữu ích cho báo cáo dữ liệu thiếu, kiểm tra đồng bộ hoặc tìm các đối tượng chưa có quan hệ liên quan. Nếu mục tiêu là tìm các hàng chưa khớp, `NOT EXISTS` thường diễn đạt trực tiếp ý định hơn việc nối rồi lọc một cột null.

## 5. EXISTS, JOIN và DISTINCT: chọn theo kết quả cần có

Ba cách viết có thể cho kết quả giống nhau trong một số trường hợp, nhưng không có cùng ngữ nghĩa trong mọi trường hợp.

| Cách viết | Kết quả chính | Hành vi khi phía liên quan có nhiều hàng khớp |
|---|---|---|
| `EXISTS` | Hàng từ phía ngoài nếu có ít nhất một hàng phù hợp | Không nhân bản hàng ngoài do số lượng hàng khớp |
| `INNER JOIN` | Các tổ hợp hàng thỏa điều kiện nối | Một hàng ngoài có thể xuất hiện nhiều lần |
| `JOIN` kết hợp `DISTINCT` | Các hàng khác nhau theo danh sách cột được chọn | Có thể phải loại trùng bằng sort hoặc hash; việc loại trùng có thể làm thay đổi ngữ nghĩa nếu chọn thêm cột |

Ví dụ, nếu chỉ cần danh sách khách hàng có đơn hàng, cách sau thường không cần thiết:

```sql
SELECT DISTINCT c.customer_id, c.full_name
FROM customer AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
```

Cách biểu đạt trực tiếp hơn là:

```sql
SELECT c.customer_id, c.full_name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

`DISTINCT` có thể yêu cầu sort hoặc hash aggregate, tiêu thụ CPU và bộ nhớ, thậm chí spill ra đĩa khi tập dữ liệu lớn. Bộ tối ưu đôi khi có thể đơn giản hóa truy vấn join-distinct, nhưng không nên dựa vào điều đó để che giấu ý định chưa rõ. Hãy chọn dạng truy vấn đúng với cardinality mong muốn.

Nếu cần số lượng đơn hàng hoặc tổng doanh thu, `EXISTS` không đủ vì nó chỉ trả lời có/không. Khi đó dùng `JOIN` với `GROUP BY`, truy vấn tổng hợp hoặc một cấu trúc phù hợp với mục tiêu.

## 6. NOT EXISTS và bẫy NULL của NOT IN

Một lỗi thường gặp là thay `NOT EXISTS` bằng `NOT IN` mà không kiểm tra `NULL` trong tập con.

Ví dụ:

```sql
SELECT c.customer_id
FROM customer AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

Nếu truy vấn con trả về ít nhất một `NULL`, phép so sánh `x NOT IN (subquery)` có thể cho kết quả `UNKNOWN` với các giá trị không khớp. Trong mệnh đề `WHERE`, `UNKNOWN` không được xem là đúng, nên truy vấn có thể không trả về hàng nào dù có khách hàng chưa đặt đơn.

`NOT EXISTS` thường tránh được bẫy này vì điều kiện tương quan được đánh giá theo từng hàng và `NULL` ở một hàng bên trong không tự động làm toàn bộ điều kiện phủ định trở thành `UNKNOWN`:

```sql
SELECT c.customer_id
FROM customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Tuy vậy, cần hiểu cách so sánh `NULL` trong điều kiện tương quan. Với `o.customer_id = c.customer_id`, nếu một trong hai giá trị là `NULL`, phép so sánh không đúng; hàng đó không tạo ra kết quả khớp. Nếu nghiệp vụ muốn coi hai `NULL` là tương đương, phải viết điều kiện null-safe phù hợp với hệ quản trị.

### Khi nào NOT IN vẫn dùng được?

`NOT IN` có thể phù hợp nếu biểu thức ở cả phía ngoài và tập kết quả con được bảo đảm `NOT NULL`, hoặc nếu truy vấn con lọc rõ `IS NOT NULL` và ngữ nghĩa phía ngoài đã được xác định. Ví dụ:

```sql
SELECT c.customer_id
FROM customer AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT o.customer_id
      FROM orders AS o
      WHERE o.customer_id IS NOT NULL
  );
```

Ngay cả khi đó, hãy chọn cú pháp dễ đọc và kiểm tra kế hoạch. Không nên thêm `IS NOT NULL` máy móc nếu điều đó làm thay đổi kết quả nghiệp vụ mong muốn.

## 7. LEFT JOIN ... IS NULL và NOT EXISTS

Một cách khác để tìm hàng không có quan hệ là `LEFT JOIN` rồi lọc hàng không khớp:

```sql
SELECT c.customer_id, c.full_name
FROM customer AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

Truy vấn này có thể tương đương với `NOT EXISTS` nếu `o.order_id` là cột không null ở mọi hàng thực tế được nối, chẳng hạn khóa chính. Nếu chọn một cột có thể null trong dữ liệu, `o.column IS NULL` không phân biệt được hàng không khớp với hàng có khớp nhưng giá trị cột thực sự là null.

Một lỗi tinh vi khác là đặt điều kiện của bảng bên phải vào `WHERE` thay vì `ON`:

```sql
-- Có thể làm mất ý nghĩa LEFT JOIN vì điều kiện WHERE loại hàng null-extended.
SELECT c.customer_id
FROM customer AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.order_id IS NULL;
```

Nếu muốn kiểm tra không có đơn hàng đã thanh toán, điều kiện cần nằm trong phép nối:

```sql
SELECT c.customer_id
FROM customer AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
WHERE o.order_id IS NULL;
```

Hoặc biểu đạt trực tiếp bằng `NOT EXISTS`:

```sql
SELECT c.customer_id
FROM customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

`NOT EXISTS` thường dễ đọc hơn vì điều kiện liên quan nằm gọn trong truy vấn con. `LEFT JOIN ... IS NULL` vẫn hữu ích khi truy vấn cần thêm dữ liệu từ bảng ngoài hoặc khi nhóm phát triển đã có quy ước rõ ràng.

## 8. Thiết kế chỉ mục cho EXISTS và NOT EXISTS

Hiệu năng của phép kiểm tra tồn tại phụ thuộc lớn vào khả năng tìm nhanh hàng khớp ở bảng bên trong. Hãy lập chỉ mục trên các cột được dùng để liên kết và lọc.

Với truy vấn:

```sql
SELECT c.customer_id
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Một chỉ mục ứng viên có thể là:

```sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
```

Nếu hệ quản trị duyệt khách hàng rồi tìm đơn hàng theo `customer_id` và `status`, chỉ mục ghép này có thể hỗ trợ phép tìm kiếm. Thứ tự cột nên dựa trên các truy vấn khác trong workload, độ chọn lọc và kế hoạch dự kiến. Nếu truy vấn thường lọc theo trạng thái trước rồi mới nhóm khách hàng, thứ tự khác có thể phù hợp hơn.

Với anti-semi-join:

```sql
SELECT p.product_id
FROM product AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM warehouse_stock AS s
    WHERE s.product_id = p.product_id
      AND s.warehouse_id = ?
);
```

chỉ mục `(product_id, warehouse_id)` hoặc `(warehouse_id, product_id)` có thể là ứng viên tùy hướng truy cập và các truy vấn liên quan. Nếu `warehouse_id` cố định và có độ chọn lọc cao, thứ tự khóa có thể ảnh hưởng lớn đến chi phí. Hãy kiểm tra estimated rows, actual rows và số trang đọc thay vì chọn thứ tự chỉ theo cảm tính.

### Chỉ mục phủ và cột cần đọc

Vì `EXISTS` chỉ cần xác định có hàng khớp, hệ quản trị có thể chỉ cần đọc các cột khóa trong index. Không cần đưa mọi cột của bảng bên trong vào chỉ mục nếu truy vấn con không dùng chúng. Cột bổ sung có thể làm index lớn hơn và tăng chi phí ghi mà không cải thiện phép kiểm tra.

Một số hệ quản trị có thể dừng tìm kiếm sau khi phát hiện một hàng khớp trong một chiến lược nested loops; nhưng kế hoạch hash hoặc merge semi-join có thể phải xử lý nhiều dữ liệu hơn để xây dựng hoặc duyệt cấu trúc. Không nên giả định mọi `EXISTS` đều đọc đúng một hàng vật lý. Mục tiêu là giúp bộ tối ưu chọn được đường truy cập có chi phí thấp.

### Partial hoặc filtered index

Nếu chỉ cần kiểm tra một nhóm trạng thái nhỏ, partial/filtered index có thể giảm kích thước chỉ mục trên nền tảng hỗ trợ:

```sql
-- Ví dụ PostgreSQL
CREATE INDEX ix_orders_paid_customer
ON orders (customer_id)
WHERE status = 'PAID';
```

Điều kiện truy vấn phải tương thích với predicate của chỉ mục để bộ tối ưu có thể sử dụng. Khả năng nhận diện phụ thuộc hệ quản trị, tham số hóa và dạng điều kiện. SQL Server có filtered index với cú pháp riêng; không nên giả định mọi hệ quản trị đều hỗ trợ partial index tương tự.

## 9. Các chiến lược semi-join và anti-semi-join trong execution plan

Bộ tối ưu có thể chọn nhiều chiến lược tùy số hàng, thống kê, chỉ mục và độ chọn lọc:

| Chiến lược | Cách hoạt động khái quát | Trường hợp có thể phù hợp |
|---|---|---|
| Nested loops semi-join | Với mỗi hàng ngoài, tìm hàng khớp ở trong; khi biết có khớp có thể không cần tìm thêm | Tập ngoài nhỏ, có index seek tốt ở phía trong |
| Hash semi-join | Xây cấu trúc hash từ một phía rồi kiểm tra hàng phía còn lại | Tập dữ liệu lớn, cần xử lý nhiều hàng và có bộ nhớ phù hợp |
| Merge semi-join | Duyệt hai đầu vào đã được sắp xếp theo khóa nối | Hai đầu vào có thứ tự phù hợp hoặc chi phí sort chấp nhận được |
| Anti-semi-join | Trả hàng ngoài không tìm thấy khóa khớp ở phía trong | Tìm bản ghi thiếu quan hệ hoặc chưa có sự kiện |

Tên toán tử hiển thị khác nhau theo hệ quản trị. Một số hệ thống thể hiện rõ `Left Semi Join`, `Left Anti Semi Join`, `Hash Match`, `Nested Loops` hoặc biến thể tương đương; hệ thống khác có thể biểu diễn bằng filter, subquery hoặc toán tử join nội bộ.

### Khi nào nested loops trở nên đắt?

Nếu tập ngoài có hàng triệu hàng và mỗi hàng dẫn đến một lần tìm kiếm phía trong, dù có index, số lần truy cập ngẫu nhiên vẫn có thể cao. Hash semi-join có thể hiệu quả hơn nếu dữ liệu lớn và bộ nhớ đủ. Ngược lại, hash join cần xây bảng băm và có thể spill ra đĩa khi memory grant thiếu.

### Khi nào scan có thể hợp lý?

Nếu phần lớn hàng bên trong đều cần kiểm tra hoặc bảng nhỏ, scan tuần tự có thể rẻ hơn hàng triệu lần index lookup. Vì vậy, “có index” không có nghĩa hệ quản trị luôn nên dùng index. Hãy đọc actual plan, số lần lặp, logical reads, CPU, memory grant và wait.

## 10. EXISTS trong các bài toán nghiệp vụ

### Khách hàng có đơn hàng thanh toán

```sql
SELECT c.customer_id, c.full_name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.payment_status = 'PAID'
);
```

Chỉ cần biết đã có ít nhất một đơn hàng thanh toán. Nếu cần tổng số đơn hoặc tổng tiền, hãy dùng phép tổng hợp.

### Sản phẩm có ít nhất một dòng hàng còn tồn

```sql
SELECT p.product_id, p.product_name
FROM product AS p
WHERE EXISTS (
    SELECT 1
    FROM warehouse_stock AS s
    WHERE s.product_id = p.product_id
      AND s.quantity > 0
);
```

Điều kiện `quantity > 0` là một phần của định nghĩa tồn tại. Nếu có nhiều kho, một sản phẩm vẫn chỉ xuất hiện một lần trong kết quả.

### Tài khoản chưa có giao dịch trong kỳ

```sql
SELECT a.account_id
FROM account AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM account_transaction AS t
    WHERE t.account_id = a.account_id
      AND t.created_at >= ?
      AND t.created_at < ?
);
```

Điều kiện thời gian dùng khoảng nửa mở `[start, end)` giúp tránh nhập nhằng ở ranh giới và có thể tận dụng index phù hợp. Một chỉ mục ứng viên là `(account_id, created_at)` hoặc thứ tự khác tùy cách truy cập và workload.

### Kiểm tra bản ghi liên quan còn hiệu lực

```sql
SELECT u.user_id, u.username
FROM app_user AS u
WHERE EXISTS (
    SELECT 1
    FROM user_role AS ur
    JOIN role AS r
      ON r.role_id = ur.role_id
    WHERE ur.user_id = u.user_id
      AND r.role_name = 'ADMIN'
      AND ur.revoked_at IS NULL
);
```

Truy vấn chỉ trả về người dùng có ít nhất một vai trò quản trị còn hiệu lực. Các bảng trung gian có thể cần index trên `user_role(user_id, role_id)` và `role(role_name)` hoặc thiết kế tương đương theo cardinality và kế hoạch thực tế.

## 11. EXISTS không thay thế ràng buộc toàn vẹn hoặc xử lý đồng thời

Một truy vấn `NOT EXISTS` có thể kiểm tra trước khi tạo bản ghi:

```sql
INSERT INTO customer_account (email)
SELECT ?
WHERE NOT EXISTS (
    SELECT 1
    FROM customer_account
    WHERE email = ?
);
```

Cách viết này có thể hữu ích trong một số thao tác, nhưng không tự bảo đảm tính duy nhất khi nhiều transaction chạy đồng thời. Hai transaction vẫn có thể cùng quan sát không có hàng phù hợp trước khi ghi. Nếu quy tắc nghiệp vụ yêu cầu duy nhất, hãy dùng `UNIQUE` constraint hoặc unique index làm lớp bảo vệ cuối cùng và xử lý lỗi xung đột ở ứng dụng.

Tương tự, `EXISTS` trong một transaction chỉ phản ánh dữ liệu nhìn thấy theo isolation level và snapshot của transaction đó. Một hàng có thể được thêm hoặc xóa bởi transaction khác sau thời điểm kiểm tra. Nếu logic cần khóa hoặc bảo đảm nhất quán xuyên nhiều thao tác, phải chọn transaction isolation, khóa hoặc constraint phù hợp với hệ quản trị.

## 12. EXISTS và phân trang, lọc theo quan hệ

Khi truy vấn danh sách cha kèm điều kiện có ít nhất một bản ghi con, `EXISTS` giúp lọc trước khi phân trang:

```sql
SELECT c.customer_id, c.full_name
FROM customer AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'OPEN'
)
ORDER BY c.customer_id
FETCH FIRST 50 ROWS ONLY;
```

Cú pháp giới hạn hàng khác nhau theo hệ quản trị; `FETCH FIRST` là cú pháp được nhiều nền tảng hỗ trợ, nhưng cần điều chỉnh khi chuyển hệ. Nên có thứ tự sắp xếp ổn định để phân trang nhất quán. Nếu dùng offset lớn, chi phí bỏ qua hàng có thể tăng; keyset pagination có thể phù hợp hơn.

Khi dùng `EXISTS` trong truy vấn phân trang, cần kiểm tra kế hoạch xem hệ quản trị có thể đẩy điều kiện và giới hạn hàng hiệu quả hay không. Index trên khóa sắp xếp của bảng ngoài và index trên cột liên kết ở bảng trong thường quan trọng.

## 13. Chẩn đoán và tối ưu theo hệ quản trị

Ngữ nghĩa `EXISTS` và `NOT EXISTS` là SQL chuẩn, nhưng kế hoạch và công cụ quan sát khác nhau:

| Hệ quản trị | Công cụ kiểm tra | Điều cần xem |
|---|---|---|
| PostgreSQL | `EXPLAIN (ANALYZE, BUFFERS)` | Semi/anti join, actual rows, loops, shared hit/read và thời gian |
| SQL Server | Actual Execution Plan, `SET STATISTICS IO, TIME ON` | Logical reads, số lần thực thi, semi/anti semi join, CPU và elapsed time |
| MySQL | `EXPLAIN`, `EXPLAIN ANALYZE` ở phiên bản hỗ trợ | Subquery transformation, semijoin strategy, access type và actual rows |
| Oracle Database | `DBMS_XPLAN.DISPLAY_CURSOR` với thống kê thực thi | SEMI/ANTI join, starts, actual rows, buffers và thời gian |

Một số hệ quản trị có các chiến lược biến đổi subquery thành semi-join như materialization, duplicate weedout, first match hoặc loose scan tùy loại truy vấn và phiên bản. Đây là lựa chọn nội bộ của bộ tối ưu; không nên cố ép một chiến lược nếu chưa đo được lợi ích.

### Quy trình điều tra

1. Xác định truy vấn chỉ cần kiểm tra tồn tại hay thật sự cần lấy dữ liệu từ cả hai bảng.
2. Ghi nhận số hàng đầu vào và số hàng thực tế khớp ở bảng liên quan.
3. Kiểm tra điều kiện tương quan, bộ lọc, `NULL` và kiểu dữ liệu của khóa nối.
4. Kiểm tra chỉ mục ở phía trong theo các cột nối và lọc.
5. Đọc actual execution plan để nhận diện semi-join, anti-join, nested loops, hash, merge hoặc scan.
6. So sánh estimated rows với actual rows; cập nhật thống kê nếu có sai lệch đáng kể.
7. Đo logical/physical reads, CPU, elapsed time, memory grant, spill và wait.
8. Thử một thay đổi có phạm vi rõ, chẳng hạn index ghép hoặc viết lại `JOIN DISTINCT` thành `EXISTS`.
9. Chạy lại với dữ liệu, cache và mức đồng thời đại diện.
10. Kiểm tra workload liên quan để bảo đảm cải thiện không làm truy vấn khác hoặc thao tác ghi suy giảm đáng kể.

## 14. Những sai lầm thường gặp

1. **Dùng JOIN khi chỉ cần kiểm tra tồn tại:** hàng bên ngoài có thể bị nhân bản theo số hàng khớp.
2. **Thêm DISTINCT để chữa hàng trùng không cần thiết:** có thể tạo sort/hash tốn CPU và bộ nhớ.
3. **Cho rằng EXISTS luôn chạy một lần cho mỗi hàng ngoài:** bộ tối ưu có thể decorrelate và chọn chiến lược semi-join khác.
4. **Cho rằng EXISTS luôn dừng sau một lần đọc vật lý:** điều đó phụ thuộc kế hoạch; hash hoặc merge có thể xử lý nhiều dữ liệu hơn.
5. **Dùng NOT IN khi tập con có thể chứa NULL:** kết quả có thể thành UNKNOWN và loại bỏ các hàng mong muốn.
6. **Dùng LEFT JOIN ... IS NULL trên cột nullable:** có thể nhầm hàng khớp có giá trị null với hàng không khớp.
7. **Đặt điều kiện bảng phải vào WHERE sau LEFT JOIN:** có thể vô tình biến phép nối ngoài thành hành vi tương tự inner join.
8. **Thiếu index trên khóa tương quan:** kiểm tra tồn tại có thể đọc quá nhiều hàng ở bảng bên trong.
9. **Tạo index quá rộng:** tăng dung lượng và chi phí ghi dù truy vấn chỉ cần kiểm tra một khóa.
10. **Dùng NOT EXISTS để thay unique constraint:** kiểm tra tồn tại không ngăn được race condition giữa các transaction.
11. **Chỉ nhìn estimated plan:** cần đo actual rows, loops, I/O và thời gian dưới tải thực.

## 15. Danh sách kiểm tra trước khi tối ưu

- [ ] Đã xác định truy vấn cần lấy dữ liệu liên quan hay chỉ kiểm tra có/không.
- [ ] Đã dùng `EXISTS` cho điều kiện có ít nhất một hàng và `NOT EXISTS` cho điều kiện không có hàng.
- [ ] Đã kiểm tra hàng ngoài có bị nhân bản khi dùng `JOIN` hay không.
- [ ] Đã xem xét `NULL` trước khi dùng `NOT IN` hoặc `LEFT JOIN ... IS NULL`.
- [ ] Đã xác minh điều kiện tương quan và kiểu dữ liệu của khóa nối.
- [ ] Đã thiết kế index trên cột liên kết và bộ lọc quan trọng của bảng bên trong.
- [ ] Đã kiểm tra actual execution plan và chiến lược semi/anti join.
- [ ] Đã so sánh estimated rows, actual rows, loops, logical reads và CPU.
- [ ] Đã đo p95/p99 và throughput với dữ liệu, cache và tải đại diện.
- [ ] Đã dùng constraint hoặc transaction phù hợp nếu yêu cầu là bảo đảm toàn vẹn khi ghi đồng thời.

`EXISTS` và `NOT EXISTS` diễn đạt trực tiếp việc có hoặc không có hàng liên quan. Chúng phù hợp với semi-join và anti-semi-join, giúp tránh nhân bản hàng ngoài khi bảng liên quan có nhiều bản ghi khớp. Để đạt hiệu năng tốt, hãy kiểm tra ngữ nghĩa `NULL`, thiết kế chỉ mục theo khóa tương quan và bộ lọc, rồi xác nhận chiến lược thực thi bằng số liệu thực tế. Khi quy tắc tồn tại là điều kiện toàn vẹn dữ liệu, hãy bảo vệ nó bằng constraint hoặc cơ chế transaction thích hợp thay vì chỉ dựa vào một lần kiểm tra `EXISTS`.
