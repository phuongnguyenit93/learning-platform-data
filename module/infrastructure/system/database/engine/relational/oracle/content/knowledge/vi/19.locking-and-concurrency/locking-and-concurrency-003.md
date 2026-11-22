# SELECT FOR UPDATE và phạm vi dòng bị khóa trong Oracle Database

## 1. Vì sao cần khóa dòng trước khi cập nhật?

Trong một ứng dụng nhiều người dùng, nhiều session có thể cùng đọc và thay đổi một bản ghi. Một quy trình thường gặp là:

1. Đọc số dư tài khoản.
2. Kiểm tra số dư có đủ hay không.
3. Tính số dư mới trong ứng dụng.
4. Ghi số dư mới về database.

Nếu hai session cùng đọc một giá trị trước khi session nào cập nhật, cả hai có thể đưa ra quyết định dựa trên cùng trạng thái cũ. Một cập nhật có thể ghi đè kết quả của cập nhật còn lại.

Oracle tự động khóa các row khi thực hiện UPDATE hoặc DELETE. Tuy nhiên, nếu ứng dụng cần **đọc một row, giữ nguyên row đó trong lúc kiểm tra hoặc tính toán, rồi mới cập nhật**, có thể dùng **SELECT ... FOR UPDATE**.

SELECT FOR UPDATE là cơ chế khóa tường minh theo hướng pessimistic locking:

- Chọn những row cần bảo vệ.
- Lấy exclusive row lock trước khi DML tiếp theo chạy.
- Session khác không thể cập nhật, xóa hoặc lấy khóa xung đột trên các row đó cho đến khi transaction hiện tại kết thúc.
- Các row khác không nằm trong tập kết quả vẫn có thể được session khác cập nhật.

Điểm quan trọng của bài học là **phạm vi dòng bị khóa**. Phạm vi này phụ thuộc tập kết quả SELECT, các bảng tham gia JOIN và mệnh đề OF. Khóa dòng không đồng nghĩa khóa toàn bộ bảng.

> Các ví dụ dùng Oracle Database 19c. Tạo bảng lab trong schema riêng và chạy bằng hai database session độc lập để quan sát khóa. Không thử thao tác giữ khóa lâu trên production.

## 2. Cú pháp SELECT FOR UPDATE

Cú pháp thường dùng:

~~~sql
SELECT select_list
FROM   table_or_join
WHERE  condition
ORDER BY sort_expression
FOR UPDATE [OF column [, column ...]]
           [NOWAIT | WAIT integer | SKIP LOCKED];
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| SELECT ... FROM ... WHERE ... | Xác định tập row cần đọc và khóa |
| FOR UPDATE | Khóa các row được chọn từ các bảng trong query |
| OF column | Chỉ rõ bảng hoặc view nào có row cần khóa trong query JOIN |
| NOWAIT | Không chờ nếu row đang bị khóa; trả quyền điều khiển ngay |
| WAIT n | Chờ tối đa n giây để lấy khóa |
| SKIP LOCKED | Bỏ qua row đang bị transaction khác khóa |

Ví dụ đơn giản:

~~~sql
SELECT account_id, balance
FROM   accounts
WHERE  account_id = 1001
FOR UPDATE;
~~~

Oracle lấy khóa trên row tài khoản 1001 nếu row đó được tìm thấy. Khóa tồn tại cho đến khi transaction hiện tại COMMIT hoặc ROLLBACK.

SELECT FOR UPDATE không thay đổi dữ liệu. Nó chỉ lấy khóa để bảo vệ row trước khi một câu UPDATE/DELETE tiếp theo được thực hiện.

## 3. Phạm vi khóa trong một bảng

### 3.1. WHERE quyết định row nào được chọn

Giả sử bảng ACCOUNT_BALANCE_LAB có nhiều tài khoản:

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Chỉ row có ACCOUNT_ID = 10 thuộc tập kết quả và bị khóa.

Nếu điều kiện chọn nhiều row:

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE branch_id = 3
FOR UPDATE;
~~~

Các row thỏa BRANCH_ID = 3 đều được khóa. Những tài khoản thuộc chi nhánh khác không nằm trong tập kết quả nên không bị khóa bởi câu lệnh này.

Nếu bỏ WHERE:

~~~sql
SELECT account_id, balance
FROM account_balance_lab
FOR UPDATE;
~~~

Query chọn toàn bộ row của bảng, do đó có thể khóa toàn bộ các row được chọn. Đây là lý do phải cẩn thận khi chạy SELECT FOR UPDATE mà không có predicate giới hạn.

### 3.2. Chỉ khóa row được chọn, không khóa mọi row đã quét

Về mặt logic, Oracle khóa các row thuộc tập kết quả của SELECT. Một execution plan có thể đọc hoặc kiểm tra nhiều row hơn số row cuối cùng thỏa điều kiện; không nên hiểu rằng mọi row mà bộ máy từng đọc trong lúc tìm kết quả đều bị khóa.

Ví dụ:

~~~sql
SELECT order_id, status
FROM orders
WHERE customer_id = 100
  AND status = 'READY'
FOR UPDATE;
~~~

Mục tiêu là khóa các đơn của khách hàng 100 đang ở trạng thái READY. Các đơn đã SHIPPED hoặc thuộc khách hàng khác không nằm trong kết quả.

Nếu predicate có thể thay đổi do session khác đang cập nhật dữ liệu trong lúc câu SELECT FOR UPDATE chạy, Oracle có thể phải lấy khóa trên các row chưa thay đổi, dựng lại tập kết quả nhất quán rồi khởi động lại việc lấy khóa cho phần còn lại. Vì vậy, ứng dụng phải xử lý deadlock ORA-00060 nếu các thao tác đồng thời có thể làm thay đổi tập kết quả khóa.

### 3.3. Không có row được chọn thì không có row lock

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = -1
FOR UPDATE;
~~~

