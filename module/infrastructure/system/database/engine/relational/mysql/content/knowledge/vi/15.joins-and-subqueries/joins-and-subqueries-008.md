# Single-row, multi-row và correlated subquery

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Subquery (truy vấn con) cho phép dùng kết quả của một câu SELECT bên trong câu SQL khác. Tùy số hàng và số cột mà subquery trả về, MySQL áp dụng các quy tắc khác nhau: scalar subquery, row subquery, multi-row subquery và các toán tử như IN, ANY, ALL, EXISTS.

Một khía cạnh khác là subquery có tham chiếu đến cột của truy vấn bên ngoài hay không. Subquery không tham chiếu truy vấn ngoài là uncorrelated; subquery có tham chiếu như vậy là correlated. Hai cách phân loại này độc lập: một correlated subquery có thể trả một giá trị duy nhất hoặc nhiều hàng. Hiểu đúng cardinality và phạm vi tham chiếu giúp tránh lỗi subquery trả nhiều hàng, lỗi logic với NULL và truy vấn chậm do thiếu index.

## 1. Subquery là gì?

Subquery là câu lệnh SELECT nằm bên trong một câu SQL khác. Truy vấn chứa subquery thường được gọi là outer query; SELECT bên trong là inner query.

Ví dụ tìm nhân viên có lương cao hơn mức lương trung bình toàn công ty:

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
);
~~~

Subquery tính mức lương trung bình; outer query dùng giá trị đó để lọc nhân viên. Vì subquery không tham chiếu alias hoặc cột của outer query, đây là uncorrelated scalar subquery.

Subquery có thể xuất hiện ở nhiều vị trí:

- Trong SELECT để tạo một biểu thức kết quả.
- Trong WHERE hoặc HAVING để lọc hàng hoặc nhóm.
- Trong FROM như một derived table.
- Trong các toán tử IN, ANY, ALL, EXISTS và NOT EXISTS.
- Trong một số biểu thức INSERT, UPDATE hoặc DELETE theo cú pháp MySQL hỗ trợ.

Bài học tập trung vào cardinality (số hàng, số cột) của subquery và mối quan hệ correlated/uncorrelated. Derived table trong FROM là một dạng sử dụng subquery; phần trọng tâm ở đây là cách outer query tiêu thụ kết quả của truy vấn con.

## 2. Hai chiều phân loại cần tách biệt

Subquery thường được phân loại theo hai câu hỏi:

1. **Trả về bao nhiêu hàng và bao nhiêu cột?** Một giá trị, một hàng nhiều cột hay nhiều hàng.
2. **Có tham chiếu outer query không?** Uncorrelated hay correlated.

| Loại | Cardinality | Cách outer query sử dụng |
|---|---|---|
| Scalar subquery | Một cột, tối đa một hàng | Dùng như một giá trị đơn |
| Row subquery | Một hàng, có thể nhiều cột | Dùng trong so sánh theo tuple |
| Multi-row subquery | Nhiều hàng; thường một cột, hoặc nhiều cột trong ngữ cảnh tuple | Dùng với IN, ANY, ALL hoặc EXISTS |
| Uncorrelated subquery | Có thể thuộc bất kỳ loại nào ở trên | Không tham chiếu cột của outer query |
| Correlated subquery | Có thể thuộc bất kỳ loại nào ở trên | Tham chiếu một hoặc nhiều cột từ outer query |

Vì vậy, không nên xem "single-row", "multi-row" và "correlated" là ba loại loại trừ lẫn nhau. Một scalar subquery hoàn toàn có thể là correlated; một multi-row subquery cũng có thể là correlated.

## 3. Scalar subquery: một cột, tối đa một hàng

Scalar subquery trả về đúng một cột và tối đa một hàng. Outer query có thể sử dụng nó ở vị trí cần một giá trị đơn, chẳng hạn trong SELECT, WHERE hoặc biểu thức tính toán.

### 3.1. So sánh với giá trị từ subquery

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
    WHERE department_id = 10
);
~~~

AVG() không có GROUP BY trả về một hàng với một cột. Nếu phòng ban 10 có nhân viên, giá trị là mức lương trung bình; nếu không có giá trị đầu vào, AVG trả NULL. Subquery vẫn có một hàng kết quả, nhưng giá trị trong hàng là NULL.

### 3.2. Dùng scalar subquery trong SELECT

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.price,
    (SELECT AVG(price) FROM products) AS average_price
FROM products AS p;
~~~

Giá trị average_price được hiển thị cạnh mỗi sản phẩm. Đây là một subquery không tương quan vì không dùng p trong inner query. Optimizer có thể xử lý subquery độc lập hoặc biến đổi kế hoạch; không nên suy luận số lần thực thi vật lý chỉ từ cách viết SQL.

### 3.3. Subquery không có hàng và giá trị NULL

Nếu scalar subquery trả về 0 hàng, giá trị của nó được xem là NULL:

~~~sql
SELECT
    (SELECT department_name
     FROM departments
     WHERE department_id = -1) AS department_name;
~~~

