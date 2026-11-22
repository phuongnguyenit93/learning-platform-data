# READ COMMITTED và ảnh chụp dữ liệu tại từng câu lệnh trong Oracle Database

## 1. Vì sao hai câu SELECT trong cùng một transaction có thể thấy kết quả khác nhau?

Một ứng dụng thường thực hiện nhiều câu SQL trong một transaction: đọc số dư, kiểm tra điều kiện, ghi giao dịch, rồi đọc lại báo cáo. Trong lúc đó, các session khác cũng có thể INSERT, UPDATE hoặc DELETE dữ liệu và COMMIT.

Hãy hình dung hai session cùng làm việc:

- Session A bắt đầu transaction và đọc tổng số đơn hàng.
- Session B thêm một đơn hàng mới rồi COMMIT.
- Session A chạy lại câu SELECT tổng số đơn hàng.

Trong Oracle với mức cô lập mặc định **READ COMMITTED**, câu SELECT thứ hai của A có thể thấy đơn hàng mà B vừa commit, dù transaction của A chưa kết thúc.

Đó là vì Oracle sử dụng **statement-level read consistency**: mỗi câu truy vấn nhìn dữ liệu đã COMMIT tại thời điểm câu lệnh bắt đầu. Hai câu SELECT khác nhau trong cùng transaction có thể có hai ảnh chụp dữ liệu khác nhau.

Đặc tính này là nền tảng của cơ chế đồng thời Oracle:

- Không đọc dữ liệu chưa COMMIT của session khác (không dirty read).
- Một câu SELECT có ảnh chụp nhất quán trong suốt quá trình thực thi.
- Câu SQL tiếp theo có thể thấy các thay đổi đã COMMIT sau khi câu trước bắt đầu.
- Reader thông thường không cần khóa dòng để đọc; Oracle có thể dựng lại phiên bản cũ bằng undo.

Bài này giải thích READ COMMITTED, SCN, consistent read, undo, các hiện tượng đọc lặp lại, SELECT FOR UPDATE và những lựa chọn khi nghiệp vụ cần ảnh chụp nhất quán xuyên suốt nhiều câu lệnh.

> Nội dung dùng Oracle Database 19c. Các ví dụ SQL có thể chạy trong schema lab riêng; tên bảng và dữ liệu minh họa. Không chạy lệnh DML trên môi trường production nếu chưa kiểm tra điều kiện và transaction.

## 2. READ COMMITTED là gì?

**READ COMMITTED** là mức cô lập transaction mặc định của Oracle Database. Một câu SQL chỉ đọc dữ liệu đã được transaction khác COMMIT trước thời điểm câu lệnh bắt đầu, cùng với các thay đổi do chính transaction hiện tại tạo ra.

Có hai phạm vi thời gian cần phân biệt:

| Phạm vi | READ COMMITTED |
| --- | --- |
| Một câu SQL | Nhìn một ảnh chụp nhất quán tại thời điểm bắt đầu câu lệnh |
| Nhiều câu SQL trong cùng transaction | Mỗi câu có thể nhìn ảnh chụp mới, bao gồm commit từ session khác đã hoàn tất trước khi câu đó bắt đầu |

Ví dụ:

~~~sql
-- READ COMMITTED là mặc định của Oracle.
SELECT COUNT(*) FROM orders;

-- Một session khác có thể COMMIT ở đây.

SELECT COUNT(*) FROM orders;
~~~

Nếu session khác thêm đơn hàng và COMMIT giữa hai câu SELECT, kết quả COUNT thứ hai có thể lớn hơn kết quả đầu.

Điều này không phải lỗi nhất quán. Mỗi câu SELECT đều nhất quán theo ảnh chụp riêng của nó; transaction READ COMMITTED không hứa giữ nguyên một ảnh chụp cho tất cả câu lệnh.

### 2.1. READ COMMITTED không phải “đọc dữ liệu mới nhất ở mọi thời điểm trong khi query chạy”

Một câu SELECT dài có thể bắt đầu lúc 10:00 và chạy đến 10:05. Nếu session khác COMMIT thay đổi lúc 10:02, câu SELECT đang chạy vẫn đọc theo ảnh chụp được xác định khi nó bắt đầu. Câu SELECT mới bắt đầu lúc 10:03 có thể nhìn thấy thay đổi đó.

Vì vậy, không nên hiểu READ COMMITTED là mỗi lần Oracle chạm vào một block dữ liệu thì lấy phiên bản mới nhất ngay tại thời điểm chạm. Oracle giữ tính nhất quán ở **cấp câu lệnh**.

### 2.2. Oracle không cho phép dirty read

Giả sử session B UPDATE một dòng nhưng chưa COMMIT. Session A chạy SELECT thông thường:

- A không nhìn thấy giá trị chưa COMMIT của B.
- A nhìn thấy phiên bản đã COMMIT trước đó.
- Nếu B ROLLBACK, giá trị cũ vẫn là giá trị đúng.

Oracle không hỗ trợ mức cô lập READ UNCOMMITTED như một lựa chọn transaction thông thường. READ COMMITTED vẫn bảo đảm không đọc dữ liệu chưa commit từ transaction khác.

## 3. SCN: mốc xác định ảnh chụp dữ liệu

Oracle dùng **System Change Number (SCN)** để xác định thứ tự các thay đổi trong database. Có thể xem SCN như một mốc logic của database, giúp Oracle biết một phiên bản dữ liệu đã tồn tại tại thời điểm nào.

Khi một câu query bắt đầu, Oracle xác định một snapshot SCN cho câu lệnh. Câu query phải trả kết quả dựa trên những thay đổi đã COMMIT tại hoặc trước snapshot đó.

~~~text
Thời gian ---------------------------------------------------->

