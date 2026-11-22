# DBMS_XPLAN.DISPLAY và DISPLAY_CURSOR

Oracle cung cấp package DBMS_XPLAN để trình bày execution plan theo định dạng dễ đọc. Hai hàm thường dùng nhất là DISPLAY và DISPLAY_CURSOR, nhưng chúng đọc dữ liệu từ hai nguồn khác nhau:

- DBMS_XPLAN.DISPLAY trình bày plan đã được ghi vào PLAN_TABLE, thường là kết quả của EXPLAIN PLAN.
- DBMS_XPLAN.DISPLAY_CURSOR trình bày plan của một SQL cursor trong library cache. Khi runtime statistics đã được thu thập, nó còn có thể hiển thị số hàng thực tế, số lần khởi chạy row source, buffer gets, reads và thời gian.

DISPLAY không chạy lại câu SQL. DISPLAY_CURSOR cũng không chạy lại câu SQL; nó đọc cursor đã có trong shared pool. Khi điều tra SQL chậm, cần biết SQL_ID, child cursor, plan hash, bind values và runtime statistics của đúng lần chạy.

Bài học trình bày EXPLAIN PLAN, PLAN_TABLE, hai hàm DBMS_XPLAN, format output, E-Rows/A-Rows/Starts, GATHER_PLAN_STATISTICS, cách tìm SQL_ID và child number, predicate, alias, outline, peeked binds, adaptive plan và quy trình điều tra.

Các ví dụ dùng Oracle Database 19c. Quyền truy cập V$ view và một số format option phụ thuộc phiên bản và quyền database; hãy đối chiếu DBMS_XPLAN Reference đúng release.

## 1. Execution plan là gì?

Execution plan là cây operation mà cost-based optimizer chọn để thực hiện SQL. Mỗi node biểu diễn một bước như table access, index access, join, sort, aggregation hoặc filter.

| Operation | Ý nghĩa |
| --- | --- |
| TABLE ACCESS FULL | Đọc toàn bộ table/segment hoặc phần được chọn |
| TABLE ACCESS BY INDEX ROWID | Lấy row từ table bằng ROWID tìm qua index |
| INDEX RANGE SCAN | Đọc một dải key trong index |
| INDEX UNIQUE SCAN | Tìm một key duy nhất trong index |
| NESTED LOOPS | Join bằng cách lặp outer rows và lookup inner rows |
| HASH JOIN | Join bằng hash table |
| SORT ORDER BY | Sắp xếp kết quả |
| HASH GROUP BY | Gom nhóm bằng hash |
| FILTER | Áp dụng điều kiện lọc |
| PARTITION RANGE ITERATOR | Duyệt các partition được chọn |

Plan thường hiển thị Id, Operation, Name, Rows, Bytes, Cost và Time. Cost là chi phí tương đối do optimizer ước lượng, không phải thời gian chạy tính bằng mili giây. Không so sánh cost giữa các SQL khác nhau như thể đó là số đo runtime tuyệt đối.

### 1.1. Hai nguồn plan

~~~text
SQL statement
    |
    +-- EXPLAIN PLAN
    |       |
    |       v
    |   PLAN_TABLE
    |       |
    |       v
    |   DBMS_XPLAN.DISPLAY
    |       |
    |       +-- Estimated plan
    |
    +-- Parse / execute SQL
            |
            v
        Library cache cursor
            |
            +-- V$SQL_PLAN
            +-- V$SQL_PLAN_STATISTICS_ALL
                    |
                    v
              DBMS_XPLAN.DISPLAY_CURSOR
                    |
                    +-- Cursor plan
                    +-- Runtime stats, nếu đã thu thập
~~~

DISPLAY trình bày plan từ PLAN_TABLE. DISPLAY_CURSOR trình bày plan của cursor trong library cache. Hai kết quả có thể khác nhau vì explain plan không thực thi câu SQL và không nhất thiết dùng cùng bind values hoặc session environment với lần chạy thực tế.

## 2. EXPLAIN PLAN và PLAN_TABLE

EXPLAIN PLAN yêu cầu optimizer tạo plan cho một câu SQL rồi ghi các dòng plan vào PLAN_TABLE. Nó không thực thi câu SELECT hoặc DML được explain.

### 2.1. Tạo PLAN_TABLE

Trong nhiều database, PLAN_TABLE đã có sẵn. Nếu chưa có, dùng script Oracle cung cấp từ SQL*Plus hoặc SQLcl:

~~~sql
@?/rdbms/admin/utlxplan.sql
~~~

