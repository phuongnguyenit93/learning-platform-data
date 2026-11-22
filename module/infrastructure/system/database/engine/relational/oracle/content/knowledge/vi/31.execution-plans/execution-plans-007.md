# Predicate information: access predicate và filter predicate trong Oracle execution plan

## 1. Predicate Information nằm ở đâu trong execution plan?

Execution plan cho biết Oracle thực hiện truy vấn bằng những row source nào: full table scan, index range scan, nested loops, hash join, sort, aggregation, partition iterator và nhiều operation khác. Chỉ nhìn cột Operation thường chưa đủ để hiểu vì sao Oracle chọn một đường truy cập hoặc vì sao truy vấn đọc nhiều row.

Phần **Predicate Information** giải thích điều kiện được gắn vào từng operation. Oracle thường hiển thị hai nhãn:

- **access(...):** điều kiện được dùng để xác định hoặc truy cập row source, ví dụ xác định phạm vi key của index range scan hoặc điều kiện nối hai row source.
- **filter(...):** điều kiện được đánh giá trên các row mà operation nhận được để quyết định row nào được giữ lại.

Ví dụ:

~~~text
Predicate Information (identified by operation id):
---------------------------------------------------
   1 - filter("E"."STATUS"='ACTIVE')
   2 - access("E"."DEPARTMENT_ID"=50)
~~~

Điều đó cho biết predicate DEPARTMENT_ID được dùng ở operation 2 để truy cập index; predicate STATUS được đánh giá tại operation 1 sau khi row được đưa lên tầng table access. Cần đọc operation ID đi kèm để hiểu predicate đang áp dụng ở đâu.

Predicate Information giúp trả lời:

1. Điều kiện nào đang giới hạn phạm vi index scan?
2. Điều kiện nào chỉ được kiểm tra sau khi đã lấy được candidate rows?
3. Predicate thuộc index operation, table access hay join operation?
4. Có cột nào đang bị bọc trong function hoặc implicit conversion?
5. Có predicate nào bị đẩy xuống view, subquery hoặc partition?
6. Vì sao một truy vấn dùng index nhưng vẫn đọc nhiều row?

## 2. Access predicate và filter predicate khác nhau thế nào?

### 2.1. Access predicate

Access predicate được dùng bởi một operation để tìm hoặc xác định các row cần truy cập. Với B-tree index, access predicate thường tạo start key/stop key hoặc xác định key range mà index scan sẽ đi qua.

Ví dụ:

~~~sql
SELECT employee_id, last_name
FROM employees
WHERE department_id = 50;
~~~

Nếu Oracle dùng index trên DEPARTMENT_ID, predicate:

~~~text
access("DEPARTMENT_ID"=50)
~~~

có thể xuất hiện ở operation INDEX RANGE SCAN hoặc INDEX UNIQUE SCAN. Index giúp Oracle tìm phần key liên quan đến department 50 thay vì đọc toàn bộ bảng.

Access predicate cũng có thể là điều kiện nối ở join operation. Ví dụ một nested loops join dùng giá trị từ row bên ngoài để tìm row tương ứng trong index của bảng bên trong.

### 2.2. Filter predicate

Filter predicate được đánh giá trên các row mà operation đã nhận được. Row không thỏa điều kiện sẽ bị loại trước khi chuyển lên operation cha.

Ví dụ:

~~~sql
SELECT employee_id, last_name
FROM employees
WHERE department_id = 50
  AND status = 'ACTIVE';
~~~

Giả sử index chỉ có DEPARTMENT_ID. Oracle có thể dùng index để lấy các row thuộc department 50, sau đó đọc row từ table và kiểm tra STATUS:

~~~text
Predicate Information:
   1 - filter("STATUS"='ACTIVE')
   2 - access("DEPARTMENT_ID"=50)
~~~

Trong tình huống này, STATUS không giúp xác định key range của index DEPARTMENT_ID. Nó được dùng để lọc các row ứng viên sau đó.

### 2.3. Bảng so sánh

| Tiêu chí | Access predicate | Filter predicate |
| --- | --- | --- |
| Vai trò | Xác định cách tìm/truy cập row hoặc ghép row source | Giữ hoặc loại row sau khi operation nhận được |
| Ví dụ trên index | Điều kiện tạo key range | Điều kiện không tạo key range nhưng có thể lọc index entry |
| Ví dụ trên table | Có thể tham gia xác định row source trong một số operation | Lọc row sau khi table access |
| Ví dụ trên join | Join condition dùng để ghép row source | Điều kiện lọc row trước/sau join tùy vị trí được tối ưu |
| Ý nghĩa hiệu năng | Có thể giảm phạm vi tìm kiếm ngay từ đầu | Có thể giảm row truyền lên trên, nhưng candidate row có thể đã được đọc |

Không nên hiểu rằng access luôn tốt và filter luôn xấu. Filter có thể rất chọn lọc và rẻ; access predicate có thể chọn một phạm vi lớn, khiến index scan vẫn tốn nhiều I/O.

