# FILTER, SORT, HASH GROUP BY và WINDOW SORT trong Oracle Execution Plan

Khi Oracle thực thi một câu SQL, optimizer chọn một kế hoạch gồm các operation (operator) nối với nhau thành cây row source. Mỗi operator nhận hàng từ các bước con, xử lý chúng rồi trả hàng cho bước cha. Trong cây này, FILTER, SORT, HASH GROUP BY và WINDOW SORT mô tả bốn kiểu xử lý thường gặp:

- **FILTER** kiểm tra điều kiện trên hàng do row source phía dưới cung cấp và chỉ chuyển tiếp những hàng thỏa điều kiện.
- **SORT** sắp xếp hàng theo một hoặc nhiều khóa, hoặc thực hiện các thao tác cần thứ tự như loại trùng.
- **HASH GROUP BY** gom hàng thành nhóm bằng cấu trúc băm trong bộ nhớ làm việc.
- **WINDOW SORT** tổ chức hàng theo partition/order key để tính các analytic function như ROW_NUMBER, RANK, LAG hoặc SUM OVER.

Các operator này không phải lệnh SQL mà lập trình viên gọi trực tiếp. Chúng là cách Oracle mô tả một phần công việc trong execution plan. Một câu SQL có thể dùng nhiều operator, có thể không dùng operator nào trong bốn loại này, và optimizer có thể chọn kế hoạch khác nhau theo thống kê, bind value, phiên bản, cấu hình và dữ liệu thực tế.

Bài học tập trung vào cách đọc bốn operator, phân biệt chúng với predicate hoặc cú pháp SQL, hiểu tác động tới PGA/TEMP, và dùng DBMS_XPLAN để kiểm tra kế hoạch thực thi cùng số liệu runtime.

## 1. Execution plan và row source

### 1.1. Operator là bước xử lý trong cây thực thi

Execution plan mô tả cách Oracle lấy và biến đổi dữ liệu. Một cây đơn giản có thể trông như sau:

~~~text
SELECT STATEMENT
  SORT ORDER BY
    FILTER
      TABLE ACCESS FULL EMPLOYEES
~~~

Đọc từ dưới lên theo quan hệ cha-con:
1. TABLE ACCESS FULL đọc hàng từ EMPLOYEES.
2. FILTER kiểm tra điều kiện và chỉ chuyển tiếp hàng phù hợp.
3. SORT ORDER BY sắp xếp kết quả.
4. SELECT STATEMENT trả kết quả cho client.

Đây là ví dụ minh họa. Kế hoạch thực tế có thể dùng index, join, partition pruning, hash aggregation hoặc các phép biến đổi khác.

### 1.2. Row source

Row source là nguồn hàng mà operator cung cấp cho operator phía trên. Một bước có thể:
- Đọc hàng từ bảng hoặc index.
- Kết hợp hàng từ hai nguồn.
- Lọc hàng.
- Sắp xếp hàng.
- Gom hàng thành nhóm.
- Tính giá trị analytic.
- Trả kết quả cuối.

Operator phía trên thường tiêu thụ hàng từ các operator con. Một số operator có thể xử lý theo kiểu pipeline, trong khi các operator cần nhìn trước nhiều hàng (blocking hoặc partially blocking) có thể phải tích lũy dữ liệu trước khi trả kết quả.

### 1.3. Execution plan không phải thứ tự dòng SQL

Không đọc plan như danh sách câu lệnh từ trên xuống. Cột Id và quan hệ cây cho biết cấu trúc. Với plan dạng cây, thường cần đọc từ các lá lên các nút cha để hiểu luồng dữ liệu.

Ngoài ra:
- Optimizer có thể đổi thứ tự join và đẩy predicate xuống dưới.
- Subquery có thể được unnest hoặc biến đổi thành join.
- Một số operation có thể chạy nhiều lần.
- Parallel execution có thể chia công việc giữa nhiều process.
- Adaptive plan có thể chọn nhánh hoặc phương án dựa trên runtime.

Vì vậy, hãy kết hợp cây operation với Predicate Information và runtime statistics.

### 1.4. Cost không phải thời gian thực tế

Cost là ước lượng tương đối của optimizer để so sánh các kế hoạch. Cost không phải số mili giây và không bảo đảm kế hoạch có cost thấp hơn sẽ chạy nhanh hơn trong mọi lần chạy.

Khi chẩn đoán, cần xem:
- Cardinality ước lượng và số hàng thực tế.
- Starts của operator.
- Logical I/O, physical I/O.
- Thời gian và mức sử dụng TEMP.
- Bind values, statistics và điều kiện chạy.

## 2. FILTER — lọc hàng trong row source

### 2.1. FILTER làm gì?

FILTER nhận hàng từ row source con, đánh giá điều kiện filter rồi chuyển tiếp các hàng thỏa điều kiện. Nó thường xuất hiện khi predicate không được xử lý hoàn toàn ngay tại access path hoặc khi kế hoạch cần đánh giá một điều kiện/subquery ở bước riêng.

Ví dụ:

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM   employees
WHERE  salary > 5000;
~~~

Một kế hoạch có thể có TABLE ACCESS FULL rồi FILTER. Oracle đọc các hàng và kiểm tra salary. Nhưng không nên kết luận mọi WHERE clause đều tạo operation FILTER. Optimizer có thể đưa predicate vào access path, dùng index range scan, partition pruning hoặc kết hợp điều kiện vào operation khác.

### 2.2. FILTER operation khác filter predicate

Đây là hai khái niệm dễ nhầm:

- **FILTER operation** là một node trong cây execution plan.
- **filter predicate** là điều kiện được thực thi ở một operation, thường xuất hiện trong phần Predicate Information.

Ví dụ phần Predicate Information có thể hiển thị:

~~~text
filter("E"."SALARY">5000)
~~~

Điều đó cho biết predicate được áp dụng tại bước tương ứng. Nó không tự chứng minh plan có một node tên FILTER. Một TABLE ACCESS hoặc INDEX operation cũng có thể hiển thị filter predicate.

Ngược lại, plan có node FILTER có thể chứa điều kiện phức tạp hoặc subquery, không chỉ một phép so sánh cột đơn giản.

