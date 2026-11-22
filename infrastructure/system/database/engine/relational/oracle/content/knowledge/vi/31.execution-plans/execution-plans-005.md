# NESTED LOOPS, HASH JOIN và SORT MERGE JOIN

Khi một câu SQL kết hợp dữ liệu từ hai hoặc nhiều bảng, Oracle Optimizer phải chọn cách tạo kết quả join. Ba thuật toán quan trọng thường gặp trong execution plan là **NESTED LOOPS**, **HASH JOIN** và **SORT MERGE JOIN**. Trong execution plan Oracle, sort merge join thường hiển thị operation MERGE JOIN và có thể có các operation SORT JOIN ở đầu vào.

Mỗi thuật toán xử lý dữ liệu theo cách khác nhau:

- Nested loops lấy từng hàng từ một row source rồi tìm hàng phù hợp ở row source còn lại.
- Hash join xây dựng hash table từ một row source rồi dò các hàng của row source kia theo join key.
- Sort merge join sắp xếp hai row source theo join key rồi merge hai luồng đã sắp xếp để tìm hàng khớp.

Không có thuật toán nào luôn nhanh nhất. Lựa chọn phụ thuộc số hàng thực tế, selectivity, thống kê, index, thứ tự join, kích thước dữ liệu, bộ nhớ PGA, TEMP, kiểu predicate và số hàng cần trả về. Một query có thể dùng nested loops rất tốt cho giá trị hiếm nhưng cần hash join cho giá trị phổ biến.

Để đọc plan đúng, cần tách ba quyết định của optimizer:

1. **Join order:** bảng hoặc row source nào được kết hợp trước.
2. **Access path:** mỗi row source được lấy bằng full scan, index scan, partition access hay phương thức khác.
3. **Join method:** các row source được kết hợp bằng nested loops, hash join hay sort merge join.

Ba quyết định tương tác với nhau nhưng không phải một. Có index không có nghĩa Oracle bắt buộc dùng nested loops; full table scan cũng không có nghĩa chắc chắn phải hash join.

## 1. Join là gì?

JOIN kết hợp hàng từ hai row source theo một điều kiện. Ví dụ có hai bảng:

~~~sql
CREATE TABLE departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(100)
);

CREATE TABLE employees (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    department_id NUMBER,
    salary        NUMBER(12,2)
);
~~~

Truy vấn:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Oracle cần kết hợp hàng EMPLOYEES với hàng DEPARTMENTS có cùng DEPARTMENT_ID. Optimizer có thể chọn nested loops, hash join hoặc sort merge join tùy ước lượng chi phí.

### 1.1 Row source

Row source là tập hàng đầu vào của một operation trong execution plan. Row source có thể đến từ:

- Table access.
- Index access.
- Một join operation trước đó.
- View hoặc inline view.
- Subquery đã được optimizer biến đổi.
- JSON_TABLE hoặc một row generator khác.

Trong join nhiều bảng, kết quả của join trước có thể trở thành đầu vào cho join tiếp theo. Vì vậy, không phải lúc nào hai row source cũng tương ứng với hai bảng vật lý đơn lẻ.

### 1.2 Join predicate

Join predicate mô tả cách ghép hàng:

~~~sql
ON d.department_id = e.department_id
~~~

Đây là equijoin vì dùng phép bằng. Predicate có thể gồm nhiều cột:

~~~sql
ON a.tenant_id = b.tenant_id
AND a.order_id = b.order_id
~~~

Hoặc điều kiện không phải phép bằng:

~~~sql
ON e.salary BETWEEN g.min_salary AND g.max_salary
~~~

Loại predicate ảnh hưởng tới các thuật toán có thể sử dụng và chi phí ước lượng.

## 2. NESTED LOOPS JOIN

Nested loops là thuật toán join theo kiểu lặp:

1. Đọc một hàng từ row source ngoài (outer/driving row source).
2. Dùng giá trị join key của hàng đó để tìm hàng phù hợp trong row source trong (inner row source).
3. Ghép các hàng khớp và phát kết quả.
4. Chuyển sang hàng tiếp theo của outer row source.
5. Lặp lại cho tới khi outer row source hết hàng.

Sơ đồ:

~~~text
Outer row source
       |
       | fetch one row
       v
   Join key
       |
       v
Inner row source access
 (often an index lookup)
       |
       v
Matching inner rows
       |
       v
Combine and return rows
       |
       +---- next outer row
~~~

### 2.1 Ví dụ nested loops

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = 1001;
~~~

Nếu EMPLOYEE_ID là primary key, predicate có thể chỉ lấy một nhân viên. Oracle có thể:

1. Tìm nhân viên bằng index trên EMPLOYEE_ID.
2. Lấy DEPARTMENT_ID của nhân viên.
3. Dùng index/primary key của DEPARTMENTS để tìm một phòng ban.
4. Trả về kết quả.

Outer row source chỉ có một hàng, inner lookup rất nhỏ. Nested loops thường phù hợp với tình huống này.

### 2.2 Outer và inner row source

Trong nested loops:

- Outer row source cung cấp hàng driving.
- Inner row source được dò cho mỗi hàng outer.

Nếu outer có N hàng, inner access có thể được thực hiện nhiều lần, xấp xỉ N lần theo số hàng outer đi vào operation. Trong plan, cột Starts của operation inner có thể cho thấy số lần operation được khởi chạy.

Tên outer/inner ở đây mô tả vai trò trong thuật toán, không phải bảng cha/con theo mô hình dữ liệu và cũng không nhất thiết là thứ tự bảng được viết trong FROM.

### 2.3 Vì sao nested loops nhanh với tập outer nhỏ?

Giả sử:

- Outer trả 10 hàng.
- Mỗi lookup inner dùng index hiệu quả.
- Mỗi lookup tìm được rất ít hàng.

Oracle chỉ cần thực hiện một số ít index lookup và table access. Không cần đọc toàn bộ hai bảng hoặc xây hash table lớn.

Nested loops thường phù hợp khi:

- Outer row source có cardinality nhỏ.
- Predicate lọc outer rất chọn lọc.
- Inner row source có index phù hợp trên join key.
- Mỗi lookup inner có chi phí thấp.
- Query cần trả kết quả nhanh theo kiểu first rows.

### 2.4 Khi nested loops có thể chậm?

Giả sử outer có 500.000 hàng và mỗi hàng cần lookup inner bằng index. Nếu mỗi lookup gây truy cập block khác nhau, chi phí lặp lại có thể rất lớn:

~~~text
500,000 outer rows
       |
       +--> inner index lookup
       +--> inner index lookup
       +--> inner index lookup
       ...
       +--> inner index lookup
~~~

Nested loops có thể kém hiệu quả khi:

- Outer row source lớn hơn dự kiến.
- Inner lookup phải đọc nhiều block ngẫu nhiên.
- Index không tồn tại hoặc không phù hợp.
- Predicate trên inner không chọn lọc.
- Nhiều outer row cùng dò một vùng dữ liệu nhưng không có lợi ích cache đủ lớn.
- Query cần phần lớn hàng của cả hai bảng.

Khi đó hash join hoặc sort merge join có thể giảm số lần truy cập lặp.

### 2.5 Index trong nested loops

Index trên inner join key thường giúp nested loops hiệu quả:

~~~sql
CREATE INDEX ix_employees_department
ON employees(department_id);
~~~

Tuy nhiên, cần phân biệt:

- Index trên join key.
- Index trên predicate lọc outer.
- Index trên các cột cần trả về.
- Clustering factor của index.

Index lookup có thể vẫn tốn kém nếu phải truy cập nhiều rowid phân tán. Optimizer có thể chọn full scan hoặc phương thức join khác nếu cost thấp hơn.

### 2.6 NESTED LOOPS OUTER

Với LEFT OUTER JOIN:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id;
~~~

Các nhân viên không có department phù hợp vẫn phải xuất hiện, với cột DEPARTMENT_NAME là NULL. Oracle có thể dùng nested loops outer join, thường hiển thị NESTED LOOPS OUTER trong plan.

Thuật toán giữ các hàng của phía được bảo toàn (preserved side) và trả NULL cho phía không khớp.

## 3. HASH JOIN

Hash join thường được dùng cho join dữ liệu lớn, đặc biệt là equijoin. Thuật toán có hai giai đoạn chính:

1. **Build:** Oracle đọc một row source và xây dựng hash table trong workarea.
2. **Probe:** Oracle đọc row source còn lại, tính hash theo join key và tìm các hàng khớp trong hash table.

Sơ đồ:

~~~text
Build row source
       |
       v
Hash join key
       |
       v
Build hash table
       |
       |                  Probe row source
       |                         |
       |                         v
       |                    Hash join key
       |                         |
       +-------------------------+
                   |
                   v
             Find matches
                   |
                   v
             Return joined rows
~~~

### 3.1 Ví dụ hash join

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Nếu truy vấn cần phần lớn hàng của cả hai bảng, optimizer có thể chọn hash join:

1. Đọc DEPARTMENTS và xây hash table theo DEPARTMENT_ID.
2. Đọc EMPLOYEES.
3. Tính hash cho EMPLOYEES.DEPARTMENT_ID.
4. Tìm các department tương ứng trong hash table.
5. Trả các cặp hàng khớp.

Ví dụ chỉ minh họa một lựa chọn build/probe. Optimizer có thể chọn row source khác làm build input dựa trên cardinality, kích thước hàng, predicate và cost.

### 3.2 Build input và probe input

Build input là row source được dùng để xây hash table. Probe input là row source được dò vào hash table.

Thông thường, Oracle cố gắng chọn build input nhỏ hơn sau khi áp dụng filter, vì hash table nhỏ cần ít bộ nhớ hơn. Nhưng không nên suy ra build side chỉ từ kích thước bảng gốc. Predicate, join order, partitioning và transformations có thể làm kích thước row source sau lọc thay đổi đáng kể.

### 3.3 Hash join cần equijoin key

Hash join đặc biệt phù hợp với điều kiện so sánh bằng:

~~~sql
ON a.customer_id = b.customer_id
~~~

Join nhiều key:

~~~sql
ON a.tenant_id = b.tenant_id
AND a.order_id = b.order_id
~~~

Hash function được xây dựng từ các giá trị join key. Các điều kiện bổ sung có thể được áp dụng như filter hoặc join predicate tùy plan.

Với điều kiện không phải phép bằng, sort merge join thường là ứng viên phù hợp hơn; khả năng lựa chọn cụ thể phụ thuộc predicate và phiên bản optimizer.

### 3.4 Vì sao hash join tốt với tập dữ liệu lớn?

Thay vì lookup inner lặp lại cho từng hàng outer, hash join:

- Đọc row source để build một lần.
- Đọc probe row source.
- So khớp bằng hash lookup.

Hash join thường hữu ích khi:

- Cả hai row source có nhiều hàng.
- Predicate là equijoin.
- Có thể đọc các row source hiệu quả bằng full scan/partition scan.
- Build input vừa trong workarea hoặc có thể xử lý spill chấp nhận được.
- Không có index lookup đủ chọn lọc để làm nested loops rẻ hơn.

### 3.5 Hash join và PGA workarea

Hash table cần bộ nhớ trong PGA workarea của process/session. Oracle quản lý workarea theo cấu hình và tải hệ thống.

Nếu workarea đủ lớn, hash join có thể chạy trong memory (optimal execution). Nếu không đủ:

- Oracle có thể phân vùng dữ liệu hash.
- Một phần dữ liệu được ghi ra TEMP.
- Các partition được đọc lại và xử lý theo nhiều lượt.
- I/O TEMP có thể làm query chậm đáng kể.

Trong plan, có thể thấy thông tin workarea như OMem, 1Mem, Used-Mem và TempSpc tùy format, phiên bản và thống kê runtime.

### 3.6 One-pass và multi-pass

Khái quát:

- Optimal: hash workarea đủ bộ nhớ, không cần spill dữ liệu join ra TEMP.
- One-pass: cần ghi/đọc partition trung gian nhưng xử lý trong một lượt chính.
- Multi-pass: phải thực hiện nhiều lượt I/O TEMP hơn do dữ liệu lớn hơn bộ nhớ đáng kể.

Tên gọi và chi tiết thống kê phụ thuộc cách Oracle báo cáo workarea. Khi query chậm, hãy kiểm tra TEMP usage, PGA pressure và SQL Monitor nếu được cấp phép.

### 3.7 Hash join không cần index trên join key

Hash join có thể join hai row source mà không cần index trên cột join. Đây là lợi thế khi cần xử lý lượng lớn dữ liệu.

Điều đó không có nghĩa nên xóa index. Index có thể phục vụ query khác, constraint hoặc nested loops cho workload chọn lọc. Quyết định index cần dựa trên toàn bộ workload.

### 3.8 HASH JOIN OUTER

Oracle có thể dùng hash join cho outer join:

~~~sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

Plan có thể hiển thị HASH JOIN OUTER. Các hàng của phía preserved được giữ lại dù không có hàng tương ứng ở phía còn lại.

### 3.9 Hash join và parallel execution

Hash join thường xuất hiện trong truy vấn phân tích lớn và parallel execution. Oracle có thể phân phối row source giữa các parallel execution servers, dùng hash distribution hoặc partition-wise join tùy thiết kế.

Parallel không tự động làm query nhanh hơn:

- Có chi phí phân phối dữ liệu.
- Có thể tăng TEMP và PGA.
- Có thể gây contention CPU/I/O.
- Có thể ảnh hưởng workload đồng thời.

Chỉ bật parallel khi đo được lợi ích và kiểm soát được tài nguyên.

## 4. SORT MERGE JOIN

Sort merge join kết hợp hai row source bằng cách sắp xếp chúng theo join key rồi quét/merge hai luồng đã có thứ tự.

Hai giai đoạn:

1. Sort mỗi row source theo join key nếu chưa có thứ tự phù hợp.
2. Merge hai luồng đã sắp xếp, tiến con trỏ theo thứ tự key để tìm hàng khớp.

Sơ đồ:

~~~text
Left row source                 Right row source
      |                                |
      v                                v
   Sort by key                     Sort by key
      |                                |
      v                                v
  Sorted stream A                 Sorted stream B
      |                                |
      +---------------+----------------+
                      |
                      v
                 Merge by key
                      |
                      v
                Joined rows
~~~

Trong execution plan, operation join thường hiển thị MERGE JOIN; các đầu vào có thể có SORT JOIN.

### 4.1 Ví dụ sort merge join

~~~sql
SELECT e.employee_id,
       d.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON e.department_id = d.department_id;
~~~

Nếu Oracle chọn sort merge join, plan có thể cần sort EMPLOYEES và DEPARTMENTS theo DEPARTMENT_ID rồi merge chúng. Nếu một row source đã có thứ tự phù hợp nhờ access path, một số bước sort có thể được giảm hoặc bỏ.

### 4.2 Sort merge join có thể phù hợp khi nào?

Sort merge join có thể là lựa chọn tốt khi:

- Hai row source lớn và cần xử lý phần lớn hàng.
- Dữ liệu đã có thứ tự phù hợp hoặc chi phí sort chấp nhận được.
- Điều kiện join không phải equijoin trong những trường hợp hash join không phù hợp.
- Một số đặc điểm của outer/full outer join và row source khiến sort merge có cost tốt.
- Sort có thể phục vụ thêm yêu cầu xử lý của plan, dù không được bảo đảm thay thế ORDER BY cuối cùng.

Với equijoin lớn, hash join thường là đối thủ quan trọng. Optimizer sẽ so sánh cost thực tế dựa trên thống kê và tài nguyên.

### 4.3 Chi phí sort

Sort có thể cần workarea trong PGA. Nếu dữ liệu vượt bộ nhớ, Oracle có thể spill ra TEMP, làm tăng I/O.

Chi phí phụ thuộc:

- Số hàng cần sort.
- Độ rộng mỗi hàng.
- Số cột sort key.
- Bộ nhớ workarea.
- Dữ liệu đã có thứ tự hay chưa.
- Mức độ phân vùng/parallel.

Một plan có hai SORT JOIN không tự động xấu. Cần xem số hàng, bytes, TEMP, buffers và elapsed.

### 4.4 Sort merge join và non-equi join

Ví dụ range join:

~~~sql
SELECT e.employee_id,
       g.grade
FROM employees e
JOIN salary_grades g
  ON e.salary >= g.min_salary
 AND e.salary <  g.max_salary;
~~~

Điều kiện này không phải equijoin. Sort merge join có thể xử lý một số dạng non-equi join mà hash join không phù hợp. Việc optimizer thực sự chọn thuật toán nào phụ thuộc predicate, thống kê và khả năng của phiên bản.

### 4.5 Sort merge join không đồng nghĩa kết quả đã ORDER BY

Đây là điểm rất quan trọng. Dù thuật toán có sắp xếp các row source nội bộ, SQL không bảo đảm thứ tự kết quả nếu câu query không có ORDER BY.

Muốn kết quả có thứ tự:

~~~sql
SELECT e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
ORDER BY e.employee_id;
~~~

Chỉ ORDER BY ở query block cuối mới xác định thứ tự kết quả mà ứng dụng được phép dựa vào.

## 5. So sánh ba thuật toán

| Tiêu chí | NESTED LOOPS | HASH JOIN | SORT MERGE JOIN |
|---|---|---|---|
| Cách xử lý | Lặp outer row, lookup inner | Build hash table rồi probe | Sort hai luồng rồi merge |
| Phù hợp thường gặp | Outer nhỏ, inner lookup rẻ | Hai row source lớn, equijoin | Row source lớn, có thứ tự hoặc non-equi phù hợp |
| Index trên join key | Thường hữu ích cho inner | Không bắt buộc | Có thể giúp cung cấp thứ tự |
| Bộ nhớ | Thường ít cho join operation, nhưng access path có buffer riêng | Cần hash workarea | Cần sort workarea nếu phải sort |
| TEMP | Không phải đặc trưng chính của join method | Có thể spill khi thiếu PGA | Có thể spill khi sort vượt workarea |
| Chi phí nhạy với | Số outer rows × chi phí inner lookup | Kích thước build/probe và hash workarea | Số hàng cần sort và chi phí merge |
| Dữ liệu rất chọn lọc | Thường phù hợp | Có thể không cần thiết | Thường không phải lựa chọn đầu tiên |
| Dữ liệu lớn | Có thể đắt nếu lặp lookup nhiều | Thường là ứng viên mạnh | Có thể tốt khi sort/order phù hợp |
| Kết quả có thứ tự? | Không bảo đảm | Không bảo đảm | Không bảo đảm nếu không ORDER BY |

Đây là quy tắc định hướng, không phải luật cứng. Oracle có thể chọn phương án khác nếu thống kê, join order, predicate hoặc chi phí thực tế khiến lựa chọn đó rẻ hơn.

## 6. Join method khác join order

Giả sử query:

~~~sql
SELECT *
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN regions r
  ON r.region_id = c.region_id;
~~~

Oracle có thể kết hợp:

1. ORDERS với CUSTOMERS trước, sau đó với REGIONS.
2. CUSTOMERS với REGIONS trước, sau đó với ORDERS.