Nếu không có tài khoản -1, câu SELECT trả không dòng và không khóa row nào.

Điều này có hệ quả quan trọng: SELECT FOR UPDATE không khóa một khoảng trống để ngăn session khác INSERT row mới thỏa điều kiện. Oracle không dùng cơ chế next-key/gap lock kiểu một số hệ quản trị khác cho câu lệnh này.

Ví dụ, nếu chưa có tài khoản mang mã 500, hai session cùng SELECT FOR UPDATE với ACCOUNT_ID = 500 đều có thể không tìm thấy row. Việc không tìm thấy không bảo đảm một session khác không thể INSERT mã 500 sau đó.

Để bảo vệ tính duy nhất, dùng PRIMARY KEY hoặc UNIQUE constraint. Không dùng SELECT FOR UPDATE trên một tập rỗng để thay thế constraint.

## 4. SELECT FOR UPDATE trong JOIN: khóa bảng nào?

Đây là phần quan trọng nhất khi xác định phạm vi khóa.

### 4.1. Mặc định: khóa row được chọn từ mọi bảng trong query

Giả sử query JOIN EMPLOYEES và DEPARTMENTS:

~~~sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.job_id = 'SA_REP'
  AND d.location_id = 2500
FOR UPDATE;
~~~

Nếu không có mệnh đề OF, Oracle khóa các row được chọn từ cả EMPLOYEES và DEPARTMENTS. Điều này có thể khiến session khác không cập nhật được row phòng ban liên quan, dù mục đích của ứng dụng chỉ là chỉnh sửa nhân viên.

### 4.2. Dùng OF để giới hạn bảng có row bị khóa

Nếu chỉ muốn khóa row nhân viên:

~~~sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.job_id = 'SA_REP'
  AND d.location_id = 2500
FOR UPDATE OF e.salary;
~~~

Oracle khóa row được chọn từ EMPLOYEES; row trong DEPARTMENTS không bị khóa bởi câu lệnh này.

Nếu chỉ muốn khóa phòng ban:

~~~sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.job_id = 'SA_REP'
  AND d.location_id = 2500
FOR UPDATE OF d.department_name;
~~~

Lúc này row được chọn từ DEPARTMENTS là đối tượng khóa.

### 4.3. OF column không phải khóa riêng một cột

Tên cột trong OF chỉ dùng để xác định bảng hoặc view nào có row cần khóa. Oracle khóa **row** của bảng đó, không khóa riêng cột được ghi sau OF.

Ví dụ:

~~~sql
FOR UPDATE OF e.salary
~~~

không có nghĩa chỉ cột SALARY bị khóa còn các cột khác trong row vẫn có thể được cập nhật độc lập. Row của nhân viên được khóa; session khác không thể cập nhật một cột khác của cùng row đó cho đến khi khóa được giải phóng.

Tên cột trong OF không quan trọng về mặt chọn cột khóa; phải dùng tên cột thật, không dùng alias của biểu thức trong SELECT list. Nên ghi rõ alias bảng như e.salary để người đọc biết bảng nào được khóa.

### 4.4. Có thể chỉ định nhiều bảng

Trong một query JOIN, có thể chỉ định cột thuộc các bảng muốn khóa:

~~~sql
SELECT e.employee_id,
       d.department_id
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = 100
FOR UPDATE OF e.salary, d.department_name;
~~~

Các row được chọn từ cả hai bảng được khóa. Mỗi cột trong danh sách chỉ ra bảng tương ứng; nó không giới hạn khóa vào đúng cột đó.

### 4.5. Bảng so sánh phạm vi khóa

| Câu lệnh | Bảng có row bị khóa |
| --- | --- |
| JOIN hai bảng, FOR UPDATE | Các row được chọn từ cả hai bảng |
| JOIN hai bảng, FOR UPDATE OF e.salary | Các row được chọn từ EMPLOYEES |
| JOIN hai bảng, FOR UPDATE OF d.department_name | Các row được chọn từ DEPARTMENTS |
| JOIN hai bảng, FOR UPDATE OF e.salary, d.department_name | Các row được chọn từ cả hai bảng |

Đừng dùng OF như một điều kiện lọc. Điều kiện WHERE quyết định row nào được chọn; OF quyết định row của bảng nào trong tập kết quả sẽ bị khóa.

## 5. Khóa dòng khác khóa toàn bảng

SELECT FOR UPDATE lấy exclusive row locks trên các row được chọn. Oracle cũng quản lý khóa ở cấp bảng để bảo vệ thao tác DML, nhưng câu lệnh này không có nghĩa là lấy exclusive table lock trên toàn bảng.

Trong thực tế:

- Session khác có thể SELECT thông thường cùng các row đó và đọc phiên bản đã commit theo cơ chế read consistency của Oracle.
- Session khác muốn UPDATE hoặc DELETE row đã khóa phải chờ transaction giữ khóa kết thúc.
- Session khác vẫn có thể cập nhật row khác không bị khóa trong cùng bảng.
- Session khác không thể lấy một khóa xung đột trên cùng row bằng SELECT FOR UPDATE.

Ví dụ, A khóa tài khoản 10. B có thể cập nhật tài khoản 20, nhưng khi B cập nhật tài khoản 10 thì phải chờ A kết thúc transaction.

Đây là lý do row-level locking hỗ trợ nhiều giao dịch đồng thời hơn so với việc khóa toàn bảng. Nếu query khóa hàng trăm nghìn row, lợi ích này giảm đi và cần đánh giá lại thiết kế.

## 6. Khóa tồn tại trong bao lâu?

### 6.1. COMMIT giải phóng khóa

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;

UPDATE account_balance_lab
SET balance = balance - 100
WHERE account_id = 10;

COMMIT;
~~~

Sau COMMIT, các row lock của transaction được giải phóng. Session khác có thể tiếp tục lấy khóa hoặc cập nhật các row đó.

