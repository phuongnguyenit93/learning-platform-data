# NULL trong B-tree và ảnh hưởng đến lựa chọn thiết kế chỉ mục

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Chỉ mục  
> **Mục tiêu:** Hiểu cách Oracle lưu giá trị NULL trong B-tree index; phân biệt index một cột và index ghép; xác định khi nào IS NULL/IS NOT NULL có thể dùng index; lựa chọn function-based index, bitmap index hoặc full table scan; hiểu ảnh hưởng của NULL đến thứ tự sắp xếp, unique constraint, selectivity và execution plan.

## 1. NULL là một giá trị đặc biệt trong SQL

NULL biểu thị dữ liệu chưa biết, không áp dụng hoặc chưa được cung cấp. NULL không giống số 0 hay một giá trị mặc định do ứng dụng tự chọn.

Trong SQL, phép so sánh thông thường với NULL trả về UNKNOWN:

~~~sql
SELECT *
FROM employees
WHERE commission_pct = NULL;
~~~

Predicate này không tìm được các hàng NULL như mong muốn. Phải dùng:

~~~sql
SELECT *
FROM employees
WHERE commission_pct IS NULL;
~~~

Tương tự, điều kiện:

~~~sql
WHERE commission_pct <> 0
~~~

không bao gồm hàng có COMMISSION_PCT là NULL, vì phép so sánh NULL <> 0 trả UNKNOWN. Nếu nghiệp vụ muốn lấy cả NULL, cần viết rõ:

~~~sql
WHERE commission_pct <> 0
   OR commission_pct IS NULL
~~~

Quy tắc logic ba giá trị này ảnh hưởng trực tiếp đến index design. Một B-tree index có thể không chứa một số hàng NULL, vì vậy database không thể dùng index đó để tìm mọi trường hợp IS NULL.

## 2. Oracle B-tree index lưu NULL như thế nào?

B-tree index của Oracle lưu các key entry theo thứ tự và kèm ROWID để tìm hàng trong bảng. Có một quy tắc quan trọng:

**Một hàng không được lưu trong B-tree index nếu tất cả các cột thuộc index key của hàng đó đều NULL.**

Điều này dẫn đến hai trường hợp khác nhau.

### 2.1. Index một cột nullable

Giả sử:

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    commission_pct NUMBER
);

CREATE INDEX ix_employees_commission
ON employees(commission_pct);
~~~

Dữ liệu:

~~~text
EMPLOYEE_ID | COMMISSION_PCT
------------+---------------
100         | 0.10
101         | 0.15
102         | NULL
103         | NULL
~~~

Index IX_EMPLOYEES_COMMISSION có entry cho các hàng 100 và 101. Hai hàng 102 và 103 có key duy nhất là NULL nên không có entry trong B-tree index này.

Vì vậy truy vấn:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE commission_pct IS NULL;
~~~

không thể dùng index một cột trên COMMISSION_PCT làm nguồn để tìm đầy đủ các hàng NULL. Oracle thường phải đọc bảng bằng full table scan hoặc chọn một access path khác có khả năng trả lời predicate.

Ngược lại:

~~~sql
SELECT employee_id
FROM employees
WHERE commission_pct IS NOT NULL;
~~~

có thể dùng B-tree index vì tất cả hàng có giá trị khác NULL đều có entry. Optimizer vẫn quyết định theo cost; nếu phần lớn bảng có COMMISSION_PCT khác NULL, full table scan có thể rẻ hơn index scan cộng table access.

### 2.2. Index ghép có ít nhất một thành phần khác NULL

Xét index:

~~~sql
CREATE INDEX ix_employees_commission_id
ON employees(commission_pct, employee_id);
~~~

EMPLOYEE_ID là PRIMARY KEY nên luôn khác NULL. Khi COMMISSION_PCT là NULL, key ghép vẫn có thành phần EMPLOYEE_ID khác NULL. Vì vậy hàng đó vẫn có entry trong B-tree index ghép.

| EMPLOYEE_ID | COMMISSION_PCT | Có entry trong index (COMMISSION_PCT, EMPLOYEE_ID)? |
|---:|---:|---|
| 100 | 0.10 | Có |
| 101 | 0.15 | Có |
| 102 | NULL | Có, vì EMPLOYEE_ID khác NULL |
| 103 | NULL | Có, vì EMPLOYEE_ID khác NULL |

