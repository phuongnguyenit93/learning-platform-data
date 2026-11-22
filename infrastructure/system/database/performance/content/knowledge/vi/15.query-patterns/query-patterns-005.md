# Truy vấn kiểm tra tồn tại và đếm theo đúng nhu cầu nghiệp vụ

Trong ứng dụng, nhiều câu hỏi dữ liệu nghe có vẻ giống nhau nhưng đòi hỏi cơ sở dữ liệu thực hiện những công việc khác nhau. “Khách hàng này có đơn hàng nào không?” chỉ cần biết có ít nhất một dòng phù hợp. “Khách hàng này có bao nhiêu đơn hàng?” cần tính số lượng chính xác. “Có bao nhiêu khách hàng đã từng đặt hàng?” cần đếm số khách hàng phân biệt, không phải số đơn hàng. Dùng cùng một kiểu truy vấn cho tất cả những câu hỏi này có thể tạo ra công việc dư thừa hoặc trả về kết quả sai.

Trong chương **Mẫu truy vấn**, bài học này tập trung vào cách viết truy vấn kiểm tra tồn tại và đếm theo đúng nhu cầu nghiệp vụ. Đây là một phần của phương pháp tối ưu hiệu năng trong module **DATABASE_PERFORMANCE**: lựa chọn mẫu SQL phù hợp, tận dụng chỉ mục, đọc execution plan, hiểu thống kê và kiểm chứng kết quả dưới tải thực tế. Mục tiêu là để DBMS chỉ xử lý lượng dữ liệu cần thiết cho câu hỏi mà ứng dụng thực sự đặt ra.

Nguyên tắc quan trọng là phân biệt ba nhu cầu: xác nhận có hay không có bản ghi, đếm số dòng và đếm số thực thể phân biệt. EXISTS, NOT EXISTS, COUNT(*) và COUNT(DISTINCT ...) có semantics và chi phí khác nhau. Chọn đúng phép toán trước, sau đó mới tối ưu access path và đo hiệu quả.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt truy vấn kiểm tra tồn tại với truy vấn đếm chính xác.
- Sử dụng EXISTS và NOT EXISTS để biểu đạt câu hỏi có hoặc không có bản ghi liên quan.
- Chọn COUNT(*), COUNT(column) và COUNT(DISTINCT column) theo đúng semantics.
- Tránh nhân bản dòng khi JOIN chỉ nhằm kiểm tra sự tồn tại.
- Hiểu ảnh hưởng của NULL, duplicate rows, điều kiện tương quan và phép nối ngoài.
- Thiết kế chỉ mục hỗ trợ existence check và count theo điều kiện thực tế.
- Đọc execution plan để nhận diện semi-join, anti-join, aggregate, scan và index access.
- Đánh giá đánh đổi giữa kết quả đếm chính xác, số liệu ước lượng và dữ liệu tổng hợp được duy trì.
- Kiểm chứng tính đúng đắn và hiệu năng trên dữ liệu, tham số và mức đồng thời đại diện.

## 1. Xác định chính xác câu hỏi nghiệp vụ

Trước khi viết SQL, hãy diễn đạt nhu cầu bằng một câu hỏi rõ ràng. Những câu hỏi sau không tương đương:

| Nhu cầu nghiệp vụ | Kết quả cần có | Phép toán thường phù hợp |
|---|---|---|
| Khách hàng có đơn hàng hay không? | Boolean hoặc có/không | EXISTS |
| Khách hàng chưa từng đặt hàng? | Boolean hoặc danh sách khách hàng | NOT EXISTS |
| Khách hàng có bao nhiêu đơn hàng? | Số nguyên chính xác | COUNT(*) |
| Có bao nhiêu email khác nhau? | Số lượng giá trị phân biệt | COUNT(DISTINCT email) |
| Mỗi khách hàng có bao nhiêu đơn hàng? | Một số đếm cho từng khách hàng | GROUP BY và COUNT |
| Có ít nhất 3 đơn hàng PAID? | Boolean theo ngưỡng | COUNT với điều kiện, hoặc EXISTS/logic giới hạn phù hợp |
| Trang danh sách còn bản ghi tiếp theo không? | Boolean | EXISTS hoặc truy vấn lấy tối đa một dòng |
| Có bao nhiêu đơn hàng trong tháng? | Số lượng chính xác theo khoảng | COUNT(*) với predicate thời gian |

Nếu chỉ cần trả lời có hoặc không, đếm tất cả các dòng phù hợp là công việc thừa. Nếu nghiệp vụ cần số lượng chính xác để tính hóa đơn, hạn mức hoặc báo cáo, EXISTS không cung cấp đủ thông tin. Nếu cần đếm thực thể duy nhất, COUNT(*) trên bảng quan hệ một-nhiều có thể đếm sai đối tượng.

Cần làm rõ thêm:

- Đếm dòng của bảng nào hay đếm thực thể nghiệp vụ nào?
- Có tính bản ghi đã hủy, đã xóa mềm hoặc hết hiệu lực không?
- NULL có được xem là một giá trị hay bị bỏ qua?
- Có tính trùng lặp không?
- Kết quả phải chính xác tại thời điểm truy vấn hay có thể chấp nhận số liệu gần đúng?
- Phạm vi thời gian và timezone được xác định thế nào?
- Cần kết quả trong một snapshot nhất quán hay chấp nhận dữ liệu thay đổi trong lúc xử lý?

Các câu hỏi này ảnh hưởng trực tiếp đến câu SQL, chỉ mục và cách kiểm thử.

## 2. Kiểm tra tồn tại bằng EXISTS

### 2.1. Cách viết cơ bản

EXISTS kiểm tra xem subquery có trả về ít nhất một dòng hay không. Giá trị các cột được chọn trong subquery không quan trọng; điều cần biết là có dòng thỏa điều kiện.

