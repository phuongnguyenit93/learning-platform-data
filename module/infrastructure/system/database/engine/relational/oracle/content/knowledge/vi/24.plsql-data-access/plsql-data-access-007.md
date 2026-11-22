# Khóa dòng bằng cursor FOR UPDATE và WHERE CURRENT OF trong PL/SQL

Một quy trình xử lý đơn hàng thường cần đọc một hàng, kiểm tra trạng thái hiện tại rồi cập nhật chính hàng đó. Nếu ứng dụng chỉ SELECT trước, xử lý một lúc rồi UPDATE sau, session khác có thể thay đổi hàng trong khoảng thời gian ở giữa. Khi đó quyết định của chương trình có thể dựa trên dữ liệu đã cũ. Oracle cung cấp cơ chế **SELECT ... FOR UPDATE** để đọc hàng đồng thời khóa hàng đó, và cú pháp **WHERE CURRENT OF** để UPDATE hoặc DELETE đúng hàng mà cursor đang đứng tại.

Trong PL/SQL, cursor khai báo với FOR UPDATE cho phép chương trình duyệt tập hàng có khóa. Mỗi lần FETCH, cursor được định vị tại một hàng; câu UPDATE hoặc DELETE dùng WHERE CURRENT OF cursor_name sẽ tác động vào hàng hiện tại mà không cần tự truyền lại khóa chính hoặc ROWID. Khóa hàng được giữ đến khi transaction COMMIT hoặc ROLLBACK. Đóng cursor không giải phóng khóa.

Bài học thuộc nhóm **PL/SQL và dữ liệu** của Database Engine Relational Oracle. Nội dung giải thích cursor FOR UPDATE, mệnh đề OF, WAIT/NOWAIT/SKIP LOCKED, WHERE CURRENT OF, vòng đời khóa, xử lý đồng thời, deadlock và cách dùng cursor khóa trong quy trình cập nhật dữ liệu an toàn.

Sau bài này, bạn có thể:

- Phân biệt cursor đọc thông thường với cursor có FOR UPDATE.
- Dùng SELECT ... FOR UPDATE để khóa các hàng cần xử lý.
- Khai báo cursor tường minh với FOR UPDATE OF.
- Chọn WAIT, NOWAIT hoặc SKIP LOCKED theo chính sách concurrency.
- Dùng WHERE CURRENT OF để UPDATE/DELETE hàng hiện tại của cursor.
- Hiểu sự khác nhau giữa vị trí cursor, row lock và transaction boundary.
- Tránh COMMIT giữa lúc đang fetch cursor FOR UPDATE.
- Thiết kế worker queue bằng SKIP LOCKED khi semantics cho phép.
- Xử lý lỗi khóa, timeout và deadlock.
- Nhận biết giới hạn của SELECT FOR UPDATE trong truy vấn phức tạp.

> **Phạm vi ví dụ:** Cú pháp theo Oracle Database 19c. Các bảng có hậu tố _LAB dành cho schema thực hành. Hãy thử concurrency bằng hai session độc lập. Không chạy thử nghiệm khóa trên bảng nghiệp vụ đang phục vụ production.

## 1. Vì sao cần khóa dòng khi đọc để cập nhật?

Giả sử một ứng dụng xử lý yêu cầu nghỉ phép. Nó đọc số ngày còn lại của nhân viên, kiểm tra đủ điều kiện rồi trừ số ngày tương ứng. Nếu hai session cùng đọc một số dư trước khi session nào cập nhật, cả hai có thể cùng cho rằng yêu cầu hợp lệ.

~~~text
SESSION A                         SESSION B
---------                         ---------
SELECT balance = 5
                                  SELECT balance = 5
Check request 4 days
                                  Check request 4 days
UPDATE balance = 1
                                  UPDATE balance = 1
COMMIT
                                  COMMIT
~~~

Đây là dạng race condition trong mẫu read-then-write. Kết quả có thể sai nếu ứng dụng ghi lại giá trị tính từ một snapshot cũ mà không kiểm soát xung đột.

Một cách là đưa điều kiện vào chính câu UPDATE:

~~~sql
UPDATE leave_balance_lab
SET remaining_days = remaining_days - :requested_days
WHERE employee_id = :employee_id
  AND remaining_days >= :requested_days;
~~~

Sau đó kiểm tra SQL%ROWCOUNT. Với quy trình cần đọc nhiều trường, kiểm tra nhiều điều kiện hoặc thực hiện một số thao tác dựa trên hàng đang xử lý, SELECT FOR UPDATE là công cụ phù hợp:

~~~sql
SELECT remaining_days
FROM leave_balance_lab
WHERE employee_id = :employee_id
FOR UPDATE;
~~~

Oracle khóa hàng được chọn để transaction khác không thể đồng thời sửa cùng hàng cho đến khi transaction hiện tại kết thúc.

## 2. Cursor thông thường và cursor FOR UPDATE

### 2.1. Cursor đọc thông thường

Cursor thông thường truy vấn và fetch dữ liệu theo read consistency. Nó không lấy row lock chỉ vì đọc hàng:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 10;

    l_employee c_employee%ROWTYPE;
BEGIN
    OPEN c_employee;
    FETCH c_employee INTO l_employee;
    CLOSE c_employee;
END;
/
~~~

Trong khi cursor đọc, session khác vẫn có thể cập nhật các hàng đó. Cursor đọc nhìn dữ liệu nhất quán theo snapshot của câu truy vấn; nó không hứa giữ nguyên giá trị cho đến khi chương trình quyết định UPDATE.

### 2.2. Cursor có FOR UPDATE

Thêm FOR UPDATE vào câu SELECT:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 10
        FOR UPDATE;
BEGIN
    OPEN c_employee;
    -- Cac hang trong tap ket qua duoc khoa cho transaction.
    CLOSE c_employee;
    ROLLBACK;
END;
/
~~~

Khi cursor FOR UPDATE được mở, Oracle khóa các hàng thuộc tập kết quả theo semantics của SELECT FOR UPDATE. Các transaction khác muốn UPDATE/DELETE những hàng đang bị khóa phải chờ, hoặc nhận lỗi nếu câu truy vấn yêu cầu NOWAIT/WAIT timeout.

