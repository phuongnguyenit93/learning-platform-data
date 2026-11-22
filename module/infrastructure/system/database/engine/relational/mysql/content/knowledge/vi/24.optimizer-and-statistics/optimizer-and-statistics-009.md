# Semijoin, antijoin và biến đổi truy vấn tồn tại

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Khi một câu truy vấn chỉ cần biết một hàng ở bảng khác có tồn tại hay không, EXISTS, IN, NOT EXISTS và NOT IN diễn đạt ý định đó rõ hơn việc JOIN rồi loại trùng. Optimizer MySQL có thể biến các truy vấn tồn tại thành **semijoin** hoặc **antijoin** để chọn cách thực thi hiệu quả.

Semijoin giữ hàng của phía ngoài khi có ít nhất một hàng khớp ở phía trong; antijoin giữ hàng phía ngoài khi không có hàng khớp. Đây là biến đổi về kế hoạch thực thi, không phải yêu cầu người viết phải thay câu SQL bằng một cú pháp JOIN riêng. Muốn dùng đúng, cần nắm semantics của NULL, điều kiện optimizer được phép biến đổi, các chiến lược semijoin và cách xác minh bằng EXPLAIN.

Các mốc phiên bản cần nhớ: MySQL 8.0.16 mở rộng semijoin transformation cho EXISTS; MySQL 8.0.17 bổ sung antijoin transformation cho nhiều dạng predicate phủ định; EXPLAIN FORMAT=TREE có từ MySQL 8.0.16 và EXPLAIN ANALYZE có từ MySQL 8.0.18. Kiểm tra phiên bản server bằng SELECT VERSION() trước khi chạy các ví dụ tương ứng.

## 1. Truy vấn tồn tại với EXISTS và IN

Giả sử có hai bảng:

- customers: mỗi hàng là một khách hàng.
- orders: mỗi hàng là một đơn hàng thuộc về một khách hàng.

Yêu cầu: lấy những khách hàng đã từng có đơn hàng.

Có thể viết bằng EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Hoặc viết bằng IN:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Cả hai câu truy vấn diễn đạt điều kiện khách hàng có ít nhất một đơn hàng phù hợp. Optimizer có thể nhận diện đây là semijoin và chọn kế hoạch join-like thay vì chạy subquery theo cách ngây thơ cho từng hàng.

### 1.1. EXISTS kiểm tra sự tồn tại

EXISTS (subquery) trả về TRUE nếu subquery tạo ra ít nhất một hàng; nếu không có hàng, nó trả về FALSE. Giá trị trong danh sách SELECT của subquery không quyết định kết quả:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

SELECT 1, SELECT * hay SELECT o.order_id đều có cùng ý nghĩa về kiểm tra tồn tại. SELECT 1 thường được dùng vì thể hiện rõ rằng ta chỉ quan tâm có hàng hay không.

EXISTS không cần đọc hết mọi hàng khớp để xác định kết quả logic. Khi đã tìm được một hàng phù hợp, các hàng khớp khác không làm thay đổi TRUE thành một kết quả khác.

### 1.2. IN kiểm tra thành viên

expression IN (subquery) kiểm tra giá trị ở phía trái có bằng một giá trị trong tập kết quả hay không theo quy tắc so sánh SQL.

~~~sql
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.status = 'PAID'
)
~~~

Nếu subquery trả nhiều hàng có cùng customer_id, điều kiện IN vẫn chỉ là TRUE/FALSE/UNKNOWN cho hàng phía ngoài. Nó không nhân bản hàng khách hàng theo số đơn hàng.

### 1.3. EXISTS có tương quan và không tương quan

Subquery có tương quan (correlated subquery) tham chiếu cột từ query block bên ngoài:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Subquery không tương quan không phụ thuộc hàng ngoài:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.status = 'PAID'
);
~~~

Tương quan mô tả quan hệ logic trong SQL, không khẳng định optimizer bắt buộc chạy subquery một lần cho mỗi hàng ngoài. Semijoin transformation có thể decorrelate hoặc tổ chức lại phép thực thi để tránh cách chạy lặp tốn kém.

## 2. Semijoin là gì?

Semijoin trả về hàng từ phía ngoài nếu tìm thấy ít nhất một hàng khớp ở phía trong. Nó không trả các cột của phía trong và không nhân bản hàng ngoài theo số lượng match.

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Mỗi khách hàng xuất hiện tối đa một lần từ nguồn customers, dù có một hay hàng trăm đơn hàng. Nếu bảng customers tự nó có nhiều hàng trùng customer_id vì không có ràng buộc duy nhất, các hàng ngoài đó vẫn là những hàng đầu vào riêng; semijoin chỉ ngăn việc nhân bản chúng do nhiều hàng match bên trong.

### 2.1. Semijoin khác INNER JOIN

Viết bằng JOIN:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Nếu khách hàng có ba đơn hàng, JOIN có thể trả ba hàng cho khách hàng đó. Muốn loại trùng cần thêm DISTINCT:

~~~sql
SELECT DISTINCT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Semijoin thể hiện trực tiếp yêu cầu "có ít nhất một match" và không cần tạo kết quả nhân bản rồi mới loại trùng. Optimizer có thể chọn một kế hoạch hiệu quả tương đương.

| Đặc điểm | EXISTS / Semijoin | INNER JOIN |
|---|---|---|
| Mục tiêu | Kiểm tra có match | Kết hợp các hàng khớp |
| Cột từ bảng trong | Không cần trả về | Có thể trả về |
| Nhiều hàng trong khớp | Không nhân bản hàng ngoài | Có thể nhân bản hàng ngoài |
| Cần DISTINCT để giữ hàng ngoài duy nhất | Thường không | Có thể cần tùy dữ liệu |

### 2.2. Khi nào nên dùng semijoin?

Dùng EXISTS hoặc IN khi câu hỏi nghiệp vụ là:

- Khách hàng nào đã có đơn hàng?
- Sản phẩm nào từng xuất hiện trong chi tiết đơn?
- Nhân viên nào có ít nhất một nhiệm vụ đang mở?
- Tài khoản nào có bản ghi giao dịch thỏa điều kiện?

Nếu cần lấy dữ liệu từ bảng trong, chẳng hạn ngày đặt hàng mới nhất, tổng số đơn hoặc chi tiết từng đơn, JOIN, aggregate hoặc window function có thể phù hợp hơn.

## 3. Antijoin là gì?

Antijoin trả về hàng của phía ngoài khi không tồn tại hàng nào ở phía trong thỏa điều kiện khớp.

Yêu cầu: lấy khách hàng chưa từng có đơn hàng:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Đây là antijoin về mặt ngữ nghĩa. Optimizer có thể biến truy vấn thành kế hoạch anti join để tìm hàng ngoài không có match.

### 3.1. Antijoin khác LEFT JOIN ... IS NULL

Cùng yêu cầu có thể viết:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

Đây là mẫu anti-join bằng outer join: hàng khách hàng không có đơn sẽ có các cột phía orders là NULL. Nên kiểm tra một cột phía trong được khai báo NOT NULL, thường là khóa chính, để phân biệt hàng không match với hàng match có giá trị NULL.

NOT EXISTS thường diễn đạt trực tiếp ý định và tránh phụ thuộc vào việc chọn cột kiểm tra NULL trong outer join.

### 3.2. Antijoin trả hàng ngoài không có match

Antijoin không có nghĩa là "bảng trong rỗng". Mỗi hàng ngoài được kiểm tra theo điều kiện tương quan của nó. Có thể một số khách hàng có đơn, số khác không; antijoin giữ nhóm không có match.

### 3.3. Điều kiện khớp phải phản ánh đúng nghiệp vụ

Ví dụ lấy khách hàng chưa có đơn đã thanh toán:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Khách hàng đã có đơn PENDING nhưng chưa có đơn PAID vẫn được trả về. Không được bỏ điều kiện status hoặc chuyển nó ra ngoài query block nếu điều đó làm thay đổi ý nghĩa.

## 4. NULL và khác biệt quan trọng giữa NOT IN với NOT EXISTS

Trong SQL, phép so sánh có thể trả về TRUE, FALSE hoặc UNKNOWN. WHERE chỉ giữ hàng khi điều kiện là TRUE. UNKNOWN không được xem là TRUE.

Đây là nguồn gây lỗi phổ biến khi dùng NOT IN.

### 4.1. NOT IN gặp NULL trong subquery

Giả sử subquery trả tập giá trị (1, 2, NULL):

~~~sql
SELECT 3 NOT IN (1, 2, NULL);
~~~

Kết quả là UNKNOWN, không phải TRUE. Vì 3 không bằng 1 hoặc 2, nhưng cũng không thể kết luận nó khác NULL theo logic ba giá trị của SQL.

Do đó:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Nếu orders.customer_id có ít nhất một NULL, điều kiện NOT IN của các khách hàng không match có thể trở thành UNKNOWN và bị loại khỏi kết quả. Truy vấn có thể trả về ít hàng hơn mong đợi, thậm chí không trả hàng nào.

### 4.2. NOT EXISTS không bị NULL trong danh sách SELECT làm nhiễu

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

EXISTS chỉ kiểm tra có hàng thỏa điều kiện hay không. Một hàng trong orders có customer_id NULL không match với customer_id thông thường bằng phép =, và nó không làm mọi phép kiểm tra NOT EXISTS trở thành UNKNOWN.

### 4.3. NULL ở phía ngoài cũng cần được cân nhắc

NOT IN với biểu thức bên trái NULL có kết quả UNKNOWN nếu tập con không rỗng; nếu tập con rỗng, phép NOT IN có thể là TRUE theo quy tắc tập rỗng. Trong khi đó, NOT EXISTS có thể trả TRUE cho hàng ngoài có khóa NULL nếu không có hàng nào thỏa phép so sánh bằng.

Vì vậy, thay NOT IN bằng NOT EXISTS có thể là cách sửa đúng cho yêu cầu "không có hàng match", nhưng cần xác định nghiệp vụ muốn xử lý khóa ngoài NULL như thế nào.

