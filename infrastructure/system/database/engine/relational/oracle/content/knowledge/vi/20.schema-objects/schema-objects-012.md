# Lựa chọn bảng, view, materialized view hoặc kết quả truy vấn trực tiếp

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Đối tượng schema  
> **Mục tiêu:** Chọn đúng hình thức lưu trữ và truy xuất dữ liệu trong Oracle: bảng (table), view, materialized view hoặc kết quả truy vấn trực tiếp. Phân biệt dữ liệu vật lý với định nghĩa truy vấn, hiểu khả năng cập nhật, độ mới dữ liệu, index, refresh, query rewrite, quyền truy cập và chi phí vận hành; áp dụng một quy trình quyết định dựa trên nhu cầu thực tế.

## 1. Bốn cách biểu diễn dữ liệu, bốn mục đích khác nhau

Khi xây dựng một chức năng báo cáo hoặc nghiệp vụ, ta thường có một truy vấn SQL trả về dữ liệu. Câu hỏi tiếp theo là nên:

- Lưu dữ liệu thành **bảng** để quản lý như dữ liệu nghiệp vụ.
- Đóng gói logic SQL thành **view** để tái sử dụng.
- Lưu trước kết quả truy vấn bằng **materialized view** để đọc nhanh hoặc phục vụ phân tích.
- Viết **truy vấn trực tiếp** (SELECT, inline view hoặc CTE) ngay tại nơi sử dụng.

Bốn lựa chọn đều có thể trả về các hàng và cột, nhưng khác nhau về nơi lưu dữ liệu, thời điểm tính toán, độ mới, khả năng ghi và chi phí đồng bộ.

| Lựa chọn | Lưu dữ liệu kết quả? | Khi nào tính toán? | Điểm mạnh chính |
|---|---|---|---|
| Table | Có, lưu dữ liệu nghiệp vụ | Khi INSERT/UPDATE/DELETE hoặc nạp dữ liệu | Quản lý dữ liệu, constraint, index, transaction |
| View | Không lưu các hàng kết quả | Khi truy vấn view được thực thi | Tái sử dụng SQL, chuẩn hóa logic, kiểm soát cột/hàng |
| Materialized view | Có, lưu kết quả truy vấn | Khi tạo và mỗi lần refresh | Đọc nhanh kết quả tổng hợp hoặc join tốn kém |
| Truy vấn trực tiếp | Không lưu thành schema object | Mỗi lần chạy SQL | Linh hoạt, cục bộ, không cần object trung gian |

Một quy tắc ban đầu:

- Nếu dữ liệu là nguồn sự thật cần được INSERT/UPDATE/DELETE, dùng table.
- Nếu cần một tên logic để tái sử dụng SELECT, cân nhắc view.
- Nếu tính toán tốn kém và có thể chấp nhận chính sách refresh, cân nhắc materialized view.
- Nếu logic chỉ dùng một nơi hoặc cần truy vấn tùy biến, dùng SELECT/CTE/inline view trực tiếp.

Không chọn object chỉ dựa trên tên gọi hoặc suy nghĩ rằng view luôn chậm, materialized view luôn nhanh. Cần xem workload, freshness, optimizer plan và yêu cầu bảo trì.

## 2. Table: nơi lưu dữ liệu có thẩm quyền

Table là đối tượng lưu trữ dữ liệu trong schema. Dữ liệu được tổ chức trong segment và block theo cấu trúc lưu trữ của Oracle. Table có thể có:

- PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK và NOT NULL.
- B-tree/bitmap/function-based index tùy workload.
- Trigger, partitioning, compression và các thuộc tính lưu trữ.
- Transaction DML, undo, redo và locking.
- Quyền SELECT/INSERT/UPDATE/DELETE được cấp theo nhu cầu.

Ví dụ:

~~~sql
CREATE TABLE orders (
    order_id NUMBER CONSTRAINT pk_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    total_amount NUMBER(14,2) NOT NULL,
    CONSTRAINT ck_orders_amount CHECK (total_amount >= 0)
);
~~~

Đây là nơi lưu dữ liệu đơn hàng gốc. Ứng dụng có thể thêm, sửa, xóa theo quy tắc nghiệp vụ.

### 2.1. Khi nào table là lựa chọn đúng?

Dùng table khi:

- Dữ liệu cần tồn tại độc lập với một câu SELECT cụ thể.
- Người dùng hoặc hệ thống có thể thay đổi dữ liệu.
- Cần transaction để bảo đảm nhiều thay đổi cùng thành công hoặc cùng rollback.
- Cần constraint để bảo vệ tính toàn vẹn.
- Cần lưu lịch sử, trạng thái, sự kiện hoặc snapshot nghiệp vụ.
- Cần quản lý vòng đời dữ liệu, backup, partition, retention và quyền truy cập.

Một bảng staging cũng là table, nhưng thường có vòng đời khác bảng nghiệp vụ: nạp dữ liệu thô, validate, transform rồi chuyển vào bảng đích. Không nên dùng view thay table chỉ vì dữ liệu ban đầu đến từ một truy vấn.

### 2.2. Bảng tổng hợp có nên được lưu thành table?

Có thể lưu kết quả tổng hợp vào table nếu đó là dữ liệu được quản lý bởi một pipeline riêng, có batch/version, quy tắc cập nhật và audit. Ví dụ bảng snapshot doanh thu cuối ngày có thể là sản phẩm dữ liệu chính thức của quy trình ETL.

Tuy nhiên, nếu dữ liệu tổng hợp có thể được tính lại từ nguồn và cần đồng bộ tự động với chính sách Oracle, materialized view có thể phù hợp hơn. Cần phân biệt bảng kết quả do ứng dụng tự quản lý với materialized view có định nghĩa query và refresh metadata.