Script tạo PLAN_TABLE trong schema hiện tại. Kiểm tra object trước khi chạy:

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name = 'PLAN_TABLE';
~~~

### 2.2. Chạy EXPLAIN PLAN

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'ROW413_DEMO'
FOR
SELECT employee_id, last_name, salary
FROM employees
WHERE department_id = 50;
~~~

Optimizer ghi plan vào PLAN_TABLE với STATEMENT_ID đã chỉ định. Dùng statement ID khác nhau để phân biệt nhiều plan trong cùng bảng.

### 2.3. Hiển thị bằng DBMS_XPLAN.DISPLAY

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        'PLAN_TABLE',
        'ROW413_DEMO',
        'TYPICAL'
    )
);
~~~

Tham số lần lượt là tên plan table, STATEMENT_ID và format. Nếu dùng PLAN_TABLE mặc định và không cần statement ID riêng:

~~~sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

DISPLAY đọc các dòng đã có trong PLAN_TABLE rồi định dạng thành văn bản. Nó không tự gọi EXPLAIN PLAN và không thực thi câu SQL.

### 2.4. Xem dữ liệu thô trong PLAN_TABLE

~~~sql
SELECT
    statement_id,
    id,
    parent_id,
    operation,
    options,
    object_owner,
    object_name,
    cardinality,
    cost
FROM plan_table
WHERE statement_id = 'ROW413_DEMO'
ORDER BY id;
~~~

PLAN_TABLE lưu cấu trúc plan dưới dạng quan hệ. DBMS_XPLAN.DISPLAY định dạng các dòng thành cây dễ đọc, kèm predicate và thông tin bổ sung.

### 2.5. Xóa plan cũ

~~~sql
DELETE FROM plan_table
WHERE statement_id = 'ROW413_DEMO';

COMMIT;
~~~

Chỉ xóa dòng thuộc statement ID của bạn. Không xóa toàn bộ PLAN_TABLE dùng chung trong schema nếu có người khác đang sử dụng.

## 3. Giới hạn của EXPLAIN PLAN và DISPLAY

Vì EXPLAIN PLAN không thực thi SQL, nó không có số hàng thực tế đã trả về, buffer gets hoặc elapsed time thực tế.

Plan explain có thể khác plan của cursor thực thi vì:
- Bind values và bind peeking.
- Adaptive cursor sharing tạo child cursor khác nhau.
- Session optimizer settings hoặc NLS khác.
- Schema/object resolution khác.
- Statistics thay đổi giữa thời điểm explain và execute.
- SQL profile, SQL patch, baseline hoặc optimizer environment khác.
- Adaptive plan và quyết định runtime.

DISPLAY phù hợp để xem plan dự kiến, kiểm tra access path và so sánh phương án trong môi trường kiểm thử. Khi điều tra một lần chạy thực tế, hãy ưu tiên DISPLAY_CURSOR của đúng SQL_ID và child cursor.

Ví dụ EXPLAIN PLAN có thể cho thấy INDEX RANGE SCAN với Rows = 100. Điều đó không chứng minh lần chạy thực tế chỉ đọc 100 hàng. Runtime có thể trả 500.000 hàng do bind value, skew hoặc dữ liệu đã thay đổi.

## 4. DBMS_XPLAN.DISPLAY_CURSOR

DISPLAY_CURSOR đọc execution plan từ cursor trong library cache. Đây thường là công cụ quan trọng hơn khi điều tra SQL đã chạy.

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => 'SQL_ID_HERE',
        cursor_child_no => 0,
        format          => 'TYPICAL'
    )
);
~~~

Các tham số:
- SQL_ID: định danh SQL cursor. NULL có thể yêu cầu plan của SQL gần nhất trong session hiện tại theo quy tắc của package.
- CURSOR_CHILD_NO: số child cursor cần hiển thị.
- FORMAT: mức chi tiết và các phần bổ sung của output.
- CON_ID: tham số container trong môi trường multitenant ở các release hỗ trợ.

Hãy dùng SQL_ID và child number rõ ràng khi điều tra production. Không giả định child number 0 luôn là cursor đã phục vụ request đang gặp lỗi.

### 4.1. Hiển thị cursor gần nhất

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL'
    )
);
~~~

Cách gọi này thuận tiện khi thử nghiệm trong một session riêng: chạy câu SQL mục tiêu rồi gọi DISPLAY_CURSOR ngay sau đó. Nếu thực hiện thêm truy vấn chẩn đoán khác trước khi gọi, khái niệm SQL gần nhất có thể không còn là câu SQL bạn muốn xem. Trong môi trường nhiều session, dùng SQL_ID/child number cụ thể an toàn hơn.