Ví dụ, kiểm tra khách hàng có đơn hàng:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Với mỗi khách hàng, DBMS kiểm tra có ít nhất một đơn hàng khớp customer_id hay không. Khi đã xác định được một dòng phù hợp, về mặt logic không cần đếm tiếp những dòng còn lại cho điều kiện EXISTS.

SELECT 1 là cách viết phổ biến vì thể hiện rằng chỉ kiểm tra sự tồn tại. SELECT * hoặc SELECT o.order_id cũng không làm EXISTS trả về thêm cột; semantics của EXISTS không phụ thuộc danh sách select trong subquery.

### 2.2. Vì sao EXISTS thường phù hợp hơn COUNT khi chỉ cần có/không?

Một cách viết khác là:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
) > 0;
~~~

Câu này yêu cầu tính số dòng phù hợp rồi mới so sánh với 0. EXISTS biểu đạt trực tiếp rằng chỉ cần biết có ít nhất một dòng. Optimizer có thể chuyển EXISTS thành semi-join hoặc dùng access path dừng sau khi tìm thấy một kết quả phù hợp.

Tuy nhiên, không nên khẳng định EXISTS luôn nhanh hơn COUNT trong mọi tình huống. Optimizer có thể biến đổi cả hai dạng; bảng có thể nhỏ; index, cache, thống kê và cách thực thi có thể làm chênh lệch không đáng kể. Lợi ích rõ nhất của EXISTS là biểu đạt đúng nhu cầu và cho phép DBMS tận dụng chiến lược kiểm tra tồn tại.

### 2.3. EXISTS và semi-join

Semi-join trả về dòng từ phía được kiểm tra nếu có ít nhất một dòng phù hợp ở phía còn lại. Nó không nhân bản dòng bên ngoài theo số lượng dòng khớp.

Ví dụ:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Nếu một khách hàng có 50 đơn PAID, khách hàng vẫn chỉ xuất hiện một lần. Đây là khác biệt quan trọng so với JOIN thông thường.

DBMS có thể hiển thị semi-join dưới dạng toán tử riêng, nested loop semi join, hash semi join hoặc một dạng kế hoạch tương đương. Tên gọi tùy sản phẩm. Khi đọc plan, hãy kiểm tra số dòng đầu ra và việc DBMS có phải xử lý toàn bộ các dòng khớp hay có thể dừng sau lần khớp đầu tiên.

### 2.4. EXISTS có thể tương quan với truy vấn ngoài

Subquery có tham chiếu đến cột của truy vấn ngoài được gọi là correlated subquery:

~~~sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE EXISTS (
    SELECT 1
    FROM order_items AS i
    WHERE i.product_id = p.product_id
);
~~~

Về mặt diễn đạt, điều kiện trong subquery phụ thuộc vào từng product. Nhưng điều đó không có nghĩa DBMS bắt buộc thực thi subquery như một truy vấn độc lập cho từng dòng. Optimizer có thể decorrelate và biến đổi thành semi-join hoặc plan tương đương.

Nếu plan thực tế cho thấy một inner lookup lặp lại nhiều lần, hãy xem số dòng ngoài, index trên order_items(product_id), actual loops và buffer reads. Với tập sản phẩm nhỏ và index tốt, nested loop semi-join có thể rất hiệu quả. Với tập dữ liệu lớn, hash semi-join hoặc cách thực hiện khác có thể phù hợp hơn.

## 3. Kiểm tra không tồn tại bằng NOT EXISTS

### 3.1. Cách viết cơ bản

NOT EXISTS kiểm tra subquery không trả về dòng nào thỏa điều kiện. Ví dụ, tìm khách hàng chưa từng có đơn hàng:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

DBMS cần xác định không có dòng phù hợp. Khi tìm thấy một dòng, điều kiện NOT EXISTS đã sai đối với khách hàng đó. Với khách hàng không có dòng phù hợp, DBMS cần xác minh hết phạm vi liên quan theo access path được chọn.

### 3.2. Anti-join

NOT EXISTS thường được tối ưu thành anti-join: giữ dòng từ phía ngoài nếu không có dòng khớp ở phía trong.

Anti-join có thể được thực hiện bằng nested loop, hash hoặc merge tùy DBMS và dữ liệu. Index trên khóa tra cứu ở phía trong thường giúp nested loop anti-join kiểm tra nhanh sự vắng mặt. Với hai tập dữ liệu lớn, hash anti-join hoặc merge anti-join có thể phù hợp hơn.

### 3.3. NOT EXISTS và NOT IN không luôn tương đương

Cần đặc biệt cẩn thận với NULL. Ví dụ:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Nếu subquery trả về ít nhất một NULL, phép NOT IN có thể cho kết quả UNKNOWN đối với các giá trị không khớp. WHERE chỉ giữ kết quả TRUE, vì vậy những khách hàng không có đơn hàng vẫn có thể bị loại ngoài dự kiến.

NOT EXISTS với điều kiện tương quan:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

không bị ảnh hưởng theo cùng cách bởi một NULL không liên quan ở phía orders. Phép so sánh o.customer_id = c.customer_id với NULL không trả TRUE, nên dòng đó không tạo ra match.

Nếu hai cột được bảo đảm NOT NULL, NOT IN và NOT EXISTS có thể cho cùng kết quả trong một số cấu trúc đơn giản. Nhưng không nên rewrite máy móc. Hãy kiểm tra nullable constraints, semantics và dữ liệu thực tế.

### 3.4. LEFT JOIN ... IS NULL

Một cách viết anti-join khác là:

~~~sql
SELECT c.customer_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

Cách này có thể tương đương với NOT EXISTS nếu order_id là cột không NULL của một dòng orders thực sự tồn tại, chẳng hạn khóa chính. Nếu kiểm tra một cột nullable như o.note IS NULL, truy vấn có thể nhầm một dòng orders có note NULL với trường hợp không có dòng khớp.