### 2.3. Access predicate và filter predicate

Trong Predicate Information, thường gặp hai nhãn:

- **access(...):** điều kiện dùng để xác định phạm vi truy cập của operation, ví dụ khóa index hoặc partition key.
- **filter(...):** điều kiện dùng để loại hàng sau hoặc trong quá trình operation tạo row source.

Ví dụ truy vấn theo khóa nhân viên và lọc lương:

~~~sql
SELECT employee_id, salary
FROM   employees
WHERE  employee_id = :p_employee_id
AND    salary >= :p_min_salary;
~~~

Nếu có index phù hợp trên EMPLOYEE_ID, plan có thể dùng EMPLOYEE_ID làm access predicate, còn SALARY là filter predicate sau khi lấy hàng từ index/table.

Không phải mọi filter predicate đều là vấn đề. Nếu chỉ một hàng được truy cập bằng index, kiểm tra thêm một điều kiện salary thường rất rẻ. Cần xem số hàng và chi phí thực tế trước khi kết luận.

### 2.4. FILTER với EXISTS và NOT EXISTS

Ví dụ tìm khách hàng có ít nhất một đơn hàng đang mở:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM   customers c
WHERE  EXISTS (
    SELECT 1
    FROM   orders o
    WHERE  o.customer_id = c.customer_id
    AND    o.status = 'OPEN'
);
~~~

Oracle có thể unnest subquery và chuyển thành SEMI JOIN, hoặc chọn một dạng kế hoạch có FILTER tùy cấu trúc và ước lượng. Không phải mọi EXISTS đều tạo node FILTER.

Với NOT EXISTS, optimizer có thể dùng ANTI JOIN hoặc dạng kế hoạch khác. Hãy đọc operation thực tế thay vì suy ra từ cú pháp SQL.

### 2.5. FILTER và subquery tương quan

Một FILTER có thể đánh giá điều kiện phụ thuộc hàng hiện tại từ row source phía dưới. Trong một số kế hoạch, subquery có thể được bắt đầu lặp lại theo từng hàng đầu vào.

Dấu hiệu cần chú ý:
- Starts của nhánh con lớn.
- Số hàng ở row source cha lớn.
- Subquery có truy cập bảng hoặc index lặp lại.
- Predicate có tương quan với cột của hàng cha.

Starts cao không tự động là lỗi. Nếu mỗi lần chỉ kiểm tra một index lookup rất rẻ, kế hoạch có thể tốt. Nếu subquery lặp lại nhiều lần và mỗi lần quét nhiều hàng, cần xem xét index, unnesting, join hoặc cách viết truy vấn.

### 2.6. FILTER không thay thế constraint

Nếu điều kiện là quy tắc toàn vẹn dữ liệu như salary không âm, nên ưu tiên CHECK constraint. FILTER chỉ là bước xử lý khi truy vấn; nó không ngăn dữ liệu sai được ghi vào bảng.

## 3. SORT — sắp xếp và các operation liên quan

### 3.1. SORT ORDER BY

SORT ORDER BY sắp xếp row source theo khóa ORDER BY:

~~~sql
SELECT employee_id,
       last_name,
       salary
FROM   employees
ORDER  BY salary DESC, employee_id;
~~~

Oracle cần bảo đảm thứ tự kết quả theo yêu cầu SQL. Nếu access path đã cung cấp đúng thứ tự, optimizer có thể không cần SORT ORDER BY. Ví dụ một index có thể hỗ trợ truy vấn theo thứ tự khóa phù hợp.

Không nên tạo index chỉ để loại một SORT mà chưa đánh giá:
- Index có được dùng cho các truy vấn khác không?
- Có làm DML chậm hơn hoặc tăng dung lượng không?
- Thứ tự ASC/DESC và các cột leading có phù hợp không?
- Filter và selectivity có làm index path hiệu quả không?

### 3.2. ORDER BY ở ngoài và trong aggregate

ORDER BY ở cuối SELECT quy định thứ tự hàng trả về cho client. Với aggregate như JSON_ARRAYAGG, LISTAGG hoặc một số hàm khác, thứ tự phần tử bên trong aggregate phải được khai báo trong chính lời gọi aggregate theo cú pháp hỗ trợ.

SORT ORDER BY trong plan có thể phục vụ thứ tự kết quả cuối; nó không nhất thiết là sort nội bộ của mọi aggregate.

### 3.3. SORT UNIQUE

SORT UNIQUE có thể được dùng để loại bỏ các hàng trùng theo một tập cột:

~~~sql
SELECT DISTINCT department_id
FROM   employees;
~~~

Oracle có thể chọn SORT UNIQUE hoặc HASH UNIQUE tùy kế hoạch. SORT UNIQUE sắp xếp các hàng theo khóa cần xét rồi loại các hàng trùng liền kề.

Không phải câu DISTINCT nào cũng tạo SORT UNIQUE; optimizer có thể dùng phương án khác, hoặc uniqueness đã được bảo đảm bởi access path/constraint.

### 3.4. SORT GROUP BY

SORT GROUP BY là phương án gom nhóm dựa trên việc sắp xếp theo các cột GROUP BY. Sau khi các hàng cùng group nằm cạnh nhau, Oracle có thể tính aggregate cho từng nhóm.

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
FROM   employees
GROUP  BY department_id;
~~~

Plan có thể chọn SORT GROUP BY hoặc HASH GROUP BY. Cả hai thực hiện ngữ nghĩa GROUP BY, nhưng cách tổ chức dữ liệu khác nhau.

### 3.5. SORT AGGREGATE

SORT AGGREGATE thường xuất hiện với aggregate không có GROUP BY, ví dụ:

~~~sql
SELECT COUNT(*),
       AVG(salary),
       MAX(salary)
FROM   employees;
~~~

Đầu ra chỉ có một hàng aggregate cho toàn bộ tập đầu vào (với COUNT luôn trả một hàng; các aggregate khác có thể là NULL khi không có hàng). Tên SORT AGGREGATE không có nghĩa Oracle nhất thiết phải sort toàn bộ hàng như SORT ORDER BY.

### 3.6. SORT ORDER BY STOPKEY và Top-N

