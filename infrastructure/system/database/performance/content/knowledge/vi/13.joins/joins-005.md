# INNER JOIN, OUTER JOIN và ràng buộc ngữ nghĩa khi viết lại

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt kết quả của INNER JOIN, LEFT/RIGHT OUTER JOIN và FULL OUTER JOIN, kể cả khi có nhiều hàng khớp hoặc không có hàng khớp.
- Giải thích cách SQL xử lý NULL và vì sao vị trí đặt điều kiện trong ON hay WHERE có thể làm thay đổi kết quả.
- Nhận biết những phép viết lại JOIN có thể bảo toàn ngữ nghĩa và những phép viết lại làm mất hàng hoặc nhân bản dữ liệu.
- Dùng EXISTS, NOT EXISTS và phép tổng hợp trước JOIN khi chúng diễn đạt đúng ý định nghiệp vụ.
- Đánh giá ảnh hưởng của kiểu JOIN, ràng buộc dữ liệu, chỉ mục và ước lượng cardinality lên kế hoạch thực thi.

## 1. JOIN kết hợp hàng theo điều kiện

JOIN kết hợp hàng từ hai nguồn dữ liệu dựa trên một điều kiện. Trong cơ sở dữ liệu quan hệ, kết quả thường tuân theo ngữ nghĩa bag (multiset): nếu một hàng ở bảng trái khớp với nhiều hàng ở bảng phải, hàng trái xuất hiện nhiều lần trong kết quả. JOIN không tự động loại bỏ bản ghi trùng.

Giả sử có hai bảng:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
```

Một khách hàng có thể có nhiều đơn hàng. Truy vấn kết hợp tên khách hàng với từng đơn:

```sql
SELECT c.customer_id, c.customer_name, o.order_id, o.total_amount
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Kết quả có một hàng cho mỗi cặp khách hàng/đơn hàng khớp. Khách hàng chưa có đơn không xuất hiện. Đây là đặc điểm cốt lõi của INNER JOIN.

Trong module DATABASE_PERFORMANCE, hiểu đúng ngữ nghĩa JOIN là điều kiện tiên quyết trước khi tối ưu SQL hoặc thay đổi kế hoạch. Một phép viết lại có thể giảm số lần đọc nhưng vẫn sai nếu nó làm mất hàng, thêm hàng hoặc thay đổi số lần xuất hiện của một hàng.

## 2. INNER JOIN

INNER JOIN chỉ trả về các cặp hàng thỏa mãn điều kiện nối. Nếu không có cặp nào khớp, hàng không xuất hiện trong kết quả.

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Nếu một khách hàng có ba đơn hàng, khách hàng đó xuất hiện ba lần. Nếu một khách hàng không có đơn hàng, khách hàng đó không xuất hiện.

### Điều kiện nối và điều kiện lọc

Điều kiện trong ON xác định hai hàng có khớp nhau hay không. Với INNER JOIN, một điều kiện lọc có thể thường được chuyển giữa ON và WHERE mà vẫn giữ cùng kết quả:

```sql
-- Cách 1
SELECT c.customer_id, o.order_id
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';

-- Cách 2
SELECT c.customer_id, o.order_id
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Trong ví dụ này, cả hai truy vấn đều chỉ trả về cặp khách hàng/đơn hàng đã thanh toán. Bộ tối ưu thường có thể đẩy điều kiện `status = 'PAID'` xuống gần bảng `orders` để giảm số hàng trước khi nối.

Đối với INNER JOIN, việc đẩy điều kiện lọc thường linh hoạt hơn OUTER JOIN. Tuy vậy, cần giữ nguyên biểu thức, kiểu dữ liệu và các quy tắc NULL; không nên suy luận rằng mọi biểu thức đều có thể di chuyển tùy ý.

## 3. LEFT OUTER JOIN

LEFT OUTER JOIN giữ lại tất cả hàng ở nguồn bên trái. Nếu một hàng bên trái không tìm được hàng phù hợp bên phải, kết quả vẫn chứa hàng bên trái và các cột bên phải được điền NULL. Quá trình này gọi là null extension.

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Truy vấn trả về:

- Một hàng cho mỗi đơn hàng khớp với khách hàng.
- Một hàng với `o.order_id IS NULL` cho khách hàng không có đơn.

LEFT JOIN thường dùng khi cần danh sách đầy đủ đối tượng chính cùng dữ liệu tùy chọn, chẳng hạn tất cả khách hàng kể cả khách chưa phát sinh đơn hàng.

### Điều kiện ON có thể giới hạn hàng khớp mà vẫn giữ hàng bên trái

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

Truy vấn giữ mọi khách hàng nhưng chỉ ghép các đơn đã thanh toán. Khách chỉ có đơn chưa thanh toán vẫn xuất hiện một lần với các cột đơn hàng là NULL, vì không có hàng nào thỏa toàn bộ điều kiện ON.

### Điều kiện WHERE có thể loại hàng được null-extend

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Ở đây, hàng không có đơn sẽ có `o.status = NULL`. Biểu thức `NULL = 'PAID'` cho kết quả UNKNOWN, không phải TRUE; WHERE chỉ giữ hàng có điều kiện TRUE. Do đó các hàng không có đơn bị loại và truy vấn có kết quả tương đương INNER JOIN đối với điều kiện này.

Đây là lỗi phổ biến khi chuyển điều kiện từ ON sang WHERE trong LEFT JOIN. Hai vị trí không tương đương vì WHERE chạy trên kết quả đã được null-extend.

## 4. RIGHT OUTER JOIN và FULL OUTER JOIN

### RIGHT OUTER JOIN

RIGHT JOIN giữ lại tất cả hàng ở nguồn bên phải, kể cả khi không có hàng trái khớp. Các cột bên trái được điền NULL khi không có hàng tương ứng.

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
RIGHT JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Với khóa ngoại được thực thi đúng, mọi đơn hàng thường phải có khách hàng tương ứng nên ví dụ này không tạo hàng phải không khớp. Nhưng RIGHT JOIN vẫn có thể hữu ích khi nguồn phải là tập cần giữ đầy đủ hoặc khi dữ liệu chưa được ràng buộc.

RIGHT JOIN có thể được viết lại thành LEFT JOIN bằng cách đổi thứ tự hai nguồn và điều chỉnh thứ tự cột. Việc đổi nguồn phải bảo toàn điều kiện nối và thứ tự cột đầu ra nếu ứng dụng phụ thuộc vào cấu trúc kết quả.

### FULL OUTER JOIN

FULL OUTER JOIN giữ tất cả hàng từ cả hai phía:

- Các hàng khớp được kết hợp.
- Hàng chỉ có bên trái vẫn xuất hiện với cột bên phải là NULL.
- Hàng chỉ có bên phải vẫn xuất hiện với cột bên trái là NULL.

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
FULL OUTER JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

FULL JOIN hữu ích cho đối soát hai tập dữ liệu, phát hiện bản ghi chỉ tồn tại ở một phía hoặc so sánh dữ liệu đồng bộ. Không thể thay FULL JOIN bằng LEFT JOIN đơn thuần nếu cần giữ cả hàng chỉ có bên phải.

## 5. ON và WHERE: khác biệt ngữ nghĩa khi có NULL

SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. So sánh thông thường với NULL thường tạo UNKNOWN. WHERE chỉ giữ hàng có kết quả TRUE; FALSE và UNKNOWN đều bị loại.

Bảng dưới đây minh họa:

| Biểu thức | Kết quả khi cột là NULL | Hàng được WHERE giữ? |
| --- | --- | --- |
| `x = 10` | UNKNOWN | Không |
| `x <> 10` | UNKNOWN | Không |
| `x > 10` | UNKNOWN | Không |
| `x IS NULL` | TRUE | Có |
| `x IS NOT NULL` | FALSE | Không |
| `COALESCE(x, 0) = 0` | TRUE | Có |

Xét khách hàng có thể chưa có đơn:

```sql
-- Giữ mọi khách hàng, ghép đơn đã thanh toán nếu có
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';

-- Chỉ giữ hàng có đơn đã thanh toán
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Truy vấn đầu giữ khách hàng không có đơn đã thanh toán; truy vấn sau loại họ. Đặt điều kiện vào ON có nghĩa là điều kiện quyết định hàng phải nào được ghép. Đặt vào WHERE có nghĩa là điều kiện quyết định hàng kết quả nào được giữ sau khi JOIN.