Index ghép này có thể cung cấp access path cho predicate COMMISSION_PCT IS NULL vì COMMISSION_PCT là leading column và các hàng NULL vẫn có entry nhờ EMPLOYEE_ID.

Điều này không có nghĩa optimizer chắc chắn dùng index. Nó còn phụ thuộc số hàng NULL, statistics, clustering factor, chi phí table access và phần cột được truy vấn.

### 2.3. Nếu toàn bộ cột của index ghép đều NULL

Với index:

~~~sql
CREATE INDEX ix_example_a_b
ON example_table(a, b);
~~~

Một hàng có A = NULL và B = NULL không có entry trong B-tree index này. Một hàng có A = NULL, B = 7 thì có entry vì key không còn toàn NULL.

| A | B | Có entry trong B-tree index (A, B)? |
|---|---|---|
| NULL | NULL | Không |
| NULL | 7 | Có |
| 7 | NULL | Có |
| 7 | 8 | Có |

Đây là khác biệt cốt lõi giữa index một cột và index ghép khi xử lý NULL.

## 3. Predicate IS NULL và IS NOT NULL có dùng B-tree không?

Không nên trả lời đơn giản rằng “B-tree không hỗ trợ NULL”. Câu trả lời đúng phụ thuộc vào tất cả key columns và thứ tự cột index.

| Predicate | Index một cột trên C nullable | Index ghép (C, NOT_NULL_ID) |
|---|---|---|
| C IS NULL | Không có entry để tìm các hàng NULL | Có thể dùng vì entry vẫn tồn tại |
| C IS NOT NULL | Có thể dùng | Có thể dùng |
| C = :value khác NULL | Có thể dùng | Có thể dùng nếu C là leading column |
| C IS NULL và ID = :id | Index đơn không đủ để tìm NULL | Index ghép có thể phù hợp |
| ID = :id | Không phù hợp nếu ID không nằm trong index | Không phải leading key; có thể cần access path khác |

### 3.1. IS NOT NULL

Với index một cột:

~~~sql
SELECT employee_id
FROM employees
WHERE commission_pct IS NOT NULL;
~~~

Oracle có thể dùng index range scan hoặc một dạng index scan phù hợp để đọc các entry có key khác NULL. Nếu truy vấn cần nhiều cột không nằm trong index, Oracle có thể phải truy cập table block theo ROWID.

Nếu predicate trả về tỷ lệ rất lớn của bảng, full table scan có thể ít tốn kém hơn.

### 3.2. IS NULL trên index ghép

~~~sql
CREATE INDEX ix_emp_commission_id
ON employees(commission_pct, employee_id);
~~~

Truy vấn:

~~~sql
SELECT employee_id
FROM employees
WHERE commission_pct IS NULL;
~~~

Index ghép có thể được dùng để tìm vùng key có COMMISSION_PCT NULL vì EMPLOYEE_ID bảo đảm entry tồn tại. Nếu chỉ chọn EMPLOYEE_ID, index còn có thể đáp ứng truy vấn mà không cần table access trong trường hợp phù hợp.

Đây là một lý do index ghép đôi khi hữu ích hơn index đơn khi cột đầu có thể NULL.

### 3.3. Leading column vẫn quan trọng

Giả sử index là:

~~~sql
CREATE INDEX ix_emp_status_commission
ON employees(status, commission_pct);
~~~

Predicate:

~~~sql
WHERE commission_pct IS NULL
~~~

đang lọc theo cột thứ hai, không phải leading column. Optimizer có thể cân nhắc index skip scan nếu phân bố và số distinct của STATUS phù hợp, nhưng không thể mặc định index này sẽ phục vụ IS NULL hiệu quả.

Nếu truy vấn thường xuyên lọc COMMISSION_PCT, cân nhắc index bắt đầu bằng COMMISSION_PCT hoặc một function-based index dành cho predicate NULL. Cần xem plan thực tế trước khi tạo index mới.

## 4. Function-based index để lập chỉ mục các hàng NULL

