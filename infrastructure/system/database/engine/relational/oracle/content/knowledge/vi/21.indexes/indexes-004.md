# Index range scan, unique scan, full scan và fast full scan

Oracle Database có nhiều cách đọc một chỉ mục B-tree. Trong execution plan, các operation thường gặp gồm **INDEX UNIQUE SCAN**, **INDEX RANGE SCAN**, **INDEX FULL SCAN** và **INDEX FAST FULL SCAN**. Ngoài ra, optimizer có thể chọn **TABLE ACCESS FULL** để đọc toàn bộ bảng thay vì dùng index.

Các tên này mô tả những đường truy cập dữ liệu khác nhau. Chúng không phải các cấp độ nhanh/chậm cố định. Một INDEX RANGE SCAN có thể rất hiệu quả khi chỉ lấy một tỷ lệ nhỏ hàng, nhưng cũng có thể tốn kém nếu phải đọc hàng trăm nghìn ROWID rải rác trong bảng. Một TABLE ACCESS FULL có thể là lựa chọn tốt nhất khi truy vấn cần phần lớn dữ liệu.

Bài học tập trung vào cách index B-tree lưu khóa và ROWID, điều kiện phù hợp cho từng operation, sự khác nhau giữa index full scan và fast full scan, cách optimizer ước lượng chi phí, và cách đọc execution plan để hiểu Oracle thực sự đã chọn đường truy cập nào.

## 1. Index B-tree lưu dữ liệu như thế nào?

Index B-tree của Oracle là cấu trúc cây cân bằng. Với index thông thường, các nút trong cây giúp tìm vùng khóa cần đọc; các leaf block lưu khóa index và ROWID trỏ tới hàng trong bảng.

~~~text
                 ROOT / BRANCH
                 /           \
          BRANCH               BRANCH
          /    \               /    \
       LEAF   LEAF           LEAF   LEAF
        |      |              |      |
      key+   key+           key+   key+
      ROWID  ROWID          ROWID  ROWID
~~~

Một cách hình dung:

- Root/branch block dẫn đường tới vùng khóa cần tìm.
- Leaf block chứa các entry được sắp theo khóa index.
- ROWID xác định vị trí hàng trong table segment.
- Các leaf block được liên kết để có thể duyệt tuần tự theo thứ tự khóa.

Ví dụ:

~~~sql
CREATE INDEX ix_employee_department_salary
ON employees (department_id, salary);
~~~

Index lưu các cặp khóa theo thứ tự DEPARTMENT_ID, rồi SALARY, cùng ROWID của hàng tương ứng. Nếu truy vấn tìm nhân viên trong phòng ban 10 có lương từ 20.000 trở lên, Oracle có thể đi tới vùng khóa (10, 20000) rồi đọc tiếp các leaf entry thỏa điều kiện.

### 1.1 ROWID dùng để làm gì?

ROWID là địa chỉ logic của hàng trong Oracle. Khi index tìm được entry phù hợp, Oracle có thể dùng ROWID để truy cập hàng trong bảng:

~~~text
INDEX RANGE SCAN
       |
       |  ROWID values
       v
TABLE ACCESS BY INDEX ROWID
       |
       v
   Table rows
~~~

Nếu tất cả cột truy vấn cần đều có trong index và Oracle có thể lấy kết quả trực tiếp từ index, plan có thể không cần bước TABLE ACCESS BY INDEX ROWID. Trường hợp này thường được gọi là index-only access hoặc covering access.

Index giúp tìm hàng, nhưng bản thân nó không chứa mọi cột của bảng. Nếu truy vấn cần EMPLOYEE_NAME, còn index chỉ có DEPARTMENT_ID và SALARY, Oracle thường phải dùng ROWID để đọc thêm hàng từ table.

### 1.2 Index không phải bản sao đầy đủ của bảng

Index B-tree chỉ lưu các cột khóa index và thông tin định vị hàng. Một số hệ quả:

- Index thường nhỏ hơn table, nhưng vẫn có chi phí đọc leaf block và truy cập table.
- Cột không có trong index có thể yêu cầu table access.
- DML trên bảng phải duy trì index, làm tăng chi phí INSERT/UPDATE/DELETE.
- Một index đơn cột B-tree không lưu entry cho hàng có giá trị NULL ở toàn bộ khóa index.

Vì vậy, không nên tạo index chỉ vì một cột xuất hiện trong WHERE. Phải xét selectivity, số hàng trả về, số block phải đọc và chi phí cập nhật index.

## 2. Những operation cần phân biệt

| Operation trong plan | Mục tiêu | Số hàng/entry có thể đọc |
|---|---|---|
| INDEX UNIQUE SCAN | Tìm tối đa một entry theo khóa unique đầy đủ | 0 hoặc 1 entry logic |
| INDEX RANGE SCAN | Tìm một vùng khóa hoặc một tập khóa | 0 đến nhiều entry |
| INDEX FULL SCAN | Duyệt toàn bộ leaf entry theo thứ tự khóa | Toàn bộ entry trong index |
| INDEX FAST FULL SCAN | Đọc toàn bộ block của index theo cách scan nhanh, không giữ thứ tự khóa | Toàn bộ index block cần thiết |
| TABLE ACCESS FULL | Đọc toàn bộ block bảng thuộc phạm vi scan | Toàn bộ block bảng |

Tên operation có ý nghĩa cụ thể trong execution plan. Đừng suy luận chỉ từ chữ FULL: INDEX FULL SCAN và INDEX FAST FULL SCAN đều đọc toàn index, nhưng cách duyệt và thứ tự đầu ra khác nhau.

## 3. INDEX UNIQUE SCAN

INDEX UNIQUE SCAN dùng để tìm một entry theo đầy đủ khóa của một unique index. Kết quả có tối đa một hàng logic.

Ví dụ bảng:

~~~sql
CREATE TABLE employees (
    employee_id   NUMBER(8) PRIMARY KEY,
    department_id NUMBER(6),
    employee_name VARCHAR2(100),
    salary        NUMBER(12,2)
);
~~~

Primary key EMPLOYEE_ID tạo unique index (trừ khi cấu hình constraint/index khác được chỉ định). Truy vấn:

~~~sql
SELECT employee_id,
       department_id,
       employee_name,
       salary
FROM employees
WHERE employee_id = 1001;
~~~

Oracle có thể chọn:

~~~text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID EMPLOYEES
    INDEX UNIQUE SCAN (PK_EMPLOYEES)
~~~

Đầu tiên index tìm entry cho EMPLOYEE_ID = 1001. Sau đó ROWID được dùng để lấy các cột còn lại từ table.

### 3.1 Điều kiện để có unique scan

Với unique index một cột:

~~~sql
CREATE UNIQUE INDEX ux_employee_email
ON employees(email);
~~~

Truy vấn equality:

~~~sql
SELECT employee_id, email
FROM employees
WHERE email = 'linh@example.com';
~~~

có thể dùng INDEX UNIQUE SCAN vì điều kiện xác định đầy đủ khóa unique.

Với unique index nhiều cột:

~~~sql
CREATE UNIQUE INDEX ux_order_line
ON order_lines(order_id, line_number);
~~~

Truy vấn:

~~~sql
SELECT *
FROM order_lines
WHERE order_id = 500
  AND line_number = 3;
~~~

có thể dùng unique scan vì cả hai cột khóa đều được xác định bằng equality.

Nếu chỉ có:

~~~sql
WHERE order_id = 500
~~~

thì có thể có nhiều dòng cho một order. Đây là truy cập theo tiền tố của composite index và thường phù hợp với INDEX RANGE SCAN, không phải unique scan.

### 3.2 Unique scan không có nghĩa truy vấn chỉ đọc một block

Để tìm entry, Oracle có thể cần đọc root, branch và leaf block. Nếu truy vấn cần cột ngoài index, còn phải đọc table block theo ROWID. Cache có thể giúp các block đã nằm trong buffer cache được đọc nhanh hơn, nhưng operation vẫn có thể bao gồm nhiều lần truy cập block.

### 3.3 Unique scan khác unique constraint

Unique constraint là quy tắc dữ liệu. INDEX UNIQUE SCAN là access path trong execution plan.

- Có unique constraint không có nghĩa mọi truy vấn đều dùng unique scan.
- Optimizer có thể chọn table full scan nếu truy vấn cần nhiều hàng hoặc chi phí index không có lợi.
- Một truy vấn dùng equality trên khóa unique thường có thể dùng unique scan, nhưng quyết định cuối cùng phụ thuộc biểu thức, kiểu dữ liệu, thống kê và plan.

### 3.4 NULL và unique key

Oracle cho phép unique constraint có các giá trị NULL theo quy tắc của Oracle; unique key không đồng nghĩa mọi cột đều NOT NULL. Điều kiện IS NULL không phải equality lookup thông thường trên unique key. Với B-tree một cột, entry của hàng có key NULL không được lưu, nên index đó không thể tự tìm tất cả hàng NULL.

Nếu cột định danh cần một giá trị duy nhất và bắt buộc có mặt, thường kết hợp NOT NULL với PRIMARY KEY hoặc UNIQUE theo yêu cầu dữ liệu.

## 4. INDEX RANGE SCAN

INDEX RANGE SCAN đọc một vùng entry trong leaf block của index. Đây là operation phổ biến khi truy vấn:

- Equality trên cột không unique.
- Tìm theo tiền tố của composite index.
- Dùng điều kiện khoảng như >, >=, <, <=, BETWEEN.
- Dùng prefix pattern như LIKE 'ABC%' trong điều kiện phù hợp.
- Dùng một danh sách giá trị có thể được triển khai qua nhiều range.

Ví dụ:

~~~sql
CREATE INDEX ix_employee_department
ON employees(department_id);

SELECT employee_id,
       employee_name,
       department_id
FROM employees
WHERE department_id = 10;
~~~

Nếu phòng ban 10 chỉ chiếm một phần nhỏ bảng, index range scan có thể hiệu quả. Oracle tìm điểm bắt đầu của khóa 10 rồi đọc các entry có khóa phù hợp.

### 4.1 Range scan với điều kiện khoảng

~~~sql
SELECT employee_id, salary
FROM employees
WHERE salary BETWEEN 20000 AND 40000;
~~~

Với index trên SALARY, Oracle có thể tìm leaf entry đầu tiên thỏa SALARY >= 20000, sau đó đọc tới khi vượt quá 40000.

BETWEEN bao gồm cả hai biên, tương đương:

~~~sql
salary >= 20000
AND salary <= 40000
~~~

### 4.2 Composite index và leading column

Giả sử:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders(customer_id, order_date);
~~~

Các truy vấn sau có khả năng tận dụng thứ tự khóa của index:

~~~sql
-- Tìm một khách hàng.
WHERE customer_id = 101

-- Tìm đơn của một khách hàng trong một khoảng ngày.
WHERE customer_id = 101
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'

-- Tìm theo tiền tố khách hàng.
WHERE customer_id BETWEEN 100 AND 200
~~~

Truy vấn chỉ lọc ORDER_DATE mà không có điều kiện CUSTOMER_ID không sử dụng được một range liên tục theo cách thông thường trên leading prefix. Oracle vẫn có thể cân nhắc index skip scan hoặc một access path khác, nhưng không nên thiết kế dựa trên giả định rằng mọi cột trong index đều có thể được tìm độc lập với cùng hiệu quả.

### 4.3 Range scan với IN

~~~sql
SELECT employee_id, department_id
FROM employees
WHERE department_id IN (10, 20, 30);
~~~