Vì vậy, nếu dùng LEFT JOIN ... IS NULL, hãy kiểm tra cột được dùng làm dấu hiệu match phải không NULL khi dòng tồn tại. NOT EXISTS thường diễn đạt ý định rõ hơn.

## 4. Đếm số dòng bằng COUNT

### 4.1. COUNT(*)

COUNT(*) đếm số dòng trong tập kết quả sau khi áp dụng FROM, JOIN và WHERE. Nó không loại bỏ dòng chỉ vì một cột có giá trị NULL.

~~~sql
SELECT COUNT(*) AS order_count
FROM orders
WHERE customer_id = 42
  AND status = 'PAID';
~~~

Nếu cần số đơn PAID của khách hàng, COUNT(*) thường là phép toán phù hợp. DBMS phải xác định số dòng thỏa điều kiện. Với index thích hợp, nó có thể đọc index entries thay vì toàn bộ row payload; khả năng và cách thực hiện phụ thuộc engine, visibility, predicate và plan.

### 4.2. COUNT(column)

COUNT(column) chỉ đếm những dòng mà biểu thức column không NULL:

~~~sql
SELECT COUNT(delivered_at) AS delivered_count,
       COUNT(*) AS all_order_count
FROM orders
WHERE customer_id = 42;
~~~

Nếu delivered_at NULL ở đơn chưa giao, COUNT(delivered_at) đếm đơn có thời điểm giao; COUNT(*) đếm mọi đơn của khách hàng. Hai kết quả có ý nghĩa khác nhau.

Không thay COUNT(column) bằng COUNT(*) nếu cột có thể NULL và nghiệp vụ muốn bỏ qua NULL. Ngược lại, nếu muốn đếm dòng, COUNT(*) thể hiện ý định rõ ràng và tránh phụ thuộc vào tính nullable của một cột.

### 4.3. COUNT(1) và COUNT(*)

COUNT(1) thường được dùng trong một số codebase cũ. Với biểu thức hằng 1, nó thường cho cùng kết quả với COUNT(*) vì biểu thức không NULL ở mọi dòng. Optimizer của các DBMS hiện đại thường xử lý hai dạng tương đương hoặc có chi phí tương tự.

COUNT(*) thường rõ nghĩa hơn khi mục tiêu là đếm dòng. Không nên kỳ vọng COUNT(1) nhanh hơn một cách đáng kể nếu chưa có phép đo chứng minh trên DBMS cụ thể.

### 4.4. Đếm theo nhóm

Để đếm số đơn của từng khách hàng:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id;
~~~

Nếu chỉ cần các khách hàng có ít nhất 3 đơn:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 3;
~~~

HAVING lọc nhóm sau khi aggregation. Nếu điều kiện lọc có thể áp dụng cho từng dòng trước khi nhóm, đặt ở WHERE để giảm đầu vào. Không chuyển HAVING COUNT(*) >= 3 thành WHERE; hai điều kiện không cùng ý nghĩa.

### 4.5. COUNT trong subquery tương quan

Ví dụ:

~~~sql
SELECT c.customer_id,
       (
           SELECT COUNT(*)
           FROM orders AS o
           WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers AS c;
~~~

Câu truy vấn yêu cầu số đơn cho từng khách hàng. Nếu customers có hàng triệu dòng và mỗi subquery thực hiện một lần lookup riêng, chi phí có thể lớn. Optimizer có thể decorrelate, nhưng cần xem plan.

Một dạng tổng hợp trước rồi join:

~~~sql
SELECT c.customer_id,
       COALESCE(x.order_count, 0) AS order_count
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS x
  ON x.customer_id = c.customer_id;
~~~

Dạng này có thể phù hợp khi cần đếm cho phần lớn khách hàng và có thể tổng hợp orders một lần. Nếu chỉ lấy 10 khách hàng, correlated count với index tốt có thể rẻ hơn nhiều so với nhóm toàn bộ orders. Quyết định phụ thuộc phạm vi truy vấn, index, số dòng và actual plan.

## 5. Đếm thực thể phân biệt bằng COUNT(DISTINCT)

### 5.1. Khi nào cần DISTINCT?

Giả sử mỗi đơn hàng có nhiều dòng chi tiết. Muốn đếm số sản phẩm khác nhau đã được đặt trong một khoảng thời gian:

~~~sql
SELECT COUNT(DISTINCT product_id) AS unique_products
FROM order_items
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at < TIMESTAMP '2026-12-01 00:00:00';
~~~

COUNT(*) sẽ đếm số dòng chi tiết; COUNT(DISTINCT product_id) đếm số giá trị product_id phân biệt, với semantics NULL của COUNT(DISTINCT expression) thường bỏ qua NULL. Cần xác nhận quy tắc này theo DBMS và biểu thức sử dụng.

### 5.2. COUNT(DISTINCT) có thể tốn kém

Để loại bỏ trùng, DBMS có thể dùng sort, hash aggregate hoặc thuật toán khác. Nếu số dòng đầu vào lớn hoặc số giá trị phân biệt cao, cấu trúc trung gian có thể tiêu tốn nhiều memory và spill ra storage.

Khi truy vấn COUNT(DISTINCT) chậm, hãy xem:

- Số dòng đầu vào sau filter.
- Số giá trị phân biệt ước lượng và thực tế.
- Hash aggregate hoặc sort operation.
- Memory grant và temp I/O.
- Có thể lọc sớm hơn không?
- Có index hỗ trợ điều kiện lọc và thứ tự khóa không?
- Có thể dùng bảng tổng hợp hoặc dữ liệu đã khử trùng lặp được duy trì không?

Không loại bỏ DISTINCT chỉ để tăng tốc nếu nghiệp vụ thực sự cần đếm thực thể duy nhất.

### 5.3. DISTINCT sau JOIN có thể che giấu fan-out

Ví dụ:

~~~sql
SELECT COUNT(DISTINCT c.customer_id)
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Truy vấn này đếm số khách hàng có đơn hàng. Nó có thể được viết trực tiếp bằng EXISTS:

~~~sql
SELECT COUNT(*)
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Dạng EXISTS tránh tạo các dòng customer lặp theo số đơn rồi mới khử trùng. Optimizer có thể đã chuyển đổi truy vấn JOIN DISTINCT thành semi-join, nhưng viết EXISTS thể hiện đúng nhu cầu. Cần đo plan và kết quả thực tế.

## 6. Tránh nhân bản dòng khi JOIN chỉ để kiểm tra tồn tại

Một lỗi thường gặp là dùng JOIN khi chỉ cần biết có bản ghi liên quan:

~~~sql
SELECT c.customer_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Nếu một khách hàng có 10 đơn PAID, customer_id có thể xuất hiện 10 lần. Nếu giao diện chỉ cần danh sách khách hàng, kết quả này vừa sai về số dòng mong muốn vừa tạo thêm công việc truyền dữ liệu hoặc phải khử trùng.

Có thể dùng:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Hoặc JOIN DISTINCT:

~~~sql
SELECT DISTINCT c.customer_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

EXISTS thường biểu đạt đúng mục tiêu hơn. DISTINCT có thể cần sort hoặc hash để loại trùng. Tuy nhiên, nếu query cần cột từ orders hoặc muốn trả mỗi quan hệ customer-order, JOIN vẫn là phép toán đúng. Không đổi JOIN thành EXISTS nếu cần tất cả cặp dòng.

### 6.1. Đếm quan hệ hay đếm thực thể?

Giả sử một khách hàng có 3 đơn, mỗi đơn có 4 dòng sản phẩm. Khi join customers, orders và order_items:

- COUNT(*) có thể đếm 12 dòng chi tiết.
- COUNT(o.order_id) có thể đếm 12 lần xuất hiện của đơn hàng sau join.
- COUNT(DISTINCT o.order_id) đếm 3 đơn.
- COUNT(DISTINCT c.customer_id) đếm 1 khách hàng.

Hãy xác định đơn vị nghiệp vụ cần đếm trước khi chọn biểu thức.

## 7. Kết hợp điều kiện và đếm theo ngưỡng

Một số nghiệp vụ chỉ cần biết số lượng có đạt ngưỡng hay không. Ví dụ khách hàng có ít nhất 3 đơn PAID.

Dạng đếm chính xác rồi so sánh:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
) >= 3;
~~~