Khi cần tìm NULL thường xuyên và cột đơn không có entry cho NULL, có thể tạo function-based index (FBI). Ý tưởng là biến NULL thành một biểu thức khác NULL để Oracle lưu entry.

Chọn biểu thức sao cho không làm thay đổi ý nghĩa nghiệp vụ, không xung đột với giá trị hợp lệ, query predicate có thể khớp biểu thức index và không tạo một index quá rộng nếu chỉ cần tìm một tập con nhỏ.

### 4.1. Dùng CASE để chỉ index các hàng NULL

~~~sql
CREATE INDEX ix_emp_commission_null
ON employees (
    CASE
        WHEN commission_pct IS NULL THEN 1
    END
);
~~~

Với hàng có COMMISSION_PCT NULL, biểu thức trả về 1 nên B-tree có entry. Với hàng khác NULL, biểu thức trả NULL; các hàng này không được đưa vào index vì toàn bộ key expression là NULL.

Truy vấn tương ứng:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE CASE
          WHEN commission_pct IS NULL THEN 1
      END = 1;
~~~

Predicate sử dụng cùng biểu thức có thể dùng function-based index. Optimizer cần nhận diện biểu thức tương ứng và cost phải có lợi.

Một cách khác là tạo virtual column:

~~~sql
ALTER TABLE employees ADD (
    commission_is_null NUMBER
        GENERATED ALWAYS AS (
            CASE WHEN commission_pct IS NULL THEN 1 ELSE 0 END
        ) VIRTUAL
);

CREATE INDEX ix_emp_commission_null_flag
ON employees(commission_is_null);
~~~

Truy vấn:

~~~sql
SELECT employee_id
FROM employees
WHERE commission_is_null = 1;
~~~

Virtual column đặt tên cho biểu thức và giúp query dễ đọc. Biểu thức trả 0 hoặc 1 cho mọi hàng, nên index có entry cho cả hai nhóm; nếu nhóm NULL rất nhỏ, index vẫn có thể có ích. Nếu cần index chỉ cho nhóm NULL, dùng biểu thức CASE trả NULL cho các hàng không cần lưu.

### 4.2. Dùng NVL với sentinel

Một lựa chọn khác:

~~~sql
CREATE INDEX ix_emp_commission_nvl
ON employees(NVL(commission_pct, -999999));
~~~

Truy vấn phải dùng cùng biểu thức:

~~~sql
SELECT employee_id
FROM employees
WHERE NVL(commission_pct, -999999) = -999999;
~~~

Cách này chỉ an toàn nếu -999999 chắc chắn nằm ngoài miền giá trị hợp lệ. Nếu giá trị đó có thể xuất hiện thật, hàng có commission bằng sentinel và hàng NULL bị gộp vào cùng key; query có thể trả kết quả sai theo nghiệp vụ.

Không chọn sentinel tùy tiện. Với chuỗi, sentinel còn chịu ảnh hưởng collation, độ dài, ký tự hợp lệ và quy tắc chuẩn hóa. CASE thường diễn đạt ý nghĩa rõ hơn.

### 4.3. FBI có chi phí duy trì

Function-based index vẫn là index vật lý. Khi cột đầu vào thay đổi, Oracle phải tính biểu thức và duy trì entry tương ứng. Index tạo thêm storage, redo, undo và chi phí INSERT/UPDATE/DELETE.

Nếu biểu thức phụ thuộc function do người dùng định nghĩa, function phải đáp ứng yêu cầu deterministic và các quy tắc Oracle liên quan. Thay đổi logic function có thể yêu cầu rebuild/recompute index theo quy trình phù hợp.

## 5. Bitmap index và NULL

Bitmap index của Oracle có khả năng biểu diễn các giá trị NULL, khác với quy tắc B-tree bỏ hàng mà tất cả key columns đều NULL. Vì vậy bitmap index có thể phục vụ một số predicate IS NULL.

~~~sql
CREATE BITMAP INDEX bix_employees_commission
ON employees(commission_pct);
~~~

Truy vấn:

~~~sql
SELECT COUNT(*)
FROM employees
WHERE commission_pct IS NULL;
~~~