### 4.2. Tìm SQL_ID và child number

Nếu có quyền đọc V$SQL:

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    last_active_time,
    parsing_schema_name,
    sql_text
FROM v$sql
WHERE sql_text LIKE '%FROM EMPLOYEES%'
ORDER BY last_active_time DESC;
~~~

Điều kiện LIKE chỉ là cách tìm nhanh. Có thể có nhiều câu SQL chứa cùng đoạn text hoặc SQL_TEXT bị cắt. Với điều tra nghiêm túc, xác nhận SQL_ID bằng SQL text đầy đủ, module/action, parsing schema, thời điểm và session/request liên quan.

Sau khi xác định:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'abc123example',
        0,
        'TYPICAL'
    )
);
~~~

Thay SQL_ID và child number bằng giá trị thật. abc123example chỉ là placeholder.

### 4.3. Cursor có thể không còn trong shared pool

DISPLAY_CURSOR cần cursor còn khả dụng trong library cache. Cursor có thể bị aged out hoặc invalidated; khi đó không thể hiển thị từ V$SQL như trước. Nếu cần lịch sử lâu dài, xem AWR/ASH và các API DBMS_XPLAN tương ứng, đồng thời tuân thủ điều kiện sử dụng Diagnostics Pack theo hợp đồng/license của môi trường.

## 5. Thu thập actual row-source statistics

DISPLAY_CURSOR có thể trình bày actual execution statistics khi chúng đã được thu thập. Chỉ thêm format ALLSTATS LAST không tự làm cho mọi lần chạy trước đó có đủ A-Rows và buffer statistics.

### 5.1. GATHER_PLAN_STATISTICS hint

Thêm hint vào câu SQL cần đo:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       last_name,
       salary
FROM employees
WHERE department_id = 50;
~~~

Sau khi câu SQL thực thi xong, xem cursor:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Hint yêu cầu thu thập row-source execution statistics cho câu SQL đó. Đây thường là lựa chọn có phạm vi hẹp khi cần chẩn đoán một statement.

### 5.2. STATISTICS_LEVEL = ALL

Có thể bật ở session:

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

Sau khi chạy SQL, xem DISPLAY_CURSOR với ALLSTATS LAST. Khi hoàn tất thử nghiệm, khôi phục:

~~~sql
ALTER SESSION SET statistics_level = TYPICAL;
~~~

STATISTICS_LEVEL = ALL có thể tạo overhead và thu thập runtime stats cho nhiều câu SQL trong session. Không bật rộng trên production chỉ để kiểm tra một query nếu hint có thể đáp ứng nhu cầu.

### 5.3. ALLSTATS LAST

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

ALLSTATS yêu cầu các cột I/O và memory statistics; LAST tập trung vào lần thực thi gần nhất có statistics tương ứng. Output có thể bao gồm:
- E-Rows: số hàng optimizer ước lượng.
- A-Rows: số hàng thực tế row source trả ra.
- Starts: số lần row source được khởi chạy.
- A-Time: thời gian được báo cáo cho operation.
- Buffers: logical reads.
- Reads: physical reads được ghi nhận.
- OMem, 1Mem, Used-Mem: thông tin bộ nhớ cho operation phù hợp.

Nếu không thu thập runtime stats, các cột actual có thể trống hoặc không xuất hiện. Hãy chạy lại câu SQL với GATHER_PLAN_STATISTICS hoặc session statistics_level phù hợp.

LAST chỉ hiển thị thống kê của lần thực thi gần nhất mà cursor giữ. Nó không phải trung bình của mọi lần chạy và không phải lịch sử đầy đủ theo từng request. Nếu nhiều session dùng cùng cursor, hãy diễn giải last execution thận trọng.

## 6. Đọc E-Rows, A-Rows và Starts

Đây là phần có giá trị nhất khi tìm nguyên nhân optimizer ước lượng sai.

| Cột | Ý nghĩa |
| --- | --- |
| E-Rows | Cardinality optimizer ước lượng |
| A-Rows | Số hàng thực tế row source trả ra |
| Starts | Số lần operation được khởi chạy |
| A-Time | Thời gian operation theo runtime statistics |
| Buffers | Logical block gets |
| Reads | Physical reads được ghi nhận |

### 6.1. Ước lượng gần đúng