### 4.4. Cách viết NOT IN an toàn khi NULL không có ý nghĩa

Nếu customer_id bắt buộc phải có giá trị và dữ liệu trong subquery cũng cần loại NULL:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT o.customer_id
      FROM orders AS o
      WHERE o.customer_id IS NOT NULL
  );
~~~

Điều kiện loại NULL phải xuất phát từ quy tắc nghiệp vụ. Không thêm IS NOT NULL máy móc nếu NULL có ý nghĩa cần giữ.

### 4.5. Bảng chân trị rút gọn

| Phép thử | Kết quả |
|---|---|
| 3 IN (1, 2) | FALSE |
| 3 IN (1, 2, NULL) | UNKNOWN |
| 3 NOT IN (1, 2) | TRUE |
| 3 NOT IN (1, 2, NULL) | UNKNOWN |
| EXISTS (SELECT 1 WHERE 1 = 0) | FALSE |
| NOT EXISTS (SELECT 1 WHERE 1 = 0) | TRUE |

Khi thiết kế antijoin, hãy quyết định rõ liệu khóa so sánh có thể NULL và kết quả mong muốn cho trường hợp đó.

## 5. MySQL biến truy vấn tồn tại thành semijoin

Optimizer có thể chuyển một số predicate IN, = ANY hoặc EXISTS thành semijoin. Thay vì thực thi subquery tương quan độc lập cho từng hàng ngoài, optimizer có thể kết hợp query block thành một kế hoạch join và chọn chiến lược phù hợp.

Ví dụ:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Optimizer có thể tổ chức truy vấn thành phép semijoin giữa customers và tập đơn hàng PAID. Tùy dữ liệu, index và chi phí ước lượng, MySQL có thể bắt đầu từ khách hàng rồi tìm đơn phù hợp, hoặc bắt đầu từ tập đơn hàng rồi kết hợp với khách hàng.

### 5.1. EXISTS và IN có thể được tối ưu tương tự

Trong MySQL 8.0.16 trở lên, các truy vấn EXISTS đủ điều kiện có thể được xử lý theo cùng nhóm semijoin transformation như IN. Trước mốc này, khả năng tối ưu EXISTS có những khác biệt theo phiên bản.

Không nên chọn cú pháp chỉ vì nghĩ EXISTS luôn chạy nhanh hơn IN hoặc ngược lại. Hãy chọn biểu thức dễ đọc, đúng semantics và xác minh execution plan trên phiên bản MySQL đang dùng.

### 5.2. Semijoin là biến đổi của optimizer

Người viết SQL vẫn giữ cấu trúc EXISTS/IN. Semijoin là cách optimizer thực thi tương đương về kết quả. Cùng một câu SQL có thể có kế hoạch khác nhau khi:

- Số hàng và phân bố dữ liệu thay đổi.
- Thống kê index được cập nhật.
- Index được thêm hoặc xóa.
- Điều kiện lọc thay đổi.
- Phiên bản MySQL hoặc optimizer setting thay đổi.

Không dựa vào một kế hoạch duy nhất như cam kết cố định của cú pháp SQL.

## 6. Điều kiện để semijoin transformation được áp dụng

Không phải mọi subquery đều có thể biến thành semijoin. MySQL cần bảo toàn ngữ nghĩa của câu SQL và tuân theo các giới hạn của query block.

Những điều kiện quan trọng thường gồm:

- Predicate tồn tại dùng IN, = ANY hoặc EXISTS trong WHERE hoặc ON.
- Predicate nằm ở vị trí top-level của điều kiện hoặc là một thành phần trong chuỗi AND; predicate bị lồng trong OR thường không đủ điều kiện.
- Subquery là một query block SELECT đơn; UNION/UNION ALL không thuộc dạng semijoin cơ bản này.
- Subquery không có cấu trúc cản trở như aggregate function, HAVING hoặc LIMIT.
- Query block và tổng số bảng tham gia phải nằm trong giới hạn optimizer.
- Một số cấu trúc hoặc modifier như STRAIGHT_JOIN và window function có thể ngăn phép biến đổi.

DISTINCT, GROUP BY không có aggregate và ORDER BY trong một số subquery có thể được bỏ qua hoặc xử lý vì không làm thay đổi ngữ nghĩa tồn tại. Không nên tự loại bỏ chúng nếu chúng có ý nghĩa khác trong truy vấn thực tế; hãy kiểm tra đúng điều kiện của phiên bản.

### 6.1. Predicate nằm dưới OR

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.is_vip = 1
   OR EXISTS (
       SELECT 1
       FROM orders AS o
       WHERE o.customer_id = c.customer_id
   );
~~~

EXISTS nằm dưới OR. Đây không phải vị trí top-level AND term điển hình để semijoin transformation được áp dụng. Không nên kỳ vọng optimizer sẽ biến đổi giống truy vấn có predicate EXISTS đứng riêng.

### 6.2. LIMIT trong subquery

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    LIMIT 1
);
~~~