### 6.2. ROLLBACK cũng giải phóng khóa

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;

-- Sau khi kiểm tra, quyết định không thực hiện thay đổi.
ROLLBACK;
~~~

ROLLBACK kết thúc transaction và giải phóng các khóa. Nếu transaction đã thực hiện DML, các thay đổi của transaction cũng được hoàn tác.

### 6.3. ROLLBACK TO SAVEPOINT

Oracle có thể giải phóng các row lock được lấy sau savepoint khi rollback về savepoint đó. Những khóa được lấy trước savepoint vẫn thuộc transaction và tiếp tục được giữ.

~~~sql
SAVEPOINT before_lock;

SELECT account_id
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;

ROLLBACK TO before_lock;
~~~

Sau rollback về savepoint, khóa được lấy sau savepoint được giải phóng. Transaction vẫn tiếp tục hoạt động.

### 6.4. Đóng cursor không giải phóng row lock

Nếu SELECT FOR UPDATE được thực hiện qua explicit cursor, việc CLOSE cursor không kết thúc transaction và không tự giải phóng row lock. Khóa tiếp tục tồn tại đến COMMIT, ROLLBACK hoặc rollback về savepoint thích hợp.

Vì vậy, không được dùng thao tác đóng cursor thay cho kết thúc transaction.

## 7. NOWAIT, WAIT và SKIP LOCKED

Khi một row cần khóa đang bị session khác giữ, Oracle cần biết session hiện tại sẽ chờ, báo lỗi hay bỏ qua row đó.

### 7.1. Mặc định: chờ đến khi lấy được khóa

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Nếu row đã bị session khác khóa, câu lệnh chờ đến khi khóa được giải phóng. Nếu session kia COMMIT hoặc ROLLBACK, Oracle tiếp tục xử lý việc lấy khóa.

### 7.2. NOWAIT: không chờ

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE NOWAIT;
~~~

Nếu row đang bị khóa, Oracle trả lỗi ngay, thường là:

~~~text
ORA-00054: resource busy and acquire with NOWAIT specified
~~~

Ứng dụng có thể báo cho người dùng rằng bản ghi đang được người khác xử lý, hoặc thử lại sau theo chính sách phù hợp.

NOWAIT phù hợp với giao diện tương tác cần phản hồi nhanh, không muốn người dùng chờ một khóa không rõ thời gian.

### 7.3. WAIT n: chờ trong một khoảng thời gian

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE WAIT 5;
~~~

Oracle chờ tối đa 5 giây để lấy khóa. Nếu hết thời gian mà row vẫn đang bị khóa, có thể nhận:

~~~text
ORA-30006: resource busy; acquire with WAIT timeout expired
~~~

Giá trị sau WAIT là số nguyên giây trong cú pháp Oracle 19c. Chọn thời gian chờ theo SLA của ứng dụng; không nên đặt thời gian quá dài chỉ để che một transaction bị treo.

### 7.4. SKIP LOCKED: bỏ qua row đang bị khóa

~~~sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

Nếu một số row READY đã bị session khác khóa, Oracle bỏ qua chúng và cố lấy những row chưa bị khóa. Cơ chế này phù hợp với nhiều worker cùng lấy công việc từ một queue.

SKIP LOCKED không có nghĩa là row bị khóa đã biến mất hoặc không còn hợp lệ. Nó chỉ bị bỏ qua trong lần lấy dữ liệu hiện tại; worker khác có thể đang xử lý nó.

### 7.5. So sánh ba cách xử lý

| Tùy chọn | Row đang bị khóa | Trường hợp phù hợp |
| --- | --- | --- |
| Mặc định | Chờ đến khi row sẵn sàng | Quy trình cần đúng row, chấp nhận chờ |
| NOWAIT | Trả lỗi ngay | Giao diện cần phản hồi nhanh |
| WAIT n | Chờ tối đa n giây, sau đó lỗi | Có thời gian chờ giới hạn |
| SKIP LOCKED | Bỏ qua row đang khóa | Queue nhiều worker, xử lý song song |

### 7.6. Lưu ý khi bảng bị khóa ở chế độ EXCLUSIVE

Nếu bảng bị một session khác khóa ở chế độ EXCLUSIVE, WAIT hoặc SKIP LOCKED không bảo đảm câu SELECT FOR UPDATE trả kết quả ngay. Oracle có thể phải chờ đến khi table lock đó được giải phóng; WAIT không phải timeout cho mọi dạng table-level blocking.

SKIP LOCKED chỉ giải quyết việc bỏ qua row lock đang tranh chấp theo thiết kế của nó. Không nên xem nó là cơ chế bỏ qua mọi loại khóa hoặc mọi tình trạng database bận.

## 8. Cursor FOR UPDATE và WHERE CURRENT OF trong PL/SQL

SELECT FOR UPDATE thường được dùng khi muốn duyệt một tập row, đọc từng row rồi cập nhật hoặc xóa chính row hiện tại.

### 8.1. Khai báo cursor FOR UPDATE

~~~sql
DECLARE
    CURSOR c_emp (p_department_id NUMBER) IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = p_department_id
        FOR UPDATE OF salary;

    l_employee_id employees.employee_id%TYPE;
    l_salary      employees.salary%TYPE;
BEGIN
    OPEN c_emp(50);

    LOOP
        FETCH c_emp INTO l_employee_id, l_salary;
        EXIT WHEN c_emp%NOTFOUND;

        UPDATE employees
        SET salary = l_salary * 1.05
        WHERE CURRENT OF c_emp;
    END LOOP;

    CLOSE c_emp;
    COMMIT;
END;
/
~~~

FOR UPDATE OF salary xác định row của EMPLOYEES được khóa. WHERE CURRENT OF c_emp cập nhật row hiện tại của cursor, không cần viết lại điều kiện khóa chính.