Truy vấn lấy N hàng đầu:

~~~sql
SELECT employee_id,
       salary
FROM   employees
ORDER  BY salary DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Optimizer có thể sử dụng operation liên quan STOPKEY hoặc top-N để tránh sắp xếp và giữ toàn bộ tập kết quả nếu không cần. Tên operation cụ thể phụ thuộc phiên bản và hình dạng plan.

Nếu ORDER BY có ties ở ranh giới, hãy thêm khóa phụ để kết quả top-N xác định:

~~~sql
ORDER BY salary DESC, employee_id
FETCH FIRST 10 ROWS ONLY
~~~

Nếu không có thứ tự xác định, hàng nào được chọn ở ranh giới có thể thay đổi giữa các lần chạy.

### 3.7. SORT JOIN

SORT JOIN có thể xuất hiện khi Oracle cần sắp xếp đầu vào để thực hiện một kiểu join, ví dụ sort merge join. Đừng nhầm nó với SORT ORDER BY trả kết quả theo yêu cầu của client.

Sort merge join cần hai đầu vào được sắp theo join key. Oracle có thể dùng index cung cấp thứ tự hoặc thực hiện sort riêng.

## 4. SORT sử dụng PGA và TEMP như thế nào?

### 4.1. Workarea

Các operation như sort, hash join và hash aggregation cần vùng nhớ làm việc (workarea). Trong cấu hình thông thường, Oracle quản lý workarea trong PGA theo chính sách bộ nhớ tự động.

Nếu workarea đủ lớn, operation có thể xử lý trong bộ nhớ. Nếu không đủ, Oracle có thể ghi một phần dữ liệu ra temporary tablespace và đọc lại khi cần.

### 4.2. Optimal, one-pass và multi-pass

Có thể hiểu khái quát ba trạng thái:

- **Optimal:** toàn bộ operation hoàn tất trong vùng nhớ làm việc, không cần spill dữ liệu sort/hash ra TEMP.
- **One-pass:** cần dùng TEMP nhưng có thể xử lý với một lượt ghi/đọc phân vùng trung gian theo chiến lược operation.
- **Multi-pass:** phải xử lý qua nhiều lượt vì vùng nhớ không đủ; thường có chi phí I/O lớn hơn.

Đây là khái niệm workarea. Chi tiết triển khai phụ thuộc loại operation và phiên bản Oracle.

### 4.3. Dấu hiệu spill

Khi sort hoặc hash aggregation dùng TEMP, có thể thấy:
- Cột TempSpc trong plan hoặc thông tin memory của DBMS_XPLAN.
- Logical/physical reads hoặc writes tăng.
- V$SQL_WORKAREA cho biết operation có thể thực thi optimal/one-pass/multi-pass.
- V$TEMPSEG_USAGE cho biết session đang dùng temporary segment.

TEMP usage không tự động là lỗi. Một sort lớn có thể cần TEMP hợp lý. Vấn đề là spill quá nhiều, kéo dài hoặc xảy ra trên workload nhạy latency.

### 4.4. PGA không phải TEMP

PGA là vùng nhớ riêng của process/session theo mô hình Oracle; temporary tablespace là nơi lưu dữ liệu tạm trên storage khi operation cần spill hoặc khi ứng dụng tạo temporary segment. Tăng TEMP không làm sort trong bộ nhớ lớn hơn. Điều chỉnh PGA/workarea và TEMP giải quyết hai khía cạnh liên quan nhưng khác nhau.

### 4.5. Không tăng PGA chỉ dựa trên một plan

Trước khi điều chỉnh memory:
1. Xác định SQL và operation nào dùng workarea.
2. Kiểm tra số hàng thực tế và kích thước hàng.
3. Kiểm tra concurrent sessions.
4. Kiểm tra trạng thái workarea và TEMP.
5. Xác định SQL có đang xử lý quá nhiều hàng không.
6. Đánh giá khả năng giảm dữ liệu đầu vào hoặc tận dụng thứ tự từ index.
7. Đo lại dưới concurrency tương đương production.

Tăng PGA có thể giúp một số operation nhưng cũng ảnh hưởng tổng bộ nhớ của instance khi nhiều session chạy đồng thời.

## 5. HASH GROUP BY — gom nhóm bằng hash table

### 5.1. Cách hoạt động

HASH GROUP BY gom các hàng có cùng giá trị GROUP BY key vào cùng một nhóm bằng cấu trúc băm. Oracle đọc đầu vào, tính hash từ khóa nhóm, cập nhật aggregate state của nhóm rồi phát kết quả.

Ví dụ:

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       SUM(salary) AS total_salary
FROM   employees
GROUP  BY department_id;
~~~

Một kế hoạch có thể chứa:

~~~text
HASH GROUP BY
  TABLE ACCESS FULL EMPLOYEES
~~~

Oracle không cần sắp xếp toàn bộ hàng theo department_id chỉ để xác định các nhóm.

### 5.2. Khi nào optimizer có thể chọn HASH GROUP BY?

Hash aggregation thường hấp dẫn khi:
- Cần gom nhiều hàng thành số lượng group tương đối nhỏ.
- Input không sẵn thứ tự theo group key.
- Workarea có khả năng chứa hash table.
- Cost estimate cho hash aggregation thấp hơn sort-based alternative.

Optimizer lựa chọn dựa trên cost và điều kiện thực tế. Không có quy tắc đơn giản rằng bảng lớn luôn dùng HASH GROUP BY hoặc bảng nhỏ luôn dùng SORT GROUP BY.

### 5.3. Kết quả không có thứ tự bảo đảm

HASH GROUP BY không đảm bảo các group được trả theo thứ tự khóa. SQL không bảo đảm thứ tự nếu không có ORDER BY.

Nếu cần kết quả theo department_id:

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count
FROM   employees
GROUP  BY department_id
ORDER  BY department_id;
~~~

Optimizer có thể phải thêm SORT ORDER BY sau HASH GROUP BY, hoặc chọn một kế hoạch khác có thứ tự phù hợp. Đừng dựa vào thứ tự tình cờ quan sát được.

### 5.4. Hash table và số lượng group

