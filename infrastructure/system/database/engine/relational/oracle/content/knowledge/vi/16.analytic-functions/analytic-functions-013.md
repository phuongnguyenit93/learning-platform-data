# Chi phí sắp xếp, kích thước phân vùng và kiểm chứng kết quả

Hàm phân tích (analytic function) giúp tính tổng lũy kế, thứ hạng, giá trị trước/sau, trung bình trượt và nhiều chỉ số theo cửa sổ dữ liệu mà vẫn giữ các hàng chi tiết. Đổi lại, Oracle phải tổ chức các hàng theo nhóm và thứ tự mà biểu thức phân tích yêu cầu. Với tập dữ liệu lớn, bước tổ chức này có thể tiêu tốn CPU, PGA và TEMP tablespace.

Muốn dùng analytic function hiệu quả, cần hiểu ba vấn đề liên quan chặt chẽ:

1. **Chi phí sắp xếp:** khi nào Oracle cần sắp hàng cho PARTITION BY và ORDER BY, khi nào có thể tận dụng thứ tự đã có hoặc dùng chung một lần sắp xếp.
2. **Kích thước phân vùng:** một partition quá lớn, phân bố lệch hoặc có nhiều cửa sổ khác nhau có thể làm tăng bộ nhớ, I/O và thời gian xử lý.
3. **Kiểm chứng kết quả:** một truy vấn chạy nhanh nhưng sai thứ tự, sai window frame, sai cách xử lý ties hoặc NULL vẫn là truy vấn sai.

Bài học sử dụng Oracle Database 19c làm bối cảnh tham chiếu. Tên operation trong execution plan và chi tiết tối ưu có thể thay đổi theo phiên bản, thống kê, cấu hình và hình dạng truy vấn; hãy kiểm tra trên hệ thống thực tế.

## 1. Nhắc lại cách analytic function xử lý dữ liệu

Một hàm phân tích có dạng tổng quát:

~~~sql
analytic_function(expression)
    OVER (
        PARTITION BY partition_expression
        ORDER BY sort_expression
        windowing_clause
    )
~~~

- `PARTITION BY` chia tập hàng thành các nhóm độc lập để tính.
- `ORDER BY` trong `OVER` xác định thứ tự logic của hàng bên trong từng partition.
- Window frame xác định những hàng nào tham gia tính cho hàng hiện tại, nếu hàm hỗ trợ frame.
- Kết quả analytic thường được gắn vào từng hàng nguồn; nó không tự gộp các hàng như `GROUP BY`.

Ví dụ tổng doanh thu lũy kế theo từng khách hàng:

~~~sql
SELECT customer_id,
       transaction_date,
       transaction_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions;
~~~

Oracle cần xử lý các hàng theo khách hàng và thứ tự ngày/mã giao dịch để tính đúng tổng lũy kế. Nếu nguồn có hàng triệu giao dịch, bước tổ chức thứ tự có thể là phần đáng kể của chi phí truy vấn.

### 1.1 Analytic ORDER BY không phải ORDER BY cuối truy vấn

Hai phần này có nhiệm vụ khác nhau:

~~~sql
SELECT customer_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date
       ) AS running_amount
FROM sales_transactions
ORDER BY amount DESC;
~~~

`ORDER BY transaction_date` trong `OVER` quyết định thứ tự tính tổng trong từng khách hàng. `ORDER BY amount DESC` ở cuối câu SQL quyết định thứ tự hiển thị các hàng sau khi tính xong.

Một truy vấn không có `ORDER BY` cuối cùng không bảo đảm thứ tự hàng trả về, ngay cả khi analytic function có `ORDER BY` bên trong `OVER`.

### 1.2 Analytic function thường không làm giảm số hàng

~~~sql
SELECT employee_id,
       department_id,
       salary,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_average
FROM employees;
~~~

Mỗi nhân viên vẫn có một hàng kết quả; cột `DEPARTMENT_AVERAGE` được tính trên các nhân viên cùng phòng ban. Đây là khác biệt quan trọng với:

~~~sql
SELECT department_id,
       AVG(salary) AS department_average
FROM employees
GROUP BY department_id;
~~~

Truy vấn `GROUP BY` chỉ trả một hàng cho mỗi phòng ban. Kích thước đầu vào cho analytic phụ thuộc vào tập hàng còn lại sau các bước lọc/nhóm trước đó, chứ không phải số hàng của kết quả hiển thị cuối cùng.

## 2. Vì sao analytic function có thể cần sắp xếp?

Hãy xét:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
)
~~~

Để đánh số nhân viên theo lương trong từng phòng ban, Oracle cần biết:

1. Hàng thuộc partition nào.
2. Thứ tự các hàng trong partition.
3. Hàng nào đứng trước/sau khi gán số.

Nếu access path không cung cấp thứ tự phù hợp, Oracle thường phải tổ chức lại hàng bằng một bước sort hoặc operation tương đương.

~~~mermaid
flowchart TD
    A["Nguồn hàng sau FROM / WHERE / GROUP BY"] --> B["Phân chia theo PARTITION BY"]
    B --> C["Tổ chức thứ tự theo analytic ORDER BY"]
    C --> D["Áp dụng hàm và window frame"]
    D --> E["Gắn kết quả analytic vào hàng"]
    E --> F["ORDER BY cuối truy vấn (nếu có)"]
~~~

Không phải mọi analytic function đều cần một sort độc lập. Hàm chỉ dùng `PARTITION BY` mà không có `ORDER BY` có thể được xử lý khác hàm cần thứ tự; Oracle cũng có thể tận dụng access path hoặc thứ tự đã có. Khi truy vấn yêu cầu một thứ tự cụ thể, cần có bằng chứng trong execution plan để biết Oracle đã đáp ứng thứ tự đó như thế nào.

### 2.1 Chi phí sort không chỉ là so sánh khóa

Sort trên tập lớn có thể bao gồm:

- Đọc các hàng đầu vào.
- Tính các biểu thức dùng làm khóa sắp xếp.
- Giữ các hàng hoặc thông tin cần thiết trong work area.
- So sánh và sắp xếp các khóa.
- Ghi/đọc dữ liệu trung gian nếu bộ nhớ không đủ.
- Chuyển kết quả đã sắp xếp cho operation analytic tiếp theo.

Chi phí tăng theo số hàng, kích thước hàng, độ dài khóa, số thứ tự khác nhau và điều kiện tài nguyên tại thời điểm chạy. Không thể đánh giá chỉ bằng số cột trong `ORDER BY`.

### 2.2 Một truy vấn có thể có nhiều sort

~~~sql
SELECT employee_id,
       department_id,
       hire_date,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY hire_date, employee_id
       ) AS hire_sequence,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank
FROM employees;
~~~

Hai analytic expression yêu cầu hai thứ tự khác nhau. Oracle có thể cần nhiều bước tổ chức thứ tự hoặc một chiến lược xử lý trung gian. Đừng giả định chỉ vì chúng cùng dùng `PARTITION BY department_id` nên chắc chắn chỉ có một sort.

## 3. Đọc operation liên quan trong execution plan

Khi kiểm tra truy vấn analytic, một số operation có thể xuất hiện:

| Operation thường gặp | Ý nghĩa khái quát |
|---|---|
| `WINDOW SORT` | Tổ chức hàng theo thứ tự cần thiết cho analytic operation |
| `WINDOW BUFFER` | Giữ/đệm hàng phục vụ xử lý cửa sổ trong một số kế hoạch |
| `WINDOW NOSORT` | Optimizer có thể xử lý cửa sổ mà không cần một sort riêng ở bước đó |
| `SORT ORDER BY` | Sắp xếp kết quả theo ORDER BY cuối truy vấn |
| `SORT GROUP BY` | Sắp xếp/phân nhóm cho phép tổng hợp, tùy plan |
| `TABLE ACCESS FULL` | Đọc toàn bộ bảng; không tự chứng minh truy vấn kém hiệu quả |
| `INDEX RANGE SCAN` | Đọc các mục index trong một phạm vi |