## 3. View: lưu định nghĩa SQL, không lưu kết quả hàng

View là một schema object chứa định nghĩa truy vấn. Khi truy vấn view, Oracle sử dụng câu SELECT định nghĩa view để tạo kết quả tại thời điểm thực thi.

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW active_orders_v AS
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM orders
WHERE status = 'OPEN';
~~~

Đọc view:

~~~sql
SELECT order_id, customer_id, total_amount
FROM active_orders_v
WHERE customer_id = :p_customer_id;
~~~

View không tự tạo một bản sao các hàng OPEN. Nó đọc dữ liệu từ bảng cơ sở theo snapshot của statement. Nếu đơn hàng được đổi từ OPEN sang CLOSED và transaction commit, truy vấn view tiếp theo sẽ phản ánh trạng thái đã commit mới.

### 3.1. View giúp tái sử dụng logic

Một view có thể đóng gói:

- JOIN giữa nhiều bảng.
- Predicate lọc hàng.
- Biểu thức chuẩn hóa dữ liệu.
- Phép tính cột.
- Phân loại hoặc ánh xạ giá trị.
- Một giao diện ổn định cho ứng dụng.

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW order_customer_v AS
SELECT o.order_id,
       o.order_date,
       o.status,
       o.total_amount,
       c.customer_id,
       c.customer_name,
       c.region_code
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id;
~~~

Nhiều ứng dụng có thể dùng cùng một định nghĩa thay vì sao chép JOIN và điều kiện giữa nhiều nơi. Khi logic thay đổi, chủ sở hữu có thể cập nhật view theo quy trình quản lý schema.

View cũng có thể chỉ công bố một số cột, ví dụ ẩn thông tin nội bộ hoặc chỉ cho người dùng đọc dữ liệu thuộc phạm vi được phép. View là một lớp giao diện dữ liệu; quyền trên view cần được thiết kế cẩn thận và không thay thế mọi cơ chế bảo mật khác.

### 3.2. View không bảo đảm thứ tự hàng

Không nên dựa vào thứ tự hàng bên trong định nghĩa view. Nếu cần kết quả có thứ tự, đặt ORDER BY ở truy vấn sử dụng view:

~~~sql
SELECT order_id, order_date
FROM active_orders_v
ORDER BY order_date DESC, order_id DESC;
~~~

Đây là quy tắc chung của SQL: kết quả chỉ có thứ tự được bảo đảm khi câu truy vấn ngoài cùng có ORDER BY phù hợp.

### 3.3. View không nhất thiết làm truy vấn chậm hơn

Optimizer có thể merge view query block vào câu truy vấn bên ngoài, đẩy predicate xuống bảng cơ sở (predicate pushing) và chọn access path phù hợp. Vì vậy view đơn giản thường chỉ là cách tổ chức SQL, không nhất thiết tạo một bước vật lý riêng.

Tuy nhiên, một view phức tạp có thể chứa DISTINCT, GROUP BY, analytic function, UNION, outer join hoặc biểu thức làm hạn chế một số phép biến đổi. Query lồng nhiều tầng cũng có thể khiến SQL khó đọc và khó tối ưu nếu không có cấu trúc rõ ràng.

Đánh giá bằng execution plan và runtime statistics thay vì mặc định view luôn có overhead.

## 4. View có cập nhật được không?

Một view có thể cho phép INSERT, UPDATE hoặc DELETE thông qua view nếu Oracle có thể ánh xạ thay đổi một cách rõ ràng về các hàng của bảng cơ sở và các quy tắc DML được đáp ứng.

### 4.1. View đơn giản có thể updatable

~~~sql
CREATE OR REPLACE VIEW employees_basic_v AS
SELECT employee_id,
       employee_name,
       department_id,
       salary
FROM employees;
~~~

Có thể cập nhật qua view:

~~~sql
UPDATE employees_basic_v
SET salary = salary + 500
WHERE employee_id = 100;
~~~

Oracle cập nhật hàng tương ứng trong bảng EMPLOYEES. View không có segment dữ liệu riêng để nhận thay đổi.

### 4.2. Các cấu trúc có thể hạn chế khả năng DML

Một view có thể không updatable tự động hoặc chỉ cho phép một số cột/hàng khi chứa:

- Aggregate như SUM, COUNT, AVG.
- GROUP BY hoặc HAVING.
- DISTINCT.
- Set operator như UNION/UNION ALL, INTERSECT hoặc MINUS.
- Một số biểu thức, subquery hoặc join phức tạp.
- Cột được tính toán thay vì ánh xạ trực tiếp đến cột bảng.

Ví dụ view tổng hợp:

~~~sql
CREATE OR REPLACE VIEW department_salary_v AS
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
FROM employees
GROUP BY department_id;
~~~

Không thể đơn giản UPDATE AVERAGE_SALARY để Oracle tự biết phải phân bổ giá trị mới cho từng nhân viên.

### 4.3. Kiểm tra khả năng cập nhật bằng USER_UPDATABLE_COLUMNS

Oracle cung cấp dictionary view để xem cột view có thể insert/update/delete qua view hay không:

~~~sql
SELECT table_name,
       column_name,
       updatable,
       insertable,
       deletable
FROM user_updatable_columns
WHERE table_name = 'EMPLOYEES_BASIC_V'
ORDER BY column_name;
~~~

Các giá trị phụ thuộc cấu trúc view và quy tắc Oracle. Đây là công cụ kiểm tra metadata hữu ích trước khi thiết kế API DML qua view.

