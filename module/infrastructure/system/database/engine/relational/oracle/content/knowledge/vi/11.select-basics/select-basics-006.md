# DISTINCT và chi phí loại bỏ dữ liệu trùng trong Oracle

Trong một truy vấn SQL, nhiều hàng kết quả có thể mang cùng một tổ hợp giá trị. Điều này thường xảy ra khi dữ liệu có quan hệ một-nhiều, khi JOIN nhiều bảng hoặc khi một cột chỉ có vài giá trị lặp lại. Oracle cung cấp từ khóa **`DISTINCT`** để loại bỏ các hàng trùng trong tập kết quả. Cú pháp rất ngắn, nhưng chi phí thực thi có thể đáng kể: database phải nhận diện những hàng có cùng giá trị, thường bằng cách sắp xếp hoặc dùng cấu trúc băm, đôi khi phải ghi dữ liệu trung gian xuống TEMP.

Ví dụ:

~~~sql
SELECT DISTINCT department_id
FROM employees;
~~~

Câu truy vấn trả mỗi `DEPARTMENT_ID` một lần, dù bảng `EMPLOYEES` có hàng nghìn nhân viên thuộc cùng phòng ban. Nhưng nếu chọn thêm `EMPLOYEE_ID`:

~~~sql
SELECT DISTINCT department_id, employee_id
FROM employees;
~~~

thì gần như mọi hàng vẫn khác nhau vì `EMPLOYEE_ID` là định danh riêng. **DISTINCT xét toàn bộ tổ hợp biểu thức trong danh sách SELECT**, không tự đoán cột nào là “khóa trùng” theo ý người viết.

Bài học này giải thích semantics của `DISTINCT`, cách Oracle thực hiện duplicate elimination, mối liên hệ với index, `GROUP BY`, `UNION` và `COUNT(DISTINCT ...)`, cách đọc execution plan, cùng những trường hợp nên sửa JOIN hoặc dùng `EXISTS` thay vì thêm DISTINCT để che kết quả nhân bản.

## 1. DISTINCT loại bỏ điều gì?

`DISTINCT` yêu cầu kết quả của một query block chỉ chứa **một hàng cho mỗi tổ hợp giá trị khác nhau của các biểu thức được SELECT**. Nó không xóa dữ liệu gốc trong bảng, không sửa bảng và không đặt ràng buộc duy nhất lên dữ liệu.

| Truy vấn | Kết quả được coi là trùng khi nào? |
| --- | --- |
| `SELECT DISTINCT department_id` | Hai hàng có cùng `department_id`. |
| `SELECT DISTINCT department_id, job_id` | Cả `department_id` và `job_id` đều bằng nhau theo semantics so sánh của kiểu dữ liệu. |
| `SELECT DISTINCT UPPER(email)` | Hai hàng có cùng kết quả `UPPER(email)`, dù chuỗi email gốc có thể khác chữ hoa/thường. |
| `SELECT DISTINCT TRUNC(created_at)` | Hai hàng có cùng ngày sau khi biểu thức `TRUNC` được tính. |
| `SELECT DISTINCT employee_id, employee_name` | Cả mã và tên cùng trùng; thêm một cột duy nhất thường làm giảm khả năng loại bỏ hàng. |

### DISTINCT áp dụng sau phép chiếu

SQL được mô tả theo logic: các hàng nguồn được lọc, kết hợp, tính biểu thức và cuối cùng chỉ giữ một bản sao cho mỗi tổ hợp giá trị kết quả. Optimizer có thể thay đổi thứ tự thao tác vật lý nếu vẫn bảo toàn semantics, nhưng cách hiểu quan trọng là **duplicate được xét trên kết quả SELECT của query block**.

~~~sql
SELECT DISTINCT UPPER(city) AS normalized_city
FROM customers;
~~~

Nếu dữ liệu có `'Ha Noi'`, `'HA NOI'` và `'ha noi'`, biểu thức `UPPER(city)` tạo cùng giá trị `'HA NOI'`; kết quả chỉ có một hàng cho tổ hợp đó.

Ngược lại:

~~~sql
SELECT DISTINCT city
FROM customers;
~~~

không đồng nghĩa với truy vấn trên. Giá trị gốc khác nhau có thể vẫn được giữ thành các hàng riêng. Đừng bỏ biểu thức khỏi SELECT chỉ để có ít kết quả hơn nếu người dùng cần phân biệt các giá trị nguồn.

### DISTINCT trên nhiều cột

Giả sử dữ liệu:

| EMPLOYEE_ID | DEPARTMENT_ID | JOB_ID |
| ---: | ---: | --- |
| 1 | 10 | DEV |
| 2 | 10 | DEV |
| 3 | 10 | QA |
| 4 | 20 | DEV |

`SELECT DISTINCT DEPARTMENT_ID` trả về `10` và `20`. `SELECT DISTINCT DEPARTMENT_ID, JOB_ID` trả về ba tổ hợp:

| DEPARTMENT_ID | JOB_ID |
| ---: | --- |
| 10 | DEV |
| 10 | QA |
| 20 | DEV |

Thêm `EMPLOYEE_ID` vào danh sách SELECT khiến bốn tổ hợp trở thành bốn hàng khác nhau. Đây là lý do phải xác định rõ **đơn vị dữ liệu cần duy nhất** trước khi viết truy vấn.

## 2. NULL và các giá trị được so sánh

Trong kết quả `SELECT DISTINCT`, các hàng có cùng tổ hợp giá trị `NULL` ở các vị trí tương ứng được gom thành **một tổ hợp kết quả**. Điều này khác với cách hiểu của biểu thức `NULL = NULL` trong điều kiện SQL: biểu thức đó không trả `TRUE` mà trả `UNKNOWN`.

Ví dụ:

~~~sql
SELECT DISTINCT commission_pct
FROM employees
ORDER BY commission_pct;
~~~

Nếu nhiều nhân viên không có hoa hồng (`COMMISSION_PCT IS NULL`), kết quả chỉ có **một hàng NULL**. Muốn loại bỏ NULL khỏi danh sách, cần viết điều kiện riêng:

~~~sql
SELECT DISTINCT commission_pct
FROM employees
WHERE commission_pct IS NOT NULL
ORDER BY commission_pct;
~~~

Với nhiều cột, hai hàng chỉ bị loại là trùng khi **tất cả biểu thức trong danh sách SELECT** tương ứng cùng giá trị theo quy tắc so sánh. Ví dụ `(10, NULL)` và `(10, 'A')` là hai tổ hợp khác nhau.

### DISTINCT không phải phép kiểm tra NULL

`DISTINCT` không làm dữ liệu NULL biến mất, cũng không thay đổi số lượng NULL trong bảng:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(commission_pct) AS non_null_commission,
    COUNT(DISTINCT commission_pct) AS distinct_non_null_commission
FROM employees;
~~~

`COUNT(expression)` bỏ qua NULL; vì vậy `COUNT(DISTINCT commission_pct)` đếm số giá trị hoa hồng khác nhau **không NULL**. Nếu muốn đếm cả nhóm NULL như một nhóm riêng, phải cộng thêm điều kiện:

~~~sql
SELECT
    COUNT(DISTINCT commission_pct)
    + CASE
        WHEN COUNT(*) > COUNT(commission_pct) THEN 1
        ELSE 0
      END AS distinct_values_including_null
FROM employees;
~~~

### Kiểu dữ liệu ảnh hưởng khả năng so sánh

Oracle cần xác định cách so sánh các biểu thức để loại bỏ trùng. Một số kiểu dữ liệu không hỗ trợ trực tiếp thao tác so sánh/duplicate elimination như cách áp dụng cho scalar thông thường. Chẳng hạn, **không thể dùng `SELECT DISTINCT` trực tiếp trên cột LOB (`CLOB`/`BLOB`)** như một cột chuỗi hoặc số thông thường. Nếu nghiệp vụ cần nhóm nội dung lớn giống nhau, phải chọn cách biểu diễn/so sánh phù hợp (ví dụ khóa hash có kiểm soát và bước xác minh nội dung), không giả định hash không thể va chạm. Với dữ liệu ký tự, collation, kiểu `CHAR`/`VARCHAR2` và quy tắc so sánh có thể ảnh hưởng thế nào được xem là bằng nhau; hãy giữ nhất quán quy tắc so sánh giữa ứng dụng và database.

## 3. Cú pháp và vị trí của DISTINCT

Trong một query block, `DISTINCT` đặt ngay sau `SELECT`:

~~~sql
SELECT DISTINCT expression_1, expression_2
FROM table_name
WHERE condition;
~~~

Oracle cũng chấp nhận từ đồng nghĩa `UNIQUE` trong một số cú pháp SELECT truyền thống, nhưng nên dùng **`DISTINCT`** vì đây là cách viết phổ biến, dễ hiểu và tương thích với nhiều hệ quản trị.

### DISTINCT kết hợp ORDER BY

`DISTINCT` **không đảm bảo thứ tự kết quả**. Nếu giao diện cần thứ tự, viết `ORDER BY` rõ ràng:

~~~sql
SELECT DISTINCT department_id
FROM employees
ORDER BY department_id;
~~~

Trong Oracle, khi dùng `SELECT DISTINCT`, biểu thức trong `ORDER BY` phải tương thích với danh sách biểu thức được SELECT; tham chiếu cột không được chọn có thể gây `ORA-01791: not a SELECTed expression`. Ví dụ không hợp lệ theo quy tắc này:

~~~sql
-- department_name không có trong danh sách SELECT DISTINCT.
SELECT DISTINCT department_id
FROM employees
ORDER BY department_name;
~~~

Nếu cần sắp xếp theo tên phòng ban, hãy xác định rõ giá trị tên tương ứng và đưa nó vào tập kết quả:

~~~sql
SELECT DISTINCT d.department_id, d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
ORDER BY d.department_name;
~~~

Truy vấn trên loại trùng theo **cặp mã phòng ban và tên phòng ban**. Nếu mã phòng ban là duy nhất và mỗi mã chỉ có một tên, kết quả vẫn là một hàng/phòng ban.

### DISTINCT trong subquery

`DISTINCT` có phạm vi trong query block nơi nó xuất hiện:

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE d.department_id IN (
    SELECT DISTINCT e.department_id
    FROM employees e
    WHERE e.status = 'ACTIVE'
);
~~~

Trong ví dụ này, `IN` chỉ cần tập giá trị để kiểm tra thành viên; duplicate trong subquery thường không làm thay đổi kết quả logic của `IN`. Vì vậy, `DISTINCT` trong subquery có thể không cần thiết và optimizer có thể biến đổi truy vấn. Có thể viết gọn:

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE d.department_id IN (
    SELECT e.department_id
    FROM employees e
    WHERE e.status = 'ACTIVE'
);
~~~

Không nên thêm DISTINCT theo thói quen trong mọi subquery. Hãy xác định toán tử bên ngoài có cần tập duy nhất hay chỉ cần biết có ít nhất một hàng phù hợp.

## 4. Vì sao loại bỏ duplicate có chi phí?

Để trả về một hàng cho mỗi tổ hợp giá trị, Oracle phải xác định những hàng nào tương đương. Nếu dữ liệu đầu vào có `N` hàng, database có thể cần xử lý một lượng lớn hàng trung gian trước khi còn `D` tổ hợp khác nhau (`D ≤ N`).

Chi phí thường phụ thuộc vào:

- **N – số hàng đầu vào:** càng nhiều hàng cần xem xét, công việc loại trùng càng lớn.
- **D – số tổ hợp khác nhau:** ảnh hưởng kích thước kết quả và số lượng nhóm cần giữ.
- **Độ rộng hàng:** loại trùng trên 10 cột rộng tốn bộ nhớ hơn trên một mã số ngắn.
- **Kiểu dữ liệu và biểu thức:** tính `UPPER`, `TRUNC`, chuyển kiểu hoặc xử lý chuỗi trước khi so sánh cũng tiêu tốn CPU.
- **Bộ nhớ workarea (PGA):** đủ bộ nhớ có thể giữ cấu trúc sort/hash trong memory; thiếu bộ nhớ có thể spill xuống TEMP.
- **I/O và parallelism:** nhiều luồng song song, phân phối hàng giữa các process và việc đọc/ghi trung gian có thể làm chi phí tăng.
- **Khả năng tận dụng thứ tự/index:** nếu nguồn đã có thứ tự hoặc tính duy nhất được chứng minh từ metadata, Oracle có thể giảm/bỏ thao tác loại trùng.

Ví dụ, bảng có 10 triệu giao dịch nhưng chỉ 12 trạng thái:

~~~sql
SELECT DISTINCT status
FROM transactions;
~~~

Kết quả chỉ có tối đa 12 hàng, nhưng Oracle vẫn phải xác định các trạng thái trong dữ liệu theo execution plan. Số hàng trả về nhỏ **không đồng nghĩa** công việc xử lý nhỏ.

Ngược lại, nếu một cột là primary key:

~~~sql
SELECT DISTINCT employee_id
FROM employees;
~~~

Oracle biết `EMPLOYEE_ID` duy nhất theo constraint đã được thực thi. Tùy plan và biến đổi optimizer, nó có thể không cần một bước duplicate elimination độc lập. Không nên kết luận rằng mọi `DISTINCT` trên khóa chính chắc chắn sinh `SORT UNIQUE`.

## 5. Oracle loại bỏ duplicate bằng SORT UNIQUE hoặc HASH UNIQUE

Hai thao tác thường gặp trong execution plan là **`SORT UNIQUE`** và **`HASH UNIQUE`**. Chúng là các cách thực hiện duplicate elimination; optimizer chọn kế hoạch theo ước lượng chi phí và các ràng buộc của truy vấn.

### SORT UNIQUE

Mô hình khái niệm:

1. Đọc các hàng đầu vào.
2. Sắp xếp theo những biểu thức cần phân biệt.
3. So sánh các hàng liền kề sau khi sắp xếp.
4. Chỉ phát ra một hàng cho mỗi tổ hợp giá trị.

~~~text
Input:
  (10, DEV)
  (20, DEV)
  (10, DEV)
  (10, QA)

SORT:
  (10, DEV)
  (10, DEV)
  (10, QA)
  (20, DEV)

UNIQUE output:
  (10, DEV)
  (10, QA)
  (20, DEV)
~~~

`SORT UNIQUE` có thể cần workarea trong PGA. Nếu tập dữ liệu lớn hơn vùng nhớ được cấp, sort có thể ghi các run tạm xuống temporary tablespace rồi đọc/trộn lại. Khi đó query có thể phát sinh TEMP I/O dù câu SQL chỉ là SELECT.

### HASH UNIQUE

Mô hình khái niệm:

1. Tính hash key từ các biểu thức cần phân biệt.
2. Tra cấu trúc hash để xem tổ hợp đã xuất hiện chưa.
3. Nếu chưa có, giữ tổ hợp và phát ra hàng; nếu đã có, bỏ hàng trùng.

~~~text
Input row -> compute hash key -> hash table
                                 |
                    +------------+------------+
                    |                         |
                da ton tai                 chua ton tai
                    |                         |
                 bo qua                 luu va phat hang
~~~

Hash table cũng cần memory và có thể spill/phân vùng ra TEMP khi workarea không đủ. Hash collision được xử lý bằng cách kiểm tra giá trị thực, không thể chỉ dựa vào hash code để kết luận hai hàng bằng nhau.

### Oracle chọn cách nào?

Không có quy tắc đơn giản kiểu “ít hàng thì HASH, nhiều hàng thì SORT”. Optimizer xét cardinality ước lượng, độ rộng hàng, cost của nguồn truy cập, thứ tự sẵn có, memory, parallel execution và các phép toán xung quanh. Execution plan có thể có:

| Operation | Ý nghĩa |
| --- | --- |
| `SORT UNIQUE` | Sort theo biểu thức rồi loại các tổ hợp trùng. |
| `HASH UNIQUE` | Dùng cấu trúc hash để loại các tổ hợp trùng. |
| `SORT GROUP BY` | Sort dữ liệu để tạo nhóm; có thể xuất hiện khi xử lý phép tổng hợp. |
| `HASH GROUP BY` | Dùng hash aggregation để tạo nhóm. |
| `INDEX RANGE SCAN` / `INDEX FULL SCAN` | Đọc index theo một đường truy cập; có thể hỗ trợ thứ tự hoặc giảm lượng dữ liệu cần xử lý. |
| `HASH JOIN` / `NESTED LOOPS` / `MERGE JOIN` | Các phép JOIN tạo ra đầu vào cho bước duplicate elimination hoặc được optimizer biến đổi. |

Một câu SQL có `DISTINCT` **không bắt buộc** plan phải chứa operation tên `SORT UNIQUE`. Optimizer có thể chọn `HASH UNIQUE`, tận dụng index, loại bỏ DISTINCT nếu metadata chứng minh không thể trùng, hoặc biến đổi truy vấn theo cách tương đương.

## 6. Workarea, PGA và TEMP khi DISTINCT lớn