### Trường hợp WHERE kiểm tra IS NULL

```sql
SELECT c.customer_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

Vì `order_id` là khóa chính không NULL, truy vấn này tìm khách hàng không có đơn hàng. Nếu dùng một cột nullable như `o.note IS NULL`, kết quả có thể bao gồm cả các đơn có note NULL và không còn là phép anti join chính xác.

Để diễn đạt ý định không tồn tại hàng con rõ ràng, thường nên dùng NOT EXISTS:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

NOT EXISTS không cần tạo hàng null-extended rồi lọc lại; bộ tối ưu có thể triển khai thành anti join. Chỉ mục trên `orders(customer_id)` có thể hỗ trợ tìm nhanh hàng con.

## 6. Null-rejecting predicate và chuyển OUTER JOIN thành INNER JOIN

Một predicate là null-rejecting đối với một phía của OUTER JOIN nếu nó không thể cho kết quả TRUE khi các cột của phía đó được thay bằng NULL.

Ví dụ `o.status = 'PAID'` là null-rejecting với phía orders: khi `o.status` là NULL, điều kiện không TRUE. Vì vậy:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

có thể được viết lại tương đương về ngữ nghĩa thành:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Việc chuyển đổi này có thể giúp bộ tối ưu có thêm tự do sắp xếp JOIN, chọn thứ tự nối hoặc đẩy điều kiện lọc. Nhiều hệ quản trị tự nhận diện và thực hiện phép outer-join reduction này.

Không phải mọi điều kiện WHERE đều null-rejecting. Ví dụ `o.status IS NULL` là TRUE khi status NULL, nên không thể chuyển LEFT JOIN thành INNER JOIN theo quy tắc trên. `COALESCE(o.status, 'UNKNOWN') = 'UNKNOWN'` cũng có thể giữ hàng được null-extend.

Trước khi viết lại, hãy thử với ba trường hợp: bên phải có hàng khớp, bên phải không có hàng khớp, và bên phải có hàng khớp nhưng giá trị cột lọc là NULL. Nếu có nhiều hàng khớp, cũng cần xác nhận số lần xuất hiện trong kết quả.

## 7. Viết lại JOIN bằng EXISTS và NOT EXISTS

JOIN thường dùng để trả dữ liệu từ cả hai bảng. Nếu chỉ cần biết có ít nhất một hàng liên quan, EXISTS diễn đạt ý định tốt hơn và tránh nhân bản hàng bên trái.

### Dùng EXISTS để kiểm tra sự tồn tại

Truy vấn sau trả khách hàng có ít nhất một đơn đã thanh toán:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Nếu viết bằng INNER JOIN:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

khách hàng có nhiều đơn đã thanh toán sẽ xuất hiện nhiều lần. Thêm DISTINCT có thể loại trùng nhưng phải trả thêm chi phí sort hoặc hash và có thể che giấu việc truy vấn đang tạo ra nhiều hàng trung gian. EXISTS phù hợp hơn nếu chỉ cần kiểm tra sự tồn tại.

### Dùng NOT EXISTS để kiểm tra không tồn tại

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Đây là anti-semi join về mặt ngữ nghĩa: chỉ trả hàng bên trái khi không có hàng phải khớp.

### Vì sao NOT IN có thể khác NOT EXISTS?

```sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

Nếu tập con trả về ít nhất một NULL, kết quả của phép NOT IN có thể trở thành UNKNOWN cho các giá trị không khớp, khiến WHERE loại chúng. NOT EXISTS với điều kiện tương đương thường tránh bẫy NULL này. Nếu dùng NOT IN, cần chứng minh cột con không thể NULL hoặc xử lý NULL rõ ràng.

## 8. Tránh nhân bản hàng khi nối nhiều bảng một-nhiều

Một lỗi hiệu năng và tính đúng thường gặp là nối nhiều bảng con độc lập rồi mới tổng hợp.

Giả sử mỗi đơn hàng có nhiều dòng hàng và nhiều lần thanh toán. Truy vấn:

```sql
SELECT
    o.order_id,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY o.order_id;
```