### 2.3. FOR UPDATE không có nghĩa khóa toàn bộ bảng

SELECT FOR UPDATE khóa các hàng được chọn trong các bảng được chỉ định theo câu truy vấn. Nó không mặc định biến câu SELECT thành table lock độc quyền. DML vẫn có thể xảy ra đồng thời trên các hàng khác nếu không có xung đột với những hàng đang bị khóa.

Oracle cũng dùng các khóa ở cấp bảng phục vụ phối hợp DML/DDL; nhưng mục đích của FOR UPDATE trong ví dụ là bảo vệ các hàng được chọn.

### 2.4. Khi nào cursor FOR UPDATE hữu ích?

- Đọc một hàng và cập nhật chính hàng đó theo nhiều điều kiện nghiệp vụ.
- Duyệt các hàng chờ xử lý và đánh dấu trạng thái.
- Chọn bản ghi công việc để một worker nhận quyền xử lý.
- Thực hiện UPDATE/DELETE hàng hiện tại mà không cần tự ghép lại predicate.
- Ngăn session khác thay đổi hàng giữa bước đọc và bước ghi.

Không cần dùng FOR UPDATE cho mọi SELECT. Khóa không cần thiết làm tăng blocking, giảm concurrency và có thể gây deadlock.

## 3. Khai báo cursor với FOR UPDATE

### 3.1. Cú pháp cơ bản

Mẫu:

~~~sql
CURSOR cursor_name IS
    select_statement
    FOR UPDATE [OF column_list]
    [NOWAIT | WAIT integer | SKIP LOCKED];
~~~

Mệnh đề FOR UPDATE thuộc câu SELECT của cursor. Các tùy chọn:

- FOR UPDATE: khóa các hàng được chọn trong những bảng liên quan theo quy tắc Oracle.
- OF column_list: xác định bảng hoặc các bảng có hàng cần khóa thông qua cột được liệt kê.
- NOWAIT: nếu hàng cần khóa đang bị session khác giữ, trả lỗi ngay.
- WAIT n: chờ tối đa n giây để lấy khóa.
- SKIP LOCKED: bỏ qua các hàng hiện đang bị transaction khác khóa.

Không kết hợp NOWAIT, WAIT và SKIP LOCKED như ba tùy chọn đồng thời; chọn chính sách phù hợp cho câu truy vấn.

### 3.2. FOR UPDATE OF

Ví dụ một cursor JOIN nhân viên với phòng ban:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT
            e.employee_id,
            e.full_name,
            e.department_id,
            d.department_name
        FROM employee_lock_lab e
        JOIN department_lock_lab d
          ON d.department_id = e.department_id
        WHERE e.department_id = 10
        FOR UPDATE OF e.monthly_salary;
BEGIN
    OPEN c_employee;
    CLOSE c_employee;
    ROLLBACK;
END;
/
~~~

OF e.monthly_salary xác định bảng EMPLOYEE_LOCK_LAB là bảng có các hàng cần khóa. Nó không có nghĩa chỉ riêng cột MONTHLY_SALARY bị khóa hoặc chỉ cột đó mới được UPDATE. Row lock bảo vệ hàng, không phải khóa từng cột.

Nếu truy vấn JOIN nhiều bảng và chỉ cần sửa hàng nhân viên, OF giúp làm rõ bảng cần khóa. Nếu cần sửa hàng ở nhiều bảng, có thể chỉ định cột thuộc từng bảng theo cú pháp hỗ trợ.

### 3.3. OF không bắt buộc cột phải nằm trong SELECT list

Danh sách OF dùng để xác định bảng thông qua cột được chỉ định. Cột được dùng trong OF không nhất thiết phải xuất hiện trong select list, miễn là nó hợp lệ trong câu truy vấn và được tham chiếu đúng alias.

### 3.4. FOR UPDATE trong cursor khai báo ở package/procedure

Cursor có thể được khai báo trong block PL/SQL, procedure hoặc package body. Điều quan trọng là cursor phải còn mở và đang định vị ở một hàng để dùng WHERE CURRENT OF. Nếu cần consumer bên ngoài package gọi quy trình khóa, hãy thiết kế API rõ ràng; không để cursor/transaction ownership bị che khuất.

## 4. Mở cursor, FETCH và vòng đời khóa

### 4.1. OPEN cursor FOR UPDATE

Ví dụ:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 10
        FOR UPDATE OF monthly_salary;
BEGIN
    OPEN c_employee;
    -- Cursor da mo va cac hang thuoc tap ket qua duoc khoa.
    CLOSE c_employee;
    ROLLBACK;
END;
/
~~~

OPEN bắt đầu thực thi cursor. Với FOR UPDATE, Oracle lấy các khóa cần thiết cho các hàng thuộc tập kết quả. Thời điểm và lượng công việc khóa thực tế còn phụ thuộc execution plan và cách truy vấn được thực thi; về mặt lập trình, hãy coi tập hàng kết quả là tập đã được yêu cầu khóa.

### 4.2. FETCH định vị hàng hiện tại

Sau FETCH, cursor có một hàng hiện tại. WHERE CURRENT OF dùng vị trí hiện tại này để xác định hàng cần UPDATE hoặc DELETE:

~~~sql
FETCH c_employee INTO l_employee;

UPDATE employee_lock_lab
SET monthly_salary = monthly_salary * 1.05
WHERE CURRENT OF c_employee;
~~~

Không cần viết lại predicate theo khóa chính. WHERE CURRENT OF gắn thao tác DML với hàng mà cursor đang đứng tại.

### 4.3. CLOSE cursor không giải phóng row locks

Đóng cursor chỉ kết thúc việc sử dụng cursor và giải phóng tài nguyên cursor. Row locks được lấy bởi SELECT FOR UPDATE vẫn được giữ đến khi transaction COMMIT hoặc ROLLBACK.

~~~text
OPEN FOR UPDATE
      |
      v
FETCH / UPDATE CURRENT ROW
      |
      v
CLOSE CURSOR
      |
      | row locks van duoc giu
      v