Nếu chỉ cần kiểm tra đạt ngưỡng, có thể dùng truy vấn con giới hạn số dòng trong một số DBMS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    OFFSET 2 ROWS
);
~~~

Cú pháp OFFSET trong subquery không được hỗ trợ giống nhau ở mọi DBMS và optimizer không nhất thiết thực hiện theo cách dừng sớm mong muốn. Một dạng phổ biến khác là đếm trong derived table với LIMIT hoặc TOP để giới hạn tối đa số dòng cần xác nhận:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE (
    SELECT COUNT(*)
    FROM (
        SELECT 1
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
          AND o.status = 'PAID'
        LIMIT 3
    ) AS first_matches
) = 3;
~~~

Đây là cú pháp minh họa theo các DBMS hỗ trợ LIMIT trong derived table; SQL Server dùng TOP hoặc cú pháp tương ứng. Dạng này đếm tối đa 3 dòng và chỉ cần xác nhận đủ 3 dòng. Tuy nhiên, correlated derived table và khả năng decorrelation khác nhau theo optimizer. Hãy kiểm tra cú pháp và plan của DBMS đang sử dụng.

Nếu nghiệp vụ cần con số chính xác để hiển thị, hãy dùng COUNT đầy đủ. Nếu chỉ cần điều kiện ngưỡng, hãy thiết kế phép kiểm tra giới hạn và đo xem DBMS có dừng sớm hay không. Đừng làm phức tạp SQL nếu optimizer đã tối ưu được dạng COUNT.

## 8. Thiết kế chỉ mục cho EXISTS và NOT EXISTS

### 8.1. Index trên khóa tương quan

Với:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Index trên orders(customer_id) có thể giúp tìm nhanh ít nhất một đơn hàng của mỗi khách hàng. Với NOT EXISTS, index cũng giúp xác minh nhanh rằng không có dòng phù hợp.

Nếu bảng orders lớn và truy vấn còn lọc trạng thái:

~~~sql
WHERE o.customer_id = c.customer_id
  AND o.status = 'PAID'
~~~

có thể cân nhắc index ghép:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

Thứ tự cột nên dựa trên các truy vấn thực tế. Nếu nhiều truy vấn lọc customer_id và status bằng, cả hai cột đều tham gia equality prefix. Nếu có truy vấn chỉ lọc status, index bắt đầu bằng customer_id không nhất thiết hỗ trợ tốt truy vấn đó.

### 8.2. Index cho count theo khoảng

Ví dụ:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at < TIMESTAMP '2026-12-01 00:00:00';
~~~

Một index ghép trên (customer_id, created_at) có thể dùng equality trên customer_id rồi quét phạm vi created_at. Nếu truy vấn còn lọc status bằng equality, có thể thử (customer_id, status, created_at) tùy workload và thứ tự truy vấn khác.

Cột range thường đặt sau các cột equality trong B-tree ghép để tạo vùng khóa liên tục phù hợp. Đây là điểm khởi đầu, không phải quy tắc cứng cho mọi optimizer hoặc mọi truy vấn.

### 8.3. Index có thể giúp đếm nhưng không đảm bảo tránh đọc nhiều

