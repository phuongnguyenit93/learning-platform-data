# EXPLAIN PLAN và khác biệt với kế hoạch đã thực thi

Oracle cung cấp nhiều cách xem execution plan. Hai cách thường được đặt cạnh nhau là **EXPLAIN PLAN** và **DBMS_XPLAN.DISPLAY_CURSOR**. Chúng có liên quan nhưng trả lời hai câu hỏi khác nhau:

- **EXPLAIN PLAN** yêu cầu optimizer phân tích một câu SQL và lưu kế hoạch dự kiến vào PLAN_TABLE. Câu SQL được giải thích không được thực thi.
- **DBMS_XPLAN.DISPLAY_CURSOR** đọc plan của một cursor SQL đã được parse/execute và còn có trong library cache. Khi thu thập runtime row-source statistics, plan này có thể cho biết số hàng thực tế, số lần bắt đầu operation, thời gian và I/O quan sát được.

Vì vậy, EXPLAIN PLAN hữu ích khi cần xem nhanh một phương án dự kiến, còn cursor plan là bằng chứng quan trọng hơn khi điều tra câu SQL đã chạy trong ứng dụng. Hai plan có thể khác nhau vì bind values, child cursor, optimizer environment, statistics, schema resolution, adaptive behavior và nhiều yếu tố runtime khác.

Một quy trình chẩn đoán đáng tin cậy thường là: xác định đúng SQL_ID và child cursor, thu thập plan thực tế cùng runtime statistics, so sánh estimated rows với actual rows, sau đó dùng EXPLAIN PLAN như công cụ bổ sung để thử một biến thể SQL hoặc môi trường parse khác.

## 1. Execution plan trong Oracle

### 1.1. Plan là gì?

Execution plan mô tả cách Oracle dự định hoặc đã thực hiện một câu SQL. Plan được biểu diễn thành các operation/row source có quan hệ cha-con. Các operation thường gặp:

- TABLE ACCESS FULL: đọc bảng theo full scan.
- TABLE ACCESS BY INDEX ROWID: lấy hàng từ bảng bằng ROWID thu được từ index.
- INDEX RANGE SCAN, INDEX UNIQUE SCAN, INDEX FULL SCAN: các kiểu truy cập index.
- NESTED LOOPS, HASH JOIN, MERGE JOIN: các phương pháp join.
- SORT ORDER BY, SORT GROUP BY, HASH GROUP BY: sắp xếp hoặc gom nhóm.
- FILTER: áp dụng điều kiện lọc.
- PARTITION RANGE ITERATOR: điều phối truy cập partition.

Plan cũng có thể hiển thị predicate, projection, partition pruning, parallel execution, temporary space và thông tin memory tùy loại operation và format.

### 1.2. Plan được tổ chức thành cây

Ví dụ:

```sql
SELECT e.employee_id, d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE d.location_id = 1700;
```

Một plan minh họa:

```text
SELECT STATEMENT
  HASH JOIN
    TABLE ACCESS FULL DEPARTMENTS
    TABLE ACCESS FULL EMPLOYEES
```

Các operation con tạo row source đầu vào cho operation cha. Cách đọc plan cần xét quan hệ cha-con và thứ tự xử lý, không đơn giản đọc các dòng từ trên xuống như một danh sách lệnh tuần tự.

### 1.3. Plan có thể là dự kiến hoặc đã thực thi

Một plan do EXPLAIN PLAN tạo ra là kết quả optimization cho câu SQL trong môi trường của thao tác explain. Một cursor plan là plan gắn với cursor thực tế trong shared pool/library cache. Khi cursor đã chạy và runtime statistics được thu thập, ta có thêm dữ liệu thực tế để đánh giá.

Plan được lưu trong cache có thể đã được parse nhưng chưa chạy hết, đã chạy nhiều lần hoặc được chia thành nhiều child cursor. Luôn xác định đúng cursor và child number khi điều tra.

## 2. EXPLAIN PLAN hoạt động thế nào?

### 2.1. Cú pháp cơ bản