### 4.4. WITH CHECK OPTION

Nếu view lọc STATUS = OPEN, cần tránh việc DML qua view tạo hoặc sửa hàng khiến nó không còn thỏa predicate mà vẫn được thực hiện theo cách gây bất ngờ.

~~~sql
CREATE OR REPLACE VIEW open_orders_v AS
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE status = 'OPEN'
WITH CHECK OPTION CONSTRAINT ck_open_orders_view;
~~~

WITH CHECK OPTION yêu cầu các hàng được INSERT/UPDATE qua view tiếp tục thỏa điều kiện view áp dụng. Nó hữu ích khi view đại diện cho một tập con dữ liệu có quy tắc rõ ràng.

Nó không biến view thành bảng riêng và không thay thế constraint nghiệp vụ ở bảng cơ sở.

### 4.5. WITH READ ONLY

Nếu view chỉ được dùng để đọc, có thể khai báo:

~~~sql
CREATE OR REPLACE VIEW order_summary_read_v AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
WITH READ ONLY;
~~~

WITH READ ONLY ngăn DML qua view. Người dùng vẫn có thể đọc kết quả nếu có quyền phù hợp.

### 4.6. INSTEAD OF trigger

Với view phức tạp hoặc join view không tự updatable, có thể dùng INSTEAD OF trigger để định nghĩa cách DML được chuyển thành thay đổi ở bảng cơ sở.

Ví dụ minh họa view kết hợp phòng ban và nhân viên:

~~~sql
CREATE OR REPLACE VIEW employee_department_v AS
SELECT e.employee_id,
       e.employee_name,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Một INSTEAD OF trigger có thể định nghĩa cách xử lý thao tác trên view:

~~~sql
CREATE OR REPLACE TRIGGER employee_department_v_upd
INSTEAD OF UPDATE ON employee_department_v
FOR EACH ROW
BEGIN
    UPDATE employees
    SET employee_name = :NEW.employee_name,
        department_id = :NEW.department_id
    WHERE employee_id = :OLD.employee_id;
END;
/
~~~

Trigger này chỉ minh họa cập nhật một số cột ở bảng EMPLOYEES. Nếu cần cập nhật DEPARTMENT_NAME, phải định nghĩa riêng quy tắc thay đổi bảng DEPARTMENTS; không thể suy luận rằng một hàng join tương ứng với một hàng cập nhật ở cả hai bảng.

INSTEAD OF trigger tăng khả năng tùy biến nhưng cũng tăng trách nhiệm: xử lý key, validate, quyền, lỗi, concurrency và số hàng thực sự được tác động.

## 5. Materialized view: lưu trước kết quả truy vấn

Materialized view (MV) lưu kết quả của một query trong database. Khác với view thông thường, MV có dữ liệu vật lý được lưu và cần được refresh để phản ánh thay đổi từ bảng nguồn.

Ví dụ báo cáo doanh thu theo khách hàng:

~~~sql
CREATE MATERIALIZED VIEW mv_customer_sales
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_sales
FROM orders
WHERE status = 'CLOSED'
GROUP BY customer_id;
~~~

BUILD IMMEDIATE tạo và nạp dữ liệu ngay khi tạo MV. REFRESH COMPLETE ON DEMAND nghĩa là mỗi lần refresh theo yêu cầu, Oracle tính lại toàn bộ kết quả của MV theo query định nghĩa.

Đọc MV:

~~~sql
SELECT customer_id, order_count, total_sales
FROM mv_customer_sales
WHERE total_sales > :p_min_sales;
~~~

Truy vấn đọc dữ liệu đã materialize. Nếu bảng ORDERS thay đổi sau lần refresh cuối, MV có thể chưa phản ánh thay đổi đó.

### 5.1. MV phù hợp khi nào?

Materialized view thường hữu ích khi:

- Query nguồn có JOIN hoặc GROUP BY tốn kém.
- Nhiều người dùng đọc cùng một kết quả tổng hợp.
- Workload đọc nhiều hơn ghi.
- Có thể chấp nhận dữ liệu trễ theo một chu kỳ refresh.
- Cần tăng tốc báo cáo, dashboard hoặc một số query phân tích.
- Có thể quản lý chi phí storage, refresh và lịch đồng bộ.

MV không phù hợp tự động cho mọi bảng báo cáo. Nếu refresh tốn hơn chi phí query trực tiếp, hoặc dữ liệu phải tức thời sau mỗi commit, lợi ích có thể không đáng.

### 5.2. MV có index riêng

Vì MV lưu dữ liệu, có thể tạo index trên MV:

~~~sql
CREATE INDEX ix_mv_customer_sales_total
ON mv_customer_sales(total_sales);
~~~

Index này có thể hỗ trợ truy vấn lọc theo TOTAL_SALES. Index trên MV cũng tiêu thụ storage và phải được duy trì khi MV refresh.

Không tạo index theo thói quen; xem predicate, selectivity và execution plan của truy vấn đọc MV.

## 6. Refresh materialized view

MV phải được đồng bộ với dữ liệu nguồn bằng refresh. Oracle hỗ trợ nhiều cách refresh và nhiều thời điểm thực hiện.

### 6.1. COMPLETE refresh

COMPLETE refresh tính lại toàn bộ kết quả theo query định nghĩa. Đây là cách đơn giản và có thể áp dụng cho nhiều MV, nhưng chi phí tăng theo lượng dữ liệu nguồn và kết quả.

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list           => 'MV_CUSTOMER_SALES',
        method         => 'C'
    );
END;
/
~~~

Dùng COMPLETE khi query không đáp ứng điều kiện fast refresh, khi dữ liệu thay đổi lớn, hoặc khi chi phí tính lại toàn bộ vẫn chấp nhận được.