Optimizer có thể dùng bitmap index để xác định tập ROWID tương ứng với NULL.

Tuy nhiên, bitmap index thường phù hợp với workload data warehouse hoặc phân tích có ít DML đồng thời. Với OLTP nhiều session INSERT/UPDATE/DELETE, bitmap index có thể tạo locking/contention rộng hơn và làm giảm concurrency.

Không tạo bitmap index chỉ vì muốn lập chỉ mục NULL trên bảng giao dịch. Hãy cân nhắc function-based B-tree index hoặc full scan theo workload.

## 6. NULL ảnh hưởng đến ORDER BY và index ordering

Oracle có quy tắc mặc định cho vị trí NULL trong sort:

- ASC: NULLS LAST.
- DESC: NULLS FIRST.

Ví dụ:

~~~sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct ASC;
~~~

Hàng có COMMISSION_PCT NULL nằm cuối theo mặc định.

~~~sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct DESC;
~~~

NULL nằm đầu theo mặc định.

Có thể chỉ định tường minh:

~~~sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct DESC NULLS LAST;
~~~

Khi index được dùng để đáp ứng ORDER BY, hướng scan và vị trí NULL của index phải tương thích với thứ tự yêu cầu. Nếu không khớp, Oracle có thể phải sort thêm hoặc chọn một access path khác.

Đừng giả định một index trên C luôn loại bỏ SORT ORDER BY cho mọi tổ hợp ASC/DESC và NULLS FIRST/LAST. Kiểm tra execution plan.

### 6.1. Thứ tự hỗn hợp nhiều cột

~~~sql
ORDER BY department_id ASC,
         commission_pct DESC NULLS LAST,
         employee_id ASC
~~~

Thứ tự NULL được quy định riêng cho COMMISSION_PCT. Index ứng viên có thể cần phản ánh các cột và hướng sort phù hợp:

~~~sql
CREATE INDEX ix_emp_dept_comm_id
ON employees (
    department_id ASC,
    commission_pct DESC,
    employee_id ASC
);
~~~

Tùy release, Oracle hỗ trợ nhiều dạng index ordering và scan direction. Nếu NULLS LAST không trùng với thứ tự mà index scan cung cấp cho cột DESC, optimizer có thể cần sort. Với yêu cầu sort đặc biệt, có thể dùng biểu thức null-rank trong index:

~~~sql
CREATE INDEX ix_emp_dept_comm_sort
ON employees (
    department_id,
    CASE WHEN commission_pct IS NULL THEN 1 ELSE 0 END,
    commission_pct DESC,
    employee_id
);
~~~

Query phải ORDER BY cùng logic:

~~~sql
SELECT employee_id, department_id, commission_pct
FROM employees
ORDER BY department_id,
         CASE WHEN commission_pct IS NULL THEN 1 ELSE 0 END,
         commission_pct DESC,
         employee_id;
~~~

Index này minh họa việc mã hóa NULLS LAST thành một sort key riêng. Cần kiểm tra khả năng optimizer sử dụng index và tính đúng của ordering trên release thực tế.

## 7. NULL và UNIQUE index/constraint

UNIQUE và NOT NULL là hai quy tắc khác nhau.

Một unique constraint không tự động có nghĩa cột bắt buộc phải có giá trị. Với unique key một cột, Oracle cho phép nhiều hàng có giá trị NULL. Ví dụ:

~~~sql
CREATE TABLE lab_unique_null (
    code VARCHAR2(20),
    CONSTRAINT uq_lab_unique_null UNIQUE(code)
);
~~~

Có thể chèn nhiều hàng có CODE NULL mà không vi phạm unique constraint:

~~~sql
INSERT INTO lab_unique_null(code) VALUES (NULL);
INSERT INTO lab_unique_null(code) VALUES (NULL);
~~~

Nếu nghiệp vụ yêu cầu mỗi hàng phải có CODE, cần khai báo cả NOT NULL:

~~~sql
ALTER TABLE lab_unique_null
MODIFY (code NOT NULL);
~~~

### 7.1. Unique key ghép