Sort và hash duplicate elimination sử dụng **SQL workarea** trong PGA. Nếu workarea đủ lớn, phép toán có thể xử lý tối ưu trong bộ nhớ. Nếu không đủ, Oracle có thể thực hiện một-pass hoặc multi-pass và ghi dữ liệu trung gian xuống temporary tablespace.

| Kiểu thực thi workarea | Đặc điểm | Hệ quả với DISTINCT |
| --- | --- | --- |
| **Optimal** | Đủ memory để hoàn thành phép toán trong workarea | Thường tránh spill do thiếu workarea. |
| **One-pass** | Dùng TEMP cho dữ liệu trung gian và xử lý với số lượt hạn chế | Tăng I/O so với xử lý hoàn toàn trong memory. |
| **Multi-pass** | Phải phân vùng/đọc ghi nhiều vòng do memory quá nhỏ so với dữ liệu | Có thể làm truy vấn chậm đáng kể và tăng tải TEMP. |

Không nên kết luận TEMP cao chỉ do DISTINCT; sort, hash join, group by, analytic function và các công việc khác cũng dùng TEMP. Cần xem SQL ID, workarea và session đang giữ temporary segment.

### Quan sát execution plan thực tế

Ví dụ chạy một truy vấn có hint thu thập thống kê plan:

~~~sql
SELECT /*+ gather_plan_statistics */
       DISTINCT department_id
FROM employees
WHERE hire_date >= DATE '2020-01-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

`DBMS_XPLAN.DISPLAY_CURSOR` hiển thị plan của cursor còn khả dụng trong shared pool. `ALLSTATS LAST` cần thống kê thực thi được thu thập (ví dụ hint `GATHER_PLAN_STATISTICS` hoặc cấu hình phù hợp). Hãy quan sát:

- `E-Rows`: số hàng optimizer ước lượng.
- `A-Rows`: số hàng thực tế tại từng operation trong lần thực thi gần nhất.
- `Buffers`: logical buffer gets được ghi nhận cho operation.
- `Reads` và các thông tin I/O nếu plan/statistics cung cấp.
- `TempSpc` hoặc thống kê workarea liên quan nếu có.
- Vị trí operation `SORT UNIQUE`/`HASH UNIQUE` so với scan và join.

Quyền truy cập cursor/plan và độ chi tiết thống kê phụ thuộc user, phiên bản và cấu hình. Nếu `DISPLAY_CURSOR` không có actual statistics, đừng nhầm plan ước lượng với số liệu thực thi.

### EXPLAIN PLAN không phải số liệu chạy thật