### 6.2. FAST refresh

FAST refresh áp dụng thay đổi tăng dần dựa trên thông tin cần thiết được Oracle lưu/ghi nhận, thường liên quan đến materialized view log trên bảng master và khả năng refresh của query.

Ví dụ tạo MV log:

~~~sql
CREATE MATERIALIZED VIEW LOG ON orders
WITH ROWID, SEQUENCE (customer_id, status, total_amount)
INCLUDING NEW VALUES;
~~~

Sau đó MV có thể được tạo với FAST refresh nếu query đáp ứng yêu cầu:

~~~sql
CREATE MATERIALIZED VIEW mv_customer_sales_fast
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_sales
FROM orders
WHERE status = 'CLOSED'
GROUP BY customer_id;
~~~

Đây là ví dụ minh họa, không phải bảo đảm rằng mọi phiên bản/cấu hình sẽ chấp nhận đúng query và log trên. Khả năng FAST refresh phụ thuộc cấu trúc query, aggregate, join, biểu thức, khóa, materialized view log và release Oracle.

Có thể dùng DBMS_MVIEW.EXPLAIN_MVIEW để xem khả năng refresh:

~~~sql
-- Bảng MV_CAPABILITIES_TABLE cần được tạo theo script utlxmv.sql
-- trong Oracle home phù hợp trước khi gọi thủ tục.
DELETE FROM mv_capabilities_table;

BEGIN
    DBMS_MVIEW.EXPLAIN_MVIEW('MV_CUSTOMER_SALES_FAST');
END;
/

SELECT capability_name,
       possible,
       related_text,
       msgtxt
FROM mv_capabilities_table
ORDER BY seq;
~~~

DBMS_MVIEW.EXPLAIN_MVIEW giúp hiểu capability nào được hỗ trợ và lý do capability khác không được hỗ trợ. Hãy đối chiếu script và package với Oracle release đang dùng.

### 6.3. FORCE refresh

FORCE cho phép Oracle chọn FAST nếu có thể, nếu không thì COMPLETE. Đây là lựa chọn linh hoạt nhưng không có nghĩa refresh luôn tăng dần.

Ví dụ gọi refresh:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'MV_CUSTOMER_SALES',
        method => '?'
    );
END;
/
~~~

Khi cần dự đoán thời gian chạy, hãy xác định capability và refresh method thực tế, thay vì giả định FORCE sẽ luôn nhanh.

### 6.4. ON DEMAND và ON COMMIT

| Chế độ | Thời điểm cập nhật | Đặc điểm |
|---|---|---|
| ON DEMAND | Khi gọi refresh hoặc job chạy | Chủ động chọn thời gian, chấp nhận độ trễ |
| ON COMMIT | Khi transaction thay đổi bảng nguồn commit | MV được cập nhật đồng bộ với commit, làm tăng công việc commit |

ON COMMIT có thể phù hợp với MV nhỏ, query hỗ trợ fast refresh và yêu cầu freshness chặt. Tuy nhiên, nó làm tăng chi phí transaction ghi nguồn; commit có thể chậm hơn vì phải cập nhật MV.

ON DEMAND thường phù hợp với báo cáo theo lịch hoặc workload chấp nhận dữ liệu trễ.

### 6.5. Lịch refresh

Có thể lập lịch bằng Scheduler để refresh theo chu kỳ. Ví dụ tạo job:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'JOB_REFRESH_CUSTOMER_SALES',
        job_type        => 'PLSQL_BLOCK',
        job_action      => q'[
            BEGIN
                DBMS_MVIEW.REFRESH(
                    list   => 'MV_CUSTOMER_SALES',
                    method => 'C'
                );
            END;
        ]',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=HOURLY;INTERVAL=1',
        enabled         => TRUE
    );
END;
/
~~~

Job cần owner/quyền phù hợp, lịch không chồng lấn và xử lý lỗi. Theo dõi thời điểm refresh thành công, thời gian chạy và độ trễ dữ liệu. Không để refresh job chạy song song không kiểm soát với chính nó hoặc các batch nguồn lớn.

## 7. Độ mới dữ liệu và tính nhất quán

Đây là khác biệt quan trọng nhất giữa view và materialized view.

- View đọc bảng nguồn theo snapshot của câu SELECT hiện tại.
- Materialized view đọc dữ liệu đã lưu ở lần refresh gần nhất.
- Table kết quả do ETL/ứng dụng quản lý có freshness theo pipeline của chính nó.
- Truy vấn trực tiếp đọc snapshot tại thời điểm statement bắt đầu.

Ví dụ:

1. 10:00, MV được refresh.
2. 10:05, một đơn hàng mới được INSERT vào ORDERS và COMMIT.
3. 10:06, query view trực tiếp sẽ thấy dữ liệu đã commit theo snapshot mới.
4. 10:06, query MV có thể chưa thấy đơn hàng vì MV chưa refresh.
5. 11:00, MV refresh thành công; query MV mới phản ánh đơn hàng đó.

MV không phải cache tự động đồng bộ từng thay đổi trừ khi được thiết kế refresh tương ứng. Ứng dụng phải biết và chấp nhận độ trễ này.

### 7.1. Theo dõi trạng thái và thời điểm refresh

Có thể xem metadata:

~~~sql
SELECT mview_name,
       refresh_mode,
       refresh_method,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM user_mviews
ORDER BY mview_name;
~~~

Các trường giúp xem mode/method, trạng thái freshness và lần refresh gần nhất. Tên cột và thông tin khả dụng cần đối chiếu theo Oracle release.