Với unique constraint nhiều cột, cần phân biệt các tổ hợp có NULL với khóa đầy đủ. Oracle có quy tắc lưu trữ và so sánh của composite key; một hàng có ít nhất một thành phần khác NULL có thể tạo index entry dù thành phần khác NULL. Không suy luận rằng mọi tổ hợp có NULL đều giống trường hợp một cột NULL.

Nếu business key bắt buộc mọi thành phần đều có giá trị, khai báo NOT NULL cho từng thành phần. Nếu nghiệp vụ muốn một quy tắc đặc biệt về uniqueness khi một phần key là NULL, hãy biểu diễn quy tắc đó bằng constraint/index được thiết kế rõ ràng và thử các tổ hợp đại diện trên đúng Oracle release.

Ví dụ khóa ghép bắt buộc:

~~~sql
CREATE TABLE tenant_customer (
    tenant_id NUMBER NOT NULL,
    external_id VARCHAR2(50 CHAR) NOT NULL,
    customer_name VARCHAR2(100),
    CONSTRAINT uq_tenant_customer
        UNIQUE (tenant_id, external_id)
);
~~~

Ở đây NOT NULL bảo đảm uniqueness áp dụng trên khóa nghiệp vụ đầy đủ.

### 7.2. Function-based unique index để kiểm soát NULL

Có thể tạo unique function-based index khi cần áp đặt quy tắc tùy biến. Ví dụ chỉ duy nhất các email khác NULL của khách hàng ACTIVE:

~~~sql
CREATE UNIQUE INDEX uq_active_email
ON customers (
    CASE
        WHEN customer_status = 'ACTIVE' THEN LOWER(email)
    END
);
~~~

Các hàng không ACTIVE hoặc có EMAIL NULL có thể tạo expression NULL và không có entry theo cách thiết kế này. Hàng ACTIVE có email được index theo giá trị chuẩn hóa.

Nếu cần cấm nhiều email NULL hoặc cần uniqueness có điều kiện khác, biểu thức phải phản ánh chính xác quy tắc nghiệp vụ. Function-based unique index không thay thế kiểm tra NOT NULL khi dữ liệu bắt buộc phải có.

## 8. Chọn index theo phân bố NULL và selectivity

Có một index không đồng nghĩa mọi query dùng index đều nhanh. Optimizer so sánh chi phí index access cộng table access với full table scan.

Các yếu tố quan trọng:

- Tỷ lệ NULL trong cột.
- Tỷ lệ hàng thỏa predicate.
- Số block bảng và index.
- Clustering factor.
- Cột truy vấn có được bao phủ trong index không.
- Số hàng cần trả và số ROWID phải truy cập.
- Statistics và histogram.
- Các predicate khác kết hợp với IS NULL.

### 8.1. NULL rất hiếm

Nếu chỉ 0,1% hàng có NULL, function-based index chỉ chứa nhóm NULL có thể nhỏ và rất hiệu quả cho truy vấn tìm nhóm đó.

### 8.2. NULL chiếm phần lớn bảng

Nếu 90% hàng có NULL, index để lấy toàn bộ nhóm NULL có thể không có lợi. Đọc gần như toàn bảng bằng index rồi truy cập table theo ROWID có thể tốn hơn full table scan.

### 8.3. IS NOT NULL cũng phụ thuộc selectivity

Nếu chỉ 1% hàng khác NULL, B-tree index một cột có thể hữu ích. Nếu 99% hàng khác NULL và query cần nhiều cột, full scan có thể rẻ hơn.

### 8.4. Kết hợp predicate

~~~sql
SELECT employee_id, commission_pct
FROM employees
WHERE department_id = :p_department_id
  AND commission_pct IS NULL;
~~~

Index ghép ứng viên:

~~~sql
CREATE INDEX ix_emp_dept_comm
ON employees(department_id, commission_pct, employee_id);
~~~

DEPARTMENT_ID là predicate equality và là leading column; COMMISSION_PCT là predicate NULL tiếp theo; EMPLOYEE_ID bảo đảm entry tồn tại cho hàng có hai cột đầu NULL hoặc một phần NULL, vì ID không NULL.

Tuy nhiên, nếu DEPARTMENT_ID cũng có thể NULL hoặc query pattern khác, cần đánh giá lại thứ tự và tính bao phủ. Index design phải dựa trên tập truy vấn thực tế, không chỉ một ví dụ.

