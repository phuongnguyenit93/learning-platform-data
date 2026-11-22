# Đọc kết quả rỗng, dữ liệu NULL và số dòng bị nhân bản

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Khi đọc kết quả SELECT, ba tình huống thường gây nhầm lẫn là truy vấn không trả hàng nào, một hàng có cột mang giá trị NULL và kết quả có nhiều hàng trông giống nhau. Mỗi tình huống có nguyên nhân và cách xử lý riêng.

Kết quả rỗng không có nghĩa dữ liệu trong bảng là NULL. Một giá trị NULL không có nghĩa hàng đó không tồn tại. Nhiều hàng giống nhau trong kết quả cũng không nhất thiết là dữ liệu bị lưu trùng; chúng có thể được tạo ra bởi quan hệ một-nhiều hoặc nhiều-nhiều khi JOIN. Muốn đọc SQL chính xác, cần kiểm tra số hàng, khóa định danh, điều kiện lọc và lực lượng quan hệ giữa các bảng.

## 1. Phân biệt ba hiện tượng

| Hiện tượng | Điều đang xảy ra | Ví dụ |
|---|---|---|
| Kết quả rỗng (empty result) | Truy vấn trả về 0 hàng | Không có đơn hàng nào có trạng thái CANCELLED |
| Giá trị NULL | Hàng tồn tại nhưng một cột không có giá trị được lưu hoặc không xác định | Khách hàng chưa cung cấp ngày sinh |
| Hàng lặp trong kết quả | Nhiều hàng có cùng một phần hoặc toàn bộ giá trị được hiển thị | Một khách hàng xuất hiện nhiều lần vì có nhiều đơn hàng hoặc nhiều dòng hàng |

Ví dụ, ba truy vấn sau cho ba kết quả khác nhau:

~~~sql
-- Không có hàng nào thỏa điều kiện
SELECT customer_id, full_name
FROM customers
WHERE customer_id = -1;

-- Một hàng, trong đó giá trị của cột là NULL
SELECT NULL AS birth_date;

-- Nhiều hàng có thể cùng customer_id khi JOIN sang bảng con
SELECT c.customer_id, c.full_name, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Khi ứng dụng nhận kết quả từ driver, cần phân biệt:

- Result set không có hàng: vòng lặp đọc kết quả không chạy lần nào.
- Result set có hàng nhưng cột trả NULL: hàng vẫn tồn tại; giá trị của trường đó là NULL.
- Result set có nhiều hàng: mỗi hàng là một dòng kết quả theo phép toán SQL, kể cả khi các cột đang hiển thị giống nhau.

## 2. Truy vấn rỗng khác với một hàng chứa NULL

### 2.1. Truy vấn không trả hàng

Một truy vấn SELECT thông thường trả kết quả rỗng khi không có hàng nào thỏa điều kiện:

~~~sql
SELECT order_id, status
FROM orders
WHERE status = 'CANCELLED';
~~~

Nếu bảng không có đơn CANCELLED, kết quả có 0 hàng và vẫn có metadata về các cột kết quả. Không có một hàng ngầm nào chứa NULL.

Trong Java JDBC, ResultSet vẫn được tạo thành công. Lần gọi next() đầu tiên trả false nếu không có hàng:

~~~java
try (PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id, status FROM orders WHERE status = ?")) {
    statement.setString(1, "CANCELLED");

    try (ResultSet result = statement.executeQuery()) {
        if (!result.next()) {
            System.out.println("Không tìm thấy đơn hàng");
        } else {
            do {
                long orderId = result.getLong("order_id");
                String status = result.getString("status");
                System.out.println(orderId + " " + status);
            } while (result.next());
        }
    }
}
~~~

Điểm quan trọng là kiểm tra next() trước khi đọc cột. Không đọc một hàng giả định khi ResultSet đang rỗng.

### 2.2. Một hàng có giá trị NULL

Truy vấn có thể trả một hàng mà giá trị một hoặc nhiều cột là NULL:

~~~sql
SELECT customer_id, birth_date, age
FROM customers
WHERE customer_id = 10;
~~~

Nếu khách hàng 10 tồn tại nhưng chưa có birth_date, truy vấn vẫn trả một hàng. Chỉ birth_date có giá trị NULL.