Nếu không có department_id = -1, kết quả SELECT ngoài vẫn trả một hàng, trong đó department_name là NULL.

Khi scalar subquery được dùng trong điều kiện:

~~~sql
SELECT employee_id, full_name
FROM employees
WHERE department_id = (
    SELECT department_id
    FROM departments
    WHERE department_name = 'Unknown Department'
);
~~~

Nếu subquery không trả hàng, phép so sánh trở thành so sánh với NULL và có kết quả UNKNOWN. WHERE không giữ hàng nào. Vì vậy, cần phân biệt "scalar subquery không có hàng" với "outer query không tìm thấy bản ghi".

### 3.4. Subquery trả nhiều hơn một hàng sẽ lỗi

Scalar subquery không được trả nhiều hơn một hàng. Ví dụ:

~~~sql
-- Có thể lỗi nếu nhiều phòng ban cùng location_id
SELECT employee_id, full_name
FROM employees
WHERE department_id = (
    SELECT department_id
    FROM departments
    WHERE location_id = 1
);
~~~

Nếu subquery trả nhiều hàng, MySQL báo lỗi 1242: Subquery returns more than 1 row. Nếu subquery trả nhiều cột ở vị trí cần một giá trị đơn, MySQL báo lỗi về số cột, thường là lỗi 1241: Operand should contain 1 column(s).

Không sửa lỗi bằng cách thêm LIMIT 1 một cách máy móc. Trước tiên, xác định nghiệp vụ mong muốn là:

- Chỉ có một bản ghi: bảo đảm bằng PRIMARY KEY hoặc UNIQUE constraint.
- Chấp nhận nhiều bản ghi: dùng IN, EXISTS, ANY hoặc ALL tùy ý nghĩa.
- Chọn bản ghi theo thứ tự: dùng ORDER BY với tiêu chí và khóa phụ phân định rõ ràng cùng LIMIT 1.

### 3.5. Dùng ORDER BY và LIMIT 1 có chủ đích

Nếu nghiệp vụ cần bản ghi mới nhất:

~~~sql
SELECT customer_id,
       (
           SELECT o.status
           FROM orders AS o
           WHERE o.customer_id = c.customer_id
           ORDER BY o.created_at DESC, o.order_id DESC
           LIMIT 1
       ) AS latest_order_status
FROM customers AS c;
~~~

ORDER BY xác định thứ tự ưu tiên; order_id là tiêu chí phụ để kết quả ổn định khi nhiều đơn có cùng created_at. LIMIT 1 bảo đảm subquery trả tối đa một hàng. Nếu không có đơn, scalar subquery trả NULL.

Nếu yêu cầu thực chất là một bản ghi duy nhất theo khóa, nên dựa vào constraint thay vì dùng LIMIT 1 để che dữ liệu không nhất quán.

### 3.6. Aggregate có và không có GROUP BY

Aggregate không có GROUP BY như COUNT(*), MAX(), MIN(), AVG() thường tạo một hàng kết quả ngay cả khi tập đầu vào rỗng:

~~~sql
SELECT
    COUNT(*) AS employee_count,
    AVG(salary) AS average_salary
FROM employees
WHERE department_id = -1;
~~~

Truy vấn trả một hàng: employee_count = 0 và average_salary = NULL. Nhưng khi thêm GROUP BY, nếu không có hàng đầu vào thì không có nhóm nào, nên subquery có thể trả 0 hàng:

~~~sql
SELECT AVG(salary)
FROM employees
WHERE department_id = -1
GROUP BY department_id;
~~~

Điểm này quan trọng khi dùng aggregate làm scalar subquery. Hãy kiểm tra GROUP BY và cardinality thực tế.

## 4. Row subquery: một hàng có nhiều cột

Row subquery trả về một hàng gồm nhiều cột. Nó được dùng trong ngữ cảnh so sánh theo tuple (row constructor).

Ví dụ tìm phòng ban có department_id và location_id khớp với một cặp xác định:

~~~sql
SELECT department_name
FROM departments
WHERE (department_id, location_id) = (
    SELECT department_id, location_id
    FROM departments
    WHERE department_name = 'Engineering'
);
~~~

Inner query phải trả tối đa một hàng và đúng số cột tương ứng với tuple bên trái. Nếu trả nhiều hàng, so sánh bằng sẽ gặp lỗi scalar/row subquery trả nhiều hàng.

### 4.1. So sánh tuple với giá trị tường minh

~~~sql
SELECT *
FROM employees
WHERE (department_id, salary) = (10, 1200.00);
~~~

Điều kiện yêu cầu cả department_id và salary cùng khớp. Tuple comparison giúp thể hiện một điều kiện nhiều thành phần, nhưng vẫn phải xem xét NULL: nếu một thành phần làm phép so sánh không xác định, kết quả tổng thể có thể là UNKNOWN.

### 4.2. Row subquery với nhiều cột

Một subquery nhiều cột không thể đặt trực tiếp vào vị trí scalar:

~~~sql
-- Không hợp lệ: outer expression cần một giá trị đơn
SELECT (SELECT department_id, location_id FROM departments);
~~~

