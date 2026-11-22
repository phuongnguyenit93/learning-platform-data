# Đẩy điều kiện lọc, loại bỏ phép tính thừa và biến đổi truy vấn tương đương

Một câu SQL có thể trả về đúng kết quả nhưng vẫn buộc cơ sở dữ liệu đọc, tính toán và truyền nhiều dữ liệu hơn mức cần thiết. Truy vấn có thể lọc dữ liệu quá muộn, tính cùng một biểu thức nhiều lần, nối một bảng chỉ để kiểm tra sự tồn tại, hoặc thực hiện các bước trung gian không cần thiết. Những công việc dư thừa này làm tăng CPU, I/O, bộ nhớ, thời gian giữ khóa và độ trễ.

Trong chương **Bộ tối ưu truy vấn**, bài học này tập trung vào ba nhóm kỹ thuật: đẩy điều kiện lọc đến gần nguồn dữ liệu, loại bỏ phép tính hoặc thao tác không cần thiết, và biến đổi câu SQL thành dạng tương đương nhưng có khả năng tạo kế hoạch thực thi tốt hơn. Đây là phương pháp phục vụ mục tiêu của module **DATABASE_PERFORMANCE**: tối ưu hiệu năng dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu.

Một phép rewrite chỉ có giá trị khi vẫn giữ nguyên kết quả theo ngữ nghĩa SQL và tạo ra lợi ích có thể đo được. Vì vậy, bài học luôn đi cùng hai câu hỏi: phép biến đổi có tương đương trong mọi trường hợp liên quan không, và execution plan sau biến đổi có thực sự giảm công việc không?

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích predicate pushdown và lý do lọc dữ liệu sớm thường giảm chi phí xử lý.
- Nhận diện điều kiện lọc có thể tận dụng chỉ mục, partition pruning hoặc access path khác.
- Viết lại biểu thức để tránh hàm hoặc phép chuyển kiểu không cần thiết trên cột được lọc.
- Loại bỏ phép tính lặp, cột không dùng, phép nối thừa và truy vấn con không cần thiết.
- Chọn cách viết JOIN, EXISTS, IN hoặc UNION phù hợp mà vẫn bảo toàn số dòng và ngữ nghĩa NULL.
- Nhận diện các trường hợp rewrite dễ làm thay đổi kết quả như outer join, NULL, duplicate rows, LIMIT, aggregate và thứ tự sắp xếp.
- Kiểm chứng phép biến đổi bằng dữ liệu đại diện, execution plan và số đo trước/sau.

## 1. Tư duy tối ưu: giảm công việc trước khi tăng tài nguyên

Khi một truy vấn chậm, phản xạ đầu tiên đôi khi là thêm chỉ mục hoặc tăng bộ nhớ. Nhưng nếu truy vấn đang xử lý quá nhiều dòng hoặc tính toán lặp lại, cách hiệu quả hơn có thể là loại bỏ công việc không cần thiết ngay trong cấu trúc SQL.

Một truy vấn thường trải qua các thao tác như scan, filter, join, projection, sort và aggregate. Mỗi thao tác có thể tạo ra một tập dữ liệu trung gian. Nếu một bộ lọc chỉ giữ lại 1% dữ liệu nhưng được thực hiện sau một phép join lớn, DBMS có thể phải xử lý nhiều dòng hơn cần thiết. Nếu truy vấn lấy tất cả cột nhưng ứng dụng chỉ dùng hai cột, dữ liệu truyền và bộ nhớ trung gian có thể tăng không cần thiết.

Có thể hình dung nguyên tắc tổng quát:

~~~text
Nguồn dữ liệu
    |
    v
Lọc sớm các dòng không cần thiết
    |
    v
Chỉ giữ các cột cần dùng
    |
    v
Thực hiện join / tính toán trên tập dữ liệu nhỏ hơn
    |
    v
Sắp xếp hoặc tổng hợp phần dữ liệu còn lại
    |
    v
Trả kết quả
~~~

Đây là định hướng logic. Optimizer có thể tự di chuyển filter, loại bỏ projection thừa hoặc thay đổi thứ tự join. Người viết SQL vẫn cần tạo ra câu lệnh rõ ràng, tránh cản trở các phép biến đổi hợp lệ và kiểm tra xem optimizer đã chọn kế hoạch tốt chưa.

## 2. Đẩy điều kiện lọc (predicate pushdown)

### 2.1. Predicate là gì?

Predicate là biểu thức điều kiện trả về TRUE, FALSE hoặc UNKNOWN theo logic ba giá trị của SQL. Điều kiện trong WHERE, HAVING và ON là các ví dụ thường gặp.

~~~sql
SELECT order_id, customer_id, total
FROM orders
WHERE status = 'PAID'
  AND created_at >= DATE '2026-11-01';
~~~

Hai điều kiện trong WHERE là predicate. Chúng xác định dòng nào được giữ lại.

Predicate pushdown là việc đưa điều kiện lọc đến gần nguồn dữ liệu nhất có thể, để giảm số dòng đi qua các toán tử phía sau. Tùy cấu trúc truy vấn, điều kiện có thể được đẩy vào subquery, derived table, view, scan hoặc phía đầu vào của phép join.

### 2.2. Vì sao lọc sớm có ích?

Giả sử bảng orders có 10 triệu dòng, trong đó chỉ 100.000 dòng thuộc trạng thái PAID. Một truy vấn cần kết hợp orders với order_items. Nếu lọc PAID trước khi join, đầu vào của phép join có thể giảm đáng kể.

Minh họa về mặt logic:

~~~sql
-- Cách viết thể hiện việc lấy tập đơn hàng phù hợp trước.
SELECT o.order_id, i.product_id, i.quantity
FROM (
    SELECT order_id
    FROM orders
    WHERE status = 'PAID'
) AS paid_orders
JOIN order_items AS i
  ON i.order_id = paid_orders.order_id;
~~~

Câu truy vấn này chỉ lấy order_id từ tập đơn hàng đã lọc rồi mới nối với order_items. Optimizer có thể tự thực hiện phép đẩy điều kiện tương tự ngay cả khi SQL được viết theo dạng khác.