COUNT(*) vẫn cần xác định chính xác số dòng thỏa predicate. Index có thể giảm lượng dữ liệu cần đọc, nhưng nếu điều kiện chọn 80% bảng, scan có thể rẻ hơn. Một index-only access có thể giảm truy cập bảng, nhưng điều kiện visibility, MVCC, cache và DBMS có thể vẫn cần đọc thêm dữ liệu.

Không nên kỳ vọng COUNT(*) luôn là O(1). Trong nhiều DBMS giao dịch, số dòng chính xác thay đổi liên tục và phải được tính theo snapshot hiện tại; hệ thống không thể luôn dùng một con số tổng lưu sẵn mà bảo đảm đúng.

### 8.4. Partial hoặc filtered index

Nếu truy vấn luôn kiểm tra một tập con nhỏ, partial/filtered index có thể hữu ích ở DBMS hỗ trợ:

~~~sql
-- Ví dụ PostgreSQL.
CREATE INDEX idx_orders_paid_customer
ON orders (customer_id)
WHERE status = 'PAID';
~~~

Index này chỉ chứa các đơn PAID. Nó có thể giảm kích thước index và hỗ trợ EXISTS hoặc COUNT cho predicate phù hợp. Nhưng dòng chuyển trạng thái vào hoặc ra khỏi tập PAID làm index phải cập nhật. Cũng cần bảo đảm optimizer chứng minh được predicate truy vấn tương thích với predicate của index.

## 9. Đọc execution plan cho existence check và count

### 9.1. Những toán tử thường gặp

Tên node thay đổi theo DBMS, nhưng có thể gặp các dạng:

| Dạng plan | Ý nghĩa cần xem |
|---|---|
| Semi Join | Giữ dòng phía ngoài nếu có ít nhất một dòng khớp |
| Anti Join | Giữ dòng phía ngoài nếu không có dòng khớp |
| Nested Loop | Lặp lookup theo từng dòng ngoài |
| Hash Join / Hash Semi Join | Xây dựng hash table rồi kiểm tra match |
| Index Seek/Scan | Tìm hoặc quét vùng khóa trong index |
| Aggregate / Hash Aggregate | Tính COUNT hoặc nhóm dữ liệu |
| Sort / Unique | Sắp xếp hoặc loại bỏ dòng trùng |
| Filter | Lọc sau khi dữ liệu đã được đọc hoặc nối |

### 9.2. Với EXISTS

Kiểm tra:

- DBMS có chọn semi-join hoặc access path tương đương không?
- Có index trên cột tương quan không?
- Số dòng outer và số loops là bao nhiêu?
- Inner lookup có dừng sau match hay xử lý nhiều dòng?
- Buffer reads và actual rows có phù hợp với kỳ vọng không?
- Predicate status hoặc thời gian có được áp dụng gần scan không?

Nếu outer input rất lớn, nested loop semi-join có thể tạo nhiều lookup. Hash semi-join có thể tốt hơn nếu cả hai tập lớn. Kết quả phụ thuộc cardinality và cache.

### 9.3. Với NOT EXISTS

Kiểm tra anti-join, index ở phía trong và phân bố dòng không khớp. Các trường hợp không có match có thể phải dò hết vùng khóa liên quan. Index phù hợp giúp xác nhận vắng mặt mà không scan toàn bảng.

### 9.4. Với COUNT

Kiểm tra:

- Aggregate xử lý bao nhiêu dòng đầu vào?
- Có scan bảng hay index?
- Có index-only access hoặc covering access không?
- Có sort/hash để DISTINCT không?
- Có spill hoặc temp I/O không?
- Estimated rows và actual rows có sai lệch lớn không?
- Predicate có được pushdown và partition pruning không?

Một COUNT trả về một dòng vẫn có thể đọc hàng triệu dòng. Kích thước kết quả không đại diện cho lượng công việc.

### 9.5. Ví dụ PostgreSQL

Có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Với COUNT:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM orders
WHERE customer_id = 42
  AND status = 'PAID';
~~~

Quan sát actual rows, loops, buffers, scan type, aggregate node và thời gian. EXPLAIN ANALYZE thực thi truy vấn và tạo tải thật; chỉ chạy trong môi trường phù hợp. Với câu lệnh ghi, có thể tạo thay đổi dữ liệu.

### 9.6. Ví dụ MySQL

MySQL 8.0.18 trở lên hỗ trợ EXPLAIN ANALYZE cho truy vấn SELECT:

~~~sql
EXPLAIN ANALYZE
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Iterator tree có thể cho biết số dòng, thời gian và loops. Dùng thêm EXPLAIN dạng JSON hoặc truyền thống để kiểm tra key và access type. Cú pháp và các chỉ số phụ thuộc phiên bản.

## 10. Đếm chính xác, ước lượng và số liệu được duy trì

### 10.1. Khi nào cần COUNT chính xác?

COUNT chính xác phù hợp khi kết quả ảnh hưởng trực tiếp đến nghiệp vụ, ví dụ:

- Số lượng hàng tồn hoặc số đơn cần đối soát.
- Số lần sử dụng còn lại của hạn mức.
- Số bản ghi phải xử lý trong một transaction hoặc batch.
- Báo cáo tài chính hoặc kiểm soát yêu cầu độ chính xác.
- Điều kiện nghiệp vụ mà sai lệch một đơn vị cũng quan trọng.

Nếu bảng lớn và truy vấn COUNT chạy thường xuyên, chi phí tính chính xác có thể đáng kể. Hãy xác định có thực sự cần đếm lại toàn bộ tại mỗi request hay không.

### 10.2. Ước lượng số dòng

Một số DBMS lưu thống kê số dòng hoặc cardinality ước lượng. Đây có thể là lựa chọn nhanh cho dashboard hoặc công cụ quản trị khi sai số được chấp nhận. Nhưng số ước lượng có thể cũ, lấy mẫu hoặc không phản ánh snapshot hiện tại.