Nếu muốn lấy hai giá trị, hãy dùng row context hoặc JOIN phù hợp:

~~~sql
SELECT d.department_id, d.location_id
FROM departments AS d
WHERE (d.department_id, d.location_id) = (
    SELECT x.department_id, x.location_id
    FROM departments AS x
    WHERE x.department_name = 'Engineering'
);
~~~

Nếu mục tiêu chỉ là lấy cột của cùng bảng, truy vấn trực tiếp hoặc JOIN thường dễ hiểu hơn việc bọc lại bằng subquery.

## 5. Multi-row subquery

Multi-row subquery có thể trả về nhiều hàng. Khi outer query cần so sánh với tập kết quả, không dùng toán tử bằng đơn thông thường như thể inner query chỉ có một giá trị. Hãy dùng toán tử phù hợp với ngữ nghĩa tập hợp.

### 5.1. IN: có thuộc tập kết quả?

IN kiểm tra một biểu thức có bằng một trong các giá trị của danh sách hoặc subquery hay không:

~~~sql
SELECT employee_id, full_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1
);
~~~

Subquery có thể trả nhiều department_id. Outer query giữ nhân viên thuộc ít nhất một phòng ban trong tập đó. Các giá trị trùng trong kết quả subquery không làm nhân bản hàng outer query; IN là phép kiểm tra membership, không phải JOIN.

IN cũng có thể dùng với danh sách literal:

~~~sql
SELECT *
FROM orders
WHERE status IN ('PAID', 'SHIPPED', 'COMPLETED');
~~~

### Ví dụ: tuple IN với subquery nhiều cột và nhiều hàng

Subquery trong IN cũng có thể trả nhiều cột khi biểu thức bên trái là row constructor có cùng số thành phần:

~~~sql
SELECT e.employee_id, e.department_id, e.salary
FROM employees AS e
WHERE (e.department_id, e.salary) IN (
    SELECT department_id, MIN(salary)
    FROM employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
);
~~~

Inner query trả một cặp department_id và mức lương thấp nhất cho mỗi phòng ban. Outer query lấy tất cả nhân viên có đúng cặp giá trị đó; nếu nhiều nhân viên đồng hạng thấp nhất trong cùng phòng ban, tất cả đều được giữ. Hai phía phải có cùng số thành phần và kiểu dữ liệu có thể so sánh. Điều kiện loại department_id NULL vì phép so sánh tuple có NULL không tạo kết quả TRUE theo phép bằng thông thường.

### 5.2. IN tương đương = ANY

Trong MySQL, biểu thức:

~~~sql
salary = ANY (
    SELECT salary
    FROM employees
    WHERE department_id = 10
)
~~~

có ý nghĩa tương đương:

~~~sql
salary IN (
    SELECT salary
    FROM employees
    WHERE department_id = 10
)
~~~

ANY trả TRUE nếu phép so sánh đúng với ít nhất một giá trị trong tập kết quả. SOME là synonym của ANY.

### 5.3. ANY/SOME: chỉ cần một giá trị thỏa

Ví dụ tìm nhân viên có lương cao hơn ít nhất một nhân viên trong phòng ban 20:

~~~sql
SELECT e.employee_id, e.full_name, e.salary
FROM employees AS e
WHERE e.salary > ANY (
    SELECT e2.salary
    FROM employees AS e2
    WHERE e2.department_id = 20
);
~~~

Điều kiện đúng nếu tồn tại ít nhất một mức lương trong phòng ban 20 nhỏ hơn lương của nhân viên ngoài đang xét.

Với tập không rỗng và không chứa NULL, có thể hiểu:

- x > ANY(S) gần tương đương x > MIN(S).
- x < ANY(S) gần tương đương x < MAX(S).

Đây chỉ là cách diễn giải trực quan trong trường hợp dữ liệu không NULL; không thay thế quy tắc logic ba giá trị khi tập chứa NULL.

### 5.4. ALL: phải thỏa với mọi giá trị

Ví dụ tìm nhân viên có lương cao hơn tất cả nhân viên trong phòng ban 20:

~~~sql
SELECT e.employee_id, e.full_name, e.salary
FROM employees AS e
WHERE e.salary > ALL (
    SELECT e2.salary
    FROM employees AS e2
    WHERE e2.department_id = 20
);
~~~

Điều kiện đúng nếu lương của nhân viên outer query lớn hơn mọi mức lương trong tập con.

Với tập không rỗng và không có NULL:

- x > ALL(S) tương đương x > MAX(S).
- x < ALL(S) tương đương x < MIN(S).

Nếu cần xử lý NULL, hãy phân tích rõ semantics thay vì thay ALL bằng MAX/MIN một cách tự động.

### 5.5. ANY và ALL với tập rỗng

Quy tắc logic quan trọng:

- ANY trên tập rỗng trả FALSE vì không tồn tại phần tử nào thỏa.
- ALL trên tập rỗng trả TRUE vì không có phần tử nào vi phạm điều kiện.