### 2.4. Filter predicate không đồng nghĩa với full table scan

Một truy vấn dùng index vẫn có filter predicate. Predicate có thể được kiểm tra:

- Trên table row sau khi lấy ROWID từ index.
- Ngay trên index entry nếu các cột cần thiết có trong index.
- Ở operation join hoặc operation khác.

Vì vậy, thấy FILTER trong Predicate Information không có nghĩa Oracle bỏ index. Phải đọc cả Operation, Name, predicate, cardinality và thống kê thực thi.

### 2.5. Access predicate không có nghĩa index chắc chắn hiệu quả

Nếu điều kiện access trả về 70% số row của bảng, index range scan có thể phải đọc nhiều leaf block, nhiều ROWID và nhiều table block. Full table scan đôi khi rẻ hơn.

Optimizer cân nhắc selectivity, clustering factor, số block, thống kê, partitioning, bind values và chi phí của các operation. Không thể kết luận chỉ từ chữ access.

## 3. Đọc Predicate Information theo operation ID

Ví dụ minh họa:

~~~text
--------------------------------------------------------------------------------
| Id | Operation                            | Name             | Rows | Cost |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT                     |                  |   10 |    5 |
|  1 |  TABLE ACCESS BY INDEX ROWID BATCHED  | EMPLOYEES        |   10 |    5 |
|  2 |   INDEX RANGE SCAN                   | EMP_DEPT_IX      |  100 |    2 |
--------------------------------------------------------------------------------

Predicate Information (identified by operation id):
---------------------------------------------------
   1 - filter("E"."STATUS"='ACTIVE')
   2 - access("E"."DEPARTMENT_ID"=50)
~~~

Đọc theo từng dòng:

- Operation 2 là INDEX RANGE SCAN trên EMP_DEPT_IX. Access predicate DEPARTMENT_ID = 50 xác định các index entry cần đọc.
- Operation 1 là TABLE ACCESS BY INDEX ROWID BATCHED. Filter predicate STATUS = 'ACTIVE' loại các row không phù hợp sau khi table row được truy xuất.
- Operation 0 là SELECT STATEMENT, nhận kết quả từ operation con.

Predicate Information đánh số theo Id trong plan. Không nhầm số operation với thứ tự dòng văn bản. Trong cây execution plan, operation ở dưới thường cung cấp row source cho operation ở trên.

### 3.1. Một operation có thể có nhiều predicate

Ví dụ:

~~~text
   2 - access("DEPARTMENT_ID"=50)
       filter("SALARY">10000)
~~~

Operation 2 vừa dùng DEPARTMENT_ID để truy cập, vừa lọc SALARY. Nếu SALARY không phải key của index, nó có thể được đánh giá ở table operation khác. Nếu SALARY nằm trong index, Oracle có thể kiểm tra nó ngay trên index entry mà không cần đọc table row cho mọi candidate.

Vị trí thực tế phụ thuộc index definition, projection, predicate transformation và plan được chọn.

### 3.2. Predicate có thể được gắn vào nhiều tầng khác nhau

Một điều kiện trong SQL không nhất thiết xuất hiện ở operation mà người đọc nghĩ là tương ứng với câu WHERE ban đầu. Optimizer có thể:

- Đẩy predicate xuống table access.
- Merge view.
- Unnest subquery.
- Chuyển đổi OR thành nhiều nhánh.
- Dùng predicate làm điều kiện join.
- Áp dụng điều kiện trong partition iterator hoặc index operation.

Đọc plan sau tối ưu hóa, không suy luận vị trí predicate chỉ dựa trên thứ tự viết câu SQL.

## 4. Ví dụ cơ bản: index predicate và filter predicate

Giả sử có bảng EMPLOYEES với index trên DEPARTMENT_ID:

~~~sql
CREATE INDEX emp_dept_ix
ON employees(department_id);
~~~

Truy vấn:

~~~sql
SELECT employee_id,
       last_name,
       salary
FROM employees
WHERE department_id = 50
  AND status = 'ACTIVE'
  AND salary >= 10000;
~~~

Một plan có thể có cấu trúc:

~~~text
TABLE ACCESS BY INDEX ROWID BATCHED EMPLOYEES
  INDEX RANGE SCAN EMP_DEPT_IX
~~~

Predicate Information minh họa:

~~~text
1 - filter("STATUS"='ACTIVE' AND "SALARY">=10000)
2 - access("DEPARTMENT_ID"=50)
~~~

Giải thích:

1. Oracle dùng EMP_DEPT_IX tìm key DEPARTMENT_ID = 50.
2. Các ROWID tìm được được dùng để đọc row trong EMPLOYEES.
3. STATUS và SALARY được đánh giá trên row ứng viên ở table access.
4. Chỉ row thỏa cả ba điều kiện mới được trả về.

Đây là ví dụ để hiểu cách đọc. Plan thực tế có thể là full table scan nếu bảng nhỏ, department 50 chiếm tỷ lệ lớn, thống kê khác hoặc chi phí index access cao hơn.