```sql
EXPLAIN PLAN FOR
SELECT employee_id, last_name
FROM employees
WHERE department_id = 50;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Lệnh EXPLAIN PLAN FOR yêu cầu Oracle parse/optimize câu SQL và lưu plan vào PLAN_TABLE. Câu SELECT được giải thích không chạy để trả dữ liệu. Sau đó DBMS_XPLAN.DISPLAY định dạng nội dung plan đã lưu.

### 2.2. Gán STATEMENT_ID

Nếu cần giữ nhiều plan trong PLAN_TABLE, đặt statement identifier:

```sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'EMP_DEPT_50'
FOR
SELECT employee_id, last_name
FROM employees
WHERE department_id = 50;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        table_name   => 'PLAN_TABLE',
        statement_id => 'EMP_DEPT_50',
        format       => 'TYPICAL'
    )
);
```

STATEMENT_ID giúp phân biệt các lần explain. Có thể thêm timestamp hoặc tên thử nghiệm trong identifier theo giới hạn độ dài và quy ước của PLAN_TABLE.

### 2.3. PLAN_TABLE

PLAN_TABLE là nơi chứa các dòng mô tả plan được tạo bởi EXPLAIN PLAN. Oracle cung cấp script/tài nguyên để tạo cấu trúc này; trong các phiên bản hiện đại, người dùng thường có thể sử dụng PLAN_TABLE và synonym tương ứng theo cài đặt database.

Một số cột thường gặp:

- STATEMENT_ID: định danh lần explain.
- PLAN_ID: định danh plan.
- OPERATION, OPTIONS: loại operation và biến thể.
- OBJECT_OWNER, OBJECT_NAME, OBJECT_TYPE: object liên quan.
- ID, PARENT_ID: cấu trúc cây plan.
- COST, CARDINALITY, BYTES: ước lượng optimizer.
- ACCESS_PREDICATES, FILTER_PREDICATES: điều kiện truy cập/lọc.
- TEMP_SPACE: ước lượng temporary space trong các operation phù hợp.

Không nên dựa vào việc tự đọc PLAN_TABLE thô nếu DBMS_XPLAN có thể trình bày rõ hơn. Cấu trúc PLAN_TABLE có thể thay đổi giữa các release.

### 2.4. Xem plan trong SQL*Plus hoặc SQLcl

Sau EXPLAIN PLAN:

```sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Hoặc hiển thị statement cụ thể:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        'PLAN_TABLE',
        'EMP_DEPT_50',
        'BASIC +PREDICATE'
    )
);
```

BASIC hiển thị phần cốt lõi; +PREDICATE bổ sung điều kiện access/filter. Có thể dùng TYPICAL hoặc ALL khi cần nhiều thông tin hơn.

### 2.5. Dọn các plan thử nghiệm

PLAN_TABLE có thể tích lũy nhiều statement nếu dùng STATEMENT_ID khác nhau. Xóa đúng các dòng thuộc thử nghiệm của mình:

```sql
DELETE FROM plan_table
WHERE statement_id = 'EMP_DEPT_50';
COMMIT;
```

Chỉ xóa các dòng do phiên làm việc của mình tạo và đúng statement identifier. Trong môi trường nhiều người dùng, không xóa toàn bộ PLAN_TABLE tùy tiện.

## 3. EXPLAIN PLAN không thực thi câu SQL

### 3.1. Không có A-Rows của lần chạy thật

EXPLAIN PLAN cung cấp các ước lượng như cardinality, cost và bytes. Vì câu SQL mục tiêu không được thực thi, nó không thể cung cấp số hàng thực tế đã trả, elapsed time thực tế hoặc buffer gets của lần chạy đó.

Plan explain thông thường có E-Rows/ước lượng nhưng không có A-Rows runtime của câu SQL mục tiêu.

### 3.2. Không đo thời gian query

Thời gian chạy của lệnh EXPLAIN PLAN chỉ phản ánh công việc parse/optimization và lưu plan, không phải thời gian thực thi câu SQL được giải thích. Không dùng elapsed time của EXPLAIN PLAN để kết luận query nhanh hay chậm.

### 3.3. Không tạo tác động DML của câu được giải thích

Ví dụ:

```sql
EXPLAIN PLAN FOR
UPDATE orders
SET status_code = 'CLOSED'
WHERE order_date < DATE '2025-01-01';
```

Lệnh này không cập nhật các hàng trong ORDERS. Nó chỉ giải thích kế hoạch dự kiến cho UPDATE. Tuy nhiên, EXPLAIN PLAN là một thao tác riêng có thể ghi plan vào PLAN_TABLE; thao tác explain không thay thế việc kiểm thử DML trên dữ liệu an toàn.

### 3.4. Câu lệnh có thể vẫn cần parse và quyền

Không thực thi câu SQL không có nghĩa Oracle bỏ qua kiểm tra cú pháp, tên object và quyền cần thiết để giải thích. Một câu SQL sai cú pháp hoặc tham chiếu object không hợp lệ vẫn có thể thất bại ở bước parse/optimization.

### 3.5. Không dùng EXPLAIN PLAN để kiểm tra kết quả nghiệp vụ

EXPLAIN PLAN không cho biết câu SELECT trả những hàng nào, DML tác động bao nhiêu hàng hoặc constraint có bị vi phạm khi chạy hay không. Các câu hỏi đó cần thực thi có kiểm soát và quan sát kết quả thực tế.

## 4. DBMS_XPLAN.DISPLAY và DISPLAY_CURSOR

### 4.1. DISPLAY

DBMS_XPLAN.DISPLAY đọc plan đã lưu trong PLAN_TABLE:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        table_name   => 'PLAN_TABLE',
        statement_id => 'EMP_DEPT_50',
        format       => 'TYPICAL'
    )
);
```

Nguồn dữ liệu của DISPLAY là plan table. Nó không tự tìm cursor đã chạy trong library cache.

### 4.2. DISPLAY_CURSOR

DBMS_XPLAN.DISPLAY_CURSOR hiển thị plan của cursor trong library cache:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => '0123456789abc',
        cursor_child_no => 0,
        format          => 'TYPICAL'
    )
);
```

SQL_ID và child number ở trên chỉ là placeholder minh họa. Thay bằng giá trị lấy từ cursor thực tế.

### 4.3. Cursor gần nhất trong session

Trong lab đơn giản, có thể chạy query cần xem rồi ngay sau đó gọi:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL'
    )
);
```

Hai tham số NULL yêu cầu Oracle chọn cursor gần nhất phù hợp trong session theo semantics của API. Trong môi trường có nhiều SQL xen kẽ, cách an toàn hơn là lấy SQL_ID/child number rõ ràng từ V$SQL hoặc instrumentation, tránh nhầm cursor.

### 4.4. DISPLAY_AWR

DBMS_XPLAN.DISPLAY_AWR có thể hiển thị plan được lưu trong Automatic Workload Repository khi có license/quyền và dữ liệu AWR phù hợp. AWR plan history hữu ích để xem plan lịch sử, nhưng không nhất thiết có runtime row-source statistics đầy đủ cho mỗi execution.