có thể nhân bản tổ hợp dòng hàng và thanh toán. Nếu một đơn có 3 dòng hàng và 2 lần thanh toán, phép nối tạo 6 hàng trung gian. Mỗi dòng hàng lặp hai lần và mỗi khoản thanh toán lặp ba lần; cả hai tổng có thể bị tính sai.

Một cách diễn đạt an toàn hơn là tổng hợp từng bảng con về một hàng trên mỗi đơn trước khi nối:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.paid_total, 0) AS paid_total
FROM orders AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
    ON p.order_id = o.order_id;
```

Việc tổng hợp trước làm mỗi CTE có tối đa một hàng cho mỗi order_id, tránh nhân chéo giữa hai tập con. CTE ở đây là cách tổ chức câu SQL; hệ quản trị có thể inline hoặc materialize tùy phiên bản và kế hoạch. Hãy kiểm tra execution plan thay vì mặc định CTE luôn tạo bảng tạm.

COALESCE biến NULL do không có hàng con thành 0 theo quy tắc nghiệp vụ. Chỉ dùng 0 nếu không có giao dịch thực sự có nghĩa là tổng bằng 0; nếu cần phân biệt không có dữ liệu với giá trị bằng 0, hãy giữ NULL.

## 9. COUNT và phép tổng hợp trên OUTER JOIN

OUTER JOIN tạo một hàng kết quả cho đối tượng bên trái ngay cả khi không có hàng con. Vì vậy, `COUNT(*)` và `COUNT(cột)` có thể cho kết quả khác nhau.

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

Với khách hàng không có đơn:

- `COUNT(*)` đếm hàng đã được null-extend nên bằng 1.
- `COUNT(o.order_id)` bỏ qua NULL và bằng 0 vì order_id là khóa chính không NULL.

Nếu mục tiêu là đếm số đơn, hãy dùng `COUNT(o.order_id)` hoặc đếm một cột phía phải được bảo đảm NOT NULL. Không dùng `COUNT(*)` một cách máy móc.

SUM, AVG và các hàm tổng hợp khác cũng bỏ qua giá trị NULL trong đầu vào; nhưng khi không có hàng đầu vào phù hợp, kết quả SUM thường là NULL. Dùng COALESCE nếu nghiệp vụ yêu cầu số 0.

## 10. Điều kiện JOIN có thể làm thay đổi tính duy nhất và cardinality

JOIN trên khóa duy nhất ở phía phải có tối đa một hàng khớp cho mỗi hàng trái. JOIN trên cột không duy nhất có thể tạo nhiều hàng kết quả. Bộ tối ưu sử dụng thông tin PRIMARY KEY, UNIQUE, NOT NULL và thống kê để ước lượng số hàng.

Ví dụ:

- `orders.customer_id` có thể lặp lại vì nhiều đơn thuộc cùng khách.
- `customers.customer_id` là PRIMARY KEY nên mỗi đơn khớp tối đa một khách.
- Nếu JOIN qua `email` không có UNIQUE, một email trùng có thể làm một hàng nguồn khớp nhiều hàng đích.

Ràng buộc dữ liệu không chỉ bảo vệ tính đúng mà còn giúp bộ tối ưu ước lượng cardinality và chọn thuật toán JOIN. Nếu dữ liệu thực tế có tính duy nhất nhưng không có ràng buộc tương ứng, optimizer có thể thiếu thông tin để đưa ra kế hoạch tốt nhất.

Không nên thêm DISTINCT chỉ để ép kết quả có vẻ duy nhất. Trước hết xác định quan hệ nghiệp vụ có thật sự một-một hay không, rồi sửa điều kiện JOIN hoặc ràng buộc dữ liệu nếu cần.

## 11. Các phép viết lại JOIN và giới hạn ngữ nghĩa

### INNER JOIN có thể đổi thứ tự trong nhiều trường hợp

Với các phép nối INNER và điều kiện thuần túy, bộ tối ưu thường có thể đổi thứ tự nối vì kết quả quan hệ tương đương về ngữ nghĩa. Ví dụ `(A JOIN B) JOIN C` có thể được tổ chức thành `A JOIN (B JOIN C)` khi điều kiện nối được giữ đúng.

Điều này cho phép optimizer chọn bảng nhỏ hoặc điều kiện chọn lọc cao làm đầu vào trước, giảm số hàng trung gian. Tuy nhiên, outer join, hàm có tác dụng phụ, phép giới hạn hàng, window function hoặc biểu thức không thuần có thể đặt ra ràng buộc khác.

### OUTER JOIN không thể hoán đổi tùy ý

`A LEFT JOIN B` giữ tất cả hàng A. Đổi thành `B LEFT JOIN A` sẽ giữ tất cả hàng B, nên thường thay đổi kết quả. Tương tự, thay LEFT JOIN bằng INNER JOIN làm mất các hàng A không có B.

Việc đẩy điều kiện lọc qua một outer join cũng cần xét null extension. Một điều kiện lọc trên bảng được giữ đầy đủ có thể được đẩy xuống trước join trong một số trường hợp, nhưng điều kiện trên phía được null-extend có thể thay đổi ý nghĩa nếu chuyển sai vị trí.

### UNION ALL không phải lúc nào thay được JOIN

Có thể có cách viết lại dùng UNION ALL để tách các trường hợp khớp và không khớp, nhưng cần xử lý đúng các hàng trùng, NULL và điều kiện loại trừ. Không nên thay một JOIN bằng UNION ALL chỉ dựa trên hình thức truy vấn.

### DISTINCT không sửa được mọi lỗi JOIN

DISTINCT loại các hàng trùng trên toàn bộ danh sách cột được chọn. Nó không khôi phục tổng đã bị nhân bản, không xác định được hàng con đúng và có thể làm mất các hàng trùng hợp lệ theo nghiệp vụ.

## 12. JOIN, chỉ mục và access path

Chỉ mục hỗ trợ JOIN bằng cách cung cấp đường truy cập cho điều kiện nối hoặc điều kiện lọc. Nhưng chỉ mục có ích hay không phụ thuộc số hàng cần đọc và kiểu JOIN.

Với quan hệ customers/orders:

```sql
CREATE INDEX ix_orders_customer_id
    ON orders (customer_id);