Mỗi thứ tự có thể dùng nested loops, hash join hoặc sort merge join ở từng bước.

Ví dụ:

~~~text
Plan A:
  (ORDERS JOIN CUSTOMERS) JOIN REGIONS

Plan B:
  (CUSTOMERS JOIN REGIONS) JOIN ORDERS
~~~

Join order quyết định thứ tự kết hợp row source. Join method quyết định cách thực hiện từng phép kết hợp. Một plan có thể dùng nested loops ở bước đầu và hash join ở bước sau.

### 6.1 Vì sao join order quan trọng?

Nếu một predicate lọc được 10 hàng từ bảng lớn, kết hợp bảng đó sớm có thể giảm dữ liệu trung gian. Nếu optimizer đánh giá sai selectivity, nó có thể chọn thứ tự join khiến row source trung gian phình lớn.

Histogram, extended statistics, constraints và cardinality estimates ảnh hưởng tới quyết định này.

### 6.2 Access path cũng là quyết định riêng

Một row source có thể được lấy bằng:

- TABLE ACCESS FULL.
- INDEX RANGE SCAN.
- INDEX UNIQUE SCAN.
- INDEX FAST FULL SCAN.
- PARTITION RANGE SCAN.

Nested loops có thể dùng index lookup cho inner row source, nhưng không phải mọi nested loops đều dùng index. Hash join có thể dùng full scan, nhưng không có quy tắc cấm index access ở các row source của hash join.

## 7. Cardinality và cost quyết định join method

Optimizer ước lượng số hàng ở mỗi row source và chi phí xử lý. Nếu ước lượng sai, join method có thể không phù hợp.

Ví dụ:

- Optimizer nghĩ outer chỉ có 10 hàng, chọn nested loops.
- Thực tế outer có 500.000 hàng.
- Inner lookup phải chạy hàng trăm nghìn lần.
- Query chậm hơn dự kiến.

Ngược lại:

- Optimizer nghĩ predicate trả 300.000 hàng, chọn hash join.
- Thực tế chỉ có 5 hàng.
- Một index lookup nested loops có thể rẻ hơn nhiều.

### 7.1 Kiểm tra estimated và actual rows

Dùng GATHER_PLAN_STATISTICS trong môi trường kiểm thử:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id BETWEEN 1000 AND 1010;
~~~

Sau khi fetch hết kết quả:

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

Các cột thường cần đọc:

- E-Rows: số hàng optimizer ước lượng.
- A-Rows: số hàng thực tế được operation xử lý.
- Starts: số lần operation được bắt đầu.
- Buffers: logical reads.
- Reads: physical reads.
- A-Time: thời gian operation theo thống kê có sẵn.
- OMem/1Mem/Used-Mem và TempSpc: thông tin workarea nếu được hiển thị.

Nếu inner operation của nested loops có Starts rất lớn, cần xem mỗi lookup tốn bao nhiêu buffers và tổng thời gian. Nếu hash join hoặc sort merge join dùng TEMP nhiều, cần xem workarea và kích thước row source.

### 7.2 Sai cardinality ở đâu thì sửa ở đó

Đừng vội ép join method nếu nguyên nhân là ước lượng sai. Điều tra:

- Table/column statistics có stale không?
- Histogram có cần thiết không?
- Predicate có implicit conversion không?
- Các cột có tương quan không?
- Bind peeking/Adaptive Cursor Sharing có liên quan không?
- Function trên cột có làm sai selectivity không?
- View/subquery có transformation làm thay đổi cardinality không?

Sửa thống kê hoặc biểu thức có thể giúp optimizer chọn join method tốt hơn mà không cần hint.

## 8. Join với giá trị bind phổ biến và hiếm

Một SQL có thể dùng cùng bind variable nhưng giá trị đầu vào khác nhau:

~~~sql
SELECT o.order_id,
       o.customer_id
FROM orders o
WHERE o.status = :status;
~~~

Nếu STATUS có phân bố lệch:

- STATUS = 'CANCELLED' có thể chỉ trả vài trăm hàng.
- STATUS = 'OPEN' có thể trả hàng triệu hàng.

Với giá trị hiếm, nested loops tới bảng liên quan có thể tốt. Với giá trị phổ biến, hash join có thể phù hợp hơn.

Oracle có bind peeking và Adaptive Cursor Sharing để xử lý một số tình huống selectivity khác nhau. Tuy nhiên, cần xem child cursor và actual plan thay vì giả định mỗi bind luôn có plan riêng.

## 9. Các biến thể join operation trong execution plan

Ngoài ba thuật toán chính, execution plan có thể hiển thị các biến thể theo kiểu quan hệ và cách xử lý.

### 9.1 NESTED LOOPS OUTER

Dùng cho outer join theo nested loops. Các hàng của phía preserved được giữ lại nếu không có hàng khớp.

### 9.2 HASH JOIN OUTER

Dùng hash join để thực hiện outer join. Plan thể hiện operation có hậu tố OUTER.

### 9.3 HASH JOIN SEMI

Semijoin chỉ cần xác định có hàng khớp ở phía còn lại, không cần trả mọi cặp hàng kết hợp.

SQL thường thể hiện qua EXISTS:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Optimizer có thể chuyển EXISTS thành semijoin. Plan có thể hiển thị HASH JOIN SEMI hoặc NESTED LOOPS SEMI.

### 9.4 HASH JOIN ANTI

Antijoin tìm hàng ở một phía không có hàng tương ứng ở phía kia. SQL thường thể hiện bằng NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Optimizer có thể chuyển đổi thành anti join. Plan có thể hiển thị HASH JOIN ANTI hoặc NESTED LOOPS ANTI.

### 9.5 MERGE JOIN CARTESIAN

Cartesian join tạo mọi cặp hàng giữa hai row source khi không có join predicate phù hợp hoặc optimizer xác định phép kết hợp Cartesian có ích trong một tình huống cụ thể.

Nếu hai row source lần lượt có M và N hàng, kết quả Cartesian có M × N hàng.

Không nên nhầm MERGE JOIN CARTESIAN với SORT MERGE JOIN thông thường. Khi thấy operation CARTESIAN trong plan, kiểm tra:

- Có thiếu điều kiện join không?
- Predicate có bị đặt sai trong WHERE/ON?
- Có query transformation tạo Cartesian hợp lệ không?
- Cardinality hai row source có nhỏ không?

## 10. Đọc execution plan cho ba thuật toán

### 10.1 Plan nested loops minh họa