## 9. Statistics giúp optimizer ước lượng NULL

Oracle thu thập số lượng NULL và phân bố dữ liệu trong table/column statistics. Có thể xem NUM_NULLS trong USER_TAB_COL_STATISTICS:

~~~sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram
FROM user_tab_col_statistics
WHERE table_name = 'EMPLOYEES'
ORDER BY column_name;
~~~

Thu thập statistics cho bảng:

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

CASCADE cho phép thu thập statistics liên quan index theo thiết lập phù hợp. Không nên chạy gather statistics tùy tiện giữa giờ cao điểm trên bảng lớn mà không theo quy trình DBA.

NUM_NULLS giúp hiểu tỷ lệ NULL, nhưng optimizer còn cần statistics khác và query context. Sau khi phân bố dữ liệu thay đổi mạnh, statistics cũ có thể làm cardinality estimate không chính xác.

## 10. Kiểm tra execution plan

Ví dụ truy vấn IS NULL:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id
FROM employees
WHERE commission_pct IS NULL;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Nếu chỉ có index đơn trên COMMISSION_PCT, plan thường không thể dùng index đó để lấy các hàng NULL vì không có entry tương ứng. Nếu có function-based index hoặc composite index phù hợp, optimizer có thể chọn index access.

Xem runtime plan khi có quyền và statistics phù hợp:

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

Chú ý:

- TABLE ACCESS FULL: quét bảng.
- INDEX RANGE SCAN: đọc một vùng key trong index.
- INDEX FAST FULL SCAN: quét index như cấu trúc dữ liệu, không bảo đảm thứ tự.
- INDEX FULL SCAN: quét index theo thứ tự phù hợp trong một số trường hợp.
- Predicate Information: điều kiện được dùng làm access predicate hay filter predicate.
- E-Rows/A-Rows: số hàng ước lượng so với thực tế.
- Buffers/reads: chi phí logical/physical I/O.

EXPLAIN PLAN chỉ là plan ước lượng. Runtime statistics trên cursor thực tế giúp hiểu optimizer đã thực hiện ra sao. Không tạo index chỉ để ép một plan; hãy đo với dữ liệu và bind values đại diện.

## 11. Ví dụ so sánh ba thiết kế

Giả sử bảng EMPLOYEES có 1.000.000 hàng, trong đó 5% COMMISSION_PCT là NULL.

### Thiết kế A — Chỉ mục một cột

~~~sql
CREATE INDEX ix_emp_commission
ON employees(commission_pct);
~~~

- Phù hợp cho truy vấn bằng giá trị khác NULL và một số truy vấn IS NOT NULL.
- Không lưu hàng mà COMMISSION_PCT là NULL.
- Không thể dùng riêng index này để tìm đầy đủ hàng IS NULL.

### Thiết kế B — Chỉ mục ghép có ID NOT NULL

~~~sql
CREATE INDEX ix_emp_commission_id
ON employees(commission_pct, employee_id);
~~~

- Mọi hàng có EMPLOYEE_ID khác NULL có entry, kể cả COMMISSION_PCT NULL.
- Có thể hỗ trợ truy vấn IS NULL khi COMMISSION_PCT là leading column.
- Index lớn hơn vì lưu thêm EMPLOYEE_ID.
- Có thể bao phủ truy vấn chỉ cần EMPLOYEE_ID và COMMISSION_PCT.

### Thiết kế C — Function-based index chỉ cho NULL

~~~sql
CREATE INDEX ix_emp_commission_null
ON employees (
    CASE WHEN commission_pct IS NULL THEN 1 END
);
~~~

Truy vấn:

~~~sql
SELECT employee_id
FROM employees
WHERE CASE WHEN commission_pct IS NULL THEN 1 END = 1;
~~~

- Index chỉ chứa các hàng có COMMISSION_PCT NULL.
- Có thể nhỏ nếu NULL hiếm.
- Câu query phải dùng biểu thức phù hợp.
- Thêm chi phí duy trì biểu thức/index khi DML.