COMMIT hoac ROLLBACK
      |
      v
Giai phong transaction locks
~~~

Đây là điểm quan trọng khi vận hành. Đừng đóng cursor rồi nghĩ session khác có thể lập tức sửa hàng. Nếu cần giải phóng khóa, phải kết thúc transaction.

### 4.4. COMMIT/ROLLBACK kết thúc transaction

- COMMIT xác nhận thay đổi và giải phóng các khóa transaction.
- ROLLBACK hủy các thay đổi chưa commit và giải phóng khóa.
- ROLLBACK TO SAVEPOINT hoàn tác phần thay đổi sau savepoint theo quy tắc Oracle; transaction vẫn mở.

Không giữ transaction mở lâu sau khi đã xử lý xong cursor. Transaction dài giữ row locks lâu và tăng khả năng các session khác phải chờ.

## 5. WHERE CURRENT OF

### 5.1. Ý nghĩa

WHERE CURRENT OF cursor_name chỉ định hàng hiện tại của cursor FOR UPDATE đang mở. Câu lệnh UPDATE hoặc DELETE sẽ thao tác đúng hàng đó.

~~~sql
UPDATE table_name
SET column_name = expression
WHERE CURRENT OF cursor_name;
~~~

hoặc:

~~~sql
DELETE FROM table_name
WHERE CURRENT OF cursor_name;
~~~

Cursor phải được khai báo với FOR UPDATE, đang mở và đã FETCH đến một hàng hiện tại. Nếu cursor chưa mở, đã đóng hoặc không có hàng hiện tại hợp lệ, câu lệnh không thể dùng vị trí đó.

### 5.2. UPDATE hàng hiện tại

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 10
        FOR UPDATE OF monthly_salary;

    l_employee c_employee%ROWTYPE;
BEGIN
    OPEN c_employee;

    LOOP
        FETCH c_employee INTO l_employee;
        EXIT WHEN c_employee%NOTFOUND;

        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary * 1.05
        WHERE CURRENT OF c_employee;
    END LOOP;

    CLOSE c_employee;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employee%ISOPEN THEN
            CLOSE c_employee;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

Ví dụ tăng lương 5% cho nhân viên thuộc phòng ban 10. Cursor chọn và khóa các hàng; mỗi FETCH định vị một hàng; UPDATE CURRENT OF cập nhật hàng hiện tại.

### 5.3. DELETE hàng hiện tại

~~~sql
DECLARE
    CURSOR c_expired_job IS
        SELECT job_id, created_at
        FROM job_queue_lock_lab
        WHERE status = 'CANCELLED'
          AND created_at < SYSTIMESTAMP - INTERVAL '30' DAY
        FOR UPDATE OF status;

    l_job c_expired_job%ROWTYPE;
BEGIN
    OPEN c_expired_job;

    LOOP
        FETCH c_expired_job INTO l_job;
        EXIT WHEN c_expired_job%NOTFOUND;

        DELETE FROM job_queue_lock_lab
        WHERE CURRENT OF c_expired_job;
    END LOOP;

    CLOSE c_expired_job;
    COMMIT;
END;
/
~~~

DELETE CURRENT OF xóa hàng đang được cursor định vị. Sau khi xóa hàng hiện tại, tiếp tục FETCH để lấy hàng tiếp theo.

### 5.4. UPDATE/DELETE không cần tự truyền lại khóa chính

WHERE CURRENT OF hữu ích khi:

- Select list không chứa primary key.
- Cursor query có join hoặc biểu thức.
- Không muốn lặp lại predicate có thể bị sai lệch.
- Muốn diễn đạt rõ thao tác là trên hàng cursor đang xử lý.

Tuy nhiên, nếu logic nghiệp vụ cần dùng khóa chính cho audit/log/API, vẫn nên SELECT khóa đó vào record.

### 5.5. DML target phải phù hợp cursor

Với cursor JOIN nhiều bảng, FOR UPDATE OF e.salary khóa hàng của bảng được chỉ định. WHERE CURRENT OF dùng để UPDATE/DELETE hàng của bảng có thể được xác định theo cursor. Nếu cursor chứa nhiều bảng hoặc phép biến đổi phức tạp, hãy kiểm tra quy tắc updatable cursor và thử câu DML cụ thể trên release mục tiêu.

## 6. Cursor FOR LOOP và WHERE CURRENT OF

Cursor FOR LOOP tự động OPEN, FETCH và CLOSE cursor. Có thể kết hợp với WHERE CURRENT OF:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 20
        FOR UPDATE OF monthly_salary;
BEGIN
    FOR r_employee IN c_employee LOOP
        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 200
        WHERE CURRENT OF c_employee;
    END LOOP;

    COMMIT;
END;
/
~~~

Trong vòng lặp, cursor đang mở và hiện tại đang ở hàng r_employee. WHERE CURRENT OF c_employee nhắm đúng hàng đó.

### 6.1. Lợi ích của cursor FOR LOOP

- Không cần khai báo biến record riêng.
- Không phải tự viết OPEN/FETCH/EXIT/CLOSE.
- Code ngắn và dễ đọc.
- Oracle tự đóng cursor khi vòng lặp kết thúc bình thường hoặc rời khỏi phạm vi.

### 6.2. Lưu ý khi xử lý exception

Cursor FOR LOOP tự quản lý vòng đời cursor. Nếu có exception, cursor được đóng khi rời phạm vi vòng lặp. Tuy nhiên, transaction vẫn có thể còn mở và giữ khóa. Exception handler cần quyết định COMMIT/ROLLBACK theo đơn vị công việc.

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, monthly_salary
        FROM employee_lock_lab
        WHERE department_id = 20
        FOR UPDATE;
BEGIN
    FOR r IN c_employee LOOP
        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 200
        WHERE CURRENT OF c_employee;
    END LOOP;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

## 7. FOR UPDATE OF trong truy vấn JOIN

### 7.1. Khóa bảng cần cập nhật

Giả sử truy vấn đọc nhân viên và tên phòng ban:

~~~sql
SELECT
    e.employee_id,
    e.full_name,
    e.department_id,
    d.department_name