Chi phí hash aggregation phụ thuộc:
- Số hàng đầu vào.
- Số lượng group khác nhau (NDV).
- Kích thước group key.
- Số lượng và kiểu aggregate state.
- Kích thước workarea.
- Mức độ phân bố dữ liệu và khả năng spill.

Nếu số group gần bằng số hàng, hash table có thể lớn. Nếu chỉ có vài group, hash aggregation có thể gọn hơn dù input rất lớn.

### 5.5. Spill của HASH GROUP BY

Nếu hash table không vừa workarea, Oracle có thể partition dữ liệu và sử dụng TEMP để hoàn tất aggregation. Điều này làm tăng I/O và thời gian.

Khi thấy HASH GROUP BY chậm:
- So sánh E-Rows và A-Rows ở đầu vào.
- Kiểm tra số group thực tế.
- Xem workarea memory và TempSpc.
- Xem predicate có thể giảm input trước aggregation không.
- Kiểm tra thống kê bảng/cột và histogram khi phù hợp.
- Đánh giá việc aggregate sớm hay muộn trong join plan.

Không cố ép HASH GROUP BY bằng hint trước khi hiểu nguyên nhân của kế hoạch hiện tại.

### 5.6. HASH GROUP BY và SORT GROUP BY

| Tiêu chí | HASH GROUP BY | SORT GROUP BY |
| --- | --- | --- |
| Cách gom nhóm | Hash table theo group key | Sort theo group key rồi gom hàng kề nhau |
| Cần input có thứ tự? | Không | Tự sắp xếp hoặc tận dụng thứ tự có sẵn |
| Bộ nhớ | Hash table/workarea | Sort workarea |
| Có thể spill TEMP? | Có | Có |
| Thứ tự output | Không được bảo đảm | Không nên dựa vào nếu không có ORDER BY |
| Phù hợp | Nhiều hàng, group key không có thứ tự sẵn, hash table phù hợp | Có thứ tự phù hợp hoặc optimizer đánh giá sort-based rẻ hơn |

### 5.7. Aggregate không GROUP BY

Một câu như:

~~~sql
SELECT SUM(salary)
FROM employees;
~~~

không tạo nhiều group theo cột. Plan thường có SORT AGGREGATE hoặc operation aggregate tương ứng, chứ không nhất thiết HASH GROUP BY.

## 6. WINDOW SORT — sắp xếp để tính analytic function

### 6.1. Analytic function giữ lại từng hàng

Analytic function tính giá trị dựa trên một cửa sổ hàng, nhưng thường không gom nhiều hàng thành một hàng như GROUP BY.

Ví dụ:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_avg
FROM   employees;
~~~

Mỗi nhân viên vẫn là một hàng đầu ra. Cột department_avg chứa trung bình lương của phòng ban mà hàng đó thuộc về.

### 6.2. PARTITION BY và ORDER BY

Một analytic clause có thể gồm:
- **PARTITION BY:** chia input thành các partition độc lập.
- **ORDER BY:** quy định thứ tự xử lý hàng trong mỗi partition.
- **Windowing clause:** quy định phạm vi hàng được dùng cho một số analytic aggregate.

Ví dụ:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS salary_rank
FROM   employees;
~~~

Oracle cần tổ chức hàng theo department_id và salary/employee_id để tính ROW_NUMBER. Plan có thể xuất hiện WINDOW SORT.

### 6.3. WINDOW SORT không phải GROUP BY

So sánh:

~~~sql
SELECT department_id,
       AVG(salary)
FROM   employees
GROUP  BY department_id;
~~~

Kết quả có một hàng mỗi phòng ban.

Trong khi:

~~~sql
SELECT employee_id,
       department_id,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_avg
FROM   employees;
~~~

Kết quả giữ một hàng mỗi nhân viên. WINDOW SORT (nếu cần) chuẩn bị thứ tự để tính analytic function, không gom toàn bộ partition thành một hàng.

### 6.4. ROW_NUMBER, RANK và DENSE_RANK

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS row_num,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank,
       DENSE_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS dense_salary_rank
FROM   employees;
~~~

Các hàm có thể dùng chung một thứ tự xử lý nếu partition/order key tương thích. Thêm tie-breaker vào ROW_NUMBER để xác định thứ tự ổn định. RANK và DENSE_RANK thường cố ý giữ cùng hạng cho các hàng có giá trị sort key bằng nhau.

### 6.5. LAG và LEAD

~~~sql
SELECT employee_id,
       hire_date,
       salary,
       LAG(salary) OVER (
           ORDER BY hire_date, employee_id
       ) AS previous_salary,
       LEAD(salary) OVER (
           ORDER BY hire_date, employee_id
       ) AS next_salary
FROM   employees;
~~~

LAG lấy giá trị từ hàng đứng trước, LEAD lấy từ hàng đứng sau theo thứ tự analytic. WINDOW SORT có thể cần để thiết lập thứ tự đó.

### 6.6. Aggregate analytic và window frame