Lợi ích có thể gồm:

- Ít dòng đầu vào hơn cho join, sort và aggregate.
- Ít trang dữ liệu phải đọc nếu predicate dùng được index hoặc partition pruning.
- Ít bộ nhớ cần cho hash table hoặc dữ liệu trung gian.
- Ít dòng phải truyền giữa các toán tử hoặc qua mạng trong truy vấn phân tán.
- Giảm khả năng spill dữ liệu tạm ra storage.

Tuy nhiên, lọc sớm không luôn làm truy vấn nhanh hơn. Nếu điều kiện chọn phần lớn bảng, DBMS có thể vẫn cần scan. Nếu việc tách subquery khiến một hệ quản trị vật hóa dữ liệu trung gian, chi phí có thể tăng. Hãy xem execution plan thực tế.

### 2.3. Predicate pushdown qua derived table và view

Một truy vấn có thể bọc bảng trong derived table hoặc view:

~~~sql
SELECT *
FROM (
    SELECT order_id, customer_id, status, total
    FROM orders
) AS order_view
WHERE status = 'PAID';
~~~

Về mặt ngữ nghĩa, điều kiện status có thể được đẩy vào truy vấn bên trong vì derived table không thay đổi tập dòng. Optimizer thường có thể flatten hoặc merge truy vấn con như vậy.

Nhưng không phải mọi view hoặc subquery đều có thể được flatten. DISTINCT, GROUP BY, window function, LIMIT, OFFSET, set operation, materialization hint hoặc đặc tính riêng của DBMS có thể giới hạn phép biến đổi. Trong một số trường hợp, predicate đặt bên ngoài sẽ lọc sau khi dữ liệu trung gian đã được tạo.

Khi nghi ngờ filter chưa được đẩy xuống, kiểm tra plan để xem điều kiện xuất hiện ở scan hay ở một Filter node phía trên. Đừng chỉ dựa vào vị trí câu WHERE trong văn bản SQL.

## 3. Đẩy điều kiện qua phép JOIN

### 3.1. INNER JOIN

Với INNER JOIN, một điều kiện chỉ tham chiếu đến một phía của phép nối thường có thể được áp dụng cho phía đó trước khi join mà vẫn giữ kết quả.

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.region = 'NORTH';
~~~

Điều kiện c.region = 'NORTH' chỉ phụ thuộc vào customers. DBMS có thể lọc customers trước, sau đó mới join với orders. Việc này có thể giảm số dòng phía đầu vào.

Viết điều kiện ngay trong derived table đôi khi làm ý định dễ đọc hơn:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN (
    SELECT customer_id, customer_name
    FROM customers
    WHERE region = 'NORTH'
) AS c
  ON c.customer_id = o.customer_id;
~~~

Hai cách viết có thể tạo cùng kết quả và cùng kế hoạch. Nếu optimizer đã push predicate, viết thêm subquery không đem lại lợi ích. Hãy giữ dạng SQL dễ bảo trì trừ khi plan chứng minh có vấn đề.

### 3.2. LEFT JOIN và điều kiện ở ON hoặc WHERE

Với outer join, vị trí điều kiện có thể thay đổi kết quả. Đây là một trong những lỗi rewrite phổ biến nhất.

Giả sử cần liệt kê mọi khách hàng, kèm đơn hàng PAID nếu có:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
~~~

Điều kiện status trong ON giới hạn những dòng orders được ghép. Khách hàng không có đơn PAID vẫn xuất hiện với các cột orders là NULL.

Nếu chuyển điều kiện sang WHERE:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Các dòng không có đơn hàng có o.status = NULL; predicate trả về UNKNOWN và bị loại. Truy vấn lúc này thường có kết quả tương đương INNER JOIN đối với điều kiện đó, nên khách hàng không có đơn PAID biến mất.

Quy tắc thực hành:

- Điều kiện giới hạn dòng được ghép ở phía nullable của outer join thường cần đặt trong ON nếu vẫn muốn giữ dòng bên trái không có kết quả khớp.
- Điều kiện WHERE lọc kết quả sau join và có thể loại bỏ dòng đã được bổ sung NULL.
- Chỉ di chuyển predicate qua outer join khi đã chứng minh tính tương đương theo NULL và logic ba giá trị.

### 3.3. Điều kiện tham chiếu cả hai phía

Một predicate tham chiếu cột từ cả hai bảng thường chỉ có thể đánh giá sau khi có giá trị từ cả hai phía, ví dụ:

~~~sql
SELECT o.order_id, i.product_id
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE i.quantity > o.minimum_quantity;
~~~

Có thể đẩy các predicate độc lập của từng bảng xuống trước join, nhưng điều kiện so sánh i.quantity với o.minimum_quantity cần cả hai phía. Optimizer có thể tận dụng các điều kiện join hoặc constraint để suy luận thêm điều kiện lọc, nhưng phải bảo toàn kết quả.

## 4. Đẩy điều kiện vào truy vấn con và phép tổng hợp

### 4.1. WHERE và HAVING có vai trò khác nhau

WHERE lọc dòng trước aggregation; HAVING lọc nhóm sau aggregation.

~~~sql
SELECT customer_id, SUM(total) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(total) > 100000;
~~~

Ở đây, status = 'PAID' có thể lọc từng dòng trước khi nhóm. Điều kiện SUM(total) > 100000 cần kết quả tổng hợp của từng nhóm nên được đánh giá sau aggregation.

Không thể thay mọi điều kiện HAVING bằng WHERE. Ví dụ:

~~~sql
-- Lọc nhóm có doanh thu lớn hơn 100000.
HAVING SUM(total) > 100000
~~~

Không tương đương với việc lọc các đơn hàng có total > 100000 trước khi tính tổng. Hai điều kiện mô tả hai tập dữ liệu khác nhau.

### 4.2. Đẩy điều kiện trên khóa nhóm

Một predicate chỉ tham chiếu đến cột nhóm có thể trong nhiều trường hợp được chuyển từ HAVING xuống WHERE:

~~~sql
-- Dạng lọc sau khi nhóm
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING customer_id = 42;
~~~

Có thể viết:

~~~sql
-- Dạng lọc trước khi nhóm
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id = 42
GROUP BY customer_id;
~~~

Vì customer_id là khóa nhóm, mọi dòng trong nhóm đều có cùng giá trị đó. Việc lọc trước aggregation giảm số dòng cần xử lý. Optimizer thường có thể tự thực hiện phép biến đổi này.

### 4.3. Aggregation và điều kiện trên dữ liệu gốc

Với truy vấn tổng hợp, lọc sớm thường giúp giảm đầu vào:

~~~sql
SELECT customer_id, SUM(total) AS revenue
FROM orders
WHERE created_at >= DATE '2026-11-01'
  AND created_at < DATE '2026-12-01'
GROUP BY customer_id;
~~~

Nếu predicate thời gian phù hợp với chỉ mục hoặc partition key, DBMS có thể chỉ đọc các vùng liên quan. Cần kiểm tra actual rows ở đầu vào aggregation và số block đọc để xác nhận lợi ích.

## 5. Sargability: viết điều kiện để có thể tận dụng access path

### 5.1. Khái niệm

Sargable là cách gọi điều kiện có thể được DBMS sử dụng hiệu quả để tìm phạm vi khóa trong chỉ mục hoặc chọn access path phù hợp. Khái niệm thường được dùng khi nói về B-tree index. Không phải mọi predicate không sargable đều chậm, và optimizer có thể có các kỹ thuật đặc biệt để xử lý một số biểu thức. Tuy nhiên, cách viết điều kiện có thể ảnh hưởng lớn đến khả năng sử dụng index.

### 5.2. Tránh bọc cột bằng hàm khi không cần

Ví dụ:

~~~sql
-- Có thể khó tận dụng index thông thường trên created_at.
SELECT order_id
FROM orders
WHERE DATE(created_at) = DATE '2026-11-19';
~~~

Biểu thức DATE(created_at) áp dụng hàm lên từng giá trị cột. Một index thông thường trên created_at có thể không hỗ trợ trực tiếp điều kiện này, tùy DBMS và khả năng biến đổi của optimizer.

Có thể viết lại thành khoảng nửa mở:

~~~sql
SELECT order_id
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00';
~~~

Điều kiện mới so sánh trực tiếp cột với hai mốc thời gian, thường cho phép range scan trên index created_at. Dùng khoảng nửa mở giúp không phải đoán độ chính xác của timestamp và tránh bỏ sót các thời điểm cuối ngày.

Phải xác định đúng timezone và kiểu dữ liệu. Nếu created_at lưu UTC nhưng mốc ngày được xác định theo timezone địa phương, cần chuyển đổi mốc thời gian ở phía tham số một cách nhất quán. Rewrite sai timezone có thể thay đổi tập kết quả.

### 5.3. Tránh chuyển kiểu trên cột

Giả sử customer_id là số nguyên. Cách viết sau có thể khiến DBMS phải chuyển kiểu trên cột:

~~~sql
WHERE CAST(customer_id AS VARCHAR(20)) = '42'
~~~

Nếu ứng dụng đã có giá trị số, hãy truyền tham số đúng kiểu:

~~~sql
WHERE customer_id = 42
~~~

Hoặc dùng bind parameter với kiểu dữ liệu phù hợp. Hành vi chuyển kiểu phụ thuộc DBMS, collation và kiểu tham số; có trường hợp optimizer vẫn dùng được index, có trường hợp không. Hãy kiểm tra plan thay vì mặc định.

### 5.4. LIKE và wildcard

Điều kiện:

~~~sql
WHERE email LIKE 'user%'
~~~

có thể sử dụng B-tree index trong nhiều DBMS và collation phù hợp vì tiền tố được xác định. Trong khi đó:

~~~sql
WHERE email LIKE '%example.test'
~~~

có wildcard ở đầu, nên B-tree thông thường khó xác định điểm bắt đầu của vùng khóa phù hợp. Có thể cần full-text, trigram, reverse index hoặc cơ chế tìm kiếm chuyên dụng tùy yêu cầu và DBMS.

Không thay đổi biểu thức LIKE nếu điều đó làm thay đổi collation, phân biệt chữ hoa/thường hoặc ngữ nghĩa Unicode. Tìm kiếm chuỗi cần kiểm tra chính xác quy tắc so sánh của hệ thống.

### 5.5. OR và các lựa chọn access path

Một predicate OR có thể làm optimizer khó dùng một index đơn, nhưng nhiều DBMS hỗ trợ bitmap OR hoặc index merge. Ví dụ:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 42
   OR assigned_agent_id = 17;
~~~

Nếu cả hai cột có index phù hợp, optimizer có thể kết hợp các tập row identifier. Một phép rewrite thành UNION có thể hữu ích trong một số trường hợp nhưng phải xử lý duplicate semantics:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 42
UNION
SELECT order_id
FROM orders
WHERE assigned_agent_id = 17;
~~~

UNION loại bỏ các dòng trùng theo toàn bộ cột được chọn. Điều này có thể tương đương với OR trong ví dụ khi chỉ chọn order_id, nhưng tốn thêm chi phí sort/hash để loại trùng. Nếu dùng UNION ALL, các đơn hàng thỏa cả hai điều kiện sẽ xuất hiện hai lần, khác với OR. Nếu chọn thêm các cột không duy nhất, quy tắc loại trùng cũng có thể khác kỳ vọng. Cần xác định khóa dòng và kiểm thử dữ liệu giao nhau.

## 6. Loại bỏ phép tính và dữ liệu không cần thiết

### 6.1. Chỉ lấy cột cần dùng

SELECT * có thể khiến DBMS đọc và truyền các cột không cần thiết, đặc biệt khi bảng có cột văn bản lớn, JSON hoặc payload nhị phân.

~~~sql
-- Chỉ cần trạng thái và tổng tiền nhưng lại lấy mọi cột.
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