Optimizer có thể thực hiện nhiều lần truy cập range hoặc dùng operation INLIST ITERATOR bao quanh index scan. Hình dạng plan phụ thuộc số giá trị, thống kê và chi phí.

### 4.4 LIKE và index range scan

Prefix pattern:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_name LIKE 'AN%';
~~~

có thể được chuyển thành một vùng khóa bắt đầu bằng AN, nếu kiểu dữ liệu/collation và biểu thức cho phép.

Pattern có wildcard ở đầu:

~~~sql
WHERE customer_name LIKE '%AN'
~~~

thường không xác định được điểm bắt đầu của một range B-tree thông thường. Oracle có thể chọn full scan hoặc kỹ thuật khác. Nếu nghiệp vụ cần tìm chuỗi con, cân nhắc thiết kế tìm kiếm phù hợp thay vì kỳ vọng B-tree index thông thường sẽ giải quyết tốt.

### 4.5 INDEX RANGE SCAN DESCENDING

Oracle có thể duyệt index range theo chiều ngược:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = 101
ORDER BY order_date DESC;
~~~

Với index phù hợp (customer_id, order_date), plan có thể hiển thị INDEX RANGE SCAN DESCENDING. Dù vậy, chỉ ORDER BY ở cấp truy vấn mới bảo đảm thứ tự kết quả cho người gọi.

### 4.6 Range scan không đồng nghĩa chỉ đọc ít dữ liệu

Một truy vấn có điều kiện index nhưng trả về 70% số hàng của bảng có thể tốn:

1. Đọc nhiều leaf block.
2. Lấy rất nhiều ROWID.
3. Đọc nhiều table block rải rác.

Trong trường hợp này, table full scan có thể rẻ hơn do đọc block tuần tự hoặc multiblock I/O. Optimizer chọn theo chi phí ước lượng, không theo quy tắc “có index thì dùng index”.

## 5. TABLE ACCESS BY INDEX ROWID

Sau một index scan, Oracle thường phải truy cập table để lấy cột không nằm trong index:

~~~text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID EMPLOYEES
    INDEX RANGE SCAN IX_EMPLOYEE_DEPARTMENT
~~~

Index scan tạo ra ROWID của các hàng thỏa điều kiện. Table access dùng các ROWID này để đọc hàng tương ứng.

### 5.1 Vì sao table access có thể đắt?

Nếu các hàng nằm rải rác trên nhiều block, Oracle có thể phải đọc nhiều block table riêng lẻ. Độ tương quan giữa thứ tự index và vị trí hàng trong table được phản ánh một phần qua **clustering factor**.

- Clustering factor thấp: các entry gần nhau trong index thường trỏ tới các hàng nằm gần nhau trong table; truy cập theo ROWID có thể tiết kiệm block I/O.
- Clustering factor cao: các entry gần nhau trong index có thể trỏ tới các block table rải rác; range scan lớn có thể gây nhiều table block access.

Clustering factor không phải số đo thời gian trực tiếp và không quyết định plan một mình. Nó là một thống kê optimizer dùng khi ước lượng chi phí table access qua ROWID.

### 5.2 TABLE ACCESS BY INDEX ROWID BATCHED

Trong một số plan, Oracle hiển thị TABLE ACCESS BY INDEX ROWID BATCHED. Cơ chế batching gom các ROWID để sắp xếp/nhóm truy cập table block nhằm giảm I/O ngẫu nhiên.

Vì việc lấy hàng có thể được tối ưu theo block, không nên dựa vào thứ tự vật lý mà index scan đã tạo để suy ra thứ tự hàng cuối cùng. Nếu cần thứ tự, dùng ORDER BY.

### 5.3 Index-only access

Nếu truy vấn chỉ cần các cột có trong index:

~~~sql
CREATE INDEX ix_employee_dept_salary
ON employees(department_id, salary);

SELECT department_id, salary
FROM employees
WHERE department_id = 10;
~~~

Oracle có thể trả các cột cần thiết trực tiếp từ index, tránh table access. Đây là một lý do index có thể được thiết kế để bao phủ một truy vấn quan trọng.

Tuy nhiên, thêm quá nhiều cột vào index làm index rộng hơn, tốn storage, buffer cache và chi phí DML. Chỉ nên cân nhắc covering index khi workload và đo đạc chứng minh lợi ích.

## 6. INDEX FULL SCAN

INDEX FULL SCAN duyệt toàn bộ leaf entry của index theo thứ tự khóa. Oracle đọc toàn bộ vùng leaf cần thiết, bắt đầu từ đầu hoặc cuối tùy hướng, và có thể trả các giá trị theo thứ tự index.

Ví dụ:

~~~sql
CREATE INDEX ix_employee_department_salary
ON employees(department_id, salary);

SELECT department_id, salary
FROM employees
ORDER BY department_id, salary;
~~~

Nếu index phù hợp và optimizer thấy chi phí có lợi, plan có thể dùng INDEX FULL SCAN. Vì truy vấn chỉ cần hai cột đã có trong index, Oracle có thể không cần đọc table.

### 6.1 Vì sao đọc toàn index?

Một index full scan có thể được chọn khi:

- Truy vấn cần nhiều hoặc toàn bộ entry index.
- Index nhỏ hơn table đáng kể.
- Index chứa đủ cột truy vấn.
- Thứ tự index có thể đáp ứng yêu cầu sắp xếp.
- Access path index có chi phí thấp hơn table full scan cộng sort.

### 6.2 INDEX FULL SCAN có thể giúp đáp ứng ORDER BY

Index có thứ tự (department_id, salary). Truy vấn:

~~~sql
SELECT department_id, salary
FROM employees
ORDER BY department_id, salary;
~~~

có cùng thứ tự khóa. Oracle có thể duyệt index theo thứ tự đó và tránh một sort riêng.