~~~text
E-Rows = 100
A-Rows = 105
Starts = 1
~~~

Ước lượng gần với thực tế. Không cần tìm cách làm E-Rows bằng tuyệt đối A-Rows; statistics là ước lượng và sai số nhỏ có thể chấp nhận.

### 6.2. Ước lượng lệch lớn

~~~text
E-Rows = 10
A-Rows = 500000
Starts = 1
~~~

Optimizer nghĩ row source rất nhỏ nhưng thực tế trả nửa triệu hàng. Điều này có thể khiến nested loops được chọn trong khi hash join hoặc full scan sẽ phù hợp hơn.

Hãy điều tra:
- Column statistics và histogram.
- Data skew.
- Correlation giữa nhiều predicate.
- Bind peeking và bind sensitivity.
- Function trên cột hoặc implicit conversion.
- Statistics stale/missing.
- Predicate selectivity và cardinality feedback.

### 6.3. Starts ảnh hưởng cách đọc A-Rows

Với nested loops, một operation inner có thể chạy nhiều lần. Khi Starts lớn hơn 1, A-Rows thường là tổng số hàng operation trả ra qua các lần khởi chạy. Muốn hiểu số hàng trung bình mỗi lần, cần xem xét A-Rows/Starts và cấu trúc operation. Đừng so sánh E-Rows và A-Rows máy móc khi Starts khác 1.

A-Rows ở mỗi node là số hàng do node đó trả cho parent, không phải luôn là số hàng client nhận cuối cùng. Filter, join, aggregation và sort có thể làm số hàng thay đổi qua từng node. Đọc cây plan từ row source phía dưới lên để hiểu dữ liệu được tạo ra và lọc như thế nào.

## 7. Các format phổ biến

| Format | Nội dung |
| --- | --- |
| BASIC | Thông tin tối thiểu của plan |
| TYPICAL | Thông tin plan thường cần, là lựa chọn mặc định phổ biến |
| SERIAL | Chi tiết phù hợp cho plan chạy serial |
| ALL | Nhiều thông tin hơn, gồm các phần chi tiết bổ sung |

Có thể thêm modifier bằng dấu +:

| Modifier | Mục đích |
| --- | --- |
| +PREDICATE | Hiển thị access/filter predicates |
| +ALIAS | Hiển thị alias/query block |
| +OUTLINE | Hiển thị outline hints của plan |
| +NOTE | Hiển thị ghi chú optimizer |
| +PEEKED_BINDS | Hiển thị bind values đã được peek khi parse nếu có |
| +PROJECTION | Hiển thị cột/biểu thức được project |
| +PARTITION | Hiển thị thông tin partition pruning |
| +PARALLEL | Hiển thị thông tin parallel execution |
| +REMOTE | Hiển thị thông tin remote SQL/database link |
| +IOSTATS | Hiển thị I/O runtime statistics nếu đã thu thập |
| +MEMSTATS | Hiển thị memory statistics nếu có |
| +ALLSTATS | Yêu cầu I/O và memory statistics |
| +ADAPTIVE | Hiển thị thông tin adaptive plan theo hỗ trợ của release |

Ví dụ:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'your_sql_id',
        0,
        'ALLSTATS LAST +PREDICATE +ALIAS +NOTE'
    )
);
~~~

Chọn format theo câu hỏi cần trả lời. Không cần dùng ALL cho mọi lần kiểm tra vì output dài và có thể làm phần quan trọng khó nhìn.

## 8. Predicate Information

Predicate Information cho biết điều kiện nào được dùng để truy cập object và điều kiện nào được lọc sau khi đọc.

~~~text
access("E"."EMPLOYEE_ID"=100)
filter("E"."STATUS"='ACTIVE')
~~~

ACCESS predicate thường tham gia định vị dữ liệu qua index/partition hoặc access path. FILTER predicate được áp dụng để loại hàng sau một bước truy cập hoặc ở operation tương ứng. Một điều kiện xuất hiện trong FILTER không nhất thiết là xấu; hãy xem operation, số hàng, index và dữ liệu thực tế.

### 8.1. Implicit conversion

Nếu cột NUMBER được so sánh với string bind, Oracle có thể thực hiện implicit conversion. Predicate có thể xuất hiện dưới dạng hàm trên cột, làm ảnh hưởng khả năng dùng index hoặc cardinality estimate.

~~~sql
SELECT *
FROM employees
WHERE employee_id = :p_employee_id;
~~~

Ứng dụng nên bind :p_employee_id dưới kiểu NUMBER thay vì truyền chuỗi số rồi dựa vào implicit conversion.