Một số trạng thái staleness thường gặp:

- FRESH: MV phản ánh dữ liệu nguồn theo metadata Oracle.
- STALE: dữ liệu nguồn đã thay đổi và MV chưa được refresh tương ứng.
- NEEDS_COMPILE hoặc trạng thái khác: có thể liên quan định nghĩa/metadata cần xử lý.

Không chỉ dựa vào tên trạng thái; kiểm tra refresh job, lỗi, log và query định nghĩa.

## 8. Query rewrite: Oracle có thể dùng MV thay query nguồn

Materialized view có thể tham gia query rewrite: optimizer có thể thay một phần truy vấn trên bảng gốc bằng việc đọc MV nếu MV chứa thông tin đủ đáp ứng câu truy vấn và các điều kiện rewrite được thỏa.

Ví dụ người dùng chạy:

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_sales
FROM orders
WHERE status = 'CLOSED'
GROUP BY customer_id;
~~~

Nếu MV tương ứng đã tồn tại và query rewrite được bật/cấu hình phù hợp, Oracle có thể dùng MV thay vì tính lại từ ORDERS.

Có thể bật query rewrite ở MV:

~~~sql
ALTER MATERIALIZED VIEW mv_customer_sales
ENABLE QUERY REWRITE;
~~~

Việc optimizer có rewrite hay không phụ thuộc:

- QUERY_REWRITE_ENABLED và các tham số liên quan.
- MV có đủ dữ liệu/cột để trả lời query.
- Freshness/staleness và chính sách rewrite integrity.
- Constraint và metadata mà optimizer tin cậy.
- Cấu trúc SQL và capability của MV.
- Statistics và cost estimate.

Có thể quan sát execution plan để xác nhận optimizer thực sự đọc MV. Không giả định cứ tạo MV là mọi query tương tự tự động dùng MV.

## 9. Truy vấn trực tiếp, inline view và CTE

Nếu logic chỉ dùng tại một nơi hoặc cần thay đổi linh hoạt theo request, có thể viết truy vấn trực tiếp.

### 9.1. SELECT trực tiếp

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM orders
WHERE status = :p_status
  AND order_date >= :p_from_date
ORDER BY order_date DESC, order_id DESC;
~~~

Ưu điểm là logic hiện ngay tại nơi dùng, không cần tạo schema object. Nhược điểm là nếu nhiều ứng dụng sao chép cùng logic, định nghĩa có thể lệch nhau.

### 9.2. Inline view

Inline view là subquery trong mệnh đề FROM:

~~~sql
SELECT x.customer_id,
       x.total_sales
FROM (
    SELECT customer_id,
           SUM(total_amount) AS total_sales
    FROM orders
    WHERE status = 'CLOSED'
    GROUP BY customer_id
) x
WHERE x.total_sales >= :p_min_sales;
~~~

Inline view phù hợp để chia query thành các tầng logic cục bộ. Nó không phải schema view và không tồn tại sau khi statement kết thúc.

### 9.3. Common Table Expression (CTE)

WITH clause đặt tên cho một query block để dễ đọc và tái sử dụng trong cùng statement:

~~~sql
WITH customer_sales AS (
    SELECT customer_id,
           SUM(total_amount) AS total_sales
    FROM orders
    WHERE status = 'CLOSED'
    GROUP BY customer_id
),
high_value_customers AS (
    SELECT customer_id, total_sales
    FROM customer_sales
    WHERE total_sales >= :p_min_sales
)
SELECT customer_id, total_sales
FROM high_value_customers
ORDER BY total_sales DESC;
~~~

CTE giúp tách logic phức tạp thành các phần có tên. Oracle có thể inline/merge query block hoặc chọn cách thực thi khác; CTE không mặc định là bảng tạm vật lý.

### 9.4. Khi nào CTE tốt hơn view?

CTE thường phù hợp khi:

- Query chỉ dùng trong một statement.
- Các tầng biến đổi chỉ có ý nghĩa cục bộ.
- Muốn đặt tên cho intermediate result để dễ đọc.
- Không muốn tạo và quản lý schema object chỉ cho một query.

View phù hợp khi nhiều câu SQL hoặc nhiều ứng dụng cần dùng cùng logic ổn định. Nếu logic được tái sử dụng rộng, view giảm nguy cơ mỗi nơi tự viết một phiên bản khác.

## 10. So sánh chi phí và khả năng DML

| Tiêu chí | Table | View | Materialized view | SELECT/CTE |
|---|---|---|---|---|
| Lưu hàng kết quả | Có | Không | Có | Không |
| Lưu định nghĩa query | Không phải mục đích chính | Có | Có | Trong câu SQL |
| Dữ liệu mới nhất | Theo DML vào bảng | Đọc bảng nguồn hiện tại | Theo lần refresh | Theo snapshot statement |
| DML trực tiếp | Có | Tùy khả năng updatable/trigger | Có giới hạn, phụ thuộc loại và cấu hình | DML theo statement gốc |
| Index riêng | Có | Không index trực tiếp trên view thông thường | Có | Không |
| Constraint riêng | Có | Không như table độc lập | Có một số metadata/constraint tùy loại, không thay nguồn | Không |
| Refresh | Không | Không | Có | Không |
| Query rewrite | Không áp dụng như MV | Không phải mục tiêu | Có thể | Optimizer tối ưu query trực tiếp |
| Storage | Dữ liệu và index | Định nghĩa/metadata | Kết quả và index | Không lưu schema object |
| Bảo trì | DML/schema/backup | Thay đổi định nghĩa/dependency | Refresh/log/job/storage | Duy trì SQL ở code |