### 8.2. WHERE CURRENT OF

WHERE CURRENT OF là phần mở rộng của PL/SQL cho UPDATE và DELETE. Nó tham chiếu row được FETCH gần nhất từ explicit cursor FOR UPDATE.

Ví dụ xóa row hiện tại:

~~~sql
DELETE FROM employees
WHERE CURRENT OF c_emp;
~~~

Chỉ cursor được khai báo với FOR UPDATE mới có thể được dùng trong CURRENT OF.

### 8.3. Row được khóa khi nào?

Với cursor FOR UPDATE thông thường, Oracle khóa các row thuộc tập kết quả khi cursor được OPEN, trước lần FETCH đầu tiên. Việc khóa không đợi đến khi ứng dụng fetch từng row.

Điều này có nghĩa:

- Cursor trả về 10.000 row thì có thể lấy khóa trên cả 10.000 row ngay khi OPEN.
- Ứng dụng mới FETCH được 1 row nhưng các row còn lại trong tập kết quả cũng đã bị khóa.
- CLOSE cursor không giải phóng row lock.
- COMMIT hoặc ROLLBACK mới giải phóng khóa.

Vì vậy, tránh mở cursor FOR UPDATE trên một tập kết quả lớn nếu chỉ định xử lý một vài row.

### 8.4. Không COMMIT giữa vòng lặp FETCH

Sau COMMIT hoặc ROLLBACK, row lock được giải phóng. Cursor FOR UPDATE đã mở không thể tiếp tục FETCH; Oracle có thể báo:

~~~text
ORA-01002: fetch out of sequence
~~~

Mẫu không nên dùng:

~~~sql
LOOP
    FETCH c_emp INTO ...;
    EXIT WHEN c_emp%NOTFOUND;

    UPDATE employees
    SET salary = salary * 1.05
    WHERE CURRENT OF c_emp;

    COMMIT; -- Không commit giữa vòng FETCH của FOR UPDATE cursor.
END LOOP;
~~~

Hãy xác định ranh giới transaction trước khi mở cursor. Nếu cần xử lý theo batch và commit từng batch, hãy thiết kế cách lấy batch riêng thay vì commit rồi tiếp tục fetch cùng cursor FOR UPDATE.

## 9. SKIP LOCKED trong cursor: thời điểm lấy khóa khác biệt

Có một điểm đặc biệt:

- Cursor FOR UPDATE thông thường khóa các row trong tập kết quả khi OPEN.
- Cursor FOR UPDATE có SKIP LOCKED lấy khóa trong giai đoạn FETCH; các row đang bị session khác khóa được bỏ qua khi fetch.

Điều này giúp các consumer cùng đọc một queue mà không chờ nhau. Mỗi consumer lấy được những row còn có thể khóa.

Ví dụ một worker nhận một công việc:

~~~sql
DECLARE
    CURSOR c_ready IS
        SELECT job_id, payload
        FROM job_queue
        WHERE status = 'READY'
        ORDER BY priority DESC, created_at, job_id
        FOR UPDATE SKIP LOCKED;

    l_job_id job_queue.job_id%TYPE;
    l_payload job_queue.payload%TYPE;
BEGIN
    OPEN c_ready;
    FETCH c_ready INTO l_job_id, l_payload;

    IF c_ready%FOUND THEN
        UPDATE job_queue
        SET status = 'PROCESSING',
            started_at = SYSTIMESTAMP
        WHERE CURRENT OF c_ready;
    END IF;

    CLOSE c_ready;
    COMMIT;

    -- Sau COMMIT, xử lý payload ngoài transaction khóa.
    IF l_job_id IS NOT NULL THEN
        process_job(l_job_id, l_payload);
    END IF;
END;
/
~~~

Trong ví dụ:

1. Cursor tìm row READY theo thứ tự ưu tiên.
2. FETCH đầu tiên lấy một row chưa bị worker khác khóa.
3. WHERE CURRENT OF chuyển row đó sang PROCESSING.
4. CLOSE cursor và COMMIT giải phóng row lock.
5. Worker xử lý payload sau khi đã ghi trạng thái PROCESSING.

Đây là khung minh họa. Ứng dụng thực tế cần xử lý lỗi trong PROCESS_JOB, ghi trạng thái FAILED hoặc RETRY, và có cơ chế phục hồi job PROCESSING bị bỏ dở nếu worker chết sau COMMIT.

### 9.1. Lease hoặc timeout để phục hồi job

Nếu worker COMMIT trạng thái PROCESSING rồi bị dừng đột ngột, row không còn bị khóa nhưng vẫn mang trạng thái PROCESSING. Một cơ chế queue bền vững thường cần:

- started_at hoặc lease_until.
- Số lần thử attempt_count.
- Trạng thái FAILED/READY/PROCESSING/DONE.
- Một tiến trình phục hồi job có lease đã hết hạn.
- Khả năng xử lý idempotent để retry không tạo tác dụng phụ trùng lặp.

SKIP LOCKED phân phối row giữa các worker; nó không tự xây dựng hệ thống retry hoặc bảo đảm một job chỉ tạo tác dụng phụ đúng một lần.

### 9.2. Không dùng SKIP LOCKED khi cần kết quả đầy đủ

Nếu câu hỏi là “liệt kê tất cả đơn đang mở”, SKIP LOCKED có thể bỏ qua các đơn đang bị session khác khóa. Kết quả lúc đó không còn là toàn bộ tập đơn đang mở.

Chỉ dùng SKIP LOCKED khi nghiệp vụ chấp nhận rằng row đang được xử lý bởi worker khác sẽ được lấy ở lần sau.

## 10. SELECT FOR UPDATE và read consistency

Oracle hỗ trợ consistent read cho SELECT thông thường bằng undo. Vì vậy SELECT thường không cần chờ một writer chỉ để đọc phiên bản đã commit.