~~~sql
SELECT employee_id,
       department_id,
       hire_date,
       salary,
       SUM(salary) OVER (
           PARTITION BY department_id
           ORDER BY hire_date, employee_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_salary
FROM   employees;
~~~

Window frame xác định những hàng đóng góp vào kết quả cho hàng hiện tại. ROWS mô tả phạm vi theo vị trí hàng sau khi sắp xếp; RANGE mô tả phạm vi theo giá trị sort key và có ngữ nghĩa khác khi có ties.

Khi viết running total, chỉ định frame tường minh giúp tránh nhầm lẫn về hành vi mặc định và xử lý các giá trị ORDER BY trùng nhau.

### 6.7. WINDOW SORT và thứ tự kết quả cuối

ORDER BY bên trong OVER chỉ quy định thứ tự tính analytic function. Nó không tự bảo đảm thứ tự các hàng được trả về cho client.

Nếu muốn kết quả cuối theo department_id và salary, vẫn cần:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM   employees
ORDER  BY department_id, salary DESC, employee_id;
~~~

Optimizer có thể tận dụng cùng thứ tự hoặc phải thực hiện sort bổ sung. Không suy ra thứ tự cuối chỉ từ WINDOW SORT.

### 6.8. WINDOW NOSORT và WINDOW BUFFER

Tùy phiên bản và plan, có thể thấy các operation như WINDOW NOSORT hoặc WINDOW BUFFER:
- WINDOW NOSORT cho biết Oracle có thể xử lý analytic operation mà không cần sort mới vì đầu vào đã có thứ tự phù hợp.
- WINDOW BUFFER có thể xuất hiện khi Oracle cần buffer hàng để tính một số analytic window.

Tên operation và cách xuất hiện phụ thuộc hàm analytic, frame và release. Đọc toàn bộ plan và Predicate/Projection Information thay vì chỉ nhìn một dòng.

### 6.9. Nhiều analytic function

Nếu nhiều analytic function có cùng PARTITION BY và ORDER BY, Oracle có thể chia sẻ thứ tự đã chuẩn bị. Nếu các hàm yêu cầu các thứ tự khác nhau, có thể cần nhiều sort hoặc nhiều bước xử lý.

Khi tối ưu:
- Gom các analytic expression có cùng window specification.
- Chỉ chọn các cột cần thiết.
- Xem có thể tận dụng index/order từ access path hay không.
- Đừng xóa tie-breaker chỉ để hy vọng giảm sort nếu điều đó làm kết quả không xác định.

## 7. So sánh bốn operator

| Operator | Mục tiêu | Có làm giảm số hàng? | Có cần thứ tự? | Có thể dùng TEMP? |
| --- | --- | --- | --- | --- |
| FILTER | Loại hàng không thỏa điều kiện | Thường có | Không nhất thiết | Không phải do bản thân filter; nhánh con vẫn có thể dùng TEMP |
| SORT | Sắp xếp hoặc hỗ trợ distinct/join/group | Có thể, nếu SORT UNIQUE; ORDER BY thường giữ số hàng | Có | Có |
| HASH GROUP BY | Tạo một hàng mỗi group | Có | Không cần sort đầu vào | Có |
| WINDOW SORT | Chuẩn bị thứ tự để tính analytic | Thường giữ số hàng | Có, theo partition/order key | Có |

Các operator có thể cùng xuất hiện trong một plan. Ví dụ Oracle có thể FILTER trước, HASH GROUP BY sau, rồi SORT ORDER BY để trả kết quả theo thứ tự người dùng yêu cầu.

## 8. Ví dụ đọc plan theo từng dạng truy vấn

### 8.1. Lọc rồi sắp xếp

~~~sql
SELECT employee_id,
       department_id,
       salary
FROM   employees
WHERE  department_id = 10
AND    salary >= 3000
ORDER  BY salary DESC, employee_id;
~~~

Một plan có thể có:
- INDEX RANGE SCAN để tìm department_id.
- TABLE ACCESS BY INDEX ROWID để lấy cột còn lại.
- FILTER cho điều kiện salary nếu không xử lý ngay trong access.
- SORT ORDER BY để sắp kết quả.

Đây chỉ là hình dạng có thể xảy ra. Nếu index chứa đủ cột hoặc cung cấp đúng thứ tự, plan có thể khác.

### 8.2. Gom nhóm

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       SUM(salary) AS total_salary
FROM   employees
WHERE  hire_date >= DATE '2023-01-01'
GROUP  BY department_id;
~~~

Oracle có thể lọc input trước, sau đó chọn HASH GROUP BY hoặc SORT GROUP BY. Việc lọc sớm giúp giảm số hàng cần aggregate nếu predicate được áp dụng trước operator đó.

### 8.3. Tính analytic

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM   employees
WHERE  salary IS NOT NULL;
~~~

Plan có thể lọc hàng có salary NULL, rồi thực hiện WINDOW SORT theo partition/order key, sau đó tính ROW_NUMBER.

### 8.4. Top-N theo nhóm

~~~sql
SELECT employee_id,
       department_id,
       salary
FROM (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

Đây là mẫu lấy ba nhân viên lương cao nhất trong mỗi phòng ban. Plan có thể chứa WINDOW SORT, operation rank được đẩy hoặc tối ưu hóa khác, FILTER/VIEW để giữ rn <= 3 và sort cuối cho output. Tên operation cụ thể tùy optimizer.

### 8.5. EXISTS và FILTER

~~~sql
SELECT c.customer_id
FROM   customers c
WHERE  EXISTS (
    SELECT 1
    FROM   orders o
    WHERE  o.customer_id = c.customer_id
    AND    o.order_date >= DATE '2025-01-01'
);
~~~

Optimizer có thể chọn nested loops semi join, hash semi join hoặc FILTER/subquery. Kiểm tra plan thực tế để xem nhánh orders được chạy bao nhiêu lần và có index trên customer_id/order_date phù hợp không.

## 9. Hiển thị execution plan

### 9.1. EXPLAIN PLAN

Có thể yêu cầu Oracle tạo plan ước lượng:

~~~sql
EXPLAIN PLAN FOR
SELECT department_id,
       COUNT(*)
FROM   employees
GROUP  BY department_id;

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN không thực thi câu SQL. Nó lưu một kế hoạch được optimizer ước lượng trong PLAN_TABLE. Kế hoạch này có thể khác cursor thực sự được chạy do bind variables, session settings, adaptive behavior hoặc môi trường khác.

### 9.2. Xem cursor đã thực thi

Để xem plan của cursor trong shared SQL area:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       department_id,
       COUNT(*) AS employee_count
FROM   employees
GROUP  BY department_id;
~~~

Sau khi fetch hết kết quả, chạy trong cùng session:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +MEMSTATS'
    )
);
~~~

GATHER_PLAN_STATISTICS yêu cầu thu thập thống kê row source cho câu lệnh. ALLSTATS LAST hiển thị thống kê của lần thực thi gần nhất cho cursor được chọn. Nếu câu lệnh chưa được fetch hết, số liệu có thể chưa phản ánh toàn bộ công việc.

### 9.3. Các format option hữu ích