SCN 100             SCN 105                SCN 110
  |                    |                      |
  |                    |                      +-- Session B COMMIT
  |                    |
  +-- Query A bắt đầu  +-- Query A vẫn chạy
       snapshot=100         không thấy commit ở SCN 110

Query B bắt đầu sau commit:
snapshot >= 110, có thể thấy thay đổi của B
~~~

SCN là cơ chế logic nội bộ, không phải đồng hồ thời gian thực. Không nên so sánh SCN như số giây hoặc tự suy ra timestamp chính xác từ chênh lệch SCN.

### 3.1. Vì sao query vẫn đọc được phiên bản cũ?

Giả sử một dòng có số dư ban đầu là 1.000. Session B cập nhật thành 1.200 và COMMIT. Một query của session A đã bắt đầu trước commit đó vẫn phải thấy 1.000.

Oracle dùng thông tin undo để dựng lại phiên bản dữ liệu phù hợp với snapshot của A:

~~~text
Phiên bản hiện tại trong data block: 1.200
                         |
                         | undo chứa thông tin phiên bản trước
                         v
Phiên bản nhất quán cho snapshot cũ: 1.000
~~~

Đây là một phần của **multiversion concurrency control (MVCC)**. Thay vì buộc reader chờ writer để lấy dữ liệu, Oracle có thể dùng undo để đọc phiên bản phù hợp.

### 3.2. Quan sát SCN hiện tại

Trong môi trường có quyền phù hợp:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM dual;
~~~

Hàm trả SCN hiện tại mà database cung cấp tại thời điểm gọi. SCN có thể được dùng trong Flashback Query hoặc công cụ chẩn đoán khi có quyền và dữ liệu undo phù hợp.

Không nhầm:

- SYSDATE/SYSTIMESTAMP: thời gian theo clock của database host.
- SCN: mốc logic theo thứ tự thay đổi trong database.
- COMMIT: kết thúc transaction và công bố thay đổi; Oracle gán thứ tự commit bằng cơ chế SCN.

## 4. Consistent read và undo

**Consistent read** là cách Oracle cung cấp phiên bản dữ liệu phù hợp với snapshot SCN của câu query.

Khi query đọc một block đã bị transaction khác sửa sau snapshot:

1. Oracle nhận ra phiên bản hiện tại quá mới so với snapshot.
2. Oracle dùng undo records để dựng lại phiên bản cũ cần thiết.
3. Query tiếp tục đọc phiên bản phù hợp với thời điểm bắt đầu.

Điều này giúp một câu SELECT không thấy nửa dữ liệu trước và nửa dữ liệu sau một transaction khác.

### 4.1. Undo không chỉ dùng cho ROLLBACK

Undo có nhiều vai trò:

- Hoàn tác thay đổi khi transaction ROLLBACK.
- Dựng phiên bản dữ liệu cũ cho consistent read.
- Hỗ trợ Flashback Query và một số khả năng flashback khác trong phạm vi undo còn giữ được.
- Hỗ trợ khôi phục transaction và tính nhất quán sau sự cố theo cơ chế Oracle.

Undo không phải một bản sao lịch sử vô hạn. Oracle quản lý không gian undo và có thể tái sử dụng các undo record khi không còn cần thiết theo chính sách retention và trạng thái hệ thống.

### 4.2. ORA-01555: snapshot too old

Một query dài cần phiên bản cũ của block, nhưng undo cần thiết đã bị ghi đè/tái sử dụng trước khi query hoàn tất. Oracle không thể dựng lại snapshot và có thể báo:

~~~text
ORA-01555: snapshot too old
~~~

Các nguyên nhân thường gặp:

- Query chạy lâu trong khi dữ liệu bị UPDATE/DELETE thường xuyên.
- Undo tablespace không đủ cho workload và thời gian query.
- UNDO_RETENTION không phù hợp với yêu cầu.
- Ứng dụng mở cursor lâu hoặc xử lý từng dòng quá chậm.

Hướng điều tra:

1. Ghi nhận thời lượng query, thời điểm lỗi và workload DML đồng thời.
2. Xem cấu hình undo tablespace, dung lượng và retention.
3. Kiểm tra các query chạy lâu và cách ứng dụng fetch dữ liệu.
4. Tối ưu query, giảm thời gian xử lý hoặc điều chỉnh undo theo năng lực lưu trữ.
5. Nếu cần bảo đảm retention cho một mục tiêu cụ thể, DBA có thể xem xét RETENTION GUARANTEE cùng tác động đến khả năng cấp phát undo.

Không mặc định chỉ cần tăng UNDO_RETENTION là giải quyết được mọi trường hợp. Nếu không đủ dung lượng, retention guarantee có thể khiến DML gặp lỗi vì Oracle không thể tái sử dụng undo còn được bảo vệ. Việc thay đổi cấu hình undo cần DBA đánh giá.

## 5. Mô phỏng hai session: mỗi câu SELECT có một snapshot

Ta dùng bảng số dư nhỏ để quan sát. Chỉ tạo trong schema lab:

~~~sql
CREATE TABLE account_balance_lab (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL
);

INSERT INTO account_balance_lab VALUES (1, 1000);
COMMIT;
~~~

### 5.1. Trình tự thao tác

| Bước | Session A | Session B |
| --- | --- | --- |
| 1 | SELECT balance ... → 1.000 | |
| 2 | | UPDATE ... SET balance = 1200 ... |
| 3 | | COMMIT |
| 4 | SELECT balance ... → 1.200 | |

Session A có thể nhìn giá trị mới ở câu SELECT thứ hai, dù A không COMMIT hay kết thúc transaction giữa hai lần đọc.

### 5.2. Session A

~~~sql
SELECT balance
FROM account_balance_lab
WHERE account_id = 1;
~~~

Giả sử kết quả là 1.000.

### 5.3. Session B