Nên chỉ chọn những cột ứng dụng thực sự cần:

~~~sql
SELECT order_id, status, total
FROM orders
WHERE customer_id = 42;
~~~

Việc giảm projection có thể giảm bytes đọc, bộ nhớ trung gian, dữ liệu truyền qua mạng và cho phép covering index trong một số trường hợp. Tuy nhiên, DBMS có thể không đọc toàn bộ cột của SELECT * nếu projection phía trên loại bỏ chúng; hãy kiểm tra actual plan và chi phí truyền dữ liệu.

### 6.2. Loại bỏ biểu thức tính lặp

Nếu cùng một biểu thức phức tạp được tính nhiều lần, có thể tính một lần trong derived table hoặc CTE để làm rõ ý định:

~~~sql
SELECT order_id,
       total * tax_rate AS tax_amount,
       total + total * tax_rate AS grand_total
FROM orders;
~~~

Có thể tổ chức biểu thức:

~~~sql
SELECT order_id,
       tax_amount,
       total + tax_amount AS grand_total
FROM (
    SELECT order_id,
           total,
           total * tax_rate AS tax_amount
    FROM orders
) AS calculated;
~~~

Đây là cách làm rõ cấu trúc, nhưng không bảo đảm DBMS chỉ tính biểu thức đúng một lần. Optimizer có thể inline derived table và tính lại biểu thức, hoặc tự nhận diện biểu thức lặp. Nếu biểu thức rất tốn kém, cần kiểm tra plan và profile CPU. Không dùng CTE chỉ vì nghĩ rằng nó luôn materialize hoặc luôn cache kết quả; hành vi phụ thuộc DBMS và phiên bản.

### 6.3. Tránh gọi hàm hoặc scalar subquery lặp lại

Một scalar subquery tương quan có thể được thực hiện cho từng dòng bên ngoài:

~~~sql
SELECT c.customer_id,
       (SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id) AS last_order_at
FROM customers AS c;
~~~

Nếu customers có nhiều dòng, truy vấn con có thể được thực hiện lặp lại hoặc được optimizer biến đổi thành một dạng khác. Có thể thử tổng hợp một lần rồi join:

~~~sql
SELECT c.customer_id, x.last_order_at
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, MAX(created_at) AS last_order_at
    FROM orders
    GROUP BY customer_id
) AS x
  ON x.customer_id = c.customer_id;
~~~

Cách rewrite này có thể hiệu quả nếu tập orders được quét và tổng hợp một lần. Nhưng nếu chỉ có một vài khách hàng được chọn và index trên orders(customer_id, created_at) rất tốt, scalar lookup có thể rẻ hơn. Cần so sánh hai kế hoạch trên số lượng khách hàng và phân bố dữ liệu đại diện.

### 6.4. Tránh chuyển đổi và format ở phía DBMS khi không cần

Các hàm format ngày, số hoặc chuỗi có thể tốn CPU và làm kết quả khó tái sử dụng. Nếu ứng dụng chỉ cần dữ liệu có kiểu, hãy trả về kiểu gốc và format ở tầng trình bày khi phù hợp.

Tuy nhiên, không chuyển logic nghiệp vụ sang client nếu điều đó làm thay đổi tính nhất quán, lọc, sắp xếp hoặc tổng hợp. Việc chuyển đổi chỉ nên thực hiện ở tầng có trách nhiệm phù hợp và không làm tăng lượng dữ liệu truyền quá mức.

## 7. Loại bỏ phép JOIN hoặc truy vấn con không cần thiết

### 7.1. Chỉ join khi cần dữ liệu hoặc điều kiện từ bảng đó

Ví dụ:

~~~sql
SELECT o.order_id, o.total
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
~~~

Nếu không dùng cột customers, không lọc theo customers và quan hệ khóa ngoại cùng ràng buộc duy nhất bảo đảm mỗi order có đúng một customer tương ứng, phép join có thể không cần thiết. Có thể viết:

~~~sql
SELECT o.order_id, o.total
FROM orders AS o
WHERE o.status = 'PAID';
~~~

Nhưng phải kiểm tra các giả định. INNER JOIN sẽ loại bỏ order không có customer khớp. Nếu dữ liệu có orphan row, bỏ join sẽ làm kết quả thay đổi. Nếu quan hệ một-nhiều, join có thể nhân bản dòng orders. Không thể loại bỏ join chỉ vì không chọn cột từ bảng kia.

### 7.2. EXISTS khi chỉ cần kiểm tra sự tồn tại

Nếu mục tiêu là tìm khách hàng có ít nhất một đơn hàng, EXISTS thể hiện ý định rõ ràng:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Nếu dùng JOIN:

~~~sql
SELECT c.customer_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Một khách hàng có nhiều đơn hàng sẽ xuất hiện nhiều lần trong kết quả JOIN. Nếu muốn mỗi khách hàng chỉ xuất hiện một lần, có thể cần DISTINCT, làm phát sinh thêm công việc. EXISTS biểu đạt phép semi-join: chỉ cần biết có ít nhất một dòng phù hợp, không cần nhân bản khách hàng theo số đơn hàng.

Optimizer thường có thể chuyển EXISTS thành semi-join hoặc dạng kế hoạch tương đương. Hiệu năng vẫn phụ thuộc index, cardinality và số dòng đầu vào.

### 7.3. NOT EXISTS và NOT IN khi có NULL

Để tìm khách hàng chưa có đơn hàng, NOT EXISTS thường là cách viết rõ ràng:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Cần thận trọng với NOT IN:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Nếu subquery trả về ít nhất một NULL, biểu thức NOT IN có thể trở thành UNKNOWN cho các giá trị không khớp và loại bỏ kết quả ngoài dự kiến. NOT EXISTS có ngữ nghĩa khác trong trường hợp này. Chỉ rewrite giữa hai dạng khi đã xác định rõ ràng tính nullable và yêu cầu nghiệp vụ.

## 8. Biến đổi truy vấn tương đương

### 8.1. Tương đương về kết quả là điều kiện bắt buộc