Không dùng row estimate để quyết định nghiệp vụ cần độ chính xác. Ghi rõ đó là số ước lượng và thời điểm thống kê.

### 10.3. Counter hoặc summary table

Nếu ứng dụng cần số đếm thường xuyên, có thể duy trì counter hoặc bảng tổng hợp thay vì chạy COUNT trên dữ liệu chi tiết mỗi lần.

Ví dụ bảng customer_order_summary lưu customer_id và order_count. Khi thêm hoặc xóa đơn, ứng dụng hoặc cơ chế đồng bộ cập nhật counter tương ứng.

Lợi ích:

- Đọc số đếm nhanh, thường là point lookup.
- Giảm scan và aggregation lặp lại.
- Có thể hỗ trợ dashboard có tần suất đọc cao.

Chi phí và rủi ro:

- Mọi thay đổi dữ liệu gốc phải cập nhật summary chính xác.
- Cập nhật counter có thể tạo hot row và lock contention.
- Retry, rollback, event duplication hoặc xử lý bất đồng bộ có thể làm lệch số đếm.
- Cần cơ chế reconcile định kỳ so sánh summary với dữ liệu gốc.
- Transaction và thứ tự cập nhật phải được thiết kế rõ.

Không duy trì counter nếu lợi ích đọc không bù được độ phức tạp ghi và đồng bộ.

### 10.4. Materialized view và aggregation theo lịch

Một số DBMS hỗ trợ materialized view hoặc bảng aggregate được làm mới theo lịch. Đây là lựa chọn phù hợp cho báo cáo chấp nhận độ trễ dữ liệu nhất định.

Cần xác định:

- Độ trễ cập nhật cho phép.
- Refresh toàn bộ hay incremental.
- Chi phí refresh và ảnh hưởng workload.
- Cách xử lý bản ghi mới, cập nhật và xóa.
- Quy tắc nhất quán khi người dùng đọc trong lúc refresh.

Nếu yêu cầu số đếm phải phản ánh transaction mới nhất, dữ liệu tổng hợp làm mới theo lịch có thể không đáp ứng.

## 11. Kiểm tra tồn tại không thay thế ràng buộc dữ liệu

Một lỗi thiết kế phổ biến là kiểm tra trước rồi mới ghi:

~~~sql
SELECT 1
FROM users
WHERE email = 'user@example.test';

-- Nếu chưa có, ứng dụng thực hiện INSERT.
~~~

Hai transaction đồng thời có thể cùng kiểm tra và đều thấy chưa có dòng, sau đó cùng INSERT. Đây là race condition. Truy vấn EXISTS hoặc COUNT không bảo đảm tính duy nhất giữa thời điểm kiểm tra và thời điểm ghi.

Nếu nghiệp vụ yêu cầu email duy nhất, hãy dùng UNIQUE constraint hoặc unique index làm cơ chế bảo vệ cuối cùng:

~~~sql
ALTER TABLE users
ADD CONSTRAINT uq_users_email UNIQUE (email);
~~~

Ứng dụng có thể thực hiện INSERT và xử lý lỗi vi phạm unique constraint, hoặc dùng cú pháp upsert phù hợp DBMS. Một kiểm tra EXISTS trước khi ghi có thể giúp hiển thị thông báo sớm, nhưng không thay thế constraint.

Tương tự, nếu nghiệp vụ yêu cầu không vượt hạn mức hoặc không đặt quá số lượng tồn, chỉ đọc COUNT rồi quyết định ghi có thể bị race khi nhiều transaction cùng chạy. Cần dùng khóa, cập nhật có điều kiện, isolation phù hợp hoặc cơ chế kiểm soát đồng thời được DBMS hỗ trợ.

## 12. Tính nhất quán của COUNT dưới tải đồng thời

COUNT được thực hiện trên một snapshot theo isolation level và cơ chế MVCC/locking của DBMS. Trong khi truy vấn đang chạy, transaction khác có thể thêm hoặc xóa dòng. Kết quả phản ánh tập dữ liệu mà transaction hiện tại được phép nhìn thấy, không nhất thiết là tổng số dòng tại thời điểm client nhận kết quả.

Cần hiểu:

- READ COMMITTED có thể cho snapshot mới ở mỗi statement trong một số DBMS.
- REPEATABLE READ hoặc SNAPSHOT có thể giữ snapshot nhất quán lâu hơn.
- SERIALIZABLE có thể tăng khả năng chờ hoặc retry để bảo đảm các tính chất mạnh hơn.
- Các DBMS khác nhau có semantics isolation và phantom handling khác nhau.

Nếu ứng dụng chạy COUNT rồi chạy SELECT trang dữ liệu trong hai statement, số đếm và trang kết quả có thể phản ánh hai snapshot khác nhau tùy isolation. Nếu cần đồng bộ, hãy dùng transaction/isolation phù hợp và chấp nhận chi phí đi kèm.

Không dùng COUNT làm khóa logic để ngăn hai transaction cùng thao tác một tài nguyên nếu chưa có cơ chế đồng thời bảo đảm.

## 13. Tối ưu mẫu truy vấn theo nhu cầu giao diện

### 13.1. Chỉ cần biết trang tiếp theo có tồn tại

Một giao diện phân trang có thể cần biết còn dữ liệu sau trang hiện tại hay không. Không cần COUNT toàn bộ bảng. Có thể truy vấn lấy tối đa một dòng sau khóa cuối:

~~~sql
SELECT 1
FROM orders
WHERE customer_id = 42
  AND order_id > 830154
LIMIT 1;
~~~

Cú pháp LIMIT phổ biến ở PostgreSQL và MySQL; SQL Server dùng TOP hoặc FETCH tương ứng. Với index phù hợp trên customer_id và order_id, DBMS có thể dừng sau khi tìm được một dòng.