Không có thiết kế nào tốt nhất cho mọi workload. So sánh storage, số hàng, plan, buffer gets và thời gian chạy.

## 12. Bài thực hành trên schema lab

Các ví dụ dùng bảng thử riêng. Chỉ chạy trên schema được phép.

### 12.1. Tạo dữ liệu

~~~sql
CREATE TABLE lab_null_index (
    row_id NUMBER CONSTRAINT pk_lab_null_index PRIMARY KEY,
    group_code VARCHAR2(10),
    nullable_value NUMBER,
    description VARCHAR2(50)
);

INSERT INTO lab_null_index VALUES (1, 'A', 10, 'Value 10');
INSERT INTO lab_null_index VALUES (2, 'A', NULL, 'Null A 1');
INSERT INTO lab_null_index VALUES (3, 'A', NULL, 'Null A 2');
INSERT INTO lab_null_index VALUES (4, 'B', 20, 'Value 20');
INSERT INTO lab_null_index VALUES (5, 'B', NULL, 'Null B');
INSERT INTO lab_null_index VALUES (6, NULL, NULL, 'All key values null');
COMMIT;
~~~

### 12.2. Tạo index đơn và xem truy vấn IS NULL

~~~sql
CREATE INDEX ix_lab_nullable_value
ON lab_null_index(nullable_value);

EXPLAIN PLAN FOR
SELECT row_id
FROM lab_null_index
WHERE nullable_value IS NULL;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Index đơn không có entry cho các hàng NULL; plan có thể dùng full table scan.

### 12.3. Tạo index ghép

~~~sql
CREATE INDEX ix_lab_nullable_rowid
ON lab_null_index(nullable_value, row_id);
~~~

Truy vấn:

~~~sql
SELECT row_id
FROM lab_null_index
WHERE nullable_value IS NULL;
~~~

Vì ROW_ID khác NULL, các hàng có NULLABLE_VALUE NULL vẫn có entry trong index ghép. Xem plan để biết optimizer có chọn index không.

### 12.4. Tạo function-based index

~~~sql
CREATE INDEX ix_lab_null_flag
ON lab_null_index (
    CASE WHEN nullable_value IS NULL THEN 1 END
);
~~~

Truy vấn:

~~~sql
SELECT row_id
FROM lab_null_index
WHERE CASE WHEN nullable_value IS NULL THEN 1 END = 1;
~~~

So sánh plan và số buffer với hai thiết kế trước. Bảng nhỏ có thể khiến full table scan rẻ hơn dù index có thể đáp ứng predicate; tăng dữ liệu thử nếu cần quan sát rõ hơn.

### 12.5. Kiểm tra statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_NULL_INDEX',
        cascade => TRUE
    );
END;
/
~~~

Sau đó xem:

~~~sql
SELECT column_name, num_distinct, num_nulls, histogram
FROM user_tab_col_statistics
WHERE table_name = 'LAB_NULL_INDEX';
~~~

### 12.6. Dọn bảng lab

~~~sql
DROP TABLE lab_null_index PURGE;
~~~

Chỉ xóa bảng lab do chính bạn tạo.

## 13. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ B-tree luôn lưu mọi NULL | Bỏ sót quy tắc hàng có toàn bộ key columns NULL không được index | Phân tích từng key column và index ghép |
| Dùng index một cột để tìm IS NULL | Index không có entry cho các hàng NULL | FBI, composite index hoặc full scan |
| Nghĩ composite index không thể chứa NULL | Mất cơ hội dùng index ghép có thành phần khác NULL | Thêm/kiểm tra cột NOT NULL ở key nếu phù hợp |
| Đặt cột lọc NULL ở vị trí không thuận lợi | Không có access path tốt theo leading prefix | Thiết kế thứ tự index theo predicate |
| Dùng NVL với sentinel hợp lệ | Gộp NULL với dữ liệu thật | Chọn sentinel ngoài miền hoặc dùng CASE |
| Tạo bitmap index cho OLTP nhiều DML | Tăng contention | Cân nhắc B-tree/FBI hoặc full scan |
| Cho rằng UNIQUE cũng có nghĩa NOT NULL | Dữ liệu thiếu khóa vẫn tồn tại | Khai báo NOT NULL riêng |
| Dùng = NULL | Predicate không match NULL | Dùng IS NULL |
| Quên NULL trong <> | Bỏ sót hàng NULL | Viết predicate bao gồm IS NULL nếu nghiệp vụ yêu cầu |
| Giả định index luôn nhanh hơn full scan | Có thể tăng I/O và table lookup | So sánh cost/plan với dữ liệu thật |
| ORDER BY không nêu NULLS FIRST/LAST | Vị trí NULL phụ thuộc mặc định ASC/DESC | Khai báo sort semantics rõ |
| Không cập nhật statistics sau thay đổi lớn | Cardinality estimate sai | Thu thập statistics theo quy trình |