Tên operation và cách bố trí có thể khác theo release, loại analytic function và plan. Một operation `WINDOW SORT` không tự động có nghĩa truy vấn sai hoặc cần tạo index; cần xét số hàng, số byte, thời gian, TEMP và các bước liền kề.

### 3.1 Lấy execution plan dự kiến

~~~sql
EXPLAIN PLAN FOR
SELECT customer_id,
       transaction_date,
       transaction_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` cho biết kế hoạch mà Oracle ghi nhận cho câu lệnh trong điều kiện explain hiện tại. Nó không phải số đo runtime của lần chạy thực tế; cardinality và lựa chọn plan có thể thay đổi theo bind values, statistics, adaptive behavior và môi trường.

### 3.2 Xem plan thực tế sau khi chạy

Trong môi trường kiểm thử, có thể yêu cầu thu thập thống kê thực thi:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       transaction_date,
       transaction_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01';
~~~

Sau khi câu lệnh đã chạy trong cùng session:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +MEMSTATS +PREDICATE'
    )
);
~~~

Các tùy chọn hiển thị có thể khác theo phiên bản. Nếu không có quyền xem cursor hoặc thống kê chưa được thu thập, kết quả có thể thiếu các cột runtime. Hãy dùng quyền và công cụ được DBA cho phép.

### 3.3 So sánh E-Rows và A-Rows

Trong plan thực tế:

- `E-Rows` là số hàng optimizer ước lượng.
- `A-Rows` là số hàng thực tế operation xử lý/đưa ra theo thống kê được thu thập.
- Chênh lệch lớn giữa hai số có thể khiến optimizer chọn join order, access path hoặc work area không phù hợp.

Ví dụ, optimizer ước lượng một partition chỉ có vài trăm hàng nhưng thực tế một khách hàng có hàng triệu giao dịch. Sort và window processing có thể tốn nhiều tài nguyên hơn dự đoán.

Không chỉ nhìn tổng số hàng cuối. Hãy xác định operation nào nhận nhiều hàng nhất trước `WINDOW SORT`, và hàng có bị nhân lên ở JOIN trước analytic hay không.

## 4. PGA, work area và TEMP tablespace

Sort và một số operation xử lý dữ liệu lớn sử dụng **work area** trong PGA của tiến trình Oracle. Nếu work area đủ lớn, operation có thể hoàn thành chủ yếu trong bộ nhớ. Nếu không đủ, Oracle có thể ghi dữ liệu trung gian ra TEMP tablespace rồi đọc lại theo từng lượt.

Các khái niệm:

- **PGA:** vùng bộ nhớ riêng của tiến trình/server process, dùng cho sort, hash join và các operation tương tự.
- **Work area:** vùng làm việc phục vụ một operation cụ thể, chẳng hạn sort.
- **TEMP tablespace:** nơi lưu các temporary segment khi operation cần spill ra đĩa.
- **One-pass/multipass:** cách operation xử lý dữ liệu khi không thể giữ toàn bộ trong work area; nhiều lượt đọc/ghi có thể làm tăng thời gian.

~~~mermaid
flowchart TD
    A["WINDOW SORT cần xử lý hàng"] --> B{"Work area đủ lớn?"}
    B -->|Có| C["Xử lý chủ yếu trong PGA"]
    B -->|Không| D["Spill dữ liệu trung gian ra TEMP"]
    D --> E["Đọc/ghi các run hoặc partition trung gian"]
    C --> F["Chuyển hàng sang analytic evaluation"]
    E --> F
~~~

### 4.1 Vì sao TEMP tăng?

Một truy vấn analytic có thể dùng TEMP nhiều khi:

- Tập hàng đầu vào rất lớn.
- Các hàng mang nhiều cột rộng không cần thiết trong bước sort.
- Một partition rất lớn hoặc có skew.
- Truy vấn cần nhiều thứ tự analytic không tương thích.
- Nhiều truy vấn đồng thời cạnh tranh PGA/work area.
- Work area được cấp nhỏ so với lượng dữ liệu operation cần xử lý.

TEMP usage không nhất thiết chỉ đến từ analytic function; hash join, sort order by, group by và các operation khác cũng có thể dùng TEMP. Phải xác định đúng operation trong plan và số liệu runtime.

### 4.2 One-pass và multipass

Sort có thể chạy:

- **Optimal:** work area đủ để xử lý theo cách tối ưu trong bộ nhớ.
- **One-pass:** cần ghi dữ liệu trung gian, nhưng có thể hoàn tất với một lượt merge/đọc chính.
- **Multipass:** phải thực hiện nhiều lượt do work area hạn chế so với dữ liệu.

Tên trạng thái và cách thống kê cụ thể phụ thuộc view/phiên bản. Nếu một truy vấn analytic thường xuyên multipass, cần điều tra lượng dữ liệu, kích thước hàng, mức đồng thời và PGA; tăng PGA toàn hệ thống không phải bước đầu tiên.

### 4.3 Quan sát work area và TEMP

DBA hoặc tài khoản có quyền phù hợp có thể kiểm tra work area đang hoạt động:

~~~sql
SELECT sid,
       sql_id,
       operation_type,
       actual_mem_used,
       max_mem_used,
       tempseg_size
FROM v$sql_workarea_active
ORDER BY tempseg_size DESC NULLS LAST;
~~~

View này chỉ phản ánh operation đang hoạt động tại thời điểm truy vấn. Truy vấn ngắn có thể kết thúc trước khi kịp quan sát.

Có thể kiểm tra thông tin work area đã thực hiện:

~~~sql
SELECT sql_id,
       operation_type,
       policy,
       estimated_optimal_size,
       estimated_onepass_size,
       last_memory_used,
       last_execution,
       optimal_executions,
       onepass_executions,
       multipasses_executions
FROM v$sql_workarea
ORDER BY multipasses_executions DESC;
~~~

Tên cột có thể cần điều chỉnh theo release và quyền. Với TEMP segment theo session:

~~~sql
SELECT username,
       sql_id,
       tablespace,
       segtype,
       blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

Các view `V$` là giao diện giám sát hệ thống; ứng dụng thông thường không nên phụ thuộc vào chúng. Không cấp quyền rộng chỉ để người dùng cuối tự đọc thông tin DBA.

### 4.4 Không tự thay đổi tham số PGA/TEMP

Các tham số như `PGA_AGGREGATE_TARGET`, `PGA_AGGREGATE_LIMIT` và cấu hình TEMP ảnh hưởng toàn database/instance hoặc workload chung. Không tăng chúng chỉ vì một truy vấn có `WINDOW SORT`. Cần DBA đánh giá:

- Bộ nhớ vật lý và mức sử dụng đồng thời.
- Work area policy.
- Số truy vấn sort/hash hoạt động cùng lúc.
- TEMP capacity và tốc độ I/O.
- Có thể giảm dữ liệu/độ rộng/số lần sort ở tầng SQL không.

## 5. Kích thước partition trong analytic function

Trong biểu thức:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date
)
~~~

partition là tập các hàng cùng `CUSTOMER_ID`. Đây là **partition logic của analytic function**, không nhất thiết là partition vật lý của bảng Oracle.

### 5.1 Partition nhỏ và cân bằng

Giả sử có 10 triệu giao dịch, phân bố khá đều cho 100.000 khách hàng. Mỗi khách hàng có khoảng 100 giao dịch. Oracle có thể xử lý các nhóm theo thứ tự cần thiết; kích thước tối đa của một nhóm tương đối nhỏ.

### 5.2 Một partition quá lớn

Nếu một khách hàng đặc biệt có 4 triệu giao dịch còn phần lớn khách hàng chỉ có vài chục hàng, partition lớn có thể trở thành điểm nóng:

- Nhiều hàng phải được tổ chức theo thứ tự trong cùng một nhóm.
- Một operation có thể cần work area lớn hoặc spill TEMP.
- Các nhóm nhỏ có thể hoàn tất nhanh trong khi nhóm lớn kéo dài thời gian toàn truy vấn.
- Trong xử lý song song, một nhóm lớn có thể gây skew và mất cân bằng công việc.

Đây là vấn đề **data skew**. Số lượng partition lớn không bảo đảm mỗi partition đều nhỏ; cần xem phân bố kích thước, đặc biệt là MAX, percentile và nhóm lớn nhất.

### 5.3 Kiểm tra phân bố kích thước partition

~~~sql
WITH partition_sizes AS (
    SELECT customer_id,
           COUNT(*) AS row_count
    FROM sales_transactions
    WHERE transaction_date >= DATE '2026-01-01'
    GROUP BY customer_id
)
SELECT COUNT(*) AS partition_count,
       SUM(row_count) AS total_rows,
       MIN(row_count) AS min_rows,
       ROUND(AVG(row_count), 2) AS avg_rows,
       MAX(row_count) AS max_rows
FROM partition_sizes;
~~~

Để xem những partition lớn nhất:

~~~sql
SELECT customer_id,
       COUNT(*) AS row_count
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01'
GROUP BY customer_id
ORDER BY row_count DESC
FETCH FIRST 20 ROWS ONLY;
~~~

`FETCH FIRST` có từ các release Oracle hỗ trợ row limiting clause; với phiên bản cũ hơn, có thể bọc truy vấn bằng `ROWNUM`. Thống kê này chỉ là bước khảo sát dữ liệu, không cho biết trực tiếp kích thước sort trong PGA.

### 5.4 Partition key có ý nghĩa

Chọn partition key theo định nghĩa nghiệp vụ của chỉ số:

- Tổng lũy kế theo khách hàng: `PARTITION BY customer_id`.
- Thứ hạng lương trong phòng ban: `PARTITION BY department_id`.
- Tỷ trọng doanh thu trong khu vực: `PARTITION BY region_id`.

Không thêm một cột tùy ý vào `PARTITION BY` chỉ để làm nhóm nhỏ hơn. Ví dụ:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id, transaction_id
)
~~~

nếu `TRANSACTION_ID` là duy nhất, gần như mỗi partition chỉ có một hàng. Kết quả khi đó không còn là tổng theo khách hàng mà là tổng theo từng giao dịch. Nó có thể giảm kích thước nhóm nhưng đã thay đổi ý nghĩa chỉ số.

## 6. PARTITION BY của analytic khác partitioning của bảng

Hai khái niệm cùng tên nhưng ở hai tầng khác nhau:

| Analytic PARTITION BY | Table partitioning |
|---|---|
| Là một phần của biểu thức `OVER` | Là cách tổ chức lưu trữ vật lý của bảng/index |
| Xác định nhóm hàng dùng để tính một analytic result | Chia segment dữ liệu thành partition/subpartition vật lý |
| Không tạo hoặc thay đổi partition vật lý | Được khai báo khi tạo/alter table hoặc index |
| Có thể dùng biểu thức hợp lệ theo cú pháp analytic | Bị chi phối bởi partition key và chiến lược lưu trữ |
| Có tác động tới logic kết quả | Có thể hỗ trợ pruning, maintenance và một số chiến lược song song |

Ví dụ bảng được partition vật lý theo tháng:

~~~sql
CREATE TABLE sales_transactions (
    transaction_id   NUMBER,
    customer_id      NUMBER,
    transaction_date DATE,
    amount           NUMBER(14,2)
)
PARTITION BY RANGE (transaction_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
~~~

Truy vấn vẫn có thể tính lũy kế theo khách hàng:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Oracle phải bảo đảm thứ tự logic theo khách hàng và ngày, dù bảng được lưu theo partition tháng. Partition pruning có thể giảm số segment cần đọc khi điều kiện ngày phù hợp, nhưng không tự động loại bỏ nhu cầu sắp xếp theo khách hàng/ngày.

### 6.1 Khi physical partitioning có thể giúp

Nếu truy vấn thường lọc theo ngày:

~~~sql
WHERE transaction_date >= DATE '2026-01-01'
  AND transaction_date <  DATE '2026-02-01'
~~~

partition theo tháng có thể cho phép Oracle chỉ đọc partition liên quan (*partition pruning*). Ít hàng đầu vào thường giúp giảm chi phí analytic sau đó.

Nếu physical partition key và analytic partition key tương thích, một số kế hoạch partition-wise/parallel có thể xử lý hiệu quả hơn. Nhưng không được suy luận rằng hai khóa trùng nhau là đủ để bỏ sort; vẫn phải kiểm tra plan thực tế.

### 6.2 Không partition bảng chỉ để sửa WINDOW SORT

Partition vật lý là quyết định thiết kế lưu trữ dài hạn. Nó ảnh hưởng DDL, index, maintenance, backup/recovery, pruning và chiến lược phân phối dữ liệu. Nếu chỉ có một truy vấn analytic chậm, hãy xem:

- Có lọc đúng kỳ dữ liệu trước analytic không?
- Có thể giảm số cột hoặc số hàng đầu vào không?
- Có nhiều analytic order không tương thích không?
- Có partition logic bị skew không?
- Optimizer ước lượng sai không?

Chỉ thiết kế lại partition vật lý khi workload tổng thể và quy mô dữ liệu chứng minh lợi ích.

## 7. Nhiều analytic function và khả năng dùng chung sort

Một câu truy vấn thường cần nhiều chỉ số:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       hire_date,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS salary_position,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_avg
FROM employees;
~~~

Các analytic expression có thể có yêu cầu sort khác nhau:

- `SALARY_POSITION` cần thứ tự lương giảm dần và employee ID để phá hòa.
- `SALARY_RANK` cần thứ tự lương giảm dần nhưng không có employee ID trong thứ tự xếp hạng.
- `DEPARTMENT_AVG` chỉ cần nhóm theo phòng ban, không cần thứ tự hàng.

Oracle có thể chia sẻ hoặc tái sử dụng một phần thứ tự khi các yêu cầu tương thích; nhưng không nên dựa vào quy tắc đơn giản rằng cùng PARTITION BY thì chỉ sort một lần.

### 7.1 Viết analytic specification nhất quán khi ngữ nghĩa giống nhau

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS row_num,
       LAG(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS prior_salary
FROM employees;
~~~

Việc dùng cùng partition/order specification giúp optimizer có cơ hội dùng chung thứ tự. Nó không bảo đảm một plan cụ thể; hãy xem operation thực tế.

### 7.2 Không thêm tie-breaker nếu nó thay đổi ngữ nghĩa RANK

Nếu yêu cầu hai nhân viên cùng lương phải đồng hạng, dùng:

~~~sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

Nếu thêm `employee_id` vào `ORDER BY`, mỗi nhân viên có thể trở thành một nhóm thứ tự riêng và không còn đồng hạng. Có thể cần một thứ tự khác cho `ROW_NUMBER`:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS deterministic_row_number
FROM employees;
~~~

Hai specification khác nhau vì chúng trả lời hai câu hỏi khác nhau. Không hy sinh kết quả đúng chỉ để hy vọng giảm số sort.

### 7.3 Khác biệt nhỏ trong ORDER BY có thể cần thứ tự khác

Các biểu thức sau không nhất thiết tương thích:

- `ORDER BY salary DESC`.
- `ORDER BY salary ASC`.
- `ORDER BY hire_date, employee_id`.
- `ORDER BY salary DESC NULLS LAST`.

Hướng sắp xếp, biểu thức, collation và NULL ordering có thể ảnh hưởng khả năng chia sẻ sort. Nếu plan cho thấy nhiều WINDOW SORT, hãy xác định từng sort phục vụ analytic nào trước khi chỉnh SQL.

## 8. Window frame ảnh hưởng cả kết quả lẫn chi phí

Window frame xác định những hàng tham gia vào hàm analytic tại hàng hiện tại. Ba dạng quan trọng:

- `ROWS`: tính theo số hàng vật lý trong thứ tự.
- `RANGE`: tính theo khoảng giá trị logic của khóa ORDER BY; các hàng cùng giá trị khóa có thể được xử lý như peers.
- `GROUPS`: tính theo nhóm peer trong các release hỗ trợ cú pháp này.

### 8.1 ROWS với running total

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Frame gồm tất cả hàng trước đó trong thứ tự cộng với hàng hiện tại. Thêm `TRANSACTION_ID` tạo thứ tự xác định nếu ngày có thể trùng.

### 8.2 RANGE và các hàng đồng giá trị

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Với các giao dịch cùng ngày, chúng là peers theo khóa `TRANSACTION_DATE`. Giá trị running sum có thể giống nhau cho các hàng cùng ngày vì frame logic bao gồm các hàng có giá trị khóa đến ngày hiện tại.

Nếu nghiệp vụ muốn tính từng giao dịch theo thứ tự riêng, dùng `ROWS` cùng khóa sắp xếp duy nhất. Nếu nghiệp vụ muốn tổng theo ngày, `RANGE` hoặc bước tổng hợp theo ngày có thể phù hợp hơn.

### 8.3 Frame mặc định có thể gây bất ngờ

Với nhiều hàm aggregate analytic có `ORDER BY` nhưng không chỉ định windowing clause, Oracle mặc định frame là:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Do đó:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date
)
~~~

không nhất thiết tương đương với `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` khi có nhiều giao dịch cùng ngày. Hãy viết frame tường minh khi kết quả phụ thuộc việc xử lý peers.

### 8.4 Moving average

~~~sql
AVG(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
) AS avg_last_7_transactions
~~~

Frame gồm tối đa bảy hàng theo thứ tự giao dịch: sáu hàng trước và hàng hiện tại. Đây là trung bình của bảy giao dịch gần nhất, không phải trung bình bảy ngày.

Nếu yêu cầu bảy ngày, phải định nghĩa frame theo khoảng thời gian phù hợp hoặc tổng hợp theo ngày trước; không diễn giải `ROWS 6 PRECEDING` thành “7 ngày”.

### 8.5 Frame càng phức tạp càng cần kiểm chứng

Các frame trượt có thể yêu cầu Oracle giữ thông tin về các hàng lân cận hoặc buffer dữ liệu. Chi phí cụ thể tùy hàm, frame, thứ tự và plan. Đừng suy luận mọi frame đều cần một sort mới; thứ tự có thể được dùng chung, nhưng frame vẫn có thể làm thay đổi cách operation duy trì trạng thái và truy cập hàng.

## 9. Deterministic ordering: thứ tự phải đủ xác định

Một lỗi logic phổ biến là dùng một cột không duy nhất làm analytic ORDER BY:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

Nếu nhiều nhân viên có cùng lương, thứ tự giữa họ không được xác định đầy đủ. Oracle có thể gán row number khác nhau giữa các lần chạy hoặc plan khác nhau. Nếu kết quả được dùng để chọn “nhân viên đầu tiên”, đây là rủi ro nghiệp vụ.

Thêm khóa duy nhất để phá hòa:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
)
~~~

`EMPLOYEE_ID` làm thứ tự xác định nếu nó duy nhất và không NULL. Nhưng với `RANK`/`DENSE_RANK`, chỉ thêm tie-breaker khi nghiệp vụ muốn phá hòa; nếu muốn giữ đồng hạng, giữ khóa xếp hạng chỉ gồm tiêu chí đồng hạng.

### 9.1 NULL ordering

Oracle mặc định:

- `ASC`: NULL thường đứng cuối (`NULLS LAST`).
- `DESC`: NULL thường đứng đầu (`NULLS FIRST`).

Để tránh phụ thuộc mặc định và thể hiện ý định:

~~~sql
ORDER BY salary DESC NULLS LAST, employee_id
~~~

Nếu NULL có ý nghĩa “chưa có lương” và không được xếp trước người có lương, hãy chỉ rõ `NULLS LAST`. Cách xử lý NULL cũng có thể ảnh hưởng kết quả ranking và phép so sánh.

### 9.2 Collation và biểu thức sắp xếp ký tự

Khi ORDER BY cột văn bản, thứ tự có thể chịu ảnh hưởng collation/NLS và kiểu dữ liệu. Nếu thứ tự tên là tiêu chí nghiệp vụ, cần xác định quy tắc so sánh chữ hoa/thường, dấu tiếng Việt và giá trị NULL. Không dùng thứ tự hiển thị hiện tại như một hợp đồng ổn định nếu môi trường có thể thay đổi collation.

## 10. Giảm chi phí bằng cách giảm dữ liệu đầu vào hợp lệ

Một trong những cách hiệu quả nhất là tránh đưa những hàng không cần thiết vào analytic operation. Nhưng việc lọc phải giữ nguyên ngữ nghĩa.

### 10.1 Lọc kỳ dữ liệu trước analytic khi chỉ cần kỳ đó

~~~sql
SELECT customer_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01'
  AND transaction_date <  DATE '2026-02-01';
~~~

Truy vấn chỉ tính running total trên các giao dịch trong tháng 1/2026. Nếu nghiệp vụ cần running total **từ trước đó đến hết tháng 1**, lọc bỏ các giao dịch cũ trước analytic sẽ làm sai kết quả.

### 10.2 Nếu cần lịch sử để tính nhưng chỉ hiển thị một kỳ

Dùng query block ngoài để lọc sau analytic:

~~~sql
WITH calculated AS (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           amount,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM sales_transactions
    WHERE transaction_date < DATE '2026-02-01'
)
SELECT customer_id,
       transaction_date,
       transaction_id,
       amount,
       running_amount
FROM calculated
WHERE transaction_date >= DATE '2026-01-01'
ORDER BY customer_id, transaction_date, transaction_id;
~~~

Nguồn analytic gồm toàn bộ lịch sử trước ngày 1/2; truy vấn ngoài chỉ hiển thị tháng 1. Đây là mẫu quan trọng khi cần giá trị lũy kế nhưng chỉ xuất một đoạn thời gian.

### 10.3 Giảm độ rộng hàng

Sort phải di chuyển/giữ dữ liệu cần thiết cho các bước tiếp theo. Nếu nguồn có nhiều cột LOB hoặc chuỗi lớn nhưng analytic chỉ cần vài cột, có thể tách query block:

~~~sql
WITH analytic_input AS (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           amount
    FROM sales_transactions
    WHERE transaction_date >= :start_date
      AND transaction_date <  :end_date
),
calculated AS (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           amount,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM analytic_input
)
SELECT *
FROM calculated;
~~~

Đây là cách làm rõ tập cột đầu vào; optimizer có thể inline CTE và biến đổi truy vấn. Vì vậy, không mặc định chỉ thêm CTE sẽ ép Oracle materialize dữ liệu hẹp hơn. Kiểm tra projection và plan thực tế.

### 10.4 Tổng hợp trước analytic khi đúng grain

Nếu báo cáo chỉ cần tổng theo ngày rồi tính running total theo ngày, không cần sắp hàng từng giao dịch:

~~~sql
WITH daily_sales AS (
    SELECT customer_id,
           TRUNC(transaction_date) AS sales_day,
           SUM(amount) AS daily_amount
    FROM sales_transactions
    WHERE transaction_date >= :start_date
      AND transaction_date <  :end_date
    GROUP BY customer_id, TRUNC(transaction_date)
)
SELECT customer_id,
       sales_day,
       daily_amount,
       SUM(daily_amount) OVER (
           PARTITION BY customer_id
           ORDER BY sales_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_daily_amount
FROM daily_sales;
~~~

Nếu dữ liệu có hàng triệu giao dịch nhưng chỉ vài nghìn ngày/khách hàng, bước tổng hợp có thể giảm đáng kể số hàng phải đưa vào analytic. Tuy nhiên, chỉ làm vậy nếu kết quả yêu cầu là lũy kế theo ngày; nó không thay thế lũy kế theo từng giao dịch.

## 11. Index và thứ tự analytic

Một index có thứ tự phù hợp đôi khi giúp Oracle đọc dữ liệu gần với thứ tự cần thiết, nhưng **không có bảo đảm rằng tạo index sẽ loại bỏ WINDOW SORT**.

Ví dụ analytic:

~~~sql
PARTITION BY customer_id
ORDER BY transaction_date, transaction_id
~~~

Index có thể được đánh giá:

~~~sql
CREATE INDEX ix_sales_customer_date
ON sales_transactions (
    customer_id,
    transaction_date,
    transaction_id
);
~~~

Index này có thứ tự khóa phù hợp với partition/order expression. Nhưng optimizer chỉ chọn nó khi chi phí tổng thể hợp lý; nếu cần đọc phần lớn bảng, full table scan cộng sort có thể rẻ hơn nhiều random index access.

### 11.1 Các yếu tố ảnh hưởng việc tận dụng index

- Các cột đầu của index có khớp với điều kiện lọc và thứ tự cần thiết không?
- Truy vấn có cần đọc phần lớn bảng hay chỉ một phạm vi nhỏ?
- Index có đủ selectivity để giảm số hàng đọc không?
- Có biểu thức, hàm, kiểu dữ liệu hoặc hướng NULL ordering làm thứ tự khác không?
- Index có bao phủ các cột cần thiết hay Oracle vẫn phải truy cập table row nhiều lần?
- Có nhiều partition logic khác nhau hoặc analytic order khác nhau không?

Một index phục vụ truy vấn ngày có thể không cung cấp thứ tự theo khách hàng; ngược lại, index theo khách hàng/ngày có thể không tối ưu khi lọc toàn bộ hệ thống theo một khoảng ngày hẹp.

### 11.2 Function-based index

Nếu analytic ORDER BY dùng biểu thức:

~~~sql
ORDER BY TRUNC(transaction_date)
~~~

có thể đánh giá function-based index:

~~~sql
CREATE INDEX ix_sales_customer_day
ON sales_transactions (
    customer_id,
    TRUNC(transaction_date),
    transaction_id
);
~~~

Chỉ tạo khi workload chứng minh biểu thức này thường xuyên được dùng và index có lợi. Index làm tăng chi phí INSERT/UPDATE/DELETE, dung lượng và bảo trì. Hãy kiểm tra execution plan với truy vấn thật.

### 11.3 Index không thay thế ORDER BY cuối

Dù plan đọc hàng theo index, SQL vẫn không bảo đảm thứ tự hiển thị nếu câu truy vấn không có `ORDER BY` cuối cùng. Thứ tự index là chi tiết thực thi; thứ tự kết quả là hợp đồng SQL chỉ khi được yêu cầu tường minh.

## 12. Parallel execution và partition skew

Oracle có thể thực hiện một số truy vấn analytic song song tùy cấu hình, object, plan và điều kiện. Song song có thể tăng throughput, nhưng không bảo đảm giảm latency cho mọi analytic query.

Các vấn đề thường gặp:

- Một số partition lớn hơn nhiều so với phần còn lại.
- Một nhóm cần xử lý nhiều hàng bị dồn vào một worker.
- Có bước phân phối hàng giữa parallel execution servers.
- Sort/merge và TEMP I/O trở thành nút thắt.
- Mức đồng thời cao làm nhiều truy vấn cạnh tranh PGA/TEMP và I/O.

### 12.1 Đánh giá skew

Thống kê `MAX(row_count)` so với `AVG(row_count)` là một tín hiệu ban đầu. Nếu partition lớn nhất gấp hàng trăm hoặc hàng nghìn lần trung bình, cần xem nhóm đó có chi phối thời gian chạy không.

~~~sql
WITH sizes AS (
    SELECT customer_id,
           COUNT(*) AS cnt
    FROM sales_transactions
    GROUP BY customer_id
)
SELECT MAX(cnt) AS largest_partition,
       ROUND(AVG(cnt), 2) AS average_partition,
       ROUND(MAX(cnt) / NULLIF(AVG(cnt), 0), 2)
           AS max_to_average_ratio
FROM sizes;
~~~

Tỷ lệ này không phải metric chuẩn duy nhất cho skew; hãy kết hợp percentile, số nhóm, dữ liệu theo thời gian và runtime thực tế.

### 12.2 Không chia nhỏ partition bằng một khóa giả

Nếu một khách hàng lớn cần running total xuyên suốt toàn bộ lịch sử, thêm `MOD(transaction_id, 8)` vào analytic PARTITION BY sẽ chia nhóm thành tám phần nhưng **làm sai running total của khách hàng**. Có thể dùng kỹ thuật phân đoạn/tiền tổng hợp chỉ khi có cách ghép lại đúng kết quả và đã chứng minh bằng công thức.

Không được hy sinh ngữ nghĩa chỉ để làm partition nhỏ hơn.

### 12.3 Parallelism không phải nút tăng tốc mặc định

Hint `PARALLEL` hoặc cấu hình parallel có thể tăng tài nguyên tiêu thụ và ảnh hưởng workload khác. Trước khi tăng parallel degree:

- Xác nhận truy vấn thực sự bị giới hạn bởi CPU/I/O/sort.
- Kiểm tra số worker được cấp thực tế.
- Kiểm tra skew và exchange/distribution operations.
- Đánh giá tác động tới TEMP, PGA và workload đồng thời.
- So sánh thời gian thực thi và tài nguyên, không chỉ elapsed time một lần chạy.

## 13. Kiểm chứng kết quả: đúng trước khi tối ưu

Một analytic query có thể chạy thành công nhưng trả sai do:

- Thiếu hoặc thừa partition key.
- ORDER BY không xác định khi có ties.
- Window frame mặc định không đúng ý nghĩa.
- Lọc hàng trước analytic thay vì sau analytic.
- NULL ordering khác kỳ vọng.
- JOIN nhân bản hàng trước khi tính.
- Đếm hàng theo sai grain.

Quy trình kiểm chứng nên dùng một tập dữ liệu nhỏ có thể tính tay, rồi mở rộng lên dữ liệu đại diện.

### 13.1 Tạo dữ liệu nhỏ có ties và NULL

~~~sql
CREATE TABLE lab_analytic_sales (
    transaction_id   NUMBER(6) PRIMARY KEY,
    customer_id      NUMBER(6),
    transaction_date DATE,
    amount           NUMBER(12,2)
);
~~~

~~~sql
INSERT ALL
    INTO lab_analytic_sales VALUES (1, 10, DATE '2026-01-01', 100)
    INTO lab_analytic_sales VALUES (2, 10, DATE '2026-01-02', 50)
    INTO lab_analytic_sales VALUES (3, 10, DATE '2026-01-02', 75)
    INTO lab_analytic_sales VALUES (4, 10, DATE '2026-01-04', NULL)
    INTO lab_analytic_sales VALUES (5, 20, DATE '2026-01-01', 40)
    INTO lab_analytic_sales VALUES (6, 20, DATE '2026-01-03', 60)
SELECT 1 FROM dual;

COMMIT;
~~~

Dữ liệu có:

- Khách hàng 10 có hai giao dịch cùng ngày 2/1.
- Một giao dịch có amount NULL.
- Khách hàng 20 là partition khác.

### 13.2 Tính running total với ROWS

~~~sql
SELECT customer_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM lab_analytic_sales
ORDER BY customer_id, transaction_date, transaction_id;
~~~

Kết quả dự kiến:

| CUSTOMER_ID | TRANSACTION_ID | DATE | AMOUNT | RUNNING_AMOUNT |
|---:|---:|---|---:|---:|
| 10 | 1 | 2026-01-01 | 100 | 100 |
| 10 | 2 | 2026-01-02 | 50 | 150 |
| 10 | 3 | 2026-01-02 | 75 | 225 |
| 10 | 4 | 2026-01-04 | NULL | 225 |
| 20 | 5 | 2026-01-01 | 40 | 40 |
| 20 | 6 | 2026-01-03 | 60 | 100 |

`SUM` bỏ qua giá trị NULL; vì vậy hàng số 4 không làm thay đổi running total. Partition khách hàng 20 bắt đầu lại từ 40.

### 13.3 So sánh ROWS với RANGE

~~~sql
SELECT customer_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date
           RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS range_running_amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS rows_running_amount
FROM lab_analytic_sales
ORDER BY customer_id, transaction_date, transaction_id;
~~~

Với khách hàng 10, hai hàng ngày 2/1 là peers theo khóa `TRANSACTION_DATE` trong biểu thức RANGE. Chúng có thể cùng nhận tổng 225, trong khi ROWS với `TRANSACTION_ID` phân biệt từng hàng và lần lượt cho 150, 225. Đây là khác biệt về ngữ nghĩa, không phải lỗi hiệu năng.

### 13.4 Kiểm tra ranking có ties

~~~sql
SELECT department_id,
       employee_id,
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
FROM employees;
~~~

Đối chiếu ba hàm:

- `ROW_NUMBER` luôn gán số thứ tự riêng cho từng hàng; cần tie-breaker nếu muốn kết quả ổn định.
- `RANK` giữ đồng hạng và để lại khoảng trống số thứ hạng tiếp theo.
- `DENSE_RANK` giữ đồng hạng nhưng không để khoảng trống.

Không thêm khóa duy nhất vào `RANK` nếu muốn các hàng cùng lương đồng hạng.

## 14. Kiểm chứng bằng truy vấn tham chiếu độc lập

Một cách xác minh là viết một truy vấn khác có cùng ý nghĩa để đối chiếu. Ví dụ running total có thể so với correlated subquery:

~~~sql
SELECT a.customer_id,
       a.transaction_id,
       a.transaction_date,
       a.amount,
       (
           SELECT SUM(b.amount)
           FROM lab_analytic_sales b
           WHERE b.customer_id = a.customer_id
             AND (
                    b.transaction_date < a.transaction_date
                 OR (
                        b.transaction_date = a.transaction_date
                    AND b.transaction_id <= a.transaction_id
                 )
             )
       ) AS reference_running_amount
FROM lab_analytic_sales a
ORDER BY a.customer_id, a.transaction_date, a.transaction_id;
~~~

Truy vấn con mô tả trực tiếp “cộng các giao dịch trước hoặc bằng hàng hiện tại theo thứ tự ngày/mã”. Nó có thể chậm hơn nhiều trên dữ liệu lớn; mục đích ở đây là làm **truy vấn tham chiếu kiểm chứng** trên dữ liệu nhỏ hoặc tập mẫu, không phải thay analytic query trong production.

Nếu hai cách khác nhau, kiểm tra:

- Cùng partition key chưa?
- Cùng thứ tự tie-break chưa?
- Cùng xử lý NULL của khóa ngày chưa?
- Có trùng transaction ID không?
- Có lọc hàng ở cùng giai đoạn chưa?

### 14.1 So sánh kết quả bằng MINUS

~~~sql
WITH analytic_result AS (
    SELECT customer_id,
           transaction_id,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM lab_analytic_sales
),
reference_result AS (
    SELECT a.customer_id,
           a.transaction_id,
           (
               SELECT SUM(b.amount)
               FROM lab_analytic_sales b
               WHERE b.customer_id = a.customer_id
                 AND (
                        b.transaction_date < a.transaction_date
                     OR (
                            b.transaction_date = a.transaction_date
                        AND b.transaction_id <= a.transaction_id
                     )
                 )
           ) AS running_amount
    FROM lab_analytic_sales a
)
SELECT *
FROM analytic_result
MINUS
SELECT *
FROM reference_result;
~~~

Nếu không có hàng, hai tập kết quả không có khác biệt theo các cột so sánh. Muốn kiểm tra chiều ngược lại, chạy `reference_result MINUS analytic_result`. `MINUS` loại trùng theo semantics tập hợp; nếu cần kiểm tra số lần xuất hiện của từng hàng, hãy kiểm tra khóa và số lượng riêng.

## 15. Kiểm chứng row count và grain trước/sau analytic

Analytic function thông thường gắn thêm cột và không tự nhân số hàng. Nếu số hàng thay đổi, hãy tìm nguyên nhân ở:

- JOIN trước analytic.
- WHERE/GROUP BY/DISTINCT.
- Query block ngoài lọc analytic result.
- UNION/UNION ALL hoặc phép biến đổi khác.

Có thể kiểm tra:

~~~sql
SELECT COUNT(*) AS source_rows
FROM sales_transactions;
~~~

và:

~~~sql
SELECT COUNT(*) AS analytic_rows
FROM (
    SELECT customer_id,
           transaction_date,
           amount,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date
           ) AS running_amount
    FROM sales_transactions
);
~~~

Nếu không có filter hoặc JOIN làm thay đổi grain, hai số đếm phải bằng nhau. Kiểm tra số hàng là bước đơn giản để phát hiện truy vấn vô tình thêm/bớt hàng.

### 15.1 Kiểm tra khóa duy nhất ở grain mong muốn

Nếu kết quả mong đợi một hàng cho mỗi giao dịch:

~~~sql
SELECT transaction_id,
       COUNT(*) AS occurrences
FROM (
    SELECT transaction_id,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
           ) AS running_amount
    FROM sales_transactions
)
GROUP BY transaction_id
HAVING COUNT(*) > 1;
~~~

Nếu truy vấn trả hàng, hãy xem lại JOIN hoặc khóa giao dịch. Không dùng `DISTINCT` để che việc JOIN tạo nhiều bản sao nếu chưa hiểu nguyên nhân.

### 15.2 Kiểm tra partition boundary

Chọn một vài partition đại diện và xác nhận:

- Tổng/average/rank bắt đầu lại ở partition mới.
- Không có hàng của khách hàng A ảnh hưởng tới kết quả khách hàng B.
- Các partition có NULL key được xử lý theo mong muốn; các hàng có partition key NULL thường thuộc cùng một nhóm NULL.

Ví dụ:

~~~sql
SELECT customer_id,
       MIN(running_amount) AS first_running_value,
       MAX(running_amount) AS last_running_value
FROM (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM sales_transactions
)
GROUP BY customer_id;
~~~

Đây chỉ là kiểm tra tổng quát; để xác minh chính xác, đối chiếu từng hàng tại điểm đầu/cuối và các giao dịch có ties/NULL.

## 16. Kiểm chứng NULL, giá trị trống và phép chia

Analytic aggregate tuân theo quy tắc NULL của hàm. Ví dụ:

~~~sql
AVG(amount) OVER (PARTITION BY customer_id)
~~~

`AVG` bỏ qua amount NULL; mẫu số là số giá trị amount không NULL, không phải tổng số hàng trong partition.

Nếu muốn biết cả số hàng lẫn số amount có dữ liệu:

~~~sql
SELECT customer_id,
       COUNT(*) OVER (PARTITION BY customer_id) AS row_count,
       COUNT(amount) OVER (PARTITION BY customer_id) AS amount_count,
       AVG(amount) OVER (PARTITION BY customer_id) AS avg_amount
FROM sales_transactions;
~~~

Với tỷ lệ:

~~~sql
SUM(paid_amount) OVER (PARTITION BY region_id)
/
NULLIF(
    SUM(total_amount) OVER (PARTITION BY region_id),
    0
) AS paid_ratio
~~~

`NULLIF` bảo vệ mẫu số bằng 0. Đừng tự thay tỷ lệ NULL thành 0 nếu “không có mẫu số” khác với “tỷ lệ thực sự bằng 0”.

## 17. Predicate placement và analytic result

Oracle không cho dùng analytic function trực tiếp trong `WHERE` cùng query block ở vị trí thông thường. Muốn lọc theo kết quả analytic, dùng inline view hoặc CTE:

~~~sql
WITH ranked AS (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id,
       department_id,
       salary
FROM ranked
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

Đây là cách lấy ba nhân viên đầu mỗi phòng ban. Bộ lọc `RN <= 3` nằm ở query block ngoài, sau khi analytic đã tính số thứ tự.

### 17.1 Lọc trước hay sau analytic?

Hai câu sau không tương đương:

~~~sql
SELECT customer_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01';
~~~

~~~sql
WITH all_history AS (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           amount,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM sales_transactions
)
SELECT *
FROM all_history
WHERE transaction_date >= DATE '2026-01-01';
~~~

Truy vấn đầu tính lũy kế chỉ trên hàng từ 1/1/2026. Truy vấn sau tính lũy kế trên lịch sử trước, rồi mới chỉ hiển thị từ 1/1/2026. Chọn theo định nghĩa nghiệp vụ.

## 18. Tối ưu theo thứ tự ưu tiên

Khi analytic query chậm, hãy điều tra từ những thay đổi ít rủi ro về ngữ nghĩa trước:

### 18.1 Xác nhận đúng tập dữ liệu

- Bỏ các hàng không thuộc kỳ báo cáo nếu chúng không cần cho phép tính.
- Đặt điều kiện lọc sớm khi việc đó không thay đổi cửa sổ cần tính.
- Tổng hợp trước nếu grain báo cáo nhỏ hơn grain nguồn và phép tính cho phép.
- Tránh JOIN bảng không cần thiết trước analytic.

### 18.2 Giảm số lượng và độ rộng hàng

- Chỉ chọn cột cần cho phép tính và kết quả.
- Tránh kéo LOB/chuỗi lớn qua bước sort nếu không cần.
- Kiểm tra JOIN có nhân bản hàng không.
- Tránh dùng DISTINCT chỉ để che lỗi grain.

### 18.3 Xem lại analytic specifications

- Có nhiều OVER clause khác nhau không?
- Có thể dùng chung partition/order specification mà vẫn đúng nghiệp vụ không?
- Có frame tường minh để tránh tính toán/logic ngoài ý muốn không?
- Có ORDER BY không cần thiết trong một analytic expression không?
- Có thể thay một phép tính bằng aggregate hoặc analytic đơn giản hơn không?

### 18.4 Xem execution plan và work area

- Xác định operation WINDOW SORT/BUFFER.
- So sánh E-Rows với A-Rows.
- Kiểm tra memory/TEMP và one-pass/multipass.
- Kiểm tra access path và partition pruning.
- Đánh giá concurrency, skew và parallel distribution.

### 18.5 Chỉ sau đó mới xem xét index/cấu trúc lưu trữ

- Đánh giá index theo partition key và analytic order key.
- Đánh giá partition vật lý theo workload tổng thể.
- Cân nhắc summary table/materialized view nếu báo cáo lặp lại và dữ liệu có chiến lược refresh phù hợp.
- Kiểm tra chi phí DML, storage, statistics và maintenance.

Không tạo index, tăng parallel degree hoặc thay đổi PGA/TEMP chỉ dựa vào việc nhìn thấy một operation sort.

## 19. Materialized view và tiền tổng hợp cho workload lặp lại

Nếu một báo cáo luôn tính analytic trên hàng tỷ giao dịch nhưng người dùng chỉ cần số liệu theo ngày/khách hàng, có thể cân nhắc lưu lớp tổng hợp:

~~~sql
SELECT customer_id,
       TRUNC(transaction_date) AS sales_day,
       SUM(amount) AS daily_amount
FROM sales_transactions
GROUP BY customer_id, TRUNC(transaction_date);
~~~

Sau đó analytic chạy trên dữ liệu ngày:

~~~sql
SELECT customer_id,
       sales_day,
       daily_amount,
       SUM(daily_amount) OVER (
           PARTITION BY customer_id
           ORDER BY sales_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_daily_amount
FROM customer_daily_sales;
~~~

Nếu báo cáo thường xuyên dùng và dữ liệu nguồn lớn, materialized view hoặc bảng summary có thể giảm lượng dữ liệu phải sort. Nhưng cần quyết định:

- Độ trễ chấp nhận được.
- Refresh nhanh/toàn phần và lịch refresh.
- Xử lý giao dịch đến muộn hoặc điều chỉnh lịch sử.
- Quyền truy cập và tính nhất quán.
- Dung lượng lưu trữ và chi phí cập nhật.

Tiền tổng hợp chỉ đúng khi nó giữ đủ thông tin cho phép tính cuối. Không thể thay tổng giao dịch bằng tổng ngày nếu báo cáo cần thứ tự từng giao dịch.

## 20. Các phép đo cần ghi lại khi benchmark

Khi so sánh hai cách viết, đừng chỉ ghi thời gian một lần. Hãy thu thập cùng điều kiện:

| Nhóm | Chỉ số nên ghi |
|---|---|
| Kích thước dữ liệu | Số hàng nguồn, số partition, max/avg rows per partition |
| Kết quả | Số hàng trả về, checksum/đối chiếu theo khóa, số NULL |
| Plan | SQL_ID, plan hash, operation, E-Rows/A-Rows |
| Tài nguyên | CPU time, elapsed time, buffer gets, physical reads |
| Sort | Work area, optimal/one-pass/multipass, TEMP bytes |
| Mức đồng thời | Số session chạy cùng lúc, mức tải hệ thống |
| Điều kiện | Bind values, thời điểm, statistics, cache state, phiên bản |

Đo ít nhất vài lần trong điều kiện ổn định; không so sánh lần chạy cold cache của câu này với lần chạy warm cache của câu kia rồi kết luận.

### 20.1 Elapsed time không đủ

Một truy vấn có elapsed time thấp trong môi trường ít tải có thể tiêu thụ CPU/TEMP lớn và làm chậm workload khác khi chạy đồng thời. Ngược lại, truy vấn chạy lâu do chờ tài nguyên ngoài sort không thể được cải thiện chỉ bằng thay đổi ORDER BY.

Hãy phân biệt:

- CPU-bound.
- I/O-bound.
- TEMP spill/sort-bound.
- Chờ lock hoặc tài nguyên khác.
- Chờ parallel workers hoặc contention.

### 20.2 So sánh cùng kết quả

Hai truy vấn chỉ có thể so sánh hiệu năng công bằng nếu cùng:

- Tập hàng đầu vào.
- Grain và partition logic.
- Tie-breaking và NULL ordering.
- Window frame.
- Cách lọc trước/sau analytic.
- Tập cột kết quả có ý nghĩa.

Nếu một câu bỏ `ORDER BY` hoặc bỏ partition key khiến nó chạy nhanh hơn nhưng trả kết quả khác, đó không phải tối ưu hợp lệ.

## 21. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Có `WINDOW SORT` là truy vấn kém | Sort có thể là bước bắt buộc để đáp ứng thứ tự; cần đo thay vì kết luận từ tên operation |
| Tạo index luôn bỏ được WINDOW SORT | Optimizer chỉ dùng index khi access path và chi phí phù hợp |
| Analytic PARTITION BY chính là partition bảng | Một bên là nhóm logic, một bên là cấu trúc lưu trữ |
| Nhiều partition nhỏ luôn tốt hơn | Phân vùng phải giữ đúng ngữ nghĩa; quá nhiều nhóm cũng có chi phí |
| Partition lớn luôn có thể chia nhỏ | Chia khóa có thể làm thay đổi kết quả; phải bảo toàn phép tính |
| Cùng PARTITION BY thì mọi analytic dùng chung sort | ORDER BY, NULL ordering và frame có thể khác nhau |
| ORDER BY trong OVER sắp xếp output | Nó chỉ điều khiển analytic; muốn thứ tự output phải có ORDER BY cuối |
| ROWS và RANGE giống nhau | ROWS theo hàng; RANGE theo giá trị logic và peers |
| Không có ORDER BY thì kết quả vẫn ổn định | Thứ tự hàng không được bảo đảm nếu không có quy tắc xác định |
| Lọc kỳ báo cáo trước analytic luôn tốt | Có thể làm mất lịch sử cần cho running total |
| Analytic làm giảm số hàng | Thường giữ số hàng đầu vào; GROUP BY mới gộp hàng |
| TEMP tăng chắc chắn do analytic | Sort, hash join, group by và các operation khác đều có thể dùng TEMP |
| EXPLAIN PLAN là runtime thật | Cần actual execution statistics để kiểm chứng số hàng và tài nguyên |

## 22. Bài thực hành tự kiểm tra

Các bài tập dùng bảng `LAB_ANALYTIC_SALES` ở phần 13 và các bảng giả định `EMPLOYEES`, `SALES_TRANSACTIONS`.

### Bài 1 — ROWS và RANGE

Chạy hai phép running sum:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

và:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Giải thích kết quả của hai giao dịch cùng ngày và chọn frame phù hợp nếu báo cáo cần lũy kế từng giao dịch.

### Bài 2 — Tính kích thước partition

Trên bảng giao dịch lớn, đếm số partition, tổng số hàng, min/avg/max hàng mỗi partition. Lấy 20 partition lớn nhất. Nêu dấu hiệu skew và tác động có thể tới sort/parallel execution.

### Bài 3 — Đọc execution plan

Chạy một truy vấn có `SUM(...) OVER (PARTITION BY ... ORDER BY ...)`. Dùng `DBMS_XPLAN.DISPLAY_CURSOR` với thống kê thực tế. Xác định operation analytic, E-Rows/A-Rows, memory và TEMP nếu có.

### Bài 4 — Nhiều analytic order

Viết cùng một truy vấn có:

- `ROW_NUMBER` theo ngày giao dịch.
- `RANK` theo số tiền giảm dần.
- `AVG` theo khách hàng không có ORDER BY.

Xem plan và mô tả các bước xử lý thứ tự. Sau đó hợp nhất specification chỉ khi ngữ nghĩa thực sự giống nhau.

### Bài 5 — Deterministic row number

Tạo nhiều hàng có cùng salary. Chạy ROW_NUMBER với ORDER BY salary, rồi thêm employee_id. Giải thích vì sao thứ tự hàng có thể thay đổi và khi nào tie-breaker là bắt buộc.

### Bài 6 — Predicate placement

Tính running total toàn lịch sử nhưng chỉ hiển thị tháng hiện tại. Viết một truy vấn lọc trước analytic và một truy vấn dùng CTE lọc sau analytic. So sánh kết quả tại hàng đầu tiên của tháng.

### Bài 7 — Kiểm chứng bằng correlated subquery

Viết analytic running total và correlated subquery độc lập trên bảng nhỏ. Dùng MINUS theo cả hai chiều để kiểm tra. Giải thích vì sao correlated subquery chỉ nên dùng làm reference ở tập nhỏ.

### Bài 8 — Kiểm tra row count sau JOIN

JOIN bảng giao dịch với bảng chi tiết có nhiều dòng cho mỗi giao dịch, rồi tính running total. Đếm số lần mỗi transaction_id xuất hiện và giải thích vì sao kết quả bị nhân bản.

### Bài 9 — TEMP và work area

Trong môi trường được DBA cho phép, chạy truy vấn sort lớn và quan sát `V$SQL_WORKAREA`/`V$TEMPSEG_USAGE`. So sánh truy vấn optimal và truy vấn spill. Không thay đổi tham số instance trong bài thực hành.

### Bài 10 — So sánh tiền tổng hợp

Tính running total từng giao dịch, sau đó tính running total theo ngày từ dữ liệu tổng hợp. Xác định hai kết quả khác grain nào và vì sao không thể thay thế nhau trong báo cáo chi tiết giao dịch.

## 23. Quy trình điều tra một analytic query chậm

~~~mermaid
flowchart TD
    A["Xác nhận kết quả và grain"] --> B["Đếm hàng nguồn và kích thước partition"]
    B --> C["Lấy actual execution plan"]
    C --> D["Tìm WINDOW SORT / BUFFER và sort khác"]
    D --> E["Đối chiếu E-Rows, A-Rows, memory, TEMP"]
    E --> F{"Nguồn có quá nhiều hàng hoặc skew?"}
    F -->|Có| G["Lọc/tổng hợp trước nếu giữ nguyên ngữ nghĩa"]
    F -->|Không| H["Xem nhiều analytic specification và sort reuse"]
    G --> I["Đánh giá lại plan và kết quả"]
    H --> I
    I --> J["Đánh giá index, partition vật lý, parallel hoặc summary"]
    J --> K["Benchmark cùng dữ liệu và cùng kết quả"]
~~~

Trình tự thực hành:

1. Viết lại yêu cầu kết quả: partition, thứ tự, frame và cách xử lý ties/NULL.
2. Kiểm tra số hàng và grain trước analytic.
3. Đo phân bố kích thước partition và phát hiện skew.
4. Thu thập actual execution plan, không chỉ explain plan.
5. Xác định sort operation, work area và TEMP.
6. Giảm hàng/độ rộng hoặc tổng hợp trước nếu không thay đổi kết quả.
7. Chuẩn hóa analytic specification khi ngữ nghĩa cho phép.
8. Đánh giá index, physical partitioning, parallelism hoặc summary.
9. So sánh hiệu năng cùng kết quả và trong điều kiện đại diện.

## 24. Ghi nhớ

| Chủ đề | Điều cần nhớ |
|---|---|
| WINDOW SORT | Có thể là bước cần thiết để đáp ứng thứ tự analytic; phải đo thay vì kết luận từ tên operation |
| PGA/work area | Bộ nhớ cho sort/window processing; thiếu bộ nhớ có thể spill ra TEMP |
| TEMP | Có thể được dùng bởi nhiều operation, không chỉ analytic |
| Partition size | Kiểm tra min/avg/max và phân bố, đặc biệt partition lớn nhất |
| Data skew | Một nhóm quá lớn có thể kéo dài sort hoặc làm lệch parallel workload |
| Analytic PARTITION BY | Chia nhóm logic để tính, khác physical table partitioning |
| Sort reuse | Có thể dùng chung khi specification tương thích, nhưng phải xác nhận bằng plan |
| ROWS/RANGE | Khác nhau ở cách xác định frame và xử lý peers |
| Deterministic order | Thêm tie-breaker duy nhất khi cần thứ tự hàng ổn định |
| Predicate placement | Lọc trước analytic chỉ khi không loại bỏ hàng cần cho cửa sổ |
| Actual plan | So sánh E-Rows/A-Rows, memory, TEMP và thời gian thực tế |
| Correctness | Đối chiếu dữ liệu nhỏ, ties, NULL, partition boundary và grain sau JOIN |

Tối ưu analytic query bắt đầu bằng việc xác định đúng kết quả cần tính. Sau đó mới đo số hàng, kích thước partition, sort, PGA và TEMP. Giảm dữ liệu đầu vào, giữ hàng ở đúng grain và dùng chung thứ tự khi ngữ nghĩa cho phép thường là những hướng điều tra hữu ích. Mọi thay đổi phải được kiểm chứng bằng cùng một tập dữ liệu, cùng partition, tie-breaking và window frame; một plan nhanh hơn nhưng đổi kết quả không phải là tối ưu.