FROM employee_lock_lab e
JOIN department_lock_lab d
  ON d.department_id = e.department_id
WHERE d.department_id = 10
FOR UPDATE OF e.monthly_salary;
~~~

OF e.monthly_salary yêu cầu khóa các hàng của EMPLOYEE_LOCK_LAB tương ứng với kết quả. Bảng DEPARTMENT_LOCK_LAB chỉ được dùng để lọc/hiển thị; không được chỉ định làm bảng cần khóa trong ví dụ này.

### 7.2. Vì sao dùng OF?

Nếu truy vấn JOIN nhiều bảng và không chỉ rõ OF, Oracle có thể yêu cầu khóa các hàng của nhiều bảng trong kết quả theo quy tắc SELECT FOR UPDATE. Chỉ định OF giúp nêu rõ bảng mà chương trình định sửa và tránh khóa không cần thiết.

### 7.3. Cột trong OF không phải cột duy nhất được cập nhật

FOR UPDATE OF e.monthly_salary không giới hạn câu UPDATE chỉ được sửa MONTHLY_SALARY. Nó xác định bảng EMPLOYEE_LOCK_LAB để khóa hàng. Câu UPDATE vẫn có thể sửa cột khác của hàng nếu quyền và quy tắc DML cho phép.

### 7.4. Giới hạn của FOR UPDATE với truy vấn phức tạp

SELECT FOR UPDATE có các giới hạn. Theo các quy tắc Oracle, không thể áp dụng FOR UPDATE tùy ý cho query có các cấu trúc như:

- DISTINCT.
- GROUP BY.
- Set operators như UNION, UNION ALL, INTERSECT, MINUS.
- Aggregate functions hoặc một số query block/biểu thức không ánh xạ được hàng cần khóa.
- Một số view hoặc subquery có cấu trúc không hỗ trợ khóa trực tiếp.

Khi truy vấn cần tổng hợp để ra quyết định, thường phải xác định bảng/hàng nguồn cần khóa bằng một query riêng phù hợp, thay vì cố khóa kết quả aggregate.

Không nên dựa vào việc một câu SELECT phức tạp chạy được để kết luận FOR UPDATE luôn khóa đúng đối tượng nghiệp vụ. Hãy kiểm tra SQL Language Reference của release và xác minh row source/plan.

## 8. NOWAIT, WAIT và SKIP LOCKED

Ba tùy chọn này xác định hành vi khi hàng cần khóa đang bị transaction khác giữ.

### 8.1. Mặc định: chờ

Nếu không chỉ định NOWAIT/WAIT/SKIP LOCKED, session có thể chờ đến khi khóa được giải phóng. Điều này phù hợp khi chờ ngắn là chấp nhận được, nhưng ứng dụng phải hiểu thời gian chờ có thể kéo dài.

### 8.2. NOWAIT: không chờ

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE NOWAIT;
~~~

Nếu hàng đang bị khóa, Oracle trả lỗi ngay, thường là ORA-00054 trong tình huống resource busy với NOWAIT. Ứng dụng có thể:

- Thông báo bản ghi đang được xử lý.
- Chọn công việc khác.
- Retry có giới hạn sau backoff.
- Ghi log để theo dõi contention.

NOWAIT phù hợp khi user không muốn chờ hoặc worker cần phản hồi nhanh nếu tài nguyên bận.

### 8.3. WAIT n: chờ tối đa n giây

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE WAIT 5;
~~~

Session chờ tối đa 5 giây để lấy khóa. Nếu quá thời gian mà khóa chưa được giải phóng, Oracle trả lỗi timeout, thường là ORA-30006. Giá trị WAIT phải là số nguyên giây theo cú pháp Oracle.

WAIT hữu ích khi contention thường ngắn nhưng ứng dụng cần giới hạn thời gian chờ.

### 8.4. SKIP LOCKED: bỏ qua hàng đang bị khóa

~~~sql
SELECT job_id, payload
FROM job_queue_lock_lab
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

Nếu hàng READY đang bị session khác khóa, query bỏ qua hàng đó và trả các hàng chưa bị khóa khác. Đây là cơ chế hữu ích cho nhiều worker cùng lấy công việc từ queue.

SKIP LOCKED không chờ hàng bận và không bảo đảm thứ tự công bằng. Nếu hàng đầu tiên luôn bị giữ lâu, worker khác có thể tiếp tục lấy hàng sau; semantics xử lý cần chấp nhận điều đó.

### 8.5. So sánh

| Tùy chọn | Hành vi khi hàng bị khóa | Tình huống |
| --- | --- | --- |
| Không chỉ định | Chờ đến khi khóa được giải phóng | Chấp nhận chờ |
| NOWAIT | Báo lỗi ngay | Tương tác cần phản hồi tức thời |
| WAIT n | Chờ tối đa n giây | Chấp nhận chờ có giới hạn |
| SKIP LOCKED | Bỏ qua hàng bận, lấy hàng khác | Worker queue nhiều consumer |

Không chọn SKIP LOCKED cho nghiệp vụ cần xử lý đúng một hàng cụ thể, vì bỏ qua hàng đó có thể khiến caller hiểu nhầm rằng không có dữ liệu cần xử lý.

## 9. Mẫu worker queue với SKIP LOCKED

Một queue có nhiều worker thường cần bảo đảm một job không bị hai worker xử lý đồng thời. SKIP LOCKED cho phép worker lấy các hàng chưa được worker khác khóa.

### 9.1. Bảng queue lab

~~~sql
CREATE TABLE job_queue_lock_lab (
    job_id NUMBER PRIMARY KEY,
    payload VARCHAR2(200),
    status VARCHAR2(12) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    claimed_by VARCHAR2(30),
    claimed_at TIMESTAMP,
    CONSTRAINT ck_job_status_lock_lab
        CHECK (status IN ('READY', 'RUNNING', 'DONE', 'FAILED'))
);

INSERT INTO job_queue_lock_lab(job_id, payload, status)
VALUES (1, 'Send invoice', 'READY');

INSERT INTO job_queue_lock_lab(job_id, payload, status)
VALUES (2, 'Generate report', 'READY');