### 4.1. Tạo composite index

Nếu truy vấn thường xuyên dùng đồng thời DEPARTMENT_ID và SALARY, có thể thử index:

~~~sql
CREATE INDEX emp_dept_salary_ix
ON employees(department_id, salary);
~~~

Với truy vấn:

~~~sql
SELECT employee_id, last_name, salary
FROM employees
WHERE department_id = 50
  AND salary >= 10000;
~~~

Một plan phù hợp có thể hiển thị:

~~~text
INDEX RANGE SCAN EMP_DEPT_SALARY_IX
  access("DEPARTMENT_ID"=50 AND "SALARY">=10000)
~~~

Hai điều kiện có thể được dùng để xác định phạm vi key của index. Đây là một ví dụ về việc đưa một predicate từ filter ở table access vào access path của composite index.

### 4.2. Chọn thứ tự cột trong composite index

Với index B-tree (DEPARTMENT_ID, SALARY):

- Predicate bằng trên DEPARTMENT_ID là điều kiện leading-column hữu ích.
- Predicate range trên SALARY tiếp tục thu hẹp vùng key sau giá trị department.
- Chỉ lọc theo SALARY mà không có DEPARTMENT_ID thường không thể dùng một range scan thông thường hiệu quả trên leading prefix; Oracle có thể cân nhắc skip scan hoặc access path khác.

Thứ tự cột phải dựa vào workload, selectivity, các truy vấn khác và khả năng tái sử dụng index. Không có quy tắc tuyệt đối rằng cột có cardinality cao luôn phải đứng đầu.

### 4.3. Predicate sau range key

Với index (DEPARTMENT_ID, SALARY, HIRE_DATE) và điều kiện:

~~~sql
WHERE department_id = 50
  AND salary >= 10000
  AND hire_date >= DATE '2024-01-01'
~~~

Oracle có thể dùng DEPARTMENT_ID và SALARY để xác định phạm vi scan; HIRE_DATE có thể được kiểm tra như filter trên index entry hoặc ở table access tùy plan và các cột có sẵn. Khi đã có range condition trên một key, các key tiếp theo thường không tiếp tục tạo một dải liên tục nhỏ hơn theo cách giống leading equality keys.

Đừng áp dụng máy móc một mẫu Predicate Information cho mọi index. Hãy xem plan thực tế.

## 5. Access và filter trên các loại operation

### 5.1. INDEX UNIQUE SCAN

Ví dụ truy vấn theo primary key:

~~~sql
SELECT *
FROM employees
WHERE employee_id = 100;
~~~

Nếu EMPLOYEE_ID có unique index phù hợp, Oracle có thể dùng INDEX UNIQUE SCAN. Predicate:

~~~text
access("EMPLOYEE_ID"=100)
~~~

Access predicate xác định key duy nhất cần tìm.

### 5.2. INDEX RANGE SCAN

Ví dụ:

~~~sql
SELECT *
FROM employees
WHERE department_id = 50
  AND salary BETWEEN 10000 AND 20000;
~~~

Với composite index (DEPARTMENT_ID, SALARY), các điều kiện có thể tạo key range. Operation INDEX RANGE SCAN đọc các entry nằm trong phạm vi phù hợp.

### 5.3. INDEX FULL SCAN và INDEX FAST FULL SCAN

Index full scan hoặc fast full scan đọc nhiều hoặc toàn bộ index entries. Predicate vẫn có thể xuất hiện:

- Access predicate nếu có điều kiện dùng để điều khiển truy cập theo cấu trúc index.
- Filter predicate nếu điều kiện được kiểm tra trên các entry đã đọc.

Không kết luận rằng dùng index thì chỉ đọc ít entry. Cần xem số buffers, A-Rows, Starts và operation thực tế.

### 5.4. TABLE ACCESS FULL

Ví dụ:

~~~sql
SELECT employee_id
FROM employees
WHERE status = 'ACTIVE';
~~~

Nếu không có index phù hợp hoặc phần lớn row đều ACTIVE, Oracle có thể full scan:

~~~text
TABLE ACCESS FULL EMPLOYEES
  filter("STATUS"='ACTIVE')
~~~

Filter predicate được đánh giá khi Oracle đọc các block của bảng. Full scan không tự động là plan xấu; với tỷ lệ row cần đọc lớn, nó có thể là cách hiệu quả nhất.

### 5.5. TABLE ACCESS BY INDEX ROWID

Đây là bước đọc row từ table bằng ROWID nhận được từ index. Predicate trên operation này thường là filter cho các cột chưa được kiểm tra ở index access.

Nếu index chứa đủ các cột cần trả về và lọc, Oracle đôi khi có thể tránh table access, tùy cấu trúc truy vấn và access path. Nếu phải truy xuất table row cho rất nhiều ROWID phân tán, chi phí có thể tăng.

### 5.6. NESTED LOOPS JOIN

Ví dụ:

~~~sql
SELECT e.employee_id,
       d.department_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id
WHERE d.department_id = 50;
~~~

Trong nested loops:

1. Oracle lấy row từ outer row source, ví dụ DEPARTMENTS.
2. Giá trị DEPARTMENT_ID được truyền sang inner row source.
3. Inner index lookup có thể dùng join predicate làm access predicate.

Predicate Information có thể thể hiện:

~~~text
access("E"."DEPARTMENT_ID"="D"."DEPARTMENT_ID")
~~~

Đây là access condition để tìm employee rows tương ứng với department đang xử lý. Điều kiện lọc trên bảng ngoài có thể xuất hiện ở operation khác.

### 5.7. HASH JOIN

Hash join cũng dùng join predicate để ghép hai row source. Predicate Information thường hiển thị join condition ở operation HASH JOIN, ví dụ:

~~~text
access("E"."DEPARTMENT_ID"="D"."DEPARTMENT_ID")
~~~

Ở đây access không có nghĩa là Oracle dùng B-tree index. Nó mô tả điều kiện ghép row source trong operation. Cách diễn giải phải dựa trên operation name, không chỉ từ nhãn access.

### 5.8. MERGE JOIN

Merge join yêu cầu hai row source được sắp xếp theo join key hoặc được sắp xếp trước. Join condition có thể được hiển thị dưới dạng access predicate của MERGE JOIN. Filter predicate riêng vẫn có thể loại row.

## 6. Predicate trên partitioned table

Với bảng partition, điều kiện lọc có thể giúp Oracle bỏ qua partition không liên quan. Đây là **partition pruning**.

Ví dụ:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE order_date >= DATE '2025-01-01'
  AND order_date <  DATE '2025-02-01';
~~~

Nếu ORDERS partition theo ORDER_DATE, Oracle có thể chỉ truy cập partition tháng 1 năm 2025.

Trong plan, kiểm tra:

- Operation PARTITION RANGE SINGLE, PARTITION RANGE ITERATOR hoặc operation partition tương ứng.
- Cột Pstart và Pstop.
- Predicate Information cho điều kiện ORDER_DATE.

Pstart/Pstop cho biết partition start/stop được chọn. Chúng là thông tin bổ sung, không đồng nghĩa trực tiếp với access predicate/filter predicate.

### 6.1. Static pruning và dynamic pruning

- **Static pruning:** Oracle xác định partition từ literal hoặc điều kiện biết được khi parse/optimization; Pstart/Pstop có thể hiển thị số partition cụ thể.
- **Dynamic pruning:** partition được xác định khi thực thi, ví dụ dựa trên bind variable hoặc giá trị từ row source khác; plan có thể hiển thị KEY/KEY(I) ở Pstart/Pstop tùy trường hợp.

Không chỉ nhìn predicate access/filter để kết luận pruning có xảy ra hay không. Hãy kiểm tra Pstart/Pstop và runtime row source statistics.

### 6.2. Function trên partition key

Điều kiện:

~~~sql
WHERE TRUNC(order_date) = DATE '2025-01-15'
~~~

có thể làm khó việc dùng range pruning hoặc index thông thường tùy partition expression và optimizer transformation.

Dạng khoảng thời gian thường dễ khai thác hơn:

~~~sql
WHERE order_date >= DATE '2025-01-15'
  AND order_date <  DATE '2025-01-16'
~~~

Khoảng nửa mở cũng tránh vấn đề bỏ sót giờ/phút/giây trong ngày. Nếu partition theo expression, cần đánh giá predicate tương thích với partition key thực tế.

## 7. Function, implicit conversion và predicate không sargable

Predicate có thể đúng về logic nhưng không phù hợp với access path mong muốn.

### 7.1. Function bọc cột

Ví dụ:

~~~sql
SELECT *
FROM employees
WHERE UPPER(last_name) = 'SMITH';
~~~

Nếu chỉ có index trên LAST_NAME, Oracle không thể luôn dùng index đó như một range scan trực tiếp trên giá trị UPPER(LAST_NAME). Plan có thể dùng full scan và filter:

~~~text
filter(UPPER("LAST_NAME")='SMITH')
~~~

Một giải pháp là function-based index:

~~~sql
CREATE INDEX emp_upper_last_name_ix
ON employees(UPPER(last_name));
~~~

Sau đó predicate tương thích với expression index có thể được dùng làm access predicate. Cần gather stats và xem plan thực tế.

### 7.2. TRUNC trên cột ngày

~~~sql
WHERE TRUNC(order_date) = DATE '2025-01-15'
~~~

Nếu có index thường trên ORDER_DATE, function có thể ngăn việc dùng index như điều kiện range trực tiếp. Viết lại:

~~~sql
WHERE order_date >= DATE '2025-01-15'
  AND order_date <  DATE '2025-01-16'
~~~

hoặc cân nhắc function-based index nếu truy vấn theo TRUNC là workload chủ đạo và có lý do thiết kế.

### 7.3. Implicit conversion