### 8.2. Access và filter

Khi đọc plan, kiểm tra:
- Index có dùng đúng cột đầu tiên của composite index không?
- Predicate có bị bọc trong function hoặc implicit conversion không?
- Điều kiện có được đẩy xuống gần table access không?
- Partition pruning có xảy ra không?
- A-Rows sau filter có hợp lý không?

Không tạo index chỉ vì thấy một predicate. Cần cân nhắc selectivity, DML overhead, clustering factor và workload tổng thể.

## 9. Alias, query block và outline

### 9.1. +ALIAS

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL +ALIAS'
    )
);
~~~

Alias giúp xác định operation thuộc table alias hoặc query block nào, đặc biệt trong SQL có nhiều subquery, view merging và join nhiều bảng.

### 9.2. +OUTLINE

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL +OUTLINE'
    )
);
~~~

Outline hiển thị hint/định hướng cần thiết để tái tạo plan theo optimizer context tương ứng. Đây là thông tin chẩn đoán, không phải lời khuyên tự động sao chép toàn bộ hint vào SQL production.

### 9.3. +NOTE

NOTE có thể cho biết dynamic statistics, SQL profile, SQL plan baseline, adaptive plan hoặc thông tin optimizer khác được áp dụng. Đọc NOTE để hiểu plan được hình thành trong bối cảnh nào.

## 10. Bind variables và child cursor

Một SQL_ID có thể có nhiều child cursor. Oracle tạo child cursor khác nhau khi cần plan hoặc execution environment khác nhau, chẳng hạn bind sensitivity, optimizer environment, object metadata hoặc privilege differences.

### 10.1. Liệt kê child cursor

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    is_bind_sensitive,
    is_bind_aware,
    last_active_time
FROM v$sql
WHERE sql_id = :p_sql_id
ORDER BY child_number;
~~~

Mỗi child number có thể có plan hash khác nhau. Khi điều tra, phải chọn child cursor đã phục vụ request cần phân tích.

### 10.2. Xem plan của từng child

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        1,
        'ALLSTATS LAST +PEEKED_BINDS +NOTE'
    )
);
~~~

Thay 1 bằng CHILD_NUMBER đã xác định. Không giả định child 0 là child duy nhất.

### 10.3. Peeked binds

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'TYPICAL +PEEKED_BINDS'
    )
);
~~~

PEEKED_BINDS có thể hiển thị giá trị bind mà optimizer đã peek lúc hard parse, nếu có. Giá trị đó không nhất thiết là giá trị của mọi execution sau này. Không nhầm peeked bind với bind values của lần chạy gần nhất.

Bind values có thể chứa dữ liệu nhạy cảm. Hãy hạn chế quyền truy cập và che/redact output trước khi chia sẻ log hoặc plan.

### 10.4. Adaptive cursor sharing

Nếu cùng một SQL_ID được chạy với bind values có selectivity rất khác nhau, Oracle có thể tạo nhiều child cursor/plan để phục vụ các nhóm bind khác nhau. Vì vậy một lần DISPLAY_CURSOR với child 0 chưa đủ để kết luận mọi request đều dùng plan đó.

## 11. Adaptive plan và parallel execution

Oracle có thể tạo adaptive plan với nhiều lựa chọn runtime. Một số nhánh được chọn hoặc loại bỏ khi thực thi dựa trên thông tin thực tế. Format +ADAPTIVE và NOTE giúp quan sát thông tin adaptive theo phiên bản.

Với parallel query, plan có thể chứa PX SEND/PX RECEIVE, producer/consumer và operation chạy ở nhiều process. A-Rows, Starts, Buffers và thời gian cần được diễn giải theo cấu trúc parallel plan; không cộng hoặc so sánh tùy tiện các con số giữa coordinator và parallel slaves.

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +PARALLEL +ADAPTIVE +NOTE'
    )
);
~~~

Nếu query chạy song song và cần phân tích sâu theo từng SQL Monitor execution, dùng công cụ monitoring phù hợp và xác nhận quyền/license trước khi truy cập các tính năng Diagnostics/Tuning Pack.

## 12. Quyền cần thiết

DISPLAY dùng PLAN_TABLE trong schema và quyền truy cập phù hợp. DISPLAY_CURSOR cần đọc thông tin cursor/runtime từ các dynamic performance views như V$SQL_PLAN, V$SQL_PLAN_STATISTICS_ALL và V$SQL.