~~~sql
UPDATE account_balance_lab
SET balance = 1200
WHERE account_id = 1;

COMMIT;
~~~

### 5.4. Session A đọc lại

~~~sql
SELECT balance
FROM account_balance_lab
WHERE account_id = 1;
~~~

Kết quả bây giờ là 1.200. Đây là ví dụ điển hình của statement-level read consistency trong READ COMMITTED.

## 6. Một câu SELECT không trộn hai phiên bản dữ liệu

Điều quan trọng là phân biệt hai tình huống:

- **Hai câu SELECT:** mỗi câu có thể thấy snapshot khác nhau.
- **Một câu SELECT duy nhất:** các phần của câu lệnh cùng đọc theo snapshot của câu đó.

Ví dụ query:

~~~sql
SELECT d.department_id,
       d.department_name,
       COUNT(e.employee_id) AS employee_count,
       SUM(e.salary) AS salary_total
FROM departments d
LEFT JOIN employees e
       ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name;
~~~

Oracle không để phép JOIN đọc bảng DEPARTMENTS tại một thời điểm rồi đọc EMPLOYEES tại một thời điểm mới hơn giữa lúc cùng một statement đang chạy. Câu lệnh có read consistency ở cấp statement.

Điều này cũng áp dụng khi query dùng JOIN nhiều bảng, inline view, subquery, common table expression (WITH), aggregate hoặc analytic function. Các query block không tạo ra một transaction snapshot mới riêng chỉ vì được viết thành subquery; chúng là thành phần của cùng câu SQL.

## 7. READ COMMITTED cho phép nonrepeatable read và phantom read giữa các câu lệnh

READ COMMITTED ngăn dirty read, nhưng không giữ một snapshot chung cho toàn transaction. Do đó, dữ liệu có thể thay đổi giữa hai câu query.

### 7.1. Nonrepeatable read

Một dòng đã đọc lần đầu có giá trị khác khi đọc lại:

~~~text
Session A                         Session B
---------                         ---------
SELECT balance = 100
                                  UPDATE balance = 150
                                  COMMIT
SELECT balance = 150
~~~

Session A đã đọc cùng một row hai lần nhưng nhận hai giá trị khác nhau. Điều này được gọi là nonrepeatable read.

### 7.2. Phantom read

Tập dòng thỏa một điều kiện thay đổi giữa hai lần query:

~~~text
Session A                         Session B
---------                         ---------
SELECT COUNT(*) = 3
  WHERE status='OPEN'
                                  INSERT một OPEN order
                                  COMMIT
SELECT COUNT(*) = 4
  WHERE status='OPEN'
~~~

Lần query sau thấy thêm một dòng mới thỏa predicate. Dòng đó được gọi là phantom row so với lần đọc trước.

### 7.3. Bảng so sánh

| Hiện tượng | Ý nghĩa | READ COMMITTED của Oracle |
| --- | --- | --- |
| Dirty read | Đọc thay đổi chưa COMMIT của transaction khác | Không xảy ra |
| Nonrepeatable read | Đọc lại cùng row nhưng giá trị đã đổi sau commit khác | Có thể xảy ra giữa các statement |
| Phantom read | Tập row thỏa predicate thay đổi giữa các statement | Có thể xảy ra giữa các statement |
| Inconsistent read trong một statement | Một query thấy các phần dữ liệu ở những snapshot không đồng nhất | Được ngăn bằng statement-level read consistency |

READ COMMITTED phù hợp với nhiều ứng dụng OLTP vì transaction thường ngắn và cần thấy dữ liệu mới đã commit. Nhưng nếu một quy trình nghiệp vụ cần nhiều câu query cùng nhìn một trạng thái dữ liệu, phải chọn cơ chế phù hợp hơn.

## 8. READ COMMITTED và transaction boundary

Transaction bắt đầu khi session thực hiện câu SQL đầu tiên sau khi transaction trước kết thúc. Transaction kết thúc bằng COMMIT hoặc ROLLBACK. Với READ COMMITTED, snapshot của một SELECT gắn với thời điểm câu SELECT đó bắt đầu, không gắn cố định với thời điểm transaction bắt đầu.

~~~sql
COMMIT;

-- Câu lệnh đầu tiên trong transaction mới.
SELECT COUNT(*) FROM orders;

-- Session khác có thể COMMIT ở đây.

SELECT COUNT(*) FROM orders;

COMMIT;
~~~

Hai SELECT có thể cho kết quả khác nhau.

### 8.1. SET TRANSACTION ISOLATION LEVEL READ COMMITTED

Có thể khai báo tường minh:

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) FROM orders;
~~~

READ COMMITTED vốn là mặc định, nên thường không cần khai báo lại. SET TRANSACTION phải là câu lệnh đầu tiên của transaction; hãy đặt nó trước SELECT/INSERT/UPDATE/DELETE trong transaction đó.

Không đặt SET TRANSACTION giữa một transaction đã thực hiện DML rồi mới mong thay đổi isolation level của các statement trước.

### 8.2. Autocommit ở client

Một số công cụ hoặc ứng dụng bật autocommit. Khi đó mỗi statement thành công có thể được commit ngay sau khi chạy. Nếu không kiểm soát transaction boundary, người phát triển có thể nhầm rằng nhiều câu SQL đang nằm trong cùng một transaction.

Khi thử nghiệm hai session:

- Kiểm tra trạng thái autocommit.
- Xác nhận thời điểm COMMIT thật sự.
- Dùng hai connection độc lập.
- Không dựa vào trạng thái transaction của tab SQL khác.

## 9. Reader và writer: vì sao SELECT thông thường không khóa dòng?

Oracle dùng MVCC và consistent read để cho phép reader nhìn phiên bản đã commit phù hợp với snapshot mà không cần khóa các row chỉ để đọc.

Với SELECT thông thường:

- Reader không đặt row lock chỉ vì đọc một row.
- Writer có thể UPDATE row trong khi query đang chạy.
- Query đang chạy vẫn đọc phiên bản nhất quán của nó.
- Một query khác bắt đầu sau khi writer COMMIT có thể thấy phiên bản mới.

Điều này giúp tăng concurrency trong OLTP: báo cáo đọc không nhất thiết chặn giao dịch cập nhật, và writer không cần chờ mọi SELECT thông thường kết thúc.

Tuy nhiên, **SELECT thông thường không bảo vệ một quy tắc nghiệp vụ qua nhiều câu lệnh**. Nếu ứng dụng đọc rồi quyết định cập nhật dựa trên giá trị đọc, phải dùng một kỹ thuật đồng bộ phù hợp.

## 10. Race condition khi đọc rồi cập nhật

Giả sử số dư tài khoản là 100. Hai ứng dụng cùng đọc số dư và muốn trừ tiền:

~~~text
Session A                         Session B
---------                         ---------
SELECT balance = 100
                                  SELECT balance = 100
Tính số dư mới = 90
                                  Tính số dư mới = 80
UPDATE balance = 90
COMMIT
                                  UPDATE balance = 80
                                  COMMIT
~~~

Nếu cả hai ứng dụng ghi một con số đã tính từ giá trị cũ, kết quả cuối cùng có thể là 80. Một cập nhật đã ghi đè kết quả cập nhật kia. Đây là một dạng lost update ở tầng logic ứng dụng.

READ COMMITTED không tự động bảo vệ mọi chuỗi thao tác đọc-tính-ghi nằm trong nhiều statement. Có một số cách xử lý.

### 10.1. Ưu tiên cập nhật nguyên tử trong một câu SQL

Nếu nghiệp vụ chỉ cần trừ tiền và không cho phép số dư âm:

~~~sql
UPDATE account_balance_lab
SET    balance = balance - :amount
WHERE  account_id = :account_id
AND    balance >= :amount;
~~~

Sau đó kiểm tra số dòng bị ảnh hưởng trong PL/SQL:

~~~plsql
IF SQL%ROWCOUNT = 0 THEN
    -- Không tìm thấy tài khoản hoặc số dư không đủ.
    -- Phân biệt hai trường hợp nếu nghiệp vụ yêu cầu.
    NULL;
END IF;
~~~

Phép kiểm tra điều kiện và phép trừ nằm trong cùng một DML statement. Oracle khóa row được cập nhật; khi có cạnh tranh, transaction khác phải chờ và điều kiện DML được xử lý theo cơ chế write consistency của Oracle.

Nếu cần phân biệt “không có tài khoản” với “không đủ số dư”, có thể kiểm tra bổ sung bằng query phù hợp hoặc thiết kế mã kết quả riêng. Không nên suy luận quá mức chỉ từ SQL%ROWCOUNT.

### 10.2. SELECT FOR UPDATE

Nếu nghiệp vụ thực sự cần đọc row, thực hiện nhiều phép tính trong ứng dụng, rồi mới ghi lại, có thể khóa row trước khi đọc:

~~~sql
SELECT balance
FROM account_balance_lab
WHERE account_id = :account_id
FOR UPDATE;
~~~

Oracle khóa các row được chọn cho transaction hiện tại. Session khác muốn UPDATE/DELETE cùng row sẽ phải chờ đến khi transaction giữ khóa COMMIT hoặc ROLLBACK.

Sau khi lấy khóa:

~~~sql
UPDATE account_balance_lab
SET    balance = balance - :amount
WHERE  account_id = :account_id;
~~~

SELECT FOR UPDATE phù hợp với quy trình read-modify-write có nhiều bước, nhưng phải:

- Giữ transaction ngắn.
- COMMIT hoặc ROLLBACK sớm sau khi hoàn tất.
- Khóa các row theo thứ tự nhất quán khi thao tác nhiều tài khoản để giảm nguy cơ deadlock.
- Xử lý trường hợp không tìm thấy row hoặc row đã bị session khác khóa.

### 10.3. Optimistic locking với version column

Nếu không muốn khóa row trong suốt thời gian ứng dụng xử lý, có thể dùng cột phiên bản:

~~~sql
ALTER TABLE account_balance_lab
ADD version_no NUMBER DEFAULT 0 NOT NULL;
~~~

Ứng dụng đọc BALANCE và VERSION_NO, ví dụ version 7. Khi cập nhật:

~~~sql
UPDATE account_balance_lab
SET    balance = :new_balance,
       version_no = version_no + 1
WHERE  account_id = :account_id
AND    version_no = :old_version_no;
~~~

Nếu SQL%ROWCOUNT = 1, cập nhật thành công. Nếu bằng 0, row đã bị thay đổi hoặc không còn tồn tại theo điều kiện; ứng dụng cần đọc lại và xử lý xung đột.

Optimistic locking phù hợp khi xung đột hiếm và ứng dụng có thể retry. Version column phải được tăng nhất quán bởi mọi đường ghi liên quan.

## 11. SELECT FOR UPDATE và các tùy chọn chờ khóa

SELECT FOR UPDATE là locking read, khác với SELECT thông thường.

### 11.1. Cú pháp cơ bản

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = :account_id
FOR UPDATE;
~~~

Row được khóa cho transaction hiện tại. Khóa tồn tại đến COMMIT hoặc ROLLBACK.

### 11.2. NOWAIT

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = :account_id
FOR UPDATE NOWAIT;
~~~

Nếu row đã bị session khác khóa, statement không chờ mà trả lỗi ngay (thường là ORA-00054 trong ngữ cảnh resource busy).

### 11.3. WAIT n

~~~sql
SELECT account_id, balance
FROM account_balance_lab
WHERE account_id = :account_id
FOR UPDATE WAIT 5;
~~~