## 14. Quy trình chọn index cho cột nullable

~~~text
Cột có thể NULL?
      |
      v
Truy vấn có lọc IS NULL?
      |
      +-- Không --> Đánh giá IS NOT NULL/equality/range
      |
      +-- Có
           |
           v
Index B-tree một cột?
           |
           +-- Có --> Không chứa entry NULL
           |          |
           |          v
           |     NULL hiếm và query quan trọng?
           |          |
           |          +-- Có --> Cân nhắc FBI hoặc composite index
           |          +-- Không --> Full scan có thể phù hợp
           |
           +-- Composite index?
                      |
                      v
           Có thành phần khác NULL
           và cột nullable ở leading prefix?
                      |
                 +----+----+
                 |         |
                Có        Không
                 |         |
           Có thể dùng   Đánh giá FBI,
           để tìm NULL   skip scan hoặc index mới
                 |
                 v
           Kiểm tra selectivity,
           statistics và execution plan
~~~

Quy trình này giúp khoanh vùng lựa chọn, nhưng quyết định cuối cùng vẫn dựa trên workload và chi phí thực tế.

## 15. Ghi nhớ cốt lõi

- Oracle B-tree index không lưu một hàng nếu tất cả cột thuộc index key của hàng đó đều NULL.
- Index một cột trên cột nullable vì vậy không có entry cho các hàng NULL; không thể dùng riêng index đó để tìm đầy đủ predicate IS NULL.
- Index ghép vẫn có entry nếu ít nhất một thành phần key khác NULL; cột NOT NULL ở phía sau có thể giúp lưu hàng mà leading column là NULL.
- IS NOT NULL có thể dùng B-tree vì các hàng khác NULL có entry, nhưng optimizer vẫn có thể chọn full scan theo selectivity và cost.
- Function-based index dùng CASE hoặc biểu thức chuẩn hóa để tạo key khác NULL cho nhóm cần tìm.
- NVL với sentinel chỉ an toàn nếu sentinel chắc chắn không phải giá trị hợp lệ; CASE thường thể hiện ý định rõ hơn.
- Bitmap index có thể biểu diễn NULL nhưng thường cần cân nhắc kỹ trong workload OLTP nhiều DML đồng thời.
- NULLS LAST/FIRST ảnh hưởng thứ tự sort; index chỉ loại bỏ sort khi ordering phù hợp và optimizer chọn access path tương ứng.
- UNIQUE không đồng nghĩa NOT NULL; khai báo NOT NULL riêng khi business key bắt buộc đầy đủ.
- Đặt cột trong leading prefix phù hợp với predicate; kiểm tra index hiện có trước khi tạo thêm.
- Statistics về NUM_NULLS, selectivity, clustering factor và execution plan quyết định index có thực sự có lợi.
- Luôn đo cả chi phí đọc lẫn chi phí INSERT/UPDATE/DELETE khi thêm function-based hoặc composite index.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — B-tree indexes, composite indexes, NULL values và index entries.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — NULL conditions, ORDER BY, CREATE INDEX và constraints.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing indexes, function-based indexes và bitmap indexes.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Optimizer statistics, access paths và execution plans.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_STATS và quản lý statistics.

Chi tiết access path, function-based index, bitmap index và composite unique key cần được đối chiếu theo đúng Oracle release. Hãy thử các tổ hợp NULL đại diện trên schema lab, thu thập statistics và xác nhận bằng execution plan trước khi áp dụng thiết kế vào bảng production.