LIMIT thường không cần thiết trong EXISTS vì EXISTS đã chỉ quan tâm có ít nhất một hàng. Tuy nhiên, LIMIT có thể ngăn semijoin transformation theo điều kiện eligibility. Trong ví dụ này, hãy bỏ LIMIT nếu không có yêu cầu khác:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

### 6.3. Aggregate và HAVING

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    GROUP BY o.customer_id
    HAVING COUNT(*) >= 3
);
~~~

Đây là truy vấn kiểm tra điều kiện aggregate: khách hàng có ít nhất ba đơn. Aggregate và HAVING khiến truy vấn không còn là semijoin tồn tại đơn giản. Có thể cần giữ subquery hoặc thiết kế lại thành derived table/CTE đã tổng hợp rồi JOIN.

Không được bỏ GROUP BY/HAVING nếu mục tiêu nghiệp vụ là có ít nhất ba đơn; EXISTS thông thường chỉ kiểm tra ít nhất một hàng.

## 7. Các chiến lược thực thi semijoin

Khi semijoin transformation được áp dụng, MySQL có thể chọn nhiều chiến lược. Chiến lược phù hợp phụ thuộc số hàng, tính chọn lọc, index và chi phí ước lượng.

### 7.1. Table pullout

Optimizer có thể kéo một bảng từ subquery lên query block ngoài khi điều kiện cho phép. Sau khi pullout, bảng đó tham gia kế hoạch join chung. Điều này có thể mở thêm lựa chọn về thứ tự join và access path.

Table pullout là phép biến đổi cấu trúc query block; không có nghĩa hàng ngoài bị nhân bản trong kết quả cuối như INNER JOIN thông thường. Semijoin semantics vẫn phải được giữ.

### 7.2. FirstMatch

FirstMatch dừng tìm kiếm phía trong khi đã tìm thấy hàng match đầu tiên cho tổ hợp hàng ngoài tương ứng. Vì câu hỏi chỉ là "có tồn tại hay không", tìm thêm các hàng match khác không mang lại giá trị.

Ví dụ khách hàng có nhiều đơn PAID: sau khi tìm thấy đơn PAID đầu tiên, optimizer không cần tiếp tục duyệt các đơn PAID còn lại chỉ để quyết định khách hàng có tồn tại hay không.

FirstMatch có thể hiệu quả khi truy cập inner table bằng index và nhanh chóng tìm thấy match. Nếu match hiếm hoặc index không phù hợp, chi phí tìm kiếm có thể khác.

### 7.3. LooseScan

LooseScan có thể duyệt một index theo nhóm giá trị để lấy đại diện phù hợp, tránh xử lý lặp nhiều hàng inner có cùng giá trị join. Chiến lược này phụ thuộc cấu trúc index và thứ tự cột.

Ví dụ, nhiều đơn có cùng customer_id. Nếu index cho phép duyệt theo nhóm customer_id, optimizer có thể tận dụng việc các giá trị được sắp xếp để xác định khách hàng có đơn mà không cần xử lý toàn bộ duplicate theo cách thông thường.

Không phải mọi index đều hỗ trợ LooseScan. Cần xem plan để biết optimizer có chọn hay không.

### 7.4. Duplicate Weedout

Duplicate Weedout thực thi một kế hoạch join nhưng loại bỏ các tổ hợp trùng của hàng phía ngoài để giữ semijoin semantics. MySQL có thể dùng temporary table để ghi nhận các hàng ngoài đã xuất hiện.

Chiến lược này linh hoạt nhưng có thể tạo chi phí lưu và kiểm tra duplicate. Nếu số lượng tổ hợp lớn, temporary table và I/O có thể ảnh hưởng hiệu năng.

### 7.5. Materialization

Optimizer có thể thực thi subquery trước, materialize kết quả cần thiết vào internal temporary table, loại bỏ duplicate và tạo index phù hợp để tra cứu. Sau đó, query ngoài dùng tập materialized để xác định match.

Materialization có thể có lợi khi tập inner được tính một lần rồi tra cứu nhiều lần. Nó cũng có chi phí xây dựng và lưu kết quả trung gian. Với tập dữ liệu lớn, temporary table có thể cần lưu trên đĩa.

### 7.6. So sánh chiến lược

| Chiến lược | Ý tưởng | Điểm cần chú ý |
|---|---|---|
| Table pullout | Kéo bảng inner vào join plan chung | Mở thêm lựa chọn thứ tự join |
| FirstMatch | Dừng sau match đầu tiên | Hiệu quả khi tìm match nhanh |
| LooseScan | Duyệt đại diện theo nhóm index | Phụ thuộc index và thứ tự cột |
| Duplicate Weedout | Loại duplicate của hàng ngoài sau join | Có thể cần temporary table |
| Materialization | Tạo tập inner trung gian để tra cứu | Có chi phí tạo và lưu bảng tạm |

Optimizer chọn chiến lược dựa trên ước lượng chi phí; người dùng không nên mặc định một chiến lược luôn nhanh nhất.