Session chờ tối đa số giây được chỉ định để lấy khóa. Nếu hết thời gian mà chưa lấy được, statement báo lỗi.

### 11.4. SKIP LOCKED

~~~sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED bỏ qua row đang bị session khác khóa thay vì chờ. Đây là kỹ thuật hữu ích cho nhiều worker cùng lấy việc từ queue, nhưng cần thiết kế thêm trạng thái, lease/timeout và recovery để tránh job bị bỏ quên.

Không dùng SKIP LOCKED cho mọi nghiệp vụ đọc dữ liệu: nó cố ý không trả những row đang bị khóa, nên kết quả không phải một danh sách đầy đủ.

### 11.5. Locking read không phải cách giữ snapshot cho báo cáo

Nếu mục tiêu chỉ là nhiều câu SELECT nhìn cùng một ảnh chụp, khóa mọi row bằng SELECT FOR UPDATE là cách quá nặng và thay đổi semantics. Cân nhắc transaction READ ONLY, SERIALIZABLE hoặc Flashback Query AS OF SCN.

## 12. Khi cần một ảnh chụp xuyên suốt transaction

READ COMMITTED phù hợp khi mỗi statement được phép thấy commit mới. Một số báo cáo hoặc phép đối soát lại cần nhiều query cùng nhìn một trạng thái dữ liệu.

Oracle có hai lựa chọn transaction-level isolation thường dùng:

- SET TRANSACTION READ ONLY: transaction chỉ đọc và giữ một snapshot nhất quán cho các query trong transaction.
- SET TRANSACTION ISOLATION LEVEL SERIALIZABLE: transaction có snapshot nhất quán ở cấp transaction và vẫn có thể DML; các xung đột ghi có thể gây ORA-08177.

### 12.1. READ ONLY transaction

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM orders;
SELECT SUM(order_total) FROM orders;
SELECT COUNT(*) FROM order_lines;

COMMIT;
~~~

Các SELECT trong read-only transaction nhìn cùng một ảnh chụp dữ liệu được thiết lập tại thời điểm transaction bắt đầu. Commit từ session khác sau thời điểm đó không làm thay đổi kết quả snapshot của các câu SELECT tiếp theo trong transaction.

Đặc điểm:

- Dùng cho báo cáo nhiều câu query cần nhất quán với nhau.
- Không thực hiện INSERT, UPDATE, DELETE, MERGE trong read-only transaction.
- Không dùng SELECT FOR UPDATE trong read-only transaction.
- Transaction vẫn cần kết thúc bằng COMMIT hoặc ROLLBACK để giải phóng tài nguyên và đóng phạm vi snapshot.

### 12.2. SERIALIZABLE transaction

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM account_balance_lab
WHERE account_id = 1;

-- Có thể thực hiện DML trong transaction.
UPDATE account_balance_lab
SET balance = balance - 10
WHERE account_id = 1;

COMMIT;
~~~

SERIALIZABLE cung cấp read consistency ở cấp transaction: các câu query nhìn dữ liệu đã commit tại thời điểm transaction bắt đầu, cộng với thay đổi do chính transaction đó tạo ra.

Khác READ ONLY, SERIALIZABLE cho phép DML. Tuy nhiên, nếu transaction cố sửa một row đã bị transaction khác thay đổi và commit sau khi transaction serializable bắt đầu, Oracle có thể báo:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Ứng dụng cần xử lý bằng cách ROLLBACK và retry toàn bộ transaction theo chính sách an toàn, nếu nghiệp vụ cho phép. Không retry riêng câu UPDATE mà bỏ qua các quyết định đã được tính từ snapshot cũ.

### 12.3. So sánh ba chế độ

| Đặc điểm | READ COMMITTED | READ ONLY | SERIALIZABLE |
| --- | --- | --- | --- |
| Mặc định của Oracle | Có | Không | Không |
| Snapshot | Mỗi statement | Cấp transaction | Cấp transaction |
| Thấy commit mới giữa hai query cùng transaction | Có thể | Không | Không |
| DML trong transaction | Có | Không | Có |
| SELECT FOR UPDATE | Có | Không | Có theo giới hạn của transaction |
| Xung đột ghi | Có thể chờ khóa và tiếp tục theo write consistency | Không có DML của transaction | Có thể ORA-08177 |
| Phù hợp | OLTP thông thường | Báo cáo nhiều query nhất quán | Giao dịch cần snapshot transaction và có xử lý serialization conflict |

READ ONLY và SERIALIZABLE không tự động tốt hơn READ COMMITTED. Chúng giữ snapshot lâu hơn và có thể cần undo lâu hơn; SERIALIZABLE còn yêu cầu ứng dụng xử lý lỗi serialization.

## 13. Ví dụ phantom read và cách giữ snapshot

Giả sử bảng ORDERS có ba đơn OPEN.

### 13.1. READ COMMITTED

Session A:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'OPEN';
~~~

Kết quả: 3.

Session B:

~~~sql
INSERT INTO orders (order_id, status, order_total)
VALUES (9001, 'OPEN', 100);

COMMIT;
~~~

Session A chạy lại:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'OPEN';
~~~

Kết quả: 4.

### 13.2. READ ONLY

Session A:

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT COUNT(*)
FROM orders
WHERE status = 'OPEN';
~~~

Session B chèn và COMMIT đơn mới như trên.

Session A chạy lại cùng SELECT trong transaction READ ONLY:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'OPEN';

COMMIT;
~~~

Kết quả vẫn là 3 vì các query của A dùng snapshot của transaction READ ONLY.

Khi transaction READ ONLY kết thúc, query mới thuộc transaction tiếp theo sẽ nhìn commit mới.

## 14. Flashback Query AS OF SCN: dùng cùng một mốc cho nhiều câu SQL