INSERT INTO job_queue_lock_lab(job_id, payload, status)
VALUES (3, 'Refresh cache', 'READY');

COMMIT;
~~~

### 9.2. Claim một job

~~~sql
DECLARE
    CURSOR c_job IS
        SELECT job_id, payload
        FROM job_queue_lock_lab
        WHERE status = 'READY'
        ORDER BY created_at, job_id
        FOR UPDATE SKIP LOCKED;

    l_job c_job%ROWTYPE;
BEGIN
    OPEN c_job;
    FETCH c_job INTO l_job;

    IF c_job%FOUND THEN
        UPDATE job_queue_lock_lab
        SET status = 'RUNNING',
            claimed_by = 'WORKER_A',
            claimed_at = SYSTIMESTAMP
        WHERE CURRENT OF c_job;

        DBMS_OUTPUT.PUT_LINE(
            'Claimed job ' || l_job.job_id ||
            ': ' || l_job.payload
        );
    END IF;

    CLOSE c_job;
    COMMIT;
END;
/
~~~

Commit sau khi cập nhật trạng thái RUNNING sẽ giải phóng khóa. Các worker khác nhìn thấy job không còn READY và không claim lại theo query này.

### 9.3. Tách claim và xử lý công việc

Không giữ transaction/row lock trong lúc thực hiện công việc dài như gọi API, gửi email hoặc xử lý tệp. Quy trình thường là:

1. Mở transaction ngắn.
2. SELECT FOR UPDATE SKIP LOCKED để claim job.
3. Cập nhật RUNNING, worker ID và timestamp.
4. COMMIT để giải phóng khóa.
5. Xử lý công việc ngoài transaction.
6. Mở transaction mới, cập nhật DONE hoặc FAILED.

Mô hình này cần timeout/lease để khôi phục job bị bỏ dở nếu worker chết sau khi claim. claimed_at có thể giúp job scheduler xác định RUNNING quá lâu và đưa vào quy trình recovery.

### 9.4. Claim nhiều job theo batch

Có thể dùng FETCH BULK COLLECT LIMIT với cursor FOR UPDATE SKIP LOCKED:

~~~sql
DECLARE
    CURSOR c_job IS
        SELECT job_id
        FROM job_queue_lock_lab
        WHERE status = 'READY'
        ORDER BY created_at, job_id
        FOR UPDATE SKIP LOCKED;

    TYPE job_id_tab IS TABLE OF job_queue_lock_lab.job_id%TYPE
        INDEX BY PLS_INTEGER;

    l_job_ids job_id_tab;
BEGIN
    OPEN c_job;

    FETCH c_job
    BULK COLLECT INTO l_job_ids
    LIMIT 20;

    FOR i IN 1 .. l_job_ids.COUNT LOOP
        UPDATE job_queue_lock_lab
        SET status = 'RUNNING',
            claimed_by = 'WORKER_BATCH',
            claimed_at = SYSTIMESTAMP
        WHERE job_id = l_job_ids(i);
    END LOOP;

    CLOSE c_job;
    COMMIT;
END;
/
~~~

Ở ví dụ batch, DML dùng job_id thay vì WHERE CURRENT OF vì collection chứa các ID sau bulk fetch. Cursor vẫn khóa các hàng đã fetch; transaction commit sau khi cập nhật trạng thái. Nếu cần xử lý từng hàng bằng CURRENT OF, fetch từng hàng hoặc thiết kế logic phù hợp.

### 9.5. SKIP LOCKED không tự tạo exactly-once processing

SKIP LOCKED giúp tránh hai worker cùng claim một hàng đang bị khóa tại thời điểm đó. Nó không bảo đảm công việc bên ngoài chỉ chạy đúng một lần:

- Worker có thể commit RUNNING rồi chết trước khi xử lý.
- Worker có thể hoàn tất API bên ngoài rồi chết trước khi cập nhật DONE.
- Job có thể được retry sau lease timeout.

Consumer và tác động ngoài database vẫn cần idempotency key, retry có kiểm soát và quy trình recovery.

## 10. Deadlock và thứ tự khóa

### 10.1. Cursor FOR UPDATE không loại bỏ deadlock

Hai session có thể khóa nhiều hàng theo thứ tự ngược:

~~~text
Session A: lock row 1 -> request row 2
Session B: lock row 2 -> request row 1
                     |
                     v
                 ORA-00060
~~~

FOR UPDATE chỉ lấy khóa; nó không tự giải quyết thứ tự khóa giữa các transaction.

### 10.2. Duy trì thứ tự khóa nhất quán

Nếu nghiệp vụ cần khóa nhiều tài khoản, hãy khóa theo account_id tăng dần trong mọi code path. Nếu một transaction khóa CUSTOMER rồi ORDER, transaction khác cũng phải tuân theo cùng lock hierarchy.

### 10.3. Giữ transaction ngắn

- Không gọi REST/email khi đang giữ row lock.
- Không chờ người dùng nhập liệu.
- Chỉ khóa những hàng thật sự cần cập nhật.
- COMMIT/ROLLBACK ngay khi đơn vị công việc kết thúc.
- Tránh cursor FOR UPDATE trên tập hàng quá rộng nếu chỉ cần một số hàng.

### 10.4. Xử lý ORA-00060

Khi deadlock xảy ra, Oracle rollback statement được chọn để phá chu trình. Những DML thành công trước đó trong transaction có thể vẫn pending. Với nghiệp vụ cần atomicity, ứng dụng thường phải ROLLBACK toàn transaction, sau đó mới cân nhắc retry toàn bộ đơn vị công việc.

Không chỉ bắt lỗi rồi COMMIT những thay đổi trước đó nếu nghiệp vụ chưa hoàn chỉnh.

## 11. COMMIT khi cursor FOR UPDATE còn mở

Đây là lỗi phổ biến trong cursor loop.

### 11.1. Không COMMIT giữa các lần FETCH

Ví dụ không nên dùng:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, monthly_salary
        FROM employee_lock_lab
        FOR UPDATE;
BEGIN
    FOR r IN c_employee LOOP
        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 100
        WHERE CURRENT OF c_employee;

        COMMIT;
    END LOOP;