Nhưng nếu có phép JOIN, parallel operation, batching hoặc một operation khác làm thay đổi thứ tự, optimizer vẫn có thể cần sort. SQL không bảo đảm thứ tự kết quả nếu không có ORDER BY cuối truy vấn.

### 6.3 INDEX FULL SCAN khác INDEX RANGE SCAN

| Đặc điểm | INDEX RANGE SCAN | INDEX FULL SCAN |
|---|---|---|
| Phạm vi | Một vùng khóa thỏa predicate | Toàn bộ leaf entry |
| Bắt đầu | Từ vị trí khóa phù hợp | Từ đầu/cuối leaf chain |
| Số entry | Có thể ít hoặc nhiều | Toàn bộ entry |
| Thứ tự khóa | Duyệt theo thứ tự index trong range | Duyệt toàn bộ theo thứ tự index |
| Trường hợp phổ biến | Lọc chọn lọc | Đọc index toàn phần, có thể tận dụng thứ tự |

## 7. INDEX FAST FULL SCAN

INDEX FAST FULL SCAN đọc toàn bộ block của index theo cách scan nhanh, thường tận dụng multiblock I/O và có thể thực hiện song song. Oracle xem index như một cấu trúc nhỏ hơn để đọc toàn bộ dữ liệu cần thiết.

Khác biệt quan trọng nhất so với INDEX FULL SCAN:

**Fast full scan không bảo đảm thứ tự khóa index.**

Ví dụ:

~~~sql
SELECT department_id, salary
FROM employees;
~~~

Nếu hai cột đều có trong index (department_id, salary) và optimizer ước lượng index nhỏ hơn/ít tốn kém hơn table, plan có thể chọn INDEX FAST FULL SCAN.

### 7.1 Fast full scan đọc gì?

Operation này đọc các block của index theo cách tối ưu throughput, không đi tuần tự qua leaf chain để giữ thứ tự khóa. Nó có thể đọc nhiều block cùng lúc, giống cách table full scan đọc block.

Mục tiêu là lấy tất cả dữ liệu cần từ index nhanh nhất theo chi phí, không phải trả dữ liệu đã sắp xếp.

### 7.2 Fast full scan thường cần index bao phủ truy vấn

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders(customer_id, order_date);

SELECT customer_id, order_date
FROM orders;
~~~

Truy vấn chỉ cần các cột trong index, nên fast full scan có thể là một ứng viên. Nếu truy vấn cần ORDER_TOTAL mà cột đó không có trong index, Oracle cần table access bổ sung hoặc chọn access path khác; khi phải đọc nhiều hàng, table full scan có thể phù hợp hơn.

### 7.3 Không dùng fast full scan để đáp ứng thứ tự

Truy vấn:

~~~sql
SELECT customer_id, order_date
FROM orders
ORDER BY customer_id, order_date;
~~~

không thể dựa vào INDEX FAST FULL SCAN để bảo đảm thứ tự. Nếu optimizer chọn fast full scan, có thể cần một operation sort ở trên:

~~~text
SORT ORDER BY
  INDEX FAST FULL SCAN IX_ORDERS_CUSTOMER_DATE
~~~

Nếu muốn tận dụng thứ tự index, INDEX FULL SCAN có thể là ứng viên khác. Optimizer chọn theo chi phí tổng thể.

### 7.4 Fast full scan và cột NULL

B-tree index một cột không lưu entry cho hàng có giá trị NULL ở cột đó. Nếu truy vấn cần mọi hàng của bảng, một index chỉ gồm cột nullable có thể không chứa đầy đủ các hàng để thay thế table full scan.

Với composite B-tree index, một hàng vẫn có entry nếu ít nhất một cột trong khóa index khác NULL. Tuy nhiên, nếu tất cả cột khóa đều NULL thì entry không được lưu.

Do đó, khi đánh giá index fast full scan như một đường đọc thay cho table, cần chắc rằng index chứa mọi hàng cần thiết. Không suy luận rằng index scan toàn bộ luôn tương đương đọc toàn bộ bảng.

### 7.5 Fast full scan có thể chạy song song

Vì không cần giữ thứ tự leaf chain, fast full scan phù hợp với việc phân phối block cho nhiều parallel execution server trong những điều kiện được hỗ trợ. Parallel query vẫn phụ thuộc cấu hình, quyền, object và quyết định optimizer; không phải cứ có fast full scan là truy vấn chắc chắn chạy song song.

## 8. TABLE ACCESS FULL

TABLE ACCESS FULL đọc toàn bộ block của bảng thuộc phạm vi scan. Nó không cần index để tìm từng hàng; Oracle đọc table segment và áp dụng predicate.

Ví dụ:

~~~sql
SELECT employee_id,
       employee_name,
       department_id,
       salary
FROM employees
WHERE salary > 10000;
~~~

Nếu phần lớn nhân viên có lương trên 10.000 hoặc bảng tương đối nhỏ, table full scan có thể rẻ hơn việc:

1. Duyệt index để lấy ROWID.
2. Truy cập table block cho rất nhiều hàng.

### 8.1 Vì sao full table scan đôi khi tốt hơn index?

Full table scan thường có thể đọc block theo cách tuần tự/multiblock, tận dụng I/O throughput. Ngược lại, index range scan trên tỷ lệ hàng lớn có thể phải đọc nhiều leaf block và nhiều table block rải rác.

Optimizer cân nhắc:

- Số hàng dự kiến trả về.
- Tổng số block table phải đọc.
- Số leaf block index cần đọc.
- Clustering factor.
- Kích thước index và table.
- Predicate selectivity.
- System statistics và chi phí I/O/CPU.
- Parallel degree và các điều kiện thực thi.

### 8.2 Full scan không có nghĩa là bỏ qua WHERE

Operation TABLE ACCESS FULL có thể đọc các block của bảng rồi lọc theo predicate. Truy vấn:

~~~sql
SELECT *
FROM employees
WHERE department_id = 10;
~~~