Giả sử EMPLOYEE_ID là NUMBER nhưng ứng dụng truyền chuỗi:

~~~sql
WHERE employee_id = '100'
~~~

Oracle có thể chuyển chuỗi sang NUMBER; trong một số ngữ cảnh, implicit conversion có thể xuất hiện ở phía cột và làm mất khả năng dùng index như mong đợi. Predicate Information có thể cho thấy biểu thức conversion hoặc INTERNAL_FUNCTION.

Nên bind parameter đúng kiểu dữ liệu của cột:

- NUMBER cho cột NUMBER.
- DATE/TIMESTAMP cho cột thời gian.
- VARCHAR2 cho cột ký tự.

Không dựa vào implicit conversion trong code ứng dụng.

### 7.4. LIKE và wildcard

Với index B-tree trên CODE:

~~~sql
WHERE code LIKE 'ABC%'
~~~

Oracle có thể dùng range access phù hợp vì prefix được xác định.

Ngược lại:

~~~sql
WHERE code LIKE '%ABC'
~~~

không có leading prefix cố định nên index B-tree thông thường khó dùng để tạo range scan hiệu quả. Có thể cần full scan hoặc giải pháp tìm kiếm khác.

### 7.5. OR và IN

Điều kiện:

~~~sql
WHERE department_id = 10
   OR department_id = 20
~~~

có thể được biến đổi thành OR expansion hoặc dùng INLIST ITERATOR tùy plan:

~~~sql
WHERE department_id IN (10, 20)
~~~

Predicate Information có thể biểu diễn nhiều key hoặc một điều kiện INLIST. Không giả định Oracle luôn tạo cùng một plan cho OR và IN.

## 8. Predicate pushdown và query transformation

Optimizer có thể di chuyển predicate đến nơi có thể giảm row sớm hơn.

### 8.1. View merging

~~~sql
SELECT *
FROM (
    SELECT employee_id, department_id, salary
    FROM employees
) e
WHERE e.department_id = 50;
~~~

Optimizer có thể merge inline view vào query ngoài. Predicate DEPARTMENT_ID có thể được áp dụng trực tiếp trên EMPLOYEES.

### 8.2. Predicate pushdown

Nếu view hoặc subquery có thể được tối ưu theo điều kiện từ query ngoài, Oracle có thể đẩy predicate xuống bên trong để giảm số row trung gian.

Điều đó có thể khiến Predicate Information gắn điều kiện ở operation khác với vị trí người viết đặt trong SQL.

### 8.3. Subquery unnesting

~~~sql
SELECT d.department_id
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
      AND e.status = 'ACTIVE'
);
~~~

Optimizer có thể unnest subquery thành semi-join hoặc transformation tương đương. Predicate STATUS có thể xuất hiện ở row source của EMPLOYEES, còn điều kiện DEPARTMENT_ID là join predicate.

### 8.4. Predicate Information mô tả plan sau transformation

Đừng tìm từng predicate theo đúng thứ tự văn bản SQL. Hãy:

1. Xác định operation tree.
2. Đọc Predicate Information theo Id.
3. Xem alias và query block nếu có.
4. Xác định predicate đã được đẩy xuống, chuyển thành join condition hoặc được dùng trong index.
5. Đối chiếu A-Rows, Starts và buffers để biết tác động thực tế.

## 9. Access/filter predicate và selectivity

Selectivity là tỷ lệ row ước tính thỏa một điều kiện. Trong tuning, highly selective thường có nghĩa điều kiện lọc ra rất ít row.

Ví dụ:

- EMPLOYEE_ID = 100 thường rất selective nếu là primary key.
- DEPARTMENT_ID = 50 có thể trả vài phần trăm hoặc phần lớn bảng tùy phân bố.
- STATUS = 'ACTIVE' có thể trả 95% bảng và ít selective.

Một access predicate trên index có thể trả hàng chục nghìn ROWID nếu giá trị có selectivity thấp. Khi đó, chi phí table lookup có thể lớn.

### 9.1. Filter sớm có thể giảm công việc phía trên

Predicate được áp dụng ở operation thấp hơn thường giúp ít row được truyền lên join, sort hoặc aggregation. Tuy nhiên, optimizer tự chọn vị trí dựa trên transformation và cost; không thể ép filter sớm chỉ bằng cách viết điều kiện trước trong WHERE.

### 9.2. Cardinality quan trọng hơn nhãn access/filter

Hãy xem:

- E-Rows: số row optimizer ước tính.
- A-Rows: số row thực tế.
- Starts: số lần operation được khởi chạy.
- Buffers: logical reads.
- Reads: physical reads khi có thống kê.
- A-Time: thời gian thực thi được báo cáo cho operation.

Nếu E-Rows lệch xa A-Rows, optimizer có thể chọn join order hoặc access path không phù hợp. Cần kiểm tra statistics, histograms, bind peeking, correlation giữa cột và data skew.

## 10. Lấy execution plan và Predicate Information