Trong JDBC, getString() trả Java null khi SQL value là NULL. Với kiểu số nguyên, getInt() trả 0 nếu SQL value là NULL; cần gọi wasNull() ngay sau khi đọc cột để phân biệt NULL với số 0 thực:

~~~java
if (result.next()) {
    int age = result.getInt("age");
    boolean ageIsNull = result.wasNull();

    if (ageIsNull) {
        System.out.println("Chưa biết tuổi");
    } else {
        System.out.println("Tuổi: " + age);
    }
}
~~~

Nếu dùng getObject() với kiểu Java phù hợp, có thể nhận null trực tiếp. Hãy kiểm tra hành vi mapping của JDBC driver và kiểu dữ liệu cụ thể.

### 2.3. Aggregate trên tập rỗng

Một điểm dễ gây nhầm là SELECT aggregate không có GROUP BY có thể trả một hàng ngay cả khi đầu vào không có hàng:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS amount_sum,
       AVG(total_amount) AS amount_average
FROM orders
WHERE status = 'CANCELLED';
~~~

Nếu không có đơn CANCELLED, kết quả thường là một hàng với row_count = 0, amount_sum = NULL và amount_average = NULL. COUNT trả 0; SUM và AVG trả NULL khi không có giá trị đầu vào để tổng hợp.

Ngược lại, nếu truy vấn có GROUP BY và không có hàng đầu vào, không có nhóm nào để tạo kết quả:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE status = 'CANCELLED'
GROUP BY customer_id;
~~~

Truy vấn này trả 0 hàng nếu không có đơn CANCELLED. Cần hiểu sự khác nhau giữa aggregate toàn tập và aggregate theo nhóm.

## 3. NULL và điều kiện lọc

NULL không phải chuỗi rỗng và cũng không phải số 0. Phép so sánh thông thường với NULL tạo kết quả UNKNOWN:

~~~sql
SELECT
    NULL = NULL AS equals_null,
    NULL = 0 AS equals_zero,
    NULL <> 'PAID' AS not_paid;
~~~

Các biểu thức so sánh trên trả NULL/UNKNOWN. Vì WHERE chỉ giữ hàng mà điều kiện là TRUE, hàng có biểu thức UNKNOWN bị loại.

Kiểm tra NULL phải dùng IS NULL hoặc IS NOT NULL:

~~~sql
SELECT customer_id, birth_date
FROM customers
WHERE birth_date IS NULL;

SELECT customer_id, birth_date
FROM customers
WHERE birth_date IS NOT NULL;
~~~

Không viết WHERE birth_date = NULL. Nếu muốn so sánh null-safe theo cú pháp MySQL, có thể dùng toán tử <=>:

~~~sql
SELECT customer_id
FROM customers
WHERE birth_date <=> @target_birth_date;
~~~

Khi tham số là NULL, toán tử <=> tìm các hàng có birth_date NULL; khi tham số có ngày cụ thể, nó so sánh giá trị tương ứng.

### 3.1. Phân biệt NULL, chuỗi rỗng và số 0

Các điều kiện sau kiểm tra các trạng thái khác nhau:

~~~sql
SELECT *
FROM customer_profiles
WHERE nickname IS NULL;

SELECT *
FROM customer_profiles
WHERE nickname = '';

SELECT *
FROM inventory
WHERE quantity = 0;
~~~

NULL có nghĩa chưa biết hoặc không áp dụng theo mô hình dữ liệu; chuỗi rỗng là một giá trị chuỗi có độ dài 0; số 0 là một giá trị số cụ thể. Không dùng 0 hoặc chuỗi rỗng thay cho NULL nếu nghiệp vụ cần phân biệt.

## 4. Vì sao JOIN làm tăng số hàng?

### 4.1. JOIN trả một hàng cho mỗi tổ hợp khớp

JOIN không mặc định trả một hàng cho mỗi bản ghi ở bảng bên trái. Nó trả hàng cho mỗi tổ hợp bản ghi thỏa điều kiện JOIN.

Giả sử:

- Một khách hàng có hai đơn hàng.
- Đơn thứ nhất có hai dòng hàng.
- Đơn thứ hai có một dòng hàng.

Khi nối customers → orders → order_items, khách hàng đó xuất hiện ba lần vì có ba dòng hàng. Đây là kết quả đúng của quan hệ một-nhiều, không nhất thiết là lỗi dữ liệu.

### 4.2. Cardinality của quan hệ