vẫn có thể dùng table full scan nếu optimizer ước lượng đọc toàn bảng rẻ hơn. Điều kiện WHERE vẫn được áp dụng; full scan chỉ mô tả cách lấy block đầu vào.

### 8.3 Full scan không bảo đảm thứ tự

Ngay cả khi bảng được tạo theo thứ tự tăng dần ID hoặc dữ liệu hiện tại tình cờ trả ra theo thứ tự nào đó, TABLE ACCESS FULL không bảo đảm thứ tự kết quả. Muốn có thứ tự ổn định phải viết:

~~~sql
ORDER BY employee_id;
~~~

## 9. So sánh INDEX FULL SCAN và INDEX FAST FULL SCAN

Đây là hai operation dễ nhầm vì cả hai đều đọc toàn bộ index:

| Tiêu chí | INDEX FULL SCAN | INDEX FAST FULL SCAN |
|---|---|---|
| Phạm vi | Toàn bộ leaf entry | Toàn bộ block index cần thiết |
| Cách duyệt | Theo leaf chain/thứ tự khóa | Theo block scan tối ưu throughput |
| Thứ tự khóa | Có | Không |
| I/O | Thường duyệt theo thứ tự, có thể single-block | Có thể dùng multiblock I/O |
| Dùng để đáp ứng ORDER BY | Có thể, nếu thứ tự phù hợp và plan giữ được thứ tự | Không |
| Index-only access | Có thể | Thường là điều kiện quan trọng |
| Mục tiêu | Đọc toàn index theo thứ tự | Đọc index nhanh như một cấu trúc nhỏ |

Một cách nhớ:

- INDEX FULL SCAN: đọc hết index theo thứ tự khóa.
- INDEX FAST FULL SCAN: đọc hết index không cần thứ tự khóa.
- TABLE ACCESS FULL: đọc toàn bộ table block.

Không có quy tắc rằng fast full scan luôn nhanh hơn full scan. Nếu cần thứ tự, chi phí sort bổ sung có thể làm fast full scan kém hấp dẫn. Nếu chỉ cần tổng hợp trên các cột index, fast full scan có thể là ứng viên tốt.

## 10. Bảng chọn access path theo dạng predicate

Giả sử có index:

~~~sql
CREATE UNIQUE INDEX ux_employee_id
ON employees(employee_id);

CREATE INDEX ix_employee_dept_salary
ON employees(department_id, salary);
~~~

Các ví dụ định hướng:

| Truy vấn | Access path có thể phù hợp | Lý do |
|---|---|---|
| employee_id = 1001 | INDEX UNIQUE SCAN | Equality trên toàn bộ khóa unique |
| department_id = 10 | INDEX RANGE SCAN | Một phòng ban có thể có nhiều nhân viên |
| department_id = 10 AND salary >= 20000 | INDEX RANGE SCAN | Leading equality + range trên cột tiếp theo |
| department_id BETWEEN 10 AND 20 | INDEX RANGE SCAN | Một khoảng trên leading key |
| department_id IN (10,20) | RANGE SCAN / INLIST ITERATOR | Nhiều vùng khóa |
| Chọn mọi department_id, salary theo thứ tự index | INDEX FULL SCAN có thể phù hợp | Đọc toàn index và có thể giữ thứ tự |
| Chọn mọi department_id, salary không cần thứ tự | INDEX FAST FULL SCAN có thể phù hợp | Đọc toàn index theo throughput |
| Chọn nhiều cột của hầu hết hàng | TABLE ACCESS FULL có thể phù hợp | Tránh hàng loạt table access qua ROWID |

Đây là hướng suy luận, không phải cam kết operation. Optimizer quyết định dựa trên cost và thống kê.

## 11. Selectivity: predicate lọc được bao nhiêu hàng?

**Selectivity** là tỷ lệ hàng được ước lượng thỏa predicate. Một predicate chọn lọc cao chỉ trả một phần nhỏ bảng:

~~~sql
WHERE employee_id = 1001
~~~

Nếu employee_id unique, selectivity rất nhỏ. Index unique scan thường phù hợp.

Một predicate chọn lọc thấp có thể trả nhiều hàng:

~~~sql
WHERE status = 'ACTIVE'
~~~

Nếu 95% hàng đều ACTIVE, index range scan có thể phải lấy gần hết hàng và truy cập table theo ROWID. Full table scan có thể rẻ hơn.

### 11.1 Selectivity phụ thuộc phân bố dữ liệu

Không chỉ nhìn số giá trị khác nhau. Ví dụ cột STATUS có hai giá trị ACTIVE và INACTIVE nhưng phân bố 99%/1%. Một predicate ACTIVE và một predicate INACTIVE có selectivity rất khác nhau.

Optimizer dùng thống kê cột, histogram khi phù hợp, và các thông tin khác để ước lượng cardinality. Thống kê cũ hoặc không đại diện có thể dẫn tới plan không phù hợp.

### 11.2 Đừng dùng quy tắc phần trăm cố định

Không có ngưỡng chung như “dưới 10% thì dùng index, trên 10% thì full scan”. Quyết định phụ thuộc:

- Table block count.
- Row width.
- Index leaf block count.
- Clustering factor.
- Buffer cache và system statistics.
- Cột cần lấy từ table.
- Parallelism và I/O subsystem.

## 12. Clustering factor ảnh hưởng index range scan

Clustering factor phản ánh mức độ các hàng trong table được sắp tương quan với thứ tự khóa index.

Ví dụ index theo CUSTOMER_ID:

- Nếu các hàng của cùng khách hàng nằm gần nhau trong table, một range có thể đọc ít table block hơn.
- Nếu các hàng được chèn xen kẽ giữa nhiều khách hàng, ROWID cho một khách hàng có thể nằm trên rất nhiều block khác nhau.

Trong trường hợp thứ hai, index range scan có thể cần nhiều table block access dù số hàng trả về không quá lớn.