### 10.1. EXPLAIN PLAN

EXPLAIN PLAN lưu một kế hoạch ước tính:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id, last_name
FROM employees
WHERE department_id = 50
  AND status = 'ACTIVE';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Để yêu cầu hiển thị predicate, dùng format phù hợp:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        NULL,
        'BASIC +PREDICATE +ALIAS'
    )
);
~~~

EXPLAIN PLAN không thực thi câu SQL. Nó cho biết plan được ghi vào PLAN_TABLE cho lần explain đó; bind variable và môi trường thực thi thực tế có thể khiến cursor plan khác.

### 10.2. Xem cursor plan thực tế bằng DISPLAY_CURSOR

Trong tuning, thường cần plan của cursor đã thực thi:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       last_name
FROM employees
WHERE department_id = 50
  AND status = 'ACTIVE';
~~~

Sau khi query chạy trong cùng session:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

ALLSTATS LAST yêu cầu runtime plan statistics được thu thập, ví dụ bằng hint GATHER_PLAN_STATISTICS hoặc cấu hình STATISTICS_LEVEL phù hợp. Nó cho phép so sánh E-Rows và A-Rows của lần chạy gần nhất.

### 10.3. Hiển thị bind information

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
~~~

PEEKED_BINDS hiển thị bind values được optimizer peek khi hard parse nếu có và nếu thông tin được lưu. Nó không nhất thiết là giá trị của mọi lần execute sau đó. Cần xử lý output cẩn thận vì bind value có thể chứa dữ liệu nhạy cảm.

### 10.4. Quyền cần thiết

DISPLAY_CURSOR và một số dynamic performance views cần quyền đọc các view nền tương ứng. Nếu user lab không có quyền, DBA cần cấp quyền tối thiểu theo chính sách. Không cấp quyền catalog rộng chỉ để đọc một plan.

### 10.5. SQL_ID và child cursor

Một SQL statement có thể có nhiều child cursor vì bind sensitivity, optimizer environment hoặc các yếu tố khác. Khi cần phân tích chính xác, xác định SQL_ID và CHILD_NUMBER thay vì mặc định cursor gần nhất:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parsing_schema_name
FROM V$SQL
WHERE sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%'
ORDER BY last_active_time DESC;
~~~

Sau đó:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_HERE',
        0,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

SQL text trong V$SQL có thể bị cắt hoặc không duy nhất nếu LIKE rộng. Dùng SQL_ID đã xác định và đúng child cursor.

## 11. Lab: quan sát access predicate và filter predicate

Lab tạo một bảng lớn vừa đủ để minh họa. Kết quả plan phụ thuộc phiên bản, thống kê, cấu hình và môi trường; mục tiêu là học cách đọc, không ép mọi hệ thống tạo một plan giống hệt.

### 11.1. Tạo dữ liệu

~~~sql
CREATE TABLE plan_predicate_lab AS
SELECT LEVEL AS id,
       MOD(LEVEL, 100) AS department_id,
       MOD(LEVEL * 17, 20000) AS salary,
       CASE
           WHEN MOD(LEVEL, 10) = 0 THEN 'INACTIVE'
           ELSE 'ACTIVE'
       END AS status
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Tạo index:

~~~sql
CREATE UNIQUE INDEX plan_predicate_lab_pk
ON plan_predicate_lab(id);

CREATE INDEX plan_predicate_lab_dept_ix
ON plan_predicate_lab(department_id);
~~~

Thu thập statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'PLAN_PREDICATE_LAB',
        cascade => TRUE
    );
END;
/
~~~

### 11.2. Truy vấn chỉ có điều kiện trên index key

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       id,
       department_id
FROM plan_predicate_lab
WHERE department_id = 50;
~~~

Xem plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Nếu optimizer chọn index, hãy tìm INDEX RANGE SCAN và predicate access trên DEPARTMENT_ID. Nếu optimizer chọn full scan vì chi phí, vẫn có thể đọc filter predicate trên TABLE ACCESS FULL. Không ép index chỉ để làm plan trông đẹp.

### 11.3. Thêm điều kiện không nằm trong index

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       id,
       salary
FROM plan_predicate_lab
WHERE department_id = 50
  AND salary >= 15000
  AND status = 'ACTIVE';
~~~

Với index chỉ trên DEPARTMENT_ID, một plan dùng index có thể có:

~~~text
TABLE ACCESS BY INDEX ROWID BATCHED PLAN_PREDICATE_LAB
  filter("SALARY">=15000 AND "STATUS"='ACTIVE')
  INDEX RANGE SCAN PLAN_PREDICATE_LAB_DEPT_IX
    access("DEPARTMENT_ID"=50)
~~~

Predicate SALARY và STATUS cần được kiểm tra trên row ứng viên. Vì chúng không nằm trong index, Oracle thường phải lấy table row để kiểm tra.

### 11.4. Thử composite index

~~~sql
CREATE INDEX plan_predicate_lab_dept_sal_ix
ON plan_predicate_lab(department_id, salary);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'PLAN_PREDICATE_LAB',
        cascade => TRUE
    );