Không nhầm plan AWR với plan đang được thực thi ngay lúc này trong library cache.

### 4.5. Quyền truy cập

Đọc plan cursor có thể cần quyền xem các dynamic performance views và catalog metadata liên quan. DBMS_XPLAN.DISPLAY từ PLAN_TABLE và DISPLAY_CURSOR từ shared pool có phạm vi quyền khác nhau. DBA nên cấp đúng quyền tối thiểu cho người điều tra thay vì cấp quyền quản trị rộng không cần thiết.

## 5. Plan thực thi và runtime statistics

### 5.1. Vì sao cần runtime statistics?

Một plan cursor có thể cho thấy operation và estimate, nhưng muốn biết estimate có đúng không thì cần actual row-source statistics. Oracle có thể thu thập thông tin runtime như:

- Số lần operation bắt đầu (Starts).
- Số hàng thực tế (A-Rows).
- Thời gian operation (A-Time) khi được thu thập.
- Logical I/O (Buffers).
- Physical reads (Reads).
- Memory work area (OMem, 1Mem, Used-Mem) ở operation phù hợp.

Thông tin có sẵn phụ thuộc cách thu thập, loại cursor và format DBMS_XPLAN.

### 5.2. GATHER_PLAN_STATISTICS

Có thể thêm hint để thu thập row-source statistics cho một câu SQL:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id, last_name
FROM employees
WHERE department_id = 50;
```

Sau khi câu SQL thực thi, xem plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
```

ALLSTATS LAST yêu cầu hiển thị thống kê I/O/memory/row-source cho lần thực thi gần nhất được ghi nhận, nếu có dữ liệu tương ứng. Nếu chưa thu thập runtime stats, cột A-Rows có thể không có hoặc không hữu ích.

### 5.3. STATISTICS_LEVEL = ALL

Trong session lab, có thể bật:

```sql
ALTER SESSION SET STATISTICS_LEVEL = ALL;
```

Setting này yêu cầu thu thập thêm statistics runtime cho các statement phù hợp trong session. Nó có thể tăng overhead, nên chỉ bật trong phạm vi và thời gian cần thiết. Sau thử nghiệm, khôi phục setting ban đầu:

```sql
ALTER SESSION SET STATISTICS_LEVEL = TYPICAL;
```

Nếu session ban đầu có setting khác, hãy đọc và khôi phục đúng giá trị cũ thay vì mặc định TYPICAL.

### 5.4. A-Rows không có nghĩa là số hàng cuối cùng của query

A-Rows xuất hiện ở từng operation. Một operation scan có thể đọc nhiều hàng, filter loại bớt, join tạo số hàng khác và aggregation tiếp tục giảm số hàng. Phải đọc A-Rows ở đúng row source và đúng quan hệ cha-con.

### 5.5. Starts ảnh hưởng cách so sánh

Operation bên trong nested loops có thể được chạy nhiều lần. E-Rows thường là ước lượng theo một lần start, trong khi A-Rows ở plan output có thể là tổng số hàng qua các lần start. Khi so sánh, phải xét Starts và cách format/version trình bày số liệu. Không kết luận misestimate chỉ bằng phép chia A-Rows cho E-Rows mà bỏ qua Starts.

Ví dụ, inner operation dự kiến 1 hàng mỗi lần, Starts = 1.000 và tổng A-Rows = 1.000 có thể hoàn toàn hợp lý. Nếu chỉ so 1.000 với 1 sẽ tưởng sai 1.000 lần.

## 6. Các cột quan trọng trong DBMS_XPLAN

| Cột | Ý nghĩa | Cách dùng |
|---|---|---|
| Id | ID operation trong plan | Xác định row source |
| Operation | Loại thao tác | Hiểu cách truy cập/join |
| Name | Object hoặc index | Biết object được sử dụng |
| Starts | Số lần operation được bắt đầu | Quan trọng với nested loops |
| E-Rows | Số hàng optimizer ước lượng | So với actual |
| A-Rows | Số hàng thực tế ghi nhận | Phát hiện estimate lệch |
| A-Time | Thời gian runtime theo operation | Tìm vùng tốn thời gian, đọc thận trọng |
| Buffers | Logical I/O | Đánh giá công việc đọc buffer |
| Reads | Physical reads | Đánh giá I/O từ storage |
| OMem / 1Mem | Memory ước lượng cho work area | Phân tích sort/hash |
| Used-Mem | Memory sử dụng trong operation | Xem work area runtime |
| Cost | Cost optimizer ước lượng | So sánh phương án optimizer |
| Bytes | Kích thước dữ liệu ước lượng | Hiểu volume trung gian |

Không phải mọi format hoặc mọi operation đều có tất cả cột. A-Time có thể được làm tròn và không cộng đơn giản thành elapsed time toàn statement.

## 7. Vì sao EXPLAIN PLAN khác plan đã thực thi?

### 7.1. Bind values và bind peeking