Hai câu SQL tương đương khi chúng trả về cùng kết quả theo ngữ nghĩa cần bảo toàn, bao gồm:

- Giá trị cột và kiểu dữ liệu.
- Số lần xuất hiện của từng dòng (bag semantics), trừ khi truy vấn có DISTINCT hoặc set operation loại trùng.
- Cách xử lý NULL theo logic ba giá trị.
- Ràng buộc về thứ tự nếu có ORDER BY.
- Quy tắc collation, timezone và chuyển kiểu.
- Hành vi khi dữ liệu trùng hoặc quan hệ không thỏa giả định.
- Tính nhất quán khi truy vấn chạy trong transaction và isolation level cụ thể.

SQL thường không bảo đảm thứ tự kết quả nếu không có ORDER BY. Hai plan trả về cùng tập dòng nhưng thứ tự khác nhau vẫn tương đương nếu ứng dụng không yêu cầu thứ tự. Nếu ứng dụng phụ thuộc thứ tự ngầm định, đó là lỗi hợp đồng truy vấn cần sửa bằng ORDER BY rõ ràng.

### 8.2. Thay subquery bằng JOIN

Một subquery trả về dữ liệu từ bảng liên quan có thể được rewrite thành JOIN. Ví dụ:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id IN (
    SELECT customer_id
    FROM customers
    WHERE region = 'NORTH'
);
~~~

Có thể viết:

~~~sql
SELECT o.order_id
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.region = 'NORTH';
~~~

Hai dạng có thể tương đương nếu customer_id của customers là duy nhất hoặc các dòng trùng không làm thay đổi kết quả mong muốn. Nếu customers có nhiều dòng cùng customer_id, JOIN có thể nhân bản order_id, trong khi IN chỉ kiểm tra sự tồn tại và không nhân bản dòng bên ngoài.

Nếu muốn bảo toàn semantics membership, có thể dùng EXISTS:

~~~sql
SELECT o.order_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM customers AS c
    WHERE c.customer_id = o.customer_id
      AND c.region = 'NORTH'
);
~~~

Chọn dạng nào cần căn cứ vào quan hệ dữ liệu và plan; không giả định JOIN luôn nhanh hơn subquery.

### 8.3. UNION và UNION ALL

UNION kết hợp kết quả và loại bỏ dòng trùng; UNION ALL giữ tất cả dòng. Nếu hai nhánh chắc chắn rời nhau, UNION ALL có thể tránh bước sort/hash loại trùng.

Ví dụ, hai điều kiện trạng thái loại trừ lẫn nhau:

~~~sql
SELECT order_id FROM orders WHERE status = 'PAID'
UNION ALL
SELECT order_id FROM orders WHERE status = 'CANCELLED';
~~~

Nếu điều kiện không loại trừ nhau, UNION ALL có thể tạo kết quả trùng. Thay UNION bằng UNION ALL chỉ hợp lệ khi đã chứng minh các nhánh không giao nhau hoặc ứng dụng chấp nhận dòng trùng.

### 8.4. OR thành UNION

Tách OR thành hai nhánh có thể giúp mỗi nhánh dùng một chỉ mục riêng. Tuy nhiên, phải xử lý giao nhau và duplicate semantics. UNION loại trùng có thể tốn kém; UNION ALL giữ trùng. Một cách khác là dùng UNION ALL với điều kiện nhánh thứ hai loại trừ các dòng đã thỏa nhánh đầu:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 42

UNION ALL

SELECT order_id
FROM orders
WHERE assigned_agent_id = 17
  AND (customer_id <> 42 OR customer_id IS NULL);
~~~

Điều kiện loại trừ cần được viết đúng với nullable semantics và các cột được chọn. Cách này minh họa kỹ thuật, không phải mẫu rewrite áp dụng máy móc. So sánh với kế hoạch OR ban đầu và kiểm thử dữ liệu giao nhau, NULL.

### 8.5. Điều kiện BETWEEN và khoảng nửa mở

BETWEEN bao gồm cả hai đầu mút. Với thời gian, điều kiện:

~~~sql
WHERE created_at BETWEEN TIMESTAMP '2026-11-01 00:00:00'
                     AND TIMESTAMP '2026-11-30 00:00:00'
~~~

chỉ bao gồm chính xác thời điểm 00:00:00 của ngày cuối nếu cột có độ chính xác nhỏ hơn hoặc bằng biểu diễn đó; các thời điểm sau đó trong ngày 30 có thể bị bỏ sót.

Một khoảng nửa mở thường rõ ràng hơn:

~~~sql
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-12-01 00:00:00'
~~~

Khoảng nửa mở bao gồm đầu kỳ và loại trừ đầu kỳ kế tiếp, tránh phải đoán precision của timestamp. Khi rewrite, cần giữ cùng timezone và quy tắc chuyển kiểu.

## 9. Những phép biến đổi dễ làm thay đổi kết quả

### 9.1. NULL và logic ba giá trị

Trong SQL, so sánh với NULL bằng dấu bằng không trả TRUE; nó trả UNKNOWN. Dùng IS NULL hoặc IS NOT NULL để kiểm tra NULL.

~~~sql
WHERE cancelled_at = NULL
~~~

không tương đương với:

~~~sql
WHERE cancelled_at IS NULL
~~~

Optimizer có thể đơn giản hóa biểu thức dựa trên quy tắc NULL, nhưng người viết truy vấn cần hiểu điều kiện. Các phép biến đổi NOT IN, NOT EXISTS, NOT, OR và phép so sánh nullable cần được kiểm thử kỹ.

### 9.2. Duplicate rows

SQL mặc định xử lý kết quả theo dạng bag, nghĩa là dòng trùng có thể xuất hiện nhiều lần. JOIN có thể nhân dòng; EXISTS chỉ kiểm tra có hay không; DISTINCT và UNION loại trùng.