- **BASIC:** thông tin plan cơ bản.
- **TYPICAL:** thông tin thường dùng.
- **ALL:** thêm nhiều cột plan.
- **ALLSTATS LAST:** số liệu runtime của lần thực thi cuối khi có thu thập thống kê.
- **+PREDICATE:** hiển thị access/filter predicate.
- **+ALIAS:** hiển thị alias/object alias.
- **+PEEKED_BINDS:** hiển thị bind values được peek nếu có và quyền cho phép.
- **+MEMSTATS:** thông tin memory/workarea ở các operation phù hợp.
- **+IOSTATS:** thống kê I/O ở các operation phù hợp.

Cú pháp và dữ liệu được hiển thị phụ thuộc quyền, loại cursor và phiên bản. Không phải mọi plan đều có mọi cột thống kê.

### 9.4. Tìm SQL_ID và child cursor

Nếu cần xem một cursor cụ thể, có thể lấy SQL_ID/child number từ V$SQL hoặc công cụ quản trị:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       plan_hash_value,
       sql_text
FROM   v$sql
WHERE  sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%';
~~~

Sau đó:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'sql_id_here',
        0,
        'ALLSTATS LAST +PREDICATE +MEMSTATS'
    )
);
~~~

Ví dụ dùng child number 0 để minh họa. Một SQL_ID có thể có nhiều child cursor; chọn đúng child đã thực thi và đúng bind/environment cần điều tra.

### 9.5. Quyền truy cập

DBMS_XPLAN.DISPLAY_CURSOR và các view V$ có thể cần quyền đọc dictionary hoặc quyền được DBA cấp. Không cấp quyền rộng chỉ để chạy ví dụ. Có thể dùng quyền catalog phù hợp hoặc DBA hỗ trợ trong môi trường học tập.

## 10. Đọc các cột runtime statistics

### 10.1. E-Rows và A-Rows

- **E-Rows:** số hàng optimizer ước lượng operation sẽ trả.
- **A-Rows:** số hàng thực tế operation đã trả trong lần chạy có thu thập thống kê.

Nếu E-Rows lệch lớn so với A-Rows, optimizer có thể chọn join method, access path, memory hoặc thứ tự xử lý không phù hợp.

Không phải mọi chênh lệch đều nghiêm trọng. Cần xem vị trí chênh lệch đầu tiên trong cây và tác động tới các operator phía trên.

### 10.2. Starts

Starts là số lần operation được bắt đầu. Nó hữu ích khi một nhánh con được chạy lặp lại, ví dụ inner side của nested loops hoặc subquery FILTER tương quan.

Nếu một operation có Starts rất cao, hãy kiểm tra:
- Hàng đầu vào của parent.
- Predicate tương quan.
- Chi phí mỗi lần chạy.
- Index/access path của nhánh con.
- Khả năng unnest hoặc chuyển đổi truy vấn.

### 10.3. A-Time và Buffers

A-Time thể hiện thời gian thực thi được ghi nhận ở row source. Một số giá trị có thể mang tính tích lũy theo cây; không cộng tất cả A-Time của các node để suy ra tổng thời gian SQL.

Buffers thường phản ánh consistent gets/logical reads ở operation. Physical Reads cho biết I/O đọc từ storage được ghi nhận. So sánh giữa các operation để tìm phần tiêu tốn nhiều công việc.

### 10.4. TempSpc và memory

Nếu plan hiển thị TempSpc hoặc thông tin memory:
- Xác định operator nào spill.
- Xem lượng dữ liệu và số group.
- Kiểm tra workarea optimal/one-pass/multi-pass.
- So sánh giữa các lần chạy và concurrency.

Không phải mọi sort/hash operation đều spill. Không có TempSpc trong một bản plan cũng không chứng minh mọi lần chạy đều không dùng TEMP; cần đúng runtime statistics và đúng cursor.

### 10.5. A-Rows không nhất thiết là số hàng cuối cùng của SQL

A-Rows tại mỗi node là số hàng row source đó trả ra. FILTER có thể giảm hàng; GROUP BY giảm thành số group; WINDOW SORT thường giữ số hàng; SORT ORDER BY thường giữ số hàng nhưng thay đổi thứ tự. Đọc A-Rows theo từng node giúp thấy lượng dữ liệu thay đổi qua pipeline.

## 11. Chẩn đoán từng operator

### 11.1. FILTER có Starts cao

Nếu nhánh FILTER gọi subquery lặp lại:
1. Xác định parent cung cấp bao nhiêu hàng.
2. Xem Starts của nhánh subquery.
3. Kiểm tra access predicate trong nhánh con.
4. Xem index có phù hợp với correlation key và filter không.
5. Xem optimizer có thể unnest subquery hoặc chọn semi/anti join không.
6. Kiểm tra E-Rows/A-Rows và statistics.

Không rewrite EXISTS thành JOIN một cách máy móc; JOIN có thể nhân bản hàng nếu quan hệ một-nhiều và thay đổi ngữ nghĩa.

### 11.2. SORT ORDER BY lớn

Nếu sort tiêu thụ nhiều memory/TEMP:
- Xác nhận ứng dụng có thật sự cần ORDER BY không.
- Giảm số hàng trước sort bằng predicate đúng ngữ nghĩa.
- Chỉ chọn cột cần trả về thay vì SELECT *.
- Xem index có thể cung cấp thứ tự hữu ích không.
- Với Top-N, dùng FETCH FIRST/ROWNUM theo đúng yêu cầu và kiểm tra plan.
- Kiểm tra kích thước hàng, số hàng và concurrency.

Không bỏ ORDER BY nếu client phụ thuộc thứ tự kết quả.

### 11.3. HASH GROUP BY spill

Nếu HASH GROUP BY dùng nhiều TEMP:
- Kiểm tra số group khác nhau.
- Xác minh statistics trên group key.
- Giảm input trước aggregate nếu điều kiện cho phép.
- Kiểm tra join có làm nhân bản hàng trước group không.
- Xem có cần tất cả group/aggregate không.
- Đo workarea và concurrency.

Không thêm index chỉ vì thấy HASH GROUP BY. Index có thể giúp access path hoặc cung cấp thứ tự, nhưng không tự động làm hash aggregation rẻ hơn.

### 11.4. WINDOW SORT tốn kém