Một câu SQL có thể dùng bind:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
```

Customer 100 có thể chỉ có 1 order, còn customer 200 có thể có 50.000 order. Selectivity khác nhau có thể khiến optimizer chọn index access cho một giá trị và full scan/hash strategy cho giá trị khác.

EXPLAIN PLAN thường không tái tạo đầy đủ tình huống bind thực tế và child cursor đã được tạo khi ứng dụng chạy. Bind peeking ở lần hard parse, adaptive cursor sharing và bind sensitivity có thể khiến cursor plan khác với plan explain.

### 7.2. Datatype của bind

Bind NUMBER, VARCHAR2, DATE hoặc TIMESTAMP khác nhau có thể ảnh hưởng implicit conversion và access predicate. Ứng dụng bind kiểu khác với kiểu cột có thể khiến plan thực tế khác plan được giải thích với literal hoặc bind type khác.

Luôn ghi nhận datatype của bind từ driver/application, không chỉ giá trị hiển thị.

### 7.3. Child cursor khác nhau

Một SQL_ID có thể có nhiều child cursor do khác bind behavior, optimizer environment, object metadata, authorization context hoặc các lý do cursor sharing khác. Mỗi child có thể có plan riêng.

Nếu chỉ xem child 0 trong khi ứng dụng chạy child 3, kết luận sẽ sai. Xác định đúng SQL_ID và child number của execution cần điều tra.

### 7.4. Optimizer environment khác nhau

Các setting như OPTIMIZER_MODE, optimizer feature enablement, NLS, parallel settings, statistics level và một số parameter khác có thể ảnh hưởng plan. Session ứng dụng và session chạy EXPLAIN PLAN có thể không có cùng môi trường.

So sánh optimizer environment của cursor với session explain khi cần.

### 7.5. Statistics thay đổi

Giữa thời điểm EXPLAIN PLAN và thời điểm ứng dụng parse/execute:

- Table/column/index statistics có thể được gather lại.
- Histogram có thể được tạo hoặc thay đổi.
- Partition/global stats có thể cập nhật.
- Dữ liệu có thể thay đổi đủ lớn để stats stale hoặc plan khác.

Plan explain mới không nhất thiết phản ánh plan đã được tạo trước đó trong shared pool.

### 7.6. Schema resolution, synonym và current schema

Hai session có CURRENT_SCHEMA khác nhau, synonym khác nhau hoặc quyền khác nhau có thể phân giải cùng tên object thành object khác. Điều này đặc biệt dễ nhầm khi SQL không ghi rõ schema owner.

Khi điều tra, xác nhận object thực tế trong plan: OBJECT_OWNER, OBJECT_NAME và object type.

### 7.7. VPD, application context và security policy

Virtual Private Database (VPD) hoặc row-level security có thể thêm predicate vào SQL dựa trên user/context. Application session có thể có client identifier hoặc application context khác session explain. Vì vậy SQL được parse trong ứng dụng có thể khác SQL được optimizer thấy trong session explain.

Phải tái hiện đúng context bảo mật khi điều tra, nhưng không giả lập hoặc bỏ qua policy trong production để ép plan.

### 7.8. Global temporary table và dữ liệu session-specific

Global temporary table có metadata chung nhưng dữ liệu thuộc session hoặc transaction theo cách khai báo. Statistics và dữ liệu của session ứng dụng có thể khác session explain. Một plan được giải thích trong session không có cùng tập dữ liệu tạm có thể không đại diện.

### 7.9. Dynamic statistics và feedback

Optimizer có thể sử dụng dynamic statistics, cardinality/statistics feedback hoặc adaptive mechanisms. Những thông tin này có thể xuất hiện trong lần parse/cursor sau hoặc dẫn đến child/plan khác với EXPLAIN PLAN chạy riêng.

### 7.10. Adaptive plans

Một số phiên bản/cấu hình hỗ trợ adaptive plan. Plan có thể chứa lựa chọn runtime, và nhánh thực tế được dùng có thể phụ thuộc thông tin quan sát khi chạy. Plan explain không cho biết chắc chắn nhánh nào đã được chọn trong execution cụ thể.

### 7.11. SQL Profile, SQL Patch và SQL Plan Baseline

Cursor thực tế có thể chịu ảnh hưởng của SQL Profile, SQL Patch hoặc SQL Plan Baseline đã được áp dụng cho statement. EXPLAIN PLAN trong session khác hoặc môi trường khác có thể không phản ánh đúng cùng cấu hình quản lý plan.

Khi so sánh, kiểm tra SQL Management Base, profile/patch liên quan và plan hash của cursor thực tế.

### 7.12. Parallel execution

Plan có thể được thực thi song song với PX server, DOP và distribution method cụ thể. Explain plan có thể hiển thị kế hoạch song song dự kiến, nhưng runtime DOP, downgrade, PX allocation và hoạt động thực tế có thể khác khi tài nguyên thay đổi.

### 7.13. Phiên bản Oracle và optimizer features

Khác database release hoặc OPTIMIZER_FEATURES_ENABLE có thể làm transformation, costing và plan thay đổi. Không so sánh plan từ hai release mà bỏ qua khác biệt optimizer version.

## 8. Xác định đúng SQL_ID và child cursor

### 8.1. Tìm câu SQL trong V$SQL

Ví dụ:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parsing_schema_name,
       module,
       action,
       last_active_time,
       sql_text
FROM v$sql
WHERE sql_text LIKE '%FROM orders%'
ORDER BY last_active_time DESC;
```

V$SQL chứa thông tin cursor trong shared pool. Điều kiện LIKE có thể trả nhiều statement gần giống nhau; dùng SQL_ID đã được application trace/APM ghi nhận nếu có.

### 8.2. Xem child cursor

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       is_bind_sensitive,
       is_bind_aware,
       optimizer_env_hash_value,
       parsing_schema_name
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Các cột có thể khác theo release. IS_BIND_SENSITIVE và IS_BIND_AWARE hữu ích khi điều tra adaptive cursor sharing.