| Quan hệ | Kết quả khi JOIN |
|---|---|
| Một-một | Mỗi hàng phía trái khớp tối đa một hàng phía phải nếu ràng buộc được bảo đảm |
| Một-nhiều | Một hàng phía trái có thể xuất hiện nhiều lần, một lần cho mỗi hàng con |
| Nhiều-nhiều | Một hàng có thể kết hợp với nhiều hàng ở cả hai phía qua bảng liên kết; số tổ hợp có thể tăng nhanh |

Ví dụ, một order có 3 order_items và mỗi item có 2 bản ghi shipment thì khi JOIN cả hai bảng con trực tiếp, order có thể xuất hiện 3 × 2 = 6 dòng. Nếu cộng giá trị cấp order trên kết quả đó, tổng sẽ bị nhân lên.

### 4.3. SQL sử dụng bag semantics

Kết quả truy vấn SQL mặc định có thể chứa các hàng lặp (bag/multiset semantics). SELECT không tự loại bỏ hàng trùng. Hai hàng có cùng giá trị ở các cột đang chiếu vẫn có thể là hai tổ hợp dữ liệu hợp lệ khác nhau.

Chỉ dùng DISTINCT khi yêu cầu nghiệp vụ thực sự là lấy các tổ hợp giá trị duy nhất trong danh sách SELECT. DISTINCT không phải công cụ mặc định để sửa JOIN sai.

## 5. Ví dụ JOIN làm nhân bản kết quả

Xét truy vấn:

~~~sql
SELECT c.customer_id,
       c.full_name,
       o.order_id,
       i.item_id,
       i.product_name
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN order_items AS i
  ON i.order_id = o.order_id
ORDER BY c.customer_id, o.order_id, i.item_id;
~~~

Nếu một khách có hai đơn, cả hai đơn đều có dòng hàng và tổng cộng có ba dòng hàng, kết quả có ba hàng cho khách đó. Nếu một đơn không có dòng hàng, LEFT JOIN vẫn tạo một hàng null-extended cho đơn đó. Các cột customer_id và full_name lặp lại vì mỗi hàng biểu diễn một tổ hợp đơn/dòng hàng, chứ không phải một khách hàng riêng.

Muốn biết số hàng ở mỗi cấp, hãy xác định khóa của từng thực thể:

- customer_id định danh khách hàng.
- order_id định danh đơn hàng.
- item_id định danh dòng hàng.

Không đếm số khách bằng COUNT(*) sau khi JOIN sang order_items. Dùng COUNT(DISTINCT c.customer_id) nếu muốn đếm khách duy nhất trong kết quả, hoặc tính ở đúng cấp dữ liệu trước khi JOIN.

## 6. LEFT JOIN tạo NULL cho phía không khớp

LEFT JOIN giữ tất cả hàng ở bảng trái. Nếu không có hàng bên phải thỏa điều kiện, MySQL tạo một hàng kết quả trong đó các cột từ phía phải mang NULL:

~~~sql
SELECT c.customer_id,
       c.full_name,
       o.order_id,
       o.status
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Khách hàng chưa có đơn vẫn xuất hiện. Các cột o.order_id và o.status trong hàng được bổ sung sẽ là NULL, kể cả khi cột order_id được khai báo NOT NULL ở bảng orders. Đây là NULL do phép outer join tạo ra, không phải giá trị NULL được lưu trong hàng orders.

### 6.1. Phân biệt không có hàng khớp với cột thật sự NULL

Để kiểm tra có hàng con khớp hay không, hãy kiểm tra khóa chính hoặc một cột được bảo đảm NOT NULL của bảng con:

~~~sql
SELECT c.customer_id,
       o.order_id,
       o.delivery_note
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Nếu o.order_id IS NULL, không có hàng orders khớp (giả sử order_id là primary key). Nhưng nếu o.delivery_note IS NULL, chưa thể kết luận không có đơn hàng: đơn có thể tồn tại và delivery_note thực sự chưa được cung cấp.

Đây là lý do nên kiểm tra khóa chính phía phải khi phân biệt hàng không khớp với dữ liệu cột NULL.

### 6.2. Đếm hàng con sau LEFT JOIN

~~~sql
SELECT c.customer_id,
       COUNT(*) AS joined_rows,
       COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

Với khách không có đơn:

- COUNT(*) trả 1 vì LEFT JOIN vẫn tạo một hàng null-extended.
- COUNT(o.order_id) trả 0 vì order_id là NULL ở hàng được bổ sung và COUNT(expression) bỏ qua NULL.

Khi đếm số hàng con sau LEFT JOIN, thường cần COUNT(primary_key_con), không phải COUNT(*).

## 7. Điều kiện trong ON và WHERE của LEFT JOIN

Vị trí điều kiện lọc có thể làm thay đổi kết quả đáng kể.

### 7.1. Đặt điều kiện phía phải trong WHERE

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Khách không có đơn nhận NULL ở o.status. Điều kiện o.status = 'PAID' trở thành UNKNOWN, nên WHERE loại hàng đó. Kết quả vì thế chỉ còn khách có đơn PAID; với điều kiện này, LEFT JOIN có hiệu quả giống INNER JOIN.

### 7.2. Đặt điều kiện phía phải trong ON

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
~~~

Truy vấn này vẫn giữ mọi khách hàng. Nó chỉ ghép các đơn PAID; khách không có đơn PAID nhận NULL ở các cột của orders.

### 7.3. Tìm khách chưa có đơn

Có thể dùng LEFT JOIN kết hợp kiểm tra khóa chính phía phải:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

Hoặc diễn đạt trực tiếp bằng NOT EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

NOT EXISTS thường rõ nghĩa khi mục tiêu chỉ là kiểm tra không có hàng con. Nó không nhân bản hàng khách hàng vì subquery chỉ kiểm tra sự tồn tại.

## 8. Đếm và tính tổng sau JOIN

### 8.1. COUNT(*) có thể đếm dòng kết hợp

Ví dụ:

~~~sql
SELECT c.customer_id,
       COUNT(*) AS row_count,
       COUNT(o.order_id) AS order_count,
       COUNT(i.item_id) AS item_count,
       COUNT(DISTINCT o.order_id) AS distinct_order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id;
~~~

Ý nghĩa các phép đếm:

- COUNT(*) đếm số hàng sau khi hai JOIN tạo ra.
- COUNT(o.order_id) đếm số lần order xuất hiện trong kết quả đã JOIN; nếu một order có nhiều item, order đó vẫn có thể bị đếm nhiều lần.
- COUNT(i.item_id) đếm số dòng hàng khớp.
- COUNT(DISTINCT o.order_id) đếm số đơn duy nhất trong nhóm.

Nếu muốn đếm đơn, COUNT(DISTINCT o.order_id) sửa đúng cấp đếm trong ví dụ này. Nhưng không nên mặc định thêm DISTINCT cho mọi aggregate; hãy hiểu quan hệ và chọn phép tính đúng.

### 8.2. SUM cũng có thể bị nhân

Giả sử một đơn hàng có total_amount = 120 và hai dòng hàng. Sau JOIN, total_amount xuất hiện hai lần. SUM(o.total_amount) sẽ cộng 120 hai lần nếu tính trực tiếp trên kết quả đã JOIN.

Không nên sửa bằng SUM(DISTINCT o.total_amount). Hai đơn hàng khác nhau có thể cùng tổng tiền 120; DISTINCT theo giá trị tiền sẽ gộp hai giá trị hợp lệ và làm thiếu tổng.

### 8.3. Tổng hợp trước khi JOIN

Nếu cần tổng đơn theo khách và tổng số dòng hàng theo khách, hãy tính từng cấp riêng:

~~~sql
WITH order_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS order_amount
    FROM orders
    GROUP BY customer_id
),
item_totals AS (
    SELECT o.customer_id,
           COUNT(i.item_id) AS item_count,
           SUM(i.quantity * i.unit_price) AS item_amount
    FROM orders AS o
    JOIN order_items AS i
      ON i.order_id = o.order_id
    GROUP BY o.customer_id
)
SELECT c.customer_id,
       c.full_name,
       COALESCE(ot.order_count, 0) AS order_count,
       COALESCE(ot.order_amount, 0) AS order_amount,
       COALESCE(it.item_count, 0) AS item_count,
       COALESCE(it.item_amount, 0) AS item_amount
FROM customers AS c
LEFT JOIN order_totals AS ot
  ON ot.customer_id = c.customer_id
LEFT JOIN item_totals AS it
  ON it.customer_id = c.customer_id;
~~~