Nếu analytic query cần sort lớn:
- Kiểm tra partition key và order key.
- Chỉ giữ các cột cần thiết ở input.
- Kiểm tra có nhiều analytic window khác nhau cần nhiều sort không.
- Dùng cùng window specification khi nghiệp vụ cho phép.
- Đánh giá index/order từ access path.
- Xác định frame có thể làm tăng nhu cầu buffer không.
- Kiểm tra final ORDER BY có tạo sort thứ hai không.

Không bỏ PARTITION BY hoặc tie-breaker nếu điều đó làm thay đổi kết quả nghiệp vụ.

## 12. Thống kê và cardinality

### 12.1. Vì sao thống kê ảnh hưởng operator?

Optimizer ước lượng số hàng và chi phí của từng row source. Ước lượng này ảnh hưởng:
- Có dùng FILTER hay unnest subquery.
- Có dùng index hay full table scan.
- Có chọn SORT GROUP BY hay HASH GROUP BY.
- Có thể chọn thứ tự join nào.
- Kích thước workarea dự kiến và lượng dữ liệu cần xử lý.

### 12.2. Kiểm tra thống kê

Có thể xem thời điểm và trạng thái thống kê:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM   user_tab_statistics
WHERE  table_name IN ('EMPLOYEES', 'ORDERS');
~~~

Cột và quyền hiển thị tùy view. Dữ liệu NUM_ROWS là số liệu thống kê, không phải COUNT(*) trực tiếp tại thời điểm truy vấn.

### 12.3. Thu thập thống kê

Trong schema thử nghiệm, DBA hoặc chủ schema có thể thu thập thống kê bằng DBMS_STATS:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'JSON_DEMO_EMP',
        cascade => TRUE
    );
END;
/
~~~

Đây chỉ là ví dụ với bảng demo. Trên production, dùng quy trình thống kê được quản trị, đánh giá histogram, incremental stats và lịch thu thập; không chạy gather toàn schema tùy tiện trong giờ cao điểm.

### 12.4. Histogram và skew

Nếu dữ liệu lệch mạnh, ví dụ một status chiếm 99% hàng còn một status chỉ chiếm 1%, thống kê cơ bản có thể không đủ mô tả selectivity. Histogram có thể giúp optimizer ước lượng predicate tốt hơn trong trường hợp phù hợp.

Không tạo histogram cho mọi cột. Bind peeking, adaptive cursor sharing và cách ứng dụng bind giá trị cũng ảnh hưởng kế hoạch.

## 13. Phân biệt operation với cú pháp SQL

| Cú pháp SQL | Operation có thể thấy | Ghi chú |
| --- | --- | --- |
| WHERE | FILTER hoặc predicate tại access path | Không phải WHERE nào cũng có node FILTER |
| ORDER BY | SORT ORDER BY | Có thể được loại nếu input đã có thứ tự phù hợp |
| DISTINCT | SORT UNIQUE hoặc HASH UNIQUE | Phụ thuộc cost và access path |
| GROUP BY | HASH GROUP BY hoặc SORT GROUP BY | Cả hai đều thực hiện grouping |
| COUNT/SUM không GROUP BY | SORT AGGREGATE hoặc aggregate operation khác | Một nhóm tổng thể |
| ROW_NUMBER/RANK/LAG/LEAD OVER | WINDOW SORT hoặc WINDOW NOSORT | Chuẩn bị dữ liệu cho analytic calculation |
| EXISTS/NOT EXISTS | SEMI/ANTI JOIN hoặc FILTER | Optimizer có thể unnest subquery |
| FETCH FIRST N ROWS | STOPKEY/top-N operation hoặc sort | Hình dạng plan tùy truy vấn và phiên bản |

Không suy ra operation chỉ từ một từ khóa SQL. Hãy xem plan của chính cursor được thực thi.

## 14. Hướng dẫn thực hành đọc plan

### 14.1. Chạy truy vấn có filter và sort

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       department_id,
       salary
FROM   employees
WHERE  salary >= 3000
ORDER  BY salary DESC, employee_id;
~~~

Fetch toàn bộ kết quả, sau đó gọi DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST và PREDICATE. Xác định:
- Access path đọc EMPLOYEES.
- Predicate salary được áp dụng ở đâu.
- Có SORT ORDER BY hay không.
- E-Rows/A-Rows khác nhau bao nhiêu.

### 14.2. Chạy GROUP BY

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       department_id,
       COUNT(*) AS employee_count,
       SUM(salary) AS total_salary
FROM   employees
WHERE  salary IS NOT NULL
GROUP  BY department_id;
~~~

Xác định:
- FILTER predicate salary IS NOT NULL nằm ở đâu.
- Operation aggregate là HASH GROUP BY hay SORT GROUP BY.
- Số hàng input so với số group output.
- Có memory/TEMP usage không.

### 14.3. Chạy analytic function

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM   employees;
~~~

Xác định:
- WINDOW SORT hoặc WINDOW NOSORT.
- Partition/order keys.
- Số hàng trước và sau analytic operation.
- Có SORT ORDER BY cuối hay không nếu thêm ORDER BY ngoài truy vấn.

### 14.4. Chạy EXISTS

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM   customers c
WHERE  EXISTS (
    SELECT 1
    FROM   orders o
    WHERE  o.customer_id = c.customer_id
    AND    o.status = 'OPEN'
);
~~~

Xác định optimizer dùng FILTER, NESTED LOOPS SEMI, HASH JOIN SEMI hay operation khác. Nếu có FILTER, xem Starts của nhánh con và access predicate.

### 14.5. Ghi lại kết quả

Với mỗi truy vấn, lưu:
- SQL text và bind values.
- SQL_ID, child number và plan hash value.
- Operation tree.
- E-Rows, A-Rows, Starts.
- Buffers, Reads, A-Time.
- Memory/TEMP nếu có.
- Session settings và trạng thái statistics.

Để so sánh trước/sau, chạy cùng dữ liệu và điều kiện tương đương. Không so sánh một plan estimate với runtime statistics của một cursor khác.

## 15. Những hiểu nhầm thường gặp

**“Có WHERE thì chắc chắn có FILTER operation.”** Không. Predicate có thể được áp dụng ngay tại index/table access hoặc được biến đổi.