Điều này có thể gây bất ngờ nếu subquery không trả hàng:

~~~sql
SELECT
    10 > ANY (SELECT salary FROM employees WHERE department_id = -1)
        AS greater_than_any,
    10 > ALL (SELECT salary FROM employees WHERE department_id = -1)
        AS greater_than_all;
~~~

Kết quả lần lượt là FALSE và TRUE. Đây là quy tắc của phép lượng từ logic, không phải lỗi của MySQL.

### 5.6. NULL trong IN, ANY và ALL

Nếu tập kết quả chứa NULL và không có giá trị không NULL làm phép so sánh đúng, kết quả có thể là UNKNOWN:

~~~sql
SELECT 10 IN (5, 20, NULL) AS in_result,
       10 NOT IN (5, 20, NULL) AS not_in_result;
~~~

Không có giá trị 10 trong các phần tử xác định; phép so sánh với NULL không thể kết luận. Vì vậy IN và NOT IN đều có thể trả NULL/UNKNOWN trong trường hợp này.

Trong WHERE, UNKNOWN bị loại giống FALSE. Đây là nguyên nhân phổ biến khiến NOT IN không trả những hàng mà người viết nghĩ là "không có trong danh sách".

## 6. EXISTS và NOT EXISTS

EXISTS kiểm tra subquery có trả ít nhất một hàng hay không. Nó không cần biết giá trị của các cột trong hàng đó:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Truy vấn lấy khách hàng có ít nhất một đơn hàng. SELECT 1 là quy ước dễ đọc; EXISTS quan tâm sự tồn tại của hàng, không dùng giá trị 1 để so sánh.

### 6.1. EXISTS không bị ảnh hưởng bởi giá trị NULL trong danh sách SELECT

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT NULL
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Kết quả vẫn dựa trên việc có hàng khớp hay không. Một hàng mà SELECT NULL trả về vẫn là một hàng; EXISTS trả TRUE khi subquery có ít nhất một hàng.

### 6.2. NOT EXISTS: không có hàng liên quan

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Truy vấn lấy khách hàng chưa có đơn hàng. NOT EXISTS thường là lựa chọn rõ ràng để diễn đạt anti-join (tìm hàng ở bảng ngoài không có bản ghi liên quan).

### 6.3. So sánh NOT EXISTS với NOT IN

NOT IN:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Nếu subquery có một customer_id NULL, các phép so sánh không khớp có thể trở thành UNKNOWN và làm truy vấn không trả hàng như dự kiến.

NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

NULL ở một hàng orders không tự làm điều kiện NOT EXISTS trở thành UNKNOWN; phép so sánh đó không tìm thấy hàng khớp. Tuy nhiên, nếu c.customer_id ở outer query là NULL, phép bằng vẫn UNKNOWN và subquery không tìm thấy hàng khớp; NOT EXISTS khi đó có thể trả TRUE. Hãy xác định liệu khóa ngoài có thể NULL hay không và ý nghĩa nghiệp vụ của hàng đó.

Nếu vẫn dùng NOT IN, có thể loại NULL khỏi subquery:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.customer_id IS NOT NULL
);
~~~

Điều kiện lọc NULL trong subquery giải quyết một bẫy phổ biến, nhưng vẫn cần quyết định cách xử lý giá trị NULL ở biểu thức bên trái.

## 7. Correlated và uncorrelated subquery

### 7.1. Uncorrelated subquery

Uncorrelated subquery không tham chiếu cột của outer query. Ví dụ:

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
);
~~~

Inner query có thể được đánh giá độc lập về mặt logic. Optimizer quyết định cách thực thi phù hợp; có thể tính một lần, materialize hoặc biến đổi biểu thức tùy truy vấn và phiên bản. Không nên giả định một cách thực thi vật lý cố định.

### 7.2. Correlated subquery

Correlated subquery tham chiếu một cột từ outer query:

~~~sql
SELECT e.employee_id, e.full_name, e.salary
FROM employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees AS e2
    WHERE e2.department_id = e.department_id
);
~~~

Điều kiện e2.department_id = e.department_id dùng alias e từ outer query. Mỗi hàng nhân viên được so sánh với mức trung bình của chính phòng ban nhân viên đó.

Subquery có quan hệ logic với hàng ngoài. Cách viết này không khẳng định MySQL nhất thiết chạy inner query độc lập một lần cho từng hàng; optimizer có thể biến đổi một số correlated subquery thành kế hoạch khác. Hãy xem EXPLAIN để biết kế hoạch cụ thể.

### 7.3. Correlated scalar subquery trong SELECT

~~~sql
SELECT c.customer_id,
       c.full_name,
       (
           SELECT COUNT(*)
           FROM orders AS o
           WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers AS c;
~~~

Subquery tham chiếu c.customer_id, nên đây là correlated scalar subquery. COUNT(*) không có GROUP BY trả về một hàng kể cả khi không có đơn; giá trị đếm khi đó là 0.

### 7.4. Correlated EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE EXISTS (
    SELECT 1
    FROM employees AS e
    WHERE e.department_id = d.department_id
      AND e.salary > 1000
);
~~~