END;
/
~~~

COMMIT kết thúc transaction và giải phóng các row locks. Cursor FOR UPDATE không còn ở trạng thái khóa phù hợp để tiếp tục fetch; lần FETCH tiếp theo có thể phát sinh ORA-01002: fetch out of sequence. Cách làm còn phá vỡ tính nguyên tử của batch vì mỗi hàng đã được commit riêng.

### 11.2. Commit sau khi hoàn tất cursor

Mẫu đơn giản:

~~~sql
BEGIN
    FOR r IN c_employee LOOP
        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 100
        WHERE CURRENT OF c_employee;
    END LOOP;

    COMMIT;
END;
/
~~~

Nếu tập dữ liệu quá lớn và cần commit theo batch, không thể chỉ thêm COMMIT vào giữa một cursor FOR UPDATE rồi tiếp tục fetch. Hãy thiết kế lại quy trình theo các batch độc lập:

- Chọn một batch key range hoặc batch ID.
- Mở transaction mới cho batch.
- Claim/lock một số hàng.
- Cập nhật trạng thái hoặc dữ liệu của batch.
- Commit và kết thúc cursor.
- Bắt đầu batch kế tiếp bằng query mới.

Hoặc dùng queue với SKIP LOCKED để mỗi worker claim một tập công việc độc lập. Mỗi batch phải là một đơn vị công việc nghiệp vụ có thể commit riêng.

### 11.3. CLOSE cursor không thay thế COMMIT

Đóng cursor rồi mở cursor mới không tự giải phóng row locks của transaction trước. Nếu muốn session khác xử lý các hàng, transaction phải kết thúc. Ngược lại, COMMIT khi cursor FOR UPDATE còn mở có thể khiến cursor không tiếp tục fetch được. Hãy phối hợp đúng thứ tự: hoàn tất cursor, đóng cursor, rồi commit/rollback.

## 12. SELECT FOR UPDATE và optimistic concurrency

Không phải mọi cập nhật đều cần pessimistic row locking.

### 12.1. Pessimistic locking

SELECT FOR UPDATE là cách khóa trước khi thay đổi. Transaction giữ khóa trong thời gian kiểm tra và cập nhật. Phù hợp khi:

- Xung đột ghi thường xuyên.
- Quy trình cần đọc trạng thái rồi thực hiện quyết định nhiều bước.
- Không thể biểu diễn đầy đủ điều kiện trong một câu DML.

### 12.2. Optimistic locking

Có thể dùng cột version_no:

~~~sql
UPDATE employee_lock_lab
SET monthly_salary = :new_salary,
    version_no = version_no + 1
WHERE employee_id = :employee_id
  AND version_no = :old_version;
~~~

Nếu SQL%ROWCOUNT = 0, hàng đã thay đổi hoặc không còn tồn tại. Ứng dụng đọc lại và quyết định có thử lại không. Cách này tránh giữ row lock trong lúc client suy nghĩ, nhưng phải xử lý conflict.

### 12.3. Conditional UPDATE

Nếu nghiệp vụ chỉ cần một điều kiện đơn giản, có thể thực hiện atomically:

~~~sql
UPDATE inventory_lock_lab
SET available_qty = available_qty - :requested_qty
WHERE product_id = :product_id
  AND available_qty >= :requested_qty;
~~~

Kiểm tra SQL%ROWCOUNT = 1 để xác nhận cập nhật thành công. Cách này thường ngắn và hiệu quả hơn SELECT FOR UPDATE rồi UPDATE riêng nếu không cần các bước đọc khác.

### 12.4. Chọn chiến lược

| Yêu cầu | Cách cân nhắc |
| --- | --- |
| Cần đọc nhiều thuộc tính rồi quyết định sửa hàng | SELECT FOR UPDATE |
| Điều kiện cập nhật đơn giản, có thể đặt trong WHERE | Conditional UPDATE |
| Client đọc lâu trước khi gửi cập nhật | Optimistic version column |
| Nhiều worker cùng lấy job độc lập | FOR UPDATE SKIP LOCKED |
| Cần khóa nhiều hàng | Lock order nhất quán và transaction ngắn |

## 13. Giới hạn và lưu ý khi dùng SELECT FOR UPDATE

### 13.1. Không dùng với mọi query shape

SELECT FOR UPDATE có giới hạn với truy vấn chứa DISTINCT, GROUP BY, aggregate functions và set operators. Những query trả về kết quả tổng hợp không ánh xạ một-một đến hàng vật lý để khóa.

Nếu cần khóa hàng nguồn, hãy tách thành:

1. Query xác định khóa nghiệp vụ.
2. SELECT FOR UPDATE trên bảng nguồn theo các khóa đó.
3. Kiểm tra trạng thái mới nhất.
4. DML và kết thúc transaction.

### 13.2. View và join

Khả năng khóa qua view/join phụ thuộc view có thể cập nhật và các quy tắc key-preserved table. Với query join, dùng FOR UPDATE OF để chỉ định bảng cần khóa. Không giả định mọi view hoặc join đều hỗ trợ FOR UPDATE.

### 13.3. Cursor FOR UPDATE cần transaction phù hợp

Cursor FOR UPDATE thuộc transaction hiện tại. Nếu dùng connection pool, không trả connection về pool khi transaction còn mở. Đảm bảo commit/rollback trước khi connection được tái sử dụng.

### 13.4. Không khóa quá sớm

Nếu cursor được mở rồi chương trình thực hiện tính toán nặng, gọi API hoặc chờ user, row locks bị giữ lâu. Hãy hoàn thành các bước không cần khóa trước, sau đó mở cursor FOR UPDATE trong khoảng thời gian ngắn nhất có thể.

### 13.5. Tránh khóa toàn bộ tập không cần thiết

Predicate càng rộng thì số hàng bị khóa càng lớn. Dùng điều kiện lọc chính xác, index phù hợp và giới hạn batch theo nghiệp vụ. Không mở cursor FOR UPDATE trên toàn bảng chỉ để sau đó xử lý một vài hàng.

## 14. Chẩn đoán blocking và lock waits