Lưu ý: MV là đối tượng lưu kết quả truy vấn nhưng không nên xem như một table nghiệp vụ thông thường có thể tự do cập nhật theo mọi cách. Hành vi DML của MV phụ thuộc định nghĩa, refresh method và Oracle release; thường nên quản lý nội dung MV qua refresh.

## 11. Cây quyết định lựa chọn

~~~text
Dữ liệu này có phải nguồn sự thật cần lưu và cập nhật?
                    |
             +------+------+
             |             |
            Có            Không
             |             |
           TABLE      Cần tái sử dụng
                      logic SQL nhiều nơi?
                           |
                     +-----+-----+
                     |           |
                    Có          Không
                     |           |
                    VIEW     Cần lưu trước kết quả
                             để tăng tốc đọc?
                                  |
                            +-----+-----+
                            |           |
                           Có          Không
                            |           |
                    MATERIALIZED     SELECT / CTE /
                       VIEW          INLINE VIEW
                            |
                  Có chấp nhận refresh lag?
                            |
                  Đánh giá FAST/COMPLETE,
                  ON DEMAND/ON COMMIT,
                  storage và query rewrite
~~~

Cây quyết định chỉ là điểm bắt đầu. Một hệ thống có thể kết hợp nhiều loại: bảng nguồn, view làm giao diện logic, materialized view cho báo cáo, và CTE cho các bước xử lý cục bộ.

## 12. Ví dụ thiết kế một chức năng báo cáo đơn hàng

Giả sử ứng dụng có ba nhu cầu:

1. Màn hình chi tiết đơn hàng cần trạng thái hiện hành.
2. Nhiều chức năng cần cùng một JOIN đơn hàng-khách hàng.
3. Dashboard cần tổng doanh thu theo khách hàng trong 12 tháng, được cập nhật mỗi giờ.

Thiết kế có thể là:

### 12.1. Table cho dữ liệu gốc

ORDERS và CUSTOMERS là nguồn sự thật, có PK/FK/constraint/index phù hợp.

### 12.2. View cho giao diện chi tiết dùng chung

~~~sql
CREATE OR REPLACE VIEW order_detail_v AS
SELECT o.order_id,
       o.order_date,
       o.status,
       o.total_amount,
       c.customer_id,
       c.customer_name,
       c.region_code
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id;
~~~

Các chức năng dùng chung định nghĩa JOIN và tên cột.

### 12.3. Materialized view cho dashboard

~~~sql
CREATE MATERIALIZED VIEW mv_customer_month_sales
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT customer_id,
       TRUNC(order_date, 'MM') AS sales_month,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_sales
FROM orders
WHERE status = 'CLOSED'
GROUP BY customer_id, TRUNC(order_date, 'MM');
~~~

Job refresh chạy theo giờ. Dashboard chấp nhận dữ liệu trễ tối đa theo lịch refresh và cần hiển thị thời điểm cập nhật gần nhất.

### 12.4. CTE cho một báo cáo đặc thù

Nếu một báo cáo chỉ dùng một lần để phân tích top khách hàng trong khoảng ngày do người dùng chọn, có thể dùng CTE thay vì tạo view mới:

~~~sql
WITH sales_by_customer AS (
    SELECT customer_id,
           SUM(total_amount) AS total_sales
    FROM orders
    WHERE status = 'CLOSED'
      AND order_date >= :p_from_date
      AND order_date < :p_to_date
    GROUP BY customer_id
)
SELECT customer_id, total_sales
FROM sales_by_customer
WHERE total_sales >= :p_min_sales
ORDER BY total_sales DESC;
~~~

Mỗi loại phục vụ một nhu cầu cụ thể; không cần ép tất cả logic vào một object.

## 13. Bảo mật và quyền truy cập

Table, view và materialized view đều là schema object, nhưng cách cấp quyền và công bố dữ liệu cần được cân nhắc.

### 13.1. View làm lớp công bố dữ liệu

Ví dụ chỉ công bố một số cột:

~~~sql
CREATE OR REPLACE VIEW customer_public_v AS
SELECT customer_id,
       customer_name,
       region_code
FROM customers
WHERE customer_status = 'ACTIVE';
~~~

Có thể cấp SELECT trên view cho role phù hợp thay vì cấp quyền đọc trực tiếp toàn bộ bảng cơ sở:

~~~sql
GRANT SELECT ON customer_public_v TO reporting_role;
~~~

View có thể giúp giới hạn cột/hàng trong giao diện dữ liệu, nhưng cần xem xét quyền underlying object, view owner, definer/invoker rights của PL/SQL gọi view, VPD/RLS và các đường truy cập khác. Không dùng view như biện pháp bảo mật duy nhất nếu dữ liệu nhạy cảm.

### 13.2. MV là bản sao dữ liệu

MV lưu kết quả tại thời điểm refresh. Khi cấp quyền đọc MV, người dùng có thể đọc dữ liệu đã materialize mà không cần trực tiếp truy vấn bảng nguồn trong mỗi statement, tùy cách thiết kế quyền và refresh owner.

Cần bảo vệ cả:

- Dữ liệu trong MV.
- Quyền refresh và quyền truy cập bảng nguồn.
- Job credentials/owner.
- Log hoặc bảng trung gian.
- Chính sách refresh sau khi quyền hoặc dữ liệu nhạy cảm thay đổi.

Nếu view lọc dữ liệu theo người dùng nhưng MV lưu một tập dữ liệu rộng hơn, cần đảm bảo query đọc MV vẫn áp dụng đúng phạm vi quyền. Không materialize dữ liệu nhiều tenant rồi cấp quyền đọc trực tiếp nếu không có cơ chế phân tách phù hợp.