Tài khoản ứng dụng thông thường có thể không được cấp quyền trực tiếp trên các V$ view. DBA có thể cấp các quyền SELECT cụ thể theo chính sách bảo mật.

~~~sql
GRANT SELECT ON V_$SQL TO plan_reader;
GRANT SELECT ON V_$SQL_PLAN TO plan_reader;
GRANT SELECT ON V_$SQL_PLAN_STATISTICS_ALL TO plan_reader;
~~~

Tên object nền thường có tiền tố V_$; synonym công khai có tên V$. Việc cấp quyền phải do DBA thực hiện và chỉ cấp view cần thiết. Không cấp SELECT ANY DICTIONARY hoặc quyền DBA chỉ để người dùng xem một execution plan.

Trong môi trường multitenant, cần xác định đúng container/PDB và phạm vi view. DISPLAY_CURSOR có tham số CON_ID ở các release hỗ trợ.

## 13. Quy trình điều tra SQL chậm

### Bước 1: Xác định statement

- Lấy SQL_ID từ ứng dụng, trace hoặc V$SQL.
- Xác định child number và plan hash value.
- Ghi nhận parsing schema, module/action và thời điểm.
- Xác nhận SQL text đầy đủ.

### Bước 2: Lấy cursor plan

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'TYPICAL +PREDICATE +ALIAS +NOTE'
    )
);
~~~

### Bước 3: Thu thập runtime stats nếu cần

Nếu có thể tái hiện trong môi trường thử nghiệm, chạy lại statement với GATHER_PLAN_STATISTICS rồi hiển thị:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
~~~

Không thêm hint vào production SQL đang phục vụ người dùng chỉ để chẩn đoán nếu chưa đánh giá overhead và quy trình triển khai.

### Bước 4: Tìm điểm lệch cardinality

- So sánh E-Rows và A-Rows ở từng row source.
- Xem Starts, nhất là inner side của nested loops.
- Tìm operation đầu tiên có chênh lệch lớn.
- Kiểm tra predicate, histogram, stale stats và bind values.
- Kiểm tra join method/order có bị ảnh hưởng bởi sai lệch đó không.

### Bước 5: Xem chi phí thực tế

- Buffers và Reads cho biết hoạt động I/O.
- A-Time cho biết thời gian theo operation trong thống kê.
- OMem/Used-Mem có thể gợi ý hash/sort spill hoặc memory pressure.
- Kiểm tra elapsed time ở cấp SQL và số lần thực thi.

### Bước 6: Đưa ra giả thuyết rồi thử nghiệm

Ví dụ:
- Histogram thiếu khiến predicate skew bị ước lượng sai.
- Bind peeking tạo plan phù hợp cho một giá trị nhưng không phù hợp cho giá trị khác.
- Function trên cột làm mất khả năng dùng index mong đợi.
- Join order không tốt vì cardinality ở một nhánh sai.
- Table/index statistics cũ sau bulk load.

Thay đổi một yếu tố mỗi lần, đo lại plan/runtime và giữ khả năng rollback. Không thêm hint, index hoặc gather stats hàng loạt chỉ vì một operation trông lạ.

## 14. Lab: DISPLAY và DISPLAY_CURSOR

Lab dùng schema riêng. Nếu database có HR.EMPLOYEES, có thể dùng bảng đó; nếu không, tạo bảng lab.

### 14.1. Tạo dữ liệu mẫu

~~~sql
CREATE TABLE lab_plan_employees (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER,
    status VARCHAR2(20),
    salary NUMBER(12, 2)
);

INSERT INTO lab_plan_employees
SELECT
    LEVEL,
    MOD(LEVEL, 20),
    CASE WHEN MOD(LEVEL, 100) = 0 THEN 'PENDING' ELSE 'ACTIVE' END,
    MOD(LEVEL, 10000) + 1000
FROM dual
CONNECT BY LEVEL <= 50000;

COMMIT;

CREATE INDEX lab_plan_emp_dept_ix
ON lab_plan_employees(department_id);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_PLAN_EMPLOYEES',
        cascade => TRUE
    );
END;
/
~~~

### 14.2. EXPLAIN PLAN và DISPLAY

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'LAB_PLAN_01'
FOR
SELECT employee_id, salary
FROM lab_plan_employees
WHERE department_id = 5;
~~~

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        'PLAN_TABLE',
        'LAB_PLAN_01',
        'TYPICAL +PREDICATE'
    )
);
~~~

Quan sát estimated Rows, access path và predicate. Câu SQL chưa được thực thi bởi EXPLAIN PLAN.