```

Chỉ mục trên `orders.customer_id` có thể hỗ trợ nested loop khi truy vấn bắt đầu từ một tập khách hàng nhỏ. Khóa chính `customers(customer_id)` hỗ trợ tìm khách hàng từ đơn hàng.

Nếu truy vấn đọc phần lớn đơn hàng, hash join kết hợp scan có thể rẻ hơn hàng triệu index lookup. Nếu hai tập đầu vào đã có thứ tự theo khóa nối, merge join có thể tránh sort. Chỉ mục không phải lúc nào cũng được dùng chỉ vì nó tồn tại.

### Các yếu tố cần kiểm tra

- Điều kiện nối có dùng trực tiếp cột khóa hay bọc trong hàm/CAST?
- Hai phía có cùng kiểu dữ liệu, độ dài và collation không?
- Chỉ mục có bắt đầu bằng các cột JOIN hoặc điều kiện lọc quan trọng không?
- Có cần composite index để hỗ trợ WHERE và ORDER BY cùng lúc không?
- Ước lượng số hàng có gần với số hàng thực tế không?
- Số lần lặp lookup có quá cao không?
- Có sort, hash spill, bitmap operation hoặc scan quá lớn không?

Ví dụ, nếu một phía là BIGINT và phía kia là VARCHAR, phép nối có thể phát sinh implicit conversion, ảnh hưởng khả năng dùng chỉ mục hoặc ước lượng cardinality. Nên thống nhất kiểu khóa ở schema và truyền tham số đúng kiểu.

## 13. Đọc execution plan để kiểm tra JOIN

Execution plan cho biết hệ quản trị đã triển khai JOIN bằng cách nào. Khi phân tích, hãy xem cả ngữ nghĩa truy vấn và chi phí vật lý.

| Operator/đặc điểm | Cần kiểm tra |
| --- | --- |
| Nested Loop | Số hàng outer, số loops và số lần seek/lookup ở inner |
| Hash Join | Kích thước hai đầu vào, memory grant, hash spill và số hàng thực tế |
| Merge Join | Đầu vào có được sắp xếp sẵn hay phải sort, số hàng hai phía |
| Left/Right/Full Join | Có giữ đúng phía cần bảo toàn và có null extension không |
| Semi/Anti Join | Có được dùng cho EXISTS/NOT EXISTS hay không |
| Estimated vs actual rows | Sai lệch cardinality có làm chọn sai thuật toán hoặc thứ tự nối không |

### Ví dụ với PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.customer_id BETWEEN 1000 AND 1100;
```