Một cách khác là lấy page_size + 1 dòng. Nếu nhận được nhiều hơn page_size, ứng dụng biết còn trang tiếp theo mà không cần COUNT tổng. Cách này thường phù hợp cho keyset pagination.

### 13.2. Hiển thị tổng số kết quả

Nếu giao diện thực sự cần tổng số kết quả, COUNT chính xác có thể cần đọc toàn bộ tập dòng phù hợp. Cần quyết định có nên hiển thị:

- Tổng chính xác.
- Số gần đúng.
- Một nhãn như “hơn 1.000 kết quả”.
- Chỉ trạng thái còn trang tiếp theo.

Việc chọn trải nghiệm sản phẩm có thể giảm đáng kể tải cơ sở dữ liệu mà không làm mất thông tin cần thiết cho người dùng.

### 13.3. Tránh N+1 existence/count queries

Nếu danh sách có 100 khách hàng và ứng dụng chạy thêm một EXISTS hoặc COUNT cho từng khách hàng, sẽ tạo 100 round-trip. Có thể dùng một truy vấn tổng hợp cho cả tập:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id IN (101, 102, 103, 104)
GROUP BY customer_id;
~~~

Ứng dụng ghép kết quả vào danh sách khách hàng; khách hàng không xuất hiện trong kết quả có thể được gán số 0. Với tập khóa lớn, dùng bảng tạm, table-valued parameter, array binding hoặc cơ chế phù hợp DBMS thay vì tạo một IN list quá lớn.

Nếu chỉ cần cờ có đơn hàng, có thể dùng SELECT DISTINCT customer_id từ tập orders phù hợp hoặc semi-join. Cần xem kích thước tập đầu vào và plan để chọn dạng tốt.

## 14. Quy trình đo và kiểm chứng

### Bước 1: Ghi rõ yêu cầu nghiệp vụ

Xác định đang cần có/không, số dòng, số giá trị phân biệt, số dòng theo nhóm hay số đếm đạt ngưỡng. Ghi rõ NULL, duplicate, thời gian và yêu cầu nhất quán.

### Bước 2: Ghi nhận baseline

Thu SQL, query fingerprint, số lần chạy, latency, p95/p99, rows read, buffer reads, CPU, I/O và execution plan. Với truy vấn tương quan, ghi số dòng outer và số loops.

### Bước 3: Chọn mẫu SQL đúng

- EXISTS cho kiểm tra có ít nhất một dòng.
- NOT EXISTS cho kiểm tra không có dòng phù hợp.
- COUNT(*) cho số dòng.
- COUNT(column) cho số dòng có biểu thức không NULL.
- COUNT(DISTINCT ...) cho số giá trị phân biệt.
- GROUP BY để đếm theo nhóm.
- Semi-join để tránh nhân bản dòng khi chỉ kiểm tra match.

### Bước 4: Kiểm tra semantics

Tạo dữ liệu kiểm thử có:

- Không có dòng khớp.
- Một dòng khớp.
- Nhiều dòng khớp.
- Join key NULL nếu được phép.
- Cột đếm NULL và non-NULL.
- Duplicate key.
- Bản ghi bị xóa mềm hoặc trạng thái không còn hiệu lực.
- Giá trị ở biên thời gian.

So sánh kết quả và số lần xuất hiện của từng dòng, không chỉ so tập giá trị đã loại trùng.

### Bước 5: Kiểm tra index và execution plan

Xem index trên cột tương quan, predicate lọc và phạm vi thời gian. Đọc semi-join/anti-join, aggregate, scan, actual rows, loops, sort/hash và buffer reads. Kiểm tra estimated rows với actual rows.

### Bước 6: Benchmark trên tham số đại diện

Dùng khách hàng nhỏ/lớn, trạng thái phổ biến/hiếm, khoảng thời gian ngắn/dài và concurrency gần production. Đo p50/p95/p99, throughput và tài nguyên.

### Bước 7: Đánh giá tác động toàn workload

Một index thêm vào để tăng tốc EXISTS hoặc COUNT cũng làm tăng chi phí ghi. Kiểm tra INSERT/UPDATE/DELETE, log bytes, cache pressure, lock wait và các truy vấn khác trên cùng bảng.

### Bước 8: Theo dõi và điều chỉnh

Sau khi triển khai, theo dõi query digest và counter trong khoảng thời gian đủ dài. Nếu số liệu đếm được cache hoặc duy trì ở summary table, kiểm tra tính nhất quán và cơ chế reconcile.

## 15. Ví dụ xuyên suốt: quản lý đơn hàng

Giả sử hệ thống cần hỗ trợ bốn chức năng:

1. Hiển thị khách hàng đã từng mua hàng hay chưa.
2. Hiển thị chính xác số đơn PAID của khách hàng.
3. Tìm khách hàng chưa có đơn trong 90 ngày.
4. Hiển thị số khách hàng duy nhất đã mua trong tháng.

Các truy vấn có thể là:

~~~sql
-- 1. Có ít nhất một đơn hàng?
SELECT EXISTS (
    SELECT 1
    FROM orders
    WHERE customer_id = 42
);

-- 2. Đếm số đơn PAID chính xác.
SELECT COUNT(*)
FROM orders
WHERE customer_id = 42
  AND status = 'PAID';

-- 3. Khách hàng không có đơn trong 90 ngày.
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.created_at >= CURRENT_TIMESTAMP - INTERVAL '90 days'
      AND o.created_at < CURRENT_TIMESTAMP
);

-- 4. Đếm khách hàng duy nhất đã mua trong tháng.
SELECT COUNT(DISTINCT customer_id)
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at < TIMESTAMP '2026-12-01 00:00:00'
  AND status = 'PAID';
~~~