### 8.3. Xem plan cho child cụ thể

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => :sql_id,
        cursor_child_no => :child_number,
        format          => 'TYPICAL +PREDICATE'
    )
);
```

Đảm bảo bind SQL_ID và child number đúng với cursor cần phân tích. Một SQL_ID không đồng nghĩa chỉ có một execution plan.

### 8.4. Xem optimizer environment

```sql
SELECT name, value
FROM v$sql_optimizer_env
WHERE sql_id = :sql_id
  AND child_number = :child_number
ORDER BY name;
```

So sánh các setting quan trọng với session chạy EXPLAIN PLAN. Không cần so sánh mọi dòng một cách máy móc; tập trung parameter khác biệt có thể ảnh hưởng optimizer.

### 8.5. Xem SQL text đầy đủ

SQL_TEXT trong V$SQL có thể chỉ chứa một phần câu lệnh. Dùng V$SQL.SQL_FULLTEXT hoặc DBMS_LOB.SUBSTR theo quyền và release để lấy đầy đủ SQL text. Đối chiếu whitespace, comment hint, literal và bind names.

## 9. Xem plan với DBMS_XPLAN theo mục đích

### 9.1. Plan dự kiến từ PLAN_TABLE

```sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'TEST_EXPLAIN'
FOR
SELECT *
FROM orders
WHERE customer_id = 1001;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        'PLAN_TABLE',
        'TEST_EXPLAIN',
        'TYPICAL +PREDICATE'
    )
);
```

### 9.2. Cursor plan đã chạy

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM orders
WHERE customer_id = 1001;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Trong môi trường thực tế, dùng SQL_ID/child cụ thể thay NULL nếu session chạy nhiều statement xen kẽ.

### 9.3. Format phổ biến

| Format | Công dụng |
|---|---|
| BASIC | Các operation chính |
| TYPICAL | Thông tin thường cần để đọc plan |
| ALL | Nhiều chi tiết hơn |
| +PREDICATE | Predicate information |
| +ALIAS | Alias/query block |
| +OUTLINE | Outline hints của plan |
| +PEEKED_BINDS | Bind values được peek nếu có |
| +NOTE | Ghi chú optimizer |
| +IOSTATS | Runtime I/O statistics nếu có |
| +MEMSTATS | Memory statistics nếu có |
| ALLSTATS LAST | Runtime statistics của lần thực thi cuối được thu thập |

Các tùy chọn được kết hợp trong chuỗi format, ví dụ ALLSTATS LAST +PEEKED_BINDS +PREDICATE. Tính sẵn có và chi tiết output phụ thuộc phiên bản Oracle.

### 9.4. Predicate Information

Access Predicates thường là điều kiện được dùng để xác định vị trí truy cập index/row source. Filter Predicates là điều kiện lọc sau hoặc trong operation. Phân biệt chúng giúp hiểu tại sao operation đọc nhiều hàng rồi mới loại bớt.

### 9.5. Outline Data

+OUTLINE có thể hiển thị hint outline dùng để tái tạo plan. Đây là dữ liệu hữu ích khi cần nghiên cứu plan hoặc SQL Plan Management. Không nên sao chép outline thành hint cố định mà không hiểu dependency và môi trường.

## 10. EXPLAIN PLAN và bind variables

### 10.1. Literal và bind có thể dẫn tới estimate khác

So sánh:

```sql
SELECT *
FROM orders
WHERE customer_id = 1001;
```

với:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
```

Literal có thể cho optimizer thông tin cụ thể khi parse. Bind có thể được xử lý qua bind peeking/ACS và child cursor behavior. Không thể coi plan của literal trong EXPLAIN PLAN là đại diện chắc chắn cho mọi bind execution.

### 10.2. Bind datatype và implicit conversion

Nếu CUSTOMER_ID là NUMBER nhưng ứng dụng bind VARCHAR2, Oracle có thể thực hiện conversion. Conversion có thể ảnh hưởng access path và estimate. Bind đúng datatype và kiểm tra Predicate Information/plan.

### 10.3. Peeked bind không phải mọi bind

+PEEKED_BINDS hiển thị thông tin bind được peek ở lần parse liên quan nếu có. Nó không phải lịch sử mọi giá trị bind đã chạy. Dùng V$SQL_BIND_CAPTURE khi phù hợp, đồng thời nhớ bind capture không ghi nhận mọi execution và có giới hạn.

### 10.4. Child cursor và ACS

Adaptive Cursor Sharing có thể tạo child cursor phù hợp với các selectivity range khác nhau. Khi query chạy chậm, xác định child cursor thực tế, bind-aware status và plan hash thay vì chỉ EXPLAIN PLAN với một literal.

## 11. Adaptive plan và plan đã thực thi

### 11.1. Adaptive plan

Adaptive plan có thể chứa nhiều lựa chọn plan ở thời điểm optimization. Trong lúc chạy, Oracle có thể dùng thông tin runtime để chọn nhánh phù hợp khi điều kiện adaptive được đáp ứng.

### 11.2. Plan hiển thị có thể chứa nhánh chưa dùng

Output plan có thể hiển thị operation inactive hoặc nhánh thay thế. Cần đọc format và thông tin adaptive để phân biệt nhánh được chọn với nhánh không được dùng.

### 11.3. ALLSTATS LAST

Runtime statistics giúp biết operation nào thực sự phát sinh rows/starts và nhánh nào được thực thi. EXPLAIN PLAN chỉ hiển thị plan dự kiến và không có bằng chứng runtime của nhánh được chọn.

### 11.4. Plan hash value