## 8. Antijoin transformation trong MySQL

Antijoin là dạng biến đổi cho predicate phủ định như NOT EXISTS hoặc NOT IN. MySQL 8.0.17 trở lên hỗ trợ antijoin transformation cho nhiều dạng truy vấn phủ định đủ điều kiện.

Ví dụ:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Optimizer có thể thực thi như anti join: tìm các khách hàng không có match trong orders. Kế hoạch có thể dừng hoặc loại hàng ngoài ngay khi phát hiện match, tùy chiến lược thực thi.

### 8.1. Điều kiện NULL ảnh hưởng antijoin

Antijoin transformation không áp dụng được cho mọi biểu thức nullable vì phải giữ chính xác kết quả UNKNOWN của SQL. Đặc biệt, NOT IN với giá trị so sánh nullable có semantics khác với "không có hàng bằng giá trị này".

MySQL có một số dạng predicate phủ định mà có thể áp dụng antijoin trong những trường hợp nullable nhất định, ví dụ các biểu thức được viết tường minh để coi UNKNOWN như FALSE bằng IS NOT TRUE. Tuy nhiên, không nên dựa vào phép biến đổi đó thay cho việc hiểu truth table.

### 8.2. Dùng NOT EXISTS khi cần "không có hàng match"

~~~sql
SELECT p.product_id
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
);
~~~

Nếu product_id phía ngoài có thể NULL, truy vấn NOT EXISTS vẫn có thể trả hàng đó vì không có phép so sánh bằng nào TRUE. Nếu muốn loại NULL, thêm điều kiện p.product_id IS NOT NULL theo yêu cầu nghiệp vụ.

### 8.3. Antijoin và LEFT JOIN ... IS NULL

Optimizer có thể nhận diện một số mẫu LEFT JOIN ... IS NULL và dùng cách thực thi anti-join hiệu quả. Tuy nhiên, cần kiểm tra cột dùng trong IS NULL có được đảm bảo NOT NULL khi có match hay không. Nếu dùng một cột nullable của bảng trong, hàng match nhưng giá trị NULL có thể bị nhầm thành không match.

Ưu tiên NOT EXISTS khi mục tiêu là kiểm tra sự không tồn tại; dùng LEFT JOIN khi cần lấy thêm dữ liệu hoặc khi cấu trúc truy vấn dễ đọc hơn và đã xác định rõ cột kiểm tra.

## 9. Chọn index cho truy vấn semijoin và antijoin

Index tốt giúp optimizer kiểm tra match nhanh và giảm số hàng phải đọc.

### 9.1. Index trên cột tương quan

Với:

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

Một index có thể cần đánh giá:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

Index này hỗ trợ tìm đơn theo customer_id và status. Tùy chiến lược, index bắt đầu bằng status rồi customer_id cũng có thể hợp lý nếu optimizer bắt đầu từ các đơn PAID. Chọn thứ tự cột theo selectivity, workload và plan, không chỉ dựa vào một câu truy vấn.

### 9.2. Index phía ngoài

Nếu bảng customers có primary key trên customer_id, truy cập từng khách hàng đã có đường truy cập hiệu quả. Nếu điều kiện ngoài lọc theo region_id hoặc trạng thái, index phù hợp trên bảng ngoài có thể giảm số hàng cần kiểm tra.

### 9.3. Index cho antijoin

Với NOT EXISTS, index trên cột tương quan ở bảng trong thường rất quan trọng:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Index orders(customer_id) giúp kiểm tra nhanh có đơn nào khớp với từng khách hàng hay không. Nếu không có index, engine có thể phải quét nhiều hàng trong orders.

### 9.4. Không tạo index trùng lặp

Trước khi thêm index:

~~~sql
SHOW INDEX FROM orders;
~~~

Đọc execution plan:

~~~sql
EXPLAIN
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Kiểm tra key, type, rows, filtered và điều kiện được dùng để truy cập. Index giúp đọc nhanh hơn nhưng làm tăng chi phí INSERT/UPDATE/DELETE và dung lượng lưu trữ.

## 10. Đọc execution plan

Không thể kết luận semijoin đã được áp dụng chỉ bằng cách nhìn câu SQL. Dùng EXPLAIN để kiểm tra kế hoạch optimizer.

### 10.1. EXPLAIN dạng mặc định

~~~sql
EXPLAIN
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Trong output dạng tabular, xem các cột như select_type, table, type, possible_keys, key, rows, filtered và Extra. Subquery có thể được thể hiện dưới dạng SIMPLE/PRIMARY hoặc materialized/semijoin-related tùy chiến lược và phiên bản.

### 10.2. EXPLAIN FORMAT=TREE

~~~sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

TREE giúp nhìn thứ tự iterator và loại join. Tùy kế hoạch, có thể thấy node semijoin, nested loop, materialize hoặc node tương đương. Tên node và cách hiển thị phụ thuộc phiên bản MySQL.

### 10.3. EXPLAIN FORMAT=JSON

~~~sql
EXPLAIN FORMAT=JSON
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