Một phương án khác là ghi nhận một SCN rồi dùng AS OF SCN để truy vấn các bảng tại cùng mốc dữ liệu. Cách này hữu ích khi cần nhiều câu SQL độc lập nhưng muốn chúng tham chiếu cùng snapshot, hoặc cần đối chiếu dữ liệu lịch sử trong phạm vi Flashback Query hỗ trợ.

### 14.1. Lấy SCN

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS snapshot_scn
FROM dual;
~~~

Ứng dụng lưu giá trị SCN này và truyền vào các câu truy vấn sau.

### 14.2. Query một bảng tại SCN cố định

~~~sql
SELECT order_id, status, order_total
FROM orders AS OF SCN :snapshot_scn
WHERE status = 'OPEN';
~~~

### 14.3. Query nhiều bảng tại cùng SCN

~~~sql
SELECT o.order_id,
       o.status,
       l.line_no,
       l.product_id,
       l.quantity
FROM orders AS OF SCN :snapshot_scn o
JOIN order_lines AS OF SCN :snapshot_scn l
  ON l.order_id = o.order_id
WHERE o.status = 'OPEN';
~~~

Mỗi bảng đều dùng cùng :snapshot_scn, nên join phản ánh dữ liệu ở cùng mốc. Nếu một bảng không dùng cùng SCN, kết quả có thể ghép các phiên bản ở các thời điểm khác nhau.

### 14.4. Điều kiện và giới hạn

- Cần quyền phù hợp để dùng Flashback Query.
- Undo cần thiết phải còn sẵn; nếu dữ liệu lịch sử đã bị tái sử dụng, query có thể thất bại.
- SCN phải nằm trong phạm vi dữ liệu có thể flashback.
- Không dùng Flashback Query như một bản sao lưu dài hạn.
- Cần cân nhắc DDL, object thay đổi và các giới hạn flashback theo release.

AS OF SCN là một snapshot tường minh cho query. Nó không thay đổi isolation level của transaction hiện tại.

## 15. Phân biệt READ COMMITTED với SERIALIZABLE qua hai session

### 15.1. Tình huống

Ban đầu có một row:

~~~sql
CREATE TABLE isolation_demo_lab (
    id NUMBER PRIMARY KEY,
    value_no NUMBER NOT NULL
);

INSERT INTO isolation_demo_lab VALUES (1, 10);
COMMIT;
~~~

### 15.2. Session A: SERIALIZABLE

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT value_no
FROM isolation_demo_lab
WHERE id = 1;
~~~

Kết quả 10. Transaction A đã bắt đầu snapshot của nó.

### 15.3. Session B: cập nhật và COMMIT

~~~sql
UPDATE isolation_demo_lab
SET value_no = 20
WHERE id = 1;

COMMIT;
~~~

### 15.4. Session A đọc lại

~~~sql
SELECT value_no
FROM isolation_demo_lab
WHERE id = 1;
~~~

A vẫn thấy 10 vì snapshot của SERIALIZABLE transaction được giữ từ đầu transaction.

Nếu A cố cập nhật row mà B đã thay đổi sau khi A bắt đầu:

~~~sql
UPDATE isolation_demo_lab
SET value_no = 30
WHERE id = 1;
~~~

Oracle có thể trả ORA-08177. Khi đó A cần ROLLBACK và quyết định có chạy lại toàn bộ transaction hay không.

### 15.5. Chạy lại với READ COMMITTED

Kết thúc transaction A, bắt đầu transaction READ COMMITTED mới. Hai câu SELECT riêng biệt có thể thấy 10 trước commit của B và 20 sau commit của B, tùy thứ tự thời gian.

## 16. Write consistency của DML

Đọc nhất quán và ghi nhất quán có liên quan nhưng không đồng nhất.

Một câu SELECT thông thường đọc snapshot tại statement start. Một câu DML cũng cần đánh giá dữ liệu theo quy tắc nhất quán, đồng thời phải lấy khóa để thay đổi row. Khi DML đụng row đang bị transaction khác khóa, nó có thể chờ.

Ví dụ:

~~~sql
UPDATE inventory
SET    quantity = quantity - 1
WHERE  product_id = :product_id
AND    quantity > 0;
~~~

Nếu hai session cùng cập nhật row này, Oracle quản lý row lock và điều kiện DML theo cơ chế write consistency. Khi cần, Oracle có thể đánh giá lại statement sau khi chờ xung đột để tránh dùng predicate cũ một cách sai lệch. Chi tiết restart phụ thuộc tình huống và phiên bản; không nên xây dựng logic ứng dụng dựa vào giả định rằng mọi DML sẽ luôn chạy đúng một lần hoặc không bao giờ được đánh giá lại.

Thực hành tốt:

- Đưa điều kiện nghiệp vụ vào cùng câu UPDATE/DELETE khi có thể.
- Kiểm tra SQL%ROWCOUNT.
- Dùng khóa hoặc version column nếu quy trình có nhiều bước.
- Giữ transaction ngắn và xác định rõ retry policy.
- Không dựa vào một SELECT trước đó để bảo đảm row vẫn thỏa điều kiện ở statement DML sau.

## 17. READ COMMITTED trong ứng dụng và connection pool

Một ứng dụng thường dùng connection pool, trong đó cùng một database session có thể được mượn lại bởi nhiều request ở các thời điểm khác nhau.

Các rủi ro cần quản lý:

### 17.1. Transaction chưa được kết thúc

Nếu request quên COMMIT hoặc ROLLBACK, session có thể giữ row lock và undo lâu hơn dự kiến. Khi connection được trả về pool, request tiếp theo có thể gặp trạng thái transaction không mong muốn nếu pool không reset đúng cách.

### 17.2. Isolation level là trạng thái session/transaction