~~~sql
EXPLAIN PLAN FOR
SELECT DISTINCT department_id
FROM employees;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` cho biết plan được tạo cho câu lệnh theo thông tin hiện có, nhưng **không thực thi truy vấn để đo A-Rows, thời gian, buffer thực tế hay TEMP spill**. Muốn hiểu chi phí thật, hãy xem cursor đã chạy với thống kê phù hợp và workload đại diện.

## 7. DISTINCT và index

Index có thể giúp giảm chi phí duplicate elimination, nhưng **không phải cứ thêm index lên cột DISTINCT là truy vấn sẽ nhanh hơn**.

Ví dụ:

~~~sql
SELECT DISTINCT department_id
FROM employees;
~~~

Nếu có index trên `EMPLOYEES(DEPARTMENT_ID)`, Oracle có thể đọc giá trị theo thứ tự index và giảm chi phí truy cập table. Tuy nhiên, plan tối ưu phụ thuộc:

- Tỷ lệ chọn lọc của predicate (nếu có).
- Index có chứa đủ các cột cần SELECT hay không.
- Số block index so với số block table.
- Số lượng giá trị khác nhau và phân bố dữ liệu.
- Cost của index scan so với full table scan và sort/hash.
- Các phép JOIN, filter và parallelism xung quanh.

Nếu SELECT thêm một cột không có trong index, Oracle có thể phải truy cập table cho từng rowid; chi phí đó có thể lớn hơn lợi ích của index. Với cột có rất ít giá trị khác nhau, full scan và hash/sort có thể là lựa chọn hợp lý hơn.

### Index không tự làm dữ liệu trở thành duy nhất

Một **nonunique index** trên `DEPARTMENT_ID` chỉ hỗ trợ truy cập, không ngăn nhiều nhân viên thuộc cùng phòng ban. Một **unique index/constraint** mới bảo đảm tính duy nhất cho khóa được định nghĩa. Hai mục tiêu khác nhau:

- `SELECT DISTINCT`: yêu cầu một tập kết quả không lặp.
- `UNIQUE constraint`: cấm dữ liệu vi phạm được ghi vào bảng.

Nếu nghiệp vụ yêu cầu mỗi email chỉ xuất hiện một lần, hãy dùng `UNIQUE` (và `NOT NULL` nếu email bắt buộc) thay vì chỉ chạy truy vấn DISTINCT để hiển thị danh sách email.

### DISTINCT trên khóa đã duy nhất

~~~sql
SELECT DISTINCT employee_id
FROM employees;
~~~

Nếu `EMPLOYEE_ID` là `PRIMARY KEY` được ENABLE và VALIDATE, mọi hàng trong bảng đã duy nhất theo khóa đó. Optimizer có thể loại bỏ duplicate elimination vì tính duy nhất đã được chứng minh. Đọc plan thay vì đoán từ cú pháp SQL.

## 8. DISTINCT, GROUP BY và các phép hợp tập

### DISTINCT và GROUP BY

Hai truy vấn sau thường cho cùng tập giá trị:

~~~sql
SELECT DISTINCT department_id
FROM employees;

SELECT department_id
FROM employees
GROUP BY department_id;
~~~

Khi không có aggregate expression khác, `GROUP BY` nhóm theo các biểu thức và trả một hàng mỗi nhóm; `DISTINCT` loại các hàng kết quả trùng. Optimizer có thể dùng các chiến lược sort/hash tương tự. Hãy dùng:

- `DISTINCT` khi mục đích chỉ là lấy các tổ hợp giá trị duy nhất.
- `GROUP BY` khi cần tính `COUNT`, `SUM`, `MIN`, `MAX` hoặc các aggregate khác cho từng nhóm.

Không nên dùng `GROUP BY` chỉ để né `DISTINCT` hoặc ngược lại với hy vọng mặc định nhanh hơn; hãy so sánh execution plan và số liệu thực tế.

### DISTINCT và UNION

`UNION` mặc định loại bỏ các hàng trùng giữa các tập kết quả:

~~~sql
SELECT email FROM current_customers
UNION
SELECT email FROM archived_customers;
~~~

`UNION ALL` giữ tất cả hàng, bao gồm các hàng trùng:

~~~sql
SELECT email FROM current_customers
UNION ALL
SELECT email FROM archived_customers;
~~~

`UNION` thường cần duplicate elimination trên kết quả kết hợp; `UNION ALL` không yêu cầu bước đó. Nếu nghiệp vụ không cần loại trùng, `UNION ALL` thường tránh được công việc không cần thiết. Nhưng **không thay UNION bằng UNION ALL** nếu kết quả duy nhất là một phần yêu cầu nghiệp vụ.

Nếu chỉ muốn loại trùng trong từng nguồn trước khi kết hợp, điều đó không luôn tương đương với loại trùng toàn bộ kết quả; hãy xác định rõ phạm vi duplicate cần loại.

### COUNT(DISTINCT expression)

~~~sql
SELECT department_id,
       COUNT(DISTINCT job_id) AS distinct_job_count
FROM employees
GROUP BY department_id;
~~~

Đây là đếm số `JOB_ID` khác nhau trong từng phòng ban. Nó khác `COUNT(*)` (đếm số hàng) và `COUNT(job_id)` (đếm số giá trị job_id không NULL, kể cả lặp). Với aggregate nhiều nhóm, Oracle cần loại trùng **trong phạm vi từng nhóm** cho biểu thức được đếm; chi phí có thể lớn khi có nhiều nhóm và nhiều giá trị khác nhau.

`COUNT(DISTINCT ...)` bỏ qua NULL giống các hàm COUNT trên biểu thức. Nếu nghiệp vụ cần xem NULL là một giá trị riêng, phải thêm logic rõ ràng thay vì mặc định COUNT DISTINCT đã tính NULL.

## 9. DISTINCT sau JOIN: khi nào là hợp lý, khi nào che lỗi?

Một nguyên nhân phổ biến tạo hàng trùng là quan hệ **một-nhiều**. Ví dụ một khách hàng có nhiều đơn hàng:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

Nếu khách hàng có ba đơn, JOIN tạo ba hàng cho khách hàng đó. Nếu yêu cầu chỉ là danh sách khách hàng **có ít nhất một đơn hàng**, thêm DISTINCT sẽ cho kết quả mong muốn:

~~~sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

Nhưng cách diễn đạt tự nhiên hơn là dùng `EXISTS`:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

`EXISTS` thể hiện đúng câu hỏi “có đơn hàng hay không” và không yêu cầu tạo tập kết quả nhân bản rồi mới loại trùng. Optimizer có thể biến đổi thành semi-join để dừng tìm khi đã tìm thấy hàng phù hợp. Kế hoạch cụ thể vẫn phụ thuộc dữ liệu và optimizer.

### Khi DISTINCT che một JOIN sai

Giả sử bảng `ORDER_ITEMS` chứa nhiều dòng cho mỗi đơn hàng. Truy vấn:

~~~sql
SELECT DISTINCT o.order_id, c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN order_items i
  ON i.order_id = o.order_id;
~~~

Nếu chỉ muốn danh sách đơn và khách hàng, việc JOIN `ORDER_ITEMS` tạo thêm hàng nhưng không đóng góp thông tin cần trả. Có thể bỏ JOIN đó nếu không có predicate/điều kiện nghiệp vụ nào cần kiểm tra dòng hàng; hoặc dùng `EXISTS` nếu yêu cầu là “đơn có ít nhất một dòng hàng”.

Đặc biệt nguy hiểm khi JOIN thiếu điều kiện:

~~~sql
-- Sai: thiếu điều kiện liên kết đơn hàng và dòng hàng.
SELECT DISTINCT o.order_id, i.product_id
FROM orders o
CROSS JOIN order_items i;
~~~

DISTINCT không sửa tích Descartes đã tạo ra. Nó chỉ loại những tổ hợp trùng sau khi database phải xử lý nguồn dữ liệu nhân bản. Cần kiểm tra:

1. Khóa nối có đủ không?
2. Có cần JOIN bảng đó cho cột kết quả hoặc điều kiện lọc không?
3. Quan hệ thực tế là 1-1, 1-n hay n-n?
4. Có thể diễn đạt bằng `EXISTS`/`NOT EXISTS` không?
5. Số hàng tăng bao nhiêu sau từng JOIN?

### Khi cần chọn một hàng đại diện, DISTINCT không đủ

Yêu cầu “lấy đơn hàng mới nhất của mỗi khách hàng” không phải bài toán chỉ loại các hàng trùng. Cần quy định **hàng nào được chọn**:

~~~sql
SELECT customer_id, order_id, created_at, total_amount
FROM (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY created_at DESC, order_id DESC
           ) AS rn
    FROM orders o
)
WHERE rn = 1;
~~~

`ROW_NUMBER` chọn một hàng theo thứ tự đã chỉ định. Thêm `ORDER BY order_id DESC` làm tiêu chí phá hòa khi nhiều đơn có cùng `CREATED_AT`, để kết quả có tính xác định. `DISTINCT` chỉ giữ tổ hợp giá trị khác nhau; nó không quyết định bản ghi mới nhất, lớn nhất hay ưu tiên theo trạng thái.

## 10. Những cách viết DISTINCT có thể tốn kém hoặc sai mục tiêu

### SELECT DISTINCT * trên bảng rộng

~~~sql
SELECT DISTINCT *
FROM order_audit;
~~~

Truy vấn yêu cầu so sánh tất cả cột được chọn. Nếu bảng có nhiều cột rộng, dữ liệu văn bản dài hoặc nhiều cột không cần thiết, chi phí sort/hash có thể tăng. Một cột timestamp, sequence hoặc ID khác nhau giữa các bản ghi cũng khiến chúng không còn là duplicate.

Hãy chọn đúng các cột cần trả:

~~~sql
SELECT DISTINCT customer_id, event_type
FROM order_audit;
~~~

Không bỏ cột khỏi SELECT nếu người dùng thực sự cần nó; mục tiêu là tránh mang dữ liệu không cần thiết vào duplicate elimination.

### Thêm ROWID làm mọi hàng khác nhau

~~~sql
-- Thường không đạt mục đích loại trùng theo customer_id:
SELECT DISTINCT customer_id, ROWID
FROM customers;
~~~

`ROWID` định danh vị trí hàng trong bảng heap (có ngoại lệ theo kiểu tổ chức bảng), vì vậy mỗi hàng vật lý thường có ROWID khác nhau. Thêm nó vào SELECT khiến các hàng trước đó giống nhau trở thành khác nhau. Nếu cần loại trùng theo khóa nghiệp vụ, đừng thêm định danh vật lý vào tập biểu thức DISTINCT.

### DISTINCT không thay thế constraint

~~~sql
SELECT DISTINCT email
FROM customers;
~~~

Truy vấn này chỉ trình bày một bản sao của mỗi email trong kết quả. Nó không ngăn một phiên khác INSERT email trùng ngay sau đó. Để bảo đảm duy nhất ở mọi luồng ghi, cần thiết kế `UNIQUE constraint` phù hợp:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Nếu email bắt buộc:

~~~sql
ALTER TABLE customers
MODIFY email NOT NULL;
~~~

Trước khi thêm UNIQUE, phải xử lý duplicate hiện có. DDL thay đổi cấu trúc có implicit commit; không chạy trên bảng sản xuất mà chưa có kế hoạch chuyển đổi.

### DISTINCT không bảo đảm thứ tự

Ngay cả khi plan đang dùng `SORT UNIQUE` và kết quả tình cờ có thứ tự, không được dựa vào điều đó như một hợp đồng SQL. Khi cần thứ tự, luôn dùng `ORDER BY`.

## 11. Tối ưu truy vấn có DISTINCT theo dữ liệu và mục tiêu

Không có một mẹo chung khiến mọi DISTINCT nhanh hơn. Hãy bắt đầu từ câu hỏi nghiệp vụ và đo nguồn công việc mà query đang tạo.

### Giảm số hàng trước duplicate elimination

Nếu nghiệp vụ cho phép lọc dữ liệu sớm, hãy có predicate rõ ràng:

~~~sql
SELECT DISTINCT department_id
FROM employees
WHERE status = 'ACTIVE'
  AND hire_date >= DATE '2024-01-01';
~~~

Ít hàng đầu vào hơn thường làm giảm khối lượng cần loại trùng. Optimizer có thể đẩy predicate và biến đổi query; viết predicate chọn lọc rõ ràng giúp plan có cơ hội tận dụng index/partition pruning phù hợp.

### Giảm độ rộng tập dữ liệu

~~~sql
-- Có thể mang nhiều dữ liệu không cần thiết vào bước distinct:
SELECT DISTINCT department_id, department_name, location_id,
                manager_id, description
FROM departments_view;
~~~

Nếu giao diện chỉ cần mã phòng ban:

~~~sql
SELECT DISTINCT department_id
FROM departments_view;
~~~

Ít biểu thức hơn có thể giảm kích thước sort/hash row và bộ nhớ cần thiết. Tuy nhiên, nếu tên/địa điểm cũng cần thiết để phân biệt kết quả, hãy giữ chúng và thiết kế truy vấn theo yêu cầu thật.

### Dùng EXISTS khi chỉ cần kiểm tra tồn tại

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Truy vấn này trả mỗi khách hàng một lần theo hàng của bảng cha, không nhân bản khách hàng theo số đơn đã thanh toán. Nó mô tả rõ hơn ý nghĩa “khách hàng có ít nhất một đơn PAID”.

### Dùng UNION ALL khi không cần duplicate elimination

Nếu hai nguồn dữ liệu không yêu cầu loại trùng, `UNION ALL` tránh bước loại trùng toàn bộ. Nếu cần loại trùng theo một số cột nhưng vẫn muốn giữ thông tin nguồn, hãy định nghĩa khóa nghiệp vụ và quy tắc chọn hàng trước khi chọn toán tử.

### Tận dụng uniqueness đã được bảo đảm

Nếu cột/biểu thức được suy ra duy nhất nhờ PK/UK, DISTINCT có thể dư thừa. Xóa nó khỏi SQL khi tính duy nhất đã được chứng minh và semantics không đổi có thể làm câu lệnh rõ hơn. Tuy nhiên, nếu DISTINCT là lớp bảo vệ cần thiết trước JOIN nhiều-nhiều, bỏ nó có thể làm thay đổi kết quả.

### Đừng ép optimizer bằng hint khi chưa đo

Các hint hoặc thiết lập session ép một kiểu sort/hash có thể làm query nhanh trong một bộ dữ liệu nhưng chậm khi phân bố hoặc tải thay đổi. Hãy để optimizer chọn trước, đọc actual plan, rồi mới thử phương án có kiểm chứng. Không tăng PGA hoặc TEMP chỉ để che một phép JOIN tạo ra hàng trung gian bất thường.

## 12. Đọc execution plan và thống kê thực tế

Một quy trình thực tế:

1. Chạy truy vấn với bộ lọc và bind values đại diện.
2. Thu thập thống kê thực thi cho cursor.
3. Xác định operation loại trùng (`SORT UNIQUE`/`HASH UNIQUE`) và số hàng đầu vào/đầu ra.
4. So sánh `E-Rows` với `A-Rows` để tìm sai lệch cardinality.
5. Xem buffer gets, physical reads, thời gian, TEMP và các wait event.
6. Thử thay đổi JOIN, predicate, projection hoặc index trên dữ liệu đại diện rồi đo lại.

Ví dụ:

~~~sql
SELECT /*+ gather_plan_statistics */
       DISTINCT c.customer_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

So sánh với cách dùng EXISTS:

~~~sql
SELECT /*+ gather_plan_statistics */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Hai câu có thể cho cùng tập khách hàng nếu điều kiện được viết đúng. Oracle có thể chuyển câu EXISTS thành semi-join; plan có thể không chứa bước duplicate elimination riêng. Hãy so sánh **kết quả**, số hàng trung gian, buffer, CPU và thời gian trong cùng điều kiện dữ liệu. Đừng chỉ nhìn cost estimate hoặc một lần chạy đã được cache khác nhau.

### Một số dấu hiệu trong plan

| Dấu hiệu | Câu hỏi nên đặt |
| --- | --- |
| `SORT UNIQUE` | Có nhiều hàng đầu vào không? Sort có spill ra TEMP không? |
| `HASH UNIQUE` | Hash workarea có đủ memory? Có multi-pass không? |
| `A-Rows` ở JOIN lớn hơn nhiều dự kiến | Cardinality estimate có sai? Điều kiện JOIN có đầy đủ? |
| `A-Rows` trước DISTINCT rất lớn, sau DISTINCT rất nhỏ | Query đang tạo nhiều bản sao; đó có phải quan hệ nghiệp vụ thật hay JOIN dư/sai? |
| `Buffers` cao | Có thể giảm hàng/column trước bước loại trùng? Index có giúp không? |
| `TempSpc` hoặc TEMP usage tăng | Có workarea spill? Nhiều query đồng thời hay parallel server cùng dùng TEMP? |
| DISTINCT biến mất khỏi plan | Optimizer có thể đã chứng minh uniqueness hoặc biến đổi tương đương; kiểm tra semantics và metadata. |

**Actual plan phụ thuộc bind, dữ liệu và phiên bản Oracle.** Một plan ở môi trường phát triển không bảo đảm giống production. Nếu câu lệnh chạy trong nhiều phiên, thống kê toàn session/instance có thể chứa hoạt động khác; cần gắn đúng SQL ID/session khi đo.

## 13. Bài thực hành tổng hợp

Các lệnh dưới đây dùng schema thực hành có quyền `CREATE TABLE` và quota phù hợp. `CREATE TABLE`/`DROP TABLE` là DDL có implicit commit; không chạy trên bảng nghiệp vụ thật.

### Bước 1: tạo dữ liệu có lặp

~~~sql
CREATE TABLE lab_sales (
    sale_id       NUMBER(10) PRIMARY KEY,
    customer_id   NUMBER(10) NOT NULL,
    product_id    NUMBER(10) NOT NULL,
    sale_status   VARCHAR2(20 CHAR),
    sale_amount   NUMBER(12,2),
    created_at    DATE NOT NULL
);

INSERT INTO lab_sales VALUES
    (1, 100, 10, 'PAID', 120, DATE '2025-01-01');
INSERT INTO lab_sales VALUES
    (2, 100, 20, 'PAID', 80, DATE '2025-01-02');
INSERT INTO lab_sales VALUES
    (3, 100, 10, 'PENDING', 120, DATE '2025-01-03');
INSERT INTO lab_sales VALUES
    (4, 200, 10, 'PAID', 120, DATE '2025-01-04');
INSERT INTO lab_sales VALUES
    (5, 200, 10, 'PAID', 120, DATE '2025-01-05');
INSERT INTO lab_sales VALUES
    (6, 300, 30, NULL, NULL, DATE '2025-01-06');

COMMIT;
~~~

### Bước 2: thử DISTINCT trên một và nhiều biểu thức

~~~sql
SELECT DISTINCT customer_id
FROM lab_sales
ORDER BY customer_id;

SELECT DISTINCT customer_id, product_id
FROM lab_sales
ORDER BY customer_id, product_id;

SELECT DISTINCT sale_status
FROM lab_sales
ORDER BY sale_status;
~~~

Đếm số hàng đầu vào, số khách hàng khác nhau và số trạng thái khác nhau:

~~~sql
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT customer_id) AS customers,
       COUNT(DISTINCT sale_status) AS non_null_statuses
FROM lab_sales;
~~~

Giải thích vì sao trạng thái `NULL` chỉ xuất hiện một lần trong SELECT DISTINCT nhưng không được tính trong `COUNT(DISTINCT sale_status)`.

### Bước 3: quan sát JOIN nhân bản

~~~sql
SELECT s.customer_id, s.sale_id
FROM lab_sales s
JOIN (
    SELECT customer_id
    FROM lab_sales
    WHERE sale_status = 'PAID'
) p
  ON p.customer_id = s.customer_id;
~~~

Truy vấn có thể nhân số hàng do khách hàng có nhiều giao dịch PAID. Viết lại theo EXISTS để trả mỗi sale thỏa điều kiện có khách hàng có ít nhất một giao dịch PAID (điều kiện minh họa; hãy xác định chính xác mục tiêu trước khi viết):

~~~sql
SELECT s.customer_id, s.sale_id
FROM lab_sales s
WHERE EXISTS (
    SELECT 1
    FROM lab_sales p
    WHERE p.customer_id = s.customer_id
      AND p.sale_status = 'PAID'
);
~~~

Hai câu trên không nhất thiết trả cùng số hàng nếu truy vấn đầu JOIN tạo nhiều bản sao cho từng sale. Thử so sánh kết quả và giải thích **semi-join/EXISTS chỉ kiểm tra sự tồn tại**.

### Bước 4: so sánh UNION và UNION ALL

~~~sql
SELECT customer_id FROM lab_sales WHERE sale_status = 'PAID'
UNION
SELECT customer_id FROM lab_sales WHERE sale_status = 'PENDING';

SELECT customer_id FROM lab_sales WHERE sale_status = 'PAID'
UNION ALL
SELECT customer_id FROM lab_sales WHERE sale_status = 'PENDING';
~~~

Đếm số hàng của từng kết quả và giải thích vì sao `UNION` cần loại trùng còn `UNION ALL` giữ số lần xuất hiện.

### Bước 5: quan sát execution plan

~~~sql
SELECT /*+ gather_plan_statistics */
       DISTINCT product_id
FROM lab_sales
WHERE sale_status = 'PAID';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Ghi nhận operation, E-Rows, A-Rows và buffers. Sau đó tạo index trong môi trường thử nghiệm:

~~~sql
CREATE INDEX ix_lab_sales_status_product
ON lab_sales (sale_status, product_id);
~~~

Chạy lại câu query và quan sát plan. Optimizer có thể chọn index hoặc vẫn dùng full scan; **việc có index không bắt buộc plan phải dùng index**. So sánh chi phí trên dữ liệu lớn hơn và phân bố đại diện trước khi kết luận.

### Bước 6: dọn dữ liệu

~~~sql
DROP TABLE lab_sales PURGE;
~~~

Chỉ chạy khi đã hoàn thành bài và không cần giữ dữ liệu thực hành.

## 14. Câu hỏi tự kiểm tra

1. **`SELECT DISTINCT department_id` loại trùng theo tiêu chí nào?** Theo giá trị của toàn bộ biểu thức được SELECT trong query block, ở đây là `department_id`.
2. **Nếu thêm `employee_id` là khóa chính vào danh sách SELECT thì sao?** Mỗi hàng thường khác nhau theo employee_id nên DISTINCT không còn loại được các hàng chỉ trùng department.
3. **DISTINCT có xóa duplicate khỏi bảng không?** Không; nó chỉ loại trùng trong kết quả truy vấn.
4. **DISTINCT xử lý nhiều NULL như thế nào?** Các tổ hợp có NULL ở cùng vị trí được gom thành một kết quả; `COUNT(DISTINCT expr)` bỏ qua NULL.
5. **Vì sao DISTINCT có thể cần TEMP?** Sort/hash workarea có thể không đủ PGA và phải spill dữ liệu trung gian xuống temporary tablespace.
6. **SORT UNIQUE khác HASH UNIQUE ở đâu?** Một cách sort rồi so sánh hàng kề; cách kia dùng cấu trúc hash để nhận diện tổ hợp đã thấy.
7. **Có phải query có DISTINCT luôn sinh SORT UNIQUE?** Không; optimizer có thể dùng HASH UNIQUE, tận dụng index, chứng minh uniqueness hoặc biến đổi truy vấn.
8. **DISTINCT và GROUP BY khác gì khi chỉ chọn một cột?** Chúng thường trả cùng tập giá trị; GROUP BY phù hợp hơn khi cần aggregate theo nhóm.
9. **UNION và UNION ALL khác nhau thế nào?** UNION loại trùng toàn bộ kết quả kết hợp; UNION ALL giữ các hàng lặp.
10. **Khi chỉ cần biết khách hàng có đơn hàng, nên cân nhắc gì?** EXISTS/semi-join thường thể hiện đúng ý định và tránh nhân bản hàng cha.
11. **Vì sao DISTINCT không sửa được JOIN thiếu điều kiện?** Nó chỉ xử lý các hàng trùng sau khi nguồn đã nhân bản, còn tích Descartes và chi phí trung gian vẫn có thể rất lớn.
12. **Tại sao thêm ROWID làm giảm hiệu quả DISTINCT?** ROWID thường khác nhau giữa các hàng vật lý nên tổ hợp SELECT trở nên khác nhau.
13. **DISTINCT có bảo đảm kết quả đã sắp xếp không?** Không; cần ORDER BY rõ ràng.
14. **Một UNIQUE constraint khác DISTINCT thế nào?** UNIQUE bảo vệ dữ liệu khi ghi; DISTINCT chỉ định hình kết quả đọc.
15. **Muốn lấy đơn mới nhất mỗi khách hàng, DISTINCT có đủ không?** Không; phải chọn một hàng đại diện theo thứ tự xác định, thường dùng ROW_NUMBER.
16. **EXPLAIN PLAN có cho biết TEMP thực tế đã dùng không?** Không; cần actual cursor/workarea statistics và quan sát session phù hợp.

Khi sử dụng `DISTINCT` trong Oracle, hãy bắt đầu từ câu hỏi **“hai hàng được coi là trùng theo những cột nào?”** rồi xác định liệu duplicate có phải kết quả tự nhiên của quan hệ dữ liệu hay dấu hiệu của JOIN chưa đúng. Sau đó đọc execution plan để hiểu Oracle đang dùng sort, hash hay index, theo dõi PGA/TEMP và đo số hàng thực tế. DISTINCT là công cụ hữu ích để tạo tập kết quả duy nhất, nhưng nó không thay thế constraint, không sửa mô hình JOIN và không bảo đảm thứ tự dữ liệu.