~~~text
--------------------------------------------------------------------------------
| Id | Operation                    | Name              |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT             |                   |
|  1 |  NESTED LOOPS                |                   |
|  2 |   TABLE ACCESS BY INDEX ROWID| EMPLOYEES         |
|  3 |    INDEX RANGE SCAN          | IX_EMP_DEPT       |
|  4 |   TABLE ACCESS BY INDEX ROWID| DEPARTMENTS       |
|  5 |    INDEX UNIQUE SCAN         | PK_DEPARTMENTS    |
--------------------------------------------------------------------------------
~~~

Diễn giải:

1. Lấy nhân viên qua index.
2. Với mỗi nhân viên, dùng DEPARTMENT_ID để lookup phòng ban.
3. Kết hợp hàng và trả kết quả.

Plan trên chỉ là sơ đồ minh họa. Tên index và thứ tự operation phụ thuộc schema/optimizer.

### 10.2 Plan hash join minh họa

~~~text
-----------------------------------------------------------
| Id | Operation          | Name                         |
-----------------------------------------------------------
|  0 | SELECT STATEMENT   |                              |
|  1 |  HASH JOIN         |                              |
|  2 |   TABLE ACCESS FULL| DEPARTMENTS                  |
|  3 |   TABLE ACCESS FULL| EMPLOYEES                    |
-----------------------------------------------------------
~~~

Diễn giải:

1. Một row source được dùng để build hash table.
2. Row source còn lại được probe theo join key.
3. Kết quả được phát ra.

Không kết luận build side chỉ bằng cách nhìn thứ tự dòng trong bảng minh họa; cần hiểu plan thực tế và thông tin operation/optimizer.

### 10.3 Plan sort merge join minh họa

~~~text
-----------------------------------------------------------
| Id | Operation           | Name                        |
-----------------------------------------------------------
|  0 | SELECT STATEMENT    |                             |
|  1 |  MERGE JOIN         |                             |
|  2 |   SORT JOIN         |                             |
|  3 |    TABLE ACCESS FULL| EMPLOYEES                   |
|  4 |   SORT JOIN         |                             |
|  5 |    TABLE ACCESS FULL| DEPARTMENTS                 |
-----------------------------------------------------------
~~~

Diễn giải:

1. Đọc và sắp xếp row source EMPLOYEES.
2. Đọc và sắp xếp row source DEPARTMENTS.
3. Merge hai luồng theo join key.

Nếu access path cung cấp thứ tự phù hợp, plan có thể không cần SORT JOIN cho một hoặc cả hai đầu vào.

## 11. Kiểm tra plan bằng DBMS_XPLAN

### 11.1 GATHER_PLAN_STATISTICS

Trong môi trường thử nghiệm:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
FROM ...
JOIN ...
  ON ...;
~~~

Fetch hết kết quả để thống kê runtime của cursor được cập nhật đầy đủ.

### 11.2 DISPLAY_CURSOR

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +BYTES +PREDICATE +ALIAS'
    )
);
~~~

Nếu query có nhiều cursor trong session, có thể truyền SQL_ID và child number cụ thể thay vì NULL.

### 11.3 So sánh E-Rows/A-Rows

Ví dụ:

| Operation | E-Rows | A-Rows | Starts |
|---|---:|---:|---:|
| Outer index access | 10 | 10 | 1 |
| Inner index access | 1 | 1 | 10 |
| Nested loops output | 10 | 10 | 1 |

Đây là hình dung cho nested loops có outer nhỏ.

Một trường hợp khác:

| Operation | E-Rows | A-Rows | Starts |
|---|---:|---:|---:|
| Outer access | 10 | 500.000 | 1 |
| Inner index access | 1 | 1 | 500.000 |
| Nested loops output | 10 | 500.000 | 1 |

Sai lệch ước lượng ở outer row source có thể khiến nested loops phải thực hiện nhiều lookup hơn dự kiến.

Các con số chỉ minh họa. Trong plan thực tế, A-Rows ở operation có thể là tổng số hàng qua nhiều Starts; cần đọc các cột cùng nhau.

## 12. Tác động của PGA và TEMP

Hash join và sort merge join có thể cần workarea đáng kể:

- Hash join cần vùng nhớ cho hash table.
- Sort merge join cần vùng nhớ để sắp xếp đầu vào nếu chưa có thứ tự.

Khi workarea thiếu:

- Hash join có thể spill partition ra TEMP.
- Sort có thể ghi run ra TEMP rồi merge.
- Elapsed time tăng do I/O tạm.
- Nhiều session đồng thời có thể cạnh tranh PGA/TEMP.

Nested loops thường không cần workarea lớn cho bản thân phép join, nhưng vẫn có thể tạo nhiều random I/O qua inner lookup.

### 12.1 Không tăng PGA chỉ vì thấy hash join spill

Trước khi tăng PGA:

1. Xác nhận query có cardinality hợp lý.
2. Kiểm tra build input có quá lớn do join order/filter không.
3. Kiểm tra row width và cột không cần thiết.
4. Xem có thể lọc dữ liệu sớm không.
5. Xem workload đồng thời và ngân sách bộ nhớ tổng.
6. Đánh giá TEMP và workarea policy.

Một query spill có thể do thống kê sai hoặc join order không tốt, không nhất thiết chỉ do PGA quá nhỏ.

### 12.2 Theo dõi workarea

Các view như V$SQL_WORKAREA, V$SQL_WORKAREA_ACTIVE và thống kê session/system có thể giúp kiểm tra workarea. Cần quyền phù hợp.

Ví dụ xem workarea:

~~~sql
SELECT operation_type,
       policy,
       estimated_optimal_size,
       estimated_onepass_size,
       last_memory_used,
       last_execution,
       optimal_executions,
       onepass_executions,
       multipasses_executions
FROM v$sql_workarea
WHERE sql_id = :sql_id;
~~~

Tên/cột có thể khác theo phiên bản; kiểm tra view metadata nếu truy vấn cần điều chỉnh.

## 13. Hints điều khiển join method

Oracle hỗ trợ các hint như:

- USE_NL(table_alias): yêu cầu dùng nested loops với bảng/row source được chỉ định làm inner row source.
- USE_HASH(table_alias): yêu cầu dùng hash join với row source được chỉ định.
- USE_MERGE(table_alias): yêu cầu dùng sort merge join với row source được chỉ định.
- LEADING(alias...): gợi ý thứ tự join.
- ORDERED: dùng thứ tự row source theo FROM clause trong query block.

Ví dụ:

~~~sql
SELECT /*+ USE_NL(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = 1001;
~~~

USE_NL(d) chỉ định DEPARTMENTS là inner row source trong nested loops theo hint. Nó không đơn giản có nghĩa “dùng nested loops cho toàn bộ query bất kể điều kiện”.

Hash join:

~~~sql
SELECT /*+ USE_HASH(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Sort merge:

~~~sql
SELECT /*+ USE_MERGE(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

### 13.1 Hints không phải cách sửa cardinality

Nếu optimizer chọn nested loops vì ước lượng 10 hàng nhưng thực tế 500.000, thêm USE_HASH có thể làm query cụ thể nhanh hơn. Nhưng nguyên nhân gốc có thể là thống kê sai.

Nếu không sửa nguyên nhân, các SQL khác có thể vẫn gặp plan không tốt. Hints cũng có thể trở nên lỗi thời khi dữ liệu, index hoặc schema thay đổi.

### 13.2 Hint có thể bị bỏ qua

Hint có thể không được áp dụng do:

- Alias không khớp.
- Hint đặt sai query block.
- Cú pháp không hợp lệ.
- Các hint xung đột.
- Join order/transformations không tương thích.
- Row source không thể tham gia phương thức được yêu cầu.

Hãy kiểm tra hint report trong DBMS_XPLAN ở phiên bản hỗ trợ, không giả định comment hint luôn có hiệu lực.

### 13.3 Dùng alias trong hint

Nếu query khai báo:

~~~sql
FROM employees e
JOIN departments d
~~~

thì dùng alias e và d trong hint. Không nên viết tên bảng gốc thay alias khi query đã alias, vì hint có thể không match đối tượng như mong muốn.

## 14. Ví dụ chọn nested loops cho outer nhỏ

Giả sử ứng dụng tìm một nhân viên theo khóa:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = :employee_id;
~~~

Nếu EMPLOYEE_ID là primary key:

- Predicate thường chọn lọc cao.
- Outer row source có thể chỉ một hàng.
- Department lookup theo primary key rất rẻ.
- Nested loops thường là lựa chọn tự nhiên.

Nếu query trả thêm nhiều cột từ bảng lớn, cần xem index coverage và table access by rowid.

## 15. Ví dụ hash join cho báo cáo lớn

Query báo cáo:

~~~sql
SELECT d.region_id,
       SUM(o.order_amount) AS total_amount
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN departments d
  ON d.department_id = c.sales_department_id
WHERE o.created_at >= DATE '2026-01-01'
GROUP BY d.region_id;
~~~

Nếu truy vấn xử lý hàng triệu đơn hàng và một tỷ lệ lớn khách hàng, optimizer có thể chọn hash join để kết hợp row source lớn. Tuy nhiên, cần xem:

- Predicate ngày có pruning/index phù hợp không.
- Số hàng sau filter.
- Kích thước row source.
- Hash workarea và TEMP.
- Join order.
- Partitioning và parallelism.

Không nên ép hash join chỉ vì đây là báo cáo lớn. Actual plan và resource mới quyết định.

## 16. Ví dụ sort merge join cho range join

Giả sử bảng SALARY_GRADES chứa khoảng lương:

~~~sql
CREATE TABLE salary_grades (
    grade       VARCHAR2(2),
    min_salary  NUMBER,
    max_salary  NUMBER
);
~~~

Query:

~~~sql
SELECT e.employee_id,
       e.salary,
       g.grade
FROM employees e
JOIN salary_grades g
  ON e.salary >= g.min_salary
 AND e.salary <  g.max_salary;
~~~

Đây là non-equi join. Sort merge join có thể là một lựa chọn vì hai row source có thể được sắp xếp theo các key phù hợp. Oracle vẫn có thể chọn cách khác tùy dữ liệu và điều kiện.

## 17. Outer join và preserved row source

Với outer join, cần hiểu phía nào phải được giữ lại:

~~~sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

CUSTOMERS là preserved side. Khách hàng không có đơn vẫn xuất hiện.

Oracle có thể triển khai outer join bằng nested loops outer, hash join outer hoặc phương thức phù hợp khác.

### 17.1 Predicate trong ON và WHERE

Hai truy vấn sau không tương đương:

~~~sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.status = 'OPEN';
~~~

~~~sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'OPEN';
~~~

Ở truy vấn thứ hai, điều kiện WHERE loại hàng mà O.STATUS là NULL, nên kết quả có thể tương đương inner join về mặt hàng được giữ. Đặt predicate đúng vị trí là vấn đề ngữ nghĩa, không chỉ là tuning.

## 18. Semi join và anti join

### 18.1 EXISTS

Khi chỉ cần biết có tồn tại hàng liên quan:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Optimizer có thể chuyển thành semijoin. Nó chỉ cần xác định có match, không cần phát mọi cặp customer/order.

### 18.2 NOT EXISTS

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Optimizer có thể dùng antijoin để tìm khách hàng không có đơn.

### 18.3 NOT IN và NULL

Không thay NOT EXISTS bằng NOT IN một cách máy móc:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

Nếu subquery trả về NULL, NOT IN có thể cho kết quả UNKNOWN và không trả hàng như kỳ vọng. NOT EXISTS thường dễ diễn đạt anti-match an toàn hơn khi cột bên trong có thể NULL.

Join method hiển thị trong plan có thể là NESTED LOOPS ANTI, HASH JOIN ANTI hoặc biến thể khác.

## 19. Bloom filter trong một số hash join lớn

Trong một số plan, đặc biệt là data warehouse và parallel query, Oracle có thể dùng bloom filter để giảm số hàng phải chuyển qua các bước tiếp theo.

Bloom filter là cấu trúc xác suất dùng để kiểm tra khả năng một key thuộc tập build:

- Nếu filter nói “không có”, key chắc chắn không thuộc tập.
- Nếu filter nói “có thể có”, vẫn cần kiểm tra join thực tế.
- Có thể có false positive nhưng không có false negative theo mô hình bloom filter chuẩn.

Bloom filter có thể được đẩy xuống scan để loại sớm các hàng không có khả năng join. Đây là tối ưu bổ trợ; không phải join method thay thế hash join.

Plan có thể hiển thị operation/metadata liên quan bloom filter tùy phiên bản và format DBMS_XPLAN.

## 20. Join method và FIRST_ROWS/ALL_ROWS

Optimizer có thể tối ưu mục tiêu khác nhau:

- ALL_ROWS: tối ưu throughput/tổng chi phí xử lý toàn bộ kết quả.
- FIRST_ROWS(n): ưu tiên trả về một số hàng đầu sớm hơn trong một số workload tương tác.

Nested loops có thể bắt đầu trả kết quả sớm khi outer row source nhỏ và inner lookup nhanh. Hash join thường cần build phase trước khi phát nhiều kết quả. Nhưng không có quy tắc rằng FIRST_ROWS luôn chọn nested loops hoặc ALL_ROWS luôn chọn hash join.

Hãy xem mục tiêu optimizer, fetch pattern thực tế của ứng dụng và plan.

## 21. Join method trong query nhiều bảng

Ví dụ query:

~~~sql
SELECT o.order_id,
       c.customer_name,
       p.product_name,
       i.quantity
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN order_items i
  ON i.order_id = o.order_id
JOIN products p
  ON p.product_id = i.product_id
WHERE o.order_date >= DATE '2026-01-01';
~~~

Plan có thể có:

- Index range scan trên ORDERS.
- Nested loops để lookup CUSTOMERS.
- Hash join giữa ORDER_ITEMS và PRODUCTS.
- Một join tiếp theo kết hợp kết quả.

Không cần một join method duy nhất cho cả query. Mỗi operation được chọn riêng theo row source và cost.

## 22. Join method và partition-wise join

Nếu hai bảng được partition tương thích theo join key, Oracle có thể thực hiện partition-wise join trong một số trường hợp:

- Full partition-wise join: các partition tương ứng được join riêng.
- Partial partition-wise join: một row source được phân phối/redistribute để join theo partition.

Partition-wise join có thể giảm dữ liệu cần trao đổi và tận dụng parallelism. Nó là chiến lược tổ chức join theo partition, không phải thuật toán thay thế nested loops/hash/sort merge; các thuật toán đó vẫn có thể được dùng bên trong partition join.

## 23. So sánh ba join method bằng một thí nghiệm

Một thí nghiệm nên:

1. Tạo dữ liệu có kích thước và phân bố đại diện.
2. Gather statistics.
3. Tạo index phù hợp với workload.
4. Viết một query có thể chạy theo nhiều plan.
5. Ghi plan và runtime baseline.
6. Thử hint trong môi trường kiểm thử để so sánh thuật toán.
7. Đo nhiều lần với cùng input.
8. Bỏ hint và xem optimizer tự chọn gì.
9. Đánh giá cả CPU, buffers, TEMP và concurrency.

### 23.1 Query baseline

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

### 23.2 Thử nested loops

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS USE_NL(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

### 23.3 Thử hash join

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS USE_HASH(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

### 23.4 Thử sort merge join

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS USE_MERGE(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

Các hint là công cụ thí nghiệm, không phải đề xuất triển khai. Optimizer có thể bỏ qua hint hoặc tạo plan khác nếu hint không áp dụng được. Kiểm tra hint report và operation thực tế.

### 23.5 Bảng ghi kết quả

| Test | Bind value | Join method | Median elapsed | CPU | Buffers | TEMP | A-Rows |
|---|---|---|---:|---:|---:|---:|---:|
| A | Hiếm | Nested loops | Ghi đo | Ghi đo | Ghi đo | Ghi đo | Ghi đo |
| B | Hiếm | Hash join | Ghi đo | Ghi đo | Ghi đo | Ghi đo | Ghi đo |
| C | Phổ biến | Nested loops | Ghi đo | Ghi đo | Ghi đo | Ghi đo | Ghi đo |
| D | Phổ biến | Hash join | Ghi đo | Ghi đo | Ghi đo | Ghi đo | Ghi đo |

Không điền số giả định rồi coi là kết quả thực tế. Chỉ kết luận sau khi chạy trên môi trường đại diện.

## 24. Khi nào không nên ép join method?

Tránh thêm USE_NL/USE_HASH/USE_MERGE chỉ vì:

- Một query từng chậm một lần.
- Một plan hash khác với môi trường test.
- Một bảng lớn nên “chắc chắn phải hash join”.
- Có index nên “chắc chắn phải nested loops”.
- Plan có SORT JOIN nên “sort là xấu”.

Trước hết kiểm tra:

- Actual cardinality.
- Thống kê bảng/cột/index.
- Histogram và bind values.
- Predicate và implicit conversion.
- Join order.
- Workarea/TEMP.
- Buffer gets và physical reads.
- Tải đồng thời.

Nếu vẫn cần hint, ghi rõ lý do, phạm vi query block, test với bind values khác nhau và theo dõi sau khi dữ liệu thay đổi.

## 25. Các lỗi thường gặp khi đọc join plan

| Hiểu nhầm | Thực tế | Cách kiểm tra |
|---|---|---|
| Nested loops luôn chậm | Rất tốt khi outer nhỏ và inner lookup rẻ | Xem outer A-Rows, inner Starts/Buffers |
| Hash join luôn nhanh với bảng lớn | Có thể spill TEMP hoặc build input quá lớn | Xem workarea, TEMP, elapsed |
| Sort merge join luôn phải sort cả hai bảng | Row source có thể đã có thứ tự phù hợp | Xem SORT JOIN và access path |
| Có index thì phải dùng nested loops | Optimizer so sánh cost toàn plan | Xem cardinality và index access |
| Full scan đồng nghĩa hash join | Full scan chỉ là access path | Phân biệt operation table access và join |
| Sort merge join trả kết quả có thứ tự | SQL không bảo đảm thứ tự nếu thiếu ORDER BY | Kiểm tra query có ORDER BY |
| USE_HASH(c) ép mọi join trong query thành hash | Hint chỉ định row source/điểm join theo quy tắc hint | Xem hint report và plan |
| Join order là join method | Đây là hai quyết định khác nhau | Đọc cấu trúc cây plan |
| Plan hash đổi là query chậm | Plan mới có thể nhanh hơn hoặc chậm hơn | Đo runtime và resource |
| E-Rows bằng A-Rows ở một node nghĩa toàn plan đúng | Các node khác vẫn có thể sai | Kiểm tra toàn bộ plan |
| Hash join không cần bộ nhớ | Cần workarea, có thể dùng TEMP | Xem memory/TEMP |
| Cartesian luôn là bug | Có thể được optimizer chọn có chủ đích với row source nhỏ | Xem predicate, cardinality và transformations |

## 26. Quy trình điều tra query join chậm

Một quy trình có thể áp dụng:

1. Lấy SQL_ID, child number, bind values và plan thực tế.
2. Dùng DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST.
3. Xác định operation có A-Rows/Buffers/Starts lớn.
4. So sánh E-Rows với A-Rows để tìm sai cardinality.
5. Xác định join method và join order tại từng bước.
6. Kiểm tra inner Starts nếu là nested loops.
7. Kiểm tra PGA/TEMP nếu là hash join hoặc sort merge join.
8. Kiểm tra access path và index.
9. Kiểm tra histogram, extended stats, bind peeking và stale stats.
10. Thử phương án trong môi trường kiểm thử, đo và regression test.

Đừng chỉ nhìn dòng operation cuối cùng hoặc plan hash. Bottleneck có thể nằm ở row source đầu vào, join order trước đó hoặc một bước sort/hash trung gian.

## 27. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema thử nghiệm với dữ liệu đủ lớn để phân biệt các phương án.

### Bài 1 — Nested loops với một hàng

Tìm một EMPLOYEE_ID theo primary key rồi join DEPARTMENTS. Xem plan và xác định outer/inner row source, số Starts của inner lookup.

### Bài 2 — Nested loops với nhiều hàng

Bỏ predicate theo primary key, dùng predicate trả nhiều nhân viên. Quan sát khi nào inner index lookup bắt đầu chiếm nhiều buffers.

### Bài 3 — Hash join

Tạo hai bảng lớn có join key. Gather stats và chạy equijoin. Xem plan, build/probe row source, A-Rows và workarea.

### Bài 4 — Sort merge join

Thử query join có row source đã được sắp xếp hoặc có thể dùng index order. Quan sát SORT JOIN có xuất hiện hay không.

### Bài 5 — Non-equi join

Tạo bảng salary grades và join bằng BETWEEN/range predicate. Xem thuật toán optimizer chọn và lý do.

### Bài 6 — Outer join

Tạo khách hàng không có đơn. So sánh LEFT JOIN với inner join và xem NESTED LOOPS OUTER/HASH JOIN OUTER nếu xuất hiện.

### Bài 7 — EXISTS và semijoin

Viết query EXISTS tìm khách hàng có đơn. Quan sát plan có semijoin hay không.

### Bài 8 — NOT EXISTS và antijoin

Viết query NOT EXISTS tìm khách hàng không có đơn. Thêm thử dữ liệu NULL vào cột liên quan và so sánh với NOT IN.

### Bài 9 — Bind skew

Tạo STATUS có một giá trị phổ biến và một giá trị hiếm. Chạy query join với bind khác nhau, kiểm tra child cursor, bind sensitivity và join method.

### Bài 10 — Hash join spill

Trong môi trường được kiểm soát, chạy join với row source lớn và theo dõi workarea/TEMP. Thử giảm số cột hoặc lọc sớm rồi so sánh.

### Bài 11 — Hint comparison

Thử USE_NL, USE_HASH và USE_MERGE. Xác nhận hint có được áp dụng bằng plan/hint report. So sánh runtime nhiều lần.

### Bài 12 — Cardinality

Tạo thống kê sai lệch hoặc thiếu histogram trong schema thử nghiệm. So sánh E-Rows/A-Rows và xem join method thay đổi sau khi gather stats.

## 28. Checklist đọc NESTED LOOPS, HASH JOIN và SORT MERGE JOIN

**Cấu trúc query**

- Join predicate là equijoin hay non-equi?
- Có outer join, EXISTS hoặc NOT EXISTS?
- Join order có hợp lý?
- Có predicate bị đặt sai ON/WHERE?

**Cardinality**

- E-Rows và A-Rows có chênh lệch?
- Outer row source của nested loops có nhỏ như dự kiến?
- Inner Starts có quá lớn?
- Build input của hash join có kích thước hợp lý?
- Số hàng cần sort có lớn?

**Access path**

- Có index phù hợp với inner lookup?
- Clustering factor có làm lookup tốn kém?
- Full scan có hợp lý với tỷ lệ hàng cần đọc?
- Có partition pruning?

**Tài nguyên**

- Hash join có spill TEMP?
- Sort merge có spill TEMP?
- PGA pressure hoặc concurrency có ảnh hưởng?
- Buffers/reads/CPU/elapsed có cải thiện?

**Kiểm chứng**

- Đã xem actual plan thay vì chỉ EXPLAIN PLAN?
- Đã thử bind phổ biến và hiếm?
- Đã fetch hết kết quả trong benchmark?
- Đã chạy nhiều lần?
- Có regression với query khác?
- Có lý do rõ ràng nếu giữ hint?

## 29. Ghi nhớ

| Thuật toán/khái niệm | Quy tắc thực hành |
|---|---|
| NESTED LOOPS | Outer row source cung cấp từng hàng; inner được lookup lặp lại |
| Outer row source | Row source driving trong nested loops |
| Inner row source | Row source được dò cho mỗi hàng outer |
| HASH JOIN | Build hash table từ một row source, probe bằng row source còn lại |
| Build input | Row source dùng xây hash table, thường chọn theo kích thước sau lọc |
| Probe input | Row source dùng dò hash table |
| SORT MERGE JOIN | Sắp xếp hai luồng theo key rồi merge |
| MERGE JOIN | Tên operation thường thấy trong Oracle execution plan |
| SORT JOIN | Operation sắp xếp row source phục vụ merge join |
| Join order | Thứ tự kết hợp row source |
| Access path | Cách lấy hàng từ table/index/partition |
| Join method | Cách kết hợp hai row source |
| E-Rows/A-Rows | So sánh số hàng ước lượng và thực tế |
| Starts | Số lần operation được khởi chạy |
| PGA/TEMP | Tài nguyên quan trọng với hash/sort workarea |
| USE_NL/USE_HASH/USE_MERGE | Hint thử nghiệm join method, không thay thế điều tra cardinality |
| SEMI/ANTI JOIN | Tối ưu cho EXISTS/NOT EXISTS |
| ORDER BY | Cách duy nhất bảo đảm thứ tự kết quả SQL |

Nested loops phù hợp khi row source driving nhỏ và mỗi lookup inner rẻ. Hash join thường phù hợp với equijoin có lượng dữ liệu lớn khi hash workarea đủ hoặc spill chấp nhận được. Sort merge join sắp xếp hai luồng rồi merge, có thể hữu ích khi dữ liệu đã có thứ tự hoặc với một số non-equi join. Optimizer chọn phương án dựa trên cardinality và cost; hãy đọc actual plan, kiểm tra E-Rows/A-Rows, Starts, buffers và TEMP trước khi thay đổi index, thống kê hoặc thêm hint.