SET TRANSACTION áp dụng cho transaction hiện tại. Ứng dụng phải đặt đúng ở đầu transaction và kết thúc transaction trước khi connection được trả lại pool.

### 17.3. Autocommit và nhiều statement

Nếu autocommit bật, mỗi statement có thể thành transaction riêng. Khi đó không thể giả định hai câu SELECT đang dùng chung transaction chỉ vì chúng chạy trên cùng connection.

### 17.4. Quy tắc triển khai

- Bắt đầu và kết thúc transaction rõ ràng ở tầng service/repository.
- Luôn rollback khi xử lý exception trước khi trả connection về pool.
- Không để transaction mở trong khi chờ người dùng hoặc gọi API bên ngoài.
- Không thay đổi isolation level tùy tiện trên connection dùng chung.
- Nếu cần snapshot xuyên nhiều query, dùng READ ONLY/SERIALIZABLE hoặc AS OF SCN có chủ đích.

## 18. Các lỗi thường gặp liên quan đến read consistency

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| ORA-01555: snapshot too old | Undo cần cho consistent read không còn sẵn | Điều tra query dài, DML đồng thời, undo tablespace/retention |
| ORA-08177: can't serialize access for this transaction | Transaction SERIALIZABLE gặp row đã bị transaction khác sửa sau snapshot | ROLLBACK và cân nhắc retry toàn transaction |
| ORA-00054: resource busy and acquire with NOWAIT specified | SELECT FOR UPDATE NOWAIT hoặc thao tác lock không thể chờ | Xử lý retry/backoff hoặc báo tài nguyên đang bận |
| Query thứ hai thấy số liệu khác query đầu | READ COMMITTED dùng snapshot mới cho statement mới | Dùng READ ONLY/SERIALIZABLE/AS OF SCN nếu cần snapshot chung |
| Hai request ghi đè kết quả của nhau | Read-modify-write nhiều statement không có khóa/version/atomic update | Dùng atomic DML, SELECT FOR UPDATE hoặc optimistic locking |
| SELECT FOR UPDATE bị treo | Session khác đang giữ row lock và câu lệnh đang chờ | Kiểm tra blocker, dùng WAIT/NOWAIT/SKIP LOCKED đúng nghiệp vụ |
| Báo cáo nhiều bảng không cùng thời điểm | Các statement độc lập chạy trong READ COMMITTED hoặc AS OF SCN khác nhau | Dùng một transaction snapshot hoặc cùng SCN cho mọi bảng |

## 19. Bài thực hành: quan sát READ COMMITTED

> Cần hai connection Oracle độc lập, ví dụ hai worksheet SQL Developer hoặc hai terminal SQLcl. Không dùng hai tab nếu chúng thực chất dùng chung session.

### Bài A — Hai SELECT trong một transaction

1. Tạo bảng isolation_demo_lab và insert một row như phần 15.
2. Session A chạy SELECT value_no.
3. Session B UPDATE value thành 20 và COMMIT.
4. Session A chạy lại SELECT.
5. Ghi nhận hai kết quả.

Kỳ vọng: A đọc 10 lần đầu, 20 lần sau nếu B commit trước khi SELECT thứ hai bắt đầu.

### Bài B — Một SELECT dài và một commit ở giữa

Thiết kế một query đọc nhiều row hoặc chạy đủ lâu trong lab. Trong lúc query đang chạy, session khác cập nhật một số row và COMMIT.

Quan sát: query đang chạy tiếp tục dùng snapshot của statement start; query mới bắt đầu sau commit có thể thấy giá trị mới.

Không dùng DBMS_LOCK.SLEEP hoặc thủ thuật gây tải trên production. Chỉ thử trong database lab và có kiểm soát.

### Bài C — READ ONLY transaction

1. Session A chạy COMMIT; SET TRANSACTION READ ONLY.
2. A chạy SELECT lần đầu.
3. Session B INSERT một row và COMMIT.
4. A chạy lại SELECT.
5. Kết thúc A bằng COMMIT.
6. A chạy SELECT trong transaction mới.

Kỳ vọng: hai query trong READ ONLY thấy cùng snapshot; query sau transaction mới thấy row B đã commit.

### Bài D — SERIALIZABLE conflict

1. Session A bắt đầu SERIALIZABLE và đọc row.
2. Session B cập nhật row đó rồi COMMIT.
3. Session A thử cập nhật cùng row.
4. Quan sát ORA-08177 nếu tình huống tạo xung đột serialization.
5. ROLLBACK A và thử lại toàn transaction với dữ liệu mới.

### Bài E — SELECT FOR UPDATE

1. A chạy SELECT FOR UPDATE trên một account.
2. B thử UPDATE cùng account.
3. Quan sát B chờ.
4. A COMMIT.
5. B tiếp tục.

Thử lại với NOWAIT và WAIT 3 trong lab để so sánh hành vi.

### Bài F — Flashback Query cùng SCN

1. Lấy một SCN bằng DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER.
2. B thay đổi dữ liệu và COMMIT.
3. Query AS OF SCN với SCN đã lưu.
4. Query bình thường.
5. So sánh hai kết quả.

Kỳ vọng: Flashback Query đọc trạng thái tại SCN đã chọn; SELECT bình thường đọc snapshot mới của statement.

## 20. Checklist chọn cơ chế nhất quán