Mỗi CTE tạo tối đa một hàng cho mỗi customer_id. Khi ghép các tập đã tổng hợp, phép JOIN không còn nhân các hàng chi tiết của hai bảng con với nhau.

COALESCE ở đây chuyển kết quả tổng hợp NULL do không có hàng thành 0 để hiển thị. Chỉ làm vậy nếu nghiệp vụ định nghĩa không có đơn hoặc dòng hàng tương đương tổng bằng 0; nếu cần phân biệt "không có dữ liệu" với "đã đo và tổng bằng 0", hãy giữ NULL.

CTE yêu cầu MySQL 8.0 trở lên. Trên phiên bản cũ hơn, có thể dùng derived table với cùng logic tổng hợp.

## 9. DISTINCT không phải cách sửa JOIN sai

DISTINCT loại các hàng trùng nhau trong toàn bộ danh sách cột được SELECT:

~~~sql
SELECT DISTINCT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Truy vấn trên trả mỗi tổ hợp customer_id/full_name một lần. Nó phù hợp nếu yêu cầu là danh sách khách có ít nhất một đơn, nhưng có thể biểu diễn ý định rõ hơn bằng EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Nếu SELECT thêm o.order_id, các hàng có order_id khác nhau không còn trùng nhau nên DISTINCT không loại chúng. DISTINCT chỉ xét những cột trong projection; nó không biết khóa nghiệp vụ nào được xem là một thực thể.

Không dùng DISTINCT để che lỗi điều kiện JOIN thiếu hoặc sai. Nếu JOIN tạo tích Descartes ngoài ý muốn, DISTINCT có thể tốn tài nguyên và vẫn không khôi phục được ý nghĩa của truy vấn.

### 9.1. UNION và UNION ALL

UNION loại hàng trùng trong kết quả kết hợp; UNION ALL giữ nguyên mọi hàng:

~~~sql
SELECT email FROM current_customers
UNION
SELECT email FROM archived_customers;
~~~

~~~sql
SELECT email FROM current_customers
UNION ALL
SELECT email FROM archived_customers;
~~~

Chọn UNION nếu yêu cầu là tập giá trị email duy nhất theo phép so sánh của truy vấn. Chọn UNION ALL nếu cần giữ mọi hàng nguồn, chẳng hạn để đối chiếu hoặc đếm bản ghi. Không dùng UNION để tự động loại dữ liệu trùng trong quy trình ETL nếu chưa xác định quy tắc hợp nhất.

## 10. Tìm nguyên nhân hàng bị nhân bản

### 10.1. Kiểm tra khóa và tính duy nhất

Trước tiên, xác nhận cột dùng để JOIN có phải khóa duy nhất ở phía cần một-một hay không:

~~~sql
SHOW CREATE TABLE customers;
SHOW CREATE TABLE orders;
~~~

Hoặc xem index:

~~~sql
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE,
       SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('customers', 'orders')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
~~~

Nếu điều kiện JOIN dựa trên một cột không unique, một hàng phía trái có thể khớp nhiều hàng phía phải. Đây có thể là đúng theo mô hình hoặc là thiếu thành phần trong điều kiện JOIN.

### 10.2. Kiểm tra duplicate theo khóa nghiệp vụ

Ví dụ, nếu email phải duy nhất:

~~~sql
SELECT email, COUNT(*) AS occurrences
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Nếu cột có collation không phân biệt hoa/thường hoặc dấu, GROUP BY dùng quy tắc collation của cột. Nếu kiểm tra theo quy tắc mới, hãy chỉ định collation đích trong biểu thức và xem lại các nhóm trùng.

Một kết quả có nhiều hàng cùng tên không chứng minh dữ liệu trùng nếu khóa chính khác nhau. Hãy xác định khóa nghiệp vụ nào phải duy nhất trước khi kết luận.

### 10.3. Đếm số hàng trước và sau từng JOIN

Chạy truy vấn từng bước:

~~~sql
SELECT COUNT(*) AS customer_rows
FROM customers;

SELECT COUNT(*) AS customer_order_rows
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;

SELECT COUNT(*) AS customer_order_item_rows
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS i
  ON i.order_id = o.order_id;
~~~

So sánh số hàng giúp xác định JOIN nào làm tăng cardinality. Mức tăng có thể hoàn toàn hợp lệ nếu nối sang bảng con; cần so sánh với số hàng dự kiến theo quan hệ dữ liệu.