Khi thay JOIN bằng EXISTS, hoặc UNION bằng UNION ALL, cần kiểm tra số lần xuất hiện của từng dòng. So sánh hai kết quả chỉ bằng tập giá trị duy nhất có thể bỏ qua lỗi duplicate. Nên so sánh cả multiplicity, ví dụ nhóm theo toàn bộ cột kết quả và đếm số lần xuất hiện.

### 9.3. LIMIT, OFFSET và ORDER BY

LIMIT hoặc OFFSET làm thay đổi số dòng được lấy. Di chuyển filter qua một subquery có LIMIT có thể thay đổi kết quả vì tập dòng được giới hạn trước khi lọc.

Ví dụ, hai cách sau không tương đương:

~~~sql
-- Lấy 10 đơn hàng mới nhất, rồi chỉ giữ đơn PAID trong 10 dòng đó.
SELECT *
FROM (
    SELECT *
    FROM orders
    ORDER BY created_at DESC
    LIMIT 10
) AS recent
WHERE status = 'PAID';
~~~

~~~sql
-- Lọc đơn PAID trước, rồi lấy 10 đơn mới nhất trong số đó.
SELECT *
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 10;
~~~

Kết quả có thể khác vì vị trí LIMIT thay đổi. Khi dùng LIMIT, cần có ORDER BY ổn định và hiểu thứ tự thực hiện logic.

### 9.4. Hàm không xác định và hàm có side effect

Các hàm như random(), current timestamp theo ngữ nghĩa cụ thể, sequence generator hoặc hàm do người dùng định nghĩa có thể không cho cùng kết quả khi được tính ở vị trí hoặc số lần khác nhau. Đẩy predicate hoặc loại bỏ biểu thức có thể thay đổi số lần gọi hàm.

Không rewrite biểu thức chứa hàm volatile hoặc side effect nếu chưa hiểu hành vi DBMS. Một biểu thức nhìn giống nhau về mặt văn bản không nhất thiết có thể tính lại tùy ý.

### 9.5. Phép toán số và độ chính xác

Biến đổi đại số như phân phối phép nhân, cộng hoặc chia có thể thay đổi kết quả do kiểu số nguyên, overflow, floating point rounding hoặc decimal precision. Ví dụ, phép chia số nguyên có thể cắt phần thập phân; thay đổi thứ tự phép tính có thể thay đổi điểm overflow.

Nếu cần kết quả tài chính chính xác, giữ kiểu DECIMAL/NUMERIC và kiểm tra scale/precision. Không giả định các phép biến đổi số học là hoàn toàn tương đương ở mọi kiểu dữ liệu.

### 9.6. Outer join và NULL được tạo ra

Outer join tạo giá trị NULL cho phía không khớp. Đẩy điều kiện lọc vào hoặc ra khỏi join có thể thay đổi việc giữ lại dòng không khớp. Luôn kiểm tra tập dòng có match, không match và có cột NULL thực sự trước khi rewrite.

## 10. CTE, derived table và materialization

CTE (WITH clause) và derived table giúp chia truy vấn phức tạp thành các bước dễ hiểu. Nhưng không nên cho rằng CTE luôn là một bảng tạm hoặc luôn được tính đúng một lần.

~~~sql
WITH paid_orders AS (
    SELECT order_id, customer_id, total
    FROM orders
    WHERE status = 'PAID'
)
SELECT customer_id, SUM(total)
FROM paid_orders
GROUP BY customer_id;
~~~

Một số DBMS có thể inline CTE vào truy vấn chính; một số trường hợp hoặc phiên bản có thể materialize. Materialization có thể hữu ích nếu kết quả trung gian được dùng nhiều lần và tránh tính lặp, nhưng cũng có thể ngăn predicate pushdown và tạo dữ liệu tạm lớn.

Khi quyết định dùng CTE, hãy xem:

- DBMS và phiên bản có inline hay materialize mặc định không?
- Có hint điều khiển materialization không, và hint có thực sự cần thiết không?
- CTE được tham chiếu bao nhiêu lần?
- Predicate có thể được đẩy vào nguồn dữ liệu không?
- Kết quả trung gian lớn đến đâu?
- Execution plan có Materialize, CTE Scan hoặc toán tử tương đương không?

CTE trước hết là công cụ tổ chức SQL dễ đọc. Chỉ dùng điều khiển materialization khi có bằng chứng về kế hoạch và lợi ích.

## 11. Partition pruning và đẩy điều kiện đến storage

Nếu bảng được phân vùng theo thời gian hoặc khóa, predicate phù hợp có thể giúp DBMS bỏ qua các partition không liên quan. Quá trình này thường gọi là partition pruning.

~~~sql
SELECT event_id, occurred_at, event_type
FROM events
WHERE occurred_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-11-02 00:00:00';
~~~

Nếu events được partition theo tháng hoặc ngày trên occurred_at, DBMS có thể chỉ truy cập partition giao với khoảng thời gian. Nếu cột phân vùng bị bọc trong hàm hoặc kiểu tham số không phù hợp, pruning có thể bị hạn chế tùy DBMS.

Trong hệ thống lưu trữ phân tán hoặc columnar, predicate có thể được đẩy xuống storage engine để chỉ đọc block hoặc row group phù hợp. Các cơ chế như zone map, min/max metadata, bloom filter và column pruning có thể giảm lượng dữ liệu đọc. Tính năng cụ thể phụ thuộc engine.

Điều kiện để pushdown hiệu quả:

- Predicate có thể được đánh giá tại tầng storage.
- Kiểu dữ liệu và phép so sánh được hỗ trợ.
- Hàm hoặc biểu thức không cản trở việc đánh giá.
- Thống kê hoặc metadata đủ để loại bỏ vùng dữ liệu.
- Kết quả vẫn tuân thủ đúng semantics của DBMS.

## 12. Kiểm tra optimizer đã tự thực hiện rewrite chưa

Nhiều phép biến đổi được optimizer tự động thực hiện. Trước khi sửa SQL, hãy xem execution plan để biết DBMS đã làm gì.

Các dấu hiệu có thể quan sát:

- Predicate xuất hiện trong Index Cond hoặc điều kiện scan thay vì chỉ ở Filter phía trên.
- Số actual rows giảm mạnh trước join hoặc aggregate.
- Scan chỉ truy cập partition liên quan.
- Projection chỉ giữ cột cần thiết.
- Semi Join hoặc Anti Join được dùng cho EXISTS/NOT EXISTS.
- Join order và join algorithm thay đổi hợp lý.
- Sort hoặc materialization không cần thiết được loại bỏ.
- Estimated rows gần với actual rows hơn sau khi cập nhật thống kê.

Tên toán tử khác nhau giữa PostgreSQL, MySQL, SQL Server và các hệ thống khác. Hãy đọc execution plan theo đúng DBMS và phiên bản.

Ví dụ với PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.region = 'NORTH'
  AND o.created_at >= TIMESTAMP '2026-11-01 00:00:00';
~~~

So sánh:

- Estimated rows và actual rows tại scan, join.
- Filter và Index Cond.
- Số loops của từng node.
- Buffers hit/read.
- Actual time và tổng thời gian.
- Có sort, hash spill hoặc temporary I/O không.

EXPLAIN ANALYZE thực thi truy vấn. Với câu lệnh ghi, có thể tạo thay đổi thật. Không chạy trên production nếu chưa đánh giá tác động và có quy trình an toàn.

## 13. Quy trình rewrite và kiểm chứng

### Bước 1: Ghi nhận baseline

Lưu SQL ban đầu, giá trị tham số đại diện, execution plan, số dòng ước lượng/thực tế, thời gian, buffer reads, CPU, I/O và mức đồng thời. Ghi cả latency p50/p95/p99 ở tầng ứng dụng nếu truy vấn thuộc luồng người dùng.

### Bước 2: Xác định công việc dư thừa

Tìm các dấu hiệu:

- Filter nằm sau một join hoặc sort lớn dù có thể lọc sớm.
- Scan nhiều dòng nhưng chỉ trả một vài dòng.
- SELECT * hoặc cột trung gian không được dùng.
- Scalar subquery hoặc biểu thức tính toán lặp lại.
- Join chỉ để kiểm tra sự tồn tại.
- DISTINCT hoặc UNION loại trùng không cần thiết.
- Hàm trên cột lọc làm mất khả năng dùng access path.
- Subquery/CTE materialize một tập dữ liệu lớn không cần thiết.

### Bước 3: Đưa ra một giả thuyết cụ thể

Ví dụ: “Điều kiện created_at đang được áp dụng sau khi join; đẩy predicate vào scan orders sẽ giảm actual rows ở đầu vào join.” Giả thuyết phải có dấu hiệu trong plan hoặc metrics để kiểm chứng.

### Bước 4: Rewrite một thay đổi mỗi lần

Giữ nguyên semantics, thay đổi một cấu trúc SQL và lưu phiên bản trước/sau. Tránh thay nhiều điều kiện, chỉ mục và cấu hình cùng lúc vì khó xác định yếu tố tạo ra khác biệt.

### Bước 5: Kiểm tra tính tương đương

Chạy hai phiên bản trên cùng snapshot dữ liệu hoặc transaction có isolation phù hợp. So sánh:

- Số dòng kết quả và số lần xuất hiện của mỗi dòng.
- Giá trị NULL và kiểu dữ liệu.
- Kết quả với dữ liệu trùng, không khớp và biên thời gian.
- Kết quả với tham số phổ biến, hiếm và giá trị NULL nếu được phép.
- Thứ tự kết quả khi có yêu cầu ORDER BY.
- Hành vi của hàm không xác định hoặc side effect nếu có.

Với truy vấn lớn, có thể so sánh kết quả theo batch hoặc checksum có kiểm soát, nhưng checksum không thay thế việc kiểm tra semantics khi cần độ chính xác tuyệt đối.

### Bước 6: Đo lại trong điều kiện tương đương

Dùng cùng dữ liệu, tham số, cache state và mức concurrency. So sánh plan, actual rows, CPU, I/O, temp usage, latency phân vị và throughput. Đừng chỉ so một lần chạy nóng với một lần chạy lạnh.

### Bước 7: Đánh giá tác động toàn workload

Một rewrite có thể tăng tốc truy vấn đọc nhưng tăng số lần gọi, thay đổi khóa hoặc làm transaction giữ tài nguyên lâu hơn. Kiểm tra cả các query digest khác, thao tác ghi và workload đồng thời.

### Bước 8: Theo dõi sau triển khai

Quan sát p95/p99, lỗi, CPU, I/O, wait events, rows read và số lần chạy trong môi trường thật. Nếu lợi ích không xuất hiện hoặc có tác dụng phụ, hoàn nguyên theo quy trình thay đổi đã định.

## 14. Ví dụ xuyên suốt: tối ưu truy vấn lịch sử đơn hàng

Giả sử ứng dụng hiển thị 20 đơn hàng PAID mới nhất của một khách hàng trong một khoảng thời gian. Bảng orders có hàng chục triệu dòng và bảng order_items chứa nhiều dòng chi tiết cho mỗi đơn.

Một truy vấn ban đầu:

~~~sql
SELECT o.order_id,
       o.created_at,
       o.total,
       (SELECT COUNT(*)
        FROM order_items AS i
        WHERE i.order_id = o.order_id) AS item_count
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE DATE(o.created_at) = DATE '2026-11-19'
  AND c.region = 'NORTH'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 20;
~~~

Có một số điểm cần điều tra:

1. DATE(o.created_at) bọc cột thời gian, có thể hạn chế range access trên index thông thường.
2. Join customers chỉ để lọc region; predicate region có thể được đẩy xuống phía customers.
3. Scalar subquery đếm order_items có thể được thực hiện cho từng đơn hàng được xét.
4. LIMIT yêu cầu thứ tự, nên cần xem DBMS có thể tận dụng index để tránh sort lớn hay không.
5. Nếu filter và join làm giảm dữ liệu muộn, DBMS có thể xử lý nhiều dòng hơn cần thiết.

Một phiên bản viết lại để thử nghiệm:

~~~sql
SELECT o.order_id,
       o.created_at,
       o.total,
       (
           SELECT COUNT(*)
           FROM order_items AS i
           WHERE i.order_id = o.order_id
       ) AS item_count
FROM orders AS o
WHERE o.created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-11-20 00:00:00'
  AND o.status = 'PAID'
  AND EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.customer_id = o.customer_id
        AND c.region = 'NORTH'
  )
ORDER BY o.created_at DESC
LIMIT 20;
~~~

Phiên bản này thay hàm trên cột bằng khoảng thời gian, và biểu đạt điều kiện customers như một phép kiểm tra tồn tại. Việc đổi JOIN thành EXISTS giữ nguyên số dòng trong ví dụ khi customer_id là duy nhất ở customers (chẳng hạn được bảo đảm bằng khóa chính hoặc unique constraint); nếu khóa này không duy nhất, JOIN ban đầu có thể nhân bản đơn hàng còn EXISTS thì không. Nó không đảm bảo nhanh hơn trong mọi DBMS. Optimizer có thể đã thực hiện các biến đổi tương tự ở truy vấn đầu; scalar count có thể vẫn cần truy cập order_items cho từng đơn hàng.

Nếu order_items có chỉ mục trên order_id, phép đếm theo từng đơn có thể phù hợp khi chỉ xét 20 đơn. Nếu DBMS chọn plan không tốt hoặc cần tổng hợp nhiều dòng, có thể thử pre-aggregate:

~~~sql
SELECT o.order_id,
       o.created_at,
       o.total,
       COALESCE(i.item_count, 0) AS item_count
FROM orders AS o
LEFT JOIN (
    SELECT order_id, COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
) AS i
  ON i.order_id = o.order_id
WHERE o.created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-11-20 00:00:00'
  AND o.status = 'PAID'
  AND EXISTS (
      SELECT 1
      FROM customers AS c
      WHERE c.customer_id = o.customer_id
        AND c.region = 'NORTH'
  )
ORDER BY o.created_at DESC
LIMIT 20;
~~~

Cách pre-aggregate có thể đắt nếu phải nhóm toàn bộ order_items trong khi chỉ cần đếm cho 20 đơn. Một optimizer tốt có thể đẩy giới hạn hoặc dùng plan khác, nhưng không nên giả định điều đó. Có thể cần một cấu trúc truy vấn khác hoặc chỉ mục phù hợp.

Để quyết định, hãy đo hai dạng với cùng dữ liệu và tham số. Xem số dòng orders được xét trước LIMIT, số lần truy cập order_items, actual loops, buffers, sort và tổng thời gian. Đồng thời xác minh kết quả giống nhau cho đơn không có item, dữ liệu customer thiếu, trạng thái khác và mốc thời gian biên.

## 15. Các nguyên tắc thực hành

- Viết điều kiện lọc rõ ràng và giữ kiểu tham số phù hợp với kiểu cột.
- Lọc sớm khi có thể mà không làm thay đổi ngữ nghĩa outer join hoặc aggregation.
- Chỉ chọn cột cần thiết, nhất là với bảng có payload lớn.
- Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại; dùng JOIN khi thực sự cần kết hợp dòng.
- Kiểm tra duplicate và NULL trước khi đổi JOIN, IN, EXISTS, UNION hoặc UNION ALL.
- Dùng khoảng nửa mở cho truy vấn thời gian khi phù hợp.
- Không bọc cột trong hàm nếu có thể viết predicate tương đương trực tiếp trên cột.
- Không giả định CTE được materialize hoặc inline; kiểm tra hành vi của DBMS.
- Để optimizer tự chọn plan nếu nó đã tối ưu; chỉ can thiệp khi có bằng chứng.
- Đo cả chi phí đọc và tác động đến ghi, cache, concurrency và workload khác.

## 16. Checklist trước khi chấp nhận một phép rewrite

- [ ] Đã lưu SQL, tham số và execution plan ban đầu chưa?
- [ ] Đã xác định phần dữ liệu hoặc phép tính đang dư thừa chưa?
- [ ] Predicate có thể được đẩy xuống scan hoặc phía đầu vào join không?
- [ ] Có nguy cơ thay đổi semantics của LEFT/RIGHT/FULL JOIN không?
- [ ] Có NULL, duplicate rows, NOT IN hoặc logic ba giá trị cần kiểm tra không?
- [ ] Có LIMIT, OFFSET, ORDER BY, DISTINCT hoặc aggregation ảnh hưởng thứ tự biến đổi không?
- [ ] Có hàm volatile, side effect, timezone, collation hoặc phép tính nhạy độ chính xác không?
- [ ] Kiểu tham số và kiểu cột có tương thích để dùng access path không?
- [ ] Kết quả trước/sau đã được so sánh trên dữ liệu biên và tham số đại diện chưa?
- [ ] Execution plan mới có giảm actual rows, loops, I/O, sort hoặc CPU không?
- [ ] Đã đo latency phân vị, throughput và tác động lên các query khác chưa?
- [ ] Đã có kế hoạch theo dõi và hoàn nguyên nếu kết quả production xấu đi chưa?

## Kết luận

Đẩy điều kiện lọc, loại bỏ phép tính thừa và rewrite truy vấn là những cách giảm công việc trước khi cân nhắc tăng tài nguyên. Predicate pushdown có thể thu nhỏ đầu vào của join, sort và aggregation; điều kiện sargable giúp DBMS tận dụng index hoặc partition pruning; projection gọn, EXISTS đúng chỗ và loại bỏ join không cần thiết có thể giảm dữ liệu phải xử lý.

Mọi phép biến đổi phải bảo toàn semantics của SQL, đặc biệt với NULL, outer join, duplicate rows, LIMIT, aggregation, hàm không xác định và kiểu dữ liệu. Optimizer có thể đã tự thực hiện nhiều rewrite, vì vậy execution plan và số liệu actual là bằng chứng quyết định. Hãy đo baseline, thay đổi từng yếu tố, kiểm tra kết quả tương đương và đo lại trên workload đại diện để xác nhận lợi ích thực tế.