### 12.1 Xem clustering factor

Trong schema có quyền xem user index statistics:

~~~sql
SELECT index_name,
       table_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       num_rows
FROM user_indexes
WHERE table_name = 'EMPLOYEES';
~~~

Ý nghĩa khái quát:

- BLEVEL: độ sâu nhánh của index.
- LEAF_BLOCKS: số leaf block thống kê.
- DISTINCT_KEYS: số giá trị khóa khác nhau được thống kê.
- CLUSTERING_FACTOR: mức tương quan index/table.
- NUM_ROWS: số entry index theo thống kê.

Thống kê có thể chưa cập nhật hoặc khác theo loại index. Không đọc một cột riêng lẻ rồi kết luận index tốt/xấu.

### 12.2 Cập nhật statistics

Trong môi trường được phép và theo quy trình DBA:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'EMPLOYEES',
        cascade => TRUE
    );
END;
/
~~~

CASCADE => TRUE yêu cầu thu thập statistics cho các index liên quan theo cơ chế DBMS_STATS. Production cần tuân thủ lịch, quyền và chính sách thống kê của hệ thống; không tự thu thập stats trên bảng lớn đang chạy workload mà chưa đánh giá.

## 13. Các nguyên nhân khiến Oracle không dùng index như mong đợi

Một index tồn tại không có nghĩa optimizer có thể hoặc nên dùng nó.

### 13.1 Không dùng leading column

Index:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders(customer_id, order_date);
~~~

Predicate:

~~~sql
WHERE order_date >= DATE '2026-01-01'
~~~

không xác định customer_id. Oracle có thể cân nhắc skip scan nếu số giá trị leading key ít và cost phù hợp, nhưng table full scan hoặc index khác cũng có thể tốt hơn.

### 13.2 Áp dụng hàm lên cột

~~~sql
WHERE TRUNC(order_date) = DATE '2026-01-01'
~~~

có thể ngăn việc dùng range scan trực tiếp trên index thông thường của ORDER_DATE. Một cách viết range thường thân thiện với index hơn:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-01-02'
~~~

Nếu truy vấn thường xuyên cần biểu thức TRUNC(order_date), có thể cân nhắc function-based index:

~~~sql
CREATE INDEX ix_orders_order_day
ON orders(TRUNC(order_date));
~~~

Phải đánh giá kiểu dữ liệu, NLS, biểu thức và chi phí duy trì index.

### 13.3 Implicit conversion

Nếu cột là NUMBER nhưng ứng dụng bind chuỗi, hoặc cột DATE bị so sánh qua chuỗi phụ thuộc NLS, Oracle có thể phải chuyển đổi dữ liệu. Khi hàm chuyển đổi được áp lên cột index, access path có thể kém hiệu quả hoặc không dùng range scan như mong đợi.

Hãy bind đúng kiểu dữ liệu:

- NUMBER bằng kiểu số.
- DATE/TIMESTAMP bằng kiểu ngày giờ.
- VARCHAR2 bằng chuỗi.

Không chuyển cột index sang kiểu khác trong predicate nếu có thể chuyển giá trị đầu vào sang đúng kiểu cột.

### 13.4 Predicate không chọn lọc

Nếu predicate trả về phần lớn bảng, table full scan có thể rẻ hơn index range scan cộng nhiều table access by ROWID. Đây có thể là lựa chọn đúng của optimizer.

### 13.5 Thống kê sai hoặc không đại diện

Stats cũ, thiếu histogram cho cột skew, hoặc bind values có selectivity khác nhau có thể dẫn tới cardinality estimate không tốt. Khi điều tra, so sánh E-Rows và A-Rows trong actual plan.

### 13.6 Biểu thức OR

Predicate có OR trên nhiều cột có thể cần nhiều access path. Oracle có thể dùng OR expansion hoặc bitmap conversion tùy trường hợp, nhưng không phải mọi OR đều chuyển thành một index range scan đơn giản.

## 14. Index range scan với composite index: ví dụ chi tiết

Tạo bảng đơn hàng:

~~~sql
CREATE TABLE lab_orders (
    order_id     NUMBER(10) PRIMARY KEY,
    customer_id  NUMBER(10) NOT NULL,
    order_date   DATE NOT NULL,
    status       VARCHAR2(20) NOT NULL,
    total_amount NUMBER(14,2) NOT NULL
);

CREATE INDEX ix_lab_orders_customer_date
ON lab_orders(customer_id, order_date);
~~~

Truy vấn:

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM lab_orders
WHERE customer_id = 101
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

Optimizer có thể dùng:

~~~text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID LAB_ORDERS
    INDEX RANGE SCAN IX_LAB_ORDERS_CUSTOMER_DATE
~~~

Index tìm vùng khóa:

~~~text
(101, 2026-01-01) <= key < (101, 2026-02-01)
~~~

Sau đó lấy ROWID và đọc các hàng tương ứng. Vì truy vấn cần TOTAL_AMOUNT, cột này không có trong index, nên table access thường cần thiết.

### 14.1 Tạo index bao phủ truy vấn

Có thể thử:

~~~sql
CREATE INDEX ix_lab_orders_customer_date_amount
ON lab_orders(customer_id, order_date, total_amount);
~~~

Truy vấn trên có thể lấy các cột cần thiết từ index, giảm table access. Nhưng index rộng hơn và làm tăng chi phí DML/storage. Nếu truy vấn trả rất nhiều hàng, scan index rộng có thể vẫn đắt hơn full table scan.

Không nên tạo index thứ hai nếu index hiện có đã đáp ứng workload; hãy xem plan và đo trước.

## 15. So sánh các loại full scan bằng ví dụ

Giả sử có:

~~~sql
CREATE INDEX ix_lab_orders_customer_date
ON lab_orders(customer_id, order_date);
~~~

### 15.1 Chỉ đọc các cột index, không yêu cầu thứ tự