### 14.3. Chạy SQL và lấy cursor plan

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       salary
FROM lab_plan_employees
WHERE department_id = 5;
~~~

Ngay sau đó:

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

So sánh E-Rows và A-Rows. Nếu không thấy runtime columns, xác nhận hint được áp dụng và cursor được giữ trong library cache.

### 14.4. Tìm SQL_ID

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    last_active_time,
    sql_text
FROM v$sql
WHERE sql_text LIKE '%LAB_PLAN_EMPLOYEES%'
ORDER BY last_active_time DESC;
~~~

Ghi SQL_ID và CHILD_NUMBER của câu SELECT mục tiêu. Sau đó gọi DISPLAY_CURSOR với hai giá trị đó để tránh phụ thuộc cursor gần nhất.

### 14.5. Xem plan với nhiều format

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +PEEKED_BINDS +NOTE +OUTLINE'
    )
);
~~~

So sánh output với TYPICAL. Ghi lại phần nào hữu ích cho điều tra và phần nào không cần trong báo cáo ngắn.

### 14.6. Thử bind variable

~~~sql
VARIABLE p_department_id NUMBER
EXEC :p_department_id := 5

SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       salary
FROM lab_plan_employees
WHERE department_id = :p_department_id;
~~~

Xem DISPLAY_CURSOR và +PEEKED_BINDS nếu có. Thử một giá trị khác rồi xem SQL_ID/child cursor. Quan sát liệu Oracle có dùng child cursor khác hay plan hash khác không; kết quả phụ thuộc optimizer environment và dữ liệu.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| DISPLAY không trả plan | Chưa chạy EXPLAIN PLAN hoặc sai STATEMENT_ID/table | Chạy explain và kiểm tra PLAN_TABLE |
| DISPLAY_CURSOR không tìm thấy cursor | SQL_ID sai hoặc cursor đã aged out | Tìm lại V$SQL hoặc dùng lịch sử được phép |
| DISPLAY và DISPLAY_CURSOR khác nhau | Explain không phải execution cursor thực tế | Điều tra cursor SQL_ID/child number |
| Không có A-Rows/Buffers | Chưa thu thập row-source stats | Dùng GATHER_PLAN_STATISTICS hoặc STATISTICS_LEVEL=ALL |
| Xem nhầm child cursor | SQL_ID có nhiều child | Lấy CHILD_NUMBER đúng request |
| E-Rows khác A-Rows lớn | Cardinality estimate sai hoặc Starts > 1 | Xem predicate, histogram, bind và Starts |
| Plan cost thấp nhưng query chậm | Cost là ước lượng, không phải elapsed time | Xem actual stats và workload |
| Peeked bind khác bind hiện tại | Peeked bind thuộc thời điểm parse | Đối chiếu bind của request và child cursor |
| Predicate có implicit conversion | Bind/cột khác datatype | Bind đúng kiểu, kiểm tra plan predicate |
| DISPLAY_CURSOR báo thiếu quyền | Thiếu quyền đọc V$ views | Nhờ DBA cấp quyền SELECT tối thiểu |
| ALLSTATS LAST không phản ánh mọi request | LAST không phải lịch sử mọi execution | Theo dõi đúng execution hoặc dùng công cụ phù hợp |
| Plan thay đổi sau statistics gather | Cursor invalidation/hard parse và stats mới | Xem plan hash, note, invalidation và stats history |
| Output quá dài | Format ALL và quá nhiều modifier | Dùng TYPICAL rồi thêm modifier theo câu hỏi |

## 16. Checklist đọc execution plan

Khi mở một plan, lần lượt xác định:

1. Đây là plan từ PLAN_TABLE hay cursor library cache?
2. Nếu là cursor, SQL_ID và child number có đúng request không?
3. Plan hash value là gì?
4. Có runtime row-source statistics không?
5. Node nào có E-Rows lệch A-Rows lớn nhất?
6. Starts có làm thay đổi cách so sánh cardinality không?
7. Predicate nào là ACCESS, predicate nào là FILTER?
8. Có implicit conversion hoặc function trên cột không?
9. Join method/order có hợp với số hàng thực tế không?
10. Partition pruning và parallel operations có đúng mong đợi không?
11. Statistics, histogram và bind values có phù hợp không?
12. Có SQL profile, baseline, adaptive plan hoặc note nào ảnh hưởng plan không?

Plan là bằng chứng kỹ thuật để hình thành giả thuyết. Hãy kết hợp với elapsed time, buffer gets, application latency và workload thực tế trước khi thay đổi schema hoặc SQL.