PLAN_HASH_VALUE là fingerprint dùng để nhận diện cấu trúc plan theo thuật toán Oracle. Hai cursor có plan hash khác nhau thường có plan structure khác nhau; plan hash giống nhau không bảo đảm mọi chi tiết runtime, predicate, bind hoặc environment giống hệt.

Một số phiên bản có thêm full plan hash hoặc thông tin plan hash khác. Không dùng plan hash như bằng chứng duy nhất rằng hai execution hoàn toàn tương đương.

## 12. SQL Monitor và các nguồn runtime khác

### 12.1. Real-Time SQL Monitoring

SQL Monitoring có thể cung cấp thông tin theo execution, operation, elapsed time, CPU, I/O, parallel server và tiến trình theo thời gian. Nó đặc biệt hữu ích với SQL dài hoặc parallel execution.

Real-Time SQL Monitoring phụ thuộc edition, license/management pack và cấu hình. Kiểm tra quyền và điều khoản cấp phép của môi trường trước khi dùng.

### 12.2. DBMS_SQLTUNE.REPORT_SQL_MONITOR

Trong môi trường có quyền và license phù hợp, có thể tạo report:

```sql
SELECT DBMS_SQLTUNE.REPORT_SQL_MONITOR(
           sql_id       => :sql_id,
           type         => 'TEXT',
           report_level => 'ALL'
       )
FROM dual;
```

SQL Monitor report bổ sung runtime detail; nó không thay thế việc xác định đúng execution/child cursor. Có thể cần SQL_EXEC_ID và SQL_EXEC_START khi cùng SQL_ID có nhiều execution.

### 12.3. SQL trace và TKPROF

SQL trace ghi thông tin parse/execute/fetch, wait và thống kê liên quan. TKPROF định dạng trace để điều tra. Trace giúp phân biệt thời gian parse, execute, fetch và các wait; plan trong trace có thể bổ sung bằng chứng về execution.

Bật trace có overhead và có thể chứa bind/data nhạy cảm. Dùng theo thời gian/phạm vi kiểm soát và bảo vệ file trace.

### 12.4. AWR và ASH

AWR/ASH giúp quan sát workload và lịch sử SQL/plan theo thời gian trong môi trường có quyền/license phù hợp. Dữ liệu lịch sử tổng hợp không nhất thiết thay thế runtime statistics đầy đủ của một execution cụ thể.

### 12.5. Application tracing

Ứng dụng nên ghi SQL_ID, module/action, request ID, execution timing và bind metadata đã được bảo vệ phù hợp. Điều này giúp liên kết request chậm với đúng cursor trong database. Không ghi secret hoặc dữ liệu nhạy cảm nguyên văn vào log.

## 13. EXPLAIN PLAN có thể khác vì môi trường nào?

| Yếu tố | EXPLAIN PLAN | Cursor plan đã chạy |
|---|---|---|
| Bind values | Có thể không tái tạo bind peek/child behavior | Gắn với cursor/child thực tế |
| Bind datatype | Phụ thuộc cách explain/parse | Datatype do ứng dụng bind |
| Optimizer environment | Session explain hiện tại | Environment của cursor parse |
| Statistics | Stats lúc explain | Stats/metadata lúc cursor được parse |
| Schema/synonym | Theo session explain | Theo parsing schema và context thực tế |
| VPD/context | Context của session explain | Context khi ứng dụng parse |
| Child cursor | Không đại diện một child runtime cụ thể | Có SQL_ID và child number |
| Adaptive behavior | Kế hoạch dự kiến | Có thể quan sát nhánh runtime |
| Runtime rows/time/I/O | Không có cho SQL mục tiêu | Có nếu thu thập |
| SQL Profile/Baseline/Patch | Phụ thuộc môi trường explain | Có thể tác động cursor thực tế |

## 14. Quy trình điều tra một câu SQL chậm

### Bước 1 — Xác định đúng execution

Thu thập SQL_ID, child number, SQL_EXEC_ID/SQL_EXEC_START nếu có, module/action, user/schema, request ID và thời điểm chạy.

### Bước 2 — Lấy SQL text đầy đủ

Đối chiếu SQL text từ cursor với SQL do ứng dụng tạo. Kiểm tra bind placeholders, literal, comments/hints và query block.

### Bước 3 — Lấy cursor plan

Gọi DBMS_XPLAN.DISPLAY_CURSOR với SQL_ID/child number cụ thể. Không mặc định child 0 là child ứng dụng đang dùng.

### Bước 4 — Thu thập runtime statistics

Nếu có thể tái hiện an toàn, chạy với GATHER_PLAN_STATISTICS hoặc STATISTICS_LEVEL phù hợp rồi lấy ALLSTATS LAST. Với execution production đã qua, xem SQL Monitor/AWR/trace nếu dữ liệu có sẵn.

### Bước 5 — So E-Rows và A-Rows

Tìm operation đầu tiên có chênh lệch lớn, có xét Starts. Ghi lại predicate và row source đầu vào.

### Bước 6 — Kiểm tra bind và child cursor

Xem bind datatype, peeked binds, bind sensitivity/awareness và optimizer environment. Xác định query có nhiều nhóm selectivity khác nhau không.

### Bước 7 — Kiểm tra object và statistics

Xác nhận owner/object, table/column/index stats, histogram, extended stats, partition stats, stale status và thời điểm gather.

### Bước 8 — Kiểm tra runtime factors

Xem concurrency, DOP, workarea memory, TEMP spill, I/O, locks, waits, session context và thay đổi schema gần thời điểm sự cố.