### 10.4. Tìm khóa có nhiều hàng khớp

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Truy vấn này liệt kê khách có nhiều đơn. Nếu mô hình cho phép một khách có nhiều đơn, đây không phải dữ liệu lỗi. Nếu một bảng được kỳ vọng chỉ có một hàng cho mỗi customer_id, cần kiểm tra unique constraint hoặc điều kiện JOIN.

## 11. JOIN thiếu điều kiện và tích Descartes

Một lỗi thường gặp là bỏ quên điều kiện nối:

~~~sql
-- Sai nếu mục tiêu là ghép đơn với đúng khách hàng
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o;
~~~

Không có điều kiện JOIN, truy vấn tạo tích Descartes: mỗi hàng customers kết hợp với mỗi hàng orders. Nếu có 100 khách và 1.000 đơn, kết quả có thể có 100.000 tổ hợp.

Viết điều kiện quan hệ:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Một lỗi khác là nối thiếu thành phần khóa ghép. Nếu bảng có tenant_id và customer_id, chỉ nối customer_id có thể ghép nhầm dữ liệu giữa tenant:

~~~sql
SELECT *
FROM tenant_customers AS c
JOIN orders AS o
  ON o.tenant_id = c.tenant_id
 AND o.customer_id = c.customer_id;
~~~

Luôn kiểm tra đầy đủ các cột tham gia khóa ngoại hoặc khóa nghiệp vụ. Với quan hệ nhiều-nhiều, nối qua bảng liên kết và hiểu số tổ hợp được tạo ra.

## 12. Quy trình chẩn đoán kết quả SELECT

Khi kết quả rỗng, có NULL bất ngờ hoặc số hàng tăng nhiều, thực hiện lần lượt:

1. **Kiểm tra ngữ cảnh:** xác nhận database mặc định bằng SELECT DATABASE(), bảng đúng schema và tài khoản có quyền xem dữ liệu.
2. **Chạy truy vấn nguồn:** kiểm tra từng bảng riêng, số hàng và các giá trị mẫu trước khi JOIN.
3. **Kiểm tra điều kiện WHERE:** tạm thời bỏ từng điều kiện để xác định điều kiện nào loại hàng; xem xét NULL, kiểu dữ liệu và ép kiểu.
4. **Thêm JOIN từng bước:** bắt đầu từ bảng gốc, thêm từng bảng liên quan rồi đếm số hàng sau mỗi bước.
5. **Kiểm tra khóa:** xác nhận cột JOIN, unique index, foreign key và các thành phần của khóa ghép.
6. **Phân biệt NULL:** dùng khóa chính phía phải để kiểm tra hàng không khớp; không dùng cột nullable làm dấu hiệu duy nhất.
7. **Kiểm tra aggregate:** xác định đang đếm hàng kết hợp, hàng con hay thực thể duy nhất; tổng hợp từng cấp trước khi ghép nếu cần.
8. **Đọc kế hoạch:** dùng EXPLAIN để xem thứ tự JOIN, access type và ước lượng rows. MySQL 8.0.18+ có EXPLAIN ANALYZE để thực thi truy vấn và xem số liệu iterator thực tế; chỉ chạy khi đã đánh giá tải và tác động.

Không sửa bằng DISTINCT hoặc COALESCE trước khi xác định nguyên nhân. Hai hàm này có thể thay đổi hình dạng kết quả nhưng không sửa điều kiện JOIN sai hoặc logic lọc không đúng.

## 13. Bài thực hành: kết quả rỗng, NULL và fan-out

Thực hiện trên database lab. Tạo ba bảng độc lập:

~~~sql
CREATE TABLE lab_customers (
    customer_id INT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id INT NOT NULL,
    customer_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_orders_customer (customer_id),
    CONSTRAINT fk_lab_orders_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customers (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_order_items (
    item_id INT NOT NULL,
    order_id INT NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (item_id),
    KEY ix_lab_items_order (order_id),
    CONSTRAINT fk_lab_items_order
      FOREIGN KEY (order_id)
      REFERENCES lab_orders (order_id)
) ENGINE=InnoDB;
~~~

Nạp dữ liệu mẫu:

~~~sql
INSERT INTO lab_customers (customer_id, full_name) VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');

INSERT INTO lab_orders (order_id, customer_id, status, total_amount) VALUES
    (101, 1, 'PAID', 120.00),
    (102, 1, 'PENDING', 50.00),
    (103, 2, 'PAID', 90.00);

INSERT INTO lab_order_items
    (item_id, order_id, product_name, quantity, unit_price)
VALUES
    (1001, 101, 'Book', 1, 100.00),
    (1002, 101, 'Pen', 2, 10.00),
    (1003, 102, 'Bag', 1, 50.00);
~~~

**Bước 1 — Quan sát kết quả rỗng và hàng NULL.**

~~~sql
SELECT *
FROM lab_customers
WHERE customer_id = 99;

SELECT NULL AS missing_value;

SELECT COUNT(*) AS no_customer
FROM lab_customers
WHERE customer_id = 99;
~~~

Ghi nhận truy vấn đầu trả 0 hàng, truy vấn thứ hai trả một hàng có NULL, truy vấn thứ ba trả một hàng có giá trị 0.

**Bước 2 — Quan sát JOIN một-nhiều.**

~~~sql
SELECT c.customer_id, c.full_name,
       o.order_id, i.item_id, i.product_name
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lab_order_items AS i
  ON i.order_id = o.order_id
ORDER BY c.customer_id, o.order_id, i.item_id;
~~~

Khách An xuất hiện ba hàng: hai dòng của đơn 101 và một dòng của đơn 102. Khách Binh có một đơn nhưng chưa có dòng hàng, nên item_id NULL. Khách Chi chưa có đơn, nên cả order_id và item_id NULL.

**Bước 3 — So sánh cách đếm.**

~~~sql
SELECT c.customer_id,
       COUNT(*) AS joined_rows,
       COUNT(o.order_id) AS order_occurrences,
       COUNT(DISTINCT o.order_id) AS distinct_orders,
       COUNT(i.item_id) AS item_count
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lab_order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả dự kiến:

| Khách hàng | joined_rows | order_occurrences | distinct_orders | item_count |
|---|---:|---:|---:|---:|
| An | 3 | 3 | 2 | 3 |
| Binh | 1 | 1 | 1 | 0 |
| Chi | 1 | 0 | 0 | 0 |

Giải thích vì sao COUNT(o.order_id) của An bằng 3 dù khách chỉ có 2 đơn, và vì sao COUNT(*) của Chi bằng 1.

**Bước 4 — Quan sát tổng tiền bị nhân.**

~~~sql
SELECT c.customer_id,
       SUM(o.total_amount) AS incorrect_order_total,
       SUM(DISTINCT o.total_amount) AS distinct_amount_total
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lab_order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Với khách An, tổng đúng ở bảng orders là 170.00 nhưng truy vấn sau JOIN có thể cộng 120.00 hai lần và trả 290.00. SUM(DISTINCT total_amount) tình cờ trả 170.00 trong dữ liệu mẫu; nếu hai đơn khác nhau cùng có tổng 120.00 thì cách này lại làm thiếu dữ liệu. Không dùng SUM(DISTINCT) để chữa fan-out.

**Bước 5 — Tổng hợp trước khi JOIN.**

~~~sql
WITH order_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS order_amount
    FROM lab_orders
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       COALESCE(ot.order_count, 0) AS order_count,
       COALESCE(ot.order_amount, 0) AS order_amount
FROM lab_customers AS c
LEFT JOIN order_totals AS ot
  ON ot.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Mỗi khách chỉ có tối đa một hàng trong order_totals nên kết quả có đúng một hàng cho mỗi khách. CTE cần MySQL 8.0 trở lên; có thể thay bằng derived table nếu dùng phiên bản cũ hơn.

**Bước 6 — So sánh điều kiện ON và WHERE.**

~~~sql
-- Giữ tất cả khách, chỉ ghép đơn PAID
SELECT c.customer_id, o.order_id
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';

-- Chỉ còn khách có đơn PAID
SELECT c.customer_id, o.order_id
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

So sánh việc khách Chi có còn xuất hiện hay không và giải thích vai trò của WHERE.

**Bước 7 — Tìm khách không có đơn.**

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Kết quả chỉ có khách Chi. Thử viết lại bằng LEFT JOIN và WHERE o.order_id IS NULL để so sánh.

**Bước 8 — Dọn dữ liệu lab.**

~~~sql
DROP TABLE lab_order_items;
DROP TABLE lab_orders;
DROP TABLE lab_customers;
~~~

Xóa bảng con trước bảng cha để không vi phạm foreign key. Chỉ thực hiện trên các bảng lab vừa tạo.

**Kết quả cần đạt:** phân biệt được result set rỗng với hàng chứa NULL; giải thích được LEFT JOIN tạo NULL cho phía không khớp; nhận diện fan-out khi nối một-nhiều; chọn đúng COUNT và cách tổng hợp; biết khi nào dùng EXISTS thay cho JOIN.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ứng dụng báo không có dữ liệu nhưng truy vấn trên SQL client có hàng | Khác database, session, tham số, transaction hoặc quyền | Kiểm tra DATABASE(), tham số bind, session và transaction của ứng dụng |
| SELECT trả 0 hàng nhưng ứng dụng mong một hàng NULL | Không có hàng thỏa điều kiện; không phải cột bị NULL | Xác minh dữ liệu và điều kiện lọc; xử lý empty result riêng |
| LEFT JOIN không giữ hàng bảng trái | Điều kiện trên bảng phải đặt trong WHERE | Chuyển điều kiện lọc bảng phải vào ON nếu muốn giữ hàng trái |
| COUNT(*) lớn hơn số bản ghi cha | JOIN sang bảng con tạo nhiều hàng cho mỗi cha | Đếm khóa con hoặc COUNT(DISTINCT khóa cha) theo mục tiêu |
| SUM bị cao bất thường sau JOIN | Giá trị cấp cha bị lặp theo hàng con | Tổng hợp từng bảng theo đúng cấp trước khi JOIN |
| DISTINCT làm kết quả đúng số hàng nhưng tổng vẫn sai | DISTINCT chỉ khử hàng trùng trong projection, không sửa aggregate đã nhân | Xác định cardinality và tổng hợp trước khi ghép |
| Cột phía phải NULL nhưng không rõ có hàng khớp hay không | Cột được kiểm tra vốn cho phép NULL | Kiểm tra primary key hoặc cột NOT NULL phía phải |
| JOIN tạo rất nhiều hàng | Thiếu điều kiện hoặc thiếu thành phần khóa ghép | Kiểm tra ON, khóa ngoại và số hàng từng bước |
| GROUP BY không trả nhóm nào | Không có hàng đầu vào thỏa WHERE | Kiểm tra điều kiện nguồn; phân biệt với aggregate không GROUP BY |

## 15. Nguyên tắc cần ghi nhớ

- Empty result là 0 hàng; NULL là giá trị của một cột trong hàng tồn tại.
- Aggregate không GROUP BY có thể trả một hàng với COUNT = 0 và SUM/AVG = NULL khi đầu vào rỗng.
- WHERE chỉ giữ điều kiện TRUE; phép so sánh với NULL thường tạo UNKNOWN và bị loại.
- LEFT JOIN tạo hàng null-extended cho phía phải không khớp; dùng khóa chính phía phải để xác định có hàng con.
- JOIN trả một hàng cho mỗi tổ hợp khớp; quan hệ một-nhiều và nhiều-nhiều làm hàng phía trái xuất hiện nhiều lần.
- COUNT(*) đếm hàng sau JOIN; COUNT(child.primary_key) đếm hàng con khớp; COUNT(DISTINCT parent.primary_key) đếm thực thể cha duy nhất.
- Giá trị cấp cha có thể bị cộng nhiều lần khi JOIN xuống cấp chi tiết; tổng hợp từng cấp trước khi ghép.
- DISTINCT chỉ loại hàng trùng trong toàn bộ projection; nó không sửa JOIN sai hoặc aggregate bị nhân.
- Dùng EXISTS/NOT EXISTS khi chỉ cần kiểm tra có hoặc không có hàng liên quan.
- Thêm JOIN từng bước và đếm số hàng để tìm đúng điểm cardinality tăng.

Đọc đúng kết quả SELECT đòi hỏi hiểu số hàng, giá trị NULL và quan hệ giữa các bảng. Khi xác định đúng cấp dữ liệu và cardinality trước khi lọc, đếm hoặc tổng hợp, bạn sẽ tránh được kết quả rỗng bị hiểu sai, dữ liệu thiếu bị che khuất và các phép tính bị nhân do JOIN.