SELECT FOR UPDATE có mục tiêu khác:

- Đọc row.
- Đặt khóa để bảo vệ row khỏi thay đổi xung đột.
- Cho phép transaction hiện tại thực hiện DML sau khi đã kiểm tra.

Ví dụ:

~~~sql
-- SELECT thông thường: đọc snapshot, không khóa row để cập nhật.
SELECT balance
FROM account_balance_lab
WHERE account_id = 10;

-- SELECT FOR UPDATE: đọc và khóa row.
SELECT balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Session khác vẫn có thể chạy SELECT thông thường trên row bị khóa và đọc phiên bản đã commit phù hợp với snapshot của nó. Nhưng UPDATE/DELETE cùng row phải chờ khóa.

Không dùng SELECT FOR UPDATE chỉ để làm báo cáo nhất quán. Nếu nhiều query cần cùng một snapshot, xem xét transaction READ ONLY, SERIALIZABLE hoặc Flashback Query AS OF SCN.

## 11. SELECT FOR UPDATE và câu UPDATE nguyên tử

Không phải bài toán nào cũng cần SELECT FOR UPDATE.

### 11.1. Khi một UPDATE là đủ

Ví dụ trừ tiền nếu số dư đủ:

~~~sql
UPDATE account_balance_lab
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Kiểm tra số row bị ảnh hưởng:

~~~plsql
IF SQL%ROWCOUNT = 1 THEN
    -- Giao dịch đã trừ tiền thành công.
ELSE
    -- Không có tài khoản hoặc số dư không đủ.
    NULL;
END IF;
~~~

Điều kiện BALANCE >= :amount và phép trừ nằm trong cùng một statement. Oracle tự khóa row khi UPDATE. Đây thường là cách đơn giản và an toàn cho phép cập nhật một giá trị theo điều kiện.

### 11.2. Khi cần SELECT FOR UPDATE

Dùng SELECT FOR UPDATE nếu:

- Phải đọc nhiều cột để quyết định một quy trình gồm nhiều bước.
- Phải kiểm tra một trạng thái rồi thực hiện nhiều DML liên quan.
- Cần giữ row cha ổn định trong lúc kiểm tra và cập nhật row con.
- Ứng dụng có giao diện chỉnh sửa một bản ghi và cần ngăn người khác sửa cùng row trong lúc người dùng thao tác, với transaction được quản lý phù hợp.

Ví dụ:

~~~sql
SELECT status, available_quantity, reserved_quantity
FROM inventory
WHERE product_id = :product_id
FOR UPDATE;
~~~

Ứng dụng đọc trạng thái và tính lượng có thể đặt chỗ, sau đó cập nhật các cột liên quan trong cùng transaction.

### 11.3. Giữ transaction ngắn

Không nên khóa row rồi:

- Chờ người dùng điền biểu mẫu trong vài phút.
- Gọi API thanh toán bên ngoài.
- Gửi email hoặc thực hiện tác vụ mạng lâu.
- Chờ một tiến trình khác không liên quan.

Những hành động này kéo dài thời gian giữ khóa, làm session khác chờ và tăng nguy cơ deadlock hoặc timeout. Hãy chuẩn bị dữ liệu trước, mở transaction ngay trước thao tác cần bảo vệ, khóa row, kiểm tra, cập nhật và COMMIT/ROLLBACK nhanh.

## 12. SELECT FOR UPDATE không khóa row chưa tồn tại hoặc predicate range

Đây là giới hạn quan trọng khi thiết kế quy tắc nghiệp vụ.

Giả sử ứng dụng muốn bảo đảm mỗi khách hàng chỉ có một đơn hàng OPEN:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 100
  AND status = 'OPEN'
FOR UPDATE;
~~~

Nếu hiện chưa có đơn OPEN, SELECT không khóa row nào. Hai session cùng chạy câu lệnh có thể đều nhận không dòng, sau đó cùng INSERT một đơn OPEN.

SELECT FOR UPDATE không khóa khoảng trống trong index để ngăn INSERT. Vì vậy không thể dùng nó một mình để bảo đảm “không có row nào khác thỏa predicate”.

Các cách bảo vệ phù hợp:

- Dùng unique constraint nếu quy tắc có thể biểu diễn bằng tính duy nhất.
- Khóa một row cha luôn tồn tại, ví dụ row CUSTOMER, trước khi kiểm tra và tạo đơn.
- Dùng transaction SERIALIZABLE nếu nghiệp vụ cần semantics phù hợp và ứng dụng xử lý được ORA-08177.
- Thiết kế trạng thái hoặc bảng reservation với khóa duy nhất.

Ví dụ khóa row khách hàng luôn tồn tại trước khi kiểm tra đơn:

~~~sql
SELECT customer_id
FROM customers
WHERE customer_id = 100
FOR UPDATE;

SELECT order_id
FROM orders
WHERE customer_id = 100
  AND status = 'OPEN';

-- Kiểm tra và INSERT trong cùng transaction.
~~~

Mọi đường tạo đơn OPEN phải tuân theo cùng quy tắc khóa row CUSTOMER. Nếu một chương trình bỏ qua khóa row cha, quy tắc đồng bộ này không còn được bảo đảm.

## 13. Giới hạn của SELECT FOR UPDATE trong Oracle 19c

Theo SQL Language Reference 19c, cần nhớ các giới hạn sau:

### 13.1. Chỉ dùng ở SELECT cấp cao nhất

FOR UPDATE chỉ được chỉ định trong top-level SELECT, không đặt trong subquery:

~~~sql
-- Không hợp lệ về ý tưởng:
SELECT *
FROM employees
WHERE employee_id IN (
    SELECT employee_id
    FROM employee_requests
    FOR UPDATE
);
~~~

### 13.2. Không kết hợp với một số cấu trúc query

Không thể dùng FOR UPDATE cùng:

- DISTINCT.
- CURSOR expression.
- Set operators như UNION, INTERSECT, MINUS.
- GROUP BY.
- Aggregate functions.

Lý do chung là các cấu trúc đó có thể tạo kết quả tổng hợp hoặc biến đổi khiến Oracle không thể xác định row cơ sở cần khóa theo cách yêu cầu.

### 13.3. Không kết hợp với FETCH FIRST / row limiting clause

Trong Oracle 19c, row limiting clause không được dùng cùng FOR UPDATE:

~~~sql
-- Không hợp lệ trong Oracle 19c:
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at
FETCH FIRST 10 ROWS ONLY
FOR UPDATE SKIP LOCKED;
~~~

Nếu cần lấy từng row từ queue, có thể dùng explicit cursor với FETCH và SKIP LOCKED như ví dụ trước. Không sao chép cú pháp FETCH FIRST của SELECT thông thường vào SELECT FOR UPDATE trên Oracle 19c.

### 13.4. Views

Nói chung, FOR UPDATE không được hỗ trợ trực tiếp trên view. Một số query trên view có thể thành công nếu optimizer merge view vào query block bên ngoài, nhưng hành vi phụ thuộc cấu trúc view và transformation.

Oracle khuyến nghị tránh dùng FOR UPDATE trên view do độ phức tạp của view merging. Nếu cần khóa row, hãy query trực tiếp bảng cơ sở hoặc kiểm tra rõ tính updatable và plan trong môi trường thực tế.

### 13.5. Các giới hạn khác

- Các bảng bị khóa trong câu lệnh phải nằm trên cùng database.
- Row của nested table không tự động bị khóa khi chỉ khóa row của bảng cha; nếu cần, phải khóa nested table row riêng.
- Với dữ liệu LOB, phải khóa row chứa LOB trước khi cập nhật LOB theo yêu cầu của Oracle.
- Trong bảng dùng Hybrid Columnar Compression, một số thao tác DML có thể khóa compression unit thay vì từng row theo cách nhìn logic thông thường.

## 14. Deadlock và thứ tự lấy khóa

Deadlock xảy ra khi hai transaction giữ các khóa mà transaction kia cần, tạo thành vòng chờ.

Ví dụ:

~~~text
Session A                         Session B
---------                         ---------
Khóa account 10
                                  Khóa account 20
Muốn khóa account 20
                                  Muốn khóa account 10
        |                                  |
        +---------- chờ lẫn nhau -----------+
~~~

Oracle phát hiện deadlock và chọn một statement để hủy, thường báo:

~~~text
ORA-00060: deadlock detected while waiting for resource
~~~

Transaction cần xử lý lỗi và quyết định ROLLBACK phù hợp. Không nên chỉ retry statement lỗi mà bỏ qua trạng thái của các bước trước.

Để giảm deadlock:

1. Khóa nhiều row theo cùng một thứ tự nghiệp vụ trong mọi đường code.
2. Giữ transaction ngắn.
3. Chỉ khóa những row thực sự cần.
4. Tránh gọi dịch vụ ngoài khi đang giữ row lock.
5. Bắt và ghi nhận ORA-00060; có retry có giới hạn và backoff nếu nghiệp vụ cho phép.

ORDER BY có thể giúp làm rõ thứ tự mong muốn của tập kết quả, nhưng không nên xem riêng nó là bảo đảm tuyệt đối về thứ tự khóa nội bộ của mọi execution plan. Quy tắc khóa nhất quán cần được thiết kế trong toàn bộ các transaction cạnh tranh.

## 15. Những lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| ORA-00054 | Dùng NOWAIT nhưng row/table resource đang bận | Báo bận hoặc thử lại theo chính sách |
| ORA-30006 | WAIT n hết thời gian | Kiểm tra transaction giữ khóa, điều chỉnh timeout có căn cứ |
| ORA-00060 | Hai transaction lấy khóa theo thứ tự gây vòng chờ | Chuẩn hóa thứ tự khóa, rollback/retry có kiểm soát |
| ORA-01002 | FETCH cursor FOR UPDATE sau COMMIT/ROLLBACK | Không commit giữa vòng fetch; kết thúc cursor/transaction đúng thứ tự |
| ORA-02014 | FOR UPDATE trên view không thể merge hoặc view có cấu trúc không hỗ trợ | Truy vấn bảng cơ sở; tránh khóa view phức tạp |
| Row ở bảng JOIN bị khóa ngoài ý muốn | Bỏ OF, nên Oracle khóa row từ mọi bảng được chọn | Chỉ định FOR UPDATE OF alias.column |
| Session khác vẫn đọc được row đã khóa | SELECT thường dùng consistent read, không cần row lock | Đây là hành vi bình thường |
| Session khác không cập nhật được row | Row đang bị transaction giữ FOR UPDATE | Chờ COMMIT/ROLLBACK hoặc xử lý timeout |
| Query không khóa gì | WHERE không trả row | Kiểm tra predicate; nhớ SELECT FOR UPDATE không khóa gap |
| Nhiều row bị khóa dù mới FETCH một row | Cursor FOR UPDATE thường khóa tập kết quả tại OPEN | Thu hẹp query; dùng SKIP LOCKED cursor khi đúng nghiệp vụ |
| Queue bỏ qua một số job | Job đang bị worker khác khóa hoặc chưa đủ điều kiện | Đọc lại sau; có recovery/lease cho job bị bỏ dở |

## 16. Bộ dữ liệu lab tự chứa

Phần này tạo bảng số dư để thử khóa giữa hai session. Chỉ chạy trong schema lab.

### 16.1. Tạo bảng và dữ liệu