## 17. Bài tập thực hành

Sử dụng LAB_PLAN_EMPLOYEES trong mục 14.

### Bài 1 — DISPLAY

Chạy EXPLAIN PLAN với một truy vấn lọc theo DEPARTMENT_ID. Dùng DISPLAY với TYPICAL và +PREDICATE. Ghi operation tree và estimated rows.

### Bài 2 — DISPLAY_CURSOR

Chạy cùng truy vấn với GATHER_PLAN_STATISTICS. Dùng DISPLAY_CURSOR với ALLSTATS LAST. So sánh E-Rows và A-Rows.

### Bài 3 — SQL_ID và child number

Tìm SQL_ID, CHILD_NUMBER và PLAN_HASH_VALUE trong V$SQL. Hiển thị cursor bằng ID cụ thể thay vì NULL.

### Bài 4 — Bind variable

Chạy cùng SQL với các bind values khác nhau. Xem +PEEKED_BINDS và child cursors. Giải thích vì sao một SQL_ID có thể có nhiều child.

### Bài 5 — Predicate

Viết một điều kiện có implicit conversion có chủ đích trong lab, xem Predicate Information rồi sửa bind/datatype. So sánh plan.

### Bài 6 — Cardinality

Tạo dữ liệu skew trên STATUS. Gather statistics, chạy truy vấn cho giá trị phổ biến và hiếm. So sánh E-Rows/A-Rows và histogram.

### Bài 7 — Format modifiers

So sánh BASIC, TYPICAL, ALL, ALLSTATS LAST +ALIAS +NOTE. Ghi lại câu hỏi nào mỗi format giúp trả lời.

### Bài 8 — Plan investigation

Chọn một truy vấn lab có nhiều operation. Xác định node đầu tiên có chênh lệch cardinality lớn, tìm nguyên nhân khả dĩ và đề xuất một thay đổi có thể kiểm chứng.

## 18. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP TABLE lab_plan_employees PURGE;
~~~

Nếu tạo STATEMENT_ID trong PLAN_TABLE, xóa đúng dòng lab của bạn:

~~~sql
DELETE FROM plan_table
WHERE statement_id = 'LAB_PLAN_01';
COMMIT;
~~~

Không xóa plan của người dùng khác và không dọn PLAN_TABLE dùng chung một cách toàn cục.

## Tổng kết

DBMS_XPLAN.DISPLAY trình bày plan đã được EXPLAIN PLAN ghi vào PLAN_TABLE. Đây là estimated plan và không thực thi câu SQL. DBMS_XPLAN.DISPLAY_CURSOR đọc plan của cursor trong library cache; khi row-source statistics được thu thập bằng GATHER_PLAN_STATISTICS hoặc STATISTICS_LEVEL=ALL, output có thể cho thấy A-Rows, Starts, A-Time, Buffers, Reads và memory.

Khi điều tra SQL thực tế, hãy xác định đúng SQL_ID và child number, rồi dùng DISPLAY_CURSOR với format phù hợp. So sánh E-Rows và A-Rows, lưu ý Starts, đọc Predicate Information, alias, outline, note và bind values. Cost không phải thời gian chạy; ALLSTATS LAST không phải lịch sử của mọi request. Dùng plan cùng runtime metrics, statistics, bind context và workload để hình thành giả thuyết, thử nghiệm thay đổi và xác nhận kết quả.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html) — DISPLAY, DISPLAY_CURSOR, format và plan output.
- [Oracle Database SQL Tuning Guide — Generating and Displaying Execution Plans (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html) — EXPLAIN PLAN và cách đọc execution plan.
- [Oracle Database Reference — V$SQL_PLAN (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_PLAN.html) — plan rows trong library cache.
- [Oracle Database Reference — V$SQL_PLAN_STATISTICS_ALL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_PLAN_STATISTICS_ALL.html) — estimated và runtime row-source statistics.
- [Oracle Database Reference — V$SQL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html) — SQL_ID, child cursor, executions và plan hash.
- [Oracle Database SQL Tuning Guide — Adaptive Query Optimization (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-optimizer-concepts.html) — adaptive plans và cardinality feedback.
+
+Khi triển khai trên Oracle release khác 19c, hãy đối chiếu DBMS_XPLAN Reference, SQL Tuning Guide và Data Dictionary Reference đúng phiên bản, đặc biệt DISPLAY_CURSOR parameters, format modifiers, runtime statistics và multitenant CON_ID.