1. **Một câu SELECT có cần nhất quán nội bộ không?** Oracle đã cung cấp statement-level read consistency trong READ COMMITTED.
2. **Nhiều câu SELECT có cần cùng một snapshot không?** Cân nhắc READ ONLY, SERIALIZABLE hoặc AS OF SCN.
3. **Transaction có cần DML không?** READ ONLY không cho DML; SERIALIZABLE cho DML nhưng có thể ORA-08177.
4. **Có thao tác đọc rồi ghi cùng row không?** Dùng atomic DML, SELECT FOR UPDATE hoặc optimistic locking.
5. **Có cần danh sách đầy đủ các row đang chờ xử lý không?** Không dùng SKIP LOCKED nếu bỏ qua row đang khóa là không chấp nhận được.
6. **Query chạy lâu không?** Đánh giá undo retention và nguy cơ ORA-01555.
7. **Có connection pool/autocommit không?** Kiểm soát transaction boundary và reset session.
8. **Có nhiều bảng cần đọc cùng mốc lịch sử không?** Dùng cùng SCN cho mọi bảng trong Flashback Query.
9. **Retry có an toàn không?** Chỉ retry toàn transaction khi có idempotency hoặc cơ chế ngăn ghi trùng.
10. **Đã kiểm tra quyền và release chưa?** READ ONLY, SERIALIZABLE, Flashback và locking có cú pháp/giới hạn riêng.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Mức cô lập transaction mặc định của Oracle là gì?

**Câu 2.** Trong READ COMMITTED, snapshot được xác định ở cấp statement hay transaction?

**Câu 3.** Nếu một transaction khác COMMIT giữa hai câu SELECT của cùng transaction, câu SELECT thứ hai có thể thấy dữ liệu mới không?

**Câu 4.** Một câu SELECT đang chạy có thấy commit xảy ra sau khi câu lệnh bắt đầu không?

**Câu 5.** Oracle dùng cơ chế nào để dựng phiên bản cũ cho consistent read?

**Câu 6.** READ COMMITTED có cho phép dirty read không?

**Câu 7.** Nonrepeatable read và phantom read khác nhau thế nào?

**Câu 8.** READ ONLY transaction khác SERIALIZABLE transaction ở quyền DML nào?

**Câu 9.** ORA-01555 thường liên quan đến tài nguyên nào?

**Câu 10.** ORA-08177 xuất hiện trong bối cảnh nào?

**Câu 11.** SELECT FOR UPDATE khác SELECT thông thường ra sao?

**Câu 12.** Khi nào nên dùng AS OF SCN?

**Câu 13.** Vì sao một câu UPDATE nguyên tử thường an toàn hơn chuỗi SELECT rồi UPDATE từ giá trị ứng dụng giữ?

**Câu 14.** Vì sao không nên giữ transaction mở trong lúc chờ người dùng hoặc gọi API?

<details>
<summary>Gợi ý đáp án</summary>

1. READ COMMITTED.
2. Cấp statement; mỗi câu lệnh có snapshot riêng.
3. Có. Nếu commit hoàn tất trước khi SELECT thứ hai bắt đầu, câu thứ hai có thể thấy thay đổi.
4. Không. Query đang chạy tiếp tục dùng snapshot tại thời điểm bắt đầu.
5. Undo records và consistent read.
6. Không. Oracle không cho transaction đọc thay đổi chưa commit của transaction khác.
7. Nonrepeatable read là cùng row đổi giá trị khi đọc lại; phantom là tập row thỏa predicate thay đổi.
8. READ ONLY chỉ cho query; SERIALIZABLE cho DML nhưng có thể gặp ORA-08177.
9. Undo cần thiết cho snapshot đã bị tái sử dụng/không còn sẵn.
10. Transaction SERIALIZABLE cố sửa dữ liệu đã bị transaction khác thay đổi sau khi snapshot của nó bắt đầu.
11. SELECT FOR UPDATE lấy row lock để bảo vệ read-modify-write; SELECT thường chỉ đọc consistent snapshot.
12. Khi nhiều câu query cần đọc cùng một mốc SCN hoặc cần truy vấn trạng thái lịch sử.
13. Điều kiện và phép thay đổi được thực hiện trong cùng statement, giảm khoảng thời gian race giữa đọc và ghi.
14. Có thể giữ row lock, undo và tài nguyên transaction lâu, làm tăng chờ khóa và lỗi đồng thời.

</details>

## 22. Tài liệu Oracle chính thức

1. [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): read consistency, multiversion concurrency control, statement-level consistency và transaction isolation.
2. [Oracle Database 19c Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transaction boundaries, COMMIT, ROLLBACK và tính nguyên tử.
3. [Oracle Database 19c SQL Language Reference — SET TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-TRANSACTION.html): READ COMMITTED, READ ONLY và SERIALIZABLE.
4. [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT FOR UPDATE và Flashback Query clauses.
5. [Oracle Database 19c Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): undo data, undo retention và quản lý undo tablespace.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_FLASHBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK.html): lấy SCN và các tiện ích Flashback.
7. [Oracle Database Error Messages — ORA-01555](https://docs.oracle.com/en/error-help/db/ora-01555/): snapshot too old.
8. [Oracle Database Error Messages — ORA-08177](https://docs.oracle.com/en/error-help/db/ora-08177/): không thể serialize access cho transaction.
9. [Oracle Database Error Messages — ORA-00054](https://docs.oracle.com/en/error-help/db/ora-00054/): resource busy khi yêu cầu NOWAIT.

**Nguyên tắc cần nhớ:** READ COMMITTED của Oracle tạo một ảnh chụp nhất quán cho **từng câu lệnh**. Vì vậy một query đang chạy không trộn commit mới xảy ra giữa chừng, nhưng câu SELECT tiếp theo trong cùng transaction có thể nhìn thấy commit đó. Oracle dùng undo để dựng phiên bản cũ cho consistent read. Nếu nhiều query cần chung một snapshot, hãy cân nhắc READ ONLY, SERIALIZABLE hoặc Flashback Query AS OF SCN. Nếu cần bảo vệ chuỗi đọc rồi ghi, dùng atomic DML, SELECT FOR UPDATE hoặc optimistic locking thay vì giả định READ COMMITTED khóa logic nghiệp vụ qua nhiều statement.