Kiểm tra loại join, số hàng thực tế, loops, shared hit/read và các điều kiện filter/join filter. Xem điều kiện status có được áp dụng trước hoặc trong quá trình truy cập orders không, và kết quả có giữ khách hàng không có đơn thanh toán hay không.

`EXPLAIN ANALYZE` thực thi truy vấn. Với truy vấn ghi, có tác dụng phụ; hãy dùng môi trường hoặc transaction thử nghiệm phù hợp. Thời gian đo trong một lần chạy cũng có thể bị ảnh hưởng bởi cache và tải đồng thời.

### Ví dụ với SQL Server

```sql
SET STATISTICS IO, TIME ON;

SELECT c.CustomerId, o.OrderId
FROM dbo.Customers AS c
LEFT JOIN dbo.Orders AS o
    ON o.CustomerId = c.CustomerId
   AND o.Status = 'PAID'
WHERE c.CustomerId BETWEEN 1000 AND 1100;

SET STATISTICS IO, TIME OFF;
```

Đọc actual execution plan, logical reads, CPU time và elapsed time. Kiểm tra Nested Loops/Hash Match/Merge Join, số hàng thực tế, residual predicate, lookup và spill.

## 14. Quy trình viết lại JOIN an toàn

1. **Ghi rõ kết quả nghiệp vụ cần có.** Có cần giữ mọi hàng bên trái, mọi hàng hai phía, hay chỉ cần biết có/không có hàng liên quan?
2. **Xác định cardinality.** Ghi quan hệ một-một, một-nhiều hoặc nhiều-nhiều; xác định khóa duy nhất và cột nullable.
3. **Lập bộ dữ liệu biên.** Có hàng khớp, không có hàng khớp, nhiều hàng khớp, giá trị NULL và hàng có trạng thái không thỏa điều kiện.
4. **Ghi nhận truy vấn gốc.** Lưu kết quả, số hàng, các tổng hợp và execution plan trong điều kiện đo rõ ràng.
5. **Đề xuất một thay đổi.** Ví dụ chuyển LEFT JOIN thành INNER JOIN khi predicate null-rejecting, dùng EXISTS thay JOIN khi chỉ cần kiểm tra sự tồn tại, hoặc tổng hợp bảng con trước khi nối.
6. **So sánh kết quả theo bag semantics.** Không chỉ so sánh tập giá trị phân biệt; phải kiểm tra số lần xuất hiện của từng hàng nếu trùng lặp có ý nghĩa.
7. **Đọc kế hoạch mới.** Xác nhận access path, thuật toán JOIN, cardinality, số trang đọc và chi phí sort/hash.
8. **Đo trên workload đại diện.** So sánh throughput, p50/p95/p99, CPU, I/O, lỗi và tác động đến các truy vấn liên quan.
9. **Triển khai có kiểm soát và theo dõi.** Quan sát thay đổi dữ liệu, thống kê và kế hoạch theo thời gian.

## 15. Ví dụ kiểm chứng ngữ nghĩa

Giả sử dữ liệu có ba khách hàng:

| customer_id | customer_name |
| ---: | --- |
| 1 | An |
| 2 | Bình |
| 3 | Chi |

Và hai đơn hàng:

| order_id | customer_id | status |
| ---: | ---: | --- |
| 101 | 1 | PAID |
| 102 | 1 | PENDING |

Truy vấn LEFT JOIN có điều kiện trạng thái trong ON:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

Kết quả:

| customer_id | order_id |
| ---: | ---: |
| 1 | 101 |
| 2 | NULL |
| 3 | NULL |

Truy vấn với cùng điều kiện ở WHERE:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Kết quả chỉ còn `(1, 101)`. Khách hàng 2 và 3 bị loại vì predicate WHERE không TRUE với giá trị NULL được tạo ra ở phía orders.