Truy vấn lấy phòng ban có ít nhất một nhân viên lương trên 1000. Điều kiện e.department_id = d.department_id liên kết subquery với hàng phòng ban hiện tại.

### 7.5. Correlated NOT EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees AS e
    WHERE e.department_id = d.department_id
);
~~~

Truy vấn lấy phòng ban chưa có nhân viên. Đây là một anti-join correlated.

### 7.6. Correlated multi-row subquery

Correlated subquery không nhất thiết phải là scalar. Ví dụ, tìm sản phẩm có giá cao hơn mọi sản phẩm cùng danh mục:

~~~sql
SELECT p.product_id, p.category_id, p.price
FROM products AS p
WHERE p.price > ALL (
    SELECT p2.price
    FROM products AS p2
    WHERE p2.category_id = p.category_id
      AND p2.product_id <> p.product_id
);
~~~

Subquery tham chiếu p.category_id và p.product_id từ outer query, đồng thời có thể trả nhiều giá. Đây là correlated multi-row subquery. Cần xem xét danh mục chỉ có một sản phẩm: inner query rỗng khiến > ALL trả TRUE theo quy tắc tập rỗng. Nếu nghiệp vụ yêu cầu ít nhất một sản phẩm so sánh khác, phải thêm điều kiện EXISTS hoặc điều kiện tương ứng.

## 8. Chọn loại subquery theo ý định

| Ý định nghiệp vụ | Cách viết thường phù hợp | Lý do |
|---|---|---|
| So sánh với một giá trị tổng hợp | Scalar subquery | Kết quả là một giá trị |
| So sánh một cặp hoặc bộ giá trị | Row subquery | Đối chiếu tuple nhiều cột |
| Kiểm tra một giá trị thuộc tập | IN | Diễn đạt membership |
| So sánh với ít nhất một giá trị | ANY/SOME | Lượng từ tồn tại |
| So sánh với mọi giá trị | ALL | Lượng từ phổ quát |
| Kiểm tra có bản ghi liên quan | EXISTS | Chỉ cần biết có hàng |
| Kiểm tra không có bản ghi liên quan | NOT EXISTS | Diễn đạt anti-join, tránh bẫy NULL của NOT IN |
| Tạo một giá trị phụ thuộc hàng ngoài | Correlated scalar subquery | Có thể tham chiếu alias outer query |

Không chọn EXISTS chỉ vì nó "nhanh hơn IN" trong mọi trường hợp. Optimizer MySQL có thể chuyển một số truy vấn IN/EXISTS thành semijoin hoặc áp dụng chiến lược khác. Hãy viết theo ngữ nghĩa đúng, sau đó kiểm tra kế hoạch và hiệu năng.

## 9. Viết lại subquery thành JOIN hoặc aggregate

Một số subquery có thể được biểu diễn bằng JOIN, nhưng hai cách viết không phải lúc nào cũng tương đương về số hàng.

### 9.1. Scalar aggregate và derived table

Truy vấn tương quan tính số đơn của mỗi khách:

~~~sql
SELECT c.customer_id,
       (
           SELECT COUNT(*)
           FROM orders AS o
           WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers AS c;
~~~

Có thể viết bằng derived table đã tổng hợp:

~~~sql
SELECT c.customer_id,
       COALESCE(order_counts.order_count, 0) AS order_count
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS order_counts
  ON order_counts.customer_id = c.customer_id;
~~~

Derived table tạo tối đa một hàng cho mỗi customer_id. LEFT JOIN giữ khách chưa có đơn; COALESCE chuyển giá trị thiếu của derived table thành 0. Hai cách diễn đạt cùng mục tiêu nếu customer_id và cách xử lý NULL được xác định phù hợp.

### 9.2. EXISTS và JOIN có thể tạo cardinality khác nhau

EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

JOIN:

~~~sql
SELECT c.customer_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Nếu một khách có ba đơn, EXISTS vẫn trả một hàng cho khách; JOIN trả ba hàng nếu không có DISTINCT. Muốn chuyển EXISTS thành JOIN mà giữ một hàng cho mỗi khách, cần dùng DISTINCT, GROUP BY hoặc một tập orders đã khử về một hàng mỗi customer. Đừng bỏ qua khác biệt cardinality.

### 9.3. NOT EXISTS và LEFT JOIN IS NULL

Có thể biểu diễn anti-join bằng LEFT JOIN:

~~~sql
SELECT c.customer_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

order_id phải là cột được bảo đảm NOT NULL ở hàng orders thật, thường là primary key. Nếu kiểm tra một cột nullable như delivery_note, hàng có đơn nhưng delivery_note NULL có thể bị nhận nhầm là không có đơn.

NOT EXISTS thường trực tiếp thể hiện ý định và tránh phải chọn cột phía phải làm dấu hiệu không khớp.

## 10. Hiệu năng và kế hoạch thực thi

Subquery không mặc nhiên chậm. Hiệu năng phụ thuộc cardinality, index, thống kê, cách viết, phiên bản và chiến lược optimizer.

### 10.1. Index cho correlated lookup

Với correlated subquery:

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

Index có thể hữu ích trên các cột lọc và nối ở bảng con:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

Thứ tự cột trong composite index nên dựa trên điều kiện truy vấn, các truy vấn khác và phân bố dữ liệu. Không tạo index chỉ vì một ví dụ; kiểm tra index hiện có và EXPLAIN trước.

### 10.2. Index cho correlated aggregate

Với subquery tính AVG theo phòng ban:

~~~sql
SELECT e.employee_id, e.salary
FROM employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees AS e2
    WHERE e2.department_id = e.department_id
);
~~~