JSON cung cấp cấu trúc query block, access path, estimated rows và thông tin materialization/semijoin khi được optimizer xuất ra. Dùng JSON khi cần kiểm tra chi tiết hoặc đưa plan vào công cụ phân tích.

### 10.4. EXPLAIN ANALYZE

MySQL 8.0.18+ hỗ trợ EXPLAIN ANALYZE cho SELECT tương thích. Lệnh này thực thi truy vấn và hiển thị số hàng, loops cùng thời gian thực tế:

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

Đối chiếu estimated rows với actual rows để phát hiện thống kê sai hoặc cardinality ước lượng lệch. EXPLAIN ANALYZE thực thi truy vấn thật và tiêu thụ tài nguyên; nên chạy trên lab/staging hoặc thời điểm đã đánh giá tải.

### 10.5. Dấu hiệu cần quan sát

- Semijoin hoặc antijoin node nếu plan hiển thị rõ.
- FirstMatch, LooseScan, Duplicate Weedout hoặc materialization trong output phù hợp.
- Index được chọn trên cột tương quan.
- Số hàng inner phải đọc để tìm match.
- Số vòng lặp của nested loop.
- Temporary table hoặc bước duplicate elimination.
- Chênh lệch estimated rows và actual rows.

Không phải mọi phiên bản đều in đúng cùng một nhãn. Đọc toàn bộ cấu trúc plan và so sánh với query semantics.

## 11. Optimizer switch và hints

MySQL cung cấp optimizer_switch để bật/tắt các nhóm tối ưu hóa. Có thể kiểm tra:

~~~sql
SELECT @@SESSION.optimizer_switch;
~~~

Các tùy chọn liên quan semijoin có thể gồm:

- semijoin: bật/tắt semijoin transformation.
- firstmatch: cho phép chiến lược FirstMatch.
- loosescan: cho phép LooseScan.
- duplicateweedout: cho phép Duplicate Weedout.
- materialization: cho phép materialization trong các ngữ cảnh optimizer hỗ trợ.

### 11.1. Thử tắt semijoin trong session lab

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;
SET SESSION optimizer_switch = 'semijoin=off';

EXPLAIN FORMAT=TREE
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

So sánh plan khi semijoin bật và tắt. Chỉ thay đổi session trong lab; không đặt GLOBAL chỉ để thử một truy vấn. Khi khôi phục, dùng đúng giá trị đã lưu để không vô tình ghi đè các optimizer setting khác.

### 11.2. Optimizer hints

MySQL hỗ trợ hints như SEMIJOIN() và NO_SEMIJOIN() để gợi ý lựa chọn semijoin strategy cho query block phù hợp. Có thể dùng QB_NAME() để đặt tên query block rồi tham chiếu từ hint ngoài.

Ví dụ minh họa cú pháp hint trên phiên bản hỗ trợ:

~~~sql
SELECT /*+ SEMIJOIN(@orders_subq FIRSTMATCH) */
       c.customer_id
FROM customers AS c
WHERE c.customer_id IN (
    SELECT /*+ QB_NAME(orders_subq) */
           o.customer_id
    FROM orders AS o
    WHERE o.status = 'PAID'
);
~~~

Hint chỉ là chỉ dẫn cho optimizer và chỉ có hiệu lực khi query block đủ điều kiện. Nếu cấu trúc truy vấn không thể semijoin hoặc strategy không phù hợp, hint có thể bị bỏ qua. Kiểm tra warning và execution plan; không kết luận hint được áp dụng chỉ vì câu SQL chạy thành công.

### 11.3. Không cố ép một chiến lược cho mọi dữ liệu

FirstMatch có thể tốt khi match dễ tìm; materialization có thể tốt khi tập inner nhỏ và tái sử dụng hiệu quả; LooseScan có thể tốt với index thích hợp. Dữ liệu thay đổi có thể khiến chiến lược tối ưu thay đổi. Hãy dùng hints để kiểm chứng giả thuyết hoặc xử lý trường hợp đã đo đạc, không rải hints theo thói quen.

## 12. Các mẫu viết lại truy vấn

### 12.1. JOIN gây duplicate: chuyển sang EXISTS

Truy vấn ban đầu:

~~~sql
SELECT DISTINCT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Nếu chỉ cần khách hàng có ít nhất một đơn PAID:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

EXISTS diễn đạt đúng mục tiêu, không cần tạo các hàng lặp do nhiều đơn rồi loại trùng bằng DISTINCT. Hai truy vấn có thể tương đương về tập kết quả trong điều kiện cột được chọn chỉ thuộc phía customers và semantics NULL/duplicate được giữ đúng.

### 12.2. NOT IN có NULL: chuyển sang NOT EXISTS

Truy vấn có rủi ro:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Nếu orders.customer_id có NULL, kết quả có thể không như mong muốn. Dùng NOT EXISTS để diễn đạt không có hàng match:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Nếu customer_id ở phía ngoài nullable và NULL phải bị loại, thêm c.customer_id IS NOT NULL. Hãy quyết định semantics trước khi viết lại.