### Bước 9 — Tạo giả thuyết và thử có kiểm soát

Dùng EXPLAIN PLAN để khảo sát một rewrite hoặc setting khác, nhưng xác nhận bằng cursor plan/runtime trong môi trường đại diện. Không thay optimizer parameter toàn hệ thống để thử nhanh.

### Bước 10 — Bảo vệ plan tốt

Nếu đã xác định plan ổn định, đánh giá SQL Plan Baseline hoặc công cụ SQL Tuning phù hợp. Ghi lại điều kiện, SQL text, bind profile, plan hash và số đo trước/sau.

## 15. Ví dụ so sánh EXPLAIN PLAN và cursor plan

### 15.1. Tạo dữ liệu lab

Thực hiện trong schema lab riêng:

```sql
CREATE TABLE plan_lab (
    id NUMBER NOT NULL,
    category VARCHAR2(20),
    payload VARCHAR2(100)
);

INSERT INTO plan_lab(id, category, payload)
SELECT level,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'RARE'
           ELSE 'COMMON'
       END,
       RPAD('X', 50, 'X')
FROM dual
CONNECT BY level <= 100000;

CREATE INDEX plan_lab_cat_ix
    ON plan_lab(category);

COMMIT;
```

### 15.2. Gather statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'PLAN_LAB',
        method_opt => 'FOR COLUMNS CATEGORY SIZE 254',
        cascade => TRUE
    );
END;
/
```

### 15.3. Explain plan

```sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'PLAN_LAB_RARE'
FOR
SELECT *
FROM plan_lab
WHERE category = 'RARE';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        'PLAN_TABLE',
        'PLAN_LAB_RARE',
        'TYPICAL +PREDICATE'
    )
);
```

### 15.4. Thực thi và lấy runtime plan

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM plan_lab
WHERE category = 'RARE';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

So sánh operation, E-Rows, A-Rows, Starts, Buffers và plan hash. Kết quả cụ thể phụ thuộc Oracle release, statistics, optimizer settings và dữ liệu lab.

### 15.5. Thử giá trị phổ biến

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM plan_lab
WHERE category = 'COMMON';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
```

So sánh plan và runtime với giá trị RARE. Nếu dùng literal, optimizer có thể biết giá trị ở parse. Có thể mở rộng lab sang bind variable và quan sát child cursor/ACS.

### 15.6. Thử khác session environment

Chạy EXPLAIN PLAN trong session có optimizer settings khác, hoặc thay đổi current schema/context trong môi trường lab, rồi xem object và plan có thay đổi không. Ghi rõ từng setting trước/sau; không thay system-wide setting trên database dùng chung.

### 15.7. Ghi kết quả

| Cách lấy plan | Plan hash | E-Rows | A-Rows | Starts | Buffers | Nhận xét |
|---|---|---:|---:|---:|---:|---|
| EXPLAIN PLAN |  |  | Không có | Không có runtime | Không có runtime | Estimate |
| DISPLAY_CURSOR |  |  |  |  |  | Cursor thực tế |
| DISPLAY_CURSOR với bind khác |  |  |  |  |  | Có thể là child khác |

Điền dữ liệu thực nghiệm từ hệ thống đang chạy. Không coi số liệu ví dụ trong bài là kết quả bắt buộc.

## 16. Các lỗi và hiểu nhầm thường gặp

### 16.1. Dùng EXPLAIN PLAN để kết luận thời gian query

EXPLAIN PLAN không thực thi câu SQL mục tiêu và không đo elapsed time thực tế. Dùng cursor runtime statistics, SQL Monitor hoặc trace.

### 16.2. So sánh plan mà không giữ cùng bind

Một literal phổ biến và một literal hiếm có thể có selectivity rất khác. Ghi nhận bind values/type và child cursor.

### 16.3. Xem sai child cursor

SQL_ID có nhiều child. DISPLAY_CURSOR với child number không đúng có thể dẫn tới chẩn đoán sai. Xác định child từ V$SQL, trace hoặc APM.

### 16.4. Không thu thập A-Rows

Nếu không có GATHER_PLAN_STATISTICS hoặc thống kê runtime phù hợp, ALLSTATS LAST không thể tự tạo actual rows cho execution đã qua. Thu thập khi tái hiện hoặc dùng nguồn lịch sử có sẵn.

### 16.5. Đọc E-Rows và A-Rows bỏ qua Starts

Operation chạy nhiều lần có thể có A-Rows cộng dồn. Xét Starts trước khi kết luận estimate sai.

### 16.6. Nhầm cost với elapsed time

Cost là thước đo optimizer, không phải giây. Plan cost thấp hơn không đảm bảo runtime thấp hơn khi estimate sai hoặc workload khác.

### 16.7. Cho rằng EXPLAIN PLAN luôn giống production

Session, schema, context, statistics, bind, version, profile/baseline và runtime adaptive behavior có thể khác. Tái hiện môi trường gần production nhất có thể.

### 16.8. Chỉ nhìn operation đầu tiên trên cùng

Plan là cây row source. Hãy lần theo quan hệ cha-con, predicate và cardinality từ các operation con.

### 16.9. Dùng EXPLAIN PLAN trước và sau để chứng minh runtime cải thiện

Plan explain chỉ cho biết dự kiến. Sau thay đổi SQL/stats/index, cần thực thi workload đại diện và đo runtime, buffers, reads, CPU, latency.

### 16.10. Bật thống kê runtime trên toàn hệ thống không kiểm soát