~~~sql
CREATE TABLE account_balance_lab (
    account_id NUMBER PRIMARY KEY,
    branch_id  NUMBER NOT NULL,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO account_balance_lab VALUES (10, 1, 1000);
INSERT INTO account_balance_lab VALUES (20, 1, 2000);
INSERT INTO account_balance_lab VALUES (30, 2, 3000);
COMMIT;
~~~

### 16.2. Lab A — Khóa một row

Session A:

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Session B:

~~~sql
UPDATE account_balance_lab
SET balance = balance + 100
WHERE account_id = 10;
~~~

B sẽ chờ vì A đang giữ khóa row 10. A chạy:

~~~sql
COMMIT;
~~~

Sau đó B tiếp tục và có thể COMMIT.

### 16.3. Lab B — Row khác vẫn cập nhật được

Session A khóa account 10:

~~~sql
SELECT account_id
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE;
~~~

Session B cập nhật account 20:

~~~sql
UPDATE account_balance_lab
SET balance = balance + 50
WHERE account_id = 20;

COMMIT;
~~~

B có thể cập nhật row 20 vì A chỉ khóa row 10. Sau đó A ROLLBACK hoặc COMMIT để giải phóng khóa 10.

### 16.4. Lab C — NOWAIT

Giữ row 10 bị khóa ở Session A. Session B chạy:

~~~sql
SELECT account_id
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE NOWAIT;
~~~

B nhận lỗi resource busy ngay thay vì chờ.

### 16.5. Lab D — WAIT

Giữ row 10 bị khóa ở A. B chạy:

~~~sql
SELECT account_id
FROM account_balance_lab
WHERE account_id = 10
FOR UPDATE WAIT 3;
~~~

Nếu A không giải phóng trong 3 giây, B nhận lỗi timeout. Thử lại bằng cách cho A COMMIT trước khi hết thời gian.

### 16.6. Lab E — Phạm vi khóa trong JOIN

Tạo bảng đơn hàng và khách hàng:

~~~sql
CREATE TABLE customers_lock_lab (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(50 CHAR)
);

CREATE TABLE orders_lock_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER REFERENCES customers_lock_lab(customer_id),
    status VARCHAR2(20 CHAR)
);

INSERT INTO customers_lock_lab VALUES (1, 'An');
INSERT INTO customers_lock_lab VALUES (2, 'Binh');
INSERT INTO orders_lock_lab VALUES (101, 1, 'READY');
INSERT INTO orders_lock_lab VALUES (102, 1, 'READY');
INSERT INTO orders_lock_lab VALUES (201, 2, 'READY');
COMMIT;
~~~

Query khóa cả hai bảng:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders_lock_lab o
JOIN customers_lock_lab c
  ON c.customer_id = o.customer_id
WHERE c.customer_id = 1
FOR UPDATE;
~~~

Query chỉ khóa đơn hàng:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders_lock_lab o
JOIN customers_lock_lab c
  ON c.customer_id = o.customer_id
WHERE c.customer_id = 1
FOR UPDATE OF o.status;
~~~

Trong khi A giữ khóa, dùng Session B thử UPDATE CUSTOMERS_LOCK_LAB và ORDERS_LOCK_LAB để quan sát sự khác biệt. Với câu lệnh có OF o.status, row khách hàng không bị khóa bởi câu SELECT đó; row đơn hàng thỏa điều kiện bị khóa.

### 16.7. Lab F — SKIP LOCKED

Tạo queue nhỏ:

~~~sql
CREATE TABLE job_queue_lab (
    job_id NUMBER PRIMARY KEY,
    status VARCHAR2(20 CHAR) NOT NULL,
    payload VARCHAR2(100 CHAR)
);

INSERT INTO job_queue_lab VALUES (1, 'READY', 'Job A');
INSERT INTO job_queue_lab VALUES (2, 'READY', 'Job B');
INSERT INTO job_queue_lab VALUES (3, 'READY', 'Job C');
COMMIT;
~~~

Session A:

~~~sql
SELECT job_id, payload
FROM job_queue_lab
WHERE job_id = 1
FOR UPDATE;
~~~

Session B:

~~~sql
SELECT job_id, payload
FROM job_queue_lab
WHERE status = 'READY'
ORDER BY job_id
FOR UPDATE SKIP LOCKED;
~~~

B có thể lấy job 2 và 3 mà không chờ job 1 đang bị A khóa. A COMMIT/ROLLBACK; lần đọc sau của B có thể lấy job 1 nếu nó vẫn READY.

### 16.8. Dọn bảng lab (tùy chọn)

~~~sql
DROP TABLE job_queue_lab PURGE;
DROP TABLE orders_lock_lab PURGE;
DROP TABLE customers_lock_lab PURGE;
DROP TABLE account_balance_lab PURGE;
~~~

DDL có implicit commit. Chỉ xóa đúng các bảng lab do bạn tạo.

## 17. Checklist trước khi dùng SELECT FOR UPDATE

1. **Tập row cần khóa là gì?** Kiểm tra WHERE và số lượng row có thể trả về.
2. **Query JOIN những bảng nào?** Nếu bỏ OF, các row được chọn từ mọi bảng đều có thể bị khóa.
3. **Có cần khóa tất cả bảng không?** Nếu chỉ cập nhật một bảng, dùng OF để giới hạn phạm vi.
4. **OF đang chỉ ra bảng hay bạn đang nghĩ nó chỉ khóa cột?** OF xác định bảng; row được khóa.
5. **Nếu không có row thì nghiệp vụ có còn đúng không?** SELECT FOR UPDATE không khóa row chưa tồn tại hoặc khoảng trống.
6. **Thời gian chờ nên là bao lâu?** Chọn mặc định, NOWAIT hay WAIT theo trải nghiệm ứng dụng.
7. **Có cần SKIP LOCKED không?** Chỉ dùng khi row đang khóa được phép xử lý sau.
8. **Cursor có thể trả quá nhiều row không?** Cursor FOR UPDATE thường khóa tập kết quả khi OPEN.
9. **Transaction có được kết thúc đúng lúc không?** Commit/rollback sớm sau khi hoàn tất; đừng commit giữa vòng fetch.
10. **Có thể dùng một UPDATE nguyên tử không?** Nếu có, câu UPDATE thường đơn giản hơn.
11. **Có nhiều row hoặc nhiều bảng không?** Chuẩn hóa thứ tự khóa để giảm deadlock.
12. **Có xử lý lỗi khóa không?** Chuẩn bị cho ORA-00054, ORA-30006, ORA-00060 và ORA-01002.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** SELECT FOR UPDATE dùng để làm gì?