Index bắt đầu bằng department_id có thể giúp lấy các hàng của phòng ban; thêm salary có thể hỗ trợ truy cập dữ liệu cần tổng hợp:

~~~sql
CREATE INDEX ix_employees_department_salary
ON employees (department_id, salary);
~~~

Khả năng cải thiện phụ thuộc kích thước bảng, tỷ lệ hàng mỗi phòng ban, covering, thống kê và kế hoạch optimizer. Aggregate vẫn phải xử lý các giá trị phù hợp; index không biến mọi truy vấn thành O(1).

### 10.3. Đọc EXPLAIN

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

Kiểm tra:

- Bảng nào được đọc trước và thứ tự truy cập.
- access type như const, eq_ref, ref, range, index hoặc ALL.
- key được chọn và key_len.
- rows ước lượng và filtered.
- Subquery có được chuyển thành semijoin, materialize hoặc vẫn là dependent subquery hay không.

Tên và cách hiển thị plan có thể khác giữa phiên bản MySQL. Đọc EXPLAIN theo toàn bộ plan, không chỉ nhìn một dòng.

### 10.4. EXPLAIN ANALYZE

MySQL 8.0.18+ hỗ trợ EXPLAIN ANALYZE cho các câu SELECT tương thích. Lệnh này thực thi truy vấn và hiển thị thời gian, số vòng lặp cùng số hàng thực tế của iterator:

~~~sql
EXPLAIN ANALYZE
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Vì EXPLAIN ANALYZE thực sự chạy truy vấn, chỉ dùng khi đã đánh giá chi phí và tải trên môi trường phù hợp. Không chạy truy vấn nặng trên production chỉ để lấy plan nếu chưa có đánh giá tác động.

### 10.5. Semijoin và materialization

MySQL optimizer có thể biến đổi một số subquery IN hoặc EXISTS thành semijoin. Semijoin giữ hàng outer khi có ít nhất một hàng inner khớp mà không nhân bản outer row theo số hàng inner. Một số subquery khác có thể được materialize thành tập trung gian hoặc dùng chiến lược khác.

Khả năng biến đổi phụ thuộc cấu trúc subquery, vị trí xuất hiện, aggregate, LIMIT, UNION và phiên bản. Không tự giả định mọi correlated subquery đều bị chạy lại nguyên vẹn cho từng hàng outer hoặc mọi IN đều materialize; hãy kiểm tra EXPLAIN trên phiên bản thực tế.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Subquery returns more than 1 row (1242) | Dùng scalar context nhưng inner query trả nhiều hàng | Kiểm tra uniqueness; dùng IN/EXISTS/ANY/ALL hoặc chọn hàng có thứ tự rõ |
| Operand should contain 1 column(s) (1241) | Scalar context nhận subquery nhiều cột | Chỉ trả một cột hoặc dùng row comparison đúng số thành phần |
| Điều kiện bằng scalar subquery không trả hàng | Inner query không có hàng nên scalar result là NULL; phép so sánh thành UNKNOWN | Kiểm tra dữ liệu và quyết định có cần COALESCE hay EXISTS không |
| NOT IN không trả hàng mong đợi | Subquery chứa NULL | Dùng NOT EXISTS hoặc lọc NULL trong subquery |
| JOIN thay thế EXISTS làm hàng bị lặp | JOIN trả một hàng cho mỗi hàng khớp | Giữ EXISTS hoặc tổng hợp/khử trùng theo khóa đúng |
| Correlated subquery chậm | Thiếu index trên cột liên kết/lọc hoặc outer set quá lớn | Kiểm tra EXPLAIN, index và cân nhắc aggregate/derived table |
| LIMIT 1 trả kết quả không ổn định | ORDER BY thiếu tiêu chí phân định khi có giá trị bằng nhau | Thêm khóa duy nhất làm tie-breaker |
| ANY/ALL cho kết quả bất ngờ khi tập rỗng | ANY(empty) là FALSE, ALL(empty) là TRUE | Xác định hành vi nghiệp vụ với tập không có phần tử |
| So sánh ANY/ALL trả NULL | Có NULL trong tập và không có kết quả TRUE/FALSE quyết định | Lọc NULL nếu phù hợp hoặc xử lý logic ba giá trị tường minh |

## 12. Quy trình chọn và kiểm tra subquery

Khi thiết kế một truy vấn con:

1. Xác định outer query cần một giá trị, một tuple hay một tập hàng.
2. Kiểm tra số cột subquery trả về có phù hợp với vị trí sử dụng không.
3. Xác định cardinality được bảo đảm bằng khóa, aggregate, GROUP BY hay điều kiện lọc.
4. Nếu dùng scalar context, chứng minh subquery trả tối đa một hàng; không dùng LIMIT 1 để che dữ liệu trùng.
5. Xác định subquery có tham chiếu outer alias không; nếu có, ghi rõ quan hệ tương quan.
6. Phân tích trường hợp subquery rỗng và giá trị NULL.
7. Chọn IN, ANY, ALL, EXISTS hoặc NOT EXISTS theo ý nghĩa logic.
8. Kiểm tra số hàng kết quả nếu viết lại thành JOIN; bảo đảm không tạo fan-out ngoài ý muốn.
9. Đọc EXPLAIN và kiểm tra index trên cột liên kết/lọc.
10. So sánh kết quả trên dữ liệu biên: không có hàng, một hàng, nhiều hàng, giá trị trùng và NULL.

## 13. Bài thực hành: single-row, multi-row và correlated subquery

Thực hiện trong database lab hoặc môi trường phát triển mà bạn được phép tạo bảng. Các ví dụ dùng MySQL 8.0; phần cơ bản có thể chạy trên các phiên bản cũ hơn nếu không dùng CTE hay tính năng mới.

### 13.1. Tạo dữ liệu mẫu

~~~sql
CREATE TABLE lab_departments (
    department_id INT NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    location_id INT NOT NULL,
    PRIMARY KEY (department_id)
) ENGINE=InnoDB;

CREATE TABLE lab_employees (
    employee_id INT NOT NULL,
    department_id INT NULL,
    full_name VARCHAR(100) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    manager_id INT NULL,
    PRIMARY KEY (employee_id),
    KEY ix_lab_employee_department_salary (department_id, salary),
    CONSTRAINT fk_lab_employee_department
      FOREIGN KEY (department_id)
      REFERENCES lab_departments (department_id)
) ENGINE=InnoDB;

CREATE TABLE lab_customers (
    customer_id INT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id INT NOT NULL,
    customer_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_order_customer_status (customer_id, status),
    CONSTRAINT fk_lab_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customers (customer_id)
) ENGINE=InnoDB;
~~~

Nạp dữ liệu:

~~~sql
INSERT INTO lab_departments
    (department_id, department_name, location_id)
VALUES
    (10, 'Engineering', 1),
    (20, 'Sales', 1),
    (30, 'Operations', 2);

INSERT INTO lab_employees
    (employee_id, department_id, full_name, salary, manager_id)
VALUES
    (1, 10, 'An', 1000.00, NULL),
    (2, 10, 'Binh', 1200.00, 1),
    (3, 20, 'Chi', 900.00, NULL),
    (4, 20, 'Dung', 900.00, 3),
    (5, 30, 'Em', 1500.00, NULL),
    (6, NULL, 'Giang', 800.00, NULL);

INSERT INTO lab_customers (customer_id, full_name)
VALUES (1, 'Lan'), (2, 'Minh'), (3, 'Phuong');

INSERT INTO lab_orders (order_id, customer_id, status)
VALUES
    (101, 1, 'PAID'),
    (102, 1, 'PENDING'),
    (103, 2, 'PAID');
~~~

### 13.2. Bước 1 — Scalar subquery

Tìm nhân viên có lương cao hơn lương trung bình toàn công ty:

~~~sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > (
    SELECT AVG(salary)
    FROM lab_employees
);
~~~

Giải thích vì sao subquery là scalar và không correlated. Thử thêm WHERE department_id = 10 vào inner query để đổi phạm vi trung bình.

### 13.3. Bước 2 — Scalar subquery không có hàng

~~~sql
SELECT (
    SELECT department_name
    FROM lab_departments
    WHERE department_id = 999
) AS missing_department;
~~~

Quan sát kết quả là một hàng chứa NULL. Sau đó dùng scalar subquery này trong điều kiện WHERE và giải thích vì sao không có hàng outer nào được giữ.

### 13.4. Bước 3 — Phát hiện lỗi cardinality

~~~sql
SELECT employee_id, full_name
FROM lab_employees
WHERE department_id = (
    SELECT department_id
    FROM lab_departments
    WHERE location_id = 1
);
~~~

Inner query trả hai department_id nên scalar comparison báo lỗi 1242. Sửa bằng IN:

~~~sql
SELECT employee_id, full_name
FROM lab_employees
WHERE department_id IN (
    SELECT department_id
    FROM lab_departments
    WHERE location_id = 1
);
~~~

So sánh hai cách viết và giải thích vì sao IN phù hợp với tập nhiều giá trị.

### 13.5. Bước 4 — ANY và ALL

~~~sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > ANY (
    SELECT salary
    FROM lab_employees
    WHERE department_id = 20
);

SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > ALL (
    SELECT salary
    FROM lab_employees
    WHERE department_id = 20
);
~~~