Trường hợp khách hàng 1 có hai đơn PAID sẽ tạo hai hàng kết quả trong cả hai truy vấn đầu tiên. Nếu mục tiêu chỉ là liệt kê khách hàng có ít nhất một đơn PAID, dùng EXISTS để tránh nhân bản.

## 16. Những sai lầm thường gặp

- **Đưa điều kiện của LEFT JOIN từ ON sang WHERE.** Có thể loại các hàng không có hàng khớp và vô tình đổi kết quả thành INNER JOIN.
- **Chuyển OUTER JOIN thành INNER JOIN mà không kiểm tra NULL.** Chỉ hợp lệ khi điều kiện sau join thực sự loại hàng null-extended và các ngữ nghĩa khác được giữ nguyên.
- **Dùng JOIN khi chỉ cần kiểm tra tồn tại.** Một hàng trái có nhiều hàng phải khớp sẽ bị nhân bản; EXISTS thường diễn đạt đúng ý định hơn.
- **Dùng NOT IN với tập con có thể chứa NULL.** Logic ba giá trị có thể làm kết quả khác với NOT EXISTS.
- **Dùng COUNT(*) để đếm hàng con sau LEFT JOIN.** Hàng null-extended vẫn được đếm; hãy đếm cột khóa phía con không NULL.
- **Nối nhiều bảng một-nhiều rồi SUM trực tiếp.** Các tập con có thể nhân chéo và làm sai tổng.
- **Thêm DISTINCT để che lỗi nhân bản.** DISTINCT không sửa phép tổng hợp đã sai và có thể loại trùng hợp lệ.
- **Hoán đổi thứ tự OUTER JOIN tùy ý.** Phía được giữ lại thay đổi nên kết quả có thể khác.
- **Cho rằng chỉ mục luôn làm JOIN nhanh hơn.** Hash join hoặc scan có thể rẻ hơn khi cần phần lớn dữ liệu.
- **Bỏ qua kiểu dữ liệu và thống kê.** Implicit conversion hoặc cardinality sai có thể làm kế hoạch kém hiệu quả.

## 17. Danh sách kiểm tra trước khi tối ưu JOIN

- [ ] Đã xác định rõ loại JOIN và phía cần được giữ lại.
- [ ] Đã phân biệt điều kiện nối trong ON với điều kiện lọc trong WHERE.
- [ ] Đã kiểm tra logic NULL và các trường hợp không có hàng khớp.
- [ ] Đã hiểu cardinality và khả năng một hàng bị nhân bản.
- [ ] Dùng EXISTS/NOT EXISTS nếu nghiệp vụ chỉ cần kiểm tra tồn tại/không tồn tại.
- [ ] Đã kiểm tra NOT IN có nguy cơ nhận NULL từ tập con không.
- [ ] Các phép tổng hợp đã tránh nhân chéo giữa nhiều bảng con.
- [ ] Ràng buộc PRIMARY KEY, UNIQUE, FOREIGN KEY và NOT NULL phản ánh dữ liệu thật.
- [ ] Kiểu dữ liệu hai phía JOIN tương thích và không có chuyển đổi không cần thiết.
- [ ] Execution plan có estimated/actual rows, thuật toán JOIN và số lần lookup hợp lý.
- [ ] Đã đo logical/physical reads, CPU, throughput và p95/p99 trước/sau.
- [ ] Kết quả được so sánh theo cả giá trị và số lần xuất hiện của hàng.

## Kết luận

INNER JOIN chỉ giữ các cặp hàng khớp; OUTER JOIN còn giữ các hàng ở một hoặc cả hai phía bằng cách tạo giá trị NULL cho phía không khớp. Vì vậy, vị trí đặt điều kiện trong ON và WHERE có thể làm thay đổi kết quả, đặc biệt với LEFT JOIN. Những phép viết lại như chuyển outer thành inner, dùng EXISTS/NOT EXISTS, đổi thứ tự nối hoặc tổng hợp trước JOIN chỉ an toàn khi bảo toàn logic NULL, cardinality và số lần xuất hiện của hàng. Hãy kiểm chứng bằng dữ liệu biên, đọc execution plan và đo workload thực tế để đạt hiệu năng tốt mà vẫn giữ nguyên ngữ nghĩa nghiệp vụ.