**Câu 2.** Nếu SELECT FOR UPDATE có WHERE chỉ chọn một row, những row nào bị khóa?

**Câu 3.** Nếu bỏ WHERE, phạm vi khóa có thể thay đổi ra sao?

**Câu 4.** Khi JOIN hai bảng và bỏ OF, Oracle khóa row ở bảng nào?

**Câu 5.** FOR UPDATE OF e.salary có nghĩa chỉ cột SALARY bị khóa không?

**Câu 6.** FOR UPDATE OF dùng để lọc row hay chỉ định bảng có row cần khóa?

**Câu 7.** Nếu SELECT FOR UPDATE không tìm thấy row, nó có khóa khoảng trống để ngăn INSERT không?

**Câu 8.** Row lock được giải phóng khi nào?

**Câu 9.** CLOSE cursor FOR UPDATE có tự giải phóng row lock không?

**Câu 10.** Cursor FOR UPDATE thông thường khóa row lúc OPEN hay lúc FETCH?

**Câu 11.** SKIP LOCKED khác WAIT như thế nào?

**Câu 12.** Vì sao không nên COMMIT giữa vòng FETCH của cursor FOR UPDATE?

**Câu 13.** Oracle 19c có cho kết hợp FETCH FIRST với FOR UPDATE không?

**Câu 14.** Khi nào nên dùng UPDATE nguyên tử thay cho SELECT FOR UPDATE?

<details>
<summary>Gợi ý đáp án</summary>

1. Khóa trước các row được chọn để session khác không thể cập nhật/xóa hoặc lấy khóa xung đột cho đến khi transaction kết thúc.
2. Row duy nhất thỏa điều kiện và thuộc bảng được khóa theo query.
3. Toàn bộ row của bảng có thể thuộc tập kết quả và bị khóa.
4. Mặc định khóa các row được chọn từ cả hai bảng.
5. Không. SALARY chỉ xác định bảng EMPLOYEES; row của nhân viên bị khóa.
6. Chỉ định bảng hoặc view có row cần khóa; WHERE mới quyết định row nào được chọn.
7. Không. Không có row thì không có row lock; SELECT FOR UPDATE không khóa gap.
8. Khi COMMIT hoặc ROLLBACK; rollback về savepoint có thể giải phóng các khóa được lấy sau savepoint.
9. Không. Khóa tiếp tục đến khi transaction kết thúc hoặc rollback phù hợp.
10. Cursor FOR UPDATE thông thường khóa tập kết quả lúc OPEN, trước FETCH đầu tiên. Với SKIP LOCKED, row được khóa trong giai đoạn FETCH.
11. WAIT chờ tối đa thời gian chỉ định; SKIP LOCKED bỏ qua row đang bị khóa.
12. COMMIT giải phóng row lock và cursor FOR UPDATE không thể FETCH tiếp; có thể nhận ORA-01002.
13. Không. Row limiting clause không tương thích FOR UPDATE trong Oracle 19c.
14. Khi điều kiện nghiệp vụ và phép cập nhật có thể gộp trong cùng một UPDATE statement, ví dụ trừ số dư chỉ khi số dư đủ.

</details>

## 19. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp FOR UPDATE, OF, NOWAIT, WAIT, SKIP LOCKED, giới hạn và ví dụ khóa row trong JOIN.
2. [Oracle Database 19c Database Development Guide — Locking Tables Explicitly](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/sql-processing-for-application-developers.html): explicit row locks, thời điểm khóa cursor, thời gian giữ khóa và deadlock khi tập kết quả thay đổi.
3. [Oracle Database 19c PL/SQL Language Reference — Transaction Processing and Control](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/transaction-processing-and-control.html): cursor FOR UPDATE, WHERE CURRENT OF, SKIP LOCKED và vòng đời row lock.
4. [Oracle Database 19c Error Messages — ORA-00054](https://docs.oracle.com/en/error-help/db/ora-00054/): resource busy khi dùng NOWAIT.
5. [Oracle Database 19c Error Messages — ORA-30006](https://docs.oracle.com/en/error-help/db/ora-30006/): timeout khi chờ khóa.
6. [Oracle Database 19c Error Messages — ORA-00060](https://docs.oracle.com/en/error-help/db/ora-00060/): deadlock detected.
7. [Oracle Database 19c Error Messages — ORA-01002](https://docs.oracle.com/en/error-help/db/ora-01002/): fetch out of sequence.

**Nguyên tắc cần nhớ:** SELECT FOR UPDATE khóa các row thuộc tập kết quả của SELECT. Trong JOIN, nếu không có OF, Oracle khóa row được chọn từ mọi bảng; OF alias.column chỉ ra bảng nào có row cần khóa và không phải khóa riêng cột. Row lock tồn tại đến khi transaction COMMIT/ROLLBACK. Dùng NOWAIT, WAIT hoặc SKIP LOCKED theo cách ứng dụng xử lý cạnh tranh; với cursor FOR UPDATE, nhớ rằng cursor thông thường khóa cả tập kết quả ngay khi OPEN, còn SKIP LOCKED lấy khóa trong FETCH. Nếu chỉ cần kiểm tra và cập nhật một điều kiện đơn giản, ưu tiên một câu DML nguyên tử; dùng SELECT FOR UPDATE khi cần giữ row ổn định qua một quy trình nhiều bước.