Đối chiếu tập kết quả: truy vấn ANY cần lớn hơn ít nhất một nhân viên phòng Sales; truy vấn ALL cần lớn hơn mọi nhân viên phòng Sales. Thử đổi department_id thành 999 để quan sát semantics của tập rỗng.

### 13.6. Bước 5 — EXISTS và NOT EXISTS

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);

SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Truy vấn đầu tìm khách có đơn; truy vấn sau tìm khách chưa có đơn. Khách hàng số 3 không có đơn nên chỉ xuất hiện ở truy vấn NOT EXISTS.

### 13.7. Bước 6 — Correlated scalar subquery

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       e.salary,
       (
           SELECT AVG(e2.salary)
           FROM lab_employees AS e2
           WHERE e2.department_id = e.department_id
       ) AS department_average
FROM lab_employees AS e;
~~~

Mỗi hàng ngoài tham chiếu department_id của chính nhân viên đó. Quan sát nhân viên không có department_id: điều kiện e2.department_id = NULL không khớp hàng nào và AVG không có giá trị đầu vào nên trả NULL.

### 13.8. Bước 7 — Correlated EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM lab_departments AS d
WHERE EXISTS (
    SELECT 1
    FROM lab_employees AS e
    WHERE e.department_id = d.department_id
      AND e.salary >= 1000
);
~~~

Truy vấn tìm phòng ban có ít nhất một nhân viên đạt ngưỡng lương. Hãy giải thích alias d được tham chiếu bên trong subquery và vì sao đây là correlated subquery.

### 13.9. Bước 8 — So sánh EXISTS và JOIN

~~~sql
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);

SELECT c.customer_id
FROM lab_customers AS c
JOIN lab_orders AS o
  ON o.customer_id = c.customer_id;
~~~

Khách hàng 1 có hai đơn nên xuất hiện một lần trong kết quả EXISTS nhưng hai lần trong kết quả JOIN. Giải thích cardinality và thử dùng DISTINCT nếu mục tiêu là danh sách khách hàng duy nhất.

### 13.10. Bước 9 — Đọc kế hoạch

~~~sql
EXPLAIN
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Quan sát index ix_lab_order_customer_status và cách optimizer xử lý EXISTS. Nếu server MySQL 8.0.18+ và tải lab phù hợp, có thể thử EXPLAIN ANALYZE để xem số hàng và thời gian thực tế.

### 13.11. Bước 10 — Dọn dữ liệu lab

~~~sql
DROP TABLE lab_orders;
DROP TABLE lab_customers;
DROP TABLE lab_employees;
DROP TABLE lab_departments;
~~~

Xóa bảng con trước bảng cha để không vi phạm foreign key. Chỉ xóa các bảng lab vừa tạo.

**Kết quả cần đạt:** phân biệt scalar, row và multi-row subquery; phát hiện lỗi cardinality; dùng đúng IN/ANY/ALL/EXISTS/NOT EXISTS; nhận biết correlated reference; giải thích khác biệt số hàng giữa EXISTS và JOIN; đọc được kế hoạch truy cập cơ bản.

## 14. Nguyên tắc cần ghi nhớ

- Scalar subquery trả một cột và tối đa một hàng; không có hàng cho giá trị NULL, nhiều hàng gây lỗi 1242.
- Row subquery trả một hàng nhiều cột và chỉ dùng trong ngữ cảnh so sánh tuple phù hợp.
- Multi-row subquery cần toán tử phù hợp như IN, ANY/SOME, ALL hoặc EXISTS.
- IN kiểm tra membership; ANY cần ít nhất một phép so sánh đúng; ALL yêu cầu mọi phép so sánh đúng.
- ANY trên tập rỗng là FALSE; ALL trên tập rỗng là TRUE.
- NULL trong tập con có thể khiến IN/NOT IN/ANY/ALL trả UNKNOWN.
- NOT EXISTS thường là lựa chọn rõ ràng để tìm hàng không có bản ghi liên quan và tránh bẫy NULL của NOT IN.
- Correlated subquery tham chiếu outer query; uncorrelated subquery không có tham chiếu đó.
- Correlated subquery có thể là scalar hoặc multi-row; correlated mô tả quan hệ tham chiếu, không mô tả cardinality.
- JOIN có thể nhân hàng theo số bản ghi khớp; EXISTS chỉ kiểm tra sự tồn tại và giữ cardinality của outer rows.
- Không dùng LIMIT 1 để che dữ liệu trùng; nếu chọn một hàng, phải có ORDER BY và tiêu chí phân định rõ.
- Dùng index trên cột liên kết/lọc và kiểm tra EXPLAIN trước khi kết luận subquery chậm.

Chọn subquery theo cardinality và ý nghĩa logic của bài toán giúp câu SQL chính xác, dễ đọc và dễ tối ưu. Trước khi triển khai, hãy kiểm tra trường hợp không có hàng, nhiều hàng, NULL và quan hệ tương quan; sau đó xác minh kế hoạch thực thi trên phiên bản MySQL đang dùng.