Khi một session chờ khóa, DBA có thể quan sát session và blocker (cần quyền truy cập dynamic performance views):

~~~sql
SELECT
    sid,
    serial#,
    username,
    event,
    blocking_session,
    seconds_in_wait,
    wait_class
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

Có thể xem TX/TM enqueue:

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    l.type,
    l.id1,
    l.id2,
    l.lmode,
    l.request,
    l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
WHERE l.type IN ('TX', 'TM')
  AND (l.request > 0 OR l.block = 1)
ORDER BY s.sid, l.type;
~~~

Các view này giúp quan sát trạng thái tại thời điểm truy vấn. Chúng không thay thế việc hiểu SQL và transaction timeline. Trong RAC, cân nhắc GV$SESSION/GV$LOCK và instance ID.

Các wait event thường gặp gồm enqueues liên quan TX/TM. Hãy xem blocking_session, SQL ID, module/action và thời gian transaction để xác định blocker thực sự.

## 15. Bài thực hành hai session: quan sát FOR UPDATE

### 15.1. Tạo bảng lab

~~~sql
CREATE TABLE employee_lock_lab (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    monthly_salary NUMBER(12,2) NOT NULL,
    version_no NUMBER DEFAULT 0 NOT NULL
);

INSERT INTO employee_lock_lab VALUES (101, 'Nguyen An', 10, 2500, 0);
INSERT INTO employee_lock_lab VALUES (102, 'Tran Binh', 10, 3200, 0);
INSERT INTO employee_lock_lab VALUES (103, 'Le Chi', 20, 2800, 0);
COMMIT;
~~~

### 15.2. Session A mở cursor FOR UPDATE

Để quan sát blocking, hãy dùng một session tương tác và giữ transaction chưa kết thúc. Ví dụ trong Session A:

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE;
~~~

Không COMMIT/ROLLBACK ngay sau câu lệnh. Session A đang giữ khóa hàng 101.

### 15.3. Session B thử cập nhật cùng hàng

~~~sql
UPDATE employee_lock_lab
SET monthly_salary = monthly_salary + 100
WHERE employee_id = 101;
~~~

Session B sẽ chờ vì Session A đang giữ row lock. Sau khi Session A COMMIT hoặc ROLLBACK, Session B có thể tiếp tục.

### 15.4. Thử NOWAIT

Trong Session A, giữ khóa hàng 101. Session B chạy:

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE NOWAIT;
~~~

Session B nhận lỗi ngay nếu hàng đang bị khóa. Không cần chờ đến khi Session A kết thúc.

### 15.5. Thử WAIT

~~~sql
SELECT employee_id, full_name
FROM employee_lock_lab
WHERE employee_id = 101
FOR UPDATE WAIT 3;
~~~

Session B chờ tối đa ba giây.

### 15.6. Thử WHERE CURRENT OF

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, monthly_salary
        FROM employee_lock_lab
        WHERE employee_id IN (101, 102)
        ORDER BY employee_id
        FOR UPDATE;

    l_employee c_employee%ROWTYPE;
BEGIN
    OPEN c_employee;

    LOOP
        FETCH c_employee INTO l_employee;
        EXIT WHEN c_employee%NOTFOUND;

        UPDATE employee_lock_lab
        SET monthly_salary = monthly_salary + 50
        WHERE CURRENT OF c_employee;
    END LOOP;

    CLOSE c_employee;
    COMMIT;
END;
/
~~~

Kiểm tra kết quả:

~~~sql
SELECT employee_id, monthly_salary
FROM employee_lock_lab
ORDER BY employee_id;
~~~

### 15.7. Dọn bảng lab

Chỉ chạy sau khi cả hai session đã kết thúc transaction:

~~~sql
DROP TABLE employee_lock_lab PURGE;
~~~

DROP TABLE là DDL có implicit commit theo quy tắc Oracle. Chỉ chạy khi chắc chắn đây là bảng lab của bạn.

## 16. Các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| ORA-00054 với NOWAIT | Hàng/tài nguyên đang bị session khác khóa | Chọn hàng khác, báo bận hoặc retry có giới hạn |
| ORA-30006 với WAIT timeout | Hết thời gian chờ lấy khóa | Tăng timeout có lý do hoặc xử lý contention |
| ORA-01002 fetch out of sequence | COMMIT hoặc thao tác làm cursor FOR UPDATE không còn fetch hợp lệ | Không commit giữa các lần fetch; kết thúc cursor trước commit |
| ORA-00060 | Deadlock giữa các transaction | Rollback toàn đơn vị công việc nếu cần atomicity; sửa lock order |
| ORA-01001 invalid cursor | Dùng cursor đã đóng/chưa mở | Kiểm tra OPEN/CLOSE và phạm vi cursor |
| Không thể FOR UPDATE trên query | Query có DISTINCT/GROUP BY/aggregate/set operation hoặc cấu trúc không hỗ trợ | Tách query xác định hàng nguồn cần khóa |
| Worker xử lý trùng job | Claim không được commit đúng hoặc tác động ngoài DB không idempotent | Claim trạng thái trong transaction, idempotency và lease recovery |
| Session khác vẫn chờ sau CLOSE | CLOSE không giải phóng transaction row locks | COMMIT/ROLLBACK để giải phóng |

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| SELECT thông thường khóa hàng | SELECT thường dùng read consistency, không lấy row lock như FOR UPDATE |
| FOR UPDATE khóa toàn bảng | Nó khóa các hàng được chọn trong bảng được chỉ định |
| OF salary chỉ khóa cột salary | OF xác định bảng thông qua cột; row lock bảo vệ cả hàng |
| CLOSE cursor giải phóng row locks | Khóa giữ đến COMMIT/ROLLBACK |
| WHERE CURRENT OF dùng được với cursor bất kỳ | Cursor phải là cursor FOR UPDATE đang mở và có hàng hiện tại |
| WHERE CURRENT OF cần SELECT ROWID | Không cần tự lấy ROWID; cursor position xác định hàng |
| NOWAIT và WAIT giống nhau | NOWAIT lỗi ngay; WAIT chờ tối đa số giây |
| SKIP LOCKED phù hợp mọi truy vấn | Nó bỏ qua hàng bận, có thể không phù hợp nghiệp vụ cần đúng hàng |
| COMMIT giữa cursor loop là cách chia batch an toàn | Cursor FOR UPDATE có thể không fetch tiếp được và transaction bị chia nhỏ |
| FOR UPDATE loại bỏ deadlock | Lock order ngược vẫn tạo deadlock |
| FOR UPDATE luôn dùng được với GROUP BY | Query aggregate/grouping có giới hạn không thể khóa hàng kết quả theo cách đó |
| SKIP LOCKED bảo đảm exactly-once | Cần idempotency, trạng thái claim và recovery riêng |