**“filter(...) trong Predicate Information có nghĩa có node FILTER.”** Không. Đây là điều kiện predicate, khác operation node.

**“SORT ORDER BY luôn có mặt khi SQL viết ORDER BY.”** Không. Index hoặc row source đã có thứ tự phù hợp có thể loại sort riêng.

**“HASH GROUP BY trả group theo thứ tự hash.”** Không có bảo đảm thứ tự. Chỉ ORDER BY mới quy định thứ tự output.

**“HASH GROUP BY không dùng TEMP.”** Có thể spill khi hash workarea không đủ.

**“SORT AGGREGATE nghĩa là Oracle sort toàn bộ bảng.”** Không. Đây thường là operation aggregate cho một tập kết quả tổng thể.

**“WINDOW SORT gom hàng giống GROUP BY.”** Không. Analytic function thường giữ từng hàng và bổ sung giá trị tính trên cửa sổ.

**“ORDER BY trong OVER đảm bảo output được sắp xếp.”** Không. Nó quy định thứ tự tính analytic; muốn thứ tự cuối cần ORDER BY ở truy vấn ngoài.

**“E-Rows là số hàng thực tế.”** Không. E-Rows là estimate; A-Rows là số hàng thực tế được thu thập.

**“Cost là số giây.”** Không. Cost là thước đo ước lượng tương đối của optimizer.

**“EXPLAIN PLAN luôn giống plan đã chạy.”** Không. Bind, session, adaptive plan và môi trường có thể làm khác.

**“TEMP lớn nghĩa phải tăng TEMP.”** Không nhất thiết. Cần tìm operator spill, số hàng, workarea và khả năng giảm dữ liệu đầu vào.

## 16. Bài thực hành

Dùng schema mẫu hoặc tạo bảng thử có đủ số lượng hàng để thấy khác biệt giữa estimate, actual và workarea.

### Bài 1 — FILTER operation

Tạo truy vấn có predicate trên cột không có index và xem plan. Phân biệt FILTER node với filter predicate trong Predicate Information.

### Bài 2 — Access predicate và filter predicate

Tạo index trên khóa tìm kiếm, thêm một điều kiện trên cột khác. Xác định điều kiện nào được dùng làm access predicate và điều kiện nào là filter.

### Bài 3 — EXISTS

Viết truy vấn EXISTS tương quan. Xem optimizer dùng FILTER hay SEMI JOIN. Ghi nhận Starts của nhánh con nếu có.

### Bài 4 — SORT ORDER BY

Chạy SELECT có ORDER BY. Tạo index phù hợp trong schema test và so sánh plan trước/sau. Đánh giá cả chi phí DML và dung lượng index.

### Bài 5 — DISTINCT

Chạy SELECT DISTINCT và quan sát SORT UNIQUE hoặc HASH UNIQUE. Tăng số lượng hàng trùng và so sánh operation.

### Bài 6 — SORT GROUP BY và HASH GROUP BY

Chạy GROUP BY với dữ liệu đủ lớn. Quan sát operation mà optimizer chọn và xem memory/TEMP nếu có.

### Bài 7 — Aggregate không GROUP BY

Chạy COUNT, SUM, AVG không GROUP BY. Phân biệt operation aggregate với HASH GROUP BY.

### Bài 8 — WINDOW SORT

Dùng ROW_NUMBER theo PARTITION BY/ORDER BY. Xác định sort key và số hàng trước/sau WINDOW SORT.

### Bài 9 — LAG và LEAD

Dùng LAG/LEAD theo ngày. Thêm tie-breaker duy nhất và quan sát kết quả ổn định.

### Bài 10 — Window frame

Tính running total với ROWS UNBOUNDED PRECEDING. Thử dữ liệu có ngày trùng và so sánh với RANGE.

### Bài 11 — Top-N mỗi nhóm

Dùng ROW_NUMBER và FILTER rn <= N để lấy top 3 theo phòng ban. Quan sát operation rank/window trong plan.

### Bài 12 — PGA và TEMP

Dùng dữ liệu lớn hơn để tạo sort/hash workarea đáng kể. Quan sát memory, TempSpc và trạng thái workarea bằng quyền phù hợp.

### Bài 13 — Estimate và actual

Chạy truy vấn với GATHER_PLAN_STATISTICS. So sánh E-Rows/A-Rows và tìm node đầu tiên có sai lệch lớn.

### Bài 14 — Trước và sau tối ưu

Chọn một truy vấn có FILTER lặp lại hoặc SORT lớn. Thử một thay đổi có lý do (index, predicate, query shape hoặc statistics), sau đó đo lại bằng cùng phương pháp.

## 17. Tài liệu Oracle tham khảo

- [Oracle Database SQL Tuning Guide 19c — Generating and Displaying Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html): EXPLAIN PLAN, DBMS_XPLAN và cách hiển thị plan.
- [Oracle Database SQL Tuning Guide 19c — Optimizer Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer, cardinality, cost và execution plan.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): DISPLAY, DISPLAY_CURSOR và format options.
- [Oracle Database Performance Tuning Guide 19c — Managing Memory](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/): PGA, workarea và quản lý bộ nhớ.
- [Oracle Database Reference — V$SQL_WORKAREA](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_WORKAREA.html): thông tin workarea của SQL.
- [Oracle Database SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): PARTITION BY, ORDER BY, windowing clause và ngữ nghĩa analytic.

FILTER, SORT, HASH GROUP BY và WINDOW SORT là các operation khác nhau trong cây row source. FILTER loại hàng theo điều kiện; SORT tổ chức hàng theo thứ tự hoặc hỗ trợ thao tác cần sort; HASH GROUP BY gom hàng bằng hash table; WINDOW SORT chuẩn bị thứ tự cho analytic function mà thường vẫn giữ từng hàng. Khi đọc plan, hãy phân biệt operation với predicate, xem E-Rows/A-Rows/Starts, kiểm tra workarea và TEMP, rồi đối chiếu với SQL cùng runtime statistics. **Chỉ thay đổi index, memory hoặc cấu trúc truy vấn sau khi xác định operator nào thực sự tạo ra chi phí và vì sao.**