## 14. Dependency và thay đổi schema

View và MV phụ thuộc vào bảng, cột, function hoặc object khác trong định nghĩa query.

Nếu đổi tên/xóa cột nguồn, view có thể INVALID và cần compile lại hoặc sửa định nghĩa. Có thể kiểm tra:

~~~sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_type IN ('VIEW', 'MATERIALIZED VIEW')
ORDER BY object_type, object_name;
~~~

Xem lỗi compile của view:

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE type = 'VIEW'
ORDER BY name, sequence;
~~~

Khi thay đổi schema, cần xem dependency và triển khai theo thứ tự: bảng/column, view, MV, trigger, package, grants và ứng dụng phụ thuộc.

Không giả định CREATE OR REPLACE VIEW sẽ giữ nguyên mọi hành vi hoặc tương thích với mọi consumer nếu thứ tự/cấu trúc cột thay đổi.

## 15. Theo dõi materialized view

Một số view metadata hữu ích:

~~~sql
SELECT mview_name,
       refresh_mode,
       refresh_method,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM user_mviews
ORDER BY mview_name;
~~~

Xem các job refresh:

~~~sql
SELECT job_name,
       enabled,
       state,
       last_start_date,
       last_run_duration,
       next_run_date
FROM user_scheduler_jobs
WHERE job_name LIKE 'JOB_REFRESH_%'
ORDER BY job_name;
~~~

Xem lịch sử job:

~~~sql
SELECT log_date,
       job_name,
       status,
       run_duration,
       error#,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name = 'JOB_REFRESH_CUSTOMER_SALES'
ORDER BY log_date DESC;
~~~

Theo dõi:

- Lần refresh gần nhất có thành công không.
- MV đang FRESH hay STALE.
- Thời gian refresh và độ trễ so với lịch.
- Lượng dữ liệu thay đổi ở bảng nguồn.
- Dung lượng MV và index.
- Refresh có cạnh tranh với batch DML nguồn không.
- Job có bị chạy chồng hoặc thất bại lặp lại không.

Không chỉ giám sát query đọc; refresh cũng là một workload database cần capacity và lịch vận hành.

## 16. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng view với kỳ vọng lưu sẵn kết quả | Query vẫn đọc/tính từ bảng nguồn | Dùng MV nếu cần materialize |
| Dùng MV khi cần dữ liệu tức thời | Người dùng đọc dữ liệu stale | View/table hoặc refresh phù hợp hơn |
| Nghĩ view luôn chậm hơn table | Bỏ qua query transformation của optimizer | So sánh execution plan và runtime |
| Tạo MV nhưng không có refresh plan | Kết quả cũ kéo dài | Chọn ON DEMAND/ON COMMIT và giám sát |
| Giả định FAST refresh luôn được hỗ trợ | CREATE/refresh thất bại hoặc phải complete | Dùng EXPLAIN_MVIEW và kiểm tra log/capability |
| Dùng ON COMMIT cho MV lớn | Commit DML nguồn tăng chi phí | Đánh giá ON DEMAND hoặc thiết kế khác |
| Dùng CTE như bảng tạm vật lý | Hiểu sai storage và lifetime | CTE chỉ thuộc một statement |
| Nghĩ mọi view đều updatable | DML lỗi hoặc không ánh xạ được | Kiểm tra USER_UPDATABLE_COLUMNS, trigger |
| Dùng DISTINCT/GROUP BY rồi mong UPDATE tự suy ra hàng nguồn | Không có ánh xạ DML rõ ràng | Dùng base table, INSTEAD OF trigger hoặc quy trình riêng |
| Dùng view làm lớp bảo mật duy nhất | Có thể còn đường truy cập khác | Thiết kế grants, VPD/RLS và quyền hệ thống |
| Tạo index cho MV mà không xem query | Tăng refresh/storage cost | Index theo predicate thực tế |
| Không kiểm tra dependency khi đổi bảng | View/MV có thể INVALID hoặc sai logic | Kiểm tra USER_OBJECTS/USER_ERRORS và triển khai theo thứ tự |

## 17. Bài thực hành trên schema lab

Các ví dụ dưới đây dùng bảng thử riêng. Chỉ chạy trên schema được phép và không thay đổi bảng nghiệp vụ production.

### 17.1. Tạo bảng nguồn

~~~sql
CREATE TABLE lab_sales (
    sale_id NUMBER CONSTRAINT pk_lab_sales PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    amount NUMBER(12,2) NOT NULL
);

INSERT INTO lab_sales VALUES (1, 10, DATE '2026-01-10', 'CLOSED', 100);
INSERT INTO lab_sales VALUES (2, 10, DATE '2026-01-15', 'CLOSED', 150);
INSERT INTO lab_sales VALUES (3, 20, DATE '2026-01-20', 'OPEN', 200);
COMMIT;
~~~

### 17.2. Tạo view

~~~sql
CREATE OR REPLACE VIEW lab_closed_sales_v AS
SELECT sale_id, customer_id, sale_date, amount
FROM lab_sales
WHERE status = 'CLOSED';
~~~

Đọc:

~~~sql
SELECT *
FROM lab_closed_sales_v
ORDER BY sale_id;
~~~

Thay đổi một hàng nguồn rồi commit:

~~~sql
UPDATE lab_sales
SET status = 'OPEN'
WHERE sale_id = 1;

COMMIT;
~~~

Truy vấn view tiếp theo không còn thấy sale_id 1 vì view tính lại từ bảng nguồn.

### 17.3. Tạo materialized view

~~~sql
CREATE MATERIALIZED VIEW lab_customer_sales_mv
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT customer_id,
       COUNT(*) AS sale_count,
       SUM(amount) AS total_amount