~~~sql
SELECT customer_id, order_date
FROM lab_orders;
~~~

INDEX FAST FULL SCAN có thể phù hợp nếu index nhỏ hơn table và chứa đủ hàng/cột cần thiết.

### 15.2 Chỉ đọc các cột index và yêu cầu thứ tự

~~~sql
SELECT customer_id, order_date
FROM lab_orders
ORDER BY customer_id, order_date;
~~~

INDEX FULL SCAN có thể được cân nhắc để cung cấp thứ tự khóa. Nếu optimizer chọn fast full scan hoặc một access path khác, plan có thể cần sort.

### 15.3 Cần nhiều cột của bảng

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       status,
       total_amount
FROM lab_orders;
~~~

Nếu cần gần như toàn bộ bảng và index không bao phủ các cột, TABLE ACCESS FULL thường là ứng viên tự nhiên.

### 15.4 Lọc chọn lọc một khách hàng

~~~sql
SELECT order_id, order_date, total_amount
FROM lab_orders
WHERE customer_id = 101;
~~~

INDEX RANGE SCAN trên leading key CUSTOMER_ID có thể phù hợp nếu khách hàng 101 có ít đơn so với tổng bảng.

## 16. Đọc execution plan

### 16.1 EXPLAIN PLAN

Ví dụ:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id,
       employee_name
FROM employees
WHERE department_id = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Trong output, xem:

- Operation: INDEX RANGE SCAN, INDEX UNIQUE SCAN hay TABLE ACCESS FULL.
- Name: tên index hoặc table.
- Rows: số hàng ước lượng.
- Cost: chi phí tương đối optimizer dùng để so sánh plan.
- Predicate Information: điều kiện access và filter.

### 16.2 Access predicate và filter predicate

Trong plan:

- **access predicate** giúp định vị vùng index/table cần đọc.
- **filter predicate** được áp dụng để loại hàng sau khi operation lấy được dữ liệu.

Ví dụ index (customer_id, order_date):

~~~sql
WHERE customer_id = 101
  AND order_date >= DATE '2026-01-01'
  AND status = 'PAID'
~~~

Hai điều kiện đầu có thể dùng để định vị range trong index. STATUS không có trong index nên có thể là filter sau khi đọc table row. Predicate Information cho biết optimizer thực sự dùng điều kiện nào ở từng operation.

### 16.3 Actual execution statistics

Trong môi trường kiểm thử, thu thập actual plan:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       employee_name
FROM employees
WHERE department_id = 10;
~~~

Sau khi chạy:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST'
    )
);
~~~

So sánh:

- E-Rows: số hàng optimizer ước lượng.
- A-Rows: số hàng thực tế operation trả ra theo thống kê đã thu thập.
- Buffers: logical reads nếu được hiển thị.
- Reads: physical reads nếu được hiển thị.
- Starts: số lần operation được khởi chạy.

Nếu index range scan ước lượng 10 hàng nhưng thực tế 100.000 hàng, optimizer có thể đã đánh giá thấp chi phí table access. Điều tra stats, histogram, bind values và predicate trước khi ép index.

### 16.4 EXPLAIN PLAN không phải runtime plan

EXPLAIN PLAN cho biết kế hoạch được tạo trong điều kiện explain. Nó không đo đầy đủ runtime của một lần thực thi với bind values, adaptive plan và thống kê thực tế.

Khi điều tra production, ưu tiên xem cursor thực tế bằng DBMS_XPLAN.DISPLAY_CURSOR nếu có quyền và instrumentation phù hợp.

## 17. Hints và vì sao không nên ép index tùy tiện

Oracle có các hints như:

~~~sql
SELECT /*+ INDEX(e ix_employee_department) */
       e.employee_id,
       e.department_id
FROM employees e
WHERE e.department_id = 10;
~~~

Hint có thể hướng optimizer tới một index, nhưng:

- Hint có thể không hợp lệ hoặc bị bỏ qua.
- Plan bị ép hôm nay có thể kém khi dữ liệu tăng.
- Index range scan có thể tạo quá nhiều ROWID/table block access.
- Hint không thay thế thống kê tốt và SQL đúng.

Chỉ cân nhắc hint sau khi đã xác định plan tự nhiên có vấn đề, kiểm tra lý do optimizer chọn plan, và đo kết quả trên dữ liệu đại diện.

Không dùng hint FULL hoặc INDEX như mẹo mặc định cho mọi truy vấn.

## 18. Các lỗi tư duy phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| Index tồn tại thì Oracle phải dùng | Optimizer so sánh chi phí các access path |
| UNIQUE SCAN luôn đọc đúng một block | Có thể cần root/branch/leaf và table block |
| RANGE SCAN luôn trả ít hàng | Range có thể rất rộng |
| FULL SCAN luôn chậm | Có thể rẻ hơn khi cần phần lớn dữ liệu |
| INDEX FULL SCAN và FAST FULL SCAN giống nhau | Một loại giữ thứ tự khóa, một loại không |
| FAST FULL SCAN có thể đáp ứng ORDER BY | Không bảo đảm thứ tự; có thể cần SORT ORDER BY |
| INDEX RANGE SCAN không cần table access | Cần table access nếu truy vấn cần cột ngoài index |
| Index càng rộng càng tốt | Index rộng tăng storage, I/O và chi phí DML |
| Clustering factor càng cao càng tốt | Clustering factor thấp thường thuận lợi cho ROWID access |
| LIKE '%abc' dùng B-tree range như prefix | Wildcard đầu thường ngăn định vị range thông thường |
| Có WHERE là sẽ dùng index | Predicate chọn lọc thấp có thể phù hợp full scan |
| Index scan tự bảo đảm thứ tự kết quả | Chỉ ORDER BY cuối mới bảo đảm thứ tự SQL |

## 19. Quy trình lựa chọn và điều tra access path