### 12.3. Đếm số lượng không phải bài toán tồn tại

Nếu yêu cầu là khách hàng có ít nhất ba đơn, EXISTS đơn giản không đủ:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
) >= 3;
~~~

Có thể viết bằng derived aggregate:

~~~sql
SELECT c.customer_id
FROM customers AS c
JOIN (
    SELECT customer_id
    FROM orders
    GROUP BY customer_id
    HAVING COUNT(*) >= 3
) AS active_customers
  ON active_customers.customer_id = c.customer_id;
~~~

Không đổi truy vấn đếm thành EXISTS chỉ vì EXISTS có thể dừng ở match đầu tiên; điều đó làm thay đổi điều kiện từ ít nhất ba hàng thành ít nhất một hàng.

### 12.4. EXISTS với điều kiện bổ sung

~~~sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE EXISTS (
    SELECT 1
    FROM order_items AS oi
    JOIN orders AS o
      ON o.order_id = oi.order_id
    WHERE oi.product_id = p.product_id
      AND o.status = 'PAID'
      AND o.created_at >= '2026-01-01'
);
~~~

Semijoin vẫn chỉ trả sản phẩm có ít nhất một chi tiết đơn thuộc đơn PAID trong khoảng thời gian. Các bảng bên trong có thể JOIN với nhau; điều kiện tương quan với bảng ngoài xác định match.

## 13. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| NOT IN trả về 0 hàng bất ngờ | Subquery chứa NULL | Kiểm tra NULL; dùng NOT EXISTS nếu yêu cầu là không có match |
| JOIN trả khách hàng nhiều lần | Một khách có nhiều đơn | Dùng EXISTS nếu chỉ cần kiểm tra tồn tại |
| EXISTS chạy chậm | Thiếu index trên cột tương quan hoặc nhiều hàng inner phải kiểm tra | Đọc EXPLAIN, đánh giá index và access path |
| Semijoin không xuất hiện trong plan | Subquery không đủ điều kiện biến đổi hoặc optimizer chọn cách khác | Kiểm tra vị trí predicate, LIMIT, aggregate, HAVING, OR và phiên bản |
| Antijoin không được áp dụng | Biểu thức nullable hoặc query shape không đủ điều kiện | Xác định semantics NULL và đọc plan |
| Hint không có tác dụng | Hint sai query block, strategy không hợp lệ hoặc phép biến đổi bị cấm | Xem SHOW WARNINGS và EXPLAIN |
| Materialization tạo bảng tạm lớn | Tập inner lớn hoặc ít chọn lọc | Kiểm tra cardinality, điều kiện lọc và index |
| Thay NOT IN bằng NOT EXISTS làm thay đổi hàng có khóa NULL | Hai biểu thức có semantics khác nhau với NULL | Quy định rõ cách xử lý NULL ở phía ngoài và trong |
| Dùng EXISTS cho điều kiện "ít nhất N hàng" | EXISTS chỉ kiểm tra có ít nhất một hàng | Dùng aggregate COUNT/HAVING hoặc logic tương ứng |
| Dựa vào plan cũ sau khi dữ liệu tăng | Cardinality và chi phí đã thay đổi | Cập nhật thống kê khi phù hợp và đo lại EXPLAIN ANALYZE |

## 14. Bài thực hành: quan sát semijoin và antijoin

Thực hiện trên database lab MySQL 8.0. Bài tạo bảng riêng để kiểm tra duplicate, NULL và execution plan. Không chạy trên bảng production.

### 14.1. Tạo bảng mẫu

~~~sql
CREATE TABLE lab_customers (
    customer_id INT NOT NULL,
    full_name VARCHAR(80) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id INT NOT NULL,
    customer_id INT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_orders_customer_status (customer_id, status)
) ENGINE=InnoDB;

INSERT INTO lab_customers (customer_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung'),
    (5, 'Em');

INSERT INTO lab_orders (order_id, customer_id, status)
VALUES
    (101, 1, 'PAID'),
    (102, 1, 'PENDING'),
    (103, 2, 'PAID'),
    (104, 2, 'PAID'),
    (105, 4, 'CANCELLED'),
    (106, NULL, 'PAID');
~~~

Khách hàng 1 và 2 có đơn PAID; khách hàng 3 và 5 không có đơn; khách hàng 4 chỉ có đơn CANCELLED. Bảng orders có một customer_id NULL để kiểm tra NOT IN.

### 14.2. Bước 1 — Tìm khách hàng có đơn PAID bằng EXISTS

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả gồm khách hàng 1 và 2, mỗi khách hàng xuất hiện một lần dù khách hàng 2 có hai đơn PAID.

### 14.3. Bước 2 — So sánh với JOIN

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
~~~

Quan sát khách hàng 2 xuất hiện hai lần. Thêm DISTINCT để so sánh tập kết quả với EXISTS:

~~~sql
SELECT DISTINCT c.customer_id, c.full_name
FROM lab_customers AS c
JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Giải thích vì sao EXISTS không cần DISTINCT để loại duplicate phát sinh từ bảng orders.

### 14.4. Bước 3 — Tìm khách hàng không có đơn bằng NOT EXISTS

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả gồm khách hàng 3 và 5. Khách hàng 4 không được trả về vì có đơn CANCELLED; điều kiện trong truy vấn này kiểm tra mọi trạng thái đơn.

### 14.5. Bước 4 — Quan sát NOT IN có NULL

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM lab_orders AS o
)
ORDER BY c.customer_id;
~~~