Cú pháp INTERVAL và biểu thức thời gian có thể khác giữa DBMS; ví dụ trên dùng cú pháp kiểu PostgreSQL. Với MySQL hoặc SQL Server, hãy dùng hàm và cú pháp khoảng thời gian phù hợp. Khi dùng CURRENT_TIMESTAMP, xác định timezone và thời điểm đánh giá để các lần chạy có semantics nhất quán.

Biểu thức SELECT EXISTS ở ví dụ đầu phù hợp với PostgreSQL và MySQL. Trong SQL Server, có thể biểu đạt giá trị boolean bằng CASE WHEN EXISTS (...) THEN 1 ELSE 0 END, hoặc dùng EXISTS trực tiếp trong mệnh đề WHERE.

Các index có thể được đánh giá:

- orders(customer_id) cho kiểm tra tồn tại theo khách hàng.
- orders(customer_id, status) hoặc orders(customer_id, status, created_at) cho đếm đơn PAID và kiểm tra khoảng thời gian.
- Index trên created_at/status/customer_id có thể phục vụ báo cáo toàn hệ thống theo tháng, nhưng thứ tự cột phải dựa trên workload thực tế.

Không nên tạo cả ba index ngay lập tức. Xem index hiện có, tần suất truy vấn, selectivity, kích thước bảng và chi phí ghi. Với truy vấn đếm khách hàng duy nhất theo tháng, có thể cần đọc nhiều dòng; index không chắc loại bỏ được chi phí DISTINCT.

## 16. Những sai lầm thường gặp

**Dùng COUNT(*) > 0 để kiểm tra tồn tại.** Điều này yêu cầu diễn đạt và có thể thực hiện nhiều công việc hơn cần thiết. EXISTS thể hiện ý định trực tiếp.

**Dùng JOIN để kiểm tra có bản ghi liên quan.** JOIN có thể nhân bản dòng khi có nhiều bản ghi khớp. Dùng EXISTS nếu chỉ cần xác nhận có ít nhất một dòng.

**Thay COUNT(*) bằng COUNT(column).** Nếu column có NULL, kết quả thay đổi.

**Dùng COUNT(*) thay cho COUNT(DISTINCT entity_id).** JOIN một-nhiều có thể làm số đếm tăng theo số dòng con.

**Rewrite NOT IN thành NOT EXISTS mà không kiểm tra NULL.** Semantics có thể khác, đặc biệt khi subquery chứa NULL.

**Cho rằng EXISTS luôn dừng ngay sau một dòng trong mọi plan.** Optimizer có thể biến đổi truy vấn và access path; cần xem actual plan.

**Đếm chính xác cho mọi request giao diện.** Nhiều màn hình chỉ cần biết còn trang tiếp theo hoặc số lượng gần đúng.

**Dùng COUNT để bảo đảm tính duy nhất hoặc hạn mức dưới concurrency.** Kiểm tra rồi ghi có thể gặp race condition; cần constraint hoặc cơ chế giao dịch phù hợp.

**Tạo index cho mọi COUNT.** COUNT có thể cần đọc phần lớn dữ liệu; index không luôn rẻ hơn scan.

**Không đo tác động của index lên ghi.** Index hỗ trợ existence/count vẫn cần được duy trì khi dữ liệu thay đổi.

## 17. Checklist lựa chọn và tối ưu existence/count

- [ ] Đã xác định cần boolean, số dòng, số giá trị phân biệt hay số lượng theo nhóm chưa?
- [ ] Đã xác định chính xác thực thể cần đếm chưa?
- [ ] Đã kiểm tra NULL và duplicate semantics chưa?
- [ ] Đã dùng EXISTS/NOT EXISTS khi chỉ cần kiểm tra có hoặc không chưa?
- [ ] Đã tránh JOIN nhân bản dòng khi chỉ cần existence chưa?
- [ ] Đã chọn COUNT(*), COUNT(column) hoặc COUNT(DISTINCT ...) đúng mục đích chưa?
- [ ] Đã kiểm tra NOT IN và khả năng subquery trả về NULL chưa?
- [ ] Đã xem index trên cột tương quan và predicate lọc chưa?
- [ ] Đã đọc actual plan, loops, aggregate, sort/hash và buffer reads chưa?
- [ ] Đã đo với tham số phổ biến, hiếm và dữ liệu skew chưa?
- [ ] Đã đánh giá COUNT chính xác có thật sự cần cho giao diện/nghiệp vụ không?
- [ ] Nếu dùng counter hoặc summary table, đã có cơ chế đồng bộ và reconcile chưa?
- [ ] Đã xem xét race condition và constraint cho quy tắc duy nhất/hạn mức chưa?
- [ ] Đã benchmark tải đọc/ghi hỗn hợp và concurrency chưa?

## Kết luận

Truy vấn kiểm tra tồn tại và truy vấn đếm phục vụ những nhu cầu khác nhau. EXISTS và NOT EXISTS phù hợp khi chỉ cần biết có hay không có dòng liên quan; COUNT(*) đếm dòng; COUNT(column) bỏ qua NULL; COUNT(DISTINCT ...) đếm giá trị phân biệt. JOIN thông thường có thể nhân bản dòng, vì vậy không nên dùng nó chỉ để kiểm tra tồn tại nếu semi-join biểu đạt đúng yêu cầu hơn.

Hiệu năng phụ thuộc điều kiện tương quan, index, selectivity, cardinality, duplicate, NULL, cache và execution plan. COUNT chính xác có thể phải đọc toàn bộ tập dòng phù hợp; số liệu ước lượng hoặc summary table chỉ phù hợp khi nghiệp vụ chấp nhận sai số hoặc độ trễ cập nhật. Hãy xác định đúng đơn vị cần kiểm tra/đếm, bảo toàn semantics, đọc actual plan và đo trên workload đại diện. Với quy tắc cần đúng dưới concurrency, hãy dùng constraint và cơ chế giao dịch phù hợp thay vì dựa vào một lần kiểm tra COUNT hoặc EXISTS.