~~~mermaid
flowchart TD
    A["Đọc SQL và xác định cột cần trả"] --> B["Xác định predicate và khóa index"]
    B --> C{"Equality trên toàn unique key?"}
    C -->|Có| D["INDEX UNIQUE SCAN có thể phù hợp"]
    C -->|Không| E{"Có vùng khóa/leading prefix chọn lọc?"}
    E -->|Có| F["INDEX RANGE SCAN có thể phù hợp"]
    E -->|Không| G{"Index bao phủ truy vấn?"}
    G -->|Có, cần thứ tự khóa| H["INDEX FULL SCAN có thể phù hợp"]
    G -->|Có, không cần thứ tự| I["INDEX FAST FULL SCAN có thể phù hợp"]
    G -->|Không| J["So sánh TABLE ACCESS FULL"]
    D --> K["Đọc actual plan và đo"]
    F --> K
    H --> K
    I --> K
    J --> K
    K --> L["So sánh E-Rows/A-Rows, buffers, reads và predicate"]
~~~

Trình tự thực tế:

1. Xác định số hàng và cột truy vấn cần.
2. Xác định index key, thứ tự cột và unique property.
3. Xác định predicate equality, range, IN, LIKE, NULL hoặc biểu thức.
4. Xem operation trong execution plan.
5. Xem table access by ROWID có đọc nhiều block không.
6. Đối chiếu selectivity, clustering factor và actual rows.
7. So sánh với table full scan và các index khác.
8. Chỉ thay index/SQL/hint khi có số liệu chứng minh.

## 20. Bài thực hành tự kiểm tra

Các bài thực hành dùng bảng EMPLOYEES, ORDERS, LAB_ORDERS đã nêu. Chạy trong schema thử nghiệm và không tạo index trùng tên với object có sẵn.

### Bài 1 — Unique scan

Tạo primary key trên EMPLOYEE_ID. Truy vấn một ID bằng equality. Dùng DBMS_XPLAN để xác định Oracle có chọn INDEX UNIQUE SCAN hay không. Giải thích bước TABLE ACCESS BY INDEX ROWID nếu xuất hiện.

### Bài 2 — Range scan trên nonunique key

Tạo index trên DEPARTMENT_ID. Truy vấn một phòng ban có nhiều nhân viên. Quan sát INDEX RANGE SCAN và số ROWID trả về.

### Bài 3 — Composite index

Tạo index (CUSTOMER_ID, ORDER_DATE). So sánh truy vấn chỉ lọc CUSTOMER_ID, truy vấn lọc cả CUSTOMER_ID và ORDER_DATE, và truy vấn chỉ lọc ORDER_DATE. Giải thích vai trò leading column.

### Bài 4 — INDEX FULL SCAN

Chạy truy vấn chỉ chọn các cột trong index và có ORDER BY khớp thứ tự khóa. Quan sát xem plan có thể dùng INDEX FULL SCAN để tránh sort hay không.

### Bài 5 — INDEX FAST FULL SCAN

Chạy truy vấn chỉ cần cột index nhưng không có ORDER BY. So sánh plan khi optimizer chọn fast full scan. Kiểm tra kết quả có thứ tự ổn định hay không.

### Bài 6 — Table full scan

Chạy truy vấn trả về phần lớn bảng và nhiều cột. So sánh plan với index range scan khi có predicate chọn lọc hơn. Giải thích vì sao full scan có thể rẻ hơn.

### Bài 7 — Clustering factor

Xem USER_INDEXES cho các index của bảng thử nghiệm. So sánh clustering factor, leaf blocks và actual buffer gets của truy vấn range scan.

### Bài 8 — Predicate dùng hàm

So sánh TRUNC(order_date) = ... với khoảng ngày nửa mở. Xem access predicate và plan. Thử function-based index trong schema thử nghiệm.

### Bài 9 — LIKE prefix và suffix

So sánh LIKE 'AN%' với LIKE '%AN' trên cột có index. Ghi nhận khác biệt trong access path.

### Bài 10 — Đọc actual plan

Thu thập ALLSTATS LAST. So sánh E-Rows và A-Rows, Starts, Buffers và Reads. Nêu nguyên nhân có thể nếu optimizer ước lượng sai cardinality.

## 21. Ghi nhớ

| Operation/khái niệm | Vai trò |
|---|---|
| INDEX UNIQUE SCAN | Tìm tối đa một entry theo đầy đủ khóa unique |
| INDEX RANGE SCAN | Đọc một vùng entry theo predicate |
| INDEX FULL SCAN | Đọc toàn bộ leaf entry theo thứ tự khóa |
| INDEX FAST FULL SCAN | Đọc toàn bộ index block theo throughput, không giữ thứ tự |
| TABLE ACCESS FULL | Đọc toàn bộ block bảng |
| TABLE ACCESS BY INDEX ROWID | Dùng ROWID lấy cột từ table sau index scan |
| Covering index | Index chứa đủ cột cần cho truy vấn |
| Selectivity | Tỷ lệ hàng được ước lượng thỏa predicate |
| Clustering factor | Mức tương quan giữa thứ tự index và vị trí hàng trong table |
| Leading column | Cột đầu tiên của composite index, quan trọng cho range access |
| Access predicate | Điều kiện dùng để định vị vùng dữ liệu |
| Filter predicate | Điều kiện lọc sau khi lấy dữ liệu |

Hãy đọc access path theo công việc thực tế mà truy vấn yêu cầu. Equality trên đầy đủ unique key thường phù hợp unique scan; predicate chọn lọc trên vùng khóa có thể phù hợp range scan; full index scan có thể tận dụng thứ tự khóa; fast full scan ưu tiên throughput khi không cần thứ tự; còn table full scan có thể rẻ nhất khi phải đọc phần lớn bảng. Execution plan và thống kê runtime mới cho biết lựa chọn nào phù hợp với dữ liệu và workload cụ thể.