END;
/
~~~

Chạy lại query:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       id,
       salary
FROM plan_predicate_lab
WHERE department_id = 50
  AND salary >= 15000
  AND status = 'ACTIVE';
~~~

Nếu optimizer dùng composite index, access predicate có thể chứa DEPARTMENT_ID và SALARY. STATUS vẫn là filter vì không nằm trong index. Plan thực tế có thể khác; hãy đọc đúng Predicate Information được tạo ra.

### 11.5. Xóa dữ liệu lab

~~~sql
DROP TABLE plan_predicate_lab PURGE;
~~~

Chỉ chạy khi đã hoàn thành bài thực hành và không cần giữ dữ liệu.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Access predicate luôn nhanh hơn filter predicate | Không. Access có thể chọn phạm vi lớn; phải xem selectivity, buffers và A-Rows |
| Filter predicate nghĩa là Oracle không dùng index | Sai. Filter có thể nằm trên index operation hoặc table operation sau index |
| Mọi điều kiện WHERE đều phải xuất hiện ở một operation riêng | Optimizer có thể kết hợp, biến đổi, đẩy hoặc loại predicate dư thừa |
| Access predicate chỉ xuất hiện ở index scan | Sai. Join operation cũng có access predicate |
| Filter predicate luôn được đánh giá ở cuối truy vấn | Sai. Nó có thể được áp dụng ở row source thấp để giảm row sớm |
| Có index là Oracle luôn dùng index | Sai. Cost-based optimizer so sánh chi phí |
| Thấy INDEX RANGE SCAN là truy vấn đã tối ưu | Chưa đủ. Có thể đọc nhiều index entry và nhiều table block |
| EXPLAIN PLAN là plan chắc chắn đã chạy | Sai. DISPLAY_CURSOR phản ánh cursor plan đã thực thi |
| Predicate trong plan luôn giữ nguyên biểu thức SQL gốc | Sai. Optimizer có thể rewrite hoặc chuẩn hóa biểu thức |
| Pstart/Pstop chính là access predicate | Không. Đây là thông tin partition start/stop, cần đọc cùng predicate |

## 13. Quy trình đọc Predicate Information khi tuning

Khi điều tra một SQL chậm, có thể theo trình tự:

1. Lấy đúng cursor plan đã thực thi bằng DISPLAY_CURSOR.
2. Xác định SQL_ID và child cursor nếu có nhiều plan.
3. Đọc operation tree từ các row source thấp lên trên.
4. Đối chiếu Predicate Information với operation ID.
5. Tìm access predicate: index key, join key, range condition hoặc partition-related access.
6. Tìm filter predicate: điều kiện loại row sau khi row source đã lấy được candidate.
7. Kiểm tra function, implicit conversion, datatype mismatch và bind values.
8. Với partitioned table, xem Pstart/Pstop để đánh giá pruning.
9. So sánh E-Rows với A-Rows; xác định operation có cardinality lệch lớn.
10. Xem Buffers, Starts, A-Time và số row thực tế để tìm điểm tốn chi phí.
11. Đánh giá statistics, histograms, composite index và data skew.
12. Thay đổi một yếu tố tại một thời điểm rồi đo lại trên dữ liệu đại diện.

Không tạo index chỉ vì thấy filter predicate. Trước hết xác định điều kiện có đủ selective không, có được dùng thường xuyên không, chi phí DML/index maintenance là bao nhiêu và index mới có phục vụ nhiều truy vấn liên quan không.

## 14. Checklist đọc access/filter predicate

1. **Đã xem đúng cursor chưa?** Phân biệt EXPLAIN PLAN với DISPLAY_CURSOR.
2. **Đã bật runtime statistics chưa?** Dùng GATHER_PLAN_STATISTICS hoặc cấu hình phù hợp.
3. **Đã map đúng operation ID chưa?** Predicate thuộc operation nào?
4. **Access predicate đang làm gì?** Xác định index range, key lookup hay join condition.
5. **Filter predicate đang lọc ở đâu?** Index entry, table row hay join output?
6. **Có composite index phù hợp không?** Xem leading columns, equality/range và trailing predicates.
7. **Có function hoặc conversion trên cột không?** Kiểm tra UPPER, TRUNC, TO_NUMBER, INTERNAL_FUNCTION.
8. **Có partition pruning không?** Xem Pstart/Pstop.
9. **Có predicate pushdown hoặc view merging không?** Đọc plan sau transformation.
10. **Cardinality có đúng không?** So E-Rows với A-Rows.
11. **Index access có thực sự rẻ không?** Xem Buffers, ROWID lookups, Starts và selectivity.
12. **Có bind-sensitive plan không?** Kiểm tra SQL_ID, child cursor và peeked binds.
13. **Đã kiểm tra nhiều giá trị đầu vào chưa?** Một plan tốt cho bind này có thể không tốt cho bind khác.
14. **Đã đo lại sau thay đổi chưa?** Dùng runtime evidence, không chỉ dựa vào plan text.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Predicate Information cung cấp thông tin gì ngoài tên operation?