## 18. Checklist dùng cursor FOR UPDATE an toàn

Trước khi triển khai:

1. Có thật sự cần khóa trước khi cập nhật không, hay conditional UPDATE đủ?
2. Cursor chỉ chọn các hàng cần thiết chưa?
3. Có chỉ định FOR UPDATE OF để khóa đúng bảng trong JOIN không?
4. WAIT/NOWAIT/SKIP LOCKED phù hợp với UX và semantics nghiệp vụ không?
5. Cursor có được FETCH đúng cách và kiểm tra %NOTFOUND không?
6. WHERE CURRENT OF tham chiếu đúng cursor đang mở không?
7. Transaction có kết thúc ngay sau xử lý không?
8. Có COMMIT giữa các lần FETCH không? Nếu có, thiết kế batch cần thay đổi.
9. Các luồng khóa nhiều hàng có cùng thứ tự không?
10. Có xử lý ORA-00054, ORA-30006 và ORA-00060 không?
11. Queue worker có idempotency và lease recovery không?
12. Connection pool có được trả connection sau COMMIT/ROLLBACK không?

## 19. Câu hỏi tự kiểm tra

1. SELECT thông thường khác SELECT FOR UPDATE ở điểm nào?
2. Cursor FOR UPDATE khóa những hàng nào?
3. FOR UPDATE OF column có nghĩa gì?
4. OF column có giới hạn cột được UPDATE không?
5. WHERE CURRENT OF dùng trong câu lệnh nào?
6. Cursor cần ở trạng thái nào để dùng WHERE CURRENT OF?
7. Vì sao không cần tự SELECT ROWID để dùng WHERE CURRENT OF?
8. CLOSE cursor có giải phóng row lock không?
9. Điều gì giải phóng row lock?
10. NOWAIT khác WAIT n thế nào?
11. SKIP LOCKED phù hợp với mô hình nào?
12. Vì sao SKIP LOCKED không bảo đảm fairness?
13. Vì sao không COMMIT giữa các lần FETCH của cursor FOR UPDATE?
14. ORA-01002 có thể xuất hiện trong trường hợp nào?
15. FOR UPDATE có dùng được với GROUP BY/DISTINCT/aggregate không?
16. Vì sao FOR UPDATE OF hữu ích trong query JOIN?
17. Cursor FOR UPDATE có loại bỏ deadlock không?
18. Khi nào conditional UPDATE phù hợp hơn SELECT FOR UPDATE?
19. Worker queue cần cơ chế gì ngoài SKIP LOCKED?
20. Sau ORA-00060, vì sao thường cần rollback toàn transaction?

**Gợi ý trả lời:**

1. SELECT thường đọc snapshot; FOR UPDATE đọc và khóa các hàng được chọn.
2. Các hàng thuộc tập kết quả trong các bảng được yêu cầu khóa.
3. Xác định bảng chứa cột đó để Oracle khóa các hàng tương ứng.
4. Không; row lock bảo vệ hàng, không phải khóa riêng cột.
5. UPDATE hoặc DELETE.
6. Cursor FOR UPDATE đang mở và đã FETCH đến một hàng hiện tại.
7. Cursor position đã xác định hàng cần DML.
8. Không.
9. COMMIT hoặc ROLLBACK transaction.
10. NOWAIT lỗi ngay; WAIT n chờ tối đa n giây.
11. Nhiều worker cùng claim job từ queue.
12. Hàng đang bị khóa bị bỏ qua; worker có thể xử lý hàng sau trước.
13. COMMIT kết thúc transaction và cursor FOR UPDATE có thể không fetch tiếp được; batch bị chia nhỏ.
14. Khi fetch cursor sai trình tự, đặc biệt sau commit trong cursor FOR UPDATE.
15. Các query shape đó có giới hạn và thường không thể khóa hàng nguồn trực tiếp bằng FOR UPDATE.
16. Để chỉ định bảng cần khóa trong join, tránh khóa hàng ở bảng không cần cập nhật.
17. Không; thứ tự khóa ngược vẫn có thể tạo chu trình.
18. Khi điều kiện nghiệp vụ có thể biểu diễn nguyên tử trong WHERE của UPDATE.
19. Idempotency, trạng thái claim, lease timeout và recovery.
20. Vì statement gây deadlock có thể bị rollback riêng, còn DML trước đó vẫn pending.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — Cursors Overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursors-overview.html): khai báo, mở, fetch và đóng cursor.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT FOR UPDATE, OF, WAIT, NOWAIT và SKIP LOCKED.
- [Oracle Database PL/SQL Language Reference — UPDATE Statement](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/UPDATE-statement.html): UPDATE và WHERE CURRENT OF.
- [Oracle Database PL/SQL Language Reference — DELETE Statement](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/DELETE-statement.html): DELETE và WHERE CURRENT OF.
- [Oracle Database Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): row locks, transaction và xử lý đồng thời.
- [Oracle Database Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transaction boundary, commit và rollback.

**Nguyên tắc cần nhớ:** Cursor FOR UPDATE khóa các hàng mà quy trình sắp đọc để cập nhật; FETCH xác định hàng hiện tại; WHERE CURRENT OF UPDATE/DELETE đúng hàng đó. Row locks tồn tại đến COMMIT/ROLLBACK chứ không mất khi CLOSE cursor. Hãy khóa đúng hàng, giữ transaction ngắn, không COMMIT giữa cursor fetch, và chọn NOWAIT/WAIT/SKIP LOCKED theo semantics nghiệp vụ.