STATISTICS_LEVEL=ALL có thể tăng overhead. Ưu tiên hint GATHER_PLAN_STATISTICS cho câu lab hoặc bật setting trong session điều tra, rồi khôi phục.

## 17. Quy tắc sử dụng từng công cụ

| Công cụ | Dùng khi | Giới hạn chính |
|---|---|---|
| EXPLAIN PLAN | Xem plan dự kiến, thử SQL rewrite | Không thực thi SQL mục tiêu, không có actual rows/time |
| DBMS_XPLAN.DISPLAY | Định dạng plan trong PLAN_TABLE | Chỉ phản ánh lần explain đã lưu |
| DBMS_XPLAN.DISPLAY_CURSOR | Xem plan của cursor thực tế trong shared pool | Cần đúng SQL_ID/child; runtime stats có thể chưa thu thập |
| DBMS_XPLAN.DISPLAY_AWR | Xem plan lịch sử trong AWR | Phụ thuộc AWR/license/quyền; không phải mọi execution có actual rows |
| SQL Monitor | Phân tích execution dài/parallel theo runtime | Phụ thuộc license, quyền và điều kiện monitor |
| SQL Trace/TKPROF | Phân tích parse/execute/fetch, waits và I/O | Có overhead, cần quản lý trace |
| AWR/ASH | Điều tra workload và lịch sử | Dữ liệu tổng hợp, phụ thuộc license/quyền |

## 18. Checklist trước khi kết luận plan

- [ ] Đã xác định đây là plan explain hay cursor plan thực tế.
- [ ] Nếu là cursor plan, đã xác định SQL_ID và child number.
- [ ] Đã lấy đúng SQL text đầy đủ.
- [ ] Đã ghi nhận bind values và datatype cần thiết.
- [ ] Đã xem optimizer environment của cursor.
- [ ] Đã xác nhận parsing schema, owner và object thực tế.
- [ ] Đã kiểm tra application context/VPD nếu có.
- [ ] Đã thu thập runtime statistics nếu cần A-Rows.
- [ ] Đã xét Starts khi so sánh E-Rows và A-Rows.
- [ ] Đã xem Predicate Information và query block/alias.
- [ ] Đã xem plan hash và adaptive branches.
- [ ] Đã kiểm tra statistics, histogram, extended stats và thời điểm gather.
- [ ] Đã kiểm tra SQL Profile, SQL Patch và SQL Plan Baseline.
- [ ] Đã xem DOP/PX, workarea, TEMP spill, waits và I/O nếu liên quan.
- [ ] Đã benchmark với dữ liệu, bind và concurrency đại diện.
- [ ] Không dùng cost như thời gian thực tế.
- [ ] Không dùng EXPLAIN PLAN đơn lẻ để tuyên bố query production đã nhanh hơn.

## 19. Câu hỏi tự kiểm tra

1. EXPLAIN PLAN thực hiện công việc gì và không thực hiện công việc gì?
2. PLAN_TABLE lưu thông tin nào?
3. STATEMENT_ID có tác dụng gì khi chạy nhiều lần explain?
4. DBMS_XPLAN.DISPLAY khác DISPLAY_CURSOR ở nguồn dữ liệu nào?
5. Vì sao EXPLAIN PLAN không có A-Rows của lần chạy thật?
6. Làm thế nào xem cursor plan của một SQL_ID và child number cụ thể?
7. Vì sao một SQL_ID có thể có nhiều child cursor?
8. GATHER_PLAN_STATISTICS giúp thu thập thông tin gì?
9. ALLSTATS LAST hiển thị những loại runtime statistics nào?
10. STATISTICS_LEVEL=ALL có trade-off gì?
11. E-Rows và A-Rows khác nhau như thế nào?
12. Vì sao phải xét Starts khi so sánh E-Rows/A-Rows?
13. Bind peeking có thể làm EXPLAIN PLAN khác cursor plan ra sao?
14. Bind datatype và implicit conversion ảnh hưởng plan thế nào?
15. Optimizer environment khác nhau có thể thay đổi plan bằng cách nào?
16. CURRENT_SCHEMA, synonym và VPD có thể làm object/predicate khác nhau ra sao?
17. Adaptive plan có thể chứa nhánh nào không được thực thi?
18. PLAN_HASH_VALUE dùng để làm gì và không chứng minh điều gì?
19. Khi nào nên dùng SQL Monitor thay cho chỉ xem DBMS_XPLAN?
20. SQL Trace/TKPROF cung cấp bằng chứng gì?
21. Vì sao DISPLAY_CURSOR cần đúng child cursor?
22. Khi nào EXPLAIN PLAN vẫn hữu ích dù không có runtime statistics?
23. Làm thế nào tái hiện plan của ứng dụng trong session điều tra?
24. Vì sao không nên dùng cost như elapsed time?
25. Quy trình nào giúp xác định nguyên nhân plan regression đáng tin cậy?

**Nguyên tắc cần nhớ:** EXPLAIN PLAN cho biết optimizer dự kiến thực hiện SQL như thế nào trong môi trường explain; nó không chạy câu SQL mục tiêu và không cung cấp runtime rows/time. DBMS_XPLAN.DISPLAY đọc PLAN_TABLE, còn DISPLAY_CURSOR đọc cursor thực tế trong library cache. Khi điều tra production, phải xác định SQL_ID/child cursor, bind datatype/value, optimizer environment và session context; thu thập runtime statistics để so E-Rows với A-Rows có xét Starts. Dùng EXPLAIN PLAN để khảo sát, rồi xác nhận mọi thay đổi bằng execution thực tế và số đo đại diện.