FROM lab_sales
WHERE status = 'CLOSED'
GROUP BY customer_id;
~~~

Đọc kết quả:

~~~sql
SELECT *
FROM lab_customer_sales_mv
ORDER BY customer_id;
~~~

Tiếp tục thay đổi dữ liệu nguồn và COMMIT:

~~~sql
INSERT INTO lab_sales VALUES (
    4, 10, DATE '2026-02-01', 'CLOSED', 250
);
COMMIT;
~~~

View trực tiếp sẽ phản ánh hàng mới. MV vẫn giữ kết quả cũ cho đến khi refresh:

~~~sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'LAB_CUSTOMER_SALES_MV',
        method => 'C'
    );
END;
/
~~~

Sau refresh, truy vấn MV phản ánh tổng mới.

### 17.4. Dùng CTE cho kết quả cục bộ

~~~sql
WITH customer_totals AS (
    SELECT customer_id,
           SUM(amount) AS total_amount
    FROM lab_sales
    WHERE status = 'CLOSED'
    GROUP BY customer_id
)
SELECT customer_id, total_amount
FROM customer_totals
WHERE total_amount >= 200;
~~~

CTE chỉ tồn tại trong statement này; không có object CUSTOMER_TOTALS được tạo trong schema.

### 17.5. Dọn object lab

Khi hoàn tất và không còn cần dữ liệu:

~~~sql
DROP MATERIALIZED VIEW lab_customer_sales_mv;
DROP VIEW lab_closed_sales_v;
DROP TABLE lab_sales PURGE;
~~~

Chỉ xóa các object lab do chính bạn tạo. DDL Oracle có implicit commit trong các ngữ cảnh thông thường; không chạy DROP khi còn transaction lab chưa kết thúc.

## 18. Quy trình chọn lựa trước khi tạo object

Trước khi tạo table/view/MV, trả lời lần lượt:

1. **Dữ liệu có phải nguồn sự thật không?** Nếu có, lưu trong table với key và constraint rõ.
2. **Logic có được tái sử dụng nhiều nơi không?** Nếu có, cân nhắc view.
3. **Kết quả có tốn kém để tính và được đọc nhiều không?** Nếu có, cân nhắc materialized view.
4. **Độ trễ dữ liệu tối đa chấp nhận được là bao nhiêu?** Nếu cần tức thời, view thường phù hợp hơn MV ON DEMAND.
5. **Có thể hỗ trợ FAST refresh không?** Kiểm tra query, log và EXPLAIN_MVIEW.
6. **DML qua view có cần thiết không?** Xác định updatability, CHECK OPTION hoặc INSTEAD OF trigger.
7. **Logic chỉ dùng trong một statement?** CTE hoặc inline view có thể đủ.
8. **Có cần index riêng trên kết quả không?** Table/MV có thể có index; view/CTE thông thường không có segment index riêng.
9. **Ai được đọc và refresh?** Thiết kế grants, owner, job và bảo vệ dữ liệu.
10. **Ai chịu trách nhiệm freshness và dependency?** Đặt lịch refresh, monitoring và quy trình triển khai schema.

## 19. Ghi nhớ cốt lõi

- **Table** lưu dữ liệu có thẩm quyền và hỗ trợ DML, constraint, index, transaction.
- **View** lưu định nghĩa SQL, không lưu các hàng kết quả; query view đọc dữ liệu nguồn theo snapshot hiện tại.
- **Materialized view** lưu trước kết quả truy vấn; phải có refresh strategy và chấp nhận freshness theo chính sách đó.
- **SELECT/CTE/inline view** phục vụ logic cục bộ trong statement, không tạo schema object bền vững.
- View không mặc định chậm; optimizer có thể merge view và đẩy predicate xuống nguồn.
- View chỉ updatable khi Oracle ánh xạ DML rõ ràng; aggregate, GROUP BY, DISTINCT và cấu trúc phức tạp thường hạn chế DML.
- WITH CHECK OPTION bảo đảm hàng DML qua view tiếp tục thỏa predicate; WITH READ ONLY cấm DML qua view.
- INSTEAD OF trigger có thể định nghĩa DML cho view phức tạp nhưng làm tăng trách nhiệm xử lý.
- MV có thể dùng COMPLETE, FAST hoặc FORCE refresh; khả năng FAST phụ thuộc query và materialized view log.
- ON COMMIT giảm độ trễ nhưng làm tăng chi phí commit của transaction nguồn; ON DEMAND cho phép chủ động lịch refresh.
- Query rewrite có thể cho optimizer dùng MV thay truy vấn nguồn khi điều kiện phù hợp; xác nhận bằng execution plan.
- Lựa chọn đúng phụ thuộc nguồn sự thật, độ mới dữ liệu, read/write ratio, query cost, storage, quyền và chi phí vận hành.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — CREATE VIEW, CREATE MATERIALIZED VIEW, SELECT, WITH clause và DML qua view.
- [Oracle Database Data Warehousing Guide](https://docs.oracle.com/en/database/) — Materialized views, refresh và query rewrite.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing tables, views, indexes và schema objects.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_MVIEW và DBMS_SCHEDULER.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — USER_MVIEWS, USER_UPDATABLE_COLUMNS, USER_OBJECTS và scheduler views.

Khả năng updatable, fast refresh, query rewrite và một số giới hạn cú pháp phụ thuộc phiên bản Oracle và định nghĩa query. Hãy kiểm tra metadata/capability trên release thực tế, xem execution plan và đo cả chi phí đọc lẫn chi phí refresh trước khi chọn giải pháp production.