**Câu 2.** Access predicate là gì?

**Câu 3.** Filter predicate là gì?

**Câu 4.** Vì sao filter predicate không có nghĩa là full table scan?

**Câu 5.** Predicate Information được liên kết với operation bằng thông tin nào?

**Câu 6.** Access predicate trong HASH JOIN có nhất thiết liên quan tới B-tree index không?

**Câu 7.** Với index (DEPARTMENT_ID, SALARY), vì sao điều kiện bằng trên DEPARTMENT_ID và range trên SALARY có thể tạo access predicate?

**Câu 8.** Vì sao predicate trên cột không nằm trong index có thể trở thành filter ở table access?

**Câu 9.** Vì sao function bọc cột có thể làm mất index range scan thông thường?

**Câu 10.** Function-based index giải quyết trường hợp nào?

**Câu 11.** Pstart/Pstop cho biết điều gì?

**Câu 12.** Predicate pushdown ảnh hưởng vị trí predicate trong plan ra sao?

**Câu 13.** Vì sao access predicate vẫn có thể dẫn tới nhiều I/O?

**Câu 14.** EXPLAIN PLAN khác DISPLAY_CURSOR thế nào?

**Câu 15.** ALLSTATS LAST cần điều kiện thu thập runtime statistics nào?

**Câu 16.** Vì sao phải so E-Rows và A-Rows?

**Câu 17.** Khi nào filter predicate trên index entry có thể tránh table lookup?

**Câu 18.** Vì sao không nên tạo index chỉ dựa trên nhãn FILTER?

<details>
<summary>Gợi ý đáp án</summary>

1. Cho biết điều kiện truy cập và điều kiện lọc gắn với từng operation.
2. Điều kiện được dùng để tìm hoặc xác định row source, key range hoặc join matching.
3. Điều kiện được đánh giá trên các row operation nhận được để giữ hoặc loại row.
4. Vì filter có thể xuất hiện sau index scan hoặc trên nhiều loại operation khác.
5. Operation ID trong execution plan.
6. Không. Trong HASH JOIN, access có thể là join condition dùng để ghép row source.
7. Leading equality xác định vùng key của department; range trên key tiếp theo thu hẹp phạm vi trong vùng đó.
8. Index không chứa giá trị cột đó nên Oracle có thể cần đọc table row để kiểm tra.
9. Index thường lưu giá trị cột gốc; function expression có thể không khớp key index thông thường.
10. Khi workload thường xuyên lọc theo expression như UPPER(column) hoặc TRUNC(date).
11. Partition start/stop được chọn; giúp đánh giá partition pruning.
12. Predicate có thể được áp dụng ở row source thấp hơn sau optimizer transformation.
13. Access range có thể có selectivity thấp và trả nhiều entry/ROWID.
14. EXPLAIN PLAN là kế hoạch ước tính được ghi vào PLAN_TABLE; DISPLAY_CURSOR xem plan của cursor đã thực thi.
15. Runtime plan statistics cần được thu thập, ví dụ GATHER_PLAN_STATISTICS hoặc STATISTICS_LEVEL phù hợp.
16. Để phát hiện sai lệch cardinality ảnh hưởng join order và access path.
17. Khi mọi cột cần lọc có sẵn trong index entry và optimizer có thể đánh giá predicate ngay tại index operation.
18. Vì phải xem selectivity, index definition, operation, buffers, row counts và chi phí DML.

</details>

## 16. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Tuning Guide — Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html): cách tạo, hiển thị và diễn giải execution plan.
2. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): DISPLAY, DISPLAY_CURSOR và format options.
3. [Oracle Database 19c SQL Tuning Guide — Optimizer Access Paths](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html): full table scan, index access và access path selection.
4. [Oracle Database 19c SQL Tuning Guide — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/joins.html): nested loops, hash join, merge join và join predicates.
5. [Oracle Database 19c SQL Tuning Guide — Optimizer Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html): cardinality, selectivity và statistics.
6. [Oracle Database 19c SQL Tuning Guide — Query Transformations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html): view merging, predicate pushing và subquery transformations.
7. [Oracle Database 19c VLDB and Partitioning Guide — Partition Pruning](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-pruning.html): static/dynamic pruning và Pstart/Pstop.
8. [Oracle Database 19c SQL Tuning Guide — Managing Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html): lựa chọn index access path và cách optimizer sử dụng index.

**Nguyên tắc cần nhớ:** access predicate cho biết operation dùng điều kiện nào để truy cập hoặc ghép row; filter predicate cho biết điều kiện nào được áp dụng để loại row ở operation đó. Luôn gắn predicate với operation ID, đọc cùng cây plan, index definition, partition information và runtime statistics. Nhãn access/filter là manh mối để giải thích cách Oracle thực thi, không phải kết luận độc lập về hiệu năng.