Do subquery chứa NULL, phép NOT IN của các customer_id không match có thể là UNKNOWN; truy vấn có thể không trả về khách hàng 3 và 5. Sau đó loại NULL trong subquery:

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM lab_orders AS o
    WHERE o.customer_id IS NOT NULL
)
ORDER BY c.customer_id;
~~~

Kết quả lúc này có thể khớp NOT EXISTS vì customer_id phía ngoài là NOT NULL trong bảng lab_customers. Giải thích vai trò của từng điều kiện NULL.

### 14.6. Bước 5 — Kiểm tra semijoin plan

~~~sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Quan sát semijoin, nested loop, materialization hoặc cách trình bày tương đương. Bảng lab nhỏ có thể khiến optimizer chọn scan; điều đó không đủ để kết luận index không có ích với dữ liệu lớn.

### 14.7. Bước 6 — Kiểm tra antijoin plan

~~~sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Quan sát anti join hoặc kế hoạch tương đương. Đối chiếu với truy vấn NOT IN có NULL và giải thích vì sao optimizer phải bảo toàn semantics ba giá trị.

### 14.8. Bước 7 — Thử tắt semijoin trong session

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;
SET SESSION optimizer_switch = 'semijoin=off';

EXPLAIN FORMAT=TREE
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

So sánh plan với bước 5. Khôi phục session setting ngay sau khi thử nghiệm.

### 14.9. Bước 8 — Đo bằng EXPLAIN ANALYZE

Nếu server là MySQL 8.0.18 trở lên:

~~~sql
EXPLAIN ANALYZE
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Đọc actual rows, loops và thời gian. Dữ liệu lab rất nhỏ nên mục tiêu là hiểu plan, không dùng thời gian tuyệt đối để kết luận trên production.

### 14.10. Bước 9 — Dọn bảng lab

~~~sql
DROP TABLE lab_orders;
DROP TABLE lab_customers;
~~~

Chỉ xóa hai bảng lab vừa tạo.

**Kết quả cần đạt:** viết đúng EXISTS/IN cho semijoin và NOT EXISTS/NOT IN cho antijoin; giải thích được NULL; phân biệt semijoin với JOIN có duplicate; đọc plan cơ bản và so sánh khi tắt semijoin.

## 15. Nguyên tắc cần ghi nhớ

- EXISTS trả TRUE khi subquery có ít nhất một hàng; giá trị trong SELECT list của subquery không quyết định kết quả.
- IN kiểm tra thành viên của tập kết quả; NULL có thể làm phép so sánh thành UNKNOWN.
- Semijoin giữ hàng ngoài khi có ít nhất một match và không nhân bản hàng ngoài do nhiều hàng inner.
- Antijoin giữ hàng ngoài khi không có match.
- NOT IN rất nhạy với NULL ở subquery; NOT EXISTS thường phù hợp hơn khi ý định là "không có hàng match".
- NULL ở phía ngoài cũng có thể làm NOT IN và NOT EXISTS khác nhau; quy định rõ semantics trước khi viết lại.
- MySQL 8.0.16+ có thể biến đổi EXISTS đủ điều kiện thành semijoin; MySQL 8.0.17+ bổ sung antijoin transformation cho nhiều dạng phủ định.
- Semijoin có các chiến lược như FirstMatch, LooseScan, Duplicate Weedout và Materialization; table pullout là một phép biến đổi liên quan.
- Query shape, vị trí predicate, aggregate, HAVING, LIMIT, OR và cấu trúc khác có thể ngăn semijoin transformation.
- Index trên cột tương quan giúp kiểm tra match nhanh hơn; chọn thứ tự index theo dữ liệu và execution plan.
- Dùng EXPLAIN TREE/JSON để xem kế hoạch; EXPLAIN ANALYZE thực thi truy vấn thật và cung cấp số liệu thực tế từ MySQL 8.0.18+.
- Optimizer switch và hints chỉ hỗ trợ kiểm chứng hoặc điều khiển có chủ đích; không thay thế việc xác minh semantics và đo plan.
- Không đổi EXISTS thành JOIN nếu không xử lý duplicate; không đổi truy vấn đếm thành EXISTS nếu yêu cầu cần ít nhất N hàng.

Semijoin và antijoin giúp MySQL thực thi truy vấn tồn tại theo cách phù hợp với dữ liệu và index. Người viết SQL cần chọn đúng semantics trước, đặc biệt với NULL và duplicate; sau đó đọc execution plan để biết optimizer đã chọn chiến lược nào và liệu index có hỗ trợ tốt cho việc tìm match hay không.
